# 📖 The Master Guide to NEPSE Scrip (Stock) Analytics

> *A comprehensive, beginner-friendly manual explaining every metric, chart, and feature in the institutional NEPSE Scrip Analytics Suite.*

---

## 🌟 1. Introduction & Purpose

When analyzing stocks on the **Nepal Stock Exchange (NEPSE)**, understanding who is participating in a specific stock is critical for making informed market decisions.

While **Broker Analytics** tracks the market-wide portfolio of a single brokerage firm, **Scrip Analytics** (`script.html`) flips the lens to focus entirely on **individual stocks (e.g. SHIVM, NABIL, SONA, HDL)**.

It answers key questions:
- Which stocks are seeing the highest turnover and institutional volume?
- Which brokers are the dominant **net buyers** vs **net sellers** in a stock?
- At what average execution prices (**Buy VWAP** vs **Sell VWAP**) did brokers trade?
- How concentrated is buying volume (e.g., *are 3 brokers controlling 65% of all buying volume?*)?
- At what exact times of the day did **large block / whale trades** execute?
- What are the direct **broker-to-broker trade routes** (who supplied the stock to whom)?

---

## 🧭 2. Global Navigation

The platform provides a unified top navigation bar across all three views:
- **`📄 Raw Floorsheet` (`index.html`)**: Search, filter, and page through raw transaction records.
- **`🏢 Broker Analytics` (`visual.html`)**: Analyze brokerage firms' market share, portfolio allocations, and trading timelines.
- **`📊 Scrip Analytics` (`script.html`)**: Deep dive into individual stocks, broker concentration, VWAP curves, and block deals.

---

## 🔍 3. Core Concepts & Metric Definitions

### 3.1. LTP vs. VWAP (Volume-Weighted Average Price)
- **LTP (Last Traded Price)**: The price of the very last executed contract for the stock in the session.
- **VWAP (Volume-Weighted Average Price)**: The true weighted average price at which all shares were traded throughout the session:
  $$\text{VWAP} = \frac{\sum (\text{Quantity} \times \text{Rate})}{\sum \text{Quantity}}$$
- **Why it matters**: If LTP is trading above VWAP, buyers have been willing to pay higher prices late in the session. If LTP is below VWAP, the stock faced selling pressure toward the close.

---

### 3.2. Broker Buy VWAP vs. Sell VWAP
For every broker that traded a stock, the system calculates their separate execution averages:
- **Buy VWAP**: Average price at which this broker *bought* shares.
  $$\text{Buy VWAP} = \frac{\text{Buy Value}}{\text{Buy Quantity}}$$
- **Sell VWAP**: Average price at which this broker *sold* shares.
  $$\text{Sell VWAP} = \frac{\text{Sell Value}}{\text{Sell Quantity}}$$
- **Why it matters**: Reveals whether a broker was accumulating at lower levels and unloading at higher levels, or vice versa.

---

### 3.3. Net Flow & Flow Status (`🟢 NET BUYING` / `🔴 NET SELLING`)
Floorsheet data captures observed transaction flow during the selected window:
- **Net Flow Quantity**: Total shares bought minus total shares sold ($\text{Buy Qty} - \text{Sell Qty}$).
- **Net Flow Value (NPR)**: Total money spent buying minus total money received selling ($\text{Buy Value} - \text{Sell Value}$).
- **🟢 NET BUYING**: $\text{Buy Value} > \text{Sell Value}$ (The broker absorbed more shares than they released).
- **🔴 NET SELLING**: $\text{Sell Value} > \text{Buy Value}$ (The broker released more shares to the market than they bought).

---

### 3.4. Top 3 Buyer Concentration (%)
- **Formula**:
  $$\text{Top 3 Buyer Share \%} = \frac{\text{Volume Bought by Top 3 Buyers}}{\text{Total Stock Volume}} \times 100$$
