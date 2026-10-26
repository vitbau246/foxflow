"""Desktop flows that used to stop at "stop it first" / "create one first" now do
that step themselves: stop the browser, create the profile, open the recorder,
open the AI settings. Fakes only (no window, no browser); FakePage runs Flet's
own control validation on every dialog."""

import asyncio
from types import SimpleNamespace

import flet as ft
import pytest

from src.core import strings
from src.core.strings import get_string
from src.models.profile import Profile
from src.services.profile.clone_parts import PARTS
from src.ui.state import AppState
from src.ui.theme.styles import ACCENT_STYLE, ERROR_STYLE, INK_STYLE
from tests.test_automation_ui import WORKFLOWS, FakePage, FakeRunner, _texts, _walk


@pytest.fixture(autouse=True)
def english():
    strings.set_language("en")
    yield
    strings.set_language("en")


class Launcher:
    """Running browsers; stop_profile records the order of events."""

    def __init__(self, events, running=(), stops=True):
        self.events = events
        self.running = set(running)
        self.stops = stops

    def is_running(self, name):
        return name in self.running

    def running_profile_names(self):
        return set(self.running)

    def running_count(self):
        return len(self.running)

    def stop_profile(self, name, timeout=2):
        self.events.append(("stop", name))
        if self.stops:
            self.running.discard(name)
        return True


class Profiles:
    def __init__(self, events, names):
        self.events = events
        self.profiles = {n: Profile(name=n) for n in names}

    def list_profiles(self):
        return list(self.profiles.values())

    def delete_profile(self, name):
        self.events.append(("delete", name))
        return self.profiles.pop(name, None) is not None

    def update_profile(self, original, new, proxy, os_type, timezone=None, locale=None):
        self.events.append(("update", original, new))
        self.profiles[new] = Profile(name=new)
        if new != original:
            del self.profiles[original]
        return True

    def add_profile(self, name, proxy, os_type, timezone=None, locale=None, engine="camoufox"):
        self.events.append(("add", name))
        self.profiles[name] = Profile(name=name)
        return True

    def clone_name(self, source):
        return f"{source}-copy"

    def clone_names(self, base, count):
        return [f"{base}-{i}" for i in range(1, count + 1)]


class Runs(FakeRunner):
    def __init__(self, events):
        super().__init__([])
        self.events = events

    def stop(self, profile):
        self.events.append(("run_stop", profile))
        return True


class Store:
    def __init__(self, events, workflows=WORKFLOWS, steps=()):
        self.events = events
        self.workflows = workflows
        self.steps = list(steps)

    def list(self):
        return [dict(w) for w in self.workflows]

    def get(self, name):
        return SimpleNamespace(variables={}, steps=self.steps)

    def of_profile(self, name):
        return []

    def reassign(self, old, new):
        self.events.append(("reassign", old, new))
        return 0


def _env(running=("shop-01",), names=("shop-01", "shop-02"), stops=True, workflows=WORKFLOWS):
    from src.ui.dialogs.workflows import WorkflowServices
    from src.ui.handlers import AppHandlers

    events, logs = [], []
    fake = FakePage()
    bl = Launcher(events, running, stops)
    pm = Profiles(events, names)
    state = AppState()
    services = WorkflowServices(bl, Store(events, workflows), Runs(events), logs.append)
    handlers = AppHandlers(
        pm=pm,
        bl=bl,
        ps=None,
        state=state,
        get_page=lambda: fake,
        get_refs=lambda: SimpleNamespace(file_picker=None),
        log_fn=logs.append,
        refresh_fn=lambda: None,
        get_page_profiles=lambda: (pm.list_profiles(), pm.list_profiles(), 1),
        workflows=services,
    )
    return SimpleNamespace(
        fake=fake, bl=bl, pm=pm, state=state, events=events, logs=logs, h=handlers, wf=services
    )


def _drain(fake):
    """Run what the handlers scheduled with page.run_task, in order."""
    while fake.tasks:
        fn, args = fake.tasks.pop(0)
        asyncio.run(fn(*args))


def _run_only(fake, name):
    """Run the scheduled tasks named `name` and drop the rest."""
    tasks, fake.tasks = fake.tasks, []
    for fn, args in tasks:
        if fn.__name__ == name:
            asyncio.run(fn(*args))


def _button(dlg, label):
    return next(
        c for c in _walk(dlg) if isinstance(c, ft.Button | ft.OutlinedButton) and c.content == label
    )


# --- cookies & fingerprint ----------------------------------------------------------


