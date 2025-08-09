"""
TradeMaestro Configuration Management
Centralizes all configuration settings with Windows-optimized paths
"""

import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
import json


def load_environment():
    """Load environment variables from .env file"""
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)


class Config:
    """
    Centralized configuration management for TradeMaestro
    Handles all settings with Windows-friendly paths and environment variables
    """
    
    def __init__(self):
        self.PROJECT_ROOT = Path(__file__).parent
        self.setup_directories()
        self.load_settings()
    
    def setup_directories(self):
        """Create and setup all required directories"""
        # Core directories
        self.LOGS_DIR = self.PROJECT_ROOT / "logs"
        self.DATA_DIR = self.PROJECT_ROOT / "data"
        self.CACHE_DIR = self.DATA_DIR / "cache"
        self.HISTORY_DIR = self.DATA_DIR / "history"
        
        # Create directories if they don't exist
        for directory in [self.LOGS_DIR, self.DATA_DIR, self.CACHE_DIR, self.HISTORY_DIR]:
            directory.mkdir(parents=True, exist_ok=True)
    
    def load_settings(self):
        """Load all configuration settings"""
        # Application Settings
        self.APP_NAME = "TradeMaestro"
        self.APP_VERSION = "2.0.0"
        self.DEBUG_MODE = os.getenv("DEBUG", "false").lower() == "true"
        self.DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"  # Enable demo mode by default
        
        # Logging Configuration
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        self.LOG_FILE = self.LOGS_DIR / "trademaestro.log"
        self.LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", "10485760"))  # 10MB
        self.LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "5"))
        
        # MetaTrader 5 Configuration
        self.MT5_LOGIN = os.getenv("MT5_LOGIN", "")
        self.MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
        self.MT5_SERVER = os.getenv("MT5_SERVER", "")
        self.MT5_PATH = os.getenv("MT5_PATH", "")
        self.MT5_TIMEOUT = int(os.getenv("MT5_TIMEOUT", "60"))
        self.MT5_RETRY_ATTEMPTS = int(os.getenv("MT5_RETRY_ATTEMPTS", "5"))
        self.MT5_RETRY_DELAY = int(os.getenv("MT5_RETRY_DELAY", "3"))
        
        # Trading Configuration
        self.TRADING_ENABLED = os.getenv("TRADING_ENABLED", "true").lower() == "true"
        self.TRADING_INTERVAL_MS = int(os.getenv("TRADING_INTERVAL_MS", "1000"))
        self.MAX_POSITIONS = int(os.getenv("MAX_POSITIONS", "10"))
        self.DEFAULT_LOT_SIZE = float(os.getenv("DEFAULT_LOT_SIZE", "0.01"))
        self.DEFAULT_STOP_LOSS = int(os.getenv("DEFAULT_STOP_LOSS", "50"))
        self.DEFAULT_TAKE_PROFIT = int(os.getenv("DEFAULT_TAKE_PROFIT", "100"))
        
        # Risk Management
        self.MAX_RISK_PER_TRADE = float(os.getenv("MAX_RISK_PER_TRADE", "0.02"))  # 2%
        self.MAX_DAILY_LOSS = float(os.getenv("MAX_DAILY_LOSS", "0.05"))  # 5%
        self.MAX_DRAWDOWN = float(os.getenv("MAX_DRAWDOWN", "0.10"))  # 10%
        self.TRAILING_STOP_ENABLED = os.getenv("TRAILING_STOP_ENABLED", "true").lower() == "true"
        self.TRAILING_STOP_DISTANCE = int(os.getenv("TRAILING_STOP_DISTANCE", "20"))
        
        # Strategy Configuration
        self.DEFAULT_STRATEGY = os.getenv("DEFAULT_STRATEGY", "scalping")
        self.STRATEGY_TIMEFRAME = os.getenv("STRATEGY_TIMEFRAME", "M1")
        self.ANALYSIS_LOOKBACK = int(os.getenv("ANALYSIS_LOOKBACK", "100"))
        
        # Symbols and Markets
        self.DEFAULT_SYMBOLS = self.parse_symbol_list(
            os.getenv("DEFAULT_SYMBOLS", "EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD")
        )
        self.SYMBOL_SPREADS = self.load_symbol_spreads()
        
        # News and Market Hours
        self.AVOID_NEWS_TRADING = os.getenv("AVOID_NEWS_TRADING", "true").lower() == "true"
        self.NEWS_BUFFER_MINUTES = int(os.getenv("NEWS_BUFFER_MINUTES", "30"))
        self.TRADING_SESSIONS = self.load_trading_sessions()
        
        # Telegram Integration
        self.TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"
        self.TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
        self.TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
        
        # Performance and Monitoring
        self.PERFORMANCE_TRACKING = os.getenv("PERFORMANCE_TRACKING", "true").lower() == "true"
        self.SAVE_TRADE_HISTORY = os.getenv("SAVE_TRADE_HISTORY", "true").lower() == "true"
        self.BACKUP_INTERVAL_HOURS = int(os.getenv("BACKUP_INTERVAL_HOURS", "24"))
        
        # GUI Configuration
        self.GUI_UPDATE_INTERVAL_MS = int(os.getenv("GUI_UPDATE_INTERVAL_MS", "1000"))
        self.GUI_THEME = os.getenv("GUI_THEME", "dark")
        self.WINDOW_WIDTH = int(os.getenv("WINDOW_WIDTH", "1200"))
        self.WINDOW_HEIGHT = int(os.getenv("WINDOW_HEIGHT", "800"))
    
    def parse_symbol_list(self, symbol_string: str) -> List[str]:
        """Parse comma-separated symbol list"""
        if not symbol_string:
            return []
        return [symbol.strip().upper() for symbol in symbol_string.split(",")]
    
    def load_symbol_spreads(self) -> Dict[str, float]:
        """Load symbol-specific spread configurations"""
        spreads_file = self.PROJECT_ROOT / "config" / "symbol_spreads.json"
        
        if spreads_file.exists():
            try:
                with open(spreads_file, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        
        # Default spread configurations
        return {
            "EURUSD": 1.5,
            "GBPUSD": 2.0,
            "USDJPY": 1.5,
            "AUDUSD": 2.0,
            "USDCAD": 2.0,
            "EURGBP": 2.5,
            "EURJPY": 2.5,
            "GBPJPY": 3.0,
        }
    
    def load_trading_sessions(self) -> Dict[str, Dict[str, Any]]:
        """Load trading session configurations"""
        return {
            "Asian": {
                "start_hour": 21,
                "start_minute": 0,
                "end_hour": 6,
                "end_minute": 0,
                "timezone": "UTC",
                "active": True,
                "preferred_symbols": ["USDJPY", "AUDUSD", "NZDUSD"]
            },
            "London": {
                "start_hour": 7,
                "start_minute": 0,
                "end_hour": 16,
                "end_minute": 0,
                "timezone": "UTC",
                "active": True,
                "preferred_symbols": ["EURUSD", "GBPUSD", "EURGBP"]
            },
            "New_York": {
                "start_hour": 13,
                "start_minute": 0,
                "end_hour": 22,
                "end_minute": 0,
                "timezone": "UTC",
                "active": True,
                "preferred_symbols": ["EURUSD", "GBPUSD", "USDCAD"]
            }
        }
    
    def get_mt5_paths(self) -> List[str]:
        """Get possible MT5 installation paths for Windows"""
        possible_paths = []
        
        # Custom path from environment
        if self.MT5_PATH:
            possible_paths.append(self.MT5_PATH)
        
        # Common installation paths
        program_files = [
            os.environ.get("ProgramFiles", "C:\\Program Files"),
            os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
        ]
        
        for pf in program_files:
            possible_paths.extend([
                os.path.join(pf, "MetaTrader 5", "terminal64.exe"),
                os.path.join(pf, "MetaTrader 5", "terminal.exe"),
                os.path.join(pf, "MetaTrader5", "terminal64.exe"),
                os.path.join(pf, "MetaTrader5", "terminal.exe"),
            ])
        
        # Check AppData for portable installations
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            possible_paths.extend([
                os.path.join(appdata, "MetaQuotes", "Terminal", "*", "terminal64.exe"),
                os.path.join(appdata, "MetaQuotes", "Terminal", "*", "terminal.exe"),
            ])
        
        return possible_paths
    
    def validate_config(self) -> List[str]:
        """Validate configuration and return any errors"""
        errors = []
        
        # Check required directories
        if not self.LOGS_DIR.exists():
            errors.append(f"Logs directory not accessible: {self.LOGS_DIR}")
        
        if not self.DATA_DIR.exists():
            errors.append(f"Data directory not accessible: {self.DATA_DIR}")
        
        # Validate trading parameters
        if self.DEFAULT_LOT_SIZE <= 0:
            errors.append("Default lot size must be greater than 0")
        
        if self.MAX_RISK_PER_TRADE <= 0 or self.MAX_RISK_PER_TRADE > 1:
            errors.append("Max risk per trade must be between 0 and 1")
        
        if self.DEFAULT_STOP_LOSS <= 0:
            errors.append("Default stop loss must be greater than 0")
        
        if self.DEFAULT_TAKE_PROFIT <= 0:
            errors.append("Default take profit must be greater than 0")
        
        # Validate symbol list
        if not self.DEFAULT_SYMBOLS:
            errors.append("At least one default symbol must be specified")
        
        # Validate Telegram config if enabled
        if self.TELEGRAM_ENABLED:
            if not self.TELEGRAM_TOKEN:
                errors.append("Telegram token required when Telegram is enabled")
            if not self.TELEGRAM_CHAT_ID:
                errors.append("Telegram chat ID required when Telegram is enabled")
        
        return errors
    
    def save_config(self, config_file: Optional[str] = None) -> bool:
        """Save current configuration to file"""
        if not config_file:
            config_file = self.PROJECT_ROOT / "config" / "settings.json"
        
        try:
            config_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Prepare configuration data
            config_data = {
                "trading": {
                    "default_lot_size": self.DEFAULT_LOT_SIZE,
                    "default_stop_loss": self.DEFAULT_STOP_LOSS,
                    "default_take_profit": self.DEFAULT_TAKE_PROFIT,
                    "max_positions": self.MAX_POSITIONS,
                    "default_strategy": self.DEFAULT_STRATEGY,
                    "default_symbols": self.DEFAULT_SYMBOLS
                },
                "risk_management": {
                    "max_risk_per_trade": self.MAX_RISK_PER_TRADE,
                    "max_daily_loss": self.MAX_DAILY_LOSS,
                    "max_drawdown": self.MAX_DRAWDOWN,
                    "trailing_stop_enabled": self.TRAILING_STOP_ENABLED,
                    "trailing_stop_distance": self.TRAILING_STOP_DISTANCE
                },
                "gui": {
                    "theme": self.GUI_THEME,
                    "window_width": self.WINDOW_WIDTH,
                    "window_height": self.WINDOW_HEIGHT,
                    "update_interval_ms": self.GUI_UPDATE_INTERVAL_MS
                }
            }
            
            with open(config_file, 'w') as f:
                json.dump(config_data, f, indent=2)
            
            return True
            
        except Exception:
            return False
    
    def load_user_config(self, config_file: Optional[str] = None) -> bool:
        """Load user configuration from file"""
        if not config_file:
            config_file = self.PROJECT_ROOT / "config" / "settings.json"
        
        if not Path(config_file).exists():
            return False
        
        try:
            with open(config_file, 'r') as f:
                config_data = json.load(f)
            
            # Update configuration from file
            if "trading" in config_data:
                trading = config_data["trading"]
                self.DEFAULT_LOT_SIZE = trading.get("default_lot_size", self.DEFAULT_LOT_SIZE)
                self.DEFAULT_STOP_LOSS = trading.get("default_stop_loss", self.DEFAULT_STOP_LOSS)
                self.DEFAULT_TAKE_PROFIT = trading.get("default_take_profit", self.DEFAULT_TAKE_PROFIT)
                self.MAX_POSITIONS = trading.get("max_positions", self.MAX_POSITIONS)
                self.DEFAULT_STRATEGY = trading.get("default_strategy", self.DEFAULT_STRATEGY)
                self.DEFAULT_SYMBOLS = trading.get("default_symbols", self.DEFAULT_SYMBOLS)
            
            if "risk_management" in config_data:
                risk = config_data["risk_management"]
                self.MAX_RISK_PER_TRADE = risk.get("max_risk_per_trade", self.MAX_RISK_PER_TRADE)
                self.MAX_DAILY_LOSS = risk.get("max_daily_loss", self.MAX_DAILY_LOSS)
                self.MAX_DRAWDOWN = risk.get("max_drawdown", self.MAX_DRAWDOWN)
                self.TRAILING_STOP_ENABLED = risk.get("trailing_stop_enabled", self.TRAILING_STOP_ENABLED)
                self.TRAILING_STOP_DISTANCE = risk.get("trailing_stop_distance", self.TRAILING_STOP_DISTANCE)
            
            if "gui" in config_data:
                gui = config_data["gui"]
                self.GUI_THEME = gui.get("theme", self.GUI_THEME)
                self.WINDOW_WIDTH = gui.get("window_width", self.WINDOW_WIDTH)
                self.WINDOW_HEIGHT = gui.get("window_height", self.WINDOW_HEIGHT)
                self.GUI_UPDATE_INTERVAL_MS = gui.get("update_interval_ms", self.GUI_UPDATE_INTERVAL_MS)
            
            return True
            
        except Exception:
            return False


# Global config instance
config = Config()
