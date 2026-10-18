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

Daily stock prices has nine weekday opportunities at 3:17, 3:37, 3:57, 4:17, 4:37, 4:57, 5:17, 5:37 and 5:57 PM America/Chicago, using paired DST-aware UTC schedules. Runs are serialized. A later attempt skips generation only after finding a verified current-session readiness record from the same release with an uploaded report. Lookup failure triggers generation. Push/manual runs always refresh. GitHub can delay or drop cron events; these retries improve resilience but cannot guarantee the 5 PM deadline without an independent timer.

After generation, `production_integrity.py` validates freshness, universe, usable price dates, input/code hashes, both dated exports, workbook rows and dashboard data before creating `ready.json`. The `stock-monitor-ready` artifact is published only after the full report upload succeeds. The read-only Verify published stock monitor workflow tests actual artifact reuse. Failed jobs retain diagnostics but never publish a verified readiness marker. ChatGPT delivery reads verified artifacts; it does not need to initiate GitHub writes. Successful retry no-op runs contain no new report artifact, so consumers must search for the actual producing run.

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

### Workbook historical levels

Production now uses one UTC schedule across seasons, with weekday wake-ups every 20 minutes from 18:07–03:47 UTC (after-midnight triggers Tuesday–Saturday). The exchange calendar permits local afternoon/evening work. An early runner waits until the actual close plus ten minutes, bounded at 130 minutes with a 160-minute job timeout, instead of discarding the wake-up. This consumes bounded GitHub runner minutes and removes dependence on a timely second cron. Price-feed failures have three bounded attempts; diagnostics are retained. Readiness checks distinguish NOT_DUE, verified reuse and actual production, and fail when a post-close run has no verified output. Production admission ends at 9 PM local, and download/export steps are bounded at 10/15 minutes to leave room for the final delivery check. The existing external task now uses the user-approved native hourly fallback, quiet outside weekday delivery hours and after delivery; its actual recurrence and saved prompt were verified. See PRODUCTION_MONITOR_HANDOFF.md. GitHub cron and ChatGPT scheduling remain external dependencies; this is not a guarantee of exact wall-clock delivery.

Every ticker view includes S1/S2/S3 and R1/R2/R3 observed min/max bands and boundary dates, COVID and since-COVID adjusted daily low/high references and dates, plus Recent Volume and Average Volume 20D. Short/Next/Major zone rules remain unchanged. COVID is February 19–April 30, 2020 and needs full coverage; since COVID starts March 1, 2020, with later-IPO history explicitly labeled. Earlier feed bars are used only for display references; scores and zones retain the established March 1 start.

Zone Details contains one row per ticker rather than four repeated identity rows. Detailed dates, tests and events remain in columns and JSON. Calculations retains complete audit evidence, with advanced columns collapsed initially. Methodology explains observation counts, when a band was knowable, basing uncertainty and the 15-name drawdown Scanner.

