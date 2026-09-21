"""Every user-facing string, keyed once, in every supported language.

Python-generated strings (tray menu, "updated Ns ago") are looked up here
directly. The HTML pages get the whole current-language dict pushed to them
via evaluate_js and apply it to their own elements by id.
"""

STRINGS = {
    "pt": {
        "tray_menu_main_panel": "Painel principal",
        "tray_menu_compact_panel": "Painel compacto",
        "tray_menu_settings": "Configurações",
        "tray_menu_quit": "Sair",
        "popup_title": "Se7e",
        "popup_updated_ago": "atualizado ha {s}s",
        "popup_updated_stale": "desatualizado",
        "popup_label_5h": "5h",
        "popup_label_week": "sem",
        "popup_btn_floating": "Painel flutuante",
        "popup_btn_transparent": "Transparente",
        "popup_btn_hide": "Esconder",
        "popup_btn_quit": "Sair",
        "provider_claude_full": "Claude Code",
        "provider_claude_short": "Claude",
        "provider_codex": "Codex",
        "status_not_connected": "nao conectado",
        "status_placeholder": "--",
        "settings_title": "Configurações",
        "settings_autostart": "Inicializar com o sistema",
        "settings_apply": "Aplicar",
        "settings_language": "Idioma",
        "settings_language_note": "O painel principal e o flutuante usam o novo idioma na proxima vez que abrirem.",
        "settings_theme": "Tema",
        "settings_theme_dark": "Escuro",
        "settings_theme_light": "Claro",
        "settings_orientation": "Girar painel flutuante",
        "settings_orientation_horizontal": "Horizontal",
        "settings_orientation_vertical": "Vertical",
        "settings_orientation_note": "O painel flutuante usa a orientacao nova na proxima vez que abrir.",
        "settings_uninstall": "Desinstalar",
        "settings_uninstall_confirm_title": "Desinstalar Se7e",
        "settings_uninstall_confirm_body": "Isso remove os hooks do Claude Code e desativa a inicializacao automatica, e fecha o Se7e. Depois, arraste o app para a Lixeira para concluir. Continuar?",
    },
    "en": {
        "tray_menu_main_panel": "Main panel",
        "tray_menu_compact_panel": "Compact panel",
        "tray_menu_settings": "Settings",
        "tray_menu_quit": "Quit",
        "popup_title": "Se7e",
        "popup_updated_ago": "updated {s}s ago",
        "popup_updated_stale": "stale",
        "popup_label_5h": "5h",
        "popup_label_week": "wk",
        "popup_btn_floating": "Floating panel",
        "popup_btn_transparent": "Transparent",
        "popup_btn_hide": "Hide",
        "popup_btn_quit": "Quit",
        "provider_claude_full": "Claude Code",
        "provider_claude_short": "Claude",
        "provider_codex": "Codex",
        "status_not_connected": "not connected",
        "status_placeholder": "--",
        "settings_title": "Settings",
        "settings_autostart": "Start with the system",
        "settings_apply": "Apply",
        "settings_language": "Language",
        "settings_language_note": "The main panel and floating pill pick up the new language the next time they open.",
        "settings_theme": "Theme",
        "settings_theme_dark": "Dark",
        "settings_theme_light": "Light",
        "settings_orientation": "Rotate floating panel",
        "settings_orientation_horizontal": "Horizontal",
        "settings_orientation_vertical": "Vertical",
        "settings_orientation_note": "The floating pill uses the new orientation the next time it opens.",
        "settings_uninstall": "Uninstall",
        "settings_uninstall_confirm_title": "Uninstall Se7e",
        "settings_uninstall_confirm_body": "This removes Se7e's Claude Code hooks, disables autostart, and quits Se7e. Afterwards, drag the app to the Trash to finish. Continue?",
    },
}

DEFAULT_LANGUAGE = "pt"
SUPPORTED_LANGUAGES = tuple(STRINGS.keys())


def t(key: str, lang: str = DEFAULT_LANGUAGE, **kwargs) -> str:
    table = STRINGS.get(lang, STRINGS[DEFAULT_LANGUAGE])
    template = table.get(key) or STRINGS[DEFAULT_LANGUAGE].get(key, key)
    return template.format(**kwargs) if kwargs else template
