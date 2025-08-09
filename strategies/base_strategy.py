"""
Base Strategy Class for TradeMaestro
Provides common functionality for all trading strategies
"""

from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

class SignalType(Enum):
    """Trading signal types"""
    BUY = "BUY"
    SELL = "SELL" 
    HOLD = "HOLD"
    CLOSE_BUY = "CLOSE_BUY"
    CLOSE_SELL = "CLOSE_SELL"


@dataclass
class StrategyResult:
    """Result of strategy analysis"""
    signal: SignalType
    confidence: float  # 0.0 to 1.0
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    lot_size: Optional[float] = None
    reason: str = ""
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies
    Provides common functionality and enforces strategy interface
    """
    
    def __init__(self, mt5_connector, performance_tracker, config):
        self.mt5_connector = mt5_connector
        self.performance_tracker = performance_tracker
        self.config = config
        self.name = self.__class__.__name__
        
        # Strategy parameters
        self.symbols = config.DEFAULT_SYMBOLS
        self.timeframe = getattr(config, 'STRATEGY_TIMEFRAME', 'M1')
        self.lookback_periods = getattr(config, 'ANALYSIS_LOOKBACK', 100)
        
        # Risk management
        self.max_risk_per_trade = config.MAX_RISK_PER_TRADE
        self.default_lot_size = config.DEFAULT_LOT_SIZE
        self.default_stop_loss = config.DEFAULT_STOP_LOSS
        self.default_take_profit = config.DEFAULT_TAKE_PROFIT
        
        # Strategy state
        self.last_analysis_time = None
        self.current_positions = {}
        
        # Initialize strategy-specific parameters
        self.initialize_parameters()
    
    @abstractmethod
    def initialize_parameters(self):
        """Initialize strategy-specific parameters"""
        pass
    
    @abstractmethod
    def analyze_market(self, symbol: str, data: pd.DataFrame) -> StrategyResult:
        """
        Analyze market data and generate trading signals
        
        Args:
            symbol: Trading symbol (e.g., 'EURUSD')
            data: Historical price data
            
        Returns:
            StrategyResult containing signal and trade parameters
        """
        pass
    
    def execute(self) -> List[StrategyResult]:
        """
        Execute strategy for all configured symbols
        
        Returns:
            List of StrategyResult for each symbol
        """
        results = []
        
        try:
            for symbol in self.symbols:
                # Get market data
                data = self.get_market_data(symbol)
                
                if data is not None and len(data) >= self.lookback_periods:
                    # Analyze market
                    result = self.analyze_market(symbol, data)
                    
                    if result:
                        result.metadata['symbol'] = symbol
                        result.metadata['timestamp'] = datetime.now()
                        results.append(result)
                        
                        # Execute trade if signal is actionable
                        if result.signal in [SignalType.BUY, SignalType.SELL]:
                            self.execute_trade(symbol, result)
                        elif result.signal in [SignalType.CLOSE_BUY, SignalType.CLOSE_SELL]:
                            self.close_positions(symbol, result.signal)
            
            self.last_analysis_time = datetime.now()
            
        except Exception as e:
            print(f"Error in strategy execution: {str(e)}")
        
        return results
    
    def get_market_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """
        Get historical market data for analysis
        
        Args:
            symbol: Trading symbol
            
        Returns:
            DataFrame with OHLCV data or None if error
        """
        try:
            if not self.mt5_connector.is_connected():
                return None
            
            # Use data_fetcher to get market data
            from utils.data_fetcher import DataFetcher
            fetcher = DataFetcher(self.mt5_connector)
            
            return fetcher.get_historical_data(
                symbol, 
                self.timeframe, 
                self.lookback_periods
            )
            
        except Exception as e:
            print(f"Error getting market data for {symbol}: {str(e)}")
            return None
    
    def execute_trade(self, symbol: str, result: StrategyResult):
        """
        Execute a trade based on strategy result
        
        Args:
            symbol: Trading symbol
            result: StrategyResult with trade parameters
        """
        try:
            # Check risk management
            if not self.check_risk_management(symbol, result):
                return
            
            # Use order_manager to execute trade
            from utils.order_manager import OrderManager
            order_manager = OrderManager(self.mt5_connector, self.config)
            
            # Determine trade parameters
            lot_size = result.lot_size or self.calculate_lot_size(symbol, result)
            stop_loss = result.stop_loss or self.calculate_stop_loss(symbol, result)
            take_profit = result.take_profit or self.calculate_take_profit(symbol, result)
            
            # Execute order
            if result.signal == SignalType.BUY:
                order_result = order_manager.place_buy_order(
                    symbol, lot_size, stop_loss, take_profit, result.reason
                )
            elif result.signal == SignalType.SELL:
                order_result = order_manager.place_sell_order(
                    symbol, lot_size, stop_loss, take_profit, result.reason
                )
            
            # Update position tracking
            if order_result and order_result.get('success'):
                self.current_positions[symbol] = {
                    'signal': result.signal,
                    'entry_time': datetime.now(),
                    'lot_size': lot_size,
                    'entry_price': result.entry_price,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'ticket': order_result.get('ticket')
                }
                
        except Exception as e:
            print(f"Error executing trade for {symbol}: {str(e)}")
    
    def close_positions(self, symbol: str, close_signal: SignalType):
        """
        Close existing positions for a symbol
        
        Args:
            symbol: Trading symbol
            close_signal: Type of close signal
        """
        try:
            if symbol not in self.current_positions:
                return
            
            from utils.order_manager import OrderManager
            order_manager = OrderManager(self.mt5_connector, self.config)
            
            position = self.current_positions[symbol]
            ticket = position.get('ticket')
            
            if ticket:
                if close_signal == SignalType.CLOSE_BUY and position['signal'] == SignalType.BUY:
                    order_manager.close_position(ticket)
                elif close_signal == SignalType.CLOSE_SELL and position['signal'] == SignalType.SELL:
                    order_manager.close_position(ticket)
                
                # Remove from position tracking
                del self.current_positions[symbol]
                
        except Exception as e:
            print(f"Error closing position for {symbol}: {str(e)}")
    
    def check_risk_management(self, symbol: str, result: StrategyResult) -> bool:
        """
        Check if trade meets risk management criteria
        
        Args:
            symbol: Trading symbol
            result: StrategyResult to check
            
        Returns:
            True if trade is allowed, False otherwise
        """
        try:
            # Check maximum positions
            if len(self.current_positions) >= self.config.MAX_POSITIONS:
                return False
            
            # Check if already have position in this symbol
            if symbol in self.current_positions:
                return False
            
            # Check confidence threshold
            if result.confidence < 0.6:  # Minimum 60% confidence
                return False
            
            # Check account balance and risk
            account_info = self.mt5_connector.get_account_info()
            if not account_info:
                return False
            
            balance = account_info.get('balance', 0)
            if balance <= 0:
                return False
            
            # Calculate potential loss
            lot_size = result.lot_size or self.calculate_lot_size(symbol, result)
            potential_loss = lot_size * abs(result.stop_loss - result.entry_price) if result.stop_loss and result.entry_price else 0
            
            # Check risk per trade
            risk_percentage = potential_loss / balance
            if risk_percentage > self.max_risk_per_trade:
                return False
            
            return True
            
        except Exception as e:
            print(f"Error in risk management check: {str(e)}")
            return False
    
    def calculate_lot_size(self, symbol: str, result: StrategyResult) -> float:
        """
        Calculate appropriate lot size based on risk management
        
        Args:
            symbol: Trading symbol
            result: StrategyResult
            
        Returns:
            Calculated lot size
        """
        try:
            # Get account information
            account_info = self.mt5_connector.get_account_info()
            if not account_info:
                return self.default_lot_size
            
            balance = account_info.get('balance', 0)
            if balance <= 0:
                return self.default_lot_size
            
            # Risk-based lot size calculation
            if result.entry_price and result.stop_loss:
                risk_amount = balance * self.max_risk_per_trade
                price_diff = abs(result.entry_price - result.stop_loss)
                
                if price_diff > 0:
                    # Get symbol info for contract size
                    symbol_info = self.mt5_connector.get_symbol_info(symbol)
                    if symbol_info:
                        contract_size = symbol_info.get('trade_contract_size', 100000)
                        calculated_lot = risk_amount / (price_diff * contract_size)
                        
                        # Ensure within reasonable bounds
                        min_lot = symbol_info.get('volume_min', 0.01)
                        max_lot = symbol_info.get('volume_max', 10.0)
                        
                        return max(min_lot, min(calculated_lot, max_lot))
            
            return self.default_lot_size
            
        except Exception as e:
            print(f"Error calculating lot size: {str(e)}")
            return self.default_lot_size
    
    def calculate_stop_loss(self, symbol: str, result: StrategyResult) -> Optional[float]:
        """Calculate stop loss price"""
        if result.stop_loss:
            return result.stop_loss
        
        if result.entry_price:
            if result.signal == SignalType.BUY:
                return result.entry_price - (self.default_stop_loss * 0.0001)
            elif result.signal == SignalType.SELL:
                return result.entry_price + (self.default_stop_loss * 0.0001)
        
        return None
    
    def calculate_take_profit(self, symbol: str, result: StrategyResult) -> Optional[float]:
        """Calculate take profit price"""
        if result.take_profit:
            return result.take_profit
        
        if result.entry_price:
            if result.signal == SignalType.BUY:
                return result.entry_price + (self.default_take_profit * 0.0001)
            elif result.signal == SignalType.SELL:
                return result.entry_price - (self.default_take_profit * 0.0001)
        
        return None
    
    # Technical Analysis Helper Methods
    
    def calculate_sma(self, data: pd.Series, period: int) -> pd.Series:
        """Calculate Simple Moving Average"""
        return data.rolling(window=period).mean()
    
    def calculate_ema(self, data: pd.Series, period: int) -> pd.Series:
        """Calculate Exponential Moving Average"""
        return data.ewm(span=period).mean()
    
    def calculate_rsi(self, data: pd.Series, period: int = 14) -> pd.Series:
        """Calculate Relative Strength Index"""
        delta = data.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def calculate_macd(self, data: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
        """Calculate MACD indicator"""
        exp1 = data.ewm(span=fast).mean()
        exp2 = data.ewm(span=slow).mean()
        macd = exp1 - exp2
        signal_line = macd.ewm(span=signal).mean()
        histogram = macd - signal_line
        
        return macd, signal_line, histogram
    
    def calculate_bollinger_bands(self, data: pd.Series, period: int = 20, std_dev: float = 2.0):
        """Calculate Bollinger Bands"""
        sma = self.calculate_sma(data, period)
        std = data.rolling(window=period).std()
        
        upper_band = sma + (std * std_dev)
        lower_band = sma - (std * std_dev)
        
        return upper_band, sma, lower_band
    
    def identify_support_resistance(self, data: pd.DataFrame, window: int = 20):
        """Identify support and resistance levels"""
        highs = data['high'].rolling(window=window, center=True).max() == data['high']
        lows = data['low'].rolling(window=window, center=True).min() == data['low']
        
        resistance_levels = data.loc[highs, 'high'].tolist()
        support_levels = data.loc[lows, 'low'].tolist()
        
        return support_levels, resistance_levels
