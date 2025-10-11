# Database and Settings Consolidation

## Current Issues

### 1. Database Confusion
- **database.db** - Used for Capital.com real-time data (for execution)
- **database_av.db** - Used for Alpha Vantage historical data (for analysis)

### 2. Settings Inconsistency
Multiple sections and defaults:
- `[FINANCE]` section - Used by elite scripts (Test1.py, Test3.py)
- `[STRATEGY]` section - Used by some scripts
- Hardcoded defaults vary: 100 vs 500

## Recommended Fix

### Database Strategy
1. **Keep both databases** but clarify usage:
   - `database.db` → Rename to `database_capital.db` for clarity
   - `database_av.db` → Primary database for all analysis and backtesting

2. **Update all analysis scripts** to use `database_av.db` exclusively

### Settings Consolidation
1. **Use [FINANCE] section** as the single source of truth:
   ```ini
   [FINANCE]
   start_balance = 500
   monthly_top_up = 100
   invest_pct = 0.99
   ```

2. **Remove [STRATEGY] section** to avoid confusion

3. **All scripts should read from [FINANCE]** with consistent defaults:
   ```python
   start_balance = float(settings.get('FINANCE', 'start_balance', '500'))
   ```

## Files to Update

### High Priority (Analysis/Backtesting)
- ✅ Brains/Test1.py - Already uses FINANCE
- ✅ Brains/Test3.py - Already uses FINANCE
- ✅ Brains/Test5_TwoSignals.py - Already uses FINANCE
- ✅ Test6_Proper.py - Already uses FINANCE
- ✅ Brains/Test_Strategies.py - Already updated to use FINANCE
- ❌ backtest_test7.py - Uses STRATEGY section
- ❌ compare_all_strategies.py - Uses STRATEGY section
- ❌ show_real_performance.py - Uses STRATEGY section

### Trading Bot
- bot/trader.py - Should use database_av.db for analysis, keep database.db for Capital.com data
- main.py - Should clarify which database for what purpose
