"""Record what a user does in a profile's browser, edit it as a workflow, replay it."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Response

from ...services.ai.client import AIError, generate
from ...services.ai.settings import AISettings
from ...services.workflow import recording
from ...services.workflow.model import Workflow
from ...services.workflow.store import WorkflowError
from ...utils import net
from ..dependencies import (
    get_ai_settings,
    get_browser_launcher,
    get_event_bus,
    get_profile_manager,
    get_workflow_runner,
    get_workflow_store,
)
from ..helpers import require_profile
from ..schemas.common import SuccessResponse
from ..schemas.workflows import (
    AISettingsUpdate,
    AITestRequest,
    ChainRunRequest,
    RecordStopRequest,
    RunRequest,
)

if TYPE_CHECKING:
    from ...core.events import EventBus
    from ...interfaces import IBrowserLauncher, IProfileManager
    from ...services.ai.settings import AISettingsStore
    from ...services.workflow.runner import WorkflowRunner
    from ...services.workflow.store import WorkflowStore

router = APIRouter(tags=["workflows"])

_PM = Depends(get_profile_manager)
_BL = Depends(get_browser_launcher)
_WS = Depends(get_workflow_store)
_WR = Depends(get_workflow_runner)
_BUS = Depends(get_event_bus)


def _http(e: WorkflowError) -> HTTPException:
    return HTTPException(status_code=e.status, detail=str(e))


# --- Workflows ----------------------------------------------------------------


@router.get("/workflows")
def list_workflows(store: WorkflowStore = _WS) -> dict:
    return {"workflows": store.list()}


@router.post("/workflows", status_code=201)
def create_workflow(body: Workflow, store: WorkflowStore = _WS) -> Workflow:
    try:
        return store.save(body, create=True)
    except WorkflowError as e:
        raise _http(e) from e


@router.get("/workflows/{name}")
def get_workflow(name: str, store: WorkflowStore = _WS) -> Workflow:
    try:
        workflow = store.get(name)
    except WorkflowError as e:
        raise _http(e) from e
    if workflow is None:
        raise HTTPException(status_code=404, detail=f"Workflow '{name}' not found")
    return workflow


@router.put("/workflows/{name}")
def save_workflow(name: str, body: Workflow, store: WorkflowStore = _WS) -> Workflow:
    """Create or replace a workflow (steps, delays, typing speed, checks, retries)."""
    body.name = name
    try:
        return store.save(body)
    except WorkflowError as e:
        raise _http(e) from e


@router.delete("/workflows/{name}", response_model=SuccessResponse)
def delete_workflow(name: str, store: WorkflowStore = _WS) -> SuccessResponse:
    try:
        deleted = store.delete(name)
    except WorkflowError as e:
        raise _http(e) from e
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Workflow '{name}' not found")
    return SuccessResponse(message=f"Workflow '{name}' deleted")


@router.post("/workflows/{name}/run", status_code=202)
def run_workflow(name: str, body: RunRequest, runner: WorkflowRunner = _WR) -> dict:
    """Replay a workflow in a profile, launching its browser if needed.

    Every step is checked; a failed step is retried (settings.retries), then the
    browser is restarted and the workflow runs from the start (settings.max_restarts).
    Follow it with GET /workflow-runs/{profile}.
    """
    try:
        return runner.start(name, body.profile, body.variables)
    except WorkflowError as e:
        raise _http(e) from e


# --- AI ---------------------------------------------------------------------------

_AI = Depends(get_ai_settings)


@router.get("/ai/settings")
def ai_settings(settings: AISettingsStore = _AI) -> dict:
    """AI used by "ai" steps; the API key only as a hint, and the outbound proxy's host:port."""
    return {**settings.public(), "network_proxy": net.proxy_label()}


