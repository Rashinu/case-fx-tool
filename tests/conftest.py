"""Test harness: every test runs with the real app wired to a fake upstream.

No test in this suite ever touches the network — FX_UPSTREAM_BASE can point
anywhere, including a closed port, and the suite still passes, because the
app's http client is swapped for an httpx.MockTransport before any request
is made.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Callable

import httpx
from fastapi.testclient import TestClient

from service.main import app
from service.upstream import RateCache


@contextmanager
def running_client(handler: Callable[[httpx.Request], httpx.Response]):
    """Yield a TestClient whose upstream calls are answered by `handler`."""
    with TestClient(app) as client:
        client.app.state.http_client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://upstream.invalid",
        )
        client.app.state.cache = RateCache()
        yield client


def frankfurter_response(base: str, target: str, rate: float, rate_date: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"amount": 1.0, "base": base, "date": rate_date, "rates": {target: rate}},
    )
