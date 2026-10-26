"""Workflows of one profile: record in its browser, follow a run, run / edit / delete.

The same dialog as the web panel's; services are called directly (in threads,
since recording calls go to the browser process).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import flet as ft

from ...core.strings import get_string
from ...interfaces.protocols import IBrowserLauncher
from ...services.ai.settings import AISettingsStore
from ...services.workflow import recording
from ...services.workflow.model import ACTIONS
from ...services.workflow.runner import WorkflowRunner
from ...services.workflow.store import WorkflowError, WorkflowStore
from ..theme.colors import COLORS, FONT_BOLD, FONT_DATA, FONT_SEMIBOLD
from ..theme.styles import ACCENT_STYLE, DLG_FIELD_KWARGS, ICON_STYLE, INK_STYLE, OUTLINE_STYLE
from .ai_settings import ai_setup_needed
from .confirm import open_confirm_dialog

POLL_SECONDS = 1.5

# Run states read by form as well as ink, like the profile stamps.
_RUN_INK = {
    "starting": COLORS["text_sub"],
    "running": COLORS["live"],
    "succeeded": COLORS["success"],
    "failed": COLORS["error"],
    "stopped": COLORS["text_dim"],
}


@dataclass
class WorkflowServices:
    bl: IBrowserLauncher
    store: WorkflowStore
    runner: WorkflowRunner
    log: Callable[[str], None]
    ai: AISettingsStore | None = None


def run_stamp(status: str) -> ft.Container:
    ink = _RUN_INK.get(status, COLORS["text_sub"])
    text = ft.Text(
        get_string(f"wf_state_{status}").upper(),
        size=10.5,
        font_family=FONT_DATA,
        weight=ft.FontWeight.W_700,
        color=ink,
        style=ft.TextStyle(decoration=ft.TextDecoration.LINE_THROUGH)
        if status == "failed"
        else None,
    )
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=7, vertical=2),
        border_radius=5,
        border=ft.Border.all(1.5 if status in ("running", "succeeded", "failed") else 1, ink),
        content=text,
    )


def log_block(lines: list[str], height: float = 170) -> ft.Container:
    """A run's log as a code block on cover-deep, kept scrolled to the end."""
    return ft.Container(
        bgcolor=COLORS["cover_deep"],
        border_radius=8,
        padding=12,
        content=ft.ListView(
            height=height,
            spacing=0,
            auto_scroll=True,
            controls=[
                ft.Text(line, size=12, font_family=FONT_DATA, color="#DDE8E3", selectable=True)
                for line in lines
            ],
        ),
    )


def _panel(*controls: ft.Control, visible: bool = True) -> ft.Container:
    return ft.Container(
        visible=visible,
        padding=14,
        border_radius=9,
        bgcolor=COLORS["bg"],
        border=ft.Border.all(1, COLORS["card_border"]),
        content=ft.Column(spacing=8, tight=True, controls=list(controls)),
    )


def _heading(text: str, *extra: ft.Control) -> ft.Row:
    return ft.Row(
        spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Text(text, size=14, font_family=FONT_SEMIBOLD, color=COLORS["text_main"]),
            *extra,
        ],
    )


def recent_line(line: str) -> str:
    """ "click Log in" from the recorder, with the action in the UI language."""
    action, _, rest = line.partition(" ")
    if action not in ACTIONS:
        return line
    return f"{get_string(f'wf_act_{action}')} {rest}".strip()


def _hint(text: str) -> ft.Text:
    return ft.Text(text, size=13, color=COLORS["text_sub"])


