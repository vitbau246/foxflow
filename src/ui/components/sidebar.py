from collections.abc import Callable

import flet as ft

from ...core.strings import get_string
from ..theme.colors import COLORS, FONT_BOLD, FONT_DATA, FONT_MEDIUM, FONT_SEMIBOLD
from ..theme.styles import ACCENT_STYLE, RAIL_STYLE

# (filter id, string key) in display order; counts come from the app.
FILTERS = (
    ("all", "filter_all"),
    ("running", "filter_running"),
    ("proxy", "filter_proxy"),
    ("direct", "filter_direct"),
    ("chrome", "filter_chrome"),
)


# (view id, string key): what the main area shows.
VIEWS = (
    ("automation", "view_automation"),
    ("profiles", "view_profiles"),
)


def _nav_item(label: str, count: int, on: bool, on_click: Callable) -> ft.Container:
    """A rail nav item: label, count right-aligned in mono; the active one in cover ink."""
    return ft.Container(
        height=36,
        border_radius=7,
        padding=ft.Padding.symmetric(horizontal=10),
        bgcolor=COLORS["cover_ink"] if on else None,
        ink=True,
        on_click=on_click,
        content=ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text(
                    label,
                    size=13.5,
                    font_family=FONT_SEMIBOLD if on else FONT_MEDIUM,
                    color=COLORS["sidebar"] if on else COLORS["cover_ink"],
                ),
                ft.Text(
                    str(count),
                    size=12,
                    font_family=FONT_DATA,
                    color=COLORS["sidebar"] if on else COLORS["cover_muted"],
                ),
            ],
        ),
    )


def build_filter_buttons(
    active: str, counts: dict[str, int], on_filter: Callable[[str], None]
) -> list[ft.Control]:
    """The rail's filter list; the active filter is set in cover ink."""
    return [
        _nav_item(get_string(key), counts.get(fid, 0), fid == active, lambda _, f=fid: on_filter(f))
        for fid, key in FILTERS
    ]


def build_view_buttons(
    active: str, counts: dict[str, int], on_view: Callable[[str], None]
) -> list[ft.Control]:
    """Automation / Profiles: which page the main area shows."""
    return [
        _nav_item(get_string(key), counts.get(vid, 0), vid == active, lambda _, v=vid: on_view(v))
        for vid, key in VIEWS
    ]


def rail_section(title: str, items: ft.Control, visible: bool = True) -> ft.Column:
    """A titled group of nav items on the rail (with the 22px gap above it)."""
    return ft.Column(
        spacing=0,
        visible=visible,
        controls=[
            ft.Container(height=22),
            ft.Container(
                padding=ft.Padding.only(left=10, bottom=6),
                content=ft.Text(
                    title,
                    size=12,
                    font_family=FONT_SEMIBOLD,
                    color=COLORS["cover_muted"],
                ),
            ),
            items,
        ],
    )


def build_primary_button(on_click: Callable) -> ft.Button:
    """The rail's orange button; its label follows the view (see `primary_for`)."""
    return ft.Button(width=208, height=42, style=ACCENT_STYLE, on_click=on_click)


def primary_for(button: ft.Button, view: str) -> None:
    """New profile in the Profiles view, Record workflow in the Automation view."""
    if view == "profiles":
        button.content, button.icon = get_string("new_profile"), ft.Icons.ADD
    else:
        button.content = get_string("record_workflow")
        button.icon = ft.Icons.FIBER_MANUAL_RECORD_OUTLINED


def build_sidebar(
    stats_text: ft.Text,
    running_text: ft.Text,
    _log_text: ft.Text,
    log_column: ft.Container,
    log_toggle_btn: ft.TextButton,
    primary_button: ft.Control,
    on_import: Callable,
    on_export: Callable,
    on_toggle_log: Callable,
    on_mcp: Callable,
    on_fullscreen_log: Callable,
    sections: list[ft.Control] | None = None,
    language: str = "en",
    on_language: Callable[[str], None] | None = None,
) -> ft.Container:
    log_toggle_btn.on_click = on_toggle_log
    return ft.Container(
        width=240,
        bgcolor=COLORS["sidebar"],
        # The tile is rendered at 2x; scale 2 draws it at its authored size.
        image=ft.DecorationImage(src="rail-guilloche.png", repeat=ft.ImageRepeat.REPEAT, scale=2),
        padding=ft.Padding.only(left=16, right=16, top=22, bottom=16),
        content=ft.Column(
            spacing=0,
            expand=True,
            controls=[
                ft.Row(
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Image(src="logo.png", width=34, height=34),
                        ft.Column(
                            spacing=0,
                            controls=[
                                ft.Text(
                                    get_string("app_name"),
                                    size=18,
                                    font_family=FONT_BOLD,
                                    color=COLORS["cover_ink"],
                                ),
                                ft.Text(
                                    get_string("app_subtitle"),
                                    size=12,
                                    color=COLORS["cover_muted"],
                                ),
                            ],
                        ),
                    ],
                ),
                ft.Container(height=10),
                stats_text,
                ft.Container(height=2),
                running_text,
                ft.Container(height=10),
                primary_button,
                ft.Container(height=10),
                ft.Row(
                    spacing=8,
                    controls=[
                        ft.OutlinedButton(
                            get_string("import"),
                            icon=ft.Icons.FILE_DOWNLOAD_OUTLINED,
                            expand=True,
                            height=36,
                            style=RAIL_STYLE,
                            on_click=on_import,
                        ),
                        ft.OutlinedButton(
                            get_string("export"),
                            icon=ft.Icons.FILE_UPLOAD_OUTLINED,
                            expand=True,
                            height=36,
                            style=RAIL_STYLE,
                            on_click=on_export,
                        ),
                    ],
                ),
                # The nav takes the free height and scrolls in a short window.
                ft.Column(
                    spacing=0,
                    expand=True,
                    scroll=ft.ScrollMode.AUTO,
                    controls=list(sections or []),
                ),
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        log_toggle_btn,
                        ft.IconButton(
                            icon=ft.Icons.OPEN_IN_FULL,
                            icon_size=16,
                            icon_color=COLORS["cover_muted"],
                            tooltip=get_string("activity_log"),
                            on_click=on_fullscreen_log,
                        ),
                    ],
                ),
                log_column,
                ft.Container(height=8),
                ft.OutlinedButton(
                    get_string("mcp_button"),
                    icon=ft.Icons.SMART_TOY_OUTLINED,
                    width=208,
                    height=38,
                    style=RAIL_STYLE,
                    on_click=on_mcp,
                ),
                ft.Container(height=8),
                _language_switch(language, on_language),
            ],
        ),
    )


def _language_switch(active: str, on_language: Callable[[str], None] | None) -> ft.Container:
    """Segmented Tiếng Việt / English switch, as in the web panel."""

    def seg(code: str, label: str) -> ft.Container:
        on = code == active
        return ft.Container(
            expand=True,
            height=30,
            border_radius=6,
            alignment=ft.Alignment(0, 0),
            bgcolor=COLORS["sidebar"] if on else None,
            ink=not on,
            on_click=None if on or on_language is None else (lambda _, c=code: on_language(c)),
            content=ft.Text(
                label,
                size=13,
                font_family=FONT_SEMIBOLD if on else FONT_MEDIUM,
                color=COLORS["cover_ink"] if on else COLORS["cover_muted"],
            ),
        )

    return ft.Container(
        padding=3,
        border_radius=8,
        bgcolor=COLORS["cover_deep"],
        content=ft.Row(spacing=0, controls=[seg("vi", "Tiếng Việt"), seg("en", "English")]),
    )
