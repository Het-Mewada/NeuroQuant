import asyncio
import json
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.models.database import init_db, AsyncSessionLocal, DecisionDB
from app.models.domain import (
    Order, OrderSide, OrderType, DecisionAction, InstrumentType
)
from app.data.live_feed import live_feed
from app.data.aggregator import CandleAggregator
from app.decision.arbiter import arbiter
from app.risk.engine import RiskEngineGate
from app.risk.formulas import calculate_kelly_position_size
from app.execution.paper_engine import PaperExecutionEngine
from app.execution.position_manager import PositionManager
from app.memory.counterfactual import CounterfactualEngine
from app.notifications.telegram import notifier
from app.api.routes import router as api_router
from app.api.websocket import telemetry_hub

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("neuroquant.main")

aggregator = CandleAggregator(timeframe_minutes=1)
background_tasks = set()


async def autonomous_trading_engine_loop():
    """
    Core autonomous orchestration loop.
    Consumes live market data, marks open positions to market,
    evaluates strategy signals, runs risk gates, and executes paper orders.
    """
    logger.info("Starting NeuroQuant Autonomous Trading Engine background loop...")
    await asyncio.sleep(2.0)  # Brief warm-up

    async for tick in live_feed.stream_ticks(live_interval_seconds=2.0):
        try:
            async with AsyncSessionLocal() as session:
                pos_manager = PositionManager(session)
                risk_gate = RiskEngineGate(session)
                exec_engine = PaperExecutionEngine(session)
                counterfactual = CounterfactualEngine(session)

                # 1. Update active positions Mark-To-Market
                mtm_updates = await pos_manager.update_mark_to_market(
                    instrument=tick.instrument,
                    current_ltp=tick.ltp,
                    bid=tick.bid,
                    ask=tick.ask
                )
                if mtm_updates:
                    await telemetry_hub.broadcast("PositionsMarkedToMarket", {"updates": mtm_updates})

                # Also update counterfactual shadow trackers
                await counterfactual.update_market_price(tick.instrument, tick.ltp)

                # 2. Feed tick into candle aggregator
                closed_candle = aggregator.process_tick(tick)

                # Broadcast live tick to dashboard
                await telemetry_hub.broadcast("TickReceived", {
                    "instrument": tick.instrument,
                    "ltp": tick.ltp,
                    "bid": tick.bid,
                    "ask": tick.ask,
                    "volume": tick.volume,
                    "timestamp": tick.timestamp.isoformat()
                })

                # 3. If a 1-minute candle closed, evaluate trading opportunities
                if closed_candle:
                    vwap = aggregator.get_session_vwap(tick.instrument)
                    sess_high = aggregator.session_highs.get(tick.instrument, tick.ltp)
                    sess_low = aggregator.session_lows.get(tick.instrument, tick.ltp)

                    # Simulate a 25-candle history from the current active tracking
                    history = [closed_candle] * 25  # In live mode, fetched from database

                    decision = arbiter.evaluate_opportunity(
                        instrument=tick.instrument,
                        candles=history,
                        vwap=vwap,
                        session_high=sess_high,
                        session_low=sess_low,
                        vix=live_feed.vix
                    )

                    # Persist decision to audit log
                    dec_db = DecisionDB(
                        id=decision.id,
                        instrument=decision.instrument,
                        action=decision.action.value,
                        raw_confidence=decision.raw_confidence,
                        calibrated_probability=decision.calibrated_probability,
                        expected_value_r=decision.expected_value_r,
                        regime=decision.regime,
                        features_json=json.dumps(decision.features),
                        veto_reason=decision.veto_reason,
                        rationale=decision.rationale
                    )
                    session.add(dec_db)
                    await session.commit()

                    await telemetry_hub.broadcast("DecisionEvaluated", {
                        "id": decision.id,
                        "instrument": decision.instrument,
                        "action": decision.action.value,
                        "regime": decision.regime,
                        "calibrated_prob": decision.calibrated_probability,
                        "expected_r": decision.expected_value_r,
                        "rationale": decision.rationale
                    })

                    # 4. If an entry signal was generated, run deterministic Risk Gate
                    if decision.action in (DecisionAction.ENTER_LONG, DecisionAction.ENTER_SHORT):
                        stop_loss = decision.features.get("stop_loss", tick.ltp - 20)
                        target = decision.features.get("target", tick.ltp + 40)
                        side = OrderSide.BUY if decision.action == DecisionAction.ENTER_LONG else OrderSide.SELL

                        # Find appropriate option contract (ATM Call or Put)
                        chain = live_feed.generate_option_chain(tick.instrument, num_strikes=2)
                        opt_type = InstrumentType.OPTION_CE if side == OrderSide.BUY else InstrumentType.OPTION_PE
                        target_contract = next((c for c in chain if c.option_type == opt_type), chain[0])

                        # Sizing: Quarter-Kelly
                        lot_size = target_contract.lot_size
                        qty, alloc_cap, size_notes = calculate_kelly_position_size(
                            available_capital=500000.0,
                            entry_price=target_contract.ask,
                            stop_loss_price=max(0.05, target_contract.ask * 0.75),
                            calibrated_win_prob=decision.calibrated_probability,
                            target_price=target_contract.ask * 1.5,
                            lot_size=lot_size
                        )

                        if qty > 0:
                            order = Order(
                                instrument=target_contract.symbol,
                                side=OrderSide.BUY,  # Long option buyer
                                order_type=OrderType.MARKET,
                                price=target_contract.ask,
                                quantity=qty,
                                decision_id=decision.id
                            )

                            # Risk Gate Evaluation
                            approved, risk_reason = await risk_gate.evaluate_order_proposal(
                                order=order,
                                stop_loss=target_contract.ask * 0.75,
                                target=target_contract.ask * 1.5
                            )

                            if approved:
                                # Execute simulated fill
                                pos_db, order_db = await exec_engine.execute_entry_order(
                                    order=order,
                                    bid=target_contract.bid,
                                    ask=target_contract.ask,
                                    stop_loss=target_contract.ask * 0.75,
                                    take_profit=target_contract.ask * 1.5,
                                    underlying=tick.instrument,
                                    depth_vol=1000
                                )
                                logger.info(f"EXECUTED ORDER: {order.instrument} Qty={qty} Price={order_db.price}")
                                await notifier.notify_trade_opened(
                                    instrument=order.instrument,
                                    side=order.side.value,
                                    quantity=qty,
                                    entry_price=order_db.price,
                                    stop_loss=target_contract.ask * 0.75,
                                    target=target_contract.ask * 1.5,
                                    rationale=decision.rationale
                                )
                                await telemetry_hub.broadcast("PositionOpened", {
                                    "position_id": pos_db.id,
                                    "instrument": pos_db.instrument,
                                    "quantity": pos_db.quantity,
                                    "entry_price": pos_db.entry_price,
                                    "stop_loss": pos_db.stop_loss,
                                    "take_profit": pos_db.take_profit
                                })
                            else:
                                # Vetoed by Risk Gate -> Register to counterfactual tracking
                                logger.info(f"RISK VETO: {risk_reason}")
                                counterfactual.register_rejected_trade(
                                    decision_id=decision.id,
                                    instrument=target_contract.symbol,
                                    shadow_entry_price=target_contract.ask,
                                    stop_loss=target_contract.ask * 0.75,
                                    target=target_contract.ask * 1.5,
                                    side="BUY"
                                )
        except Exception as e:
            logger.error(f"Error in autonomous engine loop: {e}", exc_info=True)
            await asyncio.sleep(1.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Database
    logger.info("Initializing NeuroQuant Database...")
    await init_db()

    # Launch autonomous background runner task
    task = asyncio.create_task(autonomous_trading_engine_loop())
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)

    yield

    # Shutdown
    logger.info("Shutting down NeuroQuant Engine...")
    live_feed.stop()
    for t in background_tasks:
        t.cancel()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

# Enable CORS for dashboard UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.websocket("/ws/telemetry")
async def websocket_telemetry_endpoint(websocket: WebSocket):
    await telemetry_hub.connect(websocket)
    try:
        while True:
            # Keepalive receiver
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        telemetry_hub.disconnect(websocket)
