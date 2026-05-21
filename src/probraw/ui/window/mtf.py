from __future__ import annotations

from dataclasses import replace

from ...analysis.mtf_roi import (
    build_full_resolution_base_roi,
    clip_roi_to_dimensions,
    normalize_full_resolution_image,
    padded_roi as padded_mtf_roi,
    read_base_roi_cache,
    roi_for_analysis_dimensions,
    write_base_roi_cache,
)
from ._imports import *  # noqa: F401,F403


class MTFAnalysisMixin:
    """Sharpness-panel controller for full-resolution slanted-edge analysis.

    The mixin owns UI construction, ROI selection, full-resolution ROI caching,
    background MTF/CA calculation, sidecar persistence, comparison dialogs and
    auto-sharpening. Numeric analysis lives in ``probraw.analysis.mtf`` and plot
    rendering lives in ``MTFPlotWidget``; this class coordinates those layers
    with the main window state and recipe controls.
    """

    MTF_EXTENDED_ANALYSIS_MAX_FREQUENCY = 1.0
    MTF_INTERACTIVE_REFRESH_DELAY_MS = 80
    MTF_SETTLED_REFRESH_DELAY_MS = 45

    def _build_mtf_analysis_panel(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.mtf_graph_tabs = QtWidgets.QTabWidget()
        self.mtf_graph_tabs.setDocumentMode(True)
        self.mtf_plot_esf = MTFPlotWidget("esf")
        self.mtf_plot_lsf = MTFPlotWidget("lsf")
        self.mtf_plot_mtf = MTFPlotWidget("mtf")
        self.mtf_plot_ca = MTFPlotWidget("ca")
        self.mtf_metrics_table = self._make_mtf_result_table()
        self.mtf_context_table = self._make_mtf_result_table()
        self.mtf_details_table = self.mtf_context_table
        self.mtf_graph_tabs.addTab(self.mtf_plot_esf, "ESF")
        self.mtf_graph_tabs.addTab(self.mtf_plot_lsf, "LSF")
        self.mtf_graph_tabs.addTab(self.mtf_plot_mtf, "MTF")
        self.mtf_graph_tabs.addTab(self.mtf_plot_ca, self.tr("CA lateral"))
        self.mtf_graph_tabs.addTab(self.mtf_metrics_table, self.tr("Métricas MTF"))
        self.mtf_graph_tabs.addTab(self.mtf_context_table, self.tr("Contexto técnico"))
        self.mtf_result_tabs = self.mtf_graph_tabs
        self.mtf_graph_tabs.setMinimumHeight(320)
        self.mtf_graph_tabs.setMaximumHeight(430)
        layout.addWidget(self.mtf_graph_tabs, 1)

        tools = QtWidgets.QHBoxLayout()
        self.btn_mtf_select_roi = QtWidgets.QPushButton(self.tr("Seleccionar borde"))
        self.btn_mtf_select_roi.setCheckable(True)
        self.btn_mtf_select_roi.clicked.connect(self._toggle_mtf_roi_selection)
        tools.addWidget(self.btn_mtf_select_roi)
        tools.addWidget(self._button(self.tr("Actualizar"), self._recalculate_mtf_analysis))
        tools.addWidget(self._button(self.tr("Auto nitidez"), self._auto_optimize_mtf_sharpening))
        tools.addWidget(self._button(self.tr("Ampliar"), self._show_mtf_expanded_dialog))
        tools.addWidget(self._button(self.tr("Copiar datos"), self._copy_mtf_analysis_data))
        tools.addWidget(self._button(self.tr("Exportar CSV"), self._export_mtf_analysis_csv))
        tools.addWidget(self._button(self.tr("Limpiar"), self._clear_mtf_roi))
        layout.addLayout(tools)

        options = QtWidgets.QGridLayout()
        self.check_mtf_auto_update = QtWidgets.QCheckBox(self.tr("Actualizar MTF con los ajustes"))
        self.check_mtf_auto_update.setChecked(True)
        options.addWidget(self.check_mtf_auto_update, 0, 0, 1, 2)

        options.addWidget(QtWidgets.QLabel(self.tr("Sensor ancho (mm)")), 1, 0)
        self.spin_mtf_sensor_width_mm = QtWidgets.QDoubleSpinBox()
        self.spin_mtf_sensor_width_mm.setRange(0.0, 200.0)
        self.spin_mtf_sensor_width_mm.setDecimals(3)
        self.spin_mtf_sensor_width_mm.setSingleStep(0.1)
        self.spin_mtf_sensor_width_mm.setSpecialValueText(self.tr("sin dato"))
        self.spin_mtf_sensor_width_mm.valueChanged.connect(self._on_mtf_manual_sensor_size_changed)
        options.addWidget(self.spin_mtf_sensor_width_mm, 1, 1)

        options.addWidget(QtWidgets.QLabel(self.tr("Sensor alto (mm)")), 2, 0)
        self.spin_mtf_sensor_height_mm = QtWidgets.QDoubleSpinBox()
        self.spin_mtf_sensor_height_mm.setRange(0.0, 200.0)
        self.spin_mtf_sensor_height_mm.setDecimals(3)
        self.spin_mtf_sensor_height_mm.setSingleStep(0.1)
        self.spin_mtf_sensor_height_mm.setSpecialValueText(self.tr("sin dato"))
        self.spin_mtf_sensor_height_mm.valueChanged.connect(self._on_mtf_manual_sensor_size_changed)
        options.addWidget(self.spin_mtf_sensor_height_mm, 2, 1)

        options.addWidget(QtWidgets.QLabel(self.tr("Tamaño de píxel (µm)")), 3, 0)
        self.spin_mtf_pixel_pitch_um = QtWidgets.QDoubleSpinBox()
        self.spin_mtf_pixel_pitch_um.setRange(0.0, 50.0)
        self.spin_mtf_pixel_pitch_um.setDecimals(3)
        self.spin_mtf_pixel_pitch_um.setSingleStep(0.1)
        self.spin_mtf_pixel_pitch_um.setSpecialValueText(self.tr("sin dato"))
        self.spin_mtf_pixel_pitch_um.valueChanged.connect(self._on_mtf_pixel_pitch_changed)
        options.addWidget(self.spin_mtf_pixel_pitch_um, 3, 1)
        self.mtf_pixel_pitch_source_label = QtWidgets.QLabel(self.tr("Pitch: pendiente de metadatos"))
        self.mtf_pixel_pitch_source_label.setWordWrap(True)
        self.mtf_pixel_pitch_source_label.setStyleSheet("font-size: 11px; color: #4b5563;")
        options.addWidget(self.mtf_pixel_pitch_source_label, 4, 0, 1, 2)
        layout.addLayout(options)

        self.mtf_progress_panel = self._build_mtf_progress_panel()
        self.mtf_progress_panel.hide()

        self.mtf_metrics_label = QtWidgets.QLabel(self.tr("MTF: selecciona una ROI con un borde inclinado."))
        self.mtf_metrics_label.setWordWrap(True)
        self.mtf_metrics_label.setStyleSheet("font-size: 12px; color: #374151;")
        layout.addWidget(self.mtf_metrics_label)
        return panel

    def _build_mtf_progress_panel(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget()
        panel.setObjectName("mtfProgressPanel")
        panel.setStyleSheet(
            "QWidget#mtfProgressPanel {"
            " background-color: #f8fafc;"
            " border: 1px solid #d1d5db;"
            " border-radius: 4px;"
            "}"
        )
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        self.mtf_progress_label = QtWidgets.QLabel(self.tr("MTF: esperando ROI"))
        self.mtf_progress_label.setWordWrap(True)
        self.mtf_progress_label.setStyleSheet("font-size: 12px; color: #111827; font-weight: 600;")
        layout.addWidget(self.mtf_progress_label)

        self.mtf_progress_time_label = QtWidgets.QLabel(self.tr("Tiempo: --"))
        self.mtf_progress_time_label.setWordWrap(True)
        self.mtf_progress_time_label.setStyleSheet("font-size: 11px; color: #374151;")

        self.mtf_progress_bar = QtWidgets.QProgressBar()
        self.mtf_progress_bar.setTextVisible(False)
        self.mtf_progress_bar.setRange(0, 1)
        self.mtf_progress_bar.setValue(0)
        self.mtf_progress_bar.setMaximumHeight(8)
        layout.addWidget(self.mtf_progress_bar)
        layout.addWidget(self.mtf_progress_time_label)

        self.mtf_phase_label = QtWidgets.QLabel(self._mtf_phase_text("idle"))
        self.mtf_phase_label.setWordWrap(True)
        self.mtf_phase_label.setStyleSheet("font-size: 11px; color: #4b5563;")
        layout.addWidget(self.mtf_phase_label)
        return panel

    def _make_mtf_result_table(self) -> QtWidgets.QTableWidget:
        table = QtWidgets.QTableWidget(0, 2)
        table.setHorizontalHeaderLabels([self.tr("Dato"), self.tr("Valor")])
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        return table

    def _mtf_phase_text(self, stage: str) -> str:
        key = str(stage or "idle")
        if key in {"prepare", "queued"}:
            return self.tr("ROI full-res: activo | MTF: pendiente | Caché: pendiente")
        if key in {"analyze", "auto_sharpen"}:
            return self.tr("ROI full-res: lista | MTF: activo | Caché: lista")
        if key in {"complete", "auto_complete"}:
            return self.tr("ROI full-res: lista | MTF: lista | Caché: lista")
        if key in {"deferred"}:
            return self.tr("ROI full-res: pendiente | MTF: pospuesta | Caché: pendiente")
        if key in {"error"}:
            return self.tr("ROI full-res: error | MTF: detenida | Caché: sin actualizar")
        return self.tr("ROI full-res: pendiente | MTF: pendiente | Caché: pendiente")

    def _mtf_stage_label(self, stage: str) -> str:
        labels = {
            "idle": self.tr("MTF: esperando ROI"),
            "queued": self.tr("MTF: ROI full-res en cola"),
            "prepare": self.tr("MTF: preparando ROI full-res"),
            "analyze": self.tr("MTF: calculando curvas y métricas"),
            "auto_sharpen": self.tr("Auto nitidez: evaluando combinaciones"),
            "complete": self.tr("MTF: análisis completado"),
            "auto_complete": self.tr("Auto nitidez completada"),
            "deferred": self.tr("MTF: recálculo automático pospuesto"),
            "error": self.tr("MTF: análisis detenido"),
        }
        return labels.get(str(stage or "idle"), str(stage or "MTF"))

    def _mtf_format_duration(self, seconds: float | None) -> str:
        if seconds is None:
            return "--"
        value = max(0.0, float(seconds))
        if value < 60.0:
            return f"{value:.1f}s"
        minutes = int(value // 60)
        rest = int(round(value - minutes * 60))
        return f"{minutes}m {rest:02d}s"

    def _mtf_settings_float(self, key: str, default: float) -> float:
        try:
            value = float(self._settings.value(key, default))
        except Exception:
            return float(default)
        return value if np.isfinite(value) and value > 0.0 else float(default)

    def _record_mtf_timing(self, key: str, seconds: float) -> None:
        value = float(seconds)
        if not np.isfinite(value) or value <= 0.0:
            return
        try:
            previous_raw = self._settings.value(key, 0.0)
            previous = float(previous_raw)
        except Exception:
            previous = 0.0
        averaged = value if previous <= 0.0 else previous * 0.65 + value * 0.35
        try:
            self._settings.setValue(key, float(averaged))
            self._settings.sync()
        except Exception:
            pass

    def _mtf_worker_estimate_seconds(self, request: dict[str, Any] | None = None) -> float:
        default = 6.0
        if isinstance(request, dict):
            path = Path(str(request.get("path") or ""))
            if path.suffix.lower() not in RAW_EXTENSIONS:
                default = 1.0
        return self._mtf_settings_float("performance/mtf_fullres_roi_seconds_ewma", default)

    def _mtf_analysis_estimate_seconds(self) -> float:
        return self._mtf_settings_float("performance/mtf_analysis_seconds_ewma", 0.4)

    def _mtf_auto_sharpen_estimate_seconds(self) -> float:
        return self._mtf_settings_float("performance/mtf_auto_sharpen_seconds_ewma", 3.5)

    def _start_mtf_progress(
        self,
        stage: str,
        *,
        detail: str = "",
        estimate_seconds: float | None = None,
        total_steps: int = 0,
    ) -> None:
        self._mtf_progress_started_at = time.perf_counter()
        self._mtf_progress_estimated_seconds = float(estimate_seconds) if estimate_seconds is not None else None
        self._mtf_progress_stage = str(stage)
        self._mtf_progress_detail = str(detail or "")
        self._mtf_progress_current_step = 0
        self._mtf_progress_total_steps = max(0, int(total_steps))
        if stage == "prepare":
            self._mtf_progress_roi_elapsed_seconds = None
        timer = getattr(self, "_mtf_progress_timer", None)
        if timer is not None and not timer.isActive():
            timer.start()
        self._update_mtf_progress_status()

    def _set_mtf_progress_steps(self, current: int, total: int, *, detail: str = "") -> None:
        self._mtf_progress_current_step = max(0, int(current))
        self._mtf_progress_total_steps = max(0, int(total))
        if detail:
            self._mtf_progress_detail = str(detail)
        self._update_mtf_progress_status()

    def _finish_mtf_progress(
        self,
        stage: str = "complete",
        *,
        detail: str = "",
        elapsed_seconds: float | None = None,
    ) -> None:
        timer = getattr(self, "_mtf_progress_timer", None)
        if timer is not None:
            timer.stop()
        started = getattr(self, "_mtf_progress_started_at", None)
        elapsed = (
            float(elapsed_seconds)
            if elapsed_seconds is not None
            else (time.perf_counter() - float(started) if started is not None else None)
        )
        self._mtf_progress_started_at = None
        self._mtf_progress_stage = str(stage)
        self._mtf_progress_detail = str(detail or "")
        self._mtf_progress_current_step = 0
        self._mtf_progress_total_steps = 0
        if hasattr(self, "mtf_progress_label"):
            suffix = f" - {detail}" if detail else ""
            self.mtf_progress_label.setText(self._mtf_stage_label(stage) + suffix)
        if hasattr(self, "mtf_progress_time_label"):
            self.mtf_progress_time_label.setText(self.tr("Total:") + f" {self._mtf_format_duration(elapsed)}")
        if hasattr(self, "mtf_progress_bar"):
            self.mtf_progress_bar.setRange(0, 100)
            self.mtf_progress_bar.setValue(100 if str(stage) not in {"error", "deferred"} else 0)
        if hasattr(self, "mtf_phase_label"):
            self.mtf_phase_label.setText(self._mtf_phase_text(stage))
        self._set_global_operation_progress(
            "mtf",
            self._mtf_stage_label(stage) + (f" - {detail}" if detail else ""),
            time_text=self.tr("Total:") + f" {self._mtf_format_duration(elapsed)}",
            phase_text=self._mtf_phase_text(stage),
            minimum=0,
            maximum=100,
            value=100 if str(stage) not in {"error", "deferred"} else 0,
        )

    def _fail_mtf_progress(self, detail: str = "") -> None:
        self._finish_mtf_progress("error", detail=detail)

    def _reset_mtf_progress(self) -> None:
        timer = getattr(self, "_mtf_progress_timer", None)
        if timer is not None:
            timer.stop()
        self._mtf_progress_started_at = None
        self._mtf_progress_estimated_seconds = None
        self._mtf_progress_stage = "idle"
        self._mtf_progress_detail = ""
        self._mtf_progress_current_step = 0
        self._mtf_progress_total_steps = 0
        self._mtf_progress_roi_elapsed_seconds = None
        if hasattr(self, "mtf_progress_label"):
            self.mtf_progress_label.setText(self._mtf_stage_label("idle"))
        if hasattr(self, "mtf_progress_time_label"):
            self.mtf_progress_time_label.setText(self.tr("Tiempo: --"))
        if hasattr(self, "mtf_progress_bar"):
            self.mtf_progress_bar.setRange(0, 1)
            self.mtf_progress_bar.setValue(0)
        if hasattr(self, "mtf_phase_label"):
            self.mtf_phase_label.setText(self._mtf_phase_text("idle"))
        self._reset_global_operation_progress(owner="mtf")

    def _update_mtf_progress_status(self) -> None:
        if not hasattr(self, "mtf_progress_label"):
            return
        stage = str(getattr(self, "_mtf_progress_stage", "idle") or "idle")
        detail = str(getattr(self, "_mtf_progress_detail", "") or "")
        started = getattr(self, "_mtf_progress_started_at", None)
        elapsed = max(0.0, time.perf_counter() - float(started)) if started is not None else 0.0
        total_steps = int(getattr(self, "_mtf_progress_total_steps", 0) or 0)
        current_step = int(getattr(self, "_mtf_progress_current_step", 0) or 0)
        estimate = getattr(self, "_mtf_progress_estimated_seconds", None)
        label = self._mtf_stage_label(stage)
        if detail:
            label = f"{label} - {detail}"
        self.mtf_progress_label.setText(label)
        phase_text = self._mtf_phase_text(stage)
        if hasattr(self, "mtf_phase_label"):
            self.mtf_phase_label.setText(phase_text)
        progress_min = 0
        progress_max = 1
        progress_value = 0
        if hasattr(self, "mtf_progress_bar"):
            if total_steps > 0:
                progress_max = total_steps
                progress_value = int(np.clip(current_step, 0, total_steps))
                self.mtf_progress_bar.setRange(progress_min, progress_max)
                self.mtf_progress_bar.setValue(progress_value)
            elif estimate is not None and estimate > 0:
                progress_max = 100
                progress_value = (
                    95
                    if elapsed > float(estimate)
                    else int(np.clip((elapsed / float(estimate)) * 90.0, 0.0, 90.0))
                )
                self.mtf_progress_bar.setRange(progress_min, progress_max)
                self.mtf_progress_bar.setValue(progress_value)
            elif started is not None:
                progress_min = 0
                progress_max = 0
                progress_value = 0
                self.mtf_progress_bar.setRange(progress_min, progress_max)
            else:
                self.mtf_progress_bar.setRange(progress_min, progress_max)
                self.mtf_progress_bar.setValue(progress_value)
        time_text = self.tr("Tiempo: --")
        if started is not None:
            if total_steps > 0:
                time_text = (
                    self.tr("Paso")
                    + f" {min(current_step, total_steps)}/{total_steps} | "
                    + self.tr("transcurrido")
                    + f" {self._mtf_format_duration(elapsed)}"
                )
            elif estimate is not None and estimate > 0:
                remaining = max(0.0, float(estimate) - elapsed)
                suffix = (
                    self.tr("superando estimación")
                    if elapsed > float(estimate) * 1.15
                    else self.tr("restante")
                    + f" {self._mtf_format_duration(remaining)}"
                )
                time_text = (
                    self.tr("Transcurrido")
                    + f" {self._mtf_format_duration(elapsed)} | "
                    + self.tr("estimado")
                    + f" ~{self._mtf_format_duration(float(estimate))} | {suffix}"
                )
            else:
                time_text = self.tr("Transcurrido") + f" {self._mtf_format_duration(elapsed)}"
        if hasattr(self, "mtf_progress_time_label"):
            self.mtf_progress_time_label.setText(time_text)
        self._set_global_operation_progress(
            "mtf",
            label,
            time_text=time_text,
            phase_text=phase_text,
            minimum=progress_min,
            maximum=progress_max,
            value=progress_value,
        )

    def _auto_update_mtf_pixel_pitch_from_file(self, path: Path | None = None) -> None:
        selected = path or getattr(self, "_selected_file", None)
        if selected is None or self._original_linear is None:
            return
        try:
            h, w = int(self._original_linear.shape[0]), int(self._original_linear.shape[1])
        except Exception:
            h, w = 0, 0
        image_dimensions = self._mtf_analysis_image_dimensions()
        if image_dimensions is None and self._effective_preview_max_side() <= 0 and w and h:
            image_dimensions = (w, h)
        try:
            estimated = estimate_pixel_pitch_um(Path(selected), image_dimensions=image_dimensions)
        except Exception:
            estimated = None
        if estimated is None:
            if self._apply_mtf_manual_sensor_size_pitch():
                return
            if (
                getattr(self, "_mtf_pixel_pitch_auto_source", None) == "manual_pixel_pitch"
                and hasattr(self, "spin_mtf_pixel_pitch_um")
                and self.spin_mtf_pixel_pitch_um.value() > 0.0
            ):
                if hasattr(self, "mtf_pixel_pitch_source_label"):
                    self.mtf_pixel_pitch_source_label.setText(self.tr("Pitch: manual"))
                self._update_mtf_result_widgets()
                return
            if hasattr(self, "spin_mtf_pixel_pitch_um"):
                self.spin_mtf_pixel_pitch_um.blockSignals(True)
                self.spin_mtf_pixel_pitch_um.setValue(0.0)
                self.spin_mtf_pixel_pitch_um.blockSignals(False)
            self._mtf_pixel_pitch_auto_source = None
            if hasattr(self, "mtf_pixel_pitch_source_label"):
                self.mtf_pixel_pitch_source_label.setText(self.tr("Pitch: no disponible en metadatos"))
            self._update_mtf_result_widgets()
            return
        pitch, source = estimated
        if hasattr(self, "spin_mtf_pixel_pitch_um"):
            self.spin_mtf_pixel_pitch_um.blockSignals(True)
            self.spin_mtf_pixel_pitch_um.setValue(float(pitch))
            self.spin_mtf_pixel_pitch_um.blockSignals(False)
        self._mtf_pixel_pitch_auto_source = str(source)
        if hasattr(self, "mtf_pixel_pitch_source_label"):
            self.mtf_pixel_pitch_source_label.setText(
                self.tr("Pitch estimado desde metadatos") + f": {float(pitch):.3f} µm ({self._mtf_pitch_source_label(source)})"
            )
        self._update_mtf_result_widgets()

    def _on_mtf_pixel_pitch_changed(self, value: float) -> None:
        self._mtf_pixel_pitch_auto_source = "manual_pixel_pitch" if float(value) > 0.0 else None
        if hasattr(self, "mtf_pixel_pitch_source_label"):
            if float(value) > 0.0:
                self.mtf_pixel_pitch_source_label.setText(self.tr("Pitch: manual"))
            else:
                self.mtf_pixel_pitch_source_label.setText(self.tr("Pitch: pendiente de metadatos"))
        self._update_mtf_result_widgets()

    def _on_mtf_manual_sensor_size_changed(self, _value: float) -> None:
        if self._apply_mtf_manual_sensor_size_pitch():
            return
        if getattr(self, "_mtf_pixel_pitch_auto_source", None) == "manual_sensor_size":
            self._mtf_pixel_pitch_auto_source = None
            if hasattr(self, "spin_mtf_pixel_pitch_um"):
                self.spin_mtf_pixel_pitch_um.blockSignals(True)
                self.spin_mtf_pixel_pitch_um.setValue(0.0)
                self.spin_mtf_pixel_pitch_um.blockSignals(False)
            if hasattr(self, "mtf_pixel_pitch_source_label"):
                self.mtf_pixel_pitch_source_label.setText(self.tr("Pitch: pendiente de metadatos"))
            self._update_mtf_result_widgets()

    def _apply_mtf_manual_sensor_size_pitch(self) -> bool:
        dimensions = self._mtf_analysis_image_dimensions()
        if dimensions is None and self._effective_preview_max_side() <= 0:
            dimensions = self._mtf_current_image_dimensions()
        if dimensions is None or not hasattr(self, "spin_mtf_pixel_pitch_um"):
            return False
        width_px, height_px = dimensions
        sensor_width = self.spin_mtf_sensor_width_mm.value() if hasattr(self, "spin_mtf_sensor_width_mm") else 0.0
        sensor_height = self.spin_mtf_sensor_height_mm.value() if hasattr(self, "spin_mtf_sensor_height_mm") else 0.0
        candidates: list[float] = []
        if sensor_width > 0.0 and width_px > 0:
            candidates.append(float(sensor_width) * 1000.0 / float(width_px))
        if sensor_height > 0.0 and height_px > 0:
            candidates.append(float(sensor_height) * 1000.0 / float(height_px))
        candidates = [value for value in candidates if 0.1 <= value <= 50.0]
        if not candidates:
            return False
        pitch = float(sum(candidates) / len(candidates))
        self.spin_mtf_pixel_pitch_um.blockSignals(True)
        self.spin_mtf_pixel_pitch_um.setValue(pitch)
        self.spin_mtf_pixel_pitch_um.blockSignals(False)
        self._mtf_pixel_pitch_auto_source = "manual_sensor_size"
        if hasattr(self, "mtf_pixel_pitch_source_label"):
            self.mtf_pixel_pitch_source_label.setText(
                self.tr("Pitch calculado desde sensor manual")
                + f": {pitch:.3f} µm ({width_px}x{height_px} px)"
            )
        self._update_mtf_result_widgets()
        return True

    def _mtf_current_image_dimensions(self) -> tuple[int, int] | None:
        image = getattr(self, "_original_linear", None)
        if image is None:
            image = self._mtf_source_image()
        if image is None:
            return None
        try:
            height, width = int(image.shape[0]), int(image.shape[1])
        except Exception:
            return None
        if width <= 0 or height <= 0:
            return None
        return width, height

    def _mtf_analysis_image_dimensions(self) -> tuple[int, int] | None:
        dimensions = getattr(self, "_mtf_last_analysis_image_dimensions", None)
        if isinstance(dimensions, (list, tuple)) and len(dimensions) >= 2:
            try:
                width = int(dimensions[0])
                height = int(dimensions[1])
            except (TypeError, ValueError):
                return None
            if width > 0 and height > 0:
                return width, height
        return None

    def _mtf_pitch_source_label(self, source: str) -> str:
        labels = {
            "sensor_width_height": self.tr("tamaño de sensor"),
            "sensor_width": self.tr("anchura de sensor"),
            "sensor_height": self.tr("altura de sensor"),
            "focal_plane_resolution": self.tr("resolución de plano focal"),
            "35mm_equivalent": self.tr("equivalencia 35 mm"),
            "manual_pixel_pitch": self.tr("manual"),
            "manual_sensor_size": self.tr("sensor manual"),
            "sidecar": self.tr("sidecar"),
        }
        return labels.get(str(source), str(source))

    def _toggle_mtf_roi_selection(self, checked: bool = False) -> None:
        if checked and self._original_linear is None:
            self._set_mtf_roi_selection_active(False)
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("Carga primero una imagen en el visor."))
            return
        self._set_mtf_roi_selection_active(bool(checked))
        if checked:
            self._manual_chart_marking = False
            self._set_neutral_picker_active(False)
            if hasattr(self, "_set_color_picker_active"):
                self._set_color_picker_active(False)
            if hasattr(self, "_sync_manual_chart_overlay"):
                self._sync_manual_chart_overlay()
            self._set_status(self.tr("MTF: arrastra un rectángulo alrededor de un borde inclinado"))
        else:
            self._set_status(self.tr("Selección MTF desactivada"))

    def _set_mtf_roi_selection_active(self, active: bool) -> None:
        if active and hasattr(self, "_set_image_crop_selection_active"):
            self._set_image_crop_selection_active(False)
        self._mtf_roi_selection_active = bool(active)
        if hasattr(self, "btn_mtf_select_roi"):
            self.btn_mtf_select_roi.blockSignals(True)
            self.btn_mtf_select_roi.setChecked(self._mtf_roi_selection_active)
            self.btn_mtf_select_roi.blockSignals(False)
        for panel_name in ("image_result_single", "image_result_compare"):
            panel = getattr(self, panel_name, None)
            if panel is not None and hasattr(panel, "set_roi_selection_enabled"):
                panel.set_roi_selection_enabled(
                    self._mtf_roi_selection_active or bool(getattr(self, "_image_crop_selection_active", False))
                )
        self._sync_mtf_roi_overlay()

    def _on_mtf_roi_selected(self, x: float, y: float, width: float, height: float) -> None:
        self._mtf_roi = (
            int(round(float(x))),
            int(round(float(y))),
            int(round(float(width))),
            int(round(float(height))),
        )
        self._set_mtf_roi_selection_active(False)
        self._sync_mtf_roi_overlay()
        self._recalculate_mtf_analysis()

    def _sync_mtf_roi_overlay(self) -> None:
        if hasattr(self, "_sync_image_tool_overlays"):
            self._sync_image_tool_overlays()
            return
        rect = self._mtf_roi if self._mtf_roi_overlay_should_be_visible() else None
        for panel_name in ("image_result_single", "image_result_compare"):
            panel = getattr(self, panel_name, None)
            if panel is not None and hasattr(panel, "set_roi_rect"):
                panel.set_roi_rect(rect, label="MTF")

    def _mtf_roi_overlay_should_be_visible(self) -> bool:
        if getattr(self, "_mtf_roi", None) is None:
            return False
        if bool(getattr(self, "_mtf_roi_selection_active", False)):
            return True
        main_tabs = getattr(self, "main_tabs", None)
        right_tabs = getattr(self, "right_workflow_tabs", None)
        if main_tabs is None or right_tabs is None:
            return False
        try:
            if int(main_tabs.currentIndex()) != 1:
                return False
            return right_tabs.tabText(right_tabs.currentIndex()) == self.tr("Nitidez")
        except Exception:
            return False

    def _on_mtf_context_visibility_changed(self, _index: int | None = None) -> None:
        mtf_visible = self._mtf_roi_overlay_should_be_visible()
        if not mtf_visible and bool(getattr(self, "_mtf_roi_selection_active", False)):
            self._set_mtf_roi_selection_active(False)
        if not mtf_visible:
            timer = getattr(self, "_mtf_refresh_timer", None)
            if timer is not None and timer.isActive():
                timer.stop()
                self._mtf_auto_refresh_deferred_until_visible = True
        elif bool(getattr(self, "_mtf_auto_refresh_deferred_until_visible", False)):
            self._mtf_auto_refresh_deferred_until_visible = False
            self._schedule_mtf_refresh(interactive=False, require_auto_update=False)
        elif mtf_visible:
            self._ensure_mtf_analysis_ready_for_sharpness_panel()
        self._sync_mtf_roi_overlay()

    def _clear_mtf_roi(self) -> None:
        self._mtf_roi = None
        self._mtf_last_result = None
        self._mtf_last_analysis_image_dimensions = None
        self._mtf_last_display_dimensions = None
        self._mtf_last_display_roi = None
        self._clear_mtf_image_caches()
        self._reset_mtf_progress()
        self._set_mtf_roi_selection_active(False)
        for panel_name in ("image_result_single", "image_result_compare"):
            panel = getattr(self, panel_name, None)
            if panel is not None and hasattr(panel, "clear_roi_rect"):
                panel.clear_roi_rect()
        self._update_mtf_result_widgets()

    def _clear_mtf_roi_for_file_change(self) -> None:
        self._clear_mtf_image_caches()
        if (
            getattr(self, "_mtf_roi", None) is not None
            or getattr(self, "_mtf_last_result", None) is not None
            or bool(getattr(self, "_mtf_roi_selection_active", False))
        ):
            self._clear_mtf_roi()

    def _restore_persisted_mtf_analysis_for_selected(self, path: Path | None = None) -> None:
        selected = path or getattr(self, "_selected_file", None)
        if selected is None:
            return
        payload = self._load_persisted_mtf_analysis(Path(selected))
        if payload is None:
            return
        result = self._mtf_result_from_payload(payload)
        if result is None:
            return
        summary = self._mtf_payload_summary(payload)
        analysis_dimensions = self._mtf_payload_dimensions(summary.get("image_dimensions_px"))
        stored_display_dimensions = self._mtf_payload_dimensions(summary.get("display_dimensions_px"))
        current_display_dimensions = self._mtf_current_image_dimensions()
        display_dimensions = current_display_dimensions or stored_display_dimensions
        stored_display_roi = self._mtf_payload_roi(summary.get("display_roi"))
        display_roi = None
        if (
            stored_display_roi is not None
            and stored_display_dimensions is not None
            and current_display_dimensions == stored_display_dimensions
        ):
            display_roi = stored_display_roi
        if display_roi is None:
            display_roi = self._mtf_display_roi_from_analysis_roi(result.roi, analysis_dimensions)
        if display_roi == result.roi and current_display_dimensions is None and stored_display_roi is not None:
            display_roi = stored_display_roi
        self._restore_mtf_pixel_pitch_from_payload(payload)
        self._mtf_last_analysis_image_dimensions = analysis_dimensions
        self._mtf_last_display_dimensions = display_dimensions
        self._mtf_last_display_roi = display_roi
        self._mtf_roi = display_roi
        self._mtf_last_result = result
        self._set_mtf_roi_selection_active(False)
        self._sync_mtf_roi_overlay()
        self._update_mtf_result_widgets()
        self._set_status(self.tr("MTF recuperada del sidecar:") + f" {Path(selected).name}")

    def _mtf_result_from_payload(self, payload: dict[str, Any]) -> MTFResult | None:
        summary = self._mtf_payload_summary(payload)
        roi = self._mtf_payload_roi(summary.get("roi"))
        if roi is None:
            return None
        roi_shape = self._mtf_payload_roi_shape(summary.get("roi_shape"), roi)
        curves = payload.get("curves") if isinstance(payload.get("curves"), dict) else {}
        esf_distance, esf = self._mtf_payload_curve(curves.get("esf"), "distance_px", "signal")
        lsf_distance, lsf = self._mtf_payload_curve(curves.get("lsf"), "distance_px", "derivative")
        frequency, mtf = self._mtf_payload_curve(curves.get("mtf"), "frequency_cycles_per_pixel", "modulation")
        frequency_extended, mtf_extended = self._mtf_payload_curve(
            curves.get("mtf_extended"),
            "frequency_cycles_per_pixel",
            "modulation",
        )
        ca_distance, ca_red, ca_green, ca_blue, ca_diff = self._mtf_payload_ca_curve(curves.get("chromatic_aberration"))
        ca_pixel_distance, ca_pixel_red, ca_pixel_green, ca_pixel_blue = self._mtf_payload_ca_pixel_strip(curves.get("chromatic_aberration_pixels"))
        ca_summary = summary.get("chromatic_aberration") if isinstance(summary.get("chromatic_aberration"), dict) else {}
        warnings_value = summary.get("warnings")
        warnings = [str(value) for value in warnings_value] if isinstance(warnings_value, list) else []
        return MTFResult(
            roi=roi,
            roi_shape=roi_shape,
            edge_angle_degrees=self._mtf_payload_float(summary.get("edge_angle_degrees"), default=0.0),
            edge_contrast=self._mtf_payload_float(summary.get("edge_contrast"), default=0.0),
            overshoot=self._mtf_payload_float(summary.get("overshoot"), default=0.0),
            undershoot=self._mtf_payload_float(summary.get("undershoot"), default=0.0),
            mtf50=self._mtf_payload_optional_float(summary.get("mtf50")),
            mtf50p=self._mtf_payload_optional_float(summary.get("mtf50p")),
            mtf30=self._mtf_payload_optional_float(summary.get("mtf30")),
            mtf10=self._mtf_payload_optional_float(summary.get("mtf10")),
            acutance=self._mtf_payload_float(summary.get("acutance"), default=0.0),
            esf_distance=esf_distance,
            esf=esf,
            lsf_distance=lsf_distance,
            lsf=lsf,
            frequency=frequency,
            mtf=mtf,
            frequency_extended=frequency_extended,
            mtf_extended=mtf_extended,
            warnings=warnings,
            ca_distance=ca_distance,
            ca_red=ca_red,
            ca_green=ca_green,
            ca_blue=ca_blue,
            ca_diff=ca_diff,
            ca_pixel_distance=ca_pixel_distance,
            ca_pixel_red=ca_pixel_red,
            ca_pixel_green=ca_pixel_green,
            ca_pixel_blue=ca_pixel_blue,
            ca_area_pixels=self._mtf_payload_optional_float(ca_summary.get("area_pixels")),
            ca_crossing_pixels=self._mtf_payload_optional_float(ca_summary.get("crossing_pixels")),
            ca_red_green_shift_pixels=self._mtf_payload_optional_float(ca_summary.get("red_green_shift_pixels")),
            ca_blue_green_shift_pixels=self._mtf_payload_optional_float(ca_summary.get("blue_green_shift_pixels")),
            ca_red_blue_shift_pixels=self._mtf_payload_optional_float(ca_summary.get("red_blue_shift_pixels")),
            ca_edge_width_10_90_pixels=self._mtf_payload_optional_float(ca_summary.get("edge_width_10_90_pixels")),
        )

    def _restore_mtf_pixel_pitch_from_payload(self, payload: dict[str, Any]) -> None:
        if not hasattr(self, "spin_mtf_pixel_pitch_um"):
            return
        summary = self._mtf_payload_summary(payload)
        pitch = self._mtf_payload_optional_float(summary.get("pixel_pitch_um"))
        if pitch is None or pitch <= 0.0:
            return
        source = summary.get("pixel_pitch_source")
        self.spin_mtf_pixel_pitch_um.blockSignals(True)
        self.spin_mtf_pixel_pitch_um.setValue(float(pitch))
        self.spin_mtf_pixel_pitch_um.blockSignals(False)
        self._mtf_pixel_pitch_auto_source = str(source) if source else "sidecar"
        if hasattr(self, "mtf_pixel_pitch_source_label"):
            self.mtf_pixel_pitch_source_label.setText(
                self.tr("Pitch recuperado de MTF guardada")
                + f": {float(pitch):.3f} µm ({self._mtf_pitch_source_label(self._mtf_pixel_pitch_auto_source)})"
            )

    def _mtf_payload_roi(self, value: Any) -> tuple[int, int, int, int] | None:
        if not isinstance(value, (list, tuple)) or len(value) != 4:
            return None
        try:
            x, y, width, height = [int(round(float(v))) for v in value]
        except (TypeError, ValueError):
            return None
        if width <= 0 or height <= 0:
            return None
        return x, y, width, height

    def _mtf_payload_roi_shape(self, value: Any, roi: tuple[int, int, int, int]) -> tuple[int, int]:
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            try:
                height = int(round(float(value[0])))
                width = int(round(float(value[1])))
                if height > 0 and width > 0:
                    return height, width
            except (TypeError, ValueError):
                pass
        return int(roi[3]), int(roi[2])

    def _mtf_payload_dimensions(self, value: Any) -> tuple[int, int] | None:
        if not isinstance(value, (list, tuple)) or len(value) < 2:
            return None
        try:
            width = int(round(float(value[0])))
            height = int(round(float(value[1])))
        except (TypeError, ValueError):
            return None
        if width <= 0 or height <= 0:
            return None
        return width, height

    def _mtf_payload_curve(self, value: Any, x_key: str, y_key: str) -> tuple[list[float], list[float]]:
        if not isinstance(value, list):
            return [], []
        x_values: list[float] = []
        y_values: list[float] = []
        for point in value:
            if not isinstance(point, dict):
                continue
            x = self._mtf_payload_optional_float(point.get(x_key))
            y = self._mtf_payload_optional_float(point.get(y_key))
            if x is None or y is None:
                continue
            x_values.append(x)
            y_values.append(y)
        return x_values, y_values

    def _mtf_payload_ca_curve(self, value: Any) -> tuple[list[float], list[float], list[float], list[float], list[float]]:
        if not isinstance(value, list):
            return [], [], [], [], []
        distance: list[float] = []
        red: list[float] = []
        green: list[float] = []
        blue: list[float] = []
        diff: list[float] = []
        for point in value:
            if not isinstance(point, dict):
                continue
            x = self._mtf_payload_optional_float(point.get("distance_px"))
            r = self._mtf_payload_optional_float(point.get("red"))
            g = self._mtf_payload_optional_float(point.get("green"))
            b = self._mtf_payload_optional_float(point.get("blue"))
            d = self._mtf_payload_optional_float(point.get("difference"))
            if x is None or r is None or g is None or b is None or d is None:
                continue
            distance.append(x)
            red.append(r)
            green.append(g)
            blue.append(b)
            diff.append(d)
        return distance, red, green, blue, diff

    def _mtf_payload_ca_pixel_strip(self, value: Any) -> tuple[list[float], list[float], list[float], list[float]]:
        if not isinstance(value, list):
            return [], [], [], []
        distance: list[float] = []
        red: list[float] = []
        green: list[float] = []
        blue: list[float] = []
        for point in value:
            if not isinstance(point, dict):
                continue
            x = self._mtf_payload_optional_float(point.get("distance_px"))
            r = self._mtf_payload_optional_float(point.get("red"))
            g = self._mtf_payload_optional_float(point.get("green"))
            b = self._mtf_payload_optional_float(point.get("blue"))
            if x is None or r is None or g is None or b is None:
                continue
            distance.append(x)
            red.append(r)
            green.append(g)
            blue.append(b)
        return distance, red, green, blue

    def _mtf_payload_float(self, value: Any, *, default: float) -> float:
        parsed = self._mtf_payload_optional_float(value)
        return float(default) if parsed is None else parsed

    def _mtf_payload_optional_float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if np.isfinite(number) else None

    def _mtf_source_image(self) -> np.ndarray | None:
        if self._preview_srgb is not None:
            return np.asarray(self._preview_srgb, dtype=np.float32)
        if self._adjusted_linear is not None:
            return linear_to_srgb_display(self._adjusted_linear)
        if self._original_linear is not None:
            return linear_to_srgb_display(self._original_linear)
        return None

    def _clear_mtf_image_caches(self) -> None:
        timer = getattr(self, "_mtf_refresh_timer", None)
        if timer is not None:
            timer.stop()
        self._mtf_base_roi_pending_request = None
        self._mtf_roi_base_cache_key = None
        self._mtf_roi_base_cache = None
        self._mtf_roi_pre_sharpen_cache_key = None
        self._mtf_roi_pre_sharpen_cache = None
        self._mtf_roi_analysis_cache_key = None
        self._mtf_roi_analysis_cache = None
        self._mtf_result_cache_key = None
        self._mtf_result_cache = None
        self._mtf_deferred_auto_refresh_key = None
        if hasattr(self, "_mtf_auto_candidate_cache"):
            self._mtf_auto_candidate_cache.clear()
        if hasattr(self, "_mtf_auto_candidate_cache_order"):
            self._mtf_auto_candidate_cache_order.clear()

    def _mtf_selected_source_context(self) -> tuple[Path, Recipe | None, str] | None:
        selected = getattr(self, "_selected_file", None)
        if selected is None:
            return None
        path = Path(selected).expanduser()
        if not path.exists() or not path.is_file():
            return None
        recipe = self._build_effective_recipe() if path.suffix.lower() in RAW_EXTENSIONS else None
        return path, recipe, self._mtf_full_resolution_source_key(path, recipe)

    def _mtf_full_resolution_source_key(self, path: Path, recipe: Recipe | None) -> str:
        try:
            st = path.stat()
            stamp = f"{st.st_mtime_ns}:{st.st_size}"
        except Exception:
            stamp = "nostat"
        if recipe is None:
            recipe_sig = "nonraw"
        else:
            try:
                recipe_sig = json.dumps(to_json_dict(recipe), sort_keys=True, ensure_ascii=False, default=str)
            except Exception:
                recipe_sig = repr(recipe)
        return f"{self._cache_path_identity(path)}|{stamp}|mtf-fullres-roi-v1|{recipe_sig}"

    def _mtf_cache_token(self, value: Any) -> str:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))

    @staticmethod
    def _run_mtf_analysis_inline() -> bool:
        # Unit tests need deterministic results immediately after selecting a ROI.
        return bool(
            os.environ.get("PYTEST_CURRENT_TEST")
            or os.environ.get("PROBRAW_SYNC_MTF")
        )

    def _mtf_base_roi_disk_cache_path(
        self,
        key: str,
        *,
        base_dir: Path | None = None,
        path: Path | None = None,
    ) -> Path:
        return self._disk_cache_path(base_dir or self._disk_cache_dirs(path, "mtf-roi")[0], key, ".npz")

    def _read_mtf_base_roi_from_disk_cache(
        self,
        key: str,
        *,
        path: Path | None = None,
    ) -> dict[str, Any] | None:
        for cache_dir in self._disk_cache_dirs(path, "mtf-roi"):
            cache_path = self._mtf_base_roi_disk_cache_path(key, base_dir=cache_dir)
            if not cache_path.is_file():
                continue
            try:
                payload = read_base_roi_cache(cache_path)
                try:
                    os.utime(cache_path, None)
                except Exception:
                    pass
                return payload
            except Exception:
                continue
        return None

    def _write_mtf_base_roi_to_disk_cache(
        self,
        key: str,
        payload: dict[str, Any],
        *,
        path: Path | None = None,
    ) -> None:
        try:
            cache_dir = self._disk_cache_dirs(path, "mtf-roi")[0]
            cache_path = self._mtf_base_roi_disk_cache_path(key, base_dir=cache_dir)
            write_base_roi_cache(cache_path, payload)
            self._prune_disk_cache(
                cache_dir,
                pattern="*.npz",
                max_entries=MTF_ROI_DISK_CACHE_MAX_ENTRIES,
                max_bytes=MTF_ROI_DISK_CACHE_MAX_BYTES,
            )
        except Exception:
            return

    def _set_mtf_base_roi_cache(self, cache_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)
        normalized["image"] = np.ascontiguousarray(np.asarray(payload["image"], dtype=np.float32)[..., :3]).copy()
        normalized["cache_key"] = cache_key
        self._mtf_roi_base_cache_key = cache_key
        self._mtf_roi_base_cache = normalized
        self._mtf_roi_pre_sharpen_cache_key = None
        self._mtf_roi_pre_sharpen_cache = None
        self._mtf_roi_analysis_cache_key = None
        self._mtf_roi_analysis_cache = None
        self._mtf_result_cache_key = None
        self._mtf_result_cache = None
        self._mtf_deferred_auto_refresh_key = None
        return normalized

    def _mtf_normalize_full_resolution_image(self, image: np.ndarray) -> np.ndarray:
        return normalize_full_resolution_image(image)

    def _mtf_full_resolution_base_image(
        self,
        path: Path | None = None,
        recipe: Recipe | None = None,
    ) -> np.ndarray | None:
        if path is None:
            context = self._mtf_selected_source_context()
            if context is None:
                return None
            path, recipe, _source_key = context
        if path.suffix.lower() in RAW_EXTENSIONS:
            recipe = recipe or self._build_effective_recipe()
            if is_standard_output_space(recipe.output_space):
                image = develop_standard_output_array(path, recipe, half_size=False)
            else:
                image = develop_image_array(path, recipe, half_size=False)
        else:
            image = read_image(path)
        return self._mtf_normalize_full_resolution_image(image)

    def _mtf_detail_adjustment_kwargs(self) -> dict[str, float]:
        if hasattr(self, "_detail_adjustment_state") and hasattr(self, "_detail_adjustment_kwargs_from_state"):
            state = self._detail_adjustment_state()
            detail = self._detail_adjustment_kwargs_from_state(state)
            return {
                "denoise_luminance": float(detail.get("denoise_luma", 0.0)),
                "denoise_color": float(detail.get("denoise_color", 0.0)),
                "sharpen_amount": float(detail.get("sharpen_amount", 0.0)),
                "sharpen_radius": float(detail.get("sharpen_radius", 1.0)),
                "lateral_ca_red_scale": float(detail.get("lateral_ca_red_scale", 1.0)),
                "lateral_ca_blue_scale": float(detail.get("lateral_ca_blue_scale", 1.0)),
            }
        nl = self.slider_noise_luma.value() / 100.0 if hasattr(self, "slider_noise_luma") else 0.0
        nc = self.slider_noise_color.value() / 100.0 if hasattr(self, "slider_noise_color") else 0.0
        sharpen = self.slider_sharpen.value() / 100.0 if hasattr(self, "slider_sharpen") else 0.0
        radius = self.slider_radius.value() / 10.0 if hasattr(self, "slider_radius") else 1.0
        ca_red, ca_blue = self._ca_scale_factors() if hasattr(self, "_ca_scale_factors") else (1.0, 1.0)
        return {
            "denoise_luminance": float(nl),
            "denoise_color": float(nc),
            "sharpen_amount": float(sharpen),
            "sharpen_radius": float(radius),
            "lateral_ca_red_scale": float(ca_red),
            "lateral_ca_blue_scale": float(ca_blue),
        }

    def _mtf_effective_detail_cache_state(self) -> dict[str, Any]:
        if hasattr(self, "_detail_adjustment_state"):
            detail = dict(self._detail_adjustment_state())
            if int(detail.get("sharpen", 0)) <= 0:
                detail["radius"] = 0
            return detail
        detail_kwargs = dict(self._mtf_detail_adjustment_kwargs())
        if float(detail_kwargs.get("sharpen_amount", 0.0)) <= 0.0:
            detail_kwargs["sharpen_radius"] = 0.0
        return detail_kwargs

    def _mtf_adjustment_cache_state(self) -> dict[str, Any]:
        return {
            "detail": self._mtf_effective_detail_cache_state(),
            "render": self._render_adjustment_state() if hasattr(self, "_render_adjustment_state") else {},
        }

    def _mtf_lateral_ca_adjustment_active(self, detail_kwargs: dict[str, float] | None = None) -> bool:
        detail = detail_kwargs or self._mtf_detail_adjustment_kwargs()
        return (
            abs(float(detail.get("lateral_ca_red_scale", 1.0)) - 1.0) > 1e-5
            or abs(float(detail.get("lateral_ca_blue_scale", 1.0)) - 1.0) > 1e-5
        )

    def _mtf_pre_sharpen_detail_active(self, detail_kwargs: dict[str, float]) -> bool:
        return (
            float(detail_kwargs.get("denoise_luminance", 0.0)) > 0.0
            or float(detail_kwargs.get("denoise_color", 0.0)) > 0.0
        )

    def _mtf_sharpen_detail_active(self, detail_kwargs: dict[str, float]) -> bool:
        return float(detail_kwargs.get("sharpen_amount", 0.0)) > 0.0

    def _mtf_pre_sharpen_kwargs(self, detail_kwargs: dict[str, float]) -> dict[str, float]:
        return {
            "denoise_luminance": float(detail_kwargs.get("denoise_luminance", 0.0)),
            "denoise_color": float(detail_kwargs.get("denoise_color", 0.0)),
            "sharpen_amount": 0.0,
            "sharpen_radius": 1.0,
            "lateral_ca_red_scale": 1.0,
            "lateral_ca_blue_scale": 1.0,
        }

    def _mtf_sharpen_kwargs(self, detail_kwargs: dict[str, float]) -> dict[str, float]:
        return {
            "denoise_luminance": 0.0,
            "denoise_color": 0.0,
            "sharpen_amount": float(detail_kwargs.get("sharpen_amount", 0.0)),
            "sharpen_radius": float(detail_kwargs.get("sharpen_radius", 1.0)),
            "lateral_ca_red_scale": 1.0,
            "lateral_ca_blue_scale": 1.0,
        }

    def _mtf_roi_block_padding_px(self) -> int:
        # Keep enough surrounding pixels so Gaussian denoise/sharpen matches
        # the full-frame result inside the ROI. The floor also covers the
        # current +/-1% lateral-CA slider range on large sensors.
        radius_max = 8.0
        if hasattr(self, "slider_radius"):
            try:
                radius_max = max(radius_max, float(self.slider_radius.maximum()) / 10.0)
            except Exception:
                pass
        noise_luma_max = 0.2 + 3.2
        noise_color_max = 0.2 + 3.8
        filter_sigma = max(radius_max, noise_luma_max, noise_color_max)
        return int(max(128, np.ceil(filter_sigma * 6.0) + 8))

    def _mtf_clip_roi_to_dimensions(
        self,
        roi: tuple[int, int, int, int],
        dimensions: tuple[int, int],
    ) -> tuple[int, int, int, int]:
        return clip_roi_to_dimensions(roi, dimensions)

    def _mtf_padded_roi(
        self,
        roi: tuple[int, int, int, int],
        dimensions: tuple[int, int],
        *,
        padding: int,
    ) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
        return padded_mtf_roi(roi, dimensions, padding=padding)

    def _mtf_base_roi_cache_key(self, display_roi: tuple[int, int, int, int]) -> str | None:
        context = self._mtf_selected_source_context()
        if context is None:
            return None
        _path, _recipe, source_key = context
        display_dimensions = self._mtf_current_image_dimensions()
        padding = self._mtf_roi_block_padding_px()
        return self._mtf_cache_token(
            {
                "source": source_key,
                "display_dimensions": list(display_dimensions) if display_dimensions else None,
                "display_roi": list(display_roi),
                "padding": padding,
            }
        )

    def _mtf_has_hot_base_roi_cache(self, display_roi: tuple[int, int, int, int]) -> bool:
        cache_key = self._mtf_base_roi_cache_key(display_roi)
        return bool(
            cache_key is not None
            and self._mtf_roi_base_cache_key == cache_key
            and isinstance(getattr(self, "_mtf_roi_base_cache", None), dict)
        )

    def _mtf_full_resolution_base_roi(
        self,
        display_roi: tuple[int, int, int, int],
    ) -> dict[str, Any] | None:
        context = self._mtf_selected_source_context()
        if context is None:
            return None
        path, recipe, source_key = context
        display_dimensions = self._mtf_current_image_dimensions()
        padding = self._mtf_roi_block_padding_px()
        cache_key = self._mtf_base_roi_cache_key(display_roi)
        if cache_key is None:
            return None
        cached = getattr(self, "_mtf_roi_base_cache", None)
        if self._mtf_roi_base_cache_key == cache_key and isinstance(cached, dict):
            return cached

        disk_cached = self._read_mtf_base_roi_from_disk_cache(cache_key, path=path)
        if disk_cached is not None:
            return self._set_mtf_base_roi_cache(cache_key, disk_cached)

        base = self._mtf_full_resolution_base_image(path, recipe)
        if base is None:
            return None
        analysis_dimensions = (int(base.shape[1]), int(base.shape[0]))
        analysis_roi = self._mtf_roi_for_analysis_dimensions(display_roi, display_dimensions, analysis_dimensions)
        analysis_roi = self._mtf_clip_roi_to_dimensions(analysis_roi, analysis_dimensions)
        padded_roi, relative_roi = self._mtf_padded_roi(analysis_roi, analysis_dimensions, padding=padding)
        px, py, pw, ph = padded_roi
        block = np.ascontiguousarray(base[py : py + ph, px : px + pw, :3]).copy()
        payload: dict[str, Any] = {
            "image": block,
            "source_key": source_key,
            "analysis_dimensions": analysis_dimensions,
            "display_dimensions": display_dimensions,
            "display_roi": display_roi,
            "analysis_roi": analysis_roi,
            "padded_roi": padded_roi,
            "relative_roi": relative_roi,
            "padding": padding,
        }
        self._write_mtf_base_roi_to_disk_cache(cache_key, payload, path=path)
        return self._set_mtf_base_roi_cache(cache_key, payload)

    def _mtf_pre_sharpen_base_roi(
        self,
        base_info: dict[str, Any],
        detail_kwargs: dict[str, float],
    ) -> dict[str, Any]:
        cache_key = self._mtf_cache_token(
            {
                "mode": "roi-pre-sharpen-v1",
                "base": self._mtf_roi_base_cache_key,
                "pre_sharpen": self._mtf_pre_sharpen_kwargs(detail_kwargs),
            }
        )
        cached = getattr(self, "_mtf_roi_pre_sharpen_cache", None)
        if self._mtf_roi_pre_sharpen_cache_key == cache_key and isinstance(cached, dict):
            return cached

        base_image = np.asarray(base_info["image"], dtype=np.float32)
        if self._mtf_pre_sharpen_detail_active(detail_kwargs):
            image = apply_adjustments(
                base_image,
                **self._mtf_pre_sharpen_kwargs(detail_kwargs),
            )
        else:
            image = np.clip(base_image, 0.0, 1.0).astype(np.float32, copy=False)

        payload = dict(base_info)
        payload["image"] = np.ascontiguousarray(image[..., :3]).copy()
        payload["cache_key"] = cache_key
        self._mtf_roi_pre_sharpen_cache_key = cache_key
        self._mtf_roi_pre_sharpen_cache = payload
        self._mtf_roi_analysis_cache_key = None
        self._mtf_roi_analysis_cache = None
        self._mtf_result_cache_key = None
        self._mtf_result_cache = None
        return payload

    def _mtf_auto_candidate_cache_get(self, cache_key: str) -> MTFResult | None:
        cache = getattr(self, "_mtf_auto_candidate_cache", None)
        if not isinstance(cache, dict):
            return None
        result = cache.get(cache_key)
        if result is None:
            return None
        order = getattr(self, "_mtf_auto_candidate_cache_order", None)
        if isinstance(order, list):
            try:
                order.remove(cache_key)
            except ValueError:
                pass
            order.append(cache_key)
        return result

    def _mtf_auto_candidate_cache_put(self, cache_key: str, result: MTFResult) -> None:
        cache = getattr(self, "_mtf_auto_candidate_cache", None)
        order = getattr(self, "_mtf_auto_candidate_cache_order", None)
        if not isinstance(cache, dict) or not isinstance(order, list):
            return
        cache[cache_key] = result
        try:
            order.remove(cache_key)
        except ValueError:
            pass
        order.append(cache_key)
        while len(order) > 320:
            old = order.pop(0)
            cache.pop(old, None)

    def _mtf_render_pre_sharpened_roi(
        self,
        prepared: dict[str, Any],
        detail_kwargs: dict[str, float],
    ) -> dict[str, Any]:
        source = np.asarray(prepared["image"], dtype=np.float32)
        if self._mtf_lateral_ca_adjustment_active(detail_kwargs):
            source = self._mtf_apply_lateral_ca_to_padded_roi(source, prepared, detail_kwargs)
        if self._mtf_sharpen_detail_active(detail_kwargs):
            adjusted = apply_adjustments(
                source,
                **self._mtf_sharpen_kwargs(detail_kwargs),
            )
        else:
            adjusted = source
        render_kwargs = self._render_adjustment_kwargs() if hasattr(self, "_render_adjustment_kwargs") else {}
        adjusted = apply_render_adjustments(adjusted, **render_kwargs)
        srgb = linear_to_srgb_display(adjusted)
        rx, ry, rw, rh = [int(v) for v in prepared["relative_roi"]]
        roi_image = np.ascontiguousarray(srgb[ry : ry + rh, rx : rx + rw, :3]).copy()
        payload = dict(prepared)
        payload["image"] = roi_image
        payload["relative_roi"] = (0, 0, int(rw), int(rh))
        return payload

    def _mtf_apply_lateral_ca_to_padded_roi(
        self,
        source: np.ndarray,
        prepared: dict[str, Any],
        detail_kwargs: dict[str, float],
    ) -> np.ndarray:
        image = np.clip(np.asarray(source, dtype=np.float32), 0.0, 1.0)
        if image.ndim != 3 or image.shape[2] < 3:
            return image
        analysis_dimensions = prepared.get("analysis_dimensions")
        padded_roi = prepared.get("padded_roi")
        if (
            not isinstance(analysis_dimensions, (list, tuple))
            or len(analysis_dimensions) < 2
            or not isinstance(padded_roi, (list, tuple))
            or len(padded_roi) < 4
        ):
            return image
        full_w, full_h = int(analysis_dimensions[0]), int(analysis_dimensions[1])
        px, py, pw, ph = [int(v) for v in padded_roi]
        if full_w <= 0 or full_h <= 0 or pw <= 0 or ph <= 0:
            return image

        out = image[..., :3].copy()
        red_scale = float(detail_kwargs.get("lateral_ca_red_scale", 1.0))
        blue_scale = float(detail_kwargs.get("lateral_ca_blue_scale", 1.0))
        if abs(red_scale - 1.0) > 1e-5:
            out[..., 0] = self._mtf_scale_channel_radially_roi(
                out[..., 0],
                red_scale,
                (px, py, pw, ph),
                (full_w, full_h),
            )
        if abs(blue_scale - 1.0) > 1e-5:
            out[..., 2] = self._mtf_scale_channel_radially_roi(
                out[..., 2],
                blue_scale,
                (px, py, pw, ph),
                (full_w, full_h),
            )
        return np.clip(out, 0.0, 1.0).astype(np.float32, copy=False)

    def _mtf_scale_channel_radially_roi(
        self,
        channel: np.ndarray,
        scale: float,
        padded_roi: tuple[int, int, int, int],
        analysis_dimensions: tuple[int, int],
    ) -> np.ndarray:
        if scale <= 0.0 or abs(float(scale) - 1.0) <= 1e-5:
            return channel.astype(np.float32, copy=False)
        px, py, pw, ph = [int(v) for v in padded_roi]
        full_w, full_h = [int(v) for v in analysis_dimensions]
        y, x = np.indices((int(ph), int(pw)), dtype=np.float32)
        global_x = x + float(px)
        global_y = y + float(py)
        cx = (float(full_w) - 1.0) / 2.0
        cy = (float(full_h) - 1.0) / 2.0
        map_x = (((global_x - cx) / float(scale)) + cx - float(px)).astype(np.float32)
        map_y = (((global_y - cy) / float(scale)) + cy - float(py)).astype(np.float32)
        return cv2.remap(
            channel.astype(np.float32, copy=False),
            map_x,
            map_y,
            interpolation=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT,
        )

    def _mtf_full_resolution_analysis_image(
        self,
        path: Path | None = None,
        recipe: Recipe | None = None,
    ) -> np.ndarray | None:
        base = self._mtf_full_resolution_base_image(path, recipe)
        if base is None:
            return None
        detail_kwargs = self._mtf_detail_adjustment_kwargs()
        adjusted = apply_adjustments(
            base,
            **detail_kwargs,
        )
        render_kwargs = self._render_adjustment_kwargs() if hasattr(self, "_render_adjustment_kwargs") else {}
        adjusted = apply_render_adjustments(adjusted, **render_kwargs)
        return linear_to_srgb_display(adjusted)

    def _mtf_full_resolution_analysis_roi_image(
        self,
        display_roi: tuple[int, int, int, int],
    ) -> dict[str, Any] | None:
        detail_kwargs = self._mtf_detail_adjustment_kwargs()
        base_info = self._mtf_full_resolution_base_roi(display_roi)
        if base_info is None:
            return None
        cache_key = self._mtf_cache_token(
            {
                "mode": "roi-block-v1",
                "base": self._mtf_roi_base_cache_key,
                "adjustments": self._mtf_adjustment_cache_state(),
            }
        )
        cached = getattr(self, "_mtf_roi_analysis_cache", None)
        if self._mtf_roi_analysis_cache_key == cache_key and isinstance(cached, dict):
            return cached

        prepared = self._mtf_pre_sharpen_base_roi(base_info, detail_kwargs)
        payload = self._mtf_render_pre_sharpened_roi(prepared, detail_kwargs)
        self._mtf_roi_analysis_cache_key = cache_key
        self._mtf_roi_analysis_cache = payload
        self._mtf_result_cache_key = None
        self._mtf_result_cache = None
        return payload

    def _mtf_full_resolution_analysis_roi_image_from_full_image(
        self,
        display_roi: tuple[int, int, int, int],
    ) -> dict[str, Any] | None:
        context = self._mtf_selected_source_context()
        if context is None:
            return None
        path, recipe, source_key = context
        display_dimensions = self._mtf_current_image_dimensions()
        cache_key = self._mtf_cache_token(
            {
                "mode": "full-image-ca-v1",
                "source": source_key,
                "display_dimensions": list(display_dimensions) if display_dimensions else None,
                "display_roi": list(display_roi),
                "adjustments": self._mtf_adjustment_cache_state(),
            }
        )
        cached = getattr(self, "_mtf_roi_analysis_cache", None)
        if self._mtf_roi_analysis_cache_key == cache_key and isinstance(cached, dict):
            return cached

        image = self._mtf_full_resolution_analysis_image(path, recipe)
        if image is None:
            return None
        analysis_dimensions = (int(image.shape[1]), int(image.shape[0]))
        analysis_roi = self._mtf_roi_for_analysis_dimensions(display_roi, display_dimensions, analysis_dimensions)
        analysis_roi = self._mtf_clip_roi_to_dimensions(analysis_roi, analysis_dimensions)
        x, y, width, height = analysis_roi
        roi_image = np.ascontiguousarray(image[y : y + height, x : x + width, :3]).copy()
        payload: dict[str, Any] = {
            "image": roi_image,
            "source_key": source_key,
            "analysis_dimensions": analysis_dimensions,
            "display_dimensions": display_dimensions,
            "display_roi": display_roi,
            "analysis_roi": analysis_roi,
            "padded_roi": analysis_roi,
            "relative_roi": (0, 0, width, height),
            "padding": 0,
        }
        self._mtf_roi_analysis_cache_key = cache_key
        self._mtf_roi_analysis_cache = payload
        self._mtf_result_cache_key = None
        self._mtf_result_cache = None
        return payload

    def _mtf_roi_for_analysis_image(
        self,
        roi: tuple[int, int, int, int],
        analysis_dimensions: tuple[int, int],
    ) -> tuple[int, int, int, int]:
        display_dimensions = self._mtf_current_image_dimensions()
        return self._mtf_roi_for_analysis_dimensions(roi, display_dimensions, analysis_dimensions)

    def _mtf_roi_for_analysis_dimensions(
        self,
        roi: tuple[int, int, int, int],
        display_dimensions: tuple[int, int] | None,
        analysis_dimensions: tuple[int, int],
    ) -> tuple[int, int, int, int]:
        return roi_for_analysis_dimensions(roi, display_dimensions, analysis_dimensions)

    def _mtf_display_roi_from_analysis_roi(
        self,
        roi: tuple[int, int, int, int],
        analysis_dimensions: tuple[int, int] | None,
    ) -> tuple[int, int, int, int]:
        display_dimensions = self._mtf_current_image_dimensions()
        if analysis_dimensions is None or display_dimensions is None or analysis_dimensions == display_dimensions:
            return roi
        analysis_w, analysis_h = analysis_dimensions
        display_w, display_h = display_dimensions
        if analysis_w <= 0 or analysis_h <= 0 or display_w <= 0 or display_h <= 0:
            return roi
        scale_x = float(display_w) / float(analysis_w)
        scale_y = float(display_h) / float(analysis_h)
        x, y, width, height = roi
        return (
            int(round(float(x) * scale_x)),
            int(round(float(y) * scale_y)),
            max(1, int(round(float(width) * scale_x))),
            max(1, int(round(float(height) * scale_y))),
        )

    def _auto_optimize_mtf_sharpening(self) -> None:
        if getattr(self, "_mtf_roi", None) is None:
            self._update_mtf_result_widgets(error=self.tr("Auto nitidez: selecciona primero una ROI MTF."))
            return
        if not self._run_mtf_analysis_inline() and not self._mtf_try_activate_cached_base_roi(self._mtf_roi):
            self._update_mtf_result_widgets(error=self.tr("Auto nitidez: preparando ROI full-res en segundo plano..."))
            self._queue_mtf_base_roi_worker(self._mtf_roi, mode="auto_sharpen")
            return
        auto_started = time.perf_counter()
        if getattr(self, "_mtf_progress_stage", "") != "auto_sharpen":
            self._start_mtf_progress(
                "auto_sharpen",
                detail=self.tr("preparando candidatos"),
                estimate_seconds=self._mtf_auto_sharpen_estimate_seconds(),
            )
        self._set_status(self.tr("Auto nitidez: evaluando ROI a resolución real..."))
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.processEvents(QtCore.QEventLoop.ExcludeUserInputEvents)
        try:
            prepared = self._mtf_auto_sharpen_prepared_roi(self._mtf_roi)
        except Exception as exc:
            self._fail_mtf_progress(str(exc))
            self._update_mtf_result_widgets(error=f"{self.tr('Auto nitidez')}: {exc}")
            return
        if prepared is None:
            self._fail_mtf_progress(self.tr("No se pudo preparar la ROI."))
            self._update_mtf_result_widgets(error=self.tr("Auto nitidez: no se pudo preparar la ROI."))
            return

        evaluated: list[dict[str, Any]] = []
        candidates = self._mtf_auto_sharpen_candidates()
        self._set_mtf_progress_steps(
            0,
            len(candidates),
            detail=self.tr("evaluando combinaciones de nitidez"),
        )
        for index, (amount_slider, radius_slider) in enumerate(candidates):
            self._set_mtf_progress_steps(
                index + 1,
                len(candidates),
                detail=self.tr("combinación")
                + f" {index + 1}/{len(candidates)}"
                + f" (amount={float(amount_slider) / 100.0:.2f}, radius={float(radius_slider) / 10.0:.1f})",
            )
            if app is not None and index % 6 == 0:
                app.processEvents(QtCore.QEventLoop.ExcludeUserInputEvents)
            try:
                result = self._mtf_auto_sharpen_candidate_result(
                    prepared,
                    amount_slider=amount_slider,
                    radius_slider=radius_slider,
                )
            except Exception:
                continue
            candidate = {
                "amount_slider": int(amount_slider),
                "radius_slider": int(radius_slider),
                "result": result,
            }
            candidate.update(self._mtf_auto_sharpen_quality_metrics(result))
            candidate.update(self._mtf_auto_sharpen_halo_metrics(result))
            candidate["score"] = self._mtf_auto_sharpen_score(
                result,
                amount=float(amount_slider) / 100.0,
                radius=float(radius_slider) / 10.0,
            )
            evaluated.append(candidate)

        best = self._mtf_auto_sharpen_select_best(evaluated)
        if best is None:
            self._fail_mtf_progress(self.tr("Sin combinación válida."))
            self._update_mtf_result_widgets(error=self.tr("Auto nitidez: no se encontró una combinación válida."))
            return
        self._apply_mtf_auto_sharpening(best, prepared)
        elapsed = time.perf_counter() - auto_started
        self._record_mtf_timing("performance/mtf_auto_sharpen_seconds_ewma", elapsed)
        roi_elapsed = getattr(self, "_mtf_progress_roi_elapsed_seconds", None)
        total_elapsed = float(roi_elapsed) + elapsed if roi_elapsed is not None else elapsed
        detail = (
            self.tr("ROI")
            + f" {self._mtf_format_duration(float(roi_elapsed))} + "
            + self.tr("auto nitidez")
            + f" {self._mtf_format_duration(elapsed)}"
            if roi_elapsed is not None
            else f"{len(evaluated)}/{len(candidates)} " + self.tr("combinaciones evaluadas")
        )
        self._mtf_progress_roi_elapsed_seconds = None
        self._finish_mtf_progress("auto_complete", detail=detail, elapsed_seconds=total_elapsed)

    def _mtf_auto_sharpen_prepared_roi(
        self,
        display_roi: tuple[int, int, int, int],
    ) -> dict[str, Any] | None:
        detail_kwargs = self._mtf_detail_adjustment_kwargs()
        base_info = self._mtf_full_resolution_base_roi(display_roi)
        if base_info is None:
            return None
        prepared = self._mtf_pre_sharpen_base_roi(base_info, detail_kwargs)
        if not self._mtf_lateral_ca_adjustment_active(detail_kwargs):
            return prepared
        payload = dict(prepared)
        payload["image"] = self._mtf_apply_lateral_ca_to_padded_roi(
            np.asarray(prepared["image"], dtype=np.float32),
            prepared,
            detail_kwargs,
        )
        payload["cache_key"] = self._mtf_cache_token(
            {
                "mode": "auto-roi-ca-pre-sharpen-v1",
                "prepared": str(prepared.get("cache_key") or id(prepared.get("image"))),
                "ca": {
                    "lateral_ca_red_scale": float(detail_kwargs.get("lateral_ca_red_scale", 1.0)),
                    "lateral_ca_blue_scale": float(detail_kwargs.get("lateral_ca_blue_scale", 1.0)),
                },
            }
        )
        return payload

    def _mtf_auto_sharpen_prepared_roi_from_full_image(
        self,
        display_roi: tuple[int, int, int, int],
        fixed_kwargs: dict[str, float],
        detail_kwargs: dict[str, float],
    ) -> dict[str, Any] | None:
        context = self._mtf_selected_source_context()
        if context is None:
            return None
        path, recipe, source_key = context
        base = self._mtf_full_resolution_base_image(path, recipe)
        if base is None:
            return None
        display_dimensions = self._mtf_current_image_dimensions()
        analysis_dimensions = (int(base.shape[1]), int(base.shape[0]))
        analysis_roi = self._mtf_roi_for_analysis_dimensions(display_roi, display_dimensions, analysis_dimensions)
        analysis_roi = self._mtf_clip_roi_to_dimensions(analysis_roi, analysis_dimensions)
        padded_roi, relative_roi = self._mtf_padded_roi(
            analysis_roi,
            analysis_dimensions,
            padding=self._mtf_roi_block_padding_px(),
        )
        fixed_full_kwargs = dict(fixed_kwargs)
        fixed_full_kwargs["lateral_ca_red_scale"] = float(detail_kwargs.get("lateral_ca_red_scale", 1.0))
        fixed_full_kwargs["lateral_ca_blue_scale"] = float(detail_kwargs.get("lateral_ca_blue_scale", 1.0))
        preprocessed = apply_adjustments(base, **fixed_full_kwargs)
        px, py, pw, ph = padded_roi
        block = np.ascontiguousarray(preprocessed[py : py + ph, px : px + pw, :3]).copy()
        cache_key = self._mtf_cache_token(
            {
                "mode": "auto-full-ca-pre-sharpen-v1",
                "source": source_key,
                "display_dimensions": list(display_dimensions) if display_dimensions else None,
                "display_roi": list(display_roi),
                "analysis_roi": list(analysis_roi),
                "padded_roi": list(padded_roi),
                "fixed": fixed_full_kwargs,
            }
        )
        return {
            "image": block,
            "source_key": source_key,
            "analysis_dimensions": analysis_dimensions,
            "display_dimensions": display_dimensions,
            "display_roi": display_roi,
            "analysis_roi": analysis_roi,
            "padded_roi": padded_roi,
            "relative_roi": relative_roi,
            "padding": self._mtf_roi_block_padding_px(),
            "cache_key": cache_key,
        }

    def _mtf_auto_sharpen_candidates(self) -> list[tuple[int, int]]:
        amount_slider = getattr(self, "slider_sharpen", None)
        radius_slider = getattr(self, "slider_radius", None)
        amount_min = int(amount_slider.minimum()) if amount_slider is not None else 0
        amount_max = int(amount_slider.maximum()) if amount_slider is not None else 300
        radius_min = int(radius_slider.minimum()) if radius_slider is not None else 1
        radius_max = int(radius_slider.maximum()) if radius_slider is not None else 80
        current_amount = int(amount_slider.value()) if amount_slider is not None else 0
        current_radius = int(radius_slider.value()) if radius_slider is not None else 10
        base_amounts = [0, 20, 40, 60, 80, 100, 120, 140, 160, 180, 210, 240]
        base_radii = [4, 6, 8, 10, 12, 15, 18, 22, 28, 35]
        amounts = sorted({int(np.clip(v, amount_min, amount_max)) for v in [*base_amounts, current_amount]})
        radii = sorted({int(np.clip(v, radius_min, radius_max)) for v in [*base_radii, current_radius]})
        candidates: list[tuple[int, int]] = []
        seen: set[tuple[int, int]] = set()
        for amount in amounts:
            radius_values = [int(np.clip(current_radius, radius_min, radius_max))] if amount <= 0 else radii
            for radius in radius_values:
                key = (int(amount), int(radius))
                if key not in seen:
                    seen.add(key)
                    candidates.append(key)
        return candidates

    def _mtf_auto_sharpen_candidate_result(
        self,
        prepared: dict[str, Any],
        *,
        amount_slider: int,
        radius_slider: int,
    ) -> MTFResult:
        render_state = self._render_adjustment_state() if hasattr(self, "_render_adjustment_state") else {}
        cache_key = self._mtf_cache_token(
            {
                "mode": "auto-candidate-result-v1",
                "prepared": str(prepared.get("cache_key") or id(prepared.get("image"))),
                "analysis_roi": list(prepared["analysis_roi"]),
                "amount": int(amount_slider),
                "radius": int(radius_slider),
                "render": render_state,
            }
        )
        cached = self._mtf_auto_candidate_cache_get(cache_key)
        if cached is not None:
            return cached
        source = np.asarray(prepared["image"], dtype=np.float32)
        if int(amount_slider) > 0:
            adjusted = apply_adjustments(
                source,
                denoise_luminance=0.0,
                denoise_color=0.0,
                sharpen_amount=float(amount_slider) / 100.0,
                sharpen_radius=float(radius_slider) / 10.0,
                lateral_ca_red_scale=1.0,
                lateral_ca_blue_scale=1.0,
            )
        else:
            adjusted = source
        render_kwargs = self._render_adjustment_kwargs() if hasattr(self, "_render_adjustment_kwargs") else {}
        adjusted = apply_render_adjustments(adjusted, **render_kwargs)
        srgb = linear_to_srgb_display(adjusted)
        rx, ry, rw, rh = [int(v) for v in prepared["relative_roi"]]
        roi_image = np.ascontiguousarray(srgb[ry : ry + rh, rx : rx + rw, :3]).copy()
        measured = analyze_slanted_edge_mtf(roi_image, None)
        result = replace(measured, roi=prepared["analysis_roi"])
        self._mtf_auto_candidate_cache_put(cache_key, result)
        return result

    def _mtf_auto_sharpen_score(self, result: MTFResult, *, amount: float, radius: float) -> float:
        mtf50 = self._mtf_payload_optional_float(result.mtf50) or 0.0
        mtf50p = self._mtf_payload_optional_float(getattr(result, "mtf50p", None)) or mtf50
        mtf30 = self._mtf_payload_optional_float(result.mtf30) or 0.0
        mtf10 = self._mtf_payload_optional_float(result.mtf10) or 0.0
        acutance = float(np.clip(result.acutance, 0.0, 2.0))
        quality = self._mtf_auto_sharpen_quality_metrics(result)
        halo_metrics = self._mtf_auto_sharpen_halo_metrics(result)
        halo = float(halo_metrics["halo"])
        hard_halo = max(0.0, halo - 0.025)
        post = self._mtf_post_nyquist_metrics(result)
        post_peak = float(post.get("peak_modulation", 0.0) or 0.0)
        post_energy = float(post.get("energy_ratio", 0.0) or 0.0)
        mtf50_gap = float(quality.get("mtf50_gap", 0.0))
        mtf_peak_boost = float(quality.get("mtf_peak_boost", 0.0))
        sharpness = 1.15 * mtf50p + 0.35 * mtf50 + 0.35 * mtf30 + 0.12 * mtf10 + 0.08 * acutance
        penalty = 4.0 * halo + 24.0 * hard_halo
        penalty += 2.2 * mtf50_gap + 0.65 * mtf_peak_boost
        penalty += 0.12 * post_peak + 0.08 * post_energy
        penalty += 0.020 * max(0.0, float(amount) - 1.20)
        penalty += 0.004 * max(0.0, float(radius) - 1.50)
        return float(sharpness - penalty)

    def _mtf_auto_sharpen_quality_metrics(self, result: MTFResult) -> dict[str, float]:
        mtf50 = self._mtf_payload_optional_float(result.mtf50) or 0.0
        mtf50p = self._mtf_payload_optional_float(getattr(result, "mtf50p", None)) or mtf50
        mtf_source = getattr(result, "mtf", None)
        mtf_values = np.asarray([] if mtf_source is None else mtf_source, dtype=np.float64)
        mtf_values = mtf_values[np.isfinite(mtf_values)]
        mtf_peak = float(np.max(mtf_values)) if mtf_values.size else 0.0
        return {
            "effective_mtf50": float(mtf50p),
            "mtf50_gap": float(max(0.0, mtf50 - mtf50p)),
            "mtf_peak": float(mtf_peak),
            "mtf_peak_boost": float(max(0.0, mtf_peak - 1.05)),
        }

    def _mtf_auto_sharpen_halo_metrics(self, result: MTFResult) -> dict[str, float]:
        overshoot = max(0.0, float(result.overshoot))
        undershoot = max(0.0, float(result.undershoot))
        esf = np.asarray(getattr(result, "esf", []) or [], dtype=np.float64)
        bright_peak = 0.0
        dark_dip = 0.0
        if esf.size >= 12 and np.all(np.isfinite(esf)):
            edge_count = max(4, int(esf.size) // 10)
            low_level = float(np.median(esf[:edge_count]))
            high_level = float(np.median(esf[-edge_count:]))
            diffs = np.diff(esf)
            if diffs.size:
                edge_idx = int(np.argmax(diffs))
                bright_side = esf[min(esf.size - 1, edge_idx + 1) :]
                dark_side = esf[: max(1, edge_idx + 1)]
                if bright_side.size:
                    bright_peak = max(0.0, float(np.max(bright_side)) - high_level)
                if dark_side.size:
                    dark_dip = max(0.0, low_level - float(np.min(dark_side)))
        bright_halo = max(overshoot, bright_peak)
        dark_halo = max(undershoot, dark_dip)
        return {
            "bright_halo": float(bright_halo),
            "dark_halo": float(dark_halo),
            "halo": float(bright_halo + dark_halo),
        }

    def _mtf_auto_sharpen_select_best(self, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not candidates:
            return None
        baseline_candidates = [candidate for candidate in candidates if int(candidate["amount_slider"]) == 0]
        baseline = min(
            baseline_candidates or candidates,
            key=lambda candidate: (
                float(candidate.get("halo", 0.0)),
                int(candidate["amount_slider"]),
                int(candidate["radius_slider"]),
            ),
        )
        baseline_halo = float(baseline.get("halo", 0.0))
        baseline_bright = float(baseline.get("bright_halo", 0.0))
        baseline_dark = float(baseline.get("dark_halo", 0.0))
        baseline_effective = float(baseline.get("effective_mtf50", 0.0))
        baseline_gap = float(baseline.get("mtf50_gap", 0.0))
        baseline_peak_boost = float(baseline.get("mtf_peak_boost", 0.0))
        allowed_halo = max(0.025, baseline_halo + 0.010)
        allowed_bright = max(0.020, baseline_bright + 0.008)
        allowed_dark = max(0.020, baseline_dark + 0.008)
        allowed_gap = max(0.035, baseline_gap + 0.020)
        allowed_peak_boost = max(0.100, baseline_peak_boost + 0.060)
        minimum_effective = baseline_effective * 1.01
        acceptable = [
            candidate
            for candidate in candidates
            if (
                int(candidate["amount_slider"]) == 0
                or float(candidate.get("effective_mtf50", 0.0)) >= minimum_effective
            )
            and float(candidate.get("halo", 0.0)) <= allowed_halo
            and float(candidate.get("bright_halo", 0.0)) <= allowed_bright
            and float(candidate.get("dark_halo", 0.0)) <= allowed_dark
            and float(candidate.get("mtf50_gap", 0.0)) <= allowed_gap
            and float(candidate.get("mtf_peak_boost", 0.0)) <= allowed_peak_boost
        ]
        pool = acceptable or candidates
        return max(pool, key=lambda candidate: self._mtf_auto_sharpen_sort_key(candidate))

    def _mtf_auto_sharpen_sort_key(self, candidate: dict[str, Any]) -> tuple[float, float, float, int, int]:
        return (
            float(candidate["score"]),
            float(candidate.get("effective_mtf50", 0.0)),
            -float(candidate.get("halo", 0.0)),
            -int(candidate["amount_slider"]),
            -int(candidate["radius_slider"]),
        )

    def _apply_mtf_auto_sharpening(self, best: dict[str, Any], prepared: dict[str, Any]) -> None:
        amount_slider = int(best["amount_slider"])
        radius_slider = int(best["radius_slider"])
        self._suspend_detail_adjustment_autosave = int(getattr(self, "_suspend_detail_adjustment_autosave", 0) or 0) + 1
        try:
            if hasattr(self, "slider_sharpen"):
                self.slider_sharpen.setValue(amount_slider)
            if hasattr(self, "slider_radius"):
                self.slider_radius.setValue(radius_slider)
        finally:
            self._suspend_detail_adjustment_autosave = max(
                0,
                int(getattr(self, "_suspend_detail_adjustment_autosave", 1) or 1) - 1,
            )
        if hasattr(self, "_set_active_named_adjustment_profile_id"):
            self._set_active_named_adjustment_profile_id("detail", "")
        if hasattr(self, "_refresh_named_adjustment_profile_combo"):
            self._refresh_named_adjustment_profile_combo("detail")
        result = best["result"]
        self._mtf_last_analysis_image_dimensions = prepared["analysis_dimensions"]
        self._mtf_last_display_dimensions = prepared["display_dimensions"]
        self._mtf_last_display_roi = prepared["display_roi"]
        self._mtf_last_result = result
        self._update_mtf_result_widgets()
        self._persist_mtf_analysis_for_selected()
        if hasattr(self, "_schedule_detail_adjustment_sidecar_persist"):
            self._schedule_detail_adjustment_sidecar_persist(immediate=True)
        if hasattr(self, "_schedule_preview_refresh") and getattr(self, "_original_linear", None) is not None:
            self._schedule_preview_refresh()
        amount = float(amount_slider) / 100.0
        radius = float(radius_slider) / 10.0
        mtf50 = self._format_mtf_cycles(result.mtf50)
        mtf50p = self._format_mtf_cycles(getattr(result, "mtf50p", None))
        self._set_status(
            self.tr("Auto nitidez aplicada")
            + f": amount={amount:.2f}, radius={radius:.1f}, MTF50={mtf50}, MTF50P={mtf50p}, halo={float(best.get('halo', 0.0)) * 100.0:.1f}%"
        )

    def _mtf_try_activate_cached_base_roi(self, display_roi: tuple[int, int, int, int]) -> bool:
        cache_key = self._mtf_base_roi_cache_key(display_roi)
        if cache_key is None:
            return False
        cached = getattr(self, "_mtf_roi_base_cache", None)
        if self._mtf_roi_base_cache_key == cache_key and isinstance(cached, dict):
            return True
        context = self._mtf_selected_source_context()
        if context is None:
            return False
        path, _recipe, _source_key = context
        disk_cached = self._read_mtf_base_roi_from_disk_cache(cache_key, path=path)
        if disk_cached is None:
            return False
        self._set_mtf_base_roi_cache(cache_key, disk_cached)
        return True

    def _mtf_base_roi_worker_request(
        self,
        display_roi: tuple[int, int, int, int],
        *,
        mode: str,
    ) -> dict[str, Any] | None:
        context = self._mtf_selected_source_context()
        if context is None:
            return None
        path, recipe, source_key = context
        cache_key = self._mtf_base_roi_cache_key(display_roi)
        if cache_key is None:
            return None
        return {
            "cache_key": cache_key,
            "mode": str(mode),
            "path": str(path),
            "recipe": to_json_dict(recipe) if recipe is not None else None,
            "source_key": source_key,
            "display_dimensions": list(self._mtf_current_image_dimensions() or ()),
            "display_roi": list(display_roi),
            "padding": int(self._mtf_roi_block_padding_px()),
        }

    def _queue_mtf_base_roi_worker(
        self,
        display_roi: tuple[int, int, int, int],
        *,
        mode: str = "analysis",
    ) -> bool:
        request = self._mtf_base_roi_worker_request(display_roi, mode=mode)
        if request is None:
            return False
        cache_key = str(request["cache_key"])
        if bool(getattr(self, "_mtf_base_roi_task_active", False)):
            if getattr(self, "_mtf_base_roi_inflight_key", None) == cache_key:
                self._set_status(self.tr("MTF: ROI full-res ya se está preparando en segundo plano..."))
                return True
            self._mtf_base_roi_pending_request = request
            self._start_mtf_progress(
                "queued",
                detail=self._mtf_request_progress_detail(request),
                estimate_seconds=self._mtf_worker_estimate_seconds(request),
            )
            self._set_status(self.tr("MTF: ROI full-res encolada; se procesará al terminar la actual."))
            return True
        self._start_mtf_base_roi_worker(request)
        return True

    def _mtf_request_progress_detail(self, request: dict[str, Any]) -> str:
        path = Path(str(request.get("path") or ""))
        roi = request.get("display_roi")
        roi_label = ""
        if isinstance(roi, (list, tuple)) and len(roi) >= 4:
            try:
                roi_label = f" ROI {int(roi[2])}x{int(roi[3])}"
            except Exception:
                roi_label = ""
        mode = str(request.get("mode") or "analysis")
        mode_label = self.tr("auto nitidez") if mode == "auto_sharpen" else self.tr("análisis")
        name = path.name or self.tr("archivo actual")
        return f"{name}{roi_label} ({mode_label})"

    def _mtf_base_roi_worker_command(self, request_path: Path, output_path: Path) -> list[str]:
        if bool(getattr(sys, "frozen", False)):
            exe_path = Path(sys.executable).resolve()
            candidates = [exe_path.with_name("probraw.exe"), exe_path.with_name("probraw")]
            for candidate in candidates:
                if candidate.exists() and candidate.is_file():
                    return [
                        str(candidate),
                        "mtf-roi-worker",
                        str(request_path),
                        str(output_path),
                    ]
            raise RuntimeError(
                self.tr("No se encontrÃ³ el ejecutable CLI de ProbRAW para calcular la ROI MTF.")
            )
        return [
            sys.executable,
            "-m",
            "probraw.analysis.mtf_roi",
            str(request_path),
            str(output_path),
        ]

    def _start_mtf_base_roi_worker(self, request: dict[str, Any]) -> None:
        label = self.tr("MTF ROI full-res")
        self._set_status(self.tr("MTF: preparando ROI full-res en segundo plano..."))
        task_row = self._monitor_task_start(label)
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.processEvents(QtCore.QEventLoop.ExcludeUserInputEvents)
        cache_key = str(request["cache_key"])
        self._mtf_base_roi_task_active = True
        self._mtf_base_roi_inflight_key = cache_key
        self._start_mtf_progress(
            "prepare",
            detail=self._mtf_request_progress_detail(request),
            estimate_seconds=self._mtf_worker_estimate_seconds(request),
        )

        def task():
            started = time.perf_counter()
            src_root = Path(__file__).resolve().parents[3]
            env = dict(os.environ)
            existing_pythonpath = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = (
                str(src_root)
                if not existing_pythonpath
                else str(src_root) + os.pathsep + existing_pythonpath
            )
            with tempfile.TemporaryDirectory(prefix="probraw-mtf-roi-") as tmp_dir:
                tmp_root = Path(tmp_dir)
                request_path = tmp_root / "request.json"
                output_path = tmp_root / "base_roi.npz"
                request_path.write_text(json.dumps(request, sort_keys=True, ensure_ascii=False), encoding="utf-8")
                proc = run_external(
                    self._mtf_base_roi_worker_command(request_path, output_path),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=300,
                    env=env,
                    cwd=str(Path.cwd()),
                )
                if proc.returncode != 0:
                    detail = (proc.stderr or proc.stdout or "").strip()
                    raise RuntimeError(detail or f"mtf_roi worker exited with {proc.returncode}")
                payload = read_base_roi_cache(output_path)
            return {
                "cache_key": cache_key,
                "request": dict(request),
                "payload": payload,
                "elapsed_seconds": float(time.perf_counter() - started),
            }

        thread = TaskThread(task)
        self._threads.append(thread)

        def cleanup() -> dict[str, Any] | None:
            self._mtf_base_roi_task_active = False
            self._mtf_base_roi_inflight_key = None
            if thread in self._threads:
                self._threads.remove(thread)
            thread.deleteLater()
            pending = self._mtf_base_roi_pending_request
            self._mtf_base_roi_pending_request = None
            return pending

        def maybe_start_pending(pending: dict[str, Any] | None) -> None:
            if pending is not None and not bool(getattr(self, "_background_threads_shutdown", False)):
                self._start_mtf_base_roi_worker(pending)

        def ok(result: dict[str, Any]) -> None:
            pending = None
            try:
                pending = cleanup()
                payload_request = result.get("request") if isinstance(result, dict) else {}
                display_roi = tuple(int(v) for v in payload_request.get("display_roi", []))
                current_key = self._mtf_base_roi_cache_key(display_roi) if len(display_roi) == 4 else None
                result_key = str(result.get("cache_key") or "")
                if current_key != result_key:
                    self._monitor_task_finish(task_row, self.tr("Descartado"), self.tr("ROI MTF obsoleta"))
                    return
                payload = result.get("payload")
                if not isinstance(payload, dict):
                    raise RuntimeError("El worker MTF no devolvió una ROI válida.")
                self._set_mtf_base_roi_cache(result_key, payload)
                self._write_mtf_base_roi_to_disk_cache(result_key, payload, path=Path(str(payload_request.get("path"))))
                elapsed = float(result.get("elapsed_seconds") or 0.0)
                self._mtf_progress_roi_elapsed_seconds = elapsed
                self._record_mtf_timing("performance/mtf_fullres_roi_seconds_ewma", elapsed)
                self._monitor_task_finish(task_row, self.tr("Completado"), f"{elapsed:.2f}s")
                self._start_mtf_progress(
                    "analyze" if str(payload_request.get("mode") or "") != "auto_sharpen" else "auto_sharpen",
                    detail=self.tr("ROI preparada; calculando resultado"),
                    estimate_seconds=(
                        self._mtf_analysis_estimate_seconds()
                        if str(payload_request.get("mode") or "") != "auto_sharpen"
                        else self._mtf_auto_sharpen_estimate_seconds()
                    ),
                )
                self._set_status(self.tr("MTF: ROI full-res preparada; calculando métricas..."))
                if str(payload_request.get("mode") or "") == "auto_sharpen":
                    self._auto_optimize_mtf_sharpening()
                else:
                    self._recalculate_mtf_analysis()
            except Exception as exc:
                self._monitor_task_finish(task_row, self.tr("Error"), str(exc))
                self._fail_mtf_progress(str(exc))
                self._update_mtf_result_widgets(error=f"MTF: {exc}")
            finally:
                maybe_start_pending(pending)

        def fail(trace: str) -> None:
            pending = cleanup()
            self._log_preview(trace[-1200:])
            self._set_status(self.tr("Error preparando ROI MTF full-res"))
            self._monitor_task_finish(
                task_row,
                self.tr("Error"),
                trace.strip().splitlines()[-1] if trace.strip() else self.tr("Error"),
            )
            self._fail_mtf_progress(trace.strip().splitlines()[-1] if trace.strip() else self.tr("Error"))
            self._update_mtf_result_widgets(error=self.tr("MTF: no se pudo preparar la ROI full-res."))
            maybe_start_pending(pending)

        thread.succeeded.connect(ok)
        thread.failed.connect(fail)
        thread.start()

    def _recalculate_mtf_analysis(self) -> None:
        if getattr(self, "_mtf_roi", None) is None:
            self._update_mtf_result_widgets(error=self.tr("MTF: selecciona una ROI de borde inclinado."))
            return
        display_roi = self._mtf_roi
        if not self._run_mtf_analysis_inline() and not self._mtf_try_activate_cached_base_roi(display_roi):
            self._mtf_last_result = None
            self._update_mtf_result_widgets(error=self.tr("MTF: preparando ROI full-res en segundo plano..."))
            self._queue_mtf_base_roi_worker(display_roi, mode="analysis")
            return
        analysis_started = time.perf_counter()
        if getattr(self, "_mtf_progress_stage", "") != "analyze":
            self._start_mtf_progress(
                "analyze",
                detail=self.tr("calculando ESF/LSF/MTF"),
                estimate_seconds=self._mtf_analysis_estimate_seconds(),
            )
        self._set_status(self.tr("MTF: preparando ROI a resolución real..."))
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.processEvents(QtCore.QEventLoop.ExcludeUserInputEvents)
        analysis_info = self._mtf_full_resolution_analysis_roi_image(display_roi)
        if analysis_info is None:
            self._fail_mtf_progress(self.tr("No se pudo cargar la ROI."))
            self._update_mtf_result_widgets(error=self.tr("MTF: no se pudo cargar la imagen a resolución real."))
            return
        image = np.asarray(analysis_info["image"], dtype=np.float32)
        analysis_dimensions = analysis_info["analysis_dimensions"]
        display_dimensions = analysis_info["display_dimensions"]
        analysis_roi = analysis_info["analysis_roi"]
        self._mtf_last_analysis_image_dimensions = analysis_dimensions
        self._mtf_last_display_dimensions = display_dimensions
        self._mtf_last_display_roi = display_roi
        if getattr(self, "_mtf_pixel_pitch_auto_source", None) in {None, "manual_sensor_size"}:
            self._apply_mtf_manual_sensor_size_pitch()
        result_key = self._mtf_cache_token(
            {
                "mode": "mtf-result-v1",
                "analysis": self._mtf_roi_analysis_cache_key,
                "analysis_roi": list(analysis_roi),
                "image_shape": list(image.shape),
            }
        )
        cached_result = getattr(self, "_mtf_result_cache", None)
        if self._mtf_result_cache_key == result_key and cached_result is not None:
            result = cached_result
            self._mtf_last_result = result
            self._update_mtf_result_widgets()
            self._persist_mtf_analysis_for_selected()
            elapsed = time.perf_counter() - analysis_started
            self._record_mtf_timing("performance/mtf_analysis_seconds_ewma", elapsed)
            roi_elapsed = getattr(self, "_mtf_progress_roi_elapsed_seconds", None)
            total_elapsed = float(roi_elapsed) + elapsed if roi_elapsed is not None else elapsed
            detail = (
                self.tr("ROI")
                + f" {self._mtf_format_duration(float(roi_elapsed))} + "
                + self.tr("análisis")
                + f" {self._mtf_format_duration(elapsed)}"
                if roi_elapsed is not None
                else self.tr("resultado desde caché")
            )
            self._mtf_progress_roi_elapsed_seconds = None
            self._finish_mtf_progress(
                "complete",
                detail=detail,
                elapsed_seconds=total_elapsed,
            )
            return
        try:
            measured = analyze_slanted_edge_mtf(image, None)
            result = replace(measured, roi=analysis_roi)
        except Exception as exc:
            self._mtf_last_result = None
            self._fail_mtf_progress(str(exc))
            self._update_mtf_result_widgets(error=f"MTF: {exc}")
            return
        self._mtf_result_cache_key = result_key
        self._mtf_result_cache = result
        self._mtf_last_result = result
        self._update_mtf_result_widgets()
        self._persist_mtf_analysis_for_selected()
        elapsed = time.perf_counter() - analysis_started
        self._record_mtf_timing("performance/mtf_analysis_seconds_ewma", elapsed)
        roi_elapsed = getattr(self, "_mtf_progress_roi_elapsed_seconds", None)
        total_elapsed = float(roi_elapsed) + elapsed if roi_elapsed is not None else elapsed
        detail = (
            self.tr("ROI")
            + f" {self._mtf_format_duration(float(roi_elapsed))} + "
            + self.tr("análisis")
            + f" {self._mtf_format_duration(elapsed)}"
            if roi_elapsed is not None
            else self.tr("curvas y métricas actualizadas")
        )
        self._mtf_progress_roi_elapsed_seconds = None
        self._finish_mtf_progress(
            "complete",
            detail=detail,
            elapsed_seconds=total_elapsed,
        )

    def _schedule_mtf_refresh(
        self,
        *,
        interactive: bool | None = None,
        require_auto_update: bool = True,
    ) -> None:
        if getattr(self, "_mtf_roi", None) is None:
            return
        if (
            bool(require_auto_update)
            and (
                not hasattr(self, "check_mtf_auto_update")
                or not self.check_mtf_auto_update.isChecked()
            )
        ):
            return
        if not hasattr(self, "_mtf_refresh_timer"):
            return
        if not self._mtf_roi_overlay_should_be_visible():
            self._mtf_refresh_timer.stop()
            self._mtf_auto_refresh_deferred_until_visible = True
            return
        self._mtf_auto_refresh_deferred_until_visible = False
        if not self._mtf_has_hot_base_roi_cache(self._mtf_roi):
            deferred_key = self._mtf_base_roi_cache_key(self._mtf_roi) or "missing"
            if getattr(self, "_mtf_deferred_auto_refresh_key", None) != deferred_key:
                self._mtf_deferred_auto_refresh_key = deferred_key
                if not bool(getattr(self, "_mtf_base_roi_task_active", False)):
                    self._finish_mtf_progress(
                        "deferred",
                        detail=self.tr("pulsa Actualizar para preparar la ROI full-res"),
                        elapsed_seconds=0.0,
                    )
                self._set_status(
                    self.tr(
                        "MTF: recálculo automático pospuesto; "
                        "pulsa Actualizar para cargar la ROI a resolución real."
                    )
                )
            return
        active = bool(self._is_preview_interaction_active() if interactive is None else interactive)
        delay = self.MTF_INTERACTIVE_REFRESH_DELAY_MS if active else self.MTF_SETTLED_REFRESH_DELAY_MS
        if active and self._mtf_refresh_timer.isActive():
            return
        self._mtf_refresh_timer.start(delay)

    def _maybe_update_mtf_after_preview(self) -> None:
        if not hasattr(self, "_mtf_refresh_timer") or self._mtf_refresh_timer.isActive():
            return
        self._schedule_mtf_refresh(interactive=self._is_preview_interaction_active())

    def _ensure_mtf_analysis_ready_for_sharpness_panel(self) -> None:
        if getattr(self, "_mtf_roi", None) is None:
            return
        if not self._mtf_roi_overlay_should_be_visible():
            return
        if getattr(self, "_mtf_last_result", None) is not None:
            return
        if self._mtf_has_hot_base_roi_cache(self._mtf_roi):
            self._schedule_mtf_refresh(interactive=False, require_auto_update=False)
            return
        if bool(getattr(self, "_mtf_base_roi_task_active", False)):
            return
        self._recalculate_mtf_analysis()

    def _update_mtf_result_widgets(self, *, error: str | None = None) -> None:
        result = getattr(self, "_mtf_last_result", None)
        for plot_name in ("mtf_plot_esf", "mtf_plot_lsf", "mtf_plot_mtf", "mtf_plot_ca"):
            plot = getattr(self, plot_name, None)
            if plot is not None:
                plot.set_result(result)
        self._update_mtf_details_table(result, error=error)
        if not hasattr(self, "mtf_metrics_label"):
            return
        if error:
            self.mtf_metrics_label.setText(error)
            return
        if result is None:
            self.mtf_metrics_label.setText(self.tr("MTF: selecciona una ROI con un borde inclinado."))
            return
        suggestion = self._mtf_suggestion(result)
        details = [suggestion]
        if hasattr(self, "spin_mtf_pixel_pitch_um") and self.spin_mtf_pixel_pitch_um.value() > 0.0:
            details.append(self.tr("lp/mm válido solo si la ROI está a escala 1:1."))
        if result.warnings:
            details.extend(result.warnings)
        self.mtf_metrics_label.setText(" ".join(details))

    def _format_mtf_frequency(self, value: float | None) -> str:
        if value is None:
            return self.tr("no cruza")
        pitch = self.spin_mtf_pixel_pitch_um.value() if hasattr(self, "spin_mtf_pixel_pitch_um") else 0.0
        base = f"{float(value):.3f} c/p"
        if pitch > 0.0:
            lpmm = float(value) * 1000.0 / float(pitch)
            base += f" · {lpmm:.1f} lp/mm"
        return base

    def _format_mtf_cycles(self, value: float | None) -> str:
        if value is None:
            return self.tr("no cruza")
        return f"{float(value):.6f} c/p"

    def _mtf_pixel_pitch_um_value(self) -> float | None:
        if not hasattr(self, "spin_mtf_pixel_pitch_um"):
            return None
        pitch = float(self.spin_mtf_pixel_pitch_um.value())
        return pitch if pitch > 0.0 else None

    def _mtf_lpmm(self, cycles_per_pixel: float | None) -> float | None:
        if cycles_per_pixel is None:
            return None
        pitch = self._mtf_pixel_pitch_um_value()
        if pitch is None:
            return None
        return float(cycles_per_pixel) * 1000.0 / float(pitch)

    def _format_mtf_lpmm(self, cycles_per_pixel: float | None) -> str:
        lpmm = self._mtf_lpmm(cycles_per_pixel)
        return "sin pitch" if lpmm is None else f"{lpmm:.2f} lp/mm"

    def _format_mtf_pixels(self, value: float | None, *, signed: bool = False) -> str:
        if value is None:
            return self.tr("sin dato")
        return f"{float(value):+.4f} px" if signed else f"{float(value):.4f} px"

    def _update_mtf_details_table(self, result: MTFResult | None, *, error: str | None = None) -> None:
        metrics_table = getattr(self, "mtf_metrics_table", None)
        context_table = getattr(self, "mtf_context_table", None)
        if metrics_table is None or context_table is None:
            return
        if error:
            self._populate_mtf_details_table(metrics_table, [(self.tr("Estado"), error)])
            self._populate_mtf_details_table(context_table, [])
            return
        if result is None:
            self._populate_mtf_details_table(metrics_table, [(self.tr("Estado"), self.tr("Sin medición MTF"))])
            self._populate_mtf_details_table(context_table, [])
            return
        self._populate_mtf_details_table(metrics_table, self._mtf_metric_rows(result))
        self._populate_mtf_details_table(context_table, self._mtf_context_rows(result))

    def _populate_mtf_details_table(self, table: QtWidgets.QTableWidget, rows: list[tuple[str, str]]) -> None:
        table.setUpdatesEnabled(False)
        try:
            table.setRowCount(len(rows))
            for row, (key, value) in enumerate(rows):
                key_item = QtWidgets.QTableWidgetItem(str(key))
                value_item = QtWidgets.QTableWidgetItem(str(value))
                key_item.setFlags(key_item.flags() & ~QtCore.Qt.ItemIsEditable)
                value_item.setFlags(value_item.flags() & ~QtCore.Qt.ItemIsEditable)
                table.setItem(row, 0, key_item)
                table.setItem(row, 1, value_item)
        finally:
            table.setUpdatesEnabled(True)

    def _mtf_metric_rows(self, result: MTFResult) -> list[tuple[str, str]]:
        post = self._mtf_post_nyquist_metrics(result)
        rows: list[tuple[str, str]] = [
            (self.tr("MTF50"), f"{self._format_mtf_cycles(result.mtf50)} | {self._format_mtf_lpmm(result.mtf50)}"),
            (self.tr("MTF50P"), f"{self._format_mtf_cycles(result.mtf50p)} | {self._format_mtf_lpmm(result.mtf50p)}"),
            (self.tr("MTF30"), f"{self._format_mtf_cycles(result.mtf30)} | {self._format_mtf_lpmm(result.mtf30)}"),
            (self.tr("MTF10"), f"{self._format_mtf_cycles(result.mtf10)} | {self._format_mtf_lpmm(result.mtf10)}"),
            (self.tr("Nyquist"), f"0.500000 c/p | {self._format_mtf_lpmm(0.5)}"),
            (self.tr("Acutancia"), f"{float(result.acutance):.6f}"),
            (self.tr("CA area"), self._format_mtf_pixels(getattr(result, "ca_area_pixels", None))),
            (self.tr("CA cruce max"), self._format_mtf_pixels(getattr(result, "ca_crossing_pixels", None))),
            (self.tr("CA R-G"), self._format_mtf_pixels(getattr(result, "ca_red_green_shift_pixels", None), signed=True)),
            (self.tr("CA B-G"), self._format_mtf_pixels(getattr(result, "ca_blue_green_shift_pixels", None), signed=True)),
            (self.tr("CA R-B"), self._format_mtf_pixels(getattr(result, "ca_red_blue_shift_pixels", None), signed=True)),
            (self.tr("Borde 10-90 RGB"), self._format_mtf_pixels(getattr(result, "ca_edge_width_10_90_pixels", None))),
            (self.tr("Ángulo de borde"), f"{float(result.edge_angle_degrees):.3f}°"),
            (self.tr("Contraste de borde"), f"{float(result.edge_contrast):.6f}"),
            (self.tr("Sobreimpulso / subimpulso"), f"{float(result.overshoot) * 100.0:.3f}% / {float(result.undershoot) * 100.0:.3f}%"),
        ]
        if post["samples"] > 0:
            rows.extend(
                [
                    (
                        self.tr("Post-Nyquist rango"),
                        f"{post['min_frequency']:.6f} - {post['max_frequency']:.6f} c/p ({int(post['samples'])} muestras)",
                    ),
                    (
                        self.tr("Post-Nyquist pico"),
                        f"{post['peak_modulation']:.6f} @ {post['peak_frequency']:.6f} c/p | {self._format_mtf_lpmm(post['peak_frequency'])}",
                    ),
                    (self.tr("Post-Nyquist media"), f"{post['mean_modulation']:.6f}"),
                    (self.tr("Post-Nyquist RMS"), f"{post['rms_modulation']:.6f}"),
                    (self.tr("Energía post/Nyquist"), f"{post['energy_ratio']:.6f}"),
                ]
            )
        else:
            rows.append((self.tr("Post-Nyquist"), self.tr("sin muestras extendidas")))
        return rows

    def _mtf_context_rows(self, result: MTFResult) -> list[tuple[str, str]]:
        pitch = self._mtf_pixel_pitch_um_value()
        image_dimensions = self._mtf_analysis_image_dimensions() or self._mtf_current_image_dimensions()
        display_dimensions = getattr(self, "_mtf_last_display_dimensions", None) or self._mtf_current_image_dimensions()
        source = getattr(self, "_selected_file", None)
        roi_x, roi_y, roi_w, roi_h = result.roi
        rows: list[tuple[str, str]] = [
            (self.tr("Fuente"), str(source) if source is not None else self.tr("preview actual")),
            (self.tr("Imagen análisis"), f"{image_dimensions[0]} x {image_dimensions[1]} px" if image_dimensions else self.tr("no disponible")),
            (self.tr("Imagen visor"), f"{display_dimensions[0]} x {display_dimensions[1]} px" if display_dimensions else self.tr("no disponible")),
            (self.tr("ROI"), f"x={roi_x}, y={roi_y}, w={roi_w}, h={roi_h} px"),
            (self.tr("ROI muestras"), f"{int(result.roi_shape[1])} x {int(result.roi_shape[0])} px ({int(result.roi_shape[0]) * int(result.roi_shape[1])})"),
            (self.tr("Pitch píxel"), f"{pitch:.6f} µm ({self._mtf_pixel_pitch_auto_source or 'manual'})" if pitch is not None else self.tr("sin dato")),
            (self.tr("Muestras ESF"), str(len(result.esf))),
            (self.tr("Muestras LSF"), str(len(result.lsf))),
            (self.tr("Muestras MTF"), str(len(result.mtf))),
            (self.tr("Muestras MTF extendida"), str(len(self._mtf_limited_extended_frequencies(result)))),
            (self.tr("Muestras CA lateral"), str(len(getattr(result, "ca_distance", []) or []))),
            (self.tr("Rango frecuencia MTF"), self._mtf_frequency_range_label(result)),
            (self.tr("Rango frecuencia extendida"), self._mtf_extended_frequency_range_label(result)),
            (self.tr("Nota post-Nyquist"), self.tr("diagnóstico exploratorio; no interpretar como resolución real por encima del límite de muestreo")),
            (self.tr("Advertencias"), " | ".join(result.warnings) if result.warnings else self.tr("ninguna")),
        ]
        display_roi = getattr(self, "_mtf_last_display_roi", None)
        if display_roi is not None and tuple(display_roi) != tuple(result.roi):
            x, y, w, h = [int(v) for v in display_roi]
            rows.insert(4, (self.tr("ROI visor"), f"x={x}, y={y}, w={w}, h={h} px"))
        return rows

    def _mtf_frequency_range_label(self, result: MTFResult) -> str:
        values = [float(v) for v in result.frequency if np.isfinite(float(v))]
        if not values:
            return self.tr("sin datos")
        return f"{min(values):.6f} - {max(values):.6f} c/p"

    def _mtf_extended_frequency_range_label(self, result: MTFResult) -> str:
        values = self._mtf_limited_extended_frequencies(result)
        if not values:
            return self.tr("sin datos")
        return f"{min(values):.6f} - {max(values):.6f} c/p"

    def _mtf_limited_extended_frequencies(self, result: MTFResult) -> list[float]:
        max_extended = float(self.MTF_EXTENDED_ANALYSIS_MAX_FREQUENCY)
        return [
            float(v)
            for v in getattr(result, "frequency_extended", [])
            if np.isfinite(float(v)) and float(v) <= max_extended
        ]

    def _mtf_post_nyquist_metrics(self, result: MTFResult) -> dict[str, float | int]:
        freq = np.asarray(getattr(result, "frequency_extended", []) or [], dtype=np.float64)
        mtf = np.asarray(getattr(result, "mtf_extended", []) or [], dtype=np.float64)
        valid = np.isfinite(freq) & np.isfinite(mtf)
        freq = freq[valid]
        mtf = mtf[valid]
        max_extended = float(self.MTF_EXTENDED_ANALYSIS_MAX_FREQUENCY)
        post_mask = (freq > 0.5) & (freq <= max_extended)
        if int(np.count_nonzero(post_mask)) == 0:
            return {"samples": 0}
        post_freq = freq[post_mask]
        post_mtf = np.clip(mtf[post_mask], 0.0, 2.0)
        peak_idx = int(np.argmax(post_mtf))
        in_mask = freq <= 0.5
        in_energy = float(np.trapezoid(np.clip(mtf[in_mask], 0.0, 2.0), freq[in_mask])) if int(np.count_nonzero(in_mask)) > 1 else 0.0
        post_energy = float(np.trapezoid(post_mtf, post_freq)) if post_freq.size > 1 else 0.0
        return {
            "samples": int(post_freq.size),
            "min_frequency": float(np.min(post_freq)),
            "max_frequency": float(np.max(post_freq)),
            "peak_frequency": float(post_freq[peak_idx]),
            "peak_modulation": float(post_mtf[peak_idx]),
            "mean_modulation": float(np.mean(post_mtf)),
            "rms_modulation": float(np.sqrt(np.mean(post_mtf * post_mtf))),
            "energy": post_energy,
            "energy_ratio": post_energy / in_energy if in_energy > 1e-12 else 0.0,
        }

    def _mtf_analysis_payload(self, *, include_curves: bool = True) -> dict[str, Any] | None:
        result = getattr(self, "_mtf_last_result", None)
        if result is None:
            return None
        pitch = self._mtf_pixel_pitch_um_value()
        image_dimensions = self._mtf_analysis_image_dimensions() or self._mtf_current_image_dimensions()
        display_dimensions = getattr(self, "_mtf_last_display_dimensions", None) or self._mtf_current_image_dimensions()
        selected = getattr(self, "_selected_file", None)
        summary = result.summary()
        post_nyquist = self._mtf_post_nyquist_metrics(result)
        limited_extended_frequencies = self._mtf_limited_extended_frequencies(result)
        display_roi = getattr(self, "_mtf_last_display_roi", None) or getattr(self, "_mtf_roi", None)
        summary.update(
            {
                "source": str(selected) if selected is not None else "",
                "measured_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                "image_dimensions_px": list(image_dimensions) if image_dimensions else None,
                "display_dimensions_px": list(display_dimensions) if display_dimensions else None,
                "display_roi": list(display_roi) if display_roi is not None else None,
                "pixel_pitch_um": pitch,
                "pixel_pitch_source": self._mtf_pixel_pitch_auto_source,
                "nyquist_cycles_per_pixel": 0.5,
                "nyquist_lp_per_mm": self._mtf_lpmm(0.5),
                "mtf50_lp_per_mm": self._mtf_lpmm(result.mtf50),
                "mtf50p_lp_per_mm": self._mtf_lpmm(result.mtf50p),
                "mtf30_lp_per_mm": self._mtf_lpmm(result.mtf30),
                "mtf10_lp_per_mm": self._mtf_lpmm(result.mtf10),
                "esf_samples": len(result.esf),
                "lsf_samples": len(result.lsf),
                "mtf_samples": len(result.mtf),
                "mtf_extended_samples": len(limited_extended_frequencies),
                "frequency_range_cycles_per_pixel": [
                    min(result.frequency) if result.frequency else None,
                    max(result.frequency) if result.frequency else None,
                ],
                "extended_frequency_range_cycles_per_pixel": [
                    min(limited_extended_frequencies) if limited_extended_frequencies else None,
                    max(limited_extended_frequencies) if limited_extended_frequencies else None,
                ],
                "post_nyquist": post_nyquist,
                "analysis_source": "full_resolution_image_data",
                "scale_note": "MTF is calculated from full-resolution image data; lp/mm depends on the pixel pitch value",
                "post_nyquist_note": "values above 0.5 cycles/pixel are exploratory diagnostics for aliasing, harmonics or processing artifacts; they are not physical resolution beyond sampling Nyquist",
            }
        )
        payload: dict[str, Any] = {"summary": summary}
        if include_curves:
            payload["curves"] = {
                "esf": [
                    {"distance_px": x, "signal": y}
                    for x, y in zip(result.esf_distance, result.esf, strict=False)
                ],
                "lsf": [
                    {"distance_px": x, "derivative": y}
                    for x, y in zip(result.lsf_distance, result.lsf, strict=False)
                ],
                "mtf": [
                    {"frequency_cycles_per_pixel": x, "modulation": y, "frequency_lp_per_mm": self._mtf_lpmm(x)}
                    for x, y in zip(result.frequency, result.mtf, strict=False)
                ],
                "mtf_extended": [
                    {
                        "frequency_cycles_per_pixel": x,
                        "modulation": y,
                        "frequency_lp_per_mm": self._mtf_lpmm(x),
                        "post_nyquist": bool(float(x) > 0.5),
                    }
                    for x, y in zip(
                        getattr(result, "frequency_extended", []) or [],
                        getattr(result, "mtf_extended", []) or [],
                        strict=False,
                    )
                    if float(x) <= float(self.MTF_EXTENDED_ANALYSIS_MAX_FREQUENCY)
                ],
                "chromatic_aberration": [
                    {"distance_px": x, "red": r, "green": g, "blue": b, "difference": d}
                    for x, r, g, b, d in zip(
                        getattr(result, "ca_distance", []) or [],
                        getattr(result, "ca_red", []) or [],
                        getattr(result, "ca_green", []) or [],
                        getattr(result, "ca_blue", []) or [],
                        getattr(result, "ca_diff", []) or [],
                        strict=False,
                    )
                ],
                "chromatic_aberration_pixels": [
                    {"distance_px": x, "red": r, "green": g, "blue": b}
                    for x, r, g, b in zip(
                        getattr(result, "ca_pixel_distance", []) or [],
                        getattr(result, "ca_pixel_red", []) or [],
                        getattr(result, "ca_pixel_green", []) or [],
                        getattr(result, "ca_pixel_blue", []) or [],
                        strict=False,
                    )
                ],
            }
        return payload

    def _persist_mtf_analysis_for_selected(self) -> None:
        selected = getattr(self, "_selected_file", None)
        if selected is None:
            return
        if hasattr(self, "_is_preview_interaction_active") and self._is_preview_interaction_active():
            timer = getattr(self, "_mtf_persist_timer", None)
            if timer is not None:
                timer.start(600)
            return
        payload = self._mtf_analysis_payload(include_curves=True)
        if payload is None:
            return
        session_name = self.session_name_edit.text().strip() if hasattr(self, "session_name_edit") else ""
        payload_key = self._mtf_cache_token(
            {
                "path": self._normalized_path_key(Path(selected)) if hasattr(self, "_normalized_path_key") else str(Path(selected)),
                "session_root": str(getattr(self, "_active_session_root", "") or ""),
                "session_name": session_name,
                "payload": payload,
            }
        )
        if getattr(self, "_mtf_persisted_payload_key", None) == payload_key:
            return
        try:
            write_raw_mtf_analysis(
                Path(selected),
                payload,
                session_root=getattr(self, "_active_session_root", None),
                session_name=session_name,
            )
        except Exception as exc:
            self._log_preview(f"Aviso: no se pudo guardar MTF en sidecar: {exc}")
            return
        if hasattr(self, "_invalidate_raw_sidecar_cache_for_path"):
            self._invalidate_raw_sidecar_cache_for_path(Path(selected))
        self._mtf_persisted_payload_key = payload_key
        self._refresh_mtf_sidecar_indicator_for_path(Path(selected))
        self._set_status(self.tr("MTF guardada en sidecar:") + f" {Path(selected).name}")

    def _refresh_mtf_sidecar_indicator_for_path(self, path: Path) -> None:
        if not hasattr(self, "file_list"):
            return
        key = self._normalized_path_key(path)
        item = self._file_items_by_key.get(key)
        if item is None or self.file_list.row(item) < 0:
            return
        item.setToolTip(self._file_item_tooltip(path))

    def _load_persisted_mtf_analysis(self, path: Path) -> dict[str, Any] | None:
        if hasattr(self, "_cached_raw_sidecar_payload"):
            sidecar = self._cached_raw_sidecar_payload(path)
        else:
            try:
                sidecar = load_raw_sidecar(path)
            except Exception:
                sidecar = None
        if sidecar is None:
            return None
        payload = sidecar.get("mtf_analysis")
        return payload if isinstance(payload, dict) else None

    def _raw_sidecar_mtf_summary(self, path: Path) -> str:
        payload = self._load_persisted_mtf_analysis(path)
        summary = payload.get("summary") if isinstance(payload, dict) and isinstance(payload.get("summary"), dict) else {}
        if not summary:
            return ""
        mtf50 = self._format_persisted_mtf_number(summary.get("mtf50"), decimals=3, suffix=" c/p")
        mtf50_lpmm = self._format_persisted_mtf_number(summary.get("mtf50_lp_per_mm"), decimals=1, suffix=" lp/mm")
        parts = [part for part in (mtf50, mtf50_lpmm) if part]
        return self.tr("MTF guardada") + (": MTF50 " + " | ".join(parts) if parts else "")

    def _format_persisted_mtf_number(self, value: Any, *, decimals: int, suffix: str = "") -> str:
        if value is None:
            return ""
        try:
            number = float(value)
        except (TypeError, ValueError):
            return ""
        if not np.isfinite(number):
            return ""
        return f"{number:.{decimals}f}{suffix}"

    def _compare_mtf_for_selected_thumbnails(self) -> None:
        files = self._collect_selected_file_paths() if hasattr(self, "_collect_selected_file_paths") else []
        if len(files) != 2:
            QtWidgets.QMessageBox.information(
                self,
                self.tr("Comparar MTF"),
                self.tr("Selecciona exactamente dos miniaturas con datos MTF guardados."),
            )
            return
        left_path, right_path = files
        left_payload = self._load_persisted_mtf_analysis(left_path)
        right_payload = self._load_persisted_mtf_analysis(right_path)
        missing = [
            path.name
            for path, payload in ((left_path, left_payload), (right_path, right_payload))
            if payload is None
        ]
        if missing:
            QtWidgets.QMessageBox.information(
                self,
                self.tr("Comparar MTF"),
                self.tr("No hay MTF guardada para:") + " " + ", ".join(missing),
            )
            return
        self._show_mtf_comparison_dialog(left_path, left_payload, right_path, right_payload)

    def _show_mtf_comparison_dialog(
        self,
        left_path: Path,
        left_payload: dict[str, Any],
        right_path: Path,
        right_payload: dict[str, Any],
    ) -> None:
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(self.tr("Comparación MTF"))
        dialog.resize(860, 560)
        layout = QtWidgets.QVBoxLayout(dialog)
        tabs = QtWidgets.QTabWidget()
        table = QtWidgets.QTableWidget(0, 4)
        table.setHorizontalHeaderLabels([
            self.tr("Dato"),
            left_path.name,
            right_path.name,
            self.tr("Diferencia segunda - primera"),
        ])
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        rows = self._mtf_comparison_rows(left_path, left_payload, right_path, right_payload)
        table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
                table.setItem(row, column, item)
        tabs.addTab(table, self.tr("Métricas MTF"))
        for label, curve in (("ESF", "esf"), ("LSF", "lsf"), ("MTF", "mtf"), (self.tr("CA lateral"), "ca")):
            plot = MTFComparisonPlotWidget(curve)
            plot.set_payloads([(left_path.name, left_payload), (right_path.name, right_payload)])
            tabs.addTab(plot, label)
        layout.addWidget(tabs, 1)
        close = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        close.rejected.connect(dialog.reject)
        layout.addWidget(close)
        dialog.exec()

    def _mtf_comparison_rows(
        self,
        left_path: Path,
        left_payload: dict[str, Any],
        right_path: Path,
        right_payload: dict[str, Any],
    ) -> list[tuple[str, str, str, str]]:
        left_summary = self._mtf_payload_summary(left_payload)
        right_summary = self._mtf_payload_summary(right_payload)
        rows: list[tuple[str, str, str, str]] = [
            (self.tr("Archivo"), left_path.name, right_path.name, ""),
            (
                self.tr("Medición"),
                str(left_summary.get("measured_at") or self.tr("sin dato")),
                str(right_summary.get("measured_at") or self.tr("sin dato")),
                "",
            ),
            (
                self.tr("ROI"),
                self._format_mtf_comparison_roi(left_summary.get("roi")),
                self._format_mtf_comparison_roi(right_summary.get("roi")),
                "",
            ),
        ]
        specs: list[tuple[str, tuple[str, ...], int, str, float]] = [
            (self.tr("MTF50"), ("mtf50",), 6, " c/p", 1.0),
            (self.tr("MTF50"), ("mtf50_lp_per_mm",), 2, " lp/mm", 1.0),
            (self.tr("MTF50P"), ("mtf50p",), 6, " c/p", 1.0),
            (self.tr("MTF50P"), ("mtf50p_lp_per_mm",), 2, " lp/mm", 1.0),
            (self.tr("MTF30"), ("mtf30",), 6, " c/p", 1.0),
            (self.tr("MTF30"), ("mtf30_lp_per_mm",), 2, " lp/mm", 1.0),
            (self.tr("MTF10"), ("mtf10",), 6, " c/p", 1.0),
            (self.tr("MTF10"), ("mtf10_lp_per_mm",), 2, " lp/mm", 1.0),
            (self.tr("Nyquist"), ("nyquist_lp_per_mm",), 2, " lp/mm", 1.0),
            (self.tr("Acutancia"), ("acutance",), 6, "", 1.0),
            (self.tr("Ángulo de borde"), ("edge_angle_degrees",), 3, "°", 1.0),
            (self.tr("Contraste de borde"), ("edge_contrast",), 6, "", 1.0),
            (self.tr("Sobreimpulso"), ("overshoot",), 3, "%", 100.0),
            (self.tr("Subimpulso"), ("undershoot",), 3, "%", 100.0),
            (self.tr("CA area"), ("chromatic_aberration", "area_pixels"), 4, " px", 1.0),
            (self.tr("CA cruce max"), ("chromatic_aberration", "crossing_pixels"), 4, " px", 1.0),
            (self.tr("CA R-G"), ("chromatic_aberration", "red_green_shift_pixels"), 4, " px", 1.0),
            (self.tr("CA B-G"), ("chromatic_aberration", "blue_green_shift_pixels"), 4, " px", 1.0),
            (self.tr("Post-Nyquist pico"), ("post_nyquist", "peak_frequency"), 6, " c/p", 1.0),
            (self.tr("Post-Nyquist pico"), ("post_nyquist", "peak_modulation"), 6, "", 1.0),
            (self.tr("Energía post/Nyquist"), ("post_nyquist", "energy_ratio"), 6, "", 1.0),
        ]
        for label, key_path, decimals, suffix, factor in specs:
            left_value = self._mtf_nested_number(left_summary, key_path)
            right_value = self._mtf_nested_number(right_summary, key_path)
            rows.append(
                (
                    f"{label} ({suffix.strip()})" if suffix.strip() else label,
                    self._format_mtf_comparison_value(left_value, decimals=decimals, suffix=suffix, factor=factor),
                    self._format_mtf_comparison_value(right_value, decimals=decimals, suffix=suffix, factor=factor),
                    self._format_mtf_comparison_delta(left_value, right_value, decimals=decimals, suffix=suffix, factor=factor),
                )
            )
        return rows

    def _mtf_payload_summary(self, payload: dict[str, Any]) -> dict[str, Any]:
        summary = payload.get("summary") if isinstance(payload, dict) else None
        return summary if isinstance(summary, dict) else {}

    def _mtf_nested_number(self, summary: dict[str, Any], key_path: tuple[str, ...]) -> float | None:
        value: Any = summary
        for key in key_path:
            if not isinstance(value, dict):
                return None
            value = value.get(key)
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if np.isfinite(number) else None

    def _format_mtf_comparison_roi(self, value: Any) -> str:
        if isinstance(value, (list, tuple)) and len(value) == 4:
            try:
                x, y, w, h = [int(round(float(v))) for v in value]
            except (TypeError, ValueError):
                return str(value)
            return f"x={x}, y={y}, w={w}, h={h} px"
        return self.tr("sin dato")

    def _format_mtf_comparison_value(
        self,
        value: float | None,
        *,
        decimals: int,
        suffix: str,
        factor: float,
    ) -> str:
        if value is None:
            return self.tr("sin dato")
        return f"{float(value) * float(factor):.{decimals}f}{suffix}"

    def _format_mtf_comparison_delta(
        self,
        left: float | None,
        right: float | None,
        *,
        decimals: int,
        suffix: str,
        factor: float,
    ) -> str:
        if left is None or right is None:
            return ""
        return f"{(float(right) - float(left)) * float(factor):+.{decimals}f}{suffix}"

    def _copy_mtf_analysis_data(self) -> None:
        payload = self._mtf_analysis_payload(include_curves=True)
        if payload is None:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("No hay medición MTF para copiar."))
            return
        app = QtWidgets.QApplication.instance()
        if app is None:
            return
        app.clipboard().setText(json.dumps(payload, indent=2, ensure_ascii=False))
        self._set_status(self.tr("Datos MTF copiados al portapapeles"))

    def _export_mtf_analysis_csv(self) -> None:
        payload = self._mtf_analysis_payload(include_curves=True)
        if payload is None:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("No hay medición MTF para exportar."))
            return
        default = self._mtf_default_export_path()
        path_text, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            self.tr("Exportar MTF CSV"),
            str(default),
            "CSV (*.csv);;Todos (*)",
        )
        if not path_text:
            return
        path = Path(path_text).expanduser()
        path.write_text(self._mtf_payload_to_csv(payload), encoding="utf-8")
        self._set_status(self.tr("Datos MTF exportados:") + f" {path}")

    def _mtf_default_export_path(self) -> Path:
        selected = getattr(self, "_selected_file", None)
        stem = Path(selected).stem if selected is not None else "mtf"
        if getattr(self, "_active_session_root", None) is not None:
            try:
                return self._session_paths_from_root(self._active_session_root)["work"] / f"{stem}_mtf.csv"
            except Exception:
                pass
        return Path.cwd() / f"{stem}_mtf.csv"

    def _mtf_payload_to_csv(self, payload: dict[str, Any]) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["section", "index", "x", "y", "key", "value"])
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        for key, value in summary.items():
            writer.writerow(["summary", "", "", "", key, json.dumps(value, ensure_ascii=False)])
        curves = payload.get("curves") if isinstance(payload.get("curves"), dict) else {}
        for idx, point in enumerate(curves.get("esf", []) or []):
            writer.writerow(["esf", idx, point.get("distance_px"), point.get("signal"), "", ""])
        for idx, point in enumerate(curves.get("lsf", []) or []):
            writer.writerow(["lsf", idx, point.get("distance_px"), point.get("derivative"), "", ""])
        for idx, point in enumerate(curves.get("mtf", []) or []):
            writer.writerow([
                "mtf",
                idx,
                point.get("frequency_cycles_per_pixel"),
                point.get("modulation"),
                "frequency_lp_per_mm",
                point.get("frequency_lp_per_mm"),
            ])
        for idx, point in enumerate(curves.get("mtf_extended", []) or []):
            writer.writerow([
                "mtf_extended",
                idx,
                point.get("frequency_cycles_per_pixel"),
                point.get("modulation"),
                "post_nyquist",
                point.get("post_nyquist"),
            ])
        for idx, point in enumerate(curves.get("chromatic_aberration", []) or []):
            writer.writerow([
                "chromatic_aberration",
                idx,
                point.get("distance_px"),
                point.get("difference"),
                "rgb",
                json.dumps(
                    {
                        "red": point.get("red"),
                        "green": point.get("green"),
                        "blue": point.get("blue"),
                    },
                    ensure_ascii=False,
                ),
            ])
        for idx, point in enumerate(curves.get("chromatic_aberration_pixels", []) or []):
            writer.writerow([
                "chromatic_aberration_pixels",
                idx,
                point.get("distance_px"),
                "",
                "rgb",
                json.dumps(
                    {
                        "red": point.get("red"),
                        "green": point.get("green"),
                        "blue": point.get("blue"),
                    },
                    ensure_ascii=False,
                ),
            ])
        return output.getvalue()

    def _mtf_suggestion(self, result: MTFResult) -> str:
        halo = max(float(result.overshoot), float(result.undershoot))
        if halo > 0.10:
            return self.tr("Sugerencia: reduce acutancia o radio; hay halo/sobreimpulso.")
        if result.mtf50 is not None and result.mtf50 < 0.15 and halo < 0.04:
            return self.tr("Sugerencia: puedes probar más acutancia con radio bajo.")
        return self.tr("Sugerencia: ajuste equilibrado para esta ROI.")

    def _show_mtf_expanded_dialog(self) -> None:
        result = getattr(self, "_mtf_last_result", None)
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(self.tr("Análisis MTF"))
        dialog.resize(980, 720)
        layout = QtWidgets.QVBoxLayout(dialog)
        tabs = QtWidgets.QTabWidget()
        for label, curve in (("ESF", "esf"), ("LSF", "lsf"), ("MTF", "mtf"), (self.tr("CA lateral"), "ca")):
            plot = MTFPlotWidget(curve)
            plot.setMinimumHeight(560)
            plot.set_result(result)
            tabs.addTab(plot, label)
        layout.addWidget(tabs, 1)
        summary = QtWidgets.QLabel(self.mtf_metrics_label.text() if hasattr(self, "mtf_metrics_label") else "")
        summary.setWordWrap(True)
        layout.addWidget(summary)
        close = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        close.rejected.connect(dialog.reject)
        layout.addWidget(close)
        dialog.exec()
