# 📋 NEPSE Scrip Analytics Suite — Review, Improvements & Feature Upgrade Specification

> **Document Type:** CLI Agent Review & Upgrade Instructions  
> **Target:** `api/script.py`, `public/script.html`, `public/script.js`, database/query architecture, routing, documentation  
> **Status:** REVIEW REQUIRED BEFORE CODING  
> **Source:** Review of the current `Script_Plan.md` / Master Blueprint  
> **Date:** September 2026

---

# 1. Purpose of This Document

This document is intended to be given directly to the CLI coding/analysis agent.

The current Scrip Analytics blueprint is conceptually strong, but it should **not be implemented blindly**. The agent must first analyze the existing blueprint against the corrections, architectural improvements, data-semantics safeguards, performance requirements, and additional features defined below.

The goal is to produce a revised, technically defensible implementation plan before writing production code.

The agent must:

1. Analyze the current blueprint.
2. Identify where the existing design is correct.
3. Identify contradictions, technical risks, scalability concerns, and data-interpretation risks.
4. Incorporate the required improvements below where appropriate.
5. Propose any additional improvements that are logically justified.
6. Produce a revised implementation architecture.
7. Only after the analysis and revised plan are internally consistent should implementation begin.

**Important:** Do not simply agree with this document. Verify every recommendation against the actual repository, schema, existing APIs, database access patterns, and current implementation.

---

# 2. Product Vision

The Scrip Analytics Suite is the third analytical pillar of the platform:

```text
Raw Floorsheet
      ↓
Broker Analytics
      ↓
Scrip Analytics
```

The product should answer questions such as:

- Which brokers are most active in a particular scrip?
- Which brokers are net buyers or net sellers?
- How concentrated is buying/selling activity?
- How does broker activity evolve during the trading session?
- Where are unusually large trades occurring?
- Which broker-to-broker counterparties dominate trading?
- Does price movement align with or diverge from observed broker flow?
- Is today's activity unusually large compared with the stock's historical behavior?

The platform should remain primarily an **observational market-intelligence and analytics system**, not a prediction or trading-signal engine.

---

# 3. Executive Assessment of the Current Blueprint

## 3.1 Strong Areas

The following concepts from the current blueprint are good and should generally be retained:

- Market-wide scrip leaderboard.
- Deep scrip drilldown.
- Date selector and session filters.
- Custom time ranges.
- Turnover and volume filters.
- VWAP.
- Intraday timeline.
- Broker participation matrix.
- Counterparty network.
- Whale/block trade scanner.
- CSV export.
- Shared navigation between Raw Floorsheet, Broker Analytics, and Scrip Analytics.
- Separate frontend/backend files.
- Documentation and verification phase.

## 3.2 Main Weaknesses Identified

The current blueprint has several areas that should be corrected before implementation:

1. It sometimes treats broker net activity as proof of actual accumulation/distribution.
2. It sometimes uses language implying a broker can be proven to be controlling or moving a stock's price.
3. The `<100 ms` database performance statement is too definitive without benchmarking.
4. The existing `idx_symbol_time(symbol, trade_time)` index is ideal for deep scrip queries but is not the natural index for market-wide queries filtered primarily by time.
5. The market-wide overview query performs substantial aggregation work and may become expensive as raw floorsheet history grows.
6. A single deep endpoint returning every analytical module may produce unnecessarily large JSON responses.
7. Whale thresholds based only on fixed quantity/value are not equally meaningful across different stock prices and liquidity levels.
8. The `Impact` field needs an explicit measurable definition and should not imply causal market impact unless the available data supports that conclusion.
9. There is no explicit data-integrity/completeness layer in the current architecture.
10. Historical context, unusual-activity detection, flow persistence, turnover velocity, price/flow divergence, and broker rotation are missing.

---

# 4. Mandatory Data-Semantics Corrections

This section is critical.

## 4.1 Do Not Equate Net Buying With Proven Accumulation

Current concept:

```text
🟢 ACCUMULATING
🔴 DISTRIBUTING
```

Recommended terminology:

```text
🟢 NET BUYING
🔴 NET SELLING
```

Reason:

A broker's floorsheet activity represents executed broker-level transactions. It does not, by itself, prove the underlying client's investment intention, beneficial ownership, or long-term accumulation/distribution behavior.

