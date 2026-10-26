"""The Automation page: every profile's current or last run, then the saved workflows.

Both are ruled sheets on the profile table's pattern: a 40px header row on paper
and 58px rows, every data cell two lines. The body is rebuilt only when what it
shows changed, so buttons are not swapped under the cursor while runs progress.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import flet as ft

from ...core.strings import current_language, get_string
from ..automation_model import (
    counts,
    ddmm,
    ddmm_hhmm,
    hhmm,
    match_run,
    match_workflow,
    plural,
    sort_runs,
    workflow_activity,
)
from ..dialogs.workflows import run_stamp
from ..theme.colors import COLORS, FONT_BOLD, FONT_SEMIBOLD
from ..theme.styles import ACCENT_STYLE, DANGER_ICON_STYLE, ICON_STYLE, INK_STYLE
from .empty_state import build_empty_state
from .factory import build_search_field
from .profile_card import ROW_HEIGHT, _data, _minor, _stack

# One grid per sheet, for its header and every row: (expand, fixed width).
RUN_COLUMNS = {
    "profile": (9, None),
    "workflow": (9, None),
    "progress": (12, None),
    "retries": (None, 140),
    "status": (None, 100),
    # Stop / Run again (124) + gap (8) + the log icon (40).
    "actions": (None, 172),
}
WORKFLOW_COLUMNS = {
    "workflow": (12, None),
    "recorded": (9, None),
    "steps": (None, 110),
    "last": (10, None),
    # Run (100) + gap (8) + edit and delete icons (2 x 40).
    "actions": (None, 188),
}

# Progress track ink: the run-state inks of the stamp.
_TRACK_INK = {
    "starting": COLORS["live"],
    "running": COLORS["live"],
    "succeeded": COLORS["success"],
    "failed": COLORS["error"],
    "stopped": COLORS["text_dim"],
}


@dataclass
class AutomationActions:
    on_run: Callable[[str], None]  # workflow -> the Run dialog
    on_edit: Callable[[str], None]  # workflow
    on_delete: Callable[[str], None]  # workflow
    on_stop: Callable[[str], None]  # profile
    # workflow, profile[, the whole chain when the run had several workflows]
    on_run_again: Callable[..., None]
    on_log: Callable[[str], None]  # profile
    on_record: Callable[[], None]


@dataclass
class AutomationData:
    workflows: list[dict]
    runs: list[dict]
    running: set[str] = field(default_factory=set)  # profiles with an open browser
    query: str = ""


class AutomationPage:
    def __init__(self, actions: AutomationActions, on_search: Callable[[str], None]) -> None:
        self.actions = actions
        self.subtitle = ft.Text("", size=13.5, color=COLORS["text_sub"])
        self.search_field = build_search_field(get_string("auto_search_hint"), on_search)
        self.body = ft.Column(spacing=0, expand=True, scroll=ft.ScrollMode.AUTO)
        self._key: str | None = None
        self.control = ft.Container(
            expand=True,
            bgcolor=COLORS["bg"],
            padding=ft.Padding.only(left=32, right=32, top=26, bottom=16),
            content=ft.Column(
                spacing=0,
                expand=True,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.END,
                        controls=[
                            ft.Column(
                                spacing=2,
                                controls=[
                                    ft.Text(
                                        get_string("auto_title"),
                                        size=26,
                                        font_family=FONT_BOLD,
                                        color=COLORS["text_main"],
                                    ),
                                    self.subtitle,
                                ],
                            ),
                            self.search_field,
                        ],
                    ),
                    ft.Container(height=18),
                    self.body,
                ],
            ),
        )

    def invalidate(self) -> None:
        self._key = None

    def render(self, data: AutomationData) -> bool:
        """Redraw if anything shown changed; True when it did."""
        browsers = sorted(data.running & {r["profile"] for r in data.runs})
        key = repr((data.workflows, data.runs, browsers, data.query, current_language()))
        if key == self._key:
            return False
        self._key = key
        self._set_subtitle(*counts(data.workflows, data.runs))
        self.body.controls = self._build_body(data)
        return True

    def _set_subtitle(self, w: int, a: int, f: int) -> None:
        """ "3 workflows · 1 running · 0 failed", running in violet and failed in red."""
        head = plural("auto_count_workflows", w) + " · "
        self.subtitle.value = None
        if not a and not f:
            self.subtitle.spans = [ft.TextSpan(head + get_string("auto_nothing_running"))]
            return
        self.subtitle.spans = [
            ft.TextSpan(head),
            ft.TextSpan(str(a), ft.TextStyle(color=COLORS["live"], font_family=FONT_SEMIBOLD)),
            ft.TextSpan(" " + get_string("auto_running_suffix") + " · "),
            ft.TextSpan(str(f), ft.TextStyle(color=COLORS["error"], font_family=FONT_SEMIBOLD)),
            ft.TextSpan(" " + get_string("auto_failed_suffix")),
        ]

    # --- body -----------------------------------------------------------------

    def _build_body(self, data: AutomationData) -> list[ft.Control]:
        q = data.query
        runs = sort_runs(r for r in data.runs if match_run(r, q))
        workflows = [w for w in data.workflows if match_workflow(w, q)]
        activity = workflow_activity(data.runs)
        controls: list[ft.Control] = []
        if runs:
            controls += [
                _section_title(get_string("auto_runs"), get_string("auto_runs_hint")),
                _sheet(
                    [
                        _header(
                            RUN_COLUMNS,
                            {
                                "profile": "col_profile",
                                "workflow": "auto_col_workflow",
                                "progress": "auto_col_progress",
                                "retries": "auto_col_retries",
                                "status": "col_status",
                            },
                        ),
                        *(_run_row(r, r["profile"] in data.running, self.actions) for r in runs),
                    ]
                ),
                ft.Container(height=26),
            ]
        controls.append(_section_title(get_string("auto_workflows")))
        if not data.workflows:
            sheet_rows: list[ft.Control] = [
                build_empty_state(
                    lambda _: self.actions.on_record(),
                    title=get_string("auto_empty_title"),
                    text=get_string("auto_empty_text"),
                    button=get_string("record_workflow"),
                    icon=ft.Icons.FIBER_MANUAL_RECORD_OUTLINED,
                )
            ]
        elif not workflows:
            sheet_rows = [
                ft.Container(
                    padding=ft.Padding.symmetric(vertical=40, horizontal=24),
                    alignment=ft.Alignment(0, 0),
                    content=ft.Text(
                        get_string("auto_no_results", query=q.strip()),
                        size=14,
                        color=COLORS["text_sub"],
                    ),
                )
            ]
        else:
            sheet_rows = [
                _header(
                    WORKFLOW_COLUMNS,
                    {
                        "workflow": "auto_col_workflow",
                        "recorded": "auto_col_recorded",
                        "steps": "auto_col_steps",
                        "last": "auto_col_last_run",
                    },
                ),
                *(_workflow_row(w, activity.get(w["name"]), self.actions) for w in workflows),
            ]
        controls.append(_sheet(sheet_rows))
        return controls


# --- building blocks ----------------------------------------------------------


def _cell(columns: dict, key: str, content: ft.Control | None) -> ft.Container:
    expand, width = columns[key]
    return ft.Container(content=content, expand=expand, width=width)


def _section_title(title: str, hint: str = "") -> ft.Container:
    lines: list[ft.Control] = [
        ft.Text(title, size=15, font_family=FONT_SEMIBOLD, color=COLORS["text_main"])
    ]
    if hint:
        lines.append(ft.Text(hint, size=12.5, color=COLORS["text_dim"]))
    return ft.Container(
        padding=ft.Padding.only(bottom=10),
        content=ft.Column(spacing=1, tight=True, controls=lines),
    )


def _sheet(rows: list[ft.Control]) -> ft.Container:
    return ft.Container(
        bgcolor=COLORS["card_bg"],
        border=ft.Border.all(1, COLORS["card_border"]),
        border_radius=10,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        content=ft.Column(spacing=0, tight=True, controls=rows),
    )


def _header(columns: dict, labels: dict[str, str]) -> ft.Container:
    return ft.Container(
        height=40,
        padding=ft.Padding.symmetric(horizontal=14),
        bgcolor=COLORS["bg"],
        border=ft.Border.only(bottom=ft.BorderSide(1, COLORS["card_border"])),
        content=ft.Row(
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                _cell(
                    columns,
                    key,
                    ft.Text(
                        get_string(labels[key]),
                        size=12,
                        font_family=FONT_SEMIBOLD,
                        color=COLORS["text_dim"],
                    )
                    if key in labels
                    else None,
                )
                for key in columns
            ],
        ),
    )


def _row(cells: list[ft.Control], bgcolor: str) -> ft.Container:
    return ft.Container(
        height=ROW_HEIGHT,
        padding=ft.Padding.symmetric(horizontal=14),
        bgcolor=bgcolor,
        border=ft.Border.only(bottom=ft.BorderSide(1, COLORS["card_border"])),
        content=ft.Row(spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=cells),
    )


def _strong(text: str) -> ft.Text:
    return ft.Text(
        text,
        size=14,
        font_family=FONT_SEMIBOLD,
        color=COLORS["text_main"],
        no_wrap=True,
        overflow=ft.TextOverflow.ELLIPSIS,
        tooltip=text,
    )


def _track(step: int, total: int, ink: str) -> ft.Container:
    """A thin flat progress track: done steps in the run-state ink, the rest in rule."""
    done = max(0, min(step, total))
    parts: list[ft.Control] = []
    if done:
        parts.append(ft.Container(expand=done, height=3, bgcolor=ink))
    if total - done:
        parts.append(ft.Container(expand=total - done, height=3))
    return ft.Container(
        expand=True,
        height=3,
        border_radius=2,
        bgcolor=COLORS["card_border"],
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        content=ft.Row(spacing=0, controls=parts),
    )


def _main_button(label: str, icon: ft.IconData, style: ft.ButtonStyle, on_click, width: int):
    return ft.Button(
        label, icon=icon, width=width, height=36, style=style, on_click=lambda _: on_click()
    )


def _icon(icon: ft.IconData, tooltip: str, on_click, style: ft.ButtonStyle = ICON_STYLE):
    return ft.IconButton(
        icon=icon,
        icon_size=19,
        icon_color=COLORS["text_sub"],
        tooltip=tooltip,
        style=style,
        on_click=lambda _: on_click(),
    )


def _run_row(run: dict, browser_open: bool, actions: AutomationActions) -> ft.Container:
    active, status = run["active"], run["status"]
    profile, workflow = run["profile"], run["workflow"]
    chain = run.get("workflows") or [workflow]
    when = (
        get_string("auto_started_at", time=hhmm(run["started_at"]))
        if active or not run["finished_at"]
        else get_string("auto_ended_at", time=hhmm(run["finished_at"]))
    )
    if status == "failed" and run["error"]:
        detail: ft.Control = ft.Text(
            run["error"],
            size=11.5,
            color=COLORS["error"],
            no_wrap=True,
            overflow=ft.TextOverflow.ELLIPSIS,
            tooltip=run["error"],
        )
    else:
        detail = _minor(run["step_label"] or "—")
    progress = _stack(
        ft.Row(
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                _data(get_string("auto_step", step=run["step"], total=run["step_total"])),
                _track(run["step"], run["step_total"], _TRACK_INK.get(status, COLORS["text_dim"])),
            ],
        ),
        detail,
    )
    main = (
        _main_button(
            get_string("stop"),
            ft.Icons.STOP_ROUNDED,
            INK_STYLE,
            lambda: actions.on_stop(profile),
            124,
        )
        if active
        else _main_button(
            get_string("auto_run_again"),
            ft.Icons.REPLAY_ROUNDED,
            ACCENT_STYLE,
            (lambda: actions.on_run_again(workflow, profile, chain))
            if len(chain) > 1
            else (lambda: actions.on_run_again(workflow, profile)),
            124,
        )
    )
    c = RUN_COLUMNS
    return _row(
        [
            _cell(
                c,
                "profile",
                _stack(
                    _strong(profile),
                    _minor(
                        get_string("auto_browser_open" if browser_open else "auto_browser_stopped")
                    ),
                ),
            ),
            _cell(
                c,
                "workflow",
                _stack(
                    ft.Text(
                        workflow,
                        size=13.5,
                        color=COLORS["text_main"],
                        no_wrap=True,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        tooltip=" → ".join(chain),
                    ),
                    _minor(
                        f"{get_string('run_chain_pos', index=run.get('workflow_index', 1), count=len(chain))} · {when}"
                        if len(chain) > 1
                        else when
                    ),
                ),
            ),
            _cell(c, "progress", progress),
            _cell(
                c,
                "retries",
                _stack(
                    _data(get_string("auto_attempt", count=run["attempt"])),
                    _minor(
                        get_string(
                            "auto_restarts", restarts=run["restarts"], max=run["max_restarts"]
                        ),
                        data=True,
                    ),
                ),
            ),
            # A Row lets the stamp keep its own width instead of filling the cell.
            _cell(c, "status", ft.Row(controls=[run_stamp(status)])),
            _cell(
                c,
                "actions",
                ft.Row(
                    spacing=0,
                    alignment=ft.MainAxisAlignment.END,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        main,
                        ft.Container(width=8),
                        _icon(
                            ft.Icons.RECEIPT_LONG_OUTLINED,
                            get_string("auto_run_log"),
                            lambda: actions.on_log(profile),
                        ),
                    ],
                ),
            ),
        ],
        COLORS["card_hover"] if active else COLORS["card_bg"],
    )


def _last_run(activity: dict | None) -> ft.Control:
    """Running now, else the most recently finished run, else not run yet."""
    if activity and activity["active"]:
        return _stack(
            ft.Row(controls=[run_stamp("running")]),
            _minor(get_string("auto_active_runs", count=activity["active"])),
        )
    last = activity and activity["last"]
    if last:
        return _stack(
            ft.Row(controls=[run_stamp(last["status"])]),
            _minor(f"{last['profile']} · {hhmm(last['finished_at'])}".rstrip(" ·")),
        )
    return _stack(
        ft.Text(get_string("auto_not_run"), size=13, color=COLORS["text_dim"]),
        _minor("—"),
    )


def _workflow_row(workflow: dict, activity: dict | None, actions: AutomationActions):
    name = workflow["name"]
    c = WORKFLOW_COLUMNS
    return _row(
        [
            _cell(
                c,
                "workflow",
                _stack(
                    _strong(name),
                    _minor(workflow["description"] or get_string("auto_no_description")),
                ),
            ),
            _cell(
                c,
                "recorded",
                _stack(
                    _data(workflow["profile"] or "—"),
                    _minor(get_string("auto_updated", date=ddmm_hhmm(workflow["updated_at"]))),
                ),
            ),
            _cell(
                c,
                "steps",
                _stack(
                    _data(plural("auto_steps", workflow["step_count"])),
                    _minor(get_string("auto_created", date=ddmm(workflow["created_at"]))),
                ),
            ),
            _cell(c, "last", _last_run(activity)),
            _cell(
                c,
                "actions",
                ft.Row(
                    spacing=0,
                    alignment=ft.MainAxisAlignment.END,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        _main_button(
                            get_string("wf_run"),
                            ft.Icons.PLAY_ARROW_ROUNDED,
                            ACCENT_STYLE,
                            lambda: actions.on_run(name),
                            100,
                        ),
                        ft.Container(width=8),
                        _icon(
                            ft.Icons.EDIT_OUTLINED,
                            get_string("tooltip_edit_workflow"),
                            lambda: actions.on_edit(name),
                        ),
                        _icon(
                            ft.Icons.DELETE_OUTLINE,
                            get_string("tooltip_delete_workflow"),
                            lambda: actions.on_delete(name),
                            DANGER_ICON_STYLE,
                        ),
                    ],
                ),
            ),
        ],
        COLORS["card_bg"],
    )
