#!/usr/bin/env python3
"""Per-sector threshold presets for the screen's soft criteria (Sector-Adjusted mode).

Each sector overrides a subset of the engine's generic `SECTOR_ADJUSTED_THRESHOLDS`
(the baseline) with growth/valuation thresholds suited to its economics; anything
not overridden keeps the generic baseline. Soft = growth (CAGR/YoY/quarterly) and
absolute valuation (P/E, PEG, P/B). Hard criteria (quality/leverage/cash-flow/
promoter) are never threshold-adjusted here.

These are judgment presets, not hard rules - tune them as you validate against data.
"""

from pharma_screening_engine import SECTOR_ADJUSTED_THRESHOLDS as BASE

# Growth overrides (">" = higher is better): soft growth minima.
IT_GROWTH = {"G1-02": (">", 12), "G1-03": (">", 12), "G1-04": (">", 10), "G1-05": (">", 12),
             "G2-01": (">", 10), "G2-02": (">", 10), "G2-15": (">", 12), "G2-16": (">", 14),
             "G2-21": (">", 12)}
# Valuation overrides ("<" = lower is better): premium multiples tolerated.
IT_VAL = {"G1-20": ("<", 50), "G1-21": ("<", 3.0), "G1-22": ("<", 9.0),
          "G2-12": ("<", 45), "G2-13": ("<", 3.0), "G2-14": ("<", 8.0)}

