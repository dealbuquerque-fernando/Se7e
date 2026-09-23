import base64
import json
import sqlite3
import tempfile
import time
import urllib.error
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from se7e import usage_codex


def _fake_jwt(payload: dict) -> str:
    """A JWT with a real header/payload but a nonsense signature — good
    enough for _decode_id_token_exp, which never checks the signature."""
    def b64(part: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(part).encode()).decode().rstrip("=")
    return f"{b64({'alg': 'none'})}.{b64(payload)}.sig"


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
        conn.execute("CREATE TABLE thread_turns (status TEXT, completed_at INTEGER)")
        # A real, long-past Unix timestamp — completed_at is genuinely
        # numeric in the real db (confirmed live), not a date string.
        conn.execute("INSERT INTO thread_turns (status, completed_at) VALUES ('done', 0)")
        conn.commit()
        conn.close()
        assert usage_codex.is_busy(db_path) is False


def test_get_status_just_finished_reads_as_parado():
    """Mirrors Claude Code's own brief gray window right after its Stop
    hook, before the idle_prompt Notification fires — a turn that
    completed moments ago isn't "esperando voce" yet."""
    with tempfile.TemporaryDirectory() as d:
        db_path = Path(d) / "thread_history_1.sqlite"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE thread_turns (status TEXT, completed_at INTEGER)")
        conn.execute("INSERT INTO thread_turns (status, completed_at) VALUES ('done', ?)", (int(time.time()),))
        conn.commit()
        conn.close()
        assert usage_codex.get_status(db_path) == "parado"


def test_get_status_finished_a_while_ago_reads_as_esperando_voce():
    with tempfile.TemporaryDirectory() as d:
        db_path = Path(d) / "thread_history_1.sqlite"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE thread_turns (status TEXT, completed_at INTEGER)")
        old = int(time.time()) - usage_codex.IDLE_GRACE_SECONDS - 1
        conn.execute("INSERT INTO thread_turns (status, completed_at) VALUES ('done', ?)", (old,))
        conn.commit()
        conn.close()
        assert usage_codex.get_status(db_path) == "esperando voce"


def test_get_status_more_than_24h_since_last_turn_reverts_to_parado():
    """Mirrors state_store.STALE_SECONDS: a Codex thread used once and
    never touched again must eventually stop showing "esperando voce"
    forever, the same way Claude's own idle sessions get pruned."""
    with tempfile.TemporaryDirectory() as d:
        db_path = Path(d) / "thread_history_1.sqlite"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE thread_turns (status TEXT, completed_at INTEGER)")
        old = int(time.time()) - usage_codex.state_store.STALE_SECONDS - 1
        conn.execute("INSERT INTO thread_turns (status, completed_at) VALUES ('done', ?)", (old,))
        conn.commit()
        conn.close()
        assert usage_codex.get_status(db_path) == "parado"


def test_get_status_just_under_24h_still_reads_as_esperando_voce():
    with tempfile.TemporaryDirectory() as d:
        db_path = Path(d) / "thread_history_1.sqlite"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE thread_turns (status TEXT, completed_at INTEGER)")
        old = int(time.time()) - usage_codex.state_store.STALE_SECONDS + 60
        conn.execute("INSERT INTO thread_turns (status, completed_at) VALUES ('done', ?)", (old,))
        conn.commit()
        conn.close()
        assert usage_codex.get_status(db_path) == "esperando voce"


def test_get_status_never_used_reads_as_parado():
    with tempfile.TemporaryDirectory() as d:
        db_path = Path(d) / "thread_history_1.sqlite"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE thread_turns (status TEXT, completed_at INTEGER)")
        conn.commit()
        conn.close()
        assert usage_codex.get_status(db_path) == "parado"


def test_get_status_missing_db_reads_as_parado():
    with tempfile.TemporaryDirectory() as d:
        missing = Path(d) / "does-not-exist.sqlite"
        assert usage_codex.get_status(missing) == "parado"


