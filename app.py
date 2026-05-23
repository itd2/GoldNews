import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import feedparser
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from dotenv import load_dotenv
from ta.momentum import RSIIndicator
from ta.trend import MACD, SMAIndicator

try:
    import ccxt
except Exception:
    ccxt = None

load_dotenv()

st.set_page_config(page_title="BTC Realtime Command Center", page_icon="₿", layout="wide")


@dataclass
class SignalResult:
    confidence: int
    summary: str
    action: str


def get_btc_ohlcv(limit: int = 300) -> pd.DataFrame:
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": "BTCUSDT", "interval": "1m", "limit": limit}
    data = requests.get(url, params=params, timeout=10).json()
    df = pd.DataFrame(data, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "qav", "num_trades", "taker_base", "taker_quote", "ignore"
    ])
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df[["open_time", "open", "high", "low", "close", "volume"]].dropna()


def technical_confidence(df: pd.DataFrame) -> SignalResult:
    close = df["close"]
    rsi = RSIIndicator(close, window=14).rsi().iloc[-1]
    sma20 = SMAIndicator(close, window=20).sma_indicator().iloc[-1]
    sma50 = SMAIndicator(close, window=50).sma_indicator().iloc[-1]
    macd = MACD(close)
    macd_line = macd.macd().iloc[-1]
    signal_line = macd.macd_signal().iloc[-1]
    price = close.iloc[-1]

    score = 50
    notes = []

    if rsi < 30:
        score += 20
        notes.append("RSI oversold")
    elif rsi > 70:
        score -= 20
        notes.append("RSI overbought")

    if sma20 > sma50:
        score += 15
        notes.append("SMA20 above SMA50")
    else:
        score -= 15
        notes.append("SMA20 below SMA50")

    if macd_line > signal_line:
        score += 15
        notes.append("MACD bullish crossover")
    else:
        score -= 15
        notes.append("MACD bearish crossover")

    if price > sma20:
        score += 10
    else:
        score -= 10

    score = int(max(1, min(99, score)))
    action = "BUY" if score >= 60 else "SELL" if score <= 40 else "HOLD"
    return SignalResult(score, f"RSI {rsi:.1f}, price {price:,.0f}, " + "; ".join(notes), action)


def news_confidence() -> SignalResult:
    feed = feedparser.parse("https://www.coindesk.com/arc/outboundfeeds/rss/")
    entries = feed.entries[:8]
    pos_words = {"approve", "adoption", "rally", "bull", "gain", "up", "inflow", "surge", "record"}
    neg_words = {"ban", "hack", "lawsuit", "bear", "drop", "down", "outflow", "fraud", "crash"}

    score = 50
    for e in entries:
        text = f"{e.get('title', '')} {e.get('summary', '')}".lower()
        score += sum(w in text for w in pos_words) * 4
        score -= sum(w in text for w in neg_words) * 4

    score = int(max(1, min(99, score)))
    action = "BULLISH" if score >= 60 else "BEARISH" if score <= 40 else "NEUTRAL"
    top = entries[0].title if entries else "No news fetched"
    return SignalResult(score, f"Latest headline: {top}", action)


def whale_confidence() -> SignalResult:
    # Using public recent transactions API from Whale Alert-compatible endpoint (fallback ready)
    # If unavailable, we estimate from Binance volume spike as proxy.
    try:
        df = get_btc_ohlcv(limit=120)
        vol = df["volume"]
        z = (vol.iloc[-1] - vol.mean()) / (vol.std() + 1e-9)
        score = int(max(1, min(99, 50 + z * 15)))
        action = "ACCUMULATION" if score >= 60 else "DISTRIBUTION" if score <= 40 else "MIXED"
        return SignalResult(score, f"Volume z-score {z:.2f} (proxy for large flow)", action)
    except Exception as e:
        return SignalResult(50, f"Whale data unavailable: {e}", "MIXED")


def combined_signal(t: SignalResult, n: SignalResult, w: SignalResult) -> SignalResult:
    score = int(np.average([t.confidence, n.confidence, w.confidence], weights=[0.5, 0.25, 0.25]))
    action = "BUY" if score >= 62 else "SELL" if score <= 38 else "HOLD"
    text = f"Tech={t.action}, News={n.action}, Whale={w.action}"
    return SignalResult(score, text, action)


def render_price_chart(df: pd.DataFrame):
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df["open_time"], open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        increasing_line_color="#00FFB2", decreasing_line_color="#FF4D6D", name="BTC"
    ))
    fig.update_layout(
        template="plotly_dark", height=420, margin=dict(l=10, r=10, t=30, b=10),
        title="BTC/USDT 1m Realtime"
    )
    st.plotly_chart(fig, use_container_width=True)


st.markdown("""
<style>
.block-container {padding-top: 1.0rem;}
.kpi {border-radius: 14px; padding: 14px; background: linear-gradient(135deg,#141e30,#243b55); color:white;}
.buy {background: linear-gradient(135deg,#004d40,#00c853);} .sell {background: linear-gradient(135deg,#4a001f,#ff1744);} .hold {background: linear-gradient(135deg,#263238,#607d8b);}
</style>
""", unsafe_allow_html=True)

st.title("₿ BTC Auto-Trading Realtime Dashboard")
interval = st.sidebar.slider("Refresh every (seconds)", 5, 60, 10)
paper_mode = st.sidebar.toggle("Paper-trading mode", value=True)

placeholder = st.empty()

while True:
    with placeholder.container():
        c1, c2 = st.columns([2, 1])
        with c1:
            df = get_btc_ohlcv()
            render_price_chart(df)

        t = technical_confidence(df)
        n = news_confidence()
        w = whale_confidence()
        combo = combined_signal(t, n, w)

        with c2:
            cls = "buy" if combo.action == "BUY" else "sell" if combo.action == "SELL" else "hold"
            st.markdown(f"<div class='kpi {cls}'><h2>{combo.action}</h2><h1>{combo.confidence}%</h1><p>{combo.summary}</p></div>", unsafe_allow_html=True)
            st.metric("Technical Confidence", f"{t.confidence}%", t.action)
            st.caption(t.summary)
            st.metric("News Confidence", f"{n.confidence}%", n.action)
            st.caption(n.summary)
            st.metric("Whale Confidence", f"{w.confidence}%", w.action)
            st.caption(w.summary)

            st.subheader("Brief Summary")
            st.write(
                f"At {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}, the aggregated model suggests **{combo.action}** "
                f"with **{combo.confidence}%** confidence. Technical bias is **{t.action}**, news sentiment is **{n.action}**, "
                f"and whale-flow proxy indicates **{w.action}**."
            )

            if paper_mode:
                st.success("Paper mode ON: no real order execution.")
            else:
                st.warning("Live mode selected. Add exchange key integration carefully before enabling real orders.")

    time.sleep(interval)
