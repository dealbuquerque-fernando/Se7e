import json
import tempfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from se7e import hooks_install

COMMAND = 'python "C:\\se7e\\hook.py"'


def test_install_writes_only_the_narrow_event_set():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "settings.json"
        hooks_install.install(COMMAND, path=path)
        data = json.loads(path.read_text())
        assert set(data["hooks"].keys()) == {
            "SessionStart", "UserPromptSubmit", "Notification", "Stop", "SessionEnd",
        }
        assert "PreToolUse" not in data["hooks"]
        assert "PostToolUse" not in data["hooks"]


def test_install_backs_up_existing_file():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "settings.json"
        path.write_text(json.dumps({"hooks": {}}))
        hooks_install.install(COMMAND, path=path)
        backups = list(Path(d).glob("settings.json.se7e-bak-*"))
        assert len(backups) == 1


def test_install_preserves_other_tools_hooks():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "settings.json"
        path.write_text(json.dumps({
            "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "someone-elses-hook", "timeout": 5}]}]}
        }))
        hooks_install.install(COMMAND, path=path)
        data = json.loads(path.read_text())
        commands = [h["command"] for entry in data["hooks"]["Stop"] for h in entry["hooks"]]
        assert "someone-elses-hook" in commands
        assert any("se7e" in c or COMMAND in c for c in commands)


def test_uninstall_removes_only_our_entries():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "settings.json"
        hooks_install.install(COMMAND, path=path)
        assert hooks_install.is_installed(path=path)
        hooks_install.uninstall(path=path)
        assert not hooks_install.is_installed(path=path)


def test_successive_installs_create_distinct_backups():
    """Verify nanosecond-precision backup filenames prevent collision on rapid writes."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "settings.json"
        # Create initial file so backups will be created
        path.write_text(json.dumps({"hooks": {}}))

        # First install creates a backup
        hooks_install.install(COMMAND, path=path)
        backups_after_first = list(Path(d).glob("settings.json.se7e-bak-*"))
        assert len(backups_after_first) == 1, "First install should create exactly one backup"
        first_backup = backups_after_first[0]

        # Second install in quick succession should create a new distinct backup
        hooks_install.install(COMMAND, path=path)
        backups_after_second = list(Path(d).glob("settings.json.se7e-bak-*"))
        assert len(backups_after_second) == 2, "Second install should create a second backup with different name"
        assert first_backup in backups_after_second, "First backup should still exist"


def test_is_installed_requires_actual_hook_entry_not_string_match():
    """Verify is_installed() checks hook entries precisely, not raw text search."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "settings.json"

        # Create a file with "se7e" string in unrelated location
        path.write_text(json.dumps({
            "unrelated_key": "this mentions se7e somewhere",
            "hooks": {}
        }))
        # Should return False because the marker is not in an actual hook command
        assert not hooks_install.is_installed(path=path), \
            "is_installed() should return False when 'se7e' appears outside hook entries"

        # Install our hooks
        hooks_install.install(COMMAND, path=path)
        # Now should return True because we have an actual hook with the marker
        assert hooks_install.is_installed(path=path), \
            "is_installed() should return True after real hook installation"


def test_install_refuses_corrupt_json_and_leaves_file_untouched():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "settings.json"
        corrupt = "{not valid json"
        path.write_text(corrupt)
        result = hooks_install.install(COMMAND, path=path)
        assert "refus" in result.lower()
        assert path.read_text() == corrupt, "corrupt file must be left byte-for-byte unchanged"
        assert not list(Path(d).glob("settings.json.se7e-bak-*")), "must not back up a file it refused to touch"


def test_uninstall_refuses_corrupt_json_and_leaves_file_untouched():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "settings.json"
        corrupt = "{not valid json"
        path.write_text(corrupt)
        result = hooks_install.uninstall(path=path)
        assert "refus" in result.lower()
        assert path.read_text() == corrupt, "corrupt file must be left byte-for-byte unchanged"
        assert not list(Path(d).glob("settings.json.se7e-bak-*")), "must not back up a file it refused to touch"


def test_install_refuses_non_dict_json_and_leaves_file_untouched():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "settings.json"
        non_dict = "[]"
        path.write_text(non_dict)
        result = hooks_install.install(COMMAND, path=path)
        assert "refus" in result.lower()
        assert path.read_text() == non_dict


def test_uninstall_refuses_non_dict_json_and_leaves_file_untouched():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "settings.json"
        non_dict = "[]"
        path.write_text(non_dict)
        result = hooks_install.uninstall(path=path)
        assert "refus" in result.lower()
        assert path.read_text() == non_dict


def test_uninstall_noop_does_not_rewrite_or_backup():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "settings.json"
        original = json.dumps({"hooks": {}})
        path.write_text(original)
        result = hooks_install.uninstall(path=path)
        assert "nothing" in result.lower()
        assert path.read_text() == original
        assert not list(Path(d).glob("settings.json.se7e-bak-*"))


def test_is_installed_returns_false_on_corrupt_json():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "settings.json"
        path.write_text("{not valid json")
        assert hooks_install.is_installed(path=path) is False


if __name__ == "__main__":
    test_install_writes_only_the_narrow_event_set()
    test_install_backs_up_existing_file()
    test_install_preserves_other_tools_hooks()
    test_uninstall_removes_only_our_entries()
    test_successive_installs_create_distinct_backups()
    test_is_installed_requires_actual_hook_entry_not_string_match()
    test_install_refuses_corrupt_json_and_leaves_file_untouched()
    test_uninstall_refuses_corrupt_json_and_leaves_file_untouched()
    test_install_refuses_non_dict_json_and_leaves_file_untouched()
    test_uninstall_refuses_non_dict_json_and_leaves_file_untouched()
    test_uninstall_noop_does_not_rewrite_or_backup()
    test_is_installed_returns_false_on_corrupt_json()
    print("OK")
