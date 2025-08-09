"""
Order Management System for TradeMaestro
Handles order execution, position management, and trade tracking
"""

import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import threading
from enum import Enum

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

# from PySide6.QtCore import QObject, Signal  # Disabled for CLI mode

from .logger import Logger


class OrderType(Enum):
    """Order types"""
    BUY = "BUY"
    SELL = "SELL"
    BUY_LIMIT = "BUY_LIMIT"
    SELL_LIMIT = "SELL_LIMIT"
    BUY_STOP = "BUY_STOP"
    SELL_STOP = "SELL_STOP"


class OrderStatus(Enum):
    """Order status"""
    PENDING = "PENDING"
    EXECUTED = "EXECUTED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"


class OrderManager:
    """
    Comprehensive order management system with risk controls
    Handles all trading operations and position tracking
    """
    
    # Signals for order updates (disabled for CLI mode)
    # order_placed = Signal(dict)  # order_info
    # order_executed = Signal(dict)  # execution_info
    # order_failed = Signal(str, str)  # reason, details
    # position_opened = Signal(dict)  # position_info
    # position_closed = Signal(dict)  # close_info
    # trade_completed = Signal(dict)  # trade_summary
    
    def __init__(self, mt5_connector, config):
        # super().__init__()  # Disabled for CLI mode
        self.mt5_connector = mt5_connector
        self.config = config
        self.logger = Logger(__name__)
        
        # Order tracking
        self._active_orders = {}
        self._order_history = []
        self._position_tracker = {}
        self._trade_lock = threading.Lock()
        
        # Risk management
        self.max_positions = getattr(config, 'MAX_POSITIONS', 10)
        self.max_risk_per_trade = getattr(config, 'MAX_RISK_PER_TRADE', 0.02)
        self.max_daily_loss = getattr(config, 'MAX_DAILY_LOSS', 0.05)
        self.default_deviation = 20  # Price deviation in points
        self.max_slippage = 50  # Maximum acceptable slippage
        
        # Performance tracking
        self._daily_trades = 0
        self._daily_profit = 0.0
        self._session_start_balance = 0.0
        
        # Magic number for EA identification
        self.magic_number = 123456
        
        # Position monitoring
        self._monitor_thread = None
        self._monitoring = False
    
    def place_buy_order(self, symbol: str, volume: float, stop_loss: float = None,
                       take_profit: float = None, comment: str = "", 
                       order_type: OrderType = OrderType.BUY, price: float = None) -> Dict[str, Any]:
        """
        Place a buy order
        
        Args:
            symbol: Trading symbol
            volume: Order volume (lot size)
            stop_loss: Stop loss price (optional)
            take_profit: Take profit price (optional)
            comment: Order comment
            order_type: Type of buy order
            price: Limit/stop price for pending orders
            
        Returns:
            Dict with order result
        """
        try:
            with self._trade_lock:
                self.logger.info(f"📈 Placing BUY order: {volume} {symbol}")
                
                # Pre-execution checks
                if not self._pre_order_checks(symbol, volume):
                    return {'success': False, 'error': 'Pre-order checks failed'}
                
                # Get current price for market orders
                if order_type == OrderType.BUY and price is None:
                    tick = self.mt5_connector.get_symbol_tick(symbol)
                    if not tick:
                        return {'success': False, 'error': 'Cannot get current price'}
                    price = tick['ask']
                
                # Create order request
                request = self._create_order_request(
                    symbol, volume, order_type, price, stop_loss, take_profit, comment
                )
                
                # Execute order
                result = self._execute_order(request)
                
                # Process result
                if result['success']:
                    self._post_order_success(result, symbol, volume, order_type, comment)
                else:
                    self._post_order_failure(result, symbol, volume, order_type)
                
                return result
                
        except Exception as e:
            error_msg = f"Error placing buy order: {str(e)}"
            self.logger.error(error_msg)
            self.order_failed.emit(error_msg, str(e))
            return {'success': False, 'error': error_msg}
    
    def place_sell_order(self, symbol: str, volume: float, stop_loss: float = None,
                        take_profit: float = None, comment: str = "",
                        order_type: OrderType = OrderType.SELL, price: float = None) -> Dict[str, Any]:
        """
        Place a sell order
        
        Args:
            symbol: Trading symbol
            volume: Order volume (lot size)
            stop_loss: Stop loss price (optional)
            take_profit: Take profit price (optional)
            comment: Order comment
            order_type: Type of sell order
            price: Limit/stop price for pending orders
            
        Returns:
            Dict with order result
        """
        try:
            with self._trade_lock:
                self.logger.info(f"📉 Placing SELL order: {volume} {symbol}")
                
                # Pre-execution checks
                if not self._pre_order_checks(symbol, volume):
                    return {'success': False, 'error': 'Pre-order checks failed'}
                
                # Get current price for market orders
                if order_type == OrderType.SELL and price is None:
                    tick = self.mt5_connector.get_symbol_tick(symbol)
                    if not tick:
                        return {'success': False, 'error': 'Cannot get current price'}
                    price = tick['bid']
                
                # Create order request
                request = self._create_order_request(
                    symbol, volume, order_type, price, stop_loss, take_profit, comment
                )
                
                # Execute order
                result = self._execute_order(request)
                
                # Process result
                if result['success']:
                    self._post_order_success(result, symbol, volume, order_type, comment)
                else:
                    self._post_order_failure(result, symbol, volume, order_type)
                
                return result
                
        except Exception as e:
            error_msg = f"Error placing sell order: {str(e)}"
            self.logger.error(error_msg)
            self.order_failed.emit(error_msg, str(e))
            return {'success': False, 'error': error_msg}
    
    def close_position(self, ticket: int, volume: float = None, comment: str = "Close position") -> Dict[str, Any]:
        """
        Close an open position
        
        Args:
            ticket: Position ticket number
            volume: Partial close volume (None for full close)
            comment: Close comment
            
        Returns:
            Dict with close result
        """
        try:
            with self._trade_lock:
                self.logger.info(f"🔒 Closing position: {ticket}")
                
                # Get position info
                positions = self.mt5_connector.get_positions()
                position = None
                
                for pos in positions:
                    if pos['ticket'] == ticket:
                        position = pos
                        break
                
                if not position:
                    return {'success': False, 'error': f'Position {ticket} not found'}
                
                # Determine close parameters
                symbol = position['symbol']
                pos_volume = volume or position['volume']
                
                # Get current price
                tick = self.mt5_connector.get_symbol_tick(symbol)
                if not tick:
                    return {'success': False, 'error': 'Cannot get current price'}
                
                # Determine close order type and price
                if position['type'] == 0:  # Buy position
                    close_type = mt5.ORDER_TYPE_SELL
                    close_price = tick['bid']
                else:  # Sell position
                    close_type = mt5.ORDER_TYPE_BUY
                    close_price = tick['ask']
                
                # Create close request
                close_request = {
                    'action': mt5.TRADE_ACTION_DEAL,
                    'symbol': symbol,
                    'volume': pos_volume,
                    'type': close_type,
                    'position': ticket,
                    'price': close_price,
                    'deviation': self.default_deviation,
                    'magic': self.magic_number,
                    'comment': comment,
                    'type_time': mt5.ORDER_TIME_GTC,
                    'type_filling': mt5.ORDER_FILLING_IOC,
                }
                
                # Execute close order
                result = self.mt5_connector.send_order(close_request)
                
                if result['success']:
                    self.logger.info(f"✅ Position {ticket} closed successfully")
                    
                    # Calculate profit/loss
                    close_profit = self._calculate_close_profit(position, close_price, pos_volume)
                    
                    # Update tracking
                    self._update_position_tracking(ticket, 'CLOSED', close_profit)
                    
                    # Emit signals
                    close_info = {
                        'ticket': ticket,
                        'symbol': symbol,
                        'volume': pos_volume,
                        'close_price': close_price,
                        'profit': close_profit,
                        'close_time': datetime.now(),
                        'comment': comment
                    }
                    
                    self.position_closed.emit(close_info)
                    
                    # Trade completed signal
                    trade_summary = {
                        'ticket': ticket,
                        'symbol': symbol,
                        'type': 'BUY' if position['type'] == 0 else 'SELL',
                        'volume': position['volume'],
                        'open_price': position['price_open'],
                        'close_price': close_price,
                        'profit': close_profit,
                        'duration': datetime.now() - position.get('time', datetime.now()),
                        'status': 'COMPLETED'
                    }
                    
                    self.trade_completed.emit(trade_summary)
                    
                else:
                    self.logger.error(f"❌ Failed to close position {ticket}: {result.get('error')}")
                
                return result
                
        except Exception as e:
            error_msg = f"Error closing position {ticket}: {str(e)}"
            self.logger.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    def cancel_order(self, ticket: int) -> Dict[str, Any]:
        """
        Cancel a pending order
        
        Args:
            ticket: Order ticket number
            
        Returns:
            Dict with cancellation result
        """
        try:
            with self._trade_lock:
                self.logger.info(f"❌ Cancelling order: {ticket}")
                
                # Create cancel request
                cancel_request = {
                    'action': mt5.TRADE_ACTION_REMOVE,
                    'order': ticket,
                }
                
                result = self.mt5_connector.send_order(cancel_request)
                
                if result['success']:
                    self.logger.info(f"✅ Order {ticket} cancelled successfully")
                    self._update_order_tracking(ticket, 'CANCELLED')
                else:
                    self.logger.error(f"❌ Failed to cancel order {ticket}: {result.get('error')}")
                
                return result
                
        except Exception as e:
            error_msg = f"Error cancelling order {ticket}: {str(e)}"
            self.logger.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    def modify_position(self, ticket: int, stop_loss: float = None, 
                       take_profit: float = None) -> Dict[str, Any]:
        """
        Modify stop loss and/or take profit of an open position
        
        Args:
            ticket: Position ticket number
            stop_loss: New stop loss price (None to keep current)
            take_profit: New take profit price (None to keep current)
            
        Returns:
            Dict with modification result
        """
        try:
            with self._trade_lock:
                self.logger.info(f"✏️ Modifying position: {ticket}")
                
                # Get position info
                positions = self.mt5_connector.get_positions()
                position = None
                
                for pos in positions:
                    if pos['ticket'] == ticket:
                        position = pos
                        break
                
                if not position:
                    return {'success': False, 'error': f'Position {ticket} not found'}
                
                # Use current values if not specified
                new_sl = stop_loss if stop_loss is not None else position['sl']
                new_tp = take_profit if take_profit is not None else position['tp']
                
                # Create modification request
                modify_request = {
                    'action': mt5.TRADE_ACTION_SLTP,
                    'symbol': position['symbol'],
                    'position': ticket,
                    'sl': new_sl,
                    'tp': new_tp,
                    'magic': self.magic_number,
                    'comment': f'Modify SL/TP {ticket}'
                }
                
                result = self.mt5_connector.send_order(modify_request)
                
                if result['success']:
                    self.logger.info(f"✅ Position {ticket} modified: SL={new_sl}, TP={new_tp}")
                else:
                    self.logger.error(f"❌ Failed to modify position {ticket}: {result.get('error')}")
                
                return result
                
        except Exception as e:
            error_msg = f"Error modifying position {ticket}: {str(e)}"
            self.logger.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    def close_all_positions(self, symbol: str = None) -> Dict[str, Any]:
        """
        Close all open positions
        
        Args:
            symbol: Close positions for specific symbol only (None for all)
            
        Returns:
            Dict with results summary
        """
        try:
            self.logger.info(f"🔒 Closing all positions" + (f" for {symbol}" if symbol else ""))
            
            positions = self.mt5_connector.get_positions(symbol)
            if not positions:
                return {'success': True, 'message': 'No positions to close', 'closed': 0}
            
            results = []
            successful_closes = 0
            
            for position in positions:
                result = self.close_position(position['ticket'])
                results.append({
                    'ticket': position['ticket'],
                    'symbol': position['symbol'],
                    'result': result
                })
                
                if result['success']:
                    successful_closes += 1
                
                # Small delay between closes
                time.sleep(0.1)
            
            summary = {
                'success': True,
                'total_positions': len(positions),
                'successful_closes': successful_closes,
                'failed_closes': len(positions) - successful_closes,
                'results': results
            }
            
            self.logger.info(f"✅ Closed {successful_closes}/{len(positions)} positions")
            return summary
            
        except Exception as e:
            error_msg = f"Error closing all positions: {str(e)}"
            self.logger.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    def get_position_summary(self) -> Dict[str, Any]:
        """
        Get summary of current positions
        
        Returns:
            Dict with position summary
        """
        try:
            positions = self.mt5_connector.get_positions()
            
            if not positions:
                return {
                    'total_positions': 0,
                    'total_volume': 0.0,
                    'total_profit': 0.0,
                    'buy_positions': 0,
                    'sell_positions': 0,
                    'symbols': []
                }
            
            summary = {
                'total_positions': len(positions),
                'total_volume': sum(pos['volume'] for pos in positions),
                'total_profit': sum(pos['profit'] for pos in positions),
                'buy_positions': sum(1 for pos in positions if pos['type'] == 0),
                'sell_positions': sum(1 for pos in positions if pos['type'] == 1),
                'symbols': list(set(pos['symbol'] for pos in positions)),
                'positions': positions
            }
            
            return summary
            
        except Exception as e:
            self.logger.error(f"Error getting position summary: {str(e)}")
            return {}
    
    def get_daily_stats(self) -> Dict[str, Any]:
        """
        Get daily trading statistics
        
        Returns:
            Dict with daily stats
        """
        return {
            'daily_trades': self._daily_trades,
            'daily_profit': self._daily_profit,
            'session_start_balance': self._session_start_balance,
            'current_balance': self._get_current_balance(),
            'daily_return': self._calculate_daily_return()
        }
    
    def _pre_order_checks(self, symbol: str, volume: float) -> bool:
        """Perform pre-order risk and validity checks"""
        try:
            # Check MT5 connection
            if not self.mt5_connector.is_connected():
                self.logger.error("MT5 not connected")
                return False
            
            # Check symbol info
            symbol_info = self.mt5_connector.get_symbol_info(symbol)
            if not symbol_info:
                self.logger.error(f"Cannot get symbol info for {symbol}")
                return False
            
            # Check if trading is allowed
            if not symbol_info.get('trade_allowed', False):
                self.logger.error(f"Trading not allowed for {symbol}")
                return False
            
            # Check volume limits
            min_volume = symbol_info.get('volume_min', 0.01)
            max_volume = symbol_info.get('volume_max', 100.0)
            
            if volume < min_volume or volume > max_volume:
                self.logger.error(f"Volume {volume} outside limits [{min_volume}, {max_volume}]")
                return False
            
            # Check maximum positions
            current_positions = len(self.mt5_connector.get_positions())
            if current_positions >= self.max_positions:
                self.logger.error(f"Maximum positions limit reached: {current_positions}/{self.max_positions}")
                return False
            
            # Check account balance
            account_info = self.mt5_connector.get_account_info()
            if not account_info:
                self.logger.error("Cannot get account info")
                return False
            
            free_margin = account_info.get('free_margin', 0)
            if free_margin <= 0:
                self.logger.error("Insufficient free margin")
                return False
            
            # Check daily loss limit
            if self._check_daily_loss_limit():
                self.logger.error("Daily loss limit reached")
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Pre-order check error: {str(e)}")
            return False
    
    def _create_order_request(self, symbol: str, volume: float, order_type: OrderType,
                             price: float, stop_loss: float = None, take_profit: float = None,
                             comment: str = "") -> Dict[str, Any]:
        """Create MT5 order request"""
        
        # Map order types
        type_mapping = {
            OrderType.BUY: mt5.ORDER_TYPE_BUY,
            OrderType.SELL: mt5.ORDER_TYPE_SELL,
            OrderType.BUY_LIMIT: mt5.ORDER_TYPE_BUY_LIMIT,
            OrderType.SELL_LIMIT: mt5.ORDER_TYPE_SELL_LIMIT,
            OrderType.BUY_STOP: mt5.ORDER_TYPE_BUY_STOP,
            OrderType.SELL_STOP: mt5.ORDER_TYPE_SELL_STOP,
        }
        
        request = {
            'action': mt5.TRADE_ACTION_DEAL,
            'symbol': symbol,
            'volume': volume,
            'type': type_mapping[order_type],
            'price': price,
            'deviation': self.default_deviation,
            'magic': self.magic_number,
            'comment': comment or f'TradeMaestro {order_type.value}',
            'type_time': mt5.ORDER_TIME_GTC,
            'type_filling': mt5.ORDER_FILLING_IOC,
        }
        
        # Add stop loss and take profit if provided
        if stop_loss is not None:
            request['sl'] = stop_loss
        
        if take_profit is not None:
            request['tp'] = take_profit
        
        # For pending orders, use different action
        if order_type in [OrderType.BUY_LIMIT, OrderType.SELL_LIMIT, 
                         OrderType.BUY_STOP, OrderType.SELL_STOP]:
            request['action'] = mt5.TRADE_ACTION_PENDING
        
        return request
    
    def _execute_order(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Execute order through MT5"""
        try:
            # Log order details
            self.logger.info(f"📤 Executing order: {request['type']} {request['volume']} {request['symbol']} @ {request['price']}")
            
            # Send order
            result = self.mt5_connector.send_order(request)
            
            # Log result
            if result['success']:
                self.logger.info(f"✅ Order executed: Ticket {result.get('ticket')}")
            else:
                self.logger.error(f"❌ Order failed: {result.get('error')}")
            
            return result
            
        except Exception as e:
            error_msg = f"Order execution error: {str(e)}"
            self.logger.error(error_msg)
            return {'success': False, 'error': error_msg}
    
    def _post_order_success(self, result: Dict[str, Any], symbol: str, volume: float,
                           order_type: OrderType, comment: str):
        """Handle successful order execution"""
        try:
            ticket = result.get('ticket')
            price = result.get('price', 0.0)
            
            # Update tracking
            order_info = {
                'ticket': ticket,
                'symbol': symbol,
                'volume': volume,
                'type': order_type.value,
                'price': price,
                'time': datetime.now(),
                'comment': comment,
                'status': 'EXECUTED'
            }
            
            self._active_orders[ticket] = order_info
            self._order_history.append(order_info)
            
            # Update daily stats
            self._daily_trades += 1
            
            # Emit signals
            self.order_executed.emit(order_info)
            
            if order_type in [OrderType.BUY, OrderType.SELL]:
                self.position_opened.emit(order_info)
            
        except Exception as e:
            self.logger.error(f"Post-order success handling error: {str(e)}")
    
    def _post_order_failure(self, result: Dict[str, Any], symbol: str, volume: float, order_type: OrderType):
        """Handle failed order execution"""
        try:
            error_msg = result.get('error', 'Unknown error')
            
            # Log failure details
            failure_info = {
                'symbol': symbol,
                'volume': volume,
                'type': order_type.value,
                'error': error_msg,
                'time': datetime.now()
            }
            
            self._order_history.append(failure_info)
            
            # Emit signal
            self.order_failed.emit(f"Order failed: {error_msg}", str(failure_info))
            
        except Exception as e:
            self.logger.error(f"Post-order failure handling error: {str(e)}")
    
    def _update_order_tracking(self, ticket: int, status: str):
        """Update order tracking information"""
        if ticket in self._active_orders:
            self._active_orders[ticket]['status'] = status
            self._active_orders[ticket]['update_time'] = datetime.now()
    
    def _update_position_tracking(self, ticket: int, status: str, profit: float = 0.0):
        """Update position tracking information"""
        try:
            if ticket in self._position_tracker:
                self._position_tracker[ticket]['status'] = status
                self._position_tracker[ticket]['close_time'] = datetime.now()
                self._position_tracker[ticket]['profit'] = profit
            
            # Update daily profit
            self._daily_profit += profit
            
        except Exception as e:
            self.logger.error(f"Position tracking update error: {str(e)}")
    
    def _calculate_close_profit(self, position: Dict[str, Any], close_price: float, volume: float) -> float:
        """Calculate profit/loss for closing position"""
        try:
            open_price = position['price_open']
            pos_type = position['type']
            
            if pos_type == 0:  # Buy position
                profit = (close_price - open_price) * volume
            else:  # Sell position
                profit = (open_price - close_price) * volume
            
            # Get symbol info for contract size
            symbol_info = self.mt5_connector.get_symbol_info(position['symbol'])
            if symbol_info:
                contract_size = symbol_info.get('trade_contract_size', 100000)
                profit *= contract_size
            
            return profit
            
        except Exception as e:
            self.logger.error(f"Error calculating close profit: {str(e)}")
            return 0.0
    
    def _check_daily_loss_limit(self) -> bool:
        """Check if daily loss limit has been reached"""
        try:
            if self._session_start_balance <= 0:
                account_info = self.mt5_connector.get_account_info()
                if account_info:
                    self._session_start_balance = account_info.get('balance', 0)
            
            current_balance = self._get_current_balance()
            
            if self._session_start_balance > 0:
                daily_loss_pct = (self._session_start_balance - current_balance) / self._session_start_balance
                return daily_loss_pct >= self.max_daily_loss
            
            return False
            
        except Exception as e:
            self.logger.error(f"Daily loss check error: {str(e)}")
            return False
    
    def _get_current_balance(self) -> float:
        """Get current account balance"""
        try:
            account_info = self.mt5_connector.get_account_info()
            return account_info.get('balance', 0.0) if account_info else 0.0
        except Exception:
            return 0.0
    
    def _calculate_daily_return(self) -> float:
        """Calculate daily return percentage"""
        try:
            if self._session_start_balance <= 0:
                return 0.0
            
            current_balance = self._get_current_balance()
            return ((current_balance - self._session_start_balance) / self._session_start_balance) * 100
            
        except Exception:
            return 0.0
    
    def start_monitoring(self):
        """Start position monitoring thread"""
        if self._monitoring:
            return
        
        self._monitoring = True
        self._monitor_thread = threading.Thread(target=self._monitor_positions, daemon=True)
        self._monitor_thread.start()
        self.logger.info("📊 Started position monitoring")
    
    def stop_monitoring(self):
        """Stop position monitoring"""
        self._monitoring = False
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2.0)
        self.logger.info("📊 Stopped position monitoring")
    
    def _monitor_positions(self):
        """Monitor positions for updates and changes"""
        while self._monitoring:
            try:
                # Get current positions
                current_positions = self.mt5_connector.get_positions()
                
                # Update position tracking
                for position in current_positions:
                    ticket = position['ticket']
                    
                    if ticket not in self._position_tracker:
                        # New position discovered
                        self._position_tracker[ticket] = {
                            'symbol': position['symbol'],
                            'type': 'BUY' if position['type'] == 0 else 'SELL',
                            'volume': position['volume'],
                            'open_price': position['price_open'],
                            'open_time': position.get('time', datetime.now()),
                            'status': 'OPEN',
                            'current_profit': position['profit']
                        }
                    else:
                        # Update existing position
                        self._position_tracker[ticket]['current_profit'] = position['profit']
                
                time.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                self.logger.error(f"Position monitoring error: {str(e)}")
                time.sleep(10)
