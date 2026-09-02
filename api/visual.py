import os
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, APIRouter, Query, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, date

# Load local .env if present
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

DB_URI = os.getenv("DB_URI")

app = FastAPI(title="NEPSE Broker Visual Analytics API")
router = APIRouter()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db_connection():
    if not DB_URI:
        raise HTTPException(status_code=500, detail="DB_URI environment variable is missing!")
    uri = DB_URI
    if "sslmode=verify-full" in uri:
        uri = uri.replace("sslmode=verify-full", "sslmode=require")
    try:
        conn = psycopg2.connect(uri, cursor_factory=RealDictCursor)
        conn.autocommit = True
        return conn
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection error: {str(e)}")

def apply_cache_headers(response: Response, date_str: str = None):
    """Applies Vercel CDN and browser cache headers. Historical dates cached 24h."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    if date_str and date_str < today_str:
        response.headers["Cache-Control"] = "public, max-age=86400, s-maxage=86400, stale-while-revalidate=604800"
    else:
        response.headers["Cache-Control"] = "public, max-age=60, s-maxage=60"

def build_time_bounds(date_str: str, start_time: str = None, end_time: str = None):
    s_time = start_time.strip() if start_time else "11:00:00"
    e_time = end_time.strip() if end_time else "15:00:00"
    if len(s_time) == 5:
        s_time += ":00"
    if len(e_time) == 5:
        e_time += ":59"
        
    start_ts = f"{date_str} {s_time}"
    end_ts = f"{date_str} {e_time}"
    return start_ts, end_ts

@router.get("/dates")
def get_available_dates(response: Response):
    """Returns available trading dates efficiently from summary layer."""
    apply_cache_headers(response)
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT 
                trade_date AS trading_date,
                COALESCE(SUM(trades_count), 0) AS total_trades,
                COALESCE(SUM(buy_amt), 0) AS total_turnover
            FROM daily_broker_scrip_summary
            GROUP BY trade_date
            ORDER BY trade_date DESC
            LIMIT 30;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [
            {
                "date": r["trading_date"].strftime("%Y-%m-%d"),
                "trades": int(r["total_trades"]),
                "turnover": float(r["total_turnover"])
            }
            for r in rows
        ]
    except Exception as e:
        cur.close()
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/overview")
def get_market_overview(
    response: Response,
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    start_time: str = Query(None, description="Start time HH:MM:SS (Optional)"),
    end_time: str = Query(None, description="End time HH:MM:SS (Optional)"),
    min_activity: float = Query(0.0, description="Minimum turnover threshold in NPR")
):
    apply_cache_headers(response, date)
    min_act = float(min_activity) if isinstance(min_activity, (int, float, str)) and not hasattr(min_activity, 'default') else 0.0
    start_ts, end_ts = build_time_bounds(date, start_time, end_time)
    is_full_day = (start_time is None and end_time is None) or (start_time == "11:00" and end_time == "15:00")

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        if is_full_day:
            # OPTIMIZED: Query pre-aggregated daily_broker_scrip_summary (78% smaller)
            cur.execute("""
                SELECT 
                    COALESCE(SUM(trades_count), 0) AS total_trades,
                    COALESCE(SUM(buy_amt), 0) AS total_turnover,
                    COALESCE(SUM(buy_qty), 0) AS total_quantity,
                    COUNT(DISTINCT symbol) AS active_scrips
                FROM daily_broker_scrip_summary
                WHERE trade_date = %s;
            """, (date,))
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
                    "time_window": {"start": "11:00:00", "end": "15:00:00"},
                    "market_summary": {
                        "total_market_turnover": 0.0,
                        "total_market_shares": 0,
                        "total_market_trades": 0,
                        "active_brokers_count": 0,
                        "active_scrips_count": 0
                    },
                    "brokers": []
                }

            query = """
                WITH broker_scrip_agg AS (
                    SELECT 
                        broker_id, symbol,
                        buy_qty, sell_qty,
                        buy_amt, sell_amt,
                        net_qty, net_amt
                    FROM daily_broker_scrip_summary
                    WHERE trade_date = %s
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
            cur.execute(query, (date, min_act))
            broker_rows = cur.fetchall()

        else:
            # Intraday Time-Sliced Query using covering index on floorsheet_raw
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

        # 3. Format Response Payload
        brokers = []
        for r in broker_rows:
            buy_val = float(r["buy_value"])
            sell_val = float(r["sell_value"])
            gross = float(r["gross_activity"])
            net_val = float(r["net_flow_value"])
            market_share_pct = round((buy_val / total_market_turnover * 100), 2) if total_market_turnover > 0 else 0.0

            brokers.append({
                "broker_id": int(r["broker_id"]),
                "gross_activity": gross,
                "buy_amount": buy_val,
                "sell_amount": sell_val,
                "net_flow_value": net_val,
                "net_flow_pct": float(r["net_flow_pct"] or 0),
                "buy_sell_ratio": float(r["buy_sell_ratio"] or 0),
                "buy_quantity": int(r["buy_qty"]),
                "sell_quantity": int(r["sell_qty"]),
                "net_flow_quantity": int(r["net_flow_qty"]),
                "market_share_pct": market_share_pct,
                "flow_status": "ACCUMULATING" if net_val >= 0 else "DISTRIBUTING",
                "top_buy_scrip": {
                    "symbol": r["top_buy_sym"],
                    "quantity": int(r["top_buy_qty"] or 0),
                    "amount": float(r["top_buy_amt"] or 0)
                } if r["top_buy_sym"] else None,
                "top_sell_scrip": {
                    "symbol": r["top_sell_sym"],
                    "quantity": int(r["top_sell_qty"] or 0),
                    "amount": float(r["top_sell_amt"] or 0)
                } if r["top_sell_sym"] else None,
                "top_accum_scrip": {
                    "symbol": r["top_accum_sym"],
                    "net_quantity": int(r["top_accum_qty"] or 0),
                    "net_amount": float(r["top_accum_amt"] or 0)
                } if r["top_accum_sym"] else None,
                "top_dist_scrip": {
                    "symbol": r["top_dist_sym"],
                    "net_quantity": int(r["top_dist_qty"] or 0),
                    "net_amount": float(r["top_dist_amt"] or 0)
                } if r["top_dist_sym"] else None
            })

        return {
            "date": date,
            "time_window": {
                "start": start_time or "11:00:00",
                "end": end_time or "15:00:00"
            },
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

@router.get("/broker/{broker_id}")
def get_broker_detail(
    broker_id: int,
    response: Response,
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    start_time: str = Query(None, description="Start time HH:MM:SS (Optional)"),
    end_time: str = Query(None, description="End time HH:MM:SS (Optional)"),
    time_bucket: str = Query("15m", description="Aggregation bucket: 5m, 15m, 30m, 1h")
):
    apply_cache_headers(response, date)
    start_ts, end_ts = build_time_bounds(date, start_time, end_time)
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # 1. Total Broker Summary for Period
        cur.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN buyer_broker = %s THEN amount ELSE 0 END), 0) AS total_buy_val,
                COALESCE(SUM(CASE WHEN seller_broker = %s THEN amount ELSE 0 END), 0) AS total_sell_val,
                COALESCE(SUM(CASE WHEN buyer_broker = %s THEN quantity ELSE 0 END), 0) AS total_buy_qty,
                COALESCE(SUM(CASE WHEN seller_broker = %s THEN quantity ELSE 0 END), 0) AS total_sell_qty,
                COUNT(*) AS total_participations
            FROM floorsheet_raw
            WHERE (buyer_broker = %s OR seller_broker = %s)
              AND trade_time >= %s AND trade_time <= %s;
        """, (broker_id, broker_id, broker_id, broker_id, broker_id, broker_id, start_ts, end_ts))
        summary = cur.fetchone()

        total_buy = float(summary["total_buy_val"])
        total_sell = float(summary["total_sell_val"])
        gross = total_buy + total_sell
        net = total_buy - total_sell
        total_buy_qty = int(summary["total_buy_qty"])
        total_sell_qty = int(summary["total_sell_qty"])

        # 2. Portfolio Breakdown by Scrip
        cur.execute("""
            WITH b_trades AS (
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
                SUM(buy_qty) - SUM(sell_qty) AS net_qty,
                SUM(buy_amt) AS buy_amt,
                SUM(sell_amt) AS sell_amt,
                SUM(buy_amt) - SUM(sell_amt) AS net_amt,
                SUM(buy_amt + sell_amt) AS gross_amt,
                ROUND(SUM(buy_amt) / NULLIF(SUM(buy_qty), 0), 2) AS buy_vwap,
                ROUND(SUM(sell_amt) / NULLIF(SUM(sell_qty), 0), 2) AS sell_vwap
            FROM b_trades
            GROUP BY symbol
            ORDER BY gross_amt DESC;
        """, (broker_id, start_ts, end_ts, broker_id, start_ts, end_ts))
        scrip_rows = cur.fetchall()

        scrips = [
            {
                "symbol": r["symbol"],
                "buy_quantity": int(r["buy_qty"]),
                "sell_quantity": int(r["sell_qty"]),
                "net_quantity": int(r["net_qty"]),
                "buy_amount": float(r["buy_amt"]),
                "sell_amount": float(r["sell_amt"]),
                "net_amount": float(r["net_amt"]),
                "gross_amount": float(r["gross_amt"]),
                "buy_vwap": float(r["buy_vwap"] or 0),
                "sell_vwap": float(r["sell_vwap"] or 0),
                "flow_status": "ACCUMULATING" if float(r["net_amt"]) >= 0 else "DISTRIBUTING"
            }
            for r in scrip_rows
        ]

        # 3. Counterparty Network Analysis
        cur.execute("""
            SELECT 
                seller_broker AS counterparty_id,
                SUM(amount) AS trade_amount,
                SUM(quantity) AS trade_quantity,
                COUNT(*) AS trade_count
            FROM floorsheet_raw
            WHERE buyer_broker = %s AND trade_time >= %s AND trade_time <= %s
            GROUP BY seller_broker
            ORDER BY trade_amount DESC
            LIMIT 10;
        """, (broker_id, start_ts, end_ts))
        bought_from = [
            {
                "broker_id": int(r["counterparty_id"]),
                "amount": float(r["trade_amount"]),
                "quantity": int(r["trade_quantity"]),
                "trades": int(r["trade_count"]),
                "market_share_pct": round(float(r["trade_amount"]) / total_buy * 100, 2) if total_buy > 0 else 0.0
            }
            for r in cur.fetchall()
        ]

        cur.execute("""
            SELECT 
                buyer_broker AS counterparty_id,
                SUM(amount) AS trade_amount,
                SUM(quantity) AS trade_quantity,
                COUNT(*) AS trade_count
            FROM floorsheet_raw
            WHERE seller_broker = %s AND trade_time >= %s AND trade_time <= %s
            GROUP BY buyer_broker
            ORDER BY trade_amount DESC
            LIMIT 10;
        """, (broker_id, start_ts, end_ts))
        sold_to = [
            {
                "broker_id": int(r["counterparty_id"]),
                "amount": float(r["trade_amount"]),
                "quantity": int(r["trade_quantity"]),
                "trades": int(r["trade_count"]),
                "market_share_pct": round(float(r["trade_amount"]) / total_sell * 100, 2) if total_sell > 0 else 0.0
            }
            for r in cur.fetchall()
        ]

        # 4. Intraday Timeline
        bucket_mins = 15
        if time_bucket == "5m": bucket_mins = 5
        elif time_bucket == "30m": bucket_mins = 30
        elif time_bucket == "1h": bucket_mins = 60

        cur.execute(f"""
            WITH b_flow AS (
                SELECT 
                    TO_CHAR(trade_time, 'HH24') || ':' || 
                    LPAD((FLOOR(EXTRACT(MINUTE FROM trade_time) / {bucket_mins}) * {bucket_mins})::TEXT, 2, '0') AS time_bucket,
                    amount AS buy_amt, 0::numeric AS sell_amt, quantity AS buy_qty, 0::bigint AS sell_qty
                FROM floorsheet_raw WHERE buyer_broker = %s AND trade_time >= %s AND trade_time <= %s
                UNION ALL
                SELECT 
                    TO_CHAR(trade_time, 'HH24') || ':' || 
                    LPAD((FLOOR(EXTRACT(MINUTE FROM trade_time) / {bucket_mins}) * {bucket_mins})::TEXT, 2, '0') AS time_bucket,
                    0::numeric AS buy_amt, amount AS sell_amt, 0::bigint AS buy_qty, quantity AS sell_qty
                FROM floorsheet_raw WHERE seller_broker = %s AND trade_time >= %s AND trade_time <= %s
            )
            SELECT 
                time_bucket,
                SUM(buy_amt) AS buy_amount,
                SUM(sell_amt) AS sell_amount,
                SUM(buy_amt) - SUM(sell_amt) AS net_flow,
                SUM(buy_qty) AS buy_quantity,
                SUM(sell_qty) AS sell_quantity
            FROM b_flow
            GROUP BY time_bucket
            ORDER BY time_bucket ASC;
        """, (broker_id, start_ts, end_ts, broker_id, start_ts, end_ts))

        timeline = [
            {
                "bucket": r["time_bucket"],
                "buy_amount": float(r["buy_amount"]),
                "sell_amount": float(r["sell_amount"]),
                "net_amount": float(r["net_flow"]),
                "buy_quantity": int(r["buy_quantity"]),
                "sell_quantity": int(r["sell_quantity"])
            }
            for r in cur.fetchall()
        ]

        cur.close()
        conn.close()

        return {
            "broker_id": broker_id,
            "date": date,
            "time_window": {"start": start_time or "11:00:00", "end": end_time or "15:00:00"},
            "summary": {
                "gross_activity": gross,
                "buy_amount": total_buy,
                "sell_amount": total_sell,
                "net_flow_value": net,
                "net_flow_pct": round((net / gross * 100), 2) if gross > 0 else 0.0,
                "buy_sell_ratio": round((total_buy / total_sell), 2) if total_sell > 0 else 0.0,
                "buy_quantity": total_buy_qty,
                "sell_quantity": total_sell_qty,
                "net_flow_quantity": total_buy_qty - total_sell_qty,
                "trades_count": int(summary["total_participations"]),
                "active_scrips_count": len(scrips)
            },
            "scrips": scrips,
            "counterparties": {
                "bought_from": bought_from,
                "sold_to": sold_to
            },
            "timeline": timeline
        }

    except Exception as e:
        cur.close()
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))

# Mount Routers
app.include_router(router, prefix="/api/visual")
app.include_router(router, prefix="/visual")
app.include_router(router, prefix="/api")
app.include_router(router, prefix="")
