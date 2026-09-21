import os
from pathlib import Path

APP_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "se7e"
STATE_FILE = APP_DIR / "state.json"
FLOATING_POSITION_FILE = APP_DIR / "floating_position.json"
SETTINGS_FILE = APP_DIR / "settings.json"
