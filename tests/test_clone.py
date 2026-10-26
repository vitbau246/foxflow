"""Cloning a profile: same settings, a fingerprint of its own, the parts that were ticked."""

import json

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core.container import Container
from src.services.profile.clone_parts import PARTS
from src.services.profile.manager import CloneError, ProfileManager
from src.services.workflow.model import Step, Workflow
from src.services.workflow.store import WorkflowStore

API = "/api/v1"


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    # profiles.json and camoufox_data/ are relative to the working directory.
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _source(pm, workdir):
    pm.add_profile(
        "shop-01", "socks5://user:pass@203.0.113.7:1080", "macos", "Europe/Paris", "fr-FR"
    )
    data = workdir / "camoufox_data" / "shop-01"
    (data / "storage").mkdir()
    (data / "cookies.sqlite").write_bytes(b"cookies")
    (data / "cookies.sqlite-wal").write_bytes(b"wal")
    (data / "places.sqlite").write_bytes(b"history")
    (data / "logins.json").write_text("{}", encoding="utf-8")
    (data / "key4.db").write_bytes(b"key")
    (data / "tabs.json").write_text('{"tabs": []}', encoding="utf-8")
    (data / "prefs.js").write_text("", encoding="utf-8")
    (data / "storage" / "ls.sqlite").write_bytes(b"local storage")
    (data / "fingerprint.json").write_text("{}", encoding="utf-8")
    (data / "recording.json").write_text('{"steps": []}', encoding="utf-8")
    (data / "parent.lock").write_bytes(b"")
    (data / "cache2").mkdir()
    (data / "cache2" / "entry").write_bytes(b"x" * 100)
    return data


def test_clone_copies_settings_not_data_by_default(workdir):
    pm = ProfileManager()
    _source(pm, workdir)
    clone = pm.clone_profile("shop-01", "shop-02")
    assert (clone.proxy, clone.os_type, clone.timezone, clone.locale, clone.engine) == (
        "socks5://user:pass@203.0.113.7:1080",
        "macos",
        "Europe/Paris",
        "fr-FR",
        "camoufox",
    )
    copy = workdir / "camoufox_data" / "shop-02"
    assert copy.is_dir() and not any(copy.iterdir())
    saved = json.loads((workdir / "profiles.json").read_text(encoding="utf-8"))
    assert saved["shop-02"]["proxy"] == clone.proxy
    assert "shop-01" in ProfileManager().profiles and "shop-02" in ProfileManager().profiles


def _files(path):
    return sorted(
        str(p.relative_to(path)).replace("\\", "/") for p in path.rglob("*") if p.is_file()
    )


def test_clone_with_every_part_gets_a_new_fingerprint(workdir):
    pm = ProfileManager()
    _source(pm, workdir)
    pm.clone_profile("shop-01", "shop-02", PARTS)
    copy = workdir / "camoufox_data" / "shop-02"
    assert (copy / "cookies.sqlite").read_bytes() == b"cookies"
    assert (copy / "storage" / "ls.sqlite").read_bytes() == b"local storage"
    for skipped in ("fingerprint.json", "recording.json", "parent.lock", "cache2", "prefs.js"):
        assert not (copy / skipped).exists(), skipped
    # The source is untouched.
    assert (workdir / "camoufox_data" / "shop-01" / "fingerprint.json").exists()


@pytest.mark.parametrize(
    ("parts", "files"),
    [
        (["cookies"], ["cookies.sqlite", "cookies.sqlite-wal"]),
        (["history"], ["places.sqlite"]),
        (["site_data"], ["storage/ls.sqlite"]),
        (["passwords"], ["key4.db", "logins.json"]),
        (["tabs"], ["tabs.json"]),
        (["cookies", "tabs"], ["cookies.sqlite", "cookies.sqlite-wal", "tabs.json"]),
    ],
)
def test_each_part_copies_only_its_files(workdir, parts, files):
    pm = ProfileManager()
    _source(pm, workdir)
    pm.clone_profile("shop-01", "shop-02", parts)
    assert _files(workdir / "camoufox_data" / "shop-02") == files


