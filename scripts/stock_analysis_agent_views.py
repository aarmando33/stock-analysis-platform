"""Value-investing and technical-analysis research views for the stock scanner."""

from __future__ import annotations

scanner = None
pd = None
np = None
_original_prepare_price_features = None
_original_latest_performance = None
_original_make_ranked_views = None
_original_get_column_dictionary = None
_original_finalize_slim_workbook_views = None
_original_build_table_of_contents = None

AGENT_VIEW_NAMES = [
    "Value Technical Picks",
    "Largest Move Win %",
    "Hot Quality 2W Declines",
    "Hot Quality 1M Declines",
    "Basing Near Support",
    "Support Analysis",
]

AGENT_VIEW_GUIDES = {
    "Value Technical Picks": (
        "Which value-qualified companies also have the best technical setup?",
        "price_status = OK; capMil >= 2000; value_investing_score >= 70; positive FCF; ROE >= 10%.",
        "Value quality, management outcome proxy, technical setup, support levels and industry heat.",
        "Sorted by expert_research_score descending.",
        "Primary combined value-and-entry research list.",
    ),
    "Largest Move Win %": (
        "Which value-qualified stocks have the strongest original historical move-win measure?",
        "Same value-quality and $2B screen as Value Technical Picks.",
        "Original script win% plus new value and technical review columns.",
        "Sorted by win% descending.",
        "Use as a historical ranking input, then check support and technical rating.",
    ),
    "Hot Quality 2W Declines": (
        "Which value-qualified stocks declined over two weeks inside a hot sector or sub-sector?",
        "Value-quality screen; hot_industry_context = TRUE; two_week_performance < 0.",
        "Two-week pullback, sector/sub-sector heat, support and basing context.",
        "Sorted by two_week_performance ascending.",
        "Find declines within stronger industry context for review.",
    ),
    "Hot Quality 1M Declines": (
        "Which value-qualified stocks declined over one month inside a hot sector or sub-sector?",
        "Value-quality screen; hot_industry_context = TRUE; one_month_performance < 0.",
        "One-month pullback, sector/sub-sector heat, support and basing context.",
        "Sorted by one_month_performance ascending.",
        "Find medium-term pullbacks within stronger industry context.",
    ),
    "Basing Near Support": (
        "Which value-qualified stocks are forming a one-week base near support?",
        "Value-quality screen; basing_5d_10pct = TRUE; nearest_support_distance_pct between 0 and 10.",
        "Weekly basing and multi-horizon support proximity.",
        "Sorted by expert_research_score descending.",
        "Look for stabilization before entry decisions.",
    ),
    "Support Analysis": (
        "Which value-qualified stocks have the strongest technical support context?",
        "Same value-quality and $2B screen as Value Technical Picks.",
        "One-month, six-month and post-Covid-history average support levels and proximity scores.",
        "Sorted by technical_analysis_score descending.",
        "Use to compare downside reference levels and entry timing.",
    ),
}


def prepare_price_features(prices):
    out = _original_prepare_price_features(prices)
    if out.empty:
        return out
    grouped = out.groupby("Symbol", group_keys=False)
    low_col = "Low" if "Low" in out.columns else "Close"
    high_col = "High" if "High" in out.columns else "Close"
    out["two_week_close"] = grouped["Close"].shift(10).round(4)
    out["two_week_performance"] = ((out["Close"] / out["two_week_close"] - 1) * 100).round(4)
    out["five_year_close"] = grouped["Close"].shift(1260).round(4)
    out["five_year_cagr_pct"] = (
        ((out["Close"] / out["five_year_close"]) ** (1 / 5) - 1) * 100
    ).round(2)
    out["support_1m"] = grouped[low_col].transform(lambda x: x.rolling(21, min_periods=5).min())
    out["resistance_1m"] = grouped[high_col].transform(lambda x: x.rolling(21, min_periods=5).max())
    out["support_6m"] = grouped[low_col].transform(lambda x: x.rolling(126, min_periods=21).min())
    out["resistance_6m"] = grouped[high_col].transform(lambda x: x.rolling(126, min_periods=21).max())
    out["support_avg_1m"] = grouped[low_col].transform(lambda x: x.rolling(21, min_periods=5).mean())
    out["support_avg_6m"] = grouped[low_col].transform(lambda x: x.rolling(126, min_periods=21).mean())
    out["support_avg_covid"] = grouped[low_col].transform(lambda x: x.expanding(min_periods=21).mean())
    base_high = grouped[high_col].transform(lambda x: x.rolling(5, min_periods=5).max())
    base_low = grouped[low_col].transform(lambda x: x.rolling(5, min_periods=5).min())
    out["basing_range_5d_pct"] = ((base_high - base_low) / base_high).replace([np.inf, -np.inf], np.nan) * 100
    out["basing_5d_10pct"] = out["basing_range_5d_pct"].le(10).fillna(False)
    return out


