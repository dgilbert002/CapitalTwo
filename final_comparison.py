"""
Final Comparison - Using Existing Elite Model Scripts
Shows actual results from the proven backtesting logic
"""

import subprocess
import sys
import os

def run_and_capture(script_path):
    """Run a script and capture its final balance"""
    result = subprocess.run([sys.executable, script_path], 
                          capture_output=True, text=True, cwd=os.getcwd())
    output = result.stdout
    
    # Extract final balance from output
    for line in output.split('\n'):
        if 'Final Balance:' in line:
            balance = line.split('$')[1].split()[0].replace(',', '')
            return float(balance)
        elif 'Balance:' in line and '$' in line:
            # Alternative format
            parts = line.split('$')
            if len(parts) > 1:
                balance = parts[1].split()[0].replace(',', '')
                try:
                    return float(balance)
                except:
                    pass
    return None

def main():
    print("\n" + "="*80)
    print("FINAL STRATEGY COMPARISON - ACTUAL RESULTS")
    print("Using the exact elite model scripts and current database")
    print("="*80)
    
    # Run each test script
    tests = [
        ("All 6 Signals NO Protection", "Brains/Test1.py"),
        ("All 6 Signals WITH Protection", "Brains/Test3.py"),
        ("Two RSI Strategies", "Brains/Test5_TwoSignals.py"),
        ("Test6 - 8 Signals WITH Protection", "Test6_Proper.py"),
    ]
    
    results = []
    
    print("\nRunning backtests...")
    print("-"*80)
    
    for name, script in tests:
        if os.path.exists(script):
            print(f"Running {name}...", end=' ')
            balance = run_and_capture(script)
            if balance:
                results.append((name, balance))
                print(f"${balance:,.0f}")
            else:
                print("Error parsing result")
        else:
            print(f"Script not found: {script}")
    
    # Also run our Test_Strategies.py to get Test7 results
    print("\nRunning Test7 comparison...")
    result = subprocess.run([sys.executable, "Brains/Test_Strategies.py"], 
                          capture_output=True, text=True)
    
    # Parse Test7 results from output
    for line in result.stdout.split('\n'):
        if 'Test7 - 9 Signals WITH Protection' in line and '$' in line:
            parts = line.split('$')
            if len(parts) > 1:
                balance = parts[1].split()[0].replace(',', '')
                try:
                    results.append(("Test7 - 9 Signals WITH Protection", float(balance)))
                except:
                    pass
        elif 'Test7 - 9 Signals NO Protection' in line and '$' in line:
            parts = line.split('$')
            if len(parts) > 1:
                balance = parts[1].split()[0].replace(',', '')
                try:
                    results.append(("Test7 - 9 Signals NO Protection", float(balance)))
                except:
                    pass
    
    # Print summary
    print("\n" + "="*80)
    print("SUMMARY OF ACTUAL RESULTS")
    print("="*80)
    print(f"{'Strategy':<45} {'Final Balance':>15} {'vs HTML':>15}")
    print("-"*80)
    
    # Expected values from HTML
    html_values = {
        "All 6 Signals WITH Protection": 699074,
        "All 6 Signals NO Protection": 376004,
        "Two RSI WITH Protection": 485948,
        "Two RSI NO Protection": 348803,
        "Test6 - 8 Signals WITH Protection": 958260,
        "Test6 - 8 Signals NO Protection": 509453,
    }
    
    for name, balance in sorted(results, key=lambda x: x[1], reverse=True):
        html_val = html_values.get(name, 0)
        diff = ((balance - html_val) / html_val * 100) if html_val > 0 else 0
        print(f"{name:<45} ${balance:>14,.0f} {diff:>14.1f}%")
    
    print("\n" + "="*80)
    print("KEY FINDINGS:")
    print("-"*80)
    
    # Find best performer
    if results:
        best = max(results, key=lambda x: x[1])
        print(f"🏆 BEST PERFORMER: {best[0]}")
        print(f"   Final Balance: ${best[1]:,.0f}")
        print(f"   Return: {((best[1]-500)/500)*100:,.1f}%")
    
    print("\n📊 Why the differences from HTML values?")
    print("   1. HTML shows idealized/baseline results")
    print("   2. Data period may differ (check settings.txt dates)")
    print("   3. Some strategies evolved during development")
    print("   4. Test6/Test7 include additional signals not in original tests")
    print("="*80)

if __name__ == "__main__":
    main()
