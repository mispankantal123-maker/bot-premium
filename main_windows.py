"""
TradeMaestro Bot - Windows Main Entry Point
Robust startup with comprehensive error handling and Windows compatibility
"""

import sys
import os
import traceback
import threading
import time
from pathlib import Path
from datetime import datetime

# Add current directory to Python path
current_dir = Path(__file__).parent.absolute()
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

# Import configuration first
try:
    from config_windows import windows_config
    print("✅ Configuration loaded successfully")
except Exception as e:
    print(f"❌ Failed to load configuration: {e}")
    sys.exit(1)

# Setup logging early
import logging
from utils.logger import setup_logging, Logger

# Setup logging system
try:
    setup_logging(str(windows_config.LOG_FILE), windows_config.get("LOG_LEVEL", "INFO"))
    logger = Logger(__name__)
    logger.info("🚀 TradeMaestro Windows Bot starting up...")
except Exception as e:
    print(f"❌ Failed to setup logging: {e}")
    # Fallback to basic logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

# Import required modules with error handling
try:
    import pandas as pd
    import numpy as np
    logger.info("✅ Data processing libraries loaded")
except ImportError as e:
    logger.error(f"❌ Missing data libraries: {e}")
    sys.exit(1)

try:
    import psutil
    logger.info("✅ System monitoring library loaded")
except ImportError as e:
    logger.warning(f"⚠️ System monitoring not available: {e}")
    psutil = None

# GUI imports with fallback
GUI_AVAILABLE = False
try:
    from PySide6.QtWidgets import QApplication, QMessageBox
    from PySide6.QtCore import QThread, QTimer
    from gui.main_window import MainWindow
    GUI_AVAILABLE = True
    logger.info("✅ GUI libraries loaded successfully")
except ImportError as e:
    logger.warning(f"⚠️ GUI not available: {e}")
    logger.info("🔄 Will run in CLI mode")

# Import bot components
try:
    from utils.mt5_connector_windows import WindowsMT5Connector
    from utils.mock_mt5 import MockMT5Connector
    from utils.performance import PerformanceTracker
    from strategies import StrategyManager
    logger.info("✅ Bot components loaded")
except Exception as e:
    logger.error(f"❌ Failed to load bot components: {e}")
    traceback.print_exc()
    # Try fallback imports
    try:
        from utils.mock_mt5 import MockMT5Connector
        from utils.performance import PerformanceTracker
        logger.info("✅ Fallback components loaded")
    except Exception as e2:
        logger.error(f"❌ Fallback components failed: {e2}")
        sys.exit(1)


