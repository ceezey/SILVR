"""Shared fixtures: a throwaway Postgres schema per test."""

import os
import uuid
from urllib.parse import quote

import psycopg
import pytest

DEFAULT_TEST_DATABASE_URL = "postgresql://silvr:silvr@localhost:5432/silvr"


@pytest.fixture
def database_url():
    """Yield a Postgres URL whose search_path is a fresh schema, dropped after the test.

    Fails instead of skipping when Postgres is unreachable, so storage and risk-state
    tests can never pass silently.
    """

    base = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
    schema = f"test_{uuid.uuid4().hex[:12]}"
    try:
        with psycopg.connect(base, autocommit=True) as connection:
            connection.execute(f"CREATE SCHEMA {schema}")
    except psycopg.OperationalError as exc:
        pytest.fail(f"Postgres unreachable at TEST_DATABASE_URL ({exc}); start it: docker compose up -d postgres")
    separator = "&" if "?" in base else "?"
    yield f"{base}{separator}options={quote(f'-csearch_path={schema}')}"
    with psycopg.connect(base, autocommit=True) as connection:
        connection.execute(f"DROP SCHEMA {schema} CASCADE")


@pytest.fixture
def fast_connect_timeout(monkeypatch):
    """Unreachable-database tests: Windows waits out the whole timeout on a refused port."""

    import silvr.monitoring.status as status
    import silvr.storage.postgres as postgres

    monkeypatch.setattr(postgres, "CONNECT_TIMEOUT_SECONDS", 1)
    monkeypatch.setattr(status, "CONNECT_TIMEOUT_SECONDS", 1)


def execute(database_url: str, sql: str, params: tuple = ()) -> None:
    """Run one statement and commit; tests use it to write rows the bot would not."""

    with psycopg.connect(database_url) as connection:
        connection.execute(sql, params)
