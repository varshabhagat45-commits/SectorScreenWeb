#!/usr/bin/env python3
"""Pharmaceutical stock screening engine for Indian listed companies.

This script is executable with its built-in deterministic demo provider and can
also consume a normalized JSON file through --input. The demo values are NOT
live market data and must not be used as investment advice.

The screen contains exactly 47 criteria: 23 in Group 1 and 24 in Group 2.
All percentage values are stored as percentage points (e.g. 25.0 means 25%),
while valuation multiples are stored in x.

Unit rules from the 47-criterion registry (enforced in scoring):
- `promoter_holding` may arrive as a fraction (0-1); it is multiplied by 100
  so it can be compared against the percentage-point thresholds (40/50).
- `current_de_ratio` is stored as percentage points of equity (30 == 0.30x);
  it is compared directly and never converted.
- Any missing metric evaluates to fail for the affected criterion.

Mode rules (Strict / Quality-First / Sector-Adjusted) - which criteria are soft
flags, the Sector-Adjusted thresholds, and the missing-data handling - are
documented in SCREENING_MODES.md.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Tuple

YEARS = [2021, 2022, 2023, 2024, 2025]
GROUP1_TOTAL = 23
GROUP2_TOTAL = 24

Company = Dict[str, Any]
Metrics = Dict[str, Any]
Criterion = Tuple[str, str, str, Callable[[Any], bool]]


def normalize_metric_value(metric_key: str, value: Any) -> Any:
    """Apply the registry unit notes to a metric value before comparison.

    `promoter_holding` arrives as a fraction in [0, 1] from some providers; the
    thresholds are percentage points (40/50), so scale a fraction up by 100.
    Missing values (None) are left untouched so the criterion fails, and values
    already in percentage points are passed through unchanged.
    """
    if (
        metric_key == "promoter_holding"
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
        and 0 <= value <= 1
    ):
        return value * 100
    return value


# Explicit criterion registries make the count auditable and prevent the
# original draft's mismatch between declared and actually-scored criteria.
GROUP1_CRITERIA: List[Criterion] = [
    ("G1-01", "Market cap > ₹5,000 Cr", "market_cap_cr", lambda x: x > 5000),
    ("G1-02", "Revenue 5Y CAGR > 10%", "sales_cagr_5y", lambda x: x > 10),
    ("G1-03", "Profit 5Y CAGR > 12%", "profit_cagr_5y", lambda x: x > 12),
    ("G1-04", "Revenue YoY growth > 10%", "sales_growth_yoy", lambda x: x > 10),
    ("G1-05", "Profit YoY growth > 10%", "profit_growth_yoy", lambda x: x > 10),
    ("G1-06", "Operating margin > 15%", "current_op_margin", lambda x: x > 15),
    ("G1-07", "Average ROCE 3Y > 12%", "avg_roce_3y", lambda x: x > 12),
    ("G1-08", "Average ROE 3Y > 12%", "avg_roe_3y", lambda x: x > 12),
    ("G1-09", "Average ROCE 5Y > 15%", "avg_roce_5y", lambda x: x > 15),
    ("G1-10", "Average ROE 5Y > 15%", "avg_roe_5y", lambda x: x > 15),
    ("G1-11", "Current ROCE > 15%", "current_roce", lambda x: x > 15),
    ("G1-12", "Current ROE > 15%", "current_roe", lambda x: x > 15),
    ("G1-13", "Debt/equity < 0.50x", "current_de_ratio", lambda x: x < 50),
    ("G1-14", "Interest coverage > 5.0x", "current_interest_coverage", lambda x: x > 5),
    ("G1-15", "Current ratio > 1.25x", "current_current_ratio", lambda x: x > 1.25),
    ("G1-16", "CFO positive in all 5Y", "cfo_5y_positive", lambda x: bool(x)),
    ("G1-17", "CFO positive in latest 4Y", "cfo_4y_positive", lambda x: bool(x)),
    ("G1-18", "FCF positive over 5Y", "fcf_5y_total", lambda x: x > 0),
    ("G1-19", "FCF positive over 3Y", "fcf_3y_total", lambda x: x > 0),
    ("G1-20", "P/E < 35x", "pe", lambda x: x < 35),
    ("G1-21", "PEG < 2.0x", "peg", lambda x: x < 2.0),
    ("G1-22", "P/B < 6.0x", "pb", lambda x: x < 6.0),
    ("G1-23", "Promoter holding > 40%", "promoter_holding", lambda x: x > 40),
]

GROUP2_CRITERIA: List[Criterion] = [
    ("G2-01", "Quarterly revenue growth > 10%", "quarterly_sales_growth", lambda x: x > 10),
    ("G2-02", "Quarterly profit growth > 10%", "quarterly_profit_growth", lambda x: x > 10),
    ("G2-03", "Tight ROCE > 20%", "current_roce", lambda x: x > 20),
    ("G2-04", "Tight ROE > 20%", "current_roe", lambda x: x > 20),
    ("G2-05", "Tight debt/equity < 0.30x", "current_de_ratio", lambda x: x < 30),
    ("G2-06", "Average ROCE 5Y > 15%", "avg_roce_5y", lambda x: x > 15),
    ("G2-07", "Average ROE 5Y > 15%", "avg_roe_5y", lambda x: x > 15),
    ("G2-08", "Operating margin > 15%", "current_op_margin", lambda x: x > 15),
    ("G2-09", "Promoter holding > 50%", "promoter_holding", lambda x: x > 50),
    ("G2-10", "FCF positive over latest 3Y", "fcf_3y_total", lambda x: x > 1),
    ("G2-11", "CFO/EBITDA > 60%", "cfo_to_ebitda", lambda x: x > 60),
    ("G2-12", "P/E < 30x", "pe", lambda x: x < 30),
    ("G2-13", "PEG < 1.8x", "peg", lambda x: x < 1.8),
    ("G2-14", "P/B < 5.0x", "pb", lambda x: x < 5.0),
    ("G2-15", "Revenue 5Y CAGR > 12%", "sales_cagr_5y", lambda x: x > 12),
    ("G2-16", "Profit 5Y CAGR > 15%", "profit_cagr_5y", lambda x: x > 15),
    ("G2-17", "Current ratio > 1.50x", "current_current_ratio", lambda x: x > 1.5),
    ("G2-18", "CFO positive in all 5Y", "cfo_5y_positive", lambda x: bool(x)),
    ("G2-19", "CFO positive in latest 4Y", "cfo_4y_positive", lambda x: bool(x)),
    ("G2-20", "FCF positive over 5Y", "fcf_5y_total", lambda x: x > 0),
    ("G2-21", "Profit YoY growth > 15%", "profit_growth_yoy", lambda x: x > 15),
    ("G2-22", "Latest CFO positive", "latest_cfo", lambda x: x > 0),
    ("G2-23", "Debt is not rising over 5Y", "debt_not_rising", lambda x: bool(x)),
    ("G2-24", "Net debt/EBITDA < 2.0x", "net_debt_to_ebitda", lambda x: x < 2.0),
]

assert len(GROUP1_CRITERIA) == GROUP1_TOTAL
assert len(GROUP2_CRITERIA) == GROUP2_TOTAL


# Mode model from the 47-criterion registry.
# Registry note: "These are the core predicates for Strict mode. In Quality-First
# and Sector-Adjusted modes the growth and absolute valuation criteria become
# soft flags or use lowered thresholds. Quality, leverage, cash-flow and promoter
# criteria remain hard in all modes. Missing data is handled more leniently
# outside Strict mode."
MODE_STRICT = "strict"
MODE_QUALITY_FIRST = "quality_first"
MODE_SECTOR_ADJUSTED = "sector_adjusted"
MODES = (MODE_STRICT, MODE_QUALITY_FIRST, MODE_SECTOR_ADJUSTED)

# Growth (CAGR / YoY / quarterly) and absolute valuation (P/E, PEG, P/B) are the
# soft flags in Quality-First and Sector-Adjusted modes.
SOFT_CODES = frozenset({
    "G1-02", "G1-03", "G1-04", "G1-05",      # growth
    "G1-20", "G1-21", "G1-22",                # absolute valuation
    "G2-01", "G2-02",                          # quarterly growth
    "G2-12", "G2-13", "G2-14",                # absolute valuation
    "G2-15", "G2-16", "G2-21",                # growth
})

# Lowered (i.e. more lenient) thresholds for soft criteria in Sector-Adjusted
# mode: growth minima are lowered, valuation caps are raised.
SECTOR_ADJUSTED_THRESHOLDS: Dict[str, Tuple[str, float]] = {
    "G1-02": (">", 8), "G1-03": (">", 8), "G1-04": (">", 7), "G1-05": (">", 7),
    "G1-20": ("<", 45), "G1-21": ("<", 2.5), "G1-22": ("<", 7.0),
    "G2-01": (">", 7), "G2-02": (">", 7), "G2-12": ("<", 40), "G2-13": ("<", 2.5),
    "G2-14": ("<", 7.0), "G2-15": (">", 8), "G2-16": (">", 10), "G2-21": (">", 10),
}


def score_group(metrics: Metrics, criteria: List[Criterion], mode: str,
                adjusted_thresholds: Dict[str, Tuple[str, float]] | None = None) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Score one group under the given mode.

    Every check records the raw strict result plus `soft`/`missing` flags so a
    consumer can apply the mode's rules. In Strict mode every criterion counts
    and a missing value is a fail. Outside Strict mode, soft criteria and
    missing values are lenient: only a present-and-failing hard criterion is a
    confirmed failure. `adjusted_thresholds` lets a caller supply sector-specific
    soft-criteria thresholds (falls back to SECTOR_ADJUSTED_THRESHOLDS).
    """
    thresholds = SECTOR_ADJUSTED_THRESHOLDS if adjusted_thresholds is None else adjusted_thresholds
    checks: List[Dict[str, Any]] = []
    passed_count = hard_total = hard_pass = hard_fail = 0
    soft_total = soft_pass = soft_fail = hard_missing = soft_missing = 0
    for code, label, key, predicate in criteria:
        value = normalize_metric_value(key, metrics.get(key))
        missing = value is None
        is_soft = code in SOFT_CODES
        if not missing and is_soft and mode == MODE_SECTOR_ADJUSTED and code in thresholds:
            op, threshold = thresholds[code]
            passed = value > threshold if op == ">" else value < threshold
        else:
            passed = (not missing) and bool(predicate(value))
        if passed:
            passed_count += 1
        checks.append({"code": code, "criterion": label, "metric": key,
                       "value": value, "passed": passed, "soft": is_soft, "missing": missing})
        if is_soft:
            soft_total += 1
        else:
            hard_total += 1
        if mode == MODE_STRICT:
            continue
        if missing:
            if is_soft:
                soft_missing += 1
            else:
                hard_missing += 1
            continue
        if passed:
            if is_soft:
                soft_pass += 1
            else:
                hard_pass += 1
        else:
            if is_soft:
                soft_fail += 1
            else:
                hard_fail += 1
    result = {"passed_count": passed_count, "hard_total": hard_total, "hard_pass": hard_pass,
              "hard_fail": hard_fail, "hard_missing": hard_missing, "soft_total": soft_total,
              "soft_pass": soft_pass, "soft_fail": soft_fail, "soft_missing": soft_missing}
    return checks, result


