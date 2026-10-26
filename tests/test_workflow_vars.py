"""Variables, get_text results and AI steps in a workflow run (no browser, no real AI)."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi.testclient import TestClient

from src.services.ai.client import AIError, generate
from src.services.ai.settings import AISettings, AISettingsStore
from src.services.workflow.model import Step, Workflow, problems, render
from src.services.workflow.runner import WorkflowRunner
from src.services.workflow.store import WorkflowError, WorkflowStore
from tests.test_workflow_runner import FakeLauncher, FakeProfiles, _wait


def test_render_and_references():
    assert render("Hi {{ name }}, {{name}}!", {"name": "An"}) == "Hi An, An!"
    with pytest.raises(KeyError):
        render("{{missing}}", {})


def test_problems_check_variables_in_order():
    wf = Workflow(
        name="x",
        variables={"site": "https://example.test"},
        steps=[
            Step(action="navigate", value="{{site}}/{{profile}}"),
            Step(action="fill", selectors=["#q"], value="{{comment}}"),  # saved later
            Step(action="get_text", selectors=["#post"], save_as="post", value=r"\d{3}"),
            Step(action="ai", value="Reply to: {{post}}", save_as="comment"),
            Step(action="fill", selectors=["#q"], value="{{comment}}"),
            Step(action="ai", value="no target"),
        ],
    )
    issues = problems(wf)
    assert issues == [
        "Step 2 (fill): unknown variable {{comment}}",
        "Step 6 (ai): needs a variable to save into",
    ]


def test_bad_variable_names_are_refused():
    with pytest.raises(ValueError):
        Workflow(name="x", variables={"1st": "a"})
    with pytest.raises(ValueError):
        Workflow(name="x", variables={"profile": "a"})
    with pytest.raises(ValueError):
        Step(action="ai", value="p", save_as="my var")


@pytest.fixture
def ai_store(tmp_path):
    store = AISettingsStore(str(tmp_path / "ai_settings.json"))
    store.save(AISettings(api_key="sk-test-0000000000"))
    return store


def _runner(tmp_path, launcher, workflow, ai_store, ai=None):
    store = WorkflowStore(str(tmp_path / "workflows"))
    store.save(workflow)
    return WorkflowRunner(
        store,
        FakeProfiles("p1"),
        launcher,
        launch_timeout=5,
        ai_settings=ai_store,
        ai_generate=ai or (lambda settings, prompt, timeout: f"AI says: {prompt}"),
    )


def test_get_text_and_ai_feed_later_steps(tmp_path, ai_store, monkeypatch):
    monkeypatch.setattr(WorkflowRunner, "RESTART_PAUSE_S", 0)
    wf = Workflow(
        name="wf",
        variables={"tone": "friendly"},
        settings={"retry_delay_ms": 0},
        steps=[
            Step(id="g", action="get_text", selectors=["#post"], save_as="post", delay_ms=0),
            Step(id="a", action="ai", value="Be {{tone}}: {{post}}", save_as="reply", delay_ms=0),
            Step(
                id="f", action="fill", selectors=["#c-{{profile}}"], value="{{reply}}", delay_ms=0
            ),
        ],
    )
    bl = FakeLauncher()
    original = bl.control

    def control(name, action, params=None, timeout=60):
        result = original(name, action, params, timeout)
        if action == "run_step" and params["step"]["action"] == "get_text":
            return {**result, "text": "Great post"}
        return result

    bl.control = control
    prompts = []

    def ai(settings, prompt, timeout):
        prompts.append(prompt)
        return "Thanks!"

    runner = _runner(tmp_path, bl, wf, ai_store, ai)
    runner.start("wf", "p1")
    state = _wait(runner)
    assert state["status"] == "succeeded", state
    assert prompts == ["Be friendly: Great post"]
    sent = [p["step"] for a, p in bl.calls if a == "run_step"]
    # AI steps never reach the browser.
    assert [s["id"] for s in sent] == ["g", "f"]
    assert sent[1]["value"] == "Thanks!" and sent[1]["selectors"] == ["#c-p1"]
    assert state["variables"]["reply"] == "Thanks!"
    assert any("{{reply}}" in line for line in state["log"])


def test_variables_can_be_set_for_one_run(tmp_path, ai_store):
    wf = Workflow(
        name="wf",
        variables={"q": "default"},
        steps=[Step(action="fill", selectors=["#q"], value="{{q}}", delay_ms=0)],
    )
    bl = FakeLauncher()
    runner = _runner(tmp_path, bl, wf, ai_store)
    runner.start("wf", "p1", {"q": "this run"})
    _wait(runner)
    assert [p["step"]["value"] for a, p in bl.calls if a == "run_step"] == ["this run"]
    with pytest.raises(WorkflowError):
        runner.start("wf", "p1", {"bad name": "x"})


def test_a_failing_ai_call_is_retried(tmp_path, ai_store):
    wf = Workflow(
        name="wf",
        settings={"retry_delay_ms": 0, "retries": 2, "max_restarts": 0},
        steps=[Step(action="ai", value="hi", save_as="x", delay_ms=0)],
    )
    calls = []

    def ai(settings, prompt, timeout):
        calls.append(prompt)
        if len(calls) < 3:
            raise AIError("rate limited")
        return "ok"

    runner = _runner(tmp_path, FakeLauncher(), wf, ai_store, ai)
    runner.start("wf", "p1")
    state = _wait(runner)
    assert state["status"] == "succeeded" and len(calls) == 3


def test_ai_steps_need_ai_set_up(tmp_path):
    wf = Workflow(name="wf", steps=[Step(action="ai", value="hi", save_as="x")])
    empty = AISettingsStore(str(tmp_path / "none.json"))
    runner = _runner(tmp_path, FakeLauncher(), wf, empty)
    with pytest.raises(WorkflowError, match="set up AI"):
        runner.start("wf", "p1")


class _FakeOpenAI(BaseHTTPRequestHandler):
    requests: list = []

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _FakeOpenAI.requests.append((self.path, self.headers["Authorization"], body))
        if body["messages"][-1]["content"] == "fail":
            self.send_response(429)
            payload = {"error": {"message": "Rate limit reached"}}
        else:
            self.send_response(200)
            payload = {"choices": [{"message": {"content": '"Hello there"'}}]}
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

    def log_message(self, *args):
        pass


@pytest.fixture
def fake_openai(monkeypatch):
    # The corporate proxy of a CI or dev machine must not swallow loopback calls.
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    server = HTTPServer(("127.0.0.1", 0), _FakeOpenAI)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _FakeOpenAI.requests = []
    yield f"http://127.0.0.1:{server.server_port}/v1"
    server.shutdown()


def test_client_talks_chat_completions(fake_openai):
    settings = AISettings(api_key="sk-abc", base_url=fake_openai, model="m1", temperature=0.5)
    assert generate(settings, "hi") == "Hello there"  # quotes around the reply are dropped
    path, auth, body = _FakeOpenAI.requests[0]
    assert path == "/v1/chat/completions" and auth == "Bearer sk-abc"
    assert body["model"] == "m1" and body["temperature"] == 0.5
    assert body["messages"][0]["role"] == "system" and body["messages"][1]["content"] == "hi"
    with pytest.raises(AIError, match="HTTP 429.*Rate limit"):
        generate(settings, "fail")
    with pytest.raises(AIError, match="API key"):
        generate(AISettings(), "hi")


def test_ai_settings_api(tmp_path, monkeypatch, fake_openai):
    from src.api.app import create_app
    from src.core.container import Container

    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app(Container()), base_url="http://127.0.0.1")
    api = "/api/v1/ai"
    assert client.get(f"{api}/settings").json()["configured"] is False
    r = client.put(
        f"{api}/settings", json={"api_key": "sk-secret-123456789", "base_url": fake_openai}
    )
    assert r.status_code == 200
    shown = r.json()
    assert shown["configured"] and "secret" not in json.dumps(shown)
    assert shown["key_hint"] == "sk-…6789"
    # Omitting the key keeps it.
    client.put(f"{api}/settings", json={"model": "m2"})
    saved = json.loads((tmp_path / "ai_settings.json").read_text(encoding="utf-8"))
    assert saved["api_key"] == "sk-secret-123456789" and saved["model"] == "m2"
    assert client.post(f"{api}/test", json={"prompt": "hi"}).json() == {"text": "Hello there"}
    assert client.post(f"{api}/test", json={"prompt": "fail"}).status_code == 502
    assert client.put(f"{api}/settings", json={"base_url": "ftp://x"}).status_code == 400
    client.put(f"{api}/settings", json={"api_key": ""})
    assert client.get(f"{api}/settings").json()["configured"] is False


def test_wait_helper_is_shared():
    # _wait comes from test_workflow_runner; make sure it still times out sensibly.
    class Never:
        def get(self, _):
            return {"active": True}

    start = time.monotonic()
    with pytest.raises(AssertionError):
        _wait(Never(), timeout=0.1)
    assert time.monotonic() - start < 2
