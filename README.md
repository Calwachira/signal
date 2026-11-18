# Signalboard

A clean, modern analytics app for Splunk: live dashboards, a search workspace with CSV export,
anomaly detection, and an alert inbox fed by Splunk webhooks.

It starts in **demo mode** with built-in sample data, so you can see everything working before
connecting Splunk.

## Run it (2 minutes)

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

Open http://localhost:8000. Docker works too: `cp .env.example .env && docker compose up --build`.

## Connect to Splunk

1. `cp .env.example .env`
2. Create a token in Splunk (Settings > Tokens) and set:
   ```
   SPLUNK_MODE=live
   SPLUNK_HOST=your-splunk-host
   SPLUNK_TOKEN=...
   INDEX_APP=app_logs
   INDEX_SECURITY=security
   ```
3. Restart. The sidebar shows "Splunk connected" when the REST API (port 8089) is reachable.

The dashboards expect these fields. If yours differ, edit `app/queries.py`; it is the only file
with SPL in it.

| Index | Fields |
|---|---|
| app index | `level` (INFO/WARN/ERROR), `service`, `host`, `endpoint`, `response_time` (ms), `message` |
| security index | `action` (`success` or `failure`) |

Give the Splunk user/token read access to those indexes only. Searches typed on the Search page
run with that account's permissions.

## Alerts

In a Splunk saved search, add the **Webhook** alert action pointing at
`http://<this-app>/api/webhooks/splunk`. Add `| eval severity="high"` to control severity
(`critical`, `high`, `medium`, `low`). Repeats of an unresolved alert within 15 minutes are
merged into one entry. Set `WEBHOOK_SECRET` and send it in an `X-Webhook-Secret` header if
the app is reachable from outside your network.

```bash
curl -X POST localhost:8000/api/webhooks/splunk -H "Content-Type: application/json" \
  -d '{"search_name":"Test alert","result":{"severity":"high","summary":"Hello"}}'
```

## What's inside

```
app/
  main.py           FastAPI routes (also serves the UI; API docs at /api/docs)
  splunk_client.py  Splunk REST client + live data provider
  queries.py        All SPL used by the dashboards
  demo.py           Sample-data provider (no Splunk needed)
  analytics.py      Caching, parallel queries, period comparison, anomaly detection
  alerts.py         Alert inbox with de-duplication
  guard.py          Blocks write/exec SPL commands from the Search page
static/             Dependency-free frontend (HTML, CSS, ES modules, SVG charts)
tests/              pytest suite
```

Run the tests with `pip install -r requirements-dev.txt && pytest`.

## Before production

- **Authentication:** the app has none. Put it behind your SSO/reverse proxy (or add a FastAPI
  auth dependency) before exposing it. Anyone who can open it can run searches as the Splunk account.
- **Alert storage:** alerts live in memory and reset on restart. Swap `AlertStore` for a
  database if you need history.
- **Search guard:** `app/guard.py` blocks commands such as `delete`, `outputlookup`, `script`
  and `rest`. Your Splunk role should also be read-only.
- **Scaling:** results are cached for `CACHE_TTL` seconds per time range. For many users, use a
  shared cache (Redis) and Splunk data-model acceleration.
- **Demo-mode search** supports filters, bare words, `| head N` and `| stats count by field`
  only. Live mode accepts full SPL.
- **Live mode is untested against a real Splunk server** (none was available while building).
  Check the queries in `app/queries.py` against your data first.