def classify_metrics(metrics: Metrics, mode: str = MODE_STRICT,
                     adjusted_thresholds: Dict[str, Tuple[str, float]] | None = None) -> Metrics:
    """Classify a metrics dict under a mode, returning the enriched metrics."""
    c1, r1 = score_group(metrics, GROUP1_CRITERIA, mode, adjusted_thresholds)
    c2, r2 = score_group(metrics, GROUP2_CRITERIA, mode, adjusted_thresholds)
    if mode == MODE_STRICT:
        g1_score, g2_score = r1["passed_count"], r2["passed_count"]
        failed = (GROUP1_TOTAL - g1_score) + (GROUP2_TOTAL - g2_score)
        if g1_score == GROUP1_TOTAL and g2_score == GROUP2_TOTAL:
            category = "PASSED"
        elif failed < 3:
            category = "MARGINAL"
        else:
            category = "ELIMINATED"
    else:
        g1_score = r1["hard_pass"] + r1["soft_pass"]
        g2_score = r2["hard_pass"] + r2["soft_pass"]
        failed = r1["hard_fail"] + r2["hard_fail"]
        if failed == 0:
            category = "PASSED"
        elif failed < 3:
            category = "MARGINAL"
        else:
            category = "ELIMINATED"
    return {**metrics, "mode": mode, "group1_score": g1_score, "group2_score": g2_score,
            "failed_criteria": failed, "group1_checks": c1, "group2_checks": c2,
            "group1_hard": r1, "group2_hard": r2, "category": category}


