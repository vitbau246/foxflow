"""Triggers: webhook, clipboard, new file and schedule -> open profiles, run workflows, close."""

import json
import os
import time

import pytest

from src.services.automation.engine import AutomationEngine
from src.services.automation.model import Automation, Trigger
from src.services.automation.store import AutomationError, AutomationStore
from src.services.browser.launcher import BrowserControlError
from src.services.workflow.model import Settings, Step, Workflow
from src.services.workflow.runner import WorkflowRunner
from src.services.workflow.store import WorkflowStore
from src.utils.clipboard import ClipboardUnavailable
from tests.test_workflow_runner import FakeLauncher, FakeProfiles


class Clipboard:
    def __init__(self, text="", count=None):
        self.text, self.count, self.error = text, count, None

    def read(self):
        if self.error:
            raise ClipboardUnavailable(self.error)
        return self.text

    def copy(self, text):
        self.text = text
        if self.count is not None:
            self.count += 1


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(WorkflowRunner, "RESTART_PAUSE_S", 0)
    monkeypatch.setattr(AutomationEngine, "BUSY_RETRY_S", 0.05)
    monkeypatch.setattr(AutomationEngine, "RUN_POLL_S", 0.02)
    workflows = WorkflowStore(str(tmp_path / "workflows"))
    workflows.save(
        Workflow(
            name="open",
            steps=[Step(id="o1", action="navigate", value="https://example.test/", delay_ms=0)],
            settings=Settings(retry_delay_ms=0, max_restarts=0),
        )
    )
    workflows.save(
        Workflow(
            name="post",
            variables={"title": "none"},
            steps=[
                Step(
                    id="p1",
                    action="fill",
                    selectors=["#q"],
                    value="{{trigger_type}}|{{trigger_text}}|{{trigger_file_name}}|{{title}}",
                    delay_ms=0,
                )
            ],
            settings=Settings(retry_delay_ms=0, max_restarts=0),
        )
    )
    bl = FakeLauncher()
    runner = WorkflowRunner(workflows, FakeProfiles("p1", "p2"), bl, launch_timeout=5)
    store = AutomationStore(str(tmp_path / "automations.json"))
    clip = Clipboard()
    now = [1_000_000.0]
    engine = AutomationEngine(
        store,
        runner,
        bl,
        FakeProfiles("p1", "p2"),
        read_clipboard=clip.read,
        clipboard_count=lambda: clip.count,
        clock=lambda: now[0],
    )

    class Env:
        pass

    e = Env()
    e.__dict__.update(
        bl=bl, runner=runner, store=store, engine=engine, clip=clip, now=now, tmp=tmp_path
    )
    return e


def _add(env, trigger, **kw):
    a = Automation(
        name=kw.pop("name", "t"), trigger=trigger, profiles=["p1"], workflows=["post"], **kw
    )
    return env.store.save(a)


def _settle(env, automation_id, timeout=10):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        state = env.engine.status(automation_id)
        last = state["last"]
        idle = not state["queued"] and not state["active"]
        if idle and last and last["status"] not in ("queued", "running"):
            return state
        time.sleep(0.02)
    raise AssertionError("the trigger did not finish")


def _typed(env):
    return [
        p["step"]["value"] for a, p in env.bl.calls if a == "run_step" and p["step"]["id"] == "p1"
    ]


# --- model and store ----------------------------------------------------------------


def test_trigger_settings_are_checked():
    assert Trigger(type="schedule", at=["9:30", "18:00", "09:30"]).at == ["09:30", "18:00"]
    assert len(Trigger(key="").key) >= 16  # a blank key gets a new one
    for bad in (
        {"type": "schedule"},
        {"type": "file"},
        {"type": "clipboard", "pattern": "("},
        {"type": "schedule", "at": ["25:00"]},
        {"key": "short"},
    ):
        with pytest.raises(ValueError):
            Trigger(**bad)
    with pytest.raises(ValueError):
        Automation(name="x", profiles=[], workflows=["a"])


def test_store_keeps_names_unique_and_follows_renamed_profiles(tmp_path):
    store = AutomationStore(str(tmp_path / "a.json"))
    a = store.save(Automation(name="Inbox", profiles=["p1"], workflows=["w"]))
    with pytest.raises(AutomationError):
        store.save(Automation(name="inbox", profiles=["p1"], workflows=["w"]))
    store.rename_profile("p1", "p9")
    again = AutomationStore(str(tmp_path / "a.json"))
    assert again.get("INBOX").profiles == ["p9"] and again.get(a.id).created_at
    assert again.delete("Inbox") and again.list() == []


# --- what a firing does ----------------------------------------------------------------


def test_a_firing_runs_the_chain_in_every_profile_and_closes_what_it_opened(env):
    a = env.store.save(
        Automation(
            name="both",
            profiles=["p1", "p2"],
            workflows=["open", "post"],
            variables={"title": "fixed"},
        )
    )
    env.bl.running.add("p2")  # already open: left open
    env.engine.fire(a.id, "manual", text="hello")
    state = _settle(env, a.id)
    assert state["last"]["status"] == "succeeded", state["last"]["detail"]
    assert state["last"]["runs"] == {"p1": "succeeded", "p2": "succeeded"}
    assert _typed(env) == ["manual|hello||fixed", "manual|hello||fixed"]
    assert env.bl.running == {"p2"}
    assert env.runner.get("p1")["origin"] == "both"