def open_workflows_dialog(
    page: ft.Page,
    profile: str,
    services: WorkflowServices,
    on_close: Callable[[], None] | None = None,
    launch: Callable[[str], None] | None = None,
    is_loading: Callable[[str], bool] | None = None,
    auto_record: bool = False,
) -> None:
    """`launch`/`is_loading`: the app's Launch action and its starting state.

    With `auto_record` a stopped profile is launched and recording starts as soon
    as its browser is ready.
    """
    from .workflow_editor import open_workflow_editor

    bl, store, runner = services.bl, services.store, services.runner
    alive = True
    error_text = ft.Text("", size=12.5, color=COLORS["error"], visible=False)
    name_field = ft.TextField(
        hint_text=get_string("wf_name"), expand=True, height=44, text_size=14, **DLG_FIELD_KWARGS
    )
    rec_box = _panel()
    run_box = _panel(visible=False)
    list_box = ft.Column(spacing=6, tight=True)
    state: dict[str, Any] = {
        "rec": None,
        "run": None,
        "on": bl.is_running(profile),
        "list": [],
        # Other profiles' workflows run here too, but are listed only on request.
        "all": False,
        "launching": False,
        # Start recording once the browser is up (Record workflow picked this profile).
        "pending": auto_record,
    }
    keys = {"rec": "", "run": "", "list": ""}

    def show_error(message: str = "") -> None:
        error_text.value = message
        error_text.visible = bool(message)

    def update() -> None:
        with contextlib.suppress(Exception):
            page.update()

    async def act(fn: Callable[[], Any], button: ft.Control | None = None) -> Any:
        """Run a blocking service call off the UI thread; errors show in the dialog."""
        if button is not None:
            button.disabled = True
            update()
        show_error()
        try:
            return await asyncio.to_thread(fn)
        except WorkflowError as e:
            show_error(str(e))
        finally:
            if button is not None:
                button.disabled = False
            await refresh_state()

    # --- recording ------------------------------------------------------------

    async def start_recording(e: ft.ControlEvent) -> None:
        if await act(lambda: recording.start(bl, runner, profile), e.control):
            services.log(get_string("wf_record_started", name=profile))

    async def save_recording(e: ft.ControlEvent) -> None:
        name = (name_field.value or "").strip()
        if not name:
            show_error(get_string("wf_need_name"))
            update()
            return
        result = await act(lambda: recording.stop(bl, store, profile, save_as=name), e.control)
        if result and result.get("workflow"):
            name_field.value = ""
            services.log(get_string("wf_saved", name=result["workflow"]["name"]))
            await load_list()

    def discard_recording(_: ft.ControlEvent) -> None:
        count = (state["rec"] or {}).get("step_count", 0)

        def confirmed() -> None:
            page.run_task(act, lambda: recording.stop(bl, store, profile, discard=True))

        open_confirm_dialog(
            page,
            profile,
            confirmed,
            title=get_string("wf_confirm_discard", count=count),
            body="",
            action_label=get_string("wf_discard"),
        )

    def do_launch(_: ft.ControlEvent | None = None) -> None:
        if launch and not bl.is_running(profile):
            launch(profile)
            page.run_task(refresh_state)

    def draw_rec() -> None:
        rec, on, run = state["rec"], state["on"], state["run"]
        key = repr((on, rec, run and run["active"], state["launching"], state["pending"]))
        if key == keys["rec"]:
            return
        keys["rec"] = key
        controls: list[ft.Control]
        if rec and (rec["recording"] or rec["draft"]):
            recent = ft.Column(
                spacing=2,
                tight=True,
                controls=[
                    ft.Text(
                        f"› {recent_line(line)}",
                        size=12.5,
                        color=COLORS["text_sub"],
                        no_wrap=True,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    )
                    for line in rec.get("recent", [])
                ],
            )
            title = (
                get_string("wf_recording", count=rec["step_count"])
                if rec["recording"]
                else get_string("wf_draft", count=rec["step_count"])
            )
            dot = ft.Container(width=8, height=8, border_radius=4, bgcolor=COLORS["live"])
            controls = [
                _heading(title, *([dot] if rec["recording"] else [])),
                *([] if rec["recording"] else [_hint(get_string("wf_draft_hint"))]),
                recent,
                ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        name_field,
                        ft.Button(
                            get_string("wf_stop_save" if rec["recording"] else "wf_save_draft"),
                            height=40,
                            style=ACCENT_STYLE,
                            on_click=save_recording,
                        ),
                        ft.TextButton(
                            get_string("wf_discard"),
                            style=ft.ButtonStyle(color=COLORS["text_sub"]),
                            on_click=discard_recording,
                        ),
                    ],
                ),
            ]
        elif on:
            controls = [
                _heading(get_string("wf_record")),
                _hint(get_string("wf_record_hint")),
                ft.Row(
                    controls=[
                        ft.Button(
                            get_string("wf_record_start"),
                            icon=ft.Icons.FIBER_MANUAL_RECORD_OUTLINED,
                            height=38,
                            style=ACCENT_STYLE,
                            disabled=bool(run and run["active"]),
                            on_click=start_recording,
                        )
                    ]
                ),
            ]
        elif state["launching"]:
            controls = [
                _heading(get_string("wf_record")),
                _hint(
                    get_string(
                        "wf_record_launching_auto" if state["pending"] else "wf_record_launching",
                        name=profile,
                    )
                ),
            ]
        else:
            controls = [
                _heading(get_string("wf_record")),
                _hint(get_string("wf_record_need_launch")),
            ]
            if launch:
                controls.append(
                    ft.Row(
                        controls=[
                            ft.Button(
                                get_string("launch"),
                                icon=ft.Icons.PLAY_ARROW_ROUNDED,
                                height=38,
                                style=ACCENT_STYLE,
                                on_click=do_launch,
                            )
                        ]
                    )
                )
        rec_box.content.controls = controls

    # --- run --------------------------------------------------------------------

    async def stop_run(e: ft.ControlEvent) -> None:
        await act(lambda: runner.stop(profile), e.control)

    def draw_run() -> None:
        run = state["run"]
        run_box.visible = bool(run)
        if not run:
            return
        key = repr(run)
        if key == keys["run"]:
            return
        keys["run"] = key
        lines: list[ft.Control] = [
            _heading(
                get_string("wf_last_run"),
                run_stamp(run["status"]),
                ft.Text(
                    run["workflow"], size=12.5, font_family=FONT_DATA, color=COLORS["text_main"]
                ),
            )
        ]
        if run["step"]:
            lines.append(
                ft.Text(
                    get_string(
                        "wf_progress",
                        step=run["step"],
                        total=run["step_total"],
                        attempt=run["attempt"],
                        restarts=run["restarts"],
                        max=run["max_restarts"],
                    )
                    + (f" · {run['step_label']}" if run["step_label"] else ""),
                    size=13,
                    color=COLORS["text_sub"],
                )
            )
        if run["error"]:
            lines.append(ft.Text(run["error"], size=13, color=COLORS["error"], selectable=True))
        lines.append(log_block(run["log"][-60:]))
        if run["active"]:
            lines.append(
                ft.Row(
                    controls=[
                        ft.Button(
                            get_string("wf_stop_run"),
                            icon=ft.Icons.STOP_ROUNDED,
                            height=38,
                            style=INK_STYLE,
                            on_click=stop_run,
                        )
                    ]
                )
            )
        run_box.content.controls = lines

    # --- saved workflows --------------------------------------------------------

    async def run_workflow(e: ft.ControlEvent, name: str) -> None:
        if message := ai_setup_needed(page, services.ai, store, name, services.log):
            show_error(message)
            update()
            return
        if await act(lambda: runner.start(name, profile), e.control):
            services.log(get_string("wf_started", workflow=name, name=profile))

    def delete_workflow(name: str) -> None:
        def confirmed() -> None:
            store.delete(name)
            services.log(get_string("wf_deleted", name=name))
            page.run_task(load_list)

        open_confirm_dialog(
            page,
            name,
            confirmed,
            title=get_string("wf_confirm_delete", name=name),
        )

    def edit_workflow(name: str) -> None:
        open_workflow_editor(
            page,
            store,
            name,
            on_saved=lambda: page.run_task(load_list),
            ai_settings=services.ai,
        )

    def draw_list() -> None:
        blocked = bool(
            (state["run"] and state["run"]["active"])
            or (state["rec"] and state["rec"]["recording"])
        )
        key = repr((state["list"], blocked, state["all"]))
        if key == keys["list"]:
            return
        keys["list"] = key
        mine = [w for w in state["list"] if w["profile"].casefold() == profile.casefold()]
        others = len(state["list"]) - len(mine)
        shown = state["list"] if state["all"] else mine
        items: list[ft.Control] = []
        for w in shown:
            items.append(
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                    border=ft.Border.only(top=ft.BorderSide(1, COLORS["card_border"]))
                    if items
                    else None,
                    content=ft.Row(
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Column(
                                spacing=1,
                                expand=True,
                                tight=True,
                                controls=[
                                    ft.Text(
                                        w["name"],
                                        size=14,
                                        font_family=FONT_SEMIBOLD,
                                        color=COLORS["text_main"],
                                    ),
                                    ft.Text(
                                        w["description"]
                                        or get_string(
                                            "wf_meta",
                                            count=w["step_count"],
                                            profile=w["profile"] or "?",
                                        ),
                                        size=11.5,
                                        color=COLORS["text_dim"],
                                        no_wrap=True,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                ],
                            ),
                            ft.Button(
                                get_string("wf_run"),
                                icon=ft.Icons.PLAY_ARROW_ROUNDED,
                                height=36,
                                style=ACCENT_STYLE,
                                disabled=blocked,
                                on_click=lambda e, n=w["name"]: page.run_task(run_workflow, e, n),
                            ),
                            ft.IconButton(
                                icon=ft.Icons.EDIT_OUTLINED,
                                icon_size=19,
                                icon_color=COLORS["text_sub"],
                                tooltip=get_string("tooltip_edit_workflow"),
                                style=ICON_STYLE,
                                on_click=lambda _, n=w["name"]: edit_workflow(n),
                            ),
                            ft.IconButton(
                                icon=ft.Icons.DELETE_OUTLINE,
                                icon_size=19,
                                icon_color=COLORS["text_sub"],
                                tooltip=get_string("tooltip_delete_workflow"),
                                style=ICON_STYLE,
                                on_click=lambda _, n=w["name"]: delete_workflow(n),
                            ),
                        ],
                    ),
                )
            )
        list_box.controls = [
            ft.Text(
                get_string("wf_saved_list"),
                size=12.5,
                font_family=FONT_SEMIBOLD,
                color=COLORS["text_sub"],
            ),
            ft.Container(
                border_radius=9,
                bgcolor=COLORS["card_bg"],
                border=ft.Border.all(1, COLORS["card_border"]),
                # Five rows, then the list scrolls; the dialog keeps its height.
                content=ft.Column(
                    spacing=0,
                    tight=True,
                    scroll=ft.ScrollMode.AUTO if len(items) > 5 else None,
                    height=5 * 58 if len(items) > 5 else None,
                    controls=items,
                ),
            )
            if items
            else _hint(get_string("wf_none_here" if others else "wf_none")),
        ]
        if others:

            def toggle(_: ft.ControlEvent) -> None:
                state["all"] = not state["all"]
                draw_list()
                update()

            list_box.controls.append(
                ft.TextButton(
                    get_string("wf_hide_others")
                    if state["all"]
                    else get_string("wf_show_others", count=others),
                    style=ft.ButtonStyle(color=COLORS["text_sub"]),
                    on_click=toggle,
                )
            )

    # --- polling ----------------------------------------------------------------

    async def refresh_state() -> None:
        def read() -> dict[str, Any]:
            return {
                "rec": recording.status(bl, profile),
                "run": runner.get(profile),
                "on": bl.is_running(profile),
                "launching": bool(is_loading and is_loading(profile)),
            }

        try:
            state.update(await asyncio.to_thread(read))
        except Exception as e:  # the browser went away mid-call
            show_error(str(e))
        if state["pending"] and not state["launching"]:
            state["pending"] = False
            if not state["on"]:
                # The launch failed; the activity log has the reason.
                show_error(get_string("wf_record_launch_failed", name=profile))
            elif not (state["rec"] or {}).get("recording") and not (state["run"] or {}).get(
                "active"
            ):
                try:
                    await asyncio.to_thread(recording.start, bl, runner, profile)
                    services.log(get_string("wf_record_started", name=profile))
                    state["rec"] = await asyncio.to_thread(recording.status, bl, profile)
                except Exception as e:  # WorkflowError, or the browser went away
                    show_error(str(e))
        draw_rec()
        draw_run()
        draw_list()
        update()

    async def load_list() -> None:
        state["list"] = await asyncio.to_thread(store.list)
        keys["list"] = ""
        draw_list()
        update()

    async def poll() -> None:
        while alive:
            await refresh_state()
            await asyncio.sleep(POLL_SECONDS)

    def close(_: ft.ControlEvent | None = None) -> None:
        nonlocal alive
        alive = False
        with contextlib.suppress(Exception):
            page.pop_dialog()
        if on_close:
            on_close()

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
                    get_string("wf_title", name=profile),
                    size=19,
                    font_family=FONT_BOLD,
                    color=COLORS["text_main"],
                ),
                ft.Text(get_string("wf_subtitle"), size=13.5, color=COLORS["text_sub"]),
            ],
        ),
        content=ft.Container(
            width=640,
            content=ft.Column(
                tight=True,
                spacing=12,
                controls=[rec_box, run_box, error_text, list_box],
            ),
        ),
        actions=[
            ft.OutlinedButton(get_string("close_btn"), style=OUTLINE_STYLE, on_click=close),
        ],
    )
    if auto_record and not state["on"]:
        do_launch()
        state["launching"] = bool(is_loading and is_loading(profile))
    draw_rec()
    draw_list()
    page.show_dialog(dlg)
    page.run_task(load_list)
    page.run_task(poll)
