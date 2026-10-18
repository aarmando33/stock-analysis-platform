# Stock Buy/Sell Monitor production delivery

The daily GitHub `Daily stock prices` workflow is the canonical calculation/export runtime.
Use its completed `stock-price-feed` artifact rather than recalculating the workbook inside a chat.

Production wakes every 20 minutes on weekdays at minutes 7, 27 and 47, 18:00–03:59 UTC (the after-midnight portion is Tuesday–Saturday). The local production window is 1 PM through 8:59 PM America/Chicago on actual XNYS sessions. Cron payloads never select a summer/winter branch: both seasons use the same exchange-calendar decision. An early afternoon runner stays alive until the actual exchange close plus ten minutes, including early closes, instead of exiting and depending on another dispatch. Waiting is bounded at 130 minutes, in at most 60-second increments; the 160-minute job limit leaves generation time. This uses GitHub-hosted runner minutes, bounded by that timeout. Runs are serialized without canceling active work. A scheduled retry reuses only a successful main run at the same SHA with a matching current-session report and verified readiness; lookup searches the latest 100 successful runs to avoid hiding a producer behind no-op runs. Lookup failure generates afresh. Push/manual runs always generate immediately for the latest completed session. Failed price-feed commands retry up to three times, with 60 seconds between attempts. Failed jobs retain diagnostic artifacts and fail visibly.

`production_integrity.py` checks session dates, all universe members, usable counts, price/profile/universe/code hashes, dated deliverable hashes, workbook rows and dashboard cutoff/price data before producing `ready.json`. A separate `stock-monitor-ready` artifact holds this small record. The full report artifact must upload successfully before the readiness artifact is published. `Verify published stock monitor` then tests the real GitHub readiness lookup and reuse path. This job is read-only.

Delivery should search completed runs with actual report/readiness artifacts, not simply the most recent successful workflow: a successful retry can be a no-op with no new artifact. Verify `ready.json` against the exact run SHA, session, run id and validator hash; verify its deliverable/report hashes after downloading the report. GitHub performs scheduled generation and retries; the ChatGPT delivery task should only read and deliver verified artifacts, avoiding unattended GitHub write approvals. A missing report still requires a clear failure notice. GitHub cron can be delayed or dropped; these retries improve resilience but do not guarantee a wall-clock deadline without an independent timer.

For each delivery:

The independent checker validates the exact producing run's readiness, so another healthy run cannot mask a broken artifact. A post-close no-op must find verified reusable output or fail; an early/holiday gate is explicitly NOT_DUE. Failed/cancelled production also fails the checker. The validator still rechecks the XNYS cutoff before publishing; waiting never authorizes incomplete equity prices.

Delivery has two separate responsibilities: the 5 PM target and eventual catch-up. The user approved the native hourly fallback on October 18 after custom recurrence updates were blocked by the ChatGPT app-access layer. The existing task is active, Interval / Every 1 hour, in America/Chicago, with notifications preserved. Its prompt short-circuits without network outside weekdays 4 PM through the 10 PM hour, stays quiet during 4 PM preflight, targets delivery from 5 PM, and suppresses duplicate deliveries and unchanged waiting notices. A missing 5 PM report is delayed, not terminal. The 10 PM-hour check gives the final actionable failure if no verified output exists. Actual recurrence and saved prompt were reopened and verified; no new task/service was created. This native interval remains scheduled overnight, but its instructions stop immediately outside delivery hours, so it still incurs small model invocations. Prompt text alone cannot change recurrence.

Production admission stops at 9 PM local, with price-download and calculation/export step limits of 10 and 15 minutes. The latest nominal admitted slot is 8:47 PM; a delayed admitted slot starts before 9 PM, leaving headroom before the 10 PM final delivery check. Failed/timeout output cannot publish readiness. GitHub and ChatGPT can still delay dispatch, so no exact-time guarantee is possible. Late verification or attachment failure must provide a verified producer/artifact download link. Holiday/weekend freshness uses the latest completed session; manual requests may deliver immediately. Preserve notification preferences.

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