- **Interpretation**:
  - **$\ge 50\%$ (High Concentration)**: Buying volume is heavily driven by 1 to 3 dominant institutional brokers.
  - **$< 30\%$ (Dispersed / Retail Flow)**: Buying is scattered across dozens of different retail brokers.

---

## 📊 4. The Master Scrip Leaderboard

The main table ranks all stocks traded on NEPSE for the selected date and time window:

| Column | Description |
|---|---|
| **Symbol** | Stock ticker / symbol (e.g., `SHIVM`, `NABIL`). |
| **Turnover (NPR)** | Total transaction value with market share %. |
| **Volume (Shares)** | Total quantity of shares exchanged. |
| **Trades** | Total number of executed contracts. |
| **LTP (NPR)** | Last Traded Price of the session. |
| **VWAP (NPR)** | Volume-Weighted Average Price. |
| **Price Range** | Low price to High price spread ($Low - High$). |
| **Top Net Buyer Broker** | Broker with highest net buy volume (e.g. `Broker #58 (+45,000)`). |
| **Top Net Seller Broker** | Broker with highest net sell volume (e.g. `Broker #28 (-38,000)`). |
| **Top 3 Buyer Share %** | Institutional concentration percentage. |
| **Action** | `[🔍 Deep Dive]` button to open full stock intelligence. |

---

## 🔬 5. Deep Scrip Intelligence (The Stock Drawer)

Clicking on any stock row opens the dedicated institutional drilldown drawer:

### 1. Executive Summary KPIs
- **Turnover & Shares**: Total liquidity.
- **LTP & VWAP**: Closing price vs Volume-Weighted benchmark.
- **Price Range (High - Low)**: Intraday price volatility spread.
- **Top 3 Buyer Concentration**: Institutional accumulation density.
- **Peak Volume Window**: Exact time bucket when volume spiked (e.g., `14:45`).

---

### 2. Dual-Axis Intraday Price & Volume Flow Chart (Chart.js)
- **Left Y-Axis (Price)**: High, Low, and VWAP price trajectory across time buckets (`5m`, `15m`, `30m`, `1h`).
- **Right Y-Axis (Volume)**: Bar chart showing trading volume velocity in each time bucket.
- **Time Calibration**: Exact NEPSE session window (`10:45 AM` pre-open to `15:00 PM` close).

---

### 3. Broker Participation & Net Flow Matrix
A complete table ranking every broker active in this stock:
- Broker #, Buy Qty, Sell Qty, Net Qty, Buy Turnover, Sell Turnover, Net Flow (NPR), **Buy VWAP**, **Sell VWAP**, and Flow Status (`🟢 NET BUYING` / `🔴 NET SELLING`).
- Instant broker search filter input.

---

### 4. Direct Counterparty Deal Routes (Supply Pairs)
Reveals the direct trade routes:
- **Route (Buyer ➔ Seller)**: Which broker bought from which seller.
- **Amount & Qty**: Value and share count of the direct pair.
- **Route VWAP**: Average price of contracts between these two specific brokers.
- **Share %**: Percentage of the stock's total turnover executed through this pair.

---

### 5. 🐋 Whale & Block Trade Scanner
Instantly identifies large, high-value transaction tickets:
- **Threshold Filters**:
  - `All Whales (Qty >= 1,000 OR Value >= Rs 5 Lakh)`
  - `Qty >= 1,000 shares`
  - `Qty >= 5,000 shares`
  - `Value >= Rs 5 Lakh`
  - `Value >= Rs 10 Lakh`
- **Columns**: Trade Time, Contract ID, Buyer Broker ➔ Seller Broker, Quantity, Rate, Amount (NPR).

---

## 📥 6. CSV Export & Downloads

- Click **📥 Export Scrips CSV** at the top right to download the complete scrip matrix for the selected date and time window.
- The file is formatted for instant analysis in Excel, Google Sheets, or Python/Pandas.

---

*Authored with endless dedication and ❤️ by **Your Zara** for **Jagdish Sah** and the NEPSE trading community.*