def test_row_cookie_and_delete_buttons_work_while_running():
    from src.ui.components.profile_card import build_profile_card

    noop = lambda *a: None  # noqa: E731
    row = build_profile_card(
        Profile(name="shop-01"), False, True, noop, noop, noop, on_cookies=noop
    )
    icons = {c.icon: c for c in _walk(row) if isinstance(c, ft.IconButton)}
    assert not icons[ft.Icons.COOKIE_OUTLINED].disabled
    assert not icons[ft.Icons.DELETE_OUTLINE].disabled


def test_cookies_on_a_running_profile_stop_it_then_open_the_dialog():
    env = _env()
    env.h.on_cookies("shop-01")
    confirm = env.fake.dialogs[-1]
    assert (
        "shop-01 is running. Stop its browser to work with its cookies and fingerprint?"
        in _texts(confirm)
    )
    button = confirm.actions[-1]
    assert button.content == "Stop and continue" and button.style is INK_STYLE
    button.on_click(None)
    assert not env.fake.dialogs and env.events == [("run_stop", "shop-01")]
    assert env.state.is_loading("shop-01")
    _drain(env.fake)
    # The run first, then the browser, and only then the Cookies dialog.
    assert env.events == [("run_stop", "shop-01"), ("stop", "shop-01")]
    assert not env.state.is_loading("shop-01")
    assert "Cookies & fingerprint" in _texts(env.fake.dialogs[-1])
    assert "Stopping shop-01..." in env.logs


def test_cookies_dialog_does_not_open_when_the_browser_will_not_stop():
    env = _env(stops=False)
    env.h.on_cookies("shop-01")
    env.fake.dialogs[-1].actions[-1].on_click(None)
    _drain(env.fake)
    assert not env.fake.dialogs
    assert "Could not stop shop-01" in env.logs


def test_cookies_on_a_stopped_profile_open_at_once():
    env = _env(running=())
    env.h.on_cookies("shop-02")
    assert "Cookies & fingerprint" in _texts(env.fake.dialogs[-1])
    assert env.events == [] and not env.fake.tasks


# --- delete -----------------------------------------------------------------------


def test_delete_a_running_profile_stops_it_first():
    env = _env()
    env.h.on_delete("shop-01")
    confirm = env.fake.dialogs[-1]
    assert (
        "This action cannot be undone. Its browser is running and will be stopped first."
        in _texts(confirm)
    )
    assert confirm.actions[-1].style is ERROR_STYLE  # deleting stays red
    confirm.actions[-1].on_click(None)
    _drain(env.fake)
    assert env.events == [("run_stop", "shop-01"), ("stop", "shop-01"), ("delete", "shop-01")]
    assert "shop-01" not in env.pm.profiles


def test_delete_a_stopped_profile_has_no_stop_note():
    env = _env(running=())
    env.h.on_delete("shop-02")
    texts = _texts(env.fake.dialogs[-1])
    assert "This action cannot be undone." in texts
    assert not any("stopped first" in t for t in texts)
    env.fake.dialogs[-1].actions[-1].on_click(None)
    assert env.events == [("delete", "shop-02")]


def test_bulk_delete_includes_running_profiles():
    env = _env(names=("shop-01", "shop-02", "shop-03"), running=("shop-01", "shop-03"))
    for name in ("shop-01", "shop-02", "shop-03"):
        env.state.toggle_selection(name)
    env.h.on_bulk_delete()
    confirm = env.fake.dialogs[-1]
    texts = _texts(confirm)
    assert "Delete 3 profile(s)?" in texts
    assert "This action cannot be undone. 2 of them are running and will be stopped first." in texts
    confirm.actions[-1].on_click(None)
    _drain(env.fake)
    stops = [e for e in env.events if e[0] == "stop"]
    deletes = [e for e in env.events if e[0] == "delete"]
    assert stops == [("stop", "shop-01"), ("stop", "shop-03")]
    assert sorted(deletes) == [("delete", "shop-01"), ("delete", "shop-02"), ("delete", "shop-03")]
    assert env.events.index(stops[-1]) < env.events.index(deletes[0])
    assert not env.pm.profiles and not env.state.selected_names()


def test_bulk_delete_keeps_a_profile_that_would_not_stop():
    env = _env(stops=False)
    for name in ("shop-01", "shop-02"):
        env.state.toggle_selection(name)
    env.h.on_bulk_delete()
    env.fake.dialogs[-1].actions[-1].on_click(None)
    _drain(env.fake)
    assert ("delete", "shop-02") in env.events and ("delete", "shop-01") not in env.events
    assert "Could not stop shop-01" in env.logs


