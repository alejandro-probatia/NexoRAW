from __future__ import annotations

import math
from typing import Any

import numpy as np

from ..gui_config import (
    IMAGE_PANEL_BACKGROUND,
    IMAGE_PANEL_BORDER,
    IMAGE_PANEL_TEXT,
    VIEWER_HISTOGRAM_CLIP_ALERT_RATIO,
    VIEWER_HISTOGRAM_HIGHLIGHT_CLIP_U8,
    VIEWER_HISTOGRAM_SHADOW_CLIP_U8,
)
from ..raw.preview import normalize_tone_curve_points, tone_curve_lut

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except Exception:  # pragma: no cover - entorno sin GUI
    QtCore = None
    QtGui = None
    QtWidgets = None

if QtWidgets is not None:
    class PersistentSideTabWidget(QtWidgets.QTabWidget):
        def __init__(self, *, collapsed_margin: int = 6, minimum_tab_width: int = 34) -> None:
            super().__init__()
            self._collapsed_margin = int(collapsed_margin)
            self._minimum_tab_width = int(minimum_tab_width)

        def collapsedWidth(self) -> int:  # noqa: N802
            tab_bar = self.tabBar()
            if tab_bar is None:
                return self._minimum_tab_width
            frame_width = self.style().pixelMetric(QtWidgets.QStyle.PM_DefaultFrameWidth, None, self)
            width = tab_bar.sizeHint().width() + 2 * frame_width + self._collapsed_margin
            return max(self._minimum_tab_width, int(width))

        def minimumSizeHint(self) -> QtCore.QSize:  # noqa: N802
            hint = super().minimumSizeHint()
            return QtCore.QSize(self.collapsedWidth(), min(hint.height(), 160))


    class CollapsibleToolPanel(QtWidgets.QScrollArea):
        def __init__(self) -> None:
            super().__init__()
            self.setWidgetResizable(True)
            self.setFrameShape(QtWidgets.QFrame.NoFrame)
            self._items: list[dict[str, Any]] = []

            self._content = QtWidgets.QWidget()
            self._layout = QtWidgets.QVBoxLayout(self._content)
            self._layout.setContentsMargins(0, 0, 0, 0)
            self._layout.setSpacing(6)
            self._layout.setSizeConstraint(QtWidgets.QLayout.SetMinAndMaxSize)
            self._layout.addStretch(1)
            self.setWidget(self._content)

        def addItem(self, widget: QtWidgets.QWidget, title: str, expanded: bool = True) -> int:  # noqa: N802
            section = QtWidgets.QFrame()
            section.setFrameShape(QtWidgets.QFrame.StyledPanel)
            section.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

            section_layout = QtWidgets.QVBoxLayout(section)
            section_layout.setContentsMargins(0, 0, 0, 0)
            section_layout.setSpacing(0)
            section_layout.setSizeConstraint(QtWidgets.QLayout.SetMinAndMaxSize)

            header = QtWidgets.QToolButton()
            header.setText(title)
            header.setCheckable(True)
            header.setChecked(bool(expanded))
            header.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
            header.setArrowType(QtCore.Qt.DownArrow if expanded else QtCore.Qt.RightArrow)
            header.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            header.setStyleSheet(
                "QToolButton {"
                "text-align: left;"
                "font-weight: 600;"
                "padding: 5px 6px;"
                "border: 0;"
                "}"
            )

            body = QtWidgets.QWidget()
            body_layout = QtWidgets.QVBoxLayout(body)
            body_layout.setContentsMargins(8, 8, 8, 8)
            body_layout.setSpacing(6)
            body_layout.setSizeConstraint(QtWidgets.QLayout.SetMinAndMaxSize)
            body_layout.addWidget(widget)
            body.setVisible(bool(expanded))
            body.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

            def toggle(
                checked: bool,
                *,
                section_widget=section,
                body_widget=body,
                button=header,
            ) -> None:
                button.setArrowType(QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow)
                self._set_section_expanded(section_widget, body_widget, button, bool(checked))

            header.toggled.connect(toggle)
            section_layout.addWidget(header)
            section_layout.addWidget(body)

            self._layout.insertWidget(max(0, self._layout.count() - 1), section)
            self._items.append({"title": title, "header": header, "body": body, "widget": widget, "section": section})
            self._set_section_expanded(section, body, header, bool(expanded))
            return len(self._items) - 1

        def count(self) -> int:
            return len(self._items)

        def itemText(self, index: int) -> str:  # noqa: N802
            if index < 0 or index >= len(self._items):
                return ""
            return str(self._items[index]["title"])

        def indexOf(self, title: str) -> int:  # noqa: N802
            for index, item in enumerate(self._items):
                if str(item["title"]) == title:
                    return index
            return -1

        def setCurrentIndex(self, index: int) -> None:  # noqa: N802
            self.setItemExpanded(index, True)

        def setItemExpanded(self, index: int, expanded: bool) -> None:  # noqa: N802
            if index < 0 or index >= len(self._items):
                return
            header = self._items[index]["header"]
            header.setChecked(bool(expanded))
            if expanded:
                section = self._items[index]["section"]
                QtCore.QTimer.singleShot(0, lambda: self.ensureWidgetVisible(section, 0, 24))

        def isItemExpanded(self, index: int) -> bool:  # noqa: N802
            if index < 0 or index >= len(self._items):
                return False
            return bool(self._items[index]["header"].isChecked())

        def _set_section_expanded(
            self,
            section: QtWidgets.QFrame,
            body: QtWidgets.QWidget,
            header: QtWidgets.QToolButton,
            expanded: bool,
        ) -> None:
            body.setVisible(expanded)
            if expanded:
                section.setMinimumHeight(0)
                section.setMaximumHeight(16777215)
            else:
                collapsed_height = header.sizeHint().height() + 2 * section.frameWidth()
                section.setMinimumHeight(collapsed_height)
                section.setMaximumHeight(collapsed_height)
            body.updateGeometry()
            section.updateGeometry()
            self._content.updateGeometry()
            QtCore.QTimer.singleShot(0, self._content.adjustSize)


    class ToneCurveEditor(QtWidgets.QWidget):
        pointsChanged = QtCore.Signal(object)
        interactionFinished = QtCore.Signal()

        def __init__(self) -> None:
            super().__init__()
            self._points = normalize_tone_curve_points([(0.0, 0.0), (1.0, 1.0)])
            self._drag_index: int | None = None
            self._histogram: np.ndarray | None = None
            self._histogram_luminance: np.ndarray | None = None
            self._histogram_r: np.ndarray | None = None
            self._histogram_g: np.ndarray | None = None
            self._histogram_b: np.ndarray | None = None
            self._active_channel = "luminance"
            self._channel_curves: dict[str, list[tuple[float, float]]] = {
                "luminance": normalize_tone_curve_points([(0.0, 0.0), (1.0, 1.0)]),
                "red": normalize_tone_curve_points([(0.0, 0.0), (1.0, 1.0)]),
                "green": normalize_tone_curve_points([(0.0, 0.0), (1.0, 1.0)]),
                "blue": normalize_tone_curve_points([(0.0, 0.0), (1.0, 1.0)]),
            }
            self._black_point = 0.0
            self._white_point = 1.0
            self._range_dragging = False
            self.setMinimumHeight(320)
            self.setMouseTracking(True)
            self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)

        def hasHeightForWidth(self) -> bool:  # noqa: N802
            return True

        def heightForWidth(self, width: int) -> int:  # noqa: N802
            return int(np.clip(width, 300, 460))

        def sizeHint(self) -> QtCore.QSize:  # noqa: N802
            return QtCore.QSize(340, 340)

        def points(self) -> list[tuple[float, float]]:
            return list(self._points)

        def set_points(self, points: list[tuple[float, float]], *, emit: bool = True) -> None:
            self._points = normalize_tone_curve_points(points)
            self._channel_curves[self._active_channel] = list(self._points)
            self._drag_index = None
            self.update()
            if emit:
                self.pointsChanged.emit(self.points())

        def cancel_interaction(self) -> None:
            if self._drag_index is None:
                return
            self._drag_index = None
            self._points = normalize_tone_curve_points(self._points)
            self._channel_curves[self._active_channel] = list(self._points)
            self.update()

        def set_active_channel(self, channel: str) -> None:
            key = str(channel or "luminance").strip().lower()
            if key not in {"luminance", "red", "green", "blue"}:
                key = "luminance"
            previous = self._active_channel
            if previous in {"luminance", "red", "green", "blue"}:
                self._channel_curves[previous] = list(self._points)
            self._active_channel = key
            self.update()

        def set_channel_curves(self, curves: dict[str, Any] | None) -> None:
            normalized: dict[str, list[tuple[float, float]]] = {}
            for channel in ("luminance", "red", "green", "blue"):
                raw = curves.get(channel) if isinstance(curves, dict) else None
                if isinstance(raw, (list, tuple)):
                    try:
                        normalized[channel] = normalize_tone_curve_points(
                            [
                                (float(point[0]), float(point[1]))
                                for point in raw
                                if isinstance(point, (list, tuple)) and len(point) >= 2
                            ]
                        )
                    except Exception:
                        normalized[channel] = normalize_tone_curve_points([(0.0, 0.0), (1.0, 1.0)])
                else:
                    normalized[channel] = normalize_tone_curve_points([(0.0, 0.0), (1.0, 1.0)])
            normalized[self._active_channel] = list(self._points)
            self._channel_curves = normalized
            self.update()

        def set_input_range(self, black_point: float, white_point: float) -> None:
            black = float(np.clip(black_point, 0.0, 0.95))
            white = float(np.clip(white_point, black + 0.01, 1.0))
            self._black_point = black
            self._white_point = white
            self.update()

        def set_range_dragging(self, dragging: bool) -> None:
            active = bool(dragging)
            if self._range_dragging == active:
                return
            self._range_dragging = active
            self.update()

        def set_histogram_from_image(self, image_linear_rgb: np.ndarray | None, *, channel: str = "luminance") -> None:
            if image_linear_rgb is None:
                self._clear_histograms()
                self.update()
                return
            rgb = np.asarray(image_linear_rgb)
            if rgb.ndim != 3 or rgb.shape[2] < 3:
                self._clear_histograms()
                self.update()
                return
            rgb = np.clip(rgb[..., :3].astype(np.float32, copy=False), 0.0, 1.0)
            key = str(channel or "luminance").strip().lower()
            if key not in {"luminance", "red", "green", "blue"}:
                key = "luminance"
            self._active_channel = key
            weights = np.asarray([0.2126, 0.7152, 0.0722], dtype=np.float32)
            luminance = np.sum(rgb[..., :3] * weights.reshape((1, 1, 3)), axis=2)
            hist_l, _ = np.histogram(luminance, bins=64, range=(0.0, 1.0))
            hist_r, _ = np.histogram(rgb[..., 0], bins=64, range=(0.0, 1.0))
            hist_g, _ = np.histogram(rgb[..., 1], bins=64, range=(0.0, 1.0))
            hist_b, _ = np.histogram(rgb[..., 2], bins=64, range=(0.0, 1.0))
            histograms = {
                "luminance": hist_l.astype(np.float32),
                "red": hist_r.astype(np.float32),
                "green": hist_g.astype(np.float32),
                "blue": hist_b.astype(np.float32),
            }
            if key in {"red", "green", "blue"}:
                maxv = float(np.max(histograms[key])) if histograms[key].size else 0.0
            else:
                maxv = float(max((np.max(hist) for hist in histograms.values() if hist.size), default=0.0))
            if maxv <= 0.0:
                self._clear_histograms()
                self.update()
                return
            self._histogram_luminance = histograms["luminance"] / maxv
            self._histogram_r = histograms["red"] / maxv
            self._histogram_g = histograms["green"] / maxv
            self._histogram_b = histograms["blue"] / maxv
            self._histogram = {
                "red": self._histogram_r,
                "green": self._histogram_g,
                "blue": self._histogram_b,
            }.get(key, self._histogram_luminance)
            self.update()

        def _clear_histograms(self) -> None:
            self._histogram = None
            self._histogram_luminance = None
            self._histogram_r = None
            self._histogram_g = None
            self._histogram_b = None

        def paintEvent(self, _event) -> None:  # noqa: N802
            painter = QtGui.QPainter(self)
            dragging = self.is_dragging() or self.is_range_dragging()
            painter.setRenderHint(QtGui.QPainter.Antialiasing, not dragging)
            rect = self._plot_rect()
            painter.fillRect(self.rect(), QtGui.QColor("#2b2b2b"))
            painter.fillRect(rect, QtGui.QColor("#242424"))

            grid_pen = QtGui.QPen(QtGui.QColor("#505050"), 1)
            painter.setPen(grid_pen)
            for i in range(6):
                x = rect.left() + rect.width() * i / 5.0
                y = rect.top() + rect.height() * i / 5.0
                painter.drawLine(QtCore.QPointF(x, rect.top()), QtCore.QPointF(x, rect.bottom()))
                painter.drawLine(QtCore.QPointF(rect.left(), y), QtCore.QPointF(rect.right(), y))

            self._draw_histogram_columns(painter, rect)

            diagonal_pen = QtGui.QPen(QtGui.QColor("#8a8a8a"), 1, QtCore.Qt.DashLine)
            painter.setPen(diagonal_pen)
            painter.drawLine(self._domain_point_to_widget(0.0, 0.0), self._domain_point_to_widget(1.0, 1.0))

            range_pen = QtGui.QPen(QtGui.QColor("#bdbdbd"), 1, QtCore.Qt.DotLine)
            painter.setPen(range_pen)
            painter.drawLine(
                self._domain_point_to_widget(self._black_point, 0.0),
                self._domain_point_to_widget(self._black_point, 1.0),
            )
            painter.drawLine(
                self._domain_point_to_widget(self._white_point, 0.0),
                self._domain_point_to_widget(self._white_point, 1.0),
            )

            if not dragging:
                self._draw_channel_curve_overlays(painter)

            active_color = self._curve_color(self._active_channel, alpha=235)
            self._draw_curve(painter, self._points, active_color, width=2.6, lut_size=96 if dragging else 256)

            painter.setBrush(QtGui.QBrush(active_color))
            painter.setPen(QtGui.QPen(QtGui.QColor("#101010"), 1))
            for idx, point in enumerate(self._points):
                radius = 5 if idx == self._drag_index else 4
                pos = self._point_to_widget(point)
                painter.drawEllipse(pos, radius, radius)

        def _draw_histogram_columns(self, painter: QtGui.QPainter, rect: QtCore.QRectF) -> None:
            active = self._active_channel
            hist_l = self._histogram_luminance
            hist_r = self._histogram_r
            hist_g = self._histogram_g
            hist_b = self._histogram_b
            if not any(hist is not None and hist.size for hist in (hist_l, hist_r, hist_g, hist_b)):
                return
            if active in {"red", "green", "blue"}:
                hist = {"red": hist_r, "green": hist_g, "blue": hist_b}.get(active)
                if hist is None:
                    return
                self._draw_single_histogram(painter, rect, hist, self._histogram_color(active, alpha=150))
                return
            bins = max(
                int(hist.size)
                for hist in (hist_l, hist_r, hist_g, hist_b)
                if hist is not None and hist.size
            )
            bin_w = rect.width() / max(1, bins)
            painter.setPen(QtCore.Qt.NoPen)

            if hist_l is not None:
                painter.setBrush(QtGui.QColor(120, 120, 120, 70))
                for idx, value in enumerate(hist_l):
                    h = rect.height() * float(value)
                    painter.drawRect(QtCore.QRectF(rect.left() + idx * bin_w, rect.bottom() - h, bin_w + 1.0, h))

            sub_w = bin_w / 3.0 if bin_w >= 3.0 else bin_w
            channels = (
                (hist_r, QtGui.QColor(248, 113, 113, 120), 0),
                (hist_g, QtGui.QColor(134, 239, 172, 115), 1),
                (hist_b, QtGui.QColor(96, 165, 250, 125), 2),
            )
            for hist, color, sub_idx in channels:
                if hist is None:
                    continue
                painter.setBrush(color)
                for idx, value in enumerate(hist):
                    h = rect.height() * float(value)
                    if bin_w >= 3.0:
                        x = rect.left() + idx * bin_w + sub_idx * sub_w
                    else:
                        x = rect.left() + idx * bin_w
                    painter.drawRect(QtCore.QRectF(x, rect.bottom() - h, sub_w + 0.8, h))

        def _draw_single_histogram(
            self,
            painter: QtGui.QPainter,
            rect: QtCore.QRectF,
            hist: np.ndarray,
            color: QtGui.QColor,
        ) -> None:
            if hist is None or not hist.size:
                return
            bins = int(hist.size)
            bin_w = rect.width() / max(1, bins)
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(color)
            for idx, value in enumerate(hist):
                h = rect.height() * float(value)
                painter.drawRect(QtCore.QRectF(rect.left() + idx * bin_w, rect.bottom() - h, bin_w + 1.0, h))

        def _draw_channel_curve_overlays(self, painter: QtGui.QPainter) -> None:
            active = self._active_channel
            chromatic_curves = {
                channel: self._curve_points_for_channel(channel)
                for channel in ("red", "green", "blue")
            }
            for channel, points in chromatic_curves.items():
                if channel == active:
                    continue
                if self._curve_is_identity(points):
                    continue
                self._draw_curve(
                    painter,
                    points,
                    self._curve_color(channel, alpha=150),
                    width=1.7,
                )
            if active != "luminance":
                luminance_points = self._curve_points_for_channel("luminance")
                if not self._curve_is_identity(luminance_points):
                    self._draw_curve(
                        painter,
                        luminance_points,
                        QtGui.QColor(230, 230, 230, 130),
                        width=1.4,
                        style=QtCore.Qt.DashLine,
                    )
            if any(not self._curve_is_identity(points) for points in chromatic_curves.values()):
                self._draw_rgb_luminance_effect(painter, chromatic_curves)

        def _draw_curve(
            self,
            painter: QtGui.QPainter,
            points: list[tuple[float, float]],
            color: QtGui.QColor,
            *,
            width: float,
            lut_size: int = 256,
            style: QtCore.Qt.PenStyle = QtCore.Qt.SolidLine,
        ) -> None:
            curve_x, curve_y = tone_curve_lut(
                points,
                lut_size=max(16, int(lut_size)),
                black_point=self._black_point,
                white_point=self._white_point,
            )
            path = QtGui.QPainterPath(self._domain_point_to_widget(float(curve_x[0]), float(curve_y[0])))
            for x, y in zip(curve_x[1:], curve_y[1:]):
                path.lineTo(self._domain_point_to_widget(float(x), float(y)))
            painter.setPen(QtGui.QPen(color, width, style))
            painter.drawPath(path)

        def _draw_rgb_luminance_effect(
            self,
            painter: QtGui.QPainter,
            chromatic_curves: dict[str, list[tuple[float, float]]],
        ) -> None:
            lut_x: np.ndarray | None = None
            weighted = np.zeros(256, dtype=np.float32)
            weights = {"red": 0.2126, "green": 0.7152, "blue": 0.0722}
            for channel, weight in weights.items():
                x_values, y_values = tone_curve_lut(
                    chromatic_curves[channel],
                    lut_size=256,
                    black_point=self._black_point,
                    white_point=self._white_point,
                )
                if lut_x is None:
                    lut_x = x_values
                weighted += float(weight) * y_values.astype(np.float32)
            if lut_x is None:
                return
            path = QtGui.QPainterPath(self._domain_point_to_widget(float(lut_x[0]), float(weighted[0])))
            for x, y in zip(lut_x[1:], weighted[1:]):
                path.lineTo(self._domain_point_to_widget(float(x), float(y)))
            painter.setPen(QtGui.QPen(QtGui.QColor(250, 204, 21, 150), 1.5, QtCore.Qt.DotLine))
            painter.drawPath(path)

        def _curve_points_for_channel(self, channel: str) -> list[tuple[float, float]]:
            if channel == self._active_channel:
                return list(self._points)
            points = self._channel_curves.get(channel)
            if isinstance(points, list):
                return normalize_tone_curve_points(points)
            return normalize_tone_curve_points([(0.0, 0.0), (1.0, 1.0)])

        def _curve_is_identity(self, points: list[tuple[float, float]]) -> bool:
            curve = normalize_tone_curve_points(points)
            xs = np.asarray([p[0] for p in curve], dtype=np.float32)
            ys = np.asarray([p[1] for p in curve], dtype=np.float32)
            return (
                len(curve) <= 2
                and np.allclose(xs, [0.0, 1.0], atol=1e-6)
                and np.allclose(ys, [0.0, 1.0], atol=1e-6)
                and abs(float(self._black_point)) <= 1e-6
                and abs(float(self._white_point) - 1.0) <= 1e-6
            )

        def _curve_color(self, channel: str, *, alpha: int) -> QtGui.QColor:
            colors = {
                "red": (248, 113, 113),
                "green": (134, 239, 172),
                "blue": (96, 165, 250),
                "luminance": (226, 232, 240),
            }
            r, g, b = colors.get(channel, colors["luminance"])
            return QtGui.QColor(r, g, b, int(alpha))

        def _histogram_color(self, channel: str, *, alpha: int) -> QtGui.QColor:
            return self._curve_color(channel, alpha=alpha)

        def mousePressEvent(self, event) -> None:  # noqa: N802
            pos = event.position()
            nearest = self._nearest_point_index(pos)
            if event.button() == QtCore.Qt.RightButton and nearest not in (None, 0, len(self._points) - 1):
                self._points.pop(int(nearest))
                self.update()
                self.pointsChanged.emit(self.points())
                self.interactionFinished.emit()
                return
            if event.button() != QtCore.Qt.LeftButton:
                return super().mousePressEvent(event)
            if nearest is None:
                self._points.append(self._widget_to_point(pos))
                self._points = normalize_tone_curve_points(self._points)
                self._channel_curves[self._active_channel] = list(self._points)
                nearest = self._nearest_point_index(pos)
            self._drag_index = nearest

        def mouseMoveEvent(self, event) -> None:  # noqa: N802
            if self._drag_index is None:
                return super().mouseMoveEvent(event)
            idx = int(self._drag_index)
            if idx == 0 or idx == len(self._points) - 1:
                return
            x, y = self._widget_to_point(event.position())
            left = self._points[idx - 1][0] + 0.01
            right = self._points[idx + 1][0] - 0.01
            lower_y = self._points[idx - 1][1]
            upper_y = self._points[idx + 1][1]
            self._points[idx] = (
                float(np.clip(x, left, right)),
                float(np.clip(y, lower_y, upper_y)),
            )
            self._channel_curves[self._active_channel] = list(self._points)
            self.update()

        def mouseReleaseEvent(self, event) -> None:  # noqa: N802
            had_drag = self._drag_index is not None
            self._drag_index = None
            self._points = normalize_tone_curve_points(self._points)
            self._channel_curves[self._active_channel] = list(self._points)
            self.update()
            if had_drag:
                self.interactionFinished.emit()
            return super().mouseReleaseEvent(event)

        def is_dragging(self) -> bool:
            return self._drag_index is not None

        def is_range_dragging(self) -> bool:
            return bool(self._range_dragging)

        def changeEvent(self, event) -> None:  # noqa: N802
            if event.type() == QtCore.QEvent.EnabledChange and not self.isEnabled():
                self.cancel_interaction()
            return super().changeEvent(event)

        def _plot_rect(self) -> QtCore.QRectF:
            available_w = max(20.0, float(self.width() - 24))
            available_h = max(20.0, float(self.height() - 24))
            side = min(available_w, available_h)
            left = (float(self.width()) - side) / 2.0
            top = (float(self.height()) - side) / 2.0
            return QtCore.QRectF(left, top, side, side)

        def _point_to_widget(self, point: tuple[float, float]) -> QtCore.QPointF:
            domain_x = self._black_point + float(point[0]) * max(1e-4, self._white_point - self._black_point)
            return self._domain_point_to_widget(domain_x, float(point[1]))

        def _domain_point_to_widget(self, x_value: float, y_value: float) -> QtCore.QPointF:
            rect = self._plot_rect()
            x = rect.left() + float(np.clip(x_value, 0.0, 1.0)) * rect.width()
            y = rect.bottom() - float(np.clip(y_value, 0.0, 1.0)) * rect.height()
            return QtCore.QPointF(x, y)

        def _widget_to_point(self, pos: QtCore.QPointF) -> tuple[float, float]:
            rect = self._plot_rect()
            domain_x = (pos.x() - rect.left()) / max(1.0, rect.width())
            x = (domain_x - self._black_point) / max(1e-4, self._white_point - self._black_point)
            y = (rect.bottom() - pos.y()) / max(1.0, rect.height())
            return float(np.clip(x, 0.0, 1.0)), float(np.clip(y, 0.0, 1.0))

        def _nearest_point_index(self, pos: QtCore.QPointF) -> int | None:
            best_idx = None
            best_dist = 14.0
            for idx, point in enumerate(self._points):
                p = self._point_to_widget(point)
                dist = float(np.hypot(p.x() - pos.x(), p.y() - pos.y()))
                if dist < best_dist:
                    best_dist = dist
                    best_idx = idx
            return best_idx


    class MTFPlotWidget(QtWidgets.QWidget):
        """Render one MTF analysis curve family for the sharpness panel.

        ``curve`` selects the view: ``esf``, ``lsf``, ``mtf`` or ``ca``. The
        widget is deliberately data-only: callers provide an ``MTFResult``-like
        object and the painter derives all axes, labels and analysis overlays
        locally. This keeps the persistence format and the visual presentation
        decoupled while sharing one rendering path for the docked and expanded
        dialogs.
        """

        EXTENDED_DISPLAY_MAX_FREQUENCY = 1.0

        def __init__(self, curve: str = "mtf") -> None:
            super().__init__()
            self._curve = str(curve or "mtf").lower()
            self._result: Any | None = None
            self._hover_pos: QtCore.QPointF | None = None
            self.setMouseTracking(True)
            self.setMinimumHeight(260)
            self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        def set_result(self, result: Any | None) -> None:
            self._result = result
            self.update()

        def clear(self) -> None:
            self._result = None
            self.update()

        def paintEvent(self, _event) -> None:  # noqa: N802
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            painter.fillRect(self.rect(), QtGui.QColor("#202020"))
            plot = self.rect().adjusted(56, 22, -18, -44)
            painter.fillRect(plot, QtGui.QColor("#181818"))

            x_values, y_values, title, x_label, y_label = self._curve_payload()
            painter.setPen(QtGui.QPen(QtGui.QColor("#d8d8d8"), 1))
            painter.drawText(self.rect().adjusted(8, 2, -8, -4), QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft, title)
            painter.drawText(self.rect().adjusted(8, 0, -8, -8), QtCore.Qt.AlignBottom | QtCore.Qt.AlignHCenter, x_label)
            painter.save()
            painter.translate(14, self.rect().center().y())
            painter.rotate(-90)
            painter.drawText(QtCore.QRectF(-72, -8, 144, 16), QtCore.Qt.AlignCenter, y_label)
            painter.restore()

            if x_values.size < 2 or y_values.size < 2:
                self._draw_empty_grid(painter, plot)
                painter.setPen(QtGui.QPen(QtGui.QColor("#a8a8a8"), 1))
                painter.drawText(plot, QtCore.Qt.AlignCenter, self.tr("Selecciona una ROI de borde inclinado"))
                painter.end()
                return

            xmin, xmax = self._x_range(x_values)
            ymin, ymax = self._y_range(y_values)
            if xmax <= xmin or ymax <= ymin:
                painter.end()
                return

            self._draw_axes(painter, plot, xmin, xmax, ymin, ymax)
            if self._curve == "esf":
                self._draw_top_pixel_scale(painter, plot, xmin, xmax, ymin, ymax)
                self._draw_esf_pixel_strip(painter, plot, xmin, xmax)
            if self._curve == "mtf":
                self._draw_nyquist_marker(painter, plot, xmin, xmax)

            if self._curve == "mtf":
                self._draw_mtf_curve(painter, plot, x_values, y_values, xmin, xmax, ymin, ymax)
                self._draw_mtf_reference_levels(painter, plot, ymin, ymax)
            elif self._curve == "ca":
                self._draw_ca_profiles(painter, plot, xmin, xmax, ymin, ymax)
            else:
                self._draw_curve_path(painter, plot, x_values, y_values, xmin, xmax, ymin, ymax)
            self._draw_analysis_annotations(painter, plot, xmin, xmax, ymin, ymax)
            self._draw_hover_coordinates(painter, plot, xmin, xmax, ymin, ymax)
            painter.end()

        def mouseMoveEvent(self, event) -> None:  # noqa: N802
            self._hover_pos = event.position()
            self.update()
            super().mouseMoveEvent(event)

        def leaveEvent(self, event) -> None:  # noqa: N802
            self._hover_pos = None
            self.update()
            super().leaveEvent(event)

        # Data extraction -------------------------------------------------

        def _curve_payload(self) -> tuple[np.ndarray, np.ndarray, str, str, str]:
            result = self._result
            if result is None:
                return np.asarray([]), np.asarray([]), self._title(), "", ""
            if self._curve == "esf":
                return (
                    np.asarray(getattr(result, "esf_distance", []), dtype=np.float64),
                    np.asarray(getattr(result, "esf", []), dtype=np.float64),
                    "ESF",
                    self.tr("distancia al borde (px)"),
                    self.tr("señal normalizada"),
                )
            if self._curve == "lsf":
                return (
                    np.asarray(getattr(result, "lsf_distance", []), dtype=np.float64),
                    np.asarray(getattr(result, "lsf", []), dtype=np.float64),
                    "LSF",
                    self.tr("distancia al borde (px)"),
                    self.tr("derivada"),
                )
            if self._curve == "ca":
                x, red, green, blue, diff = self._ca_payload()
                y = np.concatenate([red - green, blue - green, diff]) if red.size and green.size and blue.size else diff
                return (
                    x,
                    y,
                    "CA lateral: diferencias RGB",
                    self.tr("pixeles"),
                    self.tr("diferencia normalizada"),
                )
            frequency = getattr(result, "frequency_extended", None)
            mtf = getattr(result, "mtf_extended", None)
            if frequency is None or len(frequency) == 0:
                frequency = getattr(result, "frequency", [])
            if mtf is None or len(mtf) == 0:
                mtf = getattr(result, "mtf", [])
            return (
                np.asarray(frequency, dtype=np.float64),
                np.asarray(mtf, dtype=np.float64),
                "MTF",
                self.tr("ciclos/píxel"),
                self.tr("modulación"),
            )

        def _title(self) -> str:
            return {"esf": "ESF", "lsf": "LSF", "ca": "CA lateral RGB"}.get(self._curve, "MTF")

        # Axis ranges and scales -----------------------------------------

        def _x_range(self, values: np.ndarray) -> tuple[float, float]:
            finite = np.asarray(values, dtype=np.float64)
            finite = finite[np.isfinite(finite)]
            if finite.size == 0:
                return 0.0, 1.0
            xmin = float(np.min(finite))
            xmax = float(np.max(finite))
            if self._curve == "mtf":
                xmin = min(0.0, xmin)
                xmax = max(0.5, xmax)
                if xmax > 0.5:
                    xmax = min(
                        self.EXTENDED_DISPLAY_MAX_FREQUENCY,
                        float(np.ceil(xmax / 0.5) * 0.5),
                    )
            elif self._curve == "ca":
                xmin, xmax = self._ca_zoomed_x_range(xmin, xmax)
            elif self._curve == "esf":
                xmin, xmax = self._esf_zoomed_x_range(xmin, xmax)
            if xmax <= xmin:
                return xmin - 0.5, xmax + 0.5
            return xmin, xmax

        def _y_range(self, values: np.ndarray) -> tuple[float, float]:
            if self._curve == "ca":
                finite = np.asarray(values, dtype=np.float64)
                finite = finite[np.isfinite(finite)]
                if finite.size == 0:
                    return -0.02, 0.02
                span = max(abs(float(np.min(finite))), abs(float(np.max(finite))), 0.005)
                limit = min(0.35, max(0.02, span * 1.35))
                return -limit, limit
            if self._curve == "mtf":
                return 0.0, max(1.0, float(np.nanmax(values)) * 1.05)
            ymin = float(np.nanmin(values))
            ymax = float(np.nanmax(values))
            if ymax <= ymin:
                return ymin - 0.5, ymax + 0.5
            pad = (ymax - ymin) * 0.08
            return ymin - pad, ymax + pad

        def _draw_empty_grid(self, painter: QtGui.QPainter, plot: QtCore.QRect) -> None:
            painter.setPen(QtGui.QPen(QtGui.QColor("#454545"), 1))
            for i in range(5):
                x = plot.left() + plot.width() * i / 4.0
                y = plot.top() + plot.height() * i / 4.0
                painter.drawLine(x, plot.top(), x, plot.bottom())
                painter.drawLine(plot.left(), y, plot.right(), y)

        def _draw_axes(
            self,
            painter: QtGui.QPainter,
            plot: QtCore.QRect,
            xmin: float,
            xmax: float,
            ymin: float,
            ymax: float,
        ) -> None:
            painter.setPen(QtGui.QPen(QtGui.QColor("#454545"), 1))
            font = painter.font()
            font.setPointSize(max(7, font.pointSize() - 1))
            painter.setFont(font)

            minor_ticks = self._minor_axis_ticks(xmin, xmax)
            if minor_ticks:
                painter.setPen(QtGui.QPen(QtGui.QColor("#333333"), 1))
                for value in minor_ticks:
                    px, _py = self._data_to_plot(value, ymin, plot, xmin, xmax, ymin, ymax)
                    painter.drawLine(px, plot.top(), px, plot.bottom())

            painter.setPen(QtGui.QPen(QtGui.QColor("#454545"), 1))
            for value in self._axis_ticks(xmin, xmax):
                px, _py = self._data_to_plot(value, ymin, plot, xmin, xmax, ymin, ymax)
                painter.drawLine(px, plot.top(), px, plot.bottom())
                painter.setPen(QtGui.QPen(QtGui.QColor("#a8a8a8"), 1))
                label_rect = QtCore.QRectF(px - 28, plot.bottom() + 3, 56, 16)
                painter.drawText(label_rect, QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop, self._format_axis_value(value))
                painter.setPen(QtGui.QPen(QtGui.QColor("#454545"), 1))

            for value in self._axis_ticks(ymin, ymax):
                _px, py = self._data_to_plot(xmin, value, plot, xmin, xmax, ymin, ymax)
                painter.drawLine(plot.left(), py, plot.right(), py)
                painter.setPen(QtGui.QPen(QtGui.QColor("#a8a8a8"), 1))
                label_rect = QtCore.QRectF(plot.left() - 50, py - 8, 44, 16)
                painter.drawText(label_rect, QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, self._format_axis_value(value))
                painter.setPen(QtGui.QPen(QtGui.QColor("#454545"), 1))

            painter.setPen(QtGui.QPen(QtGui.QColor("#5c5c5c"), 1))
            painter.drawRect(plot)

        def _draw_nyquist_marker(
            self,
            painter: QtGui.QPainter,
            plot: QtCore.QRect,
            xmin: float,
            xmax: float,
        ) -> None:
            if not (xmin <= 0.5 <= xmax):
                return
            px = plot.left() + (0.5 - xmin) / (xmax - xmin) * plot.width()
            if xmax > 0.5:
                post_rect = QtCore.QRectF(px, plot.top(), plot.right() - px, plot.height())
                painter.fillRect(post_rect, QtGui.QColor(239, 68, 68, 18))
            painter.setPen(QtGui.QPen(QtGui.QColor("#ef4444"), 1, QtCore.Qt.DashDotLine))
            painter.drawLine(px, plot.top(), px, plot.bottom())

        # Curve rendering -------------------------------------------------

        def _draw_curve_path(
            self,
            painter: QtGui.QPainter,
            plot: QtCore.QRect,
            x_values: np.ndarray,
            y_values: np.ndarray,
            xmin: float,
            xmax: float,
            ymin: float,
            ymax: float,
            *,
            pen: QtGui.QPen | None = None,
        ) -> None:
            path = QtGui.QPainterPath()
            started = False
            for x, y in zip(x_values, y_values, strict=True):
                if not np.isfinite(x) or not np.isfinite(y):
                    continue
                if float(x) < xmin or float(x) > xmax:
                    continue
                px, py = self._data_to_plot(float(x), float(y), plot, xmin, xmax, ymin, ymax)
                if not started:
                    path.moveTo(px, py)
                    started = True
                else:
                    path.lineTo(px, py)
            if started:
                painter.setPen(pen or QtGui.QPen(QtGui.QColor("#38bdf8"), 2))
                painter.drawPath(path)

        def _draw_mtf_curve(
            self,
            painter: QtGui.QPainter,
            plot: QtCore.QRect,
            x_values: np.ndarray,
            y_values: np.ndarray,
            xmin: float,
            xmax: float,
            ymin: float,
            ymax: float,
        ) -> None:
            x = np.asarray(x_values, dtype=np.float64)
            y = np.asarray(y_values, dtype=np.float64)
            in_band = x <= 0.5
            post_band = x >= 0.5
            self._draw_curve_path(
                painter,
                plot,
                x[in_band],
                y[in_band],
                xmin,
                xmax,
                ymin,
                ymax,
                pen=QtGui.QPen(QtGui.QColor("#38bdf8"), 2),
            )
            self._draw_curve_path(
                painter,
                plot,
                x[post_band],
                y[post_band],
                xmin,
                xmax,
                ymin,
                ymax,
                pen=QtGui.QPen(QtGui.QColor("#f97316"), 2, QtCore.Qt.DashLine),
            )

        def _draw_mtf_reference_levels(
            self,
            painter: QtGui.QPainter,
            plot: QtCore.QRect,
            ymin: float,
            ymax: float,
        ) -> None:
            metrics = painter.fontMetrics()
            for level in (0.5, 0.3, 0.1):
                py = plot.bottom() - (level - ymin) / (ymax - ymin) * plot.height()
                if plot.top() <= py <= plot.bottom():
                    painter.setPen(QtGui.QPen(QtGui.QColor("#f59e0b"), 1, QtCore.Qt.DashLine))
                    painter.drawLine(plot.left(), py, plot.right(), py)
                    label = f"MTF{int(level * 100)}"
                    label_rect = QtCore.QRectF(plot.left() + 5, py - metrics.height() - 2, metrics.horizontalAdvance(label) + 10, metrics.height() + 4)
                    painter.setPen(QtGui.QPen(QtGui.QColor("#92400e"), 1))
                    painter.setBrush(QtGui.QColor(15, 23, 42, 190))
                    painter.drawRoundedRect(label_rect, 3, 3)
                    painter.setPen(QtGui.QPen(QtGui.QColor("#fde68a"), 1))
                    painter.drawText(label_rect, QtCore.Qt.AlignCenter, label)

        def _draw_top_pixel_scale(
            self,
            painter: QtGui.QPainter,
            plot: QtCore.QRect,
            xmin: float,
            xmax: float,
            ymin: float,
            ymax: float,
        ) -> None:
            painter.setPen(QtGui.QPen(QtGui.QColor("#7a7a7a"), 1))
            top_y = plot.top()
            for value in self._axis_ticks(xmin, xmax):
                px, _py = self._data_to_plot(value, ymax, plot, xmin, xmax, ymin, ymax)
                painter.drawLine(px, top_y, px, top_y + 6)
                label = self._format_axis_value(value)
                painter.setPen(QtGui.QPen(QtGui.QColor("#d8d8d8"), 1))
                painter.drawText(QtCore.QRectF(px - 24, top_y + 6, 48, 14), QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop, label)
                painter.setPen(QtGui.QPen(QtGui.QColor("#7a7a7a"), 1))

        # Pixel strips ----------------------------------------------------

        def _draw_esf_pixel_strip(self, painter: QtGui.QPainter, plot: QtCore.QRect, xmin: float, xmax: float) -> None:
            x, values = self._esf_pixel_strip_payload()
            if x.size == 0 or values.size == 0:
                return
            strip = QtCore.QRectF(plot.left(), plot.top() + 21, plot.width(), 16)
            painter.setPen(QtGui.QPen(QtGui.QColor("#5a5a5a"), 1))
            painter.drawRect(strip)
            for distance, value in zip(x, values, strict=False):
                x0 = float(distance) - 0.5
                x1 = float(distance) + 0.5
                if x1 < xmin or x0 > xmax:
                    continue
                px0 = plot.left() + (max(x0, xmin) - xmin) / (xmax - xmin) * plot.width()
                px1 = plot.left() + (min(x1, xmax) - xmin) / (xmax - xmin) * plot.width()
                if px1 <= px0:
                    px1 = px0 + 1.0
                gray = int(np.clip(round(float(value) * 255.0), 0, 255))
                painter.fillRect(QtCore.QRectF(px0, strip.top() + 1, px1 - px0, strip.height() - 2), QtGui.QColor(gray, gray, gray))
            painter.setPen(QtGui.QPen(QtGui.QColor("#d8d8d8"), 1))
            painter.drawText(strip.adjusted(6, 0, -6, 0), QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, self.tr("tonos de pixeles del borde"))

        def _esf_pixel_strip_payload(self) -> tuple[np.ndarray, np.ndarray]:
            x, rgb = self._ca_pixel_strip_payload()
            if x.size and rgb.size:
                return x, np.clip(0.2126 * rgb[:, 0] + 0.7152 * rgb[:, 1] + 0.0722 * rgb[:, 2], 0.0, 1.0)
            result = self._result
            if result is None:
                return np.asarray([], dtype=np.float64), np.asarray([], dtype=np.float64)
            distance = np.asarray(getattr(result, "esf_distance", []), dtype=np.float64)
            signal = np.asarray(getattr(result, "esf", []), dtype=np.float64)
            count = min(distance.size, signal.size)
            if count <= 0:
                return np.asarray([], dtype=np.float64), np.asarray([], dtype=np.float64)
            samples = np.arange(math.floor(float(np.min(distance[:count]))), math.ceil(float(np.max(distance[:count]))) + 1, dtype=np.float64)
            return samples, np.interp(samples, distance[:count], signal[:count])

        def _esf_zoomed_x_range(self, xmin: float, xmax: float) -> tuple[float, float]:
            result = self._result
            if result is None:
                return xmin, xmax
            x = np.asarray(getattr(result, "esf_distance", []), dtype=np.float64)
            y = np.asarray(getattr(result, "esf", []), dtype=np.float64)
            valid = np.isfinite(x) & np.isfinite(y)
            x = x[valid]
            y = y[valid]
            center = self._level_crossing(x, np.maximum.accumulate(y), 0.5) if x.size >= 2 else None
            if center is None or not np.isfinite(float(center)):
                center = 0.5 * (float(xmin) + float(xmax))
            return max(float(xmin), float(center) - 10.0), min(float(xmax), float(center) + 10.0)

        # Analysis overlays ----------------------------------------------

        def _draw_analysis_annotations(
            self,
            painter: QtGui.QPainter,
            plot: QtCore.QRect,
            xmin: float,
            xmax: float,
            ymin: float,
            ymax: float,
        ) -> None:
            result = self._result
            if result is None:
                return
            lines = self._analysis_summary_lines()
            if lines:
                summary_top = 42 if self._curve in {"esf", "ca"} else 8
                self._draw_annotation_box(painter, plot.adjusted(8, summary_top, -8, -8), lines, align_right=False)
            if self._curve == "esf":
                self._draw_esf_rise_annotation(painter, plot, xmin, xmax, ymin, ymax)
            elif self._curve == "mtf":
                self._draw_mtf_metric_annotations(painter, plot, xmin, xmax, ymin, ymax)
            elif self._curve == "ca":
                self._draw_ca_annotations(painter, plot, xmin, xmax, ymin, ymax)

        def _analysis_summary_lines(self) -> list[str]:
            result = self._result
            if result is None:
                return []
            lines: list[str] = []
            shape = getattr(result, "roi_shape", None)
            if isinstance(shape, (list, tuple)) and len(shape) >= 2:
                h = max(0, int(shape[0]))
                w = max(0, int(shape[1]))
                pixels = int(w * h)
                if pixels > 0:
                    lines.append(f"ROI: {w} x {h} px ({pixels / 1_000_000.0:.3f} Mpix)")
            count = self._curve_sample_count()
            if count > 0:
                lines.append(self.tr("Muestras") + f": {count}")
            return lines

        def _curve_sample_count(self) -> int:
            result = self._result
            if result is None:
                return 0
            if self._curve == "esf":
                return len(getattr(result, "esf", []) or [])
            if self._curve == "lsf":
                return len(getattr(result, "lsf", []) or [])
            if self._curve == "ca":
                return len(getattr(result, "ca_distance", []) or [])
            values = getattr(result, "mtf_extended", None)
            if values is None or len(values) == 0:
                values = getattr(result, "mtf", []) or []
            return len(values)

        # Chromatic-aberration helpers -----------------------------------

        def _ca_payload(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
            result = self._result
            if result is None:
                empty = np.asarray([], dtype=np.float64)
                return empty, empty, empty, empty, empty
            x = np.asarray(getattr(result, "ca_distance", []), dtype=np.float64)
            red = np.asarray(getattr(result, "ca_red", []), dtype=np.float64)
            green = np.asarray(getattr(result, "ca_green", []), dtype=np.float64)
            blue = np.asarray(getattr(result, "ca_blue", []), dtype=np.float64)
            diff = np.asarray(getattr(result, "ca_diff", []), dtype=np.float64)
            count = min(x.size, red.size, green.size, blue.size, diff.size)
            if count <= 0:
                empty = np.asarray([], dtype=np.float64)
                return empty, empty, empty, empty, empty
            return x[:count], red[:count], green[:count], blue[:count], diff[:count]

        def _ca_pixel_strip_payload(self) -> tuple[np.ndarray, np.ndarray]:
            result = self._result
            if result is None:
                return np.asarray([], dtype=np.float64), np.empty((0, 3), dtype=np.float64)
            x = np.asarray(getattr(result, "ca_pixel_distance", []), dtype=np.float64)
            red = np.asarray(getattr(result, "ca_pixel_red", []), dtype=np.float64)
            green = np.asarray(getattr(result, "ca_pixel_green", []), dtype=np.float64)
            blue = np.asarray(getattr(result, "ca_pixel_blue", []), dtype=np.float64)
            count = min(x.size, red.size, green.size, blue.size)
            if count <= 0:
                return np.asarray([], dtype=np.float64), np.empty((0, 3), dtype=np.float64)
            rgb = np.column_stack([red[:count], green[:count], blue[:count]])
            return x[:count], rgb

        def _ca_zoomed_x_range(self, xmin: float, xmax: float) -> tuple[float, float]:
            x, _red, green, _blue, _diff = self._ca_payload()
            center = None
            if x.size >= 2 and green.size >= 2:
                center = self._level_crossing(x, np.maximum.accumulate(green), 0.5)
            width = self._optional_float(getattr(self._result, "ca_edge_width_10_90_pixels", None))
            crossing = self._optional_float(getattr(self._result, "ca_crossing_pixels", None))
            half_span = max(6.0, (width or 0.0) * 3.0, (crossing or 0.0) * 8.0)
            half_span = min(30.0, half_span)
            if center is None or not np.isfinite(float(center)):
                center = 0.5 * (float(xmin) + float(xmax))
            left = max(float(xmin), float(center) - half_span)
            right = min(float(xmax), float(center) + half_span)
            if right - left < 4.0:
                left = max(float(xmin), float(center) - 2.0)
                right = min(float(xmax), float(center) + 2.0)
            return left, right

        def _draw_ca_profiles(
            self,
            painter: QtGui.QPainter,
            plot: QtCore.QRect,
            xmin: float,
            xmax: float,
            ymin: float,
            ymax: float,
        ) -> None:
            x, red, green, blue, diff = self._ca_payload()
            self._draw_ca_pixel_strip(painter, plot, xmin, xmax)
            if ymin < 0.0 < ymax:
                _px, py = self._data_to_plot(xmin, 0.0, plot, xmin, xmax, ymin, ymax)
                painter.setPen(QtGui.QPen(QtGui.QColor("#7a7a7a"), 1, QtCore.Qt.DashLine))
                painter.drawLine(plot.left(), py, plot.right(), py)
            self._draw_curve_path(painter, plot, x, red - green, xmin, xmax, ymin, ymax, pen=QtGui.QPen(QtGui.QColor("#ef4444"), 2))
            self._draw_curve_path(painter, plot, x, blue - green, xmin, xmax, ymin, ymax, pen=QtGui.QPen(QtGui.QColor("#3b82f6"), 2))
            self._draw_curve_path(painter, plot, x, diff, xmin, xmax, ymin, ymax, pen=QtGui.QPen(QtGui.QColor("#d946ef"), 2, QtCore.Qt.DotLine))
            self._draw_channel_legend(painter, plot)

        def _draw_ca_pixel_strip(self, painter: QtGui.QPainter, plot: QtCore.QRect, xmin: float, xmax: float) -> None:
            distances, rgb = self._ca_pixel_strip_payload()
            if distances.size == 0 or rgb.size == 0:
                return
            strip = QtCore.QRectF(plot.left(), plot.top() + 4, plot.width(), 18)
            painter.setPen(QtGui.QPen(QtGui.QColor("#5a5a5a"), 1))
            painter.drawRect(strip)
            for distance, color in zip(distances, rgb, strict=False):
                x0 = float(distance) - 0.5
                x1 = float(distance) + 0.5
                if x1 < xmin or x0 > xmax:
                    continue
                px0 = plot.left() + (max(x0, xmin) - xmin) / (xmax - xmin) * plot.width()
                px1 = plot.left() + (min(x1, xmax) - xmin) / (xmax - xmin) * plot.width()
                if px1 <= px0:
                    px1 = px0 + 1.0
                r, g, b = [int(np.clip(round(float(v) * 255.0), 0, 255)) for v in color[:3]]
                painter.fillRect(QtCore.QRectF(px0, strip.top() + 1, px1 - px0, strip.height() - 2), QtGui.QColor(r, g, b))
            painter.setPen(QtGui.QPen(QtGui.QColor("#d8d8d8"), 1))
            painter.drawText(strip.adjusted(6, 0, -6, 0), QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, self.tr("fila de pixeles del borde"))

        def _draw_channel_legend(self, painter: QtGui.QPainter, plot: QtCore.QRect) -> None:
            entries = [("R-G", "#ef4444"), ("B-G", "#3b82f6"), ("CA", "#d946ef")]
            metrics = painter.fontMetrics()
            width = 146
            height = metrics.height() + 12
            rect = QtCore.QRectF(plot.right() - width - 8, plot.bottom() - height - 8, width, height)
            painter.setPen(QtGui.QPen(QtGui.QColor("#454545"), 1))
            painter.setBrush(QtGui.QColor(15, 23, 42, 210))
            painter.drawRoundedRect(rect, 4, 4)
            x = rect.left() + 8
            for label, color in entries:
                painter.setPen(QtGui.QPen(QtGui.QColor(color), 3))
                y = rect.center().y()
                painter.drawLine(x, y, x + 12, y)
                painter.setPen(QtGui.QPen(QtGui.QColor("#e6e6e6"), 1))
                painter.drawText(QtCore.QRectF(x + 16, rect.top() + 4, 34, metrics.height()), QtCore.Qt.AlignVCenter, label)
                x += 44

        def _draw_ca_annotations(
            self,
            painter: QtGui.QPainter,
            plot: QtCore.QRect,
            xmin: float,
            xmax: float,
            ymin: float,
            ymax: float,
        ) -> None:
            result = self._result
            if result is None:
                return
            lines: list[str] = []
            area = self._optional_float(getattr(result, "ca_area_pixels", None))
            crossing = self._optional_float(getattr(result, "ca_crossing_pixels", None))
            rg = self._optional_float(getattr(result, "ca_red_green_shift_pixels", None))
            bg = self._optional_float(getattr(result, "ca_blue_green_shift_pixels", None))
            width = self._optional_float(getattr(result, "ca_edge_width_10_90_pixels", None))
            if area is not None:
                lines.append(f"CA area: {area:.3f} px")
            if crossing is not None:
                lines.append(f"CA cruce: {crossing:.3f} px")
            if rg is not None or bg is not None:
                lines.append(f"R-G: {rg:+.3f} px  B-G: {bg:+.3f} px")
            if width is not None:
                lines.append(f"10-90: {width:.2f} px")
            if lines:
                self._draw_annotation_box(painter, plot.adjusted(8, 34, -8, -8), lines, align_right=True)
            x, red, green, blue, _diff = self._ca_payload()
            for values, color in ((red, "#ef4444"), (green, "#22c55e"), (blue, "#3b82f6")):
                crossing_x = self._level_crossing(x, np.maximum.accumulate(values), 0.5)
                if crossing_x is not None and xmin <= crossing_x <= xmax:
                    marker_y = 0.0 if ymin <= 0.0 <= ymax else 0.5 * (ymin + ymax)
                    self._draw_frequency_marker(painter, plot, xmin, xmax, ymin, ymax, crossing_x, marker_y, color)

        # ESF/MTF metric annotations -------------------------------------

        def _draw_esf_rise_annotation(
            self,
            painter: QtGui.QPainter,
            plot: QtCore.QRect,
            xmin: float,
            xmax: float,
            ymin: float,
            ymax: float,
        ) -> None:
            rise = self._esf_rise_10_90()
            if rise is None:
                return
            x10, x90, width = rise
            if not (xmin <= x10 <= xmax or xmin <= x90 <= xmax):
                return
            y10 = 0.10
            y90 = 0.90
            px10, py10 = self._data_to_plot(x10, y10, plot, xmin, xmax, ymin, ymax)
            px90, py90 = self._data_to_plot(x90, y90, plot, xmin, xmax, ymin, ymax)
            painter.setPen(QtGui.QPen(QtGui.QColor("#e879f9"), 1, QtCore.Qt.DashLine))
            painter.drawLine(px10, plot.top(), px10, plot.bottom())
            painter.drawLine(px90, plot.top(), px90, plot.bottom())
            painter.setPen(QtGui.QPen(QtGui.QColor("#f7f7f7"), 1))
            bracket_y = min(max(plot.top() + 34, (py10 + py90) * 0.5), plot.bottom() - 24)
            painter.drawLine(px10, bracket_y, px90, bracket_y)
            painter.drawLine(px10, bracket_y - 4, px10, bracket_y + 4)
            painter.drawLine(px90, bracket_y - 4, px90, bracket_y + 4)
            text = self.tr("10-90 rise") + f": {width:.2f} px"
            metrics = painter.fontMetrics()
            rect = QtCore.QRectF(
                min(max(plot.left() + 8, (px10 + px90) * 0.5 - metrics.horizontalAdvance(text) / 2 - 8), plot.right() - metrics.horizontalAdvance(text) - 20),
                bracket_y - metrics.height() - 8,
                metrics.horizontalAdvance(text) + 16,
                metrics.height() + 6,
            )
            self._draw_annotation_box(painter, rect, [text], align_right=False)

        def _draw_mtf_metric_annotations(
            self,
            painter: QtGui.QPainter,
            plot: QtCore.QRect,
            xmin: float,
            xmax: float,
            ymin: float,
            ymax: float,
        ) -> None:
            result = self._result
            if result is None:
                return
            lines: list[str] = []
            mtf50 = self._optional_float(getattr(result, "mtf50", None))
            mtf50p = self._optional_float(getattr(result, "mtf50p", None))
            mtf30 = self._optional_float(getattr(result, "mtf30", None))
            mtf10 = self._optional_float(getattr(result, "mtf10", None))
            if mtf50 is not None:
                lines.append(f"MTF50: {mtf50:.3f} c/p")
                self._draw_frequency_marker(painter, plot, xmin, xmax, ymin, ymax, mtf50, 0.5, "#f7f7f7")
            if mtf50p is not None:
                lines.append(f"MTF50P: {mtf50p:.3f} c/p")
                self._draw_frequency_marker(painter, plot, xmin, xmax, ymin, ymax, mtf50p, 0.5, "#a78bfa")
            if mtf30 is not None:
                lines.append(f"MTF30: {mtf30:.3f} c/p")
                self._draw_frequency_marker(painter, plot, xmin, xmax, ymin, ymax, mtf30, 0.3, "#fb923c")
            if mtf10 is not None:
                lines.append(f"MTF10: {mtf10:.3f} c/p")
                self._draw_frequency_marker(painter, plot, xmin, xmax, ymin, ymax, mtf10, 0.1, "#facc15")
            if lines:
                self._draw_annotation_box(painter, plot.adjusted(8, 8, -8, -8), lines, align_right=True)

        def _draw_frequency_marker(
            self,
            painter: QtGui.QPainter,
            plot: QtCore.QRect,
            xmin: float,
            xmax: float,
            ymin: float,
            ymax: float,
            x: float,
            y: float,
            color: str,
        ) -> None:
            if not (xmin <= float(x) <= xmax):
                return
            px, py = self._data_to_plot(float(x), float(y), plot, xmin, xmax, ymin, ymax)
            painter.setPen(QtGui.QPen(QtGui.QColor(color), 1, QtCore.Qt.DashLine))
            painter.drawLine(px, py, px, plot.bottom())
            painter.drawLine(plot.left(), py, px, py)
            painter.setBrush(QtGui.QColor(color))
            painter.setPen(QtGui.QPen(QtGui.QColor(color), 1))
            painter.drawEllipse(QtCore.QPointF(px, py), 4, 4)

        def _draw_annotation_box(
            self,
            painter: QtGui.QPainter,
            anchor: QtCore.QRectF | QtCore.QRect,
            lines: list[str],
            *,
            align_right: bool,
        ) -> None:
            if not lines:
                return
            metrics = painter.fontMetrics()
            width = max(metrics.horizontalAdvance(line) for line in lines) + 14
            height = metrics.height() * len(lines) + 8
            anchor_rect = QtCore.QRectF(anchor)
            x = anchor_rect.right() - width if align_right else anchor_rect.left()
            y = anchor_rect.top()
            rect = QtCore.QRectF(x, y, width, height)
            painter.setPen(QtGui.QPen(QtGui.QColor("#454545"), 1))
            painter.setBrush(QtGui.QColor(15, 23, 42, 210))
            painter.drawRoundedRect(rect, 4, 4)
            painter.setPen(QtGui.QPen(QtGui.QColor("#e6e6e6"), 1))
            for index, line in enumerate(lines):
                line_rect = QtCore.QRectF(
                    rect.left() + 7,
                    rect.top() + 4 + metrics.height() * index,
                    rect.width() - 14,
                    metrics.height(),
                )
                flags = QtCore.Qt.AlignVCenter | (QtCore.Qt.AlignRight if align_right else QtCore.Qt.AlignLeft)
                painter.drawText(line_rect, flags, line)

        def _esf_rise_10_90(self) -> tuple[float, float, float] | None:
            result = self._result
            if result is None:
                return None
            x = np.asarray(getattr(result, "esf_distance", []), dtype=np.float64)
            y = np.asarray(getattr(result, "esf", []), dtype=np.float64)
            valid = np.isfinite(x) & np.isfinite(y)
            x = x[valid]
            y = y[valid]
            if x.size < 4:
                return None
            order = np.argsort(x)
            x = x[order]
            y = y[order]
            if float(y[-1]) < float(y[0]):
                x = -x[::-1]
                y = y[::-1]
            y_mono = np.maximum.accumulate(y)
            span = float(np.nanmax(y_mono) - np.nanmin(y_mono))
            if not np.isfinite(span) or span <= 1e-6:
                return None
            y_norm = (y_mono - float(np.nanmin(y_mono))) / span
            x10 = self._level_crossing(x, y_norm, 0.10)
            x90 = self._level_crossing(x, y_norm, 0.90)
            if x10 is None or x90 is None:
                return None
            return float(x10), float(x90), abs(float(x90) - float(x10))

        def _level_crossing(self, x: np.ndarray, y: np.ndarray, level: float) -> float | None:
            if x.size < 2 or y.size < 2:
                return None
            for index in range(1, x.size):
                y0 = float(y[index - 1])
                y1 = float(y[index])
                if y0 <= level <= y1:
                    x0 = float(x[index - 1])
                    x1 = float(x[index])
                    if abs(y1 - y0) <= 1e-12:
                        return x1
                    t = (float(level) - y0) / (y1 - y0)
                    return x0 + t * (x1 - x0)
            return None

        def _draw_hover_coordinates(
            self,
            painter: QtGui.QPainter,
            plot: QtCore.QRect,
            xmin: float,
            xmax: float,
            ymin: float,
            ymax: float,
        ) -> None:
            pos = self._hover_pos
            if pos is None or not plot.contains(pos.toPoint()):
                return
            x = xmin + (float(pos.x()) - plot.left()) / max(1.0, float(plot.width())) * (xmax - xmin)
            y = ymax - (float(pos.y()) - plot.top()) / max(1.0, float(plot.height())) * (ymax - ymin)
            x = float(np.clip(x, xmin, xmax))
            y = float(np.clip(y, ymin, ymax))
            px, py = self._data_to_plot(x, y, plot, xmin, xmax, ymin, ymax)

            painter.setPen(QtGui.QPen(QtGui.QColor("#e6e6e6"), 1, QtCore.Qt.DotLine))
            painter.drawLine(px, plot.top(), px, plot.bottom())
            painter.drawLine(plot.left(), py, plot.right(), py)

            label = self._coordinate_label(x, y)
            metrics = painter.fontMetrics()
            label_w = metrics.horizontalAdvance(label) + 14
            label_h = metrics.height() + 8
            lx = min(max(plot.left() + 4, px + 8), plot.right() - label_w - 4)
            ly = max(plot.top() + 4, py - label_h - 8)
            rect = QtCore.QRectF(lx, ly, label_w, label_h)
            painter.setPen(QtGui.QPen(QtGui.QColor("#454545"), 1))
            painter.setBrush(QtGui.QColor(15, 23, 42, 230))
            painter.drawRoundedRect(rect, 4, 4)
            painter.setPen(QtGui.QPen(QtGui.QColor("#f7f7f7"), 1))
            painter.drawText(rect.adjusted(7, 0, -7, 0), QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, label)

        def _data_to_plot(
            self,
            x: float,
            y: float,
            plot: QtCore.QRect,
            xmin: float,
            xmax: float,
            ymin: float,
            ymax: float,
        ) -> tuple[float, float]:
            px = plot.left() + (float(x) - xmin) / (xmax - xmin) * plot.width()
            py = plot.bottom() - (float(y) - ymin) / (ymax - ymin) * plot.height()
            return px, py

        def _axis_ticks(self, minimum: float, maximum: float) -> list[float]:
            if self._curve == "mtf" and minimum <= 0.0 and maximum >= 0.5:
                top = min(1.0, max(0.5, float(maximum)))
                return [float(v) for v in np.arange(0.0, top + 0.0625, 0.125)]
            if self._curve in {"esf", "lsf", "ca"}:
                return self._nice_pixel_ticks(minimum, maximum, max_ticks=9)
            return [float(v) for v in np.linspace(float(minimum), float(maximum), 5)]

        def _minor_axis_ticks(self, minimum: float, maximum: float) -> list[float]:
            if self._curve == "mtf":
                step = 0.025 if maximum <= 0.55 else 0.0625
                values = np.arange(0.0, float(maximum) + step * 0.5, step)
                major_set = {round(float(v), 6) for v in self._axis_ticks(minimum, maximum)}
                return [
                    float(v)
                    for v in values
                    if float(minimum) <= float(v) <= float(maximum)
                    and round(float(v), 6) not in major_set
                ]
            if self._curve not in {"esf", "lsf", "ca"}:
                return []
            major = self._axis_ticks(minimum, maximum)
            if len(major) < 2:
                return []
            step = float(major[1] - major[0])
            if step <= 1.0:
                return []
            minor_step = max(1.0, step / 5.0)
            values = np.arange(
                np.floor(float(minimum) / minor_step) * minor_step,
                float(maximum) + minor_step * 0.5,
                minor_step,
            )
            major_set = {round(float(v), 6) for v in major}
            return [
                float(v)
                for v in values
                if float(minimum) <= float(v) <= float(maximum)
                and round(float(v), 6) not in major_set
            ]

        def _nice_pixel_ticks(self, minimum: float, maximum: float, *, max_ticks: int) -> list[float]:
            span = float(maximum) - float(minimum)
            if not np.isfinite(span) or span <= 0.0:
                return [float(minimum), float(maximum)]
            target = max(1.0, span / max(2, int(max_ticks) - 1))
            magnitude = 10.0 ** np.floor(np.log10(target))
            step = magnitude
            for factor in (1.0, 2.0, 5.0, 10.0):
                step = float(factor * magnitude)
                if span / step <= max_ticks:
                    break
            start = np.ceil(float(minimum) / step) * step
            end = np.floor(float(maximum) / step) * step
            ticks = [float(v) for v in np.arange(start, end + step * 0.5, step)]
            if not ticks:
                return [float(minimum), float(maximum)]
            return ticks

        def _format_axis_value(self, value: float) -> str:
            value = float(value)
            if abs(value) >= 100.0:
                text = f"{value:.0f}"
            elif abs(value) >= 10.0:
                text = f"{value:.1f}"
            else:
                text = f"{value:.3f}"
            return text.rstrip("0").rstrip(".") if "." in text else text

        def _coordinate_label(self, x: float, y: float) -> str:
            suffix = " post-Nyquist" if self._curve == "mtf" and float(x) > 0.5 else ""
            return f"x={self._format_axis_value(x)}  y={self._format_axis_value(y)}{suffix}"

        def _optional_float(self, value: Any) -> float | None:
            try:
                number = float(value)
            except (TypeError, ValueError):
                return None
            return number if np.isfinite(number) else None


    class MTFComparisonPlotWidget(MTFPlotWidget):
        """Overlay persisted ESF/LSF/MTF/CA curves from two or more images."""

        SERIES_COLORS = ("#38bdf8", "#f97316", "#a78bfa", "#22c55e")

        def __init__(self, curve: str = "mtf") -> None:
            super().__init__(curve)
            self._series: list[tuple[str, np.ndarray, np.ndarray]] = []
            self.setMinimumHeight(360)
            self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        def set_payloads(self, payloads: list[tuple[str, dict[str, Any]]]) -> None:
            series: list[tuple[str, np.ndarray, np.ndarray]] = []
            for label, payload in payloads:
                x_values, y_values = self._curve_from_payload(payload)
                if x_values.size >= 2 and y_values.size >= 2:
                    series.append((str(label), x_values, y_values))
            self._series = series
            self.update()

        def clear(self) -> None:
            self._series = []
            self.update()

        def paintEvent(self, _event) -> None:  # noqa: N802
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            painter.fillRect(self.rect(), QtGui.QColor("#202020"))
            plot = self.rect().adjusted(56, 22, -18, -48)
            painter.fillRect(plot, QtGui.QColor("#181818"))

            title, x_label, y_label = self._comparison_labels()
            painter.setPen(QtGui.QPen(QtGui.QColor("#d8d8d8"), 1))
            painter.drawText(self.rect().adjusted(8, 2, -8, -4), QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft, title)
            painter.drawText(self.rect().adjusted(8, 0, -8, -8), QtCore.Qt.AlignBottom | QtCore.Qt.AlignHCenter, x_label)
            painter.save()
            painter.translate(14, self.rect().center().y())
            painter.rotate(-90)
            painter.drawText(QtCore.QRectF(-72, -8, 144, 16), QtCore.Qt.AlignCenter, y_label)
            painter.restore()

            if not self._series:
                self._draw_empty_grid(painter, plot)
                painter.setPen(QtGui.QPen(QtGui.QColor("#a8a8a8"), 1))
                painter.drawText(plot, QtCore.Qt.AlignCenter, self.tr("No hay curvas MTF guardadas"))
                painter.end()
                return

            all_x = np.concatenate([values[1] for values in self._series])
            all_y = np.concatenate([values[2] for values in self._series])
            xmin, xmax = self._x_range(all_x)
            ymin, ymax = self._y_range(all_y)
            if xmax <= xmin or ymax <= ymin:
                painter.end()
                return

            self._draw_axes(painter, plot, xmin, xmax, ymin, ymax)
            if self._curve == "mtf":
                self._draw_nyquist_marker(painter, plot, xmin, xmax)
                self._draw_mtf_reference_levels(painter, plot, ymin, ymax)

            for idx, (_label, x_values, y_values) in enumerate(self._series):
                color = QtGui.QColor(self.SERIES_COLORS[idx % len(self.SERIES_COLORS)])
                if self._curve == "mtf":
                    in_band = x_values <= 0.5
                    post_band = x_values >= 0.5
                    self._draw_curve_path(
                        painter,
                        plot,
                        x_values[in_band],
                        y_values[in_band],
                        xmin,
                        xmax,
                        ymin,
                        ymax,
                        pen=QtGui.QPen(color, 2),
                    )
                    self._draw_curve_path(
                        painter,
                        plot,
                        x_values[post_band],
                        y_values[post_band],
                        xmin,
                        xmax,
                        ymin,
                        ymax,
                        pen=QtGui.QPen(color, 2, QtCore.Qt.DashLine),
                    )
                else:
                    self._draw_curve_path(
                        painter,
                        plot,
                        x_values,
                        y_values,
                        xmin,
                        xmax,
                        ymin,
                        ymax,
                        pen=QtGui.QPen(color, 2),
                    )
            self._draw_legend(painter, plot)
            self._draw_hover_coordinates(painter, plot, xmin, xmax, ymin, ymax)
            painter.end()

        def _comparison_labels(self) -> tuple[str, str, str]:
            if self._curve == "esf":
                return "ESF", self.tr("distancia al borde (px)"), self.tr("señal normalizada")
            if self._curve == "lsf":
                return "LSF", self.tr("distancia al borde (px)"), self.tr("derivada")
            if self._curve == "ca":
                return "CA lateral", self.tr("pixeles"), self.tr("diferencia RGB")
            return "MTF", self.tr("ciclos/píxel"), self.tr("modulación")

        def _curve_from_payload(self, payload: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
            curves = payload.get("curves") if isinstance(payload, dict) else None
            curves = curves if isinstance(curves, dict) else {}
            if self._curve == "esf":
                return self._extract_payload_points(curves.get("esf"), "distance_px", "signal")
            if self._curve == "lsf":
                return self._extract_payload_points(curves.get("lsf"), "distance_px", "derivative")
            if self._curve == "ca":
                return self._extract_payload_points(curves.get("chromatic_aberration"), "distance_px", "difference")
            mtf_extended = curves.get("mtf_extended")
            if isinstance(mtf_extended, list) and mtf_extended:
                return self._extract_payload_points(mtf_extended, "frequency_cycles_per_pixel", "modulation")
            return self._extract_payload_points(curves.get("mtf"), "frequency_cycles_per_pixel", "modulation")

        def _extract_payload_points(self, points: Any, x_key: str, y_key: str) -> tuple[np.ndarray, np.ndarray]:
            if not isinstance(points, list):
                return np.asarray([], dtype=np.float64), np.asarray([], dtype=np.float64)
            x_values: list[float] = []
            y_values: list[float] = []
            for point in points:
                if not isinstance(point, dict):
                    continue
                try:
                    x = float(point.get(x_key))
                    y = float(point.get(y_key))
                except (TypeError, ValueError):
                    continue
                if np.isfinite(x) and np.isfinite(y):
                    x_values.append(x)
                    y_values.append(y)
            return np.asarray(x_values, dtype=np.float64), np.asarray(y_values, dtype=np.float64)

        def _draw_legend(self, painter: QtGui.QPainter, plot: QtCore.QRect) -> None:
            metrics = painter.fontMetrics()
            row_h = metrics.height() + 6
            legend_w = min(300, max(160, int(plot.width() * 0.44)))
            legend_h = row_h * len(self._series) + 8
            rect = QtCore.QRectF(plot.right() - legend_w - 8, plot.top() + 8, legend_w, legend_h)
            painter.setPen(QtGui.QPen(QtGui.QColor("#454545"), 1))
            painter.setBrush(QtGui.QColor(15, 23, 42, 220))
            painter.drawRoundedRect(rect, 4, 4)
            for idx, (label, _x_values, _y_values) in enumerate(self._series):
                color = QtGui.QColor(self.SERIES_COLORS[idx % len(self.SERIES_COLORS)])
                y = rect.top() + 8 + idx * row_h + row_h / 2.0
                painter.setPen(QtGui.QPen(color, 3))
                painter.drawLine(rect.left() + 10, y, rect.left() + 34, y)
                painter.setPen(QtGui.QPen(QtGui.QColor("#e6e6e6"), 1))
                text_rect = QtCore.QRectF(rect.left() + 42, rect.top() + 4 + idx * row_h, rect.width() - 50, row_h)
                text = metrics.elidedText(str(label), QtCore.Qt.ElideMiddle, int(text_rect.width()))
                painter.drawText(text_rect, QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, text)


    class RGBHistogramWidget(QtWidgets.QWidget):
        def __init__(self) -> None:
            super().__init__()
            self._hist_r: np.ndarray | None = None
            self._hist_g: np.ndarray | None = None
            self._hist_b: np.ndarray | None = None
            self._clip_shadow = np.zeros(3, dtype=np.float32)
            self._clip_highlight = np.zeros(3, dtype=np.float32)
            self._clip_markers_enabled = True
            self._pending_label: str | None = None
            self.setMinimumHeight(130)
            self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)

        def sizeHint(self) -> QtCore.QSize:  # noqa: N802
            return QtCore.QSize(340, 150)

        def clear(self) -> None:
            self._hist_r = None
            self._hist_g = None
            self._hist_b = None
            self._clip_shadow = np.zeros(3, dtype=np.float32)
            self._clip_highlight = np.zeros(3, dtype=np.float32)
            self._pending_label = None
            self.setToolTip(self.tr(""))
            self.update()

        def set_pending(self, label: str | None = None) -> None:
            self._pending_label = str(label or self.tr("Actualizando..."))
            self.update()

        def set_clip_markers_enabled(self, enabled: bool) -> None:
            self._clip_markers_enabled = bool(enabled)
            self.update()

        def clip_metrics(self) -> dict[str, float]:
            return {
                "shadow_r": float(self._clip_shadow[0]),
                "shadow_g": float(self._clip_shadow[1]),
                "shadow_b": float(self._clip_shadow[2]),
                "highlight_r": float(self._clip_highlight[0]),
                "highlight_g": float(self._clip_highlight[1]),
                "highlight_b": float(self._clip_highlight[2]),
                "shadow_any": float(np.max(self._clip_shadow)),
                "highlight_any": float(np.max(self._clip_highlight)),
            }

        def set_image_u8(self, image_rgb_u8: np.ndarray | None, *, source_label: str | None = None) -> None:
            if image_rgb_u8 is None:
                self.clear()
                return
            rgb = np.asarray(image_rgb_u8)
            if rgb.ndim == 2:
                rgb = np.repeat(rgb[..., None], 3, axis=2)
            if rgb.ndim != 3 or rgb.shape[2] < 3:
                self.clear()
                return
            rgb = rgb[..., :3]
            if rgb.dtype != np.uint8:
                rgb = np.clip(np.round(rgb.astype(np.float32)), 0, 255).astype(np.uint8)
            else:
                rgb = np.ascontiguousarray(rgb)
            self._pending_label = None

            pixels = rgb.reshape((-1, 3))
            if pixels.size == 0:
                self.clear()
                return

            hist_r = np.bincount(pixels[:, 0], minlength=256).astype(np.float32)
            hist_g = np.bincount(pixels[:, 1], minlength=256).astype(np.float32)
            hist_b = np.bincount(pixels[:, 2], minlength=256).astype(np.float32)
            maxv = float(max(np.max(hist_r), np.max(hist_g), np.max(hist_b), 1.0))
            self._hist_r = hist_r / maxv
            self._hist_g = hist_g / maxv
            self._hist_b = hist_b / maxv

            self._clip_shadow = np.mean(
                pixels <= int(VIEWER_HISTOGRAM_SHADOW_CLIP_U8), axis=0
            ).astype(np.float32)
            self._clip_highlight = np.mean(
                pixels >= int(VIEWER_HISTOGRAM_HIGHLIGHT_CLIP_U8), axis=0
            ).astype(np.float32)

            metrics = self.clip_metrics()
            tooltip_parts = []
            if source_label:
                tooltip_parts.append(str(source_label))
            tooltip_parts.append(
                "Clipping sombras: "
                f"R {metrics['shadow_r'] * 100.0:.2f}%  "
                f"G {metrics['shadow_g'] * 100.0:.2f}%  "
                f"B {metrics['shadow_b'] * 100.0:.2f}%\n"
                "Clipping luces: "
                f"R {metrics['highlight_r'] * 100.0:.2f}%  "
                f"G {metrics['highlight_g'] * 100.0:.2f}%  "
                f"B {metrics['highlight_b'] * 100.0:.2f}%"
            )
            self.setToolTip("\n".join(tooltip_parts))
            self.update()

        def paintEvent(self, _event) -> None:  # noqa: N802
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            painter.fillRect(self.rect(), QtGui.QColor("#202020"))

            plot_rect = self.rect().adjusted(8, 8, -8, -24)
            if plot_rect.width() <= 4 or plot_rect.height() <= 4:
                return

            bg_grad = QtGui.QLinearGradient(plot_rect.topLeft(), plot_rect.bottomLeft())
            bg_grad.setColorAt(0.0, QtGui.QColor("#303030"))
            bg_grad.setColorAt(1.0, QtGui.QColor("#242424"))
            painter.fillRect(plot_rect, bg_grad)

            painter.setPen(QtGui.QPen(QtGui.QColor("#4a4a4a"), 1))
            for idx in range(1, 4):
                x = plot_rect.left() + (plot_rect.width() * idx / 4.0)
                painter.drawLine(QtCore.QPointF(x, plot_rect.top()), QtCore.QPointF(x, plot_rect.bottom()))
            for idx in range(1, 3):
                y = plot_rect.top() + (plot_rect.height() * idx / 3.0)
                painter.drawLine(QtCore.QPointF(plot_rect.left(), y), QtCore.QPointF(plot_rect.right(), y))

            self._draw_hist_channel(painter, plot_rect, self._hist_r, QtGui.QColor(248, 113, 113, 170), QtGui.QColor(248, 113, 113, 245))
            self._draw_hist_channel(painter, plot_rect, self._hist_g, QtGui.QColor(134, 239, 172, 150), QtGui.QColor(134, 239, 172, 245))
            self._draw_hist_channel(painter, plot_rect, self._hist_b, QtGui.QColor(96, 165, 250, 150), QtGui.QColor(96, 165, 250, 245))

            painter.setPen(QtGui.QPen(QtGui.QColor("#5c5c5c"), 1))
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawRect(plot_rect)

            metrics = self.clip_metrics()
            self._draw_clip_marker(
                painter,
                left_side=True,
                active=bool(self._pending_label is None and metrics["shadow_any"] > VIEWER_HISTOGRAM_CLIP_ALERT_RATIO),
                color=QtGui.QColor("#bdbdbd"),
            )
            self._draw_clip_marker(
                painter,
                left_side=False,
                active=bool(self._pending_label is None and metrics["highlight_any"] > VIEWER_HISTOGRAM_CLIP_ALERT_RATIO),
                color=QtGui.QColor("#f87171"),
            )

            painter.setPen(QtGui.QColor("#b3b3b3"))
            if self._pending_label:
                painter.drawText(
                    self.rect().adjusted(8, 0, -8, -4),
                    QtCore.Qt.AlignRight | QtCore.Qt.AlignBottom,
                    self._pending_label,
                )
                return
            painter.drawText(
                self.rect().adjusted(8, 0, -8, -4),
                QtCore.Qt.AlignLeft | QtCore.Qt.AlignBottom,
                f"S {metrics['shadow_any'] * 100.0:.2f}%",
            )
            painter.drawText(
                self.rect().adjusted(8, 0, -8, -4),
                QtCore.Qt.AlignRight | QtCore.Qt.AlignBottom,
                f"L {metrics['highlight_any'] * 100.0:.2f}%",
            )

        def _draw_hist_channel(
            self,
            painter: QtGui.QPainter,
            rect: QtCore.QRect,
            hist: np.ndarray | None,
            fill_color: QtGui.QColor,
            line_color: QtGui.QColor,
        ) -> None:
            if hist is None or hist.size == 0:
                return
            n = int(hist.size)
            if n <= 1:
                return
            path = QtGui.QPainterPath()
            path.moveTo(rect.left(), rect.bottom())
            for idx, value in enumerate(hist):
                x = rect.left() + rect.width() * (idx / float(n - 1))
                y = rect.bottom() - rect.height() * float(np.clip(value, 0.0, 1.0))
                path.lineTo(float(x), float(y))
            path.lineTo(rect.right(), rect.bottom())
            path.closeSubpath()
            painter.fillPath(path, fill_color)

            line_path = QtGui.QPainterPath()
            for idx, value in enumerate(hist):
                x = rect.left() + rect.width() * (idx / float(n - 1))
                y = rect.bottom() - rect.height() * float(np.clip(value, 0.0, 1.0))
                if idx == 0:
                    line_path.moveTo(float(x), float(y))
                else:
                    line_path.lineTo(float(x), float(y))
            painter.setPen(QtGui.QPen(line_color, 1.15))
            painter.drawPath(line_path)

        def _draw_clip_marker(
            self,
            painter: QtGui.QPainter,
            *,
            left_side: bool,
            active: bool,
            color: QtGui.QColor,
        ) -> None:
            size = 12
            margin = 3
            if left_side:
                x = margin
            else:
                x = max(margin, self.width() - margin - size)
            y = margin
            points = QtGui.QPolygonF(
                [
                    QtCore.QPointF(x, y + size),
                    QtCore.QPointF(x + size * 0.5, y),
                    QtCore.QPointF(x + size, y + size),
                ]
            )
            marker_on = bool(self._clip_markers_enabled and active)
            painter.setPen(QtGui.QPen(QtGui.QColor("#181818"), 1))
            painter.setBrush(QtGui.QBrush(color if marker_on else QtGui.QColor("#3a3a3a")))
            painter.drawPolygon(points)


    class Gamut3DWidget(QtWidgets.QWidget):
        DEFAULT_AZIMUTH = -38.0
        DEFAULT_ELEVATION = 24.0
        DEFAULT_ZOOM = 1.0

        def __init__(self) -> None:
            super().__init__()
            self._series: list[dict[str, Any]] = []
            self._series_signature: tuple[Any, ...] | None = None
            self._azimuth = self.DEFAULT_AZIMUTH
            self._elevation = self.DEFAULT_ELEVATION
            self._zoom = self.DEFAULT_ZOOM
            self._view_mode = "lab3d"
            self._l_slice = 50.0
            self._l_slice_half_width = 6.0
            self._drag_start: QtCore.QPoint | None = None
            self.setMinimumHeight(260)
            self.setMouseTracking(True)
            self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        def sizeHint(self) -> QtCore.QSize:  # noqa: N802
            return QtCore.QSize(420, 320)

        def clear(self) -> None:
            self._series = []
            self._series_signature = None
            self.reset_view(update=False)
            self.setToolTip("")
            self.update()

        def reset_view(self, *, update: bool = True) -> None:
            self._azimuth = self.DEFAULT_AZIMUTH
            self._elevation = self.DEFAULT_ELEVATION
            self._zoom = self.DEFAULT_ZOOM
            self._drag_start = None
            if update:
                self.update()

        def set_view_mode(self, mode: str) -> None:
            normalized = str(mode or "lab3d").strip().lower()
            if normalized not in {"lab3d", "lab_xy"}:
                normalized = "lab3d"
            if normalized == self._view_mode:
                return
            self._view_mode = normalized
            self.update()

        def set_l_slice(self, value: float) -> None:
            new_value = float(np.clip(float(value), 0.0, 100.0))
            if abs(new_value - self._l_slice) < 1e-6:
                return
            self._l_slice = new_value
            self.update()

        def set_gamut_payload(self, payload: dict[str, Any] | None) -> None:
            if not isinstance(payload, dict):
                self.clear()
                return
            self.set_series(payload.get("series") if isinstance(payload.get("series"), list) else [])
            comparisons = payload.get("comparisons") if isinstance(payload.get("comparisons"), list) else []
            skipped = payload.get("skipped") if isinstance(payload.get("skipped"), list) else []
            tooltip_lines = []
            for item in comparisons:
                if not isinstance(item, dict):
                    continue
                tooltip_lines.append(
                    f"{item.get('source', 'Perfil')} en {item.get('target', '')}: "
                    f"{float(item.get('inside_ratio') or 0.0) * 100.0:.1f}% dentro"
                )
                outside = int(item.get("outside_samples") or 0)
                if outside:
                    tooltip_lines.append(
                        f"Fuera de gama {item.get('source', 'Perfil')} -> {item.get('target', '')}: {outside}"
                    )
            for item in skipped:
                if isinstance(item, dict):
                    tooltip_lines.append(f"Omitido {item.get('label', '')}: {item.get('reason', '')}")
            self.setToolTip("\n".join(line for line in tooltip_lines if line.strip()))

        def set_series(self, series: list[Any]) -> None:
            normalized: list[dict[str, Any]] = []
            for item in series:
                if not isinstance(item, dict):
                    continue
                points = np.asarray(item.get("points_lab"), dtype=np.float64)
                if points.ndim != 2 or points.shape[1] < 3:
                    continue
                points = points[:, :3]
                points = points[np.all(np.isfinite(points), axis=1)]
                if points.size == 0:
                    continue
                out_of_gamut = self._coerce_lab_points(item.get("out_of_gamut_lab"))
                normalized.append(
                    {
                        "label": str(item.get("label") or "Perfil"),
                        "color": str(item.get("color") or "#a8a8a8"),
                        "points": np.ascontiguousarray(points, dtype=np.float64),
                        "rgb": self._coerce_rgb_points(item.get("surface_rgb"), points.shape[0]),
                        "quads": self._coerce_quads(item.get("quads"), points.shape[0]),
                        "role": str(item.get("role") or "wire"),
                        "source_key": str(item.get("path") or item.get("profile_key") or item.get("label") or ""),
                        "out_of_gamut": out_of_gamut,
                        "out_of_gamut_rgb": self._coerce_rgb_points(
                            item.get("out_of_gamut_rgb"),
                            out_of_gamut.shape[0],
                        ),
                        "out_of_gamut_target": str(item.get("out_of_gamut_target") or ""),
                        "out_of_gamut_color": str(item.get("out_of_gamut_color") or "#f43f5e"),
                    }
                )
            signature = self._series_payload_signature(normalized)
            if signature != self._series_signature:
                self.reset_view(update=False)
                self._series_signature = signature
            self._series = normalized
            self.update()
            QtCore.QTimer.singleShot(0, self.update)

        def _series_payload_signature(self, series: list[dict[str, Any]]) -> tuple[Any, ...]:
            signature: list[tuple[Any, ...]] = []
            for item in series:
                points = np.asarray(item.get("points"), dtype=np.float64)
                if points.ndim != 2 or points.shape[1] < 3 or points.size == 0:
                    stats = (0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
                else:
                    finite = points[:, :3][np.all(np.isfinite(points[:, :3]), axis=1)]
                    if finite.size:
                        minv = np.min(finite, axis=0)
                        maxv = np.max(finite, axis=0)
                        stats = (
                            int(finite.shape[0]),
                            *[float(round(v, 3)) for v in minv],
                            *[float(round(v, 3)) for v in maxv],
                        )
                    else:
                        stats = (0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
                signature.append(
                    (
                        str(item.get("label") or ""),
                        str(item.get("source_key") or ""),
                        str(item.get("role") or ""),
                        str(item.get("color") or ""),
                        stats,
                    )
                )
            return tuple(signature)

        def _coerce_rgb_points(self, value: Any, count: int) -> np.ndarray:
            rgb = np.asarray(value, dtype=np.float64)
            if rgb.ndim != 2 or rgb.shape[1] < 3 or rgb.shape[0] != count:
                return np.zeros((count, 3), dtype=np.float64)
            return np.ascontiguousarray(np.clip(rgb[:, :3], 0.0, 1.0), dtype=np.float64)

        def _coerce_quads(self, value: Any, count: int) -> list[list[int]]:
            quads: list[list[int]] = []
            if not isinstance(value, list):
                return quads
            for item in value:
                if not isinstance(item, (list, tuple)) or len(item) < 4:
                    continue
                try:
                    quad = [int(item[idx]) for idx in range(4)]
                except (TypeError, ValueError):
                    continue
                if all(0 <= idx < count for idx in quad):
                    quads.append(quad)
            return quads

        def _coerce_lab_points(self, value: Any) -> np.ndarray:
            points = np.asarray(value, dtype=np.float64)
            if points.ndim != 2 or points.shape[1] < 3:
                return np.zeros((0, 3), dtype=np.float64)
            points = points[:, :3]
            points = points[np.all(np.isfinite(points), axis=1)]
            return np.ascontiguousarray(points, dtype=np.float64)

        def mousePressEvent(self, event) -> None:  # noqa: N802
            if event.button() == QtCore.Qt.LeftButton:
                self._drag_start = event.position().toPoint() if hasattr(event, "position") else event.pos()
                event.accept()
                return
            super().mousePressEvent(event)

        def mouseMoveEvent(self, event) -> None:  # noqa: N802
            if self._drag_start is None:
                return super().mouseMoveEvent(event)
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            delta = pos - self._drag_start
            self._drag_start = pos
            self._azimuth += float(delta.x()) * 0.45
            self._elevation = float(np.clip(self._elevation + float(delta.y()) * 0.35, -78.0, 78.0))
            self.update()
            event.accept()

        def mouseReleaseEvent(self, event) -> None:  # noqa: N802
            if event.button() == QtCore.Qt.LeftButton:
                self._drag_start = None
                event.accept()
                return
            super().mouseReleaseEvent(event)

        def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
            if event.button() == QtCore.Qt.LeftButton:
                self.reset_view()
                event.accept()
                return
            super().mouseDoubleClickEvent(event)

        def wheelEvent(self, event) -> None:  # noqa: N802
            delta = event.angleDelta().y()
            if delta:
                factor = 1.12 if delta > 0 else 1.0 / 1.12
                self._zoom = float(np.clip(self._zoom * factor, 0.55, 3.0))
                self.update()
                event.accept()
                return
            super().wheelEvent(event)

        def paintEvent(self, _event) -> None:  # noqa: N802
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            painter.fillRect(self.rect(), QtGui.QColor("#202020"))

            if self._view_mode == "lab_xy":
                self._paint_lab_xy(painter)
                return

            plot_rect = self.rect().adjusted(8, 8, -8, -30)
            if plot_rect.width() <= 40 or plot_rect.height() <= 40:
                return

            painter.setPen(QtGui.QPen(QtGui.QColor("#454545"), 1))
            painter.drawRect(plot_rect)

            if not self._series:
                self._draw_axes(painter, plot_rect, np.asarray([50.0, 0.0, 0.0], dtype=np.float64), 1.0)
                painter.setPen(QtGui.QColor("#a6a6a6"))
                painter.drawText(plot_rect, QtCore.Qt.AlignCenter, self.tr("Sin datos de gama 3D"))
                return

            all_points = np.vstack([item["points"] for item in self._series])
            center = self._lab_center(all_points)
            scale = self._projection_scale(all_points, center, plot_rect)
            self._draw_axes(painter, plot_rect, center, scale)

            solid_quads: list[tuple[float, QtGui.QPolygonF, QtGui.QColor]] = []
            wire_quads: list[tuple[float, QtGui.QPolygonF, QtGui.QColor]] = []
            fallback_points: list[tuple[float, QtCore.QPointF, QtGui.QColor]] = []
            for item in self._series:
                base_color = QtGui.QColor(str(item["color"]))
                projected, depth = self._project_points(item["points"], center, scale, plot_rect)
                quads = item.get("quads") or []
                if not quads:
                    base_color.setAlpha(210 if item.get("role") == "solid" else 170)
                    for point, z in zip(projected, depth, strict=True):
                        fallback_points.append((float(z), point, QtGui.QColor(base_color)))
                    continue
                for quad in quads:
                    polygon = QtGui.QPolygonF([projected[idx] for idx in quad])
                    z = float(np.mean([depth[idx] for idx in quad]))
                    if item.get("role") == "solid":
                        color = self._solid_quad_color(item, quad, fallback=base_color)
                        solid_quads.append((z, polygon, color))
                    else:
                        color = QtGui.QColor(base_color)
                        color.setAlpha(210)
                        wire_quads.append((z, polygon, color))

            painter.setPen(QtCore.Qt.NoPen)
            for _depth, polygon, color in sorted(solid_quads, key=lambda entry: entry[0]):
                painter.setBrush(QtGui.QBrush(color))
                painter.drawPolygon(polygon)
            painter.setBrush(QtCore.Qt.NoBrush)
            for _depth, polygon, color in sorted(solid_quads, key=lambda entry: entry[0]):
                edge = QtGui.QColor("#202020")
                edge.setAlpha(46)
                painter.setPen(QtGui.QPen(edge, 0.45))
                painter.drawPolygon(polygon)
            for _depth, polygon, color in sorted(wire_quads, key=lambda entry: entry[0]):
                painter.setPen(QtGui.QPen(color, 0.75))
                painter.drawPolygon(polygon)
            painter.setPen(QtCore.Qt.NoPen)
            for _depth, point, color in sorted(fallback_points, key=lambda entry: entry[0]):
                painter.setBrush(QtGui.QBrush(color))
                painter.drawEllipse(point, 2.0, 2.0)

            self._draw_legend(painter, plot_rect)
            painter.setPen(QtGui.QColor("#a6a6a6"))
            painter.drawText(
                self.rect().adjusted(8, 0, -8, -6),
                QtCore.Qt.AlignLeft | QtCore.Qt.AlignBottom,
                f"Lab 3D | az {self._azimuth:.0f} / el {self._elevation:.0f}",
            )

        def _paint_lab_xy(self, painter: QtGui.QPainter) -> None:
            plot_rect = self.rect().adjusted(8, 8, -42, -30)
            if plot_rect.width() <= 40 or plot_rect.height() <= 40:
                return

            painter.setPen(QtGui.QPen(QtGui.QColor("#454545"), 1))
            painter.drawRect(plot_rect)

            if not self._series:
                self._draw_lab_xy_grid(painter, plot_rect, 120.0)
                painter.setPen(QtGui.QColor("#a6a6a6"))
                painter.drawText(plot_rect, QtCore.Qt.AlignCenter, self.tr("Sin datos de gama Lab 2D"))
                return

            all_points = np.vstack([item["points"] for item in self._series])
            all_ab = all_points[:, 1:3]
            outside_sets = [
                item.get("out_of_gamut")
                for item in self._series
                if isinstance(item.get("out_of_gamut"), np.ndarray) and item.get("out_of_gamut").size
            ]
            if outside_sets:
                all_ab = np.vstack([all_ab, *[points[:, 1:3] for points in outside_sets]])
            max_abs = float(np.max(np.abs(all_ab))) if all_ab.size else 120.0
            limit = float(np.clip(np.ceil(max(max_abs, 120.0) / 20.0) * 20.0, 120.0, 260.0))
            self._draw_lab_xy_grid(painter, plot_rect, limit)

            for item in self._series:
                points = np.asarray(item["points"], dtype=np.float64)
                mask = self._lab_xy_slice_mask(points)
                slice_points = points[mask]
                if slice_points.size == 0:
                    continue
                base_color = QtGui.QColor(str(item["color"]))
                hull = self._convex_hull_2d(slice_points[:, 1:3])
                if len(hull) >= 3:
                    polygon = QtGui.QPolygonF([
                        self._lab_xy_to_screen(float(a), float(b), plot_rect, limit)
                        for a, b in hull
                    ])
                    if item.get("role") == "solid":
                        fill = QtGui.QColor(base_color)
                        fill.setAlpha(42)
                        painter.setBrush(QtGui.QBrush(fill))
                    else:
                        painter.setBrush(QtCore.Qt.NoBrush)
                    line = QtGui.QColor(base_color)
                    line.setAlpha(220)
                    painter.setPen(QtGui.QPen(line, 1.15 if item.get("role") == "solid" else 1.35))
                    painter.drawPolygon(polygon)

                rgb = item.get("rgb")
                rgb_slice = rgb[mask] if isinstance(rgb, np.ndarray) and rgb.shape[0] == points.shape[0] else None
                for idx, point in enumerate(slice_points):
                    marker = self._lab_xy_to_screen(float(point[1]), float(point[2]), plot_rect, limit)
                    if isinstance(rgb_slice, np.ndarray) and rgb_slice.shape[0] > idx:
                        color = QtGui.QColor(
                            int(round(float(rgb_slice[idx, 0]) * 255.0)),
                            int(round(float(rgb_slice[idx, 1]) * 255.0)),
                            int(round(float(rgb_slice[idx, 2]) * 255.0)),
                            150,
                        )
                    else:
                        color = QtGui.QColor(base_color)
                        color.setAlpha(145)
                    painter.setPen(QtCore.Qt.NoPen)
                    painter.setBrush(QtGui.QBrush(color))
                    painter.drawEllipse(marker, 2.1, 2.1)

            outside_summary: list[str] = []
            for item in self._series:
                outside = item.get("out_of_gamut")
                if not isinstance(outside, np.ndarray) or outside.size == 0:
                    continue
                mask = self._lab_xy_slice_mask(outside)
                outside_slice = outside[mask]
                if outside_slice.size == 0:
                    continue
                outside_summary.append(
                    f"{item['label']} -> {item.get('out_of_gamut_target') or '?'}: {outside_slice.shape[0]}"
                )
                rgb = item.get("out_of_gamut_rgb")
                rgb_slice = rgb[mask] if isinstance(rgb, np.ndarray) and rgb.shape[0] == outside.shape[0] else None
                marker_color = QtGui.QColor(str(item.get("out_of_gamut_color") or "#f43f5e"))
                for idx, point in enumerate(outside_slice):
                    marker = self._lab_xy_to_screen(float(point[1]), float(point[2]), plot_rect, limit)
                    if isinstance(rgb_slice, np.ndarray) and rgb_slice.shape[0] > idx:
                        fill = QtGui.QColor(
                            int(round(float(rgb_slice[idx, 0]) * 255.0)),
                            int(round(float(rgb_slice[idx, 1]) * 255.0)),
                            int(round(float(rgb_slice[idx, 2]) * 255.0)),
                            210,
                        )
                    else:
                        fill = QtGui.QColor(marker_color)
                        fill.setAlpha(170)
                    outline = QtGui.QColor(marker_color)
                    outline.setAlpha(245)
                    painter.setBrush(QtGui.QBrush(fill))
                    painter.setPen(QtGui.QPen(outline, 1.4))
                    painter.drawEllipse(marker, 4.2, 4.2)

            self._draw_legend(painter, plot_rect)
            painter.setPen(QtGui.QColor("#a6a6a6"))
            footer = f"Lab 2D | L* {self._l_slice:.0f} +/- {self._l_slice_half_width:.0f}"
            if outside_summary:
                footer += " | fuera: " + ", ".join(outside_summary[:2])
            painter.drawText(
                self.rect().adjusted(8, 0, -8, -6),
                QtCore.Qt.AlignLeft | QtCore.Qt.AlignBottom,
                footer,
            )

        def _draw_lab_xy_grid(self, painter: QtGui.QPainter, rect: QtCore.QRect, limit: float) -> None:
            center = rect.center()
            scale = min(rect.width(), rect.height()) * 0.46 / max(float(limit), 1.0)
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.setPen(QtGui.QPen(QtGui.QColor("#3a3a3a"), 1))
            ring = 40
            while ring <= limit:
                radius = float(ring) * scale
                painter.drawEllipse(QtCore.QPointF(center), radius, radius)
                ring += 40
            painter.setPen(QtGui.QPen(QtGui.QColor("#5c5c5c"), 1))
            painter.drawLine(
                self._lab_xy_to_screen(-limit, 0.0, rect, limit),
                self._lab_xy_to_screen(limit, 0.0, rect, limit),
            )
            painter.drawLine(
                self._lab_xy_to_screen(0.0, -limit, rect, limit),
                self._lab_xy_to_screen(0.0, limit, rect, limit),
            )
            painter.setPen(QtGui.QColor("#d8d8d8"))
            painter.drawText(self._lab_xy_to_screen(limit, 0.0, rect, limit) + QtCore.QPointF(-18, -6), "a*")
            painter.drawText(self._lab_xy_to_screen(0.0, limit, rect, limit) + QtCore.QPointF(4, 12), "b*")

        def _lab_xy_to_screen(
            self,
            a_value: float,
            b_value: float,
            rect: QtCore.QRect,
            limit: float,
        ) -> QtCore.QPointF:
            scale = min(rect.width(), rect.height()) * 0.46 / max(float(limit), 1.0)
            return QtCore.QPointF(
                rect.center().x() + float(a_value) * scale,
                rect.center().y() - float(b_value) * scale,
            )

        def _lab_xy_slice_mask(self, points: np.ndarray) -> np.ndarray:
            lab = np.asarray(points, dtype=np.float64)
            if lab.ndim != 2 or lab.shape[1] < 3:
                return np.zeros(0, dtype=bool)
            mask = np.abs(lab[:, 0] - float(self._l_slice)) <= float(self._l_slice_half_width)
            if np.count_nonzero(mask) > 0:
                return mask
            if lab.shape[0] == 0:
                return mask
            nearest_count = max(1, min(12, int(np.ceil(lab.shape[0] * 0.04))))
            nearest = np.argsort(np.abs(lab[:, 0] - float(self._l_slice)))[:nearest_count]
            mask = np.zeros(lab.shape[0], dtype=bool)
            mask[nearest] = True
            return mask

        def _convex_hull_2d(self, points: np.ndarray) -> list[tuple[float, float]]:
            pts = sorted({(float(row[0]), float(row[1])) for row in np.asarray(points, dtype=np.float64)})
            if len(pts) <= 2:
                return pts

            def cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
                return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

            lower: list[tuple[float, float]] = []
            for point in pts:
                while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0.0:
                    lower.pop()
                lower.append(point)
            upper: list[tuple[float, float]] = []
            for point in reversed(pts):
                while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0.0:
                    upper.pop()
                upper.append(point)
            return lower[:-1] + upper[:-1]

        def _draw_axes(
            self,
            painter: QtGui.QPainter,
            rect: QtCore.QRect,
            center: np.ndarray,
            scale: float,
        ) -> None:
            axis_points = np.asarray(
                [
                    [0.0, 0.0, 0.0],
                    [100.0, 0.0, 0.0],
                    [50.0, -120.0, 0.0],
                    [50.0, 120.0, 0.0],
                    [50.0, 0.0, -120.0],
                    [50.0, 0.0, 120.0],
                ],
                dtype=np.float64,
            )
            projected, _depth = self._project_points(axis_points, center, scale, rect)
            painter.setPen(QtGui.QPen(QtGui.QColor("#5c5c5c"), 1))
            painter.drawLine(projected[0], projected[1])
            painter.drawLine(projected[2], projected[3])
            painter.drawLine(projected[4], projected[5])
            painter.setPen(QtGui.QColor("#d8d8d8"))
            painter.drawText(projected[1] + QtCore.QPointF(4, -4), "L*")
            painter.drawText(projected[3] + QtCore.QPointF(4, 0), "a*")
            painter.drawText(projected[5] + QtCore.QPointF(4, 0), "b*")

        def _draw_legend(self, painter: QtGui.QPainter, rect: QtCore.QRect) -> None:
            x = rect.left() + 10
            y = rect.top() + 10
            painter.setFont(QtGui.QFont(painter.font().family(), 8))
            for item in self._series:
                color = QtGui.QColor(str(item["color"]))
                color.setAlpha(230)
                painter.setPen(QtCore.Qt.NoPen)
                if item.get("role") == "solid":
                    painter.setBrush(QtGui.QBrush(color))
                    painter.drawRect(QtCore.QRectF(x + 1, y + 2, 9, 9))
                else:
                    painter.setBrush(QtCore.Qt.NoBrush)
                    painter.setPen(QtGui.QPen(color, 1.2))
                    painter.drawRect(QtCore.QRectF(x + 1, y + 2, 9, 9))
                painter.setPen(QtGui.QColor("#d8d8d8"))
                painter.drawText(QtCore.QPointF(x + 16, y + 10), f"{item['label']} ({len(item['points'])})")
                y += 16

        def _solid_quad_color(self, item: dict[str, Any], quad: list[int], *, fallback: QtGui.QColor) -> QtGui.QColor:
            rgb = item.get("rgb")
            if isinstance(rgb, np.ndarray) and rgb.ndim == 2 and rgb.shape[0] > max(quad):
                mean_rgb = np.clip(np.mean(rgb[quad, :3], axis=0), 0.0, 1.0)
                color = QtGui.QColor(
                    int(round(float(mean_rgb[0]) * 255.0)),
                    int(round(float(mean_rgb[1]) * 255.0)),
                    int(round(float(mean_rgb[2]) * 255.0)),
                    168,
                )
                return color
            color = QtGui.QColor(fallback)
            color.setAlpha(150)
            return color

        def _project_points(
            self,
            points: np.ndarray,
            center: np.ndarray,
            scale: float,
            rect: QtCore.QRect,
            *,
            apply_zoom: bool = True,
        ) -> tuple[list[QtCore.QPointF], np.ndarray]:
            centered = np.asarray(points, dtype=np.float64) - center.reshape((1, 3))
            a = centered[:, 1]
            b = centered[:, 2]
            l = centered[:, 0]
            az = np.deg2rad(float(self._azimuth))
            el = np.deg2rad(float(self._elevation))
            x_rot = a * np.cos(az) - b * np.sin(az)
            depth = a * np.sin(az) + b * np.cos(az)
            y_rot = l * np.cos(el) - depth * np.sin(el)
            depth = depth * np.cos(el) + l * np.sin(el)
            cx = rect.center().x()
            cy = rect.center().y()
            effective_scale = float(scale) * (float(self._zoom) if apply_zoom else 1.0)
            projected = [
                QtCore.QPointF(cx + float(x) * effective_scale, cy - float(y) * effective_scale)
                for x, y in zip(x_rot, y_rot, strict=True)
            ]
            return projected, depth

        def _lab_center(self, points: np.ndarray) -> np.ndarray:
            if points.size == 0:
                return np.asarray([50.0, 0.0, 0.0], dtype=np.float64)
            return np.asarray(
                [
                    50.0,
                    float(np.median(points[:, 1])),
                    float(np.median(points[:, 2])),
                ],
                dtype=np.float64,
            )

        def _projection_scale(self, points: np.ndarray, center: np.ndarray, rect: QtCore.QRect) -> float:
            if points.size == 0:
                return 1.0
            projected, _depth = self._project_points(points, center, 1.0, rect, apply_zoom=False)
            xs = np.asarray([point.x() - rect.center().x() for point in projected], dtype=np.float64)
            ys = np.asarray([point.y() - rect.center().y() for point in projected], dtype=np.float64)
            span = max(float(np.max(np.abs(xs))), float(np.max(np.abs(ys))), 1.0)
            available = max(20.0, min(rect.width(), rect.height()) * 0.44)
            return available / span


    class ColorSampleGamutWidget(QtWidgets.QWidget):
        def __init__(self) -> None:
            super().__init__()
            self._groups: list[dict[str, Any]] = []
            self.setMinimumHeight(170)
            self.setMaximumHeight(240)

        def groups(self) -> list[dict[str, Any]]:
            return [
                {
                    "name": str(group.get("name") or ""),
                    "color": str(group.get("color") or "#22d3ee"),
                    "points_lab": np.asarray(group.get("points"), dtype=np.float64).copy(),
                }
                for group in self._groups
            ]

        def set_groups(self, groups: list[dict[str, Any]] | None) -> None:
            normalized: list[dict[str, Any]] = []
            for index, group in enumerate(groups or []):
                if not isinstance(group, dict):
                    continue
                points = np.asarray(group.get("points_lab"), dtype=np.float64)
                if points.ndim != 2 or points.shape[1] < 3:
                    points = np.zeros((0, 3), dtype=np.float64)
                else:
                    points = points[:, :3]
                    points = points[np.all(np.isfinite(points), axis=1)]
                normalized.append(
                    {
                        "name": str(group.get("name") or f"Conjunto {index + 1}"),
                        "color": str(group.get("color") or "#22d3ee"),
                        "points": np.ascontiguousarray(points, dtype=np.float64),
                    }
                )
            self._groups = normalized
            self.update()

        def paintEvent(self, _event) -> None:  # noqa: N802
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            painter.fillRect(self.rect(), QtGui.QColor("#202020"))
            plot = self.rect().adjusted(8, 8, -116, -24)
            if plot.width() <= 50 or plot.height() <= 50:
                return
            valid = [group for group in self._groups if group["points"].size]
            if not valid:
                self._draw_grid(painter, plot, 120.0)
                painter.setPen(QtGui.QColor("#a6a6a6"))
                painter.drawText(plot, QtCore.Qt.AlignCenter, self.tr("Sin conjuntos de muestras"))
                return

            all_ab = np.vstack([group["points"][:, 1:3] for group in valid])
            max_abs = float(np.max(np.abs(all_ab))) if all_ab.size else 120.0
            limit = float(np.clip(np.ceil(max(max_abs, 80.0) / 20.0) * 20.0, 80.0, 220.0))
            self._draw_grid(painter, plot, limit)

            legend_y = plot.top() + 2
            legend_x = plot.right() + 12
            for group in valid:
                points = np.asarray(group["points"], dtype=np.float64)
                color = QtGui.QColor(str(group["color"]))
                if not color.isValid():
                    color = QtGui.QColor("#22d3ee")
                hull = self._convex_hull_2d(points[:, 1:3])
                if len(hull) >= 3:
                    polygon = QtGui.QPolygonF([self._ab_to_screen(a, b, plot, limit) for a, b in hull])
                    fill = QtGui.QColor(color)
                    fill.setAlpha(44)
                    line = QtGui.QColor(color)
                    line.setAlpha(230)
                    painter.setBrush(fill)
                    painter.setPen(QtGui.QPen(line, 1.6))
                    painter.drawPolygon(polygon)
                painter.setPen(QtCore.Qt.NoPen)
                marker = QtGui.QColor(color)
                marker.setAlpha(215)
                painter.setBrush(marker)
                for lab in points:
                    center = self._ab_to_screen(float(lab[1]), float(lab[2]), plot, limit)
                    painter.drawEllipse(center, 3.2, 3.2)

                painter.setPen(QtCore.Qt.NoPen)
                painter.setBrush(color)
                painter.drawRect(QtCore.QRectF(legend_x, legend_y + 4, 9, 9))
                painter.setPen(QtGui.QColor("#d8d8d8"))
                l_min = float(np.min(points[:, 0]))
                l_max = float(np.max(points[:, 0]))
                text = f"{group['name']} ({points.shape[0]}) L* {l_min:.0f}-{l_max:.0f}"
                painter.drawText(QtCore.QRectF(legend_x + 14, legend_y, 94, 20), QtCore.Qt.AlignLeft, text)
                legend_y += 22

            painter.setPen(QtGui.QColor("#a6a6a6"))
            painter.drawText(
                self.rect().adjusted(8, 0, -8, -4),
                QtCore.Qt.AlignLeft | QtCore.Qt.AlignBottom,
                self.tr("Comparacion de conjuntos en Lab a*b*"),
            )

        def _draw_grid(self, painter: QtGui.QPainter, rect: QtCore.QRect, limit: float) -> None:
            painter.setPen(QtGui.QPen(QtGui.QColor("#3a3a3a"), 1))
            painter.setBrush(QtCore.Qt.NoBrush)
            center = rect.center()
            scale = min(rect.width(), rect.height()) * 0.46 / max(limit, 1.0)
            ring = 40
            while ring <= limit:
                radius = float(ring) * scale
                painter.drawEllipse(QtCore.QPointF(center), radius, radius)
                ring += 40
            painter.setPen(QtGui.QPen(QtGui.QColor("#5c5c5c"), 1))
            painter.drawLine(self._ab_to_screen(-limit, 0, rect, limit), self._ab_to_screen(limit, 0, rect, limit))
            painter.drawLine(self._ab_to_screen(0, -limit, rect, limit), self._ab_to_screen(0, limit, rect, limit))
            painter.setPen(QtGui.QColor("#d8d8d8"))
            painter.drawText(self._ab_to_screen(limit, 0, rect, limit) + QtCore.QPointF(-18, -6), "a*")
            painter.drawText(self._ab_to_screen(0, limit, rect, limit) + QtCore.QPointF(4, 12), "b*")

        def _ab_to_screen(
            self,
            a_value: float,
            b_value: float,
            rect: QtCore.QRect,
            limit: float,
        ) -> QtCore.QPointF:
            scale = min(rect.width(), rect.height()) * 0.46 / max(float(limit), 1.0)
            return QtCore.QPointF(
                rect.center().x() + float(a_value) * scale,
                rect.center().y() - float(b_value) * scale,
            )

        def _convex_hull_2d(self, points: np.ndarray) -> list[tuple[float, float]]:
            pts = sorted({(float(row[0]), float(row[1])) for row in np.asarray(points, dtype=np.float64)})
            if len(pts) <= 2:
                return pts

            def cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
                return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

            lower: list[tuple[float, float]] = []
            for point in pts:
                while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0.0:
                    lower.pop()
                lower.append(point)
            upper: list[tuple[float, float]] = []
            for point in reversed(pts):
                while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0.0:
                    upper.pop()
                upper.append(point)
            return lower[:-1] + upper[:-1]


    class ImagePanel(QtWidgets.QLabel):
        imageClicked = QtCore.Signal(float, float)
        roiSelected = QtCore.Signal(float, float, float, float)
        lineSelected = QtCore.Signal(float, float, float, float)
        sampleRegionMoved = QtCore.Signal(str, object)
        viewTransformChanged = QtCore.Signal(float, float)
        PIXEL_EXACT_MIN_SCALE = 1.0
        PIXEL_GRID_MIN_SCALE = 8.0

        def __init__(
            self,
            title: str,
            *,
            framed: bool = True,
            background: str = IMAGE_PANEL_BACKGROUND,
        ) -> None:
            super().__init__()
            self._base_pixmap: QtGui.QImage | QtGui.QPixmap | None = None
            self._base_color_space = "device"
            self._image_size: tuple[int, int] | None = None
            self._overlay_points: list[tuple[float, float]] = []
            self._editable_sample_regions: list[dict[str, Any]] = []
            self._editable_sample_regions_enabled = False
            self._sample_region_drag_id: str | None = None
            self._sample_region_drag_start_image: tuple[float, float] | None = None
            self._sample_region_drag_start_points: list[tuple[float, float]] = []
            self._sample_region_hover_id: str | None = None
            self._sample_markers: list[dict[str, Any]] = []
            self._sample_magnifier_enabled = False
            self._sample_magnifier_radius = 2
            self._sample_magnifier_image_pos: tuple[float, float] | None = None
            self._view_zoom = 1.0
            self._view_rotation = 0
            self._view_crop_rect: tuple[int, int, int, int] | None = None
            self._display_pixmap_cache_key: tuple[object, ...] | None = None
            self._display_pixmap_cache: QtGui.QImage | QtGui.QPixmap | None = None
            self._display_clip_cache_key: tuple[object, ...] | None = None
            self._display_clip_cache: QtGui.QImage | QtGui.QPixmap | None = None
            self._framed = bool(framed)
            self._background = str(background or IMAGE_PANEL_BACKGROUND)
            self._clip_overlay_pixmap: QtGui.QImage | QtGui.QPixmap | None = None
            self._clip_overlay_enabled = False
            self._roi_rect: tuple[float, float, float, float] | None = None
            self._roi_label = "MTF"
            self._roi_selection_enabled = False
            self._roi_drag_start_image: tuple[float, float] | None = None
            self._roi_drag_current_image: tuple[float, float] | None = None
            self._line_selection_enabled = False
            self._line_reference_axis = "horizontal"
            self._line_drag_start_image: tuple[float, float] | None = None
            self._line_drag_current_image: tuple[float, float] | None = None
            self._pan = QtCore.QPointF(0.0, 0.0)
            self._drag_start: QtCore.QPointF | None = None
            self._drag_last: QtCore.QPointF | None = None
            self._drag_moved = False
            self._interaction_cursor: QtCore.Qt.CursorShape | None = None
            self._space_pan_active = False
            self.setAlignment(QtCore.Qt.AlignCenter)
            self.setMinimumSize(220, 160)
            self.setMouseTracking(True)
            self.setText(title)
            border_style = f"1px solid {IMAGE_PANEL_BORDER}" if self._framed else "1px solid transparent"
            self.setStyleSheet(
                "QLabel {"
                f"border: {border_style};"
                f"background-color: {self._background};"
                f"color: {IMAGE_PANEL_TEXT};"
                "font-size: 13px;"
                "}"
            )

        def set_rgb_float_image(self, image_rgb: np.ndarray, *, color_space: str = "device") -> None:
            rgb = np.clip(image_rgb, 0.0, 1.0)
            u8 = np.clip(np.round(rgb * 255.0), 0, 255).astype(np.uint8)
            self.set_rgb_u8_image(u8, color_space=color_space)

        def set_rgb_u8_image(self, image_rgb_u8: np.ndarray, *, color_space: str = "device") -> None:
            u8 = np.ascontiguousarray(image_rgb_u8.astype(np.uint8))
            if u8.ndim == 2:
                u8 = np.repeat(u8[..., None], 3, axis=2)
            if u8.ndim != 3 or u8.shape[2] < 3:
                raise RuntimeError(f"Imagen RGB inesperada para visor: shape={u8.shape}")
            u8 = np.ascontiguousarray(u8[..., :3])
            h, w, _ = u8.shape
            self._image_size = (w, h)
            qimg = QtGui.QImage(u8.data, w, h, 3 * w, QtGui.QImage.Format_RGB888).copy()
            self._base_color_space = self._normalized_color_space(color_space)
            self._tag_qimage_color_space(qimg, self._base_color_space)
            self._base_pixmap = qimg
            self._clip_overlay_pixmap = None
            self._clear_display_cache()
            self._refresh_scaled_pixmap()

        def update_rgb_u8_region(
            self,
            x: int,
            y: int,
            image_rgb_u8: np.ndarray,
            *,
            color_space: str | None = None,
        ) -> None:
            if self._base_pixmap is None or self._image_size is None:
                self.set_rgb_u8_image(image_rgb_u8, color_space=color_space or "device")
                return
            if not isinstance(self._base_pixmap, QtGui.QImage):
                self.set_rgb_u8_image(image_rgb_u8, color_space=color_space or "device")
                return
            u8 = np.ascontiguousarray(np.asarray(image_rgb_u8, dtype=np.uint8))
            if u8.ndim == 2:
                u8 = np.repeat(u8[..., None], 3, axis=2)
            if u8.ndim != 3 or u8.shape[2] < 3:
                raise RuntimeError(f"Region RGB inesperada para visor: shape={u8.shape}")
            u8 = np.ascontiguousarray(u8[..., :3])
            image_w, image_h = self._image_size
            x0 = int(np.clip(int(x), 0, image_w))
            y0 = int(np.clip(int(y), 0, image_h))
            if x0 >= image_w or y0 >= image_h:
                return
            h, w, _ = u8.shape
            w = min(int(w), image_w - x0)
            h = min(int(h), image_h - y0)
            if w <= 0 or h <= 0:
                return
            qimg = QtGui.QImage(u8[:h, :w].data, w, h, 3 * w, QtGui.QImage.Format_RGB888).copy()
            patch_color_space = self._normalized_color_space(color_space or self._base_color_space)
            self._tag_qimage_color_space(qimg, patch_color_space)
            painter = QtGui.QPainter(self._base_pixmap)
            painter.drawImage(QtCore.QPoint(int(x0), int(y0)), qimg)
            painter.end()
            self._clear_display_cache()
            self.update()

        @staticmethod
        def _normalized_color_space(color_space: str | None) -> str:
            value = str(color_space or "device").strip().lower()
            return "srgb" if value == "srgb" else "device"

        def _tag_qimage_color_space(self, qimg: QtGui.QImage, color_space: str) -> None:
            if color_space != "srgb":
                # Device RGB means ProbRAW already converted the pixels to the
                # monitor profile with LittleCMS. Keep the QImage untagged so
                # Qt/compositor does not run an additional color transform.
                return
            try:
                # Pixels are still sRGB when no monitor ICC conversion was
                # applied, so tagging allows a color-managed compositor to do
                # the final sRGB -> monitor transform.
                try:
                    srgb_cs = QtGui.QColorSpace(QtGui.QColorSpace.NamedColorSpace.SRgb)
                except AttributeError:
                    srgb_cs = QtGui.QColorSpace(QtGui.QColorSpace.SRgb)
                qimg.setColorSpace(srgb_cs)
            except Exception:
                pass

        def image_size(self) -> tuple[int, int] | None:
            return self._image_size

        def set_view_crop_rect(self, rect: tuple[float, float, float, float] | None) -> None:
            normalized = self._normalize_view_crop_rect(rect)
            if normalized == self._view_crop_rect:
                return
            self._view_crop_rect = normalized
            self._pan = QtCore.QPointF(0.0, 0.0)
            self._clear_display_cache()
            self._refresh_scaled_pixmap()

        def clear_view_crop_rect(self) -> None:
            self.set_view_crop_rect(None)

        def view_crop_rect(self) -> tuple[int, int, int, int] | None:
            return self._view_crop_rect

        def set_interaction_cursor(self, cursor: QtCore.Qt.CursorShape | None) -> None:
            self._interaction_cursor = cursor
            self._apply_idle_cursor()

        def set_space_pan_active(self, active: bool) -> None:
            self._space_pan_active = bool(active)
            self._apply_idle_cursor()

        def set_overlay_points(self, points: list[tuple[float, float]]) -> None:
            self._overlay_points = list(points)
            self._refresh_scaled_pixmap()

        def set_editable_sample_regions(self, regions: list[dict[str, Any]], *, enabled: bool = True) -> None:
            normalized: list[dict[str, Any]] = []
            for fallback_index, region in enumerate(regions or [], start=1):
                if not isinstance(region, dict):
                    continue
                points: list[tuple[float, float]] = []
                for point in region.get("points") or []:
                    try:
                        x, y = point
                        points.append((float(x), float(y)))
                    except Exception:
                        continue
                if len(points) < 3:
                    continue
                region_id = str(region.get("id") or f"R{fallback_index:02d}")
                normalized.append(
                    {
                        "id": region_id,
                        "label": str(region.get("label") or region_id),
                        "points": points,
                    }
                )
            self._editable_sample_regions = normalized
            self._editable_sample_regions_enabled = bool(enabled) and bool(normalized)
            self._sample_region_drag_id = None
            self._sample_region_drag_start_image = None
            self._sample_region_drag_start_points = []
            self._sample_region_hover_id = None
            self._refresh_scaled_pixmap()
            self._apply_idle_cursor()

        def clear_editable_sample_regions(self) -> None:
            self.set_editable_sample_regions([], enabled=False)

        def set_sample_markers(self, markers: list[dict[str, Any]]) -> None:
            self._sample_markers = [dict(marker) for marker in markers]
            self._refresh_scaled_pixmap()

        def set_sample_magnifier_enabled(self, enabled: bool, *, radius: int | None = None) -> None:
            self._sample_magnifier_enabled = bool(enabled)
            if radius is not None:
                self._sample_magnifier_radius = max(0, int(radius))
            if not self._sample_magnifier_enabled:
                self._sample_magnifier_image_pos = None
            self.update()

        def set_sample_magnifier_radius(self, radius: int) -> None:
            self._sample_magnifier_radius = max(0, int(radius))
            self.update()

        def set_roi_selection_enabled(self, enabled: bool) -> None:
            self._roi_selection_enabled = bool(enabled)
            self._roi_drag_start_image = None
            self._roi_drag_current_image = None
            self._apply_idle_cursor()
            self.update()

        def set_line_selection_enabled(self, enabled: bool, *, reference_axis: str = "horizontal") -> None:
            self._line_selection_enabled = bool(enabled)
            axis = str(reference_axis or "horizontal").strip().lower()
            self._line_reference_axis = "vertical" if axis == "vertical" else "horizontal"
            self._line_drag_start_image = None
            self._line_drag_current_image = None
            self._apply_idle_cursor()
            self.update()

        def set_roi_rect(
            self,
            rect: tuple[float, float, float, float] | None,
            *,
            label: str | None = None,
        ) -> None:
            self._roi_rect = _normalize_rect(rect) if rect is not None else None
            if label is not None:
                self._roi_label = str(label)
            self._refresh_scaled_pixmap()

        def clear_roi_rect(self) -> None:
            self.set_roi_rect(None)

        def set_clip_overlay_enabled(self, enabled: bool) -> None:
            self._clip_overlay_enabled = bool(enabled)
            self._refresh_scaled_pixmap()

        def clear_clip_overlay(self) -> None:
            self._clip_overlay_pixmap = None
            self._clear_display_cache()
            self._refresh_scaled_pixmap()

        def set_clip_overlay_classes(self, classes_u8: np.ndarray | None) -> None:
            if classes_u8 is None:
                self._clip_overlay_pixmap = None
                self._refresh_scaled_pixmap()
                return
            classes = np.ascontiguousarray(np.asarray(classes_u8, dtype=np.uint8))
            if classes.ndim != 2:
                self._clip_overlay_pixmap = None
                self._refresh_scaled_pixmap()
                return
            h, w = int(classes.shape[0]), int(classes.shape[1])
            if h <= 0 or w <= 0:
                self._clip_overlay_pixmap = None
                self._refresh_scaled_pixmap()
                return
            qimg = QtGui.QImage(classes.data, w, h, w, QtGui.QImage.Format_Indexed8).copy()
            self._set_clip_overlay_color_table(qimg)
            self._clip_overlay_pixmap = qimg
            self._clear_display_cache()
            self._refresh_scaled_pixmap()

        def update_clip_overlay_classes_region(self, x: int, y: int, classes_u8: np.ndarray | None) -> None:
            if classes_u8 is None or self._image_size is None:
                return
            classes = np.ascontiguousarray(np.asarray(classes_u8, dtype=np.uint8))
            if classes.ndim != 2:
                return
            image_w, image_h = self._image_size
            x0 = int(np.clip(int(x), 0, image_w))
            y0 = int(np.clip(int(y), 0, image_h))
            if x0 >= image_w or y0 >= image_h:
                return
            h, w = int(classes.shape[0]), int(classes.shape[1])
            w = min(w, image_w - x0)
            h = min(h, image_h - y0)
            if w <= 0 or h <= 0:
                return

            if (
                not isinstance(self._clip_overlay_pixmap, QtGui.QImage)
                or int(self._clip_overlay_pixmap.width()) != image_w
                or int(self._clip_overlay_pixmap.height()) != image_h
                or self._clip_overlay_pixmap.format() != QtGui.QImage.Format_Indexed8
            ):
                base = QtGui.QImage(image_w, image_h, QtGui.QImage.Format_Indexed8)
                self._set_clip_overlay_color_table(base)
                base.fill(0)
                self._clip_overlay_pixmap = base

            overlay = self._clip_overlay_pixmap
            bpl = int(overlay.bytesPerLine())
            bits = overlay.bits()
            overlay_view = np.ndarray((image_h, bpl), dtype=np.uint8, buffer=bits)
            overlay_view[y0 : y0 + h, x0 : x0 + w] = classes[:h, :w]
            self._display_clip_cache_key = None
            self._display_clip_cache = None
            self.update()

        @staticmethod
        def _set_clip_overlay_color_table(qimg: QtGui.QImage) -> None:
            qimg.setColorCount(4)
            qimg.setColor(0, QtGui.qRgba(0, 0, 0, 0))
            qimg.setColor(1, QtGui.qRgba(44, 156, 255, 110))
            qimg.setColor(2, QtGui.qRgba(255, 68, 68, 120))
            qimg.setColor(3, QtGui.qRgba(196, 65, 255, 140))

        def set_view_transform(self, *, zoom: float, rotation: float) -> None:
            anchor_widget = QtCore.QPointF(float(self.width()) / 2.0, float(self.height()) / 2.0)
            anchor_image = self._map_widget_to_image(anchor_widget)
            old_zoom = float(self._view_zoom)
            old_rotation = float(self._view_rotation) % 360.0
            self._view_zoom = float(np.clip(zoom, 0.05, 64.0))
            self._view_rotation = float(rotation) % 360.0
            if (
                anchor_image is not None
                and (
                    abs(float(self._view_zoom) - old_zoom) > 1e-9
                    or abs((float(self._view_rotation) - old_rotation + 180.0) % 360.0 - 180.0) > 1e-9
                )
            ):
                self._pan = self._pan_for_image_anchor(anchor_image, anchor_widget)
            if not self._image_can_pan():
                self._pan = QtCore.QPointF(0.0, 0.0)
            self._refresh_scaled_pixmap()
            self._apply_idle_cursor()
            self.viewTransformChanged.emit(float(self._view_zoom), float(self._view_rotation))

        def current_display_scale(self) -> float | None:
            geometry = self._display_geometry()
            if geometry is None:
                return None
            _pixmap, _rect, scale, _transform, _bounds = geometry
            return float(scale)

        def view_zoom_for_display_scale(self, scale: float) -> float:
            fit = self._display_fit_scale()
            return float(np.clip(float(scale) / max(1e-6, fit), 0.05, 64.0))

        def visible_image_rect(self, *, margin: int = 0) -> tuple[int, int, int, int] | None:
            if self._base_pixmap is None or self._image_size is None:
                return None
            if abs(float(self._view_rotation) % 360.0) > 1e-6:
                return None
            geometry = self._display_geometry()
            if geometry is None:
                return None
            _pixmap, rect, scale, _transform, _bounds = geometry
            visible = rect.intersected(QtCore.QRectF(self.rect()))
            if visible.isEmpty():
                return None
            source_rect = self._active_source_rect()
            image_w, image_h = int(source_rect.width()), int(source_rect.height())
            scale = max(float(scale), 1e-6)
            pad = max(0, int(margin))
            x0 = max(0, int(np.floor((visible.left() - rect.left()) / scale)) - pad)
            y0 = max(0, int(np.floor((visible.top() - rect.top()) / scale)) - pad)
            x1 = min(int(image_w), int(np.ceil((visible.right() - rect.left()) / scale)) + pad)
            y1 = min(int(image_h), int(np.ceil((visible.bottom() - rect.top()) / scale)) + pad)
            if x1 <= x0 or y1 <= y0:
                return None
            return int(source_rect.x()) + x0, int(source_rect.y()) + y0, x1 - x0, y1 - y0

        def mousePressEvent(self, event) -> None:  # noqa: N802
            self._update_sample_magnifier_from_widget_pos(event.position())
            if (
                self._editable_sample_regions_enabled
                and event.button() == QtCore.Qt.LeftButton
                and self._base_pixmap is not None
            ):
                mapped = self._map_widget_to_image(event.position())
                region = self._sample_region_at_image_pos(mapped)
                if mapped is not None and region is not None:
                    self._sample_region_drag_id = str(region.get("id") or "")
                    self._sample_region_drag_start_image = mapped
                    self._sample_region_drag_start_points = list(region.get("points") or [])
                    self.setCursor(QtCore.Qt.SizeAllCursor)
                    event.accept()
                    return
            if event.button() == QtCore.Qt.LeftButton and self._base_pixmap is not None and self._space_pan_active:
                self._drag_start = event.position()
                self._drag_last = event.position()
                self._drag_moved = False
                self.setCursor(QtCore.Qt.ClosedHandCursor)
                return
            if self._line_selection_enabled and event.button() == QtCore.Qt.LeftButton and self._base_pixmap is not None:
                mapped = self._map_widget_to_image(event.position())
                if mapped is not None:
                    self._line_drag_start_image = mapped
                    self._line_drag_current_image = mapped
                    self.update()
                    return
            if self._roi_selection_enabled and event.button() == QtCore.Qt.LeftButton and self._base_pixmap is not None:
                mapped = self._map_widget_to_image(event.position())
                if mapped is not None:
                    self._roi_drag_start_image = mapped
                    self._roi_drag_current_image = mapped
                    self._roi_rect = _rect_from_points(mapped, mapped)
                    self.update()
                    return
            if event.button() == QtCore.Qt.LeftButton and self._base_pixmap is not None:
                self._drag_start = event.position()
                self._drag_last = event.position()
                self._drag_moved = False
                if self._image_can_pan():
                    self.setCursor(QtCore.Qt.ClosedHandCursor)
                else:
                    self._apply_idle_cursor()
                return
            super().mousePressEvent(event)

        def mouseMoveEvent(self, event) -> None:  # noqa: N802
            self._update_sample_magnifier_from_widget_pos(event.position())
            if self._sample_region_drag_id is not None and self._sample_region_drag_start_image is not None:
                mapped = self._map_widget_to_image(event.position())
                if mapped is not None:
                    dx = float(mapped[0]) - float(self._sample_region_drag_start_image[0])
                    dy = float(mapped[1]) - float(self._sample_region_drag_start_image[1])
                    self._move_sample_region(self._sample_region_drag_id, dx, dy)
                    self.setCursor(QtCore.Qt.SizeAllCursor)
                return
            if self._line_selection_enabled and self._line_drag_start_image is not None:
                mapped = self._map_widget_to_image(event.position())
                if mapped is not None:
                    self._line_drag_current_image = mapped
                    self.update()
                return
            if self._roi_selection_enabled and self._roi_drag_start_image is not None:
                mapped = self._map_widget_to_image(event.position())
                if mapped is not None:
                    self._roi_drag_current_image = mapped
                    self._roi_rect = _rect_from_points(self._roi_drag_start_image, mapped)
                    self.update()
                return
            if self._drag_last is not None and self._drag_start is not None:
                delta = event.position() - self._drag_last
                distance = event.position() - self._drag_start
                if self._image_can_pan() and (abs(distance.x()) > 3.0 or abs(distance.y()) > 3.0):
                    self._pan += delta
                    self._drag_moved = True
                    self._refresh_scaled_pixmap()
                self._drag_last = event.position()
                return
            if self._editable_sample_regions_enabled:
                mapped = self._map_widget_to_image(event.position())
                region = self._sample_region_at_image_pos(mapped)
                next_hover = str(region.get("id") or "") if region is not None else None
                if next_hover != self._sample_region_hover_id:
                    self._sample_region_hover_id = next_hover
                    self.update()
                if region is not None:
                    self.setCursor(QtCore.Qt.SizeAllCursor)
                    return
            self._apply_idle_cursor()
            super().mouseMoveEvent(event)

        def mouseReleaseEvent(self, event) -> None:  # noqa: N802
            self._update_sample_magnifier_from_widget_pos(event.position())
            if (
                event.button() == QtCore.Qt.LeftButton
                and self._sample_region_drag_id is not None
                and self._sample_region_drag_start_image is not None
            ):
                region_id = self._sample_region_drag_id
                region = self._sample_region_by_id(region_id)
                points = list(region.get("points") or []) if region is not None else []
                self._sample_region_drag_id = None
                self._sample_region_drag_start_image = None
                self._sample_region_drag_start_points = []
                self._apply_idle_cursor()
                self.update()
                if points:
                    self.sampleRegionMoved.emit(str(region_id), points)
                event.accept()
                return
            if (
                self._line_selection_enabled
                and event.button() == QtCore.Qt.LeftButton
                and self._line_drag_start_image is not None
            ):
                mapped = self._map_widget_to_image(event.position()) or self._line_drag_current_image
                start = self._line_drag_start_image
                self._line_drag_current_image = mapped
                if mapped is not None:
                    dx = float(mapped[0]) - float(start[0])
                    dy = float(mapped[1]) - float(start[1])
                    if math.hypot(dx, dy) >= 3.0:
                        self.lineSelected.emit(float(start[0]), float(start[1]), float(mapped[0]), float(mapped[1]))
                self._line_drag_start_image = None
                self._line_drag_current_image = None
                self._apply_idle_cursor()
                self.update()
                return
            if (
                self._roi_selection_enabled
                and event.button() == QtCore.Qt.LeftButton
                and self._roi_drag_start_image is not None
            ):
                mapped = self._map_widget_to_image(event.position()) or self._roi_drag_current_image
                if mapped is not None:
                    rect = _rect_from_points(self._roi_drag_start_image, mapped)
                    self._roi_rect = rect
                    if rect[2] >= 8.0 and rect[3] >= 8.0:
                        self.roiSelected.emit(float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3]))
                self._roi_drag_start_image = None
                self._roi_drag_current_image = None
                self._apply_idle_cursor()
                self.update()
                return
            if event.button() == QtCore.Qt.LeftButton and self._drag_start is not None:
                mapped = self._map_widget_to_image(event.position())
                if mapped is not None and not self._drag_moved:
                    self.imageClicked.emit(float(mapped[0]), float(mapped[1]))
                elif self._drag_moved:
                    self.viewTransformChanged.emit(float(self._view_zoom), float(self._view_rotation))
                self._drag_start = None
                self._drag_last = None
                self._drag_moved = False
                self._apply_idle_cursor()
                return
            super().mouseReleaseEvent(event)

        def leaveEvent(self, event) -> None:  # noqa: N802
            if self._sample_magnifier_image_pos is not None:
                self._sample_magnifier_image_pos = None
                self.update()
            if self._sample_region_hover_id is not None:
                self._sample_region_hover_id = None
                self.update()
            super().leaveEvent(event)

        def wheelEvent(self, event) -> None:  # noqa: N802
            if self._base_pixmap is None:
                return super().wheelEvent(event)
            factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
            self.set_view_transform(zoom=self._view_zoom * factor, rotation=self._view_rotation)
            event.accept()

        def resizeEvent(self, event) -> None:  # noqa: N802
            super().resizeEvent(event)
            self._refresh_scaled_pixmap()

        def paintEvent(self, event) -> None:  # noqa: N802
            if self._base_pixmap is None:
                return super().paintEvent(event)

            geometry = self._display_geometry()
            if geometry is None:
                return super().paintEvent(event)

            pixmap, rect, scale, transform, bounds = geometry
            pixel_exact = self._pixel_exact_rendering_enabled(scale)
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, not pixel_exact)
            painter.fillRect(self.rect(), QtGui.QColor(self._background))
            if isinstance(pixmap, QtGui.QImage):
                painter.drawImage(rect, pixmap, QtCore.QRectF(pixmap.rect()))
            else:
                painter.drawPixmap(rect, pixmap, QtCore.QRectF(pixmap.rect()))
            clip_pixmap = self._display_clip_pixmap()
            if self._clip_overlay_enabled and clip_pixmap is not None:
                if isinstance(clip_pixmap, QtGui.QImage):
                    painter.drawImage(rect, clip_pixmap, QtCore.QRectF(clip_pixmap.rect()))
                else:
                    painter.drawPixmap(rect, clip_pixmap, QtCore.QRectF(clip_pixmap.rect()))
            if self._pixel_grid_visible(scale):
                self._draw_pixel_grid(painter, rect, scale)

            if self._overlay_points and self._image_size is not None:
                painter.setRenderHint(QtGui.QPainter.Antialiasing)
                painter.setPen(QtGui.QPen(QtGui.QColor("#f59e0b"), 2))
                painter.setBrush(QtCore.Qt.NoBrush)
                qpoints = [
                    self._map_image_to_widget(x, y, rect, scale, transform, bounds)
                    for x, y in self._overlay_points
                ]
                if len(qpoints) >= 2:
                    painter.drawPolyline(QtGui.QPolygonF(qpoints))
                if len(qpoints) == 4:
                    painter.drawLine(qpoints[-1], qpoints[0])
                painter.setBrush(QtGui.QBrush(QtGui.QColor(245, 158, 11, 160)))
                for idx, point in enumerate(qpoints, start=1):
                    painter.drawEllipse(point, 6, 6)
                    painter.drawText(point + QtCore.QPointF(8, -8), str(idx))

            if self._editable_sample_regions and self._image_size is not None:
                self._draw_editable_sample_regions(painter, rect, scale, transform, bounds)

            if self._sample_markers and self._image_size is not None:
                self._draw_sample_markers(painter, rect, scale, transform, bounds)

            if self._line_drag_start_image is not None and self._line_drag_current_image is not None and self._image_size is not None:
                start = self._map_image_to_widget(
                    self._line_drag_start_image[0],
                    self._line_drag_start_image[1],
                    rect,
                    scale,
                    transform,
                    bounds,
                )
                end = self._map_image_to_widget(
                    self._line_drag_current_image[0],
                    self._line_drag_current_image[1],
                    rect,
                    scale,
                    transform,
                    bounds,
                )
                self._draw_level_line_overlay(painter, start, end)

            if self._roi_rect is not None and self._image_size is not None:
                x, y, w, h = self._roi_rect
                corners = [
                    self._map_image_to_widget(x, y, rect, scale, transform, bounds),
                    self._map_image_to_widget(x + w, y, rect, scale, transform, bounds),
                    self._map_image_to_widget(x + w, y + h, rect, scale, transform, bounds),
                    self._map_image_to_widget(x, y + h, rect, scale, transform, bounds),
                ]
                painter.setRenderHint(QtGui.QPainter.Antialiasing)
                painter.setPen(QtGui.QPen(QtGui.QColor("#38bdf8"), 2))
                painter.setBrush(QtGui.QColor(56, 189, 248, 34))
                painter.drawPolygon(QtGui.QPolygonF(corners))
                painter.setBrush(QtCore.Qt.NoBrush)
                painter.drawText(corners[0] + QtCore.QPointF(6, -6), self._roi_label)

            if self._sample_magnifier_enabled and self._sample_magnifier_image_pos is not None:
                self._draw_sample_magnifier(painter, rect, scale, transform, bounds)

            if self._framed:
                painter.setBrush(QtCore.Qt.NoBrush)
                painter.setPen(QtGui.QPen(QtGui.QColor("#5c5c5c"), 1))
                painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
            painter.end()

        def _refresh_scaled_pixmap(self) -> None:
            self.update()

        def _pixel_exact_rendering_enabled(self, scale: float) -> bool:
            return float(scale) >= float(self.PIXEL_EXACT_MIN_SCALE)

        def _pixel_grid_visible(self, scale: float) -> bool:
            return (
                self._image_size is not None
                and abs(float(self._view_rotation) % 360.0) <= 1e-6
                and float(scale) >= float(self.PIXEL_GRID_MIN_SCALE)
            )

        def _draw_pixel_grid(self, painter: QtGui.QPainter, rect: QtCore.QRectF, scale: float) -> None:
            if self._image_size is None:
                return
            image_w, image_h = self._image_size
            source_rect = self._active_source_rect()
            if image_w <= 0 or image_h <= 0:
                return
            scale = max(float(scale), 1e-6)
            visible = rect.intersected(QtCore.QRectF(self.rect()))
            if visible.isEmpty():
                return
            x0 = max(0, int(np.floor((visible.left() - rect.left()) / scale)))
            x1 = min(int(source_rect.width()), int(np.ceil((visible.right() - rect.left()) / scale)))
            y0 = max(0, int(np.floor((visible.top() - rect.top()) / scale)))
            y1 = min(int(source_rect.height()), int(np.ceil((visible.bottom() - rect.top()) / scale)))
            if x1 < x0 or y1 < y0:
                return

            painter.save()
            painter.setRenderHint(QtGui.QPainter.Antialiasing, False)
            alpha = 42 if scale < 16.0 else 58
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, alpha), 0))
            top = max(visible.top(), rect.top())
            bottom = min(visible.bottom(), rect.bottom())
            left = max(visible.left(), rect.left())
            right = min(visible.right(), rect.right())
            for x in range(x0, x1 + 1):
                px = rect.left() + float(x) * scale
                painter.drawLine(QtCore.QPointF(px, top), QtCore.QPointF(px, bottom))
            for y in range(y0, y1 + 1):
                py = rect.top() + float(y) * scale
                painter.drawLine(QtCore.QPointF(left, py), QtCore.QPointF(right, py))
            painter.restore()

        def _draw_sample_markers(
            self,
            painter: QtGui.QPainter,
            rect: QtCore.QRectF,
            scale: float,
            transform: QtGui.QTransform,
            bounds: QtCore.QRectF,
        ) -> None:
            source_rect = self._active_source_rect()
            painter.save()
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            font = painter.font()
            font.setBold(True)
            font.setPointSize(max(8, font.pointSize()))
            painter.setFont(font)
            for fallback_index, marker in enumerate(self._sample_markers, start=1):
                try:
                    x = float(marker.get("x", 0.0))
                    y = float(marker.get("y", 0.0))
                except Exception:
                    continue
                if (
                    x < float(source_rect.x())
                    or y < float(source_rect.y())
                    or x >= float(source_rect.x() + source_rect.width())
                    or y >= float(source_rect.y() + source_rect.height())
                ):
                    continue
                point = self._map_image_to_widget(x, y, rect, scale, transform, bounds)
                label = str(marker.get("label") or marker.get("index") or fallback_index)
                selected = bool(marker.get("selected"))
                radius = 12.0 if selected else 10.0
                label_rect = QtCore.QRectF(point.x() - radius, point.y() - radius, radius * 2.0, radius * 2.0)
                fill = QtGui.QColor(str(marker.get("color") or "#22d3ee"))
                if not fill.isValid():
                    fill = QtGui.QColor("#22d3ee")
                fill.setAlpha(220)
                text_color = QtGui.QColor(str(marker.get("text_color") or ""))
                if not text_color.isValid():
                    luminance = (
                        0.2126 * float(fill.red())
                        + 0.7152 * float(fill.green())
                        + 0.0722 * float(fill.blue())
                    ) / 255.0
                    text_color = QtGui.QColor("#202020" if luminance >= 0.62 else "#ffffff")
                outline = QtGui.QColor("#fbbf24" if selected else ("#ffffff" if text_color.lightnessF() < 0.5 else "#202020"))
                painter.setPen(QtGui.QPen(outline, 4 if selected else 3))
                painter.setBrush(fill)
                painter.drawEllipse(label_rect)
                painter.setPen(QtGui.QPen(text_color, 1))
                painter.drawText(label_rect, QtCore.Qt.AlignCenter, label)
                painter.setPen(QtGui.QPen(outline, 2 if selected else 1))
                outer = 18.0 if selected else 15.0
                inner = 7.0 if selected else 6.0
                painter.drawLine(point + QtCore.QPointF(-outer, 0), point + QtCore.QPointF(-inner, 0))
                painter.drawLine(point + QtCore.QPointF(inner, 0), point + QtCore.QPointF(outer, 0))
                painter.drawLine(point + QtCore.QPointF(0, -outer), point + QtCore.QPointF(0, -inner))
                painter.drawLine(point + QtCore.QPointF(0, inner), point + QtCore.QPointF(0, outer))
            painter.restore()

        def _draw_editable_sample_regions(
            self,
            painter: QtGui.QPainter,
            rect: QtCore.QRectF,
            scale: float,
            transform: QtGui.QTransform,
            bounds: QtCore.QRectF,
        ) -> None:
            painter.save()
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            font = painter.font()
            font.setBold(True)
            font.setPointSize(max(7, font.pointSize() - 1))
            painter.setFont(font)
            for region in self._editable_sample_regions:
                points = region.get("points") or []
                if len(points) < 3:
                    continue
                qpoints = [
                    self._map_image_to_widget(float(x), float(y), rect, scale, transform, bounds)
                    for x, y in points
                ]
                region_id = str(region.get("id") or "")
                active = region_id and region_id in {self._sample_region_drag_id, self._sample_region_hover_id}
                pen_color = QtGui.QColor("#facc15" if active else "#38bdf8")
                fill_color = QtGui.QColor(250, 204, 21, 46) if active else QtGui.QColor(56, 189, 248, 30)
                painter.setPen(QtGui.QPen(pen_color, 2 if active else 1))
                painter.setBrush(fill_color)
                polygon = QtGui.QPolygonF(qpoints)
                painter.drawPolygon(polygon)
                center_x = sum(point.x() for point in qpoints) / max(1, len(qpoints))
                center_y = sum(point.y() for point in qpoints) / max(1, len(qpoints))
                label = str(region.get("label") or region_id)
                if label:
                    metrics = painter.fontMetrics()
                    text_w = metrics.horizontalAdvance(label)
                    label_rect = QtCore.QRectF(
                        center_x - text_w / 2.0 - 4.0,
                        center_y - metrics.height() / 2.0 - 2.0,
                        text_w + 8.0,
                        metrics.height() + 4.0,
                    )
                    painter.setPen(QtCore.Qt.NoPen)
                    painter.setBrush(QtGui.QColor(17, 24, 39, 185))
                    painter.drawRoundedRect(label_rect, 3, 3)
                    painter.setPen(QtGui.QColor("#f8fafc"))
                    painter.drawText(label_rect, QtCore.Qt.AlignCenter, label)
            painter.restore()

        def _draw_sample_magnifier(
            self,
            painter: QtGui.QPainter,
            rect: QtCore.QRectF,
            scale: float,
            transform: QtGui.QTransform,
            bounds: QtCore.QRectF,
        ) -> None:
            if self._base_pixmap is None or self._image_size is None or self._sample_magnifier_image_pos is None:
                return
            image = self._base_pixmap if isinstance(self._base_pixmap, QtGui.QImage) else self._base_pixmap.toImage()
            image_w, image_h = self._image_size
            xi = int(round(float(np.clip(self._sample_magnifier_image_pos[0], 0, max(0, image_w - 1)))))
            yi = int(round(float(np.clip(self._sample_magnifier_image_pos[1], 0, max(0, image_h - 1)))))
            sample_radius = max(0, int(self._sample_magnifier_radius))
            context_radius = max(6, sample_radius + 4)
            x0 = max(0, xi - context_radius)
            x1 = min(image_w - 1, xi + context_radius)
            y0 = max(0, yi - context_radius)
            y1 = min(image_h - 1, yi + context_radius)
            patch_w = max(1, x1 - x0 + 1)
            patch_h = max(1, y1 - y0 + 1)
            pixel_size = int(np.clip(176.0 / max(patch_w, patch_h), 5, 14))
            label_h = 24
            padding = 8
            lens_w = patch_w * pixel_size + padding * 2
            lens_h = patch_h * pixel_size + padding * 2 + label_h
            anchor = self._map_image_to_widget(xi, yi, rect, scale, transform, bounds)
            lens = QtCore.QRectF(anchor.x() + 18, anchor.y() + 18, lens_w, lens_h)
            bounds_rect = QtCore.QRectF(self.rect()).adjusted(6, 6, -6, -6)
            if lens.right() > bounds_rect.right():
                lens.moveRight(anchor.x() - 18)
            if lens.left() < bounds_rect.left():
                lens.moveLeft(bounds_rect.left())
            if lens.bottom() > bounds_rect.bottom():
                lens.moveBottom(anchor.y() - 18)
            if lens.top() < bounds_rect.top():
                lens.moveTop(bounds_rect.top())

            painter.save()
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            painter.setPen(QtGui.QPen(QtGui.QColor("#7a7a7a"), 1))
            painter.setBrush(QtGui.QColor(15, 23, 42, 235))
            painter.drawRoundedRect(lens, 6, 6)

            grid_origin = QtCore.QPointF(lens.left() + padding, lens.top() + padding)
            painter.setRenderHint(QtGui.QPainter.Antialiasing, False)
            for yy in range(y0, y1 + 1):
                for xx in range(x0, x1 + 1):
                    color = image.pixelColor(xx, yy)
                    px = grid_origin.x() + (xx - x0) * pixel_size
                    py = grid_origin.y() + (yy - y0) * pixel_size
                    painter.fillRect(QtCore.QRectF(px, py, pixel_size, pixel_size), color)

            painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 55), 1))
            for column in range(patch_w + 1):
                xline = grid_origin.x() + column * pixel_size
                painter.drawLine(
                    QtCore.QPointF(xline, grid_origin.y()),
                    QtCore.QPointF(xline, grid_origin.y() + patch_h * pixel_size),
                )
            for row in range(patch_h + 1):
                yline = grid_origin.y() + row * pixel_size
                painter.drawLine(
                    QtCore.QPointF(grid_origin.x(), yline),
                    QtCore.QPointF(grid_origin.x() + patch_w * pixel_size, yline),
                )

            selected_x0 = max(x0, xi - sample_radius)
            selected_x1 = min(x1, xi + sample_radius)
            selected_y0 = max(y0, yi - sample_radius)
            selected_y1 = min(y1, yi + sample_radius)
            selection = QtCore.QRectF(
                grid_origin.x() + (selected_x0 - x0) * pixel_size,
                grid_origin.y() + (selected_y0 - y0) * pixel_size,
                (selected_x1 - selected_x0 + 1) * pixel_size,
                (selected_y1 - selected_y0 + 1) * pixel_size,
            )
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            painter.setBrush(QtGui.QColor(250, 204, 21, 42))
            painter.setPen(QtGui.QPen(QtGui.QColor("#facc15"), 2))
            painter.drawRect(selection.adjusted(1, 1, -1, -1))

            center = QtCore.QRectF(
                grid_origin.x() + (xi - x0) * pixel_size,
                grid_origin.y() + (yi - y0) * pixel_size,
                pixel_size,
                pixel_size,
            )
            painter.setPen(QtGui.QPen(QtGui.QColor("#ffffff"), 2))
            painter.drawLine(center.center() + QtCore.QPointF(-pixel_size * 0.35, 0), center.center() + QtCore.QPointF(pixel_size * 0.35, 0))
            painter.drawLine(center.center() + QtCore.QPointF(0, -pixel_size * 0.35), center.center() + QtCore.QPointF(0, pixel_size * 0.35))

            painter.setPen(QtGui.QColor("#e6e6e6"))
            font = painter.font()
            font.setPointSize(max(8, font.pointSize() - 1))
            painter.setFont(font)
            matrix = sample_radius * 2 + 1
            label_rect = QtCore.QRectF(lens.left() + padding, lens.bottom() - label_h, lens.width() - padding * 2, label_h)
            painter.drawText(label_rect, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, f"x {xi}, y {yi} | {matrix}x{matrix}")
            painter.restore()

        def _update_sample_magnifier_from_widget_pos(self, pos: QtCore.QPointF) -> None:
            if not self._sample_magnifier_enabled or self._base_pixmap is None:
                if self._sample_magnifier_image_pos is not None:
                    self._sample_magnifier_image_pos = None
                    self.update()
                return
            mapped = self._map_widget_to_image(pos)
            next_pos = None if mapped is None else (float(mapped[0]), float(mapped[1]))
            if next_pos != self._sample_magnifier_image_pos:
                self._sample_magnifier_image_pos = next_pos
                self.update()

        def _apply_idle_cursor(self) -> None:
            if self._space_pan_active and self._base_pixmap is not None:
                self.setCursor(QtCore.Qt.OpenHandCursor)
            elif self._sample_region_drag_id is not None:
                self.setCursor(QtCore.Qt.SizeAllCursor)
            elif self._roi_selection_enabled:
                self.setCursor(QtCore.Qt.CrossCursor)
            elif self._line_selection_enabled:
                self.setCursor(QtCore.Qt.CrossCursor)
            elif self._interaction_cursor is not None:
                self.setCursor(self._interaction_cursor)
            elif self._image_can_pan():
                self.setCursor(QtCore.Qt.OpenHandCursor)
            else:
                self.unsetCursor()

        def _sample_region_by_id(self, region_id: str) -> dict[str, Any] | None:
            for region in self._editable_sample_regions:
                if str(region.get("id") or "") == str(region_id):
                    return region
            return None

        def _sample_region_at_image_pos(self, mapped: tuple[float, float] | None) -> dict[str, Any] | None:
            if mapped is None or not self._editable_sample_regions_enabled:
                return None
            point = QtCore.QPointF(float(mapped[0]), float(mapped[1]))
            best_region = None
            best_area = float("inf")
            for region in self._editable_sample_regions:
                points = region.get("points") or []
                if len(points) < 3:
                    continue
                polygon = QtGui.QPolygonF([QtCore.QPointF(float(x), float(y)) for x, y in points])
                if not polygon.containsPoint(point, QtCore.Qt.OddEvenFill):
                    continue
                bounds = polygon.boundingRect()
                area = max(1.0, float(bounds.width()) * float(bounds.height()))
                if area < best_area:
                    best_region = region
                    best_area = area
            return best_region

        def _move_sample_region(self, region_id: str, dx: float, dy: float) -> None:
            region = self._sample_region_by_id(region_id)
            if region is None:
                return
            image_w, image_h = self._image_size or (0, 0)
            moved: list[tuple[float, float]] = []
            for x, y in self._sample_region_drag_start_points:
                moved.append(
                    (
                        float(np.clip(float(x) + float(dx), 0.0, max(0.0, float(image_w) - 1.0))),
                        float(np.clip(float(y) + float(dy), 0.0, max(0.0, float(image_h) - 1.0))),
                    )
                )
            region["points"] = moved
            self.update()

        def _draw_level_line_overlay(
            self,
            painter: QtGui.QPainter,
            start: QtCore.QPointF,
            end: QtCore.QPointF,
        ) -> None:
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            painter.setPen(QtGui.QPen(QtGui.QColor("#f59e0b"), 2))
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawLine(start, end)
            painter.setBrush(QtGui.QBrush(QtGui.QColor(245, 158, 11, 180)))
            painter.setPen(QtGui.QPen(QtGui.QColor("#202020"), 1))
            painter.drawEllipse(start, 5, 5)
            painter.drawEllipse(end, 5, 5)

            text = self._level_line_angle_text()
            if not text:
                return
            metrics = painter.fontMetrics()
            mid = QtCore.QPointF((start.x() + end.x()) / 2.0, (start.y() + end.y()) / 2.0)
            text_w = metrics.horizontalAdvance(text)
            label_rect = QtCore.QRectF(mid.x() + 8, mid.y() - metrics.height() - 8, text_w + 12, metrics.height() + 6)
            bounds = QtCore.QRectF(self.rect()).adjusted(4, 4, -4, -4)
            if label_rect.right() > bounds.right():
                label_rect.moveRight(bounds.right())
            if label_rect.left() < bounds.left():
                label_rect.moveLeft(bounds.left())
            if label_rect.top() < bounds.top():
                label_rect.moveTop(bounds.top())
            if label_rect.bottom() > bounds.bottom():
                label_rect.moveBottom(bounds.bottom())
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QColor(17, 24, 39, 215))
            painter.drawRoundedRect(label_rect, 4, 4)
            painter.setPen(QtGui.QColor("#fbbf24"))
            painter.drawText(label_rect, QtCore.Qt.AlignCenter, text)

        def _level_line_angle_text(self) -> str:
            if self._line_drag_start_image is None or self._line_drag_current_image is None:
                return ""
            dx = float(self._line_drag_current_image[0]) - float(self._line_drag_start_image[0])
            dy = float(self._line_drag_current_image[1]) - float(self._line_drag_start_image[1])
            if abs(dx) < 1e-6 and abs(dy) < 1e-6:
                return "0.00 grados"
            angle = math.degrees(math.atan2(dy, dx))
            if self._line_reference_axis == "vertical":
                delta = ((angle - 90.0 + 180.0) % 360.0) - 180.0
                prefix = "V"
            else:
                delta = ((angle + 180.0) % 360.0) - 180.0
                prefix = "H"
            return f"{prefix} {delta:+.2f} grados"

        def _map_widget_to_image(self, pos: QtCore.QPointF) -> tuple[float, float] | None:
            if self._base_pixmap is None or self._image_size is None:
                return None
            geometry = self._display_geometry()
            if geometry is None:
                return None
            _pixmap, rect, scale, transform, bounds = geometry
            if not rect.contains(pos):
                return None
            tx = (float(pos.x()) - rect.left()) / max(1e-6, scale)
            ty = (float(pos.y()) - rect.top()) / max(1e-6, scale)
            inv, ok = transform.inverted()
            if not ok:
                return None
            mapped_local = inv.map(QtCore.QPointF(tx + bounds.left(), ty + bounds.top()))
            source_rect = self._active_source_rect()
            mapped = QtCore.QPointF(mapped_local.x() + source_rect.x(), mapped_local.y() + source_rect.y())
            if (
                mapped.x() < source_rect.x()
                or mapped.y() < source_rect.y()
                or mapped.x() > source_rect.x() + source_rect.width()
                or mapped.y() > source_rect.y() + source_rect.height()
            ):
                return None
            return float(mapped.x()), float(mapped.y())

        def _pan_for_image_anchor(
            self,
            image_pos: tuple[float, float],
            widget_pos: QtCore.QPointF,
        ) -> QtCore.QPointF:
            if self._base_pixmap is None:
                return QtCore.QPointF(0.0, 0.0)
            source_rect = self._active_source_rect()
            transform = QtGui.QTransform()
            transform.rotate(float(self._view_rotation) % 360.0)
            bounds = transform.mapRect(
                QtCore.QRectF(
                    0.0,
                    0.0,
                    float(source_rect.width()),
                    float(source_rect.height()),
                )
            )
            pixmap = self._display_pixmap()
            pw = max(1.0, float(pixmap.width()))
            ph = max(1.0, float(pixmap.height()))
            fit = self._display_fit_scale(pixmap=pixmap)
            scale = fit * float(self._view_zoom)
            draw_w = pw * scale
            draw_h = ph * scale
            mapped = transform.map(
                QtCore.QPointF(float(image_pos[0]) - source_rect.x(), float(image_pos[1]) - source_rect.y())
            )
            anchor_x = (mapped.x() - bounds.left()) * scale
            anchor_y = (mapped.y() - bounds.top()) * scale
            pan_x = float(widget_pos.x()) - (float(self.width()) - draw_w) / 2.0 - anchor_x
            pan_y = float(widget_pos.y()) - (float(self.height()) - draw_h) / 2.0 - anchor_y
            max_pan_x = max(0.0, (draw_w - float(self.width())) / 2.0)
            max_pan_y = max(0.0, (draw_h - float(self.height())) / 2.0)
            return QtCore.QPointF(
                float(np.clip(pan_x, -max_pan_x, max_pan_x)),
                float(np.clip(pan_y, -max_pan_y, max_pan_y)),
            )

        def _display_geometry(self):
            if self._base_pixmap is None:
                return None
            source_rect = self._active_source_rect()
            transform = QtGui.QTransform()
            transform.rotate(self._view_rotation)
            bounds = transform.mapRect(
                QtCore.QRectF(
                    0.0,
                    0.0,
                    float(source_rect.width()),
                    float(source_rect.height()),
                )
            )
            pixmap = self._display_pixmap()
            pw = max(1.0, float(pixmap.width()))
            ph = max(1.0, float(pixmap.height()))
            fit = self._display_fit_scale(pixmap=pixmap)
            scale = fit * self._view_zoom
            draw_w = pw * scale
            draw_h = ph * scale
            max_pan_x = max(0.0, (draw_w - self.width()) / 2.0)
            max_pan_y = max(0.0, (draw_h - self.height()) / 2.0)
            pan_x = float(np.clip(self._pan.x(), -max_pan_x, max_pan_x))
            pan_y = float(np.clip(self._pan.y(), -max_pan_y, max_pan_y))
            self._pan = QtCore.QPointF(pan_x, pan_y)
            rect = QtCore.QRectF(
                (self.width() - draw_w) / 2.0 + pan_x,
                (self.height() - draw_h) / 2.0 + pan_y,
                draw_w,
                draw_h,
            )
            return pixmap, rect, scale, transform, bounds

        def _display_fit_scale(self, *, pixmap: QtGui.QPixmap | None = None) -> float:
            if pixmap is None:
                if self._base_pixmap is None:
                    return 1.0
                pixmap = self._display_pixmap()
            pw = max(1.0, float(pixmap.width()))
            ph = max(1.0, float(pixmap.height()))
            return float(min(max(1.0, self.width()) / pw, max(1.0, self.height()) / ph))

        def _image_can_pan(self) -> bool:
            geometry = self._display_geometry()
            if geometry is None:
                return False
            _pixmap, rect, _scale, _transform, _bounds = geometry
            return rect.width() > self.width() + 1.0 or rect.height() > self.height() + 1.0

        def _map_image_to_widget(
            self,
            x: float,
            y: float,
            rect: QtCore.QRectF,
            scale: float,
            transform: QtGui.QTransform,
            bounds: QtCore.QRectF,
        ) -> QtCore.QPointF:
            source_rect = self._active_source_rect()
            mapped = transform.map(QtCore.QPointF(float(x) - source_rect.x(), float(y) - source_rect.y()))
            tx = mapped.x() - bounds.left()
            ty = mapped.y() - bounds.top()
            return QtCore.QPointF(rect.left() + tx * scale, rect.top() + ty * scale)

        def _normalize_view_crop_rect(self, rect: tuple[float, float, float, float] | None) -> tuple[int, int, int, int] | None:
            if rect is None or self._image_size is None:
                return None
            image_w, image_h = self._image_size
            x, y, w, h = _normalize_rect(rect)
            x0 = int(np.clip(np.floor(x), 0, max(0, image_w - 1)))
            y0 = int(np.clip(np.floor(y), 0, max(0, image_h - 1)))
            x1 = int(np.clip(np.ceil(x + w), x0 + 1, image_w))
            y1 = int(np.clip(np.ceil(y + h), y0 + 1, image_h))
            if x1 - x0 < 1 or y1 - y0 < 1:
                return None
            if x0 == 0 and y0 == 0 and x1 == image_w and y1 == image_h:
                return None
            return x0, y0, x1 - x0, y1 - y0

        def _active_source_rect(self) -> QtCore.QRect:
            if self._base_pixmap is None or self._image_size is None:
                return QtCore.QRect(0, 0, 1, 1)
            image_w, image_h = self._image_size
            crop = self._normalize_view_crop_rect(self._view_crop_rect)
            if crop is None:
                return QtCore.QRect(0, 0, int(image_w), int(image_h))
            x, y, w, h = crop
            return QtCore.QRect(int(x), int(y), int(w), int(h))

        def _display_pixmap(self) -> QtGui.QImage | QtGui.QPixmap:
            if self._base_pixmap is None:
                return QtGui.QImage()
            source_rect = self._active_source_rect()
            rotation = float(self._view_rotation) % 360.0
            key = (id(self._base_pixmap), source_rect.x(), source_rect.y(), source_rect.width(), source_rect.height(), round(rotation, 6))
            if self._display_pixmap_cache_key == key and self._display_pixmap_cache is not None:
                return self._display_pixmap_cache
            cropped = (
                self._base_pixmap
                if source_rect.x() == 0
                and source_rect.y() == 0
                and source_rect.width() == self._base_pixmap.width()
                and source_rect.height() == self._base_pixmap.height()
                else self._base_pixmap.copy(source_rect)
            )
            if abs(rotation) > 1e-6:
                cropped = cropped.transformed(QtGui.QTransform().rotate(rotation), QtCore.Qt.SmoothTransformation)
            self._display_pixmap_cache_key = key
            self._display_pixmap_cache = cropped
            return cropped

        def _display_clip_pixmap(self) -> QtGui.QImage | QtGui.QPixmap | None:
            if self._clip_overlay_pixmap is None:
                return None
            source_rect = self._active_source_rect()
            rotation = float(self._view_rotation) % 360.0
            key = (
                id(self._clip_overlay_pixmap),
                source_rect.x(),
                source_rect.y(),
                source_rect.width(),
                source_rect.height(),
                round(rotation, 6),
            )
            if self._display_clip_cache_key == key and self._display_clip_cache is not None:
                return self._display_clip_cache
            cropped = (
                self._clip_overlay_pixmap
                if source_rect.x() == 0
                and source_rect.y() == 0
                and source_rect.width() == self._clip_overlay_pixmap.width()
                and source_rect.height() == self._clip_overlay_pixmap.height()
                else self._clip_overlay_pixmap.copy(source_rect)
            )
            if abs(rotation) > 1e-6:
                cropped = cropped.transformed(QtGui.QTransform().rotate(rotation), QtCore.Qt.FastTransformation)
            self._display_clip_cache_key = key
            self._display_clip_cache = cropped
            return cropped

        def _clear_display_cache(self) -> None:
            self._display_pixmap_cache_key = None
            self._display_pixmap_cache = None
            self._display_clip_cache_key = None
            self._display_clip_cache = None
