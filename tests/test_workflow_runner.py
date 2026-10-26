"""Replaying a workflow: a check per step, retries, then a browser restart from step 1."""

import threading
import time

import pytest

from src.services.browser.launcher import BrowserControlError
from src.services.workflow.model import Settings, Step, Workflow
from src.services.workflow.runner import WorkflowRunner
from src.services.workflow.store import WorkflowError, WorkflowStore


class FakeLauncher:
    """Stands in for BrowserLauncher; `fail(step_id)` decides each run_step's outcome."""

    def __init__(self, fail=lambda step, call: None) -> None:
        self.running: set[str] = set()
        self.fail = fail
        self.calls: list[tuple[str, dict]] = []
        self.launches = 0
        self.stops = 0
        self.recording = False
        self._lock = threading.Lock()

    def is_running(self, name):
        return name in self.running

    def start_thread(self, profile, log_callback, on_start=None, on_ready=None, on_stop=None):
        self.launches += 1
        self.running.add(profile.name)
        return True

    def wait_for_launch(self, name, timeout):
        return True, None

    def stop_profile(self, name, timeout=2):
        self.stops += 1
        self.running.discard(name)
        return True

    def control(self, name, action, params=None, timeout=60):
        if name not in self.running:
            raise BrowserControlError("Browser is not running", status=409)
        with self._lock:
            self.calls.append((action, params or {}))
            count = sum(1 for a, p in self.calls if a == action and p == (params or {}))
        if action == "record_status":
            return {"recording": self.recording}
        if action == "run_step":
            error = self.fail(params["step"], count)
            if error:
                raise error
        return {"url": "https://example.test/", "title": "T"}

    def steps_run(self):
        return [p["step"]["id"] for a, p in self.calls if a == "run_step"]


class FakeProfiles:
    def __init__(self, *names):
        from src.models.profile import Profile

        self.profiles = {n: Profile(name=n, os_type="windows") for n in names}


def _workflow(**settings):
    defaults = {"retry_delay_ms": 0, "max_restarts": 2}
    steps = [
        Step(id="s1", action="navigate", value="https://example.test/", delay_ms=0),
        Step(id="s2", action="fill", selectors=["#q"], value="hello", delay_ms=0),
        Step(id="s3", action="click", selectors=["#go"], delay_ms=0),
    ]
    return Workflow(name="wf", steps=steps, settings=Settings(**{**defaults, **settings}))


@pytest.fixture
def make_runner(tmp_path, monkeypatch):
    monkeypatch.setattr(WorkflowRunner, "RESTART_PAUSE_S", 0)

    def build(launcher, workflow=None):
        store = WorkflowStore(str(tmp_path / "workflows"))
        store.save(workflow or _workflow())
        return WorkflowRunner(store, FakeProfiles("p1"), launcher, launch_timeout=5)

    return build


def _wait(runner, profile="p1", timeout=10):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        state = runner.get(profile)
        if state and not state["active"]:
            return state
        time.sleep(0.02)
    raise AssertionError("run did not finish")


def test_run_launches_the_browser_and_runs_every_step(make_runner):
    bl = FakeLauncher()
    runner = make_runner(bl)
    runner.start("wf", "p1")
    state = _wait(runner)
    assert state["status"] == "succeeded"
    assert bl.launches == 1 and bl.stops == 0
    assert bl.steps_run() == ["s1", "s2", "s3"]
    assert [a for a, _ in bl.calls if a != "record_status"][0] == "run_prepare"


def test_a_failing_step_is_retried_before_anything_else(make_runner):
    # s2 fails twice, then passes: two retries, no restart.
    bl = FakeLauncher(
        lambda step, n: BrowserControlError("nope", 422) if step["id"] == "s2" and n <= 2 else None
    )
    runner = make_runner(bl)
    runner.start("wf", "p1")
    state = _wait(runner)
    assert state["status"] == "succeeded"
    assert state["restarts"] == 0 and bl.stops == 0
    assert bl.steps_run() == ["s1", "s2", "s2", "s2", "s3"]


def test_out_of_retries_restarts_the_browser_and_runs_from_step_one(make_runner):
    # s3 fails 3 times (1 try + 2 retries) on the first run only.
    bl = FakeLauncher(
        lambda step, n: BrowserControlError("nope", 422) if step["id"] == "s3" and n <= 3 else None
    )
    runner = make_runner(bl)
    runner.start("wf", "p1")
    state = _wait(runner)
    assert state["status"] == "succeeded"
    assert state["restarts"] == 1
    assert bl.stops == 1 and bl.launches == 2
    assert bl.steps_run() == ["s1", "s2", "s3", "s3", "s3", "s1", "s2", "s3"]


