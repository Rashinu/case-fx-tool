# Review of tool.py

One page. Findings **ranked**, most harmful to a customer first. Every
finding below was reproduced by running `tool.py` against the real
frankfurter.dev API and reading the actual response — not just the source.

## 1. Every failure returns a normal-looking `200` with a fabricated `0`

`convert()` wraps the whole request in `try/except Exception`, and on *any*
failure — invalid currency, a KeyError from a missing rate, upstream down —
it returns `rate: 0.0, result: 0.0` with a `200` status, `print()`-ing the
real error to a log the customer never sees.

**Customer impact:** the calling agent cannot tell "this conversion is
worth zero" from "this conversion failed." It has no signal to fall back or
apologize — it will confidently tell the customer their money is worth
nothing. This is the exact failure mode the brief warns about, except
inverted: it's not "no number," it's a *wrong* number with a success status.

**Verified:**
```
GET /tools/convert?amount=100&from_=EUR&to=ZZZ
→ 200 {"amount":100.0,"from":"EUR","to":"ZZZ","rate":0.0,"result":0.0,"rate_date":"2026-09-01",...}
```

## 2. The documented `from` and `date` query parameters silently do nothing

The handler's parameters are named `from_` and `on`, with no `alias=`. A
caller following the API as specified — `?from=USD&date=2020-01-01` — binds
to *neither* of them; both silently fall back to their defaults (`EUR`,
"latest"). No error, no validation error, just the wrong currency and the
wrong date, returned as if they were what was asked for.

**Customer impact:** every real caller using the contract this service
claims to expose gets an answer for a completely different conversion than
the one they asked for, with no indication anything went wrong.

**Verified:**
```
GET /tools/convert?amount=100&from=USD&to=TRY
→ 200 {"amount":100.0,"from":"EUR","to":"TRY",...}   # from=USD was ignored
```

## 3. `rate_date` is never read from the upstream response — it's just echoed back

`fetch_rate` returns `str(on or date.today())` as the "date the rate
belongs to" on *every* path, including a fresh, successful fetch. The
payload's own `"date"` field (which is exactly what the brief says to read)
is never looked at. Combined with a cache keyed only on `(base, target)` —
not the date — this means: ask for a rate on 2020-01-01 (gets cached under
`EUR-TRY`), then ask for "latest," and you get the 2020 rate back, silently
labeled with today's date.

**Customer impact:** this is the one thing the brief says must never
happen — a rate presented as belonging to a date it does not belong to —
and it happens on the very first weekend/holiday request (the fallback to
`/latest` keeps the originally-asked date) and on every cache hit after
that.

**Verified:**
```
GET /tools/convert?amount=100&from_=EUR&to=TRY&on=2020-01-01
→ rate 55.95, rate_date "2020-01-01"
GET /tools/convert?amount=100&from_=EUR&to=TRY        (no date → "latest")
→ rate 55.95 (same, stale, 2020 value), rate_date "2026-09-01"  (today — wrong)
```

## The one I would fix before shipping tonight

**#1, the blanket `except Exception → 200 with rate 0`.** It's the
highest-blast-radius bug — it converts every other failure (including #2 and
#3's symptoms, and anything not yet found) into a confident, wrong,
`200 OK` answer. Removing it alone would turn today's silent-zero responses
into visible errors, which is the single change that most directly serves
"a wrong number is worse than no number."

## Things that look suspicious but are fine

- The in-process cache having no TTL/eviction looked worrying at first, but
  for a case-study-scale service that's a reasonable simplification, not a
  defect — the real problem is what it's keyed on (see #3), not that it
  never expires.
- `httpx.AsyncClient()` is created with no explicit timeout, which looks
  unbounded — but httpx defaults to a 5-second timeout on all operations, so
  a hung upstream doesn't hang the request indefinitely. Worth making
  explicit, but not a bug.