The system may derive higher-level inference metrics, but such labels must be clearly presented as **inferences**, not facts.

Example:

```text
Observed:
Net Qty = +83,000

Derived:
Strong Buy-Side Participation

Optional interpretation:
Potential Accumulation Pattern
```

Do not silently collapse these three layers into one.

---

# 5. Separate Facts, Derived Analytics, and Interpretations

The system should conceptually use three layers.

## 5.1 Observed Facts

Examples:

- Buy quantity.
- Sell quantity.
- Net quantity.
- Buy value.
- Sell value.
- Net value.
- Trade count.
- Rate.
- VWAP.
- High/Low.
- Broker participation.
- Counterparty pair.
- Trade size.
- Trade time.

## 5.2 Derived Analytics

Examples:

- Flow Bias.
- Broker Concentration.
- HHI.
- Flow Persistence.
- Turnover Velocity.
- Relative Activity.
- Relative Trade Size.
- Unusual Trade Score.
- Price/Flow Divergence.
- Broker Rotation.

## 5.3 Interpretations

Examples:

- Potential Accumulation.
- Potential Distribution.
- High Institutional-Like Activity.
- Concentrated Participation.
- Unusual Broker Participation.
- Potential Rotation.

The UI should make it clear which category a metric belongs to.

---

# 6. Correct the "Price Control / Price Driver" Language

Avoid claims such as:

```text
Which broker is controlling this stock?
Which broker is driving the price?
```

unless the specific methodology genuinely supports causal claims.

Prefer wording such as:

```text
Which brokers contribute most to observed buying/selling activity?
Which brokers account for the largest share of traded flow?
Which broker activity coincides with notable price movement?
```

The system should describe observable relationships rather than claim intent or causality that the data cannot prove.

---

# 7. Database and Indexing Architecture Improvements

## 7.1 Existing Index

The current blueprint proposes:

```sql
CREATE INDEX idx_symbol_time
ON floorsheet_raw (symbol ASC, trade_time ASC);
```

Retain this concept for deep scrip queries such as:

```sql
WHERE symbol = ?
AND trade_time >= ?
AND trade_time <= ?
```

## 7.2 Market-Wide Query Problem

The overview query primarily filters by:

```sql
WHERE trade_time >= ?
AND trade_time <= ?
```

The existing `(symbol, trade_time)` index is not naturally optimized for a scan whose leading predicate is time.

The agent should investigate whether a complementary strategy such as:

```sql
(trade_time, symbol)
```

would materially improve the market-wide query.

Do **not** create indexes blindly. Use real query plans and benchmark evidence.

## 7.3 Required Verification

For important queries, inspect:

```sql
EXPLAIN ANALYZE ...
```

and review:

- Rows scanned.
- Rows returned.
- KV operations.
- KV bytes.
- Sorting.
- Index joins.
- Memory use.
- Execution time.
- Whether the optimizer actually chooses the intended index.

The specification must not claim a universal `<100 ms` response unless that has been demonstrated under a representative production-like dataset and workload.

Replace absolute claims with measurable targets, for example:

```text
Target: <100 ms for symbol/time queries under the expected production workload.
Validation: EXPLAIN ANALYZE + representative load testing.
```

---

# 8. Consider Pre-Aggregated Analytics Tables

The current overview query performs large aggregations directly over raw floorsheet data.

As the database grows, repeatedly recalculating the same daily summaries may become unnecessarily expensive.

The agent should evaluate a derived-data architecture such as:

## 8.1 Daily Scrip Aggregate

Suggested conceptual structure:

```text
scrip_daily_summary
-------------------
date
symbol
trade_count
total_volume
total_turnover
high_price
low_price
close_price
vwap
```

## 8.2 Daily Scrip Broker Aggregate

Suggested conceptual structure:

```text
scrip_broker_daily
------------------
date
symbol
broker_id
buy_qty
sell_qty
net_qty
buy_value
sell_value
net_value
buy_vwap
sell_vwap
```

## 8.3 Why

This allows common dashboard reads to work against relatively small aggregate datasets rather than repeatedly scanning a large raw table.

The agent must compare:

