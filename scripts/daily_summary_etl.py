import os
import sys
import time
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, date

# Load local .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DB_URI = os.getenv("DB_URI")

def get_connection():
    if not DB_URI:
        raise ValueError("DB_URI environment variable is missing!")
    uri = DB_URI
    if "sslmode=verify-full" in uri:
        uri = uri.replace("sslmode=verify-full", "sslmode=require")
    conn = psycopg2.connect(uri)
    conn.autocommit = True
    return conn

def execute_with_retry(cur, query, params=None, max_retries=5):
    for attempt in range(max_retries):
        try:
            cur.execute(query, params)
            return
        except (psycopg2.errors.SerializationFailure, psycopg2.OperationalError) as e:
            if attempt < max_retries - 1:
                time.sleep(0.5 * (2 ** attempt))
                continue
            raise e

def rebuild_summary_for_date(trade_date_str, conn=None):
    """
    Idempotently aggregates floorsheet_raw into daily_broker_scrip_summary for a single date,
    performs automated reconciliation checks, and logs the run to analytics_etl_runs.
    """
    t0 = time.time()
    should_close_conn = False
    if conn is None:
        conn = get_connection()
        should_close_conn = True

    start_ts = f"{trade_date_str} 00:00:00+00"
    end_ts = f"{trade_date_str} 23:59:59.999999+00"

    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Step 1: Start audit record
        execute_with_retry(cur, """
            INSERT INTO analytics_etl_runs (trade_date, started_at, status)
            VALUES (%s, now(), 'PENDING')
            ON CONFLICT (trade_date) DO UPDATE SET
                started_at = now(),
                status = 'PENDING',
                error_message = NULL
            RETURNING run_id;
        """, (trade_date_str,))
        run_id = cur.fetchone()['run_id']

        # Step 1.5: Delete existing summary rows for this date to ensure 100% clean rebuild
        execute_with_retry(cur, "DELETE FROM daily_broker_scrip_summary WHERE trade_date = %s;", (trade_date_str,))

        # Step 2: Atomic Aggregation & Insert into daily_broker_scrip_summary (using indexed timestamp bounds)
        execute_with_retry(cur, """
            INSERT INTO daily_broker_scrip_summary (
                trade_date, broker_id, symbol, buy_qty, sell_qty, net_qty, buy_amt, sell_amt, net_amt,
                trades_count, buy_vwap, sell_vwap, first_trade_time, last_trade_time, updated_at
            )
            SELECT 
                %s::date AS trade_date,
                broker_id,
                symbol,
                SUM(buy_qty) AS buy_qty,
                SUM(sell_qty) AS sell_qty,
                SUM(buy_qty) - SUM(sell_qty) AS net_qty,
                SUM(buy_amt) AS buy_amt,
                SUM(sell_amt) AS sell_amt,
                SUM(buy_amt) - SUM(sell_amt) AS net_amt,
                COUNT(*) AS trades_count,
                ROUND(SUM(buy_amt) / NULLIF(SUM(buy_qty), 0), 4) AS buy_vwap,
                ROUND(SUM(sell_amt) / NULLIF(SUM(sell_qty), 0), 4) AS sell_vwap,
                MIN(trade_time) AS first_trade_time,
                MAX(trade_time) AS last_trade_time,
                now() AS updated_at
            FROM (
                SELECT trade_time, buyer_broker AS broker_id, symbol, quantity AS buy_qty, 0::bigint AS sell_qty, amount AS buy_amt, 0::numeric AS sell_amt 
                FROM floorsheet_raw 
                WHERE trade_time >= %s AND trade_time <= %s
                UNION ALL
                SELECT trade_time, seller_broker AS broker_id, symbol, 0::bigint AS buy_qty, quantity AS sell_qty, 0::numeric AS buy_amt, amount AS sell_amt 
                FROM floorsheet_raw 
                WHERE trade_time >= %s AND trade_time <= %s
            ) flows
            GROUP BY broker_id, symbol
            ON CONFLICT (trade_date, broker_id, symbol) DO UPDATE SET
                buy_qty = EXCLUDED.buy_qty,
                sell_qty = EXCLUDED.sell_qty,
                net_qty = EXCLUDED.net_qty,
                buy_amt = EXCLUDED.buy_amt,
                sell_amt = EXCLUDED.sell_amt,
                net_amt = EXCLUDED.net_amt,
                trades_count = EXCLUDED.trades_count,
                buy_vwap = EXCLUDED.buy_vwap,
                sell_vwap = EXCLUDED.sell_vwap,
                first_trade_time = EXCLUDED.first_trade_time,
                last_trade_time = EXCLUDED.last_trade_time,
                updated_at = now();
        """, (trade_date_str, start_ts, end_ts, start_ts, end_ts))

        # Step 3: Reconciliation Check
        execute_with_retry(cur, """
            SELECT 
                COUNT(*) AS raw_trades,
                COALESCE(SUM(quantity), 0) AS raw_qty,
                COALESCE(SUM(amount), 0) AS raw_amt
            FROM floorsheet_raw
            WHERE trade_time >= %s AND trade_time <= %s;
        """, (start_ts, end_ts))
        raw_stats = cur.fetchone()

        execute_with_retry(cur, """
            SELECT 
                COUNT(*) AS summary_rows,
                COALESCE(SUM(buy_qty), 0) AS sum_buy_qty,
                COALESCE(SUM(sell_qty), 0) AS sum_sell_qty,
                COALESCE(SUM(buy_amt), 0) AS sum_buy_amt,
                COALESCE(SUM(sell_amt), 0) AS sum_sell_amt
            FROM daily_broker_scrip_summary
            WHERE trade_date = %s;
        """, (trade_date_str,))
        sum_stats = cur.fetchone()

        raw_trades = raw_stats['raw_trades']
        raw_qty = int(raw_stats['raw_qty'])
        raw_amt = float(raw_stats['raw_amt'])

        summary_rows = sum_stats['summary_rows']
        sum_buy_qty = int(sum_stats['sum_buy_qty'])
        sum_sell_qty = int(sum_stats['sum_sell_qty'])
        sum_buy_amt = float(sum_stats['sum_buy_amt'])
        sum_sell_amt = float(sum_stats['sum_sell_amt'])

        qty_matched = (raw_qty == sum_buy_qty == sum_sell_qty)
        amt_matched = (abs(raw_amt - sum_buy_amt) < 0.1 and abs(raw_amt - sum_sell_amt) < 0.1)
        reconciled = qty_matched and amt_matched
        status = "SUCCESS" if reconciled else "MISMATCH"
        duration_ms = int((time.time() - t0) * 1000)

        # Step 4: Update Audit Record
        execute_with_retry(cur, """
            UPDATE analytics_etl_runs
            SET completed_at = now(),
                status = %s,
                raw_trades_count = %s,
                summary_rows_count = %s,
                raw_buy_qty = %s,
                summary_buy_qty = %s,
                raw_buy_amt = %s,
                summary_buy_amt = %s,
                reconciliation_matched = %s,
                duration_ms = %s
            WHERE run_id = %s;
        """, (
            status, raw_trades, summary_rows, raw_qty, sum_buy_qty, raw_amt, sum_buy_amt,
            reconciled, duration_ms, run_id
        ))

        result = {
            "date": trade_date_str,
            "status": status,
            "reconciled": reconciled,
            "raw_trades": raw_trades,
            "summary_rows": summary_rows,
            "raw_qty": raw_qty,
            "summary_qty": sum_buy_qty,
            "raw_amt": raw_amt,
            "summary_amt": sum_buy_amt,
            "duration_ms": duration_ms
        }
        return result

    except Exception as e:
        duration_ms = int((time.time() - t0) * 1000)
        try:
            execute_with_retry(cur, """
                UPDATE analytics_etl_runs
                SET completed_at = now(),
                    status = 'FAILED',
                    error_message = %s,
                    duration_ms = %s
                WHERE trade_date = %s;
            """, (str(e), duration_ms, trade_date_str))
        except Exception:
            pass
        raise e

    finally:
        cur.close()
        if should_close_conn:
            conn.close()

