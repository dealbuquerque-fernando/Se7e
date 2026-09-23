"""PySide6 floating status pill."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QFontMetrics,
    QIcon,
    QMouseEvent,
    QPainter,
    QPen,
    QRadialGradient,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QWidget

from . import i18n, ui_colors
from .config import FLOATING_POSITION_FILE, resource_dir
from .geometry_types import WindowRect

if sys.platform == "darwin":
    from .platform_mac import (
        _cursor_position,
        _force_topmost,
        _hide_from_taskbar,
        _set_joins_all_spaces,
        _set_native_geometry,
        monitor_rect_for_point,
        read_window_rect,
        work_area_for_point,
    )
elif sys.platform == "win32":
    from .platform_win import (
        _cursor_position,
        _force_topmost,
        _hide_from_taskbar,
        _set_joins_all_spaces,
        _set_native_geometry,
        monitor_rect_for_point,
        read_window_rect,
        work_area_for_point,
    )
else:
    raise NotImplementedError(f"se7e.floating_ui_qt has no native backend for {sys.platform!r}")

_ICON_PATH = resource_dir() / "assets" / "se7e_icon_v2.ico"


def _window_icon() -> QIcon:
    """QApplication.setWindowIcon() alone left this app's taskbar entry
    showing Windows' generic blank-window icon instead of inheriting it —
    setting it directly on each top-level window is more reliable."""
    return QIcon(str(_ICON_PATH))


def _reapply_icon_after_show(window: QWidget) -> None:
    """The very FIRST time any window in this process becomes visible,
    Windows' shell can register its taskbar button before the icon Qt set
    has actually reached it — the icon set at construction time doesn't
    always "take" on that first show, even though it's already correct on
    every show after that (confirmed live: hiding and reopening the same
    window fixes it). Re-setting the icon on the next event-loop tick,
    after the window is already visible, reliably forces the refresh that
    a manual hide+reopen was doing."""
    QTimer.singleShot(0, lambda: window.setWindowIcon(_window_icon()))


WINDOW_WIDTH = 150
# The pill's cross-dimension (height when docked horizontally, width when
# vertical) used to be measured from the OS's own taskbar/Dock thickness,
# so the pill would sit flush against it — but that made the exact same
# design look very different across platforms, and even across Dock
# settings on the same Mac (a Dock set to auto-hide reserves no space at
# all, silently falling back to measuring the menu bar instead: 25 logical
# px, vs. Windows' usual ~40+ for its taskbar). Now a fixed constant, so
# both platforms render identically regardless of the OS's own taskbar/Dock
# configuration.
PILL_THICKNESS = 25
RIGHT_MARGIN = 20
BOTTOM_MARGIN = 60
CORNER_RADIUS = 14

@dataclass(frozen=True)
class ScreenGeometry:
    x: int
    y: int
    width: int
    height: int
    scale: float | None
    physical_width: int | None
    physical_height: int | None


def _dpi_scale(screen) -> tuple[float, float]:
    physical_width = getattr(screen, "physical_width", None)
    physical_height = getattr(screen, "physical_height", None)
    scale = getattr(screen, "scale", None) or 1.0

    width_scale = (
        physical_width / screen.width
        if physical_width and screen.width
        else scale
    )
    height_scale = (
        physical_height / screen.height
        if physical_height and screen.height
        else scale
    )
    return width_scale, height_scale


def _native_window_size(
    logical_width: int,
    logical_height: int,
    screen,
) -> tuple[int, int]:
    width_scale, height_scale = _dpi_scale(screen)
    return (
        round(logical_width * width_scale),
        round(logical_height * height_scale),
    )


def _physical_screen_bounds(
    screen,
) -> tuple[float, float, float, float]:
    width_scale, height_scale = _dpi_scale(screen)
    return (
        screen.x * width_scale,
        screen.y * height_scale,
        screen.width * width_scale,
        screen.height * height_scale,
    )


def _screen_geometry(screen) -> ScreenGeometry:
    geometry = screen.geometry()
    scale = float(screen.devicePixelRatio())
    return ScreenGeometry(
        x=geometry.x(),
        y=geometry.y(),
        width=geometry.width(),
        height=geometry.height(),
        scale=scale,
        physical_width=round(geometry.width() * scale),
        physical_height=round(geometry.height() * scale),
    )


def _floating_dimensions(
    screen: ScreenGeometry,
    orientation: str,
) -> tuple[int, int, int, int]:
    """Return logical width/height and physical width/height."""
    width_scale, height_scale = _dpi_scale(screen)
    physical_thickness = round(PILL_THICKNESS * height_scale)

    if orientation == "vertical":
        physical_length = round(WINDOW_WIDTH * height_scale)
        return (
            PILL_THICKNESS,
            WINDOW_WIDTH,
            physical_thickness,
            physical_length,
        )

    physical_length = round(WINDOW_WIDTH * width_scale)
    return (
        WINDOW_WIDTH,
        PILL_THICKNESS,
        physical_length,
        physical_thickness,
    )


def save_position(
    rect: WindowRect,
    path: Path = FLOATING_POSITION_FILE,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"x": rect.left, "y": rect.top}),
        encoding="utf-8",
    )
    temporary.replace(path)


def load_position(
    path: Path = FLOATING_POSITION_FILE,
) -> tuple[int, int] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return int(data["x"]), int(data["y"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


_FONT_FAMILY: str | None = None


def _font(pixel_size: int, bold: bool = False) -> QFont:
    global _FONT_FAMILY

    if _FONT_FAMILY is None:
        assets = resource_dir() / "assets"
        regular_id = QFontDatabase.addApplicationFont(
            str(assets / "Inconsolata-Regular.ttf")
        )
        QFontDatabase.addApplicationFont(
            str(assets / "Inconsolata-Bold.ttf")
        )
        families = QFontDatabase.applicationFontFamilies(regular_id)
        _FONT_FAMILY = families[0] if families else "Inconsolata"

    font = QFont(_FONT_FAMILY)
    font.setPixelSize(pixel_size)
    font.setWeight(
        QFont.Weight.Bold if bold else QFont.Weight.Normal
    )
    return font


CLAUDE_SVG_PATH = (
    "M4.709 15.955l4.72-2.647.08-.23-.08-.128H9.2l-.79-.048-2.698-.073"
    "-2.339-.097-2.266-.122-.571-.121L0 11.784l.055-.352.48-.321.686.06"
    " 1.52.103 2.278.158 1.652.097 2.449.255h.389l.055-.157-.134-.098"
    "-.103-.097-2.358-1.596-2.552-1.688-1.336-.972-.724-.491-.364-.462"
    "-.158-1.008.656-.722.881.06.225.061.893.686 1.908 1.476 2.491"
    " 1.833.365.304.145-.103.019-.073-.164-.274-1.355-2.446-1.446"
    "-2.49-.644-1.032-.17-.619a2.97 2.97 0 01-.104-.729L6.283.134"
    " 6.696 0l.996.134.42.364.62 1.414 1.002 2.229 1.555 3.03.456"
    ".898.243.832.091.255h.158V9.01l.128-1.706.237-2.095.23-2.695"
    ".08-.76.376-.91.747-.492.584.28.48.685-.067.444-.286 1.851"
    "-.559 2.903-.364 1.942h.212l.243-.242.985-1.306 1.652-2.064"
    ".73-.82.85-.904.547-.431h1.033l.76 1.129-.34 1.166-1.064"
    " 1.347-.881 1.142-1.264 1.7-.79 1.36.073.11.188-.02 2.856"
    "-.606 1.543-.28 1.841-.315.833.388.091.395-.328.807-1.969"
    ".486-2.309.462-3.439.813-.042.03.049.061 1.549.146.662.036"
    "h1.622l3.02.225.79.522.474.638-.079.485-1.215.62-1.64-.389"
    "-3.829-.91-1.312-.329h-.182v.11l1.093 1.068 2.006 1.81 2.509"
    " 2.33.127.578-.322.455-.34-.049-2.205-1.657-.851-.747-1.926"
    "-1.62h-.128v.17l.444.649 2.345 3.521.122 1.08-.17.353-.608"
    ".213-.668-.122-1.374-1.925-1.415-2.167-1.143-1.943-.14.08"
    "-.674 7.254-.316.37-.729.28-.607-.461-.322-.747.322-1.476"
    ".389-1.924.315-1.53.286-1.9.17-.632-.012-.042-.14.018-1.434"
    " 1.967-2.18 2.945-1.726 1.845-.414.164-.717-.37.067-.662"
    ".401-.589 2.388-3.036 1.44-1.882.93-1.086-.006-.158h-.055"
    "L4.132 18.56l-1.13.146-.487-.456.061-.746.231-.243 1.908"
    "-1.312-.006.006z"
)

CODEX_SVG_PATH = (
    "M9.205 8.658v-2.26c0-.19.072-.333.238-.428l4.543-2.616c.619"
    "-.357 1.356-.523 2.117-.523 2.854 0 4.662 2.212 4.662 4.566"
    " 0 .167 0 .357-.024.547l-4.71-2.759a.797.797 0 00-.856 0"
    "l-5.97 3.473zm10.609 8.8V12.06c0-.333-.143-.57-.429-.737"
    "l-5.97-3.473 1.95-1.118a.433.433 0 01.476 0l4.543 2.617"
    "c1.309.76 2.189 2.378 2.189 3.948 0 1.808-1.07 3.473-2.76"
    " 4.163zM7.802 12.703l-1.95-1.142c-.167-.095-.239-.238-.239"
    "-.428V5.899c0-2.545 1.95-4.472 4.591-4.472 1 0 1.927.333"
    " 2.712.928L8.23 5.067c-.285.166-.428.404-.428.737v6.898z"
    "M12 15.128l-2.795-1.57v-3.33L12 8.658l2.795 1.57v3.33"
    "L12 15.128zm1.796 7.23c-1 0-1.927-.332-2.712-.927l4.686"
    "-2.712c.285-.166.428-.404.428-.737v-6.898l1.974 1.142"
    "c.167.095.238.238.238.428v5.233c0 2.545-1.974 4.472"
    "-4.614 4.472zm-5.637-5.303l-4.544-2.617c-1.308-.761"
    "-2.188-2.378-2.188-3.948A4.482 4.482 0 014.21 6.327v5.423"
    "c0 .333.143.571.428.738l5.947 3.449-1.95 1.118a.432.432"
    " 0 01-.476 0zm-.262 3.9c-2.688 0-4.662-2.021-4.662-4.519"
    " 0-.19.024-.38.047-.57l4.686 2.71c.286.167.571.167.856 0"
    "l5.97-3.448v2.26c0 .19-.07.333-.237.428l-4.543 2.616"
    "c-.619.357-1.356.523-2.117.523zm5.899 2.83a5.947 5.947"
    " 0 005.827-4.756C22.287 18.339 24 15.84 24 13.296"
    "c0-1.665-.713-3.282-1.998-4.448.119-.5.19-.999.19-1.498"
    " 0-3.401-2.759-5.947-5.946-5.947-.642 0-1.26.095-1.88.31"
    "A5.962 5.962 0 0010.205 0a5.947 5.947 0 00-5.827 4.757"
    "C1.713 5.447 0 7.945 0 10.49c0 1.666.713 3.283 1.998"
    " 4.448-.119.5-.19 1-.19 1.499 0 3.401 2.759 5.946"
    " 5.946 5.946.642 0 1.26-.095 1.88-.309a5.96 5.96"
    " 0 004.162 1.713z"
)


THEMES = {
    "dark": {
        "background": "#14161c",
        "border": "#262a35",
        "primary": "#e7e9ee",
        "muted": "#6b7280",
    },
    "light": {
        "background": "#f5f6f8",
        "border": "#dcdfe4",
        "primary": "#1a1d24",
        "muted": "#8b93a1",
    },
}


class FloatingWidget(QWidget):
    def __init__(
        self,
        title: str = "Se7e",
        lang: str = i18n.DEFAULT_LANGUAGE,
        theme: str = "dark",
        orientation: str = "horizontal",
    ) -> None:
        super().__init__()

        self.title = title
        self.lang = lang
        self.theme = theme if theme == "light" else "dark"
        self.orientation = (
            "vertical" if orientation == "vertical" else "horizontal"
        )
        self._transparent = False
        self._blink_on = True
        self._drag_offset: tuple[int, int] | None = None
        self._destroyed = False
        self._svg_cache: dict[tuple[str, str], QSvgRenderer] = {}

        self._providers = {
            "claude": {
                "percentage": i18n.t("status_placeholder", self.lang),
                "dot_color": ui_colors.color_for_status("parado"),
                "blink": False,
            },
            "codex": {
                "percentage": i18n.t("status_placeholder", self.lang),
                "dot_color": ui_colors.color_for_status(
                    "parado",
                    working_color=ui_colors.CODEX_WORKING_COLOR,
                ),
                "blink": False,
            },
        }

        self.setWindowTitle(title)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground,
            True,
        )
        self.setAttribute(
            Qt.WidgetAttribute.WA_DeleteOnClose,
            False,
        )

        app = QApplication.instance()
        screen = app.primaryScreen() if app is not None else None
        if screen is None:
            raise RuntimeError(
                "FloatingWidget requires an active QApplication"
            )

        self.screen_geometry = _screen_geometry(screen)
        (
            logical_width,
            logical_height,
            physical_width,
            physical_height,
        ) = _floating_dimensions(
            self.screen_geometry,
            self.orientation,
        )

        self._physical_size = physical_width, physical_height
        self.setFixedSize(logical_width, logical_height)

        x, y = self._initial_position(
            physical_width,
            physical_height,
        )
        _set_native_geometry(
            self,
            x,
            y,
            physical_width,
            physical_height,
        )
        # Set right before show(), not earlier in __init__: Windows' shell
        # can query (and cache, for this AppUserModelID group) the taskbar
        # icon as soon as a window becomes visible — set too early and a
        # window with more setup work between icon-set and show() risks
        # that query landing before the icon actually reached the native
        # handle. Observed live: whichever window opens first "wins" the
        # group's icon for the rest of the session.
        self.setWindowIcon(_window_icon())
        _hide_from_taskbar(self)
        self.show()
        _reapply_icon_after_show(self)
        _force_topmost(self)
        _set_joins_all_spaces(self)

        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(300)
        self._blink_timer.timeout.connect(self._advance_blink)
        self._blink_timer.start()

    def _initial_position(
        self,
        width: int,
        height: int,
    ) -> tuple[int, int]:
        phys_x, phys_y, phys_width, phys_height = (
            _physical_screen_bounds(self.screen_geometry)
        )
        query_x = int(phys_x + phys_width - 10)
        query_y = int(phys_y + phys_height - 10)

        try:
            monitor = monitor_rect_for_point(query_x, query_y)
            work = work_area_for_point(query_x, query_y)
        except OSError:
            monitor = WindowRect(
                round(phys_x),
                round(phys_y),
                round(phys_x + phys_width),
                round(phys_y + phys_height),
            )
            work = monitor

        saved = load_position()
        if saved is not None:
            x, y = saved
        elif self.orientation == "vertical":
            if work.right < monitor.right:
                x = work.right
            elif work.left > monitor.left:
                x = monitor.left
            else:
                x = monitor.right - width - RIGHT_MARGIN
            y = monitor.bottom - height - BOTTOM_MARGIN
        else:
            x = monitor.right - width - RIGHT_MARGIN
            if work.bottom < monitor.bottom:
                y = work.bottom
            elif work.top > monitor.top:
                y = monitor.top
            else:
                y = monitor.bottom - height - BOTTOM_MARGIN

        max_x = monitor.right - width
        max_y = monitor.bottom - height
        return (
            min(max(x, monitor.left), max_x),
            min(max(y, monitor.top), max_y),
        )

    def _svg_renderer(
        self,
        provider: str,
        color: str,
    ) -> QSvgRenderer:
        key = provider, color
        renderer = self._svg_cache.get(key)
        if renderer is not None:
            return renderer

        path = (
            CLAUDE_SVG_PATH
            if provider == "claude"
            else CODEX_SVG_PATH
        )
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'viewBox="0 0 24 24">'
            f'<path fill="{color}" d="{path}"/>'
            "</svg>"
        )
        renderer = QSvgRenderer(svg.encode("utf-8"))
        self._svg_cache[key] = renderer
        return renderer

    def _draw_dot(
        self,
        painter: QPainter,
        x: float,
        y: float,
        color_text: str,
        visible: bool,
        diameter: float,
    ) -> None:
        if not visible:
            return

        color = QColor(color_text)
        center_x = x + diameter / 2
        center_y = y + diameter / 2

        glow = QRadialGradient(
            center_x,
            center_y,
            diameter / 2 + 4,
        )
        glow_color = QColor(color)
        glow_color.setAlpha(150)
        transparent = QColor(color)
        transparent.setAlpha(0)
        glow.setColorAt(0.35, glow_color)
        glow.setColorAt(1.0, transparent)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(
            QRectF(
                x - 4,
                y - 4,
                diameter + 8,
                diameter + 8,
            )
        )
        painter.setBrush(color)
        painter.drawEllipse(QRectF(x, y, diameter, diameter))

    def _draw_provider(
        self,
        painter: QPainter,
        name: str,
        rect: QRectF,
    ) -> None:
        colors = THEMES[self.theme]
        provider = self._providers[name]
        text = provider["percentage"]
        font = _font(
            12 if self.orientation == "vertical" else 15,
            bold=True,
        )
        metrics = QFontMetrics(font)

        blink_visible = (
            not provider["blink"] or self._blink_on
        )

        if self.orientation == "vertical":
            text_width = max(1, rect.width() - 4)
            text_height = metrics.height()
            total_height = 10 + 5 + 12 + 5 + text_height
            top = rect.top() + (rect.height() - total_height) / 2
            center_x = rect.center().x()

            self._draw_dot(
                painter,
                center_x - 5,
                top,
                provider["dot_color"],
                blink_visible,
                10,
            )

            icon_rect = QRectF(
                center_x - 6,
                top + 15,
                12,
                12,
            )
            self._svg_renderer(
                name,
                colors["muted"],
            ).render(painter, icon_rect)

            painter.setFont(font)
            painter.setPen(QColor(colors["primary"]))
            elided = metrics.elidedText(
                text,
                Qt.TextElideMode.ElideRight,
                round(text_width),
            )
            painter.drawText(
                QRectF(
                    rect.left() + 2,
                    top + 32,
                    text_width,
                    text_height,
                ),
                Qt.AlignmentFlag.AlignCenter,
                elided,
            )
            return

        available_text_width = max(1, rect.width() - 37)
        display_text = metrics.elidedText(
            text,
            Qt.TextElideMode.ElideRight,
            round(available_text_width),
        )
        text_width = metrics.horizontalAdvance(display_text)
        total_width = 10 + 5 + 12 + 5 + text_width
        left = rect.left() + (rect.width() - total_width) / 2
        center_y = rect.center().y()

        self._draw_dot(
            painter,
            left,
            center_y - 5,
            provider["dot_color"],
            blink_visible,
            10,
        )

        icon_rect = QRectF(
            left + 15,
            center_y - 6,
            12,
            12,
        )
        self._svg_renderer(
            name,
            colors["muted"],
        ).render(painter, icon_rect)

        painter.setFont(font)
        painter.setPen(QColor(colors["primary"]))
        painter.drawText(
            QRectF(
                left + 32,
                center_y - metrics.height() / 2,
                text_width + 1,
                metrics.height(),
            ),
            Qt.AlignmentFlag.AlignVCenter
            | Qt.AlignmentFlag.AlignLeft,
            display_text,
        )

    def paintEvent(self, event) -> None:
        del event

        colors = THEMES[self.theme]
        painter = QPainter(self)
        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing,
            True,
        )

        background = QColor(colors["background"])
        if self._transparent:
            background.setAlphaF(0.7)

        outer = QRectF(
            0.5,
            0.5,
            self.width() - 1,
            self.height() - 1,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(
            outer,
            CORNER_RADIUS,
            CORNER_RADIUS,
        )

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(colors["border"]), 1))
        painter.drawRoundedRect(
            outer,
            CORNER_RADIUS,
            CORNER_RADIUS,
        )

        painter.setPen(QPen(QColor(colors["border"]), 1))

        if self.orientation == "vertical":
            divider_y = self.height() / 2
            painter.drawLine(
                8,
                round(divider_y),
                self.width() - 8,
                round(divider_y),
            )
            claude_rect = QRectF(
                1,
                1,
                self.width() - 2,
                divider_y - 1,
            )
            codex_rect = QRectF(
                1,
                divider_y + 1,
                self.width() - 2,
                self.height() - divider_y - 2,
            )
        else:
            divider_x = self.width() / 2
            painter.drawLine(
                round(divider_x),
                8,
                round(divider_x),
                self.height() - 8,
            )
            claude_rect = QRectF(
                1,
                1,
                divider_x - 1,
                self.height() - 2,
            )
            codex_rect = QRectF(
                divider_x + 1,
                1,
                self.width() - divider_x - 2,
                self.height() - 2,
            )

        self._draw_provider(
            painter,
            "claude",
            claude_rect,
        )
        self._draw_provider(
            painter,
            "codex",
            codex_rect,
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        try:
            cursor_x, cursor_y = _cursor_position()
            rect = read_window_rect(self)
            self._drag_offset = (
                cursor_x - rect.left,
                cursor_y - rect.top,
            )
            event.accept()
        except OSError:
            self._drag_offset = None
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            self._drag_offset is None
            or not event.buttons() & Qt.MouseButton.LeftButton
        ):
            super().mouseMoveEvent(event)
            return

        try:
            cursor_x, cursor_y = _cursor_position()
            width, height = self._physical_size
            _set_native_geometry(
                self,
                cursor_x - self._drag_offset[0],
                cursor_y - self._drag_offset[1],
                width,
                height,
            )
            event.accept()
        except OSError:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._drag_offset is not None
        ):
            self._drag_offset = None
            try:
                save_position(read_window_rect(self))
            except OSError:
                pass
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def _advance_blink(self) -> None:
        if any(
            provider["blink"]
            for provider in self._providers.values()
        ):
            self._blink_on = not self._blink_on
            QWidget.update(self)
        elif not self._blink_on:
            self._blink_on = True
            QWidget.update(self)

    def update(
        self,
        claude_status,
        claude_pct,
        codex_status,
        codex_pct,
        claude_connected: bool = True,
        codex_connected: bool = True,
    ) -> None:
        self._providers["claude"] = {
            "percentage": ui_colors.format_pct(
                claude_pct,
                claude_connected,
                lang=self.lang,
            ),
            "dot_color": ui_colors.color_for_status(
                claude_status,
                connected=claude_connected,
            ),
            "blink": ui_colors.should_blink(
                claude_status,
                connected=claude_connected,
            ),
        }
        self._providers["codex"] = {
            "percentage": ui_colors.format_pct(
                codex_pct,
                codex_connected,
                lang=self.lang,
            ),
            "dot_color": ui_colors.color_for_status(
                codex_status,
                working_color=ui_colors.CODEX_WORKING_COLOR,
                connected=codex_connected,
            ),
            "blink": ui_colors.should_blink(
                codex_status,
                connected=codex_connected,
            ),
        }
        QWidget.update(self)
        _force_topmost(self)

    def set_transparent(self, enabled: bool) -> None:
        self._transparent = bool(enabled)
        QWidget.update(self)

    def destroy(self) -> None:
        if self._destroyed:
            return

        self._destroyed = True
        self._blink_timer.stop()

        try:
            save_position(read_window_rect(self))
        except OSError:
            pass

        self.close()
        self.deleteLater()
