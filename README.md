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
python export_monitor.py outputs/monitor_results.json outputs/Stock_Buy_Sell_Monitor.xlsx
```

Python export uses openpyxl and requires no daemon, RPC socket or proprietary runtime. Business calculations stay in the calculator. `RUN_MONITOR.ps1` is a convenience runner for bundled Codex Python. `export_monitor.mjs` remains an optional artifact-tool preview exporter, with that runtime requirement.

Supply `--context`, `--positions`, and `--benchmarks` only with sourced, dated inputs. The daily workflow currently supplies prices only: fundamental/revision/insider/institutional/benchmark/ownership evidence is unavailable unless explicitly provided. Missing evidence lowers coverage and cannot grant a Buy. Empty large-cap/rotation views can reflect missing research rather than an absence of opportunities.

Historical rebuilds require `--historical --session YYYY-MM-DD` and a matching archived feed. Cutting off today's adjusted series does not recreate point-in-time fundamentals, constituents or corporate-action knowledge.

See `REPORT_INTEGRITY_AUDIT.md` for all 62 assessments and activation gates. Review and merge the integrated change, verify a real GitHub daily run, and deliberately update the external monitor's exact-commit pin before restoring its schedule. Source changes alone do not update that external task.

Legacy research entry points remain available, with different adjustment/scoring conventions. They must not substitute for canonical monitor decisions. No brokerage execution or profitability claim is included.
# Concise daily workbook

The default Excel export uses the October 2 reader tabs plus Calculations (12 sheets).
Reader lists retain the October 2 columns, adding missing bottom scores, full input coverage/status and level test counts
alongside the existing basing status. Scanner shows up to 15 bottom technical candidates (drawdown at least 15%) and Top Opportunities
up to 10. Master and Calculations retain all 168 identities.

Support/resistance sheets show up to 10 candidates within 3% of price, with a
relevant swing-low/high source and at least two subsequent defended touch episodes. MA-only levels,
same-day extremes, invalid prices and opposite-side levels are excluded. These
are screening candidates, not validated price floors/ceilings. Full source fields,
bottom/base heuristics and original scores remain available on Calculations.

`python export_monitor.py report.json report.xlsx --detailed` retains the expanded
technical export. Range-position percentages are not probabilities of profit;
bottom/base/strength rules still require independent historical validation.

