"""macOS native window backend for the floating pill/tray popup.

Built entirely on Qt's own screen APIs rather than pyobjc/Cocoa:
QScreen.availableGeometry() already excludes the Dock and menu bar, doing
the same job Win32's GetMonitorInfo work-area does on Windows — so no extra
native dependency, and no need to deal with Cocoa's bottom-left-origin
coordinate system. Every function here keeps platform_win.py's "physical
pixels" contract (values already multiplied by the screen's scale factor),
converting to/from Qt's own logical pixels internally, so floating_ui_qt.py
needs no platform-specific math of its own.
"""

from __future__ import annotations

from PySide6.QtGui import QCursor, QGuiApplication, QScreen
from PySide6.QtWidgets import QWidget

from .geometry_types import WindowRect


def _physical_rect(geometry, scale: float) -> WindowRect:
    left = round(geometry.x() * scale)
    top = round(geometry.y() * scale)
    return WindowRect(
        left,
        top,
        left + round(geometry.width() * scale),
        top + round(geometry.height() * scale),
    )


def _physical_screen_rect(screen: QScreen) -> WindowRect:
    return _physical_rect(screen.geometry(), float(screen.devicePixelRatio()))


def _physical_available_rect(screen: QScreen) -> WindowRect:
    return _physical_rect(screen.availableGeometry(), float(screen.devicePixelRatio()))


def _screen_for_point(x: int, y: int) -> QScreen:
    """The QScreen whose physical bounds contain (x, y), falling back to
    the primary screen for a point just off every screen's edge."""
    for screen in QGuiApplication.screens():
        rect = _physical_screen_rect(screen)
        if rect.left <= x < rect.right and rect.top <= y < rect.bottom:
            return screen
    return QGuiApplication.primaryScreen()


def work_area_for_point(x: int, y: int) -> WindowRect:
    """Usable screen bounds (Dock/menu bar excluded) in physical pixels."""
    return _physical_available_rect(_screen_for_point(x, y))


def monitor_rect_for_point(x: int, y: int) -> WindowRect:
    """Full screen bounds (Dock/menu bar included) in physical pixels."""
    return _physical_screen_rect(_screen_for_point(x, y))


def read_window_rect(widget: QWidget) -> WindowRect:
    screen = widget.screen() or QGuiApplication.primaryScreen()
    return _physical_rect(widget.geometry(), float(screen.devicePixelRatio()))


def _set_native_geometry(
    widget: QWidget,
    x: int,
    y: int,
    width: int,
    height: int,
) -> None:
    scale = float(_screen_for_point(round(x), round(y)).devicePixelRatio())
    widget.setGeometry(
        round(x / scale),
        round(y / scale),
        round(width / scale),
        round(height / scale),
    )


def _force_topmost(widget: QWidget) -> None:
    # WindowStaysOnTopHint (already set on this window) is enough on its
    # own on macOS. This was originally widget.raise_(), mirroring
    # platform_win.py's "reassert topmost on every update" pattern — but
    # confirmed live, raise_() on macOS also activates the app, stealing
    # keyboard focus from whatever window the user was actually typing
    # into. floating_ui_qt.py calls this on every ~2s status-poll update,
    # so that was yanking focus back to Se7e continuously. A genuine
    # no-op here, unlike Windows, where SetWindowPos's topmost flag can
    # be stolen by another app and needs reasserting.
    pass


def _cursor_position() -> tuple[int, int]:
    pos = QCursor.pos()
    screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
    scale = float(screen.devicePixelRatio())
    return round(pos.x() * scale), round(pos.y() * scale)


def _set_joins_all_spaces(widget: QWidget) -> None:
    """Lets this window float over a full-screen app's own Space too.

    macOS puts a full-screen app on its own separate virtual desktop
    (Space) — a plain "always on top" window (Qt's WindowStaysOnTopHint)
    only applies within the Space it was created on, so without this the
    floating pill vanished as soon as any app went full-screen (confirmed
    live). Qt has no cross-platform equivalent of AppKit's
    NSWindowCollectionBehavior, so this reaches into Cocoa directly via
    the NSView pointer Qt's own winId() already returns on macOS —
    best-effort: on any failure the pill still works, it just won't
    follow into full-screen Spaces.

    Only actually visible when running as the packaged .app: macOS only
    grants this to an "accessory" app (LSUIElement=1 in Info.plist, set
    on the PyInstaller bundle — see packaging/se7e.spec), not to a
    regular foreground process. Confirmed live: running straight from
    source (`python -m se7e.app`, no Info.plist in play) sets this same
    collectionBehavior value with no error, but the pill still doesn't
    show over another app's full-screen Space — only testing the actual
    built .app exercises this correctly.
    """
    try:
        import objc
        from AppKit import (
            NSWindowCollectionBehaviorCanJoinAllSpaces,
            NSWindowCollectionBehaviorFullScreenAuxiliary,
        )

        view = objc.objc_object(c_void_p=int(widget.winId()))
        window = view.window()
        if window is None:
            return
        window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
        )
    except Exception:
        pass


def _hide_from_taskbar(widget: QWidget) -> None:
    """No-op on macOS: LSUIElement in Info.plist (packaging/se7e.spec)
    already keeps the whole process out of the Dock and Cmd+Tab switcher,
    for every window it ever shows — there's no per-window taskbar concept
    here the way Windows has one."""
