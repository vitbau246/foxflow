"""Pick the profile to record a workflow in; its workflows dialog does the recording."""

from __future__ import annotations

import contextlib
from collections.abc import Callable

import flet as ft

from ...core.strings import get_string
from ..automation_model import recording_order
from ..theme.colors import COLORS, FONT_BOLD, FONT_SEMIBOLD
from ..theme.styles import ACCENT_STYLE, OUTLINE_STYLE


def open_record_dialog(
    page: ft.Page,
    profiles: list[str],
    running: set[str],
    on_pick: Callable[[str], None],
    on_new_profile: Callable[[], None] | None = None,
    note: str = "",
) -> None:
    """`on_new_profile`: offered when there is no profile to record in yet."""

    def pick(name: str) -> None:
        with contextlib.suppress(Exception):
            page.pop_dialog()
        on_pick(name)

    def new_profile(_: ft.ControlEvent) -> None:
        with contextlib.suppress(Exception):
            page.pop_dialog()
        assert on_new_profile is not None
        on_new_profile()

    items: list[ft.Control] = []
    for name in recording_order(profiles, running):
        on = name in running
        items.append(
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                border=ft.Border.only(top=ft.BorderSide(1, COLORS["card_border"]))
                if items
                else None,
                ink=True,
                on_click=lambda _, n=name: pick(n),
                content=ft.Row(
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Column(
                            spacing=1,
                            expand=True,
                            tight=True,
                            controls=[
                                ft.Text(
                                    name,
                                    size=14,
                                    font_family=FONT_SEMIBOLD,
                                    color=COLORS["text_main"],
                                    no_wrap=True,
                                    overflow=ft.TextOverflow.ELLIPSIS,
                                ),
                                ft.Text(
                                    get_string(
                                        "auto_browser_open" if on else "auto_browser_stopped"
                                    ),
                                    size=11.5,
                                    color=COLORS["live"] if on else COLORS["text_dim"],
                                ),
                            ],
                        ),
                        ft.Icon(ft.Icons.CHEVRON_RIGHT, size=18, color=COLORS["text_dim"]),
                    ],
                ),
            )
        )

    body: ft.Control = (
        ft.Container(
            border_radius=9,
            bgcolor=COLORS["card_bg"],
            border=ft.Border.all(1, COLORS["card_border"]),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            content=ft.Column(
                spacing=0,
                tight=True,
                scroll=ft.ScrollMode.AUTO if len(items) > 6 else None,
                height=6 * 56 if len(items) > 6 else None,
                controls=items,
            ),
        )
        if items
        else ft.Column(
            spacing=12,
            tight=True,
            controls=[
                ft.Text(get_string("rec_no_profiles"), size=13, color=COLORS["text_sub"]),
                *(
                    [
                        ft.Row(
                            controls=[
                                ft.Button(
                                    get_string("new_profile"),
                                    icon=ft.Icons.ADD,
                                    height=38,
                                    style=ACCENT_STYLE,
                                    on_click=new_profile,
                                )
                            ]
                        )
                    ]
                    if on_new_profile
                    else []
                ),
            ],
        )
    )
    if note:
        body = ft.Column(
            spacing=10,
            tight=True,
            controls=[ft.Text(note, size=13, color=COLORS["text_sub"]), body],
        )
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
                    get_string("rec_title"),
                    size=19,
                    font_family=FONT_BOLD,
                    color=COLORS["text_main"],
                ),
                ft.Text(get_string("rec_subtitle"), size=13.5, color=COLORS["text_sub"]),
            ],
        ),
        content=ft.Container(width=420, content=body),
        actions=[
            ft.OutlinedButton(
                get_string("cancel"), style=OUTLINE_STYLE, on_click=lambda _: page.pop_dialog()
            ),
        ],
    )
    page.show_dialog(dlg)
