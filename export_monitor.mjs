import fs from 'node:fs/promises';
import {Workbook,SpreadsheetFile} from '@oai/artifact-tool';

const [input,output,previewDir]=process.argv.slice(2);
if(!input||!output)throw new Error('Usage: node export_monitor.mjs report.json output.xlsx [preview-directory]');
const report=JSON.parse(await fs.readFile(input,'utf8'));
const wb=Workbook.create();
// Optional artifact-tool preview exporter. Production uses export_monitor.py.
const visible=['Overall Rank','Ticker','Owned/Watch','Price','Price Date','Buy Zone','Primary Win%','52W Closing-Range Win%',
 'Opportunity Score','Setup Confidence','Setup Confidence Coverage %','Evidence Coverage %','Bottom Confidence',
 'Bottom Confidence Coverage %','Research Coverage %','Overall Signal/Action','Action Reason',
 'Short Support','Support Timeframe','Major Support','Distance to Support %','Short Resistance','Major Resistance','Distance to Resistance %',
 'Invalidation','Downside %','Upside %','Risk/Reward','Trim Zone','Recent Volume','Average Volume 20D','Relative Volume','20D Net Volume %',
 'Basing Status','Bottom/Falling-Knife Status','Volume Confirmation','Rotation Stage','Money Flow'];
const letters=n=>{let s='';while(n){n--;s=String.fromCharCode(65+n%26)+s;n=Math.floor(n/26);}return s;};
async function sheet(name,rows,headers){
 const sh=wb.worksheets.add(name);sh.showGridLines=false;
 headers=headers||[...new Set(rows.flatMap(r=>Object.keys(r)))];
 if(!headers.length)headers=['Status'];
 const content=rows.length?rows.map(r=>headers.map(h=>r[h]??null)):[headers.map((_,i)=>i===0?'No qualifying records':null)];
 sh.getRange(`A1:${letters(headers.length)}1`).values=[headers];
 sh.getRange(`A2:${letters(headers.length)}${content.length+1}`).values=content;
 const all=sh.getRange(`A1:${letters(headers.length)}${content.length+1}`);
 all.format.font.size=11;all.format.rowHeight=name==='Methodology'?110:60;
 all.format.columnWidth=18;all.format.wrapText=true;
 sh.getRange(`A1:${letters(headers.length)}1`).format={fill:'#193F60',font:{bold:true,color:'#FFFFFF'},rowHeight:52,wrapText:true};
 sh.freezePanes.freezeRows(1);sh.freezePanes.freezeColumns(Math.min(2,headers.length));
 headers.forEach((h,i)=>{
  const column=sh.getRange(`${letters(i+1)}2:${letters(i+1)}${content.length+1}`);
  if(h.includes('%'))column.setNumberFormat('0.0"%"');
  else if(h.includes('Score')||h.includes('Confidence')||h.includes('Points')||h==='Risk/Reward')column.setNumberFormat('0.0');
  else if(/Price$|Support$|Resistance$|^ATR$|^MACD|MA$|Basis$|Value$|Unrealized \$/.test(h))column.setNumberFormat('0.00');
  else if(h.includes('Volume')&&!h.includes('Ratio')&&!h.includes('Confirmation'))column.setNumberFormat('#,##0');
  if(/Reason|Source|Status|Action|Location|Basis|Evidence|Owned\/Watch|Formula|Notes/.test(h))sh.getRange(`${letters(i+1)}:${letters(i+1)}`).format.columnWidth=36;
 });
 if(previewDir){
  await fs.mkdir(previewDir,{recursive:true});
  const image=await wb.render({sheetName:name,range:`A1:${letters(Math.min(headers.length,7))}${Math.min(content.length+1,6)}`,scale:1.4,format:'png'});
  await fs.writeFile(`${previewDir}/${name.replaceAll('/','-')}.png`,new Uint8Array(await image.arrayBuffer()));
 }
 return sh;
}
await sheet('Summary',[
 {Metric:'Report status',Value:report.status,Notes:report.historical?'Historical rebuild; not current trading guidance':'Latest completed session'},
 {Metric:'Market session',Value:report.session,Notes:'All technical history is cut off at this session'},
 ...Object.entries(report.counts).map(([Metric,Value])=>({Metric,Value,Notes:'Computed from validated records'})),
 ...Object.entries(report.failure||{}).map(([Metric,Value])=>({Metric,Value,Notes:'Freshness failure; no current signals'})),
 {Metric:'Ownership',Value:report.positions.length?'Confirmed source supplied':'Unavailable',Notes:'No hardcoded holdings used'},
 {Metric:'Scoring',Value:'Fixed 20/25/20/20/10/5 weights',Notes:'Missing evidence earns no points; coverage shown separately'}
],['Metric','Value','Notes']);
for(const [name,rows]of Object.entries(report.views)){
 const cols=[...visible];
 if(name==='Owned Positions')cols.push('Qty','Cost Basis','Current Value','Unrealized $','Unrealized %');
 await sheet(name,rows,cols);
}
await sheet('Calculations',report.calculations);
const auditSheet=await sheet('Audit-Provenance',report.calculations.map(r=>Object.fromEntries(
 ['Ticker','Universe','price_status','Price Date','Price Provider','Price Basis','Context Source','Context As Of','Ownership Source',
 'Short Support Source','Short Support Date','Major Support Source','Major Support Date','Major Support Strength',
 'Short Resistance Source','Major Resistance Source','Context Raw Evidence'].map(k=>[k,r[k]??null]))));