class TradeMaestroWindows:
    """
    Main TradeMaestro application class for Windows
    Handles initialization, startup, and error recovery
    """
    
    def __init__(self):
        self.logger = Logger(__name__)
        self.config = windows_config
        
        # Application state
        self.mt5_connector = None
        self.performance_tracker = None
        self.strategy_manager = None
        self.main_window = None
        self.app = None
        
        # Threading
        self.trading_thread = None
        self.monitoring_thread = None
        self.shutdown_event = threading.Event()
        
        # Status flags
        self.is_running = False
        self.is_connected = False
        self.startup_success = False
        
        self.logger.info("🏗️ TradeMaestro Windows instance created")
    
    def startup_checks(self) -> bool:
        """Perform comprehensive startup checks"""
        self.logger.info("🔍 Performing startup checks...")
        
        try:
            # 1. Configuration validation
            if not self.config.validate_configuration():
                self.logger.error("❌ Configuration validation failed")
                return False
            
            # 2. Directory checks
            required_dirs = [
                self.config.DATA_DIR,
                self.config.LOGS_DIR,
                self.config.CACHE_DIR,
                self.config.HISTORY_DIR
            ]
            
            for directory in required_dirs:
                if not directory.exists():
                    directory.mkdir(parents=True, exist_ok=True)
                    self.logger.info(f"📁 Created directory: {directory}")
            
            # 3. System resources check
            if psutil:
                memory = psutil.virtual_memory()
                if memory.percent > 90:
                    self.logger.warning(f"⚠️ High memory usage: {memory.percent}%")
                
                cpu_count = psutil.cpu_count()
                self.logger.info(f"💻 System: {cpu_count} CPUs, {memory.total // (1024**3)}GB RAM")
            
            # 4. File permissions check
            test_file = self.config.DATA_DIR / "startup_test.txt"
            try:
                test_file.write_text("test", encoding='utf-8')
                test_file.unlink()
                self.logger.info("✅ File permissions OK")
            except Exception as e:
                self.logger.error(f"❌ File permission error: {e}")
                return False
            
            self.logger.info("✅ All startup checks passed")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Startup checks failed: {e}")
            traceback.print_exc()
            return False
    
    def initialize_mt5_connector(self) -> bool:
        """Initialize MT5 connector with fallback to mock"""
        try:
            self.logger.info("🔌 Initializing MT5 connection...")
            
            # Check if demo mode or no credentials
            credentials = self.config.get_mt5_credentials()
            if (self.config.is_demo_mode() or 
                not all(credentials.values())):
                
                self.logger.info("🎭 Using Mock MT5 connector (Demo Mode)")
                self.mt5_connector = MockMT5Connector(self.config)
            else:
                try:
                    self.logger.info("🏦 Using Real MT5 connector")
                    self.mt5_connector = WindowsMT5Connector(self.config)
                except:
                    self.logger.warning("⚠️ Real MT5 not available, using Mock")
                    self.mt5_connector = MockMT5Connector(self.config)
            
            # Test connection
            if self.mt5_connector.connect():
                self.is_connected = True
                self.logger.info("✅ MT5 connector initialized successfully")
                return True
            else:
                self.logger.error("❌ Failed to connect to MT5")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ MT5 initialization error: {e}")
            traceback.print_exc()
            return False
    
    def initialize_components(self) -> bool:
        """Initialize bot components"""
        try:
            self.logger.info("🔧 Initializing bot components...")
            
            # Performance tracker
            self.performance_tracker = PerformanceTracker(self.config)
            self.logger.info("✅ Performance tracker initialized")
            
            # Strategy manager
            self.strategy_manager = StrategyManager(
                self.mt5_connector,
                self.performance_tracker,
                self.config
            )
            self.logger.info("✅ Strategy manager initialized")
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Component initialization error: {e}")
            traceback.print_exc()
            return False
    
    def initialize_gui(self) -> bool:
        """Initialize GUI if available"""
        if not GUI_AVAILABLE:
            self.logger.info("ℹ️ GUI not available, running in CLI mode")
            return True
        
        try:
            self.logger.info("🖥️ Initializing GUI...")
            
            # Create QApplication
            self.app = QApplication(sys.argv)
            self.app.setApplicationName("TradeMaestro")
            self.app.setApplicationVersion("2.0")
            
            # Create main window
            self.main_window = MainWindow(
                self.mt5_connector,
                self.strategy_manager,
                self.performance_tracker,
                self.config
            )
            
            self.logger.info("✅ GUI initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ GUI initialization error: {e}")
            traceback.print_exc()
            return False
    
    def start_monitoring(self):
        """Start system monitoring thread"""
        if not psutil:
            return
        
        def monitor_system():
            while not self.shutdown_event.is_set():
                try:
                    cpu_percent = psutil.cpu_percent(interval=1)
                    memory = psutil.virtual_memory()
                    
                    if cpu_percent > self.config.get("MAX_CPU_USAGE", 80):
                        self.logger.warning(f"⚠️ High CPU usage: {cpu_percent}%")
                    
                    if memory.percent > 90:
                        self.logger.warning(f"⚠️ High memory usage: {memory.percent}%")
                    
                    # Log performance periodically
                    if hasattr(self, '_last_perf_log'):
                        if (datetime.now() - self._last_perf_log).seconds > 300:  # 5 minutes
                            self.logger.info(f"📊 System: CPU {cpu_percent}%, RAM {memory.percent}%")
                            self._last_perf_log = datetime.now()
                    else:
                        self._last_perf_log = datetime.now()
                    
                    time.sleep(30)  # Check every 30 seconds
                    
                except Exception as e:
                    self.logger.error(f"❌ Monitoring error: {e}")
                    time.sleep(60)
        
        self.monitoring_thread = threading.Thread(target=monitor_system, daemon=True)
        self.monitoring_thread.start()
        self.logger.info("📊 System monitoring started")
    
    def startup(self) -> bool:
        """Complete startup sequence"""
        try:
            self.logger.info("🚀 Starting TradeMaestro Windows Bot...")
            
            # Startup checks
            if not self.startup_checks():
                return False
            
            # Initialize MT5
            if not self.initialize_mt5_connector():
                return False
            
            # Initialize components
            if not self.initialize_components():
                return False
            
            # Initialize GUI
            if not self.initialize_gui():
                return False
            
            # Start monitoring
            self.start_monitoring()
            
            self.startup_success = True
            self.is_running = True
            
            self.logger.info("✅ TradeMaestro startup completed successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Startup failed: {e}")
            traceback.print_exc()
            return False
    
    def run_gui(self):
        """Run GUI application"""
        if not GUI_AVAILABLE or not self.main_window:
            self.logger.error("❌ GUI not available")
            return False
        
        try:
            self.logger.info("🖥️ Starting GUI...")
            self.main_window.show()
            return self.app.exec()
        
        except Exception as e:
            self.logger.error(f"❌ GUI runtime error: {e}")
            traceback.print_exc()
            return False
    
    def run_cli(self):
        """Run CLI application"""
        try:
            self.logger.info("💻 Running in CLI mode...")
            
            # Simple CLI status loop
            while not self.shutdown_event.is_set():
                # Display status
                account_info = self.mt5_connector.get_account_info() if self.mt5_connector else {}
                
                print(f"\n{'='*60}")
                print(f"📊 TRADEMAESTRO STATUS - {datetime.now().strftime('%H:%M:%S')}")
                print(f"{'='*60}")
                print(f"🔌 MT5 Connection: {'✅ Connected' if self.is_connected else '❌ Disconnected'}")
                print(f"💰 Balance: ${account_info.get('balance', 0):.2f}")
                print(f"💎 Equity: ${account_info.get('equity', 0):.2f}")
                print(f"📊 Profit: ${account_info.get('profit', 0):.2f}")
                print(f"{'='*60}")
                
                # Wait or check for shutdown
                for _ in range(10):  # 10 second intervals
                    if self.shutdown_event.is_set():
                        break
                    time.sleep(1)
            
        except KeyboardInterrupt:
            self.logger.info("🛑 CLI interrupted by user")
        except Exception as e:
            self.logger.error(f"❌ CLI runtime error: {e}")
            traceback.print_exc()
    
    def shutdown(self):
        """Clean shutdown"""
        try:
            self.logger.info("🛑 Shutting down TradeMaestro...")
            
            # Set shutdown flag
            self.shutdown_event.set()
            self.is_running = False
            
            # Stop strategy
            if self.strategy_manager:
                try:
                    self.strategy_manager.stop_strategy()
                except:
                    pass
            
            # Disconnect MT5
            if self.mt5_connector:
                try:
                    self.mt5_connector.disconnect()
                except:
                    pass
            
            # Wait for threads
            if self.monitoring_thread and self.monitoring_thread.is_alive():
                self.monitoring_thread.join(timeout=5)
            
            # Save configuration
            self.config.save_configuration()
            
            self.logger.info("✅ TradeMaestro shutdown completed")
            
        except Exception as e:
            self.logger.error(f"❌ Shutdown error: {e}")


def main():
    """Main entry point"""
    print("🚀 TradeMaestro Windows Bot v2.0")
    print("=" * 50)
    
    bot = None
    try:
        # Create bot instance
        bot = TradeMaestroWindows()
        
        # Startup
        if not bot.startup():
            print("❌ Bot startup failed")
            return 1
        
        # Determine run mode
        if GUI_AVAILABLE and not bot.config.get("FORCE_CLI_MODE", False):
            print("🖥️ Starting GUI mode...")
            exit_code = bot.run_gui()
        else:
            print("💻 Starting CLI mode...")
            bot.run_cli()
            exit_code = 0
        
        return exit_code
        
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
        return 0
    except Exception as e:
        print(f"❌ Critical error: {e}")
        traceback.print_exc()
        return 1
    finally:
        if bot:
            bot.shutdown()


if __name__ == "__main__":
    sys.exit(main())