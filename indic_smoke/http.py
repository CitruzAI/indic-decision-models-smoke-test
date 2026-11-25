"""HTTP helper. Inference POSTs are disabled unless the runner flips the flag.

Free GETs are allowed. This module never logs header values or key material.
"""

from __future__ import annotations

import json
import os
import http.client
import urllib.error
import urllib.request
from typing import Any

INFERENCE_POSTS_ENABLED = False

_INFERENCE_PATH_MARKERS = (
    "/api/alpha/decisions",
    "/api/v1/chat/completions",
    "/v2/systemone",
    "/v1/systemone",
)


def _is_inference_post(method: str, url: str) -> bool:
    if method.upper() != "POST":
        return False
    return any(marker in url for marker in _INFERENCE_PATH_MARKERS)


def request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    timeout: float = 60.0,
) -> tuple[int, dict[str, Any]]:
    if _is_inference_post(method, url) and not INFERENCE_POSTS_ENABLED:
        raise RuntimeError(
            f"Refusing inference POST to {url.split('?')[0]}. "
            "Pass --live and --max-usd after spend is approved."
        )
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method.upper(),
        headers={
            "Accept": "application/json",
            "User-Agent": "citruz-indic-decision-models-smoke-test/0.1",
            **({"Content-Type": "application/json"} if data is not None else {}),
            **(headers or {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            payload = json.loads(raw.decode("utf-8")) if raw else {}
            return resp.status, payload
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {"error": exc.reason}
        except json.JSONDecodeError:
            payload = {"error": "non-json error body", "status": exc.code}
        return exc.code, payload
    except (urllib.error.URLError, TimeoutError, http.client.RemoteDisconnected,
            http.client.IncompleteRead, ConnectionError, OSError) as exc:
        # Treat transport failures as a retryable 599. Never include headers.
        return 599, {"error": {"type": type(exc).__name__, "message": str(exc)[:300]}}


def env_key(name: str) -> str | None:
    """Return a key from the current process environment only. Callers must not print it."""
    value = os.environ.get(name)
    return value if value else None
