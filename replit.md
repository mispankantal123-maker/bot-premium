# TradeMaestro Trading Bot

## Overview

TradeMaestro is a professional automated trading bot designed for MetaTrader5 integration with both GUI and CLI interfaces. The application provides a comprehensive trading platform with multiple strategy support, real-time market data processing, and advanced performance tracking. Built with cross-platform compatibility, the bot features modular architecture separating trading logic, user interface, and external integrations.

## Current Status (January 2025)

**✅ COMPLETED MAJOR REBUILD:**
- Complete modular architecture implemented from scratch
- Mock trading environment for demo/testing without MT5 dependency
- CLI interface working and tested successfully
- Multi-strategy framework with scalping and swing trading implementations
- Comprehensive logging and performance tracking systems
- Windows-compatible file structure and path handling

**🎯 WORKING FEATURES:**
- CLI demo mode with simulated trading environment
- Mock MT5 connector with realistic price simulation
- Performance tracking with trade history and metrics
- Strategy management system supporting multiple algorithms
- Robust error handling and logging throughout

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Frontend Architecture
- **GUI Framework**: PySide6 (Qt6 for Python) providing native Windows look and feel (GUI components ready but require OpenGL libraries)
- **CLI Interface**: Fully functional command-line interface for headless environments and testing
- **Main Window Structure**: Tabbed interface with dedicated panels for trading control, strategy configuration, and settings management
- **Real-time Updates**: Signal-slot pattern for thread-safe GUI updates from background trading operations
- **Theme Support**: Dark/light theme switching with Windows system integration
- **Demo Mode**: Mock trading environment allowing testing without MetaTrader5 installation

### Backend Architecture
- **Core Application**: Object-oriented design with centralized application controller (TradeMaestroApp)
- **Threading Model**: Background threads for trading operations to maintain GUI responsiveness
- **Configuration Management**: Centralized config system using environment variables and JSON settings
- **Strategy Pattern**: Abstract base strategy class with concrete implementations for different trading approaches (scalping, swing trading)

### Data Management
- **Market Data**: Real-time and historical data fetching from MetaTrader5 with intelligent caching
- **Performance Tracking**: Comprehensive trade history and metrics calculation with persistent storage
- **File Storage**: Uses pathlib for Windows-compatible path handling, organized data directories for logs, cache, and history

### Trading Engine
- **MT5 Integration**: Robust connector with connection monitoring and automatic reconnection
- **Mock Trading Environment**: Simulated trading for development and testing without real MT5 connection
- **Order Management**: Complete order lifecycle management with status tracking and risk controls
- **Strategy Manager**: Plugin-like architecture for loading and switching between different trading strategies
- **Risk Management**: Built-in position sizing, stop-loss, and take-profit management
- **Real-time Price Simulation**: Mock connector provides realistic price movements and profit/loss calculations

### Error Handling and Logging
- **Comprehensive Logging**: Multi-level logging system with colored console output and file rotation
- **Windows Compatibility**: ANSI color support enabling and proper error handling for Windows-specific issues
- **Thread Safety**: Concurrent logging from multiple threads with proper synchronization

## External Dependencies

### Trading Platform
- **MetaTrader5**: Primary trading platform integration via official Python API
- **Market Data**: Real-time price feeds and historical data through MT5 connection

### Python Libraries
- **PySide6**: Modern Qt6-based GUI framework for cross-platform interface
- **pandas/numpy**: Data manipulation and numerical analysis for market data processing
- **colorlog**: Enhanced logging with color support for better debugging experience

### Development Tools
- **pathlib**: Windows-compatible path handling throughout the application
- **threading**: Background operations for non-blocking GUI performance
- **pickle/json**: Data serialization for settings and performance data persistence

### Configuration Management
- **python-dotenv**: Environment variable management for sensitive credentials
- **Environment Variables**: Secure storage of MT5 login credentials and API keys
- **Demo Mode**: Configurable demo/production mode switching via environment variables

### Data Storage
- **Local Files**: JSON configuration files, CSV trade history, and pickle cache files
- **Directory Structure**: Organized data storage with separate folders for logs, cache, and historical data
- **Cache Management**: Intelligent caching system for market data to reduce API calls

## Recent Changes (January 2025)

### Completed Rebuild
- **Complete Architecture Overhaul**: Rebuilt entire codebase with modular Python architecture
- **CLI Interface Added**: Functional command-line interface for environments without GUI support
- **Mock Trading Environment**: Created comprehensive mock MT5 connector for demo and testing
- **Cross-platform Compatibility**: Removed Windows-specific dependencies while maintaining compatibility
- **Strategy Framework**: Implemented base strategy system with scalping and swing trading algorithms

### Demo Mode Features
- **Realistic Price Simulation**: Mock connector simulates real market conditions with price movements
- **Account Management**: Demo accounts with balance, equity, and profit tracking
- **Performance Metrics**: Complete trade history and performance analysis in demo mode
- **Strategy Execution**: Full strategy testing without requiring actual MT5 installation

### Technical Improvements
- **Error Handling**: Comprehensive error handling throughout all modules
- **Logging System**: Advanced logging with file rotation and colored console output
- **Thread Safety**: Thread-safe operations for background trading and GUI updates
- **Configuration Management**: Centralized configuration with environment variable support