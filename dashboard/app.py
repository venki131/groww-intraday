"""
Groww Intraday Automation — Interactive Dashboard.

Run with:
    cd trade/groww-intraday
    .venv/bin/streamlit run dashboard/app.py

Tabs:
  1. 📊 Chart          — Candlestick + EMA overlay + buy/sell signal markers
  2. 🚀 Backtest       — Run strategy, see equity curve + trade log
  3. 💼 Paper Trading  — Place paper orders, track positions & P&L
  4. 🌐 Universe       — Browse all 100 Nifty stocks, filter by sector
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from market.hours import is_market_open, is_trading_allowed
from market.universe import NIFTY100_SYMBOLS

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Groww Intraday Automation",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  .stTabs [data-baseweb="tab-list"] { gap: 8px; }
  .stTabs [data-baseweb="tab"] {
    background: #1e1e2e; border-radius: 6px 6px 0 0;
    padding: 6px 18px; font-weight: 600;
  }
  .stTabs [aria-selected="true"] { background: #313244; }
  .metric-card {
    background: #1e1e2e; border-radius: 10px;
    padding: 14px 18px; margin-bottom: 8px;
  }
  div[data-testid="stMetricValue"] { font-size: 1.4rem; font-weight: 700; }
  .trade-win  { color: #a6e3a1; font-weight: 700; }
  .trade-loss { color: #f38ba8; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────
if "paper_broker" not in st.session_state:
    from broker.mock import MockBroker
    st.session_state.paper_broker = MockBroker(
        available_cash=Decimal("100000"), mode="paper"
    )
if "paper_trades" not in st.session_state:
    st.session_state.paper_trades = []        # list[dict]
if "paper_positions" not in st.session_state:
    st.session_state.paper_positions = {}     # ticker → {qty, avg_price}
if "paper_cash" not in st.session_state:
    st.session_state.paper_cash = Decimal("100000")
if "last_candles" not in st.session_state:
    st.session_state.last_candles = {}        # ticker → DataFrame
if "last_report" not in st.session_state:
    st.session_state.last_report = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _generate_candles(ticker: str, count: int = 500,
                      base_price: float = 1000.0) -> pd.DataFrame:
    """Generate synthetic candles and cache in session state."""
    if ticker in st.session_state.last_candles:
        return st.session_state.last_candles[ticker]
    broker = st.session_state.paper_broker
    candles = broker.generate_candles(
        ticker=ticker, count=count, base_price=Decimal(str(base_price))
    )
    df = pd.DataFrame([
        {"timestamp": c.timestamp,
         "open": float(c.open), "high": float(c.high),
         "low": float(c.low), "close": float(c.close),
         "volume": c.volume}
        for c in candles
    ])
    st.session_state.last_candles[ticker] = df
    return df


def _add_emas(df: pd.DataFrame, fast: int, slow: int) -> pd.DataFrame:
    df = df.copy()
    df[f"ema{fast}"] = df["close"].ewm(span=fast, adjust=False).mean()
    df[f"ema{slow}"] = df["close"].ewm(span=slow, adjust=False).mean()
    return df


def _get_signals(ticker: str, df: pd.DataFrame,
                 strategy_name: str, fast: int, slow: int,
                 rsi_period: int = 14) -> list[dict]:
    from strategies.ema_crossover import EMACrossoverStrategy
    from strategies.rsi_mean_reversion import RSIMeanReversionStrategy

    if strategy_name == "ema_crossover":
        strat = EMACrossoverStrategy(fast_period=fast, slow_period=slow)
    else:
        strat = RSIMeanReversionStrategy(rsi_period=rsi_period)

    signals = strat.generate_all_signals(ticker, df)
    return [
        {
            "timestamp": s.timestamp,
            "type": s.signal_type.value,
            "price": float(s.price),
        }
        for s in signals
    ]


def _candlestick_fig(df: pd.DataFrame, ticker: str,
                     fast: int, slow: int, signals: list[dict]) -> go.Figure:
    """Build a full candlestick chart with EMA + volume + signal markers."""
    df = _add_emas(df, fast, slow)

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.75, 0.25],
        vertical_spacing=0.03,
    )

    # Candlesticks
    fig.add_trace(go.Candlestick(
        x=df["timestamp"],
        open=df["open"], high=df["high"],
        low=df["low"], close=df["close"],
        name=ticker,
        increasing_line_color="#a6e3a1",
        decreasing_line_color="#f38ba8",
    ), row=1, col=1)

    # EMA fast
    fig.add_trace(go.Scatter(
        x=df["timestamp"], y=df[f"ema{fast}"],
        name=f"EMA {fast}", mode="lines",
        line=dict(color="#89b4fa", width=1.5),
    ), row=1, col=1)

    # EMA slow
    fig.add_trace(go.Scatter(
        x=df["timestamp"], y=df[f"ema{slow}"],
        name=f"EMA {slow}", mode="lines",
        line=dict(color="#fab387", width=1.5),
    ), row=1, col=1)

    # Signal markers
    buys  = [s for s in signals if s["type"] == "BUY"]
    sells = [s for s in signals if s["type"] == "SELL"]

    if buys:
        fig.add_trace(go.Scatter(
            x=[s["timestamp"] for s in buys],
            y=[s["price"] * 0.995 for s in buys],
            mode="markers",
            name="BUY",
            marker=dict(symbol="triangle-up", color="#a6e3a1", size=12),
        ), row=1, col=1)

    if sells:
        fig.add_trace(go.Scatter(
            x=[s["timestamp"] for s in sells],
            y=[s["price"] * 1.005 for s in sells],
            mode="markers",
            name="SELL",
            marker=dict(symbol="triangle-down", color="#f38ba8", size=12),
        ), row=1, col=1)

    # Volume bars
    colors = ["#a6e3a1" if c >= o else "#f38ba8"
              for c, o in zip(df["close"], df["open"])]
    fig.add_trace(go.Bar(
        x=df["timestamp"], y=df["volume"],
        name="Volume", marker_color=colors, opacity=0.6,
    ), row=2, col=1)

    fig.update_layout(
        template="plotly_dark",
        height=580,
        margin=dict(l=0, r=0, t=30, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0),
        xaxis_rangeslider_visible=False,
        xaxis2_title="",
        yaxis_title="Price (₹)",
        yaxis2_title="Volume",
    )
    return fig


def _equity_fig(equity_curve: list[dict], initial_capital: float) -> go.Figure:
    eq_df = pd.DataFrame(equity_curve)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=eq_df["timestamp"], y=eq_df["equity"],
        mode="lines+markers",
        name="Portfolio Value",
        line=dict(color="#89b4fa", width=2),
        fill="tozeroy", fillcolor="rgba(137,180,250,0.08)",
    ))
    fig.add_hline(
        y=initial_capital, line_dash="dash",
        line_color="#6c7086", annotation_text="Initial Capital",
    )
    fig.update_layout(
        template="plotly_dark", height=360,
        margin=dict(l=0, r=0, t=20, b=0),
        yaxis_title="Portfolio Value (₹)",
    )
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# Header
# ══════════════════════════════════════════════════════════════════════════════
st.title("📈 Groww Intraday Automation")
st.caption("Mode: **BACKTEST / PAPER only** — Live trading is permanently disabled.")

# Market status bar
c1, c2, c3, c4 = st.columns(4)
c1.metric("NSE Market", "🟢 Open" if is_market_open() else "🔴 Closed")
c2.metric("Trading Allowed", "✅ Yes" if is_trading_allowed() else "❌ No")
c3.metric("Universe", f"Nifty 100  ({len(NIFTY100_SYMBOLS)} stocks)")
c4.metric(
    "Paper Cash",
    f"₹{float(st.session_state.paper_cash):,.0f}",
)

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# Tabs
# ══════════════════════════════════════════════════════════════════════════════
tab_chart, tab_backtest, tab_paper, tab_universe = st.tabs([
    "📊 Chart & Signals",
    "🚀 Backtest",
    "💼 Paper Trading",
    "🌐 Universe",
])


# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — Chart & Signals
# ─────────────────────────────────────────────────────────────────────────────
with tab_chart:
    left, right = st.columns([1, 3])

    with left:
        st.subheader("⚙️ Chart Settings")
        ticker_c = st.selectbox("Symbol", NIFTY100_SYMBOLS, key="chart_ticker")
        strategy_c = st.selectbox(
            "Strategy overlay", ["ema_crossover", "rsi_mean_reversion"],
            key="chart_strategy",
        )
        fast_c  = st.slider("EMA Fast", 3, 30, 9, key="chart_fast")
        slow_c  = st.slider("EMA Slow", 10, 60, 21, key="chart_slow")
        candle_count = st.slider("Candles", 100, 1000, 300, 50, key="chart_count")
        base_p = st.number_input("Base Price (₹)", 100, 50000, 1000, key="chart_base")

        if st.button("🔄 Refresh Candles", key="chart_refresh"):
            # Clear cache for this ticker so new data is generated
            st.session_state.last_candles.pop(ticker_c, None)

        show_signals = st.toggle("Show buy/sell signals", value=True, key="chart_signals")
        st.info("ℹ️ Synthetic OHLCV data — no live feed required.")

    with right:
        df_c = _generate_candles(ticker_c, count=candle_count, base_price=float(base_p))
        signals_c = _get_signals(ticker_c, df_c, strategy_c, fast_c, slow_c) if show_signals else []

        fig_c = _candlestick_fig(df_c, ticker_c, fast_c, slow_c, signals_c)
        st.plotly_chart(fig_c, use_container_width=True, key="chart_fig")

        if show_signals:
            buys_c  = [s for s in signals_c if s["type"] == "BUY"]
            sells_c = [s for s in signals_c if s["type"] == "SELL"]
            sc1, sc2, sc3 = st.columns(3)
            sc1.metric("Total Signals", len(signals_c))
            sc2.metric("🟢 Buy signals",  len(buys_c))
            sc3.metric("🔴 Sell signals", len(sells_c))

        # Last 10 candles table
        with st.expander("📋 Raw candle data (last 20 rows)"):
            st.dataframe(
                df_c.tail(20).sort_values("timestamp", ascending=False)
                    .reset_index(drop=True),
                use_container_width=True,
            )


# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — Backtest
# ─────────────────────────────────────────────────────────────────────────────
with tab_backtest:
    left_b, right_b = st.columns([1, 3])

    with left_b:
        st.subheader("⚙️ Backtest Config")
        ticker_b   = st.selectbox("Symbol", NIFTY100_SYMBOLS, key="bt_ticker")
        strategy_b = st.selectbox("Strategy", ["ema_crossover", "rsi_mean_reversion"], key="bt_strat")
        capital_b  = st.number_input("Capital (₹)", 1000, 10_000_000, 100_000, 1000, key="bt_capital")
        fast_b     = st.slider("EMA Fast", 3, 30, 9, key="bt_fast")
        slow_b     = st.slider("EMA Slow", 10, 60, 21, key="bt_slow")
        candles_b  = st.slider("Candle count", 100, 2000, 500, 50, key="bt_candles")
        comm_b     = st.slider("Commission %", 0.0, 0.5, 0.03, 0.01, key="bt_comm")
        slip_b     = st.slider("Slippage %",   0.0, 0.5, 0.01, 0.005, key="bt_slip")

        run_bt = st.button("🚀 Run Backtest", type="primary", key="bt_run")

    with right_b:
        if run_bt:
            with st.spinner(f"Running {strategy_b} on {ticker_b}..."):
                from backtesting.engine import BacktestEngine
                from strategies.ema_crossover import EMACrossoverStrategy
                from strategies.rsi_mean_reversion import RSIMeanReversionStrategy

                broker_bt = st.session_state.paper_broker
                candles_obj = broker_bt.generate_candles(
                    ticker=ticker_b, count=candles_b, base_price=Decimal("1000")
                )
                df_bt = pd.DataFrame([
                    {"timestamp": c.timestamp, "open": float(c.open),
                     "high": float(c.high), "low": float(c.low),
                     "close": float(c.close), "volume": c.volume}
                    for c in candles_obj
                ])

                strat_bt = (
                    EMACrossoverStrategy(fast_period=fast_b, slow_period=slow_b)
                    if strategy_b == "ema_crossover"
                    else RSIMeanReversionStrategy()
                )
                engine = BacktestEngine(
                    strategy=strat_bt,
                    capital=Decimal(str(capital_b)),
                    commission_pct=comm_b,
                    slippage_pct=slip_b,
                )
                report = engine.run(ticker=ticker_b, candles_df=df_bt)
                st.session_state.last_report = report

        report = st.session_state.last_report
        if report is None:
            st.info("👈 Configure parameters and click **Run Backtest**.")
        else:
            # Metric cards
            st.subheader(f"📊 {report.strategy_name} · {report.ticker}")
            m1, m2, m3, m4, m5 = st.columns(5)
            ret_color = "normal" if report.total_return_pct >= 0 else "inverse"
            m1.metric("Total Return", f"{report.total_return_pct:+.2f}%",
                      delta_color=ret_color)
            m2.metric("Total Trades", report.total_trades)
            m3.metric("Win Rate", f"{report.win_rate_pct:.1f}%")
            m4.metric("Max Drawdown", f"{report.max_drawdown_pct:.2f}%")
            m5.metric("Sharpe Ratio", f"{report.sharpe_ratio:.2f}")

            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("Net P&L", f"₹{float(report.total_pnl):+,.2f}")
            mc2.metric("Commission Paid", f"₹{float(report.total_commission):,.2f}")
            mc3.metric("Final Capital",   f"₹{float(report.final_capital):,.2f}")

            # Equity curve
            if report.equity_curve:
                st.plotly_chart(
                    _equity_fig(report.equity_curve, float(report.initial_capital)),
                    use_container_width=True, key="bt_eq_fig",
                )
            else:
                st.warning("No trades executed — equity curve unavailable.")

            # Trade log
            if report.trades:
                st.subheader(f"📋 Trade Log ({report.total_trades} trades)")
                trades_df = pd.DataFrame([
                    {
                        "Entry Time": t.entry_time.strftime("%Y-%m-%d %H:%M"),
                        "Exit Time":  t.exit_time.strftime("%Y-%m-%d %H:%M"),
                        "Entry ₹":    float(t.entry_price),
                        "Exit ₹":     float(t.exit_price),
                        "Qty":        t.quantity,
                        "Gross P&L":  float(t.gross_pnl),
                        "Commission": float(t.commission),
                        "Net P&L":    float(t.net_pnl),
                        "Exit Reason": t.exit_reason,
                        "W/L":        "✅ Win" if t.net_pnl > 0 else "❌ Loss",
                    }
                    for t in report.trades
                ])
                st.dataframe(
                    trades_df.style.map(
                        lambda v: "color: #a6e3a1" if v == "✅ Win" else "color: #f38ba8",
                        subset=["W/L"],
                    ),
                    use_container_width=True,
                    height=360,
                )

                # Win/Loss distribution
                win_df = trades_df["Net P&L"]
                fig_dist = go.Figure()
                fig_dist.add_trace(go.Histogram(
                    x=win_df, nbinsx=20,
                    marker_color=["#a6e3a1" if v > 0 else "#f38ba8" for v in win_df],
                    name="P&L Distribution",
                ))
                fig_dist.update_layout(
                    template="plotly_dark", height=260,
                    title="P&L Distribution",
                    margin=dict(l=0, r=0, t=36, b=0),
                    xaxis_title="Net P&L (₹)", yaxis_title="# Trades",
                )
                st.plotly_chart(fig_dist, use_container_width=True, key="bt_dist_fig")
            else:
                st.info("No trades generated — try different EMA periods or more candles.")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — Paper Trading
# ─────────────────────────────────────────────────────────────────────────────
with tab_paper:
    st.subheader("💼 Paper Trading Session")
    st.caption("⚠️ All orders are simulated — no real money, no real network calls.")

    # Portfolio summary
    positions = st.session_state.paper_positions
    cash      = st.session_state.paper_cash

    # Compute unrealised P&L using last known candle price
    total_mktval = Decimal("0")
    for tkr, pos in positions.items():
        df_p = st.session_state.last_candles.get(tkr)
        last_px = Decimal(str(df_p["close"].iloc[-1])) if df_p is not None else pos["avg_price"]
        total_mktval += last_px * pos["qty"]

    total_equity = cash + total_mktval
    unrealised   = total_mktval - sum(
        p["avg_price"] * p["qty"] for p in positions.values()
    )

    pc1, pc2, pc3, pc4 = st.columns(4)
    pc1.metric("Cash Available", f"₹{float(cash):,.2f}")
    pc2.metric("Market Value",   f"₹{float(total_mktval):,.2f}")
    pc3.metric("Total Equity",   f"₹{float(total_equity):,.2f}")
    pc4.metric(
        "Unrealised P&L",
        f"₹{float(unrealised):+,.2f}",
        delta_color="normal" if unrealised >= 0 else "inverse",
    )

    st.divider()

    # Order entry
    oe1, oe2 = st.columns([1, 2])
    with oe1:
        st.markdown("### 📝 Place Order")
        order_ticker = st.selectbox("Symbol", NIFTY100_SYMBOLS, key="paper_ticker")
        order_side   = st.radio("Side", ["BUY", "SELL"], horizontal=True, key="paper_side")
        order_qty    = st.number_input("Quantity", 1, 10000, 10, key="paper_qty")

        # Get latest price for the ticker
        df_oe = st.session_state.last_candles.get(order_ticker)
        if df_oe is None:
            df_oe = _generate_candles(order_ticker, count=100)
        last_price_oe = float(df_oe["close"].iloc[-1])
        order_price   = st.number_input(
            "Price (₹) — 0 = market",
            min_value=0.0, value=last_price_oe,
            step=0.5, format="%.2f", key="paper_price",
        )

        order_value = (order_price or last_price_oe) * order_qty
        st.caption(f"Estimated order value: **₹{order_value:,.2f}**")

        place_btn = st.button(
            f"{'🟢 BUY' if order_side == 'BUY' else '🔴 SELL'} {order_qty} × {order_ticker}",
            type="primary", key="paper_place",
        )

        if place_btn:
            fill_px = Decimal(str(order_price or last_price_oe))
            trade_val = fill_px * order_qty

            if order_side == "BUY":
                if trade_val > cash:
                    st.error(f"❌ Insufficient cash. Need ₹{float(trade_val):,.2f}, have ₹{float(cash):,.2f}")
                else:
                    st.session_state.paper_cash -= trade_val
                    if order_ticker in positions:
                        old = positions[order_ticker]
                        total_qty  = old["qty"] + order_qty
                        total_cost = old["avg_price"] * old["qty"] + fill_px * order_qty
                        positions[order_ticker] = {
                            "qty": total_qty,
                            "avg_price": total_cost / total_qty,
                        }
                    else:
                        positions[order_ticker] = {"qty": order_qty, "avg_price": fill_px}

                    st.session_state.paper_trades.append({
                        "Side": "BUY", "Ticker": order_ticker,
                        "Qty": order_qty, "Price": float(fill_px),
                        "Value": float(trade_val),
                    })
                    st.success(f"✅ Bought {order_qty} × {order_ticker} @ ₹{float(fill_px):,.2f}")
                    st.rerun()

            else:  # SELL
                held_qty = positions.get(order_ticker, {}).get("qty", 0)
                if order_qty > held_qty:
                    st.error(f"❌ Only {held_qty} shares held in {order_ticker}.")
                else:
                    avg_buy = positions[order_ticker]["avg_price"]
                    pnl = (fill_px - avg_buy) * order_qty
                    st.session_state.paper_cash += trade_val

                    if order_qty == held_qty:
                        del positions[order_ticker]
                    else:
                        positions[order_ticker]["qty"] -= order_qty

                    st.session_state.paper_trades.append({
                        "Side": "SELL", "Ticker": order_ticker,
                        "Qty": order_qty, "Price": float(fill_px),
                        "Value": float(trade_val),
                        "Realised P&L": float(pnl),
                    })
                    pnl_str = f"₹{float(pnl):+,.2f}"
                    color   = "✅" if pnl >= 0 else "❌"
                    st.success(
                        f"{color} Sold {order_qty} × {order_ticker} "
                        f"@ ₹{float(fill_px):,.2f} | P&L: **{pnl_str}**"
                    )
                    st.rerun()

    with oe2:
        st.markdown("### 📂 Open Positions")
        if positions:
            pos_rows = []
            for tkr, pos in positions.items():
                df_pp = st.session_state.last_candles.get(tkr)
                lp = float(df_pp["close"].iloc[-1]) if df_pp is not None else float(pos["avg_price"])
                upnl = (lp - float(pos["avg_price"])) * pos["qty"]
                pos_rows.append({
                    "Ticker": tkr,
                    "Qty":    pos["qty"],
                    "Avg Buy ₹": float(pos["avg_price"]),
                    "LTP ₹":    lp,
                    "Mkt Value ₹": lp * pos["qty"],
                    "Unreal P&L ₹": upnl,
                })
            pos_df = pd.DataFrame(pos_rows)
            st.dataframe(
                pos_df.style.map(
                    lambda v: f"color: {'#a6e3a1' if v >= 0 else '#f38ba8'}",
                    subset=["Unreal P&L ₹"],
                ),
                use_container_width=True, height=240,
            )
        else:
            st.info("No open positions.")

        st.markdown("### 📋 Order History")
        trades_hist = st.session_state.paper_trades
        if trades_hist:
            th_df = pd.DataFrame(trades_hist[::-1])   # newest first
            st.dataframe(th_df, use_container_width=True, height=240)
        else:
            st.info("No orders placed yet.")

        if st.button("🔄 Reset Paper Session", key="paper_reset"):
            st.session_state.paper_cash      = Decimal("100000")
            st.session_state.paper_positions = {}
            st.session_state.paper_trades    = []
            st.session_state.paper_broker    = __import__(
                "broker.mock", fromlist=["MockBroker"]
            ).MockBroker(available_cash=Decimal("100000"), mode="paper")
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 — Universe Browser
# ─────────────────────────────────────────────────────────────────────────────
with tab_universe:
    st.subheader("🌐 Nifty 100 Universe")

    # Build sector-enriched table from InstrumentRegistry
    try:
        from app.market.instruments import get_registry
        reg = get_registry()
        rows = [
            {
                "Ticker":        r.ticker,
                "Name":          r.name,
                "Sector":        r.sector,
                "Industry":      r.industry,
                "ISIN":          r.isin,
                "Groww Symbol":  r.groww_symbol,
            }
            for r in sorted(reg._records, key=lambda x: x.ticker)
        ]
        universe_df = pd.DataFrame(rows)
        sectors = ["All"] + sorted(universe_df["Sector"].unique().tolist())
    except Exception:
        # Fallback if InstrumentRegistry not on path
        universe_df = pd.DataFrame([{"Ticker": s} for s in sorted(NIFTY100_SYMBOLS)])
        sectors = ["All"]

    # Sector filter
    u1, u2 = st.columns([1, 3])
    with u1:
        sector_filter = st.selectbox("Filter by Sector", sectors, key="uni_sector")
        search_term   = st.text_input("Search ticker / name", key="uni_search").upper()

    filtered_df = universe_df.copy()
    if sector_filter != "All" and "Sector" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["Sector"] == sector_filter]
    if search_term:
        mask = filtered_df["Ticker"].str.contains(search_term, na=False)
        if "Name" in filtered_df.columns:
            mask |= filtered_df["Name"].str.upper().str.contains(search_term, na=False)
        filtered_df = filtered_df[mask]

    with u2:
        st.caption(f"Showing **{len(filtered_df)}** of **{len(universe_df)}** instruments")

    st.dataframe(filtered_df.reset_index(drop=True), use_container_width=True, height=520)

    # Sector breakdown chart (only when full data available)
    if "Sector" in universe_df.columns:
        sector_counts = universe_df["Sector"].value_counts().reset_index()
        sector_counts.columns = ["Sector", "Count"]
        fig_pie = go.Figure(go.Pie(
            labels=sector_counts["Sector"],
            values=sector_counts["Count"],
            hole=0.4,
            textinfo="label+percent",
        ))
        fig_pie.update_layout(
            template="plotly_dark", height=380,
            title="Nifty 100 — Sector Breakdown",
            margin=dict(l=0, r=0, t=40, b=0),
            showlegend=False,
        )
        st.plotly_chart(fig_pie, use_container_width=True, key="uni_pie")