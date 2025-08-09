"""
Windows-specific configuration for TradeMaestro Bot
Robust configuration with error handling and Windows path compatibility
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

# Import dotenv safely with fallback
try:
    from dotenv import load_dotenv
    load_dotenv()
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False
    print("⚠️ python-dotenv not available, using environment variables only")


class WindowsConfig:
    """
    Windows-optimized configuration class
    Handles all settings with robust error handling
    """
    
    def __init__(self, config_file: str = "trademaestro_config.json"):
        """Initialize Windows-compatible configuration"""
        self.config_file = Path(config_file)
        self.logger = self._setup_logging()
        
        # Default configuration
        self._default_config = self._get_default_config()
        
        # Load configuration
        self.config = self._load_configuration()
        
        # Create Windows-friendly directories
        self._ensure_directories()
        
        # Setup paths
        self._setup_paths()
        
        self.logger.info("✅ Windows configuration initialized successfully")
    
    def _setup_logging(self):
        """Setup basic logging for configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler('config.log', encoding='utf-8')
            ]
        )
        return logging.getLogger(__name__)
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration values"""
        return {
            # Trading Settings
            "DEFAULT_LOT_SIZE": 0.01,
            "MAX_LOT_SIZE": 1.0,
            "MIN_LOT_SIZE": 0.01,
            "DEFAULT_TIMEFRAME": "M15",
            "DEFAULT_SYMBOL": "EURUSD",
            "TRADING_SYMBOLS": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"],
            
            # Risk Management
            "MAX_RISK_PER_TRADE": 0.02,  # 2% of balance
            "MAX_DAILY_LOSS": 0.05,      # 5% of balance
            "MAX_POSITIONS": 5,
            "DEFAULT_STOP_LOSS": 50,     # pips
            "DEFAULT_TAKE_PROFIT": 100,  # pips
            
            # Strategy Settings
            "DEFAULT_STRATEGY": "scalping",
            "STRATEGY_CONFIDENCE_THRESHOLD": 0.7,
            "EMA_PERIODS": [9, 21, 50, 200],
            "RSI_PERIOD": 14,
            "RSI_OVERBOUGHT": 70,
            "RSI_OVERSOLD": 30,
            
            # Bot Settings
            "AUTO_START": False,
            "DEMO_MODE": True,
            "DEBUG_MODE": True,
            "REFRESH_RATE": 1,           # seconds
            "LOG_LEVEL": "INFO",
            "SAVE_TRADES_TO_FILE": True,
            
            # GUI Settings
            "WINDOW_WIDTH": 1200,
            "WINDOW_HEIGHT": 800,
            "THEME": "dark",
            "AUTO_SCROLL_LOGS": True,
            "SHOW_CHARTS": True,
            
            # MT5 Settings (safe defaults)
            "MT5_LOGIN": "",
            "MT5_PASSWORD": "",
            "MT5_SERVER": "",
            "MT5_TIMEOUT": 60000,        # milliseconds
            "MT5_RETRY_COUNT": 3,
            "MT5_RETRY_DELAY": 5,        # seconds
            
            # File Paths (Windows-compatible)
            "DATA_DIR": "data",
            "LOGS_DIR": "logs",
            "CACHE_DIR": "data/cache",
            "HISTORY_DIR": "data/history",
            "STRATEGIES_DIR": "strategies",
            
            # Performance Settings
            "MONITOR_PERFORMANCE": True,
            "MAX_CPU_USAGE": 80,         # percent
            "MAX_MEMORY_USAGE": 1024,    # MB
            "PERFORMANCE_LOG_INTERVAL": 300,  # seconds
        }
    
    def _load_configuration(self) -> Dict[str, Any]:
        """Load configuration from file with fallback to defaults"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    file_config = json.load(f)
                
                # Merge with defaults
                config = self._default_config.copy()
                config.update(file_config)
                
                self.logger.info(f"✅ Configuration loaded from {self.config_file}")
                return config
            else:
                self.logger.info("ℹ️ No config file found, using defaults")
                return self._default_config.copy()
                
        except Exception as e:
            self.logger.error(f"❌ Error loading config: {e}")
            self.logger.info("🔄 Using default configuration")
            return self._default_config.copy()
    
    def _ensure_directories(self):
        """Create required directories if they don't exist"""
        try:
            directories = [
                self.config["DATA_DIR"],
                self.config["LOGS_DIR"],
                self.config["CACHE_DIR"],
                self.config["HISTORY_DIR"],
                self.config["STRATEGIES_DIR"]
            ]
            
            for directory in directories:
                path = Path(directory)
                path.mkdir(parents=True, exist_ok=True)
                self.logger.info(f"📁 Directory ensured: {path.absolute()}")
                
        except Exception as e:
            self.logger.error(f"❌ Error creating directories: {e}")
    
    def _setup_paths(self):
        """Setup Windows-compatible absolute paths"""
        try:
            # Convert relative paths to absolute paths
            base_dir = Path.cwd()
            
            self.DATA_DIR = base_dir / self.config["DATA_DIR"]
            self.LOGS_DIR = base_dir / self.config["LOGS_DIR"]
            self.CACHE_DIR = base_dir / self.config["CACHE_DIR"]
            self.HISTORY_DIR = base_dir / self.config["HISTORY_DIR"]
            self.STRATEGIES_DIR = base_dir / self.config["STRATEGIES_DIR"]
            
            # Log file paths
            self.LOG_FILE = self.LOGS_DIR / f"trademaestro_{datetime.now().strftime('%Y%m%d')}.log"
            self.TRADE_HISTORY_FILE = self.HISTORY_DIR / "trade_history.csv"
            self.PERFORMANCE_FILE = self.HISTORY_DIR / "performance.json"
            
            self.logger.info("✅ Paths configured successfully")
            
        except Exception as e:
            self.logger.error(f"❌ Error setting up paths: {e}")
    
    def save_configuration(self):
        """Save current configuration to file"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            
            self.logger.info(f"✅ Configuration saved to {self.config_file}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error saving config: {e}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value safely"""
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any):
        """Set configuration value"""
        self.config[key] = value
        self.logger.info(f"⚙️ Config updated: {key} = {value}")
    
    def update_from_env(self):
        """Update configuration from environment variables"""
        try:
            env_mappings = {
                "MT5_LOGIN": "MT5_LOGIN",
                "MT5_PASSWORD": "MT5_PASSWORD", 
                "MT5_SERVER": "MT5_SERVER",
                "DEMO_MODE": "DEMO_MODE",
                "DEBUG_MODE": "DEBUG_MODE"
            }
            
            for config_key, env_key in env_mappings.items():
                env_value = os.getenv(env_key)
                if env_value is not None:
                    # Convert string booleans
                    if env_value.lower() in ['true', 'false']:
                        env_value = env_value.lower() == 'true'
                    
                    self.config[config_key] = env_value
                    self.logger.info(f"🔧 Config from env: {config_key}")
            
        except Exception as e:
            self.logger.error(f"❌ Error updating from environment: {e}")
    
    def validate_configuration(self) -> bool:
        """Validate configuration values"""
        try:
            # Check critical paths
            if not self.DATA_DIR.exists():
                self.logger.error("❌ Data directory not found")
                return False
            
            # Check numeric ranges
            if not (0.01 <= self.config["DEFAULT_LOT_SIZE"] <= 1.0):
                self.logger.error("❌ Invalid lot size")
                return False
            
            if not (0.01 <= self.config["MAX_RISK_PER_TRADE"] <= 0.1):
                self.logger.error("❌ Invalid risk per trade")
                return False
            
            self.logger.info("✅ Configuration validation passed")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Configuration validation error: {e}")
            return False
    
    def get_mt5_credentials(self) -> Dict[str, str]:
        """Get MT5 credentials safely"""
        return {
            "login": str(self.config.get("MT5_LOGIN", "")),
            "password": str(self.config.get("MT5_PASSWORD", "")),
            "server": str(self.config.get("MT5_SERVER", ""))
        }
    
    def is_demo_mode(self) -> bool:
        """Check if running in demo mode"""
        return bool(self.config.get("DEMO_MODE", True))
    
    def is_debug_mode(self) -> bool:
        """Check if running in debug mode"""
        return bool(self.config.get("DEBUG_MODE", True))


# Global configuration instance
windows_config = WindowsConfig()

# Export common configuration values as module attributes for backwards compatibility
DEFAULT_LOT_SIZE = windows_config.get("DEFAULT_LOT_SIZE")
MAX_POSITIONS = windows_config.get("MAX_POSITIONS")
DEFAULT_STRATEGY = windows_config.get("DEFAULT_STRATEGY")
DEMO_MODE = windows_config.is_demo_mode()
DEBUG_MODE = windows_config.is_debug_mode()
DATA_DIR = windows_config.DATA_DIR
LOGS_DIR = windows_config.LOGS_DIR
CACHE_DIR = windows_config.CACHE_DIR
HISTORY_DIR = windows_config.HISTORY_DIR