import os
import tempfile
import pytest
from pathlib import Path


@pytest.fixture
def isolated_config(monkeypatch):
    """Point config_store at a temp file so tests don't clobber the real one."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    tmp.write("{}")
    tmp.close()
    monkeypatch.setattr("services.config_store.CONFIG_PATH", Path(tmp.name))
    yield Path(tmp.name)
    os.unlink(tmp.name)


def test_arkham_key_round_trip(isolated_config):
    from services import config_store

    config_store.update_config({"arkham_api_key": "test-key-1234"})

    loaded = config_store.get_config()
    assert loaded["arkham_api_key"] == "test-key-1234"


def test_arkham_key_appears_in_masked(isolated_config):
    from services import config_store

    config_store.update_config({"arkham_api_key": "test-key-1234"})

    masked = config_store.get_masked_config()
    assert masked["arkham_api_key_masked"] == "****1234"