def latest_performance(df):
    out = _original_latest_performance(df)
    if df.empty:
        return out
    latest = df.sort_values("Date").groupby("Symbol", as_index=False).tail(1)
    extra_columns = [
        "Symbol", "two_week_close", "two_week_performance",
        "five_year_close", "five_year_cagr_pct",
        "support_1m", "resistance_1m", "support_6m", "resistance_6m",
        "support_avg_1m", "support_avg_6m", "support_avg_covid",
        "basing_range_5d_pct", "basing_5d_10pct",
    ]
    extra = latest[[col for col in extra_columns if col in latest.columns]].copy()
    return out.merge(extra, on="Symbol", how="left")


def _numeric(df, column):
    if column not in df.columns:
        return pd.Series(np.nan, index=df.index)
    return pd.to_numeric(df[column], errors="coerce")


def _support_score(price, reference):
    distance = ((price - reference).abs() / price * 100).where(price.gt(0) & reference.gt(0))
    return (100 - distance * 10).clip(0, 100).round(2)


def _add_subsector_heat(out):
    if "Sub_Sector" not in out.columns:
        out["Sub_Sector"] = "Unknown"
    out["Sub_Sector"] = out["Sub_Sector"].fillna("Unknown").astype(str).str.strip().replace("", "Unknown")
    group_cols = ["Sector", "Sub_Sector"] if "Sector" in out.columns else ["Sub_Sector"]
    groups = out.groupby(group_cols, dropna=False)
    out["subsector_stock_count"] = groups["Symbol"].transform("nunique")
    avg_1w = groups["one_week_performance"].transform("mean") if "one_week_performance" in out else 0
    avg_1m = groups["one_month_performance"].transform("mean") if "one_month_performance" in out else 0
    avg_3m = groups["three_month_performance"].transform("mean") if "three_month_performance" in out else 0
    out["subsector_hot_score"] = (
        pd.Series(avg_1m, index=out.index).fillna(0) * 0.45
        + pd.Series(avg_3m, index=out.index).fillna(0) * 0.35
        + pd.Series(avg_1w, index=out.index).fillna(0) * 0.20
    ).round(2)
    out["subsector_temperature"] = np.select(
        [
            out["subsector_stock_count"].ge(2) & out["subsector_hot_score"].ge(5),
            out["subsector_stock_count"].ge(2) & out["subsector_hot_score"].le(-3),
        ],
        ["Hot", "Cold"],
        default="Neutral",
    )
    sector_hot = out.get("sector_temperature", pd.Series("Unknown", index=out.index)).astype(str).str.upper().eq("HOT")
    subsector_hot = out["subsector_temperature"].astype(str).str.upper().eq("HOT")
    out["hot_industry_context"] = sector_hot | subsector_hot
    out["hot_industry_reason"] = np.select(
        [sector_hot & subsector_hot, sector_hot, subsector_hot],
        ["Hot sector and sub-sector", "Hot sector", "Hot sub-sector"],
        default="No hot industry confirmation",
    )
    return out


