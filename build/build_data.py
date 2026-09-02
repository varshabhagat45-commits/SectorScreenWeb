#!/usr/bin/env python3
"""Regenerate site/data/sectors.json in this repo (vendored for GitHub Actions).

This is a copy of the engine's build_data.py adjusted so it writes into THIS repo
(site/data/sectors.json). It runs on any machine with Python + the requirements
installed, or automatically via .github/workflows/refresh-data.yml.

Run:  python build/build_data.py
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import sector_map
import yfinance as yf
from bank_engine import BankEngine
from cache import DiskCache
from pharma_screening_engine import MODES
from pharma_screening_engine_live import LiveScreeningEngine
from screener_provider import ScreenerProvider

REPO = Path(__file__).resolve().parents[1]
CACHE = REPO / "cache"
OUT = REPO / "site" / "data" / "sectors.json"


def momentum(ticker_symbol: str):
    """Price momentum: 1Y / 6M / 3M returns (%). None if price data unavailable."""
    try:
        hist = yf.Ticker(ticker_symbol).history(period="2y")
        if hist is None or hist.empty or "Close" not in hist:
            return (None, None, None)
        close = hist["Close"].dropna()
        def ret(days):
            if len(close) <= days:
                return None
            latest, past = close.iloc[-1], close.iloc[-1 - days]
            return (latest / past - 1) * 100 if past else None
        return (ret(252), ret(126), ret(63))
    except Exception:
        return (None, None, None)


METRIC_KEYS = [
    "pe", "pb", "peg", "roe_current", "roe_avg_5y", "current_roe", "current_roce",
    "current_op_margin", "avg_roce_5y", "avg_roe_5y", "current_de_ratio", "avg_de_5y",
    "net_debt_to_ebitda", "fcf_5y_total", "fcf_3y_total", "cfo_to_ebitda",
    "sales_cagr_5y", "profit_cagr_5y", "sales_growth_yoy", "profit_growth_yoy",
    "promoter_holding", "roa_current", "equity_to_assets", "gross_npa",
    "revenue_cagr_5y", "deposits_cagr_5y",
]


def _norm(companies: list, is_bank: bool) -> list:
    out = []
    for c in companies:
        if is_bank:
            checks = c.get("checks") or []
        else:
            checks = (c.get("group1_checks") or []) + (c.get("group2_checks") or [])
        out.append({
            "ticker": c.get("ticker"), "company": c.get("company"),
            "category": c.get("category"),
            "g1": c.get("group1_score"), "g2": c.get("group2_score"),
            "passed": sum(1 for x in checks if x.get("passed")),
            "failed": c.get("failed_criteria"),
            "market_cap_cr": c.get("market_cap_cr"),
            "metrics": {k: c.get(k) for k in METRIC_KEYS if k in c},
            "hard": [{"code": x["code"], "criterion": x["criterion"], "value": x.get("value")}
                     for x in checks if (not x.get("soft")) and (not x.get("missing")) and (not x.get("passed"))],
            "soft": [{"code": x["code"], "criterion": x["criterion"], "value": x.get("value")}
                     for x in checks if x.get("soft") and (not x.get("missing")) and (not x.get("passed"))],
            "missing": sum(1 for x in checks if x.get("missing")),
        })
    return out


def _score(c: dict) -> tuple:
    """Composite research score (0-100): quality+fundamentals (60%) and
    price momentum (40%). Transparent, heuristic ranking only — not advice."""
    hard = len(c.get("hard") or [])
    passed = c.get("passed") or 0
    failed = c.get("failed") or 0
    missing = c.get("missing") or 0
    total = passed + failed + missing
    pass_pct = (passed / total) if total else 0.0
    quality = max(0.0, min(100.0, pass_pct * 100.0 - hard * 3.0))
    m = c.get("metrics") or {}
    rets = [(m.get("mom_1y"), 0.5), (m.get("mom_6m"), 0.3), (m.get("mom_3m"), 0.2)]
    avail = [(r, w) for r, w in rets if isinstance(r, (int, float)) and not isinstance(r, bool)]
    weighted = (sum(r * w for r, w in avail) / sum(w for _, w in avail)) if avail else 0.0
    mom_score = max(0.0, min(100.0, 50.0 + 0.5 * weighted))
    composite = round(0.6 * quality + 0.4 * mom_score, 1)
    return round(quality, 1), round(mom_score, 1), composite


def build(only_sectors: list | None = None, modes: list | None = None, delay: float = 0.3) -> None:
    modes = modes or list(MODES)
    cache = DiskCache(CACHE, 1.0)
    data = {"as_of": datetime.now(timezone.utc).isoformat(),
            "source": "Screener.in (consolidated) + Yahoo Finance valuation (snapshot)",
            "sectors": {}}
    sectors = only_sectors or sector_map.sector_names()
    for sector in sectors:
        tickers = sector_map.get_tickers(sector)
        if not tickers:
            continue
        fit = sector_map.get_fit(sector)
        entry = {"fit": fit, "note": sector_map.get_fit_note(sector), "modes": {}}
        is_bank = fit == "financial"
        errors_total = 0
        mom = {t: momentum(t) for t in tickers}
        for mode in modes:
            if is_bank:
                report = BankEngine(mode=mode).run(tickers, delay, cache)
            else:
                report = LiveScreeningEngine(provider=ScreenerProvider(), mode=mode).run(tickers, delay, cache)
            companies = _norm(report["companies"], is_bank)
            for c in companies:
                m = mom.get(c["ticker"], (None, None, None))
                c["metrics"]["mom_1y"], c["metrics"]["mom_6m"], c["metrics"]["mom_3m"] = m
                c["q_score"], c["mom_score"], c["composite"] = _score(c)
            entry["modes"][mode] = companies
            errors_total += len(report.get("errors") or [])
        data["sectors"][sector] = entry
        print(f"built: {sector} ({len(tickers)} tickers, fit={fit}, errors={errors_total})")
        time.sleep(0.3)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {OUT} ({len(data['sectors'])} sectors)")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--sector", action="append", dest="only", help="Build only this sector (repeatable)")
    p.add_argument("--modes", nargs="+", choices=MODES, default=list(MODES))
    p.add_argument("--delay", type=float, default=0.3)
    a = p.parse_args()
    build(a.only, a.modes, a.delay)
