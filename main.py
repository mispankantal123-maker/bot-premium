"""
TradeMaestro Trading Bot - Main Entry Point
Windows-optimized trading bot with PySide6 GUI and MetaTrader5 integration
"""

import sys
import os
from pathlib import Path
import threading
import signal
import traceback
from typing import Optional

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Import PySide6 components
try:
    from PySide6.QtWidgets import QApplication, QMessageBox
    from PySide6.QtCore import QTimer, Signal, QObject, QThread
    from PySide6.QtGui import QIcon
except ImportError:
    print("PySide6 not found. Please install it using: pip install PySide6")
    sys.exit(1)

# Import our modules
from config import Config, load_environment
from utils.logger import Logger, setup_logging
from utils.mt5_connector import MT5Connector
from utils.mock_mt5 import MockMT5Connector
from utils.performance import PerformanceTracker
from gui.main_window import MainWindow
from strategies import StrategyManager

class TradeMaestroApp(QObject):
    """
    Main application class that orchestrates the trading bot
    Handles initialization, shutdown, and coordination between components
    """
    
    # Signals for thread-safe GUI updates
    status_update = Signal(str)
    error_occurred = Signal(str)
    
    def __init__(self):
        super().__init__()
        self.config = None
        self.logger = None
        self.mt5_connector = None
        self.strategy_manager = None
        self.performance_tracker = None
        self.main_window = None
        self.trading_thread = None
        self.is_running = False
        self.is_trading = False
        
    def initialize(self) -> bool:
        """
        Initialize all application components
        Returns True if successful, False otherwise
        """
        try:
            # Load environment and configuration
            load_environment()
            self.config = Config()
            
            # Setup logging system
            setup_logging(self.config.LOG_LEVEL, self.config.LOG_FILE)
            self.logger = Logger(__name__)
            self.logger.info("🚀 TradeMaestro starting up...")
            
            # Initialize performance tracker
            self.performance_tracker = PerformanceTracker()
            
            # Initialize MT5 connector (use mock in demo mode)
            if self.config.DEMO_MODE:
                self.logger.info("🎭 Running in demo mode with mock MT5 connector")
                self.mt5_connector = MockMT5Connector(self.config)
            else:
                self.mt5_connector = MT5Connector(self.config)
            
            # Initialize strategy manager
            self.strategy_manager = StrategyManager(
                self.mt5_connector,
                self.performance_tracker,
                self.config
            )
            
            # Create main window
            self.main_window = MainWindow(
                self.mt5_connector,
                self.strategy_manager,
                self.performance_tracker,
                self.config
            )
            
            # Connect signals
            self.setup_signals()
            
            self.logger.info("✅ TradeMaestro initialized successfully")
            return True
            
        except Exception as e:
            error_msg = f"❌ Failed to initialize TradeMaestro: {str(e)}"
            print(error_msg)
            if self.logger:
                self.logger.error(error_msg)
                self.logger.error(f"Traceback: {traceback.format_exc()}")
            
            # Show error dialog if possible
            try:
                QMessageBox.critical(None, "Initialization Error", error_msg)
            except:
                pass
            
            return False
    
    def setup_signals(self):
        """Setup signal connections for thread-safe communication"""
        try:
            if self.main_window:
                # Connect main window signals
                self.main_window.start_trading.connect(self.start_trading)
                self.main_window.stop_trading.connect(self.stop_trading)
                self.main_window.shutdown_requested.connect(self.shutdown)
                
                # Connect our signals to main window
                self.status_update.connect(self.main_window.update_status)
                self.error_occurred.connect(self.main_window.show_error)
                
            if self.mt5_connector:
                # Connect MT5 connector signals
                self.mt5_connector.connection_status_changed.connect(
                    self.main_window.update_connection_status
                )
                
            if self.strategy_manager:
                # Connect strategy manager signals
                self.strategy_manager.trade_executed.connect(
                    self.main_window.update_trade_info
                )
                self.strategy_manager.signal_generated.connect(
                    self.main_window.update_signals
                )
                
        except Exception as e:
            self.logger.error(f"Failed to setup signals: {str(e)}")
    
    def start_trading(self):
        """Start the trading process in a separate thread"""
        if self.is_trading:
            self.logger.warning("Trading is already running")
            return
            
        try:
            self.logger.info("🎯 Starting trading process...")
            
            # Connect to MT5 if not connected
            if not self.mt5_connector.is_connected():
                if not self.mt5_connector.connect():
                    self.error_occurred.emit("Failed to connect to MetaTrader 5")
                    return
            
            # Start trading in background thread
            self.trading_thread = TradingThread(
                self.strategy_manager,
                self.config
            )
            self.trading_thread.status_update.connect(self.status_update)
            self.trading_thread.error_occurred.connect(self.error_occurred)
            self.trading_thread.finished.connect(self.on_trading_finished)
            
            self.trading_thread.start()
            self.is_trading = True
            
            self.status_update.emit("Trading started successfully")
            self.logger.info("✅ Trading process started")
            
        except Exception as e:
            error_msg = f"Failed to start trading: {str(e)}"
            self.logger.error(error_msg)
            self.error_occurred.emit(error_msg)
    
    def stop_trading(self):
        """Stop the trading process"""
        if not self.is_trading:
            self.logger.warning("Trading is not running")
            return
            
        try:
            self.logger.info("⏹️ Stopping trading process...")
            
            if self.trading_thread and self.trading_thread.isRunning():
                self.trading_thread.stop()
                self.trading_thread.wait(5000)  # Wait up to 5 seconds
                
                if self.trading_thread.isRunning():
                    self.logger.warning("Force terminating trading thread")
                    self.trading_thread.terminate()
                    self.trading_thread.wait()
            
            self.is_trading = False
            self.status_update.emit("Trading stopped")
            self.logger.info("✅ Trading process stopped")
            
        except Exception as e:
            error_msg = f"Error stopping trading: {str(e)}"
            self.logger.error(error_msg)
            self.error_occurred.emit(error_msg)
    
    def on_trading_finished(self):
        """Called when trading thread finishes"""
        self.is_trading = False
        self.trading_thread = None
        self.status_update.emit("Trading session ended")
        self.logger.info("Trading thread finished")
    
    def shutdown(self):
        """Gracefully shutdown the application"""
        try:
            self.logger.info("🔄 Shutting down TradeMaestro...")
            
            # Stop trading if running
            if self.is_trading:
                self.stop_trading()
            
            # Disconnect from MT5
            if self.mt5_connector:
                self.mt5_connector.disconnect()
            
            # Close main window
            if self.main_window:
                self.main_window.close()
            
            # Save performance data
            if self.performance_tracker:
                self.performance_tracker.save_session_data()
            
            self.logger.info("✅ TradeMaestro shutdown complete")
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {str(e)}")
        
        finally:
            QApplication.quit()


