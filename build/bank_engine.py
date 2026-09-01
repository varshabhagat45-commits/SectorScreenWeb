#!/usr/bin/env python3
"""Bank-specific screening engine.

The 47 operational criteria (margins, current ratio, interest coverage,
cash-flow) do not fit banks/NBFCs, whose economics run on NIM, ROA, asset
quality and leverage. This module defines a bank-fashioned criterion registry
and a provider that extracts bank metrics from Screener.in (plus valuation from
Yahoo). Missing data (e.g. masked Gross NPA) is lenient outside Strict mode.

Run:  python bank_engine.py --mode quality_first --tickers HDFCBANK.NS SBIN.NS
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

import bs4
import requests
import yfinance as yf

from cache import DiskCache, cached_fetch
from screener_provider import (
    BASE_URL,
    HEADERS,
    _annual_tables,
    _cagr,
    _find_annual,
    _latest_non_none,
    _list_of,
    _num,
    _series,
    _year,
)
from pharma_screening_engine import MODES, MODE_STRICT, MODE_QUALITY_FIRST, MODE_SECTOR_ADJUSTED

BankCriterion = Tuple[str, str, str, Any, bool]  # code, label, key, predicate, soft
BANK_TOTAL = 11


def _avg(values: List[float | None]) -> float | None:
    valid = [v for v in values if v is not None]
    return sum(valid) / len(valid) if valid else None


def _row_series(soup: bs4.BeautifulSoup, anchor: str) -> Dict[int, float | None]:
    return _series(_find_annual(soup, anchor), anchor)


def _prefix_series(soup: bs4.BeautifulSoup, prefix: str) -> Dict[int, float | None]:
    """Last-per-year series for a row whose label starts with `prefix` (e.g. NPA)."""
    for table in _annual_tables(soup):
        years: List[int | None] = []
        for tr in table.find_all("tr"):
            th = tr.find_all("th")
            if th:
                years = [_year(c.get_text(strip=True)) for c in th[:0] + th]
                break
        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            if not cells or not cells[0].get_text(strip=True).startswith(prefix):
                continue
            values = [_num(c.get_text(strip=True)) for c in cells[1:]]
            return {y: v for y, v in zip(years[0:], values) if y is not None}
    return {}


# Bank registry: quality/leverage/asset-quality are hard; growth + valuation soft.
# Screener's bank 'Financing Margin %' (NIM) and 'Expenses+' do not map to standard
# NIM / cost-to-income, so the margin and efficiency bars are carried by ROA and a
# capital-cushion (equity/total assets) criterion instead.
BANK_CRITERIA: List[BankCriterion] = [
    ("B-01", "Return on Equity (latest) > 12%", "roe_current", lambda x: x > 12, False),
    ("B-02", "Average ROE 5Y > 12%", "roe_avg_5y", lambda x: x > 12, False),
    ("B-03", "Return on Assets > 0.8%", "roa_current", lambda x: x > 0.8, False),
    ("B-04", "Equity / total assets > 6%", "equity_to_assets", lambda x: x > 6.0, False),
    ("B-05", "Gross NPA < 3% (if reported)", "gross_npa", lambda x: x < 3.0, False),
    ("B-06", "Net profit 5Y CAGR > 10%", "profit_cagr_5y", lambda x: x > 10, True),
    ("B-07", "Revenue 5Y CAGR > 8%", "revenue_cagr_5y", lambda x: x > 8, True),
    ("B-08", "Profit YoY growth > 10%", "profit_growth_yoy", lambda x: x > 10, True),
    ("B-09", "Deposits 5Y CAGR > 8%", "deposits_cagr_5y", lambda x: x > 8, True),
    ("B-10", "P/E < 15x", "pe", lambda x: x < 15, True),
    ("B-11", "P/B < 3.0x", "pb", lambda x: x < 3.0, True),
]
assert len(BANK_CRITERIA) == BANK_TOTAL


def _valuation(ticker_symbol: str) -> Dict[str, float | None]:
    try:
        info = yf.Ticker(ticker_symbol).info or {}
    except Exception:
        return {"pe": None, "pb": None, "long_name": None}
    return {"pe": _num(info.get("trailingPE")), "pb": _num(info.get("priceToBook")),
            "long_name": info.get("longName") or info.get("shortName")}


class BankScreenerProvider:
    """Fetch and reduce a bank's Screener page + Yahoo valuation to bank metrics."""

    SOURCE_LABEL = "Screener.in (bank) + Yahoo Finance valuation"

    def fetch(self, ticker_symbol: str) -> Dict[str, Any]:
        slug = ticker_symbol.split(".")[0].upper()
        response = requests.get(BASE_URL.format(slug=slug), headers=HEADERS, timeout=20)
        response.raise_for_status()
        soup = bs4.BeautifulSoup(response.text, "html.parser")

        revenue_y = _row_series(soup, "Revenue+") or _row_series(soup, "Sales+")
        profit_y = _row_series(soup, "Net Profit+")
        roe_y = _row_series(soup, "ROE %")
        deposits_y = _row_series(soup, "Deposits")
        equity_cap_y = _row_series(soup, "Equity Capital")
        reserves_y = _row_series(soup, "Reserves")
        assets_y = _row_series(soup, "Total Assets")
        gross_npa_y = _prefix_series(soup, "Gross NPA ratio")

        if not any(v is not None for v in revenue_y.values()) and \
           not any(v is not None for v in profit_y.values()):
            raise ValueError(f"Bank financials unavailable/masked for slug '{slug}'")

        equity_y = {}
        for y in set(equity_cap_y) | set(reserves_y):
            cap, res = equity_cap_y.get(y), reserves_y.get(y)
            equity_y[y] = (cap + res) if cap is not None and res is not None else (cap if res is None else None)

        last_profit = _latest_non_none(_list_of(profit_y))
        last_assets = _latest_non_none(_list_of(assets_y))
        last_equity = _latest_non_none(_list_of(equity_y))
        profit_list = _list_of(profit_y)
        profit_base = profit_list[-2] if len(profit_list) >= 2 else None
        valuation = _valuation(ticker_symbol)

        metrics = {
            "ticker": ticker_symbol,
            "company": valuation.get("long_name") or f"Bank {slug}",
            "roe_current": _latest_non_none(_list_of(roe_y)),
            "roe_avg_5y": _avg(_list_of(roe_y)[-5:]),
            "roa_current": (last_profit / last_assets * 100) if (last_profit is not None and last_assets not in (None, 0)) else None,
            "equity_to_assets": (last_equity / last_assets * 100) if (last_equity is not None and last_assets not in (None, 0)) else None,
            "gross_npa": _latest_non_none(_list_of(gross_npa_y)),
            "profit_cagr_5y": _cagr(profit_y, 5),
            "revenue_cagr_5y": _cagr(revenue_y, 5),
            "deposits_cagr_5y": _cagr(deposits_y, 5),
            "profit_growth_yoy": ((last_profit - profit_base) / profit_base * 100)
                                if (last_profit is not None and profit_base not in (None, 0)) else None,
            "pe": valuation.get("pe"), "pb": valuation.get("pb"),
            "source": self.SOURCE_LABEL,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        }
        return metrics