def add_expert_analysis_fields(dfagg):
    """Create transparent value, management-outcome and technical review fields."""
    out = _add_subsector_heat(dfagg.copy())
    cap_mil = _numeric(out, "capMil")
    market_cap = _numeric(out, "Marketcap")
    free_cash_flow = _numeric(out, "freeCashFlow")
    roe = _numeric(out, "returnOnEquity")
    revenue_growth = _numeric(out, "revenueGrowth")
    price_to_book = _numeric(out, "priceToBook")
    debt_to_equity_raw = _numeric(out, "debtToEquity")
    five_year_cagr = _numeric(out, "five_year_cagr_pct")
    price = _numeric(out, "last_close")
    rsi = _numeric(out, "RSI")

    out["market_cap_gate_2b"] = cap_mil.ge(2000)
    out["free_cash_flow_yield_pct"] = np.where(
        market_cap.gt(0), free_cash_flow / market_cap * 100, np.nan
    )
    out["debt_to_equity_pct"] = np.where(
        debt_to_equity_raw.le(10), debt_to_equity_raw * 100, debt_to_equity_raw
    )
    debt_pct = pd.Series(out["debt_to_equity_pct"], index=out.index)
    fcf_yield = pd.Series(out["free_cash_flow_yield_pct"], index=out.index)
    out["value_investing_score"] = pd.DataFrame(
        {
            "positive_fcf": free_cash_flow.gt(0).astype(int) * 20,
            "strong_roe": roe.ge(0.15).astype(int) * 20,
            "revenue_growth": revenue_growth.ge(0.05).astype(int) * 15,
            "low_debt": debt_pct.le(50).astype(int) * 15,
            "fcf_yield": fcf_yield.ge(4).astype(int) * 20,
            "reasonable_book_value": (price_to_book.gt(0) & price_to_book.le(5)).astype(int) * 10,
        }
    ).sum(axis=1)
    out["value_investing_rating"] = np.select(
        [out["value_investing_score"].ge(70), out["value_investing_score"].ge(50)],
        ["Attractive", "Review"],
        default="Weak/Incomplete",
    )
    out["strong_fundamentals"] = (
        out["market_cap_gate_2b"]
        & out["value_investing_score"].ge(70)
        & free_cash_flow.gt(0)
        & roe.ge(0.10)
    )
    out["management_quality_score"] = (
        roe.ge(0.15).astype(int) * 30
        + free_cash_flow.gt(0).astype(int) * 25
        + debt_pct.le(50).astype(int) * 20
        + five_year_cagr.ge(8).astype(int) * 25
    )
    out["management_quality_rating"] = np.select(
        [
            five_year_cagr.isna(),
            out["management_quality_score"].ge(75),
            out["management_quality_score"].ge(50),
        ],
        ["Needs 5Y Data", "Strong Outcome Proxy", "Mixed Outcome Proxy"],
        default="Weak Outcome Proxy",
    )
    out["management_rating_basis"] = "ROE, free cash flow, debt and 5Y stock CAGR; CEO tenure not sourced"
    value_range = _numeric(out, "value_range_score").fillna(0)
    out["valuation_quality_score"] = (
        out["value_investing_score"] * 0.60
        + value_range * 0.25
        + fcf_yield.clip(0, 10).fillna(0) * 10 * 0.15
    ).round(2)

    for period in ["1m", "6m", "covid"]:
        out[f"support_avg_{period}_score"] = _support_score(price, _numeric(out, f"support_avg_{period}"))
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
    avg_support_score = out[["support_avg_1m_score", "support_avg_6m_score", "support_avg_covid_score"]].max(axis=1)
    out["technical_analysis_score"] = (
        avg_support_score * 0.35
        + basing.astype(int) * 25
        + rsi.between(25, 50, inclusive="both").astype(int) * 20
        + _numeric(out, "one_month_performance").lt(0).astype(int) * 10
        + out["hot_industry_context"].astype(int) * 10
    ).round(2)
    out["technical_analysis_rating"] = np.select(
        [out["technical_analysis_score"].ge(70), out["technical_analysis_score"].ge(50)],
        ["Strong Setup", "Watch Setup"],
        default="Weak Setup",
    )
    out["expert_research_score"] = (
        out["valuation_quality_score"] * 0.60
        + out["technical_analysis_score"] * 0.40
    ).round(2)
    out["expert_analysis_view"] = np.select(
        [
            out["strong_fundamentals"] & out["technical_analysis_score"].ge(70) & out["hot_industry_context"],
            out["strong_fundamentals"] & out["technical_analysis_score"].ge(50),
            out["strong_fundamentals"],
        ],
        [
            "Value-qualified setup with hot industry confirmation",
            "Value-qualified; technical watchlist setup",
            "Value-qualified; wait for stronger technical entry",
        ],
        default="Does not meet value-quality hurdle",
    )
    return out


