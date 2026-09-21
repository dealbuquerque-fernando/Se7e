import os
import sys
from pathlib import Path

if sys.platform == "darwin":
    APP_DIR = Path.home() / "Library" / "Application Support" / "se7e"
else:
    APP_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "se7e"
STATE_FILE = APP_DIR / "state.json"
FLOATING_POSITION_FILE = APP_DIR / "floating_position.json"
SETTINGS_FILE = APP_DIR / "settings.json"


def resource_dir() -> Path:
    """Base directory for bundled files (assets/, fonts, icons).

    A PyInstaller build doesn't extract pure-Python modules to real files,
    so __file__-relative lookups break there; sys._MEIPASS is PyInstaller's
    own answer to "where did the bundled data actually land" — the extracted
    temp dir for --onefile, or the _internal/ folder for --onedir.
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "se7e"
    return Path(__file__).resolve().parent
