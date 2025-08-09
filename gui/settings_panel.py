"""
Settings Panel for TradeMaestro
Provides interface for configuring trading parameters and bot settings
"""

from typing import Dict, Any, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QGroupBox, QLabel, QLineEdit, QSpinBox, QDoubleSpinBox, 
    QCheckBox, QComboBox, QPushButton, QSlider, QTextEdit,
    QMessageBox, QFileDialog, QTabWidget
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont

from ..utils.logger import Logger


class SettingsPanel(QWidget):
    """
    Comprehensive settings panel for TradeMaestro configuration
    Provides organized interface for all trading and system settings
    """
    
    # Signals
    settings_changed = Signal(dict)  # settings_dict
    settings_saved = Signal()
    settings_loaded = Signal()
    
    def __init__(self, config, parent=None):
        super().__init__(parent)
        
        self.config = config
        self.logger = Logger(__name__)
        
        # Settings storage
        self.current_settings = {}
        self.original_settings = {}
        
        # UI components
        self.setup_ui()
        self.load_current_settings()
        
        self.logger.debug("Settings panel initialized")
    
    def setup_ui(self):
        """Setup the settings interface"""
        try:
            layout = QVBoxLayout(self)
            
            # Create tab widget for organized settings
            self.tab_widget = QTabWidget()
            
            # Trading settings tab
            trading_tab = self.create_trading_tab()
            self.tab_widget.addTab(trading_tab, "Trading")
            
            # Risk management tab
            risk_tab = self.create_risk_tab()
            self.tab_widget.addTab(risk_tab, "Risk Management")
            
            # Symbols tab
            symbols_tab = self.create_symbols_tab()
            self.tab_widget.addTab(symbols_tab, "Symbols")
            
            # System tab
            system_tab = self.create_system_tab()
            self.tab_widget.addTab(system_tab, "System")
            
            layout.addWidget(self.tab_widget)
            
            # Control buttons
            button_layout = QHBoxLayout()
            
            self.save_button = QPushButton("Save Settings")
            self.save_button.clicked.connect(self.save_settings)
            button_layout.addWidget(self.save_button)
            
            self.reset_button = QPushButton("Reset to Defaults")
            self.reset_button.clicked.connect(self.reset_to_defaults)
            button_layout.addWidget(self.reset_button)
            
            self.load_button = QPushButton("Load from File")
            self.load_button.clicked.connect(self.load_from_file)
            button_layout.addWidget(self.load_button)
            
            self.export_button = QPushButton("Export Settings")
            self.export_button.clicked.connect(self.export_settings)
            button_layout.addWidget(self.export_button)
            
            layout.addLayout(button_layout)
            
        except Exception as e:
            self.logger.error(f"Error setting up settings UI: {str(e)}")
    
    def create_trading_tab(self) -> QWidget:
        """Create trading settings tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Basic trading parameters
        basic_group = QGroupBox("Basic Trading Parameters")
        basic_layout = QFormLayout(basic_group)
        
        # Default lot size
        self.lot_size_spin = QDoubleSpinBox()
        self.lot_size_spin.setRange(0.01, 100.0)
        self.lot_size_spin.setDecimals(2)
        self.lot_size_spin.setSingleStep(0.01)
        self.lot_size_spin.setValue(0.01)
        basic_layout.addRow("Default Lot Size:", self.lot_size_spin)
        
        # Stop Loss
        self.stop_loss_spin = QSpinBox()
        self.stop_loss_spin.setRange(5, 1000)
        self.stop_loss_spin.setSuffix(" pips")
        self.stop_loss_spin.setValue(50)
        basic_layout.addRow("Default Stop Loss:", self.stop_loss_spin)
        
        # Take Profit
        self.take_profit_spin = QSpinBox()
        self.take_profit_spin.setRange(5, 2000)
        self.take_profit_spin.setSuffix(" pips")
        self.take_profit_spin.setValue(100)
        basic_layout.addRow("Default Take Profit:", self.take_profit_spin)
        
        # Max positions
        self.max_positions_spin = QSpinBox()
        self.max_positions_spin.setRange(1, 50)
        self.max_positions_spin.setValue(5)
        basic_layout.addRow("Maximum Positions:", self.max_positions_spin)
        
        # Trading interval
        self.trading_interval_spin = QSpinBox()
        self.trading_interval_spin.setRange(100, 10000)
        self.trading_interval_spin.setSuffix(" ms")
        self.trading_interval_spin.setValue(1000)
        basic_layout.addRow("Trading Interval:", self.trading_interval_spin)
        
        layout.addWidget(basic_group)
        
        # Advanced settings
        advanced_group = QGroupBox("Advanced Settings")
        advanced_layout = QFormLayout(advanced_group)
        
        # Trailing stop
        self.trailing_stop_check = QCheckBox()
        self.trailing_stop_check.setChecked(True)
        advanced_layout.addRow("Enable Trailing Stop:", self.trailing_stop_check)
        
        self.trailing_stop_distance_spin = QSpinBox()
        self.trailing_stop_distance_spin.setRange(5, 200)
        self.trailing_stop_distance_spin.setSuffix(" pips")
        self.trailing_stop_distance_spin.setValue(20)
        advanced_layout.addRow("Trailing Stop Distance:", self.trailing_stop_distance_spin)
        
        # News trading
        self.avoid_news_check = QCheckBox()
        self.avoid_news_check.setChecked(True)
        advanced_layout.addRow("Avoid News Trading:", self.avoid_news_check)
        
        self.news_buffer_spin = QSpinBox()
        self.news_buffer_spin.setRange(5, 120)
        self.news_buffer_spin.setSuffix(" minutes")
        self.news_buffer_spin.setValue(30)
        advanced_layout.addRow("News Buffer Time:", self.news_buffer_spin)
        
        layout.addWidget(advanced_group)
        
        layout.addStretch()
        return widget
    
    def create_risk_tab(self) -> QWidget:
        """Create risk management tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Risk parameters
        risk_group = QGroupBox("Risk Management")
        risk_layout = QFormLayout(risk_group)
        
        # Max risk per trade
        self.max_risk_spin = QDoubleSpinBox()
        self.max_risk_spin.setRange(0.01, 0.20)
        self.max_risk_spin.setDecimals(3)
        self.max_risk_spin.setSingleStep(0.001)
        self.max_risk_spin.setSuffix("%")
        self.max_risk_spin.setValue(2.0)
        risk_layout.addRow("Max Risk per Trade:", self.max_risk_spin)
        
        # Max daily loss
        self.max_daily_loss_spin = QDoubleSpinBox()
        self.max_daily_loss_spin.setRange(0.01, 0.50)
        self.max_daily_loss_spin.setDecimals(3)
        self.max_daily_loss_spin.setSingleStep(0.001)
        self.max_daily_loss_spin.setSuffix("%")
        self.max_daily_loss_spin.setValue(5.0)
        risk_layout.addRow("Max Daily Loss:", self.max_daily_loss_spin)
        
        # Max drawdown
        self.max_drawdown_spin = QDoubleSpinBox()
        self.max_drawdown_spin.setRange(0.01, 0.50)
        self.max_drawdown_spin.setDecimals(3)
        self.max_drawdown_spin.setSingleStep(0.001)
        self.max_drawdown_spin.setSuffix("%")
        self.max_drawdown_spin.setValue(10.0)
        risk_layout.addRow("Max Drawdown:", self.max_drawdown_spin)
        
        layout.addWidget(risk_group)
        
        # Position sizing
        sizing_group = QGroupBox("Position Sizing")
        sizing_layout = QFormLayout(sizing_group)
        
        # Position sizing method
        self.sizing_method_combo = QComboBox()
        self.sizing_method_combo.addItems([
            "Fixed Lot Size",
            "Risk-based Sizing",
            "Balance Percentage",
            "Volatility-based"
        ])
        sizing_layout.addRow("Sizing Method:", self.sizing_method_combo)
        
        # Risk calculation method
        self.risk_calc_combo = QComboBox()
        self.risk_calc_combo.addItems([
            "Account Balance",
            "Account Equity",
            "Free Margin"
        ])
        sizing_layout.addRow("Risk Based On:", self.risk_calc_combo)
        
        layout.addWidget(sizing_group)
        
        layout.addStretch()
        return widget
    
    def create_symbols_tab(self) -> QWidget:
        """Create symbols configuration tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Symbol selection
        symbol_group = QGroupBox("Trading Symbols")
        symbol_layout = QVBoxLayout(symbol_group)
        
        # Available symbols
        available_label = QLabel("Available Symbols:")
        available_label.setFont(QFont("Arial", 9, QFont.Bold))
        symbol_layout.addWidget(available_label)
        
        # Symbol checkboxes
        self.symbol_checkboxes = {}
        common_symbols = [
            "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", 
            "USDCAD", "NZDUSD", "EURGBP", "EURJPY", "GBPJPY"
        ]
        
        symbols_grid = QGridLayout()
        for i, symbol in enumerate(common_symbols):
            checkbox = QCheckBox(symbol)
            if symbol in ["EURUSD", "GBPUSD", "USDJPY"]:
                checkbox.setChecked(True)
            self.symbol_checkboxes[symbol] = checkbox
            symbols_grid.addWidget(checkbox, i // 3, i % 3)
        
        symbol_layout.addLayout(symbols_grid)
        
        # Custom symbols
        custom_layout = QHBoxLayout()
        custom_layout.addWidget(QLabel("Custom Symbol:"))
        self.custom_symbol_edit = QLineEdit()
        self.custom_symbol_edit.setPlaceholderText("Enter symbol name")
        custom_layout.addWidget(self.custom_symbol_edit)
        
        add_symbol_btn = QPushButton("Add")
        add_symbol_btn.clicked.connect(self.add_custom_symbol)
        custom_layout.addWidget(add_symbol_btn)
        
        symbol_layout.addLayout(custom_layout)
        
        layout.addWidget(symbol_group)
        
        # Symbol-specific settings
        symbol_settings_group = QGroupBox("Symbol Settings")
        symbol_settings_layout = QFormLayout(symbol_settings_group)
        
        # Default timeframe
        self.timeframe_combo = QComboBox()
        self.timeframe_combo.addItems(["M1", "M5", "M15", "M30", "H1", "H4", "D1"])
        self.timeframe_combo.setCurrentText("H1")
        symbol_settings_layout.addRow("Default Timeframe:", self.timeframe_combo)
        
        # Max spread
        self.max_spread_spin = QDoubleSpinBox()
        self.max_spread_spin.setRange(0.1, 10.0)
        self.max_spread_spin.setDecimals(1)
        self.max_spread_spin.setSuffix(" pips")
        self.max_spread_spin.setValue(3.0)
        symbol_settings_layout.addRow("Max Spread:", self.max_spread_spin)
        
        layout.addWidget(symbol_settings_group)
        
        layout.addStretch()
        return widget
    
    def create_system_tab(self) -> QWidget:
        """Create system settings tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Logging settings
        logging_group = QGroupBox("Logging")
        logging_layout = QFormLayout(logging_group)
        
        # Log level
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        self.log_level_combo.setCurrentText("INFO")
        logging_layout.addRow("Log Level:", self.log_level_combo)
        
        # Save trade history
        self.save_history_check = QCheckBox()
        self.save_history_check.setChecked(True)
        logging_layout.addRow("Save Trade History:", self.save_history_check)
        
        # Performance tracking
        self.performance_tracking_check = QCheckBox()
        self.performance_tracking_check.setChecked(True)
        logging_layout.addRow("Performance Tracking:", self.performance_tracking_check)
        
        layout.addWidget(logging_group)
        
        # GUI settings
        gui_group = QGroupBox("Interface")
        gui_layout = QFormLayout(gui_group)
        
        # Theme
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark", "Light"])
        self.theme_combo.setCurrentText("Dark")
        gui_layout.addRow("Theme:", self.theme_combo)
        
        # Update interval
        self.gui_update_spin = QSpinBox()
        self.gui_update_spin.setRange(100, 5000)
        self.gui_update_spin.setSuffix(" ms")
        self.gui_update_spin.setValue(1000)
        gui_layout.addRow("Update Interval:", self.gui_update_spin)
        
        # Window size
        window_layout = QHBoxLayout()
        self.window_width_spin = QSpinBox()
        self.window_width_spin.setRange(800, 2400)
        self.window_width_spin.setValue(1200)
        window_layout.addWidget(self.window_width_spin)
        
        window_layout.addWidget(QLabel("x"))
        
        self.window_height_spin = QSpinBox()
        self.window_height_spin.setRange(600, 1600)
        self.window_height_spin.setValue(800)
        window_layout.addWidget(self.window_height_spin)
        
        gui_layout.addRow("Window Size:", window_layout)
        
        layout.addWidget(gui_group)
        
        # Notifications
        notification_group = QGroupBox("Notifications")
        notification_layout = QFormLayout(notification_group)
        
        # Telegram notifications
        self.telegram_enabled_check = QCheckBox()
        notification_layout.addRow("Enable Telegram:", self.telegram_enabled_check)
        
        self.telegram_token_edit = QLineEdit()
        self.telegram_token_edit.setEchoMode(QLineEdit.Password)
        self.telegram_token_edit.setPlaceholderText("Bot token")
        notification_layout.addRow("Telegram Token:", self.telegram_token_edit)
        
        self.telegram_chat_id_edit = QLineEdit()
        self.telegram_chat_id_edit.setPlaceholderText("Chat ID")
        notification_layout.addRow("Chat ID:", self.telegram_chat_id_edit)
        
        layout.addWidget(notification_group)
        
        layout.addStretch()
        return widget
    
    def load_current_settings(self):
        """Load current settings from config"""
        try:
            # Trading settings
            self.lot_size_spin.setValue(self.config.DEFAULT_LOT_SIZE)
            self.stop_loss_spin.setValue(self.config.DEFAULT_STOP_LOSS)
            self.take_profit_spin.setValue(self.config.DEFAULT_TAKE_PROFIT)
            self.max_positions_spin.setValue(self.config.MAX_POSITIONS)
            self.trading_interval_spin.setValue(self.config.TRADING_INTERVAL_MS)
            
            # Risk settings
            self.max_risk_spin.setValue(self.config.MAX_RISK_PER_TRADE * 100)
            self.max_daily_loss_spin.setValue(self.config.MAX_DAILY_LOSS * 100)
            self.max_drawdown_spin.setValue(self.config.MAX_DRAWDOWN * 100)
            
            # Trailing stop
            self.trailing_stop_check.setChecked(self.config.TRAILING_STOP_ENABLED)
            self.trailing_stop_distance_spin.setValue(self.config.TRAILING_STOP_DISTANCE)
            
            # News settings
            self.avoid_news_check.setChecked(self.config.AVOID_NEWS_TRADING)
            self.news_buffer_spin.setValue(self.config.NEWS_BUFFER_MINUTES)
            
            # Symbols
            for symbol, checkbox in self.symbol_checkboxes.items():
                checkbox.setChecked(symbol in self.config.DEFAULT_SYMBOLS)
            
            # Timeframe
            if hasattr(self.config, 'STRATEGY_TIMEFRAME'):
                self.timeframe_combo.setCurrentText(self.config.STRATEGY_TIMEFRAME)
            
            # System settings
            self.log_level_combo.setCurrentText(self.config.LOG_LEVEL)
            self.save_history_check.setChecked(self.config.SAVE_TRADE_HISTORY)
            self.performance_tracking_check.setChecked(self.config.PERFORMANCE_TRACKING)
            
            # GUI settings
            self.theme_combo.setCurrentText(self.config.GUI_THEME.title())
            self.gui_update_spin.setValue(self.config.GUI_UPDATE_INTERVAL_MS)
            self.window_width_spin.setValue(self.config.WINDOW_WIDTH)
            self.window_height_spin.setValue(self.config.WINDOW_HEIGHT)
            
            # Telegram settings
            self.telegram_enabled_check.setChecked(self.config.TELEGRAM_ENABLED)
            self.telegram_token_edit.setText(self.config.TELEGRAM_TOKEN)
            self.telegram_chat_id_edit.setText(self.config.TELEGRAM_CHAT_ID)
            
            # Store original settings
            self.original_settings = self.get_current_values()
            
        except Exception as e:
            self.logger.error(f"Error loading current settings: {str(e)}")
    
    def get_current_values(self) -> Dict[str, Any]:
        """Get current values from all controls"""
        try:
            # Get selected symbols
            selected_symbols = [symbol for symbol, checkbox in self.symbol_checkboxes.items() 
                              if checkbox.isChecked()]
            
            return {
                # Trading settings
                'default_lot_size': self.lot_size_spin.value(),
                'default_stop_loss': self.stop_loss_spin.value(),
                'default_take_profit': self.take_profit_spin.value(),
                'max_positions': self.max_positions_spin.value(),
                'trading_interval_ms': self.trading_interval_spin.value(),
                
                # Risk settings
                'max_risk_per_trade': self.max_risk_spin.value() / 100,
                'max_daily_loss': self.max_daily_loss_spin.value() / 100,
                'max_drawdown': self.max_drawdown_spin.value() / 100,
                
                # Advanced settings
                'trailing_stop_enabled': self.trailing_stop_check.isChecked(),
                'trailing_stop_distance': self.trailing_stop_distance_spin.value(),
                'avoid_news_trading': self.avoid_news_check.isChecked(),
                'news_buffer_minutes': self.news_buffer_spin.value(),
                
                # Symbols
                'default_symbols': selected_symbols,
                'strategy_timeframe': self.timeframe_combo.currentText(),
                'max_spread': self.max_spread_spin.value(),
                
                # System settings
                'log_level': self.log_level_combo.currentText(),
                'save_trade_history': self.save_history_check.isChecked(),
                'performance_tracking': self.performance_tracking_check.isChecked(),
                
                # GUI settings
                'gui_theme': self.theme_combo.currentText().lower(),
                'gui_update_interval_ms': self.gui_update_spin.value(),
                'window_width': self.window_width_spin.value(),
                'window_height': self.window_height_spin.value(),
                
                # Notifications
                'telegram_enabled': self.telegram_enabled_check.isChecked(),
                'telegram_token': self.telegram_token_edit.text(),
                'telegram_chat_id': self.telegram_chat_id_edit.text(),
            }
            
        except Exception as e:
            self.logger.error(f"Error getting current values: {str(e)}")
            return {}
    
    def save_settings(self):
        """Save current settings"""
        try:
            current_values = self.get_current_values()
            
            if not current_values:
                QMessageBox.warning(self, "Error", "Failed to read current settings")
                return
            
            # Validate settings
            validation_errors = self.validate_settings(current_values)
            if validation_errors:
                error_msg = "Settings validation failed:\n" + "\n".join(validation_errors)
                QMessageBox.warning(self, "Validation Error", error_msg)
                return
            
            # Save to config
            success = self.config.save_config()
            if success:
                # Update config object
                self.update_config_object(current_values)
                
                # Store current settings
                self.current_settings = current_values
                
                # Emit signal
                self.settings_changed.emit(current_values)
                self.settings_saved.emit()
                
                QMessageBox.information(self, "Success", "Settings saved successfully!")
                self.logger.info("Settings saved successfully")
            else:
                QMessageBox.warning(self, "Error", "Failed to save settings to file")
                
        except Exception as e:
            self.logger.error(f"Error saving settings: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to save settings: {str(e)}")
    
    def validate_settings(self, settings: Dict[str, Any]) -> List[str]:
        """Validate settings values"""
        errors = []
        
        try:
            # Validate basic ranges
            if settings['default_lot_size'] <= 0:
                errors.append("Default lot size must be greater than 0")
            
            if settings['default_stop_loss'] <= 0:
                errors.append("Default stop loss must be greater than 0")
            
            if settings['default_take_profit'] <= 0:
                errors.append("Default take profit must be greater than 0")
            
            if settings['max_positions'] <= 0:
                errors.append("Maximum positions must be greater than 0")
            
            # Validate risk percentages
            if settings['max_risk_per_trade'] <= 0 or settings['max_risk_per_trade'] > 1:
                errors.append("Max risk per trade must be between 0% and 100%")
            
            if settings['max_daily_loss'] <= 0 or settings['max_daily_loss'] > 1:
                errors.append("Max daily loss must be between 0% and 100%")
            
            if settings['max_drawdown'] <= 0 or settings['max_drawdown'] > 1:
                errors.append("Max drawdown must be between 0% and 100%")
            
            # Validate symbols
            if not settings['default_symbols']:
                errors.append("At least one trading symbol must be selected")
            
            # Validate Telegram settings if enabled
            if settings['telegram_enabled']:
                if not settings['telegram_token'].strip():
                    errors.append("Telegram token is required when Telegram is enabled")
                if not settings['telegram_chat_id'].strip():
                    errors.append("Telegram chat ID is required when Telegram is enabled")
            
        except Exception as e:
            errors.append(f"Validation error: {str(e)}")
        
        return errors
    
    def update_config_object(self, settings: Dict[str, Any]):
        """Update the config object with new settings"""
        try:
            # Update config attributes
            self.config.DEFAULT_LOT_SIZE = settings['default_lot_size']
            self.config.DEFAULT_STOP_LOSS = settings['default_stop_loss']
            self.config.DEFAULT_TAKE_PROFIT = settings['default_take_profit']
            self.config.MAX_POSITIONS = settings['max_positions']
            self.config.TRADING_INTERVAL_MS = settings['trading_interval_ms']
            
            self.config.MAX_RISK_PER_TRADE = settings['max_risk_per_trade']
            self.config.MAX_DAILY_LOSS = settings['max_daily_loss']
            self.config.MAX_DRAWDOWN = settings['max_drawdown']
            
            self.config.TRAILING_STOP_ENABLED = settings['trailing_stop_enabled']
            self.config.TRAILING_STOP_DISTANCE = settings['trailing_stop_distance']
            self.config.AVOID_NEWS_TRADING = settings['avoid_news_trading']
            self.config.NEWS_BUFFER_MINUTES = settings['news_buffer_minutes']
            
            self.config.DEFAULT_SYMBOLS = settings['default_symbols']
            self.config.STRATEGY_TIMEFRAME = settings['strategy_timeframe']
            
            self.config.LOG_LEVEL = settings['log_level']
            self.config.SAVE_TRADE_HISTORY = settings['save_trade_history']
            self.config.PERFORMANCE_TRACKING = settings['performance_tracking']
            
            self.config.GUI_THEME = settings['gui_theme']
            self.config.GUI_UPDATE_INTERVAL_MS = settings['gui_update_interval_ms']
            self.config.WINDOW_WIDTH = settings['window_width']
            self.config.WINDOW_HEIGHT = settings['window_height']
            
            self.config.TELEGRAM_ENABLED = settings['telegram_enabled']
            self.config.TELEGRAM_TOKEN = settings['telegram_token']
            self.config.TELEGRAM_CHAT_ID = settings['telegram_chat_id']
            
        except Exception as e:
            self.logger.error(f"Error updating config object: {str(e)}")
    
    def reset_to_defaults(self):
        """Reset all settings to defaults"""
        try:
            reply = QMessageBox.question(self, 'Confirm Reset', 
                                       'Reset all settings to defaults?')
            if reply == QMessageBox.Yes:
                # Reset to original config values
                self.load_current_settings()
                QMessageBox.information(self, "Reset Complete", "Settings reset to defaults")
                self.logger.info("Settings reset to defaults")
        except Exception as e:
            self.logger.error(f"Error resetting settings: {str(e)}")
    
    def load_from_file(self):
        """Load settings from file"""
        try:
            filename, _ = QFileDialog.getOpenFileName(
                self, "Load Settings", "", "JSON Files (*.json);;All Files (*)"
            )
            
            if filename:
                success = self.config.load_user_config(filename)
                if success:
                    self.load_current_settings()
                    QMessageBox.information(self, "Success", "Settings loaded successfully!")
                    self.settings_loaded.emit()
                else:
                    QMessageBox.warning(self, "Error", "Failed to load settings from file")
        except Exception as e:
            self.logger.error(f"Error loading settings from file: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to load settings: {str(e)}")
    
    def export_settings(self):
        """Export current settings to file"""
        try:
            filename, _ = QFileDialog.getSaveFileName(
                self, "Export Settings", "trademaestro_settings.json", 
                "JSON Files (*.json);;All Files (*)"
            )
            
            if filename:
                current_values = self.get_current_values()
                self.update_config_object(current_values)
                
                success = self.config.save_config(filename)
                if success:
                    QMessageBox.information(self, "Success", f"Settings exported to {filename}")
                else:
                    QMessageBox.warning(self, "Error", "Failed to export settings")
        except Exception as e:
            self.logger.error(f"Error exporting settings: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to export settings: {str(e)}")
    
    def add_custom_symbol(self):
        """Add custom trading symbol"""
        try:
            symbol = self.custom_symbol_edit.text().strip().upper()
            if symbol and symbol not in self.symbol_checkboxes:
                # Add new checkbox for custom symbol
                checkbox = QCheckBox(symbol)
                checkbox.setChecked(True)
                self.symbol_checkboxes[symbol] = checkbox
                
                # Add to symbols grid (find next available position)
                symbols_grid = self.findChild(QGridLayout)
                if symbols_grid:
                    row = len(self.symbol_checkboxes) // 3
                    col = len(self.symbol_checkboxes) % 3
                    symbols_grid.addWidget(checkbox, row, col)
                
                self.custom_symbol_edit.clear()
                self.logger.info(f"Added custom symbol: {symbol}")
            elif symbol in self.symbol_checkboxes:
                QMessageBox.information(self, "Info", f"Symbol {symbol} already exists")
        except Exception as e:
            self.logger.error(f"Error adding custom symbol: {str(e)}")
    
    def get_settings_summary(self) -> str:
        """Get a text summary of current settings"""
        try:
            settings = self.get_current_values()
            summary_lines = [
                "=== TradeMaestro Settings Summary ===",
                "",
                "Trading Parameters:",
                f"  Default Lot Size: {settings['default_lot_size']:.2f}",
                f"  Stop Loss: {settings['default_stop_loss']} pips",
                f"  Take Profit: {settings['default_take_profit']} pips",
                f"  Max Positions: {settings['max_positions']}",
                "",
                "Risk Management:",
                f"  Max Risk per Trade: {settings['max_risk_per_trade']:.1%}",
                f"  Max Daily Loss: {settings['max_daily_loss']:.1%}",
                f"  Max Drawdown: {settings['max_drawdown']:.1%}",
                "",
                "Trading Symbols:",
                f"  Active Symbols: {', '.join(settings['default_symbols'])}",
                f"  Timeframe: {settings['strategy_timeframe']}",
                "",
                "System:",
                f"  Log Level: {settings['log_level']}",
                f"  Theme: {settings['gui_theme']}",
                f"  Telegram Enabled: {settings['telegram_enabled']}"
            ]
            
            return "\n".join(summary_lines)
        except Exception as e:
            return f"Error generating settings summary: {str(e)}"
    
    def has_unsaved_changes(self) -> bool:
        """Check if there are unsaved changes"""
        try:
            current_values = self.get_current_values()
            return current_values != self.original_settings
        except Exception:
            return False
    
    def prompt_save_changes(self) -> bool:
        """Prompt user to save changes if any exist"""
        try:
            if self.has_unsaved_changes():
                reply = QMessageBox.question(
                    self, 'Unsaved Changes',
                    'You have unsaved settings changes. Do you want to save them?',
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
                )
                
                if reply == QMessageBox.Yes:
                    self.save_settings()
                    return True
                elif reply == QMessageBox.Cancel:
                    return False
            
            return True
        except Exception as e:
            self.logger.error(f"Error prompting save changes: {str(e)}")
            return True

