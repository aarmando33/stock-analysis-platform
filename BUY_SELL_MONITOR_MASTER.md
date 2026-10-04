# STOCK BUY/SELL DECISION MONITOR — MASTER SPECIFICATION

## 1. PURPOSE

Build, maintain, and run a comprehensive Stock Buy/Sell Decision Monitor.

The system is intended to help answer five questions:

1. **What should I consider buying now?**
2. **What is approaching an attractive buy area?**
3. **What do I already own that should be held, protected, trimmed, or sold?**
4. **Which stocks have fallen substantially but are forming a legitimate bottom/reversal rather than remaining falling knives?**
5. **Which stocks, sectors, subsectors, or themes are beginning to gain momentum early enough to capture a developing trend?**

The monitor must combine:

- Price history
- Primary Win%
- 52-week Win%
- Support/resistance
- Trend
- Momentum
- Basing/bottom formation
- Drop-and-reversal analysis
- Breakouts/breakdowns
- Relative strength
- Volume
- Money flow
- Sector/subsector rotation
- Fundamentals
- Earnings/revisions
- Insider activity
- Institutional evidence
- Market environment
- Risk/reward
- Discovery of new opportunities

The system must NEVER assume that a low price, large decline, oversold RSI, or high Win% automatically makes a stock a Buy.

The central principle is:

**FALLEN + QUALITY + SUPPORT + STABILIZATION + IMPROVING FLOW/ROTATION + FAVORABLE RISK/REWARD = POTENTIAL OPPORTUNITY**

A falling knife must be distinguished from a developing bottom.

---

# 2. AUTHORITATIVE PROJECT / DATA SOURCE

Use the connected GitHub repository:

**aarmando33/stock-analysis-platform**

as the primary project repository.

Before performing current-market analysis, locate the newest successful **Daily stock prices workflow artifact**.

The price artifact is the authoritative source for the monitor's current-session technical calculations unless the implementation has subsequently been deliberately upgraded to a more reliable source.

Expected artifact components include:

- `price_audit.json`
- `prices_latest.csv`
- `price_history.csv.gz`

Read `price_audit.json` FIRST.

Do not silently substitute stale public prices when the official pipeline has failed.

---

# 3. HARD CURRENT-SESSION FRESHNESS GATE

This is mandatory.

Determine the **latest completed U.S. regular trading session** as of execution time in `America/New_York`.

Then compare that date against:

`price_audit.json -> latest_market_date`

The usable price rows must correspond to that same completed trading session.

## PASS

The freshness gate passes only when:

- the artifact represents the latest completed U.S. trading session;
- `latest_market_date` matches that session;
- usable rows contain that session's prices;
- the price audit is valid enough to support analysis.

## FAIL

If the newest successful artifact is stale:

1. Look for a newer workflow run/artifact.
2. Recheck freshness.
3. If current-session prices still cannot be obtained, DO NOT pretend the monitor is current.

Report:

**INCOMPLETE — CURRENT-DATE PRICE FEED UNAVAILABLE**

Also report:

- expected market session;
- artifact market date;
- workflow/artifact date;
- ticker coverage;
- missing/failed rows;
- relevant pipeline error information.

Do NOT produce current:

- rankings;
- Buy zones;
- Sell zones;
- current support/resistance conclusions;
- technical signals;

using stale prices.

## WEEKENDS / HOLIDAYS

Use the latest completed U.S. trading session, not the calendar date.

---

# 4. PRICE QUALITY

Only rows where:

`price_status = OK`

may be used for current analysis.

Track and report:

- expected tickers;
- received tickers;
- usable tickers;
- missing tickers;
- failed tickers;
- duplicate tickers;
- stale tickers;
- unexpected tickers.

Never silently remove a failed ticker from the monitor.

---

# 5. REQUIRED UNIVERSE AUDIT

The monitor must reconcile the complete expected universe before rankings are created.

Current baseline:

**Core Expected = 160**

Additional explicitly required names:

- LRCX
- AMAT
- ETN
- PWR
- CIEN
- ADI
- ZS
- MCHP

**Added Expected = 8**

ONTO and GLW are already members of the core universe and must NOT be double counted as added stocks.

Current expected total:

**168 unique required symbols**, assuming the 160-core definition has not intentionally changed.

If the repository contains the authoritative core-universe file, use that file rather than recreating the list manually.

