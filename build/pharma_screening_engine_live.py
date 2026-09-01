#!/usr/bin/env python3
"""Live Indian-pharma stock screener backed by Yahoo Finance via yfinance.

Yahoo Finance is used here as a convenient public market-data source. It is
not an official filing database, may rate-limit requests, and can omit fields.
Missing values are preserved as None and cause the affected criterion to fail;
no proxy values are invented. Verify decision-critical figures against dated,
consolidated company filings before relying on the output.

Install: python3 -m pip install yfinance
Run:     python3 pharma_screening_engine_live.py --output live_report.json
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Tuple

import pandas as pd
import yfinance as yf

from pharma_screening_engine import (
    GROUP1_CRITERIA,
    GROUP2_CRITERIA,
    GROUP1_TOTAL,
    GROUP2_TOTAL,
    MODES,
    MODE_STRICT,
    normalize_metric_value,
    classify_metrics,
)

from screener_provider import ScreenerProvider
from cache import DiskCache, cached_fetch

DEFAULT_TICKERS = [
    "SUNPHARMA.NS", "DIVISLAB.NS", "CIPLA.NS", "LUPIN.NS", "DRREDDY.NS",
    "ZYDUSLIFE.NS", "AUROPHARMA.NS", "TORNTPHARM.NS", "BIOCON.NS",
    "GLENMARK.NS", "WOCKPHARMA.NS", "IPCALAB.NS",
]
YEARS_REQUIRED = 5


def clean_number(value: Any) -> float | None:
    try:
        number = float(value)
        return number if pd.notna(number) and number not in (float("inf"), float("-inf")) else None
    except (TypeError, ValueError):
        return None


def row_values(frame: pd.DataFrame, names: List[str], periods: int = YEARS_REQUIRED) -> List[float | None]:
    if frame is None or frame.empty:
        return []
    index_map = {str(index).lower().replace(" ", ""): index for index in frame.index}
    row = None
    for name in names:
        key = name.lower().replace(" ", "")
        if key in index_map:
            row = frame.loc[index_map[key]]
            break
    if row is None:
        return []
    cols = sorted(list(row.index), key=lambda x: str(x))[-periods:]
    return [clean_number(row.get(column)) for column in cols]


def latest(values: List[float | None]) -> float | None:
    valid = [v for v in values if v is not None]
    return valid[-1] if valid else None


def average(values: List[float | None]) -> float | None:
    valid = [v for v in values if v is not None]
    return sum(valid) / len(valid) if valid else None


def safe_ratio(numerator: float | None, denominator: float | None, scale: float = 1.0) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator * scale


def cagr(values: List[float | None], periods: int = 5, scale: float = 100.0) -> float | None:
    """CAGR (%) over the latest `periods` years (periods+1 points).

    Requires `periods + 1` values and positive endpoints; a negative or zero base
    makes CAGR not meaningful (metrics-and-fiscal-rules guardrail). Returns None
    on insufficient history so multi-year tests stay honestly lenient.
    """
    valid = [v for v in values if v is not None]
    if len(valid) < periods + 1 or valid[-1] <= 0 or valid[-(periods + 1)] <= 0:
        return None
    return ((valid[-1] / valid[-(periods + 1)]) ** (1 / periods) - 1) * scale


def info_number(info: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = clean_number(info.get(key))
        if value is not None:
            return value
    return None


def series_by_year(frame: pd.DataFrame, names: List[str], periods: int = YEARS_REQUIRED) -> Dict[int, float | None]:
    """Return {fiscal_year: value} for the latest `periods` years, ascending.

    Yahoo's balance sheet and income/cash-flow statements can carry different
    depths, so multi-statement ratios must align on fiscal-year labels rather
    than list position.
    """
    if frame is None or frame.empty:
        return {}
    index_map = {str(index).lower().replace(" ", ""): index for index in frame.index}
    row = None
    for name in names:
        key = name.lower().replace(" ", "")
        if key in index_map:
            row = frame.loc[index_map[key]]
            break
    if row is None:
        return {}
    out: Dict[int, float | None] = {}
    for col in row.index:
        year = getattr(col, "year", None)
        if year is None:
            head = str(col)[:4]
            year = int(head) if head.isdigit() else None
        if year is None:
            continue
        out[int(year)] = clean_number(row.get(col))
    return {y: out[y] for y in sorted(out)[-periods:]}


def latest_of(by_year: Dict[int, float | None]) -> float | None:
    years = [y for y in by_year if by_year[y] is not None]
    return by_year[max(years)] if years else None


def avg_ratio_series(num: Dict[int, float | None], den: Dict[int, float | None], periods: int, scale: float = 100.0) -> float | None:
    """Average of per-period ratios over the latest `periods` aligned, valid periods.

    Returns None when fewer than `periods` aligned periods are available so that a
    multi-year test is treated as insufficient data (missing) rather than measured
    on truncated history. Strict mode then fails it; lenient modes skip it.
    """
    years = [y for y in sorted(set(num) & set(den)) if num[y] is not None and den[y] not in (None, 0)]
    if len(years) < periods:
        return None
    years = years[-periods:]
    return sum(num[y] / den[y] * scale for y in years) / len(years)


def sum_series(by_year: Dict[int, float | None], periods: int | None = None) -> float | None:
    years = sorted(by_year)[-periods:] if periods else sorted(by_year)
    values = [by_year[y] for y in years if by_year[y] is not None]
    return sum(values) if values else None


def valid_year_count(by_year: Dict[int, float | None]) -> int:
    return sum(1 for v in by_year.values() if v is not None)


class YahooFinanceProvider:
    """Fetch and normalize Yahoo Finance data for one NSE-listed ticker."""

    def fetch(self, ticker_symbol: str) -> Dict[str, Any]:
        ticker = yf.Ticker(ticker_symbol)
        annual = ticker.get_income_stmt(freq="yearly")
        balance = ticker.get_balance_sheet(freq="yearly")
        cashflow = ticker.get_cash_flow(freq="yearly")
        quarterly = ticker.get_income_stmt(freq="quarterly")
        info = ticker.info or {}

        revenue = row_values(annual, ["TotalRevenue", "OperatingRevenue"])
        profit = row_values(annual, ["NetIncome", "NetIncomeCommonStockholders"])
        assets = row_values(balance, ["TotalAssets"])
        total_debt = row_values(balance, ["TotalDebt", "LongTermDebtAndCapitalLeaseObligation"])
        equity = row_values(balance, ["StockholdersEquity", "CommonStockEquity", "TotalEquityGrossMinorityInterest"])
        current_assets = latest(row_values(balance, ["CurrentAssets"], 1))
        current_liabilities = latest(row_values(balance, ["CurrentLiabilities"], 1))
        cash = latest(row_values(balance, ["CashCashEquivalentsAndShortTermInvestments", "CashAndCashEquivalents"], 1))
        cfo = row_values(cashflow, ["OperatingCashFlow", "TotalCashFromOperatingActivities"])
        capex = row_values(cashflow, ["CapitalExpenditure", "CapitalExpenditures"])
        interest = latest(row_values(annual, ["InterestExpenseNonOperating", "InterestExpense"] , 1))
        operating_income = latest(row_values(annual, ["OperatingIncome", "EBIT"] , 1))
        ebitda = latest(row_values(annual, ["EBITDA"] , 1))
        if ebitda is None and operating_income is not None:
            da = latest(row_values(cashflow, ["DepreciationAndAmortization"] , 1)) or 0
            ebitda = operating_income + da

        # Fiscal-period-aligned series for ratio metrics. Reports label these
        # EBIT / EBITDA / InvestedCapital / NetDebt / FreeCashFlow, and balance
        # and cash-flow statements can differ in depth, so we align by year.
        ebit_y = series_by_year(annual, ["OperatingIncome", "EBIT"])
        profit_y = series_by_year(annual, ["NetIncome", "NetIncomeCommonStockholders"])
        equity_y = series_by_year(balance, ["StockholdersEquity", "CommonStockEquity", "TotalEquityGrossMinorityInterest"])
        debt_y = series_by_year(balance, ["TotalDebt", "LongTermDebtAndCapitalLeaseObligation"])
        cash_y = series_by_year(balance, ["CashCashEquivalentsAndShortTermInvestments", "CashAndCashEquivalents"])
        net_debt_y = series_by_year(balance, ["NetDebt", "TotalDebtNetMinorityInterest"])
        for y in set(debt_y) | set(cash_y):
            if net_debt_y.get(y) is None and (debt_y.get(y) is not None or cash_y.get(y) is not None):
                net_debt_y[y] = max((debt_y.get(y) or 0) - (cash_y.get(y) or 0), 0)
        invested_capital_y = series_by_year(balance, ["InvestedCapital"])
        for y in set(equity_y):
            if invested_capital_y.get(y) is None and equity_y.get(y) is not None:
                invested_capital_y[y] = equity_y[y] + (net_debt_y.get(y) or 0)
        ebitda_y = series_by_year(annual, ["EBITDA"])
        da_y = series_by_year(cashflow, ["DepreciationAndAmortization"])
        for y in set(ebit_y):
            if ebitda_y.get(y) is None and ebit_y.get(y) is not None:
                ebitda_y[y] = ebit_y[y] + (da_y.get(y) or 0)
        cfo_y = series_by_year(cashflow, ["OperatingCashFlow", "TotalCashFromOperatingActivities"])
        capex_y = series_by_year(cashflow, ["CapitalExpenditure", "CapitalExpenditures"])
        fcf_y = series_by_year(cashflow, ["FreeCashFlow"])
        for y in set(cfo_y) | set(capex_y):
            if fcf_y.get(y) is None and cfo_y.get(y) is not None and capex_y.get(y) is not None:
                fcf_y[y] = cfo_y[y] + capex_y[y]

        # Yahoo's quarterly columns are usually date-labelled. Comparing the
        # last two available quarters is safer than fabricating a YoY value.
        q_revenue = row_values(quarterly, ["TotalRevenue", "OperatingRevenue"], 5)
        q_profit = row_values(quarterly, ["NetIncome", "NetIncomeCommonStockholders"], 5)
        quarterly_sales_growth = None
        quarterly_profit_growth = None
        if len(q_revenue) >= 5 and q_revenue[-1] is not None and q_revenue[-5] not in (None, 0):
            quarterly_sales_growth = (q_revenue[-1] / q_revenue[-5] - 1) * 100
        if len(q_profit) >= 5 and q_profit[-1] is not None and q_profit[-5] not in (None, 0):
            quarterly_profit_growth = (q_profit[-1] / q_profit[-5] - 1) * 100

        market_cap = info_number(info, "marketCap")
        market_cap_cr = market_cap / 10_000_000 if market_cap is not None else None
        return {
            "ticker": ticker_symbol, "company": info.get("longName") or info.get("shortName") or ticker_symbol,
            "market_cap_cr": market_cap_cr, "sales": revenue, "profit": profit, "assets": assets,
            "debt": total_debt, "equity": equity, "cfo": cfo, "capex": capex,
            "current_assets": current_assets, "current_liabilities": current_liabilities, "cash": cash,
            "interest": interest, "operating_income": operating_income, "ebitda": ebitda,
            "quarterly_sales_growth": quarterly_sales_growth, "quarterly_profit_growth": quarterly_profit_growth,
            "pe": info_number(info, "trailingPE"), "peg": info_number(info, "pegRatio"),
            "pb": info_number(info, "priceToBook"),
            # Yahoo quoteSummary often omits promoter holding for Indian stocks.
            "promoter_holding": info_number(info, "heldPercentInsiders"),
            "ebit_y": ebit_y, "profit_y": profit_y, "equity_y": equity_y,
            "invested_capital_y": invested_capital_y, "net_debt_y": net_debt_y,
            "ebitda_y": ebitda_y, "fcf_y": fcf_y, "cfo_y": cfo_y,
            "source": "Yahoo Finance via yfinance", "retrieved_at": datetime.now(timezone.utc).isoformat(),
        }


class LiveScreeningEngine:
    def __init__(self, provider: YahooFinanceProvider | None = None, mode: str = MODE_STRICT,
                 adjusted_thresholds: Dict[str, Tuple[str, float]] | None = None):
        self.provider = provider or YahooFinanceProvider()
        self.mode = mode
        self.adjusted_thresholds = adjusted_thresholds

    def calculate_metrics(self, data: Mapping[str, Any]) -> Dict[str, Any]:
        sales, profit, assets = data["sales"], data["profit"], data["assets"]
        debt, equity, cfo, capex = data["debt"], data["equity"], data["cfo"], data["capex"]
        latest_sales, latest_profit = latest(sales), latest(profit)
        latest_assets, latest_debt, latest_equity = latest(assets), latest(debt), latest(equity)
        latest_cfo = latest(cfo)
        avg_assets_5y, avg_equity_5y = average(assets), average(equity)
        avg_debt_5y = average(debt)
        sales_base = sales[-2] if len(sales) >= 2 else None
        profit_base = profit[-2] if len(profit) >= 2 else None
        metrics = {
            "company": data["company"], "ticker": data["ticker"], "market_cap_cr": data["market_cap_cr"],
            "sales_cagr_5y": cagr(sales), "profit_cagr_5y": cagr(profit),
            "sales_growth_yoy": safe_ratio((latest_sales - sales_base) if (latest_sales is not None and sales_base is not None) else None, sales_base, 100),
            "profit_growth_yoy": safe_ratio((latest_profit - profit_base) if (latest_profit is not None and profit_base is not None) else None, profit_base, 100),
            "avg_roce_3y": avg_ratio_series(data["ebit_y"], data["invested_capital_y"], 3),
            "avg_roe_3y": avg_ratio_series(data["profit_y"], data["equity_y"], 3),
            "avg_roce_5y": avg_ratio_series(data["ebit_y"], data["invested_capital_y"], 5),
            "avg_roe_5y": avg_ratio_series(data["profit_y"], data["equity_y"], 5),
            "current_roce": avg_ratio_series(data["ebit_y"], data["invested_capital_y"], 1),
            "current_roe": avg_ratio_series(data["profit_y"], data["equity_y"], 1),
            "current_de_ratio": safe_ratio(latest_debt, latest_equity, 100),
            "avg_de_5y": safe_ratio(avg_debt_5y, avg_equity_5y, 100),
            "current_interest_coverage": safe_ratio(data["operating_income"], data["interest"]),
            "current_current_ratio": safe_ratio(data["current_assets"], data["current_liabilities"]),
            "current_op_margin": safe_ratio(data["operating_income"], latest_sales, 100),
            "cfo_5y_positive": None if valid_year_count(data["cfo_y"]) < 5 else all(x is not None and x > 0 for x in cfo[-5:]),
            "cfo_4y_positive": None if valid_year_count(data["cfo_y"]) < 4 else all(x is not None and x > 0 for x in cfo[-4:]),
            "latest_cfo": latest_cfo,
            "fcf_5y_total": sum_series(data["fcf_y"]) if valid_year_count(data["fcf_y"]) >= 5 else None,
            "fcf_3y_total": sum_series(data["fcf_y"], 3) if valid_year_count(data["fcf_y"]) >= 3 else None,
            "cfo_to_ebitda": safe_ratio(average(cfo), latest_of(data["ebitda_y"]), 100),
            "quarterly_sales_growth": data["quarterly_sales_growth"], "quarterly_profit_growth": data["quarterly_profit_growth"],
            "pe": data["pe"], "peg": data["peg"], "pb": data["pb"], "promoter_holding": data["promoter_holding"],
            "debt_not_rising": (lambda v: None if len(v) < 2 else (v[-1] <= v[0]))([x for x in debt if x is not None]),
            "net_debt_to_ebitda": safe_ratio(max(latest_of(data["net_debt_y"]) or 0, 0), latest_of(data["ebitda_y"])),
            "data_quality": {"annual_revenue_points": len([x for x in sales if x is not None]), "annual_profit_points": len([x for x in profit if x is not None]), "annual_cfo_points": len([x for x in cfo if x is not None])},
            "source": data["source"], "retrieved_at": data["retrieved_at"],
        }
        return metrics

    @staticmethod
    def classify(metrics: Dict[str, Any], mode: str = MODE_STRICT,
                 adjusted_thresholds: Dict[str, Tuple[str, float]] | None = None) -> Dict[str, Any]:
        return classify_metrics(metrics, mode, adjusted_thresholds)

    def run(self, tickers: List[str], delay_seconds: float = 1.0, cache: DiskCache | None = None) -> Dict[str, Any]:
        rows, errors = [], []
        source = getattr(self.provider, "SOURCE_LABEL", "Yahoo Finance via yfinance")
        for symbol in tickers:
            try:
                print(f"Fetching {symbol} ...")
                data = cached_fetch(self.provider, symbol, cache, source)
                scored = self.classify(self.calculate_metrics(data), self.mode, self.adjusted_thresholds)
                for warning in data.get("warnings") or []:
                    print(f"    ! {symbol}: {warning}")
                rows.append(scored)
            except Exception as exc:
                errors.append({"ticker": symbol, "error": f"{type(exc).__name__}: {exc}"})
            time.sleep(max(delay_seconds, 0))
        rows.sort(key=lambda x: (-x["group1_score"] - x["group2_score"], x["ticker"]))
        return {"sector": "Pharmaceutical", "as_of": datetime.now(timezone.utc).isoformat(), "source": source, "mode": self.mode, "cache": bool(cache), "criteria": {"group1": 23, "group2": 24, "total": 47}, "universe_size": len(rows), "summary": {c: sum(r["category"] == c for r in rows) for c in ("PASSED", "MARGINAL", "ELIMINATED")}, "companies": rows, "errors": errors}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the 47-criterion live Indian pharma screen.")
    parser.add_argument("--tickers", nargs="+", default=DEFAULT_TICKERS, help="Yahoo symbols, e.g. SUNPHARMA.NS CIPLA.NS")
    parser.add_argument("--mode", choices=MODES, default=MODE_STRICT, help="Screening mode (default: strict)")
    parser.add_argument("--source", choices=("yahoo", "screener"), default="yahoo",
                        help="Fundamentals source: screener gives 10+ years; yahoo current valuation only")
    parser.add_argument("--cache-dir", type=Path, default=Path(__file__).resolve().parent / "cache",
                        help="Disk cache directory (default: <script>/cache)")
    parser.add_argument("--no-cache", action="store_true", help="Disable the disk cache")
    parser.add_argument("--ttl-hours", type=float, default=12.0, help="Cache TTL in hours (default 12)")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between ticker requests")
    parser.add_argument("--output", type=Path, default=Path("pharma_screening_live_report.json"))
    args = parser.parse_args()
    provider = ScreenerProvider() if args.source == "screener" else None
    cache = None if args.no_cache else DiskCache(args.cache_dir, args.ttl_hours)
    report = LiveScreeningEngine(provider=provider, mode=args.mode).run(args.tickers, args.delay, cache)
    args.output.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    print(f"Report written to {args.output.resolve()} ({len(report['companies'])} companies; {len(report['errors'])} errors)")


if __name__ == "__main__":
    main()
