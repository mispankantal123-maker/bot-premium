"""
TradeMaestro Trading Bot - Command Line Interface
Alternative CLI interface for environments without GUI support
"""

import sys
import os
import time
import threading
from pathlib import Path
from datetime import datetime
import signal

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Import our modules
from config import Config, load_environment
from utils.logger import Logger, setup_logging
from utils.mock_mt5 import MockMT5Connector
from utils.performance import PerformanceTracker
from strategies import StrategyManager


class TradeMaestroCLI:
    """
    Command-line interface for TradeMaestro trading bot
    Provides basic trading functionality without GUI requirements
    """
    
    def __init__(self):
        self.config = None
        self.logger = None
        self.mt5_connector = None
        self.strategy_manager = None
        self.performance_tracker = None
        self.is_running = False
        self.is_trading = False
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        print("\n🛑 Shutdown signal received. Stopping TradeMaestro...")
        self.shutdown()
        sys.exit(0)
    
    def initialize(self) -> bool:
        """Initialize all application components"""
        try:
            # Load environment and configuration
            load_environment()
            self.config = Config()
            
            # Setup logging system
            setup_logging(self.config.LOG_LEVEL, self.config.LOG_FILE)
            self.logger = Logger(__name__)
            
            print("🚀 TradeMaestro CLI starting up...")
            self.logger.info("🚀 TradeMaestro CLI starting up...")
            
            # Initialize performance tracker
            self.performance_tracker = PerformanceTracker(self.config)
            print("✅ Performance tracker initialized")
            
            # Initialize mock MT5 connector (CLI always uses demo mode)
            self.logger.info("🎭 Running in CLI demo mode with mock MT5 connector")
            self.mt5_connector = MockMT5Connector(self.config)
            print("✅ Mock MT5 connector initialized")
            
            # Initialize strategy manager
            self.strategy_manager = StrategyManager(
                self.mt5_connector,
                self.performance_tracker,
                self.config
            )
            print("✅ Strategy manager initialized")
            
            # Connect signals
            self.setup_connections()
            
            print("✅ TradeMaestro CLI initialized successfully")
            self.logger.info("✅ TradeMaestro CLI initialized successfully")
            return True
            
        except Exception as e:
            error_msg = f"Failed to initialize TradeMaestro CLI: {str(e)}"
            print(f"❌ {error_msg}")
            if self.logger:
                self.logger.error(error_msg)
            return False
    
    def setup_connections(self):
        """Setup signal connections"""
        try:
            # MT5 connector signals
            self.mt5_connector.connection_status_changed.connect(self.on_connection_status_changed)
            self.mt5_connector.account_info_updated.connect(self.on_account_info_updated)
            self.mt5_connector.error_occurred.connect(self.on_error_occurred)
            
            # Performance tracker signals
            self.performance_tracker.trade_recorded.connect(self.on_trade_recorded)
            self.performance_tracker.performance_updated.connect(self.on_performance_updated)
            
        except Exception as e:
            self.logger.error(f"Error setting up connections: {str(e)}")
    
    def on_connection_status_changed(self, connected: bool, message: str):
        """Handle connection status changes"""
        status = "Connected" if connected else "Disconnected"
        print(f"🔌 MT5 Status: {status} - {message}")
        self.logger.info(f"MT5 connection status: {connected} - {message}")
    
    def on_account_info_updated(self, account_info: dict):
        """Handle account info updates"""
        balance = account_info.get('balance', 0)
        equity = account_info.get('equity', 0)
        profit = account_info.get('profit', 0)
        print(f"💰 Account: Balance=${balance:.2f}, Equity=${equity:.2f}, Profit=${profit:.2f}")
    
    def on_error_occurred(self, error_message: str):
        """Handle errors"""
        print(f"❌ Error: {error_message}")
        self.logger.error(f"MT5 Error: {error_message}")
    
    def on_trade_recorded(self, trade_data: dict):
        """Handle new trades"""
        symbol = trade_data.get('symbol', 'Unknown')
        trade_type = trade_data.get('type', 'Unknown')
        profit = trade_data.get('profit', 0)
        print(f"📊 Trade: {symbol} {trade_type} - Profit: ${profit:.2f}")
    
    def on_performance_updated(self, performance_data: dict):
        """Handle performance updates"""
        trades = performance_data.get('total_trades', 0)
        win_rate = performance_data.get('win_rate', 0)
        total_profit = performance_data.get('total_profit', 0)
        print(f"📈 Performance: {trades} trades, {win_rate:.1f}% win rate, ${total_profit:.2f} profit")
    
    def connect_mt5(self) -> bool:
        """Connect to MT5"""
        print("🔄 Connecting to MT5...")
        success = self.mt5_connector.connect()
        if success:
            print("✅ MT5 connected successfully")
        else:
            print("❌ MT5 connection failed")
        return success
    
    def start_trading(self):
        """Start trading operations"""
        if not self.mt5_connector.is_connected():
            print("❌ Cannot start trading: MT5 not connected")
            return
        
        if self.is_trading:
            print("⚠️ Trading already active")
            return
        
        print("▶️ Starting trading operations...")
        self.is_trading = True
        
        # Start strategy
        try:
            self.strategy_manager.start_strategy("scalping")
            print("✅ Trading started successfully")
            self.logger.info("Trading operations started")
        except Exception as e:
            print(f"❌ Failed to start trading: {str(e)}")
            self.is_trading = False
    
    def stop_trading(self):
        """Stop trading operations"""
        if not self.is_trading:
            print("⚠️ Trading not active")
            return
        
        print("⏹️ Stopping trading operations...")
        self.is_trading = False
        
        try:
            self.strategy_manager.stop_strategy()
            print("✅ Trading stopped successfully")
            self.logger.info("Trading operations stopped")
        except Exception as e:
            print(f"❌ Error stopping trading: {str(e)}")
    
    def show_status(self):
        """Display current status"""
        print("\n" + "="*60)
        print("📊 TRADEMAESTRO STATUS")
        print("="*60)
        
        # Connection status
        connected = self.mt5_connector.is_connected() if self.mt5_connector else False
        print(f"🔌 MT5 Connection: {'✅ Connected' if connected else '❌ Disconnected'}")
        
        # Trading status
        print(f"📈 Trading Status: {'✅ Active' if self.is_trading else '❌ Stopped'}")
        
        # Account info
        if connected:
            account_info = self.mt5_connector.get_account_info()
            print(f"💰 Balance: ${account_info.get('balance', 0):.2f}")
            print(f"💎 Equity: ${account_info.get('equity', 0):.2f}")
            print(f"📊 Profit: ${account_info.get('profit', 0):.2f}")
        
        # Performance info
        if self.performance_tracker:
            performance = self.performance_tracker.get_performance_summary()
            print(f"🎯 Total Trades: {performance.get('total_trades', 0)}")
            print(f"📈 Win Rate: {performance.get('win_rate', 0):.1f}%")
            print(f"💵 Total Profit: ${performance.get('total_profit', 0):.2f}")
        
        print("="*60)
    
    def run_interactive(self):
        """Run interactive command interface"""
        if not self.initialize():
            return
        
        print("\n🎯 TradeMaestro CLI Interactive Mode")
        print("Type 'help' for available commands")
        
        self.is_running = True
        
        while self.is_running:
            try:
                command = input("\nTradeMaestro> ").strip().lower()
                
                if command == 'help':
                    self.show_help()
                elif command == 'connect':
                    self.connect_mt5()
                elif command == 'start':
                    self.start_trading()
                elif command == 'stop':
                    self.stop_trading()
                elif command == 'status':
                    self.show_status()
                elif command == 'exit' or command == 'quit':
                    break
                elif command == '':
                    continue
                else:
                    print(f"❌ Unknown command: {command}. Type 'help' for available commands.")
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"❌ Error: {str(e)}")
        
        print("\n👋 Shutting down TradeMaestro CLI...")
        self.shutdown()
    
    def show_help(self):
        """Show available commands"""
        print("\n📚 Available Commands:")
        print("connect  - Connect to MT5")
        print("start    - Start trading")
        print("stop     - Stop trading") 
        print("status   - Show current status")
        print("help     - Show this help")
        print("exit     - Exit TradeMaestro")
    
    def run_demo(self):
        """Run a simple demo sequence"""
        if not self.initialize():
            return
        
        print("\n🎭 Running TradeMaestro Demo Sequence...")
        
        # Connect to MT5
        if self.connect_mt5():
            time.sleep(2)
            
            # Show initial status
            self.show_status()
            time.sleep(2)
            
            # Start trading
            self.start_trading()
            time.sleep(5)
            
            # Show status during trading
            self.show_status()
            time.sleep(5)
            
            # Stop trading
            self.stop_trading()
            time.sleep(2)
            
            # Final status
            self.show_status()
        
        print("\n🎬 Demo completed")
        self.shutdown()
    
    def shutdown(self):
        """Cleanup and shutdown"""
        try:
            if self.is_trading:
                self.stop_trading()
            
            if self.mt5_connector and self.mt5_connector.is_connected():
                self.mt5_connector.disconnect()
            
            self.is_running = False
            
            if self.logger:
                self.logger.info("TradeMaestro CLI shutdown completed")
            
        except Exception as e:
            print(f"Error during shutdown: {str(e)}")


def main():
    """Main entry point"""
    cli = TradeMaestroCLI()
    
    # Check command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == 'demo':
            cli.run_demo()
        elif sys.argv[1] == 'interactive':
            cli.run_interactive()
        else:
            print("Usage: python main_cli.py [demo|interactive]")
            print("  demo        - Run automated demo sequence")
            print("  interactive - Run interactive command interface")
    else:
        # Default to interactive mode
        cli.run_interactive()


if __name__ == "__main__":
    main()