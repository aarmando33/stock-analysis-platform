"""Fetch fresh, bounded Yahoo profiles and enrich the daily display snapshot."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import shutil
from urllib.parse import quote

from profile_enrichment import enrich


def now():
    return datetime.now(timezone.utc).isoformat()


def fetch_one(symbol):
    # A separate process makes even a hung provider call subject to a hard limit.
    import yfinance as yf
    data=yf.Ticker(symbol).get_info()
    cap=data.get('marketCap')
    cap=cap if isinstance(cap,(int,float)) and math.isfinite(cap) and cap>0 else None
    return {'Stock Name':data.get('longName') or data.get('shortName'),
            'Market Cap':cap,'Currency':data.get('currency'),'Sector':data.get('sector'),
            'Subsector':data.get('industry'),'Quote Type':data.get('quoteType')}


def bounded_profile(symbol, timeout=20):
    escaped=quote(symbol,safe='')
    profile={'Provider Symbol':symbol,'Profile Retrieved UTC':now(),
             'Profile Source':f'https://finance.yahoo.com/quote/{escaped}/profile/',
             'Market Cap Source':f'https://finance.yahoo.com/quote/{escaped}/'}
    try:
        response=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--symbol',symbol],
                                capture_output=True,text=True,timeout=timeout,check=True)
        data=json.loads(response.stdout.strip().splitlines()[-1])
        if not isinstance(data,dict):raise ValueError('Provider returned no profile object')
        profile.update(data)
        if not data.get('Stock Name'):profile['Profile Error']='Provider returned no stock name'
    except subprocess.TimeoutExpired:
        profile['Profile Error']=f'Profile request exceeded {timeout} seconds'
    except (subprocess.SubprocessError,ValueError,IndexError,OSError) as exc:
        profile['Profile Error']=f'Profile unavailable ({type(exc).__name__})'
    profile['Profile Retrieved UTC']=now()
    return profile


def collect(tickers, aliases, workers=6, timeout=20):
    tickers=list(dict.fromkeys(tickers))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        profiles=list(pool.map(lambda ticker:bounded_profile(aliases.get(ticker,ticker),timeout),tickers))
    return dict(zip(tickers,profiles))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_enriched(report, profiles, profile_path, output_path, aliases_path):
    profile_path=Path(profile_path);output_path=Path(output_path)
    profile_path.parent.mkdir(parents=True,exist_ok=True)
    archived_aliases=profile_path.parent/'symbol_aliases.csv'
    if Path(aliases_path).resolve()!=archived_aliases.resolve():
        shutil.copyfile(aliases_path,archived_aliases)
    profile_path.write_text(json.dumps(profiles,indent=2,allow_nan=False),encoding='utf-8')
    result=enrich(report,profiles)
    result.setdefault('input_sha256',{}).update({profile_path.name:sha(profile_path),
                                                'symbol_aliases.csv':sha(archived_aliases)})
    root=Path(__file__).resolve().parent
    result.setdefault('code_sha256',{}).update({name:sha(root/name) for name in ['profile_feed.py','profile_enrichment.py']})
    result['profile_coverage']={'Expected':len(report['calculations']),
        'Named':sum(bool(p.get('Stock Name')) for p in profiles.values()),
        'Failed':sum(bool(p.get('Profile Error')) for p in profiles.values()),
        'Retrieved UTC':now()}
    output_path.parent.mkdir(parents=True,exist_ok=True)
    temporary=output_path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
    temporary.replace(output_path)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--symbol',help=argparse.SUPPRESS)
    parser.add_argument('--input',type=Path,default=Path('outputs/monitor_results.json'))
    parser.add_argument('--output',type=Path,default=Path('outputs/monitor_results.json'))
    parser.add_argument('--profiles',type=Path,default=Path('outputs/profiles.json'))
    parser.add_argument('--aliases',type=Path,default=Path('symbol_aliases.csv'))
    args=parser.parse_args()
    if args.symbol:
        print(json.dumps(fetch_one(args.symbol),allow_nan=False));return
    report=json.loads(args.input.read_text(encoding='utf-8'))
    with args.aliases.open(encoding='utf-8-sig',newline='') as source:
        aliases={r['Monitor Symbol']:r['Provider Symbol'] for r in csv.DictReader(source)}
    profiles=collect([r['Ticker'] for r in report['calculations']],aliases)
    result=write_enriched(report,profiles,args.profiles,args.output,args.aliases)
    print(json.dumps(result['profile_coverage']))


if __name__=='__main__':main()
