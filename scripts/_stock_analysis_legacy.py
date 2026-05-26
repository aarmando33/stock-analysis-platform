# stock_analysis_v10_6_sector_summary.py
# Updates:
# - Adds Sector Summary sheet with hot/cold sector calculations
# - Adds sector_temperature and sector_hot_score to exported stock sheets
# - Hot/cold is calculated from your run data, not pulled externally
#
# stock_analysis_v10_5_formatting_dictionary.py
# Updates:
# - Moves Marketcap and capMil near beginning, before price columns
# - Expands Column Dictionary descriptions
# - Highlights sorted column headers in each Excel sheet
#
# stock_analysis_v10_4_stable_rank_views.py
# Fix:
# - Rewrites make_ranked_views defensively
# - Prevents missing ranking-column KeyErrors, including regular_range_score
# - Keeps internal score columns for ranking and cleans columns only at export
#
# stock_analysis_v10_3_rank_then_clean.py
# Fix:
# - Prevents KeyError: regular_range_score
# - Keeps internal score columns for ranking
# - Cleans/hides score component columns only during final export
#
# stock_analysis_v10_2_clean_columns.py
# Update:
# - Cleaner exported columns
# - Actual price columns before performance columns
# - Hides internal component score columns from workbook/CSVs
# - Keeps only main scores: final_watch_score, value_range_score, drop_alert_score
#
# stock_analysis_v9_7_clean_patch.py
# Clean patch:
# - Compiled successfully before download
# - Fixes AttributeError: numpy.ndarray has no attribute 'between'
# - Keeps encoding-safe flagged_watch.csv reader
# - Defaults ranking filter to market cap >= $2B
# - Keeps full master output unfiltered
# - Prints runtime stats to terminal only; no debug/profile files created
#
# stock_analysis_v9_5_error_proof.py
# Error-proof patch:
# - optional ticker files like config/flagged_watch.csv cannot crash the run
# - handles Windows cp1252 / latin1 / bad characters
# - falls back to extra_tickers if watchlist file is bad
#
# stock_analysis_v9_4_vscode_safe.py
# This version is safe to run from VS Code even if VS Code uses an Interactive/ipykernel backend.
# Defaults:
#   universe=all
#   mode=incremental
#   fundamentals_mode=missing
#
# Recommended terminal command:
#   py stock_analysis_v9_4_vscode_safe.py --universe all --mode incremental --fundamentals-mode missing
#
# You can also just click "Run Python File" in VS Code; it will use defaults.

"""
stock_analysis_v10_clean_outputs.py

Purpose
-------
Automated stock scanner that:
1. Handles S&P 500, Nasdaq, Russell 2000, NYSE, Extra/watchlist, or all universes.
   Extra/watchlist tickers are force-included by default so they cannot accidentally drop out.
2. Caches price history so nightly runs do not have to redownload everything from 2020.
3. Preserves your main calculations:
   - price_suggest_80
   - win%
   - price_suggest_80_covid
   - win%_covid
4. Creates combined ranked views:
   - Regular Range Opportunity = price_suggest_80 + win%, ranked mainly by win%
   - Covid Range Opportunity = price_suggest_80_covid + win%_covid, ranked mainly by win%_covid
5. Adds a Table of Contents and Column Dictionary inside the Excel workbook.

Run examples
------------
py stock_analysis_v10_clean_outputs.py --universe all --mode incremental
py stock_analysis_v10_clean_outputs.py --universe sp500 --mode incremental
py stock_analysis_v10_clean_outputs.py --universe nasdaq --mode incremental
py stock_analysis_v10_clean_outputs.py --universe extra --mode incremental
py stock_analysis_v10_clean_outputs.py --universe all --mode full

Optional useful flags
---------------------
--start-date 2020-03-01
--chunk-size 100
--delay 1.5
--fundamentals-mode missing    # missing, force, skip
--min-market-cap 2000       # in millions; 2000 = $2B

Outputs
-------
outputs/stock_rankings.xlsx
outputs/top_high_conviction.csv
outputs/top_watchlist_candidates.csv
outputs/top_recent_drops.csv

Notes
-----
This script is a scanner/ranker, not financial advice. Use the output as a research starting point.
"""

from __future__ import annotations

import argparse
import sys
import json
import math
import os
import re
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Literal

import numpy as np
import pandas as pd
import requests
import yfinance as yf


# =============================================================================
# FOLDERS / PROFILING
# =============================================================================

CACHE_DIR = Path("cache")
OUTPUT_DIR = Path("outputs")
CONFIG_DIR = Path("config")
INDEX_PRIORITY = ["S&P 500", "NYSE", "Nasdaq", "Russell 2000", "Extra"]
OUTPUT_WORKBOOK = OUTPUT_DIR / "stock_rankings.xlsx"


for _p in [CACHE_DIR, OUTPUT_DIR, CONFIG_DIR]:
    _p.mkdir(parents=True, exist_ok=True)

PROFILE_ROWS: list[dict] = []


@contextmanager
def timer(step_name: str):
    start = time.perf_counter()
    print(f"\n▶ START: {step_name}")
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        PROFILE_ROWS.append(
            {"step": step_name, "seconds": round(elapsed, 2), "minutes": round(elapsed / 60, 2)}
        )
        print(f"✅ END: {step_name} | {elapsed:.2f} seconds")


def save_profile_report(path: Path | None = None) -> None:
    """Print runtime stats to terminal only. No debug/profile file is created."""
    if not PROFILE_ROWS:
        return
    profile_df = pd.DataFrame(PROFILE_ROWS).sort_values("seconds", ascending=False)
    print("\n========== RUN TIME STATS ==========")
    print(profile_df.to_string(index=False))
    print("====================================")


# =============================================================================
# CONFIG / UNIVERSE
# =============================================================================

DEFAULT_EXTRA_TICKERS = [
    # Original extras / watchlist style names from prior versions
    "ZM", "PLAB", "ALB", "PTLO", "GRMN", "WING", "MODG", "COLB", "CELH",
    "CLOV", "SPWR", "CNXC", "VERB", "SHOP", "JD", "ROKU", "AAP", "AACG",
    "U", "RDFN", "FUBO", "ARKK", "COIN", "RUN", "XPEV", "ABT", "ACN",
    "ATVI", "AMD", "AES", "AFL", "A", "ALK", "AEE", "AAL", "AEP",
    "ABC", "ACGL", "AJG", "AIZ", "BTC-USD", "DXC", "RE", "FRT", "FI",
    "HST", "LNC", "LIN", "LKQ", "NWL", "NIO", "OMF", "OGN", "SEE",
    "SPY", "URI", "PLTR", "ILMN",
    # Larger watchlist from v8
    "DECK", "PSKY", "PAGS", "STZ", "TGT", "LW", "GLOB", "EL", "RIVN",
    "OKTA", "NVCR", "PYPL", "AMT", "DG", "GPN", "DXCM", "DIS", "BXP",
    "ALGN", "IFF", "NKE", "LUV", "NVDA", "AMZN", "AAPL", "META", "MSFT",
    "TSLA", "GBTC", "C", "JPM", "OXY", "CRSP", "CGC", "GOOG", "LEN",
    "ACHR", "RGTI", "MRVL", "UNH", "LULU", "NFE", "QBTS", "QUBT", "XOM",
    "GFAI", "AI", "ORCL", "ARM", "CAVA", "PLUG", "BEAT", "XRP-USD", "TSM",
    "SMCI", "BYND", "QXO", "WIX", "EPAM", "INTC", "DAVA", "LNG", "FLR",
    "IONQ", "CRM", "SOUN", "KMX", "GMED", "TECK", "FMST", "CAG", "IT",
    "FTV", "ADBE", "SWKS", "HUBS", "FTAI", "WH", "FIG", "VFC", "NFLX",
    "ONTO", "CDNS", "CRCL", "FMC", "MP", "CMG", "JNJ", "UBER", "W", "VSCO",
    "TAP", "SBUX", "MCD", "WMT", "COST", "CRWD", "AVGO", "TEAM", "SNOW",
    "ISRG", "JHX", "ENPH", "SNPS", "IOT", "TCNNF", "GTBIF", "CURLF",
    "MNMD", "GRWG", "VFF", "CMPS", "CRON", "ACB", "TLRY", "LTC-USD",
    "ETH-USD",
]


def normalize_symbol(s: str) -> str:
    return str(s).strip().upper().replace(".", "-").replace("\n", "")




def ordered_index_membership(values) -> str:
    """Return index membership in preferred review order: S&P 500, NYSE, Nasdaq, Russell, Extra."""
    parts = []
    for value in values:
        if pd.isna(value):
            continue
        for p in str(value).split(","):
            p = p.strip()
            if p and p.lower() != "nan":
                parts.append(p)
    unique = set(parts)
    ordered = [p for p in INDEX_PRIORITY if p in unique]
    ordered += sorted(unique - set(ordered))
    return ", ".join(ordered)


def primary_index_origin(index_value) -> str:
    """Return the first/main origin based on preferred index order."""
    membership = ordered_index_membership([index_value])
    return membership.split(", ")[0] if membership else "Unknown"


def read_optional_ticker_file(path) -> list:
    """
    Error-proof optional ticker-file reader.

    Handles missing files, empty files, UTF-8, UTF-8-SIG, Windows cp1252,
    Latin-1, bad characters, CSV/TXT, and Excel files.

    If the file cannot be read, it returns [] instead of stopping the script.
    """
    from pathlib import Path
    import pandas as pd
    import re

    path = Path(path)

    if not path.exists():
        return []

    def _clean_symbol(x):
        try:
            s = str(x).strip().upper()
            s = s.replace(".", "-")
            s = s.replace('"', "").replace("'", "")
            s = re.sub(r"[^A-Z0-9\-\^=]", "", s)
            if not s:
                return None
            if s in {"SYMBOL", "TICKER", "TICKERS", "NAN", "NONE"}:
                return None
            return s
        except Exception:
            return None

    try:
        if path.suffix.lower() in [".xlsx", ".xls"]:
            try:
                df = pd.read_excel(path, header=None)
                vals = df.values.ravel().tolist()
                out = [_clean_symbol(v) for v in vals]
                return sorted(set([x for x in out if x]))
            except Exception as e:
                print(f"WARNING: Could not read optional ticker Excel file {path}: {e}")
                return []

        if path.suffix.lower() in [".csv", ".txt"]:
            encodings_to_try = ["utf-8", "utf-8-sig", "cp1252", "latin1"]

            last_error = None
            for enc in encodings_to_try:
                try:
                    df = pd.read_csv(
                        path,
                        header=None,
                        dtype=str,
                        encoding=enc,
                        encoding_errors="replace",
                        engine="python",
                        sep=None,
                        on_bad_lines="skip"
                    )

                    vals = df.values.ravel().tolist()
                    out = [_clean_symbol(v) for v in vals]
                    out = sorted(set([x for x in out if x]))

                    if out:
                        print(f"Loaded {len(out)} tickers from {path} using encoding={enc}")
                    return out

                except Exception as e:
                    last_error = e
                    continue

            try:
                raw_text = path.read_text(encoding="latin1", errors="replace")
                pieces = re.split(r"[\s,;|]+", raw_text)
                out = [_clean_symbol(v) for v in pieces]
                out = sorted(set([x for x in out if x]))
                if out:
                    print(f"Loaded {len(out)} tickers from {path} using manual fallback")
                return out
            except Exception as e:
                print(f"WARNING: Could not read optional ticker file {path}. Last error: {last_error}. Fallback error: {e}")
                return []

        return []

    except Exception as e:
        print(f"WARNING: Optional ticker file failed but run will continue: {path} | {e}")
        return []



def load_sp500() -> pd.DataFrame:
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    headers = {"User-Agent": "Mozilla/5.0"}
    html = requests.get(url, headers=headers, timeout=30).text
    sp500 = pd.read_html(html)[0]
    sp500 = sp500.rename(
        columns={"GICS Sector": "Sector", "GICS Sub-Industry": "Sub_Sector"}
    )
    sp500["Symbol"] = sp500["Symbol"].map(normalize_symbol)
    sp500["Index"] = "S&P 500"
    keep = ["Symbol", "Security", "Sector", "Sub_Sector", "Index"]
    return sp500[keep].drop_duplicates("Symbol")


def load_nasdaq() -> pd.DataFrame:
    urls = [
        "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
        "ftp://ftp.nasdaqtrader.com/SymbolDirectory/nasdaqlisted.txt",
    ]
    last_err = None
    for url in urls:
        try:
            df = pd.read_csv(url, sep="|")
            df = df[df["Symbol"].notna()]
            df = df[df["Symbol"] != "File Creation Time"]
            df["Symbol"] = df["Symbol"].map(normalize_symbol)
            # Keep cleaner common stock-like symbols; this reduces bad yfinance calls.
            df = df[df["Symbol"].str.match(r"^[A-Z]{1,5}(-[A-Z])?$|^[A-Z]+-USD$", na=False)]
            df = df[~df["Symbol"].str.endswith(tuple(["W", "U", "R", "P"]))]
            df = df.rename(columns={"Security Name": "Security"})
            df["Index"] = "Nasdaq"
            for col in ["Sector", "Sub_Sector"]:
                if col not in df.columns:
                    df[col] = np.nan
            return df[["Symbol", "Security", "Sector", "Sub_Sector", "Index"]].drop_duplicates("Symbol")
        except Exception as e:
            last_err = e
    print(f"Warning: failed to load Nasdaq list: {last_err}")
    return pd.DataFrame(columns=["Symbol", "Security", "Sector", "Sub_Sector", "Index"])


def load_russell2000() -> pd.DataFrame:
    url = "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/1467271812596.ajax?fileType=csv&fileName=IWM_holdings&dataType=fund"
    try:
        df = pd.read_csv(url, skiprows=9)
        if "Ticker" not in df.columns:
            raise ValueError("Ticker column not found in IWM holdings file")
        df = df.rename(columns={"Ticker": "Symbol", "Name": "Security", "Sector": "Sector"})
        df["Symbol"] = df["Symbol"].map(normalize_symbol)
        df = df[df["Symbol"].str.match(r"^[A-Z]{1,5}(-[A-Z])?$", na=False)]
        df["Index"] = "Russell 2000"
        if "Sub_Sector" not in df.columns:
            df["Sub_Sector"] = np.nan
        return df[["Symbol", "Security", "Sector", "Sub_Sector", "Index"]].drop_duplicates("Symbol")
    except Exception as e:
        print(f"Warning: failed to load Russell 2000 list: {e}")
        return pd.DataFrame(columns=["Symbol", "Security", "Sector", "Sub_Sector", "Index"])


def load_nyse() -> pd.DataFrame:
    url = "https://raw.githubusercontent.com/datasets/nyse-other-listings/master/data/nyse-listed.csv"
    try:
        df = pd.read_csv(url, usecols=["ACT Symbol", "Company Name"])
        df = df.rename(columns={"ACT Symbol": "Symbol", "Company Name": "Security"})
        df["Symbol"] = df["Symbol"].map(normalize_symbol)
        df = df[~df["Symbol"].str.contains(r"[$\.]", na=False)]
        df = df[df["Symbol"].str.len() <= 5]
        df["Index"] = "NYSE"
        df["Sector"] = np.nan
        df["Sub_Sector"] = np.nan
        return df[["Symbol", "Security", "Sector", "Sub_Sector", "Index"]].drop_duplicates("Symbol")
    except Exception as e:
        print(f"Warning: failed to load NYSE list: {e}")
        return pd.DataFrame(columns=["Symbol", "Security", "Sector", "Sub_Sector", "Index"])


def load_extra() -> pd.DataFrame:
    file_tickers = read_optional_ticker_file(CONFIG_DIR / "extra_tickers.csv")
    tickers = sorted(set([normalize_symbol(x) for x in DEFAULT_EXTRA_TICKERS] + file_tickers))
    return pd.DataFrame(
        {
            "Symbol": tickers,
            "Security": np.nan,
            "Sector": np.nan,
            "Sub_Sector": np.nan,
            "Index": "Extra",
        }
    )


def get_extra_tickers() -> list[str]:
    """Return default + config/extra_tickers.csv symbols.

    This is intentionally separate from build_universe so extras can be
    force-included even if a later universe edit accidentally removes load_extra().
    """
    file_tickers = read_optional_ticker_file(CONFIG_DIR / "extra_tickers.csv")
    return sorted(set([normalize_symbol(x) for x in DEFAULT_EXTRA_TICKERS] + file_tickers))


def force_include_extras(universe_df: pd.DataFrame, include_extra: bool = True) -> pd.DataFrame:
    """Guarantee Extra/watchlist tickers are present in universe_df.

    This protects your manually curated list from being dropped when running
    --universe all, --universe sp500, --universe nyse, etc.
    """
    if not include_extra:
        return universe_df.copy()

    base = universe_df.copy()
    base["Symbol"] = base["Symbol"].map(normalize_symbol)

    extra = load_extra()
    existing = set(base["Symbol"].dropna().astype(str))
    missing = extra[~extra["Symbol"].isin(existing)].copy()

    if not missing.empty:
        base = pd.concat([base, missing], ignore_index=True)

    # If an extra ticker is already in another index, preserve that membership but
    # append Extra so you can always identify your manually added names.
    extra_set = set(extra["Symbol"].dropna().astype(str))
    base["is_extra"] = base["Symbol"].isin(extra_set).astype(int)

    def _append_extra(idx: object, sym: str) -> str:
        parts = set(str(idx).split(", ")) if pd.notna(idx) else set()
        if sym in extra_set:
            parts.add("Extra")
        return ", ".join(sorted(p for p in parts if p and p != "nan"))

    base["Index"] = [_append_extra(idx, sym) for idx, sym in zip(base["Index"], base["Symbol"])]

    # Collapse any duplicates created by force-include.
    out = (
        base.groupby("Symbol", as_index=False)
        .agg(
            Security=("Security", lambda x: x.dropna().iloc[0] if x.dropna().shape[0] else np.nan),
            Sector=("Sector", lambda x: x.dropna().iloc[0] if x.dropna().shape[0] else np.nan),
            Sub_Sector=("Sub_Sector", lambda x: x.dropna().iloc[0] if x.dropna().shape[0] else np.nan),
            Index=("Index", ordered_index_membership),
            is_extra=("is_extra", "max"),
        )
    )
    out["Index_Origin"] = out["Index"].map(primary_index_origin)
    return out.sort_values("Symbol").reset_index(drop=True)


def validate_extra_inclusion(universe_df: pd.DataFrame) -> pd.DataFrame:
    """Print a quick audit showing whether every extra ticker made it into the run. No file is created."""
    extra = set(get_extra_tickers())
    included = set(universe_df["Symbol"].dropna().map(normalize_symbol))
    check = pd.DataFrame({"Symbol": sorted(extra)})
    check["included_in_run"] = check["Symbol"].isin(included).astype(int)
    missing = check[check["included_in_run"] == 0]["Symbol"].tolist()
    if missing:
        print(f"WARNING: {len(missing)} extra tickers missing from universe. Examples: {missing[:10]}")
    else:
        print(f"Extra ticker check passed: {len(check):,} extras included/available in universe.")
    return check


def build_universe(universe: str) -> pd.DataFrame:
    pieces = []
    sp500 = None

    if universe in ["sp500", "all"]:
        sp500 = load_sp500()
        pieces.append(sp500)
    else:
        # Still useful as metadata source.
        try:
            sp500 = load_sp500()
        except Exception:
            sp500 = pd.DataFrame(columns=["Symbol", "Security", "Sector", "Sub_Sector", "Index"])

    if universe in ["nasdaq", "all"]:
        pieces.append(load_nasdaq())
    if universe in ["russell", "russell2000", "all"]:
        pieces.append(load_russell2000())
    if universe in ["nyse", "all"]:
        pieces.append(load_nyse())
    if universe in ["extra", "watchlist", "all"]:
        pieces.append(load_extra())

    if not pieces:
        raise ValueError(f"Unknown universe: {universe}")

    df = pd.concat(pieces, ignore_index=True)
    df["Symbol"] = df["Symbol"].map(normalize_symbol)
    df = df[df["Symbol"].notna() & (df["Symbol"] != "")]

    # If a symbol appears in multiple universes, preserve combined membership.
    agg = (
        df.groupby("Symbol", as_index=False)
        .agg(
            Security=("Security", lambda x: x.dropna().iloc[0] if x.dropna().shape[0] else np.nan),
            Sector=("Sector", lambda x: x.dropna().iloc[0] if x.dropna().shape[0] else np.nan),
            Sub_Sector=("Sub_Sector", lambda x: x.dropna().iloc[0] if x.dropna().shape[0] else np.nan),
            Index=("Index", ordered_index_membership),
        )
    )

    # Prefer S&P metadata where available.
    if sp500 is not None and not sp500.empty:
        sp_meta = sp500[["Symbol", "Security", "Sector", "Sub_Sector"]].rename(
            columns={
                "Security": "Security_sp",
                "Sector": "Sector_sp",
                "Sub_Sector": "Sub_Sector_sp",
            }
        )
        agg = agg.merge(sp_meta, on="Symbol", how="left")
        for col in ["Security", "Sector", "Sub_Sector"]:
            agg[col] = agg[col].combine_first(agg[f"{col}_sp"])
            agg.drop(columns=[f"{col}_sp"], inplace=True)

    agg["Index_Origin"] = agg["Index"].map(primary_index_origin)
    return agg.sort_values("Symbol").reset_index(drop=True)


# =============================================================================
# PRICE HISTORY CACHE
# =============================================================================

def cache_base(universe: str) -> Path:
    safe = universe.replace(" ", "_").lower()
    return CACHE_DIR / f"prices_{safe}"


def read_prices_cache(universe: str) -> pd.DataFrame:
    base = cache_base(universe)
    pq = base.with_suffix(".parquet")
    pkl = base.with_suffix(".pkl")
    csv = base.with_suffix(".csv")
    if pq.exists():
        try:
            return pd.read_parquet(pq)
        except Exception:
            pass
    if pkl.exists():
        return pd.read_pickle(pkl)
    if csv.exists():
        return pd.read_csv(csv, parse_dates=["Date"])
    return pd.DataFrame()


def write_prices_cache(df: pd.DataFrame, universe: str) -> Path:
    base = cache_base(universe)
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.drop_duplicates(["Date", "Symbol"], keep="last").sort_values(["Symbol", "Date"])
    try:
        path = base.with_suffix(".parquet")
        df.to_parquet(path, index=False)
        return path
    except Exception:
        path = base.with_suffix(".pkl")
        df.to_pickle(path)
        return path


def chunk_list(items: list[str], chunk_size: int) -> Iterable[list[str]]:
    for i in range(0, len(items), chunk_size):
        yield items[i : i + chunk_size]


