"""assign, if / else, for, while and break in a workflow run; chains of workflows."""

import asyncio

import pytest

from src.services.browser.launcher import BrowserControlError
from src.services.browser.recorder import Recorder
from src.services.workflow.expression import ExpressionError, evaluate, names, to_text, truthy
from src.services.workflow.model import Step, Workflow, blocks, depths, problems, unclosed
from src.services.workflow.runner import WorkflowRunner
from src.services.workflow.store import WorkflowError, WorkflowStore
from tests.test_recorder import FakeContext, FakePage
from tests.test_workflow_runner import FakeLauncher, FakeProfiles, _wait

# --- expressions ----------------------------------------------------------------


def test_expressions_compare_numbers_as_numbers_and_the_rest_as_text():
    v = {"price": "120", "status": "ok", "name": " An ", "n": "9"}
    assert evaluate('price > 100 and status == "ok"', v) is True
    assert evaluate("n < 10", v) is True  # "9" < "10" as text would be False
    assert evaluate("{{price}} + 1", v) == 121
    assert evaluate('status + "!"', v) == "ok!"
    assert evaluate('lower(trim(name)) + "@example.com"', v) == "an@example.com"
    assert evaluate('contains(status, "o") and not matches(name, "\\\\d")', v) is True
    assert evaluate('"k" in status', v) is True
    assert to_text(evaluate("price / 4", v)) == "30"
    assert to_text(evaluate("price > 1", v)) == "true"
    assert names("a + len(b) > c and true") == ["a", "b", "c"]
    assert [truthy(x) for x in ("", "0", "false", "no", "1", 0, 2)] == [
        False,
        False,
        False,
        True,
        True,
        False,
        True,
    ]


@pytest.mark.parametrize(
    "text",
    [
        "__import__('os')",
        "price.__class__",
        "open('x')",
        "[1, 2]",
        "x if y else z",
        "2 ** 1000",
        "lambda: 1",
        "len(a, b)",
        "",
    ],
)
def test_anything_outside_the_language_is_refused(text):
    with pytest.raises(ExpressionError):
        evaluate(text, {"price": "1", "x": "1", "y": "1", "z": "1", "a": "", "b": ""})


def test_runtime_errors_are_expression_errors():
    with pytest.raises(ExpressionError, match="has no value"):
        evaluate("missing > 1", {})
    with pytest.raises(ExpressionError, match="not a number"):
        evaluate("a - 1", {"a": "abc"})
    with pytest.raises(ExpressionError, match="division by zero"):
        evaluate("1 / 0", {})


# --- structure --------------------------------------------------------------------


def test_blocks_match_and_report_what_is_wrong():
    table, errors = blocks(["if", "click", "else", "for", "break", "end", "end"])
    assert errors == []
    assert (table[0].else_at, table[0].end) == (2, 6)
    assert table[4] is table[3] and table[3].end == 5
    _, errors = blocks(["else", "end", "break", "while"])
    assert [p for _, p in errors] == [
        "else without an if before it",
        "end without an if, for or while before it",
        "break outside a for or while",
        "has no end",
    ]
    assert depths(["if", "click", "else", "for", "break", "end", "end", "x"]) == [
        0,
        1,
        0,
        1,
        2,
        1,
        0,
        0,
    ]
    assert unclosed(["for", "if", "end"]) == [0]


def test_problems_cover_blocks_conditions_and_expression_variables():
    wf = Workflow(
        name="x",
        variables={"n": "3"},
        steps=[
            Step(action="if", value="n > 1 and missing"),
            Step(action="assign", save_as="total", value="= n * 2"),
            Step(action="assign", value="no target"),
            Step(action="while", value=""),
            Step(action="for", value="{{total}}", save_as="i"),
            Step(action="assign", save_as="bad", value="= n +"),
            Step(action="end"),
        ],
    )
    assert problems(wf) == [
        "Step 1 (if): unknown variable {{missing}}",
        "Step 1 (if): has no end",
        "Step 3 (assign): needs a variable to save into",
        "Step 4 (while): needs a condition",
        "Step 4 (while): has no end",
        "Step 6 (assign): invalid expression: invalid syntax",
    ]


# --- running ------------------------------------------------------------------------


def _steps(*specs):
    return [Step(id=f"s{i}", delay_ms=0, **spec) for i, spec in enumerate(specs, start=1)]


@pytest.fixture
def runner_for(tmp_path, monkeypatch):
    monkeypatch.setattr(WorkflowRunner, "RESTART_PAUSE_S", 0)
    store = WorkflowStore(str(tmp_path / "workflows"))

    def build(launcher, *workflows):
        for wf in workflows:
            store.save(wf)
        return WorkflowRunner(store, FakeProfiles("p1"), launcher, launch_timeout=5)

    return build


