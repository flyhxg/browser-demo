import pytest
from services.ws_manager import WebSocketManager


def test_ws_manager_has_analysis_event():
    manager = WebSocketManager()
    assert hasattr(manager, "broadcast")
    assert hasattr(manager, "send_analysis_short")
    assert hasattr(manager, "send_signal_new")
    assert hasattr(manager, "send_signal_analyzed")
    assert hasattr(manager, "send_trade_executed")
    assert hasattr(manager, "send_trade_closed")
