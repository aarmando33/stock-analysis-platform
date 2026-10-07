"""Historical pivot zones and technical basing. No provider or file I/O.

Zone tests are retrospective until final boundaries were knowable. Only subsequent
distinct defended episodes count toward current strength. MAs are separate.
"""
import math
import numpy as np
import pandas as pd
NA='Unavailable'
TIERS=[('Short',63,2,30),('Next',126,5,63),('Major',252,10,252),('Deep',None,21,504)]

def atr_series(g):
    prev=g.Close.shift()
    tr=pd.concat([g.High-g.Low,(g.High-prev).abs(),(g.Low-prev).abs()],axis=1).max(axis=1)
    return tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean().to_numpy()

def candidates(g):
    n=len(g); result={'Support':[],'Resistance':[]}
    for side,col in [('Support','Low'),('Resistance','High')]:
        vals=g[col].to_numpy()
        for i in range(2,n-2):
            win=vals[i-2:i+3]
            if vals[i]!=(min(win) if side=='Support' else max(win)) or sum(win==vals[i])!=1:continue
            scale=2
            for width in [5,10,21]:
                if i<width or i+width>=n:break
                win=vals[i-width:i+width+1]
                if vals[i]!=(min(win) if side=='Support' else max(win)) or sum(win==vals[i])!=1:break
                scale=width
            result[side].append({'i':i,'date':g.Date.iloc[i],'price':float(vals[i]),'scale':scale,
                                 'confirmed':g.Date.iloc[i+2]})
    return result

def evaluate(g,side,members,atr,confirmed_index):
    """Retrospective evidence against the displayed band; not a historical trade backtest."""
    n=len(g);lo=min(x['price'] for x in members);hi=max(x['price'] for x in members)
    earliest=min(x['i'] for x in members);start=confirmed_index+1
    boundary_known=max(confirmed_index,max(min(x['i']+2 for x in members if x['price']==edge) for edge in [lo,hi]))
    support=side=='Support';ev=[];armed=True;touch=None;last_end=-100;broken=False;last_break=None;reclaims=[]
    closes=g.Close.to_numpy();lows=g.Low.to_numpy();highs=g.High.to_numpy()
    for i in range(start,n):
        a=atr[i-1] if i and np.isfinite(atr[i-1]) else None
        if a is None:continue
        buffer=.25*a
        breached=closes[i]<lo-buffer if support else closes[i]>hi+buffer
        priorbreach=(closes[i-1]<lo-.25*atr[i-2] if support else closes[i-1]>hi+.25*atr[i-2]) if i>1 and np.isfinite(atr[i-2]) else False
        if breached and priorbreach and not broken:
            ev.append({'type':'Break','date':g.Date.iloc[i],'close':float(closes[i]),'buffer':float(buffer)})
            broken=True;last_break=i;touch=None;armed=False;last_end=i
        reclaimed=closes[i]>hi+buffer if support else closes[i]<lo-buffer
        if broken and reclaimed:
            ev.append({'type':'Reclaim','date':g.Date.iloc[i],'close':float(closes[i]),'buffer':float(buffer)})
            broken=False;reclaims.append(i);armed=False;last_end=i
        if broken:continue
        departed=closes[i]>hi+a if support else closes[i]<lo-a
        if not armed and touch is None:
            if i-last_end>=3 and departed:armed=True
            continue
        overlap=lows[i]<=hi and highs[i]>=lo
        if touch is None and armed and overlap:
            touch={'i':i,'date':g.Date.iloc[i],'price':float(lows[i] if support else highs[i]),'atr':float(a),
                   'retest':bool(reclaims and i>reclaims[-1])}
            armed=False
        if touch is not None:
            adverse=closes[i]<lo-.25*touch['atr'] if support else closes[i]>hi+.25*touch['atr']
            target=closes[i]>=hi+touch['atr'] if support else closes[i]<=lo-touch['atr']
            if adverse:
                ev.append({**touch,'type':'Failed touch','resolved':g.Date.iloc[i],'close':float(closes[i])});touch=None;last_end=i
            elif target and i>touch['i']:
                ev.append({**touch,'type':'Defended retest' if touch['retest'] else 'Defended test',
                           'resolved':g.Date.iloc[i],'close':float(closes[i]),
                           'reaction_pct':float(100*(closes[i]/touch['price']-1)*(1 if support else -1))})
                touch=None;last_end=i
            elif i-touch['i']>=10:
                ev.append({**touch,'type':'Unconfirmed touch','resolved':g.Date.iloc[i]});touch=None;last_end=i
    if touch:ev.append({**touch,'type':'Pending touch','resolved':g.Date.iloc[-1]})
    defended=[e for e in ev if e['type'].startswith('Defended')]
    since=[e for e in defended if e['i']>boundary_known and (last_break is None or e['i']>last_break)]
    failed=[e for e in ev if e['type']=='Failed touch'];breaks=[e for e in ev if e['type']=='Break']
    undercuts=[g.Date.iloc[i] for i in range(start,n) if (closes[i]<lo if support else closes[i]>hi)]
    lastdef=max((e['i'] for e in since),default=-10000)
    state='Broken' if broken else 'Defended recently' if lastdef>=n-21 else 'Reclaimed; retest unconfirmed' if reclaims and lastdef<reclaims[-1] else 'Historical; no recent defense'
    return {'low':lo,'high':hi,'origin':g.Date.iloc[earliest],'known_2bar':g.Date.iloc[earliest+2],
            'band_known_date':g.Date.iloc[boundary_known],
            'members':members,'events':ev,'tests':len(defended),'tests_since_break':len(since),
            'failed':len(failed),'breaks':len(breaks),'last_break':g.Date.iloc[last_break] if last_break is not None else None,
            'last_defense':defended[-1]['resolved'] if defended else None,'state':state,
            'outside_closes':len(undercuts),'recent_defense':lastdef>=n-21,'last_member':max(x['i'] for x in members)}

