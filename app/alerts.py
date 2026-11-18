"""In-memory alert inbox. Splunk alert actions POST to /api/webhooks/splunk.

Replace the dict with a database (see README) if alerts must survive restarts.
"""
from __future__ import annotations

import itertools
import threading
import time
from datetime import datetime, timezone

SEVERITIES = ("critical", "high", "medium", "low")
STATUSES = ("open", "acknowledged", "resolved")
DEDUP_WINDOW = 15 * 60


class AlertStore:
    def __init__(self):
        self._items: dict[int, dict] = {}
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def add(self, name, severity="medium", summary="", source="splunk", link=None, fingerprint=None, when=None):
        severity = severity if severity in SEVERITIES else "medium"
        fingerprint = fingerprint or name
        now = when or time.time()
        with self._lock:
            for a in self._items.values():   # collapse repeats of an unresolved alert
                if a["fingerprint"] == fingerprint and a["status"] != "resolved" and now - a["last_seen"] < DEDUP_WINDOW:
                    a["count"] += 1
                    a["last_seen"] = now
                    return dict(a)
            aid = next(self._ids)
            a = {"id": aid, "name": name, "severity": severity, "summary": summary, "source": source,
                 "link": link, "status": "open", "count": 1, "fingerprint": fingerprint,
                 "first_seen": now, "last_seen": now}
            self._items[aid] = a
            return dict(a)

    def list(self, status=None):
        with self._lock:
            items = [dict(a) for a in self._items.values() if not status or a["status"] == status]
        order = {s: i for i, s in enumerate(SEVERITIES)}
        return sorted(items, key=lambda a: (a["status"] == "resolved", order[a["severity"]], -a["last_seen"]))

    def set_status(self, aid: int, status: str):
        if status not in STATUSES:
            raise ValueError(f"Status must be one of: {', '.join(STATUSES)}")
        with self._lock:
            if aid not in self._items:
                raise KeyError(aid)
            self._items[aid]["status"] = status
            return dict(self._items[aid])

    def counts(self):
        with self._lock:
            out = {s: 0 for s in STATUSES}
            for a in self._items.values():
                out[a["status"]] += 1
            return out

    def seed_demo(self):
        now = time.time()
        rows = [
            ("Payments gateway timeouts", "critical", "Error rate on payments exceeded 8% for 10 minutes.", 14 * 60, 6),
            ("Login failures spike", "high", "Failed logins are 9x the 48-interval baseline, mostly bad_password.", 52 * 60, 3),
            ("Checkout p95 latency high", "medium", "p95 above 900 ms on /api/checkout.", 3 * 3600, 2),
            ("Disk usage on web-04", "low", "Volume /var is 86% full.", 7 * 3600, 1),
        ]
        for name, sev, summary, ago, count in rows:
            a = self.add(name, sev, summary, source="saved search", when=now - ago)
            with self._lock:
                self._items[a["id"]]["count"] = count
                self._items[a["id"]]["first_seen"] = now - ago - 600
        self.set_status(4, "acknowledged")
