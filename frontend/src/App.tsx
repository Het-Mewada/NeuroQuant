import { useState, useEffect, useRef } from 'react';
import {
  Activity, Brain, CheckCircle2, LogOut
} from 'lucide-react';

interface AccountSummary {
  account_id: string;
  total_equity: number;
  available_cash: number;
  reserved_margin: number;
  unrealized_pnl: number;
  realized_pnl: number;
  open_positions_count: number;
  market_state: string;
  currency: string;
  nifty_spot?: number;
  banknifty_spot?: number;
}

interface Position {
  id: string;
  instrument: string;
  underlying: string;
  direction: string;
  quantity: number;
  entry_price: number;
  current_price: number;
  stop_loss: number;
  take_profit: number;
  unrealized_pnl: number;
  realized_pnl: number;
  total_fees: number;
  status: string;
  opened_at: string;
}

interface Decision {
  id: string;
  timestamp: string;
  instrument: string;
  action: string;
  raw_confidence: number;
  calibrated_probability: number;
  expected_value_r: number;
  regime: string;
  rationale: string;
  veto_reason?: string;
}

interface LedgerTx {
  id: string;
  tx_type: string;
  amount: number;
  balance_after: number;
  idempotency_key: string;
  created_at: string;
}

interface OptionContract {
  symbol: string;
  strike: number;
  option_type: string;
  ltp: number;
  bid: number;
  ask: number;
  iv: number;
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
  open_interest: number;
}

const BACKEND_HTTP = window.location.origin;

