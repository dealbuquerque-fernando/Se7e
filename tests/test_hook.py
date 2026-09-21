from pathlib import Path
import sys
import subprocess
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from se7e import hook
from se7e.config import STATE_FILE
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
    # Clean up state file for this test
    if STATE_FILE.exists():
        STATE_FILE.unlink()

    # Invoke hook as a bare script (simulating how Claude Code will call it)
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(repo_root / "se7e" / "hook.py"), "SessionStart"],
        cwd=repo_root,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Verify exit code is 0 (never crashes)
    assert result.returncode == 0, f"Exit code {result.returncode}, stderr: {result.stderr}"

    # Verify state file was written with correct status
    data = state_store.read_all(STATE_FILE)
    assert data.get("claude", {}).get("status") == "trabalhando"


if __name__ == "__main__":
    test_known_events_map_to_expected_status()
    test_tool_use_events_are_ignored()
    test_hook_invoked_as_bare_script_exits_zero_and_writes_status()
    print("OK")
