from collections.abc import Callable

import flet as ft

from ...core.strings import get_string
from ...services.profile.clone_parts import PARTS
from ...services.profile.cloning import WORKFLOWS
from ...services.profile.manager import MAX_CLONES
from ..theme.colors import COLORS, FONT_BOLD, FONT_SEMIBOLD
from ..theme.styles import ACCENT_STYLE, DLG_FIELD_KWARGS


def open_clone_dialog(
    page: ft.Page,
    profile_name: str,
    suggested: str,
    is_running: bool,
    names_for: Callable[[str, int], list[str]],
    on_clone: Callable[[str, int, set[str]], str | None],
    workflow_count: int = 0,
) -> None:
    """Ask for the copies' name and count, and what to copy besides the settings.

    `names_for(base, count)` previews the names; `on_clone(base, count, parts)` gets
    the ticked parts (clone_parts.PARTS and "workflows") and returns an error to
    show, or None when done.
    """
    edited = False
    name_field = ft.TextField(value=suggested, autofocus=True, expand=True, **DLG_FIELD_KWARGS)
    count_field = ft.TextField(
        value="1",
        width=110,
        keyboard_type=ft.KeyboardType.NUMBER,
        input_filter=ft.NumbersOnlyInputFilter(),
        **DLG_FIELD_KWARGS,
    )
    name_label = ft.Text(
        get_string("clone_new_name"), size=12.5, font_family=FONT_SEMIBOLD, color=COLORS["text_sub"]
    )
    preview = ft.Text("", size=12, color=COLORS["text_dim"], visible=False)

    def count() -> int:
        try:
            return int(count_field.value or 1)
        except ValueError:
            return 1

    def base() -> str:
        # Several copies without a name of one's own are numbered from "<name>-copy".
        if edited or count() <= 1:
            return (name_field.value or "").strip()
        return f"{profile_name[:56]}-copy"

    def refresh_preview(_: ft.ControlEvent | None = None) -> None:
        n = count()
        name_label.value = get_string("clone_base_name" if n > 1 else "clone_new_name")
        if not edited:
            name_field.value = base() if n > 1 else suggested
        preview.visible = 1 < n <= MAX_CLONES
        if preview.visible:
            names = names_for(base() or "?", n)
            shown = ", ".join(names) if n <= 4 else f"{names[0]}, {names[1]}, \u2026 {names[-1]}"
            preview.value = get_string("clone_preview", names=shown)
        page.update()

    def on_name(_: ft.ControlEvent) -> None:
        nonlocal edited
        edited = True
        refresh_preview()

    name_field.on_change = on_name
    count_field.on_change = refresh_preview
    # Browser data needs the browser stopped: copying its open files gives a torn copy.
    boxes = {
        part: ft.Checkbox(label=get_string(f"clone_part_{part}"), value=False, disabled=is_running)
        for part in PARTS
    }
    boxes[WORKFLOWS] = ft.Checkbox(
        label=get_string("clone_part_workflows", count=workflow_count),
        value=False,
        disabled=not workflow_count,
    )
    error = ft.Text("", size=12, color=COLORS["error"], visible=False)

    def hint(key: str, **kw: object) -> ft.Container:
        return ft.Container(
            padding=ft.Padding.only(left=40),
            content=ft.Text(get_string(key, **kw), size=12, color=COLORS["text_dim"]),
        )

    def submit(_: ft.ControlEvent) -> None:
        if not 1 <= count() <= MAX_CLONES:
            error.value = get_string("clone_count_range", max=MAX_CLONES)
            error.visible = True
            page.update()
            return
        message = on_clone(base(), count(), {k for k, box in boxes.items() if box.value})
        if message:
            error.value = message
            error.visible = True
            page.update()
        else:
            page.pop_dialog()

    name_field.on_submit = submit
    dlg = ft.AlertDialog(
        modal=True,
        bgcolor=COLORS["card_bg"],
        shape=ft.RoundedRectangleBorder(radius=12),
        title_padding=ft.Padding.only(left=24, right=24, top=22, bottom=0),
        content_padding=ft.Padding.only(left=24, right=24, top=4, bottom=8),
        actions_padding=ft.Padding.only(left=24, right=24, top=8, bottom=20),
        title=ft.Column(
            spacing=4,
            tight=True,
            controls=[
                ft.Text(
                    get_string("clone_title"),
                    size=19,
                    font_family=FONT_BOLD,
                    color=COLORS["text_main"],
                ),
                ft.Text(
                    get_string("clone_subtitle", name=profile_name),
                    size=13.5,
                    color=COLORS["text_sub"],
                ),
            ],
        ),
        content=ft.Container(
            width=460,
            content=ft.Column(
                tight=True,
                spacing=8,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[
                    ft.Row(
                        spacing=12,
                        controls=[
                            ft.Container(
                                expand=True,
                                padding=ft.Padding.only(top=10),
                                content=name_label,
                            ),
                            ft.Container(
                                width=110,
                                padding=ft.Padding.only(top=10),
                                content=ft.Text(
                                    get_string("clone_count"),
                                    size=12.5,
                                    font_family=FONT_SEMIBOLD,
                                    color=COLORS["text_sub"],
                                ),
                            ),
                        ],
                    ),
                    ft.Row(spacing=12, controls=[name_field, count_field]),
                    preview,
                    ft.Container(
                        padding=ft.Padding.only(top=10),
                        content=ft.Text(
                            get_string("clone_copy_title"),
                            size=12.5,
                            font_family=FONT_SEMIBOLD,
                            color=COLORS["text_sub"],
                        ),
                    ),
                    *([hint("clone_copy_data_running")] if is_running else []),
                    boxes["cookies"],
                    hint("clone_copy_data_hint"),
                    boxes["history"],
                    boxes["site_data"],
                    boxes["passwords"],
                    boxes["tabs"],
                    boxes[WORKFLOWS],
                    hint("clone_workflows_hint"),
                    ft.Container(
                        padding=ft.Padding.symmetric(horizontal=12, vertical=10),
                        border_radius=8,
                        bgcolor=COLORS["paper_sunk"],
                        content=ft.Row(
                            spacing=8,
                            vertical_alignment=ft.CrossAxisAlignment.START,
                            controls=[
                                ft.Icon(ft.Icons.FINGERPRINT, size=16, color=COLORS["text_dim"]),
                                ft.Text(
                                    get_string("clone_new_fingerprint"),
                                    size=12.5,
                                    color=COLORS["text_sub"],
                                    expand=True,
                                ),
                            ],
                        ),
                    ),
                    error,
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
                get_string("clone_btn"),
                icon=ft.Icons.CONTENT_COPY_OUTLINED,
                style=ACCENT_STYLE,
                on_click=submit,
            ),
        ],
    )
    page.show_dialog(dlg)
