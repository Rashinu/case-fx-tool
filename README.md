# fx-tool

A small HTTP service with one endpoint, meant to be called by an AI agent
that needs to answer "how much is X in Y". It's a thin wrapper around the
ECB reference rates published at [frankfurter.dev](https://frankfurter.dev).

I spent most of the time on the part that isn't the HTTP plumbing: what the
service should do when the answer isn't clean — a weekend with no published
rate, a date that hasn't happened yet, an upstream that's down or lying.
Details on that below.

## Running it

```bash
./run.sh
```

It listens on `$PORT` (default `8080`) and reads the upstream base URL from
`$FX_UPSTREAM_BASE` (default `https://api.frankfurter.dev`). Nothing in the
code hardcodes the real host, so pointing that env var somewhere else is
enough to run this against a different upstream — including a fake one.

Try it:

```bash
curl "http://localhost:8080/tools/convert?amount=250&from=EUR&to=TRY&date=2026-08-28"
```

## Testing it

```bash
./test.sh
```

The whole suite runs with no network access at all. Every upstream call in
the tests is answered by a mocked `httpx` transport rather than a real
request, so `FX_UPSTREAM_BASE` can point at a closed port and everything
still passes — that's exactly how I understand this gets graded.

## The endpoint

```
GET /tools/convert?amount=250&from=EUR&to=TRY&date=2026-08-28
```

`amount` and both currency codes are required. `date` is optional
(`YYYY-MM-DD`) — leave it out and you get the latest available rate.
`amount` has to be a positive decimal, and I cap it at 6 fractional digits;
that's already more precision than any real currency's subunit uses, so
anything past that looks like a mistake on the caller's side rather than a
number I should just round away.

A successful call looks like this:

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

The two dates are the whole point of this exercise: `asked_date` is what
was requested (or today, if `date` was left out), and `rate_date` is the
date the `rate` actually belongs to. They won't always match, and when they
don't, that's the service telling you the rate you got is not from today —
which is exactly the information a customer needs before trusting the
number.

Anything that isn't a 2xx comes back as:

```json
{ "error": "<code>", "message": "<a sentence, not a stack trace>" }
```

## Error codes

| code | status | when |
|---|---|---|
| `invalid_request` | 400 | a required query parameter is missing |
| `invalid_amount` | 400 | missing, not a number, `<= 0`, or more than 6 decimal places |
| `invalid_currency` | 400 | not a 3-letter code, or the upstream doesn't recognize it |
| `invalid_date` | 400 | not `YYYY-MM-DD` |
| `future_date` | 400 | after today — there's no rate for it yet |
| `date_before_series` | 400 | before `1999-01-04`, where the ECB series starts |
| `upstream_unavailable` | 502 | upstream timed out or the connection failed |
| `upstream_error` | 502 | upstream returned a 5xx, or something that wasn't JSON |
| `internal_error` | 500 | anything I didn't anticipate — logged, never turned into a rate |

## How I handled the tricky cases

**No rate published for the date asked (weekend/holiday).** I ask upstream
for exactly the date requested, nothing more. Frankfurter already resolves
weekends and holidays to the nearest earlier published date on its own, and
tells you which date it actually used in its response — so I just read that
field and report it as `rate_date`, instead of writing my own fallback
logic. I deliberately did *not* build a second "if missing, re-ask for
latest" step, because that's exactly the pattern that goes wrong in
practice: it's very easy to fetch a fallback rate and forget to update the
date you report alongside it, and you end up presenting someone else's
rate as if it were the one they asked for.

**A date in the future, or before the series starts.** Rejected outright,
before any upstream call — `future_date` or `date_before_series`. These
aren't "no rate yet" situations, they're "this will never exist."

**An unknown currency code, or `from` equal to `to`.** An unrecognized code
is rejected as `invalid_currency` — I check the shape first (three letters)
and then trust whatever the upstream itself rejects. Same currency on both
sides isn't an error, though: I answer it directly as a 1:1 conversion
without calling upstream at all, since no ECB rate is needed to know 1 EUR
is worth 1 EUR.

**Upstream is slow, returns a 500, or returns something that isn't JSON.**
All three get caught explicitly and turned into `upstream_unavailable` or
`upstream_error`. None of them fall through to a made-up number — if I
can't get a real rate for a real date, the response says so instead of
guessing.

**A bad amount** — missing, not a number, zero, negative, or absurdly
precise — is rejected before any of this even starts.

## Caching

Rates are kept in memory, keyed by currency pair and the date asked for
(or `"latest"`). A rate for a specific past date is cached forever, since
once the ECB has published it, it doesn't change. `"latest"` is only kept
for 15 minutes, so a burst of repeat questions doesn't hit upstream again
and again, but a process that stays up for days still picks up each new
day's rate.

## What I left out on purpose

Auth, a database, a UI, a Dockerfile, CI, deployment, extra endpoints.
None of it was asked for, and I'd rather this one endpoint be something I
can stand behind than pad the repo with things nobody will look at.
