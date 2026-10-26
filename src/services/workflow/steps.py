"""Run one workflow step in a profile's browser and check that it worked.

Runs in the runner process: PageController.run_step calls run_step() with the
controller's active page. A step that cannot be done or whose check does not
pass raises StepFailed; retrying and restarting are up to the caller
(services/workflow/runner.py).
"""

from __future__ import annotations

import asyncio
import contextlib
import re
from typing import Any
from urllib.parse import urlsplit

from ..browser.control import ControlError, _check_url
from .model import CONTROL_ACTIONS, MAX_VARIABLE_TEXT, Step, step_problem

# Elements that exist but are hidden (styled checkboxes, off-screen inputs) are
# used once no visible match has turned up for this long.
HIDDEN_MATCH_AFTER_S = 2.0
SETTLE_MS = 5_000


class StepFailed(ControlError):
    pass


class _Clock:
    def __init__(self, timeout_ms: int) -> None:
        self._loop = asyncio.get_running_loop()
        self._end = self._loop.time() + timeout_ms / 1000

    def left_ms(self, floor: int = 500) -> int:
        return max(floor, int((self._end - self._loop.time()) * 1000))

    def expired(self) -> bool:
        return self._loop.time() >= self._end


def same_page(actual: str, expected: str) -> bool:
    """Same site and path; the query, fragment, trailing slash and www. are ignored."""

    def key(url: str) -> tuple[str, str]:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower().removeprefix("www.")
        return host, parts.path.rstrip("/") or "/"

    return key(actual) == key(expected)


def same_text(actual: str, expected: str) -> bool:
    """Equal, or equal once a field's own formatting (spaces, dashes...) is ignored."""
    if actual == expected:
        return True

    def bare(s: str) -> str:
        return re.sub(r"[\W_]+", "", s).lower()

    return bool(bare(expected)) and bare(actual) == bare(expected)


def _short(text: str, limit: int = 80) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


async def _scope(page: Any, frame_ref: str, clock: _Clock) -> Any:
    """The page, or the frame (by name or URL prefix) the step's element lives in."""
    if not frame_ref:
        return page
    while True:
        for frame in page.frames:
            if frame is page.main_frame:
                continue
            if frame.name == frame_ref or frame.url.startswith(frame_ref):
                return frame
        if clock.expired():
            raise StepFailed(f"Frame not found: {_short(frame_ref)}")
        await asyncio.sleep(0.25)


async def find_element(scope: Any, selectors: list[str], clock: _Clock) -> tuple[Any, str]:
    """The first visible element matched by any selector, in order.

    Polls until the step's time runs out. Invalid selectors are skipped.
    """
    loop = asyncio.get_running_loop()
    started = loop.time()
    hidden: tuple[Any, str] | None = None
    while True:
        for selector in selectors:
            try:
                matches = scope.locator(selector)
                n = await matches.count()
                for i in range(min(n, 5)):
                    candidate = matches.nth(i)
                    if await candidate.is_visible():
                        return candidate, selector
                if n and hidden is None:
                    hidden = (matches.first, selector)
            except Exception:
                continue
        if hidden and loop.time() - started >= HIDDEN_MATCH_AFTER_S:
            return hidden
        if clock.expired():
            break
        await asyncio.sleep(0.25)
    more = f" (and {len(selectors) - 1} other selectors)" if len(selectors) > 1 else ""
    raise StepFailed(f"Element not found: {_short(selectors[0])}{more}")


async def _wait_until(clock: _Clock, test: Any, failure: Any) -> None:
    while True:
        if await test():
            return
        if clock.expired():
            raise StepFailed(await failure())
        await asyncio.sleep(0.25)


async def _settle(page: Any, clock: _Clock) -> None:
    with contextlib.suppress(Exception):
        await page.wait_for_load_state("domcontentloaded", timeout=min(SETTLE_MS, clock.left_ms()))


async def _field_value(element: Any) -> str:
    try:
        return await element.input_value(timeout=2_000)
    except Exception:
        return await element.inner_text(timeout=2_000)