```text
Raw-query architecture
vs
Pre-aggregated architecture
vs
Hybrid architecture
```

and recommend the simplest design that meets expected workload requirements.

Do not introduce unnecessary complexity merely because aggregation tables sound sophisticated.

---

# 9. API Architecture Improvements

The existing endpoints are:

```text
GET /api/script/overview
GET /api/script/{symbol}
GET /api/script/dates
```

These are acceptable as a starting point, but the deep endpoint should be examined for over-fetching.

Recommended conceptual decomposition:

```text
GET /api/script/dates

GET /api/script/overview

GET /api/script/{symbol}/summary
GET /api/script/{symbol}/timeline
GET /api/script/{symbol}/brokers
GET /api/script/{symbol}/counterparties
GET /api/script/{symbol}/whales
```

## 9.1 Lazy Loading

The UI should load the summary first and request expensive modules only when required.

For example:

```text
Open SHIVM
   ↓
Summary
   ↓
Load timeline
   ↓
Load brokers
   ↓
Load counterparties when tab opened
   ↓
Load whale trades when tab opened
```

This reduces initial payload size and improves responsiveness.

## 9.2 Pagination

Large result sets should be paginated.

Example:

```text
/api/script/SHIVM/whales?page=1&limit=100
```

Apply similar pagination where needed to:

- Whale trades.
- Counterparty pairs.
- Large broker matrices.
- Other potentially unbounded results.

---

# 10. API Response Metadata

Responses should include useful metadata.

Suggested conceptual format:

```json
{
  "date": "2026-08-31",
  "symbol": "SHIVM",
  "filters": {
    "start": "11:00",
    "end": "15:00"
  },
  "data": [],
  "meta": {
    "generated_at": "...",
    "trade_count": 1420,
    "partial": false,
    "source": "floorsheet_raw"
  }
}
```

The exact schema may differ after repository inspection.

---

# 11. Data Integrity and Completeness Layer

Add a validation step before analytics are calculated.

Validate where applicable:

```text
quantity > 0
rate > 0
amount ≈ quantity × rate
buyer_broker != null
seller_broker != null
trade_time is valid
contract identifiers are not unexpectedly duplicated
```

Detect/report anomalies such as:

- Duplicate trade rows.
- Missing broker identifiers.
- Invalid values.
- Invalid timestamps.
- Negative quantities/amounts.
- Impossible/future timestamps.
- Unexpected gaps.

Do not silently turn bad data into seemingly precise analytics.

---

# 12. Data Completeness Indicator

The UI should visibly distinguish between complete and incomplete datasets.

Examples:

```text
🟢 Complete Session
🟡 Partial Data
🔴 Incomplete / Unavailable
```

For live or partially ingested sessions, make it obvious that the ranking is based only on the currently available data.

Example:

```text
Data Status: 🟡 Partial Session
Last Update: 13:42:18
```

---

# 13. Improve the Dates Endpoint

Instead of returning only a list of dates, consider returning useful summary metadata.

Conceptual example:

```json
[
  {
    "date": "2026-08-31",
    "trade_count": 154320,
    "symbols": 287,
    "turnover": 9850000000,
    "status": "complete"
  }
]
```

This allows the frontend to display meaningful context and distinguish complete from partial sessions.

---

# 14. Broker Metrics

For each broker in a scrip, retain the proposed matrix and improve it with clear definitions.

Recommended columns:

```text
Broker
Buy Qty
Sell Qty
Net Qty
Buy Value
Sell Value
Net Value
Buy VWAP
Sell VWAP
Flow Share
Status
```

Potential calculated metric:

```text
Net Flow = Buy Value - Sell Value
```

## 14.1 Broker VWAP

Calculate separately:

```text
Buy VWAP  = Buy Value / Buy Qty
Sell VWAP = Sell Value / Sell Qty
```

This can reveal whether a broker's observed buying and selling occurred at materially different average prices.

---

# 15. Broker Concentration: Add HHI

Keep the existing Top-3 concentration concept:

```text
Top 3 Buy Concentration
```

but add Herfindahl-Hirschman Index (HHI):

```text
HHI = Σ(s_i²)
```

where `s_i` is the broker's share of the selected activity universe, expressed consistently according to the chosen metric.

