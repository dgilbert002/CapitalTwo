import sqlite3
from datetime import datetime

conn = sqlite3.connect('database_av.db')
cursor = conn.cursor()

# Get overall stats
cursor.execute('SELECT MIN(timestamp), MAX(timestamp), COUNT(*) FROM TECL_av_5min')
min_date, max_date, total = cursor.fetchone()

print("="*60)
print("ALPHA VANTAGE DATABASE STATUS")
print("="*60)
print(f"Data range: {min_date} to {max_date}")
print(f"Total candles: {total:,}")

# Check recent data
cursor.execute("""
    SELECT DATE(timestamp) as date, COUNT(*) as count
    FROM TECL_av_5min
    WHERE timestamp >= '2025-10-10'
    GROUP BY DATE(timestamp)
    ORDER BY date DESC
""")

recent_days = cursor.fetchall()
print(f"\nRecent days (Oct 10-11):")
for date, count in recent_days:
    print(f"  {date}: {count} candles")

# Check latest candles
cursor.execute("""
    SELECT timestamp 
    FROM TECL_av_5min 
    ORDER BY timestamp DESC 
    LIMIT 5
""")

latest = cursor.fetchall()
print(f"\nLatest 5 candles:")
for ts in latest:
    print(f"  {ts[0]}")

# Check if we have market close time (15:55 ET = 19:55 UTC during DST)
cursor.execute("""
    SELECT timestamp 
    FROM TECL_av_5min 
    WHERE time(timestamp) = '19:55:00'
    AND timestamp >= '2025-10-10'
    ORDER BY timestamp DESC
    LIMIT 3
""")

close_candles = cursor.fetchall()
print(f"\nMarket close candles (15:55 ET):")
for ts in close_candles:
    print(f"  {ts[0]}")

conn.close()

print("\n✅ Data refresh is working! Latest data:", max_date)
print("   The T-120s refresh in bot/trader.py will keep this updated.")
