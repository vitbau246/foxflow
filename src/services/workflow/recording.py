"""Start, follow and finish a recording; shared by the API and the desktop app.

The recording itself runs in the profile's browser process (browser/recorder.py).
Its steps are also kept in camoufox_data/<profile>/recording.json, so a recording
whose browser was closed can still be saved as a workflow.
"""

from __future__ import annotations

import os
from typing import Any

from ...core.config import DATA_DIR
from ...interfaces.protocols import IBrowserLauncher
from ..browser.launcher import BrowserControlError
from ..browser.recorder import RECORDING_FILE, clean_steps, discard_draft, load_draft
from .model import Workflow
from .runner import WorkflowRunner
from .store import WorkflowError, WorkflowStore, check_name


def profile_dir(name: str) -> str:
    return os.path.join(os.getcwd(), DATA_DIR, name)


def _control(bl: IBrowserLauncher, name: str, action: str) -> dict[str, Any]:
    try:
        return bl.control(name, action, {}, timeout=30)
    except BrowserControlError as e:
        raise WorkflowError(str(e), status=e.status) from e


def start(bl: IBrowserLauncher, runner: WorkflowRunner, name: str) -> dict[str, Any]:
    if not bl.is_running(name):
        raise WorkflowError("Launch the profile first, then record in its browser", status=409)
    if runner.is_active(name):
        raise WorkflowError("A workflow is running in this profile; stop it first", status=409)
    return status_of(bl, name, _control(bl, name, "record_start"))


def status(bl: IBrowserLauncher, name: str) -> dict[str, Any]:
    live = None
    if bl.is_running(name):
        try:
            live = bl.control(name, "record_status", {}, timeout=10)
        except BrowserControlError:
            live = None
    return status_of(bl, name, live)


def status_of(bl: IBrowserLauncher, name: str, live: dict[str, Any] | None) -> dict[str, Any]:
    """Live status while recording; otherwise the unsaved draft, if any."""
    if live and live.get("recording"):
        return {**live, "draft": False}
    draft = load_draft(profile_dir(name))
    steps = clean_steps(draft["steps"]) if draft else []
    return {
        "recording": False,
        "draft": bool(steps),
        "started_at": draft.get("started_at", "") if draft else "",
        "step_count": len(steps),
        "recent": [f"{s['action']} {s.get('label', '')}".strip() for s in steps[-5:]],
    }


def overview(bl: IBrowserLauncher, names: list[str]) -> list[dict[str, Any]]:
    """Profiles recording now or holding an unsaved recording."""
    running = bl.running_profile_names()
    out = []
    for name in names:
        if name not in running and not os.path.exists(
            os.path.join(profile_dir(name), RECORDING_FILE)
        ):
            continue
        state = status(bl, name) if name in running else status_of(bl, name, None)
        if state["recording"] or state["draft"]:
            out.append({"profile": name, **state})
    return out


def stop(
    bl: IBrowserLauncher,
    store: WorkflowStore,
    name: str,
    save_as: str | None = None,
    description: str = "",
    overwrite: bool = False,
    discard: bool = False,
) -> dict[str, Any]:
    """End the recording. With `save_as` the steps become a saved workflow and the
    draft is removed; without it the draft stays, so it can still be saved later."""
    if save_as:
        check_name(save_as)
    steps: list[dict[str, Any]] | None = None
    if bl.is_running(name):
        try:
            live = bl.control(name, "record_status", {}, timeout=10)
        except BrowserControlError:
            live = None
        if live and live.get("recording"):
            steps = clean_steps(_control(bl, name, "record_stop")["steps"])
    if steps is None:
        draft = load_draft(profile_dir(name))
        steps = clean_steps(draft["steps"]) if draft else []
    if discard:
        discard_draft(profile_dir(name))
        return {"steps": [], "workflow": None, "discarded": True}
    if not save_as:
        return {"steps": steps, "workflow": None, "discarded": False}
    if not steps:
        raise WorkflowError("Nothing was recorded")
    workflow = Workflow(name=save_as, description=description, profile=name, steps=steps)
    saved = store.save(workflow, create=not overwrite)
    discard_draft(profile_dir(name))
    return {"steps": steps, "workflow": saved.model_dump(), "discarded": False}
