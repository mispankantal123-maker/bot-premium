"""
TradeMaestro Main Window
Professional trading interface with real-time updates and comprehensive controls
"""

import sys
from datetime import datetime
from typing import Optional, Dict, Any

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QTextEdit, QTabWidget, QTableWidget, QTableWidgetItem,
    QProgressBar, QFrame, QSplitter, QGroupBox, QStatusBar, QMenuBar,
    QScrollArea, QHeaderView, QMessageBox, QSystemTrayIcon, QMenu
)
from PySide6.QtCore import QTimer, Signal, QThread, Qt, QSize
from PySide6.QtGui import QFont, QPixmap, QIcon, QAction, QPalette, QColor

from .settings_panel import SettingsPanel
from .strategy_panel import StrategyPanel
from ..utils.logger import Logger


class MainWindow(QMainWindow):
    """
    Main window for TradeMaestro trading bot
    Provides comprehensive trading interface with real-time monitoring
    """
    
    # Signals
    start_trading = Signal()
    stop_trading = Signal()
    shutdown_requested = Signal()
    
    def __init__(self, mt5_connector, strategy_manager, performance_tracker, config):
        super().__init__()
        
        # Core components
        self.mt5_connector = mt5_connector
        self.strategy_manager = strategy_manager
        self.performance_tracker = performance_tracker
        self.config = config
        self.logger = Logger(__name__)
        
        # GUI state
        self.is_trading = False
        self.connection_status = False
        self.current_theme = config.GUI_THEME if config else "dark"
        
        # UI components
        self.settings_panel = None
        self.strategy_panel = None
        self.central_widget = None
        self.status_bar = None
        self.system_tray = None
        
        # Data tables
        self.positions_table = None
        self.orders_table = None
        self.trades_table = None
        self.log_text = None
        
        # Status indicators
        self.connection_indicator = None
        self.balance_label = None
        self.equity_label = None
        self.profit_label = None
        self.trades_count_label = None
        self.win_rate_label = None
        
        # Control buttons
        self.start_button = None
        self.stop_button = None
        self.connect_button = None
        
        # Update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_interface)
        
        # Initialize UI
        self.setup_ui()
        self.setup_connections()
        self.apply_theme()
        self.setup_system_tray()
        
        # Start update timer
        update_interval = getattr(config, 'GUI_UPDATE_INTERVAL_MS', 1000)
        self.update_timer.start(update_interval)
        
        self.logger.info("🖥️ Main window initialized")
    
    def setup_ui(self):
        """Setup the main user interface"""
        try:
            # Set window properties
            self.setWindowTitle("TradeMaestro - Professional Trading Bot")
            self.setGeometry(100, 100, self.config.WINDOW_WIDTH, self.config.WINDOW_HEIGHT)
            self.setMinimumSize(1000, 700)
            
            # Create central widget
            self.central_widget = QWidget()
            self.setCentralWidget(self.central_widget)
            
            # Setup menu bar
            self.setup_menu_bar()
            
            # Setup status bar
            self.setup_status_bar()
            
            # Create main layout
            main_layout = QHBoxLayout(self.central_widget)
            
            # Create splitter for resizable panels
            main_splitter = QSplitter(Qt.Horizontal)
            
            # Left panel - Controls and Settings
            left_panel = self.create_left_panel()
            main_splitter.addWidget(left_panel)
            
            # Right panel - Trading interface
            right_panel = self.create_right_panel()
            main_splitter.addWidget(right_panel)
            
            # Set splitter proportions
            main_splitter.setSizes([350, 850])  # Left smaller, right larger
            
            main_layout.addWidget(main_splitter)
            
        except Exception as e:
            self.logger.error(f"Error setting up UI: {str(e)}")
            QMessageBox.critical(self, "UI Error", f"Failed to setup interface: {str(e)}")
    
    def create_left_panel(self) -> QWidget:
        """Create left control panel"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # Connection status group
        connection_group = QGroupBox("Connection Status")
        connection_layout = QGridLayout(connection_group)
        
        # Connection indicator
        self.connection_indicator = QLabel("●")
        self.connection_indicator.setFont(QFont("Arial", 16))
        self.connection_indicator.setStyleSheet("color: red;")
        connection_layout.addWidget(QLabel("MT5:"), 0, 0)
        connection_layout.addWidget(self.connection_indicator, 0, 1)
        
        # Connect button
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.toggle_connection)
        connection_layout.addWidget(self.connect_button, 0, 2)
        
        layout.addWidget(connection_group)
        
        # Trading controls group
        controls_group = QGroupBox("Trading Controls")
        controls_layout = QVBoxLayout(controls_group)
        
        # Start/Stop buttons
        button_layout = QHBoxLayout()
        
        self.start_button = QPushButton("▶ Start Trading")
        self.start_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 10px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.start_button.clicked.connect(self.on_start_trading)
        self.start_button.setEnabled(False)
        
        self.stop_button = QPushButton("⏹ Stop Trading")
        self.stop_button.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                padding: 10px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.stop_button.clicked.connect(self.on_stop_trading)
        self.stop_button.setEnabled(False)
        
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        controls_layout.addLayout(button_layout)
        
        layout.addWidget(controls_group)
        
        # Account info group
        account_group = QGroupBox("Account Information")
        account_layout = QGridLayout(account_group)
        
        # Account labels
        account_layout.addWidget(QLabel("Balance:"), 0, 0)
        self.balance_label = QLabel("$0.00")
        self.balance_label.setFont(QFont("Arial", 12, QFont.Bold))
        account_layout.addWidget(self.balance_label, 0, 1)
        
        account_layout.addWidget(QLabel("Equity:"), 1, 0)
        self.equity_label = QLabel("$0.00")
        self.equity_label.setFont(QFont("Arial", 12, QFont.Bold))
        account_layout.addWidget(self.equity_label, 1, 1)
        
        account_layout.addWidget(QLabel("Profit:"), 2, 0)
        self.profit_label = QLabel("$0.00")
        self.profit_label.setFont(QFont("Arial", 12, QFont.Bold))
        account_layout.addWidget(self.profit_label, 2, 1)
        
        layout.addWidget(account_group)
        
        # Performance group
        performance_group = QGroupBox("Performance")
        performance_layout = QGridLayout(performance_group)
        
        performance_layout.addWidget(QLabel("Trades:"), 0, 0)
        self.trades_count_label = QLabel("0")
        performance_layout.addWidget(self.trades_count_label, 0, 1)
        
        performance_layout.addWidget(QLabel("Win Rate:"), 1, 0)
        self.win_rate_label = QLabel("0%")
        performance_layout.addWidget(self.win_rate_label, 1, 1)
        
        layout.addWidget(performance_group)
        
        # Settings panel
        self.settings_panel = SettingsPanel(self.config)
        settings_scroll = QScrollArea()
        settings_scroll.setWidget(self.settings_panel)
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setMaximumHeight(300)
        
        layout.addWidget(settings_scroll)
        
        # Strategy panel
        self.strategy_panel = StrategyPanel(self.strategy_manager, self.config)
        strategy_scroll = QScrollArea()
        strategy_scroll.setWidget(self.strategy_panel)
        strategy_scroll.setWidgetResizable(True)
        strategy_scroll.setMaximumHeight(200)
        
        layout.addWidget(strategy_scroll)
        
        layout.addStretch()  # Push everything to top
        
        return panel
    
    def create_right_panel(self) -> QWidget:
        """Create right trading interface panel"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # Create tab widget for different views
        tab_widget = QTabWidget()
        
        # Trading tab
        trading_tab = self.create_trading_tab()
        tab_widget.addTab(trading_tab, "Trading")
        
        # Positions tab
        positions_tab = self.create_positions_tab()
        tab_widget.addTab(positions_tab, "Positions")
        
        # Orders tab
        orders_tab = self.create_orders_tab()
        tab_widget.addTab(orders_tab, "Orders")
        
        # History tab
        history_tab = self.create_history_tab()
        tab_widget.addTab(history_tab, "History")
        
        # Logs tab
        logs_tab = self.create_logs_tab()
        tab_widget.addTab(logs_tab, "Logs")
        
        layout.addWidget(tab_widget)
        
        return panel
    
    def create_trading_tab(self) -> QWidget:
        """Create main trading interface tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Market overview
        market_group = QGroupBox("Market Overview")
        market_layout = QVBoxLayout(market_group)
        
        # Create market data table
        market_table = QTableWidget(0, 6)
        market_table.setHorizontalHeaderLabels([
            "Symbol", "Bid", "Ask", "Spread", "Change", "Time"
        ])
        market_table.horizontalHeader().setStretchLastSection(True)
        market_table.setAlternatingRowColors(True)
        market_table.setMaximumHeight(200)
        
        market_layout.addWidget(market_table)
        layout.addWidget(market_group)
        
        # Current strategy info
        strategy_info_group = QGroupBox("Current Strategy")
        strategy_info_layout = QGridLayout(strategy_info_group)
        
        strategy_info_layout.addWidget(QLabel("Strategy:"), 0, 0)
        self.current_strategy_label = QLabel("None")
        self.current_strategy_label.setFont(QFont("Arial", 10, QFont.Bold))
        strategy_info_layout.addWidget(self.current_strategy_label, 0, 1)
        
        strategy_info_layout.addWidget(QLabel("Status:"), 0, 2)
        self.strategy_status_label = QLabel("Idle")
        strategy_info_layout.addWidget(self.strategy_status_label, 0, 3)
        
        strategy_info_layout.addWidget(QLabel("Last Signal:"), 1, 0)
        self.last_signal_label = QLabel("None")
        strategy_info_layout.addWidget(self.last_signal_label, 1, 1)
        
        strategy_info_layout.addWidget(QLabel("Signal Time:"), 1, 2)
        self.signal_time_label = QLabel("Never")
        strategy_info_layout.addWidget(self.signal_time_label, 1, 3)
        
        layout.addWidget(strategy_info_group)
        
        layout.addStretch()
        
        return widget
    
    def create_positions_tab(self) -> QWidget:
        """Create positions monitoring tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Positions table
        self.positions_table = QTableWidget(0, 9)
        self.positions_table.setHorizontalHeaderLabels([
            "Ticket", "Symbol", "Type", "Volume", "Open Price", 
            "Current Price", "S/L", "T/P", "Profit"
        ])
        self.positions_table.horizontalHeader().setStretchLastSection(True)
        self.positions_table.setAlternatingRowColors(True)
        self.positions_table.setSelectionBehavior(QTableWidget.SelectRows)
        
        layout.addWidget(self.positions_table)
        
        # Position controls
        controls_layout = QHBoxLayout()
        
        close_selected_btn = QPushButton("Close Selected")
        close_selected_btn.clicked.connect(self.close_selected_position)
        controls_layout.addWidget(close_selected_btn)
        
        close_all_btn = QPushButton("Close All")
        close_all_btn.clicked.connect(self.close_all_positions)
        controls_layout.addWidget(close_all_btn)
        
        controls_layout.addStretch()
        
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_positions)
        controls_layout.addWidget(refresh_btn)
        
        layout.addLayout(controls_layout)
        
        return widget
    
    def create_orders_tab(self) -> QWidget:
        """Create pending orders tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Orders table
        self.orders_table = QTableWidget(0, 8)
        self.orders_table.setHorizontalHeaderLabels([
            "Ticket", "Symbol", "Type", "Volume", "Price", "S/L", "T/P", "Time"
        ])
        self.orders_table.horizontalHeader().setStretchLastSection(True)
        self.orders_table.setAlternatingRowColors(True)
        self.orders_table.setSelectionBehavior(QTableWidget.SelectRows)
        
        layout.addWidget(self.orders_table)
        
        # Order controls
        controls_layout = QHBoxLayout()
        
        cancel_selected_btn = QPushButton("Cancel Selected")
        cancel_selected_btn.clicked.connect(self.cancel_selected_order)
        controls_layout.addWidget(cancel_selected_btn)
        
        cancel_all_btn = QPushButton("Cancel All")
        cancel_all_btn.clicked.connect(self.cancel_all_orders)
        controls_layout.addWidget(cancel_all_btn)
        
        controls_layout.addStretch()
        
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_orders)
        controls_layout.addWidget(refresh_btn)
        
        layout.addLayout(controls_layout)
        
        return widget
    
    def create_history_tab(self) -> QWidget:
        """Create trade history tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # History table
        self.trades_table = QTableWidget(0, 10)
        self.trades_table.setHorizontalHeaderLabels([
            "Time", "Symbol", "Type", "Volume", "Open Price", 
            "Close Price", "S/L", "T/P", "Profit", "Comment"
        ])
        self.trades_table.horizontalHeader().setStretchLastSection(True)
        self.trades_table.setAlternatingRowColors(True)
        
        layout.addWidget(self.trades_table)
        
        # History controls
        controls_layout = QHBoxLayout()
        
        export_btn = QPushButton("Export History")
        export_btn.clicked.connect(self.export_trade_history)
        controls_layout.addWidget(export_btn)
        
        clear_btn = QPushButton("Clear History")
        clear_btn.clicked.connect(self.clear_trade_history)
        controls_layout.addWidget(clear_btn)
        
        controls_layout.addStretch()
        
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_history)
        controls_layout.addWidget(refresh_btn)
        
        layout.addLayout(controls_layout)
        
        return widget
    
    def create_logs_tab(self) -> QWidget:
        """Create logs monitoring tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Log text area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        self.log_text.setMaximumBlockCount(1000)  # Limit log size
        
        layout.addWidget(self.log_text)
        
        # Log controls
        controls_layout = QHBoxLayout()
        
        clear_logs_btn = QPushButton("Clear Logs")
        clear_logs_btn.clicked.connect(self.clear_logs)
        controls_layout.addWidget(clear_logs_btn)
        
        save_logs_btn = QPushButton("Save Logs")
        save_logs_btn.clicked.connect(self.save_logs)
        controls_layout.addWidget(save_logs_btn)
        
        controls_layout.addStretch()
        
        auto_scroll_btn = QPushButton("Auto Scroll: ON")
        auto_scroll_btn.setCheckable(True)
        auto_scroll_btn.setChecked(True)
        auto_scroll_btn.clicked.connect(self.toggle_auto_scroll)
        controls_layout.addWidget(auto_scroll_btn)
        
        layout.addLayout(controls_layout)
        
        return widget
    
    def setup_menu_bar(self):
        """Setup application menu bar"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu('File')
        
        # Export performance report
        export_action = QAction('Export Performance Report', self)
        export_action.triggered.connect(self.export_performance_report)
        file_menu.addAction(export_action)
        
        file_menu.addSeparator()
        
        # Exit action
        exit_action = QAction('Exit', self)
        exit_action.setShortcut('Ctrl+Q')
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Trading menu
        trading_menu = menubar.addMenu('Trading')
        
        connect_action = QAction('Connect to MT5', self)
        connect_action.triggered.connect(self.toggle_connection)
        trading_menu.addAction(connect_action)
        
        start_action = QAction('Start Trading', self)
        start_action.triggered.connect(self.on_start_trading)
        trading_menu.addAction(start_action)
        
        stop_action = QAction('Stop Trading', self)
        stop_action.triggered.connect(self.on_stop_trading)
        trading_menu.addAction(stop_action)
        
        # View menu
        view_menu = menubar.addMenu('View')
        
        theme_action = QAction('Toggle Theme', self)
        theme_action.triggered.connect(self.toggle_theme)
        view_menu.addAction(theme_action)
        
        # Help menu
        help_menu = menubar.addMenu('Help')
        
        about_action = QAction('About', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def setup_status_bar(self):
        """Setup status bar"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # Add permanent widgets to status bar
        self.status_label = QLabel("Ready")
        self.status_bar.addWidget(self.status_label)
        
        # Connection status
        self.status_connection = QLabel("Disconnected")
        self.status_bar.addPermanentWidget(self.status_connection)
        
        # Trading status
        self.status_trading = QLabel("Idle")
        self.status_bar.addPermanentWidget(self.status_trading)
        
        # Time
        self.status_time = QLabel()
        self.status_bar.addPermanentWidget(self.status_time)
        
        # Update time
        self.update_status_time()
    
    def setup_system_tray(self):
        """Setup system tray icon"""
        try:
            if QSystemTrayIcon.isSystemTrayAvailable():
                self.system_tray = QSystemTrayIcon(self)
                
                # Create tray menu
                tray_menu = QMenu()
                
                show_action = tray_menu.addAction("Show")
                show_action.triggered.connect(self.show)
                
                tray_menu.addSeparator()
                
                exit_action = tray_menu.addAction("Exit")
                exit_action.triggered.connect(self.close)
                
                self.system_tray.setContextMenu(tray_menu)
                
                # Set icon (use default icon for now)
                self.system_tray.setIcon(self.style().standardIcon(self.style().SP_ComputerIcon))
                self.system_tray.show()
                
        except Exception as e:
            self.logger.warning(f"Could not setup system tray: {str(e)}")
    
    def setup_connections(self):
        """Setup signal connections"""
        try:
            # Connect to MT5 connector signals
            if self.mt5_connector:
                self.mt5_connector.connection_status_changed.connect(self.update_connection_status)
                self.mt5_connector.account_info_updated.connect(self.update_account_info)
                self.mt5_connector.error_occurred.connect(self.show_error_message)
            
            # Connect to performance tracker signals
            if self.performance_tracker:
                self.performance_tracker.performance_updated.connect(self.update_performance_display)
                self.performance_tracker.trade_recorded.connect(self.on_trade_recorded)
            
            # Connect settings panel signals
            if self.settings_panel:
                self.settings_panel.settings_changed.connect(self.on_settings_changed)
            
            # Connect strategy panel signals
            if self.strategy_panel:
                self.strategy_panel.strategy_changed.connect(self.on_strategy_changed)
            
        except Exception as e:
            self.logger.error(f"Error setting up connections: {str(e)}")
    
    def apply_theme(self):
        """Apply UI theme"""
        try:
            if self.current_theme == "dark":
                self.setStyleSheet("""
                    QMainWindow {
                        background-color: #2b2b2b;
                        color: #ffffff;
                    }
                    QWidget {
                        background-color: #2b2b2b;
                        color: #ffffff;
                    }
                    QGroupBox {
                        font-weight: bold;
                        border: 2px solid #555555;
                        border-radius: 5px;
                        margin-top: 10px;
                        padding-top: 10px;
                    }
                    QGroupBox::title {
                        subcontrol-origin: margin;
                        left: 10px;
                        padding: 0 5px 0 5px;
                    }
                    QTabWidget::pane {
                        border: 1px solid #555555;
                    }
                    QTabBar::tab {
                        background-color: #3c3c3c;
                        color: #ffffff;
                        border: 1px solid #555555;
                        padding: 8px 16px;
                    }
                    QTabBar::tab:selected {
                        background-color: #4CAF50;
                    }
                    QTableWidget {
                        gridline-color: #555555;
                        background-color: #3c3c3c;
                        alternate-background-color: #2b2b2b;
                    }
                    QHeaderView::section {
                        background-color: #4CAF50;
                        color: white;
                        padding: 4px;
                        border: 1px solid #555555;
                        font-weight: bold;
                    }
                    QPushButton {
                        background-color: #4CAF50;
                        color: white;
                        border: none;
                        padding: 6px 12px;
                        border-radius: 3px;
                    }
                    QPushButton:hover {
                        background-color: #45a049;
                    }
                    QPushButton:disabled {
                        background-color: #666666;
                    }
                    QTextEdit {
                        background-color: #1e1e1e;
                        color: #ffffff;
                        border: 1px solid #555555;
                    }
                    QLabel {
                        color: #ffffff;
                    }
                    QStatusBar {
                        background-color: #3c3c3c;
                        color: #ffffff;
                    }
                """)
            else:
                # Light theme
                self.setStyleSheet("")
            
        except Exception as e:
            self.logger.error(f"Error applying theme: {str(e)}")
    
    def update_interface(self):
        """Update interface with current data"""
        try:
            # Update status time
            self.update_status_time()
            
            # Update connection status
            if self.mt5_connector:
                connected = self.mt5_connector.is_connected()
                if connected != self.connection_status:
                    self.update_connection_status(connected, "Connected" if connected else "Disconnected")
            
            # Update account info if connected
            if self.connection_status and self.mt5_connector:
                account_info = self.mt5_connector.get_account_info()
                if account_info:
                    self.update_account_info(account_info)
            
            # Update positions table
            self.refresh_positions()
            
            # Update orders table
            self.refresh_orders()
            
        except Exception as e:
            self.logger.error(f"Error updating interface: {str(e)}")
    
    def update_status_time(self):
        """Update status bar time"""
        current_time = datetime.now().strftime("%H:%M:%S")
        if hasattr(self, 'status_time'):
            self.status_time.setText(current_time)
    
    def update_connection_status(self, connected: bool, message: str):
        """Update connection status display"""
        try:
            self.connection_status = connected
            
            if connected:
                self.connection_indicator.setStyleSheet("color: green;")
                self.connection_indicator.setText("●")
                self.connect_button.setText("Disconnect")
                self.start_button.setEnabled(True)
                self.status_connection.setText("Connected")
            else:
                self.connection_indicator.setStyleSheet("color: red;")
                self.connection_indicator.setText("●")
                self.connect_button.setText("Connect")
                self.start_button.setEnabled(False)
                self.stop_button.setEnabled(False)
                self.status_connection.setText("Disconnected")
                
                if self.is_trading:
                    self.on_stop_trading()
            
            self.logger.info(f"Connection status: {message}")
            
        except Exception as e:
            self.logger.error(f"Error updating connection status: {str(e)}")
    
    def update_account_info(self, account_info: Dict[str, Any]):
        """Update account information display"""
        try:
            balance = account_info.get('balance', 0.0)
            equity = account_info.get('equity', 0.0)
            profit = account_info.get('profit', 0.0)
            currency = account_info.get('currency', 'USD')
            
            self.balance_label.setText(f"{currency} {balance:,.2f}")
            self.equity_label.setText(f"{currency} {equity:,.2f}")
            
            # Color profit based on positive/negative
            if profit >= 0:
                self.profit_label.setStyleSheet("color: green; font-weight: bold;")
                self.profit_label.setText(f"+{currency} {profit:,.2f}")
            else:
                self.profit_label.setStyleSheet("color: red; font-weight: bold;")
                self.profit_label.setText(f"{currency} {profit:,.2f}")
            
        except Exception as e:
            self.logger.error(f"Error updating account info: {str(e)}")
    
    def update_performance_display(self, performance_data: Dict[str, Any]):
        """Update performance metrics display"""
        try:
            total_trades = performance_data.get('total_trades', 0)
            win_rate = performance_data.get('win_rate', 0.0)
            
            self.trades_count_label.setText(str(total_trades))
            self.win_rate_label.setText(f"{win_rate:.1f}%")
            
        except Exception as e:
            self.logger.error(f"Error updating performance display: {str(e)}")
    
    def update_trade_info(self, trade_info: Dict[str, Any]):
        """Update trade information"""
        try:
            # This would be called when a trade is executed
            # Add to recent trades or update displays as needed
            pass
        except Exception as e:
            self.logger.error(f"Error updating trade info: {str(e)}")
    
    def update_signals(self, signal_info: Dict[str, Any]):
        """Update signal information"""
        try:
            if hasattr(self, 'last_signal_label'):
                signal_type = signal_info.get('signal', 'NONE')
                self.last_signal_label.setText(signal_type)
                
            if hasattr(self, 'signal_time_label'):
                self.signal_time_label.setText(datetime.now().strftime("%H:%M:%S"))
                
        except Exception as e:
            self.logger.error(f"Error updating signals: {str(e)}")
    
    def show_error(self, message: str):
        """Show error message"""
        try:
            QMessageBox.warning(self, "Error", message)
            self.log_message(f"ERROR: {message}")
        except Exception as e:
            self.logger.error(f"Error showing error message: {str(e)}")
    
    def show_error_message(self, message: str):
        """Show error message from signals"""
        self.show_error(message)
    
    def update_status(self, message: str):
        """Update status message"""
        try:
            if hasattr(self, 'status_label'):
                self.status_label.setText(message)
            self.log_message(message)
        except Exception as e:
            self.logger.error(f"Error updating status: {str(e)}")
    
    def log_message(self, message: str):
        """Add message to log display"""
        try:
            if self.log_text:
                timestamp = datetime.now().strftime("%H:%M:%S")
                formatted_message = f"[{timestamp}] {message}"
                self.log_text.append(formatted_message)
                
                # Auto-scroll if enabled
                scrollbar = self.log_text.verticalScrollBar()
                if scrollbar.value() == scrollbar.maximum():
                    self.log_text.ensureCursorVisible()
                    
        except Exception as e:
            self.logger.error(f"Error logging message: {str(e)}")
    
    # Event handlers
    def on_start_trading(self):
        """Handle start trading button click"""
        try:
            if not self.connection_status:
                QMessageBox.warning(self, "Warning", "Please connect to MT5 first!")
                return
                
            self.is_trading = True
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self.status_trading.setText("Trading")
            
            self.start_trading.emit()
            self.log_message("🎯 Trading started")
            
        except Exception as e:
            self.logger.error(f"Error starting trading: {str(e)}")
            self.show_error(f"Failed to start trading: {str(e)}")
    
    def on_stop_trading(self):
        """Handle stop trading button click"""
        try:
            self.is_trading = False
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.status_trading.setText("Idle")
            
            self.stop_trading.emit()
            self.log_message("⏹️ Trading stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping trading: {str(e)}")
    
    def toggle_connection(self):
        """Toggle MT5 connection"""
        try:
            if self.connection_status:
                # Disconnect
                if self.mt5_connector:
                    self.mt5_connector.disconnect()
            else:
                # Connect
                if self.mt5_connector:
                    success = self.mt5_connector.connect()
                    if not success:
                        QMessageBox.critical(self, "Connection Error", 
                                           "Failed to connect to MT5. Please check your settings.")
        except Exception as e:
            self.logger.error(f"Error toggling connection: {str(e)}")
            QMessageBox.critical(self, "Connection Error", f"Connection error: {str(e)}")
    
    def on_trade_recorded(self, trade_data: Dict[str, Any]):
        """Handle new trade recorded"""
        try:
            symbol = trade_data.get('symbol', '')
            trade_type = trade_data.get('type', '')
            profit = trade_data.get('profit', 0.0)
            
            self.log_message(f"📊 Trade completed: {trade_type} {symbol} - Profit: {profit:.2f}")
            
            # Refresh history table
            self.refresh_history()
            
        except Exception as e:
            self.logger.error(f"Error handling trade recorded: {str(e)}")
    
    def on_settings_changed(self, settings: Dict[str, Any]):
        """Handle settings changes"""
        try:
            self.log_message("⚙️ Settings updated")
        except Exception as e:
            self.logger.error(f"Error handling settings change: {str(e)}")
    
    def on_strategy_changed(self, strategy_name: str):
        """Handle strategy change"""
        try:
            if hasattr(self, 'current_strategy_label'):
                self.current_strategy_label.setText(strategy_name)
            self.log_message(f"📈 Strategy changed to: {strategy_name}")
        except Exception as e:
            self.logger.error(f"Error handling strategy change: {str(e)}")
    
    # Table management methods
    def refresh_positions(self):
        """Refresh positions table"""
        try:
            if not self.positions_table or not self.mt5_connector or not self.connection_status:
                return
                
            positions = self.mt5_connector.get_positions()
            
            self.positions_table.setRowCount(len(positions))
            
            for row, position in enumerate(positions):
                self.positions_table.setItem(row, 0, QTableWidgetItem(str(position.get('ticket', ''))))
                self.positions_table.setItem(row, 1, QTableWidgetItem(position.get('symbol', '')))
                self.positions_table.setItem(row, 2, QTableWidgetItem('BUY' if position.get('type') == 0 else 'SELL'))
                self.positions_table.setItem(row, 3, QTableWidgetItem(f"{position.get('volume', 0):.2f}"))
                self.positions_table.setItem(row, 4, QTableWidgetItem(f"{position.get('price_open', 0):.5f}"))
                self.positions_table.setItem(row, 5, QTableWidgetItem(f"{position.get('price_current', 0):.5f}"))
                self.positions_table.setItem(row, 6, QTableWidgetItem(f"{position.get('sl', 0):.5f}"))
                self.positions_table.setItem(row, 7, QTableWidgetItem(f"{position.get('tp', 0):.5f}"))
                
                # Color profit cell
                profit = position.get('profit', 0)
                profit_item = QTableWidgetItem(f"{profit:.2f}")
                if profit > 0:
                    profit_item.setBackground(QColor(0, 255, 0, 50))
                elif profit < 0:
                    profit_item.setBackground(QColor(255, 0, 0, 50))
                self.positions_table.setItem(row, 8, profit_item)
                
        except Exception as e:
            self.logger.error(f"Error refreshing positions: {str(e)}")
    
    def refresh_orders(self):
        """Refresh orders table"""
        try:
            if not self.orders_table or not self.mt5_connector or not self.connection_status:
                return
                
            orders = self.mt5_connector.get_orders()
            
            self.orders_table.setRowCount(len(orders))
            
            for row, order in enumerate(orders):
                self.orders_table.setItem(row, 0, QTableWidgetItem(str(order.get('ticket', ''))))
                self.orders_table.setItem(row, 1, QTableWidgetItem(order.get('symbol', '')))
                self.orders_table.setItem(row, 2, QTableWidgetItem(str(order.get('type', ''))))
                self.orders_table.setItem(row, 3, QTableWidgetItem(f"{order.get('volume_current', 0):.2f}"))
                self.orders_table.setItem(row, 4, QTableWidgetItem(f"{order.get('price_open', 0):.5f}"))
                self.orders_table.setItem(row, 5, QTableWidgetItem(f"{order.get('sl', 0):.5f}"))
                self.orders_table.setItem(row, 6, QTableWidgetItem(f"{order.get('tp', 0):.5f}"))
                
                time_setup = order.get('time_setup')
                if time_setup:
                    if isinstance(time_setup, datetime):
                        time_str = time_setup.strftime("%H:%M:%S")
                    else:
                        time_str = str(time_setup)
                    self.orders_table.setItem(row, 7, QTableWidgetItem(time_str))
                
        except Exception as e:
            self.logger.error(f"Error refreshing orders: {str(e)}")
    
    def refresh_history(self):
        """Refresh trade history table"""
        try:
            if not self.trades_table or not self.performance_tracker:
                return
                
            # Get recent trades from performance tracker
            trades_df = self.performance_tracker.get_trade_history_df(days=7)  # Last 7 days
            
            if trades_df.empty:
                self.trades_table.setRowCount(0)
                return
            
            self.trades_table.setRowCount(len(trades_df))
            
            for row, (timestamp, trade) in enumerate(trades_df.iterrows()):
                self.trades_table.setItem(row, 0, QTableWidgetItem(timestamp.strftime("%m/%d %H:%M")))
                self.trades_table.setItem(row, 1, QTableWidgetItem(trade.get('symbol', '')))
                self.trades_table.setItem(row, 2, QTableWidgetItem(trade.get('type', '')))
                self.trades_table.setItem(row, 3, QTableWidgetItem(f"{trade.get('volume', 0):.2f}"))
                self.trades_table.setItem(row, 4, QTableWidgetItem(f"{trade.get('open_price', 0):.5f}"))
                self.trades_table.setItem(row, 5, QTableWidgetItem(f"{trade.get('close_price', 0):.5f}"))
                self.trades_table.setItem(row, 6, QTableWidgetItem(f"{trade.get('stop_loss', 0):.5f}"))
                self.trades_table.setItem(row, 7, QTableWidgetItem(f"{trade.get('take_profit', 0):.5f}"))
                
                # Color profit cell
                profit = trade.get('profit', 0)
                profit_item = QTableWidgetItem(f"{profit:.2f}")
                if profit > 0:
                    profit_item.setBackground(QColor(0, 255, 0, 50))
                elif profit < 0:
                    profit_item.setBackground(QColor(255, 0, 0, 50))
                self.trades_table.setItem(row, 8, profit_item)
                
                self.trades_table.setItem(row, 9, QTableWidgetItem(trade.get('comment', '')))
                
        except Exception as e:
            self.logger.error(f"Error refreshing history: {str(e)}")
    
    # Action handlers
    def close_selected_position(self):
        """Close selected position"""
        try:
            current_row = self.positions_table.currentRow()
            if current_row >= 0:
                ticket_item = self.positions_table.item(current_row, 0)
                if ticket_item:
                    ticket = int(ticket_item.text())
                    # Close position through order manager
                    # This would be implemented in the order manager integration
                    self.log_message(f"Closing position {ticket}")
        except Exception as e:
            self.logger.error(f"Error closing position: {str(e)}")
    
    def close_all_positions(self):
        """Close all positions"""
        try:
            reply = QMessageBox.question(self, 'Confirm', 'Close all positions?')
            if reply == QMessageBox.Yes:
                # Close all positions through order manager
                self.log_message("Closing all positions")
        except Exception as e:
            self.logger.error(f"Error closing all positions: {str(e)}")
    
    def cancel_selected_order(self):
        """Cancel selected order"""
        try:
            current_row = self.orders_table.currentRow()
            if current_row >= 0:
                ticket_item = self.orders_table.item(current_row, 0)
                if ticket_item:
                    ticket = int(ticket_item.text())
                    self.log_message(f"Cancelling order {ticket}")
        except Exception as e:
            self.logger.error(f"Error cancelling order: {str(e)}")
    
    def cancel_all_orders(self):
        """Cancel all orders"""
        try:
            reply = QMessageBox.question(self, 'Confirm', 'Cancel all pending orders?')
            if reply == QMessageBox.Yes:
                self.log_message("Cancelling all orders")
        except Exception as e:
            self.logger.error(f"Error cancelling all orders: {str(e)}")
    
    def export_trade_history(self):
        """Export trade history"""
        try:
            if self.performance_tracker:
                filepath = self.performance_tracker.export_performance_report()
                if filepath:
                    QMessageBox.information(self, 'Export Complete', f'History exported to:\n{filepath}')
                else:
                    QMessageBox.warning(self, 'Export Failed', 'Failed to export trade history')
        except Exception as e:
            self.logger.error(f"Error exporting history: {str(e)}")
    
    def clear_trade_history(self):
        """Clear trade history"""
        try:
            reply = QMessageBox.question(self, 'Confirm', 'Clear all trade history?')
            if reply == QMessageBox.Yes:
                if self.trades_table:
                    self.trades_table.setRowCount(0)
                self.log_message("Trade history cleared")
        except Exception as e:
            self.logger.error(f"Error clearing history: {str(e)}")
    
    def clear_logs(self):
        """Clear log display"""
        try:
            if self.log_text:
                self.log_text.clear()
        except Exception as e:
            self.logger.error(f"Error clearing logs: {str(e)}")
    
    def save_logs(self):
        """Save logs to file"""
        try:
            if self.log_text:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"trademaestro_logs_{timestamp}.txt"
                
                with open(filename, 'w') as f:
                    f.write(self.log_text.toPlainText())
                
                QMessageBox.information(self, 'Logs Saved', f'Logs saved to {filename}')
        except Exception as e:
            self.logger.error(f"Error saving logs: {str(e)}")
    
    def toggle_auto_scroll(self):
        """Toggle auto-scroll for logs"""
        # Implementation for auto-scroll toggle
        pass
    
    def export_performance_report(self):
        """Export performance report"""
        try:
            if self.performance_tracker:
                filepath = self.performance_tracker.export_performance_report()
                if filepath:
                    QMessageBox.information(self, 'Report Exported', f'Performance report exported to:\n{filepath}')
        except Exception as e:
            self.logger.error(f"Error exporting performance report: {str(e)}")
    
    def toggle_theme(self):
        """Toggle UI theme"""
        try:
            self.current_theme = "light" if self.current_theme == "dark" else "dark"
            self.apply_theme()
        except Exception as e:
            self.logger.error(f"Error toggling theme: {str(e)}")
    
    def show_about(self):
        """Show about dialog"""
        QMessageBox.about(self, "About TradeMaestro", 
                         "TradeMaestro v2.0\n\nProfessional MetaTrader5 Trading Bot\n"
                         "Built with Python and PySide6\n\n"
                         "Features:\n"
                         "• Multi-strategy trading\n"
                         "• Risk management\n"
                         "• Performance tracking\n"
                         "• Real-time monitoring")
    
    def closeEvent(self, event):
        """Handle window close event"""
        try:
            if self.is_trading:
                reply = QMessageBox.question(self, 'Confirm Exit', 
                                           'Trading is active. Are you sure you want to exit?')
                if reply != QMessageBox.Yes:
                    event.ignore()
                    return
            
            # Emit shutdown signal
            self.shutdown_requested.emit()
            
            # Stop timer
            if self.update_timer:
                self.update_timer.stop()
            
            # Hide to system tray if available
            if self.system_tray and self.system_tray.isVisible():
                self.hide()
                event.ignore()
            else:
                event.accept()
                
        except Exception as e:
            self.logger.error(f"Error during close: {str(e)}")
            event.accept()

