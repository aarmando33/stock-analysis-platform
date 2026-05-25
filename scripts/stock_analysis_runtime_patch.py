"""Runtime reliability patch layer for the stock analysis scanner."""

from __future__ import annotations

import importlib.util
from pathlib import Path


_LEGACY_PATH = Path(__file__).with_name("_stock_analysis_legacy.py")
_SPEC = importlib.util.spec_from_file_location("_stock_analysis_legacy", _LEGACY_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"Could not load scanner implementation from {_LEGACY_PATH}")

scanner = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(scanner)

pd = scanner.pd
np = scanner.np

_original_add_core_value_calculations = scanner.add_core_value_calculations
_original_build_v10_6_views = scanner.build_v10_6_views_from_filtered_master
_original_finalize_slim_workbook_views = scanner.finalize_slim_workbook_views
_original_get_column_dictionary = scanner.get_column_dictionary


def yfinance_download_to_long(
    tickers: list[str],
    start,
    end,
    chunk_size: int = 100,
    delay: float = 1.5,
    max_attempts: int = 2,
):
    frames = []
    tickers = sorted({scanner.normalize_symbol(t) for t in tickers if str(t).strip()})
    chunks = list(scanner.chunk_list(tickers, chunk_size))

    for i, chunk in enumerate(chunks, start=1):
        print(f"Downloading price chunk {i}/{len(chunks)} | {len(chunk)} tickers")
        data = None
        last_error = None
        for attempt in range(1, max_attempts + 1):
            try:
                data = scanner.yf.download(
                    tickers=chunk,
                    start=start,
                    end=end,
                    auto_adjust=False,
                    progress=False,
                    threads=True,
                    group_by="column",
                )
                if data is None or data.empty:
                    raise ValueError("empty response")
                break
            except Exception as exc:
                last_error = exc
                if attempt < max_attempts:
                    print(f"Price chunk {i} attempt {attempt} failed: {exc}. Retrying.")
                    scanner.time.sleep(delay * attempt)

        if data is None or data.empty:
            print(f"Price chunk {i} failed after {max_attempts} attempts: {last_error}")
            scanner.time.sleep(delay)
            continue

        try:
            if isinstance(data.columns, pd.MultiIndex):
                long = data.stack(level=1, future_stack=True).reset_index()
                for ticker_col in ["level_1", "Ticker", "Symbols"]:
                    if ticker_col in long.columns:
                        long = long.rename(columns={ticker_col: "Symbol"})
                        break
            else:
                long = data.reset_index()
                long["Symbol"] = chunk[0]

            long["Symbol"] = long["Symbol"].map(scanner.normalize_symbol)
            long["Date"] = pd.to_datetime(long["Date"])
            wanted = ["Date", "Symbol", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
            frames.append(long[[col for col in wanted if col in long.columns]])
        except Exception as exc:
            print(f"Price chunk {i} conversion failed: {exc}")
        scanner.time.sleep(delay)

    columns = ["Date", "Symbol", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
    if not frames:
        out = pd.DataFrame(columns=columns)
    else:
        out = pd.concat(frames, ignore_index=True)
        out = out.dropna(subset=["Date", "Symbol"])
        out = out.drop_duplicates(["Date", "Symbol"], keep="last")
        out = out.sort_values(["Symbol", "Date"]).reset_index(drop=True)

    downloaded_symbols = sorted(set(out["Symbol"].dropna().unique())) if "Symbol" in out.columns else []
    out.attrs["downloaded_symbols"] = downloaded_symbols
    out.attrs["failed_symbols"] = sorted(set(tickers) - set(downloaded_symbols))
    return out


def load_or_update_prices(
    tickers: list[str],
    universe: str,
    start_date: str,
    end_date,
    mode: str = "incremental",
    chunk_size: int = 100,
    delay: float = 1.5,
):
    tickers = sorted({scanner.normalize_symbol(t) for t in tickers})
    cached = scanner.read_prices_cache(universe)

    if mode == "full" or cached.empty:
        print("Price mode: FULL download")
        prices = yfinance_download_to_long(tickers, start_date, end_date, chunk_size, delay)
        failed = prices.attrs.get("failed_symbols", [])
        scanner.LAST_REFRESH_FAILED_SYMBOLS = failed
        path = scanner.write_prices_cache(prices, universe)
        print(f"Saved price cache: {path}")
        return prices

    cached["Date"] = pd.to_datetime(cached["Date"])
    cached["Symbol"] = cached["Symbol"].map(scanner.normalize_symbol)
    cached_symbols = set(cached["Symbol"].dropna().unique())
    missing_symbols = sorted(set(tickers) - cached_symbols)
    frames = [cached]
    newly_downloaded = set()

    if missing_symbols:
        print(f"Found {len(missing_symbols)} tickers missing from price cache. Downloading full history for those.")
        missing_prices = yfinance_download_to_long(missing_symbols, start_date, end_date, chunk_size, delay)
        newly_downloaded = set(missing_prices.attrs.get("downloaded_symbols", []))
        frames.append(missing_prices)

    refresh_start = max(pd.to_datetime(start_date), cached["Date"].max() - pd.Timedelta(days=7))
    print(f"Price mode: INCREMENTAL refresh from {refresh_start.date()} to {end_date.date()}")
    refresh_prices = yfinance_download_to_long(tickers, refresh_start, end_date, chunk_size, delay)
    frames.append(refresh_prices)

    prices = pd.concat(frames, ignore_index=True)
    prices = prices.drop_duplicates(["Date", "Symbol"], keep="last").sort_values(["Symbol", "Date"])
    refreshed = set(refresh_prices.attrs.get("downloaded_symbols", [])) | newly_downloaded
    scanner.LAST_REFRESH_FAILED_SYMBOLS = sorted(set(tickers) - refreshed)
    path = scanner.write_prices_cache(prices, universe)
    print(f"Saved price cache: {path}")
    return prices.reset_index(drop=True)


def read_fundamentals_cache(universe: str):
    path = scanner.fundamentals_cache_path(universe)
    if not path.exists():
        return pd.DataFrame()
    try:
        payload = scanner.json.loads(path.read_text())
        records = payload.get("records", []) if isinstance(payload, dict) else []
        df = pd.DataFrame(records)
        if not df.empty and "Symbol" in df.columns:
            df["Symbol"] = df["Symbol"].map(scanner.normalize_symbol)
            if "fundamentals_fetched_at" not in df.columns:
                df["fundamentals_fetched_at"] = payload.get("fetched_at")
        return df
    except Exception as exc:
        print(f"Warning: failed to read fundamentals cache: {exc}")
        return pd.DataFrame()


def write_fundamentals_cache(df, universe: str) -> None:
    payload = {
        "fetched_at": pd.Timestamp.utcnow().isoformat(),
        "records": df.replace({np.nan: None}).to_dict(orient="records"),
    }
    scanner.fundamentals_cache_path(universe).write_text(scanner.json.dumps(payload, indent=2))


def fetch_fundamentals(tickers: list[str], delay: float = 0.15, max_attempts: int = 2):
    rows = []
    for i, symbol in enumerate(tickers, start=1):
        print(f"Fetching fundamentals {i}/{len(tickers)}: {symbol}")
        info = None
        last_error = None
        for attempt in range(1, max_attempts + 1):
            try:
                info = scanner.yf.Ticker(symbol).get_info()
                if not isinstance(info, dict) or not info:
                    raise ValueError("empty response")
                break
            except Exception as exc:
                last_error = exc
                if attempt < max_attempts:
                    scanner.time.sleep(delay * attempt)
        if not info:
            print(f"Fundamentals failed for {symbol} after {max_attempts} attempts: {last_error}")
            scanner.time.sleep(delay)
            continue

        market_cap = info.get("marketCap")
        rows.append(
            {
                "Symbol": symbol,
                "fundamentals_fetched_at": pd.Timestamp.utcnow().isoformat(),
                "Marketcap": market_cap,
                "capMil": (market_cap or 0) / 1e6 if market_cap is not None else np.nan,
                "AvgVol10d": info.get("averageDailyVolume10Day"),
                "debtToEquity": info.get("debtToEquity"),
                "shortRatio": info.get("shortRatio"),
                "priceToBook": info.get("priceToBook"),
                "revenueGrowth": info.get("revenueGrowth"),
                "freeCashFlow": info.get("freeCashflow"),
                "returnOnEquity": info.get("returnOnEquity"),
                "Security_yf": info.get("longName"),
                "Sector_yf": info.get("sector"),
                "Sub_Sector_yf": info.get("industry"),
                "description": info.get("longBusinessSummary", ""),
            }
        )
        scanner.time.sleep(delay)
    return pd.DataFrame(rows)


def load_or_update_fundamentals(
    tickers: list[str],
    universe: str,
    mode: str = "missing",
    max_age_days: int = 7,
):
    tickers = sorted({scanner.normalize_symbol(t) for t in tickers})
    cached = read_fundamentals_cache(universe)
    if mode == "skip":
        print("Fundamentals mode: SKIP remote fetch")
        return cached

    if mode == "force" or cached.empty:
        print("Fundamentals mode: FORCE/full fetch")
        fresh = fetch_fundamentals(tickers)
        if mode == "force" and not cached.empty:
            succeeded = set(fresh["Symbol"].dropna()) if "Symbol" in fresh.columns else set()
            failed = sorted(set(tickers) - succeeded)
            if failed:
                print(f"Retaining cached fundamentals for {len(failed)} symbols whose refresh failed.")
            fresh = pd.concat([cached[~cached["Symbol"].isin(succeeded)], fresh], ignore_index=True)
        write_fundamentals_cache(fresh, universe)
        return fresh

    important = [
        "Marketcap", "debtToEquity", "priceToBook", "revenueGrowth",
        "freeCashFlow", "returnOnEquity", "description",
    ]
    for col in important:
        if col not in cached.columns:
            cached[col] = np.nan
    if "fundamentals_fetched_at" not in cached.columns:
        cached["fundamentals_fetched_at"] = None

    cached_symbols = set(cached["Symbol"].dropna().unique())
    missing = sorted(set(tickers) - cached_symbols)
    weak = cached.loc[
        cached[important].isna().all(axis=1)
        | cached[["revenueGrowth", "freeCashFlow", "returnOnEquity"]].isna().all(axis=1),
        "Symbol",
    ].dropna().unique().tolist()
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=max_age_days)
    fetched_at = pd.to_datetime(cached["fundamentals_fetched_at"], errors="coerce", utc=True)
    expired = cached.loc[fetched_at.isna() | fetched_at.lt(cutoff), "Symbol"].dropna().unique().tolist()
    to_fetch = sorted(set(missing + weak + expired))
    print(f"Fundamentals mode: MISSING/expired only | need {len(to_fetch)} tickers")

    if not to_fetch:
        combined = cached
    else:
        fresh = fetch_fundamentals(to_fetch)
        succeeded = set(fresh["Symbol"].dropna()) if "Symbol" in fresh.columns else set()
        failed = sorted(set(to_fetch) - succeeded)
        if failed:
            print(f"Retaining cached fundamentals where available for {len(failed)} failed refreshes.")
        combined = pd.concat([cached[~cached["Symbol"].isin(succeeded)], fresh], ignore_index=True)

    combined = combined.drop_duplicates("Symbol", keep="last")
    write_fundamentals_cache(combined, universe)
    return combined


def add_core_value_calculations(dfagg):
    out = _original_add_core_value_calculations(dfagg)
    out["latest_price_date"] = pd.to_datetime(out.get("Date"), errors="coerce")
    failed = set(getattr(scanner, "LAST_REFRESH_FAILED_SYMBOLS", []))
    stale = out["Symbol"].isin(failed) & out["last_close"].notna()
    if stale.any():
        out.loc[stale, "price_status"] = "STALE_PRICE"
        print(f"WARNING: {int(stale.sum())} symbols retained cached price data after refresh failed; marked STALE_PRICE.")
    return out


def build_v10_6_views_from_filtered_master(dfagg_enhanced, enhanced_sheet_dict, min_market_cap=2000):
    if not enhanced_sheet_dict:
        return {}
    return _original_build_v10_6_views(dfagg_enhanced, enhanced_sheet_dict, min_market_cap)


def finalize_slim_workbook_views(views, dfagg):
    if "Summary" not in views and "High Conviction" not in views:
        return views
    return _original_finalize_slim_workbook_views(views, dfagg)


def get_column_dictionary(columns):
    dictionary = _original_get_column_dictionary(columns)
    if "Column" in dictionary.columns:
        mask = dictionary["Column"].eq("price_status")
        if mask.any():
            dictionary.loc[mask, "What It Measures"] = "Whether refreshed price data is current."
            dictionary.loc[mask, "How Calculated"] = (
                "OK after successful refresh; STALE_PRICE when cached price remains after refresh failure; "
                "MISSING_PRICE when no usable price exists."
            )
            dictionary.loc[mask, "How To Read / Use"] = "Rank only OK rows; review stale/missing rows in Download Audit."
    return dictionary


def apply_patches() -> None:
    scanner.LAST_REFRESH_FAILED_SYMBOLS = []
    scanner.yfinance_download_to_long = yfinance_download_to_long
    scanner.load_or_update_prices = load_or_update_prices
    scanner.read_fundamentals_cache = read_fundamentals_cache
    scanner.write_fundamentals_cache = write_fundamentals_cache
    scanner.fetch_fundamentals = fetch_fundamentals
    scanner.load_or_update_fundamentals = load_or_update_fundamentals
    scanner.add_core_value_calculations = add_core_value_calculations
    scanner.build_v10_6_views_from_filtered_master = build_v10_6_views_from_filtered_master
    scanner.finalize_slim_workbook_views = finalize_slim_workbook_views
    scanner.get_column_dictionary = get_column_dictionary


def run_patched_main() -> None:
    scanner.main()


apply_patches()
