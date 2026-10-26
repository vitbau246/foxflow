"""Workflows saved as JSON files, one per workflow, in WORKFLOWS_DIR."""

from __future__ import annotations

import json
import os
import pathlib
import threading
import time
from typing import Any

from pydantic import ValidationError

from ...core.config import WORKFLOWS_DIR
from ...core.logging import get_logger
from ...utils.validation import validate_profile_name
from .model import Workflow, problems

logger = get_logger("workflow.store")


class WorkflowError(Exception):
    """Bad name, missing or conflicting workflow; `status` is the HTTP status to report."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def check_name(name: str) -> str:
    """The name, if it can be a file name on every OS; WorkflowError otherwise."""
    if not name or not name.strip():
        raise WorkflowError("Workflow name cannot be empty")
    if len(name) > 64:
        raise WorkflowError("Workflow name must be 64 characters or less")
    ok, message = validate_profile_name(name)
    if not ok:
        raise WorkflowError(message)
    return name


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class WorkflowStore:
    def __init__(self, directory: str = WORKFLOWS_DIR) -> None:
        self._dir = pathlib.Path(directory)
        self._lock = threading.RLock()

    def _files(self) -> dict[str, pathlib.Path]:
        """Stored workflows by lower-cased name: names are case-insensitive, like
        profile names, so "Login" and "login" never share one file on Windows."""
        if not self._dir.is_dir():
            return {}
        return {p.stem.lower(): p for p in self._dir.glob("*.json")}

    def _path(self, name: str) -> pathlib.Path | None:
        return self._files().get(check_name(name).lower())

    def _read(self, path: pathlib.Path) -> Workflow | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            workflow = Workflow.model_validate(data)
        except (OSError, ValueError, ValidationError) as e:
            logger.warning("Ignoring unreadable workflow %s: %s", path, e)
            return None
        # The file name is the identity; a hand-edited "name" must not disagree.
        workflow.name = path.stem
        return workflow

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            workflows = [w for p in self._files().values() if (w := self._read(p))]
        return [
            {
                "name": w.name,
                "description": w.description,
                "profile": w.profile,
                "step_count": len(w.steps),
                "created_at": w.created_at,
                "updated_at": w.updated_at,
            }
            for w in sorted(workflows, key=lambda w: w.name.lower())
        ]

    def get(self, name: str) -> Workflow | None:
        with self._lock:
            path = self._path(name)
            return self._read(path) if path else None

    def save(self, workflow: Workflow, *, create: bool = False) -> Workflow:
        """Write a workflow. With create=True an existing one is a 409 conflict."""
        check_name(workflow.name)
        if issues := problems(workflow):
            raise WorkflowError("; ".join(issues[:5]))
        with self._lock:
            existing = self._path(workflow.name)
            if existing and create:
                raise WorkflowError(f"Workflow '{existing.stem}' already exists", status=409)
            if existing:
                # Keep the stored spelling of the name and the creation time.
                old = self._read(existing)
                workflow.name = existing.stem
                workflow.created_at = (old.created_at if old else "") or workflow.created_at
            workflow.created_at = workflow.created_at or _now()
            workflow.updated_at = _now()
            self._dir.mkdir(parents=True, exist_ok=True)
            path = self._dir / f"{workflow.name}.json"
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps(workflow.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
            )
            os.replace(tmp, path)
        logger.info("Saved workflow %s (%d steps)", workflow.name, len(workflow.steps))
        return workflow

    def of_profile(self, profile: str) -> list[Workflow]:
        """Workflows recorded in (or copied to) a profile."""
        with self._lock:
            workflows = [w for p in self._files().values() if (w := self._read(p))]
        return sorted(
            (w for w in workflows if w.profile.casefold() == profile.casefold()),
            key=lambda w: w.name.lower(),
        )

    def copy_to_profile(self, source: str, target: str) -> list[str]:
        """Give `target` its own copy of each workflow of `source`, named
        "<workflow>-<target>" (with -2, -3... if taken). Returns the new names."""
        made = []
        for workflow in self.of_profile(source):
            stem = f"{workflow.name}-{target}"[:60]
            with self._lock:
                taken = self._files()
                name, n = stem, 1
                while name.lower() in taken:
                    n += 1
                    name = f"{stem}-{n}"
                copy = workflow.model_copy(deep=True)
                copy.name, copy.profile, copy.created_at = name, target, ""
                self.save(copy, create=True)
            made.append(name)
        return made

    def reassign(self, old: str, new: str) -> int:
        """Move the workflows of a renamed profile to its new name."""
        moved = 0
        for workflow in self.of_profile(old):
            workflow.profile = new
            self.save(workflow)
            moved += 1
        return moved

    def delete(self, name: str) -> bool:
        with self._lock:
            path = self._path(name)
            if not path:
                return False
            path.unlink(missing_ok=True)
        logger.info("Deleted workflow %s", name)
        return True
