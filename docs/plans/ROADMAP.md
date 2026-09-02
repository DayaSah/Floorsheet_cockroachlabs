# 🗺️ NEPSE Floorsheet Scraper — Master Roadmap & Documentation

## 🎯 Project Overview
Automated ETL pipeline designed to scrape NEPSE (Nepal Stock Exchange) floorsheet transaction data from the ShareHub API, perform high-throughput bulk insertion into CockroachDB (PostgreSQL-compatible distributed database), and reconcile data integrity against independent live feeds (NepseAlpha).

---

## 📊 CockroachDB Database Schema

### Table: `floorsheet_raw`
| Column Name | Data Type | Nullable | Description |
|---|---|---|---|
| `contract_id` | `BIGINT` | `NOT NULL` | Unique transaction ID (Primary Key) |
| `symbol` | `VARCHAR` | `NOT NULL` | Stock ticker symbol (e.g. `SHIVM`, `SONA`) |
| `buyer_broker` | `BIGINT` | `NOT NULL` | Purchasing broker member ID |
| `seller_broker` | `BIGINT` | `NOT NULL` | Selling broker member ID |
| `quantity` | `BIGINT` | `NOT NULL` | Number of shares transacted |
| `rate` | `NUMERIC` | `NOT NULL` | Price per share |
| `amount` | `NUMERIC` | `NOT NULL` | Total transaction value |
| `trade_time` | `TIMESTAMPTZ` | `NOT NULL` | UTC/NPT timestamp of transaction |

### Indexes
- `floorsheet_raw_pkey`: Unique B-Tree index on `(contract_id ASC)`
- `idx_symbol_time`: B-Tree index on `(symbol ASC, trade_time ASC)`
- `idx_buyer_time`: B-Tree index on `(buyer_broker ASC, trade_time ASC)`
- `idx_seller_time`: B-Tree index on `(seller_broker ASC, trade_time ASC)`

---

## 🌐 External APIs & Parameter Specifications

### 1. Primary Ingestion Source: ShareHub API
- **Base Endpoint**: `https://sharehubnepal.com/live/api/v2/floorsheet`
- **Query Parameters**:
  | Parameter | Type | Required | Notes |
  |---|---|---|---|
  | `page` | Integer | Yes | 1-indexed (`1, 2, 3...`). *(Do not use `currentPage`)* |
  | `size` | Integer | Yes | Page size (maximum allowed: `100`). |
  | `date` | String | Yes | Format: `YYYY-MM-DD` |
  | `symbol` | String | Optional | Stock ticker filter (e.g. `KHPL`) |

### 2. Independent Verification Source: NepseAlpha Live Feed
- **Base Endpoint**: `https://nepsealpha.com/floorsheet-live-today/filter`
- **Query Parameters**:
  | Parameter | Type | Notes |
  |---|---|---|
  | `page` | Integer | 1-indexed pagination |
  | `itemsPerPage` | Integer | Supports up to `500` per request |
  | `stockSymbol` | String | Symbol filter |
  | `fsk` & `lvs` | String | Optional placeholder tokens (can be omitted) |

---

## 🛠️ Pipeline Architecture & Components

```
                ┌───────────────────────────────────┐
                │   ShareHub Floorsheet API (v2)    │
                └─────────────────┬─────────────────┘
                                  │
                 ┌────────────────┴────────────────┐
                 ▼                                 ▼
   ┌───────────────────────────┐     ┌───────────────────────────┐
   │ Floorsheet_Daily_Update   │     │     Floorsheet_Filler     │
   │ (Auto Daily Mon-Fri 17:00)│     │  (On-Demand Gap Backfill) │
   └─────────────┬─────────────┘     └─────────────┬─────────────┘
                 │                                 │
                 └────────────────┬────────────────┘
                                  │
                                  ▼
                ┌───────────────────────────────────┐
                │      CockroachDB (Cloud DB)       │
                │     Table: `floorsheet_raw`       │
                └─────────────────┬─────────────────┘
                                  │
                                  ▼
                ┌───────────────────────────────────┐
                │      verify.py (Reconciliation)   │
                │  Cross-checks with NepseAlpha live│
                └───────────────────────────────────┘
```

1. **`Floorsheet_Daily_Update.py`**:
   - Automated daily task scheduled at 17:00 NPT (11:15 UTC) on market trading days.
   - Probes total market trades and iterates through all pages with bulk `execute_values` and `ON CONFLICT DO UPDATE`.
2. **`Floorsheet_Filler.py`**:
   - Historical backfill and gap filler supporting date ranges and comma-separated stock ticker lists.
   - Pre-checks database record counts before scraping to avoid unnecessary network calls.
3. **`verify.py`**:
   - Independent reconciliation CLI tool comparing database aggregates and micro contract-level attributes against NepseAlpha.

---

## 📋 Implementation Milestones

- [x] **Phase 1: DB Schema & API Analysis** — Analyzed PostgreSQL/CockroachDB table structure, indexing, and live API schemas.
- [x] **Phase 2: Pagination Bug Fix** — Diagnosed `currentPage` bug (which caused infinite loop on Page 1) and fixed parameters to `page` and `size`.
- [x] **Phase 3: Backfill Execution & Validation** — Completed backfill for historical dates `2026-08-26` and `2026-08-27` (`KHPL`, `SONA`).
- [x] **Phase 4: Full Market Live Synchronization** — Synced all 68,137 trades for `2026-08-31` with 100% accuracy.
- [x] **Phase 5: Automated Verification Suite** — Built and verified `verify.py` against NepseAlpha feed with 100% contract-level match.
- [ ] **Phase 6: Continuous Automation Monitoring** — Maintain scheduled GitHub Actions workflows.

---

*Authored by Zara (Antigravity)*
