"""Conftest: a real-database fixture for the T017 trace store, skipped when unreachable.

Why a real database rather than a fake
--------------------------------------
Three of T017's requirements are properties of *the database*, not of Python:

* two concurrent resumes of one checkpoint must produce exactly one winner -- that is row-lock
  semantics, and an in-memory double re-implements the lock, so a test against it proves only that
  the double agrees with itself;
* ``run_id + step_index + trace_id`` must be durable and queryable;
* retention must actually shrink stored bytes.

So the store's contract tests run against PostgreSQL. When no database is reachable they **skip**
rather than fail: a missing local database is an environment fact, and a suite that goes red for it
would train people to ignore red.

Isolation
---------
Every test uses a fresh ``uuid4`` run id and deletes its own run in teardown (traces and checkpoints
cascade). Nothing here reads or writes a fixed id, so pointing this at a development database cannot
collide with demo fixtures -- and the run row is removed, so repeated runs do not accumulate.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import psycopg
import pytest

from app.trace.db import ConnectionFactory, connection_factory_from_url

#: ``127.0.0.1`` and **not** ``localhost``, measured rather than assumed. On this machine
#: ``getaddrinfo("localhost")`` returns ``::1`` first, the ``commerceagent-postgres`` container
#: publishes only ``127.0.0.1:5432``, so every connection spent the full timeout waiting on IPv6
#: before falling back to IPv4: 5.03s per connection versus 0.013s. Several connections per test
#: turned a two-second suite into minutes.
_DEFAULT_TEST_URL = "postgresql://agent_app:agent_app_dev_only@127.0.0.1:5432/commerceagent"

#: Set this to point the store tests at another database, or to a deliberately unreachable one.
TEST_DATABASE_URL_ENV = "AGENT_TRACE_TEST_DATABASE_URL"


def _database_url() -> str:
    return os.environ.get(TEST_DATABASE_URL_ENV, _DEFAULT_TEST_URL)


@pytest.fixture(scope="session")
def trace_connection_factory() -> ConnectionFactory:
    """A connection factory for a reachable ``agent``-schema database, or skip."""
    url = _database_url()
    try:
        with psycopg.connect(url, connect_timeout=3) as connection:
            with connection.cursor() as cursor:
                # The V002 columns are what these tests exercise; a database migrated only to V001
                # would fail with a confusing "column does not exist" instead of a clear skip.
                cursor.execute(
                    "SELECT version, checkpoint_compacted_at FROM agent.agent_runs LIMIT 0"
                )
                cursor.execute("SELECT 1 FROM agent.agent_checkpoints LIMIT 0")
    except psycopg.Error as exc:
        pytest.skip(f"no T017-capable database at {url!r}: {exc}")

    return connection_factory_from_url(url)


@pytest.fixture
def connection_factory(trace_connection_factory: ConnectionFactory) -> Iterator[ConnectionFactory]:
    """The same factory, exposed per test so the intent reads clearly at the call site."""
    yield trace_connection_factory
