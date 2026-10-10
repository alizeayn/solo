"""Schema migrations.

The MVP has so far only made **additive** schema changes, which
``Base.metadata.create_all`` handles on its own. This module exists so that a
change which *isn't* additive has somewhere correct to live, and so an
installation can report which schema version it is on.

Design:

* ``schema_meta`` holds a single row with the current version.
* ``SCHEMA_VERSION`` is the version this build expects.
* ``MIGRATIONS`` maps a target version to the statements that reach it.
* ``migrate()`` creates missing tables, applies any pending statements in order,
  and records the new version — reporting what it did so the updater can print
  it.

A migration that fails raises, leaving the recorded version untouched so the
next start retries rather than believing it succeeded.
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from .models import Base

logger = logging.getLogger(__name__)

#: Increment when a change cannot be expressed by ``create_all`` alone.
SCHEMA_VERSION = 1

#: ``{target_version: [SQL statement, ...]}``. Applied in ascending order.
#: Statements must be idempotent where practical, because a partially applied
#: migration is retried.
MIGRATIONS: dict[int, list[str]] = {}


async def current_version(engine: AsyncEngine) -> int:
    """Return the recorded schema version (``0`` when never recorded)."""
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_meta ("
                "  id INTEGER PRIMARY KEY CHECK (id = 1),"
                "  version INTEGER NOT NULL,"
                "  updated_at TEXT NOT NULL"
                ")"
            )
        )
        result = await connection.execute(text("SELECT version FROM schema_meta WHERE id = 1"))
        row = result.first()
    return int(row[0]) if row else 0


async def _record(engine: AsyncEngine, version: int) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO schema_meta (id, version, updated_at) "
                "VALUES (1, :version, :now) "
                "ON CONFLICT(id) DO UPDATE SET version = :version, updated_at = :now"
            ),
            {"version": version, "now": _now()},
        )


async def migrate(engine: AsyncEngine) -> dict[str, object]:
    """Bring the database up to :data:`SCHEMA_VERSION`.

    Returns a report: ``from``, ``to``, ``applied`` (the versions stepped
    through) and ``created`` (whether tables were created).
    """
    from_version = await current_version(engine)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    applied: list[int] = []
    for version in sorted(MIGRATIONS):
        if version <= from_version:
            continue
        for statement in MIGRATIONS[version]:
            async with engine.begin() as connection:
                await connection.execute(text(statement))
        applied.append(version)
        logger.info("applied schema migration to version %d", version)

    target = max([SCHEMA_VERSION, *applied])
    if from_version != target:
        await _record(engine, target)

    return {
        "from": from_version,
        "to": target,
        "applied": applied,
        "created": from_version == 0,
    }


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