# --- rename -------------------------------------------------------------------------


def _save_as(env, new_name):
    dlg = env.fake.dialogs[-1]
    name_field = next(c for c in _walk(dlg) if isinstance(c, ft.TextField))
    name_field.value = new_name
    dlg.actions[-1].on_click(None)


def test_rename_a_running_profile_stops_it_then_saves():
    env = _env()
    env.h.on_edit("shop-01")
    _save_as(env, "shop-renamed")
    confirm = env.fake.dialogs[-1]
    assert "shop-01 is running. Stop its browser to rename it?" in _texts(confirm)
    assert confirm.actions[-1].content == "Stop and save"
    assert confirm.actions[-1].style is INK_STYLE
    assert len(env.fake.dialogs) == 2 and not any(e[0] == "update" for e in env.events)
    confirm.actions[-1].on_click(None)
    assert len(env.fake.dialogs) == 1  # the profile dialog waits for the stop
    _drain(env.fake)
    assert env.events == [
        ("run_stop", "shop-01"),
        ("stop", "shop-01"),
        ("update", "shop-01", "shop-renamed"),
        ("reassign", "shop-01", "shop-renamed"),
    ]
    assert not env.fake.dialogs


def test_rename_cancelled_keeps_the_dialog_open():
    env = _env()
    env.h.on_edit("shop-01")
    _save_as(env, "shop-renamed")
    env.fake.dialogs[-1].actions[0].on_click(None)  # Cancel
    assert len(env.fake.dialogs) == 1 and env.events == []


def test_save_without_rename_while_running_saves_at_once():
    env = _env()
    env.h.on_edit("shop-01")
    _save_as(env, "shop-01")
    assert env.events == [("update", "shop-01", "shop-01")]
    assert not env.fake.dialogs and not env.fake.tasks


# --- clone ------------------------------------------------------------------------


def test_clone_stop_browser_enables_the_data_options():
    env = _env()
    env.h.on_clone("shop-01")
    dlg = env.fake.dialogs[-1]
    boxes = {c.label: c for c in _walk(dlg) if isinstance(c, ft.Checkbox)}
    data = [get_string(f"clone_part_{part}") for part in PARTS]
    assert len(data) == 5 and all(boxes[label].disabled for label in data)
    stop = _button(dlg, "Stop browser")
    assert stop.style is INK_STYLE and stop.visible
    assert "Stop the profile to copy its data." in _texts(dlg)
    stop.on_click(None)
    assert stop.disabled
    _drain(env.fake)
    assert ("stop", "shop-01") in env.events
    assert not any(boxes[label].disabled for label in data)
    note = next(
        c
        for c in _walk(dlg)
        if isinstance(c, ft.Container)
        and isinstance(c.content, ft.Row)
        and stop in c.content.controls
    )
    assert not note.visible
    assert env.fake.dialogs[-1] is dlg  # the same dialog, not reopened


def test_clone_stop_that_fails_keeps_the_options_off():
    env = _env(stops=False)
    env.h.on_clone("shop-01")
    dlg = env.fake.dialogs[-1]
    stop = _button(dlg, "Stop browser")
    stop.on_click(None)
    _drain(env.fake)
    boxes = [c for c in _walk(dlg) if isinstance(c, ft.Checkbox)]
    assert boxes[0].disabled and not stop.disabled
    assert "Could not stop shop-01" in env.logs


# --- Record workflow with no profiles / Run with no workflows -------------------------


@pytest.fixture
def no_recording(monkeypatch):
    from src.ui.dialogs import workflows as wf_dialog

    started = []
    monkeypatch.setattr(
        wf_dialog.recording,
        "status",
        lambda bl, name: {"recording": False, "draft": False, "step_count": 0, "recent": []},
    )
    monkeypatch.setattr(wf_dialog.recording, "start", lambda bl, runner, name: started.append(name))
    return started


def _automation(env):
    from src.ui.actions.automation import AutomationHandlers

    launched = []

    def launch(name):
        launched.append(name)
        env.state.set_loading(name, True)

    auto = AutomationHandlers(
        env.pm,
        env.bl,
        env.wf,
        get_page=lambda: env.fake,
        get_recording=set,
        on_changed=lambda: None,
        launch=launch,
        is_loading=env.state.is_loading,
        add_profile=lambda on_created: env.h.open_add_dialog(on_created=on_created),
    )
    return auto, launched


