# Report integrity review and repair

October 5, 2026, America/Chicago. Monitor baseline: `42417e4e54446e42df7e2ea02948a4ecbc789b87`. Main baseline: `e0e1fd069b535312903a6b3dd4d6ce33ee5819e4`.

Immediate defects have source repairs and regression tests. This is not certification of full master compliance, active production, or investment returns. The authoritative master, all 168 monitored symbols, approved range formulas, and conceptual 20/25/20/20/10/5 scoring weights are preserved. Legacy research formulas remain intact.

## Review scope and execution

Reviewed both branch inventories, master requirements, prior comprehensive audit, active entry points/patch installation, producer, calculator, Python/JS exporters, PowerShell runner, dependency/workflow contracts, tests, schemas, and relevant legacy formula/filter/output/change paths. Prior findings are carried forward where underlying code is unchanged, not counted as new live verification. The source inventory records hashes and duplicate definitions; earlier legacy definitions may be shadowed by later ones. No AGENTS.md exists in the repository.

Main lacked the monitor calculator/exporter while the external monitor pinned a newer branch. The previous workflow generated prices only. The proposed integrated change runs producer, calculator and exporter from one checkout; merge and external pin update are still activation steps.

Canonical lineage: universe and dated provider aliases -> adjusted provider history -> independent exchange-session audit -> validated records -> calculate() -> JSON -> XLSX. The exporter has no business formulas. Range/MAs/returns/RSI/MACD use closes; ATR/pivots use OHLC; flow uses signed volume. Benchmarks align actual dates. Context normalizes raw research into fixed-weight buckets; absent evidence gives no points. Ownership requires confirmed sourced inputs. Feed, optional input and source-code hashes are retained.

## Repairs

| Priority | Confirmed problem | Repair and test evidence |
|---|---|---|
| P0 | Entirely stale feed could pass | Producer compares with independent XNYS session; stale metrics withheld; holiday/early-close and stale tests |
| P0 | Export required blocked local socket | Portable openpyxl exporter; JSON/XLSX numerical round-trip and failure workbook tests |
| P1 | CURLD provider failure | Sourced date-aware CURLD -> CURLF alias, preserving universe identity and recording provider symbol |
| P1 | Tiingo raw/adjusted columns collided | Select adjusted fields before rename; raw-versus-adjusted fixture |
| P1 | Invalid prices/interior gaps passed | Positive finite OHLC geometry and interior missing-close rejection; invalid rows remain unranked |
| P1 | Blank research dates bypassed validation | Mandatory nonblank source/date/evidence; future direct benchmark cutoff |
| P1 | Missing price hid owned positions | Retain confirmed holdings with Data Unavailable; no fabricated price-derived P&L |
| P1 | Legacy stale fallback and stale refresh | No failed prices in ranked fallback; independent exchange-session check |
| P1 | Change comparison used overwritten latest | Select only strictly prior dated snapshots; OLD -> NEW fixture |
| P1 | Empty fundamentals crashed volume fill | Indexed missing-volume Series instead of scalar NaN |
| P2 | Infinite/zero volume could confirm | Unavailable flow/confirmation on invalid/empty volume |
| P1 | Crypto UTC daily candle was unfinished at U.S. close | Crypto daily bars withheld until UTC midnight; U.S. exchange close cannot validate a partial 24-hour candle |
| P2 | Source text could execute in Excel | Literal text cell types; formula-looking source fixture |
| P2 | Ranked sections absent | Add buy/accumulate, drop/reversal, rotation, flow/warnings, largest drops and large-cap views; retain old tabs |
| P2 | Schedule drifted with DST | Two UTC schedules select approximately 4:30 PM Central feed start before intended 5 PM report |

