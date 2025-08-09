"""
TradeMaestro Trading Strategies Module
Provides a unified interface for all trading strategies
"""

from .base_strategy import BaseStrategy, StrategyResult, SignalType
from .scalping import ScalpingStrategy
from .swing import SwingStrategy

# Available strategies registry
AVAILABLE_STRATEGIES = {
    "scalping": ScalpingStrategy,
    "swing": SwingStrategy,
}


class StrategyManager:
    """
    Manages multiple trading strategies and coordinates their execution
    """
    
    def __init__(self, mt5_connector, performance_tracker, config):
        self.mt5_connector = mt5_connector
        self.performance_tracker = performance_tracker
        self.config = config
        self.active_strategies = {}
        self.current_strategy = None
        
        # Initialize with default strategy
        self.load_strategy(config.DEFAULT_STRATEGY)
    
    def load_strategy(self, strategy_name: str) -> bool:
        """Load and initialize a trading strategy"""
        try:
            if strategy_name not in AVAILABLE_STRATEGIES:
                raise ValueError(f"Unknown strategy: {strategy_name}")
            
            strategy_class = AVAILABLE_STRATEGIES[strategy_name]
            strategy_instance = strategy_class(
                self.mt5_connector,
                self.performance_tracker,
                self.config
            )
            
            self.active_strategies[strategy_name] = strategy_instance
            self.current_strategy = strategy_instance
            
            return True
            
        except Exception as e:
            print(f"Failed to load strategy {strategy_name}: {str(e)}")
            return False
    
    def get_available_strategies(self) -> list:
        """Get list of available strategy names"""
        return list(AVAILABLE_STRATEGIES.keys())
    
    def switch_strategy(self, strategy_name: str) -> bool:
        """Switch to a different strategy"""
        if strategy_name in self.active_strategies:
            self.current_strategy = self.active_strategies[strategy_name]
            return True
        else:
            return self.load_strategy(strategy_name)
    
    def execute_trading_cycle(self):
        """Execute one trading cycle for the current strategy"""
        if self.current_strategy:
            return self.current_strategy.execute()
        return None
    
    def get_current_strategy_name(self) -> str:
        """Get name of current strategy"""
        for name, strategy in self.active_strategies.items():
            if strategy == self.current_strategy:
                return name
        return "Unknown"


__all__ = [
    'BaseStrategy',
    'StrategyResult', 
    'SignalType',
    'ScalpingStrategy',
    'SwingStrategy',
    'StrategyManager',
    'AVAILABLE_STRATEGIES'
]
