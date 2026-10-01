from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import yfinance as yf

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)


def tickers() -> list[str]:
    values = pd.read_csv(ROOT / "tickers.csv")["Symbol"].dropna().astype(str)
    return sorted(set(values.str.strip().str.upper()))


def exclusive_end() -> datetime:
    now = datetime.now(ZoneInfo("America/New_York"))
    day = now.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    if now.weekday() >= 5:
        day -= timedelta(days=now.weekday() - 4)
        return day + timedelta(days=1)
    return day if (now.hour, now.minute) < (16, 15) else day + timedelta(days=1)


def empty() -> pd.DataFrame:
    return pd.DataFrame(columns=["Date", "Symbol", "Open", "High", "Low", "Close", "Volume", "Provider"])


def yahoo(symbols: list[str], start: str, end: datetime) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for offset in range(0, len(symbols), 40):
        chunk = symbols[offset : offset + 40]
        data = None
        for attempt in range(1, 4):
            try:
                data = yf.download(
                    chunk, start=start, end=end, auto_adjust=True, repair=True,
                    group_by="column", threads=True, progress=False, timeout=30,
                )
                if data is not None and not data.empty:
                    break
            except Exception as exc:
                print(f"Yahoo attempt {attempt}/3 failed: {exc}")
            time.sleep(attempt * 3)
        if data is None or data.empty:
            continue
        if isinstance(data.columns, pd.MultiIndex):
            frame = data.stack(level=1, future_stack=True).reset_index()
            frame = frame.rename(columns={"Ticker": "Symbol", "level_1": "Symbol"})
        else:
            frame = data.reset_index()
            frame["Symbol"] = chunk[0]
        frame["Provider"] = "yfinance"
        frames.append(frame)
        time.sleep(1)
    if not frames:
        return empty()
    out = pd.concat(frames, ignore_index=True)
    out["Date"] = pd.to_datetime(out["Date"]).dt.tz_localize(None).dt.normalize()
    out["Symbol"] = out["Symbol"].astype(str).str.upper()
    return out[[c for c in empty().columns if c in out.columns]]


def tiingo(symbols: list[str], start: str, end: datetime) -> pd.DataFrame:
    token = os.getenv("TIINGO_API_KEY", "").strip()
    if not token:
        return empty()
    frames = []
    for symbol in symbols:
        try:
            response = requests.get(
                f"https://api.tiingo.com/tiingo/daily/{symbol}/prices",
                headers={"Authorization": f"Token {token}"},
                params={"startDate": start, "endDate": (end - timedelta(days=1)).date().isoformat()},
                timeout=30,
            )
            response.raise_for_status()
            raw = response.json()
            if not raw:
                continue
            frame = pd.DataFrame(raw).rename(columns={
                "date": "Date", "adjOpen": "Open", "adjHigh": "High",
                "adjLow": "Low", "adjClose": "Close", "adjVolume": "Volume",
            })
            frame["Date"] = pd.to_datetime(frame["Date"], utc=True).dt.tz_convert(None).dt.normalize()
            frame["Symbol"] = symbol
            frame["Provider"] = "tiingo"
            frames.append(frame[[c for c in empty().columns if c in frame.columns]])
        except Exception as exc:
            print(f"Tiingo {symbol} failed: {exc}")
        time.sleep(0.15)
    return pd.concat(frames, ignore_index=True) if frames else empty()


def wilder_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    return 100 - 100 / (1 + gain / loss.replace(0, np.nan))


def main() -> None:
    symbols = tickers()
    end = exclusive_end()
    history = yahoo(symbols, "2020-03-01", end)
    received = set(history["Symbol"].unique()) if not history.empty else set()
    missing = sorted(set(symbols) - received)
    fallback = tiingo(missing, "2020-03-01", end)
    if not fallback.empty:
        history = pd.concat([history, fallback], ignore_index=True)
    history = history.drop_duplicates(["Date", "Symbol"], keep="last").sort_values(["Symbol", "Date"])

    latest_market_date = history["Date"].max() if not history.empty else pd.NaT
    rows = []
    for symbol in symbols:
        frame = history[history["Symbol"].eq(symbol)].copy()
        frame["Close"] = pd.to_numeric(frame["Close"], errors="coerce")
        frame = frame.dropna(subset=["Close"])
        if frame.empty:
            rows.append({"Symbol": symbol, "price_status": "MISSING_PRICE"})
            continue
        last = frame.iloc[-1]
        lag = int((latest_market_date - last["Date"]).days)
        status = "OK" if lag == 0 else "STALE_PRICE"
        close = pd.to_numeric(frame["Close"], errors="coerce")
        low, high, current = close.min(), close.max(), close.iloc[-1]
        win = ((high - current) / (high - low) * 100) if high > low else np.nan
        year = frame[frame["Date"] >= last["Date"] - pd.Timedelta(days=365)]
        ylow, yhigh = year["Close"].min(), year["Close"].max()
        win52 = ((yhigh - current) / (yhigh - ylow) * 100) if yhigh > ylow else np.nan
        rsi = wilder_rsi(close).iloc[-1]
        rows.append({
            "Symbol": symbol, "Current Price": round(float(current), 4),
            "Price Date": last["Date"].date().isoformat(), "Provider": last["Provider"],
            "Price Basis": "adjusted daily OHLC", "price_status": status,
            "Lag Days": lag, "Primary Win%": round(float(win), 2),
            "52W Win%": round(float(win52), 2), "RSI(14)": round(float(rsi), 2),
        })

    audit = pd.DataFrame(rows)
    audit.to_csv(OUT / "prices_latest.csv", index=False)
    history.to_csv(OUT / "price_history.csv.gz", index=False, compression="gzip")
    summary = {
        "expected_tickers": len(symbols), "ok": int(audit["price_status"].eq("OK").sum()),
        "stale": int(audit["price_status"].eq("STALE_PRICE").sum()),
        "missing": int(audit["price_status"].eq("MISSING_PRICE").sum()),
        "latest_market_date": None if pd.isna(latest_market_date) else latest_market_date.date().isoformat(),
        "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
    }
    pd.Series(summary).to_json(OUT / "price_audit.json", indent=2)
    print(summary)
    if summary["ok"] == 0:
        raise SystemExit("No current prices were validated")


if __name__ == "__main__":
    main()
