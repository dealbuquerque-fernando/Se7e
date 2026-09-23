import io
import json
import tempfile
import time
import urllib.error
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from se7e import usage_claude


def test_parse_usage_from_limits_array():
    payload = {"limits": [
        {"id": "session", "percent": 42},
        {"id": "weekly_all", "percent": 61},
    ]}
    result = usage_claude.parse_usage(payload)
    assert result["five_hour"] == 42
    assert result["week"] == 61


def test_parse_usage_fallback_shape():
    payload = {"five_hour": {"utilization": 18}, "seven_day": {"utilization": 35}}
    result = usage_claude.parse_usage(payload)
    assert result["five_hour"] == 18
    assert result["week"] == 35


def test_parse_usage_missing_fields_stays_none():
    result = usage_claude.parse_usage({})
    assert result["five_hour"] is None
    assert result["week"] is None


def test_read_access_token_missing_file_returns_none():
    with tempfile.TemporaryDirectory() as d:
        missing = Path(d) / "does-not-exist.json"
        assert usage_claude.read_access_token(path=missing) is None


def test_read_access_token_from_credentials_file():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / ".credentials.json"
        path.write_text('{"claudeAiOauth": {"accessToken": "abc123"}}')
        assert usage_claude.read_access_token(path=path) == "abc123"


def test_read_access_token_malformed_json_array_raises():
    """Credentials file with valid JSON array instead of object raises AttributeError."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / ".credentials.json"
        path.write_text('[]')
        try:
            usage_claude.read_access_token(path=path)
            assert False, "Should have raised AttributeError"
        except AttributeError:
            pass  # Expected: .get() on non-dict


def test_read_access_token_malformed_json_null_raises():
    """Credentials file with valid JSON null instead of object raises AttributeError."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / ".credentials.json"
        path.write_text('null')
        try:
            usage_claude.read_access_token(path=path)
            assert False, "Should have raised AttributeError"
        except AttributeError:
            pass  # Expected: .get() on non-dict


def test_parse_usage_with_list_payload_raises():
    """parse_usage() with list instead of dict raises AttributeError."""
    try:
        usage_claude.parse_usage([])
        assert False, "Should have raised AttributeError"
    except AttributeError:
        pass  # Expected: .get() on non-dict


def test_parse_usage_with_limits_string_raises():
    """parse_usage() with limits as string instead of list raises."""
    try:
        usage_claude.parse_usage({"limits": "not-a-list"})
        assert False, "Should have raised"
    except (AttributeError, TypeError):
        pass  # Expected: iteration or .get() error


def test_parse_usage_with_limit_item_non_dict_raises():
    """parse_usage() with non-dict item in limits array raises AttributeError."""
    try:
        usage_claude.parse_usage({"limits": ["not-a-dict"]})
        assert False, "Should have raised AttributeError"
    except AttributeError:
        pass  # Expected: .get() on non-dict


def test_parse_usage_with_five_hour_non_dict_raises():
    """parse_usage() with five_hour as non-dict raises TypeError."""
    try:
        usage_claude.parse_usage({"five_hour": 123})
        assert False, "Should have raised TypeError"
    except TypeError:
        pass  # Expected: 'in' operator on int


def test_get_usage_backs_off_after_429_and_skips_the_next_call():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / ".credentials.json"
        path.write_text(json.dumps({
            "claudeAiOauth": {"accessToken": "abc", "expiresAt": (time.time() + 999999) * 1000}
        }))
        # read_access_token()/read_expires_at() default their `path` argument
        # to CREDENTIALS_PATH at function-definition time, so reassigning
        # that module attribute here wouldn't reach get_usage()'s own calls
        # to them — only patching the functions themselves does.
        original_read_token = usage_claude.read_access_token
        original_read_expires = usage_claude.read_expires_at
        original_until = usage_claude._rate_limit_until
        original_backoff = usage_claude._rate_limit_backoff
        original_fetch = usage_claude.fetch_usage
        original_log = usage_claude._log_attempt
        usage_claude.read_access_token = lambda: original_read_token(path)
        usage_claude.read_expires_at = lambda: original_read_expires(path)
        usage_claude._rate_limit_until = 0.0
        usage_claude._rate_limit_backoff = 0
        usage_claude._log_attempt = lambda *a, **k: None  # avoid writing the real usage_debug.log during tests
        calls = []

        def fake_fetch(token):
            calls.append(token)
            raise urllib.error.HTTPError("http://x", 429, "rate limited", {}, io.BytesIO(b""))

        usage_claude.fetch_usage = fake_fetch
        try:
            first = usage_claude.get_usage()
            assert first["stale"] is True
            assert len(calls) == 1
            assert usage_claude._rate_limit_backoff == usage_claude.RATE_LIMIT_BACKOFF_FLOOR_SECONDS

            # Still cooling down: get_usage() must not spend another attempt.
            second = usage_claude.get_usage()
            assert second["stale"] is True
            assert len(calls) == 1
        finally:
            usage_claude.fetch_usage = original_fetch
            usage_claude.read_access_token = original_read_token
            usage_claude.read_expires_at = original_read_expires
            usage_claude._rate_limit_until = original_until
            usage_claude._rate_limit_backoff = original_backoff
            usage_claude._log_attempt = original_log


def test_get_usage_success_resets_backoff():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / ".credentials.json"
        path.write_text(json.dumps({
            "claudeAiOauth": {"accessToken": "abc", "expiresAt": (time.time() + 999999) * 1000}
        }))
        original_read_token = usage_claude.read_access_token
        original_read_expires = usage_claude.read_expires_at
        original_until = usage_claude._rate_limit_until
        original_backoff = usage_claude._rate_limit_backoff
        original_fetch = usage_claude.fetch_usage
        original_log = usage_claude._log_attempt
        usage_claude.read_access_token = lambda: original_read_token(path)
        usage_claude.read_expires_at = lambda: original_read_expires(path)
        usage_claude._rate_limit_until = 0.0
        usage_claude._rate_limit_backoff = 30  # pretend a previous 429 already happened
        usage_claude._log_attempt = lambda *a, **k: None  # avoid writing the real usage_debug.log during tests

        usage_claude.fetch_usage = lambda token: {"five_hour": 10, "week": 20}
        try:
            result = usage_claude.get_usage()
            assert result == {"five_hour": 10, "week": 20, "connected": True, "stale": False}
            assert usage_claude._rate_limit_backoff == 0
            assert usage_claude._rate_limit_until == 0.0
        finally:
            usage_claude.fetch_usage = original_fetch
            usage_claude.read_access_token = original_read_token
            usage_claude.read_expires_at = original_read_expires
            usage_claude._rate_limit_until = original_until
            usage_claude._rate_limit_backoff = original_backoff
            usage_claude._log_attempt = original_log


if __name__ == "__main__":
    test_parse_usage_from_limits_array()
    test_parse_usage_fallback_shape()
    test_parse_usage_missing_fields_stays_none()
    test_read_access_token_missing_file_returns_none()
    test_read_access_token_from_credentials_file()
    test_read_access_token_malformed_json_array_raises()
    test_read_access_token_malformed_json_null_raises()
    test_parse_usage_with_list_payload_raises()
    test_parse_usage_with_limits_string_raises()
    test_parse_usage_with_limit_item_non_dict_raises()
    test_parse_usage_with_five_hour_non_dict_raises()
    test_get_usage_backs_off_after_429_and_skips_the_next_call()
    test_get_usage_success_resets_backoff()
    print("OK")
