"""Parsing and validating the raw query strings.

Nothing here talks to the network. Everything it rejects is rejected before
we spend an upstream call on it.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from service.config import SERIES_START
from service.errors import (
    future_date,
    date_before_series,
    invalid_amount,
    invalid_currency,
    invalid_date,
)

_CURRENCY_RE = re.compile(r"^[A-Za-z]{3}$")

# Currency amounts with more than this many fractional digits are not a real
# quantity of money for any ISO-4217 currency (the most any of them use is
# 3, e.g. BHD) — beyond this it looks like a bug in the caller, so we refuse
# to guess what they meant rather than silently truncating it.
MAX_AMOUNT_DECIMALS = 6

SERIES_START_DATE = date.fromisoformat(SERIES_START)


def parse_amount(raw: str) -> Decimal:
    if raw is None or raw.strip() == "":
        raise invalid_amount("amount is required")
    try:
        amount = Decimal(raw)
    except InvalidOperation:
        raise invalid_amount(f"'{raw}' is not a number")

    if not amount.is_finite():
        raise invalid_amount("amount must be a finite number")
    if amount <= 0:
        raise invalid_amount("amount must be greater than zero")

    exponent = amount.as_tuple().exponent
    decimals = -exponent if isinstance(exponent, int) and exponent < 0 else 0
    if decimals > MAX_AMOUNT_DECIMALS:
        raise invalid_amount(
            f"amount has {decimals} decimal places; at most {MAX_AMOUNT_DECIMALS} are accepted"
        )
    return amount


def parse_currency(raw: str, field: str) -> str:
    if raw is None or not _CURRENCY_RE.match(raw):
        raise invalid_currency(f"'{raw}' is not a 3-letter currency code for '{field}'")
    return raw.upper()


def parse_date(raw: str | None, today: date) -> date | None:
    """Return the requested date, or None to mean "latest"."""
    if raw is None or raw.strip() == "":
        return None
    try:
        parsed = datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        raise invalid_date(f"'{raw}' is not a date in YYYY-MM-DD format")

    if parsed > today:
        raise future_date(f"{parsed.isoformat()} is in the future; no rate can exist for it yet")
    if parsed < SERIES_START_DATE:
        raise date_before_series(
            f"the ECB series starts on {SERIES_START}; {parsed.isoformat()} predates it"
        )
    return parsed
