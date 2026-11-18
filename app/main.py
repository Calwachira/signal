from __future__ import annotations

import hmac
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import guard
from .alerts import AlertStore
from .analytics import RANGES, Analytics
from .config import get_settings
from .demo import DemoProvider
from .splunk_client import LiveProvider, SplunkError

settings = get_settings()
provider = LiveProvider(settings) if settings.mode == "live" else DemoProvider()
analytics = Analytics(provider, ttl=settings.cache_ttl)
alerts = AlertStore()
if settings.mode != "live":
    alerts.seed_demo()

app = FastAPI(title="Signalboard", version="1.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json")


class SearchRequest(BaseModel):
    query: str = Field(..., max_length=guard.MAX_LENGTH)
    range: str = "24h"


class StatusRequest(BaseModel):
    status: str


def _upstream(exc: Exception) -> HTTPException:
    return HTTPException(status_code=502, detail=str(exc))


@app.get("/api/health")
def health():
    info = provider.health()
    return {"status": "ok" if info.get("connected") else "degraded", "mode": provider.mode,
            "ranges": list(RANGES), "splunk": info}


@app.get("/api/overview")
def overview(range: str = Query("24h")):
    try:
        return analytics.overview(range)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except SplunkError as exc:
        raise _upstream(exc)


@app.post("/api/search")
def search(req: SearchRequest):
    try:
        spl = guard.check(req.query)
        return analytics.search(spl, req.range)
    except (guard.UnsafeQuery, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except SplunkError as exc:
        raise _upstream(exc)


@app.get("/api/alerts")
def list_alerts(status: str | None = None):
    return {"alerts": alerts.list(status), "counts": alerts.counts()}


@app.post("/api/alerts/{alert_id}/status")
def update_alert(alert_id: int, body: StatusRequest):
    try:
        return alerts.set_status(alert_id, body.status)
    except KeyError:
        raise HTTPException(status_code=404, detail="Alert not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/webhooks/splunk")
def splunk_webhook(payload: dict, x_webhook_secret: str = Header(default="")):
    """Receives Splunk alert-action webhooks.

    Splunk sends {"sid", "search_name", "results_link", "result": {...}}. Add a `severity`
    field to the search results (e.g. `| eval severity="high"`) to control the level.
    """
    if settings.webhook_secret and not hmac.compare_digest(x_webhook_secret, settings.webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")
    result = payload.get("result") or {}
    name = payload.get("search_name") or "Splunk alert"
    summary = result.get("summary") or ", ".join(f"{k}={v}" for k, v in list(result.items())[:4])
    return alerts.add(name, str(result.get("severity", "medium")).lower(), summary,
                      link=payload.get("results_link"))


STATIC = Path(__file__).resolve().parent.parent / "static"


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/", StaticFiles(directory=STATIC), name="static")
