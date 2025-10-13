# 📚 COMPLETE GUIDE: How to Add a New Trading Strategy

## 🚨 CRITICAL: READ THIS FIRST
This guide explains EXACTLY how to add a new trading strategy to the CapitalTwo trading bot. Follow EVERY step in order. Do NOT skip steps or make assumptions.

---

## 📋 CHECKLIST OVERVIEW
When adding a new strategy, you must update these 7 files:
1. ✅ `Brains/strategy_signals.py` - Define signal parameters and detection function
2. ✅ `Brains/ai_system.py` - Add signal evaluation logic
3. ✅ `test_all_proven_strategies.py` - Add to strategy combinations
4. ✅ `bot/trader.py` - Map UI values to strategy modes
5. ✅ `static/index.html` - Add UI radio buttons
6. ✅ `main.py` - Handle WebSocket strategy display
7. ✅ Create test file - Validate the strategy works

---

## 📝 STEP 1: Add Signal Configuration
**File:** `Brains/strategy_signals.py`

### 1.1 Add to SIGNAL_CONFIGS Dictionary
Find the `SIGNAL_CONFIGS` dictionary (around line 10-50) and add your new signal:

```python
SIGNAL_CONFIGS = {
    # ... existing signals ...
    
    # ADD YOUR NEW SIGNAL HERE (example: stochastic oversold)
    'stochastic_oversold': {
        'leverage': 6.0,           # How much leverage to use (1.0 to 10.0)
        'stop_loss_pct': 5.0,      # Stop loss percentage (2.0 to 10.0)
        'period': 14,              # Lookback period for calculation
        'smooth_k': 3,             # %K smoothing period (if applicable)
        'smooth_d': 3,             # %D smoothing period (if applicable)
        'oversold_threshold': 20,  # Below this = oversold
        'win_rate': 72.5          # Priority weight (0-100, higher = higher priority)
    }
}
```

### 1.2 Create the Detection Function
Add this AFTER the `SIGNAL_CONFIGS` dictionary (around line 100+):

```python
def check_stochastic_oversold(df, idx, period=14, smooth_k=3, smooth_d=3, oversold_threshold=20):
    """
    Check if stochastic is oversold
    
    Args:
        df: DataFrame with OHLC data
        idx: Current index to check
        period: Lookback period for stochastic
        smooth_k: %K smoothing period
        smooth_d: %D smoothing period  
        oversold_threshold: Below this level = oversold
        
    Returns:
        bool: True if signal fires, False otherwise
    """
    # SAFETY CHECK: Ensure enough data
    if len(df) < idx + 1 or idx < period + smooth_k + smooth_d:
        return False
    
    try:
        # Calculate Stochastic
        high_period = df['highPrice'].iloc[idx-period+1:idx+1].max()
        low_period = df['lowPrice'].iloc[idx-period+1:idx+1].min()
        current_close = df['closePrice'].iloc[idx]
        
        # Avoid division by zero
        if high_period == low_period:
            return False
            
        # Calculate %K
        k_percent = ((current_close - low_period) / (high_period - low_period)) * 100
        
        # Signal fires if %K is below oversold threshold
        return k_percent < oversold_threshold
        
    except Exception as e:
        logger.error(f"Error in check_stochastic_oversold: {e}")
        return False
```

### 1.3 Update check_all_signals Function
Find the `check_all_signals` function (around line 200+) and add your signal to strategy modes:

```python
def check_all_signals(df, idx, strategy_mode='all_6_signals', enable_crash_protection=True):
    # ... existing code ...
    
    # Define which signals to use for each strategy mode
    if strategy_mode == 'all_6_signals':
        # ... existing signals ...
    elif strategy_mode == 'test9':  # ADD THIS NEW MODE
        selected_signals = [
            'rsi_oversold', 'rsi_bullish_cross_50', 'bb_lower_break',
            'price_above_vwap', 'roc_below_threshold', 'macd_positive',
            'keltner_lower_break', 'macd_histogram_negative', 
            'macd_histogram_negative_v2', 'stochastic_oversold'  # YOUR NEW SIGNAL
        ]
```

---

## 📝 STEP 2: Add Signal Evaluation
**File:** `Brains/ai_system.py`

