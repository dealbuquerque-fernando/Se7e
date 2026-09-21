import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ENDPOINT = "https://api.anthropic.com/api/oauth/usage"
CREDENTIALS_PATH = Path.home() / ".claude" / ".credentials.json"
REFRESH_MARGIN_SECONDS = 60
REFRESH_TIMEOUT_SECONDS = 15
RATE_LIMIT_BACKOFF_FLOOR_SECONDS = 60
RATE_LIMIT_BACKOFF_CAP_SECONDS = 900

_rate_limit_until = 0.0
_rate_limit_backoff = 0


def read_access_token(path: Path = CREDENTIALS_PATH):
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    oauth = data.get("claudeAiOauth", data)
    return oauth.get("accessToken")


def read_expires_at(path: Path = CREDENTIALS_PATH):
    """Seconds since epoch the current access token expires at, or None if unknown."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
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
        return {"connected": True, "five_hour": None, "week": None, "stale": True}
    try:
        token = read_access_token()
        if token is None:
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
                return {"connected": True, "five_hour": None, "week": None, "stale": True}
            if exc.code != 401:
                raise
            _refresh_via_cli()
            token = read_access_token()
            if token is None:
                raise
            usage = fetch_usage(token)
        usage["connected"] = True
        usage["stale"] = False
        _rate_limit_backoff = 0
        _rate_limit_until = 0.0
        return usage
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, AttributeError, TypeError):
        return {"connected": True, "five_hour": None, "week": None, "stale": True}
