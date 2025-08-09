"""
Market Data Fetcher for TradeMaestro
Handles fetching, caching, and processing of market data from MT5
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
import threading
import time
from pathlib import Path
import pickle

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

# from PySide6.QtCore import QObject, Signal  # Disabled for CLI mode

from .logger import Logger


class DataFetcher:
    """
    Market data fetcher with caching and real-time updates
    Provides historical and live market data for trading strategies
    """
    
    # Signals for data updates (disabled for CLI mode)
    # data_updated = Signal(str, pd.DataFrame)  # symbol, data
    # tick_updated = Signal(str, dict)  # symbol, tick_data
    # error_occurred = Signal(str)
    
    def __init__(self, mt5_connector, config=None):
        # super().__init__()  # Disabled for CLI mode
        self.mt5_connector = mt5_connector
        self.config = config
        self.logger = Logger(__name__)
        
        # Data cache
        self._data_cache = {}
        self._cache_lock = threading.Lock()
        self._cache_expiry = {}
        self.default_cache_duration = 60  # seconds
        
        # Real-time data
        self._subscribed_symbols = set()
        self._real_time_thread = None
        self._real_time_running = False
        
        # Data storage
        if config:
            self.cache_dir = config.CACHE_DIR
            self.history_dir = config.HISTORY_DIR
        else:
            self.cache_dir = Path("data/cache")
            self.history_dir = Path("data/history")
        
        # Ensure directories exist
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.history_dir.mkdir(parents=True, exist_ok=True)
        
        # Timeframe mapping
        self.timeframe_map = {
            'M1': mt5.TIMEFRAME_M1,
            'M5': mt5.TIMEFRAME_M5,
            'M15': mt5.TIMEFRAME_M15,
            'M30': mt5.TIMEFRAME_M30,
            'H1': mt5.TIMEFRAME_H1,
            'H4': mt5.TIMEFRAME_H4,
            'D1': mt5.TIMEFRAME_D1,
            'W1': mt5.TIMEFRAME_W1,
            'MN1': mt5.TIMEFRAME_MN1
        }
    
    def get_historical_data(self, symbol: str, timeframe: str, count: int = 100, 
                          from_date: datetime = None, to_date: datetime = None) -> Optional[pd.DataFrame]:
        """
        Get historical market data for a symbol
        
        Args:
            symbol: Trading symbol (e.g., 'EURUSD')
            timeframe: Data timeframe ('M1', 'M5', 'H1', etc.)
            count: Number of bars to fetch
            from_date: Start date (optional)
            to_date: End date (optional)
            
        Returns:
            DataFrame with OHLCV data or None if error
        """
        try:
            # Check cache first
            cache_key = f"{symbol}_{timeframe}_{count}"
            if from_date:
                cache_key += f"_{from_date.strftime('%Y%m%d')}"
            if to_date:
                cache_key += f"_{to_date.strftime('%Y%m%d')}"
            
            cached_data = self._get_cached_data(cache_key)
            if cached_data is not None:
                self.logger.debug(f"📋 Using cached data for {symbol} {timeframe}")
                return cached_data
            
            # Check if MT5 is connected
            if not self.mt5_connector.is_connected():
                self.logger.error("MT5 not connected")
                return None
            
            # Get timeframe constant
            if timeframe not in self.timeframe_map:
                self.logger.error(f"Invalid timeframe: {timeframe}")
                return None
            
            mt5_timeframe = self.timeframe_map[timeframe]
            
            # Fetch data from MT5
            self.logger.debug(f"📊 Fetching {count} bars of {symbol} {timeframe} from MT5")
            
            if from_date and to_date:
                # Fetch data between dates
                rates = mt5.copy_rates_range(symbol, mt5_timeframe, from_date, to_date)
            elif from_date:
                # Fetch data from specific date
                rates = mt5.copy_rates_from(symbol, mt5_timeframe, from_date, count)
            else:
                # Fetch most recent data
                rates = mt5.copy_rates_from_pos(symbol, mt5_timeframe, 0, count)
            
            if rates is None or len(rates) == 0:
                self.logger.warning(f"No data received for {symbol} {timeframe}")
                return None
            
            # Convert to DataFrame
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df.set_index('time', inplace=True)
            
            # Rename columns for consistency
            df.rename(columns={
                'open': 'open',
                'high': 'high', 
                'low': 'low',
                'close': 'close',
                'tick_volume': 'volume'
            }, inplace=True)
            
            # Add symbol information
            df['symbol'] = symbol
            
            # Validate data
            if not self._validate_data(df):
                self.logger.error(f"Invalid data received for {symbol} {timeframe}")
                return None
            
            # Cache the data
            self._cache_data(cache_key, df)
            
            # Save to history if configured
            if self.config and getattr(self.config, 'SAVE_TRADE_HISTORY', False):
                self._save_historical_data(symbol, timeframe, df)
            
            # Emit signal
            self.data_updated.emit(symbol, df)
            
            self.logger.debug(f"✅ Fetched {len(df)} bars for {symbol} {timeframe}")
            return df
            
        except Exception as e:
            error_msg = f"Error fetching data for {symbol} {timeframe}: {str(e)}"
            self.logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return None
    
    def get_tick_data(self, symbol: str, count: int = 100) -> Optional[pd.DataFrame]:
        """
        Get tick data for a symbol
        
        Args:
            symbol: Trading symbol
            count: Number of ticks to fetch
            
        Returns:
            DataFrame with tick data or None if error
        """
        try:
            if not self.mt5_connector.is_connected():
                self.logger.error("MT5 not connected")
                return None
            
            # Get ticks from MT5
            from_date = datetime.now() - timedelta(hours=1)  # Last hour
            ticks = mt5.copy_ticks_from(symbol, from_date, count, mt5.COPY_TICKS_ALL)
            
            if ticks is None or len(ticks) == 0:
                self.logger.warning(f"No tick data received for {symbol}")
                return None
            
            # Convert to DataFrame
            df = pd.DataFrame(ticks)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df.set_index('time', inplace=True)
            
            return df
            
        except Exception as e:
            error_msg = f"Error fetching tick data for {symbol}: {str(e)}"
            self.logger.error(error_msg)
            return None
    
    def get_current_price(self, symbol: str) -> Optional[Dict[str, float]]:
        """
        Get current bid/ask prices for a symbol
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Dict with current prices or None if error
        """
        try:
            tick_data = self.mt5_connector.get_symbol_tick(symbol)
            if tick_data:
                return {
                    'bid': tick_data['bid'],
                    'ask': tick_data['ask'],
                    'last': tick_data.get('last', tick_data['ask']),
                    'spread': tick_data['spread'],
                    'time': tick_data['time']
                }
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error getting current price for {symbol}: {str(e)}")
            return None
    
    def subscribe_real_time(self, symbols: List[str]):
        """
        Subscribe to real-time tick updates for symbols
        
        Args:
            symbols: List of symbols to subscribe to
        """
        try:
            for symbol in symbols:
                self._subscribed_symbols.add(symbol)
            
            # Start real-time thread if not running
            if not self._real_time_running:
                self._start_real_time_updates()
            
            self.logger.info(f"📡 Subscribed to real-time updates for: {', '.join(symbols)}")
            
        except Exception as e:
            self.logger.error(f"Error subscribing to real-time data: {str(e)}")
    
    def unsubscribe_real_time(self, symbols: List[str] = None):
        """
        Unsubscribe from real-time updates
        
        Args:
            symbols: List of symbols to unsubscribe from (None for all)
        """
        try:
            if symbols is None:
                self._subscribed_symbols.clear()
            else:
                for symbol in symbols:
                    self._subscribed_symbols.discard(symbol)
            
            # Stop real-time thread if no subscriptions
            if len(self._subscribed_symbols) == 0:
                self._stop_real_time_updates()
            
            self.logger.info("📡 Unsubscribed from real-time updates")
            
        except Exception as e:
            self.logger.error(f"Error unsubscribing from real-time data: {str(e)}")
    
    def calculate_indicators(self, data: pd.DataFrame, indicators: List[str]) -> pd.DataFrame:
        """
        Calculate technical indicators for the data
        
        Args:
            data: OHLCV DataFrame
            indicators: List of indicator names to calculate
            
        Returns:
            DataFrame with additional indicator columns
        """
        try:
            df = data.copy()
            
            for indicator in indicators:
                if indicator.upper() == 'SMA_20':
                    df['sma_20'] = df['close'].rolling(window=20).mean()
                    
                elif indicator.upper() == 'SMA_50':
                    df['sma_50'] = df['close'].rolling(window=50).mean()
                    
                elif indicator.upper() == 'EMA_12':
                    df['ema_12'] = df['close'].ewm(span=12).mean()
                    
                elif indicator.upper() == 'EMA_26':
                    df['ema_26'] = df['close'].ewm(span=26).mean()
                    
                elif indicator.upper() == 'RSI_14':
                    df['rsi_14'] = self._calculate_rsi(df['close'], 14)
                    
                elif indicator.upper() == 'MACD':
                    ema_12 = df['close'].ewm(span=12).mean()
                    ema_26 = df['close'].ewm(span=26).mean()
                    df['macd'] = ema_12 - ema_26
                    df['macd_signal'] = df['macd'].ewm(span=9).mean()
                    df['macd_histogram'] = df['macd'] - df['macd_signal']
                    
                elif indicator.upper() == 'BOLLINGER_BANDS':
                    sma_20 = df['close'].rolling(window=20).mean()
                    std_20 = df['close'].rolling(window=20).std()
                    df['bb_upper'] = sma_20 + (std_20 * 2)
                    df['bb_middle'] = sma_20
                    df['bb_lower'] = sma_20 - (std_20 * 2)
                    
                elif indicator.upper() == 'ATR_14':
                    df['atr_14'] = self._calculate_atr(df, 14)
            
            return df
            
        except Exception as e:
            self.logger.error(f"Error calculating indicators: {str(e)}")
            return data
    
    def get_symbol_list(self, group: str = None) -> List[str]:
        """
        Get list of available symbols
        
        Args:
            group: Symbol group filter (e.g., 'Forex', 'Stocks')
            
        Returns:
            List of symbol names
        """
        try:
            if not self.mt5_connector.is_connected():
                return []
            
            symbols = mt5.symbols_get(group=group)
            if symbols is None:
                return []
            
            return [symbol.name for symbol in symbols if symbol.visible]
            
        except Exception as e:
            self.logger.error(f"Error getting symbol list: {str(e)}")
            return []
    
    def get_market_hours(self, symbol: str) -> Dict[str, Any]:
        """
        Get market hours information for a symbol
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Dict with market hours info
        """
        try:
            symbol_info = self.mt5_connector.get_symbol_info(symbol)
            if not symbol_info:
                return {}
            
            # This is a simplified version - real implementation would need
            # more detailed market hours data
            return {
                'symbol': symbol,
                'trade_mode': symbol_info.get('trade_mode'),
                'trade_allowed': symbol_info.get('trade_allowed'),
                'sessions_quotes': 'Session info not available',
                'sessions_trades': 'Session info not available'
            }
            
        except Exception as e:
            self.logger.error(f"Error getting market hours for {symbol}: {str(e)}")
            return {}
    
    def _get_cached_data(self, cache_key: str) -> Optional[pd.DataFrame]:
        """Get data from cache if still valid"""
        with self._cache_lock:
            if cache_key in self._data_cache:
                # Check if cache is still valid
                cache_time = self._cache_expiry.get(cache_key)
                if cache_time and datetime.now() < cache_time:
                    return self._data_cache[cache_key].copy()
                else:
                    # Remove expired cache
                    del self._data_cache[cache_key]
                    if cache_key in self._cache_expiry:
                        del self._cache_expiry[cache_key]
        
        return None
    
    def _cache_data(self, cache_key: str, data: pd.DataFrame):
        """Cache data with expiry time"""
        with self._cache_lock:
            self._data_cache[cache_key] = data.copy()
            self._cache_expiry[cache_key] = datetime.now() + timedelta(seconds=self.default_cache_duration)
            
            # Limit cache size
            max_cache_size = 100
            if len(self._data_cache) > max_cache_size:
                # Remove oldest entries
                oldest_keys = sorted(self._cache_expiry.keys(), 
                                   key=lambda k: self._cache_expiry[k])[:10]
                for key in oldest_keys:
                    self._data_cache.pop(key, None)
                    self._cache_expiry.pop(key, None)
    
    def _validate_data(self, data: pd.DataFrame) -> bool:
        """Validate that data is properly formatted"""
        try:
            required_columns = ['open', 'high', 'low', 'close', 'volume']
            
            # Check required columns
            if not all(col in data.columns for col in required_columns):
                return False
            
            # Check for NaN values in OHLC
            if data[['open', 'high', 'low', 'close']].isna().any().any():
                return False
            
            # Check data integrity (high >= low, etc.)
            if (data['high'] < data['low']).any():
                return False
            
            if (data['high'] < data['open']).any() or (data['high'] < data['close']).any():
                return False
            
            if (data['low'] > data['open']).any() or (data['low'] > data['close']).any():
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Data validation error: {str(e)}")
            return False
    
    def _save_historical_data(self, symbol: str, timeframe: str, data: pd.DataFrame):
        """Save historical data to file"""
        try:
            filename = f"{symbol}_{timeframe}_{datetime.now().strftime('%Y%m%d')}.pkl"
            filepath = self.history_dir / filename
            
            with open(filepath, 'wb') as f:
                pickle.dump(data, f)
                
            self.logger.debug(f"💾 Saved historical data to {filepath}")
            
        except Exception as e:
            self.logger.error(f"Error saving historical data: {str(e)}")
    
    def _start_real_time_updates(self):
        """Start real-time data update thread"""
        if self._real_time_running:
            return
        
        self._real_time_running = True
        self._real_time_thread = threading.Thread(target=self._real_time_worker, daemon=True)
        self._real_time_thread.start()
        self.logger.info("📡 Started real-time data updates")
    
    def _stop_real_time_updates(self):
        """Stop real-time data updates"""
        self._real_time_running = False
        if self._real_time_thread and self._real_time_thread.is_alive():
            self._real_time_thread.join(timeout=2.0)
        self.logger.info("📡 Stopped real-time data updates")
    
    def _real_time_worker(self):
        """Worker thread for real-time data updates"""
        while self._real_time_running:
            try:
                for symbol in list(self._subscribed_symbols):
                    tick_data = self.mt5_connector.get_symbol_tick(symbol)
                    if tick_data:
                        self.tick_updated.emit(symbol, tick_data)
                
                time.sleep(1)  # Update every second
                
            except Exception as e:
                self.logger.error(f"Real-time update error: {str(e)}")
                time.sleep(5)
    
    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI indicator"""
        try:
            delta = prices.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            return rsi
            
        except Exception:
            return pd.Series([50] * len(prices), index=prices.index)
    
    def _calculate_atr(self, data: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average True Range"""
        try:
            high = data['high']
            low = data['low']
            close = data['close']
            
            tr1 = high - low
            tr2 = abs(high - close.shift())
            tr3 = abs(low - close.shift())
            
            true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = true_range.rolling(window=period).mean()
            
            return atr
            
        except Exception:
            return pd.Series([0.001] * len(data), index=data.index)
    
    def clear_cache(self):
        """Clear all cached data"""
        with self._cache_lock:
            self._data_cache.clear()
            self._cache_expiry.clear()
        self.logger.info("🧹 Cleared data cache")
    
    def get_cache_info(self) -> Dict[str, Any]:
        """Get information about current cache state"""
        with self._cache_lock:
            return {
                'cached_items': len(self._data_cache),
                'cache_keys': list(self._data_cache.keys()),
                'total_memory_mb': sum(df.memory_usage(deep=True).sum() 
                                     for df in self._data_cache.values()) / 1024 / 1024
            }