def zones_for(g,mult=1.0):
    n=len(g);atr=atr_series(g);p=float(g.Close.iloc[-1]);cand=candidates(g)
    ratio=float(np.nanmedian(atr[-63:]/g.Close.to_numpy()[-63:])) if np.isfinite(atr).any() else None
    tolerance=min(.02,max(.005,.5*ratio))*mult if ratio is not None else None
    allzones=[];selected={};extra=[]
    for side in ['Support','Resistance']:
        boundary=p
        for tier,look,width,minhist in TIERS:
            key=side+' '+tier;selected[key]=None
            if n<minhist or tolerance is None:continue
            subset=[x for x in cand[side] if x['i']>=n-(look or n)]
            groups=[]
            for x in sorted(subset,key=lambda x:x['price']):
                if groups and x['price']/groups[-1][0]['price']-1<=tolerance:groups[-1].append(x)
                else:groups.append([x])
            eligible=[]
            for group in groups:
                anchors=[x for x in group if x['scale']>=width]
                if not anchors:continue
                z=evaluate(g,side,group,atr,min(x['i']+width for x in anchors))
                z.update({'tier':tier,'side':side,'window':look or n,'pivot_width':width,
                          'confirmed_for_tier':min(g.Date.iloc[x['i']+width] for x in anchors),'tolerance_pct':tolerance*100})
                allzones.append(z)
                # Historical lows/highs retain their role; no untested role reversal.
                onside=z['high']<boundary if side=='Support' else z['low']>boundary
                if onside and z['state']!='Broken':eligible.append(z)
            if eligible:
                z=max(eligible,key=lambda z:z['high']) if side=='Support' else min(eligible,key=lambda z:z['low'])
                selected[key]=z;boundary=z['low'] if side=='Support' else z['high']
                if tier=='Deep':
                    more=[x for x in eligible if (x['high']<z['low'] if side=='Support' else x['low']>z['high'])]
                    extra.extend(sorted(more,key=lambda x:x['high'],reverse=side=='Support')[:2])
    return selected,allzones,extra,atr,tolerance