def test_get_status_busy_wins_over_a_recently_completed_turn():
    """A new turn starting shortly after a previous one finished must
    show trabalhando, not get stuck on the old turn's completed_at."""
    with tempfile.TemporaryDirectory() as d:
        db_path = Path(d) / "thread_history_1.sqlite"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE thread_turns (status TEXT, completed_at INTEGER)")
        old = int(time.time()) - usage_codex.IDLE_GRACE_SECONDS - 1
        conn.execute("INSERT INTO thread_turns (status, completed_at) VALUES ('done', ?)", (old,))
        conn.execute("INSERT INTO thread_turns (status, completed_at) VALUES ('inProgress', NULL)")
        conn.commit()
        conn.close()
        assert usage_codex.get_status(db_path) == "trabalhando"


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
        original_log = usage_codex._log_attempt
        usage_codex.AUTH_PATH = path
        usage_codex._log_attempt = lambda *a, **k: None  # avoid writing the real usage_debug.log during tests
        try:
            result = usage_codex.get_usage()
        finally:
            usage_codex.AUTH_PATH = original
            usage_codex._log_attempt = original_log
        assert result == {"connected": True, "five_hour": None, "week": None, "stale": True}


def test_get_usage_null_tokens_returns_fallback_not_raise():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "auth.json"
        path.write_text('{"tokens": null}')
        original = usage_codex.AUTH_PATH
        original_log = usage_codex._log_attempt
        usage_codex.AUTH_PATH = path
        usage_codex._log_attempt = lambda *a, **k: None  # avoid writing the real usage_debug.log during tests
        try:
            result = usage_codex.get_usage()
        finally:
            usage_codex.AUTH_PATH = original
            usage_codex._log_attempt = original_log
        assert result == {"connected": True, "five_hour": None, "week": None, "stale": True}


def test_decode_id_token_exp_reads_exp_claim():
    token = _fake_jwt({"exp": 1234567890})
    assert usage_codex._decode_id_token_exp(token) == 1234567890


def test_decode_id_token_exp_malformed_returns_none():
    assert usage_codex._decode_id_token_exp("not-a-jwt") is None
    assert usage_codex._decode_id_token_exp("a.b") is None  # missing signature segment is fine, bad payload isn't
    assert usage_codex._decode_id_token_exp("a.!!!notb64!!!.c") is None


def test_read_id_token_expiry_from_file():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "auth.json"
        token = _fake_jwt({"exp": 999})
        path.write_text(json.dumps({"tokens": {"id_token": token}}))
        assert usage_codex.read_id_token_expiry(path=path) == 999


def test_read_id_token_expiry_missing_file_returns_none():
    with tempfile.TemporaryDirectory() as d:
        assert usage_codex.read_id_token_expiry(path=Path(d) / "missing.json") is None


