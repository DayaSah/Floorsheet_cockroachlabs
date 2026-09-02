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

app = FastAPI(title="NEPSE Scrip (Stock) Analytics API")
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
                COUNT(DISTINCT symbol) AS active_scrips,
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
                "active_scrips": int(r["active_scrips"]),
                "turnover": float(r["total_turnover"])
            }
            for r in rows
        ]
    except Exception as e:
        cur.close()
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/overview")
def get_scrips_overview(
    response: Response,
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    start_time: str = Query(None, description="Start time HH:MM:SS (Optional)"),
    end_time: str = Query(None, description="End time HH:MM:SS (Optional)"),
    min_turnover: float = Query(0.0, description="Minimum turnover threshold in NPR")
):
    apply_cache_headers(response, date)
    min_turn = float(min_turnover) if isinstance(min_turnover, (int, float, str)) and not hasattr(min_turnover, 'default') else 0.0
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
                        "active_scrips_count": 0
                    },
                    "scrips": []
                }

            query = """
                WITH scrip_totals AS (
                    SELECT 
                        symbol,
                        SUM(buy_amt) AS turnover,
                        SUM(buy_qty) AS volume,
                        SUM(trades_count) AS trades_count,
                        ROUND(SUM(buy_amt) / NULLIF(SUM(buy_qty), 0), 2) AS vwap
                    FROM daily_broker_scrip_summary
                    WHERE trade_date = %s
                    GROUP BY symbol
                    HAVING SUM(buy_amt) >= %s
                ),
                ranked_buyers AS (
                    SELECT symbol, broker_id, net_qty, net_amt,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY net_qty DESC) as rn
                    FROM (
                        SELECT symbol, broker_id, SUM(buy_qty) - SUM(sell_qty) AS net_qty, SUM(buy_amt) - SUM(sell_amt) AS net_amt
                        FROM daily_broker_scrip_summary WHERE trade_date = %s GROUP BY symbol, broker_id
                    ) sub WHERE net_qty > 0
                ),
                ranked_sellers AS (
                    SELECT symbol, broker_id, net_qty, net_amt,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY net_qty ASC) as rn
                    FROM (
                        SELECT symbol, broker_id, SUM(buy_qty) - SUM(sell_qty) AS net_qty, SUM(buy_amt) - SUM(sell_amt) AS net_amt
                        FROM daily_broker_scrip_summary WHERE trade_date = %s GROUP BY symbol, broker_id
                    ) sub WHERE net_qty < 0
                ),
                top3_concentration AS (
                    SELECT 
                        symbol,
                        SUM(buy_qty) AS top3_volume
                    FROM (
                        SELECT symbol, buy_qty,
                               ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY buy_qty DESC) as rn
                        FROM daily_broker_scrip_summary WHERE trade_date = %s
                    ) sub
                    WHERE rn <= 3
                    GROUP BY symbol
                )
                SELECT 
                    s.symbol,
                    s.turnover,
                    s.volume,
                    s.trades_count,
                    s.vwap,
                    s.vwap AS ltp,
                    s.vwap AS high_rate,
                    s.vwap AS low_rate,
                    rb.broker_id AS top_buyer_id,
                    rb.net_qty AS top_buyer_net_qty,
                    rs.broker_id AS top_seller_id,
                    rs.net_qty AS top_seller_net_qty,
                    COALESCE(c.top3_volume, 0) AS top3_volume
                FROM scrip_totals s
                LEFT JOIN ranked_buyers rb ON s.symbol = rb.symbol AND rb.rn = 1
                LEFT JOIN ranked_sellers rs ON s.symbol = rs.symbol AND rs.rn = 1
                LEFT JOIN top3_concentration c ON s.symbol = c.symbol
                ORDER BY s.turnover DESC;
            """
            cur.execute(query, (date, min_turn, date, date, date))
            scrip_rows = cur.fetchall()

        else:
            # Intraday Query on floorsheet_raw using covering index
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
                scrip_totals AS (
                    SELECT 
                        symbol,
                        SUM(amount) AS turnover,
                        SUM(quantity) AS volume,
                        COUNT(*) AS trades_count,
                        ROUND(SUM(amount) / NULLIF(SUM(quantity), 0), 2) AS vwap,
                        MAX(rate) AS high_rate,
                        MIN(rate) AS low_rate
                    FROM filtered_trades
                    GROUP BY symbol
                    HAVING SUM(amount) >= %s
                ),
                last_trades AS (
                    SELECT symbol, rate AS ltp
                    FROM (
                        SELECT symbol, rate,
                               ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY trade_time DESC, contract_id DESC) AS rn
                        FROM filtered_trades
                    ) ranked
                    WHERE rn = 1
                ),
                broker_scrip_flows AS (
                    SELECT 
                        symbol,
                        broker_id,
                        SUM(buy_qty) - SUM(sell_qty) AS net_qty,
                        SUM(buy_amt) - SUM(sell_amt) AS net_val,
                        SUM(buy_qty) AS total_bought_qty
                    FROM (
                        SELECT symbol, buyer_broker AS broker_id, quantity AS buy_qty, 0::bigint AS sell_qty, amount AS buy_amt, 0::numeric AS sell_amt FROM filtered_trades
                        UNION ALL
                        SELECT symbol, seller_broker AS broker_id, 0::bigint AS buy_qty, quantity AS sell_qty, 0::numeric AS buy_amt, amount AS sell_amt FROM filtered_trades
                    ) f
                    GROUP BY symbol, broker_id
                ),
                ranked_buyers AS (
                    SELECT symbol, broker_id, net_qty, net_val,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY net_qty DESC) as rn
                    FROM broker_scrip_flows
                    WHERE net_qty > 0
                ),
                ranked_sellers AS (
                    SELECT symbol, broker_id, net_qty, net_val,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY net_qty ASC) as rn
                    FROM broker_scrip_flows
                    WHERE net_qty < 0
                ),
                top3_concentration AS (
                    SELECT 
                        symbol,
                        SUM(total_bought_qty) AS top3_volume
                    FROM (
                        SELECT symbol, total_bought_qty,
                               ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY total_bought_qty DESC) as rn
                        FROM broker_scrip_flows
                    ) sub
                    WHERE rn <= 3
                    GROUP BY symbol
                )
                SELECT 
                    s.symbol,
                    s.turnover,
                    s.volume,
                    s.trades_count,
                    s.vwap,
                    s.high_rate,
                    s.low_rate,
                    COALESCE(lt.ltp, s.vwap) AS ltp,
                    rb.broker_id AS top_buyer_id,
                    rb.net_qty AS top_buyer_net_qty,
                    rs.broker_id AS top_seller_id,
                    rs.net_qty AS top_seller_net_qty,
                    COALESCE(c.top3_volume, 0) AS top3_volume
                FROM scrip_totals s
                LEFT JOIN last_trades lt ON s.symbol = lt.symbol
                LEFT JOIN ranked_buyers rb ON s.symbol = rb.symbol AND rb.rn = 1
                LEFT JOIN ranked_sellers rs ON s.symbol = rs.symbol AND rs.rn = 1
                LEFT JOIN top3_concentration c ON s.symbol = c.symbol
                ORDER BY s.turnover DESC;
            """
            cur.execute(query, (start_ts, end_ts, min_turn))
            scrip_rows = cur.fetchall()

        cur.close()
        conn.close()

        scrips = []
        for r in scrip_rows:
            turnover = float(r["turnover"])
            vol = int(r["volume"])
            top3_vol = int(r["top3_volume"])
            conc_pct = round((top3_vol / vol * 100), 2) if vol > 0 else 0.0
            mkt_share = round((turnover / total_market_turnover * 100), 2) if total_market_turnover > 0 else 0.0

            scrips.append({
                "symbol": r["symbol"],
                "turnover": turnover,
                "volume": vol,
                "trades_count": int(r["trades_count"]),
                "vwap": float(r["vwap"] or 0),
                "ltp": float(r["ltp"] or 0),
                "high_rate": float(r["high_rate"] or 0),
                "low_rate": float(r["low_rate"] or 0),
                "market_share_pct": mkt_share,
                "top3_concentration_pct": conc_pct,
                "top_net_buyer": {
                    "broker_id": int(r["top_buyer_id"]),
                    "net_qty": int(r["top_buyer_net_qty"])
                } if r["top_buyer_id"] else None,
                "top_net_seller": {
                    "broker_id": int(r["top_seller_id"]),
                    "net_qty": int(r["top_seller_net_qty"])
                } if r["top_seller_id"] else None
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
                "active_scrips_count": active_scrips_count
            },
            "scrips": scrips
        }

    except Exception as e:
        cur.close()
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/scrip/{symbol}")
def get_scrip_detail(
    symbol: str,
    response: Response,
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    start_time: str = Query(None, description="Start time HH:MM:SS (Optional)"),
    end_time: str = Query(None, description="End time HH:MM:SS (Optional)"),
    time_bucket: str = Query("15m", description="Aggregation bucket: 5m, 15m, 30m, 1h"),
    whale_threshold_qty: int = Query(1000, description="Min quantity for whale scanner"),
    whale_threshold_amt: float = Query(500000.0, description="Min amount in NPR for whale scanner")
):
    apply_cache_headers(response, date)
    start_ts, end_ts = build_time_bounds(date, start_time, end_time)
    sym_clean = symbol.strip().upper()
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # High-performance indexed single-pass CTE using idx_symbol_time (symbol, trade_time)
        cur.execute("""
            WITH s_trades AS (
                SELECT contract_id, symbol, buyer_broker, seller_broker, quantity, rate, amount, trade_time
                FROM floorsheet_raw
                WHERE symbol = %s AND trade_time >= %s AND trade_time <= %s
            )
            SELECT 
                COUNT(*) AS total_trades,
                COALESCE(SUM(amount), 0) AS total_turnover,
                COALESCE(SUM(quantity), 0) AS total_volume,
                COALESCE(MAX(rate), 0) AS high_rate,
                COALESCE(MIN(rate), 0) AS low_rate,
                ROUND(COALESCE(SUM(amount) / NULLIF(SUM(quantity), 0), 0), 2) AS vwap
            FROM s_trades;
        """, (sym_clean, start_ts, end_ts))
        summary = cur.fetchone()

        total_turnover = float(summary["total_turnover"])
        total_volume = int(summary["total_volume"])
        total_trades = int(summary["total_trades"])

        # 2. Broker Participation Matrix
        cur.execute("""
            WITH b_scrip_trades AS (
                SELECT buyer_broker AS broker_id, quantity AS buy_qty, 0::bigint AS sell_qty, amount AS buy_amt, 0::numeric AS sell_amt 
                FROM floorsheet_raw WHERE symbol = %s AND trade_time >= %s AND trade_time <= %s
                UNION ALL
                SELECT seller_broker AS broker_id, 0::bigint AS buy_qty, quantity AS sell_qty, 0::numeric AS buy_amt, amount AS sell_amt 
                FROM floorsheet_raw WHERE symbol = %s AND trade_time >= %s AND trade_time <= %s
            )
            SELECT 
                broker_id,
                SUM(buy_qty) AS buy_qty,
                SUM(sell_qty) AS sell_qty,
                SUM(buy_qty) - SUM(sell_qty) AS net_qty,
                SUM(buy_amt) AS buy_amt,
                SUM(sell_amt) AS sell_amt,
                SUM(buy_amt) - SUM(sell_amt) AS net_amt,
                ROUND(SUM(buy_amt) / NULLIF(SUM(buy_qty), 0), 2) AS buy_vwap,
                ROUND(SUM(sell_amt) / NULLIF(SUM(sell_qty), 0), 2) AS sell_vwap
            FROM b_scrip_trades
            GROUP BY broker_id
            ORDER BY SUM(buy_amt + sell_amt) DESC;
        """, (sym_clean, start_ts, end_ts, sym_clean, start_ts, end_ts))
        broker_rows = cur.fetchall()

        brokers = [
            {
                "broker_id": int(r["broker_id"]),
                "buy_quantity": int(r["buy_qty"]),
                "sell_quantity": int(r["sell_qty"]),
                "net_quantity": int(r["net_qty"]),
                "buy_amount": float(r["buy_amt"]),
                "sell_amount": float(r["sell_amt"]),
                "net_amount": float(r["net_amt"]),
                "buy_vwap": float(r["buy_vwap"] or 0),
                "sell_vwap": float(r["sell_vwap"] or 0),
                "market_share_pct": round((float(r["buy_amt"]) / total_turnover * 100), 2) if total_turnover > 0 else 0.0,
                "flow_status": "ACCUMULATING" if float(r["net_amt"]) >= 0 else "DISTRIBUTING"
            }
            for r in broker_rows
        ]

        # 3. Direct Counterparty Network Analysis
        cur.execute("""
            SELECT 
                buyer_broker,
                seller_broker,
                SUM(amount) AS trade_amount,
                SUM(quantity) AS trade_quantity,
                COUNT(*) AS trade_count
            FROM floorsheet_raw
            WHERE symbol = %s AND trade_time >= %s AND trade_time <= %s
            GROUP BY buyer_broker, seller_broker
            ORDER BY trade_amount DESC
            LIMIT 15;
        """, (sym_clean, start_ts, end_ts))
        routes = [
            {
                "buyer_broker": int(r["buyer_broker"]),
                "seller_broker": int(r["seller_broker"]),
                "amount": float(r["trade_amount"]),
                "quantity": int(r["trade_quantity"]),
                "trades": int(r["trade_count"])
            }
            for r in cur.fetchall()
        ]

        # 4. Intraday Timeline
        bucket_mins = 15
        if time_bucket == "5m": bucket_mins = 5
        elif time_bucket == "30m": bucket_mins = 30
        elif time_bucket == "1h": bucket_mins = 60

        cur.execute(f"""
            SELECT 
                TO_CHAR(trade_time, 'HH24') || ':' || 
                LPAD((FLOOR(EXTRACT(MINUTE FROM trade_time) / {bucket_mins}) * {bucket_mins})::TEXT, 2, '0') AS time_bucket,
                SUM(amount) AS turnover,
                SUM(quantity) AS volume,
                COUNT(*) AS trades_count,
                ROUND(SUM(amount) / NULLIF(SUM(quantity), 0), 2) AS bucket_vwap
            FROM floorsheet_raw
            WHERE symbol = %s AND trade_time >= %s AND trade_time <= %s
            GROUP BY time_bucket
            ORDER BY time_bucket ASC;
        """, (sym_clean, start_ts, end_ts))
        timeline = [
            {
                "bucket": r["time_bucket"],
                "turnover": float(r["turnover"]),
                "volume": int(r["volume"]),
                "trades": int(r["trades_count"]),
                "vwap": float(r["bucket_vwap"] or 0)
            }
            for r in cur.fetchall()
        ]

        # 5. Whale Deals
        cur.execute("""
            SELECT 
                contract_id,
                buyer_broker,
                seller_broker,
                quantity,
                rate,
                amount,
                TO_CHAR(trade_time, 'HH24:MI:SS') AS trade_time_str
            FROM floorsheet_raw
            WHERE symbol = %s 
              AND trade_time >= %s AND trade_time <= %s
              AND (quantity >= %s OR amount >= %s)
            ORDER BY trade_time DESC, contract_id DESC
            LIMIT 50;
        """, (sym_clean, start_ts, end_ts, whale_threshold_qty, whale_threshold_amt))
        whale_deals = [
            {
                "contract_id": int(r["contract_id"]),
                "buyer_broker": int(r["buyer_broker"]),
                "seller_broker": int(r["seller_broker"]),
                "quantity": int(r["quantity"]),
                "rate": float(r["rate"]),
                "amount": float(r["amount"]),
                "trade_time": r["trade_time_str"]
            }
            for r in cur.fetchall()
        ]

        cur.close()
        conn.close()

        return {
            "symbol": sym_clean,
            "date": date,
            "time_window": {"start": start_time or "11:00:00", "end": end_time or "15:00:00"},
            "summary": {
                "turnover": total_turnover,
                "volume": total_volume,
                "trades_count": total_trades,
                "vwap": float(summary["vwap"] or 0),
                "high_rate": float(summary["high_rate"] or 0),
                "low_rate": float(summary["low_rate"] or 0),
                "active_brokers_count": len(brokers),
                "whale_deals_count": len(whale_deals)
            },
            "brokers": brokers,
            "counterparty_routes": routes,
            "timeline": timeline,
            "whale_deals": whale_deals
        }

    except Exception as e:
        cur.close()
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))

# Mount Routers
app.include_router(router, prefix="/api/script")
app.include_router(router, prefix="/script")
app.include_router(router, prefix="/api")
app.include_router(router, prefix="")
