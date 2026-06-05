"""Verify the Workflow page renders two scheduler cards."""
import asyncio
from playwright.async_api import async_playwright


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
        await asyncio.sleep(2)  # let poll land

        data = await page.evaluate("""
() => {
  const cards = Array.from(document.querySelectorAll('.task-card'));
  return {
    cardCount: cards.length,
    names: cards.map(c => c.querySelector('.task-name')?.textContent || ''),
    statuses: cards.map(c => c.querySelector('.task-status-badge')?.textContent?.trim() || ''),
    intervals: cards.map(c => c.querySelectorAll('.metric-value')[0]?.textContent?.trim() || ''),
    helpText: document.querySelector('.help-card')?.innerText || '',
  };
}
""")
        print("=== Workflow page ===")
        for k, v in data.items():
            print(f"  {k}: {v}")

        await page.screenshot(path="D:/work/browser-demo/_verify_workflow_multi.png", full_page=True)
        print("Screenshot saved: _verify_workflow_multi.png")

        await browser.close()


asyncio.run(main())
