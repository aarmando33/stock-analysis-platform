# Stock Buy/Sell Decision Monitor

`BUY_SELL_MONITOR_MASTER.md` remains authoritative. The unchanged universe has 160 core names plus eight required additions: 168 total. This is a research decision-support system; complete master compliance and investment performance are not yet established.

The primary source is yfinance adjusted OHLCV. Optional Tiingo replaces a ticker's entire history only when its independently validated latest XNYS session is usable. Calendar holidays and early closes are respected. Stale or invalid rows are never ranked. `symbol_aliases.csv` records sourced provider symbol changes; CURLD remains monitored and is fetched as CURLF after July 6, 2026.

Outputs are stored in the `stock-price-feed` GitHub Actions artifact:

- `prices_latest.csv`: current validated close, price date, provider, Primary Win%, 52-week Win%, and RSI.
- `price_history.csv.gz`: adjusted daily OHLCV history beginning March 1, 2020.
- `price_audit.json`: expected, valid, stale, and missing counts with timestamps.
- `monitor_results.json`: validated calculations, ranked views, input/code hashes.
- `Stock_Buy_Sell_Monitor.xlsx`: presentation of those exact calculated values.

The scheduled ChatGPT Stock Buy/Sell Monitor should read the latest successful artifact and refuse to create price-based signals for any ticker whose `price_status` is not `OK`.

## Production and reproduction

Daily stock prices starts at approximately 4:30 PM America/Chicago through two DST-aware UTC schedules. GitHub can delay scheduled jobs. One job downloads, validates, calculates and exports the complete artifact before the intended 5 PM report. Failed jobs retain diagnostic artifacts; these are not successful current reports.

Use Python 3.12 in an isolated environment:

```text
python -m pip install -r requirements-feed.txt
python -m unittest discover -s tests -v
python price_feed.py
python buy_sell_monitor.py --feed outputs --universe tickers.csv --output outputs/monitor_results.json
python profile_feed.py --input outputs/monitor_results.json --output outputs/monitor_results.json --profiles outputs/profiles.json
python export_monitor.py outputs/monitor_results.json outputs/Stock_Buy_Sell_Monitor.xlsx
```

Python export uses openpyxl and requires no daemon, RPC socket or proprietary runtime. Business calculations stay in the calculator. `RUN_MONITOR.ps1` is a convenience runner for bundled Codex Python. `export_monitor.mjs` remains an optional artifact-tool preview exporter, with that runtime requirement.

Supply `--context`, `--positions`, and `--benchmarks` only with sourced, dated inputs. Daily company profiles are display metadata only: fundamental/revision/insider/institutional/benchmark/ownership evidence remains unavailable unless explicitly provided. Missing evidence lowers coverage and cannot grant a Buy. Empty large-cap/rotation views can reflect missing research rather than an absence of opportunities.

Historical rebuilds require `--historical --session YYYY-MM-DD` and a matching archived feed. Cutting off today's adjusted series does not recreate point-in-time fundamentals, constituents or corporate-action knowledge.

See `REPORT_INTEGRITY_AUDIT.md` for all 62 assessments and activation gates. Review and merge the integrated change, verify a real GitHub daily run, and deliberately update the external monitor's exact-commit pin before restoring its schedule. Source changes alone do not update that external task.

Legacy research entry points remain available, with different adjustment/scoring conventions. They must not substitute for canonical monitor decisions. No brokerage execution or profitability claim is included.
# Concise daily workbook

The default Excel export uses the October 2 reader tabs plus Calculations and Zone Details (13 sheets).
Reader lists retain the October 2 layout, expanding the four historical level columns into S1/S2/R1/R2 min/max bands,
with bottom-zone bounds/status, Win6mo% and price_suggest_80. Existing moving-average columns remain populated. Scanner shows up to 15 bottom technical candidates (drawdown at least 15%) and Top Opportunities
up to 10. Master and Calculations retain all 168 identities.

Support/resistance sheets show all qualifying tickers with historical zones within 5% of price, ordered by proximity, with no ticker limit. Untested bands remain labeled;
two current-band tests and recent defense are required before a risk/reward setup is available. Moving averages
never add historical-zone strength. Scores and actions use the same zone evidence as the visible report;
the fixed weights and missing-research gates are preserved. All seven bottom inputs remain on Calculations.

Every daily `stock-price-feed` GitHub Actions artifact now contains `Stock_Buy_Sell_Monitor.xlsx`,
`Stock_Buy_Sell_Ticker_Dashboard.html`, dated copies, and the source JSON/data audit. Download and extract
the artifact, then open the workbook or dashboard. The dashboard has a ticker selector, chart ranges,
historical bands with dates/tests, Win%/Win52%/Win6mo%/price_suggest_80, and separate 20/50/100/200-day MA
references inside In-depth bands. This is a daily-close snapshot, not a hosted streaming service.

Fresh Yahoo company profiles populate stock name, USD market capitalization in millions (`capMil`), sector and provider industry (`Subsector`). Each ticker records retrieval UTC and source URLs in `profiles.json` and Calculations. Six workers use a 20-second hard limit per ticker; failures remain explicitly unavailable without removing any ticker or changing actions or research coverage. Profiles and symbol aliases are archived with input hashes, alongside the calculator and enrichment code hashes. The profile retrieval date is separate from the price session, including historical rebuilds.

Reader sheets and ticker dashboards include Recent Volume, Average Volume 20D, Relative Volume, 20D Net Volume %, Volume Confirmation and OBV from the existing calculator. These are display additions, not new calculations or scoring inputs.

```sh
python ticker_dashboard.py outputs/monitor_results.json outputs/Stock_Buy_Sell_Ticker_Dashboard.html
python ticker_dashboard.py outputs/monitor_results.json outputs/GOOG_dashboard.html --ticker GOOG
```

Unknown ticker requests fail explicitly; they do not change universe membership. A hosted phone request
form is separate work. The existing external monitor must use the verified production commit/artifact,
not its earlier pinned generator; see `PRODUCTION_MONITOR_HANDOFF.md`.

`python export_monitor.py report.json report.xlsx --detailed` retains the expanded
technical export. Range-position percentages are not probabilities of profit;
bottom/base/strength rules still require independent historical validation.