def test_gives_up_after_max_restarts(make_runner):
    bl = FakeLauncher(
        lambda step, n: (
            BrowserControlError("Element not found: #go", 422) if step["id"] == "s3" else None
        )
    )
    runner = make_runner(bl, _workflow(max_restarts=1, retries=1))
    runner.start("wf", "p1")
    state = _wait(runner)
    assert state["status"] == "failed"
    assert "Element not found: #go" in state["error"]
    assert state["restarts"] == 1 and bl.launches == 2
    assert bl.steps_run().count("s3") == 4  # (1 try + 1 retry) x (1 run + 1 restart)


def test_a_closed_browser_restarts_without_retrying(make_runner):
    bl = FakeLauncher()

    def fail(step, n):
        if step["id"] == "s2" and n == 1:
            bl.running.discard("p1")  # the user closed the window
            return BrowserControlError("Browser is not running", 409)
        return None

    bl.fail = fail
    runner = make_runner(bl)
    runner.start("wf", "p1")
    state = _wait(runner)
    assert state["status"] == "succeeded" and state["restarts"] == 1
    assert bl.steps_run() == ["s1", "s2", "s1", "s2", "s3"]


def test_per_step_retries_override_the_workflow(make_runner):
    wf = _workflow(retries=5)
    wf.steps[1].retries = 0
    bl = FakeLauncher(
        lambda step, n: BrowserControlError("x", 422) if step["id"] == "s2" and n == 1 else None
    )
    runner = make_runner(bl, wf)
    runner.start("wf", "p1")
    state = _wait(runner)
    assert state["restarts"] == 1
    assert bl.steps_run()[:3] == ["s1", "s2", "s1"]


def test_speed_scales_typing_and_disabled_steps_are_skipped(make_runner):
    wf = _workflow(speed=2)
    wf.steps[1].char_delay_ms = 100
    wf.steps[2].enabled = False
    bl = FakeLauncher()
    runner = make_runner(bl, wf)
    runner.start("wf", "p1")
    assert _wait(runner)["status"] == "succeeded"
    sent = [p["step"] for a, p in bl.calls if a == "run_step"]
    assert [s["id"] for s in sent] == ["s1", "s2"]
    assert sent[1]["char_delay_ms"] == 50


def test_delays_follow_the_speed(make_runner):
    wf = _workflow(speed=4)
    wf.steps[1].delay_ms = 800  # 0.2 s at x4
    runner = make_runner(FakeLauncher(), wf)
    started = time.monotonic()
    runner.start("wf", "p1")
    _wait(runner)
    assert 0.15 < time.monotonic() - started < 0.8


def test_stop_ends_the_run(make_runner):
    wf = _workflow()
    wf.steps[1].delay_ms = 5_000
    runner = make_runner(FakeLauncher(), wf)
    runner.start("wf", "p1")
    time.sleep(0.2)
    assert runner.stop("p1")
    state = _wait(runner, timeout=3)
    assert state["status"] == "stopped"
    assert not runner.stop("p1")


def test_close_when_done_stops_the_browser(make_runner):
    bl = FakeLauncher()
    runner = make_runner(bl, _workflow(close_when_done=True))
    runner.start("wf", "p1")
    assert _wait(runner)["status"] == "succeeded"
    assert bl.stops == 1 and not bl.running


def test_start_refusals(make_runner):
    bl = FakeLauncher()
    runner = make_runner(bl)
    with pytest.raises(WorkflowError) as e:
        runner.start("missing", "p1")
    assert e.value.status == 404
    with pytest.raises(WorkflowError) as e:
        runner.start("wf", "nobody")
    assert e.value.status == 404

    bl.running.add("p1")
    bl.recording = True
    with pytest.raises(WorkflowError, match="recording") as e:
        runner.start("wf", "p1")
    assert e.value.status == 409

    bl.recording = False
    wf = _workflow()
    wf.steps[1].delay_ms = 5_000
    runner._store.save(wf)
    runner.start("wf", "p1")
    with pytest.raises(WorkflowError) as e:
        runner.start("wf", "p1")
    assert e.value.status == 409
    runner.stop("p1")
    _wait(runner)
