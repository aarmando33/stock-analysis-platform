"""Shared historical-zone inputs for scores, workbook views and ticker dashboards."""
import json
import math
import pandas as pd
from historical_zones import zones_for, base_state

COVID_START='2020-02-19'
COVID_END='2020-04-30'
SINCE_COVID_START='2020-03-01'
ZONE_PRICE_HEADERS=[f'{p}{i} {field}' for p in ['S','R'] for i in [1,2,3]
                    for field in ['Min','Max','Min Date','Max Date']]
REFERENCE_HEADERS=[f'{kind} {window}{suffix}' for kind in ['Min','Max']
                   for window in ['COVID','Since COVID'] for suffix in ['', ' Date']]
ZONE_DETAIL_HEADERS=['Ticker','Current Price','Stock Name','capMil','Sector','Subsector','As Of',
                     'Basing Status','Bottom Status','Recent Volume','Average Volume 20D',
                     'Win%','Win52%','Win6mo%','price_suggest_80']
for _prefix in ['S','R']:
    for _i in [1,2,3]:
        ZONE_DETAIL_HEADERS += [f'{_prefix}{_i} {field}' for field in
            ['Min','Max','Min Date','Max Date','Contributing dates and prices','Lookback observations',
             'Band Known Date','Defended tests','Status','Test / break / reclaim evidence']]
ZONE_DETAIL_HEADERS += REFERENCE_HEADERS+['COVID Coverage','Since COVID Coverage']

def reference_extremes(history, cutoff):
    """Adjusted daily extremes; explicit coverage, no future rows or invented prices."""
    g=history.copy()
    g['Date']=pd.to_datetime(g.Date)
    g=g[g.Date.le(pd.Timestamp(cutoff))].sort_values('Date')
    out={}
    for label,start,end in [('COVID',COVID_START,COVID_END),('Since COVID',SINCE_COVID_START,cutoff)]:
        h=g[g.Date.between(pd.Timestamp(start),pd.Timestamp(end))].dropna(subset=['Low','High'])
        complete=bool(len(h) and h.Date.min()<=pd.Timestamp(start)+pd.Timedelta(days=3)
                      and h.Date.max()>=pd.Timestamp(end)-pd.Timedelta(days=3))
        # The COVID crash window needs full coverage. Since-COVID extrema can
        # describe a later IPO, but its shorter available window is explicit.
        usable=bool(len(h) and (complete or label=='Since COVID'))
        out[label+' Coverage']='Full window' if complete else (
            f"Available history {h.Date.min().date()} to {h.Date.max().date()}" if len(h) else 'Unavailable')
        for kind,column,fn in [('Min','Low','idxmin'),('Max','High','idxmax')]:
            key=f'{kind} {label}';row=h.loc[getattr(h[column],fn)()] if usable else None
            out[key]=float(row[column]) if row is not None else None
            out[key+' Date']=row.Date.date().isoformat() if row is not None else None
    return out

def wide_zone_fields(selected):
    out={}
    for side,prefix in [('Support','S'),('Resistance','R')]:
        for i,tier in [(1,'Short'),(2,'Next'),(3,'Major')]:
            z=selected.get(side+' '+tier);key=f'{prefix}{i}'
            for field,source in [('Min','low'),('Max','high'),('Status','state'),
                                 ('Lookback observations','window'),('Band Known Date','band_known_date'),
                                 ('Defended tests','tests_since_break')]:
                out[key+' '+field]=z[source] if z else None
            for edge,source in [('Min','low'),('Max','high')]:
                out[key+' '+edge+' Date']='; '.join(sorted({m['date'] for m in z['members'] if m['price']==z[source]})) if z else None
            out[key+' Contributing dates and prices']='; '.join(
                f"{m['date']}: {m['price']:.6f}" for m in sorted(z['members'],key=lambda m:m['date'])) if z else None
            out[key+' Test / break / reclaim evidence']='; '.join(
                f"{e['type']} {e['date']} -> {e.get('resolved','')}" for e in z['events']) if z else None
    return out

def number(v):
    try:return math.isfinite(float(v))
    except (TypeError,ValueError):return False