### 2.1 Import the Check Function
At the top of the file (around line 5-15), add import:

```python
from Brains.strategy_signals import (
    # ... existing imports ...
    check_stochastic_oversold  # ADD THIS
)
```

### 2.2 Add to STRATEGIES Dictionary
Find the `STRATEGIES` dictionary (around line 30-80) and add:

```python
# In __init__ method or at module level:
STRATEGIES = {
    # ... existing strategies ...
    
    'test9': {  # Your new test mode
        'signals': [
            'rsi_oversold', 'rsi_bullish_cross_50', 'bb_lower_break',
            'price_above_vwap', 'roc_below_threshold', 'macd_positive',
            'keltner_lower_break', 'macd_histogram_negative',
            'macd_histogram_negative_v2', 'stochastic_oversold'
        ]
    }
}
```

### 2.3 Add Signal Evaluation Logic
Find the `_eval_signals` method (around line 150-250) and add:

```python
def _eval_signals(self, df, idx, conds):
    # ... existing signal checks ...
    
    # ADD YOUR NEW SIGNAL CHECK
    if 'stochastic_oversold' in self.selected_strategies:
        config = self.selected_strategies['stochastic_oversold']
        fired_signals['stochastic_oversold'] = check_stochastic_oversold(
            df, idx,
            period=config.get('period', 14),
            smooth_k=config.get('smooth_k', 3),
            smooth_d=config.get('smooth_d', 3),
            oversold_threshold=config.get('oversold_threshold', 20)
        )
```

### 2.4 Handle Protection Modes
In the `__init__` method (around line 20-40), add:

```python
# Handle new test9 modes
if strategy_mode == 'test9_no_protection':
    self.strategy_mode = 'test9'
    self.enable_crash_protection = False
elif strategy_mode == 'test9_with_protection':
    self.strategy_mode = 'test9'
    self.enable_crash_protection = True
```

---

## 📝 STEP 3: Add to Test Framework
**File:** `test_all_proven_strategies.py`

### 3.1 Define Strategy Combination
Find where `STRATEGIES` is defined (if external) or in the main function (around line 400+):

```python
# Add your new test configuration
test_configs = [
    # ... existing configs ...
    
    # ADD YOUR NEW STRATEGY TEST
    ("Test9 - 10 Signals", {
        'rsi_oversold': SIGNAL_CONFIGS['rsi_oversold'],
        'rsi_bullish_cross_50': SIGNAL_CONFIGS['rsi_bullish_cross_50'],
        'bb_lower_break': SIGNAL_CONFIGS['bb_lower_break'],
        'price_above_vwap': SIGNAL_CONFIGS['price_above_vwap'],
        'roc_below_threshold': SIGNAL_CONFIGS['roc_below_threshold'],
        'macd_positive': SIGNAL_CONFIGS['macd_positive'],
        'keltner_lower_break': SIGNAL_CONFIGS['keltner_lower_break'],
        'macd_histogram_negative': SIGNAL_CONFIGS['macd_histogram_negative'],
        'macd_histogram_negative_v2': SIGNAL_CONFIGS['macd_histogram_negative_v2'],
        'stochastic_oversold': SIGNAL_CONFIGS['stochastic_oversold']
    }),
]
```

### 3.2 Update eval_signals Function
Find the `eval_signals` function (around line 50-150) and add:

```python
def eval_signals(df, strategies):
    # ... existing signals ...
    
    # ADD YOUR NEW SIGNAL EVALUATION
    if 'stochastic_oversold' in strategies:
        config = strategies['stochastic_oversold']
        fired['stochastic_oversold'] = check_stochastic_oversold(
            df, len(df)-1,  # Check last row
            period=config.get('period', 14),
            smooth_k=config.get('smooth_k', 3),
            smooth_d=config.get('smooth_d', 3),
            oversold_threshold=config.get('oversold_threshold', 20)
        )
```

---

## 📝 STEP 4: Map UI Values
**File:** `bot/trader.py`

### 4.1 Add Strategy Mode Mapping
Find the `__init__` method (around line 50-100) and add mapping:

