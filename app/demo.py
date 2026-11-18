"""Deterministic sample data so the app runs fully without a Splunk server.

Traffic follows a daily cycle. Every ~9 hours a 40-minute incident raises errors and
latency, and every ~13 hours a 30-minute burst of failed logins occurs, so charts always
have something worth looking at.
"""
from __future__ import annotations

import fnmatch
import hashlib
import math
import random
import re
from datetime import datetime, timezone

INCIDENT = (32400, 0.55, 2400)   # block seconds, start fraction, duration seconds
ATTACK = (46800, 0.30, 1800)

SERVICES = {"checkout": 0.22, "auth": 0.18, "search": 0.24, "catalog": 0.16, "payments": 0.12, "notifications": 0.08}
HOSTS = [f"web-{i:02d}" for i in range(1, 7)]
ENDPOINTS = [
    ("/api/checkout", "checkout", 420), ("/api/search", "search", 310), ("/api/orders", "checkout", 260),
    ("/api/login", "auth", 180), ("/api/catalog", "catalog", 150), ("/api/cart", "checkout", 120),
    ("/api/payments/charge", "payments", 540), ("/api/profile", "auth", 90),
]
ERROR_MSGS = [
    "Upstream timeout calling payments gateway", "Database connection pool exhausted",
    "Unhandled exception in order handler: NullReference", "Redis connection reset by peer",
    "TLS handshake failed with inventory service", "Circuit breaker open for catalog-index",
]
WARN_MSGS = ["Slow response from catalog index", "Retrying request (attempt 2)", "Rate limit approaching for client"]
INFO_MSGS = ["Request completed", "Cache hit", "Session created", "Order placed"]
USERS = ["amara", "jkimani", "lwanjiru", "dotieno", "svc-batch", "nmutua", "rbarasa", "admin"]


def _rng(*key) -> random.Random:
    digest = hashlib.md5("|".join(map(str, key)).encode()).hexdigest()
    return random.Random(int(digest[:12], 16))


def _daily(ts: float) -> float:
    hour = (ts % 86400) / 3600
    return 0.65 + 0.35 * math.sin((hour - 9) / 24 * 2 * math.pi)


