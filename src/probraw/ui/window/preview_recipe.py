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
        active = bool(self._neutral_picker_active or self._manual_chart_marking or tool_active)
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
        if hasattr(self, "label_neutral_picker"):
            self.label_neutral_picker.setText(self.tr("Punto neutro: sin muestra"))
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