const hashRows=[['Input file','SHA256'],...Object.entries(report.source_sha256)];
const hashStart=report.calculations.length+5;
auditSheet.getRange(`A${hashStart}:B${hashStart+hashRows.length-1}`).values=hashRows;
await sheet('Methodology',[
 {Metric:'Win%',Formula:'(maximum adjusted close − current)/(maximum − minimum) × 100; not probability of winning',Window:'Primary: 2020-03-01 onward; 52W: 365 calendar days'},
 {Metric:'price_suggest_80',Formula:'20% maximum + 80% minimum adjusted close',Window:'Same Primary historical window'},
 {Metric:'Support selection',Formula:'Short: nearest valid candidate. Major: strongest test/confluence cluster, distance breaks ties',Window:'Short 5/21 pivots, MA20; major 63/126/252 pivots, MA50/100/200'},
 {Metric:'Basing',Formula:'Compression ≤10% of 21-day high, |20-session return|≤8%; confirmed adds higher lows, ≥2 support tests, declining ATR, volume contraction',Window:'21 sessions'},
 {Metric:'MACD',Formula:'EMA12 − EMA26; signal EMA9; histogram line − signal',Window:'Adjusted daily close'},
 {Metric:'ATR',Formula:'Wilder-style EWM of max(high−low, |high−previous close|, |low−previous close|)',Window:'14 sessions'},
 {Metric:'20D Net Volume %',Formula:'Net signed volume / total positive volume × 100; cumulative OBV also retained',Window:'20 sessions'},
 {Metric:'Breakout',Formula:'Above prior 21-session high; confirmation requires prior-session breakout and relative volume ≥1.5',Window:'Latest session excluded from reference level'},
 {Metric:'Score',Formula:'Fixed conceptual weights; unavailable inputs receive zero evidence points, never neutral constants',Window:'Sources and input dates required'},
 {Metric:'Confidence',Formula:'Equal independent evidence confirmations across support, structure, volume, RS, fundamentals, revisions, flow, valuation, RR, MACD',Window:'0–100; missing confirmation gives zero'},
 {Metric:'Bottom Confidence',Formula:'Structure, volatility, flow, momentum, RS, fundamentals, revisions; judgment remains necessary',Window:'Bands 80/65/50/35; not a probability'},
 {Metric:'Action',Formula:'Breakdown warning first; buy/confirmed-breakout decisions require ≥75% coverage and corroboration',Window:'Assigned after all calculations'},
 {Metric:'Ownership',Formula:'Only confirmed, sourced ownership input; otherwise blank quantity, basis and gain/loss',Window:'No historical hardcoded positions'},
 {Metric:'Scope',Formula:'Discovery, anchored VWAP/volume profile and expanded institutional research remain separate outstanding master requirements',Window:'This change implements approved workbook/calculation corrections'}
],['Metric','Formula','Window']);
await wb.recalculate();
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NUM!|#NAME\\?',options:{useRegex:true,maxResults:20},maxChars:1500})).ndjson);
await fs.mkdir(output.substring(0,Math.max(output.lastIndexOf('/'),output.lastIndexOf('\\'))),{recursive:true});
await(await SpreadsheetFile.exportXlsx(wb)).save(output);
console.log(output);