def rebuild_summary_for_range(start_date_str, end_date_str, conn=None):
    """Rebuilds and reconciles summary for a date range."""
    should_close_conn = False
    if conn is None:
        conn = get_connection()
        should_close_conn = True

    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT trade_time::date AS tdate
        FROM floorsheet_raw
        WHERE trade_time >= %s AND trade_time <= %s
        ORDER BY tdate ASC;
    """, (f"{start_date_str} 00:00:00+00", f"{end_date_str} 23:59:59.999999+00"))
    dates = [row[0].strftime("%Y-%m-%d") for row in cur.fetchall()]
    cur.close()

    results = []
    for d_str in dates:
        res = rebuild_summary_for_date(d_str, conn=conn)
        results.append(res)

    if should_close_conn:
        conn.close()
    return results

def backfill_all():
    """Finds all distinct trading dates in floorsheet_raw and backfills them."""
    print("=" * 65)
    print("🚀 NEPSE MULTI-DAY SUMMARY ETL ENGINE & HISTORICAL BACKFILL")
    print("=" * 65)

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT DISTINCT trade_time::date AS tdate
        FROM floorsheet_raw
        ORDER BY tdate ASC;
    """)
    dates = [row[0].strftime("%Y-%m-%d") for row in cur.fetchall()]
    cur.close()

    print(f"Found {len(dates)} historical trading sessions in floorsheet_raw.")
    print(f"Range: {dates[0]} to {dates[-1]}\n")

    results = []
    total_start = time.time()

    for idx, d_str in enumerate(dates, 1):
        print(f"[{idx}/{len(dates)}] Processing {d_str}...", end=" ", flush=True)
        res = rebuild_summary_for_date(d_str, conn=conn)
        status_icon = "✅" if res["reconciled"] else "❌"
        print(f"{status_icon} {res['status']} | Raw Trades: {res['raw_trades']:,} -> Summary Rows: {res['summary_rows']:,} in {res['duration_ms']}ms")
        results.append(res)

    conn.close()
    total_duration = round(time.time() - total_start, 2)

    all_matched = all(r["reconciled"] for r in results)
    print("\n" + "=" * 65)
    print(f"📊 BACKFILL COMPLETE in {total_duration}s")
    print(f"Total Sessions Processed: {len(results)}")
    print(f"Integrity & Reconciliation Status: {'✅ 100% RECONCILED' if all_matched else '⚠️ SOME MISMATCHES FOUND'}")
    print("=" * 65)
    return results

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Multi-Day Summary ETL & Backfill Engine")
    parser.add_argument("--date", type=str, default=None, help="Specific date YYYY-MM-DD to rebuild")
    parser.add_argument("--start", type=str, default=None, help="Start date YYYY-MM-DD for range rebuild")
    parser.add_argument("--end", type=str, default=None, help="End date YYYY-MM-DD for range rebuild")
    parser.add_argument("--all", action="store_true", help="Backfill all historical dates")
    args = parser.parse_args()

    if args.date:
        res = rebuild_summary_for_date(args.date)
        print(f"Result for {args.date}: {res}")
    elif args.start and args.end:
        results = rebuild_summary_for_range(args.start, args.end)
        print(f"Rebuilt {len(results)} dates from {args.start} to {args.end}")
    else:
        backfill_all()
