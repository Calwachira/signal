"""SPL used by live mode. Edit these to match your own data.

Expected fields in the app index: level, service, host, endpoint, response_time, message.
Expected fields in the security index: action (success|failure).
"""

KPIS_APP = (
    "index={app} | stats count AS events "
    'count(eval(level="ERROR")) AS errors '
    "perc95(response_time) AS p95 dc(host) AS hosts"
)
KPIS_SEC = "index={sec} action=failure | stats count AS failed_logins"

TIMESERIES = (
    "index={app} | timechart span={span} count AS events "
    'count(eval(level="ERROR")) AS errors'
)
LOGINS = "index={sec} action=failure | timechart span={span} count AS failures"

ENDPOINTS = (
    "index={app} | stats perc95(response_time) AS p95 avg(response_time) AS avg "
    "count BY endpoint | sort - p95 | head 8"
)
SERVICES = (
    "index={app} | stats count AS events "
    'count(eval(level="ERROR")) AS errors BY service | sort - errors | head 8'
)
ERRORS = (
    "index={app} level=ERROR | head 12 | table _time service host message"
)
