"""REST routes for workflows, runs and recordings (no browser needed)."""

import json

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core.container import Container

API = "/api/v1"


@pytest.fixture
def client(tmp_path, monkeypatch):
    # profiles.json, camoufox_data/ and workflows/ are relative to the working directory.
    monkeypatch.chdir(tmp_path)
    c = TestClient(create_app(Container()), base_url="http://127.0.0.1")
    assert c.post(f"{API}/profiles", json={"name": "p1"}).status_code == 201
    return c


WF = {
    "name": "ignored",
    "steps": [
        {"action": "navigate", "value": "https://example.test/"},
        {"action": "fill", "selectors": ["#q"], "value": "hi", "char_delay_ms": 80},
    ],
    "settings": {"speed": 1.5, "retries": 2},
}


def test_crud(client):
    assert client.get(f"{API}/workflows").json() == {"workflows": []}
    r = client.put(f"{API}/workflows/search", json=WF)
    assert r.status_code == 200 and r.json()["name"] == "search"
    assert client.post(f"{API}/workflows", json={**WF, "name": "search"}).status_code == 409
    got = client.get(f"{API}/workflows/search").json()
    assert got["steps"][1]["char_delay_ms"] == 80 and got["settings"]["speed"] == 1.5
    assert got["steps"][0]["check"] == {"type": "auto", "value": ""}
    assert client.get(f"{API}/workflows").json()["workflows"][0]["step_count"] == 2
    assert client.delete(f"{API}/workflows/search").status_code == 200
    assert client.get(f"{API}/workflows/search").status_code == 404
    assert client.delete(f"{API}/workflows/search").status_code == 404


def test_invalid_input(client):
    bad = {"name": "x", "steps": [{"action": "click"}]}
    r = client.put(f"{API}/workflows/x", json=bad)
    assert r.status_code == 400 and "needs a selector" in r.json()["detail"]
    assert client.put(f"{API}/workflows/a%2Fb", json=WF).status_code in (400, 404)
    assert client.put(f"{API}/workflows/x", json={"steps": [{"action": "nope"}]}).status_code == 422


def test_runs(client):
    client.put(f"{API}/workflows/search", json=WF)
    assert client.get(f"{API}/workflow-runs").json() == {"runs": []}
    assert client.get(f"{API}/workflow-runs/p1").status_code == 404
    assert client.post(f"{API}/workflow-runs/p1/stop").status_code == 409
    r = client.post(f"{API}/workflows/missing/run", json={"profile": "p1"})
    assert r.status_code == 404
    r = client.post(f"{API}/workflows/search/run", json={"profile": "ghost"})
    assert r.status_code == 404


def test_recording_needs_a_running_browser(client):
    r = client.post(f"{API}/browser/p1/record/start")
    assert r.status_code == 409
    assert client.post(f"{API}/browser/ghost/record/start").status_code == 404
    assert client.get(f"{API}/browser/p1/record").json()["recording"] is False


def test_a_draft_left_by_a_closed_browser_can_be_saved(client, tmp_path):
    draft_dir = tmp_path / "camoufox_data" / "p1"
    draft_dir.mkdir(parents=True, exist_ok=True)
    steps = [
        {
            "id": "a1",
            "action": "navigate",
            "value": "https://example.test/",
            "label": "example.test",
            "selectors": [],
            "frame": "",
            "delay_ms": 0,
            "expect_url": "",
            "_tab": 0,
        },
        {
            "id": "a2",
            "action": "click",
            "value": "",
            "label": "Go",
            "selectors": ["#go"],
            "frame": "",
            "delay_ms": 700,
            "expect_url": "https://example.test/done",
            "_tab": 0,
        },
    ]
    (draft_dir / "recording.json").write_text(
        json.dumps({"recording": True, "started_at": "t", "steps": steps}), encoding="utf-8"
    )
    listed = client.get(f"{API}/recordings").json()["recordings"]
    assert [(r["profile"], r["draft"], r["step_count"]) for r in listed] == [("p1", True, 2)]
    status = client.get(f"{API}/browser/p1/record").json()
    assert status["draft"] is True and status["step_count"] == 2
    assert status["recent"] == ["navigate example.test", "click Go"]

    # Stopping without a name keeps the draft.
    r = client.post(f"{API}/browser/p1/record/stop", json={})
    assert r.status_code == 200 and len(r.json()["steps"]) == 2
    assert (draft_dir / "recording.json").exists()

    r = client.post(f"{API}/browser/p1/record/stop", json={"save_as": "go", "description": "d"})
    assert r.status_code == 201
    wf = r.json()["workflow"]
    assert wf["profile"] == "p1" and wf["steps"][1]["expect_url"] == "https://example.test/done"
    assert "_tab" not in wf["steps"][0]
    assert not (draft_dir / "recording.json").exists()
    assert client.get(f"{API}/workflows/go").status_code == 200


def test_discard_a_draft(client, tmp_path):
    draft_dir = tmp_path / "camoufox_data" / "p1"
    draft_dir.mkdir(parents=True, exist_ok=True)
    (draft_dir / "recording.json").write_text(
        json.dumps({"steps": [{"action": "navigate", "value": "https://e.test/"}]}),
        encoding="utf-8",
    )
    r = client.post(f"{API}/browser/p1/record/stop", json={"discard": True})
    assert r.json()["discarded"] is True
    assert client.get(f"{API}/browser/p1/record").json()["draft"] is False


def test_mcp_exposes_workflow_tools():
    import asyncio

    from src.mcp_server.server import mcp

    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert {"list_workflows", "get_workflow", "run_workflow", "workflow_run_status"} <= names
    assert "delete_workflow" not in names
