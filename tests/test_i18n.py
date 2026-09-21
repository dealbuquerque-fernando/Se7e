from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from se7e import i18n


def test_t_returns_the_requested_language():
    assert i18n.t("tray_menu_quit", "pt") == "Sair"
    assert i18n.t("tray_menu_quit", "en") == "Quit"


def test_t_formats_kwargs():
    assert i18n.t("popup_updated_ago", "pt", s=12) == "atualizado ha 12s"
    assert i18n.t("popup_updated_ago", "en", s=12) == "updated 12s ago"


def test_t_falls_back_to_default_language_for_unknown_language():
    assert i18n.t("tray_menu_quit", "de") == i18n.t("tray_menu_quit", i18n.DEFAULT_LANGUAGE)


def test_t_falls_back_to_the_key_itself_for_an_unknown_key():
    assert i18n.t("no_such_key", "pt") == "no_such_key"


def test_every_language_has_the_same_keys():
    reference = set(i18n.STRINGS[i18n.DEFAULT_LANGUAGE])
    for lang, table in i18n.STRINGS.items():
        assert set(table) == reference, f"{lang} is missing or has extra keys"


if __name__ == "__main__":
    test_t_returns_the_requested_language()
    test_t_formats_kwargs()
    test_t_falls_back_to_default_language_for_unknown_language()
    test_t_falls_back_to_the_key_itself_for_an_unknown_key()
    test_every_language_has_the_same_keys()
    print("OK")
