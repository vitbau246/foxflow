"""One profile's current or last run: state, progress, error and log, live while it runs."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from typing import Any

import flet as ft

from ...core.strings import get_string
from ...services.workflow.runner import WorkflowRunner
from ..theme.colors import COLORS, FONT_BOLD, FONT_DATA
from ..theme.styles import INK_STYLE, OUTLINE_STYLE
from .workflows import POLL_SECONDS, log_block, run_stamp


def open_run_log(
    page: ft.Page,
    runner: WorkflowRunner,
    profile: str,
    on_stop: Callable[[str], None] | None = None,
) -> None:
    alive = True
    body = ft.Column(spacing=10, tight=True)
    key = {"run": ""}

    def stop(_: ft.ControlEvent) -> None:
        stop_btn.disabled = True
        if on_stop:
            on_stop(profile)
        else:
            runner.stop(profile)
        update()

    stop_btn = ft.Button(
        get_string("wf_stop_run"),
        icon=ft.Icons.STOP_ROUNDED,
        height=38,
        style=INK_STYLE,
        visible=False,
        on_click=stop,
    )

    def update() -> None:
        with contextlib.suppress(Exception):
            page.update()

    def draw(run: dict[str, Any] | None) -> None:
        k = repr(run)
        if k == key["run"]:
            return
        key["run"] = k
        stop_btn.visible = bool(run and run["active"])
        if not run:
            body.controls = [ft.Text(get_string("log_no_activity"), color=COLORS["text_sub"])]
            return
        lines: list[ft.Control] = [
            ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    run_stamp(run["status"]),
                    ft.Text(
                        run["workflow"],
                        size=12.5,
                        font_family=FONT_DATA,
                        color=COLORS["text_main"],
                    ),
                ],
            ),
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
            ),
        ]
        if run["error"]:
            lines.append(ft.Text(run["error"], size=13, color=COLORS["error"], selectable=True))
        lines.append(log_block(run["log"], height=320))
        body.controls = lines

    async def poll() -> None:
        while alive:
            try:
                run = await asyncio.to_thread(runner.get, profile)
            except Exception:  # never let a read error kill the dialog
                run = None
            draw(run)
            update()
            if not run or not run["active"]:
                return
            await asyncio.sleep(POLL_SECONDS)

    def close(_: ft.ControlEvent | None = None) -> None:
        nonlocal alive
        alive = False
        with contextlib.suppress(Exception):
            page.pop_dialog()

    draw(runner.get(profile))
    dlg = ft.AlertDialog(
        modal=True,
        bgcolor=COLORS["card_bg"],
        shape=ft.RoundedRectangleBorder(radius=12),
        title_padding=ft.Padding.only(left=24, right=24, top=22, bottom=0),
        content_padding=ft.Padding.only(left=24, right=24, top=10, bottom=8),
        actions_padding=ft.Padding.only(left=24, right=24, top=8, bottom=20),
        title=ft.Text(
            get_string("runlog_title", name=profile),
            size=19,
            font_family=FONT_BOLD,
            color=COLORS["text_main"],
        ),
        content=ft.Container(width=740, content=body),
        actions=[
            stop_btn,
            ft.OutlinedButton(get_string("close_btn"), style=OUTLINE_STYLE, on_click=close),
        ],
    )
    page.show_dialog(dlg)
    page.run_task(poll)
