import json
import sys
import time
from pathlib import Path

from .config import TOOL_END_FILE, TOOL_START_FILE

MARKER = "se7e"

WIRING = [
    ("SessionStart", False),
    ("UserPromptSubmit", False),
    ("SubagentStart", False),
    ("Notification", False),
    ("Stop", False),
    ("SessionEnd", False),
    ("SubagentStop", False),
]

# PreToolUse/PostToolUse fire on every single tool call — wiring them to
# the packaged app binary like every event above would add real, blocking
# delay to every tool use: measured live, ~0.7-0.74s per invocation,
# entirely the cost of starting the bundled Python/Qt runtime from
# scratch, not the hook's own trivial logic. A native OS command that just
# updates a file's mtime costs ~0.01s instead — state_store.py's own
# read_claude_status() reads that mtime directly, no Se7e code needs to
# run inside the hook itself for these two.
_TOUCH_WIRING = [
    ("PreToolUse", TOOL_START_FILE),
    ("PostToolUse", TOOL_END_FILE),
]


def _touch_command(path: Path) -> str:
    quoted = f'"{path}"'
    if sys.platform == "win32":
        return f"type nul > {quoted}"
    return f"touch {quoted}"


def settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def _is_ours(entry: dict) -> bool:
    for h in entry.get("hooks", []):
        # Case-insensitive: the dev-mode hook path is all-lowercase
        # ("se7e\hook.py"), but the installed exe's own folder/filename is
        # capitalized ("Programs\Se7e\Se7e.exe") — a case-sensitive match
        # silently finds nothing to uninstall against an installed build.
        if MARKER in h.get("command", "").lower():
            return True
    return False


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))  # let JSONDecodeError propagate
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object")
    return data


def _backup_and_write(path: Path, root: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        ts = time.time_ns()
        backup = path.with_name(f"{path.name}.se7e-bak-{ts}")
        backup.write_text(path.read_text())
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(root, indent=2))
    tmp.replace(path)


def is_installed(path: Path = None) -> bool:
    path = path or settings_path()
    try:
        root = _load(path)
    except (json.JSONDecodeError, ValueError, OSError):
        return False
    hooks = root.get("hooks", {})
    for event, entries in hooks.items():
        for entry in entries:
            if _is_ours(entry):
                return True
    return False


def install(hook_command: str, path: Path = None) -> str:
    path = path or settings_path()
    try:
        root = _load(path)
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        return f"refusing to touch {path}: existing file is not valid JSON ({exc}) — back it up and fix it manually"
    root.setdefault("hooks", {})
    for event, needs_matcher in WIRING:
        existing = [e for e in root["hooks"].get(event, []) if not _is_ours(e)]
        entry = {"hooks": [{"type": "command", "command": f"{hook_command} {event}", "timeout": 5}]}
        if needs_matcher:
            entry["matcher"] = "*"
        existing.append(entry)
        root["hooks"][event] = existing
    for event, touch_path in _TOUCH_WIRING:
        existing = [e for e in root["hooks"].get(event, []) if not _is_ours(e)]
        entry = {"hooks": [{"type": "command", "command": _touch_command(touch_path), "timeout": 2}]}
        existing.append(entry)
        root["hooks"][event] = existing
    total = len(WIRING) + len(_TOUCH_WIRING)
    _backup_and_write(path, root)
    return f"wrote {path} ({total} events)"


def uninstall(path: Path = None) -> str:
    path = path or settings_path()
    if not path.exists():
        return "settings.json does not exist, nothing to uninstall"
    try:
        root = _load(path)
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        return f"refusing to touch {path}: existing file is not valid JSON ({exc}) — back it up and fix it manually"
    hooks = root.get("hooks", {})
    removed = 0
    for event, entries in list(hooks.items()):
        filtered = [e for e in entries if not _is_ours(e)]
        removed += len(entries) - len(filtered)
        hooks[event] = filtered
    if removed == 0:
        return "no se7e hooks found, nothing to uninstall"
    _backup_and_write(path, root)
    return f"removed {removed} se7e hook(s)"
