import os
import math
import psycopg2
from datetime import datetime
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, Query, HTTPException, Response
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

app = FastAPI(title="NEPSE Floorsheet API")

# Enable CORS for frontend requests
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
    if not DB_URI:
        raise HTTPException(status_code=500, detail="DB_URI environment variable missing.")
    uri = DB_URI
    if "sslmode=verify-full" in uri:
        uri = uri.replace("sslmode=verify-full", "sslmode=require")
    try:
        conn = psycopg2.connect(uri, cursor_factory=RealDictCursor)
        conn.autocommit = True
        return conn
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection error: {str(e)}")

# Whitelist allowed sort columns to prevent SQL injection
ALLOWED_SORT_FIELDS = {
    "trade_time": "trade_time",
    "contract_id": "contract_id",
    "symbol": "symbol",
    "buyer_broker": "buyer_broker",
    "seller_broker": "seller_broker",
    "quantity": "quantity",
    "rate": "rate",
    "amount": "amount"
}

def apply_cache_headers(response: Response, date_str: str = None):
    """Applies Vercel CDN and browser cache headers. Historical dates cached 24h."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    if date_str and date_str < today_str:
        response.headers["Cache-Control"] = "public, max-age=86400, s-maxage=86400, stale-while-revalidate=604800"
    else:
        response.headers["Cache-Control"] = "public, max-age=60, s-maxage=60"

@app.get("/api/floorsheet")
def get_floorsheet(
    response: Response,
    date: str = Query(..., description="Date format YYYY-MM-DD"),
    symbol: str = Query(None, description="Stock Symbol, e.g., NABIL"),
    buyer: int = Query(None, description="Buyer Broker Number"),
    seller: int = Query(None, description="Seller Broker Number"),
    sort_by: str = Query("trade_time", description="Field to sort by"),
    order: str = Query("desc", description="asc or desc"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=10, le=500)
):
    apply_cache_headers(response, date)

    conn = get_db_connection()
    cursor = conn.cursor()

    # Validate sorting fields
    sort_column = ALLOWED_SORT_FIELDS.get(sort_by, "trade_time")
    sort_order = "ASC" if order.lower() == "asc" else "DESC"

    # High-Performance Indexed Timestamp Bounds (Uses idx_trade_time index)
    start_ts = f"{date} 00:00:00+00"
    end_ts = f"{date} 23:59:59.999999+00"
    where_clauses = ["trade_time >= %s", "trade_time <= %s"]
    params = [start_ts, end_ts]

    if symbol:
        where_clauses.append("symbol = %s")
        params.append(symbol.strip().upper())
    if buyer:
        where_clauses.append("buyer_broker = %s")
        params.append(buyer)
    if seller:
        where_clauses.append("seller_broker = %s")
        params.append(seller)

    where_sql = " WHERE " + " AND ".join(where_clauses)

    try:
        # 1. Fetch KPI Summary across entire filtered dataset
        summary_query = f"""
            SELECT 
                COALESCE(COUNT(*), 0) AS total_trades,
                COALESCE(SUM(amount), 0) AS total_amount,
                COALESCE(SUM(quantity), 0) AS total_quantity,
                COALESCE(AVG(rate), 0) AS avg_rate
            FROM floorsheet_raw
            {where_sql};
        """
        cursor.execute(summary_query, params)
        summary = cursor.fetchone()

        total_trades = summary["total_trades"]
        total_pages = math.ceil(total_trades / limit) if total_trades > 0 else 1
        offset = (page - 1) * limit

        # 2. Fetch Paginated Records using covering index
        records_query = f"""
            SELECT 
                contract_id,
                symbol,
                buyer_broker,
                seller_broker,
                quantity,
                rate,
                amount,
                TO_CHAR(trade_time, 'HH24:MI:SS') AS trade_time_formatted
            FROM floorsheet_raw
            {where_sql}
            ORDER BY {sort_column} {sort_order}
            LIMIT %s OFFSET %s;
        """
        cursor.execute(records_query, params + [limit, offset])
        records = cursor.fetchall()

        cursor.close()
        conn.close()

        return {
            "summary": {
                "total_trades": total_trades,
                "total_amount": float(summary["total_amount"]),
                "total_quantity": int(summary["total_quantity"]),
                "avg_rate": round(float(summary["avg_rate"]), 2)
            },
            "pagination": {
                "current_page": page,
                "total_pages": total_pages,
                "limit": limit,
                "total_records": total_trades
            },
            "data": records
        }

    except Exception as e:
        cursor.close()
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/symbols")
def get_symbols(response: Response, date: str = Query(None)):
    """Fetch distinct symbols efficiently using summary layer when date is provided."""
    apply_cache_headers(response, date)
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if date:
            # Query the pre-aggregated summary layer (97% fewer rows)
            cursor.execute("""
                SELECT DISTINCT symbol 
                FROM daily_broker_scrip_summary 
                WHERE trade_date = %s 
                ORDER BY symbol ASC;
            """, (date,))
        else:
            cursor.execute("""
                SELECT DISTINCT symbol 
                FROM daily_broker_scrip_summary 
                ORDER BY symbol ASC;
            """)
            
        rows = cursor.fetchall()
        return [r["symbol"] for r in rows]
    finally:
        cursor.close()
        conn.close()
