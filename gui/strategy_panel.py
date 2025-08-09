"""
Strategy Panel for TradeMaestro
Interface for selecting and configuring trading strategies
"""

from typing import Dict, Any, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QLabel, QComboBox, QPushButton, QSlider,
    QSpinBox, QDoubleSpinBox, QCheckBox, QTextEdit,
    QProgressBar, QFrame, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QTabWidget
)
from PySide6.QtCore import Signal, Qt, QTimer
from PySide6.QtGui import QFont, QColor

from ..utils.logger import Logger


class StrategyPanel(QWidget):
    """
    Strategy selection and configuration panel
    Provides interface for choosing and customizing trading strategies
    """
    
    # Signals
    strategy_changed = Signal(str)  # strategy_name
    strategy_configured = Signal(str, dict)  # strategy_name, parameters
    strategy_started = Signal(str)  # strategy_name
    strategy_stopped = Signal(str)  # strategy_name
    
    def __init__(self, strategy_manager, config, parent=None):
        super().__init__(parent)
        
        self.strategy_manager = strategy_manager
        self.config = config
        self.logger = Logger(__name__)
        
        # Current state
        self.current_strategy = None
        self.strategy_parameters = {}
        self.strategy_status = "Stopped"
        
        # Performance tracking
        self.strategy_performance = {}
        
        # Update timer for real-time data
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_strategy_info)
        self.update_timer.start(2000)  # Update every 2 seconds
        
        # Setup UI
        self.setup_ui()
        self.load_available_strategies()
        
        self.logger.debug("Strategy panel initialized")
    
    def setup_ui(self):
        """Setup the strategy panel interface"""
        try:
            layout = QVBoxLayout(self)
            
            # Strategy selection group
            selection_group = QGroupBox("Strategy Selection")
            selection_layout = QVBoxLayout(selection_group)
            
            # Strategy selector
            selector_layout = QHBoxLayout()
            selector_layout.addWidget(QLabel("Active Strategy:"))
            
            self.strategy_combo = QComboBox()
            self.strategy_combo.currentTextChanged.connect(self.on_strategy_selected)
            selector_layout.addWidget(self.strategy_combo)
            
            self.switch_button = QPushButton("Switch Strategy")
            self.switch_button.clicked.connect(self.switch_strategy)
            selector_layout.addWidget(self.switch_button)
            
            selection_layout.addLayout(selector_layout)
            
            # Strategy status
            status_layout = QHBoxLayout()
            status_layout.addWidget(QLabel("Status:"))
            
            self.status_label = QLabel("Stopped")
            self.status_label.setFont(QFont("Arial", 10, QFont.Bold))
            self.status_label.setStyleSheet("color: red;")
            status_layout.addWidget(self.status_label)
            
            status_layout.addStretch()
            
            # Performance indicators
            self.win_rate_label = QLabel("Win Rate: 0%")
            status_layout.addWidget(self.win_rate_label)
            
            self.profit_label = QLabel("Profit: $0.00")
            status_layout.addWidget(self.profit_label)
            
            selection_layout.addLayout(status_layout)
            
            layout.addWidget(selection_group)
            
            # Strategy configuration tabs
            self.config_tabs = QTabWidget()
            
            # Parameters tab
            params_tab = self.create_parameters_tab()
            self.config_tabs.addTab(params_tab, "Parameters")
            
            # Performance tab
            performance_tab = self.create_performance_tab()
            self.config_tabs.addTab(performance_tab, "Performance")
            
            # Signals tab
            signals_tab = self.create_signals_tab()
            self.config_tabs.addTab(signals_tab, "Signals")
            
            layout.addWidget(self.config_tabs)
            
        except Exception as e:
            self.logger.error(f"Error setting up strategy panel UI: {str(e)}")
    
    def create_parameters_tab(self) -> QWidget:
        """Create strategy parameters configuration tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Dynamic parameters group (will be populated based on selected strategy)
        self.parameters_group = QGroupBox("Strategy Parameters")
        self.parameters_layout = QGridLayout(self.parameters_group)
        layout.addWidget(self.parameters_group)
        
        # Strategy description
        description_group = QGroupBox("Strategy Description")
        description_layout = QVBoxLayout(description_group)
        
        self.strategy_description = QTextEdit()
        self.strategy_description.setReadOnly(True)
        self.strategy_description.setMaximumHeight(100)
        description_layout.addWidget(self.strategy_description)
        
        layout.addWidget(description_group)
        
        # Control buttons
        button_layout = QHBoxLayout()
        
        self.apply_params_button = QPushButton("Apply Parameters")
        self.apply_params_button.clicked.connect(self.apply_parameters)
        button_layout.addWidget(self.apply_params_button)
        
        self.reset_params_button = QPushButton("Reset to Defaults")
        self.reset_params_button.clicked.connect(self.reset_parameters)
        button_layout.addWidget(self.reset_params_button)
        
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        layout.addStretch()
        
        return widget
    
    def create_performance_tab(self) -> QWidget:
        """Create strategy performance monitoring tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Performance metrics
        metrics_group = QGroupBox("Performance Metrics")
        metrics_layout = QGridLayout(metrics_group)
        
        # Total trades
        metrics_layout.addWidget(QLabel("Total Trades:"), 0, 0)
        self.total_trades_label = QLabel("0")
        metrics_layout.addWidget(self.total_trades_label, 0, 1)
        
        # Winning trades
        metrics_layout.addWidget(QLabel("Winning Trades:"), 0, 2)
        self.winning_trades_label = QLabel("0")
        metrics_layout.addWidget(self.winning_trades_label, 0, 3)
        
        # Win rate
        metrics_layout.addWidget(QLabel("Win Rate:"), 1, 0)
        self.strategy_win_rate_label = QLabel("0%")
        metrics_layout.addWidget(self.strategy_win_rate_label, 1, 1)
        
        # Profit factor
        metrics_layout.addWidget(QLabel("Profit Factor:"), 1, 2)
        self.profit_factor_label = QLabel("0.00")
        metrics_layout.addWidget(self.profit_factor_label, 1, 3)
        
        # Average win
        metrics_layout.addWidget(QLabel("Avg Win:"), 2, 0)
        self.avg_win_label = QLabel("$0.00")
        metrics_layout.addWidget(self.avg_win_label, 2, 1)
        
        # Average loss
        metrics_layout.addWidget(QLabel("Avg Loss:"), 2, 2)
        self.avg_loss_label = QLabel("$0.00")
        metrics_layout.addWidget(self.avg_loss_label, 2, 3)
        
        # Total profit
        metrics_layout.addWidget(QLabel("Total Profit:"), 3, 0)
        self.total_strategy_profit_label = QLabel("$0.00")
        self.total_strategy_profit_label.setFont(QFont("Arial", 10, QFont.Bold))
        metrics_layout.addWidget(self.total_strategy_profit_label, 3, 1)
        
        # Max drawdown
        metrics_layout.addWidget(QLabel("Max Drawdown:"), 3, 2)
        self.max_drawdown_label = QLabel("0%")
        metrics_layout.addWidget(self.max_drawdown_label, 3, 3)
        
        layout.addWidget(metrics_group)
        
        # Performance chart placeholder
        chart_group = QGroupBox("Performance Chart")
        chart_layout = QVBoxLayout(chart_group)
        
        self.performance_chart_label = QLabel("Performance chart would be displayed here")
        self.performance_chart_label.setAlignment(Qt.AlignCenter)
        self.performance_chart_label.setStyleSheet("border: 1px solid gray; min-height: 150px;")
        chart_layout.addWidget(self.performance_chart_label)
        
        layout.addWidget(chart_group)
        
        layout.addStretch()
        return widget
    
    def create_signals_tab(self) -> QWidget:
        """Create strategy signals monitoring tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Current signal info
        signal_group = QGroupBox("Current Signal")
        signal_layout = QGridLayout(signal_group)
        
        signal_layout.addWidget(QLabel("Last Signal:"), 0, 0)
        self.last_signal_label = QLabel("NONE")
        self.last_signal_label.setFont(QFont("Arial", 12, QFont.Bold))
        signal_layout.addWidget(self.last_signal_label, 0, 1)
        
        signal_layout.addWidget(QLabel("Confidence:"), 0, 2)
        self.signal_confidence_label = QLabel("0%")
        signal_layout.addWidget(self.signal_confidence_label, 0, 3)
        
        signal_layout.addWidget(QLabel("Signal Time:"), 1, 0)
        self.signal_time_label = QLabel("Never")
        signal_layout.addWidget(self.signal_time_label, 1, 1)
        
        signal_layout.addWidget(QLabel("Symbol:"), 1, 2)
        self.signal_symbol_label = QLabel("N/A")
        signal_layout.addWidget(self.signal_symbol_label, 1, 3)
        
        # Signal strength indicator
        signal_layout.addWidget(QLabel("Signal Strength:"), 2, 0)
        self.signal_strength_bar = QProgressBar()
        self.signal_strength_bar.setRange(0, 100)
        self.signal_strength_bar.setValue(0)
        signal_layout.addWidget(self.signal_strength_bar, 2, 1, 1, 3)
        
        layout.addWidget(signal_group)
        
        # Recent signals table
        recent_signals_group = QGroupBox("Recent Signals")
        recent_layout = QVBoxLayout(recent_signals_group)
        
        self.signals_table = QTableWidget(0, 6)
        self.signals_table.setHorizontalHeaderLabels([
            "Time", "Symbol", "Signal", "Confidence", "Entry Price", "Action"
        ])
        self.signals_table.horizontalHeader().setStretchLastSection(True)
        self.signals_table.setAlternatingRowColors(True)
        self.signals_table.setMaximumHeight(200)
        
        recent_layout.addWidget(self.signals_table)
        layout.addWidget(recent_signals_group)
        
        layout.addStretch()
        return widget
    
    def load_available_strategies(self):
        """Load available strategies into combo box"""
        try:
            if self.strategy_manager:
                available_strategies = self.strategy_manager.get_available_strategies()
                
                self.strategy_combo.clear()
                self.strategy_combo.addItems(available_strategies)
                
                # Set current strategy
                current_strategy = self.strategy_manager.get_current_strategy_name()
                if current_strategy in available_strategies:
                    self.strategy_combo.setCurrentText(current_strategy)
                
                self.logger.info(f"Loaded {len(available_strategies)} strategies")
        except Exception as e:
            self.logger.error(f"Error loading strategies: {str(e)}")
    
    def on_strategy_selected(self, strategy_name: str):
        """Handle strategy selection change"""
        try:
            if not strategy_name:
                return
            
            self.current_strategy = strategy_name
            
            # Update strategy description
            self.update_strategy_description(strategy_name)
            
            # Update parameters for selected strategy
            self.update_strategy_parameters(strategy_name)
            
            # Load strategy performance
            self.load_strategy_performance(strategy_name)
            
            self.logger.info(f"Selected strategy: {strategy_name}")
            
        except Exception as e:
            self.logger.error(f"Error handling strategy selection: {str(e)}")
    
    def update_strategy_description(self, strategy_name: str):
        """Update strategy description text"""
        try:
            descriptions = {
                "scalping": """
                Scalping Strategy
                
                High-frequency trading strategy that focuses on capturing small price movements.
                Uses EMA crossovers, RSI levels, and Bollinger Bands for signal generation.
                
                Key Features:
                • Quick entry/exit (typically 5-30 minutes)
                • Tight stop losses (15-25 pips)
                • High win rate target (>65%)
                • Works best during high volatility sessions
                
                Best Markets: Major currency pairs during London/NY sessions
                """,
                
                "swing": """
                Swing Trading Strategy
                
                Medium-term strategy that captures larger price movements over days to weeks.
                Uses trend analysis, moving averages, and momentum indicators.
                
                Key Features:
                • Hold positions for days/weeks
                • Larger stop losses (50-100 pips)
                • Higher reward-to-risk ratio (>1.5:1)
                • Follows major trend directions
                
                Best Markets: All major pairs, works in trending markets
                """,
                
                "intraday": """
                Intraday Trading Strategy
                
                Day trading strategy that opens and closes positions within the same trading day.
                Combines technical analysis with market session patterns.
                
                Key Features:
                • All positions closed daily
                • Medium-term holds (1-8 hours)
                • Balanced risk-reward approach
                • Session-based trading logic
                
                Best Markets: Major and minor pairs during active sessions
                """
            }
            
            description = descriptions.get(strategy_name.lower(), 
                                         f"{strategy_name} Strategy\n\nNo description available.")
            
            self.strategy_description.setPlainText(description)
            
        except Exception as e:
            self.logger.error(f"Error updating strategy description: {str(e)}")
    
    def update_strategy_parameters(self, strategy_name: str):
        """Update strategy parameters UI"""
        try:
            # Clear existing parameters
            for i in reversed(range(self.parameters_layout.count())):
                child = self.parameters_layout.itemAt(i).widget()
                if child:
                    child.setParent(None)
            
            # Get default parameters for strategy
            default_params = self.get_default_parameters(strategy_name)
            
            # Create parameter controls
            self.parameter_controls = {}
            row = 0
            
            for param_name, param_info in default_params.items():
                param_type = param_info['type']
                default_value = param_info['default']
                param_range = param_info.get('range', (0, 100))
                description = param_info.get('description', param_name)
                
                # Parameter label
                label = QLabel(f"{description}:")
                self.parameters_layout.addWidget(label, row, 0)
                
                # Parameter control
                if param_type == 'int':
                    control = QSpinBox()
                    control.setRange(param_range[0], param_range[1])
                    control.setValue(default_value)
                elif param_type == 'float':
                    control = QDoubleSpinBox()
                    control.setRange(param_range[0], param_range[1])
                    control.setDecimals(2)
                    control.setValue(default_value)
                elif param_type == 'bool':
                    control = QCheckBox()
                    control.setChecked(default_value)
                else:  # string or other
                    control = QComboBox()
                    if 'options' in param_info:
                        control.addItems(param_info['options'])
                        control.setCurrentText(str(default_value))
                
                self.parameters_layout.addWidget(control, row, 1)
                self.parameter_controls[param_name] = control
                
                row += 1
            
        except Exception as e:
            self.logger.error(f"Error updating strategy parameters: {str(e)}")
    
    def get_default_parameters(self, strategy_name: str) -> Dict[str, Any]:
        """Get default parameters for a strategy"""
        try:
            # Strategy-specific parameters
            if strategy_name.lower() == "scalping":
                return {
                    'ema_fast_period': {
                        'type': 'int',
                        'default': 5,
                        'range': (3, 20),
                        'description': 'Fast EMA Period'
                    },
                    'ema_slow_period': {
                        'type': 'int',
                        'default': 13,
                        'range': (10, 50),
                        'description': 'Slow EMA Period'
                    },
                    'rsi_period': {
                        'type': 'int',
                        'default': 14,
                        'range': (5, 30),
                        'description': 'RSI Period'
                    },
                    'rsi_oversold': {
                        'type': 'int',
                        'default': 30,
                        'range': (20, 40),
                        'description': 'RSI Oversold Level'
                    },
                    'rsi_overbought': {
                        'type': 'int',
                        'default': 70,
                        'range': (60, 80),
                        'description': 'RSI Overbought Level'
                    },
                    'confidence_threshold': {
                        'type': 'float',
                        'default': 0.65,
                        'range': (0.5, 0.9),
                        'description': 'Confidence Threshold'
                    }
                }
            
            elif strategy_name.lower() == "swing":
                return {
                    'ma_short_period': {
                        'type': 'int',
                        'default': 20,
                        'range': (10, 50),
                        'description': 'Short MA Period'
                    },
                    'ma_long_period': {
                        'type': 'int',
                        'default': 50,
                        'range': (30, 100),
                        'description': 'Long MA Period'
                    },
                    'ma_signal_period': {
                        'type': 'int',
                        'default': 200,
                        'range': (100, 300),
                        'description': 'Signal MA Period'
                    },
                    'rsi_oversold': {
                        'type': 'int',
                        'default': 35,
                        'range': (25, 45),
                        'description': 'RSI Oversold Level'
                    },
                    'rsi_overbought': {
                        'type': 'int',
                        'default': 65,
                        'range': (55, 75),
                        'description': 'RSI Overbought Level'
                    },
                    'min_trend_strength': {
                        'type': 'float',
                        'default': 0.7,
                        'range': (0.5, 1.0),
                        'description': 'Min Trend Strength'
                    }
                }
            
            else:
                # Generic parameters
                return {
                    'period': {
                        'type': 'int',
                        'default': 14,
                        'range': (5, 50),
                        'description': 'Analysis Period'
                    },
                    'threshold': {
                        'type': 'float',
                        'default': 0.6,
                        'range': (0.1, 1.0),
                        'description': 'Signal Threshold'
                    }
                }
                
        except Exception as e:
            self.logger.error(f"Error getting default parameters: {str(e)}")
            return {}
    
    def get_current_parameters(self) -> Dict[str, Any]:
        """Get current parameter values from controls"""
        try:
            parameters = {}
            
            for param_name, control in self.parameter_controls.items():
                if isinstance(control, QSpinBox):
                    parameters[param_name] = control.value()
                elif isinstance(control, QDoubleSpinBox):
                    parameters[param_name] = control.value()
                elif isinstance(control, QCheckBox):
                    parameters[param_name] = control.isChecked()
                elif isinstance(control, QComboBox):
                    parameters[param_name] = control.currentText()
            
            return parameters
            
        except Exception as e:
            self.logger.error(f"Error getting current parameters: {str(e)}")
            return {}
    
    def apply_parameters(self):
        """Apply current parameter settings to strategy"""
        try:
            if not self.current_strategy:
                QMessageBox.warning(self, "Warning", "No strategy selected")
                return
            
            parameters = self.get_current_parameters()
            
            if parameters:
                # Store parameters
                self.strategy_parameters[self.current_strategy] = parameters
                
                # Emit signal
                self.strategy_configured.emit(self.current_strategy, parameters)
                
                QMessageBox.information(self, "Success", 
                                      f"Parameters applied to {self.current_strategy} strategy")
                
                self.logger.info(f"Applied parameters to {self.current_strategy}: {parameters}")
            
        except Exception as e:
            self.logger.error(f"Error applying parameters: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to apply parameters: {str(e)}")
    
    def reset_parameters(self):
        """Reset parameters to defaults"""
        try:
            if not self.current_strategy:
                return
            
            reply = QMessageBox.question(self, 'Confirm Reset', 
                                       'Reset all parameters to defaults?')
            if reply == QMessageBox.Yes:
                self.update_strategy_parameters(self.current_strategy)
                QMessageBox.information(self, "Reset Complete", 
                                      "Parameters reset to defaults")
                
        except Exception as e:
            self.logger.error(f"Error resetting parameters: {str(e)}")
    
    def switch_strategy(self):
        """Switch to selected strategy"""
        try:
            if not self.current_strategy:
                QMessageBox.warning(self, "Warning", "No strategy selected")
                return
            
            if self.strategy_manager:
                success = self.strategy_manager.switch_strategy(self.current_strategy)
                
                if success:
                    self.strategy_changed.emit(self.current_strategy)
                    QMessageBox.information(self, "Success", 
                                          f"Switched to {self.current_strategy} strategy")
                    self.logger.info(f"Switched to strategy: {self.current_strategy}")
                else:
                    QMessageBox.warning(self, "Error", 
                                      f"Failed to switch to {self.current_strategy} strategy")
            
        except Exception as e:
            self.logger.error(f"Error switching strategy: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to switch strategy: {str(e)}")
    
    def load_strategy_performance(self, strategy_name: str):
        """Load performance data for strategy"""
        try:
            # This would typically load from performance tracker
            # For now, we'll use placeholder data
            self.strategy_performance[strategy_name] = {
                'total_trades': 0,
                'winning_trades': 0,
                'win_rate': 0.0,
                'total_profit': 0.0,
                'profit_factor': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'max_drawdown': 0.0
            }
            
            self.update_performance_display()
            
        except Exception as e:
            self.logger.error(f"Error loading strategy performance: {str(e)}")
    
    def update_performance_display(self):
        """Update performance metrics display"""
        try:
            if not self.current_strategy or self.current_strategy not in self.strategy_performance:
                return
            
            perf = self.strategy_performance[self.current_strategy]
            
            # Update labels
            self.total_trades_label.setText(str(perf['total_trades']))
            self.winning_trades_label.setText(str(perf['winning_trades']))
            self.strategy_win_rate_label.setText(f"{perf['win_rate']:.1f}%")
            self.profit_factor_label.setText(f"{perf['profit_factor']:.2f}")
            self.avg_win_label.setText(f"${perf['avg_win']:.2f}")
            self.avg_loss_label.setText(f"${perf['avg_loss']:.2f}")
            self.max_drawdown_label.setText(f"{perf['max_drawdown']:.1f}%")
            
            # Color total profit based on positive/negative
            total_profit = perf['total_profit']
            if total_profit >= 0:
                self.total_strategy_profit_label.setStyleSheet("color: green;")
                self.total_strategy_profit_label.setText(f"+${total_profit:.2f}")
            else:
                self.total_strategy_profit_label.setStyleSheet("color: red;")
                self.total_strategy_profit_label.setText(f"${total_profit:.2f}")
                
        except Exception as e:
            self.logger.error(f"Error updating performance display: {str(e)}")
    
    def update_strategy_info(self):
        """Update strategy information periodically"""
        try:
            # Update strategy status
            if self.strategy_manager:
                current_strategy = self.strategy_manager.get_current_strategy_name()
                
                if current_strategy != self.current_strategy:
                    self.strategy_combo.setCurrentText(current_strategy)
                
                # Update status based on trading state
                # This would be connected to the main application's trading state
                
            # Update signal information
            self.update_signal_display()
            
        except Exception as e:
            self.logger.debug(f"Error updating strategy info: {str(e)}")
    
    def update_signal_display(self):
        """Update current signal display"""
        try:
            # This would be updated when actual signals are received
            # For now, we maintain the current display
            pass
            
        except Exception as e:
            self.logger.debug(f"Error updating signal display: {str(e)}")
    
    def update_signal_info(self, signal_data: Dict[str, Any]):
        """Update signal information from external source"""
        try:
            signal_type = signal_data.get('signal', 'NONE')
            confidence = signal_data.get('confidence', 0.0)
            symbol = signal_data.get('symbol', 'N/A')
            timestamp = signal_data.get('timestamp', 'Never')
            
            # Update signal labels
            self.last_signal_label.setText(signal_type)
            
            # Color signal based on type
            if signal_type == 'BUY':
                self.last_signal_label.setStyleSheet("color: green; font-weight: bold;")
            elif signal_type == 'SELL':
                self.last_signal_label.setStyleSheet("color: red; font-weight: bold;")
            else:
                self.last_signal_label.setStyleSheet("color: gray; font-weight: bold;")
            
            self.signal_confidence_label.setText(f"{confidence:.1%}")
            self.signal_symbol_label.setText(symbol)
            
            if isinstance(timestamp, str):
                self.signal_time_label.setText(timestamp)
            else:
                self.signal_time_label.setText(timestamp.strftime("%H:%M:%S"))
            
            # Update signal strength bar
            self.signal_strength_bar.setValue(int(confidence * 100))
            
            # Add to recent signals table
            self.add_signal_to_table(signal_data)
            
        except Exception as e:
            self.logger.error(f"Error updating signal info: {str(e)}")
    
    def add_signal_to_table(self, signal_data: Dict[str, Any]):
        """Add signal to recent signals table"""
        try:
            # Insert new row at top
            self.signals_table.insertRow(0)
            
            timestamp = signal_data.get('timestamp', 'N/A')
            if hasattr(timestamp, 'strftime'):
                time_str = timestamp.strftime("%H:%M:%S")
            else:
                time_str = str(timestamp)
            
            # Populate row
            self.signals_table.setItem(0, 0, QTableWidgetItem(time_str))
            self.signals_table.setItem(0, 1, QTableWidgetItem(signal_data.get('symbol', 'N/A')))
            self.signals_table.setItem(0, 2, QTableWidgetItem(signal_data.get('signal', 'NONE')))
            self.signals_table.setItem(0, 3, QTableWidgetItem(f"{signal_data.get('confidence', 0):.1%}"))
            self.signals_table.setItem(0, 4, QTableWidgetItem(f"{signal_data.get('entry_price', 0):.5f}"))
            self.signals_table.setItem(0, 5, QTableWidgetItem("Pending"))
            
            # Limit table size
            if self.signals_table.rowCount() > 50:
                self.signals_table.removeRow(50)
                
        except Exception as e:
            self.logger.error(f"Error adding signal to table: {str(e)}")
    
    def set_strategy_status(self, status: str):
        """Set strategy status display"""
        try:
            self.strategy_status = status
            self.status_label.setText(status)
            
            if status.lower() in ["running", "trading", "active"]:
                self.status_label.setStyleSheet("color: green; font-weight: bold;")
            elif status.lower() in ["stopped", "idle"]:
                self.status_label.setStyleSheet("color: red; font-weight: bold;")
            else:
                self.status_label.setStyleSheet("color: orange; font-weight: bold;")
                
        except Exception as e:
            self.logger.error(f"Error setting strategy status: {str(e)}")
    
    def update_strategy_performance_data(self, performance_data: Dict[str, Any]):
        """Update strategy performance with new data"""
        try:
            if self.current_strategy:
                self.strategy_performance[self.current_strategy] = performance_data
                self.update_performance_display()
                
                # Update main status labels
                self.win_rate_label.setText(f"Win Rate: {performance_data.get('win_rate', 0):.1f}%")
                
                profit = performance_data.get('total_profit', 0)
                if profit >= 0:
                    self.profit_label.setText(f"Profit: +${profit:.2f}")
                    self.profit_label.setStyleSheet("color: green;")
                else:
                    self.profit_label.setText(f"Profit: ${profit:.2f}")
                    self.profit_label.setStyleSheet("color: red;")
                    
        except Exception as e:
            self.logger.error(f"Error updating strategy performance data: {str(e)}")
    
    def get_strategy_summary(self) -> str:
        """Get text summary of current strategy configuration"""
        try:
            if not self.current_strategy:
                return "No strategy selected"
            
            parameters = self.get_current_parameters()
            performance = self.strategy_performance.get(self.current_strategy, {})
            
            summary_lines = [
                f"=== {self.current_strategy} Strategy Summary ===",
                "",
                f"Status: {self.strategy_status}",
                "",
                "Parameters:",
            ]
            
            for param_name, param_value in parameters.items():
                summary_lines.append(f"  {param_name}: {param_value}")
            
            summary_lines.extend([
                "",
                "Performance:",
                f"  Total Trades: {performance.get('total_trades', 0)}",
                f"  Win Rate: {performance.get('win_rate', 0):.1f}%",
                f"  Total Profit: ${performance.get('total_profit', 0):.2f}",
                f"  Profit Factor: {performance.get('profit_factor', 0):.2f}",
            ])
            
            return "\n".join(summary_lines)
            
        except Exception as e:
            return f"Error generating strategy summary: {str(e)}"

