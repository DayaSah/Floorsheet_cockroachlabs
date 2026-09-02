import os
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, APIRouter, Query, HTTPException
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

app = FastAPI(title="NEPSE Multi-Day Broker & Scrip Flow Analytics API")
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
        return psycopg2.connect(uri, cursor_factory=RealDictCursor)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection error: {str(e)}")

def get_trading_dates(conn):
    """Fetch distinct available trading dates from daily summary layer in desc order."""
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT trade_date
        FROM daily_broker_scrip_summary
        ORDER BY trade_date DESC;
    """)
    dates = [row['trade_date'].strftime("%Y-%m-%d") for row in cur.fetchall()]
    cur.close()
    return dates

def resolve_date_window(preset: str, start_date: str = None, end_date: str = None, conn=None):
    """
    Resolves presets ('3D', '5D', '10D', '20D', 'custom') to actual available trading dates.
    """
    all_dates = get_trading_dates(conn)
    if not all_dates:
        raise HTTPException(status_code=404, detail="No historical summary data available in database.")

    preset_clean = (preset or "5D").upper().strip()

    if preset_clean in ["3D", "5D", "10D", "20D"]:
        n_days = {"3D": 3, "5D": 5, "10D": 10, "20D": 20}[preset_clean]
        selected_dates = all_dates[:n_days]
        s_date = selected_dates[-1]
        e_date = selected_dates[0]
        return s_date, e_date, len(selected_dates), selected_dates
    elif preset_clean == "CUSTOM" and start_date and end_date:
        selected_dates = [d for d in all_dates if start_date <= d <= end_date]
        if not selected_dates:
            raise HTTPException(status_code=400, detail=f"No trading sessions found between {start_date} and {end_date}.")
        return selected_dates[-1], selected_dates[0], len(selected_dates), selected_dates
    else:
        # Default to 5 trading days
        selected_dates = all_dates[:5]
        return selected_dates[-1], selected_dates[0], len(selected_dates), selected_dates

@router.get("/dates")
def get_multiday_dates():
    """Returns available trading dates and session statistics."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT 
                trade_date,
                COUNT(DISTINCT symbol) AS active_scrips,
                COUNT(DISTINCT broker_id) AS active_brokers,
                COALESCE(SUM(buy_amt), 0) AS total_turnover,
                COALESCE(SUM(buy_qty), 0) AS total_volume,
                COALESCE(SUM(trades_count), 0) AS total_trades
            FROM daily_broker_scrip_summary
            GROUP BY trade_date
            ORDER BY trade_date DESC;
        """)
        rows = cur.fetchall()
        return [
            {
                "date": r["trade_date"].strftime("%Y-%m-%d"),
                "active_scrips": r["active_scrips"],
                "active_brokers": r["active_brokers"],
                "total_turnover": float(r["total_turnover"]),
                "total_volume": int(r["total_volume"]),
                "total_trades": int(r["total_trades"])
            }
            for r in rows
        ]
    finally:
        cur.close()
        conn.close()

@router.get("/overview")
def get_multiday_overview(
    preset: str = Query("5D", description="Date preset: 3D, 5D, 10D, 20D, custom"),
    start_date: str = Query(None, description="Start date YYYY-MM-DD for custom preset"),
    end_date: str = Query(None, description="End date YYYY-MM-DD for custom preset"),
    min_turnover: float = Query(0.0, description="Min stock turnover filter in NPR"),
    limit: int = Query(100, ge=10, le=500, description="Max records returned")
):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        s_date, e_date, session_count, active_dates = resolve_date_window(preset, start_date, end_date, conn)

        # 1. Macro Market Summary over the window
        cur.execute("""
            SELECT 
                COALESCE(SUM(buy_amt), 0) AS market_turnover,
                COALESCE(SUM(buy_qty), 0) AS market_shares,
                COALESCE(SUM(trades_count), 0) AS market_trades,
                COUNT(DISTINCT symbol) AS active_scrips,
                COUNT(DISTINCT broker_id) AS active_brokers
            FROM daily_broker_scrip_summary
            WHERE trade_date >= %s AND trade_date <= %s;
        """, (s_date, e_date))
        macro = cur.fetchone()
        market_turnover = float(macro["market_turnover"])
        market_shares = int(macro["market_shares"])
        market_trades = int(macro["market_trades"])

        # 2. Multi-Day Broker Leaderboard with Persistence & Streaks
        cur.execute("""
            WITH broker_daily AS (
                SELECT 
                    broker_id,
                    trade_date,
                    SUM(buy_amt) AS d_buy_amt,
                    SUM(sell_amt) AS d_sell_amt,
                    SUM(buy_qty) AS d_buy_qty,
                    SUM(sell_qty) AS d_sell_qty,
                    SUM(buy_amt) - SUM(sell_amt) AS d_net_amt,
                    SUM(buy_qty) - SUM(sell_qty) AS d_net_qty
                FROM daily_broker_scrip_summary
                WHERE trade_date >= %s AND trade_date <= %s
                GROUP BY broker_id, trade_date
            ),
            broker_agg AS (
                SELECT 
                    broker_id,
                    SUM(d_buy_amt) AS buy_amt,
                    SUM(d_sell_amt) AS sell_amt,
                    SUM(d_buy_amt + d_sell_amt) AS gross_activity,
                    SUM(d_buy_amt) - SUM(d_sell_amt) AS net_flow_value,
                    SUM(d_buy_qty) AS buy_qty,
                    SUM(d_sell_qty) AS sell_qty,
                    SUM(d_buy_qty) - SUM(d_sell_qty) AS net_flow_qty,
                    COUNT(CASE WHEN d_net_amt > 0 THEN 1 END) AS positive_days,
                    COUNT(CASE WHEN d_net_amt < 0 THEN 1 END) AS negative_days,
                    COUNT(DISTINCT trade_date) AS active_days
                FROM broker_daily
                GROUP BY broker_id
            ),
            broker_scrips_count AS (
                SELECT broker_id, COUNT(DISTINCT symbol) AS active_scrips
                FROM daily_broker_scrip_summary
                WHERE trade_date >= %s AND trade_date <= %s
                GROUP BY broker_id
            )
            SELECT 
                a.broker_id,
                a.gross_activity,
                a.buy_amt,
                a.sell_amt,
                a.net_flow_value,
                a.buy_qty,
                a.sell_qty,
                a.net_flow_qty,
                a.positive_days,
                a.negative_days,
                a.active_days,
                COALESCE(s.active_scrips, 0) AS active_scrips,
                ROUND(a.buy_amt / NULLIF(a.buy_qty, 0), 2) AS buy_vwap,
                ROUND(a.sell_amt / NULLIF(a.sell_qty, 0), 2) AS sell_vwap
            FROM broker_agg a
            LEFT JOIN broker_scrips_count s ON a.broker_id = s.broker_id
            ORDER BY a.gross_activity DESC;
        """, (s_date, e_date, s_date, e_date))
        broker_rows = cur.fetchall()

        brokers = []
        for r in broker_rows:
            buy_val = float(r["buy_amt"])
            sell_val = float(r["sell_amt"])
            gross = float(r["gross_activity"])
            net_val = float(r["net_flow_value"])
            pos_days = int(r["positive_days"])
            act_days = int(r["active_days"])
            pers_pct = round((pos_days / session_count * 100.0), 1) if session_count > 0 else 0.0

            brokers.append({
                "broker_id": int(r["broker_id"]),
                "gross_activity": gross,
                "buy_amount": buy_val,
                "sell_amount": sell_val,
                "net_flow_value": net_val,
                "buy_quantity": int(r["buy_qty"]),
                "sell_quantity": int(r["sell_qty"]),
                "net_flow_quantity": int(r["net_flow_qty"]),
                "buy_vwap": float(r["buy_vwap"] or 0),
                "sell_vwap": float(r["sell_vwap"] or 0),
                "positive_days": pos_days,
                "negative_days": int(r["negative_days"]),
                "active_days": act_days,
                "buy_persistence_pct": pers_pct,
                "active_scrips": int(r["active_scrips"]),
                "market_share_pct": round((buy_val / market_turnover * 100.0), 2) if market_turnover > 0 else 0.0,
                "flow_status": "NET BUYING" if net_val >= 0 else "NET SELLING"
            })

        # 3. Multi-Day Scrip Leaderboard
        cur.execute("""
            WITH scrip_totals AS (
                SELECT 
                    symbol,
                    SUM(buy_amt) AS turnover,
                    SUM(buy_qty) AS volume,
                    SUM(trades_count) AS trades_count,
                    ROUND(SUM(buy_amt) / NULLIF(SUM(buy_qty), 0), 2) AS multi_day_vwap
                FROM daily_broker_scrip_summary
                WHERE trade_date >= %s AND trade_date <= %s
                GROUP BY symbol
                HAVING SUM(buy_amt) >= %s
            ),
            broker_scrip_flows AS (
                SELECT 
                    symbol,
                    broker_id,
                    SUM(buy_qty) - SUM(sell_qty) AS net_qty,
                    SUM(buy_amt) - SUM(sell_amt) AS net_val,
                    SUM(buy_qty) AS total_bought_qty
                FROM daily_broker_scrip_summary
                WHERE trade_date >= %s AND trade_date <= %s
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
                s.multi_day_vwap,
                rb.broker_id AS top_buyer_id,
                rb.net_qty AS top_buyer_net_qty,
                rs.broker_id AS top_seller_id,
                rs.net_qty AS top_seller_net_qty,
                COALESCE(c.top3_volume, 0) AS top3_volume
            FROM scrip_totals s
            LEFT JOIN ranked_buyers rb ON s.symbol = rb.symbol AND rb.rn = 1
            LEFT JOIN ranked_sellers rs ON s.symbol = rs.symbol AND rs.rn = 1
            LEFT JOIN top3_concentration c ON s.symbol = c.symbol
            ORDER BY s.turnover DESC
            LIMIT %s;
        """, (s_date, e_date, min_turnover, s_date, e_date, limit))
        scrip_rows = cur.fetchall()

        scrips = []
        for r in scrip_rows:
            turnover = float(r["turnover"])
            vol = int(r["volume"])
            top3_vol = int(r["top3_volume"])
            conc_pct = round((top3_vol / vol * 100.0), 2) if vol > 0 else 0.0

            scrips.append({
                "symbol": r["symbol"],
                "turnover": turnover,
                "volume": vol,
                "trades_count": int(r["trades_count"]),
                "multi_day_vwap": float(r["multi_day_vwap"] or 0),
                "market_share_pct": round((turnover / market_turnover * 100.0), 2) if market_turnover > 0 else 0.0,
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
            "period": {
                "preset": (preset or "5D").upper().strip(),
                "start_date": s_date,
                "end_date": e_date,
                "trading_sessions_count": session_count,
                "sessions_list": active_dates
            },
            "market_summary": {
                "total_market_turnover": market_turnover,
                "total_market_shares": market_shares,
                "total_market_trades": market_trades,
                "active_scrips_count": int(macro["active_scrips"]),
                "active_brokers_count": int(macro["active_brokers"])
            },
            "brokers": brokers,
            "scrips": scrips
        }
    finally:
        cur.close()
        conn.close()

@router.get("/broker/{broker_id}")
def get_multiday_broker_detail(
    broker_id: int,
    preset: str = Query("5D", description="Date preset: 3D, 5D, 10D, 20D, custom"),
    start_date: str = Query(None, description="Start date YYYY-MM-DD for custom preset"),
    end_date: str = Query(None, description="End date YYYY-MM-DD for custom preset")
):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        s_date, e_date, session_count, active_dates = resolve_date_window(preset, start_date, end_date, conn)

        # 1. Broker Multi-Day Summary
        cur.execute("""
            SELECT 
                COALESCE(SUM(buy_amt), 0) AS buy_amount,
                COALESCE(SUM(sell_amt), 0) AS sell_amount,
                COALESCE(SUM(buy_qty), 0) AS buy_quantity,
                COALESCE(SUM(sell_qty), 0) AS sell_quantity,
                COALESCE(SUM(trades_count), 0) AS trades_count,
                COUNT(DISTINCT symbol) AS active_scrips
            FROM daily_broker_scrip_summary
            WHERE broker_id = %s AND trade_date >= %s AND trade_date <= %s;
        """, (broker_id, s_date, e_date))
        b_sum = cur.fetchone()
        buy_amt = float(b_sum["buy_amount"])
        sell_amt = float(b_sum["sell_amount"])
        gross = buy_amt + sell_amt
        net_val = buy_amt - sell_amt
        buy_qty = int(b_sum["buy_quantity"])
        sell_qty = int(b_sum["sell_quantity"])

        # 2. Daily Flow Timeline
        cur.execute("""
            SELECT 
                trade_date,
                SUM(buy_amt) AS buy_amt,
                SUM(sell_amt) AS sell_amt,
                SUM(buy_amt) - SUM(sell_amt) AS net_amt,
                SUM(buy_qty) AS buy_qty,
                SUM(sell_qty) AS sell_qty,
                SUM(buy_qty) - SUM(sell_qty) AS net_qty,
                COUNT(DISTINCT symbol) AS scrips_count
            FROM daily_broker_scrip_summary
            WHERE broker_id = %s AND trade_date >= %s AND trade_date <= %s
            GROUP BY trade_date
            ORDER BY trade_date ASC;
        """, (broker_id, s_date, e_date))
        timeline_rows = cur.fetchall()

        timeline = [
            {
                "date": r["trade_date"].strftime("%Y-%m-%d"),
                "buy_amount": float(r["buy_amt"]),
                "sell_amount": float(r["sell_amt"]),
                "net_amount": float(r["net_amt"]),
                "buy_quantity": int(r["buy_qty"]),
                "sell_quantity": int(r["sell_qty"]),
                "net_quantity": int(r["net_qty"]),
                "scrips_count": int(r["scrips_count"])
            }
            for r in timeline_rows
        ]

        # 3. Complete Traded Scrips Portfolio
        cur.execute("""
            SELECT 
                symbol,
                SUM(buy_qty) AS buy_qty,
                SUM(sell_qty) AS sell_qty,
                SUM(buy_qty) - SUM(sell_qty) AS net_qty,
                SUM(buy_amt) AS buy_amt,
                SUM(sell_amt) AS sell_amt,
                SUM(buy_amt) - SUM(sell_amt) AS net_amt,
                ROUND(SUM(buy_amt) / NULLIF(SUM(buy_qty), 0), 2) AS buy_vwap,
                ROUND(SUM(sell_amt) / NULLIF(SUM(sell_qty), 0), 2) AS sell_vwap,
                COUNT(CASE WHEN buy_amt > sell_amt THEN 1 END) AS buy_days,
                COUNT(DISTINCT trade_date) AS active_days
            FROM daily_broker_scrip_summary
            WHERE broker_id = %s AND trade_date >= %s AND trade_date <= %s
            GROUP BY symbol
            ORDER BY SUM(buy_amt + sell_amt) DESC;
        """, (broker_id, s_date, e_date))
        scrip_rows = cur.fetchall()

        scrips = []
        for r in scrip_rows:
            b_val = float(r["buy_amt"])
            s_val = float(r["sell_amt"])
            n_val = float(r["net_amt"])
            b_days = int(r["buy_days"])
            scrips.append({
                "symbol": r["symbol"],
                "buy_quantity": int(r["buy_qty"]),
                "sell_quantity": int(r["sell_qty"]),
                "net_quantity": int(r["net_qty"]),
                "buy_amount": b_val,
                "sell_amount": s_val,
                "net_amount": n_val,
                "buy_vwap": float(r["buy_vwap"] or 0),
                "sell_vwap": float(r["sell_vwap"] or 0),
                "buy_days": b_days,
                "active_days": int(r["active_days"]),
                "persistence_pct": round((b_days / session_count * 100.0), 1) if session_count > 0 else 0.0,
                "flow_status": "🟢 ACCUMULATING" if n_val >= 0 else "🔴 DISTRIBUTING"
            })

        return {
            "broker_id": broker_id,
            "period": {
                "start_date": s_date,
                "end_date": e_date,
                "trading_sessions_count": session_count
            },
            "summary": {
                "gross_activity": gross,
                "buy_amount": buy_amt,
                "sell_amount": sell_amt,
                "net_flow_value": net_val,
                "buy_quantity": buy_qty,
                "sell_quantity": sell_qty,
                "net_flow_quantity": buy_qty - sell_qty,
                "trades_count": int(b_sum["trades_count"]),
                "active_scrips_count": int(b_sum["active_scrips"]),
                "buy_vwap": round(buy_amt / buy_qty, 2) if buy_qty > 0 else 0.0,
                "sell_vwap": round(sell_amt / sell_qty, 2) if sell_qty > 0 else 0.0
            },
            "timeline": timeline,
            "scrips": scrips
        }
    finally:
        cur.close()
        conn.close()

@router.get("/scrip/{symbol}")
def get_multiday_scrip_detail(
    symbol: str,
    preset: str = Query("5D", description="Date preset: 3D, 5D, 10D, 20D, custom"),
    start_date: str = Query(None, description="Start date YYYY-MM-DD for custom preset"),
    end_date: str = Query(None, description="End date YYYY-MM-DD for custom preset")
):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        s_date, e_date, session_count, active_dates = resolve_date_window(preset, start_date, end_date, conn)
        sym_clean = symbol.strip().upper()

        # 1. Scrip Multi-Day Summary
        cur.execute("""
            SELECT 
                COALESCE(SUM(buy_amt), 0) AS total_turnover,
                COALESCE(SUM(buy_qty), 0) AS total_volume,
                COALESCE(SUM(trades_count), 0) AS total_trades,
                COUNT(DISTINCT broker_id) AS active_brokers,
                ROUND(SUM(buy_amt) / NULLIF(SUM(buy_qty), 0), 2) AS multi_day_vwap
            FROM daily_broker_scrip_summary
            WHERE symbol = %s AND trade_date >= %s AND trade_date <= %s;
        """, (sym_clean, s_date, e_date))
        s_sum = cur.fetchone()
        turnover = float(s_sum["total_turnover"])
        volume = int(s_sum["total_volume"])

        # 2. Day-by-Day Daily Trajectory
        cur.execute("""
            SELECT 
                trade_date,
                SUM(buy_amt) AS turnover,
                SUM(buy_qty) AS volume,
                SUM(trades_count) AS trades_count,
                ROUND(SUM(buy_amt) / NULLIF(SUM(buy_qty), 0), 2) AS day_vwap
            FROM daily_broker_scrip_summary
            WHERE symbol = %s AND trade_date >= %s AND trade_date <= %s
            GROUP BY trade_date
            ORDER BY trade_date ASC;
        """, (sym_clean, s_date, e_date))
        timeline_rows = cur.fetchall()

        timeline = [
            {
                "date": r["trade_date"].strftime("%Y-%m-%d"),
                "turnover": float(r["turnover"]),
                "volume": int(r["volume"]),
                "trades_count": int(r["trades_count"]),
                "vwap": float(r["day_vwap"] or 0)
            }
            for r in timeline_rows
        ]

        # 3. Complete Broker Participation Matrix
        cur.execute("""
            SELECT 
                broker_id,
                SUM(buy_qty) AS buy_qty,
                SUM(sell_qty) AS sell_qty,
                SUM(buy_qty) - SUM(sell_qty) AS net_qty,
                SUM(buy_amt) AS buy_amt,
                SUM(sell_amt) AS sell_amt,
                SUM(buy_amt) - SUM(sell_amt) AS net_amt,
                ROUND(SUM(buy_amt) / NULLIF(SUM(buy_qty), 0), 2) AS buy_vwap,
                ROUND(SUM(sell_amt) / NULLIF(SUM(sell_qty), 0), 2) AS sell_vwap,
                COUNT(CASE WHEN buy_amt > sell_amt THEN 1 END) AS buy_days,
                COUNT(DISTINCT trade_date) AS active_days
            FROM daily_broker_scrip_summary
            WHERE symbol = %s AND trade_date >= %s AND trade_date <= %s
            GROUP BY broker_id
            ORDER BY SUM(buy_amt) DESC;
        """, (sym_clean, s_date, e_date))
        broker_rows = cur.fetchall()

        brokers = []
        for r in broker_rows:
            b_val = float(r["buy_amt"])
            s_val = float(r["sell_amt"])
            n_val = float(r["net_amt"])
            b_days = int(r["buy_days"])
            brokers.append({
                "broker_id": int(r["broker_id"]),
                "buy_quantity": int(r["buy_qty"]),
                "sell_quantity": int(r["sell_qty"]),
                "net_quantity": int(r["net_qty"]),
                "buy_amount": b_val,
                "sell_amount": s_val,
                "net_amount": n_val,
                "buy_vwap": float(r["buy_vwap"] or 0),
                "sell_vwap": float(r["sell_vwap"] or 0),
                "buy_days": b_days,
                "active_days": int(r["active_days"]),
                "persistence_pct": round((b_days / session_count * 100.0), 1) if session_count > 0 else 0.0,
                "market_share_pct": round((b_val / turnover * 100.0), 2) if turnover > 0 else 0.0,
                "flow_status": "🟢 NET BUYING" if n_val >= 0 else "🔴 NET SELLING"
            })

        return {
            "symbol": sym_clean,
            "period": {
                "start_date": s_date,
                "end_date": e_date,
                "trading_sessions_count": session_count
            },
            "summary": {
                "turnover": turnover,
                "volume": volume,
                "trades_count": int(s_sum["total_trades"]),
                "active_brokers_count": int(s_sum["active_brokers"]),
                "multi_day_vwap": float(s_sum["multi_day_vwap"] or 0)
            },
            "timeline": timeline,
            "brokers": brokers
        }
    finally:
        cur.close()
        conn.close()

# Multi-Prefix Mounting for Vercel Serverless
app.include_router(router, prefix="/api/multiday")
app.include_router(router, prefix="/multiday")
app.include_router(router, prefix="/api")
app.include_router(router, prefix="")
