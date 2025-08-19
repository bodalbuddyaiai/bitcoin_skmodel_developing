# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Bitcoin automated trading system with a React frontend and FastAPI backend that integrates with Bitget exchange API and multiple AI models (OpenAI GPT, Claude, Claude Opus) for market analysis and trading decisions.

## Commands

### Backend
```bash
# Install dependencies
cd backend
pip install -r requirements.txt

# Run development server
cd backend
uvicorn app.main:app --reload --port 8000

# Initialize database
python -c "from app.database.init_db import init_db; init_db()"
```

### Frontend
```bash
# Install dependencies
cd frontend
npm install

# Run development server
cd frontend
npm start

# Build production
cd frontend
npm run build

# Run tests
cd frontend
npm test
```

## Architecture

### Backend Architecture
The backend uses a service-oriented architecture with clear separation of concerns:

- **FastAPI Application** (`backend/app/main.py`): Main application entry point with WebSocket support for real-time updates
- **Service Layer** (`backend/app/services/`):
  - `ai_service.py`: Unified AI interface that switches between OpenAI and Claude models
  - `bitget_service.py`: Exchange API integration for market data and trade execution
  - `trading_assistant.py`: Core trading logic with scheduled analysis and position management
  - `openai_service.py` & `claude_service.py`: AI model-specific implementations
- **Database Layer** (`backend/app/database/`): SQLAlchemy models for trading history persistence
- **WebSocket Manager**: Real-time communication system for market updates, position changes, and analysis results

### Frontend Architecture
React-based SPA with Material-UI components:

- **WebSocket Integration** (`frontend/src/services/websocket.js`): Real-time event handling with typed event system
- **API Service** (`frontend/src/services/api.js`): REST API client for backend communication
- **Component Structure**:
  - `TradingControls`: Start/stop automation, manual trade execution
  - `MarketDataDisplay`: Real-time market data visualization
  - `TradingChart`: Price chart visualization
  - `AIModelSelector`: Switch between GPT, Claude, and Claude Opus models
  - `PositionInfoCard`: Current position display
  - `TradingHistory`: Historical trades display

## Key Features & Implementation Details

### AI Model Integration
The system supports multiple AI models through a unified interface:
- Models can be switched at runtime via the UI
- Each model analyzes market data and returns: action (LONG/SHORT/CLOSE_POSITION), position_size, leverage, expected_minutes, and reasoning
- Korean language comments indicate the system was developed for Korean users

### Trading Logic Flow
1. **Market Analysis**: Collects kline data, orderbook, and current positions
2. **AI Decision**: Selected AI model analyzes data and provides trading recommendation
3. **Trade Execution**: Executes trades via Bitget API with position sizing and leverage
4. **Scheduling**: Uses APScheduler to schedule next analysis based on AI's expected_minutes
5. **Position Monitoring**: Continuously monitors positions for liquidation or target achievement

### WebSocket Events
The system uses typed WebSocket events for real-time updates:
- `MARKET_UPDATE`: Real-time price updates
- `POSITION_UPDATE`: Position changes
- `LIQUIDATION_DETECTED`: Automatic liquidation detection
- `ANALYSIS_RESULT`: AI analysis results
- `TRADING_STATUS`: Trading system status
- `SCHEDULED_JOBS`: Upcoming scheduled analyses

### Position Management
- Automatic liquidation detection with 60-minute cooldown
- Manual position closing with automatic rescheduling
- Stop-loss and take-profit tracking
- Position entry/exit time management

## Environment Variables

The system expects these environment variables (typically in `.env` files):
- Bitget API credentials (API key, secret, passphrase)
- OpenAI API key
- Claude/Anthropic API key
- Database configuration

## Database Schema

Uses SQLAlchemy with a `TradingHistory` model to track:
- Trade timestamps, actions, and positions
- Entry/exit prices, PnL, and ROE
- AI reasoning for each trade
- Trade status tracking

## Testing Approach

- Frontend: React Testing Library with Jest (via `npm test`)
- Backend: Manual testing via API endpoints
- WebSocket testing: Browser developer tools for real-time event monitoring

## Important Considerations

1. **Exchange Integration**: All trading operations go through Bitget's futures API
2. **Position Size**: Fixed at 1 contract with configurable leverage (default 2x)
3. **Market**: Specifically configured for BTCUSDT futures trading
4. **Language**: Korean comments throughout indicate primary user base
5. **Real Money**: This system executes real trades - use with caution
6. **Scheduling**: Uses APScheduler for automated trading cycles based on AI predictions