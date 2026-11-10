"""DuckDB fixture loaded with the shared hand-checkable experiment (see tests/fixture_data.py)."""

import duckdb
import pytest

from splitkit.db.schema import create_schema
from tests.fixture_data import ASSIGNMENTS, EVENTS


@pytest.fixture
def conn():
    con = duckdb.connect()
    create_schema(con)
    con.executemany("INSERT INTO assignments VALUES (?, ?, ?, ?)", ASSIGNMENTS)
    con.executemany("INSERT INTO events VALUES (?, ?, ?, ?, ?)", EVENTS)
    yield con
    con.close()
