from pathlib import Path
from types import SimpleNamespace
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import subprocess
from se7e import app as app_module
from se7e import autostart


def _bare_app():
    """App.__new__ bypasses __init__ (which needs a live Qt event loop);
    only the attributes apply_and_restart()/quit() actually touch are set.
    _ui_lock is a real RLock: "with obj:" looks up __enter__/__exit__ on the
    type, not the instance, so a SimpleNamespace fake won't satisfy it."""
    instance = app_module.App.__new__(app_module.App)
    instance.shutdown_event = SimpleNamespace(set=lambda: None)
    instance.icon = SimpleNamespace(stop=lambda: None)
    instance._ui_lock = threading.RLock()
    instance._qt_invoker = None
    instance.floating = None
    instance.settings = SimpleNamespace(destroy=lambda: None)
    instance.popup = SimpleNamespace(destroy=lambda: None)
    return instance


def test_apply_and_restart_spawns_the_launch_args_then_quits():
    instance = _bare_app()
    popen_calls = []
    destroyed = []
    instance.settings.destroy = lambda: destroyed.append(True)
    original_popen = subprocess.Popen
    app_module.subprocess.Popen = lambda *a, **k: popen_calls.append((a, k))
    try:
        instance.apply_and_restart()
    finally:
        app_module.subprocess.Popen = original_popen

    assert len(popen_calls) == 1
    (args, kwargs) = popen_calls[0]
    assert args[0] == autostart.launch_args()
    assert destroyed == [True]  # quit() ran far enough to reach UI teardown


def test_apply_and_restart_still_quits_if_the_relaunch_fails_to_spawn():
    instance = _bare_app()

    def _raise(*a, **k):
        raise OSError("no python found")

    original_popen = subprocess.Popen
    app_module.subprocess.Popen = _raise
    destroyed = []
    instance.settings.destroy = lambda: destroyed.append(True)
    try:
        instance.apply_and_restart()  # must not raise even though Popen failed
    finally:
        app_module.subprocess.Popen = original_popen

    assert destroyed == [True]


if __name__ == "__main__":
    test_apply_and_restart_spawns_the_launch_args_then_quits()
    test_apply_and_restart_still_quits_if_the_relaunch_fails_to_spawn()
    print("OK")
