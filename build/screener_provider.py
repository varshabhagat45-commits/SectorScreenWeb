#!/usr/bin/env python3
"""Screener.in provider: 10+ years of consolidated Indian annual fundamentals.

Screener.in publishes long consolidated annual history - Sales, Net Profit,
Borrowings, Equity, Cash from Operating Activity, Free Cash Flow, reported
ROCE %, and promoter holding. It has no official API, so this provider parses
the public consolidated company page by table content rather than position
(gated feature tables shift the index). This is a research/back-test aid only.

Current valuation multiples (P/E, PEG, P/B) and market cap are filled from
Yahoo Finance because Screener does not expose PEG. Promoter holding is taken
from Screener's shareholding table and may be refetched by Yahoo if missing.

Install: python3 -m pip install requests beautifulsoup4
Run:     python3 pharma_screening_engine_live.py --source screener
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

import bs4
import requests
import yfinance as yf

BASE_URL = "https://www.screener.in/company/{slug}/consolidated/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}
MONTHS = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
          "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}

# Screener masks login-gated rows with 'xxx'-style placeholders.
MASKED = {"", "-", "--", "x", "xx", "xxx", "x.xx", "xx.xx", "xxx.xx", "xxxx", "xxxxx",
          ".", "..", "NA", "N/A", "n/a", "na", "bl", "nil"}
PT_OP = "Operating Profit"
PT_DEP = "Depreciation"
PT_INT = "Interest"


def _num(text: Any) -> float | None:
    """Coerce a Screener cell to a float, or None when masked/missing."""
    if text is None:
        return None
    raw = str(text).strip().replace("\u20b9", "").replace(",", "").replace(" ", "")
    if raw in MASKED or raw.startswith("Log in") or raw.startswith("Login"):
        return None
    negative = raw.startswith("(") and raw.endswith(")")
    if negative:
        raw = raw[1:-1]
    percent = raw.endswith("%")
    if percent:
        raw = raw[:-1]
    if not raw or "%" in raw or raw.count(".") > 1:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return -value if negative else value


def _year(label: Any) -> int | None:
    for part in str(label).split():
        if part.isdigit():
            return int(part)
    return None


def _ym(label: Any) -> int | None:
    """Parse 'Mar 2026' / 'Jun 2025' into year*100+month (202603), else None."""
    parts = str(label).strip().split()
    if len(parts) != 2:
        return None
    month, year = MONTHS.get(parts[0]), parts[1]
    if month is None or not year.isdigit():
        return None
    return int(year) * 100 + month


def _annual_tables(soup: bs4.BeautifulSoup) -> List[bs4.Tag]:
    """Tables whose fiscal columns are annual ('Mar <year>' style)."""
    return [t for t in soup.find_all("table") if _is_annual(t)]


def _is_annual(table: bs4.Tag) -> bool:
    for tr in table.find_all("tr"):
        th = tr.find_all("th")
        if not th:
            continue
        cells = [c.get_text(strip=True) for c in th]
        return len(cells) >= 2 and cells[1].startswith("Mar ")
    return False


def _find_annual(soup: bs4.BeautifulSoup, anchor: str) -> bs4.Tag | None:
    for table in _annual_tables(soup):
        if _has_row(table, anchor):
            return table
    return None


def _has_row(table: bs4.Tag, anchor: str) -> bool:
    for tr in table.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        if cells and cells[0].get_text(strip=True) == anchor:
            return True
    return False


def _series(table: bs4.Tag | None, anchor: str) -> Dict[int, float | None]:
    """Return {fiscal_year: value} for the row labelled `anchor` in an annual table."""
    if table is None:
        return {}
    years: List[int | None] = []
    for tr in table.find_all("tr"):
        th = tr.find_all("th")
        if th:
            years = [_year(c.get_text(strip=True)) for c in th]
            break
    for tr in table.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        if not cells or cells[0].get_text(strip=True) != anchor:
            continue
        values = [_num(c.get_text(strip=True)) for c in cells[1:]]
        return {y: v for y, v in zip(years, values) if y is not None}
    return {}


def _quarterly_series(soup: bs4.BeautifulSoup, anchor: str) -> Dict[int, float | None]:
    """Return {ym (year*100+month): value} from the quarterly results table."""
    for table in soup.find_all("table"):
        if not _has_row(table, anchor):
            continue
        keys: List[int | None] = []
        for tr in table.find_all("tr"):
            th = tr.find_all("th")
            if th:
                keys = [_ym(c.get_text(strip=True)) for c in th]
                break
        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            if not cells or cells[0].get_text(strip=True) != anchor:
                continue
            values = [_num(c.get_text(strip=True)) for c in cells[1:]]
            return {k: v for k, v in zip(keys, values) if k is not None and v is not None}
    return {}


def _yoy(current: float | None, prior: float | None) -> float | None:
    if current is None or prior in (None, 0):
        return None
    return (current / prior - 1) * 100


def _list_of(by_year: Dict[int, float | None]) -> List[float | None]:
    return [by_year[y] for y in sorted(by_year)]


def _latest_non_none(values: List[float | None]) -> float | None:
    valid = [v for v in values if v is not None]
    return valid[-1] if valid else None


def valid_annual_count(by_year: Dict[int, float | None]) -> int:
    return sum(1 for v in by_year.values() if v is not None)


def _cagr(by_year: Dict[int, float | None], periods: int) -> float | None:
    """CAGR (%) over the latest `periods` intervals (periods+1 points).

    Returns None when either endpoint is not positive - a negative or zero base
    makes CAGR not meaningful (per the metrics-and-fiscal-rules guardrail).
    """
    values = [by_year[y] for y in sorted(by_year) if by_year[y] is not None]
    if len(values) < periods + 1:
        return None
    base, last = values[-(periods + 1)], values[-1]
    if base is None or last is None or base <= 0 or last <= 0:
        return None
    return ((last / base) ** (1 / periods) - 1) * 100


def _stat_table(soup: bs4.BeautifulSoup, header_text: str) -> Dict[str, float | None]:
    """Return {period_label: value} from a one-column stat table (e.g. CAGR)."""
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            if not cells or cells[0].get_text(strip=True) != header_text:
                continue
            out: Dict[str, float | None] = {}
            for row in table.find_all("tr"):
                rc = row.find_all(["th", "td"])
                if len(rc) >= 2:
                    key = rc[0].get_text(strip=True).rstrip(":").strip()
                    if key in ("10 Years", "5 Years", "3 Years", "1 Year", "TTM", "Last Year"):
                        out[key] = _num(rc[1].get_text(strip=True))
            return out
    return {}


def _parse_company(soup: bs4.BeautifulSoup, slug: str) -> Dict[str, Any]:
    """Extract raw annual series (and small stat tables) from a Screener page."""
    pl = _find_annual(soup, "Sales+")
    balance = _find_annual(soup, "Total Liabilities")
    cash = _find_annual(soup, "Cash from Operating Activity+")
    ratios = _find_annual(soup, "ROCE %")
    share = _find_annual(soup, "Promoters+")

    sales_y = _series(pl, "Sales+")
    op_income_y = _series(pl, PT_OP)
    dep_y = _series(pl, PT_DEP)
    profit_y = _series(pl, "Net Profit+")
    interest_y = _series(pl, PT_INT)
    assets_y = _series(balance, "Total Assets")
    debt_y = _series(balance, "Borrowings+")
    equity_cap_y = _series(balance, "Equity Capital")
    reserves_y = _series(balance, "Reserves")
    cfo_y = _series(cash, "Cash from Operating Activity+")
    fcf_y = _series(cash, "Free Cash Flow")
    roce_y = _series(ratios, "ROCE %")
    promoter_y = _series(share, "Promoters+")

    equity_y: Dict[int, float | None] = {}
    for y in set(equity_cap_y) | set(reserves_y):
        cap, res = equity_cap_y.get(y), reserves_y.get(y)
        equity_y[y] = (cap + res) if cap is not None and res is not None else (cap if res is None else None)
    net_debt_y = {y: v for y, v in debt_y.items() if v is not None}

    growth = _stat_table(soup, "Compounded Sales Growth")
    profit_growth = _stat_table(soup, "Compounded Profit Growth")

    q_sales = _quarterly_series(soup, "Sales+")
    q_profit = _quarterly_series(soup, "Net Profit+")
    qs, qp = None, None
    if q_sales:
        latest_ym = max(q_sales)
        qs = _yoy(q_sales.get(latest_ym), q_sales.get(latest_ym - 100))
        qp = _yoy(q_profit.get(latest_ym), q_profit.get(latest_ym - 100)) if q_profit else None

    return {
        "slug": slug, "sales_y": sales_y, "op_income_y": op_income_y, "dep_y": dep_y,
        "profit_y": profit_y, "interest_y": interest_y, "assets_y": assets_y,
        "debt_y": debt_y, "equity_cap_y": equity_cap_y, "reserves_y": reserves_y,
        "cfo_y": cfo_y, "fcf_y": fcf_y, "roce_y": roce_y, "promoter_y": promoter_y,
        "equity_y": equity_y, "net_debt_y": net_debt_y,
        "sales_cagr_reported_5y": growth.get("5 Years"), "profit_cagr_reported_5y": profit_growth.get("5 Years"),
        "quarterly_sales_growth": qs, "quarterly_profit_growth": qp,
    }


class ScreenerProvider:
    """Fetch consolidated annual fundamentals for one NSE-listed ticker."""

    SOURCE_LABEL = "Screener.in (consolidated) + Yahoo Finance valuation"

    def fetch(self, ticker_symbol: str) -> Dict[str, Any]:
        slug = ticker_symbol.split(".")[0].upper()
        response = requests.get(BASE_URL.format(slug=slug), headers=HEADERS, timeout=20)
        response.raise_for_status()
        soup = bs4.BeautifulSoup(response.text, "html.parser")
        p = _parse_company(soup, slug)

        sales = _list_of(p["sales_y"])
        # Some companies (e.g. HCLTech) have their financials masked/login-gated on
        # Screener, so the P&L and cash-flow tables are absent. Surface that as a
        # clear fetch error instead of silently returning empty series.
        if not any(v is not None for v in p["sales_y"].values()) and \
           not any(v is not None for v in p["profit_y"].values()):
            raise ValueError(f"Screener financials unavailable/masked for slug '{slug}'")

        invested_capital_y: Dict[int, float | None] = {}
        for y in set(p["op_income_y"]) | set(p["roce_y"]) | set(p["equity_y"]):
            ebit, roce = p["op_income_y"].get(y), p["roce_y"].get(y)
            if ebit is not None and roce not in (None, 0):
                invested_capital_y[y] = ebit * 100.0 / roce
            elif p["equity_y"].get(y) is not None:
                invested_capital_y[y] = p["equity_y"].get(y) + (p["net_debt_y"].get(y) or 0)

        ebitda_y: Dict[int, float | None] = {}
        for y in set(p["op_income_y"]) | set(p["dep_y"]):
            ebit, dep = p["op_income_y"].get(y), p["dep_y"].get(y)
            ebitda_y[y] = ebit + dep if ebit is not None and dep is not None else ebit

        valuation = self._valuation(ticker_symbol)

        warnings: List[str] = []
        for name, series in (("sales", p["sales_y"]), ("profit", p["profit_y"]),
                             ("cfo", p["cfo_y"]), ("debt", p["debt_y"]),
                             ("equity", p["equity_y"]), ("roce", p["roce_y"]),
                             ("free_cash_flow", p["fcf_y"])):
            count = valid_annual_count(series)
            if count < 5:
                warnings.append(f"{name}: only {count} annual years (<5) -> 5-year tests unreliable")

        return {
            "ticker": ticker_symbol,
            "company": valuation.get("long_name") or f"Screener slug {slug}",
            "market_cap_cr": valuation.get("market_cap_cr"),
            "sales": sales, "profit": _list_of(p["profit_y"]), "assets": _list_of(p["assets_y"]),
            "debt": _list_of(p["debt_y"]), "equity": _list_of(p["equity_y"]), "cfo": _list_of(p["cfo_y"]),
            "capex": [None] * len(sales),
            "current_assets": None, "current_liabilities": None,
            "interest": _latest_non_none(_list_of(p["interest_y"])),
            "operating_income": _latest_non_none(_list_of(p["op_income_y"])),
            "quarterly_sales_growth": p["quarterly_sales_growth"],
            "quarterly_profit_growth": p["quarterly_profit_growth"],
            "pe": valuation.get("pe"), "peg": valuation.get("peg"), "pb": valuation.get("pb"),
            "promoter_holding": _latest_non_none(_list_of(p["promoter_y"])),
            "ebit_y": p["op_income_y"], "profit_y": p["profit_y"], "equity_y": p["equity_y"],
            "invested_capital_y": invested_capital_y, "net_debt_y": p["net_debt_y"],
            "ebitda_y": ebitda_y, "fcf_y": p["fcf_y"], "cfo_y": p["cfo_y"],
            "warnings": warnings,
            "source": self.SOURCE_LABEL,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _valuation(ticker_symbol: str) -> Dict[str, float | None]:
        try:
            info = yf.Ticker(ticker_symbol).info or {}
        except Exception:
            return {"market_cap_cr": None, "pe": None, "peg": None, "pb": None, "long_name": None}
        mc = info.get("marketCap")
        return {
            "long_name": info.get("longName") or info.get("shortName"),
            "market_cap_cr": (mc / 10_000_000) if mc else None,
            "pe": _num(info.get("trailingPE")),
            "peg": _num(info.get("pegRatio")),
            "pb": _num(info.get("priceToBook")),
        }


def _fmt(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.2f}"


def validate(tickers: List[str], years: int = 5, delay: float = 1.5) -> None:
    """Render scraped series vs Screener's own reported figures for cross-check."""
    for symbol in tickers:
        slug = symbol.split(".")[0].upper()
        try:
            response = requests.get(BASE_URL.format(slug=slug), headers=HEADERS, timeout=20)
            response.raise_for_status()
            soup = bs4.BeautifulSoup(response.text, "html.parser")
            p = _parse_company(soup, slug)
        except Exception as exc:
            print(f"{symbol}: ERROR {type(exc).__name__}: {exc}")
            continue

        print("=" * 92)
        print(f"VALIDATION: {symbol} (slug {slug})  | {p['slug']}")
        common = [y for y in sorted(p["sales_y"]) if p["sales_y"][y] is not None][-years:]
        print(f"{'FY':<6}{'Sales':>11}{'PAT':>11}{'CFO':>11}{'Debt':>11}{'Equity':>11}{'RevROCE%':>10}{'CalCE%':>9}{'d%':>7}")
        for y in common:
            sales = p["sales_y"].get(y)
            pat = p["profit_y"].get(y)
            cfo = p["cfo_y"].get(y)
            debt = p["debt_y"].get(y)
            eq = p["equity_y"].get(y)
            ebit = p["op_income_y"].get(y)
            roce_rep = p["roce_y"].get(y)
            ce = (eq + debt) if (eq is not None and debt is not None) else None
            roce_calc = (ebit / ce * 100) if (ebit is not None and ce not in (None, 0)) else None
            delta = (roce_calc - roce_rep) if (roce_calc is not None and roce_rep is not None) else None

            def cell(v: float | None) -> str:
                return f"{v:,.0f}" if isinstance(v, (int, float)) else "—"
            def pct(v: float | None) -> str:
                return f"{v:.1f}" if isinstance(v, (int, float)) else "—"
            print("FY%-4d %11s %11s %11s %11s %11s %10s %9s %7s"
                  % (y, cell(sales), cell(pat), cell(cfo), cell(debt), cell(eq),
                     pct(roce_rep), pct(roce_calc),
                     (f"{delta:+.1f}" if delta is not None else "—")))

        print("CAGR over last %d years (scraped vs Screener-reported):" % years)
        print("  Sales : scraped=%s | reported=%s" % (_fmt(_cagr(p["sales_y"], years)), _fmt(p["sales_cagr_reported_5y"])))
        print("  Profit: scraped=%s | reported=%s" % (_fmt(_cagr(p["profit_y"], years)), _fmt(p["profit_cagr_reported_5y"])))
        promoter = _latest_non_none(_list_of(p["promoter_y"]))
        print("  Promoter=%s | q-sales growth=%s" % (_fmt(promoter), _fmt(p["quarterly_sales_growth"])))
        time.sleep(delay)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Screener.in provider: validate or inspect.")
    parser.add_argument("--validate", action="store_true", help="Cross-check scraped series vs Screener's reported figures")
    parser.add_argument("--tickers", nargs="+", default=["SUNPHARMA.NS", "DIVISLAB.NS", "LUPIN.NS"])
    parser.add_argument("--years", type=int, default=5, help="Number of fiscal years to render (default 5)")
    parser.add_argument("--delay", type=float, default=1.5)
    args = parser.parse_args()

    if args.validate:
        validate(args.tickers, args.years, args.delay)
    else:
        provider = ScreenerProvider()
        for symbol in args.tickers:
            data = provider.fetch(symbol)
            print("=" * 64)
            print(symbol, "| source:", data["source"])
            print("  years: sales/profit/cfo:", len(data["sales"]), len(data["profit"]), len(data["cfo"]))
            print("  promoter:", data["promoter_holding"], "| pe:", data["pe"], "| pb:", data["pb"])
            print("  latest sales/profit:", data["sales"][-1], data["profit"][-1])
            print("  q sales growth:", data["quarterly_sales_growth"])
            time.sleep(args.delay)