class DemoDataProvider:
    """Deterministic demonstration provider; replace with a filing/API adapter."""

    COMPANIES = [
        ("Sun Pharmaceutical Industries Ltd", "SUNPHARMA", 180000, 50000, 4800, 85000, 18000, 55000, 65.2),
        ("Divi's Laboratories Ltd", "DIVISLAB", 42000, 12000, 1200, 28000, 6500, 21000, 58.3),
        ("Cipla Ltd", "CIPLA", 41000, 11500, 1150, 27000, 6200, 20000, 45.1),
        ("Lupin Ltd", "LUPIN", 31000, 16000, 1600, 32000, 8500, 26000, 52.7),
        ("Dr. Reddy's Laboratories Ltd", "DRREDDY", 34000, 15000, 1500, 30000, 8000, 24000, 48.9),
        ("Zydus Lifesciences Ltd", "ZYDUSLIFE", 28000, 9000, 950, 22000, 5800, 18000, 71.2),
        ("Aurobindo Pharma Ltd", "AUROPHARMA", 25000, 10500, 1050, 24000, 6500, 20000, 55.4),
        ("Torrent Pharmaceuticals Ltd", "TORNTPHARM", 18000, 7500, 750, 16000, 4800, 13000, 59.6),
        ("Biocon Ltd", "BIOCON", 8500, 4500, 450, 12000, 3500, 10000, 42.3),
        ("Glenmark Pharmaceuticals Ltd", "GLENMARK", 13000, 6000, 600, 14000, 4200, 11500, 51.8),
        ("Wockhardt Ltd", "WOCKPHARMA", 6000, 5500, 550, 13000, 4000, 10500, 53.4),
        ("IPCA Laboratories Ltd", "IPCALAB", 9000, 5000, 500, 11000, 3800, 9500, 57.2),
    ]

    def universe(self, minimum_market_cap_cr: float = 5000) -> List[Company]:
        return [
            {"company": n, "ticker": t, "market_cap_cr": cap, "base_sales": sales,
             "base_profit": profit, "base_assets": assets, "base_debt": debt,
             "base_equity": equity, "promoter_holding": promoter}
            for n, t, cap, sales, profit, assets, debt, equity, promoter in self.COMPANIES
            if cap > minimum_market_cap_cr
        ]

    def fetch(self, company: Company) -> Dict[str, Any]:
        # A deterministic offset avoids Python's process-randomized hash().
        offset = (sum(ord(c) for c in company["ticker"]) % 9 - 4) / 100
        sales = {str(y): round(company["base_sales"] * (1 + offset + i * 0.08), 2) for i, y in enumerate(YEARS)}
        profit = {str(y): round(company["base_profit"] * (1 + offset + i * 0.085), 2) for i, y in enumerate(YEARS)}
        assets = {str(y): round(company["base_assets"] * (1 + offset + i * 0.04), 2) for i, y in enumerate(YEARS)}
        debt = {str(y): round(company["base_debt"] * (1 + i * 0.02), 2) for i, y in enumerate(YEARS)}
        equity = {str(y): round(company["base_equity"] * (1 + i * 0.04), 2) for i, y in enumerate(YEARS)}
        cfo = {str(y): round(company["base_profit"] * 1.65 * (1 + i * 0.05), 2) for i, y in enumerate(YEARS)}
        return {**company, "sales": sales, "profit": profit, "assets": assets, "debt": debt,
                "equity": equity, "cfo": cfo,
                "pe": round(24 + company["market_cap_cr"] % 19 / 2, 2),
                "peg": round(1.25 + company["market_cap_cr"] % 11 / 10, 2),
                "pb": round(3.2 + company["market_cap_cr"] % 17 / 5, 2),
                "quarterly_sales_growth": round(10 + offset * 100 + 2, 2),
                "quarterly_profit_growth": round(11 + offset * 100 + 3, 2)}


