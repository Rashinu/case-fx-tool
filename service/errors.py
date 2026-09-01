"""The one error shape the whole service is allowed to return.

Every failure path — validation, upstream, unexpected — turns into a
ConversionError before it reaches the client, so the response body is always
{"error": "<code>", "message": "<sentence>"} and never a stack trace or a
framework-shaped 422.
"""

from __future__ import annotations


class ConversionError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def invalid_request(message: str) -> ConversionError:
    return ConversionError("invalid_request", message, 400)


def invalid_amount(message: str) -> ConversionError:
    return ConversionError("invalid_amount", message, 400)


def invalid_currency(message: str) -> ConversionError:
    return ConversionError("invalid_currency", message, 400)


def invalid_date(message: str) -> ConversionError:
    return ConversionError("invalid_date", message, 400)


def future_date(message: str) -> ConversionError:
    return ConversionError("future_date", message, 400)


def date_before_series(message: str) -> ConversionError:
    return ConversionError("date_before_series", message, 400)


def upstream_unavailable(message: str) -> ConversionError:
    return ConversionError("upstream_unavailable", message, 502)


def upstream_error(message: str) -> ConversionError:
    return ConversionError("upstream_error", message, 502)
