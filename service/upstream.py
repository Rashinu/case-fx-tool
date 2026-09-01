"""Talking to the ECB rate feed, and remembering what it said.

The one rule this module exists to enforce: if we cannot get a real rate for
a real date from upstream, we raise instead of returning a number. There is
no fallback path that fabricates a rate.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import httpx

from service.config import LATEST_CACHE_TTL_SECONDS
from service.errors import invalid_currency, upstream_error, upstream_unavailable


@dataclass
class CacheEntry:
    rate: Decimal
    rate_date: date
    expires_at: float | None  # None means it never expires


class RateCache:
    """A tiny in-process cache keyed by (base, target, requested-date-or-latest).

    Historical, dated rates are cached forever — once the ECB has published a
    rate for a specific past date, it does not change. "latest" gets a short
    TTL instead, since a new rate is published once a day and we do not want
    a long-running process to serve yesterday's number forever.
    """

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str, str], CacheEntry] = {}

    def get(self, base: str, target: str, requested: date | None) -> CacheEntry | None:
        entry = self._entries.get(self._key(base, target, requested))
        if entry is None:
            return None
        if entry.expires_at is not None and entry.expires_at < time.monotonic():
            return None
        return entry

    def set(
        self, base: str, target: str, requested: date | None, rate: Decimal, rate_date: date
    ) -> None:
        expires_at = (
            None if requested is not None else time.monotonic() + LATEST_CACHE_TTL_SECONDS
        )
        self._entries[self._key(base, target, requested)] = CacheEntry(rate, rate_date, expires_at)

    @staticmethod
    def _key(base: str, target: str, requested: date | None) -> tuple[str, str, str]:
        return (base, target, requested.isoformat() if requested else "latest")


async def fetch_rate(
    client: httpx.AsyncClient,
    cache: RateCache,
    base: str,
    target: str,
    requested: date | None,
) -> tuple[Decimal, date]:
    """Return (rate, the date that rate actually belongs to).

    We ask upstream for exactly the date requested (or "latest"). Frankfurter
    resolves weekends/holidays to the nearest earlier published date on its
    own and tells us which date it used via the "date" field in the payload
    — we read that field rather than assuming the date we asked for is the
    date we got, which is the whole point of separating rate_date from
    asked_date in the response.
    """
    cached = cache.get(base, target, requested)
    if cached is not None:
        return cached.rate, cached.rate_date

    path = requested.isoformat() if requested else "latest"
    try:
        response = await client.get(f"/v1/{path}", params={"base": base, "symbols": target})
    except httpx.TimeoutException as exc:
        raise upstream_unavailable("the rate provider timed out") from exc
    except httpx.RequestError as exc:
        raise upstream_unavailable("could not reach the rate provider") from exc

    if response.status_code == 404:
        raise invalid_currency(f"'{base}' or '{target}' is not a currency the rate provider knows")
    if response.status_code >= 500:
        raise upstream_error(f"the rate provider returned status {response.status_code}")
    if response.status_code >= 400:
        raise invalid_currency(
            f"the rate provider rejected '{base}'/'{target}' (status {response.status_code})"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise upstream_error("the rate provider returned a response that was not JSON") from exc

    if not isinstance(payload, dict):
        raise upstream_error("the rate provider returned an unexpected response shape")

    rates = payload.get("rates")
    date_str = payload.get("date")
    if not isinstance(rates, dict) or target not in rates or not date_str:
        raise invalid_currency(f"the rate provider has no rate from '{base}' to '{target}'")

    try:
        rate_date = date.fromisoformat(date_str)
    except ValueError as exc:
        raise upstream_error(f"the rate provider returned an unparseable date: '{date_str}'") from exc

    raw_rate = rates[target]
    try:
        rate = Decimal(str(raw_rate))
    except Exception as exc:  # defensive: upstream sent something not numeric
        raise upstream_error("the rate provider returned a rate that was not a number") from exc

    if rate <= 0:
        raise upstream_error("the rate provider returned a non-positive rate")

    cache.set(base, target, requested, rate, rate_date)
    return rate, rate_date
