# 📖 The Ultimate Guide to NEPSE Floorsheet Visual Analytics

> *A comprehensive, beginner-friendly manual explaining every metric, chart, and feature in the institutional Broker Visual Analytics Suite.*

---

## 🌟 1. Introduction & Purpose

When trading on the **Nepal Stock Exchange (NEPSE)**, tens of thousands of individual transactions occur daily across 300+ listed companies and 60+ brokerage firms. 

The traditional **Raw Floorsheet** view is a linear table of raw transactions (Contract ID, Symbol, Buyer Broker, Seller Broker, Qty, Rate, Amount). While accurate, making sense of 70,000+ raw trades manually is overwhelming.

The **NEPSE Floorsheet Visual Analytics Suite** (`visual.html`) solves this by acting as an institutional intelligence layer. It aggregates and cross-analyzes millions of data points from CockroachDB to reveal:
- Which brokers dominate market turnover.
- Which stocks are being aggressively **accumulated (net bought)** or **distributed (net sold)**.
- The **exact time of day** major buying or selling surges occurred.
- The **counterparty network**: which brokers traded with each other.

---

## 🧭 2. Core Navigation & Layout

At the top of every page, the shared navigation bar allows seamless switching between:
- **`📄 Raw Floorsheet` (`index.html`)**: Tabular search, filtering, and paging through raw trade contracts.
- **`📈 Broker Visual Analytics` (`visual.html`)**: Interactive dashboard with macro KPIs, broker matrix leaderboard, timeline charts, and counterparty intelligence.

---

## 🔍 3. Key Concepts & Metric Definitions

Understanding the math and terminology behind each metric is essential for accurate market analysis:

### 1. Market Turnover vs. Broker Gross Activity
- **Market Turnover (NPR)**: The actual total value of all shares traded on the exchange.
  $$\text{Market Turnover} = \sum \text{Transaction Amount}$$
- **Broker Gross Activity (NPR)**: The total transaction volume processed by a specific broker on both the buy side and sell side.
  $$\text{Gross Activity} = \text{Total Buy Turnover} + \text{Total Sell Turnover}$$
- **Broker Market Share (%)**: How much of the total trading book this broker handled.
  $$\text{Market Share \%} = \frac{\text{Gross Activity}}{2 \times \text{Market Turnover}} \times 100$$

---

### 2. Net Flow Value & Net Flow Quantity (Accumulation vs. Distribution)
Floorsheet data captures *observed transaction flow* during a trading session.

- **Net Flow Quantity**: Total shares bought minus total shares sold for a broker or scrip.
  $$\text{Net Flow Qty} = \text{Buy Qty} - \text{Sell Qty}$$
- **Net Flow Value (NPR)**: Total monetary value bought minus total monetary value sold.
  $$\text{Net Flow Value} = \text{Buy Value} - \text{Sell Value}$$

#### What does it mean?
- **🟢 ACCUMULATING (Net Bought)**: $\text{Buy Value} > \text{Sell Value}$ (Positive Net Flow). The broker absorbed more shares from the market than they released.
- **🔴 DISTRIBUTING (Net Sold)**: $\text{Sell Value} > \text{Buy Value}$ (Negative Net Flow). The broker unloaded/sold more shares to the market than they purchased.

> [!NOTE]
> *Important Distinction*: Net Flow indicates buying/selling pressure *during the selected time period*. It does not represent the broker's historical inventory holdings before that session.

---

### 3. Net Flow % and Buy/Sell Ratio
- **Net Flow %**: The directional bias of the broker's activity relative to their total volume.
  $$\text{Net Flow \%} = \frac{\text{Buy Value} - \text{Sell Value}}{\text{Buy Value} + \text{Sell Value}} \times 100$$
  - $+50\%$ means the broker was heavily skewed toward buying.
  - $-50\%$ means the broker was heavily skewed toward selling.
  - Near $0\%$ indicates balanced two-way turnover (churn / market making).

- **Buy / Sell Ratio**:
  $$\text{Buy/Sell Ratio} = \frac{\text{Buy Value}}{\text{Sell Value}}$$
  - **Ratio > 1.0**: Net buyer.
  - **Ratio < 1.0**: Net seller.
  - **Ratio = 1.0**: Balanced turnover.

---

## 📊 4. The Master Broker Matrix (Leaderboard)

The main leaderboard table ranks every active broker on NEPSE with 12 real-time columns:

