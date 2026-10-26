"""A workflow: the steps recorded in a profile's browser, and how to replay them.

Stored as JSON in WORKFLOWS_DIR/<name>.json. Every step is checked after it
runs; a step that fails is retried, and when the retries run out the browser is
restarted and the workflow starts over from the first step.

Steps can use variables: "{{name}}" in a value, URL, selector or check is
replaced when the step runs. Variables come from the workflow's `variables`,
from the built-in `profile`, and from earlier get_text / ai steps (`save_as`).
"""

from __future__ import annotations

import re
import secrets
from typing import Literal

from pydantic import BaseModel, Field, field_validator

ACTIONS = (
    "navigate",
    "click",
    "fill",
    "press",
    "select",
    "check",
    "uncheck",
    "hover",
    "scroll",
    "wait",
    "switch_tab",
    "get_text",
    "ai",
)
Action = Literal[
    "navigate",
    "click",
    "fill",
    "press",
    "select",
    "check",
    "uncheck",
    "hover",
    "scroll",
    "wait",
    "switch_tab",
    "get_text",
    "ai",
]
# Actions that act on an element and so need at least one selector.
ELEMENT_ACTIONS = ("click", "fill", "select", "check", "uncheck", "hover")
# Actions whose result goes into a variable (`save_as`).
SAVING_ACTIONS = ("get_text", "ai")

CHECK_TYPES = (
    "auto",
    "none",
    "url_contains",
    "title_contains",
    "selector_visible",
    "text_visible",
)
CheckType = Literal[
    "auto",
    "none",
    "url_contains",
    "title_contains",
    "selector_visible",
    "text_visible",
]

MAX_STEPS = 500
MAX_DELAY_MS = 600_000
MAX_VARIABLES = 50
MAX_VARIABLE_TEXT = 20_000
BUILT_IN_VARIABLES = ("profile",)

VARIABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_REFERENCE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def new_step_id() -> str:
    return secrets.token_hex(4)


def references(text: str) -> list[str]:
    """Variable names used as {{name}} in a text."""
    return _REFERENCE.findall(text or "")


def render(text: str, variables: dict[str, str]) -> str:
    """Replace each {{name}}; KeyError names a variable that has no value."""
    return _REFERENCE.sub(lambda m: variables[m.group(1)], text or "")


class StepCheck(BaseModel):
    """How a step proves it worked.

    auto: the action's own check (the field holds the typed text, the box is
    ticked, a click that navigated while recording reaches the same page...).
    none: only require the action itself not to fail. The other types wait
    for a condition on the page; `value` is the text or selector to wait for.
    """

    type: CheckType = "auto"
    value: str = Field("", max_length=2_000)


def _clean(selectors: list[str]) -> list[str]:
    out = []
    for s in selectors:
        s = s.strip()
        if s and len(s) <= 2_000 and s not in out:
            out.append(s)
    return out


class Step(BaseModel):
    id: str = Field(default_factory=new_step_id, max_length=32)
    action: Action
    # Playwright selectors, tried in order; the first that finds an element wins.
    selectors: list[str] = Field(default_factory=list, max_length=10)
    # navigate: URL, fill: text, press: key, select: option value,
    # scroll: "x,y", wait: milliseconds, switch_tab: tab index,
    # get_text: optional regex (its first group, or the whole match, is kept),
    # ai: the prompt.
    value: str = Field("", max_length=20_000)
    label: str = Field("", max_length=300)
    # Frame the element lives in (name or URL prefix); blank = the page itself.
    frame: str = Field("", max_length=2_000)
    # Page the recording reached after this step, used by the auto check.
    expect_url: str = Field("", max_length=4_000)
    delay_ms: int = Field(500, ge=0, le=MAX_DELAY_MS, description="Pause before the step")
    char_delay_ms: int = Field(
        0, ge=0, le=2_000, description="fill: pause between keystrokes; 0 fills at once"
    )
    # Hover these first (menus and reaction bars that only appear on hover),
    # then wait hover_ms before the action.
    hover_selectors: list[str] = Field(default_factory=list, max_length=10)
    hover_ms: int = Field(800, ge=0, le=60_000)
    # get_text / ai: the variable that receives the result.
    save_as: str = Field("", max_length=64)
    timeout_ms: int | None = Field(None, ge=500, le=300_000)
    retries: int | None = Field(None, ge=0, le=10)
    check: StepCheck = Field(default_factory=StepCheck)
    enabled: bool = True
    # The value is a password; interfaces mask it.
    sensitive: bool = False

    @field_validator("selectors", "hover_selectors")
    @classmethod
    def _clean_selectors(cls, v: list[str]) -> list[str]:
        return _clean(v)

    @field_validator("save_as")
    @classmethod
    def _check_save_as(cls, v: str) -> str:
        v = v.strip()
        if v and not VARIABLE_NAME.match(v):
            raise ValueError(
                "a variable name uses letters, digits and _ and cannot start with a digit"
            )
        return v

    def templated(self) -> list[str]:
        """The texts that may use {{variables}}."""
        return [
            self.value,
            self.frame,
            self.expect_url,
            self.check.value,
            *self.selectors,
            *self.hover_selectors,
        ]


