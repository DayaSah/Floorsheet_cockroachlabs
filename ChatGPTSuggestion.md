# ARCHITECTURE REVIEW INSTRUCTIONS — NEPSE FLOORSHEET VISUAL ANALYTICS

I want you to review and revise the existing `Visualplan.md` architecture for the NEPSE Floorsheet Broker Visualization Suite **before writing or modifying any application code**.

The original proposal is directionally correct, but several analytical definitions need to be corrected to avoid presenting transaction-flow data as facts about broker holdings, profits, or intentions.

Your task is to incorporate the following architectural corrections into the plan.

---

## 1. CRITICAL: Do NOT call Net Quantity "Holding"

The floorsheet only tells us about transactions observed during the selected period.

For a broker and scrip:

```text
Net Flow Qty = Buy Qty - Sell Qty
Net Flow Value = Buy Value - Sell Value
```

A positive net quantity means **net buying / accumulation flow during the selected period**.

It does NOT prove that the broker currently holds that quantity.

Therefore:

### Replace:

- Top Holding
- Holding (Net+)
- Top Released
- Released (Net-)
- Dumping

### With:

- Top Accumulation
- Top Distribution
- Net Bought
- Net Sold

Preferred terminology:

```text
ACCUMULATION
Net Buy Qty: +95,000

DISTRIBUTION
Net Sell Qty: -60,000
```

Do not describe these metrics as actual inventory holdings unless an independent holdings dataset exists.

---

# 2. Clearly distinguish Market Turnover from Broker Activity

A single transaction has one market value, but appears on both sides of broker activity.

Example:

```text
Buyer #58 → NPR 10M
Seller #45 → NPR 10M
Actual Market Turnover → NPR 10M
```

Therefore:

### Market Turnover

```text
SUM(transaction_amount)
```

### Broker Buy Value

```text
SUM(amount where broker is buyer)
```

### Broker Sell Value

```text
SUM(amount where broker is seller)
```

### Broker Gross Activity

```text
Buy Value + Sell Value
```

Do NOT call:

```text
Buy Value + Sell Value
```

"Market Turnover."

Prefer the term:

```text
Gross Activity
```

for the broker-level metric.

The API schema should use explicit names such as:

```json
{
  "buy_value": 0,
  "sell_value": 0,
  "gross_activity": 0,
  "net_flow_value": 0
}
```

Avoid ambiguous fields such as simply `total_turnover` where possible.

---

# 3. Rename "Net Amount" to "Net Flow Value"

`Net Amount` can easily be mistaken for profit/loss.

Define:

```text
Net Flow Value = Buy Value - Sell Value
```

This is NOT:

- Profit
- Loss
- Return
- P/L

Use:

```text
net_flow_value
net_flow_qty
```

throughout the backend and frontend.

---

# 4. Top Bought/Sold Must Distinguish Quantity vs Value

The original plan says "Top Bought Scrip by Volume & Amount", but this is ambiguous.

Example:

| Scrip | Buy Qty | Buy Value |
|---|---:|---:|
| A | 100,000 | NPR 1 Cr |
| B | 50,000 | NPR 2 Cr |

A is the top by quantity.

B is the top by value.

Therefore the API should expose separate metrics:

```json
{
  "top_bought_by_qty": {},
  "top_bought_by_value": {},

  "top_sold_by_qty": {},
  "top_sold_by_value": {},

  "top_accumulation_by_qty": {},
  "top_accumulation_by_value": {},

  "top_distribution_by_qty": {},
  "top_distribution_by_value": {}
}
```

The frontend may visually prioritize one metric but must not merge quantity and value into one ambiguous ranking.

---

# 5. Counterparty Analysis Is a Core Feature

Keep the counterparty analysis and consider it one of the most important features.

For a selected broker:

```text
Bought From:
Broker #45
Broker #28
...

Sold To:
Broker #34
Broker #19
...
```

The system should aggregate:

```text
counterparty broker
transaction value
quantity
trade count
top symbol
```

Percentages must have an explicit denominator.

For example:

```text
Broker #45
NPR 5.4 Cr
35.2% of Broker #58 Buy Value
```

Do not display simply:

```text
Broker #45 (35%)
```

because it is ambiguous whether that means percentage of:

- buy value
- sell value
- quantity
- total activity
- market turnover

Prefer fields such as:

```text
buy_value_share_pct
sell_value_share_pct
buy_qty_share_pct
sell_qty_share_pct
```

