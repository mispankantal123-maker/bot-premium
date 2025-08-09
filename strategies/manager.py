"""
Strategy Manager for TradeMaestro
Manages trading strategies and their execution
"""

import threading
import time
from typing import Dict, Any, List, Optional
from datetime import datetime

from .base_strategy import BaseStrategy
from .scalping import ScalpingStrategy 
from .swing import SwingTradingStrategy
from ..utils.logger import Logger


class StrategyManager:
    """
    Strategy Manager for coordinating trading strategies
    Handles strategy lifecycle, execution, and monitoring
    """
    
    def __init__(self, mt5_connector, performance_tracker, config):
        self.mt5_connector = mt5_connector
        self.performance_tracker = performance_tracker
        self.config = config
        self.logger = Logger(__name__)
        
        # Strategy registry
        self._strategies = {
            'scalping': ScalpingStrategy,
            'swing': SwingTradingStrategy
        }
        
        # Active strategy
        self._current_strategy = None
        self._strategy_instance = None
        self._strategy_thread = None
        self._running = False
        
        self.logger.info("🎯 Strategy Manager initialized")
    
    def get_available_strategies(self) -> List[str]:
        """Get list of available strategies"""
        return list(self._strategies.keys())
    
    def get_current_strategy_name(self) -> Optional[str]:
        """Get current active strategy name"""
        return self._current_strategy
    
    def start_strategy(self, strategy_name: str = None) -> bool:
        """Start trading with specified strategy"""
        try:
            if strategy_name is None:
                strategy_name = 'scalping'  # Default strategy
            
            if strategy_name not in self._strategies:
                self.logger.error(f"Unknown strategy: {strategy_name}")
                return False
            
            # Stop current strategy if running
            if self._running:
                self.stop_strategy()
            
            # Create strategy instance
            strategy_class = self._strategies[strategy_name]
            self._strategy_instance = strategy_class(
                self.mt5_connector,
                self.performance_tracker,
                self.config
            )
            
            self._current_strategy = strategy_name
            self._running = True
            
            # Start strategy in separate thread
            self._strategy_thread = threading.Thread(
                target=self._run_strategy,
                daemon=True
            )
            self._strategy_thread.start()
            
            self.logger.info(f"✅ Strategy '{strategy_name}' started successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start strategy '{strategy_name}': {str(e)}")
            return False
    
    def stop_strategy(self) -> bool:
        """Stop current trading strategy"""
        try:
            if not self._running:
                self.logger.warning("No strategy is currently running")
                return True
            
            self._running = False
            
            # Stop strategy instance
            if self._strategy_instance:
                self._strategy_instance.stop()
            
            # Wait for thread to finish
            if self._strategy_thread and self._strategy_thread.is_alive():
                self._strategy_thread.join(timeout=5)
            
            self._current_strategy = None
            self._strategy_instance = None
            self._strategy_thread = None
            
            self.logger.info("🛑 Strategy stopped successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error stopping strategy: {str(e)}")
            return False
    
    def _run_strategy(self):
        """Run strategy in separate thread"""
        try:
            self.logger.info(f"🚀 Running strategy: {self._current_strategy}")
            
            while self._running and self._strategy_instance:
                # Execute strategy logic
                if hasattr(self._strategy_instance, 'execute'):
                    self._strategy_instance.execute()
                
                # Small delay to prevent excessive CPU usage
                time.sleep(1)
                
        except Exception as e:
            self.logger.error(f"Strategy execution error: {str(e)}")
        finally:
            self.logger.info(f"Strategy thread exiting: {self._current_strategy}")
    
    def is_running(self) -> bool:
        """Check if strategy is currently running"""
        return self._running
    
    def get_strategy_status(self) -> Dict[str, Any]:
        """Get current strategy status"""
        return {
            'current_strategy': self._current_strategy,
            'running': self._running,
            'available_strategies': self.get_available_strategies(),
            'thread_active': self._strategy_thread.is_alive() if self._strategy_thread else False
        }