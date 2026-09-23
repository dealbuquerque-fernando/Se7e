from pathlib import Path
import os
import sys
import subprocess
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from se7e import hook
from se7e import state_store


def test_known_events_map_to_expected_status():
    assert hook.status_for_event("SessionStart") == "trabalhando"
    assert hook.status_for_event("UserPromptSubmit") == "trabalhando"
    assert hook.status_for_event("Stop") == "parado"
    assert hook.status_for_event("SessionEnd") == "parado"


def test_notification_has_no_single_fixed_status():
    """Notification's status depends on its notification_type payload
    field (see the tests below), not a fixed EVENT_STATUS entry."""
    assert hook.status_for_event("Notification") is None


def _run_notification(notification_type, session_id="sess-1"):
    """Runs hook.main("Notification") with a fake stdin payload, capturing
    the (session_id, status) pair it would pass to mark_session_active.

    Mocks the function itself rather than redirecting state_store.STATE_FILE:
    mark_session_active's own `path` default parameter is bound to the
    real STATE_FILE once, at state_store.py's import time — reassigning
    state_store.STATE_FILE later (as a prior version of this test tried)
    doesn't reach it, the same class of bug the real usage_claude.py
    CREDENTIALS_PATH default-argument issue was."""
    calls = []
    original_read = hook._read_stdin_payload
    original_mark_active = state_store.mark_session_active
    original_log = hook._log
    hook._read_stdin_payload = lambda: {"session_id": session_id, "notification_type": notification_type}
    state_store.mark_session_active = lambda sid, status, path=None: calls.append((sid, status))
    hook._log = lambda *a, **k: None  # avoid writing the real hook_debug.log during tests
    try:
        hook.main("Notification")
    finally:
        hook._read_stdin_payload = original_read
        state_store.mark_session_active = original_mark_active
        hook._log = original_log
    return calls


def test_notification_permission_prompt_sets_esperando_decisao():
    assert _run_notification("permission_prompt") == [("sess-1", "esperando decisao")]


def test_notification_agent_needs_input_sets_esperando_decisao():
    assert _run_notification("agent_needs_input") == [("sess-1", "esperando decisao")]


def test_notification_elicitation_dialog_sets_esperando_decisao():
    assert _run_notification("elicitation_dialog") == [("sess-1", "esperando decisao")]


def test_notification_elicitation_url_dialog_sets_esperando_decisao():
    assert _run_notification("elicitation_url_dialog") == [("sess-1", "esperando decisao")]


def test_notification_idle_prompt_sets_esperando_voce():
    assert _run_notification("idle_prompt") == [("sess-1", "esperando voce")]


def test_notification_informational_types_are_ignored():
    """agent_completed, auth_success, elicitation_complete, and
    quota_auto_resume_* are informational, not a waiting state — must not
    touch the tracked status at all."""
    for notification_type in ("agent_completed", "auth_success", "elicitation_complete", "quota_auto_resume_5h"):
        assert _run_notification(notification_type) == [], f"{notification_type} should not mark any session active"


def test_tool_use_events_are_ignored():
    assert hook.status_for_event("PreToolUse") is None
    assert hook.status_for_event("PostToolUse") is None
    assert hook.status_for_event("") is None
    assert hook.status_for_event("something-unknown") is None


def test_hook_invoked_as_bare_script_exits_zero_and_writes_status():
    """Test that hook.py can be invoked as a bare script and writes state correctly."""
    # hook.py always writes to config.STATE_FILE (it takes no path argument —
    # that's the real contract Claude Code invokes it under), so isolating
    # this subprocess means giving it its own throwaway home directory
    # instead, via the same env var config.APP_DIR reads (HOME on macOS/
    # Linux, LOCALAPPDATA on Windows) — not the real one, which a previous
    # version of this test wrote "trabalhando" into directly and never
    # cleaned up, leaving the real app stuck showing a live status.
    with tempfile.TemporaryDirectory() as home_dir:
        home = Path(home_dir)
        env = dict(os.environ, HOME=str(home), LOCALAPPDATA=str(home))

        repo_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, str(repo_root / "se7e" / "hook.py"), "SessionStart"],
            cwd=repo_root,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Verify exit code is 0 (never crashes)
        assert result.returncode == 0, f"Exit code {result.returncode}, stderr: {result.stderr}"

        # Mirrors config.py's own APP_DIR logic, rooted at the throwaway
        # home above instead of the real one.
        app_dir = (
            home / "Library" / "Application Support" / "se7e"
            if sys.platform == "darwin"
            else home / "se7e"
        )
        data = state_store.read_all(app_dir / "state.json")
        assert data.get("claude", {}).get("status") == "trabalhando"


if __name__ == "__main__":
    test_known_events_map_to_expected_status()
    test_notification_has_no_single_fixed_status()
    test_notification_permission_prompt_sets_esperando_decisao()
    test_notification_agent_needs_input_sets_esperando_decisao()
    test_notification_elicitation_dialog_sets_esperando_decisao()
    test_notification_elicitation_url_dialog_sets_esperando_decisao()
    test_notification_idle_prompt_sets_esperando_voce()
    test_notification_informational_types_are_ignored()
    test_tool_use_events_are_ignored()
    test_hook_invoked_as_bare_script_exits_zero_and_writes_status()
    print("OK")
