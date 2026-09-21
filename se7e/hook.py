import json
import sys
from pathlib import Path

try:
    from . import state_store
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from se7e import state_store

EVENT_STATUS = {
    "SessionStart": "trabalhando",
    "UserPromptSubmit": "trabalhando",
    "SubagentStart": "trabalhando",
    "Notification": "esperando voce",
    "Stop": "parado",
    "SessionEnd": "parado",
    "SubagentStop": "parado",
}

_ACTIVE_EVENTS = {"SessionStart", "UserPromptSubmit", "SubagentStart"}
_INACTIVE_EVENTS = {"Stop", "SessionEnd", "SubagentStop"}


def status_for_event(event: str):
    return EVENT_STATUS.get(event)


def _read_session_id() -> str:
    """Claude Code sends a JSON payload on stdin with a session_id — needed
    to tell a dispatched subagent's own hook firings apart from the main
    session's (both fire the same global hooks). Falls back to a fixed
    placeholder when stdin isn't real JSON (e.g. invoked directly with no
    stdin, like the tests do), degrading to the old single-session
    behavior instead of crashing."""
    try:
        payload = json.load(sys.stdin)
        session_id = payload.get("session_id")
        if session_id:
            return session_id
    except (json.JSONDecodeError, ValueError, OSError, AttributeError):
        pass
    return "unknown"


def main(event: str | None = None) -> None:
    if event is None:
        event = sys.argv[1] if len(sys.argv) > 1 else ""

    status = status_for_event(event)
    if status is None:
        return

    try:
        if event in _ACTIVE_EVENTS or event in _INACTIVE_EVENTS:
            session_key = _read_session_id()
            if event in ("SubagentStart", "SubagentStop"):
                # It's unconfirmed whether Claude Code's subagent hook
                # payload reuses the parent's own session_id or gives each
                # subagent a distinct one — a shared ":subagent" suffix
                # guarantees a subagent's Stop can never remove the plain
                # parent session_id entry either way.
                # ponytail: two subagents running in parallel under the
                # same session both map to this one key, so the first to
                # finish clears it early — upgrade to a per-dispatch id if
                # Claude Code's payload exposes one and this matters live.
                session_key = f"{session_key}:subagent"
            if event in _ACTIVE_EVENTS:
                state_store.mark_session_active(session_key, status)
            else:
                state_store.mark_session_inactive(session_key)
        else:
            state_store.write_claude_status(status)
    except OSError:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
