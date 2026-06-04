"""Pytest configuration — initialise the real DB before any test runs."""
import pytest

from services.database import init_db


@pytest.fixture(autouse=True)
def _init_db():
    """Ensure migrations run before every test (in-process SQLite file)."""
    init_db()