Always deduplicate symbols.

Produce a universe reconciliation showing:

- Core Expected
- Core Found
- Core Missing
- Added Expected
- Added Found
- Added Missing
- Total Unique Expected
- Total Usable
- Coverage %

The monitor should not silently shrink because data is unavailable.

---

# 6. HISTORICAL PRICE STANDARD

Default historical anchor:

**2020-03-01 through the latest completed session**

For stocks listed after that date, use the first available trading date.

Use adjusted price history consistently when appropriate.

Avoid mixing adjusted and unadjusted historical series in calculations.

Validate:

- splits;
- large discontinuities;
- missing history;
- duplicate dates;
- suspicious zero values;
- incorrect adjustment behavior.

---

# 7. PRIMARY WIN%

Primary Win% measures the stock's location inside its historical price range.

Calculate:

`Primary Win% = (Historical Maximum Close - Current Close) / (Historical Maximum Close - Historical Minimum Close)`

Historical period:

**2020-03-01 → latest completed session**

Interpretation:

Higher Win% means the stock is closer to the lower end of its historical range.

It does NOT automatically mean the stock is undervalued or should be purchased.

A high Win% stock can still be:

- structurally impaired;
- fundamentally deteriorating;
- breaking support;
- losing institutional sponsorship;
- experiencing negative estimate revisions;
- trapped in a weak industry;
- a falling knife.

Display Primary Win% numerically.

---

# 8. 52-WEEK WIN%

Calculate a second location metric using the trailing 52-week high and low:

`52W Win% = (52W High - Current Price) / (52W High - 52W Low)`

Primary Win% and 52W Win% must remain separate.

Primary Win% provides long-range location.

52W Win% provides current-cycle location.

Do not replace one with the other.

---

# 9. PRICE_SUGGEST_80

Retain the historical price reference:

`price_suggest_80 = historical_max - ((historical_max - historical_min) × 0.80)`

Use this as a reference level rather than an automatic Buy price.

---

# 10. PRICE ANCHORS / PERFORMANCE

Calculate where history permits:

- Previous close
- 1-week close / approximately 5 sessions
- 2-week close where useful
- 1-month close / approximately 21 sessions
- 3-month close / approximately 63 sessions
- 6-month close / approximately 126 sessions
- YTD
- 52-week high
- 52-week low
- historical maximum
- historical minimum

Calculate corresponding percentage performance.

Track meaningful recent drops over:

- 1W
- 2W
- 1M
- 3M
- 6M

---

# 11. RSI

Calculate RSI(14).

Basic interpretation:

- RSI < 30 = Oversold
- RSI 30–70 = Neutral
- RSI > 70 = Overbought

Do NOT treat RSI < 30 as an automatic Buy.

An oversold stock breaking support with deteriorating volume remains dangerous.

---

# 12. MOVING AVERAGES

Calculate when sufficient history exists:

- 20-day MA
- 50-day MA
- 100-day MA
- 200-day MA

Also evaluate:

- price relative to each MA;
- slope/direction;
- MA crossovers;
- reclaim/loss of important MAs;
- MA compression;
- whether an MA is acting as support/resistance.

---

# 13. MACD

Calculate MACD using standard:

- EMA 12
- EMA 26
- Signal 9

Track:

- MACD line;
- signal line;
- histogram;
- bullish/bearish crossover;
- histogram improvement/deterioration;
- zero-line relationship.

MACD improvement after a prolonged decline may support a reversal thesis but is not sufficient by itself.

---

# 14. ATR / VOLATILITY

Calculate ATR(14).

Use ATR to evaluate:

- volatility;
- normal trading range;
- support/resistance tolerance;
- stop/invalidation risk;
- position-risk context.

Avoid treating a normal ATR-sized movement as a major technical event.

---

# 15. SUPPORT AND RESISTANCE ENGINE

This is a major component of the monitor.

Calculate **SHORT-TERM support/resistance** using:

- 5–21 day pivots;
- swing highs/lows;
- gaps;
- recent consolidation;
- recent volume areas.

Calculate **INTERMEDIATE/LONG-TERM support/resistance** using:

- 3-month swings;
- 6-month swings;
- 1-year swings;
- 50-day MA;
- 100-day MA;
- 200-day MA;
- anchored VWAP where meaningful;
- high-volume price zones;
- major historical pivots.