Alias source: [Curaleaf's July 6, 2026 announcement](https://www.prnewswire.com/news-releases/curaleaf-resumes-trading-under-curlf-as-temporary-transition-period-concludes-302817320.html). The alias alone does not establish provider adjustment correctness.

## All 62 sections

Implemented means the source capability exists, not that production has been verified. Partial means material requirements/evidence remain. Missing requirements have not been removed. These assessments are not a test pass percentage.

| Section | Assessment | Evidence / outstanding work |
|---|---|---|
| 1 Purpose | Partial | Technical/action pipeline exists; research ingestion and performance validation incomplete |
| 2 Authoritative source | Partial | Audit-first reader and artifact; external newest-success/pin activation pending |
| 3 Freshness | Implemented | Independent exchange calendar in producer/consumer; structured failure |
| 4 Price quality | Partial | Invalid/missing/stale visible; full source-status summary and discontinuity investigation incomplete |
| 5 Universe | Implemented | Unchanged 168 unique symbols; core/added counts and coverage |
| 6 History | Partial | Adjusted fixed anchor, duplicates/geometry; independent split/dividend and sparse-date checks incomplete |
| 7 Primary Win% | Implemented | Preserved formula; IPO/anchor/zero-range tests |
| 8 52W Win% | Partial | Approved closing-range label/alias preserved; high/low interpretation requires explicit resolution |
| 9 price_suggest_80 | Implemented | Preserved formula and analytical test |
| 10 Anchors | Partial | 5/10/20/63/126/YTD returns; full displayed anchors and month convention incomplete |
| 11 RSI | Implemented | Approved Wilder-style EWM; monotonic/flat tests; shared feed implementation |
| 12 MAs | Partial | MA20/50/100/200 and slopes; crossover/reclaim events incomplete |
| 13 MACD | Partial | 12/26/9/histogram; full crossover/zero-line event fields incomplete |
| 14 ATR | Implemented | Approved Wilder-style EWM; gap recurrence test and risk use |
| 15 Support/resistance | Partial | Uncapped pivots/MAs; gaps, AVWAP, volume-profile absent |
| 16 Distance | Partial | Exact bands; support/resistance conversion tracking absent |
| 17 Actionable levels | Partial | Defended buy zone/invalidation/trim/RR; complete confirmations/targets absent |
| 18 Basing | Partial | Compression/higher lows/support/ATR/volume; divergences and independent checks incomplete |
| 19 Falling knife | Partial | Breakdown precedence and bands; full lower-high/failed-bounce/fundamental veto incomplete |
| 20 Reversal | Partial | Reclaim/higher lows/histogram/flow; full RS/rotation/support checklist incomplete |
| 21 Breakouts | Partial | Prior high/consecutive break/volume; multi-month/sector/follow-through monitoring incomplete |
| 22 Breakdowns | Partial | Prior-low warnings; gap/volume/RS taxonomy incomplete |
| 23 RS | Partial | Date-aligned market/sector 20/63 returns; 126/slope/industry coverage incomplete |
| 24 Volume | Partial | Baseline/relative/up/down/contraction; full data-quality lineage incomplete |
| 25 Flow | Partial | Signed-volume five-way classification; independent institutional/fund evidence absent |
| 26 OBV/A-D | Partial | OBV and signed flow; A-D and divergence absent |
| 27 AVWAP | Missing | No sourced anchors/engine |
| 28 Volume-by-price | Missing | No reliable profile input/engine |
| 29 Rotation | Partial | Relative-return score; breadth/participation/themes/catalysts absent |
| 30 Early rotation | Partial | Legacy heat; canonical group-inflection/earnings confirmation incomplete |
| 31 Fundamentals | Partial | Dated context normalizers; industry-aware ingestion/history/currency units incomplete |
| 32 Market cap | Partial | $10B overlay; full core/speculative/ETF/crypto classification absent |
| 33 Insider | Missing | No Form 4 ingestion/transaction-code interpretation |
| 34 Institutional | Missing | Optional rating only; no structured 13F/fund-flow ingestion |
| 35 Owned | Partial | Sourced confirmed holdings retained; age/corporate-action/transaction reconciliation incomplete |
| 36 Opportunity | Partial | Fixed conceptual weights; calibration and full evidence incomplete |
| 37 Confidence | Partial | Separate score/coverage; correlated evidence/calibration needs review |
| 38 Signals | Partial | Precedence exists; complete Sell/Reduce taxonomy unvalidated |
| 39 Quick scan | Partial | Workbook Master/Top; change-focused narrative/fields incomplete |
| 40 Master | Implemented | Expected rows retained, failures unranked; full Calculations |
| 41 Ranked sections | Partial | Additive A-K-oriented views; owned-action/reversal refinement outstanding |
| 42 Large cap | Implemented | Sourced >=$10B top-25 full-score view; missing caps disclosed |
| 43 Discovery | Partial | Broad legacy universe scan; canonical candidate pipeline absent |
| 44 Holding pattern | Missing | No durable candidate lifecycle |
| 45 Promotion | Missing | No corroborated promotion audit trail |
| 46 Removal | Partial | No silent removals; durable process/journal absent |
| 47 Changes | Partial | Legacy prior-date bug repaired; canonical prior-run events absent |
| 48 Environment | Partial | Optional benchmark/sector trend; breadth/yield/credit/volatility ingestion absent |
| 49 Provenance | Partial | Input/code hashes, sources/dates/alias; publication-time/metric-level lineage incomplete |
| 50 Validation | Partial | Reconciliation/date/finite/geometry/mismatch tests; corporate-action and publish gates incomplete |
| 51 Failure | Implemented | Structured no-ranking failure; portable failure workbook |
| 52 Output levels | Partial | Summary/ranked/master; complete narrative research missing |
| 53 Write-ups | Missing | No complete sourced narrative renderer |
| 54 Decision rules | Partial | Breakdown/missing-evidence protection; unsafe legacy heuristic interpretation remains |
| 55 Bottom framework | Partial | Bands/coverage/evidence; independent judgment/calibration absent |
| 56 Risk | Partial | Positive invalidation/RR; execution gaps/sizing/liquidity/concentration absent |
| 57 Coding rules | Implemented | Requirements/formulas/membership preserved; additive reviewable repairs |
| 58 Tests | Partial | Regression/integration tests; all indicator goldens/real artifact/cross-platform checks pending |
| 59 Performance | Partial | Bulk/cache/retries; durable store/incremental/fundamental refresh needs work |
| 60 Daily run | Partial | Unified JSON/XLSX job; merge/live verification/external pin pending |
| 61 Source of truth | Implemented | Master unchanged; formula interpretation conflicts disclosed |
| 62 Improvement | Partial | Explicit gaps/validation plan; no demonstrated investment edge |

## Material unresolved integrity risks

- No out-of-sample return/drawdown/turnover/cost/liquidity/benchmark/confidence-calibration claim is supported. Correct arithmetic does not establish investment usefulness.
- Daily workflow supplies prices only. Fundamentals/revisions/insider/institutional/benchmark/sector/ownership inputs must be integrated as sourced dated evidence. Low coverage/empty views must not be presented as market conclusions.
- Legacy raw-close range metrics, debt/equity unit heuristics and basing/oversold research scores differ from canonical decisions. Preserve compatibility and disclose conflicts before changing those formulas.
- Adjusted labels are not independent proof of split/dividend/currency correctness. Archive vendor snapshots and validate representative corporate actions.
- As-of dates do not establish actual availability time. Same-day after-close research can leak unavailable knowledge; record publication and availability timestamps.
- Retrospectively testing today's 168 names introduces survivorship bias. Preserve effective-dated membership, delisted names and point-in-time actions.
- Trading setup, investment quality/valuation, portfolio sizing and executable broker orders are separate capabilities. Current score does not implement all four.

## Activation and evaluation gates

1. Review/merge the integrated change only after CI passes. Verify a real current GitHub run: audit, 168-row reconciliation, alias, missing/invalid records, JSON/XLSX matching values and source hashes.
2. Preserve the October 2 artifact and workbook for numerical comparison. Update the external exact-commit pin deliberately; test stale/no-artifact/provider/export failures before restoring its weekday 5 PM schedule.
3. Integrate sourced point-in-time research, sector/benchmark/security identity and corporate actions with explicit units/currency/industry/publication time. Implement missing engines with acceptance fixtures and additive fields. Resolve 52W high/low and 20-versus-21-session month semantics before changing approved formulas.
4. Separately evaluate trading and investing horizons. Walk forward with only available evidence, next-session executable fills, transaction costs/slippage, liquidity, delisted names and non-overlapping holdout periods. Compare SPY/sector/simple baselines; report sample sizes, turnover, drawdowns and excess return. Today's adjusted history is not a complete historical decision dataset.
5. Paper-track frozen signals before capital allocation or execution integration. Scores/confidence describe evidence, not win probabilities.

These are completion gates, not promises of investment results.

## Verification receipt

Local regression suite and the synthetic 168-symbol producer-to-XLSX integration
pass. A live October 5 feed returned all 168 symbols; 167 passed the producer and
monitor checks. CURLD was fetched as CURLF. ALB was withheld because its supplied
October 5 Close (105.75) exceeded High (105.665001); no price was fabricated to
repair that contradiction. The current 20-sheet workbook exported successfully,
and an independent saved-file check matched 55,180 exported values with report
JSON, counts and source-code hashes. Research context and benchmarks were not
supplied; the report is explicitly price-only/data-limited.

The original October 2 ZIP download reference returned HTTP 403 on this host,
so the archived original workbook comparison remains unverified. Visual layout,
real GitHub production execution and investment performance are not certified
by the local numerical checks. The external recurring monitor remains paused.
