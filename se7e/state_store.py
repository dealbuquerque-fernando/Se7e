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


def _active_sessions(claude: dict, now: float) -> dict:
    """Normalizes + prunes active_sessions into {session_id: last_active}.

    Older state files store it as a plain list (no per-session timestamp,
    from before this existed) — those entries default to `claude["since"]`
    (the best available guess at when they were last touched) so a
    genuinely old one can still age out immediately instead of getting a
    free fresh timestamp just for having the old shape.

    Pruning here (not just in read_claude_status) matters: a session
    whose Stop/SessionEnd never fires (terminal killed, laptop slept
    mid-session) would otherwise sit in this dict forever, since nothing
    else ever removes it — and because "since" used to be one shared
    timestamp for the whole entry, ANY other session's real activity kept
    resetting it, masking the stale one from ever being noticed. Per-session
    timestamps fix that: this phantom entry now ages out on its own.
    """
    active = claude.get("active_sessions")
    if isinstance(active, dict):
        pass
    elif isinstance(active, list):
        fallback = claude.get("since", now)
        active = {sid: fallback for sid in active}
    else:
        active = {}
    return {sid: ts for sid, ts in active.items() if now - ts <= STALE_SECONDS}


def write_claude_status(status: str, path: Path = STATE_FILE) -> None:
    """Notification only (the one event left outside the active-session
    tracking below) — must preserve any active_sessions already tracked,
    or a Notification firing mid-session (e.g. a permission prompt) wipes
    that bookkeeping, and a subagent's Stop right after would then find no
    record of the still-running main session and wrongly report "parado"."""
    data = read_all(path)
    now = time.time()
    active = _active_sessions(data.get("claude", {}), now)
    entry = {"status": status, "since": now}
    if active:
        entry["active_sessions"] = active
    data["claude"] = entry
    _write(data, path)


def mark_session_active(session_id: str, status: str, path: Path = STATE_FILE) -> None:
    """SessionStart/UserPromptSubmit: this session is doing work. Tracked
    by session_id (each with its own last-active time), not just a flat
    status string, because a dispatched subagent is its own Claude process
    firing the same global hooks — without this, the subagent's own Stop
    would wipe "trabalhando" back to "parado" while the main session is
    still actively waiting on it."""
    data = read_all(path)
    now = time.time()
    active = _active_sessions(data.get("claude", {}), now)
    active[session_id] = now
    data["claude"] = {
        "active_sessions": active,
        "status": status,
        "since": now,
    }
    _write(data, path)


def mark_session_inactive(session_id: str, path: Path = STATE_FILE) -> None:
    """Stop/SessionEnd: only report "parado" once EVERY tracked session
    (main session + any subagents) has stopped — a subagent finishing
    first must not mask the main session still working."""
    data = read_all(path)
    now = time.time()
    active = _active_sessions(data.get("claude", {}), now)
    active.pop(session_id, None)
    data["claude"] = {
        "active_sessions": active,
        "status": "trabalhando" if active else "parado",
        "since": now,
    }
    _write(data, path)


def read_claude_status(path: Path = STATE_FILE) -> dict:
    data = read_all(path)
    claude = data.get("claude", {"status": "parado", "since": 0})
    now = time.time()

    raw_active = claude.get("active_sessions")
    if isinstance(raw_active, (dict, list)):
        # At least one fresh session -> report the status a hook actually
        # set (usually "trabalhando", but a Notification mid-session can
        # leave it "esperando voce" — don't clobber that back to
        # "trabalhando" just because a session is still tracked active).
        if _active_sessions(claude, now):
            return claude
        return {"status": "parado", "since": claude.get("since", 0)}

    if claude["status"] != "parado" and now - claude.get("since", 0) > STALE_SECONDS:
        return {"status": "parado", "since": claude.get("since", 0)}
    return claude
