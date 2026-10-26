import json

import pytest
from pydantic import ValidationError

from src.services.workflow.model import Step, Workflow, problems, scaled, step_problem
from src.services.workflow.steps import same_page, same_text
from src.services.workflow.store import WorkflowError, WorkflowStore


def _wf(name="login", **kw):
    return Workflow(
        name=name,
        steps=[
            Step(action="navigate", value="https://example.test/"),
            Step(action="click", selectors=["#go"]),
        ],
        **kw,
    )


def test_defaults_check_every_step_retry_twice_and_restart():
    wf = Workflow(name="x")
    assert wf.settings.retries == 2
    assert wf.settings.max_restarts >= 1
    assert Step(action="click", selectors=["a"]).check.type == "auto"


@pytest.mark.parametrize(
    ("step", "problem"),
    [
        (Step(action="click"), "needs a selector"),
        (Step(action="navigate"), "needs a value"),
        (Step(action="press", selectors=["#q"]), "needs a value"),
        (Step(action="wait", value="soon"), "whole number"),
        (Step(action="scroll", value="10"), "x,y"),
        (Step(action="click", selectors=["a"], check={"type": "url_contains"}), "check needs"),
        (Step(action="fill", selectors=["#q"]), None),  # clearing a field is fine
        (Step(action="select", selectors=["s"]), None),  # an option's value may be ""
        (Step(action="scroll", value="0,-40"), None),
        (Step(action="wait", value="1500"), None),
    ],
)
def test_step_problem(step, problem):
    found = step_problem(step)
    assert (found is None) if problem is None else (problem in found)


def test_problems_skip_disabled_steps_and_name_the_step():
    wf = Workflow(
        name="x", steps=[Step(action="click", label="Buy", enabled=False), Step(action="click")]
    )
    assert problems(wf) == ["Step 2 (click): needs a selector"]


def test_selectors_are_trimmed_and_deduplicated():
    assert Step(action="click", selectors=[" #a ", "#a", "", "b"]).selectors == ["#a", "b"]


def test_limits_are_enforced():
    with pytest.raises(ValidationError):
        Step(action="click", selectors=["a"], delay_ms=-1)
    with pytest.raises(ValidationError):
        Step(action="rm_rf")
    with pytest.raises(ValidationError):
        Workflow(name="x", settings={"speed": 0})


def test_scaled():
    assert scaled(1000, 2) == 0.5
    assert scaled(1000, 0.5) == 2.0


@pytest.mark.parametrize(
    ("actual", "expected", "same"),
    [
        ("https://www.shop.test/cart/?a=1#x", "https://shop.test/cart", True),
        ("https://shop.test/", "https://shop.test", True),
        ("https://shop.test/login", "https://shop.test/cart", False),
        ("https://other.test/cart", "https://shop.test/cart", False),
    ],
)
def test_same_page(actual, expected, same):
    assert same_page(actual, expected) is same


def test_same_text_ignores_field_formatting():
    assert same_text("0901 234 567", "0901234567")
    assert same_text("abc", "abc")
    assert not same_text("abd", "abc")
    assert not same_text("", "---")


def test_store_round_trip(tmp_path):
    store = WorkflowStore(str(tmp_path))
    saved = store.save(_wf(description="d"), create=True)
    assert saved.created_at and saved.updated_at
    assert store.get("login").description == "d"
    assert [w["name"] for w in store.list()] == ["login"]
    assert store.list()[0]["step_count"] == 2
    data = json.loads((tmp_path / "login.json").read_text(encoding="utf-8"))
    assert data["steps"][1]["selectors"] == ["#go"]


def test_names_are_case_insensitive_and_keep_their_spelling(tmp_path):
    store = WorkflowStore(str(tmp_path))
    first = store.save(_wf("Login"), create=True)
    with pytest.raises(WorkflowError) as e:
        store.save(_wf("login"), create=True)
    assert e.value.status == 409
    again = store.save(_wf("LOGIN", description="v2"))
    assert again.name == "Login" and again.created_at == first.created_at
    assert store.get("login").description == "v2"
    assert len(list(tmp_path.glob("*.json"))) == 1
    assert store.delete("LOGIN") and store.get("Login") is None
    assert not store.delete("login")


@pytest.mark.parametrize("name", ["", " x", "a/b", "..", "CON", "x" * 65])
def test_bad_names_are_refused(tmp_path, name):
    with pytest.raises((WorkflowError, ValidationError)):
        WorkflowStore(str(tmp_path)).save(_wf(name))


def test_invalid_steps_are_refused_on_save(tmp_path):
    with pytest.raises(WorkflowError, match="needs a selector"):
        WorkflowStore(str(tmp_path)).save(Workflow(name="x", steps=[Step(action="click")]))


def test_unreadable_files_are_skipped(tmp_path):
    (tmp_path / "broken.json").write_text("{nope", encoding="utf-8")
    store = WorkflowStore(str(tmp_path))
    store.save(_wf())
    assert [w["name"] for w in store.list()] == ["login"]
    assert store.get("broken") is None