def test_chrome_parts_follow_the_chromium_layout(workdir):
    pm = ProfileManager()
    pm.add_profile("c1", "", "windows", engine="chrome")
    data = workdir / "camoufox_data" / "c1"
    (data / "Default" / "Network").mkdir(parents=True)
    (data / "Local State").write_text("{}", encoding="utf-8")
    (data / "Default" / "Network" / "Cookies").write_bytes(b"c")
    (data / "Default" / "History").write_bytes(b"h")
    (data / "Default" / "Login Data").write_bytes(b"l")
    (data / "chrome_persona.json").write_text("{}", encoding="utf-8")
    pm.clone_profile("c1", "c2", ["cookies"])
    # The cookies are encrypted with the key in Local State: they travel together.
    assert _files(workdir / "camoufox_data" / "c2") == ["Default/Network/Cookies", "Local State"]
    assert pm.profiles["c2"].engine == "chrome"
    with pytest.raises(CloneError, match="Unknown part"):
        pm.clone_profile("c1", "c3", ["everything"])


def test_clone_refusals(workdir):
    pm = ProfileManager()
    _source(pm, workdir)
    pm.add_profile("taken", "", "windows")
    with pytest.raises(CloneError) as e:
        pm.clone_profile("ghost", "x")
    assert e.value.status == 404
    with pytest.raises(CloneError) as e:
        pm.clone_profile("shop-01", "TAKEN")  # names are case-insensitive
    assert e.value.status == 409
    leftover = workdir / "camoufox_data" / "old"
    leftover.mkdir()
    (leftover / "cookies.sqlite").write_bytes(b"someone else's")
    with pytest.raises(CloneError) as e:
        pm.clone_profile("shop-01", "old")
    assert e.value.status == 409
    assert set(pm.profiles) == {"shop-01", "taken"}


def test_clone_name_finds_a_free_name(workdir):
    pm = ProfileManager()
    pm.add_profile("a", "", "windows")
    assert pm.clone_name("a") == "a-copy"
    pm.clone_profile("a", "a-copy")
    assert pm.clone_name("a") == "a-copy-2"
    assert len(pm.clone_name("x" * 64)) <= 64


@pytest.fixture
def client(workdir):
    return TestClient(create_app(Container()), base_url="http://127.0.0.1")


def test_clone_names(workdir):
    pm = ProfileManager()
    pm.add_profile("a", "", "windows")
    assert pm.clone_names("a-copy", 1) == ["a-copy"]
    pm.clone_profile("a", "a-copy-2")
    # Numbers in use are skipped.
    assert pm.clone_names("a-copy", 3) == ["a-copy-1", "a-copy-3", "a-copy-4"]
    assert all(len(n) <= 64 for n in pm.clone_names("x" * 64, 50))


def test_clone_many(workdir):
    pm = ProfileManager()
    _source(pm, workdir)
    made = pm.clone_profiles("shop-01", pm.clone_names("batch", 3), ["cookies"])
    assert [p.name for p in made] == ["batch-1", "batch-2", "batch-3"]
    for p in made:
        copy = workdir / "camoufox_data" / p.name
        assert (copy / "cookies.sqlite").exists() and not (copy / "fingerprint.json").exists()
    with pytest.raises(CloneError):
        pm.clone_profiles("shop-01", [f"n{i}" for i in range(51)])
    with pytest.raises(CloneError, match="Created 1 of 2"):
        pm.clone_profiles("shop-01", ["ok-1", "batch-1"])
    assert "ok-1" in pm.profiles