async def _switch_tab(controller: Any, step: Step, clock: _Clock) -> Any:
    index = int(step.value)
    while True:
        pages = controller._open_pages()
        if index < len(pages):
            controller._current = pages[index]
            with contextlib.suppress(Exception):
                await pages[index].bring_to_front()
            return pages[index]
        if clock.expired():
            raise StepFailed(f"Tab {index + 1} did not open ({len(pages)} open)")
        await asyncio.sleep(0.25)


async def _act(controller: Any, page: Any, step: Step, clock: _Clock) -> dict[str, Any]:
    """Do the action. Returns facts the auto check needs."""
    action = step.action
    if action == "navigate":
        response = await page.goto(
            _check_url(step.value), wait_until="domcontentloaded", timeout=clock.left_ms()
        )
        with contextlib.suppress(Exception):
            await page.wait_for_load_state("load", timeout=min(SETTLE_MS, clock.left_ms()))
        return {"status": response.status if response else None}
    if action == "wait":
        await asyncio.sleep(int(step.value) / 1000)
        return {}
    if action == "scroll":
        x, y = (int(v) for v in step.value.split(","))
        await page.evaluate("([x, y]) => window.scrollTo(x, y)", [x, y])
        return {}
    if action == "ai" or action in CONTROL_ACTIONS:
        raise ControlError(f"{action} steps are run by FoxFlow, not by the browser")

    scope = await _scope(page, step.frame, clock)
    if step.hover_selectors:
        # Reaction bars, menus and tooltips only exist while something is hovered.
        target, _ = await find_element(scope, step.hover_selectors, clock)
        await target.hover(timeout=clock.left_ms())
        await asyncio.sleep(step.hover_ms / 1000)
    if action == "press" and not step.selectors:
        await page.keyboard.press(step.value)
        return {}
    if action == "get_text":
        return await _get_text(scope, step, clock)

    element, selector = await find_element(scope, step.selectors, clock)
    facts: dict[str, Any] = {"element": element, "selector": selector}
    if action == "click":
        await element.click(timeout=clock.left_ms())
    elif action == "hover":
        await element.hover(timeout=clock.left_ms())
    elif action == "press":
        await element.press(step.value, timeout=clock.left_ms())
    elif action == "fill":
        if step.char_delay_ms and step.value:
            await element.fill("", timeout=clock.left_ms())
            await element.press_sequentially(
                step.value, delay=step.char_delay_ms, timeout=clock.left_ms()
            )
        else:
            await element.fill(step.value, timeout=clock.left_ms())
    elif action == "select":
        facts["selected"] = await element.select_option(step.value, timeout=clock.left_ms())
    elif action in ("check", "uncheck"):
        want = action == "check"
        try:
            await element.set_checked(want, timeout=min(5_000, clock.left_ms()))
        except Exception:
            # Sites hide the real input behind a styled box; the input still works.
            await element.set_checked(want, force=True, timeout=clock.left_ms())
    return facts


async def _get_text(scope: Any, step: Step, clock: _Clock) -> dict[str, Any]:
    """The element's visible text (the page's without a selector), through the regex if any."""
    facts: dict[str, Any] = {}
    if step.selectors:
        element, facts["selector"] = await find_element(scope, step.selectors, clock)
        text = await element.inner_text(timeout=clock.left_ms())
    else:
        text = await scope.locator("body").inner_text(timeout=clock.left_ms())
    if step.value:
        match = re.search(step.value, text, re.S)
        if match is None:
            facts["unmatched"] = True
            text = ""
        else:
            text = match.group(1) if match.groups() else match.group(0)
    facts["text"] = " ".join(text.split()) if "\n" not in text else text.strip()
    facts["text"] = facts["text"][:MAX_VARIABLE_TEXT]
    return facts


