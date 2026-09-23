# Se7e

A tiny tray/menu-bar app for **Windows and macOS** that shows your Claude
Code and Codex usage at a glance — no need to run `/usage` or dig through a
terminal to know whether you're about to hit a rate limit, or whether Claude
just finished and is waiting on you.

Three ways to see it, pick whichever fits your workflow:

- A **tray/menu-bar icon** that changes color with activity and blinks while
  something's actually happening
- A compact **floating pill**, always on top, that docks near your
  taskbar/menu bar and can be dragged anywhere
- A fuller **panel** with live 5-hour and weekly usage bars for both
  providers

## Status at a glance

The dot/icon color tells you what's going on without opening anything:

| Color | Meaning |
|---|---|
| 🟢 green (Claude) / 🔵 blue (Codex), blinking | actively working |
| 🟡 amber, blinking | needs a decision from you (permission prompt, a question, etc.) |
| ⚪ white, solid | just finished and is waiting for your next message |
| ⚫ gray | idle, nothing going on |
| 🔴 red | not connected (no valid credentials found) |

The "needs a decision" and "just waiting" states are deliberately different
colors — a permission prompt is time-sensitive, an idle session isn't, and
it's easy to confuse the two if they look the same at a glance.

## How it works

- **Claude**: a handful of Claude Code hooks (`SessionStart`,
  `UserPromptSubmit`, `Notification`, `Stop`, `SessionEnd`, `SubagentStart`,
  `SubagentStop`) are wired into `~/.claude/settings.json` automatically on
  install. Each one updates a small local state file that the tray app polls
  — multiple concurrent sessions (extra terminals, dispatched subagents) are
  tracked independently, and the busiest one wins when they disagree.
- **Codex**: the CLI has no equivalent hook for "waiting on your approval",
  so status is inferred by polling Codex's own local session history
  instead — busy while a turn is in progress, idle a little while after the
  last one finished.
- **Usage percentages** are fetched periodically from each provider's own
  usage endpoint, with the OAuth token refreshed automatically before it
  expires so the numbers don't just silently stop updating.

## Install

Grab the latest build from [Releases](https://github.com/dealbuquerque-fernando/Se7e/releases):

- **Windows** — download `Se7e-Setup-X.Y.Z.exe` and run it. Per-user install,
  no admin needed. Wires Claude Code's hooks automatically and offers to
  launch on startup.
- **macOS** — download `Se7e.pkg` and run it. Installs to `/Applications`
  and wires Claude Code's hooks the same way. The build is unsigned (fine
  for personal use), so the first launch needs a right-click → Open, or an
  approval in System Settings → Privacy & Security.

### From source

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m se7e.app
```

Requires Python 3.11+. Dependencies: PySide6, pystray, Pillow (see
`requirements.txt`).

## Settings

Open the panel (tray icon click) or right-click the tray icon for the full
menu. Settings covers:

- Language — Portuguese or English
- Theme — dark or light
- Floating pill orientation — horizontal or vertical
- Launch at login
- Uninstall — removes the Claude Code hooks and login item cleanly

## Uninstalling

Use the in-app Settings → Uninstall button, or the Windows uninstaller —
both remove the Claude Code hooks and startup entry before the app itself
is removed, so nothing is left behind in `~/.claude/settings.json`.

## Development

```bash
pip install -r requirements-dev.txt
pytest
```

Packaging lives in `packaging/`: `se7e.spec` (PyInstaller, both platforms),
`build_pkg.sh` (macOS `.pkg`), `installer.iss` (Windows, via Inno Setup).

## License

MIT — see [LICENSE](LICENSE).