The agent must define exactly whether HHI is based on:

- Buy volume.
- Buy value.
- Sell volume.
- Total activity.

Do not mix definitions across screens.

Potential UI labels:

```text
Low Concentration
Moderate Concentration
High Concentration
Extreme Concentration
```

Thresholds must be documented.

---

# 16. Add Flow Persistence

Measure whether observed net flow remains directionally consistent over time buckets.

Example:

```text
11:00–11:30   BUY
11:30–12:00   BUY
12:00–12:30   BUY
12:30–13:00   BUY
13:00–13:30   SELL
```

Potential metric:

```text
Flow Persistence: 80%
```

The agent must define the calculation mathematically and document the limitations.

This is more informative than a single end-of-day net number.

---

# 17. Add Turnover Velocity

Add time-normalized activity metrics such as:

```text
Turnover / minute
Volume / minute
Peak 5-minute turnover
Peak 15-minute turnover
```

This distinguishes:

```text
steady activity throughout the session
```

from:

```text
short bursts of intense activity
```

Potential visualization:

```text
Turnover Velocity
▁▂▃▃▅▆█▇▃▂
```

---

# 18. Add Relative Activity

Absolute turnover alone is insufficient for comparing different stocks.

Add historical relative metrics such as:

```text
Today's Volume / Historical Average Volume
Today's Turnover / Historical Average Turnover
```

Example:

```text
Volume: 2.8× 20D Average
```

The lookback period should be configurable or explicitly documented.

---

# 19. Redesign the Whale / Block Scanner

The existing fixed thresholds:

```text
> 1,000 shares
> NPR 500,000
```

should not be the only detection mechanism.

Different stocks have radically different prices and typical trade sizes.

Implement multiple scanner modes where practical:

## 19.1 Value Whale

```text
Amount >= user threshold
```

## 19.2 Volume Whale

```text
Quantity >= user threshold
```

## 19.3 Relative Whale

```text
Trade Size >= X × median trade size
```

or a similar statistically defensible metric.

## 19.4 Percentile-Based Whale

Example:

```text
Trade Size >= 95th / 99th percentile
```

The thresholds and method must be documented.

---

# 20. Add Unusual Trade Detection

A trade can be noteworthy because it is abnormal for the stock/session, even when its absolute value is not huge.

Potential logic:

```text
trade_amount > 95th percentile
```

or:

```text
trade_amount > 3 × median_trade_amount
```

The exact method must be chosen based on robustness and available data.

UI example:

```text
🐋 Unusual Trade
```

Do not imply that an unusual trade is necessarily institutional.

Use wording such as:

```text
Unusually Large Relative to Observed Session Activity
```

---

# 21. Redesign the "Impact" Field

Do not claim:

```text
Trade caused price movement
```

unless the dataset and methodology support that inference.

Instead calculate measurable post-trade context.

For example:

```text
Trade Rate: 518.20
5m Later: 519.00
15m Later: 520.10
30m Later: 519.40
```

Potential field name:

```text
Post-Trade Price Change
```

or:

```text
Price Context
```

This should be explicitly described as correlation/context, not proven causation.

---

# 22. Add Price/Flow Divergence

Detect cases where observed price direction and broker-flow direction diverge.

Examples:

```text
Price ↑
Net Broker Flow ↓
```

or:

```text
Price ↓
Net Broker Flow ↑
```

Flag as:

```text
⚠️ Price/Flow Divergence
```

This is an analytical observation, not a reversal prediction.

---

# 23. Add Broker × Time Flow Timeline

The current broker table gives only aggregate results.

Allow a broker row to be expanded/clicked to inspect activity through time.

Conceptual example:

```text
Broker #58
------------------------
11:05   +5,000
11:20   +8,000
11:45  +12,000
12:10   -2,000
12:45  +17,000
...
```

This creates a useful:

```text
Broker × Scrip × Time
```

dimension.

---

# 24. Counterparty Network: Make This a Major Feature

The counterparty section is one of the most distinctive parts of the platform and should be developed carefully.

For every trade:

```text
Buyer Broker
Seller Broker
Quantity
Rate
Amount
Time
```

Aggregate direct routes such as:

```text
#28 → #58
42,000 shares
NPR X
Average Rate X
```

