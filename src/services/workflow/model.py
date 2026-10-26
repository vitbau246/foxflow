"""A workflow: the steps recorded in a profile's browser, and how to replay them.

Stored as JSON in WORKFLOWS_DIR/<name>.json. Every step is checked after it
runs; a step that fails is retried, and when the retries run out the browser is
restarted and the workflow starts over from the first step.

Steps can use variables: "{{name}}" in a value, URL, selector or check is
replaced when the step runs. Variables come from the workflow's `variables`,
from the built-in `profile`, and from earlier get_text / ai / assign / for
steps (`save_as`).

The steps are a flat list; "if", "for" and "while" open a block that "end"
closes ("else" splits an if, "break" leaves the innermost loop). FoxFlow runs
these itself (services/workflow/runner.py); only the browser steps and page
conditions reach the browser.
"""

from __future__ import annotations

import contextlib
import re
import secrets
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .expression import ExpressionError, names, parse

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
    "assign",
    "if",
    "else",
    "end",
    "for",
    "while",
    "break",
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
    "assign",
    "if",
    "else",
    "end",
    "for",
    "while",
    "break",
]
# Actions that act on an element and so need at least one selector.
ELEMENT_ACTIONS = ("click", "fill", "select", "check", "uncheck", "hover")
# Actions whose result goes into a variable (`save_as`); for's is optional.
SAVING_ACTIONS = ("get_text", "ai", "assign", "for")
# Run by FoxFlow between the browser steps: variables and the flow of the run.
CONTROL_ACTIONS = ("assign", "if", "else", "end", "for", "while", "break")
# Open a block that "end" closes.
BLOCK_ACTIONS = ("if", "for", "while")
LOOP_ACTIONS = ("for", "while")
# Only mark the structure: no value, no delay, no check.
MARKER_ACTIONS = ("else", "end", "break")

