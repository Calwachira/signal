"""Shared analytics logic: caching, parallel fan-out, comparison with the previous period,
and anomaly detection. Works with either the demo or the live provider."""
from __future__ import annotations

import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

# range key -> (seconds covered, chart bucket seconds)
RANGES = {"1h": (3600, 60), "6h": (21600, 300), "24h": (86400, 900), "7d": (604800, 7200)}

# metric -> (label, unit, which direction is good)
KPI_META = [
    ("events", "Events", "count", "up"),
    ("error_rate", "Error rate", "percent", "down"),
    ("p95", "p95 latency", "ms", "down"),
    ("failed_logins", "Failed logins", "count", "down"),
]


def flag_anomalies(values, window=48, z=4.0):
    """Flag points far above a robust baseline (rolling median + MAD)."""
    flags = []
    for i, v in enumerate(values):
        hist = values[max(0, i - window):i]
        if len(hist) < 6:
            flags.append(False)
            continue
        med = statistics.median(hist)
        mad = statistics.median(abs(h - med) for h in hist) * 1.4826
        flags.append(v > med + z * max(mad, 0.15 * med, 1.0))
    return flags


def pct_change(cur, prev):
    if not prev:
        return None
    return (cur - prev) / prev * 100


class Analytics:
    def __init__(self, provider, ttl: int = 30):
        self.p, self.ttl = provider, ttl
        self._cache: dict = {}
        self._lock = threading.Lock()

    def cached(self, key, fn):
        now = time.time()
        with self._lock:
            hit = self._cache.get(key)
            if hit and now - hit[0] < self.ttl:
                return hit[1]
        value = fn()
        with self._lock:
            self._cache[key] = (now, value)
        return value

    def overview(self, rng: str) -> dict:
        if rng not in RANGES:
            raise ValueError(f"Unknown range '{rng}'. Use one of: {', '.join(RANGES)}")
        return self.cached(("overview", rng), lambda: self._overview(rng))

    def _overview(self, rng: str) -> dict:
        secs, span = RANGES[rng]
        end = int(time.time())
        start = end - secs
        p = self.p
        with ThreadPoolExecutor(max_workers=8) as ex:
            f = {
                "cur": ex.submit(p.kpis, start, end),
                "prev": ex.submit(p.kpis, start - secs, start),
                "ts": ex.submit(p.timeseries, start, end, span),
                "logins": ex.submit(p.logins, start, end, span),
                "endpoints": ex.submit(p.endpoints, start, end),
                "services": ex.submit(p.services, start, end),
                "errors": ex.submit(p.errors, start, end),
            }
            r = {k: v.result() for k, v in f.items()}

        kpis = [{
            "key": key, "label": label, "unit": unit, "good": good,
            "value": r["cur"][key], "delta": pct_change(r["cur"][key], r["prev"][key]),
        } for key, label, unit, good in KPI_META]

        flags = flag_anomalies(r["logins"]["failures"])
        logins = dict(r["logins"], anomalies=[i for i, x in enumerate(flags) if x])

        return {
            "range": rng, "mode": p.mode, "span_seconds": span,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "kpis": kpis, "timeseries": r["ts"], "logins": logins,
            "endpoints": r["endpoints"], "services": r["services"], "errors": r["errors"],
        }

    def search(self, spl: str, rng: str) -> dict:
        if rng not in RANGES:
            raise ValueError(f"Unknown range '{rng}'.")
        secs, _ = RANGES[rng]
        end = int(time.time())
        started = time.time()
        rows, note = self.p.search(spl, end - secs, end)
        columns: list[str] = []
        for row in rows:
            for k in row:
                if k not in columns:
                    columns.append(k)
        return {"columns": columns, "rows": rows, "count": len(rows),
                "elapsed_ms": int((time.time() - started) * 1000), "mode": self.p.mode, "note": note}
