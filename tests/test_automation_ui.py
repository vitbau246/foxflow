"""The desktop Automation page: its pure logic, and a smoke build of the page,
the dialogs and the whole app on fakes (no window, no browser)."""

import dataclasses
from types import SimpleNamespace

import flet as ft
import pytest
from flet.controls.base_control import BaseControl
from flet.utils.validation import validate

from src.core import strings
from src.models.profile import Profile
from src.ui import automation_model as am


def _run(profile, workflow="login", status="succeeded", started="", finished="", **extra):
    return {
        "workflow": workflow,
        "profile": profile,
        "status": status,
        "active": status in ("starting", "running"),
        "started_at": started,
        "finished_at": finished,
        "step": 2,
        "step_total": 4,
        "step_label": "click Log in",
        "attempt": 1,
        "restarts": 0,
        "max_restarts": 2,
        "error": "Step 2 (click Log in): timeout" if status == "failed" else "",
        "variables": {},
        "log": [],
        **extra,
    }


WORKFLOWS = [
    {
        "name": "login",
        "description": "Sign in",
        "profile": "shop-01",
        "step_count": 4,
        "created_at": "2026-10-01T08:00:00",
        "updated_at": "2026-10-20T09:15:00",
    },
    {
        "name": "post",
        "description": "",
        "profile": "shop-02",
        "step_count": 1,
        "created_at": "2026-10-02T08:00:00",
        "updated_at": "2026-10-02T08:00:00",
    },
]


# --- pure logic -------------------------------------------------------------------


def test_sort_runs_active_first_then_newest():
    runs = [
        _run("a", started="2026-10-26T08:00:00"),
        _run("b", status="running", started="2026-10-26T07:00:00"),
        _run("c", started="2026-10-26T09:00:00"),
        _run("d", status="starting", started="2026-10-26T10:00:00"),
    ]
    assert [r["profile"] for r in am.sort_runs(runs)] == ["d", "b", "c", "a"]


def test_workflow_activity_counts_active_and_keeps_latest_finished():
    runs = [
        _run("a", finished="2026-10-26T08:00:00"),
        _run("b", status="failed", finished="2026-10-26T09:00:00"),
        _run("c", status="running"),
        _run("d", workflow="post", status="stopped", finished="2026-10-25T09:00:00"),
    ]
    activity = am.workflow_activity(runs)
    assert activity["login"]["active"] == 1
    assert activity["login"]["last"]["profile"] == "b"
    assert activity["post"] == {"active": 0, "last": runs[3]}
    assert "other" not in activity


def test_counts():
    runs = [_run("a", status="running"), _run("b", status="failed"), _run("c")]
    assert am.counts(WORKFLOWS, runs) == (2, 1, 1)


def test_search_matches_workflows_and_runs():
    assert am.match_workflow(WORKFLOWS[0], "SIGN")
    assert am.match_workflow(WORKFLOWS[1], "shop-02")
    assert not am.match_workflow(WORKFLOWS[1], "login")
    assert am.match_workflow(WORKFLOWS[1], "  ")
    assert am.match_run(_run("shop-09"), "shop-0")
    assert am.match_run(_run("x", workflow="post"), "pos")
    assert not am.match_run(_run("x"), "zzz")


def test_run_blocker_and_initial_selection():
    runs = {"b": _run("b", status="running"), "c": _run("c")}
    assert am.run_blocker("a", {"a"}, runs) == ("run_blocked_recording", {})
    assert am.run_blocker("b", set(), runs) == ("run_blocked_running", {"workflow": "login"})
    assert am.run_blocker("c", set(), runs) is None
    names = ["a", "b", "c", "Shop-01"]
    assert am.initial_selection(names, ["b", "c", "gone"], "a", {"b"}) == {"c"}
    assert am.initial_selection(names, [], "shop-01", set()) == {"Shop-01"}
    assert am.initial_selection(names, [], "", set()) == set()


def test_recording_order_puts_running_first():
    assert am.recording_order(["b", "C", "a"], {"C"}) == ["C", "a", "b"]