Do not limit support/resistance analysis only to the highest-ranked stocks.

Run an **UNCAPPED SUPPORT/RESISTANCE SCANNER across the entire usable universe.**

---

# 16. DISTANCE TO SUPPORT / RESISTANCE

Calculate percentage distance from current price to relevant levels.

Classification:

- **≤2% = Strong Proximity**
- **>2% to 3% = Near**
- **>3% to 5% = Approaching**
- **>5% = Not Near**

Identify when:

- resistance becomes support after breakout;
- support becomes resistance after breakdown.

---

# 17. ACTIONABLE LEVELS

For actionable stocks provide when justified:

- Current Price
- Buy Zone
- Strong Buy level
- Confirmation/Reclaim level
- Short Support
- Major Support
- Invalidation / Stop-Risk level
- Short Resistance
- Major Resistance
- Trim Zone
- Sell/Reduce Zone
- Breakout level
- Next upside target
- Downside %
- Upside %
- Risk/Reward ratio

Do not manufacture false precision.

Use zones where the evidence supports zones rather than a single exact price.

---

# 18. BASING / BOTTOM FORMATION

The monitor must explicitly distinguish a developing bottom from a falling knife.

Evaluate:

- recent range compression;
- 21-day high/low range;
- declining volatility;
- repeated support tests;
- higher lows;
- failed breakdown;
- reclaim of prior support;
- reclaim of 20/50-day MA;
- volume drying up during declines;
- increasing volume on advances;
- OBV improvement;
- relative-strength improvement;
- MACD improvement;
- RSI divergence;
- accumulation;
- sector/subsector improvement.

Historical basing reference:

`recent_range_pct = (21D High - 21D Low) / 21D High`

A range near or below approximately 10% may help identify basing, but this is NOT a sufficient bottom signal by itself.

---

# 19. FALLING-KNIFE DETECTION

Create an explicit Falling Knife / Breakdown Risk assessment.

Warning evidence includes:

- repeated lower lows;
- repeated lower highs;
- price below declining 20/50/200-day averages;
- support levels failing instead of holding;
- expanding downside volume;
- OBV deterioration;
- negative accumulation/distribution;
- weak relative strength;
- deteriorating sector;
- negative earnings revisions;
- worsening fundamentals;
- high short interest combined with deteriorating price;
- failed bounce attempts;
- recent gaps lower;
- inability to reclaim prior support.

Possible classifications:

- Confirmed/Probable Bottom
- Bottom Developing
- Stabilizing
- Unconfirmed Bounce
- Falling-Knife Risk
- Confirmed Breakdown

A high Win% + oversold RSI alone must NEVER override strong Falling-Knife evidence.

---

# 20. DROP-AND-REVERSAL ENGINE

Actively identify stocks that:

1. declined materially from a recent or major high;
2. tested or established support;
3. stopped making major new lows;
4. began rebounding;
5. reclaimed meaningful levels;
6. show improving flow, volume, relative strength, or rotation.

Calculate:

- Drop from Recent High %
- Drop from Major High %
- Recent Low
- Rebound from Recent Low %
- Support Tested?
- Support Held?
- MA Reclaimed?
- Prior Resistance Reclaimed?
- Relative Strength Improving?
- Money Flow Improving?
- Rotation Improving?

Surface **MU-style high → decline → support → rebound patterns** even when Primary Win% is only moderate.

---

# 21. BREAKOUT ENGINE

Identify:

- base breakouts;
- multi-month breakouts;
- resistance breaks;
- MA reclaim breakouts;
- high-volume breakouts.

Require confirmation where possible.

Evaluate:

- breakout volume;
- relative volume;
- breadth/sector confirmation;
- relative strength;
- follow-through;
- resistance-to-support conversion.

Classification examples:

- Confirmed Breakout
- Breakout Watch
- Failed Breakout

---

# 22. BREAKDOWN ENGINE

Identify:

- support failure;
- failed base;
- major MA loss;
- gap breakdown;
- high-volume breakdown;
- relative-strength breakdown.

Classification examples:

- Breakdown Warning
- Confirmed Breakdown
- Falling Knife
- Failed Support Test

---

# 23. RELATIVE STRENGTH

Evaluate stock performance relative to:

- S&P 500;
- sector;
- subsector/industry where reliable.

