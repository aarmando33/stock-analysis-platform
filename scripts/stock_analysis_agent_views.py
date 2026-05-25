"""Expert research views layered onto the stock scanner."""

from __future__ import annotations

scanner = None
pd = None
np = None
_original_prepare_price_features = None
_original_latest_performance = None
_original_make_ranked_views = None
_original_get_column_dictionary = None


def prepare_price_features(prices):
    out = _original_prepare_price_features(prices)
    if out.empty:
        return out
    grouped = out.groupby("Symbol", group_keys=False)
    low_col = "Low" if "Low" in out.columns else "Close"
    high_col = "High" if "High" in out.columns else "Close"
    out["two_week_close"] = grouped["Close"].shift(10).round(4)
    out["two_week_performance"] = ((out["Close"] / out["two_week_close"] - 1) * 100).round(4)
    out["support_1m"] = grouped[low_col].transform(lambda x: x.rolling(21, min_periods=5).min())
    out["resistance_1m"] = grouped[high_col].transform(lambda x: x.rolling(21, min_periods=5).max())
    out["support_6m"] = grouped[low_col].transform(lambda x: x.rolling(126, min_periods=21).min())
    out["resistance_6m"] = grouped[high_col].transform(lambda x: x.rolling(126, min_periods=21).max())
    base_high = grouped[high_col].transform(lambda x: x.rolling(5, min_periods=5).max())
    base_low = grouped[low_col].transform(lambda x: x.rolling(5, min_periods=5).min())
    out["basing_range_5d_pct"] = ((base_high - base_low) / base_high).replace([np.inf, -np.inf], np.nan)
    out["basing_5d_10pct"] = out["basing_range_5d_pct"].le(0.10).fillna(False)
    return out


def latest_performance(df):
    out = _original_latest_performance(df)
    if df.empty:
        return out
    latest = df.sort_values("Date").groupby("Symbol", as_index=False).tail(1)
    extra_columns = [
        "Symbol", "two_week_close", "two_week_performance",
        "support_1m", "resistance_1m", "support_6m", "resistance_6m",
        "basing_range_5d_pct", "basing_5d_10pct",
    ]
    extra = latest[[col for col in extra_columns if col in latest.columns]].copy()
    return out.merge(extra, on="Symbol", how="left")


def _numeric(df, column):
    if column not in df.columns:
        return pd.Series(np.nan, index=df.index)
    return pd.to_numeric(df[column], errors="coerce")