else:  # pragma: no cover - importable en entornos sin Qt
    PersistentSideTabWidget = None
    CollapsibleToolPanel = None
    ToneCurveEditor = None
    MTFComparisonPlotWidget = None
    MTFPlotWidget = None
    RGBHistogramWidget = None
    Gamut3DWidget = None
    ColorSampleGamutWidget = None
    ImagePanel = None


def _rect_from_points(
    a: tuple[float, float],
    b: tuple[float, float],
) -> tuple[float, float, float, float]:
    x0, y0 = float(a[0]), float(a[1])
    x1, y1 = float(b[0]), float(b[1])
    x = min(x0, x1)
    y = min(y0, y1)
    return x, y, abs(x1 - x0), abs(y1 - y0)


def _normalize_rect(rect: tuple[float, float, float, float] | None) -> tuple[float, float, float, float] | None:
    if rect is None:
        return None
    x, y, w, h = [float(v) for v in rect]
    if w < 0:
        x += w
        w = abs(w)
    if h < 0:
        y += h
        h = abs(h)
    return x, y, w, h


__all__ = [
    "PersistentSideTabWidget",
    "CollapsibleToolPanel",
    "ToneCurveEditor",
    "MTFComparisonPlotWidget",
    "MTFPlotWidget",
    "RGBHistogramWidget",
    "Gamut3DWidget",
    "ColorSampleGamutWidget",
    "ImagePanel",
]
