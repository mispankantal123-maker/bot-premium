"""
TradeMaestro Simple Startup Test
Minimal version to test Windows compatibility
"""

import sys
import os
import logging
from pathlib import Path

# Simple logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('simple_test.log', encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)

def test_startup():
    """Test basic startup requirements"""
    logger.info("🚀 TradeMaestro Simple Startup Test")
    
    try:
        # Test 1: Directory creation
        logger.info("📁 Testing directory creation...")
        test_dirs = ['data', 'logs', 'cache']
        for dirname in test_dirs:
            Path(dirname).mkdir(exist_ok=True)
            logger.info(f"✅ Created: {dirname}")
        
        # Test 2: Configuration
        logger.info("⚙️ Testing configuration...")
        config = {
            "lot_size": 0.01,
            "symbols": ["EURUSD", "GBPUSD"],
            "demo_mode": True
        }
        logger.info(f"✅ Config loaded: {config}")
        
        # Test 3: Import testing
        logger.info("📦 Testing imports...")
        import pandas as pd
        import numpy as np
        logger.info("✅ Data libraries OK")
        
        try:
            import psutil
            logger.info("✅ System monitoring OK")
        except ImportError:
            logger.warning("⚠️ System monitoring not available")
        
        # Test 4: Mock MT5 connector
        logger.info("🔌 Testing mock connector...")
        
        class SimpleMockMT5:
            def __init__(self):
                self.connected = False
                self.balance = 10000.0
                self.equity = 10000.0
                
            def connect(self):
                logger.info("🔄 Mock connection...")
                self.connected = True
                logger.info("✅ Mock connected")
                return True
                
            def get_account_info(self):
                return {
                    "balance": self.balance,
                    "equity": self.equity,
                    "profit": self.equity - self.balance
                }
        
        # Test mock connector
        mt5 = SimpleMockMT5()
        if mt5.connect():
            account = mt5.get_account_info()
            logger.info(f"💰 Account: Balance=${account['balance']}, Equity=${account['equity']}")
        
        # Test 5: Strategy simulation
        logger.info("🎯 Testing strategy simulation...")
        
        class SimpleStrategy:
            def __init__(self, name):
                self.name = name
                self.active = False
                
            def start(self):
                self.active = True
                logger.info(f"▶️ Strategy '{self.name}' started")
                
            def stop(self):
                self.active = False
                logger.info(f"⏹️ Strategy '{self.name}' stopped")
        
        strategy = SimpleStrategy("scalping")
        strategy.start()
        strategy.stop()
        
        logger.info("✅ All startup tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Startup test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def run_demo():
    """Run simple demo loop"""
    logger.info("🎬 Starting demo loop...")
    
    class SimpleMockMT5:
        def __init__(self):
            self.connected = False
            self.balance = 10000.0
            self.equity = 10000.0
            
        def connect(self):
            logger.info("🔄 Mock connection...")
            self.connected = True
            logger.info("✅ Mock connected")
            return True
            
        def get_account_info(self):
            return {
                "balance": self.balance,
                "equity": self.equity,
                "profit": self.equity - self.balance
            }
    
    mt5 = SimpleMockMT5()
    mt5.connect()
    
    import time
    import random
    
    for i in range(5):
        # Simulate price fluctuation
        change = random.uniform(-50, 50)
        mt5.equity = mt5.balance + change
        
        account = mt5.get_account_info()
        
        logger.info("="*50)
        logger.info(f"📊 DEMO STATUS #{i+1}")
        logger.info("="*50)
        logger.info(f"💰 Balance: ${account['balance']:.2f}")
        logger.info(f"💎 Equity: ${account['equity']:.2f}")
        logger.info(f"📊 Profit: ${account['profit']:.2f}")
        logger.info("="*50)
        
        time.sleep(2)
    
    logger.info("🎬 Demo completed successfully")

if __name__ == "__main__":
    print("🚀 TradeMaestro Simple Test")
    print("="*40)
    
    if test_startup():
        print("✅ Startup test passed")
        run_demo()
    else:
        print("❌ Startup test failed")
        sys.exit(1)
    
    print("🎉 All tests completed!")