def last_market_end_date() -> datetime:
    today = datetime.today()
    if today.weekday() >= 5:
        # Saturday/Sunday -> previous Friday + one day for yfinance exclusive end.
        last_friday = today - timedelta(days=today.weekday() - 4)
        return datetime(last_friday.year, last_friday.month, last_friday.day) + timedelta(days=1)
    # yfinance end is exclusive, so add one day to include today's completed bar when available.
    return datetime(today.year, today.month, today.day) + timedelta(days=1)


def yfinance_download_to_long(
    tickers: list[str],
    start: str | datetime,
    end: str | datetime,
    chunk_size: int = 100,
    delay: float = 1.5,
) -> pd.DataFrame:
    frames = []
    tickers = sorted(set([normalize_symbol(t) for t in tickers if str(t).strip()]))
    chunks = list(chunk_list(tickers, chunk_size))

    for i, chunk in enumerate(chunks, start=1):
        print(f"Downloading price chunk {i}/{len(chunks)} | {len(chunk)} tickers")
        try:
            data = yf.download(
                tickers=chunk,
                start=start,
                end=end,
                auto_adjust=False,
                progress=False,
                threads=True,
                group_by="column",
            )
            if data is None or data.empty:
                time.sleep(delay)
                continue

            # Multi-ticker usually: columns = MultiIndex level0 Price, level1 Ticker.
            if isinstance(data.columns, pd.MultiIndex):
                long = data.stack(level=1, future_stack=True).reset_index()
                # Depending on pandas/yfinance, ticker level may be called level_1 or Ticker.
                if "level_1" in long.columns:
                    long = long.rename(columns={"level_1": "Symbol"})
                elif "Ticker" in long.columns:
                    long = long.rename(columns={"Ticker": "Symbol"})
                elif "Symbols" in long.columns:
                    long = long.rename(columns={"Symbols": "Symbol"})
            else:
                # Single ticker fallback.
                long = data.reset_index()
                long["Symbol"] = chunk[0]

            long["Symbol"] = long["Symbol"].map(normalize_symbol)
            long["Date"] = pd.to_datetime(long["Date"])
            keep_cols = [c for c in ["Date", "Symbol", "Open", "High", "Low", "Close", "Adj Close", "Volume"] if c in long.columns]
            long = long[keep_cols]
            frames.append(long)
        except Exception as e:
            print(f"Price chunk {i} failed: {e}")
        time.sleep(delay)

    if not frames:
        return pd.DataFrame(columns=["Date", "Symbol", "Open", "High", "Low", "Close", "Adj Close", "Volume"])

    out = pd.concat(frames, ignore_index=True)
    out = out.dropna(subset=["Date", "Symbol"])
    out = out.drop_duplicates(["Date", "Symbol"], keep="last")
    return out.sort_values(["Symbol", "Date"]).reset_index(drop=True)


def load_or_update_prices(
    tickers: list[str],
    universe: str,
    start_date: str,
    end_date: datetime,
    mode: Literal["incremental", "full"] = "incremental",
    chunk_size: int = 100,
    delay: float = 1.5,
) -> pd.DataFrame:
    tickers = sorted(set([normalize_symbol(t) for t in tickers]))
    cached = read_prices_cache(universe)

    if mode == "full" or cached.empty:
        print("Price mode: FULL download")
        prices = yfinance_download_to_long(tickers, start_date, end_date, chunk_size, delay)
        cache_path = write_prices_cache(prices, universe)
        print(f"Saved price cache: {cache_path}")
        return prices

    cached["Date"] = pd.to_datetime(cached["Date"])
    cached["Symbol"] = cached["Symbol"].map(normalize_symbol)
    cached_symbols = set(cached["Symbol"].dropna().unique())
    missing_symbols = sorted(set(tickers) - cached_symbols)

    frames = [cached]

    if missing_symbols:
        print(f"Found {len(missing_symbols)} tickers missing from price cache. Downloading full history for those.")
        missing_prices = yfinance_download_to_long(missing_symbols, start_date, end_date, chunk_size, delay)
        frames.append(missing_prices)

    # Refresh recent days for existing tickers. This captures corrections and the newest bars.
    last_cached = cached["Date"].max()
    refresh_start = max(pd.to_datetime(start_date), last_cached - pd.Timedelta(days=7))
    print(f"Price mode: INCREMENTAL refresh from {refresh_start.date()} to {end_date.date()}")
    refresh_prices = yfinance_download_to_long(tickers, refresh_start, end_date, chunk_size, delay)
    frames.append(refresh_prices)

    prices = pd.concat(frames, ignore_index=True)
    prices = prices.drop_duplicates(["Date", "Symbol"], keep="last").sort_values(["Symbol", "Date"])
    cache_path = write_prices_cache(prices, universe)
    print(f"Saved price cache: {cache_path}")
    return prices.reset_index(drop=True)


# =============================================================================
# FUNDAMENTALS CACHE
# =============================================================================

def fundamentals_cache_path(universe: str) -> Path:
    return CACHE_DIR / f"fundamentals_{universe.replace(' ', '_').lower()}.json"


def read_fundamentals_cache(universe: str) -> pd.DataFrame:
    path = fundamentals_cache_path(universe)
    if not path.exists():
        return pd.DataFrame()
    try:
        payload = json.loads(path.read_text())
        records = payload.get("records", []) if isinstance(payload, dict) else []
        df = pd.DataFrame(records)
        if not df.empty and "Symbol" in df.columns:
            df["Symbol"] = df["Symbol"].map(normalize_symbol)
        return df
    except Exception as e:
        print(f"Warning: failed to read fundamentals cache: {e}")
        return pd.DataFrame()


def write_fundamentals_cache(df: pd.DataFrame, universe: str) -> None:
    path = fundamentals_cache_path(universe)
    payload = {
        "fetched_at": pd.Timestamp.utcnow().isoformat(),
        "records": df.replace({np.nan: None}).to_dict(orient="records"),
    }
    path.write_text(json.dumps(payload, indent=2))


def fetch_fundamentals(tickers: list[str], delay: float = 0.15) -> pd.DataFrame:
    rows = []
    for i, t in enumerate(tickers, start=1):
        print(f"Fetching fundamentals {i}/{len(tickers)}: {t}")
        try:
            info = yf.Ticker(t).get_info()
            market_cap = info.get("marketCap", None)
            rows.append(
                {
                    "Symbol": t,
                    "Marketcap": market_cap,
                    "capMil": (market_cap or 0) / 1e6 if market_cap is not None else np.nan,
                    "AvgVol10d": info.get("averageDailyVolume10Day", None),
                    "debtToEquity": info.get("debtToEquity", None),
                    "shortRatio": info.get("shortRatio", None),
                    "priceToBook": info.get("priceToBook", None),
                    "revenueGrowth": info.get("revenueGrowth", None),
                    "freeCashFlow": info.get("freeCashflow", None),
                    "returnOnEquity": info.get("returnOnEquity", None),
                    "Security_yf": info.get("longName", None),
                    "Sector_yf": info.get("sector", None),
                    "Sub_Sector_yf": info.get("industry", None),
                    "description": info.get("longBusinessSummary", ""),
                }
            )
        except Exception as e:
            print(f"Fundamentals failed for {t}: {e}")
        time.sleep(delay)
    return pd.DataFrame(rows)


def load_or_update_fundamentals(
    tickers: list[str],
    universe: str,
    mode: Literal["missing", "force", "skip"] = "missing",
) -> pd.DataFrame:
    tickers = sorted(set([normalize_symbol(t) for t in tickers]))
    cached = read_fundamentals_cache(universe)

    if mode == "skip":
        print("Fundamentals mode: SKIP remote fetch")
        return cached

    if mode == "force" or cached.empty:
        print("Fundamentals mode: FORCE/full fetch")
        fresh = fetch_fundamentals(tickers)
        write_fundamentals_cache(fresh, universe)
        return fresh

    cached_symbols = set(cached["Symbol"].dropna().unique()) if "Symbol" in cached.columns else set()
    missing = sorted(set(tickers) - cached_symbols)

    # Also refresh symbols with all important values missing.
    important = ["Marketcap", "debtToEquity", "priceToBook", "revenueGrowth", "freeCashFlow", "returnOnEquity", "description"]
    for col in important:
        if col not in cached.columns:
            cached[col] = np.nan
    # Refresh rows that are almost entirely empty OR that lack all new quality fields.
    # This lets a normal --fundamentals-mode missing run populate the new
    # revenueGrowth/freeCashFlow/returnOnEquity fields without requiring a full force refresh.
    quality_fields = ["revenueGrowth", "freeCashFlow", "returnOnEquity"]
    weak_all = cached[important].isna().all(axis=1)
    weak_quality = cached[quality_fields].isna().all(axis=1)
    weak = cached.loc[weak_all | weak_quality, "Symbol"].dropna().unique().tolist()
    to_fetch = sorted(set(missing + weak))

    print(f"Fundamentals mode: MISSING only | need {len(to_fetch)} tickers")
    if to_fetch:
        fresh = fetch_fundamentals(to_fetch)
        combined = pd.concat([cached[~cached["Symbol"].isin(to_fetch)], fresh], ignore_index=True)
    else:
        combined = cached

    combined = combined.drop_duplicates("Symbol", keep="last") if "Symbol" in combined.columns else combined
    write_fundamentals_cache(combined, universe)
    return combined


# =============================================================================
# INDICATORS / CALCULATIONS
# =============================================================================

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def rsi_sentiment(x: float) -> str:
    if pd.isna(x):
        return "Unknown"
    if x > 70:
        return "Overbought"
    if x < 30:
        return "Oversold"
    return "Neutral"


