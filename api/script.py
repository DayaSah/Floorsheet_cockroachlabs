import os
import math
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, APIRouter, Query, HTTPException
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

app = FastAPI(title="NEPSE Floorsheet Scrip (Stock) Analytics API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter()

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
    """Builds timestamp bounds matching stored local clock times."""
    s_time = start_time.strip() if isinstance(start_time, str) and start_time.strip() else "00:00:00"
    e_time = end_time.strip() if isinstance(end_time, str) and end_time.strip() else "23:59:59"
    
    if len(s_time) == 5:
        s_time += ":00"
    if len(e_time) == 5:
        e_time += ":59"
        
    start_ts = f"{date_str} {s_time}"
    end_ts = f"{date_str} {e_time}"
    return start_ts, end_ts

@router.get("/dates")
def get_available_dates():
    """Returns available trading dates with macro telemetry."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT 
                trade_time::date AS trading_date,
                COUNT(*) AS total_trades,
                COUNT(DISTINCT symbol) AS active_scrips,
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
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    start_time: str = Query(None, description="Start time HH:MM:SS (Optional)"),
    end_time: str = Query(None, description="End time HH:MM:SS (Optional)"),
    min_turnover: float = Query(0.0, description="Minimum turnover threshold in NPR")
):
    """
    Computes macro market KPIs and the complete scrip leaderboard matrix
    with VWAP, High/Low, LTP, Top Net Buyer Broker, Top Net Seller Broker,
    and Top 3 Buyer Concentration (%).
    """
    min_turn = float(min_turnover) if isinstance(min_turnover, (int, float, str)) and not hasattr(min_turnover, 'default') else 0.0
    start_ts, end_ts = build_time_bounds(date, start_time, end_time)
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # 1. Market Scrip Aggregates
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
                    "active_scrips_count": 0
                },
                "scrips": []
            }

        # 2. Single-Pass Scrip Aggregation with Window Functions
        query = """
            WITH filtered_trades AS (
                SELECT contract_id, symbol, buyer_broker, seller_broker, quantity, rate, amount, trade_time
                FROM floorsheet_raw
                WHERE trade_time >= %s AND trade_time <= %s
            ),
            scrip_broker_flows AS (
                SELECT symbol, buyer_broker AS broker_id, quantity AS buy_qty, 0::bigint AS sell_qty, amount AS buy_amt, 0::numeric AS sell_amt FROM filtered_trades
                UNION ALL
                SELECT symbol, seller_broker AS broker_id, 0::bigint AS buy_qty, quantity AS sell_qty, 0::numeric AS buy_amt, amount AS sell_amt FROM filtered_trades
            ),
            broker_scrip_agg AS (
                SELECT 
                    symbol, broker_id,
                    SUM(buy_qty) AS buy_qty, SUM(sell_qty) AS sell_qty,
                    SUM(buy_amt) AS buy_amt, SUM(sell_amt) AS sell_amt,
                    (SUM(buy_qty) - SUM(sell_qty)) AS net_qty,
                    (SUM(buy_amt) - SUM(sell_amt)) AS net_amt
                FROM scrip_broker_flows
                GROUP BY symbol, broker_id
            ),
            ranked_top_buyers AS (
                SELECT symbol, broker_id AS top_buyer_id, buy_qty AS top_buyer_qty, buy_amt AS top_buyer_amt, net_qty AS top_buyer_net_qty, net_amt AS top_buyer_net_amt,
                       ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY net_amt DESC) AS rn
                FROM broker_scrip_agg WHERE net_amt > 0
            ),
            ranked_top_sellers AS (
                SELECT symbol, broker_id AS top_seller_id, sell_qty AS top_seller_qty, sell_amt AS top_seller_amt, net_qty AS top_seller_net_qty, net_amt AS top_seller_net_amt,
                       ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY net_amt ASC) AS rn
                FROM broker_scrip_agg WHERE net_amt < 0
            ),
            top3_concentration AS (
                SELECT 
                    symbol,
                    SUM(buy_qty) AS top3_buy_volume
                FROM (
                    SELECT symbol, buy_qty,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY buy_qty DESC) AS rn
                    FROM broker_scrip_agg WHERE buy_qty > 0
                ) sub WHERE rn <= 3 GROUP BY symbol
            ),
            last_traded_rates AS (
                SELECT symbol, rate AS ltp,
                       ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY trade_time DESC, contract_id DESC) AS rn
                FROM filtered_trades
            ),
            scrip_summary AS (
                SELECT 
                    symbol,
                    COUNT(*) AS total_trades,
                    SUM(quantity) AS total_quantity,
                    SUM(amount) AS total_turnover,
                    MAX(rate) AS high_price,
                    MIN(rate) AS low_price,
                    ROUND(SUM(amount) / NULLIF(SUM(quantity), 0), 2) AS vwap
                FROM filtered_trades
                GROUP BY symbol
            )
            SELECT 
                s.*,
                ltr.ltp,
                tb.top_buyer_id, tb.top_buyer_qty, tb.top_buyer_amt, tb.top_buyer_net_qty, tb.top_buyer_net_amt,
                ts.top_seller_id, ts.top_seller_qty, ts.top_seller_amt, ts.top_seller_net_qty, ts.top_seller_net_amt,
                ROUND((t3.top3_buy_volume / NULLIF(s.total_quantity, 0) * 100.0), 2) AS top3_concentration_pct
            FROM scrip_summary s
            LEFT JOIN last_traded_rates ltr ON s.symbol = ltr.symbol AND ltr.rn = 1
            LEFT JOIN ranked_top_buyers tb ON s.symbol = tb.symbol AND tb.rn = 1
            LEFT JOIN ranked_top_sellers ts ON s.symbol = ts.symbol AND ts.rn = 1
            LEFT JOIN top3_concentration t3 ON s.symbol = t3.symbol
            WHERE s.total_turnover >= %s
            ORDER BY s.total_turnover DESC;
        """
        cur.execute(query, (start_ts, end_ts, min_turn))
        scrip_rows = cur.fetchall()
        cur.close()
        conn.close()

        scrips = []
        for r in scrip_rows:
            turnover = float(r["total_turnover"])
            market_share = round((turnover / total_market_turnover * 100.0), 2) if total_market_turnover > 0 else 0.0

            scrips.append({
                "symbol": r["symbol"],
                "turnover": turnover,
                "quantity": int(r["total_quantity"]),
                "trades_count": int(r["total_trades"]),
                "high_price": float(r["high_price"]),
                "low_price": float(r["low_price"]),
                "ltp": float(r["ltp"]) if r["ltp"] is not None else float(r["high_price"]),
                "vwap": float(r["vwap"]),
                "price_spread": round(float(r["high_price"]) - float(r["low_price"]), 2),
                "market_share_pct": market_share,
                "top3_concentration_pct": float(r["top3_concentration_pct"]) if r["top3_concentration_pct"] is not None else 0.0,
                "top_net_buyer": {
                    "broker_id": int(r["top_buyer_id"]),
                    "net_qty": int(r["top_buyer_net_qty"]),
                    "net_value": float(r["top_buyer_net_amt"]),
                    "total_buy_qty": int(r["top_buyer_qty"])
                } if r["top_buyer_id"] else None,
                "top_net_seller": {
                    "broker_id": int(r["top_seller_id"]),
                    "net_qty": int(r["top_seller_net_qty"]),
                    "net_value": float(r["top_seller_net_amt"]),
                    "total_sell_qty": int(r["top_seller_qty"])
                } if r["top_seller_id"] else None
            })

        return {
            "date": date,
            "time_window": {"start": start_time or "11:00:00", "end": end_time or "15:00:00"},
            "market_summary": {
                "total_market_turnover": total_market_turnover,
                "total_market_shares": total_market_quantity,
                "total_market_trades": total_market_trades,
                "active_scrips_count": len(scrips)
            },
            "scrips": scrips
        }

    except Exception as e:
        cur.close()
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{symbol}")
def get_scrip_detail(
    symbol: str,
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    start_time: str = Query(None, description="Start time HH:MM:SS (Optional)"),
    end_time: str = Query(None, description="End time HH:MM:SS (Optional)"),
    bucket: str = Query("15m", description="Timeline bucket: 5m, 15m, 30m, 1h")
):
    """
    Returns deep institutional intelligence for a single stock:
    1. Scrip Summary (Turnover, Shares, Trades, OHLC, VWAP, Range)
    2. Intraday Price & Volume / Flow Timeline (Chart data)
    3. Broker Participation & Flow Matrix (Buy/Sell/Net Qty, Buy/Sell VWAP, Flow Status)
    4. Counterparty Trade Route Matrix (Broker-to-Broker flow)
    5. Whale & Block Deal Scanner (Top transaction tickets)
    """
    sym = symbol.strip().upper()
    start_ts, end_ts = build_time_bounds(date, start_time, end_time)
    conn = get_db_connection()
    cur = conn.cursor()

    bucket_str = bucket if isinstance(bucket, str) else "15m"
    bucket_mins = 15
    if bucket_str == "5m":
        bucket_mins = 5
    elif bucket_str == "30m":
        bucket_mins = 30
    elif bucket_str == "1h":
        bucket_mins = 60

    try:
        # High-performance indexed single-pass CTE using idx_symbol_time (symbol, trade_time)
        single_pass_sql = f"""
            WITH raw_scrip_trades AS (
                SELECT contract_id, symbol, buyer_broker, seller_broker, quantity, rate, amount, trade_time
                FROM floorsheet_raw
                WHERE symbol = %s AND trade_time >= %s AND trade_time <= %s
            ),
            broker_side_flows AS (
                SELECT buyer_broker AS broker_id, quantity AS buy_qty, 0::bigint AS sell_qty, amount AS buy_amt, 0::numeric AS sell_amt FROM raw_scrip_trades
                UNION ALL
                SELECT seller_broker AS broker_id, 0::bigint AS buy_qty, quantity AS sell_qty, 0::numeric AS buy_amt, amount AS sell_amt FROM raw_scrip_trades
            ),
            broker_agg AS (
                SELECT 
                    broker_id,
                    SUM(buy_qty) AS buy_qty,
                    SUM(sell_qty) AS sell_qty,
                    (SUM(buy_qty) - SUM(sell_qty)) AS net_flow_qty,
                    SUM(buy_amt) AS buy_value,
                    SUM(sell_amt) AS sell_value,
                    (SUM(buy_amt) - SUM(sell_amt)) AS net_flow_value,
                    ROUND(SUM(buy_amt) / NULLIF(SUM(buy_qty), 0), 2) AS buy_vwap,
                    ROUND(SUM(sell_amt) / NULLIF(SUM(sell_qty), 0), 2) AS sell_vwap,
                    CASE WHEN (SUM(buy_amt) - SUM(sell_amt)) >= 0 THEN 'NET BUYING' ELSE 'NET SELLING' END AS flow_status
                FROM broker_side_flows
                GROUP BY broker_id
            ),
            counterparty_agg AS (
                SELECT 
                    buyer_broker,
                    seller_broker,
                    SUM(amount) AS value,
                    SUM(quantity) AS quantity,
                    COUNT(*) AS trades_count,
                    ROUND(SUM(amount) / NULLIF(SUM(quantity), 0), 2) AS route_vwap
                FROM raw_scrip_trades
                GROUP BY buyer_broker, seller_broker
                ORDER BY value DESC
                LIMIT 15
            ),
            timeline_agg AS (
                SELECT 
                    TO_CHAR(trade_time, 'HH24') || ':' || 
                    LPAD((FLOOR(EXTRACT(MINUTE FROM trade_time) / {bucket_mins}) * {bucket_mins})::TEXT, 2, '0') AS time_bucket,
                    MIN(rate) AS low_price,
                    MAX(rate) AS high_price,
                    ROUND(SUM(amount) / NULLIF(SUM(quantity), 0), 2) AS vwap,
                    SUM(quantity) AS volume,
                    SUM(amount) AS turnover,
                    COUNT(*) AS trades_count
                FROM raw_scrip_trades
                GROUP BY time_bucket
                ORDER BY time_bucket ASC
            ),
            whales_agg AS (
                SELECT 
                    contract_id,
                    buyer_broker,
                    seller_broker,
                    quantity,
                    rate,
                    amount,
                    TO_CHAR(trade_time, 'HH24:MI:SS') AS trade_time_str
                FROM raw_scrip_trades
                WHERE quantity >= 1000 OR amount >= 500000
                ORDER BY amount DESC
                LIMIT 50
            ),
            last_trade AS (
                SELECT rate AS ltp
                FROM raw_scrip_trades
                ORDER BY trade_time DESC, contract_id DESC
                LIMIT 1
            ),
            summary_agg AS (
                SELECT 
                    COUNT(*) AS total_trades,
                    SUM(quantity) AS total_quantity,
                    SUM(amount) AS total_turnover,
                    MAX(rate) AS high_price,
                    MIN(rate) AS low_price,
                    ROUND(SUM(amount) / NULLIF(SUM(quantity), 0), 2) AS vwap
                FROM raw_scrip_trades
            )
            SELECT 
                (SELECT row_to_json(s) FROM summary_agg s) AS summary,
                (SELECT ltp FROM last_trade) AS ltp,
                (SELECT json_agg(b) FROM (SELECT * FROM broker_agg ORDER BY (buy_value + sell_value) DESC) b) AS brokers,
                (SELECT json_agg(c) FROM counterparty_agg c) AS counterparties,
                (SELECT json_agg(t) FROM timeline_agg t) AS timeline,
                (SELECT json_agg(w) FROM whales_agg w) AS whales;
        """
        cur.execute(single_pass_sql, (sym, start_ts, end_ts))
        result = cur.fetchone()
        cur.close()
        conn.close()

        summary_raw = result["summary"] or {}
        ltp_val = result["ltp"]
        brokers_raw = result["brokers"] or []
        cp_raw = result["counterparties"] or []
        timeline_raw = result["timeline"] or []
        whales_raw = result["whales"] or []

        total_turnover = float(summary_raw.get("total_turnover") or 0.0)
        total_quantity = int(summary_raw.get("total_quantity") or 0)
        total_trades = int(summary_raw.get("total_trades") or 0)
        high_price = float(summary_raw.get("high_price") or 0.0)
        low_price = float(summary_raw.get("low_price") or 0.0)
        vwap = float(summary_raw.get("vwap") or 0.0)
        ltp = float(ltp_val) if ltp_val is not None else high_price

        top_buyer = max([b for b in brokers_raw if b["net_flow_value"] > 0], key=lambda x: x["net_flow_value"], default=None)
        top_seller = min([b for b in brokers_raw if b["net_flow_value"] < 0], key=lambda x: x["net_flow_value"], default=None)

        # Top 3 concentration
        sorted_by_buy = sorted(brokers_raw, key=lambda x: x["buy_qty"], reverse=True)
        top3_buy_vol = sum(b["buy_qty"] for b in sorted_by_buy[:3])
        top3_concentration_pct = round((top3_buy_vol / total_quantity * 100.0), 2) if total_quantity > 0 else 0.0

        brokers = [
            {
                "broker_id": int(r["broker_id"]),
                "buy_qty": int(r["buy_qty"]),
                "sell_qty": int(r["sell_qty"]),
                "net_flow_qty": int(r["net_flow_qty"]),
                "buy_value": float(r["buy_value"]),
                "sell_value": float(r["sell_value"]),
                "net_flow_value": float(r["net_flow_value"]),
                "buy_vwap": float(r["buy_vwap"]) if r["buy_vwap"] else 0.0,
                "sell_vwap": float(r["sell_vwap"]) if r["sell_vwap"] else 0.0,
                "flow_status": r["flow_status"],
                "buy_share_pct": round((float(r["buy_value"]) / total_turnover * 100.0), 2) if total_turnover > 0 else 0.0,
                "sell_share_pct": round((float(r["sell_value"]) / total_turnover * 100.0), 2) if total_turnover > 0 else 0.0
            }
            for r in brokers_raw
        ]

        counterparties = [
            {
                "buyer_broker": int(r["buyer_broker"]),
                "seller_broker": int(r["seller_broker"]),
                "value": float(r["value"]),
                "quantity": int(r["quantity"]),
                "trades_count": int(r["trades_count"]),
                "route_vwap": float(r["route_vwap"]) if r["route_vwap"] else 0.0,
                "share_pct": round((float(r["value"]) / total_turnover * 100.0), 2) if total_turnover > 0 else 0.0
            }
            for r in cp_raw
        ]

        timeline = [
            {
                "time_label": r["time_bucket"],
                "low_price": float(r["low_price"]),
                "high_price": float(r["high_price"]),
                "vwap": float(r["vwap"]),
                "volume": int(r["volume"]),
                "turnover": float(r["turnover"]),
                "trades_count": int(r["trades_count"])
            }
            for r in timeline_raw
        ]

        whales = [
            {
                "contract_id": int(r["contract_id"]),
                "buyer_broker": int(r["buyer_broker"]),
                "seller_broker": int(r["seller_broker"]),
                "quantity": int(r["quantity"]),
                "rate": float(r["rate"]),
                "amount": float(r["amount"]),
                "trade_time": r["trade_time_str"],
                "share_pct": round((float(r["amount"]) / total_turnover * 100.0), 2) if total_turnover > 0 else 0.0
            }
            for r in whales_raw
        ]

        peak_window = max(timeline, key=lambda x: x["turnover"])["time_label"] if timeline else None

        return {
            "symbol": sym,
            "date": date,
            "time_window": {"start": start_time or "11:00:00", "end": end_time or "15:00:00"},
            "bucket": bucket_str,
            "summary": {
                "turnover": total_turnover,
                "quantity": total_quantity,
                "trades_count": total_trades,
                "high_price": high_price,
                "low_price": low_price,
                "ltp": ltp,
                "vwap": vwap,
                "price_spread": round(high_price - low_price, 2),
                "top3_concentration_pct": top3_concentration_pct,
                "top_net_buyer": {
                    "broker_id": int(top_buyer["broker_id"]),
                    "net_qty": int(top_buyer["net_flow_qty"]),
                    "net_value": float(top_buyer["net_flow_value"])
                } if top_buyer else None,
                "top_net_seller": {
                    "broker_id": int(top_seller["broker_id"]),
                    "net_qty": int(top_seller["net_flow_qty"]),
                    "net_value": float(top_seller["net_flow_value"])
                } if top_seller else None,
                "peak_trading_window": peak_window
            },
            "timeline": timeline,
            "brokers": brokers,
            "counterparties": counterparties,
            "whales": whales
        }

    except Exception as e:
        cur.close()
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))

# Mount router across all possible prefix routes to ensure 100% compatibility with Vercel rewrites & local proxies
app.include_router(router, prefix="/api/script")
app.include_router(router, prefix="/script")
app.include_router(router, prefix="/api")
app.include_router(router, prefix="")
