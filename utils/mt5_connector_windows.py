"""
Windows-optimized MT5 Connector with robust error handling
Handles MetaTrader5 connection with automatic reconnection and fallback
"""

import time
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import traceback

# Safe MT5 import with fallback
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    print("⚠️ MetaTrader5 library not available, using mock mode")

from .logger import Logger


class WindowsMT5Connector:
    """
    Windows-optimized MT5 connector with comprehensive error handling
    Automatically handles reconnection and provides fallback mechanisms
    """
    
    def __init__(self, config):
        self.config = config
        self.logger = Logger(__name__)
        
        # Connection state
        self._connected = False
        self._connection_lock = threading.Lock()
        self._last_connection_attempt = None
        self._connection_failures = 0
        self._max_failures = config.get("MT5_RETRY_COUNT", 3)
        
        # Account information
        self._account_info = {}
        self._last_account_update = None
        
        # Connection monitoring
        self._monitor_thread = None
        self._monitoring = False
        self._shutdown_event = threading.Event()
        
        # Trading state
        self._positions = []
        self._orders = []
        self._last_data_update = None
        
        self.logger.info("🔌 Windows MT5 Connector initialized")
    
    def is_mt5_available(self) -> bool:
        """Check if MT5 library is available"""
        return MT5_AVAILABLE
    
    def connect(self) -> bool:
        """Establish connection to MetaTrader5"""
        with self._connection_lock:
            try:
                self.logger.info("🔄 Connecting to MetaTrader5...")
                
                if not MT5_AVAILABLE:
                    self.logger.error("❌ MetaTrader5 library not available")
                    return False
                
                # Initialize MT5
                if not mt5.initialize():
                    error_code = mt5.last_error()
                    self.logger.error(f"❌ MT5 initialization failed: {error_code}")
                    return False
                
                # Get credentials
                credentials = self.config.get_mt5_credentials()
                
                # Login if credentials provided
                if all(credentials.values()):
                    login_result = mt5.login(
                        login=int(credentials["login"]),
                        password=credentials["password"],
                        server=credentials["server"],
                        timeout=self.config.get("MT5_TIMEOUT", 60000)
                    )
                    
                    if not login_result:
                        error_code = mt5.last_error()
                        self.logger.error(f"❌ MT5 login failed: {error_code}")
                        mt5.shutdown()
                        return False
                    
                    self.logger.info(f"✅ Logged in to MT5 server: {credentials['server']}")
                else:
                    self.logger.info("ℹ️ No credentials provided, using existing MT5 connection")
                
                # Verify connection
                account_info = mt5.account_info()
                if account_info is None:
                    self.logger.error("❌ Failed to get account information")
                    mt5.shutdown()
                    return False
                
                # Store account info
                self._account_info = account_info._asdict()
                self._connected = True
                self._connection_failures = 0
                self._last_connection_attempt = datetime.now()
                
                # Start monitoring
                self._start_connection_monitoring()
                
                self.logger.info(f"✅ MT5 connected successfully")
                self.logger.info(f"📊 Account: {self._account_info.get('login', 'Unknown')}")
                self.logger.info(f"💰 Balance: ${self._account_info.get('balance', 0):.2f}")
                
                return True
                
            except Exception as e:
                self.logger.error(f"❌ MT5 connection error: {e}")
                traceback.print_exc()
                self._connection_failures += 1
                return False
    
    def disconnect(self):
        """Disconnect from MetaTrader5"""
        with self._connection_lock:
            try:
                self.logger.info("🔌 Disconnecting from MT5...")
                
                # Stop monitoring
                self._shutdown_event.set()
                self._monitoring = False
                
                if self._monitor_thread and self._monitor_thread.is_alive():
                    self._monitor_thread.join(timeout=5)
                
                # Shutdown MT5
                if MT5_AVAILABLE and self._connected:
                    mt5.shutdown()
                
                self._connected = False
                self.logger.info("✅ MT5 disconnected successfully")
                
            except Exception as e:
                self.logger.error(f"❌ Disconnect error: {e}")
    
    def is_connected(self) -> bool:
        """Check if connected to MT5"""
        if not self._connected:
            return False
        
        try:
            # Quick connection test
            if MT5_AVAILABLE:
                account_info = mt5.account_info()
                return account_info is not None
            return False
        except Exception:
            return False
    
    def reconnect(self) -> bool:
        """Attempt to reconnect to MT5"""
        self.logger.info("🔄 Attempting to reconnect...")
        
        # Disconnect first
        self.disconnect()
        
        # Wait before reconnecting
        time.sleep(self.config.get("MT5_RETRY_DELAY", 5))
        
        # Attempt connection
        return self.connect()
    
    def _start_connection_monitoring(self):
        """Start connection monitoring thread"""
        if self._monitoring:
            return
        
        def monitor_connection():
            self._monitoring = True
            self.logger.info("👁️ Connection monitoring started")
            
            while not self._shutdown_event.is_set():
                try:
                    if not self.is_connected():
                        self.logger.warning("⚠️ Connection lost, attempting reconnect...")
                        
                        if self._connection_failures < self._max_failures:
                            if self.reconnect():
                                self.logger.info("✅ Reconnection successful")
                            else:
                                self._connection_failures += 1
                                self.logger.error(f"❌ Reconnection failed ({self._connection_failures}/{self._max_failures})")
                        else:
                            self.logger.error("❌ Max reconnection attempts reached")
                            break
                    
                    # Update account info periodically
                    self._update_account_info()
                    
                    # Sleep before next check
                    self._shutdown_event.wait(timeout=30)  # Check every 30 seconds
                    
                except Exception as e:
                    self.logger.error(f"❌ Connection monitoring error: {e}")
                    time.sleep(60)  # Wait longer on error
            
            self._monitoring = False
            self.logger.info("👁️ Connection monitoring stopped")
        
        self._monitor_thread = threading.Thread(target=monitor_connection, daemon=True)
        self._monitor_thread.start()
    
    def _update_account_info(self):
        """Update account information"""
        try:
            if not MT5_AVAILABLE or not self._connected:
                return
            
            account_info = mt5.account_info()
            if account_info:
                self._account_info = account_info._asdict()
                self._last_account_update = datetime.now()
            
        except Exception as e:
            self.logger.error(f"❌ Account info update error: {e}")
    
    def get_account_info(self) -> Dict[str, Any]:
        """Get current account information"""
        try:
            if not self._connected:
                return {}
            
            # Update if stale
            if (not self._last_account_update or 
                (datetime.now() - self._last_account_update).seconds > 30):
                self._update_account_info()
            
            return self._account_info.copy()
            
        except Exception as e:
            self.logger.error(f"❌ Get account info error: {e}")
            return {}
    
    def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get symbol information"""
        try:
            if not MT5_AVAILABLE or not self._connected:
                return None
            
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info:
                return symbol_info._asdict()
            
            return None
            
        except Exception as e:
            self.logger.error(f"❌ Get symbol info error for {symbol}: {e}")
            return None
    
    def get_tick(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get latest tick for symbol"""
        try:
            if not MT5_AVAILABLE or not self._connected:
                return None
            
            tick = mt5.symbol_info_tick(symbol)
            if tick:
                return tick._asdict()
            
            return None
            
        except Exception as e:
            self.logger.error(f"❌ Get tick error for {symbol}: {e}")
            return None
    
    def get_rates(self, symbol: str, timeframe, count: int = 100) -> Optional[List[Dict]]:
        """Get historical rates"""
        try:
            if not MT5_AVAILABLE or not self._connected:
                return None
            
            # Convert timeframe string to MT5 constant
            timeframe_map = {
                'M1': mt5.TIMEFRAME_M1,
                'M5': mt5.TIMEFRAME_M5,
                'M15': mt5.TIMEFRAME_M15,
                'M30': mt5.TIMEFRAME_M30,
                'H1': mt5.TIMEFRAME_H1,
                'H4': mt5.TIMEFRAME_H4,
                'D1': mt5.TIMEFRAME_D1
            }
            
            mt5_timeframe = timeframe_map.get(timeframe, mt5.TIMEFRAME_M15)
            
            rates = mt5.copy_rates_from_pos(symbol, mt5_timeframe, 0, count)
            if rates is not None:
                return [dict(rate) for rate in rates]
            
            return None
            
        except Exception as e:
            self.logger.error(f"❌ Get rates error for {symbol}: {e}")
            return None
    
    def place_order(self, symbol: str, order_type: str, volume: float, 
                   price: float = None, stop_loss: float = None, 
                   take_profit: float = None, comment: str = "") -> Optional[Dict[str, Any]]:
        """Place trading order"""
        try:
            if not MT5_AVAILABLE or not self._connected:
                self.logger.error("❌ Cannot place order: not connected")
                return None
            
            # Get current price if not provided
            if price is None:
                tick = self.get_tick(symbol)
                if not tick:
                    self.logger.error(f"❌ Cannot get price for {symbol}")
                    return None
                
                price = tick['ask'] if order_type.startswith('BUY') else tick['bid']
            
            # Build order request
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": getattr(mt5, f"ORDER_TYPE_{order_type}"),
                "price": price,
                "deviation": 20,
                "magic": 123456,
                "comment": comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            # Add stop loss and take profit
            if stop_loss:
                request["sl"] = stop_loss
            if take_profit:
                request["tp"] = take_profit
            
            # Send order
            result = mt5.order_send(request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                self.logger.info(f"✅ Order placed: {symbol} {order_type} {volume}")
                return result._asdict()
            else:
                error_code = result.retcode if result else "Unknown error"
                self.logger.error(f"❌ Order failed: {error_code}")
                return None
            
        except Exception as e:
            self.logger.error(f"❌ Place order error: {e}")
            traceback.print_exc()
            return None
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """Get current positions"""
        try:
            if not MT5_AVAILABLE or not self._connected:
                return []
            
            positions = mt5.positions_get()
            if positions:
                return [pos._asdict() for pos in positions]
            
            return []
            
        except Exception as e:
            self.logger.error(f"❌ Get positions error: {e}")
            return []
    
    def close_position(self, ticket: int) -> bool:
        """Close position by ticket"""
        try:
            if not MT5_AVAILABLE or not self._connected:
                return False
            
            positions = mt5.positions_get(ticket=ticket)
            if not positions:
                self.logger.error(f"❌ Position {ticket} not found")
                return False
            
            position = positions[0]
            
            # Build close request
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": position.symbol,
                "volume": position.volume,
                "type": mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
                "position": ticket,
                "price": mt5.symbol_info_tick(position.symbol).bid if position.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(position.symbol).ask,
                "deviation": 20,
                "magic": 123456,
                "comment": "Close position",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            result = mt5.order_send(request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                self.logger.info(f"✅ Position closed: {ticket}")
                return True
            else:
                error_code = result.retcode if result else "Unknown error"
                self.logger.error(f"❌ Close position failed: {error_code}")
                return False
            
        except Exception as e:
            self.logger.error(f"❌ Close position error: {e}")
            return False
    
    def get_connection_status(self) -> Dict[str, Any]:
        """Get detailed connection status"""
        return {
            "connected": self._connected,
            "mt5_available": MT5_AVAILABLE,
            "connection_failures": self._connection_failures,
            "max_failures": self._max_failures,
            "last_connection_attempt": self._last_connection_attempt,
            "monitoring": self._monitoring,
            "account_info_updated": self._last_account_update
        }