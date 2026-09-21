import sys
from pathlib import Path

import pytest

if sys.platform != "darwin":
    pytest.skip("macOS LaunchAgent autostart only exists on macOS", allow_module_level=True)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from se7e import autostart_mac as autostart

# A throwaway label/plist path, never the real one, so tests never touch the
# machine's actual autostart entry.
_TEST_LABEL = "com.se7e.autostart_test"


@pytest.fixture
def plist_path(tmp_path) -> Path:
    return tmp_path / f"{_TEST_LABEL}.plist"


def test_disabled_by_default(plist_path):
    assert autostart.is_enabled(_TEST_LABEL, plist_path) is False


def test_enable_then_is_enabled(plist_path):
    autostart.enable(_TEST_LABEL, plist_path)
    assert autostart.is_enabled(_TEST_LABEL, plist_path) is True


def test_enable_writes_launch_args_as_program_arguments(plist_path):
    autostart.enable(_TEST_LABEL, plist_path)

    import plistlib

    with plist_path.open("rb") as handle:
        data = plistlib.load(handle)

    assert data["Label"] == _TEST_LABEL
    assert data["ProgramArguments"] == autostart.launch_args()
    assert data["RunAtLoad"] is True


def test_disable_removes_the_file(plist_path):
    autostart.enable(_TEST_LABEL, plist_path)
    autostart.disable(_TEST_LABEL, plist_path)
    assert autostart.is_enabled(_TEST_LABEL, plist_path) is False
    assert not plist_path.exists()


def test_disable_missing_file_does_not_raise(plist_path):
    autostart.disable(_TEST_LABEL, plist_path)  # no file exists at all — must not raise


def test_launch_args_is_a_valid_argv_list():
    args = autostart.launch_args()
    assert args
    assert all(isinstance(arg, str) for arg in args)


def test_toggle_flips_and_returns_new_state(plist_path):
    assert autostart.toggle(_TEST_LABEL, plist_path) is True
    assert autostart.is_enabled(_TEST_LABEL, plist_path) is True
    assert autostart.toggle(_TEST_LABEL, plist_path) is False
    assert autostart.is_enabled(_TEST_LABEL, plist_path) is False
