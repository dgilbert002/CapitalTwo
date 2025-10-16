#!/usr/bin/env python3
"""
Test the 6 indicators on TECL historical data to simulate trading results
"""
import asyncio
import pandas as pd
from datetime import datetime, timedelta
from bot.database import DatabaseManager
from Brains.ai_system import HybridIntelligentSystem
from bot.settings import TradingBotSettings
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class IndicatorTester:
    def __init__(self):
        self.db = DatabaseManager()
        self.ai_system = HybridIntelligentSystem()
        self.settings = TradingBotSettings()
        self.trades = []
        self.current_position = None
        
    def load_historical_data(self, epic='TECL', days=30):
        """Load historical 5-minute candles from database"""
        logger.info(f"Loading {days} days of data for {epic}")
        
        # Get candles from database
        candles = self.db.get_candles(epic, limit=days * 24 * 12)  # 5-min candles
        
        if not candles:
            logger.error("No candles found in database")
            return None
            
        # Convert to DataFrame
        df = pd.DataFrame(candles, columns=['epic', 'timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df = df.drop(columns=['epic'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        logger.info(f"Loaded {len(df)} candles from {df['timestamp'].min()} to {df['timestamp'].max()}")
        return df
        
    def identify_market_sessions(self, df):
        """Identify market open/close times (13:30-20:00 UTC Mon-Fri)"""
        sessions = []
        
        # Group by date
        df['date'] = df['timestamp'].dt.date
        
        for date, group in df.groupby('date'):
            # Check if weekday (0=Monday, 4=Friday)
            if group.iloc[0]['timestamp'].weekday() <= 4:
                # Find candles in market hours
                market_candles = group[
                    (group['timestamp'].dt.hour >= 13) & 
                    ((group['timestamp'].dt.hour < 20) | 
                     ((group['timestamp'].dt.hour == 20) & (group['timestamp'].dt.minute == 0)))
                ]
                
                if len(market_candles) > 0:
                    session = {
                        'date': date,
                        'open_time': market_candles.iloc[0]['timestamp'],
                        'close_time': market_candles.iloc[-1]['timestamp'],
                        'data': market_candles
                    }
                    sessions.append(session)
                    
        logger.info(f"Found {len(sessions)} trading sessions")
        return sessions
        
    def simulate_trading_day(self, session, full_df):
        """Simulate trading for one day following the bot's logic"""
        date = session['date']
        close_time = session['close_time']
        
        # T-30s: Close any open position
        close_trigger_time = close_time - timedelta(seconds=30)
        
        # T-15s: Analyze and potentially open new position
        trade_trigger_time = close_time - timedelta(seconds=15)
        
        # Find the candle at T-15s
        trade_candle_idx = full_df[full_df['timestamp'] <= trade_trigger_time].index[-1] if len(full_df[full_df['timestamp'] <= trade_trigger_time]) > 0 else None
        
        if trade_candle_idx is None:
            return
            
        # Get historical data up to this point (need at least 100 candles)
        if trade_candle_idx < 100:
            return
            
        historical_data = full_df.iloc[:trade_candle_idx + 1].copy()
        
        # Calculate technical indicators
        historical_data = self.ai_system.calculate_technical_indicators(historical_data)
        
        # Get the current day's data
        day_data = historical_data[historical_data['timestamp'].dt.date == date]
        
        # Run AI analysis
        analysis = self.ai_system.analyze_market_conditions(
            day_data,  # Pass the DataFrame, not dict
            historical_data,
            trade_trigger_time
        )
        
        # Check if we should trade
        min_confidence = self.settings.getfloat('BOT_CONFIG', 'ai_confidence_threshold', 30) / 100
        
        if analysis['confidence'] >= min_confidence and analysis['trade_signal'] != 'hold':
            # Get entry price (after indicator calculation, column is renamed)
            entry_price = historical_data.iloc[-1]['closePrice']
            
            # Calculate position details
            leverage = self.settings.getfloat('BOT_CONFIG', 'leverage', 4.0)
            stop_loss_pct = self.settings.getfloat('BOT_CONFIG', 'stop_loss_pct', 2.0)
            
            # For selected strategy, use its specific parameters if available
            if analysis.get('strategy_config'):
                leverage = analysis['strategy_config'].get('leverage', leverage)
                stop_loss_pct = analysis['strategy_config'].get('stop_loss_pct', stop_loss_pct)
            
            direction = 'LONG' if analysis['direction'] == 'long' else 'SHORT'
            stop_level = entry_price * (1 - stop_loss_pct / 100) if direction == 'LONG' else entry_price * (1 + stop_loss_pct / 100)
            
            trade = {
                'date': date,
                'entry_time': trade_trigger_time,
                'entry_price': entry_price,
                'direction': direction,
                'stop_level': stop_level,
                'stop_loss_pct': stop_loss_pct,
                'leverage': leverage,
                'confidence': analysis['confidence'],
                'signal': analysis['trade_signal'],
                'strategy': analysis.get('selected_strategy', 'unknown'),
                'strategy_config': analysis.get('strategy_config', {}),
                'fired_signals': analysis.get('fired_signals', {}),
                'exit_time': None,
                'exit_price': None,
                'exit_reason': None,
                'pnl': None,
                'pnl_pct': None
            }
            
            self.current_position = trade
            logger.info(f"{date} - OPEN {direction} @ ${entry_price:.2f} | Strategy: {trade['strategy']} | Leverage: {leverage}x | SL: {stop_loss_pct}% | Confidence: {trade['confidence']:.2%}")
            
    def close_position_at_market_close(self, session, full_df):
        """Close position at next market close (T-30s)"""
        if not self.current_position:
            return
            
        # Next day's close time
        close_time = session['close_time']
        close_trigger_time = close_time - timedelta(seconds=30)
        
        # Find exit price
        exit_candle = full_df[full_df['timestamp'] <= close_trigger_time].iloc[-1] if len(full_df[full_df['timestamp'] <= close_trigger_time]) > 0 else None
        
        if exit_candle is None:
            return
            
        # Handle both original and renamed columns
        exit_price = exit_candle.get('closePrice', exit_candle.get('close'))
        
        # Calculate P&L
        if self.current_position['direction'] == 'LONG':
            pnl_pct = ((exit_price - self.current_position['entry_price']) / self.current_position['entry_price']) * 100
        else:
            pnl_pct = ((self.current_position['entry_price'] - exit_price) / self.current_position['entry_price']) * 100
            
        # Apply leverage
        pnl_pct *= self.current_position['leverage']
        
        self.current_position['exit_time'] = close_trigger_time
        self.current_position['exit_price'] = exit_price
        self.current_position['exit_reason'] = 'Market Close (T-30s)'
        self.current_position['pnl_pct'] = pnl_pct
        
        logger.info(f"{session['date']} - CLOSE @ ${exit_price:.2f} | P&L: {pnl_pct:+.2f}% | Reason: {self.current_position['exit_reason']}")
        
        self.trades.append(self.current_position)
        self.current_position = None
        
    def check_stop_loss(self, df, current_idx):
        """Check if stop loss was hit during the day"""
        if not self.current_position:
            return False
            
        candle = df.iloc[current_idx]
        
        if self.current_position['direction'] == 'LONG':
            # Handle both original and renamed columns
            low_price = candle.get('lowPrice', candle.get('low'))
            if low_price <= self.current_position['stop_level']:
                # Stop loss hit
                exit_price = self.current_position['stop_level']
                pnl_pct = ((exit_price - self.current_position['entry_price']) / self.current_position['entry_price']) * 100
                pnl_pct *= self.current_position['leverage']
                
                self.current_position['exit_time'] = candle['timestamp']
                self.current_position['exit_price'] = exit_price
                self.current_position['exit_reason'] = 'Stop Loss'
                self.current_position['pnl_pct'] = pnl_pct
                
                logger.info(f"STOP LOSS HIT @ ${exit_price:.2f} | P&L: {pnl_pct:+.2f}%")
                
                self.trades.append(self.current_position)
                self.current_position = None
                return True
                
        return False
        
    def run_simulation(self):
        """Run the full simulation"""
        # Load data
        df = self.load_historical_data(days=30)
        if df is None:
            return
            
        # Identify trading sessions
        sessions = self.identify_market_sessions(df)
        
        # Simulate each day
        for i in range(len(sessions) - 1):
            current_session = sessions[i]
            next_session = sessions[i + 1]
            
            # Close any open position at current session close
            if self.current_position:
                self.close_position_at_market_close(current_session, df)
                
            # Analyze and potentially open new position
            self.simulate_trading_day(current_session, df)
            
            # Check for stop loss hits during next session
            if self.current_position and i < len(sessions) - 1:
                next_day_data = next_session['data']
                for idx in range(len(next_day_data)):
                    candle_idx = df[df['timestamp'] == next_day_data.iloc[idx]['timestamp']].index[0]
                    if self.check_stop_loss(df, candle_idx):
                        break
                        
        # Close any remaining position
        if self.current_position and len(sessions) > 0:
            self.close_position_at_market_close(sessions[-1], df)
            
        # Generate report
        self.generate_report()
        
    def generate_report(self):
        """Generate summary report of simulation results"""
        if not self.trades:
            logger.info("No trades executed during simulation")
            return
            
        print("\n" + "="*80)
        print("TRADING SIMULATION RESULTS")
        print("="*80)
        
        # Summary stats
        total_trades = len(self.trades)
        winning_trades = [t for t in self.trades if t['pnl_pct'] > 0]
        losing_trades = [t for t in self.trades if t['pnl_pct'] <= 0]
        
        win_rate = len(winning_trades) / total_trades * 100
        total_pnl = sum(t['pnl_pct'] for t in self.trades)
        avg_pnl = total_pnl / total_trades
        
        print(f"\nTotal Trades: {total_trades}")
        print(f"Winning Trades: {len(winning_trades)} ({win_rate:.1f}%)")
        print(f"Losing Trades: {len(losing_trades)} ({100-win_rate:.1f}%)")
        print(f"Total P&L: {total_pnl:+.2f}%")
        print(f"Average P&L per Trade: {avg_pnl:+.2f}%")
        
        # Strategy breakdown
        print("\nSTRATEGY PERFORMANCE:")
        print("-"*50)
        
        strategies = {}
        for trade in self.trades:
            strategy = trade['strategy']
            if strategy not in strategies:
                strategies[strategy] = {'trades': 0, 'pnl': 0, 'wins': 0}
            strategies[strategy]['trades'] += 1
            strategies[strategy]['pnl'] += trade['pnl_pct']
            if trade['pnl_pct'] > 0:
                strategies[strategy]['wins'] += 1
                
        for strategy, stats in sorted(strategies.items(), key=lambda x: x[1]['pnl'], reverse=True):
            win_rate = stats['wins'] / stats['trades'] * 100
            avg_pnl = stats['pnl'] / stats['trades']
            print(f"{strategy:25s} | Trades: {stats['trades']:3d} | Win Rate: {win_rate:5.1f}% | Total P&L: {stats['pnl']:+7.2f}% | Avg P&L: {avg_pnl:+6.2f}%")
            
        # Detailed trade log
        print("\nDETAILED TRADE LOG:")
        print("-"*120)
        print(f"{'Date':10s} | {'Strategy':20s} | {'Dir':4s} | {'Lev':3s} | {'SL%':4s} | {'Entry':7s} | {'Exit':7s} | {'P&L %':7s} | {'Balance':8s} | {'Reason':20s}")
        print("-"*140)
        
        running_balance = 100.0  # Starting balance
        for trade in self.trades:
            running_balance *= (1 + trade['pnl_pct'] / 100)
            print(f"{trade['date']} | {trade['strategy']:20s} | {trade['direction']:4s} | "
                  f"{trade['leverage']:3.0f}x | {trade['stop_loss_pct']:4.1f}% | "
                  f"${trade['entry_price']:6.2f} | ${trade['exit_price']:6.2f} | "
                  f"{trade['pnl_pct']:+6.2f}% | ${running_balance:7.2f} | {trade['exit_reason']:20s}")
                  
        # Show which signals fired for each trade
        print("\nSIGNALS FIRED PER TRADE:")
        print("-"*80)
        for i, trade in enumerate(self.trades):
            fired = [name for name, value in trade['fired_signals'].items() if value]
            print(f"Trade {i+1} ({trade['date']}): {', '.join(fired) if fired else 'None'}")
            
        print("\n" + "="*80)

if __name__ == "__main__":
    tester = IndicatorTester()
    tester.run_simulation()
