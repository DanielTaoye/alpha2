import pymysql

# Check readonly database for huanshou data
conn = pymysql.connect(
    host='sh-cdbrg-8f14w39q.sql.tencentcdb.com', 
    port=25924, 
    user='root', 
    password='MrEPYZus7myr', 
    database='stock'
)
cursor = conn.cursor()

# Check table structure
print("=== Table structure (huanshou column) ===")
cursor.execute("DESCRIBE b_daily_chance")
for row in cursor.fetchall():
    if 'huanshou' in str(row).lower():
        print(row)

# Check sample data
print("\n=== Sample huanshou data ===")
cursor.execute("SELECT stock_code, DATE(date) as date, Huanshou FROM b_daily_chance WHERE Huanshou IS NOT NULL AND Huanshou != '' LIMIT 10")
for row in cursor.fetchall():
    print(row)

# Check data count
print("\n=== Count of records with huanshou ===")
cursor.execute("SELECT COUNT(*) FROM b_daily_chance WHERE Huanshou IS NOT NULL AND Huanshou != ''")
print(f"Records with huanshou: {cursor.fetchone()[0]}")

cursor.execute("SELECT COUNT(*) FROM b_daily_chance")
print(f"Total records: {cursor.fetchone()[0]}")

conn.close()
print("\nDone!")
