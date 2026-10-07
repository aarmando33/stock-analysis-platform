from __future__ import annotations

import os
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from buy_sell_monitor import latest_session, rsi

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)
# Keep provider SQLite caches in the writable checkout on restricted hosts.
yf.set_tz_cache_location(str(ROOT / '.yf-cache'))


def tickers() -> list[str]:
    values = pd.read_csv(ROOT / "tickers.csv")["Symbol"].dropna().astype(str)
    return sorted(set(values.str.strip().str.upper()))


def exclusive_end(now=None) -> datetime:
    return pd.Timestamp(latest_session(now)).to_pydatetime() + timedelta(days=1)


def empty() -> pd.DataFrame:
    return pd.DataFrame(columns=["Date", "Symbol", "Open", "High", "Low", "Close", "Volume", "Provider"])


def provider_symbols(symbols, end):
    """Keep monitored identities intact while recording sourced symbol changes."""
    path=ROOT/'symbol_aliases.csv'
    mapping={s:s for s in symbols}
    if path.exists():
        aliases=pd.read_csv(path)
        if aliases['Monitor Symbol'].duplicated().any(): raise ValueError('Duplicate symbol alias')
        for _,row in aliases.iterrows():
            if row['Monitor Symbol'] in mapping and pd.Timestamp(end)-pd.Timedelta(days=1)>=pd.Timestamp(row['Effective From']):
                if pd.isna(row['Source']) or not str(row['Source']).strip(): raise ValueError('Alias source required')
                mapping[row['Monitor Symbol']]=row['Provider Symbol']
    if len(set(mapping.values()))!=len(mapping): raise ValueError('Provider aliases collide')
    return mapping


def yahoo(symbols: list[str], start: str, end: datetime, *, _serial_retry=False) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    mapping=provider_symbols(symbols,end)
    reverse={value:key for key,value in mapping.items()}
    for offset in range(0, len(symbols), 40):
        chunk = [mapping[s] for s in symbols[offset : offset + 40]]
        data = None
        for attempt in range(1, 4):
            try:
                data = yf.download(
                    chunk, start=start, end=end, auto_adjust=True, repair=True,
                    group_by="column", threads=not _serial_retry, progress=False, timeout=30,
                )
                if data is not None and not data.empty and data["Close"].notna().to_numpy().any():
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
        frame['Provider Symbol']=frame['Symbol']
        frame['Symbol']=frame['Symbol'].map(reverse)
        frames.append(frame)
        time.sleep(1)
    out = pd.concat(frames, ignore_index=True) if frames else empty()
    # A nonempty batch can hide individual failures as all-NaN columns.
    # Retry those identities independently, without competing SQLite cache writes.
    if not _serial_retry:
        available = set(out.loc[pd.to_numeric(out["Close"], errors="coerce").notna(), "Symbol"])
        for symbol in symbols:
            if symbol in available:
                continue
            print(f"Yahoo {symbol}: retrying missing history serially")
            recovered = yahoo([symbol], start, end, _serial_retry=True)
            if not recovered.empty and recovered["Close"].notna().any():
                out = pd.concat([out.loc[out["Symbol"].ne(symbol)], recovered], ignore_index=True)
    out["Date"] = pd.to_datetime(out["Date"]).dt.tz_localize(None).dt.normalize()
    out["Symbol"] = out["Symbol"].astype(str).str.upper()
    return out[[c for c in [*empty().columns,'Provider Symbol'] if c in out.columns]]


def tiingo(symbols: list[str], start: str, end: datetime) -> pd.DataFrame:
    token = os.getenv("TIINGO_API_KEY", "").strip()
    if not token:
        return empty()
    frames = []
    mapping=provider_symbols(symbols,end)
    for symbol in symbols:
        try:
            response = requests.get(
                f"https://api.tiingo.com/tiingo/daily/{mapping[symbol]}/prices",
                headers={"Authorization": f"Token {token}"},
                params={"startDate": start, "endDate": (end - timedelta(days=1)).date().isoformat()},
                timeout=30,
            )
            response.raise_for_status()
            raw = response.json()
            if not raw:
                continue
            # Tiingo returns raw and adjusted fields together. Select adjusted
            # fields before renaming; otherwise duplicate OHLC names are created.
            raw_frame = pd.DataFrame(raw)
            frame = raw_frame[["date", "adjOpen", "adjHigh", "adjLow", "adjClose", "adjVolume"]].rename(columns={
                "date": "Date", "adjOpen": "Open", "adjHigh": "High",
                "adjLow": "Low", "adjClose": "Close", "adjVolume": "Volume",
            })
            frame["Date"] = pd.to_datetime(frame["Date"], utc=True).dt.tz_convert(None).dt.normalize()
            frame["Symbol"] = symbol
            frame['Provider Symbol']=mapping[symbol]
            frame["Provider"] = "tiingo"
            frames.append(frame[[c for c in [*empty().columns,'Provider Symbol'] if c in frame.columns]])
        except Exception as exc:
            print(f"Tiingo {symbol} failed: {exc}")
        time.sleep(0.15)
    return pd.concat(frames, ignore_index=True) if frames else empty()


def wilder_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    return rsi(series, period)


