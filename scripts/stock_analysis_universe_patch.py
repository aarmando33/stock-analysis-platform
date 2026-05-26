"""Broad listed-equity universe patch for the stock analysis scanner."""

from __future__ import annotations

from io import StringIO


def install_universe_patch(scanner) -> None:
    """Use official equity listings for full scans instead of a blocked Russell file."""
    pd = scanner.pd
    np = scanner.np
    original_build_universe = scanner.build_universe

    def load_sp500():
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        response = scanner.requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        response.raise_for_status()
        sp500 = pd.read_html(StringIO(response.text))[0]
        sp500 = sp500.rename(columns={"GICS Sector": "Sector", "GICS Sub-Industry": "Sub_Sector"})
        sp500["Symbol"] = sp500["Symbol"].map(scanner.normalize_symbol)
        sp500["Index"] = "S&P 500"
        return sp500[["Symbol", "Security", "Sector", "Sub_Sector", "Index"]].drop_duplicates("Symbol")

    def listed_equities(url: str, symbol_column: str, index_label):
        response = scanner.requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        response.raise_for_status()
        df = pd.read_csv(StringIO(response.text), sep="|")
        df = df[df[symbol_column].notna()].copy()
        df = df[~df[symbol_column].astype(str).str.contains("File Creation Time", na=False)]
        for column in ["Test Issue", "ETF"]:
            if column in df.columns:
                df = df[df[column].astype(str).str.upper().eq("N")]
        df["Symbol"] = df[symbol_column].map(scanner.normalize_symbol)
        df = df[df["Symbol"].str.match(r"^[A-Z]{1,5}(-[A-Z])?$", na=False)]
        df = df.rename(columns={"Security Name": "Security"})
        df["Index"] = df.apply(index_label, axis=1) if callable(index_label) else index_label
        df["Sector"] = np.nan
        df["Sub_Sector"] = np.nan
        return df[["Symbol", "Security", "Sector", "Sub_Sector", "Index"]].drop_duplicates("Symbol")

    def load_nasdaq():
        try:
            return listed_equities(
                "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
                "Symbol",
                "Nasdaq",
            )
        except Exception as exc:
            print(f"Warning: failed to load Nasdaq listed-equity feed: {exc}")
            return pd.DataFrame(columns=["Symbol", "Security", "Sector", "Sub_Sector", "Index"])

    def load_other_listed():
        labels = {
            "A": "NYSE American",
            "N": "NYSE",
            "P": "NYSE Arca",
            "V": "IEX",
            "Z": "Cboe",
        }

        def label(row):
            return labels.get(str(row.get("Exchange", "")).upper(), "Other Listed")

        try:
            return listed_equities(
                "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
                "ACT Symbol",
                label,
            )
        except Exception as exc:
            print(f"Warning: failed to load other exchange listed-equity feed: {exc}")
            return pd.DataFrame(columns=["Symbol", "Security", "Sector", "Sub_Sector", "Index"])

    def build_universe(universe):
        if universe != "all":
            return original_build_universe(universe)
        original_russell_loader = scanner.load_russell2000
        scanner.load_russell2000 = lambda: pd.DataFrame(
            columns=["Symbol", "Security", "Sector", "Sub_Sector", "Index"]
        )
        try:
            return original_build_universe(universe)
        finally:
            scanner.load_russell2000 = original_russell_loader

    scanner.INDEX_PRIORITY = [
        "S&P 500", "NYSE", "NYSE American", "NYSE Arca", "Cboe", "IEX",
        "Nasdaq", "Russell 2000", "Other Listed", "Extra",
    ]
    scanner.load_sp500 = load_sp500
    scanner.load_nasdaq = load_nasdaq
    scanner.load_nyse = load_other_listed
    scanner.build_universe = build_universe
