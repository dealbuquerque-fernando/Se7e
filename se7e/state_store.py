import json
import time
from pathlib import Path

from .config import STATE_FILE

# If "Stop"/"SessionEnd" never fires (terminal killed mid-session), a "trabalhando"
# or "esperando voce" reading older than this is treated as abandoned, not live.
STALE_SECONDS = 600


def read_all(path: Path = STATE_FILE) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (ValueError, OSError):
        return {}


def _write(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(path)


def write_claude_status(status: str, path: Path = STATE_FILE) -> None:
    """Notification only (the one event left outside the active-session
    tracking below) — must preserve any active_sessions already tracked,
    or a Notification firing mid-session (e.g. a permission prompt) wipes
    that bookkeeping, and a subagent's Stop right after would then find no
    record of the still-running main session and wrongly report "parado"."""
    data = read_all(path)
    active_sessions = data.get("claude", {}).get("active_sessions")
    entry = {"status": status, "since": time.time()}
    if active_sessions:
        entry["active_sessions"] = active_sessions
    data["claude"] = entry
    _write(data, path)


def mark_session_active(session_id: str, status: str, path: Path = STATE_FILE) -> None:
    """SessionStart/UserPromptSubmit: this session is doing work. Tracked
    by session_id, not just a flat status string, because a dispatched
    subagent is its own Claude process firing the same global hooks —
    without this, the subagent's own Stop would wipe "trabalhando" back to
    "parado" while the main session is still actively waiting on it."""
    data = read_all(path)
    active = set(data.get("claude", {}).get("active_sessions", []))
    active.add(session_id)
    data["claude"] = {
        "active_sessions": sorted(active),
        "status": status,
        "since": time.time(),
    }
    _write(data, path)


def mark_session_inactive(session_id: str, path: Path = STATE_FILE) -> None:
    """Stop/SessionEnd: only report "parado" once EVERY tracked session
    (main session + any subagents) has stopped — a subagent finishing
    first must not mask the main session still working."""
    data = read_all(path)
    active = set(data.get("claude", {}).get("active_sessions", []))
    active.discard(session_id)
    data["claude"] = {
        "active_sessions": sorted(active),
        "status": "trabalhando" if active else "parado",
        "since": time.time(),
    }
    _write(data, path)


def read_claude_status(path: Path = STATE_FILE) -> dict:
    data = read_all(path)
    status = data.get("claude", {"status": "parado", "since": 0})
    if status["status"] != "parado" and time.time() - status.get("since", 0) > STALE_SECONDS:
        return {"status": "parado", "since": status.get("since", 0)}
    return status
