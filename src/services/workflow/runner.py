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

The flow of a run is worked out here too: assign, if / else / end, for, while
and break are run by this process; only an if / while that tests the page
asks the browser (run_step answers {"result": bool}).

A run may chain several workflows in one browser, one after the other: each
uses its own settings and restarts from its own first step, and the variables
saved by one carry over to the next. The chain stops at the first that fails.
"""

from __future__ import annotations

import re
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
from .expression import ExpressionError, evaluate, to_text, truthy
from .model import (
    BUILT_IN_VARIABLES,
    LOOP_ACTIONS,
    MARKER_ACTIONS,
    MAX_LOOP_ROUNDS,
    MAX_VARIABLE_TEXT,
    TRIGGER_VARIABLES,
    VARIABLE_NAME,
    Block,
    Step,
    Workflow,
    blocks,
    problems,
    render,
    scaled,
    uses_ai,
)
from .store import WorkflowError, WorkflowStore

logger = get_logger("workflow.runner")

MAX_LOG_LINES = 300
ACTIVE = ("starting", "running")
MAX_CHAIN = 20


class _Restart(Exception):
    """This run of the workflow failed; restart the browser and begin again."""


class _Stopped(Exception):
    pass


class RunState:
    def __init__(self, workflows: list[Workflow], profile: str) -> None:
        workflow = workflows[0]
        # The chain, in order; `workflow` is the one running now.
        self.workflows = [w.name for w in workflows]
        self.workflow_index = 0
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
        # Set when a trigger started the run: its name, and {{trigger_*}} values.
        self.origin = ""
        self.trigger: dict[str, str] = {}

    def to_dict(self, log: bool = True) -> dict[str, Any]:
        return {
            "workflow": self.workflow,
            "workflows": list(self.workflows),
            "workflow_index": self.workflow_index + 1,
            "workflow_count": len(self.workflows),
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
            "origin": self.origin,
            "variables": {k: _short(v, 200) for k, v in self.variables.items()},
            "log": list(self.log[-100:]) if log else [],
        }


def _short(text: str, limit: int = 80) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _render(step: Step, variables: dict[str, str]) -> dict[str, Any]:
    """The step as sent: every {{variable}} replaced. KeyError for one with no value."""
    data = step.model_dump()
    if step.value_is_template():
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
        return self.start_chain([workflow_name], profile_name, variables)

    def start_chain(
        self,
        workflow_names: list[str],
        profile_name: str,
        variables: dict[str, str] | None = None,
        *,
        trigger: dict[str, str] | None = None,
        origin: str = "",
    ) -> dict[str, Any]:
        """Run several workflows one after the other in one profile.

        `variables` overrides the starting values of every workflow that has them.
        `trigger` holds the {{trigger_*}} values and `origin` names the trigger
        that started the run.
        """
        if not workflow_names:
            raise WorkflowError("Pick at least one workflow")
        if len(workflow_names) > MAX_CHAIN:
            raise WorkflowError(f"At most {MAX_CHAIN} workflows in one run")
        for name in variables or {}:
            if not VARIABLE_NAME.match(name) or name in BUILT_IN_VARIABLES:
                raise WorkflowError(f"'{name}' cannot be used as a variable name")
        if profile_name not in self._pm.profiles:
            raise WorkflowError(f"Profile '{profile_name}' not found", status=404)
        workflows = [
            self._ready(name, variables or {}, only_known=len(workflow_names) > 1)
            for name in workflow_names
        ]
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
            state = self._runs[profile_name] = RunState(workflows, profile_name)
            state.origin = origin
            state.trigger = {
                k: str(v)[:MAX_VARIABLE_TEXT]
                for k, v in (trigger or {}).items()
                if k in TRIGGER_VARIABLES
            }
        threading.Thread(
            target=self._run_chain,
            args=(state, workflows),
            name=f"workflow-{profile_name}",
            daemon=True,
        ).start()
        self._on_change()
        return state.to_dict()

    def _ready(self, name: str, variables: dict[str, str], only_known: bool) -> Workflow:
        """The workflow with this run's values, if it can run; WorkflowError otherwise.

        In a chain a workflow takes values only for the variables it has: one
        meant for another workflow must not look like a variable it defines.
        """
        workflow = self._store.get(name)
        if workflow is None:
            raise WorkflowError(f"Workflow '{name}' not found", status=404)
        if only_known:
            variables = {k: v for k, v in variables.items() if k in workflow.variables}
        workflow.variables = {**workflow.variables, **variables}
        if not any(s.enabled for s in workflow.steps):
            raise WorkflowError(f"Workflow '{workflow.name}' has no enabled steps")
        if issues := problems(workflow):
            raise WorkflowError(f"{workflow.name}: " + "; ".join(issues[:5]))
        if uses_ai(workflow) and not self._ai_settings.load().api_key:
            raise WorkflowError(
                f"Workflow '{workflow.name}' has AI steps: set up AI (an API key) first"
            )
        return workflow

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

    def list(self, log: bool = True) -> list[dict[str, Any]]:
        """Every profile's current or last run; without `log` the lines are left out."""
        with self._lock:
            states = list(self._runs.values())
        return [s.to_dict(log) for s in states]

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

    def _run_chain(self, state: RunState, workflows: list[Workflow]) -> None:
        try:
            carried: dict[str, str] = {}
            for i, workflow in enumerate(workflows):
                if len(workflows) > 1:
                    self._set(
                        state,
                        workflow_index=i,
                        workflow=workflow.name,
                        step=0,
                        step_label="",
                        step_total=sum(1 for s in workflow.steps if s.enabled),
                        restarts=0,
                        max_restarts=workflow.settings.max_restarts,
                    )
                    self._log(state, f"Workflow {i + 1}/{len(workflows)}: {workflow.name}")
                if not self._run(state, workflow, carried):
                    return
                carried = {k: v for k, v in state.variables.items() if k != "profile"}
            if workflows[-1].settings.close_when_done:
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

    def _run(self, state: RunState, workflow: Workflow, carried: dict[str, str]) -> bool:
        """One workflow of the chain, with its restarts; False when it failed."""
        settings = workflow.settings
        steps = [s for s in workflow.steps if s.enabled]
        while True:
            try:
                self._log(
                    state,
                    f"Run {state.restarts + 1}/{settings.max_restarts + 1}: "
                    f"{len(steps)} steps at speed x{settings.speed:g}",
                )
                state.variables = {
                    **dict.fromkeys(TRIGGER_VARIABLES, ""),
                    **state.trigger,
                    **workflow.variables,
                    **carried,
                    "profile": state.profile,
                }
                self._ensure_browser(state)
                self._set(state, status="running")
                self._prepare(state)
                self._run_steps(state, workflow, steps)
                break
            except _Restart as failure:
                if state.stop_event.is_set():
                    raise _Stopped from failure
                if state.restarts >= settings.max_restarts:
                    self._finish(state, "failed", str(failure))
                    return False
                self._set(state, restarts=state.restarts + 1)
                self._log(
                    state,
                    f"Restarting the browser and running from step 1 "
                    f"({state.restarts}/{settings.max_restarts})",
                )
                self._bl.stop_profile(state.profile)
                self._pause(state, self.RESTART_PAUSE_S)
        self._log(state, f"Finished all {len(steps)} steps")
        return True

    def _run_steps(self, state: RunState, workflow: Workflow, steps: list[Step]) -> None:
        """The steps in order, following if / else / for / while / break / end."""
        table, _ = blocks([s.action for s in steps])  # problems() checked the structure
        rounds: dict[int, int] = {}  # loop start -> rounds begun
        items: dict[int, list[str]] = {}  # for start -> what it goes through
        pc = 0
        while pc < len(steps):
            step, index = steps[pc], pc + 1
            action = step.action
            block: Block | None = table.get(pc)
            if action == "else":  # the if's branch ran: skip the else part
                pc = block.end + 1
            elif action == "end":
                pc = block.start if steps[block.start].action in LOOP_ACTIONS else pc + 1
            elif action == "break":
                self._mark(state, index, step)
                self._log(state, f"Step {index}/{state.step_total}: leaving the loop")
                rounds.pop(block.start, None)
                items.pop(block.start, None)
                pc = block.end + 1
            elif action == "assign":
                self._assign(state, workflow, index, step)
                pc += 1
            elif action == "if":
                if self._condition(state, workflow, index, step):
                    pc += 1
                else:
                    pc = (block.else_at if block.else_at is not None else block.end) + 1
            elif action == "while":
                done = rounds.get(pc, 0)
                if done >= step.max_loops:
                    self._log(
                        state,
                        f"Step {index}/{state.step_total}: stopped the loop after "
                        f"{done} rounds (the most it may run)",
                    )
                    go = False
                else:
                    go = self._condition(state, workflow, index, step)
                if go:
                    rounds[pc] = done + 1
                    pc += 1
                else:
                    rounds.pop(pc, None)
                    pc = block.end + 1
            elif action == "for":
                if pc not in items:
                    items[pc] = self._for_items(state, workflow, index, step)
                    rounds[pc] = 0
                done = rounds[pc]
                if done < len(items[pc]):
                    rounds[pc] = done + 1
                    item = items[pc][done]
                    if step.save_as:
                        state.variables[step.save_as] = item
                    self._log(
                        state,
                        f"Step {index}/{state.step_total}: round {done + 1}/{len(items[pc])}"
                        + (f", {{{{{step.save_as}}}}} = “{_short(item)}”" if step.save_as else ""),
                    )
                    pc += 1
                else:
                    rounds.pop(pc, None)
                    items.pop(pc, None)
                    pc = block.end + 1
            else:
                self._run_step(state, workflow, index, step)
                pc += 1

    @staticmethod
    def _label(step: Step) -> str:
        what = step.label or (step.value if step.action not in MARKER_ACTIONS else "")
        return f"{step.action} {_short(what, 60)}".strip()

    def _mark(self, state: RunState, index: int, step: Step) -> None:
        self._set(state, step=index, step_label=self._label(step), attempt=0)

    def _assign(self, state: RunState, workflow: Workflow, index: int, step: Step) -> None:
        label = self._label(step)
        self._mark(state, index, step)
        self._pause(state, scaled(step.delay_ms, workflow.settings.speed))
        try:
            if (expression := step.expression()) is not None:
                value = to_text(evaluate(expression, state.variables))
            else:
                value = render(step.value, state.variables)
        except KeyError as e:
            raise _Restart(f"Step {index} ({label}): {{{{{e.args[0]}}}}} has no value") from e
        except ExpressionError as e:
            raise _Restart(f"Step {index} ({label}): {e}") from e
        state.variables[step.save_as] = value[:MAX_VARIABLE_TEXT]
        shown = "•••" if step.sensitive else f"“{_short(value)}”"
        self._log(state, f"Step {index}/{state.step_total}: {{{{{step.save_as}}}}} = {shown}")

    def _for_items(self, state: RunState, workflow: Workflow, index: int, step: Step) -> list[str]:
        """1..N for a number, else the lines (or, on one line, the comma-separated parts)."""
        label = self._label(step)
        self._mark(state, index, step)
        self._pause(state, scaled(step.delay_ms, workflow.settings.speed))
        try:
            text = render(step.value, state.variables).strip()
        except KeyError as e:
            raise _Restart(f"Step {index} ({label}): {{{{{e.args[0]}}}}} has no value") from e
        if re.fullmatch(r"\d+", text):
            return [str(n) for n in range(1, min(int(text), MAX_LOOP_ROUNDS) + 1)]
        parts = [line.strip() for line in text.splitlines() if line.strip()]
        if len(parts) == 1 and "," in parts[0]:
            parts = [p.strip() for p in parts[0].split(",") if p.strip()]
        return parts[:MAX_LOOP_ROUNDS]

    def _condition(self, state: RunState, workflow: Workflow, index: int, step: Step) -> bool:
        """Whether an if / while goes in; the page is asked for page conditions."""
        label = self._label(step)
        if (expression := step.expression()) is not None:
            self._mark(state, index, step)
            self._pause(state, scaled(step.delay_ms, workflow.settings.speed))
            try:
                result = truthy(evaluate(expression, state.variables))
            except ExpressionError as e:
                raise _Restart(f"Step {index} ({label}): {e}") from e
        else:
            result = bool(self._run_step(state, workflow, index, step).get("result"))
        if step.negate:
            result = not result
        self._log(state, f"Step {index}/{state.step_total}: {label} → {str(result).lower()}")
        return result

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

    def _run_step(
        self, state: RunState, workflow: Workflow, index: int, step: Step
    ) -> dict[str, Any]:
        """A browser step (or AI text, or a page condition), retried as the settings say."""
        settings = workflow.settings
        if step.action in ("if", "while"):
            label = self._label(step)
        else:
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
                if step.action in ("if", "while"):
                    return result  # _condition logs the outcome
                self._log(state, f"Step {index}/{state.step_total} ok: {label}")
                if step.save_as:
                    value = str(result.get("text") or "")
                    state.variables[step.save_as] = value
                    shown = "•••" if step.sensitive else f"“{_short(value)}”"
                    self._log(state, f"  {{{{{step.save_as}}}}} = {shown}")
                return result
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
