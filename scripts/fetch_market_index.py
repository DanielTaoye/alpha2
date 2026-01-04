
import sys
import os
import requests
import json
from datetime import datetime
import pymysql
import traceback

def fetch_and_store_index():
    print("Starting process...")
    
    # 1. Fetch Data
    url = "https://gw.yundzh.com/quote/kline?obj=SH000001&period=1day&token=0000013f:1767579709:01a6abc9b1dd57565444c7d53090884dbf54d14f&begin_time=20240101-000000-000-8&end_time=20251231-000000-000-8"
    print(f"Fetching data from API...")
    try:
        response = requests.get(url, timeout=30)
        data = response.json()
    except Exception as e:
        print(f"API Request failed: {e}")
        return

    kline_node = data.get('Data', {}).get('JsonTbl', {})
    if not kline_node:
        print("No JsonTbl data found.") # Handle API errors gracefully
        return

    try:
        rows = kline_node['data'][0][0]['data'][0][1]['data']
        headers = kline_node['data'][0][0]['data'][0][1]['head']
    except (IndexError, KeyError, TypeError):
        print("Failed to parse JsonTbl structure.")
        return

    col_map = {name: i for i, name in enumerate(headers)}
    idx_time = col_map.get('ShiJian')
    idx_close = col_map.get('ShouPanJia')

    if idx_time is None or idx_close is None:
        print("Missing required columns in API data.")
        return

    print(f"Got {len(rows)} records from API.")

    # 2. Connect to DB
    print("Connecting to database...")
    conn = None
    try:
        conn = pymysql.connect(
            host='sh-cdb-2hxu41ka.sql.tencentcdb.com',
            port=21648,
            user='root',
            password='MrEPYZus7myr',
            database='stock',
            charset='utf8mb4',
            connect_timeout=10
        )
        cursor = conn.cursor()
        
        # 3. Inspect Table Columns
        print("Inspecting 'market_index_daily' schema...")
        cursor.execute("SELECT * FROM market_index_daily LIMIT 0")
        # cursor.description is ((name, type_code, ...), ...)
        db_cols = [desc[0].lower() for desc in cursor.description]
        print(f"DB Columns: {db_cols}")

        if 'index_code' not in db_cols and 'code' not in db_cols:
             print("Warning: 'index_code' column missing in DB. Skipping adding it to avoid locks. Data will be inserted without index_code.")
        
        # 4. Construct Insert SQL based on available columns
        # User goal: Insert (ID, IndexName, Date, Close, UpdatedAt)
        # We generally map:
        #   index_name -> '上证指数'
        #   index_code -> 'SH000001' (only if exists)
        #   trade_date | date | time -> date string
        #   close_price | close | price -> float price
        
        fields = []
        values_ph = []
        params_base = []

        # Index Name
        if 'index_name' in db_cols:
            fields.append('index_name')
            values_ph.append('%s')
            params_base.append('上证指数')
        elif 'name' in db_cols:
            fields.append('name')
            values_ph.append('%s')
            params_base.append('上证指数')
            
        # Index Code
        if 'index_code' in db_cols:
            fields.append('index_code')
            values_ph.append('%s')
            params_base.append('SH000001')
        elif 'code' in db_cols:
            fields.append('code')
            values_ph.append('%s')
            params_base.append('SH000001')

        # Date Column
        date_col = None
        if 'trade_date' in db_cols: date_col = 'trade_date'
        elif 'date' in db_cols: date_col = 'date'
        elif 'time' in db_cols: date_col = 'time'
        
        if not date_col:
            print("❌ Startling: No obvious date column found in DB!")
            return
        fields.append(date_col)
        values_ph.append('%s')

        # Close Price Column
        close_col = None
        if 'close_price' in db_cols: close_col = 'close_price'
        elif 'shou_pan_jia' in db_cols: close_col = 'shou_pan_jia'
        elif 'close' in db_cols: close_col = 'close'
        elif 'price' in db_cols: close_col = 'price'

        if not close_col:
            print("❌ Startling: No obvious close price column found in DB!")
            return
        fields.append(close_col)
        values_ph.append('%s')

        sql = f"INSERT INTO market_index_daily ({', '.join(fields)}) VALUES ({', '.join(values_ph)})"
        # Add ON DUPLICATE UPDATE
        update_parts = [f"{close_col} = VALUES({close_col})"]
        if 'updated_at' in db_cols:
            update_parts.append("updated_at = NOW()")
        
        sql += " ON DUPLICATE KEY UPDATE " + ", ".join(update_parts)
        
        print(f"Generated SQL: {sql}")

        # 5. Insert Loop
        success_count = 0
        for row in rows:
            raw_time = row[idx_time]
            raw_close = row[idx_close]
            
            # Format Date
            d_str = ""
            if isinstance(raw_time, int):
                # assume sec timestamp if > 200000000
                if raw_time > 200000000:
                    d_str = datetime.fromtimestamp(raw_time).strftime('%Y-%m-%d')
                else: # YYYYMMDD
                    s = str(raw_time)
                    d_str = f"{s[:4]}-{s[4:6]}-{s[6:]}"
            else:
                s = str(raw_time).replace('-','')
                d_str = f"{s[:4]}-{s[4:6]}-{s[6:8]}"
            
            # Prepare params
            # base params order: [Name, Code] (if existed)
            # then append Date, Close
            row_params = list(params_base)
            row_params.append(d_str)
            row_params.append(float(raw_close))
            
            cursor.execute(sql, tuple(row_params))
            success_count += 1
        
        conn.commit()
        print(f"✅ Successfully inserted {success_count} records to market_index_daily!")

    except pymysql.err.OperationalError as e:
        if 1290 in e.args or '--read-only' in str(e):
             print(f"❌ DATABASE IS READ-ONLY: {e}")
             print("Please check the DB instance status.")
        else:
             print(f"Database Operational Error: {e}")
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()
    finally:
        if conn: conn.close()

if __name__ == "__main__":
    fetch_and_store_index()