def score(metrics: Mapping[str, Any], mode: str) -> Dict[str, Any]:
    checks = []
    hard_fail = soft_fail = missing = 0
    passed = 0
    for code, label, key, predicate, soft in BANK_CRITERIA:
        value = metrics.get(key)
        is_missing = value is None
        ok = (not is_missing) and bool(predicate(value))
        if ok:
            passed += 1
        checks.append({"code": code, "criterion": label, "metric": key,
                       "value": value, "passed": ok, "soft": soft, "missing": is_missing})
        if mode == MODE_STRICT:
            if not ok:
                hard_fail += 1
            continue
        if is_missing:
            missing += 1
        elif ok:
            continue
        elif soft:
            soft_fail += 1
        else:
            hard_fail += 1

    if mode == MODE_STRICT:
        failed = BANK_TOTAL - passed
        if failed == 0:
            category = "PASSED"
        elif failed < 3:
            category = "MARGINAL"
        else:
            category = "ELIMINATED"
    else:
        if hard_fail == 0:
            category = "PASSED"
        elif hard_fail < 3:
            category = "MARGINAL"
        else:
            category = "ELIMINATED"
    return {**metrics, "mode": mode, "group1_score": None, "group2_score": None,
            "group1_checks": checks, "group2_checks": [], "failed_criteria": hard_fail if mode != MODE_STRICT else failed,
            "checks": checks, "category": category}


class BankEngine:
    def __init__(self, provider: BankScreenerProvider | None = None, mode: str = MODE_STRICT):
        self.provider = provider or BankScreenerProvider()
        self.mode = mode

    def run(self, tickers: List[str], delay: float = 1.0, cache: DiskCache | None = None) -> Dict[str, Any]:
        rows, errors = [], []
        for symbol in tickers:
            try:
                print(f"Fetching {symbol} ...")
                data = cached_fetch(self.provider, symbol, cache, self.provider.SOURCE_LABEL)
                rows.append(score(data, self.mode))
            except Exception as exc:
                errors.append({"ticker": symbol, "error": f"{type(exc).__name__}: {exc}"})
            time.sleep(max(delay, 0))
        rows.sort(key=lambda x: (x["category"] != "PASSED", -len([c for c in x["checks"] if c["passed"]])))
        return {"sector": "Banks / NBFC", "as_of": datetime.now(timezone.utc).isoformat(),
                "registry": "bank_12", "source": self.provider.SOURCE_LABEL, "mode": self.mode,
                "criteria": {"group1": 0, "group2": 0, "total": BANK_TOTAL},
                "universe_size": len(rows),
                "summary": {c: sum(r["category"] == c for r in rows) for c in ("PASSED", "MARGINAL", "ELIMINATED")},
                "companies": rows, "errors": errors}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the bank-specific screen.")
    parser.add_argument("--tickers", nargs="+", default=["HDFCBANK.NS", "SBIN.NS", "ICICIBANK.NS", "AXISBANK.NS", "KOTAKBANK.NS"])
    parser.add_argument("--mode", choices=MODES, default=MODE_QUALITY_FIRST)
    parser.add_argument("--output", type=Path, default=Path("bank_report.json"))
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--cache-dir", type=Path, default=Path(__file__).resolve().parent / "cache")
    args = parser.parse_args()
    cache = DiskCache(args.cache_dir, 12.0)
    report = BankEngine(mode=args.mode).run(args.tickers, args.delay, cache)
    import json
    args.output.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    for c in report["companies"]:
        fails = [x for x in c["checks"] if (not x["soft"]) and (not x["missing"]) and (not x["passed"])]
        print(f"{c['ticker']:<14} {c['category']:<10} passed={sum(x['passed'] for x in c['checks'])}/{BANK_TOTAL} "
              f"hard_fail={c['failed_criteria'] if c['mode']!=MODE_STRICT else c['failed_criteria']}")
        for x in fails:
            print(f"    ! {x['code']} {x['criterion']}: {x['value']}")


if __name__ == "__main__":
    main()
