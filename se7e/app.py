import ctypes
import random
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

# Base interval between usage-percentage polls. Two independent instances
# (e.g. this Mac and a Windows machine, same account) each count this from
# their own launch time — if they tend to open around the same time, their
# polls land within the same second on every cycle, doubling the request
# load against the account's usage endpoint at that exact instant instead
# of spreading it out. USAGE_POLL_JITTER_SECONDS below decorrelates them.
USAGE_POLL_SECONDS = 60
USAGE_POLL_JITTER_SECONDS = 10  # actual interval is USAGE_POLL_SECONDS +/- this, re-rolled every cycle
# How long the "updated Ns ago" line waits before calling the data stale —
# needs enough slack to absorb one missed poll (a single rate-limit cooldown
# is 60s) without flashing stale for something that's about to self-correct
# on its own within a cycle or two.
USAGE_STALE_THRESHOLD_SECONDS = 180
STATUS_POLL_SECONDS = 2
# Same 300ms rate as the popup/floating dots' own blink timer
# (tray_ui_qt.py's TrayPopup._ensure_blink_timer) — a separate loop from
# STATUS_POLL_SECONDS so the blink stays smooth without polling
# claude_status/codex_status themselves any more often than before.
TRAY_BLINK_INTERVAL_SECONDS = 0.3
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
        self.claude_status = "parado"
        self.codex_status = "parado"
        self._tray_blink_on = True
        self.last_usage_poll = 0.0
        self._next_usage_poll_interval = USAGE_POLL_SECONDS
        self.last_claude_usage_ok = 0.0
        self.last_codex_usage_ok = 0.0
        self._refresh_settings()
        self.popup = TrayPopup(
            self.toggle_floating, self.toggle_transparent, self.quit, lang=self.lang, theme=self.theme
        )
        self.settings = SettingsWindow(
            lang=self.lang,
            on_apply_restart=self.apply_and_restart,
            on_uninstall=self.uninstall_and_quit,
        )
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

    def uninstall_and_quit(self) -> None:
        """The Settings "Desinstalar" button: remove this app's Claude Code
        hooks and autostart entry, then quit. There's no OS-level uninstall
        event to hang this off of on every platform (a plain .app dragged
        to the Trash on macOS runs no code at all), so this in-app action
        is the actual uninstall hook — the user finishes by removing the
        app itself, same as the installer's uninstaller does on Windows."""
        try:
            hooks_install.uninstall()
        except OSError:
            pass
        try:
            if autostart.is_enabled():
                autostart.disable()
        except OSError:
            pass
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
                self.claude_status = state_store.read_claude_status()["status"]
                self.codex_status = usage_codex.get_status()
                now = time.time()
                if now - self.last_usage_poll > self._next_usage_poll_interval:
                    new_claude = usage_claude.get_usage()
                    new_codex = usage_codex.get_usage()
                    if not new_claude.get("stale"):
                        self.claude_usage = new_claude
                        self.last_claude_usage_ok = now
                    if not new_codex.get("stale"):
                        self.codex_usage = new_codex
                        self.last_codex_usage_ok = now
                    self.last_usage_poll = now
                    self._next_usage_poll_interval = USAGE_POLL_SECONDS + random.uniform(
                        -USAGE_POLL_JITTER_SECONDS, USAGE_POLL_JITTER_SECONDS
                    )
                elapsed = int(time.time() - self._oldest_connected_usage_ok())
                updated_text = (
                    i18n.t("popup_updated_ago", self.lang, s=elapsed)
                    if elapsed < USAGE_STALE_THRESHOLD_SECONDS
                    else i18n.t("popup_updated_stale", self.lang)
                )
                self._refresh_ui(self.claude_status, updated_text)
            except Exception:
                pass  # ponytail: never let one bad poll kill the loop
            if self.shutdown_event.wait(STATUS_POLL_SECONDS):
                return

    def _tray_icon_color(self) -> str:
        """The active color, held solid while only "esperando voce" (idle)
        is in play, or flipped every other tick to the idle/gray color
        while genuinely blink-worthy (working or needing a decision) — see
        ui_colors.tray_icon_should_blink()."""
        active_color = ui_colors.tray_icon_color(self.claude_status, self.codex_status)
        if not ui_colors.tray_icon_should_blink(self.claude_status, self.codex_status):
            self._tray_blink_on = True
            return active_color
        color = active_color if self._tray_blink_on else ui_colors.STATUS_COLORS["parado"]
        self._tray_blink_on = not self._tray_blink_on
        return color

    def _tray_blink_loop(self) -> None:
        """Runs on its own faster cadence than poll_loop's status reads
        (see TRAY_BLINK_INTERVAL_SECONDS) so the tray badge's blink looks
        as smooth as the popup/floating dots' own blink, without polling
        claude_status/codex_status themselves any more often than before."""
        while not self.shutdown_event.is_set():
            try:
                self.icon.icon = make_icon_image(self._tray_icon_color())
            except Exception:
                pass  # ponytail: never let one bad tick kill the loop
            if self.shutdown_event.wait(TRAY_BLINK_INTERVAL_SECONDS):
                return

    def _oldest_connected_usage_ok(self) -> float:
        """One shared "updated Ns ago" line covers both providers, so it
        has to reflect whichever CONNECTED one is least fresh — tracking a
        single combined timestamp (the old design) let either provider's
        success reset it even while the other sat on stale/rate-limited
        data, understating how old that data actually was. A provider
        that's simply not connected shows its own "não conectado" label
        instead of a percentage, so it doesn't belong in this freshness
        check."""
        connected_ok_times = [
            ok_time
            for ok_time, usage in (
                (self.last_claude_usage_ok, self.claude_usage),
                (self.last_codex_usage_ok, self.codex_usage),
            )
            if usage.get("connected", True)
        ]
        return min(connected_ok_times) if connected_ok_times else 0.0

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
            target=self._tray_blink_loop,
            name="se7e-tray-blink",
            daemon=True,
        ).start()
        # macOS's AppKit (which draws the menu-bar status item) only
        # tolerates being driven from the main thread — icon.run() here in
        # a background thread is fine on Windows, but on macOS it crashes
        # as soon as the icon is torn down (confirmed live: SIGILL inside
        # -[NSStatusItem _uninstall], called from the se7e-pystray thread
        # during quit/Apply-restart). run_detached() in run() below is
        # pystray's own documented way to hand the icon to another
        # toolkit's main-thread loop instead of running its own.
        if sys.platform != "darwin":
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
            if sys.platform == "darwin":
                # Registers the status item without starting pystray's own
                # native run loop — it shares the same NSApplication that
                # qt_app.exec() below is about to drive on this (the main)
                # thread, so both the tray icon and every Qt window get
                # their events pumped from the one loop.
                self.icon.run_detached()
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
