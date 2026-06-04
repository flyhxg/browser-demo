"""Integration tests for terminal-mode queue and idle-timer behavior.

Verifies AgentRunner's command queue, idle-timer lifecycle, and cancel
behavior. The heavy `run()` is replaced with a no-op so the queue plumbing
and `_idle_wait` can be tested in isolation.
"""
import asyncio
from collections import deque
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.agent_runner import AgentRunner


@pytest.fixture
def runner(monkeypatch):
    """Fresh AgentRunner with run() stubbed out so the queue is reachable."""
    r = AgentRunner()
    monkeypatch.setattr(r, "run", AsyncMock(return_value=None))
    return r


@pytest.mark.asyncio
async def test_enqueue_appends_and_dispatches_when_idle(runner):
    assert not runner.running
    await runner.enqueue("first command")
    await asyncio.sleep(0)
    assert runner._command_queue == deque()
    assert runner.run.await_count == 1


@pytest.mark.asyncio
async def test_enqueue_respects_max_size(runner):
    runner._queue_max_size = 2
    fake_ws = AsyncMock()
    runner.set_ws(fake_ws)
    # Pre-fill the queue by enqueueing 2 then quickly cancelling before they drain
    runner._command_queue.append("a")
    runner._command_queue.append("b")
    await runner.enqueue("c")
    assert len(runner._command_queue) == 2
    assert any(
        call.kwargs.get("type") == "error" or
        (call.args and isinstance(call.args[0], dict) and call.args[0].get("type") == "error")
        for call in fake_ws.send_json.call_args_list
    ), "expected queue-full error over WebSocket"


@pytest.mark.asyncio
async def test_enqueue_sends_queue_status(runner):
    fake_ws = AsyncMock()
    runner.set_ws(fake_ws)
    runner._command_queue.append("a")
    runner._command_queue.append("b")
    await runner.enqueue("c")
    queue_status_calls = [
        call for call in fake_ws.send_json.call_args_list
        if call.args and isinstance(call.args[0], dict)
        and call.args[0].get("type") == "queue_status"
    ]
    assert queue_status_calls, "expected queue_status event after enqueue"


@pytest.mark.asyncio
async def test_cancel_clears_queue_and_timer(runner):
    await runner.enqueue("a")
    await runner.enqueue("b")
    runner._idle_timer = asyncio.create_task(asyncio.sleep(60))
    await runner.cancel()
    assert runner._command_queue == deque()
    assert runner._idle_timer is None


@pytest.mark.asyncio
async def test_idle_wait_closes_browser_session(monkeypatch):
    """The 5-minute idle timer must close the BrowserSession to free cloud resources."""
    r = AgentRunner()
    r._idle_timeout = 0.02  # 20ms for test
    fake_session = AsyncMock()
    r._browser_session = fake_session
    fake_ws = AsyncMock()
    r.set_ws(fake_ws)
    await r._idle_wait()
    fake_session.close.assert_awaited_once()
    assert r._browser_session is None
    queue_status_calls = [
        call for call in fake_ws.send_json.call_args_list
        if call.args and isinstance(call.args[0], dict)
        and call.args[0].get("type") == "queue_status"
    ]
    assert queue_status_calls, "expected queue_status 0 after idle close"


@pytest.mark.asyncio
async def test_cancel_cancels_idle_timer(monkeypatch):
    r = AgentRunner()
    r._idle_timeout = 60
    r._idle_timer = asyncio.create_task(asyncio.sleep(60))
    await r.cancel()
    assert r._idle_timer is None
    assert r._command_queue == deque()