def test_time_formats_and_plural():
    assert am.hhmm("2026-10-26T08:05:09") == "08:05"
    assert am.ddmm("2026-10-26T08:05:09") == "26/10"
    assert am.ddmm_hhmm("2026-10-26T08:05:09") == "26/10 08:05"
    assert am.hhmm("") == am.ddmm("") == am.ddmm_hhmm("") == ""
    strings.set_language("en")
    assert am.plural("auto_steps", 1) == "1 step"
    assert am.plural("auto_steps", 3) == "3 steps"


# --- fakes ------------------------------------------------------------------------


def _validate_tree(ctrl, seen=None):
    """Flet's own control validation, which a real page runs on the first draw."""
    seen = set() if seen is None else seen
    if id(ctrl) in seen:
        return
    seen.add(id(ctrl))
    if isinstance(ctrl, (list, tuple)):
        for c in ctrl:
            _validate_tree(c, seen)
    elif isinstance(ctrl, BaseControl):
        validate(ctrl)
        for f in dataclasses.fields(ctrl):
            if not f.name.startswith("_") and f.name not in ("parent", "page", "data"):
                _validate_tree(getattr(ctrl, f.name, None), seen)


class FakePage:
    def __init__(self):
        self.controls = []
        self.dialogs = []
        self.tasks = []
        self.title = ""

    def add(self, *controls):
        _validate_tree(controls)
        self.controls.extend(controls)

    def update(self):
        pass

    def show_dialog(self, dlg):
        _validate_tree(dlg)
        self.dialogs.append(dlg)

    def pop_dialog(self):
        return self.dialogs.pop() if self.dialogs else None

    def run_task(self, fn, *args):
        self.tasks.append((fn, args))


class FakeRunner:
    def __init__(self, runs):
        self.runs = runs
        self.started = []

    def list(self, log=True):
        return [dict(r) for r in self.runs]

    def get(self, profile):
        return next((dict(r) for r in self.runs if r["profile"] == profile), None)

    def start(self, workflow, profile, variables=None):
        self.started.append((workflow, profile, variables))
        return {}

    def stop(self, profile):
        return True


class FakeStore:
    def list(self):
        return [dict(w) for w in WORKFLOWS]

    def get(self, name):
        return SimpleNamespace(variables={"query": "shoes"} if name == "login" else {})

    def delete(self, name):
        return True


class FakeLauncher:
    def __init__(self, running):
        self.running = set(running)

    def running_profile_names(self):
        return set(self.running)

    def is_running(self, name):
        return name in self.running

    def running_count(self):
        return len(self.running)


class FakeProfiles:
    def __init__(self, names):
        self.profiles = {n: Profile(name=n) for n in names}

    def list_profiles(self):
        return list(self.profiles.values())


RUNS = [
    _run("shop-01", status="running", started="2026-10-26T08:00:00"),
    _run("shop-02", status="failed", started="2026-10-26T07:00:00", finished="2026-10-26T07:05:00"),
    _run("shop-03", workflow="post", status="stopped", started="2026-10-26T06:00:00"),
]


@pytest.fixture(autouse=True)
def english():
    strings.set_language("en")
    yield
    strings.set_language("en")


def _services(runs=RUNS):
    from src.ui.dialogs.workflows import WorkflowServices

    logs = []
    return WorkflowServices(FakeLauncher({"shop-01"}), FakeStore(), FakeRunner(runs), logs.append)


def _walk(control):
    yield control
    for attr in ("content", "controls", "title", "actions"):
        child = getattr(control, attr, None)
        if isinstance(child, list):
            for c in child:
                if isinstance(c, ft.Control):
                    yield from _walk(c)
        elif isinstance(child, ft.Control):
            yield from _walk(child)


def _texts(control):
    out = []
    for c in _walk(control):
        if isinstance(c, ft.Text):
            out.append(c.value if c.value is not None else "".join(s.text for s in c.spans or []))
        elif isinstance(getattr(c, "content", None), str):
            out.append(c.content)
    return out


# --- smoke builds -----------------------------------------------------------------


