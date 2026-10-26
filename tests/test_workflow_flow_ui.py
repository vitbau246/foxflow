"""The desktop editor and run dialog with if / for / while / assign steps and chains."""

from types import SimpleNamespace

import flet as ft

from src.services.workflow.model import Step, Workflow
from src.services.workflow.store import WorkflowStore
from src.ui.dialogs.workflow_editor import close_block, new_step, open_workflow_editor
from tests.test_automation_ui import FakePage, _texts, _walk

FLOW = [
    Step(action="assign", save_as="n", value="= 1 + 1", delay_ms=0),
    Step(action="for", value="A\nB", save_as="item", delay_ms=0),
    Step(action="if", condition="text_visible", value="Sold out", negate=True, delay_ms=0),
    Step(action="click", selectors=["#buy"], delay_ms=0),
    Step(action="else", delay_ms=0),
    Step(action="break", delay_ms=0),
    Step(action="end", delay_ms=0),
    Step(action="end", delay_ms=0),
    Step(action="while", value="n < 5", max_loops=7, delay_ms=0),
    Step(action="assign", save_as="n", value="= n + 1", delay_ms=0),
    Step(action="end", delay_ms=0),
]


def _icon_buttons(control, tooltip):
    return [c for c in _walk(control) if isinstance(c, ft.IconButton) and c.tooltip == tooltip]


def test_editor_shows_blocks_and_their_fields(tmp_path):
    store = WorkflowStore(str(tmp_path))
    store.save(Workflow(name="flow", steps=FLOW))
    fake = FakePage()
    open_workflow_editor(fake, store, "flow")
    dlg = fake.dialogs[-1]
    texts = _texts(dlg)
    for label in ("Set variable", "Repeat for", "If", "Else", "Exit loop", "End", "Repeat while"):
        assert label in texts
    assert "{{n}} = = 1 + 1" in texts
    assert "A · B → {{item}}" in texts
    assert "not Text visible: Sold out" in texts
    assert "n < 5 · ≤ 7" in texts

    # Open every step's details: each kind builds its own fields.
    for button in _icon_buttons(dlg, "Details"):
        button.on_click(None)
    texts = _texts(dlg)
    assert "Repeat over" in texts and "Variable for each item" in texts
    assert "Condition" in texts and "At most (rounds)" in texts
    assert "Wait for it (ms)" in texts  # the page condition of the if

    # Save keeps the steps as they were.
    dlg.actions[-1].on_click(None)
    assert not fake.dialogs
    assert [s.action for s in store.get("flow").steps] == [s.action for s in FLOW]


def test_picking_if_adds_its_end_and_insert_below(tmp_path):
    steps = [new_step(), new_step(action="click", selectors=["#a"])]
    steps[0]["action"] = "if"
    assert close_block(steps, 0)
    assert [s["action"] for s in steps] == ["if", "end", "click"]
    assert not close_block(steps, 0)  # already closed

    store = WorkflowStore(str(tmp_path))
    store.save(Workflow(name="w", steps=[Step(action="wait", value="5")]))
    fake = FakePage()
    open_workflow_editor(fake, store, "w")
    dlg = fake.dialogs[-1]
    _icon_buttons(dlg, "Insert a step below")[0].on_click(None)
    action = next(
        c
        for c in _walk(dlg)
        if isinstance(c, ft.Dropdown) and any(o.key == "while" for o in c.options)
    )
    action.value = "while"
    action.on_select(SimpleNamespace(control=action))
    texts = _texts(dlg)
    assert texts.count("Repeat while") >= 1 and "End" in texts


def test_run_dialog_runs_a_chain():
    import asyncio

    from tests.test_automation_ui import _services

    services = _services()
    chains = []
    services.runner.start_chain = lambda names, profile, values: chains.append(
        (names, profile, values)
    )
    services.store.list = lambda: [
        {"name": "login", "profile": ""},
        {"name": "post", "profile": ""},
    ]
    from src.ui.dialogs.run_workflow import open_run_dialog

    fake = FakePage()
    open_run_dialog(
        fake, services, ["shop-02"], set(), set(), workflow="login", preselect=["shop-02"]
    )
    dlg = fake.dialogs[-1]
    add = next(
        c for c in _walk(dlg) if isinstance(c, ft.TextButton) and c.content == "Add workflow"
    )
    add.on_click(None)
    assert "Each profile runs these workflows in this order in one browser." in " ".join(
        _texts(dlg)
    )
    asyncio.run(dlg.actions[-1].on_click(None))
    assert [(n, p) for n, p, _ in chains] == [(["login", "post"], "shop-02")]
    assert services.log.__self__ == ["Started login → post in 1 profile"]
