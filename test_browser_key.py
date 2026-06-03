"""Test getting cdp_url from Agent after creation."""
import asyncio
import os
from browser_use import Agent, BrowserSession
from browser_use.llm.messages import UserMessage
from browser_use import ChatAnthropic

async def test():
    api_key = "bu_9dQgNL9oBd1xM8RhsUzGC7ipwx1bT3-bHY3shLLUeNk"
    os.environ["BROWSER_USE_API_KEY"] = api_key

    session = BrowserSession(cloud_browser=True, use_cloud=True)
    await session.start()
    print(f"cdp_url: {session.cdp_url}")

    # Check if Agent exposes cdp_url
    llm = ChatAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", "test"))
    agent = Agent(
        task="go to example.com and tell me the title",
        llm=llm,
        browser_session=session,
        use_thinking=False,
    )
    print(f"Agent attributes: {[a for a in dir(agent) if 'browser' in a.lower() or 'session' in a.lower() or 'cdp' in a.lower()]}")

    await session.close()

asyncio.run(test())