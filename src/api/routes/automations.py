"""Triggers: when a webhook is called, text is copied, a file appears or a time comes,
open profiles, run workflows and close them.

`router` sits behind the API token like every other route. `hooks_router` is
what outside services call: it needs no API token, only the trigger's own key
(?key=... or the X-FoxFlow-Key header), so a key can be shared without the token.
"""

from __future__ import annotations

import json
import secrets
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ...services.automation.model import Automation
from ...services.automation.store import AutomationError
from ...services.workflow.model import VARIABLE_NAME
from ..dependencies import (
    get_automation_engine,
    get_automation_store,
    get_event_bus,
    get_profile_manager,
    get_workflow_store,
)
from ..schemas.common import SuccessResponse

if TYPE_CHECKING:
    from ...core.events import EventBus
    from ...interfaces import IProfileManager
    from ...services.automation.engine import AutomationEngine
    from ...services.automation.store import AutomationStore
    from ...services.workflow.store import WorkflowStore

router = APIRouter(tags=["triggers"])
hooks_router = APIRouter(tags=["triggers"])

HOOK_PATH = "/hooks"
MAX_BODY = 100_000

_AS = Depends(get_automation_store)
_AE = Depends(get_automation_engine)
_PM = Depends(get_profile_manager)
_WS = Depends(get_workflow_store)
_BUS = Depends(get_event_bus)


class FireRequest(BaseModel):
    text: str = Field("", max_length=20_000, description="Becomes {{trigger_text}}")
    variables: dict[str, str] = Field(
        default_factory=dict, description="Values for the workflows' variables on this run"
    )


def _http(e: AutomationError) -> HTTPException:
    return HTTPException(status_code=e.status, detail=str(e))


def _check_targets(automation: Automation, pm: IProfileManager, ws: WorkflowStore) -> None:
    """Refuse profiles and workflows that do not exist (typos would fail every run)."""
    missing = [f"profile '{p}'" for p in automation.profiles if p not in pm.profiles]
    missing += [f"workflow '{w}'" for w in automation.workflows if ws.get(w) is None]
    if missing:
        raise HTTPException(status_code=400, detail="Not found: " + ", ".join(missing))


def _found(engine: AutomationEngine, store: AutomationStore, ref: str) -> dict[str, Any]:
    automation = store.get(ref)
    if automation is None:
        raise HTTPException(status_code=404, detail=f"Trigger '{ref}' not found")
    return {**automation.model_dump(), "state": engine.status(automation.id)}


@router.get("/automations")
def list_automations(engine: AutomationEngine = _AE) -> dict:
    """Every trigger with its state: queued events, the one running, recent outcomes."""
    return {"automations": engine.overview(), "hook_path": HOOK_PATH}


@router.post("/automations", status_code=201)
def create_automation(
    body: Automation,
    store: AutomationStore = _AS,
    engine: AutomationEngine = _AE,
    pm: IProfileManager = _PM,
    ws: WorkflowStore = _WS,
    bus: EventBus = _BUS,
) -> dict:
    _check_targets(body, pm, ws)
    try:
        saved = store.save(body, create=True)
    except AutomationError as e:
        raise _http(e) from e
    bus.emit()
    return _found(engine, store, saved.id)


@router.get("/automations/{ref}")
def get_automation(ref: str, store: AutomationStore = _AS, engine: AutomationEngine = _AE) -> dict:
    """A trigger by id or name, with its recent events."""
    return _found(engine, store, ref)


@router.put("/automations/{ref}")
def save_automation(
    ref: str,
    body: Automation,
    store: AutomationStore = _AS,
    engine: AutomationEngine = _AE,
    pm: IProfileManager = _PM,
    ws: WorkflowStore = _WS,
    bus: EventBus = _BUS,
) -> dict:
    """Create or replace a trigger. A blank webhook key gets a new one."""
    existing = store.get(ref)
    body.id = existing.id if existing else ref
    _check_targets(body, pm, ws)
    try:
        saved = store.save(body)
    except AutomationError as e:
        raise _http(e) from e
    bus.emit()
    return _found(engine, store, saved.id)


@router.delete("/automations/{ref}", response_model=SuccessResponse)
def delete_automation(
    ref: str, store: AutomationStore = _AS, engine: AutomationEngine = _AE, bus: EventBus = _BUS
) -> SuccessResponse:
    found = store.get(ref)
    if found is None or not store.delete(found.id):
        raise HTTPException(status_code=404, detail=f"Trigger '{ref}' not found")
    engine.forget(found.id)
    bus.emit()
    return SuccessResponse(message=f"Trigger '{found.name}' deleted")


@router.post("/automations/{ref}/fire", status_code=202)
def fire_automation(ref: str, body: FireRequest, engine: AutomationEngine = _AE) -> dict:
    """Run a trigger now (also when it is turned off), as if it had fired."""
    try:
        return engine.fire(ref, "manual", text=body.text, variables=body.variables)
    except AutomationError as e:
        raise _http(e) from e


# --- webhooks ---------------------------------------------------------------------


def _scalars(data: dict[str, Any]) -> dict[str, str]:
    """A JSON object's text, number and true/false values whose keys can be variables."""
    out = {}
    for k, v in data.items():
        if isinstance(k, str) and VARIABLE_NAME.match(k) and isinstance(v, (str, int, float, bool)):
            out[k] = ("true" if v else "false") if isinstance(v, bool) else str(v)
    return out


@hooks_router.api_route(f"{HOOK_PATH}/{{automation_id}}", methods=["GET", "POST"], status_code=202)
async def webhook(
    automation_id: str,
    request: Request,
    store: AutomationStore = _AS,
    engine: AutomationEngine = _AE,
) -> dict:
    """Fire a trigger from another app (Zapier, n8n, a script...).

    Send its key as ?key=... or the X-FoxFlow-Key header. A JSON object body (or
    the query string of a GET) fills the workflows' variables of the same names;
    the body as text, or ?text=..., becomes {{trigger_text}}.
    """
    automation = store.get(automation_id)
    key = request.headers.get("X-FoxFlow-Key") or request.query_params.get("key") or ""
    # The same answer for an unknown trigger and a wrong key: ids cannot be probed.
    if (
        automation is None
        or automation.id != automation_id
        or automation.trigger.type != "webhook"
        or not secrets.compare_digest(key.encode(), automation.trigger.key.encode())
    ):
        raise HTTPException(status_code=404, detail="Not found")
    query = {k: v for k, v in request.query_params.items() if k != "key"}
    raw = b""
    if request.method == "POST":
        async for chunk in request.stream():
            raw += chunk
            if len(raw) > MAX_BODY:
                raise HTTPException(status_code=413, detail="The body is too large")
    text = raw.decode("utf-8", "replace") if raw else query.pop("text", "")
    variables = _scalars(query)
    if raw:
        try:
            data = json.loads(raw)
        except ValueError:
            data = None
        if isinstance(data, dict):
            variables.update(_scalars(data))
            if isinstance(data.get("text"), str):
                text = data["text"]
    try:
        event = engine.fire(
            automation.id, "webhook", text=text, variables=variables, require_enabled=True
        )
    except AutomationError as e:
        raise _http(e) from e
    return {"queued": event["status"] == "queued", "event": event}