def prepare_price_features(prices: pd.DataFrame) -> pd.DataFrame:
    df = prices.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    df["Symbol"] = df["Symbol"].map(normalize_symbol)
    df = df.sort_values(["Symbol", "Date"])

    # Ensure numeric fields.
    for col in ["Open", "High", "Low", "Close", "Adj Close", "Volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["Close"])

    g = df.groupby("Symbol", group_keys=False)
    df["one_week_close"] = g["Close"].shift(5).round(4)
    df["one_month_close"] = g["Close"].shift(21).round(4)
    df["three_month_close"] = g["Close"].shift(63).round(4)
    df["six_month_close"] = g["Close"].shift(126).round(4)
    df["previousClose"] = g["Close"].shift(1).round(4)
    df["last_close"] = df["Close"].round(4)

    df["one_week_performance"] = ((df["Close"] / df["one_week_close"] - 1) * 100).round(4)
    df["one_month_performance"] = ((df["Close"] / df["one_month_close"] - 1) * 100).round(4)
    df["three_month_performance"] = ((df["Close"] / df["three_month_close"] - 1) * 100).round(4)
    df["six_month_performance"] = ((df["Close"] / df["six_month_close"] - 1) * 100).round(4)

    df["high_5d"] = g["High"].transform(lambda x: x.rolling(5, min_periods=1).max()) if "High" in df.columns else np.nan
    df["low_5d"] = g["Low"].transform(lambda x: x.rolling(5, min_periods=1).min()) if "Low" in df.columns else np.nan
    df["high_21d"] = g["High"].transform(lambda x: x.rolling(21, min_periods=1).max()) if "High" in df.columns else np.nan
    df["low_21d"] = g["Low"].transform(lambda x: x.rolling(21, min_periods=1).min()) if "Low" in df.columns else np.nan
    df["rolling_range_21d"] = df["high_21d"] - df["low_21d"]
    df["range_pct_21d"] = (df["high_21d"] - df["low_21d"]) / df["high_21d"]
    df["near_21d_low"] = ((df["Close"] - df["low_21d"]) / df["low_21d"] <= 0.10)
    df["is_basing"] = (
        (df["range_pct_21d"] <= 0.15)
        & df["near_21d_low"].fillna(False)
        & (df["one_month_performance"] <= -5)
    )

    # YTD: first available close in current calendar year.
    df["year"] = df["Date"].dt.year
    year_first_close = df.groupby(["Symbol", "year"])["Close"].transform("first")
    df["ytd"] = ((df["Close"] / year_first_close) - 1).round(4)

    df["RSI"] = g["Close"].transform(lambda x: calculate_rsi(x, 14))
    df["Sentiment"] = df["RSI"].map(rsi_sentiment)

    return df


def latest_performance(df: pd.DataFrame) -> pd.DataFrame:
    latest = df.sort_values("Date").groupby("Symbol", as_index=False).tail(1)
    cols = [
        "Symbol", "Date", "last_close", "previousClose", "one_week_close", "one_month_close",
        "three_month_close", "six_month_close", "one_week_performance", "one_month_performance",
        "three_month_performance", "six_month_performance", "ytd", "RSI", "Sentiment", "Volume",
        "is_basing", "range_pct_21d", "high_5d", "low_5d", "high_21d", "low_21d",
    ]
    cols = [c for c in cols if c in latest.columns]
    out = latest[cols].copy().rename(columns={"Volume": "last_volume"})
    out["prior_%_change"] = ((out["last_close"] - out["previousClose"]) / out["previousClose"] * 100).round(4)
    out["RSI"] = out["RSI"].round(2)
    return out


def min_max_stats(df: pd.DataFrame) -> pd.DataFrame:
    stats = df.groupby("Symbol").agg(
        mean_vol=("Volume", "mean") if "Volume" in df.columns else ("Close", "count"),
        min=("Close", "min"),
        max=("Close", "max"),
    ).reset_index()

    covid = (
        df[df["Date"] < pd.Timestamp("2020-04-30")]
        .groupby("Symbol")
        .agg(minCovid=("Close", "min"))
        .reset_index()
    )
    stats = stats.merge(covid, on="Symbol", how="left")
    stats["minCovid_filled"] = stats["minCovid"].fillna(stats["min"])

    min_dates = df.loc[df.groupby("Symbol")["Close"].idxmin(), ["Symbol", "Date"]].rename(columns={"Date": "min_date"})
    max_dates = df.loc[df.groupby("Symbol")["Close"].idxmax(), ["Symbol", "Date"]].rename(columns={"Date": "max_date"})
    stats = stats.merge(min_dates, on="Symbol", how="left").merge(max_dates, on="Symbol", how="left")

    covid_df = df[df["Date"] < pd.Timestamp("2020-04-30")]
    if not covid_df.empty:
        covid_dates = covid_df.loc[covid_df.groupby("Symbol")["Close"].idxmin(), ["Symbol", "Date"]].rename(columns={"Date": "mincovid_date"})
        stats = stats.merge(covid_dates, on="Symbol", how="left")
    else:
        stats["mincovid_date"] = pd.NaT

    numeric_cols = ["mean_vol", "min", "max", "minCovid", "minCovid_filled"]
    for c in numeric_cols:
        stats[c] = pd.to_numeric(stats[c], errors="coerce").round(2)
    return stats


def support_pivot_latest(df: pd.DataFrame, lookback_days: int = 180, n_levels: int = 3, min_pct_diff: float = 0.05) -> pd.DataFrame:
    rows = []
    for symbol, g in df.groupby("Symbol"):
        g = g.sort_values("Date").copy()
        if g.empty:
            continue
        last = g.iloc[-1]
        last_close = last["Close"]
        last_date = pd.to_datetime(last["Date"])
        hist = g[(g["Date"] < last_date) & (g["Date"] >= last_date - pd.Timedelta(days=lookback_days))]

        recent = g.tail(5)
        high_5d = recent["High"].max() if "High" in recent.columns else recent["Close"].max()
        low_5d = recent["Low"].min() if "Low" in recent.columns else recent["Close"].min()
        high_21d = g.tail(21)["High"].max() if "High" in g.columns else g.tail(21)["Close"].max()
        low_21d = g.tail(21)["Low"].min() if "Low" in g.columns else g.tail(21)["Close"].min()

        pivot = (high_5d + low_5d + last_close) / 3 if pd.notna(last_close) else np.nan
        support1 = (2 * pivot) - high_5d if pd.notna(pivot) else np.nan
        resistance1 = (2 * pivot) - low_5d if pd.notna(pivot) else np.nan

        raw_supports = hist.loc[hist["Close"] < last_close, "Close"].sort_values(ascending=False).dropna().unique()
        raw_resistances = hist.loc[hist["Close"] > last_close, "Close"].sort_values().dropna().unique()

        supports = []
        for s in raw_supports:
            if not supports or abs(s - supports[-1]) / max(abs(supports[-1]), 1e-9) > min_pct_diff:
                supports.append(float(s))
            if len(supports) == n_levels:
                break

        resistances = []
        for r in raw_resistances:
            if not resistances or abs(r - resistances[-1]) / max(abs(resistances[-1]), 1e-9) > min_pct_diff:
                resistances.append(float(r))
            if len(resistances) == n_levels:
                break

        row = {
            "Symbol": symbol,
            "Pivot_5d": round(pivot, 2) if pd.notna(pivot) else np.nan,
            "Support1_5d": round(support1, 2) if pd.notna(support1) else np.nan,
            "Resistance1_5d": round(resistance1, 2) if pd.notna(resistance1) else np.nan,
            "high_5d_pivot": round(high_5d, 2) if pd.notna(high_5d) else np.nan,
            "low_5d_pivot": round(low_5d, 2) if pd.notna(low_5d) else np.nan,
            "high_21d_pivot": round(high_21d, 2) if pd.notna(high_21d) else np.nan,
            "low_21d_pivot": round(low_21d, 2) if pd.notna(low_21d) else np.nan,
        }
        for i in range(n_levels):
            row[f"next_support_{i+1}"] = supports[i] if i < len(supports) else np.nan
            row[f"next_resistance_{i+1}"] = resistances[i] if i < len(resistances) else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


# =============================================================================
# SCORING / RANKING
# =============================================================================

def safe_div(numerator, denominator):
    """
    Safe division that preserves pandas index when possible.
    Returns NaN for divide-by-zero or invalid values.
    """
    import numpy as np
    import pandas as pd

    try:
        idx = getattr(numerator, "index", None)
        if idx is None:
            idx = getattr(denominator, "index", None)

        num = pd.to_numeric(numerator, errors="coerce")
        den = pd.to_numeric(denominator, errors="coerce")

        result = np.where((den == 0) | pd.isna(den), np.nan, num / den)

        if idx is not None:
            return pd.Series(result, index=idx)
        return result
    except Exception:
        try:
            return numerator / denominator
        except Exception:
            return np.nan




def add_core_value_calculations(dfagg: pd.DataFrame) -> pd.DataFrame:
    dfagg = dfagg.copy()
    for col in ["min", "max", "minCovid_filled", "last_close"]:
        dfagg[col] = pd.to_numeric(dfagg[col], errors="coerce")

    # Main original calculations: keep these as core fields.
    dfagg["price_suggest_80"] = (
        dfagg["max"] - (((dfagg["max"] - dfagg["min"]) / 100) * 80)
    ).round(2)

    dfagg["win%"] = safe_div(dfagg["max"] - dfagg["last_close"], dfagg["max"] - dfagg["min"])

    dfagg["price_suggest_80_covid"] = (
        dfagg["max"] - (((dfagg["max"] - dfagg["minCovid_filled"]) / 100) * 80)
    ).round(2)

    dfagg["win%_covid"] = safe_div(
        dfagg["max"] - dfagg["last_close"], dfagg["max"] - dfagg["minCovid_filled"]
    )

    # Combined paired views ranked mainly by win %.
    dfagg["regular_range_score"] = (pd.to_numeric(dfagg["win%"], errors="coerce").clip(0, 1) * 100).round(2)
    dfagg["covid_range_score"] = (pd.to_numeric(dfagg["win%_covid"], errors="coerce").clip(0, 1) * 100).round(2)

    dfagg["below_price_suggest_80"] = (dfagg["last_close"] <= dfagg["price_suggest_80"]).astype(int)
    dfagg["below_price_suggest_80_covid"] = (dfagg["last_close"] <= dfagg["price_suggest_80_covid"]).astype(int)

    dfagg["Percent_min_price"] = np.where(
        dfagg["min"] < dfagg["minCovid_filled"],
        safe_div(dfagg["last_close"] - dfagg["min"], dfagg["min"]) * 100,
        safe_div(dfagg["last_close"] - dfagg["minCovid_filled"], dfagg["minCovid_filled"]) * 100,
    )

    conditions = [
        (dfagg["min"] < dfagg["minCovid_filled"])
        & ((dfagg["last_close"] == dfagg["min"]) | ((dfagg["last_close"] - dfagg["min"]) < 5)),
        (dfagg["min"] < dfagg["minCovid_filled"])
        & (dfagg["last_close"] > dfagg["min"])
        & (dfagg["last_close"] < dfagg["minCovid_filled"]),
        safe_div(dfagg["last_close"] - dfagg["min"], dfagg["min"]) <= 0.05,
        (dfagg["min"] == dfagg["minCovid_filled"])
        | (safe_div((dfagg["min"] - dfagg["minCovid_filled"]).abs(), dfagg["minCovid_filled"]) * 100).between(-3, 3),
        dfagg["min"] > dfagg["minCovid_filled"],
    ]
    choices = [
        "Y - min below covid min, At bottom",
        "Y - price between min and mincovid",
        "Y - near all-time low (not covid-related)",
        "N - covid low = low",
        "N - Min > Mincovid",
    ]
    dfagg["Is_Covid_Low"] = np.select(conditions, choices, default="Condition not met")
    return dfagg


def add_scores(dfagg: pd.DataFrame) -> pd.DataFrame:
    dfagg = dfagg.copy()
    perf_cols = ["one_week_performance", "one_month_performance", "three_month_performance", "six_month_performance"]
    for col in perf_cols:
        dfagg[col] = pd.to_numeric(dfagg[col], errors="coerce")

    # Drop alert = helps you spot sudden damage across multiple windows.
    dfagg["largest_recent_drop"] = dfagg[
        ["one_week_performance", "one_month_performance", "three_month_performance"]
    ].min(axis=1)
    dfagg["drop_alert_score"] = (dfagg["largest_recent_drop"].clip(upper=0).abs().clip(0, 40) / 40 * 100).round(2)

    # Technical score.
    dfagg["rsi_score"] = (100 - pd.to_numeric(dfagg["RSI"], errors="coerce").clip(0, 100)).round(2)
    support_distance = ((dfagg["last_close"] - dfagg["Support1_5d"]).abs() / dfagg["last_close"]).clip(0, 0.20)
    dfagg["support_score"] = (100 - (support_distance / 0.20 * 100)).round(2)
    dfagg["basing_score"] = dfagg.get("is_basing", False).fillna(False).astype(int) * 100
    dfagg["technical_score"] = (
        dfagg["rsi_score"].fillna(0) * 0.40
        + dfagg["support_score"].fillna(0) * 0.35
        + dfagg["basing_score"].fillna(0) * 0.25
    ).round(2)

    # Fundamentals score: simple defensive score using fields you already fetch.
    dte = pd.to_numeric(dfagg.get("debtToEquity"), errors="coerce")
    pb = pd.to_numeric(dfagg.get("priceToBook"), errors="coerce")
    sr = pd.to_numeric(dfagg.get("shortRatio"), errors="coerce")
    mcap = pd.to_numeric(dfagg.get("Marketcap"), errors="coerce")

    dfagg["mcap_score"] = np.where(mcap >= 2_000_000_000, 100, np.where(mcap >= 500_000_000, 60, 25))
    dfagg["debt_score"] = (100 - dte.fillna(150).clip(0, 300) / 300 * 100).round(2)
    dfagg["pb_score"] = (100 - pb.fillna(10).clip(0, 20) / 20 * 100).round(2)
    dfagg["short_score"] = (100 - sr.fillna(5).clip(0, 15) / 15 * 100).round(2)
    dfagg["fundamental_score"] = (
        dfagg["mcap_score"] * 0.35
        + dfagg["debt_score"] * 0.25
        + dfagg["pb_score"] * 0.25
        + dfagg["short_score"] * 0.15
    ).round(2)

    # Your primary value score uses the paired calculations, not just recent drops.
    dfagg["value_range_score"] = (
        dfagg["regular_range_score"].fillna(0) * 0.50
        + dfagg["covid_range_score"].fillna(0) * 0.40
        + dfagg["below_price_suggest_80"].fillna(0) * 5
        + dfagg["below_price_suggest_80_covid"].fillna(0) * 5
    ).clip(0, 100).round(2)

    dfagg["final_watch_score"] = (
        dfagg["value_range_score"].fillna(0) * 0.40
        + dfagg["drop_alert_score"].fillna(0) * 0.25
        + dfagg["technical_score"].fillna(0) * 0.20
        + dfagg["fundamental_score"].fillna(0) * 0.15
    ).round(2)

    # Reasons are useful for quick review.
    reasons = []
    for _, row in dfagg.iterrows():
        r = []
        if row.get("regular_range_score", 0) >= 70:
            r.append("High regular win%")
        if row.get("covid_range_score", 0) >= 70:
            r.append("High covid win%")
        if row.get("drop_alert_score", 0) >= 70:
            r.append("Large recent drop")
        if row.get("RSI", 999) <= 35:
            r.append("RSI oversold/near oversold")
        if row.get("support_score", 0) >= 75:
            r.append("Near support")
        if row.get("below_price_suggest_80", 0) == 1:
            r.append("Below price_suggest_80")
        if row.get("below_price_suggest_80_covid", 0) == 1:
            r.append("Below covid price_suggest_80")
        if row.get("flag", 0) == 1:
            r.append("On watchlist")
        reasons.append("; ".join(r))
    dfagg["watch_reason"] = reasons
    return dfagg



def add_fundamental_quality(dfagg: pd.DataFrame) -> pd.DataFrame:
    """
    Adds a compact fundamental quality indicator without adding many extra columns.

    Kept columns:
        debtToEquity, revenueGrowth, freeCashFlow, returnOnEquity, priceToBook,
        quality_score, quality_reason

    quality_score is intentionally simple and readable:
        low debt             = 20 points if debtToEquity < 1.0
        positive FCF         = 20 points if freeCashFlow > 0
        revenue growth       = 20 points if revenueGrowth >= 5%
        good ROE             = 20 points if returnOnEquity >= 10%
        reasonable P/B       = 20 points if 0 < priceToBook <= 5

    Score range: 0 to 100.
    """
    out = dfagg.copy()

    for col in ["debtToEquity", "revenueGrowth", "freeCashFlow", "returnOnEquity", "priceToBook"]:
        if col not in out.columns:
            out[col] = np.nan
        out[col] = pd.to_numeric(out[col], errors="coerce")

    low_debt = out["debtToEquity"].notna() & (out["debtToEquity"] < 1.0)
    fcf_positive = out["freeCashFlow"].notna() & (out["freeCashFlow"] > 0)
    revenue_growing = out["revenueGrowth"].notna() & (out["revenueGrowth"] >= 0.05)
    roe_good = out["returnOnEquity"].notna() & (out["returnOnEquity"] >= 0.10)
    pb_reasonable = out["priceToBook"].notna() & (out["priceToBook"] > 0) & (out["priceToBook"] <= 5)

    out["quality_score"] = (
        low_debt.astype(int) * 20
        + fcf_positive.astype(int) * 20
        + revenue_growing.astype(int) * 20
        + roe_good.astype(int) * 20
        + pb_reasonable.astype(int) * 20
    ).astype(int)

    reasons = []
    for i in out.index:
        r = []
        if bool(low_debt.loc[i]):
            r.append("Low debt")
        if bool(fcf_positive.loc[i]):
            r.append("Positive FCF")
        if bool(revenue_growing.loc[i]):
            r.append("Revenue growth >=5%")
        if bool(roe_good.loc[i]):
            r.append("ROE >=10%")
        if bool(pb_reasonable.loc[i]):
            r.append("P/B <=5")
        if not r:
            r.append("Fundamental checks not met or unavailable")
        reasons.append("; ".join(r))

    out["quality_reason"] = reasons
    return out

def add_keyword_flags(dfagg: pd.DataFrame) -> pd.DataFrame:
    keywords = ["lng", "gas", "quantum", "ai", "epc", "energy", "nuclear"]
    pattern = r"\b(" + "|".join(map(re.escape, keywords)) + r")\b"
    if "description" not in dfagg.columns:
        dfagg["description"] = ""
    dfagg["is_key"] = dfagg["description"].fillna("").str.contains(pattern, case=False, regex=True).astype(int)
    return dfagg


# =============================================================================
# EXPORTS
# =============================================================================

def reorder_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean output column layout.

    Goal:
    - Keep workbook reviewable.
    - Put market cap near the beginning, before prices.
    - Put actual price columns before performance columns.
    - Keep only the most useful score columns.
    - Hide internal score components from exported tabs.
    """

    hidden_output_columns = {
        "regular_range_score",
        "covid_range_score",
        "technical_score",
        "fundamental_score",
        "rsi_score",
        "support_score",
        "basing_score",
        "mcap_score",
        "debt_score",
        "pb_score",
        "short_score",
        "distance_from_support",
    }

    preferred = [
        "Symbol", "Security", "Index", "source_index", "Index_Origin", "price_status", "Sector", "Sub_Sector", "sector_temperature", "sector_hot_score", "Date",

        # Market cap early
        "Marketcap", "capMil",

        # Actual price columns
        "last_close", "previousClose",
        "one_week_close", "one_month_close", "three_month_close", "six_month_close",
        "min", "max", "minCovid", "minCovid_filled",
        "price_suggest_80", "price_suggest_80_covid",

        # Opportunity measurements
        "win%", "win%_covid",
        "below_price_suggest_80", "below_price_suggest_80_covid",
        "Percent_min_price", "Is_Covid_Low",

        # Main scores only
        "final_watch_score", "value_range_score", "drop_alert_score", "watch_reason",

        # Performance columns
        "prior_%_change",
        "one_week_performance", "one_month_performance", "three_month_performance", "six_month_performance", "ytd",
        "largest_recent_drop",

        # Technical indicators / levels
        "RSI", "Sentiment", "is_basing", "range_pct_21d",
        "Pivot_5d", "Support1_5d", "Resistance1_5d",
        "next_support_1", "next_support_2", "next_support_3",
        "next_resistance_1", "next_resistance_2", "next_resistance_3",

        # Fundamentals / liquidity
        "AvgVol10d", "last_volume", "mean_vol",
        "debtToEquity", "shortRatio", "priceToBook",

        # Dates and flags
        "min_date", "max_date", "mincovid_date",
        "flag", "is_extra", "is_key",

        # Long text last
        "description",
    ]

    clean_cols = [c for c in df.columns if c not in hidden_output_columns]
    ordered = [c for c in preferred if c in clean_cols]
    remaining = [c for c in clean_cols if c not in ordered]

    return df[ordered + remaining]


def add_sector_temperature(dfagg: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Add sector-level hot/cold labels based on current performance in the run.

    This does not pull an external hot/cold signal. It calculates sector strength
    from the stocks in your output using recent performance, breadth, and score.
    """
    import numpy as np
    import pandas as pd

    df = dfagg.copy()

    if "Sector" not in df.columns:
        df["Sector"] = "Unknown"

    df["Sector"] = df["Sector"].fillna("Unknown").astype(str).str.strip()
    df.loc[df["Sector"].eq(""), "Sector"] = "Unknown"

    sector_map = {
        "Financial Services": "Financials",
        "Consumer Cyclical": "Consumer Discretionary",
        "Consumer Defensive": "Consumer Staples",
        "Technology": "Information Technology",
        "Healthcare": "Health Care",
        "Basic Materials": "Materials",
    }
    df["Sector"] = df["Sector"].replace(sector_map)

    for col in [
        "one_week_performance",
        "one_month_performance",
        "three_month_performance",
        "six_month_performance",
        "final_watch_score",
        "value_range_score",
        "drop_alert_score",
        "capMil",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in ["one_week_performance", "one_month_performance", "three_month_performance", "final_watch_score", "capMil"]:
        if col not in df.columns:
            df[col] = np.nan

    if "Symbol" not in df.columns:
        df["Symbol"] = df.index.astype(str)

    df["_positive_1m"] = np.where(pd.to_numeric(df["one_month_performance"], errors="coerce") > 0, 1, 0)

    sector_summary = (
        df.groupby("Sector", dropna=False)
          .agg(
              stock_count=("Symbol", "nunique"),
              avg_1w_performance=("one_week_performance", "mean"),
              avg_1m_performance=("one_month_performance", "mean"),
              avg_3m_performance=("three_month_performance", "mean"),
              pct_positive_1m=("_positive_1m", "mean"),
              avg_final_watch_score=("final_watch_score", "mean"),
              median_market_cap_mil=("capMil", "median"),
          )
          .reset_index()
    )

    sector_summary["pct_positive_1m"] = sector_summary["pct_positive_1m"] * 100

    sector_summary["sector_hot_score"] = (
        sector_summary["avg_1m_performance"].fillna(0) * 0.40 +
        sector_summary["avg_3m_performance"].fillna(0) * 0.30 +
        sector_summary["avg_1w_performance"].fillna(0) * 0.20 +
        (sector_summary["pct_positive_1m"].fillna(0) / 10) * 0.05 +
        (sector_summary["avg_final_watch_score"].fillna(0) / 10) * 0.05
    )

    def _temperature(score):
        if pd.isna(score):
            return "Unknown"
        if score >= 5:
            return "Hot"
        if score <= -3:
            return "Cold"
        return "Neutral"

    sector_summary["sector_temperature"] = sector_summary["sector_hot_score"].apply(_temperature)

    sector_summary = sector_summary.sort_values(
        ["sector_hot_score", "avg_1m_performance", "avg_3m_performance"],
        ascending=[False, False, False],
        na_position="last",
    )

    df = df.merge(
        sector_summary[["Sector", "sector_hot_score", "sector_temperature"]],
        on="Sector",
        how="left",
    )

    df.drop(columns=["_positive_1m"], inplace=True, errors="ignore")

    round_cols = [
        "avg_1w_performance",
        "avg_1m_performance",
        "avg_3m_performance",
        "pct_positive_1m",
        "avg_final_watch_score",
        "median_market_cap_mil",
        "sector_hot_score",
    ]
    for col in round_cols:
        if col in sector_summary.columns:
            sector_summary[col] = sector_summary[col].round(2)

    if "sector_hot_score" in df.columns:
        df["sector_hot_score"] = pd.to_numeric(df["sector_hot_score"], errors="coerce").round(2)

    return df, sector_summary


def add_sector_summary_view(views: dict[str, pd.DataFrame], sector_summary: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Insert Sector Summary near the front of the workbook views."""
    ordered = {"Sector Summary": sector_summary}
    for key, value in views.items():
        ordered[key] = value
    return ordered


def make_ranked_views(dfagg: pd.DataFrame, min_market_cap: float = 2000) -> dict[str, pd.DataFrame]:
    """
    Build all workbook views defensively.

    This prevents ranking KeyErrors by recreating required internal ranking
    columns before any sorting happens.
    """

    base = dfagg.copy()

    numeric_cols = [
        "win%", "win%_covid", "price_suggest_80", "price_suggest_80_covid",
        "last_close", "RSI", "capMil", "Marketcap",
        "one_week_performance", "one_month_performance",
        "three_month_performance", "six_month_performance",
        "value_range_score", "final_watch_score", "drop_alert_score",
        "regular_range_score", "covid_range_score",
    ]

    for col in numeric_cols:
        if col in base.columns:
            base[col] = pd.to_numeric(base[col], errors="coerce")

    if "capMil" not in base.columns:
        if "Marketcap" in base.columns:
            base["capMil"] = pd.to_numeric(base["Marketcap"], errors="coerce") / 1_000_000
        else:
            base["capMil"] = np.nan

    if "below_price_suggest_80" not in base.columns:
        if {"last_close", "price_suggest_80"}.issubset(base.columns):
            base["below_price_suggest_80"] = (base["last_close"] <= base["price_suggest_80"]).astype(int)
        else:
            base["below_price_suggest_80"] = 0

    if "below_price_suggest_80_covid" not in base.columns:
        if {"last_close", "price_suggest_80_covid"}.issubset(base.columns):
            base["below_price_suggest_80_covid"] = (base["last_close"] <= base["price_suggest_80_covid"]).astype(int)
        else:
            base["below_price_suggest_80_covid"] = 0

    if "regular_range_score" not in base.columns:
        if "win%" in base.columns:
            base["regular_range_score"] = base["win%"].clip(lower=0, upper=1) * 100
        elif "value_range_score" in base.columns:
            base["regular_range_score"] = base["value_range_score"]
        else:
            base["regular_range_score"] = 0

    if "covid_range_score" not in base.columns:
        if "win%_covid" in base.columns:
            base["covid_range_score"] = base["win%_covid"].clip(lower=0, upper=1) * 100
        elif "value_range_score" in base.columns:
            base["covid_range_score"] = base["value_range_score"]
        else:
            base["covid_range_score"] = 0

    if "largest_recent_drop" not in base.columns:
        perf_cols = [
            c for c in [
                "one_week_performance",
                "one_month_performance",
                "three_month_performance",
                "six_month_performance",
            ]
            if c in base.columns
        ]
        if perf_cols:
            base["largest_recent_drop"] = base[perf_cols].min(axis=1)
        else:
            base["largest_recent_drop"] = 0

    if "drop_alert_score" not in base.columns:
        base["drop_alert_score"] = base["largest_recent_drop"].clip(upper=0).abs().clip(upper=40) / 40 * 100

    if "value_range_score" not in base.columns:
        base["value_range_score"] = (
            base["regular_range_score"].fillna(0) * 0.50 +
            base["covid_range_score"].fillna(0) * 0.50
        )

    if "final_watch_score" not in base.columns:
        base["final_watch_score"] = (
            base["value_range_score"].fillna(0) * 0.70 +
            base["drop_alert_score"].fillna(0) * 0.30
        )

    if "watch_reason" not in base.columns:
        base["watch_reason"] = ""

    base_filtered = base.copy()

    # Action/ranking views should only rank stocks with usable price data.
    # Full Master still keeps every ticker through views["Full Master"] = base.
    if "price_status" in base_filtered.columns:
        base_filtered = base_filtered[base_filtered["price_status"].astype(str).eq("OK")].copy()

    if min_market_cap is not None and float(min_market_cap) > 0:
        base_filtered = base_filtered[pd.to_numeric(base_filtered["capMil"], errors="coerce") >= float(min_market_cap)].copy()

    if base_filtered.empty:
        print("WARNING: Price/market-cap filters returned zero rows. Ranked views will use price-valid rows when available, otherwise full master.")
        if "price_status" in base.columns and base["price_status"].astype(str).eq("OK").any():
            base_filtered = base[base["price_status"].astype(str).eq("OK")].copy()
        else:
            base_filtered = base.copy()

    regular_sort_cols = [c for c in ["regular_range_score", "win%", "below_price_suggest_80", "price_suggest_80"] if c in base_filtered.columns]
    covid_sort_cols = [c for c in ["covid_range_score", "win%_covid", "below_price_suggest_80_covid", "price_suggest_80_covid"] if c in base_filtered.columns]
    final_sort_cols = [c for c in ["final_watch_score", "value_range_score", "drop_alert_score"] if c in base_filtered.columns]

    regular = base_filtered.sort_values(
        regular_sort_cols,
        ascending=[False] * len(regular_sort_cols),
        na_position="last",
    ) if regular_sort_cols else base_filtered.copy()

    covid = base_filtered.sort_values(
        covid_sort_cols,
        ascending=[False] * len(covid_sort_cols),
        na_position="last",
    ) if covid_sort_cols else base_filtered.copy()

    final_watch = base_filtered.sort_values(
        final_sort_cols,
        ascending=[False] * len(final_sort_cols),
        na_position="last",
    ) if final_sort_cols else base_filtered.copy()

    if {"drop_alert_score", "largest_recent_drop"}.issubset(base_filtered.columns):
        recent_drops = base_filtered.sort_values(
            ["drop_alert_score", "largest_recent_drop"],
            ascending=[False, True],
            na_position="last",
        )
    elif "largest_recent_drop" in base_filtered.columns:
        recent_drops = base_filtered.sort_values("largest_recent_drop", ascending=True, na_position="last")
    else:
        recent_drops = base_filtered.copy()

    rsi = pd.to_numeric(base_filtered["RSI"], errors="coerce") if "RSI" in base_filtered.columns else pd.Series(np.nan, index=base_filtered.index)
    win = pd.to_numeric(base_filtered["win%"], errors="coerce") if "win%" in base_filtered.columns else pd.Series(np.nan, index=base_filtered.index)
    last_close = pd.to_numeric(base_filtered["last_close"], errors="coerce") if "last_close" in base_filtered.columns else pd.Series(np.nan, index=base_filtered.index)
    ps80 = pd.to_numeric(base_filtered["price_suggest_80"], errors="coerce") if "price_suggest_80" in base_filtered.columns else pd.Series(np.nan, index=base_filtered.index)

    high_conviction_mask = (
        (win >= 0.60) &
        (last_close <= ps80) &
        ((rsi <= 60) | rsi.isna())
    )

    top_high_conviction = base_filtered[high_conviction_mask].copy()
    if top_high_conviction.empty:
        top_high_conviction = final_watch.head(100).copy()
    else:
        top_high_conviction = top_high_conviction.sort_values(
            final_sort_cols,
            ascending=[False] * len(final_sort_cols),
            na_position="last",
        ).head(250) if final_sort_cols else top_high_conviction.head(250)

    near_ps80 = ps80.notna() & last_close.notna() & (last_close <= ps80 * 1.10)
    watchlist_mask = (
        (win >= 0.40) &
        near_ps80 &
        ((rsi <= 70) | rsi.isna())
    )

    watchlist_candidates = base_filtered[watchlist_mask].copy()
    if watchlist_candidates.empty:
        watchlist_candidates = regular.head(250).copy()
    else:
        watchlist_candidates = watchlist_candidates.sort_values(
            regular_sort_cols,
            ascending=[False] * len(regular_sort_cols),
            na_position="last",
        ).head(250) if regular_sort_cols else watchlist_candidates.head(250)

    return {
        "Final Watch": final_watch,
        "Regular Range": regular,
        "Covid Range": covid,
        "Recent Drops": recent_drops,
        "Top High Conviction": top_high_conviction,
        "Watchlist Candidates": watchlist_candidates,
        "Full Master": base,
    }

def get_column_dictionary(columns: list[str]) -> pd.DataFrame:
    """
    Build detailed descriptions for every exported column.
    """

    descriptions = {
        "Symbol": "Ticker symbol used for Yahoo Finance downloads. Dots are converted to hyphens where needed, for example BRK.B becomes BRK-B.",
        "Security": "Company or fund name when available from the imported index source or Yahoo metadata.",
        "Index": "Primary index/universe label assigned after combining imported sources.",
        "source_index": "Source-origin label showing where the ticker came from based on priority: S&P 500, NYSE, Nasdaq, Russell 2000, then Extra.",
        "Index_Origin": "Alternative source-origin field when available. Used to preserve where the symbol was imported from.",
        "price_status": "Minimal price-data audit flag. OK means the ticker has usable latest price data; MISSING_PRICE means the ticker stayed in Full Master but Yahoo/cache did not provide a usable price row.",
        "Sector": "Broad company sector from S&P metadata or Yahoo metadata.",
        "Sub_Sector": "More detailed industry or sub-industry classification.",
        "sector_temperature": "Hot, Neutral, Cold, or Unknown label for the stock's sector. Calculated from sector-level performance and breadth in this run.",
        "sector_hot_score": "Sector strength score calculated from average 1-week, 1-month, and 3-month performance, percent positive over 1 month, and average final_watch_score.",
        "stock_count": "Number of unique stocks in the sector summary group.",
        "avg_1w_performance": "Average one-week performance for stocks in the sector.",
        "avg_1m_performance": "Average one-month performance for stocks in the sector. Main driver of hot/cold status.",
        "avg_3m_performance": "Average three-month performance for stocks in the sector.",
        "pct_positive_1m": "Percent of stocks in the sector with positive one-month performance. Measures breadth.",
        "avg_final_watch_score": "Average final_watch_score for stocks in the sector.",
        "median_market_cap_mil": "Median market cap in millions for stocks in the sector.",
        "Date": "Most recent market date used for the row's latest price calculations.",

        "Marketcap": "Company market capitalization in dollars from Yahoo fundamentals. Used to filter ranking views to larger, more investable stocks.",
        "capMil": "Market capitalization in millions. Example: 2000 means approximately $2 billion. Ranking views are normally filtered to capMil >= 2000.",
        "AvgVol10d": "Average daily trading volume over roughly the last 10 trading days. Useful liquidity check.",
        "last_volume": "Volume on the latest available trading day.",
        "mean_vol": "Average volume across the downloaded history. Useful for comparing typical liquidity versus latest volume.",

        "last_close": "Latest available closing price. This is the current price anchor for most calculations.",
        "previousClose": "Previous trading day's close. Used to calculate prior_%_change.",
        "one_week_close": "Actual close price from about 5 trading days ago.",
        "one_month_close": "Actual close price from about 21 trading days ago.",
        "three_month_close": "Actual close price from about 63 trading days ago.",
        "six_month_close": "Actual close price from about 126 trading days ago.",
        "min": "Lowest close price in the downloaded price history for that symbol.",
        "max": "Highest close price in the downloaded price history for that symbol.",
        "minCovid": "Lowest close before the Covid cutoff period used in the script, if available.",
        "minCovid_filled": "Covid low fallback value. If minCovid is missing, the script fills it with regular min so Covid-based calculations still work.",

        "price_suggest_80": "Regular range threshold based on min and max. It represents the price level around 80% down from the high-to-low range and is used as a possible cheap-zone marker.",
        "price_suggest_80_covid": "Covid-adjusted threshold using minCovid_filled and max. Similar to price_suggest_80 but anchored to Covid-low framework.",
        "win%": "Regular range opportunity measure: (max - last_close) / (max - min). Higher means the stock is farther below its historical high relative to its range.",
        "win%_covid": "Covid-adjusted opportunity measure: (max - last_close) / (max - minCovid_filled). Higher means more potential recovery relative to Covid-adjusted range.",
        "below_price_suggest_80": "1 if last_close is less than or equal to price_suggest_80, otherwise 0.",
        "below_price_suggest_80_covid": "1 if last_close is less than or equal to price_suggest_80_covid, otherwise 0.",
        "Percent_min_price": "How far current price is above the relevant low, expressed as a percentage. Lower means price is closer to the low.",
        "Is_Covid_Low": "Text label describing how current low compares with Covid-era low logic.",

        "final_watch_score": "Main blended ranking score. Higher means higher review priority.",
        "value_range_score": "Main value/range score built from win%, win%_covid, and price-suggest threshold logic.",
        "drop_alert_score": "Recent selloff score. Higher means a larger recent negative move and more need for attention.",
        "watch_reason": "Plain-English reason tags explaining why the stock appeared in a ranked or filtered view.",

        "prior_%_change": "Percent move from previousClose to last_close.",
        "one_week_performance": "Percent return from one_week_close to last_close.",
        "one_month_performance": "Percent return from one_month_close to last_close.",
        "three_month_performance": "Percent return from three_month_close to last_close.",
        "six_month_performance": "Percent return from six_month_close to last_close.",
        "ytd": "Year-to-date return based on available price history and latest close.",
        "largest_recent_drop": "Most negative recent performance across selected windows. Used to surface stocks that recently sold off.",

        "RSI": "Relative Strength Index. Below 30 is commonly considered oversold; above 70 is commonly considered overbought.",
        "Sentiment": "Simple RSI label: Oversold, Neutral, or Overbought.",
        "is_basing": "Flag indicating whether the stock appears to be consolidating near a recent low based on range and recent performance rules.",
        "range_pct_21d": "Recent 21-day high-low range divided by the 21-day high. Lower values can indicate tighter consolidation.",
        "Pivot_5d": "Short-term pivot level calculated from recent high/low/close logic.",
        "Support1_5d": "First short-term support estimate from pivot calculation.",
        "Resistance1_5d": "First short-term resistance estimate from pivot calculation.",
        "next_support_1": "Nearest historical support level below current price.",
        "next_support_2": "Second historical support level below current price.",
        "next_support_3": "Third historical support level below current price.",
        "next_resistance_1": "Nearest historical resistance level above current price.",
        "next_resistance_2": "Second historical resistance level above current price.",
        "next_resistance_3": "Third historical resistance level above current price.",

        "debtToEquity": "Debt-to-equity ratio from Yahoo fundamentals. Lower can indicate less leverage, but interpretation varies by industry.",
        "shortRatio": "Short interest ratio / days to cover from Yahoo when available.",
        "priceToBook": "Price-to-book ratio. Lower can suggest cheaper book valuation, but usefulness varies heavily by sector.",
        "description": "Long business summary from Yahoo fundamentals. Used for keyword flags and manual review.",

        "min_date": "Date when lowest close occurred in downloaded history.",
        "max_date": "Date when highest close occurred in downloaded history.",
        "mincovid_date": "Date when minCovid occurred, if available.",
        "flag": "1 if symbol is in your watchlist/extra ticker set, otherwise 0.",
        "is_extra": "1 if symbol came from manually maintained extra_tickers list, otherwise 0.",
        "is_key": "1 if company description contains one of your keyword themes.",
    }

    rows = []
    for col in columns:
        rows.append({
            "Column": col,
            "Description": descriptions.get(col, "No description defined yet. Review this column in the script and add a custom description if it becomes important."),
        })

    return pd.DataFrame(rows)

def _sheet_guide_row(sheet_name: str, df: pd.DataFrame | None = None) -> dict:
    """Return plain-English guide details for each workbook tab."""
    default = {
        "Purpose / What It Answers": "Additional output sheet generated by the scanner.",
        "Filter / Inclusion Rules": "See columns on the sheet. If stock-level, rows generally require valid price data unless this is Full Master.",
        "What It Measures": "Depends on the score/ranking columns shown on the sheet.",
        "Ranking / Sort Logic": "See the first/highlighted score or rank column on the sheet.",
        "How To Use It": "Use as a supporting view, then check Full Master for all details.",
    }

    guides = {
        "Sector Summary": {
            "Purpose / What It Answers": "Shows which sectors are hot, neutral, or cold based on the stocks in this run.",
            "Filter / Inclusion Rules": "Sector-level view; no capMil filter because each row is a sector, not a stock.",
            "What It Measures": "Average 1W/1M/3M performance, sector breadth, average score, and sector_hot_score.",
            "Ranking / Sort Logic": "Sorted by sector_hot_score descending.",
            "How To Use It": "Start here to understand market leadership before reviewing individual stocks.",
        },
        "Final Watch": {
            "Purpose / What It Answers": "Best broad opportunity list using value, recent drop, technicals, and fundamentals.",
            "Filter / Inclusion Rules": "Stock-level action sheet; capMil >= min_market_cap, normally 2000 = $2B; requires usable price data.",
            "What It Measures": "final_watch_score blends value_range_score, drop_alert_score, technical_score, and fundamental_score.",
            "Ranking / Sort Logic": "Sorted by final_watch_score descending.",
            "How To Use It": "Use this as your main ranked review list after checking the Summary.",
        },
        "Regular Range": {
            "Purpose / What It Answers": "Which stocks are attractive based on the regular min-to-max price range.",
            "Filter / Inclusion Rules": "capMil >= min_market_cap, normally $2B; requires usable price data.",
            "What It Measures": "win% and price_suggest_80 using the regular historical low/high range.",
            "Ranking / Sort Logic": "Sorted mainly by regular_range_score / win% descending.",
            "How To Use It": "Higher win% means farther below historical highs; verify the business is not broken.",
        },
        "Covid Range": {
            "Purpose / What It Answers": "Which stocks are attractive using Covid-low adjusted range logic.",
            "Filter / Inclusion Rules": "capMil >= min_market_cap, normally $2B; requires usable price data.",
            "What It Measures": "win%_covid and price_suggest_80_covid using minCovid_filled as the low anchor.",
            "Ranking / Sort Logic": "Sorted mainly by covid_range_score / win%_covid descending.",
            "How To Use It": "Use for longer-cycle recovery ideas; compare to Regular Range.",
        },
        "Recent Drops": {
            "Purpose / What It Answers": "Which stocks have been hit hardest recently.",
            "Filter / Inclusion Rules": "capMil >= min_market_cap, normally $2B; requires usable price data.",
            "What It Measures": "largest_recent_drop and drop_alert_score across recent performance windows.",
            "Ranking / Sort Logic": "Sorted by drop_alert_score descending and worst recent performance.",
            "How To Use It": "Use as an alert sheet, not a buy list. Check if the drop is temporary or fundamental.",
        },
        "Top High Conviction": {
            "Purpose / What It Answers": "Shortest original action list of stronger value setups.",
            "Filter / Inclusion Rules": "capMil >= min_market_cap, win% >= threshold, last_close <= price_suggest_80, RSI <= 60 or missing; requires usable price data.",
            "What It Measures": "Value setup quality using win%, price_suggest_80, RSI, and final_watch_score.",
            "Ranking / Sort Logic": "Sorted by final_watch_score / value_range_score descending.",
            "How To Use It": "Review these first if you want a compact list from the original model.",
        },
        "Watchlist Candidates": {
            "Purpose / What It Answers": "Broader list of stocks close to becoming attractive.",
            "Filter / Inclusion Rules": "capMil >= min_market_cap, win% >= moderate threshold, price near price_suggest_80, RSI <= 70 or missing; requires usable price data.",
            "What It Measures": "Potential candidates approaching your value/range thresholds.",
            "Ranking / Sort Logic": "Sorted by regular range/value scores descending.",
            "How To Use It": "Use for follow-up monitoring; not as strong as Top High Conviction.",
        },
        "Full Master": {
            "Purpose / What It Answers": "Complete audit table with every universe ticker retained.",
            "Filter / Inclusion Rules": "No capMil filter. Starts from universe_df, so tickers stay even if price download failed. Check price_status.",
            "What It Measures": "All available price, performance, range, sector, score, and fundamental fields.",
            "Ranking / Sort Logic": "Not a ranked action sheet. Use Excel filters/sorts as needed.",
            "How To Use It": "Use for troubleshooting, missing data review, or deeper manual analysis.",
        },
        "V10_6 Summary": {
            "Purpose / What It Answers": "Dashboard with top rows from the final filtered V10_6 detail sheets.",
            "Filter / Inclusion Rules": "Built from already-filtered V10_6 sheets; counts should align with those detail sheets.",
            "What It Measures": "Top high conviction, hot sector drops, recovery candidates, reversals, largest drops, and sector heat.",
            "Ranking / Sort Logic": "Each section inherits the ranking from its related detail sheet.",
            "How To Use It": "Open this first. Drill into the matching detail sheet when a name catches your attention.",
        },
        "V10_6 High Conviction": {
            "Purpose / What It Answers": "Enhanced best-overall setup list.",
            "Filter / Inclusion Rules": "capMil >= min_market_cap, normally $2B; price_status OK; sorted from enhanced master.",
            "What It Measures": "priority_score combines hot_drop_score, recovery_score, reversal_setup_score, and range position.",
            "Ranking / Sort Logic": "Sorted by priority_score descending.",
            "How To Use It": "Use this as the enhanced model's top review list.",
        },
        "Hot Sector Drops": {
            "Purpose / What It Answers": "Which stocks are dropping while their sector is still hot.",
            "Filter / Inclusion Rules": "capMil >= min_market_cap, price_status OK, sector_temp = HOT, perf_1m <= -5%.",
            "What It Measures": "Quality pullbacks inside strong sectors using hot_drop_score.",
            "Ranking / Sort Logic": "Sorted by hot_drop_score descending.",
            "How To Use It": "This is one of the most useful pullback sheets. Small row counts are normal when few hot-sector stocks are down 5%+.",
        },
        "Recovery Candidates": {
            "Purpose / What It Answers": "Which stocks may have rebound potential.",
            "Filter / Inclusion Rules": "capMil >= min_market_cap and price_status OK.",
            "What It Measures": "recovery_score blends range_position_1y, recent drop magnitude, sector heat, and RSI.",
            "Ranking / Sort Logic": "Sorted by recovery_score descending.",
            "How To Use It": "Look for high range position plus improving/acceptable fundamentals.",
        },
        "Reversal Setups": {
            "Purpose / What It Answers": "Which stocks may be technically oversold or nearing a bounce setup.",
            "Filter / Inclusion Rules": "capMil >= min_market_cap, price_status OK, usually RSI <= 45.",
            "What It Measures": "reversal_setup_score using RSI, short-term range position, recent drop, and sector heat.",
            "Ranking / Sort Logic": "Sorted by reversal_setup_score descending.",
            "How To Use It": "Use for possible bounce candidates; confirm with chart/support/news.",
        },
        "Largest 1W Drops": {
            "Purpose / What It Answers": "Which stocks fell the most over the last 5 trading days.",
            "Filter / Inclusion Rules": "capMil >= min_market_cap and price_status OK.",
            "What It Measures": "perf_1w and rank_drop_1w.",
            "Ranking / Sort Logic": "Sorted by rank_drop_1w ascending; rank 1 = biggest drop.",
            "How To Use It": "Use to catch fresh selloffs quickly.",
        },
        "Largest 2W Drops": {
            "Purpose / What It Answers": "Which stocks fell the most over the last 10 trading days.",
            "Filter / Inclusion Rules": "capMil >= min_market_cap and price_status OK.",
            "What It Measures": "perf_2w and rank_drop_2w.",
            "Ranking / Sort Logic": "Sorted by rank_drop_2w ascending; rank 1 = biggest drop.",
            "How To Use It": "Use to identify sustained two-week weakness.",
        },
        "Largest 1M Drops": {
            "Purpose / What It Answers": "Which stocks fell the most over the last 21 trading days.",
            "Filter / Inclusion Rules": "capMil >= min_market_cap and price_status OK.",
            "What It Measures": "perf_1m and rank_drop_1m.",
            "Ranking / Sort Logic": "Sorted by rank_drop_1m ascending; rank 1 = biggest monthly drop.",
            "How To Use It": "Use to find medium-term corrections.",
        },
        "Highest Range Position": {
            "Purpose / What It Answers": "Which stocks are furthest below their 52-week range high.",
            "Filter / Inclusion Rules": "capMil >= min_market_cap and price_status OK.",
            "What It Measures": "range_position_1y, range_position_6m, and range_position_3m.",
            "Ranking / Sort Logic": "Sorted by range_position_1y descending.",
            "How To Use It": "High value means beaten down; verify it is not permanently impaired.",
        },
        "V10_6 Sector Heatmap": {
            "Purpose / What It Answers": "Which sectors are strongest or weakest in the enhanced logic.",
            "Filter / Inclusion Rules": "Sector-level sheet; no capMil filter.",
            "What It Measures": "sector_avg_1w, sector_avg_1m, sector_avg_3m, sector_hot_score, sector_temp.",
            "Ranking / Sort Logic": "Sorted by sector_hot_score descending.",
            "How To Use It": "Use with Hot Sector Drops to separate quality pullbacks from weak-sector declines.",
        },
        "V10_6 Sheet Filters": {
            "Purpose / What It Answers": "Plain-English reference explaining each V10_6 sheet filter.",
            "Filter / Inclusion Rules": "Reference sheet only.",
            "What It Measures": "Documentation, not stock performance.",
            "Ranking / Sort Logic": "Not ranked.",
            "How To Use It": "Use when a sheet has fewer rows than expected.",
        },
    }
    return guides.get(sheet_name, default)


def build_table_of_contents(views: dict[str, pd.DataFrame], csv_outputs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Build a complete, plain-English guide for every workbook tab and CSV output."""
    rows = []

    # Workbook overview row.
    rows.append({
        "Type": "Workbook",
        "Name": "stock_rankings.xlsx",
        "Output Location": str(OUTPUT_WORKBOOK),
        "Row Count": "",
        "Purpose / What It Answers": "Main daily review workbook. Open Summary/V10_6 Summary first, then drill into detail sheets.",
        "Filter / Inclusion Rules": "Workbook contains both full audit tabs and filtered action tabs.",
        "What It Measures": "Value/range position, recent drops, sector heat, technical setup, and fundamentals.",
        "Ranking / Sort Logic": "Each tab has its own ranking; see rows below.",
        "How To Use It": "Use Full Master for all tickers; use action sheets for research candidates.",
        "Key Columns to Review": "price_status, capMil, last_close, win%, perf_1w/perf_1m, RSI, sector_temperature/sector_temp, final_watch_score/priority_score",
    })

    for sheet_name, df in views.items():
        if not isinstance(df, pd.DataFrame):
            continue
        guide = _sheet_guide_row(sheet_name, df)
        rows.append({
            "Type": "Sheet",
            "Name": sheet_name,
            "Output Location": f"stock_rankings.xlsx -> {sheet_name[:31]}",
            "Row Count": len(df),
            "Purpose / What It Answers": guide["Purpose / What It Answers"],
            "Filter / Inclusion Rules": guide["Filter / Inclusion Rules"],
            "What It Measures": guide["What It Measures"],
            "Ranking / Sort Logic": guide["Ranking / Sort Logic"],
            "How To Use It": guide["How To Use It"],
            "Key Columns to Review": ", ".join(list(df.columns[:18])) if not df.empty else "No rows",
        })

    # Column Dictionary is written separately, but add it to TOC.
    full_master = views.get("Full Master", pd.DataFrame())
    rows.append({
        "Type": "Sheet",
        "Name": "Column Dictionary",
        "Output Location": "stock_rankings.xlsx -> Column Dictionary",
        "Row Count": len(get_column_dictionary(list(full_master.columns))) if isinstance(full_master, pd.DataFrame) else "",
        "Purpose / What It Answers": "Explains what each Full Master column means.",
        "Filter / Inclusion Rules": "Documentation sheet only.",
        "What It Measures": "Column definitions and interpretation notes.",
        "Ranking / Sort Logic": "Not ranked.",
        "How To Use It": "Use when you forget what a metric means.",
        "Key Columns to Review": "Column, Description",
    })

    for file_name, df in csv_outputs.items():
        rows.append({
            "Type": "CSV",
            "Name": file_name,
            "Output Location": str(OUTPUT_DIR / file_name),
            "Row Count": len(df) if isinstance(df, pd.DataFrame) else "",
            "Purpose / What It Answers": "Quick CSV copy of one action sheet.",
            "Filter / Inclusion Rules": "Same as source workbook sheet.",
            "What It Measures": "Same as source workbook sheet.",
            "Ranking / Sort Logic": "Same as source workbook sheet.",
            "How To Use It": "Use for quick external review or sharing.",
            "Key Columns to Review": ", ".join(list(df.columns[:12])) if isinstance(df, pd.DataFrame) and not df.empty else "No rows",
        })

    return pd.DataFrame(rows)


def _autosize_worksheets(workbook_path: Path) -> None:
    """
    Format workbook:
    - autosize columns
    - freeze top row
    - add filters
    - highlight important sorted columns in each sheet
    """
    from openpyxl import load_workbook
    from openpyxl.styles import PatternFill, Font, Alignment
    from openpyxl.utils import get_column_letter

    wb = load_workbook(workbook_path)

    default_header_fill = PatternFill("solid", fgColor="D9EAF7")
    sorted_header_fill = PatternFill("solid", fgColor="FFD966")
    toc_fill = PatternFill("solid", fgColor="E2F0D9")

    sort_columns_by_sheet = {
        "Sector Summary": ["sector_hot_score", "sector_temperature"],
        "Final Watch": ["final_watch_score"],
        "Regular Range": ["win%", "price_suggest_80"],
        "Covid Range": ["win%_covid", "price_suggest_80_covid"],
        "Recent Drops": ["drop_alert_score", "largest_recent_drop"],
        "Top High Conviction": ["final_watch_score", "value_range_score", "win%"],
        "Watchlist Candidates": ["value_range_score", "final_watch_score", "win%"],
        "Full Master": [],
        "Column Dictionary": ["Column"],
        "Table of Contents": ["Name", "Row Count"],
    }

    for ws in wb.worksheets:
        ws.freeze_panes = "A2"

        if ws.max_row >= 1 and ws.max_column >= 1:
            ws.auto_filter.ref = ws.dimensions

        sorted_cols = set(sort_columns_by_sheet.get(ws.title, []))

        for cell in ws[1]:
            header = str(cell.value) if cell.value is not None else ""
            if header in sorted_cols:
                cell.fill = sorted_header_fill
            elif ws.title == "Table of Contents":
                cell.fill = toc_fill
            else:
                cell.fill = default_header_fill

            cell.font = Font(bold=True)
            cell.alignment = Alignment(wrap_text=True, vertical="center")

        for col_idx, column_cells in enumerate(ws.columns, start=1):
            max_length = 0
            for cell in list(column_cells)[:200]:
                value = "" if cell.value is None else str(cell.value)
                max_length = max(max_length, len(value))
            ws.column_dimensions[get_column_letter(col_idx)].width = min(max(max_length + 2, 10), 55)

        if ws.title in {"Table of Contents", "Column Dictionary"}:
            for row in ws.iter_rows():
                for cell in row:
                    cell.alignment = Alignment(wrap_text=True, vertical="top")
            ws.sheet_view.showGridLines = False

    wb.save(workbook_path)


# =============================================================================
# CLEAN EXPORT COLUMN SELECTION
# =============================================================================

CORE_REVIEW_COLUMNS = [
    "Symbol", "Security", "Index", "Index_Origin", "Sector", "Sub_Sector",
    "price_status", "sector_temperature", "sector_hot_score", "sector_temp",
    "Marketcap", "capMil", "Date", "latest_price_date",
    "last_close", "previousClose",
    "price_suggest_80", "price_suggest_80_covid", "win%", "win%_covid",
    "final_watch_score", "value_range_score", "drop_alert_score", "priority_score",
    "watch_reason",
    "one_week_performance", "one_month_performance", "three_month_performance", "six_month_performance",
    "perf_1w", "perf_2w", "perf_1m", "perf_3m", "perf_6m",
    "largest_recent_drop", "RSI", "Sentiment",
    "range_position_1y", "range_position_6m", "range_position_3m",
    "hot_drop_score", "recovery_score", "reversal_setup_score",
    "Pivot_5d", "Support1_5d", "Resistance1_5d",
    "next_support_1", "next_resistance_1",
    "AvgVol10d", "last_volume", "mean_vol",
    "debtToEquity", "shortRatio", "priceToBook",
    "flag", "is_extra", "is_key",
]

SHEET_SPECIFIC_COLUMNS = {
    "Sector Summary": [
        "Sector", "stock_count", "avg_1w_performance", "avg_1m_performance", "avg_3m_performance",
        "pct_positive_1m", "avg_final_watch_score", "median_market_cap_mil", "sector_hot_score", "sector_temperature"
    ],
    "V10_6 Sector Heatmap": [
        "Sector", "sector_count", "sector_avg_1w", "sector_avg_1m", "sector_avg_3m", "sector_hot_score", "sector_temp"
    ],
    "V10_6 Summary": [
        "Section", "Symbol", "Security", "Sector", "Index", "price_status", "Marketcap", "capMil",
        "debtToEquity", "revenueGrowth", "freeCashFlow", "returnOnEquity", "priceToBook", "quality_score", "quality_reason",
        "last_close", "perf_1w", "perf_2w", "perf_1m", "RSI", "range_position_1y", "sector_temp",
        "hot_drop_score", "recovery_score", "reversal_setup_score", "priority_score",
        "sector_avg_1w", "sector_avg_1m", "sector_avg_3m", "sector_hot_score", "sector_count", "Note"
    ],
    "Hot Sector Drops": [
        "Symbol", "Security", "Sector", "Index", "price_status", "Marketcap", "capMil", "last_close",
        "perf_1m", "perf_1w", "RSI", "sector_temp", "sector_hot_score", "range_position_1y", "hot_drop_score",
        "recovery_score", "priority_score", "watch_reason"
    ],
    "Recovery Candidates": [
        "Symbol", "Security", "Sector", "Index", "price_status", "Marketcap", "capMil", "last_close",
        "range_position_1y", "range_position_6m", "range_position_3m", "perf_1m", "perf_1w", "RSI",
        "sector_temp", "sector_hot_score", "recovery_score", "priority_score", "watch_reason"
    ],
    "Reversal Setups": [
        "Symbol", "Security", "Sector", "Index", "price_status", "Marketcap", "capMil", "last_close",
        "RSI", "Sentiment", "range_position_3m", "perf_1w", "perf_1m", "sector_temp", "sector_hot_score",
        "reversal_setup_score", "priority_score", "Support1_5d", "Resistance1_5d"
    ],
    "Largest 1W Drops": [
        "Symbol", "Security", "Sector", "Index", "price_status", "Marketcap", "capMil", "last_close",
        "perf_1w", "rank_drop_1w", "perf_2w", "perf_1m", "RSI", "sector_temp", "range_position_1y", "priority_score"
    ],
    "Largest 2W Drops": [
        "Symbol", "Security", "Sector", "Index", "price_status", "Marketcap", "capMil", "last_close",
        "perf_2w", "rank_drop_2w", "perf_1w", "perf_1m", "RSI", "sector_temp", "range_position_1y", "priority_score"
    ],
    "Largest 1M Drops": [
        "Symbol", "Security", "Sector", "Index", "price_status", "Marketcap", "capMil", "last_close",
        "perf_1m", "rank_drop_1m", "perf_1w", "perf_2w", "RSI", "sector_temp", "range_position_1y", "priority_score"
    ],
    "Highest Range Position": [
        "Symbol", "Security", "Sector", "Index", "price_status", "Marketcap", "capMil", "last_close",
        "range_position_1y", "rank_range_1y", "range_position_6m", "range_position_3m", "perf_1m", "RSI", "sector_temp", "priority_score"
    ],
    "V10_6 High Conviction": [
        "Symbol", "Security", "Sector", "Index", "price_status", "Marketcap", "capMil", "last_close",
        "priority_score", "hot_drop_score", "recovery_score", "reversal_setup_score", "range_position_1y",
        "perf_1w", "perf_1m", "RSI", "sector_temp", "watch_reason"
    ],
}

GUIDE_OR_DOC_SHEETS = {
    "V10_6 Sheet Filters",
}


def slim_sheet_for_export(sheet_name: str, df: pd.DataFrame) -> pd.DataFrame:
    """
    Keep Full Master detailed, but keep action sheets readable.

    This prevents V10_6 enhancement/internal columns from flooding every sheet.
    The calculations still exist internally and in Full Master; review sheets only show
    the columns needed to use that sheet.
    """
    if not isinstance(df, pd.DataFrame) or df.empty:
        return df

    # Full Master intentionally keeps everything for audit/debugging.
    if sheet_name == "Full Master":
        return df

    # Documentation sheets keep their natural columns.
    if sheet_name in GUIDE_OR_DOC_SHEETS:
        return df

    columns = SHEET_SPECIFIC_COLUMNS.get(sheet_name, CORE_REVIEW_COLUMNS)
    existing = [c for c in columns if c in df.columns]

    # If no match, keep current output rather than risking a blank sheet.
    if not existing:
        return df

    return df[existing].copy()

def export_outputs(views: dict[str, pd.DataFrame]) -> None:
    """Export one workbook plus three action CSVs only.

    Important:
    - views may contain internal score columns used for ranking.
    - clean_views hides/reorders columns only at the final export step.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    clean_views = {}
    for name, df in views.items():
        if isinstance(df, pd.DataFrame):
            cleaned = reorder_columns(df.copy())
            if name == "Summary":
                cleaned = reorder_v10_6_summary_columns(cleaned)
            cleaned = slim_sheet_for_export(name, cleaned)
            clean_views[name] = cleaned
        else:
            clean_views[name] = df

    csv_outputs = {
        "top_high_conviction.csv": clean_views.get("Top High Conviction", pd.DataFrame()),
        "top_watchlist_candidates.csv": clean_views.get("Watchlist Candidates", pd.DataFrame()),
        "top_recent_drops.csv": clean_views.get("Recent Drops", pd.DataFrame()).head(250),
    }

    for file_name, df in csv_outputs.items():
        df.to_csv(OUTPUT_DIR / file_name, index=False)

    toc = build_table_of_contents(clean_views, csv_outputs)
    col_dict = get_column_dictionary(list(clean_views.get("Full Master", pd.DataFrame()).columns))

    output_workbook = OUTPUT_WORKBOOK

    try:
        with pd.ExcelWriter(output_workbook, engine="openpyxl") as writer:
            toc.to_excel(writer, sheet_name="Table of Contents", index=False)
            col_dict.to_excel(writer, sheet_name="Column Dictionary", index=False)
            for sheet, view in clean_views.items():
                view.to_excel(writer, sheet_name=sheet[:31], index=False)
    except PermissionError:
        # This usually happens when stock_rankings.xlsx is open in Excel.
        # Save to a timestamped fallback so the run still completes.
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_workbook = OUTPUT_DIR / f"stock_rankings_{timestamp}.xlsx"
        print(f"WARNING: {OUTPUT_WORKBOOK} is locked/open. Saving fallback workbook: {output_workbook}")

        with pd.ExcelWriter(output_workbook, engine="openpyxl") as writer:
            toc.to_excel(writer, sheet_name="Table of Contents", index=False)
            col_dict.to_excel(writer, sheet_name="Column Dictionary", index=False)
            for sheet, view in clean_views.items():
                view.to_excel(writer, sheet_name=sheet[:31], index=False)

    _autosize_worksheets(output_workbook)
    print(f"Saved workbook: {output_workbook}")
    for file_name in csv_outputs:
        print(f"Saved CSV: {OUTPUT_DIR / file_name}")

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stock Analysis V10 Scanner")
    parser.add_argument("--universe", default="all", choices=["all", "sp500", "nasdaq", "russell", "russell2000", "nyse", "extra", "watchlist"])
    parser.add_argument("--mode", default="incremental", choices=["incremental", "full"], help="Price history mode")
    parser.add_argument("--start-date", default="2020-03-01")
    parser.add_argument("--chunk-size", type=int, default=100)
    parser.add_argument("--delay", type=float, default=1.5)
    parser.add_argument("--fundamentals-mode", default="missing", choices=["missing", "force", "skip"])
    parser.add_argument("--min-market-cap", type=float, default=2000, help="Minimum market cap in millions for ranked/action views; 2000 = $2B. Full Master keeps all.")
    parser.add_argument("--max-tickers", type=int, default=0, help="Optional testing limit; 0 means all")
    parser.add_argument("--no-extra", action="store_true", help="Disable force-including DEFAULT_EXTRA_TICKERS and config/extra_tickers.csv")

    argv = sys.argv[1:]
    if any(("ipykernel" in a.lower()) or a.lower().endswith(".json") or a.startswith("--f=") for a in argv):
        argv = []
    args, unknown = parser.parse_known_args(argv)
    if unknown:
        print(f"Extra arguments ignored: {unknown}")
    return args



def filter_enhancement_view_by_market_cap(view: pd.DataFrame, min_market_cap: float = 2000) -> pd.DataFrame:
    """
    Apply the same large-cap filter to V10_6 enhancement views.

    min_market_cap is in millions. Example: 2000 = $2B.
    Full Master and pure sector summary views should remain unfiltered.
    """
    if not isinstance(view, pd.DataFrame) or view.empty:
        return view

    out = view.copy()

    # Some enhancement views may use Marketcap but not capMil.
    if "capMil" not in out.columns and "Marketcap" in out.columns:
        out["capMil"] = pd.to_numeric(out["Marketcap"], errors="coerce") / 1_000_000

    if "capMil" not in out.columns:
        return out

    if min_market_cap is None or float(min_market_cap) <= 0:
        return out

    filtered = out[pd.to_numeric(out["capMil"], errors="coerce") >= float(min_market_cap)].copy()
    return filtered



def enrich_v10_6_summary_with_market_cap(summary_df: pd.DataFrame, master_df: pd.DataFrame) -> pd.DataFrame:
    """
    Add Marketcap and capMil to the V10_6 Summary stacked dashboard wherever a Symbol exists.

    Sector-only summary rows do not have a Symbol, so they remain blank for stock-level
    market-cap columns.
    """
    if not isinstance(summary_df, pd.DataFrame) or summary_df.empty:
        return summary_df

    out = summary_df.copy()
    if "Symbol" not in out.columns or not isinstance(master_df, pd.DataFrame) or master_df.empty:
        return out

    master = master_df.copy()
    if "Symbol" not in master.columns:
        return out

    if "capMil" not in master.columns and "Marketcap" in master.columns:
        master["capMil"] = pd.to_numeric(master["Marketcap"], errors="coerce") / 1_000_000

    add_cols = [c for c in ["Symbol", "Marketcap", "capMil"] if c in master.columns]
    if len(add_cols) <= 1:
        return out

    cap_lookup = master[add_cols].drop_duplicates("Symbol")

    # Avoid duplicate columns if enhancement module later adds them directly.
    out = out.drop(columns=[c for c in ["Marketcap", "capMil"] if c in out.columns], errors="ignore")
    out = out.merge(cap_lookup, on="Symbol", how="left")

    # Put market cap near the front of the dashboard.
    preferred_front = ["Section", "Symbol", "Security", "Sector", "Index", "Marketcap", "capMil"]
    ordered = [c for c in preferred_front if c in out.columns]
    remaining = [c for c in out.columns if c not in ordered]
    return out[ordered + remaining]


def build_v10_6_sheet_filter_guide(min_market_cap: float = 2000) -> pd.DataFrame:
    """Create a sheet explaining the filters used by each V10_6 enhancement tab."""
    cap_filter = f"price_status == OK; capMil >= {float(min_market_cap):,.0f} million" if min_market_cap and float(min_market_cap) > 0 else "price_status == OK; no market-cap filter"
    rows = [
        ("V10_6 Summary", cap_filter + " for stock sections; sector sections are not stock-level filtered", "Stacked top-10 dashboard sections", "Marketcap/capMil shown for stock rows only"),
        ("V10_6 High Conviction", cap_filter, "Top 100 sorted by priority_score descending", "Broadest enhanced opportunity list"),
        ("Hot Sector Drops", cap_filter + "; sector_temp == HOT; perf_1m <= -5", "Sorted by hot_drop_score descending; top 100 before export cap", "Can be small when few hot sectors are pulling back"),
        ("Recovery Candidates", cap_filter, "Top 100 sorted by recovery_score descending", "Uses range_position_1y, one-month drop, RSI, and sector heat"),
        ("Reversal Setups", cap_filter + "; RSI <= 45 where RSI exists", "Sorted by reversal_setup_score descending; top 100", "Can be small if not many large-cap stocks are oversold"),
        ("Largest 1W Drops", cap_filter, "Top 100 sorted by rank_drop_1w / perf_1w most negative", "Shows largest recent 5-trading-day selloffs"),
        ("Largest 2W Drops", cap_filter, "Top 100 sorted by rank_drop_2w / perf_2w most negative", "Shows largest 10-trading-day selloffs"),
        ("Largest 1M Drops", cap_filter, "Top 100 sorted by rank_drop_1m / perf_1m most negative", "Shows largest 21-trading-day selloffs"),
        ("Highest Range Position", cap_filter, "Top 100 sorted by range_position_1y descending", "Higher means farther below 52-week high within 52-week range"),
        ("V10_6 Sector Heatmap", "No capMil filter", "Sector-level aggregation sorted by sector_hot_score", "Rows are sectors, not stocks"),
    ]
    return pd.DataFrame(rows, columns=["Sheet", "Filter", "Ranking / Sort", "Why row count may be small"])



def _sort_head(df: pd.DataFrame, sort_col: str, ascending: bool = False, n: int = 100) -> pd.DataFrame:
    """Sort defensively and return top n rows."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()
    out = df.copy()
    if sort_col not in out.columns:
        return out.head(n)
    return out.sort_values(sort_col, ascending=ascending, na_position="last").head(n)


def build_v10_6_views_from_filtered_master(
    dfagg_enhanced: pd.DataFrame,
    enhanced_sheet_dict: dict,
    min_market_cap: float = 2000,
) -> dict[str, pd.DataFrame]:
    """
    Build V10_6 sheets from the fully enhanced master data AFTER applying capMil.

    This fixes two issues:
    1. Filtering after a top-100 cut can leave only a few rows. We now filter first,
       then select top 100.
    2. Summary is built from the final filtered sheets, so Summary counts can never
       exceed the detail sheet counts.
    """
    if not isinstance(dfagg_enhanced, pd.DataFrame) or dfagg_enhanced.empty:
        return {}

    base = dfagg_enhanced.copy()

    if "capMil" not in base.columns and "Marketcap" in base.columns:
        base["capMil"] = pd.to_numeric(base["Marketcap"], errors="coerce") / 1_000_000

    filtered = base.copy()

    # V10_6 action sheets should not rank missing-price rows, but Full Master still keeps them.
    if "price_status" in filtered.columns:
        filtered = filtered[filtered["price_status"].astype(str).eq("OK")].copy()

    if "capMil" in filtered.columns and min_market_cap is not None and float(min_market_cap) > 0:
        filtered = filtered[pd.to_numeric(filtered["capMil"], errors="coerce") >= float(min_market_cap)].copy()

    # If fundamentals are skipped or capMil is missing for too many rows, do not silently create empty tabs.
    if filtered.empty:
        print("WARNING: V10_6 price/capMil filters returned zero rows. V10_6 views will use price-valid rows when available, otherwise enhanced master.")
        if "price_status" in base.columns and base["price_status"].astype(str).eq("OK").any():
            filtered = base[base["price_status"].astype(str).eq("OK")].copy()
        else:
            filtered = base.copy()

    sector_heat = pd.DataFrame()
    if isinstance(enhanced_sheet_dict, dict):
        sector_heat = enhanced_sheet_dict.get("Sector_Heatmap", pd.DataFrame())

    # Build all stock-level tabs from the same filtered base.
    high_conviction = _sort_head(filtered, "priority_score", ascending=False, n=100)

    hot_sector_drops_base = filtered.copy()
    if "sector_temp" in hot_sector_drops_base.columns:
        hot_sector_drops_base = hot_sector_drops_base[hot_sector_drops_base["sector_temp"].astype(str).str.upper().eq("HOT")]
    if "perf_1m" in hot_sector_drops_base.columns:
        hot_sector_drops_base = hot_sector_drops_base[pd.to_numeric(hot_sector_drops_base["perf_1m"], errors="coerce") <= -5]
    hot_sector_drops = _sort_head(hot_sector_drops_base, "hot_drop_score", ascending=False, n=100)

    recovery_candidates = _sort_head(filtered, "recovery_score", ascending=False, n=100)

    reversal_base = filtered.copy()
    if "RSI" in reversal_base.columns:
        reversal_base = reversal_base[pd.to_numeric(reversal_base["RSI"], errors="coerce") <= 45]
    reversal_setups = _sort_head(reversal_base, "reversal_setup_score", ascending=False, n=100)

    largest_1w_drops = _sort_head(filtered, "perf_1w", ascending=True, n=100)
    largest_2w_drops = _sort_head(filtered, "perf_2w", ascending=True, n=100)
    largest_1m_drops = _sort_head(filtered, "perf_1m", ascending=True, n=100)
    highest_range_position = _sort_head(filtered, "range_position_1y", ascending=False, n=100)

    views = {
        "V10_6 High Conviction": high_conviction,
        "Hot Sector Drops": hot_sector_drops,
        "Recovery Candidates": recovery_candidates,
        "Reversal Setups": reversal_setups,
        "Largest 1W Drops": largest_1w_drops,
        "Largest 2W Drops": largest_2w_drops,
        "Largest 1M Drops": largest_1m_drops,
        "Highest Range Position": highest_range_position,
    }

    if isinstance(sector_heat, pd.DataFrame) and not sector_heat.empty:
        views["V10_6 Sector Heatmap"] = sector_heat

    views["V10_6 Summary"] = build_v10_6_summary_from_final_views(views)

    # Put Summary first among V10_6 tabs.
    ordered = {"V10_6 Summary": views.pop("V10_6 Summary")}
    ordered.update(views)
    return ordered


def build_v10_6_summary_from_final_views(v10_6_views: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Build V10_6 Summary from the already-filtered detail sheets.
    This keeps row counts consistent with the detail sheets.
    """
    stock_cols = [
        "Symbol", "Security", "Sector", "Index", "price_status", "Marketcap", "capMil",
        "last_close", "perf_1w", "perf_2w", "perf_1m", "RSI",
        "range_position_1y", "sector_temp", "hot_drop_score", "recovery_score",
        "reversal_setup_score", "priority_score"
    ]
    sector_cols = [
        "Sector", "sector_avg_1w", "sector_avg_1m", "sector_avg_3m",
        "sector_hot_score", "sector_temp", "sector_count"
    ]

    sections = [
        ("Top 10 High Conviction", "V10_6 High Conviction", stock_cols),
        ("Top 10 Hot Sector Drops", "Hot Sector Drops", stock_cols),
        ("Top 10 Recovery Candidates", "Recovery Candidates", stock_cols),
        ("Top 10 Reversal Setups", "Reversal Setups", stock_cols),
        ("Top 10 Largest 1W Drops", "Largest 1W Drops", stock_cols),
        ("Top 10 Highest Range Position", "Highest Range Position", stock_cols),
        ("Top 10 Hottest Sectors", "V10_6 Sector Heatmap", sector_cols),
    ]

    blocks = []
    for section_name, sheet_name, cols in sections:
        df = v10_6_views.get(sheet_name, pd.DataFrame())
        if not isinstance(df, pd.DataFrame) or df.empty:
            block = pd.DataFrame({"Section": [section_name], "Note": ["No rows met this sheet's filters"]})
        else:
            existing = [c for c in cols if c in df.columns]
            block = df[existing].head(10).copy() if existing else df.head(10).copy()
            block.insert(0, "Section", section_name)
        blocks.append(block)
        blocks.append(pd.DataFrame([{}]))

    return pd.concat(blocks, ignore_index=True, sort=False)


def reorder_v10_6_summary_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Keep V10_6 Summary readable with Section and market cap near the front."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return df
    front = ["Section", "Symbol", "Security", "Sector", "Index", "price_status", "Marketcap", "capMil"]
    ordered = [c for c in front if c in df.columns]
    remaining = [c for c in df.columns if c not in ordered]
    return df[ordered + remaining]



# =============================================================================
# FINAL SLIM WORKBOOK PATCH - BASING + PERF COLUMNS
# =============================================================================
# This section overrides the earlier broad V10_6 guide behavior with a slimmer,
# daily-use workbook:
# - Keeps perf_1w, perf_2w, perf_1m, perf_3m, perf_6m in action sheets.
# - Keeps is_basing and range_pct_21d visible.
# - Keeps Largest 2W Drops.
# - Adds Deep Value, Momentum Leaders.
# - Makes Reversal Setups basing-only.
# - Removes extra documentation-only tabs; Table of Contents and Column Dictionary
#   carry the explanations instead.

SLIM_ACTION_COLUMNS = [
    "Symbol", "Security", "Index", "Sector", "Sub_Sector", "price_status",
    "Marketcap", "capMil", "debtToEquity", "revenueGrowth", "freeCashFlow", "returnOnEquity", "priceToBook", "quality_score", "quality_reason", "last_close", "previousClose",
    "perf_1w", "perf_2w", "perf_1m", "perf_3m", "perf_6m",
    "one_week_performance", "one_month_performance", "three_month_performance", "six_month_performance",
    "RSI", "Sentiment", "is_basing", "range_pct_21d",
    "range_position_1y", "win%", "win%_covid", "price_suggest_80", "price_suggest_80_covid",
    "sector_temp", "sector_temperature", "sector_hot_score",
    "hot_drop_score", "recovery_score", "reversal_setup_score", "priority_score",
    "watch_reason", "Support1_5d", "Resistance1_5d"
]

SHEET_SPECIFIC_COLUMNS = {
    "Summary": [
        "Section", "Symbol", "Security", "Sector", "Index", "price_status", "Marketcap", "capMil",
        "debtToEquity", "revenueGrowth", "freeCashFlow", "returnOnEquity", "priceToBook", "quality_score", "quality_reason",
        "last_close", "perf_1w", "perf_2w", "perf_1m", "perf_3m", "perf_6m",
        "RSI", "is_basing", "range_pct_21d", "range_position_1y", "win%",
        "sector_temp", "sector_temperature", "hot_drop_score", "recovery_score", "reversal_setup_score", "priority_score",
        "sector_avg_1w", "sector_avg_1m", "sector_avg_3m", "sector_hot_score", "sector_count", "Note"
    ],
    "High Conviction": SLIM_ACTION_COLUMNS,
    "Hot Sector Drops": SLIM_ACTION_COLUMNS,
    "Recovery Candidates": SLIM_ACTION_COLUMNS,
    "Largest 1W Drops": SLIM_ACTION_COLUMNS,
    "Largest 2W Drops": SLIM_ACTION_COLUMNS,
    "Largest 1M Drops": SLIM_ACTION_COLUMNS,
    "Deep Value": SLIM_ACTION_COLUMNS,
    "Momentum Leaders": SLIM_ACTION_COLUMNS,
    "Reversal Setups": SLIM_ACTION_COLUMNS,
    "Sector Heatmap": [
        "Sector", "sector_count", "sector_avg_1w", "sector_avg_1m", "sector_avg_3m",
        "sector_hot_score", "sector_temp", "stock_count", "avg_1w_performance", "avg_1m_performance",
        "avg_3m_performance", "sector_temperature"
    ],
    "Download Audit": [
        "Symbol", "Security", "Index", "Sector", "price_status", "Marketcap", "capMil", "last_close",
        "Date", "latest_price_date"
    ],
}

GUIDE_OR_DOC_SHEETS = set()


def _coalesce_perf_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure simplified sheets have perf_ columns even if only original performance columns exist."""
    out = df.copy()
    mapping = {
        "perf_1w": "one_week_performance",
        "perf_1m": "one_month_performance",
        "perf_3m": "three_month_performance",
        "perf_6m": "six_month_performance",
    }
    for new_col, old_col in mapping.items():
        if new_col not in out.columns and old_col in out.columns:
            out[new_col] = out[old_col]
    return out


def _price_cap_filter(base: pd.DataFrame, min_market_cap: float = 2000) -> pd.DataFrame:
    """Common action-sheet filter: price OK and capMil >= threshold."""
    out = _coalesce_perf_columns(base.copy())
    if "capMil" not in out.columns and "Marketcap" in out.columns:
        out["capMil"] = pd.to_numeric(out["Marketcap"], errors="coerce") / 1_000_000
    if "price_status" in out.columns:
        out = out[out["price_status"].astype(str).eq("OK")].copy()
    if "capMil" in out.columns and min_market_cap is not None and float(min_market_cap) > 0:
        out = out[pd.to_numeric(out["capMil"], errors="coerce") >= float(min_market_cap)].copy()
    return out


def _is_basing_mask(df: pd.DataFrame) -> pd.Series:
    """Basing means the stock is consolidating in a tighter recent range."""
    if "is_basing" in df.columns:
        raw = df["is_basing"]
        if raw.dtype == bool:
            return raw.fillna(False)
        return raw.fillna(False).astype(str).str.upper().isin(["1", "TRUE", "YES", "Y"])
    return pd.Series(False, index=df.index)


def _sort_head(df: pd.DataFrame, sort_col: str, ascending: bool = False, n: int = 100) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()
    out = df.copy()
    if sort_col not in out.columns:
        return out.head(n)
    return out.sort_values(sort_col, ascending=ascending, na_position="last").head(n)


def build_v10_6_views_from_filtered_master(
    dfagg_enhanced: pd.DataFrame,
    enhanced_sheet_dict: dict,
    min_market_cap: float = 2000,
) -> dict[str, pd.DataFrame]:
    """Build the final slim daily-use workbook views."""
    if not isinstance(dfagg_enhanced, pd.DataFrame) or dfagg_enhanced.empty:
        return {}

    base = _coalesce_perf_columns(dfagg_enhanced.copy())
    filtered = _price_cap_filter(base, min_market_cap=min_market_cap)

    if filtered.empty:
        print("WARNING: price/capMil filters returned zero rows. Using price-valid rows if available.")
        if "price_status" in base.columns and base["price_status"].astype(str).eq("OK").any():
            filtered = base[base["price_status"].astype(str).eq("OK")].copy()
        else:
            filtered = base.copy()

    # Basing subset used to avoid catching falling knives on Deep Value/Reversal sheets.
    basing = filtered[_is_basing_mask(filtered)].copy()

    high_conviction = _sort_head(filtered, "priority_score", ascending=False, n=100)

    hot_sector_drops_base = filtered.copy()
    if "sector_temp" in hot_sector_drops_base.columns:
        hot_sector_drops_base = hot_sector_drops_base[hot_sector_drops_base["sector_temp"].astype(str).str.upper().eq("HOT")]
    elif "sector_temperature" in hot_sector_drops_base.columns:
        hot_sector_drops_base = hot_sector_drops_base[hot_sector_drops_base["sector_temperature"].astype(str).str.upper().eq("HOT")]
    if "perf_1m" in hot_sector_drops_base.columns:
        hot_sector_drops_base = hot_sector_drops_base[pd.to_numeric(hot_sector_drops_base["perf_1m"], errors="coerce") <= -5]
    hot_sector_drops = _sort_head(hot_sector_drops_base, "hot_drop_score", ascending=False, n=100)

    recovery_candidates = _sort_head(filtered, "recovery_score", ascending=False, n=100)

    largest_1w_drops = _sort_head(filtered, "perf_1w", ascending=True, n=100)
    largest_2w_drops = _sort_head(filtered, "perf_2w", ascending=True, n=100)
    largest_1m_drops = _sort_head(filtered, "perf_1m", ascending=True, n=100)

    # Deep Value is basing-only so it does not become a list of collapsing stocks.
    deep_value_base = basing.copy()
    if "range_position_1y" in deep_value_base.columns:
        deep_value_base = deep_value_base[pd.to_numeric(deep_value_base["range_position_1y"], errors="coerce") >= 70]
        deep_value = _sort_head(deep_value_base, "range_position_1y", ascending=False, n=100)
    elif "win%" in deep_value_base.columns:
        deep_value_base = deep_value_base[pd.to_numeric(deep_value_base["win%"], errors="coerce") >= 0.70]
        deep_value = _sort_head(deep_value_base, "win%", ascending=False, n=100)
    else:
        deep_value = deep_value_base.head(100)

    # Momentum Leaders are intentionally NOT basing-only; they show what is currently leading.
    momentum_source = "perf_1m" if "perf_1m" in filtered.columns else "one_month_performance"
    momentum_base = filtered[pd.to_numeric(filtered.get(momentum_source), errors="coerce") > 0].copy() if momentum_source in filtered.columns else filtered.copy()
    momentum_leaders = _sort_head(momentum_base, momentum_source, ascending=False, n=100)

    # Reversal Setups are basing-only per your preference.
    reversal_base = basing.copy()
    if "RSI" in reversal_base.columns:
        reversal_base = reversal_base[pd.to_numeric(reversal_base["RSI"], errors="coerce") <= 45]
    reversal_setups = _sort_head(reversal_base, "reversal_setup_score", ascending=False, n=100)

    sector_heat = pd.DataFrame()
    if isinstance(enhanced_sheet_dict, dict):
        sector_heat = enhanced_sheet_dict.get("Sector_Heatmap", pd.DataFrame())
        if sector_heat.empty:
            sector_heat = enhanced_sheet_dict.get("V10_6 Sector Heatmap", pd.DataFrame())

    views = {
        "High Conviction": high_conviction,
        "Hot Sector Drops": hot_sector_drops,
        "Recovery Candidates": recovery_candidates,
        "Largest 1W Drops": largest_1w_drops,
        "Largest 2W Drops": largest_2w_drops,
        "Largest 1M Drops": largest_1m_drops,
        "Deep Value": deep_value,
        "Momentum Leaders": momentum_leaders,
        "Reversal Setups": reversal_setups,
    }

    if isinstance(sector_heat, pd.DataFrame) and not sector_heat.empty:
        views["Sector Heatmap"] = sector_heat

    views["Summary"] = build_v10_6_summary_from_final_views(views)
    ordered = {"Summary": views.pop("Summary")}
    ordered.update(views)
    return ordered


def build_v10_6_summary_from_final_views(v10_6_views: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Build Summary from final filtered sheets so counts/sections align."""
    stock_cols = SHEET_SPECIFIC_COLUMNS["Summary"]
    sector_cols = SHEET_SPECIFIC_COLUMNS["Sector Heatmap"]
    sections = [
        ("Top 10 High Conviction", "High Conviction", stock_cols),
        ("Top 10 Hot Sector Drops", "Hot Sector Drops", stock_cols),
        ("Top 10 Recovery Candidates", "Recovery Candidates", stock_cols),
        ("Top 10 Largest 1W Drops", "Largest 1W Drops", stock_cols),
        ("Top 10 Largest 2W Drops", "Largest 2W Drops", stock_cols),
        ("Top 10 Largest 1M Drops", "Largest 1M Drops", stock_cols),
        ("Top 10 Deep Value Basing", "Deep Value", stock_cols),
        ("Top 10 Momentum Leaders", "Momentum Leaders", stock_cols),
        ("Top 10 Basing Reversal Setups", "Reversal Setups", stock_cols),
        ("Top 10 Hottest Sectors", "Sector Heatmap", sector_cols),
    ]
    blocks = []
    for section_name, sheet_name, cols in sections:
        df = v10_6_views.get(sheet_name, pd.DataFrame())
        if not isinstance(df, pd.DataFrame) or df.empty:
            block = pd.DataFrame({"Section": [section_name], "Note": ["No rows met this sheet's filters"]})
        else:
            existing = [c for c in cols if c in df.columns]
            block = df[existing].head(10).copy() if existing else df.head(10).copy()
            block.insert(0, "Section", section_name)
        blocks.append(block)
        blocks.append(pd.DataFrame([{}]))
    return pd.concat(blocks, ignore_index=True, sort=False)


def reorder_v10_6_summary_columns(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return df
    front = ["Section", "Symbol", "Security", "Sector", "Index", "price_status", "Marketcap", "capMil"]
    ordered = [c for c in front if c in df.columns]
    remaining = [c for c in df.columns if c not in ordered]
    return df[ordered + remaining]


def build_v10_6_sheet_filter_guide(min_market_cap: float = 2000) -> pd.DataFrame:
    """Now used only by Table of Contents logic if needed; no separate sheet is exported."""
    cap = f"price_status = OK and capMil >= {float(min_market_cap):,.0f} million"
    rows = [
        ("Summary", "Dashboard", "Top rows from final filtered sheets", "Each section inherits its detail-sheet filter", "Use first; drill into detail sheet."),
        ("High Conviction", "Overall best setups", "priority_score", cap, "Sorted by priority_score descending."),
        ("Hot Sector Drops", "Hot-sector pullbacks", "hot_drop_score", cap + "; sector HOT; perf_1m <= -5", "Sorted by hot_drop_score descending."),
        ("Recovery Candidates", "Rebound potential", "recovery_score", cap, "Sorted by recovery_score descending."),
        ("Largest 1W Drops", "Fresh weekly selloffs", "perf_1w", cap, "Sorted by perf_1w ascending."),
        ("Largest 2W Drops", "Sustained two-week selloffs", "perf_2w", cap, "Sorted by perf_2w ascending."),
        ("Largest 1M Drops", "Monthly corrections", "perf_1m", cap, "Sorted by perf_1m ascending."),
        ("Deep Value", "Basing deep-value candidates", "range_position_1y / win%", cap + "; is_basing = TRUE; range_position_1y >= 70", "Sorted by range_position_1y descending."),
        ("Momentum Leaders", "Current leaders", "perf_1m", cap + "; perf_1m > 0", "Sorted by perf_1m descending."),
        ("Reversal Setups", "Basing reversal candidates", "reversal_setup_score", cap + "; is_basing = TRUE; RSI <= 45", "Sorted by reversal_setup_score descending."),
        ("Sector Heatmap", "Sector strength", "sector_hot_score", "Sector-level only; no cap filter", "Sorted by sector_hot_score descending."),
        ("Full Master", "All tickers/source of truth", "All calculations", "No filter; includes missing-price rows", "Use price_status to audit missing data."),
        ("Download Audit", "Missing price rows", "price_status", "price_status != OK", "Use only when tickers failed price data."),
    ]
    return pd.DataFrame(rows, columns=["Sheet", "Purpose", "Main Calculation", "Filter", "How To Use"])


def _sheet_guide_row(sheet_name: str, df: pd.DataFrame | None = None) -> dict:
    """Detailed Table of Contents guide for the slim workbook."""
    guide = {
        "Summary": ("Daily dashboard", "Top 10 rows from each final filtered sheet", "No independent filter; inherits each section's detail-sheet filter", "Use this first, then open the matching detail sheet."),
        "High Conviction": ("Best overall setups", "priority_score = 35% hot_drop_score + 35% recovery_score + 20% reversal_setup_score + 10% range_position_1y", "price_status OK; capMil >= threshold", "Highest priority_score = review first."),
        "Hot Sector Drops": ("Strong sectors with pullbacks", "hot_drop_score = sector heat + 1M drop + range position + RSI components", "price_status OK; capMil >= threshold; sector HOT; perf_1m <= -5", "Find quality pullbacks in strong sectors."),
        "Recovery Candidates": ("Potential rebounds", "recovery_score = range position + 1M drop + sector heat + RSI components", "price_status OK; capMil >= threshold", "Look for beaten-down names with recovery setup."),
        "Largest 1W Drops": ("Fresh weekly selloffs", "perf_1w = (last_close / close_1w_ago - 1) * 100", "price_status OK; capMil >= threshold", "Most negative perf_1w = biggest weekly drop."),
        "Largest 2W Drops": ("Sustained two-week weakness", "perf_2w = (last_close / close_2w_ago - 1) * 100", "price_status OK; capMil >= threshold", "Most negative perf_2w = biggest two-week drop."),
        "Largest 1M Drops": ("Monthly corrections", "perf_1m = (last_close / close_1m_ago - 1) * 100", "price_status OK; capMil >= threshold", "Most negative perf_1m = biggest monthly drop."),
        "Deep Value": ("Basing value setups", "range_position_1y = (high_1y - last_close) / (high_1y - low_1y) * 100; win% = (max - last_close)/(max - min)", "price_status OK; capMil >= threshold; is_basing TRUE; range_position_1y >= 70", "Higher range_position means farther below highs, but basing helps avoid falling knives."),
        "Momentum Leaders": ("Current leaders", "perf_1m = (last_close / close_1m_ago - 1) * 100", "price_status OK; capMil >= threshold; perf_1m > 0", "Use to compare market leaders against pullback ideas."),
        "Reversal Setups": ("Basing reversal candidates", "reversal_setup_score = RSI + 3M range position + 1W drop + sector heat components", "price_status OK; capMil >= threshold; is_basing TRUE; RSI <= 45", "Possible bounce candidates that are stabilizing, not just dropping."),
        "Sector Heatmap": ("Hot/cold sector context", "sector_hot_score = weighted sector 1W/1M/3M performance", "Sector-level only; no cap filter", "Check this before judging individual stocks."),
        "Full Master": ("Complete universe audit", "All calculations and all universe tickers", "No filter; starts from universe_df", "Use for debugging and to see MISSING_PRICE tickers."),
        "Download Audit": ("Missing price data", "price_status flag", "price_status != OK", "Use to see which tickers failed or lack usable price data."),
        "Column Dictionary": ("Calculation guide", "Explains every exported Full Master column", "No filter", "Use when you do not know what a column means."),
    }
    purpose, measures, filt, usage = guide.get(sheet_name, ("Supporting output", "See score/performance columns", "Rows are filtered according to sheet logic", "Use as supporting detail."))
    return {
        "Purpose / What It Answers": purpose,
        "Filter / Inclusion Rules": filt,
        # Keep both keys because build_table_of_contents expects "What It Measures"
        # and the newer guide text also uses the more explicit calculation label.
        "What It Measures": measures,
        "What It Measures / Calculation": measures,
        "Ranking / Sort Logic": "Rows are sorted by the primary calculation described above unless noted.",
        "How To Use It": usage,
    }


def get_column_dictionary(columns: list[str]) -> pd.DataFrame:
    """Column Dictionary with no vague placeholder descriptions."""
    details = {
        "Symbol": ("Identifier", "Ticker symbol", "Imported from universe source and normalized, e.g. BRK.B -> BRK-B", "Use to identify the stock."),
        "Security": ("Identifier", "Company/security name", "Imported from index source or Yahoo metadata", "Use for easier review."),
        "Index": ("Identifier", "Universe membership", "Combined from S&P/Nasdaq/Russell/NYSE/Extra loaders", "Shows where the ticker came from."),
        "Index_Origin": ("Identifier", "Primary source universe", "First index based on priority order", "Useful when a ticker appears in multiple lists."),
        "Sector": ("Metadata", "Business sector", "Imported from index/Yahoo metadata", "Use for sector context."),
        "Sub_Sector": ("Metadata", "Industry/sub-sector", "Imported from index/Yahoo metadata", "Use for more precise industry context."),
        "price_status": ("Data Quality", "Whether price data was usable", "OK if last_close exists; otherwise MISSING_PRICE", "Filter OK for rankings; use MISSING_PRICE for audit."),
        "Marketcap": ("Fundamental", "Company market value", "Yahoo marketCap", "Larger companies are usually more liquid."),
        "capMil": ("Fundamental", "Market cap in millions", "Marketcap / 1,000,000", "The action-sheet filter uses capMil >= 2000."),
        "last_close": ("Price", "Latest close", "Most recent Close in price history", "Current price anchor."),
        "previousClose": ("Price", "Prior close", "Previous trading row close by Symbol", "Used for daily change."),
        "one_week_close": ("Price", "Close 5 trading days ago", "groupby(Symbol).Close.shift(5)", "Anchor for one_week_performance."),
        "one_month_close": ("Price", "Close 21 trading days ago", "groupby(Symbol).Close.shift(21)", "Anchor for one_month_performance."),
        "three_month_close": ("Price", "Close 63 trading days ago", "groupby(Symbol).Close.shift(63)", "Anchor for three_month_performance."),
        "six_month_close": ("Price", "Close 126 trading days ago", "groupby(Symbol).Close.shift(126)", "Anchor for six_month_performance."),
        "perf_1w": ("Performance", "1-week return", "(last_close / close_1w_ago - 1) * 100", "Negative = weekly drop."),
        "perf_2w": ("Performance", "2-week return", "(last_close / close_2w_ago - 1) * 100", "Negative = sustained recent drop."),
        "perf_1m": ("Performance", "1-month return", "(last_close / close_1m_ago - 1) * 100", "Main pullback measure."),
        "perf_3m": ("Performance", "3-month return", "(last_close / close_3m_ago - 1) * 100", "Medium-trend context."),
        "perf_6m": ("Performance", "6-month return", "(last_close / close_6m_ago - 1) * 100", "Larger-cycle context."),
        "one_week_performance": ("Performance", "Original 1-week return", "(Close / one_week_close - 1) * 100", "Same purpose as perf_1w."),
        "one_month_performance": ("Performance", "Original 1-month return", "(Close / one_month_close - 1) * 100", "Same purpose as perf_1m."),
        "three_month_performance": ("Performance", "Original 3-month return", "(Close / three_month_close - 1) * 100", "Same purpose as perf_3m."),
        "six_month_performance": ("Performance", "Original 6-month return", "(Close / six_month_close - 1) * 100", "Same purpose as perf_6m."),
        "RSI": ("Technical", "14-day relative strength index", "Calculated from rolling average gains/losses over 14 periods", "Below 30 oversold; 30-45 pullback/reversal zone; above 70 overbought."),
        "Sentiment": ("Technical", "RSI label", "RSI > 70 Overbought; RSI < 30 Oversold; else Neutral", "Quick RSI interpretation."),
        "is_basing": ("Technical", "Consolidation/basing flag", "range_pct_21d <= 0.15 AND near 21d low AND one_month_performance <= -5", "TRUE means stock may be stabilizing after weakness."),
        "range_pct_21d": ("Technical", "21-day trading range width", "(high_21d - low_21d) / high_21d", "Lower means tighter base/consolidation."),
        "range_position_1y": ("Range Position", "Position inside 52-week range", "(high_1y - last_close) / (high_1y - low_1y) * 100", "0 near high; 100 near low."),
        "range_position_6m": ("Range Position", "Position inside 6-month range", "(high_6m - last_close) / (high_6m - low_6m) * 100", "Higher = closer to 6-month low."),
        "range_position_3m": ("Range Position", "Position inside 3-month range", "(high_3m - last_close) / (high_3m - low_3m) * 100", "Higher = closer to 3-month low."),
        "win%": ("Range Position", "Long-term range position", "(max - last_close) / (max - min)", "Higher = farther below long-term high."),
        "win%_covid": ("Range Position", "Covid-adjusted long-term range position", "(max - last_close) / (max - minCovid_filled)", "Higher = farther below high using Covid low anchor."),
        "price_suggest_80": ("Value", "80% retracement/recovery reference", "max - ((max - min) * 0.80)", "If last_close is below this, stock is deep in its range."),
        "price_suggest_80_covid": ("Value", "Covid-adjusted 80% reference", "max - ((max - minCovid_filled) * 0.80)", "Covid-adjusted version of price_suggest_80."),
        "sector_hot_score": ("Sector Heat", "Sector strength score", "Weighted sector performance across recent windows", "Higher means stronger sector."),
        "sector_temp": ("Sector Heat", "HOT/WARM/COLD sector label", "Derived from sector_hot_score bins", "Prefer pullbacks in HOT sectors."),
        "sector_temperature": ("Sector Heat", "Hot/Neutral/Cold sector label", "Derived from sector_summary hot score", "Alternative sector heat label."),
        "hot_drop_score": ("Score", "Hot-sector pullback score", "35% sector_hot_score + 35% 1M drop magnitude + 20% range_position_1y + 10% RSI weakness component", "Higher = better pullback inside strong sector."),
        "recovery_score": ("Score", "Recovery potential score", "35% range_position_1y + 25% 1M drop magnitude + 20% sector_hot_score + 20% RSI weakness component", "Higher = stronger rebound candidate."),
        "reversal_setup_score": ("Score", "Technical bounce setup score", "35% RSI weakness + 25% range_position_3m + 20% 1W drop magnitude + 20% sector_hot_score", "Higher = stronger reversal setup; now filtered to basing stocks."),
        "priority_score": ("Score", "Overall opportunity score", "35% hot_drop_score + 35% recovery_score + 20% reversal_setup_score + 10% range_position_1y", "Main ranking score for High Conviction."),
        "watch_reason": ("Explanation", "Why a stock ranked highly", "Generated from rules such as high win%, large drop, oversold RSI, near support, watchlist flag", "Use to quickly understand why the row appears."),
        "largest_recent_drop": ("Drop", "Worst recent return", "Minimum of 1W, 1M, and 3M performance columns", "More negative means bigger recent damage."),
        "drop_alert_score": ("Score", "Recent drop severity", "abs(largest_recent_drop clipped at 40%) / 40 * 100", "Higher = larger recent drop."),
        "value_range_score": ("Score", "Range/value score", "50% regular_range_score + 40% covid_range_score + price_suggest flags", "Higher = more attractive range position."),
        "final_watch_score": ("Score", "Original combined watch score", "40% value_range + 25% drop_alert + 20% technical + 15% fundamental", "Original model's broad ranking score."),
        "Support1_5d": ("Technical", "Short-term support estimate", "2 * Pivot_5d - high_5d", "Potential nearby support level."),
        "Resistance1_5d": ("Technical", "Short-term resistance estimate", "2 * Pivot_5d - low_5d", "Potential nearby resistance level."),
        "Pivot_5d": ("Technical", "5-day pivot", "average of 5-day high, 5-day low, and last close", "Short-term pivot reference."),
        "Date": ("Date", "Latest price date", "Latest Date from price dataframe", "Shows last price observation."),
        "latest_price_date": ("Date", "Latest enhancement price date", "Latest date merged by enhancement module", "Audit latest price data."),
        "description": ("Metadata", "Business description", "Yahoo longBusinessSummary", "Manual business review and keyword flags."),
        "flag": ("Flag", "Watchlist flag", "1 if symbol is in extra/flagged watchlist", "Helps identify names you manually care about."),
        "is_extra": ("Flag", "Extra ticker flag", "1 if symbol came from DEFAULT_EXTRA_TICKERS or config extra file", "Shows manually force-included names."),
        "is_key": ("Flag", "Keyword theme flag", "1 if description contains selected themes like AI/energy/quantum", "Theme screen helper."),
    }

    def infer(col: str):
        c = str(col)
        lc = c.lower()
        if lc.startswith("rank_"):
            return ("Rank", f"Rank for {c.replace('rank_', '')}", "pandas rank() on the related score/performance column", "Lower or higher depends on sheet sort; use highlighted sorted column.")
        if lc.startswith("high_"):
            return ("Rolling Price", f"Rolling high for {c}", "Rolling maximum over the window named in the column", "Used to calculate range position/support context.")
        if lc.startswith("low_"):
            return ("Rolling Price", f"Rolling low for {c}", "Rolling minimum over the window named in the column", "Used to calculate range position/support context.")
        if "score" in lc:
            return ("Score", f"Model score: {c}", "Weighted calculation in add_scores or enhancement scoring logic", "Higher generally means better ranking unless sheet states otherwise.")
        if "performance" in lc or lc.startswith("perf_"):
            return ("Performance", f"Return metric: {c}", "Percentage return over the time window named in the column", "Negative means price fell; positive means price rose.")
        if "volume" in lc or "vol" in lc:
            return ("Liquidity", f"Volume/liquidity field: {c}", "Calculated from price volume data or Yahoo average volume", "Higher usually means more liquid trading.")
        if "date" in lc:
            return ("Date", f"Date field: {c}", "Date captured during price/stat calculation", "Use for audit and timing context.")
        if lc in {"min", "max", "mincovid", "mincovid_filled"}:
            return ("Range", f"Historical range anchor: {c}", "Min/max close over downloaded history or Covid period", "Used in win% and price_suggest calculations.")
        return ("Script Output", f"{c} generated or imported by the script", "Imported from universe/fundamentals or created as an intermediate calculation", "Keep in Full Master for audit; action sheets only show important fields.")

    rows = []
    for col in columns:
        cat, measure, calc, use = details.get(col, infer(col))
        rows.append({
            "Column": col,
            "Category": cat,
            "What It Measures": measure,
            "How Calculated": calc,
            "How To Read / Use": use,
        })
    return pd.DataFrame(rows)


def finalize_slim_workbook_views(views: dict[str, pd.DataFrame], dfagg: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Keep only the sheets requested for the slim workbook."""
    final = {}
    for name in [
        "Summary", "High Conviction", "Hot Sector Drops", "Recovery Candidates",
        "Largest 1W Drops", "Largest 2W Drops", "Largest 1M Drops",
        "Deep Value", "Momentum Leaders", "Reversal Setups", "Sector Heatmap"
    ]:
        if name in views:
            final[name] = views[name]

    if isinstance(dfagg, pd.DataFrame) and not dfagg.empty:
        final["Full Master"] = dfagg
        audit = dfagg.copy()
        if "price_status" in audit.columns:
            audit = audit[~audit["price_status"].astype(str).eq("OK")].copy()
        else:
            audit = pd.DataFrame()
        final["Download Audit"] = audit
    elif "Full Master" in views:
        final["Full Master"] = views["Full Master"]

    return final




# =============================================================================
# FINAL OVERRIDE - SLIM BASING VERSION WITHOUT perf_* EXPORT COLUMNS
# =============================================================================
# This block intentionally overrides earlier helper definitions.
# perf_* columns may still be used internally for sorting/scoring, but they are
# hidden from the final workbook. Existing one_week/month/three/six performance
# columns remain visible, plus reference close columns.

REFERENCE_CLOSE_COLUMNS = ["one_week_close", "one_month_close", "three_month_close", "six_month_close"]
VISIBLE_PERFORMANCE_COLUMNS = [
    "prior_%_change", "one_week_performance", "one_month_performance",
    "three_month_performance", "six_month_performance", "ytd",
]

SLIM_ACTION_COLUMNS = [
    "Symbol", "Security", "Index", "Index_Origin", "Sector", "Sub_Sector", "price_status",
    "Marketcap", "capMil", "debtToEquity", "revenueGrowth", "freeCashFlow", "returnOnEquity", "priceToBook", "quality_score", "quality_reason", "last_close", "previousClose",
    *REFERENCE_CLOSE_COLUMNS,
    *VISIBLE_PERFORMANCE_COLUMNS,
    "largest_recent_drop", "RSI", "Sentiment", "is_basing", "range_pct_21d",
    "range_position_1y", "win%", "win%_covid", "price_suggest_80", "price_suggest_80_covid",
    "sector_temp", "sector_temperature", "sector_hot_score",
    "hot_drop_score", "recovery_score", "reversal_setup_score", "priority_score",
    "final_watch_score", "value_range_score", "drop_alert_score", "watch_reason",
    "Support1_5d", "Resistance1_5d",
]

FULL_MASTER_COLUMNS = [
    "Symbol", "Security", "Index", "Index_Origin", "is_extra", "Sector", "Sub_Sector", "price_status",
    "Marketcap", "capMil", "debtToEquity", "revenueGrowth", "freeCashFlow", "returnOnEquity", "priceToBook", "quality_score", "quality_reason", "AvgVol10d", "last_volume", "mean_vol",
    "Date", "last_close", "previousClose", *REFERENCE_CLOSE_COLUMNS, *VISIBLE_PERFORMANCE_COLUMNS,
    "largest_recent_drop", "min", "max", "minCovid", "minCovid_filled",
    "price_suggest_80", "price_suggest_80_covid", "win%", "win%_covid",
    "below_price_suggest_80", "below_price_suggest_80_covid", "Percent_min_price", "Is_Covid_Low",
    "RSI", "Sentiment", "is_basing", "range_pct_21d",
    "Pivot_5d", "Support1_5d", "Resistance1_5d",
    "next_support_1", "next_support_2", "next_support_3",
    "next_resistance_1", "next_resistance_2", "next_resistance_3",
    "sector_temp", "sector_temperature", "sector_hot_score",
    "hot_drop_score", "recovery_score", "reversal_setup_score", "priority_score",
    "final_watch_score", "value_range_score", "drop_alert_score", "watch_reason",
    "shortRatio", "min_date", "max_date", "mincovid_date",
    "flag", "is_key", "description",
]

SHEET_SPECIFIC_COLUMNS = {
    "Summary": [
        "Section", "Symbol", "Security", "Sector", "Index", "price_status", "Marketcap", "capMil",
        "debtToEquity", "revenueGrowth", "freeCashFlow", "returnOnEquity", "priceToBook", "quality_score", "quality_reason",
        "last_close", "previousClose", *REFERENCE_CLOSE_COLUMNS, *VISIBLE_PERFORMANCE_COLUMNS,
        "RSI", "is_basing", "range_pct_21d", "range_position_1y", "win%",
        "sector_temp", "sector_temperature", "hot_drop_score", "recovery_score", "reversal_setup_score", "priority_score",
        "sector_avg_1w", "sector_avg_1m", "sector_avg_3m", "sector_hot_score", "sector_count", "Note",
    ],
    "High Conviction": SLIM_ACTION_COLUMNS,
    "Hot Sector Drops": SLIM_ACTION_COLUMNS,
    "Recovery Candidates": SLIM_ACTION_COLUMNS,
    "Largest 1W Drops": SLIM_ACTION_COLUMNS,
    "Largest 2W Drops": SLIM_ACTION_COLUMNS,
    "Largest 1M Drops": SLIM_ACTION_COLUMNS,
    "Deep Value": SLIM_ACTION_COLUMNS,
    "Momentum Leaders": SLIM_ACTION_COLUMNS,
    "Reversal Setups": SLIM_ACTION_COLUMNS,
    "Full Master": FULL_MASTER_COLUMNS,
    "Sector Heatmap": [
        "Sector", "sector_count", "sector_avg_1w", "sector_avg_1m", "sector_avg_3m", "sector_hot_score",
        "sector_temp", "stock_count", "avg_1w_performance", "avg_1m_performance", "avg_3m_performance",
        "sector_temperature", "pct_positive_1m", "avg_final_watch_score",
    ],
    "Download Audit": ["Symbol", "Security", "Index", "Sector", "price_status", "Marketcap", "capMil", "last_close", "Date", "latest_price_date"],
}
GUIDE_OR_DOC_SHEETS = set()


def _ensure_internal_perf_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    mapping = {"perf_1w": "one_week_performance", "perf_1m": "one_month_performance", "perf_3m": "three_month_performance", "perf_6m": "six_month_performance"}
    for perf_col, old_col in mapping.items():
        if perf_col not in out.columns and old_col in out.columns:
            out[perf_col] = out[old_col]
    return out


def _price_cap_filter(base: pd.DataFrame, min_market_cap: float = 2000) -> pd.DataFrame:
    out = _ensure_internal_perf_columns(base.copy())
    if "capMil" not in out.columns and "Marketcap" in out.columns:
        out["capMil"] = pd.to_numeric(out["Marketcap"], errors="coerce") / 1_000_000
    if "price_status" in out.columns:
        out = out[out["price_status"].astype(str).eq("OK")].copy()
    if "capMil" in out.columns and min_market_cap is not None and float(min_market_cap) > 0:
        out = out[pd.to_numeric(out["capMil"], errors="coerce") >= float(min_market_cap)].copy()
    return out


def _is_basing_mask(df: pd.DataFrame) -> pd.Series:
    if "is_basing" in df.columns:
        raw = df["is_basing"]
        if raw.dtype == bool:
            return raw.fillna(False)
        return raw.fillna(False).astype(str).str.upper().isin(["1", "TRUE", "YES", "Y"])
    return pd.Series(False, index=df.index)


def _sort_head(df: pd.DataFrame, sort_col: str, ascending: bool = False, n: int = 100) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()
    if sort_col not in df.columns:
        return df.head(n)
    return df.sort_values(sort_col, ascending=ascending, na_position="last").head(n)


def _sort_by_first_available(df: pd.DataFrame, candidates: list[str], ascending: bool, n: int = 100) -> pd.DataFrame:
    for col in candidates:
        if col in df.columns:
            return _sort_head(df, col, ascending=ascending, n=n)
    return df.head(n) if isinstance(df, pd.DataFrame) else pd.DataFrame()


def build_v10_6_views_from_filtered_master(dfagg_enhanced: pd.DataFrame, enhanced_sheet_dict: dict, min_market_cap: float = 2000) -> dict[str, pd.DataFrame]:
    if not isinstance(dfagg_enhanced, pd.DataFrame) or dfagg_enhanced.empty:
        return {}
    base = _ensure_internal_perf_columns(dfagg_enhanced.copy())
    filtered = _price_cap_filter(base, min_market_cap=min_market_cap)
    if filtered.empty:
        print("WARNING: price/capMil filters returned zero rows. Using price-valid rows if available.")
        if "price_status" in base.columns and base["price_status"].astype(str).eq("OK").any():
            filtered = base[base["price_status"].astype(str).eq("OK")].copy()
        else:
            filtered = base.copy()

    basing = filtered[_is_basing_mask(filtered)].copy()
    high_conviction = _sort_by_first_available(filtered, ["priority_score", "final_watch_score"], ascending=False, n=100)

    hot_sector_drops_base = filtered.copy()
    if "sector_temp" in hot_sector_drops_base.columns:
        hot_sector_drops_base = hot_sector_drops_base[hot_sector_drops_base["sector_temp"].astype(str).str.upper().eq("HOT")]
    elif "sector_temperature" in hot_sector_drops_base.columns:
        hot_sector_drops_base = hot_sector_drops_base[hot_sector_drops_base["sector_temperature"].astype(str).str.upper().eq("HOT")]
    if "one_month_performance" in hot_sector_drops_base.columns:
        hot_sector_drops_base = hot_sector_drops_base[pd.to_numeric(hot_sector_drops_base["one_month_performance"], errors="coerce") <= -5]
    elif "perf_1m" in hot_sector_drops_base.columns:
        hot_sector_drops_base = hot_sector_drops_base[pd.to_numeric(hot_sector_drops_base["perf_1m"], errors="coerce") <= -5]
    hot_sector_drops = _sort_by_first_available(hot_sector_drops_base, ["hot_drop_score", "priority_score"], ascending=False, n=100)

    recovery_candidates = _sort_by_first_available(filtered, ["recovery_score", "priority_score"], ascending=False, n=100)
    largest_1w_drops = _sort_by_first_available(filtered, ["one_week_performance", "perf_1w"], ascending=True, n=100)
    largest_2w_drops = _sort_by_first_available(filtered, ["perf_2w", "one_week_performance", "one_month_performance"], ascending=True, n=100)
    largest_1m_drops = _sort_by_first_available(filtered, ["one_month_performance", "perf_1m"], ascending=True, n=100)

    deep_value_base = basing.copy()
    if "range_position_1y" in deep_value_base.columns:
        deep_value_base = deep_value_base[pd.to_numeric(deep_value_base["range_position_1y"], errors="coerce") >= 70]
        deep_value = _sort_head(deep_value_base, "range_position_1y", ascending=False, n=100)
    elif "win%" in deep_value_base.columns:
        deep_value_base = deep_value_base[pd.to_numeric(deep_value_base["win%"], errors="coerce") >= 0.70]
        deep_value = _sort_head(deep_value_base, "win%", ascending=False, n=100)
    else:
        deep_value = deep_value_base.head(100)

    momentum_source = "one_month_performance" if "one_month_performance" in filtered.columns else "perf_1m"
    momentum_base = filtered[pd.to_numeric(filtered[momentum_source], errors="coerce") > 0].copy() if momentum_source in filtered.columns else filtered.copy()
    momentum_leaders = _sort_head(momentum_base, momentum_source, ascending=False, n=100) if momentum_source in momentum_base.columns else momentum_base.head(100)

    reversal_base = basing.copy()
    if "RSI" in reversal_base.columns:
        reversal_base = reversal_base[pd.to_numeric(reversal_base["RSI"], errors="coerce") <= 45]
    reversal_setups = _sort_by_first_available(reversal_base, ["reversal_setup_score", "recovery_score"], ascending=False, n=100)

    sector_heat = pd.DataFrame()
    if isinstance(enhanced_sheet_dict, dict):
        sector_heat = enhanced_sheet_dict.get("Sector_Heatmap", pd.DataFrame())
        if sector_heat.empty:
            sector_heat = enhanced_sheet_dict.get("V10_6 Sector Heatmap", pd.DataFrame())

    views = {
        "High Conviction": high_conviction,
        "Hot Sector Drops": hot_sector_drops,
        "Recovery Candidates": recovery_candidates,
        "Largest 1W Drops": largest_1w_drops,
        "Largest 2W Drops": largest_2w_drops,
        "Largest 1M Drops": largest_1m_drops,
        "Deep Value": deep_value,
        "Momentum Leaders": momentum_leaders,
        "Reversal Setups": reversal_setups,
    }
    if isinstance(sector_heat, pd.DataFrame) and not sector_heat.empty:
        views["Sector Heatmap"] = sector_heat
    views["Summary"] = build_v10_6_summary_from_final_views(views)
    ordered = {"Summary": views.pop("Summary")}
    ordered.update(views)
    return ordered


def build_v10_6_summary_from_final_views(v10_6_views: dict[str, pd.DataFrame]) -> pd.DataFrame:
    stock_cols = SHEET_SPECIFIC_COLUMNS["Summary"]
    sector_cols = SHEET_SPECIFIC_COLUMNS["Sector Heatmap"]
    sections = [
        ("Top 10 High Conviction", "High Conviction", stock_cols),
        ("Top 10 Hot Sector Drops", "Hot Sector Drops", stock_cols),
        ("Top 10 Recovery Candidates", "Recovery Candidates", stock_cols),
        ("Top 10 Largest 1W Drops", "Largest 1W Drops", stock_cols),
        ("Top 10 Largest 2W Drops", "Largest 2W Drops", stock_cols),
        ("Top 10 Largest 1M Drops", "Largest 1M Drops", stock_cols),
        ("Top 10 Deep Value Basing", "Deep Value", stock_cols),
        ("Top 10 Momentum Leaders", "Momentum Leaders", stock_cols),
        ("Top 10 Basing Reversal Setups", "Reversal Setups", stock_cols),
        ("Top 10 Hottest Sectors", "Sector Heatmap", sector_cols),
    ]
    blocks = []
    for section_name, sheet_name, cols in sections:
        df = v10_6_views.get(sheet_name, pd.DataFrame())
        if not isinstance(df, pd.DataFrame) or df.empty:
            block = pd.DataFrame({"Section": [section_name], "Note": ["No rows met this sheet's filters"]})
        else:
            existing = [c for c in cols if c in df.columns]
            block = df[existing].head(10).copy() if existing else df.head(10).copy()
            block.insert(0, "Section", section_name)
        blocks.append(block)
        blocks.append(pd.DataFrame([{}]))
    return pd.concat(blocks, ignore_index=True, sort=False)


def reorder_v10_6_summary_columns(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return df
    front = ["Section", "Symbol", "Security", "Sector", "Index", "price_status", "Marketcap", "capMil"]
    ordered = [c for c in front if c in df.columns]
    remaining = [c for c in df.columns if c not in ordered]
    return df[ordered + remaining]


def _sheet_guide_row(sheet_name: str, df: pd.DataFrame | None = None) -> dict:
    cap = "price_status = OK and capMil >= 2000 for stock-level action sheets"
    guides = {
        "Summary": ("Daily dashboard: top names from each core sheet.", "Uses final filtered detail sheets; each section matches the related sheet.", "Best overall ideas, hot-sector drops, recovery candidates, largest drops, deep-value basing setups, momentum leaders, and basing reversals.", "Each section inherits the sort from its detail sheet.", "Open this first, then drill into detail sheets."),
        "High Conviction": ("Which stocks have the strongest overall setup?", cap, "Combined opportunity score using value/range position, recent weakness, technical setup, and sector strength.", "Sorted by priority_score descending; fallback final_watch_score.", "Main first-pass research list."),
        "Hot Sector Drops": ("Which stocks are pulling back while their sector is strong?", cap + "; sector is HOT; one_month_performance <= -5%.", "Quality pullbacks inside strong sectors.", "Sorted by hot_drop_score descending.", "Spot strong-sector dips instead of weak-sector collapses."),
        "Recovery Candidates": ("Which beaten-down stocks may rebound?", cap, "Recovery potential using range position, recent drop, sector heat, and RSI.", "Sorted by recovery_score descending.", "Find rebound candidates."),
        "Largest 1W Drops": ("What got hit hardest this week?", cap, "Worst 5-trading-day selloffs.", "Sorted by one_week_performance ascending.", "Spot panic/news-driven weakness."),
        "Largest 2W Drops": ("What sold off over roughly two weeks?", cap, "Worst 10-trading-day selloffs. Uses internal perf_2w if available, hidden from export.", "Sorted by internal perf_2w; fallback one_week_performance then one_month_performance.", "Catch sustained weakness between weekly and monthly views."),
        "Largest 1M Drops": ("What is in a monthly correction?", cap, "Worst 21-trading-day selloffs.", "Sorted by one_month_performance ascending.", "Medium-term correction candidates."),
        "Deep Value": ("Which beaten-down stocks are also basing?", cap + "; is_basing = TRUE; range_position_1y >= 70 when available.", "Deep pullbacks that are stabilizing instead of just falling.", "Sorted by range_position_1y descending; fallback win% descending.", "Discounted names that show a base."),
        "Momentum Leaders": ("Which stocks are leading upward?", cap + "; one_month_performance > 0 when available.", "Positive momentum and relative leadership.", "Sorted by one_month_performance descending.", "Compare against pullback sheets."),
        "Reversal Setups": ("Which basing stocks may be setting up for a bounce?", cap + "; is_basing = TRUE; RSI <= 45 when RSI exists.", "Stabilizing/oversold bounce setups.", "Sorted by reversal_setup_score descending; fallback recovery_score.", "Basing requirement helps avoid falling knives."),
        "Sector Heatmap": ("Which sectors are hot or cold?", "Sector-level aggregation; not stock-level cap filtered.", "Sector average performance, breadth, and sector_hot_score.", "Sorted by sector_hot_score when available.", "Check before individual stocks."),
        "Full Master": ("Source-of-truth table for all universe tickers.", "No row filter. Includes all universe tickers; price_status flags missing price data.", "Core price, performance, value/range, basing, sector, score, and audit fields.", "Not ranked by default.", "Audit missing data or inspect details."),
        "Download Audit": ("Which tickers are missing price data?", "price_status != OK.", "Data completeness issues.", "Not ranked.", "Use when counts do not match expectations."),
    }
    p, f, m, r, u = guides.get(sheet_name, ("Workbook sheet generated by the scanner.", "See script logic.", "Stock scanner metrics.", "See sheet order and key columns.", "Review key columns and compare with Full Master."))
    return {"Purpose / What It Answers": p, "Filter / Inclusion Rules": f, "What It Measures": m, "Ranking / Sort Logic": r, "How To Use It": u}


def build_table_of_contents(views: dict[str, pd.DataFrame], csv_outputs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = [{
        "Type": "Workbook", "Name": "stock_rankings.xlsx", "Output Location": str(OUTPUT_WORKBOOK), "Row Count": "",
        "Purpose / What It Answers": "Daily stock scanner workbook. Start with Summary, then drill into detail sheets.",
        "Filter / Inclusion Rules": "Full Master keeps all tickers. Action sheets require valid price and market cap threshold.",
        "What It Measures": "Pullbacks, basing, value/range position, momentum, sector heat, and core scores.",
        "Ranking / Sort Logic": "Each tab has its own ranking; see sheet rows below.",
        "How To Use It": "Use Summary first, detail sheets second, Full Master for audit.",
        "Key Columns to Review": "last_close, reference closes, performance columns, RSI, is_basing, range_position_1y, scores, watch_reason",
    }]
    for sheet_name, df in views.items():
        if not isinstance(df, pd.DataFrame):
            continue
        guide = _sheet_guide_row(sheet_name, df)
        rows.append({
            "Type": "Sheet", "Name": sheet_name, "Output Location": f"stock_rankings.xlsx -> {sheet_name[:31]}", "Row Count": len(df),
            "Purpose / What It Answers": guide["Purpose / What It Answers"],
            "Filter / Inclusion Rules": guide["Filter / Inclusion Rules"],
            "What It Measures": guide["What It Measures"],
            "Ranking / Sort Logic": guide["Ranking / Sort Logic"],
            "How To Use It": guide["How To Use It"],
            "Key Columns to Review": ", ".join(list(df.columns[:18])) if not df.empty else "No rows",
        })
    full_master = views.get("Full Master", pd.DataFrame())
    rows.append({
        "Type": "Sheet", "Name": "Column Dictionary", "Output Location": "stock_rankings.xlsx -> Column Dictionary",
        "Row Count": len(get_column_dictionary(list(full_master.columns))) if isinstance(full_master, pd.DataFrame) else "",
        "Purpose / What It Answers": "Explains every exported column.", "Filter / Inclusion Rules": "Documentation sheet only.",
        "What It Measures": "Column meaning, formula/calculation, and how to use it.", "Ranking / Sort Logic": "Not ranked.",
        "How To Use It": "Use when a column is unclear.", "Key Columns to Review": "Column, Category, What It Measures, How Calculated, How To Read / Use",
    })
    for file_name, df in csv_outputs.items():
        rows.append({
            "Type": "CSV", "Name": file_name, "Output Location": str(OUTPUT_DIR / file_name), "Row Count": len(df) if isinstance(df, pd.DataFrame) else "",
            "Purpose / What It Answers": "Quick CSV export from legacy action views.", "Filter / Inclusion Rules": "Same as source workbook sheet.",
            "What It Measures": "Same as source workbook sheet.", "Ranking / Sort Logic": "Same as source workbook sheet.",
            "How To Use It": "Use for quick external review or sharing.", "Key Columns to Review": ", ".join(list(df.columns[:12])) if isinstance(df, pd.DataFrame) and not df.empty else "No rows",
        })
    return pd.DataFrame(rows)


def get_column_dictionary(columns: list[str]) -> pd.DataFrame:
    details = {
        "Symbol": ("Identifier", "Ticker symbol.", "Loaded from universe sources and normalized, e.g. BRK.B -> BRK-B.", "Main lookup field."),
        "Security": ("Identifier", "Company/fund name.", "Index or Yahoo metadata.", "Use for recognition."),
        "Index": ("Identifier", "Universe source/membership.", "Combined from S&P 500, Nasdaq, Russell, NYSE, Extra.", "Shows where ticker came from."),
        "Index_Origin": ("Identifier", "Primary universe source.", "First source based on configured priority.", "Useful for multi-list tickers."),
        "is_extra": ("Identifier", "Manual/watchlist flag.", "1 if included from your extra list, else 0.", "Identifies manually added names."),
        "Sector": ("Metadata", "Broad sector.", "S&P/Yahoo metadata.", "Sector context."),
        "Sub_Sector": ("Metadata", "Detailed industry.", "S&P/Yahoo metadata.", "Peer context."),
        "price_status": ("Data Quality", "Whether price data exists.", "OK if last_close exists; MISSING_PRICE if not.", "MISSING_PRICE stays only in Full Master/Download Audit."),
        "Marketcap": ("Fundamental", "Company market value in dollars.", "Yahoo marketCap.", "Bigger names are usually more liquid/stable."),
        "capMil": ("Fundamental", "Market cap in millions.", "Marketcap / 1,000,000.", "Action sheets usually require capMil >= 2000."),
        "AvgVol10d": ("Liquidity", "Average 10-day volume.", "Yahoo averageDailyVolume10Day or calculated rolling 10-day average.", "Liquidity check."),
        "last_volume": ("Liquidity", "Latest volume.", "Volume on latest price date.", "Compare with AvgVol10d."),
        "mean_vol": ("Liquidity", "Average historical volume.", "Mean Volume over downloaded history.", "Longer-term liquidity context."),
        "Date": ("Price", "Latest market date.", "Latest Date from price history.", "Confirms data freshness."),
        "last_close": ("Price", "Latest closing price.", "Most recent Close.", "Current price anchor."),
        "previousClose": ("Price", "Prior close.", "Close.shift(1) by Symbol.", "Used for daily change."),
        "one_week_close": ("Price Reference", "Close about 5 trading days ago.", "Close.shift(5) by Symbol.", "Compare to last_close."),
        "one_month_close": ("Price Reference", "Close about 21 trading days ago.", "Close.shift(21) by Symbol.", "Compare to last_close."),
        "three_month_close": ("Price Reference", "Close about 63 trading days ago.", "Close.shift(63) by Symbol.", "Medium-term reference."),
        "six_month_close": ("Price Reference", "Close about 126 trading days ago.", "Close.shift(126) by Symbol.", "Longer-term reference."),
        "prior_%_change": ("Performance", "Daily percent change.", "(last_close - previousClose) / previousClose * 100.", "Negative = down from prior close."),
        "one_week_performance": ("Performance", "Approx. 1-week return.", "(Close / one_week_close - 1) * 100.", "Negative = weekly drop."),
        "one_month_performance": ("Performance", "Approx. 1-month return.", "(Close / one_month_close - 1) * 100.", "Main pullback metric."),
        "three_month_performance": ("Performance", "Approx. 3-month return.", "(Close / three_month_close - 1) * 100.", "Medium-term trend."),
        "six_month_performance": ("Performance", "Approx. 6-month return.", "(Close / six_month_close - 1) * 100.", "Longer trend."),
        "ytd": ("Performance", "Year-to-date return as decimal.", "Close / first close of year - 1.", "Positive = up YTD."),
        "largest_recent_drop": ("Performance", "Worst recent return across short windows.", "Minimum of one_week, one_month, three_month performance.", "More negative = bigger recent damage."),
        "min": ("Range", "Lowest close in history.", "Close.min by Symbol.", "Long-term low."),
        "max": ("Range", "Highest close in history.", "Close.max by Symbol.", "Long-term high."),
        "minCovid": ("Range", "Covid-period low.", "Minimum close before 2020-04-30.", "Covid low comparison."),
        "minCovid_filled": ("Range", "Covid low fallback.", "minCovid or min if missing.", "Used for Covid calculations."),
        "price_suggest_80": ("Range", "80% retracement range level.", "max - ((max - min) * 0.80).", "Lower-range/value reference, not a prediction."),
        "price_suggest_80_covid": ("Range", "80% range level using Covid low.", "max - ((max - minCovid_filled) * 0.80).", "Covid-adjusted value reference."),
        "win%": ("Range", "Long-term range position.", "(max - last_close) / (max - min).", "Higher = farther below historical high."),
        "win%_covid": ("Range", "Covid-adjusted range position.", "(max - last_close) / (max - minCovid_filled).", "Higher = farther below high."),
        "range_position_1y": ("Range", "52-week range position.", "(high_1y - last_close) / (high_1y - low_1y) * 100.", "0 near high; 100 near low."),
        "below_price_suggest_80": ("Flag", "Below regular 80% level.", "last_close <= price_suggest_80.", "1 = lower part of range."),
        "below_price_suggest_80_covid": ("Flag", "Below Covid 80% level.", "last_close <= price_suggest_80_covid.", "1 = lower Covid-adjusted range."),
        "Percent_min_price": ("Range", "Distance from selected low.", "Percent distance from min or minCovid.", "Lower = closer to lows."),
        "Is_Covid_Low": ("Range", "Covid-low classification.", "Rule comparison of min, minCovid, and last_close.", "Explains low context."),
        "RSI": ("Technical", "14-day RSI.", "Standard rolling gains/losses RSI.", "<30 oversold; >70 overbought."),
        "Sentiment": ("Technical", "RSI label.", "RSI > 70 Overbought; RSI < 30 Oversold; else Neutral.", "Quick momentum state."),
        "is_basing": ("Technical", "Consolidation/basing flag.", "range_pct_21d <= 0.15 AND near 21d low AND one_month_performance <= -5.", "TRUE = possible stabilization."),
        "range_pct_21d": ("Technical", "21-day range width.", "(high_21d - low_21d) / high_21d.", "Smaller = tighter base."),
        "Pivot_5d": ("Technical", "Short-term pivot.", "(5-day high + 5-day low + last_close) / 3.", "Support/resistance reference."),
        "Support1_5d": ("Technical", "First support.", "(2 * Pivot_5d) - 5-day high.", "Downside reference."),
        "Resistance1_5d": ("Technical", "First resistance.", "(2 * Pivot_5d) - 5-day low.", "Upside resistance reference."),
        "next_support_1": ("Technical", "Nearest historical support below price.", "Prior closes below last_close, de-duplicated.", "Potential support."),
        "next_support_2": ("Technical", "Second support below price.", "Second level from same support search.", "Support context."),
        "next_support_3": ("Technical", "Third support below price.", "Third level from same support search.", "Support context."),
        "next_resistance_1": ("Technical", "Nearest resistance above price.", "Prior closes above last_close, de-duplicated.", "Potential resistance."),
        "next_resistance_2": ("Technical", "Second resistance above price.", "Second level from same resistance search.", "Resistance context."),
        "next_resistance_3": ("Technical", "Third resistance above price.", "Third level from same resistance search.", "Resistance context."),
        "sector_temp": ("Sector", "HOT/WARM/COLD sector label.", "Based on sector_hot_score bins.", "HOT preferred for pullbacks."),
        "sector_temperature": ("Sector", "Hot/Neutral/Cold sector label.", "Base script sector performance/breadth logic.", "Sector context."),
        "sector_hot_score": ("Sector", "Sector strength score.", "Weighted sector performance/breadth score.", "Higher = stronger sector."),
        "sector_avg_1w": ("Sector", "Average sector 1-week performance.", "Mean one-week return by sector.", "Short-term sector context."),
        "sector_avg_1m": ("Sector", "Average sector 1-month performance.", "Mean one-month return by sector.", "Main sector heat input."),
        "sector_avg_3m": ("Sector", "Average sector 3-month performance.", "Mean three-month return by sector.", "Medium-term sector context."),
        "sector_count": ("Sector", "Number of stocks in sector group.", "Count of symbols in sector aggregation.", "Sample size."),
        "stock_count": ("Sector", "Sector stock count.", "Unique symbols by sector.", "Breadth/sample size."),
        "avg_1w_performance": ("Sector", "Sector average weekly return.", "Mean one_week_performance by sector.", "Short-term sector move."),
        "avg_1m_performance": ("Sector", "Sector average monthly return.", "Mean one_month_performance by sector.", "Main sector trend."),
        "avg_3m_performance": ("Sector", "Sector average 3M return.", "Mean three_month_performance by sector.", "Medium-term trend."),
        "pct_positive_1m": ("Sector", "Sector breadth.", "Percent of stocks with positive 1M return.", "Higher = broader strength."),
        "avg_final_watch_score": ("Sector", "Average final watch score by sector.", "Mean final_watch_score by sector.", "Sector quality context."),
        "hot_drop_score": ("Score", "Hot-sector pullback quality.", "sector_hot_score*35% + 1M drop magnitude*35% + range_position_1y*20% + RSI weakness*10%.", "Higher = better hot-sector pullback."),
        "recovery_score": ("Score", "Rebound potential.", "range_position_1y*35% + 1M drop magnitude*25% + sector_hot_score*20% + RSI weakness*20%.", "Higher = stronger recovery setup."),
        "reversal_setup_score": ("Score", "Possible technical bounce score.", "RSI weakness*35% + range_position_3m*25% + 1W drop magnitude*20% + sector_hot_score*20%.", "Higher = stronger reversal; final sheet requires basing."),
        "priority_score": ("Score", "Overall opportunity score.", "hot_drop_score*35% + recovery_score*35% + reversal_setup_score*20% + range_position_1y*10%.", "Main High Conviction ranking."),
        "final_watch_score": ("Score", "Original master watch score.", "value_range_score*40% + drop_alert_score*25% + technical_score*20% + fundamental_score*15%.", "Higher = stronger original setup."),
        "value_range_score": ("Score", "Original value/range score.", "regular_range_score*50% + covid_range_score*40% + price_suggest flags.", "Higher = better range/value setup."),
        "drop_alert_score": ("Score", "Recent drop severity.", "Absolute largest_recent_drop scaled/capped to 100.", "Higher = larger recent damage."),
        "watch_reason": ("Explanation", "Why stock appears interesting.", "Rule-based text using win%, drop, RSI, support, price_suggest flags.", "Quick interpretation."),
        "debtToEquity": ("Fundamental", "Leverage / balance sheet risk.", "Yahoo debtToEquity.", "Lower is better for this scanner; below 1.0 earns quality_score credit."),
        "revenueGrowth": ("Fundamental", "Recent revenue growth rate.", "Yahoo revenueGrowth; usually stored as a decimal, e.g. 0.12 = 12%.", "Positive/growing businesses are preferred; >= 5% earns quality_score credit."),
        "freeCashFlow": ("Fundamental", "Cash generated after operating/capital spending.", "Yahoo freeCashflow.", "Positive free cash flow earns quality_score credit and helps avoid cash-burning stocks."),
        "returnOnEquity": ("Fundamental", "Profitability relative to shareholder equity.", "Yahoo returnOnEquity; usually decimal, e.g. 0.18 = 18%.", ">= 10% earns quality_score credit; higher often indicates stronger profitability."),
        "priceToBook": ("Fundamental", "Price/book valuation.", "Yahoo priceToBook.", "0 < P/B <= 5 earns quality_score credit; usefulness varies by sector."),
        "quality_score": ("Fundamental Score", "Compact fundamental health score from 0 to 100.", "20 points each: debtToEquity < 1, freeCashFlow > 0, revenueGrowth >= 5%, returnOnEquity >= 10%, 0 < priceToBook <= 5.", "Higher = healthier fundamentals for pullback/recovery screening."),
        "quality_reason": ("Fundamental Score", "Plain-English explanation of quality_score.", "Lists which quality checks passed, such as Low debt, Positive FCF, Revenue growth >=5%, ROE >=10%, P/B <=5.", "Use this to quickly understand why the quality_score is high or low."),
        "shortRatio": ("Fundamental", "Short-interest days to cover.", "Yahoo shortRatio.", "Higher can imply short interest/squeeze risk."),
        "min_date": ("Date", "Date of historical low.", "Date where Close equals min.", "Low timing."),
        "max_date": ("Date", "Date of historical high.", "Date where Close equals max.", "High timing."),
        "mincovid_date": ("Date", "Date of Covid-period low.", "Date where pre-cutoff Close equals minCovid.", "Covid low timing."),
        "flag": ("Flag", "Watchlist/flag indicator.", "Existing script flag value.", "1 = manually flagged/special."),
        "is_key": ("Flag", "Keyword theme flag.", "Description contains configured keywords.", "Spot key themes like AI/energy/quantum."),
        "description": ("Text", "Business summary.", "Yahoo longBusinessSummary.", "Context only; kept last."),
        "latest_price_date": ("Data Quality", "Latest date found during enhancement merge.", "Latest date from daily price dataframe.", "Audit price freshness."),
    }
    rows=[]
    for col in columns:
        cat, measure, calc, use = details.get(col, ("Other", f"{col} exported by scanner.", "Generated/merged by script.", "Review only if needed."))
        rows.append({"Column": col, "Category": cat, "What It Measures": measure, "How Calculated": calc, "How To Read / Use": use})
    return pd.DataFrame(rows)


def slim_sheet_for_export(sheet_name: str, df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return df
    if sheet_name in GUIDE_OR_DOC_SHEETS:
        return df
    columns = SHEET_SPECIFIC_COLUMNS.get(sheet_name, SLIM_ACTION_COLUMNS)
    existing = [c for c in columns if c in df.columns]
    return df[existing].copy() if existing else df


def finalize_slim_workbook_views(views: dict[str, pd.DataFrame], dfagg: pd.DataFrame) -> dict[str, pd.DataFrame]:
    final = {}
    for name in ["Summary", "High Conviction", "Hot Sector Drops", "Recovery Candidates", "Largest 1W Drops", "Largest 2W Drops", "Largest 1M Drops", "Deep Value", "Momentum Leaders", "Reversal Setups", "Sector Heatmap"]:
        if name in views:
            final[name] = views[name]
    if isinstance(dfagg, pd.DataFrame) and not dfagg.empty:
        final["Full Master"] = dfagg
        audit = dfagg.copy()
        if "price_status" in audit.columns:
            audit = audit[~audit["price_status"].astype(str).eq("OK")].copy()
        else:
            audit = pd.DataFrame()
        final["Download Audit"] = audit
    elif "Full Master" in views:
        final["Full Master"] = views["Full Master"]
    return final

def main() -> None:
    args = parse_args()
    universe_key = args.universe
    end_date = last_market_end_date()

    run_start = time.perf_counter()

    with timer("Build universe"):
        universe_df = build_universe(args.universe)
        universe_df = force_include_extras(universe_df, include_extra=not args.no_extra)
        validate_extra_inclusion(universe_df)

        if args.max_tickers and args.max_tickers > 0:
            extras_only = universe_df[universe_df.get("is_extra", 0).eq(1)].copy()
            first_n = universe_df.head(args.max_tickers).copy()
            universe_df = pd.concat([first_n, extras_only], ignore_index=True).drop_duplicates("Symbol")
        tickers = universe_df["Symbol"].dropna().map(normalize_symbol).unique().tolist()
        print(f"Universe: {args.universe} | Tickers: {len(tickers):,} | Extras force-included: {not args.no_extra}")

    with timer("Load/update price history"):
        prices = load_or_update_prices(
            tickers=tickers,
            universe=universe_key,
            start_date=args.start_date,
            end_date=end_date,
            mode=args.mode,
            chunk_size=args.chunk_size,
            delay=args.delay,
        )
        print(f"Price rows: {len(prices):,}")

    with timer("Calculate price indicators"):
        df = prepare_price_features(prices)
        perf = latest_performance(df)
        stats = min_max_stats(df)

    with timer("Load/update fundamentals"):
        fundamentals = load_or_update_fundamentals(tickers, universe_key, args.fundamentals_mode)

        if fundamentals.empty:
            fundamentals = pd.DataFrame({"Symbol": tickers})
        if "AvgVol10d" not in fundamentals.columns or fundamentals["AvgVol10d"].isna().all():
            avg10 = (
                df.sort_values(["Symbol", "Date"])
                .assign(AvgVol10d_calc=lambda x: x.groupby("Symbol")["Volume"].transform(lambda s: s.rolling(10, min_periods=1).mean()))
                .sort_values("Date")
                .groupby("Symbol", as_index=False)
                .tail(1)[["Symbol", "AvgVol10d_calc"]]
            ) if "Volume" in df.columns else pd.DataFrame(columns=["Symbol", "AvgVol10d_calc"])
            fundamentals = fundamentals.merge(avg10, on="Symbol", how="left")
            fundamentals["AvgVol10d"] = pd.to_numeric(fundamentals.get("AvgVol10d"), errors="coerce").fillna(fundamentals["AvgVol10d_calc"])
            fundamentals.drop(columns=["AvgVol10d_calc"], inplace=True, errors="ignore")

    with timer("Calculate pivot/support levels"):
        pivots = support_pivot_latest(df, lookback_days=180, n_levels=3, min_pct_diff=0.05)

    with timer("Build master dfagg"):
        # IMPORTANT FIX:
        # Build Full Master from the complete universe list, not from perf.
        # If Full Master starts from perf, any ticker with a failed/missing Yahoo
        # price download disappears. Starting from universe_df keeps every ticker
        # in the workbook, then left-merges whatever data was successfully fetched.
        universe_cols = [
            c for c in [
                "Symbol", "Security", "Sector", "Sub_Sector",
                "Index", "Index_Origin", "is_extra"
            ]
            if c in universe_df.columns
        ]

        dfagg = universe_df[universe_cols].drop_duplicates("Symbol").copy()
        dfagg = dfagg.merge(perf, on="Symbol", how="left")
        dfagg = dfagg.merge(stats, on="Symbol", how="left")
        dfagg = dfagg.merge(fundamentals, on="Symbol", how="left")
        dfagg = dfagg.merge(pivots, on="Symbol", how="left")

        # Minimal audit flag: keeps added columns light but makes missing prices visible.
        # OK = ticker has latest price/performance row.
        # MISSING_PRICE = ticker is in universe, but no usable price row reached perf.
        dfagg["price_status"] = np.where(dfagg.get("last_close").notna(), "OK", "MISSING_PRICE")

        if "Security_yf" in dfagg.columns:
            dfagg["Security"] = dfagg["Security"].combine_first(dfagg["Security_yf"])
        if "Sector_yf" in dfagg.columns:
            dfagg["Sector"] = dfagg["Sector"].combine_first(dfagg["Sector_yf"])
        if "Sub_Sector_yf" in dfagg.columns:
            dfagg["Sub_Sector"] = dfagg["Sub_Sector"].combine_first(dfagg["Sub_Sector_yf"])

        try:
            watchlist = set(get_extra_tickers() + read_optional_ticker_file(CONFIG_DIR / "flagged_watch.csv"))
        except Exception as e:
            print(f"WARNING: Watchlist load failed, using extra_tickers only. Error: {e}")
            watchlist = set(get_extra_tickers())

        dfagg["flag"] = dfagg["Symbol"].isin(watchlist).astype(int)
        if "is_extra" not in dfagg.columns:
            dfagg["is_extra"] = dfagg["Symbol"].isin(set(get_extra_tickers())).astype(int)
        if "Index_Origin" not in dfagg.columns and "Index" in dfagg.columns:
            dfagg["Index_Origin"] = dfagg["Index"].map(primary_index_origin)

        dfagg = add_core_value_calculations(dfagg)
        dfagg = add_keyword_flags(dfagg)
        dfagg = add_scores(dfagg)
        dfagg = add_fundamental_quality(dfagg)
        dfagg, sector_summary = add_sector_temperature(dfagg)

    with timer("Export workbook and action CSVs"):
        # Rank using full internal columns first.
        # Output columns are cleaned only inside export_outputs().
        #
        # IMPORTANT:
        # The V10_6 enhancement logic must run INSIDE main(), because df and dfagg
        # are local variables created inside main(). Running it after main() causes:
        # NameError: name 'df' is not defined.
        try:
            from stock_analysis_v10_6_enhancements import run_v10_6_enhancements

            dfagg, enhanced_sheet_dict, column_dictionary = run_v10_6_enhancements(df, dfagg)
            print("V10_6 enhancement module applied successfully.")

        except ImportError as e:
            enhanced_sheet_dict = {}
            print(f"WARNING: Enhancement module not found or could not import. Continuing with base V10_6 output. Error: {e}")

        except Exception as e:
            enhanced_sheet_dict = {}
            print(f"WARNING: Enhancement module failed. Continuing with base V10_6 output. Error: {e}")

        views = make_ranked_views(dfagg, min_market_cap=args.min_market_cap)
        views = add_sector_summary_view(views, sector_summary)

        # Build V10_6 views from the fully enhanced master AFTER applying capMil.
        # This avoids the issue where an enhancement tab is cut to top 100 first
        # and then market-cap filtering leaves only a couple of rows.
        v10_6_views = build_v10_6_views_from_filtered_master(
            dfagg,
            enhanced_sheet_dict,
            min_market_cap=args.min_market_cap,
        )
        views.update(v10_6_views)

        # Keep the final workbook slim and focused.
        views = finalize_slim_workbook_views(views, dfagg)

        export_outputs(views)

    save_profile_report()
    elapsed = time.perf_counter() - run_start
    print(f"\\nCOMPLETE: Stock analysis finished successfully in {elapsed/60:.2f} minutes.")
    print(f"Main workbook: {OUTPUT_WORKBOOK}")
    print("Action CSVs: top_high_conviction.csv, top_watchlist_candidates.csv, top_recent_drops.csv")


if __name__ == "__main__":
    main()
