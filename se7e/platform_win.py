"""Windows native window backend for the floating pill/tray popup — direct
ctypes/user32.dll calls for monitor work-area queries, topmost enforcement,
and cursor/window rect reads. See platform_mac.py for the macOS equivalent."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtWidgets import QWidget

from .geometry_types import WindowRect

MONITOR_DEFAULTTONEAREST = 2

_HWND_TOPMOST = -1
_SWP_NOMOVE = 0x0002
_SWP_NOSIZE = 0x0001
_SWP_NOACTIVATE = 0x0010

_user32 = ctypes.WinDLL("user32", use_last_error=True)

_get_window_rect = _user32.GetWindowRect
_get_window_rect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_get_window_rect.restype = wintypes.BOOL

_set_window_pos = _user32.SetWindowPos
_set_window_pos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
_set_window_pos.restype = wintypes.BOOL

_get_cursor_pos = _user32.GetCursorPos
_get_cursor_pos.argtypes = [ctypes.POINTER(wintypes.POINT)]
_get_cursor_pos.restype = wintypes.BOOL


class _MonitorInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


_monitor_from_point = _user32.MonitorFromPoint
_monitor_from_point.argtypes = [wintypes.POINT, wintypes.DWORD]
_monitor_from_point.restype = ctypes.c_void_p

_get_monitor_info = _user32.GetMonitorInfoW
_get_monitor_info.argtypes = [ctypes.c_void_p, ctypes.POINTER(_MonitorInfo)]
_get_monitor_info.restype = wintypes.BOOL


def _monitor_info_for_point(x: int, y: int) -> _MonitorInfo:
    handle = _monitor_from_point(
        wintypes.POINT(x, y),
        MONITOR_DEFAULTTONEAREST,
    )
    info = _MonitorInfo()
    info.cbSize = ctypes.sizeof(_MonitorInfo)
    if not _get_monitor_info(handle, ctypes.byref(info)):
        raise OSError(ctypes.get_last_error(), "GetMonitorInfoW failed")
    return info


def work_area_for_point(x: int, y: int) -> WindowRect:
    """Usable monitor bounds in physical pixels."""
    rect = _monitor_info_for_point(x, y).rcWork
    return WindowRect(rect.left, rect.top, rect.right, rect.bottom)


def monitor_rect_for_point(x: int, y: int) -> WindowRect:
    """Full monitor bounds (taskbar included) in physical pixels."""
    rect = _monitor_info_for_point(x, y).rcMonitor
    return WindowRect(rect.left, rect.top, rect.right, rect.bottom)


def read_window_rect(widget: QWidget) -> WindowRect:
    rect = wintypes.RECT()
    hwnd = int(widget.winId())

    if not _get_window_rect(hwnd, ctypes.byref(rect)):
        raise OSError(
            ctypes.get_last_error(),
            "GetWindowRect failed",
        )

    return WindowRect(
        rect.left,
        rect.top,
        rect.right,
        rect.bottom,
    )


def _set_native_geometry(
    widget: QWidget,
    x: int,
    y: int,
    width: int,
    height: int,
) -> None:
    _set_window_pos(
        int(widget.winId()),
        _HWND_TOPMOST,
        round(x),
        round(y),
        round(width),
        round(height),
        _SWP_NOACTIVATE,
    )


def _force_topmost(widget: QWidget) -> None:
    _set_window_pos(
        int(widget.winId()),
        _HWND_TOPMOST,
        0,
        0,
        0,
        0,
        _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE,
    )


def _cursor_position() -> tuple[int, int]:
    point = wintypes.POINT()
    if not _get_cursor_pos(ctypes.byref(point)):
        raise OSError(ctypes.get_last_error(), "GetCursorPos failed")
    return point.x, point.y


def _set_joins_all_spaces(widget: QWidget) -> None:
    """No-op on Windows: WS_EX_TOPMOST (already applied via
    SetWindowPos above) already keeps a window above a full-screen app
    without needing anything like macOS's per-Space window behavior."""