def test_a_busy_profile_is_waited_for_and_failures_are_reported(env, monkeypatch):
    a = _add(env, Trigger())
    env.bl.fail = lambda step, n: BrowserControlError("nope", status=500)
    env.engine.fire(a.id)
    state = _settle(env, a.id)
    assert state["last"]["status"] == "failed" and "p1" in state["last"]["detail"]

    env.bl.fail = lambda step, n: None
    busy = {"left": 3}
    real = env.runner.start_chain

    def start_chain(*args, **kw):
        if busy["left"]:
            busy["left"] -= 1
            from src.services.workflow.store import WorkflowError

            raise WorkflowError("already running", status=409)
        return real(*args, **kw)

    monkeypatch.setattr(env.runner, "start_chain", start_chain)
    env.engine.fire(a.id)
    state = _settle(env, a.id)
    assert state["last"]["status"] == "succeeded" and busy["left"] == 0
    assert [e["status"] for e in state["history"]] == ["succeeded", "failed"]


def test_events_wait_in_line(env):
    a = _add(env, Trigger())
    for text in ("one", "two", "three"):
        env.engine.fire(a.id, text=text)
    state = _settle(env, a.id)
    assert [e["status"] for e in state["history"]] == ["succeeded"] * 3
    assert [v.split("|")[1] for v in _typed(env)] == ["one", "two", "three"]


# --- watching -----------------------------------------------------------------------


def test_clipboard_fires_on_new_matching_text_only(env):
    a = _add(env, Trigger(type="clipboard", pattern=r"https?://"))
    env.clip.text = "already there"
    env.engine.tick()  # the starting point: nothing fires
    env.clip.copy("just words")
    env.engine.tick()
    env.clip.copy("see https://example.test/item/1")
    env.engine.tick()
    env.engine.tick()  # unchanged: no second firing
    state = _settle(env, a.id)
    assert len(state["history"]) == 1
    assert _typed(env) == ["clipboard|see https://example.test/item/1||none"]

    env.clip.error = "no clipboard tool found"
    env.engine.tick()
    assert "no clipboard tool" in env.engine.status(a.id)["error"]


def test_copying_the_same_text_again_counts_where_the_os_counts_copies(env):
    a = _add(env, Trigger(type="clipboard"))
    env.clip.count = 1
    env.clip.text = "x"
    env.engine.tick()
    env.clip.copy("x")
    env.engine.tick()
    assert len(_settle(env, a.id)["history"]) == 1


def test_a_new_file_fires_once_it_is_written(env):
    folder = env.tmp / "inbox"
    folder.mkdir()
    (folder / "old.txt").write_text("old", encoding="utf-8")
    a = _add(env, Trigger(type="file", folder=str(folder), pattern="*.txt"))
    env.engine.tick()  # files already there do not count
    (folder / "order.txt").write_text("ORDER-42", encoding="utf-8")
    (folder / "photo.png").write_bytes(b"\x89PNG")
    (folder / "next.txt.part").write_text("partial", encoding="utf-8")
    env.engine.tick()  # seen, maybe still being written
    assert env.engine.status(a.id)["last"] is None
    env.engine.tick()  # unchanged since: finished
    env.engine.tick()
    state = _settle(env, a.id)
    assert len(state["history"]) == 1 and state["last"]["preview"] == "order.txt"
    assert _typed(env) == ["file|ORDER-42|order.txt|none"]

    gone = _add(env, Trigger(type="file", folder=str(env.tmp / "missing")), name="gone")
    env.engine.tick()
    assert "cannot read the folder" in env.engine.status(gone.id)["error"]


def test_schedules_run_on_an_interval_and_at_times(env):
    every = _add(env, Trigger(type="schedule", every_minutes=5), name="every")
    env.engine.tick()
    env.now[0] += 4 * 60
    env.engine.tick()
    assert env.engine.status(every.id)["last"] is None
    env.now[0] += 60
    env.engine.tick()
    env.engine.tick()
    assert len(_settle(env, every.id)["history"]) == 1

    minute = time.strftime("%H:%M", time.localtime(env.now[0]))
    daily = _add(env, Trigger(type="schedule", at=[minute]), name="daily")
    env.engine.tick()
    env.engine.tick()  # the same minute: once
    assert len(_settle(env, daily.id)["history"]) == 1


def test_turned_off_triggers_do_not_watch(env):
    a = _add(env, Trigger(type="clipboard"), enabled=False)
    env.engine.tick()
    env.clip.copy("new")
    env.engine.tick()
    assert env.engine.status(a.id)["last"] is None


# --- API and webhooks ----------------------------------------------------------------


