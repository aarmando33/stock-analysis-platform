"""Build a self-contained, offline ticker review dashboard."""

from __future__ import annotations

import json
import math
import argparse
from pathlib import Path
from typing import Any


_MAX_CHART_POINTS = 10000


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): _safe_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_value(v) for v in value]
    # Accept common scalar wrappers without importing a numerical package.
    scalar = getattr(value, "item", None)
    if callable(scalar):
        try:
            return _safe_value(scalar())
        except (TypeError, ValueError):
            pass
    return str(value)


def _date(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value[:10] if len(value) >= 10 else None


def _history_rows(rows: Any, cutoff: str) -> list[list[Any]]:
    clean: list[list[Any]] = []
    if not isinstance(rows, list):
        return clean
    for row in rows:
        if not isinstance(row, dict):
            continue
        date = _date(row.get("date"))
        close = _number(row.get("close"))
        if not date or date > cutoff or close is None:
            continue
        clean.append([
            date,
            _number(row.get("open")),
            _number(row.get("high")),
            _number(row.get("low")),
            close,
        ])
    clean.sort(key=lambda item: item[0])
    if len(clean) <= _MAX_CHART_POINTS:
        return clean

    # Keep the full-period high and low inside each chart bucket while reducing
    # the embedded data size for a dashboard covering the whole universe.
    stride = math.ceil(len(clean) / _MAX_CHART_POINTS)
    sampled: list[list[Any]] = []
    for start in range(0, len(clean), stride):
        bucket = clean[start : start + stride]
        sampled.append([
            bucket[-1][0],
            bucket[0][1],
            max((r[2] for r in bucket if r[2] is not None), default=None),
            min((r[3] for r in bucket if r[3] is not None), default=None),
            bucket[-1][4],
        ])
    return sampled


def _zones(rows: Any, cutoff: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if not isinstance(rows, list):
        return result
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        side = str(row.get("side") or "").strip().title()
        low, high = _number(row.get("low")), _number(row.get("high"))
        if side not in {"Support", "Resistance"} or low is None or high is None:
            continue
        if low > high:
            low, high = high, low
        dates = row.get("dates") if isinstance(row.get("dates"), list) else []
        dates = sorted({d for d in (_date(x) for x in dates) if d and d <= cutoff})
        test_dates = row.get("test_dates") if isinstance(row.get("test_dates"), list) else []
        test_dates = sorted({d for d in (_date(x) for x in test_dates) if d and d <= cutoff})
        result.append({
            "id": str(row.get("id") or f"{side.lower()}-{i + 1}"),
            "side": side,
            "tier": str(row.get("tier") or "Unspecified"),
            "low": low,
            "high": high,
            "status": str(row.get("status") or "Unavailable"),
            "dates": dates,
            "tests": _number(row.get("tests")),
            "test_dates": test_dates,
            "window": str(row.get("window") or "Unavailable"),
        })
    return result


def _prepare(data: dict[str, Any]) -> dict[str, Any]:
    cutoff = _date(data.get("cutoff")) or "Unknown"
    tickers: list[dict[str, Any]] = []
    for raw in data.get("tickers", []):
        if not isinstance(raw, dict):
            continue
        ticker = str(raw.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        indicators = raw.get("indicators")
        if not isinstance(indicators, dict):
            indicators = {}
        tickers.append({
            "ticker": ticker,
            "name": str(raw.get("name") or ticker),
            "market_cap": _number(raw.get("market_cap")),
            "sector": str(raw.get("sector") or "Unavailable"),
            "subsector": str(raw.get("subsector") or "Unavailable"),
            "profile_retrieved": str(raw.get("profile_retrieved") or "Unavailable"),
            "action": str(raw.get("action") or "Unavailable"),
            "action_reason": str(raw.get("action_reason") or "Unavailable"),
            "price": _number(raw.get("price")),
            "win": _number(raw.get("win")),
            "win52": _number(raw.get("win52")),
            "win6": _number(raw.get("win6")),
            "price80": _number(raw.get("price80")),
            "basing": str(raw.get("basing") or "Unavailable"),
            "bottom": str(raw.get("bottom") or "Unavailable"),
            "base_low": _number(raw.get("base_low")),
            "base_high": _number(raw.get("base_high")),
            "base_days": _number(raw.get("base_days")),
            "flat_range_pct": _number(raw.get("flat_range_pct")),
            "research_coverage": _number(raw.get("research_coverage")),
            "zones": _zones(raw.get("zones"), cutoff),
            "history": _history_rows(raw.get("history"), cutoff),
            "indicators": _safe_value(indicators),
            "volume": _safe_value(raw.get("volume") or {}),
        })
    tickers.sort(key=lambda item: item["ticker"])
    if not tickers:
        raise ValueError("data['tickers'] must contain at least one ticker")
    return {"cutoff": cutoff, "tickers": tickers, "downloaded_at": str(data.get("downloaded_at") or "Archived snapshot")}


def _json_for_script(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    # JSON is placed in a script element. Escaping these characters prevents
    # source strings such as '</script>' from ending that element.
    return (
        text.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ticker Review</title>
<style>
:root{color-scheme:light;--ink:#172b3a;--muted:#5e7180;--line:#dbe4e9;--paper:#f5f8fa;--card:#fff;--blue:#176b8b;--support:#16846f;--resist:#c14c48;--gold:#956315;--shadow:0 5px 20px #18394c0d}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}header{background:#12344a;color:#fff;padding:24px max(20px,calc((100vw - 1280px)/2));}header h1{margin:0 0 4px;font-size:clamp(1.45rem,3vw,2rem)}header p{margin:0;color:#d5e6ee}.snapshot{display:flex;gap:10px;align-items:center;margin-top:16px;padding:11px 14px;background:#fff1d8;color:#68490d;border:1px solid #ebd19d;border-radius:10px;font-weight:650}.snapshot b{white-space:nowrap}.wrap{max-width:1280px;margin:auto;padding:20px}.toolbar,.card,.panel{background:var(--card);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow)}.toolbar{display:flex;flex-wrap:wrap;gap:12px;align-items:end;padding:14px;margin-bottom:16px}.field{display:grid;gap:4px}.field label,.small-label{font-size:.78rem;color:var(--muted);font-weight:650;letter-spacing:.02em}.field input,.field select{min-width:210px;max-width:70vw;padding:9px 11px;border:1px solid #b9c9d2;border-radius:8px;background:white;color:var(--ink);font:inherit}.selected-name{font-size:.9rem;color:var(--muted);margin-left:auto;max-width:380px}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.card{padding:16px}.metric-label{color:var(--muted);font-size:.78rem;font-weight:650}.metric-value{font-size:1.35rem;font-weight:750;margin-top:3px;overflow-wrap:anywhere}.metric-note{color:var(--muted);font-size:.83rem;margin-top:3px}.section{margin-top:18px}.section-head{display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin:0 0 9px}.section h2{font-size:1.12rem;margin:0}.hint{color:var(--muted);font-size:.84rem}.zones-near{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.level-card{border-top:4px solid var(--support)}.level-card.resistance{border-top-color:var(--resist)}.level-title{display:flex;justify-content:space-between;gap:10px}.level-title h3{margin:0;font-size:1rem}.band{font-size:1.6rem;font-weight:780;margin:6px 0}.badge{border-radius:999px;padding:3px 9px;font-size:.75rem;font-weight:700;background:#edf3f6;color:#425766;white-space:nowrap}.status-defended{background:#e3f4ed;color:#17644d}.status-broken{background:#fde9e6;color:#913c36}.status-historical{background:#f3f0e6;color:#69551f}.details-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px;margin-top:10px}.details-grid div{border-top:1px solid var(--line);padding-top:7px}.details-grid strong{display:block}.panel{padding:15px}.chart-head{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px}.chart-controls{display:flex;gap:6px}.chart-controls button{border:1px solid #b8c9d1;background:#fff;color:var(--ink);padding:7px 11px;border-radius:8px;font:inherit;cursor:pointer}.chart-controls button[aria-pressed="true"]{background:#176b8b;color:#fff;border-color:#176b8b}.chart-wrap{overflow:hidden;margin-top:10px}.chart{width:100%;height:auto;min-height:260px;display:block;background:#fbfdfe;border:1px solid #edf1f3;border-radius:9px}.chart-note{font-size:.8rem;color:var(--muted);margin:7px 0 0}.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:.8rem;color:var(--muted)}.legend i{display:inline-block;width:12px;height:9px;margin-right:5px;border-radius:2px}.zone-groups{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.zone-group{border:1px solid var(--line);border-radius:10px;background:#fff}.zone-group summary{cursor:pointer;font-weight:700;padding:11px 13px}.zone-list{display:grid;gap:8px;padding:0 10px 10px}.zone-item{border:1px solid #e4ebef;border-radius:8px;padding:10px}.zone-item-head{display:flex;justify-content:space-between;gap:8px;align-items:center}.zone-item h4{margin:0;font-size:.9rem}.zone-item p{margin:4px 0;color:var(--muted);font-size:.82rem}.evidence-dates{color:#334f5e!important;overflow-wrap:anywhere}.indicators{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px}.indicator{padding:10px;border:1px solid var(--line);border-radius:9px;background:#fff}.indicator .metric-value{font-size:1rem}.empty{color:var(--muted);font-style:italic}.footer{color:var(--muted);font-size:.8rem;margin:18px 2px 4px}svg text{font-family:system-ui,-apple-system,"Segoe UI",sans-serif}.axis{fill:#627886;font-size:11px}.gridline{stroke:#e4ebef;stroke-width:1}.price-line{fill:none;stroke:#176b8b;stroke-width:2}.price-area{fill:#176b8b;opacity:.08}.zone-support{fill:#16846f;stroke:#16846f}.zone-resistance{fill:#c14c48;stroke:#c14c48}
@media(max-width:900px){.grid,.indicators{grid-template-columns:repeat(2,minmax(0,1fr))}.zones-near{grid-template-columns:1fr}}@media(max-width:600px){.wrap{padding:12px}.grid,.indicators,.zone-groups{grid-template-columns:1fr}.selected-name{margin-left:0}.details-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.snapshot{align-items:flex-start;flex-direction:column;gap:2px}.chart{min-height:220px}}
</style>
</head>
<body>
<header>
  <h1>Ticker review</h1>
  <p>Price history, technical context, and dated support/resistance evidence.</p>
  <div class="snapshot"><b>Market close: <span id="cutoff"></span></b><span id="downloadTime"></span><span>Daily snapshot; prices do not stream.</span></div>
</header>
<main class="wrap">
  <section class="toolbar" aria-label="Ticker selection">
    <div class="field"><label for="search">Find a ticker</label><input id="search" type="search" placeholder="Search symbol or company" autocomplete="off"></div>
    <div class="field"><label for="ticker">Ticker</label><select id="ticker"></select></div>
    <div class="selected-name" id="selectedName"></div>
  </section>
  <section class="grid" id="metrics" aria-label="Key metrics"></section>
  <section class="section">
    <div class="section-head"><h2>Nearest historical zones</h2><span class="hint">Bands are candidate price areas, not trade instructions.</span></div>
    <div class="zones-near" id="nearest"></div>
  </section>
  <section class="section panel">
    <div class="chart-head"><div><h2 style="margin:0">Price history and zones</h2><div class="hint">Daily close with high/low range and dated bands</div></div>
      <div class="chart-controls" role="group" aria-label="Chart date range">
        <button type="button" data-range="90" aria-pressed="true">3 mo</button><button type="button" data-range="365" aria-pressed="false">1 yr</button><button type="button" data-range="all" aria-pressed="false">All</button>
      </div>
    </div>
    <div class="legend"><span><i style="background:#16846f"></i>Support</span><span><i style="background:#c14c48"></i>Resistance</span><span><i style="background:#176b8b"></i>Close</span></div>
    <div class="chart-wrap"><svg id="chart" class="chart" viewBox="0 0 1000 420" role="img" aria-label="Historical price chart"></svg></div>
    <p class="chart-note" id="chartNote"></p>
  </section>
  <section class="section">
    <div class="section-head"><h2>In-depth bands and dated evidence</h2><span class="hint">Expand a side to review every available tier.</span></div>
    <div class="zone-groups" id="allZones"></div>
    <div class="section-head" style="margin-top:18px"><h3>Moving-average references</h3><span class="hint">Price relative to each MA; not evidence of a defended historical zone.</span></div>
    <div class="grid" id="maLevels"></div>
  </section>
  <section class="section">
    <div class="section-head"><h2>Other indicators</h2><span class="hint">Unavailable inputs stay unavailable.</span></div>
    <div class="indicators" id="indicators"></div>
  </section>
  <p class="footer">This dashboard preserves the snapshot date shown above. Historical levels and observations can change when the source history or calculation method changes.</p>
</main>
<script id="dashboard-data" type="application/json">__DATA__</script>
<script>
(() => {
  'use strict';
  const data = JSON.parse(document.getElementById('dashboard-data').textContent);
  const tickers = data.tickers;
  const bySymbol = new Map(tickers.map(t => [t.ticker, t]));
  const cutoff = data.cutoff;
  let currentRange = '90';
  const el = id => document.getElementById(id);
  el('cutoff').textContent = cutoff;
  el('downloadTime').textContent = `Downloaded: ${data.downloaded_at}`;
  const fmt = (n, digits=2) => n === null || n === undefined || !Number.isFinite(Number(n)) ? 'Unavailable' : Number(n).toLocaleString(undefined,{maximumFractionDigits:digits,minimumFractionDigits:digits});
  const money = n => n === null || n === undefined ? 'Unavailable' : '$' + fmt(n,2);
  const percent = n => n === null || n === undefined ? 'Unavailable' : fmt(n,1) + '%';
  const dateText = a => Array.isArray(a) && a.length ? a.join(', ') : 'Unavailable';
  const node = (tag, text, cls) => { const x=document.createElement(tag); if(text!==undefined) x.textContent=String(text); if(cls) x.className=cls; return x; };
  const statusClass = s => /broken|break/i.test(s||'') ? 'status-broken' : /defended|reclaim/i.test(s||'') ? 'status-defended' : 'status-historical';
  const setText = (parent, tag, text, cls) => parent.appendChild(node(tag,text,cls));
  function options(filter='') {
    const sel=el('ticker'), prev=sel.value;
    sel.replaceChildren();
    const q=filter.trim().toLowerCase();
    const matches=tickers.filter(t => !q || t.ticker.toLowerCase().includes(q) || t.name.toLowerCase().includes(q));
    matches.forEach(t => {const op=node('option',`${t.ticker} — ${t.name}`);op.value=t.ticker;sel.appendChild(op);});
    const chosen=matches.some(t=>t.ticker===prev)?prev:(matches.some(t=>t.ticker==='GOOG')?'GOOG':matches[0]?.ticker);
    if(chosen) sel.value=chosen;
    if(!matches.length) sel.appendChild(node('option','No matches'));
    render(sel.value && bySymbol.get(sel.value));
  }
  function marketCap(n) {
    if(n===null||n===undefined) return 'Unavailable';
    const x=Number(n); if(!Number.isFinite(x)) return 'Unavailable';
    const unit=Math.abs(x)>=1e12?'T':Math.abs(x)>=1e9?'B':Math.abs(x)>=1e6?'M':'';
    return '$'+fmt(unit?x/(unit==='T'?1e12:unit==='B'?1e9:1e6):x,unit?2:0)+unit;
  }
  function metric(label,value,note='') {
    const box=node('article',undefined,'card');setText(box,'div',label,'metric-label');setText(box,'div',value,'metric-value');if(note)setText(box,'div',note,'metric-note');return box;
  }
  function renderMetrics(t) {
    const box=el('metrics');box.replaceChildren();
    const rows=[
      ['Price',money(t.price),`As of ${cutoff}`],['capMil',t.market_cap===null?'Unavailable':fmt(t.market_cap/1e6,1),`USD millions; profile retrieved ${t.profile_retrieved}`],
      ['Sector',t.sector,'Provider classification'],['Subsector',t.subsector,'Provider industry'],
      ['Win%',percent(t.win),'Historical closing-range position; not a win probability'],['Win52%',percent(t.win52),'52-week closing-range position'],
      ['Win6mo%',percent(t.win6),'Six-month closing-range position; not a return'],['price_suggest_80',money(t.price80),'Price at 80% range position: 20% high + 80% low'],
      ['Action',t.action,t.action_reason],['Basing status',t.basing,'Technical state'],['Bottom status',t.bottom,'Technical state'],
      ['Base range',t.base_low===null||t.base_high===null?'Unavailable':`${money(t.base_low)} – ${money(t.base_high)}`,t.base_days===null?'Duration unavailable':`${fmt(t.base_days,0)} sessions`],
      ['Flat range',percent(t.flat_range_pct),'Historical price range'],['Research coverage',percent(t.research_coverage),'Evidence availability'],
      ['Recent Volume',fmt(t.volume['Recent Volume'],0),'Latest session volume'],
      ['Average Volume 20D',fmt(t.volume['Average Volume 20D'],0),'Prior 20 sessions'],
      ['Relative Volume',fmt(t.volume['Relative Volume'],2),'Latest volume / prior 20-session average'],
      ['20D Net Volume %',percent(t.volume['20D Net Volume %']),'Net signed volume / total volume'],
      ['Volume Confirmation',t.volume['Volume Confirmation']||'Unavailable','Volume intensity'],
      ['OBV',fmt(t.volume['OBV'],0),'Cumulative on-balance volume']
    ];
    rows.forEach(r=>box.appendChild(metric(...r)));
  }
  function bandDistance(zone,price) {
    if(price===null||price===undefined||!Number.isFinite(Number(price))) return Infinity;
    return Math.max(0,zone.low-price,price-zone.high);
  }
  function nearest(t,side,tier=null) {
    const p=t.price;
    const zs=t.zones.filter(z=>z.side===side && (tier===null||z.tier===tier));
    if(!zs.length) return null;
    const fully=zs.filter(z=>side==='Support'?z.high<=p:z.low>=p);
    const pool=fully.length?fully:zs;
    return pool.sort((a,b)=>{
      return bandDistance(a,p)-bandDistance(b,p) || (side==='Support'?b.high-a.high:a.low-b.low);
    })[0];
  }
  function levelCard(z,side,p) {
    if(!z) {const c=node('article',undefined,'card level-card '+(side==='Resistance'?'resistance':''));setText(c,'h3',`Nearest ${side.toLowerCase()}`);setText(c,'p','No eligible historical zone is available.','empty');return c;}
    const c=node('article',undefined,'card level-card '+(side==='Resistance'?'resistance':''));
    const head=node('div',undefined,'level-title');setText(head,'h3',`Nearest ${side.toLowerCase()} · ${z.tier}`);setText(head,'span',z.status,'badge '+statusClass(z.status));c.appendChild(head);
    setText(c,'div',`${money(z.low)} – ${money(z.high)}`,'band');
    const distance=bandDistance(z,p);
    setText(c,'div',`${fmt(100*distance/p,2)}% from price · ${fmt(z.tests,0)} observed tests`,'metric-note');
    const details=node('div',undefined,'details-grid');
    [['Tier window',z.window],['Source dates',dateText(z.dates)],['Test dates',dateText(z.test_dates)]].forEach(([k,v])=>{const d=node('div');setText(d,'span',k,'metric-label');setText(d,'strong',v);details.appendChild(d);});
    c.appendChild(details);return c;
  }
  function renderNearest(t) {
    const root=el('nearest');root.replaceChildren();
    for(const side of ['Support','Resistance']) for(const tier of ['Short','Next']) {
      const z=nearest(t,side,tier);
      const card=levelCard(z,side,t.price);
      card.querySelector('h3').textContent=`${tier==='Short'?'Nearest':'Next'} ${side.toLowerCase()}`;
      root.appendChild(card);
    }
  }
  function renderZones(t) {
    const root=el('allZones');root.replaceChildren();
    for(const side of ['Support','Resistance']) {
      const group=node('details',undefined,'zone-group');
      const sum=node('summary',`${side} bands · ${t.zones.filter(z=>z.side===side).length}`);group.appendChild(sum);
      const list=node('div',undefined,'zone-list');
      const zs=t.zones.filter(z=>z.side===side).sort((a,b)=>{
        const order={Short:0,Next:1,Major:2,Deep:3};return (order[a.tier]??9)-(order[b.tier]??9)||a.low-b.low;
      });
      if(!zs.length) list.appendChild(node('p','No historical bands available.','empty'));
      zs.forEach(z=>{
        const item=node('article',undefined,'zone-item');
        const h=node('div',undefined,'zone-item-head');setText(h,'h4',`${z.tier} · ${money(z.low)} – ${money(z.high)}`);setText(h,'span',z.status,'badge '+statusClass(z.status));item.appendChild(h);
        setText(item,'p',`Window: ${z.window} · Tests: ${fmt(z.tests,0)}`);
        setText(item,'p',`Anchor dates: ${dateText(z.dates)}`,'evidence-dates');
        setText(item,'p',`Test dates: ${dateText(z.test_dates)}`,'evidence-dates');list.appendChild(item);
      });
      group.appendChild(list);root.appendChild(group);
    }
  }
  function renderIndicators(t) {
    const root=el('indicators');root.replaceChildren();
    const entries=Object.entries(t.indicators||{}).filter(([k])=>!/^\d+D MA$/.test(k));
    if(!entries.length){root.appendChild(node('p','No additional indicators provided.','empty'));return;}
    entries.slice(0,24).forEach(([k,v])=>{
      const item=node('div',undefined,'indicator');setText(item,'div',k,'metric-label');
      const value=(v===null||v===undefined||v==='')?'Unavailable':(typeof v==='number'?fmt(v,2):String(v));setText(item,'div',value,'metric-value');root.appendChild(item);
    });
  }
  function renderMA(t) {
    const root=el('maLevels');root.replaceChildren();
    for(const n of [20,50,100,200]) {
      const value=t.indicators[`${n}D MA`];
      const valid=typeof value==='number' && Number.isFinite(value) && value>0;
      const side=!valid?'Unavailable':value<t.price?'MA support reference':value>t.price?'MA resistance reference':'At moving average';
      root.appendChild(metric(`${n}-day MA`,valid?money(value):'Unavailable',valid?`${side} · ${fmt(100*(t.price/value-1),2)}% price vs MA`:'Insufficient history'));
    }
  }
  function parseDate(s){return new Date(`${s}T00:00:00Z`).getTime();}
  function renderChart(t) {
    const svg=el('chart');svg.replaceChildren();
    const all=t.history||[];
    if(!all.length){el('chartNote').textContent='Price history is unavailable for this ticker.';return;}
    const end=parseDate(all[all.length-1][0]);
    const start=currentRange==='all'?-Infinity:end-Number(currentRange)*86400000;
    const rows=all.filter(r=>parseDate(r[0])>=start);
    if(!rows.length){el('chartNote').textContent='No observations in the selected range.';return;}
    const W=1000,H=420,L=62,R=22,T=20,B=34,iw=W-L-R,ih=H-T-B;
    let min=Math.min(...rows.map(r=>r[3]??r[4])),max=Math.max(...rows.map(r=>r[2]??r[4]));
    const relevant=t.zones.filter(z=>{
      const d=z.dates.length?Math.min(...z.dates.map(parseDate)):start;
      const span=Math.max(max-min,Math.abs(max)*.02);
      return d<=end && z.high>=min-span*.35 && z.low<=max+span*.35;
    });
    relevant.forEach(z=>{min=Math.min(min,z.low);max=Math.max(max,z.high);});
    const pad=(max-min)*.06||1;min-=pad;max+=pad;
    const x=i=>L+(rows.length<=1?0:i/(rows.length-1))*iw;
    const y=v=>T+(max-v)/(max-min)*ih;
    for(let j=0;j<=4;j++){
      const val=min+(max-min)*j/4, yy=y(val);const line=document.createElementNS('http://www.w3.org/2000/svg','line');line.setAttribute('x1',L);line.setAttribute('x2',W-R);line.setAttribute('y1',yy);line.setAttribute('y2',yy);line.setAttribute('class','gridline');svg.appendChild(line);
      const label=document.createElementNS('http://www.w3.org/2000/svg','text');label.setAttribute('x',L-8);label.setAttribute('y',yy+4);label.setAttribute('text-anchor','end');label.setAttribute('class','axis');label.textContent=money(val);svg.appendChild(label);
    }
    // Draw bands behind price so a close trace remains readable.
    relevant.forEach(z=>{
      const d=z.dates.length?Math.min(...z.dates.map(parseDate)):parseDate(rows[0][0]);
      const idx=Math.max(0,rows.findIndex(r=>parseDate(r[0])>=d));
      const rect=document.createElementNS('http://www.w3.org/2000/svg','rect');
      rect.setAttribute('x',x(idx));rect.setAttribute('y',y(z.high));rect.setAttribute('width',Math.max(1,W-R-x(idx)));rect.setAttribute('height',Math.max(2,y(z.low)-y(z.high)));rect.setAttribute('opacity','.12');rect.setAttribute('class',z.side==='Support'?'zone-support':'zone-resistance');
      const title=document.createElementNS('http://www.w3.org/2000/svg','title');title.textContent=`${z.side} ${z.tier}: ${z.low.toFixed(2)}–${z.high.toFixed(2)}; ${z.status}; dates ${z.dates.join(', ')||'unavailable'}`;rect.appendChild(title);svg.appendChild(rect);
    });
    let lineD='';
    rows.forEach((r,i)=>{const px=x(i),py=y(r[4]);lineD+=(i?'L':'M')+px.toFixed(1)+' '+py.toFixed(1);});
    // Subtle OHLC range whiskers.
    const stride=Math.max(1,Math.ceil(rows.length/500));
    for(let i=0;i<rows.length;i+=stride){const r=rows[i];if(r[2]===null||r[3]===null)continue;const wick=document.createElementNS('http://www.w3.org/2000/svg','line');wick.setAttribute('x1',x(i));wick.setAttribute('x2',x(i));wick.setAttribute('y1',y(r[2]));wick.setAttribute('y2',y(r[3]));wick.setAttribute('stroke','#7b9cac');wick.setAttribute('stroke-width','.7');svg.appendChild(wick);}
    const path=document.createElementNS('http://www.w3.org/2000/svg','path');path.setAttribute('d',lineD);path.setAttribute('class','price-line');svg.appendChild(path);
    const first=document.createElementNS('http://www.w3.org/2000/svg','text');first.textContent=rows[0][0];first.setAttribute('x',L);first.setAttribute('y',H-9);first.setAttribute('class','axis');svg.appendChild(first);
    const last=document.createElementNS('http://www.w3.org/2000/svg','text');last.textContent=rows[rows.length-1][0];last.setAttribute('x',W-R);last.setAttribute('y',H-9);last.setAttribute('text-anchor','end');last.setAttribute('class','axis');svg.appendChild(last);
    el('chartNote').textContent=`${rows.length} daily observations from ${rows[0][0]} through ${rows[rows.length-1][0]}. Bands are retrospective overlays, not signals available on every plotted date. Bands outside the visible scale remain listed below.`;
  }
  function render(t) {
    if(!t)return;
    el('selectedName').textContent=t.name;
    renderMetrics(t);renderNearest(t);renderMA(t);renderChart(t);renderZones(t);renderIndicators(t);
  }
  el('search').addEventListener('input',e=>options(e.target.value));
  el('ticker').addEventListener('change',e=>render(bySymbol.get(e.target.value)));
  document.querySelectorAll('[data-range]').forEach(btn=>btn.addEventListener('click',()=>{
    currentRange=btn.dataset.range;document.querySelectorAll('[data-range]').forEach(b=>b.setAttribute('aria-pressed',String(b===btn)));renderChart(bySymbol.get(el('ticker').value));
  }));
  options('');
})();
</script>
</body>
</html>
'''


def build_dashboard(data: dict[str, Any], output_path: str | Path) -> Path:
    """Write a standalone dashboard and return its path.

    Inputs are reduced to finite values and history through the declared cutoff.
    All source-provided text is carried as safely encoded JSON and inserted into
    the document with DOM text nodes.
    """
    if not isinstance(data, dict):
        raise TypeError("data must be a dictionary")
    payload = _prepare(data)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    html = _HTML.replace("__DATA__", _json_for_script(payload))
    output.write_text(html, encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an offline ticker review dashboard.")
    parser.add_argument("input_json", type=Path, help="Enriched monitor JSON containing ticker_dashboard_data")
    parser.add_argument("output_html", type=Path, help="Destination for the standalone HTML dashboard")
    parser.add_argument("--ticker", help="Filter to one exact universe ticker, such as GOOG")
    args = parser.parse_args()

    try:
        source = json.loads(args.input_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        parser.error(f"cannot read input JSON: {exc}")
    data = source.get("ticker_dashboard_data") if isinstance(source, dict) else None
    if not isinstance(data, dict) or not isinstance(data.get("tickers"), list):
        parser.error("input JSON must contain ticker_dashboard_data with a tickers list")

    if args.ticker:
        requested = args.ticker.strip().upper()
        matches = [
            row for row in data["tickers"]
            if isinstance(row, dict) and str(row.get("ticker") or "").strip().upper() == requested
        ]
        if not matches:
            parser.error(f"unknown ticker {args.ticker!r}; it must exactly match a ticker in the supplied universe")
        data = {**data, "tickers": matches}

    try:
        output = build_dashboard(data, args.output_html)
    except (OSError, TypeError, ValueError) as exc:
        parser.error(f"could not build dashboard: {exc}")
    print(output)


if __name__ == "__main__":
    main()
