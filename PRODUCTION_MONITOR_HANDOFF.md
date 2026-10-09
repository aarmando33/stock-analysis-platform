# Stock Buy/Sell Monitor production delivery

The daily GitHub `Daily stock prices` workflow is the canonical calculation/export runtime.
Use its completed `stock-price-feed` artifact rather than recalculating the workbook inside a chat.

For each delivery:

1. Select a successful main-branch run for the latest completed XNYS session. Record the run URL and exact head SHA.
2. Require `price_audit.json` and `monitor_results.json` to agree with that session. Report any missing/stale/invalid symbols and coverage counts; never present an older artifact as today's report.
3. Verify the input hashes in `monitor_results.json` against the artifact files and code hashes against that exact run commit. The production calculator/exporter and zone/dashboard modules must come from the same release. Replace the old `42417e4...` pin only after the new release passes its workflow and artifact checks.
4. Deliver `Stock_Buy_Sell_Monitor.xlsx` and `Stock_Buy_Sell_Ticker_Dashboard.html` together, including the as-of date and run link. Dated copies are supplied in the artifact. The dashboard contains all universe tickers; no separate calculation is needed to select a ticker already in the snapshot.
5. Base the written summary on the generated JSON. Include top opportunities, proximity candidates, breakdown warnings and confirmed owned-position actions as applicable. Explain the current-band evidence status and missing research; do not turn Win% into a win probability or price_suggest_80 into a recommended buy price.

The workbook preserves all 168 tickers (160 Core + 8 Added), existing MA columns, nearest/next historical-zone min/max fields, bottom bounds/status, and the dated Zone Details sheet. The dashboard additionally exposes major/deep zones and MA support/resistance references.

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
