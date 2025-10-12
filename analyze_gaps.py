import pandas as pd
import sqlite3

# Load data
conn = sqlite3.connect('database_av.db')
query = 'SELECT * FROM TECL_av_5min WHERE DATE(timestamp) >= "2024-01-01" ORDER BY timestamp'
df = pd.read_sql_query(query, conn)
conn.close()

# Parse dates
df['timestamp'] = pd.to_datetime(df['timestamp'])
df['date'] = df['timestamp'].dt.date

# Look for gap days
daily_open = df.groupby('date')['open'].first()
daily_close = df.groupby('date')['close'].last()
prev_close = daily_close.shift(1)
gaps = ((daily_open - prev_close) / prev_close) * 100

# Find major gaps
major_gaps = gaps[gaps < -5]
print('Major Gap Days (< -5%):')
for date, gap in major_gaps.items():
    print(f'  {date}: {gap:.2f}%')

print(f'\nTotal major gap days: {len(major_gaps)}')

# Check what happened on those days
print('\nWhat happened on gap days:')
for date in list(major_gaps.index)[:5]:
    day_data = df[df['date'] == date]
    if not day_data.empty:
        open_price = day_data.iloc[0]['open']
        close_price = day_data.iloc[-1]['close']
        low_price = day_data['low'].min()
        high_price = day_data['high'].max()
        day_return = (close_price - open_price) / open_price * 100
        recovery = (close_price - low_price) / low_price * 100
        print(f'\n{date}:')
        print(f'  Gap: {major_gaps[date]:.2f}%')
        print(f'  Intraday: Open={open_price:.2f}, Low={low_price:.2f}, High={high_price:.2f}, Close={close_price:.2f}')
        print(f'  Day Return: {day_return:.2f}%')
        print(f'  Recovery from low: {recovery:.2f}%')
