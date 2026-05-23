from __future__ import annotations
from pathlib import Path
from typing import Optional, Dict, Any
import os

import pandas as pd
import numpy as np

# Optional YAML support (config scoring)
try:
    import yaml  # pip install pyyaml
except Exception:
    yaml = None


# ============== Helpers ==============
def _normalize_symbol(df: pd.DataFrame, col: str = "Symbol") -> pd.DataFrame:
    """Uppercase ticker symbols and ensure it's a string column."""
    if col in df.columns:
        df[col] = df[col].astype(str).str.upper()
    return df

def _ensure_columns(df: pd.DataFrame, required: list[str]) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise KeyError(f"Missing required columns: {missing}")

def _cap_filter(df: pd.DataFrame, cap_threshold: float) -> pd.Series:
    """
    Build boolean mask for Marketcap >= threshold.
    Falls back to capMil * 1e6 if Marketcap missing.
    """
    if "Marketcap" in df.columns:
        cap = pd.to_numeric(df["Marketcap"], errors="coerce")
    elif "capMil" in df.columns:
        cap = pd.to_numeric(df["capMil"], errors="coerce") * 1_000_000
    else:
        cap = pd.Series(np.nan, index=df.index)
    return cap >= cap_threshold

def _winsorize(series: pd.Series, low_q=0.01, high_q=0.99) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    if s.notna().sum() == 0:
        return s
    lo, hi = s.quantile(low_q), s.quantile(high_q)
    return s.clip(lower=lo, upper=hi)

def _normalize_01(series: pd.Series) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    if s.notna().sum() == 0:
        return s.replace(s, 0.0)
    s = _winsorize(s)
    mn, mx = s.min(), s.max()
    if pd.isna(mn) or pd.isna(mx) or mn == mx:
        return s.replace(s, 0.0)
    return (s - mn) / (mx - mn)

def _invert_01(series01: pd.Series) -> pd.Series:
    return 1.0 - pd.to_numeric(series01, errors="coerce").fillna(0.0)

def _safe_div(a: pd.Series, b: pd.Series) -> pd.Series:
    a = pd.to_numeric(a, errors="coerce")
    b = pd.to_numeric(b, errors="coerce").replace(0, np.nan)
    return (a / b).replace([np.inf, -np.inf], np.nan)

def _load_scoring_config(path: Optional[str]) -> Optional[dict]:
    if not path:
        return None
    if yaml is None:
        raise RuntimeError("PyYAML is not installed. Run: pip install pyyaml")
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    return cfg

def _load_prior_snapshot(path: Path) -> Optional[pd.DataFrame]:
    """
    Read a previous rankings CSV and return normalized DataFrame with
    ['Symbol','candidate','rank'] or None if malformed/empty.
    Handles Symbol-as-index and 'Unnamed: 0'.
    """
    try:
        df = pd.read_csv(path)
    except Exception:
        return None
    if df is None or len(df) == 0:
        return None

    # standardize column names
    df.columns = [str(c).strip().lower() for c in df.columns]

    # ensure symbol column
    if "symbol" not in df.columns:
        if getattr(df.index, "name", None) in ("symbol", "Symbol"):
            df = df.reset_index()
            df.columns = [str(c).strip().lower() for c in df.columns]
        elif "unnamed: 0" in df.columns:
            df = df.rename(columns={"unnamed: 0": "symbol"})
        else:
            # attempt rescue by fuzzy match
            maybe = [c for c in df.columns if "symbol" in c]
            if maybe:
                df = df.rename(columns={maybe[0]: "symbol"})
            else:
                return None

    # candidate/rank presence
    if "candidate" not in df.columns:
        df["candidate"] = "N"
    if "rank" not in df.columns:
        # fallback: rank from composite_score if available
        if "composite_score" in df.columns:
            df["rank"] = pd.to_numeric(df["composite_score"], errors="coerce").rank(ascending=False, method="min")
        elif "composite_score_cfg" in df.columns:
            df["rank"] = pd.to_numeric(df["composite_score_cfg"], errors="coerce").rank(ascending=False, method="min")
        else:
            return None

    out = df[["symbol", "candidate", "rank"]].copy()
    out = out.rename(columns={"symbol": "Symbol"})
    out["Symbol"] = out["Symbol"].astype(str).str.upper()
    out["rank"] = pd.to_numeric(out["rank"], errors="coerce")
    return out