Recommended metrics:

```text
Top Counterparty Pair
Largest Supply Route
Largest Demand Route
Pair Volume
Pair Value
Pair Trade Count
Pair Share of Scrip Activity
Pair VWAP
```

Potential network visualization:

```text
              #28
             /   \
            ↓     ↓
         #58     #45
          ↑       ↑
          |       |
         #12     #33
```

Avoid implying collusion, coordination, or intent merely because two brokers trade repeatedly with one another.

---

# 25. Add Session Flow Analysis

Retain:

```text
Full Session
Opening Hour
Mid-Day
Closing Hour
Custom
```

Add comparative session metrics such as:

```text
Opening vs Mid-Day
Mid-Day vs Closing
Opening Flow Bias
Closing Flow Bias
Peak Session
```

This helps identify activity concentrated near the open or close.

---

# 26. Add Historical Comparison

The dashboard should eventually answer:

> Has this activity happened before?

Useful comparison windows:

```text
5D
20D
60D
```

Examples:

```text
Broker #58 Activity
Today: 83,000 shares
20D Average: 21,000
Relative Activity: 3.95×
```

Historical periods must exclude the current session where appropriate and clearly document the lookback methodology.

---

# 27. Add Broker Rotation Detection

Detect meaningful changes in the dominant brokers participating in a scrip across sessions.

Conceptual example:

```text
Monday     #58 dominant
Tuesday    #58 dominant
Wednesday  #28 enters
Thursday   #45 enters
Friday     #58 declines
```

Potential output:

```text
🔄 Broker Rotation Detected
```

The agent must define a quantitative rule for what qualifies as meaningful rotation.

---

# 28. Add a Scrip-Level Intelligence Score Carefully

A composite score may be added in a later phase.

Potential components:

```text
Broker Concentration
Large Trade Frequency
Flow Persistence
Counterparty Concentration
Relative Trade Size
Net Flow
Turnover Velocity
Historical Relative Activity
```

Example:

```text
Institutional Activity Score
82 / 100
```

However, the score must never become a black box.

Always expose the contributing components:

```text
Institutional Activity: 82

Concentration       +18
Whale Activity      +21
Flow Persistence    +16
Broker Bias         +14
Turnover Velocity   +13
```

Do not add the score to Version 1 unless the methodology is stable and explainable.

---

# 29. Add Market-Wide Scrip Discovery Views

The overview page should support multiple ranking modes.

Recommended views:

```text
🔥 Most Active
💰 Highest Turnover
📈 Highest Net Buying
📉 Highest Net Selling
🐋 Most Unusual Large Trades
🏢 Highest Broker Concentration
⚡ Highest Turnover Velocity
🔄 Highest Broker Rotation
```

These should operate on the same underlying query/data layer where practical.

---

# 30. Add a Market-Wide Scrip Flow Heatmap

A visual heatmap can make the overview page much more useful than a table alone.

Potential dimensions:

```text
Rows   = Scrips
Columns = Flow / Concentration / Activity metrics
```

Or a simpler quadrant such as:

```text
                 Broker Concentration
              Low                High
Net Buy       🟢                 🟢🔥
Neutral       ⚪                 🟡
Net Sell      🔴                 🔴🔥
```

The visualization must remain interpretable and not overwhelm the leaderboard.

---

# 31. Add a Human-Readable Flow Summary

Under the KPI cards, show a concise generated summary based only on measured metrics.

Example:

```text
Flow Summary:
Buying is concentrated among Brokers #58, #45 and #12, while #28 and #16 account for most observed selling. Activity intensified during the final hour.
```

The text should never invent intent.

Prefer language such as:

```text
observed buying
observed selling
concentrated activity
activity intensified
```

over:

```text
Broker is secretly accumulating
Broker is manipulating price
Broker is preparing a breakout
```

---

# 32. Advanced Filters

Retain:

```text
Date
Session
Custom Time
Symbol
Minimum Turnover
```

Add where useful:

```text
Minimum Trades
Minimum Volume
Minimum Whale Count
Broker Concentration
Flow Bias
Relative Volume
Relative Turnover
```

Allow combined filtering, for example:

```text
Turnover > 1 Cr
AND
Whale Count > 5
AND
Top-3 Buy Concentration > 50%
```

