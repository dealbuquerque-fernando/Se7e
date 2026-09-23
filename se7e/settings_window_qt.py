"""PySide6 native settings dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from . import autostart, i18n, settings_store, ui_colors
from .config import resource_dir
from .floating_ui_qt import _font, _hide_from_taskbar, _reapply_icon_after_show, _window_icon


WINDOW_WIDTH = 460
WINDOW_HEIGHT = 330


THEMES = {
    "dark": {
        "background": "#14161c",
        "border": "#262a35",
        "primary": "#e7e9ee",
        "secondary": "#a8adba",
        "muted": "#6b7280",
        "button_background": "#1c1f27",
        # Same gray as the light theme's hover ("secondary" there) — the
        # real bug hiding the hover (a private Qt combo delegate painting
        # against the wrong stylesheet, fixed via QStyledItemDelegate
        # above) was mistaken early on for a contrast problem, hence the
        # earlier blue-accent color; a plain gray reads fine now that the
        # delegate actually paints it.
        "hover_background": "#4b5160",
        "hover_text": "#f5f6f8",
    },
    "light": {
        "background": "#f5f6f8",
        "border": "#dcdfe4",
        "primary": "#1a1d24",
        "secondary": "#4b5160",
        "muted": "#8b93a1",
        "button_background": "#e9ebef",
        "hover_background": "#4b5160",  # = secondary, already confirmed visible
        "hover_text": "#f5f6f8",  # = background
    },
}


_ASSETS_DIR = resource_dir() / "assets"

# QCheckBox::indicator:checked { image: url(...) } — styling the indicator
# at all (border/background) makes Qt stop drawing its own native checkmark
# glyph, so one has to be supplied. A data: URI here silently failed to
# render (QSS's "image" property on a ::indicator sub-control doesn't
# reliably support inline data URIs), so these are real files instead —
# one per theme, since each needs a different stroke color to stay visible
# against that theme's checked-background color (THEMES[...]["secondary"]).
_CHECKMARK_PATHS = {
    "dark": (_ASSETS_DIR / "checkbox_check_dark.svg").as_posix(),
    "light": (_ASSETS_DIR / "checkbox_check_light.svg").as_posix(),
}


class _SettingsDialog(QDialog):
    def __init__(self, owner: "SettingsWindow") -> None:
        super().__init__()
        self.owner = owner
        self._loading = False

        self.setWindowTitle(owner.title)
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setMinimumSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setAttribute(
            Qt.WidgetAttribute.WA_DeleteOnClose,
            True,
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(0)

        self.title_label = QLabel()
        self.title_label.setFont(_font(13, bold=True))
        root.addWidget(self.title_label)
        root.addSpacing(6)

        self.autostart_checkbox = QCheckBox()
        self.autostart_checkbox.setFont(_font(12))
        self.autostart_row = QWidget()
        autostart_layout = QHBoxLayout(self.autostart_row)
        autostart_layout.setContentsMargins(0, 6, 0, 6)
        autostart_layout.setSpacing(8)
        autostart_layout.addWidget(self.autostart_checkbox)
        autostart_layout.addStretch()
        root.addWidget(self.autostart_row)

        self.language_label = QLabel()
        self.language_label.setFont(_font(12))
        self.language_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )
        self.language_combo = QComboBox()
        self.language_combo.setFont(_font(12))

        self.language_row = self._combo_row(
            self.language_label,
            self.language_combo,
        )
        root.addWidget(self.language_row)

        self.language_note = QLabel()
        self.language_note.setFont(_font(10))
        self.language_note.setWordWrap(True)
        root.addWidget(self.language_note)
        root.addSpacing(4)

        self.theme_label = QLabel()
        self.theme_label.setFont(_font(12))
        self.theme_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )
        self.theme_combo = QComboBox()
        self.theme_combo.setFont(_font(12))

        self.theme_row = self._combo_row(
            self.theme_label,
            self.theme_combo,
        )
        root.addWidget(self.theme_row)

        self.orientation_label = QLabel()
        self.orientation_label.setFont(_font(12))
        self.orientation_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )
        self.orientation_combo = QComboBox()
        self.orientation_combo.setFont(_font(12))

        self.orientation_row = self._combo_row(
            self.orientation_label,
            self.orientation_combo,
        )
        root.addWidget(self.orientation_row)

        # Qt's default combo popup paints rows through its own private
        # QComboMenuDelegate, which styles against the QComboBox's own QSS
        # (which has its own "background") instead of the popup view's —
        # that's what was swallowing the view's selection-background-color.
        # A public QStyledItemDelegate paints through the view instead.
        for combo in (
            self.language_combo,
            self.theme_combo,
            self.orientation_combo,
        ):
            combo.setItemDelegate(QStyledItemDelegate(combo.view()))

        self.orientation_note = QLabel()
        self.orientation_note.setFont(_font(10))
        self.orientation_note.setWordWrap(True)
        root.addWidget(self.orientation_note)

        root.addStretch()
        root.addSpacing(20)

        self.apply_button = QPushButton()
        self.apply_button.setFont(_font(12, bold=True))
        self.apply_button.setFixedHeight(30)
        self.apply_button.setMinimumWidth(82)

        self.uninstall_button = QPushButton()
        self.uninstall_button.setFont(_font(12))
        self.uninstall_button.setFixedHeight(30)
        self.uninstall_button.setMinimumWidth(82)

        apply_row = QHBoxLayout()
        apply_row.setContentsMargins(0, 0, 0, 0)
        apply_row.addWidget(
            self.apply_button,
            0,
            Qt.AlignmentFlag.AlignLeft,
        )
        apply_row.addStretch()
        apply_row.addWidget(
            self.uninstall_button,
            0,
            Qt.AlignmentFlag.AlignRight,
        )
        root.addLayout(apply_row)

        self.autostart_checkbox.clicked.connect(
            self.owner._toggle_autostart
        )
        self.language_combo.currentIndexChanged.connect(
            self.owner._language_changed
        )
        self.theme_combo.currentIndexChanged.connect(
            self.owner._theme_changed
        )
        self.orientation_combo.currentIndexChanged.connect(
            self.owner._orientation_changed
        )
        self.apply_button.clicked.connect(
            self.owner._on_apply_restart
        )
        self.uninstall_button.clicked.connect(
            self._confirm_uninstall
        )

        self.reload_values()
        self.apply_translations()
        self.apply_theme()
        # Set last, right before this dialog is shown by the caller — see
        # the matching comment in tray_ui_qt.py's _TrayPanel.__init__.
        self.setWindowIcon(_window_icon())

    def _combo_row(
        self,
        label: QLabel,
        combo: QComboBox,
    ) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(8)
        layout.addWidget(label)
        layout.addWidget(combo)
        layout.addStretch()
        return row

    @staticmethod
    def _select_data(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def reload_values(self) -> None:
        settings = settings_store.load()
        self._loading = True

        try:
            self.autostart_checkbox.setChecked(
                autostart.is_enabled()
            )

            self.language_combo.clear()
            for language in i18n.SUPPORTED_LANGUAGES:
                label = (
                    "Português"
                    if language == "pt"
                    else "English"
                )
                self.language_combo.addItem(label, language)

            self.theme_combo.clear()
            for theme in settings_store.SUPPORTED_THEMES:
                self.theme_combo.addItem(theme, theme)

            self.orientation_combo.clear()
            for orientation in (
                settings_store.SUPPORTED_ORIENTATIONS
            ):
                self.orientation_combo.addItem(
                    orientation,
                    orientation,
                )

            self._select_data(
                self.language_combo,
                self.owner.lang,
            )
            self._select_data(
                self.theme_combo,
                settings.get(
                    "theme",
                    settings_store.DEFAULTS["theme"],
                ),
            )
            self._select_data(
                self.orientation_combo,
                settings.get(
                    "floating_orientation",
                    settings_store.DEFAULTS[
                        "floating_orientation"
                    ],
                ),
            )
        finally:
            self._loading = False

    def apply_translations(self) -> None:
        strings = i18n.STRINGS.get(
            self.owner.lang,
            i18n.STRINGS[i18n.DEFAULT_LANGUAGE],
        )

        self.title_label.setText(strings["settings_title"])
        self.autostart_checkbox.setText(
            strings["settings_autostart"]
        )
        self.language_label.setText(
            strings["settings_language"]
        )
        self.language_note.setText(
            strings["settings_language_note"]
        )
        self.theme_label.setText(strings["settings_theme"])
        self.orientation_label.setText(
            strings["settings_orientation"]
        )
        self.orientation_note.setText(
            strings["settings_orientation_note"]
        )
        self.apply_button.setText(strings["settings_apply"])
        self.uninstall_button.setText(strings["settings_uninstall"])

        current_theme = self.theme_combo.currentData()
        self.theme_combo.blockSignals(True)
        self.theme_combo.clear()
        self.theme_combo.addItem(
            strings["settings_theme_dark"],
            "dark",
        )
        self.theme_combo.addItem(
            strings["settings_theme_light"],
            "light",
        )
        self._select_data(
            self.theme_combo,
            current_theme or settings_store.DEFAULTS["theme"],
        )
        self.theme_combo.blockSignals(False)

        current_orientation = (
            self.orientation_combo.currentData()
        )
        self.orientation_combo.blockSignals(True)
        self.orientation_combo.clear()
        self.orientation_combo.addItem(
            strings["settings_orientation_horizontal"],
            "horizontal",
        )
        self.orientation_combo.addItem(
            strings["settings_orientation_vertical"],
            "vertical",
        )
        self._select_data(
            self.orientation_combo,
            current_orientation
            or settings_store.DEFAULTS[
                "floating_orientation"
            ],
        )
        self.orientation_combo.blockSignals(False)

    def apply_theme(self) -> None:
        theme = self.theme_combo.currentData()
        if theme not in settings_store.SUPPORTED_THEMES:
            theme = settings_store.DEFAULTS["theme"]

        colors = THEMES[theme]
        self.setStyleSheet(
            f"""
            QDialog {{
                background: {colors["background"]};
                color: {colors["primary"]};
            }}
            QLabel, QCheckBox, QFrame {{
                background: transparent;
                color: {colors["primary"]};
            }}
            QCheckBox::indicator {{
                width: 14px;
                height: 14px;
                border: 1px solid {colors["border"]};
                border-radius: 3px;
                background: {colors["button_background"]};
            }}
            QCheckBox::indicator:checked {{
                background: {colors["secondary"]};
                border: 1px solid {colors["secondary"]};
                image: url({_CHECKMARK_PATHS[theme]});
            }}
            QPushButton {{
                padding: 0 16px;
                border: none;
                border-radius: 6px;
                background: {colors["button_background"]};
                color: {colors["primary"]};
            }}
            QPushButton:hover,
            QPushButton:focus {{
                background: {colors["border"]};
            }}
            """
        )

        # The nested selector "QComboBox QAbstractItemView" never reaches
        # the popup when the combo lives inside a QDialog specifically
        # (confirmed via isolated repro: identical stylesheet on the same
        # combo works under a plain QWidget parent, fails under QDialog) —
        # so the popup view needs its own stylesheet set directly on
        # combo.view(), not through the descendant selector.
        combo_style = f"""
            QComboBox {{
                min-height: 22px;
                padding: 1px 6px;
                border: 1px solid {colors["border"]};
                border-radius: 4px;
                background: {colors["button_background"]};
                color: {colors["primary"]};
            }}
        """
        popup_style = f"""
            QAbstractItemView {{
                border: 1px solid {colors["border"]};
                background: {colors["button_background"]};
                color: {colors["primary"]};
                selection-background-color: {colors["hover_background"]};
                selection-color: {colors["hover_text"]};
            }}
        """
        for combo in (
            self.language_combo,
            self.theme_combo,
            self.orientation_combo,
        ):
            combo.setStyleSheet(combo_style)
            combo.view().setStyleSheet(popup_style)

        self.title_label.setStyleSheet(
            f"color: {colors['secondary']};"
        )
        self.language_note.setStyleSheet(
            f"color: {colors['muted']};"
        )
        self.orientation_note.setStyleSheet(
            f"color: {colors['muted']};"
        )
        # Same red as a disconnected status dot elsewhere in the app —
        # the one existing "something serious" accent color, reused here
        # to set this apart from the plain Apply button.
        self.uninstall_button.setStyleSheet(
            f"QPushButton {{ color: {ui_colors.DISCONNECTED_COLOR}; }}"
        )

    def _confirm_uninstall(self) -> None:
        strings = i18n.STRINGS.get(
            self.owner.lang,
            i18n.STRINGS[i18n.DEFAULT_LANGUAGE],
        )
        answer = QMessageBox.question(
            self,
            strings["settings_uninstall_confirm_title"],
            strings["settings_uninstall_confirm_body"],
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.owner._on_uninstall()


class SettingsWindow:
    def __init__(
        self,
        title: str = "Se7e",
        lang: str = i18n.DEFAULT_LANGUAGE,
        on_apply_restart=None,
        on_uninstall=None,
    ) -> None:
        self.title = title
        self.lang = (
            lang
            if lang in i18n.SUPPORTED_LANGUAGES
            else i18n.DEFAULT_LANGUAGE
        )
        self.window: _SettingsDialog | None = None
        self._on_apply_restart = (
            on_apply_restart or (lambda: None)
        )
        self._on_uninstall = (
            on_uninstall or (lambda: None)
        )

    def toggle(self) -> None:
        if self.window is None:
            self.window = _SettingsDialog(self)
            self.window.finished.connect(self._on_closed)
            _hide_from_taskbar(self.window)
            self.window.show()
            _reapply_icon_after_show(self.window)
            self.window.raise_()
            self.window.activateWindow()
        else:
            window = self.window
            self.window = None
            window.close()

    def _on_closed(self, _result=None) -> None:
        self.window = None

    def _toggle_autostart(self) -> None:
        enabled = autostart.toggle()
        if self.window is not None:
            self.window.autostart_checkbox.blockSignals(True)
            self.window.autostart_checkbox.setChecked(enabled)
            self.window.autostart_checkbox.blockSignals(False)

    def _language_changed(self, _index: int) -> None:
        if self.window is None or self.window._loading:
            return

        lang = self.window.language_combo.currentData()
        if lang not in i18n.SUPPORTED_LANGUAGES:
            lang = i18n.DEFAULT_LANGUAGE

        settings_store.save({"language": lang})
        self.lang = lang
        self.window.apply_translations()

    def _theme_changed(self, _index: int) -> None:
        if self.window is None or self.window._loading:
            return

        theme = self.window.theme_combo.currentData()
        if theme not in settings_store.SUPPORTED_THEMES:
            theme = settings_store.DEFAULTS["theme"]

        settings_store.save({"theme": theme})
        self.window.apply_theme()

    def _orientation_changed(self, _index: int) -> None:
        if self.window is None or self.window._loading:
            return

        orientation = (
            self.window.orientation_combo.currentData()
        )
        if (
            orientation
            not in settings_store.SUPPORTED_ORIENTATIONS
        ):
            orientation = settings_store.DEFAULTS[
                "floating_orientation"
            ]

        settings_store.save(
            {"floating_orientation": orientation}
        )

    def destroy(self) -> None:
        if self.window is not None:
            window = self.window
            self.window = None
            window.close()