class Settings(BaseModel):
    speed: float = Field(1.0, ge=0.1, le=10, description="Divides every delay; 2 = twice as fast")
    step_timeout_ms: int = Field(15_000, ge=1_000, le=300_000)
    retries: int = Field(2, ge=0, le=10, description="Retries of a failed step before restarting")
    retry_delay_ms: int = Field(1_500, ge=0, le=MAX_DELAY_MS)
    max_restarts: int = Field(
        3, ge=0, le=20, description="Browser restarts (run from the start) before giving up"
    )
    close_when_done: bool = Field(False, description="Stop the browser after a successful run")


class Workflow(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field("", max_length=2_000)
    profile: str = Field("", max_length=64, description="Profile it was recorded in")
    created_at: str = ""
    updated_at: str = ""
    settings: Settings = Field(default_factory=Settings)
    # Starting values of the variables the steps use as {{name}}.
    variables: dict[str, str] = Field(default_factory=dict)
    steps: list[Step] = Field(default_factory=list, max_length=MAX_STEPS)

    @field_validator("variables")
    @classmethod
    def _check_variables(cls, v: dict[str, str]) -> dict[str, str]:
        if len(v) > MAX_VARIABLES:
            raise ValueError(f"at most {MAX_VARIABLES} variables")
        for name, value in v.items():
            if not VARIABLE_NAME.match(name):
                raise ValueError(f"'{name}' is not a valid variable name")
            if name in BUILT_IN_VARIABLES:
                raise ValueError(f"'{name}' is a built-in variable")
            if len(value) > MAX_VARIABLE_TEXT:
                raise ValueError(f"variable '{name}' is too long")
        return v


def step_problem(step: Step) -> str | None:
    """Why an enabled step cannot run as written, or None."""
    if step.action in ELEMENT_ACTIONS and not step.selectors:
        return "needs a selector"
    # fill may type nothing (clear a field) and an option's value may be "".
    if step.action in ("navigate", "press", "ai") and not step.value.strip():
        return "needs a value"
    if step.action in SAVING_ACTIONS and not step.save_as:
        return "needs a variable to save into"
    if step.action == "get_text" and step.value:
        try:
            re.compile(step.value)
        except re.error as e:
            return f"invalid regular expression: {e}"
    if step.action in ("wait", "switch_tab") and not step.value.strip().isdigit():
        return "value must be a whole number"
    if step.action == "scroll":
        parts = step.value.split(",")
        if len(parts) != 2 or not all(p.strip().lstrip("-").isdigit() for p in parts):
            return 'value must be "x,y"'
    if step.check.type not in ("auto", "none") and not step.check.value.strip():
        return "the check needs a value"
    return None


def problems(workflow: Workflow) -> list[str]:
    """What stops the enabled steps from running, one line per step.

    A step may only use variables the workflow defines, the built-in ones, or
    ones an earlier enabled step saves.
    """
    out = []
    known = {*workflow.variables, *BUILT_IN_VARIABLES}
    for index, step in enumerate(workflow.steps, start=1):
        if not step.enabled:
            continue
        name = f"Step {index} ({step.label or step.action})"
        if problem := step_problem(step):
            out.append(f"{name}: {problem}")
        # get_text's value is a regex: braces there are its own.
        texts = step.templated()[1:] if step.action == "get_text" else step.templated()
        unknown = sorted({r for t in texts for r in references(t)} - known)
        if unknown:
            out.append(f"{name}: unknown variable {', '.join('{{' + u + '}}' for u in unknown)}")
        if step.save_as:
            known.add(step.save_as)
    return out


def uses_ai(workflow: Workflow) -> bool:
    return any(s.enabled and s.action == "ai" for s in workflow.steps)


def scaled(ms: int, speed: float) -> float:
    """Seconds to wait for a delay of `ms` at the workflow's speed."""
    return max(0.0, ms / 1000 / (speed or 1.0))
