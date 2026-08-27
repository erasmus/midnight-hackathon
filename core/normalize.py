"""Stage: normalize (stub -- Epic 2/3 fills this in).

Cleans adapter output into a consistent shape: trims handles, unifies country
codes, drops profiles missing a handle. Today it only does the last of those.
"""

from __future__ import annotations

from core.schema import RawProfile


def normalize(profiles: list[RawProfile]) -> list[RawProfile]:
    return [p for p in profiles if p.handle]