def test_automation_page_renders_runs_and_workflows():
    from src.ui.components.automation import AutomationActions, AutomationData, AutomationPage

    noop = lambda *a: None  # noqa: E731
    page = AutomationPage(AutomationActions(noop, noop, noop, noop, noop, noop, noop), noop)
    data = AutomationData(WORKFLOWS, RUNS, {"shop-01"})
    assert page.render(data)
    assert not page.render(AutomationData(WORKFLOWS, RUNS, {"shop-01"}))  # nothing changed
    texts = _texts(page.control)
    assert "2 workflows · 1 running · 1 failed" in texts
    for expected in ("Runs", "Workflows", "Step 2/4", "attempt 1", "restarts 0/2", "Run again"):
        assert expected in texts, expected
    assert "Stop" in texts and "browser open" in texts and "1 running" in texts
    assert "Step 2 (click Log in): timeout" in texts

    page.render(AutomationData(WORKFLOWS, [], set(), query="post"))
    texts = _texts(page.control)
    assert "Runs" not in texts and "post" in texts and "login" not in texts
    assert "2 workflows · nothing running" in texts

    page.render(AutomationData([], [], set()))
    assert "No workflows yet" in _texts(page.control)


def test_run_dialog_preselects_and_starts():
    from src.ui.dialogs.run_workflow import open_run_dialog

    services = _services()
    fake = FakePage()
    names = ["shop-01", "shop-02", "shop-03"]
    open_run_dialog(fake, services, names, {"shop-01"}, {"shop-03"}, workflow="login")
    dlg = fake.dialogs[-1]
    texts = _texts(dlg)
    # shop-01 runs a workflow and shop-03 records: neither is preselected (owner is shop-01).
    assert "running login" in texts and "recording" in texts and "query" in texts
    run_btn = dlg.actions[-1]
    assert run_btn.content == "Run in 0 profiles" and run_btn.disabled

    open_run_dialog(fake, services, names, {"shop-01"}, set(), preselect=["shop-02", "shop-03"])
    dlg = fake.dialogs[-1]
    run_btn = dlg.actions[-1]
    assert run_btn.content == "Run in 2 profiles" and not run_btn.disabled
    assert any(isinstance(c, ft.Dropdown) for c in _walk(dlg))


def test_record_and_log_dialogs_build():
    from src.ui.dialogs.record_workflow import open_record_dialog
    from src.ui.dialogs.run_log import open_run_log

    fake = FakePage()
    picked = []
    open_record_dialog(fake, ["b", "a"], {"b"}, picked.append)
    texts = _texts(fake.dialogs[-1])
    assert "Record a workflow" in texts
    # Running profiles first, each with its browser state.
    assert texts.index("b") < texts.index("a") and "browser open" in texts
    fake.dialogs[-1].content.content.content.controls[1].on_click(None)
    assert picked == ["a"] and not fake.dialogs
    open_run_log(fake, FakeRunner(RUNS), "shop-02")
    texts = _texts(fake.dialogs[-1])
    assert "Run log · shop-02" in texts and "Step 2 (click Log in): timeout" in texts


def test_app_builds_switches_view_and_language():
    from src.ui.app import App

    runner = FakeRunner(RUNS)
    container = SimpleNamespace(
        profile_manager=FakeProfiles(["shop-01", "shop-02", "shop-03"]),
        browser_launcher=FakeLauncher({"shop-01"}),
        proxy_service=None,
        event_bus=SimpleNamespace(subscribe=lambda fn: None),
        workflow_runner=runner,
        workflow_store=FakeStore(),
        ai_settings=None,
        automation_store=None,
        automation_engine=SimpleNamespace(overview=list),
    )
    app = App(container)
    app.page = FakePage()
    app._file_picker = ft.FilePicker()
    app._build_ui()
    assert app.view == "automation" and app.automation.control.visible
    assert not app._filter_section.visible and app._primary_btn.content == "Record workflow"
    assert "Automation" in _texts(app._view_column)

    app._on_view("profiles")
    assert app._profiles_content.visible and not app.automation.control.visible
    assert app._filter_section.visible and app._primary_btn.content == "New Profile"
    app.state.toggle_selection("shop-02")
    app._refresh_profiles()
    assert "Run workflow" in _texts(app.refs.bulk_bar)

    app._set_language("vi")
    assert app.view == "profiles" and app._primary_btn.content == "Tạo profile"
    app._on_view("automation")
    assert app._primary_btn.content == "Ghi workflow"
    assert "Tự động hoá" in _texts(app.automation.control)


