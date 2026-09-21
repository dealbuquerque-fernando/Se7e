import json
import time
from pathlib import Path

from .config import STATE_FILE

# If "Stop"/"SessionEnd" never fires (terminal killed mid-session), a "trabalhando"
# or "esperando voce" reading older than this is treated as abandoned, not live.
STALE_SECONDS = 600


def read_all(path: Path = STATE_FILE) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (ValueError, OSError):
        return {}


def write_claude_status(status: str, path: Path = STATE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = read_all(path)
    data["claude"] = {"status": status, "since": time.time()}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(path)


def read_claude_status(path: Path = STATE_FILE) -> dict:
    data = read_all(path)
    status = data.get("claude", {"status": "parado", "since": 0})
    if status["status"] != "parado" and time.time() - status.get("since", 0) > STALE_SECONDS:
        return {"status": "parado", "since": status.get("since", 0)}
    return status