def test_refresh_via_oauth_updates_tokens_and_preserves_other_fields():
    """Must not lose auth_mode/OPENAI_API_KEY/account_id — those are the
    real Codex CLI's own fields, untouched by Se7e's refresh."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "auth.json"
        path.write_text(json.dumps({
            "auth_mode": "chatgpt",
            "OPENAI_API_KEY": None,
            "tokens": {
                "id_token": "old-id",
                "access_token": "old-access",
                "refresh_token": "old-refresh",
                "account_id": "acc-1",
            },
            "last_refresh": "2020-01-01T00:00:00.000000Z",
        }))

        original_post = usage_codex._post_token_refresh
        usage_codex._post_token_refresh = lambda refresh_token: {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "id_token": "new-id",
        }
        try:
            assert usage_codex._refresh_via_oauth(path=path) is True
        finally:
            usage_codex._post_token_refresh = original_post

        data = json.loads(path.read_text())
        assert data["auth_mode"] == "chatgpt"
        assert data["tokens"]["access_token"] == "new-access"
        assert data["tokens"]["refresh_token"] == "new-refresh"
        assert data["tokens"]["id_token"] == "new-id"
        assert data["tokens"]["account_id"] == "acc-1"  # untouched
        assert data["last_refresh"] != "2020-01-01T00:00:00.000000Z"


def test_refresh_via_oauth_network_failure_leaves_file_untouched():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "auth.json"
        original_content = json.dumps({"tokens": {"refresh_token": "rt", "access_token": "old"}})
        path.write_text(original_content)

        original_post = usage_codex._post_token_refresh
        usage_codex._post_token_refresh = lambda refresh_token: None
        try:
            assert usage_codex._refresh_via_oauth(path=path) is False
        finally:
            usage_codex._post_token_refresh = original_post

        assert path.read_text() == original_content


def test_refresh_via_oauth_missing_refresh_token_returns_false():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "auth.json"
        path.write_text(json.dumps({"tokens": {"access_token": "old"}}))
        assert usage_codex._refresh_via_oauth(path=path) is False


def test_get_usage_refreshes_proactively_when_near_expiry():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "auth.json"
        near_expiry = int(time.time()) + 10  # inside REFRESH_MARGIN_SECONDS
        path.write_text(json.dumps({
            "tokens": {
                "access_token": "stale-access",
                "refresh_token": "rt",
                "account_id": "acc-1",
                "id_token": _fake_jwt({"exp": near_expiry}),
            },
        }))

        original_auth_path = usage_codex.AUTH_PATH
        original_fetch = usage_codex.fetch_usage
        original_post = usage_codex._post_token_refresh
        original_log = usage_codex._log_attempt
        usage_codex.AUTH_PATH = path
        usage_codex._log_attempt = lambda *a, **k: None  # avoid writing the real usage_debug.log during tests
        seen_tokens = []

        def fake_post(refresh_token):
            return {"access_token": "fresh-access", "id_token": _fake_jwt({"exp": int(time.time()) + 3600})}

        def fake_fetch(credential):
            seen_tokens.append(credential["access_token"])
            return {"five_hour": 5, "week": 10}

        usage_codex._post_token_refresh = fake_post
        usage_codex.fetch_usage = fake_fetch
        try:
            result = usage_codex.get_usage()
        finally:
            usage_codex.AUTH_PATH = original_auth_path
            usage_codex.fetch_usage = original_fetch
            usage_codex._post_token_refresh = original_post
            usage_codex._log_attempt = original_log

        assert result == {"five_hour": 5, "week": 10, "connected": True, "stale": False}
        assert seen_tokens == ["fresh-access"]  # used the refreshed token, not the stale one


def test_get_usage_refreshes_reactively_on_401():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "auth.json"
        far_expiry = int(time.time()) + 3600
        path.write_text(json.dumps({
            "tokens": {
                "access_token": "expired-access",
                "refresh_token": "rt",
                "account_id": "acc-1",
                "id_token": _fake_jwt({"exp": far_expiry}),
            },
        }))

        original_auth_path = usage_codex.AUTH_PATH
        original_fetch = usage_codex.fetch_usage
        original_post = usage_codex._post_token_refresh
        original_log = usage_codex._log_attempt
        usage_codex.AUTH_PATH = path
        usage_codex._log_attempt = lambda *a, **k: None  # avoid writing the real usage_debug.log during tests
        calls = []

        def fake_post(refresh_token):
            return {"access_token": "fresh-access"}

        def fake_fetch(credential):
            calls.append(credential["access_token"])
            if credential["access_token"] == "expired-access":
                raise urllib.error.HTTPError("http://x", 401, "unauthorized", {}, None)
            return {"five_hour": 1, "week": 2}

        usage_codex._post_token_refresh = fake_post
        usage_codex.fetch_usage = fake_fetch
        try:
            result = usage_codex.get_usage()
        finally:
            usage_codex.AUTH_PATH = original_auth_path
            usage_codex.fetch_usage = original_fetch
            usage_codex._post_token_refresh = original_post
            usage_codex._log_attempt = original_log

        assert result == {"five_hour": 1, "week": 2, "connected": True, "stale": False}
        assert calls == ["expired-access", "fresh-access"]  # retried after refreshing


if __name__ == "__main__":
    test_parse_usage()
    test_parse_usage_from_real_api_shape_nested_under_rate_limit()
    test_parse_usage_missing_fields_stays_none()
    test_read_credential_missing_file()
    test_read_credential_incomplete_stays_none()
    test_read_credential_complete()
    test_is_busy_true_when_turn_in_progress()
    test_is_busy_false_when_no_active_turn()
    test_get_status_just_finished_reads_as_parado()
    test_get_status_finished_a_while_ago_reads_as_esperando_voce()
    test_get_status_more_than_24h_since_last_turn_reverts_to_parado()
    test_get_status_just_under_24h_still_reads_as_esperando_voce()
    test_get_status_never_used_reads_as_parado()
    test_get_status_missing_db_reads_as_parado()
    test_get_status_busy_wins_over_a_recently_completed_turn()
    test_is_busy_missing_db_returns_false()
    test_get_usage_malformed_tokens_shape_returns_fallback_not_raise()
    test_decode_id_token_exp_reads_exp_claim()
    test_decode_id_token_exp_malformed_returns_none()
    test_read_id_token_expiry_from_file()
    test_read_id_token_expiry_missing_file_returns_none()
    test_refresh_via_oauth_updates_tokens_and_preserves_other_fields()
    test_refresh_via_oauth_network_failure_leaves_file_untouched()
    test_refresh_via_oauth_missing_refresh_token_returns_false()
    test_get_usage_refreshes_proactively_when_near_expiry()
    test_get_usage_refreshes_reactively_on_401()
    test_get_usage_null_tokens_returns_fallback_not_raise()
    print("OK")
