"""Gate scheduled retries and attest to a fresh, intact production artifact."""
import argparse
import csv
from datetime import datetime,timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import urllib.request
import urllib.error
from zipfile import ZipFile
from zoneinfo import ZoneInfo

SUMMER_CRON='17,37,57 20-22 * * 1-5'
WINTER_CRON='17,37,57 21-23 * * 1-5'
REPORT_ARTIFACT='stock-price-feed'
READY_ARTIFACT='stock-monitor-ready'

def scheduled_window(event,schedule,now=None):
    if event!='schedule':return True
    local=(now or datetime.now(timezone.utc)).astimezone(ZoneInfo('America/Chicago'))
    chosen=SUMMER_CRON if local.utcoffset().total_seconds()==-18000 else WINTER_CRON
    return schedule==chosen

def output(name,value):
    with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf8') as f:
        f.write(f'{name}={str(value).lower() if isinstance(value,bool) else value}\n')

def expected_symbols(root):
    with (root/'tickers.csv').open(encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    symbols=[r.get('Symbol') or r.get('Ticker') for r in rows]
    if not symbols or None in symbols or len(set(symbols))!=len(symbols):
        raise ValueError('Invalid monitor universe')
    return symbols

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def confined(root,name):
    path=(root/name).resolve()
    if not path.is_relative_to(root.resolve()):raise ValueError('Unsafe provenance path')
    return path

def validate_output(folder,root,session,symbols):
    audit=json.loads((folder/'price_audit.json').read_text(encoding='utf8'))
    report=json.loads((folder/'monitor_results.json').read_text(encoding='utf8'))
    if report.get('failure') or report.get('historical'):
        raise ValueError('Report is failed or historical')
    if report.get('session')!=session or audit.get('expected_market_date')!=session or audit.get('latest_market_date')!=session:
        raise ValueError('Production dates do not match required market session')
    rows=report.get('calculations',[])
    if len(rows)!=len(symbols) or {r['Ticker'] for r in rows}!=set(symbols):
        raise ValueError('Monitor universe mismatch')
    if report['counts']['Expected']!=len(symbols) or audit['expected_tickers']!=len(symbols):
        raise ValueError('Expected coverage mismatch')
    usable=sum(r.get('price_status')=='OK' for r in rows)
    if usable==0 or report['counts']['Usable']!=usable:
        raise ValueError('No usable prices or inconsistent coverage')
    for row in rows:
        if row.get('price_status')=='OK' and (row.get('Price Date')!=session
            or not isinstance(row.get('Price'),(float,int))
            or not math.isfinite(row['Price']) or row['Price']<=0):
            raise ValueError('Usable ticker lacks a current valid price')
    required_code={'buy_sell_monitor.py','export_monitor.py','historical_zones.py','zone_monitor.py',
                   'compact_monitor.py','ticker_dashboard.py','profile_feed.py','profile_enrichment.py'}
    if not required_code.issubset(report.get('code_sha256',{})):
        raise ValueError('Missing code provenance')
    if not {'price_audit.json','prices_latest.csv','price_history.csv.gz'}.issubset(report.get('source_sha256',{})):
        raise ValueError('Missing price provenance')
    if not {'universe','profiles.json','symbol_aliases.csv'}.issubset(report.get('input_sha256',{})):
        raise ValueError('Missing profile/universe provenance')
    hashes=0
    for group in ['source_sha256','input_sha256','code_sha256']:
        for name,sha in report[group].items():
            path=root/'tickers.csv' if name=='universe' else confined(root if group=='code_sha256' else folder,name)
            if digest(path)!=sha:raise ValueError(f'Integrity mismatch: {name}')
            hashes+=1
    files={}
    for stem,ext in [('Stock_Buy_Sell_Monitor','xlsx'),('Stock_Buy_Sell_Ticker_Dashboard','html')]:
        plain=folder/f'{stem}.{ext}';dated=folder/f'{stem}_{session}.{ext}'
        if not plain.is_file() or plain.stat().st_size==0 or digest(plain)!=digest(dated):
            raise ValueError('Missing or mismatched dated deliverable')
        files[dated.name]=digest(dated)
    from openpyxl import load_workbook
    workbook=load_workbook(folder/'Stock_Buy_Sell_Monitor.xlsx',read_only=True,data_only=True)
    try:
        master=list(workbook['Master'].values)
        if len(master)!=len(symbols)+1 or {r[0] for r in master[1:]}!=set(symbols):
            raise ValueError('Workbook universe mismatch')
        zone=list(workbook['Zone Details'].values)
        if len(zone)!=len(symbols)+1 or {r[0] for r in zone[1:]}!=set(symbols):
            raise ValueError('Workbook zone rows mismatch')
    finally:workbook.close()
    html=(folder/'Stock_Buy_Sell_Ticker_Dashboard.html').read_text(encoding='utf8')
    data=json.loads(html.split('<script id="dashboard-data" type="application/json">')[1].split('</script>')[0])
    tickers=data['tickers']
    if data['cutoff']!=session or len(tickers)!=len(symbols) or {t['ticker'] for t in tickers}!=set(symbols):
        raise ValueError('Dashboard cutoff/universe mismatch')
    by={r['Ticker']:r for r in rows}
    for t in tickers:
        if any(h[0]>session for h in t['history']):raise ValueError('Future dashboard history')
        row=by[t['ticker']];expected=row.get('Price') if row.get('price_status')=='OK' else None
        if expected is None:
            if t['price'] is not None or t['history']:raise ValueError('Invalid ticker has current chart')
        elif not isinstance(t['price'],(float,int)) or not math.isclose(t['price'],expected,rel_tol=1e-10,abs_tol=1e-8):
            raise ValueError('Dashboard price mismatch')
    return {'schema_version':1,'ready':True,'session':session,'tickers':symbols,
            'counts':report['counts'],'verified_hashes':hashes,'deliverable_sha256':files,
            'retry_needed':any(r.get('price_status') not in ['OK','UNCOMPLETED_CRYPTO_CANDLE','INSUFFICIENT_HISTORY'] for r in rows)
                           or report.get('profile_coverage',{}).get('Failed',0)>0,
            'report_sha256':digest(folder/'monitor_results.json')}

def ready_matches(record,session,head,run_id,symbols,allow_partial=False):
    return (record.get('schema_version')==1 and record.get('ready') is True
            and record.get('session')==session and record.get('head_sha')==head
            and str(record.get('run_id'))==str(run_id)
            and (allow_partial or not record.get('retry_needed',False))
            and len(record.get('tickers',[]))==len(symbols)
            and set(record.get('tickers',[]))==set(symbols)
            and record.get('verified_hashes',0)>=14
            and record.get('counts',{}).get('Expected')==len(symbols)
            and 0<record.get('counts',{}).get('Usable',0)<=len(symbols)
            and len(record.get('deliverable_sha256',{}))==2
            and all(isinstance(v,str) and len(v)==64 and set(v.lower())<=set('0123456789abcdef')
                    for v in record.get('deliverable_sha256',{}).values()))

class GitHub:
    def __init__(self,repo,token):self.repo=repo;self.token=token
    def get(self,path,binary=False):
        request=urllib.request.Request('https://api.github.com/repos/'+self.repo+'/'+path,
            headers={'Authorization':'Bearer '+self.token,'Accept':'application/vnd.github+json','User-Agent':'stock-monitor-readiness'})
        # Do not carry the API credential to the artifact storage redirect.
        if binary:
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self,*args):return None
            try:
                with urllib.request.build_opener(NoRedirect()).open(request,timeout=30) as response:return response.read()
            except urllib.error.HTTPError as exc:
                if exc.code not in [301,302,303,307,308]:raise
                target=exc.headers['Location']
                if not target.startswith('https://'):raise ValueError('Invalid artifact redirect')
                with urllib.request.urlopen(target,timeout=30) as response:return response.read()
        with urllib.request.urlopen(request,timeout=30) as response:return json.load(response)

