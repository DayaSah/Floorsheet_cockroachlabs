import os
import sys
import argparse
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Load environment
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
    load_dotenv()
except ImportError:
    pass

DB_URI = os.getenv("DB_URI")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(message):
    """Sends HTML formatted verification report to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram credentials not configured. Report printed to console.")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        res = requests.post(url, json=payload, timeout=15)
        if res.status_code == 200:
            print("✅ Telegram notification sent successfully.")
        else:
            print(f"⚠️ Telegram API response: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"❌ Telegram alert failed: {e}")

def build_db_uri(uri):
    if uri and "sslmode=verify-full" in uri:
        uri = uri.replace("sslmode=verify-full", "sslmode=require")
    return uri

def fetch_nepsealpha_summary(symbol=None):
    """Fetches summary stats from NepseAlpha floorsheet-live-today."""
    url = "https://nepsealpha.com/floorsheet-live-today/filter"
    params = {
        "page": 1,
        "contractNumber": "",
        "stockSymbol": symbol if symbol else "",
        "buyer": "",
        "seller": "",
        "itemsPerPage": 500
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://nepsealpha.com/floorsheet-live-today"
    }
    r = requests.get(url, params=params, headers=headers, timeout=15)
    r.raise_for_status()
    data = r.json()
    return data

def verify_raw_vs_nepsealpha(symbol=None, sample_pages=5):
    """Verifies floorsheet_raw against live NepseAlpha feed."""
    print("=" * 65)
    print("🔍 PART 1: RAW FLOORSHEET vs NEPSEALPHA LIVE VERIFICATION")
    print("=" * 65)
    
    if not DB_URI:
        print("❌ Error: DB_URI not configured.")
        return None
        
    db_uri = build_db_uri(DB_URI)
    conn = psycopg2.connect(db_uri)
    cursor = conn.cursor()
    
    target_label = symbol.upper() if symbol else "ALL MARKET"
    print(f"📡 Querying NepseAlpha Feed [Target: {target_label}]...")
    try:
        alpha_data = fetch_nepsealpha_summary(symbol)
        alpha_summary = alpha_data.get("summary", {})
        as_of = alpha_data.get("asOf", "Today")
        
        alpha_total_trades = int(alpha_summary.get("total", 0))
        alpha_total_amount = float(alpha_summary.get("totalamount", 0))
        alpha_total_qty = int(alpha_summary.get("totalquantity", 0))
        
        trade_date = as_of.split()[0] if as_of else None
        print(f"   📅 Date: {trade_date} | NepseAlpha: Trades: {alpha_total_trades:,} | Qty: {alpha_total_qty:,} | Amount: Rs {alpha_total_amount:,.2f}")
    except Exception as e:
        print(f"   ⚠️ NepseAlpha Feed unreachable or protected ({e}). Proceeding to DBMS validation.")
        alpha_data = None
        trade_date = datetime.now().strftime("%Y-%m-%d")
        alpha_total_trades = 0
        alpha_total_amount = 0.0
        alpha_total_qty = 0
    
    if symbol:
        cursor.execute("""
            SELECT COUNT(*), COALESCE(SUM(quantity), 0), COALESCE(SUM(amount), 0)
            FROM floorsheet_raw
            WHERE trade_time::date = %s AND symbol = %s;
        """, (trade_date, symbol.upper()))
    else:
        cursor.execute("""
            SELECT COUNT(*), COALESCE(SUM(quantity), 0), COALESCE(SUM(amount), 0)
            FROM floorsheet_raw
            WHERE trade_time::date = %s;
        """, (trade_date,))
        
    db_count, db_qty, db_amount = cursor.fetchone()
    db_qty = int(db_qty)
    db_amount = float(db_amount)
    
    print(f"   💾 CockroachDB: Trades: {db_count:,} | Qty: {db_qty:,} | Amount: Rs {db_amount:,.2f}")
    
    trades_diff = db_count - alpha_total_trades
    qty_diff = db_qty - alpha_total_qty
    amt_diff = db_amount - alpha_total_amount
    
    trades_status = "✅ MATCH" if trades_diff == 0 else f"⚠️ DIFF: {trades_diff:+d}"
    qty_status = "✅ MATCH" if qty_diff == 0 else f"⚠️ DIFF: {qty_diff:+d}"
    amt_status = "✅ MATCH" if abs(amt_diff) < 10.0 else f"⚠️ DIFF: Rs {amt_diff:+,.2f}"
    
    print(f"   • Trades: {trades_status} | Volume: {qty_status} | Amount: {amt_status}")
    
    cursor.close()
    conn.close()
    
    return {
        "date": trade_date,
        "target": target_label,
        "db_count": db_count,
        "alpha_count": alpha_total_trades,
        "db_qty": db_qty,
        "alpha_qty": alpha_total_qty,
        "db_amount": db_amount,
        "alpha_amount": alpha_total_amount,
        "matched": (trades_diff == 0 and qty_diff == 0 and abs(amt_diff) < 10.0)
    }

def verify_summary_vs_raw_multiday(days=14):
    """
    Verifies internal consistency between daily_broker_scrip_summary and floorsheet_raw
    across the past N trading days (default: 14 days / past 2 weeks).
    """
    print("\n" + "=" * 65)
    print(f"🔍 PART 2: SUMMARY TABLE vs RAW FLOORSHEET (PAST {days} SESSIONS)")
    print("=" * 65)
    
    if not DB_URI:
        print("❌ Error: DB_URI not configured.")
        return []
        
    db_uri = build_db_uri(DB_URI)
    conn = psycopg2.connect(db_uri)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # 1. Fetch distinct dates from raw table
    cursor.execute("""
        SELECT DISTINCT trade_time::date AS tdate
        FROM floorsheet_raw
        ORDER BY tdate DESC
        LIMIT %s;
    """, (days,))
    raw_dates = [r['tdate'].strftime("%Y-%m-%d") for r in cursor.fetchall()]
    
    print(f"Scanning past {len(raw_dates)} available trading sessions in CockroachDB...\n")
    
    session_results = []
    
    for d_str in raw_dates:
        start_ts = f"{d_str} 00:00:00+00"
        end_ts = f"{d_str} 23:59:59.999999+00"
        
        # Raw totals
        cursor.execute("""
            SELECT 
                COUNT(*) AS raw_trades,
                COALESCE(SUM(quantity), 0) AS raw_qty,
                COALESCE(SUM(amount), 0) AS raw_amt
            FROM floorsheet_raw
            WHERE trade_time >= %s AND trade_time <= %s;
        """, (start_ts, end_ts))
        raw_row = cursor.fetchone()
        
        # Summary totals
        cursor.execute("""
            SELECT 
                COUNT(*) AS summary_rows,
                COALESCE(SUM(buy_qty), 0) AS sum_buy_qty,
                COALESCE(SUM(sell_qty), 0) AS sum_sell_qty,
                COALESCE(SUM(buy_amt), 0) AS sum_buy_amt,
                COALESCE(SUM(sell_amt), 0) AS sum_sell_amt
            FROM daily_broker_scrip_summary
            WHERE trade_date = %s;
        """, (d_str,))
        sum_row = cursor.fetchone()
        
        raw_trades = raw_row['raw_trades']
        raw_qty = int(raw_row['raw_qty'])
        raw_amt = float(raw_row['raw_amt'])
        
        summary_rows = sum_row['summary_rows']
        sum_buy_qty = int(sum_row['sum_buy_qty'])
        sum_sell_qty = int(sum_row['sum_sell_qty'])
        sum_buy_amt = float(sum_row['sum_buy_amt'])
        sum_sell_amt = float(sum_row['sum_sell_amt'])
        
        qty_ok = (raw_qty == sum_buy_qty == sum_sell_qty)
        amt_ok = (abs(raw_amt - sum_buy_amt) < 0.1 and abs(raw_amt - sum_sell_amt) < 0.1)
        reconciled = qty_ok and amt_ok and summary_rows > 0
        
        status_icon = "✅" if reconciled else "❌"
        print(f"  {status_icon} [{d_str}] Raw: {raw_trades:,} trades (Qty: {raw_qty:,}, Rs {raw_amt:,.2f}) ➔ Summary: {summary_rows:,} rows (Qty: {sum_buy_qty:,}, Rs {sum_buy_amt:,.2f})")
        
        session_results.append({
            "date": d_str,
            "reconciled": reconciled,
            "raw_trades": raw_trades,
            "summary_rows": summary_rows,
            "raw_qty": raw_qty,
            "summary_qty": sum_buy_qty,
            "raw_amt": raw_amt,
            "summary_amt": sum_buy_amt
        })
        
    cursor.close()
    conn.close()
    
    total_reconciled = sum(1 for r in session_results if r['reconciled'])
    print("\n" + "-" * 65)
    print(f"📊 SUMMARY RECONCILIATION RESULT: {total_reconciled}/{len(session_results)} SESSIONS 100% RECONCILED")
    print("-" * 65)
    
    return session_results

def main():
    parser = argparse.ArgumentParser(description="NEPSE Multi-Table Integrity & Dual-Verification Engine")
    parser.add_argument("--symbol", type=str, default=None, help="Specific symbol to check against NepseAlpha")
    parser.add_argument("--days", type=int, default=14, help="Number of past trading days to verify (default: 14)")
    parser.add_argument("--no-telegram", action="store_true", help="Skip sending Telegram notification")
    args = parser.parse_args()
    
    # Run Part 1: Raw vs NepseAlpha
    raw_res = verify_raw_vs_nepsealpha(symbol=args.symbol)
    
    # Run Part 2: Summary vs Raw over past N days
    summary_results = verify_summary_vs_raw_multiday(days=args.days)
    
    # Generate Telegram Message
    if not args.no_telegram and summary_results:
        total_sessions = len(summary_results)
        reconciled_sessions = sum(1 for r in summary_results if r['reconciled'])
        pass_rate = (reconciled_sessions / total_sessions * 100.0) if total_sessions > 0 else 100.0
        
        status_badge = "✅ <b>100% INTEGRITY PASSED</b>" if pass_rate == 100.0 else f"⚠️ <b>ATTENTION ({pass_rate:.1f}%)</b>"
        
        tg_msg = (
            f"📊 <b>NEPSE Dual-Table Integrity Audit Report</b>\n\n"
            f"<b>Status:</b> {status_badge}\n"
            f"<b>Window:</b> Past {args.days} Trading Sessions ({summary_results[-1]['date']} to {summary_results[0]['date']})\n"
            f"<b>Multi-Day Reconciled:</b> <code>{reconciled_sessions}/{total_sessions} Sessions ({pass_rate:.1f}%)</code>\n\n"
            f"<b>📋 Tables Audited:</b>\n"
            f"1. <code>floorsheet_raw</code> (Tick-level Source of Truth)\n"
            f"2. <code>daily_broker_scrip_summary</code> (Pre-aggregated Multi-Day Layer)\n\n"
        )
        
        if raw_res:
            tg_msg += (
                f"<b>📡 Latest Live Feed Check ({raw_res['date']}):</b>\n"
                f"• DBMS Trades: {raw_res['db_count']:,} vs Alpha: {raw_res['alpha_count']:,}\n"
                f"• DBMS Turnover: Rs {raw_res['db_amount']:,.2f} vs Alpha: Rs {raw_res['alpha_amount']:,.2f}\n"
            )
            
        send_telegram(tg_msg)

if __name__ == "__main__":
    main()
