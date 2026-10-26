"""The Triggers section of the Automation page and the trigger editor (desktop)."""

from types import SimpleNamespace

import flet as ft

from src.services.automation.model import Automation, Trigger
from src.services.automation.store import AutomationStore
from src.ui.components.automation import AutomationActions, AutomationData, AutomationPage
from src.ui.dialogs.trigger_editor import open_trigger_editor
from tests.test_automation_ui import FakePage, _texts, _walk

TRIGGERS = [
    {
        "id": "a1",
        "name": "New orders",
        "enabled": True,
        "trigger": {"type": "file", "folder": "/data/inbox", "pattern": "*.csv"},
        "profiles": ["shop-01", "shop-02"],
        "workflows": ["login", "post"],
        "close_profile": True,
        "state": {
            "queued": 1,
            "active": False,
            "error": "",
            "last": {"status": "succeeded", "at": "2026-10-26T09:15:00", "preview": "o.csv"},
            "history": [],
        },
    },
    {
        "id": "a2",
        "name": "Clips",
        "enabled": False,
        "trigger": {"type": "clipboard", "pattern": "https?://"},
        "profiles": ["shop-01"],
        "workflows": ["post"],
        "close_profile": False,
        "state": {"queued": 0, "active": False, "error": "", "last": None, "history": []},
    },
]


def test_the_page_lists_triggers_and_their_actions():
    calls = []

    def record(name):
        return lambda *args: calls.append((name, *args))

    noop = lambda *a: None  # noqa: E731
    actions = AutomationActions(
        noop,
        noop,
        noop,
        noop,
        noop,
        noop,
        noop,
        on_new_trigger=record("new"),
        on_edit_trigger=record("edit"),
        on_delete_trigger=record("delete"),
        on_fire_trigger=record("fire"),
        on_toggle_trigger=record("toggle"),
    )
    page = AutomationPage(actions, noop)
    page.render(AutomationData([], [], set(), triggers=TRIGGERS))
    texts = _texts(page.control)
    assert "Triggers" in texts and "New orders" in texts
    assert "New *.csv in /data/inbox" in texts
    assert "When copied text matches https?:// · Off" in texts
    assert "login → post" in texts and "2 profiles · then close" in texts
    assert "26/10 09:15 · o.csv · 1 waiting" in texts and "Not fired yet" in texts

    buttons = [c for c in _walk(page.control) if isinstance(c, ft.Button)]
    next(b for b in buttons if b.content == "Run now").on_click(None)
    next(
        c
        for c in _walk(page.control)
        if isinstance(c, ft.OutlinedButton) and c.content == "New trigger"
    ).on_click(None)
    switch = next(c for c in _walk(page.control) if isinstance(c, ft.Switch))
    switch.on_change(SimpleNamespace(control=SimpleNamespace(value=False)))
    assert calls == [("fire", "a1"), ("new",), ("toggle", "a1", False)]

    page.render(AutomationData([], [], set()))
    assert any("A trigger runs workflows by itself" in t for t in _texts(page.control))


def _button(dlg, text):
    return next(
        c
        for c in _walk(dlg)
        if isinstance(c, (ft.Button, ft.TextButton, ft.OutlinedButton)) and c.content == text
    )


def test_editor_creates_a_trigger(tmp_path):
    store = AutomationStore(str(tmp_path / "a.json"))
    fake = FakePage()
    saved = []
    open_trigger_editor(
        fake, store, ["p1", "p2"], ["login", "post"], on_saved=saved.append, hook_base="http://h"
    )
    dlg = fake.dialogs[-1]
    assert "Webhook URL" in _texts(dlg)
    dlg.actions[-1].on_click(None)
    assert "Give the trigger a name" in _texts(dlg)

    name = next(c for c in _walk(dlg) if isinstance(c, ft.TextField))
    name.value = "Orders"
    boxes = [c for c in _walk(dlg) if isinstance(c, ft.Checkbox) and c.label is None]
    boxes[1].on_change(SimpleNamespace(control=SimpleNamespace(value=True)))
    kind = next(
        c
        for c in _walk(dlg)
        if isinstance(c, ft.Dropdown) and any(o.key == "schedule" for o in c.options)
    )
    kind.value = "schedule"
    kind.on_select(SimpleNamespace(control=kind))
    assert "Daily at (HH:MM, separated by commas)" in _texts(dlg)
    dlg.actions[-1].on_click(None)  # a schedule needs a time
    assert any("interval" in t for t in _texts(dlg))
    every = next(c for c in _walk(dlg) if isinstance(c, ft.TextField) and c.value == "0")
    every.on_change(SimpleNamespace(control=SimpleNamespace(value="15")))
    _button(dlg, "Add workflow").on_click(None)
    dlg.actions[-1].on_click(None)
    assert saved == ["Orders"] and not fake.dialogs
    stored = store.get("Orders")
    assert stored.profiles == ["p2"] and stored.workflows == ["login", "post"]
    assert stored.trigger.every_minutes == 15


def test_editor_shows_the_webhook_url_and_makes_a_new_key(tmp_path):
    store = AutomationStore(str(tmp_path / "a.json"))
    a = store.save(Automation(name="Hook", trigger=Trigger(), profiles=["p1"], workflows=["w"]))
    copied = []
    fake = FakePage()
    open_trigger_editor(
        fake, store, ["p1"], ["w"], a.id, hook_base="http://h/hooks", copy=copied.append
    )
    dlg = fake.dialogs[-1]
    url = f"http://h/hooks/{a.id}?key={a.trigger.key}"
    assert url in _texts(dlg)
    import asyncio

    asyncio.run(_button(dlg, "Copy").on_click(None))
    assert copied == [url] and "Copied" in _texts(dlg)
    _button(dlg, "New key").on_click(None)
    assert url not in _texts(dlg)
    dlg.actions[-1].on_click(None)
    assert store.get(a.id).trigger.key != a.trigger.key
