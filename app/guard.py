"""Safety checks for ad-hoc SPL typed into the Search page."""
import re

# Commands that write data, run code, or reach outside the search layer.
BLOCKED = (
    "delete", "outputlookup", "outputcsv", "collect", "mcollect", "meventcollect",
    "sendemail", "sendalert", "script", "run", "rest", "dbxquery", "tscollect",
)
_PATTERN = re.compile(r"[|\[]\s*(" + "|".join(BLOCKED) + r")\b", re.IGNORECASE)
MAX_LENGTH = 4000


class UnsafeQuery(ValueError):
    pass


def check(spl: str) -> str:
    spl = (spl or "").strip()
    if not spl:
        raise UnsafeQuery("Enter a search to run.")
    if len(spl) > MAX_LENGTH:
        raise UnsafeQuery(f"Search is too long (limit {MAX_LENGTH} characters).")
    match = _PATTERN.search(spl)
    if match:
        raise UnsafeQuery(f"The '{match.group(1).lower()}' command isn't allowed from this app.")
    return spl
