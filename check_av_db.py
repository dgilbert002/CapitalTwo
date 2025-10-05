import sqlite3

conn = sqlite3.connect('database_av.db')
cursor = conn.cursor()

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print("Tables in database_av.db:", tables)

# Check each table's structure
for table in tables:
    table_name = table[0]
    cursor.execute(f"SELECT * FROM {table_name} LIMIT 5")
    rows = cursor.fetchall()
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    
    print(f"\nTable: {table_name}")
    print(f"Columns: {[col[1] for col in columns]}")
    print(f"Sample rows: {len(rows)}")
    if rows:
        print(f"First row: {rows[0]}")

conn.close()