def zone_inputs(history, price):
    g=history.copy().reset_index(drop=True)
    g['Date']=pd.to_datetime(g.Date).dt.strftime('%Y-%m-%d')
    selected,allzones,extra,atr,tolerance=zones_for(g)
    recent=[z for z in allzones if z['side']=='Support' and z['tier']=='Short' and z['state']=='Broken' and z['last_break'] and z['last_break']>=g.Date.iloc[max(0,len(g)-3)] and 0<(z['low']-price)/price<=.05]
    lower=bool(g.Low.tail(10).min()<g.Low.iloc[-21:-10].min() and g.High.tail(10).max()<g.High.iloc[-21:-10].max()) if len(g)>=21 else False
    payload={'selected':selected,'extra_deep':extra,'tolerance_pct':tolerance*100 if tolerance else None,'recent_zone_break':bool(recent),'lower_structure':lower}
    out={}
    for side,prefix in [('Support','S'),('Resistance','R')]:
        for i,tier in [(1,'Short'),(2,'Next')]:
            z=selected[side+' '+tier]
            out[f'{prefix}{i} Min']=z['low'] if z else None
            out[f'{prefix}{i} Max']=z['high'] if z else None
            out[f'{prefix}{i} Status']=z['state'] if z else 'Unavailable'
        for label,tier in [('Short','Short'),('Major','Major')]:
            k=label+' '+side;z=selected[side+' '+tier]
            out[k]=(z['high'] if side=='Support' else z['low']) if z else None
            out[k+' Source']=f"Historical pivot zone; {z['window']} observations" if z else 'Unavailable'
            out[k+' Date']=max(m['date'] for m in z['members']) if z else None
            out[k+' Strength']=min(100,20*z['tests_since_break']) if z else None
            out[k+' Tests']=z['tests_since_break'] if z else None
            out[k+' Confirmed Date']=z['band_known_date'] if z else None
            out[k+' Test Dates']=('; '.join(e['date'] for e in z['events'] if current_test(z,e)) or None) if z else None
    out['_zone_data']=payload
    return out

def current_test(z,e):
    return e['type'].startswith('Defended') and e['date']>z['band_known_date'] and (not z['last_break'] or e['date']>z['last_break'])

def basing_inputs(history,out):
    g=history.copy().reset_index(drop=True);g['Date']=pd.to_datetime(g.Date).dt.strftime('%Y-%m-%d')
    b=base_state(g,{**out['_zone_data'],'old':out})
    return {'Basing Status':b['status'],'Bottom Min':b['bottom_low'],'Bottom Max':b['bottom_high'],
            'Bottom/Falling-Knife Status':b['bottom'],'Base Reference':b['reference'],
            'Base Observed Min':b['low'],'Base Observed Max':b['high'],'Base Observations':b['days'],
            'Base Range %':b['range_pct'],'Base Evidence':b['reason'],'Bottom Pivot Dates':'; '.join(b.get('bottom_dates',[])) or None}

DETAIL_HEADERS=['Ticker','Stock Name','Current Price','Market Cap','As Of','Zone','Min','Max','Contributing dates and prices',
                'Lookback observations','Band Known Date','Current-band defended tests','Support/Resistance Status','Basing Status',
                'Bottom Status','Win%','Win52%','Win6mo%','price_suggest_80','Test / break / reclaim evidence']

