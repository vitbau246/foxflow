from collections.abc import Callable

import flet as ft

from ...core.strings import get_string
from ..theme.colors import COLORS
from ..theme.styles import ERROR_STYLE, INK_STYLE


def open_confirm_dialog(
    page: ft.Page,
    profile_name: str,
    on_confirm: Callable[[], None],
    *,
    title: str | None = None,
    body: str | None = None,
    action_label: str | None = None,
    action_icon: ft.IconData = ft.Icons.DELETE,
    ink: bool = False,
) -> None:
    """A yes/no dialog; the confirm is red (destructive) or, with `ink`, an ink Stop."""

    def _on_confirm(_: ft.ControlEvent) -> None:
        # Closed first: on_confirm may open the next dialog.
        page.pop_dialog()
        on_confirm()

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text(
            title if title is not None else get_string("confirm_delete_msg", name=profile_name),
            size=18,
            weight=ft.FontWeight.BOLD,
        ),
        content=ft.Text(
            body if body is not None else get_string("cannot_undo"),
            size=13,
            color=COLORS["text_dim"],
        ),
        actions=[
            ft.TextButton(get_string("cancel"), on_click=lambda _: page.pop_dialog()),
            ft.Button(
                action_label if action_label is not None else get_string("delete"),
                icon=action_icon,
                style=INK_STYLE if ink else ERROR_STYLE,
                on_click=_on_confirm,
            ),
        ],
    )
    page.show_dialog(dlg)
