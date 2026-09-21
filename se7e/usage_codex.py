import json
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path

ENDPOINT = "https://chatgpt.com/backend-api/wham/usage"
CODEX_HOME = Path.home() / ".codex"
AUTH_PATH = CODEX_HOME / "auth.json"
THREAD_DB_PATH = CODEX_HOME / "thread_history_1.sqlite"

# Codex has no way to signal "waiting on your approval" to an outside program:
# the notify hook only fires on turn completion (open OpenAI feature requests
# #11808/#6024/#3247/#14813 ask for approval events and remain unimplemented),
# and no local Codex database records an approval-pending state either —
# checked thread_turns, thread_items and thread_realtime_items directly.
# So Codex only ever reports busy/idle, never a third "waiting" state.


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


def get_status(db_path: Path = THREAD_DB_PATH) -> str:
    return "trabalhando" if is_busy(db_path) else "parado"