def report_details(report,histories,payloads,downloaded_at):
    """Derive both presentations from identical calculation records; preserve failed names."""
    tickers=[];details=[];summary=[]
    for r in report['calculations']:
        sym=r['Ticker'];p=payloads.get(sym,{});zones=[]
        selected=p.get('selected',{})
        valid=histories[histories.Symbol.eq(sym)] if r.get('price_status')=='OK' else histories.iloc[:0]
        wide={**wide_zone_fields(selected),**reference_extremes(valid,report['session'])}
        r.update(wide)
        summary.append({**r,'Current Price':r.get('Price') if r.get('price_status')=='OK' else None,
                        'As Of':report['session'],'Bottom Status':r.get('Bottom/Falling-Knife Status'),
                        'Win%':r.get('Primary Win%'),'Win52%':r.get('52W Closing-Range Win%')})
        for key,z in list(selected.items())+[(z['side']+' Further Deep',z) for z in p.get('extra_deep',[])]:
            if not z:continue
            zones.append({'id':key,'side':z['side'],'tier':key.removeprefix(z['side']+' '),'low':z['low'],'high':z['high'],
                'status':z['state'],'dates':[x['date'] for x in z['members']], 'tests':z['tests_since_break'],
                'test_dates':[e['date'] for e in z['events'] if current_test(z,e)],'window':f"{z['window']} observations; pivot radius {z['pivot_width']}"})
        for key in ['Support Short','Support Next','Resistance Short','Resistance Next']:
            z=selected.get(key)
            vals=[sym,r.get('Stock Name') or 'Unavailable',r.get('Price') if r.get('price_status')=='OK' else None,r.get('Market Cap'),report['session'],key,
                  z['low'] if z else None,z['high'] if z else None,
                  '; '.join(f"{x['date']}: {x['price']:.6f}" for x in sorted(z['members'],key=lambda x:x['date'])) if z else 'Unavailable',
                  z['window'] if z else None,z['band_known_date'] if z else None,z['tests_since_break'] if z else None,
                  z['state'] if z else 'Unavailable',r.get('Basing Status','Unavailable'),r.get('Bottom/Falling-Knife Status','Unavailable'),
                  r.get('Primary Win%'),r.get('52W Closing-Range Win%'),r.get('Win6mo%'),r.get('price_suggest_80'),
                  '; '.join(f"{e['type']} {e['date']} -> {e.get('resolved','')}" for e in z['events']) if z else 'Unavailable']
            details.append(dict(zip(DETAIL_HEADERS,vals)))
        # No valid-looking chart or technical data for an unusable ticker.
        g=histories[histories.Symbol.eq(sym)] if r.get('price_status')=='OK' else histories.iloc[:0]
        g=g[pd.to_datetime(g.Date).le(pd.Timestamp(report['session']))].dropna(subset=['Open','High','Low','Close']).sort_values('Date')
        tickers.append({'ticker':sym,'name':r.get('Stock Name') or 'Unavailable','market_cap':r.get('Market Cap'),
            'price':r.get('Price') if r.get('price_status')=='OK' else None,'win':r.get('Primary Win%'),'win52':r.get('52W Closing-Range Win%'),
            'win6':r.get('Win6mo%'),'price80':r.get('price_suggest_80'),'basing':r.get('Basing Status','Unavailable'),
            'bottom':r.get('Bottom/Falling-Knife Status','Unavailable'),'base_low':r.get('Base Observed Min'),'base_high':r.get('Base Observed Max'),
            'base_days':r.get('Base Observations'),'flat_range_pct':r.get('Base Range %'),'research_coverage':r.get('Research Coverage %'),
            'zones':zones,'history':[{'date':pd.Timestamp(x.Date).date().isoformat(),'open':round(x.Open,6),'high':round(x.High,6),'low':round(x.Low,6),'close':round(x.Close,6),'volume':float(x.Volume) if number(x.Volume) else None} for x in g.itertuples()],
            'indicators':{k:r.get(k) for k in ['price_status','RSI(14)','ATR','20D MA','50D MA','100D MA','200D MA','MACD','1M %','6M %','Drawdown From High %','Base Reference','Base Evidence','Bottom Min','Bottom Max','Bottom Pivot Dates']}})
    report['zone_details']=details
    report['zone_summary']=summary
    lookup={row['Ticker']:row for row in report['calculations']}
    for rows in report.get('views',{}).values():
        for row in rows:
            original=lookup[row['Ticker']]
            row.update({k:original.get(k) for k in ZONE_PRICE_HEADERS+REFERENCE_HEADERS+['COVID Coverage','Since COVID Coverage']})
    report['ticker_dashboard_data']={'cutoff':report['session'],'downloaded_at':downloaded_at,'tickers':tickers}
    report['zone_method']='Historical pivot zones v1; unique post-confirmation tests; technical basing separate from research coverage'
    return report