def _browser_steps(bl):
    return [(p["step"]["id"], p["step"]["value"]) for a, p in bl.calls if a == "run_step"]


def test_for_loops_over_a_count_and_a_list_with_if_else(runner_for):
    wf = Workflow(
        name="loop",
        variables={"names": "An\nBinh\nChi"},
        steps=_steps(
            {"action": "for", "value": "{{names}}", "save_as": "who"},
            {"action": "if", "value": 'who == "Binh"'},
            {"action": "fill", "selectors": ["#q"], "value": "skip {{who}}"},
            {"action": "else"},
            {"action": "fill", "selectors": ["#q"], "value": "hi {{who}}"},
            {"action": "end"},
            {"action": "end"},
            {"action": "assign", "save_as": "count", "value": "0"},
            {"action": "for", "value": "3", "save_as": "i"},
            {"action": "assign", "save_as": "count", "value": "= count + i"},
            {"action": "end"},
            {"action": "fill", "selectors": ["#q"], "value": "sum {{count}}"},
        ),
    )
    bl = FakeLauncher()
    runner = runner_for(bl, wf)
    runner.start("loop", "p1")
    state = _wait(runner)
    assert state["status"] == "succeeded", state["error"]
    assert [v for _, v in _browser_steps(bl)] == ["hi An", "skip Binh", "hi Chi", "sum 6"]
    assert state["variables"]["count"] == "6"


def test_while_with_break_and_the_round_limit(runner_for):
    wf = Workflow(
        name="w",
        variables={"n": "0"},
        steps=_steps(
            {"action": "while", "value": "true", "max_loops": 50},
            {"action": "assign", "save_as": "n", "value": "= n + 1"},
            {"action": "if", "value": "n >= 4"},
            {"action": "break"},
            {"action": "end"},
            {"action": "end"},
            {"action": "while", "value": "n < 100", "max_loops": 3},
            {"action": "assign", "save_as": "n", "value": "= n + 10"},
            {"action": "end"},
        ),
    )
    runner = runner_for(FakeLauncher(), wf)
    runner.start("w", "p1")
    state = _wait(runner)
    assert state["status"] == "succeeded", state["error"]
    assert state["variables"]["n"] == "34"
    assert any("stopped the loop after 3 rounds" in line for line in state["log"])


def test_page_conditions_are_asked_of_the_browser(runner_for):
    wf = Workflow(
        name="page",
        steps=_steps(
            {"action": "if", "condition": "selector_visible", "value": "#cookie-banner"},
            {"action": "click", "selectors": ["#accept"]},
            {"action": "end"},
            {
                "action": "if",
                "condition": "text_visible",
                "value": "Sold out",
                "negate": True,
            },
            {"action": "click", "selectors": ["#buy"]},
            {"action": "end"},
        ),
    )

    class PageLauncher(FakeLauncher):
        def control(self, name, action, params=None, timeout=60):
            if action == "run_step" and params["step"]["action"] == "if":
                self.calls.append((action, params))
                return {"result": True}
            return super().control(name, action, params, timeout)

    bl = PageLauncher()
    runner = runner_for(bl, wf)
    runner.start("page", "p1")
    state = _wait(runner)
    assert state["status"] == "succeeded", state["error"]
    # The banner shows: accept is clicked. "Sold out" shows too, so (negated) buy is not.
    assert [i for i, _ in _browser_steps(bl)] == ["s1", "s2", "s4"]


def test_a_failing_condition_check_is_retried_then_restarts(runner_for):
    wf = Workflow(
        name="flaky",
        settings={"retries": 1, "retry_delay_ms": 0, "max_restarts": 0},
        steps=_steps(
            {"action": "if", "condition": "url_contains", "value": "done"},
            {"action": "end"},
        ),
    )
    bl = FakeLauncher(fail=lambda step, n: BrowserControlError("boom", status=500))
    runner = runner_for(bl, wf)
    runner.start("flaky", "p1")
    state = _wait(runner)
    assert state["status"] == "failed"
    assert len(_browser_steps(bl)) == 2


def test_an_expression_that_cannot_be_worked_out_fails_the_run(runner_for):
    wf = Workflow(
        name="nan",
        variables={"price": "N/A"},
        settings={"max_restarts": 0},
        steps=_steps({"action": "assign", "save_as": "x", "value": "= price * 2"}),
    )
    runner = runner_for(FakeLauncher(), wf)
    runner.start("nan", "p1")
    state = _wait(runner)
    assert state["status"] == "failed"
    assert "not a number" in state["error"]


