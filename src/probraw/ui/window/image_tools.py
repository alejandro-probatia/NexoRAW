from __future__ import annotations

import math
from typing import Any, Literal

from ._imports import QtCore, QtWidgets


class ImageToolsMixin:
    def _toggle_image_crop_selection(self, checked: bool = False) -> None:
        if checked and getattr(self, "_original_linear", None) is None:
            self._set_image_crop_selection_active(False)
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("Carga primero una imagen en el visor."))
            return
        if checked:
            self._deactivate_image_level_tool()
            self._manual_chart_marking = False
            self._set_neutral_picker_active(False)
            if hasattr(self, "_set_color_picker_active"):
                self._set_color_picker_active(False)
            if hasattr(self, "_set_mtf_roi_selection_active"):
                self._set_mtf_roi_selection_active(False)
            if hasattr(self, "_sync_manual_chart_overlay"):
                self._sync_manual_chart_overlay()
            self._set_image_crop_selection_active(True)
            self._set_status(self.tr("Recorte: arrastra un rectangulo sobre la imagen"))
        else:
            self._set_image_crop_selection_active(False)
            self._set_status(self.tr("Seleccion de recorte desactivada"))

    def _set_image_crop_selection_active(self, active: bool) -> None:
        self._image_crop_selection_active = bool(active)
        action = getattr(self, "action_image_crop_select", None)
        if action is not None:
            action.blockSignals(True)
            action.setChecked(self._image_crop_selection_active)
            action.blockSignals(False)
        for panel_name in ("image_result_single", "image_result_compare"):
            panel = getattr(self, panel_name, None)
            if panel is not None and hasattr(panel, "set_roi_selection_enabled"):
                panel.set_roi_selection_enabled(
                    self._image_crop_selection_active or bool(getattr(self, "_mtf_roi_selection_active", False))
                )
        self._sync_image_tool_overlays()

    def _on_viewer_roi_selected(self, x: float, y: float, width: float, height: float) -> None:
        if bool(getattr(self, "_image_crop_selection_active", False)):
            self._on_image_crop_selected(x, y, width, height)
            return
        self._on_mtf_roi_selected(x, y, width, height)

    def _on_image_crop_selected(self, x: float, y: float, width: float, height: float) -> None:
        base_size = self._image_crop_reference_size()
        self._image_crop_rect = (
            int(round(float(x))),
            int(round(float(y))),
            int(round(float(width))),
            int(round(float(height))),
        )
        self._image_crop_base_size = base_size
        self._image_crop_normalized_rect = self._normalized_crop_rect(
            self._image_crop_rect,
            base_size,
        )
        self._set_image_crop_selection_active(False)
        self._viewer_zoom = 1.0
        self._viewer_real_pixel_sync_pending = False
        self._sync_viewer_transform()
        self._sync_image_tool_overlays()
        if hasattr(self, "_push_edit_history_snapshot"):
            self._push_edit_history_snapshot("crop")
        if hasattr(self, "_schedule_render_adjustment_sidecar_persist"):
            self._schedule_render_adjustment_sidecar_persist()
        x0, y0, w, h = self._image_crop_rect
        self._set_status(self.tr("Recorte definido:") + f" x={x0}, y={y0}, {w}x{h}px")

    def _clear_image_crop(self) -> None:
        self._image_crop_rect = None
        self._image_crop_base_size = None
        self._image_crop_normalized_rect = None
        self._set_image_crop_selection_active(False)
        self._viewer_zoom = 1.0
        self._sync_viewer_transform()
        self._sync_image_tool_overlays()
        if hasattr(self, "_push_edit_history_snapshot"):
            self._push_edit_history_snapshot("clear_crop")
        if hasattr(self, "_schedule_render_adjustment_sidecar_persist"):
            self._schedule_render_adjustment_sidecar_persist()
        self._set_status(self.tr("Recorte limpiado"))

    def _start_image_level_tool(self, mode: Literal["horizontal", "vertical"]) -> None:
        if getattr(self, "_original_linear", None) is None:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("Carga primero una imagen en el visor."))
            return
        self._set_image_crop_selection_active(False)
        if hasattr(self, "_set_mtf_roi_selection_active"):
            self._set_mtf_roi_selection_active(False)
        self._manual_chart_marking = False
        self._set_neutral_picker_active(False)
        if hasattr(self, "_set_color_picker_active"):
            self._set_color_picker_active(False)
        self._image_level_selection_active = True
        self._image_level_mode = mode
        self._image_level_points = []
        self._update_viewer_interaction_cursor()
        self._sync_image_tool_overlays()
        label = self.tr("horizontal") if mode == "horizontal" else self.tr("vertical")
        self._set_status(self.tr("Nivelar") + f" {label}: " + self.tr("arrastra una linea sobre una referencia"))

    def _deactivate_image_level_tool(self) -> None:
        if not bool(getattr(self, "_image_level_selection_active", False)):
            return
        self._image_level_selection_active = False
        self._image_level_points = []
        self._update_viewer_interaction_cursor()
        self._sync_image_tool_overlays()

    def _clear_image_level(self) -> None:
        self._image_level_selection_active = False
        self._image_level_points = []
        self._image_level_rotation_degrees = 0.0
        self._viewer_rotation = 0.0
        self._sync_viewer_transform()
        self._update_viewer_interaction_cursor()
        self._sync_image_tool_overlays()
        if hasattr(self, "_push_edit_history_snapshot"):
            self._push_edit_history_snapshot("clear_level")
        if hasattr(self, "_schedule_render_adjustment_sidecar_persist"):
            self._schedule_render_adjustment_sidecar_persist()
        self._set_status(self.tr("Nivelado limpiado"))

    def _apply_output_geometry_adjustment_state(self, geometry: Any | None) -> None:
        state = geometry if isinstance(geometry, dict) else {}

        crop_rect = state.get("crop_rect")
        if isinstance(crop_rect, (list, tuple)) and len(crop_rect) >= 4:
            try:
                parsed_crop = tuple(int(round(float(v))) for v in crop_rect[:4])
                self._image_crop_rect = parsed_crop if parsed_crop[2] > 0 and parsed_crop[3] > 0 else None
            except Exception:
                self._image_crop_rect = None
        else:
            self._image_crop_rect = None

        normalized = state.get("crop_normalized")
        if isinstance(normalized, (list, tuple)) and len(normalized) >= 4:
            try:
                nx, ny, nw, nh = (float(v) for v in normalized[:4])
                valid = 0.0 <= nx < 1.0 and 0.0 <= ny < 1.0 and nw > 0.0 and nh > 0.0
                self._image_crop_normalized_rect = (
                    (nx, ny, min(nw, 1.0 - nx), min(nh, 1.0 - ny))
                    if valid
                    else None
                )
            except Exception:
                self._image_crop_normalized_rect = None
        else:
            self._image_crop_normalized_rect = None

        self._image_crop_base_size = None
        self._image_crop_selection_active = False
        self._image_level_selection_active = False
        self._image_level_points = []
        rotation = float(state.get("rotation_degrees", 0.0) or 0.0)
        signed_rotation = ((rotation + 180.0) % 360.0) - 180.0
        self._image_level_rotation_degrees = float(signed_rotation)
        self._viewer_rotation = float(signed_rotation) % 360.0
        if hasattr(self, "_sync_viewer_transform"):
            self._sync_viewer_transform()
        if hasattr(self, "_update_viewer_interaction_cursor"):
            self._update_viewer_interaction_cursor()
        if hasattr(self, "_sync_image_tool_overlays"):
            self._sync_image_tool_overlays()

    def _on_viewer_line_selected(self, x0: float, y0: float, x1: float, y1: float) -> None:
        if not bool(getattr(self, "_image_level_selection_active", False)):
            return
        self._apply_image_level_from_points((float(x0), float(y0)), (float(x1), float(y1)))

    def _handle_image_tool_click(self, x: float, y: float) -> bool:
        if not bool(getattr(self, "_image_level_selection_active", False)):
            return False
        points = list(getattr(self, "_image_level_points", []))
        if len(points) >= 2:
            points = []
        points.append((float(x), float(y)))
        self._image_level_points = points
        self._sync_image_tool_overlays()
        if len(points) < 2:
            self._set_status(self.tr("Nivelar: marca el segundo punto"))
            return True
        self._apply_image_level_from_points(points[0], points[1])
        return True

    def _apply_image_level_from_points(
        self,
        first: tuple[float, float],
        second: tuple[float, float],
    ) -> None:
        dx = float(second[0]) - float(first[0])
        dy = float(second[1]) - float(first[1])
        if abs(dx) < 1e-6 and abs(dy) < 1e-6:
            self._set_status(self.tr("Nivelar: los dos puntos son iguales"))
            return
        line_angle = math.degrees(math.atan2(dy, dx))
        mode = str(getattr(self, "_image_level_mode", "horizontal") or "horizontal")
        correction = -line_angle if mode == "horizontal" else 90.0 - line_angle
        correction = ((correction + 180.0) % 360.0) - 180.0
        self._image_level_rotation_degrees = correction
        self._viewer_rotation = float(correction) % 360.0
        self._image_level_selection_active = False
        self._image_level_points = []
        self._viewer_zoom = 1.0
        self._sync_viewer_transform()
        self._update_viewer_interaction_cursor()
        self._sync_image_tool_overlays()
        if hasattr(self, "_push_edit_history_snapshot"):
            self._push_edit_history_snapshot("level")
        if hasattr(self, "_schedule_render_adjustment_sidecar_persist"):
            self._schedule_render_adjustment_sidecar_persist()
        label = self.tr("horizontal") if mode == "horizontal" else self.tr("vertical")
        self._set_status(self.tr("Nivelado") + f" {label}: {correction:+.2f} grados")

    def _sync_image_tool_overlays(self) -> None:
        crop_rect = getattr(self, "_image_crop_rect", None)
        crop_active = bool(getattr(self, "_image_crop_selection_active", False))
        mtf_rect = getattr(self, "_mtf_roi", None) if self._mtf_roi_overlay_should_be_visible() else None
        rect = None if crop_active else mtf_rect
        label = self.tr("Recorte") if crop_active else "MTF"
        level_points = list(getattr(self, "_image_level_points", [])) if bool(getattr(self, "_image_level_selection_active", False)) else []
        for panel_name in ("image_result_single", "image_result_compare", "image_original_compare"):
            panel = getattr(self, panel_name, None)
            if panel is None:
                continue
            if hasattr(panel, "set_line_selection_enabled"):
                panel.set_line_selection_enabled(
                    bool(getattr(self, "_image_level_selection_active", False)),
                    reference_axis=str(getattr(self, "_image_level_mode", "horizontal") or "horizontal"),
                )
            panel_crop_rect = self._crop_rect_for_panel(panel) if crop_rect is not None else None
            if hasattr(panel, "set_view_crop_rect"):
                panel.set_view_crop_rect(panel_crop_rect)
            if hasattr(panel, "set_roi_rect"):
                panel.set_roi_rect(rect, label=label)
            if hasattr(panel, "set_overlay_points") and not bool(getattr(self, "_manual_chart_marking", False)):
                panel.set_overlay_points(level_points)

    def _image_crop_reference_size(self) -> tuple[int, int] | None:
        panel = self._viewer_reference_panel() if hasattr(self, "_viewer_reference_panel") else None
        if panel is not None and hasattr(panel, "image_size"):
            size = panel.image_size()
            if isinstance(size, tuple) and len(size) >= 2:
                w, h = int(size[0]), int(size[1])
                if w > 0 and h > 0:
                    return w, h
        source = getattr(self, "_current_result_display_u8", None)
        if source is not None and getattr(source, "ndim", 0) >= 2:
            return int(source.shape[1]), int(source.shape[0])
        return None

    def _normalized_crop_rect(
        self,
        rect: tuple[int, int, int, int] | None,
        base_size: tuple[int, int] | None,
    ) -> tuple[float, float, float, float] | None:
        if rect is None or base_size is None:
            return None
        base_w, base_h = int(base_size[0]), int(base_size[1])
        if base_w <= 0 or base_h <= 0:
            return None
        x, y, w, h = rect
        x0 = max(0.0, min(1.0, float(x) / float(base_w)))
        y0 = max(0.0, min(1.0, float(y) / float(base_h)))
        x1 = max(x0, min(1.0, float(x + w) / float(base_w)))
        y1 = max(y0, min(1.0, float(y + h) / float(base_h)))
        if x1 <= x0 or y1 <= y0:
            return None
        return x0, y0, x1 - x0, y1 - y0

    def _crop_rect_for_panel(self, panel) -> tuple[int, int, int, int] | None:
        rect = getattr(self, "_image_crop_rect", None)
        if rect is None:
            return None
        size = panel.image_size() if hasattr(panel, "image_size") else None
        if not (isinstance(size, tuple) and len(size) >= 2 and int(size[0]) > 0 and int(size[1]) > 0):
            return rect
        panel_w, panel_h = int(size[0]), int(size[1])
        normalized = getattr(self, "_image_crop_normalized_rect", None)
        if normalized is None:
            normalized = self._normalized_crop_rect(rect, getattr(self, "_image_crop_base_size", None))
            self._image_crop_normalized_rect = normalized
        if normalized is None:
            return rect
        nx, ny, nw, nh = (float(v) for v in normalized)
        x0 = int(round(nx * panel_w))
        y0 = int(round(ny * panel_h))
        x1 = int(round((nx + nw) * panel_w))
        y1 = int(round((ny + nh) * panel_h))
        x0 = max(0, min(panel_w - 1, x0))
        y0 = max(0, min(panel_h - 1, y0))
        x1 = max(x0 + 1, min(panel_w, x1))
        y1 = max(y0 + 1, min(panel_h, y1))
        return x0, y0, x1 - x0, y1 - y0

    def _viewer_tool_cursor_active(self) -> bool:
        return bool(getattr(self, "_image_level_selection_active", False))

    def _add_image_adjustment_menu(self, menu_bar) -> None:
        menu_image = menu_bar.addMenu(self.tr("Ajustes de imagen"))
        menu_image.addAction(self._image_crop_action())
        menu_image.addAction(self._action(self.tr("Limpiar recorte"), self._clear_image_crop))
        menu_image.addSeparator()
        menu_image.addAction(self._action(self.tr("Nivelar horizontal"), lambda: self._start_image_level_tool("horizontal")))
        menu_image.addAction(self._action(self.tr("Nivelar vertical"), lambda: self._start_image_level_tool("vertical")))
        menu_image.addAction(self._action(self.tr("Limpiar nivelado"), self._clear_image_level))

    def _image_crop_action(self):
        action = getattr(self, "action_image_crop_select", None)
        if action is None:
            action = self._viewer_action(
                self.tr("Seleccionar recorte"),
                self._toggle_image_crop_selection,
                icon=self._text_badge_icon("Crop"),
                checkable=True,
                tooltip=self.tr("Seleccionar un rectangulo de recorte sobre el visor"),
            )
            self.action_image_crop_select = action
            return action
        action.setIcon(self._text_badge_icon("Crop"))
        action.setToolTip(self.tr("Seleccionar un rectangulo de recorte sobre el visor"))
        action.setStatusTip(self.tr("Seleccionar un rectangulo de recorte sobre el visor"))
        action.setCheckable(True)
        return action

    def _color_picker_action(self):
        action = getattr(self, "action_color_picker_select", None)
        if action is None:
            action = self._viewer_action(
                self.tr("Cuentagotas Lab"),
                self._toggle_color_picker,
                icon=self._text_badge_icon("Lab"),
                checkable=True,
                tooltip=self.tr("Tomar muestras RGB/Lab y comparar contra los perfiles A/B del gamut"),
            )
            self.action_color_picker_select = action
            return action
        action.setIcon(self._text_badge_icon("Lab"))
        action.setToolTip(self.tr("Tomar muestras RGB/Lab y comparar contra los perfiles A/B del gamut"))
        action.setStatusTip(self.tr("Tomar muestras RGB/Lab y comparar contra los perfiles A/B del gamut"))
        action.setCheckable(True)
        return action

    def _image_adjustment_toolbar_actions(self) -> list:
        crop_action = self._image_crop_action()
        crop_action.setText(self.tr("Seleccionar recorte"))
        color_picker_action = self._color_picker_action()
        color_picker_action.setText(self.tr("Cuentagotas Lab"))
        return [
            crop_action,
            color_picker_action,
            self._viewer_action(
                self.tr("Nivelar horizontal"),
                lambda: self._start_image_level_tool("horizontal"),
                icon=self._text_badge_icon("H"),
                tooltip=self.tr("Arrastrar una linea sobre una referencia horizontal"),
            ),
            self._viewer_action(
                self.tr("Nivelar vertical"),
                lambda: self._start_image_level_tool("vertical"),
                icon=self._text_badge_icon("V"),
                tooltip=self.tr("Arrastrar una linea sobre una referencia vertical"),
            ),
        ]
