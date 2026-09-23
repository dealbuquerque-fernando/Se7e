import getpass
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from .config import APP_DIR

ENDPOINT = "https://api.anthropic.com/api/oauth/usage"
CREDENTIALS_PATH = Path.home() / ".claude" / ".credentials.json"
KEYCHAIN_SERVICE = "Claude Code-credentials"
REFRESH_MARGIN_SECONDS = 60
REFRESH_TIMEOUT_SECONDS = 15
RATE_LIMIT_BACKOFF_FLOOR_SECONDS = 60
RATE_LIMIT_BACKOFF_CAP_SECONDS = 900

_rate_limit_until = 0.0
_rate_limit_backoff = 0

# Temporary diagnostic trail for a reported bug: the "updated Ns ago" line
# sometimes goes stale well past the normal 45s poll cycle, on Windows
# persistently and on macOS at least occasionally. get_usage() logs one
# line per outcome here — including the exact HTTP status / exception when
# it fails — instead of that detail only ever surfacing as an
# undifferentiated "stale" in the UI. Remove once the report is resolved.
_USAGE_LOG_MAX_LINES = 500


def _log_attempt(outcome: str, detail: str = "") -> None:
    try:
        log_path = APP_DIR / "usage_debug.log"
        entry = {"ts": time.time(), "provider": "claude", "outcome": outcome, "detail": detail}
        lines = []
        if log_path.exists():
            lines = log_path.read_text().splitlines()
        lines.append(json.dumps(entry))
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("\n".join(lines[-_USAGE_LOG_MAX_LINES:]) + "\n")
    except OSError:
        pass


def _read_credentials_from_keychain() -> dict | None:
    """macOS only: Claude Code stores its OAuth credential (same JSON shape
    as .credentials.json — a claudeAiOauth object with accessToken etc.) in
    the login Keychain instead of a file, unless it fell back to writing
    the file itself (e.g. Keychain locked in an SSH session — the file is
    checked first, above, so that case is already covered)."""
    if sys.platform != "darwin":
        return None
    try:
        result = subprocess.run(
            [
                "security", "find-generic-password",
                "-a", getpass.getuser(),
                "-s", KEYCHAIN_SERVICE,
                "-w",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


# A file that exists but holds valid JSON `null` must still reach the
# .get() calls below and raise AttributeError — that's a deliberate signal
# of a corrupted credentials file, not "no credentials". This sentinel
# marks the "nothing readable at all" case instead of reusing None, which
# is also json.loads('null')'s legitimate return value.
_NO_CREDENTIALS = object()


def _read_credentials(path: Path):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return _NO_CREDENTIALS
    # Only fall back to the real Keychain for the real default path — a
    # test passing its own (missing-on-purpose) path must still get
    # nothing, not a query against this machine's actual Claude Code
    # credential.
    if path == CREDENTIALS_PATH:
        keychain_data = _read_credentials_from_keychain()
        if keychain_data is not None:
            return keychain_data
    return _NO_CREDENTIALS


def read_access_token(path: Path = CREDENTIALS_PATH):
    data = _read_credentials(path)
    if data is _NO_CREDENTIALS:
        return None
    oauth = data.get("claudeAiOauth", data)
    return oauth.get("accessToken")


def read_expires_at(path: Path = CREDENTIALS_PATH):
    """Seconds since epoch the current access token expires at, or None if unknown."""
    data = _read_credentials(path)
    if data is _NO_CREDENTIALS:
        return None
    oauth = data.get("claudeAiOauth", data)
    expires_at_ms = oauth.get("expiresAt")
    return expires_at_ms / 1000 if expires_at_ms else None


def _refresh_via_cli() -> None:
    """Claude Code rotates its own token on any CLI invocation; `/usage` is a local
    command (no model call, no cost) that's enough to trigger that rotation."""
    try:
        subprocess.run(
            ["claude", "/usage"],
            capture_output=True,
            timeout=REFRESH_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def parse_usage(payload: dict) -> dict:
    result = {"five_hour": None, "week": None}
    for limit in payload.get("limits", []):
        kind = limit.get("id") or limit.get("kind")
        pct = limit.get("percent")
        if pct is None:
            continue
        if kind in ("session", "five_hour"):
            result["five_hour"] = pct
        elif kind in ("seven_day", "weekly_all", "weekly"):
            result["week"] = pct
    five_hour_block = payload.get("five_hour") or {}
    seven_day_block = payload.get("seven_day") or {}
    if result["five_hour"] is None and "utilization" in five_hour_block:
        result["five_hour"] = five_hour_block["utilization"]
    if result["week"] is None and "utilization" in seven_day_block:
        result["week"] = seven_day_block["utilization"]
    return result


def fetch_usage(token: str) -> dict:
    req = urllib.request.Request(ENDPOINT, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        payload = json.loads(resp.read())
    return parse_usage(payload)


def get_usage() -> dict:
    global _rate_limit_until, _rate_limit_backoff
    if time.time() < _rate_limit_until:
        # Still cooling down from a 429 — don't spend another attempt on it,
        # the endpoint's own Retry-After is 0 and useless.
        _log_attempt("rate_limit_cooldown", f"until={_rate_limit_until}")
        return {"connected": True, "five_hour": None, "week": None, "stale": True}
    try:
        token = read_access_token()
        if token is None:
            _log_attempt("no_token")
            return {"connected": False, "five_hour": None, "week": None, "stale": False}
        expires_at = read_expires_at()
        if expires_at is not None and expires_at - time.time() < REFRESH_MARGIN_SECONDS:
            _refresh_via_cli()
            token = read_access_token() or token
        try:
            usage = fetch_usage(token)
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                _rate_limit_backoff = min(
                    max(_rate_limit_backoff * 2, RATE_LIMIT_BACKOFF_FLOOR_SECONDS),
                    RATE_LIMIT_BACKOFF_CAP_SECONDS,
                )
                _rate_limit_until = time.time() + _rate_limit_backoff
                _log_attempt("http_429", f"backoff={_rate_limit_backoff}")
                return {"connected": True, "five_hour": None, "week": None, "stale": True}
            if exc.code != 401:
                _log_attempt("http_error", f"code={exc.code} reason={exc.reason}")
                raise
            _refresh_via_cli()
            token = read_access_token()
            if token is None:
                _log_attempt("http_401_no_token_after_refresh")
                raise
            usage = fetch_usage(token)
            _log_attempt("http_401_recovered_after_refresh")
        usage["connected"] = True
        usage["stale"] = False
        _rate_limit_backoff = 0
        _rate_limit_until = 0.0
        _log_attempt("success")
        return usage
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, AttributeError, TypeError) as exc:
        detail = getattr(exc, "reason", None) or str(exc)
        _log_attempt(f"{type(exc).__name__}", str(detail))
        return {"connected": True, "five_hour": None, "week": None, "stale": True}