Evaluate:

- 1M relative strength;
- 3M relative strength;
- 6M relative strength;
- direction/slope;
- inflection from weak to improving;
- deterioration from strong to weak.

Pay particular attention to stocks whose absolute return is still modest but whose relative strength has begun improving.

That can provide an early rotation signal.

---

# 24. VOLUME

Evaluate:

- average volume;
- recent volume;
- relative volume;
- up-day volume;
- down-day volume;
- breakout volume;
- breakdown volume;
- volume contraction during basing.

Price movement without confirming volume should receive lower confidence.

---

# 25. MONEY FLOW

Assign each ticker one of:

- **Entering**
- **Accumulating**
- **Neutral**
- **Distributing**
- **Leaving**

Use evidence such as:

- price/volume behavior;
- relative volume;
- OBV;
- accumulation/distribution;
- breakout/breakdown volume;
- ETF/fund-flow evidence when reliable;
- institutional evidence;
- repeated high-volume advances/declines.

Do not claim exact institutional buying merely because price increased.

---

# 26. OBV / ACCUMULATION-DISTRIBUTION

Calculate OBV when history permits.

Also evaluate accumulation/distribution behavior.

Look for divergences such as:

- price flat/down while OBV rises;
- price rising while OBV deteriorates.

Use divergence as supporting evidence, not standalone proof.

---

# 27. ANCHORED VWAP

Use anchored VWAP where meaningful.

Potential anchors:

- major low;
- major high;
- earnings gap;
- breakout;
- major selloff;
- important market event.

Use AVWAP as potential:

- support;
- resistance;
- institutional cost-basis proxy.

Clearly state the anchor used.

---

# 28. VOLUME-BY-PRICE

When data permits, identify high-volume price zones.

Use them to improve:

- support;
- resistance;
- supply zones;
- demand zones;
- risk/reward.

If reliable data is unavailable, do not fabricate it.

---

# 29. SECTOR / SUBSECTOR / THEME ROTATION

Every stock analysis must include its:

- Sector
- Industry/Subsector
- Important investable theme where relevant

Examples of themes may include:

- AI infrastructure
- Memory/HBM
- Semiconductor equipment
- Optical networking
- Data-center power
- Grid modernization
- Nuclear/power
- Cybersecurity
- Aerospace/defense
- Robotics
- Infrastructure
- Specialty materials

Assign:

**Rotation Score = 1–10**

Use:

- 1M relative strength;
- 3M relative strength;
- breadth;
- participation;
- earnings/fundamental trends;
- catalysts;
- market leadership.

Labels:

- Strong
- Improving
- Neutral
- Weak
- Deteriorating

A stock with strong technicals but a deteriorating industry should receive a lower-confidence setup.

---

# 30. EARLY ROTATION / EMERGING TREND DETECTION

The monitor should not only identify established winners.

Look for early signs that a previously weak or ignored group is beginning to improve.

Potential evidence:

- RS inflection;
- improving 1M versus 3M returns;
- increasing breadth;
- multiple companies participating;
- improving volume;
- positive estimate revisions;
- fundamental/capex catalyst;
- base breakouts;
- prior laggards outperforming parent sector.

This is intended to identify trends similar to memory stocks strengthening before the move becomes obvious.

---

# 31. FUNDAMENTAL ANALYSIS

Evaluate where applicable:

- Market Cap
- Revenue growth
- EPS growth
- Revenue trend
- Earnings trend
- Gross margin
- Operating margin
- FCF
- FCF trend
- Debt
- Net debt/cash
- Debt/equity
- Balance-sheet strength
- Forward P/E
- Price/Sales
- Price/Book where relevant
- EV/EBITDA where relevant
- valuation versus history
- valuation versus sector
- earnings estimate revisions
- earnings surprise trends
- short interest
- days to cover
- upcoming earnings/catalyst risk

Use industry-appropriate metrics.

Do not apply identical valuation standards to every industry.

---

# 32. MARKET-CAP CLASSIFICATION

Distinguish:

### CORE
Market Cap ≥ $2B

### LARGE-CAP OVERLAY
Market Cap ≥ $10B

### SPECULATIVE
Small-cap/high-volatility or otherwise speculative names.

ETFs and crypto-related instruments require asset-appropriate analysis rather than standard corporate fundamentals.

---

