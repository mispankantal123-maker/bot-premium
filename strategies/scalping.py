"""
Scalping Strategy for TradeMaestro
High-frequency trading strategy focusing on small price movements
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional

from .base_strategy import BaseStrategy, StrategyResult, SignalType


class ScalpingStrategy(BaseStrategy):
    """
    Scalping strategy implementation
    Focuses on quick trades with tight stop losses and take profits
    """
    
    def initialize_parameters(self):
        """Initialize scalping-specific parameters"""
        # Scalping parameters
        self.ema_fast_period = 5
        self.ema_slow_period = 13
        self.rsi_period = 14
        self.rsi_oversold = 30
        self.rsi_overbought = 70
        
        # Bollinger Bands parameters
        self.bb_period = 20
        self.bb_std_dev = 2.0
        
        # Trade management
        self.min_pips_move = 5  # Minimum price movement to consider
        self.max_spread_multiplier = 2.0  # Max spread allowed
        self.confidence_threshold = 0.65
        
        # Scalping-specific risk management
        self.scalp_stop_loss_pips = 15
        self.scalp_take_profit_pips = 25
        self.max_trade_duration_minutes = 30
        
        # News and session filters
        self.avoid_news_minutes_before = 30
        self.avoid_news_minutes_after = 15
        self.preferred_sessions = ['London', 'New_York', 'Overlap_London_NY']
    
    def analyze_market(self, symbol: str, data: pd.DataFrame) -> Optional[StrategyResult]:
        """
        Analyze market for scalping opportunities
        
        Args:
            symbol: Trading symbol
            data: Historical OHLCV data
            
        Returns:
            StrategyResult or None
        """
        try:
            # Pre-filtering checks
            if not self.is_suitable_for_scalping(symbol, data):
                return StrategyResult(
                    signal=SignalType.HOLD,
                    confidence=0.0,
                    reason="Market conditions not suitable for scalping"
                )
            
            # Calculate technical indicators
            indicators = self.calculate_indicators(data)
            
            # Generate signals
            signal_result = self.generate_scalping_signal(symbol, data, indicators)
            
            # Enhance with entry/exit levels
            if signal_result.signal in [SignalType.BUY, SignalType.SELL]:
                signal_result = self.calculate_trade_levels(symbol, data, signal_result, indicators)
            
            return signal_result
            
        except Exception as e:
            print(f"Error in scalping analysis for {symbol}: {str(e)}")
            return StrategyResult(
                signal=SignalType.HOLD,
                confidence=0.0,
                reason=f"Analysis error: {str(e)}"
            )
    
    def is_suitable_for_scalping(self, symbol: str, data: pd.DataFrame) -> bool:
        """
        Check if market conditions are suitable for scalping
        
        Args:
            symbol: Trading symbol
            data: Price data
            
        Returns:
            True if suitable, False otherwise
        """
        try:
            # Check if we have enough data
            if len(data) < self.ema_slow_period:
                return False
            
            # Check spread conditions
            current_spread = self.get_current_spread(symbol)
            if current_spread is None:
                return False
            
            # Get average spread for symbol
            symbol_info = self.mt5_connector.get_symbol_info(symbol)
            if symbol_info:
                point = symbol_info.get('point', 0.0001)
                spread_pips = current_spread / point
                
                # Check if spread is reasonable for scalping
                max_allowed_spread = 3.0  # Maximum 3 pips for major pairs
                if spread_pips > max_allowed_spread:
                    return False
            
            # Check volatility - should be moderate for scalping
            recent_data = data.tail(20)
            volatility = (recent_data['high'] - recent_data['low']).mean()
            atr = self.calculate_atr(data, 14)
            current_atr = atr.iloc[-1] if len(atr) > 0 else 0
            
            # Volatility should be neither too low nor too high
            if current_atr < 0.0005 or current_atr > 0.0050:  # Adjust based on symbol
                return False
            
            # Check trading session
            if not self.is_preferred_session():
                return False
            
            # Check news events (basic time-based filtering)
            if self.is_news_time():
                return False
            
            return True
            
        except Exception as e:
            print(f"Error checking scalping suitability: {str(e)}")
            return False
    
    def calculate_indicators(self, data: pd.DataFrame) -> dict:
        """Calculate technical indicators for scalping"""
        indicators = {}
        
        try:
            close = data['close']
            high = data['high']
            low = data['low']
            
            # Moving averages
            indicators['ema_fast'] = self.calculate_ema(close, self.ema_fast_period)
            indicators['ema_slow'] = self.calculate_ema(close, self.ema_slow_period)
            
            # RSI
            indicators['rsi'] = self.calculate_rsi(close, self.rsi_period)
            
            # Bollinger Bands
            bb_upper, bb_middle, bb_lower = self.calculate_bollinger_bands(
                close, self.bb_period, self.bb_std_dev
            )
            indicators['bb_upper'] = bb_upper
            indicators['bb_middle'] = bb_middle
            indicators['bb_lower'] = bb_lower
            
            # Price position within Bollinger Bands
            indicators['bb_position'] = (close - bb_lower) / (bb_upper - bb_lower)
            
            # ATR for volatility
            indicators['atr'] = self.calculate_atr(data, 14)
            
            # Support and resistance levels
            support_levels, resistance_levels = self.identify_support_resistance(data, 10)
            indicators['support_levels'] = support_levels[-3:] if support_levels else []
            indicators['resistance_levels'] = resistance_levels[-3:] if resistance_levels else []
            
            # Price momentum
            indicators['momentum'] = close.pct_change(periods=3)
            
            # Volume analysis (if available)
            if 'volume' in data.columns:
                indicators['volume_sma'] = self.calculate_sma(data['volume'], 10)
                indicators['volume_ratio'] = data['volume'] / indicators['volume_sma']
            
        except Exception as e:
            print(f"Error calculating indicators: {str(e)}")
        
        return indicators
    
    def generate_scalping_signal(self, symbol: str, data: pd.DataFrame, indicators: dict) -> StrategyResult:
        """Generate scalping trading signal based on multiple conditions"""
        try:
            current_price = data['close'].iloc[-1]
            current_time = datetime.now()
            
            # Initialize signal components
            buy_signals = 0
            sell_signals = 0
            confidence_factors = []
            reasons = []
            
            # 1. EMA Crossover Signal
            if len(indicators['ema_fast']) >= 2 and len(indicators['ema_slow']) >= 2:
                ema_fast_current = indicators['ema_fast'].iloc[-1]
                ema_fast_prev = indicators['ema_fast'].iloc[-2]
                ema_slow_current = indicators['ema_slow'].iloc[-1]
                ema_slow_prev = indicators['ema_slow'].iloc[-2]
                
                # Bullish crossover
                if (ema_fast_current > ema_slow_current and 
                    ema_fast_prev <= ema_slow_prev):
                    buy_signals += 2
                    confidence_factors.append(0.8)
                    reasons.append("EMA bullish crossover")
                
                # Bearish crossover
                elif (ema_fast_current < ema_slow_current and 
                      ema_fast_prev >= ema_slow_prev):
                    sell_signals += 2
                    confidence_factors.append(0.8)
                    reasons.append("EMA bearish crossover")
                
                # Trend continuation
                elif ema_fast_current > ema_slow_current:
                    buy_signals += 1
                    confidence_factors.append(0.4)
                    reasons.append("EMA uptrend")
                
                elif ema_fast_current < ema_slow_current:
                    sell_signals += 1
                    confidence_factors.append(0.4)
                    reasons.append("EMA downtrend")
            
            # 2. RSI Signal
            if len(indicators['rsi']) > 0:
                current_rsi = indicators['rsi'].iloc[-1]
                
                if current_rsi < self.rsi_oversold:
                    buy_signals += 1
                    confidence_factors.append(0.6)
                    reasons.append(f"RSI oversold ({current_rsi:.1f})")
                
                elif current_rsi > self.rsi_overbought:
                    sell_signals += 1
                    confidence_factors.append(0.6)
                    reasons.append(f"RSI overbought ({current_rsi:.1f})")
            
            # 3. Bollinger Bands Signal
            if len(indicators['bb_position']) > 0:
                bb_pos = indicators['bb_position'].iloc[-1]
                
                # Price near lower band (oversold)
                if bb_pos < 0.2:
                    buy_signals += 1
                    confidence_factors.append(0.5)
                    reasons.append("Price near BB lower band")
                
                # Price near upper band (overbought)
                elif bb_pos > 0.8:
                    sell_signals += 1
                    confidence_factors.append(0.5)
                    reasons.append("Price near BB upper band")
            
            # 4. Support/Resistance Signal
            support_levels = indicators.get('support_levels', [])
            resistance_levels = indicators.get('resistance_levels', [])
            
            for support in support_levels:
                if abs(current_price - support) / current_price < 0.0005:  # Within 0.05%
                    buy_signals += 1
                    confidence_factors.append(0.7)
                    reasons.append("Price at support level")
            
            for resistance in resistance_levels:
                if abs(current_price - resistance) / current_price < 0.0005:  # Within 0.05%
                    sell_signals += 1
                    confidence_factors.append(0.7)
                    reasons.append("Price at resistance level")
            
            # 5. Momentum Signal
            if len(indicators['momentum']) >= 3:
                recent_momentum = indicators['momentum'].iloc[-3:].mean()
                
                if recent_momentum > 0.0001:  # Positive momentum
                    buy_signals += 1
                    confidence_factors.append(0.3)
                    reasons.append("Positive momentum")
                
                elif recent_momentum < -0.0001:  # Negative momentum
                    sell_signals += 1
                    confidence_factors.append(0.3)
                    reasons.append("Negative momentum")
            
            # 6. Volume Confirmation (if available)
            if 'volume_ratio' in indicators and len(indicators['volume_ratio']) > 0:
                volume_ratio = indicators['volume_ratio'].iloc[-1]
                
                if volume_ratio > 1.5:  # Higher than average volume
                    if buy_signals > sell_signals:
                        confidence_factors.append(0.2)
                        reasons.append("High volume confirmation")
                    elif sell_signals > buy_signals:
                        confidence_factors.append(0.2)
                        reasons.append("High volume confirmation")
            
            # Decision logic
            signal = SignalType.HOLD
            confidence = 0.0
            final_reason = "No clear signal"
            
            if buy_signals > sell_signals and buy_signals >= 2:
                signal = SignalType.BUY
                confidence = min(0.95, sum(confidence_factors) / len(confidence_factors) if confidence_factors else 0.5)
                final_reason = "; ".join(reasons)
            
            elif sell_signals > buy_signals and sell_signals >= 2:
                signal = SignalType.SELL
                confidence = min(0.95, sum(confidence_factors) / len(confidence_factors) if confidence_factors else 0.5)
                final_reason = "; ".join(reasons)
            
            # Filter by minimum confidence
            if confidence < self.confidence_threshold:
                signal = SignalType.HOLD
                final_reason = f"Low confidence ({confidence:.2f})"
            
            return StrategyResult(
                signal=signal,
                confidence=confidence,
                entry_price=current_price,
                reason=final_reason,
                metadata={
                    'buy_signals': buy_signals,
                    'sell_signals': sell_signals,
                    'indicators': {k: v.iloc[-1] if hasattr(v, 'iloc') else v for k, v in indicators.items()
                                 if not k.endswith('_levels')}
                }
            )
            
        except Exception as e:
            print(f"Error generating scalping signal: {str(e)}")
            return StrategyResult(
                signal=SignalType.HOLD,
                confidence=0.0,
                reason=f"Signal generation error: {str(e)}"
            )
    
    def calculate_trade_levels(self, symbol: str, data: pd.DataFrame, 
                             result: StrategyResult, indicators: dict) -> StrategyResult:
        """Calculate stop loss and take profit levels for scalping"""
        try:
            current_price = result.entry_price or data['close'].iloc[-1]
            
            # Get symbol info for point calculation
            symbol_info = self.mt5_connector.get_symbol_info(symbol)
            if not symbol_info:
                return result
            
            point = symbol_info.get('point', 0.0001)
            
            # ATR-based levels
            atr = indicators.get('atr')
            current_atr = atr.iloc[-1] if atr is not None and len(atr) > 0 else 0.0005
            
            if result.signal == SignalType.BUY:
                # Dynamic stop loss (minimum of fixed pips or ATR-based)
                atr_stop = current_price - (current_atr * 1.5)
                fixed_stop = current_price - (self.scalp_stop_loss_pips * point)
                result.stop_loss = max(atr_stop, fixed_stop)
                
                # Dynamic take profit
                atr_target = current_price + (current_atr * 2.0)
                fixed_target = current_price + (self.scalp_take_profit_pips * point)
                result.take_profit = min(atr_target, fixed_target)
                
                # Check for nearby resistance
                resistance_levels = indicators.get('resistance_levels', [])
                for resistance in resistance_levels:
                    if current_price < resistance < result.take_profit:
                        result.take_profit = resistance - (2 * point)  # Adjust for spread
                        break
            
            elif result.signal == SignalType.SELL:
                # Dynamic stop loss
                atr_stop = current_price + (current_atr * 1.5)
                fixed_stop = current_price + (self.scalp_stop_loss_pips * point)
                result.stop_loss = min(atr_stop, fixed_stop)
                
                # Dynamic take profit
                atr_target = current_price - (current_atr * 2.0)
                fixed_target = current_price - (self.scalp_take_profit_pips * point)
                result.take_profit = max(atr_target, fixed_target)
                
                # Check for nearby support
                support_levels = indicators.get('support_levels', [])
                for support in support_levels:
                    if result.take_profit < support < current_price:
                        result.take_profit = support + (2 * point)  # Adjust for spread
                        break
            
            # Calculate risk-reward ratio
            if result.stop_loss and result.take_profit:
                risk = abs(current_price - result.stop_loss)
                reward = abs(result.take_profit - current_price)
                risk_reward_ratio = reward / risk if risk > 0 else 0
                
                # Minimum risk-reward ratio for scalping
                if risk_reward_ratio < 1.2:
                    result.signal = SignalType.HOLD
                    result.reason = f"Poor risk-reward ratio ({risk_reward_ratio:.2f})"
                    result.confidence = 0.0
                
                result.metadata['risk_reward_ratio'] = risk_reward_ratio
            
            return result
            
        except Exception as e:
            print(f"Error calculating trade levels: {str(e)}")
            return result
    
    def calculate_atr(self, data: pd.DataFrame, period: int = 14) -> pd.Series:
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
            
        except Exception as e:
            print(f"Error calculating ATR: {str(e)}")
            return pd.Series([0.0005] * len(data))
    
    def get_current_spread(self, symbol: str) -> Optional[float]:
        """Get current bid-ask spread for symbol"""
        try:
            if not self.mt5_connector.is_connected():
                return None
            
            tick = self.mt5_connector.get_symbol_tick(symbol)
            if tick:
                return tick.get('ask', 0) - tick.get('bid', 0)
            
            return None
            
        except Exception as e:
            print(f"Error getting spread for {symbol}: {str(e)}")
            return None
    
    def is_preferred_session(self) -> bool:
        """Check if current time is within preferred trading sessions"""
        try:
            current_time = datetime.utcnow().time()
            current_hour = current_time.hour
            
            # Define session hours (UTC)
            sessions = {
                'London': (7, 16),
                'New_York': (13, 22),
                'Overlap_London_NY': (13, 16)
            }
            
            for session_name in self.preferred_sessions:
                if session_name in sessions:
                    start_hour, end_hour = sessions[session_name]
                    if start_hour <= current_hour < end_hour:
                        return True
            
            return False
            
        except Exception as e:
            print(f"Error checking trading session: {str(e)}")
            return True  # Default to allowing trading
    
    def is_news_time(self) -> bool:
        """Basic news time detection (placeholder for more sophisticated implementation)"""
        try:
            current_time = datetime.utcnow()
            current_hour = current_time.hour
            current_minute = current_time.minute
            
            # High-impact news times (UTC)
            news_times = [
                (8, 30),   # European news
                (12, 30),  # US news
                (14, 30),  # FOMC, NFP
            ]
            
            for news_hour, news_minute in news_times:
                news_time = current_time.replace(hour=news_hour, minute=news_minute)
                time_diff = abs((current_time - news_time).total_seconds()) / 60
                
                if time_diff <= self.avoid_news_minutes_before:
                    return True
            
            return False
            
        except Exception as e:
            print(f"Error checking news time: {str(e)}")
            return False
