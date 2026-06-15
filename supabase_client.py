import os
from pathlib import Path

# load .env if present
try:
    from dotenv import load_dotenv
    base_dir = Path(__file__).resolve().parent
    for env_path in (base_dir / ".env", base_dir / "models" / ".env"):
        if env_path.exists():
            load_dotenv(env_path)
    # fallback to system env
    load_dotenv()
except Exception:
    pass
import uuid
from datetime import datetime
from typing import Any, Dict
from urllib.parse import urlsplit, urlunsplit

try:
    import httpx
    from supabase import ClientOptions, create_client
except Exception:  # pragma: no cover - client optional at import time
    ClientOptions = None
    create_client = None
    httpx = None


def normalize_supabase_url(url: str | None) -> str | None:
    if not url:
        return None

    parts = urlsplit(url.strip())
    path = parts.path.rstrip("/")
    if path.endswith("/rest/v1"):
        path = path[: -len("/rest/v1")]
    return urlunsplit((parts.scheme, parts.netloc, path, "", "")).rstrip("/")


SUPABASE_URL = normalize_supabase_url(os.getenv("SUPABASE_URL"))
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY")
_supabase = None
_IGNORED_PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")


def clear_broken_local_proxy_env() -> None:
    """Ignore placeholder local proxies that make outgoing API calls fail."""
    for name in _IGNORED_PROXY_VARS:
        value = os.environ.get(name)
        if value and "127.0.0.1:9" in value:
            os.environ.pop(name, None)
            os.environ.pop(name.lower(), None)


def get_supabase_client():
    global _supabase
    if _supabase is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            return None
        if create_client is None or ClientOptions is None or httpx is None:
            return None
        clear_broken_local_proxy_env()
        options = ClientOptions(httpx_client=httpx.Client(trust_env=False))
        _supabase = create_client(SUPABASE_URL, SUPABASE_KEY, options)
    return _supabase


def insert_inspection(record: Dict[str, Any]) -> Dict[str, Any]:
    """Insert an inspection record into the `inspections` table in Supabase.

    The function will add `id` and `created_at` if missing. Raises RuntimeError
    when client is not configured.
    """
    client = get_supabase_client()
    if client is None:
        raise RuntimeError("Supabase client not configured. Set SUPABASE_URL and SUPABASE_KEY.")

    payload = dict(record)
    payload.setdefault("id", str(uuid.uuid4()))
    payload.setdefault("created_at", datetime.utcnow().isoformat())

    # Insert and return result (may raise on network errors)
    res = client.table("inspections").insert(payload).execute()
    # Some client versions return dict-like, others return an object with .data/.error
    try:
        return {"data": res.data, "error": getattr(res, "error", None)}
    except Exception:
        return {"data": res, "error": None}


def fetch_inspections(limit: int = 50) -> list[Dict[str, Any]]:
    """Fetch recent inspection records for report generation."""
    client = get_supabase_client()
    if client is None:
        raise RuntimeError("Supabase client not configured. Set SUPABASE_URL and SUPABASE_KEY.")

    res = (
        client.table("inspections")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return list(getattr(res, "data", []) or [])
