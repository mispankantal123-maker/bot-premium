"""
Swing Trading Strategy for TradeMaestro
Medium-term trading strategy focusing on trend reversals and continuations
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional

from .base_strategy import BaseStrategy, StrategyResult, SignalType


class SwingStrategy(BaseStrategy):
    """
    Swing trading strategy implementation
    Focuses on capturing larger price movements over days/weeks
    """
    
    def initialize_parameters(self):
        """Initialize swing trading specific parameters"""
        # Moving average parameters
        self.ma_short_period = 20
        self.ma_long_period = 50
        self.ma_signal_period = 200
        
        # RSI parameters
        self.rsi_period = 14
        self.rsi_oversold = 35
        self.rsi_overbought = 65
        
        # MACD parameters
        self.macd_fast = 12
        self.macd_slow = 26
        self.macd_signal = 9
        
        # Bollinger Bands parameters
        self.bb_period = 20
        self.bb_std_dev = 2.0
        
        # Swing specific parameters
        self.min_trend_strength = 0.7
        self.lookback_for_swing = 50
        self.confidence_threshold = 0.6
        
        # Risk management for swing trading
        self.swing_stop_loss_pips = 80
        self.swing_take_profit_pips = 160
        self.max_trade_duration_days = 7
        
        # Preferred timeframes for swing trading
        self.preferred_timeframes = ['H1', 'H4', 'D1']
        
        # Override base timeframe for swing trading
        self.timeframe = 'H4'
        self.lookback_periods = 200  # Need more data for swing analysis
    
    def analyze_market(self, symbol: str, data: pd.DataFrame) -> Optional[StrategyResult]:
        """
        Analyze market for swing trading opportunities
        
        Args:
            symbol: Trading symbol
            data: Historical OHLCV data
            
        Returns:
            StrategyResult or None
        """
        try:
            # Pre-filtering checks
            if not self.is_suitable_for_swing_trading(symbol, data):
                return StrategyResult(
                    signal=SignalType.HOLD,
                    confidence=0.0,
                    reason="Market conditions not suitable for swing trading"
                )
            
            # Calculate technical indicators
            indicators = self.calculate_swing_indicators(data)
            
            # Analyze trend structure
            trend_analysis = self.analyze_trend_structure(data, indicators)
            
            # Generate swing trading signal
            signal_result = self.generate_swing_signal(symbol, data, indicators, trend_analysis)
            
            # Calculate entry/exit levels
            if signal_result.signal in [SignalType.BUY, SignalType.SELL]:
                signal_result = self.calculate_swing_trade_levels(symbol, data, signal_result, indicators)
            
            return signal_result
            
        except Exception as e:
            print(f"Error in swing trading analysis for {symbol}: {str(e)}")
            return StrategyResult(
                signal=SignalType.HOLD,
                confidence=0.0,
                reason=f"Analysis error: {str(e)}"
            )
    
    def is_suitable_for_swing_trading(self, symbol: str, data: pd.DataFrame) -> bool:
        """
        Check if market conditions are suitable for swing trading
        
        Args:
            symbol: Trading symbol
            data: Price data
            
        Returns:
            True if suitable, False otherwise
        """
        try:
            # Check if we have enough data
            if len(data) < self.ma_signal_period:
                return False
            
            # Check for sufficient volatility
            recent_data = data.tail(20)
            volatility = (recent_data['high'] - recent_data['low']).std()
            
            # Should have reasonable volatility for swing moves
            if volatility < 0.001:  # Too low volatility
                return False
            
            # Check trend clarity - avoid choppy markets
            close_prices = data['close']
            ma20 = self.calculate_sma(close_prices, 20)
            ma50 = self.calculate_sma(close_prices, 50)
            
            if len(ma20) >= 10 and len(ma50) >= 10:
                # Check for trend consistency
                ma20_trend = (ma20.iloc[-1] - ma20.iloc[-10]) / ma20.iloc[-10]
                ma50_trend = (ma50.iloc[-1] - ma50.iloc[-10]) / ma50.iloc[-10]
                
                # Both MAs should be moving in same direction for clear trend
                if abs(ma20_trend) < 0.005 and abs(ma50_trend) < 0.002:
                    return False  # Too sideways
            
            # Check for recent swing highs/lows
            swing_points = self.identify_swing_points(data)
            if len(swing_points) < 2:
                return False  # Need swing structure
            
            return True
            
        except Exception as e:
            print(f"Error checking swing trading suitability: {str(e)}")
            return False
    
    def calculate_swing_indicators(self, data: pd.DataFrame) -> dict:
        """Calculate technical indicators for swing trading"""
        indicators = {}
        
        try:
            close = data['close']
            high = data['high']
            low = data['low']
            
            # Multiple timeframe moving averages
            indicators['ma_short'] = self.calculate_sma(close, self.ma_short_period)
            indicators['ma_long'] = self.calculate_sma(close, self.ma_long_period)
            indicators['ma_signal'] = self.calculate_sma(close, self.ma_signal_period)
            
            # Exponential moving averages
            indicators['ema_short'] = self.calculate_ema(close, self.ma_short_period)
            indicators['ema_long'] = self.calculate_ema(close, self.ma_long_period)
            
            # RSI
            indicators['rsi'] = self.calculate_rsi(close, self.rsi_period)
            
            # MACD
            macd, macd_signal, macd_histogram = self.calculate_macd(
                close, self.macd_fast, self.macd_slow, self.macd_signal
            )
            indicators['macd'] = macd
            indicators['macd_signal'] = macd_signal
            indicators['macd_histogram'] = macd_histogram
            
            # Bollinger Bands
            bb_upper, bb_middle, bb_lower = self.calculate_bollinger_bands(
                close, self.bb_period, self.bb_std_dev
            )
            indicators['bb_upper'] = bb_upper
            indicators['bb_middle'] = bb_middle
            indicators['bb_lower'] = bb_lower
            
            # ATR for volatility
            indicators['atr'] = self.calculate_atr(data, 14)
            
            # Swing highs and lows
            indicators['swing_highs'] = self.find_swing_highs(data, 10)
            indicators['swing_lows'] = self.find_swing_lows(data, 10)
            
            # Trend strength
            indicators['trend_strength'] = self.calculate_trend_strength(data)
            
            # Support and resistance levels
            support_levels, resistance_levels = self.identify_support_resistance(data, 20)
            indicators['support_levels'] = support_levels[-5:] if support_levels else []
            indicators['resistance_levels'] = resistance_levels[-5:] if resistance_levels else []
            
            # Volume analysis (if available)
            if 'volume' in data.columns:
                indicators['volume_ma'] = self.calculate_sma(data['volume'], 20)
                indicators['volume_trend'] = data['volume'] / indicators['volume_ma']
            
        except Exception as e:
            print(f"Error calculating swing indicators: {str(e)}")
        
        return indicators
    
    def analyze_trend_structure(self, data: pd.DataFrame, indicators: dict) -> dict:
        """Analyze the overall trend structure"""
        trend_analysis = {}
        
        try:
            # Primary trend (200 MA)
            if len(indicators['ma_signal']) > 0:
                current_price = data['close'].iloc[-1]
                ma_signal = indicators['ma_signal'].iloc[-1]
                
                if current_price > ma_signal:
                    trend_analysis['primary_trend'] = 'BULLISH'
                else:
                    trend_analysis['primary_trend'] = 'BEARISH'
                
                # Trend strength based on distance from 200 MA
                distance = abs(current_price - ma_signal) / ma_signal
                trend_analysis['trend_strength'] = min(1.0, distance * 100)  # Scale to 0-1
            
            # Secondary trend (50 vs 200 MA)
            if len(indicators['ma_long']) > 0 and len(indicators['ma_signal']) > 0:
                ma_long = indicators['ma_long'].iloc[-1]
                ma_signal = indicators['ma_signal'].iloc[-1]
                
                if ma_long > ma_signal:
                    trend_analysis['secondary_trend'] = 'BULLISH'
                else:
                    trend_analysis['secondary_trend'] = 'BEARISH'
            
            # Short-term trend (20 vs 50 MA)
            if len(indicators['ma_short']) > 0 and len(indicators['ma_long']) > 0:
                ma_short = indicators['ma_short'].iloc[-1]
                ma_long = indicators['ma_long'].iloc[-1]
                
                if ma_short > ma_long:
                    trend_analysis['short_trend'] = 'BULLISH'
                else:
                    trend_analysis['short_trend'] = 'BEARISH'
            
            # Trend alignment
            trends = [
                trend_analysis.get('primary_trend'),
                trend_analysis.get('secondary_trend'),
                trend_analysis.get('short_trend')
            ]
            
            if all(t == 'BULLISH' for t in trends):
                trend_analysis['alignment'] = 'STRONG_BULLISH'
            elif all(t == 'BEARISH' for t in trends):
                trend_analysis['alignment'] = 'STRONG_BEARISH'
            elif trends.count('BULLISH') > trends.count('BEARISH'):
                trend_analysis['alignment'] = 'WEAK_BULLISH'
            elif trends.count('BEARISH') > trends.count('BULLISH'):
                trend_analysis['alignment'] = 'WEAK_BEARISH'
            else:
                trend_analysis['alignment'] = 'MIXED'
            
            # Momentum analysis
            if 'macd_histogram' in indicators and len(indicators['macd_histogram']) >= 2:
                current_hist = indicators['macd_histogram'].iloc[-1]
                prev_hist = indicators['macd_histogram'].iloc[-2]
                
                if current_hist > prev_hist > 0:
                    trend_analysis['momentum'] = 'ACCELERATING_UP'
                elif current_hist < prev_hist < 0:
                    trend_analysis['momentum'] = 'ACCELERATING_DOWN'
                elif current_hist > 0 > prev_hist:
                    trend_analysis['momentum'] = 'TURNING_BULLISH'
                elif current_hist < 0 < prev_hist:
                    trend_analysis['momentum'] = 'TURNING_BEARISH'
                else:
                    trend_analysis['momentum'] = 'NEUTRAL'
            
        except Exception as e:
            print(f"Error analyzing trend structure: {str(e)}")
        
        return trend_analysis
    
    def generate_swing_signal(self, symbol: str, data: pd.DataFrame, 
                            indicators: dict, trend_analysis: dict) -> StrategyResult:
        """Generate swing trading signal based on trend and momentum"""
        try:
            current_price = data['close'].iloc[-1]
            
            buy_signals = 0
            sell_signals = 0
            confidence_factors = []
            reasons = []
            
            # 1. Trend alignment signal
            alignment = trend_analysis.get('alignment', 'MIXED')
            
            if alignment in ['STRONG_BULLISH', 'WEAK_BULLISH']:
                buy_signals += 2 if 'STRONG' in alignment else 1
                confidence_factors.append(0.8 if 'STRONG' in alignment else 0.5)
                reasons.append(f"Bullish trend alignment ({alignment})")
            
            elif alignment in ['STRONG_BEARISH', 'WEAK_BEARISH']:
                sell_signals += 2 if 'STRONG' in alignment else 1
                confidence_factors.append(0.8 if 'STRONG' in alignment else 0.5)
                reasons.append(f"Bearish trend alignment ({alignment})")
            
            # 2. Moving average crossover
            if (len(indicators['ma_short']) >= 2 and 
                len(indicators['ma_long']) >= 2):
                
                ma_short_current = indicators['ma_short'].iloc[-1]
                ma_short_prev = indicators['ma_short'].iloc[-2]
                ma_long_current = indicators['ma_long'].iloc[-1]
                ma_long_prev = indicators['ma_long'].iloc[-2]
                
                # Golden cross
                if (ma_short_current > ma_long_current and 
                    ma_short_prev <= ma_long_prev):
                    buy_signals += 2
                    confidence_factors.append(0.9)
                    reasons.append("Golden cross (MA bullish crossover)")
                
                # Death cross
                elif (ma_short_current < ma_long_current and 
                      ma_short_prev >= ma_long_prev):
                    sell_signals += 2
                    confidence_factors.append(0.9)
                    reasons.append("Death cross (MA bearish crossover)")
            
            # 3. MACD signal
            if ('macd' in indicators and 'macd_signal' in indicators and 
                len(indicators['macd']) >= 2 and len(indicators['macd_signal']) >= 2):
                
                macd_current = indicators['macd'].iloc[-1]
                macd_prev = indicators['macd'].iloc[-2]
                signal_current = indicators['macd_signal'].iloc[-1]
                signal_prev = indicators['macd_signal'].iloc[-2]
                
                # MACD bullish crossover
                if (macd_current > signal_current and 
                    macd_prev <= signal_prev):
                    buy_signals += 1
                    confidence_factors.append(0.7)
                    reasons.append("MACD bullish crossover")
                
                # MACD bearish crossover
                elif (macd_current < signal_current and 
                      macd_prev >= signal_prev):
                    sell_signals += 1
                    confidence_factors.append(0.7)
                    reasons.append("MACD bearish crossover")
            
            # 4. RSI divergence and levels
            if len(indicators['rsi']) >= 5:
                current_rsi = indicators['rsi'].iloc[-1]
                
                # RSI oversold in uptrend
                if (current_rsi < self.rsi_oversold and 
                    alignment in ['STRONG_BULLISH', 'WEAK_BULLISH']):
                    buy_signals += 1
                    confidence_factors.append(0.6)
                    reasons.append(f"RSI oversold in uptrend ({current_rsi:.1f})")
                
                # RSI overbought in downtrend
                elif (current_rsi > self.rsi_overbought and 
                      alignment in ['STRONG_BEARISH', 'WEAK_BEARISH']):
                    sell_signals += 1
                    confidence_factors.append(0.6)
                    reasons.append(f"RSI overbought in downtrend ({current_rsi:.1f})")
                
                # Check for RSI divergence
                rsi_divergence = self.check_rsi_divergence(data, indicators['rsi'])
                if rsi_divergence == 'BULLISH':
                    buy_signals += 1
                    confidence_factors.append(0.8)
                    reasons.append("Bullish RSI divergence")
                elif rsi_divergence == 'BEARISH':
                    sell_signals += 1
                    confidence_factors.append(0.8)
                    reasons.append("Bearish RSI divergence")
            
            # 5. Support/Resistance bounce
            support_levels = indicators.get('support_levels', [])
            resistance_levels = indicators.get('resistance_levels', [])
            
            for support in support_levels:
                if abs(current_price - support) / current_price < 0.005:  # Within 0.5%
                    if alignment != 'STRONG_BEARISH':
                        buy_signals += 1
                        confidence_factors.append(0.6)
                        reasons.append("Price bouncing off support")
            
            for resistance in resistance_levels:
                if abs(current_price - resistance) / current_price < 0.005:  # Within 0.5%
                    if alignment != 'STRONG_BULLISH':
                        sell_signals += 1
                        confidence_factors.append(0.6)
                        reasons.append("Price rejection at resistance")
            
            # 6. Momentum confirmation
            momentum = trend_analysis.get('momentum', 'NEUTRAL')
            
            if momentum in ['ACCELERATING_UP', 'TURNING_BULLISH']:
                if buy_signals > 0:
                    confidence_factors.append(0.4)
                    reasons.append(f"Momentum confirmation ({momentum})")
            
            elif momentum in ['ACCELERATING_DOWN', 'TURNING_BEARISH']:
                if sell_signals > 0:
                    confidence_factors.append(0.4)
                    reasons.append(f"Momentum confirmation ({momentum})")
            
            # Decision logic
            signal = SignalType.HOLD
            confidence = 0.0
            final_reason = "No clear swing signal"
            
            if buy_signals >= 2 and buy_signals > sell_signals:
                signal = SignalType.BUY
                confidence = min(0.95, sum(confidence_factors) / len(confidence_factors) if confidence_factors else 0.5)
                final_reason = "; ".join(reasons)
            
            elif sell_signals >= 2 and sell_signals > buy_signals:
                signal = SignalType.SELL
                confidence = min(0.95, sum(confidence_factors) / len(confidence_factors) if confidence_factors else 0.5)
                final_reason = "; ".join(reasons)
            
            # Apply confidence threshold
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
                    'trend_analysis': trend_analysis,
                    'momentum': momentum
                }
            )
            
        except Exception as e:
            print(f"Error generating swing signal: {str(e)}")
            return StrategyResult(
                signal=SignalType.HOLD,
                confidence=0.0,
                reason=f"Signal generation error: {str(e)}"
            )
    
    def calculate_swing_trade_levels(self, symbol: str, data: pd.DataFrame,
                                   result: StrategyResult, indicators: dict) -> StrategyResult:
        """Calculate stop loss and take profit levels for swing trades"""
        try:
            current_price = result.entry_price or data['close'].iloc[-1]
            
            # Get symbol info for point calculation
            symbol_info = self.mt5_connector.get_symbol_info(symbol)
            if not symbol_info:
                return result
            
            point = symbol_info.get('point', 0.0001)
            
            # ATR-based levels
            atr = indicators.get('atr')
            current_atr = atr.iloc[-1] if atr is not None and len(atr) > 0 else 0.002
            
            if result.signal == SignalType.BUY:
                # Stop loss below recent swing low or support
                swing_lows = indicators.get('swing_lows', [])
                support_levels = indicators.get('support_levels', [])
                
                # Find nearest swing low
                relevant_lows = [low for low in swing_lows if low < current_price]
                if relevant_lows:
                    swing_stop = min(relevant_lows[-3:])  # Use most recent swing lows
                else:
                    swing_stop = current_price - (current_atr * 2.5)
                
                # Find nearest support
                relevant_supports = [sup for sup in support_levels if sup < current_price]
                if relevant_supports:
                    support_stop = max(relevant_supports)  # Use strongest support
                else:
                    support_stop = current_price - (current_atr * 2.0)
                
                # Use the higher of swing low or support (less aggressive stop)
                result.stop_loss = max(swing_stop, support_stop) - (5 * point)  # Buffer
                
                # Take profit at resistance or multiple of ATR
                swing_highs = indicators.get('swing_highs', [])
                resistance_levels = indicators.get('resistance_levels', [])
                
                # Target resistance levels
                relevant_resistance = [res for res in resistance_levels if res > current_price]
                if relevant_resistance:
                    result.take_profit = min(relevant_resistance) - (5 * point)
                else:
                    result.take_profit = current_price + (current_atr * 3.0)
            
            elif result.signal == SignalType.SELL:
                # Stop loss above recent swing high or resistance
                swing_highs = indicators.get('swing_highs', [])
                resistance_levels = indicators.get('resistance_levels', [])
                
                # Find nearest swing high
                relevant_highs = [high for high in swing_highs if high > current_price]
                if relevant_highs:
                    swing_stop = max(relevant_highs[-3:])
                else:
                    swing_stop = current_price + (current_atr * 2.5)
                
                # Find nearest resistance
                relevant_resistance = [res for res in resistance_levels if res > current_price]
                if relevant_resistance:
                    resistance_stop = min(relevant_resistance)
                else:
                    resistance_stop = current_price + (current_atr * 2.0)
                
                # Use the lower of swing high or resistance
                result.stop_loss = min(swing_stop, resistance_stop) + (5 * point)  # Buffer
                
                # Take profit at support
                support_levels = indicators.get('support_levels', [])
                relevant_supports = [sup for sup in support_levels if sup < current_price]
                if relevant_supports:
                    result.take_profit = max(relevant_supports) + (5 * point)
                else:
                    result.take_profit = current_price - (current_atr * 3.0)
            
            # Validate risk-reward ratio
            if result.stop_loss and result.take_profit:
                risk = abs(current_price - result.stop_loss)
                reward = abs(result.take_profit - current_price)
                risk_reward_ratio = reward / risk if risk > 0 else 0
                
                # Minimum risk-reward for swing trades
                if risk_reward_ratio < 1.5:
                    result.signal = SignalType.HOLD
                    result.reason = f"Poor risk-reward ratio ({risk_reward_ratio:.2f})"
                    result.confidence = 0.0
                
                result.metadata['risk_reward_ratio'] = risk_reward_ratio
            
            return result
            
        except Exception as e:
            print(f"Error calculating swing trade levels: {str(e)}")
            return result
    
    def find_swing_highs(self, data: pd.DataFrame, window: int = 10) -> list:
        """Find swing high points in price data"""
        try:
            highs = []
            high_prices = data['high'].values
            
            for i in range(window, len(high_prices) - window):
                if all(high_prices[i] >= high_prices[i-j] for j in range(1, window+1)) and \
                   all(high_prices[i] >= high_prices[i+j] for j in range(1, window+1)):
                    highs.append(high_prices[i])
            
            return highs
            
        except Exception as e:
            print(f"Error finding swing highs: {str(e)}")
            return []
    
    def find_swing_lows(self, data: pd.DataFrame, window: int = 10) -> list:
        """Find swing low points in price data"""
        try:
            lows = []
            low_prices = data['low'].values
            
            for i in range(window, len(low_prices) - window):
                if all(low_prices[i] <= low_prices[i-j] for j in range(1, window+1)) and \
                   all(low_prices[i] <= low_prices[i+j] for j in range(1, window+1)):
                    lows.append(low_prices[i])
            
            return lows
            
        except Exception as e:
            print(f"Error finding swing lows: {str(e)}")
            return []
    
    def identify_swing_points(self, data: pd.DataFrame) -> list:
        """Identify both swing highs and lows"""
        swing_highs = self.find_swing_highs(data)
        swing_lows = self.find_swing_lows(data)
        return swing_highs + swing_lows
    
    def calculate_trend_strength(self, data: pd.DataFrame, period: int = 20) -> pd.Series:
        """Calculate trend strength indicator"""
        try:
            close = data['close']
            
            # Calculate price momentum
            momentum = close.pct_change(period)
            
            # Calculate volatility
            volatility = close.rolling(window=period).std()
            
            # Trend strength = momentum / volatility
            trend_strength = momentum / volatility
            
            return trend_strength.fillna(0)
            
        except Exception as e:
            print(f"Error calculating trend strength: {str(e)}")
            return pd.Series([0] * len(data))
    
    def check_rsi_divergence(self, data: pd.DataFrame, rsi: pd.Series, lookback: int = 20) -> str:
        """Check for RSI divergence patterns"""
        try:
            if len(data) < lookback or len(rsi) < lookback:
                return 'NONE'
            
            recent_data = data.tail(lookback)
            recent_rsi = rsi.tail(lookback)
            
            # Find price highs and lows
            price_highs = recent_data['high'].rolling(window=5, center=True).max() == recent_data['high']
            price_lows = recent_data['low'].rolling(window=5, center=True).min() == recent_data['low']
            
            # Get actual high and low points
            high_points = recent_data.loc[price_highs, 'high']
            low_points = recent_data.loc[price_lows, 'low']
            
            # Get corresponding RSI values
            rsi_at_highs = recent_rsi[price_highs]
            rsi_at_lows = recent_rsi[price_lows]
            
            # Check for bearish divergence (price making higher highs, RSI making lower highs)
            if len(high_points) >= 2 and len(rsi_at_highs) >= 2:
                if (high_points.iloc[-1] > high_points.iloc[-2] and 
                    rsi_at_highs.iloc[-1] < rsi_at_highs.iloc[-2]):
                    return 'BEARISH'
            
            # Check for bullish divergence (price making lower lows, RSI making higher lows)
            if len(low_points) >= 2 and len(rsi_at_lows) >= 2:
                if (low_points.iloc[-1] < low_points.iloc[-2] and 
                    rsi_at_lows.iloc[-1] > rsi_at_lows.iloc[-2]):
                    return 'BULLISH'
            
            return 'NONE'
            
        except Exception as e:
            print(f"Error checking RSI divergence: {str(e)}")
            return 'NONE'
    
    def calculate_atr(self, data: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average True Range for swing trading"""
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
            return pd.Series([0.002] * len(data))  # Default ATR for swing trading