where useful.

---

# 6. Broker Deep Dive Should Prefer a Dedicated View / Drawer

Do not make the complete broker analysis a huge modal.

The preferred UX hierarchy is:

```text
Market Overview
      ↓
Broker Leaderboard
      ↓
Select Broker
      ↓
Broker Deep Dive
      ├── Summary
      ├── Scrip Flow
      ├── Intraday Timeline
      └── Counterparties
```

A lightweight drawer may be used for quick inspection, but the full analytical view should not depend on a giant modal.

---

# 7. Simplify the Initial API Design

For V1, prefer fewer consolidated endpoints instead of unnecessarily splitting every component into its own API call.

Recommended structure:

```text
GET /api/visual/overview
```

Parameters:

```text
date
start_time
end_time
min_activity
```

Returns:

```text
market_summary
broker_matrix
```

And:

```text
GET /api/visual/broker/{broker_id}
```

Parameters:

```text
date
start_time
end_time
bucket
```

Returns:

```text
broker_summary
scrips
timeline
counterparties
```

A future symbol endpoint can be added:

```text
GET /api/visual/symbol/{symbol}
```

Do not over-engineer V1 unless actual performance testing proves the need for separate endpoints.

---

# 8. Add Useful Broker Metrics

For each broker, consider calculating:

### Buy/Sell Ratio

```text
Buy Value / Sell Value
```

Interpretation:

```text
> 1 → relatively more buy-side activity
< 1 → relatively more sell-side activity
≈ 1 → relatively balanced activity
```

Do NOT interpret this as a prediction of price direction.

### Net Flow Percentage

```text
(Buy Value - Sell Value)
/
(Buy Value + Sell Value)
× 100
```

This makes brokers with different activity sizes easier to compare.

Example:

```text
Buy Value: 28.45 Cr
Sell Value: 19.52 Cr

Net Flow: +8.93 Cr
Net Flow %: +18.6%
```

### Activity Intensity

Where possible:

```text
Trades per time bucket
Quantity per time bucket
Value per time bucket
```

Also identify:

```text
Peak Activity Window
```

---

# 9. Improve Intraday Timeline

The backend should support configurable time buckets.

At minimum:

```text
5 minutes
15 minutes
30 minutes
1 hour
```

Frontend controls can provide:

```text
[5m] [15m] [30m] [1h]
```

The timeline should support:

```text
Buy Value
Sell Value
Net Flow Value
Trade Count
Quantity
```

The user should be able to see whether activity occurred mainly:

```text
Early session
Mid session
Late session
```

Do not restrict the architecture permanently to fixed 30-minute buckets.

---

# 10. Broker Name Dictionary

The database may store broker IDs such as:

```text
58
45
28
```

The UI should show:

```text
58 · Naasa Securities
```

while preserving the broker number prominently.

Do not hard-code broker names throughout JavaScript.

Use a centralized mapping such as:

```text
broker_map.json
```

or a dedicated database table if appropriate.

The implementation must verify the correct broker names from a reliable source rather than blindly using examples from the proposal.

---

# 11. Important: Observed Data vs Analytical Interpretation

The application must distinguish between what is directly observed and what is inferred.

### Observed

```text
Broker #58
SHIVM
Buy Qty: 120,000
Sell Qty: 25,000
Net Flow Qty: +95,000
```

### Derived

```text
Accumulation Flow
```

### Interpretation

```text
Potential Accumulation
```

Do NOT claim from floorsheet data alone:

- institutional accumulation
- smart money
- manipulation
- dumping intent
- guaranteed future price movement
- actual broker inventory
- broker profit/loss

Use careful terminology such as:

```text
Observed Net Buying
Potential Accumulation
Observed Net Selling
Potential Distribution
```

The tool is an analytics system, not an oracle wearing a Bloomberg terminal costume.

---

# 12. Add Data Quality / Verification Information

Because all analytics depend on the underlying floorsheet dataset, consider exposing:

```text
Transactions analyzed
Unique brokers
Unique scrips
Missing timestamps
Date coverage
Time coverage
```

Example:

```text
Data Quality

Transactions: 124,521
Brokers: 62
Scrips: 318
Missing timestamps: 0
Coverage: Full trading session
```

If the underlying data is incomplete, the UI should not silently present the analytics as complete.

---

# 13. Database Schema Must Be Verified Before SQL Implementation

Before writing aggregation queries, inspect the actual `floorsheet_raw` table.