def make_ranked_views(dfagg, min_market_cap=2000):
    enriched = add_expert_analysis_fields(dfagg)
    views = _original_make_ranked_views(enriched, min_market_cap=min_market_cap)
    eligible = enriched[
        enriched["market_cap_gate_2b"]
        & enriched.get("price_status", pd.Series("OK", index=enriched.index)).eq("OK")
    ].copy()
    quality = eligible[eligible["strong_fundamentals"]].copy()
    hot_quality = quality[quality["hot_industry_context"]].copy()

    def top(df, column, ascending=False):
        if df.empty or column not in df.columns:
            return df.head(100)
        return df.sort_values(column, ascending=ascending, na_position="last").head(100)

    views["Value Technical Picks"] = top(quality, "expert_research_score")
    views["Largest Move Win %"] = top(quality, "win%")
    views["Hot Quality 2W Declines"] = top(
        hot_quality[_numeric(hot_quality, "two_week_performance").lt(0)],
        "two_week_performance",
        ascending=True,
    )
    views["Hot Quality 1M Declines"] = top(
        hot_quality[_numeric(hot_quality, "one_month_performance").lt(0)],
        "one_month_performance",
        ascending=True,
    )
    views["Basing Near Support"] = top(
        quality[
            quality.get("basing_5d_10pct", pd.Series(False, index=quality.index)).fillna(False)
            & quality["near_support_10pct"]
        ],
        "expert_research_score",
    )
    views["Support Analysis"] = top(quality, "technical_analysis_score")
    return views