async def _auto_check(page: Any, step: Step, facts: dict[str, Any], clock: _Clock) -> None:
    action = step.action
    element = facts.get("element")
    if action == "get_text":
        if facts.get("unmatched"):
            raise StepFailed(f"Check failed: the text does not match {_short(step.value, 60)}")
        if not facts.get("text"):
            raise StepFailed("Check failed: no text found")
    if action == "navigate":
        status = facts.get("status")
        if status is not None and status >= 500:
            raise StepFailed(f"Check failed: the page answered HTTP {status}")
    elif action == "fill":
        actual = await _field_value(element)
        if not same_text(actual, step.value):
            shown = "•••" if step.sensitive else _short(actual, 40)
            raise StepFailed(f"Check failed: the field holds '{shown}' instead of the typed text")
    elif action == "select":
        if not facts.get("selected"):
            raise StepFailed(f"Check failed: no option '{_short(step.value, 40)}' was selected")
    elif action in ("check", "uncheck"):
        if await element.is_checked() != (action == "check"):
            raise StepFailed(f"Check failed: the box is not {action}ed")
    if step.expect_url and action in ("navigate", "click", "press", "select", "check", "uncheck"):
        expected = step.expect_url

        async def arrived() -> bool:
            return same_page(page.url, expected)

        async def where() -> str:
            return f"Check failed: reached {_short(page.url)} instead of {_short(expected)}"

        await _wait_until(clock, arrived, where)


async def _custom_check(page: Any, scope: Any, step: Step, clock: _Clock) -> None:
    kind, value = step.check.type, step.check.value
    if kind == "url_contains":

        async def test() -> bool:
            return value in page.url

        async def failure() -> str:
            return f"Check failed: URL {_short(page.url)} does not contain '{_short(value, 40)}'"

        await _wait_until(clock, test, failure)
    elif kind == "title_contains":

        async def test() -> bool:
            return value in await page.title()

        async def failure() -> str:
            title = await page.title()
            return (
                f"Check failed: title '{_short(title, 40)}' does not contain '{_short(value, 40)}'"
            )

        await _wait_until(clock, test, failure)
    elif kind in ("selector_visible", "text_visible"):
        target = scope.locator(value) if kind == "selector_visible" else scope.get_by_text(value)
        try:
            await target.first.wait_for(state="visible", timeout=clock.left_ms())
        except Exception as e:
            what = "element" if kind == "selector_visible" else "text"
            raise StepFailed(f"Check failed: {what} '{_short(value, 60)}' did not appear") from e


async def _page_condition(page: Any, step: Step) -> bool:
    """Whether the page shows what an if / while looks for.

    Checked once, or until it holds for up to the step's own timeout.
    """
    kind, value = step.condition, step.value
    clock = _Clock(step.timeout_ms or 0)

    async def holds() -> bool:
        if kind == "url_contains":
            return value in page.url
        if kind == "title_contains":
            return value in await page.title()
        try:
            scope = await _scope(page, step.frame, _Clock(0))
        except StepFailed:
            return False  # no such frame (yet)
        try:
            found = scope.locator(value) if kind == "selector_visible" else scope.get_by_text(value)
            for i in range(min(await found.count(), 5)):
                if await found.nth(i).is_visible():
                    return True
        except Exception as e:
            if kind == "selector_visible":
                raise ControlError(f"Invalid selector: {_short(value, 60)}: {e}") from e
        return False

    while True:
        if await holds():
            return True
        if clock.expired():
            return False
        await asyncio.sleep(0.25)


async def run_step(controller: Any, raw: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
    """Run one step on the controller's active tab; StepFailed when it did not work."""
    try:
        step = Step.model_validate(raw)
    except ValueError as e:
        raise ControlError(f"Invalid step: {e}") from e
    if problem := step_problem(step):
        raise ControlError(f"Invalid step: {problem}")
    timeout = step.timeout_ms or timeout_ms

    if step.action in ("if", "while"):
        if step.expression() is not None:
            raise ControlError("Expressions are worked out by FoxFlow, not by the browser")
        page = await controller._page()
        return {"result": await _page_condition(page, step), "url": page.url}

    clock = _Clock(timeout)
    if step.action == "switch_tab":
        page = await _switch_tab(controller, step, clock)
        return {"url": page.url, "title": await page.title()}
    page = await controller._page()
    facts = await _act(controller, page, step, clock)
    if step.action in ("click", "press"):
        await _settle(page, clock)

    # The check gets its own time: a slow action should not starve it.
    check_clock = _Clock(timeout)
    if step.check.type == "auto":
        await _auto_check(page, step, facts, check_clock)
    elif step.check.type != "none":
        scope = await _scope(page, step.frame, check_clock)
        await _custom_check(page, scope, step, check_clock)
    return {
        "url": page.url,
        "title": await page.title(),
        "selector": facts.get("selector"),
        "text": facts.get("text"),
    }
