# Project NeuroQuant: Autonomous Quantitative Trading Engine

> **Notice:** Operates strictly in a **simulated paper-trading environment** driven by genuine real-time / synthetic market data. Built for Indian derivatives (NSE Nifty 50 & Bank Nifty index options).

---

## 1. System Overview

NeuroQuant is an autonomous, self-learning paper-trading platform engineered for Indian markets (NSE). It solves the fundamental flaw of retail trading bots (non-stationarity, catastrophic forgetting, and false confidence) through:
- **Market Lifecycle State Machine:** Automatically transitions across IST market phases (09:00 Pre-Market, 09:15-09:20 Opening Volatility filter, 09:20-15:00 Active Trading, 15:00-15:15 Wind Down, 15:15-15:30 EOD Auto Square-Off).
- **Deterministic Risk Gate:** Vetoes ML proposals if daily loss >= 2.0% (hard circuit breaker), concurrent positions >= 3, or reward-to-risk < 1.5:1.
- **Double-Entry Ledger:** Reconciles available cash, reserved margin, and realized P&L with mathematical invariance.
- **Realistic Execution Simulation:** Models bid-ask spread penalties, size impact, and statutory Indian F&O fees (STT, exchange turnover, GST, SEBI charges, stamp duty).
- **Options Analytics Engine:** High-performance Black-76 Greeks calculation (Delta, Gamma, Theta, Vega) and implied volatility solver.
- **Epistemic Learning & Memory:** Decomposes trades via post-mortems (distinguishing lucky noise wins from genuine skill) and tracks counterfactual shadow outcomes for rejected setups.

---

## 2. Quick Start Guide

### Prerequisites
- Python 3.12+ (or `uv`)
- Node.js 20+

### A. Run Backend Engine
```bash
cd neuroquant/backend
# Run the test suite (100% passing)
uv run pytest -v

# Start the autonomous trading engine & telemetry server
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
The backend initializes the SQLite/PostgreSQL database, launches the autonomous market data ingestion loop, marks open positions to market, and opens the streaming WebSocket telemetry at `ws://localhost:8000/ws/telemetry`.

### B. Run Interactive Dashboard
```bash
cd neuroquant/frontend
npm run dev
```
Open **`http://localhost:5173`** in your browser. The dashboard connects via live WebSocket to display:
- Live Nifty 50 & Bank Nifty market tickers.
- Active open positions with real-time MTM P&L and manual liquidation buttons.
- Streaming decision intelligence logs with win probability calibration and expected value $R$.
- Live Nifty options chain with Greeks.
- Learning & memory center with post-mortem skill vs. luck attribution.
- Virtual capital deposit/withdrawal controls and immutable double-entry ledger history.

---

## 3. Architecture & Project Layout

```
neuroquant/
├── backend/
│   ├── app/
│   │   ├── core/           # Configuration & market lifecycle state machine
│   │   ├── models/         # Pydantic domain models & SQLAlchemy database schemas
│   │   ├── data/           # High-fidelity mock feed, Upstox API V3 client, Black-76 Greeks solver
│   │   ├── risk/           # Deterministic Risk Gate, Kelly position sizing, statutory fees
│   │   ├── execution/      # Paper execution engine, position manager, double-entry ledger
│   │   ├── decision/       # Decision arbiter, regime detector, probability calibrator
│   │   ├── memory/         # Vector memory store, post-mortem analyzer, counterfactual tracker
│   │   ├── notifications/  # Telegram notification gateway with rate limiting
│   │   ├── api/            # FastAPI REST routes & WebSocket telemetry hub
│   │   └── main.py         # Autonomous orchestration loop & server entrypoint
│   └── tests/              # Comprehensive unit and integration test suite
└── frontend/               # React 19 + TypeScript + Vite + Tailwind CSS Financial Dashboard
```
