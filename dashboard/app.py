"""
Streamlit Dashboard for Groww Intraday Automation.

Run with: streamlit run dashboard/app.py

Shows:
- Market status
- Portfolio snapshot
- Backtest results with equity curve
- Nifty 100 universe
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

# Ensure project root is on sys.path when run via `streamlit run dashboard/app.py`
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from market.hours import is_market_open, is_trading_allowed
from market.universe import NIFTY100_SYMBOLS

st.set_page_config(
    page_title="Groww Intraday Automation",
    page_icon="📈",
    layout="wide",
)

st.title("📈 Groww Intraday Automation Dashboard")
st.caption("Mode: **BACKTEST / PAPER only** — Live trading is permanently disabled.")

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Configuration")
    selected_ticker = st.selectbox("Symbol", NIFTY100_SYMBOLS, index=0)
    strategy = st.selectbox("Strategy", ["ema_crossover", "rsi_mean_reversion"])
    initial_capital = st.number_input("Capital (₹)", min_value=1000, value=10000, step=1000)
    fast_period = st.slider("EMA Fast Period", 3, 20, 9)
    slow_period = st.slider("EMA Slow Period", 10, 50, 21)
    run_backtest = st.button("🚀 Run Backtest", type="primary")

# ---------------------------------------------------------------------------
# Market Status
# ---------------------------------------------------------------------------
col1, col2, col3 = st.columns(3)
with col1:
    status = "🟢 Open" if is_market_open() else "🔴 Closed"
    st.metric("NSE Market", status)
with col2:
    allowed = "✅ Yes" if is_trading_allowed() else "❌ No"
    st.metric("Trading Allowed", allowed)
with col3:
    st.metric("Universe", f"Nifty 100 ({len(NIFTY100_SYMBOLS)} stocks)")

st.divider()

# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------
if run_backtest:
    with st.spinner(f"Running backtest: {strategy} on {selected_ticker}..."):
        from backtesting.engine import BacktestEngine
        from broker.mock import MockBroker
        from strategies.ema_crossover import EMACrossoverStrategy
        from strategies.rsi_mean_reversion import RSIMeanReversionStrategy

        broker = MockBroker()
        candles = broker.generate_candles(
            ticker=selected_ticker,
            count=500,
            base_price=Decimal("1000"),
        )
        df = pd.DataFrame([
            {"timestamp": c.timestamp, "open": float(c.open), "high": float(c.high),
             "low": float(c.low), "close": float(c.close), "volume": c.volume}
            for c in candles
        ])

        if strategy == "ema_crossover":
            strat = EMACrossoverStrategy(fast_period=fast_period, slow_period=slow_period)
        else:
            strat = RSIMeanReversionStrategy()

        engine = BacktestEngine(strategy=strat, capital=Decimal(str(initial_capital)))
        report = engine.run(ticker=selected_ticker, candles_df=df)

    # Metrics row
    st.subheader(f"📊 Results: {strategy} on {selected_ticker}")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total Return", f"{report.total_return_pct:+.2f}%")
    m2.metric("Total Trades", report.total_trades)
    m3.metric("Win Rate", f"{report.win_rate_pct:.1f}%")
    m4.metric("Max Drawdown", f"{report.max_drawdown_pct:.2f}%")
    m5.metric("Sharpe Ratio", f"{report.sharpe_ratio:.2f}")

    col_a, col_b = st.columns(2)
    col_a.metric("Net P&L", f"₹{float(report.total_pnl):+,.2f}")
    col_b.metric("Commission Paid", f"₹{float(report.total_commission):,.2f}")

    # Equity curve
    if report.equity_curve:
        eq_df = pd.DataFrame(report.equity_curve)
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=eq_df["timestamp"], y=eq_df["equity"],
            mode="lines", name="Portfolio Value",
            line=dict(color="#00cc96", width=2),
        ))
        fig.add_hline(y=float(initial_capital), line_dash="dash",
                      line_color="gray", annotation_text="Initial Capital")
        fig.update_layout(
            title=f"Equity Curve — {selected_ticker}",
            xaxis_title="Time", yaxis_title="Portfolio Value (₹)",
            template="plotly_dark", height=400,
        )
        st.plotly_chart(fig, use_container_width=True)

    # Trade log
    if report.trades:
        st.subheader("📋 Trade Log")
        trades_df = pd.DataFrame([
            {"Entry": t.entry_time, "Exit": t.exit_time,
             "Entry ₹": float(t.entry_price), "Exit ₹": float(t.exit_price),
             "Qty": t.quantity, "Net PnL ₹": float(t.net_pnl),
             "Reason": t.exit_reason, "Win": "✅" if t.net_pnl > 0 else "❌"}
            for t in report.trades
        ])
        st.dataframe(trades_df, use_container_width=True)
    else:
        st.info("No trades generated. Try different parameters.")

else:
    st.info("👈 Configure parameters in the sidebar and click **Run Backtest**.")

# ---------------------------------------------------------------------------
# Nifty 100 Universe
# ---------------------------------------------------------------------------
with st.expander("📌 Nifty 100 Universe"):
    universe_df = pd.DataFrame(
        [{"Symbol": s} for s in NIFTY100_SYMBOLS]
    )
    st.dataframe(universe_df, use_container_width=True)

st.caption("⚠️ This system is for BACKTEST and PAPER trading only. Live trading is permanently disabled.")