Do not make the filter system so complex that it becomes unusable.

---

# 33. Frontend Information Hierarchy

The deep-dive modal/drawer should prioritize clarity.

Recommended structure:

```text
┌─────────────────────────────────────────┐
│ SHIVM                                  │
│ Rs 14.5 Cr | 280k | VWAP 518.40       │
└─────────────────────────────────────────┘

┌────────────┬──────────────┬────────────┐
│ Flow Bias  │ Concentration│ Whale Act. │
│   +18%     │     64%      │    HIGH    │
└────────────┴──────────────┴────────────┘

FLOW SUMMARY
────────────

PRICE + VWAP
────────────

BUY / SELL FLOW
────────────

BROKER PARTICIPATION
────────────

COUNTERPARTY NETWORK
────────────

WHALE / UNUSUAL TRADES
────────────
```

Do not present every metric at the same visual priority.

---

# 34. Recommended MVP Feature Set (P0)

These should be considered core Version 1 functionality:

```text
1. Scrip leaderboard.
2. Date/session filtering.
3. Custom time filtering.
4. Turnover / volume / trade count.
5. VWAP.
6. High / Low / Close or LTP where source data supports it.
7. Top observed net-buying broker.
8. Top observed net-selling broker.
9. Broker participation matrix.
10. Broker buy/sell/net values.
11. Broker buy/sell VWAP.
12. Intraday price + volume timeline.
13. Counterparty aggregation.
14. Basic large-trade scanner.
15. Data completeness indicator.
16. API pagination where required.
17. CSV export.
18. Input/output validation.
19. Query plan verification.
20. Responsive frontend integration.
```

---

# 35. Recommended P1 Features

Implement after the core system is stable:

```text
1. HHI concentration.
2. Flow persistence.
3. Turnover velocity.
4. Relative volume.
5. Relative turnover.
6. Dynamic whale thresholds.
7. Unusual-trade detection.
8. Price/flow divergence.
9. Broker × time timeline.
10. Historical comparison.
11. Broker rotation detection.
12. Market-wide ranking modes.
13. Flow heatmap.
14. Flow summary text.
```

---

# 36. Recommended P2 Features

Advanced features for later iterations:

```text
1. Institutional Activity Score.
2. Historical broker fingerprints.
3. Cross-day broker behavior profiles.
4. Scrip similarity analysis.
5. Accumulation/distribution regime classification.
6. Anomaly detection engine.
7. Automated session classification.
8. Alerts.
9. Broker-scrip relationship graph.
10. Advanced historical pattern discovery.
```

These should not delay the initial working product.

---

# 37. Features to Explicitly Avoid in Version 1

Do not immediately add:

```text
BUY SIGNAL
SELL SIGNAL
ENTRY
TARGET
STOP LOSS
PRICE WILL RISE
PRICE WILL FALL
MANIPULATION DETECTED
INSIDER ACTIVITY CONFIRMED
```

unless a future methodology is developed that can genuinely support such claims.

The first release should remain an evidence-driven market analytics system.

---

# 38. Suggested Revised System Architecture

The agent should evaluate an architecture along these lines:

```text
                    ┌──────────────────────┐
                    │   Raw Floorsheet     │
                    │    floorsheet_raw    │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │ Data Validation Layer│
                    └──────────┬───────────┘
                               │
                 ┌─────────────┴──────────────┐
                 │                            │
       ┌─────────▼──────────┐      ┌─────────▼──────────┐
       │ Daily Scrip Agg    │      │ Scrip Broker Agg   │
       │                    │      │                    │
       │ turnover           │      │ buy_qty            │
       │ volume             │      │ sell_qty           │
       │ high/low           │      │ net_qty            │
       │ VWAP               │      │ buy/sell value     │
       └─────────┬──────────┘      └─────────┬──────────┘
                 │                           │
                 └────────────┬──────────────┘
                              │
                    ┌─────────▼──────────┐
                    │ Analytics Engine   │
                    │                    │
                    │ HHI                │
                    │ concentration      │
                    │ whale detection     │
                    │ flow persistence    │
                    │ velocity            │
                    │ divergence          │
                    └─────────┬──────────┘
                              │
                      ┌───────▼───────┐
                      │ REST API      │
                      └───────┬───────┘
                              │
                ┌─────────────▼─────────────┐
                │       script.js           │
                └─────────────┬─────────────┘
                              │
       ┌──────────────────────┼──────────────────────┐
       │                      │                      │
   Leaderboard            Deep Dive             Networks
       │                      │                      │
   Scrip Matrix          Timeline              Counterparty
                         Brokers                Whale Scanner
```

