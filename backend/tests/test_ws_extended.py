import pytest
from unittest.mock import AsyncMock, patch
from api.ws import websocket_endpoint

def test_ws_imports():
    from api import ws
    assert hasattr(ws, "websocket_endpoint")
