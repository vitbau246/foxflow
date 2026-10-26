"""Run a workflow, or several one after the other, in several profiles at once.

Opened from a workflow row (it comes first) or from the Profiles bulk bar (the
first workflow is picked). More workflows can be added: each profile runs them
in order in one browser. Profiles that are recording or already running a
workflow cannot be picked; stopped ones are launched by the runner.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable, Iterable

import flet as ft

from ...core.strings import get_string
from ..automation_model import initial_selection, plural, run_blocker
from ..theme.colors import COLORS, FONT_BOLD, FONT_DATA, FONT_SEMIBOLD
from ..theme.styles import ACCENT_STYLE, DLG_FIELD_KWARGS, OUTLINE_STYLE
from .ai_settings import ai_setup_needed
from .workflows import WorkflowServices

_LINE_HEIGHT = 40


def open_run_dialog(
    page: ft.Page,
    services: WorkflowServices,
    profiles: list[str],
    running: set[str],
    recording: set[str],
    workflow: str | None = None,
    preselect: Iterable[str] = (),
    on_started: Callable[[], None] | None = None,
) -> None:
    store, runner = services.store, services.runner
    workflows = store.list()
    runs_by_profile = {r["profile"]: r for r in runner.list(log=False)}
    blocked = {p: b for p in profiles if (b := run_blocker(p, recording, runs_by_profile))}
    first = workflow or (workflows[0]["name"] if workflows else None)
    # The workflows to run, in order.
    chain: list[str] = [first] if first else []
    owner = next((w["profile"] for w in workflows if w["name"] == first), "")
    selected = initial_selection(profiles, preselect, owner, set(blocked))
    var_fields: dict[str, ft.TextField] = {}
    boxes: dict[str, ft.Checkbox] = {}

    error_text = ft.Text("", size=12.5, color=COLORS["error"], visible=False, selectable=True)
    vars_box = ft.Column(spacing=8, tight=True, visible=False)
    chain_box = ft.Column(spacing=6, tight=True)
    run_btn = ft.Button(height=38, style=ACCENT_STYLE, icon=ft.Icons.PLAY_ARROW_ROUNDED)

    def update() -> None:
        with contextlib.suppress(Exception):
            page.update()

    def sync_button() -> None:
        run_btn.content = plural("run_in_profiles", len(selected))
        run_btn.disabled = not selected or not chain

    def draw_vars() -> None:
        var_fields.clear()
        # Every variable of the chain, with the first workflow's value for a shared one.
        variables: dict[str, str] = {}
        for name in chain:
            found = store.get(name)
            for key, value in (found.variables if found else {}).items():
                variables.setdefault(key, value)
        vars_box.visible = bool(variables)
        if not variables:
            vars_box.controls = []
            return
        rows: list[ft.Control] = []
        for name, value in variables.items():
            # A list on several lines (for Repeat for) keeps its lines.
            lines = "\n" in value
            field = var_fields[name] = ft.TextField(
                value=value,
                expand=True,
                height=None if lines else 44,
                multiline=lines,
                max_lines=5 if lines else None,
                text_size=13.5,
                **DLG_FIELD_KWARGS,
            )
            rows.append(
                ft.Row(
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text(
                            name,
                            width=130,
                            size=12.5,
                            font_family=FONT_DATA,
                            color=COLORS["text_main"],
                            no_wrap=True,
                            overflow=ft.TextOverflow.ELLIPSIS,
                            tooltip=name,
                        ),
                        field,
                    ],
                )
            )
        vars_box.controls = [
            _label(get_string("run_vars")),
            ft.Text(get_string("run_vars_hint"), size=12, color=COLORS["text_dim"]),
            *rows,
        ]

    def toggle(name: str, on: bool) -> None:
        if on:
            selected.add(name)
        else:
            selected.discard(name)
        sync_button()
        update()

    def select_all(on: bool) -> None:
        selected.clear()
        if on:
            selected.update(p for p in profiles if p not in blocked)
        for name, box in boxes.items():
            box.value = name in selected
        sync_button()
        update()

    def line(name: str) -> ft.Container:
        reason = blocked.get(name)
        if reason:
            key, args = reason
            state = get_string(key, **args)
        else:
            state = get_string("auto_browser_open" if name in running else "auto_browser_stopped")
        box = boxes[name] = ft.Checkbox(
            value=name in selected,
            disabled=bool(reason),
            on_change=lambda e, n=name: toggle(n, bool(e.control.value)),
        )
        return ft.Container(
            height=_LINE_HEIGHT,
            padding=ft.Padding.only(left=4, right=12),
            border=ft.Border.only(bottom=ft.BorderSide(1, COLORS["card_border"])),
            content=ft.Row(
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    box,
                    ft.Text(
                        name,
                        expand=True,
                        size=14,
                        font_family=FONT_SEMIBOLD,
                        color=COLORS["text_dim"] if reason else COLORS["text_main"],
                        no_wrap=True,
                        overflow=ft.TextOverflow.ELLIPSIS,
                        tooltip=name,
                    ),
                    ft.Text(
                        state,
                        size=12,
                        color=COLORS["text_dim"],
                        no_wrap=True,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                ],
            ),
        )

    def chain_changed() -> None:
        draw_chain()
        draw_vars()
        sync_button()
        update()

    def pick(i: int, name: str | None) -> None:
        if name:
            chain[i] = name
            chain_changed()

    def drop(i: int) -> None:
        del chain[i]
        chain_changed()

    def add_workflow(_: ft.ControlEvent) -> None:
        unused = [w["name"] for w in workflows if w["name"] not in chain]
        chain.append(unused[0] if unused else chain[-1])
        chain_changed()

    def draw_chain() -> None:
        rows: list[ft.Control] = []
        for i, name in enumerate(chain):
            rows.append(
                ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text(
                            f"{i + 1}.",
                            width=22,
                            size=12.5,
                            font_family=FONT_DATA,
                            color=COLORS["text_dim"],
                        ),
                        ft.Dropdown(
                            value=name,
                            text_size=13.5,
                            expand=True,
                            bgcolor=COLORS["input_bg"],
                            border_color=COLORS["rule_strong"],
                            focused_border_color=COLORS["sidebar"],
                            border_radius=8,
                            on_select=lambda e, i=i: pick(i, e.control.value),
                            options=[ft.dropdown.Option(w["name"]) for w in workflows],
                        ),
                        ft.IconButton(
                            icon=ft.Icons.CLOSE,
                            icon_size=18,
                            icon_color=COLORS["text_sub"],
                            tooltip=get_string("run_remove_workflow"),
                            disabled=len(chain) == 1,
                            on_click=lambda _, i=i: drop(i),
                        ),
                    ],
                )
            )
        chain_box.controls = [
            *rows,
            ft.Row(
                controls=[
                    ft.TextButton(
                        get_string("run_add_workflow"),
                        icon=ft.Icons.ADD,
                        style=ft.ButtonStyle(color=COLORS["text_sub"]),
                        on_click=add_workflow,
                    )
                ]
            ),
            *(
                [ft.Text(get_string("run_chain_note"), size=12, color=COLORS["text_dim"])]
                if len(chain) > 1
                else []
            ),
        ]

    async def run(_: ft.ControlEvent) -> None:
        order, names = list(chain), sorted(selected)
        if not order or not names:
            return
        # Stays open: Run works again once AI is saved.
        for name in dict.fromkeys(order):
            if message := ai_setup_needed(page, services.ai, store, name, services.log):
                error_text.value = message
                error_text.visible = True
                update()
                return
        name = " → ".join(order)
        values = {k: f.value or "" for k, f in var_fields.items()}
        run_btn.disabled = True
        error_text.visible = False
        update()

        def start_all() -> tuple[list[str], list[tuple[str, str]]]:
            started, failed = [], []
            for profile in names:
                try:
                    if len(order) == 1:
                        runner.start(order[0], profile, values)
                    else:
                        runner.start_chain(order, profile, values)
                    started.append(profile)
                except Exception as e:  # WorkflowError, or the browser went away
                    failed.append((profile, str(e)))
            return started, failed

        started, failed = await asyncio.to_thread(start_all)
        if started:
            services.log(plural("run_started", len(started), workflow=name))
        for profile, error in failed:
            services.log(get_string("wf_run_failed", workflow=name, name=profile, error=error))
        if started:
            close()
            if on_started:
                on_started()
            return
        error_text.value = "\n".join(f"{p}: {err}" for p, err in failed)
        error_text.visible = True
        sync_button()
        update()

    def close(_: ft.ControlEvent | None = None) -> None:
        with contextlib.suppress(Exception):
            page.pop_dialog()

    run_btn.on_click = run

    draw_chain()
    picker: list[ft.Control] = [
        _label(get_string("run_workflow_label")),
        chain_box
        if workflows
        else ft.Text(get_string("run_no_workflows"), size=13, color=COLORS["text_sub"]),
        ft.Container(height=4),
    ]

    checklist = ft.Container(
        bgcolor=COLORS["card_bg"],
        border=ft.Border.all(1, COLORS["card_border"]),
        border_radius=9,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        content=ft.Column(
            spacing=0,
            scroll=ft.ScrollMode.AUTO,
            height=min(300, max(1, len(profiles)) * (_LINE_HEIGHT + 1)),
            controls=[line(p) for p in profiles],
        ),
    )
    quiet = ft.ButtonStyle(color=COLORS["text_sub"])
    draw_vars()
    sync_button()
    dlg = ft.AlertDialog(
        modal=True,
        bgcolor=COLORS["card_bg"],
        shape=ft.RoundedRectangleBorder(radius=12),
        title_padding=ft.Padding.only(left=24, right=24, top=22, bottom=0),
        content_padding=ft.Padding.only(left=24, right=24, top=10, bottom=8),
        actions_padding=ft.Padding.only(left=24, right=24, top=8, bottom=20),
        title=ft.Column(
            spacing=4,
            tight=True,
            controls=[
                ft.Text(
                    get_string("run_title"),
                    size=19,
                    font_family=FONT_BOLD,
                    color=COLORS["text_main"],
                ),
                ft.Text(
                    get_string("run_subtitle_fixed", workflow=workflow)
                    if workflow
                    else get_string("run_subtitle_pick"),
                    size=13.5,
                    color=COLORS["text_sub"],
                ),
            ],
        ),
        content=ft.Container(
            width=500,
            content=ft.Column(
                tight=True,
                spacing=8,
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    *picker,
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            _label(get_string("run_profiles_label")),
                            ft.Row(
                                spacing=0,
                                controls=[
                                    ft.TextButton(
                                        get_string("select_all"),
                                        style=quiet,
                                        on_click=lambda _: select_all(True),
                                    ),
                                    ft.TextButton(
                                        get_string("run_select_none"),
                                        style=quiet,
                                        on_click=lambda _: select_all(False),
                                    ),
                                ],
                            ),
                        ],
                    ),
                    checklist,
                    ft.Container(height=4),
                    vars_box,
                    ft.Container(
                        padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                        border_radius=8,
                        bgcolor=COLORS["paper_sunk"],
                        content=ft.Text(get_string("run_note"), size=13, color=COLORS["text_sub"]),
                    ),
                    error_text,
                ],
            ),
        ),
        actions=[
            ft.OutlinedButton(get_string("cancel"), style=OUTLINE_STYLE, on_click=close),
            run_btn,
        ],
    )
    page.show_dialog(dlg)


def _label(text: str) -> ft.Text:
    return ft.Text(text, size=12.5, font_family=FONT_SEMIBOLD, color=COLORS["text_sub"])