def get_column_dictionary(columns):
    dictionary = _original_get_column_dictionary(columns)
    details = {
        "value_investing_score": ("Fundamental", "Value-investing quality score.", "FCF, ROE, growth, leverage, FCF yield and P/B tests.", "70+ meets the value-quality hurdle."),
        "value_investing_rating": ("Fundamental", "Value investing verdict.", "Rating from value_investing_score.", "Attractive names enter value-qualified screens."),
        "five_year_cagr_pct": ("Management Outcome", "Approximate five-year annualized shareholder return.", "Annualized close-price return across 1260 trading sessions.", "One management outcome proxy; not proof of management quality."),
        "management_quality_rating": ("Management Outcome", "Simple quality/outcome rating.", "ROE, FCF, leverage and 5Y CAGR.", "CEO tenure requires an additional sourced data feed."),
        "support_avg_1m": ("Technical", "One-month average low reference.", "Mean daily low across 21 trading sessions.", "Reference for shorter-term support."),
        "support_avg_6m": ("Technical", "Six-month average low reference.", "Mean daily low across 126 trading sessions.", "Reference for intermediate support."),
        "support_avg_covid": ("Technical", "Post-Covid-history average low reference.", "Mean daily low since loaded history begins, normally March 2020.", "Long-history support context."),
        "support_avg_1m_score": ("Technical", "One-month support proximity score.", "100 at average support, decreases with distance.", "Higher means price is nearer the reference."),
        "support_avg_6m_score": ("Technical", "Six-month support proximity score.", "100 at average support, decreases with distance.", "Higher means price is nearer the reference."),
        "support_avg_covid_score": ("Technical", "Long-history support proximity score.", "100 at average support, decreases with distance.", "Higher means price is nearer the reference."),
        "basing_5d_10pct": ("Technical", "One-week base flag.", "TRUE when five-session range is 10% or less.", "Possible stabilization."),
        "subsector_hot_score": ("Industry", "Sub-sector strength score.", "Weighted sub-sector 1W/1M/3M average returns.", "Hot label needs at least two observed peers."),
        "hot_industry_context": ("Industry", "Hot sector or sub-sector confirmation.", "TRUE when sector or qualified sub-sector is Hot.", "Required for hot decline sheets."),
        "technical_analysis_score": ("Technical", "Entry setup score.", "Support, basing, RSI, pullback and industry heat.", "Higher means stronger technical entry context."),
        "expert_analysis_view": ("Analysis", "Combined research assessment.", "Value hurdle plus technical and industry signals.", "Use as a review prompt, not investment advice."),
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
            else:
                category, measure, calculation, usage = values
                dictionary = pd.concat(
                    [
                        dictionary,
                        pd.DataFrame([{
                            "Column": column,
                            "Category": category,
                            "What It Measures": measure,
                            "How Calculated": calculation,
                            "How To Read / Use": usage,
                        }]),
                    ],
                    ignore_index=True,
                )
    return dictionary


def build_table_of_contents(views, csv_outputs):
    toc = _original_build_table_of_contents(views, csv_outputs)
    for sheet, guide in AGENT_VIEW_GUIDES.items():
        mask = toc["Name"].eq(sheet)
        if not mask.any():
            continue
        purpose, filters, measures, ranking, usage = guide
        toc.loc[mask, "Purpose / What It Answers"] = purpose
        toc.loc[mask, "Filter / Inclusion Rules"] = filters
        toc.loc[mask, "What It Measures"] = measures
        toc.loc[mask, "Ranking / Sort Logic"] = ranking
        toc.loc[mask, "How To Use It"] = usage
        toc.loc[mask, "Key Columns to Review"] = (
            "value_investing_score, value_investing_rating, technical_analysis_score, "
            "technical_analysis_rating, expert_analysis_view, hot_industry_context, "
            "support_avg_1m_score, support_avg_6m_score, support_avg_covid_score, basing_5d_10pct"
        )
    return toc


def finalize_slim_workbook_views(views, dfagg):
    """Retain new research views after slim selection."""
    final = _original_finalize_slim_workbook_views(views, dfagg)
    for sheet in AGENT_VIEW_NAMES:
        if sheet in views:
            final[sheet] = views[sheet]
    return final


def install_agent_views(target_scanner) -> None:
    global scanner, pd, np
    global _original_prepare_price_features, _original_latest_performance
    global _original_make_ranked_views, _original_get_column_dictionary
    global _original_finalize_slim_workbook_views
    global _original_build_table_of_contents
    scanner = target_scanner
    pd = scanner.pd
    np = scanner.np
    _original_prepare_price_features = scanner.prepare_price_features
    _original_latest_performance = scanner.latest_performance
    _original_make_ranked_views = scanner.make_ranked_views
    _original_get_column_dictionary = scanner.get_column_dictionary
    _original_finalize_slim_workbook_views = scanner.finalize_slim_workbook_views
    _original_build_table_of_contents = scanner.build_table_of_contents
    scanner.prepare_price_features = prepare_price_features
    scanner.latest_performance = latest_performance
    scanner.make_ranked_views = make_ranked_views
    scanner.get_column_dictionary = get_column_dictionary
    scanner.finalize_slim_workbook_views = finalize_slim_workbook_views
    scanner.build_table_of_contents = build_table_of_contents
    expert_columns = [
        "Symbol", "Security", "Index", "Sector", "Sub_Sector", "price_status", "Marketcap", "capMil",
        "last_close", "two_week_close", "two_week_performance", "one_month_performance",
        "six_month_performance", "five_year_cagr_pct", "win%", "win%_covid",
        "freeCashFlow", "free_cash_flow_yield_pct", "returnOnEquity", "revenueGrowth",
        "debtToEquity", "debt_to_equity_pct", "priceToBook", "value_investing_score",
        "value_investing_rating", "management_quality_score", "management_quality_rating",
        "management_rating_basis", "valuation_quality_score", "technical_analysis_score",
        "technical_analysis_rating", "expert_research_score", "expert_analysis_view",
        "sector_temperature", "sector_hot_score", "subsector_temperature", "subsector_hot_score",
        "hot_industry_context", "hot_industry_reason", "basing_5d_10pct", "basing_range_5d_pct",
        "Support1_5d", "support_1m", "support_avg_1m", "support_avg_1m_score",
        "support_6m", "support_avg_6m", "support_avg_6m_score",
        "minCovid_filled", "support_avg_covid", "support_avg_covid_score",
        "resistance_1m", "resistance_6m", "nearest_support_distance_pct", "near_support_10pct",
        "RSI", "watch_reason",
    ]
    for sheet in AGENT_VIEW_NAMES:
        scanner.SHEET_SPECIFIC_COLUMNS[sheet] = expert_columns
