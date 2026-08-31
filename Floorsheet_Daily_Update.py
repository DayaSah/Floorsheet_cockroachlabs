import os
import sys
import time
import random
import requests
import psycopg2
from psycopg2.extras import execute_values
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime
from dotenv import load_dotenv

# Load local .env if it exists (ignored in GitHub Actions)
load_dotenv()

DB_URI = os.getenv("DB_URI")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(message):
    """Sends HTML formatted message to your Telegram bot."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram credentials missing. Message logged to console instead:")
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

def main():
    start_time = time.time()
    today_date = datetime.now().strftime("%Y-%m-%d")
    
    # 1. Anti-Bot Start Delay (1 to 5 minutes)
    startup_delay = random.randint(60, 300)
    print(f"🕒 Delaying startup by {startup_delay} seconds...")
    time.sleep(startup_delay)
    
    url = "https://sharehubnepal.com/live/api/v2/floorsheet"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://sharehubnepal.com/nepse/floorsheet",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
    }
    
    session = get_robust_session()
    
    try:
        # 2. Holiday / Market Closed Probe (Page 1)
        probe_params = {"Size": 100, "currentPage": 1, "date": today_date}
        probe_response = session.get(url, params=probe_params, headers=headers, timeout=15)
        probe_response.raise_for_status()
        
        probe_data = probe_response.json().get("data", {})
        total_items = probe_data.get("totalItems", 0)
        
        if total_items == 0 or not probe_data.get("content"):
            send_telegram(f"ℹ️ <b>NEPSE Market Closed</b>\nDate: {today_date}\nStatus: Holiday/Weekend detected. 0 records found.")
            sys.exit(0)

        # 3. Market is open, initialize Database Connection
        conn = psycopg2.connect(DB_URI)
        cursor = conn.cursor()

        page = 1
        page_size = 100
        total_processed = 0
        total_pages = probe_data.get("totalPages", 1)

        while True:
            params = {"Size": page_size, "currentPage": page, "date": today_date}
            
            response = session.get(url, params=params, headers=headers, timeout=15)
            response.raise_for_status()
            
            data = response.json()
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

            total_processed += len(batch_data)
            
            if total_processed >= total_items or page >= total_pages:
                break
                
            page += 1
            
            # 4. Anti-Bot Page Loop Delay (0.5 to 2.0 seconds)
            time.sleep(random.uniform(0.5, 2.0))

        # Cleanup
        cursor.close()
        conn.close()
        
        # 5. Success Message Calculation
        elapsed_minutes = round((time.time() - start_time) / 60, 2)
        success_msg = (
            f"✅ <b>NEPSE Sync Successful</b>\n"
            f"<b>Date:</b> {today_date}\n"
            f"<b>Records Stored:</b> {total_processed:,}\n"
            f"<b>Pages Processed:</b> {page:,}\n"
            f"<b>Execution Time:</b> {elapsed_minutes} mins"
        )
        send_telegram(success_msg)

    except Exception as e:
        # 6. Failure Catch All
        fail_msg = (
            f"❌ <b>NEPSE Sync Failed</b>\n"
            f"<b>Date:</b> {today_date}\n"
            f"<b>Error:</b> <code>{str(e)[:500]}</code>"
        )
        send_telegram(fail_msg)
        sys.exit(1)

if __name__ == "__main__":
    main()