@pytest.fixture
def api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from src.api.app import create_app
    from src.core.container import Container

    monkeypatch.chdir(tmp_path)
    container = Container()
    calls = []
    container.automation_engine.fire = lambda ref, source="manual", **kw: (
        calls.append((ref, source, kw)) or {"id": "e1", "status": "queued"}
    )
    client = TestClient(create_app(container), base_url="http://127.0.0.1")
    base = "/api/v1"
    assert client.post(f"{base}/profiles", json={"name": "p1"}).status_code == 201
    wf = {"name": "w", "steps": [{"action": "wait", "value": "1"}]}
    assert client.put(f"{base}/workflows/w", json=wf).status_code == 200
    return client, calls, container


def test_trigger_crud_and_fire(api):
    client, calls, _ = api
    body = {"name": "Inbox", "profiles": ["p1"], "workflows": ["w"]}
    bad = client.post("/api/v1/automations", json={**body, "profiles": ["nope"]})
    assert bad.status_code == 400 and "profile 'nope'" in bad.json()["detail"]
    created = client.post("/api/v1/automations", json=body).json()
    assert created["trigger"]["type"] == "webhook" and len(created["trigger"]["key"]) >= 16
    assert client.post("/api/v1/automations", json=body).status_code == 409
    listed = client.get("/api/v1/automations").json()
    assert [a["name"] for a in listed["automations"]] == ["Inbox"]
    assert listed["hook_path"] == "/hooks"
    changed = client.put(
        "/api/v1/automations/Inbox",
        json={**body, "trigger": {"type": "schedule", "every_minutes": 10}},
    ).json()
    assert changed["id"] == created["id"] and changed["trigger"]["every_minutes"] == 10
    r = client.post("/api/v1/automations/Inbox/fire", json={"text": "hi"})
    assert r.status_code == 202 and calls[-1][:2] == ("Inbox", "manual")
    assert client.delete("/api/v1/automations/Inbox").status_code == 200
    assert client.get("/api/v1/automations/Inbox").status_code == 404


def test_webhooks_need_the_trigger_key(api):
    client, calls, container = api
    created = client.post(
        "/api/v1/automations", json={"name": "hook", "profiles": ["p1"], "workflows": ["w"]}
    ).json()
    hook = f"/api/v1/hooks/{created['id']}"
    key = created["trigger"]["key"]
    assert client.post(hook).status_code == 404
    assert client.post(hook, params={"key": "x" * 32}).status_code == 404
    assert client.post(f"/api/v1/hooks/hook?key={key}").status_code == 404  # names are not ids
    r = client.post(
        hook,
        headers={"X-FoxFlow-Key": key},
        content=json.dumps({"text": "new order", "title": "A", "n": 3, "bad key": 1}),
    )
    assert r.status_code == 202 and r.json()["queued"]
    ref, source, kw = calls[-1]
    assert (ref, source) == (created["id"], "webhook")
    assert kw["text"] == "new order" and kw["variables"] == {
        "text": "new order",
        "title": "A",
        "n": "3",
    }
    assert kw["require_enabled"] is True
    client.get(hook, params={"key": key, "text": "from GET", "title": "B"})
    assert calls[-1][2]["text"] == "from GET" and calls[-1][2]["variables"] == {"title": "B"}
    assert client.post(hook, params={"key": key}, content="x" * 100_001).status_code == 413


def test_webhooks_work_without_the_api_token(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import src.api.app as app_module
    import src.api.auth as auth_module
    from src.core.container import Container

    token = "t" * 32
    monkeypatch.setattr(auth_module, "API_TOKEN", token)
    monkeypatch.setattr(app_module, "API_TOKEN", token)
    monkeypatch.chdir(tmp_path)
    container = Container()
    container.automation_engine.fire = lambda *a, **kw: {"id": "e", "status": "queued"}
    client = TestClient(app_module.create_app(container))
    auth = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/automations").status_code == 401
    assert client.post("/api/v1/profiles", json={"name": "p1"}, headers=auth).status_code == 201
    client.put(
        "/api/v1/workflows/w",
        json={"name": "w", "steps": [{"action": "wait", "value": "1"}]},
        headers=auth,
    )
    created = client.post(
        "/api/v1/automations",
        json={"name": "h", "profiles": ["p1"], "workflows": ["w"]},
        headers=auth,
    ).json()
    hook = f"/api/v1/hooks/{created['id']}?key={created['trigger']['key']}"
    assert client.post(hook).status_code == 202


def test_trigger_variables_are_built_in():
    with pytest.raises(ValueError):
        Workflow(name="x", variables={"trigger_text": "a"})
    wf = Workflow(name="x", steps=[Step(action="fill", selectors=["#a"], value="{{trigger_text}}")])
    from src.services.workflow.model import problems

    assert problems(wf) == []


def test_file_text_is_only_read_for_small_text_files(tmp_path):
    from src.services.automation.engine import _file_text

    small = tmp_path / "a.txt"
    small.write_text("xin chào", encoding="utf-8")
    binary = tmp_path / "b.bin"
    binary.write_bytes(b"\x00\x01")
    assert _file_text(str(small), os.path.getsize(small)) == "xin chào"
    assert _file_text(str(binary), 2) == ""
    assert _file_text(str(small), 10**9) == ""
