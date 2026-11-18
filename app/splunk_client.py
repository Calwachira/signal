"""Thin wrapper over the Splunk REST API (port 8089) plus the live data provider."""
from __future__ import annotations

from datetime import datetime, timezone

import requests

from . import queries
from .config import Settings


class SplunkError(RuntimeError):
    pass


class SplunkClient:
    def __init__(self, settings: Settings):
        self.s = settings
        self.http = requests.Session()
        self.http.verify = settings.verify_ssl
        if settings.token:
            self.http.headers["Authorization"] = f"Bearer {settings.token}"
        elif settings.username:
            self.http.auth = (settings.username, settings.password)

    def ping(self) -> dict:
        try:
            r = self.http.get(
                f"{self.s.base_url}/services/server/info",
                params={"output_mode": "json"}, timeout=10,
            )
            r.raise_for_status()
            info = r.json()["entry"][0]["content"]
            return {"connected": True, "version": info.get("version"), "server": info.get("serverName")}
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI as text
            return {"connected": False, "error": str(exc)}

    def search(self, spl: str, earliest: int, latest: int, max_rows: int = 1000) -> list[dict]:
        spl = spl.strip()
        if not spl.startswith(("search ", "|")):
            spl = "search " + spl
        try:
            r = self.http.post(
                f"{self.s.base_url}/services/search/jobs",
                data={
                    "search": spl, "earliest_time": earliest, "latest_time": latest,
                    "exec_mode": "oneshot", "output_mode": "json", "count": max_rows,
                },
                timeout=120,
            )
        except requests.RequestException as exc:
            raise SplunkError(f"Could not reach Splunk: {exc}") from exc
        if r.status_code >= 400:
            try:
                msg = "; ".join(m["text"] for m in r.json().get("messages", []))
            except Exception:  # noqa: BLE001
                msg = r.text[:300]
            raise SplunkError(msg or f"Splunk returned HTTP {r.status_code}")
        return r.json().get("results", [])


def _f(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _epoch(iso: str) -> int:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _span(secs: int) -> str:
    return f"{secs // 60}m" if secs < 3600 else f"{secs // 3600}h"


class LiveProvider:
    mode = "live"

    def __init__(self, settings: Settings):
        self.s = settings
        self.client = SplunkClient(settings)

    def _q(self, template: str, **kw) -> str:
        return template.format(app=self.s.index_app, sec=self.s.index_security, **kw)

    def health(self) -> dict:
        info = self.client.ping()
        info["host"] = self.s.host
        return info

    def kpis(self, start, end):
        app = self.client.search(self._q(queries.KPIS_APP), start, end)
        sec = self.client.search(self._q(queries.KPIS_SEC), start, end)
        a = app[0] if app else {}
        events, errors = _f(a.get("events")), _f(a.get("errors"))
        return {
            "events": events, "errors": errors,
            "error_rate": (errors / events * 100) if events else 0.0,
            "p95": _f(a.get("p95")), "hosts": _f(a.get("hosts")),
            "failed_logins": _f(sec[0].get("failed_logins")) if sec else 0.0,
        }

    def timeseries(self, start, end, span_secs):
        rows = self.client.search(self._q(queries.TIMESERIES, span=_span(span_secs)), start, end)
        return {
            "t": [_epoch(r["_time"]) * 1000 for r in rows],
            "events": [_f(r.get("events")) for r in rows],
            "errors": [_f(r.get("errors")) for r in rows],
        }

    def logins(self, start, end, span_secs):
        rows = self.client.search(self._q(queries.LOGINS, span=_span(span_secs)), start, end)
        return {
            "t": [_epoch(r["_time"]) * 1000 for r in rows],
            "failures": [_f(r.get("failures")) for r in rows],
        }

    def endpoints(self, start, end):
        rows = self.client.search(self._q(queries.ENDPOINTS), start, end)
        return [{"endpoint": r.get("endpoint", "?"), "p95": _f(r.get("p95")),
                 "avg": _f(r.get("avg")), "count": _f(r.get("count"))} for r in rows]

    def services(self, start, end):
        rows = self.client.search(self._q(queries.SERVICES), start, end)
        out = []
        for r in rows:
            ev, er = _f(r.get("events")), _f(r.get("errors"))
            out.append({"service": r.get("service", "?"), "events": ev, "errors": er,
                        "error_rate": (er / ev * 100) if ev else 0.0})
        return out

    def errors(self, start, end):
        rows = self.client.search(self._q(queries.ERRORS), start, end)
        return [{"time": _epoch(r["_time"]) * 1000, "service": r.get("service", ""),
                 "host": r.get("host", ""), "message": r.get("message", "")} for r in rows]

    def search(self, spl, start, end, limit=1000):
        rows = self.client.search(spl, start, end, max_rows=limit)
        clean = []
        for r in rows:
            row = {}
            for k, v in r.items():
                if k.startswith("_") and k != "_time":
                    continue
                row[k] = ", ".join(v) if isinstance(v, list) else v
            clean.append(row)
        return clean, None
