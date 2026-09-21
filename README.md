# Se7e

Windows tray app that shows your Claude Code and Codex usage at a glance —
a system tray icon, a compact floating pill, and a fuller panel with 5-hour
and weekly usage bars for both providers.

## Features

- Tray icon that changes color based on Claude/Codex activity status
- Floating always-on-top pill with live status dots
- Full panel with usage percentages, language (PT/EN), and dark/light theme
- Optional launch on Windows startup
- Hooks into Claude Code's own session lifecycle to track status in real time

## Requirements

- Windows
- Python 3.11+
- Dependencies in `requirements.txt` (PySide6, pystray, Pillow)

## Install & run

```
pip install -r requirements.txt
python -m se7e.app
```

## Settings

Right-click (or open via the tray panel) to access Settings: language, theme,
floating pill orientation, and autostart with Windows.

## License

MIT — see [LICENSE](LICENSE).