This is a **reference architecture**, not a command to force unnecessary tables into the repository. The agent must inspect the current system and choose the simplest reliable implementation.

---

# 39. Query Architecture Requirements

For each major endpoint/query, the agent must document:

```text
Purpose
Inputs
Indexes used
Expected cardinality
Aggregation strategy
Sort strategy
Pagination strategy
Caching/aggregation strategy
Expected response size
Failure behavior
```

At minimum, analyze:

```text
/api/script/overview
/api/script/{symbol}/summary
/api/script/{symbol}/timeline
/api/script/{symbol}/brokers
/api/script/{symbol}/counterparties
/api/script/{symbol}/whales
/api/script/dates
```

---

# 40. Performance Requirements

Do not make unsupported performance guarantees.

Instead define measurable targets.

Example:

```text
Symbol deep-query target:
<100 ms under representative production-like conditions.

Overview target:
Defined after benchmark because it depends on dataset size and aggregation strategy.

Large-response endpoints:
Must use pagination or bounded result sets.
```

All targets should be validated with actual queries and representative data.

---

# 41. Security / Reliability Considerations

The agent should inspect the current repository for:

- SQL parameterization.
- Input validation.
- Symbol sanitization.
- Date/time validation.
- Pagination limits.
- Maximum query windows.
- Error handling.
- Rate limiting if applicable.
- Accidental leakage of internal database errors.
- Excessive query payloads.

Never construct SQL by directly concatenating untrusted user input.

---

# 42. Frontend Requirements

The dashboard should support:

```text
Responsive dark theme.
Shared navigation.
Fast initial load.
Lazy-loading of heavy sections.
Sortable tables.
Search/filter controls.
Loading indicators.
Empty states.
Error states.
Partial-data states.
CSV export.
Accessible interactive controls.
```

The agent should reuse existing project patterns from `visual.html`, `visual.js`, and `styles.css` wherever practical rather than inventing a disconnected UI system.

---

# 43. Documentation Requirements

Update or create:

```text
Explain_script.md
README.md
Script_Plan.md or its replacement
```

Documentation must explain:

- Data source.
- Definitions of all metrics.
- VWAP formula.
- Net flow formula.
- Concentration formula.
- HHI methodology.
- Whale methodology.
- Unusual-trade methodology.
- Flow persistence methodology.
- Turnover velocity methodology.
- Price/flow divergence methodology.
- Historical lookback assumptions.
- What the data can prove.
- What the data cannot prove.

The documentation should explicitly distinguish **observation from interpretation**.

---

# 44. Testing Requirements

The agent must propose tests for:

## Backend

```text
Endpoint correctness.
Date filtering.
Time filtering.
Symbol filtering.
Minimum turnover filtering.
Pagination.
Empty result sets.
Invalid dates.
Invalid symbols.
Partial data.
VWAP correctness.
Broker net-flow correctness.
Counterparty aggregation correctness.
Whale detection correctness.
```

## Database

```text
EXPLAIN ANALYZE.
Index utilization.
Large date-range performance.
Single-symbol performance.
Large-result pagination.
```

## Frontend

```text
Leaderboard rendering.
Sorting.
Filtering.
Modal/drawer opening.
Chart rendering.
Lazy loading.
Export.
Empty/error/partial states.
```

---

# 45. Acceptance Criteria for the Revised Blueprint

Before coding, the CLI agent should produce a revised blueprint that clearly answers:

1. What are the final endpoints?
2. What is the final database/query strategy?
3. Which indexes are actually required and why?
4. Which computations run on raw data?
5. Which computations run on aggregates?
6. Which analytics are facts versus inferences?
7. How is broker concentration calculated?
8. How is a whale defined?
9. How is an unusual trade defined?
10. How is flow persistence calculated?
11. How is price/flow divergence calculated?
12. How is broker rotation detected?
13. How are incomplete sessions represented?
14. How is pagination handled?
15. How are large responses controlled?
16. What are the measurable performance targets?
17. How will those targets be benchmarked?
18. What is included in P0, P1, and P2?
19. Which proposed features are rejected and why?
20. What risks remain after the revision?