# ============== Config-driven scoring (no P/E/policy required) ==============
def _compute_config_score(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """
    Build 'composite_score_cfg' using weights/thresholds.
    Uses only columns you actually have; missing features contribute 0.
    Features supported with v7:
      - win%  (higher -> more undervalued)
      - RSI   (below threshold better)
      - momentum (uses one_month_performance_num, three_month_performance_num; drop -> better)
      - d2e (debtToEquity; lower better)
      - pb  (priceToBook; lower better)
      - off_highs (from max/min/last_close OR off_high_52w if you add it)
      - basing (is_basing; 1 -> better)
    """
    df = df.copy()
    w = (cfg or {}).get("weights", {})
    t = (cfg or {}).get("thresholds", {})

    # off_highs
    if {"max", "min", "last_close"}.issubset(df.columns):
        rng = pd.to_numeric(df["max"], errors="coerce") - pd.to_numeric(df["min"], errors="coerce")
        off = pd.to_numeric(df["max"], errors="coerce") - pd.to_numeric(df["last_close"], errors="coerce")
        off_highs_raw = _safe_div(off, rng)  # 0 near high, 1 near low
    elif "off_high_52w" in df.columns:
        off_highs_raw = pd.to_numeric(df["off_high_52w"], errors="coerce")
    else:
        off_highs_raw = pd.Series(np.nan, index=df.index)
    off_highs = _normalize_01(off_highs_raw)

    # rsi
    rsi_thr = float(t.get("rsi_oversold", 30))
    if "RSI" in df.columns:
        rsi = pd.to_numeric(df["RSI"], errors="coerce")
        rsi_score = ((rsi_thr - rsi) / max(rsi_thr, 1)).clip(lower=0)  # >0 when below thr
        rsi_score = _normalize_01(rsi_score)
    else:
        rsi_score = pd.Series(0.0, index=df.index)

    # win%
    if "win%" in df.columns:
        win_raw = pd.to_numeric(df["win%"], errors="coerce")
        if win_raw.max(skipna=True) is not np.nan and win_raw.max(skipna=True) > 1.5:
            win_raw = win_raw / 100.0
        win_pct = _normalize_01(win_raw)  # higher is better
    else:
        win_pct = pd.Series(0.0, index=df.index)

    # d2e
    if "debtToEquity" in df.columns:
        d2e_raw = pd.to_numeric(df["debtToEquity"], errors="coerce")
        d2e = _invert_01(_normalize_01(d2e_raw))
    else:
        d2e = pd.Series(0.0, index=df.index)

    # pb
    if "priceToBook" in df.columns:
        pb_raw = pd.to_numeric(df["priceToBook"], errors="coerce")
        pb = _invert_01(_normalize_01(pb_raw))
    else:
        pb = pd.Series(0.0, index=df.index)

    # momentum (recent drop preferred)
    one_m = pd.to_numeric(df.get("one_month_performance_num", pd.Series(np.nan, index=df.index)), errors="coerce")
    three_m = pd.to_numeric(df.get("three_month_performance_num", pd.Series(np.nan, index=df.index)), errors="coerce")
    six_m = pd.to_numeric(df.get("six_month_performance_num", pd.Series(np.nan, index=df.index)), errors="coerce")
    # emphasize 1m/3m, lightly 6m
    mom_raw = -(0.5 * one_m + 0.35 * three_m + 0.15 * six_m)  # drop -> positive
    momentum = _normalize_01(mom_raw)

    # basing
    if "is_basing" in df.columns:
        basing = pd.to_numeric(df["is_basing"], errors="coerce").fillna(0.0).clip(0, 1)
    else:
        basing = pd.Series(0.0, index=df.index)

    # helper to fetch weight safely
    def wget(k: str, default: float = 0.0) -> float:
        try:
            return float(w.get(k, default) or 0.0)
        except Exception:
            return 0.0

    parts = {
        "off_highs": wget("off_highs") * off_highs,
        "rsi": wget("rsi") * rsi_score,
        "win_pct": wget("win_pct") * win_pct,
        "d2e": wget("d2e") * d2e,
        "pb": wget("pb") * pb,
        "momentum": wget("momentum") * momentum,
        "basing": wget("basing") * basing,
        # intentionally no pe/policy since v7 lacks them
    }

    # Keep contributions for auditability
    for name, series in parts.items():
        df[f"score_{name}"] = series

    df["composite_score_cfg"] = sum(parts.values())
    return df


# ============== Public API ==============
def generate_rankings_watchlists(
    dfagg: pd.DataFrame,
    cap_threshold: float = 2_000_000_000,   # $2B
    topn: int = 50,
    output_dir: str | os.PathLike = "outputs",
    run_date: Optional[str] = None,         # "YYYY-MM-DD"; None = today (local)
    write_files: bool = True,
    dataset_tag: Optional[str] = None,      # e.g., "sp500", "nasdaq", "all"
    scoring_config_path: Optional[str] = None,  # path to YAML (optional)
    score_column: Optional[str] = None,     # which score to rank by; defaults to cfg if provided
) -> Dict[str, Any]:
    """
    Create rankings + watchlist artifacts for a universe (e.g., full, S&P 500),
    filtered to Marketcap >= cap_threshold. If scoring_config_path provided,
    compute 'composite_score_cfg' and per-feature columns ('score_*').
    """
    if dfagg is None or len(dfagg) == 0:
        return {"status": "empty_input", "message": "dfagg is empty."}

    out_df = dfagg.copy()

    # Ensure Symbol is a column
    if "Symbol" not in out_df.columns:
        if getattr(out_df.index, "name", None) == "Symbol":
            out_df = out_df.reset_index()
        else:
            raise KeyError(f"dfagg missing 'Symbol' column. "
                           f"Columns={list(out_df.columns)}, index_name={getattr(out_df.index, 'name', None)}")
    _normalize_symbol(out_df, "Symbol")

    # Optional: compute config-driven score
    cfg = _load_scoring_config(scoring_config_path)
    if cfg is not None:
        out_df = _compute_config_score(out_df, cfg)

    # Decide ranking score
    if score_column is None:
        score_column = "composite_score_cfg" if "composite_score_cfg" in out_df.columns else "composite_score"
    _ensure_columns(out_df, ["Symbol", score_column])

    # Derive rank/candidate if missing
    if "rank" not in out_df.columns or out_df.get("rank").isna().all():
        out_df["rank"] = out_df[score_column].rank(ascending=False, method="min")
    if "candidate" not in out_df.columns or out_df.get("candidate").isna().all():
        out_df["candidate"] = np.where(out_df["rank"] <= topn, "Y", "N")

    # Filter by cap
    mask_cap = _cap_filter(out_df, cap_threshold)
    df_cap = out_df.loc[mask_cap].copy()

    OUTPUT_DIR = Path(output_dir)
    if write_files:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if run_date is None:
        run_date = pd.Timestamp.today().strftime("%Y-%m-%d")

    tag = f"_{dataset_tag}" if dataset_tag else ""
    base = f"cap2b{tag}"

    files = {
        "rank_today":       OUTPUT_DIR / f"rankings_{base}_{run_date}.csv",
        "rank_latest":      OUTPUT_DIR / f"rankings_{base}_latest.csv",
        "topn_today":       OUTPUT_DIR / f"top{topn}_{base}_{run_date}.csv",
        "history":          OUTPUT_DIR / f"rankings_{base}_history.csv",
        "promotions_today": OUTPUT_DIR / f"watchlist_promotions_{base}_{run_date}.csv",
        "demotions_today":  OUTPUT_DIR / f"watchlist_demotions_{base}_{run_date}.csv",
        "movers_today":     OUTPUT_DIR / f"rank_movers_{base}_{run_date}.csv",
    }

    if df_cap.empty:
        if write_files and not files["history"].exists():
            pd.DataFrame(columns=["run_date","Symbol","rank",score_column,"candidate"]).to_csv(files["history"], index=False)
        return {
            "status": "ok",
            "message": f"No names ≥ ${cap_threshold:,.0f}.",
            "paths": files,
            "counts": {"universe_cap2b": 0, "topn": 0, "promotions": 0, "demotions": 0},
        }

    # Sorted snapshot & TopN
    df_cap_sorted = df_cap.sort_values([score_column, "rank"], ascending=[False, True]).reset_index(drop=True)
    if "Symbol" not in df_cap_sorted.columns and getattr(df_cap_sorted.index, "name", None) == "Symbol":
        df_cap_sorted = df_cap_sorted.reset_index()
    _normalize_symbol(df_cap_sorted, "Symbol")
    top_df = df_cap_sorted.head(topn).copy()

    # History
    present_cols = ["Symbol","rank",score_column,"candidate"]
    for extra in ["Index","Sector","capMil","RSI","composite_score_cfg"]:
        if extra in df_cap_sorted.columns and extra not in present_cols:
            present_cols.append(extra)
    today_hist = df_cap_sorted[present_cols].copy()
    today_hist.insert(0, "run_date", run_date)

    if write_files:
        df_cap_sorted.to_csv(files["rank_today"], index=False)
        df_cap_sorted.to_csv(files["rank_latest"], index=False)
        top_df.to_csv(files["topn_today"], index=False)
        if files["history"].exists():
            old_hist = pd.read_csv(files["history"])
            hist_all = pd.concat([old_hist, today_hist], ignore_index=True)
        else:
            hist_all = today_hist
        hist_all.to_csv(files["history"], index=False)

    # Prior snapshot → prev_df
    prev_df = None
    if write_files and OUTPUT_DIR.exists():
        prior_files = sorted([p for p in OUTPUT_DIR.glob(f"rankings_{base}_*.csv") if run_date not in p.name])
        if prior_files:
            prev_df = _load_prior_snapshot(prior_files[-1])

    if prev_df is not None and not prev_df.empty:
        if "Symbol" not in prev_df.columns and getattr(prev_df.index, "name", None) == "Symbol":
            prev_df = prev_df.reset_index()
        _normalize_symbol(prev_df, "Symbol")
        prev_candidates = set(prev_df.loc[prev_df["candidate"] == "Y", "Symbol"])
        rank_prev = prev_df[["Symbol", "rank"]].rename(columns={"rank": "rank_prev"})
    else:
        prev_candidates = set()
        rank_prev = pd.DataFrame({"Symbol": pd.Series(dtype="object"),
                                  "rank_prev": pd.Series(dtype="float")})

    # Promotions / Demotions
    curr_candidates = set(df_cap_sorted.loc[df_cap_sorted["candidate"] == "Y", "Symbol"])
    promotions = sorted(curr_candidates - prev_candidates)
    demotions  = sorted(prev_candidates - curr_candidates)
    df_promotions = df_cap_sorted[df_cap_sorted["Symbol"].isin(promotions)].copy()
    if prev_df is not None and not prev_df.empty and demotions:
        df_demotions = prev_df[prev_df["Symbol"].isin(demotions)].copy()
    else:
        df_demotions = pd.DataFrame(columns=["Symbol","rank","candidate"])

    # Movers (defensive)
    try:
        if "Symbol" not in rank_prev.columns and getattr(rank_prev.index, "name", None) == "Symbol":
            rank_prev = rank_prev.reset_index()
        if "Symbol" not in rank_prev.columns:
            rank_prev = pd.DataFrame({"Symbol": pd.Series(dtype="object"), "rank_prev": pd.Series(dtype="float")})
        _normalize_symbol(rank_prev, "Symbol")

        movers = df_cap_sorted.merge(rank_prev, on="Symbol", how="left")
        movers["rank_prev"] = pd.to_numeric(movers["rank_prev"], errors="coerce")
        movers["rank_change"] = movers["rank_prev"] - movers["rank"]
        movers_out = movers.sort_values("rank_change", ascending=False).head(50).copy()
    except Exception:
        movers_out = pd.DataFrame(columns=["Symbol","rank_prev","rank","rank_change"])

    if write_files:
        if not df_promotions.empty:
            df_promotions.to_csv(files["promotions_today"], index=False)
        if not df_demotions.empty:
            df_demotions.to_csv(files["demotions_today"], index=False)
        movers_out.to_csv(files["movers_today"], index=False)

        return {
            "status": "ok",
            "run_date": run_date,
            "topn": topn,
            "cap_threshold": cap_threshold,
            "score_column": score_column,
            "paths": files,
            "counts": {
                "universe_cap2b": len(df_cap_sorted),
                "topn": len(top_df),
                "promotions": len(df_promotions),
                "demotions": len(df_demotions),
            },
        }
    else:
        return {
            "status": "ok",
            "run_date": run_date,
            "topn": topn,
            "cap_threshold": cap_threshold,
            "score_column": score_column,
            "counts": {
                "universe_cap2b": len(df_cap_sorted),
                "topn": len(top_df),
                "promotions": len(df_promotions),
                "demotions": len(df_demotions),
            },
            "df_cap_sorted": df_cap_sorted,
            "top_df": top_df,
            "promotions_df": df_promotions,
            "demotions_df": df_demotions,
            "movers_df": movers_out,
        }