def audit_history(history, symbols, session, now=None):
    """Validate against the exchange session, never the providers' newest row."""
    history = history.copy()
    current_time=pd.Timestamp.now(tz='UTC') if now is None else pd.Timestamp(now)
    if current_time.tzinfo is None: raise ValueError('Timezone-aware audit time required')
    history['Date'] = pd.to_datetime(history['Date'], errors='coerce')
    for column in ['Open', 'High', 'Low', 'Close', 'Volume']:
        history[column] = pd.to_numeric(history[column], errors='coerce')
    rows = []
    for symbol in symbols:
        frame = history[history.Symbol.eq(symbol)].sort_values('Date')
        frame = frame.dropna(subset=['Close'])
        if frame.empty:
            rows.append({'Symbol':symbol, 'price_status':'MISSING_PRICE'})
            continue
        last = frame.iloc[-1]
        values = frame[['Open','High','Low','Close']]
        tol = 1e-10 * values.abs().max(axis=1).clip(lower=1)
        invalid = (frame.Date.isna().any() or frame.Date.duplicated().any()
                   or not np.isfinite(values.to_numpy()).all() or (values <= 0).any().any()
                   or ((frame.High+tol < frame.Low) | (frame.High+tol < frame.Close)
                       | (frame.Low-tol > frame.Close) | (frame.High+tol < frame.Open)
                       | (frame.Low-tol > frame.Open)).any())
        status = ('INVALID_HISTORY' if invalid else 'FUTURE_PRICE' if last.Date > pd.Timestamp(session)
                  else 'OK' if last.Date == pd.Timestamp(session) else 'STALE_PRICE')
        if status=='OK' and symbol.endswith('-USD') and current_time<pd.Timestamp(session,tz='UTC')+pd.Timedelta(days=1):
            status='UNCOMPLETED_CRYPTO_CANDLE'
        close = frame.Close
        low, high, current = close.min(), close.max(), close.iloc[-1]
        year = frame[frame.Date >= pd.Timestamp(session)-pd.Timedelta(days=365)]
        ylow, yhigh = year.Close.min(), year.Close.max()
        rows.append({'Symbol':symbol, 'Current Price':round(float(current),4),
                     'Price Date':last.Date.date().isoformat() if pd.notna(last.Date) else None,
                     'Provider':last.Provider, 'Price Basis':'adjusted daily OHLC', 'price_status':status,
                     'Provider Symbol':last.get('Provider Symbol',symbol),
                     'Lag Days':int((pd.Timestamp(session)-last.Date).days) if pd.notna(last.Date) else None,
                     'Primary Win%':round(float((high-current)/(high-low)*100),2) if status=='OK' and high>low else np.nan,
                     '52W Win%':round(float((yhigh-current)/(yhigh-ylow)*100),2) if status=='OK' and yhigh>ylow else np.nan,
                     'RSI(14)':float(wilder_rsi(close).iloc[-1]) if status=='OK' else np.nan})
    return pd.DataFrame(rows)


def main() -> None:
    symbols = tickers()
    end = exclusive_end()
    session = (end-timedelta(days=1)).date().isoformat()
    history = yahoo(symbols, "2020-03-01", end)
    preliminary = audit_history(history, symbols, session)
    missing = preliminary.loc[preliminary.price_status.ne('OK'),'Symbol'].tolist()
    fallback = tiingo(missing, "2020-03-01", end)
    if not fallback.empty:
        replacement = audit_history(fallback, missing, session)
        usable = replacement.loc[replacement.price_status.eq('OK'),'Symbol'].tolist()
        # Replace complete histories, so one ticker never mixes adjustment bases.
        history = pd.concat([history[~history.Symbol.isin(usable)], fallback[fallback.Symbol.isin(usable)]], ignore_index=True)
    history = history.sort_values(["Symbol", "Date"])

    latest_market_date = history["Date"].max() if not history.empty else pd.NaT
    audit = audit_history(history, symbols, session)
    audit.to_csv(OUT / "prices_latest.csv", index=False)
    history.to_csv(OUT / "price_history.csv.gz", index=False, compression="gzip")
    summary = {
        "expected_tickers": len(symbols), "ok": int(audit["price_status"].eq("OK").sum()),
        "stale": int(audit["price_status"].eq("STALE_PRICE").sum()),
        "missing": int(audit["price_status"].eq("MISSING_PRICE").sum()),
        "invalid": int(audit["price_status"].isin(['INVALID_HISTORY','FUTURE_PRICE','UNCOMPLETED_CRYPTO_CANDLE']).sum()),
        "expected_market_date": session,
        "price_basis": "adjusted daily OHLC",
        "failed_symbols": audit.loc[audit.price_status.ne('OK'),'Symbol'].tolist(),
        "latest_market_date": None if pd.isna(latest_market_date) else latest_market_date.date().isoformat(),
        "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
    }
    (OUT / 'price_audit.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(summary)
    if summary['latest_market_date'] != session:
        raise SystemExit('FEED_SESSION_MISMATCH: no current-session artifact available')
    if summary["ok"] / len(symbols) < 0.90:
        raise SystemExit("Price coverage below 90%; refusing to mark this run successful")


if __name__ == "__main__":
    main()