@router.put("/ai/settings")
def save_ai_settings(body: AISettingsUpdate, settings: AISettingsStore = _AI) -> dict:
    current = settings.load().model_dump()
    changes = body.model_dump(exclude_unset=True, exclude={"clear_temperature"})
    if body.clear_temperature:
        changes["temperature"] = None
    try:
        updated = AISettings.model_validate({**current, **changes})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e).splitlines()[-1]) from e
    settings.save(updated)
    return {**settings.public(), "network_proxy": net.proxy_label()}


@router.post("/ai/test")
def test_ai(body: AITestRequest, settings: AISettingsStore = _AI) -> dict:
    """Send one prompt with the saved settings and return the reply."""
    try:
        return {"text": generate(settings.load(), body.prompt, timeout=60)}
    except AIError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


# --- Runs ---------------------------------------------------------------------


@router.get("/workflow-runs")
def list_runs(log: bool = True, runner: WorkflowRunner = _WR) -> dict:
    """Each profile's current or last run. `log=false` leaves out the log lines (dashboards)."""
    return {"runs": runner.list(log)}


@router.post("/workflow-runs", status_code=202)
def run_workflows(body: ChainRunRequest, runner: WorkflowRunner = _WR) -> dict:
    """Run several workflows one after the other in one profile's browser.

    Each keeps its own settings and restarts from its own first step; variables
    saved by one carry over to the next. The run stops at the first workflow
    that fails. Follow it with GET /workflow-runs/{profile}.
    """
    try:
        return runner.start_chain(body.workflows, body.profile, body.variables)
    except WorkflowError as e:
        raise _http(e) from e


@router.get("/workflow-runs/{profile}")
def run_status(profile: str, runner: WorkflowRunner = _WR) -> dict:
    """The profile's current or last run: status, step, attempt, restarts and log."""
    state = runner.get(profile)
    if state is None:
        raise HTTPException(status_code=404, detail=f"No workflow run for '{profile}'")
    return state


@router.post("/workflow-runs/{profile}/stop", response_model=SuccessResponse)
def stop_run(profile: str, runner: WorkflowRunner = _WR) -> SuccessResponse:
    if not runner.stop(profile):
        raise HTTPException(status_code=409, detail=f"No workflow is running in '{profile}'")
    return SuccessResponse(message="Stopping after the current action")


# --- Recording ----------------------------------------------------------------


@router.get("/recordings")
def list_recordings(pm: IProfileManager = _PM, bl: IBrowserLauncher = _BL) -> dict:
    """Profiles that are recording, or hold a recording that was not saved yet."""
    return {"recordings": recording.overview(bl, list(pm.profiles))}


@router.post("/browser/{name}/record/start")
def record_start(
    name: str,
    pm: IProfileManager = _PM,
    bl: IBrowserLauncher = _BL,
    runner: WorkflowRunner = _WR,
    bus: EventBus = _BUS,
) -> dict:
    """Record what is done in the running profile's browser, from the active tab."""
    require_profile(name, pm)
    try:
        result = recording.start(bl, runner, name)
    except WorkflowError as e:
        raise _http(e) from e
    bus.emit()
    return result


@router.get("/browser/{name}/record")
def record_status(name: str, pm: IProfileManager = _PM, bl: IBrowserLauncher = _BL) -> dict:
    """Recording state; `draft` is an unsaved recording kept after the browser closed."""
    require_profile(name, pm)
    return recording.status(bl, name)


@router.post("/browser/{name}/record/stop")
def record_stop(
    name: str,
    body: RecordStopRequest,
    response: Response,
    pm: IProfileManager = _PM,
    bl: IBrowserLauncher = _BL,
    store: WorkflowStore = _WS,
    bus: EventBus = _BUS,
) -> dict:
    require_profile(name, pm)
    try:
        result = recording.stop(
            bl,
            store,
            name,
            save_as=body.save_as,
            description=body.description,
            overwrite=body.overwrite,
            discard=body.discard,
        )
    except WorkflowError as e:
        raise _http(e) from e
    if result["workflow"]:
        response.status_code = 201
    bus.emit()
    return result
