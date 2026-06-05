"""Toggle the Polymarket scheduler end-to-end and screenshot the result."""
import asyncio
import sys
import io
from playwright.async_api import async_playwright

# Force utf-8 stdout so emoji in button labels don't crash on Windows gbk.
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await ctx.new_page()
        page.on("pageerror", lambda e: print(f"  [page error] {e}"))
        page.on(
            "console",
            lambda m: print(f"  [console.{m.type}] {m.text}") if m.type in ("error", "warning") else None,
        )

        await page.goto("http://localhost:5173/workflow", wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_selector(".task-card", timeout=10000)
        await asyncio.sleep(2)

        poly_card = page.locator(".task-card", has_text="Polymarket")
        poly_btn = poly_card.locator("button.btn-primary")
        before_label = (await poly_btn.text_content()).strip()
        before_status = (await poly_card.locator(".task-status-badge").text_content()).strip()
        print(f">>> Before: button='{before_label}'  status='{before_status}'")

        # Click "Enable & Start"
        await poly_btn.click()
        await asyncio.sleep(2)

        after_start_label = (await poly_btn.text_content()).strip()
        after_start_status = (await poly_card.locator(".task-status-badge").text_content()).strip()
        print(f">>> After 1st click: button='{after_start_label}'  status='{after_start_status}'")

        # Now click again (should toggle to Pause)
        await poly_btn.click()
        await asyncio.sleep(2)

        after_pause_label = (await poly_btn.text_content()).strip()
        after_pause_status = (await poly_card.locator(".task-status-badge").text_content()).strip()
        print(f">>> After 2nd click: button='{after_pause_label}'  status='{after_pause_status}'")

        await page.screenshot(path="D:/work/browser-demo/_verify_workflow_poly_toggle.png", full_page=True)
        print("Screenshot saved: _verify_workflow_poly_toggle.png")

        await browser.close()


asyncio.run(main())
