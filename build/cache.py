#!/usr/bin/env python3
"""Tiny disk cache for provider fetches (Screener.in / Yahoo Finance).

Screener.in is HTML-scraped and rate-limited, and Yahoo can be slow or omit
fields. Caching each provider's normalized fetch output as JSON, keyed by
source + ticker + day, lets reruns reuse a fresh day's data without re-hitting
the network. Disable with --no-cache or adjust the TTL with --ttl-hours; clear
the cache directory to force a refresh.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _safe_key(key: str) -> str:
    # ':' and other characters are invalid/ambiguous in Windows filenames (e.g.
    # NTFS Alternate Data Streams), so map anything unsafe to '_'.
    return re.sub(r"[^A-Za-z0-9._-]", "_", key)


class DiskCache:
    def __init__(self, root: str | Path, ttl_hours: float = 12.0):
        self.root = Path(root)
        self.ttl_seconds = ttl_hours * 3600.0

    def _path(self, key: str) -> Path:
        return self.root / f"{_safe_key(key)}.json"

    def get(self, key: str) -> Any:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            if time.time() - path.stat().st_mtime > self.ttl_seconds:
                return None
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def set(self, key: str, value: Any) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._path(key).write_text(json.dumps(value, default=str), encoding="utf-8")


def daily_key(source: str, symbol: str) -> str:
    day = datetime.now(timezone.utc).date().isoformat()
    return f"{source}:{symbol}:{day}"


def cached_fetch(provider: Any, symbol: str, cache: DiskCache | None, source: str) -> dict:
    """Fetch through `provider`, serving from `cache` when a fresh entry exists."""
    key = daily_key(source, symbol)
    cached = cache.get(key) if cache else None
    if cached is not None:
        cached["__cache_hit"] = True
        return cached
    data = provider.fetch(symbol)
    data["__cache_hit"] = False
    if cache:
        cache.set(key, data)
    return data