```python
# In __init__ method, where strategy_mode is handled:
if self.settings.has_option('STRATEGY', 'strategy_mode'):
    ui_strategy = self.settings.get('STRATEGY', 'strategy_mode')
    
    # ... existing mappings ...
    
    # ADD YOUR NEW MAPPINGS
    elif ui_strategy == 'test9_no_protection':
        self.ai_system.strategy_mode = 'test9'
        self.ai_system.enable_crash_protection = False
    elif ui_strategy == 'test9_with_protection':
        self.ai_system.strategy_mode = 'test9'
        self.ai_system.enable_crash_protection = True
```

---

## 📝 STEP 5: Add UI Controls
**File:** `static/index.html`

### 5.1 Add Radio Buttons
Find the strategy radio buttons section (search for "strategyMode" around line 800-900):

```html
<!-- Find the existing radio buttons and add: -->
<div class="form-check">
    <input class="form-check-input" type="radio" name="strategyMode" 
           id="test9NoProtection" value="test9_no_protection">
    <label class="form-check-label" for="test9NoProtection">
        <strong>Test9 - 10 Signals NO Protection</strong>
        <small class="text-muted d-block">Includes Stochastic Oversold</small>
    </label>
</div>

<div class="form-check">
    <input class="form-check-input" type="radio" name="strategyMode" 
           id="test9WithProtection" value="test9_with_protection">
    <label class="form-check-label" for="test9WithProtection">
        <strong>Test9 - 10 Signals WITH Protection</strong>
        <small class="text-muted d-block">Includes Stochastic + Crash Protection</small>
    </label>
</div>
```

### 5.2 Update JavaScript saveStrategySettings
Find `saveStrategySettings` function (around line 1800-2000):

```javascript
function saveStrategySettings() {
    // ... existing code ...
    
    // ADD EXPECTED RESULTS FOR YOUR NEW STRATEGY
    if (actualStrategy === 'test9_no_protection' || actualStrategy === 'test9_with_protection') {
        expectedResults = 'Test9 - 10 Signals (includes Stochastic Oversold)';
        if (actualStrategy === 'test9_with_protection') {
            expectedResults += ' WITH protection';
        } else {
            expectedResults += ' NO protection';
        }
    }
}
```

### 5.3 Update loadSavedStrategySettings
Find `loadSavedStrategySettings` function (around line 2100-2200):

```javascript
function loadSavedStrategySettings(data) {
    // ... existing mappings ...
    
    // ADD YOUR NEW MAPPINGS
    } else if (strategyMode === 'test9_no_protection') {
        document.getElementById('test9NoProtection').checked = true;
    } else if (strategyMode === 'test9_with_protection') {
        document.getElementById('test9WithProtection').checked = true;
    }
}
```

### 5.4 Add to Strategy Details Modal
Find the strategy details modal (search for "strategyDetailsModal" around line 2400+):

```html
<!-- Add accordion item for your new strategy -->
<div class="accordion-item">
    <h2 class="accordion-header">
        <button class="accordion-button collapsed" type="button" 
                data-bs-toggle="collapse" data-bs-target="#collapseTest9">
            Test9 - 10 Signals (Includes Stochastic)
        </button>
    </h2>
    <div id="collapseTest9" class="accordion-collapse collapse">
        <div class="accordion-body">
            <p><strong>Overview:</strong> Adds Stochastic Oversold to the 9-signal suite.</p>
            
            <h6>Signals Included:</h6>
            <ul>
                <li>All Test7 signals PLUS:</li>
                <li><strong>Stochastic Oversold:</strong>
                    <ul>
                        <li>Trigger: Stochastic %K < 20</li>
                        <li>Meaning: Extreme oversold condition</li>
                        <li>Leverage: 6x</li>
                        <li>Stop Loss: 5%</li>
                        <li>Priority: 72.5</li>
                    </ul>
                </li>
            </ul>
            
            <div class="alert alert-info">
                <strong>Expected Performance:</strong><br>
                • Without Protection: $XXX,XXX<br>
                • With Protection: $XXX,XXX
            </div>
        </div>
    </div>
</div>
```

---

## 📝 STEP 6: Update WebSocket Handler
**File:** `main.py`

### 6.1 Update Strategy Display
Find where WebSocket data is prepared (around line 170-180):

