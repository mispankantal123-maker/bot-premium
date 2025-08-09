"""
Mock MetaTrader5 Connector for Demo Mode
Provides simulated trading environment for testing TradeMaestro GUI without MT5
"""

import random
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import pandas as pd
# from PySide6.QtCore import QObject, Signal, QTimer  # Disabled for CLI mode

from .logger import Logger


class MockMT5Connector:
    """
    Mock MT5 connector for demo mode
    Simulates trading environment without requiring actual MT5 installation
    """
    
    # Signals for GUI updates (disabled for CLI mode)
    # connection_status_changed = Signal(bool, str)  # connected, status_message
    # account_info_updated = Signal(dict)
    # symbol_info_updated = Signal(str, dict)
    # error_occurred = Signal(str)
    
    def __init__(self, config):
        # super().__init__()  # Disabled for CLI mode
        self.config = config
        self.logger = Logger(__name__)
        
        # Connection state
        self._connected = False
        self._demo_mode = True
        
        # Mock account data
        self._account_info = {
            'login': 12345678,
            'balance': 10000.0,
            'equity': 10000.0,
            'margin': 0.0,
            'free_margin': 10000.0,
            'profit': 0.0,
            'margin_level': 0.0,
            'server': 'Demo-Server',
            'currency': 'USD',
            'name': 'Demo Account',
            'company': 'MetaQuotes Ltd.',
            'leverage': 100
        }
        
        # Mock symbols with realistic data
        self._symbols = {
            'EURUSD': {'bid': 1.0520, 'ask': 1.0523, 'spread': 3, 'digits': 5},
            'GBPUSD': {'bid': 1.2650, 'ask': 1.2653, 'spread': 3, 'digits': 5},
            'USDJPY': {'bid': 149.20, 'ask': 149.23, 'spread': 3, 'digits': 3},
            'USDCHF': {'bid': 0.8890, 'ask': 0.8893, 'spread': 3, 'digits': 5},
            'AUDUSD': {'bid': 0.6420, 'ask': 0.6423, 'spread': 3, 'digits': 5},
            'USDCAD': {'bid': 1.4250, 'ask': 1.4253, 'spread': 3, 'digits': 5}
        }
        
        # Mock positions and orders
        self._positions = []
        self._orders = []
        self._trade_history = []
        
        # Price simulation timer (disabled for CLI mode)
        # self._price_timer = QTimer()
        # self._price_timer.timeout.connect(self._simulate_price_changes)
        self._price_simulation_active = False
        
        self.logger.info("🎭 Mock MT5 connector initialized (Demo Mode)")
    
    def connect(self) -> bool:
        """Simulate MT5 connection"""
        try:
            self.logger.info("🔄 Simulating MT5 connection...")
            time.sleep(1)  # Simulate connection delay
            
            self._connected = True
            # self.connection_status_changed.emit(True, "Connected to Demo Server")
            # self.account_info_updated.emit(self._account_info)
            
            # Start price simulation (simplified for CLI mode)
            # self._price_timer.start(2000)  # Update prices every 2 seconds
            self._price_simulation_active = True
            
            self.logger.info("✅ Mock MT5 connection established")
            return True
            
        except Exception as e:
            self.logger.error(f"Mock connection error: {str(e)}")
            self.error_occurred.emit(f"Mock connection failed: {str(e)}")
            return False
    
    def disconnect(self):
        """Simulate MT5 disconnection"""
        try:
            self._connected = False
            # self._price_timer.stop()
            self._price_simulation_active = False
            # self.connection_status_changed.emit(False, "Disconnected")
            self.logger.info("🔌 Mock MT5 disconnected")
        except Exception as e:
            self.logger.error(f"Mock disconnection error: {str(e)}")
    
    def is_connected(self) -> bool:
        """Check if mock connection is active"""
        return self._connected
    
    def get_account_info(self) -> Dict[str, Any]:
        """Get mock account information"""
        if not self._connected:
            return {}
        
        # Add some random variation to equity
        variation = random.uniform(-50, 50)
        self._account_info['equity'] = max(0, self._account_info['balance'] + variation)
        self._account_info['profit'] = self._account_info['equity'] - self._account_info['balance']
        
        return self._account_info.copy()
    
    def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get mock symbol information"""
        if not self._connected or symbol not in self._symbols:
            return None
            
        return self._symbols[symbol].copy()
    
    def get_tick(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get mock tick data"""
        if not self._connected or symbol not in self._symbols:
            return None
        
        symbol_data = self._symbols[symbol]
        return {
            'time': datetime.now(),
            'bid': symbol_data['bid'],
            'ask': symbol_data['ask'],
            'last': symbol_data['bid'],
            'volume': random.randint(1, 100)
        }
    
    def get_rates(self, symbol: str, timeframe: str, start: int, count: int) -> pd.DataFrame:
        """Generate mock historical rates"""
        if not self._connected or symbol not in self._symbols:
            return pd.DataFrame()
        
        try:
            # Generate mock OHLCV data
            base_price = self._symbols[symbol]['bid']
            dates = pd.date_range(end=datetime.now(), periods=count, freq='1H')
            
            data = []
            price = base_price
            
            for date in dates:
                # Simulate price movement
                change = random.uniform(-0.01, 0.01) * price
                price = max(0.1, price + change)
                
                high = price + random.uniform(0, 0.005) * price
                low = price - random.uniform(0, 0.005) * price
                volume = random.randint(100, 1000)
                
                data.append({
                    'time': date,
                    'open': price,
                    'high': high,
                    'low': low,
                    'close': price,
                    'volume': volume
                })
            
            return pd.DataFrame(data)
            
        except Exception as e:
            self.logger.error(f"Error generating mock rates: {str(e)}")
            return pd.DataFrame()
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """Get mock open positions"""
        return self._positions.copy()
    
    def get_orders(self) -> List[Dict[str, Any]]:
        """Get mock pending orders"""
        return self._orders.copy()
    
    def send_order(self, symbol: str, order_type: str, volume: float, 
                   price: float = None, sl: float = None, tp: float = None,
                   comment: str = "") -> Dict[str, Any]:
        """Simulate order sending"""
        if not self._connected:
            return {"retcode": 10018, "comment": "Not connected"}
        
        try:
            # Simulate order execution
            if order_type in ['BUY', 'SELL']:
                # Market order - add to positions
                current_price = self._symbols[symbol]['bid' if order_type == 'SELL' else 'ask']
                
                position = {
                    'ticket': random.randint(100000, 999999),
                    'symbol': symbol,
                    'type': order_type,
                    'volume': volume,
                    'price_open': current_price,
                    'price_current': current_price,
                    'sl': sl or 0,
                    'tp': tp or 0,
                    'profit': 0.0,
                    'swap': 0.0,
                    'comment': comment,
                    'time': datetime.now()
                }
                
                self._positions.append(position)
                self.logger.info(f"📊 Mock order executed: {symbol} {order_type} {volume}")
                
                return {"retcode": 10009, "comment": "Request completed", "order": position['ticket']}
            
            else:
                # Pending order - add to orders
                order = {
                    'ticket': random.randint(100000, 999999),
                    'symbol': symbol,
                    'type': order_type,
                    'volume': volume,
                    'price_open': price or self._symbols[symbol]['ask'],
                    'sl': sl or 0,
                    'tp': tp or 0,
                    'comment': comment,
                    'time_setup': datetime.now()
                }
                
                self._orders.append(order)
                self.logger.info(f"📋 Mock pending order created: {symbol} {order_type}")
                
                return {"retcode": 10009, "comment": "Request completed", "order": order['ticket']}
                
        except Exception as e:
            self.logger.error(f"Mock order error: {str(e)}")
            return {"retcode": 10013, "comment": f"Invalid request: {str(e)}"}
    
    def close_position(self, ticket: int) -> Dict[str, Any]:
        """Simulate position closing"""
        if not self._connected:
            return {"retcode": 10018, "comment": "Not connected"}
        
        try:
            # Find position
            position = None
            for i, pos in enumerate(self._positions):
                if pos['ticket'] == ticket:
                    position = self._positions.pop(i)
                    break
            
            if not position:
                return {"retcode": 10013, "comment": "Position not found"}
            
            # Calculate profit
            current_price = self._symbols[position['symbol']]['ask' if position['type'] == 'SELL' else 'bid']
            if position['type'] == 'BUY':
                profit = (current_price - position['price_open']) * position['volume'] * 100000
            else:
                profit = (position['price_open'] - current_price) * position['volume'] * 100000
            
            # Add to history
            trade = {
                'ticket': ticket,
                'symbol': position['symbol'],
                'type': position['type'],
                'volume': position['volume'],
                'price_open': position['price_open'],
                'price_close': current_price,
                'profit': profit,
                'time_open': position['time'],
                'time_close': datetime.now(),
                'comment': position['comment']
            }
            
            self._trade_history.append(trade)
            
            # Update account balance
            self._account_info['balance'] += profit
            self._account_info['equity'] = self._account_info['balance']
            
            self.logger.info(f"🔄 Mock position closed: {ticket} Profit: {profit:.2f}")
            # self.account_info_updated.emit(self._account_info)
            
            return {"retcode": 10009, "comment": "Request completed"}
            
        except Exception as e:
            self.logger.error(f"Mock close position error: {str(e)}")
            return {"retcode": 10013, "comment": f"Close failed: {str(e)}"}
    
    def cancel_order(self, ticket: int) -> Dict[str, Any]:
        """Simulate order cancellation"""
        if not self._connected:
            return {"retcode": 10018, "comment": "Not connected"}
        
        try:
            # Find and remove order
            for i, order in enumerate(self._orders):
                if order['ticket'] == ticket:
                    self._orders.pop(i)
                    self.logger.info(f"❌ Mock order cancelled: {ticket}")
                    return {"retcode": 10009, "comment": "Request completed"}
            
            return {"retcode": 10013, "comment": "Order not found"}
            
        except Exception as e:
            self.logger.error(f"Mock cancel order error: {str(e)}")
            return {"retcode": 10013, "comment": f"Cancel failed: {str(e)}"}
    
    def get_history_deals(self, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Get mock trade history"""
        return [trade for trade in self._trade_history 
                if start_date <= trade['time_close'] <= end_date]
    
    def _simulate_price_changes(self):
        """Simulate realistic price movements"""
        try:
            for symbol in self._symbols:
                symbol_data = self._symbols[symbol]
                
                # Random price movement (±0.1%)
                change_pct = random.uniform(-0.001, 0.001)
                
                old_bid = symbol_data['bid']
                new_bid = old_bid * (1 + change_pct)
                
                symbol_data['bid'] = round(new_bid, symbol_data['digits'])
                symbol_data['ask'] = round(new_bid + symbol_data['spread'] * 10**(-symbol_data['digits']), 
                                         symbol_data['digits'])
                
                # Update position profits
                self._update_position_profits(symbol)
                
                # Emit signal for GUI update (disabled for CLI mode)
                # self.symbol_info_updated.emit(symbol, symbol_data.copy())
            
            # Update account equity based on position profits
            total_profit = sum(pos.get('profit', 0) for pos in self._positions)
            self._account_info['equity'] = self._account_info['balance'] + total_profit
            self._account_info['profit'] = total_profit
            # self.account_info_updated.emit(self._account_info)
            
        except Exception as e:
            self.logger.error(f"Price simulation error: {str(e)}")
    
    def _update_position_profits(self, symbol: str):
        """Update profits for positions of given symbol"""
        try:
            symbol_data = self._symbols[symbol]
            current_price = symbol_data['bid']
            
            for position in self._positions:
                if position['symbol'] == symbol:
                    if position['type'] == 'BUY':
                        profit = (current_price - position['price_open']) * position['volume'] * 100000
                    else:  # SELL
                        profit = (position['price_open'] - current_price) * position['volume'] * 100000
                    
                    position['profit'] = round(profit, 2)
                    position['price_current'] = current_price
                    
        except Exception as e:
            self.logger.error(f"Error updating position profits: {str(e)}")