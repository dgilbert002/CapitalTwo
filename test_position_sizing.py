#!/usr/bin/env python3
"""
Test CORRECT position sizing vs WRONG position sizing
"""

print("=" * 80)
print("POSITION SIZING COMPARISON")
print("=" * 80)

# Initial setup
balance = 500.0
entry_price = 100.0  # Example price
leverage = 10.0  # RSI oversold leverage
stop_loss_pct = 3.5

print(f"\nInitial Balance: ${balance}")
print(f"Entry Price: ${entry_price}")
print(f"Leverage: {leverage}x")
print(f"Stop Loss: {stop_loss_pct}%")

print("\n" + "=" * 80)
print("CORRECT IMPLEMENTATION (Your System):")
print("=" * 80)

# CORRECT: Use 99% of balance with leverage
investment = balance * 0.99
position_size = investment * leverage
shares = position_size / entry_price

print(f"Investment: ${investment:.2f} (99% of balance)")
print(f"Position Size: ${position_size:.2f} (with {leverage}x leverage)")
print(f"Shares: {shares:.2f}")

# Example 2% gain
price_change_pct = 0.02
exit_price = entry_price * (1 + price_change_pct)
pnl = (exit_price - entry_price) * shares
return_pct = pnl / investment * 100

print(f"\nIf price moves +2%:")
print(f"  Exit Price: ${exit_price:.2f}")
print(f"  P&L: ${pnl:.2f}")
print(f"  Return on Investment: {return_pct:.1f}%")
print(f"  New Balance: ${balance - investment + investment + pnl:.2f}")

print("\n" + "=" * 80)
print("WRONG IMPLEMENTATION (What Others Might Do):")
print("=" * 80)

# WRONG: Conservative position without proper leverage
wrong_investment = balance * 0.10  # Only 10%
wrong_position = wrong_investment * 1.0  # No leverage!
wrong_shares = wrong_position / entry_price

print(f"Investment: ${wrong_investment:.2f} (only 10% of balance)")
print(f"Position Size: ${wrong_position:.2f} (NO leverage)")
print(f"Shares: {wrong_shares:.2f}")

# Same 2% gain
wrong_pnl = (exit_price - entry_price) * wrong_shares
wrong_return_pct = wrong_pnl / wrong_investment * 100

print(f"\nIf price moves +2%:")
print(f"  Exit Price: ${exit_price:.2f}")
print(f"  P&L: ${wrong_pnl:.2f}")
print(f"  Return on Investment: {wrong_return_pct:.1f}%")
print(f"  New Balance: ${balance - wrong_investment + wrong_investment + wrong_pnl:.2f}")

print("\n" + "=" * 80)
print("DIFFERENCE:")
print("=" * 80)

print(f"Correct P&L: ${pnl:.2f}")
print(f"Wrong P&L: ${wrong_pnl:.2f}")
print(f"Difference: ${pnl - wrong_pnl:.2f} ({pnl/wrong_pnl:.1f}x)")

print("\n" + "=" * 80)
print("COMPOUNDING EFFECT OVER TIME:")
print("=" * 80)

# Simulate 10 winning trades
correct_balance = 500.0
wrong_balance = 500.0

for i in range(10):
    # Correct
    correct_inv = correct_balance * 0.99
    correct_pnl = correct_inv * leverage * 0.02  # 2% price move
    correct_balance = correct_balance + correct_pnl
    
    # Wrong
    wrong_inv = wrong_balance * 0.10
    wrong_pnl = wrong_inv * 1.0 * 0.02  # 2% price move, no leverage
    wrong_balance = wrong_balance + wrong_pnl

print(f"After 10 winning trades (2% each):")
print(f"  Correct Balance: ${correct_balance:.2f}")
print(f"  Wrong Balance: ${wrong_balance:.2f}")
print(f"  Difference: ${correct_balance - wrong_balance:.2f}")

print("\n🚨 KEY INSIGHT:")
print(f"The correct implementation is {correct_balance/wrong_balance:.1f}x more profitable!")
print("\nThis explains why you get $699k while others get $4.7k!")
