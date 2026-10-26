"""Watch the triggers and act on them: open profiles, run workflows, close them.

One watcher thread looks, once a second, at the clipboard (clipboard triggers),
the watched folders (file triggers) and the clock (schedules); webhooks and
"Run now" call fire() directly. Each firing becomes an event in its trigger's
queue, and one worker thread per trigger takes them in order:

1. start the workflow chain in every profile of the trigger at once (the runner
   launches a stopped browser; a profile busy with another run is waited for);
2. wait for every run to end;
3. stop the browsers the trigger opened, when it is set to close them.

What fired reaches the workflows as {{trigger_*}} variables. Events and their
outcome are kept in memory (the last few per trigger) for the dashboard.
"""

from __future__ import annotations

import collections
import contextlib
import fnmatch
import os
import re
import secrets
import threading
import time
from collections.abc import Callable
from typing import Any

from ...core.logging import get_logger
from ...interfaces.protocols import IBrowserLauncher, IProfileManager
from ...utils import clipboard
from ..workflow.model import BUILT_IN_VARIABLES, MAX_VARIABLE_TEXT, VARIABLE_NAME
from ..workflow.runner import WorkflowRunner
from ..workflow.store import WorkflowError
from .model import Automation
from .store import AutomationError, AutomationStore

logger = get_logger("automation")

HISTORY = 20
MAX_QUEUE = 20
# Files whose name says they are still being written.
_PARTIAL = (".tmp", ".part", ".crdownload", ".download", ".partial")
_UNSET = object()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _short(text: str, limit: int = 80) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


class _Slot:
    """A trigger's queue, worker and recent events."""

    def __init__(self) -> None:
        self.queue: collections.deque[dict[str, Any]] = collections.deque()
        self.history: collections.deque[dict[str, Any]] = collections.deque(maxlen=HISTORY)
        self.worker: threading.Thread | None = None
        self.current: dict[str, Any] | None = None
        self.error = ""  # why the trigger cannot watch right now (folder missing...)


