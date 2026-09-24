from pathlib import Path
from types import SimpleNamespace
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import subprocess
from se7e import app as app_module
from se7e import autostart
from se7e import usage_claude


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


def test_oldest_connected_usage_ok_reflects_the_stale_provider_not_the_fresh_one():
    """The bug this exists to fix: Codex succeeding every poll must not
    make the shared "updated Ns ago" line claim freshness while Claude
    alone is sitting on old, rate-limited data."""
    instance = _bare_app()
    instance.claude_usage = {"connected": True, "stale": True}  # rate-limited, still showing an old %
    instance.codex_usage = {"connected": True, "stale": False}
    instance.last_claude_usage_ok = 100.0  # old
    instance.last_codex_usage_ok = 500.0  # just succeeded
    assert instance._oldest_connected_usage_ok() == 100.0


def test_oldest_connected_usage_ok_ignores_a_disconnected_provider():
    """A provider with no credentials at all shows its own "não conectado"
    label instead of a percentage — it shouldn't drag the other, working
    provider's freshness display down forever."""
    instance = _bare_app()
    instance.claude_usage = {"connected": False}
    instance.codex_usage = {"connected": True, "stale": False}
    instance.last_claude_usage_ok = 0.0  # never succeeded, never will
    instance.last_codex_usage_ok = 500.0
    assert instance._oldest_connected_usage_ok() == 500.0


def test_oldest_connected_usage_ok_both_disconnected_returns_zero():
    instance = _bare_app()
    instance.claude_usage = {"connected": False}
    instance.codex_usage = {"connected": False}
    instance.last_claude_usage_ok = 0.0
    instance.last_codex_usage_ok = 0.0
    assert instance._oldest_connected_usage_ok() == 0.0


def test_tray_icon_color_blinks_while_working():
    """Blink-worthy statuses ("trabalhando"/"esperando decisao") must
    alternate between the active color and the idle/gray color from one
    tick to the next, not stay solid."""
    instance = _bare_app()
    instance.claude_status = "trabalhando"
    instance.codex_status = "parado"
    instance._tray_blink_on = True
    first = instance._tray_icon_color()
    second = instance._tray_icon_color()
    third = instance._tray_icon_color()
    assert first == app_module.ui_colors.tray_icon_color("trabalhando", "parado")
    assert second == app_module.ui_colors.STATUS_COLORS["parado"]
    assert third == first


def test_tray_icon_color_stays_solid_while_only_idle():
    """"esperando voce" alone (no working/decision status on either
    provider) must never blink — the badge stays a static active color."""
    instance = _bare_app()
    instance.claude_status = "esperando voce"
    instance.codex_status = "parado"
    instance._tray_blink_on = True
    first = instance._tray_icon_color()
    second = instance._tray_icon_color()
    expected = app_module.ui_colors.tray_icon_color("esperando voce", "parado")
    assert first == expected
    assert second == expected


def test_force_usage_refresh_clears_rate_limit_cooldown_and_poll_timer():
    """The popup's manual reload button: must skip both the periodic poll
    wait and Claude's own 429 backoff, so the very next poll_loop tick
    retries immediately instead of waiting out up to 900s."""
    instance = _bare_app()
    instance.last_usage_poll = 999999999.0
    original_until = usage_claude._rate_limit_until
    usage_claude._rate_limit_until = 999999999.0
    try:
        instance.force_usage_refresh()
        assert instance.last_usage_poll == 0.0
        assert usage_claude._rate_limit_until == 0.0
    finally:
        usage_claude._rate_limit_until = original_until


def test_oldest_connected_usage_ok_missing_connected_key_defaults_true():
    """Before the very first successful poll, claude_usage/codex_usage are
    still their __init__ placeholders with no "connected" key at all —
    must be treated as connected (i.e. included), not silently dropped."""
    instance = _bare_app()
    instance.claude_usage = {"five_hour": None, "week": None}
    instance.codex_usage = {"five_hour": None, "week": None}
    instance.last_claude_usage_ok = 0.0
    instance.last_codex_usage_ok = 0.0
    assert instance._oldest_connected_usage_ok() == 0.0


if __name__ == "__main__":
    test_apply_and_restart_spawns_the_launch_args_then_quits()
    test_apply_and_restart_still_quits_if_the_relaunch_fails_to_spawn()
    test_oldest_connected_usage_ok_reflects_the_stale_provider_not_the_fresh_one()
    test_oldest_connected_usage_ok_ignores_a_disconnected_provider()
    test_oldest_connected_usage_ok_both_disconnected_returns_zero()
    test_oldest_connected_usage_ok_missing_connected_key_defaults_true()
    test_tray_icon_color_blinks_while_working()
    test_tray_icon_color_stays_solid_while_only_idle()
    test_force_usage_refresh_clears_rate_limit_cooldown_and_poll_timer()
    print("OK")