def prior_ready(api,session,head,symbols,allow_partial=False):
    runs=api.get('actions/workflows/daily-prices.yml/runs?branch=main&status=success&per_page=30')['workflow_runs']
    for run in runs:
        if run['head_sha']!=head or run['conclusion']!='success' or run['head_branch']!='main':continue
        artifacts=api.get(f"actions/runs/{run['id']}/artifacts?per_page=100")['artifacts']
        present=[a for a in artifacts if not a['expired']]
        if not any(a['name']==REPORT_ARTIFACT and a['size_in_bytes']>0 for a in present):continue
        markers=sorted((a for a in present if a['name']==READY_ARTIFACT),key=lambda a:a['id'],reverse=True)
        for marker in markers:
            with ZipFile(io.BytesIO(api.get(f"actions/artifacts/{marker['id']}/zip",binary=True))) as archive:
                info=archive.getinfo('ready.json')
                if info.file_size>1048576:raise ValueError('Oversized readiness record')
                record=json.loads(archive.read(info))
            if ready_matches(record,session,head,run['id'],symbols,allow_partial=allow_partial):return record
    return None

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['window','probe','mark'])
    parser.add_argument('--folder',type=Path,default=Path('outputs'))
    args=parser.parse_args();root=Path(__file__).resolve().parent
    event=os.environ.get('GITHUB_EVENT_NAME','manual')
    if args.mode=='window':
        output('run',scheduled_window(event,os.environ.get('SCHEDULE','')));return
    from buy_sell_monitor import latest_session
    session=latest_session();symbols=expected_symbols(root)
    if args.mode=='probe':
        record=None
        if event=='schedule':
            try:record=prior_ready(GitHub(os.environ['GITHUB_REPOSITORY'],os.environ['GH_TOKEN']),session,os.environ['GITHUB_SHA'],symbols)
            except Exception as exc:print(f'Readiness lookup unavailable ({type(exc).__name__}); performing a fresh validated run.')
        output('refresh',record is None)
        if record:print(f"Already verified session {session}, run {record['run_id']}; skipping duplicate price refresh.")
        else:print(f'Required market session {session}; generating a fresh report.')
        return
    record=validate_output(args.folder,root,session,symbols)
    record.update(head_sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],
                  run_attempt=int(os.environ['GITHUB_RUN_ATTEMPT']),
                  generated_at_utc=datetime.now(timezone.utc).isoformat(),
                  validator_sha256=digest(root/'production_integrity.py'))
    (args.folder/'ready.json').write_text(json.dumps(record,indent=2),encoding='utf8')
    print(f"Ready: {session}; {record['counts']['Usable']}/{len(symbols)} usable; {record['verified_hashes']} verified hashes.")

if __name__=='__main__':main()
