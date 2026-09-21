from . import i18n

STATUS_COLORS = {
    "esperando voce": "#eab308",
    "parado": "#4b5160",
}

CODEX_WORKING_COLOR = "#38bdf8"
CLAUDE_WORKING_COLOR = "#22c55e"
DISCONNECTED_COLOR = "#ef4444"
TRAY_ACTIVE_COLOR = "#ffffff"  # neon white: either provider active, no matter which


def color_for_status(status: str, working_color: str = CLAUDE_WORKING_COLOR, connected: bool = True) -> str:
    if not connected:
        return DISCONNECTED_COLOR
    if status == "trabalhando":
        return working_color
    return STATUS_COLORS.get(status, STATUS_COLORS["parado"])


def tray_icon_color(claude_status: str, codex_status: str) -> str:
    """The tray badge doesn't distinguish which provider or what kind of
    activity — any non-idle status on either one shows neon white; both
    idle shows the same neutral gray as an idle dot."""
    if claude_status != "parado" or codex_status != "parado":
        return TRAY_ACTIVE_COLOR
    return STATUS_COLORS["parado"]


def should_blink(status: str, connected: bool = True) -> bool:
    return connected and status == "trabalhando"


def format_pct(value, connected: bool = True, lang: str = i18n.DEFAULT_LANGUAGE) -> str:
    if not connected:
        return i18n.t("status_not_connected", lang)
    if value is None:
        return i18n.t("status_placeholder", lang)
    return f"{round(value)}%"
