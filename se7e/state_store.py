import json
import time
from pathlib import Path

from .config import STATE_FILE

# If a session's own hooks never signal it stopped (terminal killed, laptop
# slept mid-session) — or a subagent/turn that legitimately runs long with
# no intermediate hook to refresh it (PreToolUse/PostToolUse aren't wired:
# confirmed live they cost ~0.7-1.5s per invocation, spawning the packaged
# binary fresh each time, which would add up fast across a tool-heavy
# session) — treat a tracked session as abandoned only after this long.
# Kept generous (24h) since the cost of guessing wrong in THIS direction (a
# still-running task shown active for a while after it should've gone
# stale) is smaller than the alternative: a genuinely abandoned session, or
# an unusually long real task, getting pruned mid-work and wrongly
# reported idle. A real phantom session still self-corrects eventually —
# just slower — or can be cleared manually in the meantime.
STALE_SECONDS = 86400

# Priority when multiple sessions (a second terminal, a dispatched
# subagent, ...) are tracked with different statuses at once — the single
# displayed dot has to pick ONE, so it shows whichever is most worth your
# attention: something actively running outranks something waiting on a
# decision, which outranks something merely idle waiting for your next
# message.
_STATUS_PRIORITY = ("trabalhando", "esperando decisao", "esperando voce")


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
    """Normalizes + prunes active_sessions into
    {session_id: {"status": str, "since": float}}.

    Older state files used simpler shapes with no per-session status: a
    dict of bare timestamps (from the abandoned-session fix), or before
    that a plain list of ids. Both are migrated here, borrowing the whole
    entry's own "status"/"since" as the best available guess, so an
    already-stale one doesn't get a free fresh timestamp just for having
    an old shape.
    """
    active = claude.get("active_sessions")
    fallback_status = claude.get("status", "trabalhando")
    fallback_since = claude.get("since", now)

    normalized = {}
    if isinstance(active, dict):
        for session_id, entry in active.items():
            if isinstance(entry, dict) and "since" in entry:
                normalized[session_id] = {
                    "status": entry.get("status", fallback_status),
                    "since": entry["since"],
                }
            elif isinstance(entry, (int, float)):
                normalized[session_id] = {"status": fallback_status, "since": entry}
    elif isinstance(active, list):
        for session_id in active:
            normalized[session_id] = {"status": fallback_status, "since": fallback_since}

    return {
        session_id: entry
        for session_id, entry in normalized.items()
        if now - entry["since"] <= STALE_SECONDS
    }


def _aggregate_status(active: dict) -> str:
    statuses = {entry["status"] for entry in active.values()}
    for candidate in _STATUS_PRIORITY:
        if candidate in statuses:
            return candidate
    return "parado"


def write_claude_status(status: str, path: Path = STATE_FILE) -> None:
    """Sets a status with no session attribution. Every real hook event
    today is attributed to a session_id via mark_session_active()/
    mark_session_inactive() instead (that's what read_claude_status()'s
    multi-session aggregation actually looks at) — this is kept for
    direct/manual use. Still preserves any active_sessions already
    tracked rather than wiping them, so it can't silently erase another
    session's bookkeeping if ever called mid-session."""
    data = read_all(path)
    now = time.time()
    active = _active_sessions(data.get("claude", {}), now)
    entry = {"status": status, "since": now}
    if active:
        entry["active_sessions"] = active
    data["claude"] = entry
    _write(data, path)


def mark_session_active(session_id: str, status: str, path: Path = STATE_FILE) -> None:
    """This session is doing something (working, or waiting on a decision
    or on you) — tracked by session_id, each with its OWN status, not a
    single shared status string: a dispatched subagent (or an entirely
    separate terminal session) fires the same global hooks, and each
    one's current status must be tracked independently so one session's
    "waiting on a permission decision" can't be silently overwritten by,
    or overwrite, another session's "actively working"."""
    data = read_all(path)
    now = time.time()
    active = _active_sessions(data.get("claude", {}), now)
    active[session_id] = {"status": status, "since": now}
    data["claude"] = {
        "active_sessions": active,
        "status": _aggregate_status(active),
        "since": now,
    }
    _write(data, path)


def mark_session_inactive(session_id: str, path: Path = STATE_FILE) -> None:
    """Stop/SessionEnd: this one session is done. Only reports "parado"
    once EVERY tracked session (main session + any subagents + any other
    terminal's session) has stopped — one finishing first must not mask
    another still active."""
    data = read_all(path)
    now = time.time()
    active = _active_sessions(data.get("claude", {}), now)
    active.pop(session_id, None)
    data["claude"] = {
        "active_sessions": active,
        "status": _aggregate_status(active),
        "since": now,
    }
    _write(data, path)


def read_claude_status(path: Path = STATE_FILE) -> dict:
    data = read_all(path)
    claude = data.get("claude", {"status": "parado", "since": 0})
    now = time.time()

    raw_active = claude.get("active_sessions")
    if isinstance(raw_active, (dict, list)):
        active = _active_sessions(claude, now)
        if active:
            return {"status": _aggregate_status(active), "since": claude.get("since", 0)}
        return {"status": "parado", "since": claude.get("since", 0)}

    if claude["status"] != "parado" and now - claude.get("since", 0) > STALE_SECONDS:
        return {"status": "parado", "since": claude.get("since", 0)}
    return claude
