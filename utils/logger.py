"""
TradeMaestro Logging System
Provides comprehensive logging with Windows compatibility and GUI integration
"""

import logging
import logging.handlers
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Any
import traceback

try:
    import colorlog
    COLORLOG_AVAILABLE = True
except ImportError:
    COLORLOG_AVAILABLE = False

class ColoredFormatter(logging.Formatter):
    """Custom colored formatter for Windows compatibility"""
    
    # Color codes for Windows
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
        'RESET': '\033[0m'       # Reset
    }
    
    def format(self, record):
        if sys.platform == 'win32':
            # Enable ANSI colors on Windows
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            except:
                pass
        
        # Add color to the log level
        if record.levelname in self.COLORS:
            record.levelname = f"{self.COLORS[record.levelname]}{record.levelname}{self.COLORS['RESET']}"
        
        return super().format(record)


class TradeMaestroLogger:
    """
    Advanced logging system for TradeMaestro with multiple handlers
    and Windows-optimized configuration
    """
    
    def __init__(self, name: str, level: str = "INFO", log_file: Optional[Path] = None):
        self.name = name
        self.logger = logging.getLogger(name)
        
        # Ensure level is string
        if hasattr(level, 'upper'):
            self.logger.setLevel(getattr(logging, level.upper()))
        else:
            self.logger.setLevel(getattr(logging, str(level).upper()))
        
        # Prevent duplicate handlers
        if self.logger.handlers:
            self.logger.handlers.clear()
        
        self.setup_handlers(level, log_file)
    
    def setup_handlers(self, level: str, log_file: Optional[Path] = None):
        """Setup logging handlers for console and file output"""
        
        # Console handler with colors
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, level.upper()))
        
        if COLORLOG_AVAILABLE:
            # Use colorlog if available
            console_formatter = colorlog.ColoredFormatter(
                '%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%H:%M:%S',
                log_colors={
                    'DEBUG': 'cyan',
                    'INFO': 'green',
                    'WARNING': 'yellow',
                    'ERROR': 'red',
                    'CRITICAL': 'red,bg_white',
                }
            )
        else:
            # Fallback to custom colored formatter
            console_formatter = ColoredFormatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%H:%M:%S'
            )
        
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        
        # File handler with rotation
        if log_file:
            try:
                # Ensure log directory exists
                log_file.parent.mkdir(parents=True, exist_ok=True)
                
                # Rotating file handler to prevent huge log files
                file_handler = logging.handlers.RotatingFileHandler(
                    log_file,
                    maxBytes=10 * 1024 * 1024,  # 10MB
                    backupCount=5,
                    encoding='utf-8'
                )
                file_handler.setLevel(logging.DEBUG)  # File gets everything
                
                file_formatter = logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S'
                )
                file_handler.setFormatter(file_formatter)
                self.logger.addHandler(file_handler)
                
            except Exception as e:
                self.logger.warning(f"Could not setup file logging: {str(e)}")
    
    def debug(self, message: str, *args, **kwargs):
        """Log debug message"""
        self.logger.debug(message, *args, **kwargs)
    
    def info(self, message: str, *args, **kwargs):
        """Log info message"""
        self.logger.info(message, *args, **kwargs)
    
    def warning(self, message: str, *args, **kwargs):
        """Log warning message"""
        self.logger.warning(message, *args, **kwargs)
    
    def error(self, message: str, *args, **kwargs):
        """Log error message"""
        self.logger.error(message, *args, **kwargs)
    
    def critical(self, message: str, *args, **kwargs):
        """Log critical message"""
        self.logger.critical(message, *args, **kwargs)
    
    def exception(self, message: str, *args, **kwargs):
        """Log exception with traceback"""
        self.logger.exception(message, *args, **kwargs)
    
    def log_trade(self, symbol: str, action: str, lot_size: float, 
                  price: float, sl: float = None, tp: float = None, 
                  result: str = "PENDING", ticket: int = None):
        """Log trading activity with structured format"""
        trade_info = {
            'symbol': symbol,
            'action': action,
            'lot_size': lot_size,
            'price': price,
            'stop_loss': sl,
            'take_profit': tp,
            'result': result,
            'ticket': ticket,
            'timestamp': datetime.now().isoformat()
        }
        
        self.info(f"TRADE | {action} {lot_size} {symbol} @ {price} | "
                 f"SL:{sl} TP:{tp} | {result} | Ticket:{ticket}")
    
    def log_performance(self, balance: float, equity: float, profit: float, 
                       trades_today: int, win_rate: float):
        """Log performance metrics"""
        self.info(f"PERFORMANCE | Balance:{balance:.2f} Equity:{equity:.2f} "
                 f"Profit:{profit:.2f} | Trades:{trades_today} WinRate:{win_rate:.1f}%")
    
    def log_error_with_context(self, error: Exception, context: dict = None):
        """Log error with additional context information"""
        error_msg = f"ERROR: {str(error)}"
        
        if context:
            context_str = " | ".join([f"{k}:{v}" for k, v in context.items()])
            error_msg = f"{error_msg} | Context: {context_str}"
        
        self.error(error_msg)
        self.error(f"Traceback: {traceback.format_exc()}")


