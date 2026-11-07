"""In-memory attempt limits for sign-in, sign-up and password reset.

One uvicorn worker (see HANDOFF.md), so a dict is enough; it empties on restart.
"""
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

_hits: dict[tuple[str, str], deque] = defaultdict(deque)
_lock = threading.Lock()


def client_ip(request: Request) -> str:
    """The caller's IP. The API is DNS-only (not behind Cloudflare's proxy), so App Service's front end
    appends the real address, as ip:port, to the end of X-Forwarded-For."""
    fwd = request.headers.get("x-forwarded-for", "")
    ip = fwd.split(",")[-1].strip() if fwd else (request.client.host if request.client else "")
    if ip.startswith("["):
        return ip[1:ip.find("]")]
    return ip.rsplit(":", 1)[0] if ip.count(":") == 1 else ip


def _prune(q: deque, now: float, window_s: int) -> None:
    while q and q[0] <= now - window_s:
        q.popleft()


def check(bucket: str, key: str, limit: int, window_s: int) -> None:
    """429 once `key` has `limit` attempts in the last `window_s` seconds."""
    now = time.monotonic()
    with _lock:
        q = _hits[(bucket, key)]
        _prune(q, now, window_s)
        if len(q) >= limit:
            mins = max(1, round((q[0] + window_s - now) / 60))
            raise HTTPException(429, f"Too many attempts. Try again in {mins} min.")


def hit(bucket: str, key: str, limit: int, window_s: int) -> None:
    """check(), then count this attempt. For limits on failures only, check() first and hit() on failure."""
    check(bucket, key, limit, window_s)
    with _lock:
        _hits[(bucket, key)].append(time.monotonic())


def reset() -> None:
    with _lock:
        _hits.clear()