# 33. INSIDER ACTIVITY

Evaluate Form 4 activity separately.

Emphasize:

- meaningful open-market insider purchases;
- repeated insider buying;
- cluster buying;
- meaningful open-market selling.

Do not treat:

- option exercises;
- tax withholding;
- routine compensation grants

as equivalent to discretionary insider purchases/sales.

---

# 34. INSTITUTIONAL ACTIVITY

Use reliable evidence such as:

- ownership changes;
- fund flows;
- unusual volume;
- block activity when reliable;
- accumulation patterns;
- 13F reports.

13F DATA IS DELAYED.

Always label it as delayed supporting evidence rather than current real-time institutional flow.

---

# 35. OWNED POSITIONS

When ownership/cost-basis data has been explicitly established and is available to the monitor, calculate:

- Shares
- Cost Basis
- Current Value
- Unrealized Gain/Loss $
- Unrealized Gain/Loss %
- Distance from Support
- Distance from Resistance
- Protection/Trim considerations

Never invent ownership information.

If unavailable, show:

**Ownership/Cost Basis Unavailable**

Do not request:

- Plaid;
- bank accounts;
- brokerage connections;
- Google Drive;
- personal financial connectors

for this monitor unless the user explicitly changes this requirement.

---

# 36. OPPORTUNITY SCORE

Calculate:

**Opportunity Score = 0–100**

Approximate weighting:

- 20% Primary/52W Win% + valuation/location
- 25% Support/Resistance + risk/reward
- 20% Trend/Momentum/Relative Strength
- 20% Fundamentals + earnings/revisions
- 10% Money Flow + institutional/insider evidence
- 5% Market/Sector environment

The implementation may improve normalization but must preserve the conceptual weighting unless explicitly approved.

A high score should require multiple independent confirmations.

---

# 37. SETUP CONFIDENCE

Calculate a separate:

**Setup Confidence = 0–100**

Confidence measures the number and quality of independent confirmations.

Examples:

- support;
- trend;
- volume;
- RS;
- rotation;
- fundamentals;
- revisions;
- flow;
- catalyst;
- valuation;
- risk/reward.

Do not confuse Opportunity Score with Confidence.

---

# 38. OVERALL SIGNAL

Assign one primary signal:

- Strong Buy Zone
- Buy/Accumulate
- Approaching Buy Zone
- Hold/Wait
- Hold for Breakout
- Raise Protection
- Trim Watch
- Sell/Reduce
- Confirmed Breakout
- Drop-and-Reversal Watch
- Breakdown Warning
- Falling Knife

The signal must reflect the complete evidence rather than a single indicator.

---

# 39. QUICK-SCAN TABLE

Start every successful monitor with a scan-friendly table.

Required columns:

| Ticker | Owned/Watch | Current Price | Buy Zone | Primary Win% | 52W Win% | Rotation | Money Flow | Opportunity Score | Setup Confidence | Overall Signal |

Also include or make readily available:

- Cost Basis
- Unrealized %
- Short Support
- Major Support
- Short Resistance
- Major Resistance
- Sell/Trim Zone
- Distance to Key Level
- RSI
- Trend
- Relative Strength
- Drop from Recent/Major High %
- Rebound from Recent Low %
- Insider Signal
- Institutional Signal
- Falling Knife / Bottom Status

---

# 40. COMPLETE MASTER TABLE

Produce a complete master table for **ALL usable monitored tickers**, not only Top 10 names.

Do not hide poor-performing or unattractive stocks merely because they do not rank highly.

The master table is the audit trail for the entire monitor.

---

# 41. REQUIRED RANKED SECTIONS

After the quick-scan summary, provide:

### A. TOP BUY / ACCUMULATE

Best current opportunities.

### B. NEAR SUPPORT / APPROACHING BUY ZONE

Stocks close to technically important support even if they are not top Opportunity Score names.

### C. WINNERS NEAR RESISTANCE

Stocks requiring:

- Hold for Breakout;
- Raise Protection;
- Trim Watch;
- Sell/Reduce.

### D. DROP-AND-REVERSAL

Major declines that have begun establishing credible reversals.

### E. BREAKOUTS

Confirmed and near-confirmed breakouts.

### F. BREAKDOWNS / FALLING KNIVES

Stocks where technical damage remains significant.

### G. OWNED POSITIONS REQUIRING ACTION

