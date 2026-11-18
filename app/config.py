import os
from dataclasses import dataclass


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader so no extra dependency is needed."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    mode: str
    host: str
    port: int
    scheme: str
    token: str
    username: str
    password: str
    verify_ssl: bool
    index_app: str
    index_security: str
    cache_ttl: int
    webhook_secret: str

    @property
    def base_url(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}"


def get_settings() -> Settings:
    load_dotenv()
    return Settings(
        mode=os.getenv("SPLUNK_MODE", "demo").lower(),
        host=os.getenv("SPLUNK_HOST", "localhost"),
        port=int(os.getenv("SPLUNK_PORT", "8089")),
        scheme=os.getenv("SPLUNK_SCHEME", "https"),
        token=os.getenv("SPLUNK_TOKEN", ""),
        username=os.getenv("SPLUNK_USERNAME", ""),
        password=os.getenv("SPLUNK_PASSWORD", ""),
        verify_ssl=_bool("SPLUNK_VERIFY_SSL", True),
        index_app=os.getenv("INDEX_APP", "app_logs"),
        index_security=os.getenv("INDEX_SECURITY", "security"),
        cache_ttl=int(os.getenv("CACHE_TTL", "30")),
        webhook_secret=os.getenv("WEBHOOK_SECRET", ""),
    )