def flat_test(g,low,high,atr):
    c=g.Close.iloc[-10:]
    inside=int(((c>=low-.5*atr)&(c<=high+.5*atr)).sum())
    span=float(c.max()-c.min()); drift=abs(float(c.iloc[-1]-c.iloc[0]))
    bad=c<low-.25*atr
    broken=bool((bad & bad.shift(1,fill_value=False)).any())
    touch=bool(((g.Low.iloc[-10:]<=high)&(g.High.iloc[-10:]>=low)).any())
    ok=len(c)==10 and inside>=8 and span<=2*atr and span/c.iloc[-1]<=.08 and drift<=atr and not broken and touch
    return dict(ok=bool(ok),inside=inside,span=span,drift=drift,broken=broken,touch=touch,
                low=float(c.min()),high=float(c.max()),range_pct=100*span/float(c.iloc[-1]))

def base_state(g,r):
    atr=r['old'].get('ATR'); price=float(g.Close.iloc[-1]); drawdown=r['old'].get('Drawdown From High %')
    if len(g)<30 or not isinstance(atr,(float,int)) or not math.isfinite(atr) or atr<=0:
        return dict(status=NA,bottom=NA,reference=NA,low=None,high=None,days=0,range_pct=None,bottom_low=None,bottom_high=None,reason='Need 30 observations and valid ATR')
    supports=[z for z in r['selected'].values() if z and z['side']=='Support']+ [z for z in r['extra_deep'] if z['side']=='Support']
    near=sorted(supports,key=lambda z:max(z['low']-price,price-z['high'],0))
    z=near[0] if near else None
    ref=(f"Historical support {z['low']:.6f}â€“{z['high']:.6f}" if z else NA)
    f=flat_test(g,z['low'],z['high'],atr) if z else None
    distance=max(z['low']-price,price-z['high'],0) if z else float('inf')
    status='No base near support'
    if z and distance<=atr: status='Near support; base unconfirmed'
    if f and f['ok']: status='Basing near support (unconfirmed)'
    # Bottom boundaries are observed, confirmed pivot lows, never arbitrary ATR prices.
    piv=[]
    for i in range(max(2,len(g)-21),len(g)-2):
        v=float(g.Low.iloc[i]); neighbors=pd.concat([g.Low.iloc[i-2:i],g.Low.iloc[i+1:i+3]])
        if bool((neighbors>v).all()): piv.append((v,str(g.Date.iloc[i])))
    material=isinstance(drawdown,(int,float)) and drawdown<=-15
    blo=bhi=None; bottom='No bottom setup'; bottom_dates=[]
    if material and piv:
        floor=min(v for v,_ in piv)
        members=[(v,d) for v,d in piv if v/floor-1<=r['tolerance_pct']/100]
        blo=min(v for v,_ in members); bhi=max(v for v,_ in members); bottom_dates=[d for _,d in members]
        bf=flat_test(g,blo,bhi,atr)
        bottom='Potential bottom zone; base unconfirmed'
        if bf['ok']:
            bottom='Bottom-forming candidate (unconfirmed)'
            if not(f and f['ok']):
                status='Basing near potential bottom (unconfirmed)'; f=bf;ref=f"Potential bottom {blo:.6f}â€“{bhi:.6f}"
        elif bf['broken']:
            bottom='Bottom zone broken'
    elif material: bottom='No confirmed bottom zone'
    if r['recent_zone_break'] or (r['lower_structure'] and r['old'].get('1M %',0)<-8):
        bottom='Breakdown / falling-knife risk'
        if 'Basing near' not in status: status='No confirmed base; breakdown risk'
    if not f: f=flat_test(g,price,price,atr)
    reason=f"10 observations; {f['inside']}/10 closes in reference Â±0.5 ATR; range {f['span']:.6f} vs 2 ATR {2*atr:.6f}; drift {f['drift']:.6f} vs ATR {atr:.6f}; touch={f['touch']}; consecutive break={f['broken']}"
    return dict(status=status,bottom=bottom,reference=ref,low=f['low'],high=f['high'],days=10,range_pct=f['range_pct'],bottom_low=blo,bottom_high=bhi,bottom_dates=bottom_dates,reason=reason)
