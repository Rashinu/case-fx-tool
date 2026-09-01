from __future__ import annotations

import httpx

from tests.conftest import frankfurter_response, running_client


def test_happy_path_same_day_rate():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/2026-08-28"
        assert request.url.params["base"] == "EUR"
        assert request.url.params["symbols"] == "TRY"
        return frankfurter_response("EUR", "TRY", 47.1234, "2026-08-28")

    with running_client(handler) as client:
        resp = client.get(
            "/tools/convert", params={"amount": "250", "from": "EUR", "to": "TRY", "date": "2026-08-28"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body == {
            "amount": 250.0,
            "from": "EUR",
            "to": "TRY",
            "rate": 47.1234,
            "result": 11780.85,
            "rate_date": "2026-08-28",
            "asked_date": "2026-08-28",
            "source": "ECB via frankfurter.dev",
        }


def test_weekend_falls_back_to_the_nearest_earlier_published_date():
    # Asked for a Saturday; the upstream (like the real Frankfurter API)
    # resolves it to the preceding Friday and says so in "date". rate_date
    # must reflect that, and must differ from asked_date.
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/2026-08-29"
        return frankfurter_response("EUR", "TRY", 47.0, "2026-08-28")

    with running_client(handler) as client:
        resp = client.get(
            "/tools/convert", params={"amount": "10", "from": "EUR", "to": "TRY", "date": "2026-08-29"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["asked_date"] == "2026-08-29"
        assert body["rate_date"] == "2026-08-28"
        assert body["rate_date"] != body["asked_date"]


def test_future_date_is_rejected_without_calling_upstream():
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    with running_client(handler) as client:
        resp = client.get(
            "/tools/convert", params={"amount": "10", "from": "EUR", "to": "TRY", "date": "2099-01-01"}
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "future_date"
        assert called is False


def test_date_before_series_start_is_rejected():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("upstream should not be called")

    with running_client(handler) as client:
        resp = client.get(
            "/tools/convert", params={"amount": "10", "from": "EUR", "to": "TRY", "date": "1990-01-01"}
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "date_before_series"


def test_malformed_date_is_rejected():
    with running_client(lambda r: httpx.Response(200, json={})) as client:
        resp = client.get(
            "/tools/convert", params={"amount": "10", "from": "EUR", "to": "TRY", "date": "28-08-2026"}
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "invalid_date"


def test_malformed_currency_code_is_rejected_without_calling_upstream():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("upstream should not be called")

    with running_client(handler) as client:
        resp = client.get("/tools/convert", params={"amount": "10", "from": "EU", "to": "TRY"})
        assert resp.status_code == 400
        assert resp.json()["error"] == "invalid_currency"


def test_currency_unknown_to_upstream_is_reported_as_invalid_currency():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "not found"})

    with running_client(handler) as client:
        resp = client.get("/tools/convert", params={"amount": "10", "from": "EUR", "to": "ZZZ"})
        assert resp.status_code == 400
        assert resp.json()["error"] == "invalid_currency"


def test_identical_currencies_short_circuit_without_calling_upstream():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("upstream should not be called")

    with running_client(handler) as client:
        resp = client.get(
            "/tools/convert", params={"amount": "10", "from": "eur", "to": "EUR", "date": "2026-08-28"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["rate"] == 1.0
        assert body["result"] == 10.0
        assert body["rate_date"] == "2026-08-28"


def test_upstream_timeout_is_reported_not_swallowed():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    with running_client(handler) as client:
        resp = client.get("/tools/convert", params={"amount": "10", "from": "EUR", "to": "TRY"})
        assert resp.status_code == 502
        assert resp.json()["error"] == "upstream_unavailable"


def test_upstream_connection_error_is_reported_not_swallowed():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with running_client(handler) as client:
        resp = client.get("/tools/convert", params={"amount": "10", "from": "EUR", "to": "TRY"})
        assert resp.status_code == 502
        assert resp.json()["error"] == "upstream_unavailable"


def test_upstream_500_is_reported_not_swallowed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    with running_client(handler) as client:
        resp = client.get("/tools/convert", params={"amount": "10", "from": "EUR", "to": "TRY"})
        assert resp.status_code == 502
        assert resp.json()["error"] == "upstream_error"


def test_upstream_non_json_is_reported_not_swallowed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")

    with running_client(handler) as client:
        resp = client.get("/tools/convert", params={"amount": "10", "from": "EUR", "to": "TRY"})
        assert resp.status_code == 502
        assert resp.json()["error"] == "upstream_error"


def test_missing_amount_is_a_clean_400_not_a_framework_422():
    with running_client(lambda r: httpx.Response(200, json={})) as client:
        resp = client.get("/tools/convert", params={"from": "EUR", "to": "TRY"})
        assert resp.status_code == 400
        assert resp.json()["error"] == "invalid_request"


def test_zero_amount_is_rejected():
    with running_client(lambda r: httpx.Response(200, json={})) as client:
        resp = client.get("/tools/convert", params={"amount": "0", "from": "EUR", "to": "TRY"})
        assert resp.status_code == 400
        assert resp.json()["error"] == "invalid_amount"


def test_negative_amount_is_rejected():
    with running_client(lambda r: httpx.Response(200, json={})) as client:
        resp = client.get("/tools/convert", params={"amount": "-5", "from": "EUR", "to": "TRY"})
        assert resp.status_code == 400
        assert resp.json()["error"] == "invalid_amount"


def test_non_numeric_amount_is_rejected():
    with running_client(lambda r: httpx.Response(200, json={})) as client:
        resp = client.get("/tools/convert", params={"amount": "abc", "from": "EUR", "to": "TRY"})
        assert resp.status_code == 400
        assert resp.json()["error"] == "invalid_amount"


def test_excessive_decimal_places_are_rejected():
    with running_client(lambda r: httpx.Response(200, json={})) as client:
        resp = client.get(
            "/tools/convert", params={"amount": "1.1234567890", "from": "EUR", "to": "TRY"}
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "invalid_amount"


def test_repeat_query_is_served_from_cache_not_reasked():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return frankfurter_response("EUR", "TRY", 47.1234, "2026-08-28")

    with running_client(handler) as client:
        params = {"amount": "250", "from": "EUR", "to": "TRY", "date": "2026-08-28"}
        first = client.get("/tools/convert", params=params)
        second = client.get("/tools/convert", params=params)
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json() == second.json()
        assert len(calls) == 1


def test_health_endpoint():
    with running_client(lambda r: httpx.Response(200, json={})) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