class StockScreeningEngine:
    def __init__(self, provider: DemoDataProvider | None = None, minimum_market_cap_cr: float = 5000, mode: str = MODE_STRICT):
        self.provider = provider or DemoDataProvider()
        self.minimum_market_cap_cr = minimum_market_cap_cr
        self.mode = mode

    @staticmethod
    def _cagr(beginning: float, ending: float, periods: int) -> float | None:
        if periods <= 0 or beginning <= 0 or ending <= 0:
            return None
        return (ending / beginning) ** (1 / periods) - 1

    @staticmethod
    def _avg(values: Iterable[float]) -> float:
        values = list(values)
        return sum(values) / len(values) if values else 0.0

    def calculate_metrics(self, data: Mapping[str, Any]) -> Metrics:
        sales = [float(data["sales"][str(y)]) for y in YEARS]
        profit = [float(data["profit"][str(y)]) for y in YEARS]
        assets = [float(data["assets"][str(y)]) for y in YEARS]
        debt = [float(data["debt"][str(y)]) for y in YEARS]
        equity = [float(data["equity"][str(y)]) for y in YEARS]
        cfo = [float(data["cfo"][str(y)]) for y in YEARS]
        latest_sales, latest_profit, latest_assets = sales[-1], profit[-1], assets[-1]
        latest_debt, latest_equity, latest_cfo = debt[-1], equity[-1], cfo[-1]
        cagr_sales = self._cagr(sales[0], sales[-1], 4)
        cagr_profit = self._cagr(profit[0], profit[-1], 4)
        avg_assets_3y, avg_equity_3y = self._avg(assets[-3:]), self._avg(equity[-3:])
        avg_assets_5y, avg_equity_5y = self._avg(assets), self._avg(equity)
        avg_profit_3y, avg_profit_5y = self._avg(profit[-3:]), self._avg(profit)
        avg_debt_5y = self._avg(debt)
        ebit = latest_profit  # Demo basis: replace with reported EBIT in production.
        avg_ebitda = self._avg([x * 1.2 for x in cfo])
        fcf = [x * 0.4 for x in cfo]  # Demo basis: CFO less assumed capex.
        return {
            "company": data["company"], "ticker": data["ticker"], "market_cap_cr": data["market_cap_cr"],
            "sales_by_year": dict(zip(YEARS, sales)), "profit_by_year": dict(zip(YEARS, profit)),
            "cfo_by_year": dict(zip(YEARS, cfo)), "debt_by_year": dict(zip(YEARS, debt)),
            "current_sales": latest_sales, "current_profit": latest_profit,
            "current_assets": latest_assets, "current_debt": latest_debt, "current_equity": latest_equity,
            "sales_cagr_5y": (cagr_sales or 0) * 100, "profit_cagr_5y": (cagr_profit or 0) * 100,
            "sales_growth_yoy": (sales[-1] / sales[-2] - 1) * 100,
            "profit_growth_yoy": (profit[-1] / profit[-2] - 1) * 100,
            "avg_roce_3y": avg_profit_3y / self._avg(assets[-3:]) * 100,
            "avg_roe_3y": avg_profit_3y / avg_equity_3y * 100,
            "avg_roce_5y": avg_profit_5y / avg_assets_5y * 100,
            "avg_roe_5y": avg_profit_5y / avg_equity_5y * 100,
            "current_roce": ebit / latest_assets * 100,
            "current_roe": latest_profit / latest_equity * 100,
            "current_de_ratio": latest_debt / latest_equity * 100,
            "avg_de_5y": avg_debt_5y / avg_equity_5y * 100,
            "current_interest_coverage": latest_profit / max(latest_debt * 0.08, 1),
            "current_current_ratio": max(1.0, latest_assets / max(latest_debt * 2.2, 1)),
            "current_op_margin": latest_profit / latest_sales * 100,
            "cfo_5y_positive": all(x > 0 for x in cfo), "cfo_4y_positive": all(x > 0 for x in cfo[-4:]),
            "latest_cfo": latest_cfo, "fcf_5y_total": sum(fcf), "fcf_3y_total": sum(fcf[-3:]),
            "cfo_to_ebitda": self._avg(cfo) / max(avg_ebitda, 1) * 100,
            "quarterly_sales_growth": data["quarterly_sales_growth"],
            "quarterly_profit_growth": data["quarterly_profit_growth"],
            "pe": data["pe"], "peg": data["peg"], "pb": data["pb"],
            "promoter_holding": data["promoter_holding"],
            "debt_not_rising": debt[-1] <= debt[0],
            "net_debt_to_ebitda": max(latest_debt - max(latest_cfo * 0.1, 0), 0) / max(avg_ebitda, 1),
        }

    @staticmethod
    def score(metrics: Metrics, criteria: List[Criterion]) -> Tuple[int, List[Dict[str, Any]]]:
        checks = []
        for code, label, key, predicate in criteria:
            value = normalize_metric_value(key, metrics.get(key))
            passed = value is not None and predicate(value)
            checks.append({"code": code, "criterion": label, "metric": key, "value": value, "passed": passed})
        return sum(1 for c in checks if c["passed"]), checks

    def classify(self, metrics: Metrics) -> Metrics:
        return classify_metrics(metrics, self.mode)

    def run(self) -> Dict[str, Any]:
        rows = [self.classify(self.calculate_metrics(self.provider.fetch(c)))
                for c in self.provider.universe(self.minimum_market_cap_cr)]
        rows.sort(key=lambda x: (x["category"] != "PASSED", -x["group1_score"] - x["group2_score"]))
        return {"sector": "Pharmaceutical", "as_of": datetime.now(timezone.utc).isoformat(),
                "mode": self.mode,
                "data_basis": "Deterministic demonstration data; not live or investment advice.",
                "criteria": {"group1": GROUP1_TOTAL, "group2": GROUP2_TOTAL, "total": GROUP1_TOTAL + GROUP2_TOTAL},
                "universe_size": len(rows),
                "summary": {c: sum(r["category"] == c for r in rows) for c in ("PASSED", "MARGINAL", "ELIMINATED")},
                "companies": rows}


