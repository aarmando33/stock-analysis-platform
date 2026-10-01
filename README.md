# Stock Buy/Sell Monitor price feed

This repository job downloads split-adjusted daily OHLCV history for the 160-ticker core universe plus permanent monitor names LRCX and AMAT after the U.S. market closes.

The primary source is yfinance. If a `TIINGO_API_KEY` repository secret is present, Tiingo fills symbols Yahoo did not return. The job rejects symbols whose last observation trails the newest completed session in the same run.

Outputs are stored in the `stock-price-feed` GitHub Actions artifact:

- `prices_latest.csv`: current validated close, price date, provider, Primary Win%, 52-week Win%, and RSI.
- `price_history.csv.gz`: adjusted daily OHLCV history beginning March 1, 2020.
- `price_audit.json`: expected, valid, stale, and missing counts with timestamps.

The scheduled ChatGPT Stock Buy/Sell Monitor should read the latest successful artifact and refuse to create price-based signals for any ticker whose `price_status` is not `OK`.
