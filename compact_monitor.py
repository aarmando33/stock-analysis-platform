"""Concise reader views; technical estimates remain on Calculations."""
import math

BASE = ['Ticker', 'Universe', 'Owned/Watch', 'Qty', 'Cost Basis', 'Price', 'Price Date', 'Price Provider', 'Price Basis', 'price_status', 'Primary Win%', '52W Closing-Range Win%', '1W %', '1M %', '3M %', '6M %', 'YTD %', 'RSI(14)', '20D MA', '50D MA', '100D MA', '200D MA', 'MACD', 'ATR', 'Drawdown From High %', 'Rebound From Recent Low %', 'Basing Status', 'Short Support', 'Major Support', 'Distance to Support %', 'Short Resistance', 'Major Resistance', 'Distance to Resistance %', 'Rotation Score', 'Rotation Stage', 'Money Flow', 'Opportunity Score', 'Setup Confidence', 'Technical Location', 'Overall Signal/Action', 'Unrealized %', 'Technical Bottom Score', 'Bottom Confidence', 'Bottom Confidence Coverage %', 'Bottom/Falling-Knife Status', 'Short Support Tests', 'Short Resistance Tests']
ORDER = ['Master','Scanner','Top Opportunities','At-Approach Support','At-Approach Resistance',
         'Breakouts','Breakdowns','Owned Positions','Added Names']

def numeric(value):
    try:return math.isfinite(float(value))
    except (ValueError,TypeError):return False

def level_candidate(row, side):
    """Price proximity is a screen, not evidence of a successful trade."""
    label='Short '+side
    distance=row.get('Distance to '+side+' %')
    level=row.get(label); price=row.get('Price'); tests=row.get(label+' Tests')
    if not all(numeric(v) for v in [distance,level,price,tests]):return False
    if row.get('price_status')!='OK' or not 0<=distance<=3 or tests<2:return False
    pivot_kind='swing low' if side=='Support' else 'swing high'
    if pivot_kind not in str(row.get(label+' Source','')):return False
    if row.get(label+' Date')==row.get('Price Date'):return False
    return level<price if side=='Support' else level>price

def prepare(report):
    views=report.get('views',{})
    calc=report.get('calculations',[])
    result=[]
    for name in ORDER:
        headers=list(BASE); rows=list(views.get(name,[]))
        if name in ['Top Opportunities','Scanner']:rows=rows[:10 if name=='Top Opportunities' else 15]
        if name=='Scanner':
            rows=[r for r in calc if r.get('price_status')=='OK' and numeric(r.get('Drawdown From High %')) and r['Drawdown From High %']<=-15]
            rows.sort(key=lambda r:(-float(r.get('Technical Bottom Score') or 0),r['Ticker']))
            rows=rows[:15]
            headers=['Ticker','Price','Drawdown From High %','Rebound From Recent Low %','Higher Low Observed',
                     'ATR Contraction Ratio','Volume Contraction Ratio','Money Flow','Momentum Status',
                     'Technical Bottom Score','Bottom Confidence Coverage %','Bottom/Falling-Knife Status','Basing Status']
        if name.startswith('At-Approach '):
            side=name.removeprefix('At-Approach ')
            rows=[r for r in calc if level_candidate(r,side)
                  and r.get('Breakdown Status' if side=='Support' else 'Breakout Status')=='None']
            rows.sort(key=lambda r:(float(r['Distance to '+side+' %']),-float(r['Short '+side+' Tests']),r['Ticker']))
            rows=rows[:10]
            # Full cluster evidence stays on Calculations; show only the swing
            # source relevant to this screen, without MA/range-edge clutter.
            kind='swing low' if side=='Support' else 'swing high'
            rows=[{**r,'Short '+side+' Source':'; '.join(s.replace('-session','D') for s in str(r['Short '+side+' Source']).split('; ') if kind in s)} for r in rows]
            headers=['Ticker','Price','Short '+side,'Distance to '+side+' %',
                     'Short '+side+' Tests','Short '+side+' Source','RSI(14)','Money Flow','Overall Signal/Action']
        if name=='Breakouts':headers=['Ticker','Price','Breakout Level','Breakout Status','Relative Volume','1W %','1M %','Money Flow','Overall Signal/Action']
        if name=='Breakdowns':headers=['Ticker','Price','Breakdown Level','1W %','1M %','Money Flow','Overall Signal/Action']
        if name=='Owned Positions':headers=['Ticker','Qty','Cost Basis','Price','Current Value','Unrealized %','Overall Signal/Action']
        # Preserve the October 2 reader columns on every reader tab.
        headers=list(BASE)
        result.append((name,rows,headers))
    return result

LABELS={'Primary Win%':'Historical Range Position %','52W Closing-Range Win%':'52W Range Position %',
        'Opportunity Score':'Provisional Score','Overall Signal/Action':'Action',
        'Short Support':'Candidate Support','Short Resistance':'Candidate Resistance',
        'Short Support Tests':'Touch Episodes','Short Resistance Tests':'Touch Episodes',
        'Short Support Source':'Level Source','Short Resistance Source':'Level Source',
        'Technical Bottom Score':'Technical Bottom Score','Bottom Confidence Coverage %':'Full Bottom Input Coverage %',
        'Bottom/Falling-Knife Status':'Bottom Status'}