class Logger:
    """
    Simplified logger interface for easy use throughout the application
    """
    
    _instances = {}
    _global_config = {
        'level': 'INFO',
        'log_file': None
    }
    
    def __new__(cls, name: str):
        if name not in cls._instances:
            cls._instances[name] = TradeMaestroLogger(
                name, 
                cls._global_config['level'],
                cls._global_config['log_file']
            )
        return cls._instances[name]
    
    @classmethod
    def configure_global(cls, level: str = "INFO", log_file: Optional[Path] = None):
        """Configure global logging settings"""
        cls._global_config['level'] = level
        cls._global_config['log_file'] = log_file
        
        # Update existing loggers
        for logger in cls._instances.values():
            logger.logger.setLevel(getattr(logging, level.upper()))


def setup_logging(level: str = "INFO", log_file: Optional[Path] = None) -> bool:
    """
    Setup global logging configuration for the application
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file
    
    Returns:
        bool: True if setup successful, False otherwise
    """
    try:
        # Configure global logger settings
        Logger.configure_global(level, log_file)
        
        # Test logging
        test_logger = Logger("setup_test")
        test_logger.info("🚀 TradeMaestro logging system initialized")
        test_logger.debug("Debug logging enabled")
        
        if log_file:
            test_logger.info(f"📝 Log file: {log_file}")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to setup logging: {str(e)}")
        traceback.print_exc()
        return False


class PerformanceTimer:
    """Context manager for performance timing with logging"""
    
    def __init__(self, operation_name: str, logger: Logger = None):
        self.operation_name = operation_name
        self.logger = logger or Logger("performance_timer")
        self.start_time = None
    
    def __enter__(self):
        self.start_time = datetime.now()
        self.logger.debug(f"⏱️ Starting {self.operation_name}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration = (datetime.now() - self.start_time).total_seconds()
            
            if exc_type:
                self.logger.error(f"❌ {self.operation_name} failed after {duration:.3f}s: {exc_val}")
            else:
                self.logger.debug(f"✅ {self.operation_name} completed in {duration:.3f}s")


def log_function_call(func):
    """Decorator to log function calls for debugging"""
    def wrapper(*args, **kwargs):
        logger = Logger(func.__module__)
        func_name = func.__name__
        
        # Log function entry
        logger.debug(f"🔧 Calling {func_name}")
        
        try:
            result = func(*args, **kwargs)
            logger.debug(f"✅ {func_name} completed successfully")
            return result
            
        except Exception as e:
            logger.error(f"❌ {func_name} failed: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise
    
    return wrapper


# Global logger instance for quick access
main_logger = Logger("TradeMaestro")

# Convenience functions
def log_info(message: str):
    """Quick info logging"""
    main_logger.info(message)

def log_error(message: str):
    """Quick error logging"""
    main_logger.error(message)

def log_warning(message: str):
    """Quick warning logging"""
    main_logger.warning(message)

def log_debug(message: str):
    """Quick debug logging"""
    main_logger.debug(message)

def log_trade_activity(symbol: str, action: str, lot_size: float, 
                      price: float, result: str = "EXECUTED"):
    """Quick trade logging"""
    main_logger.log_trade(symbol, action, lot_size, price, result=result)


# Windows-specific logging optimizations
def optimize_windows_logging():
    """Apply Windows-specific logging optimizations"""
    if sys.platform == 'win32':
        try:
            # Enable ANSI color support on Windows 10+
            import ctypes
            from ctypes import wintypes
            
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            
            # Get console handles
            stdout_handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            stderr_handle = kernel32.GetStdHandle(-12)  # STD_ERROR_HANDLE
            
            # Enable virtual terminal processing
            ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            
            # Get current console mode
            original_mode = wintypes.DWORD()
            kernel32.GetConsoleMode(stdout_handle, ctypes.byref(original_mode))
            
            # Set new mode with virtual terminal processing
            new_mode = original_mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING
            kernel32.SetConsoleMode(stdout_handle, new_mode)
            kernel32.SetConsoleMode(stderr_handle, new_mode)
            
            return True
            
        except Exception as e:
            print(f"Could not enable Windows color support: {str(e)}")
            return False
    
    return True


# Initialize Windows optimizations on import
optimize_windows_logging()
