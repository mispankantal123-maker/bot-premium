"""
Performance Tracking System for TradeMaestro
Comprehensive performance analysis and reporting
"""

import json
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np
import threading

# from PySide6.QtCore import QObject, Signal  # Disabled for CLI mode

from .logger import Logger


class PerformanceTracker:
    """
    Comprehensive performance tracking and analysis system
    Tracks trades, calculates metrics, and provides performance reports
    """
    
    # Signals for performance updates (disabled for CLI mode)
    # performance_updated = Signal(dict)  # performance_metrics
    # trade_recorded = Signal(dict)  # trade_data
    # daily_summary_ready = Signal(dict)  # daily_summary
    # milestone_reached = Signal(str, float)  # milestone_type, value
    
    def __init__(self, config=None):
        # super().__init__()  # Disabled for CLI mode
        self.config = config
        self.logger = Logger(__name__)
        
        # Data storage
        if config:
            self.data_dir = config.DATA_DIR
            self.history_dir = config.HISTORY_DIR
        else:
            self.data_dir = Path("data")
            self.history_dir = Path("data/history")
        
        # Ensure directories exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.history_dir.mkdir(parents=True, exist_ok=True)
        
        # Performance data
        self.trade_history = []
        self.daily_stats = {}
        self.session_stats = {}
        self.monthly_stats = {}
        
        # Real-time tracking
        self.session_start_time = datetime.now()
        self.session_start_balance = 0.0
        self.current_balance = 0.0
        self.current_equity = 0.0
        
        # Performance metrics
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_profit = 0.0
        self.max_profit = 0.0
        self.max_loss = 0.0
        self.max_drawdown = 0.0
        self.max_equity = 0.0
        
        # Risk metrics
        self.profit_factor = 0.0
        self.sharpe_ratio = 0.0
        self.win_rate = 0.0
        self.avg_win = 0.0
        self.avg_loss = 0.0
        self.largest_win = 0.0
        self.largest_loss = 0.0
        
        # Threading
        self._data_lock = threading.Lock()
        
        # Load existing data
        self.load_session_data()
    
    def record_trade(self, trade_data: Dict[str, Any]):
        """
        Record a completed trade
        
        Args:
            trade_data: Dictionary containing trade information
        """
        try:
            with self._data_lock:
                # Validate trade data
                required_fields = ['symbol', 'type', 'volume', 'open_price', 'close_price', 'profit']
                if not all(field in trade_data for field in required_fields):
                    self.logger.error("Invalid trade data: missing required fields")
                    return
                
                # Add timestamp if not present
                if 'timestamp' not in trade_data:
                    trade_data['timestamp'] = datetime.now()
                
                if 'close_time' not in trade_data:
                    trade_data['close_time'] = datetime.now()
                
                # Calculate additional metrics
                trade_data = self._calculate_trade_metrics(trade_data)
                
                # Add to trade history
                self.trade_history.append(trade_data)
                
                # Update counters
                self.total_trades += 1
                profit = trade_data['profit']
                
                if profit > 0:
                    self.winning_trades += 1
                    if profit > self.largest_win:
                        self.largest_win = profit
                else:
                    self.losing_trades += 1
                    if profit < self.largest_loss:
                        self.largest_loss = profit
                
                # Update profit tracking
                self.total_profit += profit
                if profit > self.max_profit:
                    self.max_profit = profit
                if profit < self.max_loss:
                    self.max_loss = profit
                
                # Update daily stats
                self._update_daily_stats(trade_data)
                
                # Recalculate performance metrics
                self._calculate_performance_metrics()
                
                # Check for milestones
                self._check_milestones()
                
                # Emit signals
                self.trade_recorded.emit(trade_data)
                self.performance_updated.emit(self.get_performance_summary())
                
                # Auto-save
                self._auto_save()
                
                self.logger.info(f"📊 Trade recorded: {trade_data['symbol']} {trade_data['type']} "
                               f"Profit: {profit:.2f}")
                
        except Exception as e:
            self.logger.error(f"Error recording trade: {str(e)}")
    
    def update_account_info(self, account_info: Dict[str, Any]):
        """
        Update account information for performance tracking
        
        Args:
            account_info: Account information from MT5
        """
        try:
            with self._data_lock:
                if 'balance' in account_info:
                    self.current_balance = account_info['balance']
                
                if 'equity' in account_info:
                    self.current_equity = account_info['equity']
                    
                    # Track maximum equity
                    if self.current_equity > self.max_equity:
                        self.max_equity = self.current_equity
                    
                    # Calculate drawdown
                    if self.max_equity > 0:
                        current_drawdown = (self.max_equity - self.current_equity) / self.max_equity
                        if current_drawdown > self.max_drawdown:
                            self.max_drawdown = current_drawdown
                
                # Set session start balance if not set
                if self.session_start_balance == 0.0 and 'balance' in account_info:
                    self.session_start_balance = account_info['balance']
                
                # Update session stats
                self._update_session_stats()
                
        except Exception as e:
            self.logger.error(f"Error updating account info: {str(e)}")
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """
        Get comprehensive performance summary
        
        Returns:
            Dictionary with performance metrics
        """
        try:
            session_duration = datetime.now() - self.session_start_time
            
            return {
                # Basic stats
                'total_trades': self.total_trades,
                'winning_trades': self.winning_trades,
                'losing_trades': self.losing_trades,
                'win_rate': self.win_rate,
                
                # Profit metrics
                'total_profit': self.total_profit,
                'avg_win': self.avg_win,
                'avg_loss': self.avg_loss,
                'largest_win': self.largest_win,
                'largest_loss': self.largest_loss,
                'profit_factor': self.profit_factor,
                
                # Risk metrics
                'max_drawdown': self.max_drawdown,
                'sharpe_ratio': self.sharpe_ratio,
                
                # Account info
                'session_start_balance': self.session_start_balance,
                'current_balance': self.current_balance,
                'current_equity': self.current_equity,
                'max_equity': self.max_equity,
                
                # Session info
                'session_duration': str(session_duration),
                'session_profit': self.current_balance - self.session_start_balance if self.session_start_balance > 0 else 0,
                'session_return_pct': self._calculate_session_return(),
                
                # Timestamps
                'session_start': self.session_start_time.isoformat(),
                'last_update': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Error getting performance summary: {str(e)}")
            return {}
    
    def get_daily_summary(self, date: datetime = None) -> Dict[str, Any]:
        """
        Get daily performance summary
        
        Args:
            date: Date for summary (today if None)
            
        Returns:
            Dictionary with daily summary
        """
        try:
            if date is None:
                date = datetime.now().date()
            
            date_str = date.strftime('%Y-%m-%d')
            
            if date_str in self.daily_stats:
                daily_data = self.daily_stats[date_str]
                
                summary = {
                    'date': date_str,
                    'trades': daily_data.get('trades', 0),
                    'winning_trades': daily_data.get('winning_trades', 0),
                    'losing_trades': daily_data.get('losing_trades', 0),
                    'win_rate': daily_data.get('win_rate', 0.0),
                    'total_profit': daily_data.get('total_profit', 0.0),
                    'largest_win': daily_data.get('largest_win', 0.0),
                    'largest_loss': daily_data.get('largest_loss', 0.0),
                    'avg_profit_per_trade': daily_data.get('avg_profit_per_trade', 0.0),
                    'symbols_traded': daily_data.get('symbols_traded', []),
                    'trading_hours': daily_data.get('trading_hours', 0.0)
                }
                
                return summary
            
            return {'date': date_str, 'trades': 0}
            
        except Exception as e:
            self.logger.error(f"Error getting daily summary: {str(e)}")
            return {}
    
    def get_monthly_summary(self, year: int = None, month: int = None) -> Dict[str, Any]:
        """
        Get monthly performance summary
        
        Args:
            year: Year for summary (current if None)
            month: Month for summary (current if None)
            
        Returns:
            Dictionary with monthly summary
        """
        try:
            now = datetime.now()
            if year is None:
                year = now.year
            if month is None:
                month = now.month
            
            month_key = f"{year}-{month:02d}"
            
            # Calculate monthly stats from daily data
            monthly_trades = 0
            monthly_profit = 0.0
            monthly_winners = 0
            monthly_losers = 0
            symbols_traded = set()
            
            for date_str, daily_data in self.daily_stats.items():
                if date_str.startswith(month_key):
                    monthly_trades += daily_data.get('trades', 0)
                    monthly_profit += daily_data.get('total_profit', 0.0)
                    monthly_winners += daily_data.get('winning_trades', 0)
                    monthly_losers += daily_data.get('losing_trades', 0)
                    symbols_traded.update(daily_data.get('symbols_traded', []))
            
            win_rate = (monthly_winners / monthly_trades * 100) if monthly_trades > 0 else 0
            
            return {
                'year': year,
                'month': month,
                'trades': monthly_trades,
                'winning_trades': monthly_winners,
                'losing_trades': monthly_losers,
                'win_rate': win_rate,
                'total_profit': monthly_profit,
                'avg_profit_per_trade': monthly_profit / monthly_trades if monthly_trades > 0 else 0,
                'symbols_traded': list(symbols_traded),
                'trading_days': len([d for d in self.daily_stats.keys() if d.startswith(month_key)])
            }
            
        except Exception as e:
            self.logger.error(f"Error getting monthly summary: {str(e)}")
            return {}
    
    def get_trade_history_df(self, days: int = None) -> pd.DataFrame:
        """
        Get trade history as pandas DataFrame
        
        Args:
            days: Number of recent days to include (None for all)
            
        Returns:
            DataFrame with trade history
        """
        try:
            if not self.trade_history:
                return pd.DataFrame()
            
            df = pd.DataFrame(self.trade_history)
            
            # Convert timestamps
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df.set_index('timestamp', inplace=True)
            
            # Filter by days if specified
            if days is not None:
                cutoff_date = datetime.now() - timedelta(days=days)
                df = df[df.index >= cutoff_date]
            
            return df
            
        except Exception as e:
            self.logger.error(f"Error creating trade history DataFrame: {str(e)}")
            return pd.DataFrame()
    
    def calculate_strategy_performance(self, strategy_name: str) -> Dict[str, Any]:
        """
        Calculate performance metrics for a specific strategy
        
        Args:
            strategy_name: Name of the strategy
            
        Returns:
            Dictionary with strategy performance
        """
        try:
            strategy_trades = [t for t in self.trade_history 
                             if t.get('strategy') == strategy_name]
            
            if not strategy_trades:
                return {'strategy': strategy_name, 'trades': 0}
            
            total_trades = len(strategy_trades)
            winning_trades = sum(1 for t in strategy_trades if t['profit'] > 0)
            total_profit = sum(t['profit'] for t in strategy_trades)
            
            wins = [t['profit'] for t in strategy_trades if t['profit'] > 0]
            losses = [t['profit'] for t in strategy_trades if t['profit'] < 0]
            
            return {
                'strategy': strategy_name,
                'trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': total_trades - winning_trades,
                'win_rate': (winning_trades / total_trades * 100) if total_trades > 0 else 0,
                'total_profit': total_profit,
                'avg_win': np.mean(wins) if wins else 0,
                'avg_loss': np.mean(losses) if losses else 0,
                'largest_win': max(wins) if wins else 0,
                'largest_loss': min(losses) if losses else 0,
                'profit_factor': sum(wins) / abs(sum(losses)) if losses else float('inf')
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating strategy performance: {str(e)}")
            return {}
    
    def export_performance_report(self, filepath: str = None) -> str:
        """
        Export comprehensive performance report
        
        Args:
            filepath: Output file path (auto-generated if None)
            
        Returns:
            Path to exported file
        """
        try:
            if filepath is None:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filepath = self.history_dir / f"performance_report_{timestamp}.json"
            
            report = {
                'report_generated': datetime.now().isoformat(),
                'session_info': {
                    'start_time': self.session_start_time.isoformat(),
                    'start_balance': self.session_start_balance,
                    'current_balance': self.current_balance,
                    'current_equity': self.current_equity
                },
                'performance_summary': self.get_performance_summary(),
                'daily_stats': self.daily_stats,
                'trade_history': [
                    {k: (v.isoformat() if isinstance(v, datetime) else v) 
                     for k, v in trade.items()}
                    for trade in self.trade_history[-100:]  # Last 100 trades
                ],
                'monthly_summaries': [
                    self.get_monthly_summary(year, month)
                    for year in range(datetime.now().year - 1, datetime.now().year + 1)
                    for month in range(1, 13)
                ],
            }
            
            with open(filepath, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            
            self.logger.info(f"📄 Performance report exported to {filepath}")
            return str(filepath)
            
        except Exception as e:
            self.logger.error(f"Error exporting performance report: {str(e)}")
            return ""
    
    def save_session_data(self):
        """Save current session data"""
        try:
            session_file = self.data_dir / "session_data.pkl"
            
            session_data = {
                'trade_history': self.trade_history,
                'daily_stats': self.daily_stats,
                'session_stats': self.session_stats,
                'session_start_time': self.session_start_time,
                'session_start_balance': self.session_start_balance,
                'performance_metrics': {
                    'total_trades': self.total_trades,
                    'winning_trades': self.winning_trades,
                    'losing_trades': self.losing_trades,
                    'total_profit': self.total_profit,
                    'max_drawdown': self.max_drawdown,
                    'max_equity': self.max_equity
                }
            }
            
            with open(session_file, 'wb') as f:
                pickle.dump(session_data, f)
            
            self.logger.debug("💾 Session data saved")
            
        except Exception as e:
            self.logger.error(f"Error saving session data: {str(e)}")
    
    def load_session_data(self):
        """Load previous session data"""
        try:
            session_file = self.data_dir / "session_data.pkl"
            
            if not session_file.exists():
                self.logger.info("No previous session data found")
                return
            
            with open(session_file, 'rb') as f:
                session_data = pickle.load(f)
            
            # Restore data
            self.trade_history = session_data.get('trade_history', [])
            self.daily_stats = session_data.get('daily_stats', {})
            self.session_stats = session_data.get('session_stats', {})
            
            # Restore metrics
            metrics = session_data.get('performance_metrics', {})
            self.total_trades = metrics.get('total_trades', 0)
            self.winning_trades = metrics.get('winning_trades', 0)
            self.losing_trades = metrics.get('losing_trades', 0)
            self.total_profit = metrics.get('total_profit', 0.0)
            self.max_drawdown = metrics.get('max_drawdown', 0.0)
            self.max_equity = metrics.get('max_equity', 0.0)
            
            # Recalculate performance metrics
            self._calculate_performance_metrics()
            
            self.logger.info(f"📂 Loaded session data: {self.total_trades} trades")
            
        except Exception as e:
            self.logger.error(f"Error loading session data: {str(e)}")
    
    def _calculate_trade_metrics(self, trade_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate additional metrics for a trade"""
        try:
            # Calculate pips (simplified for major pairs)
            if 'pips' not in trade_data:
                open_price = trade_data['open_price']
                close_price = trade_data['close_price']
                symbol = trade_data['symbol']
                
                # Simplified pip calculation
                if 'JPY' in symbol:
                    pip_diff = abs(close_price - open_price) * 100
                else:
                    pip_diff = abs(close_price - open_price) * 10000
                
                if trade_data['type'].upper() == 'BUY':
                    trade_data['pips'] = pip_diff if close_price > open_price else -pip_diff
                else:
                    trade_data['pips'] = pip_diff if close_price < open_price else -pip_diff
            
            # Calculate duration
            if 'duration_minutes' not in trade_data:
                if 'open_time' in trade_data and 'close_time' in trade_data:
                    open_time = trade_data['open_time']
                    close_time = trade_data['close_time']
                    
                    if isinstance(open_time, str):
                        open_time = datetime.fromisoformat(open_time)
                    if isinstance(close_time, str):
                        close_time = datetime.fromisoformat(close_time)
                    
                    duration = close_time - open_time
                    trade_data['duration_minutes'] = duration.total_seconds() / 60
            
            # Add trade result
            trade_data['result'] = 'WIN' if trade_data['profit'] > 0 else 'LOSS' if trade_data['profit'] < 0 else 'BREAKEVEN'
            
            return trade_data
            
        except Exception as e:
            self.logger.error(f"Error calculating trade metrics: {str(e)}")
            return trade_data
    
    def _update_daily_stats(self, trade_data: Dict[str, Any]):
        """Update daily statistics"""
        try:
            trade_date = trade_data.get('close_time', datetime.now())
            if isinstance(trade_date, str):
                trade_date = datetime.fromisoformat(trade_date)
            
            date_str = trade_date.strftime('%Y-%m-%d')
            
            if date_str not in self.daily_stats:
                self.daily_stats[date_str] = {
                    'trades': 0,
                    'winning_trades': 0,
                    'losing_trades': 0,
                    'total_profit': 0.0,
                    'largest_win': 0.0,
                    'largest_loss': 0.0,
                    'symbols_traded': set(),
                    'first_trade_time': None,
                    'last_trade_time': None
                }
            
            daily = self.daily_stats[date_str]
            profit = trade_data['profit']
            
            # Update stats
            daily['trades'] += 1
            daily['total_profit'] += profit
            daily['symbols_traded'].add(trade_data['symbol'])
            
            if profit > 0:
                daily['winning_trades'] += 1
                if profit > daily['largest_win']:
                    daily['largest_win'] = profit
            else:
                daily['losing_trades'] += 1
                if profit < daily['largest_loss']:
                    daily['largest_loss'] = profit
            
            # Update time tracking
            trade_time = trade_data.get('close_time', datetime.now())
            if daily['first_trade_time'] is None:
                daily['first_trade_time'] = trade_time
            daily['last_trade_time'] = trade_time
            
            # Calculate derived metrics
            daily['win_rate'] = (daily['winning_trades'] / daily['trades'] * 100) if daily['trades'] > 0 else 0
            daily['avg_profit_per_trade'] = daily['total_profit'] / daily['trades'] if daily['trades'] > 0 else 0
            
            # Convert set to list for JSON serialization
            daily['symbols_traded'] = list(daily['symbols_traded'])
            
        except Exception as e:
            self.logger.error(f"Error updating daily stats: {str(e)}")
    
    def _update_session_stats(self):
        """Update session statistics"""
        try:
            session_duration = datetime.now() - self.session_start_time
            
            self.session_stats.update({
                'duration_hours': session_duration.total_seconds() / 3600,
                'current_balance': self.current_balance,
                'current_equity': self.current_equity,
                'session_profit': self.current_balance - self.session_start_balance if self.session_start_balance > 0 else 0,
                'session_return': self._calculate_session_return(),
                'max_equity': self.max_equity,
                'max_drawdown': self.max_drawdown,
                'last_update': datetime.now().isoformat()
            })
            
        except Exception as e:
            self.logger.error(f"Error updating session stats: {str(e)}")
    
    def _calculate_performance_metrics(self):
        """Calculate overall performance metrics"""
        try:
            if self.total_trades == 0:
                return
            
            # Win rate
            self.win_rate = (self.winning_trades / self.total_trades) * 100
            
            # Average win/loss
            wins = [t['profit'] for t in self.trade_history if t['profit'] > 0]
            losses = [t['profit'] for t in self.trade_history if t['profit'] < 0]
            
            self.avg_win = np.mean(wins) if wins else 0
            self.avg_loss = np.mean(losses) if losses else 0
            
            # Profit factor
            total_wins = sum(wins) if wins else 0
            total_losses = abs(sum(losses)) if losses else 0
            self.profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')
            
            # Sharpe ratio (simplified)
            if self.trade_history:
                returns = [t['profit'] for t in self.trade_history]
                if len(returns) > 1:
                    mean_return = np.mean(returns)
                    std_return = np.std(returns)
                    self.sharpe_ratio = mean_return / std_return if std_return > 0 else 0
            
        except Exception as e:
            self.logger.error(f"Error calculating performance metrics: {str(e)}")
    
    def _calculate_session_return(self) -> float:
        """Calculate session return percentage"""
        try:
            if self.session_start_balance <= 0:
                return 0.0
            
            return ((self.current_balance - self.session_start_balance) / self.session_start_balance) * 100
            
        except Exception:
            return 0.0
    
    def _check_milestones(self):
        """Check for performance milestones"""
        try:
            # Check trade count milestones
            milestone_trades = [10, 50, 100, 500, 1000]
            for milestone in milestone_trades:
                if self.total_trades == milestone:
                    self.milestone_reached.emit(f"{milestone} trades", milestone)
            
            # Check profit milestones
            if self.session_start_balance > 0:
                profit_pct = self._calculate_session_return()
                milestone_profits = [5, 10, 25, 50, 100]
                for milestone in milestone_profits:
                    if profit_pct >= milestone and f"profit_{milestone}" not in getattr(self, '_milestones_hit', set()):
                        if not hasattr(self, '_milestones_hit'):
                            self._milestones_hit = set()
                        self._milestones_hit.add(f"profit_{milestone}")
                        self.milestone_reached.emit(f"{milestone}% profit", profit_pct)
            
        except Exception as e:
            self.logger.error(f"Error checking milestones: {str(e)}")
    
    def _auto_save(self):
        """Auto-save session data periodically"""
        try:
            # Save every 10 trades
            if self.total_trades % 10 == 0:
                self.save_session_data()
        except Exception as e:
            self.logger.error(f"Auto-save error: {str(e)}")
