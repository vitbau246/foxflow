"""Edit a workflow: run settings, and each step's delay, typing speed, check and retries.

If / Repeat blocks are steps too: the rows between an opener and its End are
indented, and picking If or a Repeat for a step adds the End it needs.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any

import flet as ft
from pydantic import ValidationError

from ...core.strings import get_string
from ...services.ai.settings import AISettingsStore
from ...services.workflow.model import (
    ACTIONS,
    BLOCK_ACTIONS,
    CHECK_TYPES,
    CONDITIONS,
    CONTROL_ACTIONS,
    ELEMENT_ACTIONS,
    MARKER_ACTIONS,
    Workflow,
    depths,
    new_step_id,
    unclosed,
)
from ...services.workflow.store import WorkflowError, WorkflowStore
from ..theme.colors import COLORS, FONT_BOLD, FONT_DATA, FONT_SEMIBOLD
from ..theme.styles import ACCENT_STYLE, DANGER_ICON_STYLE, ICON_STYLE, OUTLINE_STYLE

SPEEDS = (0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 3, 5)
_DATA = ft.TextStyle(font_family=FONT_DATA, size=13)
_FIELD: dict[str, Any] = dict(
    border_radius=8,
    bgcolor=COLORS["input_bg"],
    color=COLORS["text_main"],
    border_color=COLORS["rule_strong"],
    focused_border_color=COLORS["sidebar"],
    hint_style=ft.TextStyle(color=COLORS["text_dim"], size=12.5),
    cursor_color=COLORS["accent"],
    text_size=13,
    # Material's 48px, the height dropdowns cannot go below, so a row lines up.
    content_padding=ft.Padding.symmetric(horizontal=10),
)
# Step table columns: (expand, fixed width), shared by the header and every row.
COLUMNS = {
    "num": (None, 26),
    "on": (None, 34),
    "step": (1, None),
    "delay": (None, 92),
    "typing": (None, 92),
    "check": (None, 200),
    "retries": (None, 100),
    "acts": (None, 200),
}
# Pixels of indent per block level.
_INDENT = 18


def _cell(key: str, content: ft.Control | None) -> ft.Container:
    expand, width = COLUMNS[key]
    return ft.Container(content=content, expand=expand, width=width)


def _label(text: str) -> ft.Text:
    return ft.Text(text, size=12.5, font_family=FONT_SEMIBOLD, color=COLORS["text_sub"])


def _field(label: str, control: ft.Control, hint: str | None = None) -> ft.Column:
    return ft.Column(
        spacing=6,
        tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[
            _label(label),
            control,
            *([ft.Text(hint, size=12, color=COLORS["text_dim"])] if hint else []),
        ],
    )


def _int(value: str | None, fallback: int | None) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return fallback


def _number(value: Any, hint: str = "", on_change: Callable | None = None) -> ft.TextField:
    return ft.TextField(
        value="" if value is None else str(value),
        hint_text=hint,
        text_style=_DATA,
        keyboard_type=ft.KeyboardType.NUMBER,
        input_filter=ft.NumbersOnlyInputFilter(),
        on_change=on_change,
        **_FIELD,
    )


def target_text(step: dict[str, Any]) -> str:
    """What a step types, opens or acts on; the second line of its row."""
    hover = step.get("hover_selectors") or []
    return (f"↗ {hover[0]} · " if hover else "") + _what(step)


def _what(step: dict[str, Any]) -> str:
    first = (step.get("selectors") or [""])[0]
    action, value = step["action"], step.get("value", "")
    into = f" → {{{{{step['save_as']}}}}}" if step.get("save_as") else ""
    if action in MARKER_ACTIONS:
        return ""
    if action == "assign":
        return f"{{{{{step.get('save_as', '')}}}}} = {value}"
    if action == "for":
        return " · ".join(line.strip() for line in value.splitlines() if line.strip()) + into
    if action in ("if", "while"):
        condition = step.get("condition", "expression")
        text = (
            value if condition == "expression" else f"{get_string(f'wf_cond_{condition}')}: {value}"
        )
        limit = f" · ≤ {step.get('max_loops', 100)}" if action == "while" else ""
        return ("not " if step.get("negate") else "") + text + limit
    if action == "fill":
        return "•••" if step.get("sensitive") else f"“{value}” → {first}"
    if action == "get_text":
        return (first or "body") + (f" /{value}/" if value else "") + into
    if action == "ai":
        return f"“{value}”{into}"
    if action in ("navigate", "press", "scroll", "wait", "switch_tab"):
        return value
    if action == "select":
        return f"{value} → {first}"
    return first


# Actions that find an element and so may hover something first.
_HOVERING = (*ELEMENT_ACTIONS, "press", "get_text")


def new_step(**changes: Any) -> dict[str, Any]:
    """A step as the editor holds it: every field, with the defaults for a new one."""
    return {
        "id": new_step_id(),
        "action": "wait",
        "value": "1000",
        "label": "",
        "selectors": [],
        "frame": "",
        "expect_url": "",
        "delay_ms": 0,
        "char_delay_ms": 0,
        "timeout_ms": None,
        "retries": None,
        "check": {"type": "auto", "value": ""},
        "enabled": True,
        "sensitive": False,
        "hover_selectors": [],
        "hover_ms": 800,
        "save_as": "",
        "condition": "expression",
        "negate": False,
        "max_loops": 100,
        **changes,
    }


def close_block(steps: list[dict[str, Any]], i: int) -> bool:
    """Add an End after step i when it opens a block nothing closes; True if added."""
    if steps[i]["action"] not in BLOCK_ACTIONS:
        return False
    if i not in unclosed([s["action"] for s in steps]):
        return False
    steps.insert(i + 1, new_step(action="end", value=""))
    return True


def open_workflow_editor(
    page: ft.Page,
    store: WorkflowStore,
    name: str,
    on_saved: Callable[[], None] | None = None,
    ai_settings: AISettingsStore | None = None,
) -> None:
    from .ai_settings import open_ai_settings_dialog

    workflow = store.get(name)
    if workflow is None:
        return
    data = workflow.model_dump()
    steps: list[dict[str, Any]] = data["steps"]
    settings = data["settings"]
    expanded: set[str] = set()

    error_text = ft.Text("", size=12.5, color=COLORS["error"], visible=False, selectable=True)
    description = ft.TextField(value=data["description"], **_FIELD)
    speed = ft.Dropdown(
        value=str(settings["speed"]),
        text_size=13,
        bgcolor=COLORS["input_bg"],
        border_color=COLORS["rule_strong"],
        focused_border_color=COLORS["sidebar"],
        border_radius=8,
        options=[
            ft.dropdown.Option(str(v), f"x{v:g}")
            for v in sorted({*SPEEDS, float(settings["speed"])})
        ],
    )
    # Dropdown values are strings; "1" and "1.0" must name the same option.
    speed.value = next(
        (o.key for o in speed.options if float(o.key) == float(settings["speed"])), "1"
    )
    timeout = _number(settings["step_timeout_ms"] // 1000)
    retries = _number(settings["retries"])
    retry_delay = _number(settings["retry_delay_ms"])
    restarts = _number(settings["max_restarts"])
    close_when_done = ft.Checkbox(
        label=get_string("wf_close_when_done"), value=settings["close_when_done"]
    )
    policy = ft.Text(size=12.5, color=COLORS["text_sub"], expand=True)

    def sync_policy(_: Any = None) -> None:
        policy.value = get_string(
            "wf_policy", retries=retries.value or 0, restarts=restarts.value or 0
        )
        with contextlib.suppress(Exception):
            policy.update()

    retries.on_change = restarts.on_change = sync_policy
    sync_policy()

    steps_column = ft.Column(spacing=0, tight=True)

    # Variables as rows while editing, so renaming one keeps its place.
    variables = [{"name": k, "value": v} for k, v in data.get("variables", {}).items()]
    variables_column = ft.Column(spacing=8, tight=True)

    def draw_variables() -> None:
        rows = []
        for i, var in enumerate(variables):

            def setter(key: str, var: dict = var) -> Callable:
                def on_change(e: ft.ControlEvent) -> None:
                    var[key] = (e.control.value or "").strip() if key == "name" else e.control.value

                return on_change

            def remove(_: ft.ControlEvent, i: int = i) -> None:
                del variables[i]
                draw_variables()

            rows.append(
                ft.Row(
                    spacing=8,
                    controls=[
                        ft.Container(
                            width=220,
                            content=ft.TextField(
                                value=var["name"],
                                hint_text=get_string("wf_var_name"),
                                text_style=_DATA,
                                on_change=setter("name"),
                                **_FIELD,
                            ),
                        ),
                        ft.Container(
                            expand=True,
                            # Several lines (a list for Repeat for) stay several lines.
                            content=ft.TextField(
                                value=var["value"],
                                hint_text=get_string("wf_var_value"),
                                on_change=setter("value"),
                                multiline=True,
                                max_lines=5,
                                **_FIELD,
                            ),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.DELETE_OUTLINE,
                            icon_size=18,
                            icon_color=COLORS["text_sub"],
                            tooltip=get_string("wf_var_remove"),
                            style=DANGER_ICON_STYLE,
                            on_click=remove,
                        ),
                    ],
                )
            )
        variables_column.controls = rows
        with contextlib.suppress(Exception):
            variables_column.update()

    def add_variable(_: ft.ControlEvent) -> None:
        variables.append({"name": "", "value": ""})
        draw_variables()

    ai_status = ft.Text("", size=12.5, color=COLORS["text_dim"])

    def show_ai() -> None:
        if ai_settings is None:
            return
        info = ai_settings.public()
        ai_status.value = (
            get_string("ai_status_on", model=info["model"])
            if info["configured"]
            else get_string("ai_status_off")
        )
        with contextlib.suppress(Exception):
            ai_status.update()

    draw_variables()
    show_ai()
    bulk_delay = _number(None, get_string("wf_col_delay"))
    bulk_typing = _number(None, get_string("wf_col_typing"))

    def apply_all(_: ft.ControlEvent) -> None:
        delay, typing = _int(bulk_delay.value, None), _int(bulk_typing.value, None)
        for st in steps:
            if delay is not None:
                st["delay_ms"] = delay
            if typing is not None and st["action"] == "fill":
                st["char_delay_ms"] = typing
        draw_steps()

    def move(i: int, d: int) -> None:
        steps[i], steps[i + d] = steps[i + d], steps[i]
        draw_steps()

    def remove(i: int) -> None:
        del steps[i]
        draw_steps()

    def insert_below(i: int) -> None:
        step = new_step()
        steps.insert(i + 1, step)
        expanded.add(step["id"])
        draw_steps()

    def toggle(step_id: str) -> None:
        expanded.symmetric_difference_update({step_id})
        draw_steps()

    def header() -> ft.Container:
        def h(key: str, text: str = "") -> ft.Container:
            return _cell(
                key, ft.Text(text, size=12, font_family=FONT_SEMIBOLD, color=COLORS["text_dim"])
            )

        return ft.Container(
            height=38,
            padding=ft.Padding.symmetric(horizontal=12),
            bgcolor=COLORS["bg"],
            border_radius=ft.BorderRadius.only(top_left=9, top_right=9),
            content=ft.Row(
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    h("num", "#"),
                    h("on"),
                    h("step", get_string("wf_col_step")),
                    h("delay", get_string("wf_col_delay")),
                    h("typing", get_string("wf_col_typing")),
                    h("check", get_string("wf_col_check")),
                    h("retries", get_string("wf_col_retries")),
                    h("acts"),
                ],
            ),
        )

    def step_row(i: int, st: dict[str, Any], depth: int = 0) -> ft.Container:
        def setter(key: str, numeric: bool = False, fallback: Any = 0) -> Callable:
            def on_change(e: ft.ControlEvent) -> None:
                st[key] = _int(e.control.value, fallback) if numeric else e.control.value

            return on_change

        check_value = ft.TextField(
            value=st["check"]["value"],
            hint_text=get_string("wf_check_value"),
            visible=st["check"]["type"] not in ("auto", "none"),
            on_change=lambda e: st["check"].update(value=e.control.value),
            **_FIELD,
        )

        def on_check(e: ft.ControlEvent) -> None:
            st["check"]["type"] = e.control.value
            check_value.visible = e.control.value not in ("auto", "none")
            check_value.update()

        check = ft.Dropdown(
            value=st["check"]["type"],
            text_size=13,
            bgcolor=COLORS["input_bg"],
            border_color=COLORS["rule_strong"],
            focused_border_color=COLORS["sidebar"],
            border_radius=8,
            on_select=on_check,
            options=[ft.dropdown.Option(c, get_string(f"wf_check_{c}")) for c in CHECK_TYPES],
        )
        enabled = ft.Checkbox(
            value=st["enabled"],
            tooltip=get_string("wf_step_on", n=i + 1),
            on_change=lambda e: (st.update(enabled=e.control.value), draw_steps()),
        )
        typing = (
            _number(st["char_delay_ms"], on_change=setter("char_delay_ms", True))
            if st["action"] == "fill"
            else ft.Text("—", color=COLORS["text_dim"])
        )
        action = st["action"]
        # Control steps have no check; markers no delay; only conditions retry.
        delay_cell = (
            ft.Text("—", color=COLORS["text_dim"])
            if action in MARKER_ACTIONS
            else _number(st["delay_ms"], on_change=setter("delay_ms", True))
        )
        check_cell = (
            ft.Text("—", color=COLORS["text_dim"])
            if action in CONTROL_ACTIONS
            else ft.Column(spacing=4, tight=True, controls=[check, check_value])
        )
        retries_cell = (
            ft.Text("—", color=COLORS["text_dim"])
            if action in CONTROL_ACTIONS and action not in ("if", "while")
            else _number(
                st["retries"],
                get_string("wf_default"),
                on_change=setter("retries", True, None),
            )
        )

        def icon(name: Any, tip: str, fn: Callable, disabled: bool = False, danger: bool = False):
            return ft.IconButton(
                icon=name,
                icon_size=18,
                icon_color=COLORS["text_sub"],
                tooltip=tip,
                disabled=disabled,
                style=DANGER_ICON_STYLE if danger else ICON_STYLE,
                on_click=lambda _: fn(),
            )

        dim = 1.0 if st["enabled"] else 0.5
        row = ft.Row(
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                _cell(
                    "num",
                    ft.Text(str(i + 1), size=12, font_family=FONT_DATA, color=COLORS["text_dim"]),
                ),
                _cell("on", enabled),
                _cell(
                    "step",
                    ft.Column(
                        spacing=1,
                        tight=True,
                        opacity=dim,
                        controls=[
                            ft.Row(
                                spacing=6,
                                controls=[
                                    ft.Container(
                                        padding=ft.Padding.symmetric(horizontal=6, vertical=1),
                                        border_radius=5,
                                        border=ft.Border.all(1, COLORS["rule_strong"]),
                                        content=ft.Text(
                                            get_string(f"wf_act_{st['action']}"),
                                            size=11.5,
                                            font_family=FONT_SEMIBOLD,
                                            color=COLORS["text_sub"],
                                        ),
                                    ),
                                    ft.Text(
                                        st["label"],
                                        size=13.5,
                                        font_family=FONT_SEMIBOLD,
                                        color=COLORS["text_main"],
                                        no_wrap=True,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                        expand=True,
                                    ),
                                ],
                            ),
                            ft.Text(
                                target_text(st),
                                size=11.5,
                                font_family=FONT_DATA,
                                color=COLORS["text_dim"],
                                no_wrap=True,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                        ],
                    ),
                ),
                _cell("delay", delay_cell),
                _cell("typing", typing),
                _cell("check", check_cell),
                _cell("retries", retries_cell),
                _cell(
                    "acts",
                    ft.Row(
                        spacing=0,
                        alignment=ft.MainAxisAlignment.END,
                        controls=[
                            icon(ft.Icons.TUNE, get_string("wf_details"), lambda: toggle(st["id"])),
                            icon(
                                ft.Icons.KEYBOARD_ARROW_UP,
                                get_string("wf_move_up"),
                                lambda: move(i, -1),
                                disabled=i == 0,
                            ),
                            icon(
                                ft.Icons.KEYBOARD_ARROW_DOWN,
                                get_string("wf_move_down"),
                                lambda: move(i, 1),
                                disabled=i == len(steps) - 1,
                            ),
                            icon(
                                ft.Icons.ADD, get_string("wf_insert_below"), lambda: insert_below(i)
                            ),
                            icon(
                                ft.Icons.DELETE_OUTLINE,
                                get_string("wf_remove_step"),
                                lambda: remove(i),
                                danger=True,
                            ),
                        ],
                    ),
                ),
            ],
        )
        body: list[ft.Control] = [row]
        if st["id"] in expanded:
            body.append(step_details(st))
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            border=ft.Border.only(top=ft.BorderSide(1, COLORS["card_border"])),
            # The block guide: a rule down the left of the indent, one per level.
            content=ft.Row(
                spacing=0,
                vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[
                    *(
                        ft.Container(
                            width=_INDENT,
                            border=ft.Border.only(left=ft.BorderSide(2, COLORS["rule_strong"])),
                        )
                        for _ in range(depth)
                    ),
                    ft.Column(spacing=8, tight=True, expand=True, controls=body),
                ],
            ),
        )

    def step_details(st: dict[str, Any]) -> ft.Container:
        def text(key: str, numeric: bool = False, **kw: Any) -> ft.TextField:
            value = st[key]

            def on_change(e: ft.ControlEvent) -> None:
                raw = e.control.value
                st[key] = (_int(raw, None) if raw.strip() else None) if numeric else raw

            return ft.TextField(
                value="" if value is None else str(value), on_change=on_change, **_FIELD, **kw
            )

        def on_action(e: ft.ControlEvent) -> None:
            st["action"] = e.control.value
            if st["action"] in MARKER_ACTIONS:
                st["value"] = ""
            elif st["action"] in CONTROL_ACTIONS and st["value"] == "1000":
                st["value"] = ""  # the new step's wait time means nothing here
            close_block(steps, steps.index(st))
            draw_steps()

        def on_selectors(e: ft.ControlEvent) -> None:
            st["selectors"] = [s.strip() for s in (e.control.value or "").splitlines() if s.strip()]

        def lines(key: str) -> ft.TextField:
            def on_change(e: ft.ControlEvent) -> None:
                st[key] = [s.strip() for s in (e.control.value or "").splitlines() if s.strip()]

            return ft.TextField(
                value="\n".join(st[key]),
                multiline=True,
                min_lines=2,
                max_lines=5,
                text_style=_DATA,
                on_change=on_change,
                **_FIELD,
            )

        if st["action"] == "ai":
            value = text("value", multiline=True, min_lines=3, max_lines=8)
        else:
            value = text(
                "value", password=st["sensitive"], can_reveal_password=True, text_style=_DATA
            )
        action = ft.Dropdown(
            value=st["action"],
            text_size=13,
            bgcolor=COLORS["input_bg"],
            border_color=COLORS["rule_strong"],
            focused_border_color=COLORS["sidebar"],
            border_radius=8,
            on_select=on_action,
            options=[ft.dropdown.Option(a, get_string(f"wf_act_{a}")) for a in ACTIONS],
        )
        selectors = ft.TextField(
            value="\n".join(st["selectors"]),
            multiline=True,
            min_lines=2,
            max_lines=5,
            text_style=_DATA,
            on_change=on_selectors,
            **_FIELD,
        )

        def on_sensitive(e: ft.ControlEvent) -> None:
            st["sensitive"] = e.control.value
            draw_steps()

        def pair(a: ft.Control, b: ft.Control) -> ft.Row:
            return ft.Row(
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[ft.Container(expand=1, content=a), ft.Container(expand=1, content=b)],
            )

        if st["action"] in CONTROL_ACTIONS:
            return control_details(st, action, text, pair)

        return ft.Container(
            padding=ft.Padding.only(left=70, bottom=6),
            content=ft.Column(
                spacing=8,
                tight=True,
                controls=[
                    pair(
                        _field(get_string("wf_field_action"), action),
                        _field(get_string("wf_field_label"), text("label")),
                    ),
                    _field(get_string("wf_field_value"), value, get_string("wf_field_value_hint")),
                    *(
                        [
                            _field(
                                get_string("wf_field_save_as"),
                                text("save_as", text_style=_DATA),
                                get_string("wf_field_save_as_hint"),
                            )
                        ]
                        if st["action"] in ("get_text", "ai")
                        else []
                    ),
                    *(
                        [
                            _field(
                                get_string("wf_field_hover"),
                                lines("hover_selectors"),
                                get_string("wf_field_hover_hint"),
                            ),
                            ft.Container(
                                width=220,
                                content=_field(
                                    get_string("wf_field_hover_ms"),
                                    text("hover_ms", numeric=True, text_style=_DATA),
                                ),
                            ),
                        ]
                        if st["action"] in _HOVERING
                        else []
                    ),
                    *(
                        [
                            ft.Checkbox(
                                label=get_string("wf_field_sensitive"),
                                value=st["sensitive"],
                                on_change=on_sensitive,
                            )
                        ]
                        if st["action"] == "fill"
                        else []
                    ),
                    _field(
                        get_string("wf_field_selectors"),
                        selectors,
                        get_string("wf_field_selectors_hint"),
                    ),
                    pair(
                        _field(
                            get_string("wf_field_frame"),
                            text("frame", text_style=_DATA),
                            get_string("wf_field_frame_hint"),
                        ),
                        _field(
                            get_string("wf_field_timeout"),
                            text("timeout_ms", numeric=True, text_style=_DATA),
                            get_string("wf_field_timeout_hint"),
                        ),
                    ),
                    _field(
                        get_string("wf_field_expect"),
                        text("expect_url", text_style=_DATA),
                        get_string("wf_field_expect_hint"),
                    ),
                ],
            ),
        )

    def control_details(
        st: dict[str, Any], action: ft.Dropdown, text: Callable, pair: Callable
    ) -> ft.Container:
        """The fields of an assign, if, for, while or a block marker."""
        kind = st["action"]
        controls: list[ft.Control] = [
            pair(
                _field(get_string("wf_field_action"), action),
                _field(get_string("wf_field_label"), text("label")),
            )
        ]
        if kind == "assign":
            controls += [
                _field(
                    get_string("wf_field_save_as"),
                    text("save_as", text_style=_DATA),
                    get_string("wf_field_save_as_hint"),
                ),
                _field(
                    get_string("wf_field_value"),
                    text("value", text_style=_DATA),
                    get_string("wf_field_assign_hint"),
                ),
            ]
        elif kind == "for":
            controls += [
                _field(
                    get_string("wf_field_for_value"),
                    text("value", multiline=True, min_lines=2, max_lines=8, text_style=_DATA),
                    get_string("wf_field_for_hint"),
                ),
                _field(
                    get_string("wf_field_for_var"),
                    text("save_as", text_style=_DATA),
                    get_string("wf_field_for_var_hint"),
                ),
            ]
        elif kind in ("if", "while"):

            def on_condition(e: ft.ControlEvent) -> None:
                st["condition"] = e.control.value
                draw_steps()

            def on_negate(e: ft.ControlEvent) -> None:
                st["negate"] = bool(e.control.value)
                draw_steps()

            condition = ft.Dropdown(
                value=st.get("condition", "expression"),
                text_size=13,
                bgcolor=COLORS["input_bg"],
                border_color=COLORS["rule_strong"],
                focused_border_color=COLORS["sidebar"],
                border_radius=8,
                on_select=on_condition,
                options=[ft.dropdown.Option(c, get_string(f"wf_cond_{c}")) for c in CONDITIONS],
            )
            controls += [
                pair(
                    _field(get_string("wf_field_condition"), condition),
                    _field(get_string("wf_field_cond_value"), text("value", text_style=_DATA)),
                ),
                ft.Text(get_string("wf_field_cond_hint"), size=12, color=COLORS["text_dim"]),
                ft.Checkbox(
                    label=get_string("wf_field_negate"),
                    value=bool(st.get("negate")),
                    on_change=on_negate,
                ),
            ]
            extra: list[ft.Control] = []
            if kind == "while":
                extra.append(
                    _field(
                        get_string("wf_field_max_loops"),
                        text("max_loops", numeric=True, text_style=_DATA),
                    )
                )
            if st.get("condition", "expression") != "expression":
                extra.append(
                    _field(
                        get_string("wf_field_cond_wait"),
                        text("timeout_ms", numeric=True, text_style=_DATA),
                        get_string("wf_field_cond_wait_hint"),
                    )
                )
                extra.append(
                    _field(
                        get_string("wf_field_frame"),
                        text("frame", text_style=_DATA),
                        get_string("wf_field_frame_hint"),
                    )
                )
            for k in range(0, len(extra), 2):
                controls.append(pair(extra[k], extra[k + 1]) if k + 1 < len(extra) else extra[k])
        return ft.Container(
            padding=ft.Padding.only(left=70, bottom=6),
            content=ft.Column(spacing=8, tight=True, controls=controls),
        )

    def draw_steps() -> None:
        levels = depths([st["action"] for st in steps])
        steps_column.controls = [
            header(),
            *(step_row(i, st, levels[i]) for i, st in enumerate(steps)),
        ]
        with contextlib.suppress(Exception):
            steps_column.update()

    def add_step(_: ft.ControlEvent) -> None:
        step = new_step()
        steps.append(step)
        expanded.add(step["id"])
        draw_steps()

    def save(_: ft.ControlEvent) -> None:
        data["description"] = (description.value or "").strip()
        data["variables"] = {v["name"]: v["value"] for v in variables if v["name"]}
        for st in steps:
            if st.get("hover_ms") is None:
                st["hover_ms"] = 800
            if st.get("max_loops") is None:
                st["max_loops"] = 100
        data["settings"] = {
            "speed": float(speed.value or 1),
            "step_timeout_ms": (_int(timeout.value, 15) or 15) * 1000,
            "retries": _int(retries.value, 2),
            "retry_delay_ms": _int(retry_delay.value, 1500),
            "max_restarts": _int(restarts.value, 3),
            "close_when_done": bool(close_when_done.value),
        }
        try:
            store.save(Workflow.model_validate(data))
        except ValidationError as e:
            first = e.errors()[0]
            where = ".".join(str(p) for p in first["loc"])
            error_text.value = f"{where}: {first['msg']}"
            error_text.visible = True
            error_text.update()
            return
        except WorkflowError as e:
            error_text.value = str(e)
            error_text.visible = True
            error_text.update()
            return
        page.pop_dialog()
        if on_saved:
            on_saved()

    def setting(label_key: str, control: ft.Control) -> ft.Container:
        return ft.Container(width=170, content=_field(get_string(label_key), control))

    draw_steps()
    dlg = ft.AlertDialog(
        modal=True,
        bgcolor=COLORS["card_bg"],
        shape=ft.RoundedRectangleBorder(radius=12),
        title_padding=ft.Padding.only(left=24, right=24, top=22, bottom=0),
        content_padding=ft.Padding.only(left=24, right=24, top=8, bottom=8),
        actions_padding=ft.Padding.only(left=24, right=24, top=8, bottom=20),
        title=ft.Column(
            spacing=4,
            tight=True,
            controls=[
                ft.Text(
                    get_string("wf_edit_title"),
                    size=19,
                    font_family=FONT_BOLD,
                    color=COLORS["text_main"],
                ),
                ft.Text(
                    get_string("wf_edit_sub", name=workflow.name, count=len(steps)),
                    size=13.5,
                    color=COLORS["text_sub"],
                ),
            ],
        ),
        content=ft.Container(
            width=1080,
            content=ft.Column(
                spacing=12,
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    _field(get_string("wf_description"), description),
                    ft.Text(
                        get_string("wf_settings"),
                        size=14,
                        font_family=FONT_SEMIBOLD,
                        color=COLORS["text_main"],
                    ),
                    ft.Row(
                        spacing=12,
                        wrap=True,
                        controls=[
                            setting("wf_speed", speed),
                            setting("wf_step_timeout", timeout),
                            setting("wf_retries", retries),
                            setting("wf_retry_delay", retry_delay),
                            setting("wf_max_restarts", restarts),
                        ],
                    ),
                    close_when_done,
                    ft.Container(
                        padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                        border_radius=8,
                        bgcolor=COLORS["paper_sunk"],
                        content=ft.Row(
                            spacing=8,
                            vertical_alignment=ft.CrossAxisAlignment.START,
                            controls=[
                                ft.Icon(ft.Icons.CHECK, size=16, color=COLORS["text_dim"]),
                                policy,
                            ],
                        ),
                    ),
                    ft.Text(
                        get_string("wf_vars"),
                        size=14,
                        font_family=FONT_SEMIBOLD,
                        color=COLORS["text_main"],
                    ),
                    ft.Text(get_string("wf_vars_hint"), size=12.5, color=COLORS["text_sub"]),
                    variables_column,
                    ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.OutlinedButton(
                                get_string("wf_var_add"),
                                icon=ft.Icons.ADD,
                                style=OUTLINE_STYLE,
                                on_click=add_variable,
                            ),
                            *(
                                [
                                    ft.OutlinedButton(
                                        get_string("ai_setup"),
                                        icon=ft.Icons.SMART_TOY_OUTLINED,
                                        style=OUTLINE_STYLE,
                                        on_click=lambda _: open_ai_settings_dialog(
                                            page, ai_settings, show_ai
                                        ),
                                    ),
                                    ai_status,
                                ]
                                if ai_settings is not None
                                else []
                            ),
                        ],
                    ),
                    ft.Text(
                        get_string("wf_steps"),
                        size=14,
                        font_family=FONT_SEMIBOLD,
                        color=COLORS["text_main"],
                    ),
                    ft.Text(get_string("wf_block_hint"), size=12.5, color=COLORS["text_sub"]),
                    ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Text(get_string("wf_set_all"), size=13, color=COLORS["text_sub"]),
                            ft.Container(width=150, content=bulk_delay),
                            ft.Container(width=150, content=bulk_typing),
                            ft.OutlinedButton(
                                get_string("wf_apply_all"), style=OUTLINE_STYLE, on_click=apply_all
                            ),
                        ],
                    ),
                    ft.Container(
                        border_radius=9,
                        bgcolor=COLORS["card_bg"],
                        border=ft.Border.all(1, COLORS["card_border"]),
                        content=steps_column,
                    ),
                    ft.Row(
                        controls=[
                            ft.OutlinedButton(
                                get_string("wf_add_step"),
                                icon=ft.Icons.ADD,
                                style=OUTLINE_STYLE,
                                on_click=add_step,
                            )
                        ]
                    ),
                    error_text,
                ],
            ),
        ),
        actions=[
            ft.TextButton(
                get_string("cancel"),
                style=ft.ButtonStyle(color=COLORS["text_sub"]),
                on_click=lambda _: page.pop_dialog(),
            ),
            ft.Button(
                get_string("save_changes"), icon=ft.Icons.SAVE, style=ACCENT_STYLE, on_click=save
            ),
        ],
    )
    page.show_dialog(dlg)
