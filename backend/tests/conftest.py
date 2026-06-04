"""Pytest configuration — opt-in fixture for tests that need the real DB."""
import pytest

from services.database import init_db


@pytest.fixture
def db_init():
    """Run DB migrations + seed before a test. Use for tests that read/write
    the real SQLite DB (most FastAPI endpoint tests)."""
    init_db()