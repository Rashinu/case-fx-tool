# Notes

## Decisions

When the ECB published no rate for the asked date (weekends/holidays), I
don't do a second, separate "fetch latest instead" call — I just ask
upstream for exactly the date requested and read the `"date"` field it
returns. Frankfurter already resolves weekends/holidays to the nearest
earlier published date on its own, so trusting its own answer instead of
re-deriving it avoids the exact bug I found in `tool.py`'s Part B: a
`rate_date` that doesn't correspond to the `rate` actually returned. Future
dates and dates before the ECB series start (1999-01-04) are rejected
before any upstream call, since those aren't "no rate yet," they're "no
rate ever going to exist for what was asked." `from == to` is answered
directly as a 1:1 conversion without an upstream call — a customer asking
"convert 100 USD to USD" deserves a sensible answer, not an error, and no
ECB rate is needed to know that.

## With another day

I'd add a currency allow-list (fetched once from `/v1/currencies`) so an
unrecognized code fails fast with a specific message instead of relying on
upstream's 4xx/404 shape, which I only confirmed empirically against the
real API rather than a documented contract. I'd also make the "latest"
cache TTL configurable and add a structured log line per request (currency
pair, asked vs. resolved date, cache hit/miss) — useful for spotting
exactly the kind of date-mislabeling bug from Part B in production before a
customer does.

## AI tools

Claude Code, throughout — writing the service, the test suite, and running
`tool.py` locally to verify Part B's findings against real HTTP responses
rather than guessing from reading the source.

## One thing the AI got wrong

Nothing in the implementation itself came out wrong on the first pass — but
I didn't trust my assumptions about how Frankfurter actually behaves on
weekends or with an omitted `symbols` currency, so before writing the mocked
tests I ran real requests against `https://api.frankfurter.dev` (a Saturday
date, an unknown currency, `EUR→EUR`) and read the actual JSON back. That's
what the tests' fake-upstream responses in `tests/conftest.py` are modeled
on, rather than a guess. The same instinct — verify against the real thing
before trusting the read — is what surfaced every finding in `REVIEW.md`:
each one is backed by an actual `curl` against `tool.py` running live, not
just a read of the source.
