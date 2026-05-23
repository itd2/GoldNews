# BTC Realtime Auto-Trading Dashboard (UI First)

Single-page, colorful, realtime BTC dashboard with three confidence engines:
1. Technical indicators (RSI/SMA/MACD)
2. BTC-related news sentiment
3. Whale-flow proxy signal

## Run
```bash
pip install -r requirements.txt
streamlit run app.py
```

Open the local URL shown by Streamlit (usually `http://localhost:8501`).

## Notes
- Default is **paper mode** (safe, no live orders).
- You can adapt this into real trading by wiring `ccxt` exchange order execution with risk controls.
- Data sources currently use public endpoints and RSS for a no-key quick start.
