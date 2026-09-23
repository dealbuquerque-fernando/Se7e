import json
import tempfile
import time
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from se7e import state_store


def test_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "state.json"
        state_store.write_claude_status("trabalhando", path=path)
        result = state_store.read_claude_status(path=path)
        assert result["status"] == "trabalhando"
        assert result["since"] > 0


def test_missing_file_returns_default():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "does-not-exist.json"
        result = state_store.read_claude_status(path=path)
        assert result["status"] == "parado"


def test_corrupt_file_returns_default():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "state.json"
        path.write_text("{not valid json")
        result = state_store.read_claude_status(path=path)
        assert result["status"] == "parado"


def test_stale_working_status_falls_back_to_idle():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "state.json"
        stuck_since = time.time() - state_store.STALE_SECONDS - 1
        path.write_text(json.dumps({"claude": {"status": "trabalhando", "since": stuck_since}}))
        result = state_store.read_claude_status(path=path)
        assert result["status"] == "parado"


def test_fresh_working_status_stays_working():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "state.json"
        state_store.write_claude_status("trabalhando", path=path)
        result = state_store.read_claude_status(path=path)
        assert result["status"] == "trabalhando"


def test_subagent_stopping_does_not_mask_main_session_still_working():
    """The bug this whole active-session-set design exists to fix: a
    dispatched subagent fires the same global Stop hook as the main
    session — its own Stop must not report "parado" while the main
    session (a different session_id) is still active."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "state.json"
        state_store.mark_session_active("main-session", "trabalhando", path=path)
        state_store.mark_session_active("subagent-1:subagent", "trabalhando", path=path)
        state_store.mark_session_inactive("subagent-1:subagent", path=path)
        result = state_store.read_claude_status(path=path)
        assert result["status"] == "trabalhando"


def test_last_session_stopping_reports_idle():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "state.json"
        state_store.mark_session_active("main-session", "trabalhando", path=path)
        state_store.mark_session_inactive("main-session", path=path)
        result = state_store.read_claude_status(path=path)
        assert result["status"] == "parado"


def test_notification_mid_session_does_not_wipe_active_sessions():
    """write_claude_status (a manual/direct-use path — real Notification
    events go through mark_session_active now, see hook.py) must still
    not clobber active_sessions if ever called mid-session, or a
    subagent's Stop right after would find no record of the still-running
    main session and wrongly report "parado"."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "state.json"
        state_store.mark_session_active("main-session", "trabalhando", path=path)
        state_store.write_claude_status("esperando voce", path=path)
        state_store.mark_session_active("main-session:subagent", "trabalhando", path=path)
        state_store.mark_session_inactive("main-session:subagent", path=path)
        result = state_store.read_claude_status(path=path)
        assert result["status"] == "trabalhando"


def test_abandoned_session_ages_out_even_while_another_session_stays_active():
    """A session whose Stop/SessionEnd never fires (terminal killed,
    laptop slept mid-session) must not stay "trabalhando" forever just
    because a totally different, legitimately active session keeps
    refreshing activity — each session needs its own last-active time,
    not one shared timestamp for the whole entry."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "state.json"
        stuck_since = time.time() - state_store.STALE_SECONDS - 1
        path.write_text(json.dumps({
            "claude": {
                "active_sessions": {"phantom-session": stuck_since, "live-session": time.time()},
                "status": "trabalhando",
                "since": time.time(),
            }
        }))
        result = state_store.read_claude_status(path=path)
        assert result["status"] == "trabalhando"  # live-session is still fresh

        state_store.mark_session_inactive("live-session", path=path)
        result = state_store.read_claude_status(path=path)
        assert result["status"] == "parado"  # phantom alone must not keep it stuck


def test_legacy_list_shaped_active_sessions_still_ages_out():
    """Pre-fix state files stored active_sessions as a plain list with no
    per-session timestamp — migrating that shape must not hand a stale
    entry a free fresh timestamp just for having the old shape."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "state.json"
        stuck_since = time.time() - state_store.STALE_SECONDS - 1
        path.write_text(json.dumps({
            "claude": {
                "active_sessions": ["old-phantom"],
                "status": "trabalhando",
                "since": stuck_since,
            }
        }))
        result = state_store.read_claude_status(path=path)
        assert result["status"] == "parado"


def test_session_transitioning_from_trabalhando_to_esperando_voce_updates_status():
    """A session that finishes a turn and gets an idle_prompt Notification
    updates its OWN tracked status via mark_session_active — replacing
    "trabalhando" with "esperando voce" for that same session_id, not
    leaving the old status stuck."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "state.json"
        state_store.mark_session_active("main-session", "trabalhando", path=path)
        state_store.mark_session_active("main-session", "esperando voce", path=path)
        result = state_store.read_claude_status(path=path)
        assert result["status"] == "esperando voce"


def test_multiple_sessions_different_statuses_prioritizes_trabalhando():
    """Session A working + Session B just idle-waiting on you -> the dot
    shows "trabalhando" (green), the more actionable of the two — one
    session's idle Notification must not mask another's real activity."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "state.json"
        state_store.mark_session_active("session-a", "trabalhando", path=path)
        state_store.mark_session_active("session-b", "esperando voce", path=path)
        result = state_store.read_claude_status(path=path)
        assert result["status"] == "trabalhando"


def test_multiple_sessions_prioritizes_esperando_decisao_over_esperando_voce():
    """Session A just idle-waiting + Session B needs an actual decision ->
    the dot shows "esperando decisao" (more urgent than plain idle)."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "state.json"
        state_store.mark_session_active("session-a", "esperando voce", path=path)
        state_store.mark_session_active("session-b", "esperando decisao", path=path)
        result = state_store.read_claude_status(path=path)
        assert result["status"] == "esperando decisao"


if __name__ == "__main__":
    test_roundtrip()
    test_missing_file_returns_default()
    test_corrupt_file_returns_default()
    test_stale_working_status_falls_back_to_idle()
    test_fresh_working_status_stays_working()
    test_subagent_stopping_does_not_mask_main_session_still_working()
    test_last_session_stopping_reports_idle()
    test_notification_mid_session_does_not_wipe_active_sessions()
    test_abandoned_session_ages_out_even_while_another_session_stays_active()
    test_legacy_list_shaped_active_sessions_still_ages_out()
    test_session_transitioning_from_trabalhando_to_esperando_voce_updates_status()
    test_multiple_sessions_different_statuses_prioritizes_trabalhando()
    test_multiple_sessions_prioritizes_esperando_decisao_over_esperando_voce()
    print("OK")
