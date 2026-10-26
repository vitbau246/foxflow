"""The "Get text" offer while recording, and page conditions, in a real Camoufox.

Skipped unless the browser was fetched (python -m camoufox fetch).
"""

import asyncio

from src.services.browser.control import PageController
from src.services.browser.recorder import clean_steps
from tests.test_workflow_browser import _camoufox

SHOP = """<!doctype html><html><head><title>Shop</title></head><body style="font-size:20px">
<h1 id="name">Blue kettle</h1>
<p>Price: <span class="price">1.290.000 ₫</span></p>
<p id="stock">In stock: 7 left</p>
</body></html>"""


async def _scenario():
    from aiohttp import web
    from camoufox.async_api import AsyncCamoufox

    async def shop(_request):
        return web.Response(text=SHOP, content_type="text/html")

    app = web.Application()
    app.router.add_get("/", shop)
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
            await ctrl.dispatch("record_start", {"lang": "vi"})
            offer = page.locator("foxflow-offer")

            # Select the price with the mouse: the offer names it text1.
            box = await page.locator("span.price").bounding_box()
            y = box["y"] + box["height"] / 2
            await page.mouse.move(box["x"] + 1, y)
            await page.mouse.down()
            await page.mouse.move(box["x"] + box["width"] - 1, y, steps=5)
            await page.mouse.up()
            await offer.locator(".yes").wait_for(timeout=5000)
            title = await offer.locator("b").inner_text()
            name_field = offer.locator("input")
            await name_field.fill("price")
            await offer.locator(".yes").click()
            await offer.locator(".done").wait_for(timeout=5000)

            # Rest the mouse on the stock line for 3 s: offered, then skipped.
            stock = await page.locator("#stock").bounding_box()
            await page.mouse.move(stock["x"] + 5, stock["y"] + stock["height"] / 2, steps=3)
            await offer.locator(".no").wait_for(timeout=6000)
            await offer.locator(".no").click()

            # Rest on the heading and accept the suggested name.
            head = await page.locator("#name").bounding_box()
            await page.mouse.move(head["x"] + 5, head["y"] + head["height"] / 2, steps=3)
            await offer.locator(".yes").wait_for(timeout=6000)
            suggested = await offer.locator("input").input_value()
            await offer.locator(".yes").click()
            await asyncio.sleep(0.3)
            steps = clean_steps((await ctrl.dispatch("record_stop", {}))["steps"])

            await ctrl.dispatch("run_prepare", {})
            texts = []
            for step in steps:
                result = await ctrl.dispatch("run_step", {"step": step, "timeout_ms": 5000})
                if step["action"] == "get_text":
                    texts.append(result["text"])
            conditions = []
            for condition, value in (
                ("selector_visible", "span.price"),
                ("text_visible", "Sold out"),
                ("title_contains", "Shop"),
                ("url_contains", "/checkout"),
            ):
                step = {"action": "if", "condition": condition, "value": value}
                result = await ctrl.dispatch("run_step", {"step": step, "timeout_ms": 5000})
                conditions.append(result["result"])
            return steps, title, suggested, texts, conditions
    finally:
        await server.cleanup()


def test_get_text_offers_and_page_conditions():
    _camoufox()
    steps, title, suggested, texts, conditions = asyncio.run(_scenario())
    assert title == "Lấy text này?"
    # Only the two accepted offers became steps: the offer's own clicks are not recorded.
    assert [s["action"] for s in steps] == ["navigate", "get_text", "get_text"]
    assert [s["save_as"] for s in steps[1:]] == ["price", "text1"]
    assert suggested == "text1"
    # Text the step reads changes between runs, so no selector is made of it.
    assert not any("text-is" in sel for s in steps[1:] for sel in s["selectors"])
    assert texts == ["1.290.000 ₫", "Blue kettle"]
    assert conditions == [True, False, True, False]
