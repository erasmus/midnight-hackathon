"""Core data models (spec §3).

Three models flow through the pipeline:

    RawProfile  -- one platform profile, as fetched by an adapter
    Person      -- one human, after identity resolution merged their profiles
    Scores      -- the ranking output for a Person

All three round-trip to/from plain dicts so they can be stored in SQLite
JSON columns without a separate serialisation layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

# Flags a Person can be tagged with during scoring. Kept closed so a typo in an
# adapter shows up immediately instead of silently disabling a filter.
KNOWN_FLAGS = frozenset(
    {
        "age_unknown",
        "single_source",
        "already_founder",
        "no_contact",
        "stale_data",
    }
)


@dataclass
class RawProfile:
    """A single platform profile, exactly as the adapter saw it."""

    platform: str
    handle: str
    display_name: str | None = None
    url: str | None = None
    rating: float | None = None
    rank_pct: float | None = None
    rating_history: list[dict[str, Any]] = field(default_factory=list)
    profile_links: list[str] = field(default_factory=list)
    country: str | None = None
    birth_year: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    fetched_at: str | None = None

    @property
    def key(self) -> tuple[str, str]:
        """Upsert key: one row per (platform, handle)."""
        return (self.platform, self.handle)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RawProfile":
        return cls(**data)


@dataclass
class Person:
    """One human, possibly assembled from several platform profiles."""

    id: str
    display_name: str | None = None
    birth_year: int | None = None
    country: str | None = None
    profiles: list[RawProfile] = field(default_factory=list)
    # Resolved off-platform links, e.g. {"github": "...", "linkedin": "..."}.
    links: dict[str, str] = field(default_factory=dict)
    # Human-readable justification for every resolved link. Required: a link we
    # cannot explain is a link we must not show a judge.
    evidence: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.links and not self.evidence:
            raise ValueError(
                f"Person {self.id!r} has resolved links {sorted(self.links)} "
                "but no evidence; every resolved link must be justified."
            )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["profiles"] = [p.to_dict() for p in self.profiles]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Person":
        data = dict(data)
        data["profiles"] = [RawProfile.from_dict(p) for p in data.get("profiles", [])]
        return cls(**data)


@dataclass
class Scores:
    """Ranking output for one Person (spec §5)."""

    person_id: str
    outlierness: float | None = None
    trajectory: float | None = None
    addressability: float | None = None
    composite: float | None = None
    flags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        unknown = [f for f in self.flags if f not in KNOWN_FLAGS]
        if unknown:
            raise ValueError(
                f"Unknown score flags {unknown}; known flags are {sorted(KNOWN_FLAGS)}."
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Scores":
        return cls(**data)
