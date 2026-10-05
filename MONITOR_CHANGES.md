# Approved monitor corrections — October 4, 2026

The October 2 generator ran inline in ChatGPT, outside this repository.
`buy_sell_monitor.py` now owns calculations; `export_monitor.mjs` owns presentation.
The authoritative master specification remains unchanged. Existing legacy scripts
and price-feed workflow remain intact. This implements the approved targeted
calculation and Excel changes; it does not claim completion of all 62 sections.

## Running

On the Codex desktop host, run `RUN_MONITOR.ps1 -Feed <extracted-feed-directory>`.
Supply `-Context`, `-Positions` and `-Benchmarks` when sourced inputs are available.
Use `-Session 2026-10-02 -Historical` only for an explicitly labeled historical
rebuild. Current runs determine the latest completed XNYS session, including
holidays and early closes. Stale feed/session mismatches stop before ranking.

The existing ChatGPT scheduled task must be instructed to run this versioned
generator instead of constructing inline calculations. Adding files to the
repository alone cannot change that external task. No duplicate schedule is
created by this change. The PowerShell runner requires the Codex bundled runtime
and its artifact-tool exporter; the Python calculator is independently portable.

## Inputs

Feed: `prices_latest.csv`, `price_history.csv.gz`, `price_audit.json` from the
successful Daily stock prices artifact. Expected universe: unchanged `tickers.csv`.
Price/history must match, have adjusted basis and valid positive OHLC.
Duplicate source keys are errors. Missing symbols stay visible and unranked.

Benchmark CSV: Date,Symbol,Close. SPY is market benchmark; the context's
Sector Benchmark identifies the relevant ETF. Benchmark closes must be adjusted
and sourced consistently. No benchmark means unavailable RS/rotation evidence.

Context template contains raw fundamentals, peer valuation, estimate revisions
and source/date/raw-evidence provenance. Growth/margin/revision ratios are decimal
fractions, monetary amounts use matching currencies and scales. See
`fundamental_evidence` for each documented normalizer. Sector peer PE and outside
institutional/insider evidence are not inferred from price changes. Inputs dated
after the report session or more than 120 days old are rejected. Missing data
remain unavailable. This version does not add an unverified financial-data feed.

Ownership template requires confirmed quantities/bases with source and as-of date.
No historical hardcoded holdings are imported. Aggregate transaction history
explicitly before supplying positions. Empty ownership is a valid placeholder.

## Formula changes

Primary/52W range-position formulas and price_suggest_80 are preserved. Added
2W return and changed YTD denominator to the prior year's last available close;
an IPO without that reference shows YTD unavailable. Wilder-style RSI/ATR are
preserved, with defined flat/one-direction RSI handling. MACD signal/histogram
and MA slopes are now computed and used.

Major support uses independently tested 63/126/252-session levels and MA50/100/200,
clustered within 0.5%. Touch episodes within 1% plus source confluence determine
strength; distance breaks ties. Short levels use 5/21-session pivots and MA20.
Both expose source, date, strength and tests. Anchored VWAP and volume-profile
levels remain outstanding, rather than being mislabeled as implemented.

Proximity is exactly the master's ≤2%, >2–3%, >3–5%, >5% bands. Support-distance
and resistance-distance use current price as denominator. Action tabs match
explicit proximity fields and exclude breakdown/breakout-only substring matches.

Volume now includes recent volume, prior-20-session average, relative volume,
up/down volume, contraction and signed-volume flow. OBV20 percentage is changed
to net signed volume / positive total volume, avoiding dependence on the arbitrary
starting cumulative OBV. Cumulative OBV remains available. Missing volume cannot
confirm a breakout or silently become Neutral flow.

Breakout confirmation requires two consecutive prior-high breaks plus relative
volume ≥1.5. Bottom evidence uses independent structure, volatility, flow,
momentum, benchmark RS, fundamentals and revisions; it is a research score that
still requires judgment, not a forecast probability. Existing drawdown/rebound
measures remain available.

Opportunity weights remain 20/25/20/20/10/5. Missing inputs earn zero evidence
points; weights are not renormalized. Evidence coverage is shown separately.
Setup Confidence is numeric 0–100. Actions are assigned last. Strong buy/buy and
confirmed breakout require corroboration and ≥75% evidence coverage. Warnings
remain possible when evidence is incomplete. No unavailable fundamental inputs
receive fixed neutral points. Every stock remains in Master.

## Layout

Existing 11 tabs retained. Calculations and Audit-Provenance are added.
User-facing sheets have 25 concise columns, with five position details on Owned
Positions. Technical provenance is removed from those views but retained in
Audit-Provenance. All original metrics remain available in Calculations.
Summary counts are computed, not hardcoded. Master includes failures; Scanner
is usable triggered stocks, uncapped and ranked. Support/resistance overlap is
allowed only when both explicit proximity rules qualify.

## Validation and remaining requirements

Run `python -m unittest discover -s tests -v` after installing requirements-monitor.
Tests independently verify key indicator recurrences, period boundaries, major
support candidates, volume sign, missing-data behavior, holidays, gates and views.
Real October 2 history is required for full workbook comparison before activation.

Discovery, analyst/insider/institutional ingestion, anchored VWAP/volume profile,
expanded market regime, historical change detection and additional ranked master
sections remain outstanding requirements. They are not removed from the master.