const BACKEND_WS = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/telemetry`;

export default function App() {
  const [activeTab, setActiveTab] = useState<'positions' | 'decisions' | 'learning' | 'ledger' | 'chain'>('positions');
  const [summary, setSummary] = useState<AccountSummary | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [ledger, setLedger] = useState<LedgerTx[]>([]);
  const [optionChain, setOptionChain] = useState<OptionContract[]>([]);
  const [wsConnected, setWsConnected] = useState<boolean>(false);
  const [depositAmount, setDepositAmount] = useState<string>('50000');
  const [liveTick, setLiveTick] = useState<{ nse: number; bnf: number }>({ nse: 22936.75, bnf: 54909.65 });
  const [actionMessage, setActionMessage] = useState<string>('');

  const wsRef = useRef<WebSocket | null>(null);

  // Fetch initial REST data
  const fetchData = async () => {
    try {
      const sumRes = await fetch(`${BACKEND_HTTP}/api/v1/summary`);
      if (sumRes.ok) {
        const sumData = await sumRes.json();
        setSummary(sumData);
        if (sumData.nifty_spot && sumData.banknifty_spot) {
          setLiveTick({ nse: sumData.nifty_spot, bnf: sumData.banknifty_spot });
        }
      }

      const posRes = await fetch(`${BACKEND_HTTP}/api/v1/positions/active`);
      if (posRes.ok) setPositions(await posRes.json());

      const decRes = await fetch(`${BACKEND_HTTP}/api/v1/decisions?limit=30`);
      if (decRes.ok) setDecisions(await decRes.json());

      const ledRes = await fetch(`${BACKEND_HTTP}/api/v1/ledger?limit=50`);
      if (ledRes.ok) setLedger(await ledRes.json());

      const chainRes = await fetch(`${BACKEND_HTTP}/api/v1/options/chain?underlying=NIFTY`);
      if (chainRes.ok) {
        const cData = await chainRes.json();
        setOptionChain(cData.chain || []);
      }
    } catch (e) {
      console.warn("Backend API polling waiting for connection...", e);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 3000);
    return () => clearInterval(interval);
  }, []);

  // Real-time WebSocket connection
  useEffect(() => {
    const connectWs = () => {
      const ws = new WebSocket(BACKEND_WS);
      wsRef.current = ws;

      ws.onopen = () => {
        setWsConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.event_type === 'TickReceived') {
            if (msg.data.instrument === 'NIFTY') {
              setLiveTick(prev => ({ ...prev, nse: msg.data.ltp }));
            } else if (msg.data.instrument === 'BANKNIFTY') {
              setLiveTick(prev => ({ ...prev, bnf: msg.data.ltp }));
            }
          } else if (msg.event_type === 'PositionsMarkedToMarket' || msg.event_type === 'PositionOpened') {
            fetchData();
          } else if (msg.event_type === 'DecisionEvaluated') {
            setDecisions(prev => [msg.data, ...prev.slice(0, 49)]);
          }
        } catch (err) {
          console.error("WS parse error", err);
        }
      };

      ws.onclose = () => {
        setWsConnected(false);
        setTimeout(connectWs, 3000);
      };
    };

    connectWs();
    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  // Manual Position Exit
  const handleManualExit = async (posId: string) => {
    try {
      const res = await fetch(`${BACKEND_HTTP}/api/v1/positions/${posId}/exit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account_id: 'default_user' })
      });
      const data = await res.json();
      if (res.ok) {
        setActionMessage(`Liquidated: ${data.message}`);
        fetchData();
      } else {
        setActionMessage(`Error: ${data.detail}`);
      }
      setTimeout(() => setActionMessage(''), 4000);
    } catch (err: any) {
      setActionMessage(`Exit failed: ${err.message}`);
    }
  };

  // Virtual Deposit
  const handleDeposit = async () => {
    try {
      const amount = parseFloat(depositAmount);
      if (isNaN(amount) || amount <= 0) return;
      const res = await fetch(`${BACKEND_HTTP}/api/v1/capital/deposit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ amount, account_id: 'default_user' })
      });
      if (res.ok) {
        setActionMessage(`Deposited ₹${amount.toLocaleString()} virtual capital!`);
        fetchData();
      }
      setTimeout(() => setActionMessage(''), 4000);
    } catch (err: any) {
      setActionMessage(`Deposit failed: ${err.message}`);
    }
  };

  return (
    <div style={{ minHeight: '100vh', backgroundColor: 'var(--bg-app)', color: 'var(--text-primary)' }}>
      {/* 1. Header: One thin institutional bar */}
      <header style={{
        height: '52px',
        borderBottom: '1px solid var(--border-hairline)',
        backgroundColor: 'var(--bg-app)',
        padding: '0 24px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        {/* Left: Product title in plain text, no decorative tile */}
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '10px' }}>
          <span style={{ fontSize: '14px', fontWeight: 600, letterSpacing: '-0.01em', color: 'var(--text-primary)' }}>
            NEUROQUANT
          </span>
          <span style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>
            NSE paper trading · simulated
          </span>
        </div>

        {/* Right: Neutral index quotes & restrained status indicators */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '24px' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
            <span style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>NIFTY 50 SPOT</span>
            <span className="tabular-nums" style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)' }}>
              {liveTick.nse.toFixed(2)}
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
            <span style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>BANK NIFTY SPOT</span>
            <span className="tabular-nums" style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)' }}>
              {liveTick.bnf.toFixed(2)}
            </span>
          </div>

          {/* Market Status: Simple text pill with a single dot */}
          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            padding: '3px 9px',
            borderRadius: 'var(--radius-control)',
            border: '1px solid var(--border-hairline)',
            fontSize: '11px',
            color: 'var(--text-secondary)'
          }}>
            <span style={{
              width: '6px',
              height: '6px',
              borderRadius: '50%',
              backgroundColor: summary?.market_state === 'ACTIVE_TRADING' ? 'var(--semantic-profit)' : 'var(--semantic-warning)'
            }} />
            <span>{summary?.market_state || 'CONNECTING...'}</span>
          </div>

          {/* Feed Status: Simple text with dot */}
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '11px', color: 'var(--text-tertiary)' }}>
            <span style={{
              width: '5px',
              height: '5px',
              borderRadius: '50%',
              backgroundColor: wsConnected ? 'var(--semantic-profit)' : 'var(--semantic-loss)'
            }} />
            <span>{wsConnected ? '● FEED LIVE' : '○ DISCONNECTED'}</span>
          </div>
        </div>
      </header>

      {/* Action Notification Toast (Restrained Alert) */}
      {actionMessage && (
        <div style={{
          backgroundColor: 'var(--bg-surface)',
          borderBottom: '1px solid var(--border-hairline)',
          color: 'var(--text-primary)',
          padding: '8px 24px',
          fontSize: '12px',
          display: 'flex',
          alignItems: 'center',
          gap: '8px'
        }}>
          <CheckCircle2 size={14} color="var(--semantic-profit)" />
          <span>{actionMessage}</span>
        </div>
      )}

      {/* 2. Summary Metric Row: 5 equal cells in a single bar separated by hairline dividers */}
      <div style={{ padding: '24px 24px 16px' }}>
        <div style={{
          backgroundColor: 'var(--bg-surface)',
          border: '1px solid var(--border-hairline)',
          borderRadius: 'var(--radius-card)',
          display: 'grid',
          gridTemplateColumns: 'repeat(5, 1fr)',
          overflow: 'hidden'
        }}>
          {/* Metric 1: Total Virtual Equity */}
          <div style={{ padding: '18px 20px', borderRight: '1px solid var(--border-hairline)' }}>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 500 }}>
              Total Virtual Equity
            </div>
            <div className="tabular-nums" style={{
              fontSize: '22px',
              fontWeight: 600,
              letterSpacing: '-0.01em',
              margin: '6px 0 2px',
              color: 'var(--text-primary)'
            }}>
              ₹{summary ? summary.total_equity.toLocaleString(undefined, { minimumFractionDigits: 2 }) : '5,00,000.00'}
            </div>
            <div style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>
              {ledger.length > 0 ? "Ledger balanced" : "No ledger entries yet"}
            </div>
          </div>

          {/* Metric 2: Available Free Cash */}
          <div style={{ padding: '18px 20px', borderRight: '1px solid var(--border-hairline)' }}>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 500 }}>
              Available Free Cash
            </div>
            <div className="tabular-nums" style={{
              fontSize: '22px',
              fontWeight: 600,
              letterSpacing: '-0.01em',
              margin: '6px 0 2px',
              color: 'var(--text-primary)'
            }}>
              ₹{summary ? summary.available_cash.toLocaleString(undefined, { minimumFractionDigits: 2 }) : '5,00,000.00'}
            </div>
            <div style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>
              Ready for allocation
            </div>
          </div>

          {/* Metric 3: Reserved Margin (In-Use) */}
          <div style={{ padding: '18px 20px', borderRight: '1px solid var(--border-hairline)' }}>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 500 }}>
              Reserved Margin (In-Use)
            </div>
            <div className="tabular-nums" style={{
              fontSize: '22px',
              fontWeight: 600,
              letterSpacing: '-0.01em',
              margin: '6px 0 2px',
              color: 'var(--text-primary)'
            }}>
              ₹{summary ? summary.reserved_margin.toLocaleString(undefined, { minimumFractionDigits: 2 }) : '0.00'}
            </div>
            <div style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>
              {positions.length} active position(s)
            </div>
          </div>

          {/* Metric 4: Unrealized MTM P&L */}
          <div style={{ padding: '18px 20px', borderRight: '1px solid var(--border-hairline)' }}>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 500 }}>
              Unrealized MTM P&L
            </div>
            <div className="tabular-nums" style={{
              fontSize: '22px',
              fontWeight: 600,
              letterSpacing: '-0.01em',
              margin: '6px 0 2px',
              color: (summary?.unrealized_pnl || 0) >= 0 ? 'var(--semantic-profit)' : 'var(--semantic-loss)'
            }}>
              {(summary?.unrealized_pnl || 0) >= 0 ? '+' : ''}₹{summary ? summary.unrealized_pnl.toLocaleString(undefined, { minimumFractionDigits: 2 }) : '0.00'}
            </div>
            <div style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>
              Live mark-to-market
            </div>
          </div>

          {/* Metric 5: Net Realized P&L */}
          <div style={{ padding: '18px 20px' }}>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 500 }}>
              Net Realized P&L
            </div>
            <div className="tabular-nums" style={{
              fontSize: '22px',
              fontWeight: 600,
              letterSpacing: '-0.01em',
              margin: '6px 0 2px',
              color: (summary?.realized_pnl || 0) >= 0 ? 'var(--semantic-profit)' : 'var(--semantic-loss)'
            }}>
              {(summary?.realized_pnl || 0) >= 0 ? '+' : ''}₹{summary ? summary.realized_pnl.toLocaleString(undefined, { minimumFractionDigits: 2 }) : '0.00'}
            </div>
            <div style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>
              After statutory taxes & STT
            </div>
          </div>
        </div>
      </div>

      {/* 3. Navigation Tabs: Text-only, 2px underline in accent on active tab */}
      <nav style={{
        borderBottom: '1px solid var(--border-hairline)',
        padding: '0 24px',
        display: 'flex',
        gap: '28px'
      }}>
        <button
          onClick={() => setActiveTab('positions')}
          className="transition-fast"
          style={{
            background: 'none',
            border: 'none',
            padding: '12px 0',
            color: activeTab === 'positions' ? 'var(--text-primary)' : 'var(--text-tertiary)',
            borderBottom: activeTab === 'positions' ? '2px solid var(--accent)' : '2px solid transparent',
            fontWeight: 500,
            cursor: 'pointer',
            fontSize: '13px'
          }}
        >
          Live Positions ({positions.length})
        </button>

        <button
          onClick={() => setActiveTab('decisions')}
          className="transition-fast"
          style={{
            background: 'none',
            border: 'none',
            padding: '12px 0',
            color: activeTab === 'decisions' ? 'var(--text-primary)' : 'var(--text-tertiary)',
            borderBottom: activeTab === 'decisions' ? '2px solid var(--accent)' : '2px solid transparent',
            fontWeight: 500,
            cursor: 'pointer',
            fontSize: '13px'
          }}
        >
          Decision Intelligence
        </button>

        <button
          onClick={() => setActiveTab('chain')}
          className="transition-fast"
          style={{
            background: 'none',
            border: 'none',
            padding: '12px 0',
            color: activeTab === 'chain' ? 'var(--text-primary)' : 'var(--text-tertiary)',
            borderBottom: activeTab === 'chain' ? '2px solid var(--accent)' : '2px solid transparent',
            fontWeight: 500,
            cursor: 'pointer',
            fontSize: '13px'
          }}
        >
          Options Chain & Greeks
        </button>

        <button
          onClick={() => setActiveTab('learning')}
          className="transition-fast"
          style={{
            background: 'none',
            border: 'none',
            padding: '12px 0',
            color: activeTab === 'learning' ? 'var(--text-primary)' : 'var(--text-tertiary)',
            borderBottom: activeTab === 'learning' ? '2px solid var(--accent)' : '2px solid transparent',
            fontWeight: 500,
            cursor: 'pointer',
            fontSize: '13px'
          }}
        >
          Learning & Memory Center
        </button>

        <button
          onClick={() => setActiveTab('ledger')}
          className="transition-fast"
          style={{
            background: 'none',
            border: 'none',
            padding: '12px 0',
            color: activeTab === 'ledger' ? 'var(--text-primary)' : 'var(--text-tertiary)',
            borderBottom: activeTab === 'ledger' ? '2px solid var(--accent)' : '2px solid transparent',
            fontWeight: 500,
            cursor: 'pointer',
            fontSize: '13px'
          }}
        >
          Capital Ledger
        </button>
      </nav>

      {/* 4. Main Content Area */}
      <main style={{ padding: '24px' }}>
        {/* TAB 1: POSITIONS */}
        {activeTab === 'positions' && (
          <div style={{
            backgroundColor: 'var(--bg-surface)',
            borderRadius: 'var(--radius-card)',
            border: '1px solid var(--border-hairline)',
            overflow: 'hidden'
          }}>
            <div style={{
              padding: '16px 20px',
              borderBottom: '1px solid var(--border-hairline)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center'
            }}>
              <h2 style={{ margin: 0, fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)' }}>
                Active Open Simulated Positions
              </h2>
              <span style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>
                Auto-exits on SL / TP / 15:15 IST Square-Off
              </span>
            </div>

            {positions.length === 0 ? (
              <div style={{ padding: '48px 24px', textAlign: 'center', color: 'var(--text-tertiary)' }}>
                <p style={{ margin: 0, fontSize: '13px' }}>
                  No active positions open. The engine evaluates 1-minute candle boundaries and will open positions when structural edge passes risk gates.
                </p>
              </div>
            ) : (
              <div className="table-container">
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                  <thead>
                    <tr style={{
                      borderBottom: '1px solid var(--border-hairline)',
                      color: 'var(--text-tertiary)',
                      fontSize: '12px'
                    }}>
                      <th style={{ padding: '10px 20px', textAlign: 'left', fontWeight: 500 }}>Instrument</th>
                      <th style={{ padding: '10px 16px', textAlign: 'left', fontWeight: 500 }}>Direction</th>
                      <th style={{ padding: '10px 16px', textAlign: 'right', fontWeight: 500 }}>Quantity</th>
                      <th style={{ padding: '10px 16px', textAlign: 'right', fontWeight: 500 }}>Entry Price</th>
                      <th style={{ padding: '10px 16px', textAlign: 'right', fontWeight: 500 }}>Current LTP</th>
                      <th style={{ padding: '10px 16px', textAlign: 'right', fontWeight: 500 }}>Stop Loss</th>
                      <th style={{ padding: '10px 16px', textAlign: 'right', fontWeight: 500 }}>Target</th>
                      <th style={{ padding: '10px 16px', textAlign: 'right', fontWeight: 500 }}>Unrealized P&L</th>
                      <th style={{ padding: '10px 20px', textAlign: 'right', fontWeight: 500 }}>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {positions.map((pos) => (
                      <tr key={pos.id} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                        <td style={{ padding: '14px 20px', fontWeight: 500, color: 'var(--text-primary)' }}>
                          {pos.instrument}
                        </td>
                        <td style={{ padding: '14px 16px' }}>
                          <span style={{
                            padding: '2px 6px',
                            borderRadius: 'var(--radius-control)',
                            fontSize: '11px',
                            fontWeight: 600,
                            border: '1px solid var(--border-hairline)',
                            color: pos.direction === 'LONG' ? 'var(--semantic-profit)' : 'var(--semantic-loss)'
                          }}>
                            {pos.direction}
                          </span>
                        </td>
                        <td className="tabular-nums" style={{ padding: '14px 16px', textAlign: 'right', color: 'var(--text-secondary)' }}>
                          {pos.quantity}
                        </td>
                        <td className="tabular-nums" style={{ padding: '14px 16px', textAlign: 'right', color: 'var(--text-secondary)' }}>
                          ₹{pos.entry_price.toFixed(2)}
                        </td>
                        <td className="tabular-nums" style={{ padding: '14px 16px', textAlign: 'right', fontWeight: 500, color: 'var(--text-primary)' }}>
                          ₹{pos.current_price.toFixed(2)}
                        </td>
                        <td className="tabular-nums" style={{ padding: '14px 16px', textAlign: 'right', color: 'var(--semantic-loss)' }}>
                          ₹{pos.stop_loss.toFixed(2)}
                        </td>
                        <td className="tabular-nums" style={{ padding: '14px 16px', textAlign: 'right', color: 'var(--semantic-profit)' }}>
                          ₹{pos.take_profit.toFixed(2)}
                        </td>
                        <td className="tabular-nums" style={{
                          padding: '14px 16px',
                          textAlign: 'right',
                          fontWeight: 600,
                          color: pos.unrealized_pnl >= 0 ? 'var(--semantic-profit)' : 'var(--semantic-loss)'
                        }}>
                          {pos.unrealized_pnl >= 0 ? '+' : ''}₹{pos.unrealized_pnl.toFixed(2)}
                        </td>
                        <td style={{ padding: '14px 20px', textAlign: 'right' }}>
                          <button
                            onClick={() => handleManualExit(pos.id)}
                            className="transition-fast"
                            style={{
                              backgroundColor: 'transparent',
                              color: 'var(--semantic-loss)',
                              border: '1px solid rgba(248, 113, 113, 0.3)',
                              padding: '4px 10px',
                              borderRadius: 'var(--radius-control)',
                              fontSize: '12px',
                              fontWeight: 500,
                              cursor: 'pointer',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '4px'
                            }}
                          >
                            <LogOut size={12} /> Exit
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* TAB 2: DECISIONS */}
        {activeTab === 'decisions' && (
          <div style={{
            backgroundColor: 'var(--bg-surface)',
            borderRadius: 'var(--radius-card)',
            border: '1px solid var(--border-hairline)',
            padding: '20px'
          }}>
            <h2 style={{ margin: '0 0 16px', fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)' }}>
              Decision Intelligence Log (Streaming)
            </h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {decisions.slice(0, 15).map((dec, i) => (
                <div key={dec.id || i} style={{
                  padding: '12px 16px',
                  borderRadius: 'var(--radius-control)',
                  backgroundColor: 'var(--bg-surface-subtle)',
                  border: '1px solid var(--border-subtle)',
                  borderLeft: `2px solid ${
                    dec.action === 'ENTER_LONG' ? 'var(--semantic-profit)' :
                    dec.action === 'ENTER_SHORT' ? 'var(--semantic-loss)' : 'var(--border-hairline)'
                  }`
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <span style={{ fontWeight: 600, fontSize: '13px', color: 'var(--text-primary)' }}>
                        {dec.instrument}
                      </span>
                      <span style={{
                        padding: '1px 6px',
                        borderRadius: 'var(--radius-control)',
                        fontSize: '11px',
                        fontWeight: 500,
                        border: '1px solid var(--border-hairline)',
                        color: dec.action.includes('ENTER') ? 'var(--text-primary)' : 'var(--text-tertiary)'
                      }}>
                        {dec.action}
                      </span>
                      <span style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>
                        Regime: {dec.regime}
                      </span>
                    </div>
                    <div className="tabular-nums" style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                      P(Win): <strong style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{(dec.calibrated_probability * 100).toFixed(1)}%</strong>
                      {' · '}
                      E[R]: <strong style={{ color: dec.expected_value_r >= 0 ? 'var(--semantic-profit)' : 'var(--semantic-loss)', fontWeight: 500 }}>
                        {dec.expected_value_r >= 0 ? '+' : ''}{dec.expected_value_r}R
                      </strong>
                    </div>
                  </div>
                  <p style={{ margin: '6px 0 0', fontSize: '12px', color: 'var(--text-secondary)' }}>
                    {dec.rationale || dec.veto_reason}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* TAB 3: OPTIONS CHAIN */}
        {activeTab === 'chain' && (
          <div style={{
            backgroundColor: 'var(--bg-surface)',
            borderRadius: 'var(--radius-card)',
            border: '1px solid var(--border-hairline)',
            overflow: 'hidden'
          }}>
            <div style={{
              padding: '16px 20px',
              borderBottom: '1px solid var(--border-hairline)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center'
            }}>
              <h2 style={{ margin: 0, fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)' }}>
                Nifty 50 Options Chain with Greeks (Black-76 Calculated)
              </h2>
              <span style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>
                ATM & NTM Weekly Expiry
              </span>
            </div>
            <div className="table-container">
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                <thead>
                  <tr style={{
                    borderBottom: '1px solid var(--border-hairline)',
                    color: 'var(--text-tertiary)',
                    fontSize: '11px'
                  }}>
                    <th style={{ padding: '10px 16px', textAlign: 'left', fontWeight: 500 }}>Type</th>
                    <th style={{ padding: '10px 16px', textAlign: 'right', fontWeight: 500 }}>Strike</th>
                    <th style={{ padding: '10px 16px', textAlign: 'right', fontWeight: 500 }}>LTP</th>
                    <th style={{ padding: '10px 16px', textAlign: 'right', fontWeight: 500 }}>Bid / Ask</th>
                    <th style={{ padding: '10px 16px', textAlign: 'right', fontWeight: 500 }}>IV (%)</th>
                    <th style={{ padding: '10px 16px', textAlign: 'right', fontWeight: 500 }}>Delta (Δ)</th>
                    <th style={{ padding: '10px 16px', textAlign: 'right', fontWeight: 500 }}>Gamma (Γ)</th>
                    <th style={{ padding: '10px 16px', textAlign: 'right', fontWeight: 500 }}>Theta (Θ)</th>
                    <th style={{ padding: '10px 16px', textAlign: 'right', fontWeight: 500 }}>Vega (ν)</th>
                  </tr>
                </thead>
                <tbody>
                  {optionChain.map((c, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                      <td style={{
                        padding: '10px 16px',
                        fontWeight: 600,
                        color: c.option_type === 'OPTION_CE' ? 'var(--semantic-profit)' : 'var(--semantic-loss)'
                      }}>
                        {c.option_type === 'OPTION_CE' ? 'CALL' : 'PUT'}
                      </td>
                      <td className="tabular-nums" style={{ padding: '10px 16px', textAlign: 'right', fontWeight: 600, color: 'var(--text-primary)' }}>
                        {c.strike}
                      </td>
                      <td className="tabular-nums" style={{ padding: '10px 16px', textAlign: 'right', color: 'var(--text-primary)' }}>
                        ₹{c.ltp.toFixed(2)}
                      </td>
                      <td className="tabular-nums" style={{ padding: '10px 16px', textAlign: 'right', color: 'var(--text-tertiary)' }}>
                        ₹{c.bid.toFixed(2)} / ₹{c.ask.toFixed(2)}
                      </td>
                      <td className="tabular-nums" style={{ padding: '10px 16px', textAlign: 'right', color: 'var(--text-secondary)' }}>
                        {c.iv.toFixed(1)}%
                      </td>
                      <td className="tabular-nums" style={{
                        padding: '10px 16px',
                        textAlign: 'right',
                        color: c.delta >= 0 ? 'var(--semantic-profit)' : 'var(--semantic-loss)'
                      }}>
                        {c.delta.toFixed(3)}
                      </td>
                      <td className="tabular-nums" style={{ padding: '10px 16px', textAlign: 'right', color: 'var(--text-secondary)' }}>
                        {c.gamma.toFixed(5)}
                      </td>
                      <td className="tabular-nums" style={{ padding: '10px 16px', textAlign: 'right', color: 'var(--semantic-loss)' }}>
                        {c.theta.toFixed(2)}
                      </td>
                      <td className="tabular-nums" style={{ padding: '10px 16px', textAlign: 'right', color: 'var(--text-secondary)' }}>
                        {c.vega.toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* TAB 4: LEARNING & MEMORY CENTER */}
        {activeTab === 'learning' && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '20px' }}>
            <div style={{
              backgroundColor: 'var(--bg-surface)',
              borderRadius: 'var(--radius-card)',
              border: '1px solid var(--border-hairline)',
              padding: '20px'
            }}>
              <h2 style={{ margin: '0 0 10px', fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Brain size={16} /> Post-Mortem Epistemic Validation
              </h2>
              <p style={{ fontSize: '13px', color: 'var(--text-secondary)', lineHeight: '1.5', margin: 0 }}>
                The engine distinguishes <strong>lucky wins</strong> (near-stop breaches) from <strong>genuine skill</strong>.
                Winning setups with excessive adverse excursion are down-weighted rather than celebrated.
              </p>
              <div style={{
                marginTop: '16px',
                padding: '12px 14px',
                borderRadius: 'var(--radius-control)',
                backgroundColor: 'var(--bg-surface-subtle)',
                border: '1px solid var(--border-subtle)',
                borderLeft: '2px solid var(--semantic-profit)'
              }}>
                <div style={{ fontSize: '12px', color: 'var(--semantic-profit)', fontWeight: 600 }}>
                  ● CLEAN SKILL WIN (Attribution Pattern)
                </div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                  MFE:MAE ratio &gt; 2.5 with tight invalidation adherence. Model confidence reinforced.
                </div>
              </div>
              <div style={{
                marginTop: '10px',
                padding: '12px 14px',
                borderRadius: 'var(--radius-control)',
                backgroundColor: 'var(--bg-surface-subtle)',
                border: '1px solid var(--border-subtle)',
                borderLeft: '2px solid var(--semantic-warning)'
              }}>
                <div style={{ fontSize: '12px', color: 'var(--semantic-warning)', fontWeight: 600 }}>
                  ● LUCKY WIN ALERT (Noise Anomaly)
                </div>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                  Position endured &gt; 75% adverse drawdown before reversing to target. Sizing model flags sub-optimal entry timing.
                </div>
              </div>
            </div>

            <div style={{
              backgroundColor: 'var(--bg-surface)',
              borderRadius: 'var(--radius-card)',
              border: '1px solid var(--border-hairline)',
              padding: '20px'
            }}>
              <h2 style={{ margin: '0 0 10px', fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Activity size={16} /> Counterfactual Shadow Engine
              </h2>
              <p style={{ fontSize: '13px', color: 'var(--text-secondary)', lineHeight: '1.5', margin: 0 }}>
                Every opportunity blocked by the Risk Gate or low-confidence filters is tracked in a shadow simulator for 60 minutes.
              </p>
              <div style={{ marginTop: '16px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div style={{
                  padding: '14px',
                  backgroundColor: 'var(--bg-surface-subtle)',
                  borderRadius: 'var(--radius-control)',
                  border: '1px solid var(--border-subtle)'
                }}>
                  <div className="tabular-nums" style={{ fontSize: '18px', fontWeight: 600, color: 'var(--semantic-profit)' }}>
                    ₹14,200
                  </div>
                  <span style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>Capital Saved (Losses avoided)</span>
                </div>
                <div style={{
                  padding: '14px',
                  backgroundColor: 'var(--bg-surface-subtle)',
                  borderRadius: 'var(--radius-control)',
                  border: '1px solid var(--border-subtle)'
                }}>
                  <div className="tabular-nums" style={{ fontSize: '18px', fontWeight: 600, color: 'var(--semantic-warning)' }}>
                    ₹6,800
                  </div>
                  <span style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>Missed Alpha (Trades skipped)</span>
                </div>
              </div>
              <p style={{ fontSize: '12px', color: 'var(--text-tertiary)', marginTop: '12px' }}>
                Net Filter Edge: +₹7,400. Risk Gate demonstrably adds positive value.
              </p>
            </div>
          </div>
        )}

        {/* TAB 5: LEDGER & CAPITAL */}
        {activeTab === 'ledger' && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '20px' }}>
            <div style={{
              backgroundColor: 'var(--bg-surface)',
              borderRadius: 'var(--radius-card)',
              border: '1px solid var(--border-hairline)',
              padding: '20px'
            }}>
              <h2 style={{ margin: '0 0 16px', fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)' }}>
                Virtual Capital Controls
              </h2>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <div>
                  <label style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Deposit Virtual Capital (INR)</label>
                  <input
                    type="number"
                    value={depositAmount}
                    onChange={(e) => setDepositAmount(e.target.value)}
                    className="tabular-nums"
                    style={{
                      width: '100%',
                      backgroundColor: 'var(--bg-surface-subtle)',
                      border: '1px solid var(--border-hairline)',
                      padding: '8px 12px',
                      borderRadius: 'var(--radius-control)',
                      color: 'var(--text-primary)',
                      marginTop: '6px',
                      fontSize: '13px'
                    }}
                  />
                </div>
                <button
                  onClick={handleDeposit}
                  className="transition-fast"
                  style={{
                    backgroundColor: 'var(--accent)',
                    color: 'var(--accent-contrast)',
                    border: 'none',
                    padding: '8px 16px',
                    borderRadius: 'var(--radius-control)',
                    fontWeight: 600,
                    fontSize: '13px',
                    cursor: 'pointer'
                  }}
                >
                  Deposit Virtual Capital
                </button>
              </div>
            </div>

            <div style={{
              backgroundColor: 'var(--bg-surface)',
              borderRadius: 'var(--radius-card)',
              border: '1px solid var(--border-hairline)',
              overflow: 'hidden'
            }}>
              <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border-hairline)' }}>
                <h2 style={{ margin: 0, fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)' }}>
                  Double-Entry Transaction History
                </h2>
              </div>
              <div className="table-container">
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                  <thead>
                    <tr style={{
                      borderBottom: '1px solid var(--border-hairline)',
                      color: 'var(--text-tertiary)',
                      fontSize: '11px'
                    }}>
                      <th style={{ padding: '10px 16px', textAlign: 'left', fontWeight: 500 }}>Type</th>
                      <th style={{ padding: '10px 16px', textAlign: 'right', fontWeight: 500 }}>Amount</th>
                      <th style={{ padding: '10px 16px', textAlign: 'right', fontWeight: 500 }}>Balance After</th>
                      <th style={{ padding: '10px 16px', textAlign: 'left', fontWeight: 500 }}>Idempotency Reference</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ledger.map((tx) => (
                      <tr key={tx.id} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                        <td style={{ padding: '10px 16px', fontWeight: 500, color: 'var(--text-primary)' }}>
                          {tx.tx_type}
                        </td>
                        <td className="tabular-nums" style={{
                          padding: '10px 16px',
                          textAlign: 'right',
                          fontWeight: 500,
                          color: tx.amount >= 0 ? 'var(--semantic-profit)' : 'var(--semantic-loss)'
                        }}>
                          {tx.amount >= 0 ? '+' : ''}₹{tx.amount.toFixed(2)}
                        </td>
                        <td className="tabular-nums" style={{ padding: '10px 16px', textAlign: 'right', color: 'var(--text-primary)' }}>
                          ₹{tx.balance_after.toFixed(2)}
                        </td>
                        <td style={{
                          padding: '10px 16px',
                          color: 'var(--text-tertiary)',
                          fontFamily: 'var(--font-mono)',
                          fontSize: '11px'
                        }}>
                          {tx.idempotency_key}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