```python
# In the WebSocket data preparation:
data = {
    # ... existing data ...
    "strategy_mode": app_state.settings.get("STRATEGY", "strategy_mode", "enhanced"),
    # Make sure new modes are handled
}
```

---

## 📝 STEP 7: Create Test File
**File:** Create new `test_test9_strategy.py`

```python
"""
Test script for Test9 strategy (10 signals including Stochastic Oversold)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_all_proven_strategies import *
from Brains.strategy_signals import SIGNAL_CONFIGS, check_stochastic_oversold

def test_new_strategy():
    """Test the new Test9 strategy"""
    
    print("="*80)
    print("TESTING TEST9 STRATEGY (10 SIGNALS)")
    print("="*80)
    
    # Load data
    df = load_data()
    print(f"Loaded {len(df)} candles from {df['date'].min()} to {df['date'].max()}")
    
    # Test stochastic signal alone first
    print("\n1. Testing Stochastic Oversold Signal Alone:")
    print("-"*40)
    
    stochastic_only = {
        'stochastic_oversold': SIGNAL_CONFIGS['stochastic_oversold']
    }
    
    result = run_strategy(df, stochastic_only, "Stochastic Only", enable_protection=False)
    print(f"  Final Balance: ${result['final_balance']:,.2f}")
    print(f"  Total Trades: {result['total_trades']}")
    print(f"  Win Rate: {result['win_rate']:.1f}%")
    
    # Test full Test9 strategy
    print("\n2. Testing Full Test9 Strategy:")
    print("-"*40)
    
    test9_signals = {
        'rsi_oversold': SIGNAL_CONFIGS['rsi_oversold'],
        'rsi_bullish_cross_50': SIGNAL_CONFIGS['rsi_bullish_cross_50'],
        'bb_lower_break': SIGNAL_CONFIGS['bb_lower_break'],
        'price_above_vwap': SIGNAL_CONFIGS['price_above_vwap'],
        'roc_below_threshold': SIGNAL_CONFIGS['roc_below_threshold'],
        'macd_positive': SIGNAL_CONFIGS['macd_positive'],
        'keltner_lower_break': SIGNAL_CONFIGS['keltner_lower_break'],
        'macd_histogram_negative': SIGNAL_CONFIGS['macd_histogram_negative'],
        'macd_histogram_negative_v2': SIGNAL_CONFIGS['macd_histogram_negative_v2'],
        'stochastic_oversold': SIGNAL_CONFIGS['stochastic_oversold']
    }
    
    # Without protection
    result_no_prot = run_strategy(df, test9_signals, "Test9 No Protection", enable_protection=False)
    print(f"\nTest9 WITHOUT Protection:")
    print(f"  Final Balance: ${result_no_prot['final_balance']:,.2f}")
    print(f"  Total Trades: {result_no_prot['total_trades']}")
    print(f"  Win Rate: {result_no_prot['win_rate']:.1f}%")
    print(f"  Max Drawdown: {result_no_prot['max_drawdown']:.1f}%")
    
    # With protection
    result_with_prot = run_strategy(df, test9_signals, "Test9 With Protection", enable_protection=True)
    print(f"\nTest9 WITH Protection:")
    print(f"  Final Balance: ${result_with_prot['final_balance']:,.2f}")
    print(f"  Total Trades: {result_with_prot['total_trades']}")
    print(f"  Win Rate: {result_with_prot['win_rate']:.1f}%")
    print(f"  Max Drawdown: {result_with_prot['max_drawdown']:.1f}%")
    
    # Compare with Test7
    print("\n3. Comparison with Test7:")
    print("-"*40)
    
    test7_signals = {k: v for k, v in test9_signals.items() if k != 'stochastic_oversold'}
    result_test7 = run_strategy(df, test7_signals, "Test7", enable_protection=True)
    
    improvement = result_with_prot['final_balance'] - result_test7['final_balance']
    improvement_pct = (improvement / result_test7['final_balance']) * 100
    
    print(f"Test7 Final Balance: ${result_test7['final_balance']:,.2f}")
    print(f"Test9 Final Balance: ${result_with_prot['final_balance']:,.2f}")
    print(f"Improvement: ${improvement:,.2f} ({improvement_pct:+.1f}%)")
    
    print("\n" + "="*80)
    print("TEST COMPLETE")
    print("="*80)

if __name__ == "__main__":
    test_new_strategy()
```

