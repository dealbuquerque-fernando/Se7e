"""Real macOS autostart via a per-user LaunchAgent .plist in
~/Library/LaunchAgents — no admin needed, and easy to undo (removing the
file, which `disable()` does, is the whole uninstall)."""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

LABEL = "com.se7e.app"


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _launch_agents_dir() -> Path:
    return Path.home() / "Library" / "LaunchAgents"


def _plist_path(label: str = LABEL) -> Path:
    return _launch_agents_dir() / f"{label}.plist"


def launch_args() -> list[str]:
    """Safe to pass straight to subprocess.Popen, and used verbatim as a
    LaunchAgent's ProgramArguments — no shell involved either way."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    # "-m se7e.app" only resolves the package from the current working
    # directory, which launchd does not guarantee at login — the absolute
    # project root is inserted on sys.path explicitly instead.
    root = _project_root()
    code = f"import sys; sys.path.insert(0, '{root}'); from se7e.app import main; main()"
    return [sys.executable, "-c", code]


def _plist_data(label: str) -> dict:
    return {
        "Label": label,
        "ProgramArguments": launch_args(),
        "RunAtLoad": True,
    }


def _launchctl(*args: str) -> None:
    try:
        subprocess.run(
            ["launchctl", *args],
            capture_output=True,
            check=False,
        )
    except OSError:
        pass  # launchctl missing/unavailable — the plist file is still the source of truth


def is_enabled(label: str = LABEL, plist_path: Path | None = None) -> bool:
    path = plist_path or _plist_path(label)
    try:
        with path.open("rb") as handle:
            data = plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException):
        return False
    return data.get("ProgramArguments") == launch_args()


def enable(label: str = LABEL, plist_path: Path | None = None) -> None:
    # plist_path is only ever overridden by tests, against a throwaway
    # tmp_path — registering that with the real launchd session would
    # actually spawn the app (RunAtLoad) as a side effect of running the
    # test suite, so the real launchctl call only fires for the real path.
    is_real_target = plist_path is None
    path = plist_path or _plist_path(label)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        plistlib.dump(_plist_data(label), handle)
    if is_real_target:
        _launchctl("bootstrap", f"gui/{os.getuid()}", str(path))


def disable(label: str = LABEL, plist_path: Path | None = None) -> None:
    is_real_target = plist_path is None
    path = plist_path or _plist_path(label)
    if is_real_target:
        _launchctl("bootout", f"gui/{os.getuid()}/{label}")
    try:
        path.unlink()
    except OSError:
        pass


def toggle(label: str = LABEL, plist_path: Path | None = None) -> bool:
    """Flips the setting and returns the resulting state."""
    if is_enabled(label, plist_path):
        disable(label, plist_path)
        return False
    enable(label, plist_path)
    return True
