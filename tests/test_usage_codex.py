import sqlite3
import tempfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from se7e import usage_codex


def test_parse_usage():
    payload = {"primary_window": {"used_percent": 18}, "secondary_window": {"used_percent": 35}}
    result = usage_codex.parse_usage(payload)
    assert result["five_hour"] == 18
    assert result["week"] == 35


def test_parse_usage_from_real_api_shape_nested_under_rate_limit():
    """The live endpoint nests the windows under "rate_limit", not top-level."""
    payload = {"rate_limit": {"primary_window": {"used_percent": 12}, "secondary_window": {"used_percent": 30}}}
    result = usage_codex.parse_usage(payload)
    assert result["five_hour"] == 12
    assert result["week"] == 30


def test_parse_usage_missing_fields_stays_none():
    result = usage_codex.parse_usage({})
    assert result["five_hour"] is None
    assert result["week"] is None


def test_read_credential_missing_file():
    with tempfile.TemporaryDirectory() as d:
        missing = Path(d) / "auth.json"
        assert usage_codex.read_credential(path=missing) is None


def test_read_credential_incomplete_stays_none():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "auth.json"
        path.write_text('{"tokens": {"access_token": "abc"}}')
        assert usage_codex.read_credential(path=path) is None


def test_read_credential_complete():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "auth.json"
        path.write_text('{"tokens": {"access_token": "abc", "account_id": "acc-1"}}')
        cred = usage_codex.read_credential(path=path)
        assert cred == {"access_token": "abc", "account_id": "acc-1"}


def test_is_busy_true_when_turn_in_progress():
    with tempfile.TemporaryDirectory() as d:
        db_path = Path(d) / "thread_history_1.sqlite"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE thread_turns (status TEXT, completed_at TEXT)")
        conn.execute("INSERT INTO thread_turns (status, completed_at) VALUES ('inProgress', NULL)")
        conn.commit()
        conn.close()
        assert usage_codex.is_busy(db_path) is True
        assert usage_codex.get_status(db_path) == "trabalhando"


def test_is_busy_false_when_no_active_turn():
    with tempfile.TemporaryDirectory() as d:
        db_path = Path(d) / "thread_history_1.sqlite"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE thread_turns (status TEXT, completed_at TEXT)")
        conn.execute("INSERT INTO thread_turns (status, completed_at) VALUES ('done', '2026-01-01')")
        conn.commit()
        conn.close()
        assert usage_codex.is_busy(db_path) is False
        assert usage_codex.get_status(db_path) == "parado"


def test_is_busy_missing_db_returns_false():
    with tempfile.TemporaryDirectory() as d:
        missing = Path(d) / "does-not-exist.sqlite"
        assert usage_codex.is_busy(missing) is False


def test_get_usage_malformed_tokens_shape_returns_fallback_not_raise():
    """auth.json with a non-dict 'tokens' value must not raise AttributeError out of get_usage()."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "auth.json"
        path.write_text('{"tokens": "not-an-object"}')
        original = usage_codex.AUTH_PATH
        usage_codex.AUTH_PATH = path
        try:
            result = usage_codex.get_usage()
        finally:
            usage_codex.AUTH_PATH = original
        assert result == {"connected": True, "five_hour": None, "week": None, "stale": True}


def test_get_usage_null_tokens_returns_fallback_not_raise():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "auth.json"
        path.write_text('{"tokens": null}')
        original = usage_codex.AUTH_PATH
        usage_codex.AUTH_PATH = path
        try:
            result = usage_codex.get_usage()
        finally:
            usage_codex.AUTH_PATH = original
        assert result == {"connected": True, "five_hour": None, "week": None, "stale": True}


if __name__ == "__main__":
    test_parse_usage()
    test_parse_usage_from_real_api_shape_nested_under_rate_limit()
    test_parse_usage_missing_fields_stays_none()
    test_read_credential_missing_file()
    test_read_credential_incomplete_stays_none()
    test_read_credential_complete()
    test_is_busy_true_when_turn_in_progress()
    test_is_busy_false_when_no_active_turn()
    test_is_busy_missing_db_returns_false()
    test_get_usage_malformed_tokens_shape_returns_fallback_not_raise()
    test_get_usage_null_tokens_returns_fallback_not_raise()
    print("OK")