Only when ownership data is available.

### H. STRONGEST ROTATION

Stocks benefiting from strong/improving sector/subsector trends.

### I. STRONGEST MONEY FLOW

Entering / Accumulating.

### J. MONEY FLOW WARNINGS

Distributing / Leaving.

### K. LARGEST RECENT DROPS

Preserve this section to catch unusually large selloffs.

---

# 42. LARGE-CAP OPPORTUNITY OVERLAY

Maintain a separate view for stocks with:

**Market Cap ≥ $10B**

Rank approximately the top 25 opportunities using the complete monitor rather than Win% alone.

This is intended to identify high-quality companies that have fallen enough to become interesting even if they have not reached extreme historical Win%.

---

# 43. DISCOVERY ENGINE

The monitor must not remain permanently limited to the existing ticker list.

Search for potentially attractive new names based on:

- high Win%;
- major declines;
- support proximity;
- basing;
- reversal;
- improving RS;
- sector rotation;
- emerging themes;
- unusual accumulation;
- strong fundamentals;
- estimate revisions;
- breakouts;
- quality large-cap pullbacks.

A stock reaching approximately **80%+ Primary Win%** should be eligible for discovery review, but should NOT automatically be added.

---

# 44. DISCOVERY HOLDING PATTERN

Newly discovered stocks should normally enter a temporary candidate/holding state before permanent inclusion.

Track:

- Date discovered
- Reason discovered
- Primary Win%
- 52W Win%
- Support status
- Rotation
- Money Flow
- Fundamentals
- Opportunity Score
- Setup Confidence
- Confirmation progress

Possible statuses:

- Candidate
- Holding Pattern
- Promote to Monitor
- Reject
- Recheck

Promotion should require multiple confirming signals.

This prevents the permanent monitor from becoming cluttered with one-day anomalies.

---

# 45. PROMOTION RULES

A discovery candidate can be promoted when several conditions align, such as:

- high-quality company;
- attractive price location;
- support confirmed;
- basing;
- improving RS;
- favorable rotation;
- accumulation;
- improving estimates;
- attractive risk/reward;
- meaningful catalyst.

Do not require every condition.

Use evidence-based judgment.

Record WHY the ticker was promoted.

---

# 46. REMOVAL RULES

Do not silently delete monitored stocks.

Potential reasons for removal:

- thesis invalidated;
- persistent structural deterioration;
- no longer relevant;
- acquisition/delisting;
- user request;
- repeated data failure requiring investigation.

Maintain an audit trail.

---

# 47. CHANGE DETECTION

Compare each run with the prior successful run.

Highlight:

- newly entered Buy Zone;
- newly approaching Buy Zone;
- newly near support;
- newly near resistance;
- new breakout;
- new breakdown;
- new Falling Knife warning;
- new reversal;
- Rotation upgrade/downgrade;
- Money Flow change;
- Opportunity Score change;
- Setup Confidence change;
- promoted discovery names;
- rejected discovery names.

Focus attention on what CHANGED.

---

# 48. MARKET ENVIRONMENT

Use the broader market as an overlay rather than allowing it to completely override stock-specific evidence.

Consider:

- S&P 500 trend;
- volatility;
- Treasury yields;
- breadth;
- credit;
- sector leadership;
- risk-on/risk-off conditions.

The separate Market Health / Sector Leadership systems may provide useful context where available.

Do not duplicate them unnecessarily.

---

# 49. PROVENANCE

Every important metric should have traceable provenance.

Where practical record:

- data source;
- source date;
- market session;
- calculation window;
- formula;
- fallback source;
- whether data is live/current, delayed, or historical.

Never present delayed information as real time.

---

# 50. VALIDATION

Before publishing:

Validate:

- session freshness;
- universe completeness;
- duplicate symbols;
- price status;
- historical coverage;
- adjusted-price consistency;
- calculation errors;
- impossible values;
- missing values;
- score ranges;
- support < current price when classified as support;
- resistance > current price when classified as resistance;
- rank ordering;
- ticker/company mapping.

Flag exceptions rather than silently correcting uncertain data.

---

# 51. CURRENT-DATE FAILURE BEHAVIOR

If the price freshness gate fails, STOP current technical ranking.

The output should instead prominently state:

**INCOMPLETE — CURRENT-DATE PRICE FEED UNAVAILABLE**