def test_run_dialog_run_starts_every_selected_profile():
    import asyncio

    from src.ui.dialogs.run_workflow import open_run_dialog

    services = _services()
    fake = FakePage()
    started = []
    open_run_dialog(
        fake,
        services,
        ["shop-01", "shop-02", "shop-03"],
        {"shop-01"},
        set(),
        workflow="login",
        preselect=["shop-02", "shop-03"],
        on_started=lambda: started.append(True),
    )
    asyncio.run(fake.dialogs[-1].actions[-1].on_click(None))
    assert services.runner.started == [
        ("login", "shop-02", {"query": "shoes"}),
        ("login", "shop-03", {"query": "shoes"}),
    ]
    assert services.log.__self__ == ["Started login in 2 profiles"]
    assert not fake.dialogs and started == [True]


def test_run_again_and_stop_log_to_the_activity_log():
    import asyncio

    from src.ui.actions.automation import AutomationHandlers

    services = _services()
    fake = FakePage()
    changed = []
    handlers = AutomationHandlers(
        FakeProfiles(["shop-02"]),
        services.bl,
        services,
        get_page=lambda: fake,
        get_recording=set,
        on_changed=lambda: changed.append(True),
    )
    handlers.run_again("login", "shop-02")
    fn, args = fake.tasks.pop()
    asyncio.run(fn(*args))
    assert services.runner.started == [("login", "shop-02", {})]
    handlers.stop("shop-01")
    assert services.log.__self__ == [
        "Running login in shop-02",
        "Stopping the run in shop-01...",
    ]
    assert changed == [True, True]


# --- Record workflow: launch the picked profile, then record -----------------------


@pytest.fixture
def record_env(monkeypatch):
    """A stopped profile, a fake launch and fake recording calls."""
    from src.ui.dialogs import workflows as wf_dialog

    env = SimpleNamespace(bl=FakeLauncher(set()), loading=set(), launched=[], started=[], logs=[])
    monkeypatch.setattr(
        wf_dialog.recording,
        "status",
        lambda bl, name: {
            "recording": bool(env.started),
            "draft": False,
            "step_count": 0,
            "recent": [],
        },
    )
    monkeypatch.setattr(
        wf_dialog.recording, "start", lambda bl, runner, name: env.started.append(name)
    )

    def launch(name):
        env.launched.append(name)
        env.loading.add(name)

    env.launch = launch
    env.services = wf_dialog.WorkflowServices(env.bl, FakeStore(), FakeRunner([]), env.logs.append)
    return env


def _open_recording(env):
    from src.ui.dialogs.workflows import open_workflows_dialog

    fake = FakePage()
    open_workflows_dialog(
        fake,
        "shop-02",
        env.services,
        launch=env.launch,
        is_loading=env.loading.__contains__,
        auto_record=True,
    )
    refresh = next(fn for fn, _ in fake.tasks if fn.__name__ == "refresh_state")
    return fake, refresh


def test_record_launches_a_stopped_profile_then_starts_recording(record_env):
    import asyncio

    fake, refresh = _open_recording(record_env)
    assert record_env.launched == ["shop-02"]
    assert "Launching shop-02… Recording starts as soon as the browser is ready." in _texts(
        fake.dialogs[-1]
    )
    asyncio.run(refresh())  # still starting: nothing to record in yet
    assert record_env.started == []
    record_env.loading.clear()
    record_env.bl.running.add("shop-02")
    asyncio.run(refresh())
    assert record_env.started == ["shop-02"]
    assert any("shop-02" in line for line in record_env.logs)
    asyncio.run(refresh())  # only once
    assert record_env.started == ["shop-02"]


def test_record_reports_a_failed_launch(record_env):
    import asyncio

    fake, refresh = _open_recording(record_env)
    record_env.loading.clear()  # the browser exited before it was ready
    asyncio.run(refresh())
    assert record_env.started == []
    assert any("did not start" in t for t in _texts(fake.dialogs[-1]))
