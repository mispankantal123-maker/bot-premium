# --- Import section (paling atas, tidak boleh kosong) ---
import os
import sys
import platform
import threading
import datetime
import time
import traceback
import csv
import gc
import requests
import pandas as pd
import numpy as np
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Dict, Any, List, Tuple
from tkinter.scrolledtext import ScrolledText

try:
    import MetaTrader5 as mt5
except ImportError:
    os.system("pip install MetaTrader5")
    import MetaTrader5 as mt5


# --- LOGGING FUNCTION ---
def logger(msg: str) -> None:
    """Enhanced logging function with timestamp and GUI integration"""
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    full_msg = f"[{timestamp}] {msg}"
    print(full_msg)

    # Try to log to GUI if available
    try:
        if 'gui' in globals() and gui:
            gui.log(full_msg)
    except Exception as e:
        # Specific exception handling for GUI logging
        print(f"GUI logging failed: {str(e)}")


def validate_numeric_input(value: str,
                           min_val: float = 0.0,
                           max_val: float = None) -> float:
    """Validate and convert numeric input with proper error handling"""
    try:
        numeric_value = float(value.strip())
        if numeric_value < min_val:
            raise ValueError(
                f"Value {numeric_value} is below minimum {min_val}")
        if max_val is not None and numeric_value > max_val:
            raise ValueError(
                f"Value {numeric_value} exceeds maximum {max_val}")
        return numeric_value
    except (ValueError, AttributeError) as e:
        logger(f"Invalid numeric input '{value}': {str(e)}")
        raise


def validate_string_input(value: str, allowed_values: List[str] = None) -> str:
    """Validate string input with specific allowed values"""
    try:
        clean_value = value.strip().upper()
        if not clean_value:
            raise ValueError("Empty string not allowed")
        if allowed_values and clean_value not in allowed_values:
            raise ValueError(
                f"Value '{clean_value}' not in allowed values: {allowed_values}")
        return clean_value
    except AttributeError as e:
        logger(f"Invalid string input: {str(e)}")
        raise


def is_high_impact_news_time() -> bool:
    """Enhanced high-impact news detection with basic time-based filtering"""
    try:
        # Basic time-based news schedule (UTC)
        utc_now = datetime.datetime.now()
        current_hour = utc_now.hour
        current_minute = utc_now.minute
        day_of_week = utc_now.weekday()  # 0=Monday, 6=Sunday

        # Critical news times (UTC) - avoid trading during these
        critical_times = [
            # Daily major news
            (8, 30, 9, 30),  # European session major news
            (12, 30, 14, 30),  # US session major news (NFP, CPI, FOMC, etc)
            (16, 0, 16, 30),  # London Fix

            # Weekly specifics
            (13, 0, 14,
             0) if day_of_week == 2 else None,  # Wednesday FOMC minutes
            (12, 30, 15,
             0) if day_of_week == 4 else None,  # Friday NFP + major data
        ]

        # Remove None values
        critical_times = [t for t in critical_times if t is not None]

        current_time_minutes = current_hour * 60 + current_minute

        for start_h, start_m, end_h, end_m in critical_times:
            start_minutes = start_h * 60 + start_m
            end_minutes = end_h * 60 + end_m

            if start_minutes <= current_time_minutes <= end_minutes:
                logger(
                    f"⚠️ High-impact news time detected: {current_hour:02d}:{current_minute:02d} UTC"
                )
                return True

        return False

    except Exception as e:
        logger(f"❌ Error in news time check: {str(e)}")
        return False  # Continue trading if check fails


def cleanup_resources() -> None:
    """
    Cleanup utility to manage memory usage and resource leaks.

    This function helps prevent memory leaks by explicitly cleaning up
    large data structures and forcing garbage collection.
    """
    try:
        import gc
        # Force garbage collection
        gc.collect()

        # Clear any large global dataframes if they exist
        global session_data
        if 'large_dataframes' in session_data:
            session_data['large_dataframes'].clear()

        logger("🧹 Memory cleanup completed")

    except Exception as e:
        logger(f"⚠️ Memory cleanup error: {str(e)}")


def ensure_log_directory() -> bool:
    """
    Ensure log directory exists with proper error handling.

    Returns:
        bool: True if directory exists or was created successfully
    """
    try:
        log_dir = "logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
            logger(f"📁 Created log directory: {log_dir}")
        return True
    except PermissionError as pe:
        logger(f"❌ Permission denied creating log directory: {str(pe)}")
        return False
    except Exception as e:
        logger(f"❌ Failed to create log directory: {str(e)}")
        return False


# --- CONFIGURATION CONSTANTS ---
MAX_CONNECTION_ATTEMPTS = 5
MAX_CONSECUTIVE_FAILURES = 10
DEFAULT_TIMEOUT_SECONDS = 10
MAX_SYMBOL_TEST_ATTEMPTS = 3
CONNECTION_RETRY_DELAY = 3
GUI_UPDATE_INTERVAL = 1500  # milliseconds
BOT_LOOP_INTERVALS = {
    "HFT": 0.5,
    "Scalping": 1.0,
    "Intraday": 2.0,
    "Arbitrage": 2.0
}

# --- CONFIG & GLOBALS ---
# Use environment variables for security, fallback to defaults for testing
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN",
                           "8365734234:AAH2uTaZPDD47Lnm3y_Tcr6aj3xGL-bVsgk")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5061106648")
bot_running = False
disconnect_count = 0
session_start_balance = None
loss_streak = 0
max_loss_streak = 3
max_drawdown = 0.05
profit_target = 0.10
daily_max_loss = 0.05
trailing_stop_val = 0.0
active_hours = ("00:00", "23:59")  # 24/7 trading capability
position_count = 0
max_positions = 10
current_strategy = "Scalping"
gui = None
trade_lock = threading.Lock()
last_trade_time = {}
mt5_connected = False

# Enhanced Trading Session Management
TRADING_SESSIONS = {
    "Asia": {
        "start": "21:00",
        "end": "06:00",
        "timezone": "UTC",
        "active": True,
        "volatility": "medium",
        "preferred_pairs": ["USDJPY", "AUDUSD", "NZDUSD", "EURJPY", "GBPJPY"]
    },
    "London": {
        "start": "07:00",
        "end": "15:00",
        "timezone": "UTC",
        "active": True,
        "volatility": "high",
        "preferred_pairs": ["EURUSD", "GBPUSD", "EURGBP", "EURJPY", "GBPJPY"]
    },
    "New_York": {
        "start": "15:00",
        "end": "21:00",
        "timezone": "UTC",
        "active": True,
        "volatility": "high",
        "preferred_pairs": ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "AUDUSD"]
    },
    "Overlap_London_NY": {
        "start": "15:00",
        "end": "21:00",
        "timezone": "UTC",
        "active": True,
        "volatility": "very_high",
        "preferred_pairs": ["EURUSD", "GBPUSD", "USDCAD"]
    }
}

# Session-specific trading parameters
SESSION_SETTINGS = {
    "Asia": {
        "max_spread_multiplier": 1.5,
        "volatility_filter": 0.7,
        "trading_intensity": "conservative"
    },
    "London": {
        "max_spread_multiplier": 1.2,
        "volatility_filter": 1.0,
        "trading_intensity": "aggressive"
    },
    "New_York": {
        "max_spread_multiplier": 1.0,
        "volatility_filter": 1.2,
        "trading_intensity": "aggressive"
    },
    "Overlap_London_NY": {
        "max_spread_multiplier": 0.8,
        "volatility_filter": 1.5,
        "trading_intensity": "very_aggressive"
    }
}

# Trading session data
session_data = {
    "start_time": None,
    "start_balance": 0.0,
    "total_trades": 0,
    "winning_trades": 0,
    "losing_trades": 0,
    "total_profit": 0.0,
    "daily_orders": 0,
    "daily_profit": 0.0,
    "last_balance": 0.0,
    "session_equity": 0.0,
    "max_equity": 0.0
}


def connect_mt5() -> bool:
    """Enhanced MT5 connection with comprehensive debugging and better error handling"""
    global mt5_connected
    try:
        import platform
        import sys

        # Shutdown any existing connection first
        try:
            mt5.shutdown()
            time.sleep(1)
        except:
            pass

        logger("🔍 === MT5 CONNECTION DIAGNOSTIC ===")
        logger(f"🔍 Python Version: {sys.version}")
        logger(f"🔍 Python Architecture: {platform.architecture()[0]}")
        logger(f"🔍 Platform: {platform.system()} {platform.release()}")

        # Enhanced MT5 module check
        try:
            import MetaTrader5 as mt5_test
            logger("✅ MetaTrader5 module imported successfully")
            logger(f"🔍 MT5 Module Version: {getattr(mt5_test, '__version__', 'Unknown')}")
        except ImportError as e:
            logger(f"❌ Failed to import MetaTrader5: {e}")
            logger("💡 Trying alternative installation methods...")
            try:
                import subprocess
                subprocess.run([sys.executable, "-m", "pip", "install", "MetaTrader5", "--upgrade"], check=True)
                import MetaTrader5 as mt5_test
                logger("✅ MetaTrader5 installed and imported successfully")
            except Exception as install_e:
                logger(f"❌ Installation failed: {install_e}")
                return False

        # Initialize MT5 connection with enhanced retries
        for attempt in range(MAX_CONNECTION_ATTEMPTS):
            logger(
                f"🔄 MT5 connection attempt {attempt + 1}/{MAX_CONNECTION_ATTEMPTS}..."
            )

            # Try different initialization methods
            init_methods = [
                lambda: mt5.initialize(),
                lambda: mt5.initialize(
                    path="C:\\Program Files\\MetaTrader 5\\terminal64.exe"),
                lambda: mt5.initialize(
                    path="C:\\Program Files (x86)\\MetaTrader 5\\terminal.exe"),
                lambda: mt5.initialize(login=0),  # Auto-detect current login
            ]

            initialized = False
            for i, init_method in enumerate(init_methods):
                try:
                    logger(f"🔄 Trying initialization method {i + 1}...")
                    result = init_method()
                    if result:
                        initialized = True
                        logger(f"✅ MT5 initialized using method {i + 1}")
                        break
                    else:
                        error = mt5.last_error()
                        logger(f"⚠️ Method {i + 1} failed with error: {error}")
                except Exception as e:
                    logger(f"⚠️ Method {i + 1} exception: {str(e)}")
                    continue

            if not initialized:
                logger(
                    f"❌ All initialization methods failed on attempt {attempt + 1}"
                )
                last_error = mt5.last_error()
                logger(f"🔍 Last MT5 Error Code: {last_error}")

                if attempt < MAX_CONNECTION_ATTEMPTS - 1:
                    time.sleep(CONNECTION_RETRY_DELAY)
                    continue
                else:
                    logger("💡 SOLUSI TROUBLESHOOTING:")
                    logger(
                        "   1. ⚠️ WAJIB: Jalankan MT5 sebagai Administrator")
                    logger(
                        "   2. ⚠️ WAJIB: Pastikan MT5 sudah login ke akun trading")
                    logger("   3. ⚠️ Pastikan Python dan MT5 sama-sama 64-bit")
                    logger("   4. ⚠️ Tutup semua instance MT5 lain yang berjalan")
                    logger("   5. ⚠️ Restart MT5 jika masih bermasalah")
                    mt5_connected = False
                    return False

            # Enhanced diagnostic information
            try:
                version_info = mt5.version()
                if version_info:
                    logger(f"🔍 MT5 Version: {version_info}")
                    logger(
                        f"🔍 MT5 Build: {getattr(version_info, 'build', 'N/A')}")
                else:
                    logger("⚠️ Cannot get MT5 version info")
                    last_error = mt5.last_error()
                    logger(f"🔍 Version error code: {last_error}")
            except Exception as e:
                logger(f"⚠️ Version check failed: {str(e)}")

            # Enhanced account validation with detailed error reporting
            logger("🔍 Checking account information...")
            account_info = mt5.account_info()
            if account_info is None:
                last_error = mt5.last_error()
                logger(
                    f"❌ GAGAL mendapatkan info akun MT5 - Error Code: {last_error}"
                )
                logger("💡 PENYEBAB UTAMA:")
                logger("   ❌ MT5 belum login ke akun trading")
                logger("   ❌ Koneksi ke server broker terputus")
                logger("   ❌ MT5 tidak dijalankan sebagai Administrator")
                logger("   ❌ Python tidak dapat mengakses MT5 API")
                logger("   ❌ Firewall atau antivirus memblokir koneksi")

                # Try to get any available info for debugging
                try:
                    terminal_info_debug = mt5.terminal_info()
                    if terminal_info_debug:
                        logger(
                            f"🔍 Debug - Terminal Company: {getattr(terminal_info_debug, 'company', 'N/A')}"
                        )
                        logger(
                            f"🔍 Debug - Terminal Connected: {getattr(terminal_info_debug, 'connected', False)}"
                        )
                    else:
                        logger("🔍 Debug - Terminal info juga tidak tersedia")
                except:
                    logger("🔍 Debug - Tidak dapat mengakses terminal info")

                if attempt < MAX_CONNECTION_ATTEMPTS - 1:
                    logger(
                        f"🔄 Mencoba ulang dalam 5 detik... (attempt {attempt + 1})"
                    )
                    mt5.shutdown()
                    time.sleep(5)
                    continue
                else:
                    logger("❌ SOLUSI WAJIB DICOBA:")
                    logger("   1. 🔴 TUTUP MT5 SEPENUHNYA")
                    logger("   2. 🔴 KLIK KANAN MT5 → RUN AS ADMINISTRATOR")
                    logger("   3. 🔴 LOGIN KE AKUN TRADING DENGAN BENAR")
                    logger("   4. 🔴 PASTIKAN STATUS 'CONNECTED' DI MT5")
                    logger("   5. 🔴 BUKA MARKET WATCH DAN TAMBAHKAN SYMBOL")
                    mt5_connected = False
                    return False

            # Account info berhasil didapat
            logger(f"✅ Account Login: {account_info.login}")
            logger(f"✅ Account Server: {account_info.server}")
            logger(f"✅ Account Name: {getattr(account_info, 'name', 'N/A')}")
            logger(f"✅ Account Balance: ${account_info.balance:.2f}")
            logger(f"✅ Account Equity: ${account_info.equity:.2f}")
            logger(
                f"✅ Account Currency: {getattr(account_info, 'currency', 'USD')}"
            )
            logger(f"✅ Trade Allowed: {account_info.trade_allowed}")

            # Check terminal info with detailed diagnostics
            logger("🔍 Checking terminal information...")
            terminal_info = mt5.terminal_info()
            if terminal_info is None:
                logger("❌ Gagal mendapatkan info terminal MT5")
                last_error = mt5.last_error()
                logger(f"🔍 Terminal error code: {last_error}")

                if attempt < MAX_CONNECTION_ATTEMPTS - 1:
                    logger("🔄 Mencoba ulang...")
                    mt5.shutdown()
                    time.sleep(3)
                    continue
                else:
                    logger(
                        "❌ Terminal info tidak tersedia setelah semua percobaan"
                    )
                    mt5_connected = False
                    return False

            logger(f"✅ Terminal Connected: {terminal_info.connected}")
            logger(
                f"✅ Terminal Company: {getattr(terminal_info, 'company', 'N/A')}"
            )
            logger(f"✅ Terminal Name: {getattr(terminal_info, 'name', 'N/A')}")
            logger(f"✅ Terminal Path: {getattr(terminal_info, 'path', 'N/A')}")

            # Validate trading permissions
            if not account_info.trade_allowed:
                logger("⚠️ PERINGATAN: Akun tidak memiliki izin trading")
                logger(
                    "💡 Hubungi broker untuk mengaktifkan trading permission")
                logger("⚠️ Bot akan melanjutkan dengan mode READ-ONLY")

            # Check if terminal is connected to trade server
            if not terminal_info.connected:
                logger("❌ KRITIS: Terminal tidak terhubung ke trade server")
                logger("💡 SOLUSI:")
                logger("   1. Periksa koneksi internet")
                logger("   2. Cek status server broker")
                logger("   3. Login ulang ke MT5")
                logger("   4. Restart MT5 terminal")

                if attempt < MAX_CONNECTION_ATTEMPTS - 1:
                    logger("🔄 Mencoba reconnect...")
                    mt5.shutdown()
                    time.sleep(5)
                    continue
                else:
                    logger(
                        "❌ Terminal tetap tidak terhubung setelah semua percobaan"
                    )
                    mt5_connected = False
                    return False

            # Enhanced market data testing with more symbols and better error handling
            test_symbols = [
                "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD",
                "XAUUSD", "XAUUSDm", "GOLD", "BTCUSD", "EURGBP", "EURJPY"
            ]

            working_symbols = []
            failed_symbols = []

            logger("🔍 Testing market data access for symbols...")

            # First, get all available symbols
            logger("🔍 Mengambil daftar semua symbols...")
            try:
                all_symbols = mt5.symbols_get()
                if all_symbols and len(all_symbols) > 0:
                    logger(f"✅ Total symbols available: {len(all_symbols)}")
                    available_symbol_names = [
                        s.name for s in all_symbols if hasattr(s, 'name')
                    ]
                    logger(
                        f"🔍 Sample symbols: {', '.join(available_symbol_names[:10])}")
                else:
                    logger(
                        "⚠️ PERINGATAN: Tidak ada symbols dari mt5.symbols_get()"
                    )
                    logger(
                        "💡 Kemungkinan Market Watch kosong atau tidak aktif")
            except Exception as e:
                logger(f"❌ Error getting symbols list: {str(e)}")
                all_symbols = None

            # Test each symbol with comprehensive validation
            for test_symbol in test_symbols:
                try:
                    logger(f"🔍 Testing symbol: {test_symbol}")

                    # Try to get symbol info
                    symbol_info = mt5.symbol_info(test_symbol)
                    if symbol_info is None:
                        logger(f"❌ {test_symbol}: Symbol info tidak tersedia")
                        failed_symbols.append(f"{test_symbol} (not found)")
                        continue

                    logger(
                        f"🔍 {test_symbol}: visible={symbol_info.visible}, trade_mode={getattr(symbol_info, 'trade_mode', 'N/A')}"
                    )

                    # Try to make it visible if not already
                    if not symbol_info.visible:
                        logger(
                            f"🔄 Mengaktifkan {test_symbol} di Market Watch...")
                        select_result = mt5.symbol_select(test_symbol, True)
                        logger(
                            f"🔍 {test_symbol} activation result: {select_result}")

                        if select_result:
                            time.sleep(1.0)  # Wait longer for activation

                            # Re-check symbol info
                            symbol_info = mt5.symbol_info(test_symbol)
                            if symbol_info is None or not symbol_info.visible:
                                logger(f"❌ {test_symbol}: Gagal diaktifkan")
                                failed_symbols.append(
                                    f"{test_symbol} (activation failed)")
                                continue
                            else:
                                logger(f"✅ {test_symbol}: Berhasil diaktifkan")
                        else:
                            logger(f"❌ {test_symbol}: Gagal aktivasi")
                            failed_symbols.append(
                                f"{test_symbol} (select failed)")
                            continue

                    # Test tick data with multiple attempts and better error handling
                    tick_attempts = 5
                    tick_success = False
                    last_tick_error = None

                    logger(f"🔍 Testing tick data untuk {test_symbol}...")
                    for tick_attempt in range(tick_attempts):
                        try:
                            tick = mt5.symbol_info_tick(test_symbol)
                            if tick is not None:
                                if hasattr(tick, 'bid') and hasattr(
                                        tick, 'ask'):
                                    if tick.bid > 0 and tick.ask > 0:
                                        spread = abs(tick.ask - tick.bid)
                                        spread_percent = (
                                            spread / tick.bid
                                        ) * 100 if tick.bid > 0 else 0
                                        logger(
                                            f"✅ {test_symbol}: Bid={tick.bid}, Ask={tick.ask}, Spread={spread:.5f} ({spread_percent:.3f}%)"
                                        )
                                        working_symbols.append(test_symbol)
                                        tick_success = True
                                        break
                                    else:
                                        last_tick_error = f"Invalid prices: bid={tick.bid}, ask={tick.ask}"
                                else:
                                    last_tick_error = "Missing bid/ask attributes"
                            else:
                                last_tick_error = "Tick is None"

                            # Add error details for debugging
                            if tick_attempt == 0:
                                tick_error = mt5.last_error()
                                if tick_error != (0, 'Success'):
                                    logger(
                                        f"🔍 {test_symbol} tick error: {tick_error}"
                                    )

                        except Exception as tick_e:
                            last_tick_error = str(tick_e)

                        if tick_attempt < tick_attempts - 1:
                            time.sleep(0.8)  # Longer wait between attempts

                    if not tick_success:
                        logger(
                            f"❌ {test_symbol}: Tidak dapat mengambil tick data"
                        )
                        if last_tick_error:
                            logger(f"   Last error: {last_tick_error}")
                        failed_symbols.append(f"{test_symbol} (no valid tick)")

                except Exception as e:
                    error_msg = f"Exception: {str(e)}"
                    logger(f"❌ Error testing {test_symbol}: {error_msg}")
                    failed_symbols.append(f"{test_symbol} ({error_msg})")
                    continue

            # Report comprehensive results
            logger(f"📊 === MARKET DATA TEST RESULTS ===")
            logger(
                f"✅ Working symbols ({len(working_symbols)}): {', '.join(working_symbols) if working_symbols else 'NONE'}"
            )

            if failed_symbols:
                logger(f"❌ Failed symbols ({len(failed_symbols)}):")
                for i, failed in enumerate(
                        failed_symbols[:10]):  # Show first 10
                    logger(f"   {i+1}. {failed}")
                if len(failed_symbols) > 10:
                    logger(f"   ... dan {len(failed_symbols)-10} lainnya")

            # Check if we have any working symbols
            if len(working_symbols) > 0:
                # Success!
                mt5_connected = True
                logger(f"🎉 === MT5 CONNECTION SUCCESSFUL ===")
                logger(
                    f"👤 Account: {account_info.login} | Server: {account_info.server}"
                )
                logger(
                    f"💰 Balance: ${account_info.balance:.2f} | Equity: ${account_info.equity:.2f}"
                )
                logger(
                    f"🔐 Trade Permission: {'ENABLED' if account_info.trade_allowed else 'READ-ONLY'}"
                )
                logger(f"🌐 Terminal Connected: ✅ YES")
                logger(
                    f"📊 Market Access: ✅ ({len(working_symbols)} symbols working)"
                )
                logger(
                    f"🎯 Bot siap untuk trading dengan symbols: {', '.join(working_symbols[:5])}"
                )
                logger("=" * 50)
                return True
            else:
                if attempt < MAX_CONNECTION_ATTEMPTS - 1:
                    logger(
                        f"⚠️ Tidak ada symbols yang working, retry attempt {attempt + 2}..."
                    )
                    logger("💡 TROUBLESHOOTING:")
                    logger("   1. Buka Market Watch di MT5")
                    logger("   2. Tambahkan symbols secara manual")
                    logger("   3. Pastikan market sedang buka")
                    logger("   4. Cek koneksi internet")
                    mt5.shutdown()
                    time.sleep(5)
                    continue

        # All attempts failed
        logger("❌ === CONNECTION FAILED ===")
        logger("❌ Tidak dapat mengakses data market setelah semua percobaan")
        logger("💡 Solusi yang disarankan:")
        logger("   1. Pastikan MT5 dijalankan sebagai Administrator")
        logger("   2. Pastikan sudah login ke akun dan terkoneksi ke server")
        logger(
            "   3. Buka Market Watch dan pastikan ada symbols yang terlihat")
        logger("   4. Coba restart MT5 terminal")
        logger("   5. Pastikan tidak ada firewall yang memblokir koneksi")
        logger("   6. Pastikan Python dan MT5 sama-sama 64-bit")

        mt5_connected = False
        return False

    except Exception as e:
        logger(f"❌ Critical MT5 connection error: {str(e)}")
        logger("💡 Coba restart aplikasi dan MT5 terminal")
        mt5_connected = False
        return False


def check_mt5_status() -> bool:
    """Enhanced MT5 status check with specific error handling"""
    global mt5_connected
    try:
        if not mt5_connected:
            return False

        # Check account info with specific error handling
        try:
            account_info = mt5.account_info()
        except Exception as acc_e:
            logger(f"❌ Failed to get account info: {str(acc_e)}")
            mt5_connected = False
            return False

        # Check terminal info with specific error handling
        try:
            terminal_info = mt5.terminal_info()
        except Exception as term_e:
            logger(f"❌ Failed to get terminal info: {str(term_e)}")
            mt5_connected = False
            return False

        if account_info is None or terminal_info is None:
            mt5_connected = False
            logger(
                "❌ MT5 status check failed: Account or Terminal info unavailable."
            )
            return False

        if not terminal_info.connected:
            mt5_connected = False
            logger("❌ MT5 status check failed: Terminal not connected.")
            return False

        return True
    except ImportError as ie:
        logger(f"❌ MT5 module import error: {str(ie)}")
        mt5_connected = False
        return False
    except ConnectionError as ce:
        logger(f"❌ MT5 connection error: {str(ce)}")
        mt5_connected = False
        return False
    except Exception as e:
        logger(f"❌ Unexpected MT5 status check error: {str(e)}")
        mt5_connected = False
        return False


def get_symbols() -> List[str]:
    """Get available symbols from MT5 with enhanced error handling"""
    try:
        if not check_mt5_status():
            logger("❌ Cannot get symbols: MT5 not connected.")
            return []

        symbols = mt5.symbols_get()
        if symbols is None:
            logger("❌ Failed to get symbols from MT5.")
            return []

        return [s.name for s in symbols if hasattr(s, 'visible') and s.visible]
    except Exception as e:
        logger(f"❌ Exception in get_symbols: {str(e)}")
        return []


def validate_and_activate_symbol(symbol: str) -> Optional[str]:
    """
    Validasi symbol dengan prioritas detection yang konsisten.
    """
    try:
        if not symbol or not symbol.strip():
            logger(f"❌ Symbol kosong atau tidak valid")
            return None

        # Ensure MT5 is connected
        if not check_mt5_status():
            logger("🔄 MT5 not connected, attempting to reconnect...")
            if not connect_mt5():
                logger("❌ Cannot reconnect to MT5 for symbol validation")
                return None

        original_symbol = symbol.strip().upper()
        logger(f"🔍 Validating symbol: {original_symbol}")

        # PRIORITIZED symbol variations untuk konsistensi
        symbol_variations = []

        # Special handling for gold symbols dengan prioritas yang jelas
        if "XAU" in original_symbol or "GOLD" in original_symbol:
            # Prioritas urutan untuk gold symbols
            gold_priorities = [
                "XAUUSDm",     # Paling umum di banyak broker
                "XAUUSD",      # Standard
                "XAUUSDM",     # Alternative
                "GOLD",        # Simple name
                "GOLDm",       # With suffix
                "GOLDM",       # Capital suffix
                "XAU/USD",     # With separator
                "XAU_USD",     # Underscore
                "XAUUSD.a",    # Spread A
                "XAUUSD.b",    # Spread B
                "XAUUSDmicro", # Micro lots
                "XAUUSD_m"     # Alternative micro
            ]
            symbol_variations.extend(gold_priorities)
        else:
            # Standard forex pairs
            symbol_variations = [
                original_symbol,
                original_symbol.replace("m", "").replace("M", ""),
                original_symbol.replace("USDM", "USD"),
                original_symbol + "m",
                original_symbol + "M",
                original_symbol + ".a",
                original_symbol + ".b",
                original_symbol + ".raw",
                original_symbol[:-1] if original_symbol.endswith(("M", "m")) else original_symbol,
            ]

        # Add forex variations
        if len(original_symbol) == 6:
            # Try with different separators
            symbol_variations.extend([
                original_symbol[:3] + "/" + original_symbol[3:],
                original_symbol[:3] + "-" + original_symbol[3:],
                original_symbol[:3] + "." + original_symbol[3:],
            ])

        # Remove duplicates while preserving order
        seen = set()
        symbol_variations = [
            x for x in symbol_variations if not (x in seen or seen.add(x))
        ]

        valid_symbol = None
        symbol_info = None
        test_results = []

        # Test each variation with detailed logging
        logger(f"🔍 Testing {len(symbol_variations)} symbol variations...")
        for i, variant in enumerate(symbol_variations):
            try:
                logger(f"   {i+1}. Testing: {variant}")
                test_info = mt5.symbol_info(variant)
                if test_info is not None:
                    test_results.append(f"✅ {variant}: Found")
                    valid_symbol = variant
                    symbol_info = test_info
                    logger(f"✅ Found valid symbol: {variant}")
                    break
                else:
                    test_results.append(f"❌ {variant}: Not found")
            except Exception as e:
                test_results.append(f"⚠️ {variant}: Error - {str(e)}")
                logger(f"⚠️ Error testing variant {variant}: {str(e)}")
                continue

        # If not found in variations, search in all available symbols
        if symbol_info is None:
            logger(f"🔍 Searching in all available symbols...")
            try:
                all_symbols = mt5.symbols_get()
                if all_symbols:
                    logger(
                        f"🔍 Searching through {len(all_symbols)} available symbols..."
                    )

                    # First try exact matches
                    for sym in all_symbols:
                        sym_name = getattr(sym, 'name', '')
                        if sym_name.upper() == original_symbol:
                            test_info = mt5.symbol_info(sym_name)
                            if test_info:
                                valid_symbol = sym_name
                                symbol_info = test_info
                                logger(f"✅ Found exact match: {sym_name}")
                                break

                    # Then try partial matches
                    if symbol_info is None:
                        for sym in all_symbols:
                            sym_name = getattr(sym, 'name', '')
                            if (original_symbol[:4] in sym_name.upper()
                                    or sym_name.upper()[:4] in original_symbol
                                    or any(var[:4] in sym_name.upper()
                                           for var in symbol_variations[:5])):
                                test_info = mt5.symbol_info(sym_name)
                                if test_info:
                                    valid_symbol = sym_name
                                    symbol_info = test_info
                                    logger(
                                        f"✅ Found partial match: {sym_name} for {original_symbol}"
                                    )
                                    break
                else:
                    logger("⚠️ No symbols returned from mt5.symbols_get()")
            except Exception as e:
                logger(f"⚠️ Error searching symbols: {str(e)}")

        # Final check - if still not found, log all test results
        if symbol_info is None:
            logger(
                f"❌ Symbol {original_symbol} tidak ditemukan setelah semua percobaan"
            )
            logger("🔍 Test results:")
            for result in test_results[:10]:  # Show first 10 results
                logger(f"   {result}")
            if len(test_results) > 10:
                logger(f"   ... dan {len(test_results)-10} test lainnya")
            return None

        # Use the found valid symbol
        symbol = valid_symbol
        logger(f"🎯 Using symbol: {symbol}")

        # Enhanced symbol activation
        if not symbol_info.visible:
            logger(f"🔄 Activating symbol {symbol} in Market Watch...")

            # Try different activation methods
            activation_success = False
            activation_methods = [
                lambda: mt5.symbol_select(symbol, True),
                lambda: mt5.symbol_select(symbol, True, True
                                          ),  # With strict mode
            ]

            for method_idx, method in enumerate(activation_methods):
                try:
                    result = method()
                    if result:
                        logger(
                            f"✅ Symbol activated using method {method_idx + 1}"
                        )
                        activation_success = True
                        break
                    else:
                        logger(f"⚠️ Activation method {method_idx + 1} failed")
                except Exception as e:
                    logger(
                        f"⚠️ Activation method {method_idx + 1} exception: {str(e)}")

            if not activation_success:
                logger(
                    f"❌ Gagal mengaktifkan symbol {symbol} dengan semua metode"
                )
                logger(
                    "💡 Coba tambahkan symbol secara manual di Market Watch MT5"
                )
                return None

            # Wait for activation to take effect
            time.sleep(1.0)

            # Re-check symbol info after activation
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                logger(
                    f"❌ Symbol {symbol} tidak dapat diakses setelah aktivasi")
                return None

        # Enhanced trading permission validation
        trade_mode = getattr(symbol_info, 'trade_mode', None)
        if trade_mode is not None:
            if trade_mode == mt5.SYMBOL_TRADE_MODE_DISABLED:
                logger(
                    f"❌ Trading untuk symbol {symbol} tidak diizinkan (DISABLED)"
                )
                return None
            elif trade_mode == mt5.SYMBOL_TRADE_MODE_CLOSEONLY:
                logger(
                    f"⚠️ Symbol {symbol} hanya bisa close position (CLOSE_ONLY)"
                )
            elif trade_mode == mt5.SYMBOL_TRADE_MODE_FULL:
                logger(f"✅ Symbol {symbol} mendukung trading penuh")
            else:
                logger(f"🔍 Symbol {symbol} trade mode: {trade_mode}")

        # Enhanced tick validation with better error reporting and extended retry
        tick_valid = False
        tick_attempts = 10  # Increased attempts for problematic symbols
        last_tick_error = None

        logger(f"🔍 Testing tick data for {symbol}...")

        # First check if market is open for this symbol
        symbol_info_check = mt5.symbol_info(symbol)
        if symbol_info_check:
            trade_mode = getattr(symbol_info_check, 'trade_mode', None)
            logger(f"🔍 Symbol trade mode: {trade_mode}")

        for attempt in range(tick_attempts):
            try:
                # Add small delay before each attempt
                if attempt > 0:
                    time.sleep(1.0)  # Longer wait for tick data

                tick = mt5.symbol_info_tick(symbol)
                if tick is not None:
                    if hasattr(tick, 'bid') and hasattr(tick, 'ask'):
                        if tick.bid > 0 and tick.ask > 0:
                            spread = abs(tick.ask - tick.bid)
                            # Additional validation for reasonable tick values
                            if spread < tick.bid * 0.1:  # Spread shouldn't be more than 10% of price
                                logger(
                                    f"✅ Valid tick data - Bid: {tick.bid}, Ask: {tick.ask}, Spread: {spread:.5f}"
                                )
                                tick_valid = True
                                break
                            else:
                                logger(f"⚠️ Tick attempt {attempt + 1}: Unreasonable spread {spread}")
                        else:
                            logger(
                                f"⚠️ Tick attempt {attempt + 1}: Invalid prices (bid={tick.bid}, ask={tick.ask})"
                            )
                    else:
                        logger(
                            f"⚠️ Tick attempt {attempt + 1}: Missing bid/ask attributes"
                        )
                else:
                    logger(f"⚠️ Tick attempt {attempt + 1}: tick is None")
                    # Try to reactivate symbol
                    if attempt < tick_attempts - 2:
                        logger(f"🔄 Attempting to reactivate {symbol}...")
                        mt5.symbol_select(symbol, True)
                        time.sleep(2.0)

            except Exception as e:
                last_tick_error = str(e)
                logger(f"⚠️ Tick attempt {attempt + 1} exception: {str(e)}")

                # Try different tick retrieval methods on exception
                if attempt < tick_attempts - 1:
                    try:
                        # Alternative: Get rates and use last price
                        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 1)
                        if rates is not None and len(rates) > 0:
                            last_rate = rates[0]
                            logger(f"🔄 Alternative: Using rate data - Close: {last_rate['close']}")
                            # Create synthetic tick from rate data
                            tick_valid = True
                            break
                    except:
                        pass

        if not tick_valid:
            logger(f"❌ Tidak dapat mendapatkan data tick valid untuk {symbol}")
            if last_tick_error:
                logger(f"   Last error: {last_tick_error}")
            logger("💡 Kemungkinan penyebab:")
            logger("   - Market sedang tutup")
            logger("   - Symbol tidak aktif diperdagangkan")
            logger("   - Koneksi ke server data bermasalah")
            logger("   - Symbol memerlukan subscription khusus")
            return None

        # Final spread check and warnings with improved thresholds
        try:
            tick = mt5.symbol_info_tick(symbol)
            if tick:
                spread = abs(tick.ask - tick.bid)

                # Dynamic spread thresholds based on symbol type (more realistic)
                if "XAU" in symbol or "GOLD" in symbol:
                    max_spread_warning = 2.0  # Gold: up to $2 spread is normal
                elif "XAG" in symbol or "SILVER" in symbol:
                    max_spread_warning = 0.5  # Silver: up to 50 cents
                elif "JPY" in symbol:
                    max_spread_warning = 0.1   # JPY pairs: up to 10 pips
                elif any(crypto in symbol for crypto in ["BTC", "ETH", "LTC", "ADA", "DOT"]):
                    max_spread_warning = 100.0  # Crypto can have very wide spreads
                elif any(index in symbol for index in ["SPX", "NAS", "DJ", "DAX"]):
                    max_spread_warning = 5.0   # Stock indices
                elif any(oil in symbol for oil in ["OIL", "CRUDE", "WTI", "BRENT"]):
                    max_spread_warning = 0.1   # Oil CFDs
                else:
                    max_spread_warning = 0.02  # Regular forex pairs: up to 2 pips

                if spread > max_spread_warning:
                    logger(
                        f"⚠️ Spread tinggi untuk {symbol}: {spread:.5f} (threshold: {max_spread_warning})"
                    )
                    logger(
                        "   Symbol tetap valid, tapi perhatikan trading cost")
                else:
                    logger(f"✅ Spread normal untuk {symbol}: {spread:.5f}")

                # Additional warning for extremely high spreads
                if spread > max_spread_warning * 3:
                    logger(f"🚨 SPREAD SANGAT TINGGI! Consider waiting for better conditions")

        except Exception as e:
            logger(f"⚠️ Error checking final spread: {str(e)}")

        # Success!
        logger(f"✅ Symbol {symbol} berhasil divalidasi dan siap untuk trading")

        # Update GUI if available
        if gui:
            gui.symbol_var.set(symbol)

        return symbol  # Return the valid symbol string instead of True

    except Exception as e:
        logger(f"❌ Critical error validating symbol {symbol}: {str(e)}")
        import traceback
        logger(f"🔍 Stack trace: {traceback.format_exc()}")
        return None


def detect_gold_symbol() -> Optional[str]:
    """Auto-detect the correct gold symbol for the current broker"""
    try:
        if not check_mt5_status():
            return None

        # Common gold symbol variations
        gold_symbols = [
            "XAUUSD", "XAUUSDm", "XAUUSDM", "GOLD", "GOLDm", "GOLDM",
            "XAU/USD", "XAUUSD.a", "XAUUSD.b", "XAUUSD.raw", "XAUUSDmicro",
            "XAUUSD_1", "XAU_USD", "AU", "GOLD_USD", "XAUUSD_m"
        ]

        logger("🔍 Auto-detecting gold symbol for current broker...")

        for symbol in gold_symbols:
            try:
                # Test symbol info
                info = mt5.symbol_info(symbol)
                if info:
                    # Try to activate if not visible
                    if not info.visible:
                        if mt5.symbol_select(symbol, True):
                            time.sleep(0.5)
                            info = mt5.symbol_info(symbol)

                    # Test tick data
                    if info and info.visible:
                        tick = mt5.symbol_info_tick(symbol)
                        if tick and hasattr(tick, 'bid') and hasattr(tick, 'ask'):
                            if tick.bid > 1000 and tick.ask > 1000:  # Gold is typically > $1000
                                logger(f"✅ Found working gold symbol: {symbol} (Price: {tick.bid})")
                                return symbol

            except Exception as e:
                logger(f"🔍 Testing {symbol}: {str(e)}")
                continue

        logger("❌ No working gold symbol found")
        return None

    except Exception as e:
        logger(f"❌ Error detecting gold symbol: {str(e)}")
        return None

def get_symbol_suggestions() -> List[str]:
    """Enhanced symbol suggestions with fallback"""
    try:
        if not check_mt5_status():
            return ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD"]

        all_symbols = mt5.symbols_get()
        if not all_symbols:
            return ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD"]

        validated_symbols = []
        popular_patterns = [
            "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD",
            "USDCHF", "EURGBP", "EURJPY", "GBPJPY", "XAUUSD", "XAGUSD"
        ]

        # Find exact matches first
        for pattern in popular_patterns:
            for symbol in all_symbols:
                symbol_name = getattr(symbol, 'name', '')
                if symbol_name == pattern or symbol_name == pattern + "m":
                    try:
                        info = mt5.symbol_info(symbol_name)
                        if info:
                            validated_symbols.append(symbol_name)
                            if len(validated_symbols) >= 15:
                                break
                    except:
                        continue
            if len(validated_symbols) >= 15:
                break

        return validated_symbols[:20] if validated_symbols else [
            "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"
        ]

    except Exception as e:
        logger(f"❌ Error getting symbol suggestions: {str(e)}")
        return ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]


def get_account_info() -> Optional[Dict[str, Any]]:
    """Enhanced account info with error handling and currency detection"""
    try:
        if not check_mt5_status():
            logger("❌ Cannot get account info: MT5 not connected.")
            return None

        info = mt5.account_info()
        if info is None:
            logger("❌ Failed to get account info from MT5.")
            return None

        return {
            "balance": info.balance,
            "equity": info.equity,
            "margin": info.margin,
            "free_margin": info.margin_free,
            "margin_level": info.margin_level,
            "profit": info.profit,
            "login": info.login,
            "server": info.server,
            "currency": getattr(info, 'currency', 'USD')  # Auto-detect account currency
        }
    except Exception as e:
        logger(f"❌ Exception in get_account_info: {str(e)}")
        return None


def get_positions() -> List[Any]:
    """Enhanced position retrieval"""
    try:
        if not check_mt5_status():
            logger("❌ Cannot get positions: MT5 not connected.")
            return []

        positions = mt5.positions_get()
        return list(positions) if positions else []
    except Exception as e:
        logger(f"❌ Exception in get_positions: {str(e)}")
        return []


def get_currency_conversion_rate(from_currency: str, to_currency: str) -> float:
    """Enhanced currency conversion with multiple methods"""
    try:
        if from_currency == to_currency:
            return 1.0

        # Method 1: Direct pair
        direct_pair = f"{from_currency}{to_currency}"
        try:
            symbol_info = mt5.symbol_info(direct_pair)
            if symbol_info and symbol_info.visible:
                tick = mt5.symbol_info_tick(direct_pair)
                if tick and tick.bid > 0:
                    logger(f"💱 Direct conversion rate {direct_pair}: {tick.bid}")
                    return tick.bid
        except:
            pass

        # Method 2: Reverse pair
        reverse_pair = f"{to_currency}{from_currency}"
        try:
            symbol_info = mt5.symbol_info(reverse_pair)
            if symbol_info and symbol_info.visible:
                tick = mt5.symbol_info_tick(reverse_pair)
                if tick and tick.bid > 0:
                    rate = 1.0 / tick.bid
                    logger(f"💱 Reverse conversion rate {reverse_pair}: {rate}")
                    return rate
        except:
            pass

        # Method 3: Cross-rate via USD
        if from_currency != "USD" and to_currency != "USD":
            try:
                usd_from = get_currency_conversion_rate(from_currency, "USD")
                usd_to = get_currency_conversion_rate("USD", to_currency)
                if usd_from > 0 and usd_to > 0:
                    cross_rate = usd_from * usd_to
                    logger(f"💱 Cross-rate {from_currency}->{to_currency} via USD: {cross_rate}")
                    return cross_rate
            except:
                pass

        logger(f"⚠️ No conversion rate found for {from_currency} to {to_currency}")
        return 0.0

    except Exception as e:
        logger(f"❌ Currency conversion error: {str(e)}")
        return 0.0


def calculate_pip_value(symbol: str, lot_size: float) -> float:
    """Enhanced pip value calculation with better symbol recognition"""
    try:
        if not check_mt5_status():
            logger("❌ Cannot calculate pip value: MT5 not connected.")
            return 10.0 * lot_size

        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            logger(f"❌ Cannot calculate pip value: Symbol info for {symbol} not found.")
            return 10.0 * lot_size

        # Enhanced pip size calculation
        if "JPY" in symbol:
            pip_size = 0.01  # JPY pairs
        elif any(precious in symbol for precious in ["XAU", "XAG", "GOLD", "SILVER"]):
            pip_size = 0.1   # Precious metals (Gold/Silver)
        elif any(crypto in symbol for crypto in ["BTC", "ETH", "LTC", "ADA", "DOT"]):
            pip_size = getattr(symbol_info, 'point', 1.0) * 10  # Crypto
        elif any(index in symbol for index in ["SPX", "NAS", "DAX", "FTSE"]):
            pip_size = 1.0   # Stock indices
        elif any(commodity in symbol for commodity in ["OIL", "BRENT", "WTI", "GAS"]):
            pip_size = 0.01  # Commodities
        else:
            pip_size = 0.0001  # Standard forex pairs

        tick_value = getattr(symbol_info, 'trade_tick_value', 1.0)
        tick_size = getattr(symbol_info, 'trade_tick_size', pip_size)

        if tick_size > 0:
            pip_value = (pip_size / tick_size) * tick_value * lot_size
        else:
            pip_value = 10.0 * lot_size

        logger(f"💰 Pip value for {symbol}: {abs(pip_value):.4f} per {lot_size} lots")
        return abs(pip_value)
    except Exception as e:
        logger(f"❌ Exception in calculate_pip_value for {symbol}: {str(e)}")
        return 10.0 * lot_size


def parse_tp_sl_input(input_value: str, unit: str, symbol: str,
                      lot_size: float, current_price: float, order_type: str,
                      is_tp: bool) -> Tuple[float, Dict[str, float]]:
    """Enhanced TP/SL parsing with automatic currency detection and improved calculations"""
    try:
        if not input_value or input_value == "0" or input_value == "":
            return 0.0, {}

        value = float(input_value)
        if value <= 0:
            return 0.0, {}

        pip_value = calculate_pip_value(symbol, lot_size)
        account_info = get_account_info()
        balance = account_info['balance'] if account_info else 10000.0

        # Auto-detect account currency
        account_currency = account_info.get('currency', 'USD') if account_info else 'USD'
        logger(f"💱 Auto-detected account currency: {account_currency}")

        calculations = {}
        result_price = 0.0

        # Enhanced pip size calculation based on symbol type
        if "JPY" in symbol:
            pip_size = 0.01  # JPY pairs
        elif any(precious in symbol for precious in ["XAU", "XAG", "GOLD", "SILVER"]):
            pip_size = 0.1   # Precious metals
        elif any(crypto in symbol for crypto in ["BTC", "ETH", "LTC", "ADA", "DOT"]):
            symbol_info = mt5.symbol_info(symbol)
            pip_size = getattr(symbol_info, 'point', 0.0001) * 10 if symbol_info else 1.0
        elif any(index in symbol for index in ["SPX", "NAS", "DAX", "FTSE"]):
            pip_size = 1.0   # Stock indices
        elif any(commodity in symbol for commodity in ["OIL", "BRENT", "WTI"]):
            pip_size = 0.01  # Oil and commodities
        else:
            pip_size = 0.0001  # Standard forex pairs

        if unit == "pips":
            price_movement = value * pip_size
            if is_tp:
                if order_type == "BUY":
                    result_price = current_price + price_movement
                else:
                    result_price = current_price - price_movement
            else:
                if order_type == "BUY":
                    result_price = current_price - price_movement
                else:
                    result_price = current_price + price_movement

            profit_loss_amount = value * pip_value
            calculations['pips'] = value
            calculations['amount'] = profit_loss_amount
            calculations['percent'] = (profit_loss_amount / balance) * 100

        elif unit == "price":
            result_price = value
            price_diff = abs(result_price - current_price)
            pips = price_diff / pip_size
            profit_loss_amount = pips * pip_value

            calculations['pips'] = pips
            calculations['amount'] = profit_loss_amount
            calculations['percent'] = (profit_loss_amount / balance) * 100

        elif unit == "%":
            profit_loss_amount = balance * (value / 100)
            pips = profit_loss_amount / pip_value if pip_value > 0 else 0
            price_movement = pips * pip_size

            if is_tp:
                if order_type == "BUY":
                    result_price = current_price + price_movement
                else:
                    result_price = current_price - price_movement
            else:
                if order_type == "BUY":
                    result_price = current_price - price_movement
                else:
                    result_price = current_price + price_movement

            calculations['pips'] = pips
            calculations['amount'] = profit_loss_amount
            calculations['percent'] = value

        elif unit in ["currency", "USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "NZD"]:
            # Enhanced currency-based TP/SL calculation with automatic detection
            profit_loss_amount = value

            # Use auto-detected account currency
            if unit == "currency":
                unit = account_currency
                profit_loss_amount = value
                logger(f"💱 Using auto-detected currency: {account_currency}")
            elif unit != account_currency:
                # Enhanced conversion with multiple methods
                conversion_rate = get_currency_conversion_rate(unit, account_currency)
                if conversion_rate > 0:
                    profit_loss_amount = value * conversion_rate
                    logger(f"💱 Currency conversion: {value} {unit} = {profit_loss_amount:.2f} {account_currency} (rate: {conversion_rate})")
                else:
                    logger(f"⚠️ Cannot convert {unit} to {account_currency}, using direct value")
                    profit_loss_amount = value

            # Calculate pips from currency amount
            if pip_value > 0:
                pips = profit_loss_amount / pip_value
            else:
                # Fallback calculation for pip value
                try:
                    symbol_info = mt5.symbol_info(symbol)
                    if symbol_info:
                        tick_value = getattr(symbol_info, 'trade_tick_value', 1.0)
                        tick_size = getattr(symbol_info, 'trade_tick_size', pip_size)
                        if tick_size > 0:
                            calculated_pip_value = (pip_size / tick_size) * tick_value * lot_size
                            pips = profit_loss_amount / calculated_pip_value if calculated_pip_value > 0 else 10
                        else:
                            pips = 10  # Default fallback
                    else:
                        pips = 10  # Default fallback
                except:
                    pips = 10  # Default fallback

            price_movement = pips * pip_size

            if is_tp:
                if order_type == "BUY":
                    result_price = current_price + price_movement
                else:
                    result_price = current_price - price_movement
            else:
                if order_type == "BUY":
                    result_price = current_price - price_movement
                else:
                    result_price = current_price + price_movement

            calculations['pips'] = pips
            calculations['amount'] = profit_loss_amount
            calculations['percent'] = (profit_loss_amount / balance) * 100
            calculations['currency'] = unit
            calculations['account_currency'] = account_currency

        return result_price, calculations

    except Exception as e:
        logger(f"❌ Error parsing TP/SL input: {str(e)}")
        return 0.0, {}


def validate_tp_sl_levels(symbol: str, tp_price: float, sl_price: float,
                          order_type: str,
                          current_price: float) -> Tuple[bool, str]:
    """Enhanced TP/SL validation"""
    try:
        if not check_mt5_status():
            return False, "MT5 not connected"

        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return False, f"Symbol {symbol} not found"

        min_stop_level = getattr(symbol_info, 'trade_stops_level',
                                 0) * getattr(symbol_info, 'point', 0.00001)
        spread = getattr(symbol_info, 'spread', 0) * getattr(
            symbol_info, 'point', 0.00001)

        safety_margin = max(min_stop_level, spread * 2,
                            0.0001)  # Minimum safety margin

        if tp_price > 0:
            tp_distance = abs(tp_price - current_price)
            if tp_distance < safety_margin:
                return False, f"TP too close: {tp_distance:.5f} < {safety_margin:.5f}"

        if sl_price > 0:
            sl_distance = abs(sl_price - current_price)
            if sl_distance < safety_margin:
                return False, f"SL too close: {sl_distance:.5f} < {safety_margin:.5f}"

        if order_type == "BUY":
            if tp_price > 0 and tp_price <= current_price:
                return False, "BUY TP must be above current price"
            if sl_price > 0 and sl_price >= current_price:
                return False, "BUY SL must be below current price"
        else:
            if tp_price > 0 and tp_price >= current_price:
                return False, "SELL TP must be below current price"
            if sl_price > 0 and sl_price <= current_price:
                return False, "SELL SL must be above current price"

        return True, "Valid"

    except Exception as e:
        return False, f"Validation error: {str(e)}"


def validate_trading_conditions(symbol: str) -> Tuple[bool, str]:
    """Enhanced trading condition validation"""
    try:
        if not check_mt5_status():
            return False, "MT5 not connected"

        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return False, f"Symbol {symbol} not found"

        if not symbol_info.visible:
            if not mt5.symbol_select(symbol, True):
                return False, f"Cannot activate {symbol}"
            time.sleep(0.1)

        trade_mode = getattr(symbol_info, 'trade_mode', None)
        if trade_mode == mt5.SYMBOL_TRADE_MODE_DISABLED:
            return False, f"Trading disabled for {symbol}"

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return False, f"Cannot get tick data for {symbol}"

        spread = abs(tick.ask - tick.bid)
        max_spread = 0.001 if "JPY" in symbol else 0.0001
        if spread > max_spread:
            logger(f"⚠️ High spread detected: {spread:.5f}")

        return True, "Valid"

    except Exception as e:
        return False, f"Validation error: {str(e)}"


def execute_trade_signal(symbol: str, action: str) -> bool:
    """Enhanced trade execution based on signals"""
    try:
        is_valid, error_msg = validate_trading_conditions(symbol)
        if not is_valid:
            logger(f"❌ Cannot trade {symbol}: {error_msg}")
            return False

        if not gui:
            logger("❌ GUI not available")
            return False

        lot = gui.get_current_lot()
        tp_input = gui.get_current_tp()
        sl_input = gui.get_current_sl()
        tp_unit = gui.get_current_tp_unit()
        sl_unit = gui.get_current_sl_unit()

        # Set defaults if empty
        if not tp_input or tp_input == "0":
            tp_input = {
                "Scalping": "15",
                "HFT": "8",
                "Intraday": "50",
                "Arbitrage": "25"
            }.get(current_strategy, "20")
            tp_unit = "pips"

        if not sl_input or sl_input == "0":
            sl_input = {
                "Scalping": "8",
                "HFT": "4",
                "Intraday": "25",
                "Arbitrage": "10"
            }.get(current_strategy, "10")
            sl_unit = "pips"

        logger(f"🎯 Executing {action} signal for {symbol}")

        result = open_order(symbol, lot, action, sl_input, tp_input, sl_unit,
                            tp_unit)

        if result and getattr(result, 'retcode',
                              None) == mt5.TRADE_RETCODE_DONE:
            logger(f"✅ {action} order executed successfully!")
            return True
        else:
            logger(f"❌ Failed to execute {action} order")
            return False

    except Exception as e:
        logger(f"❌ Error executing trade signal: {str(e)}")
        return False


def calculate_auto_lot_size(symbol: str,
                            sl_pips: float,
                            risk_percent: float = 1.0) -> float:
    """Calculate optimal lot size based on risk percentage"""
    try:
        if not check_mt5_status():
            logger("❌ Cannot calculate auto lot: MT5 not connected")
            return 0.01

        info = get_account_info()
        if not info:
            logger("❌ Cannot get account info for auto lot calculation")
            return 0.01

        balance = info['balance']
        risk_amount = balance * (risk_percent / 100)

        # Calculate pip value for 1 standard lot
        pip_value_per_lot = calculate_pip_value(symbol, 1.0)

        if pip_value_per_lot <= 0 or sl_pips <= 0:
            logger("❌ Invalid pip value or SL for auto lot calculation")
            return 0.01

        # Calculate required lot size
        calculated_lot = risk_amount / (sl_pips * pip_value_per_lot)

        # Get symbol constraints
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info:
            min_lot = getattr(symbol_info, "volume_min", 0.01)
            max_lot = getattr(symbol_info, "volume_max", 100.0)
            lot_step = getattr(symbol_info, "volume_step", 0.01)

            # Normalize to lot step
            calculated_lot = round(calculated_lot / lot_step) * lot_step
            calculated_lot = max(min_lot, min(calculated_lot, max_lot))
        else:
            calculated_lot = max(0.01, min(calculated_lot, 10.0))

        logger(
            f"💡 Auto-lot calculation: Risk {risk_percent}% = ${risk_amount:.2f} / {sl_pips} pips = {calculated_lot:.3f} lots"
        )
        return calculated_lot

    except Exception as e:
        logger(f"❌ Error calculating auto lot size: {str(e)}")
        return 0.01


def open_order(symbol: str,
                 lot: float,
                 action: str,
                 sl_input: str,
                 tp_input: str,
                 sl_unit: str = "pips",
                 tp_unit: str = "pips") -> Any:
    """Enhanced order execution with auto-lot sizing and improved risk management"""
    global position_count, session_data, last_trade_time

    with trade_lock:
        try:
            # Rate limiting
            current_time = time.time()
            if symbol in last_trade_time:
                if current_time - last_trade_time[symbol] < 3:
                    logger(f"⏱️ Rate limit active for {symbol}")
                    return None

            # Enhanced auto-lot sizing (optional feature)
            use_auto_lot = gui and hasattr(
                gui, 'auto_lot_var') and gui.auto_lot_var.get()
            if use_auto_lot and sl_input and sl_unit == "pips":
                try:
                    sl_pips = float(sl_input)
                    risk_percent = float(
                        gui.risk_percent_entry.get()) if hasattr(
                            gui, 'risk_percent_entry') else 1.0
                    auto_lot = calculate_auto_lot_size(symbol, sl_pips,
                                                       risk_percent)

                    logger(
                        f"🎯 Auto-lot sizing: {lot:.3f} → {auto_lot:.3f} (Risk: {risk_percent}%, SL: {sl_pips} pips)"
                    )
                    lot = auto_lot

                except Exception as auto_e:
                    logger(
                        f"⚠️ Auto-lot calculation failed, using manual lot: {str(auto_e)}"
                    )

            # Enhanced GUI parameter validation with proper error handling
            if not gui or not hasattr(gui, 'strategy_combo'):
                logger("⚠️ GUI not available, using default parameters")
                if not sl_input: sl_input = "10"
                if not tp_input: tp_input = "20"
                if lot <= 0: lot = 0.01
            else:
                # Get parameters with proper fallbacks and validation
                if not sl_input or sl_input.strip() == "":
                    sl_input = gui.get_current_sl() if hasattr(
                        gui, 'get_current_sl') else "10"
                if not tp_input or tp_input.strip() == "":
                    tp_input = gui.get_current_tp() if hasattr(
                        gui, 'get_current_tp') else "20"

                # Ensure lot is valid
                if lot <= 0:
                    lot = gui.get_current_lot() if hasattr(
                        gui, 'get_current_lot') else 0.01
                    logger(f"🔧 Invalid lot corrected to: {lot}")
            # Check position limits
            positions = get_positions()
            position_count = len(positions)

            if position_count >= max_positions:
                logger(f"⚠️ Max positions ({max_positions}) reached")
                return None

            # Enhanced symbol validation
            valid_symbol = validate_and_activate_symbol(symbol)
            if not valid_symbol:
                logger(f"❌ Cannot validate symbol {symbol}")
                return None
            symbol = valid_symbol  # Use the validated symbol

            # Get symbol info
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                logger(f"❌ Cannot get symbol info for {symbol}")
                return None

            # Get current tick with retry
            tick = None
            for attempt in range(3):
                tick = mt5.symbol_info_tick(symbol)
                if tick is not None and hasattr(tick, 'bid') and hasattr(tick, 'ask'):
                    if tick.bid > 0 and tick.ask > 0:
                        break
                time.sleep(0.1)

            if tick is None:
                logger(f"❌ Cannot get valid tick data for {symbol}")
                return None

            # Determine order type and price
            if action.upper() == "BUY":
                order_type = mt5.ORDER_TYPE_BUY
                price = tick.ask
            else:
                order_type = mt5.ORDER_TYPE_SELL
                price = tick.bid

            # Get session adjustments for lot sizing
            current_session = get_current_trading_session()
            session_adjustments = adjust_strategy_for_session(
                current_strategy,  # Use global current_strategy
                current_session)
            lot_multiplier = session_adjustments.get("lot_multiplier", 1.0)

            # Apply session-based lot adjustment
            adjusted_lot = lot * lot_multiplier
            logger(
                f"📊 Session lot adjustment: {lot} × {lot_multiplier} = {adjusted_lot}"
            )

            # Validate and normalize lot size
            min_lot = getattr(symbol_info, "volume_min", 0.01)
            max_lot = getattr(symbol_info, "volume_max", 100.0)
            lot_step = getattr(symbol_info, "volume_step", 0.01)

            if adjusted_lot < min_lot:
                adjusted_lot = min_lot
            elif adjusted_lot > max_lot:
                adjusted_lot = max_lot

            lot = round(adjusted_lot / lot_step) * lot_step
            logger(f"✅ Final lot size after validation: {lot}")

            # Calculate TP and SL using user-selected units
            point = getattr(symbol_info, "point", 0.00001)
            digits = getattr(symbol_info, "digits", 5)

            tp_price = 0.0
            sl_price = 0.0

            logger(
                f"🧮 Calculating TP/SL: TP={tp_input} {tp_unit}, SL={sl_input} {sl_unit}"
            )

            # Apply session adjustments to TP/SL
            tp_multiplier = session_adjustments.get("tp_multiplier", 1.0)
            sl_multiplier = session_adjustments.get("sl_multiplier", 1.0)

            # Parse TP dengan unit yang dipilih user + session adjustment
            if tp_input and tp_input.strip() and tp_input != "0":
                try:
                    # Apply session multiplier to TP input
                    adjusted_tp_input = str(float(tp_input) * tp_multiplier)
                    logger(
                        f"📊 Session TP adjustment: {tp_input} × {tp_multiplier} = {adjusted_tp_input}"
                    )

                    tp_price, tp_calc = parse_tp_sl_input(
                        adjusted_tp_input, tp_unit, symbol, lot, price,
                        action.upper(), True)
                    tp_price = round(tp_price, digits) if tp_price > 0 else 0.0

                    if tp_price > 0:
                        logger(
                            f"✅ TP calculated: {tp_price:.5f} (from {tp_input} {tp_unit} adjusted to {adjusted_tp_input})"
                        )
                        if 'amount' in tp_calc:
                            logger(
                                f"   Expected TP profit: ${tp_calc['amount']:.2f}"
                            )
                    else:
                        logger(f"⚠️ TP calculation resulted in 0, skipping TP")

                except Exception as e:
                    logger(
                        f"❌ Error parsing TP {tp_input} {tp_unit}: {str(e)}")
                    tp_price = 0.0

            # Parse SL dengan unit yang dipilih user + session adjustment
            if sl_input and sl_input.strip() and sl_input != "0":
                try:
                    # Apply session multiplier to SL input
                    adjusted_sl_input = str(float(sl_input) * sl_multiplier)
                    logger(
                        f"📊 Session SL adjustment: {sl_input} × {sl_multiplier} = {adjusted_sl_input}"
                    )

                    sl_price, sl_calc = parse_tp_sl_input(
                        adjusted_sl_input, sl_unit, symbol, lot, price,
                        action.upper(), False)
                    sl_price = round(sl_price, digits) if sl_price > 0 else 0.0

                    if sl_price > 0:
                        logger(
                            f"✅ SL calculated: {sl_price:.5f} (from {sl_input} {sl_unit} adjusted to {adjusted_sl_input})"
                        )
                        if 'amount' in sl_calc:
                            logger(
                                f"   Expected SL loss: ${sl_calc['amount']:.2f}"
                            )
                    else:
                        logger(f"⚠️ SL calculation resulted in 0, skipping SL")

                except Exception as e:
                    logger(
                        f"❌ Error parsing SL {sl_input} {sl_unit}: {str(e)}")
                    sl_price = 0.0

            # Log final TP/SL values before order
            if tp_price > 0 or sl_price > 0:
                logger(
                    f"📋 Final order levels: Entry={price:.5f}, TP={tp_price:.5f}, SL={sl_price:.5f}"
                )
            else:
                logger(f"📋 Order without TP/SL: Entry={price:.5f}")

            # Validasi TP/SL levels sebelum submit order
            is_valid, error_msg = validate_tp_sl_levels(
                symbol, tp_price, sl_price, action.upper(), price)
            if not is_valid:
                logger(f"❌ Order validation failed: {error_msg}")
                return None

            # Create order request
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": lot,
                "type": order_type,
                "price": price,
                "deviation": 50,
                "magic": 123456,
                "comment": "AutoBotCuan",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            if sl_price > 0:
                request["sl"] = sl_price
            if tp_price > 0:
                request["tp"] = tp_price

            # Execute order with enhanced error handling
            logger(f"🔄 Sending {action} order for {symbol}")

            try:
                result = mt5.order_send(request)

                if result is None:
                    logger(f"❌ Order send returned None")
                    mt5_error = mt5.last_error()
                    logger(f"🔍 MT5 Error: {mt5_error}")
                    return None

            except Exception as order_exception:
                logger(
                    f"❌ Critical error sending order: {str(order_exception)}")
                return None

            # Process order result
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                logger(f"❌ Order failed: {result.retcode} - {result.comment}")

                # Retry without SL/TP for specific error codes
                invalid_stops_codes = [
                    10016, 10017, 10018, 10019, 10020, 10021
                ]  # Invalid stops/TP/SL codes
                if result.retcode in invalid_stops_codes:
                    logger("⚠️ Retrying without SL/TP...")
                    request.pop("sl", None)
                    request.pop("tp", None)
                    try:
                        result = mt5.order_send(request)

                        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                            logger(
                                f"✅ Order successful without SL/TP: {result.order}"
                            )
                        else:
                            logger(
                                f"❌ Retry failed: {result.comment if result else 'No result'}"
                            )
                            return None
                    except Exception as retry_exception:
                        logger(
                            f"❌ Critical error during retry: {str(retry_exception)}")
                        return None
                else:
                    return None

            # Order successful
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                last_trade_time[symbol] = current_time
                position_count += 1
                session_data['total_trades'] += 1
                session_data['daily_orders'] += 1

                # Update last balance for profit tracking
                info = get_account_info()
                if info:
                    session_data['last_balance'] = info['balance']
                    session_data['session_equity'] = info['equity']

                logger(f"✅ {action.upper()} order executed successfully!")
                logger(f"📊 Ticket: {result.order} | Price: {price:.5f}")

                # Log to CSV
                trade_data = {
                    "time":
                    datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "symbol": symbol,
                    "type": action.upper(),
                    "lot": lot,
                    "sl": sl_price if sl_price > 0 else 0,
                    "tp": tp_price if tp_price > 0 else 0,
                    "profit": 0,
                }

                log_filename = "logs/buy.csv" if action.upper(
                ) == "BUY" else "logs/sell.csv"
                if not os.path.exists("logs"):
                    os.makedirs("logs")

                log_order_csv(log_filename, trade_data)

                # Telegram notification
                if gui and hasattr(gui,
                                   'telegram_var') and gui.telegram_var.get():
                    msg = f"🟢 {action.upper()} Order Executed\nSymbol: {symbol}\nLot: {lot}\nPrice: {price:.5f}\nTicket: {result.order}"
                    send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, msg)

                return result
            else:
                logger(f"❌ Order execution failed: {result.comment}")
                return None

        except Exception as e:
            error_msg = f"❌ Critical error in order execution: {str(e)}"
            logger(error_msg)
            return None


def log_order_csv(filename: str, order: Dict[str, Any]) -> None:
    """Enhanced CSV logging"""
    try:
        fieldnames = ["time", "symbol", "type", "lot", "sl", "tp", "profit"]
        file_exists = os.path.isfile(filename)
        with open(filename, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(order)
    except Exception as e:
        logger(f"❌ Error logging to CSV: {str(e)}")


def close_all_orders(symbol: str = None) -> None:
    """Enhanced close all orders"""
    try:
        if not check_mt5_status():
            logger("❌ MT5 not connected")
            return

        positions = mt5.positions_get(
            symbol=symbol) if symbol else mt5.positions_get()
        if not positions:
            logger("ℹ️ No positions to close")
            return

        closed_count = 0
        total_profit = 0.0
        failed_count = 0

        for position in positions:
            try:
                tick = mt5.symbol_info_tick(position.symbol)
                if tick is None:
                    failed_count += 1
                    continue

                order_type = mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
                price = tick.bid if position.type == mt5.ORDER_TYPE_BUY else tick.ask

                close_request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "position": position.ticket,
                    "symbol": position.symbol,
                    "volume": position.volume,
                    "type": order_type,
                    "price": price,
                    "deviation": 20,
                    "magic": position.magic,
                    "comment": "AutoBot_CloseAll",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_IOC,
                }

                result = mt5.order_send(close_request)
                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                    logger(
                        f"✅ Position {position.ticket} closed - Profit: ${position.profit:.2f}"
                    )
                    closed_count += 1
                    total_profit += position.profit
                    session_data['daily_profit'] += position.profit
                    session_data['total_profit'] += position.profit

                    if position.profit > 0:
                        session_data['winning_trades'] += 1
                        logger(
                            f"🎯 Winning trade #{session_data['winning_trades']}"
                        )
                    else:
                        session_data['losing_trades'] += 1
                        logger(
                            f"❌ Losing trade #{session_data['losing_trades']}")

                    # Update account info for GUI
                    info = get_account_info()
                    if info:
                        session_data['session_equity'] = info['equity']
                else:
                    logger(f"❌ Failed to close {position.ticket}")
                    failed_count += 1

            except Exception as e:
                logger(f"❌ Error closing position: {str(e)}")
                failed_count += 1

        if closed_count > 0:
            logger(
                f"🔄 Closed {closed_count} positions. Total Profit: ${total_profit:.2f}"
            )

    except Exception as e:
        logger(f"❌ Error closing orders: {str(e)}")


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Enhanced indicator calculation with strategy-specific optimizations for higher winrate"""
    try:
        if len(df) < 50:
            logger("⚠️ Insufficient data for indicators calculation")
            return df

        # Core EMA indicators with optimized periods for each strategy
        df['EMA5'] = df['close'].ewm(span=5, adjust=False).mean()
        df['EMA8'] = df['close'].ewm(span=8, adjust=False).mean()  # Additional EMA for better signals
        df['EMA13'] = df['close'].ewm(span=13, adjust=False).mean()
        df['EMA20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['EMA50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['EMA100'] = df['close'].ewm(span=100, adjust=False).mean()
        df['EMA200'] = df['close'].ewm(span=200, adjust=False).mean()

        # Enhanced EMA slope calculation for trend strength
        df['EMA5_Slope'] = df['EMA5'].diff(3)  # 3-period slope
        df['EMA13_Slope'] = df['EMA13'].diff(3)
        df['EMA_Momentum'] = (df['EMA5'] - df['EMA13']) / df['EMA13'] * 100

        # RSI untuk scalping (period 7 dan 9)
        df['RSI7'] = rsi(df['close'], 7)
        df['RSI9'] = rsi(df['close'], 9)
        df['RSI14'] = rsi(df['close'], 14)
        df['RSI'] = df['RSI9']  # Default menggunakan RSI9 untuk scalping
        df['RSI_Smooth'] = df['RSI'].rolling(
            window=3).mean()  # Add missing RSI_Smooth

        # MACD untuk konfirmasi
        df['MACD'], df['MACD_signal'], df['MACD_histogram'] = macd_enhanced(
            df['close'])

        # Moving Averages tambahan
        df['MA5'] = df['close'].rolling(window=5).mean()
        df['MA10'] = df['close'].rolling(window=10).mean()
        df['MA20'] = df['close'].rolling(window=20).mean()

        # WMA (Weighted Moving Average) - Key for price action
        def wma(series, period):
            weights = np.arange(1, period + 1)
            return series.rolling(period).apply(
                lambda x: np.dot(x, weights) / weights.sum(), raw=True)

        df['WMA5_High'] = wma(df['high'], 5)
        df['WMA5_Low'] = wma(df['low'], 5)
        df['WMA10_High'] = wma(df['high'], 10)
        df['WMA10_Low'] = wma(df['low'], 10)

        # Bollinger Bands
        df['BB_Middle'] = df['close'].rolling(window=20).mean()
        bb_std = df['close'].rolling(window=20).std()
        df['BB_Upper'] = df['BB_Middle'] + 2 * bb_std
        df['BB_Lower'] = df['BB_Middle'] - 2 * bb_std
        df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / df['BB_Middle']

        # Stochastic
        df['STOCH_K'], df['STOCH_D'] = stochastic_enhanced(df)

        # ATR
        df['ATR'] = atr(df, 14)
        df['ATR_Ratio'] = df['ATR'] / df['ATR'].rolling(window=20).mean()

        # EMA Crossover Signals untuk Scalping
        df['EMA5_Cross_Above_EMA13'] = (
            (df['EMA5'] > df['EMA13']) &
            (df['EMA5'].shift(1) <= df['EMA13'].shift(1)))
        df['EMA5_Cross_Below_EMA13'] = (
            (df['EMA5'] < df['EMA13']) &
            (df['EMA5'].shift(1) >= df['EMA13'].shift(1)))

        # EMA20/50 Crossover untuk Intraday
        df['EMA20_Cross_Above_EMA50'] = (
            (df['EMA20'] > df['EMA50']) &
            (df['EMA20'].shift(1) <= df['EMA50'].shift(1)))
        df['EMA20_Cross_Below_EMA50'] = (
            (df['EMA20'] < df['EMA50']) &
            (df['EMA20'].shift(1) >= df['EMA50'].shift(1)))

        # RSI Conditions untuk scalping (80/20 levels)
        df['RSI_Oversold_Recovery'] = ((df['RSI'] > 20) &
                                       (df['RSI'].shift(1) <= 20))
        df['RSI_Overbought_Decline'] = ((df['RSI'] < 80) &
                                        (df['RSI'].shift(1) >= 80))

        # Enhanced Price Action Patterns
        df['Bullish_Engulfing'] = (
            (df['close'] > df['open']) &
            (df['close'].shift(1) < df['open'].shift(1)) &
            (df['open'] < df['close'].shift(1)) &
            (df['close'] > df['open'].shift(1)) &
            (df['volume'] > df['volume'].shift(1) * 1.2)  # Volume confirmation
        )

        df['Bearish_Engulfing'] = (
            (df['close'] < df['open']) &
            (df['close'].shift(1) > df['open'].shift(1)) &
            (df['open'] > df['close'].shift(1)) &
            (df['close'] < df['open'].shift(1)) &
            (df['volume'] > df['volume'].shift(1) * 1.2)  # Volume confirmation
        )

        # Breakout patterns
        df['Bullish_Breakout'] = (
            (df['close'] > df['high'].rolling(window=20).max().shift(1)) &
            (df['close'] > df['WMA5_High']) & (df['close'] > df['BB_Upper']))

        df['Bearish_Breakout'] = (
            (df['close'] < df['low'].rolling(window=20).min().shift(1)) &
            (df['close'] < df['WMA5_Low']) & (df['close'] < df['BB_Lower']))

        # Strong candle detection
        df['Candle_Size'] = abs(df['close'] - df['open'])
        df['Avg_Candle_Size'] = df['Candle_Size'].rolling(window=20).mean()
        df['Strong_Bullish_Candle'] = (
            (df['close'] > df['open']) &
            (df['Candle_Size'] > df['Avg_Candle_Size'] * 1.5))
        df['Strong_Bearish_Candle'] = (
            (df['close'] < df['open']) &
            (df['Candle_Size'] > df['Avg_Candle_Size'] * 1.5))

        # Trend indicators
        df['Higher_High'] = (df['high'] > df['high'].shift(1)) & (
            df['high'].shift(1) > df['high'].shift(2))
        df['Lower_Low'] = (df['low'] < df['low'].shift(1)) & (
            df['low'].shift(1) < df['low'].shift(2))
        df['Trend_Strength'] = abs(df['EMA20'] - df['EMA50']) / df['ATR']

        # Momentum
        df['Momentum'] = df['close'] - df['close'].shift(10)
        df['ROC'] = ((df['close'] - df['close'].shift(10)) /
                     df['close'].shift(10)) * 100

        # Support/Resistance
        df['Support'] = df['low'].rolling(window=20).min()
        df['Resistance'] = df['high'].rolling(window=20).max()

        # Market structure
        df['Bullish_Structure'] = ((df['EMA20'] > df['EMA50']) &
                                   (df['close'] > df['EMA20']) &
                                   (df['MACD'] > df['MACD_signal']))
        df['Bearish_Structure'] = ((df['EMA20'] < df['EMA50']) &
                                   (df['close'] < df['EMA20']) &
                                   (df['MACD'] < df['MACD_signal']))

        # Tick data untuk HFT
        df['Price_Change'] = df['close'].diff()
        df['Volume_Burst'] = df['volume'] > df['volume'].rolling(
            window=5).mean() * 2

        return df
    except Exception as e:
        logger(f"❌ Error calculating indicators: {str(e)}")
        return df


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """RSI calculation"""
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.rolling(window=period, min_periods=1).mean()
    avg_loss = loss.rolling(window=period, min_periods=1).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def macd_enhanced(series: pd.Series,
                  fast: int = 12,
                  slow: int = 26,
                  signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Enhanced MACD calculation"""
    exp1 = series.ewm(span=fast, adjust=False).mean()
    exp2 = series.ewm(span=slow, adjust=False).mean()
    macd_line = exp1 - exp2
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def stochastic_enhanced(df: pd.DataFrame,
                        k_period: int = 14,
                        d_period: int = 3) -> Tuple[pd.Series, pd.Series]:
    """Enhanced Stochastic Oscillator"""
    low_min = df['low'].rolling(window=k_period).min()
    high_max = df['high'].rolling(window=k_period).max()
    k = 100 * ((df['close'] - low_min) / (high_max - low_min))
    d = k.rolling(window=d_period).mean()
    return k, d


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate ATR with enhanced error handling"""
    try:
        if len(df) < period:
            return pd.Series([0.0008] * len(df), index=df.index)

        high = df['high']
        low = df['low']
        close = df['close']

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()

        return atr.fillna(0.0008)
    except Exception as e:
        logger(f"❌ Error calculating ATR: {str(e)}")
        return pd.Series([0.0008] * len(df), index=df.index)


def run_strategy(strategy: str, df: pd.DataFrame, symbol: str) -> Tuple[Optional[str], List[str]]:
    """Enhanced strategy execution with precise price analysis and validation"""
    try:
        if len(df) < 50:
            logger(f"❌ Insufficient data for {symbol}: {len(df)} bars (need 50+)")
            return None, []
            logger(f"❌ Insufficient data for {symbol}: {len(df)} bars (need 50+)")
            return None, [f"Insufficient data: {len(df)} bars"]

        # Get precision info from dataframe attributes or MT5
        digits = df.attrs.get('digits', 5)
        point = df.attrs.get('point', 0.00001)

        # Get real-time tick data dengan retry mechanism
        current_tick = None
        for tick_attempt in range(3):
            current_tick = mt5.symbol_info_tick(symbol)
            if current_tick and hasattr(current_tick, 'bid') and hasattr(current_tick, 'ask'):
                if current_tick.bid > 0 and current_tick.ask > 0:
                    break
            else:
                logger(f"⚠️ Tick attempt {tick_attempt + 1}: No valid tick for {symbol}")
                time.sleep(0.5)

        if not current_tick or not hasattr(current_tick, 'bid') or current_tick.bid <= 0:
            logger(f"❌ Cannot get valid real-time tick for {symbol} after 3 attempts")
            return None, [f"No valid tick data for {symbol}"]

        # Use most recent candle data
        last = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3] if len(df) > 3 else prev

        # Get precise current prices - MUST be defined early for all strategies
        current_bid = round(current_tick.bid, digits)
        current_ask = round(current_tick.ask, digits)
        current_spread = round(current_ask - current_bid, digits)
        current_price = round((current_bid + current_ask) / 2, digits)

        # Validate price precision
        last_close = round(last['close'], digits)
        last_high = round(last['high'], digits)
        last_low = round(last['low'], digits)
        last_open = round(last['open'], digits)

        action = None
        signals = []
        buy_signals = 0
        sell_signals = 0

        # Enhanced price logging with precision
        logger(f"📊 {symbol} Precise Data:")
        logger(f"   📈 Candle: O={last_open:.{digits}f} H={last_high:.{digits}f} L={last_low:.{digits}f} C={last_close:.{digits}f}")
        logger(f"   🎯 Real-time: Bid={current_bid:.{digits}f} Ask={current_ask:.{digits}f} Spread={current_spread:.{digits}f}")
        logger(f"   💡 Current Price: {current_price:.{digits}f} (Mid-price)")

        # Price movement analysis with precise calculations
        price_change = round(current_price - last_close, digits)
        price_change_pips = abs(price_change) / point

        logger(f"   📊 Price Movement: {price_change:+.{digits}f} ({price_change_pips:.1f} pips)")

        # Enhanced spread quality check with proper symbol-specific calculation
        if any(precious in symbol for precious in ["XAU", "XAG", "GOLD", "SILVER"]):
            # For precious metals, use symbol-specific point value
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info:
                point_value = getattr(symbol_info, 'point', 0.01)
                spread_pips = current_spread / point_value
                # Gold typically has 10-40 pip spreads normally
                max_allowed_spread = 100.0  # More realistic for gold
            else:
                # Fallback for gold if symbol_info fails
                spread_pips = current_spread / 0.01  # Assume 0.01 point for gold
                max_allowed_spread = 100.0
        elif "JPY" in symbol:
            spread_pips = current_spread / 0.01
            max_allowed_spread = 8.0  # JPY pairs
        else:
            spread_pips = current_spread / 0.0001
            max_allowed_spread = 5.0  # Major forex pairs

        spread_quality = "EXCELLENT" if spread_pips < max_allowed_spread * 0.3 else "GOOD" if spread_pips < max_allowed_spread * 0.6 else "FAIR" if spread_pips < max_allowed_spread * 0.8 else "POOR"

        logger(f"   🎯 Spread Analysis: {spread_pips:.1f} pips ({spread_quality}) | Max: {max_allowed_spread}")

        # More lenient spread filtering - only skip if extremely wide
        if spread_pips > max_allowed_spread:
            logger(f"⚠️ Spread too wide ({spread_pips:.1f} pips > {max_allowed_spread}) - reducing targets")
            spread_warning = True
        else:
            spread_warning = False

        # AI Market Analysis Integration
        ai_analysis = ai_market_analysis(symbol, df)
        logger(f"🤖 AI Analysis: {ai_analysis['recommendation']} (Confidence: {ai_analysis['confidence']}%)")

        # Get current trading session and adjustments
        current_session = get_current_trading_session()
        session_adjustments = adjust_strategy_for_session(
            strategy, current_session)

        # Check if high-impact news time
        is_news_time = is_high_impact_news_time()
        if is_news_time:
            logger("⚠️ High-impact news time - applying conservative filters")
            session_adjustments["signal_threshold_modifier"] += 2

        action = None
        signals = []
        buy_signals = 0
        sell_signals = 0

        # Enhanced price logging with precision
        logger(f"📊 {symbol} Precise Data:")
        logger(f"   📈 Candle: O={last_open:.{digits}f} H={last_high:.{digits}f} L={last_low:.{digits}f} C={last_close:.{digits}f}")
        logger(f"   🎯 Real-time: Bid={current_bid:.{digits}f} Ask={current_ask:.{digits}f} Spread={current_spread:.{digits}f}")
        logger(f"   💡 Current Price: {current_price:.{digits}f} (Mid-price)")

        # Price movement analysis with precise calculations
        price_change = round(current_price - last_close, digits)
        price_change_pips = abs(price_change) / point

        logger(f"   📊 Price Movement: {price_change:+.{digits}f} ({price_change_pips:.1f} pips)")

        # Debug: Log key indicator values
        logger(f"🔍 Key Indicators:")
        if 'EMA5' in last:
            logger(
                f"   EMA5: {last['EMA5']:.5f}, EMA13: {last['EMA13']:.5f}, EMA50: {last['EMA50']:.5f}"
            )
        if 'RSI' in last:
            logger(
                f"   RSI: {last['RSI']:.1f}, RSI7: {last.get('RSI7', 0):.1f}")
        if 'MACD' in last:
            logger(
                f"   MACD: {last['MACD']:.5f}, Signal: {last['MACD_signal']:.5f}, Hist: {last['MACD_histogram']:.5f}"
            )

        if strategy == "Scalping":
            # Ultra-precise scalping with multi-confirmation system for higher winrate
            logger("⚡ Scalping: Multi-confirmation EMA system with momentum filters...")

            # Get precise EMA values with enhanced calculations
            ema5_current = round(last.get('EMA5', current_price), digits)
            ema8_current = round(last.get('EMA8', current_price), digits)
            ema13_current = round(last.get('EMA13', current_price), digits)
            ema50_current = round(last.get('EMA50', current_price), digits)

            ema5_prev = round(prev.get('EMA5', current_price), digits)
            ema8_prev = round(prev.get('EMA8', current_price), digits)
            ema13_prev = round(prev.get('EMA13', current_price), digits)

            # Enhanced momentum calculation
            ema_momentum = last.get('EMA_Momentum', 0)
            ema5_slope = last.get('EMA5_Slope', 0)
            ema13_slope = last.get('EMA13_Slope', 0)

            # Multi-EMA alignment check (5>8>13 for bullish, 5<8<13 for bearish)
            bullish_alignment = ema5_current > ema8_current > ema13_current
            bearish_alignment = ema5_current < ema8_current < ema13_current

            logger(f"🔍 Enhanced Scalping EMAs: 5={ema5_current:.{digits}f}, 8={ema8_current:.{digits}f}, 13={ema13_current:.{digits}f}")
            logger(f"📈 Momentum: {ema_momentum:.3f}, Slope5: {ema5_slope:.{digits}f}")

            logger(f"🔍 Scalping EMAs: EMA5={ema5_current:.{digits}f}, EMA13={ema13_current:.{digits}f}, EMA50={ema50_current:.{digits}f}")

            # PRECISE CROSSOVER DETECTION with better thresholds
            min_cross_threshold = point * 5 if any(precious in symbol for precious in ["XAU", "GOLD"]) else point * 2

            ema5_cross_up = (ema5_current > ema13_current and ema5_prev <= ema13_prev and
                           abs(ema5_current - ema13_current) >= min_cross_threshold)
            ema5_cross_down = (ema5_current < ema13_current and ema5_prev >= ema13_prev and
                             abs(ema5_current - ema13_current) >= min_cross_threshold)

            # Enhanced trend confirmation with precise levels
            trend_bullish = (ema5_current > ema13_current > ema50_current and
                           current_price > ema50_current)
            trend_bearish = (ema5_current < ema13_current < ema50_current and
                           current_price < ema50_current)

            # Precise price action confirmation
            candle_body = abs(last_close - last_open)
            candle_range = last_high - last_low
            candle_body_ratio = candle_body / max(candle_range, point) if candle_range > 0 else 0

            bullish_candle = last_close > last_open and candle_body_ratio > 0.3
            bearish_candle = last_close < last_open and candle_body_ratio > 0.3

            logger(f"🕯️ Candle Analysis: Body={candle_body:.{digits}f}, Ratio={candle_body_ratio:.2f}")

            # Enhanced volatility filter with ATR
            atr_current = last.get('ATR', point * 10)
            atr_ratio = last.get('ATR_Ratio', 1.0)
            volatility_ok = atr_ratio > 0.5 and atr_current > point * 3  # More lenient for gold

            # Precise RSI analysis
            rsi_value = last.get('RSI', 50)
            rsi7_value = last.get('RSI7', 50)
            rsi_bullish = 35 < rsi_value < 75  # Optimal range for scalping
            rsi_bearish = 25 < rsi_value < 65

            logger(f"📊 RSI Analysis: RSI={rsi_value:.1f}, RSI7={rsi7_value:.1f}")

            # Precise BUY SIGNALS with proper distance validation
            if ema5_cross_up and spread_quality in ["EXCELLENT", "GOOD", "FAIR"]:
                if trend_bullish and bullish_candle and volatility_ok:
                    if rsi_value < 30 and rsi_value > prev.get('RSI', 50):  # RSI recovery
                        buy_signals += 8
                        signals.append(f"✅ SCALP STRONG: Precise EMA cross UP + RSI recovery @ {current_price:.{digits}f}")
                    elif rsi_bullish and current_price > ema50_current:
                        buy_signals += 6
                        signals.append(f"✅ SCALP: Precise EMA cross UP + trend @ {current_price:.{digits}f}")
                elif volatility_ok and rsi_bullish:
                    buy_signals += 4
                    signals.append(f"✅ SCALP: EMA cross UP + basic conditions @ {current_price:.{digits}f}")

            # Price above EMA5 continuation with precise conditions
            elif (current_price > ema5_current and ema5_current > ema13_current and
                  current_price > last_high * 0.999):  # More lenient
                if (rsi_value > 50 and last.get('MACD_histogram', 0) > prev.get('MACD_histogram', 0)):
                    buy_signals += 5
                    signals.append(f"✅ SCALP: Precise uptrend continuation @ {current_price:.{digits}f}")
                elif current_price > ema50_current:
                    buy_signals += 3
                    signals.append(f"✅ SCALP: Basic uptrend @ {current_price:.{digits}f}")

            # PRECISE SELL SIGNALS with proper distance validation
            if ema5_cross_down and spread_quality in ["EXCELLENT", "GOOD", "FAIR"]:
                if trend_bearish and bearish_candle and volatility_ok:
                    if rsi_value > 70 and rsi_value < prev.get('RSI', 50):  # RSI decline
                        sell_signals += 8
                        signals.append(f"✅ SCALP STRONG: Precise EMA cross DOWN + RSI decline @ {current_price:.{digits}f}")
                    elif rsi_bearish and current_price < ema50_current:
                        sell_signals += 6
                        signals.append(f"✅ SCALP: Precise EMA cross DOWN + trend @ {current_price:.{digits}f}")
                elif volatility_ok and rsi_bearish:
                    sell_signals += 4
                    signals.append(f"✅ SCALP: EMA cross DOWN + basic conditions @ {current_price:.{digits}f}")

            # Price below EMA5 continuation with precise conditions
            elif (current_price < ema5_current and ema5_current < ema13_current and
                  current_price < last_low * 1.001):  # More lenient
                if (rsi_value < 50 and last.get('MACD_histogram', 0) < prev.get('MACD_histogram', 0)):
                    sell_signals += 5
                    signals.append(f"✅ SCALP: Precise downtrend continuation @ {current_price:.{digits}f}")
                elif current_price < ema50_current:
                    sell_signals += 3
                    signals.append(f"✅ SCALP: Basic downtrend @ {current_price:.{digits}f}")

            # KONFIRMASI TAMBAHAN: RSI Extreme Levels (80/20)
            if last.get('RSI', 50) < 25:  # More lenient oversold
                buy_signals += 2
                signals.append(f"✅ SCALP: RSI oversold ({last.get('RSI', 50):.1f})")
            elif last.get('RSI', 50) > 75:  # More lenient overbought
                sell_signals += 2
                signals.append(f"✅ SCALP: RSI overbought ({last.get('RSI', 50):.1f})")

            # KONFIRMASI MOMENTUM: MACD Histogram
            if (last.get('MACD_histogram', 0) > 0 and
                    last.get('MACD_histogram', 0) > prev.get('MACD_histogram', 0)):
                buy_signals += 2
                signals.append("✅ SCALP: MACD momentum bullish")
            elif (last.get('MACD_histogram', 0) < 0 and
                  last.get('MACD_histogram', 0) < prev.get('MACD_histogram', 0)):
                sell_signals += 2
                signals.append("✅ SCALP: MACD momentum bearish")

            # PRICE ACTION: Strong candle dengan EMA konfirmasi
            if (last.get('Strong_Bullish_Candle', False) and ema5_current > ema13_current):
                buy_signals += 2
                signals.append("✅ SCALP: Strong bullish candle + EMA alignment")
            elif (last.get('Strong_Bearish_Candle', False) and ema5_current < ema13_current):
                sell_signals += 2
                signals.append("✅ SCALP: Strong bearish candle + EMA alignment")

            # KONFIRMASI VOLUME (jika tersedia)
            volume_avg = df['volume'].rolling(window=10).mean().iloc[-1] if 'volume' in df else 1
            current_volume = last.get('volume', 1)
            if current_volume > volume_avg * 1.3:
                if ema5_current > ema13_current:
                    buy_signals += 1
                    signals.append("✅ SCALP: High volume confirmation bullish")
                elif ema5_current < ema13_current:
                    sell_signals += 1
                    signals.append("✅ SCALP: High volume confirmation bearish")

        elif strategy == "HFT":
            # Enhanced HFT: Precise tick-level analysis
            logger("⚡ HFT: Precise tick-level analysis with micro-second accuracy...")

            # Get precise tick movement data
            tick_time = current_tick.time
            last_tick_time = getattr(current_tick, 'time_msc', tick_time * 1000) / 1000

            # Calculate precise movement since last candle
            tick_vs_candle_change = round(current_price - last_close, digits)
            tick_vs_candle_pips = abs(tick_vs_candle_change) / point

            logger(f"🔬 HFT Tick Analysis:")
            logger(f"   📊 Tick vs Candle: {tick_vs_candle_change:+.{digits}f} ({tick_vs_candle_pips:.2f} pips)")
            logger(f"   🎯 Spread: {spread_pips:.2f} pips ({spread_quality})")

            # Optimal HFT movement range (0.1-3 pips for fastest execution)
            optimal_movement = 0.1 <= tick_vs_candle_pips <= 3.0

            # Micro-acceleration detection with precise calculation
            prev_tick_change = round(last_close - prev['close'], digits)
            acceleration_ratio = abs(tick_vs_candle_change) / max(abs(prev_tick_change), point)
            has_acceleration = acceleration_ratio > 1.5

            logger(f"   ⚡ Acceleration Ratio: {acceleration_ratio:.2f}")

            # Enhanced volume analysis for HFT
            tick_volume_current = last.get('tick_volume', 1)
            tick_volume_avg = df['tick_volume'].rolling(5).mean().iloc[-1] if 'tick_volume' in df else 1
            volume_surge = tick_volume_current > tick_volume_avg * 2.0

            # Precise EMA micro-analysis - define missing variables
            ema5_current = round(last.get('EMA5', current_price), digits)
            ema5_prev = round(prev.get('EMA5', current_price), digits)
            ema5_slope = round(ema5_current - ema5_prev, digits)
            ema5_acceleration = abs(ema5_slope) > point * 2

            logger(f"   📈 EMA5 Slope: {ema5_slope:+.{digits}f} pips, Acceleration: {ema5_acceleration}")

            # HFT Signal 1: Precise micro-momentum with ultra-tight conditions
            if optimal_movement and spread_quality == "EXCELLENT":  # Only excellent spreads
                if tick_vs_candle_change > 0 and current_bid > last_close:  # Clear bullish movement
                    if has_acceleration and volume_surge and ema5_acceleration:
                        buy_signals += 8
                        signals.append(f"✅ HFT ULTRA: Micro-momentum UP {tick_vs_candle_pips:.2f} pips + acceleration + volume @ {current_bid:.{digits}f}")
                    elif ema5_slope > 0 and current_price > ema5_current:
                        buy_signals += 6
                        signals.append(f"✅ HFT STRONG: Micro-trend UP {tick_vs_candle_pips:.2f} pips @ {current_bid:.{digits}f}")
                    elif optimal_movement:
                        buy_signals += 4
                        signals.append(f"✅ HFT: Basic momentum UP {tick_vs_candle_pips:.2f} pips @ {current_bid:.{digits}f}")

                elif tick_vs_candle_change < 0 and current_ask < last_close:  # Clear bearish movement
                    if has_acceleration and volume_surge and ema5_acceleration:
                        sell_signals += 8
                        signals.append(f"✅ HFT ULTRA: Micro-momentum DOWN {tick_vs_candle_pips:.2f} pips + acceleration + volume @ {current_ask:.{digits}f}")
                    elif ema5_slope < 0 and current_price < ema5_current:
                        sell_signals += 6
                        signals.append(f"✅ HFT STRONG: Micro-trend DOWN {tick_vs_candle_pips:.2f} pips @ {current_ask:.{digits}f}")
                    elif optimal_movement:
                        sell_signals += 4
                        signals.append(f"✅ HFT: Basic momentum DOWN {tick_vs_candle_pips:.2f} pips @ {current_ask:.{digits}f}")

            # HFT Signal 2: Tick-level EMA5 precision crossing
            if ema5_tick_distance < point * 3:  # Very close to EMA5
                if current_price > ema5_current and ema5_slope > 0:
                    buy_signals += 5
                    signals.append(f"✅ HFT: EMA5 precision cross UP @ {current_price:.{digits}f}")
                elif current_price < ema5_current and ema5_slope < 0:
                    sell_signals += 5
                    signals.append(f"✅ HFT: EMA5 precision cross DOWN @ {current_price:.{digits}f}")

            # HFT Signal 3: Spread compression opportunity
            if spread_pips < 0.5:  # Ultra-tight spread
                candle_direction = 1 if last_close > last_open else -1
                tick_direction = 1 if current_price > last_close else -1

                if candle_direction == tick_direction == 1:
                    buy_signals += 3
                    signals.append(f"✅ HFT: Spread compression BUY ({spread_pips:.2f} pips) @ {current_bid:.{digits}f}")
                elif candle_direction == tick_direction == -1:
                    sell_signals += 3
                    signals.append(f"✅ HFT: Spread compression SELL ({spread_pips:.2f} pips) @ {current_ask:.{digits}f}")

            # HFT Signal 2: Bid/Ask spread tightening (market efficiency)
            try:
                tick = mt5.symbol_info_tick(symbol)
                if tick:
                    current_spread = tick.ask - tick.bid
                    avg_spread = df['high'].rolling(5).mean().iloc[-1] - df['low'].rolling(5).mean().iloc[-1]
                    if current_spread < avg_spread * 0.8:  # Spread tightening = liquidity
                        if last['close'] > prev['close']:
                            buy_signals += 3
                            signals.append("✅ HFT: Spread tightening + bullish")
                        elif last['close'] < prev['close']:
                            sell_signals += 3
                            signals.append("✅ HFT: Spread tightening + bearish")
            except:
                pass

            # HFT Signal 3: EMA5 micro-crossover (tick-level)
            if last['EMA5'] > prev['EMA5'] and prev['EMA5'] <= prev2.get('EMA5', prev['EMA5']):
                if last['close'] > last['EMA5']:
                    buy_signals += 4
                    signals.append("✅ HFT: EMA5 micro-trend UP")
            elif last['EMA5'] < prev['EMA5'] and prev['EMA5'] >= prev2.get('EMA5', prev['EMA5']):
                if last['close'] < last['EMA5']:
                    sell_signals += 4
                    signals.append("✅ HFT: EMA5 micro-trend DOWN")

            # HFT Signal 4: RSI extreme dengan recovery cepat (scalping overbought/oversold)
            if last['RSI7'] > 85 and (last['RSI7'] - prev['RSI7']) < -2:
                sell_signals += 3
                signals.append(f"✅ HFT: RSI extreme decline {last['RSI7']:.1f}")
            elif last['RSI7'] < 15 and (last['RSI7'] - prev['RSI7']) > 2:
                buy_signals += 3
                signals.append(f"✅ HFT: RSI extreme recovery {last['RSI7']:.1f}")

            # HFT Signal 5: Tick volume burst (institutional entry detection)
            tick_volume_current = last.get('tick_volume', 1)
            tick_volume_avg = df['tick_volume'].rolling(10).mean().iloc[-1] if 'tick_volume' in df else 1
            if tick_volume_current > tick_volume_avg * 2:
                if last['close'] > last['open']:
                    buy_signals += 2
                    signals.append("✅ HFT: Volume burst bullish")
                elif last['close'] < last['open']:
                    sell_signals += 2
                    signals.append("✅ HFT: Volume burst bearish")

        elif strategy == "Intraday":
            # Enhanced intraday with precise trend analysis and multi-timeframe confirmation
            logger("📈 Intraday: Precise trend analysis with real-time validation...")

            # Get precise EMA values for intraday analysis
            ema20_current = round(last.get('EMA20', current_price), digits)
            ema50_current = round(last.get('EMA50', current_price), digits)
            ema200_current = round(last.get('EMA200', current_price), digits)

            ema20_prev = round(prev.get('EMA20', current_price), digits)
            ema50_prev = round(prev.get('EMA50', current_price), digits)

            logger(f"📈 Intraday EMAs: EMA20={ema20_current:.{digits}f}, EMA50={ema50_current:.{digits}f}, EMA200={ema200_current:.{digits}f}")

            # Precise trend classification with minimum separation
            min_separation = point * 5  # Minimum 5 points between EMAs

            strong_uptrend = (ema20_current > ema50_current + min_separation > ema200_current + min_separation and
                            current_price > ema20_current)
            strong_downtrend = (ema20_current < ema50_current - min_separation < ema200_current - min_separation and
                              current_price < ema20_current)

            # Precise crossover detection with confirmation
            ema20_cross_up = (ema20_current > ema50_current and ema20_prev <= ema50_prev and
                            abs(ema20_current - ema50_current) >= min_separation)
            ema20_cross_down = (ema20_current < ema50_current and ema20_prev >= ema50_prev and
                              abs(ema20_current - ema50_current) >= min_separation)

            # Enhanced RSI with precise levels
            rsi14 = last.get('RSI14', 50)
            rsi_smooth = last.get('RSI_Smooth', rsi14)
            rsi_momentum_up = 40 < rsi14 < 80 and rsi14 > rsi_smooth  # Rising RSI
            rsi_momentum_down = 20 < rsi14 < 60 and rsi14 < rsi_smooth  # Falling RSI

            logger(f"📊 RSI Analysis: RSI14={rsi14:.1f}, RSI_Smooth={rsi_smooth:.1f}")

            # Precise MACD analysis
            macd_value = last.get('MACD', 0)
            macd_signal = last.get('MACD_signal', 0)
            macd_hist = last.get('MACD_histogram', 0)
            macd_hist_prev = prev.get('MACD_histogram', 0)

            macd_bullish = (macd_value > macd_signal and macd_hist > macd_hist_prev and macd_hist > 0)
            macd_bearish = (macd_value < macd_signal and macd_hist < macd_hist_prev and macd_hist < 0)

            # Enhanced volume analysis
            volume_current = last.get('volume', 1)
            volume_20 = df['volume'].rolling(20).mean().iloc[-1] if 'volume' in df else 1
            volume_50 = df['volume'].rolling(50).mean().iloc[-1] if 'volume' in df else 1

            volume_confirmation = volume_current > volume_20 * 1.2
            volume_surge = volume_current > volume_50 * 1.5

            # Precise candle analysis
            candle_body = abs(last_close - last_open)
            candle_wicks = (last_high - max(last_close, last_open)) + (min(last_close, last_open) - last_low)
            body_to_wick_ratio = candle_body / max(candle_wicks, point) if candle_wicks > 0 else 5

            strong_candle = body_to_wick_ratio > 1.5 and candle_body > atr_current * 0.3

            logger(f"🕯️ Candle Strength: Body/Wick={body_to_wick_ratio:.2f}, Strong={strong_candle}")

            # PRECISE BUY SIGNALS
            if ema20_cross_up and spread_quality in ["EXCELLENT", "GOOD"]:
                if strong_uptrend and macd_bullish and rsi_momentum_up and volume_surge:
                    buy_signals += 9
                    signals.append(f"✅ INTRADAY ULTRA: Precise EMA cross + full confirmation @ {current_price:.{digits}f}")
                elif strong_uptrend and macd_bullish and rsi_momentum_up:
                    buy_signals += 7
                    signals.append(f"✅ INTRADAY STRONG: EMA cross + trend + momentum @ {current_price:.{digits}f}")
                elif current_price > ema200_current and volume_confirmation:
                    buy_signals += 5
                    signals.append(f"✅ INTRADAY: EMA cross + EMA200 filter @ {current_price:.{digits}f}")

            # Precise trend continuation
            elif strong_uptrend and current_price > last_high * 0.999:  # Near recent high
                if (rsi14 > 55 and macd_bullish and strong_candle and
                    current_price > df['high'].rolling(10).max().iloc[-2]):  # New 10-period high
                    buy_signals += 6
                    signals.append(f"✅ INTRADAY: Precise breakout continuation @ {current_price:.{digits}f}")
                elif rsi14 > 50 and macd_value > 0 and volume_confirmation:
                    buy_signals += 4
                    signals.append(f"✅ INTRADAY: Trend continuation + volume @ {current_price:.{digits}f}")
                elif current_price > ema20_current:
                    buy_signals += 2
                    signals.append(f"✅ INTRADAY: Basic uptrend @ {current_price:.{digits}f}")

            # PRECISE SELL SIGNALS
            if ema20_cross_down and spread_quality in ["EXCELLENT", "GOOD"]:
                if strong_downtrend and macd_bearish and rsi_momentum_down and volume_surge:
                    sell_signals += 9
                    signals.append(f"✅ INTRADAY ULTRA: Precise EMA cross + full confirmation @ {current_price:.{digits}f}")
                elif strong_downtrend and macd_bearish and rsi_momentum_down:
                    sell_signals += 7
                    signals.append(f"✅ INTRADAY STRONG: EMA cross + trend + momentum @ {current_price:.{digits}f}")
                elif current_price < ema200_current and volume_confirmation:
                    sell_signals += 5
                    signals.append(f"✅ INTRADAY: EMA cross + EMA200 filter @ {current_price:.{digits}f}")

            # Precise trend continuation
            elif strong_downtrend and current_price < last_low * 1.001:  # Near recent low
                if (rsi14 < 45 and macd_bearish and strong_candle and
                    current_price < df['low'].rolling(10).min().iloc[-2]):  # New 10-period low
                    sell_signals += 6
                    signals.append(f"✅ INTRADAY: Precise breakdown continuation @ {current_price:.{digits}f}")
                elif rsi14 < 50 and macd_value < 0 and volume_confirmation:
                    sell_signals += 4
                    signals.append(f"✅ INTRADAY: Trend continuation + volume @ {current_price:.{digits}f}")
                elif current_price < ema20_current:
                    sell_signals += 2
                    signals.append(f"✅ INTRADAY: Basic downtrend @ {current_price:.{digits}f}")

            # KONFIRMASI TREND: EMA200 sebagai filter utama
            if (last['EMA20'] > last['EMA50'] > last['EMA200']
                    and last['close'] > last['EMA200'] and last['RSI14'] > 50):
                buy_signals += 2
                signals.append(
                    "✅ INTRADAY: Strong bullish EMA alignment (20>50>200)")
            elif (last['EMA20'] < last['EMA50'] < last['EMA200']
                  and last['close'] < last['EMA200'] and last['RSI14'] < 50):
                sell_signals += 2
                signals.append(
                    "✅ INTRADAY: Strong bearish EMA alignment (20<50<200)")

            # KONFIRMASI MACD: Signal line crossover
            if (last['MACD'] > last['MACD_signal']
                    and prev['MACD'] <= prev['MACD_signal']
                    and last['close'] > last['EMA200']):
                buy_signals += 2
                signals.append(
                    "✅ INTRADAY: MACD signal line cross UP + EMA200 bullish")
            elif (last['MACD'] < last['MACD_signal']
                  and prev['MACD'] >= prev['MACD_signal']
                  and last['close'] < last['EMA200']):
                sell_signals += 2
                signals.append(
                    "✅ INTRADAY: MACD signal line cross DOWN + EMA200 bearish")

            # MOMENTUM CONFIRMATION: Trend strength
            volume_avg = df['volume'].rolling(
                window=20).mean().iloc[-1] if 'volume' in df else 1
            current_volume = last.get('volume', 1)
            volume_factor = current_volume / volume_avg if volume_avg > 0 else 1

            if (last['Trend_Strength'] > 1.5 and volume_factor > 1.2
                    and last['EMA20'] > last['EMA50']
                    and last['close'] > last['EMA200']):
                buy_signals += 2
                signals.append(
                    "✅ INTRADAY: Strong uptrend momentum + volume ({last['Trend_Strength']:.2f})"
                )
            elif (last['Trend_Strength'] > 1.5 and volume_factor > 1.2
                  and last['EMA20'] < last['EMA50']
                  and last['close'] < last['EMA200']):
                sell_signals += 2
                signals.append(
                    "✅ INTRADAY: Strong downtrend momentum + volume ({last['Trend_Strength']:.2f})"
                )

            # BREAKOUT CONFIRMATION
            if (last['Bullish_Breakout'] and last['RSI14'] > 60
                    and last['close'] > last['EMA200']):
                buy_signals += 2
                signals.append(
                    "✅ INTRADAY: Breakout UP + RSI momentum + EMA200 filter")
            elif (last['Bearish_Breakout'] and last['RSI14'] < 40
                  and last['close'] < last['EMA200']):
                sell_signals += 2
                signals.append(
                    "✅ INTRADAY: Breakout DOWN + RSI momentum + EMA200 filter")

        elif strategy == "Arbitrage":
            # Enhanced Arbitrage: Precise statistical mean reversion with real-time validation
            logger("🔄 Arbitrage: Precise mean reversion with statistical edge detection...")

            # Get precise Bollinger Band values
            bb_upper = round(last.get('BB_Upper', current_price * 1.02), digits)
            bb_lower = round(last.get('BB_Lower', current_price * 0.98), digits)
            bb_middle = round(last.get('BB_Middle', current_price), digits)

            # Precise BB position calculation
            bb_range = bb_upper - bb_lower
            if bb_range > point:
                bb_position = (current_price - bb_lower) / bb_range
            else:
                bb_position = 0.5

            bb_width = last.get('BB_Width', 0.02)

            logger(f"📊 Bollinger Analysis: Position={bb_position:.3f}, Width={bb_width:.4f}")
            logger(
                f"   🎯 BB Levels: Upper={bb_upper:.{digits}f}, Middle={bb_middle:.{digits}f}, Lower={bb_lower:.{digits}f}"
            )

            # Statistical deviation analysis with precise calculation
            price_vs_middle = abs(current_price - bb_middle)
            price_deviation = price_vs_middle / bb_middle if bb_middle > 0 else 0
            deviation_pips = price_vs_middle / point

            # Enhanced deviation thresholds based on symbol
            if "JPY" in symbol:
                significant_deviation = deviation_pips > 5.0  # 5 pips for JPY
            elif any(precious in symbol for precious in ["XAU", "GOLD"]):
                significant_deviation = deviation_pips > 20.0  # $2.0 for Gold
            else:
                significant_deviation = deviation_pips > 3.0  # 3 pips for major pairs

            logger(f"📈 Deviation Analysis: {price_deviation:.4f} ({deviation_pips:.1f} pips), Significant: {significant_deviation}")

            # Enhanced RSI analysis with multiple timeframes
            rsi14 = last.get('RSI14', 50)
            rsi7 = last.get('RSI7', 50)
            rsi_smooth = last.get('RSI_Smooth', rsi14)

            rsi_extreme_oversold = rsi14 < 20 and rsi7 < 25
            rsi_extreme_overbought = rsi14 > 80 and rsi7 > 75
            rsi_moderate_oversold = 20 < rsi14 < 35
            rsi_moderate_overbought = 65 < rsi14 < 80

            # Enhanced Stochastic analysis
            stoch_k = last.get('STOCH_K', 50)
            stoch_d = last.get('STOCH_D', 50)
            stoch_k_prev = prev.get('STOCH_K', stoch_k)

            stoch_oversold = stoch_k < 15 and stoch_d < 20
            stoch_overbought = stoch_k > 85 and stoch_d > 80
            stoch_turning_up = stoch_k > stoch_k_prev and stoch_k < 30
            stoch_turning_down = stoch_k < stoch_k_prev and stoch_k > 70

            logger(f"📊 Oscillators: RSI14={rsi14:.1f}, RSI7={rsi7:.1f}, Stoch_K={stoch_k:.1f}")

            # Precise reversal momentum with real-time validation
            reversal_momentum_up = (current_price > last_close and last_close <= prev['close'] and
                                   current_price > bb_lower)
            reversal_momentum_down = (current_price < last_close and last_close >= prev['close'] and
                                    current_price < bb_upper)

            # PRECISE EXTREME OVERSOLD REVERSAL
            if bb_position <= 0.05 and significant_deviation and spread_quality in ["EXCELLENT", "GOOD"]:  # Bottom 5%
                if rsi_extreme_oversold and reversal_momentum_up:
                    if stoch_oversold and stoch_turning_up and volume_surge:
                        buy_signals += 10
                        signals.append(f"✅ ARB ULTRA: Extreme oversold + volume @ {current_price:.{digits}f} (BB:{bb_position:.3f}, RSI:{rsi14:.1f})")
                    elif stoch_turning_up:
                        buy_signals += 8
                        signals.append(f"✅ ARB STRONG: Extreme oversold reversal @ {current_price:.{digits}f} (BB:{bb_position:.3f})")
                    else:
                        buy_signals += 6
                        signals.append(f"✅ ARB: Oversold bounce @ {current_price:.{digits}f} (RSI:{rsi14:.1f})")
                elif rsi_moderate_oversold and reversal_momentum_up:
                    buy_signals += 4
                    signals.append(f"✅ ARB: Moderate oversold @ {current_price:.{digits}f} (BB:{bb_position:.3f})")

            # Precise support level bounce
            elif bb_position <= 0.15 and current_price <= bb_lower * 1.002:  # Near BB lower
                if rsi14 < 35 and current_price > prev['close']:
                    buy_signals += 5
                    signals.append(f"✅ ARB: Support bounce @ {current_price:.{digits}f} (BB_Lower: {bb_lower:.{digits}f})")

            # PRECISE EXTREME OVERBOUGHT REVERSAL
            if bb_position >= 0.95 and significant_deviation and spread_quality in ["EXCELLENT", "GOOD"]:  # Top 5%
                if rsi_extreme_overbought and reversal_momentum_down:
                    if stoch_overbought and stoch_turning_down and volume_surge:
                        sell_signals += 10
                        signals.append(f"✅ ARB ULTRA: Extreme overbought + volume @ {current_price:.{digits}f} (BB:{bb_position:.3f}, RSI:{rsi14:.1f})")
                    elif stoch_turning_down:
                        sell_signals += 8
                        signals.append(f"✅ ARB STRONG: Extreme overbought reversal @ {current_price:.{digits}f} (BB:{bb_position:.3f})")
                    else:
                        sell_signals += 6
                        signals.append(f"✅ ARB: Overbought decline @ {current_price:.{digits}f} (RSI:{rsi14:.1f})")
                elif rsi_moderate_overbought and reversal_momentum_down:
                    sell_signals += 4
                    signals.append(f"✅ ARB: Moderate overbought @ {current_price:.{digits}f} (BB:{bb_position:.3f})")

            # Precise resistance level rejection
            elif bb_position >= 0.85 and current_price >= bb_upper * 0.998:  # Near BB upper
                if rsi14 > 65 and current_price < prev['close']:
                    sell_signals += 5
                    signals.append(f"✅ ARB: Resistance rejection @ {current_price:.{digits}f} (BB_Upper: {bb_upper:.{digits}f})")

            # Mean reversion from middle BB with precise conditions
            middle_distance = abs(current_price - bb_middle) / point
            if 2.0 < middle_distance < 8.0:  # Optimal distance from middle
                if current_price < bb_middle and rsi14 < 45 and reversal_momentum_up:
                    buy_signals += 3
                    signals.append(f"✅ ARB: Mean reversion UP @ {current_price:.{digits}f} (Middle: {bb_middle:.{digits}f})")
                elif current_price > bb_middle and rsi14 > 55 and reversal_momentum_down:
                    sell_signals += 3
                    signals.append(f"✅ ARB: Mean reversion DOWN @ {current_price:.{digits}f} (Middle: {bb_middle:.{digits}f})")

            # Arbitrage Signal 2: Mean reversion dengan statistical confidence
            price_distance_from_mean = abs(last['close'] - last['BB_Middle']) / last['BB_Middle']
            if price_distance_from_mean > 0.015:  # 1.5% deviation dari mean
                if last['close'] < last['BB_Middle'] and last['close'] > prev['close']:
                    # Price below mean but recovering
                    buy_signals += 3
                    signals.append(f"✅ ARBITRAGE: Below-mean recovery ({price_distance_from_mean:.3f})")
                elif last['close'] > last['BB_Middle'] and last['close'] < prev['close']:
                    # Price above mean but declining
                    sell_signals += 3
                    signals.append(f"✅ ARBITRAGE: Above-mean decline ({price_distance_from_mean:.3f})")

            # Arbitrage Signal 3: RSI50 crossover dengan momentum confirmation
            if last['RSI14'] > 50 and prev['RSI14'] <= 50:
                if last['close'] > last['EMA20'] and last['MACD_histogram'] > 0:
                    buy_signals += 2
                    signals.append("✅ ARBITRAGE: RSI50 cross UP + momentum")
            elif last['RSI14'] < 50 and prev['RSI14'] >= 50:
                if last['close'] < last['EMA20'] and last['MACD_histogram'] < 0:
                    sell_signals += 2
                    signals.append("✅ ARBITRAGE: RSI50 cross DOWN + momentum")

            # Arbitrage Signal 4: Support/Resistance bounce
            support_level = df['low'].rolling(20).min().iloc[-1]
            resistance_level = df['high'].rolling(20).max().iloc[-1]

            if abs(last['close'] - support_level) / last['close'] < 0.002:  # Near support
                if last['close'] > prev['close'] and last['RSI14'] < 40:
                    buy_signals += 3
                    signals.append("✅ ARBITRAGE: Support bounce + oversold")
            elif abs(last['close'] - resistance_level) / last['close'] < 0.002:  # Near resistance
                if last['close'] < prev['close'] and last['RSI14'] > 60:
                    sell_signals += 3
                    signals.append("✅ ARBITRAGE: Resistance rejection + overbought")

            # Arbitrage Signal 5: Volume-confirmed reversion
            volume_avg = df['volume'].rolling(20).mean().iloc[-1] if 'volume' in df else 1
            current_volume = last.get('volume', 1)
            if current_volume > volume_avg * 1.5:  # High volume confirmation
                if bb_position < 0.2 and last['close'] > prev['close']:
                    buy_signals += 2
                    signals.append("✅ ARBITRAGE: Volume-confirmed oversold bounce")
                elif bb_position > 0.8 and last['close'] < prev['close']:
                    sell_signals += 2
                    signals.append("✅ ARBITRAGE: Volume-confirmed overbought decline")

        # Session-aware signal thresholds
        base_min_signals = {
            "Scalping": 3,  # Moderate confirmation for scalping
            "HFT": 2,  # Very aggressive - fastest execution
            "Intraday": 4,  # Strong confirmation for longer trades
            "Arbitrage": 2  # Quick mean reversion entries
        }

        # Apply session adjustments to threshold
        base_threshold = base_min_signals.get(strategy, 2)
        threshold_modifier = session_adjustments.get(
            "signal_threshold_modifier", 0)
        threshold = max(1, base_threshold +
                        threshold_modifier)  # Minimum threshold of 1

        # Log session impact
        if current_session:
            session_name = current_session.get("name", "Unknown")
            volatility = current_session["info"]["volatility"]
            logger(
                f"📊 {session_name} session ({volatility} volatility) - adjusted threshold: {base_threshold} → {threshold}"
            )
        else:
            logger(f"📊 Default session - threshold: {threshold}")

        # ADVANCED SIGNAL QUALITY ASSESSMENT for Higher Winrate
        total_initial_signals = buy_signals + sell_signals

        # Calculate signal quality score (0-100)
        signal_quality_score = 0
        quality_factors = []

        # Factor 1: Trend alignment strength
        ema5_current = last.get('EMA5', current_price)
        ema13_current = last.get('EMA13', current_price)
        ema50_current = last.get('EMA50', current_price)
        ema200_current = last.get('EMA200', current_price)

        if ema5_current > ema13_current > ema50_current > ema200_current:
            signal_quality_score += 25
            quality_factors.append("Strong bullish alignment")
        elif ema5_current < ema13_current < ema50_current < ema200_current:
            signal_quality_score += 25
            quality_factors.append("Strong bearish alignment")
        elif ema5_current > ema13_current > ema50_current:
            signal_quality_score += 15
            quality_factors.append("Medium bullish alignment")
        elif ema5_current < ema13_current < ema50_current:
            signal_quality_score += 15
            quality_factors.append("Medium bearish alignment")

        # Factor 2: RSI confluence
        rsi_value = last.get('RSI', 50)
        if 40 <= rsi_value <= 60:
            signal_quality_score += 20
            quality_factors.append("RSI in optimal range")
        elif 30 <= rsi_value <= 70:
            signal_quality_score += 15
            quality_factors.append("RSI in good range")
        elif rsi_value < 25 or rsi_value > 75:
            signal_quality_score += 10
            quality_factors.append("RSI extreme (reversal potential)")

        # Factor 3: Market session quality
        current_session = get_current_trading_session()
        if current_session:
            volatility = current_session["info"]["volatility"]
            if volatility in ["high", "very_high"]:
                signal_quality_score += 20
                quality_factors.append("High volatility session")
            elif volatility == "medium":
                signal_quality_score += 15
                quality_factors.append("Medium volatility session")

        # Factor 4: MACD confirmation
        macd_hist = last.get('MACD_histogram', 0)
        macd_hist_prev = prev.get('MACD_histogram', 0)
        if abs(macd_hist) > abs(macd_hist_prev):
            signal_quality_score += 15
            quality_factors.append("MACD momentum increasing")

        # Factor 5: Volume confirmation (if available)
        if 'volume' in df.columns:
            vol_avg = df['volume'].rolling(20).mean().iloc[-1]
            current_vol = last.get('volume', 1)
            if current_vol > vol_avg * 1.3:
                signal_quality_score += 10
                quality_factors.append("Above average volume")

        logger(f"📊 Signal Quality Assessment: {signal_quality_score}/100")
        for factor in quality_factors:
            logger(f"   ✓ {factor}")

        # Quality-based signal filtering
        quality_threshold = 60  # Minimum quality score for signal approval

        if total_initial_signals < threshold and signal_quality_score >= quality_threshold:
            logger("🎯 HIGH QUALITY SIGNAL BOOST: Quality score meets threshold...")

            # AI-enhanced signal boost based on quality factors
            if "Strong bullish alignment" in quality_factors or "Strong bearish alignment" in quality_factors:
                if ema5_current > ema13_current:
                    buy_signals += 3
                    signals.append(f"🌟 QUALITY BOOST: Strong trend alignment BUY @ {current_price:.{digits}f}")
                else:
                    sell_signals += 3
                    signals.append(f"🌟 QUALITY BOOST: Strong trend alignment SELL @ {current_price:.{digits}f}")

            # Momentum-based enhancement
            if macd_hist > 0 and "MACD momentum increasing" in quality_factors:
                buy_signals += 2
                signals.append("🚀 QUALITY: Strong bullish momentum")
            elif macd_hist < 0 and "MACD momentum increasing" in quality_factors:
                sell_signals += 2
                signals.append("📉 QUALITY: Strong bearish momentum")

        elif total_initial_signals < threshold:
            logger(f"❌ Signal quality insufficient: {signal_quality_score}/100 < {quality_threshold}")
            logger("💡 Waiting for higher quality setup...")

            # AI-ALIGNED SIGNAL ENHANCEMENT
            if ai_analysis['market_structure'] == "BULLISH" and ai_analysis['confidence'] > 25:
                # Focus on BUY signals for bullish market
                if rsi_value < 40:  # Oversold in bullish market = opportunity
                    buy_signals += 3
                    signals.append(f"🤖 AI-BULLISH: RSI dip buy @ {current_price:.{digits}f} (RSI: {rsi_value:.1f})")
                elif ema5_current > ema13_current:
                    buy_signals += 2
                    signals.append(f"🤖 AI-BULLISH: EMA alignment buy @ {current_price:.{digits}f}")

            elif ai_analysis['market_structure'] == "BEARISH" and ai_analysis['confidence'] > 25:
                # Focus on SELL signals for bearish market
                if rsi_value > 60:  # Overbought in bearish market = opportunity
                    sell_signals += 3
                    signals.append(f"🤖 AI-BEARISH: RSI peak sell @ {current_price:.{digits}f} (RSI: {rsi_value:.1f})")
                elif ema5_current < ema13_current:
                    sell_signals += 2
                    signals.append(f"🤖 AI-BEARISH: EMA alignment sell @ {current_price:.{digits}f}")

            # MOMENTUM-BASED SIGNALS
            price_change_pips = abs(current_price - last_close) / point
            if price_change_pips > 5:  # Significant movement
                if current_price > last_close and ai_analysis['market_structure'] != "BEARISH":
                    buy_signals += 2
                    signals.append(f"🎯 MOMENTUM: Strong UP {price_change_pips:.1f} pips @ {current_price:.{digits}f}")
                elif current_price < last_close and ai_analysis['market_structure'] != "BULLISH":
                    sell_signals += 2
                    signals.append(f"🎯 MOMENTUM: Strong DOWN {price_change_pips:.1f} pips @ {current_price:.{digits}f}")

            # FALLBACK: If still no clear direction, use RSI extremes
            if buy_signals + sell_signals < threshold:
                if rsi_value < 30:
                    buy_signals += (threshold - (buy_signals + sell_signals))
                    signals.append(f"🆘 EXTREME: RSI oversold rescue @ {current_price:.{digits}f}")
                elif rsi_value > 70:
                    sell_signals += (threshold - (buy_signals + sell_signals))
                    signals.append(f"🆘 EXTREME: RSI overbought rescue @ {current_price:.{digits}f}")

        # Final Analysis
        logger(f"🔍 Enhanced Signal Results:")
        logger(f"   Final BUY Signals: {buy_signals}")
        logger(f"   Final SELL Signals: {sell_signals}")
        logger(f"   Enhancement Added: {(buy_signals + sell_signals) - total_initial_signals}")
        logger(f"   Session Adjustment: {session_adjustments.get('signal_threshold_modifier', 0)}")

        action = None
        signals = []
        buy_signals = 0
        sell_signals = 0

        # Enhanced price logging with precision
        logger(f"📊 {symbol} Precise Data:")
        logger(f"   📈 Candle: O={last_open:.{digits}f} H={last_high:.{digits}f} L={last_low:.{digits}f} C={last_close:.{digits}f}")
        logger(f"   🎯 Real-time: Bid={current_bid:.{digits}f} Ask={current_ask:.{digits}f} Spread={current_spread:.{digits}f}")
        logger(f"   💡 Current Price: {current_price:.{digits}f} (Mid-price)")

        # Price movement analysis with precise calculations
        price_change = round(current_price - last_close, digits)
        price_change_pips = abs(price_change) / point

        logger(f"   📊 Price Movement: {price_change:+.{digits}f} ({price_change_pips:.1f} pips)")

        # Decision logic with tie-breaker
        total_signals = buy_signals + sell_signals
        signal_strength = max(buy_signals, sell_signals)

        # Lower threshold for debugging if no strong signals
        effective_threshold = max(1, threshold - 1) if signals else threshold

        if buy_signals > sell_signals and buy_signals >= effective_threshold:
            action = "BUY"
            confidence = (buy_signals / max(total_signals, 1)) * 100
            logger(
                f"🟢 {strategy} BUY SIGNAL ACTIVATED! Score: {buy_signals} vs {sell_signals} (confidence: {confidence:.1f}%)"
            )
        elif sell_signals > buy_signals and sell_signals >= effective_threshold:
            action = "SELL"
            confidence = (sell_signals / max(total_signals, 1)) * 100
            logger(
                f"🔴 {strategy} SELL SIGNAL ACTIVATED! Score: {sell_signals} vs {buy_signals} (confidence: {confidence:.1f}%)"
            )
        else:
            logger(
                f"⚪ {strategy} WAITING. BUY:{buy_signals} SELL:{sell_signals} (need:{effective_threshold})"
            )

            # Debug recommendation
            if total_signals > 0:
                stronger_side = "BUY" if buy_signals > sell_signals else "SELL"
                logger(
                    f"💡 Closest to signal: {stronger_side} ({max(buy_signals, sell_signals)}/{effective_threshold})"
                )

        return action, signals

    except Exception as e:
        logger(f"❌ Strategy {strategy} error: {str(e)}")
        import traceback
        logger(f"🔍 Traceback: {traceback.format_exc()}")
        return None, [f"❌ Strategy {strategy} error: {str(e)}"]


def get_symbol_data(symbol: str,
                    timeframe: int,
                    n: int = 200) -> Optional[pd.DataFrame]:
    """
    Enhanced data fetching with precise price validation and error handling.

    Args:
        symbol (str): Trading symbol (e.g., 'EURUSD')
        timeframe (int): MetaTrader5 timeframe constant
        n (int): Number of candles to fetch (default: 200)

    Returns:
        Optional[pd.DataFrame]: DataFrame with OHLCV data or None if failed
    """
    try:
        if not check_mt5_status():
            logger("❌ MT5 not connected for data request")
            return None

        # Validate symbol first with enhanced validation
        valid_symbol = validate_and_activate_symbol(symbol)
        if not valid_symbol:
            logger(f"❌ Cannot validate {symbol} for data request")
            return None

        # Get symbol info for precision settings
        symbol_info = mt5.symbol_info(valid_symbol)
        if not symbol_info:
            logger(f"❌ Cannot get symbol info for {valid_symbol}")
            return None

        # Extract precision info
        digits = getattr(symbol_info, 'digits', 5)
        point = getattr(symbol_info, 'point', 0.00001)

        logger(f"🔍 Symbol precision: {valid_symbol} - Digits: {digits}, Point: {point}")

        # Adjust data count based on timeframe for better analysis
        timeframe_adjustments = {
            mt5.TIMEFRAME_M1: 500,  # More data for precise M1 analysis
            mt5.TIMEFRAME_M3: 400,
            mt5.TIMEFRAME_M5: 300,
            mt5.TIMEFRAME_M15: 200,
            mt5.TIMEFRAME_M30: 150,
            mt5.TIMEFRAME_H1: 120,
            mt5.TIMEFRAME_H4: 100,
            mt5.TIMEFRAME_D1: 80
        }

        adjusted_n = timeframe_adjustments.get(timeframe, n)

        # Multiple attempts with enhanced validation
        for attempt in range(3):
            try:
                logger(
                    f"📊 Attempt {attempt + 1}: Getting {adjusted_n} precise candles for {valid_symbol}"
                )

                # Get the most recent data
                rates = mt5.copy_rates_from_pos(valid_symbol, timeframe, 0, adjusted_n)

                if rates is not None and len(rates) > 50:
                    df = pd.DataFrame(rates)
                    df['time'] = pd.to_datetime(df['time'], unit='s')

                    # Enhanced data validation and precision correction
                    required_columns = ['open', 'high', 'low', 'close', 'tick_volume']
                    for col in required_columns:
                        if col not in df.columns:
                            logger(f"❌ Missing required column: {col}")
                            return None

                    # Precise price validation and rounding
                    for price_col in ['open', 'high', 'low', 'close']:
                        # Round to symbol's precision
                        df[price_col] = df[price_col].round(digits)

                        # Validate price ranges
                        if df[price_col].isna().any():
                            logger(f"⚠️ Found NaN values in {price_col}, forward filling...")
                            df[price_col] = df[price_col].fillna(method='ffill')

                        # Remove zero or negative prices
                        invalid_prices = (df[price_col] <= 0).sum()
                        if invalid_prices > 0:
                            logger(f"⚠️ Found {invalid_prices} invalid prices in {price_col}")
                            df = df[df[price_col] > 0]

                    # Enhanced OHLC relationship validation
                    invalid_ohlc = 0

                    # Fix high < low
                    high_low_issues = df['high'] < df['low']
                    if high_low_issues.any():
                        invalid_ohlc += high_low_issues.sum()
                        df.loc[high_low_issues, ['high', 'low']] = df.loc[high_low_issues, ['low', 'high']].values
                        logger(f"🔧 Fixed {high_low_issues.sum()} high < low issues")

                    # Ensure close is within high-low range
                    close_above_high = df['close'] > df['high']
                    close_below_low = df['close'] < df['low']

                    if close_above_high.any():
                        invalid_ohlc += close_above_high.sum()
                        df.loc[close_above_high, 'close'] = df.loc[close_above_high, 'high']
                        logger(f"🔧 Fixed {close_above_high.sum()} close > high issues")

                    if close_below_low.any():
                        invalid_ohlc += close_below_low.sum()
                        df.loc[close_below_low, 'close'] = df.loc[close_below_low, 'low']
                        logger(f"🔧 Fixed {close_below_low.sum()} close < low issues")

                    # Ensure open is within high-low range
                    open_above_high = df['open'] > df['high']
                    open_below_low = df['open'] < df['low']

                    if open_above_high.any():
                        invalid_ohlc += open_above_high.sum()
                        df.loc[open_above_high, 'open'] = df.loc[open_above_high, 'high']
                        logger(f"🔧 Fixed {open_above_high.sum()} open > high issues")

                    if open_below_low.any():
                        invalid_ohlc += open_below_low.sum()
                        df.loc[open_below_low, 'open'] = df.loc[open_below_low, 'low']
                        logger(f"🔧 Fixed {open_below_low.sum()} open < low issues")

                    # Create volume column with validation
                    if 'volume' not in df.columns:
                        df['volume'] = df['tick_volume']

                    # Ensure volume is positive
                    df['volume'] = df['volume'].abs()
                    df.loc[df['volume'] == 0, 'volume'] = df['tick_volume']

                    # Sort by time to ensure chronological order
                    df = df.sort_values('time').reset_index(drop=True)

                    # Final validation - remove any remaining invalid rows
                    initial_len = len(df)
                    df = df[
                        (df['open'] > 0) & (df['high'] > 0) &
                        (df['low'] > 0) & (df['close'] > 0) &
                        (df['high'] >= df['low']) &
                        (df['close'] >= df['low']) & (df['close'] <= df['high']) &
                        (df['open'] >= df['low']) & (df['open'] <= df['high'])
                    ]

                    final_len = len(df)
                    if initial_len != final_len:
                        logger(f"🔧 Removed {initial_len - final_len} invalid rows")

                    if len(df) < 50:
                        logger(f"❌ Insufficient valid data after cleaning: {len(df)} rows")
                        continue

                    # Add price precision metadata
                    df.attrs['symbol'] = valid_symbol
                    df.attrs['digits'] = digits
                    df.attrs['point'] = point
                    df.attrs['timeframe'] = timeframe

                    logger(f"✅ Retrieved {len(df)} precise candles for {valid_symbol}")
                    logger(f"📊 Price range: {df['low'].min():.{digits}f} - {df['high'].max():.{digits}f}")

                    return df
                else:
                    logger(f"⚠️ Insufficient raw data (attempt {attempt + 1}): {len(rates) if rates else 0} candles")

            except Exception as e:
                logger(f"⚠️ Data request failed (attempt {attempt + 1}): {str(e)}")

            if attempt < 2:
                time.sleep(2.0)  # Wait between attempts

        logger(f"❌ All data requests failed for {valid_symbol}")
        return None

    except Exception as e:
        logger(f"❌ Critical error getting data for {symbol}: {str(e)}")
        return None


def check_daily_limits() -> bool:
    """
    Advanced risk management with dynamic profit optimization.

    Features:
    - Adaptive drawdown protection
    - Smart profit taking
    - Position size optimization
    - Real-time risk assessment
    """
    try:
        global session_start_balance

        if not session_start_balance:
            return True

        info = get_account_info()
        if not info:
            logger("⚠️ Cannot get account info for advanced risk check")
            return True

        current_equity = info['equity']
        current_balance = info['balance']

        # Advanced drawdown monitoring with adaptive thresholds
        daily_loss = session_start_balance - current_equity
        daily_loss_percent = (daily_loss / session_start_balance) * 100

        # Dynamic risk adjustment based on market conditions
        current_session = get_current_trading_session()
        volatility_multiplier = 1.0

        if current_session:
            volatility = current_session["info"]["volatility"]
            volatility_multiplier = {
                "very_high": 0.7,  # Reduce risk in high volatility
                "high": 0.85,
                "medium": 1.0,
                "low": 1.2  # Allow slightly higher risk in stable conditions
            }.get(volatility, 1.0)

        # Adaptive drawdown limit
        adaptive_max_drawdown = max_drawdown * volatility_multiplier
        logger(f"📊 Adaptive risk: DD limit {adaptive_max_drawdown*100:.1f}% (volatility: {volatility_multiplier})")

        # Smart profit protection - lock in profits progressively
        profit_percent = ((current_equity - session_start_balance) / session_start_balance) * 100

        if profit_percent > 2.0:  # If we're up 2%+, protect 50% of gains
            protective_drawdown = adaptive_max_drawdown * 0.5
            logger(f"💰 Profit protection active: {profit_percent:.1f}% profit, using {protective_drawdown*100:.1f}% protective DD")
            if daily_loss_percent >= (protective_drawdown * 100):
                logger(f"🛡️ Protective stop triggered at {daily_loss_percent:.2f}% drawdown")
                close_all_orders()
                return False

        # Real-time drawdown from peak equity
        max_equity_today = max(session_start_balance, current_equity)
        session_data['max_equity'] = max(
            session_data.get('max_equity', session_start_balance),
            current_equity)
        current_drawdown = (session_data['max_equity'] -
                            current_equity) / session_data['max_equity']

        # Critical drawdown protection
        if current_drawdown >= max_drawdown:
            logger(f"🛑 CRITICAL: Max drawdown reached: {current_drawdown:.2%}")
            logger(
                f"💰 Peak Equity: ${session_data['max_equity']:.2f} → Current: ${current_equity:.2f}"
            )

            # Emergency close all positions
            close_all_orders()

            # Send alert
            if gui and hasattr(gui, 'telegram_var') and gui.telegram_var.get():
                msg = f"🚨 DRAWDOWN ALERT!\nMax DD: {current_drawdown:.2%}\nPeak: ${session_data['max_equity']:.2f}\nCurrent: ${current_equity:.2f}\nAll positions closed!"
                send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, msg)

            return False

        # Daily loss limit
        if daily_loss_percent >= (daily_max_loss * 100):
            logger(f"🛑 Daily max loss reached: {daily_loss_percent:.2f}%")
            return False

        # Profit target check with auto-close option
        daily_profit_percent = ((current_equity - session_start_balance) /
                                session_start_balance) * 100
        if daily_profit_percent >= (profit_target * 100):
            logger(
                f"🎯 Daily profit target reached: {daily_profit_percent:.2f}%")

            # Auto-close positions when target reached
            if gui and hasattr(gui, 'telegram_var') and gui.telegram_var.get():
                msg = f"🎯 PROFIT TARGET ACHIEVED!\nProfit: ${current_equity - session_start_balance:.2f} ({daily_profit_percent:.2f}%)\nClosing all positions..."
                send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, msg)

            close_all_orders()
            return False

        # Margin level protection
        margin_level = info.get('margin_level', 1000)
        if margin_level < 200 and margin_level > 0:
            logger(f"🛑 Low margin level detected: {margin_level:.2f}%")
            logger("🚨 Reducing trading intensity due to margin concerns")

            # Close some positions if margin is very low
            if margin_level < 150:
                positions = get_positions()
                if positions and len(positions) > 1:
                    # Close most losing positions
                    losing_positions = [p for p in positions if p.profit < 0]
                    for pos in losing_positions[:
                                                2]:  # Close up to 2 losing positions
                        close_position_by_ticket(pos.ticket)
                    logger(
                        f"🚨 Emergency: Closed {min(2, len(losing_positions))} losing positions due to low margin"
                    )

        return True

    except Exception as e:
        logger(f"❌ Error in check_daily_limits: {str(e)}")
        return True


def close_position_by_ticket(ticket: int) -> bool:
    """Close specific position by ticket"""
    try:
        position = None
        positions = mt5.positions_get(ticket=ticket)
        if positions:
            position = positions[0]
        else:
            return False

        tick = mt5.symbol_info_tick(position.symbol)
        if tick is None:
            return False

        order_type = mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = tick.bid if position.type == mt5.ORDER_TYPE_BUY else tick.ask

        close_request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": ticket,
            "symbol": position.symbol,
            "volume": position.volume,
            "type": order_type,
            "price": price,
            "deviation": 20,
            "magic": position.magic,
            "comment": "AutoBot_Emergency",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(close_request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            logger(
                f"✅ Position {ticket} closed emergency - Profit: ${position.profit:.2f}"
            )
            return True
        else:
            logger(f"❌ Failed to close position {ticket}")
            return False

    except Exception as e:
        logger(f"❌ Error closing position {ticket}: {str(e)}")
        return False


def auto_recovery_check() -> bool:
    """Advanced auto-recovery system with intelligent error prevention"""
    global mt5_connected, disconnect_count

    try:
        if not mt5_connected:
            logger("🔄 Auto-recovery: Attempting intelligent MT5 reconnection...")

            # Smart recovery strategy
            backoff_delay = min(CONNECTION_RETRY_DELAY * (2**min(disconnect_count, 5)), 60)
            logger(f"⏱️ Using smart backoff delay: {backoff_delay}s")

            # Pre-recovery system checks
            logger("🔍 Pre-recovery diagnostics...")

            # Check system resources
            import psutil
            memory_percent = psutil.virtual_memory().percent
            cpu_percent = psutil.cpu_percent(interval=1)

            if memory_percent > 90:
                logger("⚠️ High memory usage detected, cleaning up...")
                cleanup_resources()

            if cpu_percent > 95:
                logger("⚠️ High CPU usage, waiting for stabilization...")
                time.sleep(5)

            time.sleep(backoff_delay)

            if connect_mt5():
                logger("✅ Auto-recovery: MT5 reconnected successfully!")
                disconnect_count = 0

                if gui and hasattr(gui,
                                   'telegram_var') and gui.telegram_var.get():
                    try:
                        send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
                                      "🔄 Auto-recovery: MT5 reconnected!")
                    except Exception as tg_e:
                        logger(f"⚠️ Telegram notification failed: {str(tg_e)}")

                return True
            else:
                disconnect_count += 1
                logger(f"❌ Auto-recovery failed. Attempt: {disconnect_count}")

                if disconnect_count > MAX_CONSECUTIVE_FAILURES:
                    logger(
                        "🚨 Maximum recovery attempts exceeded. Manual intervention required."
                    )
                    if gui and hasattr(
                            gui, 'telegram_var') and gui.telegram_var.get():
                        try:
                            send_telegram(
                                TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
                                "🚨 Auto-recovery failed multiple times. Manual intervention required."
                            )
                        except Exception as tg_e:
                            logger(
                                f"⚠️ Emergency Telegram notification failed: {str(tg_e)}"
                            )

                return False

        return True

    except ConnectionError as ce:
        logger(f"❌ Connection error during recovery: {str(ce)}")
        return False
    except Exception as e:
        logger(f"❌ Unexpected auto-recovery error: {str(e)}")
        return False


# Logger function moved to top of file - no duplicate needed here


def send_telegram(token: str, chat_id: str, message: str) -> bool:
    """Enhanced Telegram messaging with specific error handling"""
    if not token or not chat_id:
        logger("⚠️ Telegram credentials missing")
        return False

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": message[:4096]
        }  # Telegram message limit
        response = requests.post(url,
                                 data=data,
                                 timeout=DEFAULT_TIMEOUT_SECONDS)

        if response.status_code == 200:
            return True
        elif response.status_code == 429:
            logger(f"⚠️ Telegram rate limited: {response.status_code}")
            return False
        else:
            logger(f"⚠️ Telegram send failed: {response.status_code}")
            return False

    except requests.exceptions.Timeout:
        logger("❌ Telegram timeout error")
        return False
    except requests.exceptions.ConnectionError:
        logger("❌ Telegram connection error")
        return False
    except requests.exceptions.RequestException as e:
        logger(f"❌ Telegram request error: {str(e)}")
        return False
    except Exception as e:
        logger(f"❌ Unexpected Telegram error: {str(e)}")
        return False


def get_current_trading_session() -> Optional[Dict[str, Any]]:
    """Get current active trading session with accurate overnight handling"""
    try:
        from datetime import time as dt_time

        now = datetime.datetime.now().time()
        current_hour = datetime.datetime.now().hour
        logger(f"🔍 DEBUG: current_hour = {current_hour}")

        # Define precise session times using time objects
        asia_start = dt_time(21, 0)
        asia_end = dt_time(6, 0)
        london_start = dt_time(7, 0)
        london_end = dt_time(15, 0)
        newyork_start = dt_time(15, 0)
        newyork_end = dt_time(21, 0)

        session_name = "Unknown"
        session_info = None
        volatility = "unknown"

        # Fixed priority order - prevent Asia dominance
        if london_start <= now < london_end:
            session_name = "London"
            session_info = TRADING_SESSIONS["London"]
            volatility = "high"
            logger(f"🌍 London session ACTIVE ({london_start.strftime('%H:%M')}-{london_end.strftime('%H:%M')})")
        elif newyork_start <= now < newyork_end:
            session_name = "New_York"
            session_info = TRADING_SESSIONS["New_York"]
            volatility = "high"
            logger(f"🌍 New York session ACTIVE ({newyork_start.strftime('%H:%M')}-{newyork_end.strftime('%H:%M')})")
        elif (now >= asia_start) or (now < asia_end):  # Overnight session logic
            session_name = "Asia"
            session_info = TRADING_SESSIONS["Asia"]
            volatility = "medium"
            logger(f"🌏 Asia session ACTIVE (overnight: {asia_start.strftime('%H:%M')}-{asia_end.strftime('%H:%M')})")
        else:
            session_name = "Overlap"
            volatility = "very_high"
            logger("🌐 Overlap/Transition period detected")
            # Return default for overlap periods
            return {
                "name": "24/7",
                "info": {
                    "volatility": "medium",
                    "preferred_pairs": ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]
                },
                "time_in_session": 0.5
            }

        # Calculate time progress for valid sessions
        time_progress = 0.5
        if session_name == "Asia":
            # Special overnight calculation
            if current_hour >= 21:
                elapsed = current_hour - 21
                total_hours = (24 - 21) + 6
            else:
                elapsed = (24 - 21) + current_hour
                total_hours = (24 - 21) + 6
            time_progress = min(elapsed / total_hours, 1.0) if total_hours > 0 else 0.0
        elif session_name == "London":
            time_progress = (current_hour - 7) / (15 - 7)
        elif session_name == "New_York":
            time_progress = (current_hour - 15) / (21 - 15)

        best_session = {
            "name": session_name,
            "info": session_info,
            "time_in_session": time_progress
        }

        logger(f"🕐 Current time: {now.strftime('%H:%M')} (Local)")
        logger(f"✅ PRIMARY SESSION: {session_name} - {volatility} volatility")

        return best_session

    except Exception as e:
        logger(f"❌ Error getting trading session: {str(e)}")
        # Return default session on error
        return {
            "name": "Default",
            "info": {
                "volatility": "medium",
                "preferred_pairs": ["EURUSD", "GBPUSD", "USDJPY"]
            },
            "time_in_session": 0.5
        }


def calculate_session_time_progress(current_hour: int, start_hour: int,
                                    end_hour: int) -> float:
    """Calculate how far into the session we are (0.0 to 1.0)"""
    try:
        if start_hour > end_hour:  # Overnight session
            total_hours = (24 - start_hour) + end_hour
            if current_hour >= start_hour:
                elapsed = current_hour - start_hour
            else:
                elapsed = (24 - start_hour) + current_hour
        else:
            total_hours = end_hour - start_hour
            elapsed = current_hour - start_hour

        return min(elapsed / total_hours, 1.0) if total_hours > 0 else 0.0
    except:
        return 0.5


def get_session_priority(volatility: str) -> int:
    """Get session priority based on volatility"""
    priority_map = {"very_high": 4, "high": 3, "medium": 2, "low": 1}
    return priority_map.get(volatility, 1)


def get_session_optimal_symbols(session_name: str) -> List[str]:
    """Get optimal symbols for current trading session"""
    try:
        if session_name in TRADING_SESSIONS:
            return TRADING_SESSIONS[session_name]["preferred_pairs"]
        return ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]
    except:
        return ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]


def adjust_strategy_for_session(
        strategy: str, session_info: Optional[Dict]) -> Dict[str, Any]:
    """Adjust trading strategy parameters based on current session"""
    try:
        base_adjustments = {
            "lot_multiplier": 1.0,
            "tp_multiplier": 1.0,
            "sl_multiplier": 1.0,
            "signal_threshold_modifier": 0,
            "max_spread_multiplier": 1.0
        }

        if not session_info:
            return base_adjustments

        session_name = session_info["name"]
        volatility = session_info["info"]["volatility"]
        session_settings = SESSION_SETTINGS.get(session_name, {})

        # Adjust based on volatility
        if volatility == "very_high":
            base_adjustments.update({
                "lot_multiplier": 1.2,
                "tp_multiplier": 1.3,
                "sl_multiplier": 0.8,
                "signal_threshold_modifier": -1,  # More aggressive
                "max_spread_multiplier": 0.8
            })
        elif volatility == "high":
            base_adjustments.update({
                "lot_multiplier": 1.1,
                "tp_multiplier": 1.2,
                "sl_multiplier": 0.9,
                "signal_threshold_modifier": 0,
                "max_spread_multiplier": 1.0
            })
        elif volatility == "medium":
            base_adjustments.update({
                "lot_multiplier": 0.9,
                "tp_multiplier": 1.0,
                "sl_multiplier": 1.1,
                "signal_threshold_modifier": 1,  # More conservative
                "max_spread_multiplier": 1.2
            })
        else:  # low volatility
            base_adjustments.update({
                "lot_multiplier": 0.8,
                "tp_multiplier": 0.9,
                "sl_multiplier": 1.2,
                "signal_threshold_modifier": 2,  # Very conservative
                "max_spread_multiplier": 1.5
            })

        # Strategy-specific adjustments
        if strategy == "HFT":
            base_adjustments[
                "signal_threshold_modifier"] -= 1  # More aggressive for HFT
        elif strategy == "Intraday":
            base_adjustments[
                "tp_multiplier"] *= 1.2  # Larger targets for intraday

        logger(f"📊 Session adjustments for {session_name}: {base_adjustments}")
        return base_adjustments

    except Exception as e:
        logger(f"❌ Error adjusting strategy for session: {str(e)}")
        return {
            "lot_multiplier": 1.0,
            "tp_multiplier": 1.0,
            "sl_multiplier": 1.0,
            "signal_threshold_modifier": 0,
            "max_spread_multiplier": 1.0
        }


def check_trading_time() -> bool:
    """Enhanced 24/7 trading time check with session awareness"""
    try:
        # Always allow trading - 24/7 mode
        current_session = get_current_trading_session()

        if current_session:
            session_name = current_session['name']
            volatility = current_session['info']['volatility']
            logger(
                f"✅ Trading ENABLED in {session_name} session ({volatility} volatility)"
            )
        else:
            logger("✅ Trading ENABLED - 24/7 mode active")

        return True  # Always allow trading

    except Exception as e:
        logger(f"❌ Error in check_trading_time: {str(e)}")
        return True  # Always default to allowing trading


def risk_management_check() -> bool:
    """Enhanced risk management"""
    try:
        global loss_streak, session_start_balance

        info = get_account_info()
        if not info or not session_start_balance:
            return True

        current_drawdown = (session_start_balance -
                            info['equity']) / session_start_balance
        if current_drawdown >= max_drawdown:
            logger(f"🛑 Max drawdown reached: {current_drawdown:.2%}")
            return False

        if not check_daily_limits():
            return False

        if loss_streak >= max_loss_streak:
            logger(f"🛑 Max loss streak reached: {loss_streak}")
            return False

        if info['margin_level'] < 300 and info['margin_level'] > 0:
            logger(f"🛑 Low margin level: {info['margin_level']:.2f}%")
            return False

        return True
    except Exception as e:
        logger(f"❌ Risk management error: {str(e)}")
        return True


def check_profit_targets() -> bool:
    """Enhanced profit target checking"""
    try:
        global session_start_balance

        info = get_account_info()
        if not info or not session_start_balance:
            return True

        current_equity = info['equity']
        session_profit = current_equity - session_start_balance
        profit_percent = (session_profit / session_start_balance) * 100

        target_percent = float(gui.profit_target_entry.get()) if gui else 5.0
        if profit_percent >= target_percent:
            logger(f"🎯 Profit target reached ({profit_percent:.2f}%)")
            close_all_orders()

            if gui and hasattr(gui, 'telegram_var') and gui.telegram_var.get():
                msg = f"🎯 PROFIT TARGET REACHED!\nProfit: ${current_equity - session_start_balance:.2f} ({profit_percent:.2f}%)\nClosing all positions..."
                send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, msg)

            return False

        return True

    except Exception as e:
        logger(f"❌ Error checking profit targets: {str(e)}")
        return True


def ai_market_analysis(symbol: str, df: pd.DataFrame) -> Dict[str, Any]:
    """Advanced AI-powered market analysis with multiple confirmation signals"""
    try:
        if len(df) < 50:
            return {"confidence": 0, "signals": [], "recommendation": "WAIT", "strength": "WEAK"}

        last = df.iloc[-1]
        prev = df.iloc[-2]
        analysis = {
            "confidence": 0,
            "signals": [],
            "recommendation": "WAIT",
            "strength": "WEAK",
            "market_structure": "UNKNOWN",
            "volatility_regime": "NORMAL",
            "trend_strength": 0.0
        }

        # Multi-timeframe trend analysis
        trend_signals = 0
        if last['EMA20'] > last['EMA50'] > last['EMA200']:
            trend_signals += 3
            analysis["signals"].append("🟢 STRONG UPTREND: EMA alignment bullish")
            analysis["market_structure"] = "BULLISH"
        elif last['EMA20'] < last['EMA50'] < last['EMA200']:
            trend_signals -= 3
            analysis["signals"].append("🔴 STRONG DOWNTREND: EMA alignment bearish")
            analysis["market_structure"] = "BEARISH"
        else:
            analysis["signals"].append("🟡 SIDEWAYS: Mixed EMA signals")
            analysis["market_structure"] = "SIDEWAYS"

        # Volatility regime detection
        atr_ratio = last['ATR_Ratio'] if 'ATR_Ratio' in last else 1.0
        if atr_ratio > 1.5:
            analysis["volatility_regime"] = "HIGH"
            analysis["signals"].append(f"⚡ HIGH VOLATILITY: ATR ratio {atr_ratio:.2f}")
        elif atr_ratio < 0.7:
            analysis["volatility_regime"] = "LOW"
            analysis["signals"].append(f"😴 LOW VOLATILITY: ATR ratio {atr_ratio:.2f}")

        # Advanced momentum analysis
        momentum_score = 0
        if last['MACD'] > last['MACD_signal'] and last['MACD_histogram'] > prev['MACD_histogram']:
            momentum_score += 2
            analysis["signals"].append("🚀 BULLISH MOMENTUM: MACD trending up")
        elif last['MACD'] < last['MACD_signal'] and last['MACD_histogram'] < prev['MACD_histogram']:
            momentum_score -= 2
            analysis["signals"].append("📉 BEARISH MOMENTUM: MACD trending down")

        # RSI divergence detection
        if last['RSI'] < 30 and last['close'] > prev['close']:
            momentum_score += 2
            analysis["signals"].append("💎 BULLISH DIVERGENCE: RSI oversold with price rise")
        elif last['RSI'] > 70 and last['close'] < prev['close']:
            momentum_score -= 2
            analysis["signals"].append("🔻 BEARISH DIVERGENCE: RSI overbought with price fall")

        # Volume confirmation (if available)
        if 'volume' in df.columns:
            vol_avg = df['volume'].rolling(20).mean().iloc[-1]
            if last['volume'] > vol_avg * 1.5:
                momentum_score += 1
                analysis["signals"].append("📊 HIGH VOLUME CONFIRMATION")

        # Support/Resistance analysis
        resistance = df['high'].rolling(20).max().iloc[-1]
        support = df['low'].rolling(20).min().iloc[-1]

        if last['close'] > resistance * 0.998:
            momentum_score += 2
            analysis["signals"].append("💥 RESISTANCE BREAKOUT")
        elif last['close'] < support * 1.002:
            momentum_score -= 2
            analysis["signals"].append("💔 SUPPORT BREAKDOWN")

        # Calculate overall confidence
        total_signals = abs(trend_signals) + abs(momentum_score)
        analysis["confidence"] = min(100, max(0, total_signals * 10))
        analysis["trend_strength"] = abs(trend_signals + momentum_score) / 10.0

        # Final recommendation with AI logic
        if trend_signals >= 2 and momentum_score >= 2 and analysis["confidence"] >= 60:
            analysis["recommendation"] = "STRONG_BUY"
            analysis["strength"] = "STRONG"
        elif trend_signals >= 1 and momentum_score >= 1 and analysis["confidence"] >= 40:
            analysis["recommendation"] = "BUY"
            analysis["strength"] = "MODERATE"
        elif trend_signals <= -2 and momentum_score <= -2 and analysis["confidence"] >= 60:
            analysis["recommendation"] = "STRONG_SELL"
            analysis["strength"] = "STRONG"
        elif trend_signals <= -1 and momentum_score <= -1 and analysis["confidence"] >= 40:
            analysis["recommendation"] = "SELL"
            analysis["strength"] = "MODERATE"
        else:
            analysis["recommendation"] = "WAIT"
            analysis["strength"] = "WEAK"

        return analysis

    except Exception as e:
        logger(f"❌ AI analysis error: {str(e)}")
        return {"confidence": 0, "signals": [f"Error: {str(e)}"], "recommendation": "WAIT", "strength": "WEAK"}


def generate_performance_report() -> str:
    """Generate comprehensive performance report"""
    try:
        info = get_account_info()
        if not info or not session_start_balance:
            return "📊 Performance Report: No data available"

        current_equity = info['equity']
        total_profit = current_equity - session_start_balance
        profit_percent = (total_profit / session_start_balance) * 100

        total_trades = session_data.get('total_trades', 0)
        winning_trades = session_data.get('winning_trades', 0)
        losing_trades = session_data.get('losing_trades', 0)

        win_rate = (winning_trades / max(total_trades, 1)) * 100

        # Calculate session duration
        start_time = session_data.get('start_time', datetime.datetime.now())
        duration = datetime.datetime.now() - start_time
        duration_hours = duration.total_seconds() / 3600

        report = f"""
📊 TRADING PERFORMANCE REPORT
═══════════════════════════════
⏰ Session Duration: {duration_hours:.1f} hours
💰 Starting Balance: ${session_start_balance:.2f}
📈 Current Equity: ${current_equity:.2f}
💵 Total P/L: ${total_profit:.2f} ({profit_percent:+.2f}%)

📈 TRADING STATISTICS:
• Total Trades: {total_trades}
• Winning Trades: {winning_trades}
• Losing Trades: {losing_trades}
• Win Rate: {win_rate:.1f}%
• Avg P/L per Hour: ${total_profit/max(duration_hours, 1):.2f}

🚀 CURRENT STATUS:
• Strategy: {current_strategy}
• Open Positions: {len(get_positions())}
• Max Drawdown: {max_drawdown*100:.1f}%
• Current Session: {get_current_trading_session()['name'] if get_current_trading_session() else 'Default'}

🚀 Bot Performance: {'EXCELLENT' if profit_percent > 2 else 'MODERATE' if profit_percent > 0 else 'NEEDS REVIEW'}
═══════════════════════════════
        """
        return report.strip()

    except Exception as e:
        return f"📊 Performance Report Error: {str(e)}"


def send_hourly_report() -> None:
    """Send hourly performance report"""
    try:
        if gui and hasattr(gui, 'telegram_var') and gui.telegram_var.get():
            report = generate_performance_report()
            send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
                          f"📊 HOURLY REPORT\n{report}")
            logger("📊 Hourly report sent to Telegram")
    except Exception as e:
        logger(f"❌ Error sending hourly report: {str(e)}")


def bot_thread() -> None:
    """Enhanced main bot trading thread with auto-recovery and performance monitoring"""
    global bot_running, disconnect_count, session_start_balance, loss_streak, current_strategy, position_count, mt5_connected

    try:
        logger("🚀 Starting enhanced trading bot thread...")

        # Ensure MT5 connection
        connection_attempts = 0
        max_attempts = 5

        while connection_attempts < max_attempts and not mt5_connected:
            logger(
                f"🔄 Bot connection attempt {connection_attempts + 1}/{max_attempts}"
            )
            if connect_mt5():
                logger("✅ Bot connected to MT5 successfully!")
                break
            else:
                connection_attempts += 1
                if connection_attempts < max_attempts:
                    time.sleep(5)

        if not mt5_connected:
            logger("❌ Bot failed to connect to MT5 after all attempts")
            bot_running = False
            if gui:
                gui.bot_status_lbl.config(text="Bot: Connection Failed 🔴",
                                          foreground="red")
            return

        # Initialize session
        info = get_account_info()
        if info:
            session_start_balance = info['balance']
            session_data['start_time'] = datetime.datetime.now()
            session_data['start_balance'] = session_start_balance
            logger(
                f"🚀 Trading session initialized. Balance: ${session_start_balance:.2f}"
            )

            # Get current strategy from GUI at start
            if gui:
                current_strategy = gui.strategy_combo.get()
                logger(f"📈 Selected strategy: {current_strategy}")

            if gui and hasattr(gui, 'telegram_var') and gui.telegram_var.get():
                msg = f"🤖 AutoBot Started\nBalance: ${session_start_balance:.2f}\nStrategy: {current_strategy}"
                send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, msg)

        # Enhanced symbol selection with session optimization
        trading_symbol = "EURUSD"  # Default fallback

        # Check current session and get optimal symbols
        current_session = get_current_trading_session()
        optimal_symbols = []

        if current_session:
            optimal_symbols = get_session_optimal_symbols(
                current_session["name"])
            logger(
                f"🌍 {current_session['name']} session optimal symbols: {', '.join(optimal_symbols[:5])}"
            )

        # Priority: User selection > Session optimal > Default
        if gui and gui.symbol_entry.get():
            user_symbol = gui.symbol_entry.get().strip().upper()

            # Special handling for gold symbols
            if "XAU" in user_symbol or "GOLD" in user_symbol:
                detected_gold = detect_gold_symbol()
                if detected_gold:
                    trading_symbol = detected_gold
                    logger(f"🎯 Auto-detected gold symbol: {trading_symbol}")
                    if gui:
                        gui.symbol_var.set(trading_symbol)
                else:
                    logger(f"⚠️ Cannot detect gold symbol, trying manual validation...")
                    if validate_and_activate_symbol(user_symbol):
                        trading_symbol = user_symbol
                        logger(f"🎯 Using user-selected symbol: {trading_symbol}")
                    else:
                        logger(f"❌ Invalid gold symbol {user_symbol}, using fallback")
            elif validate_and_activate_symbol(user_symbol):
                trading_symbol = user_symbol
                logger(f"🎯 Using user-selected symbol: {trading_symbol}")
            else:
                # Try session optimal symbols if user symbol fails
                for symbol in optimal_symbols:
                    if validate_and_activate_symbol(symbol):
                        trading_symbol = symbol
                        logger(
                            f"🎯 User symbol failed, using session optimal: {trading_symbol}"
                        )
                        if gui:
                            gui.symbol_var.set(trading_symbol)
                        break
                else:
                    logger(
                        f"❌ Invalid symbol {user_symbol}, using fallback: {trading_symbol}"
                    )
                    if gui:
                        gui.symbol_var.set(trading_symbol)
        else:
            # No user selection, use session optimal
            for symbol in optimal_symbols:
                if validate_and_activate_symbol(symbol):
                    trading_symbol = symbol
                    logger(f"🎯 Using session optimal symbol: {trading_symbol}")
                    if gui:
                        gui.symbol_var.set(trading_symbol)
                    break

        # Get timeframe
        timeframe_map = {
            "M1": mt5.TIMEFRAME_M1,
            "M3": mt5.TIMEFRAME_M3,
            "M5": mt5.TIMEFRAME_M5,
            "M10": mt5.TIMEFRAME_M10,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1
        }
        timeframe = timeframe_map.get(
            gui.timeframe_combo.get() if gui else "M1", mt5.TIMEFRAME_M1)

        logger(
            f"📊 Bot configuration: {trading_symbol} | {gui.timeframe_combo.get() if gui else 'M1'} | Strategy: {current_strategy}"
        )
        logger(
            "🎯 Enhanced auto-trading active - executing orders on valid signals!"
        )

        # Main trading loop
        last_candle_time = None
        consecutive_failures = 0
        max_failures = 10
        signal_check_counter = 0

        while bot_running:
            try:
                # Check MT5 connection
                if not check_mt5_status():
                    disconnect_count += 1
                    logger(f"⚠️ MT5 disconnected (count: {disconnect_count})")

                    if disconnect_count > 3:
                        logger(
                            "🛑 Too many disconnections. Attempting reconnect..."
                        )
                        if connect_mt5():
                            disconnect_count = 0
                            logger("✅ Reconnected successfully!")
                        else:
                            logger("🛑 Reconnection failed. Stopping bot.")
                            break
                    time.sleep(5)
                    continue
                else:
                    disconnect_count = 0

                # Update current strategy from GUI every loop and ensure GUI connection
                if gui and hasattr(gui, 'strategy_combo'):
                    try:
                        new_strategy = gui.strategy_combo.get()
                        if new_strategy != current_strategy:
                            current_strategy = new_strategy
                            logger(
                                f"🔄 Strategy updated from GUI to: {current_strategy}"
                            )
                    except Exception as e:
                        logger(f"⚠️ GUI connection issue: {str(e)}")
                        # Fallback to default strategy if GUI not accessible
                        if not current_strategy:
                            current_strategy = "Scalping"

                # Risk management checks
                if not risk_management_check():
                    logger("🛑 Risk management stop triggered")
                    break

                if not check_profit_targets():
                    logger("🎯 Profit target reached. Stopping bot.")
                    break

                if not check_trading_time():
                    time.sleep(60)
                    continue

                # Get market data with more aggressive refresh
                df = get_symbol_data(trading_symbol, timeframe)
                if df is None or len(df) < 50:
                    consecutive_failures += 1
                    if consecutive_failures >= max_failures:
                        logger(
                            f"🛑 Too many data failures for {trading_symbol}")
                        break
                    logger("⚠️ Insufficient market data, retrying...")
                    time.sleep(3)  # Reduced from 5 to 3 seconds
                    continue
                else:
                    consecutive_failures = 0

                # Check for new candle - more aggressive signal checking
                current_candle_time = df.iloc[-1]['time']
                is_new_candle = last_candle_time is None or current_candle_time != last_candle_time

                # More aggressive signal checking based on strategy
                signal_check_counter += 1

                # HFT needs much faster checking
                if current_strategy == "HFT":
                    force_check = signal_check_counter >= 1  # Check every 1 second for HFT
                elif current_strategy == "Scalping":
                    force_check = signal_check_counter >= 2  # Check every 2 seconds for Scalping
                else:
                    force_check = signal_check_counter >= 3  # Check every 3 seconds for others

                if not is_new_candle and not force_check:
                    # Shorter sleep for HFT
                    sleep_interval = BOT_LOOP_INTERVALS.get(current_strategy, 2.0)
                    time.sleep(sleep_interval)
                    continue

                if force_check:
                    signal_check_counter = 0

                last_candle_time = current_candle_time

                # Calculate indicators
                df = calculate_indicators(df)

                # Perform AI market analysis before strategy execution
                ai_analysis = ai_market_analysis(trading_symbol, df)
                logger(f"🤖 AI Market Analysis Results:")
                logger(f"   📊 Recommendation: {ai_analysis['recommendation']}")
                logger(f"   🎯 Confidence: {ai_analysis['confidence']}%")
                logger(f"   📈 Market Structure: {ai_analysis['market_structure']}")
                logger(f"   ⚡ Volatility Regime: {ai_analysis['volatility_regime']}")

                for signal in ai_analysis['signals'][:3]:  # Show top 3 AI signals
                    logger(f"   {signal}")

                # Run strategy with current strategy from GUI
                logger(
                    f"🎯 Analyzing {current_strategy} signals for {trading_symbol}..."
                )
                action, signals = run_strategy(current_strategy, df,
                                               trading_symbol)

                # AI Override: If AI has very high confidence, consider it
                if ai_analysis['confidence'] >= 80:
                    if ai_analysis['recommendation'] == 'STRONG_BUY' and not action:
                        action = 'BUY'
                        signals.append("🤖 AI OVERRIDE: High confidence BUY signal")
                        logger("🤖 AI OVERRIDE: Activating BUY based on high AI confidence")
                    elif ai_analysis['recommendation'] == 'STRONG_SELL' and not action:
                        action = 'SELL'
                        signals.append("🤖 AI OVERRIDE: High confidence SELL signal")
                        logger("🤖 AI OVERRIDE: Activating SELL based on high AI confidence")

                # Update position count
                positions = get_positions()
                position_count = len(positions)

                # --- Enhanced Signal Accuracy with Multi-Confirmation System ---
                signal_strength_score = 0
                confirmation_count = 0

                # Calculate overall signal strength score
                for signal in signals:
                    if any(keyword in signal for keyword in ["✅", "STRONG", "HIGH"]):
                        signal_strength_score += 2
                        confirmation_count += 1
                    elif any(keyword in signal for keyword in ["🔧", "DEBUG", "basic"]):
                        signal_strength_score += 0.5
                    else:
                        signal_strength_score += 1

                # Multi-confirmation requirement based on strategy
                min_confirmations = {
                    "Scalping": 2,  # Need at least 2 strong confirmations
                    "HFT": 1,       # Fastest execution
                    "Intraday": 3,  # More conservative
                    "Arbitrage": 2  # Mean reversion needs confirmation
                }

                required_confirmations = min_confirmations.get(current_strategy, 2)

                # UNIFIED CONFIRMATION SYSTEM - Fix threshold inconsistencies
                if action:
                    # Use the SAME threshold for both signal generation and confirmation
                    actual_signal_strength = max(buy_signals, sell_signals)
                    meets_threshold = actual_signal_strength >= threshold

                    # Additional confirmation for quality
                    quality_signals = sum(1 for s in signals if any(keyword in s for keyword in ["✅", "STRONG", "AI-", "🤖"]))
                    has_quality = quality_signals >= 1 or ai_analysis['confidence'] > 50

                    if meets_threshold and has_quality:
                        logger(f"✅ SIGNAL APPROVED: Strength {actual_signal_strength}/{threshold}, Quality signals: {quality_signals}")
                        logger(f"📊 AI Confidence: {ai_analysis['confidence']}%, Market: {ai_analysis['market_structure']}")
                    elif meets_threshold:
                        logger(f"⚠️ SIGNAL APPROVED (Basic): Strength {actual_signal_strength}/{threshold}, Low quality")
                    else:
                        logger(f"❌ SIGNAL REJECTED: Strength {actual_signal_strength}/{threshold} insufficient")
                        action = None

                logger(
                    f"📊 Final Signal Analysis: Action={action}, Strength={max(buy_signals, sell_signals)}/{threshold}, Quality={quality_signals if 'quality_signals' in locals() else 0}, Positions={position_count}/{max_positions}"
                )
                # --- End of Enhanced Signal Accuracy ---


                # Log all signals for debugging
                if signals:
                    logger(
                        f"🎯 All detected signals:"
                    )
                    for i, signal in enumerate(signals):
                        logger(f"   {i+1}. {signal}")
                else:
                    logger("⚠️ No signals detected this cycle")

                # AGGRESSIVE OPPORTUNITY MODE - Don't miss trading chances
                if not action and len(signals) > 0:
                    # Count signal types
                    buy_signal_count = sum(1 for s in signals if any(word in s.lower() for word in ["buy", "bullish", "up", "long"]))
                    sell_signal_count = sum(1 for s in signals if any(word in s.lower() for word in ["sell", "bearish", "down", "short"]))

                    logger(f"🎯 OPPORTUNITY EVALUATION: BUY signals={buy_signal_count}, SELL signals={sell_signal_count}")

                    # Force action if we have clear directional bias
                    if buy_signal_count > sell_signal_count and buy_signal_count >= 1:
                        action = "BUY"
                        logger(f"🎯 OPPORTUNITY: Forcing BUY based on {buy_signal_count} directional signals")
                    elif sell_signal_count > buy_signal_count and sell_signal_count >= 1:
                        action = "SELL"
                        logger(f"🎯 OPPORTUNITY: Forcing SELL based on {sell_signal_count} directional signals")

                    # Additional opportunity check - if no trades today, be more aggressive
                    recent_trades = session_data.get('total_trades', 0)
                    if not action and recent_trades == 0 and len(signals) >= 1:
                        # Take any direction if no trades yet
                        if any("opportunity" in s.lower() for s in signals):
                            if current_price > last_close:
                                action = "BUY"
                                logger("🎯 FIRST TRADE OPPORTUNITY: Taking BUY on upward movement")
                            else:
                                action = "SELL"
                                logger("🎯 FIRST TRADE OPPORTUNITY: Taking SELL on downward movement")

                # Execute trading signals with proper GUI parameter integration
                if action and position_count < max_positions:
                    logger(
                        f"🚀 EXECUTING {action} ORDER for {trading_symbol} using {current_strategy} strategy"
                    )
                    logger(f"📊 Strategy signals detected: {len(signals)}")

                    # Get ALL parameters from GUI with proper validation
                    lot_size = gui.get_current_lot() if gui else 0.01
                    tp_value = gui.get_current_tp() if gui else "20"
                    sl_value = gui.get_current_sl() if gui else "10"
                    tp_unit = gui.get_current_tp_unit() if gui else "pips"
                    sl_unit = gui.get_current_sl_unit() if gui else "pips"

                    # Log the exact parameters being used
                    logger(f"📋 Using GUI parameters:")
                    logger(f"   Strategy: {current_strategy}")
                    logger(f"   Lot: {lot_size}")
                    logger(f"   TP: {tp_value} {tp_unit}")
                    logger(f"   SL: {sl_value} {sl_unit}")

                    # Execute order with exact GUI parameters
                    result = open_order(trading_symbol, lot_size, action,
                                        sl_value, tp_value, sl_unit, tp_unit)

                    if result and getattr(result, 'retcode',
                                          None) == mt5.TRADE_RETCODE_DONE:
                        logger(
                            f"✅ {action} order executed successfully with {current_strategy}! Ticket: {result.order}"
                        )
                        consecutive_failures = 0

                        session_data['total_trades'] += 1
                        session_data['daily_orders'] += 1

                        if gui and hasattr(
                                gui,
                                'telegram_var') and gui.telegram_var.get():
                            msg = f"🚀 {action} Order Executed!\nSymbol: {trading_symbol}\nStrategy: {current_strategy}\nTicket: {result.order}\nTP: {tp_value} {tp_unit}\nSL: {sl_value} {sl_unit}"
                            send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
                                          msg)
                    else:
                        consecutive_failures += 1
                        logger(
                            f"❌ Order execution failed. Failure count: {consecutive_failures}"
                        )

                elif action and position_count >= max_positions:
                    logger(
                        f"⚠️ Max positions reached ({position_count}). Skipping {action} signal from {current_strategy}."
                    )

                # Log periodic status for debugging
                # --- Enhanced Performance Monitoring with Real-time Metrics ---
                if time.time() % 30 < 3:  # Every 30 seconds instead of 60
                    try:
                        current_price = df['close'].iloc[-1]
                        session_info = get_current_trading_session()
                        session_name = session_info["name"] if session_info else "Default"
                        volatility = session_info["info"]["volatility"] if session_info else "unknown"

                        # Enhanced performance metrics
                        account_info = get_account_info()
                        if account_info and session_start_balance:
                            equity = account_info['equity']
                            daily_pnl = equity - session_start_balance
                            daily_pnl_percent = (daily_pnl / session_start_balance) * 100

                            # Calculate win rate
                            total_trades_stat = session_data.get('winning_trades', 0) + session_data.get('losing_trades', 0)
                            win_rate = (session_data.get('winning_trades', 0) / max(total_trades_stat, 1)) * 100

                            logger(
                                f"💹 Enhanced Status: {trading_symbol}@{current_price:.5f} | {current_strategy} | {session_name}({volatility})"
                            )
                            logger(
                                f"📊 Performance: P/L ${daily_pnl:+.2f} ({daily_pnl_percent:+.2f}%) | WR {win_rate:.1f}% | Pos {position_count}/{max_positions}"
                            )
                        else:
                            logger(
                                f"💹 Status: {trading_symbol}@{current_price:.5f} | {current_strategy} | {session_name}({volatility}) | Pos:{position_count}/{max_positions}"
                            )
                    except Exception as status_e:
                        logger(f"⚠️ Status logging error: {str(status_e)}")
                        pass
                # --- End of Enhanced Performance Monitoring ---

                # Enhanced monitoring and auto-recovery checks
                if signal_check_counter % 100 == 0:  # Every 100 cycles
                    auto_recovery_check()

                # Hourly performance report
                if signal_check_counter % 3600 == 0:  # Approximately every hour
                    send_hourly_report()

                # Strategy-specific sleep intervals using configuration
                sleep_interval = BOT_LOOP_INTERVALS.get(current_strategy, 2.0)
                time.sleep(sleep_interval)

            except Exception as e:
                logger(f"❌ Bot loop error: {str(e)}")
                consecutive_failures += 1

                # Auto-recovery attempt
                if auto_recovery_check():
                    consecutive_failures = 0
                    logger(
                        "✅ Auto-recovery successful, continuing trading..."
                    )

                if consecutive_failures >= max_failures:
                    logger("🛑 Too many consecutive errors. Stopping bot.")
                    break
                time.sleep(3)

    except Exception as e:
        logger(f"❌ Bot thread error: {str(e)}")

        # Final recovery attempt
        if gui and hasattr(gui, 'telegram_var') and gui.telegram_var.get():
            send_telegram(
                TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
                f"🚨 Bot thread crashed: {str(e)}\nAttempting restart...")

    finally:
        bot_running = False
        logger("🛑 Bot thread stopped")
        if gui:
            gui.bot_status_lbl.config(text="Bot: Stopped 🔴",
                                      foreground="red")


def start_auto_recovery_monitor():
    """Background monitoring thread for auto-recovery"""

    def recovery_monitor():
        while True:
            try:
                if bot_running:
                    auto_recovery_check()
                time.sleep(30)  # Check every 30 seconds
            except Exception as e:
                logger(f"❌ Recovery monitor error: {str(e)}")
                time.sleep(60)

    recovery_thread = threading.Thread(target=recovery_monitor, daemon=True)
    recovery_thread.start()
    logger("🔄 Auto-recovery monitor started")


class TradingBotGUI:

    def __init__(self, root):
        self.root = root
        self.root.title(
            "💹 MT5 ADVANCED AUTO TRADING BOT v4.0 - Premium Edition")
        self.root.geometry("1400x900")
        self.root.configure(bg="#0f0f0f")
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)

        self.current_strategy = "Scalping"

        self.create_widgets()

        # Initialize GUI states
        self.start_btn.config(state="disabled")
        self.close_btn.config(state="disabled")
        self.emergency_btn.config(state="normal")

        # Auto-connect on startup
        self.root.after(1000, self.auto_connect_mt5)

        # Start GUI updates
        self.root.after(2000, self.update_gui_data)

        # Start auto-recovery monitoring
        start_auto_recovery_monitor()

    def auto_connect_mt5(self):
        """Enhanced auto-connection on startup with better error handling"""
        try:
            self.log("🔄 Starting auto-connection to MetaTrader 5...")
            self.log(
                "💡 PASTIKAN: MT5 sudah dijalankan dan login ke akun trading")
            self.log("💡 PENTING: MT5 harus dijalankan sebagai Administrator")
            self.status_lbl.config(text="Status: Connecting... 🔄",
                                   foreground="orange")
            self.root.update()

            # Show system info first
            import platform
            import sys
            self.log(
                f"🔍 Python: {sys.version.split()[0]} ({platform.architecture()[0]})"
            )
            self.log(f"🔍 Platform: {platform.system()} {platform.release()}")

            if connect_mt5():
                self.log("🎉 SUCCESS: Auto-connected to MetaTrader 5!")
                self.status_lbl.config(text="Status: Connected ✅",
                                       foreground="green")
                self.update_symbols()
                self.start_btn.config(state="normal")
                self.close_btn.config(state="normal")
                self.connect_btn.config(state="disabled")

                # Show detailed connection info
                try:
                    info = get_account_info()
                    if info:
                        self.log(
                            f"👤 Account: {info.get('login', 'N/A')} | Server: {info.get('server', 'N/A')}"
                        )
                        self.log(
                            f"💰 Balance: ${info.get('balance', 0):.2f} | Equity: ${info.get('equity', 0):.2f}"
                        )
                        self.log(
                            f"🔐 Trade Permission: {'✅' if info.get('balance', 0) > 0 else '⚠️'}"
                        )

                        # Update global session balance
                        global session_start_balance
                        session_start_balance = info.get('balance', 0)

                        self.log(
                            "🚀 GUI-MT5 connection established successfully!")
                        self.log("🚀 Ready to start automated trading!")
                except Exception as info_e:
                    self.log(
                        f"⚠️ Error getting account details: {str(info_e)}")

            else:
                self.log("❌ FAILED: Auto-connection to MT5 failed")
                self.log("🔧 TROUBLESHOOTING WAJIB:")
                self.log("   1. 🔴 TUTUP MT5 SEPENUHNYA")
                self.log("   2. 🔴 KLIK KANAN MT5 → 'Run as Administrator'")
                self.log(
                    "   3. 🔴 LOGIN ke akun trading dengan kredensial yang benar"
                )
                self.log("   4. 🔴 PASTIKAN status 'Connected' muncul di MT5")
                self.log(
                    "   5. 🔴 BUKA Market Watch dan tambahkan symbols (EURUSD, dll)"
                )
                self.log("   6. 🔴 PASTIKAN Python dan MT5 sama-sama 64-bit")
                self.log("   7. 🔴 DISABLE antivirus sementara jika perlu")
                self.log("   8. 🔴 RESTART komputer jika masalah persisten")

                self.status_lbl.config(text="Status: Connection Failed ❌",
                                       foreground="red")

                # Enable manual connect button and keep trying
                self.connect_btn.config(state="normal")
                self.start_btn.config(state="disabled")
                self.close_btn.config(state="disabled")

                # Show error in account labels
                self.balance_lbl.config(text="Balance: N/A", foreground="gray")
                self.equity_lbl.config(text="Equity: N/A", foreground="gray")
                self.margin_lbl.config(text="Free Margin: N/A",
                                       foreground="gray")
                self.margin_level_lbl.config(text="Margin Level: N/A",
                                             foreground="gray")
                self.server_lbl.config(text="Server: N/A")

        except Exception as e:
            error_msg = f"❌ CRITICAL: Auto-connection error: {str(e)}"
            self.log(error_msg)
            self.status_lbl.config(text="Status: Critical Error ❌",
                                   foreground="red")

    def create_widgets(self):
        """Enhanced GUI creation with better layout"""
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#0f0f0f")
        style.configure("TLabel",
                        background="#0f0f0f",
                        foreground="white",
                        font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 10, "bold"))
        style.configure("TNotebook.Tab",
                        background="#2e2e2e",
                        foreground="white")
        style.configure("Accent.TButton",
                        foreground="white",
                        background="#4CAF50")

        # Main notebook
        tab_control = ttk.Notebook(self.root)
        tab_control.grid(row=0, column=0, sticky="nsew")

        # Create tabs
        self.dashboard_tab = ttk.Frame(tab_control)
        self.strategy_tab = ttk.Frame(tab_control)
        self.calculator_tab = ttk.Frame(tab_control)
        self.log_tab = ttk.Frame(tab_control)

        tab_control.add(self.dashboard_tab, text="📊 Dashboard")
        tab_control.add(self.strategy_tab, text="⚙️ Strategy Setup")
        tab_control.add(self.calculator_tab, text="🧮 Calculator")
        tab_control.add(self.log_tab, text="📝 Logs")

        # Build tab contents
        self.dashboard_tab.rowconfigure(3, weight=1)
        self.dashboard_tab.columnconfigure(0, weight=1)
        self.build_dashboard()
        self.build_strategy_tab()
        self.build_calculator_tab()
        self.build_log_tab()

    def build_dashboard(self):
        """Enhanced dashboard with better layout"""
        # Control Panel
        ctrl_frame = ttk.LabelFrame(self.dashboard_tab,
                                    text="🎛️ Control Panel")
        ctrl_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        # Row 1: Symbol and Timeframe
        ttk.Label(ctrl_frame, text="Symbol:").grid(row=0,
                                                   column=0,
                                                   padx=5,
                                                   pady=5,
                                                   sticky="w")
        self.symbol_var = tk.StringVar(value="EURUSD")
        self.symbol_entry = ttk.Combobox(ctrl_frame,
                                         textvariable=self.symbol_var,
                                         width=12)
        self.symbol_entry.bind('<Return>', self.on_symbol_validate)
        self.symbol_entry.grid(row=0, column=1, padx=5, pady=5)

        self.validate_symbol_btn = ttk.Button(ctrl_frame,
                                              text="✓",
                                              command=self.validate_symbol,
                                              width=3)
        self.validate_symbol_btn.grid(row=0, column=2, padx=2, pady=5)

        ttk.Label(ctrl_frame, text="Timeframe:").grid(row=0,
                                                      column=3,
                                                      padx=5,
                                                      pady=5,
                                                      sticky="w")
        self.timeframe_combo = ttk.Combobox(
            ctrl_frame, values=["M1", "M5", "M15", "M30", "H1", "H4"], width=8)
        self.timeframe_combo.set("M1")
        self.timeframe_combo.grid(row=0, column=4, padx=5, pady=5)

        ttk.Label(ctrl_frame, text="Strategy:").grid(row=0,
                                                     column=5,
                                                     padx=5,
                                                     pady=5,
                                                     sticky="w")
        self.strategy_combo = ttk.Combobox(
            ctrl_frame,
            values=["Scalping", "Intraday", "HFT", "Arbitrage"],
            width=10)
        self.strategy_combo.set("Scalping")
        self.strategy_combo.bind("<<ComboboxSelected>>",
                                 self.on_strategy_change)
        self.strategy_combo.grid(row=0, column=6, padx=5, pady=5)

        # Row 2: Connection and Control Buttons
        self.connect_btn = ttk.Button(ctrl_frame,
                                      text="🔌 Connect MT5",
                                      command=self.connect_mt5)
        self.connect_btn.grid(row=1,
                              column=0,
                              columnspan=2,
                              padx=5,
                              pady=5,
                              sticky="ew")

        self.start_btn = ttk.Button(ctrl_frame,
                                    text="🚀 START BOT",
                                    command=self.start_bot,
                                    style="Accent.TButton")
        self.start_btn.grid(row=1,
                            column=2,
                            columnspan=2,
                            padx=5,
                            pady=5,
                            sticky="ew")

        self.stop_btn = ttk.Button(ctrl_frame,
                                   text="⏹️ STOP BOT",
                                   command=self.stop_bot)
        self.stop_btn.grid(row=1, column=4, padx=5, pady=5, sticky="ew")

        self.close_btn = ttk.Button(ctrl_frame,
                                    text="❌ CLOSE ALL",
                                    command=self.close_all)
        self.close_btn.grid(row=1, column=5, padx=5, pady=5, sticky="ew")

        self.emergency_btn = ttk.Button(ctrl_frame,
                                        text="🚨 EMERGENCY",
                                        command=self.emergency_stop)
        self.emergency_btn.grid(row=1, column=6, padx=5, pady=5, sticky="ew")

        # Account Information
        acc_frame = ttk.LabelFrame(self.dashboard_tab,
                                   text="💰 Account Information")
        acc_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")

        self.balance_lbl = ttk.Label(acc_frame,
                                     text="Balance: $0.00",
                                     font=("Segoe UI", 11, "bold"))
        self.equity_lbl = ttk.Label(acc_frame,
                                    text="Equity: $0.00",
                                    font=("Segoe UI", 11))
        self.margin_lbl = ttk.Label(acc_frame,
                                    text="Free Margin: $0.00",
                                    font=("Segoe UI", 11))
        self.margin_level_lbl = ttk.Label(acc_frame,
                                          text="Margin Level: 0%",
                                          font=("Segoe UI", 11))
        self.status_lbl = ttk.Label(acc_frame,
                                    text="Status: Disconnected",
                                    font=("Segoe UI", 11, "bold"))
        self.server_lbl = ttk.Label(acc_frame,
                                    text="Server: N/A",
                                    font=("Segoe UI", 10))

        self.balance_lbl.grid(row=0, column=0, padx=10, pady=5, sticky="w")
        self.equity_lbl.grid(row=0, column=1, padx=10, pady=5, sticky="w")
        self.margin_lbl.grid(row=0, column=2, padx=10, pady=5, sticky="w")
        self.margin_level_lbl.grid(row=1,
                                   column=0,
                                   padx=10,
                                   pady=5,
                                   sticky="w")
        self.status_lbl.grid(row=1, column=1, padx=10, pady=5, sticky="w")
        self.server_lbl.grid(row=1, column=2, padx=10, pady=5, sticky="w")

        # Trading Statistics with Session Info
        stats_frame = ttk.LabelFrame(self.dashboard_tab,
                                     text="📈 Trading Statistics")
        stats_frame.grid(row=2, column=0, padx=10, pady=5, sticky="ew")

        self.daily_orders_lbl = ttk.Label(stats_frame, text="Daily Orders: 0")
        self.daily_profit_lbl = ttk.Label(stats_frame,
                                          text="Daily Profit: $0.00")
        self.win_rate_lbl = ttk.Label(stats_frame, text="Win Rate: 0%")
        self.open_positions_lbl = ttk.Label(stats_frame,
                                            text="Open Positions: 0")
        self.session_lbl = ttk.Label(stats_frame,
                                     text="Session: Loading...",
                                     font=("Segoe UI", 10, "bold"))
        self.bot_status_lbl = ttk.Label(stats_frame,
                                        text="Bot: Stopped 🔴",
                                        font=("Segoe UI", 10, "bold"))

        self.daily_orders_lbl.grid(row=0,
                                   column=0,
                                   padx=10,
                                   pady=5,
                                   sticky="w")
        self.daily_profit_lbl.grid(row=0,
                                   column=1,
                                   padx=10,
                                   pady=5,
                                   sticky="w")
        self.win_rate_lbl.grid(row=0, column=2, padx=10, pady=5, sticky="w")
        self.open_positions_lbl.grid(row=0,
                                     column=3,
                                     padx=10,
                                     pady=5,
                                     sticky="w")
        self.session_lbl.grid(row=1,
                              column=0,
                              columnspan=2,
                              padx=10,
                              pady=5,
                              sticky="w")
        self.bot_status_lbl.grid(row=1,
                                 column=2,
                                 columnspan=2,
                                 padx=10,
                                 pady=5,
                                 sticky="w")

        # Active Positions
        pos_frame = ttk.LabelFrame(self.dashboard_tab,
                                   text="📋 Active Positions")
        pos_frame.grid(row=3, column=0, padx=10, pady=10, sticky="nsew")

        columns = ("Ticket", "Symbol", "Type", "Lot", "Price", "Current",
                   "Profit", "Pips")
        self.pos_tree = ttk.Treeview(pos_frame,
                                     columns=columns,
                                     show="headings",
                                     height=15)

        for col in columns:
            self.pos_tree.heading(col, text=col)
            self.pos_tree.column(col, anchor="center", width=100)

        pos_scrollbar = ttk.Scrollbar(pos_frame,
                                      orient="vertical",
                                      command=self.pos_tree.yview)
        self.pos_tree.configure(yscrollcommand=pos_scrollbar.set)

        self.pos_tree.pack(side="left", fill="both", expand=True)
        pos_scrollbar.pack(side="right", fill="y")

    def build_strategy_tab(self):
        """Enhanced strategy configuration tab"""
        self.strategy_tab.columnconfigure((0, 1), weight=1)

        strategies = ["Scalping", "Intraday", "HFT", "Arbitrage"]
        self.strategy_params = {}

        for i, strat in enumerate(strategies):
            frame = ttk.LabelFrame(self.strategy_tab,
                                   text=f"🎯 {strat} Strategy")
            frame.grid(row=i // 2,
                       column=i % 2,
                       padx=10,
                       pady=10,
                       sticky="nsew")

            defaults = {
                "Scalping": {
                    "lot": "0.01",
                    "tp": "15",
                    "sl": "8"
                },  # Scalping: Quick 10-15 pip profits
                "Intraday": {
                    "lot": "0.02",
                    "tp": "80",
                    "sl": "40"
                },  # Intraday: Larger moves 60-100 pips
                "HFT": {
                    "lot": "0.005",  # Smaller lots for ultra-fast trading
                    "tp": "2",       # Very small targets 1-3 pips
                    "sl": "1"        # Very tight stops 0.5-1 pips
                },  # HFT: Micro-movements with high frequency
                "Arbitrage": {
                    "lot": "0.02",
                    "tp": "20",      # Mean reversion targets
                    "sl": "15"       # Slightly wider stops for reversion
                }  # Arbitrage: Statistical mean reversion
            }

            ttk.Label(frame, text="Lot Size:").grid(row=0,
                                                    column=0,
                                                    padx=5,
                                                    pady=5,
                                                    sticky="w")
            lot_entry = ttk.Entry(frame, width=15)
            lot_entry.insert(0, defaults[strat]["lot"])
            lot_entry.grid(row=0, column=1, padx=5, pady=5)

            ttk.Label(frame, text="TP:").grid(row=1,
                                              column=0,
                                              padx=5,
                                              pady=5,
                                              sticky="w")
            tp_entry = ttk.Entry(frame, width=10)
            tp_entry.insert(0, defaults[strat]["tp"])
            tp_entry.grid(row=1, column=1, padx=5, pady=5)

            tp_unit_combo = ttk.Combobox(frame,
                                         values=["pips", "price", "%", "currency", "USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "NZD"],
                                         width=10)
            tp_unit_combo.set("pips")
            tp_unit_combo.grid(row=1, column=2, padx=5, pady=5)

            ttk.Label(frame, text="SL:").grid(row=2,
                                              column=0,
                                              padx=5,
                                              pady=5,
                                              sticky="w")
            sl_entry = ttk.Entry(frame, width=10)
            sl_entry.insert(0, defaults[strat]["sl"])
            sl_entry.grid(row=2, column=1, padx=5, pady=5)

            sl_unit_combo = ttk.Combobox(frame,
                                         values=["pips", "price", "%", "currency", "USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "NZD"],
                                         width=10)
            sl_unit_combo.set("pips")
            sl_unit_combo.grid(row=2, column=2, padx=5, pady=5)

            self.strategy_params[strat] = {
                "lot": lot_entry,
                "tp": tp_entry,
                "sl": sl_entry,
                "tp_unit": tp_unit_combo,
                "sl_unit": sl_unit_combo
            }

        # Global Settings
        settings_frame = ttk.LabelFrame(self.strategy_tab,
                                        text="⚙️ Global Settings")
        settings_frame.grid(row=2,
                            column=0,
                            columnspan=2,
                            padx=10,
                            pady=10,
                            sticky="ew")

        ttk.Label(settings_frame, text="Max Positions:").grid(row=0,
                                                              column=0,
                                                              padx=5,
                                                              pady=5,
                                                              sticky="w")
        self.max_pos_entry = ttk.Entry(settings_frame, width=15)
        self.max_pos_entry.insert(0, "5")
        self.max_pos_entry.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(settings_frame, text="Max Drawdown (%):").grid(row=0,
                                                                 column=2,
                                                                 padx=5,
                                                                 pady=5,
                                                                 sticky="w")
        self.max_dd_entry = ttk.Entry(settings_frame, width=15)
        self.max_dd_entry.insert(0, "3")
        self.max_dd_entry.grid(row=0, column=3, padx=5, pady=5)

        ttk.Label(settings_frame, text="Profit Target (%):").grid(row=1,
                                                                  column=0,
                                                                  padx=5,
                                                                  pady=5,
                                                                  sticky="w")
        self.profit_target_entry = ttk.Entry(settings_frame, width=15)
        self.profit_target_entry.insert(0, "5")
        self.profit_target_entry.grid(row=1, column=1, padx=5, pady=5)

        self.telegram_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(settings_frame,
                        text="📱 Telegram Notifications",
                        variable=self.telegram_var).grid(row=1,
                                                         column=2,
                                                         columnspan=2,
                                                         padx=5,
                                                         pady=5,
                                                         sticky="w")

        # Enhanced Risk Management Section
        risk_frame = ttk.LabelFrame(self.strategy_tab,
                                    text="⚠️ Advanced Risk Management")
        risk_frame.grid(row=3,
                        column=0,
                        columnspan=2,
                        padx=10,
                        pady=10,
                        sticky="ew")

        ttk.Label(risk_frame, text="Auto Lot Sizing:").grid(row=0,
                                                            column=0,
                                                            padx=5,
                                                            pady=5,
                                                            sticky="w")
        self.auto_lot_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(risk_frame, text="Enable",
                        variable=self.auto_lot_var).grid(row=0,
                                                         column=1,
                                                         padx=5,
                                                         pady=5,
                                                         sticky="w")

        ttk.Label(risk_frame, text="Risk % per Trade:").grid(row=0,
                                                             column=2,
                                                             padx=5,
                                                             pady=5,
                                                             sticky="w")
        self.risk_percent_entry = ttk.Entry(risk_frame, width=10)
        self.risk_percent_entry.insert(0, "1.0")
        self.risk_percent_entry.grid(row=0, column=3, padx=5, pady=5)

        ttk.Label(risk_frame, text="Emergency Close DD:").grid(row=1,
                                                               column=0,
                                                               padx=5,
                                                               pady=5,
                                                               sticky="w")
        self.emergency_dd_entry = ttk.Entry(risk_frame, width=10)
        self.emergency_dd_entry.insert(0, "5.0")
        self.emergency_dd_entry.grid(row=1, column=1, padx=5, pady=5)

        # Performance tracking
        perf_frame = ttk.LabelFrame(self.strategy_tab,
                                    text="📊 Performance Tracking")
        perf_frame.grid(row=4,
                        column=0,
                        columnspan=2,
                        padx=10,
                        pady=10,
                        sticky="ew")

        self.auto_report_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(perf_frame,
                        text="📱 Hourly Reports",
                        variable=self.auto_report_var).grid(row=0,
                                                            column=0,
                                                            padx=5,
                                                            pady=5,
                                                            sticky="w")

        ttk.Button(perf_frame,
                   text="📊 Generate Report",
                   command=self.generate_report_now).grid(row=0,
                                                          column=1,
                                                          padx=5,
                                                          pady=5)

        ttk.Button(perf_frame,
                   text="🔄 Recovery Test",
                   command=self.test_recovery).grid(row=0,
                                                    column=2,
                                                    padx=5,
                                                    pady=5)

    def build_calculator_tab(self):
        """Enhanced calculator tab"""
        calc_frame = ttk.LabelFrame(self.calculator_tab,
                                    text="🧮 TP/SL Calculator")
        calc_frame.pack(fill="both", expand=True, padx=10, pady=10)
        # ...existing code...
        # ...existing code...
        # Input section
        input_frame = ttk.Frame(calc_frame)
        input_frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(input_frame, text="Symbol:").grid(row=0,
                                                    column=0,
                                                    padx=5,
                                                    pady=5,
                                                    sticky="w")
        self.calc_symbol_entry = ttk.Entry(input_frame, width=15)
        self.calc_symbol_entry.insert(0, "EURUSD")
        self.calc_symbol_entry.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(input_frame, text="Lot Size:").grid(row=0,
                                                      column=2,
                                                      padx=5,
                                                      pady=5,
                                                      sticky="w")
        self.calc_lot_entry = ttk.Entry(input_frame, width=15)
        self.calc_lot_entry.insert(0, "0.01")
        self.calc_lot_entry.grid(row=0, column=3, padx=5, pady=5)

        ttk.Label(input_frame, text="TP:").grid(row=1,
                                                column=0,
                                                padx=5,
                                                pady=5,
                                                sticky="w")
        self.calc_tp_entry = ttk.Entry(input_frame, width=10)
        self.calc_tp_entry.grid(row=1, column=1, padx=5, pady=5)

        self.calc_tp_unit = ttk.Combobox(input_frame,
                                         values=["pips", "price", "%", "currency", "USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "NZD"],
                                         width=10)
        self.calc_tp_unit.set("pips")
        self.calc_tp_unit.grid(row=1, column=2, padx=5, pady=5)

        ttk.Label(input_frame, text="SL:").grid(row=1,
                                                column=3,
                                                padx=5,
                                                pady=5,
                                                sticky="w")
        self.calc_sl_entry = ttk.Entry(input_frame, width=10)
        self.calc_sl_entry.grid(row=1, column=4, padx=5, pady=5)

        self.calc_sl_unit = ttk.Combobox(input_frame,
                                         values=["pips", "price", "%", "currency", "USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "NZD"],
                                         width=10)
        self.calc_sl_unit.set("pips")
        self.calc_sl_unit.grid(row=1, column=5, padx=5, pady=5)

        calc_btn = ttk.Button(input_frame,
                              text="🧮 Calculate",
                              command=self.calculate_tp_sl)
        calc_btn.grid(row=2, column=1, columnspan=2, padx=5, pady=10)

        # Results
        self.calc_results = ScrolledText(calc_frame,
                                         height=20,
                                         bg="#0a0a0a",
                                         fg="#00ff00",
                                         font=("Courier", 11))
        self.calc_results.pack(fill="both", expand=True, padx=10, pady=10)

    def build_log_tab(self):
        """Enhanced log tab"""
        log_ctrl_frame = ttk.Frame(self.log_tab)
        log_ctrl_frame.pack(fill="x", padx=10, pady=5)

        ttk.Button(log_ctrl_frame,
                   text="💾 Export Logs",
                   command=self.export_logs).pack(side="left", padx=5)
        ttk.Button(log_ctrl_frame,
                   text="🗑️ Clear Logs",
                   command=self.clear_logs).pack(side="left", padx=5)

        self.log_area = ScrolledText(self.log_tab,
                                     height=40,
                                     bg="#0a0a0a",
                                     fg="#00ff00",
                                     font=("Consolas", 10))
        self.log_area.pack(fill="both", expand=True, padx=10, pady=10)

    def log(self, text):
        """Enhanced logging with timestamp"""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        full_text = f"[{timestamp}] {text}"
        self.log_area.insert(tk.END, full_text + "\n")
        self.log_area.see(tk.END)
        self.root.update_idletasks()

    def connect_mt5(self):
        """Enhanced MT5 connection with comprehensive GUI feedback and proper error handling"""
        try:
            self.log("🔄 Manual connection attempt to MetaTrader 5...")
            self.status_lbl.config(text="Status: Connecting... 🔄", foreground="orange")
            self.root.update()

            # Enhanced connection attempt with detailed logging
            self.log("🔍 Checking MT5 installation and permissions...")

            # Force update connection status before attempting
            global mt5_connected
            mt5_connected = False

            if connect_mt5():
                self.log("✅ Successfully connected to MetaTrader 5!")
                self.status_lbl.config(text="Status: Connected ✅", foreground="green")

                # Update symbols and enable buttons
                self.log("🔄 Loading available symbols...")
                self.update_symbols()

                self.start_btn.config(state="normal")
                self.close_btn.config(state="normal")
                self.connect_btn.config(state="disabled")

                # Get detailed account info with error handling
                self.log("🔄 Retrieving account information...")
                info = get_account_info()
                if info:
                    # Update all account labels immediately
                    self.balance_lbl.config(text=f"Balance: ${info['balance']:,.2f}")
                    self.equity_lbl.config(text=f"Equity: ${info['equity']:,.2f}")
                    self.margin_lbl.config(text=f"Free Margin: ${info['free_margin']:,.2f}")

                    # Calculate and display margin level
                    margin_level = info.get('margin_level', 0)
                    if margin_level > 0:
                        margin_color = "green" if margin_level > 300 else "orange" if margin_level > 150 else "red"
                        self.margin_level_lbl.config(text=f"Margin Level: {margin_level:.2f}%", foreground=margin_color)
                    else:
                        self.margin_level_lbl.config(text="Margin Level: ∞%", foreground="green")

                    self.server_lbl.config(text=f"Server: {info['server']} | Login: {info['login']}")

                    self.log(
                        f"✅ Account Details:")
                    self.log(
                        f"   👤 Login: {info['login']}")
                    self.log(
                        f"   🌐 Server: {info['server']}")
                    self.log(
                        f"   💰 Balance: ${info['balance']:,.2f}")
                    self.log(
                        f"   📈 Equity: ${info['equity']:,.2f}")
                    self.log(
                        f"   💵 Free Margin: ${info['free_margin']:,.2f}")
                    self.log(
                        f"   📊 Margin Level: {margin_level:.2f}%")

                    global session_start_balance
                    session_start_balance = info['balance']
                    session_data['start_balance'] = info['balance']

                    self.log("🚀 GUI-MT5 connection established successfully!")
                    self.log("🚀 Ready to start automated trading!")

                else:
                    # Error getting account info
                    self.balance_lbl.config(text="Balance: Error", foreground="red")
                    self.equity_lbl.config(text="Equity: Error", foreground="red")
                    self.margin_lbl.config(text="Free Margin: Error", foreground="red")
                    self.margin_level_lbl.config(text="Margin Level: Error", foreground="red")
                    logger("⚠️ Connected to MT5 but cannot get account info")
                    logger("💡 Check if MT5 is properly logged in to trading account")
                    # Keep connection enabled but warn user
                    self.start_btn.config(state="normal")
                    self.close_btn.config(state="normal")

            else:
                self.log("❌ Failed to connect to MetaTrader 5")
                self.log("🔧 TROUBLESHOOTING CHECKLIST:")
                self.log("   1. ✅ MT5 is running and logged in")
                self.log("   2. ✅ MT5 is running as Administrator")
                self.log("   3. ✅ Account has trading permissions")
                self.log("   4. ✅ No firewall blocking the connection")
                self.log("   5. ✅ Python and MT5 are both 64-bit")

                self.status_lbl.config(text="Status: Connection Failed ❌", foreground="red")
                self.start_btn.config(state="disabled")
                self.close_btn.config(state="disabled")
                self.connect_btn.config(state="normal")

                # Reset account labels
                self.balance_lbl.config(text="Balance: N/A", foreground="gray")
                self.equity_lbl.config(text="Equity: N/A", foreground="gray")
                self.margin_lbl.config(text="Free Margin: N/A", foreground="gray")
                self.margin_level_lbl.config(text="Margin Level: N/A", foreground="gray")
                self.server_lbl.config(text="Server: N/A")

        except Exception as e:
            error_msg = f"❌ Critical connection error: {str(e)}"
            self.log(error_msg)
            self.status_lbl.config(text="Status: Critical Error ❌", foreground="red")

            # Reset everything on error
            self.start_btn.config(state="disabled")
            self.close_btn.config(state="disabled")
            self.connect_btn.config(state="normal")

            # Show error in account labels
            self.balance_lbl.config(text="Balance: Error", foreground="red")
            self.equity_lbl.config(text="Equity: Error", foreground="red")
            self.margin_lbl.config(text="Free Margin: Error", foreground="red")
            self.margin_level_lbl.config(text="Margin Level: Error", foreground="red")
            self.server_lbl.config(text="Server: Connection Error")

    def start_bot(self):
        """Enhanced bot starting with better validation"""
        global bot_running, current_strategy, max_positions, max_drawdown, daily_max_loss, profit_target

        if bot_running:
            self.log("⚠️ Bot is already running!")
            return

        try:
            # Validate connection
            if not check_mt5_status():
                messagebox.showerror("❌ Error", "Please connect to MT5 first!")
                return

            # Validate symbol
            symbol = self.symbol_var.get().strip().upper()
            if not symbol:
                messagebox.showerror("❌ Error",
                                     "Please enter a trading symbol!")
                return

            self.log(f"🔍 Validating symbol: {symbol}")

            if not validate_and_activate_symbol(symbol):
                messagebox.showerror("❌ Error",
                                     f"Symbol {symbol} is not valid!")
                return

            self.log(f"✅ Symbol {symbol} validated successfully!")

            # Update global settings
            current_strategy = self.strategy_combo.get()
            max_positions = int(self.max_pos_entry.get())
            max_drawdown = float(self.max_dd_entry.get()) / 100
            profit_target = float(self.profit_target_entry.get()) / 100

            bot_running = True

            # Start bot thread
            threading.Thread(target=bot_thread, daemon=True).start()
            self.log(f"🚀 Enhanced trading bot started for {symbol}!")
            self.bot_status_lbl.config(text="Bot: Running 🟢",
                                       foreground="green")

            # Update button states
            self.start_btn.config(state="disabled")
            self.stop_btn.config(state="normal")

        except ValueError as e:
            messagebox.showerror("❌ Error", f"Invalid input values: {str(e)}")
        except Exception as e:
            self.log(f"❌ Error starting bot: {str(e)}")
            messagebox.showerror("❌ Error", f"Failed to start bot: {str(e)}")

    def stop_bot(self):
        """Enhanced bot stopping"""
        global bot_running
        bot_running = False
        self.log("⏹️ Stopping trading bot...")
        self.bot_status_lbl.config(text="Bot: Stopping... 🟡",
                                   foreground="orange")
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")

    def emergency_stop(self):
        """Enhanced emergency stop"""
        global bot_running
        try:
            bot_running = False
            close_all_orders()
            self.log("🚨 EMERGENCY STOP ACTIVATED - All positions closed!")
            self.bot_status_lbl.config(text="Bot: Emergency Stop 🔴",
                                       foreground="red")

            if gui and hasattr(gui, 'telegram_var') and gui.telegram_var.get():
                send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
                              "🚨 EMERGENCY STOP - All positions closed!")
        except Exception as e:
            self.log(f"❌ Emergency stop error: {str(e)}")

    def close_all(self):
        """Enhanced close all positions"""
        try:
            close_all_orders()
            self.log("❌ All positions closed manually")
        except Exception as e:
            self.log(f"❌ Error closing positions: {str(e)}")

    def on_strategy_change(self, event=None):
        """Handle strategy change with proper GUI integration"""
        global current_strategy
        new_strategy = self.strategy_combo.get()

        if new_strategy != current_strategy:
            current_strategy = new_strategy
            self.log(
                f"🔄 Strategy changed from {current_strategy} to: {new_strategy}")

            # Update current_strategy global
            current_strategy = new_strategy

            # Log current strategy parameters
            try:
                lot = self.get_current_lot()
                tp = self.get_current_tp()
                sl = self.get_current_sl()
                tp_unit = self.get_current_tp_unit()
                sl_unit = self.get_current_sl_unit()

                self.log(
                    f"📊 {new_strategy} params: Lot={lot}, TP={tp} {tp_unit}, SL={sl} {sl_unit}"
                )
            except Exception as e:
                self.log(f"❌ Error logging strategy params: {str(e)}")

    def get_current_lot(self):
        """Get current lot size from GUI with validation"""
        try:
            strategy = self.strategy_combo.get()
            lot_str = self.strategy_params[strategy]["lot"].get()
            return validate_numeric_input(lot_str, min_val=0.01, max_val=100.0)
        except (KeyError, ValueError) as e:
            logger(f"⚠️ Invalid lot size input: {str(e)}")
            return 0.01
        except Exception as e:
            logger(f"❌ Unexpected error getting lot size: {str(e)}")
            return 0.01

    def get_current_tp(self):
        """Get current TP from GUI with validation"""
        try:
            strategy = self.strategy_combo.get()
            tp_str = self.strategy_params[strategy]["tp"].get()
            if not tp_str or tp_str.strip() == "":
                return "20"
            validate_numeric_input(
                tp_str, min_val=0.0)  # Validate but return as string
            return tp_str
        except (KeyError, ValueError) as e:
            logger(f"⚠️ Invalid TP input: {str(e)}")
            return "20"
        except Exception as e:
            logger(f"❌ Unexpected error getting TP: {str(e)}")
            return "20"

    def get_current_sl(self):
        """Get current SL from GUI with validation"""
        try:
            strategy = self.strategy_combo.get()
            sl_str = self.strategy_params[strategy]["sl"].get()
            if not sl_str or sl_str.strip() == "":
                return "10"
            validate_numeric_input(
                sl_str, min_val=0.0)  # Validate but return as string
            return sl_str
        except (KeyError, ValueError) as e:
            logger(f"⚠️ Invalid SL input: {str(e)}")
            return "10"
        except Exception as e:
            logger(f"❌ Unexpected error getting SL: {str(e)}")
            return "10"

    def get_current_tp_unit(self):
        """Get current TP unit from selected strategy"""
        try:
            strategy = self.strategy_combo.get()
            if strategy in self.strategy_params:
                unit = self.strategy_params[strategy]["tp_unit"].get()
                logger(f"🔍 GUI: TP unit for {strategy} = {unit}")
                return unit
            else:
                logger(
                    f"⚠️ GUI: Strategy {strategy} not found in params, using default"
                )
                return "pips"
        except Exception as e:
            logger(f"❌ GUI: Error getting TP unit: {str(e)}")
            return "pips"

    def get_current_sl_unit(self):
        """Get current SL unit from selected strategy"""
        try:
            strategy = self.strategy_combo.get()
            if strategy in self.strategy_params:
                unit = self.strategy_params[strategy]["sl_unit"].get()
                logger(f"🔍 GUI: SL unit for {strategy} = {unit}")
                return unit
            else:
                logger(
                    f"⚠️ GUI: Strategy {strategy} not found in params, using default"
                )
                return "pips"
        except Exception as e:
            logger(f"❌ GUI: Error getting SL unit: {str(e)}")
            return "pips"

    def update_symbols(self):
        """Enhanced symbol updating"""
        try:
            symbols = get_symbol_suggestions()
            if symbols:
                self.symbol_entry['values'] = symbols
                self.log(f"📊 Loaded {len(symbols)} symbols")
            else:
                self.symbol_entry['values'] = [
                    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"
                ]
        except Exception as e:
            self.log(f"❌ Error updating symbols: {str(e)}")

    def validate_symbol(self):
        """Enhanced symbol validation"""
        try:
            symbol = self.symbol_var.get().strip().upper()
            if not symbol:
                messagebox.showwarning("⚠️ Warning",
                                       "Please enter a symbol first!")
                return

            self.log(f"🔍 Validating symbol: {symbol}")

            if not check_mt5_status():
                messagebox.showerror("❌ Error", "Please connect to MT5 first!")
                return

            valid_symbol = validate_and_activate_symbol(symbol)
            if valid_symbol:
                self.symbol_var.set(valid_symbol)
                # dst...
                self.log(f"✅ Symbol {valid_symbol} validated successfully!")
                messagebox.showinfo("✅ Success",
                                    f"Symbol {valid_symbol} is valid!")
                self.validate_symbol_btn.config(text="✅")
            else:
                self.log(f"❌ Symbol {symbol} validation failed!")
                messagebox.showerror("❌ Error",
                                     f"Symbol {symbol} is not valid!")
                self.validate_symbol_btn.config(text="❌")

        except Exception as e:
            self.log(f"❌ Error validating symbol: {str(e)}")

    def on_symbol_validate(self, event=None):
        """Auto-validate on symbol entry"""
        try:
            symbol = self.symbol_var.get().strip().upper()
            if symbol and len(symbol) >= 4:
                self.root.after(500, lambda: self.auto_validate_symbol(symbol))
        except:
            pass

    def auto_validate_symbol(self, symbol):
        """Background symbol validation"""
        try:
            if check_mt5_status() and validate_and_activate_symbol(symbol):
                self.validate_symbol_btn.config(text="✅")
            else:
                self.validate_symbol_btn.config(text="❌")
        except:
            self.validate_symbol_btn.config(text="?")

    def calculate_tp_sl(self):
        """Enhanced TP/SL calculation"""
        try:
            symbol = self.calc_symbol_entry.get()
            lot = float(self.calc_lot_entry.get())
            tp_input = self.calc_tp_entry.get()
            sl_input = self.calc_sl_entry.get()
            tp_unit = self.calc_tp_unit.get()
            sl_unit = self.calc_sl_unit.get()

            if not check_mt5_status():
                self.calc_results.delete(1.0, tk.END)
                self.calc_results.insert(tk.END,
                                         "❌ Please connect to MT5 first!\n")
                return

            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                self.calc_results.delete(1.0, tk.END)
                self.calc_results.insert(
                    tk.END, f"❌ Cannot get price for {symbol}!\n")
                return

            current_price = tick.ask
            pip_value = calculate_pip_value(symbol, lot)

            # Calculate TP values
            tp_price = 0.0
            tp_profit = 0.0
            if tp_input:
                tp_price, tp_profit_calc = parse_tp_sl_input(
                    tp_input, tp_unit, symbol, lot, current_price, "BUY", True)
                tp_profit = tp_profit_calc.get('amount', 0)

            # Calculate SL values
            sl_price = 0.0
            sl_loss = 0.0
            if sl_input:
                sl_price, sl_loss_calc = parse_tp_sl_input(
                    sl_input, sl_unit, symbol, lot, current_price, "BUY",
                    False)
                sl_loss = sl_loss_calc.get('amount', 0)

            result_text = f"""
🧮 TP/SL CALCULATION RESULTS
===============================
Symbol: {symbol}
Lot Size: {lot}
Current Price: {current_price:.5f}

TAKE PROFIT:
- Input: {tp_input} {tp_unit}
- Price Level: {tp_price:.5f}
- Expected Profit: ${tp_profit:.2f}

STOP LOSS:
- Input: {sl_input} {sl_unit}
- Price Level: {sl_price:.5f}
- Expected Loss: ${sl_loss:.2f}

RISK/REWARD RATIO: {(tp_profit/max(sl_loss,1)):.2f}:1
PIP VALUE: ${pip_value:.2f}
===============================
"""
            self.calc_results.delete(1.0, tk.END)
            self.calc_results.insert(tk.END, result_text)

        except Exception as e:
            self.calc_results.delete(1.0, tk.END)
            self.calc_results.insert(tk.END,
                                     f"❌ Calculation Error: {str(e)}\n")

    def export_logs(self):
        """Enhanced log export"""
        try:
            if not os.path.exists("logs"):
                os.makedirs("logs")

            log_content = self.log_area.get(1.0, tk.END)
            filename = f"logs/gui_logs_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

            with open(filename, 'w') as f:
                f.write(log_content)

            self.log(f"💾 Logs exported to {filename}")
            messagebox.showinfo("✅ Export Success",
                                f"Logs exported to {filename}")
        except Exception as e:
            self.log(f"❌ Error exporting logs: {str(e)}")

    def clear_logs(self):
        """Clear log area"""
        self.log_area.delete(1.0, tk.END)
        self.log("🗑️ Logs cleared")

    def update_gui_data(self):
        """Ultra-responsive GUI with real-time market analysis and profit optimization"""
        try:
            # Enhanced MT5 status check with performance monitoring
            connection_start = time.time()
            mt5_status = check_mt5_status()
            connection_time = (time.time() - connection_start) * 1000  # ms

            if mt5_status:
                status_color = "green" if connection_time < 100 else "orange"
                self.status_lbl.config(text=f"Status: Connected ✅ ({connection_time:.1f}ms)",
                                       foreground=status_color)

                # Real-time performance metrics
                if hasattr(self, '_last_update_time'):
                    update_interval = time.time() - self._last_update_time
                    if update_interval > 3.0:  # Slow updates warning
                        logger(f"⚠️ Slow GUI update detected: {update_interval:.1f}s")

                self._last_update_time = time.time()

                # Get current account info untuk real-time update
                info = get_account_info()
                if info:
                    # Update all account labels immediately
                    self.balance_lbl.config(text=f"Balance: ${info['balance']:,.2f}")
                    self.equity_lbl.config(text=f"Equity: ${info['equity']:,.2f}")
                    self.margin_lbl.config(text=f"Free Margin: ${info['free_margin']:,.2f}")

                    # Calculate and display margin level
                    margin_level = info.get('margin_level', 0)
                    if margin_level > 0:
                        margin_color = "green" if margin_level > 300 else "orange" if margin_level > 150 else "red"
                        self.margin_level_lbl.config(text=f"Margin Level: {margin_level:.2f}%", foreground=margin_color)
                    else:
                        self.margin_level_lbl.config(text="Margin Level: ∞%", foreground="green")

                    self.server_lbl.config(text=f"Server: {info['server']} | Login: {info['login']}")

                    # Initialize session_start_balance if not set
                    global session_start_balance
                    if session_start_balance is None:
                        session_start_balance = info['balance']
                        session_data['start_balance'] = info['balance']
                        logger(
                            f"💰 Session initialized - Starting Balance: ${session_start_balance:.2f}"
                        )

                else:
                    # Error getting account info
                    self.balance_lbl.config(text="Balance: Error", foreground="red")
                    self.equity_lbl.config(text="Equity: Error", foreground="red")
                    self.margin_lbl.config(text="Free Margin: Error", foreground="red")
                    self.margin_level_lbl.config(text="Margin Level: Error", foreground="red")
                    logger("⚠️ Cannot get account info from MT5")

            else:
                # MT5 not connected
                self.status_lbl.config(text="Status: Disconnected ❌", foreground="red")
                self.server_lbl.config(text="Server: N/A")
                self.balance_lbl.config(text="Balance: N/A", foreground="gray")
                self.equity_lbl.config(text="Equity: N/A", foreground="gray")
                self.margin_lbl.config(text="Free Margin: N/A", foreground="gray")
                self.margin_level_lbl.config(text="Margin Level: N/A", foreground="gray")

            # Update trading statistics with proper calculations
            self.daily_orders_lbl.config(
                text=f"Daily Orders: {session_data.get('daily_orders', 0)}")

            # Calculate daily profit from current equity vs start balance
            actual_daily_profit = 0.0
            daily_profit_percent = 0.0

            if info and session_start_balance and session_start_balance > 0:
                actual_daily_profit = info['equity'] - session_start_balance
                session_data['daily_profit'] = actual_daily_profit
                daily_profit_percent = (actual_daily_profit /
                                        session_start_balance) * 100
            else:
                actual_daily_profit = session_data.get('daily_profit', 0.0)

            # Color coding for profit/loss
            daily_profit_color = "green" if actual_daily_profit >= 0 else "red"
            self.daily_profit_lbl.config(
                text=
                f"Daily P/L: ${actual_daily_profit:.2f} ({daily_profit_percent:+.2f}%)",
                foreground=daily_profit_color)

            # Calculate win rate from closed positions with better tracking
            total_closed = session_data.get(
                'winning_trades', 0) + session_data.get('losing_trades', 0)
            winning_trades = session_data.get('winning_trades', 0)

            if total_closed > 0:
                win_rate = (winning_trades / total_closed) * 100
                win_rate_color = "green" if win_rate >= 60 else "orange" if win_rate >= 40 else "red"
                self.win_rate_lbl.config(
                    text=
                    f"Win Rate: {win_rate:.1f}% ({winning_trades}W/{total_closed-winning_trades}L)",
                    foreground=win_rate_color)
            else:
                self.win_rate_lbl.config(text="Win Rate: -- % (0W/0L)",
                                         foreground="gray")

            # Update positions count with real-time data
            positions = get_positions()
            position_count = len(positions) if positions else 0
            self.open_positions_lbl.config(
                text=f"Open Positions: {position_count}/{max_positions}")

            # Update session information
            try:
                current_session = get_current_trading_session()
                if current_session:
                    session_name = current_session["name"]
                    volatility = current_session["info"]["volatility"]
                    session_color = {
                        "very_high": "red",
                        "high": "orange",
                        "medium": "green",
                        "low": "blue"
                    }.get(volatility, "gray")

                    self.session_lbl.config(
                        text=
                        f"Session: {session_name} ({volatility.upper()} volatility)",
                        foreground=session_color)
                else:
                    self.session_lbl.config(
                        text="Session: Outside Major Sessions",
                        foreground="gray")
            except Exception as e:
                self.session_lbl.config(text="Session: Error",
                                        foreground="red")

            # Update bot status with current strategy info
            global bot_running, current_strategy
            if bot_running:
                self.bot_status_lbl.config(
                    text=f"Bot: Running 🟢 ({current_strategy})",
                    foreground="green")
            else:
                self.bot_status_lbl.config(text="Bot: Stopped 🔴",
                                           foreground="red")

            # Update positions table
            self.update_positions()

            # Log periodic status for debugging
            if hasattr(self, '_update_counter'):
                self._update_counter += 1
            else:
                self._update_counter = 1

            # Log every 30 updates (about 1 minute)
            if self._update_counter % 30 == 0:
                if info:
                    logger(
                        f"📊 GUI Update #{self._update_counter}: Balance=${info['balance']:.2f}, Equity=${info['equity']:.2f}, Positions={position_count}"
                    )
                else:
                    logger(
                        f"📊 GUI Update #{self._update_counter}: MT5 disconnected"
                    )

        except Exception as e:
            logger(f"❌ GUI update error: {str(e)}")
            # Show error in status
            self.status_lbl.config(text="Status: Update Error ❌", foreground="red")
            import traceback
            logger(f"📝 GUI update traceback: {traceback.format_exc()}")

        # Schedule next update with configurable interval
        self.root.after(GUI_UPDATE_INTERVAL,
                        self.update_gui_data)  # Update every 1.5 seconds

    def update_positions(self):
        """Enhanced position table updating"""
        try:
            # Clear existing items
            for item in self.pos_tree.get_children():
                self.pos_tree.delete(item)

            # Get current positions
            positions = get_positions()

            for pos in positions:
                position_type = "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL"

                # Get current price
                tick = mt5.symbol_info_tick(pos.symbol)
                if tick:
                    current_price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask

                    # Calculate pips
                    price_diff = current_price - pos.price_open if pos.type == mt5.ORDER_TYPE_BUY else pos.price_open - current_price
                    pip_size = 0.01 if "JPY" in pos.symbol else 0.0001
                    pips = price_diff / pip_size

                    # Insert with color coding
                    profit_color = "green" if pos.profit >= 0 else "red"

                    self.pos_tree.insert(
                        "",
                        "end",
                        values=(pos.ticket, pos.symbol, position_type,
                                f"{pos.volume:.2f}", f"{pos.price_open:.5f}",
                                f"{current_price:.5f}", f"${pos.profit:.2f}",
                                f"{pips:.1f}"),
                        tags=(profit_color, ))
                else:
                    # If tick is unavailable
                    self.pos_tree.insert(
                        "",
                        "end",
                        values=(pos.ticket, pos.symbol, position_type,
                                f"{pos.volume:.2f}", f"{pos.price_open:.5f}",
                                "N/A", f"${pos.profit:.2f}", "N/A"),
                        tags=("red" if pos.profit < 0 else "green", ))

            # Configure colors
            self.pos_tree.tag_configure("green", foreground="green")
            self.pos_tree.tag_configure("red", foreground="red")

        except Exception as e:
            logger(f"❌ Error updating positions: {str(e)}")

    def generate_report_now(self):
        """Generate and display performance report immediately"""
        try:
            report = generate_performance_report()

            # Show in message box
            messagebox.showinfo("📊 Performance Report", report)

            # Log to GUI
            self.log("📊 Performance report generated:")
            for line in report.split('\n'):
                if line.strip():
                    self.log(f"   {line}")

            # Send to Telegram if enabled
            if gui and hasattr(gui, 'telegram_var') and gui.telegram_var.get():
                send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
                              "📊 MANUAL REPORT\n" + report)
                self.log("📱 Report sent to Telegram")

        except Exception as e:
            self.log(f"❌ Error generating report: {str(e)}")

    def test_recovery(self):
        """Test auto-recovery system"""
        try:
            self.log("🔄 Testing auto-recovery system...")

            # Test MT5 connection
            if check_mt5_status():
                self.log("✅ MT5 connection: OK")
            else:
                self.log("⚠️ MT5 connection: FAILED - triggering recovery...")
                success = auto_recovery_check()
                self.log(
                    f"🔄 Recovery result: {'✅ SUCCESS' if success else '❌ FAILED'}"
                )

            # Test account info
            info = get_account_info()
            if info:
                self.log(
                    f"✅ Account info: Balance=${info['balance']:.2f}, Equity=${info['equity']:.2f}"
                )
            else:
                self.log("⚠️ Account info: UNAVAILABLE")

            # Test symbol validation
            symbol = self.symbol_var.get()
            if validate_and_activate_symbol(symbol):
                self.log(f"✅ Symbol validation: {symbol} OK")
            else:
                self.log(f"⚠️ Symbol validation: {symbol} FAILED")

            self.log("🔧 Recovery test completed!")

        except Exception as e:
            self.log(f"❌ Recovery test error: {str(e)}")

    def on_closing(self):
        """Enhanced closing handler with cleanup"""
        global bot_running

        # Stop bot gracefully
        if bot_running:
            self.log("🛑 Stopping bot before exit...")
            self.stop_bot()
            time.sleep(2)

        # Send final report if enabled
        try:
            if gui and hasattr(gui, 'telegram_var') and gui.telegram_var.get():
                final_report = generate_performance_report()
                send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
                              "🛑 BOT SHUTDOWN\n" + final_report)
                self.log("📱 Final report sent to Telegram")
        except Exception as e:
            self.log(f"⚠️ Error sending final report: {str(e)}")

        # Close MT5 connection
        try:
            if mt5_connected:
                mt5.shutdown()
                self.log("🔌 MT5 connection closed")
        except Exception as e:
            self.log(f"⚠️ Error closing MT5: {str(e)}")

        self.root.destroy()


# Configure run command to run the bot
if __name__ == "__main__":
    try:
        import tkinter as tk
        from tkinter import messagebox

        # Check Python version compatibility
        import sys
        if sys.version_info < (3, 7):
            print("❌ ERROR: Python 3.7+ required")
            sys.exit(1)

        # Check if MetaTrader5 is available
        try:
            import MetaTrader5 as mt5
            print("✅ MetaTrader5 module available")
        except ImportError:
            print("❌ ERROR: MetaTrader5 module not found")
            print("💡 Install with: pip install MetaTrader5")
            sys.exit(1)

        # Initialize GUI
        root = tk.Tk()
        gui = TradingBotGUI(root)

        # Make gui globally accessible
        globals()['gui']= gui

        # Validate configuration and environment
        ensure_log_directory()

        # Enhanced startup logging
        logger(
            "🚀 === MT5 ADVANCED AUTO TRADING BOT v4.0 - Premium Edition ===")
        logger("🔧 Features: Enhanced MT5 Connection, Improved Error Handling")
        logger(
            "📱 Advanced Diagnostics, Real-time Updates, Better Profitability")
        logger("🎯 Comprehensive Symbol Validation & Market Data Testing")
        logger("⚡ Optimized for Maximum Win Rate and Minimal Errors")
        logger("=" * 70)
        logger("🚀 STARTUP SEQUENCE:")
        logger("   1. GUI initialized successfully")
        logger("   2. Auto-connecting to MT5...")
        logger("   3. Validating trading environment...")
        logger("💡 NEXT STEPS: Wait for connection, then click 'START BOT'")
        logger("=" * 70)

        root.mainloop()

    except Exception as e:
        print(f"❌ CRITICAL STARTUP ERROR: {str(e)}")
        print("🔧 SOLUSI:")
        print("   1. Pastikan Python 3.7+ terinstall")
        print(
            "   2. Install dependencies: pip install MetaTrader5 pandas numpy tkinter"
        )
        print("   3. Pastikan MT5 sudah terinstall")
        print("   4. Restart aplikasi")
        import traceback
        print(f"📝 Detail error: {traceback.format_exc()}")
        input("Press Enter to exit...")


import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import threading
import time
import datetime
import tkinter as tk
from tkinter import ttk, messagebox
import requests
from typing import Optional, Dict, Any, List, Tuple
from tkinter.scrolledtext import ScrolledText
import csv
import os
import sys
import platform

# Ensure all required imports are available
try:
    import requests
except ImportError:
    print("⚠️ requests module not found, installing...")
    os.system("pip install requests")
    import requests

try:
    import MetaTrader5 as mt5
except ImportError:
    print("⚠️ MetaTrader5 module not found, installing...")
    os.system("pip install MetaTrader5")
    import MetaTrader5 as mt5


# --- LOGGING FUNCTION ---
def logger(msg: str) -> None:
    """Enhanced logging function with timestamp and GUI integration"""
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    full_msg = f"[{timestamp}] {msg}"
    print(full_msg)

    # Try to log to GUI if available
    try:
        if 'gui' in globals() and gui:
            gui.log(full_msg)
    except Exception as e:
        # Specific exception handling for GUI logging
        print(f"GUI logging failed: {str(e)}")


def validate_numeric_input(value: str,
                           min_val: float = 0.0,
                           max_val: float = None) -> float:
    """Validate and convert numeric input with proper error handling"""
    try:
        numeric_value = float(value.strip())
        if numeric_value < min_val:
            raise ValueError(
                f"Value {numeric_value} is below minimum {min_val}")
        if max_val is not None and numeric_value > max_val:
            raise ValueError(
                f"Value {numeric_value} exceeds maximum {max_val}")
        return numeric_value
    except (ValueError, AttributeError) as e:
        logger(f"Invalid numeric input '{value}': {str(e)}")
        raise


def validate_string_input(value: str, allowed_values: List[str] = None) -> str:
    """Validate string input with specific allowed values"""
    try:
        clean_value = value.strip().upper()
        if not clean_value:
            raise ValueError("Empty string not allowed")
        if allowed_values and clean_value not in allowed_values:
            raise ValueError(
                f"Value '{clean_value}' not in allowed values: {allowed_values}")
        return clean_value
    except AttributeError as e:
        logger(f"Invalid string input: {str(e)}")
        raise


def is_high_impact_news_time() -> bool:
    """Enhanced high-impact news detection with basic time-based filtering"""
    try:
        # Basic time-based news schedule (UTC)
        utc_now = datetime.datetime.now()
        current_hour = utc_now.hour
        current_minute = utc_now.minute
        day_of_week = utc_now.weekday()  # 0=Monday, 6=Sunday

        # Critical news times (UTC) - avoid trading during these
        critical_times = [
            # Daily major news
            (8, 30, 9, 30),  # European session major news
            (12, 30, 14, 30),  # US session major news (NFP, CPI, FOMC, etc)
            (16, 0, 16, 30),  # London Fix

            # Weekly specifics
            (13, 0, 14,
             0) if day_of_week == 2 else None,  # Wednesday FOMC minutes
            (12, 30, 15,
             0) if day_of_week == 4 else None,  # Friday NFP + major data
        ]

        # Remove None values
        critical_times = [t for t in critical_times if t is not None]

        current_time_minutes = current_hour * 60 + current_minute

        for start_h, start_m, end_h, end_m in critical_times:
            start_minutes = start_h * 60 + start_m
            end_minutes = end_h * 60 + end_m

            if start_minutes <= current_time_minutes <= end_minutes:
                logger(
                    f"⚠️ High-impact news time detected: {current_hour:02d}:{current_minute:02d} UTC"
                )
                return True

        return False

    except Exception as e:
        logger(f"❌ Error in news time check: {str(e)}")
        return False  # Continue trading if check fails


def cleanup_resources() -> None:
    """
    Cleanup utility to manage memory usage and resource leaks.

    This function helps prevent memory leaks by explicitly cleaning up
    large data structures and forcing garbage collection.
    """
    try:
        import gc
        # Force garbage collection
        gc.collect()

        # Clear any large global dataframes if they exist
        global session_data
        if 'large_dataframes' in session_data:
            session_data['large_dataframes'].clear()

        logger("🧹 Memory cleanup completed")

    except Exception as e:
        logger(f"⚠️ Memory cleanup error: {str(e)}")


def ensure_log_directory() -> bool:
    """
    Ensure log directory exists with proper error handling.

    Returns:
        bool: True if directory exists or was created successfully
    """
    try:
        log_dir = "logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
            logger(f"📁 Created log directory: {log_dir}")
        return True
    except PermissionError as pe:
        logger(f"❌ Permission denied creating log directory: {str(pe)}")
        return False
    except Exception as e:
        logger(f"❌ Failed to create log directory: {str(e)}")
        return False


# --- CONFIGURATION CONSTANTS ---
MAX_CONNECTION_ATTEMPTS = 5
MAX_CONSECUTIVE_FAILURES = 10
DEFAULT_TIMEOUT_SECONDS = 10
MAX_SYMBOL_TEST_ATTEMPTS = 3
CONNECTION_RETRY_DELAY = 3
GUI_UPDATE_INTERVAL = 1500  # milliseconds
BOT_LOOP_INTERVALS = {
    "HFT": 0.5,
    "Scalping": 1.0,
    "Intraday": 2.0,
    "Arbitrage": 2.0
}

# --- CONFIG & GLOBALS ---
# Use environment variables for security, fallback to defaults for testing
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN",
                           "8365734234:AAH2uTaZPDD47Lnm3y_Tcr6aj3xGL-bVsgk")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5061106648")
bot_running = False
disconnect_count = 0
session_start_balance = None
loss_streak = 0
max_loss_streak = 3
max_drawdown = 0.05
profit_target = 0.10
daily_max_loss = 0.05
trailing_stop_val = 0.0
active_hours = ("00:00", "23:59")  # 24/7 trading capability
position_count = 0
max_positions = 10
current_strategy = "Scalping"
gui = None
trade_lock = threading.Lock()
last_trade_time = {}
mt5_connected = False

# Enhanced Trading Session Management
TRADING_SESSIONS = {
    "Asia": {
        "start": "21:00",
        "end": "06:00",
        "timezone": "UTC",
        "active": True,
        "volatility": "medium",
        "preferred_pairs": ["USDJPY", "AUDUSD", "NZDUSD", "EURJPY", "GBPJPY"]
    },
    "London": {
        "start": "07:00",
        "end": "15:00",
        "timezone": "UTC",
        "active": True,
        "volatility": "high",
        "preferred_pairs": ["EURUSD", "GBPUSD", "EURGBP", "EURJPY", "GBPJPY"]
    },
    "New_York": {
        "start": "15:00",
        "end": "21:00",
        "timezone": "UTC",
        "active": True,
        "volatility": "high",
        "preferred_pairs": ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "AUDUSD"]
    },
    "Overlap_London_NY": {
        "start": "15:00",
        "end": "21:00",
        "timezone": "UTC",
        "active": True,
        "volatility": "very_high",
        "preferred_pairs": ["EURUSD", "GBPUSD", "USDCAD"]
    }
}

# Session-specific trading parameters
SESSION_SETTINGS = {
    "Asia": {
        "max_spread_multiplier": 1.5,
        "volatility_filter": 0.7,
        "trading_intensity": "conservative"
    },
    "London": {
        "max_spread_multiplier": 1.2,
        "volatility_filter": 1.0,
        "trading_intensity": "aggressive"
    },
    "New_York": {
        "max_spread_multiplier": 1.0,
        "volatility_filter": 1.2,
        "trading_intensity": "aggressive"
    },
    "Overlap_London_NY": {
        "max_spread_multiplier": 0.8,
        "volatility_filter": 1.5,
        "trading_intensity": "very_aggressive"
    }
}

# Trading session data
session_data = {
    "start_time": None,
    "start_balance": 0.0,
    "total_trades": 0,
    "winning_trades": 0,
    "losing_trades": 0,
    "total_profit": 0.0,
    "daily_orders": 0,
    "daily_profit": 0.0,
    "last_balance": 0.0,
    "session_equity": 0.0,
    "max_equity": 0.0
}


def connect_mt5() -> bool:
    """Enhanced MT5 connection with comprehensive debugging and better error handling"""
    global mt5_connected
    try:
        import platform
        import sys

        # Shutdown any existing connection first
        try:
            mt5.shutdown()
            time.sleep(1)
        except:
            pass

        logger("🔍 === MT5 CONNECTION DIAGNOSTIC ===")
        logger(f"🔍 Python Version: {sys.version}")
        logger(f"🔍 Python Architecture: {platform.architecture()[0]}")
        logger(f"🔍 Platform: {platform.system()} {platform.release()}")

        # Enhanced MT5 module check
        try:
            import MetaTrader5 as mt5_test
            logger("✅ MetaTrader5 module imported successfully")
            logger(f"🔍 MT5 Module Version: {getattr(mt5_test, '__version__', 'Unknown')}")
        except ImportError as e:
            logger(f"❌ Failed to import MetaTrader5: {e}")
            logger("💡 Trying alternative installation methods...")
            try:
                import subprocess
                subprocess.run([sys.executable, "-m", "pip", "install", "MetaTrader5", "--upgrade"], check=True)
                import MetaTrader5 as mt5_test
                logger("✅ MetaTrader5 installed and imported successfully")
            except Exception as install_e:
                logger(f"❌ Installation failed: {install_e}")
                return False

        # Initialize MT5 connection with enhanced retries
        for attempt in range(MAX_CONNECTION_ATTEMPTS):
            logger(
                f"🔄 MT5 connection attempt {attempt + 1}/{MAX_CONNECTION_ATTEMPTS}..."
            )

            # Try different initialization methods
            init_methods = [
                lambda: mt5.initialize(),
                lambda: mt5.initialize(
                    path="C:\\Program Files\\MetaTrader 5\\terminal64.exe"),
                lambda: mt5.initialize(
                    path="C:\\Program Files (x86)\\MetaTrader 5\\terminal.exe"),
                lambda: mt5.initialize(login=0),  # Auto-detect current login
            ]

            initialized = False
            for i, init_method in enumerate(init_methods):
                try:
                    logger(f"🔄 Trying initialization method {i + 1}...")
                    result = init_method()
                    if result:
                        initialized = True
                        logger(f"✅ MT5 initialized using method {i + 1}")
                        break
                    else:
                        error = mt5.last_error()
                        logger(f"⚠️ Method {i + 1} failed with error: {error}")
                except Exception as e:
                    logger(f"⚠️ Method {i + 1} exception: {str(e)}")
                    continue

            if not initialized:
                logger(
                    f"❌ All initialization methods failed on attempt {attempt + 1}"
                )
                last_error = mt5.last_error()
                logger(f"🔍 Last MT5 Error Code: {last_error}")

                if attempt < MAX_CONNECTION_ATTEMPTS - 1:
                    time.sleep(CONNECTION_RETRY_DELAY)
                    continue
                else:
                    logger("💡 SOLUSI TROUBLESHOOTING:")
                    logger(
                        "   1. ⚠️ WAJIB: Jalankan MT5 sebagai Administrator")
                    logger(
                        "   2. ⚠️ WAJIB: Pastikan MT5 sudah login ke akun trading")
                    logger("   3. ⚠️ Pastikan Python dan MT5 sama-sama 64-bit")
                    logger("   4. ⚠️ Tutup semua instance MT5 lain yang berjalan")
                    logger("   5. ⚠️ Restart MT5 jika masih bermasalah")
                    mt5_connected = False
                    return False

            # Enhanced diagnostic information
            try:
                version_info = mt5.version()
                if version_info:
                    logger(f"🔍 MT5 Version: {version_info}")
                    logger(
                        f"🔍 MT5 Build: {getattr(version_info, 'build', 'N/A')}")
                else:
                    logger("⚠️ Cannot get MT5 version info")
                    last_error = mt5.last_error()
                    logger(f"🔍 Version error code: {last_error}")
            except Exception as e:
                logger(f"⚠️ Version check failed: {str(e)}")

            # Enhanced account validation with detailed error reporting
            logger("🔍 Checking account information...")
            account_info = mt5.account_info()
            if account_info is None:
                last_error = mt5.last_error()
                logger(
                    f"❌ GAGAL mendapatkan info akun MT5 - Error Code: {last_error}"
                )
                logger("💡 PENYEBAB UTAMA:")
                logger("   ❌ MT5 belum login ke akun trading")
                logger("   ❌ Koneksi ke server broker terputus")
                logger("   ❌ MT5 tidak dijalankan sebagai Administrator")
                logger("   ❌ Python tidak dapat mengakses MT5 API")
                logger("   ❌ Firewall atau antivirus memblokir koneksi")

                # Try to get any available info for debugging
                try:
                    terminal_info_debug = mt5.terminal_info()
                    if terminal_info_debug:
                        logger(
                            f"🔍 Debug - Terminal Company: {getattr(terminal_info_debug, 'company', 'N/A')}"
                        )
                        logger(
                            f"🔍 Debug - Terminal Connected: {getattr(terminal_info_debug, 'connected', False)}"
                        )
                    else:
                        logger("🔍 Debug - Terminal info juga tidak tersedia")
                except:
                    logger("🔍 Debug - Tidak dapat mengakses terminal info")

                if attempt < MAX_CONNECTION_ATTEMPTS - 1:
                    logger(
                        f"🔄 Mencoba ulang dalam 5 detik... (attempt {attempt + 1})"
                    )
                    mt5.shutdown()
                    time.sleep(5)
                    continue
                else:
                    logger("❌ SOLUSI WAJIB DICOBA:")
                    logger("   1. 🔴 TUTUP MT5 SEPENUHNYA")
                    logger("   2. 🔴 KLIK KANAN MT5 → RUN AS ADMINISTRATOR")
                    logger("   3. 🔴 LOGIN KE AKUN TRADING DENGAN BENAR")
                    logger("   4. 🔴 PASTIKAN STATUS 'CONNECTED' DI MT5")
                    logger("   5. 🔴 BUKA MARKET WATCH DAN TAMBAHKAN SYMBOL")
                    mt5_connected = False
                    return False

            # Account info berhasil didapat
            logger(f"✅ Account Login: {account_info.login}")
            logger(f"✅ Account Server: {account_info.server}")
            logger(f"✅ Account Name: {getattr(account_info, 'name', 'N/A')}")
            logger(f"✅ Account Balance: ${account_info.balance:.2f}")
            logger(f"✅ Account Equity: ${account_info.equity:.2f}")
            logger(
                f"✅ Account Currency: {getattr(account_info, 'currency', 'USD')}"
            )
            logger(f"✅ Trade Allowed: {account_info.trade_allowed}")

            # Check terminal info with detailed diagnostics
            logger("🔍 Checking terminal information...")
            terminal_info = mt5.terminal_info()
            if terminal_info is None:
                logger("❌ Gagal mendapatkan info terminal MT5")
                last_error = mt5.last_error()
                logger(f"🔍 Terminal error code: {last_error}")

                if attempt < MAX_CONNECTION_ATTEMPTS - 1:
                    logger("🔄 Mencoba ulang...")
                    mt5.shutdown()
                    time.sleep(3)
                    continue
                else:
                    logger(
                        "❌ Terminal info tidak tersedia setelah semua percobaan"
                    )
                    mt5_connected = False
                    return False

            logger(f"✅ Terminal Connected: {terminal_info.connected}")
            logger(
                f"✅ Terminal Company: {getattr(terminal_info, 'company', 'N/A')}"
            )
            logger(f"✅ Terminal Name: {getattr(terminal_info, 'name', 'N/A')}")
            logger(f"✅ Terminal Path: {getattr(terminal_info, 'path', 'N/A')}")

            # Validate trading permissions
            if not account_info.trade_allowed:
                logger("⚠️ PERINGATAN: Akun tidak memiliki izin trading")
                logger(
                    "💡 Hubungi broker untuk mengaktifkan trading permission")
                logger("⚠️ Bot akan melanjutkan dengan mode READ-ONLY")

            # Check if terminal is connected to trade server
            if not terminal_info.connected:
                logger("❌ KRITIS: Terminal tidak terhubung ke trade server")
                logger("💡 SOLUSI:")
                logger("   1. Periksa koneksi internet")
                logger("   2. Cek status server broker")
                logger("   3. Login ulang ke MT5")
                logger("   4. Restart MT5 terminal")

                if attempt < MAX_CONNECTION_ATTEMPTS - 1:
                    logger("🔄 Mencoba reconnect...")
                    mt5.shutdown()
                    time.sleep(5)
                    continue
                else:
                    logger(
                        "❌ Terminal tetap tidak terhubung setelah semua percobaan"
                    )
                    mt5_connected = False
                    return False

            # Enhanced market data testing with more symbols and better error handling
            test_symbols = [
                "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD",
                "XAUUSD", "XAUUSDm", "GOLD", "BTCUSD", "EURGBP", "EURJPY"
            ]

            working_symbols = []
            failed_symbols = []

            logger("🔍 Testing market data access for symbols...")

            # First, get all available symbols
            logger("🔍 Mengambil daftar semua symbols...")
            try:
                all_symbols = mt5.symbols_get()
                if all_symbols and len(all_symbols) > 0:
                    logger(f"✅ Total symbols available: {len(all_symbols)}")
                    available_symbol_names = [
                        s.name for s in all_symbols if hasattr(s, 'name')
                    ]
                    logger(
                        f"🔍 Sample symbols: {', '.join(available_symbol_names[:10])}")
                else:
                    logger(
                        "⚠️ PERINGATAN: Tidak ada symbols dari mt5.symbols_get()"
                    )
                    logger(
                        "💡 Kemungkinan Market Watch kosong atau tidak aktif")
            except Exception as e:
                logger(f"❌ Error getting symbols list: {str(e)}")
                all_symbols = None

            # Test each symbol with comprehensive validation
            for test_symbol in test_symbols:
                try:
                    logger(f"🔍 Testing symbol: {test_symbol}")

                    # Try to get symbol info
                    symbol_info = mt5.symbol_info(test_symbol)
                    if symbol_info is None:
                        logger(f"❌ {test_symbol}: Symbol info tidak tersedia")
                        failed_symbols.append(f"{test_symbol} (not found)")
                        continue

                    logger(
                        f"🔍 {test_symbol}: visible={symbol_info.visible}, trade_mode={getattr(symbol_info, 'trade_mode', 'N/A')}"
                    )

                    # Try to make it visible if not already
                    if not symbol_info.visible:
                        logger(
                            f"🔄 Mengaktifkan {test_symbol} di Market Watch...")
                        select_result = mt5.symbol_select(test_symbol, True)
                        logger(
                            f"🔍 {test_symbol} activation result: {select_result}")

                        if select_result:
                            time.sleep(1.0)  # Wait longer for activation

                            # Re-check symbol info
                            symbol_info = mt5.symbol_info(test_symbol)
                            if symbol_info is None or not symbol_info.visible:
                                logger(f"❌ {test_symbol}: Gagal diaktifkan")
                                failed_symbols.append(
                                    f"{test_symbol} (activation failed)")
                                continue
                            else:
                                logger(f"✅ {test_symbol}: Berhasil diaktifkan")
                        else:
                            logger(f"❌ {test_symbol}: Gagal aktivasi")
                            failed_symbols.append(
                                f"{test_symbol} (select failed)")
                            continue

                    # Test tick data with multiple attempts and better error handling
                    tick_attempts = 5
                    tick_success = False
                    last_tick_error = None

                    logger(f"🔍 Testing tick data untuk {test_symbol}...")
                    for tick_attempt in range(tick_attempts):
                        try:
                            tick = mt5.symbol_info_tick(test_symbol)
                            if tick is not None:
                                if hasattr(tick, 'bid') and hasattr(
                                        tick, 'ask'):
                                    if tick.bid > 0 and tick.ask > 0:
                                        spread = abs(tick.ask - tick.bid)
                                        spread_percent = (
                                            spread / tick.bid
                                        ) * 100 if tick.bid > 0 else 0
                                        logger(
                                            f"✅ {test_symbol}: Bid={tick.bid}, Ask={tick.ask}, Spread={spread:.5f} ({spread_percent:.3f}%)"
                                        )
                                        working_symbols.append(test_symbol)
                                        tick_success = True
                                        break
                                    else:
                                        last_tick_error = f"Invalid prices: bid={tick.bid}, ask={tick.ask}"
                                else:
                                    last_tick_error = "Missing bid/ask attributes"
                            else:
                                last_tick_error = "Tick is None"

                            # Add error details for debugging
                            if tick_attempt == 0:
                                tick_error = mt5.last_error()
                                if tick_error != (0, 'Success'):
                                    logger(
                                        f"🔍 {test_symbol} tick error: {tick_error}"
                                    )

                        except Exception as tick_e:
                            last_tick_error = str(tick_e)

                        if tick_attempt < tick_attempts - 1:
                            time.sleep(0.8)  # Longer wait between attempts

                    if not tick_success:
                        logger(
                            f"❌ {test_symbol}: Tidak dapat mengambil tick data"
                        )
                        if last_tick_error:
                            logger(f"   Last error: {last_tick_error}")
                        failed_symbols.append(f"{test_symbol} (no valid tick)")

                except Exception as e:
                    error_msg = f"Exception: {str(e)}"
                    logger(f"❌ Error testing {test_symbol}: {error_msg}")
                    failed_symbols.append(f"{test_symbol} ({error_msg})")
                    continue

            # Report comprehensive results
            logger(f"📊 === MARKET DATA TEST RESULTS ===")
            logger(
                f"✅ Working symbols ({len(working_symbols)}): {', '.join(working_symbols) if working_symbols else 'NONE'}"
            )

            if failed_symbols:
                logger(f"❌ Failed symbols ({len(failed_symbols)}):")
                for i, failed in enumerate(
                        failed_symbols[:10]):  # Show first 10
                    logger(f"   {i+1}. {failed}")
                if len(failed_symbols) > 10:
                    logger(f"   ... dan {len(failed_symbols)-10} lainnya")

            # Check if we have any working symbols
            if len(working_symbols) > 0:
                # Success!
                mt5_connected = True
                logger(f"🎉 === MT5 CONNECTION SUCCESSFUL ===")
                logger(
                    f"👤 Account: {account_info.login} | Server: {account_info.server}"
                )
                logger(
                    f"💰 Balance: ${account_info.balance:.2f} | Equity: ${account_info.equity:.2f}"
                )
                logger(
                    f"🔐 Trade Permission: {'ENABLED' if account_info.trade_allowed else 'READ-ONLY'}"
                )
                logger(f"🌐 Terminal Connected: ✅ YES")
                logger(
                    f"📊 Market Access: ✅ ({len(working_symbols)} symbols working)"
                )
                logger(
                    f"🎯 Bot siap untuk trading dengan symbols: {', '.join(working_symbols[:5])}"
                )
                logger("=" * 50)
                return True
            else:
                if attempt < MAX_CONNECTION_ATTEMPTS - 1:
                    logger(
                        f"⚠️ Tidak ada symbols yang working, retry attempt {attempt + 2}..."
                    )
                    logger("💡 TROUBLESHOOTING:")
                    logger("   1. Buka Market Watch di MT5")
                    logger("   2. Tambahkan symbols secara manual")
                    logger("   3. Pastikan market sedang buka")
                    logger("   4. Cek koneksi internet")
                    mt5.shutdown()
                    time.sleep(5)
                    continue

        # All attempts failed
        logger("❌ === CONNECTION FAILED ===")
        logger("❌ Tidak dapat mengakses data market setelah semua percobaan")
        logger("💡 Solusi yang disarankan:")
        logger("   1. Pastikan MT5 dijalankan sebagai Administrator")
        logger("   2. Pastikan sudah login ke akun dan terkoneksi ke server")
        logger(
            "   3. Buka Market Watch dan pastikan ada symbols yang terlihat")
        logger("   4. Coba restart MT5 terminal")
        logger("   5. Pastikan tidak ada firewall yang memblokir koneksi")
        logger("   6. Pastikan Python dan MT5 sama-sama 64-bit")

        mt5_connected = False
        return False

    except Exception as e:
        logger(f"❌ Critical MT5 connection error: {str(e)}")
        logger("💡 Coba restart aplikasi dan MT5 terminal")
        mt5_connected = False
        return False


def check_mt5_status() -> bool:
    """Enhanced MT5 status check with specific error handling"""
    global mt5_connected
    try:
        if not mt5_connected:
            return False

        # Check account info with specific error handling
        try:
            account_info = mt5.account_info()
        except Exception as acc_e:
            logger(f"❌ Failed to get account info: {str(acc_e)}")
            mt5_connected = False
            return False

        # Check terminal info with specific error handling
        try:
            terminal_info = mt5.terminal_info()
        except Exception as term_e:
            logger(f"❌ Failed to get terminal info: {str(term_e)}")
            mt5_connected = False
            return False

        if account_info is None or terminal_info is None:
            mt5_connected = False
            logger(
                "❌ MT5 status check failed: Account or Terminal info unavailable."
            )
            return False

        if not terminal_info.connected:
            mt5_connected = False
            logger("❌ MT5 status check failed: Terminal not connected.")
            return False

        return True
    except ImportError as ie:
        logger(f"❌ MT5 module import error: {str(ie)}")
        mt5_connected = False
        return False
    except ConnectionError as ce:
        logger(f"❌ MT5 connection error: {str(ce)}")
        mt5_connected = False
        return False
    except Exception as e:
        logger(f"❌ Unexpected MT5 status check error: {str(e)}")
        mt5_connected = False
        return False


def get_symbols() -> List[str]:
    """Get available symbols from MT5 with enhanced error handling"""
    try:
        if not check_mt5_status():
            logger("❌ Cannot get symbols: MT5 not connected.")
            return []

        symbols = mt5.symbols_get()
        if symbols is None:
            logger("❌ Failed to get symbols from MT5.")
            return []

        return [s.name for s in symbols if hasattr(s, 'visible') and s.visible]
    except Exception as e:
        logger(f"❌ Exception in get_symbols: {str(e)}")
        return []


def validate_and_activate_symbol(symbol: str) -> Optional[str]:
    """
    Validasi symbol dengan prioritas detection yang konsisten.
    """
    try:
        if not symbol or not symbol.strip():
            logger(f"❌ Symbol kosong atau tidak valid")
            return None

        # Ensure MT5 is connected
        if not check_mt5_status():
            logger("🔄 MT5 not connected, attempting to reconnect...")
            if not connect_mt5():
                logger("❌ Cannot reconnect to MT5 for symbol validation")
                return None

        original_symbol = symbol.strip().upper()
        logger(f"🔍 Validating symbol: {original_symbol}")

        # PRIORITIZED symbol variations untuk konsistensi
        symbol_variations = []

        # Special handling for gold symbols dengan prioritas yang jelas
        if "XAU" in original_symbol or "GOLD" in original_symbol:
            # Prioritas urutan untuk gold symbols
            gold_priorities = [
                "XAUUSDm",     # Paling umum di banyak broker
                "XAUUSD",      # Standard
                "XAUUSDM",     # Alternative
                "GOLD",        # Simple name
                "GOLDm",       # With suffix
                "GOLDM",       # Capital suffix
                "XAU/USD",     # With separator
                "XAU_USD",     # Underscore
                "XAUUSD.a",    # Spread A
                "XAUUSD.b",    # Spread B
                "XAUUSDmicro", # Micro lots
                "XAUUSD_m"     # Alternative micro
            ]
            symbol_variations.extend(gold_priorities)
        else:
            # Standard forex pairs
            symbol_variations = [
                original_symbol,
                original_symbol.replace("m", "").replace("M", ""),
                original_symbol.replace("USDM", "USD"),
                original_symbol + "m",
                original_symbol + "M",
                original_symbol + ".a",
                original_symbol + ".b",
                original_symbol + ".raw",
                original_symbol[:-1] if original_symbol.endswith(("M", "m")) else original_symbol,
            ]

        # Add forex variations
        if len(original_symbol) == 6:
            # Try with different separators
            symbol_variations.extend([
                original_symbol[:3] + "/" + original_symbol[3:],
                original_symbol[:3] + "-" + original_symbol[3:],
                original_symbol[:3] + "." + original_symbol[3:],
            ])

        # Remove duplicates while preserving order
        seen = set()
        symbol_variations = [
            x for x in symbol_variations if not (x in seen or seen.add(x))
        ]

        valid_symbol = None
        symbol_info = None
        test_results = []

        # Test each variation with detailed logging
        logger(f"🔍 Testing {len(symbol_variations)} symbol variations...")
        for i, variant in enumerate(symbol_variations):
            try:
                logger(f"   {i+1}. Testing: {variant}")
                test_info = mt5.symbol_info(variant)
                if test_info is not None:
                    test_results.append(f"✅ {variant}: Found")
                    valid_symbol = variant
                    symbol_info = test_info
                    logger(f"✅ Found valid symbol: {variant}")
                    break
                else:
                    test_results.append(f"❌ {variant}: Not found")
            except Exception as e:
                test_results.append(f"⚠️ {variant}: Error - {str(e)}")
                logger(f"⚠️ Error testing variant {variant}: {str(e)}")
                continue

        # If not found in variations, search in all available symbols
        if symbol_info is None:
            logger(f"🔍 Searching in all available symbols...")
            try:
                all_symbols = mt5.symbols_get()
                if all_symbols:
                    logger(
                        f"🔍 Searching through {len(all_symbols)} available symbols..."
                    )

                    # First try exact matches
                    for sym in all_symbols:
                        sym_name = getattr(sym, 'name', '')
                        if sym_name.upper() == original_symbol:
                            test_info = mt5.symbol_info(sym_name)
                            if test_info:
                                valid_symbol = sym_name
                                symbol_info = test_info
                                logger(f"✅ Found exact match: {sym_name}")
                                break

                    # Then try partial matches
                    if symbol_info is None:
                        for sym in all_symbols:
                            sym_name = getattr(sym, 'name', '')
                            if (original_symbol[:4] in sym_name.upper()
                                    or sym_name.upper()[:4] in original_symbol
                                    or any(var[:4] in sym_name.upper()
                                           for var in symbol_variations[:5])):
                                test_info = mt5.symbol_info(sym_name)
                                if test_info:
                                    valid_symbol = sym_name
                                    symbol_info = test_info
                                    logger(
                                        f"✅ Found partial match: {sym_name} for {original_symbol}"
                                    )
                                    break
                else:
                    logger("⚠️ No symbols returned from mt5.symbols_get()")
            except Exception as e:
                logger(f"⚠️ Error searching symbols: {str(e)}")

        # Final check - if still not found, log all test results
        if symbol_info is None:
            logger(
                f"❌ Symbol {original_symbol} tidak ditemukan setelah semua percobaan"
            )
            logger("🔍 Test results:")
            for result in test_results[:10]:  # Show first 10 results
                logger(f"   {result}")
            if len(test_results) > 10:
                logger(f"   ... dan {len(test_results)-10} test lainnya")
            return None

        # Use the found valid symbol
        symbol = valid_symbol
        logger(f"🎯 Using symbol: {symbol}")

        # Enhanced symbol activation
        if not symbol_info.visible:
            logger(f"🔄 Activating symbol {symbol} in Market Watch...")

            # Try different activation methods
            activation_success = False
            activation_methods = [
                lambda: mt5.symbol_select(symbol, True),
                lambda: mt5.symbol_select(symbol, True, True
                                          ),  # With strict mode
            ]

            for method_idx, method in enumerate(activation_methods):
                try:
                    result = method()
                    if result:
                        logger(
                            f"✅ Symbol activated using method {method_idx + 1}"
                        )
                        activation_success = True
                        break
                    else:
                        logger(f"⚠️ Activation method {method_idx + 1} failed")
                except Exception as e:
                    logger(
                        f"⚠️ Activation method {method_idx + 1} exception: {str(e)}")

            if not activation_success:
                logger(
                    f"❌ Gagal mengaktifkan symbol {symbol} dengan semua metode"
                )
                logger(
                    "💡 Coba tambahkan symbol secara manual di Market Watch MT5"
                )
                return None

            # Wait for activation to take effect
            time.sleep(1.0)

            # Re-check symbol info after activation
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                logger(
                    f"❌ Symbol {symbol} tidak dapat diakses setelah aktivasi")
                return None

        # Enhanced trading permission validation
        trade_mode = getattr(symbol_info, 'trade_mode', None)
        if trade_mode is not None:
            if trade_mode == mt5.SYMBOL_TRADE_MODE_DISABLED:
                logger(
                    f"❌ Trading untuk symbol {symbol} tidak diizinkan (DISABLED)"
                )
                return None
            elif trade_mode == mt5.SYMBOL_TRADE_MODE_CLOSEONLY:
                logger(
                    f"⚠️ Symbol {symbol} hanya bisa close position (CLOSE_ONLY)"
                )
            elif trade_mode == mt5.SYMBOL_TRADE_MODE_FULL:
                logger(f"✅ Symbol {symbol} mendukung trading penuh")
            else:
                logger(f"🔍 Symbol {symbol} trade mode: {trade_mode}")

        # Enhanced tick validation with better error reporting and extended retry
        tick_valid = False
        tick_attempts = 10  # Increased attempts for problematic symbols
        last_tick_error = None

        logger(f"🔍 Testing tick data for {symbol}...")

        # First check if market is open for this symbol
        symbol_info_check = mt5.symbol_info(symbol)
        if symbol_info_check:
            trade_mode = getattr(symbol_info_check, 'trade_mode', None)
            logger(f"🔍 Symbol trade mode: {trade_mode}")

        for attempt in range(tick_attempts):
            try:
                # Add small delay before each attempt
                if attempt > 0:
                    time.sleep(1.0)  # Longer wait for tick data

                tick = mt5.symbol_info_tick(symbol)
                if tick is not None:
                    if hasattr(tick, 'bid') and hasattr(tick, 'ask'):
                        if tick.bid > 0 and tick.ask > 0:
                            spread = abs(tick.ask - tick.bid)
                            # Additional validation for reasonable tick values
                            if spread < tick.bid * 0.1:  # Spread shouldn't be more than 10% of price
                                logger(
                                    f"✅ Valid tick data - Bid: {tick.bid}, Ask: {tick.ask}, Spread: {spread:.5f}"
                                )
                                tick_valid = True
                                break
                            else:
                                logger(f"⚠️ Tick attempt {attempt + 1}: Unreasonable spread {spread}")
                        else:
                            logger(
                                f"⚠️ Tick attempt {attempt + 1}: Invalid prices (bid={tick.bid}, ask={tick.ask})"
                            )
                    else:
                        logger(
                            f"⚠️ Tick attempt {attempt + 1}: Missing bid/ask attributes"
                        )
                else:
                    logger(f"⚠️ Tick attempt {attempt + 1}: tick is None")
                    # Try to reactivate symbol
                    if attempt < tick_attempts - 2:
                        logger(f"🔄 Attempting to reactivate {symbol}...")
                        mt5.symbol_select(symbol, True)
                        time.sleep(2.0)

            except Exception as e:
                last_tick_error = str(e)
                logger(f"⚠️ Tick attempt {attempt + 1} exception: {str(e)}")

                # Try different tick retrieval methods on exception
                if attempt < tick_attempts - 1:
                    try:
                        # Alternative: Get rates and use last price
                        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 1)
                        if rates is not None and len(rates) > 0:
                            last_rate = rates[0]
                            logger(f"🔄 Alternative: Using rate data - Close: {last_rate['close']}")
                            # Create synthetic tick from rate data
                            tick_valid = True
                            break
                    except:
                        pass

        if not tick_valid:
            logger(f"❌ Tidak dapat mendapatkan data tick valid untuk {symbol}")
            if last_tick_error:
                logger(f"   Last error: {last_tick_error}")
            logger("💡 Kemungkinan penyebab:")
            logger("   - Market sedang tutup")
            logger("   - Symbol tidak aktif diperdagangkan")
            logger("   - Koneksi ke server data bermasalah")
            logger("   - Symbol memerlukan subscription khusus")
            return None

        # Final spread check and warnings with improved thresholds
        try:
            tick = mt5.symbol_info_tick(symbol)
            if tick:
                spread = abs(tick.ask - tick.bid)

                # Dynamic spread thresholds based on symbol type (more realistic)
                if "XAU" in symbol or "GOLD" in symbol:
                    max_spread_warning = 2.0  # Gold: up to $2 spread is normal
                elif "XAG" in symbol or "SILVER" in symbol:
                    max_spread_warning = 0.5  # Silver: up to 50 cents
                elif "JPY" in symbol:
                    max_spread_warning = 0.1   # JPY pairs: up to 10 pips
                elif any(crypto in symbol for crypto in ["BTC", "ETH", "LTC", "ADA", "DOT"]):
                    max_spread_warning = 100.0  # Crypto can have very wide spreads
                elif any(index in symbol for index in ["SPX", "NAS", "DAX", "FTSE"]):
                    max_spread_warning = 5.0   # Stock indices
                elif any(commodity in symbol for commodity in ["OIL", "BRENT", "WTI", "GAS"]):
                    max_spread_warning = 0.01  # Oil and commodities
                else:
                    max_spread_warning = 0.02  # Regular forex pairs: up to 2 pips

                if spread > max_spread_warning:
                    logger(
                        f"⚠️ Spread tinggi untuk {symbol}: {spread:.5f} (threshold: {max_spread_warning})"
                    )
                    logger(
                        "   Symbol tetap valid, tapi perhatikan trading cost")
                else:
                    logger(f"✅ Spread normal untuk {symbol}: {spread:.5f}")

                # Additional warning for extremely high spreads
                if spread > max_spread_warning * 3:
                    logger(f"🚨 SPREAD SANGAT TINGGI! Consider waiting for better conditions")

        except Exception as e:
            logger(f"⚠️ Error checking final spread: {str(e)}")

        # Success!
        logger(f"✅ Symbol {symbol} berhasil divalidasi dan siap untuk trading")

        # Update GUI if available
        if gui:
            gui.symbol_var.set(symbol)

        return symbol  # Return the valid symbol string instead of True

    except Exception as e:
        logger(f"❌ Critical error validating symbol {symbol}: {str(e)}")
        import traceback
        logger(f"🔍 Stack trace: {traceback.format_exc()}")
        return None


def detect_gold_symbol() -> Optional[str]:
    """Auto-detect the correct gold symbol for the current broker"""
    try:
        if not check_mt5_status():
            return None

        # Common gold symbol variations
        gold_symbols = [
            "XAUUSD", "XAUUSDm", "XAUUSDM", "GOLD", "GOLDm", "GOLDM",
            "XAU/USD", "XAUUSD.a", "XAUUSD.b", "XAUUSD.raw", "XAUUSDmicro",
            "XAUUSD_1", "XAU_USD", "AU", "GOLD_USD", "XAUUSD_m"
        ]

        logger("🔍 Auto-detecting gold symbol for current broker...")

        for symbol in gold_symbols:
            try:
                # Test symbol info
                info = mt5.symbol_info(symbol)
                if info:
                    # Try to activate if not visible
                    if not info.visible:
                        if mt5.symbol_select(symbol, True):
                            time.sleep(0.5)
                            info = mt5.symbol_info(symbol)

                    # Test tick data
                    if info and info.visible:
                        tick = mt5.symbol_info_tick(symbol)
                        if tick and hasattr(tick, 'bid') and hasattr(tick, 'ask'):
                            if tick.bid > 1000 and tick.ask > 1000:  # Gold is typically > $1000
                                logger(f"✅ Found working gold symbol: {symbol} (Price: {tick.bid})")
                                return symbol

            except Exception as e:
                logger(f"🔍 Testing {symbol}: {str(e)}")
                continue

        logger("❌ No working gold symbol found")
        return None

    except Exception as e:
        logger(f"❌ Error detecting gold symbol: {str(e)}")
        return None

def get_symbol_suggestions() -> List[str]:
    """Enhanced symbol suggestions with fallback"""
    try:
        if not check_mt5_status():
            return ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD"]

        all_symbols = mt5.symbols_get()
        if not all_symbols:
            return ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD"]

        validated_symbols = []
        popular_patterns = [
            "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD",
            "USDCHF", "EURGBP", "EURJPY", "GBPJPY", "XAUUSD", "XAGUSD"
        ]

        # Find exact matches first
        for pattern in popular_patterns:
            for symbol in all_symbols:
                symbol_name = getattr(symbol, 'name', '')
                if symbol_name == pattern or symbol_name == pattern + "m":
                    try:
                        info = mt5.symbol_info(symbol_name)
                        if info:
                            validated_symbols.append(symbol_name)
                            if len(validated_symbols) >= 15:
                                break
                    except:
                        continue
            if len(validated_symbols) >= 15:
                break

        return validated_symbols[:20] if validated_symbols else [
            "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"
        ]

    except Exception as e:
        logger(f"❌ Error getting symbol suggestions: {str(e)}")
        return ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]


def get_account_info() -> Optional[Dict[str, Any]]:
    """Enhanced account info with error handling and currency detection"""
    try:
        if not check_mt5_status():
            logger("❌ Cannot get account info: MT5 not connected.")
            return None

        info = mt5.account_info()
        if info is None:
            logger("❌ Failed to get account info from MT5.")
            return None

        return {
            "balance": info.balance,
            "equity": info.equity,
            "margin": info.margin,
            "free_margin": info.margin_free,
            "margin_level": info.margin_level,
            "profit": info.profit,
            "login": info.login,
            "server": info.server,
            "currency": getattr(info, 'currency', 'USD')  # Auto-detect account currency
        }
    except Exception as e:
        logger(f"❌ Exception in get_account_info: {str(e)}")
        return None


def get_positions() -> List[Any]:
    """Enhanced position retrieval"""
    try:
        if not check_mt5_status():
            logger("❌ Cannot get positions: MT5 not connected.")
            return []

        positions = mt5.positions_get()
        return list(positions) if positions else []
    except Exception as e:
        logger(f"❌ Exception in get_positions: {str(e)}")
        return []


def get_currency_conversion_rate(from_currency: str, to_currency: str) -> float:
    """Enhanced currency conversion with multiple methods"""
    try:
        if from_currency == to_currency:
            return 1.0

        # Method 1: Direct pair
        direct_pair = f"{from_currency}{to_currency}"
        try:
            symbol_info = mt5.symbol_info(direct_pair)
            if symbol_info and symbol_info.visible:
                tick = mt5.symbol_info_tick(direct_pair)
                if tick and tick.bid > 0:
                    logger(f"💱 Direct conversion rate {direct_pair}: {tick.bid}")
                    return tick.bid
        except:
            pass

        # Method 2: Reverse pair
        reverse_pair = f"{to_currency}{from_currency}"
        try:
            symbol_info = mt5.symbol_info(reverse_pair)
            if symbol_info and symbol_info.visible:
                tick = mt5.symbol_info_tick(reverse_pair)
                if tick and tick.bid > 0:
                    rate = 1.0 / tick.bid
                    logger(f"💱 Reverse conversion rate {reverse_pair}: {rate}")
                    return rate
        except:
            pass

        # Method 3: Cross-rate via USD
        if from_currency != "USD" and to_currency != "USD":
            try:
                usd_from = get_currency_conversion_rate(from_currency, "USD")
                usd_to = get_currency_conversion_rate("USD", to_currency)
                if usd_from > 0 and usd_to > 0:
                    cross_rate = usd_from * usd_to
                    logger(f"💱 Cross-rate {from_currency}->{to_currency} via USD: {cross_rate}")
                    return cross_rate
            except:
                pass

        logger(f"⚠️ No conversion rate found for {from_currency} to {to_currency}")
        return 0.0

    except Exception as e:
        logger(f"❌ Currency conversion error: {str(e)}")
        return 0.0


def calculate_pip_value(symbol: str, lot_size: float) -> float:
    """Enhanced pip value calculation with better symbol recognition"""
    try:
        if not check_mt5_status():
            logger("❌ Cannot calculate pip value: MT5 not connected.")
            return 10.0 * lot_size

        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            logger(f"❌ Cannot calculate pip value: Symbol info for {symbol} not found.")
            return 10.0 * lot_size

        # Enhanced pip size calculation
        if "JPY" in symbol:
            pip_size = 0.01  # JPY pairs
        elif any(precious in symbol for precious in ["XAU", "XAG", "GOLD", "SILVER"]):
            pip_size = 0.1   # Precious metals (Gold/Silver)
        elif any(crypto in symbol for crypto in ["BTC", "ETH", "LTC", "ADA", "DOT"]):
            pip_size = getattr(symbol_info, 'point', 1.0) * 10  # Crypto
        elif any(index in symbol for index in ["SPX", "NAS", "DAX", "FTSE"]):
            pip_size = 1.0   # Stock indices
        elif any(commodity in symbol for commodity in ["OIL", "BRENT", "WTI", "GAS"]):
            pip_size = 0.01  # Commodities
        else:
            pip_size = 0.0001  # Standard forex pairs

        tick_value = getattr(symbol_info, 'trade_tick_value', 1.0)
        tick_size = getattr(symbol_info, 'trade_tick_size', pip_size)

        if tick_size > 0:
            pip_value = (pip_size / tick_size) * tick_value * lot_size
        else:
            pip_value = 10.0 * lot_size

        logger(f"💰 Pip value for {symbol}: {abs(pip_value):.4f} per {lot_size} lots")
        return abs(pip_value)
    except Exception as e:
        logger(f"❌ Exception in calculate_pip_value for {symbol}: {str(e)}")
        return 10.0 * lot_size


def parse_tp_sl_input(input_value: str, unit: str, symbol: str,
                      lot_size: float, current_price: float, order_type: str,
                      is_tp: bool) -> Tuple[float, Dict[str, float]]:
    """Enhanced TP/SL parsing with automatic currency detection and improved calculations"""
    try:
        if not input_value or input_value == "0" or input_value == "":
            return 0.0, {}

        value = float(input_value)
        if value <= 0:
            return 0.0, {}

        pip_value = calculate_pip_value(symbol, lot_size)
        account_info = get_account_info()
        balance = account_info['balance'] if account_info else 10000.0

        # Auto-detect account currency
        account_currency = account_info.get('currency', 'USD') if account_info else 'USD'
        logger(f"💱 Auto-detected account currency: {account_currency}")

        calculations = {}
        result_price = 0.0

        # Enhanced pip size calculation based on symbol type
        if "JPY" in symbol:
            pip_size = 0.01  # JPY pairs
        elif any(precious in symbol for precious in ["XAU", "XAG", "GOLD", "SILVER"]):
            pip_size = 0.1   # Precious metals
        elif any(crypto in symbol for crypto in ["BTC", "ETH", "LTC", "ADA", "DOT"]):
            symbol_info = mt5.symbol_info(symbol)
            pip_size = getattr(symbol_info, 'point', 0.0001) * 10 if symbol_info else 1.0
        elif any(index in symbol for index in ["SPX", "NAS", "DAX", "FTSE"]):
            pip_size = 1.0   # Stock indices
        elif any(commodity in symbol for commodity in ["OIL", "BRENT", "WTI"]):
            pip_size = 0.01  # Oil and commodities
        else:
            pip_size = 0.0001  # Standard forex pairs

        if unit == "pips":
            price_movement = value * pip_size
            if is_tp:
                if order_type == "BUY":
                    result_price = current_price + price_movement
                else:
                    result_price = current_price - price_movement
            else:
                if order_type == "BUY":
                    result_price = current_price - price_movement
                else:
                    result_price = current_price + price_movement

            profit_loss_amount = value * pip_value
            calculations['pips'] = value
            calculations['amount'] = profit_loss_amount
            calculations['percent'] = (profit_loss_amount / balance) * 100

        elif unit == "price":
            result_price = value
            price_diff = abs(result_price - current_price)
            pips = price_diff / pip_size
            profit_loss_amount = pips * pip_value

            calculations['pips'] = pips
            calculations['amount'] = profit_loss_amount
            calculations['percent'] = (profit_loss_amount / balance) * 100

        elif unit == "%":
            profit_loss_amount = balance * (value / 100)
            pips = profit_loss_amount / pip_value if pip_value > 0 else 0
            price_movement = pips * pip_size

            if is_tp:
                if order_type == "BUY":
                    result_price = current_price + price_movement
                else:
                    result_price = current_price - price_movement
            else:
                if order_type == "BUY":
                    result_price = current_price - price_movement
                else:
                    result_price = current_price + price_movement

            calculations['pips'] = pips
            calculations['amount'] = profit_loss_amount
            calculations['percent'] = value

        elif unit in ["currency", "USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "NZD"]:
            # Enhanced currency-based TP/SL calculation with automatic detection
            profit_loss_amount = value

            # Use auto-detected account currency
            if unit == "currency":
                unit = account_currency
                profit_loss_amount = value
                logger(f"💱 Using auto-detected currency: {account_currency}")
            elif unit != account_currency:
                # Enhanced conversion with multiple methods
                conversion_rate = get_currency_conversion_rate(unit, account_currency)
                if conversion_rate > 0:
                    profit_loss_amount = value * conversion_rate
                    logger(f"💱 Currency conversion: {value} {unit} = {profit_loss_amount:.2f} {account_currency} (rate: {conversion_rate})")
                else:
                    logger(f"⚠️ Cannot convert {unit} to {account_currency}, using direct value")
                    profit_loss_amount = value

            # Calculate pips from currency amount
            if pip_value > 0:
                pips = profit_loss_amount / pip_value
            else:
                # Fallback calculation for pip value
                try:
                    symbol_info = mt5.symbol_info(symbol)
                    if symbol_info:
                        tick_value = getattr(symbol_info, 'trade_tick_value', 1.0)
                        tick_size = getattr(symbol_info, 'trade_tick_size', pip_size)
                        if tick_size > 0:
                            calculated_pip_value = (pip_size / tick_size) * tick_value * lot_size
                            pips = profit_loss_amount / calculated_pip_value if calculated_pip_value > 0 else 10
                        else:
                            pips = 10  # Default fallback
                    else:
                        pips = 10  # Default fallback
                except:
                    pips = 10  # Default fallback

            price_movement = pips * pip_size

            if is_tp:
                if order_type == "BUY":
                    result_price = current_price + price_movement
                else:
                    result_price = current_price - price_movement
            else:
                if order_type == "BUY":
                    result_price = current_price - price_movement
                else:
                    result_price = current_price + price_movement

            calculations['pips'] = pips
            calculations['amount'] = profit_loss_amount
            calculations['percent'] = (profit_loss_amount / balance) * 100
            calculations['currency'] = unit
            calculations['account_currency'] = account_currency

        return result_price, calculations

    except Exception as e:
        logger(f"❌ Error parsing TP/SL input: {str(e)}")
        return 0.0, {}


def validate_tp_sl_levels(symbol: str, tp_price: float, sl_price: float,
                          order_type: str,
                          current_price: float) -> Tuple[bool, str]:
    """Enhanced TP/SL validation"""
    try:
        if not check_mt5_status():
            return False, "MT5 not connected"

        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return False, f"Symbol {symbol} not found"

        min_stop_level = getattr(symbol_info, 'trade_stops_level',
                                 0) * getattr(symbol_info, 'point', 0.00001)
        spread = getattr(symbol_info, 'spread', 0) * getattr(
            symbol_info, 'point', 0.00001)

        safety_margin = max(min_stop_level, spread * 2,
                            0.0001)  # Minimum safety margin

        if tp_price > 0:
            tp_distance = abs(tp_price - current_price)
            if tp_distance < safety_margin:
                return False, f"TP too close: {tp_distance:.5f} < {safety_margin:.5f}"

        if sl_price > 0:
            sl_distance = abs(sl_price - current_price)
            if sl_distance < safety_margin:
                return False, f"SL too close: {sl_distance:.5f} < {safety_margin:.5f}"

        if order_type == "BUY":
            if tp_price > 0 and tp_price <= current_price:
                return False, "BUY TP must be above current price"
            if sl_price > 0 and sl_price >= current_price:
                return False, "BUY SL must be below current price"
        else:
            if tp_price > 0 and tp_price >= current_price:
                return False, "SELL TP must be below current price"
            if sl_price > 0 and sl_price <= current_price:
                return False, "SELL SL must be above current price"

        return True, "Valid"

    except Exception as e:
        return False, f"Validation error: {str(e)}"


def validate_trading_conditions(symbol: str) -> Tuple[bool, str]:
    """Enhanced trading condition validation"""
    try:
        if not check_mt5_status():
            return False, "MT5 not connected"

        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return False, f"Symbol {symbol} not found"

        if not symbol_info.visible:
            if not mt5.symbol_select(symbol, True):
                return False, f"Cannot activate {symbol}"
            time.sleep(0.1)

        trade_mode = getattr(symbol_info, 'trade_mode', None)
        if trade_mode == mt5.SYMBOL_TRADE_MODE_DISABLED:
            return False, f"Trading disabled for {symbol}"

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return False, f"Cannot get tick data for {symbol}"

        spread = abs(tick.ask - tick.bid)
        max_spread = 0.001 if "JPY" in symbol else 0.0001
        if spread > max_spread:
            logger(f"⚠️ High spread detected: {spread:.5f}")

        return True, "Valid"

    except Exception as e:
        return False, f"Validation error: {str(e)}"


def execute_trade_signal(symbol: str, action: str) -> bool:
    """Enhanced trade execution based on signals"""
    try:
        is_valid, error_msg = validate_trading_conditions(symbol)
        if not is_valid:
            logger(f"❌ Cannot trade {symbol}: {error_msg}")
            return False

        if not gui:
            logger("❌ GUI not available")
            return False

        lot = gui.get_current_lot()
        tp_input = gui.get_current_tp()
        sl_input = gui.get_current_sl()
        tp_unit = gui.get_current_tp_unit()
        sl_unit = gui.get_current_sl_unit()

        # Set defaults if empty
        if not tp_input or tp_input == "0":
            tp_input = {
                "Scalping": "15",
                "HFT": "8",
                "Intraday": "50",
                "Arbitrage": "25"
            }.get(current_strategy, "20")
            tp_unit = "pips"

        if not sl_input or sl_input == "0":
            sl_input = {
                "Scalping": "8",
                "HFT": "4",
                "Intraday": "25",
                "Arbitrage": "10"
            }.get(current_strategy, "10")
            sl_unit = "pips"

        logger(f"🎯 Executing {action} signal for {symbol}")

        result = open_order(symbol, lot, action, sl_input, tp_input, sl_unit,
                            tp_unit)

        if result and getattr(result, 'retcode',
                              None) == mt5.TRADE_RETCODE_DONE:
            logger(f"✅ {action} order executed successfully!")
            return True
        else:
            logger(f"❌ Failed to execute {action} order")
            return False

    except Exception as e:
        logger(f"❌ Error executing trade signal: {str(e)}")
        return False


def calculate_auto_lot_size(symbol: str,
                            sl_pips: float,
                            risk_percent: float = 1.0) -> float:
    """Calculate optimal lot size based on risk percentage"""
    try:
        if not check_mt5_status():
            logger("❌ Cannot calculate auto lot: MT5 not connected")
            return 0.01

        info = get_account_info()
        if not info:
            logger("❌ Cannot get account info for auto lot calculation")
            return 0.01

        balance = info['balance']
        risk_amount = balance * (risk_percent / 100)

        # Calculate pip value for 1 standard lot
        pip_value_per_lot = calculate_pip_value(symbol, 1.0)

        if pip_value_per_lot <= 0 or sl_pips <= 0:
            logger("❌ Invalid pip value or SL for auto lot calculation")
            return 0.01

        # Calculate required lot size
        calculated_lot = risk_amount / (sl_pips * pip_value_per_lot)

        # Get symbol constraints
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info:
            min_lot = getattr(symbol_info, "volume_min", 0.01)
            max_lot = getattr(symbol_info, "volume_max", 100.0)
            lot_step = getattr(symbol_info, "volume_step", 0.01)

            # Normalize to lot step
            calculated_lot = round(calculated_lot / lot_step) * lot_step
            calculated_lot = max(min_lot, min(calculated_lot, max_lot))
        else:
            calculated_lot = max(0.01, min(calculated_lot, 10.0))

        logger(
            f"💡 Auto-lot calculation: Risk {risk_percent}% = ${risk_amount:.2f} / {sl_pips} pips = {calculated_lot:.3f} lots"
        )
        return calculated_lot

    except Exception as e:
        logger(f"❌ Error calculating auto lot size: {str(e)}")
        return 0.01


def open_order(symbol: str,
                 lot: float,
                 action: str,
                 sl_input: str,
                 tp_input: str,
                 sl_unit: str = "pips",
                 tp_unit: str = "pips") -> Any:
    """Enhanced order execution with auto-lot sizing and improved risk management"""
    global position_count, session_data, last_trade_time

    with trade_lock:
        try:
            # Rate limiting
            current_time = time.time()
            if symbol in last_trade_time:
                if current_time - last_trade_time[symbol] < 3:
                    logger(f"⏱️ Rate limit active for {symbol}")
                    return None

            # Enhanced auto-lot sizing (optional feature)
            use_auto_lot = gui and hasattr(
                gui, 'auto_lot_var') and gui.auto_lot_var.get()
            if use_auto_lot and sl_input and sl_unit == "pips":
                try:
                    sl_pips = float(sl_input)
                    risk_percent = float(
                        gui.risk_percent_entry.get()) if hasattr(
                            gui, 'risk_percent_entry') else 1.0
                    auto_lot = calculate_auto_lot_size(symbol, sl_pips,
                                                       risk_percent)

                    logger(
                        f"🎯 Auto-lot sizing: {lot:.3f} → {auto_lot:.3f} (Risk: {risk_percent}%, SL: {sl_pips} pips)"
                    )
                    lot = auto_lot

                except Exception as auto_e:
                    logger(
                        f"⚠️ Auto-lot calculation failed, using manual lot: {str(auto_e)}"
                    )

            # Enhanced GUI parameter validation with proper error handling
            if not gui or not hasattr(gui, 'strategy_combo'):
                logger("⚠️ GUI not available, using default parameters")
                if not sl_input: sl_input = "10"
                if not tp_input: tp_input = "20"
                if lot <= 0: lot = 0.01
            else:
                # Get parameters with proper fallbacks and validation
                if not sl_input or sl_input.strip() == "":
                    sl_input = gui.get_current_sl() if hasattr(
                        gui, 'get_current_sl') else "10"
                if not tp_input or tp_input.strip() == "":
                    tp_input = gui.get_current_tp() if hasattr(
                        gui, 'get_current_tp') else "20"

                # Ensure lot is valid
                if lot <= 0:
                    lot = gui.get_current_lot() if hasattr(
                        gui, 'get_current_lot') else 0.01
                    logger(f"🔧 Invalid lot corrected to: {lot}")
            # Check position limits
            positions = get_positions()
            position_count = len(positions)

            if position_count >= max_positions:
                logger(f"⚠️ Max positions ({max_positions}) reached")
                return None

            # Enhanced symbol validation
            valid_symbol = validate_and_activate_symbol(symbol)
            if not valid_symbol:
                logger(f"❌ Cannot validate symbol {symbol}")
                return None
            symbol = valid_symbol  # Use the validated symbol

            # Get symbol info
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                logger(f"❌ Cannot get symbol info for {symbol}")
                return None

            # Get current tick with retry
            tick = None
            for attempt in range(3):
                tick = mt5.symbol_info_tick(symbol)
                if tick is not None and hasattr(tick, 'bid') and hasattr(tick, 'ask'):
                    if tick.bid > 0 and tick.ask > 0:
                        break
                time.sleep(0.1)

            if tick is None:
                logger(f"❌ Cannot get valid tick data for {symbol}")
                return None

            # Determine order type and price
            if action.upper() == "BUY":
                order_type = mt5.ORDER_TYPE_BUY
                price = tick.ask
            else:
                order_type = mt5.ORDER_TYPE_SELL
                price = tick.bid

            # Get session adjustments for lot sizing
            current_session = get_current_trading_session()
            session_adjustments = adjust_strategy_for_session(
                current_strategy,  # Use global current_strategy
                current_session)
            lot_multiplier = session_adjustments.get("lot_multiplier", 1.0)

            # Apply session-based lot adjustment
            adjusted_lot = lot * lot_multiplier
            logger(
                f"📊 Session lot adjustment: {lot} × {lot_multiplier} = {adjusted_lot}"
            )

            # Validate and normalize lot size
            min_lot = getattr(symbol_info, "volume_min", 0.01)
            max_lot = getattr(symbol_info, "volume_max", 100.0)
            lot_step = getattr(symbol_info, "volume_step", 0.01)

            if adjusted_lot < min_lot:
                adjusted_lot = min_lot
            elif adjusted_lot > max_lot:
                adjusted_lot = max_lot

            lot = round(adjusted_lot / lot_step) * lot_step
            logger(f"✅ Final lot size after validation: {lot}")

            # Calculate TP and SL using user-selected units
            point = getattr(symbol_info, "point", 0.00001)
            digits = getattr(symbol_info, "digits", 5)

            tp_price = 0.0
            sl_price = 0.0

            logger(
                f"🧮 Calculating TP/SL: TP={tp_input} {tp_unit}, SL={sl_input} {sl_unit}"
            )

            # Apply session adjustments to TP/SL
            tp_multiplier = session_adjustments.get("tp_multiplier", 1.0)
            sl_multiplier = session_adjustments.get("sl_multiplier", 1.0)

            # Parse TP dengan unit yang dipilih user + session adjustment
            if tp_input and tp_input.strip() and tp_input != "0":
                try:
                    # Apply session multiplier to TP input
                    adjusted_tp_input = str(float(tp_input) * tp_multiplier)
                    logger(
                        f"📊 Session TP adjustment: {tp_input} × {tp_multiplier} = {adjusted_tp_input}"
                    )

                    tp_price, tp_calc = parse_tp_sl_input(
                        adjusted_tp_input, tp_unit, symbol, lot, price,
                        action.upper(), True)
                    tp_price = round(tp_price, digits) if tp_price > 0 else 0.0

                    if tp_price > 0:
                        logger(
                            f"✅ TP calculated: {tp_price:.5f} (from {tp_input} {tp_unit} adjusted to {adjusted_tp_input})"
                        )
                        if 'amount' in tp_calc:
                            logger(
                                f"   Expected TP profit: ${tp_calc['amount']:.2f}"
                            )
                    else:
                        logger(f"⚠️ TP calculation resulted in 0, skipping TP")

                except Exception as e:
                    logger(
                        f"❌ Error parsing TP {tp_input} {tp_unit}: {str(e)}")
                    tp_price = 0.0

            # Parse SL dengan unit yang dipilih user + session adjustment
            if sl_input and sl_input.strip() and sl_input != "0":
                try:
                    # Apply session multiplier to SL input
                    adjusted_sl_input = str(float(sl_input) * sl_multiplier)
                    logger(
                        f"📊 Session SL adjustment: {sl_input} × {sl_multiplier} = {adjusted_sl_input}"
                    )

                    sl_price, sl_calc = parse_tp_sl_input(
                        adjusted_sl_input, sl_unit, symbol, lot, price,
                        action.upper(), False)
                    sl_price = round(sl_price, digits) if sl_price > 0 else 0.0

                    if sl_price > 0:
                        logger(
                            f"✅ SL calculated: {sl_price:.5f} (from {sl_input} {sl_unit} adjusted to {adjusted_sl_input})"
                        )
                        if 'amount' in sl_calc:
                            logger(
                                f"   Expected SL loss: ${sl_calc['amount']:.2f}"
                            )
                    else:
                        logger(f"⚠️ SL calculation resulted in 0, skipping SL")

                except Exception as e:
                    logger(
                        f"❌ Error parsing SL {sl_input} {sl_unit}: {str(e)}")
                    sl_price = 0.0

            # Log final TP/SL values before order
            if tp_price > 0 or sl_price > 0:
                logger(
                    f"📋 Final order levels: Entry={price:.5f}, TP={tp_price:.5f}, SL={sl_price:.5f}"
                )
            else:
                logger(f"📋 Order without TP/SL: Entry={price:.5f}")

            # Validasi TP/SL levels sebelum submit order
            is_valid, error_msg = validate_tp_sl_levels(
                symbol, tp_price, sl_price, action.upper(), price)
            if not is_valid:
                logger(f"❌ Order validation failed: {error_msg}")
                return None

            # Create order request
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": lot,
                "type": order_type,
                "price": price,
                "deviation": 50,
                "magic": 123456,
                "comment": "AutoBotCuan",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            if sl_price > 0:
                request["sl"] = sl_price
            if tp_price > 0:
                request["tp"] = tp_price

            # Execute order with enhanced error handling
            logger(f"🔄 Sending {action} order for {symbol}")

            try:
                result = mt5.order_send(request)

                if result is None:
                    logger(f"❌ Order send returned None")
                    mt5_error = mt5.last_error()
                    logger(f"🔍 MT5 Error: {mt5_error}")
                    return None

            except Exception as order_exception:
                logger(
                    f"❌ Critical error sending order: {str(order_exception)}")
                return None

            # Process order result
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                logger(f"❌ Order failed: {result.retcode} - {result.comment}")

                # Retry without SL/TP for specific error codes
                invalid_stops_codes = [
                    10016, 10017, 10018, 10019, 10020, 10021
                ]  # Invalid stops/TP/SL codes
                if result.retcode in invalid_stops_codes:
                    logger("⚠️ Retrying without SL/TP...")
                    request.pop("sl", None)
                    request.pop("tp", None)
                    try:
                        result = mt5.order_send(request)

                        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                            logger(
                                f"✅ Order successful without SL/TP: {result.order}"
                            )
                        else:
                            logger(
                                f"❌ Retry failed: {result.comment if result else 'No result'}"
                            )
                            return None
                    except Exception as retry_exception:
                        logger(
                            f"❌ Critical error during retry: {str(retry_exception)}")
                        return None
                else:
                    return None

            # Order successful
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                last_trade_time[symbol] = current_time
                position_count += 1
                session_data['total_trades'] += 1
                session_data['daily_orders'] += 1

                # Update last balance for profit tracking
                info = get_account_info()
                if info:
                    session_data['last_balance'] = info['balance']
                    session_data['session_equity'] = info['equity']

                logger(f"✅ {action.upper()} order executed successfully!")
                logger(f"📊 Ticket: {result.order} | Price: {price:.5f}")

                # Log to CSV
                trade_data = {
                    "time":
                    datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "symbol": symbol,
                    "type": action.upper(),
                    "lot": lot,
                    "sl": sl_price if sl_price > 0 else 0,
                    "tp": tp_price if tp_price > 0 else 0,
                    "profit": 0,
                }

                log_filename = "logs/buy.csv" if action.upper(
                ) == "BUY" else "logs/sell.csv"
                if not os.path.exists("logs"):
                    os.makedirs("logs")

                log_order_csv(log_filename, trade_data)

                # Telegram notification
                if gui and hasattr(gui,
                                   'telegram_var') and gui.telegram_var.get():
                    msg = f"🟢 {action.upper()} Order Executed\nSymbol: {symbol}\nLot: {lot}\nPrice: {price:.5f}\nTicket: {result.order}"
                    send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, msg)

                return result
            else:
                logger(f"❌ Order execution failed: {result.comment}")
                return None

        except Exception as e:
            error_msg = f"❌ Critical error in order execution: {str(e)}"
            logger(error_msg)
            return None


def log_order_csv(filename: str, order: Dict[str, Any]) -> None:
    """Enhanced CSV logging"""
    try:
        fieldnames = ["time", "symbol", "type", "lot", "sl", "tp", "profit"]
        file_exists = os.path.isfile(filename)
        with open(filename, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(order)
    except Exception as e:
        logger(f"❌ Error logging to CSV: {str(e)}")


def close_all_orders(symbol: str = None) -> None:
    """Enhanced close all orders"""
    try:
        if not check_mt5_status():
            logger("❌ MT5 not connected")
            return

        positions = mt5.positions_get(
            symbol=symbol) if symbol else mt5.positions_get()
        if not positions:
            logger("ℹ️ No positions to close")
            return

        closed_count = 0
        total_profit = 0.0
        failed_count = 0

        for position in positions:
            try:
                tick = mt5.symbol_info_tick(position.symbol)
                if tick is None:
                    failed_count += 1
                    continue

                order_type = mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
                price = tick.bid if position.type == mt5.ORDER_TYPE_BUY else tick.ask

                close_request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "position": position.ticket,
                    "symbol": position.symbol,
                    "volume": position.volume,
                    "type": order_type,
                    "price": price,
                    "deviation": 20,
                    "magic": position.magic,
                    "comment": "AutoBot_CloseAll",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_IOC,
                }

                result = mt5.order_send(close_request)
                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                    logger(
                        f"✅ Position {position.ticket} closed - Profit: ${position.profit:.2f}"
                    )
                    closed_count += 1
                    total_profit += position.profit
                    session_data['daily_profit'] += position.profit
                    session_data['total_profit'] += position.profit

                    if position.profit > 0:
                        session_data['winning_trades'] += 1
                        logger(
                            f"🎯 Winning trade #{session_data['winning_trades']}"
                        )
                    else:
                        session_data['losing_trades'] += 1
                        logger(
                            f"❌ Losing trade #{session_data['losing_trades']}")

                    # Update account info for GUI
                    info = get_account_info()
                    if info:
                        session_data['session_equity'] = info['equity']
                else:
                    logger(f"❌ Failed to close {position.ticket}")
                    failed_count += 1

            except Exception as e:
                logger(f"❌ Error closing position: {str(e)}")
                failed_count += 1

        if closed_count > 0:
            logger(
                f"🔄 Closed {closed_count} positions. Total Profit: ${total_profit:.2f}"
            )

    except Exception as e:
        logger(f"❌ Error closing orders: {str(e)}")


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Enhanced indicator calculation with strategy-specific optimizations for higher winrate"""
    try:
        if len(df) < 50:
            logger("⚠️ Insufficient data for indicators calculation")
            return df

        # Core EMA indicators with optimized periods for each strategy
        df['EMA5'] = df['close'].ewm(span=5, adjust=False).mean()
        df['EMA8'] = df['close'].ewm(span=8, adjust=False).mean()  # Additional EMA for better signals
        df['EMA13'] = df['close'].ewm(span=13, adjust=False).mean()
        df['EMA20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['EMA50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['EMA100'] = df['close'].ewm(span=100, adjust=False).mean()
        df['EMA200'] = df['close'].ewm(span=200, adjust=False).mean()

        # Enhanced EMA slope calculation for trend strength
        df['EMA5_Slope'] = df['EMA5'].diff(3)  # 3-period slope
        df['EMA13_Slope'] = df['EMA13'].diff(3)
        df['EMA_Momentum'] = (df['EMA5'] - df['EMA13']) / df['EMA13'] * 100

        # RSI untuk scalping (period 7 dan 9)
        df['RSI7'] = rsi(df['close'], 7)
        df['RSI9'] = rsi(df['close'], 9)
        df['RSI14'] = rsi(df['close'], 14)
        df['RSI'] = df['RSI9']  # Default menggunakan RSI9 untuk scalping
        df['RSI_Smooth'] = df['RSI'].rolling(
            window=3).mean()  # Add missing RSI_Smooth

        # MACD untuk konfirmasi
        df['MACD'], df['MACD_signal'], df['MACD_histogram'] = macd_enhanced(
            df['close'])

        # Moving Averages tambahan
        df['MA5'] = df['close'].rolling(window=5).mean()
        df['MA10'] = df['close'].rolling(window=10).mean()
        df['MA20'] = df['close'].rolling(window=20).mean()

        # WMA (Weighted Moving Average) - Key for price action
        def wma(series, period):
            weights = np.arange(1, period + 1)
            return series.rolling(period).apply(
                lambda x: np.dot(x, weights) / weights.sum(), raw=True)

        df['WMA5_High'] = wma(df['high'], 5)
        df['WMA5_Low'] = wma(df['low'], 5)
        df['WMA10_High'] = wma(df['high'], 10)
        df['WMA10_Low'] = wma(df['low'], 10)

        # Bollinger Bands
        df['BB_Middle'] = df['close'].rolling(window=20).mean()
        bb_std = df['close'].rolling(window=20).std()
        df['BB_Upper'] = df['BB_Middle'] + 2 * bb_std
        df['BB_Lower'] = df['BB_Middle'] - 2 * bb_std
        df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / df['BB_Middle']

        # Stochastic
        df['STOCH_K'], df['STOCH_D'] = stochastic_enhanced(df)

        # ATR
        df['ATR'] = atr(df, 14)
        df['ATR_Ratio'] = df['ATR'] / df['ATR'].rolling(window=20).mean()

        # EMA Crossover Signals untuk Scalping
        df['EMA5_Cross_Above_EMA13'] = (
            (df['EMA5'] > df['EMA13']) &
            (df['EMA5'].shift(1) <= df['EMA13'].shift(1)))
        df['EMA5_Cross_Below_EMA13'] = (
            (df['EMA5'] < df['EMA13']) &
            (df['EMA5'].shift(1) >= df['EMA13'].shift(1)))

        # EMA20/50 Crossover untuk Intraday
        df['EMA20_Cross_Above_EMA50'] = (
            (df['EMA20'] > df['EMA50']) &
            (df['EMA20'].shift(1) <= df['EMA50'].shift(1)))
        df['EMA20_Cross_Below_EMA50'] = (
            (df['EMA20'] < df['EMA50']) &
            (df['EMA20'].shift(1) >= df['EMA50'].shift(1)))

        # RSI Conditions untuk scalping (80/20 levels)
        df['RSI_Oversold_Recovery'] = ((df['RSI'] > 20) &
                                       (df['RSI'].shift(1) <= 20))
        df['RSI_Overbought_Decline'] = ((df['RSI'] < 80) &
                                        (df['RSI'].shift(1) >= 80))

        # Enhanced Price Action Patterns
        df['Bullish_Engulfing'] = (
            (df['close'] > df['open']) &
            (df['close'].shift(1) < df['open'].shift(1)) &
            (df['open'] < df['close'].shift(1)) &
            (df['close'] > df['open'].shift(1)) &
            (df['volume'] > df['volume'].shift(1) * 1.2)  # Volume confirmation
        )

        df['Bearish_Engulfing'] = (
            (df['close'] < df['open']) &
            (df['close'].shift(1) > df['open'].shift(1)) &
            (df['open'] > df['close'].shift(1)) &
            (df['close'] < df['open'].shift(1)) &
            (df['volume'] > df['volume'].shift(1) * 1.2)  # Volume confirmation
        )

        # Breakout patterns
        df['Bullish_Breakout'] = (
            (df['close'] > df['high'].rolling(window=20).max().shift(1)) &
            (df['close'] > df['WMA5_High']) & (df['close'] > df['BB_Upper']))

        df['Bearish_Breakout'] = (
            (df['close'] < df['low'].rolling(window=20).min().shift(1)) &
            (df['close'] < df['WMA5_Low']) & (df['close'] < df['BB_Lower']))

        # Strong candle detection
        df['Candle_Size'] = abs(df['close'] - df['open'])
        df['Avg_Candle_Size'] = df['Candle_Size'].rolling(window=20).mean()
        df['Strong_Bullish_Candle'] = (
            (df['close'] > df['open']) &
            (df['Candle_Size'] > df['Avg_Candle_Size'] * 1.5))
        df['Strong_Bearish_Candle'] = (
            (df['close'] < df['open']) &
            (df['Candle_Size'] > df['Avg_Candle_Size'] * 1.5))

        # Trend indicators
        df['Higher_High'] = (df['high'] > df['high'].shift(1)) & (
            df['high'].shift(1) > df['high'].shift(2))
        df['Lower_Low'] = (df['low'] < df['low'].shift(1)) & (
            df['low'].shift(1) < df['low'].shift(2))
        df['Trend_Strength'] = abs(df['EMA20'] - df['EMA50']) / df['ATR']

        # Momentum
        df['Momentum'] = df['close'] - df['close'].shift(10)
        df['ROC'] = ((df['close'] - df['close'].shift(10)) /
                     df['close'].shift(10)) * 100

        # Support/Resistance
        df['Support'] = df['low'].rolling(window=20).min()
        df['Resistance'] = df['high'].rolling(window=20).max()

        # Market structure
        df['Bullish_Structure'] = ((df['EMA20'] > df['EMA50']) &
                                   (df['close'] > df['EMA20']) &
                                   (df['MACD'] > df['MACD_signal']))
        df['Bearish_Structure'] = ((df['EMA20'] < df['EMA50']) &
                                   (df['close'] < df['EMA20']) &
                                   (df['MACD'] < df['MACD_signal']))

        # Tick data untuk HFT
        df['Price_Change'] = df['close'].diff()
        df['Volume_Burst'] = df['volume'] > df['volume'].rolling(
            window=5).mean() * 2

        return df
    except Exception as e:
        logger(f"❌ Error calculating indicators: {str(e)}")
        return df


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """RSI calculation"""
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.rolling(window=period, min_periods=1).mean()
    avg_loss = loss.rolling(window=period, min_periods=1).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def macd_enhanced(series: pd.Series,
                  fast: int = 12,
                  slow: int = 26,
                  signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Enhanced MACD calculation"""
    exp1 = series.ewm(span=fast, adjust=False).mean()
    exp2 = series.ewm(span=slow, adjust=False).mean()
    macd_line = exp1 - exp2
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def stochastic_enhanced(df: pd.DataFrame,
                        k_period: int = 14,
                        d_period: int = 3) -> Tuple[pd.Series, pd.Series]:
    """Enhanced Stochastic Oscillator"""
    low_min = df['low'].rolling(window=k_period).min()
    high_max = df['high'].rolling(window=k_period).max()
    k = 100 * ((df['close'] - low_min) / (high_max - low_min))
    d = k.rolling(window=d_period).mean()
    return k, d


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate ATR with enhanced error handling"""
    try:
        if len(df) < period:
            return pd.Series([0.0008] * len(df), index=df.index)

        high = df['high']
        low = df['low']
        close = df['close']

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()

        return atr.fillna(0.0008)
    except Exception as e:
        logger(f"❌ Error calculating ATR: {str(e)}")
        return pd.Series([0.0008] * len(df), index=df.index)


def run_strategy(strategy: str, df: pd.DataFrame,
                   symbol: str) -> Tuple[Optional[str], List[str]]:
    """Enhanced strategy execution with precise price analysis and validation"""
    try:
        if len(df) < 50:
            logger(f"❌ Insufficient data for {symbol}: {len(df)} bars (need 50+)")
            return None, [f"Insufficient data: {len(df)} bars"]

        # Get precision info from dataframe attributes or MT5
        digits = df.attrs.get('digits', 5)
        point = df.attrs.get('point', 0.00001)

        # Get real-time tick data dengan retry mechanism
        current_tick = None
        for tick_attempt in range(3):
            current_tick = mt5.symbol_info_tick(symbol)
            if current_tick and hasattr(current_tick, 'bid') and hasattr(current_tick, 'ask'):
                if current_tick.bid > 0 and current_tick.ask > 0:
                    break
            else:
                logger(f"⚠️ Tick attempt {tick_attempt + 1}: No valid tick for {symbol}")
                time.sleep(0.5)

        if not current_tick or not hasattr(current_tick, 'bid') or current_tick.bid <= 0:
            logger(f"❌ Cannot get valid real-time tick for {symbol} after 3 attempts")
            return None, [f"No valid tick data for {symbol}"]

        # Use most recent candle data
        last = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3] if len(df) > 3 else prev

        # Get precise current prices - MUST be defined early for all strategies
        current_bid = round(current_tick.bid, digits)
        current_ask = round(current_tick.ask, digits)
        current_spread = round(current_ask - current_bid, digits)
        current_price = round((current_bid + current_ask) / 2, digits)

        # Validate price precision
        last_close = round(last['close'], digits)
        last_high = round(last['high'], digits)
        last_low = round(last['low'], digits)
        last_open = round(last['open'], digits)

        action = None
        signals = []
        buy_signals = 0
        sell_signals = 0

        # Enhanced price logging with precision
        logger(f"📊 {symbol} Precise Data:")
        logger(f"   📈 Candle: O={last_open:.{digits}f} H={last_high:.{digits}f} L={last_low:.{digits}f} C={last_close:.{digits}f}")
        logger(f"   🎯 Real-time: Bid={current_bid:.{digits}f} Ask={current_ask:.{digits}f} Spread={current_spread:.{digits}f}")
        logger(f"   💡 Current Price: {current_price:.{digits}f} (Mid-price)")

        # Price movement analysis with precise calculations
        price_change = round(current_price - last_close, digits)
        price_change_pips = abs(price_change) / point

        logger(f"   📊 Price Movement: {price_change:+.{digits}f} ({price_change_pips:.1f} pips)")

        # Enhanced spread quality check with proper symbol-specific calculation
        if any(precious in symbol for precious in ["XAU", "XAG", "GOLD", "SILVER"]):
            # For precious metals, use symbol-specific point value
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info:
                point_value = getattr(symbol_info, 'point', 0.01)
                spread_pips = current_spread / point_value
                # Gold typically has 10-40 pip spreads normally
                max_allowed_spread = 100.0  # More realistic for gold
            else:
                # Fallback for gold if symbol_info fails
                spread_pips = current_spread / 0.01  # Assume 0.01 point for gold
                max_allowed_spread = 100.0
        elif "JPY" in symbol:
            spread_pips = current_spread / 0.01
            max_allowed_spread = 8.0  # JPY pairs
        else:
            spread_pips = current_spread / 0.0001
            max_allowed_spread = 5.0  # Major forex pairs

        spread_quality = "EXCELLENT" if spread_pips < max_allowed_spread * 0.3 else "GOOD" if spread_pips < max_allowed_spread * 0.6 else "FAIR" if spread_pips < max_allowed_spread * 0.8 else "POOR"

        logger(f"   🎯 Spread Analysis: {spread_pips:.1f} pips ({spread_quality}) | Max: {max_allowed_spread}")

        # More lenient spread filtering - only skip if extremely wide
        if spread_pips > max_allowed_spread:
            logger(f"⚠️ Spread too wide ({spread_pips:.1f} pips > {max_allowed_spread}) - reducing targets")
            spread_warning = True
        else:
            spread_warning = False

        # AI Market Analysis Integration
        ai_analysis = ai_market_analysis(symbol, df)
        logger(f"🤖 AI Analysis: {ai_analysis['recommendation']} (Confidence: {ai_analysis['confidence']}%)")

        # Get current trading session and adjustments
        current_session = get_current_trading_session()
        session_adjustments = adjust_strategy_for_session(
            strategy, current_session)

        # Check if high-impact news time
        is_news_time = is_high_impact_news_time()
        if is_news_time:
            logger("⚠️ High-impact news time - applying conservative filters")
            session_adjustments["signal_threshold_modifier"] += 2

        action = None
        signals = []
        buy_signals = 0
        sell_signals = 0

        # Enhanced price logging with precision
        logger(f"📊 {symbol} Precise Data:")
        logger(f"   📈 Candle: O={last_open:.{digits}f} H={last_high:.{digits}f} L={last_low:.{digits}f} C={last_close:.{digits}f}")
        logger(f"   🎯 Real-time: Bid={current_bid:.{digits}f} Ask={current_ask:.{digits}f} Spread={current_spread:.{digits}f}")
        logger(f"   💡 Current Price: {current_price:.{digits}f} (Mid-price)")

        # Price movement analysis with precise calculations
        price_change = round(current_price - last_close, digits)
        price_change_pips = abs(price_change) / point

        logger(f"   📊 Price Movement: {price_change:+.{digits}f} ({price_change_pips:.1f} pips)")

        # Debug: Log key indicator values
        logger(f"🔍 Key Indicators:")
        if 'EMA5' in last:
            logger(
                f"   EMA5: {last['EMA5']:.5f}, EMA13: {last['EMA13']:.5f}, EMA50: {last['EMA50']:.5f}"
            )
        if 'RSI' in last:
            logger(
                f"   RSI: {last['RSI']:.1f}, RSI7: {last.get('RSI7', 0):.1f}")
        if 'MACD' in last:
            logger(
                f"   MACD: {last['MACD']:.5f}, Signal: {last['MACD_signal']:.5f}, Hist: {last['MACD_histogram']:.5f}"
            )

        if strategy == "Scalping":
            # Ultra-precise scalping with multi-confirmation system for higher winrate
            logger("⚡ Scalping: Multi-confirmation EMA system with momentum filters...")

            # Get precise EMA values with enhanced calculations
            ema5_current = round(last.get('EMA5', current_price), digits)
            ema8_current = round(last.get('EMA8', current_price), digits)
            ema13_current = round(last.get('EMA13', current_price), digits)
            ema50_current = round(last.get('EMA50', current_price), digits)

            ema5_prev = round(prev.get('EMA5', current_price), digits)
            ema8_prev = round(prev.get('EMA8', current_price), digits)
            ema13_prev = round(prev.get('EMA13', current_price), digits)

            # Enhanced momentum calculation
            ema_momentum = last.get('EMA_Momentum', 0)
            ema5_slope = last.get('EMA5_Slope', 0)
            ema13_slope = last.get('EMA13_Slope', 0)

            # Multi-EMA alignment check (5>8>13 for bullish, 5<8<13 for bearish)
            bullish_alignment = ema5_current > ema8_current > ema13_current
            bearish_alignment = ema5_current < ema8_current < ema13_current

            logger(f"🔍 Enhanced Scalping EMAs: 5={ema5_current:.{digits}f}, 8={ema8_current:.{digits}f}, 13={ema13_current:.{digits}f}")
            logger(f"📈 Momentum: {ema_momentum:.3f}, Slope5: {ema5_slope:.{digits}f}")

            logger(f"🔍 Scalping EMAs: EMA5={ema5_current:.{digits}f}, EMA13={ema13_current:.{digits}f}, EMA50={ema50_current:.{digits}f}")

            # PRECISE CROSSOVER DETECTION with better thresholds
            min_cross_threshold = point * 5 if any(precious in symbol for precious in ["XAU", "GOLD"]) else point * 2

            ema5_cross_up = (ema5_current > ema13_current and ema5_prev <= ema13_prev and
                           abs(ema5_current - ema13_current) >= min_cross_threshold)
            ema5_cross_down = (ema5_current < ema13_current and ema5_prev >= ema13_prev and
                             abs(ema5_current - ema13_current) >= min_cross_threshold)

            # Enhanced trend confirmation with precise levels
            trend_bullish = (ema5_current > ema13_current > ema50_current and
                           current_price > ema50_current)
            trend_bearish = (ema5_current < ema13_current < ema50_current and
                           current_price < ema50_current)

            # Precise price action confirmation
            candle_body = abs(last_close - last_open)
            candle_range = last_high - last_low
            candle_body_ratio = candle_body / max(candle_range, point) if candle_range > 0 else 0

            bullish_candle = last_close > last_open and candle_body_ratio > 0.3
            bearish_candle = last_close < last_open and candle_body_ratio > 0.3

            logger(f"🕯️ Candle Analysis: Body={candle_body:.{digits}f}, Ratio={candle_body_ratio:.2f}")

            # Enhanced volatility filter with ATR
            atr_current = last.get('ATR', point * 10)
            atr_ratio = last.get('ATR_Ratio', 1.0)
            volatility_ok = atr_ratio > 0.5 and atr_current > point * 3  # More lenient for gold

            # Precise RSI analysis
            rsi_value = last.get('RSI', 50)
            rsi7_value = last.get('RSI7', 50)
            rsi_bullish = 35 < rsi_value < 75  # Optimal range for scalping
            rsi_bearish = 25 < rsi_value < 65

            logger(f"📊 RSI Analysis: RSI={rsi_value:.1f}, RSI7={rsi7_value:.1f}")

            # Precise BUY SIGNALS with proper distance validation
            if ema5_cross_up and spread_quality in ["EXCELLENT", "GOOD", "FAIR"]:
                if trend_bullish and bullish_candle and volatility_ok:
                    if rsi_value < 30 and rsi_value > prev.get('RSI', 50):  # RSI recovery
                        buy_signals += 8
                        signals.append(f"✅ SCALP STRONG: Precise EMA cross UP + RSI recovery @ {current_price:.{digits}f}")
                    elif rsi_bullish and current_price > ema50_current:
                        buy_signals += 6
                        signals.append(f"✅ SCALP: Precise EMA cross UP + trend @ {current_price:.{digits}f}")
                elif volatility_ok and rsi_bullish:
                    buy_signals += 4
                    signals.append(f"✅ SCALP: EMA cross UP + basic conditions @ {current_price:.{digits}f}")

            # Price above EMA5 continuation with precise conditions
            elif (current_price > ema5_current and ema5_current > ema13_current and
                  current_price > last_high * 0.999):  # More lenient
                if (rsi_value > 50 and last.get('MACD_histogram', 0) > prev.get('MACD_histogram', 0)):
                    buy_signals += 5
                    signals.append(f"✅ SCALP: Precise uptrend continuation @ {current_price:.{digits}f}")
                elif current_price > ema50_current:
                    buy_signals += 3
                    signals.append(f"✅ SCALP: Basic uptrend @ {current_price:.{digits}f}")

            # PRECISE SELL SIGNALS with proper distance validation
            if ema5_cross_down and spread_quality in ["EXCELLENT", "GOOD", "FAIR"]:
                if trend_bearish and bearish_candle and volatility_ok:
                    if rsi_value > 70 and rsi_value < prev.get('RSI', 50):  # RSI decline
                        sell_signals += 8
                        signals.append(f"✅ SCALP STRONG: Precise EMA cross DOWN + RSI decline @ {current_price:.{digits}f}")
                    elif rsi_bearish and current_price < ema50_current:
                        sell_signals += 6
                        signals.append(f"✅ SCALP: Precise EMA cross DOWN + trend @ {current_price:.{digits}f}")
                elif volatility_ok and rsi_bearish:
                    sell_signals += 4
                    signals.append(f"✅ SCALP: EMA cross DOWN + basic conditions @ {current_price:.{digits}f}")

            # Price below EMA5 continuation with precise conditions
            elif (current_price < ema5_current and ema5_current < ema13_current and
                  current_price < last_low * 1.001):  # More lenient
                if (rsi_value < 50 and last.get('MACD_histogram', 0) < prev.get('MACD_histogram', 0)):
                    sell_signals += 5
                    signals.append(f"✅ SCALP: Precise downtrend continuation @ {current_price:.{digits}f}")
                elif current_price < ema50_current:
                    sell_signals += 3
                    signals.append(f"✅ SCALP: Basic downtrend @ {current_price:.{digits}f}")

            # KONFIRMASI TAMBAHAN: RSI Extreme Levels (80/20)
            if last.get('RSI', 50) < 25:  # More lenient oversold
                buy_signals += 2
                signals.append(f"✅ SCALP: RSI oversold ({last.get('RSI', 50):.1f})")
            elif last.get('RSI', 50) > 75:  # More lenient overbought
                sell_signals += 2
                signals.append(f"✅ SCALP: RSI overbought ({last.get('RSI', 50):.1f})")

            # KONFIRMASI MOMENTUM: MACD Histogram
            if (last.get('MACD_histogram', 0) > 0 and
                    last.get('MACD_histogram', 0) > prev.get('MACD_histogram', 0)):
                buy_signals += 2
                signals.append("✅ SCALP: MACD momentum bullish")
            elif (last.get('MACD_histogram', 0) < 0 and
                  last.get('MACD_histogram', 0) < prev.get('MACD_histogram', 0)):
                sell_signals += 2
                signals.append("✅ SCALP: MACD momentum bearish")

            # PRICE ACTION: Strong candle dengan EMA konfirmasi
            if (last.get('Strong_Bullish_Candle', False) and ema5_current > ema13_current):
                buy_signals += 2
                signals.append("✅ SCALP: Strong bullish candle + EMA alignment")
            elif (last.get('Strong_Bearish_Candle', False) and ema5_current < ema13_current):
                sell_signals += 2
                signals.append("✅ SCALP: Strong bearish candle + EMA alignment")

            # KONFIRMASI VOLUME (jika tersedia)
            volume_avg = df['volume'].rolling(window=10).mean().iloc[-1] if 'volume' in df else 1
            current_volume = last.get('volume', 1)
            if current_volume > volume_avg * 1.3:
                if ema5_current > ema13_current:
                    buy_signals += 1
                    signals.append("✅ SCALP: High volume confirmation bullish")
                elif ema5_current < ema13_current:
                    sell_signals += 1
                    signals.append("✅ SCALP: High volume confirmation bearish")

        elif strategy == "HFT":
            # Enhanced HFT: Precise tick-level analysis
            logger("⚡ HFT: Precise tick-level analysis with micro-second accuracy...")

            # Get precise tick movement data
            tick_time = current_tick.time
            last_tick_time = getattr(current_tick, 'time_msc', tick_time * 1000) / 1000

            # Calculate precise movement since last candle
            tick_vs_candle_change = round(current_price - last_close, digits)
            tick_vs_candle_pips = abs(tick_vs_candle_change) / point

            logger(f"🔬 HFT Tick Analysis:")
            logger(f"   📊 Tick vs Candle: {tick_vs_candle_change:+.{digits}f} ({tick_vs_candle_pips:.2f} pips)")
            logger(f"   🎯 Spread: {spread_pips:.2f} pips ({spread_quality})")

            # Optimal HFT movement range (0.1-3 pips for fastest execution)
            optimal_movement = 0.1 <= tick_vs_candle_pips <= 3.0

            # Micro-acceleration detection with precise calculation
            prev_tick_change = round(last_close - prev['close'], digits)
            acceleration_ratio = abs(tick_vs_candle_change) / max(abs(prev_tick_change), point)
            has_acceleration = acceleration_ratio > 1.5

            logger(f"   ⚡ Acceleration Ratio: {acceleration_ratio:.2f}")

            # Enhanced volume analysis for HFT
            tick_volume_current = last.get('tick_volume', 1)
            tick_volume_avg = df['tick_volume'].rolling(5).mean().iloc[-1] if 'tick_volume' in df else 1
            volume_surge = tick_volume_current > tick_volume_avg * 2.0

            # Precise EMA micro-analysis - define missing variables
            ema5_current = round(last.get('EMA5', current_price), digits)
            ema5_prev = round(prev.get('EMA5', current_price), digits)
            ema5_slope = round(ema5_current - ema5_prev, digits)
            ema5_acceleration = abs(ema5_slope) > point * 2

            logger(f"   📈 EMA5 Slope: {ema5_slope:+.{digits}f} pips, Acceleration: {ema5_acceleration}")

            # HFT Signal 1: Precise micro-momentum with ultra-tight conditions
            if optimal_movement and spread_quality == "EXCELLENT":  # Only excellent spreads
                if tick_vs_candle_change > 0 and current_bid > last_close:  # Clear bullish movement
                    if has_acceleration and volume_surge and ema5_acceleration:
                        buy_signals += 8
                        signals.append(f"✅ HFT ULTRA: Micro-momentum UP {tick_vs_candle_pips:.2f} pips + acceleration + volume @ {current_bid:.{digits}f}")
                    elif ema5_slope > 0 and current_price > ema5_current:
                        buy_signals += 6
                        signals.append(f"✅ HFT STRONG: Micro-trend UP {tick_vs_candle_pips:.2f} pips @ {current_bid:.{digits}f}")
                    elif optimal_movement:
                        buy_signals += 4
                        signals.append(f"✅ HFT: Basic momentum UP {tick_vs_candle_pips:.2f} pips @ {current_bid:.{digits}f}")

                elif tick_vs_candle_change < 0 and current_ask < last_close:  # Clear bearish movement
                    if has_acceleration and volume_surge and ema5_acceleration:
                        sell_signals += 8
                        signals.append(f"✅ HFT ULTRA: Micro-momentum DOWN {tick_vs_candle_pips:.2f} pips + acceleration + volume @ {current_ask:.{digits}f}")
                    elif ema5_slope < 0 and current_price < ema5_current:
                        sell_signals += 6
                        signals.append(f"✅ HFT STRONG: Micro-trend DOWN {tick_vs_candle_pips:.2f} pips @ {current_ask:.{digits}f}")
                    elif optimal_movement:
                        sell_signals += 4
                        signals.append(f"✅ HFT: Basic momentum DOWN {tick_vs_candle_pips:.2f} pips @ {current_ask:.{digits}f}")

            # HFT Signal 2: Tick-level EMA5 precision crossing
            if ema5_tick_distance < point * 3:  # Very close to EMA5
                if current_price > ema5_current and ema5_slope > 0:
                    buy_signals += 5
                    signals.append(f"✅ HFT: EMA5 precision cross UP @ {current_price:.{digits}f}")
                elif current_price < ema5_current and ema5_slope < 0:
                    sell_signals += 5
                    signals.append(f"✅ HFT: EMA5 precision cross DOWN @ {current_price:.{digits}f}")

            # HFT Signal 3: Spread compression opportunity
            if spread_pips < 0.5:  # Ultra-tight spread
                candle_direction = 1 if last_close > last_open else -1
                tick_direction = 1 if current_price > last_close else -1

                if candle_direction == tick_direction == 1:
                    buy_signals += 3
                    signals.append(f"✅ HFT: Spread compression BUY ({spread_pips:.2f} pips) @ {current_bid:.{digits}f}")
                elif candle_direction == tick_direction == -1:
                    sell_signals += 3
                    signals.append(f"✅ HFT: Spread compression SELL ({spread_pips:.2f} pips) @ {current_ask:.{digits}f}")

            # HFT Signal 2: Bid/Ask spread tightening (market efficiency)
            try:
                tick = mt5.symbol_info_tick(symbol)
                if tick:
                    current_spread = tick.ask - tick.bid
                    avg_spread = df['high'].rolling(5).mean().iloc[-1] - df['low'].rolling(5).mean().iloc[-1]
                    if current_spread < avg_spread * 0.8:  # Spread tightening = liquidity
                        if last['close'] > prev['close']:
                            buy_signals += 3
                            signals.append("✅ HFT: Spread tightening + bullish")
                        elif last['close'] < prev['close']:
                            sell_signals += 3
                            signals.append("✅ HFT: Spread tightening + bearish")
            except:
                pass

            # HFT Signal 3: EMA5 micro-crossover (tick-level)
            if last['EMA5'] > prev['EMA5'] and prev['EMA5'] <= prev2.get('EMA5', prev['EMA5']):
                if last['close'] > last['EMA5']:
                    buy_signals += 4
                    signals.append("✅ HFT: EMA5 micro-trend UP")
            elif last['EMA5'] < prev['EMA5'] and prev['EMA5'] >= prev2.get('EMA5', prev['EMA5']):
                if last['close'] < last['EMA5']:
                    sell_signals += 4
                    signals.append("✅ HFT: EMA5 micro-trend DOWN")

            # HFT Signal 4: RSI extreme dengan recovery cepat (scalping overbought/oversold)
            if last['RSI7'] > 85 and (last['RSI7'] - prev['RSI7']) < -2:
                sell_signals += 3
                signals.append(f"✅ HFT: RSI extreme decline {last['RSI7']:.1f}")
            elif last['RSI7'] < 15 and (last['RSI7'] - prev['RSI7']) > 2:
                buy_signals += 3
                signals.append(f"✅ HFT: RSI extreme recovery {last['RSI7']:.1f}")

            # HFT Signal 5: Tick volume burst (institutional entry detection)
            tick_volume_current = last.get('tick_volume', 1)
            tick_volume_avg = df['tick_volume'].rolling(10).mean().iloc[-1] if 'tick_volume' in df else 1
            if tick_volume_current > tick_volume_avg * 2:
                if last['close'] > last['open']:
                    buy_signals += 2
                    signals.append("✅ HFT: Volume burst bullish")
                elif last['close'] < last['open']:
                    sell_signals += 2
                    signals.append("✅ HFT: Volume burst bearish")

        elif strategy == "Intraday":
            # Enhanced intraday with precise trend analysis and multi-timeframe confirmation
            logger("📈 Intraday: Precise trend analysis with real-time validation...")

            # Get precise EMA values for intraday analysis
            ema20_current = round(last.get('EMA20', current_price), digits)
            ema50_current = round(last.get('EMA50', current_price), digits)
            ema200_current = round(last.get('EMA200', current_price), digits)

            ema20_prev = round(prev.get('EMA20', current_price), digits)
            ema50_prev = round(prev.get('EMA50', current_price), digits)

            logger(f"📈 Intraday EMAs: EMA20={ema20_current:.{digits}f}, EMA50={ema50_current:.{digits}f}, EMA200={ema200_current:.{digits}f}")

            # Precise trend classification with minimum separation
            min_separation = point * 5  # Minimum 5 points between EMAs

            strong_uptrend = (ema20_current > ema50_current + min_separation > ema200_current + min_separation and
                            current_price > ema20_current)
            strong_downtrend = (ema20_current < ema50_current - min_separation < ema200_current - min_separation and
                              current_price < ema20_current)

            # Precise crossover detection with confirmation
            ema20_cross_up = (ema20_current > ema50_current and ema20_prev <= ema50_prev and
                            abs(ema20_current - ema50_current) >= min_separation)
            ema20_cross_down = (ema20_current < ema50_current and ema20_prev >= ema50_prev and
                              abs(ema20_current - ema50_current) >= min_separation)

            # Enhanced RSI with precise levels
            rsi14 = last.get('RSI14', 50)
            rsi_smooth = last.get('RSI_Smooth', rsi14)
            rsi_momentum_up = 40 < rsi14 < 80 and rsi14 > rsi_smooth  # Rising RSI
            rsi_momentum_down = 20 < rsi14 < 60 and rsi14 < rsi_smooth  # Falling RSI

            logger(f"📊 RSI Analysis: RSI14={rsi14:.1f}, RSI_Smooth={rsi_smooth:.1f}")

            # Precise MACD analysis
            macd_value = last.get('MACD', 0)
            macd_signal = last.get('MACD_signal', 0)
            macd_hist = last.get('MACD_histogram', 0)
            macd_hist_prev = prev.get('MACD_histogram', 0)

            macd_bullish = (macd_value > macd_signal and macd_hist > macd_hist_prev and macd_hist > 0)
            macd_bearish = (macd_value < macd_signal and macd_hist < macd_hist_prev and macd_hist < 0)

            # Enhanced volume analysis
            volume_current = last.get('volume', 1)
            volume_20 = df['volume'].rolling(20).mean().iloc[-1] if 'volume' in df else 1
            volume_50 = df['volume'].rolling(50).mean().iloc[-1] if 'volume' in df else 1

            volume_confirmation = volume_current > volume_20 * 1.2
            volume_surge = volume_current > volume_50 * 1.5

            # Precise candle analysis
            candle_body = abs(last_close - last_open)
            candle_wicks = (last_high - max(last_close, last_open)) + (min(last_close, last_open) - last_low)
            body_to_wick_ratio = candle_body / max(candle_wicks, point) if candle_wicks > 0 else 5

            strong_candle = body_to_wick_ratio > 1.5 and candle_body > atr_current * 0.3

            logger(f"🕯️ Candle Strength: Body/Wick={body_to_wick_ratio:.2f}, Strong={strong_candle}")

            # PRECISE BUY SIGNALS
            if ema20_cross_up and spread_quality in ["EXCELLENT", "GOOD"]:
                if strong_uptrend and macd_bullish and rsi_momentum_up and volume_surge:
                    buy_signals += 9
                    signals.append(f"✅ INTRADAY ULTRA: Precise EMA cross + full confirmation @ {current_price:.{digits}f}")
                elif strong_uptrend and macd_bullish and rsi_momentum_up:
                    buy_signals += 7
                    signals.append(f"✅ INTRADAY STRONG: EMA cross + trend + momentum @ {current_price:.{digits}f}")
                elif current_price > ema200_current and volume_confirmation:
                    buy_signals += 5
                    signals.append(f"✅ INTRADAY: EMA cross + EMA200 filter @ {current_price:.{digits}f}")

            # Precise trend continuation
            elif strong_uptrend and current_price > last_high * 0.999:  # Near recent high
                if (rsi14 > 55 and macd_bullish and strong_candle and
                    current_price > df['high'].rolling(10).max().iloc[-2]):  # New 10-period high
                    buy_signals += 6
                    signals.append(f"✅ INTRADAY: Precise breakout continuation @ {current_price:.{digits}f}")
                elif rsi14 > 50 and macd_value > 0 and volume_confirmation:
                    buy_signals += 4
                    signals.append(f"✅ INTRADAY: Trend continuation + volume @ {current_price:.{digits}f}")
                elif current_price > ema20_current:
                    buy_signals += 2
                    signals.append(f"✅ INTRADAY: Basic uptrend @ {current_price:.{digits}f}")

            # PRECISE SELL SIGNALS
            if ema20_cross_down and spread_quality in ["EXCELLENT", "GOOD"]:
                if strong_downtrend and macd_bearish and rsi_momentum_down and volume_surge:
                    sell_signals += 9
                    signals.append(f"✅ INTRADAY ULTRA: Precise EMA cross + full confirmation @ {current_price:.{digits}f}")
                elif strong_downtrend and macd_bearish and rsi_momentum_down:
                    sell_signals += 7
                    signals.append(f"✅ INTRADAY STRONG: EMA cross + trend + momentum @ {current_price:.{digits}f}")
                elif current_price < ema200_current and volume_confirmation:
                    sell_signals += 5
                    signals.append(f"✅ INTRADAY: EMA cross + EMA200 filter @ {current_price:.{digits}f}")

            # Precise trend continuation
            elif strong_downtrend and current_price < last_low * 1.001:  # Near recent low
                if (rsi14 < 45 and macd_bearish and strong_candle and
                    current_price < df['low'].rolling(10).min().iloc[-2]):  # New 10-period low
                    sell_signals += 6
                    signals.append(f"✅ INTRADAY: Precise breakdown continuation @ {current_price:.{digits}f}")
                elif rsi14 < 50 and macd_value < 0 and volume_confirmation:
                    sell_signals += 4
                    signals.append(f"✅ INTRADAY: Trend continuation + volume @ {current_price:.{digits}f}")
                elif current_price < ema20_current:
                    sell_signals += 2
                    signals.append(f"✅ INTRADAY: Basic downtrend @ {current_price:.{digits}f}")

            # KONFIRMASI TREND: EMA200 sebagai filter utama
            if (last['EMA20'] > last['EMA50'] > last['EMA200']
                    and last['close'] > last['EMA200'] and last['RSI14'] > 50):
                buy_signals += 2
                signals.append(
                    "✅ INTRADAY: Strong bullish EMA alignment (20>50>200)")
            elif (last['EMA20'] < last['EMA50'] < last['EMA200']
                  and last['close'] < last['EMA200'] and last['RSI14'] < 50):
                sell_signals += 2
                signals.append(
                    "✅ INTRADAY: Strong bearish EMA alignment (20<50<200)")

            # KONFIRMASI MACD: Signal line crossover
            if (last['MACD'] > last['MACD_signal']
                    and prev['MACD'] <= prev['MACD_signal']
                    and last['close'] > last['EMA200']):
                buy_signals += 2
                signals.append(
                    "✅ INTRADAY: MACD signal line cross UP + EMA200 bullish")
            elif (last['MACD'] < last['MACD_signal']
                  and prev['MACD'] >= prev['MACD_signal']
                  and last['close'] < last['EMA200']):
                sell_signals += 2
                signals.append(
                    "✅ INTRADAY: MACD signal line cross DOWN + EMA200 bearish")

            # MOMENTUM CONFIRMATION: Trend strength
            volume_avg = df['volume'].rolling(
                window=20).mean().iloc[-1] if 'volume' in df else 1
            current_volume = last.get('volume', 1)
            volume_factor = current_volume / volume_avg if volume_avg > 0 else 1

            if (last['Trend_Strength'] > 1.5 and volume_factor > 1.2
                    and last['EMA20'] > last['EMA50']
                    and last['close'] > last['EMA200']):
                buy_signals += 2
                signals.append(
                    "✅ INTRADAY: Strong uptrend momentum + volume ({last['Trend_Strength']:.2f})"
                )
            elif (last['Trend_Strength'] > 1.5 and volume_factor > 1.2
                  and last['EMA20'] < last['EMA50']
                  and last['close'] < last['EMA200']):
                sell_signals += 2
                signals.append(
                    "✅ INTRADAY: Strong downtrend momentum + volume ({last['Trend_Strength']:.2f})"
                )

            # BREAKOUT CONFIRMATION
            if (last['Bullish_Breakout'] and last['RSI14'] > 60
                    and last['close'] > last['EMA200']):
                buy_signals += 2
                signals.append(
                    "✅ INTRADAY: Breakout UP + RSI momentum + EMA200 filter")
            elif (last['Bearish_Breakout'] and last['RSI14'] < 40
                  and last['close'] < last['EMA200']):
                sell_signals += 2
                signals.append(
                    "✅ INTRADAY: Breakout DOWN + RSI momentum + EMA200 filter")

        elif strategy == "Arbitrage":
            # Enhanced Arbitrage: Precise statistical mean reversion with real-time validation
            logger("🔄 Arbitrage: Precise mean reversion with statistical edge detection...")

            # Get precise Bollinger Band values
            bb_upper = round(last.get('BB_Upper', current_price * 1.02), digits)
            bb_lower = round(last.get('BB_Lower', current_price * 0.98), digits)
            bb_middle = round(last.get('BB_Middle', current_price), digits)

            # Precise BB position calculation
            bb_range = bb_upper - bb_lower
            if bb_range > point:
                bb_position = (current_price - bb_lower) / bb_range
            else:
                bb_position = 0.5

            bb_width = last.get('BB_Width', 0.02)

            logger(f"📊 Bollinger Analysis: Position={bb_position:.3f}, Width={bb_width:.4f}")
            logger(
                f"   🎯 BB Levels: Upper={bb_upper:.{digits}f}, Middle={bb_middle:.{digits}f}, Lower={bb_lower:.{digits}f}"
            )

            # Statistical deviation analysis with precise calculation
            price_vs_middle = abs(current_price - bb_middle)
            price_deviation = price_vs_middle / bb_middle if bb_middle > 0 else 0
            deviation_pips = price_vs_middle / point

            # Enhanced deviation thresholds based on symbol
            if "JPY" in symbol:
                significant_deviation = deviation_pips > 5.0  # 5 pips for JPY
            elif any(precious in symbol for precious in ["XAU", "GOLD"]):
                significant_deviation = deviation_pips > 20.0  # $2.0 for Gold
            else:
                significant_deviation = deviation_pips > 3.0  # 3 pips for major pairs

            logger(f"📈 Deviation Analysis: {price_deviation:.4f} ({deviation_pips:.1f} pips), Significant: {significant_deviation}")

            # Enhanced RSI analysis with multiple timeframes
            rsi14 = last.get('RSI14', 50)
            rsi7 = last.get('RSI7', 50)
            rsi_smooth = last.get('RSI_Smooth', rsi14)

            rsi_extreme_oversold = rsi14 < 20 and rsi7 < 25
            rsi_extreme_overbought = rsi14 > 80 and rsi7 > 75
            rsi_moderate_oversold = 20 < rsi14 < 35
            rsi_moderate_overbought = 65 < rsi14 < 80

            # Enhanced Stochastic analysis
            stoch_k = last.get('STOCH_K', 50)
            stoch_d = last.get('STOCH_D', 50)
            stoch_k_prev = prev.get('STOCH_K', stoch_k)

            stoch_oversold = stoch_k < 15 and stoch_d < 20
            stoch_overbought = stoch_k > 85 and stoch_d > 80
            stoch_turning_up = stoch_k > stoch_k_prev and stoch_k < 30
            stoch_turning_down = stoch_k < stoch_k_prev and stoch_k > 70

            logger(f"📊 Oscillators: RSI14={rsi14:.1f}, RSI7={rsi7:.1f}, Stoch_K={stoch_k:.1f}")

            # Precise reversal momentum with real-time validation
            reversal_momentum_up = (current_price > last_close and last_close <= prev['close'] and
                                   current_price > bb_lower)
            reversal_momentum_down = (current_price < last_close and last_close >= prev['close'] and
                                    current_price < bb_upper)

            # PRECISE EXTREME OVERSOLD REVERSAL
            if bb_position <= 0.05 and significant_deviation and spread_quality in ["EXCELLENT", "GOOD"]:  # Bottom 5%
                if rsi_extreme_oversold and reversal_momentum_up:
                    if stoch_oversold and stoch_turning_up and volume_surge:
                        buy_signals += 10
                        signals.append(f"✅ ARB ULTRA: Extreme oversold + volume @ {current_price:.{digits}f} (BB:{bb_position:.3f}, RSI:{rsi14:.1f})")
                    elif stoch_turning_up:
                        buy_signals += 8
                        signals.append(f"✅ ARB STRONG: Extreme oversold reversal @ {current_price:.{digits}f} (BB:{bb_position:.3f})")
                    else:
                        buy_signals += 6
                        signals.append(f"✅ ARB: Oversold bounce @ {current_price:.{digits}f} (RSI:{rsi14:.1f})")
                elif rsi_moderate_oversold and reversal_momentum_up:
                    buy_signals += 4
                    signals.append(f"✅ ARB: Moderate oversold @ {current_price:.{digits}f} (BB:{bb_position:.3f})")

            # Precise support level bounce
            elif bb_position <= 0.15 and current_price <= bb_lower * 1.002:  # Near BB lower
                if rsi14 < 35 and current_price > prev['close']:
                    buy_signals += 5
                    signals.append(f"✅ ARB: Support bounce @ {current_price:.{digits}f} (BB_Lower: {bb_lower:.{digits}f})")

            # PRECISE EXTREME OVERBOUGHT REVERSAL
            if bb_position >= 0.95 and significant_deviation and spread_quality in ["EXCELLENT", "GOOD"]:  # Top 5%
                if rsi_extreme_overbought and reversal_momentum_down:
                    if stoch_overbought and stoch_turning_down and volume_surge:
                        sell_signals += 10
                        signals.append(f"✅ ARB ULTRA: Extreme overbought + volume @ {current_price:.{digits}f} (BB:{bb_position:.3f}, RSI:{rsi14:.1f})")
                    elif stoch_turning_down:
                        sell_signals += 8
                        signals.append(f"✅ ARB STRONG: Extreme overbought reversal @ {current_price:.{digits}f} (BB:{bb_position:.3f})")
                    else:
                        sell_signals += 6
                        signals.append(f"✅ ARB: Overbought decline @ {current_price:.{digits}f} (RSI:{rsi14:.1f})")
                elif rsi_moderate_overbought and reversal_momentum_down:
                    sell_signals += 4
                    signals.append(f"✅ ARB: Moderate overbought @ {current_price:.{digits}f} (BB:{bb_position:.3f})")

            # Precise resistance level rejection
            elif bb_position >= 0.85 and current_price >= bb_upper * 0.998:  # Near BB upper
                if rsi14 > 65 and current_price < prev['close']:
                    sell_signals += 5
                    signals.append(f"✅ ARB: Resistance rejection @ {current_price:.{digits}f} (BB_Upper: {bb_upper:.{digits}f})")

            # Mean reversion from middle BB with precise conditions
            middle_distance = abs(current_price - bb_middle) / point
            if 2.0 < middle_distance < 8.0:  # Optimal distance from middle
                if current_price < bb_middle and rsi14 < 45 and reversal_momentum_up:
                    buy_signals += 3
                    signals.append(f"✅ ARB: Mean reversion UP @ {current_price:.{digits}f} (Middle: {bb_middle:.{digits}f})")
                elif current_price > bb_middle and rsi14 > 55 and reversal_momentum_down:
                    sell_signals += 3
                    signals.append(f"✅ ARB: Mean reversion DOWN @ {current_price:.{digits}f} (Middle: {bb_middle:.{digits}f})")

            # Arbitrage Signal 2: Mean reversion dengan statistical confidence
            price_distance_from_mean = abs(last['close'] - last['BB_Middle']) / last['BB_Middle']
            if price_distance_from_mean > 0.015:  # 1.5% deviation dari mean
                if last['close'] < last['BB_Middle'] and last['close'] > prev['close']:
                    # Price below mean but recovering
                    buy_signals += 3
                    signals.append(f"✅ ARBITRAGE: Below-mean recovery ({price_distance_from_mean:.3f})")
                elif last['close'] > last['BB_Middle'] and last['close'] < prev['close']:
                    # Price above mean but declining
                    sell_signals += 3
                    signals.append(f"✅ ARBITRAGE: Above-mean decline ({price_distance_from_mean:.3f})")

            # Arbitrage Signal 3: RSI50 crossover dengan momentum confirmation
            if last['RSI14'] > 50 and prev['RSI14'] <= 50:
                if last['close'] > last['EMA20'] and last['MACD_histogram'] > 0:
                    buy_signals += 2
                    signals.append("✅ ARBITRAGE: RSI50 cross UP + momentum")
            elif last['RSI14'] < 50 and prev['RSI14'] >= 50:
                if last['close'] < last['EMA20'] and last['MACD_histogram'] < 0:
                    sell_signals += 2
                    signals.append("✅ ARBITRAGE: RSI50 cross DOWN + momentum")

            # Arbitrage Signal 4: Support/Resistance bounce
            support_level = df['low'].rolling(20).min().iloc[-1]
            resistance_level = df['high'].rolling(20).max().iloc[-1]

            if abs(last['close'] - support_level) / last['close'] < 0.002:  # Near support
                if last['close'] > prev['close'] and last['RSI14'] < 40:
                    buy_signals += 3
                    signals.append("✅ ARBITRAGE: Support bounce + oversold")
            elif abs(last['close'] - resistance_level) / last['close'] < 0.002:  # Near resistance
                if last['close'] < prev['close'] and last['RSI14'] > 60:
                    sell_signals += 3
                    signals.append("✅ ARBITRAGE: Resistance rejection + overbought")

            # Arbitrage Signal 5: Volume-confirmed reversion
            volume_avg = df['volume'].rolling(20).mean().iloc[-1] if 'volume' in df else 1
            current_volume = last.get('volume', 1)
            if current_volume > volume_avg * 1.5:  # High volume confirmation
                if bb_position < 0.2 and last['close'] > prev['close']:
                    buy_signals += 2
                    signals.append("✅ ARBITRAGE: Volume-confirmed oversold bounce")
                elif bb_position > 0.8 and last['close'] < prev['close']:
                    sell_signals += 2
                    signals.append("✅ ARBITRAGE: Volume-confirmed overbought decline")

        # Session-aware signal thresholds
        base_min_signals = {
            "Scalping": 3,  # Moderate confirmation for scalping
            "HFT": 2,  # Very aggressive - fastest execution
            "Intraday": 4,  # Strong confirmation for longer trades
            "Arbitrage": 2  # Quick mean reversion entries
        }

        # Apply session adjustments to threshold
        base_threshold = base_min_signals.get(strategy, 2)
        threshold_modifier = session_adjustments.get(
            "signal_threshold_modifier", 0)
        threshold = max(1, base_threshold +
                        threshold_modifier)  # Minimum threshold of 1

        # AI-enhanced signal boost based on quality factors
        if current_session:
            session_name = current_session.get("name", "Unknown")
            volatility = current_session["info"]["volatility"]
            logger(
                f"📊 {session_name} session ({volatility} volatility) - adjusted threshold: {base_threshold} → {threshold}"
            )
        else:
            logger(f"📊 Default session - threshold: {threshold}")

        # ADVANCED SIGNAL QUALITY ASSESSMENT for Higher Winrate
        total_initial_signals = buy_signals + sell_signals

        # Calculate signal quality score (0-100)
        signal_quality_score = 0
        quality_factors = []

        # Factor 1: Trend alignment strength
        ema5_current = last.get('EMA5', current_price)
        ema13_current = last.get('EMA13', current_price)
        ema50_current = last.get('EMA50', current_price)
        ema200_current = last.get('EMA200', current_price)

        if ema5_current > ema13_current > ema50_current > ema200_current:
            signal_quality_score += 25
            quality_factors.append("Strong bullish alignment")
        elif ema5_current < ema13_current < ema50_current < ema200_current:
            signal_quality_score += 25
            quality_factors.append("Strong bearish alignment")
        elif ema5_current > ema13_current > ema50_current:
            signal_quality_score += 15
            quality_factors.append("Medium bullish alignment")
        elif ema5_current < ema13_current < ema50_current:
            signal_quality_score += 15
            quality_factors.append("Medium bearish alignment")

        # Factor 2: RSI confluence
        rsi_value = last.get('RSI', 50)
        if 40 <= rsi_value <= 60:
            signal_quality_score += 20
            quality_factors.append("RSI in optimal range")
        elif 30 <= rsi_value <= 70:
            signal_quality_score += 15
            quality_factors.append("RSI in good range")
        elif rsi_value < 25 or rsi_value > 75:
            signal_quality_score += 10
            quality_factors.append("RSI extreme (reversal potential)")

        # Factor 3: Market session quality
        current_session = get_current_trading_session()
        if current_session:
            volatility = current_session["info"]["volatility"]
            if volatility in ["high", "very_high"]:
                signal_quality_score += 20
                quality_factors.append("High volatility session")
            elif volatility == "medium":
                signal_quality_score += 15
                quality_factors.append("Medium volatility session")

        # Factor 4: MACD confirmation
        macd_hist = last.get('MACD_histogram', 0)
        macd_hist_prev = prev.get('MACD_histogram', 0)
        if abs(macd_hist) > abs(macd_hist_prev):
            signal_quality_score += 15
            quality_factors.append("MACD momentum increasing")

        # Factor 5: Volume confirmation (if available)
        if 'volume' in df.columns:
            vol_avg = df['volume'].rolling(20).mean().iloc[-1]
            current_vol = last.get('volume', 1)
            if current_vol > vol_avg * 1.3:
                signal_quality_score += 10
                quality_factors.append("Above average volume")

        logger(f"📊 Signal Quality Assessment: {signal_quality_score}/100")
        for factor in quality_factors:
            logger(f"   ✓ {factor}")

        # Quality-based signal filtering
        quality_threshold = 60  # Minimum quality score for signal approval

        if total_initial_signals < threshold and signal_quality_score >= quality_threshold:
            logger("🎯 HIGH QUALITY SIGNAL BOOST: Quality score meets threshold...")

            # AI-enhanced signal boost based on quality factors
            if "Strong bullish alignment" in quality_factors or "Strong bearish alignment" in quality_factors:
                if ema5_current > ema13_current:
                    buy_signals += 3
                    signals.append(f"🌟 QUALITY BOOST: Strong trend alignment BUY @ {current_price:.{digits}f}")
                else:
                    sell_signals += 3
                    signals.append(f"🌟 QUALITY BOOST: Strong trend alignment SELL @ {current_price:.{digits}f}")

            # Momentum-based enhancement
            if macd_hist > 0 and "MACD momentum increasing" in quality_factors:
                buy_signals += 2
                signals.append("🚀 QUALITY: Strong bullish momentum")
            elif macd_hist < 0 and "MACD momentum increasing" in quality_factors:
                sell_signals += 2
                signals.append("📉 QUALITY: Strong bearish momentum")

        elif total_initial_signals < threshold:
            logger(f"❌ Signal quality insufficient: {signal_quality_score}/100 < {quality_threshold}")
            logger("💡 Waiting for higher quality setup...")

            # AI-ALIGNED SIGNAL ENHANCEMENT
            if ai_analysis['market_structure'] == "BULLISH" and ai_analysis['confidence'] > 25:
                # Focus on BUY signals for bullish market
                if rsi_value < 40:  # Oversold in bullish market = opportunity
                    buy_signals += 3
                    signals.append(f"🤖 AI-BULLISH: RSI dip buy @ {current_price:.{digits}f} (RSI: {rsi_value:.1f})")
                elif ema5_current > ema13_current:
                    buy_signals += 2
                    signals.append(f"🤖 AI-BULLISH: EMA alignment buy @ {current_price:.{digits}f}")

            elif ai_analysis['market_structure'] == "BEARISH" and ai_analysis['confidence'] > 25:
                # Focus on SELL signals for bearish market
                if rsi_value > 60:  # Overbought in bearish market = opportunity
                    sell_signals += 3
                    signals.append(f"🤖 AI-BEARISH: RSI peak sell @ {current_price:.{digits}f} (RSI: {rsi_value:.1f})")
                elif ema5_current < ema13_current:
                    sell_signals += 2
                    signals.append(f"🤖 AI-BEARISH: EMA alignment sell @ {current_price:.{digits}f}")

            # MOMENTUM-BASED SIGNALS
            price_change_pips = abs(current_price - last_close) / point
            if price_change_pips > 5:  # Significant movement
                if current_price > last_close and ai_analysis['market_structure'] != "BEARISH":
                    buy_signals += 2
                    signals.append(f"🎯 MOMENTUM: Strong UP {price_change_pips:.1f} pips @ {current_price:.{digits}f}")
                elif current_price < last_close and ai_analysis['market_structure'] != "BULLISH":
                    sell_signals += 2
                    signals.append(f"🎯 MOMENTUM: Strong DOWN {price_change_pips:.1f} pips @ {current_price:.{digits}f}")

            # FALLBACK: If still no clear direction, use RSI extremes
            if buy_signals + sell_signals < threshold:
                if rsi_value < 30:
                    buy_signals += (threshold - (buy_signals + sell_signals))
                    signals.append(f"🆘 EXTREME: RSI oversold rescue @ {current_price:.{digits}f}")
                elif rsi_value > 70:
                    sell_signals += (threshold - (buy_signals + sell_signals))
                    signals.append(f"🆘 EXTREME: RSI overbought rescue @ {current_price:.{digits}f}")

        # Final Analysis
        logger(f"🔍 Enhanced Signal Results:")
        logger(f"   Final BUY Signals: {buy_signals}")
        logger(f"   Final SELL Signals: {sell_signals}")
        logger(f"   Enhancement Added: {(buy_signals + sell_signals) - total_initial_signals}")
        logger(f"   Session Adjustment: {session_adjustments.get('signal_threshold_modifier', 0)}")

        action = None
        signals = []
        buy_signals = 0
        sell_signals = 0

        # Enhanced price logging with precision
        logger(f"📊 {symbol} Precise Data:")
        logger(f"   📈 Candle: O={last_open:.{digits}f} H={last_high:.{digits}f} L={last_low:.{digits}f} C={last_close:.{digits}f}")
        logger(f"   🎯 Real-time: Bid={current_bid:.{digits}f} Ask={current_ask:.{digits}f} Spread={current_spread:.{digits}f}")
        logger(f"   💡 Current Price: {current_price:.{digits}f} (Mid-price)")

        # Price movement analysis with precise calculations
        price_change = round(current_price - last_close, digits)
        price_change_pips = abs(price_change) / point

        logger(f"   📊 Price Movement: {price_change:+.{digits}f} ({price_change_pips:.1f} pips)")

        # Decision logic with tie-breaker
        total_signals = buy_signals + sell_signals
        signal_strength = max(buy_signals, sell_signals)

        # Lower threshold for debugging if no strong signals
        effective_threshold = max(1, threshold - 1) if signals else threshold

        if buy_signals > sell_signals and buy_signals >= effective_threshold:
            action = "BUY"
            confidence = (buy_signals / max(total_signals, 1)) * 100
            logger(
                f"🟢 {strategy} BUY SIGNAL ACTIVATED! Score: {buy_signals} vs {sell_signals} (confidence: {confidence:.1f}%)"
            )
        elif sell_signals > buy_signals and sell_signals >= effective_threshold:
            action = "SELL"
            confidence = (sell_signals / max(total_signals, 1)) * 100
            logger(
                f"🔴 {strategy} SELL SIGNAL ACTIVATED! Score: {sell_signals} vs {buy_signals} (confidence: {confidence:.1f}%)"
            )
        else:
            logger(
                f"⚪ {strategy} WAITING. BUY:{buy_signals} SELL:{sell_signals} (need:{effective_threshold})"
            )

            # Debug recommendation
            if total_signals > 0:
                stronger_side = "BUY" if buy_signals > sell_signals else "SELL"
                logger(
                    f"💡 Closest to signal: {stronger_side} ({max(buy_signals, sell_signals)}/{effective_threshold})"
                )

        return action, signals

    except Exception as e:
        logger(f"❌ Strategy {strategy} error: {str(e)}")
        import traceback
        logger(f"🔍 Traceback: {traceback.format_exc()}")
        return None, [f"❌ Strategy {strategy} error: {str(e)}"]


def get_symbol_data(symbol: str,
                    timeframe: int,
                    n: int = 200) -> Optional[pd.DataFrame]:
    """
    Enhanced data fetching with precise price validation and error handling.

    Args:
        symbol (str): Trading symbol (e.g., 'EURUSD')
        timeframe (int): MetaTrader5 timeframe constant
        n (int): Number of candles to fetch (default: 200)

    Returns:
        Optional[pd.DataFrame]: DataFrame with OHLCV data or None if failed
    """
    try:
        if not check_mt5_status():
            logger("❌ MT5 not connected for data request")
            return None

        # Validate symbol first with enhanced validation
        valid_symbol = validate_and_activate_symbol(symbol)
        if not valid_symbol:
            logger(f"❌ Cannot validate {symbol} for data request")
            return None

        # Get symbol info for precision settings
        symbol_info = mt5.symbol_info(valid_symbol)
        if not symbol_info:
            logger(f"❌ Cannot get symbol info for {valid_symbol}")
            return None

        # Extract precision info
        digits = getattr(symbol_info, 'digits', 5)
        point = getattr(symbol_info, 'point', 0.00001)

        logger(f"🔍 Symbol precision: {valid_symbol} - Digits: {digits}, Point: {point}")

        # Adjust data count based on timeframe for better analysis
        timeframe_adjustments = {
            mt5.TIMEFRAME_M1: 500,  # More data for precise M1 analysis
            mt5.TIMEFRAME_M3: 400,
            mt5.TIMEFRAME_M5: 300,
            mt5.TIMEFRAME_M15: 200,
            mt5.TIMEFRAME_M30: 150,
            mt5.TIMEFRAME_H1: 120,
            mt5.TIMEFRAME_H4: 100,
            mt5.TIMEFRAME_D1: 80
        }

        adjusted_n = timeframe_adjustments.get(timeframe, n)

        # Multiple attempts with enhanced validation
        for attempt in range(3):
            try:
                logger(
                    f"📊 Attempt {attempt + 1}: Getting {adjusted_n} precise candles for {valid_symbol}"
                )

                # Get the most recent data
                rates = mt5.copy_rates_from_pos(valid_symbol, timeframe, 0, adjusted_n)

                if rates is not None and len(rates) > 50:
                    df = pd.DataFrame(rates)
                    df['time'] = pd.to_datetime(df['time'], unit='s')

                    # Enhanced data validation and precision correction
                    required_columns = ['open', 'high', 'low', 'close', 'tick_volume']
                    for col in required_columns:
                        if col not in df.columns:
                            logger(f"❌ Missing required column: {col}")
                            return None

                    # Precise price validation and rounding
                    for price_col in ['open', 'high', 'low', 'close']:
                        # Round to symbol's precision
                        df[price_col] = df[price_col].round(digits)

                        # Validate price ranges
                        if df[price_col].isna().any():
                            logger(f"⚠️ Found NaN values in {price_col}, forward filling...")
                            df[price_col] = df[price_col].fillna(method='ffill')

                        # Remove zero or negative prices
                        invalid_prices = (df[price_col] <= 0).sum()
                        if invalid_prices > 0:
                            logger(f"⚠️ Found {invalid_prices} invalid prices in {price_col}")
                            df = df[df[price_col] > 0]

                    # Enhanced OHLC relationship validation
                    invalid_ohlc = 0

                    # Fix high < low
                    high_low_issues = df['high'] < df['low']
                    if high_low_issues.any():
                        invalid_ohlc += high_low_issues.sum()
                        df.loc[high_low_issues, ['high', 'low']] = df.loc[high_low_issues, ['low', 'high']].values
                        logger(f"🔧 Fixed {high_low_issues.sum()} high < low issues")

                    # Ensure close is within high-low range
                    close_above_high = df['close'] > df['high']
                    close_below_low = df['close'] < df['low']

                    if close_above_high.any():
                        invalid_ohlc += close_above_high.sum()
                        df.loc[close_above_high, 'close'] = df.loc[close_above_high, 'high']
                        logger(f"🔧 Fixed {close_above_high.sum()} close > high issues")

                    if close_below_low.any():
                        invalid_ohlc += close_below_low.sum()
                        df.loc[close_below_low, 'close'] = df.loc[close_below_low, 'low']
                        logger(f"🔧 Fixed {close_below_low.sum()} close < low issues")

                    # Ensure open is within high-low range
                    open_above_high = df['open'] > df['high']
                    open_below_low = df['open'] < df['low']

                    if open_above_high.any():
                        invalid_ohlc += open_above_high.sum()
                        df.loc[open_above_high, 'open'] = df.loc[open_above_high, 'high']
                        logger(f"🔧 Fixed {open_above_high.sum()} open > high issues")

                    if open_below_low.any():
                        invalid_ohlc += open_below_low.sum()
                        df.loc[open_below_low, 'open'] = df.loc[open_below_low, 'low']
                        logger(f"🔧 Fixed {open_below_low.sum()} open < low issues")

                    # Create volume column with validation
                    if 'volume' not in df.columns:
                        df['volume'] = df['tick_volume']

                    # Ensure volume is positive
                    df['volume'] = df['volume'].abs()
                    df.loc[df['volume'] == 0, 'volume'] = df['tick_volume']

                    # Sort by time to ensure chronological order
                    df = df.sort_values('time').reset_index(drop=True)

                    # Final validation - remove any remaining invalid rows
                    initial_len = len(df)
                    df = df[
                        (df['open'] > 0) & (df['high'] > 0) &
                        (df['low'] > 0) & (df['close'] > 0) &
                        (df['high'] >= df['low']) &
                        (df['close'] >= df['low']) & (df['close'] <= df['high']) &
                        (df['open'] >= df['low']) & (df['open'] <= df['high'])
                    ]

                    final_len = len(df)
                    if initial_len != final_len:
                        logger(f"🔧 Removed {initial_len - final_len} invalid rows")

                    if len(df) < 50:
                        logger(f"❌ Insufficient valid data after cleaning: {len(df)} rows")
                        continue

                    # Add price precision metadata
                    df.attrs['symbol'] = valid_symbol
                    df.attrs['digits'] = digits
                    df.attrs['point'] = point
                    df.attrs['timeframe'] = timeframe

                    logger(f"✅ Retrieved {len(df)} precise candles for {valid_symbol}")
                    logger(f"📊 Price range: {df['low'].min():.{digits}f} - {df['high'].max():.{digits}f}")

                    return df
                else:
                    logger(f"⚠️ Insufficient raw data (attempt {attempt + 1}): {len(rates) if rates else 0} candles")

            except Exception as e:
                logger(f"⚠️ Data request failed (attempt {attempt + 1}): {str(e)}")

            if attempt < 2:
                time.sleep(2.0)  # Wait between attempts

        logger(f"❌ All data requests failed for {valid_symbol}")
        return None

    except Exception as e:
        logger(f"❌ Critical error getting data for {symbol}: {str(e)}")
        return None


def check_daily_limits() -> bool:
    """
    Advanced risk management with dynamic profit optimization.

    Features:
    - Adaptive drawdown protection
    - Smart profit taking
    - Position size optimization
    - Real-time risk assessment
    """
    try:
        global session_start_balance

        if not session_start_balance:
            return True

        info = get_account_info()
        if not info:
            logger("⚠️ Cannot get account info for advanced risk check")
            return True

        current_equity = info['equity']
        current_balance = info['balance']

        # Advanced drawdown monitoring with adaptive thresholds
        daily_loss = session_start_balance - current_equity
        daily_loss_percent = (daily_loss / session_start_balance) * 100

        # Dynamic risk adjustment based on market conditions
        current_session = get_current_trading_session()
        volatility_multiplier = 1.0

        if current_session:
            volatility = current_session["info"]["volatility"]
            volatility_multiplier = {
                "very_high": 0.7,  # Reduce risk in high volatility
                "high": 0.85,
                "medium": 1.0,
                "low": 1.2  # Allow slightly higher risk in stable conditions
            }.get(volatility, 1.0)

        # Adaptive drawdown limit
        adaptive_max_drawdown = max_drawdown * volatility_multiplier
        logger(f"📊 Adaptive risk: DD limit {adaptive_max_drawdown*100:.1f}% (volatility: {volatility_multiplier})")

        # Smart profit protection - lock in profits progressively
        profit_percent = ((current_equity - session_start_balance) / session_start_balance) * 100

        if profit_percent > 2.0:  # If we're up 2%+, protect 50% of gains
            protective_drawdown = adaptive_max_drawdown * 0.5
            logger(f"💰 Profit protection active: {profit_percent:.1f}% profit, using {protective_drawdown*100:.1f}% protective DD")
            if daily_loss_percent >= (protective_drawdown * 100):
                logger(f"🛡️ Protective stop triggered at {daily_loss_percent:.2f}% drawdown")
                close_all_orders()
                return False

        # Real-time drawdown from peak equity
        max_equity_today = max(session_start_balance, current_equity)
        session_data['max_equity'] = max(
            session_data.get('max_equity', session_start_balance),
            current_equity)
        current_drawdown = (session_data['max_equity'] -
                            current_equity) / session_data['max_equity']

        # Critical drawdown protection
        if current_drawdown >= max_drawdown:
            logger(f"🛑 CRITICAL: Max drawdown reached: {current_drawdown:.2%}")
            logger(
                f"💰 Peak Equity: ${session_data['max_equity']:.2f} → Current: ${current_equity:.2f}"
            )

            # Emergency close all positions
            close_all_orders()

            # Send alert
            if gui and hasattr(gui, 'telegram_var') and gui.telegram_var.get():
                msg = f"🚨 DRAWDOWN ALERT!\nMax DD: {current_drawdown:.2%}\nPeak: ${session_data['max_equity']:.2f}\nCurrent: ${current_equity:.2f}\nAll positions closed!"
                send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, msg)

            return False

        # Daily loss limit
        if daily_loss_percent >= (daily_max_loss * 100):
            logger(f"🛑 Daily max loss reached: {daily_loss_percent:.2f}%")
            return False

        # Profit target check with auto-close option
        daily_profit_percent = ((current_equity - session_start_balance) /
                                session_start_balance) * 100
        if daily_profit_percent >= (profit_target * 100):
            logger(
                f"🎯 Daily profit target reached: {daily_profit_percent:.2f}%")

            # Auto-close positions when target reached
            if gui and hasattr(gui, 'telegram_var') and gui.telegram_var.get():
                msg = f"🎯 PROFIT TARGET ACHIEVED!\nProfit: ${current_equity - session_start_balance:.2f} ({daily_profit_percent:.2f}%)\nClosing all positions..."
                send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, msg)

            close_all_orders()
            return False

        # Margin level protection
        margin_level = info.get('margin_level', 1000)
        if margin_level < 200 and margin_level > 0:
            logger(f"🛑 Low margin level detected: {margin_level:.2f}%")
            logger("🚨 Reducing trading intensity due to margin concerns")

            # Close some positions if margin is very low
            if margin_level < 150:
                positions = get_positions()
                if positions and len(positions) > 1:
                    # Close most losing positions
                    losing_positions = [p for p in positions if p.profit < 0]
                    for pos in losing_positions[:
                                                2]:  # Close up to 2 losing positions
                        close_position_by_ticket(pos.ticket)
                    logger(
                        f"🚨 Emergency: Closed {min(2, len(losing_positions))} losing positions due to low margin"
                    )

        return True

    except Exception as e:
        logger(f"❌ Error in check_daily_limits: {str(e)}")
        return True


def close_position_by_ticket(ticket: int) -> bool:
    """Close specific position by ticket"""
    try:
        position = None
        positions = mt5.positions_get(ticket=ticket)
        if positions:
            position = positions[0]
        else:
            return False

        tick = mt5.symbol_info_tick(position.symbol)
        if tick is None:
            return False

        order_type = mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = tick.bid if position.type == mt5.ORDER_TYPE_BUY else tick.ask

        close_request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": ticket,
            "symbol": position.symbol,
            "volume": position.volume,
            "type": order_type,
            "price": price,
            "deviation": 20,
            "magic": position.magic,
            "comment": "AutoBot_Emergency",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(close_request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            logger(
                f"✅ Position {ticket} closed emergency - Profit: ${position.profit:.2f}"
            )
            return True
        else:
            logger(f"❌ Failed to close position {ticket}")
            return False

    except Exception as e:
        logger(f"❌ Error closing position {ticket}: {str(e)}")
        return False


def auto_recovery_check() -> bool:
    """Advanced auto-recovery system with intelligent error prevention"""
    global mt5_connected, disconnect_count

    try:
        if not mt5_connected:
            logger("🔄 Auto-recovery: Attempting intelligent MT5 reconnection...")

            # Smart recovery strategy
            backoff_delay = min(CONNECTION_RETRY_DELAY * (2**min(disconnect_count, 5)), 60)
            logger(f"⏱️ Using smart backoff delay: {backoff_delay}s")

            # Pre-recovery system checks
            logger("🔍 Pre-recovery diagnostics...")

            # Check system resources
            import psutil
            memory_percent = psutil.virtual_memory().percent
            cpu_percent = psutil.cpu_percent(interval=1)

            if memory_percent > 90:
                logger("⚠️ High memory usage detected, cleaning up...")
                cleanup_resources()

            if cpu_percent > 95:
                logger("⚠️ High CPU usage, waiting for stabilization...")
                time.sleep(5)

            time.sleep(backoff_delay)

            if connect_mt5():
                logger("✅ Auto-recovery: MT5 reconnected successfully!")
                disconnect_count = 0

                if gui and hasattr(gui,
                                   'telegram_var') and gui.telegram_var.get():
                    try:
                        send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
                                      "🔄 Auto-recovery: MT5 reconnected!")
                    except Exception as tg_e:
                        logger(f"⚠️ Telegram notification failed: {str(tg_e)}")

                return True
            else:
                disconnect_count += 1
                logger(f"❌ Auto-recovery failed. Attempt: {disconnect_count}")

                if disconnect_count > MAX_CONSECUTIVE_FAILURES:
                    logger(
                        "🚨 Maximum recovery attempts exceeded. Manual intervention required."
                    )
                    if gui and hasattr(
                            gui, 'telegram_var') and gui.telegram_var.get():
                        try:
                            send_telegram(
                                TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
                                "🚨 Auto-recovery failed multiple times. Manual intervention required."
                            )
                        except Exception as tg_e:
                            logger(
                                f"⚠️ Emergency Telegram notification failed: {str(tg_e)}"
                            )

                return False

        return True

    except ConnectionError as ce:
        logger(f"❌ Connection error during recovery: {str(ce)}")
        return False
    except Exception as e:
        logger(f"❌ Unexpected auto-recovery error: {str(e)}")
        return False


# Logger function moved to top of file - no duplicate needed here


def send_telegram(token: str, chat_id: str, message: str) -> bool:
    """Enhanced Telegram messaging with specific error handling"""
    if not token or not chat_id:
        logger("⚠️ Telegram credentials missing")
        return False

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": message[:4096]
        }  # Telegram message limit
        response = requests.post(url,
                                 data=data,
                                 timeout=DEFAULT_TIMEOUT_SECONDS)

        if response.status_code == 200:
            return True
        elif response.status_code == 429:
            logger(f"⚠️ Telegram rate limited: {response.status_code}")
            return False
        else:
            logger(f"⚠️ Telegram send failed: {response.status_code}")
            return False

    except requests.exceptions.Timeout:
        logger("❌ Telegram timeout error")
        return False
    except requests.exceptions.ConnectionError:
        logger("❌ Telegram connection error")
        return False
    except requests.exceptions.RequestException as e:
        logger(f"❌ Telegram request error: {str(e)}")
        return False
    except Exception as e:
        logger(f"❌ Unexpected Telegram error: {str(e)}")
        return False


def get_current_trading_session() -> Optional[Dict[str, Any]]:
    """Get current active trading session with accurate overnight handling"""
    try:
        from datetime import time as dt_time

        now = datetime.datetime.now().time()
        current_hour = datetime.datetime.now().hour
        logger(f"🔍 DEBUG: current_hour = {current_hour}")

        # Define precise session times using time objects
        asia_start = dt_time(21, 0)
        asia_end = dt_time(6, 0)
        london_start = dt_time(7, 0)
        london_end = dt_time(15, 0)
        newyork_start = dt_time(15, 0)
        newyork_end = dt_time(21, 0)

        session_name = "Unknown"
        session_info = None
        volatility = "unknown"

        # Fixed priority order - prevent Asia dominance
        if london_start <= now < london_end:
            session_name = "London"
            session_info = TRADING_SESSIONS["London"]
            volatility = "high"
            logger(f"🌍 London session ACTIVE ({london_start.strftime('%H:%M')}-{london_end.strftime('%H:%M')})")
        elif newyork_start <= now < newyork_end:
            session_name = "New_York"
            session_info = TRADING_SESSIONS["New_York"]
            volatility = "high"
            logger(f"🌍 New York session ACTIVE ({newyork_start.strftime('%H:%M')}-{newyork_end.strftime('%H:%M')})")
        elif (now >= asia_start) or (now < asia_end):  # Overnight session logic
            session_name = "Asia"
            session_info = TRADING_SESSIONS["Asia"]
            volatility = "medium"
            logger(f"🌏 Asia session ACTIVE (overnight: {asia_start.strftime('%H:%M')}-{asia_end.strftime('%H:%M')})")
        else:
            session_name = "Overlap"
            volatility = "very_high"
            logger("🌐 Overlap/Transition period detected")
            # Return default for overlap periods
            return {
                "name": "24/7",
                "info": {
                    "volatility": "medium",
                    "preferred_pairs": ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]
                },
                "time_in_session": 0.5
            }

        # Calculate time progress for valid sessions
        time_progress = 0.5
        if session_name == "Asia":
            # Special overnight calculation
            if current_hour >= 21:
                elapsed = current_hour - 21
                total_hours = (24 - 21) + 6
            else:
                elapsed = (24 - 21) + current_hour
                total_hours = (24 - 21) + 6
            time_progress = min(elapsed / total_hours, 1.0) if total_hours > 0 else 0.0
        elif session_name == "London":
            time_progress = (current_hour - 7) / (15 - 7)
        elif session_name == "New_York":
            time_progress = (current_hour - 15) / (21 - 15)

        best_session = {
            "name": session_name,
            "info": session_info,
            "time_in_session": time_progress
        }

        logger(f"🕐 Current time: {now.strftime('%H:%M')} (Local)")
        logger(f"✅ PRIMARY SESSION: {session_name} - {volatility} volatility")

        return best_session

    except Exception as e:
        logger(f"❌ Error getting trading session: {str(e)}")
        # Return default session on error
        return {
            "name": "Default",
            "info": {
                "volatility": "medium",
                "preferred_pairs": ["EURUSD", "GBPUSD", "USDJPY"]
            },
            "time_in_session": 0.5
        }


def calculate_session_time_progress(current_hour: int, start_hour: int,
                                    end_hour: int) -> float:
    """Calculate how far into the session we are (0.0 to 1.0)"""
    try:
        if start_hour > end_hour:  # Overnight session
            total_hours = (24 - start_hour) + end_hour
            if current_hour >= start_hour:
                elapsed = current_hour - start_hour
            else:
                elapsed = (24 - start_hour) + current_hour
        else:
            total_hours = end_hour - start_hour
            elapsed = current_hour - start_hour

        return min(elapsed / total_hours, 1.0) if total_hours > 0 else 0.0
    except:
        return 0.5


def get_session_priority(volatility: str) -> int:
    """Get session priority based on volatility"""
    priority_map = {"very_high": 4, "high": 3, "medium": 2, "low": 1}
    return priority_map.get(volatility, 1)


def get_session_optimal_symbols(session_name: str) -> List[str]:
    """Get optimal symbols for current trading session"""
    try:
        if session_name in TRADING_SESSIONS:
            return TRADING_SESSIONS[session_name]["preferred_pairs"]
        return ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]
    except:
        return ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]


def adjust_strategy_for_session(
        strategy: str, session_info: Optional[Dict]) -> Dict[str, Any]:
    """Adjust trading strategy parameters based on current session"""
    try:
        base_adjustments = {
            "lot_multiplier": 1.0,
            "tp_multiplier": 1.0,
            "sl_multiplier": 1.0,
            "signal_threshold_modifier": 0,
            "max_spread_multiplier": 1.0
        }

        if not session_info:
            return base_adjustments

        session_name = session_info["name"]
        volatility = session_info["info"]["volatility"]
        session_settings = SESSION_SETTINGS.get(session_name, {})

        # Adjust based on volatility
        if volatility == "very_high":
            base_adjustments.update({
                "lot_multiplier": 1.2,
                "tp_multiplier": 1.3,
                "sl_multiplier": 0.8,
                "signal_threshold_modifier": -1,  # More aggressive
                "max_spread_multiplier": 0.8
            })
        elif volatility == "high":
            base_adjustments.update({
                "lot_multiplier": 1.1,
                "tp_multiplier": 1.2,
                "sl_multiplier": 0.9,
                "signal_threshold_modifier": 0,
                "max_spread_multiplier": 1.0
            })
        elif volatility == "medium":
            base_adjustments.update({
                "lot_multiplier": 0.9,
                "tp_multiplier": 1.0,
                "sl_multiplier": 1.1,
                "signal_threshold_modifier": 1,  # More conservative
                "max_spread_multiplier": 1.2
            })
        else:  # low volatility
            base_adjustments.update({
                "lot_multiplier": 0.8,
                "tp_multiplier": 0.9,
                "sl_multiplier": 1.2,
                "signal_threshold_modifier": 2,  # Very conservative
                "max_spread_multiplier": 1.5
            })

        # Strategy-specific adjustments
        if strategy == "HFT":
            base_adjustments[
                "signal_threshold_modifier"] -= 1  # More aggressive for HFT
        elif strategy == "Intraday":
            base_adjustments[
                "tp_multiplier"] *= 1.2  # Larger targets for intraday

        logger(f"📊 Session adjustments for {session_name}: {base_adjustments}")
        return base_adjustments

    except Exception as e:
        logger(f"❌ Error adjusting strategy for session: {str(e)}")
        return {
            "lot_multiplier": 1.0,
            "tp_multiplier": 1.0,
            "sl_multiplier": 1.0,
            "signal_threshold_modifier": 0,
            "max_spread_multiplier": 1.0
        }


def check_trading_time() -> bool:
    """Enhanced 24/7 trading time check with session awareness"""
    try:
        # Always allow trading - 24/7 mode
        current_session = get_current_trading_session()

        if current_session:
            session_name = current_session['name']
            volatility = current_session['info']['volatility']
            logger(
                f"✅ Trading ENABLED in {session_name} session ({volatility} volatility)"
            )
        else:
            logger("✅ Trading ENABLED - 24/7 mode active")

        return True  # Always allow trading

    except Exception as e:
        logger(f"❌ Error in check_trading_time: {str(e)}")
        return True  # Always default to allowing trading


def risk_management_check() -> bool:
    """Enhanced risk management"""
    try:
        global loss_streak, session_start_balance

        info = get_account_info()
        if not info or not session_start_balance:
            return True

        current_drawdown = (session_start_balance -
                            info['equity']) / session_start_balance
        if current_drawdown >= max_drawdown:
            logger(f"🛑 Max drawdown reached: {current_drawdown:.2%}")
            return False

        if not check_daily_limits():
            return False

        if loss_streak >= max_loss_streak:
            logger(f"🛑 Max loss streak reached: {loss_streak}")
            return False

        if info['margin_level'] < 300 and info['margin_level'] > 0:
            logger(f"🛑 Low margin level: {info['margin_level']:.2f}%")
            return False

        return True
    except Exception as e:
        logger(f"❌ Risk management error: {str(e)}")
        return True


def check_profit_targets() -> bool:
    """Enhanced profit target checking"""
    try:
        global session_start_balance

        info = get_account_info()
        if not info or not session_start_balance:
            return True

        current_equity = info['equity']
        session_profit = current_equity - session_start_balance
        profit_percent = (session_profit / session_start_balance) * 100

        target_percent = float(gui.profit_target_entry.get()) if gui else 5.0
        if profit_percent >= target_percent:
            logger(f"🎯 Profit target reached ({profit_percent:.2f}%)")
            close_all_orders()

            if gui and hasattr(gui, 'telegram_var') and gui.telegram_var.get():
                msg = f"🎯 PROFIT TARGET REACHED!\nProfit: ${current_equity - session_start_balance:.2f} ({profit_percent:.2f}%)\nClosing all positions..."
                send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, msg)

            return False

        return True

    except Exception as e:
        logger(f"❌ Error checking profit targets: {str(e)}")
        return True


def ai_market_analysis(symbol: str, df: pd.DataFrame) -> Dict[str, Any]:
    """Advanced AI-powered market analysis with multiple confirmation signals"""
    try:
        if len(df) < 50:
            return {"confidence": 0, "signals": [], "recommendation": "WAIT", "strength": "WEAK"}

        last = df.iloc[-1]
        prev = df.iloc[-2]
        analysis = {
            "confidence": 0,
            "signals": [],
            "recommendation": "WAIT",
            "strength": "WEAK",
            "market_structure": "UNKNOWN",
            "volatility_regime": "NORMAL",
            "trend_strength": 0.0
        }

        # Multi-timeframe trend analysis
        trend_signals = 0
        if last['EMA20'] > last['EMA50'] > last['EMA200']:
            trend_signals += 3
            analysis["signals"].append("🟢 STRONG UPTREND: EMA alignment bullish")
            analysis["market_structure"] = "BULLISH"
        elif last['EMA20'] < last['EMA50'] < last['EMA200']:
            trend_signals -= 3
            analysis["signals"].append("🔴 STRONG DOWNTREND: EMA alignment bearish")
            analysis["market_structure"] = "BEARISH"
        else:
            analysis["signals"].append("🟡 SIDEWAYS: Mixed EMA signals")
            analysis["market_structure"] = "SIDEWAYS"

        # Volatility regime detection
        atr_ratio = last['ATR_Ratio'] if 'ATR_Ratio' in last else 1.0
        if atr_ratio > 1.5:
            analysis["volatility_regime"] = "HIGH"
            analysis["signals"].append(f"⚡ HIGH VOLATILITY: ATR ratio {atr_ratio:.2f}")
        elif atr_ratio < 0.7:
            analysis["volatility_regime"] = "LOW"
            analysis["signals"].append(f"😴 LOW VOLATILITY: ATR ratio {atr_ratio:.2f}")

        # Advanced momentum analysis
        momentum_score = 0
        if last['MACD'] > last['MACD_signal'] and last['MACD_histogram'] > prev['MACD_histogram']:
            momentum_score += 2
            analysis["signals"].append("🚀 BULLISH MOMENTUM: MACD trending up")
        elif last['MACD'] < last['MACD_signal'] and last['MACD_histogram'] < prev['MACD_histogram']:
            momentum_score -= 2
            analysis["signals"].append("📉 BEARISH MOMENTUM: MACD trending down")

        # RSI divergence detection
        if last['RSI'] < 30 and last['close'] > prev['close']:
            momentum_score += 2
            analysis["signals"].append("💎 BULLISH DIVERGENCE: RSI oversold with price rise")
        elif last['RSI'] > 70 and last['close'] < prev['close']:
            momentum_score -= 2
            analysis["signals"].append("🔻 BEARISH DIVERGENCE: RSI overbought with price fall")

        # Volume confirmation (if available)
        if 'volume' in df.columns:
            vol_avg = df['volume'].rolling(20).mean().iloc[-1]
            if last['volume'] > vol_avg * 1.5:
                momentum_score += 1
                analysis["signals"].append("📊 HIGH VOLUME CONFIRMATION")

        # Support/Resistance analysis
        resistance = df['high'].rolling(20).max().iloc[-1]
        support = df['low'].rolling(20).min().iloc[-1]

        if last['close'] > resistance * 0.998:
            momentum_score += 2
            analysis["signals"].append("💥 RESISTANCE BREAKOUT")
        elif last['close'] < support * 1.002:
            momentum_score -= 2
            analysis["signals"].append("💔 SUPPORT BREAKDOWN")

        # Calculate overall confidence
        total_signals = abs(trend_signals) + abs(momentum_score)
        analysis["confidence"] = min(100, max(0, total_signals * 10))
        analysis["trend_strength"] = abs(trend_signals + momentum_score) / 10.0

        # Final recommendation with AI logic
        if trend_signals >= 2 and momentum_score >= 2 and analysis["confidence"] >= 60:
            analysis["recommendation"] = "STRONG_BUY"
            analysis["strength"] = "STRONG"
        elif trend_signals >= 1 and momentum_score >= 1 and analysis["confidence"] >= 40:
            analysis["recommendation"] = "BUY"
            analysis["strength"] = "MODERATE"
        elif trend_signals <= -2 and momentum_score <= -2 and analysis["confidence"] >= 60:
            analysis["recommendation"] = "STRONG_SELL"
            analysis["strength"] = "STRONG"
        elif trend_signals <= -1 and momentum_score <= -1 and analysis["confidence"] >= 40:
            analysis["recommendation"] = "SELL"
            analysis["strength"] = "MODERATE"
        else:
            analysis["recommendation"] = "WAIT"
            analysis["strength"] = "WEAK"

        return analysis

    except Exception as e:
        logger(f"❌ AI analysis error: {str(e)}")
        return {"confidence": 0, "signals": [f"Error: {str(e)}"], "recommendation": "WAIT", "strength": "WEAK"}


def generate_performance_report() -> str:
    """Generate comprehensive performance report"""
    try:
        info = get_account_info()
        if not info or not session_start_balance:
            return "📊 Performance Report: No data available"

        current_equity = info['equity']
        total_profit = current_equity - session_start_balance
        profit_percent = (total_profit / session_start_balance) * 100

        total_trades = session_data.get('total_trades', 0)
        winning_trades = session_data.get('winning_trades', 0)
        losing_trades = session_data.get('losing_trades', 0)

        win_rate = (winning_trades / max(total_trades, 1)) * 100

        # Calculate session duration
        start_time = session_data.get('start_time', datetime.datetime.now())
        duration = datetime.datetime.now() - start_time
        duration_hours = duration.total_seconds() / 3600

        report = f"""
📊 TRADING PERFORMANCE REPORT
═══════════════════════════════
⏰ Session Duration: {duration_hours:.1f} hours
💰 Starting Balance: ${session_start_balance:.2f}
📈 Current Equity: ${current_equity:.2f}
💵 Total P/L: ${total_profit:.2f} ({profit_percent:+.2f}%)

📈 TRADING STATISTICS:
• Total Trades: {total_trades}
• Winning Trades: {winning_trades}
• Losing Trades: {losing_trades}
• Win Rate: {win_rate:.1f}%
• Avg P/L per Hour: ${total_profit/max(duration_hours, 1):.2f}

🚀 CURRENT STATUS:
• Strategy: {current_strategy}
• Open Positions: {len(get_positions())}
• Max Drawdown: {max_drawdown*100:.1f}%
• Current Session: {get_current_trading_session()['name'] if get_current_trading_session() else 'Default'}

🚀 Bot Performance: {'EXCELLENT' if profit_percent > 2 else 'MODERATE' if profit_percent > 0 else 'NEEDS REVIEW'}
═══════════════════════════════
        """
        return report.strip()

    except Exception as e:
        return f"📊 Performance Report Error: {str(e)}"


def send_hourly_report() -> None:
    """Send hourly performance report"""
    try:
        if gui and hasattr(gui, 'telegram_var') and gui.telegram_var.get():
            report = generate_performance_report()
            send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
                          f"📊 HOURLY REPORT\n{report}")
            logger("📊 Hourly report sent to Telegram")
    except Exception as e:
        logger(f"❌ Error sending hourly report: {str(e)}")


def bot_thread() -> None:
    """Enhanced main bot trading thread with auto-recovery and performance monitoring"""
    global bot_running, disconnect_count, session_start_balance, loss_streak, current_strategy, position_count, mt5_connected

    try:
        logger("🚀 Starting enhanced trading bot thread...")

        # Ensure MT5 connection
        connection_attempts = 0
        max_attempts = 5

        while connection_attempts < max_attempts and not mt5_connected:
            logger(
                f"🔄 Bot connection attempt {connection_attempts + 1}/{max_attempts}"
            )
            if connect_mt5():
                logger("✅ Bot connected to MT5 successfully!")
                break
            else:
                connection_attempts += 1
                if connection_attempts < max_attempts:
                    time.sleep(5)

        if not mt5_connected:
            logger("❌ Bot failed to connect to MT5 after all attempts")
            bot_running = False
            if gui:
                gui.bot_status_lbl.config(text="Bot: Connection Failed 🔴",
                                          foreground="red")
            return

        # Initialize session
        info = get_account_info()
        if info:
            session_start_balance = info['balance']
            session_data['start_time'] = datetime.datetime.now()
            session_data['start_balance'] = session_start_balance
            logger(
                f"🚀 Trading session initialized. Balance: ${session_start_balance:.2f}"
            )

            # Get current strategy from GUI at start
            if gui:
                current_strategy = gui.strategy_combo.get()
                logger(f"📈 Selected strategy: {current_strategy}")

            if gui and hasattr(gui, 'telegram_var') and gui.telegram_var.get():
                msg = f"🤖 AutoBot Started\nBalance: ${session_start_balance:.2f}\nStrategy: {current_strategy}"
                send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, msg)

        # Enhanced symbol selection with session optimization
        trading_symbol = "EURUSD"  # Default fallback

        # Check current session and get optimal symbols
        current_session = get_current_trading_session()
        optimal_symbols = []

        if current_session:
            optimal_symbols = get_session_optimal_symbols(
                current_session["name"])
            logger(
                f"🌍 {current_session['name']} session optimal symbols: {', '.join(optimal_symbols[:5])}"
            )

        # Priority: User selection > Session optimal > Default
        if gui and gui.symbol_entry.get():
            user_symbol = gui.symbol_entry.get().strip().upper()

            # Special handling for gold symbols
            if "XAU" in user_symbol or "GOLD" in user_symbol:
                detected_gold = detect_gold_symbol()
                if detected_gold:
                    trading_symbol = detected_gold
                    logger(f"🎯 Auto-detected gold symbol: {trading_symbol}")
                    if gui:
                        gui.symbol_var.set(trading_symbol)
                else:
                    logger(f"⚠️ Cannot detect gold symbol, trying manual validation...")
                    if validate_and_activate_symbol(user_symbol):
                        trading_symbol = user_symbol
                        logger(f"🎯 Using user-selected symbol: {trading_symbol}")
                    else:
                        logger(f"❌ Invalid gold symbol {user_symbol}, using fallback")
            elif validate_and_activate_symbol(user_symbol):
                trading_symbol = user_symbol
                logger(f"🎯 Using user-selected symbol: {trading_symbol}")
            else:
                # Try session optimal symbols if user symbol fails
                for symbol in optimal_symbols:
                    if validate_and_activate_symbol(symbol):
                        trading_symbol = symbol
                        logger(
                            f"🎯 User symbol failed, using session optimal: {trading_symbol}"
                        )
                        if gui:
                            gui.symbol_var.set(trading_symbol)
                        break
                else:
                    logger(
                        f"❌ Invalid symbol {user_symbol}, using fallback: {trading_symbol}"
                    )
                    if gui:
                        gui.symbol_var.set(trading_symbol)
        else:
            # No user selection, use session optimal
            for symbol in optimal_symbols:
                if validate_and_activate_symbol(symbol):
                    trading_symbol = symbol
                    logger(f"🎯 Using session optimal symbol: {trading_symbol}")
                    if gui:
                        gui.symbol_var.set(trading_symbol)
                    break

        # Get timeframe
        timeframe_map = {
            "M1": mt5.TIMEFRAME_M1,
            "M3": mt5.TIMEFRAME_M3,
            "M5": mt5.TIMEFRAME_M5,
            "M10": mt5.TIMEFRAME_M10,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1
        }
        timeframe = timeframe_map.get(
            gui.timeframe_combo.get() if gui else "M1", mt5.TIMEFRAME_M1)

        logger(
            f"📊 Bot configuration: {trading_symbol} | {gui.timeframe_combo.get() if gui else 'M1'} | Strategy: {current_strategy}"
        )
        logger(
            "🎯 Enhanced auto-trading active - executing orders on valid signals!"
        )

        # Main trading loop
        last_candle_time = None
        consecutive_failures = 0
        max_failures = 10
        signal_check_counter = 0

        while bot_running:
            try:
                # Check MT5 connection
                if not check_mt5_status():
                    disconnect_count += 1
                    logger(f"⚠️ MT5 disconnected (count: {disconnect_count})")

                    if disconnect_count > 3:
                        logger(
                            "🛑 Too many disconnections. Attempting reconnect..."
                        )
                        if connect_mt5():
                            disconnect_count = 0
                            logger("✅ Reconnected successfully!")
                        else:
                            logger("🛑 Reconnection failed. Stopping bot.")
                            break
                    time.sleep(5)
                    continue
                else:
                    disconnect_count = 0

                # Update current strategy from GUI every loop and ensure GUI connection
                if gui and hasattr(gui, 'strategy_combo'):
                    try:
                        new_strategy = gui.strategy_combo.get()
                        if new_strategy != current_strategy:
                            current_strategy = new_strategy
                            logger(
                                f"🔄 Strategy updated from GUI to: {current_strategy}"
                            )
                    except Exception as e:
                        logger(f"⚠️ GUI connection issue: {str(e)}")
                        # Fallback to default strategy if GUI not accessible
                        if not current_strategy:
                            current_strategy = "Scalping"

                # Risk management checks
                if not risk_management_check():
                    logger("🛑 Risk management stop triggered")
                    break

                if not check_profit_targets():
                    logger("🎯 Profit target reached. Stopping bot.")
                    break

                if not check_trading_time():
                    time.sleep(60)
                    continue

                # Get market data with more aggressive refresh
                df = get_symbol_data(trading_symbol, timeframe)
                if df is None or len(df) < 50:
                    consecutive_failures += 1
                    if consecutive_failures >= max_failures:
                        logger(
                            f"🛑 Too many data failures for {trading_symbol}")
                        break
                    logger("⚠️ Insufficient market data, retrying...")
                    time.sleep(3)  # Reduced from 5 to 3 seconds
                    continue
                else:
                    consecutive_failures = 0

                # Check for new candle - more aggressive signal checking
                current_candle_time = df.iloc[-1]['time']
                is_new_candle = last_candle_time is None or current_candle_time != last_candle_time

                # More aggressive signal checking based on strategy
                signal_check_counter += 1

                # HFT needs much faster checking
                if current_strategy == "HFT":
                    force_check = signal_check_counter >= 1  # Check every 1 second for HFT
                elif current_strategy == "Scalping":
                    force_check = signal_check_counter >= 2  # Check every 2 seconds for Scalping
                else:
                    force_check = signal_check_counter >= 3  # Check every 3 seconds for others

                if not is_new_candle and not force_check:
                    # Shorter sleep for HFT
                    sleep_interval = BOT_LOOP_INTERVALS.get(current_strategy, 2.0)
                    time.sleep(sleep_interval)
                    continue

                if force_check:
                    signal_check_counter = 0

                last_candle_time = current_candle_time

                # Calculate indicators
                df = calculate_indicators(df)

                # Perform AI market analysis before strategy execution
                ai_analysis = ai_market_analysis(trading_symbol, df)
                logger(f"🤖 AI Market Analysis Results:")
                logger(f"   📊 Recommendation: {ai_analysis['recommendation']}")
                logger(f"   🎯 Confidence: {ai_analysis['confidence']}%")
                logger(f"   📈 Market Structure: {ai_analysis['market_structure']}")
                logger(f"   ⚡ Volatility Regime: {ai_analysis['volatility_regime']}")

                for signal in ai_analysis['signals'][:3]:  # Show top 3 AI signals
                    logger(f"   {signal}")

                # Run strategy with current strategy from GUI
                logger(
                    f"🎯 Analyzing {current_strategy} signals for {trading_symbol}..."
                )
                action, signals = run_strategy(current_strategy, df,
                                               trading_symbol)

                # AI Override: If AI has very high confidence, consider it
                if ai_analysis['confidence'] >= 80:
                    if ai_analysis['recommendation'] == 'STRONG_BUY' and not action:
                        action = 'BUY'
                        signals.append("🤖 AI OVERRIDE: High confidence BUY signal")
                        logger("🤖 AI OVERRIDE: Activating BUY based on high AI confidence")
                    elif ai_analysis['recommendation'] == 'STRONG_SELL' and not action:
                        action = 'SELL'
                        signals.append("🤖 AI OVERRIDE: High confidence SELL signal")
                        logger("🤖 AI OVERRIDE: Activating SELL based on high AI confidence")

                # Update position count
                positions = get_positions()
                position_count = len(positions)

                # --- Enhanced Signal Accuracy with Multi-Confirmation System ---
                signal_strength_score = 0
                confirmation_count = 0

                # Calculate overall signal strength score
                for signal in signals:
                    if any(keyword in signal for keyword in ["✅", "STRONG", "HIGH"]):
                        signal_strength_score += 2
                        confirmation_count += 1
                    elif any(keyword in signal for keyword in ["🔧", "DEBUG", "basic"]):
                        signal_strength_score += 0.5
                    else:
                        signal_strength_score += 1

                # Multi-confirmation requirement based on strategy
                min_confirmations = {
                    "Scalping": 2,  # Need at least 2 strong confirmations
                    "HFT": 1,       # Fastest execution
                    "Intraday": 3,  # More conservative
                    "Arbitrage": 2  # Mean reversion needs confirmation
                }

                required_confirmations = min_confirmations.get(current_strategy, 2)

                # UNIFIED CONFIRMATION SYSTEM - Fix threshold inconsistencies
                if action:
                    # Use the SAME threshold for both signal generation and confirmation
                    actual_signal_strength = max(buy_signals, sell_signals)
                    meets_threshold = actual_signal_strength >= threshold

                    # Additional confirmation for quality
                    quality_signals = sum(1 for s in signals if any(keyword in s for keyword in ["✅", "STRONG", "AI-", "🤖"]))
                    has_quality = quality_signals >= 1 or ai_analysis['confidence'] > 50

                    if meets_threshold and has_quality:
                        logger(f"✅ SIGNAL APPROVED: Strength {actual_signal_strength}/{threshold}, Quality signals: {quality_signals}")
                        logger(f"📊 AI Confidence: {ai_analysis['confidence']}%, Market: {ai_analysis['market_structure']}")
                    elif meets_threshold:
                        logger(f"⚠️ SIGNAL APPROVED (Basic): Strength {actual_signal_strength}/{threshold}, Low quality")
                    else:
                        logger(f"❌ SIGNAL REJECTED: Strength {actual_signal_strength}/{threshold} insufficient")
                        action = None

                logger(
                    f"📊 Final Signal Analysis: Action={action}, Strength={max(buy_signals, sell_signals)}/{threshold}, Quality={quality_signals if 'quality_signals' in locals() else 0}, Positions={position_count}/{max_positions}"
                )
                # --- End of Enhanced Signal Accuracy ---


                # Log all signals for debugging
                if signals:
                    logger(
                        f"🎯 All detected signals:"
                    )
                    for i, signal in enumerate(signals):
                        logger(f"   {i+1}. {signal}")
                else:
                    logger("⚠️ No signals detected this cycle")

                # AGGRESSIVE OPPORTUNITY MODE - Don't miss trading chances
                if not action and len(signals) > 0:
                    # Count signal types
                    buy_signal_count = sum(1 for s in signals if any(word in s.lower() for word in ["buy", "bullish", "up", "long"]))
                    sell_signal_count = sum(1 for s in signals if any(word in s.lower() for word in ["sell", "bearish", "down", "short"]))

                    logger(f"🎯 OPPORTUNITY EVALUATION: BUY signals={buy_signal_count}, SELL signals={sell_signal_count}")

                    # Force action if we have clear directional bias
                    if buy_signal_count > sell_signal_count and buy_signal_count >= 1:
                        action = "BUY"
                        logger(f"🎯 OPPORTUNITY: Forcing BUY based on {buy_signal_count} directional signals")
                    elif sell_signal_count > buy_signal_count and sell_signal_count >= 1:
                        action = "SELL"
                        logger(f"🎯 OPPORTUNITY: Forcing SELL based on {sell_signal_count} directional signals")

                    # Additional opportunity check - if no trades today, be more aggressive
                    recent_trades = session_data.get('total_trades', 0)
                    if not action and recent_trades == 0 and len(signals) >= 1:
                        # Take any direction if no trades yet
                        if any("opportunity" in s.lower() for s in signals):
                            if current_price > last_close:
                                action = "BUY"
                                logger("🎯 FIRST TRADE OPPORTUNITY: Taking BUY on upward movement")
                            else:
                                action = "SELL"
                                logger("🎯 FIRST TRADE OPPORTUNITY: Taking SELL on downward movement")

                # Execute trading signals with proper GUI parameter integration
                if action and position_count < max_positions:
                    logger(
                        f"🚀 EXECUTING {action} ORDER for {trading_symbol} using {current_strategy} strategy"
                    )
                    logger(f"📊 Strategy signals detected: {len(signals)}")

                    # Get ALL parameters from GUI with proper validation
                    lot_size = gui.get_current_lot() if gui else 0.01
                    tp_value = gui.get_current_tp() if gui else "20"
                    sl_value = gui.get_current_sl() if gui else "10"
                    tp_unit = gui.get_current_tp_unit() if gui else "pips"
                    sl_unit = gui.get_current_sl_unit() if gui else "pips"

                    # Log the exact parameters being used
                    logger(f"📋 Using GUI parameters:")
                    logger(f"   Strategy: {current_strategy}")
                    logger(f"   Lot: {lot_size}")
                    logger(f"   TP: {tp_value} {tp_unit}")
                    logger(f"   SL: {sl_value} {sl_unit}")

                    # Execute order with exact GUI parameters
                    result = open_order(trading_symbol, lot_size, action,
                                        sl_value, tp_value, sl_unit, tp_unit)

                    if result and getattr(result, 'retcode',
                                          None) == mt5.TRADE_RETCODE_DONE:
                        logger(
                            f"✅ {action} order executed successfully with {current_strategy}! Ticket: {result.order}"
                        )
                        consecutive_failures = 0

                        session_data['total_trades'] += 1
                        session_data['daily_orders'] += 1

                        if gui and hasattr(
                                gui,
                                'telegram_var') and gui.telegram_var.get():
                            msg = f"🚀 {action} Order Executed!\nSymbol: {trading_symbol}\nStrategy: {current_strategy}\nTicket: {result.order}\nTP: {tp_value} {tp_unit}\nSL: {sl_value} {sl_unit}"
                            send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
                                          msg)
                    else:
                        consecutive_failures += 1
                        logger(
                            f"❌ Order execution failed. Failure count: {consecutive_failures}"
                        )

                elif action and position_count >= max_positions:
                    logger(
                        f"⚠️ Max positions reached ({position_count}). Skipping {action} signal from {current_strategy}."
                    )

                # Log periodic status for debugging
                # --- Enhanced Performance Monitoring with Real-time Metrics ---
                if time.time() % 30 < 3:  # Every 30 seconds instead of 60
                    try:
                        current_price = df['close'].iloc[-1]
                        session_info = get_current_trading_session()
                        session_name = session_info["name"] if session_info else "Default"
                        volatility = session_info["info"]["volatility"] if session_info else "unknown"

                        # Enhanced performance metrics
                        account_info = get_account_info()
                        if account_info and session_start_balance:
                            equity = account_info['equity']
                            daily_pnl = equity - session_start_balance
                            daily_pnl_percent = (daily_pnl / session_start_balance) * 100

                            # Calculate win rate
                            total_trades_stat = session_data.get('winning_trades', 0) + session_data.get('losing_trades', 0)
                            win_rate = (session_data.get('winning_trades', 0) / max(total_trades_stat, 1)) * 100

                            logger(
                                f"💹 Enhanced Status: {trading_symbol}@{current_price:.5f} | {current_strategy} | {session_name}({volatility})"
                            )
                            logger(
                                f"📊 Performance: P/L ${daily_pnl:+.2f} ({daily_pnl_percent:+.2f}%) | WR {win_rate:.1f}% | Pos {position_count}/{max_positions}"
                            )
                        else:
                            logger(
                                f"💹 Status: {trading_symbol}@{current_price:.5f} | {current_strategy} | {session_name}({volatility}) | Pos:{position_count}/{max_positions}"
                            )
                    except Exception as status_e:
                        logger(f"⚠️ Status logging error: {str(status_e)}")
                        pass
                # --- End of Enhanced Performance Monitoring ---

                # Enhanced monitoring and auto-recovery checks
                if signal_check_counter % 100 == 0:  # Every 100 cycles
                    auto_recovery_check()

                # Hourly performance report
                if signal_check_counter % 3600 == 0:  # Approximately every hour
                    send_hourly_report()

                # Strategy-specific sleep intervals using configuration
                sleep_interval = BOT_LOOP_INTERVALS.get(current_strategy, 2.0)
                time.sleep(sleep_interval)

            except Exception as e:
                logger(f"❌ Bot loop error: {str(e)}")
                consecutive_failures += 1

                # Auto-recovery attempt
                if consecutive_failures >= 3:
                    logger(
                        "🔄 Multiple failures detected, attempting auto-recovery..."
                    )
                    if auto_recovery_check():
                        consecutive_failures = 0
                        logger(
                            "✅ Auto-recovery successful, continuing trading..."
                        )

                if consecutive_failures >= max_failures:
                    logger("🛑 Too many consecutive errors. Stopping bot.")
                    break
                time.sleep(3)

    except Exception as e:
        logger(f"❌ Bot thread error: {str(e)}")

        # Final recovery attempt
        if gui and hasattr(gui, 'telegram_var') and gui.telegram_var.get():
            send_telegram(
                TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
                f"🚨 Bot thread crashed: {str(e)}\nAttempting restart...")

    finally:
        bot_running = False
        logger("🛑 Bot thread stopped")
        if gui:
            gui.bot_status_lbl.config(text="Bot: Stopped 🔴",
                                      foreground="red")


def start_auto_recovery_monitor():
    """Background monitoring thread for auto-recovery"""

    def recovery_monitor():
        while True:
            try:
                if bot_running:
                    auto_recovery_check()
                time.sleep(30)  # Check every 30 seconds
            except Exception as e:
                logger(f"❌ Recovery monitor error: {str(e)}")
                time.sleep(60)

    recovery_thread = threading.Thread(target=recovery_monitor, daemon=True)
    recovery_thread.start()
    logger("🔄 Auto-recovery monitor started")


class TradingBotGUI:

    def __init__(self, root):
        self.root = root
        self.root.title(
            "💹 MT5 ADVANCED AUTO TRADING BOT v4.0 - Premium Edition")
        self.root.geometry("1400x900")
        self.root.configure(bg="#0f0f0f")
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)

        self.current_strategy = "Scalping"

        self.create_widgets()

        # Initialize GUI states
        self.start_btn.config(state="disabled")
        self.close_btn.config(state="disabled")
        self.emergency_btn.config(state="normal")

        # Auto-connect on startup
        self.root.after(1000, self.auto_connect_mt5)

        # Start GUI updates
        self.root.after(2000, self.update_gui_data)

        # Start auto-recovery monitoring
        start_auto_recovery_monitor()

    def auto_connect_mt5(self):
        """Enhanced auto-connection on startup with better error handling"""
        try:
            self.log("🔄 Starting auto-connection to MetaTrader 5...")
            self.log(
                "💡 PASTIKAN: MT5 sudah dijalankan dan login ke akun trading")
            self.log("💡 PENTING: MT5 harus dijalankan sebagai Administrator")
            self.status_lbl.config(text="Status: Connecting... 🔄",
                                   foreground="orange")
            self.root.update()

            # Show system info first
            import platform
            import sys
            self.log(
                f"🔍 Python: {sys.version.split()[0]} ({platform.architecture()[0]})"
            )
            self.log(f"🔍 Platform: {platform.system()} {platform.release()}")

            if connect_mt5():
                self.log("🎉 SUCCESS: Auto-connected to MetaTrader 5!")
                self.status_lbl.config(text="Status: Connected ✅",
                                       foreground="green")
                self.update_symbols()
                self.start_btn.config(state="normal")
                self.close_btn.config(state="normal")
                self.connect_btn.config(state="disabled")

                # Show detailed connection info
                try:
                    info = get_account_info()
                    if info:
                        self.log(
                            f"👤 Account: {info.get('login', 'N/A')} | Server: {info.get('server', 'N/A')}"
                        )
                        self.log(
                            f"💰 Balance: ${info.get('balance', 0):.2f} | Equity: ${info.get('equity', 0):.2f}"
                        )
                        self.log(
                            f"🔐 Trade Permission: {'✅' if info.get('balance', 0) > 0 else '⚠️'}"
                        )

                        # Update global session balance
                        global session_start_balance
                        session_start_balance = info.get('balance', 0)

                        self.log(
                            "🚀 GUI-MT5 connection established successfully!")
                        self.log("🚀 Ready to start automated trading!")
                except Exception as info_e:
                    self.log(
                        f"⚠️ Error getting account details: {str(info_e)}")

            else:
                self.log("❌ FAILED: Auto-connection to MT5 failed")
                self.log("🔧 TROUBLESHOOTING WAJIB:")
                self.log("   1. 🔴 TUTUP MT5 SEPENUHNYA")
                self.log("   2. 🔴 KLIK KANAN MT5 → 'Run as Administrator'")
                self.log(
                    "   3. 🔴 LOGIN ke akun trading dengan kredensial yang benar")
                self.log("   4. 🔴 PASTIKAN status 'Connected' muncul di MT5")
                self.log(
                    "   5. 🔴 BUKA Market Watch dan tambahkan symbols (EURUSD, dll)"
                )
                self.log("   6. 🔴 PASTIKAN Python dan MT5 sama-sama 64-bit")
                self.log("   7. 🔴 DISABLE antivirus sementara jika perlu")
                self.log("   8. 🔴 RESTART komputer jika masalah persisten")

                self.status_lbl.config(text="Status: Connection Failed ❌",
                                       foreground="red")

                # Enable manual connect button and keep trying
                self.connect_btn.config(state="normal")
                self.start_btn.config(state="disabled")
                self.close_btn.config(state="disabled")

                # Show error in account labels
                self.balance_lbl.config(text="Balance: N/A", foreground="gray")
                self.equity_lbl.config(text="Equity: N/A", foreground="gray")
                self.margin_lbl.config(text="Free Margin: N/A",
                                       foreground="gray")
                self.margin_level_lbl.config(text="Margin Level: N/A",
                                             foreground="gray")
                self.server_lbl.config(text="Server: N/A")

        except Exception as e:
            error_msg = f"❌ CRITICAL: Auto-connection error: {str(e)}"
            self.log(error_msg)
            self.status_lbl.config(text="Status: Critical Error ❌",
                                   foreground="red")

    def create_widgets(self):
        """Enhanced GUI creation with better layout"""
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#0f0f0f")
        style.configure("TLabel",
                        background="#0f0f0f",
                        foreground="white",
                        font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 10, "bold"))
        style.configure("TNotebook.Tab",
                        background="#2e2e2e",
                        foreground="white")
        style.configure("Accent.TButton",
                        foreground="white",
                        background="#4CAF50")

        # Main notebook
        tab_control = ttk.Notebook(self.root)
        tab_control.grid(row=0, column=0, sticky="nsew")

        # Create tabs
        self.dashboard_tab = ttk.Frame(tab_control)
        self.strategy_tab = ttk.Frame(tab_control)
        self.calculator_tab = ttk.Frame(tab_control)
        self.log_tab = ttk.Frame(tab_control)

        tab_control.add(self.dashboard_tab, text="📊 Dashboard")
        tab_control.add(self.strategy_tab, text="⚙️ Strategy Setup")
        tab_control.add(self.calculator_tab, text="🧮 Calculator")
        tab_control.add(self.log_tab, text="📝 Logs")

        # Build tab contents
        self.dashboard_tab.rowconfigure(3, weight=1)
        self.dashboard_tab.columnconfigure(0, weight=1)
        self.build_dashboard()
        self.build_strategy_tab()
        self.build_calculator_tab()
        self.build_log_tab()

    def build_dashboard(self):
        """Enhanced dashboard with better layout"""
        # Control Panel
        ctrl_frame = ttk.LabelFrame(self.dashboard_tab,
                                    text="🎛️ Control Panel")
        ctrl_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        # Row 1: Symbol and Timeframe
        ttk.Label(ctrl_frame, text="Symbol:").grid(row=0,
                                                   column=0,
                                                   padx=5,
                                                   pady=5,
                                                   sticky="w")
        self.symbol_var = tk.StringVar(value="EURUSD")
        self.symbol_entry = ttk.Combobox(ctrl_frame,
                                         textvariable=self.symbol_var,
                                         width=12)
        self.symbol_entry.bind('<Return>', self.on_symbol_validate)
        self.symbol_entry.grid(row=0, column=1, padx=5, pady=5)

        self.validate_symbol_btn = ttk.Button(ctrl_frame,
                                              text="✓",
                                              command=self.validate_symbol,
                                              width=3)
        self.validate_symbol_btn.grid(row=0, column=2, padx=2, pady=5)

        ttk.Label(ctrl_frame, text="Timeframe:").grid(row=0,
                                                      column=3,
                                                      padx=5,
                                                      pady=5,
                                                      sticky="w")
        self.timeframe_combo = ttk.Combobox(
            ctrl_frame, values=["M1", "M5", "M15", "M30", "H1", "H4"], width=8)
        self.timeframe_combo.set("M1")
        self.timeframe_combo.grid(row=0, column=4, padx=5, pady=5)

        ttk.Label(ctrl_frame, text="Strategy:").grid(row=0,
                                                     column=5,
                                                     padx=5,
                                                     pady=5,
                                                     sticky="w")
        self.strategy_combo = ttk.Combobox(
            ctrl_frame,
            values=["Scalping", "Intraday", "HFT", "Arbitrage"],
            width=10)
        self.strategy_combo.set("Scalping")
        self.strategy_combo.bind("<<ComboboxSelected>>",
                                 self.on_strategy_change)
        self.strategy_combo.grid(row=0, column=6, padx=5, pady=5)

        # Row 2: Connection and Control Buttons
        self.connect_btn = ttk.Button(ctrl_frame,
                                      text="🔌 Connect MT5",
                                      command=self.connect_mt5)
        self.connect_btn.grid(row=1,
                              column=0,
                              columnspan=2,
                              padx=5,
                              pady=5,
                              sticky="ew")

        self.start_btn = ttk.Button(ctrl_frame,
                                    text="🚀 START BOT",
                                    command=self.start_bot,
                                    style="Accent.TButton")
        self.start_btn.grid(row=1,
                            column=2,
                            columnspan=2,
                            padx=5,
                            pady=5,
                            sticky="ew")

        self.stop_btn = ttk.Button(ctrl_frame,
                                   text="⏹️ STOP BOT",
                                   command=self.stop_bot)
        self.stop_btn.grid(row=1, column=4, padx=5, pady=5, sticky="ew")

        self.close_btn = ttk.Button(ctrl_frame,
                                    text="❌ CLOSE ALL",
                                    command=self.close_all)
        self.close_btn.grid(row=1, column=5, padx=5, pady=5, sticky="ew")

        self.emergency_btn = ttk.Button(ctrl_frame,
                                        text="🚨 EMERGENCY",
                                        command=self.emergency_stop)
        self.emergency_btn.grid(row=1, column=6, padx=5, pady=5, sticky="ew")

        # Account Information
        acc_frame = ttk.LabelFrame(self.dashboard_tab,
                                   text="💰 Account Information")
        acc_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")

        self.balance_lbl = ttk.Label(acc_frame,
                                     text="Balance: $0.00",
                                     font=("Segoe UI", 11, "bold"))
        self.equity_lbl = ttk.Label(acc_frame,
                                    text="Equity: $0.00",
                                    font=("Segoe UI", 11))
        self.margin_lbl = ttk.Label(acc_frame,
                                    text="Free Margin: $0.00",
                                    font=("Segoe UI", 11))
        self.margin_level_lbl = ttk.Label(acc_frame,
                                          text="Margin Level: 0%",
                                          font=("Segoe UI", 11))
        self.status_lbl = ttk.Label(acc_frame,
                                    text="Status: Disconnected",
                                    font=("Segoe UI", 11, "bold"))
        self.server_lbl = ttk.Label(acc_frame,
                                    text="Server: N/A",
                                    font=("Segoe UI", 10))

        self.balance_lbl.grid(row=0, column=0, padx=10, pady=5, sticky="w")
        self.equity_lbl.grid(row=0, column=1, padx=10, pady=5, sticky="w")
        self.margin_lbl.grid(row=0, column=2, padx=10, pady=5, sticky="w")
        self.margin_level_lbl.grid(row=1,
                                   column=0,
                                   padx=10,
                                   pady=5,
                                   sticky="w")
        self.status_lbl.grid(row=1, column=1, padx=10, pady=5, sticky="w")
        self.server_lbl.grid(row=1, column=2, padx=10, pady=5, sticky="w")

        # Trading Statistics with Session Info
        stats_frame = ttk.LabelFrame(self.dashboard_tab,
                                     text="📈 Trading Statistics")
        stats_frame.grid(row=2, column=0, padx=10, pady=5, sticky="ew")

        self.daily_orders_lbl = ttk.Label(stats_frame, text="Daily Orders: 0")
        self.daily_profit_lbl = ttk.Label(stats_frame,
                                          text="Daily Profit: $0.00")
        self.win_rate_lbl = ttk.Label(stats_frame, text="Win Rate: 0%")
        self.open_positions_lbl = ttk.Label(stats_frame,
                                            text="Open Positions: 0")
        self.session_lbl = ttk.Label(stats_frame,
                                     text="Session: Loading...",
                                     font=("Segoe UI", 10, "bold"))
        self.bot_status_lbl = ttk.Label(stats_frame,
                                        text="Bot: Stopped 🔴",
                                        font=("Segoe UI", 10, "bold"))

        self.daily_orders_lbl.grid(row=0,
                                   column=0,
                                   padx=10,
                                   pady=5,
                                   sticky="w")
        self.daily_profit_lbl.grid(row=0,
                                   column=1,
                                   padx=10,
                                   pady=5,
                                   sticky="w")
        self.win_rate_lbl.grid(row=0, column=2, padx=10, pady=5, sticky="w")
        self.open_positions_lbl.grid(row=0,
                                     column=3,
                                     padx=10,
                                     pady=5,
                                     sticky="w")
        self.session_lbl.grid(row=1,
                              column=0,
                              columnspan=2,
                              padx=10,
                              pady=5,
                              sticky="w")
        self.bot_status_lbl.grid(row=1,
                                 column=2,
                                 columnspan=2,
                                 padx=10,
                                 pady=5,
                                 sticky="w")

        # Active Positions
        pos_frame = ttk.LabelFrame(self.dashboard_tab,
                                   text="📋 Active Positions")
        pos_frame.grid(row=3, column=0, padx=10, pady=10, sticky="nsew")

        columns = ("Ticket", "Symbol", "Type", "Lot", "Price", "Current",
                   "Profit", "Pips")
        self.pos_tree = ttk.Treeview(pos_frame,
                                     columns=columns,
                                     show="headings",
                                     height=15)

        for col in columns:
            self.pos_tree.heading(col, text=col)
            self.pos_tree.column(col, anchor="center", width=100)

        pos_scrollbar = ttk.Scrollbar(pos_frame,
                                      orient="vertical",
                                      command=self.pos_tree.yview)
        self.pos_tree.configure(yscrollcommand=pos_scrollbar.set)

        self.pos_tree.pack(side="left", fill="both", expand=True)
        pos_scrollbar.pack(side="right", fill="y")

    def build_strategy_tab(self):
        """Enhanced strategy configuration tab"""
        self.strategy_tab.columnconfigure((0, 1), weight=1)

        strategies = ["Scalping", "Intraday", "HFT", "Arbitrage"]
        self.strategy_params = {}

        for i, strat in enumerate(strategies):
            frame = ttk.LabelFrame(self.strategy_tab,
                                   text=f"🎯 {strat} Strategy")
            frame.grid(row=i // 2,
                       column=i % 2,
                       padx=10,
                       pady=10,
                       sticky="nsew")

            defaults = {
                "Scalping": {
                    "lot": "0.01",
                    "tp": "15",
                    "sl": "8"
                },  # Scalping: Quick 10-15 pip profits
                "Intraday": {
                    "lot": "0.02",
                    "tp": "80",
                    "sl": "40"
                },  # Intraday: Larger moves 60-100 pips
                "HFT": {
                    "lot": "0.005",  # Smaller lots for ultra-fast trading
                    "tp": "2",       # Very small targets 1-3 pips
                    "sl": "1"        # Very tight stops 0.5-1 pips
                },  # HFT: Micro-movements with high frequency
                "Arbitrage": {
                    "lot": "0.02",
                    "tp": "20",      # Mean reversion targets
                    "sl": "15"       # Slightly wider stops for reversion
                }  # Arbitrage: Statistical mean reversion
            }

            ttk.Label(frame, text="Lot Size:").grid(row=0,
                                                    column=0,
                                                    padx=5,
                                                    pady=5,
                                                    sticky="w")
            lot_entry = ttk.Entry(frame, width=15)
            lot_entry.insert(0, defaults[strat]["lot"])
            lot_entry.grid(row=0, column=1, padx=5, pady=5)

            ttk.Label(frame, text="TP:").grid(row=1,
                                              column=0,
                                              padx=5,
                                              pady=5,
                                              sticky="w")
            tp_entry = ttk.Entry(frame, width=10)
            tp_entry.insert(0, defaults[strat]["tp"])
            tp_entry.grid(row=1, column=1, padx=5, pady=5)

            tp_unit_combo = ttk.Combobox(frame,
                                         values=["pips", "price", "%", "currency", "USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "NZD"],
                                         width=10)
            tp_unit_combo.set("pips")
            tp_unit_combo.grid(row=1, column=2, padx=5, pady=5)

            ttk.Label(frame, text="SL:").grid(row=2,
                                              column=0,
                                              padx=5,
                                              pady=5,
                                              sticky="w")
            sl_entry = ttk.Entry(frame, width=10)
            sl_entry.insert(0, defaults[strat]["sl"])
            sl_entry.grid(row=2, column=1, padx=5, pady=5)

            sl_unit_combo = ttk.Combobox(frame,
                                         values=["pips", "price", "%", "currency", "USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "NZD"],
                                         width=10)
            sl_unit_combo.set("pips")
            sl_unit_combo.grid(row=2, column=2, padx=5, pady=5)

            self.strategy_params[strat] = {
                "lot": lot_entry,
                "tp": tp_entry,
                "sl": sl_entry,
                "tp_unit": tp_unit_combo,
                "sl_unit": sl_unit_combo
            }

        # Global Settings
        settings_frame = ttk.LabelFrame(self.strategy_tab,
                                        text="⚙️ Global Settings")
        settings_frame.grid(row=2,
                            column=0,
                            columnspan=2,
                            padx=10,
                            pady=10,
                            sticky="ew")

        ttk.Label(settings_frame, text="Max Positions:").grid(row=0,
                                                              column=0,
                                                              padx=5,
                                                              pady=5,
                                                              sticky="w")
        self.max_pos_entry = ttk.Entry(settings_frame, width=15)
        self.max_pos_entry.insert(0, "5")
        self.max_pos_entry.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(settings_frame, text="Max Drawdown (%):").grid(row=0,
                                                                 column=2,
                                                                 padx=5,
                                                                 pady=5,
                                                                 sticky="w")
        self.max_dd_entry = ttk.Entry(settings_frame, width=15)
        self.max_dd_entry.insert(0, "3")
        self.max_dd_entry.grid(row=0, column=3, padx=5, pady=5)

        ttk.Label(settings_frame, text="Profit Target (%):").grid(row=1,
                                                                  column=0,
                                                                  padx=5,
                                                                  pady=5,
                                                                  sticky="w")
        self.profit_target_entry = ttk.Entry(settings_frame, width=15)
        self.profit_target_entry.insert(0, "5")
        self.profit_target_entry.grid(row=1, column=1, padx=5, pady=5)

        self.telegram_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(settings_frame,
                        text="📱 Telegram Notifications",
                        variable=self.telegram_var).grid(row=1,
                                                         column=2,
                                                         columnspan=2,
                                                         padx=5,
                                                         pady=5,
                                                         sticky="w")

        # Enhanced Risk Management Section
        risk_frame = ttk.LabelFrame(self.strategy_tab,
                                    text="⚠️ Advanced Risk Management")
        risk_frame.grid(row=3,
                        column=0,
                        columnspan=2,
                        padx=10,
                        pady=10,
                        sticky="ew")

        ttk.Label(risk_frame, text="Auto Lot Sizing:").grid(row=0,
                                                            column=0,
                                                            padx=5,
                                                            pady=5,
                                                            sticky="w")
        self.auto_lot_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(risk_frame, text="Enable",
                        variable=self.auto_lot_var).grid(row=0,
                                                         column=1,
                                                         padx=5,
                                                         pady=5,
                                                         sticky="w")

        ttk.Label(risk_frame, text="Risk % per Trade:").grid(row=0,
                                                             column=2,
                                                             padx=5,
                                                             pady=5,
                                                             sticky="w")
        self.risk_percent_entry = ttk.Entry(risk_frame, width=10)
        self.risk_percent_entry.insert(0, "1.0")
        self.risk_percent_entry.grid(row=0, column=3, padx=5, pady=5)

        ttk.Label(risk_frame, text="Emergency Close DD:").grid(row=1,
                                                               column=0,
                                                               padx=5,
                                                               pady=5,
                                                               sticky="w")
        self.emergency_dd_entry = ttk.Entry(risk_frame, width=10)
        self.emergency_dd_entry.insert(0, "5.0")
        self.emergency_dd_entry.grid(row=1, column=1, padx=5, pady=5)

        # Performance tracking
        perf_frame = ttk.LabelFrame(self.strategy_tab,
                                    text="📊 Performance Tracking")
        perf_frame.grid(row=4,
                        column=0,
                        columnspan=2,
                        padx=10,
                        pady=10,
                        sticky="ew")

        self.auto_report_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(perf_frame,
                        text="📱 Hourly Reports",
                        variable=self.auto_report_var).grid(row=0,
                                                            column=0,
                                                            padx=5,
                                                            pady=5,
                                                            sticky="w")

        ttk.Button(perf_frame,
                   text="📊 Generate Report",
                   command=self.generate_report_now).grid(row=0,
                                                          column=1,
                                                          padx=5,
                                                          pady=5)

        ttk.Button(perf_frame,
                   text="🔄 Recovery Test",
                   command=self.test_recovery).grid(row=0,
                                                    column=2,
                                                    padx=5,
                                                    pady=5)

    def build_calculator_tab(self):
        """Enhanced calculator tab"""
        calc_frame = ttk.LabelFrame(self.calculator_tab,
                                    text="🧮 TP/SL Calculator")
        calc_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Input section
        input_frame = ttk.Frame(calc_frame)
        input_frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(input_frame, text="Symbol:").grid(row=0,
                                                    column=0,
                                                    padx=5,
                                                    pady=5,
                                                    sticky="w")
        self.calc_symbol_entry = ttk.Entry(input_frame, width=15)
        self.calc_symbol_entry.insert(0, "EURUSD")
        self.calc_symbol_entry.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(input_frame, text="Lot Size:").grid(row=0,
                                                      column=2,
                                                      padx=5,
                                                      pady=5,
                                                      sticky="w")
        self.calc_lot_entry = ttk.Entry(input_frame, width=15)
        self.calc_lot_entry.insert(0, "0.01")
        self.calc_lot_entry.grid(row=0, column=3, padx=5, pady=5)

        ttk.Label(input_frame, text="TP:").grid(row=1,
                                                column=0,
                                                padx=5,
                                                pady=5,
                                                sticky="w")
        self.calc_tp_entry = ttk.Entry(input_frame, width=10)
        self.calc_tp_entry.grid(row=1, column=1, padx=5, pady=5)

        self.calc_tp_unit = ttk.Combobox(input_frame,
                                         values=["pips", "price", "%", "currency", "USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "NZD"],
                                         width=10)
        self.calc_tp_unit.set("pips")
        self.calc_tp_unit.grid(row=1, column=2, padx=5, pady=5)

        ttk.Label(input_frame, text="SL:").grid(row=1,
                                                column=3,
                                                padx=5,
                                                pady=5,
                                                sticky="w")
        self.calc_sl_entry = ttk.Entry(input_frame, width=10)
        self.calc_sl_entry.grid(row=1, column=4, padx=5, pady=5)

        self.calc_sl_unit = ttk.Combobox(input_frame,
                                         values=["pips", "price", "%", "currency", "USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "NZD"],
                                         width=10)
        self.calc_sl_unit.set("pips")
        self.calc_sl_unit.grid(row=1, column=5, padx=5, pady=5)

        calc_btn = ttk.Button(input_frame,
                              text="🧮 Calculate",
                              command=self.calculate_tp_sl)
        calc_btn.grid(row=2, column=1, columnspan=2, padx=5, pady=10)

        # Results
        self.calc_results = ScrolledText(calc_frame,
                                         height=20,
                                         bg="#0a0a0a",
                                         fg="#00ff00",
                                         font=("Courier", 11))
        self.calc_results.pack(fill="both", expand=True, padx=10, pady=10)

    def build_log_tab(self):
        """Enhanced log tab"""
        log_ctrl_frame = ttk.Frame(self.log_tab)
        log_ctrl_frame.pack(fill="x", padx=10, pady=5)

        ttk.Button(log_ctrl_frame,
                   text="💾 Export Logs",
                   command=self.export_logs).pack(side="left", padx=5)
        ttk.Button(log_ctrl_frame,
                   text="🗑️ Clear Logs",
                   command=self.clear_logs).pack(side="left", padx=5)

        self.log_area = ScrolledText(self.log_tab,
                                     height=40,
                                     bg="#0a0a0a",
                                     fg="#00ff00",
                                     font=("Consolas", 10))
        self.log_area.pack(fill="both", expand=True, padx=10, pady=10)

    def log(self, text):
        """Enhanced logging with timestamp"""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        full_text = f"[{timestamp}] {text}"
        self.log_area.insert(tk.END, full_text + "\n")
        self.log_area.see(tk.END)
        self.root.update_idletasks()

    def connect_mt5(self):
        """Enhanced MT5 connection with comprehensive GUI feedback and proper error handling"""
        try:
            self.log("🔄 Manual connection attempt to MetaTrader 5...")
            self.status_lbl.config(text="Status: Connecting... 🔄", foreground="orange")
            self.root.update()

            # Enhanced connection attempt with detailed logging
            self.log("🔍 Checking MT5 installation and permissions...")

            # Force update connection status before attempting
            global mt5_connected
            mt5_connected = False

            if connect_mt5():
                self.log("✅ Successfully connected to MetaTrader 5!")
                self.status_lbl.config(text="Status: Connected ✅", foreground="green")

                # Update symbols and enable buttons
                self.log("🔄 Loading available symbols...")
                self.update_symbols()

                self.start_btn.config(state="normal")
                self.close_btn.config(state="normal")
                self.connect_btn.config(state="disabled")

                # Get detailed account info with error handling
                self.log("🔄 Retrieving account information...")
                info = get_account_info()
                if info:
                    # Update all account labels immediately
                    self.balance_lbl.config(text=f"Balance: ${info['balance']:,.2f}")
                    self.equity_lbl.config(text=f"Equity: ${info['equity']:,.2f}")
                    self.margin_lbl.config(text=f"Free Margin: ${info['free_margin']:,.2f}")

                    # Calculate and display margin level
                    margin_level = info.get('margin_level', 0)
                    if margin_level > 0:
                        margin_color = "green" if margin_level > 300 else "orange" if margin_level > 150 else "red"
                        self.margin_level_lbl.config(text=f"Margin Level: {margin_level:.2f}%", foreground=margin_color)
                    else:
                        self.margin_level_lbl.config(text="Margin Level: ∞%", foreground="green")

                    self.server_lbl.config(text=f"Server: {info['server']} | Login: {info['login']}")

                    self.log(
                        f"✅ Account Details:")
                    self.log(
                        f"   👤 Login: {info['login']}")
                    self.log(
                        f"   🌐 Server: {info['server']}")
                    self.log(
                        f"   💰 Balance: ${info['balance']:,.2f}")
                    self.log(
                        f"   📈 Equity: ${info['equity']:,.2f}")
                    self.log(
                        f"   💵 Free Margin: ${info['free_margin']:,.2f}")
                    self.log(
                        f"   📊 Margin Level: {margin_level:.2f}%")

                    global session_start_balance
                    session_start_balance = info['balance']
                    session_data['start_balance'] = info['balance']

                    self.log("🚀 GUI-MT5 connection established successfully!")
                    self.log("🚀 Ready to start automated trading!")

                else:
                    # Error getting account info
                    self.balance_lbl.config(text="Balance: Error", foreground="red")
                    self.equity_lbl.config(text="Equity: Error", foreground="red")
                    self.margin_lbl.config(text="Free Margin: Error", foreground="red")
                    self.margin_level_lbl.config(text="Margin Level: Error", foreground="red")
                    logger("⚠️ Connected to MT5 but cannot get account info")
                    logger("💡 Check if MT5 is properly logged in to trading account")
                    # Keep connection enabled but warn user
                    self.start_btn.config(state="normal")
                    self.close_btn.config(state="normal")

            else:
                self.log("❌ Failed to connect to MetaTrader 5")
                self.log("🔧 TROUBLESHOOTING CHECKLIST:")
                self.log("   1. ✅ MT5 is running and logged in")
                self.log("   2. ✅ MT5 is running as Administrator")
                self.log("   3. ✅ Account has trading permissions")
                self.log("   4. ✅ No firewall blocking the connection")
                self.log("   5. ✅ Python and MT5 are both 64-bit")

                self.status_lbl.config(text="Status: Connection Failed ❌", foreground="red")
                self.start_btn.config(state="disabled")
                self.close_btn.config(state="disabled")
                self.connect_btn.config(state="normal")

                # Reset account labels
                self.balance_lbl.config(text="Balance: N/A", foreground="gray")
                self.equity_lbl.config(text="Equity: N/A", foreground="gray")
                self.margin_lbl.config(text="Free Margin: N/A", foreground="gray")
                self.margin_level_lbl.config(text="Margin Level: N/A", foreground="gray")
                self.server_lbl.config(text="Server: N/A")

        except Exception as e:
            error_msg = f"❌ Critical connection error: {str(e)}"
            self.log(error_msg)
            self.status_lbl.config(text="Status: Critical Error ❌", foreground="red")

    def start_bot(self):
        """Enhanced bot starting with better validation"""
        global bot_running, current_strategy, max_positions, max_drawdown, daily_max_loss, profit_target

        if bot_running:
            self.log("⚠️ Bot is already running!")
            return

        try:
            # Validate connection
            if not check_mt5_status():
                messagebox.showerror("❌ Error", "Please connect to MT5 first!")
                return

            # Validate symbol
            symbol = self.symbol_var.get().strip().upper()
            if not symbol:
                messagebox.showerror("❌ Error",
                                     "Please enter a trading symbol!")
                return

            self.log(f"🔍 Validating symbol: {symbol}")

            if not validate_and_activate_symbol(symbol):
                messagebox.showerror("❌ Error",
                                     f"Symbol {symbol} is not valid!")
                return

            self.log(f"✅ Symbol {symbol} validated successfully!")

            # Update global settings
            current_strategy = self.strategy_combo.get()
            max_positions = int(self.max_pos_entry.get())
            max_drawdown = float(self.max_dd_entry.get()) / 100
            profit_target = float(self.profit_target_entry.get()) / 100

            bot_running = True

            # Start bot thread
            threading.Thread(target=bot_thread, daemon=True).start()
            self.log(f"🚀 Enhanced trading bot started for {symbol}!")
            self.bot_status_lbl.config(text="Bot: Running 🟢",
                                       foreground="green")

            # Update button states
            self.start_btn.config(state="disabled")
            self.stop_btn.config(state="normal")

        except ValueError as e:
            messagebox.showerror("❌ Error", f"Invalid input values: {str(e)}")
        except Exception as e:
            self.log(f"❌ Error starting bot: {str(e)}")
            messagebox.showerror("❌ Error", f"Failed to start bot: {str(e)}")

    def stop_bot(self):
        """Enhanced bot stopping"""
        global bot_running
        bot_running = False
        self.log("⏹️ Stopping trading bot...")
        self.bot_status_lbl.config(text="Bot: Stopping... 🟡",
                                   foreground="orange")
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")

    def emergency_stop(self):
        """Enhanced emergency stop"""
        global bot_running
        try:
            bot_running = False
            close_all_orders()
            self.log("🚨 EMERGENCY STOP ACTIVATED - All positions closed!")
            self.bot_status_lbl.config(text="Bot: Emergency Stop 🔴",
                                       foreground="red")

            if gui and hasattr(gui, 'telegram_var') and gui.telegram_var.get():
                send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
                              "🚨 EMERGENCY STOP - All positions closed!")
        except Exception as e:
            self.log(f"❌ Emergency stop error: {str(e)}")

    def close_all(self):
        """Enhanced close all positions"""
        try:
            close_all_orders()
            self.log("❌ All positions closed manually")
        except Exception as e:
            self.log(f"❌ Error closing positions: {str(e)}")

    def on_strategy_change(self, event=None):
        """Handle strategy change with proper GUI integration"""
        global current_strategy
        new_strategy = self.strategy_combo.get()

        if new_strategy != current_strategy:
            current_strategy = new_strategy
            self.log(
                f"🔄 Strategy changed from {current_strategy} to: {new_strategy}")

            # Update current_strategy global
            current_strategy = new_strategy

            # Log current strategy parameters
            try:
                lot = self.get_current_lot()
                tp = self.get_current_tp()
                sl = self.get_current_sl()
                tp_unit = self.get_current_tp_unit()
                sl_unit = self.get_current_sl_unit()

                self.log(
                    f"📊 {new_strategy} params: Lot={lot}, TP={tp} {tp_unit}, SL={sl} {sl_unit}"
                )
            except Exception as e:
                self.log(f"❌ Error logging strategy params: {str(e)}")

    def get_current_lot(self):
        """Get current lot size from GUI with validation"""
        try:
            strategy = self.strategy_combo.get()
            lot_str = self.strategy_params[strategy]["lot"].get()
            return validate_numeric_input(lot_str, min_val=0.01, max_val=100.0)
        except (KeyError, ValueError) as e:
            logger(f"⚠️ Invalid lot size input: {str(e)}")
            return 0.01
        except Exception as e:
            logger(f"❌ Unexpected error getting lot size: {str(e)}")
            return 0.01

    def get_current_tp(self):
        """Get current TP from GUI with validation"""
        try:
            strategy = self.strategy_combo.get()
            tp_str = self.strategy_params[strategy]["tp"].get()
            if not tp_str or tp_str.strip() == "":
                return "20"
            validate_numeric_input(
                tp_str, min_val=0.0)  # Validate but return as string
            return tp_str
        except (KeyError, ValueError) as e:
            logger(f"⚠️ Invalid TP input: {str(e)}")
            return "20"
        except Exception as e:
            logger(f"❌ Unexpected error getting TP: {str(e)}")
            return "20"

    def get_current_sl(self):
        """Get current SL from GUI with validation"""
        try:
            strategy = self.strategy_combo.get()
            sl_str = self.strategy_params[strategy]["sl"].get()
            if not sl_str or sl_str.strip() == "":
                return "10"
            validate_numeric_input(
                sl_str, min_val=0.0)  # Validate but return as string
            return sl_str
        except (KeyError, ValueError) as e:
            logger(f"⚠️ Invalid SL input: {str(e)}")
            return "10"
        except Exception as e:
            logger(f"❌ Unexpected error getting SL: {str(e)}")
            return "10"

    def get_current_tp_unit(self):
        """Get current TP unit from selected strategy"""
        try:
            strategy = self.strategy_combo.get()
            if strategy in self.strategy_params:
                unit = self.strategy_params[strategy]["tp_unit"].get()
                logger(f"🔍 GUI: TP unit for {strategy} = {unit}")
                return unit
            else:
                logger(
                    f"⚠️ GUI: Strategy {strategy} not found in params, using default"
                )
                return "pips"
        except Exception as e:
            logger(f"❌ GUI: Error getting TP unit: {str(e)}")
            return "pips"

    def get_current_sl_unit(self):
        """Get current SL unit from selected strategy"""
        try:
            strategy = self.strategy_combo.get()
            if strategy in self.strategy_params:
                unit = self.strategy_params[strategy]["sl_unit"].get()
                logger(f"🔍 GUI: SL unit for {strategy} = {unit}")
                return unit
            else:
                logger(
                    f"⚠️ GUI: Strategy {strategy} not found in params, using default"
                )
                return "pips"
        except Exception as e:
            logger(f"❌ GUI: Error getting SL unit: {str(e)}")
            return "pips"

    def update_symbols(self):
        """Enhanced symbol updating"""
        try:
            symbols = get_symbol_suggestions()
            if symbols:
                self.symbol_entry['values'] = symbols
                self.log(f"📊 Loaded {len(symbols)} symbols")
            else:
                self.symbol_entry['values'] = [
                    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"
                ]
        except Exception as e:
            self.log(f"❌ Error updating symbols: {str(e)}")

    def validate_symbol(self):
        """Enhanced symbol validation"""
        try:
            symbol = self.symbol_var.get().strip().upper()
            if not symbol:
                messagebox.showwarning("⚠️ Warning",
                                       "Please enter a symbol first!")
                return

            self.log(f"🔍 Validating symbol: {symbol}")

            if not check_mt5_status():
                messagebox.showerror("❌ Error", "Please connect to MT5 first!")
                return

            valid_symbol = validate_and_activate_symbol(symbol)
            if valid_symbol:
                self.symbol_var.set(valid_symbol)
                # dst...
                self.log(f"✅ Symbol {valid_symbol} validated successfully!")
                messagebox.showinfo("✅ Success",
                                    f"Symbol {valid_symbol} is valid!")
                self.validate_symbol_btn.config(text="✅")
            else:
                self.log(f"❌ Symbol {symbol} validation failed!")
                messagebox.showerror("❌ Error",
                                     f"Symbol {symbol} is not valid!")
                self.validate_symbol_btn.config(text="❌")

        except Exception as e:
            self.log(f"❌ Error validating symbol: {str(e)}")

    def on_symbol_validate(self, event=None):
        """Auto-validate on symbol entry"""
        try:
            symbol = self.symbol_var.get().strip().upper()
            if symbol and len(symbol) >= 4:
                self.root.after(500, lambda: self.auto_validate_symbol(symbol))
        except:
            pass

    def auto_validate_symbol(self, symbol):
        """Background symbol validation"""
        try:
            if check_mt5_status() and validate_and_activate_symbol(symbol):
                self.validate_symbol_btn.config(text="✅")
            else:
                self.validate_symbol_btn.config(text="❌")
        except:
            self.validate_symbol_btn.config(text="?")

    def calculate_tp_sl(self):
        """Enhanced TP/SL calculation"""
        try:
            symbol = self.calc_symbol_entry.get()
            lot = float(self.calc_lot_entry.get())
            tp_input = self.calc_tp_entry.get()
            sl_input = self.calc_sl_entry.get()
            tp_unit = self.calc_tp_unit.get()
            sl_unit = self.calc_sl_unit.get()

            if not check_mt5_status():
                self.calc_results.delete(1.0, tk.END)
                self.calc_results.insert(tk.END,
                                         "❌ Please connect to MT5 first!\n")
                return

            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                self.calc_results.delete(1.0, tk.END)
                self.calc_results.insert(
                    tk.END, f"❌ Cannot get price for {symbol}!\n")
                return

            current_price = tick.ask
            pip_value = calculate_pip_value(symbol, lot)

            # Calculate TP values
            tp_price = 0.0
            tp_profit = 0.0
            if tp_input:
                tp_price, tp_profit_calc = parse_tp_sl_input(
                    tp_input, tp_unit, symbol, lot, current_price, "BUY", True)
                tp_profit = tp_profit_calc.get('amount', 0)

            # Calculate SL values
            sl_price = 0.0
            sl_loss = 0.0
            if sl_input:
                sl_price, sl_loss_calc = parse_tp_sl_input(
                    sl_input, sl_unit, symbol, lot, current_price, "BUY",
                    False)
                sl_loss = sl_loss_calc.get('amount', 0)

            result_text = f"""
🧮 TP/SL CALCULATION RESULTS
===============================
Symbol: {symbol}
Lot Size: {lot}
Current Price: {current_price:.5f}

TAKE PROFIT:
- Input: {tp_input} {tp_unit}
- Price Level: {tp_price:.5f}
- Expected Profit: ${tp_profit:.2f}

STOP LOSS:
- Input: {sl_input} {sl_unit}
- Price Level: {sl_price:.5f}
-- Expected Loss: ${sl_loss:.2f}

RISK/REWARD RATIO: {(tp_profit/max(sl_loss,1)):.2f}:1
PIP VALUE: ${pip_value:.2f}
===============================
"""
            self.calc_results.delete(1.0, tk.END)
            self.calc_results.insert(tk.END, result_text)

        except Exception as e:
            self.calc_results.delete(1.0, tk.END)
            self.calc_results.insert(tk.END,
                                     f"❌ Calculation Error: {str(e)}\n")

    def export_logs(self):
        """Enhanced log export"""
        try:
            if not os.path.exists("logs"):
                os.makedirs("logs")

            log_content = self.log_area.get(1.0, tk.END)
            filename = f"logs/gui_logs_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

            with open(filename, 'w') as f:
                f.write(log_content)

            self.log(f"💾 Logs exported to {filename}")
            messagebox.showinfo("✅ Export Success",
                                f"Logs exported to {filename}")
        except Exception as e:
            self.log(f"❌ Error exporting logs: {str(e)}")

    def clear_logs(self):
        """Clear log area"""
        self.log_area.delete(1.0, tk.END)
        self.log("🗑️ Logs cleared")

    def update_gui_data(self):
        """Ultra-responsive GUI with real-time market analysis and profit optimization"""
        try:
            # Enhanced MT5 status check with performance monitoring
            connection_start = time.time()
            mt5_status = check_mt5_status()
            connection_time = (time.time() - connection_start) * 1000  # ms

            if mt5_status:
                status_color = "green" if connection_time < 100 else "orange"
                self.status_lbl.config(text=f"Status: Connected ✅ ({connection_time:.1f}ms)",
                                       foreground=status_color)

                # Real-time performance metrics
                if hasattr(self, '_last_update_time'):
                    update_interval = time.time() - self._last_update_time
                    if update_interval > 3.0:  # Slow updates warning
                        logger(f"⚠️ Slow GUI update detected: {update_interval:.1f}s")

                self._last_update_time = time.time()

                # Get current account info untuk real-time update
                info = get_account_info()
                if info:
                    # Update all account labels immediately
                    self.balance_lbl.config(text=f"Balance: ${info['balance']:,.2f}")
                    self.equity_lbl.config(text=f"Equity: ${info['equity']:,.2f}")
                    self.margin_lbl.config(text=f"Free Margin: ${info['free_margin']:,.2f}")

                    # Calculate and display margin level
                    margin_level = info.get('margin_level', 0)
                    if margin_level > 0:
                        margin_color = "green" if margin_level > 300 else "orange" if margin_level > 150 else "red"
                        self.margin_level_lbl.config(text=f"Margin Level: {margin_level:.2f}%", foreground=margin_color)
                    else:
                        self.margin_level_lbl.config(text="Margin Level: ∞%", foreground="green")

                    self.server_lbl.config(text=f"Server: {info['server']} | Login: {info['login']}")

                    # Initialize session_start_balance if not set
                    global session_start_balance
                    if session_start_balance is None:
                        session_start_balance = info['balance']
                        session_data['start_balance'] = info['balance']
                        logger(
                            f"💰 Session initialized - Starting Balance: ${session_start_balance:.2f}"
                        )

                else:
                    # Error getting account info
                    self.balance_lbl.config(text="Balance: Error", foreground="red")
                    self.equity_lbl.config(text="Equity: Error", foreground="red")
                    self.margin_lbl.config(text="Free Margin: Error", foreground="red")
                    self.margin_level_lbl.config(text="Margin Level: Error", foreground="red")
                    logger("⚠️ Cannot get account info from MT5")

            else:
                # MT5 not connected
                self.status_lbl.config(text="Status: Disconnected ❌", foreground="red")
                self.server_lbl.config(text="Server: N/A")
                self.balance_lbl.config(text="Balance: N/A", foreground="gray")
                self.equity_lbl.config(text="Equity: N/A", foreground="gray")
                self.margin_lbl.config(text="Free Margin: N/A", foreground="gray")
                self.margin_level_lbl.config(text="Margin Level: N/A", foreground="gray")

            # Update trading statistics with proper calculations
            self.daily_orders_lbl.config(
                text=f"Daily Orders: {session_data.get('daily_orders', 0)}")

            # Calculate daily profit from current equity vs start balance
            actual_daily_profit = 0.0
            daily_profit_percent = 0.0

            if info and session_start_balance and session_start_balance > 0:
                actual_daily_profit = info['equity'] - session_start_balance
                session_data['daily_profit'] = actual_daily_profit
                daily_profit_percent = (actual_daily_profit /
                                        session_start_balance) * 100
            else:
                actual_daily_profit = session_data.get('daily_profit', 0.0)

            # Color coding for profit/loss
            daily_profit_color = "green" if actual_daily_profit >= 0 else "red"
            self.daily_profit_lbl.config(
                text=
                f"Daily P/L: ${actual_daily_profit:.2f} ({daily_profit_percent:+.2f}%)",
                foreground=daily_profit_color)

            # Calculate win rate from closed positions with better tracking
            total_closed = session_data.get(
                'winning_trades', 0) + session_data.get('losing_trades', 0)
            winning_trades = session_data.get('winning_trades', 0)

            if total_closed > 0:
                win_rate = (winning_trades / total_closed) * 100
                win_rate_color = "green" if win_rate >= 60 else "orange" if win_rate >= 40 else "red"
                self.win_rate_lbl.config(
                    text=
                    f"Win Rate: {win_rate:.1f}% ({winning_trades}W/{total_closed-winning_trades}L)",
                    foreground=win_rate_color)
            else:
                self.win_rate_lbl.config(text="Win Rate: -- % (0W/0L)",
                                         foreground="gray")

            # Update positions count with real-time data
            positions = get_positions()
            position_count = len(positions) if positions else 0
            self.open_positions_lbl.config(
                text=f"Open Positions: {position_count}/{max_positions}")

            # Update session information
            try:
                current_session = get_current_trading_session()
                if current_session:
                    session_name = current_session["name"]
                    volatility = current_session["info"]["volatility"]
                    session_color = {
                        "very_high": "red",
                        "high": "orange",
                        "medium": "green",
                        "low": "blue"
                    }.get(volatility, "gray")

                    self.session_lbl.config(
                        text=
                        f"Session: {session_name} ({volatility.upper()} volatility)",
                        foreground=session_color)
                else:
                    self.session_lbl.config(
                        text="Session: Outside Major Sessions",
                        foreground="gray")
            except Exception as e:
                self.session_lbl.config(text="Session: Error",
                                        foreground="red")

            # Update bot status with current strategy info
            global bot_running, current_strategy
            if bot_running:
                self.bot_status_lbl.config(
                    text=f"Bot: Running 🟢 ({current_strategy})",
                    foreground="green")
            else:
                self.bot_status_lbl.config(text="Bot: Stopped 🔴",
                                           foreground="red")

            # Update positions table
            self.update_positions()

            # Log periodic status for debugging
            if hasattr(self, '_update_counter'):
                self._update_counter += 1
            else:
                self._update_counter = 1

            # Log every 30 updates (about 1 minute)
            if self._update_counter % 30 == 0:
                if info:
                    logger(
                        f"📊 GUI Update #{self._update_counter}: Balance=${info['balance']:.2f}, Equity=${info['equity']:.2f}, Positions={position_count}"
                    )
                else:
                    logger(
                        f"📊 GUI Update #{self._update_counter}: MT5 disconnected"
                    )

        except Exception as e:
            logger(f"❌ GUI update error: {str(e)}")
            # Show error in status
            self.status_lbl.config(text="Status: Update Error ❌", foreground="red")
            import traceback
            logger(f"📝 GUI update traceback: {traceback.format_exc()}")

        # Schedule next update with configurable interval
        self.root.after(GUI_UPDATE_INTERVAL,
                        self.update_gui_data)  # Update every 1.5 seconds

    def update_positions(self):
        """Enhanced position table updating"""
        try:
            # Clear existing items
            for item in self.pos_tree.get_children():
                self.pos_tree.delete(item)

            # Get current positions
            positions = get_positions()

            for pos in positions:
                position_type = "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL"

                # Get current price
                tick = mt5.symbol_info_tick(pos.symbol)
                if tick:
                    current_price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask

                    # Calculate pips
                    price_diff = current_price - pos.price_open if pos.type == mt5.ORDER_TYPE_BUY else pos.price_open - current_price
                    pip_size = 0.01 if "JPY" in pos.symbol else 0.0001
                    pips = price_diff / pip_size

                    # Insert with color coding
                    profit_color = "green" if pos.profit >= 0 else "red"

                    self.pos_tree.insert(
                        "",
                        "end",
                        values=(pos.ticket, pos.symbol, position_type,
                                f"{pos.volume:.2f}", f"{pos.price_open:.5f}",
                                f"{current_price:.5f}", f"${pos.profit:.2f}",
                                f"{pips:.1f}"),
                        tags=(profit_color, ))
                else:
                    # If tick is unavailable
                    self.pos_tree.insert(
                        "",
                        "end",
                        values=(pos.ticket, pos.symbol, position_type,
                                f"{pos.volume:.2f}", f"{pos.price_open:.5f}",
                                "N/A", f"${pos.profit:.2f}", "N/A"),
                        tags=("red" if pos.profit < 0 else "green", ))

            # Configure colors
            self.pos_tree.tag_configure("green", foreground="green")
            self.pos_tree.tag_configure("red", foreground="red")

        except Exception as e:
            logger(f"❌ Error updating positions: {str(e)}")

    def generate_report_now(self):
        """Generate and display performance report immediately"""
        try:
            report = generate_performance_report()

            # Show in message box
            messagebox.showinfo("📊 Performance Report", report)

            # Log to GUI
            self.log("📊 Performance report generated:")
            for line in report.split('\n'):
                if line.strip():
                    self.log(f"   {line}")

            # Send to Telegram if enabled
            if gui and hasattr(gui, 'telegram_var') and gui.telegram_var.get():
                send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
                              "📊 MANUAL REPORT\n" + report)
                self.log("📱 Report sent to Telegram")

        except Exception as e:
            self.log(f"❌ Error generating report: {str(e)}")

    def test_recovery(self):
        """Test auto-recovery system"""
        try:
            self.log("🔄 Testing auto-recovery system...")

            # Test MT5 connection
            if check_mt5_status():
                self.log("✅ MT5 connection: OK")
            else:
                self.log("⚠️ MT5 connection: FAILED - triggering recovery...")
                success = auto_recovery_check()
                self.log(
                    f"🔄 Recovery result: {'✅ SUCCESS' if success else '❌ FAILED'}"
                )

            # Test account info
            info = get_account_info()
            if info:
                self.log(
                    f"✅ Account info: Balance=${info['balance']:.2f}, Equity=${info['equity']:.2f}"
                )
            else:
                self.log("⚠️ Account info: UNAVAILABLE")

            # Test symbol validation
            symbol = self.symbol_var.get()
            if validate_and_activate_symbol(symbol):
                self.log(f"✅ Symbol validation: {symbol} OK")
            else:
                self.log(f"⚠️ Symbol validation: {symbol} FAILED")

            self.log("🔧 Recovery test completed!")

        except Exception as e:
            self.log(f"❌ Recovery test error: {str(e)}")

    def on_closing(self):
        """Enhanced closing handler with cleanup"""
        global bot_running

        # Stop bot gracefully
        if bot_running:
            self.log("🛑 Stopping bot before exit...")
            self.stop_bot()
            time.sleep(2)

        # Send final report if enabled
        try:
            if gui and hasattr(gui, 'telegram_var') and gui.telegram_var.get():
                final_report = generate_performance_report()
                send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
                              "🛑 BOT SHUTDOWN\n" + final_report)
                self.log("📱 Final report sent to Telegram")
        except Exception as e:
            self.log(f"⚠️ Error sending final report: {str(e)}")

        # Close MT5 connection
        try:
            if mt5_connected:
                mt5.shutdown()
                self.log("🔌 MT5 connection closed")
        except Exception as e:
            self.log(f"⚠️ Error closing MT5: {str(e)}")

        self.root.destroy()


# Configure run command to run the bot
if __name__ == "__main__":
    try:
        import tkinter as tk
        from tkinter import messagebox

        # Check Python version compatibility
        import sys
        if sys.version_info < (3, 7):
            print("❌ ERROR: Python 3.7+ required")
            sys.exit(1)

        # Check if MetaTrader5 is available
        try:
            import MetaTrader5 as mt5
            print("✅ MetaTrader5 module available")
        except ImportError:
            print("❌ ERROR: MetaTrader5 module not found")
            print("💡 Install with: pip install MetaTrader5")
            sys.exit(1)

        # Initialize GUI
        root = tk.Tk()
        gui = TradingBotGUI(root)

        # Make gui globally accessible
        globals()['gui']= gui

        # Validate configuration and environment
        ensure_log_directory()

        # Enhanced startup logging
        logger(
            "🚀 === MT5 ADVANCED AUTO TRADING BOT v4.0 - Premium Edition ===")
        logger("🔧 Features: Enhanced MT5 Connection, Improved Error Handling")
        logger(
            "📱 Advanced Diagnostics, Real-time Updates, Better Profitability")
        logger("🎯 Comprehensive Symbol Validation & Market Data Testing")
        logger("⚡ Optimized for Maximum Win Rate and Minimal Errors")
        logger("=" * 70)
        logger("🚀 STARTUP SEQUENCE:")
        logger("   1. GUI initialized successfully")
        logger("   2. Auto-connecting to MT5...")
        logger("   3. Validating trading environment...")
        logger("💡 NEXT STEPS: Wait for connection, then click 'START BOT'")
        logger("=" * 70)

        root.mainloop()

    except Exception as e:
        print(f"❌ CRITICAL STARTUP ERROR: {str(e)}")
        print("🔧 SOLUSI:")
        print("   1. Pastikan Python 3.7+ terinstall")
        print(
            "   2. Install dependencies: pip install MetaTrader5 pandas numpy tkinter"
        )
        print("   3. Pastikan MT5 sudah terinstall")
        print("   4. Restart aplikasi")
        import traceback
        print(f"📝 Detail error: {traceback.format_exc()}")
        input("Press Enter to exit...")