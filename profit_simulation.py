"""
Profit Simulation based on GOSPEL trading logic
Simulates monthly $100 investments with the bot's trading strategy
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random

class TradingSimulation:
    def __init__(self):
        # From Brains/ai_system.py
        self.SPREAD_COST = 0.00019  # 0.019% per trade
        self.OVERNIGHT_FUNDING_LONG = -0.00023  # -0.023% per day
        
        # From settings (defaults)
        self.investment_pct = 0.99  # 99% of available
        self.leverage = 1.0
        self.stop_loss_pct = 0.02  # 2%
        self.confidence_threshold = 0.30
        
        # Account tracking
        self.balance = 0
        self.total_invested = 0
        self.trades = []
        
    def calculate_daily_return(self, day_of_week):
        """Simulate daily return based on the bot's logic"""
        
        # Base components (simplified from actual indicators)
        trend_signal = random.uniform(-0.01, 0.01)  # Trend component
        momentum_signal = random.uniform(-0.005, 0.005)  # Momentum
        volume_signal = random.uniform(-0.002, 0.002)  # Volume
        
        # Day of week bias (from ai_system.py)
        day_bias = {
            'Monday': 0,
            'Tuesday': 0.003,  # Bullish bias
            'Wednesday': 0.001,  # Slight bullish
            'Thursday': -0.003,  # Bearish bias
            'Friday': 0.002,  # Bullish bias
            'Saturday': 0,
            'Sunday': 0
        }
        
        # Calculate total daily return
        base_return = trend_signal + momentum_signal + volume_signal + day_bias.get(day_of_week, 0)
        
        # Add market noise
        noise = np.random.normal(0, 0.005)
        daily_return = base_return + noise
        
        # Apply stop loss if triggered
        if daily_return < -self.stop_loss_pct:
            daily_return = -self.stop_loss_pct
            
        # Subtract costs (spread + overnight funding)
        daily_return -= (self.SPREAD_COST * 2 + self.OVERNIGHT_FUNDING_LONG)
        
        return daily_return
    
    def simulate_month(self, month_num, add_deposit=False):
        """Simulate one month of trading"""
        
        # Add monthly deposit on the 25th
        if add_deposit:
            self.balance += 100
            self.total_invested += 100
            
        # Simulate ~20 trading days per month
        monthly_returns = []
        for day in range(20):
            # Get day of week (simplified)
            day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
            day_of_week = day_names[day % 5]
            
            # Calculate position size (99% of balance with leverage)
            position_size = self.balance * self.investment_pct * self.leverage
            
            # Get daily return
            daily_return = self.calculate_daily_return(day_of_week)
            
            # Apply return to position
            daily_pnl = position_size * daily_return
            self.balance += daily_pnl
            monthly_returns.append(daily_return)
            
            # Record trade (simplified)
            self.trades.append({
                'month': month_num,
                'day': day,
                'day_of_week': day_of_week,
                'position_size': position_size,
                'return': daily_return,
                'pnl': daily_pnl,
                'balance': self.balance
            })
            
        return np.mean(monthly_returns), np.std(monthly_returns)
    
    def run_simulation(self, months=12):
        """Run full simulation"""
        
        print("="*60)
        print("Trading Bot Profit Simulation")
        print("Initial Investment: $100")
        print("Monthly Addition: $100 on the 25th")
        print(f"Strategy: {self.investment_pct*100}% invested, {self.leverage}x leverage")
        print(f"Stop Loss: {self.stop_loss_pct*100}%")
        print("="*60)
        
        monthly_stats = []
        
        for month in range(1, months + 1):
            # Add deposit (first month and every 25th)
            add_deposit = True
            
            # Run month simulation
            avg_return, std_return = self.simulate_month(month, add_deposit)
            
            monthly_stats.append({
                'Month': month,
                'Balance': round(self.balance, 2),
                'Total Invested': self.total_invested,
                'P&L': round(self.balance - self.total_invested, 2),
                'Return %': round(((self.balance - self.total_invested) / self.total_invested * 100), 2) if self.total_invested > 0 else 0,
                'Avg Daily Return': f"{avg_return*100:.3f}%",
                'Volatility': f"{std_return*100:.3f}%"
            })
            
            print(f"Month {month:2d}: Balance=${self.balance:8.2f} | "
                  f"Invested=${self.total_invested:6.0f} | "
                  f"P&L=${self.balance-self.total_invested:+8.2f} | "
                  f"Return={((self.balance-self.total_invested)/self.total_invested*100):+6.2f}%")
        
        print("="*60)
        print(f"Final Balance: ${self.balance:.2f}")
        print(f"Total Invested: ${self.total_invested:.2f}")
        print(f"Total Profit/Loss: ${self.balance - self.total_invested:+.2f}")
        print(f"Total Return: {((self.balance - self.total_invested) / self.total_invested * 100):+.2f}%")
        print("="*60)
        
        # Show best/worst days
        df_trades = pd.DataFrame(self.trades)
        best_trades = df_trades.nlargest(5, 'pnl')
        worst_trades = df_trades.nsmallest(5, 'pnl')
        
        print("\nBest 5 Trading Days:")
        for _, trade in best_trades.iterrows():
            print(f"  Month {trade['month']}, Day {trade['day']:2d} ({trade['day_of_week']:9s}): ${trade['pnl']:+8.2f}")
            
        print("\nWorst 5 Trading Days:")
        for _, trade in worst_trades.iterrows():
            print(f"  Month {trade['month']}, Day {trade['day']:2d} ({trade['day_of_week']:9s}): ${trade['pnl']:+8.2f}")
        
        return monthly_stats

# Run multiple simulations for statistical significance
def monte_carlo_simulation(num_simulations=100, months=12):
    """Run multiple simulations to get expected range"""
    
    final_balances = []
    final_returns = []
    
    for i in range(num_simulations):
        sim = TradingSimulation()
        sim.run_simulation(months)
        final_balances.append(sim.balance)
        final_returns.append((sim.balance - sim.total_invested) / sim.total_invested * 100)
    
    print("\n" + "="*60)
    print(f"Monte Carlo Results ({num_simulations} simulations, {months} months):")
    print("="*60)
    print(f"Average Final Balance: ${np.mean(final_balances):.2f}")
    print(f"Median Final Balance: ${np.median(final_balances):.2f}")
    print(f"Best Case (95th percentile): ${np.percentile(final_balances, 95):.2f}")
    print(f"Worst Case (5th percentile): ${np.percentile(final_balances, 5):.2f}")
    print(f"Average Return: {np.mean(final_returns):.2f}%")
    print(f"Median Return: {np.median(final_returns):.2f}%")
    print("="*60)

if __name__ == "__main__":
    # Single detailed simulation
    print("\nDETAILED SINGLE SIMULATION:")
    sim = TradingSimulation()
    monthly_stats = sim.run_simulation(12)
    
    # Monte Carlo for statistical significance
    print("\n\nMONTE CARLO ANALYSIS:")
    monte_carlo_simulation(100, 12)
    
    print("\n⚠️ IMPORTANT DISCLAIMERS:")
    print("1. This simulation is based on the bot's logic but uses simplified market models")
    print("2. Actual results depend on market conditions, execution quality, and data availability")
    print("3. Past performance does not guarantee future results")
    print("4. The bot trades at market close which may have different dynamics")
    print("5. Slippage, gaps, and extreme events are not fully modeled")
