"""Proves PUBLIC_BASE_URL lands on this process before a call is started.

The engine calls the proxy over the public internet, so PUBLIC_BASE_URL is a tunnel, and
a tunnel is the one piece of the deployment nothing in this repo controls. On 2026-09-03
the configured ngrok domain was forwarding to a different machine running the same code:
that backend answered every turn with a 200 and the fallback line, this backend logged
nothing, and the prospect heard "give me one moment" for five minutes. curl said the
tunnel was up, because it was — just not to here.

So /health carries a per-process instance id and /start-call fetches it through the
public URL. Anything but this process's own id is a refused call, which is a one-line
error in the console instead of a call whose every turn goes to the wrong machine.
"""
import logging
import secrets
import time
from urllib.parse import urlparse

import httpx

log = logging.getLogger("pitchpilot.selfcheck")

INSTANCE_ID = secrets.token_hex(8)
CACHE_S = 60.0          # a passing check is good for a minute of calls
TIMEOUT_S = 6.0         # a tunnel slower than this would fail the call's turns anyway

_cache: dict[str, float] = {}   # base_url -> time of last pass
# One client for the life of the process. Built per check, every cache miss paid a fresh
# TLS handshake to the tunnel — 387 ms against 71 ms on a warm connection — and that sat
# directly in front of the caller's button. Reuse changes nothing about what is verified.
_client: httpx.AsyncClient | None = None


def _shared() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=TIMEOUT_S,
                                    headers={"ngrok-skip-browser-warning": "1"})
    return _client


def is_loopback(base_url: str) -> bool:
    host = (urlparse(base_url).hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "::1")


async def verify(base_url: str, transport: httpx.AsyncBaseTransport | None = None) -> str | None:
    """None if the public URL reaches this process; otherwise a sentence saying what it
    reached instead. Loopback is skipped: it never reaches the engine either, but it is
    what text-mode runs and the test suite use, and they are not calls."""
    if is_loopback(base_url):
        log.warning("PUBLIC_BASE_URL is %s: the engine cannot reach localhost, so live "
                    "calls will fail every turn until it points at a tunnel", base_url)
        return None
    if time.monotonic() - _cache.get(base_url, -1e9) < CACHE_S:
        return None

    url = f"{base_url.rstrip('/')}/health"
    try:
        if transport is not None:   # the suite injects one; it must not touch the shared client
            async with httpx.AsyncClient(timeout=TIMEOUT_S, transport=transport,
                                         headers={"ngrok-skip-browser-warning": "1"}) as client:
                r = await client.get(url)
        else:
            r = await _shared().get(url)
    except httpx.HTTPError as exc:
        return f"cannot reach PUBLIC_BASE_URL ({url}): {exc!r}"

    try:
        body = r.json()
    except ValueError:
        body = None
    if r.status_code != 200 or not isinstance(body, dict):
        return (f"PUBLIC_BASE_URL ({url}) answered {r.status_code} with something that is "
                f"not this backend's /health: {r.text[:120]!r}")
    if body.get("instance") != INSTANCE_ID:
        return (f"PUBLIC_BASE_URL ({url}) reaches another backend (instance "
                f"{body.get('instance')!r}, this one is {INSTANCE_ID!r}). The tunnel is "
                f"forwarding to a different machine or process.")

    _cache[base_url] = time.monotonic()
    return None
