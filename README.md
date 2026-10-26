<div align="center">
  <img src="src/assets/icon.png" width="112" alt="FoxFlow logo" />
  <h1>FoxFlow</h1>
  <p><strong>Self-hosted web automation: record a task once, replay it in any browser profile</strong></p>
  <p>Record-and-replay workflows with checks, retries, variables, if/else, loops and AI text · Isolated browser profiles (Camoufox or Chrome) · REST API and MCP for scripts and AI agents · English and Vietnamese UI</p>

  <p>
    <a href="https://github.com/vitbau246/foxflow/actions/workflows/ci.yml"><img src="https://github.com/vitbau246/foxflow/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
    <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+" />
    <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey" alt="Windows | macOS | Linux" />
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License" /></a>
    <a href="https://github.com/chienbm98/foxprofile"><img src="https://img.shields.io/badge/based%20on-FoxProfile-orange" alt="Based on FoxProfile" /></a>
  </p>

  <p>English · <a href="README.vi.md">Tiếng Việt</a></p>
  <p>
    <a href="#quick-start">Quick start</a> ·
    <a href="#workflows-record-and-replay">Workflows</a> ·
    <a href="#mcp-let-ai-agents-drive-the-browser">MCP</a> ·
    <a href="#rest-api">REST API</a> ·
    <a href="#based-on-foxprofile">Credits</a>
  </p>
</div>

![FoxFlow: the Automation dashboard](docs/images/en/automation.png)

FoxFlow automates repetitive work in the browser. Do a task once while FoxFlow records it, tune the steps, then replay it: every step is checked, a failed step is retried, and a stuck run restarts the browser and starts over. Workflows can read text from the page (select it or rest the mouse on it while recording), fill in variables, branch with if/else, repeat steps in loops, chain several workflows in one run and ask an OpenAI-compatible model to write text for you. You run them from the desktop app, the web panel, the REST API, or let an AI agent (Claude, Cursor...) drive the browser over MCP.