---

# 46. Required CLI Agent Workflow

The agent should follow this sequence.

## Step 1 — Inspect the Repository

Inspect:

```text
api/index.py
api/visual.py
public/index.html
public/visual.html
public/visual.js
public/styles.css
vercel.json
existing DB schema/migrations
existing database helper code
README.md
```

Also inspect any tests or deployment configuration relevant to these components.

## Step 2 — Inspect Existing Data Model

Determine:

```text
Exact columns.
Data types.
Nullability.
Existing indexes.
Approximate row counts if available.
Existing date ranges.
Existing ingestion behavior.
```

Do not assume the schema described in this specification exactly matches the live repository.

## Step 3 — Validate the Blueprint Against Reality

Identify:

```text
What can already be reused.
What conflicts with the current backend.
What requires schema changes.
What can be implemented without migration.
What might become a performance problem.
```

## Step 4 — Produce a Revised Architecture

Provide:

```text
Endpoint design.
SQL/query design.
Index design.
Aggregation strategy.
Frontend architecture.
Caching/lazy-loading strategy.
Testing strategy.
```

## Step 5 — Rank Features

Classify every proposed feature as:

```text
P0 = required for MVP
P1 = strong next step
P2 = advanced/future
REJECT = unnecessary / unsafe / unsupported / premature
```

## Step 6 — Challenge the Recommendations

The agent should explicitly disagree with recommendations when repository evidence indicates they are unnecessary or harmful.

For each rejected recommendation, explain why.

## Step 7 — Only Then Implement

Implementation should follow the revised plan rather than the original blueprint if the analysis shows the revision is superior.

---

# 47. Desired Final Output From the CLI Agent

Before coding, the agent should return something structurally similar to:

```text
# Scrip Analytics Architecture Review

## 1. Current Blueprint Assessment
- Strengths
- Risks
- Contradictions

## 2. Repository Findings
- Existing schema
- Existing indexes
- Existing APIs
- Reusable frontend components

## 3. Revised Data Architecture
- Raw tables
- Aggregate tables if needed
- Index strategy

## 4. Revised API Architecture
- Endpoints
- Parameters
- Pagination
- Response format

## 5. Analytics Definitions
- VWAP
- Net Flow
- HHI
- Whale detection
- Unusual activity
- Flow persistence
- Turnover velocity
- Divergence
- Rotation

## 6. Frontend Architecture
- Overview
- Deep Dive
- Lazy loading
- Charts
- Tables

## 7. Feature Priorities
- P0
- P1
- P2
- Rejected

## 8. Testing & Benchmarking

## 9. Risks & Limitations

## 10. Final Recommendation
```

Only after this review is internally coherent should implementation begin.

---

# 48. Final Product Principle

The most important principle for this project is:

> **Be analytically ambitious, but epistemically honest.**

The platform should extract as much useful information as possible from the floorsheet data, while never presenting an inference as a proven fact.

The intended progression is:

```text
RAW DATA
   ↓
OBSERVED ACTIVITY
   ↓
DERIVED ANALYTICS
   ↓
INTERPRETATION
```

not:

```text
RAW DATA
   ↓
MAGICAL GREEN BUY SIGNAL 🚀
```

The first version should prioritize correctness, transparency, explainability, performance, and a strong user experience.

The long-term goal is to evolve toward a powerful:

```text
Broker ↔ Scrip ↔ Time ↔ Price ↔ Flow
```

intelligence graph while preserving clear boundaries between measured facts and inferred behavior.

---

# ✅ Instruction to the CLI Agent

**Analyze the original Scrip Analytics blueprint together with this upgrade specification. Inspect the actual repository and database before making implementation decisions. Do not blindly follow either document. Resolve contradictions, verify assumptions, challenge unnecessary complexity, and produce a revised architecture that is technically justified. Then implement the revised plan in a clean, maintainable way with tests and performance verification.**
