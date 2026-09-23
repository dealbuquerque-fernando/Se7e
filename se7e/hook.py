import json
import sys
import time
from pathlib import Path

try:
    from . import state_store
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from se7e import state_store

# Temporary diagnostic trail for a reported bug: the "esperando voce" white
# sometimes doesn't show up even well past its usual ~60s delay. Every hook
# invocation appends one line here with what it received and what it did,
# plus active_sessions right after — so a stuck phantom session (from a
# terminal killed uncleanly, never getting its own Stop/SessionEnd) or a
# Notification that simply never arrives shows up directly in the log,
# instead of only being guessable from the final aggregated status.
# Remove this once the report is resolved.
_LOG_MAX_LINES = 500


def _log(event, session_key, notification_type, status, path: Path | None = None) -> None:
    try:
        log_path = path or (state_store.STATE_FILE.parent / "hook_debug.log")
        # Explicit path, not read_all()'s own default: that default is bound
        # to STATE_FILE's value at state_store.py's import time, so it
        # wouldn't follow a STATE_FILE reassigned afterward (the same class
        # of bug documented on mark_session_active's own path default).
        snapshot = state_store.read_all(state_store.STATE_FILE).get("claude", {}).get("active_sessions", {})
        entry = {
            "ts": time.time(),
            "event": event,
            "session_key": session_key,
            "notification_type": notification_type,
            "status": status,
            "active_sessions": snapshot,
        }
        lines = []
        if log_path.exists():
            lines = log_path.read_text().splitlines()
        lines.append(json.dumps(entry))
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("\n".join(lines[-_LOG_MAX_LINES:]) + "\n")
    except OSError:
        pass

EVENT_STATUS = {
    "SessionStart": "trabalhando",
    "UserPromptSubmit": "trabalhando",
    "SubagentStart": "trabalhando",
    "Stop": "parado",
    "SessionEnd": "parado",
    "SubagentStop": "parado",
}

_ACTIVE_EVENTS = {"SessionStart", "UserPromptSubmit", "SubagentStart"}
_INACTIVE_EVENTS = {"Stop", "SessionEnd", "SubagentStop"}

# Notification fires for many different situations — its stdin payload
# carries a notification_type telling them apart. Confirmed live (captured
# real payloads): "Claude needs your permission" -> permission_prompt,
# "Claude is waiting for your input" -> idle_prompt. Only some of these
# actually mean "Claude needs something from you right now" (a decision)
# vs. "just finished, waiting for your next message" vs. purely
# informational ones that shouldn't touch the displayed status at all.
_DECISION_NOTIFICATION_TYPES = {
    "permission_prompt",
    "agent_needs_input",
    "elicitation_dialog",
    "elicitation_url_dialog",
}
_IDLE_NOTIFICATION_TYPES = {"idle_prompt"}
# Deliberately NOT mapped to anything (informational, not a waiting
# state): elicitation_complete, agent_completed, auth_success,
# quota_auto_resume_*, and anything else Claude Code might add.


def status_for_event(event: str):
    return EVENT_STATUS.get(event)


def _read_stdin_payload() -> dict:
    """Claude Code sends a JSON payload on stdin with session_id (needed
    to tell a dispatched subagent's own hook firings apart from the main
    session's, since both fire the same global hooks) and, for
    Notification, notification_type. Falls back to an empty dict when
    stdin isn't real JSON (e.g. invoked directly with no stdin, like the
    tests do), so callers degrade gracefully instead of crashing."""
    try:
        payload = json.load(sys.stdin)
        if isinstance(payload, dict):
            return payload
    except (json.JSONDecodeError, ValueError, OSError, AttributeError):
        pass
    return {}


def _notification_status(notification_type):
    if notification_type in _DECISION_NOTIFICATION_TYPES:
        return "esperando decisao"
    if notification_type in _IDLE_NOTIFICATION_TYPES:
        return "esperando voce"
    return None  # informational or unrecognized type — ignore


def main(event: str | None = None) -> None:
    if event is None:
        event = sys.argv[1] if len(sys.argv) > 1 else ""

    try:
        if event == "Notification":
            payload = _read_stdin_payload()
            notification_type = payload.get("notification_type")
            status = _notification_status(notification_type)
            session_key = payload.get("session_id") or "unknown"
            if status is None:
                _log(event, session_key, notification_type, None)
                return
            state_store.mark_session_active(session_key, status)
            _log(event, session_key, notification_type, status)
            return

        status = status_for_event(event)
        if status is None:
            _log(event, None, None, None)
            return

        if event in _ACTIVE_EVENTS or event in _INACTIVE_EVENTS:
            payload = _read_stdin_payload()
            session_key = payload.get("session_id") or "unknown"
            if event in ("SubagentStart", "SubagentStop"):
                # agent_id is a required field on SubagentStart/SubagentStop
                # (code.claude.com/docs/en/hooks) — a unique id per subagent
                # dispatch, unlike session_id, which every subagent in the
                # same session shares. Confirmed live: a single subagent
                # dispatch produced one SubagentStart but THREE
                # SubagentStop firings sharing the old flat ":subagent"
                # key — the first one incorrectly cleared the tracked
                # session while the real subagent was still running,
                # showing "parado" (gray) mid-task. Keying on agent_id
                # instead isolates each dispatch, so one clearing early
                # can't affect another. Falls back to the old flat suffix
                # only if agent_id is ever missing (should not happen per
                # the docs, but degrading to the previous behavior beats
                # crashing on an unexpected payload shape).
                agent_id = payload.get("agent_id")
                session_key = f"{session_key}:{agent_id}" if agent_id else f"{session_key}:subagent"
            if event in _ACTIVE_EVENTS:
                state_store.mark_session_active(session_key, status)
            else:
                state_store.mark_session_inactive(session_key)
            _log(event, session_key, None, status)
        else:
            state_store.write_claude_status(status)
            _log(event, None, None, status)
    except OSError:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