def test_clone_route(client, workdir):
    def names(r):
        return [p["name"] for p in r.json()["profiles"]]

    client.post(f"{API}/profiles", json={"name": "p1", "os_type": "linux", "locale": "vi-VN"})
    r = client.post(f"{API}/profiles/p1/clone", json={})
    assert r.status_code == 201 and names(r) == ["p1-copy"]
    first = r.json()["profiles"][0]
    assert first["os_type"] == "linux" and first["locale"] == "vi-VN"
    r = client.post(f"{API}/profiles/p1/clone", json={"name": "p2", "copy_data": True})
    assert r.status_code == 201 and names(r) == ["p2"]
    r = client.post(f"{API}/profiles/p1/clone", json={"name": "p3", "copy": ["history"]})
    assert r.status_code == 201
    assert client.post(f"{API}/profiles/p1/clone", json={"copy": ["nope"]}).status_code == 422
    r = client.post(f"{API}/profiles/p1/clone", json={"name": "shop", "count": 3})
    assert r.status_code == 201 and names(r) == ["shop-1", "shop-2", "shop-3"]
    assert r.json()["total"] == 3
    r = client.post(f"{API}/profiles/p1/clone", json={"count": 2})
    assert names(r) == ["p1-copy-1", "p1-copy-2"]
    assert client.post(f"{API}/profiles/p1/clone", json={"count": 0}).status_code == 422
    assert client.post(f"{API}/profiles/p1/clone", json={"count": 51}).status_code == 422
    assert client.post(f"{API}/profiles/p1/clone", json={"name": "P2"}).status_code == 409
    assert client.post(f"{API}/profiles/ghost/clone", json={}).status_code == 404
    assert client.post(f"{API}/profiles/p1/clone", json={"name": "a/b"}).status_code == 400
    listed = {p["name"] for p in client.get(f"{API}/profiles").json()["profiles"]}
    assert len(listed) == 9


def test_copying_data_needs_the_source_stopped(client, monkeypatch):
    client.post(f"{API}/profiles", json={"name": "live"})
    launcher = client.app.state.container.browser_launcher
    monkeypatch.setattr(launcher, "is_running", lambda name: name == "live")
    with launcher._lock:
        launcher._active_sessions["live"] = type("P", (), {"poll": lambda self: None})()
    try:
        r = client.post(f"{API}/profiles/live/clone", json={"copy": ["cookies"]})
        assert r.status_code == 409 and "Stop the browser" in r.json()["detail"]
        # Settings and workflows can be cloned while it runs.
        assert client.post(f"{API}/profiles/live/clone", json={}).status_code == 201
        r = client.post(f"{API}/profiles/live/clone", json={"name": "w", "copy": ["workflows"]})
        assert r.status_code == 201
    finally:
        with launcher._lock:
            launcher._active_sessions.clear()


def test_mcp_has_clone_tool():
    import asyncio

    from src.mcp_server.server import mcp

    assert "clone_profile" in {t.name for t in asyncio.run(mcp.list_tools())}


def _workflow(name, profile):
    return Workflow(
        name=name, profile=profile, steps=[Step(action="navigate", value="https://example.test/")]
    )


def test_each_clone_gets_its_own_workflows(client, workdir):
    store = WorkflowStore(str(workdir / "workflows"))
    store.save(_workflow("login", "p1"))
    store.save(_workflow("buy", "P1"))  # profile names are case-insensitive
    store.save(_workflow("other", "p9"))
    client.post(f"{API}/profiles", json={"name": "p1"})
    r = client.post(
        f"{API}/profiles/p1/clone", json={"name": "c", "count": 2, "copy": ["workflows"]}
    )
    assert r.status_code == 201 and r.json()["workflows_copied"] == 4
    assert [w.name for w in store.of_profile("c-1")] == ["buy-c-1", "login-c-1"]
    assert [w.name for w in store.of_profile("c-2")] == ["buy-c-2", "login-c-2"]
    assert store.get("login-c-1").steps[0].value == "https://example.test/"
    # Cloning again does not overwrite: the names get a number.
    assert store.copy_to_profile("p1", "c-1") == ["buy-c-1-2", "login-c-1-2"]
    # Without the box ticked nothing is copied.
    r = client.post(f"{API}/profiles/p1/clone", json={"name": "d"})
    assert r.json()["workflows_copied"] == 0 and store.of_profile("d") == []


def test_a_renamed_profile_keeps_its_workflows(client, workdir):
    store = WorkflowStore(str(workdir / "workflows"))
    client.post(f"{API}/profiles", json={"name": "old"})
    store.save(_workflow("login", "old"))
    assert client.patch(f"{API}/profiles/old", json={"name": "new"}).status_code == 200
    assert [w.name for w in store.of_profile("new")] == ["login"]
    assert store.of_profile("old") == []