class TradingThread(QThread):
    """
    Background thread for trading operations
    Prevents GUI freezing during intensive operations
    """
    
    status_update = Signal(str)
    error_occurred = Signal(str)
    
    def __init__(self, strategy_manager, config):
        super().__init__()
        self.strategy_manager = strategy_manager
        self.config = config
        self.running = False
        self.logger = Logger(__name__)
    
    def run(self):
        """Main trading loop"""
        self.running = True
        self.logger.info("Trading thread started")
        
        try:
            while self.running:
                # Execute trading cycle
                self.strategy_manager.execute_trading_cycle()
                
                # Sleep for configured interval
                self.msleep(self.config.TRADING_INTERVAL_MS)
                
        except Exception as e:
            error_msg = f"Trading thread error: {str(e)}"
            self.logger.error(error_msg)
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            self.error_occurred.emit(error_msg)
        
        finally:
            self.logger.info("Trading thread finished")
    
    def stop(self):
        """Stop the trading thread"""
        self.running = False


def signal_handler(signum, frame):
    """Handle system signals for graceful shutdown"""
    print(f"\nReceived signal {signum}, shutting down gracefully...")
    QApplication.quit()


def main():
    """Main application entry point"""
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create QApplication
    app = QApplication(sys.argv)
    app.setApplicationName("TradeMaestro")
    app.setApplicationVersion("2.0")
    app.setOrganizationName("TradeMaestro")
    
    # Set application icon if available
    icon_path = project_root / "assets" / "icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    
    # Create and initialize main application
    trade_app = TradeMaestroApp()
    
    if not trade_app.initialize():
        print("❌ Failed to initialize application")
        sys.exit(1)
    
    # Show main window
    if trade_app.main_window:
        trade_app.main_window.show()
    
    # Handle application quit
    app.aboutToQuit.connect(trade_app.shutdown)
    
    # Start event loop
    try:
        exit_code = app.exec()
        print(f"Application exited with code: {exit_code}")
        sys.exit(exit_code)
        
    except KeyboardInterrupt:
        print("\nApplication interrupted by user")
        trade_app.shutdown()
        sys.exit(0)
        
    except Exception as e:
        print(f"Unhandled exception: {str(e)}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
