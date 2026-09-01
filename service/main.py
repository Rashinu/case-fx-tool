"""The FastAPI app: one endpoint, one error shape.

Wiring only — parsing lives in validation.py, upstream I/O in upstream.py.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import date as date_type
from decimal import ROUND_HALF_UP, Decimal

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from service.config import upstream_base
from service.errors import ConversionError
from service.upstream import RateCache, fetch_rate
from service.validation import parse_amount, parse_currency, parse_date

logger = logging.getLogger("fx-tool")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient(base_url=upstream_base(), timeout=5.0)
    app.state.cache = RateCache()
    try:
        yield
    finally:
        await app.state.http_client.aclose()


app = FastAPI(title="fx-tool", version="1.0", lifespan=lifespan)


@app.exception_handler(ConversionError)
async def handle_conversion_error(request: Request, exc: ConversionError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.code, "message": exc.message})


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    field = errors[0]["loc"][-1] if errors and errors[0].get("loc") else "request"
    return JSONResponse(
        status_code=400,
        content={"error": "invalid_request", "message": f"missing or invalid parameter: '{field}'"},
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    # Anything that reaches here is a bug, not a validated business case.
    # We log it and tell the caller nothing usable happened — we do not
    # return a rate, ever, on an error path.
    logger.exception("unhandled error converting request")
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "message": "something went wrong on our side"},
    )


@app.get("/tools/convert")
async def convert(
    request: Request,
    amount: str = Query(...),
    from_: str = Query(..., alias="from"),
    to: str = Query(...),
    date: str | None = Query(None),
) -> dict:
    """Convert an amount from one currency to another using ECB reference rates.

    amount: decimal string, > 0, at most 6 fractional digits.
    from / to: 3-letter ISO-4217-shaped currency codes.
    date: optional YYYY-MM-DD; omitted means "latest available".
    """
    http_client: httpx.AsyncClient = request.app.state.http_client
    cache: RateCache = request.app.state.cache

    amount_dec = parse_amount(amount)
    base = parse_currency(from_, "from")
    target = parse_currency(to, "to")
    today = date_type.today()
    requested = parse_date(date, today)

    if base == target:
        # Trivial and correct without consulting upstream at all: 1 EUR is
        # always worth 1 EUR, on every date, published or not.
        rate = Decimal(1)
        rate_date = requested or today
    else:
        rate, rate_date = await fetch_rate(http_client, cache, base, target, requested)

    result = (amount_dec * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    asked_date = requested or today

    return {
        "amount": float(amount_dec),
        "from": base,
        "to": target,
        "rate": float(rate),
        "result": float(result),
        "rate_date": rate_date.isoformat(),
        "asked_date": asked_date.isoformat(),
        "source": "ECB via frankfurter.dev",
    }


@app.get("/health")
async def health() -> dict:
    return {"ok": True}