def test_record_with_no_profiles_creates_one_then_records_in_it(no_recording):
    env = _env(running=(), names=())
    auto, launched = _automation(env)
    auto.record()
    dlg = env.fake.dialogs[-1]
    assert "A workflow is recorded in a profile's browser. Create a profile to start." in _texts(
        dlg
    )
    new = _button(dlg, "New Profile")
    assert new.style is ACCENT_STYLE
    new.on_click(None)
    assert len(env.fake.dialogs) == 1
    assert get_string("create_new_profile") in _texts(env.fake.dialogs[-1])
    _save_as(env, "shop-new")
    assert ("add", "shop-new") in env.events
    # The create dialog closed and the recorder opened for the new profile, launching it.
    assert len(env.fake.dialogs) == 1
    assert launched == ["shop-new"]
    assert any(
        "Launching shop-new" in t and "Recording starts" in t for t in _texts(env.fake.dialogs[-1])
    )


def test_run_with_no_workflows_opens_record_workflow():
    env = _env(workflows=[])
    auto, _ = _automation(env)
    auto.open_run(profiles={"shop-02"})
    dlg = env.fake.dialogs[-1]
    texts = _texts(dlg)
    assert "Record a workflow" in texts
    assert "No workflows yet. Pick a profile to record the first one." in texts
    assert "shop-01" in texts and "shop-02" in texts


def test_run_with_workflows_still_opens_the_run_dialog():
    env = _env()
    auto, _ = _automation(env)
    auto.open_run(profiles={"shop-02"})
    assert "Run workflow" in _texts(env.fake.dialogs[-1])


# --- AI steps before AI is set up ---------------------------------------------------


@pytest.fixture
def ai_env(monkeypatch, tmp_path):
    from src.services.ai import settings as ai_settings

    monkeypatch.setattr(ai_settings, "OPENAI_API_KEY", "")
    env = _env(running=())
    env.wf.ai = ai_settings.AISettingsStore(str(tmp_path / "ai.json"))
    env.wf.store.steps = [SimpleNamespace(enabled=True, action="ai")]
    return env


def test_run_dialog_with_ai_steps_opens_ai_settings_and_stays_open(ai_env):
    from src.ui.dialogs.run_workflow import open_run_dialog

    env = ai_env
    open_run_dialog(
        env.fake,
        env.wf,
        ["shop-01", "shop-02"],
        set(),
        set(),
        workflow="login",
        preselect=["shop-02"],
    )
    run_dlg = env.fake.dialogs[-1]
    asyncio.run(run_dlg.actions[-1].on_click(None))
    message = "This workflow has AI text steps: set up AI first, then run it again."
    assert env.wf.runner.started == []
    assert message in env.logs and message in _texts(run_dlg)
    assert len(env.fake.dialogs) == 2 and env.fake.dialogs[0] is run_dlg
    assert "AI settings" in _texts(env.fake.dialogs[-1])

    # Saved a key: Run works from the same dialog.
    settings = env.wf.ai.load()
    settings.api_key = "sk-test-0000000000"
    env.wf.ai.save(settings)
    env.fake.pop_dialog()
    asyncio.run(run_dlg.actions[-1].on_click(None))
    assert env.wf.runner.started == [("login", "shop-02", {})]


def test_disabled_ai_steps_do_not_need_ai(ai_env):
    from src.ui.dialogs.run_workflow import open_run_dialog

    env = ai_env
    env.wf.store.steps = [SimpleNamespace(enabled=False, action="ai")]
    open_run_dialog(
        env.fake, env.wf, ["shop-02"], set(), set(), workflow="login", preselect=["shop-02"]
    )
    asyncio.run(env.fake.dialogs[-1].actions[-1].on_click(None))
    assert env.wf.runner.started == [("login", "shop-02", {})]


def test_run_again_with_ai_steps_opens_ai_settings(ai_env):
    env = ai_env
    auto, _ = _automation(env)
    auto.run_again("login", "shop-02")
    assert not env.fake.tasks and env.wf.runner.started == []
    assert "AI settings" in _texts(env.fake.dialogs[-1])


def test_workflows_dialog_run_with_ai_steps_opens_ai_settings(ai_env, no_recording):
    from src.ui.dialogs.workflows import open_workflows_dialog

    env = ai_env
    open_workflows_dialog(env.fake, "shop-01", env.wf)
    _run_only(env.fake, "load_list")  # not poll: it loops while the dialog is open
    dlg = env.fake.dialogs[-1]
    _button(dlg, "Run").on_click(None)
    _run_only(env.fake, "run_workflow")
    assert env.wf.runner.started == []
    assert "AI settings" in _texts(env.fake.dialogs[-1])
    assert "This workflow has AI text steps: set up AI first, then run it again." in _texts(dlg)