class AutomationEngine:
    TICK_S = 1.0
    # A profile busy with another run is tried again this often, for this long.
    BUSY_RETRY_S = 2.0
    BUSY_WAIT_S = 600.0
    RUN_POLL_S = 1.0

    def __init__(
        self,
        store: AutomationStore,
        runner: WorkflowRunner,
        bl: IBrowserLauncher,
        pm: IProfileManager,
        on_change: Callable[[], None] | None = None,
        read_clipboard: Callable[[], str | None] = clipboard.read_text,
        clipboard_count: Callable[[], int | None] = clipboard.change_count,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._store = store
        self._runner = runner
        self._bl = bl
        self._pm = pm
        self._on_change = on_change or (lambda: None)
        self._read_clipboard = read_clipboard
        self._clipboard_count = clipboard_count
        self._clock = clock
        self._slots: dict[str, _Slot] = {}
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._watcher: threading.Thread | None = None
        # Watch state, per trigger id: (its settings, what has been seen so far).
        self._folders: dict[str, tuple[tuple, dict[str, Any]]] = {}
        self._schedules: dict[str, tuple[tuple, dict[str, Any]]] = {}
        self._clip_text: Any = _UNSET
        self._clip_count: int | None = None

    # --- lifecycle --------------------------------------------------------------

    def start(self) -> None:
        if self._watcher and self._watcher.is_alive():
            return
        self._stop.clear()
        self._watcher = threading.Thread(target=self._watch, name="triggers", daemon=True)
        self._watcher.start()
        logger.info("Watching triggers")

    def stop(self) -> None:
        """Stop watching; queued events are dropped, runs in progress go on."""
        self._stop.set()
        with self._lock:
            for slot in self._slots.values():
                slot.queue.clear()

    # --- firing -------------------------------------------------------------------

    def fire(
        self,
        ref: str,
        source: str = "manual",
        *,
        text: str = "",
        file: str = "",
        variables: dict[str, str] | None = None,
        require_enabled: bool = False,
    ) -> dict[str, Any]:
        """Queue a run of the trigger `ref` (id or name). Returns the event."""
        automation = self._store.get(ref)
        if automation is None:
            raise AutomationError(f"Trigger '{ref}' not found", status=404)
        if require_enabled and not automation.enabled:
            raise AutomationError(f"Trigger '{automation.name}' is turned off", status=409)
        values = {
            k: str(v)[:MAX_VARIABLE_TEXT]
            for k, v in (variables or {}).items()
            if VARIABLE_NAME.match(k) and k not in BUILT_IN_VARIABLES
        }
        event: dict[str, Any] = {
            "id": secrets.token_hex(4),
            "source": source,
            "at": _now(),
            "finished_at": "",
            "status": "queued",
            "detail": "",
            "preview": _short(os.path.basename(file) if file else text),
            "runs": {},
            "_trigger": {
                "trigger_type": source,
                "trigger_text": text[:MAX_VARIABLE_TEXT],
                "trigger_file": file,
                "trigger_file_name": os.path.basename(file) if file else "",
                "trigger_time": _now(),
            },
            "_variables": values,
        }
        with self._lock:
            slot = self._slots.setdefault(automation.id, _Slot())
            if len(slot.queue) >= MAX_QUEUE:
                event.update(status="skipped", detail="too many events waiting")
                event["finished_at"] = event["at"]
                slot.history.appendleft(event)
                logger.warning("Trigger %s: queue full, event dropped", automation.name)
                self._on_change()
                return _public(event)
            slot.queue.append(event)
            slot.history.appendleft(event)
            if not (slot.worker and slot.worker.is_alive()):
                slot.worker = threading.Thread(
                    target=self._work,
                    args=(automation.id,),
                    name=f"trigger-{automation.id}",
                    daemon=True,
                )
                slot.worker.start()
        logger.info("Trigger %s fired (%s)", automation.name, source)
        self._on_change()
        return _public(event)

    # --- status ---------------------------------------------------------------------

    def status(self, automation_id: str) -> dict[str, Any]:
        with self._lock:
            slot = self._slots.get(automation_id)
            if slot is None:
                return {"queued": 0, "active": False, "error": "", "last": None, "history": []}
            history = [_public(e) for e in slot.history]
            return {
                "queued": len(slot.queue),
                "active": slot.current is not None,
                "error": slot.error,
                "last": history[0] if history else None,
                "history": history,
            }

    def overview(self) -> list[dict[str, Any]]:
        """Every trigger with its state, for the dashboard."""
        return [{**a.model_dump(), "state": self.status(a.id)} for a in self._store.list()]

    def forget(self, automation_id: str) -> None:
        """Drop a deleted trigger's queue (its event in progress goes on)."""
        with self._lock:
            slot = self._slots.get(automation_id)
            if slot:
                slot.queue.clear()

    # --- the worker: one event at a time per trigger ----------------------------------

    def _work(self, automation_id: str) -> None:
        while True:
            with self._lock:
                slot = self._slots[automation_id]
                if not slot.queue or self._stop.is_set():
                    slot.current = None
                    slot.worker = None
                    return
                event = slot.current = slot.queue.popleft()
            try:
                self._execute(automation_id, event)
            except Exception as e:  # a bug must not leave the event "running"
                logger.exception("Trigger event crashed")
                self._end(event, "failed", f"{type(e).__name__}: {e}")
            with self._lock:
                slot.current = None

    def _end(self, event: dict[str, Any], status: str, detail: str = "") -> None:
        event.update(status=status, detail=detail, finished_at=_now())
        self._on_change()

    def _execute(self, automation_id: str, event: dict[str, Any]) -> None:
        automation = self._store.get(automation_id)
        if automation is None:
            self._end(event, "skipped", "the trigger was deleted")
            return
        event["status"] = "running"
        self._on_change()
        variables = {**automation.variables, **event["_variables"]}
        was_open = {p: self._bl.is_running(p) for p in automation.profiles}
        started, errors = self._start_runs(automation, event, variables)
        self._wait_for(started)
        for profile in started:
            state = self._runner.get(profile) or {}
            event["runs"][profile] = state.get("status", "")
            if state.get("status") != "succeeded":
                errors.append(f"{profile}: {state.get('error') or state.get('status')}")
        if automation.close_profile:
            for profile in started:
                if not was_open[profile] and self._bl.is_running(profile):
                    with contextlib.suppress(Exception):
                        self._bl.stop_profile(profile)
        if errors:
            self._end(event, "failed", "; ".join(errors))
            logger.warning("Trigger %s: %s", automation.name, "; ".join(errors))
        else:
            self._end(event, "succeeded")
            logger.info("Trigger %s: every run succeeded", automation.name)

    def _start_runs(
        self, automation: Automation, event: dict[str, Any], variables: dict[str, str]
    ) -> tuple[list[str], list[str]]:
        """Start the chain in each profile; a busy one is tried again for a while."""
        waiting = list(automation.profiles)
        started: list[str] = []
        errors: list[str] = []
        deadline = time.monotonic() + self.BUSY_WAIT_S
        while waiting:
            for profile in list(waiting):
                try:
                    self._runner.start_chain(
                        automation.workflows,
                        profile,
                        variables,
                        trigger=event["_trigger"],
                        origin=automation.name,
                    )
                except WorkflowError as e:
                    # 409: another run (or a recording) holds the profile; wait for it.
                    if e.status == 409 and time.monotonic() < deadline:
                        continue
                    errors.append(f"{profile}: {e}")
                    event["runs"][profile] = "failed"
                else:
                    started.append(profile)
                    event["runs"][profile] = "running"
                waiting.remove(profile)
            self._on_change()
            if waiting and self._stop.wait(self.BUSY_RETRY_S):
                errors.extend(f"{p}: FoxFlow is closing" for p in waiting)
                break
        return started, errors

    def _wait_for(self, profiles: list[str]) -> None:
        while not self._stop.is_set():
            if not any(self._runner.is_active(p) for p in profiles):
                return
            self._stop.wait(self.RUN_POLL_S)

    # --- the watcher: clipboard, folders, schedules --------------------------------------

    def _watch(self) -> None:
        while not self._stop.wait(self.TICK_S):
            try:
                self.tick()
            except Exception:
                logger.exception("Trigger watcher failed")

    def tick(self) -> None:
        """Look once at everything the enabled triggers watch."""
        enabled = [a for a in self._store.list() if a.enabled]
        by_type: dict[str, list[Automation]] = collections.defaultdict(list)
        for a in enabled:
            by_type[a.trigger.type].append(a)
        self._check_clipboard(by_type["clipboard"])
        live = {a.id for a in enabled}
        for table in (self._folders, self._schedules):
            for gone in set(table) - live:
                del table[gone]
        for a in by_type["file"]:
            self._check_folder(a)
        for a in by_type["schedule"]:
            self._check_schedule(a)

    def _set_error(self, automation: Automation, error: str) -> None:
        with self._lock:
            slot = self._slots.setdefault(automation.id, _Slot())
            if slot.error != error:
                slot.error = error
                if error:
                    logger.warning("Trigger %s: %s", automation.name, error)
                self._on_change()

    def _check_clipboard(self, automations: list[Automation]) -> None:
        if not automations:
            # Nothing listens: the next clipboard trigger starts from what is there then.
            self._clip_text, self._clip_count = _UNSET, None
            return
        count = self._clipboard_count()
        if count is not None and count == self._clip_count:
            return
        try:
            text = self._read_clipboard()
        except clipboard.ClipboardUnavailable as e:
            for a in automations:
                self._set_error(a, f"cannot read the clipboard: {e}")
            return
        for a in automations:
            self._set_error(a, "")
        first = self._clip_text is _UNSET
        # Where the OS counts copies, copying the same text again counts too.
        same = text == self._clip_text and (count is None or self._clip_count is None)
        self._clip_text, self._clip_count = text, count
        if first or same or not text or not text.strip():
            return
        for a in automations:
            if not a.trigger.pattern or re.search(a.trigger.pattern, text):
                self.fire(a.id, "clipboard", text=text)

    def _check_folder(self, automation: Automation) -> None:
        trigger = automation.trigger
        folder = os.path.abspath(os.path.expanduser(trigger.folder.strip()))
        settings = (folder, trigger.pattern)
        known = self._folders.get(automation.id)
        try:
            files = {}
            with os.scandir(folder) as entries:
                for entry in entries:
                    name = entry.name
                    if name.startswith(("~$", ".")) or name.lower().endswith(_PARTIAL):
                        continue
                    if not fnmatch.fnmatch(name.lower(), (trigger.pattern or "*").lower()):
                        continue
                    with contextlib.suppress(OSError):
                        if entry.is_file():
                            stat = entry.stat()
                            files[entry.path] = (stat.st_size, stat.st_mtime)
        except OSError as e:
            self._set_error(automation, f"cannot read the folder {folder}: {e.strerror or e}")
            return
        self._set_error(automation, "")
        if known is None or known[0] != settings:
            # Files already there do not count; only the ones that come after.
            self._folders[automation.id] = (settings, {"seen": set(files), "pending": {}})
            return
        seen: set[str] = known[1]["seen"]
        pending: dict[str, tuple] = known[1]["pending"]
        seen &= set(files)  # a file removed and made again counts again
        for path, sig in files.items():
            if path in seen:
                continue
            # Fire once the file stopped growing: it is finished being written.
            if pending.get(path) == sig:
                del pending[path]
                seen.add(path)
                self.fire(automation.id, "file", file=path, text=_file_text(path, sig[0]))
            else:
                pending[path] = sig
        for path in set(pending) - set(files):
            del pending[path]

    def _check_schedule(self, automation: Automation) -> None:
        trigger = automation.trigger
        settings = (trigger.every_minutes, tuple(trigger.at))
        now = self._clock()
        known = self._schedules.get(automation.id)
        if known is None or known[0] != settings:
            state = {"next": now + trigger.every_minutes * 60, "done": set()}
            self._schedules[automation.id] = (settings, state)
        else:
            state = known[1]
        if trigger.every_minutes and now >= state["next"]:
            # After a sleep, run once and keep the rhythm from now.
            state["next"] = max(state["next"] + trigger.every_minutes * 60, now + 1)
            self.fire(automation.id, "schedule")
        if trigger.at:
            local = time.localtime(now)
            minute = time.strftime("%H:%M", local)
            stamp = time.strftime("%Y-%m-%d ", local) + minute
            if minute in trigger.at and stamp not in state["done"]:
                state["done"] = {d for d in state["done"] if d[:10] == stamp[:10]} | {stamp}
                self.fire(automation.id, "schedule")


def _file_text(path: str, size: int) -> str:
    """A small text file's content, for {{trigger_text}}; "" for anything else."""
    if size > MAX_VARIABLE_TEXT:
        return ""
    try:
        with open(path, "rb") as f:
            raw = f.read(MAX_VARIABLE_TEXT + 1)
        if b"\x00" in raw:
            return ""
        return raw.decode("utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return ""


def _public(event: dict[str, Any]) -> dict[str, Any]:
    return {k: (dict(v) if isinstance(v, dict) else v) for k, v in event.items() if k[0] != "_"}