# What an if / while tests: the variables (an expression) or the page.
CONDITIONS = ("expression", "selector_visible", "text_visible", "url_contains", "title_contains")
ConditionType = Literal[
    "expression", "selector_visible", "text_visible", "url_contains", "title_contains"
]

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
# Rounds of one for / while loop.
MAX_LOOP_ROUNDS = 10_000
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
    # ai: the prompt, assign: text with {{variables}} or "=expression",
    # if / while: the condition, for: a count or a list (lines or commas).
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
    # get_text / ai / assign: the variable that receives the result;
    # for: the variable that holds each item (or round number).
    save_as: str = Field("", max_length=64)
    # if / while: "expression" tests variables (value is the expression); the
    # others test the page (value is the selector, text or URL / title part).
    condition: ConditionType = "expression"
    # if / while: go in when the condition does NOT hold.
    negate: bool = False
    # while: stop after this many rounds even if the condition still holds.
    max_loops: int = Field(100, ge=1, le=MAX_LOOP_ROUNDS)
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

    def expression(self) -> str | None:
        """The expression the value holds, if it is one rather than text."""
        if self.action in ("if", "while") and self.condition == "expression":
            return self.value
        if self.action == "assign" and self.value.lstrip().startswith("="):
            return self.value.lstrip()[1:]
        return None

    def value_is_template(self) -> bool:
        """get_text's value is a regex (its braces are its own); expressions name
        variables directly."""
        return self.action != "get_text" and self.expression() is None

    def templated(self) -> list[str]:
        """The texts that may use {{variables}}."""
        return [
            *([self.value] if self.value_is_template() else []),
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


@dataclass
class Block:
    """An if / for / while and the positions of its else and end."""

    start: int
    else_at: int | None = None
    end: int | None = None


def blocks(actions: list[str]) -> tuple[dict[int, Block], list[tuple[int, str]]]:
    """The block of each if / else / end / for / while / break, by position, and
    what is wrong with the structure as (position, problem)."""
    out: dict[int, Block] = {}
    errors: list[tuple[int, str]] = []
    stack: list[Block] = []
    for i, action in enumerate(actions):
        if action in BLOCK_ACTIONS:
            out[i] = Block(i)
            stack.append(out[i])
        elif action == "else":
            if not stack or actions[stack[-1].start] != "if":
                errors.append((i, "else without an if before it"))
            elif stack[-1].else_at is not None:
                errors.append((i, "the if already has an else"))
            else:
                stack[-1].else_at = i
                out[i] = stack[-1]
        elif action == "end":
            if not stack:
                errors.append((i, "end without an if, for or while before it"))
            else:
                block = stack.pop()
                block.end = i
                out[i] = block
        elif action == "break":
            loop = next((b for b in reversed(stack) if actions[b.start] in LOOP_ACTIONS), None)
            if loop is None:
                errors.append((i, "break outside a for or while"))
            else:
                out[i] = loop
    errors.extend((b.start, "has no end") for b in stack)
    return out, sorted(errors)


def depths(actions: list[str]) -> list[int]:
    """How deep each step sits in the blocks, for indenting it in an editor."""
    out, depth = [], 0
    for action in actions:
        if action in ("else", "end"):
            out.append(max(0, depth - 1))
            if action == "end":
                depth = max(0, depth - 1)
        else:
            out.append(depth)
            if action in BLOCK_ACTIONS:
                depth += 1
    return out


def unclosed(actions: list[str]) -> list[int]:
    """Positions of the blocks that no end closes."""
    _, errors = blocks(actions)
    return [i for i, problem in errors if problem == "has no end"]


def step_problem(step: Step) -> str | None:
    """Why an enabled step cannot run as written, or None."""
    if step.action in ELEMENT_ACTIONS and not step.selectors:
        return "needs a selector"
    # fill may type nothing (clear a field) and an option's value may be "".
    if step.action in ("navigate", "press", "ai", "for") and not step.value.strip():
        return "needs a value"
    if step.action in ("if", "while") and not step.value.strip():
        return "needs a condition"
    if step.action in ("get_text", "ai", "assign") and not step.save_as:
        return "needs a variable to save into"
    if (expression := step.expression()) is not None:
        try:
            parse(expression)
        except ExpressionError as e:
            return str(e)
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
    """What stops the enabled steps from running, one line per problem.

    A step may only use variables the workflow defines, the built-in ones, or
    ones an earlier enabled step saves. Every if / for / while needs its end.
    """
    found: list[tuple[int, str]] = []
    known = {*workflow.variables, *BUILT_IN_VARIABLES}
    enabled = [(n, s) for n, s in enumerate(workflow.steps, start=1) if s.enabled]

    def name(index: int, step: Step) -> str:
        return f"Step {index} ({step.label or step.action})"

    for index, step in enabled:
        if problem := step_problem(step):
            found.append((index, f"{name(index, step)}: {problem}"))
        used = {r for t in step.templated() for r in references(t)}
        if (expression := step.expression()) is not None:
            with contextlib.suppress(ExpressionError):  # step_problem reported it
                used.update(names(expression))
        if unknown := sorted(used - known):
            listed = ", ".join("{{" + u + "}}" for u in unknown)
            found.append((index, f"{name(index, step)}: unknown variable {listed}"))
        if step.save_as and step.action in SAVING_ACTIONS:
            known.add(step.save_as)
    _, errors = blocks([s.action for _, s in enabled])
    for position, problem in errors:
        index, step = enabled[position]
        found.append((index, f"{name(index, step)}: {problem}"))
    return [line for _, line in sorted(found, key=lambda f: f[0])]


def uses_ai(workflow: Workflow) -> bool:
    return any(s.enabled and s.action == "ai" for s in workflow.steps)


def scaled(ms: int, speed: float) -> float:
    """Seconds to wait for a delay of `ms` at the workflow's speed."""
    return max(0.0, ms / 1000 / (speed or 1.0))
