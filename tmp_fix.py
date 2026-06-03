import re

# Read file
with open('D:/work/browser-demo/backend/services/agent_runner.py', 'r', encoding='utf-8') as f:
    content = f.read()

# The pattern to find
old_section = '''        # Emit live_url if cloud mode (cdp_url is now available after get_or_create_cdp_session)
        if browser_use_api_key:
            cdp = str(browser_session.cdp_url)
            live_url = f"https://live.browser-use.com/?wss={quote(cdp, safe='')}"  # type: ignore[arg-type]
            from api.ws import send_live_url  # type: ignore[import-not-at-top-of-file]
            if self._ws:
                await send_live_url(self._ws, live_url)

        async def step_callback(browser_state, agent_output, step_number):
            action_desc = ""
            target_desc = ""'''

# The replacement
new_section = '''        # Emit live_url if cloud mode - sent inside step_callback when cdp_url is actually available
        _live_url_sent = False

        async def step_callback(browser_state, agent_output, step_number):
            # Emit live_url on first step when cloud mode and cdp_url is available
            nonlocal _live_url_sent
            if browser_use_api_key and not _live_url_sent and self._ws:
                cdp_url = browser_session.cdp_url
                if cdp_url:
                    live_url = f"https://live.browser-use.com/?wss={quote(str(cdp_url), safe='')}"  # type: ignore[arg-type]
                    from api.ws import send_live_url  # type: ignore[import-not-at-top-of-file]
                    await send_live_url(self._ws, live_url)
                    _live_url_sent = True

            action_desc = ""
            target_desc = ""'''

# Check if old_section exists
if old_section in content:
    content = content.replace(old_section, new_section)
    with open('D:/work/browser-demo/backend/services/agent_runner.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Successfully updated agent_runner.py")
else:
    print("Could not find the section to replace. Lines around 233:")
    lines = content.split('\n')
    for i in range(230, 245):
        if i < len(lines):
            print(f"{i+1}: {lines[i]}")
