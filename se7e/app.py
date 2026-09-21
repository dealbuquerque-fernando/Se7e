import ctypes
import subprocess
import sys
import threading
import time
from pathlib import Path

import pystray
from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from . import autostart, config, hooks_install, i18n, settings_store, state_store, ui_colors, usage_claude, usage_codex
from .floating_ui_qt import FloatingWidget
from .settings_window_qt import SettingsWindow
from .tray_ui_qt import TrayPopup, make_icon_image

USAGE_POLL_SECONDS = 45
STATUS_POLL_SECONDS = 2
_ICON_PATH = config.resource_dir() / "assets" / "se7e_icon_v2.ico"

# Without a distinct AppUserModelID, Windows groups this taskbar entry under
# python.exe's own generic identity instead of this app's — it then falls
# back to a generic/blank icon for the taskbar button no matter what
# QWidget.setWindowIcon()/QApplication.setWindowIcon() are set to (both
# were already tried and didn't fix it). Must be set before any window is
# created, ideally as the very first thing the process does.
#
# This exact string must match packaging/installer.iss's MyAppUserModelID:
# without a Start Menu/Desktop shortcut carrying the same ID, Explorer has
# no shortcut to resolve the group's real icon from on the first window
# this process ever shows, and falls back to a provisional/generic icon
# for about a second before correcting it (diagnosed with Codex's help,
# 2026-09-21 — see the removed WM_SETICON/hide-show dead ends this
# replaced in floating_ui_qt.py's git history for what did NOT fix it).
# No trailing version/date suffix — a stable ID lets Windows Start
# menu/taskbar pins survive an app upgrade instead of orphaning them.
APP_USER_MODEL_ID = "Se7eQt.TrayApp"

try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
except (AttributeError, OSError):
    pass  # not on Windows, or the call isn't available — cosmetic only


class _QtInvoker(QObject):
    """Marshals pystray/polling callbacks onto QApplication's thread."""

    invoke = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.invoke.connect(self._call, Qt.ConnectionType.QueuedConnection)

    @Slot(object)
    def _call(self, callback) -> None:
        callback()


def hook_command() -> str:
    # Frozen (PyInstaller) build: the exe itself has a hidden "hook"
    # subcommand (see main() below), so there's no python.exe or loose
    # hook.py file needed on the machine that installed the app.
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" hook'
    hook_script = str(Path(__file__).with_name("hook.py"))
    return f'"{sys.executable}" "{hook_script}"'