Every run happens inside a **browser profile**: an isolated browser with its own cookies, logins, proxy, timezone, locale and a stable device fingerprint, so tasks for different accounts or clients never share a session. Profiles run on [Camoufox](https://github.com/daijro/camoufox) (Firefox) or an experimental Chrome engine based on [fingerprint-chromium](https://github.com/adryfish/fingerprint-chromium), on your own machine or a VPS.

> [!NOTE]
> **FoxFlow is based on [FoxProfile](https://github.com/chienbm98/foxprofile) by [chienbm98](https://github.com/chienbm98)**, an open-source (MIT) manager for browser profiles. FoxFlow keeps all of FoxProfile's profile management and refocuses the project on web automation. See [Based on FoxProfile](#based-on-foxprofile).

## Contents

- [Features](#features)
- [Requirements](#requirements)
- [Quick start](#quick-start)
- [Workflows: record and replay](#workflows-record-and-replay)
- [MCP: let AI agents drive the browser](#mcp-let-ai-agents-drive-the-browser)
- [Server mode and web panel](#server-mode-and-web-panel)
- [Browser profiles](#browser-profiles)
- [Configuration](#configuration)
- [REST API](#rest-api)
- [Moving from FoxProfile](#moving-from-foxprofile)
- [Development](#development)
- [Contributing](#contributing)
- [Responsible use](#responsible-use)
- [Based on FoxProfile](#based-on-foxprofile)
- [License](#license)
- [Acknowledgements](#acknowledgements)

## Features

**Automation**

- **An automation dashboard.** The app opens on every profile's current or last run (step progress, retries, a stamp for its state, the reason it failed) and on every saved workflow with its last result. Stop, run again or open the log in one click.
- **One workflow, many profiles.** Run a workflow in as many profiles as you pick, with its variables filled in for that run; stopped profiles are launched first.
- **Record and replay workflows.** Every click, keystroke, selection, key press, scroll and page load in a profile's browser becomes a step, with several fallback selectors per element.
- **Reliable replays.** Each step is checked (the field holds the text, the box is ticked, the click reached the same page), retried on failure, and the whole run restarts from step 1 in a fresh browser when a step keeps failing.
- **Human pacing.** Each step keeps the delay you actually took while recording, typing has its own speed per character, and one speed setting (x0.25 to x5) scales the whole workflow.
- **Variables, page text and AI.** `{{variables}}` in values, URLs and selectors; *Get text* reads the page into a variable (optionally through a regex), and while recording, selecting text or resting the mouse on an element for 3 s offers to add one; *AI text* sends a prompt to an OpenAI-compatible API and saves the reply.
- **If, loops and chains.** *If / Else*, *Repeat for* (a count or a list), *Repeat while*, *Exit loop* and *Set variable* steps, with conditions on variables or on the page; run several workflows one after the other in one browser.
- **Hover menus.** Clicks on elements that only appear on hover are recorded with a *Hover first* step.
- **AI agents over MCP.** Claude Code, Claude Desktop, Cursor, VS Code and others can launch profiles, navigate, read, click, type, take screenshots and run your workflows.
- **REST API** with Swagger docs for every action, so any script or scheduler can start runs and read their logs.
- **Server mode + web panel** for a VPS: hidden browsers, a token-protected panel and a remote screen view you can click and type into.

**Browser profiles** (from FoxProfile)

- **Isolated sessions.** History, cookies and logins stay in each profile's directory; open tabs are reopened on the next launch.
- **Stable device fingerprint per profile**, generated once and reused, so a site sees the same device every time.
- **Two engines.** Camoufox (Firefox, default) or Chrome (fingerprint-chromium, experimental), chosen when the profile is created.
- **Per-profile proxy** (HTTP/HTTPS/SOCKS4/SOCKS5, with or without auth, `host:port:user:pass` too), a proxy checker, and timezone/locale that follow the exit IP or are pinned per profile.
- **Cookie export/import** (Cookie-Editor JSON, Netscape `cookies.txt`), **profile ZIP export/import**, and **clone** a profile up to 50 times with its workflows.
- **Bulk actions, filters and search** in a profile table built for scanning, in the desktop app and the web panel.
- **English** (default) and Vietnamese UI, switchable inside the app. Fonts are bundled, no network needed.

## Requirements

- Python 3.10+
- Windows, macOS or Linux (CI tests all three)
- A few hundred MB of free disk space for Camoufox and the GeoIP database, plus ~140-190 MB for the Chrome engine if you use it

## Quick start

```bash
git clone https://github.com/vitbau246/foxflow.git
cd foxflow

python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Linux/macOS

pip install -r requirements.txt
python -m camoufox fetch
```

`camoufox fetch` downloads the Camoufox browser (a few hundred MB) from the Camoufox GitHub releases. The first profile launch also downloads a GeoIP database (~50 MB).

Run the app:

```bash
python -m src.main
```

On Windows you can also double-click `run_foxflow.bat`. The app opens the main window and serves the API on `http://127.0.0.1:8000`; API docs are at `http://127.0.0.1:8000/docs`. Set `FOXFLOW_LANG=vi` for the Vietnamese UI.

Your first automation: create a profile, then in **Automation** click **Record workflow** and pick it. Launch it from that dialog, click **Start recording**, do the task in the browser, then **Stop and save**. Press **Run** on the new workflow to replay it in one or many profiles.

## Workflows: record and replay

A workflow is a task you did once in a profile's browser, saved as steps you can replay in any profile.

### The Automation dashboard

The desktop app and the web panel open on **Automation** (switch to **Profiles** in the left rail for the profile table):

- **Runs**: the current or last run of every profile, active runs first. Each row shows the step it is on with a progress rule, the attempt and restarts, a stamp for the state (running, starting, done, failed, stopped) and, for a failed run, the reason. Stop a run, **Run again**, open its **Log** (live while it runs) or view the profile's screen.
- **Workflows**: every saved workflow with the profile it was recorded in, its steps and its last result. **Run** opens the run dialog; edit and delete sit next to it.
- **Run dialog**: tick the profiles that should run the workflow (each runs its own copy; profiles that are recording or already running a workflow are greyed out with the reason) and fill in the workflow's variables for this run. Stopped profiles are launched first.
- In **Profiles**, select rows and use **Run workflow** in the bulk bar to run a workflow you pick in all of them.

The dashboard refreshes every 1.5 s while something runs and every 4 s otherwise.

### Record, edit, run

Open a profile's workflows with the **Workflows** button on its row, or with **Record workflow** in Automation.

1. **Record.** Launch the profile, click **Start recording**, then do the task in its browser: every click, keystroke, selection, key press (Enter, Escape, Tab...) and scroll becomes a step, and so does opening a page. On a server, do it through **View screen**. **Stop and save** names it. If the browser closes while recording, the steps are kept as an unsaved recording you can still save.
2. **Edit.** Each step has its own **delay** (the pause before it, taken from how long you actually paused while recording) and, for typing, a **typing speed** in ms per character (0 types at once). A workflow-wide **speed** divides every delay: x2 runs twice as fast. Steps can be disabled, reordered, added or removed; **Details** shows the selectors (tried in order), the value, the frame, the timeout and the expected URL.
3. **Run.** Every step's result is checked by default: a typed field must hold the text, a ticked box must be ticked, a click that changed the page while recording must reach the same page again, and the element must be found within the step timeout. A check can instead wait for a URL, a title, an element or a text, or be turned off. A failed step is retried after the retry delay (**2 retries** by default); if it still fails, the browser is closed and the workflow runs again **from step 1**, up to **3 restarts** by default, then the run is reported as failed with the reason. Follow the run, its log and stop it from the same dialog.

Running a workflow leaves one tab open in the profile (it starts the way a recording does) and refuses to start while the profile is recording. Stopping the profile also stops its run. A workflow can also be started from the REST API (`POST /workflows/{name}/run`) or by an AI agent (`run_workflow`).

### Hover menus, variables, page text and AI

- **Hover first.** Some buttons only exist while something else is hovered: reaction pickers appear over a "Like" button, menus open on hover. When a click lands in such a part of the page, the recording adds **Hover first** to that step (the element to hover, then a pause, 800 ms by default). Add it by hand in a step's **Details** when the recording missed it.
- **Variables.** Write `{{name}}` in a step's value, URL or selector; it is replaced when the step runs. Give variables a starting value under **Variables** in the editor, or per run with the API (`"variables": {...}`). `{{profile}}` is always the running profile's name. A step that uses an unknown variable is refused when you save.
- **Get text** reads an element's visible text (the whole page without a selector), optionally through a regular expression (its first group is kept, e.g. `#(\d+)`), and saves it into a variable. Its check fails when there is no text or the expression does not match.
- **AI text** sends its prompt, with its `{{variables}}` filled in, to an OpenAI-compatible Chat Completions API and saves the reply into a variable, e.g. *Get text* of an order page into `{{order}}`, *AI text* "Write a short reply confirming this order: {{order}}" into `{{reply}}`, then *Type* `{{reply}}`. Set it up with **AI settings** in the editor: API key, base URL (OpenAI by default; Azure OpenAI, OpenRouter or a local LLM work too), model, system prompt and temperature, with a **Test** button. AI is off until a key is set. The prompt, including any page text it uses, is sent to that service, from the FoxFlow process (not through the profile's proxy). The key is kept in `ai_settings.json` next to `profiles.json`, or comes from `FOXFLOW_OPENAI_API_KEY`, which is never written to disk.

### Get text while recording

While recording, **select text** with the mouse, or **rest the mouse on an element for 3 seconds**: a small card in the page asks *Get this text?*, shows the text and suggests a variable name (`text1`, `text2`...). **Get text** adds a *Get text* step for that element; **Skip**, Escape or a click elsewhere dismisses it, and the same element is not offered again until the mouse moves to another one. The card's own clicks and keys are not recorded, dragging to select text is not recorded as a click, and the step's selectors never use the element's text (it changes from run to run).

### If, loops and variables

Steps can also steer the run. These run in FoxFlow, between the browser steps:

| Step | What it does |
|---|---|
| **Set variable** | Saves a value into a variable: text with `{{variables}}`, or `=` and an expression, e.g. `= count + 1`, `= upper(name)`. |
| **If** ... **Else** ... **End** | Runs the steps up to Else (or End) when the condition holds, the steps after Else otherwise. |
| **Repeat for** ... **End** | Runs the steps inside once per item: a number N (rounds 1 to N), or a list, one item per line or separated by commas, e.g. `{{names}}`. The item (or round number) goes into the step's variable. |
| **Repeat while** ... **End** | Runs the steps inside while the condition holds, at most *At most (rounds)* times (100 by default). |
| **Exit loop** | Leaves the innermost Repeat. |

A condition is either an **expression on variables**, e.g. `price > 100 and status == "ok"`, `contains(title, "Sale")`, `len(code) == 6` (two values that read as numbers compare as numbers; functions: `len`, `int`, `num`, `str`, `lower`, `upper`, `trim`, `contains`, `startswith`, `endswith`, `matches`, `replace`), or a **page condition**: element visible, text visible, URL contains, title contains, optionally waited for up to the step's timeout. Tick *Go in when the condition does NOT hold* to turn it around. Expressions are parsed, never executed as code.

In the editor, steps inside a block are indented, **+** on a row inserts a step below it, and picking If or a Repeat adds its End. Saving refuses a block without its End, an Else outside an If and an Exit loop outside a loop.

### Several workflows in one run

In the run dialog, **Add workflow** chains more workflows: each picked profile runs them one after the other in the same browser. Each workflow keeps its own settings and restarts from its own first step; variables saved by one carry over to the next (give the later workflow a variable of that name to use it); the run stops at the first workflow that fails. **Run again** on a run row runs the whole chain. From the API: `POST /workflow-runs` with `{"profile": ..., "workflows": [...], "variables": {...}}`; over MCP: `run_workflows`.

Workflows are JSON files in `workflows/`, one per workflow, editable with the REST API (`PUT /workflows/{name}`) as well. They contain what you typed while recording, **including passwords** (a password field only hides the value in the interface), so treat that folder like `camoufox_data/`. Replays drive the page through Playwright: a site that blocks automation may notice it.

## MCP: let AI agents drive the browser

FoxFlow ships an MCP server so Claude Code, Claude Desktop, Cursor, VS Code and others can manage profiles, act on pages (navigate, read, click, type, screenshot) and run your recorded workflows.

**Quickest:** click **Connect AI (MCP)** in the left sidebar of the desktop app or the web panel. It generates ready-to-paste configs for each AI app with your address and token.

![Connect AI (MCP)](docs/images/en/mcp-guide.png)

MCP is served over HTTP at `/mcp` on FoxFlow's own port, so it also works when FoxFlow runs on a VPS:

```bash
# Claude Code
claude mcp add --transport http foxflow http://127.0.0.1:8000/mcp
# Server with a token:
claude mcp add --transport http foxflow https://your-vps.example.com/mcp --header "Authorization: Bearer <token>"
```

```jsonc
// Cursor: ~/.cursor/mcp.json
{ "mcpServers": { "foxflow": { "url": "http://127.0.0.1:8000/mcp" } } }
```

Claude Desktop only launches local MCP servers: use `foxflow_mcp.py` on the same machine, or the `npx mcp-remote` bridge from another one. The Connect AI dialog generates both.

Then just ask, e.g. *"Open profile work-01, go to example.com and send me a screenshot"* or *"Run the daily-report workflow in profile work-01 and tell me if it failed"*.

| Group | Tools |
| --- | --- |
| Profiles | `list_profiles`, `get_profile`, `create_profile`, `update_profile`, `clone_profile`, `launch_profile`, `stop_profile`, `running_profiles` |
| Cookies & fingerprints | `export_cookies`, `import_cookies`, `get_fingerprint`, `reset_fingerprint`, `check_proxy`, `check_profile_ip` |
| Page | `browser_navigate`, `browser_back`, `browser_snapshot`, `browser_get_text`, `browser_click`, `browser_click_at`, `browser_type`, `browser_press`, `browser_wait_for`, `browser_screenshot`, `browser_evaluate` |
| Tabs | `browser_tabs`, `browser_tab_new`, `browser_tab_select`, `browser_tab_close` |
| Workflows | `list_workflows`, `get_workflow`, `run_workflow`, `run_workflows`, `workflow_run_status`, `stop_workflow_run` |

There is deliberately **no** delete tool, so an agent cannot wipe an account's cookies by mistake. Only `http`, `https` and `about:blank` can be opened; `file://` and `about:config` are blocked.

## Server mode and web panel

No desktop window: API + web panel only, browsers run hidden. Suited to a VPS that runs workflows around the clock.

```bash
python -m src.server                     # http://127.0.0.1:8000
python -m src.server --host 0.0.0.0      # exposed: FOXFLOW_API_TOKEN is required
```

Open `http://<host>:8000/` for the **web panel**: the same profile table, filters, bulk actions and workflow dialogs as the desktop app, plus a **remote screen view**. Click on the screenshot and type to record a workflow, log in or solve a captcha even when the browser runs hidden on a server.

| Web panel | Remote screen view |
| --- | --- |
| ![Web panel](docs/images/en/panel.png) | ![Remote screen view](docs/images/en/panel-viewer.png) |

**Security:** when listening on anything but `127.0.0.1`, the server **refuses to start** without `FOXFLOW_API_TOKEN` (24+ characters). The panel, the REST API and MCP share that token.

```bash
# Generate a random token
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

On a VPS, put the server behind an HTTPS reverse proxy (Caddy, Nginx) so the token is never sent in clear text. On a display-less Linux box, `FOXFLOW_HEADLESS=virtual` (needs `xvfb`) runs browsers on a virtual display, which behaves more like a normal desktop browser than plain headless.

Full deployment guide (Ubuntu, systemd, nginx, HTTPS; in Vietnamese): [docs/DEPLOY.md](docs/DEPLOY.md).

## Browser profiles

A profile is one isolated browser: its own data directory (cookies, logins, history), proxy, timezone, locale and device fingerprint. Workflows and agents always act inside a profile.

![Create profile dialog](docs/images/en/profile-dialog.png)

### Timezone, locale and Check IP

By default, every Camoufox launch looks up the exit IP (through the profile's proxy) and sets the timezone, locale, geolocation and WebRTC IP from it. Worth knowing:

- **The automatic locale is drawn at random on every launch**, weighted by how many people speak each language in the IP's country. A French IP gives `fr-FR` roughly 60% of the time and `en-FR`, `es-FR`… otherwise. Pin the locale per profile when a site should see the same language every session.
- **GeoIP databases disagree.** Cloudflare may place an IP in one country and Google in another, and Camoufox may pick a same-offset timezone with a different name (a Vietnamese IP gets `Asia/Bangkok` rather than `Asia/Ho_Chi_Minh`).
- **Datacenter IPs get captchas** on many sites whatever the browser looks like, which breaks unattended runs.

The profile dialog has **Timezone** (IANA name, e.g. `Asia/Ho_Chi_Minh`) and **Locale** (e.g. `vi-VN`) fields; blank means follow the IP. **Check IP** resolves the exit IP through the proxy, compares it with Cloudflare, ipinfo and ip-api, and warns about country or timezone mismatches, datacenter IPs, proxies that leave over different IPv4/IPv6 addresses, and a locale left on random.

### Chrome engine (experimental)

Besides Camoufox (Firefox), a profile can run on the **Chrome** engine: a Chromium build with fingerprint spoofing patched in C++ ([fingerprint-chromium](https://github.com/adryfish/fingerprint-chromium), BSD-3 license). Pick it in **Engine** when creating a profile; it cannot be changed afterwards. The browser build (~140-190 MB depending on the OS, fetched from fingerprint-chromium's GitHub releases and verified by SHA-256) is downloaded in the background as soon as the first Chrome profile is created, or on launch if it is still missing; progress shows in the log. To fetch it ahead of time: `python -m chrome_engine fetch`.

Pick the OS of the machine running FoxFlow: a persona of another OS leaks the machine's fonts, and a Linux persona on Windows/macOS is refused because WebGL reveals the real GPU. Supported: Windows x64, macOS Apple Silicon, Linux x64 (untested). Details and test results (in Vietnamese): [chrome_engine/README.md](chrome_engine/README.md).

### Cookies, fingerprints and cloning

![Cookies & fingerprint](docs/images/en/cookies.png)

Click the cookie button on a profile row to open **Cookies & fingerprint**. These need the profile's browser stopped, because FoxFlow opens the profile headless to read and write cookies; if it is running, FoxFlow offers to stop it first. Renaming, deleting and cloning with data do the same.

- Cookies export/import as Cookie-Editor / EditThisCookie JSON and Netscape `cookies.txt` (yt-dlp, curl, wget). Imported session cookies are given a one-year lifetime; otherwise the browser would discard them when it closes.
- "New fingerprint" deletes the stored fingerprint so the next launch presents a different device. Changing a profile's OS also regenerates it.
- **Clone** (the copy button on a profile row) makes new profiles with the same settings: set **Copies** to make several at once, named from the base name with -1, -2... (numbers in use are skipped). Each copy always gets a new fingerprint. Under **Also copy**, tick what comes along: **cookies** (logged-in sessions), **history and bookmarks**, **site data** (localStorage, IndexedDB, site permissions), **saved passwords**, **open tabs** (these need the profile stopped), and **this profile's workflows**: each copy gets its own, named `<workflow>-<new profile>`. Caches, locks, other settings and an unsaved recording are never copied. With cookies copied, sites see the same logins on a new device, which some treat as a new sign-in.
- **Profile export/import** as ZIP, with or without browser data, moves profiles between machines. The fingerprint always travels with the profile.

## Configuration

Everything is optional. To override defaults, copy `.env.example` to `.env`.

| Variable | Default | Meaning |
| --- | --- | --- |
| `FOXFLOW_LANG` | `en` | UI language: `en` or `vi` |
| `FOXFLOW_PROFILES_FILE` | `profiles.json` | Profile list file |
| `FOXFLOW_DATA_DIR` | `camoufox_data` | Data directory, one subdirectory per profile |
| `FOXFLOW_LOG_DIR` | `logs` | Log directory |
| `FOXFLOW_LOG_LEVEL` | `INFO` | Log level |
| `FOXFLOW_PROXY_TIMEOUT` | `10` | Proxy check timeout (seconds) |
| `FOXFLOW_LAUNCH_TIMEOUT` | `90` | How long the API waits for a browser to finish launching (seconds) |
| `FOXFLOW_HEADLESS` | `false` (`true` in server mode) | Hidden browsers: `true`, `false` or `virtual` (Linux + Xvfb) |
| `FOXFLOW_RESTORE_TABS` | `true` | Reopen the tabs from the previous run |
| `FOXFLOW_WORKFLOWS_DIR` | `workflows` | Saved workflows, one JSON file each |
| `FOXFLOW_OPENAI_API_KEY` | *(empty)* | Key for workflow AI text steps; overrides the one in the AI settings and is never saved |
| `FOXFLOW_OPENAI_BASE_URL` | `https://api.openai.com/v1` | Default base URL of an OpenAI-compatible API |
| `FOXFLOW_OPENAI_MODEL` | `gpt-4o-mini` | Default model |
| `FOXFLOW_AI_SETTINGS_FILE` | `ai_settings.json` | Where the AI settings (and key) are saved |
| `FOXFLOW_HTTP_PROXY` | *(empty: direct)* | Proxy for FoxFlow's own internet requests, e.g. `http://host:port` or `http://user:pass@host:port`. See [Network and proxy](#network-and-proxy) |
| `FOXFLOW_API_TOKEN` | *(empty)* | Token for the API, web panel and MCP. Required when the API listens beyond `127.0.0.1` |
| `FOXFLOW_API_HOST` | `127.0.0.1` | API host |
| `FOXFLOW_API_PORT` | `8000` | API port |

The old `FOXPROFILE_*` names still work; a `FOXFLOW_*` variable wins when both are set.

### Network and proxy

FoxFlow's own internet requests are the AI text steps, the Chrome engine and GeoIP downloads, and the exit-IP / **Check IP** lookups of profiles that have no proxy of their own. They go **direct** unless you set `FOXFLOW_HTTP_PROXY`; the system proxy and `HTTP(S)_PROXY` are ignored. Requests to FoxFlow's own API and to the browsers on `127.0.0.1` never use a proxy.

If this machine reaches the internet only through a proxy (a company network, for example), add it to `.env` and restart FoxFlow:

```bash
FOXFLOW_HTTP_PROXY=http://host:port
# or with a login
FOXFLOW_HTTP_PROXY=http://user:pass@host:port
```

How to tell you need it: the startup log says *"Internet requests go direct"*, and AI steps, the Chrome engine download, Check IP or launching a profile without a proxy fail with *"no internet connection"* or *"Cannot reach..."*. Those errors end with a reminder to set `FOXFLOW_HTTP_PROXY`, and **AI settings** shows which route is in use. `python -m camoufox fetch` is not part of FoxFlow: behind a proxy, run it with `HTTPS_PROXY` set in that terminal.

This setting does not change what the browsers use: each profile's traffic goes through that profile's own proxy.

### Proxy format

`host:port`, `http://host:port`, `https://...`, `socks4://...`, `socks5://...`, optionally with `user:pass@`. The provider format `host:port:user:pass` works too. Blank means a direct connection.

### Data layout

```text
profiles.json                                  profile list (name, engine, proxy, OS, timezone, locale)
camoufox_data/<profile>/                       browser data: cookies, history, localStorage
camoufox_data/<profile>/fingerprint.json       device fingerprint (Camoufox engine)
camoufox_data/<profile>/chrome_persona.json    device fingerprint (Chrome engine)
camoufox_data/<profile>/tabs.json              tabs to reopen on next launch
camoufox_data/<profile>/recording.json         steps of the recording in progress or not saved yet
workflows/<workflow>.json                      saved workflows: steps, delays, checks, retries
ai_settings.json                               AI settings for AI text steps, with the API key
logs/foxflow_YYYYMMDD.log                      daily log
```

> [!WARNING]
> `camoufox_data/` holds the login cookies of every account, and `workflows/` what was typed while recording, passwords included. Never commit or share them.

## REST API

Prefix `/api/v1`. The full reference is at `/docs` while the app is running.

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | Health check |
| `POST` | `/browser/{name}/record/start` · `/record/stop` | Start recording; stop it, saving it as a workflow with `{"save_as": "name"}` or throwing it away with `{"discard": true}` |
| `GET` | `/browser/{name}/record` · `/recordings` | Recording state of a profile (`draft` = recorded but not saved) / of every profile |
| `GET` / `POST` | `/workflows` | List / create workflows |
| `GET` / `PUT` / `DELETE` | `/workflows/{name}` | Read / save (steps, delays, typing speed, checks, retries) / delete a workflow |
| `POST` | `/workflows/{name}/run` | Replay it in a profile: `{"profile": "name", "variables": {}}`, launching the browser if needed (202) |
| `POST` | `/workflow-runs` | Run several workflows one after the other in a profile: `{"profile": "name", "workflows": ["a", "b"], "variables": {}}` (202) |
| `GET` / `POST` | `/workflow-runs` · `/workflow-runs/{profile}` · `/workflow-runs/{profile}/stop` | Runs (`?log=false` leaves out the log lines); one profile's current or last run (status, step, attempt, restarts, log); stop it |
| `GET` / `PUT` | `/ai/settings` | AI settings (the key only as a hint) / save them (`api_key` omitted keeps it, `""` removes it) |
| `POST` | `/ai/test` | Send one prompt with the saved AI settings |
| `POST` | `/browser/{name}/page/navigate` · `back` | Open a URL in the active tab, go back |
| `GET` | `/browser/{name}/page/snapshot` · `text` | Accessibility tree of the page (for picking selectors), page text |
| `POST` | `/browser/{name}/page/click` · `type` · `press` · `wait` | Click, type, press a key, wait for an element (Playwright selectors) |
| `POST` | `/browser/{name}/page/click-at` · `keyboard` | Click at coordinates, type into the focused element |
| `GET` | `/browser/{name}/page/screenshot` | PNG of the tab (`?format=json` for base64) |
| `POST` | `/browser/{name}/page/evaluate` | Run JavaScript |
| `GET` / `POST` | `/browser/{name}/page/tabs` | List tabs / open a new tab |
| `POST` / `DELETE` | `/browser/{name}/page/tabs/{index}/select` · `/page/tabs/{index}` | Select / close a tab |
| `GET` | `/browser` | Running profiles |
| `GET` | `/browser/{name}/status` | Whether the profile is running |
| `POST` | `/browser/{name}/launch` | Launch and wait until ready or failed (409 if already running or busy) |
| `POST` | `/browser/{name}/stop` | Stop |
| `GET` / `POST` | `/profiles` | List / create profiles |
| `GET` / `PATCH` / `DELETE` | `/profiles/{name}` | Read / update / delete a profile (`engine` cannot change) |
| `POST` | `/profiles/{name}/clone` | Clone: `{"name": "new-name", "count": 1, "copy": ["cookies", "workflows"]}`; with `count` > 1 (up to 50) the names are `new-name-1`, `new-name-2`...; `copy` takes `cookies`, `history`, `site_data`, `passwords`, `tabs` (profile stopped) and `workflows`; each copy gets a new fingerprint |
| `GET` | `/profiles/{name}/data-dir` | Path of the profile's data directory |
| `POST` | `/profiles/{name}/export` | Export a profile to ZIP |
| `POST` | `/profiles/import` | Import a profile from ZIP |
| `GET` | `/profiles/{name}/cookies?format=json\|netscape` | Export cookies |
| `POST` | `/profiles/{name}/cookies` | Import cookies (`{"content": "<JSON or cookies.txt>"}`) |
| `GET` / `DELETE` | `/profiles/{name}/fingerprint` | Show / generate a new fingerprint |
| `GET` | `/profiles/{name}/ip-check` | Where Cloudflare/ipinfo/ip-api place the profile's exit IP, with mismatch warnings |
| `POST` | `/proxy/check` | Check a proxy |
| `POST` | `/proxy/geo-check` | Same as `ip-check` for an unsaved `{proxy, timezone, locale}` |
| `GET` | `/mcp/setup?base_url=...` | MCP configs for each AI app (used by the Connect AI dialog) |

With `FOXFLOW_API_TOKEN` set, every request except `/health` and `/info` needs `Authorization: Bearer <token>`.

Examples:

```bash
# Create a profile with a proxy. Add "engine": "chrome" for the Chrome engine (default "camoufox").
curl -X POST http://127.0.0.1:8000/api/v1/profiles \
  -H "Content-Type: application/json" \
  -d '{"name": "work-01", "os_type": "windows", "proxy": "socks5://user:pass@203.0.113.10:1080"}'

# Replay a recorded workflow in that profile (the browser is launched if needed)
curl -X POST http://127.0.0.1:8000/api/v1/workflows/daily-report/run \
  -H "Content-Type: application/json" \
  -d '{"profile": "work-01", "variables": {"date": "2026-10-26"}}'

# Follow the run: status, current step, attempts and log
curl http://127.0.0.1:8000/api/v1/workflow-runs/work-01
```

## Moving from FoxProfile

FoxFlow reads a FoxProfile installation as it is: run it from the same folder and your profiles, cookies, fingerprints and workflows are there.

- **Data is unchanged**: `profiles.json`, `camoufox_data/`, `workflows/` and `ai_settings.json` keep their names and format.
- **Environment variables** are now `FOXFLOW_*`. `FOXPROFILE_*` in an existing `.env` is still read, so nothing breaks; rename them when convenient.
- **The Chrome engine** reuses a build FoxProfile already downloaded instead of fetching it again.
- **Network**: FoxFlow no longer picks up the system proxy for its own requests. If you need one, set `FOXFLOW_HTTP_PROXY` (see [Network and proxy](#network-and-proxy)).
- **MCP**: the server is now called `foxflow` and the stdio launcher is `foxflow_mcp.py`. Re-add it in your AI apps (the Connect AI dialog generates the new config).
- **Renamed files**: `run_foxflow.bat`, `deploy/foxflow.service`, `deploy/nginx-foxflow.conf`, and logs are written to `logs/foxflow_YYYYMMDD.log`.
- **Web panel**: the saved language and token carry over; you stay logged in. It now opens on the Automation view; the profile table is under **Profiles**.

## Development

```bash
pip install -r requirements-dev.txt
ruff check src tests chrome_engine
ruff format --check src tests chrome_engine
pytest                  # real-browser tests skip unless the browsers are fetched
```

Project layout, code conventions and the PR process are in [CONTRIBUTING.md](CONTRIBUTING.md) (Vietnamese; issues and PRs in English are welcome). UI changes follow [DESIGN.md](DESIGN.md) and touch both the desktop app and the web panel. Release notes: [CHANGELOG.md](CHANGELOG.md).

## Contributing

Contributions of all kinds are welcome: bug reports, feature ideas, docs, translations and code.

- Bugs and ideas: open an [issue](https://github.com/vitbau246/foxflow/issues/new/choose) from a template.
- Code: read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.
- Security issues: **do not** open a public issue, see [SECURITY.md](SECURITY.md).
- Everyone taking part is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

Changes that concern FoxProfile's own code may be worth sending upstream to [chienbm98/foxprofile](https://github.com/chienbm98/foxprofile) as well.

## Responsible use

Automate only what you are allowed to. Many websites forbid bots, scraping or running several accounts in their terms of service, and running multiple accounts on one platform may violate the terms of Facebook, TikTok, Google, Shopee and others. Respect rate limits and other people's data. You are responsible for how you use this software.

## Based on FoxProfile

FoxFlow is a fork of **[FoxProfile](https://github.com/chienbm98/foxprofile)**, created by **[chienbm98](https://github.com/chienbm98)** and released under the MIT License. FoxProfile built the foundation FoxFlow stands on: browser profiles with persistent fingerprints, the Camoufox and Chrome engines, proxy and Check IP, cookie tools, the REST API, the MCP server, server mode with the web panel, and the desktop app and its design system.

FoxFlow renames the project, refocuses it on web automation (workflow recording and replay, variables, AI text steps) and continues its development. Versions up to 2.3.1 in the [changelog](CHANGELOG.md) are FoxProfile releases. If FoxProfile is useful to you, give [the original repository](https://github.com/chienbm98/foxprofile) a ⭐ or [buy its author a coffee](https://buymeacoffee.com/chienbm98).

## License

Released under the [MIT License](LICENSE). Copyright (c) 2026 chienbm98 (FoxProfile) and 2026 vitbau246 (FoxFlow).

## Acknowledgements

- [FoxProfile](https://github.com/chienbm98/foxprofile) by chienbm98, the project FoxFlow is based on.
- The [Camoufox](https://github.com/daijro/camoufox) browser by daijro.
- [fingerprint-chromium](https://github.com/adryfish/fingerprint-chromium) by adryfish for the Chrome engine (BSD-3).
- [Playwright](https://github.com/microsoft/playwright-python), which drives the browsers during replays.
- The [Be Vietnam Pro](https://github.com/bettergui/BeVietnamPro) and [JetBrains Mono](https://github.com/JetBrains/JetBrainsMono) fonts, SIL Open Font License (`src/assets/fonts/`).
