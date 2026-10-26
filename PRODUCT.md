# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

Two surfaces share one product: a desktop app built with Flet (Python, Flutter renderer; `src/ui/`) and a browser web panel served by the FastAPI server (`src/web/index.html`, one file, no build step). Neither follows iOS/Android native design language.

## Users

- **Operators automating repetitive web work**: back-office, marketing and support staff who do the same task in a browser many times a day. They record it once as a workflow, then replay it across profiles and check the run log.
- **Agencies and teams managing several accounts or clients**: each account lives in its own profile so logins, cookies and settings never mix; several people share one installation and the list must stay orderly and trustworthy.
- **Developers and AI-agent users** who drive FoxFlow through the REST API and MCP, often on a VPS; for them the UI is where they check state and step in by hand (log in, solve a captcha through the remote screen view).

## Product Purpose

FoxFlow is a free, open-source, self-hosted web automation tool. A task done once in a browser becomes a workflow: steps with delays, checks, retries, variables and optional AI-written text, replayed by the app, the REST API or an AI agent over MCP. Every run happens in an isolated browser profile with its own fingerprint, cookies, proxy, timezone and locale. Success means a user can record a task, replay it reliably across profiles and see at once which run failed and why. FoxFlow is based on FoxProfile by chienbm98 (https://github.com/chienbm98/foxprofile).

## Positioning

Open source (MIT), runs on the user's own machine or VPS, no account and no per-run pricing. Record-and-replay workflows with built-in checks and retries, a REST API and an MCP server so scripts and AI agents can drive the browsers. Two browser engines: Camoufox (Firefox, default) and an experimental Chrome engine (fingerprint-chromium).

## Operating Context

- Desktop: `python -m src.main` on Windows, macOS or Linux; the API runs alongside on `127.0.0.1:8000`.
- Server: `python -m src.server` on a VPS behind HTTPS; the web panel at `/` is token-protected and includes a remote screen view that accepts clicks and typing.
- Core tasks: record, edit and run a workflow and follow its run log; create/edit a profile (name, engine, OS, proxy, timezone, locale), launch/stop, bulk launch/stop/delete, search by name or proxy, check proxy, Check IP (exit IP vs Cloudflare/ipinfo/ip-api with warnings), cookie export/import (JSON, Netscape), new fingerprint, profile ZIP export/import, connect an AI agent over MCP, read the activity log.
- Sessions are long; users scan many cards at once and repeat the same actions many times a day.

## Capabilities and Constraints

- Profile fields: name, engine (`camoufox` | `chrome`, fixed after creation), OS (`windows` | `macos` | `linux`), proxy (`[scheme://][user:pass@]host:port` or `host:port:user:pass`), optional pinned timezone (IANA) and locale.
- Cookie and fingerprint operations require the profile's browser to be stopped.
- Desktop UI is limited to what Flet 1.0 controls can render; the web panel is a single static HTML file with inline CSS/JS and no external requests at runtime (it must work offline and on a locked-down VPS).
- All UI strings live in `src/core/strings.py` (desktop) and the panel's own dictionary, in both `vi` and `en`.

## Brand Commitments

- Name: **FoxFlow**. Keep it.
- Logo: the fox icon in `src/assets/icon.png` (and `icon.ico`), inherited from FoxProfile. Keep it.
- Language: English is the default UI language, with Vietnamese available.
- Terminology: keep industry terms in English inside Vietnamese copy (profile, proxy, cookie, fingerprint, engine, timezone, locale, headless, API, MCP...) because users read them more easily than translations.

## Evidence on Hand

- Screenshots of the current UI (taken before the rename, still titled FoxProfile): `docs/images/en/` and `docs/images/main.png` (desktop), `panel.png`, `panel-viewer.png`, `cookies.png`, `mcp-guide.png` (web panel), `profile-dialog.png` (desktop).
- README (vi/en) describing every feature. No user testimonials, usage numbers or customer names exist; do not invent them.

## Product Principles

1. Speed for repeated work: the most frequent actions (launch, stop, find a profile) take one click and are always in the same place.
2. State at a glance: whether a profile is running, which proxy/IP and device it presents, and anything that would leak (geo mismatch, datacenter IP) must be visible without opening it.
3. Safety over convenience for destructive or leaking actions: deleting profiles, cookies and credentials needs a clear confirmation; credentials are never shown in full.
4. One product, two surfaces: desktop and web panel offer the same tasks with the same vocabulary.
5. Honest about limits: experimental features (Chrome engine) and failures are labeled plainly, not hidden.
