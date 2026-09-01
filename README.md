# fx-tool

A small HTTP service with one endpoint an AI agent can call to convert
between currencies, backed by the ECB reference rates from
[frankfurter.dev](https://frankfurter.dev).

## Run it

```bash
./run.sh
```

Listens on `$PORT` (default `8080`). Reads the upstream base URL from
`$FX_UPSTREAM_BASE` (default `https://api.frankfurter.dev`) — the real host
is never hardcoded, so pointing that variable elsewhere is enough to run
this against a different upstream.

```bash
curl "http://localhost:8080/tools/convert?amount=250&from=EUR&to=TRY&date=2026-08-28"
```

## Test it

```bash
./test.sh
```

The whole suite runs with no network access — every upstream call is
answered by an `httpx.MockTransport`, not a real request — so it passes even
with `FX_UPSTREAM_BASE` pointing at a closed port.

## The endpoint

```
GET /tools/convert?amount=250&from=EUR&to=TRY&date=2026-08-28
```

| param | required | notes |
|---|---|---|
| `amount` | yes | decimal string, `> 0`, at most 6 fractional digits |
| `from` | yes | 3-letter currency code |
| `to` | yes | 3-letter currency code |
| `date` | no | `YYYY-MM-DD`; omitted means "latest available" |

**200** on success:

```json
{
  "amount": 250,
  "from": "EUR",
  "to": "TRY",
  "rate": 47.1234,
  "result": 11780.85,
  "rate_date": "2026-08-28",
  "asked_date": "2026-08-28",
  "source": "ECB via frankfurter.dev"
}
```

`asked_date` is what was requested (or today, if `date` was omitted).
`rate_date` is the date the `rate` actually belongs to, as reported by the
upstream. They can differ — that's not a bug, it's the answer to "is this
rate current?".

Non-2xx on failure:

```json
{ "error": "<code>", "message": "<sentence>" }
```

## Error codes and what triggers them

| code | status | when |
|---|---|---|
| `invalid_request` | 400 | a required query parameter is missing |
| `invalid_amount` | 400 | `amount` is missing, not a number, `<= 0`, or has more than 6 decimal places |
| `invalid_currency` | 400 | `from`/`to` isn't a 3-letter code, or the upstream doesn't recognize it |
| `invalid_date` | 400 | `date` isn't `YYYY-MM-DD` |
| `future_date` | 400 | `date` is after today — no rate can exist yet |
| `date_before_series` | 400 | `date` is before `1999-01-04`, when the ECB series starts |
| `upstream_unavailable` | 502 | the upstream timed out or the connection failed |
| `upstream_error` | 502 | the upstream returned a 5xx, or a response that wasn't valid JSON |
| `internal_error` | 500 | anything unexpected — logged, never returned as a rate |

## What happens in each required case

- **No rate for the date asked (weekend/holiday):** we ask upstream for
  exactly that date. Frankfurter itself resolves it to the nearest earlier
  published date and reports which date it used — we read that field and put
  it in `rate_date`, distinct from `asked_date`. We never silently re-query
  "latest" ourselves; the date came from the same upstream call, so it's
  guaranteed to correspond to the `rate` returned.
- **Future date / before the series starts:** rejected before any upstream
  call, as `future_date` / `date_before_series`.
- **Unknown currency code, or `from == to`:** an unknown code is rejected as
  `invalid_currency` (checked by shape first, then by what upstream actually
  recognizes). Identical currencies are answered directly as a 1:1
  conversion without calling upstream at all — no ECB rate is needed to know
  that 1 EUR is worth 1 EUR.
- **Upstream slow / 500 / not JSON:** each is caught and turned into
  `upstream_unavailable` or `upstream_error`. None of them produce a `rate`
  — there is no fallback path that invents one.
- **Invalid amount:** missing, non-numeric, zero, negative, or oddly precise
  (more than 6 decimal places, which is more precision than any real
  currency subunit uses) are all rejected as `invalid_amount` before any
  upstream call.

## Caching

Rates are cached in-process, keyed by `(from, to, date-or-"latest")`.
Historical (dated) rates are cached forever — once the ECB publishes a rate
for a specific past date it never changes. "latest" is cached for 15
minutes, so a burst of repeat queries doesn't re-ask upstream, but a
long-running process still picks up a new day's rate.

## Not included

Auth, a database, a UI, a Dockerfile, CI, deployment, extra endpoints — out
of scope for this task by design.
