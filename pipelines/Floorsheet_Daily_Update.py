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
import zoneinfo

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

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
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"⚠️ Telegram Log:\n{message}")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"❌ Telegram alert failed: {e}")

def get_robust_session():
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session

def build_db_uri(uri):
    """Ensure SSL mode is compatible with CockroachDB in all environments."""
    if uri and "sslmode=verify-full" in uri:
        uri = uri.replace("sslmode=verify-full", "sslmode=require")
    return uri

def main():
    start_time = time.time()
    
    # 1. Enforce Nepal Timezone (NPT) regardless of runner location
    nepal_tz = zoneinfo.ZoneInfo("Asia/Kathmandu")
    today_date = datetime.now(nepal_tz).strftime("%Y-%m-%d")
    
    print(f"🚀 Starting NEPSE Daily Floorsheet Scraper")
    print(f"📅 Date: {today_date}")
    
    url = "https://sharehubnepal.com/live/api/v2/floorsheet"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://sharehubnepal.com/nepse/floorsheet",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
    }
    
    session = get_robust_session()
    
    try:
        # 2. Probe Request — ShareHub requires 'page' and 'size'
        probe_params = {"size": 100, "page": 1, "date": today_date}
        probe_response = session.get(url, params=probe_params, headers=headers, timeout=15)
        probe_response.raise_for_status()
        
        probe_data = probe_response.json().get("data", {})
        total_items = probe_data.get("totalItems", 0)
        total_pages = probe_data.get("totalPages", 1)
        
        print(f"📊 API reports: {total_items:,} total trades across {total_pages:,} pages")
        
        if total_items == 0 or not probe_data.get("content"):
            msg = f"ℹ️ <b>NEPSE Market Closed</b>\nDate: {today_date}\nStatus: 0 records found."
            print(msg)
            send_telegram(msg)
            sys.exit(0)

        db_uri = build_db_uri(DB_URI)
        conn = psycopg2.connect(db_uri)
        cursor = conn.cursor()

        page = 1
        page_size = 100
        total_inserted = 0
        empty_retries = 0
        batch_buffer = []

        while page <= total_pages:
            params = {
                "size": page_size,
                "page": page,
                "date": today_date
            }
            
            try:
                response = session.get(url, params=params, headers=headers, timeout=15)
                response.raise_for_status()
                data = response.json()
                records = data.get("data", {}).get("content", [])
            except Exception as req_err:
                print(f"⚠️ Fetch warning on page {page}: {req_err}")
                empty_retries += 1
                if empty_retries > 3:
                    break
                time.sleep(2)
                continue

            if not records:
                empty_retries += 1
                if empty_retries >= 3:
                    break
                page += 1
                continue
            
            empty_retries = 0  # Reset retry counter on successful page

            for r in records:
                try:
                    contract_id = int(r["contractId"])
                    if contract_id <= 0:
                        continue
                    batch_buffer.append((
                        contract_id,
                        str(r["symbol"]).strip().upper(),
                        int(r["buyerMemberId"]),
                        int(r["sellerMemberId"]),
                        int(r["contractQuantity"]),
                        float(r["contractRate"]),
                        float(r["contractAmount"]),
                        r["tradeTime"]
                    ))
                except (KeyError, ValueError, TypeError):
                    continue

            # Flush in scaled chunks of 2,000 rows (95% fewer distributed SQL transactions)
            if len(batch_buffer) >= 2000:
                insert_query = """
                INSERT INTO floorsheet_raw 
                (contract_id, symbol, buyer_broker, seller_broker, quantity, rate, amount, trade_time)
                VALUES %s
                ON CONFLICT (contract_id) DO UPDATE SET
                    symbol = EXCLUDED.symbol,
                    rate = EXCLUDED.rate,
                    amount = EXCLUDED.amount;
                """
                execute_values(cursor, insert_query, batch_buffer)
                conn.commit()
                total_inserted += len(batch_buffer)
                batch_buffer = []

            if page % 50 == 0 or page == total_pages:
                print(f"  ✅ Progress: page {page}/{total_pages} | Records inserted: {total_inserted:,}")

            page += 1
            time.sleep(random.uniform(0.15, 0.35))

        # Flush any remaining buffered records
        if batch_buffer:
            insert_query = """
            INSERT INTO floorsheet_raw 
            (contract_id, symbol, buyer_broker, seller_broker, quantity, rate, amount, trade_time)
            VALUES %s
            ON CONFLICT (contract_id) DO UPDATE SET
                symbol = EXCLUDED.symbol,
                rate = EXCLUDED.rate,
                amount = EXCLUDED.amount;
            """
            execute_values(cursor, insert_query, batch_buffer)
            conn.commit()
            total_inserted += len(batch_buffer)
            batch_buffer = []

        cursor.close()
        conn.close()

        # Step 3: Trigger Multi-Day Summary ETL & Automated Reconciliation
        print(f"\n🔄 Running Multi-Day Summary ETL & Reconciliation for {today_date}...")
        etl_status = "Skipped"
        summary_rows_count = 0
        try:
            from scripts.daily_summary_etl import rebuild_summary_for_date
            etl_result = rebuild_summary_for_date(today_date)
            summary_rows_count = etl_result.get("summary_rows", 0)
            etl_status = "✅ 100% Reconciled" if etl_result.get("reconciled") else "⚠️ Mismatch"
            print(f"  {etl_status} ({summary_rows_count:,} summary rows generated)")
        except Exception as etl_err:
            etl_status = f"⚠️ Warning: {etl_err}"
            print(f"⚠️ Summary ETL Warning: {etl_err}")
        
        elapsed_minutes = round((time.time() - start_time) / 60, 2)
        success_msg = (
            f"✅ <b>NEPSE Daily Sync Successful</b>\n"
            f"<b>Date:</b> {today_date}\n"
            f"<b>Total API Items:</b> {total_items:,}\n"
            f"<b>Raw Records Saved:</b> {total_inserted:,}\n"
            f"<b>Multi-Day Summary:</b> {etl_status} ({summary_rows_count:,} rows)\n"
            f"<b>Pages Processed:</b> {page - 1:,} / {total_pages:,}\n"
            f"<b>Execution Time:</b> {elapsed_minutes} mins"
        )
        print(success_msg)
        send_telegram(success_msg)

    except Exception as e:
        fail_msg = (
            f"❌ <b>NEPSE Sync Failed</b>\n"
            f"<b>Date:</b> {today_date}\n"
            f"<b>Error:</b> <code>{str(e)[:500]}</code>"
        )
        print(fail_msg)
        send_telegram(fail_msg)
        sys.exit(1)

if __name__ == "__main__":
    main()
