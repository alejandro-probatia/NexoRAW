from __future__ import annotations

import math

from ._imports import *  # noqa: F401,F403


class DisplayControlsMixin:
    def _init_fs_model(self) -> None:
        self._dir_model = QtWidgets.QFileSystemModel(self)
        for option in (
            "DontResolveSymlinks",
            "DontUseCustomDirectoryIcons",
            "DontWatchForChanges",
        ):
            if hasattr(QtWidgets.QFileSystemModel, option):
                self._dir_model.setOption(getattr(QtWidgets.QFileSystemModel, option), True)
        self._dir_model.setFilter(QtCore.QDir.AllDirs | QtCore.QDir.NoDotAndDotDot)
        root_path = self._filesystem_model_root(self._current_dir)
        self._dir_model_root_path = root_path
        index = self._dir_model.setRootPath(root_path)
        self.dir_tree.setModel(self._dir_model)
        self.dir_tree.setRootIndex(index)
        for c in (1, 2, 3):
            self.dir_tree.hideColumn(c)

    def _filesystem_model_root(self, folder: Path) -> str:
        if sys.platform.startswith("win"):
            return folder.anchor or str(folder)
        candidate = Path(folder).expanduser()
        try:
            candidate = candidate.resolve(strict=False)
        except Exception:
            pass

        active_root = getattr(self, "_active_session_root", None)
        if active_root is not None:
            try:
                active_root = Path(active_root).expanduser().resolve(strict=False)
                candidate.relative_to(active_root)
                return str(active_root)
            except Exception:
                pass

        project_root = None
        if hasattr(self, "_project_root_for_path"):
            try:
                project_root = self._project_root_for_path(candidate)
            except Exception:
                project_root = None
        if project_root is not None:
            return str(project_root)

        return str(candidate)

    def _set_filesystem_model_root(self, folder: Path) -> None:
        root_path = self._filesystem_model_root(folder)
        if getattr(self, "_dir_model_root_path", None) == root_path:
            return
        self._dir_model_root_path = root_path
        root_index = self._dir_model.setRootPath(root_path)
        self.dir_tree.setRootIndex(root_index)

    def _action(self, text: str, callback, shortcut: str | None = None) -> QtGui.QAction:
        a = QtGui.QAction(text, self)
        if shortcut:
            a.setShortcut(shortcut)
        a.triggered.connect(callback)
        return a

    def _button(self, text: str, callback) -> QtWidgets.QPushButton:
        b = QtWidgets.QPushButton(text)
        b.clicked.connect(callback)
        return b

    def _go_home_directory(self) -> None:
        self._set_current_directory(self._default_work_directory())

    def _slider(self, minimum: int, maximum: int, value: int, on_change, formatter):
        label = QtWidgets.QLabel(formatter(value))
        slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        slider.setRange(minimum, maximum)
        slider.setValue(value)
        slider.valueChanged.connect(lambda v: label.setText(formatter(v)))
        slider.valueChanged.connect(on_change)
        slider.sliderReleased.connect(self._on_slider_release)
        return slider, label

    def _render_adjustment_state(self) -> dict[str, Any]:
        channel_points = self._tone_curve_channel_points_state()
        luminance_points = channel_points.get(
            "luminance",
            [[float(x), float(y)] for x, y in normalize_tone_curve_points(self.tone_curve_editor.points())],
        )
        return {
            "illuminant": self.combo_illuminant_render.currentText().strip(),
            "temperature_kelvin": int(self.spin_render_temperature.value()),
            "tint": float(self.spin_render_tint.value()),
            "brightness_ev": self.slider_brightness.value() / 100.0,
            "black_point": self.slider_black_point.value() / 1000.0,
            "white_point": self.slider_white_point.value() / 1000.0,
            "contrast": self.slider_contrast.value() / 100.0,
            "highlights": self.slider_highlights.value() / 100.0,
            "shadows": self.slider_shadows.value() / 100.0,
            "whites": self.slider_whites.value() / 100.0,
            "blacks": self.slider_blacks.value() / 100.0,
            "midtone": self.slider_midtone.value() / 100.0,
            "vibrance": self.slider_vibrance.value() / 100.0,
            "saturation": self.slider_saturation.value() / 100.0,
            "grade_shadows_hue": float(self.slider_grade_shadows_hue.value()),
            "grade_shadows_saturation": self.slider_grade_shadows_sat.value() / 100.0,
            "grade_midtones_hue": float(self.slider_grade_midtones_hue.value()),
            "grade_midtones_saturation": self.slider_grade_midtones_sat.value() / 100.0,
            "grade_highlights_hue": float(self.slider_grade_highlights_hue.value()),
            "grade_highlights_saturation": self.slider_grade_highlights_sat.value() / 100.0,
            "grade_blending": self.slider_grade_blending.value() / 100.0,
            "grade_balance": self.slider_grade_balance.value() / 100.0,
            "tone_curve_enabled": bool(self.check_tone_curve_enabled.isChecked()),
            "tone_curve_preset": self._tone_curve_preset_key(),
            "tone_curve_channel": self._tone_curve_channel_key(),
            "tone_curve_black_point": self.slider_tone_curve_black.value() / 1000.0,
            "tone_curve_white_point": self.slider_tone_curve_white.value() / 1000.0,
            "tone_curve_points": luminance_points,
            "tone_curve_channel_points": channel_points,
            "tone_curve_channel_presets": dict(getattr(self, "_tone_curve_channel_presets", {})),
            "libraw": self._libraw_color_adjustment_state(),
        }

    def _libraw_color_adjustment_state(self) -> dict[str, Any]:
        if not hasattr(self, "check_libraw_auto_bright"):
            return self._default_libraw_color_adjustment_state()
        return {
            "white_balance_mode": str(self.combo_wb_mode.currentData() or "fixed"),
            "wb_multipliers": self._parse_wb_multipliers(self.edit_wb_multipliers.text(), [1.0, 1.0, 1.0, 1.0]),
            "auto_bright": bool(self.check_libraw_auto_bright.isChecked()),
            "auto_bright_thr": float(self.spin_libraw_auto_bright_thr.value()),
            "adjust_maximum_thr": float(self.spin_libraw_adjust_maximum_thr.value()),
            "bright": float(self.spin_libraw_bright.value()),
            "highlight_mode": str(self.combo_libraw_highlight_mode.currentData() or "clip"),
            "exp_shift": float(self.spin_libraw_exp_shift.value()),
            "exp_preserve_highlights": float(self.spin_libraw_exp_preserve_highlights.value()),
            "no_auto_scale": bool(self.check_libraw_no_auto_scale.isChecked()),
            "gamma_power": float(self.spin_libraw_gamma_power.value()),
            "gamma_slope": float(self.spin_libraw_gamma_slope.value()),
            "chromatic_aberration_red": float(self.spin_libraw_ca_red.value()),
            "chromatic_aberration_blue": float(self.spin_libraw_ca_blue.value()),
        }

    def _default_libraw_color_adjustment_state(self) -> dict[str, Any]:
        return {
            "white_balance_mode": "camera_metadata",
            "wb_multipliers": [1.0, 1.0, 1.0, 1.0],
            "auto_bright": False,
            "auto_bright_thr": 0.01,
            "adjust_maximum_thr": 0.75,
            "bright": 1.0,
            "highlight_mode": "clip",
            "exp_shift": 1.0,
            "exp_preserve_highlights": 0.0,
            "no_auto_scale": False,
            "gamma_power": 1.0,
            "gamma_slope": 1.0,
            "chromatic_aberration_red": 1.0,
            "chromatic_aberration_blue": 1.0,
        }

    def _render_adjustment_kwargs_from_state(self, state: dict[str, Any]) -> dict[str, Any]:
        return {
            "temperature_kelvin": float(state.get("temperature_kelvin", 5003.0)),
            "neutral_kelvin": 5003.0,
            "tint": float(state.get("tint", 0.0)),
            "brightness_ev": float(state.get("brightness_ev", 0.0)),
            "black_point": float(state.get("black_point", 0.0)),
            "white_point": float(max(float(state.get("black_point", 0.0)) + 0.001, float(state.get("white_point", 1.0)))),
            "contrast": float(state.get("contrast", 0.0)),
            "highlights": float(state.get("highlights", 0.0)),
            "shadows": float(state.get("shadows", 0.0)),
            "whites": float(state.get("whites", 0.0)),
            "blacks": float(state.get("blacks", 0.0)),
            "midtone": float(state.get("midtone", 1.0)),
            "vibrance": float(state.get("vibrance", 0.0)),
            "saturation": float(state.get("saturation", 0.0)),
            "grade_shadows_hue": float(state.get("grade_shadows_hue", 240.0)),
            "grade_shadows_saturation": float(state.get("grade_shadows_saturation", 0.0)),
            "grade_midtones_hue": float(state.get("grade_midtones_hue", 45.0)),
            "grade_midtones_saturation": float(state.get("grade_midtones_saturation", 0.0)),
            "grade_highlights_hue": float(state.get("grade_highlights_hue", 50.0)),
            "grade_highlights_saturation": float(state.get("grade_highlights_saturation", 0.0)),
            "grade_blending": float(state.get("grade_blending", 0.5)),
            "grade_balance": float(state.get("grade_balance", 0.0)),
            "tone_curve_points": state.get("tone_curve_points") if state.get("tone_curve_enabled") else None,
            "tone_curve_channel_points": state.get("tone_curve_channel_points") if state.get("tone_curve_enabled") else None,
            "tone_curve_black_point": float(state.get("tone_curve_black_point", 0.0)),
            "tone_curve_white_point": float(
                max(float(state.get("tone_curve_black_point", 0.0)) + 0.01, float(state.get("tone_curve_white_point", 1.0)))
            ),
        }

    def _render_adjustment_kwargs(self) -> dict[str, Any]:
        return self._render_adjustment_kwargs_from_state(self._render_adjustment_state())

    @staticmethod
    def _tone_curve_points_have_effect(points: Any) -> bool:
        if not points:
            return False
        normalized = normalize_tone_curve_points(
            [
                (p[0], p[1])
                for p in points
                if isinstance(p, (list, tuple)) and len(p) >= 2
            ]
        )
        if len(normalized) != 2:
            return True
        return any(
            abs(float(x) - float(y)) > 1e-4
            for x, y in normalized
        )

    def _render_adjustment_state_has_effect(self, state: dict[str, Any] | None = None) -> bool:
        if not isinstance(state, dict):
            state = self._render_adjustment_state()
        if abs(float(state.get("temperature_kelvin", 5003.0)) - 5003.0) > 0.5:
            return True
        if abs(float(state.get("tint", 0.0))) > 1e-4:
            return True
        if abs(float(state.get("brightness_ev", 0.0))) > 1e-4:
            return True
        if abs(float(state.get("black_point", 0.0))) > 1e-4:
            return True
        if abs(float(state.get("white_point", 1.0)) - 1.0) > 1e-4:
            return True
        if abs(float(state.get("contrast", 0.0))) > 1e-4:
            return True
        for key in ("highlights", "shadows", "whites", "blacks", "vibrance", "saturation"):
            if abs(float(state.get(key, 0.0))) > 1e-4:
                return True
        if abs(float(state.get("midtone", 1.0)) - 1.0) > 1e-4:
            return True
        for key in ("grade_shadows_saturation", "grade_midtones_saturation", "grade_highlights_saturation"):
            if abs(float(state.get(key, 0.0))) > 1e-4:
                return True
        if self._libraw_color_adjustment_state_has_effect(state.get("libraw")):
            return True
        if not bool(state.get("tone_curve_enabled", False)):
            return False
        if abs(float(state.get("tone_curve_black_point", 0.0))) > 1e-4:
            return True
        if abs(float(state.get("tone_curve_white_point", 1.0)) - 1.0) > 1e-4:
            return True
        channel_points = state.get("tone_curve_channel_points")
        if isinstance(channel_points, dict):
            return any(self._tone_curve_points_have_effect(channel_points.get(channel)) for channel in ("luminance", "red", "green", "blue"))
        return self._tone_curve_points_have_effect(state.get("tone_curve_points"))

    def _libraw_color_adjustment_state_has_effect(self, state: Any) -> bool:
        if not isinstance(state, dict):
            state = self._default_libraw_color_adjustment_state()
        default = self._default_libraw_color_adjustment_state()
        for key, baseline in default.items():
            current = state.get(key, baseline)
            if isinstance(baseline, bool):
                if bool(current) != baseline:
                    return True
                continue
            if isinstance(baseline, str):
                if str(current or "").strip().lower() != baseline:
                    return True
                continue
            if isinstance(baseline, list):
                try:
                    current_values = [float(v) for v in current]
                except Exception:
                    return True
                if len(current_values) != len(baseline):
                    return True
                if any(abs(a - float(b)) > 1e-4 for a, b in zip(current_values, baseline)):
                    return True
                continue
            try:
                if abs(float(current) - float(baseline)) > 1e-4:
                    return True
            except Exception:
                return True
        return False

    def _detail_adjustment_state(self) -> dict[str, Any]:
        return {
            "sharpen": int(self.slider_sharpen.value()),
            "radius": int(self.slider_radius.value()),
            "noise_luma": int(self.slider_noise_luma.value()),
            "noise_color": int(self.slider_noise_color.value()),
            "ca_red": int(self.slider_ca_red.value()),
            "ca_blue": int(self.slider_ca_blue.value()),
        }

    def _detail_adjustment_state_has_effect(self, state: dict[str, Any] | None = None) -> bool:
        if not isinstance(state, dict):
            state = self._detail_adjustment_state()
        default = self._default_detail_adjustment_state()
        for key, baseline in default.items():
            current = state.get(key, baseline)
            try:
                if abs(float(current) - float(baseline)) > 1e-4:
                    return True
            except Exception:
                if str(current) != str(baseline):
                    return True
        return False

    def _detail_adjustment_kwargs_from_state(self, state: dict[str, Any]) -> dict[str, float]:
        return {
            "denoise_luma": float(state.get("noise_luma", 0)) / 100.0,
            "denoise_color": float(state.get("noise_color", 0)) / 100.0,
            "sharpen_amount": float(state.get("sharpen", 0)) / 100.0,
            "sharpen_radius": float(state.get("radius", 10)) / 10.0,
            "lateral_ca_red_scale": 1.0 + float(state.get("ca_red", 0)) / 10000.0,
            "lateral_ca_blue_scale": 1.0 + float(state.get("ca_blue", 0)) / 10000.0,
        }

    def _apply_detail_adjustment_state(self, state: dict[str, Any]) -> None:
        self.slider_sharpen.setValue(int(state.get("sharpen", self.slider_sharpen.value())))
        self.slider_radius.setValue(int(state.get("radius", self.slider_radius.value())))
        self.slider_noise_luma.setValue(int(state.get("noise_luma", self.slider_noise_luma.value())))
        self.slider_noise_color.setValue(int(state.get("noise_color", self.slider_noise_color.value())))
        self.slider_ca_red.setValue(int(state.get("ca_red", self.slider_ca_red.value())))
        self.slider_ca_blue.setValue(int(state.get("ca_blue", self.slider_ca_blue.value())))

    def _apply_render_adjustment_state(self, state: dict[str, Any]) -> None:
        self._set_combo_text(
            self.combo_illuminant_render,
            str(state.get("illuminant") or "D50"),
        )
        self.spin_render_temperature.setValue(int(state.get("temperature_kelvin", 5003)))
        self.spin_render_tint.setValue(float(state.get("tint", 0.0)))
        self.slider_brightness.setValue(int(round(float(state.get("brightness_ev", 0.0)) * 100)))
        self.slider_black_point.setValue(int(round(float(state.get("black_point", 0.0)) * 1000)))
        self.slider_white_point.setValue(int(round(float(state.get("white_point", 1.0)) * 1000)))
        self.slider_contrast.setValue(int(round(float(state.get("contrast", 0.0)) * 100)))
        self.slider_highlights.setValue(int(round(float(state.get("highlights", 0.0)) * 100)))
        self.slider_shadows.setValue(int(round(float(state.get("shadows", 0.0)) * 100)))
        self.slider_whites.setValue(int(round(float(state.get("whites", 0.0)) * 100)))
        self.slider_blacks.setValue(int(round(float(state.get("blacks", 0.0)) * 100)))
        self.slider_midtone.setValue(int(round(float(state.get("midtone", 1.0)) * 100)))
        self.slider_vibrance.setValue(int(round(float(state.get("vibrance", 0.0)) * 100)))
        self.slider_saturation.setValue(int(round(float(state.get("saturation", 0.0)) * 100)))
        self.slider_grade_shadows_hue.setValue(int(round(float(state.get("grade_shadows_hue", 240.0)))))
        self.slider_grade_shadows_sat.setValue(int(round(float(state.get("grade_shadows_saturation", 0.0)) * 100)))
        self.slider_grade_midtones_hue.setValue(int(round(float(state.get("grade_midtones_hue", 45.0)))))
        self.slider_grade_midtones_sat.setValue(int(round(float(state.get("grade_midtones_saturation", 0.0)) * 100)))
        self.slider_grade_highlights_hue.setValue(int(round(float(state.get("grade_highlights_hue", 50.0)))))
        self.slider_grade_highlights_sat.setValue(int(round(float(state.get("grade_highlights_saturation", 0.0)) * 100)))
        self.slider_grade_blending.setValue(int(round(float(state.get("grade_blending", 0.5)) * 100)))
        self.slider_grade_balance.setValue(int(round(float(state.get("grade_balance", 0.0)) * 100)))
        if isinstance(state.get("libraw"), dict):
            self._apply_libraw_color_adjustment_state(state.get("libraw"))
        curve_enabled = bool(state.get("tone_curve_enabled", False))
        curve_preset = str(state.get("tone_curve_preset") or "linear")
        curve_points = self._coerce_tone_curve_points(state.get("tone_curve_points"))
        channel_points = self._coerce_tone_curve_channel_points(state.get("tone_curve_channel_points"))
        if curve_points is not None and "luminance" not in channel_points:
            channel_points["luminance"] = curve_points
        if not channel_points:
            channel_points["luminance"] = self._tone_curve_preset_points(curve_preset)
        presets = state.get("tone_curve_channel_presets")
        self._ensure_tone_curve_channel_state()
        for channel, points in channel_points.items():
            self._tone_curve_channel_points[channel] = points
        if isinstance(presets, dict):
            for channel in ("luminance", "red", "green", "blue"):
                preset = str(presets.get(channel) or "")
                if preset:
                    self._tone_curve_channel_presets[channel] = preset
        self._tone_curve_channel_presets["luminance"] = str(
            self._tone_curve_channel_presets.get("luminance") or curve_preset
        )
        active_channel = str(state.get("tone_curve_channel") or "luminance")
        if active_channel not in {"luminance", "red", "green", "blue"}:
            active_channel = "luminance"
        curve_black = float(state.get("tone_curve_black_point", 0.0))
        curve_white = float(state.get("tone_curve_white_point", 1.0))
        self.combo_tone_curve_channel.blockSignals(True)
        self._set_combo_data(self.combo_tone_curve_channel, active_channel)
        self.combo_tone_curve_channel.blockSignals(False)
        self._tone_curve_active_channel = active_channel
        self.combo_tone_curve_preset.blockSignals(True)
        self._set_combo_data(self.combo_tone_curve_preset, self._tone_curve_channel_presets.get(active_channel, curve_preset))
        self.combo_tone_curve_preset.blockSignals(False)
        self._set_tone_curve_range_controls(curve_black, curve_white)
        if hasattr(self.tone_curve_editor, "set_active_channel"):
            self.tone_curve_editor.set_active_channel(active_channel)
        self.tone_curve_editor.set_points(
            self._tone_curve_channel_points.get(active_channel)
            or curve_points
            or self._tone_curve_preset_points(curve_preset),
            emit=False,
        )
        if hasattr(self, "_sync_tone_curve_editor_channel_overlay"):
            self._sync_tone_curve_editor_channel_overlay()
        self.check_tone_curve_enabled.setChecked(curve_enabled)
        self._set_tone_curve_controls_enabled(curve_enabled)

    def _apply_libraw_color_adjustment_state(self, state: Any) -> None:
        if not hasattr(self, "check_libraw_auto_bright"):
            return
        if not isinstance(state, dict):
            state = self._default_libraw_color_adjustment_state()
        self._set_combo_data(self.combo_wb_mode, str(state.get("white_balance_mode", "fixed")))
        wb = state.get("wb_multipliers", [1.0, 1.0, 1.0, 1.0])
        if isinstance(wb, (list, tuple)):
            self.edit_wb_multipliers.setText(",".join(f"{float(v):.6g}" for v in wb))
        self.check_libraw_auto_bright.setChecked(bool(state.get("auto_bright", False)))
        self.spin_libraw_auto_bright_thr.setValue(float(state.get("auto_bright_thr", 0.01)))
        self.spin_libraw_adjust_maximum_thr.setValue(float(state.get("adjust_maximum_thr", 0.75)))
        self.spin_libraw_bright.setValue(float(state.get("bright", 1.0)))
        self._set_combo_data(self.combo_libraw_highlight_mode, str(state.get("highlight_mode", "clip")))
        self.spin_libraw_exp_shift.setValue(float(state.get("exp_shift", 1.0)))
        self.spin_libraw_exp_preserve_highlights.setValue(float(state.get("exp_preserve_highlights", 0.0)))
        self.check_libraw_no_auto_scale.setChecked(bool(state.get("no_auto_scale", False)))
        self.spin_libraw_gamma_power.setValue(float(state.get("gamma_power", 1.0)))
        self.spin_libraw_gamma_slope.setValue(float(state.get("gamma_slope", 1.0)))
        self.spin_libraw_ca_red.setValue(float(state.get("chromatic_aberration_red", 1.0)))
        self.spin_libraw_ca_blue.setValue(float(state.get("chromatic_aberration_blue", 1.0)))

    def _ca_scale_factors(self) -> tuple[float, float]:
        return 1.0 + self.slider_ca_red.value() / 10000.0, 1.0 + self.slider_ca_blue.value() / 10000.0

    def _selected_tiff_compression(self) -> str:
        combo = getattr(self, "combo_tiff_compression", None)
        if combo is None:
            return "none"
        return str(combo.currentData() or "none")

    def _selected_tiff_maxworkers(self) -> int | None:
        spin = getattr(self, "spin_tiff_maxworkers", None)
        if spin is None:
            return None
        value = int(spin.value())
        return value if value > 0 else None

    def _apply_output_adjustments(
        self,
        image: np.ndarray,
        *,
        denoise_luma: float,
        denoise_color: float,
        sharpen_amount: float,
        sharpen_radius: float,
        lateral_ca_red_scale: float,
        lateral_ca_blue_scale: float,
        render_adjustments: dict[str, Any],
    ) -> np.ndarray:
        adjusted = apply_adjustments(
            image,
            denoise_luminance=denoise_luma,
            denoise_color=denoise_color,
            sharpen_amount=sharpen_amount,
            sharpen_radius=sharpen_radius,
            lateral_ca_red_scale=lateral_ca_red_scale,
            lateral_ca_blue_scale=lateral_ca_blue_scale,
        )
        adjusted = apply_render_adjustments(adjusted, **render_adjustments)
        return self._apply_output_geometry_adjustments(adjusted)

    def _output_geometry_adjustment_state(self, image: np.ndarray | None = None) -> dict[str, Any]:
        crop_rect = self._export_crop_rect_for_image(image) if image is not None else getattr(self, "_image_crop_rect", None)
        rotation = float(getattr(self, "_viewer_rotation", 0.0) or 0.0) % 360.0
        signed_rotation = ((rotation + 180.0) % 360.0) - 180.0
        return {
            "crop_rect": list(crop_rect) if crop_rect is not None else None,
            "crop_normalized": list(getattr(self, "_image_crop_normalized_rect", None) or []) or None,
            "rotation_degrees": float(signed_rotation),
        }

    def _output_geometry_adjustment_state_has_effect(self, state: dict[str, Any] | None = None) -> bool:
        if not isinstance(state, dict):
            state = self._output_geometry_adjustment_state()
        if state.get("crop_rect") is not None or state.get("crop_normalized") is not None:
            return True
        try:
            rotation = float(state.get("rotation_degrees", 0.0) or 0.0)
        except Exception:
            return False
        signed_rotation = ((rotation + 180.0) % 360.0) - 180.0
        return abs(float(signed_rotation)) > 1e-4

    def _apply_output_geometry_adjustments(self, image: np.ndarray) -> np.ndarray:
        array = np.asarray(image, dtype=np.float32)
        crop_rect = self._export_crop_rect_for_image(array)
        if crop_rect is not None:
            x, y, w, h = crop_rect
            array = np.ascontiguousarray(array[y : y + h, x : x + w, :3])
        rotation = float(getattr(self, "_viewer_rotation", 0.0) or 0.0) % 360.0
        signed_rotation = ((rotation + 180.0) % 360.0) - 180.0
        if abs(signed_rotation) <= 1e-6:
            return np.clip(array, 0.0, 1.0).astype(np.float32, copy=False)
        return self._rotate_output_image(array, signed_rotation)

    def _export_crop_rect_for_image(self, image: np.ndarray | None) -> tuple[int, int, int, int] | None:
        if image is None:
            return None
        array = np.asarray(image)
        if array.ndim < 2:
            return None
        image_h, image_w = int(array.shape[0]), int(array.shape[1])
        if image_w <= 0 or image_h <= 0:
            return None
        normalized = getattr(self, "_image_crop_normalized_rect", None)
        if isinstance(normalized, (list, tuple)) and len(normalized) >= 4:
            nx, ny, nw, nh = (float(v) for v in normalized[:4])
            x0 = int(np.floor(nx * image_w))
            y0 = int(np.floor(ny * image_h))
            x1 = int(np.ceil((nx + nw) * image_w))
            y1 = int(np.ceil((ny + nh) * image_h))
        else:
            rect = getattr(self, "_image_crop_rect", None)
            if not (isinstance(rect, (list, tuple)) and len(rect) >= 4):
                return None
            x, y, w, h = (float(v) for v in rect[:4])
            x0 = int(np.floor(x))
            y0 = int(np.floor(y))
            x1 = int(np.ceil(x + w))
            y1 = int(np.ceil(y + h))
        x0 = max(0, min(image_w - 1, x0))
        y0 = max(0, min(image_h - 1, y0))
        x1 = max(x0 + 1, min(image_w, x1))
        y1 = max(y0 + 1, min(image_h, y1))
        if x0 == 0 and y0 == 0 and x1 == image_w and y1 == image_h:
            return None
        return x0, y0, x1 - x0, y1 - y0

    def _rotate_output_image(self, image: np.ndarray, rotation_degrees: float) -> np.ndarray:
        rgb = np.asarray(image, dtype=np.float32)
        if rgb.ndim != 3 or rgb.shape[2] < 3:
            return np.clip(rgb, 0.0, 1.0).astype(np.float32, copy=False)
        h, w = int(rgb.shape[0]), int(rgb.shape[1])
        if h <= 0 or w <= 0:
            return np.clip(rgb, 0.0, 1.0).astype(np.float32, copy=False)
        center = (w / 2.0, h / 2.0)
        matrix = cv2.getRotationMatrix2D(center, float(rotation_degrees), 1.0)
        cos_v = abs(float(matrix[0, 0]))
        sin_v = abs(float(matrix[0, 1]))
        new_w = max(1, int(round(h * sin_v + w * cos_v)))
        new_h = max(1, int(round(h * cos_v + w * sin_v)))
        matrix[0, 2] += new_w / 2.0 - center[0]
        matrix[1, 2] += new_h / 2.0 - center[1]
        rotated = cv2.warpAffine(
            np.ascontiguousarray(rgb[..., :3]),
            matrix,
            (new_w, new_h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0.0, 0.0, 0.0),
        )
        crop = self._valid_rotated_output_crop_rect(w, h, float(rotation_degrees), new_w, new_h)
        if crop is not None:
            x, y, cw, ch = crop
            rotated = rotated[y : y + ch, x : x + cw, :]
        return np.ascontiguousarray(np.clip(rotated, 0.0, 1.0).astype(np.float32, copy=False))

    def _valid_rotated_output_crop_rect(
        self,
        width: int,
        height: int,
        rotation_degrees: float,
        output_width: int,
        output_height: int,
    ) -> tuple[int, int, int, int] | None:
        crop_w, crop_h = self._largest_rotated_rect_without_borders(
            float(width),
            float(height),
            math.radians(float(rotation_degrees)),
        )
        angle_mod = abs(((float(rotation_degrees) + 45.0) % 90.0) - 45.0)
        safety_margin = 0 if angle_mod <= 1e-6 else 2
        crop_w = int(np.floor(min(float(output_width), max(1.0, crop_w)))) - safety_margin
        crop_h = int(np.floor(min(float(output_height), max(1.0, crop_h)))) - safety_margin
        if crop_w <= 0 or crop_h <= 0:
            return None
        x0 = max(0, int(round((int(output_width) - crop_w) / 2.0)))
        y0 = max(0, int(round((int(output_height) - crop_h) / 2.0)))
        crop_w = min(crop_w, int(output_width) - x0)
        crop_h = min(crop_h, int(output_height) - y0)
        if crop_w <= 0 or crop_h <= 0:
            return None
        return x0, y0, crop_w, crop_h

    @staticmethod
    def _largest_rotated_rect_without_borders(width: float, height: float, angle_radians: float) -> tuple[float, float]:
        if width <= 0.0 or height <= 0.0:
            return 0.0, 0.0
        sin_a = abs(math.sin(angle_radians))
        cos_a = abs(math.cos(angle_radians))
        if sin_a <= 1e-12:
            return width, height
        if cos_a <= 1e-12:
            return height, width

        width_is_longer = width >= height
        side_long = width if width_is_longer else height
        side_short = height if width_is_longer else width

        if side_short <= 2.0 * sin_a * cos_a * side_long or abs(sin_a - cos_a) < 1e-12:
            x = 0.5 * side_short
            if width_is_longer:
                return x / sin_a, x / cos_a
            return x / cos_a, x / sin_a

        cos_2a = cos_a * cos_a - sin_a * sin_a
        if abs(cos_2a) <= 1e-12:
            side = side_short / math.sqrt(2.0)
            return side, side
        return (
            (width * cos_a - height * sin_a) / cos_2a,
            (height * cos_a - width * sin_a) / cos_2a,
        )

    def _detail_cache_key(
        self,
        *,
        denoise_luma: float,
        denoise_color: float,
        sharpen_amount: float,
        sharpen_radius: float,
        lateral_ca_red_scale: float,
        lateral_ca_blue_scale: float,
    ) -> str:
        source_key = self._last_loaded_preview_key or str(id(self._original_linear))
        return "|".join(
            [
                source_key,
                f"nl={denoise_luma:.5f}",
                f"nc={denoise_color:.5f}",
                f"sh={sharpen_amount:.5f}",
                f"sr={sharpen_radius:.5f}",
                f"cr={lateral_ca_red_scale:.7f}",
                f"cb={lateral_ca_blue_scale:.7f}",
            ]
        )

    def _detail_adjusted_preview(
        self,
        image: np.ndarray,
        *,
        denoise_luma: float,
        denoise_color: float,
        sharpen_amount: float,
        sharpen_radius: float,
        lateral_ca_red_scale: float,
        lateral_ca_blue_scale: float,
    ) -> np.ndarray:
        key = self._detail_cache_key(
            denoise_luma=denoise_luma,
            denoise_color=denoise_color,
            sharpen_amount=sharpen_amount,
            sharpen_radius=sharpen_radius,
            lateral_ca_red_scale=lateral_ca_red_scale,
            lateral_ca_blue_scale=lateral_ca_blue_scale,
        )
        key = f"{key}|shape={tuple(np.asarray(image).shape)}"
        if self._detail_adjustment_cache_key == key and self._detail_adjusted_linear is not None:
            return self._detail_adjusted_linear

        adjusted = apply_adjustments(
            image,
            denoise_luminance=denoise_luma,
            denoise_color=denoise_color,
            sharpen_amount=sharpen_amount,
            sharpen_radius=sharpen_radius,
            lateral_ca_red_scale=lateral_ca_red_scale,
            lateral_ca_blue_scale=lateral_ca_blue_scale,
        )
        self._detail_adjusted_linear = adjusted
        self._detail_adjustment_cache_key = key
        return adjusted

    def _original_srgb_preview(self) -> np.ndarray:
        source_key = self._last_loaded_preview_key or str(id(self._original_linear))
        if self._original_srgb_cache_key == source_key and self._original_srgb_cache is not None:
            return self._original_srgb_cache
        if self._original_linear is None:
            raise RuntimeError("No hay imagen original cargada para la vista previa.")
        srgb = linear_to_srgb_display(self._original_linear)
        self._original_srgb_cache = srgb
        self._original_srgb_cache_key = source_key
        return srgb

    def _display_profile_stamp(self) -> str:
        profile_path = self._active_display_profile_path()
        if profile_path is None:
            return "none"
        try:
            resolved = profile_path.expanduser().resolve()
            st = resolved.stat()
            return f"{resolved}|{st.st_mtime_ns}|{st.st_size}"
        except OSError:
            return str(profile_path)

    def _original_display_u8_preview(self, *, bypass_profile: bool) -> np.ndarray:
        source_key = self._last_loaded_preview_key or str(id(self._original_linear))
        key = f"{source_key}|{self._display_profile_stamp()}|bypass={int(bool(bypass_profile))}"
        if self._original_display_u8_cache_key == key and self._original_display_u8_cache is not None:
            return self._original_display_u8_cache
        srgb = self._original_srgb_preview()
        u8 = self._display_u8_for_screen(srgb, bypass_profile=bypass_profile)
        self._original_display_u8_cache = u8
        self._original_display_u8_cache_key = key
        return u8

    def _clear_adjustment_caches(self) -> None:
        self._detail_adjusted_linear = None
        self._detail_adjustment_cache_key = None
        self._adjusted_linear_signature = None
        self._original_srgb_cache = None
        self._original_srgb_cache_key = None
        self._original_display_u8_cache = None
        self._original_display_u8_cache_key = None
        self._original_compare_panel_key = None
        self._interactive_source_cache_key = None
        self._interactive_source_cache_image = None
        self._interactive_source_cache_images = {}

    def _add_path_row(
        self,
        grid: QtWidgets.QGridLayout,
        row: int,
        label_text: str,
        line_edit: QtWidgets.QLineEdit,
        *,
        file_mode: bool,
        save_mode: bool,
        dir_mode: bool,
    ) -> tuple[QtWidgets.QWidget, QtWidgets.QWidget, QtWidgets.QWidget]:
        label = QtWidgets.QLabel(label_text)
        grid.addWidget(label, row, 0)
        grid.addWidget(line_edit, row, 1)
        browse = QtWidgets.QPushButton(self.tr("..."))
        browse.setMaximumWidth(36)
        browse.clicked.connect(
            lambda: self._browse_for_path(
                target=line_edit,
                file_mode=file_mode,
                save_mode=save_mode,
                dir_mode=dir_mode,
            )
        )
        grid.addWidget(browse, row, 2)
        return label, line_edit, browse

    def _hide_row_widgets(self, widgets: tuple[QtWidgets.QWidget, ...]) -> None:
        for widget in widgets:
            widget.hide()

    def _browse_for_path(self, target, *, file_mode: bool, save_mode: bool, dir_mode: bool) -> None:
        start = target.text().strip() or str(self._current_dir)
        if dir_mode:
            path = QtWidgets.QFileDialog.getExistingDirectory(self, self.tr("Selecciona directorio"), start)
            if path:
                target.setText(path)
                target.editingFinished.emit()
            return
        if save_mode:
            path, _ = QtWidgets.QFileDialog.getSaveFileName(self, self.tr("Guardar como"), start)
            if path:
                target.setText(path)
                target.editingFinished.emit()
            return
        if file_mode:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(self, self.tr("Selecciona archivo"), start)
            if path:
                target.setText(path)
                target.editingFinished.emit()

    def _detect_display_profile(self) -> None:
        detected = detect_system_display_profile()
        if detected is None:
            QtWidgets.QMessageBox.information(
                self,
                self.tr("Info"),
                self.tr("No se pudo detectar automaticamente el perfil ICC del monitor. Seleccionalo manualmente."),
            )
            return
        self.path_display_profile.setText(str(detected))
        self.check_display_color_management.setChecked(True)
        self._on_display_color_settings_changed()

    def _ensure_display_profile_if_enabled(self) -> None:
        if not hasattr(self, "check_display_color_management") or not hasattr(self, "path_display_profile"):
            return
        if not self.check_display_color_management.isChecked():
            return
        if self.path_display_profile.text().strip():
            return
        detected = detect_system_display_profile()
        if detected is not None:
            self.path_display_profile.setText(str(detected))

    def _on_display_color_settings_changed(self, *_args) -> None:
        if not hasattr(self, "check_display_color_management"):
            return
        self._ensure_display_profile_if_enabled()

        self._invalidate_active_display_profile_cache()
        self._settings.setValue(
            "display/color_management_enabled",
            bool(self.check_display_color_management.isChecked()),
        )
        if hasattr(self, "check_manual_profile_override"):
            self._settings.setValue(
                "display/manual_override_enabled",
                bool(self.check_manual_profile_override.isChecked()),
            )
        self._settings.setValue("display/monitor_profile", self.path_display_profile.text().strip())
        self._display_color_error_key = None
        self._image_thumb_cache.clear()
        self._original_display_u8_cache = None
        self._original_display_u8_cache_key = None
        self._original_compare_panel_key = None
        self._update_display_profile_status()
        if self._preview_srgb is not None and self._original_linear is not None:
            self._refresh_preview()
        if hasattr(self, "file_list"):
            self._queue_thumbnail_generation(self._file_list_paths(), delay_ms=0)

    def _invalidate_active_display_profile_cache(self) -> None:
        self._active_display_profile_cached_key = None
        self._active_display_profile_cache_value = None

    def _display_screen_cache_key(self) -> str:
        try:
            screen = self.screen() if callable(getattr(self, "screen", None)) else None
            if screen is None:
                screen = QtWidgets.QApplication.primaryScreen()
            if screen is None:
                return "screen:none"
            geometry = screen.geometry()
            parts = [
                str(screen.name() if hasattr(screen, "name") else ""),
                str(geometry.x()),
                str(geometry.y()),
                str(geometry.width()),
                str(geometry.height()),
                f"{float(screen.devicePixelRatio()):.4f}" if hasattr(screen, "devicePixelRatio") else "",
            ]
            return "|".join(parts)
        except Exception:
            return "screen:unknown"

    def _active_display_profile_cache_key(self) -> tuple[object, ...]:
        manual_enabled = bool(
            hasattr(self, "check_manual_profile_override")
            and self.check_manual_profile_override.isChecked()
        )
        manual_text = self.path_display_profile.text().strip() if hasattr(self, "path_display_profile") else ""
        return (manual_enabled, manual_text, self._display_screen_cache_key())

    def _monitor_profile_from_qt(self) -> Path | None:
        """Obtiene el ICC del monitor activo via Qt (Windows ICM, macOS ColorSync, Wayland CM).

        Usa QScreen::colorSpace().iccProfile(), que el SO provee a Qt automaticamente.
        El ICC en bytes se escribe a disco para que LittleCMS pueda abrirlo.
        """
        try:
            screen = self.screen() if callable(getattr(self, "screen", None)) else None
            if screen is None:
                screen = QtWidgets.QApplication.primaryScreen()
            if screen is None:
                return None
            color_space = getattr(screen, "colorSpace", None)
            if not callable(color_space):
                return None
            cs = color_space()
            if not cs.isValid():
                return None
            icc_bytes = bytes(cs.iccProfile())
            if len(icc_bytes) < 128:
                return None
            return cache_display_profile_bytes(icc_bytes, prefix="qt-screen")
        except Exception:
            return None

    def _active_display_profile_path(self) -> Path | None:
        """Devuelve la ruta ICC del monitor para la conversion LittleCMS (source ICC -> monitor ICC).

        Prioridad:
        1. Override manual explicitamente activado por el usuario.
        2. Perfil ICC del monitor obtenido via Qt (Windows ICM, macOS ColorSync, Wayland).
        3. Deteccion especifica de plataforma (ctypes/GDI32, CoreGraphics, colord).
        4. None: sin perfil - la conversion LittleCMS destina a sRGB (fallback visual).
        """
        cache_key = self._active_display_profile_cache_key()
        if getattr(self, "_active_display_profile_cached_key", None) == cache_key:
            return getattr(self, "_active_display_profile_cache_value", None)
        profile_path = self._resolve_active_display_profile_path()
        self._active_display_profile_cached_key = cache_key
        self._active_display_profile_cache_value = profile_path
        return profile_path

    def _resolve_active_display_profile_path(self) -> Path | None:
        if self._manual_override_active():
            if not hasattr(self, "path_display_profile"):
                return None
            text = self.path_display_profile.text().strip()
            return Path(text).expanduser() if text else None
        from_qt = self._monitor_profile_from_qt()
        if from_qt is not None:
            return from_qt
        return detect_system_display_profile()

    def _manual_override_active(self) -> bool:
        if not hasattr(self, "check_manual_profile_override"):
            return False
        if not self.check_manual_profile_override.isChecked():
            return False
        if not hasattr(self, "path_display_profile"):
            return False
        text = self.path_display_profile.text().strip()
        return bool(text and Path(text).expanduser().exists())

    def _display_panel_color_space(self, *, bypass_profile: bool = False) -> str:
        if bypass_profile:
            return "srgb"
        return "device" if self._active_display_profile_path() is not None else "srgb"

    def _display_u8_for_screen(self, image_srgb: np.ndarray, *, bypass_profile: bool = False) -> np.ndarray:
        if bypass_profile:
            return srgb_to_display_u8(image_srgb, None)
        profile_path = self._active_display_profile_path()
        try:
            return srgb_to_display_u8(image_srgb, profile_path)
        except Exception as exc:
            key = f"{profile_path}|{exc}"
            if self._display_color_error_key != key:
                self._display_color_error_key = key
                self._log_preview(f"Error: gestion ICC de monitor no disponible; no se actualiza la vista: {exc}")
                self._update_display_profile_status(error=str(exc))
            raise RuntimeError(f"Fallo de gestion ICC de monitor: {exc}") from exc

    def _profiled_display_u8_for_screen(
        self,
        image_rgb: np.ndarray,
        source_profile: Path,
        *,
        bypass_profile: bool = False,
    ) -> np.ndarray:
        monitor_profile = None if bypass_profile else self._active_display_profile_path()
        try:
            return profiled_float_to_display_u8(image_rgb, source_profile, monitor_profile)
        except Exception as exc:
            key = f"{source_profile}|{monitor_profile}|{exc}"
            if self._display_color_error_key != key:
                self._display_color_error_key = key
                self._log_preview(f"Error: conversion ICC directa a monitor no disponible; no se actualiza la vista: {exc}")
                self._update_display_profile_status(error=str(exc))
            raise RuntimeError(f"Fallo de conversion ICC directa a monitor: {exc}") from exc

    def _thumbnail_u8_for_screen(self, rgb_u8: np.ndarray) -> np.ndarray:
        profile_path = self._active_display_profile_path()
        try:
            return srgb_u8_to_display_u8(rgb_u8, profile_path)
        except Exception:
            return srgb_u8_to_display_u8(rgb_u8, None)

    def _set_preview_panel_image(
        self,
        panel: ImagePanel,
        image_srgb: np.ndarray,
        *,
        bypass_profile: bool = False,
    ) -> None:
        panel.set_rgb_u8_image(
            self._display_u8_for_screen(image_srgb, bypass_profile=bypass_profile),
            color_space=self._display_panel_color_space(bypass_profile=bypass_profile),
        )

    def _compare_view_active(self) -> bool:
        return bool(
            hasattr(self, "viewer_stack")
            and hasattr(self, "chk_compare")
            and self.chk_compare.isChecked()
            and int(self.viewer_stack.currentIndex()) == 1
        )

    def _set_result_display_u8(
        self,
        display_u8: np.ndarray,
        *,
        compare_enabled: bool,
        bypass_profile: bool = False,
        update_histogram: bool = True,
    ) -> None:
        colorimetric_u8 = self._preview_colorimetric_u8(display_u8)
        self._set_result_u8_pair(
            display_u8,
            colorimetric_u8,
            compare_enabled=compare_enabled,
            bypass_profile=bypass_profile,
            update_histogram=update_histogram,
        )

    def _set_result_u8_pair(
        self,
        display_u8: np.ndarray,
        colorimetric_u8: np.ndarray | None,
        *,
        compare_enabled: bool,
        bypass_profile: bool = False,
        update_histogram: bool = True,
    ) -> None:
        display_array = np.asarray(display_u8, dtype=np.uint8)
        colorimetric_array = None if colorimetric_u8 is None else np.asarray(colorimetric_u8, dtype=np.uint8)
        self._current_result_display_u8 = display_array.copy()
        self._current_result_colorimetric_u8 = None if colorimetric_array is None else colorimetric_array.copy()
        color_space = self._display_panel_color_space(bypass_profile=bypass_profile)
        if bool(compare_enabled and self._compare_view_active()):
            self.image_result_compare.set_rgb_u8_image(display_array, color_space=color_space)
            self._apply_clip_overlay_to_panel(self.image_result_compare, colorimetric_array)
        else:
            self.image_result_single.set_rgb_u8_image(display_array, color_space=color_space)
            self._apply_clip_overlay_to_panel(self.image_result_single, colorimetric_array)
        if bool(update_histogram):
            self._update_viewer_histogram(colorimetric_array)
        if hasattr(self, "_sync_mtf_roi_overlay"):
            self._sync_mtf_roi_overlay()
        if hasattr(self, "_sync_color_sample_overlay"):
            self._sync_color_sample_overlay()
        if hasattr(self, "_schedule_color_picker_samples_refresh"):
            self._schedule_color_picker_samples_refresh()
        if hasattr(self, "_sync_viewer_real_pixel_scale_if_requested"):
            self._sync_viewer_real_pixel_scale_if_requested()
        if hasattr(self, "_maybe_update_mtf_after_preview"):
            self._maybe_update_mtf_after_preview()

    def _apply_result_display_u8_region(
        self,
        display_u8: np.ndarray,
        preview_srgb: np.ndarray | None,
        rect: tuple[int, int, int, int],
        *,
        compare_enabled: bool,
        bypass_profile: bool,
    ) -> bool:
        if bool(compare_enabled and self._compare_view_active()):
            return False
        x, y, w, h = (int(v) for v in rect)
        if w <= 0 or h <= 0:
            return False
        current_display = getattr(self, "_current_result_display_u8", None)
        if current_display is None:
            return False
        current_display = np.asarray(current_display, dtype=np.uint8)
        if current_display.ndim != 3 or current_display.shape[2] < 3:
            return False
        if y + h > current_display.shape[0] or x + w > current_display.shape[1]:
            return False
        patch = np.asarray(display_u8, dtype=np.uint8)
        if patch.shape[0] != h or patch.shape[1] != w:
            return False

        current_display[y : y + h, x : x + w, :3] = patch[..., :3]
        self._current_result_display_u8 = current_display
        colorimetric_patch = None
        if preview_srgb is not None and getattr(self, "_preview_srgb", None) is not None:
            preview = np.asarray(self._preview_srgb, dtype=np.float32)
            crop_raw = np.asarray(preview_srgb)
            if crop_raw.dtype == np.uint8:
                colorimetric_patch = np.ascontiguousarray(crop_raw[..., :3].astype(np.uint8, copy=False))
                crop = colorimetric_patch.astype(np.float32) / np.float32(255.0)
            else:
                crop = np.asarray(crop_raw, dtype=np.float32)
            if preview.ndim == 3 and crop.shape[:2] == (h, w) and y + h <= preview.shape[0] and x + w <= preview.shape[1]:
                preview[y : y + h, x : x + w, :3] = crop[..., :3]
                self._preview_srgb = preview
                if colorimetric_patch is None:
                    colorimetric_patch = srgb_to_display_u8(crop, None)

        current_color = getattr(self, "_current_result_colorimetric_u8", None)
        if colorimetric_patch is not None and current_color is not None:
            current_color = np.asarray(current_color, dtype=np.uint8)
            if current_color.ndim == 3 and y + h <= current_color.shape[0] and x + w <= current_color.shape[1]:
                current_color[y : y + h, x : x + w, :3] = colorimetric_patch[..., :3]
                self._current_result_colorimetric_u8 = current_color

        self.image_result_single.update_rgb_u8_region(
            x,
            y,
            patch,
            color_space=self._display_panel_color_space(bypass_profile=bypass_profile),
        )
        if (
            colorimetric_patch is not None
            and bool(getattr(self, "check_image_clip_overlay", None) and self.check_image_clip_overlay.isChecked())
            and hasattr(self.image_result_single, "update_clip_overlay_classes_region")
        ):
            self.image_result_single.set_clip_overlay_enabled(True)
            self.image_result_single.update_clip_overlay_classes_region(
                x,
                y,
                self._clip_overlay_classes(colorimetric_patch),
            )
        if hasattr(self, "_sync_viewer_real_pixel_scale_if_requested"):
            self._sync_viewer_real_pixel_scale_if_requested()
        if hasattr(self, "_schedule_color_picker_samples_refresh"):
            self._schedule_color_picker_samples_refresh()
        return True

    def _ensure_original_compare_panel(self, *, bypass_profile: bool) -> None:
        if self._original_linear is None:
            return
        source_key = self._last_loaded_preview_key or str(id(self._original_linear))
        key = f"{source_key}|{self._display_profile_stamp()}|bp={int(bool(bypass_profile))}"
        if self._original_compare_panel_key == key:
            if bool(hasattr(self, "check_image_clip_overlay") and self.check_image_clip_overlay.isChecked()):
                self._apply_clip_overlay_to_panel(
                    self.image_original_compare,
                    self._original_display_u8_preview(bypass_profile=bypass_profile),
                )
            return
        original_display_u8 = self._original_display_u8_preview(bypass_profile=bypass_profile)
        self.image_original_compare.set_rgb_u8_image(
            original_display_u8,
            color_space=self._display_panel_color_space(bypass_profile=bypass_profile),
        )
        self._apply_clip_overlay_to_panel(self.image_original_compare, original_display_u8)
        self._original_compare_panel_key = key

    def _update_display_profile_status(self, *, error: str | None = None) -> None:
        if not hasattr(self, "display_profile_status"):
            return
        if error:
            self.display_profile_status.setText(self.tr("Monitor: error de perfil ICC; vista no actualizada"))
            return
        if self._manual_override_active():
            profile_path = self._active_display_profile_path()
            if profile_path is None or not profile_path.exists():
                self.display_profile_status.setText(self.tr("Monitor: perfil manual no encontrado"))
                return
            self.display_profile_status.setText(self.tr("Monitor: ICC manual -") + f" {display_profile_label(profile_path)}")
            return
        # Auto: intentar Qt, luego ctypes, luego fallback sRGB
        from_qt = self._monitor_profile_from_qt()
        if from_qt is not None:
            try:
                screen = self.screen() if callable(getattr(self, "screen", None)) else None
                if screen is None:
                    screen = QtWidgets.QApplication.primaryScreen()
                if screen is not None:
                    cs = screen.colorSpace()
                    if cs.isValid():
                        desc = cs.description().strip() if hasattr(cs, "description") else ""
                        label = desc or display_profile_label(from_qt)
                        self.display_profile_status.setText(self.tr("Monitor: SO (Qt) -") + f" {label}")
                        return
            except Exception:
                pass
            self.display_profile_status.setText(self.tr("Monitor: SO (Qt) -") + f" {display_profile_label(from_qt)}")
            return
        detected = detect_system_display_profile()
        if detected is not None:
            self.display_profile_status.setText(self.tr("Monitor: detectado -") + f" {display_profile_label(detected)}")
            return
        self.display_profile_status.setText(self.tr("Monitor: sin perfil ICC (respaldo visual sRGB)"))
