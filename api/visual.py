import os
import math
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Fallback: check .env in root if DB_URI not in env
if not os.getenv("DB_URI") and os.path.exists(".env"):
    with open(".env", "r") as f:
        for line in f:
            if line.strip().startswith("DB_URI="):
                os.environ["DB_URI"] = line.strip().split("DB_URI=", 1)[1].strip().strip('"').strip("'")

app = FastAPI(title="NEPSE Floorsheet Visual Analytics API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_URI = os.getenv("DB_URI")

def get_db_connection():
    """Establishes connection to CockroachDB."""
    uri = os.getenv("DB_URI")
    if not uri:
        raise HTTPException(status_code=500, detail="DB_URI environment variable missing.")
    try:
        conn = psycopg2.connect(uri, cursor_factory=RealDictCursor)
        return conn
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection error: {str(e)}")

def build_time_bounds(date_str: str, start_time = None, end_time = None):
    """Builds ISO timestamp bounds with Nepal timezone offset (+05:45)."""
    s_time = start_time.strip() if isinstance(start_time, str) and start_time.strip() else "00:00:00"
    e_time = end_time.strip() if isinstance(end_time, str) and end_time.strip() else "23:59:59"
    
    if len(s_time) == 5:
        s_time += ":00"
    if len(e_time) == 5:
        e_time += ":59"
        
    start_ts = f"{date_str} {s_time}+05:45"
    end_ts = f"{date_str} {e_time}+05:45"
    return start_ts, end_ts

@app.get("/api/visual/dates")
def get_available_dates():
    """Returns available trading dates with basic telemetry."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT 
                trade_time::date AS trading_date,
                COUNT(*) AS total_trades,
                COALESCE(SUM(amount), 0) AS total_turnover
            FROM floorsheet_raw
            GROUP BY trading_date
            ORDER BY trading_date DESC
            LIMIT 30;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [
            {
                "date": str(r["trading_date"]),
                "trades": int(r["total_trades"]),
                "turnover": float(r["total_turnover"])
            }
            for r in rows
        ]
    except Exception as e:
        cur.close()
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/visual/overview")
def get_market_overview(
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    start_time: str = Query(None, description="Start time HH:MM:SS (Optional)"),
    end_time: str = Query(None, description="End time HH:MM:SS (Optional)"),
    min_activity: float = Query(0.0, description="Minimum turnover threshold in NPR")
):
    """
    Computes macro market KPIs and the complete broker leaderboard matrix
    with top bought, top sold, top accumulation, and top distribution scrips.
    """
    min_act = float(min_activity) if isinstance(min_activity, (int, float, str)) and not hasattr(min_activity, 'default') else 0.0
    start_ts, end_ts = build_time_bounds(date, start_time, end_time)
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # 1. Market KPI Aggregates
        cur.execute("""
            SELECT 
                COUNT(*) AS total_trades,
                COALESCE(SUM(amount), 0) AS total_turnover,
                COALESCE(SUM(quantity), 0) AS total_quantity,
                COUNT(DISTINCT symbol) AS active_scrips
            FROM floorsheet_raw
            WHERE trade_time >= %s AND trade_time <= %s;
        """, (start_ts, end_ts))
        mkt = cur.fetchone()

        total_market_turnover = float(mkt["total_turnover"])
        total_market_trades = int(mkt["total_trades"])
        total_market_quantity = int(mkt["total_quantity"])
        active_scrips_count = int(mkt["active_scrips"])

        if total_market_trades == 0:
            cur.close()
            conn.close()
            return {
                "date": date,
                "time_window": {"start": start_time or "11:00:00", "end": end_time or "15:00:00"},
                "market_summary": {
                    "total_market_turnover": 0.0,
                    "total_market_shares": 0,
                    "total_market_trades": 0,
                    "active_brokers_count": 0,
                    "active_scrips_count": 0
                },
                "brokers": []
            }

        # 2. Broker Aggregations + Top Scrips Single-Pass Query
        query = """
            WITH filtered_trades AS (
                SELECT contract_id, symbol, buyer_broker, seller_broker, quantity, rate, amount, trade_time
                FROM floorsheet_raw
                WHERE trade_time >= %s AND trade_time <= %s
            ),
            trade_flows AS (
                SELECT buyer_broker AS broker_id, symbol, quantity AS buy_qty, 0::bigint AS sell_qty, amount AS buy_amt, 0::numeric AS sell_amt FROM filtered_trades
                UNION ALL
                SELECT seller_broker AS broker_id, symbol, 0::bigint AS buy_qty, quantity AS sell_qty, 0::numeric AS buy_amt, amount AS sell_amt FROM filtered_trades
            ),
            broker_scrip_agg AS (
                SELECT 
                    broker_id, symbol,
                    SUM(buy_qty) AS buy_qty, SUM(sell_qty) AS sell_qty,
                    SUM(buy_amt) AS buy_amt, SUM(sell_amt) AS sell_amt,
                    (SUM(buy_qty) - SUM(sell_qty)) AS net_qty,
                    (SUM(buy_amt) - SUM(sell_amt)) AS net_amt
                FROM trade_flows
                GROUP BY broker_id, symbol
            ),
            ranked_top_buy AS (
                SELECT broker_id, symbol AS top_buy_sym, buy_qty AS top_buy_qty, buy_amt AS top_buy_amt,
                       ROW_NUMBER() OVER (PARTITION BY broker_id ORDER BY buy_amt DESC) AS rn
                FROM broker_scrip_agg WHERE buy_amt > 0
            ),
            ranked_top_sell AS (
                SELECT broker_id, symbol AS top_sell_sym, sell_qty AS top_sell_qty, sell_amt AS top_sell_amt,
                       ROW_NUMBER() OVER (PARTITION BY broker_id ORDER BY sell_amt DESC) AS rn
                FROM broker_scrip_agg WHERE sell_amt > 0
            ),
            ranked_top_accum AS (
                SELECT broker_id, symbol AS top_accum_sym, net_qty AS top_accum_qty, net_amt AS top_accum_amt,
                       ROW_NUMBER() OVER (PARTITION BY broker_id ORDER BY net_amt DESC) AS rn
                FROM broker_scrip_agg WHERE net_amt > 0
            ),
            ranked_top_dist AS (
                SELECT broker_id, symbol AS top_dist_sym, net_qty AS top_dist_qty, net_amt AS top_dist_amt,
                       ROW_NUMBER() OVER (PARTITION BY broker_id ORDER BY net_amt ASC) AS rn
                FROM broker_scrip_agg WHERE net_amt < 0
            ),
            broker_totals AS (
                SELECT 
                    broker_id,
                    SUM(buy_amt) AS buy_value,
                    SUM(sell_amt) AS sell_value,
                    (SUM(buy_amt) + SUM(sell_amt)) AS gross_activity,
                    (SUM(buy_amt) - SUM(sell_amt)) AS net_flow_value,
                    SUM(buy_qty) AS buy_qty,
                    SUM(sell_qty) AS sell_qty,
                    (SUM(buy_qty) - SUM(sell_qty)) AS net_flow_qty
                FROM broker_scrip_agg
                GROUP BY broker_id
            )
            SELECT 
                bt.broker_id,
                bt.buy_value,
                bt.sell_value,
                bt.gross_activity,
                bt.net_flow_value,
                ROUND((bt.net_flow_value / NULLIF(bt.gross_activity, 0) * 100), 2) AS net_flow_pct,
                ROUND((bt.buy_value / NULLIF(bt.sell_value, 0)), 2) AS buy_sell_ratio,
                bt.buy_qty,
                bt.sell_qty,
                bt.net_flow_qty,
                tb.top_buy_sym, tb.top_buy_qty, tb.top_buy_amt,
                ts.top_sell_sym, ts.top_sell_qty, ts.top_sell_amt,
                ta.top_accum_sym, ta.top_accum_qty, ta.top_accum_amt,
                td.top_dist_sym, td.top_dist_qty, td.top_dist_amt
            FROM broker_totals bt
            LEFT JOIN ranked_top_buy tb ON bt.broker_id = tb.broker_id AND tb.rn = 1
            LEFT JOIN ranked_top_sell ts ON bt.broker_id = ts.broker_id AND ts.rn = 1
            LEFT JOIN ranked_top_accum ta ON bt.broker_id = ta.broker_id AND ta.rn = 1
            LEFT JOIN ranked_top_dist td ON bt.broker_id = td.broker_id AND td.rn = 1
            WHERE bt.gross_activity >= %s
            ORDER BY bt.gross_activity DESC;
        """
        cur.execute(query, (start_ts, end_ts, min_act))
        broker_rows = cur.fetchall()
        cur.close()
        conn.close()

        brokers = []
        for r in broker_rows:
            gross = float(r["gross_activity"])
            mkt_share = round((gross / (2.0 * total_market_turnover) * 100.0), 2) if total_market_turnover > 0 else 0.0

            brokers.append({
                "broker_id": int(r["broker_id"]),
                "buy_value": float(r["buy_value"]),
                "sell_value": float(r["sell_value"]),
                "gross_activity": gross,
                "net_flow_value": float(r["net_flow_value"]),
                "net_flow_pct": float(r["net_flow_pct"]) if r["net_flow_pct"] is not None else 0.0,
                "buy_sell_ratio": float(r["buy_sell_ratio"]) if r["buy_sell_ratio"] is not None else None,
                "buy_qty": int(r["buy_qty"]),
                "sell_qty": int(r["sell_qty"]),
                "net_flow_qty": int(r["net_flow_qty"]),
                "market_share_pct": mkt_share,
                "top_bought": {
                    "symbol": r["top_buy_sym"],
                    "quantity": int(r["top_buy_qty"]) if r["top_buy_qty"] else 0,
                    "value": float(r["top_buy_amt"]) if r["top_buy_amt"] else 0.0
                } if r["top_buy_sym"] else None,
                "top_sold": {
                    "symbol": r["top_sell_sym"],
                    "quantity": int(r["top_sell_qty"]) if r["top_sell_qty"] else 0,
                    "value": float(r["top_sell_amt"]) if r["top_sell_amt"] else 0.0
                } if r["top_sell_sym"] else None,
                "top_accumulation": {
                    "symbol": r["top_accum_sym"],
                    "net_qty": int(r["top_accum_qty"]) if r["top_accum_qty"] else 0,
                    "net_value": float(r["top_accum_amt"]) if r["top_accum_amt"] else 0.0
                } if r["top_accum_sym"] else None,
                "top_distribution": {
                    "symbol": r["top_dist_sym"],
                    "net_qty": int(r["top_dist_qty"]) if r["top_dist_qty"] else 0,
                    "net_value": float(r["top_dist_amt"]) if r["top_dist_amt"] else 0.0
                } if r["top_dist_sym"] else None,
            })

        return {
            "date": date,
            "time_window": {"start": start_time or "11:00:00", "end": end_time or "15:00:00"},
            "market_summary": {
                "total_market_turnover": total_market_turnover,
                "total_market_shares": total_market_quantity,
                "total_market_trades": total_market_trades,
                "active_brokers_count": len(brokers),
                "active_scrips_count": active_scrips_count
            },
            "brokers": brokers
        }

    except Exception as e:
        cur.close()
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/visual/broker/{broker_id}")
def get_broker_detail(
    broker_id: int,
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    start_time: str = Query(None, description="Start time HH:MM:SS (Optional)"),
    end_time: str = Query(None, description="End time HH:MM:SS (Optional)"),
    bucket: str = Query("15m", description="Timeline bucket: 5m, 15m, 30m, 1h")
):
    """
    Returns granular intelligence for a single broker:
    1. Complete Scrip Portfolio breakdown
    2. Intraday Timeline Velocity (Chart data)
    3. Counterparty Analysis (Bought from & Sold to)
    """
    start_ts, end_ts = build_time_bounds(date, start_time, end_time)
    conn = get_db_connection()
    cur = conn.cursor()

    # Bucket interval minutes
    bucket_str = bucket if isinstance(bucket, str) else "15m"
    bucket_mins = 15
    if bucket_str == "5m":
        bucket_mins = 5
    elif bucket_str == "30m":
        bucket_mins = 30
    elif bucket_str == "1h":
        bucket_mins = 60

    try:
        # 1. Scrips Breakdown for this broker
        scrips_query = """
            WITH broker_trades AS (
                SELECT symbol, quantity AS buy_qty, 0::bigint AS sell_qty, amount AS buy_amt, 0::numeric AS sell_amt
                FROM floorsheet_raw WHERE buyer_broker = %s AND trade_time >= %s AND trade_time <= %s
                UNION ALL
                SELECT symbol, 0::bigint AS buy_qty, quantity AS sell_qty, 0::numeric AS buy_amt, amount AS sell_amt
                FROM floorsheet_raw WHERE seller_broker = %s AND trade_time >= %s AND trade_time <= %s
            )
            SELECT 
                symbol,
                SUM(buy_qty) AS buy_qty,
                SUM(sell_qty) AS sell_qty,
                (SUM(buy_qty) - SUM(sell_qty)) AS net_flow_qty,
                SUM(buy_amt) AS buy_value,
                SUM(sell_amt) AS sell_value,
                (SUM(buy_amt) - SUM(sell_amt)) AS net_flow_value,
                ROUND(SUM(buy_amt) / NULLIF(SUM(buy_qty), 0), 2) AS avg_buy_rate,
                ROUND(SUM(sell_amt) / NULLIF(SUM(sell_qty), 0), 2) AS avg_sell_rate,
                CASE WHEN (SUM(buy_amt) - SUM(sell_amt)) >= 0 THEN 'ACCUMULATING' ELSE 'DISTRIBUTING' END AS flow_status
            FROM broker_trades
            GROUP BY symbol
            ORDER BY (SUM(buy_amt) + SUM(sell_amt)) DESC;
        """
        cur.execute(scrips_query, (broker_id, start_ts, end_ts, broker_id, start_ts, end_ts))
        scrip_rows = cur.fetchall()

        total_buy_val = sum(float(r["buy_value"]) for r in scrip_rows)
        total_sell_val = sum(float(r["sell_value"]) for r in scrip_rows)
        total_buy_qty = sum(int(r["buy_qty"]) for r in scrip_rows)
        total_sell_qty = sum(int(r["sell_qty"]) for r in scrip_rows)
        gross_activity = total_buy_val + total_sell_val
        net_flow_val = total_buy_val - total_sell_val
        net_flow_pct = round((net_flow_val / gross_activity * 100.0), 2) if gross_activity > 0 else 0.0
        buy_sell_ratio = round((total_buy_val / total_sell_val), 2) if total_sell_val > 0 else None

        scrips = [
            {
                "symbol": r["symbol"],
                "buy_qty": int(r["buy_qty"]),
                "sell_qty": int(r["sell_qty"]),
                "net_flow_qty": int(r["net_flow_qty"]),
                "buy_value": float(r["buy_value"]),
                "sell_value": float(r["sell_value"]),
                "net_flow_value": float(r["net_flow_value"]),
                "avg_buy_rate": float(r["avg_buy_rate"]) if r["avg_buy_rate"] else 0.0,
                "avg_sell_rate": float(r["avg_sell_rate"]) if r["avg_sell_rate"] else 0.0,
                "flow_status": r["flow_status"]
            }
            for r in scrip_rows
        ]

        # 2. Counterparties: Top Bought From
        cur.execute("""
            SELECT 
                seller_broker AS counter_broker,
                SUM(amount) AS value,
                SUM(quantity) AS quantity,
                COUNT(*) AS trades_count
            FROM floorsheet_raw
            WHERE buyer_broker = %s AND trade_time >= %s AND trade_time <= %s
            GROUP BY seller_broker
            ORDER BY value DESC
            LIMIT 10;
        """, (broker_id, start_ts, end_ts))
        bought_from_rows = cur.fetchall()

        bought_from = [
            {
                "counter_broker": int(r["counter_broker"]),
                "value": float(r["value"]),
                "quantity": int(r["quantity"]),
                "trades_count": int(r["trades_count"]),
                "buy_value_share_pct": round((float(r["value"]) / total_buy_val * 100.0), 2) if total_buy_val > 0 else 0.0
            }
            for r in bought_from_rows
        ]

        # 3. Counterparties: Top Sold To
        cur.execute("""
            SELECT 
                buyer_broker AS counter_broker,
                SUM(amount) AS value,
                SUM(quantity) AS quantity,
                COUNT(*) AS trades_count
            FROM floorsheet_raw
            WHERE seller_broker = %s AND trade_time >= %s AND trade_time <= %s
            GROUP BY buyer_broker
            ORDER BY value DESC
            LIMIT 10;
        """, (broker_id, start_ts, end_ts))
        sold_to_rows = cur.fetchall()

        sold_to = [
            {
                "counter_broker": int(r["counter_broker"]),
                "value": float(r["value"]),
                "quantity": int(r["quantity"]),
                "trades_count": int(r["trades_count"]),
                "sell_value_share_pct": round((float(r["value"]) / total_sell_val * 100.0), 2) if total_sell_val > 0 else 0.0
            }
            for r in sold_to_rows
        ]

        # 4. Intraday Timeline Bucketing
        timeline_query = f"""
            WITH timeline_flows AS (
                SELECT 
                    TO_CHAR(trade_time AT TIME ZONE 'Asia/Kathmandu', 'HH24') || ':' || 
                    LPAD((FLOOR(EXTRACT(MINUTE FROM trade_time AT TIME ZONE 'Asia/Kathmandu') / {bucket_mins}) * {bucket_mins})::TEXT, 2, '0') AS time_bucket,
                    amount AS buy_amt, 0::numeric AS sell_amt, 1 AS trades
                FROM floorsheet_raw WHERE buyer_broker = %s AND trade_time >= %s AND trade_time <= %s
                UNION ALL
                SELECT 
                    TO_CHAR(trade_time AT TIME ZONE 'Asia/Kathmandu', 'HH24') || ':' || 
                    LPAD((FLOOR(EXTRACT(MINUTE FROM trade_time AT TIME ZONE 'Asia/Kathmandu') / {bucket_mins}) * {bucket_mins})::TEXT, 2, '0') AS time_bucket,
                    0::numeric AS buy_amt, amount AS sell_amt, 1 AS trades
                FROM floorsheet_raw WHERE seller_broker = %s AND trade_time >= %s AND trade_time <= %s
            )
            SELECT 
                time_bucket,
                SUM(buy_amt) AS buy_value,
                SUM(sell_amt) AS sell_value,
                (SUM(buy_amt) - SUM(sell_amt)) AS net_flow_value,
                SUM(trades) AS trades_count
            FROM timeline_flows
            GROUP BY time_bucket
            ORDER BY time_bucket ASC;
        """
        cur.execute(timeline_query, (broker_id, start_ts, end_ts, broker_id, start_ts, end_ts))
        timeline_rows = cur.fetchall()

        cur.close()
        conn.close()

        timeline = [
            {
                "time_label": r["time_bucket"],
                "buy_value": float(r["buy_value"]),
                "sell_value": float(r["sell_value"]),
                "net_flow_value": float(r["net_flow_value"]),
                "trades_count": int(r["trades_count"])
            }
            for r in timeline_rows
        ]

        total_trades = sum(t["trades_count"] for t in timeline)
        peak_window = max(timeline, key=lambda x: x["buy_value"] + x["sell_value"])["time_label"] if timeline else None

        return {
            "broker_id": broker_id,
            "date": date,
            "time_window": {"start": start_time or "11:00:00", "end": end_time or "15:00:00"},
            "bucket": bucket,
            "summary": {
                "buy_value": total_buy_val,
                "sell_value": total_sell_val,
                "gross_activity": gross_activity,
                "net_flow_value": net_flow_val,
                "net_flow_pct": net_flow_pct,
                "buy_sell_ratio": buy_sell_ratio,
                "buy_qty": total_buy_qty,
                "sell_qty": total_sell_qty,
                "net_flow_qty": total_buy_qty - total_sell_qty,
                "total_trades": total_trades,
                "peak_trading_window": peak_window
            },
            "scrips": scrips,
            "timeline": timeline,
            "counterparties": {
                "bought_from": bought_from,
                "sold_to": sold_to
            }
        }

    except Exception as e:
        cur.close()
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))
