"""
TradeMaestro Final - Windows Compatible Trading Bot
Complete implementation dengan error handling robust untuk Windows
"""

import sys
import os
import logging
import threading
import time
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
import traceback

# Setup basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('trademaestro.log', encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)

# Import required libraries with error handling
try:
    import pandas as pd
    import numpy as np
    logger.info("✅ Data processing libraries loaded")
except ImportError as e:
    logger.error(f"❌ Missing data libraries: {e}")
    sys.exit(1)

try:
    import psutil
    PSUTIL_AVAILABLE = True
    logger.info("✅ System monitoring available")
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("⚠️ System monitoring not available")

try:
    import ta
    TA_AVAILABLE = True
    logger.info("✅ Technical analysis library available")
except ImportError:
    TA_AVAILABLE = False
    logger.warning("⚠️ Technical analysis library not available")


class WindowsConfig:
    """Windows-optimized configuration management"""
    
    def __init__(self):
        self.config_file = Path("trademaestro_config.json")
        self.default_config = {
            # Trading Settings
            "lot_size": 0.01,
            "max_positions": 5,
            "symbols": ["EURUSD", "GBPUSD", "USDJPY"],
            "timeframe": "M15",
            "demo_mode": True,
            
            # Risk Management
            "max_risk_per_trade": 0.02,
            "max_daily_loss": 0.05,
            "stop_loss_pips": 50,
            "take_profit_pips": 100,
            
            # Bot Settings
            "auto_start": False,
            "refresh_rate": 2,
            "log_level": "INFO",
            
            # Directories
            "data_dir": "data",
            "logs_dir": "logs",
            "cache_dir": "cache"
        }
        
        self.config = self.load_config()
        self.setup_directories()
        logger.info("✅ Configuration initialized")
    
    def load_config(self):
        """Load configuration from file with fallback to defaults"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    file_config = json.load(f)
                config = self.default_config.copy()
                config.update(file_config)
                logger.info("✅ Configuration loaded from file")
                return config
        except Exception as e:
            logger.warning(f"⚠️ Config file error: {e}")
        
        logger.info("Using default configuration")
        return self.default_config.copy()
    
    def save_config(self):
        """Save current configuration to file"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            logger.info("✅ Configuration saved")
        except Exception as e:
            logger.error(f"❌ Failed to save config: {e}")
    
    def setup_directories(self):
        """Create required directories"""
        dirs = [
            self.config["data_dir"],
            self.config["logs_dir"], 
            self.config["cache_dir"]
        ]
        
        for directory in dirs:
            Path(directory).mkdir(exist_ok=True, parents=True)
            logger.info(f"📁 Directory ready: {directory}")