Verify at minimum:

```text
contract_id
date
time
symbol
buyer
seller
quantity
rate
amount
```

Confirm:

1. Whether `amount` already exists.
2. Whether one row represents one transaction/contract.
3. Whether duplicate records exist.
4. Actual data types.
5. Actual date/time representation.
6. Whether broker IDs are integers or strings.
7. Whether timestamps contain timezone information.
8. Whether buyer/seller values can be NULL.
9. Whether transaction amounts/quantities can be zero or invalid.

Do NOT assume the schema from the planning document.

---

# 14. Database Index Strategy Must Be Based on Actual Queries

The current proposal mentions indexes such as:

```text
idx_buyer_time
idx_seller_time
idx_symbol_time
```

Before adding or changing indexes, inspect actual query plans.

The analytics queries will likely filter by:

```text
date
time
buyer
seller
symbol
```

Potential composite indexes may involve:

```text
(date, time)
(date, buyer, time)
(date, seller, time)
(date, symbol, time)
```

But these should NOT automatically be created.

Use:

```text
EXPLAIN
```

and actual query performance to determine the appropriate indexes.

Avoid premature database optimization.

---

# 15. Future Symbol Intelligence

Do not necessarily implement this in V1, but design the architecture so the reverse analytical flow is possible:

```text
Symbol
  ↓
Top Net Buyers
  ↓
Top Net Sellers
  ↓
Broker Activity
  ↓
Counterparties
  ↓
Intraday Flow
```

Potential future endpoint:

```text
GET /api/visual/symbol/{symbol}
```

Example:

```text
SHIVM — 2026-08-31

Top Net Buyers:
#58  +95K
#45  +80K
#28  +61K

Top Net Sellers:
#34  -105K
#19  -71K
```

Keep this as a future extension, not a requirement for V1.

---

# 16. Recommended Final Architecture

Use this conceptual architecture:

```text
                    NEPSE FLOORSHEET
                           │
             ┌─────────────┴─────────────┐
             │                           │
       RAW FLOORSHEET              VISUAL ANALYTICS
             │                           │
       index.html                  visual.html
             │                           │
       api/index.py                visual.js
                                         │
                              ┌──────────┼──────────┐
                              │          │          │
                           Market     Broker     Symbol
                              │          │          │
                              └──────────┼──────────┘
                                         │
                                    visual.py
                                         │
                              ┌──────────┴──────────┐
                              │                     │
                         Aggregation SQL        Analytics
                              │                     │
                              └──────────┬──────────┘
                                         │
                                    CockroachDB
                                         │
                                  floorsheet_raw
```

The desired analytical flow is:

```text
DATE
 ↓
MARKET OVERVIEW
 ↓
BROKER LEADERBOARD
 ↓
BROKER DEEP DIVE
 ↓
SCRIPTS
 ↓
ACCUMULATION / DISTRIBUTION
 ↓
INTRADAY TIMELINE
 ↓
COUNTERPARTIES
```

---

# 17. Revised Priority

Build features in this order:

### P0 — Required

```text
Broker Matrix
Broker Deep Dive
Scrip Flow
Counterparty Analysis
Date + Time Filtering
Data Validation
```

### P1 — Important

```text
Intraday Timeline
Broker Name Dictionary
Buy/Sell Ratio
Net Flow %
Activity Intensity
Configurable Time Buckets
```

### P2 — Future

```text
Symbol Intelligence
Network Graph
Advanced anomaly detection
Cross-day broker behavior
Broker flow history
```

Avoid spending development time on excessive animations or cosmetic complexity before analytical correctness is verified.

---

# 18. Your Task Right Now

Do NOT modify any application files yet.

First:

1. Inspect the repository.
2. Inspect the actual database-related code and schema assumptions.
3. Compare the existing implementation with this revised architecture.
4. Identify contradictions, missing fields, or assumptions.
5. Propose the final API contracts.
6. Propose the SQL aggregation strategy.
7. Propose any required database indexes, but only with justification.
8. Propose the frontend state/data-flow architecture.
9. Update `Visualplan.md` if appropriate.
10. Clearly list what you verified versus what still requires confirmation.

After completing this review, STOP.

Do not implement `visual.py`, `visual.html`, `visual.js`, database migrations, or `vercel.json` changes until the revised architecture has been reviewed and approved.

The primary objective is:

> **Build a technically correct broker transaction-flow analytics system, not merely a visually impressive dashboard.**