# --- chains -------------------------------------------------------------------------


def test_a_chain_runs_each_workflow_and_carries_variables(runner_for):
    first = Workflow(
        name="first",
        variables={"greeting": "hi"},
        steps=_steps({"action": "assign", "save_as": "token", "value": "abc"}),
    )
    second = Workflow(
        name="second",
        variables={"token": "", "greeting": "hello"},
        settings={"close_when_done": True},
        steps=_steps({"action": "fill", "selectors": ["#q"], "value": "{{greeting}} {{token}}"}),
    )
    bl = FakeLauncher()
    runner = runner_for(bl, first, second)
    started = runner.start_chain(["first", "second"], "p1", {"greeting": "yo"})
    assert started["workflows"] == ["first", "second"] and started["workflow_count"] == 2
    state = _wait(runner)
    assert state["status"] == "succeeded", state["error"]
    assert state["workflow"] == "second" and state["workflow_index"] == 2
    assert [v for _, v in _browser_steps(bl)] == ["yo abc"]
    assert [a for a, _ in bl.calls].count("run_prepare") == 2
    assert bl.launches == 1 and bl.stops == 1  # the last one's close_when_done


def test_a_chain_stops_at_the_first_failure(runner_for):
    bad = Workflow(
        name="bad",
        settings={"retries": 0, "max_restarts": 0},
        steps=_steps({"action": "click", "selectors": ["#x"]}),
    )
    after = Workflow(name="after", steps=_steps({"action": "click", "selectors": ["#y"]}))
    bl = FakeLauncher(fail=lambda step, n: BrowserControlError("nope", status=500))
    runner = runner_for(bl, bad, after)
    runner.start_chain(["bad", "after"], "p1")
    state = _wait(runner)
    assert state["status"] == "failed" and state["workflow"] == "bad"
    assert [i for i, _ in _browser_steps(bl)] == ["s1"]


def test_a_chain_is_checked_before_it_starts(runner_for):
    ok = Workflow(name="ok", steps=_steps({"action": "wait", "value": "1"}))
    runner = runner_for(FakeLauncher(), ok)
    with pytest.raises(WorkflowError, match="not found"):
        runner.start_chain(["ok", "missing"], "p1")
    with pytest.raises(WorkflowError, match="at least one"):
        runner.start_chain([], "p1")
    assert runner.get("p1") is None


def test_chain_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from src.api.app import create_app
    from src.core.container import Container

    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app(Container()), base_url="http://127.0.0.1")
    api = "/api/v1"
    assert client.post(f"{api}/profiles", json={"name": "p1"}).status_code == 201
    wf = {"name": "a", "steps": [{"action": "wait", "value": "1"}]}
    assert client.put(f"{api}/workflows/a", json=wf).status_code == 200
    r = client.post(f"{api}/workflow-runs", json={"profile": "p1", "workflows": ["a", "nope"]})
    assert r.status_code == 404 and "nope" in r.json()["detail"]
    r = client.post(f"{api}/workflow-runs", json={"profile": "p1", "workflows": []})
    assert r.status_code == 422


# --- recording a "Get text" offer ---------------------------------------------------


def test_an_accepted_get_text_offer_becomes_a_step(tmp_path):
    page = FakePage("https://shop.test/")
    ctx = FakeContext(page)
    recorder = Recorder(ctx, str(tmp_path))
    asyncio.run(recorder.start(page, lang="vi"))

    def event(ev):
        return asyncio.run(ctx.binding({"page": page, "frame": page.main_frame}, ev))

    assert event({"type": "get_text_name"}) == {"name": "text1", "lang": "vi"}
    assert event(
        {
            "type": "get_text",
            "save_as": "price",
            "text": "1.290.000 ₫",
            "selectors": ["span.price"],
            "hint": "",
        }
    )
    step = recorder.steps[-1]
    assert (step["action"], step["save_as"], step["selectors"]) == (
        "get_text",
        "price",
        ["span.price"],
    )
    assert step["label"] == "1.290.000 ₫"
    # A name the page could not check falls back to the next free textN.
    event({"type": "get_text", "save_as": "1bad", "selectors": ["h1"], "hint": "Title"})
    assert recorder.steps[-1]["save_as"] == "text1"
    assert event({"type": "get_text_name"})["name"] == "text2"
    Step.model_validate({k: v for k, v in recorder.steps[-1].items() if not k.startswith("_")})
    asyncio.run(recorder.stop())
    assert event({"type": "get_text_name"}) is None