PRESETS: dict[str, dict] = {
    "IT Services": {**BASE, **IT_GROWTH, **IT_VAL},
    "Consumer / FMCG": {**BASE, "G1-02": (">", 7), "G1-03": (">", 7), "G1-04": (">", 6),
                        "G1-05": (">", 6), "G2-01": (">", 6), "G2-02": (">", 6),
                        "G2-15": (">", 7), "G2-16": (">", 8), "G2-21": (">", 8),
                        "G1-20": ("<", 55), "G1-21": ("<", 3.0), "G1-22": ("<", 12.0),
                        "G2-12": ("<", 50), "G2-13": ("<", 3.0), "G2-14": ("<", 10.0)},
    "Automobiles": {**BASE, "G1-02": (">", 8), "G1-03": (">", 8), "G1-04": (">", 7),
                    "G1-05": (">", 8), "G2-01": (">", 7), "G2-02": (">", 7),
                    "G2-15": (">", 8), "G2-16": (">", 10), "G2-21": (">", 10),
                    "G1-20": ("<", 45), "G1-21": ("<", 2.5), "G1-22": ("<", 7.0),
                    "G2-12": ("<", 40), "G2-13": ("<", 2.5), "G2-14": ("<", 6.0)},
    "Chemicals": {**BASE, "G1-02": (">", 10), "G1-03": (">", 10), "G1-04": (">", 8),
                  "G1-05": (">", 10), "G2-01": (">", 8), "G2-02": (">", 8),
                  "G2-15": (">", 10), "G2-16": (">", 12), "G2-21": (">", 12),
                  "G1-20": ("<", 42), "G1-21": ("<", 2.5), "G1-22": ("<", 6.0),
                  "G2-12": ("<", 38), "G2-13": ("<", 2.5), "G2-14": ("<", 5.5)},
    "Cement": {**BASE, "G1-02": (">", 8), "G1-03": (">", 8), "G1-04": (">", 7),
               "G1-05": (">", 7), "G2-01": (">", 7), "G2-02": (">", 7),
               "G2-15": (">", 8), "G2-16": (">", 9), "G2-21": (">", 9),
               "G1-20": ("<", 45), "G1-21": ("<", 2.5), "G1-22": ("<", 4.5),
               "G2-12": ("<", 40), "G2-13": ("<", 2.5), "G2-14": ("<", 4.0)},
    "Capital Goods / Infra": {**BASE, "G1-02": (">", 12), "G1-03": (">", 12), "G1-04": (">", 10),
                              "G1-05": (">", 12), "G2-01": (">", 10), "G2-02": (">", 10),
                              "G2-15": (">", 12), "G2-16": (">", 14), "G2-21": (">", 12),
                              "G1-20": ("<", 42), "G1-21": ("<", 2.5), "G1-22": ("<", 7.0),
                              "G2-12": ("<", 38), "G2-13": ("<", 2.5), "G2-14": ("<", 6.0)},
    "Metals & Mining": {**BASE, "G1-02": (">", 8), "G1-03": (">", 8), "G1-04": (">", 6),
                        "G1-05": (">", 8), "G2-01": (">", 6), "G2-02": (">", 6),
                        "G2-15": (">", 8), "G2-16": (">", 10), "G2-21": (">", 8),
                        "G1-20": ("<", 28), "G1-21": ("<", 2.0), "G1-22": ("<", 2.5),
                        "G2-12": ("<", 25), "G2-13": ("<", 2.0), "G2-14": ("<", 2.2)},
    "Pharmaceuticals": {**BASE},
    "Oil & Gas": {**BASE, "G1-02": (">", 5), "G1-03": (">", 5), "G1-04": (">", 5),
                  "G1-05": (">", 5), "G2-01": (">", 5), "G2-02": (">", 5),
                  "G2-15": (">", 5), "G2-16": (">", 6), "G2-21": (">", 6),
                  "G1-20": ("<", 25), "G1-21": ("<", 2.0), "G1-22": ("<", 2.5),
                  "G2-12": ("<", 22), "G2-13": ("<", 2.0), "G2-14": ("<", 2.2)},
    "Power / Utilities": {**BASE, "G1-02": (">", 5), "G1-03": (">", 5), "G1-04": (">", 5),
                          "G1-05": (">", 5), "G2-01": (">", 5), "G2-02": (">", 5),
                          "G2-15": (">", 5), "G2-16": (">", 6), "G2-21": (">", 6),
                          "G1-20": ("<", 35), "G1-21": ("<", 2.5), "G1-22": ("<", 4.0),
                          "G2-12": ("<", 30), "G2-13": ("<", 2.5), "G2-14": ("<", 3.5)},
    "Telecom": {**BASE, "G1-02": (">", 5), "G1-03": (">", 6), "G1-04": (">", 5),
                "G1-05": (">", 6), "G2-01": (">", 5), "G2-02": (">", 6),
                "G2-15": (">", 5), "G2-16": (">", 7), "G2-21": (">", 7),
                "G1-20": ("<", 40), "G1-21": ("<", 2.5), "G1-22": ("<", 5.0),
                "G2-12": ("<", 36), "G2-13": ("<", 2.5), "G2-14": ("<", 4.5)},
    "Private Banks": {**BASE, "G1-02": (">", 8), "G1-03": (">", 10), "G1-04": (">", 7),
                      "G1-05": (">", 8), "G2-01": (">", 7), "G2-02": (">", 8),
                      "G2-15": (">", 8), "G2-16": (">", 10), "G2-21": (">", 8),
                      "G1-20": ("<", 30), "G1-21": ("<", 2.5), "G1-22": ("<", 5.0),
                      "G2-12": ("<", 27), "G2-13": ("<", 2.5), "G2-14": ("<", 4.5)},
    "PSU Banks": {**BASE, "G1-02": (">", 6), "G1-03": (">", 6), "G1-04": (">", 5),
                  "G1-05": (">", 6), "G2-01": (">", 5), "G2-02": (">", 6),
                  "G2-15": (">", 6), "G2-16": (">", 7), "G2-21": (">", 6),
                  "G1-20": ("<", 12), "G1-21": ("<", 1.5), "G1-22": ("<", 2.0),
                  "G2-12": ("<", 10), "G2-13": ("<", 1.5), "G2-14": ("<", 1.8)},
    "NBFC / Financial Services": {**BASE, "G1-02": (">", 8), "G1-03": (">", 10), "G1-04": (">", 7),
                                  "G1-05": (">", 8), "G2-01": (">", 7), "G2-02": (">", 8),
                                  "G2-15": (">", 8), "G2-16": (">", 10), "G2-21": (">", 8),
                                  "G1-20": ("<", 40), "G1-21": ("<", 2.5), "G1-22": ("<", 6.0),
                                  "G2-12": ("<", 35), "G2-13": ("<", 2.5), "G2-14": ("<", 5.0)},
}


# NSE-style sector names mapped onto the existing preset profiles.
ALIASES = {
    "Healthcare & Pharmaceuticals": "Pharmaceuticals",
    "Information Technology & Digital": "IT Services",
    "Automobile & Auto Components": "Automobiles",
    "Capital Goods & Industrials": "Capital Goods / Infra",
    "Infrastructure, Construction & Real Estate": "Capital Goods / Infra",
    "Transport Infrastructure & Logistics": "Capital Goods / Infra",
    "Oil, Gas & Consumable Fuels": "Oil & Gas",
    "Telecom & Media": "Telecom",
    "Power & Utilities": "Power / Utilities",
    "Chemicals & Materials": "Chemicals",
}


def _preset_key(sector: str) -> str:
    return ALIASES.get(sector, sector)


def get_thresholds(sector: str) -> dict | None:
    """Return the soft-criteria threshold override for a sector, or None (default)."""
    return PRESETS.get(_preset_key(sector))


def describe(sector: str) -> str:
    key = _preset_key(sector)
    if key not in PRESETS:
        return "default sector-adjusted thresholds"
    diffs = [f"{k} {v[0]}{v[1]}" for k, v in PRESETS[key].items() if v != BASE.get(k)]
    return ", ".join(diffs[:6]) + (f" (+{len(diffs)-6} more)" if len(diffs) > 6 else "")
