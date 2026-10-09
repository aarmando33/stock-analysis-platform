"""Attach dated provider profile metadata for display, without changing signals."""
import copy
import math
from compact_monitor import VOLUME_FIELDS

def enrich(report, profiles):
    result=copy.deepcopy(report)
    def fields(ticker):
        p=profiles.get(ticker,{})
        cap=p.get('Market Cap');currency=p.get('Currency')
        cap_ok=isinstance(cap,(int,float)) and math.isfinite(cap) and cap>0 and currency=='USD'
        no_sector=p.get('Quote Type') in ['CRYPTOCURRENCY','ETF','MUTUALFUND']
        return {'Stock Name':p.get('Stock Name') or 'Unavailable',
                'capMil':cap/1e6 if cap_ok else 'Unavailable',
                'Sector':p.get('Sector') or ('Not applicable' if no_sector else 'Unavailable'),
                'Subsector':p.get('Subsector') or ('Not applicable' if no_sector else 'Unavailable'),
                'Profile Retrieved UTC':p.get('Profile Retrieved UTC','Unavailable'),
                'Profile Source':p.get('Profile Source','Unavailable'),
                'Market Cap Source':p.get('Market Cap Source','Unavailable'),
                'Profile Error':p.get('Profile Error','')}
    for rows in [result.get('calculations',[]),result.get('zone_details',[]),*result.get('views',{}).values()]:
        for r in rows:r.update(fields(r['Ticker']))
    calc={r['Ticker']:r for r in result['calculations']}
    for t in result.get('ticker_dashboard_data',{}).get('tickers',[]):
        f=fields(t['ticker']);r=calc[t['ticker']]
        t.update(name=f['Stock Name'],market_cap=f['capMil']*1e6 if isinstance(f['capMil'],(int,float)) else None,
                 sector=f['Sector'],subsector=f['Subsector'],profile_retrieved=f['Profile Retrieved UTC'],
                 action=r.get('Overall Signal/Action','Unavailable'),action_reason=r.get('Action Reason','Unavailable'),
                 volume={key:r.get(key) for key in VOLUME_FIELDS})
        t.setdefault('indicators',{}).pop('price_status',None)
    result['profile_note']='capMil is provider market capitalization in USD millions, retrieved separately from the price snapshot. Subsector uses provider industry. Display metadata does not increase research coverage or change actions.'
    return result
