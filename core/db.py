"""SQLite persistence (issue #10).

One file, three tables, JSON blobs for the model bodies. Every write is an
idempotent upsert so re-running the pipeline over the same data never
duplicates rows -- during a hackathon the pipeline gets re-run constantly.

Upsert keys:
    raw_profiles -> (platform, handle)
    persons      -> person.id
    scores       -> person_id
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from core.schema import Person, RawProfile, Scores

DEFAULT_DB_PATH = Path("db.sqlite")

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_profiles (
    platform   TEXT NOT NULL,
    handle     TEXT NOT NULL,
    fetched_at TEXT,
    body       TEXT NOT NULL,
    PRIMARY KEY (platform, handle)
);

CREATE TABLE IF NOT EXISTS persons (
    id   TEXT PRIMARY KEY,
    body TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scores (
    person_id TEXT PRIMARY KEY,
    composite REAL,
    body      TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: str | Path = DEFAULT_DB_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.executescript(SCHEMA)
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- writes ---------------------------------------------------------

    def upsert_raw_profiles(self, profiles: Iterable[RawProfile]) -> int:
        rows = [
            (p.platform, p.handle, p.fetched_at, json.dumps(p.to_dict()))
            for p in profiles
        ]
        self.connection.executemany(
            """
            INSERT INTO raw_profiles (platform, handle, fetched_at, body)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (platform, handle) DO UPDATE SET
                fetched_at = excluded.fetched_at,
                body       = excluded.body
            """,
            rows,
        )
        self.connection.commit()
        return len(rows)

    def upsert_persons(self, persons: Iterable[Person]) -> int:
        rows = [(p.id, json.dumps(p.to_dict())) for p in persons]
        self.connection.executemany(
            """
            INSERT INTO persons (id, body) VALUES (?, ?)
            ON CONFLICT (id) DO UPDATE SET body = excluded.body
            """,
            rows,
        )
        self.connection.commit()
        return len(rows)

    def upsert_scores(self, scores: Iterable[Scores]) -> int:
        rows = [(s.person_id, s.composite, json.dumps(s.to_dict())) for s in scores]
        self.connection.executemany(
            """
            INSERT INTO scores (person_id, composite, body) VALUES (?, ?, ?)
            ON CONFLICT (person_id) DO UPDATE SET
                composite = excluded.composite,
                body      = excluded.body
            """,
            rows,
        )
        self.connection.commit()
        return len(rows)

    # -- reads ----------------------------------------------------------

    def all_raw_profiles(self) -> list[RawProfile]:
        rows = self.connection.execute(
            "SELECT body FROM raw_profiles ORDER BY platform, handle"
        ).fetchall()
        return [RawProfile.from_dict(json.loads(body)) for (body,) in rows]

    def all_persons(self) -> list[Person]:
        rows = self.connection.execute(
            "SELECT body FROM persons ORDER BY id"
        ).fetchall()
        return [Person.from_dict(json.loads(body)) for (body,) in rows]

    def all_scores(self) -> list[Scores]:
        rows = self.connection.execute(
            "SELECT body FROM scores ORDER BY composite DESC NULLS LAST, person_id"
        ).fetchall()
        return [Scores.from_dict(json.loads(body)) for (body,) in rows]
