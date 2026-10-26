"""Replay a workflow in a profile's browser: delays, checks, retries, restarts.

Runs in the FoxFlow process (desktop app or server), one thread per run and
at most one run per profile. Each step is sent to the browser's control server
(`run_step`), which does it and checks the result. A failed step waits
`retry_delay_ms` and is tried again, `retries` times; when it still fails the
browser is stopped, started again and the workflow restarts from its first
step, up to `max_restarts` times.

Variables ({{name}}) are filled in here before a step is sent, and get_text /
ai results are saved here; "ai" steps never reach the browser: the text is
generated from this process with the AI settings.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from ...core.config import LAUNCH_WAIT_TIMEOUT
from ...core.logging import get_logger
from ...interfaces.protocols import IBrowserLauncher, IProfileManager
from ..ai.client import AIError, generate
from ..ai.settings import AISettingsStore
from ..browser.launcher import BrowserControlError, ProfileBusyError
from .model import (
    BUILT_IN_VARIABLES,
    VARIABLE_NAME,
    Step,
    Workflow,
    problems,
    render,
    scaled,
    uses_ai,
)
from .store import WorkflowError, WorkflowStore

logger = get_logger("workflow.runner")

MAX_LOG_LINES = 300
ACTIVE = ("starting", "running")


class _Restart(Exception):
    """This run of the workflow failed; restart the browser and begin again."""


class _Stopped(Exception):
    pass


class RunState:
    def __init__(self, workflow: Workflow, profile: str) -> None:
        self.workflow = workflow.name
        self.profile = profile
        self.status = "starting"  # starting, running, succeeded, failed, stopped
        self.started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.finished_at = ""
        self.step = 0
        self.step_total = sum(1 for s in workflow.steps if s.enabled)
        self.step_label = ""
        self.attempt = 0
        self.restarts = 0
        self.max_restarts = workflow.settings.max_restarts
        self.error = ""
        self.log: list[str] = []
        self.stop_event = threading.Event()
        # Values of {{variables}} during the current run (set again on a restart).
        self.variables: dict[str, str] = {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow": self.workflow,
            "profile": self.profile,
            "status": self.status,
            "active": self.status in ACTIVE,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "step": self.step,
            "step_total": self.step_total,
            "step_label": self.step_label,
            "attempt": self.attempt,
            "restarts": self.restarts,
            "max_restarts": self.max_restarts,
            "error": self.error,
            "variables": {k: _short(v, 200) for k, v in self.variables.items()},
            "log": list(self.log[-100:]),
        }


def _short(text: str, limit: int = 80) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _render(step: Step, variables: dict[str, str]) -> dict[str, Any]:
    """The step as sent: every {{variable}} replaced. KeyError for one with no value."""
    data = step.model_dump()
    # get_text's value is a regex: its braces are its own.
    if step.action != "get_text":
        data["value"] = render(step.value, variables)
    for key in ("frame", "expect_url"):
        data[key] = render(data[key], variables)
    data["check"]["value"] = render(step.check.value, variables)
    data["selectors"] = [render(s, variables) for s in step.selectors]
    data["hover_selectors"] = [render(s, variables) for s in step.hover_selectors]
    return data


class WorkflowRunner:
    # Between stopping a failed run's browser and starting it again.
    RESTART_PAUSE_S = 1.5

    def __init__(
        self,
        store: WorkflowStore,
        pm: IProfileManager,
        bl: IBrowserLauncher,
        on_change: Callable[[], None] | None = None,
        launch_timeout: float = LAUNCH_WAIT_TIMEOUT,
        ai_settings: AISettingsStore | None = None,
        ai_generate: Callable[..., str] = generate,
    ) -> None:
        self._store = store
        self._ai_settings = ai_settings or AISettingsStore()
        self._ai_generate = ai_generate
        self._pm = pm
        self._bl = bl
        self._on_change = on_change or (lambda: None)
        self._launch_timeout = launch_timeout
        self._runs: dict[str, RunState] = {}
        self._lock = threading.Lock()

    # --- public -------------------------------------------------------------

    def start(
        self,
        workflow_name: str,
        profile_name: str,
        variables: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Start a run; `variables` overrides the workflow's starting values for it."""
        workflow = self._store.get(workflow_name)
        if workflow is None:
            raise WorkflowError(f"Workflow '{workflow_name}' not found", status=404)
        for name in variables or {}:
            if not VARIABLE_NAME.match(name) or name in BUILT_IN_VARIABLES:
                raise WorkflowError(f"'{name}' cannot be used as a variable name")
        workflow.variables = {**workflow.variables, **(variables or {})}
        if profile_name not in self._pm.profiles:
            raise WorkflowError(f"Profile '{profile_name}' not found", status=404)
        if not any(s.enabled for s in workflow.steps):
            raise WorkflowError("The workflow has no enabled steps")
        if issues := problems(workflow):
            raise WorkflowError("; ".join(issues[:5]))
        if uses_ai(workflow) and not self._ai_settings.load().api_key:
            raise WorkflowError("The workflow has AI steps: set up AI (an API key) first")
        if self._recording(profile_name):
            # The run would fail on it, then restart the browser and lose the recording.
            raise WorkflowError(
                f"'{profile_name}' is recording; stop the recording first", status=409
            )
        with self._lock:
            current = self._runs.get(profile_name)
            if current and current.status in ACTIVE:
                raise WorkflowError(
                    f"Workflow '{current.workflow}' is already running in '{profile_name}'",
                    status=409,
                )
            state = self._runs[profile_name] = RunState(workflow, profile_name)
        threading.Thread(
            target=self._run, args=(state, workflow), name=f"workflow-{profile_name}", daemon=True
        ).start()
        self._on_change()
        return state.to_dict()

    def stop(self, profile_name: str) -> bool:
        """Ask a profile's run to stop; it ends after the action in progress."""
        with self._lock:
            state = self._runs.get(profile_name)
        if not state or state.status not in ACTIVE:
            return False
        state.stop_event.set()
        return True

    def get(self, profile_name: str) -> dict[str, Any] | None:
        with self._lock:
            state = self._runs.get(profile_name)
        return state.to_dict() if state else None

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            states = list(self._runs.values())
        return [s.to_dict() for s in states]

    def is_active(self, profile_name: str) -> bool:
        with self._lock:
            state = self._runs.get(profile_name)
        return bool(state and state.status in ACTIVE)

    def _recording(self, profile_name: str) -> bool:
        if not self._bl.is_running(profile_name):
            return False
        try:
            status = self._bl.control(profile_name, "record_status", {}, timeout=10)
        except BrowserControlError:
            return False
        return bool(status and status.get("recording"))

    def stop_all(self) -> None:
        with self._lock:
            states = list(self._runs.values())
        for state in states:
            state.stop_event.set()

    # --- the run ------------------------------------------------------------

    def _log(self, state: RunState, message: str) -> None:
        line = f"{time.strftime('%H:%M:%S')} {message}"
        state.log.append(line)
        del state.log[:-MAX_LOG_LINES]
        logger.info("[%s/%s] %s", state.profile, state.workflow, message)

    def _set(self, state: RunState, **changes: Any) -> None:
        for key, value in changes.items():
            setattr(state, key, value)
        self._on_change()

    def _pause(self, state: RunState, seconds: float) -> None:
        if seconds > 0 and state.stop_event.wait(seconds):
            raise _Stopped
        if state.stop_event.is_set():
            raise _Stopped

    def _run(self, state: RunState, workflow: Workflow) -> None:
        settings = workflow.settings
        steps = [s for s in workflow.steps if s.enabled]
        try:
            while True:
                try:
                    self._log(
                        state,
                        f"Run {state.restarts + 1}/{settings.max_restarts + 1}: "
                        f"{len(steps)} steps at speed x{settings.speed:g}",
                    )
                    state.variables = {**workflow.variables, "profile": state.profile}
                    self._ensure_browser(state)
                    self._set(state, status="running")
                    self._prepare(state)
                    for index, step in enumerate(steps, start=1):
                        self._run_step(state, workflow, index, step)
                    break
                except _Restart as failure:
                    if state.stop_event.is_set():
                        raise _Stopped from failure
                    if state.restarts >= settings.max_restarts:
                        self._finish(state, "failed", str(failure))
                        return
                    self._set(state, restarts=state.restarts + 1)
                    self._log(
                        state,
                        f"Restarting the browser and running from step 1 "
                        f"({state.restarts}/{settings.max_restarts})",
                    )
                    self._bl.stop_profile(state.profile)
                    self._pause(state, self.RESTART_PAUSE_S)
            self._log(state, f"Finished all {len(steps)} steps")
            if settings.close_when_done:
                self._bl.stop_profile(state.profile)
            self._finish(state, "succeeded")
        except _Stopped:
            self._log(state, "Stopped")
            self._finish(state, "stopped")
        except WorkflowError as e:
            self._finish(state, "failed", str(e))
        except Exception as e:  # a bug must not leave the run "running" for good
            logger.exception("Workflow run crashed")
            self._finish(state, "failed", f"{type(e).__name__}: {e}")

    def _finish(self, state: RunState, status: str, error: str = "") -> None:
        if error:
            self._log(state, f"Failed: {error}")
        self._set(
            state,
            status=status,
            error=error,
            finished_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )

    def _ensure_browser(self, state: RunState) -> None:
        if self._bl.is_running(state.profile):
            return
        profile = self._pm.profiles.get(state.profile)
        if profile is None:
            raise WorkflowError(f"Profile '{state.profile}' no longer exists")
        self._log(state, "Launching the browser")
        try:
            started = self._bl.start_thread(
                profile,
                lambda message: logger.debug("[%s] %s", state.profile, message),
                on_ready=self._on_change,
                on_stop=self._on_change,
            )
        except ProfileBusyError as e:
            raise _Restart("The profile is busy (cookie export/import in progress)") from e
        if started:
            ok, error = self._bl.wait_for_launch(state.profile, self._launch_timeout)
            if not ok:
                raise _Restart(f"The browser did not start: {error}")

    def _prepare(self, state: RunState) -> None:
        """Leave one tab open; wait while a just-started browser sets up control."""
        for _ in range(30):
            try:
                self._bl.control(state.profile, "run_prepare", {}, timeout=30)
                return
            except BrowserControlError as e:
                if e.status != 503:
                    raise _Restart(f"Could not take control of the browser: {e}") from e
                self._pause(state, 1)
        raise _Restart("The browser did not accept control in time")

    def _run_step(self, state: RunState, workflow: Workflow, index: int, step: Step) -> None:
        settings = workflow.settings
        label = f"{step.action} {step.label}".strip()
        self._set(state, step=index, step_label=label, attempt=0)
        self._pause(state, scaled(step.delay_ms, settings.speed))

        timeout_ms = step.timeout_ms or settings.step_timeout_ms
        retries = settings.retries if step.retries is None else step.retries
        try:
            payload = _render(step, state.variables)
        except KeyError as e:
            raise _Restart(f"Step {index} ({label}): {{{{{e.args[0]}}}}} has no value") from e
        # Typing speed and the pause after hovering follow the workflow speed.
        payload["char_delay_ms"] = round(step.char_delay_ms / settings.speed)
        payload["hover_ms"] = round(step.hover_ms / settings.speed)
        wait_ms = int(step.value) if step.action == "wait" and step.value.isdigit() else 0
        # The action and its check each get timeout_ms; leave room for both.
        http_timeout = (2 * timeout_ms + wait_ms + step.hover_ms) / 1000 + 30

        def attempt_once() -> dict[str, Any]:
            if step.action == "ai":
                text = self._ai_generate(
                    self._ai_settings.load(), payload["value"], timeout=timeout_ms / 1000
                )
                return {"text": text}
            return self._bl.control(
                state.profile,
                "run_step",
                {"step": payload, "timeout_ms": timeout_ms},
                timeout=http_timeout,
            )

        for attempt in range(retries + 1):
            self._set(state, attempt=attempt + 1)
            try:
                result = attempt_once() or {}
                self._log(state, f"Step {index}/{state.step_total} ok: {label}")
                if step.save_as:
                    value = str(result.get("text") or "")
                    state.variables[step.save_as] = value
                    shown = "•••" if step.sensitive else f"“{_short(value)}”"
                    self._log(state, f"  {{{{{step.save_as}}}}} = {shown}")
                return
            except (BrowserControlError, AIError) as e:
                if state.stop_event.is_set():
                    raise _Stopped from e
                self._log(state, f"Step {index}/{state.step_total} failed: {label}: {e}")
                # The browser is gone: retrying cannot help.
                if isinstance(e, BrowserControlError) and e.status == 409:
                    raise _Restart(f"Step {index} ({label}): {e}") from e
                if attempt < retries:
                    self._log(state, f"Retrying step {index} ({attempt + 1}/{retries})")
                    self._pause(state, settings.retry_delay_ms / 1000)
                    continue
                raise _Restart(f"Step {index} ({label}): {e}") from e
