from pathlib import Path
import os
import sys
import subprocess
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from se7e import hook
from se7e import state_store


def test_known_events_map_to_expected_status():
    assert hook.status_for_event("SessionStart") == "trabalhando"
    assert hook.status_for_event("UserPromptSubmit") == "trabalhando"
    assert hook.status_for_event("Notification") == "esperando voce"
    assert hook.status_for_event("Stop") == "parado"
    assert hook.status_for_event("SessionEnd") == "parado"


def test_tool_use_events_are_ignored():
    assert hook.status_for_event("PreToolUse") is None
    assert hook.status_for_event("PostToolUse") is None
    assert hook.status_for_event("") is None
    assert hook.status_for_event("something-unknown") is None


def test_hook_invoked_as_bare_script_exits_zero_and_writes_status():
    """Test that hook.py can be invoked as a bare script and writes state correctly."""
    # hook.py always writes to config.STATE_FILE (it takes no path argument —
    # that's the real contract Claude Code invokes it under), so isolating
    # this subprocess means giving it its own throwaway home directory
    # instead, via the same env var config.APP_DIR reads (HOME on macOS/
    # Linux, LOCALAPPDATA on Windows) — not the real one, which a previous
    # version of this test wrote "trabalhando" into directly and never
    # cleaned up, leaving the real app stuck showing a live status.
    with tempfile.TemporaryDirectory() as home_dir:
        home = Path(home_dir)
        env = dict(os.environ, HOME=str(home), LOCALAPPDATA=str(home))

        repo_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, str(repo_root / "se7e" / "hook.py"), "SessionStart"],
            cwd=repo_root,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Verify exit code is 0 (never crashes)
        assert result.returncode == 0, f"Exit code {result.returncode}, stderr: {result.stderr}"

        # Mirrors config.py's own APP_DIR logic, rooted at the throwaway
        # home above instead of the real one.
        app_dir = (
            home / "Library" / "Application Support" / "se7e"
            if sys.platform == "darwin"
            else home / "se7e"
        )
        data = state_store.read_all(app_dir / "state.json")
        assert data.get("claude", {}).get("status") == "trabalhando"


if __name__ == "__main__":
    test_known_events_map_to_expected_status()
    test_tool_use_events_are_ignored()
    test_hook_invoked_as_bare_script_exits_zero_and_writes_status()
    print("OK")
