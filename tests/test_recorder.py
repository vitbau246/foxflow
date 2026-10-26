"""Turning recorded browser events into workflow steps (no browser needed)."""

import asyncio

import pytest

from src.services.browser import recorder as rec
from src.services.browser.recorder import Recorder, clean_steps, discard_draft, load_draft
from src.services.workflow.model import Step


class FakeFrame:
    def __init__(self, page, url="", name=""):
        self.page, self.url, self.name = page, url, name

    async def evaluate(self, script):
        return None


class FakePage:
    def __init__(self, url="about:blank"):
        self.main_frame = FakeFrame(self, url)
        self.frames = [self.main_frame]
        self.handlers = {}

    @property
    def url(self):
        return self.main_frame.url

    def is_closed(self):
        return False

    def on(self, event, fn):
        self.handlers[event] = fn

    def navigate(self, url):
        self.main_frame.url = url
        self.handlers["framenavigated"](self.main_frame)


class FakeContext:
    def __init__(self, page):
        self.pages = [page]
        self.binding = None

    async def expose_binding(self, name, fn):
        self.binding = fn

    async def add_init_script(self, script):
        pass

    def on(self, event, fn):
        self.on_page = fn


@pytest.fixture
def setup(tmp_path, monkeypatch):
    page = FakePage("https://shop.test/")
    ctx = FakeContext(page)
    recorder = Recorder(ctx, str(tmp_path))
    asyncio.run(recorder.start(page))

    def event(ev, p=page, frame=None):
        return asyncio.run(ctx.binding({"page": p, "frame": frame or p.main_frame}, ev))

    return recorder, page, ctx, event, tmp_path


def test_starts_on_the_current_page_and_answers_pings(setup):
    recorder, _, _, event, _ = setup
    assert recorder.steps[0]["action"] == "navigate"
    assert recorder.steps[0]["value"] == "https://shop.test/"
    assert recorder.steps[0]["delay_ms"] == 0
    assert event({"type": "ping"}) is True


def test_typing_in_one_field_is_one_fill_step(setup):
    recorder, _, _, event, _ = setup
    sel = ['input[name="q"]', "#q"]
    event(
        {
            "type": "fill",
            "value": "he",
            "selectors": sel,
            "hint": "q",
            "keystrokes": 2,
            "typing_ms": 100,
        }
    )
    event(
        {
            "type": "fill",
            "value": "hello",
            "selectors": sel,
            "hint": "q",
            "keystrokes": 5,
            "typing_ms": 400,
        }
    )
    event({"type": "fill", "value": "x", "selectors": ["#other"], "hint": "other"})
    fills = [s for s in recorder.steps if s["action"] == "fill"]
    assert [f["value"] for f in fills] == ["hello", "x"]
    assert fills[0]["char_delay_ms"] == 0  # 2 keystrokes: too few to measure


def test_typing_speed_is_measured(setup):
    recorder, _, _, event, _ = setup
    event(
        {"type": "fill", "value": "hello", "selectors": ["#q"], "keystrokes": 5, "typing_ms": 400}
    )
    assert recorder.steps[-1]["char_delay_ms"] == 100
    event(
        {
            "type": "fill",
            "value": "pasted text",
            "selectors": ["#p"],
            "keystrokes": 1,
            "typing_ms": 0,
        }
    )
    assert recorder.steps[-1]["char_delay_ms"] == 0


def test_a_navigation_right_after_a_click_is_its_expected_result(setup):
    recorder, page, _, event, _ = setup
    event({"type": "click", "selectors": ['button:text-is("Buy")'], "hint": "Buy", "tag": "button"})
    page.navigate("https://shop.test/cart?id=7")
    page.navigate("https://shop.test/cart/review")  # a redirect: keep the last stop
    assert [s["action"] for s in recorder.steps] == ["navigate", "click"]
    assert recorder.steps[1]["expect_url"] == "https://shop.test/cart/review"
    assert recorder.steps[1]["label"] == "Buy"


def test_a_navigation_on_its_own_is_a_navigate_step(setup, monkeypatch):
    recorder, page, _, event, _ = setup
    event({"type": "fill", "value": "a", "selectors": ["#q"]})
    page.navigate("https://other.test/")
    assert recorder.steps[-1]["action"] == "navigate"
    assert recorder.steps[-1]["value"] == "https://other.test/"
    assert recorder.steps[-2]["expect_url"] == ""


def test_actions_in_a_new_tab_switch_tabs_first(setup):
    recorder, _, ctx, event, _ = setup
    popup = FakePage("https://shop.test/help")
    ctx.on_page(popup)
    event({"type": "click", "selectors": ["#faq"]}, p=popup)
    assert [s["action"] for s in recorder.steps[-2:]] == ["switch_tab", "click"]
    assert recorder.steps[-2]["value"] == "1"


def test_frames_scrolls_and_keys(setup):
    recorder, page, _, event, _ = setup
    frame = FakeFrame(page, "https://pay.test/form", name="")
    event({"type": "fill", "value": "4111", "selectors": ["#card"]}, frame=frame)
    assert recorder.steps[-1]["frame"] == "https://pay.test/form"
    event({"type": "scroll", "x": 0, "y": 300})
    event({"type": "scroll", "x": 0, "y": 900})
    assert recorder.steps[-1]["value"] == "0,900"
    assert sum(s["action"] == "scroll" for s in recorder.steps) == 1
    event({"type": "press", "key": "Enter"})
    assert recorder.steps[-1]["action"] == "press" and recorder.steps[-1]["selectors"] == []


def test_stop_ignores_later_events_and_steps_are_valid(setup):
    recorder, _, _, event, _ = setup
    event({"type": "select", "value": "us", "option": "USA", "selectors": ["select"]})
    event({"type": "check", "selectors": ["#remember"], "hint": "remember"})
    result = asyncio.run(recorder.stop())
    assert result["recording"] is False
    assert event({"type": "click", "selectors": ["#x"]}) is False
    assert event({"type": "ping"}) is False
    steps = clean_steps(result["steps"])
    assert all(not k.startswith("_") for s in steps for k in s)
    for s in steps:
        Step.model_validate(s)


def test_the_draft_survives_on_disk(setup):
    recorder, _, _, event, tmp_path = setup
    event({"type": "click", "selectors": ["#a"]})
    draft = load_draft(str(tmp_path))
    assert draft["recording"] is True and len(draft["steps"]) == 2
    discard_draft(str(tmp_path))
    assert load_draft(str(tmp_path)) is None


def test_recorded_delays_are_bounded(monkeypatch):
    assert rec._delay(0.01) == rec.MIN_DELAY_MS
    assert rec._delay(1.26) == 1300
    assert rec._delay(120) == rec.MAX_DELAY_MS
