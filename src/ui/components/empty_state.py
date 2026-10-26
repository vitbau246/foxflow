from collections.abc import Callable

import flet as ft

from ...core.strings import get_string
from ..theme.colors import COLORS, FONT_BOLD
from ..theme.styles import ACCENT_STYLE


def build_empty_state(
    on_create: Callable,
    title: str | None = None,
    text: str | None = None,
    button: str | None = None,
    icon: ft.IconData = ft.Icons.ADD,
) -> ft.Container:
    """Shown when no profiles exist (or, with its own copy, no workflows)."""
    return ft.Container(
        alignment=ft.Alignment(0, 0),
        padding=ft.Padding.symmetric(vertical=64, horizontal=24),
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=6,
            tight=True,
            controls=[
                ft.Text(
                    title or get_string("no_profiles_yet"),
                    size=18,
                    font_family=FONT_BOLD,
                    color=COLORS["text_main"],
                ),
                ft.Text(
                    text or get_string("create_profile_hint"),
                    size=14,
                    color=COLORS["text_sub"],
                    text_align=ft.TextAlign.CENTER,
                    width=420,
                ),
                ft.Container(height=12),
                ft.Button(
                    button or get_string("create_profile_btn"),
                    icon=icon,
                    height=40,
                    style=ACCENT_STYLE,
                    on_click=on_create,
                ),
            ],
        ),
    )