Report:

- expected session;
- latest artifact session;
- workflow status;
- coverage;
- missing symbols;
- likely cause;
- recommended pipeline fix.

Do not generate misleading current Buy/Sell conclusions from old prices.

---

# 52. OUTPUT PHILOSOPHY

The monitor should be useful in approximately three levels:

### LEVEL 1 — 30-SECOND SCAN

Quick table answering:

- What should I look at?
- What changed?
- What requires action?

### LEVEL 2 — RANKED OPPORTUNITIES

Buy, support, resistance, reversal, breakout, breakdown, owned-action lists.

### LEVEL 3 — FULL RESEARCH

Detailed ticker write-ups and complete master table.

Do not bury the actionable information beneath long explanations.

---

# 53. TICKER WRITE-UP FORMAT

For an important ticker, use approximately:

## TICKER — SIGNAL

**Current Price:**  
**Primary Win%:**  
**52W Win%:**  
**Opportunity Score:**  
**Setup Confidence:**  
**Rotation:**  
**Money Flow:**  

**Technical Location:**  
Describe support, resistance, trend, MA structure and basing.

**Bottom vs Falling Knife:**  
Explain the evidence.

**Fundamentals:**  
Summarize quality, valuation, growth, revisions and balance sheet.

**Sector/Theme:**  
Explain rotation and relevant catalysts.

**Money Flow / Institutional / Insider:**  
Summarize reliable evidence.

**Buy Zone:**  
**Strong Buy:**  
**Confirmation:**  
**Invalidation:**  
**Resistance:**  
**Trim/Sell Zone:**  
**Upside:**  
**Downside:**  
**Risk/Reward:**  

**Action:**  
Strong Buy Zone / Buy / Accumulate / Wait / Hold / Hold for Breakout / Raise Protection / Trim / Sell / Avoid.

**Why:**  
Provide a concise evidence-based explanation.

---

# 54. IMPORTANT DECISION RULES

Never make these mistakes:

### HIGH WIN% ≠ AUTOMATIC BUY

High Win% only indicates price location.

### OVERSOLD ≠ AUTOMATIC BUY

Oversold stocks can become more oversold.

### SUPPORT ≠ SUPPORT UNTIL IT HOLDS

A theoretical level must be tested against actual price behavior.

### LOW VALUATION ≠ VALUE

Fundamental deterioration can justify lower valuation.

### INSTITUTIONAL OWNERSHIP ≠ CURRENT BUYING

Separate ownership from current accumulation.

### 13F ≠ REAL TIME

Always identify its delay.

### BREAKOUT ≠ CONFIRMED WITHOUT FOLLOW-THROUGH

Evaluate volume and follow-through.

### ONE-DAY SECTOR MOVE ≠ ROTATION

Require broader evidence.

### RECENT DECLINE ≠ REVERSAL

Require stabilization and confirmation.

---

# 55. BOTTOM VS FALLING-KNIFE FRAMEWORK

When a stock has fallen materially, explicitly score the following evidence.

## PRICE STRUCTURE

Positive:

- low holds;
- higher low;
- resistance reclaim;
- failed breakdown;
- MA reclaim.

Negative:

- repeated lower lows;
- failed bounces;
- support failures.

## VOLUME

Positive:

- selling volume contracts;
- buying volume expands.

Negative:

- downside volume expands.

## MOMENTUM

Positive:

- RSI divergence;
- MACD improving;
- momentum stabilizing.

Negative:

- momentum continues deteriorating.

## RELATIVE STRENGTH

Positive:

- stock begins outperforming market/sector.

Negative:

- RS continues making lows.

## MONEY FLOW

Positive:

- OBV/accumulation improving.

Negative:

- distribution continues.

## FUNDAMENTALS

Positive:

- estimates stabilize/improve;
- catalyst remains intact.

Negative:

- estimates/growth deteriorate.

## ROTATION

Positive:

- sector/subsector improves.

Negative:

- capital continues leaving the group.

Use these to determine:

**BOTTOM CONFIDENCE = 0–100**

and classify:

- 80–100: Strong bottom evidence
- 65–79: Bottom developing / favorable
- 50–64: Stabilization but confirmation needed
- 35–49: Weak/unconfirmed bounce
- <35: Falling-knife / breakdown risk

