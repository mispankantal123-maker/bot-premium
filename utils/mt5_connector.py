"""
MetaTrader5 Connector for TradeMaestro
Robust MT5 integration with comprehensive error handling and Windows compatibility
"""

import os
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
import pandas as pd

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

# from PySide6.QtCore import QObject, Signal  # Disabled for CLI mode

from .logger import Logger


class MT5Connector:
    """
    MetaTrader5 connection manager with robust error handling
    Provides thread-safe MT5 operations and connection monitoring
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
        self._connection_lock = threading.Lock()
        self._last_connection_attempt = None
        self._connection_retries = 0
        
        # MT5 session info
        self._account_info = {}
        self._symbol_cache = {}
        self._last_tick_cache = {}
        
        # Monitoring
        self._monitor_thread = None
        self._monitoring = False
        
        if not MT5_AVAILABLE:
            self.logger.error("MetaTrader5 module not available. Please install: pip install MetaTrader5")
    
    def connect(self) -> bool:
        """
        Establish connection to MetaTrader5
        
        Returns:
            bool: True if connected successfully, False otherwise
        """
        if not MT5_AVAILABLE:
            self.error_occurred.emit("MetaTrader5 module not installed")
            return False
        
        with self._connection_lock:
            try:
                self.logger.info("🔄 Attempting MT5 connection...")
                
                # Shutdown any existing connection
                if self._connected:
                    self.disconnect()
                
                # Try different initialization methods
                connection_methods = self._get_connection_methods()
                
                for i, (method_name, method_func) in enumerate(connection_methods):
                    self.logger.info(f"🔄 Trying connection method {i+1}: {method_name}")
                    
                    try:
                        result = method_func()
                        if result:
                            self.logger.info(f"✅ Connected using {method_name}")
                            break
                    except Exception as e:
                        self.logger.warning(f"❌ Method {method_name} failed: {str(e)}")
                        continue
                else:
                    # All methods failed
                    error_code = mt5.last_error()
                    error_msg = f"All connection methods failed. Last error: {error_code}"
                    self.logger.error(error_msg)
                    self.error_occurred.emit(error_msg)
                    return False
                
                # Verify connection and get account info
                if not self._verify_connection():
                    self.logger.error("Connection verification failed")
                    return False
                
                self._connected = True
                self._connection_retries = 0
                self._last_connection_attempt = datetime.now()
                
                # Start connection monitoring
                self._start_monitoring()
                
                # Get initial account information
                self._update_account_info()
                
                self.connection_status_changed.emit(True, "Connected to MT5")
                self.logger.info("✅ MT5 connection established successfully")
                
                return True
                
            except Exception as e:
                error_msg = f"Connection failed: {str(e)}"
                self.logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                return False
    
    def disconnect(self) -> bool:
        """
        Disconnect from MetaTrader5
        
        Returns:
            bool: True if disconnected successfully
        """
        with self._connection_lock:
            try:
                self.logger.info("🔄 Disconnecting from MT5...")
                
                # Stop monitoring
                self._stop_monitoring()
                
                # Shutdown MT5 connection
                if MT5_AVAILABLE:
                    mt5.shutdown()
                
                self._connected = False
                self._account_info = {}
                self._symbol_cache = {}
                
                self.connection_status_changed.emit(False, "Disconnected from MT5")
                self.logger.info("✅ Disconnected from MT5 successfully")
                
                return True
                
            except Exception as e:
                error_msg = f"Disconnect error: {str(e)}"
                self.logger.error(error_msg)
                return False
    
    def is_connected(self) -> bool:
        """Check if currently connected to MT5"""
        if not self._connected or not MT5_AVAILABLE:
            return False
        
        try:
            # Quick connection test
            account_info = mt5.account_info()
            return account_info is not None
        except:
            return False
    
    def get_account_info(self) -> Optional[Dict[str, Any]]:
        """
        Get current account information
        
        Returns:
            Dict with account details or None if error
        """
        if not self.is_connected():
            return None
        
        try:
            account_info = mt5.account_info()
            if account_info is None:
                self.logger.warning("Failed to get account info")
                return None
            
            # Convert to dictionary
            account_dict = {
                'login': account_info.login,
                'server': account_info.server,
                'trade_mode': account_info.trade_mode,
                'balance': account_info.balance,
                'equity': account_info.equity,
                'margin': account_info.margin,
                'free_margin': account_info.free_margin,
                'margin_level': account_info.margin_level,
                'profit': account_info.profit,
                'currency': account_info.currency,
                'company': account_info.company,
                'name': account_info.name,
                'leverage': account_info.leverage,
                'trade_allowed': account_info.trade_allowed,
                'trade_expert': account_info.trade_expert,
                'timestamp': datetime.now()
            }
            
            self._account_info = account_dict
            self.account_info_updated.emit(account_dict)
            
            return account_dict
            
        except Exception as e:
            self.logger.error(f"Error getting account info: {str(e)}")
            return None
    
    def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get symbol information
        
        Args:
            symbol: Trading symbol (e.g., 'EURUSD')
            
        Returns:
            Dict with symbol details or None if error
        """
        if not self.is_connected():
            return None
        
        # Check cache first
        if symbol in self._symbol_cache:
            cache_time = self._symbol_cache[symbol].get('_cache_time')
            if cache_time and (datetime.now() - cache_time).seconds < 300:  # 5 min cache
                return self._symbol_cache[symbol]
        
        try:
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                self.logger.warning(f"Symbol {symbol} not found")
                return None
            
            # Convert to dictionary
            symbol_dict = {
                'name': symbol_info.name,
                'basis': symbol_info.basis,
                'category': symbol_info.category,
                'currency_base': symbol_info.currency_base,
                'currency_profit': symbol_info.currency_profit,
                'currency_margin': symbol_info.currency_margin,
                'digits': symbol_info.digits,
                'trade_tick_value': symbol_info.trade_tick_value,
                'trade_tick_value_profit': symbol_info.trade_tick_value_profit,
                'trade_tick_value_loss': symbol_info.trade_tick_value_loss,
                'trade_tick_size': symbol_info.trade_tick_size,
                'trade_contract_size': symbol_info.trade_contract_size,
                'trade_execution': symbol_info.trade_execution,
                'trade_stops_level': symbol_info.trade_stops_level,
                'trade_freeze_level': symbol_info.trade_freeze_level,
                'trade_mode': symbol_info.trade_mode,
                'volume_min': symbol_info.volume_min,
                'volume_max': symbol_info.volume_max,
                'volume_step': symbol_info.volume_step,
                'volume_limit': symbol_info.volume_limit,
                'margin_initial': symbol_info.margin_initial,
                'margin_maintenance': symbol_info.margin_maintenance,
                'margin_long': symbol_info.margin_long,
                'margin_short': symbol_info.margin_short,
                'point': symbol_info.point,
                'spread': symbol_info.spread,
                'trade_allowed': symbol_info.trade_allowed,
                '_cache_time': datetime.now()
            }
            
            self._symbol_cache[symbol] = symbol_dict
            self.symbol_info_updated.emit(symbol, symbol_dict)
            
            return symbol_dict
            
        except Exception as e:
            self.logger.error(f"Error getting symbol info for {symbol}: {str(e)}")
            return None
    
    def get_symbol_tick(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get current tick data for symbol
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Dict with tick data or None if error
        """
        if not self.is_connected():
            return None
        
        try:
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return None
            
            tick_dict = {
                'time': datetime.fromtimestamp(tick.time),
                'bid': tick.bid,
                'ask': tick.ask,
                'last': tick.last,
                'volume': tick.volume,
                'spread': tick.ask - tick.bid,
                'symbol': symbol
            }
            
            self._last_tick_cache[symbol] = tick_dict
            return tick_dict
            
        except Exception as e:
            self.logger.error(f"Error getting tick for {symbol}: {str(e)}")
            return None
    
    def get_positions(self, symbol: str = None) -> List[Dict[str, Any]]:
        """
        Get current open positions
        
        Args:
            symbol: Filter by symbol (optional)
            
        Returns:
            List of position dictionaries
        """
        if not self.is_connected():
            return []
        
        try:
            if symbol:
                positions = mt5.positions_get(symbol=symbol)
            else:
                positions = mt5.positions_get()
            
            if positions is None:
                return []
            
            position_list = []
            for pos in positions:
                position_dict = {
                    'ticket': pos.ticket,
                    'time': datetime.fromtimestamp(pos.time),
                    'type': pos.type,
                    'magic': pos.magic,
                    'identifier': pos.identifier,
                    'reason': pos.reason,
                    'volume': pos.volume,
                    'price_open': pos.price_open,
                    'sl': pos.sl,
                    'tp': pos.tp,
                    'price_current': pos.price_current,
                    'swap': pos.swap,
                    'profit': pos.profit,
                    'symbol': pos.symbol,
                    'comment': pos.comment,
                }
                position_list.append(position_dict)
            
            return position_list
            
        except Exception as e:
            self.logger.error(f"Error getting positions: {str(e)}")
            return []
    
    def get_orders(self, symbol: str = None) -> List[Dict[str, Any]]:
        """
        Get current pending orders
        
        Args:
            symbol: Filter by symbol (optional)
            
        Returns:
            List of order dictionaries
        """
        if not self.is_connected():
            return []
        
        try:
            if symbol:
                orders = mt5.orders_get(symbol=symbol)
            else:
                orders = mt5.orders_get()
            
            if orders is None:
                return []
            
            order_list = []
            for order in orders:
                order_dict = {
                    'ticket': order.ticket,
                    'time_setup': datetime.fromtimestamp(order.time_setup),
                    'time_expiration': datetime.fromtimestamp(order.time_expiration) if order.time_expiration > 0 else None,
                    'type': order.type,
                    'state': order.state,
                    'magic': order.magic,
                    'volume_initial': order.volume_initial,
                    'volume_current': order.volume_current,
                    'price_open': order.price_open,
                    'sl': order.sl,
                    'tp': order.tp,
                    'price_current': order.price_current,
                    'symbol': order.symbol,
                    'comment': order.comment,
                }
                order_list.append(order_dict)
            
            return order_list
            
        except Exception as e:
            self.logger.error(f"Error getting orders: {str(e)}")
            return []
    
    def send_order(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send trading order to MT5
        
        Args:
            request: Order request dictionary
            
        Returns:
            Result dictionary with success status and details
        """
        if not self.is_connected():
            return {'success': False, 'error': 'Not connected to MT5'}
        
        try:
            self.logger.info(f"📤 Sending order: {request}")
            
            # Validate request
            validation_result = self._validate_order_request(request)
            if not validation_result['valid']:
                return {'success': False, 'error': validation_result['error']}
            
            # Send order
            result = mt5.order_send(request)
            
            if result is None:
                error_code = mt5.last_error()
                error_msg = f"Order send failed. Error code: {error_code}"
                self.logger.error(error_msg)
                return {'success': False, 'error': error_msg}
            
            # Process result
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                success_msg = f"✅ Order executed successfully. Ticket: {result.order}"
                self.logger.info(success_msg)
                
                return {
                    'success': True,
                    'ticket': result.order,
                    'retcode': result.retcode,
                    'deal': result.deal,
                    'order': result.order,
                    'volume': result.volume,
                    'price': result.price,
                    'bid': result.bid,
                    'ask': result.ask,
                    'comment': result.comment,
                    'request_id': result.request_id
                }
            else:
                error_msg = f"Order failed. Return code: {result.retcode}, Comment: {result.comment}"
                self.logger.error(error_msg)
                
                return {
                    'success': False,
                    'error': error_msg,
                    'retcode': result.retcode,
                    'comment': result.comment
                }
                
        except Exception as e:
            error_msg = f"Order send exception: {str(e)}"
            self.logger.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    def close_position(self, ticket: int) -> Dict[str, Any]:
        """
        Close an open position
        
        Args:
            ticket: Position ticket number
            
        Returns:
            Result dictionary
        """
        if not self.is_connected():
            return {'success': False, 'error': 'Not connected to MT5'}
        
        try:
            # Get position info
            position = mt5.positions_get(ticket=ticket)
            if not position:
                return {'success': False, 'error': f'Position {ticket} not found'}
            
            pos = position[0]
            
            # Determine close order type
            if pos.type == mt5.ORDER_TYPE_BUY:
                order_type = mt5.ORDER_TYPE_SELL
                price = mt5.symbol_info_tick(pos.symbol).bid
            else:
                order_type = mt5.ORDER_TYPE_BUY
                price = mt5.symbol_info_tick(pos.symbol).ask
            
            # Create close request
            close_request = {
                'action': mt5.TRADE_ACTION_DEAL,
                'symbol': pos.symbol,
                'volume': pos.volume,
                'type': order_type,
                'position': ticket,
                'price': price,
                'deviation': 20,
                'magic': pos.magic,
                'comment': f'Close position {ticket}',
                'type_time': mt5.ORDER_TIME_GTC,
                'type_filling': mt5.ORDER_FILLING_IOC,
            }
            
            return self.send_order(close_request)
            
        except Exception as e:
            error_msg = f"Error closing position {ticket}: {str(e)}"
            self.logger.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    def _get_connection_methods(self) -> List[Tuple[str, callable]]:
        """Get list of connection methods to try"""
        methods = []
        
        # Method 1: Auto-detect with environment credentials
        if self.config.MT5_LOGIN and self.config.MT5_PASSWORD and self.config.MT5_SERVER:
            methods.append((
                "Credentials from config",
                lambda: mt5.initialize(
                    login=int(self.config.MT5_LOGIN),
                    password=self.config.MT5_PASSWORD,
                    server=self.config.MT5_SERVER
                )
            ))
        
        # Method 2: Auto-detect current session
        methods.append((
            "Auto-detect current session",
            lambda: mt5.initialize()
        ))
        
        # Method 3: Try common MT5 paths
        for path in self.config.get_mt5_paths():
            if Path(path).exists():
                methods.append((
                    f"Path: {path}",
                    lambda p=path: mt5.initialize(path=p)
                ))
        
        return methods
    
    def _verify_connection(self) -> bool:
        """Verify MT5 connection is working"""
        try:
            # Test basic operations
            version = mt5.version()
            account = mt5.account_info()
            terminal = mt5.terminal_info()
            
            if not all([version, account, terminal]):
                return False
            
            self.logger.info(f"📊 MT5 Version: {version}")
            self.logger.info(f"👤 Account: {account.login} on {account.server}")
            self.logger.info(f"💰 Balance: {account.balance} {account.currency}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Connection verification failed: {str(e)}")
            return False
    
    def _validate_order_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Validate order request parameters"""
        try:
            # Required fields
            required_fields = ['action', 'symbol', 'volume', 'type']
            for field in required_fields:
                if field not in request:
                    return {'valid': False, 'error': f'Missing required field: {field}'}
            
            # Validate symbol
            symbol_info = self.get_symbol_info(request['symbol'])
            if not symbol_info:
                return {'valid': False, 'error': f'Invalid symbol: {request["symbol"]}'}
            
            # Validate volume
            volume = request['volume']
            if volume < symbol_info['volume_min'] or volume > symbol_info['volume_max']:
                return {
                    'valid': False, 
                    'error': f'Volume {volume} outside allowed range [{symbol_info["volume_min"]}, {symbol_info["volume_max"]}]'
                }
            
            # Check if trading is allowed
            if not symbol_info['trade_allowed']:
                return {'valid': False, 'error': f'Trading not allowed for {request["symbol"]}'}
            
            return {'valid': True, 'error': None}
            
        except Exception as e:
            return {'valid': False, 'error': f'Validation error: {str(e)}'}
    
    def _update_account_info(self):
        """Update account information periodically"""
        try:
            account_info = self.get_account_info()
            if account_info:
                self.account_info_updated.emit(account_info)
        except Exception as e:
            self.logger.error(f"Error updating account info: {str(e)}")
    
    def _start_monitoring(self):
        """Start connection monitoring thread"""
        if self._monitoring:
            return
        
        self._monitoring = True
        self._monitor_thread = threading.Thread(target=self._monitor_connection, daemon=True)
        self._monitor_thread.start()
        self.logger.info("📡 Started connection monitoring")
    
    def _stop_monitoring(self):
        """Stop connection monitoring"""
        self._monitoring = False
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2.0)
        self.logger.info("📡 Stopped connection monitoring")
    
    def _monitor_connection(self):
        """Monitor connection health in background thread"""
        while self._monitoring:
            try:
                if self._connected:
                    # Check connection health
                    if not self.is_connected():
                        self.logger.warning("🔌 Connection lost, attempting reconnection...")
                        self._connected = False
                        self.connection_status_changed.emit(False, "Connection lost")
                        
                        # Attempt reconnection
                        if self.connect():
                            self.logger.info("🔌 Reconnection successful")
                        else:
                            self.logger.error("🔌 Reconnection failed")
                    else:
                        # Update account info periodically
                        self._update_account_info()
                
                time.sleep(10)  # Check every 10 seconds
                
            except Exception as e:
                self.logger.error(f"Monitoring error: {str(e)}")
                time.sleep(5)
    
    def get_terminal_info(self) -> Optional[Dict[str, Any]]:
        """Get MT5 terminal information"""
        if not self.is_connected():
            return None
        
        try:
            terminal = mt5.terminal_info()
            if terminal is None:
                return None
            
            return {
                'community_account': terminal.community_account,
                'community_connection': terminal.community_connection,
                'connected': terminal.connected,
                'dlls_allowed': terminal.dlls_allowed,
                'trade_allowed': terminal.trade_allowed,
                'tradeapi_disabled': terminal.tradeapi_disabled,
                'email_enabled': terminal.email_enabled,
                'ftp_enabled': terminal.ftp_enabled,
                'notifications_enabled': terminal.notifications_enabled,
                'mqid': terminal.mqid,
                'build': terminal.build,
                'maxbars': terminal.maxbars,
                'codepage': terminal.codepage,
                'ping_last': terminal.ping_last,
                'community_balance': terminal.community_balance,
                'retransmission': terminal.retransmission,
                'company': terminal.company,
                'name': terminal.name,
                'language': terminal.language,
                'path': terminal.path
            }
            
        except Exception as e:
            self.logger.error(f"Error getting terminal info: {str(e)}")
            return None
