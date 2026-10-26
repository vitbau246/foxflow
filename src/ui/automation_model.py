"""Pure logic behind the Automation page and the Run dialog (no Flet, testable).

Runs are `WorkflowRunner.list()` dicts (one per profile: its current or last
run); workflows are `WorkflowStore.list()` dicts. Timestamps are
"YYYY-MM-DDTHH:MM:SS".
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ..core.strings import get_string

Run = dict[str, Any]


def plural(key: str, count: int, **kwargs: object) -> str:
    """`key` with {count}; `key_one` when the count is 1."""
    return get_string(f"{key}_one" if count == 1 else key, count=count, **kwargs)


def hhmm(ts: str) -> str:
    return ts[11:16] if len(ts or "") >= 16 else ""


def ddmm(ts: str) -> str:
    return f"{ts[8:10]}/{ts[5:7]}" if len(ts or "") >= 10 else ""


def ddmm_hhmm(ts: str) -> str:
    return f"{ddmm(ts)} {hhmm(ts)}".strip()


def sort_runs(runs: Iterable[Run]) -> list[Run]:
    """Active runs first, then the most recently started."""
    newest = sorted(runs, key=lambda r: r.get("started_at", ""), reverse=True)
    return sorted(newest, key=lambda r: not r.get("active"))


def workflow_activity(runs: Iterable[Run]) -> dict[str, dict[str, Any]]:
    """Per workflow: how many runs are active, and its most recently finished run."""
    out: dict[str, dict[str, Any]] = {}
    for run in runs:
        entry = out.setdefault(run["workflow"], {"active": 0, "last": None})
        if run.get("active"):
            entry["active"] += 1
            continue
        last = entry["last"]
        if last is None or run.get("finished_at", "") > last.get("finished_at", ""):
            entry["last"] = run
    return out


def counts(workflows: list[dict], runs: Iterable[Run]) -> tuple[int, int, int]:
    """(workflows, active runs, failed runs)."""
    runs = list(runs)
    active = sum(1 for r in runs if r.get("active"))
    failed = sum(1 for r in runs if r.get("status") == "failed")
    return len(workflows), active, failed


def match_workflow(workflow: dict, query: str) -> bool:
    q = query.strip().casefold()
    return not q or any(
        q in (workflow.get(k) or "").casefold() for k in ("name", "description", "profile")
    )


def match_run(run: Run, query: str) -> bool:
    q = query.strip().casefold()
    return not q or any(q in (run.get(k) or "").casefold() for k in ("profile", "workflow"))


def run_blocker(
    profile: str, recording: set[str], runs_by_profile: dict[str, Run]
) -> tuple[str, dict[str, str]] | None:
    """Why a profile cannot start a run now, as (string key, format args)."""
    if profile in recording:
        return "run_blocked_recording", {}
    run = runs_by_profile.get(profile)
    if run and run.get("active"):
        return "run_blocked_running", {"workflow": run["workflow"]}
    return None


def recording_order(profiles: Iterable[str], running: set[str]) -> list[str]:
    """Profiles to record in: running ones first (recording needs an open browser)."""
    return sorted(profiles, key=lambda n: (n not in running, n.casefold()))


def initial_selection(
    profiles: Iterable[str],
    preselect: Iterable[str],
    owner: str,
    blocked: set[str],
) -> set[str]:
    """The bulk-bar selection, else the workflow's owner profile; never a blocked one."""
    names = set(profiles)
    chosen = set(preselect) & names
    if not chosen:
        chosen = {n for n in names if owner and n.casefold() == owner.casefold()}
    return chosen - blocked
