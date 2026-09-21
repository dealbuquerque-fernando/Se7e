"""Autostart dispatcher: same public interface (is_enabled, enable, disable,
toggle, launch_args) on every platform, backed by a real per-OS mechanism —
the Windows Run registry key, or a macOS LaunchAgent .plist."""

from __future__ import annotations

import sys

if sys.platform == "win32":
    from .autostart_win import (  # noqa: F401
        RUN_KEY,
        VALUE_NAME,
        disable,
        enable,
        is_enabled,
        launch_args,
        run_key_command,
        toggle,
    )
elif sys.platform == "darwin":
    from .autostart_mac import (  # noqa: F401
        LABEL,
        disable,
        enable,
        is_enabled,
        launch_args,
        toggle,
    )
else:
    raise NotImplementedError(f"se7e.autostart has no implementation for {sys.platform!r}")
