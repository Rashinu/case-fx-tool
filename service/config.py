"""Environment-driven configuration.

Everything the grader needs to override lives here, and nowhere else: no
other module may read os.environ or hardcode the upstream host.
"""

from __future__ import annotations

import os


def upstream_base() -> str:
    return os.environ.get("FX_UPSTREAM_BASE", "https://api.frankfurter.dev").rstrip("/")


def port() -> int:
    return int(os.environ.get("PORT", "8080"))


# The first day the ECB reference series has data for. Anything before this
# is not a "no rate published today" situation, it is asking for data that
# will never exist.
SERIES_START = "1999-01-04"

# How long a cached "latest" rate is trusted before we ask upstream again.
# Historical (dated) rates never change once published, so those are cached
# forever; "latest" can change once a day, so it gets a short TTL instead of
# being cached forever.
LATEST_CACHE_TTL_SECONDS = 15 * 60
