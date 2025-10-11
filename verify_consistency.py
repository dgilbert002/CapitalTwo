"""
Verify database and settings consistency
"""
import os
from bot.settings import TradingBotSettings

print("="*70)
print("VERIFICATION: Database and Settings Consistency")
print("="*70)

# Load settings
settings = TradingBotSettings()

print("\n📊 DATABASE CONFIGURATION:")
print("-"*70)

# Check which databases exist
databases = {
    'database.db': os.path.exists('database.db'),
    'database_av.db': os.path.exists('database_av.db'),
    'database_cap.db': os.path.exists('database_cap.db')
}

for db, exists in databases.items():
    status = "✅ EXISTS" if exists else "❌ NOT FOUND"
    print(f"{db:<20} {status}")

# Check Alpha Vantage settings
av_db = settings.get('ALPHA_VANTAGE', 'database', 'NOT SET')
print(f"\nAlpha Vantage DB: {av_db}")

print("\n💰 FINANCE SETTINGS:")
print("-"*70)

# Check FINANCE section
if settings.has_section('FINANCE'):
    print("✅ [FINANCE] section exists")
    start_balance = settings.get('FINANCE', 'start_balance', 'NOT SET')
    monthly_top_up = settings.get('FINANCE', 'monthly_top_up', 'NOT SET')
    invest_pct = settings.get('FINANCE', 'invest_pct', 'NOT SET')
    
    print(f"  start_balance: ${start_balance}")
    print(f"  monthly_top_up: ${monthly_top_up}")
    print(f"  invest_pct: {invest_pct}")
else:
    print("❌ [FINANCE] section missing!")

# Check STRATEGY section
print("\n🎯 STRATEGY SETTINGS:")
print("-"*70)

if settings.has_section('STRATEGY'):
    print("✅ [STRATEGY] section exists")
    strategy_mode = settings.get('STRATEGY', 'strategy_mode', 'NOT SET')
    enable_crash = settings.get('STRATEGY', 'enable_crash_protection', 'NOT SET')
    
    print(f"  strategy_mode: {strategy_mode}")
    print(f"  enable_crash_protection: {enable_crash}")
    
    # Check for duplicate finance settings
    if settings.config.has_option('STRATEGY', 'start_balance'):
        print("  ⚠️ WARNING: start_balance in STRATEGY section (should be in FINANCE only)")
    if settings.config.has_option('STRATEGY', 'monthly_top_up'):
        print("  ⚠️ WARNING: monthly_top_up in STRATEGY section (should be in FINANCE only)")
else:
    print("❌ [STRATEGY] section missing!")

print("\n✅ RECOMMENDATIONS:")
print("-"*70)
print("1. Use database_av.db for ALL analysis and backtesting")
print("2. Use [FINANCE] section for all money-related settings")
print("3. Use [STRATEGY] section only for strategy selection")
print("4. database.db can be kept for Capital.com real-time data")

print("\n📋 CURRENT STATUS:")
print("-"*70)

# Final check
issues = []

if not databases['database_av.db']:
    issues.append("❌ Alpha Vantage database missing - run: python alpha_vantage_downloader.py --initial")

if not settings.has_section('FINANCE'):
    issues.append("❌ [FINANCE] section missing in settings.txt")

if av_db != 'database_av.db':
    issues.append(f"⚠️ Alpha Vantage database set to {av_db}, should be database_av.db")

if settings.config.has_option('STRATEGY', 'start_balance'):
    issues.append("⚠️ Duplicate finance settings in [STRATEGY] section")

if issues:
    print("Issues found:")
    for issue in issues:
        print(f"  {issue}")
else:
    print("✅ All settings and databases are properly configured!")
    print("✅ System is using database_av.db for analysis")
    print("✅ Finance settings come from [FINANCE] section")
