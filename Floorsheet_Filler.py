import os
import sys
import time
import random
import traceback
import requests
import psycopg2
from psycopg2.extras import execute_values
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load local .env file if running locally
load_dotenv()

DB_URI = os.getenv("DB_URI")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(message):
    """Sends HTML formatted master summary to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram credentials missing. Summary printed to console:")
        print(message)
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"❌ Failed to send Telegram alert: {e}")

def get_robust_session():
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session

def parse_date_robustly(date_str):
    """Parses date strings like '2026-8-1' or '2026-08-01' cleanly into date objects."""
    date_str = date_str.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%d", "%Y-%n-%d", "%Y-%m-%d"):
        try:
            # Split and pad parts to ensure YYYY-MM-DD
            parts = date_str.split('-')
            if len(parts) == 3:
                year, month, day = parts
                return datetime(int(year), int(month), int(day)).date()
        except ValueError:
            continue
    raise ValueError(f"Invalid date format: '{date_str}'. Expected YYYY-MM-DD or YYYY-M-D.")

def generate_date_range(start_str, end_str):
    """Generates list of normalized YYYY-MM-DD date strings."""
    start = parse_date_robustly(start_str)
    end = parse_date_robustly(end_str)
    date_list = []
    curr = start
    while curr <= end:
        date_list.append(curr.strftime("%Y-%m-%d"))
        curr += timedelta(days=1)
    return date_list

def parse_symbols(raw_input):
    """Splits comma-separated input into clean list, or returns [None] for ALL."""
    if not raw_input or not raw_input.strip():
        return [None]
    return [s.strip().upper() for s in raw_input.split(",") if s.strip()]

def main():
    start_time = time.time()
    
    # 0. Pre-flight Check for DB_URI
    if not DB_URI:
        print("❌ FATAL ERROR: DB_URI environment variable is missing or empty!")
        print("👉 Make sure DB_URI is added in GitHub Repo Settings > Secrets and variables > Actions")
        sys.exit(1)

    # 1. Parse Inputs from Environment Variables
    start_date = os.getenv("INPUT_START_DATE", "").strip()
    end_date = os.getenv("INPUT_END_DATE", "").strip()
    raw_symbols = os.getenv("INPUT_SYMBOLS", "").strip()

    if not start_date or not end_date:
        print("❌ Error: Both start_date and end_date are required.")
        sys.exit(1)

    try:
        target_dates = generate_date_range(start_date, end_date)
    except Exception as date_err:
        print(f"❌ Date Parsing Error: {date_err}")
        sys.exit(1)

    target_symbols = parse_symbols(raw_symbols)
    
    print(f"🚀 Starting Backfill Engine")
    print(f"📅 Date Range: {target_dates[0]} to {target_dates[-1]} ({len(target_dates)} days)")
    print(f"📈 Target Tickers: {target_symbols if target_symbols != [None] else 'ALL MARKET DATA'}\n")

    url = "https://sharehubnepal.com/live/api/v2/floorsheet"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://sharehubnepal.com/nepse/floorsheet",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
    }

    session = get_robust_session()
    
    total_records_inserted = 0
    total_tasks_completed = 0
    total_tasks_skipped = 0
    
    try:
        conn = psycopg2.connect(DB_URI)
        cursor = conn.cursor()

        for current_date in target_dates:
            for symbol in target_symbols:
                sym_label = symbol if symbol else "ALL"
                
                # Step A: Query DB count for Verification Check
                if symbol:
                    cursor.execute(
                        "SELECT COUNT(*) FROM floorsheet_raw WHERE trade_time::date = %s AND symbol = %s;",
                        (current_date, symbol)
                    )
                else:
                    cursor.execute(
                        "SELECT COUNT(*) FROM floorsheet_raw WHERE trade_time::date = %s;",
                        (current_date,)
                    )
                db_count = cursor.fetchone()[0]

                # Step B: Probe Page 1 from API to get totalItems
                probe_params = {"Size": 100, "currentPage": 1, "date": current_date}
                if symbol:
                    probe_params["Symbol"] = symbol
                
                response = session.get(url, params=probe_params, headers=headers, timeout=15)
                if response.status_code != 200:
                    print(f"⚠️ API issue for {current_date} [{sym_label}]. Status: {response.status_code}. Skipping...")
                    continue
                
                probe_data = response.json().get("data", {})
                total_items = probe_data.get("totalItems", 0)
                total_pages = probe_data.get("totalPages", 1)

                # Step C: Verification Logic
                if total_items == 0 or not probe_data.get("content"):
                    print(f"⏭️ {current_date} [{sym_label}]: Market Closed or 0 Trades. Skipping.")
                    total_tasks_skipped += 1
                    continue

                if db_count >= total_items:
                    print(f"✅ {current_date} [{sym_label}]: Fully Synced ({db_count}/{total_items} in DB). Skipping.")
                    total_tasks_skipped += 1
                    continue

                print(f"📥 {current_date} [{sym_label}]: Scraping needed. (DB: {db_count} / API: {total_items})...")

                # Step D: Pagination Loop
                page = 1
                page_size = 100
                date_inserted_count = 0

                while True:
                    params = {"Size": page_size, "currentPage": page, "date": current_date}
                    if symbol:
                        params["Symbol"] = symbol

                    res = session.get(url, params=params, headers=headers, timeout=15)
                    res.raise_for_status()
                    
                    data = res.json()
                    records = data.get("data", {}).get("content", [])

                    if not records:
                        break

                    batch_data = [
                        (
                            int(r["contractId"]), r["symbol"], int(r["buyerMemberId"]),
                            int(r["sellerMemberId"]), int(r["contractQuantity"]),
                            float(r["contractRate"]), float(r["contractAmount"]), r["tradeTime"]
                        )
                        for r in records
                    ]

                    insert_query = """
                    INSERT INTO floorsheet_raw 
                    (contract_id, symbol, buyer_broker, seller_broker, quantity, rate, amount, trade_time)
                    VALUES %s
                    ON CONFLICT (contract_id) DO NOTHING;
                    """

                    execute_values(cursor, insert_query, batch_data)
                    conn.commit()

                    date_inserted_count += len(batch_data)

                    if page >= total_pages or len(records) < page_size:
                        break

                    page += 1
                    time.sleep(random.uniform(0.5, 2.0))

                total_records_inserted += date_inserted_count
                total_tasks_completed += 1
                print(f"✨ Completed {current_date} [{sym_label}]: Saved {date_inserted_count:,} records.")

        cursor.close()
        conn.close()

        # Step E: Master Telegram Summary
        elapsed_mins = round((time.time() - start_time) / 60, 2)
        summary_msg = (
            f"🛠️ <b>NEPSE Floorsheet Backfill Complete</b>\n\n"
            f"<b>Date Range:</b> {target_dates[0]} to {target_dates[-1]}\n"
            f"<b>Symbols:</b> {raw_symbols if raw_symbols else 'ALL MARKET DATA'}\n"
            f"<b>Tasks Scraped:</b> {total_tasks_completed:,}\n"
            f"<b>Tasks Skipped:</b> {total_tasks_skipped:,} (Holidays / Fully Saved)\n"
            f"<b>New Records Stored:</b> {total_records_inserted:,}\n"
            f"<b>Total Execution Time:</b> {elapsed_mins} mins"
        )
        send_telegram(summary_msg)

    except Exception as e:
        print(f"\n❌ EXCEPTION CAUGHT IN MAIN EXECUTION:")
        traceback.print_exc() # Prints exact line number and error traceback to GitHub logs
        
        fail_msg = (
            f"❌ <b>NEPSE Backfill Engine Failed</b>\n"
            f"<b>Error:</b> <code>{str(e)[:500]}</code>"
        )
        send_telegram(fail_msg)
        sys.exit(1)

if __name__ == "__main__":
    main()
