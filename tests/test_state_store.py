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
    """write_claude_status (the Notification event's own path — the one
    event not covered by mark_session_active/inactive) must not clobber
    active_sessions, or a subagent's Stop right after a Notification finds
    no record of the still-running main session and wrongly reports
    "parado"."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "state.json"
        state_store.mark_session_active("main-session", "trabalhando", path=path)
        state_store.write_claude_status("esperando voce", path=path)
        state_store.mark_session_active("main-session:subagent", "trabalhando", path=path)
        state_store.mark_session_inactive("main-session:subagent", path=path)
        result = state_store.read_claude_status(path=path)
        assert result["status"] == "trabalhando"


if __name__ == "__main__":
    test_roundtrip()
    test_missing_file_returns_default()
    test_corrupt_file_returns_default()
    test_stale_working_status_falls_back_to_idle()
    test_fresh_working_status_stays_working()
    test_subagent_stopping_does_not_mask_main_session_still_working()
    test_last_session_stopping_reports_idle()
    test_notification_mid_session_does_not_wipe_active_sessions()
    print("OK")