def add_expert_analysis_fields(dfagg):
    """Create transparent value, quality, management-proxy and timing scores."""
    out = dfagg.copy()
    cap_mil = _numeric(out, "capMil")
    market_cap = _numeric(out, "Marketcap")
    free_cash_flow = _numeric(out, "freeCashFlow")
    roe = _numeric(out, "returnOnEquity")
    revenue_growth = _numeric(out, "revenueGrowth")
    price_to_book = _numeric(out, "priceToBook")
    debt_to_equity_raw = _numeric(out, "debtToEquity")
    price = _numeric(out, "last_close")
    rsi = _numeric(out, "RSI")

    out["market_cap_gate_2b"] = cap_mil.ge(2000)
    out["free_cash_flow_yield_pct"] = np.where(
        market_cap.gt(0),
        free_cash_flow / market_cap * 100,
        np.nan,
    )
    out["debt_to_equity_pct"] = np.where(
        debt_to_equity_raw.le(10),
        debt_to_equity_raw * 100,
        debt_to_equity_raw,
    )
    debt_pct = pd.Series(out["debt_to_equity_pct"], index=out.index)
    fcf_yield = pd.Series(out["free_cash_flow_yield_pct"], index=out.index)
    quality_parts = pd.DataFrame(
        {
            "positive_fcf": free_cash_flow.gt(0).astype(int) * 20,
            "strong_roe": roe.ge(0.15).astype(int) * 20,
            "revenue_growth": revenue_growth.ge(0.05).astype(int) * 15,
            "low_debt": debt_pct.le(50).astype(int) * 15,
            "fcf_yield": fcf_yield.ge(4).astype(int) * 20,
            "reasonable_book_value": (price_to_book.gt(0) & price_to_book.le(5)).astype(int) * 10,
        }
    )
    out["buffett_fundamental_score"] = quality_parts.sum(axis=1)
    out["strong_fundamentals"] = (
        out["market_cap_gate_2b"]
        & out["buffett_fundamental_score"].ge(70)
        & free_cash_flow.gt(0)
        & roe.ge(0.10)
    )
    out["management_proxy_score"] = (
        roe.ge(0.15).astype(int) * 30
        + free_cash_flow.gt(0).astype(int) * 25
        + revenue_growth.ge(0.05).astype(int) * 20
        + debt_pct.le(50).astype(int) * 25
    )
    out["management_assessment"] = np.where(
        out["management_proxy_score"].ge(75),
        "Strong operating/capital discipline proxy; review filings",
        "Requires filing review for management quality",
    )
    value_range = _numeric(out, "value_range_score").fillna(0)
    out["undervalued_quality_score"] = (
        out["buffett_fundamental_score"] * 0.55
        + value_range * 0.25
        + fcf_yield.clip(0, 10).fillna(0) * 10 * 0.20
    ).round(2)

    supports = {
        "support_5d_pct": "Support1_5d",
        "support_1m_pct": "support_1m",
        "support_6m_pct": "support_6m",
        "support_covid_pct": "minCovid_filled",
    }
    for distance_col, support_col in supports.items():
        support = _numeric(out, support_col)
        distance = (price - support) / price * 100
        out[distance_col] = distance.where(support.le(price) & price.gt(0))
    out["nearest_support_distance_pct"] = out[list(supports)].min(axis=1, skipna=True).round(2)
    out["near_support_10pct"] = out["nearest_support_distance_pct"].between(0, 10, inclusive="both")
    basing = out.get("basing_5d_10pct", pd.Series(False, index=out.index)).fillna(False).astype(bool)
    out["technical_entry_score"] = (
        out["near_support_10pct"].astype(int) * 35
        + basing.astype(int) * 30
        + rsi.between(25, 50, inclusive="both").astype(int) * 20
        + _numeric(out, "one_month_performance").lt(0).astype(int) * 15
    )
    out["expert_research_score"] = (
        out["undervalued_quality_score"] * 0.65
        + out["technical_entry_score"] * 0.35
    ).round(2)
    return out


def make_ranked_views(dfagg, min_market_cap=2000):
    enriched = add_expert_analysis_fields(dfagg)
    views = _original_make_ranked_views(enriched, min_market_cap=min_market_cap)
    eligible = enriched[
        enriched["market_cap_gate_2b"]
        & enriched.get("price_status", pd.Series("OK", index=enriched.index)).eq("OK")
    ].copy()
    quality = eligible[eligible["strong_fundamentals"]].copy()

    def top(df, column, ascending=False):
        if df.empty or column not in df.columns:
            return df.head(100)
        return df.sort_values(column, ascending=ascending, na_position="last").head(100)

    views["Buffett Quality"] = top(quality, "buffett_fundamental_score")
    views["Undervalued Quality"] = top(quality, "expert_research_score")
    views["Largest Win Opportunity"] = top(quality, "win%")
    views["Quality 2W Declines"] = top(quality, "two_week_performance", ascending=True)
    views["Quality 1M Declines"] = top(quality, "one_month_performance", ascending=True)
    views["Quality 3M Declines"] = top(quality, "three_month_performance", ascending=True)
    views["Basing Near Support"] = top(
        quality[
            quality.get("basing_5d_10pct", pd.Series(False, index=quality.index)).fillna(False)
            & quality["near_support_10pct"]
        ],
        "expert_research_score",
    )
    views["Support Resistance Review"] = top(quality, "nearest_support_distance_pct", ascending=True)
    views["Management Proxy Review"] = top(quality, "management_proxy_score")
    return views


