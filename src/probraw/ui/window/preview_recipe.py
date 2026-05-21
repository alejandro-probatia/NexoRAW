from __future__ import annotations

from ._imports import *  # noqa: F401,F403


class PreviewRecipeMixin:
    def _apply_recipe_to_controls(self, recipe: Recipe) -> None:
        raw_autosave_suspend = int(getattr(self, "_suspend_raw_export_autosave", 0) or 0)
        self._suspend_raw_export_autosave = raw_autosave_suspend + 1
        try:
            self._set_combo_data(self.combo_raw_developer, recipe.raw_developer)
            self._set_combo_data(
                self.combo_demosaic,
                self._supported_gui_demosaic(recipe.demosaic_algorithm, notify=True),
            )
            if hasattr(self, "spin_demosaic_edge_quality"):
                self.spin_demosaic_edge_quality.setValue(max(0, int(getattr(recipe, "demosaic_edge_quality", 0) or 0)))
            if hasattr(self, "spin_false_color_suppression"):
                self.spin_false_color_suppression.setValue(
                    max(0, int(getattr(recipe, "false_color_suppression_steps", 0) or 0))
                )
            if hasattr(self, "check_four_color_rgb"):
                self.check_four_color_rgb.setChecked(bool(getattr(recipe, "four_color_rgb", False)))
            self._apply_libraw_render_controls(recipe)
            if hasattr(self, "_update_raw_algorithm_option_state"):
                self._update_raw_algorithm_option_state()
            self._set_combo_data(self.combo_wb_mode, recipe.white_balance_mode)
            self.edit_wb_multipliers.setText(",".join(f"{float(v):.6g}" for v in recipe.wb_multipliers))

            mode, value = self._split_black_mode(recipe.black_level_mode)
            self._set_combo_data(self.combo_black_mode, mode)
            self.spin_black_value.setValue(value)

            self.spin_exposure.setValue(float(recipe.exposure_compensation))

            tone_mode, gamma = self._split_tone_curve(recipe.tone_curve)
            self._set_combo_data(self.combo_tone_curve, tone_mode)
            self.spin_gamma.setValue(gamma)

            self.check_output_linear.setChecked(bool(recipe.output_linear))
            self.check_profiling_mode.setChecked(bool(recipe.profiling_mode))
            self._set_combo_text(self.combo_recipe_denoise, recipe.denoise)
            self._set_combo_text(self.combo_recipe_sharpen, recipe.sharpen)
            self._set_combo_text(self.combo_working_space, recipe.working_space)
            self._set_combo_text(self.combo_output_space, recipe.output_space)
            self._sync_development_output_space_combo(recipe.output_space)
            self._apply_output_space_defaults_to_controls(recipe.output_space)
            self._set_combo_text(self.combo_sampling, recipe.sampling_strategy)
            self.edit_input_color.setText(recipe.input_color_assumption)
            self.edit_illuminant.setText(recipe.illuminant_metadata or "")

            if recipe.argyll_colprof_args:
                self._apply_argyll_args_to_controls(recipe.argyll_colprof_args)
            else:
                self._set_combo_data(self.combo_profile_quality, "m")
                self._set_combo_data(self.combo_profile_algo, "-as")
                self.edit_colprof_args.setText("-u -R")
        finally:
            self._suspend_raw_export_autosave = raw_autosave_suspend

    def _sync_demosaic_capabilities(self) -> None:
        flags = rawpy_feature_flags()
        has_gpl3 = bool(flags.get("DEMOSAIC_PACK_GPL3", False))
        model = self.combo_demosaic.model()
        for i in range(self.combo_demosaic.count()):
            value = str(self.combo_demosaic.itemData(i) or "").strip().lower()
            item = model.item(i) if hasattr(model, "item") else None
            if item is not None:
                item.setEnabled(is_libraw_demosaic_supported(value))
            if value == "amaze":
                suffix = "disponible" if has_gpl3 else "no disponible: requiere rawpy-demosaic/GPL3"
                self.combo_demosaic.setItemText(i, f"AMaZE (GPL3, {suffix})")

    def _on_raw_demosaic_changed(self) -> None:
        self._update_raw_algorithm_option_state()
        self._on_raw_decode_control_changed()

    def _on_raw_decode_control_changed(self) -> None:
        if int(getattr(self, "_suspend_raw_export_autosave", 0) or 0) > 0:
            return
        if hasattr(self, "_push_edit_history_snapshot"):
            self._push_edit_history_snapshot("raw")
        if self._sender_is_libraw_color_control():
            if (
                hasattr(self, "_set_active_named_adjustment_profile_id")
                and self._active_named_adjustment_profile_id("color_contrast")
            ):
                self._set_active_named_adjustment_profile_id("color_contrast", "")
                if hasattr(self, "_refresh_named_adjustment_profile_combo"):
                    self._refresh_named_adjustment_profile_combo("color_contrast")
            if hasattr(self, "_schedule_render_adjustment_sidecar_persist"):
                self._schedule_render_adjustment_sidecar_persist()
        elif hasattr(self, "_schedule_raw_export_sidecar_persist"):
            self._schedule_raw_export_sidecar_persist()
        if getattr(self, "_original_linear", None) is None:
            return
        self._invalidate_preview_cache()
        self._reload_preview_source_for_color_management()

    def _sender_is_libraw_color_control(self) -> bool:
        sender = self.sender()
        names = (
            "check_libraw_auto_bright",
            "spin_libraw_auto_bright_thr",
            "spin_libraw_adjust_maximum_thr",
            "spin_libraw_bright",
            "combo_libraw_highlight_mode",
            "spin_libraw_exp_shift",
            "spin_libraw_exp_preserve_highlights",
            "check_libraw_no_auto_scale",
            "spin_libraw_gamma_power",
            "spin_libraw_gamma_slope",
            "spin_libraw_ca_red",
            "spin_libraw_ca_blue",
            "combo_wb_mode",
            "edit_wb_multipliers",
        )
        return any(sender is getattr(self, name, None) for name in names)

    def _update_raw_algorithm_option_state(self) -> None:
        algorithm = ""
        if hasattr(self, "combo_demosaic"):
            algorithm = str(self.combo_demosaic.currentData() or self.combo_demosaic.currentText()).strip().lower()
        four_color_supported = rawpy_postprocess_parameter_supported("four_color_rgb")
        demosaic_supported = unavailable_demosaic_reason(algorithm) is None if algorithm else False
        edge_supported = demosaic_supported
        false_color_backend_supported = rawpy_postprocess_parameter_supported("median_filter_passes")
        false_color_supported = demosaic_supported

        if hasattr(self, "check_four_color_rgb"):
            self.check_four_color_rgb.setEnabled(four_color_supported)
            self.check_four_color_rgb.setToolTip(
                self.tr("Disponible en rawpy para interpolar los dos canales verdes por separado.")
                if four_color_supported
                else self.tr("La versión instalada de rawpy no expone four_color_rgb.")
            )
        if hasattr(self, "spin_demosaic_edge_quality"):
            self.spin_demosaic_edge_quality.setEnabled(edge_supported)
            if edge_supported:
                self.spin_demosaic_edge_quality.setToolTip(
                    self.tr("Recorta este numero de pixeles en cada borde tras el demosaico.")
                )
            else:
                self.spin_demosaic_edge_quality.setToolTip(
                    self.tr("Activa un metodo de demosaico disponible para aplicar el borde.")
                )
        if hasattr(self, "spin_false_color_suppression"):
            self.spin_false_color_suppression.setEnabled(false_color_supported)
            if false_color_backend_supported:
                self.spin_false_color_suppression.setToolTip(
                    self.tr("Aplicado por LibRaw/rawpy mediante median_filter_passes.")
                )
            elif false_color_supported:
                self.spin_false_color_suppression.setToolTip(
                    self.tr("Aplicado por ProbRAW como filtrado mediano de crominancia tras el demosaico.")
                )
            else:
                self.spin_false_color_suppression.setToolTip(
                    self.tr("Activa un metodo de demosaico disponible para aplicar la supresion de falso color.")
                )
        if hasattr(self, "raw_algorithm_options_status_label"):
            enabled = []
            unavailable = []
            if four_color_supported:
                enabled.append("4 colores")
            else:
                unavailable.append("4 colores")
            if edge_supported:
                enabled.append("borde")
            else:
                unavailable.append("borde")
            if false_color_backend_supported:
                enabled.append("falso color (LibRaw/rawpy)")
            elif false_color_supported:
                enabled.append("falso color (ProbRAW)")
            else:
                unavailable.append("falso color")
            enabled_text = ", ".join(enabled) if enabled else self.tr("ninguna opción adicional")
            unavailable_text = ", ".join(unavailable) if unavailable else self.tr("ninguna")
            self.raw_algorithm_options_status_label.setText(
                self.tr("Opciones disponibles para el método seleccionado: ")
                + enabled_text
                + self.tr(". No disponibles en este backend: ")
                + unavailable_text
                + "."
            )

    def _apply_raw_export_recipe_to_controls(self, recipe: Recipe) -> None:
        raw_autosave_suspend = int(getattr(self, "_suspend_raw_export_autosave", 0) or 0)
        self._suspend_raw_export_autosave = raw_autosave_suspend + 1
        self._set_combo_data(self.combo_raw_developer, recipe.raw_developer)
        self._set_combo_data(
            self.combo_demosaic,
            self._supported_gui_demosaic(recipe.demosaic_algorithm, notify=True),
        )
        if hasattr(self, "spin_demosaic_edge_quality"):
            self.spin_demosaic_edge_quality.setValue(max(0, int(getattr(recipe, "demosaic_edge_quality", 0) or 0)))
        if hasattr(self, "spin_false_color_suppression"):
            self.spin_false_color_suppression.setValue(
                max(0, int(getattr(recipe, "false_color_suppression_steps", 0) or 0))
            )
        if hasattr(self, "check_four_color_rgb"):
            self.check_four_color_rgb.setChecked(bool(getattr(recipe, "four_color_rgb", False)))
        self._apply_libraw_render_controls(recipe)
        mode, value = self._split_black_mode(recipe.black_level_mode)
        self._set_combo_data(self.combo_black_mode, mode)
        self.spin_black_value.setValue(value)
        self._update_raw_algorithm_option_state()
        self._suspend_raw_export_autosave = raw_autosave_suspend

    def _supported_gui_demosaic(self, demosaic_algorithm: str, *, notify: bool) -> str:
        requested = str(demosaic_algorithm or "dcb").strip().lower()
        reason = unavailable_demosaic_reason(requested)
        if reason is None:
            return requested
        if notify:
            self._log_preview(f"Aviso: {reason} Se usa DCB en la GUI hasta instalar soporte GPL.")
        return "dcb"

    def _apply_libraw_render_controls(self, recipe: Recipe) -> None:
        if hasattr(self, "combo_wb_mode"):
            self._set_combo_data(self.combo_wb_mode, str(getattr(recipe, "white_balance_mode", "fixed")))
        if hasattr(self, "edit_wb_multipliers"):
            self.edit_wb_multipliers.setText(",".join(f"{float(v):.6g}" for v in getattr(recipe, "wb_multipliers", [1.0, 1.0, 1.0, 1.0])))
        if hasattr(self, "check_libraw_auto_bright"):
            self.check_libraw_auto_bright.setChecked(bool(getattr(recipe, "libraw_auto_bright", False)))
        if hasattr(self, "spin_libraw_auto_bright_thr"):
            self.spin_libraw_auto_bright_thr.setValue(float(getattr(recipe, "libraw_auto_bright_thr", 0.01)))
        if hasattr(self, "spin_libraw_adjust_maximum_thr"):
            self.spin_libraw_adjust_maximum_thr.setValue(float(getattr(recipe, "libraw_adjust_maximum_thr", 0.75)))
        if hasattr(self, "spin_libraw_bright"):
            self.spin_libraw_bright.setValue(float(getattr(recipe, "libraw_bright", 1.0)))
        if hasattr(self, "combo_libraw_highlight_mode"):
            self._set_combo_data(self.combo_libraw_highlight_mode, str(getattr(recipe, "libraw_highlight_mode", "clip")))
        if hasattr(self, "spin_libraw_exp_shift"):
            self.spin_libraw_exp_shift.setValue(float(getattr(recipe, "libraw_exp_shift", 1.0)))
        if hasattr(self, "spin_libraw_exp_preserve_highlights"):
            self.spin_libraw_exp_preserve_highlights.setValue(float(getattr(recipe, "libraw_exp_preserve_highlights", 0.0)))
        if hasattr(self, "check_libraw_no_auto_scale"):
            self.check_libraw_no_auto_scale.setChecked(bool(getattr(recipe, "libraw_no_auto_scale", False)))
        if hasattr(self, "spin_libraw_gamma_power"):
            self.spin_libraw_gamma_power.setValue(float(getattr(recipe, "libraw_gamma_power", 1.0)))
        if hasattr(self, "spin_libraw_gamma_slope"):
            self.spin_libraw_gamma_slope.setValue(float(getattr(recipe, "libraw_gamma_slope", 1.0)))
        if hasattr(self, "spin_libraw_ca_red"):
            self.spin_libraw_ca_red.setValue(float(getattr(recipe, "libraw_chromatic_aberration_red", 1.0)))
        if hasattr(self, "spin_libraw_ca_blue"):
            self.spin_libraw_ca_blue.setValue(float(getattr(recipe, "libraw_chromatic_aberration_blue", 1.0)))

    def _reset_libraw_color_adjustments(self) -> None:
        self._apply_libraw_render_controls(Recipe())
        if hasattr(self, "_schedule_render_adjustment_sidecar_persist"):
            self._schedule_render_adjustment_sidecar_persist(immediate=True)
        if getattr(self, "_original_linear", None) is not None:
            self._invalidate_preview_cache()
            self._reload_preview_source_for_color_management()

    def _balanced_preview_demosaic(self) -> str:
        for candidate in PREVIEW_BALANCED_DEMOSAIC_ORDER:
            if unavailable_demosaic_reason(candidate) is None:
                return candidate
        return self._supported_gui_demosaic("dcb", notify=False)

    def _preview_requires_max_quality(self) -> bool:
        return True

    def _split_black_mode(self, value: str) -> tuple[str, int]:
        txt = (value or "metadata").strip().lower()
        if txt.startswith("fixed:"):
            try:
                return "fixed", int(txt.split(":", 1)[1])
            except Exception:
                return "fixed", 0
        if txt.startswith("white:"):
            try:
                return "white", int(txt.split(":", 1)[1])
            except Exception:
                return "white", 0
        return "metadata", 0

    def _split_tone_curve(self, value: str) -> tuple[str, float]:
        txt = (value or "linear").strip().lower()
        if txt.startswith("gamma:"):
            try:
                return "gamma", float(txt.split(":", 1)[1])
            except Exception:
                return "gamma", 2.2
        if txt == "srgb":
            return "srgb", 2.2
        return "linear", 2.2

    def _apply_argyll_args_to_controls(self, args: list[str]) -> None:
        quality = None
        algo = None
        extra: list[str] = []
        for a in args:
            if a.startswith("-q") and len(a) == 3:
                quality = a[-1]
            elif a in {"-as", "-ag", "-am", "-al", "-ax"}:
                algo = a
            else:
                extra.append(a)
        if "-u" not in args:
            extra.append("-u")
        if "-R" not in args:
            extra.append("-R")
        if quality is not None:
            self._set_combo_data(self.combo_profile_quality, quality)
        if algo is not None:
            self._set_combo_data(self.combo_profile_algo, algo)
        self.edit_colprof_args.setText(" ".join(extra))

    def _set_combo_data(self, combo: QtWidgets.QComboBox, data_value: str) -> None:
        for i in range(combo.count()):
            if str(combo.itemData(i)) == str(data_value):
                combo.setCurrentIndex(i)
                return
        self._set_combo_text(combo, str(data_value))

    def _set_combo_text(self, combo: QtWidgets.QComboBox, text: str) -> None:
        idx = combo.findText(str(text), QtCore.Qt.MatchFixedString)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _tone_curve_preset_points(self, key: str) -> list[tuple[float, float]]:
        for _label, preset_key, points in TONE_CURVE_PRESETS:
            if preset_key == key:
                return list(points)
        return [(0.0, 0.0), (1.0, 1.0)]

    def _tone_curve_preset_key(self) -> str:
        return str(self.combo_tone_curve_preset.currentData() or "linear")

    def _tone_curve_channel_key(self) -> str:
        combo = getattr(self, "combo_tone_curve_channel", None)
        key = str(combo.currentData() if combo is not None else self._tone_curve_active_channel)
        return key if key in {"luminance", "red", "green", "blue"} else "luminance"

    def _identity_tone_curve_points(self) -> list[tuple[float, float]]:
        return [(0.0, 0.0), (1.0, 1.0)]

    def _ensure_tone_curve_channel_state(self) -> None:
        channels = ("luminance", "red", "green", "blue")
        if not isinstance(getattr(self, "_tone_curve_channel_points", None), dict):
            self._tone_curve_channel_points = {}
        if not isinstance(getattr(self, "_tone_curve_channel_presets", None), dict):
            self._tone_curve_channel_presets = {}
        for channel in channels:
            points = self._coerce_tone_curve_points(self._tone_curve_channel_points.get(channel))
            self._tone_curve_channel_points[channel] = points or self._identity_tone_curve_points()
            preset = str(self._tone_curve_channel_presets.get(channel) or "linear")
            self._tone_curve_channel_presets[channel] = preset
        if getattr(self, "_tone_curve_active_channel", "luminance") not in channels:
            self._tone_curve_active_channel = "luminance"

    def _save_visible_tone_curve_channel_state(self, channel: str | None = None, *, sync_editor: bool = True) -> None:
        self._ensure_tone_curve_channel_state()
        target = channel or self._tone_curve_channel_key()
        if target not in self._tone_curve_channel_points:
            target = "luminance"
        self._tone_curve_active_channel = target
        self._tone_curve_channel_points[target] = normalize_tone_curve_points(self.tone_curve_editor.points())
        self._tone_curve_channel_presets[target] = self._tone_curve_preset_key()
        if sync_editor and channel is None:
            self._sync_tone_curve_editor_channel_overlay()

    def _load_tone_curve_channel_into_editor(self, channel: str) -> None:
        self._ensure_tone_curve_channel_state()
        key = channel if channel in self._tone_curve_channel_points else "luminance"
        self._tone_curve_active_channel = key
        preset = str(self._tone_curve_channel_presets.get(key) or "linear")
        points = self._tone_curve_channel_points.get(key) or self._tone_curve_preset_points(preset)
        self.combo_tone_curve_preset.blockSignals(True)
        self._set_combo_data(self.combo_tone_curve_preset, preset)
        self.combo_tone_curve_preset.blockSignals(False)
        if hasattr(self.tone_curve_editor, "set_active_channel"):
            self.tone_curve_editor.set_active_channel(key)
        self.tone_curve_editor.set_points(points, emit=False)
        self._sync_tone_curve_editor_channel_overlay()
        self._tone_curve_histogram_key = None
        if self._original_linear is not None and hasattr(self, "_update_tone_curve_histogram_for_current_controls"):
            self._update_tone_curve_histogram_for_current_controls(force=True)

    def _sync_tone_curve_editor_channel_overlay(self) -> None:
        editor = getattr(self, "tone_curve_editor", None)
        if editor is None:
            return
        self._ensure_tone_curve_channel_state()
        if hasattr(editor, "set_active_channel"):
            editor.set_active_channel(self._tone_curve_channel_key())
        if hasattr(editor, "set_channel_curves"):
            editor.set_channel_curves(self._tone_curve_channel_points)

    def _tone_curve_channel_points_state(self) -> dict[str, list[list[float]]]:
        self._save_visible_tone_curve_channel_state(sync_editor=False)
        return {
            channel: [[float(x), float(y)] for x, y in normalize_tone_curve_points(points)]
            for channel, points in self._tone_curve_channel_points.items()
            if channel in {"luminance", "red", "green", "blue"}
        }

    def _coerce_tone_curve_channel_points(self, value: Any) -> dict[str, list[tuple[float, float]]]:
        out: dict[str, list[tuple[float, float]]] = {}
        if not isinstance(value, dict):
            return out
        for channel in ("luminance", "red", "green", "blue"):
            points = self._coerce_tone_curve_points(value.get(channel))
            if points is not None:
                out[channel] = points
        return out

    def _set_tone_curve_controls_enabled(self, enabled: bool) -> None:
        del enabled
        editor = getattr(self, "tone_curve_editor", None)
        if editor is not None and hasattr(editor, "cancel_interaction"):
            editor.cancel_interaction()
        # The checkbox controls whether the curve is applied to the render, not
        # whether the curve can be edited. This lets users prepare/tune curves
        # while A/B testing with the effect disabled.
        self.combo_tone_curve_channel.setEnabled(True)
        self.combo_tone_curve_preset.setEnabled(True)
        self.label_tone_curve_black.setEnabled(True)
        self.slider_tone_curve_black.setEnabled(True)
        self.label_tone_curve_white.setEnabled(True)
        self.slider_tone_curve_white.setEnabled(True)
        self.tone_curve_editor.setEnabled(True)

    def _tone_curve_range_values(self) -> tuple[float, float]:
        black = self.slider_tone_curve_black.value() / 1000.0
        white = self.slider_tone_curve_white.value() / 1000.0
        black = float(np.clip(black, 0.0, 0.95))
        white = float(np.clip(white, black + 0.01, 1.0))
        return black, white

    def _set_tone_curve_range_controls(self, black_point: float, white_point: float) -> None:
        black = float(np.clip(black_point, 0.0, 0.95))
        white = float(np.clip(white_point, black + 0.01, 1.0))
        self.slider_tone_curve_black.blockSignals(True)
        self.slider_tone_curve_white.blockSignals(True)
        self.slider_tone_curve_black.setValue(int(round(black * 1000.0)))
        self.slider_tone_curve_white.setValue(int(round(white * 1000.0)))
        self.slider_tone_curve_black.blockSignals(False)
        self.slider_tone_curve_white.blockSignals(False)
        self.label_tone_curve_black.setText(self.tr("Negro curva:") + f" {self.slider_tone_curve_black.value() / 1000:.3f}")
        self.label_tone_curve_white.setText(self.tr("Blanco curva:") + f" {self.slider_tone_curve_white.value() / 1000:.3f}")
        self.tone_curve_editor.set_input_range(
            self.slider_tone_curve_black.value() / 1000.0,
            self.slider_tone_curve_white.value() / 1000.0,
        )

    def _coerce_tone_curve_points(self, value: Any) -> list[tuple[float, float]] | None:
        if not isinstance(value, (list, tuple)):
            return None
        points: list[tuple[float, float]] = []
        for item in value:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            try:
                points.append((float(item[0]), float(item[1])))
            except (TypeError, ValueError):
                continue
        if not points:
            return None
        return normalize_tone_curve_points(points)

    def _on_illuminant_changed(self) -> None:
        data = self.combo_illuminant_render.currentData()
        if isinstance(data, dict) and data.get("temperature") is not None:
            self.spin_render_temperature.blockSignals(True)
            self.spin_render_tint.blockSignals(True)
            self.spin_render_temperature.setValue(int(data["temperature"]))
            self.spin_render_tint.setValue(float(data.get("tint") or 0.0))
            self.spin_render_temperature.blockSignals(False)
            self.spin_render_tint.blockSignals(False)
            if hasattr(self, "edit_illuminant"):
                self.edit_illuminant.setText(self.combo_illuminant_render.currentText().split("(", 1)[0].strip())
        self._on_render_control_change()

    def _set_neutral_picker_active(self, active: bool) -> None:
        if active and hasattr(self, "_set_color_picker_active"):
            self._set_color_picker_active(False)
        if active and hasattr(self, "_set_mtf_roi_selection_active"):
            self._set_mtf_roi_selection_active(False)
        if active and hasattr(self, "_set_image_crop_selection_active"):
            self._set_image_crop_selection_active(False)
        if active and hasattr(self, "_deactivate_image_level_tool"):
            self._deactivate_image_level_tool()
        self._neutral_picker_active = bool(active)
        if hasattr(self, "btn_neutral_picker"):
            self.btn_neutral_picker.blockSignals(True)
            self.btn_neutral_picker.setChecked(self._neutral_picker_active)
            self.btn_neutral_picker.blockSignals(False)
        self._update_viewer_interaction_cursor()

    def _update_viewer_interaction_cursor(self) -> None:
        tool_active = bool(self._viewer_tool_cursor_active()) if hasattr(self, "_viewer_tool_cursor_active") else False
        active = bool(
            self._neutral_picker_active
            or bool(getattr(self, "_color_picker_active", False))
            or self._manual_chart_marking
            or tool_active
        )
        cursor = QtCore.Qt.CrossCursor if active else None
        for panel_name in ("image_result_single", "image_result_compare"):
            if not hasattr(self, panel_name):
                continue
            panel = getattr(self, panel_name)
            if hasattr(panel, "set_interaction_cursor"):
                panel.set_interaction_cursor(cursor)
            elif cursor is not None:
                panel.setCursor(cursor)
            else:
                panel.unsetCursor()

    def _toggle_neutral_picker(self, checked: bool = False) -> None:
        if checked and self._original_linear is None:
            self._set_neutral_picker_active(False)
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("Carga primero una imagen en el visor."))
            return
        self._set_neutral_picker_active(bool(checked))
        if self._neutral_picker_active:
            self._manual_chart_marking = False
            self._update_viewer_interaction_cursor()
            self._sync_manual_chart_overlay()
            self._set_status(self.tr("Cuentagotas neutro activo: haz clic en un gris/blanco sin saturar"))
        else:
            self._set_status(self.tr("Cuentagotas neutro desactivado"))

    def _set_color_picker_active(self, active: bool) -> None:
        if active and self._original_linear is None:
            active = False
        if active:
            if getattr(self, "_neutral_picker_active", False):
                self._set_neutral_picker_active(False)
            if hasattr(self, "_set_mtf_roi_selection_active"):
                self._set_mtf_roi_selection_active(False)
            if hasattr(self, "_set_image_crop_selection_active"):
                self._set_image_crop_selection_active(False)
            if hasattr(self, "_deactivate_image_level_tool"):
                self._deactivate_image_level_tool()
            self._manual_chart_marking = False
            if hasattr(self, "_sync_manual_chart_overlay"):
                self._sync_manual_chart_overlay()
        self._color_picker_active = bool(active)
        if hasattr(self, "btn_color_picker"):
            self.btn_color_picker.blockSignals(True)
            self.btn_color_picker.setChecked(self._color_picker_active)
            self.btn_color_picker.blockSignals(False)
        action = getattr(self, "action_color_picker_select", None)
        if action is not None:
            action.blockSignals(True)
            action.setChecked(self._color_picker_active)
            action.blockSignals(False)
        self._update_color_picker_precision_warning()
        self._sync_color_sample_overlay()
        self._update_viewer_interaction_cursor()
        if self._color_picker_active:
            self._ensure_color_picker_real_pixel_source()

    def _toggle_color_picker(self, checked: bool = False) -> None:
        if checked and self._original_linear is None:
            self._set_color_picker_active(False)
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("Carga primero una imagen en el visor."))
            return
        self._set_color_picker_active(bool(checked))
        if self._color_picker_active:
            self._focus_color_samples_tab()
            self._set_status(self.tr("Cuentagotas Lab activo: haz clic sobre la imagen"))
        else:
            self._set_status(self.tr("Cuentagotas Lab desactivado"))

    def _focus_color_samples_tab(self) -> None:
        tabs = getattr(self, "analysis_tabs", None)
        page = getattr(self, "color_samples_page", None)
        if tabs is None or page is None:
            return
        index = tabs.indexOf(page)
        if index >= 0:
            tabs.setCurrentIndex(index)

    def _on_color_picker_matrix_changed(self, *_args: object) -> None:
        self._sync_color_sample_overlay()

    def _color_picker_radius(self) -> int:
        combo = getattr(self, "color_picker_matrix_combo", None)
        if combo is None:
            return 2
        try:
            return max(0, int(combo.currentData()))
        except Exception:
            return 2

    def _color_picker_source_is_real_pixels(self) -> bool:
        base = getattr(self, "_original_linear", None)
        source = getattr(self, "_adjusted_linear", None)
        if base is None or source is None:
            return False
        try:
            if tuple(source.shape[:2]) != tuple(base.shape[:2]):
                return False
        except Exception:
            return False
        if hasattr(self, "_loaded_preview_has_real_pixels_for_viewport"):
            return bool(self._loaded_preview_has_real_pixels_for_viewport())
        return True

    def _ensure_color_picker_real_pixel_source(self) -> bool:
        if self._color_picker_source_is_real_pixels():
            return True
        selected = getattr(self, "_selected_file", None)
        if selected is None:
            self._set_status(self.tr("Cuentagotas Lab: selecciona y carga una imagen antes de medir."))
            return False
        self._viewer_full_detail_requested = True
        self._viewer_real_pixel_sync_pending = False
        self._set_status(self.tr("Cuentagotas Lab: cargando imagen a tamano real para medir pixeles exactos..."))
        if hasattr(self, "_on_load_selected"):
            self._on_load_selected(show_message=False)
        return False

    def _sample_color_patch(self, x: float, y: float, *, radius: int) -> dict[str, Any]:
        image = getattr(self, "_adjusted_linear", None)
        if image is None:
            image = getattr(self, "_original_linear", None)
        if image is None:
            raise ValueError("No hay imagen cargada para muestrear.")
        rgb_image = np.asarray(image, dtype=np.float32)
        if rgb_image.ndim != 3 or rgb_image.shape[2] < 3:
            raise ValueError("La imagen cargada no contiene datos RGB.")
        h, w = rgb_image.shape[:2]
        xi = int(round(float(np.clip(x, 0, max(0, w - 1)))))
        yi = int(round(float(np.clip(y, 0, max(0, h - 1)))))
        r = max(0, int(radius))
        crop = rgb_image[max(0, yi - r) : min(h, yi + r + 1), max(0, xi - r) : min(w, xi + r + 1), :3]
        flat = crop.reshape((-1, 3))
        valid = np.all(np.isfinite(flat), axis=1)
        flat = np.clip(flat[valid], 0.0, 1.0)
        if flat.shape[0] < 1:
            raise ValueError("La zona muestreada no contiene pixeles validos.")
        sample = np.median(flat, axis=0).astype(np.float64)
        size = 2 * r + 1
        marker_color, marker_text_color = self._color_picker_marker_color_for_patch(
            xi,
            yi,
            r,
            rgb_fallback=sample,
        )
        return {
            "x": xi,
            "y": yi,
            "rgb": sample,
            "count": int(flat.shape[0]),
            "matrix": f"{size}x{size}",
            "image_size": [int(w), int(h)],
            "marker_color": marker_color,
            "marker_text_color": marker_text_color,
        }

    def _color_picker_marker_color_for_patch(
        self,
        x: int,
        y: int,
        radius: int,
        *,
        rgb_fallback: np.ndarray,
    ) -> tuple[str, str]:
        r = max(0, int(radius))
        display = getattr(self, "_current_result_display_u8", None)
        if display is not None:
            try:
                arr = np.asarray(display, dtype=np.uint8)
                if arr.ndim == 3 and arr.shape[2] >= 3:
                    h, w = arr.shape[:2]
                    if 0 <= y < h and 0 <= x < w:
                        crop = arr[max(0, y - r) : min(h, y + r + 1), max(0, x - r) : min(w, x + r + 1), :3]
                        if crop.size:
                            values = np.median(crop.reshape((-1, 3)), axis=0)
                            return self._color_picker_marker_color_strings(values)
            except Exception:
                pass
        rgb = np.asarray(rgb_fallback, dtype=np.float64).reshape(-1)[:3]
        rgb = np.power(np.clip(rgb, 0.0, 1.0), 1.0 / 2.2) * 255.0 if rgb.size >= 3 else np.zeros(3)
        return self._color_picker_marker_color_strings(rgb)

    def _color_picker_marker_color_strings(self, values: Any) -> tuple[str, str]:
        rgb = np.asarray(values, dtype=np.float64).reshape(-1)[:3]
        if rgb.size < 3 or not np.all(np.isfinite(rgb)):
            rgb = np.asarray([34.0, 211.0, 238.0], dtype=np.float64)
        rgb = np.clip(np.round(rgb), 0, 255).astype(int)
        fill = f"#{int(rgb[0]):02x}{int(rgb[1]):02x}{int(rgb[2]):02x}"
        luminance = (0.2126 * float(rgb[0]) + 0.7152 * float(rgb[1]) + 0.0722 * float(rgb[2])) / 255.0
        text = "#0f172a" if luminance >= 0.62 else "#ffffff"
        return fill, text

    def _color_picker_source_profile(self) -> Path:
        profile = getattr(self, "_loaded_preview_source_profile_path", None)
        if profile is not None:
            path = Path(profile).expanduser()
            if path.exists():
                return path
        recipe = self._color_managed_preview_recipe(self._build_effective_recipe())
        return self._source_profile_for_preview_recipe(recipe)

    def _color_picker_profile_generated_by_app(self, profile_path: Path | None) -> bool:
        if profile_path is None:
            return False
        path = Path(profile_path).expanduser()
        profile = self._icc_profile_by_path(path) if hasattr(self, "_icc_profile_by_path") else None
        if isinstance(profile, dict) and str(profile.get("source") or "").strip().lower() == "generated":
            return True
        generated = self._candidate_generated_gamut_profile() if hasattr(self, "_candidate_generated_gamut_profile") else None
        if generated is not None and hasattr(self, "_paths_equivalent"):
            try:
                return bool(self._paths_equivalent(Path(generated).expanduser(), path))
            except Exception:
                return False
        return False

    def _color_picker_precision_warning(self, source_profile: Path | None = None) -> tuple[bool, str]:
        profile = source_profile
        if profile is None:
            loaded = getattr(self, "_loaded_preview_source_profile_path", None)
            if loaded is not None:
                try:
                    candidate = Path(loaded).expanduser()
                    profile = candidate if candidate.exists() else None
                except Exception:
                    profile = None
            if profile is None and hasattr(self, "path_profile_active"):
                raw_path = self.path_profile_active.text().strip()
                if raw_path:
                    try:
                        candidate = Path(raw_path).expanduser()
                        profile = candidate if candidate.exists() else None
                    except Exception:
                        profile = None
        if self._color_picker_profile_generated_by_app(profile):
            name = Path(profile).name if profile is not None else self.tr("perfil generado")
            return True, self.tr("Medicion colorimetrica: ICC generado por ProbRAW") + f" ({name})."
        return (
            False,
            self.tr(
                "Aviso de precision: Lab, Delta E y gamut solo son fiables si esta imagen "
                "usa un ICC generado por ProbRAW; con perfiles genericos o cargados manualmente "
                "los valores son orientativos."
            ),
        )

    def _update_color_picker_precision_warning(self, source_profile: Path | None = None) -> bool:
        precise, text = self._color_picker_precision_warning(source_profile)
        label = getattr(self, "label_color_picker_precision", None)
        if label is not None:
            label.setText(text)
            label.setStyleSheet(
                "font-size: 12px; color: #86efac;" if precise else "font-size: 12px; color: #fbbf24;"
            )
        return precise

    def _color_picker_gamut_specs_from_snapshot(
        self,
        snapshot: dict[str, Any],
        *,
        source_profile: Path,
    ) -> tuple[dict[str, str] | None, dict[str, str] | None, Path | None]:
        task_monitor_profile = snapshot["monitor_profile"]
        if task_monitor_profile is None and (
            snapshot["selection_a"] == "monitor" or snapshot["selection_b"] == "monitor"
        ):
            try:
                task_monitor_profile = detect_system_display_profile()
            except Exception:
                task_monitor_profile = None
        spec_a = self._gamut_profile_spec_from_selection(
            snapshot["selection_a"],
            snapshot["custom_a"],
            generated_profile=snapshot["generated_profile"],
            monitor_profile=task_monitor_profile,
            label_suffix="A",
        )
        spec_b = self._gamut_profile_spec_from_selection(
            snapshot["selection_b"],
            snapshot["custom_b"],
            generated_profile=snapshot["generated_profile"],
            monitor_profile=task_monitor_profile,
            label_suffix="B",
        )
        if spec_a is None and source_profile.exists():
            spec_a = {
                "kind": "icc",
                "label": "ICC imagen",
                "path": str(source_profile),
                "color": "#e5e7eb",
            }
        return spec_a, spec_b, task_monitor_profile

    def _handle_color_picker_click(self, x: float, y: float) -> bool:
        if not bool(getattr(self, "_color_picker_active", False)):
            return False
        self._apply_color_picker_at(x, y)
        return True

    def _apply_color_picker_at(self, x: float, y: float) -> None:
        if not self._ensure_color_picker_real_pixel_source():
            return
        try:
            sample = self._sample_color_patch(x, y, radius=self._color_picker_radius())
            source_profile = self._color_picker_source_profile()
        except Exception as exc:
            QtWidgets.QMessageBox.information(self, self.tr("Cuentagotas Lab"), str(exc))
            self._set_status(str(exc))
            return

        profile_generated_by_app, precision_note = self._color_picker_precision_warning(source_profile)
        self._update_color_picker_precision_warning(source_profile)
        if hasattr(self, "label_color_picker"):
            self.label_color_picker.setText(self.tr("Color Lab: calculando..."))
        generated_profile = self._candidate_generated_gamut_profile() if hasattr(self, "_candidate_generated_gamut_profile") else None
        snapshot = self._gamut_selection_snapshot(generated_profile=generated_profile)
        rgb = np.asarray(sample["rgb"], dtype=np.float64).reshape((1, 3))

        def task():
            lab = lookup_lab_with_icc(source_profile, rgb)
            spec_a, spec_b, task_monitor_profile = self._color_picker_gamut_specs_from_snapshot(
                snapshot,
                source_profile=source_profile,
            )
            membership = evaluate_lab_gamut_membership(lab, profile_a=spec_a, profile_b=spec_b)
            return {
                **sample,
                "source_profile": str(source_profile),
                "monitor_profile": str(task_monitor_profile) if task_monitor_profile else "",
                "profile_generated_by_app": bool(profile_generated_by_app),
                "profile_precision_note": precision_note,
                "lab": np.asarray(lab, dtype=np.float64).reshape((-1, 3))[0],
                "membership": membership,
            }

        def on_success(payload: dict[str, Any]) -> None:
            index = self._record_color_picker_sample(payload)
            text = self._color_picker_result_text(payload)
            if index is not None:
                text = f"Muestra {index + 1}: {text}"
            if hasattr(self, "label_color_picker"):
                self.label_color_picker.setText(text)
            self._set_status(text)

        self._start_background_task(self.tr("Cuentagotas Lab"), task, on_success)

    def _color_picker_result_text(self, payload: dict[str, Any]) -> str:
        rgb = np.asarray(payload.get("rgb"), dtype=np.float64).reshape(-1)
        lab = np.asarray(payload.get("lab"), dtype=np.float64).reshape(-1)
        membership = payload.get("membership") if isinstance(payload.get("membership"), dict) else {}

        def inside_text(key: str) -> str:
            values = np.asarray(membership.get(key), dtype=bool).reshape(-1)
            return self.tr("dentro") if values.size and bool(values[0]) else self.tr("fuera")

        common_values = np.asarray(membership.get("inside_common"), dtype=bool).reshape(-1)
        common = self.tr("si") if common_values.size and bool(common_values[0]) else "no"
        label_a = str(membership.get("label_a") or "A")
        label_b = str(membership.get("label_b") or "B")
        chroma = float(np.linalg.norm(lab[1:3])) if lab.size >= 3 else 0.0
        deltas = self._color_picker_delta_summary(lab)
        delta_text = f" | {deltas}" if deltas else ""
        return (
            f"Color Lab x={int(payload.get('x', 0))}, y={int(payload.get('y', 0))} "
            f"{payload.get('matrix', '1x1')} ({int(payload.get('count', 0))} px) | "
            f"RGB {float(rgb[0]):.4f}, {float(rgb[1]):.4f}, {float(rgb[2]):.4f} | "
            f"Lab {float(lab[0]):.2f}, {float(lab[1]):+.2f}, {float(lab[2]):+.2f}; C* {chroma:.2f}{delta_text} | "
            f"{label_a}: {inside_text('inside_a')}; {label_b}: {inside_text('inside_b')}; "
            f"gama comun: {common}"
        )

    def _color_picker_delta_summary(self, lab: np.ndarray) -> str:
        reference_lab = self._color_sample_reference_lab()
        if reference_lab is None:
            return ""
        de76 = self._color_sample_delta_e_text(lab, reference_lab, method="76")
        de00 = self._color_sample_delta_e_text(lab, reference_lab, method="00")
        dc = self._color_sample_delta_c_text(lab, reference_lab)
        return f"DE76 ref {de76}; DE00 ref {de00}; DC* ref {dc}"

    def _record_color_picker_sample(self, payload: dict[str, Any]) -> int | None:
        membership = payload.get("membership") if isinstance(payload.get("membership"), dict) else {}
        sample = {
            "x": int(payload.get("x", 0)),
            "y": int(payload.get("y", 0)),
            "matrix": str(payload.get("matrix") or "1x1"),
            "count": int(payload.get("count", 0)),
            "rgb": np.asarray(payload.get("rgb"), dtype=np.float64).reshape(-1)[:3].tolist(),
            "lab": np.asarray(payload.get("lab"), dtype=np.float64).reshape(-1)[:3].tolist(),
            "chroma": self._lab_chroma(payload.get("lab")),
            "inside_a": bool(np.asarray(membership.get("inside_a"), dtype=bool).reshape(-1)[0])
            if np.asarray(membership.get("inside_a"), dtype=bool).size
            else False,
            "inside_b": bool(np.asarray(membership.get("inside_b"), dtype=bool).reshape(-1)[0])
            if np.asarray(membership.get("inside_b"), dtype=bool).size
            else False,
            "inside_common": bool(np.asarray(membership.get("inside_common"), dtype=bool).reshape(-1)[0])
            if np.asarray(membership.get("inside_common"), dtype=bool).size
            else False,
            "label_a": str(membership.get("label_a") or "A"),
            "label_b": str(membership.get("label_b") or "B"),
            "source_profile": str(payload.get("source_profile") or ""),
            "monitor_profile": str(payload.get("monitor_profile") or ""),
            "profile_generated_by_app": bool(payload.get("profile_generated_by_app")),
            "profile_precision_note": str(payload.get("profile_precision_note") or ""),
            "marker_color": str(payload.get("marker_color") or "#22d3ee"),
            "marker_text_color": str(payload.get("marker_text_color") or "#ffffff"),
            "image_size": list(payload.get("image_size") or []),
            "source_path": str(getattr(self, "_selected_file", "") or ""),
            "group": self._active_color_sample_group(),
            "name": f"Muestra {len(getattr(self, '_color_picker_samples', []) or []) + 1}",
            "note": "",
        }
        samples = getattr(self, "_color_picker_samples", None)
        if not isinstance(samples, list):
            samples = []
            self._color_picker_samples = samples
        samples.append(sample)
        self._ensure_color_sample_group(sample.get("group"))
        self._refresh_color_samples_table()
        self._persist_color_picker_samples_for_selected()
        self._push_color_picker_history_snapshot("color_sample_add")
        return len(samples) - 1

    def _clear_color_picker_samples(self) -> None:
        if not getattr(self, "_color_picker_samples", []):
            self._set_status(self.tr("No hay tomas de color que limpiar"))
            return
        self._color_picker_samples = []
        default_group = self._default_color_sample_group()
        self._color_picker_groups = [default_group]
        self._color_picker_active_group = default_group
        self._color_picker_group_reference = default_group
        if hasattr(self, "color_samples_table"):
            self.color_samples_table.setRowCount(0)
        if hasattr(self, "label_color_picker"):
            self.label_color_picker.setText(self.tr("Color Lab: sin muestra"))
        self._update_color_picker_precision_warning()
        self._sync_color_sample_overlay()
        self._refresh_color_sample_cards()
        self._refresh_color_sample_group_controls()
        self._refresh_color_sample_group_summary()
        self._refresh_color_sample_group_gamut()
        self._persist_color_picker_samples_for_selected()
        self._push_color_picker_history_snapshot("color_sample_clear")
        self._set_status(self.tr("Tomas de color limpiadas"))

    def _clear_color_picker_samples_for_file_change(self) -> None:
        self._color_picker_samples = []
        self._color_picker_samples_source_key = ""
        default_group = self._default_color_sample_group()
        self._color_picker_groups = [default_group]
        self._color_picker_active_group = default_group
        self._color_picker_group_reference = default_group
        if hasattr(self, "color_samples_table"):
            self.color_samples_table.setRowCount(0)
        if hasattr(self, "label_color_picker"):
            self.label_color_picker.setText(self.tr("Color Lab: sin muestra"))
        self._update_color_picker_precision_warning()
        self._sync_color_sample_overlay()
        self._refresh_color_sample_cards()
        self._refresh_color_sample_group_controls()
        self._refresh_color_sample_group_summary()
        self._refresh_color_sample_group_gamut()

    def _selected_color_sample_row(self) -> int | None:
        table = getattr(self, "color_samples_table", None)
        if table is None:
            return None
        rows = table.selectionModel().selectedRows() if table.selectionModel() is not None else []
        if not rows:
            return None
        row = int(rows[0].row())
        samples = getattr(self, "_color_picker_samples", [])
        if 0 <= row < len(samples):
            return row
        return None

    def _delete_selected_color_picker_sample(self) -> None:
        row = self._selected_color_sample_row()
        if row is None:
            self._set_status(self.tr("Selecciona una toma de color para eliminarla"))
            return
        samples = getattr(self, "_color_picker_samples", [])
        if not isinstance(samples, list) or not (0 <= row < len(samples)):
            return
        del samples[row]
        self._refresh_color_samples_table()
        self._persist_color_picker_samples_for_selected()
        self._push_color_picker_history_snapshot("color_sample_delete")
        self._set_status(self.tr("Toma de color eliminada") + f": {row + 1}")

    def _on_color_sample_table_item_changed(self, item: QtWidgets.QTableWidgetItem | None) -> None:
        if item is None or item.column() not in (1, 2, 3):
            return
        row = int(item.row())
        samples = getattr(self, "_color_picker_samples", [])
        if not isinstance(samples, list) or not (0 <= row < len(samples)):
            return
        if item.column() == 1:
            group = self._color_sample_group_name(item.text())
            samples[row]["group"] = group
            self._ensure_color_sample_group(group)
        elif item.column() == 2:
            samples[row]["name"] = item.text()
        else:
            samples[row]["note"] = item.text()
        self._refresh_color_sample_cards()
        self._refresh_color_sample_group_controls()
        self._refresh_color_sample_group_summary()
        self._refresh_color_sample_group_gamut()
        self._persist_color_picker_samples_for_selected()
        self._push_color_picker_history_snapshot("color_sample_edit")

    def _push_color_picker_history_snapshot(self, label: str) -> None:
        if hasattr(self, "_push_edit_history_snapshot"):
            self._push_edit_history_snapshot(label)

    def _on_color_samples_view_changed(self, *_args: object) -> None:
        stack = getattr(self, "color_samples_stack", None)
        combo = getattr(self, "color_samples_view_combo", None)
        if stack is None or combo is None:
            return
        view = str(combo.currentData() or "table")
        stack.setCurrentIndex(1 if view == "cards" else 0)

    def _default_color_sample_group(self) -> str:
        return self.tr("Conjunto 1")

    def _color_sample_group_name(self, value: Any) -> str:
        text = str(value or "").strip()
        return text or self._default_color_sample_group()

    def _color_sample_groups(self) -> list[str]:
        groups: list[str] = []
        for group in getattr(self, "_color_picker_groups", []) or []:
            name = self._color_sample_group_name(group)
            if name not in groups:
                groups.append(name)
        for sample in getattr(self, "_color_picker_samples", []) or []:
            if isinstance(sample, dict):
                name = self._color_sample_group_name(sample.get("group"))
                if name not in groups:
                    groups.append(name)
        if not groups:
            groups.append(self._default_color_sample_group())
        self._color_picker_groups = groups
        return groups

    def _ensure_color_sample_group(self, group: Any) -> str:
        name = self._color_sample_group_name(group)
        groups = self._color_sample_groups()
        if name not in groups:
            groups.append(name)
            self._color_picker_groups = groups
        return name

    def _active_color_sample_group(self) -> str:
        groups = self._color_sample_groups()
        active = self._color_sample_group_name(getattr(self, "_color_picker_active_group", ""))
        if active not in groups:
            active = groups[0]
        self._color_picker_active_group = active
        return active

    def _color_sample_reference_group(self) -> str:
        groups = self._color_sample_groups()
        reference = self._color_sample_group_name(getattr(self, "_color_picker_group_reference", ""))
        if reference not in groups:
            reference = groups[0]
        self._color_picker_group_reference = reference
        return reference

    def _refresh_color_sample_group_controls(self) -> None:
        groups = self._color_sample_groups()
        active = self._active_color_sample_group()
        reference = self._color_sample_reference_group()
        for attr, value in (
            ("color_sample_group_combo", active),
            ("color_sample_group_reference_combo", reference),
        ):
            combo = getattr(self, attr, None)
            if combo is None:
                continue
            combo.blockSignals(True)
            combo.clear()
            for group in groups:
                combo.addItem(group, group)
            index = combo.findData(value)
            combo.setCurrentIndex(index if index >= 0 else 0)
            combo.blockSignals(False)

    def _on_color_sample_group_changed(self, *_args: object) -> None:
        combo = getattr(self, "color_sample_group_combo", None)
        if combo is None:
            return
        self._color_picker_active_group = self._ensure_color_sample_group(combo.currentData() or combo.currentText())
        self._refresh_color_sample_group_controls()
        self._persist_color_picker_samples_for_selected()

    def _on_color_sample_group_reference_changed(self, *_args: object) -> None:
        combo = getattr(self, "color_sample_group_reference_combo", None)
        if combo is None:
            return
        self._color_picker_group_reference = self._ensure_color_sample_group(combo.currentData() or combo.currentText())
        self._refresh_color_sample_group_summary()
        self._refresh_color_sample_group_gamut()
        self._persist_color_picker_samples_for_selected()
        self._push_color_picker_history_snapshot("color_sample_group_reference")

    def _create_color_sample_group(self, _checked: bool = False, name: str | None = None) -> None:
        group_name = str(name or "").strip()
        if not group_name:
            group_name, accepted = QtWidgets.QInputDialog.getText(
                self,
                self.tr("Nuevo conjunto"),
                self.tr("Nombre del conjunto"),
                text=self.tr("Conjunto") + f" {len(self._color_sample_groups()) + 1}",
            )
            if not accepted:
                return
        group = self._ensure_color_sample_group(group_name)
        self._color_picker_active_group = group
        if not getattr(self, "_color_picker_group_reference", ""):
            self._color_picker_group_reference = group
        self._refresh_color_sample_group_controls()
        self._refresh_color_sample_group_summary()
        self._refresh_color_sample_group_gamut()
        self._persist_color_picker_samples_for_selected()
        self._push_color_picker_history_snapshot("color_sample_group_add")
        self._set_status(self.tr("Conjunto activo:") + f" {group}")

    def _on_color_samples_table_section_resized(
        self,
        _section: int,
        _old_size: int,
        _new_size: int,
    ) -> None:
        if bool(getattr(self, "_color_samples_table_auto_sizing", False)):
            return
        self._color_samples_table_user_resized = True

    def _auto_size_color_samples_table_columns(self, *, force: bool = False) -> None:
        table = getattr(self, "color_samples_table", None)
        if table is None:
            return
        if bool(getattr(self, "_color_samples_table_user_resized", False)) and not force:
            return
        minimums = (46, 96, 92, 120, 66, 58, 122, 132, 54, 66, 66, 68, 66, 66, 66)
        maximums = (76, 180, 190, 260, 96, 82, 178, 190, 72, 96, 96, 92, 92, 92, 92)
        self._color_samples_table_auto_sizing = True
        try:
            table.resizeColumnsToContents()
            for column in range(table.columnCount()):
                current = int(table.columnWidth(column))
                minimum = minimums[column] if column < len(minimums) else 56
                maximum = maximums[column] if column < len(maximums) else 180
                table.setColumnWidth(column, int(np.clip(current + 10, minimum, maximum)))
        finally:
            self._color_samples_table_auto_sizing = False

    def _refresh_color_samples_table(self) -> None:
        table = getattr(self, "color_samples_table", None)
        if table is None:
            self._sync_color_sample_overlay()
            return
        samples = list(getattr(self, "_color_picker_samples", []) or [])
        reference_lab = self._color_sample_reference_lab()
        table.blockSignals(True)
        table.setRowCount(len(samples))
        for row, sample in enumerate(samples):
            values = [
                f"{row + 1}",
                self._color_sample_group_name(sample.get("group")),
                str(sample.get("name") or f"Muestra {row + 1}"),
                str(sample.get("note") or ""),
                f"{int(sample.get('x', 0))},{int(sample.get('y', 0))}",
                str(sample.get("matrix") or "1x1"),
                self._color_sample_rgb_text(sample),
                self._color_sample_lab_text(sample),
                f"{float(sample.get('chroma') or 0.0):.2f}",
                self.tr("dentro") if bool(sample.get("inside_a")) else self.tr("fuera"),
                self.tr("dentro") if bool(sample.get("inside_b")) else self.tr("fuera"),
                self.tr("si") if bool(sample.get("inside_common")) else "no",
                self._color_sample_delta_e_text(sample.get("lab"), reference_lab, method="76"),
                self._color_sample_delta_e_text(sample.get("lab"), reference_lab, method="00"),
                self._color_sample_delta_c_text(sample.get("lab"), reference_lab),
            ]
            for column, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setTextAlignment(
                    QtCore.Qt.AlignCenter
                    if column not in (1, 2, 3, 6, 7)
                    else QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
                )
                flags = QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
                if column in (1, 2, 3):
                    flags |= QtCore.Qt.ItemIsEditable
                item.setFlags(flags)
                table.setItem(row, column, item)
        table.blockSignals(False)
        if samples:
            table.resizeRowsToContents()
        self._auto_size_color_samples_table_columns()
        self._refresh_color_sample_cards()
        self._refresh_color_sample_group_controls()
        self._refresh_color_sample_group_summary()
        self._refresh_color_sample_group_gamut()
        self._sync_color_sample_overlay()

    def _select_color_sample_row(self, row: int) -> None:
        table = getattr(self, "color_samples_table", None)
        if table is None:
            return
        if 0 <= int(row) < table.rowCount():
            table.selectRow(int(row))

    def _clear_color_sample_cards(self) -> None:
        layout = getattr(self, "color_sample_cards_layout", None)
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _refresh_color_sample_cards(self) -> None:
        layout = getattr(self, "color_sample_cards_layout", None)
        if layout is None:
            return
        self._clear_color_sample_cards()
        samples = list(getattr(self, "_color_picker_samples", []) or [])
        reference_lab = self._color_sample_reference_lab()
        if not samples:
            label = QtWidgets.QLabel(self.tr("Sin muestras"))
            label.setStyleSheet("color: #9ca3af; padding: 8px;")
            layout.addWidget(label)
            layout.addStretch(1)
            return
        for row, sample in enumerate(samples):
            layout.addWidget(self._color_sample_card_widget(row, sample, reference_lab))
        layout.addStretch(1)

    def _color_sample_card_widget(
        self,
        row: int,
        sample: dict[str, Any],
        reference_lab: Any,
    ) -> QtWidgets.QWidget:
        frame = QtWidgets.QFrame()
        frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
        frame.setStyleSheet(
            "QFrame { background: #1f242c; border: 1px solid #3b4250; border-radius: 6px; }"
            "QLabel { border: none; background: transparent; }"
        )
        card = QtWidgets.QGridLayout(frame)
        card.setContentsMargins(8, 8, 8, 8)
        card.setHorizontalSpacing(8)
        card.setVerticalSpacing(4)

        swatch = QtWidgets.QLabel(str(row + 1))
        swatch.setAlignment(QtCore.Qt.AlignCenter)
        swatch.setFixedSize(30, 30)
        fill = str(sample.get("marker_color") or "#22d3ee")
        text = str(sample.get("marker_text_color") or "#ffffff")
        swatch.setStyleSheet(
            f"background: {fill}; color: {text}; border: 1px solid #e5e7eb; border-radius: 4px; font-weight: 700;"
        )
        card.addWidget(swatch, 0, 0, 2, 1)

        title = QtWidgets.QLabel(f"{row + 1} - " + str(sample.get("name") or f"Muestra {row + 1}"))
        title.setStyleSheet("color: #f9fafb; font-weight: 700;")
        card.addWidget(title, 0, 1, 1, 2)

        group = self._color_sample_group_name(sample.get("group"))
        meta = QtWidgets.QLabel(
            f"{group} | x={int(sample.get('x', 0))}, y={int(sample.get('y', 0))} | "
            f"{sample.get('matrix', '1x1')} ({int(sample.get('count', 0))} px)"
        )
        meta.setStyleSheet("color: #cbd5e1;")
        card.addWidget(meta, 1, 1, 1, 2)

        rgb_lab = QtWidgets.QLabel(
            f"RGB {self._color_sample_rgb_text(sample)}\n"
            f"Lab {self._color_sample_lab_text(sample)} | C* {float(sample.get('chroma') or 0.0):.2f}"
        )
        rgb_lab.setStyleSheet("color: #d1d5db;")
        card.addWidget(rgb_lab, 2, 0, 1, 3)

        delta = (
            f"DE76 ref {self._color_sample_delta_e_text(sample.get('lab'), reference_lab, method='76')} | "
            f"DE00 ref {self._color_sample_delta_e_text(sample.get('lab'), reference_lab, method='00')} | "
            f"DC* ref {self._color_sample_delta_c_text(sample.get('lab'), reference_lab)}"
        )
        gamut = (
            f"{sample.get('label_a') or 'A'}: "
            + (self.tr("dentro") if bool(sample.get("inside_a")) else self.tr("fuera"))
            + " | "
            + f"{sample.get('label_b') or 'B'}: "
            + (self.tr("dentro") if bool(sample.get("inside_b")) else self.tr("fuera"))
            + " | "
            + self.tr("comun")
            + ": "
            + (self.tr("si") if bool(sample.get("inside_common")) else "no")
        )
        detail = QtWidgets.QLabel(delta + "\n" + gamut)
        detail.setStyleSheet("color: #d1d5db;")
        card.addWidget(detail, 3, 0, 1, 3)

        note_text = str(sample.get("note") or "").strip()
        if note_text:
            note = QtWidgets.QLabel(note_text)
            note.setWordWrap(True)
            note.setStyleSheet("color: #9ca3af;")
            card.addWidget(note, 4, 0, 1, 3)

        select_button = QtWidgets.QPushButton(self.tr("Seleccionar"))
        select_button.clicked.connect(lambda _checked=False, sample_row=row: self._select_color_sample_row(sample_row))
        card.addWidget(select_button, 5, 2)
        card.setColumnStretch(1, 1)
        return frame

    def _color_sample_group_stats(self) -> dict[str, dict[str, Any]]:
        stats: dict[str, dict[str, Any]] = {}
        groups = self._color_sample_groups()
        samples = [sample for sample in getattr(self, "_color_picker_samples", []) or [] if isinstance(sample, dict)]
        for group in groups:
            group_samples = [
                sample
                for sample in samples
                if self._color_sample_group_name(sample.get("group")) == group
            ]
            labs = []
            rgbs = []
            for sample in group_samples:
                try:
                    lab = np.asarray(sample.get("lab"), dtype=np.float64).reshape(-1)[:3]
                    rgb = np.asarray(sample.get("rgb"), dtype=np.float64).reshape(-1)[:3]
                except Exception:
                    continue
                if lab.size == 3 and rgb.size == 3 and np.all(np.isfinite(lab)) and np.all(np.isfinite(rgb)):
                    labs.append(lab)
                    rgbs.append(rgb)
            if labs:
                lab_values = np.vstack(labs)
                lab_mean = np.mean(lab_values, axis=0)
                rgb_mean = np.mean(np.vstack(rgbs), axis=0)
                if lab_values.shape[0] > 1:
                    try:
                        centroid = np.repeat(lab_mean.reshape((1, 3)), lab_values.shape[0], axis=0)
                        distances = np.asarray(delta_e2000(lab_values, centroid), dtype=np.float64).reshape(-1)
                        distances = distances[np.isfinite(distances)]
                    except Exception:
                        distances = np.zeros(0, dtype=np.float64)
                else:
                    distances = np.zeros(0, dtype=np.float64)
            else:
                lab_mean = np.zeros(3, dtype=np.float64)
                rgb_mean = np.zeros(3, dtype=np.float64)
                distances = np.zeros(0, dtype=np.float64)
            stats[group] = {
                "count": len(labs),
                "lab": lab_mean,
                "rgb": rgb_mean,
                "chroma": self._lab_chroma(lab_mean) if labs else 0.0,
                "dispersion_de00_mean": float(np.mean(distances)) if distances.size else 0.0,
                "dispersion_de00_max": float(np.max(distances)) if distances.size else 0.0,
            }
        return stats

    def _color_sample_reference_lab(self) -> np.ndarray | None:
        stats = self._color_sample_group_stats()
        reference_group = self._color_sample_reference_group()
        reference = stats.get(reference_group, {})
        if int(reference.get("count") or 0) < 1:
            return None
        try:
            lab = np.asarray(reference.get("lab"), dtype=np.float64).reshape(-1)[:3]
        except Exception:
            return None
        if lab.size != 3 or not np.all(np.isfinite(lab)):
            return None
        return lab

    def _color_sample_group_color(self, group: str, index: int) -> str:
        palette = (
            "#38bdf8",
            "#f97316",
            "#22c55e",
            "#e879f9",
            "#facc15",
            "#fb7185",
            "#a78bfa",
            "#2dd4bf",
        )
        return palette[int(index) % len(palette)]

    def _color_sample_group_lab_points(self, group: str) -> np.ndarray:
        labs: list[np.ndarray] = []
        for sample in getattr(self, "_color_picker_samples", []) or []:
            if not isinstance(sample, dict) or self._color_sample_group_name(sample.get("group")) != group:
                continue
            try:
                lab = np.asarray(sample.get("lab"), dtype=np.float64).reshape(-1)[:3]
            except Exception:
                continue
            if lab.size == 3 and np.all(np.isfinite(lab)):
                labs.append(lab)
        return np.vstack(labs) if labs else np.zeros((0, 3), dtype=np.float64)

    def _refresh_color_sample_group_gamut(self) -> None:
        widget = getattr(self, "color_sample_gamut_widget", None)
        if widget is None or not hasattr(widget, "set_groups"):
            return
        payload = []
        for index, group in enumerate(self._color_sample_groups()):
            payload.append(
                {
                    "name": group,
                    "color": self._color_sample_group_color(group, index),
                    "points_lab": self._color_sample_group_lab_points(group),
                }
            )
        widget.set_groups(payload)

    def _color_sample_group_comparison_metrics(
        self,
        lab: Any,
        reference_lab: Any,
        *,
        tolerance: float = 3.0,
    ) -> dict[str, str]:
        try:
            current = np.asarray(lab, dtype=np.float64)
            reference = np.asarray(reference_lab, dtype=np.float64)
            if current.ndim != 2 or reference.ndim != 2 or current.shape[1] < 3 or reference.shape[1] < 3:
                raise ValueError
            current = current[:, :3]
            reference = reference[:, :3]
            if current.shape[0] < 1 or reference.shape[0] < 1:
                raise ValueError
            left = np.repeat(current, reference.shape[0], axis=0)
            right = np.tile(reference, (current.shape[0], 1))
            matrix = np.asarray(delta_e2000(left, right), dtype=np.float64).reshape(current.shape[0], reference.shape[0])
            matrix = np.where(np.isfinite(matrix), matrix, np.nan)
            nearest_current = np.nanmin(matrix, axis=1)
            nearest_reference = np.nanmin(matrix, axis=0)
            nearest = np.concatenate([nearest_current, nearest_reference])
            nearest = nearest[np.isfinite(nearest)]
            finite_matrix = matrix[np.isfinite(matrix)]
            if nearest.size < 1 or finite_matrix.size < 1:
                raise ValueError
            similarity = float(np.count_nonzero(nearest <= float(tolerance)) / nearest.size * 100.0)
            return {
                "similarity": f"{similarity:.1f}",
                "min": f"{float(np.min(finite_matrix)):.2f}",
                "mean": f"{float(np.mean(nearest)):.2f}",
                "max": f"{float(np.max(nearest)):.2f}",
            }
        except Exception:
            return {"similarity": "--", "min": "--", "mean": "--", "max": "--"}

    def _refresh_color_sample_group_summary(self) -> None:
        table = getattr(self, "color_sample_group_table", None)
        if table is None:
            return
        stats = self._color_sample_group_stats()
        groups = self._color_sample_groups()
        reference_group = self._color_sample_reference_group()
        reference = stats.get(reference_group, {})
        reference_lab = reference.get("lab") if int(reference.get("count") or 0) > 0 else None
        table.blockSignals(True)
        table.setRowCount(len(groups))
        for row, group in enumerate(groups):
            stat = stats.get(group, {})
            count = int(stat.get("count") or 0)
            lab = stat.get("lab")
            rgb = stat.get("rgb")
            group_points = self._color_sample_group_lab_points(group)
            reference_points = self._color_sample_group_lab_points(reference_group)
            is_reference = group == reference_group
            if count:
                rgb_text = self._format_color_triplet(rgb, precision=4, sign=False)
                lab_text = self._format_color_triplet(lab, precision=2, sign=True)
                chroma_text = f"{float(stat.get('chroma') or 0.0):.2f}"
                dispersion_mean = f"{float(stat.get('dispersion_de00_mean') or 0.0):.2f}"
                dispersion_max = f"{float(stat.get('dispersion_de00_max') or 0.0):.2f}"
                de76 = "ref" if is_reference else self._color_sample_delta_e_text(lab, reference_lab, method="76")
                de00 = "ref" if is_reference else self._color_sample_delta_e_text(lab, reference_lab, method="00")
                dc = "ref" if is_reference else self._color_sample_delta_c_text(lab, reference_lab)
                comparison = (
                    {"similarity": "100.0", "min": "0.00", "mean": "0.00", "max": "0.00"}
                    if is_reference
                    else self._color_sample_group_comparison_metrics(group_points, reference_points)
                )
            else:
                rgb_text = lab_text = chroma_text = dispersion_mean = dispersion_max = de76 = de00 = dc = "--"
                comparison = {"similarity": "--", "min": "--", "mean": "--", "max": "--"}
            values = [
                group,
                str(count),
                rgb_text,
                lab_text,
                chroma_text,
                dispersion_mean,
                dispersion_max,
                "ref" if is_reference else reference_group,
                comparison["similarity"],
                de76,
                de00,
                comparison["min"],
                comparison["mean"],
                comparison["max"],
                dc,
            ]
            for column, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setTextAlignment(
                    QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
                    if column in (0, 2, 3)
                    else QtCore.Qt.AlignCenter
                )
                if is_reference:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    item.setBackground(QtGui.QColor("#243042"))
                table.setItem(row, column, item)
        table.blockSignals(False)
        table.resizeColumnsToContents()
        table.resizeRowsToContents()

    def _format_color_triplet(self, values: Any, *, precision: int, sign: bool) -> str:
        try:
            arr = np.asarray(values, dtype=np.float64).reshape(-1)
            if arr.size < 3 or not np.all(np.isfinite(arr[:3])):
                return "--"
            if sign:
                return f"{float(arr[0]):.{precision}f}, {float(arr[1]):+.{precision}f}, {float(arr[2]):+.{precision}f}"
            return f"{float(arr[0]):.{precision}f}, {float(arr[1]):.{precision}f}, {float(arr[2]):.{precision}f}"
        except Exception:
            return "--"

    def _sync_color_sample_overlay(self) -> None:
        samples = list(getattr(self, "_color_picker_samples", []) or [])
        markers = [
            {
                "x": int(sample.get("x", 0)),
                "y": int(sample.get("y", 0)),
                "index": index,
                "label": str(index),
                "color": str(sample.get("marker_color") or "#22d3ee"),
                "text_color": str(sample.get("marker_text_color") or "#ffffff"),
            }
            for index, sample in enumerate(samples, start=1)
        ]
        magnifier_active = bool(getattr(self, "_color_picker_active", False))
        radius = self._color_picker_radius()
        for panel_name in ("image_result_single", "image_result_compare", "image_original_compare"):
            panel = getattr(self, panel_name, None)
            if panel is None:
                continue
            if hasattr(panel, "set_sample_markers"):
                panel.set_sample_markers(markers)
            if hasattr(panel, "set_sample_magnifier_enabled"):
                panel.set_sample_magnifier_enabled(
                    magnifier_active and panel_name != "image_original_compare",
                    radius=radius,
                )

    def _load_color_picker_samples_for_selected(self, path: Path | None = None) -> None:
        raw_selected = path if path is not None else getattr(self, "_selected_file", None)
        if raw_selected is None:
            self._clear_color_picker_samples_for_file_change()
            return
        selected = Path(raw_selected).expanduser()
        try:
            payload = load_raw_sidecar(selected)
        except FileNotFoundError:
            self._clear_color_picker_samples_for_file_change()
            return
        except Exception as exc:
            self._clear_color_picker_samples_for_file_change()
            self._log_preview(f"Aviso: no se pudieron cargar muestras de color ({raw_sidecar_path(selected).name}): {exc}")
            return
        color_payload = payload.get("color_samples") if isinstance(payload.get("color_samples"), dict) else {}
        raw_samples = color_payload.get("samples") if isinstance(color_payload, dict) else []
        raw_sample_list = raw_samples if isinstance(raw_samples, list) else []
        samples = [
            sample
            for sample in (self._coerce_color_picker_sample(item) for item in raw_sample_list)
            if sample is not None
        ]
        self._color_picker_samples = samples
        raw_groups = color_payload.get("groups") if isinstance(color_payload, dict) else []
        groups = [
            self._color_sample_group_name(group)
            for group in (raw_groups if isinstance(raw_groups, list) else [])
        ]
        for sample in samples:
            group = self._color_sample_group_name(sample.get("group"))
            if group not in groups:
                groups.append(group)
        if not groups:
            groups = [self._default_color_sample_group()]
        self._color_picker_groups = groups
        self._color_picker_active_group = self._color_sample_group_name(
            color_payload.get("active_group") if isinstance(color_payload, dict) else groups[0]
        )
        self._color_picker_group_reference = self._color_sample_group_name(
            color_payload.get("group_reference") if isinstance(color_payload, dict) else groups[0]
        )
        self._color_picker_samples_source_key = self._normalized_path_key(selected) if hasattr(self, "_normalized_path_key") else str(selected)
        if samples:
            self._viewer_full_detail_requested = True
        self._refresh_color_samples_table()
        if hasattr(self, "label_color_picker"):
            if samples:
                self.label_color_picker.setText(self.tr("Color Lab:") + f" {len(samples)} " + self.tr("muestras guardadas"))
            else:
                self.label_color_picker.setText(self.tr("Color Lab: sin muestra"))
        self._update_color_picker_precision_warning()

    def _persist_color_picker_samples_for_selected(self) -> None:
        selected = getattr(self, "_selected_file", None)
        if selected is None:
            return
        path = Path(selected).expanduser()
        payload = self._color_picker_samples_payload(path)
        try:
            session_name = self.session_name_edit.text().strip() if hasattr(self, "session_name_edit") else ""
            write_raw_color_samples(
                path,
                payload,
                session_root=getattr(self, "_active_session_root", None),
                session_name=session_name,
            )
            if hasattr(self, "_invalidate_raw_sidecar_cache_for_path"):
                self._invalidate_raw_sidecar_cache_for_path(path)
        except Exception as exc:
            self._log_preview(f"Aviso: no se pudieron guardar muestras de color ({raw_sidecar_path(path).name}): {exc}")

    def _color_picker_samples_payload(self, path: Path) -> dict[str, Any]:
        samples = getattr(self, "_color_picker_samples", [])
        return {
            "schema": "org.probatia.probraw.color-samples.v1",
            "schema_version": 1,
            "source_path": str(path),
            "source_key": self._normalized_path_key(path) if hasattr(self, "_normalized_path_key") else str(path),
            "groups": self._color_sample_groups(),
            "active_group": self._active_color_sample_group(),
            "group_reference": self._color_sample_reference_group(),
            "samples": [self._serialize_color_picker_sample(sample) for sample in samples if isinstance(sample, dict)],
        }

    def _color_picker_samples_state(self) -> dict[str, Any]:
        selected = getattr(self, "_selected_file", None)
        path = Path(selected).expanduser() if selected is not None else Path("")
        return self._color_picker_samples_payload(path)

    def _restore_color_picker_samples_state(self, state: dict[str, Any], *, persist: bool = False) -> None:
        raw_samples = state.get("samples") if isinstance(state.get("samples"), list) else []
        samples = [
            sample
            for sample in (self._coerce_color_picker_sample(item) for item in raw_samples)
            if sample is not None
        ]
        self._color_picker_samples = samples
        raw_groups = state.get("groups") if isinstance(state.get("groups"), list) else []
        groups = [self._color_sample_group_name(group) for group in raw_groups]
        for sample in samples:
            group = self._color_sample_group_name(sample.get("group"))
            if group not in groups:
                groups.append(group)
        if not groups:
            groups = [self._default_color_sample_group()]
        self._color_picker_groups = groups
        self._color_picker_active_group = self._color_sample_group_name(state.get("active_group") or groups[0])
        self._color_picker_group_reference = self._color_sample_group_name(state.get("group_reference") or groups[0])
        self._refresh_color_samples_table()
        if hasattr(self, "label_color_picker"):
            if samples:
                self.label_color_picker.setText(self.tr("Color Lab:") + f" {len(samples)} " + self.tr("muestras"))
            else:
                self.label_color_picker.setText(self.tr("Color Lab: sin muestra"))
        self._update_color_picker_precision_warning()
        if persist:
            self._persist_color_picker_samples_for_selected()

    def _serialize_color_picker_sample(self, sample: dict[str, Any]) -> dict[str, Any]:
        rgb = np.asarray(sample.get("rgb"), dtype=np.float64).reshape(-1)
        lab = np.asarray(sample.get("lab"), dtype=np.float64).reshape(-1)
        image_size_raw = sample.get("image_size") if isinstance(sample.get("image_size"), (list, tuple)) else []
        image_size = [int(v) for v in image_size_raw[:2]] if len(image_size_raw) >= 2 else []
        return {
            "x": int(sample.get("x", 0)),
            "y": int(sample.get("y", 0)),
            "matrix": str(sample.get("matrix") or "1x1"),
            "count": int(sample.get("count", 0)),
            "rgb": [float(v) for v in rgb[:3]] if rgb.size >= 3 else [0.0, 0.0, 0.0],
            "lab": [float(v) for v in lab[:3]] if lab.size >= 3 else [0.0, 0.0, 0.0],
            "chroma": float(sample.get("chroma") or self._lab_chroma(sample.get("lab"))),
            "inside_a": bool(sample.get("inside_a")),
            "inside_b": bool(sample.get("inside_b")),
            "inside_common": bool(sample.get("inside_common")),
            "label_a": str(sample.get("label_a") or "A"),
            "label_b": str(sample.get("label_b") or "B"),
            "source_profile": str(sample.get("source_profile") or ""),
            "monitor_profile": str(sample.get("monitor_profile") or ""),
            "profile_generated_by_app": bool(sample.get("profile_generated_by_app")),
            "profile_precision_note": str(sample.get("profile_precision_note") or ""),
            "marker_color": str(sample.get("marker_color") or "#22d3ee"),
            "marker_text_color": str(sample.get("marker_text_color") or "#ffffff"),
            "source_path": str(sample.get("source_path") or getattr(self, "_selected_file", "") or ""),
            "image_size": image_size,
            "group": self._color_sample_group_name(sample.get("group")),
            "name": str(sample.get("name") or ""),
            "note": str(sample.get("note") or ""),
        }

    def _coerce_color_picker_sample(self, sample: dict[str, Any]) -> dict[str, Any] | None:
        try:
            lab = np.asarray(sample.get("lab"), dtype=np.float64).reshape(-1)[:3]
            rgb = np.asarray(sample.get("rgb"), dtype=np.float64).reshape(-1)[:3]
        except Exception:
            return None
        if lab.size < 3 or rgb.size < 3 or not np.all(np.isfinite(lab)) or not np.all(np.isfinite(rgb)):
            return None
        try:
            image_size_raw = sample.get("image_size") if isinstance(sample.get("image_size"), (list, tuple)) else []
            image_size = [int(image_size_raw[0]), int(image_size_raw[1])] if len(image_size_raw) >= 2 else []
        except Exception:
            image_size = []
        return {
            "x": int(sample.get("x", 0)),
            "y": int(sample.get("y", 0)),
            "matrix": str(sample.get("matrix") or "1x1"),
            "count": int(sample.get("count", 0)),
            "rgb": np.clip(rgb, 0.0, 1.0).astype(np.float64).tolist(),
            "lab": lab.astype(np.float64).tolist(),
            "chroma": float(sample.get("chroma") or self._lab_chroma(lab)),
            "inside_a": bool(sample.get("inside_a")),
            "inside_b": bool(sample.get("inside_b")),
            "inside_common": bool(sample.get("inside_common")),
            "label_a": str(sample.get("label_a") or "A"),
            "label_b": str(sample.get("label_b") or "B"),
            "source_profile": str(sample.get("source_profile") or ""),
            "monitor_profile": str(sample.get("monitor_profile") or ""),
            "profile_generated_by_app": bool(sample.get("profile_generated_by_app")),
            "profile_precision_note": str(sample.get("profile_precision_note") or ""),
            "marker_color": str(sample.get("marker_color") or "#22d3ee"),
            "marker_text_color": str(sample.get("marker_text_color") or "#ffffff"),
            "source_path": str(sample.get("source_path") or ""),
            "image_size": image_size,
            "group": self._color_sample_group_name(sample.get("group")),
            "name": str(sample.get("name") or ""),
            "note": str(sample.get("note") or ""),
        }

    def _color_sample_rgb_text(self, sample: dict[str, Any]) -> str:
        rgb = np.asarray(sample.get("rgb"), dtype=np.float64).reshape(-1)
        if rgb.size < 3:
            return "--"
        return f"{float(rgb[0]):.4f}, {float(rgb[1]):.4f}, {float(rgb[2]):.4f}"

    def _color_sample_lab_text(self, sample: dict[str, Any]) -> str:
        lab = np.asarray(sample.get("lab"), dtype=np.float64).reshape(-1)
        if lab.size < 3:
            return "--"
        return f"{float(lab[0]):.2f}, {float(lab[1]):+.2f}, {float(lab[2]):+.2f}"

    def _lab_chroma(self, lab: Any) -> float:
        try:
            values = np.asarray(lab, dtype=np.float64).reshape(-1)
            if values.size < 3:
                return 0.0
            return float(np.linalg.norm(values[1:3]))
        except Exception:
            return 0.0

    def _color_sample_delta_e_text(self, lab: Any, reference_lab: Any, *, method: str) -> str:
        try:
            current = np.asarray(lab, dtype=np.float64).reshape((1, 3))
            reference = np.asarray(reference_lab, dtype=np.float64).reshape((1, 3))
            if str(method) == "76":
                value = np.asarray(delta_e76(current, reference), dtype=np.float64).reshape(-1)
            else:
                value = np.asarray(delta_e2000(current, reference), dtype=np.float64).reshape(-1)
            return f"{float(value[0]):.2f}" if value.size else "--"
        except Exception:
            return "--"

    def _color_sample_delta_c_text(self, lab: Any, reference_lab: Any) -> str:
        try:
            current = self._lab_chroma(lab)
            reference = self._lab_chroma(reference_lab)
            return f"{current - reference:+.2f}"
        except Exception:
            return "--"

    def _sample_neutral_patch(self, x: float, y: float, *, radius: int = 9) -> tuple[np.ndarray, int]:
        if self._original_linear is None:
            raise ValueError("No hay imagen cargada para muestrear.")
        image = np.asarray(self._original_linear, dtype=np.float32)
        if image.ndim != 3 or image.shape[2] < 3:
            raise ValueError("La imagen cargada no contiene datos RGB.")

        h, w = image.shape[:2]
        xi = int(round(float(np.clip(x, 0, max(0, w - 1)))))
        yi = int(round(float(np.clip(y, 0, max(0, h - 1)))))
        r = max(2, int(radius))
        crop = image[max(0, yi - r) : min(h, yi + r + 1), max(0, xi - r) : min(w, xi + r + 1), :3]
        flat = crop.reshape((-1, 3))
        finite = np.all(np.isfinite(flat), axis=1)
        flat = np.clip(flat[finite], 0.0, 1.0)
        if flat.shape[0] < 4:
            raise ValueError("La zona muestreada no contiene suficientes pixeles validos.")

        luminance = flat @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
        max_channel = np.max(flat, axis=1)
        valid = (luminance > 0.015) & (luminance < 0.98) & (max_channel < 0.995)
        if int(np.count_nonzero(valid)) < 4:
            raise ValueError("El punto elegido esta demasiado oscuro o saturado; elige un gris/blanco sin clipping.")

        sample = np.median(flat[valid], axis=0).astype(np.float32)
        return sample, int(np.count_nonzero(valid))

    def _apply_neutral_picker_at(self, x: float, y: float) -> None:
        try:
            sample, count = self._sample_neutral_patch(x, y)
            temperature, tint = estimate_temperature_tint_from_neutral_sample(sample)
        except ValueError as exc:
            QtWidgets.QMessageBox.information(self, self.tr("Punto neutro"), str(exc))
            self._set_status(str(exc))
            return

        self.combo_illuminant_render.blockSignals(True)
        self._set_combo_text(self.combo_illuminant_render, "Personalizado")
        self.combo_illuminant_render.blockSignals(False)

        self.spin_render_temperature.blockSignals(True)
        self.spin_render_tint.blockSignals(True)
        self.spin_render_temperature.setValue(int(temperature))
        self.spin_render_tint.setValue(float(tint))
        self.spin_render_temperature.blockSignals(False)
        self.spin_render_tint.blockSignals(False)

        if hasattr(self, "label_neutral_picker"):
            self.label_neutral_picker.setText(
                (
                    "Punto neutro: "
                    f"RGB {sample[0]:.3f}, {sample[1]:.3f}, {sample[2]:.3f} "
                    f"({count} px) -> {temperature} K / matiz {tint:+.1f}"
                )
            )
        self._set_neutral_picker_active(False)
        if self._original_linear is not None:
            self._refresh_preview()
        self._save_active_session(silent=True)
        if hasattr(self, "_schedule_render_adjustment_sidecar_persist"):
            self._schedule_render_adjustment_sidecar_persist(immediate=True)
        self._set_status(self.tr("Balance neutro aplicado:") + f" {temperature} K, " + self.tr("matiz") + f" {tint:+.1f}")

    def _on_tone_curve_enabled_changed(self, enabled: bool) -> None:
        if not enabled and hasattr(self.tone_curve_editor, "set_range_dragging"):
            self.tone_curve_editor.set_range_dragging(False)
        self._set_tone_curve_controls_enabled(enabled)
        if self._original_linear is not None and hasattr(self, "_update_tone_curve_histogram_for_current_controls"):
            self._update_tone_curve_histogram_for_current_controls(force=True)
        self._on_render_control_change()

    def _on_tone_curve_channel_changed(self, _index: int) -> None:
        previous = getattr(self, "_tone_curve_active_channel", "luminance")
        current = self._tone_curve_channel_key()
        if previous != current:
            self._save_visible_tone_curve_channel_state(previous)
        self._load_tone_curve_channel_into_editor(current)
        self._on_render_control_change(preview=bool(self.check_tone_curve_enabled.isChecked()))

    def _on_tone_curve_preset_changed(self, _index: int) -> None:
        key = self._tone_curve_preset_key()
        if key != "custom":
            self.tone_curve_editor.set_points(self._tone_curve_preset_points(key), emit=False)
        self._save_visible_tone_curve_channel_state()
        if self._original_linear is not None and hasattr(self, "_update_tone_curve_histogram_for_current_controls"):
            self._update_tone_curve_histogram_for_current_controls(force=True)
        self._on_render_control_change(preview=bool(self.check_tone_curve_enabled.isChecked()))

    def _is_tone_curve_range_slider(self, slider: object | None = None) -> bool:
        if slider is None:
            slider = self.sender()
        return slider in (
            getattr(self, "slider_tone_curve_black", None),
            getattr(self, "slider_tone_curve_white", None),
        )

    def _on_tone_curve_range_changed(self, *_args) -> None:
        sender = self.sender()
        black = self.slider_tone_curve_black.value() / 1000.0
        white = self.slider_tone_curve_white.value() / 1000.0
        if white <= black + 0.01:
            if sender is self.slider_tone_curve_black:
                black = max(0.0, white - 0.01)
            else:
                white = min(1.0, black + 0.01)
            self._set_tone_curve_range_controls(black, white)
        else:
            self.tone_curve_editor.set_input_range(black, white)
        dragging = bool(
            self._is_tone_curve_range_slider(sender)
            and hasattr(sender, "isSliderDown")
            and sender.isSliderDown()
        )
        if hasattr(self.tone_curve_editor, "set_range_dragging"):
            self.tone_curve_editor.set_range_dragging(dragging)
        preview_enabled = bool(self.check_tone_curve_enabled.isChecked())
        if dragging:
            if preview_enabled and self._original_linear is not None and hasattr(self, "_schedule_tone_curve_drag_preview_refresh"):
                self._schedule_tone_curve_drag_preview_refresh()
            if preview_enabled and self._original_linear is not None and hasattr(self, "_schedule_exact_histogram_refresh"):
                self._schedule_exact_histogram_refresh(delay_ms=80, mark_pending=False)
            return
        if self._original_linear is not None and hasattr(self, "_update_tone_curve_histogram_for_current_controls"):
            self._update_tone_curve_histogram_for_current_controls(force=True)
        self._on_render_control_change(preview=preview_enabled)
        if preview_enabled and self._original_linear is not None and hasattr(self, "_schedule_exact_histogram_refresh"):
            self._schedule_exact_histogram_refresh(delay_ms=80, mark_pending=False)

    def _on_tone_curve_range_interaction_finished(self) -> None:
        timer = getattr(self, "_tone_curve_preview_timer", None)
        if timer is not None:
            timer.stop()
        if hasattr(self.tone_curve_editor, "set_range_dragging"):
            self.tone_curve_editor.set_range_dragging(False)
        self._sync_tone_curve_editor_channel_overlay()
        preview_enabled = bool(self.check_tone_curve_enabled.isChecked())
        if self._original_linear is not None and hasattr(self, "_update_tone_curve_histogram_for_current_controls"):
            self._update_tone_curve_histogram_for_current_controls(force=True, async_update=True)
        self._on_render_control_change(preview=preview_enabled)
        if preview_enabled and self._original_linear is not None and hasattr(self, "_schedule_post_interaction_exact_preview_refresh"):
            self._schedule_post_interaction_exact_preview_refresh(delay_ms=260)
        if self._original_linear is not None and hasattr(self, "_schedule_exact_histogram_refresh"):
            self._schedule_exact_histogram_refresh(delay_ms=80)

    def _on_tone_curve_points_changed(self, _points: object) -> None:
        if self._tone_curve_preset_key() != "custom":
            self.combo_tone_curve_preset.blockSignals(True)
            self._set_combo_data(self.combo_tone_curve_preset, "custom")
            self.combo_tone_curve_preset.blockSignals(False)
        editor = getattr(self, "tone_curve_editor", None)
        dragging = bool(editor is not None and hasattr(editor, "is_dragging") and editor.is_dragging())
        self._save_visible_tone_curve_channel_state(sync_editor=not dragging)
        preview_enabled = bool(self.check_tone_curve_enabled.isChecked())
        if (
            not dragging
            and self._original_linear is not None
            and hasattr(self, "_update_tone_curve_histogram_for_current_controls")
        ):
            self._update_tone_curve_histogram_for_current_controls(force=True)
        if dragging:
            if preview_enabled and self._original_linear is not None and hasattr(self, "_schedule_tone_curve_drag_preview_refresh"):
                self._schedule_tone_curve_drag_preview_refresh()
            return
        self._on_render_control_change(preview=preview_enabled)

    def _on_tone_curve_interaction_finished(self) -> None:
        timer = getattr(self, "_tone_curve_preview_timer", None)
        if timer is not None:
            timer.stop()
        self._save_visible_tone_curve_channel_state(sync_editor=True)
        if self._original_linear is not None and hasattr(self, "_update_tone_curve_histogram_for_current_controls"):
            self._update_tone_curve_histogram_for_current_controls(force=True, async_update=True)
        self._on_render_control_change(preview=bool(self.check_tone_curve_enabled.isChecked()))

    def _on_render_control_change(self, *_args: object, preview: bool = True) -> None:
        if int(getattr(self, "_suspend_render_adjustment_autosave", 0) or 0) > 0:
            return
        if hasattr(self, "_push_edit_history_snapshot"):
            self._push_edit_history_snapshot("render")
        if not (
            hasattr(self, "_is_direct_preview_interaction_active")
            and self._is_direct_preview_interaction_active()
        ):
            timer = getattr(self, "_tone_curve_preview_timer", None)
            if timer is not None:
                timer.stop()
        if bool(preview) and self._original_linear is not None:
            if hasattr(self, "_mark_preview_control_interaction"):
                self._mark_preview_control_interaction()
            self._schedule_preview_refresh()
            if hasattr(self, "_schedule_deferred_final_preview_refresh"):
                self._schedule_deferred_final_preview_refresh()
        if (
            hasattr(self, "_set_active_named_adjustment_profile_id")
            and self._active_named_adjustment_profile_id("color_contrast")
        ):
            self._set_active_named_adjustment_profile_id("color_contrast", "")
            if hasattr(self, "_refresh_named_adjustment_profile_combo"):
                self._refresh_named_adjustment_profile_combo("color_contrast")
        if hasattr(self, "_schedule_render_adjustment_sidecar_persist"):
            interaction_active = (
                self._is_direct_preview_interaction_active()
                if hasattr(self, "_is_direct_preview_interaction_active")
                else False
            )
            if not interaction_active:
                self._schedule_render_adjustment_sidecar_persist()

    def _reset_tone_curve(self) -> None:
        history_suspend = int(getattr(self, "_suspend_edit_history", 0) or 0)
        self._suspend_edit_history = history_suspend + 1
        self.check_tone_curve_enabled.setChecked(False)
        self._tone_curve_channel_points = {
            "luminance": self._identity_tone_curve_points(),
            "red": self._identity_tone_curve_points(),
            "green": self._identity_tone_curve_points(),
            "blue": self._identity_tone_curve_points(),
        }
        self._tone_curve_channel_presets = {
            "luminance": "linear",
            "red": "linear",
            "green": "linear",
            "blue": "linear",
        }
        self._tone_curve_active_channel = "luminance"
        if hasattr(self, "combo_tone_curve_channel"):
            self._set_combo_data(self.combo_tone_curve_channel, "luminance")
        self._set_combo_data(self.combo_tone_curve_preset, "linear")
        self._set_tone_curve_range_controls(0.0, 1.0)
        self.tone_curve_editor.set_points(self._tone_curve_preset_points("linear"), emit=False)
        self._sync_tone_curve_editor_channel_overlay()
        self._set_tone_curve_controls_enabled(False)
        self._suspend_edit_history = history_suspend
        self._on_render_control_change()

    def _reset_color_adjustments(self, *_args: object, refresh: bool = True) -> None:
        history_suspend = int(getattr(self, "_suspend_edit_history", 0) or 0)
        self._suspend_edit_history = history_suspend + 1
        self._set_neutral_picker_active(False)
        self._set_color_picker_active(False)
        if hasattr(self, "label_neutral_picker"):
            self.label_neutral_picker.setText(self.tr("Punto neutro: sin muestra"))
        if hasattr(self, "label_color_picker"):
            self.label_color_picker.setText(self.tr("Color Lab: sin muestra"))
        self.combo_illuminant_render.setCurrentIndex(1)
        self.spin_render_temperature.setValue(5003)
        self.spin_render_tint.setValue(0.0)
        if hasattr(self, "slider_vibrance"):
            self.slider_vibrance.setValue(0)
        if hasattr(self, "slider_saturation"):
            self.slider_saturation.setValue(0)
        self._suspend_edit_history = history_suspend
        if hasattr(self, "_push_edit_history_snapshot"):
            self._push_edit_history_snapshot("reset_color")
        if refresh and self._original_linear is not None:
            self._refresh_preview()

    def _reset_tone_adjustments(self, *_args: object, refresh: bool = True) -> None:
        history_suspend = int(getattr(self, "_suspend_edit_history", 0) or 0)
        self._suspend_edit_history = history_suspend + 1
        self.slider_brightness.setValue(0)
        self.slider_black_point.setValue(0)
        self.slider_white_point.setValue(1000)
        self.slider_contrast.setValue(0)
        if hasattr(self, "slider_highlights"):
            self.slider_highlights.setValue(0)
        if hasattr(self, "slider_shadows"):
            self.slider_shadows.setValue(0)
        if hasattr(self, "slider_whites"):
            self.slider_whites.setValue(0)
        if hasattr(self, "slider_blacks"):
            self.slider_blacks.setValue(0)
        self.slider_midtone.setValue(100)
        self._reset_tone_curve()
        self._suspend_edit_history = history_suspend
        if hasattr(self, "_push_edit_history_snapshot"):
            self._push_edit_history_snapshot("reset_tone")
        if refresh and self._original_linear is not None:
            self._refresh_preview()

    def _reset_color_grading(self, *_args: object, refresh: bool = True) -> None:
        history_suspend = int(getattr(self, "_suspend_edit_history", 0) or 0)
        self._suspend_edit_history = history_suspend + 1
        self.slider_grade_midtones_hue.setValue(45)
        self.slider_grade_midtones_sat.setValue(0)
        self.slider_grade_shadows_hue.setValue(240)
        self.slider_grade_shadows_sat.setValue(0)
        self.slider_grade_highlights_hue.setValue(50)
        self.slider_grade_highlights_sat.setValue(0)
        self.slider_grade_blending.setValue(50)
        self.slider_grade_balance.setValue(0)
        self._suspend_edit_history = history_suspend
        if hasattr(self, "_push_edit_history_snapshot"):
            self._push_edit_history_snapshot("reset_grading")
        if refresh and self._original_linear is not None:
            self._refresh_preview()

    def _reset_basic_adjustments(self) -> None:
        history_suspend = int(getattr(self, "_suspend_edit_history", 0) or 0)
        self._suspend_edit_history = history_suspend + 1
        self._reset_color_adjustments(refresh=False)
        self._reset_tone_adjustments(refresh=False)
        self._reset_color_grading(refresh=False)
        self._suspend_edit_history = history_suspend
        if hasattr(self, "_push_edit_history_snapshot"):
            self._push_edit_history_snapshot("reset_basic")
        if self._original_linear is not None:
            self._refresh_preview()

    def _sync_viewer_transform(self) -> None:
        self._syncing_viewer_transform = True
        try:
            for panel_name in (
                "image_result_single",
                "image_original_compare",
                "image_result_compare",
            ):
                if hasattr(self, panel_name):
                    getattr(self, panel_name).set_view_transform(
                        zoom=self._viewer_zoom,
                        rotation=self._viewer_rotation,
                    )
        finally:
            self._syncing_viewer_transform = False
        if hasattr(self, "viewer_zoom_label"):
            scale = self._viewer_display_scale()
            shown = scale if scale is not None else float(self._viewer_zoom)
            self.viewer_zoom_label.setText(f"{int(round(float(shown) * 100))}%")

    def _on_viewer_panel_transform_changed(self, zoom: float, rotation: float) -> None:
        if bool(getattr(self, "_syncing_viewer_transform", False)):
            return
        self._viewer_zoom = float(np.clip(float(zoom), 0.05, 64.0))
        self._viewer_rotation = float(rotation) % 360.0
        self._sync_viewer_transform()
        self._clear_pending_real_pixel_sync_if_manual_zoom_moved()
        self._ensure_full_detail_preview_if_needed()
        if abs(float(self._viewer_rotation) % 360.0) <= 1e-6 and hasattr(self, "_schedule_visible_viewport_preview_refresh"):
            self._schedule_visible_viewport_preview_refresh(duration_ms=450)

    def _viewer_reference_panel(self) -> ImagePanel | None:
        names = (
            ("image_result_single",),
            ("image_result_compare", "image_original_compare"),
        )
        stack = getattr(self, "viewer_stack", None)
        active_names = names[1] if stack is not None and int(stack.currentIndex()) == 1 else names[0]
        for panel_name in active_names:
            panel = getattr(self, panel_name, None)
            if panel is not None and hasattr(panel, "image_size") and panel.image_size() is not None:
                return panel
        return None

    def _viewer_display_scale(self) -> float | None:
        panel = self._viewer_reference_panel()
        if panel is None or not hasattr(panel, "current_display_scale"):
            return None
        return panel.current_display_scale()

    def _viewer_zoom_in(self) -> None:
        self._viewer_zoom = float(np.clip(self._viewer_zoom * 1.25, 0.05, 64.0))
        self._sync_viewer_transform()
        self._clear_pending_real_pixel_sync_if_manual_zoom_moved()
        self._ensure_full_detail_preview_if_needed()
        if hasattr(self, "_schedule_visible_viewport_preview_refresh"):
            self._schedule_visible_viewport_preview_refresh(duration_ms=450)

    def _viewer_zoom_out(self) -> None:
        self._viewer_zoom = float(np.clip(self._viewer_zoom / 1.25, 0.05, 64.0))
        self._sync_viewer_transform()
        self._clear_pending_real_pixel_sync_if_manual_zoom_moved()
        if hasattr(self, "_schedule_visible_viewport_preview_refresh"):
            self._schedule_visible_viewport_preview_refresh(duration_ms=450)

    def _viewer_zoom_100(self) -> None:
        panel = self._viewer_reference_panel()
        if panel is not None and hasattr(panel, "view_zoom_for_display_scale"):
            self._viewer_zoom = panel.view_zoom_for_display_scale(1.0)
        else:
            self._viewer_zoom = 1.0
        self._viewer_full_detail_requested = True
        self._viewer_real_pixel_sync_pending = True
        self._sync_viewer_transform()
        self._ensure_full_detail_preview_if_needed(force=True)
        if hasattr(self, "_schedule_visible_viewport_preview_refresh"):
            self._schedule_visible_viewport_preview_refresh(duration_ms=450)

    def _clear_pending_real_pixel_sync_if_manual_zoom_moved(self) -> None:
        scale = self._viewer_display_scale()
        if scale is None:
            return
        if abs(float(scale) - 1.0) > 0.02:
            self._viewer_real_pixel_sync_pending = False

    def _sync_viewer_real_pixel_scale_if_requested(self) -> None:
        if not bool(getattr(self, "_viewer_real_pixel_sync_pending", False)):
            return
        loaded_request = getattr(self, "_loaded_preview_max_side_request", None)
        loaded_fast = bool(getattr(self, "_loaded_preview_fast_raw", True))
        if loaded_request != 0 or loaded_fast:
            return
        panel = self._viewer_reference_panel()
        if panel is None or not hasattr(panel, "view_zoom_for_display_scale"):
            return
        scale = self._viewer_display_scale()
        if scale is not None and float(scale) > 1.02:
            self._viewer_real_pixel_sync_pending = False
            return
        target_zoom = panel.view_zoom_for_display_scale(1.0)
        if abs(float(getattr(self, "_viewer_zoom", 1.0)) - float(target_zoom)) <= 1e-5:
            self._viewer_real_pixel_sync_pending = False
            self._sync_viewer_transform()
            return
        self._viewer_zoom = float(target_zoom)
        self._viewer_real_pixel_sync_pending = False
        self._sync_viewer_transform()

    def _viewer_fit(self) -> None:
        self._viewer_full_detail_requested = False
        self._viewer_real_pixel_sync_pending = False
        self._viewer_zoom = 1.0
        self._viewer_rotation = 0.0
        self._sync_viewer_transform()

    def _ensure_full_detail_preview_if_needed(self, *, force: bool = False) -> None:
        selected = getattr(self, "_selected_file", None)
        if selected is None or Path(selected).suffix.lower() not in RAW_EXTENSIONS:
            return
        if self._original_linear is None:
            return
        scale = self._viewer_display_scale()
        if not force and (scale is None or float(scale) < 0.98):
            return
        self._viewer_full_detail_requested = True
        loaded_request = getattr(self, "_loaded_preview_max_side_request", None)
        loaded_fast = bool(getattr(self, "_loaded_preview_fast_raw", True))
        if loaded_request == 0 and not loaded_fast:
            return
        self._viewer_real_pixel_sync_pending = bool(scale is None or float(scale) <= 1.02)
        self._set_status(self.tr("Cargando detalle 1:1..."))
        self._on_load_selected(show_message=False)

    def _viewer_rotate_left(self) -> None:
        self._viewer_rotation = (float(self._viewer_rotation) - 90.0) % 360.0
        self._sync_viewer_transform()
        if hasattr(self, "_push_edit_history_snapshot"):
            self._push_edit_history_snapshot("rotate_left")
        if hasattr(self, "_schedule_render_adjustment_sidecar_persist"):
            self._schedule_render_adjustment_sidecar_persist()

    def _viewer_rotate_right(self) -> None:
        self._viewer_rotation = (float(self._viewer_rotation) + 90.0) % 360.0
        self._sync_viewer_transform()
        if hasattr(self, "_push_edit_history_snapshot"):
            self._push_edit_history_snapshot("rotate_right")
        if hasattr(self, "_schedule_render_adjustment_sidecar_persist"):
            self._schedule_render_adjustment_sidecar_persist()

    def _on_histogram_clip_witness_toggled(self, checked: bool) -> None:
        self._settings.setValue("view/histogram_clip_witness", bool(checked))
        if hasattr(self, "viewer_histogram"):
            self.viewer_histogram.set_clip_markers_enabled(bool(checked))
            self._apply_histogram_clip_metrics(self.viewer_histogram.clip_metrics())

    def _on_image_clip_overlay_toggled(self, checked: bool) -> None:
        self._settings.setValue("view/image_clip_overlay", bool(checked))
        for panel_name in ("image_result_single", "image_result_compare", "image_original_compare"):
            if hasattr(self, panel_name):
                panel = getattr(self, panel_name)
                panel.set_clip_overlay_enabled(bool(checked))
                if not checked:
                    panel.clear_clip_overlay()
        if checked and self._preview_srgb is not None:
            compare_enabled = bool(getattr(self, "chk_compare", None) and self.chk_compare.isChecked())
            display_u8 = self._display_u8_for_screen(
                self._preview_srgb,
                bypass_profile=False,
            )
            self._set_result_display_u8(display_u8, compare_enabled=compare_enabled)
            if compare_enabled:
                self._ensure_original_compare_panel(bypass_profile=False)

    @staticmethod
    def _clip_overlay_classes(display_u8: np.ndarray | None) -> np.ndarray | None:
        if display_u8 is None:
            return None
        rgb = np.asarray(display_u8)
        if rgb.ndim != 3 or rgb.shape[2] < 3:
            return None
        rgb_u8 = np.ascontiguousarray(rgb[..., :3].astype(np.uint8))
        r = rgb_u8[..., 0]
        g = rgb_u8[..., 1]
        b = rgb_u8[..., 2]
        shadow_limit = int(VIEWER_HISTOGRAM_SHADOW_CLIP_U8)
        highlight_limit = int(VIEWER_HISTOGRAM_HIGHLIGHT_CLIP_U8)
        shadow_mask = (r <= shadow_limit) & (g <= shadow_limit) & (b <= shadow_limit)
        highlight_mask = (r >= highlight_limit) | (g >= highlight_limit) | (b >= highlight_limit)
        classes = np.zeros(rgb_u8.shape[:2], dtype=np.uint8)
        classes[highlight_mask] = 2
        classes[shadow_mask] = 1
        both = shadow_mask & highlight_mask
        if np.any(both):
            classes[both] = 3
        return classes

    def _apply_clip_overlay_to_panel(self, panel: ImagePanel, display_u8: np.ndarray | None) -> None:
        enabled = bool(hasattr(self, "check_image_clip_overlay") and self.check_image_clip_overlay.isChecked())
        panel.set_clip_overlay_enabled(enabled)
        if not enabled:
            panel.clear_clip_overlay()
            return
        panel.set_clip_overlay_classes(self._clip_overlay_classes(display_u8))

    def _clear_clip_overlay_panels(self) -> None:
        for panel_name in ("image_result_single", "image_result_compare", "image_original_compare"):
            if hasattr(self, panel_name):
                getattr(self, panel_name).clear_clip_overlay()

    def _preview_colorimetric_u8(self, fallback_u8: np.ndarray | None) -> np.ndarray | None:
        source = getattr(self, "_preview_srgb", None)
        if source is None:
            return fallback_u8
        try:
            source_rgb = np.asarray(source)
            if fallback_u8 is not None:
                fallback = np.asarray(fallback_u8)
                if source_rgb.shape[:2] != fallback.shape[:2]:
                    return fallback_u8
            return srgb_to_display_u8(source_rgb, None)
        except Exception:
            return fallback_u8

    def _preview_histogram_source_label(self) -> str:
        if self._active_session_icc_for_settings() is not None:
            return self.tr("Histograma: sRGB colorimétrico tras ICC de entrada, antes del ICC del monitor.")
        return self.tr("Histograma: sRGB de preview, antes del ICC del monitor.")

    def _update_viewer_histogram(self, colorimetric_u8: np.ndarray | None) -> None:
        if not hasattr(self, "viewer_histogram"):
            return
        self.viewer_histogram.set_image_u8(
            colorimetric_u8,
            source_label=self._preview_histogram_source_label() if colorimetric_u8 is not None else None,
        )
        self._apply_histogram_clip_metrics(self.viewer_histogram.clip_metrics())

    def _clear_viewer_histogram(self) -> None:
        if hasattr(self, "viewer_histogram"):
            self.viewer_histogram.clear()
        self._clear_clip_overlay_panels()
        self._apply_histogram_clip_metrics(None)

    def _apply_histogram_clip_metrics(self, metrics: dict[str, float] | None) -> None:
        if not hasattr(self, "histogram_shadow_label") or not hasattr(self, "histogram_highlight_label"):
            return
        if metrics is None:
            self.histogram_shadow_label.setText(self.tr("Sombras: --"))
            self.histogram_highlight_label.setText(self.tr("Luces: --"))
            self.histogram_shadow_label.setStyleSheet("font-size: 12px; color: #6b7280;")
            self.histogram_highlight_label.setStyleSheet("font-size: 12px; color: #6b7280;")
            return

        shadow_pct = float(metrics.get("shadow_any", 0.0)) * 100.0
        highlight_pct = float(metrics.get("highlight_any", 0.0)) * 100.0
        self.histogram_shadow_label.setText(self.tr("Sombras:") + f" {shadow_pct:.2f}%")
        self.histogram_highlight_label.setText(self.tr("Luces:") + f" {highlight_pct:.2f}%")
        alert_pct = float(VIEWER_HISTOGRAM_CLIP_ALERT_RATIO) * 100.0
        shadow_alert = shadow_pct > alert_pct
        highlight_alert = highlight_pct > alert_pct
        self.histogram_shadow_label.setStyleSheet(
            "font-size: 12px; color: #60a5fa;" if shadow_alert else "font-size: 12px; color: #94a3b8;"
        )
        self.histogram_highlight_label.setStyleSheet(
            "font-size: 12px; color: #f87171;" if highlight_alert else "font-size: 12px; color: #94a3b8;"
        )

    def _normalize_recipe_output_for_color_management(self, recipe: Recipe) -> Recipe:
        if is_generic_output_space(recipe.output_space):
            profile = generic_output_profile(recipe.output_space)
            recipe.output_linear = False
            if str(recipe.tone_curve or "").strip().lower() == "linear":
                recipe.tone_curve = "srgb" if profile.key == "srgb" else f"gamma:{profile.gamma:.3g}"
        elif self._is_camera_output_space(recipe.output_space):
            recipe.output_linear = True
            recipe.tone_curve = "linear"
        return recipe

    def _build_effective_recipe(self) -> Recipe:
        recipe = Recipe()
        path_text = self.path_recipe.text().strip()
        if path_text:
            p = Path(path_text)
            if p.exists():
                recipe = load_recipe(p)

        recipe.raw_developer = str(self.combo_raw_developer.currentData() or self.combo_raw_developer.currentText())
        recipe.demosaic_algorithm = self._supported_gui_demosaic(
            str(self.combo_demosaic.currentData() or self.combo_demosaic.currentText()),
            notify=False,
        )
        if hasattr(self, "spin_demosaic_edge_quality"):
            recipe.demosaic_edge_quality = max(0, int(self.spin_demosaic_edge_quality.value()))
        if hasattr(self, "spin_false_color_suppression"):
            recipe.false_color_suppression_steps = max(0, int(self.spin_false_color_suppression.value()))
        if hasattr(self, "check_four_color_rgb"):
            recipe.four_color_rgb = bool(self.check_four_color_rgb.isChecked())
        if hasattr(self, "check_libraw_auto_bright"):
            recipe.libraw_auto_bright = bool(self.check_libraw_auto_bright.isChecked())
        if hasattr(self, "spin_libraw_auto_bright_thr"):
            recipe.libraw_auto_bright_thr = float(self.spin_libraw_auto_bright_thr.value())
        if hasattr(self, "spin_libraw_adjust_maximum_thr"):
            recipe.libraw_adjust_maximum_thr = float(self.spin_libraw_adjust_maximum_thr.value())
        if hasattr(self, "spin_libraw_bright"):
            recipe.libraw_bright = float(self.spin_libraw_bright.value())
        if hasattr(self, "combo_libraw_highlight_mode"):
            recipe.libraw_highlight_mode = str(
                self.combo_libraw_highlight_mode.currentData() or self.combo_libraw_highlight_mode.currentText()
            )
        if hasattr(self, "spin_libraw_exp_shift"):
            recipe.libraw_exp_shift = float(self.spin_libraw_exp_shift.value())
        if hasattr(self, "spin_libraw_exp_preserve_highlights"):
            recipe.libraw_exp_preserve_highlights = float(self.spin_libraw_exp_preserve_highlights.value())
        if hasattr(self, "check_libraw_no_auto_scale"):
            recipe.libraw_no_auto_scale = bool(self.check_libraw_no_auto_scale.isChecked())
        if hasattr(self, "spin_libraw_gamma_power"):
            recipe.libraw_gamma_power = float(self.spin_libraw_gamma_power.value())
        if hasattr(self, "spin_libraw_gamma_slope"):
            recipe.libraw_gamma_slope = float(self.spin_libraw_gamma_slope.value())
        if hasattr(self, "spin_libraw_ca_red"):
            recipe.libraw_chromatic_aberration_red = float(self.spin_libraw_ca_red.value())
        if hasattr(self, "spin_libraw_ca_blue"):
            recipe.libraw_chromatic_aberration_blue = float(self.spin_libraw_ca_blue.value())
        recipe.white_balance_mode = str(self.combo_wb_mode.currentData() or self.combo_wb_mode.currentText())
        recipe.wb_multipliers = self._parse_wb_multipliers(self.edit_wb_multipliers.text(), recipe.wb_multipliers)

        black_mode = str(self.combo_black_mode.currentData() or "metadata")
        black_value = int(self.spin_black_value.value())
        if black_mode == "fixed":
            recipe.black_level_mode = f"fixed:{black_value}"
        elif black_mode == "white":
            recipe.black_level_mode = f"white:{black_value}"
        else:
            recipe.black_level_mode = "metadata"

        recipe.exposure_compensation = float(self.spin_exposure.value())
        tone_mode = str(self.combo_tone_curve.currentData() or "linear")
        if tone_mode == "gamma":
            recipe.tone_curve = f"gamma:{float(self.spin_gamma.value()):.3g}"
        else:
            recipe.tone_curve = tone_mode

        recipe.output_linear = bool(self.check_output_linear.isChecked())
        recipe.denoise = self.combo_recipe_denoise.currentText().strip().lower()
        recipe.sharpen = self.combo_recipe_sharpen.currentText().strip().lower()
        recipe.working_space = self.combo_working_space.currentText().strip()
        recipe.output_space = self.combo_output_space.currentText().strip()
        recipe.sampling_strategy = self.combo_sampling.currentText().strip()
        recipe.profiling_mode = bool(self.check_profiling_mode.isChecked())
        recipe.input_color_assumption = self.edit_input_color.text().strip() or "camera_native"
        recipe.illuminant_metadata = self.edit_illuminant.text().strip() or None
        recipe.chart_reference = self.path_reference.text().strip() or None
        recipe.profile_engine = "argyll"
        recipe.argyll_colprof_args = self._build_colprof_args()
        return self._normalize_recipe_output_for_color_management(recipe)

    def _build_colprof_args(self) -> list[str]:
        quality = str(self.combo_profile_quality.currentData() or "m")
        algo = str(self.combo_profile_algo.currentData() or "-as")
        args = [f"-q{quality}", algo]
        custom = self.edit_colprof_args.text().strip()
        if custom:
            try:
                args.extend(shlex.split(custom))
            except Exception:
                self._log_preview("No se pudieron parsear args extra colprof; se ignoran.")
        if "-u" not in args:
            args.append("-u")
        if "-R" not in args:
            args.append("-R")
        return args

    def _parse_wb_multipliers(self, text: str, fallback: list[float]) -> list[float]:
        raw = [p.strip() for p in text.split(",") if p.strip()]
        vals: list[float] = []
        for p in raw:
            try:
                vals.append(float(p))
            except Exception:
                continue
        if len(vals) >= 3:
            return vals
        return list(fallback)

    def _normalized_profile_out_path(self) -> Path:
        self._ensure_session_output_controls()
        current = self.path_profile_out.text().strip()
        if not current or self._is_legacy_temp_output_path(current):
            current = str(self._session_default_outputs()["profile_out"])
        ext = self.combo_profile_format.currentText().strip().lower() or ".icc"
        p = Path(current)
        if p.suffix.lower() != ext:
            p = p.with_suffix(ext)
        self.path_profile_out.setText(str(p))
        if hasattr(self, "profile_out_path_edit"):
            self.profile_out_path_edit.setText(str(p))
        return p
