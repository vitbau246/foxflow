"""A trigger: when something happens, open profiles, run workflows, close them.

Kinds of trigger:
- webhook: a request to /api/v1/hooks/<id> with the trigger's key;
- clipboard: text copied on this computer (optionally only text matching a regex);
- file: a new file in a folder (optionally only names matching a pattern);
- schedule: every N minutes, or at set times of day.

What happened reaches the workflows as the built-in variables {{trigger_type}},
{{trigger_text}}, {{trigger_file}}, {{trigger_file_name}} and {{trigger_time}}.
"""

from __future__ import annotations

import re
import secrets
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from ..workflow.model import VARIABLE_NAME

TRIGGER_TYPES = ("webhook", "clipboard", "file", "schedule")
TriggerType = Literal["webhook", "clipboard", "file", "schedule"]

MAX_PROFILES = 50
MAX_WORKFLOWS = 20
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def new_id() -> str:
    return secrets.token_hex(4)


def new_key() -> str:
    return secrets.token_urlsafe(24)


class Trigger(BaseModel):
    type: TriggerType = "webhook"
    # webhook: the secret a caller sends as ?key= or the X-FoxFlow-Key header.
    key: str = Field(default_factory=new_key, max_length=200)
    # clipboard: a regex the copied text must contain; file: a name pattern ("*.csv").
    pattern: str = Field("", max_length=500)
    # file: the folder watched for new files (not its subfolders).
    folder: str = Field("", max_length=1_000)
    # schedule: every N minutes (0 = not on an interval) and/or at these times ("HH:MM").
    every_minutes: int = Field(0, ge=0, le=10_080)
    at: list[str] = Field(default_factory=list, max_length=48)

    @field_validator("key")
    @classmethod
    def _key(cls, v: str) -> str:
        # A blank key asks for a new one; a short one would be guessable.
        v = v.strip()
        if not v:
            return new_key()
        if len(v) < 16:
            raise ValueError("the webhook key must be at least 16 characters")
        return v

    @field_validator("at")
    @classmethod
    def _times(cls, v: list[str]) -> list[str]:
        out = []
        for t in v:
            t = t.strip()
            if len(t) == 4 and t[1] == ":":
                t = "0" + t  # 9:30 -> 09:30
            if not _TIME.match(t):
                raise ValueError(f"'{t}' is not a time of day (HH:MM)")
            if t not in out:
                out.append(t)
        return sorted(out)

    @model_validator(mode="after")
    def _complete(self) -> Trigger:
        if self.type == "clipboard" and self.pattern:
            try:
                re.compile(self.pattern)
            except re.error as e:
                raise ValueError(f"invalid regular expression: {e}") from e
        if self.type == "file" and not self.folder.strip():
            raise ValueError("pick the folder to watch")
        if self.type == "schedule" and not self.every_minutes and not self.at:
            raise ValueError("set an interval in minutes or times of day")
        return self


class Automation(BaseModel):
    id: str = Field(default_factory=new_id, max_length=32)
    name: str = Field(min_length=1, max_length=64)
    enabled: bool = True
    trigger: Trigger = Field(default_factory=Trigger)
    # Every profile runs the workflows, in this order, at the same time.
    profiles: list[str] = Field(min_length=1, max_length=MAX_PROFILES)
    workflows: list[str] = Field(min_length=1, max_length=MAX_WORKFLOWS)
    # Values for the workflows' variables on every run of this trigger.
    variables: dict[str, str] = Field(default_factory=dict)
    # Stop a profile's browser after the run if the trigger was what opened it.
    close_profile: bool = True
    created_at: str = ""
    updated_at: str = ""

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("the name cannot be empty")
        return v

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", v):
            raise ValueError("an id uses letters, digits, - and _")
        return v

    @field_validator("profiles", "workflows")
    @classmethod
    def _names(cls, v: list[str]) -> list[str]:
        out = []
        for name in v:
            name = name.strip()
            if name and name not in out:
                out.append(name)
        if not out:
            raise ValueError("pick at least one")
        return out

    @field_validator("variables")
    @classmethod
    def _variables(cls, v: dict[str, str]) -> dict[str, str]:
        for name in v:
            if not VARIABLE_NAME.match(name):
                raise ValueError(f"'{name}' is not a valid variable name")
        return v


def describe(trigger: Trigger) -> str:
    """One line for logs: what fires it."""
    if trigger.type == "clipboard":
        return f"clipboard{f' /{trigger.pattern}/' if trigger.pattern else ''}"
    if trigger.type == "file":
        return f"new file in {trigger.folder} ({trigger.pattern or '*'})"
    if trigger.type == "schedule":
        parts = [f"every {trigger.every_minutes} min"] if trigger.every_minutes else []
        if trigger.at:
            parts.append("at " + ", ".join(trigger.at))
        return "schedule " + " and ".join(parts)
    return "webhook"