| Column Header | Description | Why It Matters |
|---|---|---|
| **Broker** | TMS Broker Number (e.g., `#58`, `#45`, `#28`). | Identifies the brokerage firm executing the trades. |
| **Gross Activity** | Total Buy + Sell turnover handled by this broker. | Identifies the most active institutional and retail hubs. |
| **Buy Turnover** | Gross NPR amount of all buy-side contracts. | Shows capital inflow generated through this broker. |
| **Sell Turnover** | Gross NPR amount of all sell-side contracts. | Shows capital outflow / liquidation through this broker. |
| **Net Flow** | Buy Turnover minus Sell Turnover. Green (`+`) for net buying; Red (`-`) for net selling. | Reveals whether the broker ended the day as a net capital absorber or releaser. |
| **Net Flow %** | Percentage intensity of the directional bias. | Standardizes comparison between small and large brokers. |
| **Buy/Sell Ratio** | Ratio of Buy value to Sell value. | Quick metric for one-sided vs two-sided activity. |
| **Top Bought Scrip** | The scrip where this broker spent the most capital. | Shows where buyer demand was concentrated. |
| **Top Sold Scrip** | The scrip where this broker sold the most capital. | Shows where selling pressure originated. |
| **Top Accumulation (Net+)** | The scrip with the highest positive net volume and value. | Highlights the specific stock this broker accumulated most aggressively. |
| **Top Distribution (Net-)** | The scrip with the highest negative net volume and value. | Highlights the specific stock this broker liquidated most aggressively. |
| **Action** | `[🔍 Deep Dive]` button. | Opens the complete institutional drilldown drawer for that broker. |

---

## ⏱️ 5. Intraday Session Presets & Time Filtering

NEPSE trading sessions run from 11:00 AM to 3:00 PM NPT. Institutional orders often concentrate at specific times. The filter panel offers quick preset chips:

- **Full Session**: Complete trading day (`11:00:00 - 15:00:00`).
- **Opening Hour (11-12)**: Captures opening price discovery and initial volatility.
- **Mid-Day (12-14)**: Captures sustained accumulation or mid-session consolidation.
- **Closing Hour (14-15)**: Captures end-of-day block executions and closing momentum.
- **Custom Time Range**: Precise minute-level start and end time pickers for surgical analysis.

---

## 🔬 6. Deep Broker Drilldown Intelligence (The Institutional Drawer)

Clicking on any broker row or the `[🔍 Deep Dive]` button opens a dedicated full-screen drawer providing 4 analytical perspectives:

### 1. Broker KPI Executive Summary
- **Gross Activity**: Total volume.
- **Total Buy / Sell**: High-level buy vs sell totals in compact format (e.g., `B: 27.7 Cr | S: 25.1 Cr`).
- **Net Flow Value**: Net capital balance with directional percentage.
- **Buy / Sell Ratio**: Buy-to-sell multiplier.
- **Peak Trading Window**: The exact time bucket where this broker traded the highest volume (e.g., `13:30 - 13:45`).

---

### 2. Intraday Velocity & Flow Timeline Chart
A dynamic **Chart.js** visualization displaying:
- **Green Bars**: Buy Turnover across time buckets.
- **Red Bars**: Sell Turnover across time buckets.
- **Blue Trend Line**: Net Flow velocity ($Buy - Sell$).
- **Configurable Time Buckets**: Toggle between `5m`, `15m`, `30m`, and `1h` granularities.

---

### 3. Complete Traded Scrips Portfolio
A comprehensive table listing every individual stock traded by this broker during the session:
- **Symbol**: Stock ticker (e.g., `SHIVM`, `NABIL`, `SONA`).
- **Buy Qty & Sell Qty**: Total shares bought and sold.
- **Net Flow Qty**: Net share accumulation or distribution.
- **Buy Value & Sell Value**: Total NPR turnover on both sides.
- **Net Flow (NPR)**: Net monetary flow into or out of the stock.
- **Avg Buy & Avg Sell Rates**: Volume-Weighted Average Price (VWAP) for this broker's buy and sell executions.
- **Flow Status Badge**: `🟢 ACCUMULATING` vs `🔴 DISTRIBUTING`.
- **Search Filter**: Search box to instantly filter specific symbols.

---

### 4. Counterparty Supply & Absorption Network
Floorsheet contracts pair a buyer broker with a seller broker. This section reveals the **counterparty relationship matrix**:
- **Top Counterparties Bought From (Supply Sources)**:
  - Which brokers supplied the shares this broker bought.
  - Columns: Counter Broker, Total Amount, Quantity, Trades Count, and **Buy Share %** (e.g., *Broker #45 supplied 35.2% of Broker #58's buys*).
- **Top Counterparties Sold To (Absorption Sinks)**:
  - Which brokers bought the shares this broker sold.
  - Columns: Counter Broker, Total Amount, Quantity, Trades Count, and **Sell Share %** (e.g., *Broker #34 absorbed 41.0% of Broker #58's sells*).

---

## 📥 7. Data Export & CSV Generation

- Click **📥 Export Matrix CSV** on the top right to download the complete broker matrix for the selected date and time window.
- The CSV file is formatted for instant analysis in Excel, Google Sheets, or Python/Pandas.

---

## ❓ 8. Frequently Asked Questions (FAQ)

### Q: Why does Market Turnover not equal the sum of all brokers' Gross Activity?
Because every trade has two sides (one buyer and one seller). The sum of all brokers' Gross Activity is exactly **twice** the market turnover.

### Q: Does a positive Net Flow mean the broker made a profit?
No. Net Flow represents net capital flow (Buy Value minus Sell Value) during that session. It does not measure realized profit or loss.

### Q: How often is the visual data updated?
The database is updated automatically after market close every trading day (Mon–Fri at 17:00 NPT) via automated GitHub Actions pipelines.

---

*Authored with ❤️ by **Your Zara** for **Jagdish Sah** and the NEPSE trading community.*
