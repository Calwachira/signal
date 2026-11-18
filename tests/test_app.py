import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ["SPLUNK_MODE"] = "demo"

from fastapi.testclient import TestClient  # noqa: E402

from app import guard  # noqa: E402
from app.analytics import flag_anomalies  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


def test_health():
    r = client.get("/api/health").json()
    assert r["status"] == "ok" and r["mode"] == "demo"


def test_overview_all_ranges():
    for rng in ("1h", "6h", "24h", "7d"):
        d = client.get(f"/api/overview?range={rng}").json()
        assert len(d["kpis"]) == 4
        assert len(d["timeseries"]["t"]) == len(d["timeseries"]["events"]) > 0
        assert d["endpoints"] and d["services"]


def test_bad_range():
    assert client.get("/api/overview?range=3y").status_code == 400


def test_search_filters_and_stats():
    r = client.post("/api/search", json={"query": "index=app_logs level=ERROR | head 5", "range": "24h"}).json()
    assert r["count"] <= 5 and all(row["level"] == "ERROR" for row in r["rows"])
    s = client.post("/api/search", json={"query": "index=app_logs | stats count by service", "range": "24h"}).json()
    assert "service" in s["columns"] and "count" in s["columns"]


def test_guard_blocks_dangerous_commands():
    for q in ("index=x | delete", "index=x | outputlookup foo.csv", "| rest /services/server/info"):
        assert client.post("/api/search", json={"query": q}).status_code == 400
    assert guard.check("index=app_logs | stats count")


def test_alert_workflow_and_dedup():
    a = client.post("/api/webhooks/splunk", json={"search_name": "Test alert", "result": {"severity": "high", "summary": "x"}}).json()
    b = client.post("/api/webhooks/splunk", json={"search_name": "Test alert", "result": {"severity": "high"}}).json()
    assert a["id"] == b["id"] and b["count"] == 2
    assert client.post(f"/api/alerts/{a['id']}/status", json={"status": "resolved"}).json()["status"] == "resolved"
    assert client.post("/api/alerts/9999/status", json={"status": "open"}).status_code == 404


def test_anomaly_detection():
    values = [10, 11, 9, 10, 12, 10, 11, 10, 60, 10]
    assert flag_anomalies(values)[8] is True
    assert not any(flag_anomalies([10, 11, 9, 10, 12, 10, 11, 10, 11, 10]))


def test_index_page_served():
    assert client.get("/").status_code == 200
