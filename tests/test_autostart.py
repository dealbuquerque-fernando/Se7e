import sys
import winreg
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from se7e import autostart

# A throwaway HKCU subkey, never the real Run key, so tests never touch the
# machine's actual autostart entry.
_TEST_KEY = r"Software\se7e_autostart_test"


def _cleanup():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _TEST_KEY, 0, winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, autostart.VALUE_NAME)
            except OSError:
                pass
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, _TEST_KEY)
    except OSError:
        pass


def test_disabled_by_default():
    _cleanup()
    try:
        assert autostart.is_enabled(_TEST_KEY) is False
    finally:
        _cleanup()


def test_enable_then_is_enabled():
    _cleanup()
    try:
        autostart.enable(_TEST_KEY)
        assert autostart.is_enabled(_TEST_KEY) is True
    finally:
        _cleanup()


def test_disable_removes_the_value():
    _cleanup()
    try:
        autostart.enable(_TEST_KEY)
        autostart.disable(_TEST_KEY)
        assert autostart.is_enabled(_TEST_KEY) is False
    finally:
        _cleanup()


def test_disable_missing_key_does_not_raise():
    _cleanup()
    autostart.disable(_TEST_KEY)  # no key/value exists at all — must not raise


def test_launch_args_matches_the_run_key_command_pieces():
    exe, code_flag, code = autostart.launch_args()
    assert code_flag == "-c"
    assert autostart.run_key_command() == f'"{exe}" -c "{code}"'


def test_toggle_flips_and_returns_new_state():
    _cleanup()
    try:
        assert autostart.toggle(_TEST_KEY) is True
        assert autostart.is_enabled(_TEST_KEY) is True
        assert autostart.toggle(_TEST_KEY) is False
        assert autostart.is_enabled(_TEST_KEY) is False
    finally:
        _cleanup()


if __name__ == "__main__":
    test_disabled_by_default()
    test_enable_then_is_enabled()
    test_disable_removes_the_value()
    test_disable_missing_key_does_not_raise()
    test_launch_args_matches_the_run_key_command_pieces()
    test_toggle_flips_and_returns_new_state()
    print("OK")
