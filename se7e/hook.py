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
            status = _notification_status(payload.get("notification_type"))
            if status is None:
                return
            session_key = payload.get("session_id") or "unknown"
            state_store.mark_session_active(session_key, status)
            return

        status = status_for_event(event)
        if status is None:
            return

        if event in _ACTIVE_EVENTS or event in _INACTIVE_EVENTS:
            payload = _read_stdin_payload()
            session_key = payload.get("session_id") or "unknown"
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