Do not mechanically calculate this without judgment. The score should reflect independent confirmations.

---

# 56. RISK MANAGEMENT

The monitor should prioritize asymmetric risk/reward.

A stock may be attractive when:

- downside to validated support is relatively limited;
- upside to meaningful resistance/target is substantially greater;
- fundamentals remain acceptable;
- technical deterioration has stopped.

A stock may remain unattractive even after a huge decline if there is no definable invalidation point.

---

# 57. CODING / IMPLEMENTATION RULES

Codex is authorized to:

- refactor code;
- improve runtime;
- improve caching;
- improve APIs/data providers;
- add tests;
- improve workflow reliability;
- improve calculations;
- improve reports;
- modularize the project;
- add logging;
- improve error handling.

Codex is NOT authorized to silently:

- remove metrics;
- change formulas;
- shrink the ticker universe;
- weaken freshness checks;
- remove validation;
- eliminate discovery logic;
- change scoring philosophy;
- replace Primary Win%;
- eliminate 52W Win%;
- change required outputs.

If a requested technical improvement conflicts with this specification, flag the conflict before implementing the change.

---

# 58. TESTING REQUIREMENTS

Create automated tests for important calculations.

At minimum test:

- Primary Win%
- 52W Win%
- price_suggest_80
- RSI
- MACD
- ATR
- moving averages
- support/resistance distance
- historical period selection
- adjusted-price handling
- universe reconciliation
- duplicate detection
- stale-price detection
- current-session gate
- Opportunity Score range
- Setup Confidence range
- Bottom Confidence range

Include edge cases for:

- IPO after 2020;
- missing history;
- split;
- zero-range high/low;
- missing current price;
- holiday/weekend;
- stale workflow;
- duplicated ticker.

---

# 59. PERFORMANCE

The monitor should be efficient enough to run daily after market close.

Avoid unnecessary repeated API calls.

Prefer:

- bulk price downloads;
- caching;
- incremental updates;
- local historical store;
- retries/backoff;
- parallelization where safe.

Fundamental data does not need to be downloaded repeatedly when unchanged.

Price freshness, however, must never be sacrificed merely to make the run faster.

---

# 60. DAILY EXECUTION TARGET

The intended monitor schedule is approximately:

**5:00 PM U.S. Central Time on U.S. trading weekdays**

At execution:

1. Determine latest completed U.S. market session.
2. Find latest successful price workflow artifact.
3. Run freshness gate.
4. Audit universe.
5. Validate prices/history.
6. Calculate technical metrics.
7. Update fundamentals where required.
8. Calculate rotation/flow.
9. Calculate scores.
10. Run support/resistance scanner.
11. Run bottom/falling-knife engine.
12. Run reversal engine.
13. Run breakout/breakdown engine.
14. Run discovery engine.
15. Compare against prior run.
16. Generate quick scan.
17. Generate ranked sections.
18. Generate complete master table.
19. Save provenance/audit information.

---

# 61. SOURCE-OF-TRUTH RULE

THIS FILE IS THE AUTHORITATIVE FUNCTIONAL SPECIFICATION FOR THE STOCK BUY/SELL MONITOR.

When implementing changes:

**DO NOT REMOVE EXISTING REQUIREMENTS UNLESS THE USER EXPLICITLY APPROVES THEIR REMOVAL.**

New requirements should normally be additive.

When two requirements conflict:

1. identify the conflict;
2. explain the impact;
3. recommend the better approach;
4. obtain approval before deleting established functionality.

Maintain backwards compatibility with existing monitor requirements whenever reasonably possible.

---

# 62. CONTINUOUS IMPROVEMENT

The objective is not merely to reproduce a static spreadsheet.

The long-term system should become increasingly capable of identifying:

- quality stocks near attractive entry levels;
- legitimate bottoms;
- falling knives to avoid;
- early reversals;
- major pullbacks in strong companies;
- emerging sector leadership;
- institutional accumulation;
- breakouts;
- deteriorating owned positions;
- sell/trim opportunities;
- newly developing investment themes.

When improving the system, prioritize **decision usefulness, data reliability, explainability, and risk management** over adding large numbers of weak indicators.

The final question the system should help answer is:

**“Given price location, technical structure, fundamentals, rotation, money flow, market environment, upside/downside and confirmation—what should I do with this stock now, and what evidence would cause that decision to change?”**