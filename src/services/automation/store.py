"""Triggers saved in one JSON file (AUTOMATIONS_FILE, next to profiles.json).

The file holds each webhook's key: treat it like profiles.json.
"""

from __future__ import annotations

import json
import os
import pathlib
import threading
import time

from pydantic import ValidationError

from ...core.config import AUTOMATIONS_FILE
from ...core.logging import get_logger
from .model import Automation

logger = get_logger("automation.store")

MAX_AUTOMATIONS = 200


class AutomationError(Exception):
    """Bad, missing or conflicting trigger; `status` is the HTTP status to report."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class AutomationStore:
    def __init__(self, path: str = AUTOMATIONS_FILE) -> None:
        self._path = pathlib.Path(path)
        self._lock = threading.RLock()
        self._cache: list[Automation] | None = None
        self._mtime: float | None = None
        # Bumped on every change, so watchers know when to read the triggers again.
        self.version = 0

    def _load(self) -> list[Automation]:
        """Every trigger; re-read when the file changed on disk."""
        try:
            mtime = self._path.stat().st_mtime
        except OSError:
            mtime = None
        if self._cache is not None and mtime == self._mtime:
            return self._cache
        items: list[Automation] = []
        if mtime is not None:
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                logger.warning("Ignoring unreadable %s: %s", self._path, e)
                raw = {}
            for entry in raw.get("automations", []) if isinstance(raw, dict) else []:
                try:
                    items.append(Automation.model_validate(entry))
                except ValidationError as e:
                    logger.warning("Ignoring an invalid trigger in %s: %s", self._path, e)
        if self._cache is not None:
            self.version += 1
        self._cache, self._mtime = items, mtime
        return items

    def _write(self, items: list[Automation]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        data = {"automations": [a.model_dump() for a in items]}
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self._path)
        self._cache = items
        self._mtime = self._path.stat().st_mtime
        self.version += 1

    def list(self) -> list[Automation]:
        with self._lock:
            return [a.model_copy(deep=True) for a in self._load()]

    def get(self, ref: str) -> Automation | None:
        """By id, or by name (case-insensitive)."""
        with self._lock:
            items = self._load()
            found = next((a for a in items if a.id == ref), None) or next(
                (a for a in items if a.name.casefold() == ref.casefold()), None
            )
            return found.model_copy(deep=True) if found else None

    def save(self, automation: Automation, *, create: bool = False) -> Automation:
        """Create or replace by id. Names are unique (case-insensitive)."""
        with self._lock:
            items = list(self._load())
            index = next((i for i, a in enumerate(items) if a.id == automation.id), None)
            if create and index is not None:
                raise AutomationError(f"Trigger id '{automation.id}' already exists", status=409)
            if index is None and len(items) >= MAX_AUTOMATIONS:
                raise AutomationError(f"At most {MAX_AUTOMATIONS} triggers")
            clash = next(
                (
                    a
                    for a in items
                    if a.id != automation.id and a.name.casefold() == automation.name.casefold()
                ),
                None,
            )
            if clash:
                raise AutomationError(f"A trigger named '{clash.name}' already exists", status=409)
            automation.updated_at = _now()
            if index is None:
                automation.created_at = automation.created_at or automation.updated_at
                items.append(automation)
            else:
                automation.created_at = items[index].created_at or automation.updated_at
                items[index] = automation
            self._write(items)
        logger.info("Saved trigger %s (%s)", automation.name, automation.trigger.type)
        return automation.model_copy(deep=True)

    def delete(self, ref: str) -> bool:
        with self._lock:
            found = self.get(ref)
            if found is None:
                return False
            self._write([a for a in self._load() if a.id != found.id])
        logger.info("Deleted trigger %s", found.name)
        return True

    def rename_profile(self, old: str, new: str) -> None:
        """Keep triggers pointing at a renamed profile."""
        with self._lock:
            items = self._load()
            if not any(old in a.profiles for a in items):
                return
            for a in items:
                a.profiles = [new if p == old else p for p in a.profiles]
            self._write(items)