def _overlap(t0: int, t1: int, spec) -> int:
    block, frac, dur = spec
    total = 0
    for b in range(t0 // block - 1, t1 // block + 1):
        s = b * block + int(block * frac)
        total += max(0, min(t1, s + dur) - max(t0, s))
    return total


def _bucket(t0: int, secs: int, now: int) -> dict:
    r = _rng("bucket", t0, secs)
    covered = max(1, min(now, t0 + secs) - t0)          # partial current bucket
    mins = covered / 60
    inc = _overlap(t0, t0 + covered, INCIDENT) / covered
    atk = _overlap(t0, t0 + covered, ATTACK) / covered
    events = 900 * _daily(t0 + secs / 2) * mins * (1 + r.uniform(-0.04, 0.04))
    errors = events * (0.011 + 0.002 * r.random() + 0.09 * inc)
    fails = mins * (1.6 * (0.5 + _daily(t0)) + r.uniform(-0.4, 0.4) + 38 * atk)
    return {"t": t0, "events": round(events), "errors": round(errors), "fails": max(0, round(fails)), "inc": inc}


def _buckets(start: int, end: int, secs: int):
    t = start - start % secs
    while t < end:
        yield _bucket(t, secs, end)
        t += secs


class DemoProvider:
    mode = "demo"

    def __init__(self, now_fn=None):
        import time
        self._now = now_fn or time.time

    def health(self) -> dict:
        return {"connected": True, "version": "demo data", "server": "built-in sample", "host": "local"}

    # ---- aggregates -------------------------------------------------------------
    def _agg_secs(self, start, end):
        d = end - start
        return 60 if d <= 3600 else 300 if d <= 86400 else 3600

    def kpis(self, start, end):
        bs = list(_buckets(start, end, self._agg_secs(start, end)))
        events = sum(b["events"] for b in bs)
        errors = sum(b["errors"] for b in bs)
        inc = sum(b["inc"] for b in bs) / max(1, len(bs))
        r = _rng("p95", start // 300, end - start)
        return {
            "events": events, "errors": errors,
            "error_rate": errors / events * 100 if events else 0.0,
            "p95": 238 + 900 * inc * 6 + r.uniform(-8, 8),
            "hosts": len(HOSTS),
            "failed_logins": sum(b["fails"] for b in bs),
        }

    def timeseries(self, start, end, span_secs):
        bs = list(_buckets(start, end, span_secs))
        return {"t": [b["t"] * 1000 for b in bs], "events": [b["events"] for b in bs],
                "errors": [b["errors"] for b in bs]}

    def logins(self, start, end, span_secs):
        bs = list(_buckets(start, end, span_secs))
        return {"t": [b["t"] * 1000 for b in bs], "failures": [b["fails"] for b in bs]}

    def endpoints(self, start, end):
        frac = _overlap(start, end, INCIDENT) / max(1, end - start)
        total = self.kpis(start, end)["events"]
        out = []
        for name, svc, base in ENDPOINTS:
            r = _rng("ep", name, start // 600)
            p95 = base * (1 + 2.5 * min(1, frac * 6)) * (1 + r.uniform(-0.05, 0.05))
            out.append({"endpoint": name, "p95": p95, "avg": p95 * 0.42,
                        "count": total * SERVICES[svc] / 2})
        return sorted(out, key=lambda e: -e["p95"])

    def services(self, start, end):
        frac = _overlap(start, end, INCIDENT) / max(1, end - start)
        total = self.kpis(start, end)["events"]
        out = []
        for svc, share in SERVICES.items():
            rate = 0.011 + (0.09 * frac if svc in ("payments", "checkout", "auth") else 0.012 * frac)
            ev = total * share
            out.append({"service": svc, "events": ev, "errors": ev * rate, "error_rate": rate * 100})
        return sorted(out, key=lambda s: -s["errors"])

    def errors(self, start, end):
        rows, _ = self._events(start, end, 400, level="ERROR")
        return [{"time": int(datetime.fromisoformat(e["_time"]).timestamp() * 1000), "service": e["service"],
                 "host": e["host"], "message": e["message"]} for e in rows[:12]]

    # ---- events & ad-hoc search ---------------------------------------------------
    def _events(self, start, end, limit, level=None, security=False):
        out, t = [], end - end % 600
        while t > start and len(out) < limit * 3 and t > end - 7 * 86400:
            r = _rng("ev", t, security)
            inc = _overlap(t, t + 600, INCIDENT) / 600
            atk = _overlap(t, t + 600, ATTACK) / 600
            for _ in range(3 + (6 if (atk if security else inc) else 0)):
                ts = min(end, t + r.randint(0, 599))
                if ts < start:
                    continue
                iso = datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")
                if security:
                    fail = r.random() < 0.3 + 0.6 * atk
                    out.append({"_time": iso, "action": "failure" if fail else "success",
                                "user": r.choice(USERS), "src_ip": f"10.{r.randint(0, 9)}.{r.randint(0, 255)}.{r.randint(1, 254)}",
                                "reason": r.choice(["bad_password", "unknown_user", "mfa_failed"]) if fail else "ok"})
                    continue
                roll = r.random()
                lvl = "ERROR" if roll < 0.05 + 0.5 * inc else "WARN" if roll < 0.16 + 0.5 * inc else "INFO"
                ep, svc, base = r.choice(ENDPOINTS)
                msg = r.choice({"ERROR": ERROR_MSGS, "WARN": WARN_MSGS, "INFO": INFO_MSGS}[lvl])
                out.append({
                    "_time": iso, "level": lvl, "service": svc, "host": r.choice(HOSTS), "endpoint": ep,
                    "status": r.choice([500, 502, 503, 504]) if lvl == "ERROR" else r.choice([200, 429]) if lvl == "WARN" else r.choice([200, 201, 304]),
                    "response_time": r.randint(800, 5000) if lvl == "ERROR" else r.randint(20, int(base * 1.2)),
                    "user": r.choice(USERS), "message": msg,
                })
            t -= 600
        out = [e for e in out if (not level or e.get("level") == level)]
        out.sort(key=lambda e: e["_time"], reverse=True)
        return out[:limit], None

    def search(self, spl, start, end, limit=1000):
        parts = [p.strip() for p in spl.split("|")]
        head, tail = parts[0], parts[1:]
        head = re.sub(r"^search\s+", "", head, flags=re.I)
        filters, words, security = [], [], False
        for m in re.finditer(r'([\w.]+)\s*(!=|=)\s*("[^"]*"|\S+)|"([^"]*)"|(\S+)', head):
            if m.group(1):
                key, op, val = m.group(1), m.group(2), m.group(3).strip('"')
                if key == "index":
                    security = val.lower() == "security"
                elif key not in ("earliest", "latest"):
                    filters.append((key, op, val))
            else:
                w = (m.group(4) or m.group(5)).strip()
                if w.upper() not in ("AND", "OR", "NOT", ""):
                    words.append(w.lower())
        events, _ = self._events(start, end, 600, security=security)

        def keep(e):
            for key, op, val in filters:
                hit = fnmatch.fnmatch(str(e.get(key, "")).lower(), val.lower())
                if hit != (op == "="):
                    return False
            blob = " ".join(map(str, e.values())).lower()
            return all(w in blob for w in words)

        rows = [e for e in events if keep(e)]
        for cmd in tail:
            m = re.match(r"head\s+(\d+)", cmd, re.I)
            if m:
                rows = rows[: int(m.group(1))]
            m = re.match(r"stats\s+count(?:\s+as\s+(\w+))?\s+by\s+([\w.]+)", cmd, re.I)
            if m:
                name, field = m.group(1) or "count", m.group(2)
                counts: dict = {}
                for e in rows:
                    counts[e.get(field, "")] = counts.get(e.get(field, ""), 0) + 1
                rows = [{field: k, name: v} for k, v in sorted(counts.items(), key=lambda kv: -kv[1])]
        note = "Demo data. Filters, bare words, `| head N` and `| stats count by field` are supported."
        return rows[:limit], note