def get_column_dictionary(columns):
    dictionary = _original_get_column_dictionary(columns)
    details = {
        "two_week_performance": ("Performance", "Approx. 2-week return.", "(Close / two_week_close - 1) * 100.", "Negative = two-week decline."),
        "buffett_fundamental_score": ("Quality", "Buffett-style quality score.", "FCF, ROE, revenue growth, leverage, FCF yield and P/B checks.", "70+ with required FCF/ROE enters strong-fundamental views."),
        "management_proxy_score": ("Management Proxy", "Operating/capital-discipline proxy.", "ROE, FCF, growth and debt discipline only.", "Requires filing review before concluding management is strong."),
        "management_assessment": ("Management Proxy", "Management-review reminder.", "Text derived from proxy score.", "Not a final management judgment."),
        "free_cash_flow_yield_pct": ("Valuation", "FCF yield.", "freeCashFlow / Marketcap * 100.", "Higher positive yield may indicate better value."),
        "undervalued_quality_score": ("Score", "Quality and value score.", "55% fundamentals, 25% range value, 20% FCF yield component.", "Higher = stronger valuation candidate."),
        "technical_entry_score": ("Technical", "Timing/setup score.", "Support proximity, five-day base, RSI zone and monthly pullback.", "Higher = better technical setup after quality gate."),
        "expert_research_score": ("Score", "Combined research priority.", "65% undervalued_quality_score plus 35% technical_entry_score.", "Primary rank for quality candidates."),
        "basing_5d_10pct": ("Technical", "Tight one-week base flag.", "TRUE when five-session high-low range is <=10%.", "Potential stabilization after decline."),
        "support_1m": ("Technical", "One-month support.", "Rolling 21-session low.", "Short/medium-term downside reference."),
        "support_6m": ("Technical", "Six-month support.", "Rolling 126-session low.", "Longer-term downside reference."),
        "nearest_support_distance_pct": ("Technical", "Distance above nearest support.", "Smallest non-negative distance to tracked supports.", "0-10% is near support."),
    }
    if "Column" in dictionary.columns:
        for column, values in details.items():
            mask = dictionary["Column"].eq(column)
            if mask.any():
                category, measure, calculation, usage = values
                dictionary.loc[mask, "Category"] = category
                dictionary.loc[mask, "What It Measures"] = measure
                dictionary.loc[mask, "How Calculated"] = calculation
                dictionary.loc[mask, "How To Read / Use"] = usage
    return dictionary


def install_agent_views(target_scanner) -> None:
    global scanner, pd, np
    global _original_prepare_price_features, _original_latest_performance
    global _original_make_ranked_views, _original_get_column_dictionary
    scanner = target_scanner
    pd = scanner.pd
    np = scanner.np
    _original_prepare_price_features = scanner.prepare_price_features
    _original_latest_performance = scanner.latest_performance
    _original_make_ranked_views = scanner.make_ranked_views
    _original_get_column_dictionary = scanner.get_column_dictionary
    scanner.prepare_price_features = prepare_price_features
    scanner.latest_performance = latest_performance
    scanner.make_ranked_views = make_ranked_views
    scanner.get_column_dictionary = get_column_dictionary
    expert_columns = [
        "Symbol", "Security", "Index", "Sector", "price_status", "Marketcap", "capMil",
        "last_close", "two_week_close", "two_week_performance", "one_month_performance",
        "three_month_performance", "six_month_performance", "win%", "win%_covid",
        "freeCashFlow", "free_cash_flow_yield_pct", "returnOnEquity", "revenueGrowth",
        "debtToEquity", "debt_to_equity_pct", "priceToBook", "buffett_fundamental_score",
        "management_proxy_score", "management_assessment", "undervalued_quality_score",
        "technical_entry_score", "expert_research_score", "basing_5d_10pct",
        "basing_range_5d_pct", "Support1_5d", "support_1m", "support_6m",
        "minCovid_filled", "resistance_1m", "resistance_6m", "nearest_support_distance_pct",
        "near_support_10pct", "RSI", "watch_reason",
    ]
    for sheet in [
        "Buffett Quality", "Undervalued Quality", "Largest Win Opportunity",
        "Quality 2W Declines", "Quality 1M Declines", "Quality 3M Declines",
        "Basing Near Support", "Support Resistance Review", "Management Proxy Review",
    ]:
        scanner.SHEET_SPECIFIC_COLUMNS[sheet] = expert_columns
    scanner.SHEET_SPECIFIC_COLUMNS["Full Master"] = list(
        dict.fromkeys(scanner.SHEET_SPECIFIC_COLUMNS.get("Full Master", []) + expert_columns)
    )
