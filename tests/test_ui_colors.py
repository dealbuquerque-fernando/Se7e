from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from se7e import ui_colors


def test_color_for_status_claude_default():
    assert ui_colors.color_for_status("trabalhando") == "#22c55e"
    # idle_prompt (just finished, waiting for your next message) shares
    # the tray badge's own neutral white — not urgent.
    assert ui_colors.color_for_status("esperando voce") == "#ffffff"
    # A real decision needed from you (permission_prompt/agent_needs_input/
    # elicitation_*) keeps the old amber, now the more urgent of the two
    # waiting colors.
    assert ui_colors.color_for_status("esperando decisao") == "#eab308"
    assert ui_colors.color_for_status("parado") == "#4b5160"


def test_color_for_status_custom_working_color():
    assert ui_colors.color_for_status("trabalhando", working_color=ui_colors.CODEX_WORKING_COLOR) == "#38bdf8"
    assert ui_colors.color_for_status("parado", working_color=ui_colors.CODEX_WORKING_COLOR) == "#4b5160"


def test_should_blink_only_when_working_or_needs_a_decision():
    assert ui_colors.should_blink("trabalhando") is True
    assert ui_colors.should_blink("esperando decisao") is True
    assert ui_colors.should_blink("esperando voce") is False
    assert ui_colors.should_blink("parado") is False


def test_disconnected_overrides_status_color_and_blink():
    assert ui_colors.color_for_status("trabalhando", connected=False) == ui_colors.DISCONNECTED_COLOR
    assert ui_colors.color_for_status("parado", connected=False) == ui_colors.DISCONNECTED_COLOR
    assert ui_colors.should_blink("trabalhando", connected=False) is False


def test_tray_icon_color_is_neutral_and_provider_agnostic():
    # Either one active (busy or waiting) turns it white, regardless of which.
    assert ui_colors.tray_icon_color("trabalhando", "parado") == ui_colors.TRAY_ACTIVE_COLOR
    assert ui_colors.tray_icon_color("parado", "trabalhando") == ui_colors.TRAY_ACTIVE_COLOR
    assert ui_colors.tray_icon_color("esperando voce", "parado") == ui_colors.TRAY_ACTIVE_COLOR
    assert ui_colors.tray_icon_color("trabalhando", "trabalhando") == ui_colors.TRAY_ACTIVE_COLOR
    # Only both idle shows the neutral idle gray.
    assert ui_colors.tray_icon_color("parado", "parado") == "#4b5160"


def test_tray_icon_should_blink_only_while_working_or_needs_a_decision():
    assert ui_colors.tray_icon_should_blink("trabalhando", "parado") is True
    assert ui_colors.tray_icon_should_blink("parado", "esperando decisao") is True
    # Idle alone ("esperando voce") already turns the badge white via
    # tray_icon_color(), but shouldn't make it blink — only a genuinely
    # active/urgent status should.
    assert ui_colors.tray_icon_should_blink("esperando voce", "parado") is False
    assert ui_colors.tray_icon_should_blink("parado", "parado") is False


def test_format_pct():
    assert ui_colors.format_pct(42) == "42%"
    assert ui_colors.format_pct(42.6) == "43%"
    assert ui_colors.format_pct(None) == "--"


def test_format_pct_respects_language():
    assert ui_colors.format_pct(None, connected=False, lang="pt") == "nao conectado"
    assert ui_colors.format_pct(None, connected=False, lang="en") == "not connected"
    # The percentage itself has no words to translate, only the placeholder/label paths do.
    assert ui_colors.format_pct(42, lang="en") == "42%"


if __name__ == "__main__":
    test_color_for_status_claude_default()
    test_color_for_status_custom_working_color()
    test_should_blink_only_when_working_or_needs_a_decision()
    test_disconnected_overrides_status_color_and_blink()
    test_tray_icon_color_is_neutral_and_provider_agnostic()
    test_tray_icon_should_blink_only_while_working_or_needs_a_decision()
    test_format_pct()
    test_format_pct_respects_language()
    print("OK")
