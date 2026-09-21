import json
import tempfile
import time
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from se7e import state_store


def test_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "state.json"
        state_store.write_claude_status("trabalhando", path=path)
        result = state_store.read_claude_status(path=path)
        assert result["status"] == "trabalhando"
        assert result["since"] > 0


def test_missing_file_returns_default():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "does-not-exist.json"
        result = state_store.read_claude_status(path=path)
        assert result["status"] == "parado"


def test_corrupt_file_returns_default():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "state.json"
        path.write_text("{not valid json")
        result = state_store.read_claude_status(path=path)
        assert result["status"] == "parado"


def test_stale_working_status_falls_back_to_idle():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "state.json"
        stuck_since = time.time() - state_store.STALE_SECONDS - 1
        path.write_text(json.dumps({"claude": {"status": "trabalhando", "since": stuck_since}}))
        result = state_store.read_claude_status(path=path)
        assert result["status"] == "parado"


def test_fresh_working_status_stays_working():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "state.json"
        state_store.write_claude_status("trabalhando", path=path)
        result = state_store.read_claude_status(path=path)
        assert result["status"] == "trabalhando"


if __name__ == "__main__":
    test_roundtrip()
    test_missing_file_returns_default()
    test_corrupt_file_returns_default()
    test_stale_working_status_falls_back_to_idle()
    test_fresh_working_status_stays_working()
    print("OK")
