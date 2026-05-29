from __future__ import annotations

from ._imports import *  # noqa: F401,F403


class ControlPanelsMixin:
    def _build_named_adjustment_profile_panel(self, category: str, default_name: str) -> QtWidgets.QWidget:
        box = QtWidgets.QGroupBox(self.tr("Perfiles guardados"))
        grid = QtWidgets.QGridLayout(box)
        combo = QtWidgets.QComboBox()
        name_edit = QtWidgets.QLineEdit(default_name)
        status = QtWidgets.QLabel(self.tr("Sin perfiles guardados"))
        status.setWordWrap(True)
        status.setStyleSheet("font-size: 12px; color: #d8d8d8;")

        if category == "color_contrast":
            self.color_contrast_profile_combo = combo
            self.color_contrast_profile_name_edit = name_edit
            self.color_contrast_profile_status_label = status
        elif category == "detail":
            self.detail_profile_combo = combo
            self.detail_profile_name_edit = name_edit
            self.detail_profile_status_label = status
        elif category == "raw_export":
            self.raw_export_profile_combo = combo
            self.raw_export_profile_name_edit = name_edit
            self.raw_export_profile_status_label = status

        grid.addWidget(QtWidgets.QLabel(self.tr("Perfil")), 0, 0)
        grid.addWidget(combo, 0, 1, 1, 2)
        grid.addWidget(QtWidgets.QLabel(self.tr("Nombre")), 1, 0)
        grid.addWidget(name_edit, 1, 1, 1, 2)

        buttons = QtWidgets.QGridLayout()
        buttons.addWidget(self._button(self.tr("Guardar"), lambda _checked=False, c=category: self._save_named_adjustment_profile(c)), 0, 0)
        buttons.addWidget(self._button(self.tr("Aplicar a controles"), lambda _checked=False, c=category: self._activate_selected_named_adjustment_profile(c)), 0, 1)
        buttons.addWidget(self._button(self.tr("Aplicar a seleccion"), lambda _checked=False, c=category: self._apply_selected_named_adjustment_profile_to_selected(c)), 1, 0, 1, 2)
        buttons.addWidget(self._button(self.tr("Copiar de imagen"), lambda _checked=False, c=category: self._copy_named_adjustment_profile_from_selected(c)), 2, 0)
        buttons.addWidget(self._button(self.tr("Pegar a imagen"), lambda _checked=False, c=category: self._paste_named_adjustment_profile_to_selected(c)), 2, 1)
        grid.addLayout(buttons, 2, 0, 1, 3)
        grid.addWidget(status, 3, 0, 1, 3)
        combo.currentIndexChanged.connect(lambda _index, c=category: self._activate_selected_named_adjustment_profile(c))
        self._refresh_named_adjustment_profile_combo(category)
        return box

    def _build_tab_color_adjustments(self) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(tab)

        grid.addWidget(QtWidgets.QLabel(self.tr("Iluminante final")), 0, 0)
        self.combo_illuminant_render = QtWidgets.QComboBox()
        for label, temp, tint in ILLUMINANT_OPTIONS:
            self.combo_illuminant_render.addItem(self.tr(label), {"temperature": temp, "tint": tint})
        self.combo_illuminant_render.setCurrentIndex(1)
        self.combo_illuminant_render.currentIndexChanged.connect(self._on_illuminant_changed)
        grid.addWidget(self.combo_illuminant_render, 0, 1, 1, 2)

        grid.addWidget(QtWidgets.QLabel(self.tr("Temperatura (K)")), 1, 0)
        self.spin_render_temperature = QtWidgets.QSpinBox()
        self.spin_render_temperature.setRange(2000, 12000)
        self.spin_render_temperature.setSingleStep(50)
        self.spin_render_temperature.setValue(5003)
        self.spin_render_temperature.valueChanged.connect(lambda _v: self._on_render_control_change())
        grid.addWidget(self.spin_render_temperature, 1, 1, 1, 2)

        grid.addWidget(QtWidgets.QLabel(self.tr("Matiz")), 2, 0)
        self.spin_render_tint = QtWidgets.QDoubleSpinBox()
        self.spin_render_tint.setRange(-100.0, 100.0)
        self.spin_render_tint.setSingleStep(1.0)
        self.spin_render_tint.setDecimals(1)
        self.spin_render_tint.valueChanged.connect(lambda _v: self._on_render_control_change())
        grid.addWidget(self.spin_render_tint, 2, 1, 1, 2)

        neutral_row = QtWidgets.QHBoxLayout()
        self.btn_neutral_picker = QtWidgets.QPushButton(self.tr("Cuentagotas neutro"))
        self.btn_neutral_picker.setCheckable(True)
        self.btn_neutral_picker.clicked.connect(self._toggle_neutral_picker)
        neutral_row.addWidget(self.btn_neutral_picker)
        self.label_neutral_picker = QtWidgets.QLabel(self.tr("Punto neutro: sin muestra"))
        self.label_neutral_picker.setWordWrap(True)
        self.label_neutral_picker.setStyleSheet("font-size: 12px; color: #d4d4d4;")
        neutral_row.addWidget(self.label_neutral_picker, 1)
        grid.addLayout(neutral_row, 3, 0, 1, 3)

        self.slider_vibrance, self.label_vibrance = self._slider(
            minimum=-100,
            maximum=100,
            value=0,
            on_change=self._on_render_control_change,
            formatter=lambda v: self.tr("Intensidad") + f": {v:+d}",
        )
        grid.addWidget(self.label_vibrance, 4, 0, 1, 3)
        grid.addWidget(self.slider_vibrance, 5, 0, 1, 3)

        self.slider_saturation, self.label_saturation = self._slider(
            minimum=-100,
            maximum=100,
            value=0,
            on_change=self._on_render_control_change,
            formatter=lambda v: self.tr("Saturacion") + f": {v:+d}",
        )
        grid.addWidget(self.label_saturation, 6, 0, 1, 3)
        grid.addWidget(self.slider_saturation, 7, 0, 1, 3)

        grid.addWidget(self._button(self.tr("Restablecer color"), self._reset_color_adjustments), 8, 0, 1, 3)
        return tab

    def _build_tab_color_grading(self) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(tab)

        self.slider_grade_midtones_hue, self.label_grade_midtones_hue = self._slider(
            minimum=0,
            maximum=360,
            value=45,
            on_change=self._on_render_control_change,
            formatter=lambda v: self.tr("Medios tono") + f": {v} deg",
        )
        grid.addWidget(self.label_grade_midtones_hue, 0, 0, 1, 3)
        grid.addWidget(self.slider_grade_midtones_hue, 1, 0, 1, 3)
        self.slider_grade_midtones_sat, self.label_grade_midtones_sat = self._slider(
            minimum=-100,
            maximum=100,
            value=0,
            on_change=self._on_render_control_change,
            formatter=lambda v: self.tr("Medios saturacion") + f": {v:+d}",
        )
        grid.addWidget(self.label_grade_midtones_sat, 2, 0, 1, 3)
        grid.addWidget(self.slider_grade_midtones_sat, 3, 0, 1, 3)

        self.slider_grade_shadows_hue, self.label_grade_shadows_hue = self._slider(
            minimum=0,
            maximum=360,
            value=240,
            on_change=self._on_render_control_change,
            formatter=lambda v: self.tr("Sombras tono") + f": {v} deg",
        )
        grid.addWidget(self.label_grade_shadows_hue, 4, 0, 1, 3)
        grid.addWidget(self.slider_grade_shadows_hue, 5, 0, 1, 3)
        self.slider_grade_shadows_sat, self.label_grade_shadows_sat = self._slider(
            minimum=-100,
            maximum=100,
            value=0,
            on_change=self._on_render_control_change,
            formatter=lambda v: self.tr("Sombras saturacion") + f": {v:+d}",
        )
        grid.addWidget(self.label_grade_shadows_sat, 6, 0, 1, 3)
        grid.addWidget(self.slider_grade_shadows_sat, 7, 0, 1, 3)

        self.slider_grade_highlights_hue, self.label_grade_highlights_hue = self._slider(
            minimum=0,
            maximum=360,
            value=50,
            on_change=self._on_render_control_change,
            formatter=lambda v: self.tr("Iluminaciones tono") + f": {v} deg",
        )
        grid.addWidget(self.label_grade_highlights_hue, 8, 0, 1, 3)
        grid.addWidget(self.slider_grade_highlights_hue, 9, 0, 1, 3)
        self.slider_grade_highlights_sat, self.label_grade_highlights_sat = self._slider(
            minimum=-100,
            maximum=100,
            value=0,
            on_change=self._on_render_control_change,
            formatter=lambda v: self.tr("Iluminaciones saturacion") + f": {v:+d}",
        )
        grid.addWidget(self.label_grade_highlights_sat, 10, 0, 1, 3)
        grid.addWidget(self.slider_grade_highlights_sat, 11, 0, 1, 3)

        self.slider_grade_blending, self.label_grade_blending = self._slider(
            minimum=0,
            maximum=100,
            value=50,
            on_change=self._on_render_control_change,
            formatter=lambda v: self.tr("Fusion") + f": {v}",
        )
        grid.addWidget(self.label_grade_blending, 12, 0, 1, 3)
        grid.addWidget(self.slider_grade_blending, 13, 0, 1, 3)
        self.slider_grade_balance, self.label_grade_balance = self._slider(
            minimum=-100,
            maximum=100,
            value=0,
            on_change=self._on_render_control_change,
            formatter=lambda v: self.tr("Equilibrio") + f": {v:+d}",
        )
        grid.addWidget(self.label_grade_balance, 14, 0, 1, 3)
        grid.addWidget(self.slider_grade_balance, 15, 0, 1, 3)

        grid.addWidget(self._button(self.tr("Restablecer gradacion"), self._reset_color_grading), 16, 0, 1, 3)
        return tab

    def _build_tab_brightness_contrast(self) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(tab)

        self.slider_brightness, self.label_brightness = self._slider(
            minimum=-200,
            maximum=200,
            value=0,
            on_change=self._on_render_control_change,
            formatter=lambda v: self.tr("Exposicion") + f": {v / 100:+.2f} EV",
        )
        grid.addWidget(self.label_brightness, 0, 0, 1, 3)
        grid.addWidget(self.slider_brightness, 1, 0, 1, 3)

        self.slider_contrast, self.label_contrast = self._slider(
            minimum=-100,
            maximum=100,
            value=0,
            on_change=self._on_render_control_change,
            formatter=lambda v: self.tr("Contraste") + f": {v / 100:+.2f}",
        )
        grid.addWidget(self.label_contrast, 2, 0, 1, 3)
        grid.addWidget(self.slider_contrast, 3, 0, 1, 3)

        self.slider_highlights, self.label_highlights = self._slider(
            minimum=-100,
            maximum=100,
            value=0,
            on_change=self._on_render_control_change,
            formatter=lambda v: self.tr("Iluminaciones") + f": {v:+d}",
        )
        grid.addWidget(self.label_highlights, 4, 0, 1, 3)
        grid.addWidget(self.slider_highlights, 5, 0, 1, 3)

        self.slider_shadows, self.label_shadows = self._slider(
            minimum=-100,
            maximum=100,
            value=0,
            on_change=self._on_render_control_change,
            formatter=lambda v: self.tr("Sombras") + f": {v:+d}",
        )
        grid.addWidget(self.label_shadows, 6, 0, 1, 3)
        grid.addWidget(self.slider_shadows, 7, 0, 1, 3)

        self.slider_whites, self.label_whites = self._slider(
            minimum=-100,
            maximum=100,
            value=0,
            on_change=self._on_render_control_change,
            formatter=lambda v: self.tr("Blancos") + f": {v:+d}",
        )
        grid.addWidget(self.label_whites, 8, 0, 1, 3)
        grid.addWidget(self.slider_whites, 9, 0, 1, 3)

        self.slider_blacks, self.label_blacks = self._slider(
            minimum=-100,
            maximum=100,
            value=0,
            on_change=self._on_render_control_change,
            formatter=lambda v: self.tr("Negros") + f": {v:+d}",
        )
        grid.addWidget(self.label_blacks, 10, 0, 1, 3)
        grid.addWidget(self.slider_blacks, 11, 0, 1, 3)

        self.slider_black_point, self.label_black_point = self._slider(
            minimum=0,
            maximum=300,
            value=0,
            on_change=self._on_render_control_change,
            formatter=lambda v: self.tr("Recorte negro") + f": {v / 1000:.3f}",
        )
        grid.addWidget(self.label_black_point, 12, 0, 1, 3)
        grid.addWidget(self.slider_black_point, 13, 0, 1, 3)

        self.slider_white_point, self.label_white_point = self._slider(
            minimum=500,
            maximum=1000,
            value=1000,
            on_change=self._on_render_control_change,
            formatter=lambda v: self.tr("Recorte blanco") + f": {v / 1000:.3f}",
        )
        grid.addWidget(self.label_white_point, 14, 0, 1, 3)
        grid.addWidget(self.slider_white_point, 15, 0, 1, 3)

        self.slider_midtone, self.label_midtone = self._slider(
            minimum=50,
            maximum=200,
            value=100,
            on_change=self._on_render_control_change,
            formatter=lambda v: self.tr("Curva medios") + f": {v / 100:.2f}",
        )
        grid.addWidget(self.label_midtone, 16, 0, 1, 3)
        grid.addWidget(self.slider_midtone, 17, 0, 1, 3)

        self.check_tone_curve_enabled = QtWidgets.QCheckBox(self.tr("Curva tonal avanzada"))
        self.check_tone_curve_enabled.setChecked(False)
        self.check_tone_curve_enabled.toggled.connect(self._on_tone_curve_enabled_changed)
        grid.addWidget(self.check_tone_curve_enabled, 18, 0, 1, 3)

        self.combo_tone_curve_channel = QtWidgets.QComboBox()
        for label, key in (
            (self.tr("Luminosidad"), "luminance"),
            (self.tr("Rojo"), "red"),
            (self.tr("Verde"), "green"),
            (self.tr("Azul"), "blue"),
        ):
            self.combo_tone_curve_channel.addItem(label, key)
        self.combo_tone_curve_channel.currentIndexChanged.connect(self._on_tone_curve_channel_changed)
        grid.addWidget(self.combo_tone_curve_channel, 19, 1, 1, 2)

        grid.addWidget(QtWidgets.QLabel(self.tr("Canal curva")), 19, 0)
        grid.addWidget(QtWidgets.QLabel(self.tr("Preset curva")), 20, 0)
        self.combo_tone_curve_preset = QtWidgets.QComboBox()
        for label, key, _points in TONE_CURVE_PRESETS:
            self.combo_tone_curve_preset.addItem(self.tr(label), key)
        self.combo_tone_curve_preset.currentIndexChanged.connect(self._on_tone_curve_preset_changed)
        grid.addWidget(self.combo_tone_curve_preset, 20, 1, 1, 2)

        self.slider_tone_curve_black, self.label_tone_curve_black = self._slider(
            minimum=0,
            maximum=950,
            value=0,
            on_change=self._on_tone_curve_range_changed,
            formatter=lambda v: self.tr("Negro curva") + f": {v / 1000:.3f}",
        )
        grid.addWidget(self.label_tone_curve_black, 21, 0, 1, 3)
        grid.addWidget(self.slider_tone_curve_black, 22, 0, 1, 3)

        self.slider_tone_curve_white, self.label_tone_curve_white = self._slider(
            minimum=50,
            maximum=1000,
            value=1000,
            on_change=self._on_tone_curve_range_changed,
            formatter=lambda v: self.tr("Blanco curva") + f": {v / 1000:.3f}",
        )
        grid.addWidget(self.label_tone_curve_white, 23, 0, 1, 3)
        grid.addWidget(self.slider_tone_curve_white, 24, 0, 1, 3)

        self.tone_curve_editor = ToneCurveEditor()
        self.tone_curve_editor.pointsChanged.connect(self._on_tone_curve_points_changed)
        self.tone_curve_editor.interactionFinished.connect(self._on_tone_curve_interaction_finished)
        grid.addWidget(self.tone_curve_editor, 25, 0, 1, 3)
        grid.addWidget(self._button(self.tr("Restablecer curva"), self._reset_tone_curve), 26, 0, 1, 3)
        self._set_tone_curve_controls_enabled(False)

        grid.addWidget(self._button(self.tr("Restablecer tono"), self._reset_tone_adjustments), 27, 0, 1, 3)
        grid.addWidget(
            self._build_named_adjustment_profile_panel("color_contrast", self.tr("Color y contraste")),
            28,
            0,
            1,
            3,
        )
        return tab

    def _build_tab_libraw_color_settings(self) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(tab)

        self.check_libraw_auto_bright = QtWidgets.QCheckBox(self.tr("Ajuste automatico de brillo RAW"))
        self.check_libraw_auto_bright.toggled.connect(lambda _checked: self._on_raw_decode_control_changed())
        grid.addWidget(self.check_libraw_auto_bright, 0, 0, 1, 3)

        grid.addWidget(QtWidgets.QLabel(self.tr("Umbral auto brillo")), 1, 0)
        self.spin_libraw_auto_bright_thr = QtWidgets.QDoubleSpinBox()
        self.spin_libraw_auto_bright_thr.setRange(0.0, 1.0)
        self.spin_libraw_auto_bright_thr.setDecimals(4)
        self.spin_libraw_auto_bright_thr.setSingleStep(0.001)
        self.spin_libraw_auto_bright_thr.setValue(0.01)
        self.spin_libraw_auto_bright_thr.valueChanged.connect(lambda _value: self._on_raw_decode_control_changed())
        grid.addWidget(self.spin_libraw_auto_bright_thr, 1, 1, 1, 2)

        grid.addWidget(QtWidgets.QLabel(self.tr("Brillo base RAW")), 2, 0)
        self.spin_libraw_bright = QtWidgets.QDoubleSpinBox()
        self.spin_libraw_bright.setRange(0.01, 8.0)
        self.spin_libraw_bright.setDecimals(3)
        self.spin_libraw_bright.setSingleStep(0.05)
        self.spin_libraw_bright.setValue(1.0)
        self.spin_libraw_bright.valueChanged.connect(lambda _value: self._on_raw_decode_control_changed())
        grid.addWidget(self.spin_libraw_bright, 2, 1, 1, 2)

        grid.addWidget(QtWidgets.QLabel(self.tr("Ajuste maximo")), 3, 0)
        self.spin_libraw_adjust_maximum_thr = QtWidgets.QDoubleSpinBox()
        self.spin_libraw_adjust_maximum_thr.setRange(0.0, 1.0)
        self.spin_libraw_adjust_maximum_thr.setDecimals(3)
        self.spin_libraw_adjust_maximum_thr.setSingleStep(0.01)
        self.spin_libraw_adjust_maximum_thr.setValue(0.75)
        self.spin_libraw_adjust_maximum_thr.valueChanged.connect(lambda _value: self._on_raw_decode_control_changed())
        grid.addWidget(self.spin_libraw_adjust_maximum_thr, 3, 1, 1, 2)

        grid.addWidget(QtWidgets.QLabel(self.tr("Altas luces")), 4, 0)
        self.combo_libraw_highlight_mode = QtWidgets.QComboBox()
        for label, value in LIBRAW_HIGHLIGHT_MODE_OPTIONS:
            self.combo_libraw_highlight_mode.addItem(self.tr(label), value)
        self.combo_libraw_highlight_mode.currentIndexChanged.connect(lambda _index: self._on_raw_decode_control_changed())
        grid.addWidget(self.combo_libraw_highlight_mode, 4, 1, 1, 2)

        grid.addWidget(QtWidgets.QLabel(self.tr("Exposicion base RAW")), 5, 0)
        self.spin_libraw_exp_shift = QtWidgets.QDoubleSpinBox()
        self.spin_libraw_exp_shift.setRange(0.25, 8.0)
        self.spin_libraw_exp_shift.setDecimals(3)
        self.spin_libraw_exp_shift.setSingleStep(0.05)
        self.spin_libraw_exp_shift.setValue(1.0)
        self.spin_libraw_exp_shift.valueChanged.connect(lambda _value: self._on_raw_decode_control_changed())
        grid.addWidget(self.spin_libraw_exp_shift, 5, 1, 1, 2)

        grid.addWidget(QtWidgets.QLabel(self.tr("Preservar luces")), 6, 0)
        self.spin_libraw_exp_preserve_highlights = QtWidgets.QDoubleSpinBox()
        self.spin_libraw_exp_preserve_highlights.setRange(0.0, 1.0)
        self.spin_libraw_exp_preserve_highlights.setDecimals(3)
        self.spin_libraw_exp_preserve_highlights.setSingleStep(0.05)
        self.spin_libraw_exp_preserve_highlights.setValue(0.0)
        self.spin_libraw_exp_preserve_highlights.valueChanged.connect(lambda _value: self._on_raw_decode_control_changed())
        grid.addWidget(self.spin_libraw_exp_preserve_highlights, 6, 1, 1, 2)

        self.check_libraw_no_auto_scale = QtWidgets.QCheckBox(self.tr("Desactivar escalado automatico RAW"))
        self.check_libraw_no_auto_scale.toggled.connect(lambda _checked: self._on_raw_decode_control_changed())
        grid.addWidget(self.check_libraw_no_auto_scale, 7, 0, 1, 3)

        grid.addWidget(QtWidgets.QLabel(self.tr("Gamma base RAW")), 8, 0)
        gamma_row = QtWidgets.QHBoxLayout()
        self.spin_libraw_gamma_power = QtWidgets.QDoubleSpinBox()
        self.spin_libraw_gamma_power.setRange(0.1, 8.0)
        self.spin_libraw_gamma_power.setDecimals(3)
        self.spin_libraw_gamma_power.setValue(1.0)
        self.spin_libraw_gamma_power.valueChanged.connect(lambda _value: self._on_raw_decode_control_changed())
        self.spin_libraw_gamma_slope = QtWidgets.QDoubleSpinBox()
        self.spin_libraw_gamma_slope.setRange(0.1, 16.0)
        self.spin_libraw_gamma_slope.setDecimals(3)
        self.spin_libraw_gamma_slope.setValue(1.0)
        self.spin_libraw_gamma_slope.valueChanged.connect(lambda _value: self._on_raw_decode_control_changed())
        gamma_row.addWidget(self.spin_libraw_gamma_power)
        gamma_row.addWidget(self.spin_libraw_gamma_slope)
        grid.addLayout(gamma_row, 8, 1, 1, 2)

        grid.addWidget(QtWidgets.QLabel(self.tr("Aberracion cromatica")), 9, 0)
        ca_row = QtWidgets.QHBoxLayout()
        self.spin_libraw_ca_red = QtWidgets.QDoubleSpinBox()
        self.spin_libraw_ca_red.setRange(0.5, 1.5)
        self.spin_libraw_ca_red.setDecimals(5)
        self.spin_libraw_ca_red.setSingleStep(0.0005)
        self.spin_libraw_ca_red.setValue(1.0)
        self.spin_libraw_ca_red.valueChanged.connect(lambda _value: self._on_raw_decode_control_changed())
        self.spin_libraw_ca_blue = QtWidgets.QDoubleSpinBox()
        self.spin_libraw_ca_blue.setRange(0.5, 1.5)
        self.spin_libraw_ca_blue.setDecimals(5)
        self.spin_libraw_ca_blue.setSingleStep(0.0005)
        self.spin_libraw_ca_blue.setValue(1.0)
        self.spin_libraw_ca_blue.valueChanged.connect(lambda _value: self._on_raw_decode_control_changed())
        ca_row.addWidget(self.spin_libraw_ca_red)
        ca_row.addWidget(self.spin_libraw_ca_blue)
        grid.addLayout(ca_row, 9, 1, 1, 2)

        grid.addWidget(QtWidgets.QLabel(self.tr("Balance blancos RAW")), 10, 0)
        self.combo_wb_mode = QtWidgets.QComboBox(tab)
        for label, val in WB_MODE_OPTIONS:
            self.combo_wb_mode.addItem(self.tr(label), val)
        self.combo_wb_mode.currentIndexChanged.connect(lambda _index: self._on_raw_decode_control_changed())
        grid.addWidget(self.combo_wb_mode, 10, 1, 1, 2)

        grid.addWidget(QtWidgets.QLabel(self.tr("Multiplicadores WB")), 11, 0)
        self.edit_wb_multipliers = QtWidgets.QLineEdit("1,1,1,1", tab)
        self.edit_wb_multipliers.setToolTip(self.tr("Formato: R,G,B,G (o R,G,B)"))
        self.edit_wb_multipliers.editingFinished.connect(self._on_raw_decode_control_changed)
        grid.addWidget(self.edit_wb_multipliers, 11, 1, 1, 2)

        grid.addWidget(self._button(self.tr("Restablecer revelado base"), self._reset_libraw_color_adjustments), 12, 0, 1, 3)

        note_text = self.tr(
            "Ajustes de revelado RAW para casos sin carta. No generan ICC ni calibran la sesion; quedan guardados "
            "como receta de revelado para reproducir el resultado."
        )
        grid.addWidget(self._info_row(self.tr("Revelado base"), note_text), 13, 0, 1, 3)
        return tab

    def _build_tab_preview_settings(self) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(tab)

        self.slider_sharpen, self.label_sharpen = self._slider(
            minimum=0,
            maximum=300,
            value=0,
            on_change=self._on_slider_change,
            formatter=lambda v: self.tr("Cantidad de nitidez") + f": {v / 100:.2f}",
        )
        grid.addWidget(self.label_sharpen, 0, 0, 1, 3)
        grid.addWidget(self.slider_sharpen, 1, 0, 1, 3)

        self.slider_radius, self.label_radius = self._slider(
            minimum=1,
            maximum=80,
            value=10,
            on_change=self._on_slider_change,
            formatter=lambda v: self.tr("Radio nitidez") + f": {v / 10:.1f}",
        )
        grid.addWidget(self.label_radius, 2, 0, 1, 3)
        grid.addWidget(self.slider_radius, 3, 0, 1, 3)

        self.slider_noise_luma, self.label_noise_luma = self._slider(
            minimum=0,
            maximum=100,
            value=0,
            on_change=self._on_slider_change,
            formatter=lambda v: self.tr("Ruido luminancia") + f": {v / 100:.2f}",
        )
        grid.addWidget(self.label_noise_luma, 4, 0, 1, 3)
        grid.addWidget(self.slider_noise_luma, 5, 0, 1, 3)

        self.slider_noise_color, self.label_noise_color = self._slider(
            minimum=0,
            maximum=100,
            value=0,
            on_change=self._on_slider_change,
            formatter=lambda v: self.tr("Ruido color") + f": {v / 100:.2f}",
        )
        grid.addWidget(self.label_noise_color, 6, 0, 1, 3)
        grid.addWidget(self.slider_noise_color, 7, 0, 1, 3)

        self.slider_ca_red, self.label_ca_red = self._slider(
            minimum=-100,
            maximum=100,
            value=0,
            on_change=self._on_slider_change,
            formatter=lambda v: self.tr("CA lateral rojo/cian") + f": {1.0 + v / 10000:.4f}",
        )
        grid.addWidget(self.label_ca_red, 8, 0, 1, 3)
        grid.addWidget(self.slider_ca_red, 9, 0, 1, 3)

        self.slider_ca_blue, self.label_ca_blue = self._slider(
            minimum=-100,
            maximum=100,
            value=0,
            on_change=self._on_slider_change,
            formatter=lambda v: self.tr("CA lateral azul/amarillo") + f": {1.0 + v / 10000:.4f}",
        )
        grid.addWidget(self.label_ca_blue, 10, 0, 1, 3)
        grid.addWidget(self.slider_ca_blue, 11, 0, 1, 3)

        self.check_precision_detail_preview = QtWidgets.QCheckBox(
            self.tr("Modo precision 1:1 para nitidez (mas lento)")
        )
        self.check_precision_detail_preview.setToolTip(
            self.tr("Aplica ajustes de nitidez/ruido/CA sobre fuente a resolucion real durante el arrastre.")
        )
        self.check_precision_detail_preview.setChecked(
            self._settings_bool("preview/precision_detail_1to1", False)
        )
        self.check_precision_detail_preview.toggled.connect(
            self._on_precision_detail_preview_toggled
        )
        grid.addWidget(self.check_precision_detail_preview, 12, 0, 1, 3)

        recipe_filter_note = self.tr(
            "Los filtros reales de nitidez, ruido y aberración cromática se aplican "
            "con los controles superiores. Los campos de receta quedan sólo como "
            "metadatos de compatibilidad."
        )
        grid.addWidget(self._info_row(self.tr("Filtros de receta"), recipe_filter_note), 13, 0, 1, 3)

        grid.addWidget(QtWidgets.QLabel(self.tr("Denoise modo receta")), 14, 0)
        self.combo_recipe_denoise = QtWidgets.QComboBox()
        self.combo_recipe_denoise.addItems(FILTER_MODE_OPTIONS)
        self.combo_recipe_denoise.setEnabled(False)
        self.combo_recipe_denoise.setToolTip(self.tr("Metadato de receta; no modifica píxeles en la GUI."))
        grid.addWidget(self.combo_recipe_denoise, 14, 1, 1, 2)

        grid.addWidget(QtWidgets.QLabel(self.tr("Sharpen modo receta")), 15, 0)
        self.combo_recipe_sharpen = QtWidgets.QComboBox()
        self.combo_recipe_sharpen.addItems(FILTER_MODE_OPTIONS)
        self.combo_recipe_sharpen.setEnabled(False)
        self.combo_recipe_sharpen.setToolTip(self.tr("Metadato de receta; no modifica píxeles en la GUI."))
        grid.addWidget(self.combo_recipe_sharpen, 15, 1, 1, 2)

        grid.addWidget(self._button(self.tr("Restablecer nitidez"), self._reset_adjustments), 16, 0, 1, 3)
        grid.addWidget(
            self._build_named_adjustment_profile_panel("detail", self.tr("Nitidez")),
            17,
            0,
            1,
            3,
        )
        return tab

    def _build_tab_raw_config(self, title: str | None = None) -> QtWidgets.QWidget:
        tab = QtWidgets.QGroupBox(title) if title else QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(tab)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        recipe_grid = QtWidgets.QGridLayout()
        self.path_recipe = QtWidgets.QLineEdit("testdata/recipes/scientific_recipe.yml")
        self._add_path_row(
            recipe_grid,
            0,
            self.tr("Receta YAML/JSON"),
            self.path_recipe,
            file_mode=True,
            save_mode=False,
            dir_mode=False,
        )
        row_recipe = QtWidgets.QHBoxLayout()
        row_recipe.addWidget(self._button(self.tr("Cargar receta"), self._menu_load_recipe))
        row_recipe.addWidget(self._button(self.tr("Guardar receta"), self._menu_save_recipe))
        row_recipe.addWidget(self._button(self.tr("Receta por defecto"), self._menu_reset_recipe))
        recipe_grid.addLayout(row_recipe, 1, 0, 1, 3)
        outer.addLayout(recipe_grid)

        demosaic_box = QtWidgets.QGroupBox(self.tr("Desentramado"))
        grid = QtWidgets.QGridLayout(demosaic_box)

        grid.addWidget(QtWidgets.QLabel(self.tr("Motor RAW")), 0, 0)
        self.combo_raw_developer = QtWidgets.QComboBox()
        self.combo_raw_developer.addItem(self.tr("LibRaw / rawpy"), "libraw")
        self.combo_raw_developer.setEnabled(False)
        grid.addWidget(self.combo_raw_developer, 0, 1, 1, 2)

        grid.addWidget(QtWidgets.QLabel(self.tr("Método")), 1, 0)
        self.combo_demosaic = QtWidgets.QComboBox()
        for label, opt in DEMOSAIC_OPTIONS:
            self.combo_demosaic.addItem(self.tr(label), opt)
        self._sync_demosaic_capabilities()
        self.combo_demosaic.currentIndexChanged.connect(lambda _index: self._on_raw_demosaic_changed())
        grid.addWidget(self.combo_demosaic, 1, 1, 1, 2)

        self.check_four_color_rgb = QtWidgets.QCheckBox(self.tr("Interpolar verdes por separado (4 colores)"))
        self.check_four_color_rgb.toggled.connect(lambda _checked: self._on_raw_decode_control_changed())
        grid.addWidget(self.check_four_color_rgb, 2, 0, 1, 3)

        grid.addWidget(QtWidgets.QLabel(self.tr("Borde")), 3, 0)
        self.spin_demosaic_edge_quality = QtWidgets.QSpinBox()
        self.spin_demosaic_edge_quality.setRange(0, 32)
        self.spin_demosaic_edge_quality.valueChanged.connect(lambda _value: self._on_raw_decode_control_changed())
        grid.addWidget(self.spin_demosaic_edge_quality, 3, 1, 1, 2)

        grid.addWidget(QtWidgets.QLabel(self.tr("Pasos de supresión de falso color")), 4, 0)
        self.spin_false_color_suppression = QtWidgets.QSpinBox()
        self.spin_false_color_suppression.setRange(0, 10)
        self.spin_false_color_suppression.valueChanged.connect(lambda _value: self._on_raw_decode_control_changed())
        grid.addWidget(self.spin_false_color_suppression, 4, 1, 1, 2)

        self.raw_algorithm_options_status_label = QtWidgets.QLabel("")
        self.raw_algorithm_options_status_label.setWordWrap(True)
        self.raw_algorithm_options_status_label.setStyleSheet("font-size: 12px; color: #d4d4d4;")
        grid.addWidget(self.raw_algorithm_options_status_label, 5, 0, 1, 3)
        outer.addWidget(demosaic_box)

        black_box = QtWidgets.QGroupBox(self.tr("Puntos de negro RAW"))
        black_grid = QtWidgets.QGridLayout(black_box)
        black_grid.addWidget(QtWidgets.QLabel(self.tr("Modo")), 0, 0)
        self.combo_black_mode = QtWidgets.QComboBox()
        for label, val in BLACK_MODE_OPTIONS:
            self.combo_black_mode.addItem(self.tr(label), val)
        self.combo_black_mode.currentIndexChanged.connect(lambda _index: self._on_raw_decode_control_changed())
        black_grid.addWidget(self.combo_black_mode, 0, 1)
        self.spin_black_value = QtWidgets.QSpinBox()
        self.spin_black_value.setRange(0, 65535)
        self.spin_black_value.valueChanged.connect(lambda _value: self._on_raw_decode_control_changed())
        black_grid.addWidget(self.spin_black_value, 0, 2)
        outer.addWidget(black_box)

        raw_note = self.tr(
            "Este panel controla solo la lectura y el destramado del RAW. El ICC de cámara se decide en "
            "Color / calibración; la conversión al monitor se aplica solo para visualizar. Exposición, color, "
            "contraste, ruido y nitidez pertenecen a sus paneles específicos."
        )
        outer.addWidget(self._info_row(self.tr("Lectura RAW"), raw_note))

        tiff_box = QtWidgets.QGroupBox(self.tr("Exportacion TIFF"))
        tiff_grid = QtWidgets.QGridLayout(tiff_box)
        tiff_grid.addWidget(QtWidgets.QLabel(self.tr("Compresion")), 0, 0)
        self.combo_tiff_compression = QtWidgets.QComboBox()
        for label, value in TIFF_COMPRESSION_OPTIONS:
            self.combo_tiff_compression.addItem(self.tr(label), value)
        self.combo_tiff_compression.setToolTip(
            self.tr("La salida sigue siendo TIFF RGB 16-bit. JPEG/LZW/ZSTD pueden requerir codecs adicionales.")
        )
        tiff_grid.addWidget(self.combo_tiff_compression, 0, 1)
        tiff_grid.addWidget(QtWidgets.QLabel(self.tr("Hilos compresion")), 1, 0)
        self.spin_tiff_maxworkers = QtWidgets.QSpinBox()
        self.spin_tiff_maxworkers.setRange(0, 64)
        self.spin_tiff_maxworkers.setValue(0)
        self.spin_tiff_maxworkers.setSpecialValueText(self.tr("Automático"))
        self.spin_tiff_maxworkers.setToolTip(
            self.tr("0 reparte CPU automaticamente en lote; valores mayores fuerzan hilos por TIFF.")
        )
        tiff_grid.addWidget(self.spin_tiff_maxworkers, 1, 1)
        tiff_note = self.tr(
            "ZIP, LZW y ZSTD son compresiones sin perdida. JPEG reduce tamano pero puede alterar pixeles. "
            "Automático usa varios nucleos sin saturar el equipo durante lotes."
        )
        tiff_grid.addWidget(self._info_row(self.tr("Compresión TIFF"), tiff_note), 2, 0, 1, 2)
        outer.addWidget(tiff_box)

        self._build_hidden_raw_compatibility_controls(tab)
        outer.addWidget(self._build_named_adjustment_profile_panel("raw_export", self.tr("Exportacion RAW")))
        outer.addStretch(1)
        self._update_raw_algorithm_option_state()
        return tab

    def _build_hidden_raw_compatibility_controls(self, parent: QtWidgets.QWidget) -> None:
        created_hidden_widgets: list[QtWidgets.QWidget] = []
        if not hasattr(self, "combo_wb_mode"):
            self.combo_wb_mode = QtWidgets.QComboBox(parent)
            for label, val in WB_MODE_OPTIONS:
                self.combo_wb_mode.addItem(self.tr(label), val)
            created_hidden_widgets.append(self.combo_wb_mode)

        if not hasattr(self, "edit_wb_multipliers"):
            self.edit_wb_multipliers = QtWidgets.QLineEdit("1,1,1,1", parent)
            self.edit_wb_multipliers.setToolTip(self.tr("Formato: R,G,B,G (o R,G,B)"))
            created_hidden_widgets.append(self.edit_wb_multipliers)

        self.spin_exposure = QtWidgets.QDoubleSpinBox(parent)
        self.spin_exposure.setRange(-8.0, 8.0)
        self.spin_exposure.setDecimals(2)
        self.spin_exposure.setSingleStep(0.1)

        self.combo_tone_curve = QtWidgets.QComboBox(parent)
        for label, val in TONE_OPTIONS:
            self.combo_tone_curve.addItem(self.tr(label), val)
        self.spin_gamma = QtWidgets.QDoubleSpinBox(parent)
        self.spin_gamma.setRange(0.8, 4.0)
        self.spin_gamma.setDecimals(2)
        self.spin_gamma.setValue(2.2)

        self.check_output_linear = QtWidgets.QCheckBox(self.tr("Salida lineal"), parent)
        self.check_output_linear.setChecked(True)
        self.check_output_linear.toggled.connect(self._on_output_linear_toggled)

        self.combo_working_space = QtWidgets.QComboBox(parent)
        self.combo_working_space.addItems(SPACE_OPTIONS)
        self.combo_working_space.setEnabled(False)

        self.combo_output_space = QtWidgets.QComboBox(parent)
        self.combo_output_space.addItems(SPACE_OPTIONS)
        self.combo_output_space.currentTextChanged.connect(self._on_output_space_changed)

        self.combo_sampling = QtWidgets.QComboBox(parent)
        self.combo_sampling.addItems(SAMPLE_OPTIONS)

        self.check_profiling_mode = QtWidgets.QCheckBox(self.tr("Profiling mode"), parent)
        self.check_profiling_mode.setChecked(True)

        self.edit_input_color = QtWidgets.QLineEdit("camera_native", parent)
        self.edit_input_color.setReadOnly(True)
        self.edit_illuminant = QtWidgets.QLineEdit("", parent)

        for widget in (
            self.spin_exposure,
            self.combo_tone_curve,
            self.spin_gamma,
            self.check_output_linear,
            self.combo_working_space,
            self.combo_output_space,
            self.combo_sampling,
            self.check_profiling_mode,
            self.edit_input_color,
            self.edit_illuminant,
            *created_hidden_widgets,
        ):
            widget.hide()

    def _build_tab_profile_config(self) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(tab)

        grid.addWidget(QtWidgets.QLabel(self.tr("ICC especifico")), 0, 0)
        self.icc_profile_combo = QtWidgets.QComboBox()
        self.icc_profile_combo.setToolTip(
            self.tr("Perfiles ICC registrados en la sesion. Permite activar perfiles generados en el proyecto.")
        )
        grid.addWidget(self.icc_profile_combo, 0, 1, 1, 2)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(self._button(self.tr("Activar seleccionado"), self._activate_selected_icc_profile))
        row.addWidget(self._button(self.tr("Cargar ICC de camara..."), self._menu_load_profile))
        row.addWidget(self._button(self.tr("Usar ICC generado"), self._use_generated_profile_as_active))
        grid.addLayout(row, 1, 0, 1, 3)

        assign_row = QtWidgets.QHBoxLayout()
        assign_row.addWidget(self._button(self.tr("Aplicar ICC a seleccion"), self._assign_active_icc_profile_to_selected))
        assign_row.addWidget(self._button(self.tr("Aplicar ICC a sesion"), self._assign_active_icc_profile_to_session_raws))
        grid.addLayout(assign_row, 2, 0, 1, 3)

        self.path_profile_active = QtWidgets.QLineEdit("/tmp/camera_profile.icc")
        self._add_path_row(grid, 3, self.tr("Perfil ICC de la imagen"), self.path_profile_active, file_mode=True, save_mode=False, dir_mode=False)

        self.icc_profile_status_label = QtWidgets.QLabel(self.tr("Sin perfiles ICC de sesión"))
        self.icc_profile_status_label.setWordWrap(True)
        self.icc_profile_status_label.setStyleSheet("font-size: 12px; color: #d8d8d8;")
        grid.addWidget(self.icc_profile_status_label, 4, 0, 1, 3)

        self._refresh_icc_profile_combo()
        return tab

    def _build_icc_workflow_decision_panel(self) -> QtWidgets.QWidget:
        box = QtWidgets.QGroupBox(self.tr("Perfil ICC de la imagen"))
        grid = QtWidgets.QGridLayout(box)
        self.path_profile_active = QtWidgets.QLineEdit("")
        self.path_profile_active.hide()

        self.radio_icc_generic = QtWidgets.QRadioButton(self.tr("Perfil ICC RGB estandar"))
        self.radio_icc_existing = QtWidgets.QRadioButton(self.tr("Perfiles ICC de la sesion"))
        self.radio_icc_generate = QtWidgets.QRadioButton(self.tr("Generar perfil ICC"))
        self.radio_icc_custom = self.radio_icc_existing
        self.radio_icc_generic.setChecked(True)
        grid.addWidget(self.radio_icc_generic, 0, 0, 1, 3)

        grid.addWidget(QtWidgets.QLabel(self.tr("Espacio RGB estandar")), 1, 0)
        self.combo_generic_icc_space = QtWidgets.QComboBox()
        self.combo_generic_icc_space.setToolTip(
            self.tr("Perfil ICC RGB estandar. ProPhoto RGB se usa por defecto si no eliges otro.")
        )
        for label, value in (
            (self.tr("sRGB"), "srgb"),
            (self.tr("Adobe RGB"), "adobe_rgb"),
            (self.tr("ProPhoto RGB"), "prophoto_rgb"),
        ):
            self.combo_generic_icc_space.addItem(label, value)
        self.combo_generic_icc_space.setCurrentIndex(2)
        grid.addWidget(self.combo_generic_icc_space, 1, 1, 1, 2)

        grid.addWidget(self.radio_icc_existing, 2, 0, 1, 3)
        grid.addWidget(QtWidgets.QLabel(self.tr("Perfil de sesion")), 3, 0)
        self.icc_profile_combo = QtWidgets.QComboBox()
        self.icc_profile_combo.setToolTip(
            self.tr("Perfiles ICC generados o registrados en esta sesion. Al elegir uno queda activo en la imagen.")
        )
        grid.addWidget(self.icc_profile_combo, 3, 1, 1, 2)

        self.icc_existing_availability_label = QtWidgets.QLabel("")
        self.icc_existing_availability_label.setWordWrap(True)
        self.icc_existing_availability_label.setStyleSheet("font-size: 12px; color: #d4d4d4; padding-left: 18px;")
        grid.addWidget(self.icc_existing_availability_label, 4, 0, 1, 3)

        self.icc_profile_status_label = QtWidgets.QLabel(self.tr("Sin perfiles ICC de sesion"))
        self.icc_profile_status_label.setWordWrap(True)
        self.icc_profile_status_label.setStyleSheet("font-size: 12px; color: #d8d8d8; padding-left: 18px;")
        grid.addWidget(self.icc_profile_status_label, 5, 0, 1, 3)

        grid.addWidget(self.radio_icc_generate, 6, 0, 1, 3)
        self.icc_workflow_decision_label = QtWidgets.QLabel("")
        self.icc_workflow_decision_label.setWordWrap(True)
        self.icc_workflow_decision_label.setStyleSheet("font-size: 12px; color: #d8d8d8;")
        grid.addWidget(self.icc_workflow_decision_label, 7, 0, 1, 3)

        self.radio_icc_generic.toggled.connect(lambda _checked: self._on_icc_workflow_choice_changed())
        self.radio_icc_existing.toggled.connect(lambda _checked: self._on_icc_workflow_choice_changed())
        self.radio_icc_generate.toggled.connect(lambda _checked: self._on_icc_workflow_choice_changed())
        self.radio_icc_generic.toggled.connect(lambda checked: self._apply_generic_icc_workflow_to_controls() if checked else None)
        self.icc_profile_combo.currentIndexChanged.connect(lambda _index: self._on_session_icc_profile_selected())
        self.combo_generic_icc_space.currentIndexChanged.connect(lambda _index: self._apply_generic_icc_workflow_to_controls())
        self._refresh_icc_profile_combo()
        self._on_icc_workflow_choice_changed()
        return box

    def _build_icc_profile_information_panel(self) -> QtWidgets.QWidget:
        box = QtWidgets.QGroupBox(self.tr("Estado ICC"))
        layout = QtWidgets.QVBoxLayout(box)
        self.icc_selected_file_info_label = QtWidgets.QLabel(self.tr("Imagen seleccionada: ninguna"))
        self.icc_selected_file_info_label.setWordWrap(True)
        self.icc_selected_file_info_label.setStyleSheet(
            "font-size: 12px; color: #f0f0f0; background-color: #262626; "
            "border: 1px solid #505050; border-radius: 4px; padding: 6px;"
        )
        layout.addWidget(self.icc_selected_file_info_label)

        self.icc_session_info_label = QtWidgets.QLabel(self.tr("Perfiles ICC de sesion: 0 | Activo: ninguno"))
        self.icc_session_info_label.setWordWrap(True)
        self.icc_session_info_label.setStyleSheet("font-size: 12px; color: #d8d8d8;")
        layout.addWidget(self.icc_session_info_label)

        note = self.tr(
            "El ICC elegido aqui se usa como perfil de la imagen para visualizar y exportar. "
            "Si no eliges un ICC de sesion, se usa un perfil ICC RGB estandar; ProPhoto RGB "
            "es el valor predeterminado. "
            "La correccion final de pantalla usa aparte el perfil ICC del monitor detectado "
            "por el sistema operativo. Los perfiles de ajuste de color/contraste se guardan "
            "en la pestana Color y contraste."
        )
        layout.addWidget(self._info_row(self.tr("Uso de ICC"), note))
        self._refresh_selected_icc_profile_info()
        return box

    def _build_tab_batch_config(self) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        grid = QtWidgets.QGridLayout()

        self.batch_input_dir = QtWidgets.QLineEdit(str(self._current_dir))
        self._add_path_row(grid, 0, self.tr("RAW a revelar (carpeta)"), self.batch_input_dir, file_mode=False, save_mode=False, dir_mode=True)

        self.batch_out_dir = QtWidgets.QLineEdit("/tmp/probraw_batch_tiffs")
        self._add_path_row(grid, 1, self.tr("Salida TIFF derivados"), self.batch_out_dir, file_mode=False, save_mode=False, dir_mode=True)

        self.batch_embed_profile = QtWidgets.QCheckBox(self.tr("Incrustar/aplicar ICC en TIFF"))
        self.batch_embed_profile.setChecked(True)
        self.batch_embed_profile.setEnabled(False)
        self.batch_embed_profile.setToolTip(
            self.tr(
                "Siempre activo: usa el ICC de entrada si la salida es RGB de cámara, "
                "o un ICC estándar si la salida es sRGB/Adobe RGB/ProPhoto."
            )
        )
        grid.addWidget(self.batch_embed_profile, 2, 0, 1, 3)

        self.batch_apply_adjustments = QtWidgets.QCheckBox(self.tr("Aplicar ajustes básicos y de nitidez"))
        self.batch_apply_adjustments.setChecked(True)
        grid.addWidget(self.batch_apply_adjustments, 3, 0, 1, 3)

        row_1 = QtWidgets.QHBoxLayout()
        row_1.addWidget(self._button(self.tr("Usar carpeta actual"), self._use_current_dir_as_batch_input))
        row_1.addWidget(self._button(self.tr("Aplicar a selección"), self._on_batch_develop_selected))
        row_1.addWidget(self._button(self.tr("Aplicar a carpeta"), self._on_batch_develop_directory))

        self.batch_output = QtWidgets.QPlainTextEdit()
        self.batch_output.setReadOnly(True)
        self.batch_output.setPlaceholderText(self.tr("Salida JSON de exportación de derivados"))

        layout.addLayout(grid)
        layout.addLayout(row_1)
        layout.addWidget(self.batch_output, 1)
        return tab
