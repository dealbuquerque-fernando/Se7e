import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from se7e import settings_store


def test_load_missing_file_returns_defaults():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "settings.json"
        assert settings_store.load(path) == settings_store.DEFAULTS


def test_load_corrupt_file_returns_defaults():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "settings.json"
        path.write_text("{not valid json")
        assert settings_store.load(path) == settings_store.DEFAULTS


def test_load_non_dict_json_returns_defaults():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "settings.json"
        path.write_text("[1, 2, 3]")
        assert settings_store.load(path) == settings_store.DEFAULTS


def test_save_then_load_roundtrips():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "settings.json"
        settings_store.save({"language": "en"}, path)
        result = settings_store.load(path)
        assert result["language"] == "en"
        # Untouched defaults survive a partial update.
        assert result["theme"] == settings_store.DEFAULTS["theme"]


def test_save_merges_with_existing_values():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "settings.json"
        settings_store.save({"language": "en"}, path)
        settings_store.save({"theme": "light"}, path)
        result = settings_store.load(path)
        assert result["language"] == "en"
        assert result["theme"] == "light"


if __name__ == "__main__":
    test_load_missing_file_returns_defaults()
    test_load_corrupt_file_returns_defaults()
    test_load_non_dict_json_returns_defaults()
    test_save_then_load_roundtrips()
    test_save_merges_with_existing_values()
    print("OK")
