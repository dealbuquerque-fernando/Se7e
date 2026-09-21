"""Plain geometry data types shared between floating_ui_qt.py and the
per-platform native window backends (platform_win.py / platform_mac.py) —
kept dependency-free to avoid a circular import between those modules."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WindowRect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top
