"""Real Windows autostart via the per-user Run registry key — no admin needed,
and easy to undo (deleting the value, which `disable()` does, is the whole
uninstall)."""

from __future__ import annotations

import sys
import winreg
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "se7e"


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _launch_pieces() -> tuple[str, str]:
    """(python executable to use, inline code to run) — shared by the Run-key
    command string and by a direct process relaunch (Settings' Apply button)."""
    exe = sys.executable
    windowless = exe.replace("python.exe", "pythonw.exe")
    if windowless != exe and Path(windowless).exists():
        exe = windowless
    # "-m se7e.app" only resolves the package from the current working
    # directory, which Windows does not guarantee at login — the absolute
    # project root is inserted on sys.path explicitly instead.
    root = _project_root()
    code = f"import sys; sys.path.insert(0, r'{root}'); from se7e.app import main; main()"
    return exe, code


def launch_args() -> list[str]:
    """[executable, "-c", code] — safe to pass straight to subprocess.Popen,
    no shell involved."""
    exe, code = _launch_pieces()
    return [exe, "-c", code]


def run_key_command() -> str:
    """The same launch, quoted as a single string for the registry Run key."""
    exe, code = _launch_pieces()
    return f'"{exe}" -c "{code}"'


def is_enabled(run_key: str = RUN_KEY, value_name: str = VALUE_NAME) -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, value_name)
    except OSError:
        return False
    return value == run_key_command()


def enable(run_key: str = RUN_KEY, value_name: str = VALUE_NAME) -> None:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, run_key) as key:
        winreg.SetValueEx(key, value_name, 0, winreg.REG_SZ, run_key_command())


def disable(run_key: str = RUN_KEY, value_name: str = VALUE_NAME) -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, value_name)
    except OSError:
        pass


def toggle(run_key: str = RUN_KEY, value_name: str = VALUE_NAME) -> bool:
    """Flips the setting and returns the resulting state."""
    if is_enabled(run_key, value_name):
        disable(run_key, value_name)
        return False
    enable(run_key, value_name)
    return True
