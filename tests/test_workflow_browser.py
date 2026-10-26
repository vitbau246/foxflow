"""Record in a real Camoufox, then replay the steps and see the checks fail on purpose.

Skipped unless the browser was fetched (python -m camoufox fetch).
"""

import asyncio

import pytest

from src.services.browser.control import ControlError, PageController
from src.services.browser.recorder import clean_steps

LOGIN = """<!doctype html><html><head><title>Login</title></head><body>
<form action="/next" method="get">
  <input name="email" placeholder="Email">
  <input type="password" name="pw">
  <label><input type="checkbox" id="remember" style="opacity:0"> Remember me</label>
  <select name="country"><option value="vn">Vietnam</option><option value="us">USA</option></select>
  <button type="submit">Log in</button>
</form></body></html>"""
NEXT = (
    "<!doctype html><html><head><title>Welcome</title></head><body><h1>Welcome</h1></body></html>"
)


def _camoufox():
    pytest.importorskip("camoufox")
    from camoufox.pkgman import camoufox_path

    try:
        camoufox_path(download_if_missing=False)
    except Exception:
        pytest.skip("Camoufox not fetched (python -m camoufox fetch)")


async def _scenario():
    from aiohttp import web
    from camoufox.async_api import AsyncCamoufox

    def page(html):
        async def handler(_request):
            return web.Response(text=html, content_type="text/html")

        return handler

    app = web.Application()
    app.router.add_get("/", page(LOGIN))
    app.router.add_get("/next", page(NEXT))
    server = web.AppRunner(app)
    await server.setup()
    site = web.TCPSite(server, "127.0.0.1", 0)
    await site.start()
    base = f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}/"
    try:
        async with AsyncCamoufox(headless=True) as browser:
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto(base)
            ctrl = PageController(context)
            await ctrl.dispatch("record_start", {})
            await page.click("input[name=email]")
            await page.keyboard.type("user@example.com", delay=30)
            await page.click("input[name=pw]")
            await page.keyboard.type("secret", delay=30)
            await page.click("text=Remember me")
            await page.select_option("select", "us")
            await page.click("button")
            await page.wait_for_url("**/next**")
            await asyncio.sleep(0.5)
            steps = clean_steps((await ctrl.dispatch("record_stop", {}))["steps"])

            await ctrl.dispatch("run_prepare", {})
            for step in steps:
                await ctrl.dispatch("run_step", {"step": step, "timeout_ms": 8000})
            replayed_url = page.url

            failures = []
            for bad in (
                {"action": "click", "selectors": ["#missing"]},
                {
                    "action": "navigate",
                    "value": base,
                    "check": {"type": "text_visible", "value": "Nope"},
                },
            ):
                try:
                    await ctrl.dispatch("run_step", {"step": bad, "timeout_ms": 1500})
                except ControlError as e:
                    failures.append(str(e))
            return steps, replayed_url, failures
    finally:
        await server.cleanup()


def test_record_then_replay_with_checks():
    _camoufox()
    steps, url, failures = asyncio.run(_scenario())
    actions = [s["action"] for s in steps]
    assert actions == ["navigate", "fill", "fill", "check", "select", "click"]
    # Nothing here opens on hover: no click may come with one.
    assert not any(s.get("hover_selectors") for s in steps)
    fill = steps[1]
    assert fill["value"] == "user@example.com" and fill["selectors"][0] == 'input[name="email"]'
    assert steps[2]["sensitive"] is True
    assert "/next" in steps[-1]["expect_url"]
    assert "/next" in url and "country=us" in url
    assert failures[0].startswith("Element not found")
    assert "did not appear" in failures[1]
