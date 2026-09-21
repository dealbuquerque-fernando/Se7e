import sys
from pathlib import Path

try:
    from . import state_store
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from se7e import state_store

EVENT_STATUS = {
    "SessionStart": "trabalhando",
    "UserPromptSubmit": "trabalhando",
    "Notification": "esperando voce",
    "Stop": "parado",
    "SessionEnd": "parado",
}


def status_for_event(event: str):
    return EVENT_STATUS.get(event)


def main(event: str | None = None) -> None:
    if event is None:
        event = sys.argv[1] if len(sys.argv) > 1 else ""
    status = status_for_event(event)
    if status is None:
        return
    try:
        state_store.write_claude_status(status)
    except OSError:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
