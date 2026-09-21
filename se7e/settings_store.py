import json
from pathlib import Path

from .config import SETTINGS_FILE

DEFAULTS = {
    "language": "pt",
    "theme": "dark",
    "floating_orientation": "horizontal",
}

SUPPORTED_THEMES = ("dark", "light")
SUPPORTED_ORIENTATIONS = ("horizontal", "vertical")


def load(path: Path = SETTINGS_FILE) -> dict:
    if not path.exists():
        return dict(DEFAULTS)
    try:
        data = json.loads(path.read_text())
    except (ValueError, OSError):
        return dict(DEFAULTS)
    if not isinstance(data, dict):
        return dict(DEFAULTS)
    merged = dict(DEFAULTS)
    merged.update(data)
    return merged


def save(updates: dict, path: Path = SETTINGS_FILE) -> dict:
    current = load(path)
    current.update(updates)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(current))
    tmp.replace(path)
    return current