class MockMT5Connector:
    """Mock MetaTrader5 connector for demo mode and testing"""
    
    def __init__(self, config):
        self.config = config
        self.connected = False
        self.account_info = {
            "balance": 10000.0,
            "equity": 10000.0,
            "profit": 0.0,
            "margin": 0.0,
            "free_margin": 10000.0
        }
        self.positions = []
        self.symbols = config["symbols"]
        self.prices = {symbol: {"bid": 1.1000, "ask": 1.1002} for symbol in self.symbols}
        self.price_thread = None
        self.running = False
        logger.info("🎭 Mock MT5 connector initialized")
    
    def connect(self):
        """Simulate MT5 connection"""
        try:
            logger.info("🔄 Connecting to MT5 (Demo Mode)...")
            time.sleep(1)  # Simulate connection delay
            
            self.connected = True
            self.running = True
            self.start_price_simulation()
            
            logger.info("✅ MT5 connected successfully (Demo Mode)")
            return True
        except Exception as e:
            logger.error(f"❌ Connection failed: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from MT5"""
        try:
            self.running = False
            self.connected = False
            
            if self.price_thread and self.price_thread.is_alive():
                self.price_thread.join(timeout=3)
            
            logger.info("🔌 MT5 disconnected")
        except Exception as e:
            logger.error(f"❌ Disconnect error: {e}")
    
    def start_price_simulation(self):
        """Start realistic price simulation"""
        def simulate_prices():
            import random
            
            while self.running:
                try:
                    for symbol in self.symbols:
                        # Simulate price movement
                        change = random.uniform(-0.0010, 0.0010)
                        current_bid = self.prices[symbol]["bid"]
                        new_bid = max(0.5, current_bid + change)
                        
                        self.prices[symbol] = {
                            "bid": round(new_bid, 5),
                            "ask": round(new_bid + 0.0002, 5)
                        }
                    
                    # Update account equity based on positions
                    total_profit = sum(pos.get("profit", 0) for pos in self.positions)
                    self.account_info["profit"] = total_profit
                    self.account_info["equity"] = self.account_info["balance"] + total_profit
                    
                    time.sleep(2)  # Update every 2 seconds
                    
                except Exception as e:
                    logger.error(f"❌ Price simulation error: {e}")
                    time.sleep(5)
        
        self.price_thread = threading.Thread(target=simulate_prices, daemon=True)
        self.price_thread.start()
        logger.info("📈 Price simulation started")
    
    def get_account_info(self):
        """Get current account information"""
        return self.account_info.copy()
    
    def get_symbol_price(self, symbol):
        """Get current price for symbol"""
        return self.prices.get(symbol, {"bid": 1.0000, "ask": 1.0002})
    
    def place_order(self, symbol, order_type, volume, price=None):
        """Simulate order placement"""
        try:
            current_price = self.get_symbol_price(symbol)
            entry_price = current_price["ask"] if order_type == "BUY" else current_price["bid"]
            
            position = {
                "ticket": len(self.positions) + 1000,
                "symbol": symbol,
                "type": order_type,
                "volume": volume,
                "price_open": entry_price,
                "profit": 0.0,
                "time": datetime.now()
            }
            
            self.positions.append(position)
            logger.info(f"✅ Order placed: {symbol} {order_type} {volume}")
            return position
            
        except Exception as e:
            logger.error(f"❌ Order placement failed: {e}")
            return None


class TradingStrategy:
    """Base trading strategy with simple scalping logic"""
    
    def __init__(self, mt5_connector, config):
        self.mt5 = mt5_connector
        self.config = config
        self.active = False
        self.trades_today = 0
        self.max_trades_per_day = 10
        logger.info("🎯 Trading strategy initialized")
    
    def start(self):
        """Start strategy execution"""
        self.active = True
        logger.info("▶️ Trading strategy started")
    
    def stop(self):
        """Stop strategy execution"""
        self.active = False
        logger.info("⏹️ Trading strategy stopped")
    
    def analyze_market(self, symbol):
        """Simple market analysis"""
        try:
            price_data = self.mt5.get_symbol_price(symbol)
            
            # Simple analysis: buy if price ends in even number, sell if odd
            price_str = str(price_data["bid"]).replace(".", "")
            last_digit = int(price_str[-1])
            
            if last_digit % 2 == 0:
                return "BUY", 0.8  # Signal, confidence
            else:
                return "SELL", 0.7
                
        except Exception as e:
            logger.error(f"❌ Analysis error for {symbol}: {e}")
            return None, 0
    
    def execute_trade(self, symbol, signal):
        """Execute trade based on signal"""
        try:
            if self.trades_today >= self.max_trades_per_day:
                logger.warning("⚠️ Max trades per day reached")
                return False
            
            volume = self.config["lot_size"]
            result = self.mt5.place_order(symbol, signal, volume)
            
            if result:
                self.trades_today += 1
                logger.info(f"✅ Trade executed: {symbol} {signal}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Trade execution error: {e}")
            return False
    
    def process_symbol(self, symbol):
        """Process trading logic for one symbol"""
        try:
            signal, confidence = self.analyze_market(symbol)
            
            if signal and confidence > 0.7:
                return self.execute_trade(symbol, signal)
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Symbol processing error: {e}")
            return False


class TradeMaestroBot:
    """Main TradeMaestro trading bot class"""
    
    def __init__(self):
        logger.info("🚀 Initializing TradeMaestro Bot...")
        
        # Initialize components
        self.config_manager = WindowsConfig()
        self.config = self.config_manager.config
        
        self.mt5_connector = MockMT5Connector(self.config)
        self.strategy = TradingStrategy(self.mt5_connector, self.config)
        
        # State management
        self.running = False
        self.trading_thread = None
        self.monitoring_thread = None
        self.shutdown_event = threading.Event()
        
        # Statistics
        self.start_time = None
        self.total_trades = 0
        self.total_profit = 0.0
        
        logger.info("✅ TradeMaestro Bot initialized successfully")
    
    def startup_checks(self):
        """Perform startup validation"""
        logger.info("🔍 Performing startup checks...")
        
        try:
            # Check configuration
            if not self.config.get("symbols"):
                logger.error("❌ No trading symbols configured")
                return False
            
            # Check system resources
            if PSUTIL_AVAILABLE:
                memory = psutil.virtual_memory()
                if memory.percent > 90:
                    logger.warning(f"⚠️ High memory usage: {memory.percent}%")
                
                cpu_count = psutil.cpu_count()
                logger.info(f"💻 System: {cpu_count} CPUs, {memory.total // (1024**3)}GB RAM")
            
            # Test file permissions
            test_file = Path("startup_test.tmp")
            try:
                test_file.write_text("test")
                test_file.unlink()
                logger.info("✅ File permissions OK")
            except Exception as e:
                logger.error(f"❌ File permission error: {e}")
                return False
            
            logger.info("✅ All startup checks passed")
            return True
            
        except Exception as e:
            logger.error(f"❌ Startup checks failed: {e}")
            return False
    
    def start_trading(self):
        """Start the trading bot"""
        try:
            logger.info("🚀 Starting TradeMaestro Bot...")
            
            # Startup checks
            if not self.startup_checks():
                return False
            
            # Connect to MT5
            if not self.mt5_connector.connect():
                logger.error("❌ Failed to connect to MT5")
                return False
            
            # Start strategy
            self.strategy.start()
            
            # Start trading loop
            self.running = True
            self.start_time = datetime.now()
            
            self.trading_thread = threading.Thread(target=self.trading_loop, daemon=True)
            self.trading_thread.start()
            
            self.monitoring_thread = threading.Thread(target=self.monitoring_loop, daemon=True)
            self.monitoring_thread.start()
            
            logger.info("✅ TradeMaestro Bot started successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to start bot: {e}")
            traceback.print_exc()
            return False
    
    def stop_trading(self):
        """Stop the trading bot"""
        try:
            logger.info("🛑 Stopping TradeMaestro Bot...")
            
            # Set shutdown flag
            self.running = False
            self.shutdown_event.set()
            
            # Stop strategy
            self.strategy.stop()
            
            # Wait for threads
            if self.trading_thread and self.trading_thread.is_alive():
                self.trading_thread.join(timeout=5)
            
            if self.monitoring_thread and self.monitoring_thread.is_alive():
                self.monitoring_thread.join(timeout=5)
            
            # Disconnect MT5
            self.mt5_connector.disconnect()
            
            # Save configuration
            self.config_manager.save_config()
            
            logger.info("✅ TradeMaestro Bot stopped successfully")
            
        except Exception as e:
            logger.error(f"❌ Error stopping bot: {e}")
    
    def trading_loop(self):
        """Main trading loop"""
        logger.info("🔄 Trading loop started")
        
        while self.running and not self.shutdown_event.is_set():
            try:
                # Process each symbol
                for symbol in self.config["symbols"]:
                    if not self.running:
                        break
                    
                    if self.strategy.process_symbol(symbol):
                        self.total_trades += 1
                
                # Wait before next cycle
                self.shutdown_event.wait(timeout=self.config["refresh_rate"])
                
            except Exception as e:
                logger.error(f"❌ Trading loop error: {e}")
                time.sleep(5)
        
        logger.info("🔄 Trading loop stopped")
    
    def monitoring_loop(self):
        """System monitoring loop"""
        logger.info("👁️ Monitoring loop started")
        
        while self.running and not self.shutdown_event.is_set():
            try:
                account = self.mt5_connector.get_account_info()
                
                # Log status every 30 seconds
                logger.info("="*60)
                logger.info(f"📊 TRADEMAESTRO STATUS - {datetime.now().strftime('%H:%M:%S')}")
                logger.info("="*60)
                logger.info(f"🔌 MT5 Connection: {'✅ Connected' if self.mt5_connector.connected else '❌ Disconnected'}")
                logger.info(f"📈 Trading Status: {'▶️ Active' if self.strategy.active else '❌ Stopped'}")
                logger.info(f"💰 Balance: ${account['balance']:.2f}")
                logger.info(f"💎 Equity: ${account['equity']:.2f}")
                logger.info(f"📊 Profit: ${account['profit']:.2f}")
                logger.info(f"🎯 Total Trades: {self.total_trades}")
                logger.info(f"📈 Trades Today: {self.strategy.trades_today}")
                logger.info("="*60)
                
                # Wait 30 seconds
                self.shutdown_event.wait(timeout=30)
                
            except Exception as e:
                logger.error(f"❌ Monitoring error: {e}")
                time.sleep(60)
        
        logger.info("👁️ Monitoring loop stopped")
    
    def run_cli_demo(self):
        """Run CLI demo mode"""
        logger.info("💻 Running CLI demo mode...")
        
        if not self.start_trading():
            logger.error("❌ Failed to start trading")
            return
        
        try:
            # Run for demo period
            demo_duration = 60  # 1 minute demo
            logger.info(f"🎬 Demo will run for {demo_duration} seconds...")
            
            time.sleep(demo_duration)
            
        except KeyboardInterrupt:
            logger.info("🛑 Demo interrupted by user")
        finally:
            self.stop_trading()
            logger.info("🎬 Demo completed")


def main():
    """Main entry point"""
    print("🚀 TradeMaestro Final - Windows Compatible Bot")
    print("="*50)
    
    bot = None
    try:
        # Create bot instance
        bot = TradeMaestroBot()
        
        # Run demo
        bot.run_cli_demo()
        
        return 0
        
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
        return 0
    except Exception as e:
        logger.error(f"❌ Critical error: {e}")
        traceback.print_exc()
        return 1
    finally:
        if bot:
            bot.stop_trading()


if __name__ == "__main__":
    sys.exit(main())