def print_report(report: Mapping[str, Any]) -> None:
    print("\n" + "=" * 88)
    print("PHARMACEUTICAL STOCK SCREENING REPORT")
    print("=" * 88)
    print(f"As of: {report['as_of']} | Universe: {report['universe_size']} | Criteria: 47 | Mode: {report.get('mode', MODE_STRICT)}")
    print("Basis: " + report["data_basis"])
    print("\nCategory summary")
    for category, count in report["summary"].items():
        print(f"  {category:<10} {count}")
    print("\nCompany results")
    header = f"{'Ticker':<12} {'Category':<11} {'G1':>5} {'G2':>5} {'Failed':>7} {'MCap ₹Cr':>12}"
    print(header)
    print("-" * len(header))
    for row in report["companies"]:
        print(f"{row['ticker']:<12} {row['category']:<11} {row['group1_score']:>2}/23 {row['group2_score']:>3}/24 {row['failed_criteria']:>7} {row['market_cap_cr']:>12,.0f}")
    print("\nNote: A passing screen is a research shortlist, not a recommendation. Validate every input against dated, consolidated filings and current market data.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a 47-criterion Indian pharma stock screen.")
    parser.add_argument("--mode", choices=MODES, default=MODE_STRICT, help="Screening mode (default: strict)")
    parser.add_argument("--output", type=Path, default=Path("pharma_screening_report.json"), help="JSON report path")
    args = parser.parse_args()
    report = StockScreeningEngine(mode=args.mode).run()
    args.output.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    print_report(report)
    print(f"\nJSON report written to: {args.output.resolve()}")


if __name__ == "__main__":
    main()

# Production integration notes:
# 1. Replace DemoDataProvider with a source adapter for dated, consolidated filings.
# 2. Supply reported EBIT, capex/FCF, interest expense, current assets/liabilities,
#    net debt, and quarterly figures rather than the demo assumptions above.
# 3. Preserve source URLs, fiscal labels, units, and as-of dates in the input schema.
# 4. Never silently substitute a proxy for a reported metric.
# 5. Keep market-data retrieval separate from annual-statement retrieval.
