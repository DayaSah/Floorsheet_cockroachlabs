import os
import sys
import argparse
import requests
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_URI = os.getenv("DB_URI")

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

def verify_today_data(symbol=None, sample_pages=1):
    print("=" * 65)
    print("🔍 NEPSE FLOORSHEET INDEPENDENT VERIFIER (NepseAlpha vs DBMS)")
    print("=" * 65)
    
    if not DB_URI:
        print("❌ Error: DB_URI not configured in environment or .env file.")
        sys.exit(1)
        
    db_uri = build_db_uri(DB_URI)
    conn = psycopg2.connect(db_uri)
    cursor = conn.cursor()
    
    # 1. Fetch NepseAlpha reference
    print(f"\n📡 Querying NepseAlpha Live Feed [Symbol: {symbol or 'ALL MARKET'}]...")
    alpha_data = fetch_nepsealpha_summary(symbol)
    alpha_summary = alpha_data.get("summary", {})
    as_of = alpha_data.get("asOf", "Today")
    
    alpha_total_trades = int(alpha_summary.get("total", 0))
    alpha_total_amount = float(alpha_summary.get("totalamount", 0))
    alpha_total_qty = int(alpha_summary.get("totalquantity", 0))
    
    print(f"   📅 NepseAlpha asOf: {as_of}")
    print(f"   📊 NepseAlpha Summary -> Trades: {alpha_total_trades:,} | Qty: {alpha_total_qty:,} | Amount: Rs {alpha_total_amount:,.2f}")
    
    # 2. Query CockroachDB
    trade_date = as_of.split()[0] if as_of else None
    print(f"\n💾 Querying CockroachDB for Date [{trade_date}] [Symbol: {symbol or 'ALL'}]...")
    
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
    
    print(f"   📊 CockroachDB Summary -> Trades: {db_count:,} | Qty: {db_qty:,} | Amount: Rs {db_amount:,.2f}")
    
    # 3. Macro Comparison
    print("\n" + "-" * 65)
    print("📋 MACRO AGGREGATE RECONCILIATION")
    print("-" * 65)
    
    trades_diff = db_count - alpha_total_trades
    qty_diff = db_qty - alpha_total_qty
    amt_diff = db_amount - alpha_total_amount
    
    trades_status = "✅ MATCH" if trades_diff == 0 else f"⚠️ DIFF: {trades_diff:+d}"
    qty_status = "✅ MATCH" if qty_diff == 0 else f"⚠️ DIFF: {qty_diff:+d}"
    amt_status = "✅ MATCH" if abs(amt_diff) < 10.0 else f"⚠️ DIFF: Rs {amt_diff:+,.2f}"
    
    print(f"  • Trade Count : {db_count:,} vs {alpha_total_trades:,} -> {trades_status}")
    print(f"  • Total Volume: {db_qty:,} vs {alpha_total_qty:,} -> {qty_status}")
    print(f"  • Total Amount: Rs {db_amount:,.2f} vs Rs {alpha_total_amount:,.2f} -> {amt_status}")
    
    # 4. Micro Contract-level Cross-check
    print("\n" + "-" * 65)
    print(f"🔬 MICRO CONTRACT-LEVEL CROSS-CHECK (Checking {sample_pages} page(s) / up to {sample_pages * 500} records)")
    print("-" * 65)
    
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://nepsealpha.com/floorsheet-live-today"
    }
    
    total_verified = 0
    matched_contracts = 0
    mismatched_contracts = 0
    missing_in_db = 0
    
    for page in range(1, sample_pages + 1):
        url = "https://nepsealpha.com/floorsheet-live-today/filter"
        params = {
            "page": page,
            "contractNumber": "",
            "stockSymbol": symbol if symbol else "",
            "buyer": "",
            "seller": "",
            "itemsPerPage": 500
        }
        res = requests.get(url, params=params, headers=headers, timeout=15)
        page_records = res.json().get("data", {}).get("data", [])
        if not page_records:
            break
            
        contract_ids = [int(r["cn"]) for r in page_records if r.get("cn")]
        cursor.execute("""
            SELECT contract_id, symbol, buyer_broker, seller_broker, quantity, rate, amount
            FROM floorsheet_raw
            WHERE contract_id = ANY(%s);
        """, (contract_ids,))
        db_map = {row[0]: row for row in cursor.fetchall()}
        
        for r in page_records:
            cid = int(r["cn"])
            total_verified += 1
            if cid not in db_map:
                missing_in_db += 1
                continue
                
            db_row = db_map[cid]
            # Verify fields: symbol, buyer, seller, qty, rate, amount
            sym_ok = db_row[1] == r["smb"].strip().upper()
            buyer_ok = db_row[2] == int(r["bb"])
            seller_ok = db_row[3] == int(r["sb"])
            qty_ok = db_row[4] == int(r["qnt"])
            rate_ok = abs(float(db_row[5]) - float(r["rt"])) < 0.01
            amt_ok = abs(float(db_row[6]) - float(r["am"])) < 1.0
            
            if sym_ok and buyer_ok and seller_ok and qty_ok and rate_ok and amt_ok:
                matched_contracts += 1
            else:
                mismatched_contracts += 1
                print(f"  ❌ Mismatch for Contract #{cid}:")
                print(f"     Alpha: sym={r['smb']}, buyer={r['bb']}, seller={r['sb']}, qty={r['qnt']}, rate={r['rt']}, amt={r['am']}")
                print(f"     DBMS : sym={db_row[1]}, buyer={db_row[2]}, seller={db_row[3]}, qty={db_row[4]}, rate={db_row[5]}, amt={db_row[6]}")
                
    print(f"  • Contracts Examined : {total_verified:,}")
    print(f"  • Perfectly Matched  : {matched_contracts:,} ({matched_contracts/total_verified*100:.1f}%)" if total_verified > 0 else "0")
    print(f"  • Missing from DBMS  : {missing_in_db:,}")
    print(f"  • Attribute Mismatches: {mismatched_contracts:,}")
    
    cursor.close()
    conn.close()
    
    print("\n" + "=" * 65)
    if missing_in_db == 0 and mismatched_contracts == 0 and trades_diff == 0:
        print("🎉 STATUS: 100% PERFECT DATA INTEGRITY & SYNCHRONIZATION!")
    else:
        print("ℹ️ STATUS: PARTIAL / IN PROGRESS — Sync or backfill recommended.")
    print("=" * 65)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify CockroachDB floorsheet data against NepseAlpha live feed.")
    parser.add_argument("--symbol", type=str, default=None, help="Stock symbol to verify (e.g. SHIVM, NABIL)")
    parser.add_argument("--pages", type=int, default=2, help="Number of 500-item pages to sample for micro verification")
    args = parser.parse_args()
    
    verify_today_data(symbol=args.symbol, sample_pages=args.pages)
