# Stock Buy/Sell Monitor production delivery

The daily GitHub `Daily stock prices` workflow is the canonical calculation/export runtime.
Use its completed `stock-price-feed` artifact rather than recalculating the workbook inside a chat.

Production has nine weekday retry slots at 3:17, 3:37, 3:57, 4:17, 4:37, 4:57, 5:17, 5:37 and 5:57 PM America/Chicago, using paired UTC cron expressions and a DST gate. Runs are serialized without canceling an active refresh. A scheduled retry skips generation only if a successful main run at the same code SHA has a verified readiness record for the latest completed XNYS session and a report artifact. Readiness lookup failure triggers fresh generation; stale or missing evidence never suppresses a refresh. Push/manual runs always generate. A 30-minute job limit leaves room for later attempts.

`production_integrity.py` checks session dates, all universe members, usable counts, price/profile/universe/code hashes, dated deliverable hashes, workbook rows and dashboard cutoff/price data before producing `ready.json`. A separate `stock-monitor-ready` artifact holds this small record. The full report artifact must upload successfully before the readiness artifact is published. `Verify published stock monitor` then tests the real GitHub readiness lookup and reuse path. This job is read-only.

Delivery should search completed runs with actual report/readiness artifacts, not simply the most recent successful workflow: a successful retry can be a no-op with no new artifact. Verify `ready.json` against the exact run SHA, session, run id and validator hash; verify its deliverable/report hashes after downloading the report. GitHub performs scheduled generation and retries; the ChatGPT delivery task should only read and deliver verified artifacts, avoiding unattended GitHub write approvals. A missing report still requires a clear failure notice. GitHub cron can be delayed or dropped; these retries improve resilience but do not guarantee a wall-clock deadline without an independent timer.

For each delivery:

Readiness permits delivery of an honestly labeled, verified data-limited snapshot. Unexpected missing/stale/invalid prices or failed company-profile retrievals set `retry_needed=true`, so later GitHub slots continue refreshing instead of treating missing data as complete. Intentionally unfinished crypto candles and legitimately insufficient history do not trigger needless retries. A consumer may validate a partial readiness record for delivery; production retry reuse requires `retry_needed=false`.

1. Select a successful main-branch run for the latest completed XNYS session. Record the run URL and exact head SHA.
2. Require `price_audit.json` and `monitor_results.json` to agree with that session. Report any missing/stale/invalid symbols and coverage counts; never present an older artifact as today's report.
3. Verify the input hashes in `monitor_results.json` against the artifact files and code hashes against that exact run commit. The production calculator/exporter and zone/dashboard modules must come from the same release. Replace the old `42417e4...` pin only after the new release passes its workflow and artifact checks.
4. Deliver `Stock_Buy_Sell_Monitor.xlsx` and `Stock_Buy_Sell_Ticker_Dashboard.html` together, including the as-of date and run link. Dated copies are supplied in the artifact. The dashboard contains all universe tickers; no separate calculation is needed to select a ticker already in the snapshot.
5. Base the written summary on the generated JSON. Include top opportunities, proximity candidates, breakdown warnings and confirmed owned-position actions as applicable. Explain the current-band evidence status and missing research; do not turn Win% into a win probability or price_suggest_80 into a recommended buy price.

The workbook preserves all 168 tickers (160 Core + 8 Added), existing MA columns, three historical support/resistance min/max bands and boundary dates, bottom bounds/status, and Zone Details. S1/R1, S2/R2 and S3/R3 are the existing Short, Next and Major zones. Zone Details has one row per ticker and keeps contributing pivots, observation counts, band-known dates, tests and events in columns. The JSON retains long-form zone evidence. Calculations keeps every audit field and collapses advanced columns by default. The dashboard additionally exposes deep zones and MA support/resistance references.

COVID extrema are adjusted daily lows/highs in 2020-02-19 through 2020-04-30, requiring full window coverage. Since-COVID extrema use 2020-03-01 through the cutoff; later IPOs report available history with an explicit coverage label in Zone Details. Missing values remain unavailable. These reference extremes are not automatically defended zones. The feed starts February 19 for these references; the established scoring and zone calculation history remains March 1 onward. Verify this distinction before comparing releases.

Support/resistance sheets show every qualifying ticker, without the former 10-row limit. Reader columns begin with Ticker and Price, followed by capMil, Sector and Subsector; Win6mo% follows Win52%, and Action Reason accompanies Action. Reader display omits Universe, price_status, Price Basis and Price Provider. The underlying calculation JSON retains those audit fields and universe membership.

The workflow fetches fresh company profiles after calculations and before either export. Verify `profiles.json` and `symbol_aliases.csv` against their input hashes, and verify `profile_feed.py` and `profile_enrichment.py` alongside the retained calculator code hashes. Profile retrieval UTC and source URLs are separate from the market-session cutoff. capMil is USD millions, Subsector is provider industry, and unavailable metadata stays unavailable. A profile failure must not remove a ticker, alter its action or raise research coverage.

Both reader sheets and the dashboard display the existing calculated Recent Volume, Average Volume 20D, Relative Volume, 20D Net Volume %, Volume Confirmation and OBV. Dashboard sector, action and action reason come from the same enriched snapshot, including when profile retrieval fails. These additions do not change historical zones, scoring or action selection.

Scores, confidence, risk/reward and action selection now consume the same historical-zone evidence. Fixed weights and research gates remain. Full bottom confidence stays unavailable when a required research input is absent; price-only basing and breakdown status remain independently visible.

The existing schedule must retain its timezone and notification preferences when its source pin is updated. This repository does not control an external ChatGPT task's pause state. Do not claim that task was resumed without confirmation from its scheduler.

For an on-demand ticker page from the already validated snapshot:

```sh
python ticker_dashboard.py outputs/monitor_results.json outputs/GOOG_dashboard.html --ticker GOOG
```

This does not refresh prices. A new daily workflow run is needed for a new snapshot. A hosted mobile trigger/page is not installed by this release.