---

## 🧪 TESTING CHECKLIST

After implementing, run these tests IN ORDER:

### Test 1: Signal Detection
```bash
.venv\Scripts\python.exe test_test9_strategy.py
```
Expected: Should show trades for the new signal

### Test 2: Integration Test
```bash
.venv\Scripts\python.exe test_all_proven_strategies.py
```
Expected: Test9 should appear in results

### Test 3: UI Test
```bash
start.bat
# Open browser to http://localhost:8011
# Check radio buttons appear
# Select Test9 and save
# Check settings.txt updated
```

### Test 4: Bot Simulation
```bash
.venv\Scripts\python.exe -c "from bot.trader import TradingBot; bot = TradingBot(); print(bot.ai_system.strategy_mode)"
```
Expected: Should show 'test9' if Test9 selected

---

## ⚠️ COMMON MISTAKES TO AVOID

1. **DON'T** forget to import your check function in files that use it
2. **DON'T** use different parameter names between files (be consistent!)
3. **DON'T** forget to handle both `_no_protection` and `_with_protection` modes
4. **DON'T** skip the safety checks in your detection function
5. **DON'T** forget to test with empty/insufficient data
6. **DON'T** use `threshold` as a parameter name if it's not passed (like ROC)
7. **DON'T** forget to add to BOTH the UI radio buttons AND the JavaScript handlers

---

## 🔍 DEBUGGING TIPS

If the strategy doesn't work:

1. **Check Signal Firing:**
```python
# Add debug print in your check function:
print(f"Stochastic: {k_percent:.2f}, Threshold: {oversold_threshold}, Fires: {k_percent < oversold_threshold}")
```

2. **Check Strategy Loading:**
```python
# In bot/trader.py __init__:
print(f"Strategy mode: {self.ai_system.strategy_mode}")
print(f"Selected strategies: {self.ai_system.selected_strategies.keys()}")
```

3. **Check UI Mapping:**
```javascript
// In saveStrategySettings:
console.log('Selected strategy:', actualStrategy);
```

4. **Check Database:**
```sql
-- Check if signals are being recorded
SELECT signal, COUNT(*) FROM trades WHERE signal = 'stochastic_oversold' GROUP BY signal;
```

---

## 📊 EXPECTED RESULTS TEMPLATE

When documenting your new strategy, provide:

```markdown
## Test9 Strategy Results
- **Signals:** 10 (all Test7 + Stochastic Oversold)
- **Without Protection:** $XXX,XXX (XX% return, XXX trades)
- **With Protection:** $XXX,XXX (XX% return, XXX trades)
- **Improvement over Test7:** +$XX,XXX (+X.X%)
- **Best Use Case:** [Describe when this strategy works best]
- **Risk Level:** [Low/Medium/High]
```

---

## ✅ FINAL VERIFICATION

Before considering the strategy fully integrated:

1. ✅ Can you select it in the UI?
2. ✅ Does it save to settings.txt?
3. ✅ Does the bot load it on startup?
4. ✅ Does it generate trades in backtesting?
5. ✅ Does it show in Brain Preview?
6. ✅ Does it work with crash protection?
7. ✅ Are the results consistent across tests?

---

## 🆘 TROUBLESHOOTING

If something doesn't work, check these files for the EXACT pattern to follow:
- Look at how `macd_histogram_negative_v2` was added (it's the most recent)
- Compare Test7 implementation as it's the most complete
- Check `git diff` to see what files were modified

---

## 📝 NOTES FOR AI IMPLEMENTERS

1. **ALWAYS** run the test file after making changes
2. **NEVER** assume parameter names - check existing patterns
3. **ALWAYS** handle edge cases (empty data, missing values)
4. **NEVER** skip the UI integration - users need to select it
5. **ALWAYS** maintain the win_rate priority system
6. **NEVER** modify existing strategies when adding new ones
7. **ALWAYS** test both with and without crash protection

This guide is COMPLETE. Follow it step by step and the strategy WILL work.
