import pytest
from services.session import SessionManager


@pytest.mark.asyncio
async def test_create_session():
    sm = SessionManager()
    session = await sm.create_session()
    assert "id" in session
    assert session["id"]


@pytest.mark.asyncio
async def test_add_and_get_messages():
    sm = SessionManager()
    session = await sm.create_session()
    sid = session["id"]
    await sm.add_message(sid, "user", "Hello")
    await sm.add_message(sid, "assistant", "Hi there")
    messages = await sm.get_messages(sid)
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