class App:
    def __init__(self):
        self.shutdown_event = threading.Event()
        self._ui_lock = threading.RLock()
        self._qt_invoker = None
        self.floating = None
        self.transparent = False
        self.claude_usage = {"five_hour": None, "week": None}
        self.codex_usage = {"five_hour": None, "week": None}
        self.codex_status = "parado"
        self.last_usage_poll = 0.0
        self.last_usage_ok = 0.0
        self._refresh_settings()
        self.popup = TrayPopup(
            self.toggle_floating, self.toggle_transparent, self.quit, lang=self.lang, theme=self.theme
        )
        self.settings = SettingsWindow(lang=self.lang, on_apply_restart=self.apply_and_restart)
        self.icon = pystray.Icon(
            "se7e",
            make_icon_image(ui_colors.color_for_status("parado")),
            "se7e",
            menu=pystray.Menu(
                pystray.MenuItem(i18n.t("tray_menu_main_panel", self.lang), self.toggle_popup),
                pystray.MenuItem(i18n.t("tray_menu_compact_panel", self.lang), self.toggle_floating),
                pystray.MenuItem(i18n.t("tray_menu_settings", self.lang), self.toggle_settings),
                pystray.MenuItem(i18n.t("tray_menu_quit", self.lang), self.quit),
            ),
        )

    def _queue_on_gui(self, callback) -> bool:
        qt_app = QApplication.instance()
        invoker = getattr(self, "_qt_invoker", None)
        if (
            qt_app is not None
            and invoker is not None
            and QThread.currentThread() is not qt_app.thread()
        ):
            invoker.invoke.emit(callback)
            return True
        return False

    def _refresh_settings(self) -> None:
        settings = settings_store.load()
        self.lang = settings.get("language", i18n.DEFAULT_LANGUAGE)
        self.theme = settings.get("theme", settings_store.DEFAULTS["theme"])
        self.floating_orientation = settings.get(
            "floating_orientation", settings_store.DEFAULTS["floating_orientation"]
        )

    def toggle_popup(self) -> None:
        if self._queue_on_gui(self.toggle_popup):
            return
        with self._ui_lock:
            self._refresh_settings()
            self.popup.set_language(self.lang)
            self.popup.set_theme(self.theme)
            self.popup.toggle()

    def toggle_floating(self) -> None:
        if self._queue_on_gui(self.toggle_floating):
            return
        with self._ui_lock:
            self._refresh_settings()
            if self.floating is None:
                self.floating = FloatingWidget(
                    lang=self.lang, theme=self.theme, orientation=self.floating_orientation
                )
                self.floating.set_transparent(self.transparent)
            else:
                self.floating.destroy()
                self.floating = None

    def toggle_settings(self) -> None:
        if self._queue_on_gui(self.toggle_settings):
            return
        with self._ui_lock:
            self.settings.toggle()

    def apply_and_restart(self) -> None:
        """The Settings "Aplicar" button: relaunch a fresh instance (so it
        picks up every setting from scratch) and quit this one."""
        try:
            subprocess.Popen(
                autostart.launch_args(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            pass  # ponytail: a failed relaunch still shouldn't trap the user in a dead app
        self.quit()

    def toggle_transparent(self) -> None:
        if self._queue_on_gui(self.toggle_transparent):
            return
        with self._ui_lock:
            self.transparent = not self.transparent
            self.popup.set_transparent(self.transparent)
            if self.floating is not None:
                self.floating.set_transparent(self.transparent)

    def quit(self) -> None:
        self.shutdown_event.set()
        self.icon.stop()
        if self._queue_on_gui(self._destroy_ui):
            return
        self._destroy_ui()

    def _destroy_ui(self) -> None:
        with self._ui_lock:
            if self.floating is not None:
                self.floating.destroy()
                self.floating = None
            self.settings.destroy()
            self.popup.destroy()
        qt_app = QApplication.instance()
        if qt_app is not None:
            qt_app.quit()

    def poll_loop(self) -> None:
        while not self.shutdown_event.is_set():
            try:
                claude_status = state_store.read_claude_status()["status"]
                self.codex_status = usage_codex.get_status()
                now = time.time()
                if now - self.last_usage_poll > USAGE_POLL_SECONDS:
                    new_claude = usage_claude.get_usage()
                    new_codex = usage_codex.get_usage()
                    if not new_claude.get("stale"):
                        self.claude_usage = new_claude
                    if not new_codex.get("stale"):
                        self.codex_usage = new_codex
                    if not new_claude.get("stale") or not new_codex.get("stale"):
                        self.last_usage_ok = now
                    self.last_usage_poll = now
                elapsed = int(time.time() - self.last_usage_ok)
                updated_text = (
                    i18n.t("popup_updated_ago", self.lang, s=elapsed)
                    if elapsed < 120
                    else i18n.t("popup_updated_stale", self.lang)
                )
                self._refresh_ui(claude_status, updated_text)
                self.icon.icon = make_icon_image(ui_colors.tray_icon_color(claude_status, self.codex_status))
            except Exception:
                pass  # ponytail: never let one bad poll kill the loop
            if self.shutdown_event.wait(STATUS_POLL_SECONDS):
                return

    def _refresh_ui(self, claude_status: str, updated_text: str) -> None:
        if self._queue_on_gui(lambda: self._refresh_ui(claude_status, updated_text)):
            return
        with self._ui_lock:
            self.popup.update(
                claude_status, self.claude_usage.get("five_hour"), self.claude_usage.get("week"),
                self.codex_status, self.codex_usage.get("five_hour"), self.codex_usage.get("week"),
                updated_text,
                claude_connected=self.claude_usage.get("connected", True),
                codex_connected=self.codex_usage.get("connected", True),
            )
            if self.floating is not None:
                self.floating.update(
                    claude_status, self.claude_usage.get("five_hour"),
                    self.codex_status, self.codex_usage.get("five_hour"),
                    claude_connected=self.claude_usage.get("connected", True),
                    codex_connected=self.codex_usage.get("connected", True),
                )

    def _start_background_tasks(self) -> None:
        threading.Thread(
            target=self.poll_loop,
            name="se7e-poll",
            daemon=True,
        ).start()
        threading.Thread(
            target=self.icon.run,
            name="se7e-pystray",
            daemon=True,
        ).start()

    def run(self) -> None:
        qt_app = QApplication.instance() or QApplication(sys.argv)
        # Windows' native style ("windowsvista") ignores some QSS color
        # overrides for popups/list views (e.g. a QComboBox dropdown's
        # hover/selection color) — Fusion is Qt's own cross-platform style
        # and actually respects the stylesheet, so colors set in
        # settings_window_qt.py's QSS render consistently instead of
        # silently falling back to the OS theme's own (invisible-in-light)
        # default.
        qt_app.setStyle("Fusion")
        qt_app.setQuitOnLastWindowClosed(False)
        qt_app.setWindowIcon(QIcon(str(_ICON_PATH)))
        self._qt_invoker = _QtInvoker()

        try:
            self._start_background_tasks()
            qt_app.exec()
        finally:
            self.shutdown_event.set()
            self.icon.stop()


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "install-hooks":
        print(hooks_install.install(hook_command()))
        return
    if len(sys.argv) > 1 and sys.argv[1] == "uninstall-hooks":
        print(hooks_install.uninstall())
        return
    if len(sys.argv) > 1 and sys.argv[1] == "hook":
        from . import hook

        hook.main(sys.argv[2] if len(sys.argv) > 2 else "")
        return
    App().run()


if __name__ == "__main__":
    main()
