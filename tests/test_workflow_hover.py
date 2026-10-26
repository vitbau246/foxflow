"""Hover menus (a reaction bar built on hover) and get_text, in a real Camoufox.

Skipped unless the browser was fetched (python -m camoufox fetch).
"""

import asyncio

import pytest

from src.services.browser.control import ControlError, PageController
from src.services.browser.recorder import clean_steps

# Like Facebook: hovering "Like" builds the reaction bar; leaving the area removes it.
POST = """<!doctype html><html><head><title>Post</title></head><body style="padding:40px">
<p id="post">Order #4521 ships on Friday.</p>
<div id="area" style="display:inline-block;padding:10px">
  <div role="button" aria-label="Like" id="like" style="padding:8px;border:1px solid #999">Like</div>
</div>
<p id="state">none</p>
<script>
  const area = document.getElementById("area");
  let timer;
  area.addEventListener("mouseenter", () => {
    clearTimeout(timer);
    if (document.getElementById("bar")) return;
    setTimeout(() => {
      const bar = document.createElement("div");
      bar.id = "bar";
      bar.innerHTML = '<div role="button" aria-label="Love" style="display:inline-block;padding:8px">Love</div>' +
        '<div role="button" aria-label="Haha" style="display:inline-block;padding:8px">Haha</div>';
      bar.addEventListener("click", (e) => {
        document.getElementById("state").textContent = e.target.getAttribute("aria-label");
      });
      area.prepend(bar);
    }, 300);
  });
  area.addEventListener("mouseleave", () => {
    timer = setTimeout(() => document.getElementById("bar")?.remove(), 400);
  });
</script></body></html>"""


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

    async def handler(_request):
        return web.Response(text=POST, content_type="text/html")

    app = web.Application()
    app.router.add_get("/", handler)
    server = web.AppRunner(app)
    await server.setup()
    site = web.TCPSite(server, "127.0.0.1", 0)
    await site.start()
    base = f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}/"
    out = {}
    try:
        async with AsyncCamoufox(headless=True) as browser:
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto(base)
            ctrl = PageController(context)
            await ctrl.dispatch("record_start", {})
            await page.mouse.move(5, 5)
            await page.hover("#like")
            await page.wait_for_selector("[aria-label=Love]")
            await asyncio.sleep(0.3)
            await page.click("[aria-label=Love]")
            await asyncio.sleep(0.5)
            steps = clean_steps((await ctrl.dispatch("record_stop", {}))["steps"])
            out["steps"] = steps
            click = next(s for s in steps if s["action"] == "click")

            async def replay(step):
                await page.goto(base)
                # Camoufox moves the cursor like a person: on its way it may cross
                # "Like" and open the bar. Start once that is gone.
                await page.mouse.move(5, 5)
                await page.wait_for_selector("#bar", state="detached", timeout=5000)
                await asyncio.sleep(0.5)
                try:
                    await ctrl.dispatch("run_step", {"step": step, "timeout_ms": 3000})
                except ControlError as e:
                    return f"error: {e}"
                return await page.inner_text("#state")

            out["with_hover"] = await replay(click)
            out["without_hover"] = await replay({**click, "hover_selectors": []})

            get = {"action": "get_text", "selectors": ["#post"], "save_as": "order"}
            out["text"] = (await ctrl.dispatch("run_step", {"step": get, "timeout_ms": 3000}))[
                "text"
            ]
            get["value"] = r"#(\d+)"
            out["number"] = (await ctrl.dispatch("run_step", {"step": get, "timeout_ms": 3000}))[
                "text"
            ]
            try:
                get["value"] = r"refund (\d+)"
                await ctrl.dispatch("run_step", {"step": get, "timeout_ms": 1000})
            except ControlError as e:
                out["unmatched"] = str(e)
    finally:
        await server.cleanup()
    return out


def test_hover_menu_is_recorded_and_replayed():
    _camoufox()
    out = asyncio.run(_scenario())
    clicks = [s for s in out["steps"] if s["action"] == "click"]
    assert len(clicks) == 1
    assert clicks[0]["selectors"][0] == 'div[aria-label="Love"]'
    assert clicks[0]["hover_selectors"][:2] == ["#like", 'div[aria-label="Like"]']
    assert out["with_hover"] == "Love"
    assert out["without_hover"].startswith("error: Element not found")
    assert out["text"] == "Order #4521 ships on Friday."
    assert out["number"] == "4521"
    assert "does not match" in out["unmatched"]
