"""Versioned decision monitor. Values are computed here, never in the exporter.

All dates are as-of dates: a historical rebuild cannot use future fundamentals.
Missing evidence earns no points; fixed bucket weights are never renormalized.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

WEIGHTS = {'Location':20, 'Support/RR':25, 'Trend/RS':20,
           'Fundamentals':20, 'Flow':10, 'Environment':5}
NAN = float('nan')
ADDED_SYMBOLS = {'LRCX','AMAT','ETN','PWR','CIEN','ADI','ZS','MCHP'}


def finite(v):
    try:
        return bool(np.isfinite(float(v)))
    except (TypeError, ValueError):
        return False


def clip(v):
    return float(np.clip(v, 0, 100)) if finite(v) else NAN


def evidence_mean(values):
    # Missing evidence lowers points and coverage, never silently becomes neutral.
    return sum(float(v) if finite(v) else 0 for v in values)/len(values)


def range_position(series, price):
    s = series.dropna()
    if s.empty or not finite(price) or s.max() <= s.min():
        return NAN, NAN
    return clip(100*(s.max()-price)/(s.max()-s.min())), float(.2*s.max()+.8*s.min())


def rsi(series, n=14):
    d = series.diff()
    gain = d.clip(lower=0).ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    result = 100-100/(1+gain/loss)
    result = result.mask((loss==0)&(gain>0),100)
    return result.mask((loss==0)&(gain==0),50)


def macd(series):
    line = series.ewm(span=12,adjust=False).mean()-series.ewm(span=26,adjust=False).mean()
    signal = line.ewm(span=9,adjust=False).mean()
    return line, signal, line-signal


def atr(history):
    previous = history.Close.shift()
    tr = pd.concat([history.High-history.Low,(history.High-previous).abs(),
                    (history.Low-previous).abs()],axis=1).max(axis=1)
    return tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean()


def proximity(distance):
    if not finite(distance): return 'Unavailable'
    if distance<=2: return 'Strong Proximity'
    if distance<=3: return 'Near'
    if distance<=5: return 'Approaching'
    return 'Not Near'


def levels(history, current, major=False):
    """Separate short pivots (5–21) from 63/126/252-session major evidence.

    Candidate strength is independent touches plus confluence. Levels from
    moving averages remain identified as dynamic, not historical pivots.
    """
    candidates = []
    for n in ([63,126,252] if major else [5,21]):
        g = history.tail(n)
        if len(g)<n: continue
        # Confirmed local extrema require two observations on each side.
        for kind in ['Low','High']:
            v=g[kind]
            extreme = v.rolling(5,center=True).min() if kind=='Low' else v.rolling(5,center=True).max()
            pivots=g.loc[v.eq(extreme),['Date',kind]]
            for _, p in pivots.iterrows():
                candidates.append({'value':float(p[kind]),'source':f'{n}-session swing {kind.lower()}',
                                   'date':str(p.Date.date()),'window':n})
        for kind,agg in [('Low','min'),('High','max')]:
            i=getattr(g[kind],agg)()
            candidates.append({'value':float(i),'source':f'{n}-session range {kind.lower()}',
                               'date':str(g.loc[g[kind].eq(i),'Date'].iloc[-1].date()),'window':n})
    for n in ([50,100,200] if major else [20]):
        if len(history)>=n:
            candidates.append({'value':float(history.Close.tail(n).mean()),
                               'source':f'{n}-session MA','date':str(history.Date.iloc[-1].date()),'window':n})
    # Deduplicate confluence clusters so repeated horizons cannot create fake strength.
    clusters=[]
    for c in sorted(candidates,key=lambda x:x['value']):
        if clusters and abs(c['value']/clusters[-1]['value']-1)<=.005:
            clusters[-1]['sources'].add(c['source'])
        else:
            clusters.append({**c,'sources':{c['source']}})
    recent=history.tail(126 if major else 21)
    for c in clusters:
        touch=((recent.Low/c['value']-1).abs()<=.01)|((recent.High/c['value']-1).abs()<=.01)
        # Consecutive days are one test, not multiple independent confirmations.
        c['tests']=int((touch & ~touch.shift(fill_value=False)).sum())
        c['strength']=min(100,20*c['tests']+10*len(c['sources']))
        c['source']='; '.join(sorted(c['sources']))
    def choose(support):
        eligible=[c for c in clusters if (c['value']<current if support else c['value']>current)]
        if not eligible: return None
        if major:
            eligible.sort(key=lambda c:(-c['strength'],abs(c['value']/current-1)))
        else:
            eligible.sort(key=lambda c:abs(c['value']/current-1))
        return eligible[0]
    return choose(True),choose(False)


def ret(series,n):
    return 100*(series.iloc[-1]/series.iloc[-n-1]-1) if len(series)>n and series.iloc[-n-1]>0 else NAN


def relative_strength(stock,benchmark,n):
    # Align actual session dates rather than comparing mismatched observations.
    pair=pd.concat([stock,benchmark],axis=1,join='inner').dropna()
    if len(pair)<=n: return NAN
    ratios=pair.iloc[-1]/pair.iloc[-n-1]
    return float(100*(ratios.iloc[0]/ratios.iloc[1]-1))


def fundamental_evidence(raw):
    """Transparent raw-data normalizers; absent fields remain absent.

    Growth: -20%→0, 0%→50, +20%→100. Margin: 0%→0, 30%→100.
    Cash flow yield: 0%→0, 8%→100. Net debt / EBITDA: 0→100, 4→0.
    Revisions: -10%→0, 0%→50, +10%→100. All ratios use decimal units.
    """
    def number(name):return float(raw[name]) if finite(raw.get(name)) else NAN
    growth=[clip(50+number(k)*250) for k in ['Revenue Growth','EPS Growth']]
    margin=clip(number('Operating Margin')/0.30*100)
    cap=number('Market Cap');fcf=number('Free Cash Flow')
    cash=clip(fcf/cap/.08*100) if cap>0 and finite(fcf) else NAN
    debt=clip(100-number('Net Debt / EBITDA')*25)
    all_values=[*growth,margin,cash,debt]
    # Missing raw fields reduce the bucket's coverage, not just its points.
    fundamental=evidence_mean(all_values) if any(finite(v) for v in all_values) else NAN
    revision=clip(50+number('EPS Revision 90D')*500)
    pe=number('Forward PE');reference=number('Peer Forward PE')
    valuation=clip(50+50*(reference/pe-1)) if pe>0 and reference>0 else NAN
    return {'Fundamentals Score':fundamental,'Fundamental Input Coverage %':100*sum(finite(v) for v in all_values)/5,
            'Revisions Score':revision,'Valuation Score':valuation}


def calculate(history,price,session,benchmark=None,sector=None,context=None,position=None):
    # Protect direct callers as well as the file pipeline against future leakage.
    benchmark=benchmark.loc[benchmark.index<=pd.Timestamp(session)] if benchmark is not None else None
    sector=sector.loc[sector.index<=pd.Timestamp(session)] if sector is not None else None
    g=history[history.Date<=pd.Timestamp(session)].sort_values('Date').copy()
    c=g.Close; current=float(price); out={}
    for label,n in [('1W %',5),('2W %',10),('1M %',20),('3M %',63),('6M %',126)]:
        out[label]=100*(current/c.iloc[-n-1]-1) if len(c)>n and c.iloc[-n-1]>0 else NAN
    out['MomentumRaw']=float(np.nanmean([out['1M %'],out['3M %']]))
    previous_year=g[g.Date.dt.year<pd.Timestamp(session).year]
    out['YTD %']=100*(current/previous_year.Close.iloc[-1]-1) if len(previous_year) else NAN
    out['Primary Win%'],out['price_suggest_80']=range_position(g[g.Date>='2020-03-01'].Close,current)
    out['52W Closing-Range Win%'],_=range_position(g[g.Date>=pd.Timestamp(session)-pd.Timedelta(days=365)].Close,current)
    out['52W Win%']=out['52W Closing-Range Win%']
    for n in [20,50,100,200]:
        out[f'{n}D MA']=float(c.tail(n).mean()) if len(c)>=n else NAN
        old=c.iloc[:-5].tail(n).mean() if len(c)>=n+5 else NAN
        out[f'{n}D MA Slope %']=100*(out[f'{n}D MA']/old-1) if finite(old) and old>0 else NAN
    rs=rsi(c); line,signal,hist=macd(c); av=atr(g)
    out.update({'RSI(14)':float(rs.iloc[-1]),'MACD':float(line.iloc[-1]),
                'MACD Signal':float(signal.iloc[-1]),'MACD Histogram':float(hist.iloc[-1]),
                'ATR':float(av.iloc[-1]),'ATR %':float(100*av.iloc[-1]/current)})
    out['Momentum Status']='Improving' if len(hist)>5 and hist.iloc[-1]>hist.iloc[-6] else 'Deteriorating'
    v=g.Volume; volume_ok=len(v)>=21 and np.isfinite(v.tail(21)).all() and (v.tail(21)>=0).all() and v.iloc[-21:-1].sum()>0
    mean20=float(v.iloc[-21:-1].mean()) if volume_ok else NAN
    out['Recent Volume']=float(v.iloc[-1]) if volume_ok else NAN
    out['Average Volume 20D']=mean20
    out['Relative Volume']=float(v.iloc[-1]/mean20) if finite(mean20) and mean20>0 else NAN
    d=c.diff(); up=float(v.tail(20)[d.tail(20)>0].sum()) if volume_ok else NAN
    down=float(v.tail(20)[d.tail(20)<0].sum()) if volume_ok else NAN
    out['Up-Day Volume 20D']=up;out['Down-Day Volume 20D']=down
    out['Up/Down Volume Ratio']=up/down if finite(down) and down>0 else NAN
    out['Volume Contraction Ratio']=float(v.tail(5).mean()/v.iloc[-25:-5].mean()) if volume_ok and len(v)>=25 and v.iloc[-25:-5].mean()>0 else NAN
    signed=np.sign(d).fillna(0)*v.where(np.isfinite(v)&v.ge(0))
    obv=signed.cumsum();out['OBV']=float(obv.iloc[-1]) if volume_ok and np.isfinite(v).all() and v.ge(0).all() else NAN
    # Scale signed volume by positive volume, not by arbitrary OBV origin.
    flow20=100*signed.tail(20).sum()/v.tail(20).sum() if volume_ok and v.tail(20).sum()>0 else NAN
    out['20D Net Volume %']=float(flow20);out['20D Net Volume Basis']='20-session net signed volume / total volume'
    out['Money Flow']=('Unavailable' if not finite(flow20) else 'Accumulating' if flow20>=15 else
                       'Entering' if flow20>5 else 'Leaving' if flow20<=-15 else 'Distributing' if flow20<-5 else 'Neutral')
    out['Volume Confirmation']=('Unavailable' if not volume_ok else 'Strong' if out['Relative Volume']>=1.5 else 'Normal' if out['Relative Volume']>=.8 else 'Light')
    short=levels(g,current);major=levels(g,current,True)
    for label,level in zip(['Short Support','Short Resistance','Major Support','Major Resistance'],[*short,*major]):
        out[label]=level['value'] if level else NAN
        out[label+' Source']=level['source'] if level else 'Unavailable'
        out[label+' Date']=level['date'] if level else None
        out[label+' Strength']=level['strength'] if level else NAN
        out[label+' Tests']=level['tests'] if level else NAN
    support=out['Short Support'];resistance=out['Short Resistance']
    out['Distance to Support %']=100*(current-support)/current if finite(support) else NAN
    out['Distance to Resistance %']=100*(resistance-current)/current if finite(resistance) else NAN
    out['Support Proximity']=proximity(out['Distance to Support %'])
    out['Resistance Proximity']=proximity(out['Distance to Resistance %'])
    high21=g.High.tail(21).max();low21=g.Low.tail(21).min()
    compression=100*(high21-low21)/high21 if len(g)>=21 and high21>0 else NAN
    out['Range Compression 21D %']=compression
    basic=finite(compression) and compression<=10 and abs(out['1M %'])<=8
    higher_low=len(g)>=21 and g.Low.tail(10).min()>g.Low.iloc[-21:-10].min()
    volatility_contracting=len(av)>=21 and finite(av.iloc[-21]) and av.iloc[-1]<av.iloc[-21]
    recent_low=float(g.Low.tail(10).min()) if len(g)>=10 else NAN
    support_recent_test=finite(support) and finite(recent_low) and abs(recent_low-support)/current*100<=2
    support_rebound=finite(recent_low) and recent_low>0 and current/recent_low-1>=0.02
    support_holds=bool(finite(support) and out['Short Support Tests']>=2 and support_recent_test and support_rebound and current>=support)
    out['Support Defended']=support_holds
    source_text=str(out.get('Short Support Source','Unavailable'))
    out['Support Timeframe']=('5-session' if '5-session' in source_text else '21-session' if '21-session' in source_text else '20-session MA' if '20-session MA' in source_text else 'Unavailable')
    out['Basing Status']=('Confirmed Base' if basic and higher_low and support_holds and volatility_contracting and finite(out['Volume Contraction Ratio']) and out['Volume Contraction Ratio']<1 else 'Range Compressing' if basic else 'Not Basing')
    prior_high=g.High.iloc[-22:-1].max() if len(g)>=22 else NAN
    prior_low=g.Low.iloc[-22:-1].min() if len(g)>=22 else NAN
    breakout=finite(prior_high) and current>prior_high
    breakdown=finite(prior_low) and current<prior_low
    followed=len(g)>=23 and c.iloc[-2]>g.High.iloc[-23:-2].max()
    confirmed=breakout and followed and out['Relative Volume']>=1.5
    out['Breakout Status']='Confirmed Breakout' if confirmed else 'Breakout Watch' if breakout else 'None'
    out['Breakdown Status']='Support Breakdown' if breakdown else 'None'
    out['Breakout Level']=float(prior_high);out['Breakdown Level']=float(prior_low)
    out['Reversal Status']='Reversal Developing' if higher_low and out['Momentum Status']=='Improving' and current>out['20D MA'] and flow20>5 else 'Unconfirmed'
    out['Drawdown From High %']=100*(current/g.loc[g.Date>=pd.Timestamp(session)-pd.Timedelta(days=365),'High'].max()-1)
    out['Rebound From Recent Low %']=100*(current/g.Low.tail(63).min()-1)
    indexed=g.set_index('Date').Close
    for label,b in [('Market',benchmark),('Sector',sector)]:
        for n in [20,63]: out[f'RS vs {label} {n}D %']=relative_strength(indexed,b,n) if b is not None else NAN
    relative=[out[f'RS vs {label} {n}D %'] for label in ['Market','Sector'] for n in [20,63]]
    rotation=clip(evidence_mean([clip(50+x*5) if finite(x) else NAN for x in relative]))
    out['Rotation Score']=round(rotation/10,1) if any(finite(x) for x in relative) else NAN
    out['Rotation Stage']='Unavailable' if not all(finite(x) for x in relative) else 'Leading' if rotation>=70 else 'Improving' if rotation>=55 else 'Neutral' if rotation>=45 else 'Lagging'
    context=context or {}
    context={**context,**fundamental_evidence(context)}
    # Inputs below are evidence ratings with source/date and raw-input provenance.
    fundamental=context.get('Fundamentals Score',NAN);valuation=context.get('Valuation Score',NAN)
    environment=context.get('Environment Score',NAN);revisions=context.get('Revisions Score',NAN)
    if benchmark is not None and len(benchmark)>=200:
        b=benchmark.dropna()
        sector_state=100 if sector is not None and len(sector)>=50 and sector.iloc[-1]>sector.tail(50).mean() else 0 if sector is not None and len(sector)>=50 else NAN
        environment=evidence_mean([100 if b.iloc[-1]>b.tail(200).mean() else 0,
                                   100 if ret(b,20)>0 else 0,sector_state])
    out.update({k:context.get(k,NAN) for k in ['Market Cap','Revenue Growth','EPS Growth','Operating Margin','Free Cash Flow','Net Debt / EBITDA','EPS Revision 90D','Forward PE','Peer Forward PE']})
    out['Fundamental Input Coverage %']=context['Fundamental Input Coverage %']
    out['Buy Zone']=f'{support:.2f}–{support*1.02:.2f}' if support_holds else 'Unconfirmed'
    stop=support-av.iloc[-1] if support_holds and finite(av.iloc[-1]) else NAN
    if not finite(stop) or stop<=0: stop=NAN
    out['Invalidation']=float(stop);out['Downside %']=100*(current-stop)/current if finite(stop) and stop>0 else NAN
    out['Upside %']=out['Distance to Resistance %']
    rr=out['Upside %']/out['Downside %'] if finite(out['Downside %']) and out['Downside %']>0 else NAN
    out['Risk/Reward']=rr
    out['Trim Zone']=f'{resistance*.98:.2f}–{resistance:.2f}' if finite(resistance) else 'Unavailable'
    trend=[100 if current>out['50D MA'] else 0 if finite(out['50D MA']) else NAN,
           100 if out['50D MA Slope %']>0 else 0 if finite(out['50D MA Slope %']) else NAN,
           100 if out['MACD Histogram']>0 else 0, rotation if all(finite(x) for x in relative) else NAN]
    flow_score={'Accumulating':100,'Entering':80,'Neutral':50,'Distributing':20,'Leaving':0}.get(out['Money Flow'],NAN)
    buckets={'Location':[out['Primary Win%'],out['52W Closing-Range Win%'],valuation],
             'Support/RR':[out['Short Support Strength'],clip(rr/3*100) if finite(rr) else NAN],
             'Trend/RS':trend,'Fundamentals':[fundamental,revisions],
             'Flow':[flow_score,context.get('Institutional/Insider Score',NAN)],'Environment':[environment]}
    points=0.0;coverage=0.0
    for name,values in buckets.items():
        bucket_points=WEIGHTS[name]*evidence_mean(values)/100
        if name=='Fundamentals':
            fundamental_fraction=context['Fundamental Input Coverage %']/100 if finite(fundamental) else 0
            present_fraction=(fundamental_fraction + (1 if finite(revisions) else 0))/2
        else:
            present_fraction=sum(finite(x) for x in values)/len(values)
        points+=bucket_points
        coverage+=WEIGHTS[name]*present_fraction
        out[name+' Points']=round(bucket_points,2)
        out[name+' Coverage %']=round(100*present_fraction,1)
    out['Opportunity Score']=round(clip(points-(12 if breakdown else 0)-(5 if out['RSI(14)']>75 else 0)),1)
    out['Evidence Coverage %']=round(coverage,1)
    confirms=[100 if support_holds else 0,100 if higher_low else 0,
              100 if confirmed or (finite(out['Relative Volume']) and out['Relative Volume']>=1.2) else 0 if volume_ok else NAN,
              rotation if all(finite(x) for x in relative) else NAN,fundamental,revisions,
              flow_score,valuation,clip(rr/3*100) if finite(rr) else NAN,
              100 if out['MACD Histogram']>0 else 0]
    out['Setup Confidence']=round(evidence_mean(confirms),1)
    out['Setup Confidence Coverage %']=round(100*sum(finite(x) for x in confirms)/len(confirms),1)
    bottom=[100 if higher_low and not breakdown else 0,
            100 if volatility_contracting else 0,
            flow_score,100 if out['Momentum Status']=='Improving' else 0,
            rotation if all(finite(x) for x in relative) else NAN,fundamental,revisions]
    out['Bottom Confidence']=round(evidence_mean(bottom),1)
    out['Bottom Confidence Coverage %']=round(100*sum(finite(x) for x in bottom)/len(bottom),1)
    bc=out['Bottom Confidence']
    research=[rotation if all(finite(x) for x in relative) else NAN,fundamental,revisions,valuation,
              context.get('Institutional/Insider Score',NAN),environment]
    out['Research Coverage %']=round(100*sum(finite(x) for x in research)/len(research),1)
    status=('Insufficient evidence' if out['Research Coverage %']<50 else
            'Strong bottom evidence' if bc>=80 else 'Bottom developing / favorable' if bc>=65 else
            'Stabilization; confirmation needed' if bc>=50 else 'Weak/unconfirmed bounce' if bc>=35 else 'Falling-knife / breakdown risk')
    out['Bottom/Falling-Knife Status']=status if out['Drawdown From High %']<=-15 or breakdown else 'Not a bottom setup'
    if breakdown: action='Falling Knife' if bc<35 else 'Breakdown Warning'
    elif position and out['Resistance Proximity']=='Strong Proximity' and out['RSI(14)']>68: action='Trim Watch'
    elif position and out['Money Flow'] in ['Leaving','Distributing']: action='Raise Protection'
    elif coverage<75: action='Hold/Wait'
    elif confirmed and out['Setup Confidence']>=65: action='Confirmed Breakout'
    elif support_holds and finite(rr) and rr>=2 and out['Opportunity Score']>=70 and out['Setup Confidence']>=65 and bc>=50:
        action='Strong Buy Zone' if out['Opportunity Score']>=80 else 'Buy/Accumulate'
    elif out['Support Proximity'] in ['Near','Approaching']: action='Approaching Buy Zone'
    elif out['Resistance Proximity'] in ['Near','Approaching']: action='Hold for Breakout'
    else: action='Hold/Wait'
    out['Overall Signal/Action']=action
    if action in ['Trim Watch','Raise Protection']:
        out['Action Reason']=f"Owned-position risk management: {action}; resistance {out['Resistance Proximity']}; flow {out['Money Flow']}"
    elif coverage<75 and not breakdown:
        out['Action Reason']='Missing evidence limits buy action; coverage '+str(out['Evidence Coverage %'])+'%'
    else:
        out['Action Reason']=f"{out['Breakdown Status']}; support {out['Support Proximity']}; R/R {round(rr,2) if finite(rr) else 'unavailable'}; confidence {out['Setup Confidence']}"
    out['Owned/Watch']='Owned' if position else 'Ownership/Cost Basis Unavailable'
    qty=position.get('Qty',NAN) if position else NAN;basis=position.get('Cost Basis',NAN) if position else NAN
    out.update({'Qty':qty,'Cost Basis':basis,'Current Value':qty*current if finite(qty) else NAN,
                'Unrealized $':qty*(current-basis) if finite(qty) and finite(basis) else NAN,
                'Unrealized %':100*(current/basis-1) if finite(basis) and basis>0 else NAN})
    out['Technical Location']='; '.join([f"Support: {out['Support Proximity']}",f"Resistance: {out['Resistance Proximity']}",out['Breakout Status'],out['Breakdown Status']])
    return out


def latest_session(now=None):
    import exchange_calendars as xc
    now=pd.Timestamp.now(tz='UTC') if now is None else pd.Timestamp(now)
    if now.tzinfo is None: raise ValueError('Timezone-aware current time required')
    cal=xc.get_calendar('XNYS')
    day=now.tz_convert('America/New_York').normalize().tz_localize(None)
    session=cal.date_to_session(day,direction='previous')
    if cal.session_close(session)>now: session=cal.previous_session(session)
    return session.strftime('%Y-%m-%d')


def history_gap(raw, valid, symbol, session):
    """Bulk mixed-asset downloads contain equity padding on crypto-only days."""
    start=valid.Date.min()
    if symbol.endswith('-USD'):
        dates=pd.date_range(start,pd.Timestamp(session),freq='D')
    else:
        import exchange_calendars as xc
        dates=xc.get_calendar('XNYS').sessions_in_range(start,pd.Timestamp(session))
    return raw[raw.Date.isin(dates)].Close.isna().any()


def structured_failure(feed, universe_count, session, code, detail, audit=None, historical=False):
    feed=Path(feed)
    hashes={}
    for name in ['price_audit.json','prices_latest.csv','price_history.csv.gz']:
        path=feed/name
        if path.exists():
            hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    empty={k:[] for k in ['Master','Scanner','Top Opportunities','At-Approach Support','At-Approach Resistance',
                          'Breakouts','Breakdowns','Owned Positions','Added Names']}
    return {'session':session,'historical':historical,'status':'INCOMPLETE — CURRENT-DATE PRICE FEED UNAVAILABLE',
            'failure':{'code':code,'detail':detail,'requested_session':session,
                       'feed_session':(audit or {}).get('latest_market_date'),
                       'artifact_generated_at':(audit or {}).get('generated_at_utc'),
                       'artifact_ok':(audit or {}).get('ok'),
                       'failed_symbols':', '.join((audit or {}).get('failed_symbols',[]))},
            'source_sha256':hashes,
            'counts':{'Expected':universe_count,'Usable':0,'Data Limited':universe_count,'Triggered':0},
            'views':empty,'calculations':[],'context':[],'positions':[]}


def run(feed,universe,session,context_path=None,positions_path=None,benchmarks_path=None,historical=False):
    feed=Path(feed)
    expected=pd.read_csv(universe).Symbol.fillna('').astype(str).str.strip().str.upper().tolist()
    if not expected or any(not x for x in expected): raise ValueError('Empty universe symbols')
    if len(set(expected))!=len(expected): raise ValueError('Duplicate universe symbols')
    try:
        audit=json.loads((feed/'price_audit.json').read_text(encoding='utf-8'))
        if not isinstance(audit,dict): raise ValueError('Audit must be an object')
    except (OSError,ValueError) as exc:
        return structured_failure(feed,len(expected),session,'INVALID_OR_MISSING_AUDIT',str(exc),historical=historical)
    if audit.get('latest_market_date')!=session:
        return structured_failure(feed,len(expected),session,'FEED_SESSION_MISMATCH',f"feed session {audit.get('latest_market_date')} does not match requested {session}",audit,historical)
    if not historical and session!=latest_session():
        return structured_failure(feed,len(expected),session,'REQUEST_SESSION_NOT_LATEST',f"requested {session}; latest completed session is {latest_session()}",audit,historical)
    try:
        lat=pd.read_csv(feed/'prices_latest.csv')
        history=pd.read_csv(feed/'price_history.csv.gz',parse_dates=['Date'])
    except (OSError,ValueError) as exc:
        return structured_failure(feed,len(expected),session,'INVALID_OR_MISSING_PRICE_FILES',str(exc),audit,historical)
    if not {'Symbol','Current Price','Price Date','Provider','Price Basis','price_status'}.issubset(lat.columns):
        raise ValueError('Latest-price schema invalid')
    if not {'Symbol','Date','Open','High','Low','Close','Volume'}.issubset(history.columns):
        raise ValueError('History schema invalid')
    for frame in [lat,history]:
        frame['Symbol']=frame.Symbol.fillna('').astype(str).str.strip().str.upper()
    for column in ['Open','High','Low','Close','Volume']:
        history[column]=pd.to_numeric(history[column],errors='coerce')
    lat['Current Price']=pd.to_numeric(lat['Current Price'],errors='coerce')
    if lat.Symbol.duplicated().any() or history.duplicated(['Symbol','Date']).any(): raise ValueError('Duplicate source rows')
    if set(lat.Symbol)!=set(expected): raise ValueError('Feed/universe reconciliation failed')
    if audit.get('expected_tickers')!=len(expected): raise ValueError('Audit/universe count mismatch')
    if set(history.Symbol)-set(expected):raise ValueError('Unexpected history symbols')
    context=pd.read_csv(context_path).set_index('Ticker') if context_path else pd.DataFrame()
    positions=pd.read_csv(positions_path).set_index('Ticker') if positions_path else pd.DataFrame()
    benchmarks=pd.read_csv(benchmarks_path,parse_dates=['Date']) if benchmarks_path else pd.DataFrame()
    if not context.empty:
        if context.index.duplicated().any(): raise ValueError('Duplicate context symbols')
        if not {'Source','As Of','Raw Evidence'}.issubset(context.columns): raise ValueError('Context requires source, as-of date and raw evidence')
        for column in ['Source','As Of','Raw Evidence']:
            if context[column].isna().any() or context[column].astype(str).str.strip().eq('').any(): raise ValueError('Context provenance cannot be blank')
        if (pd.to_datetime(context['As Of'])>pd.Timestamp(session)).any(): raise ValueError('Future context is prohibited')
        for col in ['Environment Score','Institutional/Insider Score']:
            if col in context and ((context[col].dropna()<0)|(context[col].dropna()>100)).any():raise ValueError('Context evidence ratings must be 0–100')
        if (pd.Timestamp(session)-pd.to_datetime(context['As Of'])).dt.days.gt(120).any():raise ValueError('Stale context exceeds 120 days')
    if not positions.empty:
        if positions.index.duplicated().any(): raise ValueError('Duplicate ownership symbols; aggregate transactions explicitly')
        if not {'Source','As Of','Confirmed','Qty','Cost Basis'}.issubset(positions.columns): raise ValueError('Ownership provenance required')
        for column in ['Source','As Of']:
            if positions[column].isna().any() or positions[column].astype(str).str.strip().eq('').any(): raise ValueError('Ownership provenance cannot be blank')
        if (pd.to_datetime(positions['As Of'])>pd.Timestamp(session)).any(): raise ValueError('Future ownership prohibited')
    if not benchmarks.empty:
        required_benchmark={'Date','Symbol','Close','Source','Price Basis'}
        if not required_benchmark.issubset(benchmarks.columns): raise ValueError('Benchmarks require Date, Symbol, Close, Source and Price Basis')
        if benchmarks.duplicated(['Symbol','Date']).any(): raise ValueError('Duplicate benchmarks')
        if benchmarks['Source'].isna().any() or benchmarks['Source'].astype(str).str.strip().eq('').any(): raise ValueError('Benchmark source required')
        if not benchmarks['Price Basis'].astype(str).str.lower().str.startswith('adjusted').all(): raise ValueError('Benchmark price basis must be adjusted')
        if benchmarks['Close'].isna().any() or (~np.isfinite(pd.to_numeric(benchmarks['Close'],errors='coerce'))).any() or (pd.to_numeric(benchmarks['Close'],errors='coerce')<=0).any(): raise ValueError('Benchmark closes must be positive finite values')
        if (benchmarks['Date']>pd.Timestamp(session)).any(): raise ValueError('Future benchmark data prohibited')
        ordered=benchmarks.sort_values(['Symbol','Date']).reset_index(drop=True)
        if not benchmarks.reset_index(drop=True)[['Symbol','Date']].equals(ordered[['Symbol','Date']]): raise ValueError('Benchmarks must be ordered by Symbol, Date')
    rows=[]
    for sym in expected:
        lr=lat[lat.Symbol==sym].iloc[0]
        raw_history=history[history.Symbol==sym].sort_values('Date')
        g=raw_history.dropna(subset=['Close'])
        row={'Ticker':sym,'Price':lr['Current Price'],'Price Date':lr['Price Date'],
             'Price Provider':lr['Provider'],'Price Basis':lr['Price Basis'],'price_status':lr['price_status'],
             'Provider Symbol':lr.get('Provider Symbol',sym),
             'Universe':'Added' if sym in ADDED_SYMBOLS else 'Core'}
        pos=positions.loc[sym].to_dict() if sym in positions.index and str(positions.loc[sym,'Confirmed']).lower()=='true' else None
        if pos and (not finite(pos['Qty']) or float(pos['Qty'])<=0 or not finite(pos['Cost Basis']) or float(pos['Cost Basis'])<=0): raise ValueError('Invalid confirmed ownership')
        if row['price_status']=='OK':
            required=['Close','Open','High','Low']
            if not historical and sym.endswith('-USD') and pd.Timestamp.now(tz='UTC')<pd.Timestamp(session,tz='UTC')+pd.Timedelta(days=1):
                row['price_status']='UNCOMPLETED_CRYPTO_CANDLE'
            elif g.empty or g.Date.max()!=pd.Timestamp(session) or str(row['Price Date'])!=session:
                row['price_status']='STALE_OR_MISSING_HISTORY'
            elif history_gap(raw_history,g,sym,session):
                row['price_status']='INCOMPLETE_HISTORY'
            elif not finite(row['Price']) or row['Price']<=0 or g.Date.isna().any() or not np.isfinite(g[required].to_numpy()).all() or (g[required]<=0).any().any():
                row['price_status']='INVALID_HISTORY'
            elif not str(row['Price Basis']).lower().startswith('adjusted'):
                row['price_status']='UNVERIFIED_PRICE_BASIS'
            else:
                tol=1e-10*g[['High','Low','Close']].abs().max(axis=1).clip(lower=1)
                if ((g.High+tol<g.Low)|(g.High+tol<g.Close)|(g.Low-tol>g.Close)|(g.High+tol<g.Open)|(g.Low-tol>g.Open)).any():
                    row['price_status']='INVALID_HISTORY'
                elif round(float(g.Close.iloc[-1]),4)!=round(float(row['Price']),4):
                    row['price_status']='PRICE_HISTORY_MISMATCH'
                elif len(g)<30:
                    row['price_status']='INSUFFICIENT_HISTORY'
        if row['price_status']=='OK':
            ctx=context.loc[sym].to_dict() if sym in context.index else {}
            if pos and (not finite(pos['Qty']) or pos['Qty']<=0 or not finite(pos['Cost Basis']) or pos['Cost Basis']<=0): raise ValueError('Invalid confirmed ownership')
            def bm(symbol):
                if benchmarks.empty:return None
                b=benchmarks[(benchmarks.Symbol==symbol)&(benchmarks.Date<=pd.Timestamp(session))]
                if b.empty or b.Date.max()!=pd.Timestamp(session):return None
                return b.set_index('Date').Close
            row.update(calculate(g,row['Price'],session,bm('SPY'),bm(ctx.get('Sector Benchmark','')),ctx,pos))
            row['Context Source']=ctx.get('Source','Unavailable');row['Context As Of']=ctx.get('As Of',None)
            row['Context Raw Evidence']=ctx.get('Raw Evidence','Unavailable')
            row['Ownership Source']=pos.get('Source') if pos else 'Unavailable'
        else:
            row.update({'Overall Signal/Action':'Data Unavailable','Action Reason':row['price_status'],
                        'Owned/Watch':'Owned' if pos else 'Ownership/Cost Basis Unavailable',
                        'Qty':pos['Qty'] if pos else None,'Cost Basis':pos['Cost Basis'] if pos else None,
                        'Ownership Source':pos['Source'] if pos else 'Unavailable'})
        rows.append(row)
    df=pd.DataFrame(rows)
    # Even an all-failed run must export its audit and empty action views.
    for name in ['Opportunity Score','Setup Confidence','Support Proximity','Resistance Proximity',
                 'Breakout Status','Breakdown Status','Owned/Watch','Reversal Status','Rotation Score','Money Flow','Market Cap','1W %','2W %','1M %']:
        if name not in df:df[name]=None
    ok=df.price_status.eq('OK')
    df['Largest Recent Drop %']=df[['1W %','2W %','1M %']].apply(pd.to_numeric,errors='coerce').min(axis=1)
    df.loc[ok,'Overall Rank']=df.loc[ok,'Opportunity Score'].rank(method='min',ascending=False)
    usable=df[ok]
    near=['Strong Proximity','Near','Approaching']
    views={'Master':df,'Scanner':usable[(usable['Support Proximity'].isin(near))|(usable['Resistance Proximity'].isin(near))|usable['Breakout Status'].ne('None')|usable['Breakdown Status'].ne('None')],
           'Top Opportunities':usable.sort_values(['Opportunity Score','Setup Confidence','Ticker'],ascending=[False,False,True]).head(25),
           'At-Approach Support':usable[usable['Support Proximity'].isin(near)&usable['Breakdown Status'].eq('None')],
           'At-Approach Resistance':usable[usable['Resistance Proximity'].isin(near)&usable['Breakout Status'].eq('None')],
           'Breakouts':usable[usable['Breakout Status'].ne('None')],'Breakdowns':usable[usable['Breakdown Status'].ne('None')],
           'Owned Positions':df[df['Owned/Watch'].eq('Owned')],'Added Names':df[df.Universe.eq('Added')]}
    # Add required research views without dropping or redefining existing tabs.
    views.update({
        'Buy-Accumulate':usable[usable['Overall Signal/Action'].isin(['Strong Buy Zone','Buy/Accumulate'])],
        'Drop-Reversal':usable[usable['Reversal Status'].eq('Reversal Developing') & pd.to_numeric(usable.get('Drawdown From High %',pd.Series(index=usable.index,dtype=float)),errors='coerce').le(-15)],
        'Strongest Rotation':usable[pd.to_numeric(usable['Rotation Score'],errors='coerce').ge(5.5)].sort_values('Rotation Score',ascending=False),
        'Strongest Money Flow':usable[usable['Money Flow'].isin(['Entering','Accumulating'])],
        'Money Flow Warnings':usable[usable['Money Flow'].isin(['Leaving','Distributing'])],
        'Largest Recent Drops':usable[usable['Largest Recent Drop %'].lt(0)].sort_values('Largest Recent Drop %').head(25),
        'Large-Cap Opportunities':usable[pd.to_numeric(usable['Market Cap'],errors='coerce').ge(10_000_000_000)].sort_values(['Opportunity Score','Setup Confidence','Ticker'],ascending=[False,False,True]).head(25),
    })
    def clean(frame):return json.loads(frame.to_json(orient='records'))
    return {'session':session,'historical':historical,'status':'INCOMPLETE — NO USABLE PRICES' if not ok.any() else 'HISTORICAL REBUILD' if historical else 'CURRENT — DATA LIMITED' if (~ok).any() or context.empty or benchmarks.empty else 'CURRENT',
            'source_sha256':{f:hashlib.sha256((feed/f).read_bytes()).hexdigest() for f in ['price_audit.json','prices_latest.csv','price_history.csv.gz']},
            'research_status':'PRICE-ONLY RESEARCH — CONTEXT/BENCHMARKS UNAVAILABLE' if context.empty or benchmarks.empty else 'SUPPLIED RESEARCH — COVERAGE VARIES BY TICKER',
            'code_sha256':{f:hashlib.sha256((Path(__file__).parent/f).read_bytes()).hexdigest() for f in ['buy_sell_monitor.py','export_monitor.py']},
            'input_sha256':{name:hashlib.sha256(Path(path).read_bytes()).hexdigest() for name,path in [('universe',universe),('context',context_path),('positions',positions_path),('benchmarks',benchmarks_path)] if path},
            'counts':{'Expected':len(expected),'Usable':int(ok.sum()),'Data Limited':int((~ok).sum()),'Triggered':len(views['Scanner']),
                      'Core Expected':len(set(expected)-ADDED_SYMBOLS),'Core Found':int((ok & df.Universe.eq('Core')).sum()),
                      'Core Missing':int((~ok & df.Universe.eq('Core')).sum()),
                      'Added Expected':len(set(expected)&ADDED_SYMBOLS),'Added Found':int((ok & df.Universe.eq('Added')).sum()),
                      'Added Missing':int((~ok & df.Universe.eq('Added')).sum()),'Coverage %':round(100*ok.sum()/len(expected),2)},
            'views':{k:clean(v if k in ['Largest Recent Drops','Strongest Rotation'] else v.sort_values(['Overall Rank','Ticker'],na_position='last') if 'Overall Rank' in v else v) for k,v in views.items()},
            'calculations':clean(df),'context':clean(context.reset_index()) if not context.empty else [],
            'positions':clean(positions.reset_index()) if not positions.empty else []}


def main():
    p=argparse.ArgumentParser();p.add_argument('--feed',required=True);p.add_argument('--universe',required=True)
    p.add_argument('--session');p.add_argument('--historical',action='store_true')
    for flag in ['context','positions','benchmarks']:p.add_argument('--'+flag)
    p.add_argument('--output',required=True);a=p.parse_args()
    result=run(a.feed,a.universe,a.session or latest_session(),a.context,a.positions,a.benchmarks,a.historical)
    Path(a.output).parent.mkdir(parents=True,exist_ok=True)
    Path(a.output).write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps(result['counts']))


if __name__=='__main__':main()
