"""Database connectivity for the Agent trace store (``agent`` schema, owner: this service).

Why this module is thin
-----------------------
It wraps :mod:`psycopg` in exactly two decisions, and nothing else, so the SQL in
:mod:`app.trace.store` stays readable:

* **A connection factory, injected rather than imported.** The store never calls
  ``psycopg.connect`` itself, so tests can point it at a real database without monkey-patching a
  module global, and a test double can be substituted without the store knowing. Java analogy: this
  is the ``DataSource`` that gets injected, not a static ``DriverManager.getConnection`` buried in a
  DAO.
* **``dict_row`` rows.** ``cursor.fetchone()[7]`` is a bug waiting for a column to be inserted; the
  SQL in this package is long enough that positional access would eventually read ``retry_count``
  where it meant ``step_count``.

Transaction control belongs to the caller, not here. ``autocommit=False`` is the default and the
store opens transactions explicitly: a checkpoint write and the run-row update it belongs to have to
commit *together*, and a connection that silently autocommitted would let the two drift apart --
exactly the "row says COMPLETED, payload says RUNNING" failure ``data-model.md`` section 12 forbids.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.rows import dict_row

__all__ = ["ConnectionFactory", "connect", "connection_factory_from_url", "transaction"]

#: Callable that yields a new connection. Injected into the store.
ConnectionFactory = Callable[[], "psycopg.Connection[dict[str, Any]]"]


def connect(database_url: str, *, connect_timeout_seconds: int = 5) -> psycopg.Connection[Any]:
    """Open one connection with the row factory and timeouts this package expects.

    The connect timeout is explicitly bounded: an unreachable database must fail the health path in
    seconds, not hold a worker until the OS gives up. ``dialect`` options are left at their defaults
    because every statement in this package is plain SQL.
    """
    return psycopg.connect(
        database_url,
        row_factory=dict_row,
        connect_timeout=connect_timeout_seconds,
        autocommit=False,
    )


def connection_factory_from_url(database_url: str) -> ConnectionFactory:
    """Build the factory the store wants from a connection string."""

    def factory() -> psycopg.Connection[Any]:
        return connect(database_url)

    return factory


@contextmanager
def transaction(connection: psycopg.Connection[Any]) -> Iterator[psycopg.Cursor[Any]]:
    """Run a block in one transaction, committing on success and rolling back on any exception.

    ``with connection.transaction()`` would do the same; this wrapper exists so the store reads as a
    sequence of SQL statements with one visible transaction boundary, and so a caller cannot forget
    it by using the bare connection.
    """
    with connection.transaction():
        with connection.cursor() as cursor:
            yield cursor
