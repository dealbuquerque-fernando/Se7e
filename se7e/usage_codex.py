import base64
import binascii
import json
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ENDPOINT = "https://chatgpt.com/backend-api/wham/usage"
# Public: openai/codex's own codex-rs/core/src/auth.rs, and documented at
# developers.openai.com/codex/auth/ci-cd-auth. A plain OAuth token-endpoint
# call, not a model request — no cost, unlike shelling out to `codex exec`
# (the only other way observed to actually trigger a refresh; `codex login
# status` does not).
TOKEN_URL = "https://auth.openai.com/oauth/token"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_HOME = Path.home() / ".codex"
AUTH_PATH = CODEX_HOME / "auth.json"
THREAD_DB_PATH = CODEX_HOME / "thread_history_1.sqlite"
REFRESH_MARGIN_SECONDS = 60
REFRESH_TIMEOUT_SECONDS = 15
# How long a just-finished turn still reads as "parado" before flipping to
# "esperando voce" — mirrors Claude Code's own idle_prompt delay (measured
# live: ~60s from its Stop hook to the "Claude is waiting for your input"
# Notification), so both providers settle into idle on the same rhythm:
# working -> briefly parado -> esperando voce.
IDLE_GRACE_SECONDS = 60

# Codex has no way to signal "waiting on your approval" to an outside
# program: the notify hook only fires on turn completion (open OpenAI
# feature requests #11808/#3052/#19921 ask for approval events too and
# remain unimplemented), and no local Codex database records an
# approval-pending state either — checked thread_turns, thread_items and
# thread_realtime_items directly. So Codex can't distinguish "esperando
# decisao" from plain idle the way Claude's notification_type does; it
# only ever reports trabalhando/parado/esperando voce.


def read_credential(path: Path = AUTH_PATH):
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    tokens = data.get("tokens", {})
    access_token = tokens.get("access_token")
    account_id = tokens.get("account_id")
    if not access_token or not account_id:
        return None
    return {"access_token": access_token, "account_id": account_id}


def _decode_id_token_exp(id_token: str):
    """The "exp" claim from the id_token's JWT payload — the access_token
    itself carries no expiry, but Codex issues both from the same grant
    with the same lifetime."""
    try:
        payload_b64 = id_token.split(".")[1]
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
    except (IndexError, ValueError, TypeError, UnicodeDecodeError, binascii.Error, json.JSONDecodeError):
        return None
    return payload.get("exp")


def read_id_token_expiry(path: Path = AUTH_PATH):
    """Seconds since epoch the current access token expires at, or None if
    unknown."""
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    id_token = data.get("tokens", {}).get("id_token") if isinstance(data.get("tokens"), dict) else None
    if not id_token:
        return None
    return _decode_id_token_exp(id_token)


def _post_token_refresh(refresh_token: str):
    """The actual network call, split out from _refresh_via_oauth() so
    tests can substitute a fake response without touching urllib."""
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
    }).encode()
    req = urllib.request.Request(TOKEN_URL, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=REFRESH_TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None


def _refresh_via_oauth(path: Path = AUTH_PATH) -> bool:
    """Refreshes auth.json's access_token in place. Preserves every other
    key already in the file (auth_mode, OPENAI_API_KEY, account_id, ...)
    and writes atomically (temp file + rename), so a failed or partial
    refresh can never corrupt the file the real Codex CLI depends on for
    its own login."""
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return False
    tokens = data.get("tokens")
    if not isinstance(tokens, dict):
        return False
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        return False

    result = _post_token_refresh(refresh_token)
    if not result or not result.get("access_token"):
        return False

    tokens["access_token"] = result["access_token"]
    if result.get("refresh_token"):
        tokens["refresh_token"] = result["refresh_token"]
    if result.get("id_token"):
        tokens["id_token"] = result["id_token"]
    data["tokens"] = tokens
    data["last_refresh"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(path)
    return True


def parse_usage(payload: dict) -> dict:
    result = {"five_hour": None, "week": None}
    rate_limit = payload.get("rate_limit") or payload
    primary = rate_limit.get("primary_window") or rate_limit.get("primary")
    secondary = rate_limit.get("secondary_window") or rate_limit.get("secondary")
    if primary and "used_percent" in primary:
        result["five_hour"] = primary["used_percent"]
    if secondary and "used_percent" in secondary:
        result["week"] = secondary["used_percent"]
    return result


def fetch_usage(credential: dict) -> dict:
    req = urllib.request.Request(
        ENDPOINT,
        headers={
            "Authorization": f"Bearer {credential['access_token']}",
            "ChatGPT-Account-Id": credential["account_id"],
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        payload = json.loads(resp.read())
    return parse_usage(payload)


def get_usage() -> dict:
    try:
        credential = read_credential(AUTH_PATH)
        if credential is None:
            return {"connected": False, "five_hour": None, "week": None, "stale": False}
        expires_at = read_id_token_expiry(AUTH_PATH)
        if expires_at is not None and expires_at - time.time() < REFRESH_MARGIN_SECONDS:
            if _refresh_via_oauth(AUTH_PATH):
                credential = read_credential(AUTH_PATH) or credential
        try:
            usage = fetch_usage(credential)
        except urllib.error.HTTPError as exc:
            if exc.code != 401:
                raise
            if not _refresh_via_oauth(AUTH_PATH):
                raise
            credential = read_credential(AUTH_PATH)
            if credential is None:
                raise
            usage = fetch_usage(credential)
        usage["connected"] = True
        usage["stale"] = False
        return usage
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, AttributeError, TypeError):
        return {"connected": True, "five_hour": None, "week": None, "stale": True}


def is_busy(db_path: Path = THREAD_DB_PATH) -> bool:
    if not db_path.exists():
        return False
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return False
    try:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM thread_turns WHERE status = 'inProgress' AND completed_at IS NULL"
        )
        return cursor.fetchone()[0] > 0
    except sqlite3.Error:
        return False
    finally:
        conn.close()


def _last_completed_turn_at(db_path: Path = THREAD_DB_PATH):
    """Unix timestamp (seconds) the most recently completed turn finished
    at, or None if the db doesn't exist or no turn has ever completed."""
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        cursor = conn.execute("SELECT MAX(completed_at) FROM thread_turns WHERE completed_at IS NOT NULL")
        row = cursor.fetchone()
        return row[0] if row else None
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def get_status(db_path: Path = THREAD_DB_PATH) -> str:
    if is_busy(db_path):
        return "trabalhando"
    last_completed = _last_completed_turn_at(db_path)
    if last_completed is None:
        return "parado"  # never used Codex, or the db doesn't exist yet
    if time.time() - last_completed < IDLE_GRACE_SECONDS:
        return "parado"  # just finished — same brief window Claude has right after its own Stop
    return "esperando voce"
