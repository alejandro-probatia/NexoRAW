from __future__ import annotations

from ._imports import *  # noqa: F401,F403


class LayoutMixin:
    def _info_button(self, title: str, text: str) -> QtWidgets.QToolButton:
        button = QtWidgets.QToolButton()
        button.setText("i")
        button.setAutoRaise(True)
        button.setCursor(QtCore.Qt.PointingHandCursor)
        button.setToolTip(str(text))
        button.setAccessibleName(str(title or self.tr("Información")))
        button.setFixedSize(22, 22)
        button.setStyleSheet(
            "QToolButton {"
            " border: 1px solid #707070;"
            " border-radius: 11px;"
            " color: #d0d0d0;"
            " background: #2a2a2a;"
            " font-weight: 700;"
            " padding: 0;"
            "}"
            "QToolButton:hover { background: #3f3f3f; color: #ffffff; }"
        )
        button.clicked.connect(
            lambda _checked=False, info_title=str(title or self.tr("Información")), info_text=str(text): QtWidgets.QMessageBox.information(
                self,
                info_title,
                info_text,
            )
        )
        return button

    def _info_row(self, title: str, text: str) -> QtWidgets.QWidget:
        row = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addStretch(1)
        layout.addWidget(self._info_button(title, text))
        return row

    def _build_ui(self) -> None:
        root = QtWidgets.QWidget()
        root_layout = QtWidgets.QVBoxLayout(root)
        root_layout.setContentsMargins(4, 4, 4, 4)
        root_layout.setSpacing(4)

        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)
        header.addStretch(1)
        header.addWidget(self._button(self.tr("Inicio"), self._go_home_directory))
        header.addWidget(self._button(self.tr("Abrir carpeta..."), self._pick_directory))
        header.addWidget(self._button(self.tr("Recargar"), self._reload_current_directory))
        header.addWidget(self._button(self.tr("Pantalla completa"), self._menu_toggle_fullscreen))
        root_layout.addLayout(header)

        task_panel = QtWidgets.QWidget()
        task_panel.setObjectName("globalProgressPanel")
        task_panel.setStyleSheet(
            "QWidget#globalProgressPanel {"
            " background-color: #262626;"
            " border: 1px solid #505050;"
            " border-radius: 4px;"
            "}"
        )
        task_bar = QtWidgets.QVBoxLayout(task_panel)
        task_bar.setContentsMargins(8, 5, 8, 5)
        task_bar.setSpacing(3)

        task_top = QtWidgets.QHBoxLayout()
        task_top.setContentsMargins(0, 0, 0, 0)
        task_top.setSpacing(8)
        self.global_status_label = QtWidgets.QLabel(self.tr("Listo"))
        self.global_status_label.setWordWrap(True)
        self.global_status_label.setStyleSheet("font-size: 12px; color: #f0f0f0; font-weight: 600;")
        self.global_status_label.setToolTip(self.tr("Estado de la operacion principal"))
        self.global_progress_time_label = QtWidgets.QLabel(self.tr("Tiempo: --"))
        self.global_progress_time_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.global_progress_time_label.setStyleSheet("font-size: 11px; color: #d4d4d4;")
        self.global_progress_time_label.setToolTip(self.tr("Tiempo transcurrido o estimado"))
        task_top.addWidget(self.global_status_label, 2)
        task_top.addWidget(self.global_progress_time_label, 1)
        task_bar.addLayout(task_top)

        self.global_progress = QtWidgets.QProgressBar()
        self.global_progress.setRange(0, 1)
        self.global_progress.setValue(0)
        self.global_progress.setTextVisible(False)
        self.global_progress.setMaximumHeight(8)
        self.global_progress.setToolTip(self.tr("Progreso de la tarea en segundo plano"))
        task_bar.addWidget(self.global_progress)

        self.global_progress_phase_label = QtWidgets.QLabel(self.tr("Sin operación en curso"))
        self.global_progress_phase_label.setWordWrap(True)
        self.global_progress_phase_label.setStyleSheet("font-size: 11px; color: #a6a6a6;")
        self.global_progress_phase_label.setToolTip(self.tr("Fase actual de la operacion"))
        task_bar.addWidget(self.global_progress_phase_label)
        root_layout.addWidget(task_panel)

        self.main_tabs = QtWidgets.QTabWidget()
        session_tab = self._build_tab_session()
        raw_tab = self._build_tab_raw_develop()
        queue_tab = self._build_tab_queue()

        self.main_tabs.addTab(session_tab, self.tr("1. Sesión"))
        self.main_tabs.addTab(raw_tab, self.tr("2. Ajustar / Aplicar"))
        self.main_tabs.addTab(queue_tab, self.tr("3. Cola de Revelado"))
        self.main_tabs.setTabToolTip(0, self.tr("Crear, abrir y revisar una sesion de trabajo"))
        self.main_tabs.setTabToolTip(1, self.tr("Seleccionar imagen, ajustar color, ICC, nitidez y exportacion"))
        self.main_tabs.setTabToolTip(2, self.tr("Preparar y ejecutar revelados por lote"))
        self.main_tabs.currentChanged.connect(self._on_mtf_context_visibility_changed)

        root_layout.addWidget(self.main_tabs, 1)

        self.setCentralWidget(root)
        app = QtWidgets.QApplication.instance()
        if app is not None and not bool(getattr(self, "_viewer_space_event_filter_installed", False)):
            app.installEventFilter(self)
            self._viewer_space_event_filter_installed = True
        self._build_global_settings_dialog()

    def _build_menu_bar(self) -> None:
        mb = self.menuBar()

        menu_file = mb.addMenu(self.tr("Archivo"))
        menu_file.addAction(self._action(self.tr("Crear sesión..."), self._on_create_session))
        menu_file.addAction(self._action(self.tr("Abrir sesión..."), self._on_open_session))
        menu_file.addAction(self._action(self.tr("Guardar sesión"), self._on_save_session, "Ctrl+Shift+S"))
        menu_file.addSeparator()
        menu_file.addAction(self._action(self.tr("Abrir carpeta..."), self._pick_directory, "Ctrl+O"))
        menu_file.addAction(self._action(self.tr("Guardar vista previa PNG"), self._on_save_preview, "Ctrl+S"))
        menu_file.addAction(self._action(self.tr("Aplicar ajustes a selección"), self._on_batch_develop_selected, "Ctrl+R"))
        menu_file.addSeparator()
        menu_file.addAction(self._action(self.tr("Salir"), self.close, "Ctrl+Q"))

        self._add_edit_menu(mb)

        menu_cfg = mb.addMenu(self.tr("Configuracion"))
        menu_cfg.addAction(self._action(self.tr("Cargar receta..."), self._menu_load_recipe))
        menu_cfg.addAction(self._action(self.tr("Guardar receta..."), self._menu_save_recipe))
        menu_cfg.addAction(self._action(self.tr("Receta por defecto"), self._menu_reset_recipe))
        menu_cfg.addSeparator()
        menu_cfg.addAction(self._action(self.tr("Configuracion global..."), self._open_global_settings_dialog))
        menu_cfg.addSeparator()
        menu_cfg.addAction(self._action(self.tr("Ir a pestaña Sesión"), lambda: self.main_tabs.setCurrentIndex(0)))
        menu_cfg.addAction(self._action(self.tr("Ir a pestaña Revelado"), lambda: self.main_tabs.setCurrentIndex(1)))
        menu_cfg.addAction(self._action(self.tr("Ir a pestaña Cola"), lambda: self.main_tabs.setCurrentIndex(2)))

        menu_profile = mb.addMenu(self.tr("Perfil ICC"))
        menu_profile.addAction(self._action(self.tr("Cargar perfil activo..."), self._menu_load_profile))
        menu_profile.addAction(self._action(self.tr("Usar perfil generado"), self._use_generated_profile_as_active))
        menu_profile.addAction(self._action(self.tr("Comparar reportes QA..."), self._menu_compare_qa_reports))

        self._add_image_adjustment_menu(mb)

        menu_view = mb.addMenu(self.tr("Vista"))
        a_compare = self._action(self.tr("Comparar original/resultado"), self._menu_toggle_compare)
        a_compare.setCheckable(True)
        a_compare.setChecked(False)
        self._action_compare = a_compare
        menu_view.addAction(a_compare)
        menu_view.addAction(self._action(self.tr("Ir a Nitidez"), lambda: self._go_to_nitidez_tab()))
        menu_view.addAction(self._action(self.tr("Pantalla completa"), self._menu_toggle_fullscreen, "F11"))
        menu_view.addAction(self._action(self.tr("Restablecer distribución"), self._reset_layout_splitters))

        menu_help = mb.addMenu(self.tr("Ayuda"))
        menu_help.addAction(self._action(self.tr("Diagnóstico herramientas..."), self._menu_check_tools))
        menu_help.addAction(self._action(self.tr("Buscar actualizaciones..."), self._menu_check_updates))
        menu_help.addAction(self._action(f"Acerca de {APP_NAME}", self._menu_about))

    def _go_to_nitidez_tab(self) -> None:
        self.main_tabs.setCurrentIndex(1)
        if hasattr(self, "right_workflow_tabs"):
            index = -1
            for i in range(self.right_workflow_tabs.count()):
                if self.right_workflow_tabs.tabText(i) == self.tr("Nitidez"):
                    index = i
                    break
            self.right_workflow_tabs.setCurrentIndex(index if index >= 0 else 2)

    def _menu_toggle_fullscreen(self, _checked: bool = False) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _reset_layout_splitters(self) -> None:
        if hasattr(self, "raw_splitter"):
            w = max(1200, int(self.width() * 0.98))
            left = max(260, int(w * 0.16))
            right = max(300, int(w * 0.21))
            center = max(520, w - left - right)
            self.raw_splitter.setSizes([left, center, right])
            self._left_pane_last_open_width = left

        if hasattr(self, "compare_splitter"):
            cw = max(600, int(self.width() * 0.55))
            self.compare_splitter.setSizes([cw // 2, cw // 2])

        if hasattr(self, "viewer_splitter"):
            h = max(700, int(self.height() * 0.85))
            self.viewer_splitter.setSizes([
                int(h * 0.76),
                int(h * 0.24),
            ])

    def _restore_window_settings(self) -> bool:
        restored_layout = False
        geometry = self._settings_to_bytearray(self._settings.value("window/geometry"))
        if geometry is not None:
            self.restoreGeometry(geometry)

        state = self._settings_to_bytearray(self._settings.value("window/state"))
        if state is not None:
            self.restoreState(state)

        layout_version = self._settings.value("layout/version")
        try:
            layout_version = int(layout_version) if layout_version is not None else 0
        except (TypeError, ValueError):
            layout_version = 0
        if layout_version != LAYOUT_VERSION:
            return False

        raw_splitter_state = self._settings_to_bytearray(self._settings.value("layout/raw_splitter"))
        if raw_splitter_state is not None and hasattr(self, "raw_splitter"):
            self.raw_splitter.restoreState(raw_splitter_state)
            restored_layout = True

        viewer_splitter_state = self._settings_to_bytearray(self._settings.value("layout/viewer_splitter"))
        if viewer_splitter_state is not None and hasattr(self, "viewer_splitter"):
            self.viewer_splitter.restoreState(viewer_splitter_state)
            restored_layout = True

        compare_splitter_state = self._settings_to_bytearray(self._settings.value("layout/compare_splitter"))
        if compare_splitter_state is not None and hasattr(self, "compare_splitter"):
            self.compare_splitter.restoreState(compare_splitter_state)
            restored_layout = True
        return restored_layout

    def _save_window_settings(self) -> None:
        self._settings.setValue("window/geometry", self.saveGeometry())
        self._settings.setValue("window/state", self.saveState())
        self._settings.setValue("layout/version", LAYOUT_VERSION)
        if hasattr(self, "raw_splitter"):
            self._settings.setValue("layout/raw_splitter", self.raw_splitter.saveState())
        if hasattr(self, "viewer_splitter"):
            self._settings.setValue("layout/viewer_splitter", self.viewer_splitter.saveState())
        if hasattr(self, "compare_splitter"):
            self._settings.setValue("layout/compare_splitter", self.compare_splitter.saveState())

    def _settings_to_bytearray(self, value):
        if value is None:
            return None
        if isinstance(value, QtCore.QByteArray):
            return value
        if isinstance(value, (bytes, bytearray)):
            return QtCore.QByteArray(bytes(value))
        return None

    def _settings_bool(self, key: str, default: bool = False) -> bool:
        value = self._settings.value(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def _default_work_directory(self) -> Path:
        try:
            return Path.home().expanduser().resolve()
        except Exception:
            return Path.cwd().expanduser().resolve()

    def _startup_directory_from_settings(self) -> Path:
        folder = self._persistent_directory("browser/last_dir")
        return folder or self._default_work_directory()

    def _persistent_directory(self, key: str) -> Path | None:
        text = str(self._settings.value(key) or "").strip()
        if not text:
            return None
        if self._is_legacy_temp_output_path(text):
            self._settings.remove(key)
            return None
        folder = Path(text).expanduser()
        if folder.exists() and folder.is_dir():
            return folder.resolve()
        self._settings.remove(key)
        return None

    def _persistent_session_root(self) -> Path | None:
        key = "session/last_root"
        text = str(self._settings.value(key) or "").strip()
        if not text:
            return None
        if self._is_legacy_temp_output_path(text):
            self._settings.remove(key)
            return None
        root = Path(text).expanduser()
        if session_file_path(root).exists():
            return root.resolve()
        self._settings.remove(key)
        return None

    def _restore_startup_context(self) -> bool:
        root = self._persistent_session_root()
        if root is not None:
            try:
                self._activate_session(root, load_session(root))
                return True
            except Exception as exc:
                self._settings.remove("session/last_root")
                self._set_status(self.tr("No se pudo restaurar la ultima sesion:") + f" {exc}")

        folder = self._persistent_directory("browser/last_dir")
        if folder is not None:
            self._set_current_directory(folder)
            return True
        return False

    def closeEvent(self, event) -> None:  # noqa: N802
        app = QtWidgets.QApplication.instance()
        if app is not None and bool(getattr(self, "_viewer_space_event_filter_installed", False)):
            app.removeEventFilter(self)
            self._viewer_space_event_filter_installed = False
        if hasattr(self, "_shutdown_background_threads"):
            self._shutdown_background_threads()
        self._save_window_settings()
        super().closeEvent(event)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() not in (QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease):
            return False
        if event.key() != QtCore.Qt.Key_Space:
            return False
        widget = obj if isinstance(obj, QtWidgets.QWidget) else None
        if widget is not None and widget.window() is not self:
            return False
        active = event.type() == QtCore.QEvent.KeyPress
        if not active and bool(getattr(self, "_viewer_space_pan_active", False)):
            if not event.isAutoRepeat():
                self._set_viewer_space_pan_active(False)
            return True
        if not self.isActiveWindow() or self._viewer_space_pan_ignores_focus():
            return False
        if not event.isAutoRepeat():
            self._set_viewer_space_pan_active(active)
        return True

    def _viewer_space_pan_ignores_focus(self) -> bool:
        focus = QtWidgets.QApplication.focusWidget()
        if focus is None:
            return False
        ignored_types = (
            QtWidgets.QLineEdit,
            QtWidgets.QTextEdit,
            QtWidgets.QPlainTextEdit,
            QtWidgets.QAbstractSpinBox,
            QtWidgets.QComboBox,
            QtWidgets.QAbstractButton,
        )
        return isinstance(focus, ignored_types)

    def _set_viewer_space_pan_active(self, active: bool) -> None:
        self._viewer_space_pan_active = bool(active)
        for panel_name in ("image_result_single", "image_original_compare", "image_result_compare"):
            panel = getattr(self, panel_name, None)
            if panel is not None and hasattr(panel, "set_space_pan_active"):
                panel.set_space_pan_active(self._viewer_space_pan_active)

    def _build_tab_session(self) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(tab)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        session_box = QtWidgets.QGroupBox(self.tr("Gestión de sesión"))
        grid = QtWidgets.QGridLayout(session_box)

        self.session_root_path = QtWidgets.QLineEdit(str(self._current_dir / "probraw_session"))
        self.session_root_path.setPlaceholderText(self.tr("Directorio raiz del proyecto"))
        self.session_root_path.setToolTip(self.tr("Carpeta que contiene la estructura persistente de la sesion"))
        self._add_path_row(grid, 0, self.tr("Directorio raíz de sesión"), self.session_root_path, file_mode=False, save_mode=False, dir_mode=True)
        self.session_root_path.editingFinished.connect(self._on_session_root_edited)
        self.session_root_path.textChanged.connect(lambda _text: self._session_root_update_timer.start(150))

        grid.addWidget(QtWidgets.QLabel(self.tr("Nombre de sesión")), 1, 0)
        self.session_name_edit = QtWidgets.QLineEdit("")
        self.session_name_edit.setPlaceholderText(self.tr("Nombre visible de la sesion"))
        self.session_name_edit.setToolTip(self.tr("Nombre que se guardara en session.json y en la lista de recientes"))
        grid.addWidget(self.session_name_edit, 1, 1, 1, 2)

        grid.addWidget(QtWidgets.QLabel(self.tr("Condiciones de iluminación")), 2, 0)
        self.session_illumination_edit = QtWidgets.QLineEdit("")
        self.session_illumination_edit.setPlaceholderText(self.tr("Iluminante, entorno y estabilidad de la luz"))
        grid.addWidget(self.session_illumination_edit, 2, 1, 1, 2)

        grid.addWidget(QtWidgets.QLabel(self.tr("Notas de toma")), 3, 0)
        self.session_capture_edit = QtWidgets.QLineEdit("")
        self.session_capture_edit.setPlaceholderText(self.tr("Camara, optica, carta, distancia o incidencias"))
        grid.addWidget(self.session_capture_edit, 3, 1, 1, 2)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(self._button(self.tr("Usar carpeta actual"), self._use_current_dir_as_session_root))
        row.addWidget(self._button(self.tr("Crear sesión"), self._on_create_session))
        row.addWidget(self._button(self.tr("Abrir sesión"), self._on_open_session))
        row.addWidget(self._button(self.tr("Guardar sesión"), self._on_save_session))
        grid.addLayout(row, 4, 0, 1, 3)

        self.session_active_label = QtWidgets.QLabel(self.tr("Sin sesión activa"))
        self.session_active_label.setWordWrap(True)
        self.session_active_label.setStyleSheet("font-size: 12px; color: #d8d8d8;")
        grid.addWidget(self.session_active_label, 5, 0, 1, 3)

        outer.addWidget(session_box)

        recent_box = QtWidgets.QGroupBox(self.tr("Sesiones recientes"))
        recent_grid = QtWidgets.QGridLayout(recent_box)
        self.recent_sessions_combo = QtWidgets.QComboBox()
        self.recent_sessions_combo.setMinimumContentsLength(32)
        self.recent_sessions_combo.setToolTip(self.tr("Sesiones abiertas recientemente en este equipo"))
        recent_grid.addWidget(self.recent_sessions_combo, 0, 0, 1, 2)
        recent_grid.addWidget(self._button(self.tr("Abrir reciente"), self._open_selected_recent_session), 0, 2)
        recent_grid.addWidget(self._button(self.tr("Actualizar lista"), self._refresh_recent_sessions_combo), 1, 0, 1, 3)
        outer.addWidget(recent_box)

        stats_box = QtWidgets.QGroupBox(self.tr("Resumen de sesión"))
        stats_grid = QtWidgets.QGridLayout(stats_box)
        self.session_stats_labels: dict[str, QtWidgets.QLabel] = {}
        for row_index, (key, label) in enumerate(
            [
                ("raw_images", self.tr("Imágenes RAW")),
                ("tiff_images", self.tr("Imágenes TIFF")),
                ("icc_profiles", self.tr("Perfiles ICC")),
                ("development_profiles", self.tr("Perfiles de ajuste")),
                ("raw_sidecars", self.tr("Mochilas RAW")),
                ("queue_items", self.tr("Elementos en cola")),
            ]
        ):
            value_label = QtWidgets.QLabel("0")
            value_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            value_label.setStyleSheet("font-weight: 600; color: #f0f0f0;")
            self.session_stats_labels[key] = value_label
            stats_grid.addWidget(QtWidgets.QLabel(label), row_index, 0)
            stats_grid.addWidget(value_label, row_index, 1)
        self.session_stats_updated_label = QtWidgets.QLabel(self.tr("Sin sesión activa"))
        self.session_stats_updated_label.setWordWrap(True)
        self.session_stats_updated_label.setStyleSheet("font-size: 12px; color: #d4d4d4;")
        stats_grid.addWidget(self.session_stats_updated_label, 0, 2, 3, 1)
        stats_grid.addWidget(self._button(self.tr("Actualizar estadísticas"), self._refresh_session_statistics), 3, 2)
        stats_grid.setColumnStretch(2, 1)
        outer.addWidget(stats_box)

        dirs_box = QtWidgets.QGroupBox(self.tr("Estructura persistente del proyecto"))
        dirs_grid = QtWidgets.QGridLayout(dirs_box)

        self.session_dir_charts = QtWidgets.QLineEdit("")
        self.session_dir_charts.setReadOnly(True)
        self.session_dir_raw = QtWidgets.QLineEdit("")
        self.session_dir_raw.setReadOnly(True)
        self.session_dir_profiles = QtWidgets.QLineEdit("")
        self.session_dir_profiles.setReadOnly(True)
        self.session_dir_exports = QtWidgets.QLineEdit("")
        self.session_dir_exports.setReadOnly(True)
        self.session_dir_config = QtWidgets.QLineEdit("")
        self.session_dir_config.setReadOnly(True)
        self.session_dir_work = QtWidgets.QLineEdit("")
        self.session_dir_work.setReadOnly(True)
        for directory_field in (
            self.session_dir_charts,
            self.session_dir_raw,
            self.session_dir_profiles,
            self.session_dir_exports,
            self.session_dir_config,
            self.session_dir_work,
        ):
            directory_field.setToolTip(self.tr("Ruta gestionada por la sesion"))

        dirs_grid.addWidget(QtWidgets.QLabel(self.tr("00_configuraciones")), 0, 0)
        dirs_grid.addWidget(self.session_dir_config, 0, 1)
        dirs_grid.addWidget(QtWidgets.QLabel(self.tr("01_ORG originales RAW")), 1, 0)
        dirs_grid.addWidget(self.session_dir_raw, 1, 1)
        dirs_grid.addWidget(QtWidgets.QLabel(self.tr("02_DRV derivados")), 2, 0)
        dirs_grid.addWidget(self.session_dir_exports, 2, 1)

        outer.addWidget(dirs_box)

        self._refresh_recent_sessions_combo()
        self._refresh_session_statistics()
        outer.addStretch(1)
        return tab

    def _build_tab_raw_develop(self) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.raw_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.raw_splitter.setChildrenCollapsible(True)
        self.raw_splitter.setHandleWidth(9)
        self.raw_splitter.addWidget(self._build_left_pane())
        self.raw_splitter.addWidget(self._build_center_pane())
        self.raw_splitter.addWidget(self._build_right_pane())
        self.raw_splitter.setCollapsible(0, False)
        self.raw_splitter.setSizes([260, 1180, 460])
        self.raw_splitter.setStretchFactor(0, 0)
        self.raw_splitter.setStretchFactor(1, 1)
        self.raw_splitter.setStretchFactor(2, 0)
        self.raw_splitter.splitterMoved.connect(self._on_raw_splitter_moved)
        layout.addWidget(self.raw_splitter, 1)
        return tab

    def _build_tab_profile_generation(self) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(tab)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        box = QtWidgets.QGroupBox(self.tr("Generar ICC con carta de color"))
        grid = QtWidgets.QGridLayout(box)

        self.profile_charts_dir = QtWidgets.QLineEdit(str(self._current_dir))
        self._add_path_row(grid, 0, self.tr("Carpeta de referencias colorimétricas"), self.profile_charts_dir, file_mode=False, save_mode=False, dir_mode=True)

        self.profile_chart_selection_label = QtWidgets.QLabel(self.tr("Referencias colorimétricas: todas las compatibles de la carpeta indicada"))
        self.profile_chart_selection_label.setWordWrap(True)
        self.profile_chart_selection_label.setStyleSheet("font-size: 12px; color: #d8d8d8;")
        grid.addWidget(self.profile_chart_selection_label, 1, 0, 1, 3)

        self.path_reference = QtWidgets.QLineEdit("colorchecker24_colorchecker2005_d50.json")

        grid.addWidget(QtWidgets.QLabel(self.tr("Referencia de carta")), 2, 0)
        self.reference_catalog_combo = QtWidgets.QComboBox()
        self.reference_catalog_combo.setToolTip(
            self.tr("Referencias incluidas y referencias personalizadas guardadas en la sesión.")
        )
        self.reference_catalog_combo.currentIndexChanged.connect(self._on_reference_catalog_selected)
        grid.addWidget(self.reference_catalog_combo, 2, 1, 1, 2)

        reference_buttons = QtWidgets.QHBoxLayout()
        reference_buttons.addWidget(self._button(self.tr("Importar JSON"), self._import_reference_catalog))
        reference_buttons.addWidget(self._button(self.tr("Nueva personalizada"), self._new_custom_reference_catalog))
        reference_buttons.addWidget(self._button(self.tr("Editar tabla"), self._edit_current_reference_catalog))
        reference_buttons.addWidget(self._button(self.tr("Validar"), self._validate_current_reference_catalog))
        grid.addLayout(reference_buttons, 3, 0, 1, 3)

        self._add_path_row(grid, 4, self.tr("Referencia carta JSON"), self.path_reference, file_mode=True, save_mode=False, dir_mode=False)
        self.path_reference.editingFinished.connect(self._on_reference_path_edited)

        self.reference_status_label = QtWidgets.QLabel(self.tr("Referencia de carta no validada"))
        self.reference_status_label.setWordWrap(True)
        self.reference_status_label.setStyleSheet("font-size: 12px; color: #d8d8d8;")
        grid.addWidget(self.reference_status_label, 5, 0, 1, 3)

        temp_dir = Path(tempfile.gettempdir())
        self.profile_out_path_edit = QtWidgets.QLineEdit(str(temp_dir / "camera_profile_gui.icc"))
        self.path_profile_out = self.profile_out_path_edit
        self._add_path_row(grid, 6, self.tr("Perfil ICC de entrada"), self.profile_out_path_edit, file_mode=False, save_mode=True, dir_mode=False)

        self.profile_report_out = QtWidgets.QLineEdit(str(temp_dir / "profile_report_gui.json"))
        self._hide_row_widgets(self._add_path_row(grid, 7, self.tr("Reporte perfil JSON"), self.profile_report_out, file_mode=False, save_mode=True, dir_mode=False))

        self.profile_workdir = QtWidgets.QLineEdit(str(temp_dir / "probraw_profile_work"))
        self._hide_row_widgets(self._add_path_row(grid, 8, self.tr("Directorio artefactos"), self.profile_workdir, file_mode=False, save_mode=False, dir_mode=True))

        self.develop_profile_out = QtWidgets.QLineEdit(str(temp_dir / "development_profile_gui.json"))
        self._hide_row_widgets(self._add_path_row(grid, 9, self.tr("Perfil de ajuste avanzado JSON"), self.develop_profile_out, file_mode=False, save_mode=True, dir_mode=False))

        self.calibrated_recipe_out = QtWidgets.QLineEdit(str(temp_dir / "recipe_calibrated_gui.yml"))
        self._hide_row_widgets(self._add_path_row(grid, 10, self.tr("Receta calibrada"), self.calibrated_recipe_out, file_mode=False, save_mode=True, dir_mode=False))

        grid.addWidget(QtWidgets.QLabel(self.tr("Tipo de carta")), 11, 0)
        self.profile_chart_type = QtWidgets.QComboBox()
        self.profile_chart_type.addItems(["colorchecker24", "it8"])
        grid.addWidget(self.profile_chart_type, 11, 1, 1, 2)

        grid.addWidget(QtWidgets.QLabel(self.tr("Confianza mínima")), 12, 0)
        self.profile_min_conf = QtWidgets.QDoubleSpinBox()
        self.profile_min_conf.setRange(0.0, 1.0)
        self.profile_min_conf.setSingleStep(0.05)
        self.profile_min_conf.setDecimals(2)
        self.profile_min_conf.setValue(0.35)
        grid.addWidget(self.profile_min_conf, 12, 1, 1, 2)

        self.profile_allow_fallback = QtWidgets.QCheckBox(self.tr("Permitir respaldo"))
        self.profile_allow_fallback.setChecked(False)
        grid.addWidget(self.profile_allow_fallback, 13, 1, 1, 2)

        grid.addWidget(QtWidgets.QLabel(self.tr("Formato ICC")), 14, 0)
        self.combo_profile_format = QtWidgets.QComboBox()
        self.combo_profile_format.addItems(PROFILE_FORMAT_OPTIONS)
        grid.addWidget(self.combo_profile_format, 14, 1, 1, 2)

        grid.addWidget(QtWidgets.QLabel(self.tr("Tipo de perfil ICC")), 15, 0)
        self.combo_profile_algo = QtWidgets.QComboBox()
        for label, flag in PROFILE_ALGO_OPTIONS:
            self.combo_profile_algo.addItem(self.tr(label), flag)
            self.combo_profile_algo.setItemData(
                self.combo_profile_algo.count() - 1,
                self.tr(PROFILE_ALGO_HELP.get(flag, "")),
                QtCore.Qt.ToolTipRole,
            )
        self.combo_profile_algo.setToolTip(self.tr(COLPROF_OPTIONS_HELP))
        grid.addWidget(self.combo_profile_algo, 15, 1, 1, 2)

        grid.addWidget(QtWidgets.QLabel(self.tr("Calidad colprof")), 16, 0)
        self.combo_profile_quality = QtWidgets.QComboBox()
        for label, q in PROFILE_QUALITY_OPTIONS:
            self.combo_profile_quality.addItem(self.tr(label), q)
            self.combo_profile_quality.setItemData(
                self.combo_profile_quality.count() - 1,
                self.tr(PROFILE_QUALITY_HELP.get(q, "")),
                QtCore.Qt.ToolTipRole,
            )
        self.combo_profile_quality.setCurrentIndex(1)
        self.combo_profile_quality.setToolTip(self.tr("Precision de calculo de ArgyllCMS. Medium es el equilibrio recomendado."))
        grid.addWidget(self.combo_profile_quality, 16, 1, 1, 2)

        grid.addWidget(QtWidgets.QLabel(self.tr("Args extra colprof")), 17, 0)
        self.edit_colprof_args = QtWidgets.QLineEdit("")
        self.edit_colprof_args.setPlaceholderText(self.tr("Ejemplo: -D \"Perfil Camara Museo\""))
        self.edit_colprof_args.setToolTip(self.tr(COLPROF_OPTIONS_HELP))
        colprof_args_row = QtWidgets.QHBoxLayout()
        colprof_args_row.addWidget(self.edit_colprof_args, 1)
        colprof_args_row.addWidget(self._button(self.tr("Recomendado"), self._set_recommended_colprof_args))
        grid.addLayout(colprof_args_row, 17, 1, 1, 2)

        grid.addWidget(self._info_row(self.tr("Opciones ArgyllCMS"), self.tr(COLPROF_OPTIONS_HELP)), 18, 0, 1, 3)

        label_camera = QtWidgets.QLabel(self.tr("Cámara (opcional)"))
        grid.addWidget(label_camera, 19, 0)
        self.profile_camera = QtWidgets.QLineEdit("")
        grid.addWidget(self.profile_camera, 19, 1, 1, 2)
        label_camera.hide()
        self.profile_camera.hide()

        label_lens = QtWidgets.QLabel(self.tr("Lente (opcional)"))
        grid.addWidget(label_lens, 20, 0)
        self.profile_lens = QtWidgets.QLineEdit("")
        grid.addWidget(self.profile_lens, 20, 1, 1, 2)
        label_lens.hide()
        self.profile_lens.hide()

        self._refresh_reference_catalog_combo()
        self._update_reference_status()

        outer.addWidget(box)

        manual_box = QtWidgets.QGroupBox(self.tr("Marcado manual de carta"))
        manual_layout = QtWidgets.QVBoxLayout(manual_box)
        manual_buttons = QtWidgets.QHBoxLayout()
        manual_buttons.addWidget(self._button(self.tr("Marcar en visor"), self._start_manual_chart_marking))
        manual_buttons.addWidget(self._button(self.tr("Limpiar puntos"), self._clear_manual_chart_points))
        manual_buttons.addWidget(self._button(self.tr("Guardar detección"), self._save_manual_chart_detection))
        manual_layout.addLayout(manual_buttons)
        self.manual_chart_points_label = QtWidgets.QLabel(self.tr("Puntos: 0/4"))
        self.manual_chart_points_label.setWordWrap(True)
        self.manual_chart_points_label.setStyleSheet("font-size: 12px; color: #d8d8d8;")
        manual_layout.addWidget(self.manual_chart_points_label)
        outer.addWidget(manual_box)

        row_generate = QtWidgets.QHBoxLayout()
        row_generate.addWidget(self._button(self.tr("Generar ICC con carta"), self._on_generate_profile))
        outer.addLayout(row_generate)

        self.profile_summary_label = QtWidgets.QLabel(self.tr("Sin ICC generado"))
        self.profile_summary_label.setWordWrap(True)
        self.profile_summary_label.setStyleSheet("font-size: 12px; color: #d8d8d8;")
        outer.addWidget(self.profile_summary_label)

        self.profile_output = QtWidgets.QPlainTextEdit()
        self.profile_output.setReadOnly(True)
        self.profile_output.setPlaceholderText(self.tr("Resultado JSON de la generación de perfil"))
        self.profile_output.setMaximumHeight(170)
        outer.addWidget(self.profile_output, 1)
        return tab

    def _build_development_profiles_panel(self) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(tab)

        grid.addWidget(QtWidgets.QLabel(self.tr("Perfil de ajuste activo")), 0, 0)
        self.development_profile_combo = QtWidgets.QComboBox()
        self.development_profile_combo.setToolTip(
            self.tr("Perfil de ajuste guardado. Al aplicarlo, sus parametros pasan a los controles de revelado del RAW.")
        )
        grid.addWidget(self.development_profile_combo, 0, 1, 1, 2)

        grid.addWidget(QtWidgets.QLabel(self.tr("Nombre del ajuste")), 1, 0)
        self.development_profile_name_edit = QtWidgets.QLineEdit("Perfil manual")
        grid.addWidget(self.development_profile_name_edit, 1, 1, 1, 2)

        grid.addWidget(QtWidgets.QLabel(self.tr("Espacio estándar sin carta")), 2, 0)
        self.development_output_space_combo = QtWidgets.QComboBox(tab)
        self.development_output_space_combo.setToolTip(
            self.tr(
                "Para imágenes sin carta, revela el RAW en un espacio RGB estándar real "
                "(sRGB, Adobe RGB o ProPhoto RGB) e incrusta ese perfil ICC estándar. "
                "Con carta se mantiene RGB de cámara e ICC de entrada de sesión."
            )
        )
        self.development_output_space_combo.addItem(self.tr("Carta / RGB de cámara"), "scene_linear_camera_rgb")
        self.development_output_space_combo.addItem(self.tr("sRGB estándar"), "srgb")
        self.development_output_space_combo.addItem(self.tr("Adobe RGB (1998) estándar"), "adobe_rgb")
        self.development_output_space_combo.addItem(self.tr("ProPhoto RGB estándar"), "prophoto_rgb")
        self.development_output_space_combo.currentIndexChanged.connect(self._on_development_output_space_changed)
        grid.addWidget(self.development_output_space_combo, 2, 1, 1, 2)
        output_space_label_item = grid.itemAtPosition(2, 0)
        if output_space_label_item is not None and output_space_label_item.widget() is not None:
            output_space_label_item.widget().hide()
        self.development_output_space_combo.hide()

        profile_buttons = QtWidgets.QGridLayout()
        profile_buttons.addWidget(self._button(self.tr("Guardar perfil básico"), self._save_current_development_profile), 0, 0)
        profile_buttons.addWidget(self._button(self.tr("Aplicar a controles"), self._activate_selected_development_profile), 0, 1)
        profile_buttons.addWidget(self._button(self.tr("Asignar activo a cola"), self._queue_assign_active_development_profile), 1, 0, 1, 2)
        grid.addLayout(profile_buttons, 3, 0, 1, 3)

        self.development_profile_status_label = QtWidgets.QLabel(self.tr("Sin perfiles de ajuste guardados"))
        self.development_profile_status_label.setWordWrap(True)
        self.development_profile_status_label.setStyleSheet("font-size: 12px; color: #d8d8d8;")
        grid.addWidget(self.development_profile_status_label, 4, 0, 1, 3)

        self._refresh_development_profile_combo()
        return tab

    def _build_color_management_calibration_panel(self) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        layout.addWidget(self._build_icc_workflow_decision_panel())
        layout.addWidget(self._build_icc_profile_information_panel())

        self._icc_profile_generation_section = self._build_tab_profile_generation()
        layout.addWidget(self._icc_profile_generation_section)

        self._advanced_profile_config = None
        self._icc_active_profile_section = None
        self._on_icc_workflow_choice_changed()
        layout.addStretch(1)
        return tab

    def _build_tab_queue(self) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(tab)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        queue_box = QtWidgets.QGroupBox(self.tr("Cola de imágenes para revelado"))
        queue_layout = QtWidgets.QVBoxLayout(queue_box)

        queue_actions = QtWidgets.QHBoxLayout()
        queue_actions.addWidget(self._button(self.tr("Añadir selección"), self._queue_add_selected))
        queue_actions.addWidget(self._button(self.tr("Añadir RAW de sesión"), self._queue_add_session_raws))
        queue_actions.addWidget(self._button(self.tr("Asignar perfil activo"), self._queue_assign_active_development_profile))
        queue_actions.addWidget(self._button(self.tr("Quitar seleccionados"), self._queue_remove_selected))
        queue_actions.addWidget(self._button(self.tr("Limpiar cola"), self._queue_clear))
        queue_actions.addWidget(self._button(self.tr("Revelar cola"), self._queue_process))
        queue_layout.addLayout(queue_actions)

        self.queue_status_label = QtWidgets.QLabel(self.tr("Cola vacía"))
        self.queue_status_label.setStyleSheet("font-size: 12px; color: #d8d8d8;")
        queue_layout.addWidget(self.queue_status_label)

        self.queue_table = QtWidgets.QTableWidget(0, 6)
        self.queue_table.setHorizontalHeaderLabels(
            [
                self.tr("Archivo"),
                self.tr("Perfil"),
                self.tr("Estado"),
                self.tr("Progreso"),
                self.tr("TIFF salida"),
                self.tr("Mensaje"),
            ]
        )
        self.queue_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.queue_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.queue_table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        self.queue_table.horizontalHeader().setSectionResizeMode(4, QtWidgets.QHeaderView.Stretch)
        self.queue_table.horizontalHeader().setSectionResizeMode(5, QtWidgets.QHeaderView.Stretch)
        self.queue_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.queue_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        queue_layout.addWidget(self.queue_table, 1)

        outer.addWidget(queue_box, 2)

        monitor_box = QtWidgets.QGroupBox(self.tr("Monitoreo de ejecución"))
        monitor_layout = QtWidgets.QVBoxLayout(monitor_box)

        top = QtWidgets.QHBoxLayout()
        self.monitor_status_label = QtWidgets.QLabel(self.tr("Sin tareas en ejecución"))
        self.monitor_progress = QtWidgets.QProgressBar()
        self.monitor_progress.setRange(0, 1)
        self.monitor_progress.setValue(0)
        top.addWidget(self.monitor_status_label, 1)
        top.addWidget(self.monitor_progress, 1)
        monitor_layout.addLayout(top)

        self.monitor_tasks = QtWidgets.QTableWidget(0, 4)
        self.monitor_tasks.setHorizontalHeaderLabels([self.tr("ID"), self.tr("Tarea"), self.tr("Estado"), self.tr("Detalle")])
        self.monitor_tasks.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.monitor_tasks.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)
        self.monitor_tasks.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.monitor_tasks.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        monitor_layout.addWidget(self.monitor_tasks, 1)

        self.monitor_log = QtWidgets.QPlainTextEdit()
        self.monitor_log.setReadOnly(True)
        self.monitor_log.setPlaceholderText(self.tr("Eventos y trazas de flujo"))
        monitor_layout.addWidget(self.monitor_log, 1)

        outer.addWidget(monitor_box, 2)
        return tab

    def _build_left_pane(self) -> QtWidgets.QWidget:
        pane = QtWidgets.QWidget()
        pane.setMinimumWidth(0)
        pane.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Expanding)
        layout = QtWidgets.QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._left_pane_last_open_width = 260
        self.left_tabs = PersistentSideTabWidget()
        self.left_tabs.setTabPosition(QtWidgets.QTabWidget.West)
        self.left_tabs.setDocumentMode(True)
        self.left_tabs.addTab(self._build_browser_panel(), self.tr("Explorador"))
        self.left_tabs.addTab(self._build_analysis_panel(), self.tr("Diagnóstico"))
        self.left_tabs.addTab(self._build_metadata_panel(), self.tr("Metadatos"))
        self.left_tabs.addTab(self._build_preview_log_panel(), self.tr("Log"))
        self.left_tabs.setTabToolTip(0, self.tr("Unidades, carpetas y miniaturas"))
        self.left_tabs.setTabToolTip(1, self.tr("Diagnostico de imagen, carta y muestras"))
        self.left_tabs.setTabToolTip(2, self.tr("Metadatos EXIF, GPS y C2PA"))
        self.left_tabs.setTabToolTip(3, self.tr("Trazas de previsualizacion y procesos"))
        self.left_tabs.currentChanged.connect(self._expand_left_pane_for_tab_access)
        self.left_tabs.tabBarClicked.connect(self._expand_left_pane_for_tab_access)
        layout.addWidget(self.left_tabs, 1)
        return pane

    def _left_pane_collapsed_width(self) -> int:
        if hasattr(self, "left_tabs") and hasattr(self.left_tabs, "collapsedWidth"):
            return int(self.left_tabs.collapsedWidth())
        return 40

    def _on_raw_splitter_moved(self, _pos: int, _index: int) -> None:
        if not hasattr(self, "raw_splitter"):
            return
        sizes = self.raw_splitter.sizes()
        if not sizes:
            return
        collapsed_limit = self._left_pane_collapsed_width() + 24
        if sizes[0] > collapsed_limit:
            self._left_pane_last_open_width = int(sizes[0])

    def _expand_left_pane_for_tab_access(self, _index: int = -1) -> None:
        if not hasattr(self, "raw_splitter"):
            return
        sizes = self.raw_splitter.sizes()
        if len(sizes) < 3:
            return
        collapsed_limit = self._left_pane_collapsed_width() + 24
        if sizes[0] > collapsed_limit:
            self._left_pane_last_open_width = int(sizes[0])
            return

        total = max(1, sum(sizes))
        target_left = max(260, int(getattr(self, "_left_pane_last_open_width", 260)))
        target_left = min(target_left, max(self._left_pane_collapsed_width(), total - 520))
        right = max(0, sizes[2])
        center = max(420, total - target_left - right)
        if target_left + center + right > total:
            overflow = target_left + center + right - total
            right = max(0, right - overflow)
        center = max(420, total - target_left - right)
        if target_left + center + right > total:
            target_left = max(
                self._left_pane_collapsed_width(),
                total - center - right,
            )
        self.raw_splitter.setSizes([target_left, center, right])

    def _build_browser_panel(self) -> QtWidgets.QWidget:
        box = QtWidgets.QGroupBox(self.tr("Explorador de unidades y carpetas"))
        box_layout = QtWidgets.QVBoxLayout(box)

        root_row = QtWidgets.QHBoxLayout()
        root_row.addWidget(QtWidgets.QLabel(self.tr("Unidad / raiz")))
        self.storage_root_combo = QtWidgets.QComboBox()
        self.storage_root_combo.currentIndexChanged.connect(self._on_storage_root_changed)
        root_row.addWidget(self.storage_root_combo, 1)
        root_row.addWidget(self._button(self.tr("Actualizar"), self._refresh_storage_roots))
        box_layout.addLayout(root_row)

        self.current_dir_label = QtWidgets.QLabel(self.tr(""))
        self.current_dir_label.setWordWrap(True)
        self.current_dir_label.setStyleSheet("font-size: 12px; color: #d8d8d8;")
        box_layout.addWidget(self.current_dir_label)

        self.dir_tree = QtWidgets.QTreeView()
        self.dir_tree.setHeaderHidden(True)
        self.dir_tree.setMinimumHeight(260)
        self.dir_tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.dir_tree.clicked.connect(self._on_tree_clicked)
        self.dir_tree.customContextMenuRequested.connect(self._show_directory_tree_context_menu)
        box_layout.addWidget(self.dir_tree, 1)
        return box

    def _build_histogram_header_panel(self) -> QtWidgets.QWidget:
        histogram_box = QtWidgets.QGroupBox(self.tr("Histograma RGB colorimétrico"))
        histogram_layout = QtWidgets.QVBoxLayout(histogram_box)
        histogram_layout.setContentsMargins(6, 6, 6, 6)
        histogram_layout.setSpacing(4)
        self.viewer_histogram = RGBHistogramWidget()
        self.viewer_histogram.setMaximumHeight(150)
        histogram_layout.addWidget(self.viewer_histogram, 1)
        self.check_histogram_clip_witness = QtWidgets.QCheckBox(
            self.tr("Testigos clipping")
        )
        self.check_histogram_clip_witness.setChecked(
            self._settings_bool("view/histogram_clip_witness", True)
        )
        self.check_histogram_clip_witness.setToolTip(self.tr("Marca clipping de sombras y luces sobre el histograma."))
        self.check_histogram_clip_witness.toggled.connect(self._on_histogram_clip_witness_toggled)
        self.check_image_clip_overlay = QtWidgets.QCheckBox(
            self.tr("Overlay imagen")
        )
        self.check_image_clip_overlay.setChecked(
            self._settings_bool("view/image_clip_overlay", True)
        )
        self.check_image_clip_overlay.setToolTip(
            self.tr("Muestra clipping en la imagen: azul en sombras y rojo en luces.")
        )
        self.check_image_clip_overlay.toggled.connect(self._on_image_clip_overlay_toggled)
        toggles_row = QtWidgets.QHBoxLayout()
        toggles_row.setContentsMargins(0, 0, 0, 0)
        toggles_row.addWidget(self.check_histogram_clip_witness)
        toggles_row.addWidget(self.check_image_clip_overlay)
        toggles_row.addStretch(1)
        histogram_layout.addLayout(toggles_row)
        clip_row = QtWidgets.QHBoxLayout()
        clip_row.setContentsMargins(0, 0, 0, 0)
        self.histogram_shadow_label = QtWidgets.QLabel(self.tr("Sombras: --"))
        self.histogram_shadow_label.setStyleSheet("font-size: 12px; color: #d4d4d4;")
        self.histogram_highlight_label = QtWidgets.QLabel(self.tr("Luces: --"))
        self.histogram_highlight_label.setStyleSheet("font-size: 12px; color: #d4d4d4;")
        clip_row.addWidget(self.histogram_shadow_label, 1)
        clip_row.addWidget(self.histogram_highlight_label, 1)
        histogram_layout.addLayout(clip_row)
        self.viewer_histogram.set_clip_markers_enabled(
            bool(self.check_histogram_clip_witness.isChecked())
        )
        for panel_name in ("image_result_single", "image_result_compare", "image_original_compare"):
            if hasattr(self, panel_name):
                getattr(self, panel_name).set_clip_overlay_enabled(
                    bool(self.check_image_clip_overlay.isChecked())
                )
        return histogram_box

    def _style_icon(self, standard_pixmap: str) -> QtGui.QIcon:
        pixmap = getattr(QtWidgets.QStyle, standard_pixmap, None)
        if pixmap is None:
            return QtGui.QIcon()
        return self.style().standardIcon(pixmap)

    def _text_badge_icon(self, text: str) -> QtGui.QIcon:
        pixmap = QtGui.QPixmap(56, 36)
        pixmap.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = QtCore.QRectF(3, 4, 50, 28)
        painter.setPen(QtGui.QPen(QtGui.QColor("#b3b3b3"), 1.2))
        painter.setBrush(QtGui.QColor("#303030"))
        painter.drawRoundedRect(rect, 4, 4)
        font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.GeneralFont)
        font.setBold(True)
        font.setPointSize(13)
        painter.setFont(font)
        painter.setPen(QtGui.QColor("#f7f7f7"))
        painter.drawText(rect, QtCore.Qt.AlignCenter, text)
        painter.end()
        return QtGui.QIcon(pixmap)

    def _rotate_arrow_icon(self, *, clockwise: bool) -> QtGui.QIcon:
        pixmap = QtGui.QPixmap(32, 32)
        pixmap.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        rect = QtCore.QRectF(7, 7, 18, 18)
        start_angle = 140.0 if clockwise else 40.0
        span_angle = -285.0 if clockwise else 285.0
        path = QtGui.QPainterPath()
        path.arcMoveTo(rect, start_angle)
        path.arcTo(rect, start_angle, span_angle)
        pen = QtGui.QPen(QtGui.QColor("#f7f7f7"), 2.2)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        pen.setJoinStyle(QtCore.Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawPath(path)

        end_angle = np.deg2rad(start_angle + span_angle)
        cx = rect.center().x()
        cy = rect.center().y()
        rx = rect.width() / 2.0
        ry = rect.height() / 2.0
        tip = QtCore.QPointF(cx + rx * float(np.cos(end_angle)), cy - ry * float(np.sin(end_angle)))
        tangent = np.asarray(
            [float(np.sin(end_angle)), float(np.cos(end_angle))]
            if clockwise
            else [-float(np.sin(end_angle)), -float(np.cos(end_angle))],
            dtype=np.float64,
        )
        tangent = tangent / max(1e-6, float(np.linalg.norm(tangent)))
        normal = np.asarray([-tangent[1], tangent[0]], dtype=np.float64)
        back = 5.4
        spread = 3.4
        p1 = tip - QtCore.QPointF(
            float(tangent[0] * back + normal[0] * spread),
            float(tangent[1] * back + normal[1] * spread),
        )
        p2 = tip - QtCore.QPointF(
            float(tangent[0] * back - normal[0] * spread),
            float(tangent[1] * back - normal[1] * spread),
        )
        painter.setBrush(QtGui.QColor("#f7f7f7"))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawPolygon(QtGui.QPolygonF([tip, p1, p2]))
        painter.end()
        return QtGui.QIcon(pixmap)

    def _precache_icon(self, *, one_to_one: bool = False) -> QtGui.QIcon:
        pixmap = QtGui.QPixmap(40, 32)
        pixmap.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        tile_pen = QtGui.QPen(QtGui.QColor("#b3b3b3"), 1.1)
        tile_fill = QtGui.QColor("#303030")
        painter.setPen(tile_pen)
        painter.setBrush(tile_fill)
        for row in range(2):
            for col in range(2):
                painter.drawRoundedRect(QtCore.QRectF(4 + col * 10, 5 + row * 9, 8, 7), 1.5, 1.5)

        bolt = QtGui.QPolygonF(
            [
                QtCore.QPointF(25.0, 4.0),
                QtCore.QPointF(17.5, 18.0),
                QtCore.QPointF(24.0, 18.0),
                QtCore.QPointF(20.5, 29.0),
                QtCore.QPointF(33.0, 13.5),
                QtCore.QPointF(26.0, 13.5),
            ]
        )
        painter.setPen(QtGui.QPen(QtGui.QColor("#fbbf24"), 1.0))
        painter.setBrush(QtGui.QColor("#facc15"))
        painter.drawPolygon(bolt)

        if one_to_one:
            badge_rect = QtCore.QRectF(20, 20, 18, 10)
            painter.setPen(QtGui.QPen(QtGui.QColor("#9a9a9a"), 1.0))
            painter.setBrush(QtGui.QColor("#3a3a3a"))
            painter.drawRoundedRect(badge_rect, 2, 2)
            font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.GeneralFont)
            font.setBold(True)
            font.setPointSize(6)
            painter.setFont(font)
            painter.setPen(QtGui.QColor("#f0f0f0"))
            painter.drawText(badge_rect, QtCore.Qt.AlignCenter, "1:1")

        painter.end()
        return QtGui.QIcon(pixmap)

    def _side_columns_icon(self, *, focused: bool = False) -> QtGui.QIcon:
        pixmap = QtGui.QPixmap(40, 32)
        pixmap.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        border = QtGui.QColor("#b3b3b3")
        side_fill = QtGui.QColor("#303030")
        center_fill = QtGui.QColor("#3a3a3a" if focused else "#343434")
        painter.setPen(QtGui.QPen(border, 1.1))
        painter.setBrush(side_fill)
        painter.drawRoundedRect(QtCore.QRectF(4, 6, 7, 20), 1.6, 1.6)
        painter.drawRoundedRect(QtCore.QRectF(29, 6, 7, 20), 1.6, 1.6)
        painter.setBrush(center_fill)
        painter.drawRoundedRect(QtCore.QRectF(13, 5, 14, 22), 2.0, 2.0)

        arrow_pen = QtGui.QPen(QtGui.QColor("#f7f7f7"), 1.8)
        arrow_pen.setCapStyle(QtCore.Qt.RoundCap)
        painter.setPen(arrow_pen)
        painter.setBrush(QtGui.QColor("#f7f7f7"))

        if focused:
            pairs = [
                (QtCore.QPointF(17, 16), QtCore.QPointF(9, 16)),
                (QtCore.QPointF(23, 16), QtCore.QPointF(31, 16)),
            ]
        else:
            pairs = [
                (QtCore.QPointF(8, 16), QtCore.QPointF(17, 16)),
                (QtCore.QPointF(32, 16), QtCore.QPointF(23, 16)),
            ]
        for start, end in pairs:
            painter.drawLine(start, end)
            direction = np.asarray([end.x() - start.x(), end.y() - start.y()], dtype=np.float64)
            direction = direction / max(1e-6, float(np.linalg.norm(direction)))
            normal = np.asarray([-direction[1], direction[0]], dtype=np.float64)
            back = 4.0
            spread = 2.8
            p1 = end - QtCore.QPointF(
                float(direction[0] * back + normal[0] * spread),
                float(direction[1] * back + normal[1] * spread),
            )
            p2 = end - QtCore.QPointF(
                float(direction[0] * back - normal[0] * spread),
                float(direction[1] * back - normal[1] * spread),
            )
            painter.drawPolygon(QtGui.QPolygonF([end, p1, p2]))

        painter.end()
        return QtGui.QIcon(pixmap)

    def _zoom_one_to_one_icon(self) -> QtGui.QIcon:
        pixmap = QtGui.QPixmap(44, 32)
        pixmap.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        lens_rect = QtCore.QRectF(5, 4, 18, 18)
        painter.setPen(QtGui.QPen(QtGui.QColor("#f7f7f7"), 2.0))
        painter.setBrush(QtGui.QColor("#303030"))
        painter.drawEllipse(lens_rect)
        painter.drawLine(QtCore.QPointF(19.5, 19.5), QtCore.QPointF(27.5, 27.5))

        badge_rect = QtCore.QRectF(19, 5, 22, 13)
        painter.setPen(QtGui.QPen(QtGui.QColor("#9a9a9a"), 1.0))
        painter.setBrush(QtGui.QColor("#3a3a3a"))
        painter.drawRoundedRect(badge_rect, 2, 2)
        font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.GeneralFont)
        font.setBold(True)
        font.setPointSize(7)
        painter.setFont(font)
        painter.setPen(QtGui.QColor("#f0f0f0"))
        painter.drawText(badge_rect, QtCore.Qt.AlignCenter, "1:1")

        painter.end()
        return QtGui.QIcon(pixmap)

    def _zoom_magnifier_icon(self, sign: str) -> QtGui.QIcon:
        pixmap = QtGui.QPixmap(36, 32)
        pixmap.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        lens_rect = QtCore.QRectF(5, 4, 18, 18)
        painter.setPen(QtGui.QPen(QtGui.QColor("#f7f7f7"), 2.0))
        painter.setBrush(QtGui.QColor("#303030"))
        painter.drawEllipse(lens_rect)
        painter.drawLine(QtCore.QPointF(19.5, 19.5), QtCore.QPointF(28.0, 28.0))

        painter.setPen(QtGui.QPen(QtGui.QColor("#f0f0f0"), 2.0))
        painter.drawLine(QtCore.QPointF(10.5, 13.0), QtCore.QPointF(17.5, 13.0))
        if str(sign) == "+":
            painter.drawLine(QtCore.QPointF(14.0, 9.5), QtCore.QPointF(14.0, 16.5))

        painter.end()
        return QtGui.QIcon(pixmap)

    def _toggle_side_columns_focus(self, checked: bool) -> None:
        if not hasattr(self, "raw_splitter"):
            return
        left = self.raw_splitter.widget(0)
        right = self.raw_splitter.widget(2)
        if checked:
            sizes = self.raw_splitter.sizes()
            if len(sizes) == 3 and sizes[0] > 0 and sizes[2] > 0:
                self._side_columns_saved_sizes = [int(v) for v in sizes]
            left.hide()
            right.hide()
            self._action_side_columns_focus.setIcon(self._side_columns_icon(focused=True))
            self._action_side_columns_focus.setToolTip(self.tr("Restaurar columnas laterales"))
            self._action_side_columns_focus.setStatusTip(self.tr("Restaurar columnas laterales"))
            return

        left.show()
        right.show()
        saved = getattr(self, "_side_columns_saved_sizes", None)
        if isinstance(saved, list) and len(saved) == 3:
            self.raw_splitter.setSizes([max(40, int(v)) for v in saved])
        else:
            self._reset_layout_splitters()
        self._action_side_columns_focus.setIcon(self._side_columns_icon(focused=False))
        self._action_side_columns_focus.setToolTip(self.tr("Enfocar visor ocultando columnas laterales"))
        self._action_side_columns_focus.setStatusTip(self.tr("Enfocar visor ocultando columnas laterales"))

    def _viewer_action(
        self,
        text: str,
        callback,
        *,
        icon: str | QtGui.QIcon | None = None,
        checkable: bool = False,
        checked: bool = False,
        tooltip: str | None = None,
        shortcuts: list[str] | None = None,
    ) -> QtGui.QAction:
        if isinstance(icon, QtGui.QIcon):
            icon_obj = icon
        else:
            icon_obj = self._style_icon(icon) if icon else QtGui.QIcon()
        action = QtGui.QAction(icon_obj, text, self)
        action.setCheckable(bool(checkable))
        if checkable:
            action.setChecked(bool(checked))
            action.toggled.connect(callback)
        else:
            action.triggered.connect(lambda _checked=False, cb=callback: cb())
        hint = tooltip or text
        action.setToolTip(hint)
        action.setStatusTip(hint)
        if shortcuts:
            action.setShortcuts([QtGui.QKeySequence(shortcut) for shortcut in shortcuts])
            action.setShortcutContext(QtCore.Qt.ApplicationShortcut)
            self.addAction(action)
        return action

    def _viewer_action_button(
        self,
        action: QtGui.QAction,
        *,
        text: str | None = None,
        icon_only: bool = True,
    ) -> QtWidgets.QToolButton:
        button = QtWidgets.QToolButton()
        button.setDefaultAction(action)
        button.setAutoRaise(True)
        button.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly if icon_only else QtCore.Qt.ToolButtonTextBesideIcon)
        button.setIconSize(QtCore.QSize(26, 22))
        button.setFixedHeight(30)
        button.setMinimumWidth(34)
        if text is not None:
            button.setText(text)
            action.setText(text)
            if not icon_only:
                button.setMinimumWidth(42)
        if action is getattr(self, "chk_compare", None):
            button.setIconSize(QtCore.QSize(42, 28))
            button.setMinimumWidth(48)
        return button

    def _build_viewer_toolbar(self) -> QtWidgets.QWidget:
        toolbar = QtWidgets.QFrame()
        toolbar.setFrameShape(QtWidgets.QFrame.StyledPanel)
        toolbar.setStyleSheet(
            "QFrame { background-color: #202020; border: 1px solid #4a4a4a; }"
            "QLabel { color: #d8d8d8; }"
            "QToolButton { padding: 2px 5px; }"
        )
        layout = QtWidgets.QHBoxLayout(toolbar)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(3)

        self.chk_compare = self._viewer_action(
            self.tr("Comparar original / resultado"),
            self._toggle_compare,
            icon=self._text_badge_icon("A/B"),
            checkable=True,
        )
        self.chk_apply_profile = self._viewer_action(
            self.tr("Perfil ICC de la imagen"),
            lambda _checked: self._schedule_preview_refresh(),
            icon="SP_DialogApplyButton",
            checkable=True,
            checked=True,
            tooltip=self.tr(
                "La vista usa siempre el ICC elegido para la imagen; el monitor se corrige "
                "despues con el perfil ICC del sistema."
            ),
        )
        self._action_side_columns_focus = self._viewer_action(
            self.tr("Enfocar visor"),
            self._toggle_side_columns_focus,
            icon=self._side_columns_icon(focused=False),
            checkable=True,
            tooltip=self.tr("Enfocar visor ocultando columnas laterales"),
        )
        self.action_viewer_zoom_out = self._viewer_action(
            self.tr("Reducir"),
            self._viewer_zoom_out,
            icon=self._zoom_magnifier_icon("-"),
            shortcuts=["Ctrl+-"],
        )
        self.action_viewer_zoom_in = self._viewer_action(
            self.tr("Ampliar"),
            self._viewer_zoom_in,
            icon=self._zoom_magnifier_icon("+"),
            shortcuts=["Ctrl++", "Ctrl+="],
        )
        actions = [
            self.chk_compare,
            self._action_side_columns_focus,
            self.action_viewer_zoom_out,
            self.action_viewer_zoom_in,
            self._viewer_action(self.tr("Zoom 1:1"), self._viewer_zoom_100, icon=self._zoom_one_to_one_icon()),
            self._viewer_action(self.tr("Encajar"), self._viewer_fit, icon="SP_TitleBarMaxButton"),
            self._viewer_action(self.tr("Girar izquierda"), self._viewer_rotate_left, icon=self._rotate_arrow_icon(clockwise=False)),
            self._viewer_action(self.tr("Girar derecha"), self._viewer_rotate_right, icon=self._rotate_arrow_icon(clockwise=True)),
            *self._image_adjustment_toolbar_actions(),
            self._viewer_action(
                self.tr("Caché 1:1 actual"),
                self._on_precache_selected_preview,
                icon=self._precache_icon(one_to_one=True),
                tooltip=self.tr("Cargar en caché el 100% real del RAW seleccionado"),
            ),
            self._viewer_action(
                self.tr("Caché 1:1 carpeta"),
                lambda: self._on_precache_visible_previews(full_resolution=True),
                icon=self._precache_icon(one_to_one=True),
                tooltip=self.tr("Cargar en caché el 100% real de todos los RAW visibles"),
            ),
        ]
        for index, action in enumerate(actions):
            if index in {2, 6, 8, 11}:
                separator = QtWidgets.QFrame()
                separator.setFrameShape(QtWidgets.QFrame.VLine)
                separator.setStyleSheet("color: #4a4a4a;")
                layout.addWidget(separator)
            layout.addWidget(self._viewer_action_button(action))

        self.selected_file_label = QtWidgets.QLabel(self.tr("Sin archivo seleccionado"))
        self.selected_file_label.setWordWrap(False)
        self.selected_file_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.selected_file_label.setStyleSheet("font-size: 12px; color: #d8d8d8; border: 0;")
        layout.addWidget(self.selected_file_label, 1)

        self.viewer_zoom_label = QtWidgets.QLabel(self.tr("100%"))
        self.viewer_zoom_label.setAlignment(QtCore.Qt.AlignCenter)
        self.viewer_zoom_label.setMinimumWidth(52)
        self.viewer_zoom_label.setStyleSheet("font-size: 12px; color: #d4d4d4; border: 0;")
        layout.addWidget(self.viewer_zoom_label)
        return toolbar

    def _build_analysis_panel(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)

        self.analysis_tabs = QtWidgets.QTabWidget()

        image_page = QtWidgets.QWidget()
        image_layout = QtWidgets.QVBoxLayout(image_page)
        image_layout.setContentsMargins(0, 0, 0, 0)
        self.preview_analysis = QtWidgets.QPlainTextEdit()
        self.preview_analysis.setReadOnly(True)
        self.preview_analysis.setPlaceholderText(self.tr("Sin diagnóstico de imagen"))
        self.preview_analysis.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.preview_analysis.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont))
        image_layout.addWidget(self.preview_analysis, 1)
        self.analysis_tabs.addTab(image_page, self.tr("Imagen"))

        chart_page = QtWidgets.QWidget()
        chart_layout = QtWidgets.QVBoxLayout(chart_page)
        chart_layout.setContentsMargins(0, 0, 0, 0)
        chart_layout.setSpacing(6)
        chart_header = QtWidgets.QHBoxLayout()
        chart_header.setContentsMargins(0, 0, 0, 0)
        chart_header.setSpacing(6)
        self.chart_diagnostics_summary = QtWidgets.QLabel(self.tr("Sin datos de carta"))
        self.chart_diagnostics_summary.setWordWrap(True)
        self.chart_diagnostics_summary.setStyleSheet("font-size: 12px; color: #d8d8d8;")
        chart_header.addWidget(self.chart_diagnostics_summary, 1)
        self.chart_diagnostics_refresh_button = QtWidgets.QToolButton()
        self.chart_diagnostics_refresh_button.setAutoRaise(True)
        self.chart_diagnostics_refresh_button.setIcon(self._style_icon("SP_BrowserReload"))
        self.chart_diagnostics_refresh_button.setToolTip(self.tr("Actualizar datos de carta desde el informe de perfil"))
        self.chart_diagnostics_refresh_button.clicked.connect(
            lambda _checked=False: self._refresh_chart_diagnostics_from_session(focus=True)
        )
        chart_header.addWidget(self.chart_diagnostics_refresh_button)
        chart_layout.addLayout(chart_header)
        self.chart_diagnostics_table = QtWidgets.QTableWidget(0, 9)
        self.chart_diagnostics_table.setHorizontalHeaderLabels(
            [
                self.tr("Parche"),
                "L* ref",
                "a* ref",
                "b* ref",
                "L* ICC",
                "a* ICC",
                "b* ICC",
                "DeltaE76",
                "DeltaE2000",
            ]
        )
        self.chart_diagnostics_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.chart_diagnostics_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.chart_diagnostics_table.setAlternatingRowColors(True)
        self.chart_diagnostics_table.setSortingEnabled(True)
        header = self.chart_diagnostics_table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        for column, width in enumerate((58, 70, 70, 70, 70, 70, 70, 74, 88)):
            self.chart_diagnostics_table.setColumnWidth(column, width)
        chart_layout.addWidget(self.chart_diagnostics_table, 1)
        self.analysis_tabs.addTab(chart_page, self.tr("Carta"))

        gamut_page = QtWidgets.QWidget()
        gamut_layout = QtWidgets.QVBoxLayout(gamut_page)
        gamut_layout.setContentsMargins(0, 0, 0, 0)
        gamut_layout.setSpacing(6)
        gamut_controls = QtWidgets.QGridLayout()
        gamut_controls.setContentsMargins(0, 0, 0, 0)
        gamut_controls.setHorizontalSpacing(6)
        gamut_controls.setVerticalSpacing(4)
        gamut_controls.addWidget(QtWidgets.QLabel(self.tr("Perfil A")), 0, 0)
        self.gamut_profile_a_combo = QtWidgets.QComboBox()
        self._populate_gamut_profile_combo(self.gamut_profile_a_combo, default_key="generated")
        self.gamut_profile_a_combo.currentIndexChanged.connect(self._sync_gamut_custom_controls)
        gamut_controls.addWidget(self.gamut_profile_a_combo, 0, 1)
        gamut_controls.addWidget(QtWidgets.QLabel(self.tr("Perfil B")), 0, 2)
        self.gamut_profile_b_combo = QtWidgets.QComboBox()
        self._populate_gamut_profile_combo(self.gamut_profile_b_combo, default_key="standard:srgb")
        self.gamut_profile_b_combo.currentIndexChanged.connect(self._sync_gamut_custom_controls)
        gamut_controls.addWidget(self.gamut_profile_b_combo, 0, 3)

        self.gamut_custom_a_path = QtWidgets.QLineEdit("")
        self.gamut_custom_a_label = QtWidgets.QLabel(self.tr("ICC A"))
        self.gamut_custom_a_browse = self._button(self.tr("..."), lambda: self._browse_gamut_custom_profile(self.gamut_custom_a_path))
        self.gamut_custom_a_browse.setMaximumWidth(36)
        gamut_controls.addWidget(self.gamut_custom_a_label, 1, 0)
        gamut_controls.addWidget(self.gamut_custom_a_path, 1, 1)
        gamut_controls.addWidget(self.gamut_custom_a_browse, 1, 2)
        self.gamut_custom_b_path = QtWidgets.QLineEdit("")
        self.gamut_custom_b_label = QtWidgets.QLabel(self.tr("ICC B"))
        self.gamut_custom_b_browse = self._button(self.tr("..."), lambda: self._browse_gamut_custom_profile(self.gamut_custom_b_path))
        self.gamut_custom_b_browse.setMaximumWidth(36)
        gamut_controls.addWidget(self.gamut_custom_b_label, 2, 0)
        gamut_controls.addWidget(self.gamut_custom_b_path, 2, 1)
        gamut_controls.addWidget(self.gamut_custom_b_browse, 2, 2)
        gamut_controls.setColumnStretch(1, 1)
        gamut_controls.setColumnStretch(3, 1)
        gamut_layout.addLayout(gamut_controls)

        gamut_header = QtWidgets.QHBoxLayout()
        self.gamut_status_label = QtWidgets.QLabel(self.tr("Gama 3D: sin perfil generado"))
        self.gamut_status_label.setWordWrap(True)
        self.gamut_status_label.setStyleSheet("font-size: 12px; color: #d8d8d8;")
        gamut_header.addWidget(self.gamut_status_label, 1)
        self.gamut_view_mode_combo = QtWidgets.QComboBox()
        self.gamut_view_mode_combo.addItem(self.tr("Lab 3D"), "lab3d")
        self.gamut_view_mode_combo.addItem(self.tr("Lab 2D"), "lab_xy")
        self.gamut_view_mode_combo.currentIndexChanged.connect(self._on_gamut_view_mode_changed)
        gamut_header.addWidget(self.gamut_view_mode_combo)
        gamut_header.addWidget(self._button(self.tr("Actualizar"), self._on_refresh_gamut_diagnostics))
        gamut_layout.addLayout(gamut_header)
        self.gamut_3d_widget = Gamut3DWidget()
        gamut_view_layout = QtWidgets.QHBoxLayout()
        gamut_view_layout.setContentsMargins(0, 0, 0, 0)
        gamut_view_layout.setSpacing(6)
        gamut_view_layout.addWidget(self.gamut_3d_widget, 1)
        gamut_slice_layout = QtWidgets.QVBoxLayout()
        gamut_slice_layout.setContentsMargins(0, 0, 0, 0)
        self.gamut_l_slice_label = QtWidgets.QLabel("L* 50")
        self.gamut_l_slice_label.setAlignment(QtCore.Qt.AlignCenter)
        self.gamut_l_slice_slider = QtWidgets.QSlider(QtCore.Qt.Vertical)
        self.gamut_l_slice_slider.setRange(0, 100)
        self.gamut_l_slice_slider.setSingleStep(1)
        self.gamut_l_slice_slider.setPageStep(10)
        self.gamut_l_slice_slider.setValue(50)
        self.gamut_l_slice_slider.setToolTip(self.tr("Corte de luminosidad L* para Lab 2D"))
        self.gamut_l_slice_slider.valueChanged.connect(self._on_gamut_l_slice_changed)
        gamut_slice_layout.addWidget(self.gamut_l_slice_label)
        gamut_slice_layout.addWidget(self.gamut_l_slice_slider, 1)
        gamut_view_layout.addLayout(gamut_slice_layout)
        gamut_layout.addLayout(gamut_view_layout, 1)
        self.analysis_tabs.addTab(gamut_page, self.tr("Gama 3D"))
        self._sync_gamut_custom_controls()
        self._on_gamut_view_mode_changed()

        samples_page = QtWidgets.QWidget()
        self.color_samples_page = samples_page
        samples_layout = QtWidgets.QVBoxLayout(samples_page)
        samples_layout.setContentsMargins(0, 0, 0, 0)
        samples_layout.setSpacing(6)

        samples_controls = QtWidgets.QGridLayout()
        samples_controls.setContentsMargins(0, 0, 0, 0)
        samples_controls.setHorizontalSpacing(6)
        samples_controls.setVerticalSpacing(4)
        self.btn_color_picker = QtWidgets.QPushButton(self.tr("Cuentagotas Lab"))
        self.btn_color_picker.setCheckable(True)
        self.btn_color_picker.clicked.connect(self._toggle_color_picker)
        samples_controls.addWidget(self.btn_color_picker, 0, 0)
        samples_controls.addWidget(QtWidgets.QLabel(self.tr("Matriz")), 0, 1)
        self.color_picker_matrix_combo = QtWidgets.QComboBox()
        for label, radius in (("1x1", 0), ("3x3", 1), ("5x5", 2), ("9x9", 4), ("17x17", 8)):
            self.color_picker_matrix_combo.addItem(label, radius)
        self.color_picker_matrix_combo.setCurrentIndex(2)
        self.color_picker_matrix_combo.currentIndexChanged.connect(self._on_color_picker_matrix_changed)
        samples_controls.addWidget(self.color_picker_matrix_combo, 0, 2)
        samples_controls.addWidget(QtWidgets.QLabel(self.tr("Vista")), 0, 3)
        self.color_samples_view_combo = QtWidgets.QComboBox()
        self.color_samples_view_combo.addItem(self.tr("Tabla"), "table")
        self.color_samples_view_combo.addItem(self.tr("Fichas"), "cards")
        self.color_samples_view_combo.currentIndexChanged.connect(self._on_color_samples_view_changed)
        samples_controls.addWidget(self.color_samples_view_combo, 0, 4)
        samples_controls.addWidget(QtWidgets.QLabel(self.tr("Conjunto")), 1, 0)
        self.color_sample_group_combo = QtWidgets.QComboBox()
        self.color_sample_group_combo.currentIndexChanged.connect(self._on_color_sample_group_changed)
        samples_controls.addWidget(self.color_sample_group_combo, 1, 1, 1, 2)
        samples_controls.addWidget(self._button(self.tr("Nuevo conjunto"), self._create_color_sample_group), 1, 3)
        samples_controls.addWidget(QtWidgets.QLabel(self.tr("Ref conjunto")), 2, 0)
        self.color_sample_group_reference_combo = QtWidgets.QComboBox()
        self.color_sample_group_reference_combo.currentIndexChanged.connect(self._on_color_sample_group_reference_changed)
        samples_controls.addWidget(self.color_sample_group_reference_combo, 2, 1, 1, 3)
        samples_controls.setColumnStretch(5, 1)
        samples_layout.addLayout(samples_controls)

        self.label_color_picker = QtWidgets.QLabel(self.tr("Color Lab: sin muestra"))
        self.label_color_picker.setWordWrap(True)
        self.label_color_picker.setStyleSheet("font-size: 12px; color: #d8d8d8;")
        samples_layout.addWidget(self.label_color_picker)

        precision_text = self.tr(
            "Aviso de precision: Lab, Delta E y gamut solo son fiables si esta imagen "
            "usa un ICC generado por ProbRAW; con perfiles genericos son orientativos."
        )
        self.label_color_picker_precision = QtWidgets.QLabel(precision_text)
        self.label_color_picker_precision.setVisible(False)
        self.color_picker_precision_info_button = self._info_button(self.tr("Precisión colorimétrica"), precision_text)
        samples_header = QtWidgets.QHBoxLayout()
        samples_header.setContentsMargins(0, 0, 0, 0)
        samples_header.addWidget(QtWidgets.QLabel(self.tr("Lectura colorimétrica")))
        samples_header.addStretch(1)
        samples_header.addWidget(self.color_picker_precision_info_button)
        samples_layout.addLayout(samples_header)

        self.color_samples_table = QtWidgets.QTableWidget()
        self._color_samples_table_user_resized = False
        self._color_samples_table_auto_sizing = False
        self.color_samples_table.setColumnCount(15)
        self.color_samples_table.setHorizontalHeaderLabels(
            [
                "#",
                self.tr("Conjunto"),
                self.tr("Nombre"),
                self.tr("Nota"),
                self.tr("Pos"),
                self.tr("Matriz"),
                "RGB",
                "Lab",
                "C*",
                "A",
                "B",
                self.tr("Comun"),
                "DE76 ref",
                "DE00 ref",
                "DC* ref",
            ]
        )
        self.color_samples_table.setEditTriggers(QtWidgets.QAbstractItemView.AllEditTriggers)
        self.color_samples_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.color_samples_table.setAlternatingRowColors(True)
        self.color_samples_table.verticalHeader().setVisible(False)
        self.color_samples_table.itemChanged.connect(self._on_color_sample_table_item_changed)
        self.color_samples_table.itemSelectionChanged.connect(self._sync_color_sample_overlay)
        samples_header = self.color_samples_table.horizontalHeader()
        samples_header.setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        samples_header.setStretchLastSection(False)
        samples_header.sectionResized.connect(self._on_color_samples_table_section_resized)
        self._auto_size_color_samples_table_columns(force=True)

        self.color_sample_cards_scroll = QtWidgets.QScrollArea()
        self.color_sample_cards_scroll.setWidgetResizable(True)
        self.color_sample_cards_container = QtWidgets.QWidget()
        self.color_sample_cards_layout = QtWidgets.QVBoxLayout(self.color_sample_cards_container)
        self.color_sample_cards_layout.setContentsMargins(0, 0, 0, 0)
        self.color_sample_cards_layout.setSpacing(6)
        self.color_sample_cards_scroll.setWidget(self.color_sample_cards_container)

        self.color_samples_stack = QtWidgets.QStackedWidget()
        self.color_samples_stack.addWidget(self.color_samples_table)
        self.color_samples_stack.addWidget(self.color_sample_cards_scroll)
        samples_layout.addWidget(self.color_samples_stack, 1)

        self.color_sample_gamut_widget = ColorSampleGamutWidget()
        self.color_sample_gamut_widget.setToolTip(
            self.tr("Gama visual de los conjuntos de muestras en Lab a*b*")
        )
        color_sample_gamut_row = QtWidgets.QHBoxLayout()
        color_sample_gamut_row.setContentsMargins(0, 0, 0, 0)
        color_sample_gamut_row.setSpacing(6)
        color_sample_gamut_row.addWidget(self.color_sample_gamut_widget, 1)
        self.btn_color_sample_gamut_expand = QtWidgets.QToolButton()
        self.btn_color_sample_gamut_expand.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_TitleBarMaxButton))
        self.btn_color_sample_gamut_expand.setToolTip(self.tr("Ampliar grafico de muestras Lab a*b*"))
        self.btn_color_sample_gamut_expand.clicked.connect(self._show_color_sample_gamut_dialog)
        color_sample_gamut_row.addWidget(self.btn_color_sample_gamut_expand, 0, QtCore.Qt.AlignTop)
        samples_layout.addLayout(color_sample_gamut_row)

        self.color_sample_group_table = QtWidgets.QTableWidget()
        self.color_sample_group_table.setColumnCount(15)
        self.color_sample_group_table.setHorizontalHeaderLabels(
            [
                self.tr("Conjunto"),
                "n",
                self.tr("RGB medio"),
                self.tr("Lab medio"),
                "C*",
                self.tr("Disp DE00"),
                self.tr("Max DE00"),
                self.tr("Ref"),
                self.tr("Sim %"),
                "DE76 c",
                "DE00 c",
                "DE00 min",
                "DE00 med",
                "DE00 max",
                "DC*",
            ]
        )
        self.color_sample_group_table.setToolTip(
            self.tr(
                "Sim %: porcentaje bidireccional de puntos cuyo vecino mas cercano "
                "en el otro conjunto esta a DE00 <= 3."
            )
        )
        self.color_sample_group_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.color_sample_group_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.color_sample_group_table.setAlternatingRowColors(True)
        self.color_sample_group_table.verticalHeader().setVisible(False)
        self.color_sample_group_table.setMaximumHeight(132)
        self.color_sample_group_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        samples_layout.addWidget(self.color_sample_group_table)

        color_samples_buttons = QtWidgets.QHBoxLayout()
        color_samples_buttons.addWidget(
            self._button(self.tr("Color marcador"), lambda _checked=False: self._choose_color_sample_marker_color())
        )
        color_samples_buttons.addWidget(self._button(self.tr("Eliminar seleccion"), self._delete_selected_color_picker_sample))
        color_samples_buttons.addWidget(self._button(self.tr("Limpiar tomas"), self._clear_color_picker_samples))
        samples_layout.addLayout(color_samples_buttons)
        self._refresh_color_sample_group_controls()
        self._refresh_color_sample_group_summary()
        self._refresh_color_sample_group_gamut()
        self.analysis_tabs.addTab(samples_page, self.tr("Muestras"))

        layout.addWidget(self.analysis_tabs, 1)
        return panel

    def _populate_gamut_profile_combo(self, combo: QtWidgets.QComboBox, *, default_key: str) -> None:
        current_key = str(combo.currentData() or default_key)
        items = [
            *self._managed_gamut_profile_items(),
            (self.tr("ICC elegido / salida actual"), "generated"),
            (self.tr("Monitor"), "monitor"),
            ("sRGB", "standard:srgb"),
            ("Adobe RGB (1998)", "standard:adobe_rgb"),
            ("ProPhoto RGB", "standard:prophoto_rgb"),
            (self.tr("ICC personalizado"), "custom"),
        ]
        combo.blockSignals(True)
        combo.clear()
        for label, key in items:
            combo.addItem(label, key)
        index = combo.findData(current_key)
        if index < 0:
            index = combo.findData(default_key)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    def _build_metadata_panel(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        self.metadata_file_label = QtWidgets.QLabel(self.tr("Sin archivo seleccionado"))
        self.metadata_file_label.setWordWrap(True)
        self.metadata_file_label.setStyleSheet("font-size: 12px; color: #d8d8d8;")
        layout.addWidget(self.metadata_file_label)

        actions = QtWidgets.QHBoxLayout()
        actions.addWidget(self._button(self.tr("Leer metadatos"), self._refresh_metadata_view))
        actions.addWidget(self._button(self.tr("JSON completo"), self._show_metadata_all_tab))
        layout.addLayout(actions)

        self.metadata_tabs = QtWidgets.QTabWidget()
        self.metadata_summary = self._metadata_tree_widget()
        self.metadata_exif = self._metadata_tree_widget()
        self.metadata_gps = self._metadata_tree_widget()
        self.metadata_c2pa = self._metadata_tree_widget()
        self.metadata_all = self._metadata_text_widget("JSON completo")
        self.metadata_tabs.addTab(self.metadata_summary, self.tr("Resumen"))
        self.metadata_tabs.addTab(self.metadata_exif, self.tr("EXIF"))
        self.metadata_tabs.addTab(self.metadata_gps, self.tr("GPS"))
        self.metadata_tabs.addTab(self.metadata_c2pa, self.tr("C2PA"))
        self.metadata_tabs.addTab(self.metadata_all, self.tr("Todo"))
        layout.addWidget(self.metadata_tabs, 1)
        return panel

    def _metadata_tree_widget(self) -> QtWidgets.QTreeWidget:
        tree = QtWidgets.QTreeWidget()
        tree.setHeaderLabels([self.tr("Campo"), self.tr("Valor")])
        tree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        tree.header().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        tree.setAlternatingRowColors(True)
        tree.setRootIsDecorated(True)
        tree.setUniformRowHeights(False)
        tree.setTextElideMode(QtCore.Qt.ElideMiddle)
        return tree

    def _metadata_text_widget(self, placeholder: str) -> QtWidgets.QPlainTextEdit:
        widget = QtWidgets.QPlainTextEdit()
        widget.setReadOnly(True)
        widget.setPlaceholderText(placeholder)
        widget.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        return widget

    def _build_preview_log_panel(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        self.preview_log = QtWidgets.QPlainTextEdit()
        self.preview_log.setReadOnly(True)
        self.preview_log.setPlaceholderText(self.tr("Eventos y trazas de ejecucion"))
        layout.addWidget(self.preview_log, 1)
        return panel

    def _build_thumbnails_pane(self) -> QtWidgets.QWidget:
        pane = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        toolbar = QtWidgets.QHBoxLayout()
        toolbar.setContentsMargins(4, 0, 4, 0)
        toolbar.addWidget(QtWidgets.QLabel(self.tr("Miniaturas")))
        self.thumbnail_size_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.thumbnail_size_slider.setRange(MIN_THUMBNAIL_SIZE, MAX_THUMBNAIL_SIZE)
        self.thumbnail_size_slider.setSingleStep(8)
        self.thumbnail_size_slider.setPageStep(16)
        thumbnail_size = self._thumbnail_size_from_settings()
        self.thumbnail_size_slider.setValue(thumbnail_size)
        self.thumbnail_size_slider.valueChanged.connect(self._on_thumbnail_size_changed)
        toolbar.addWidget(self.thumbnail_size_slider, 1)
        self.thumbnail_size_label = QtWidgets.QLabel(f"{thumbnail_size}px")
        self.thumbnail_size_label.setMinimumWidth(48)
        self.thumbnail_size_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        toolbar.addWidget(self.thumbnail_size_label)
        layout.addLayout(toolbar)

        self.file_list = QtWidgets.QListWidget()
        self.file_list.setViewMode(QtWidgets.QListView.IconMode)
        self.file_list.setFlow(QtWidgets.QListView.LeftToRight)
        self.file_list.setWrapping(False)
        self.file_list.setResizeMode(QtWidgets.QListView.Adjust)
        self.file_list.setMovement(QtWidgets.QListView.Static)
        self.file_list.setSpacing(2)
        self.file_list.setWordWrap(False)
        self.file_list.setTextElideMode(QtCore.Qt.ElideMiddle)
        self.file_list.setUniformItemSizes(False)
        self.file_list.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.file_list.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.file_list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.file_list.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.file_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.file_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.file_list.setStyleSheet(
            "QListWidget {"
            "background-color: #262626;"
            "border: 1px solid #4a4a4a;"
            "padding: 2px;"
            "}"
            "QListWidget::item {"
            "background-color: #242424;"
            "border: 1px solid #454545;"
            "color: #e6e6e6;"
            "margin: 0px;"
            "padding: 3px 4px;"
            "}"
            "QListWidget::item:selected {"
            "border: 2px solid #d8d8d8;"
            "background-color: #303030;"
            "}"
        )
        self.file_list.itemSelectionChanged.connect(self._on_file_selection_changed)
        self.file_list.itemDoubleClicked.connect(self._on_file_double_clicked)
        self.file_list.customContextMenuRequested.connect(self._show_file_list_context_menu)
        self.file_list.horizontalScrollBar().valueChanged.connect(self._on_thumbnail_scroll_changed)
        self._apply_thumbnail_size(thumbnail_size)
        layout.addWidget(self.file_list, 1)
        return pane

    def _thumbnail_size_from_settings(self) -> int:
        value = self._settings.value("view/thumbnail_size", DEFAULT_THUMBNAIL_SIZE)
        try:
            size = int(value)
        except (TypeError, ValueError):
            size = DEFAULT_THUMBNAIL_SIZE
        return int(np.clip(size, MIN_THUMBNAIL_SIZE, MAX_THUMBNAIL_SIZE))

    def _apply_thumbnail_size(self, size: int) -> None:
        size = int(np.clip(size, MIN_THUMBNAIL_SIZE, MAX_THUMBNAIL_SIZE))
        badge_h = self._thumbnail_badge_strip_height(size) if hasattr(self, "_thumbnail_badge_strip_height") else 0
        label_h = self._thumbnail_filename_label_height() if hasattr(self, "_thumbnail_filename_label_height") else 0
        self.file_list.setIconSize(QtCore.QSize(size, size + label_h + badge_h))
        self.file_list.setGridSize(QtCore.QSize())
        for row in range(self.file_list.count()):
            item = self.file_list.item(row)
            if item is not None and item.flags() != QtCore.Qt.NoItemFlags:
                self._apply_thumbnail_item_size_hint(item)
        if hasattr(self, "thumbnail_size_label"):
            self.thumbnail_size_label.setText(f"{size}px")

    def _on_thumbnail_size_changed(self, size: int) -> None:
        size = int(np.clip(size, MIN_THUMBNAIL_SIZE, MAX_THUMBNAIL_SIZE))
        self._settings.setValue("view/thumbnail_size", size)
        self._apply_thumbnail_size(size)
        self._refresh_color_reference_thumbnail_markers()
        self._queue_thumbnail_generation(self._file_list_paths(), delay_ms=80)

    def _build_center_pane(self) -> QtWidgets.QWidget:
        pane = QtWidgets.QWidget()
        pane.setMinimumWidth(420)
        layout = QtWidgets.QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.viewer_stack = QtWidgets.QStackedWidget()

        self.image_result_single = ImagePanel(self.tr("Resultado"))
        self.image_result_single.imageClicked.connect(self._on_result_image_click)
        self.image_result_single.sampleRegionMoved.connect(self._on_manual_chart_sample_region_moved)
        self.image_result_single.roiSelected.connect(self._on_viewer_roi_selected)
        self.image_result_single.lineSelected.connect(self._on_viewer_line_selected)
        self.image_result_single.viewTransformChanged.connect(self._on_viewer_panel_transform_changed)
        single_page = QtWidgets.QWidget()
        single_layout = QtWidgets.QVBoxLayout(single_page)
        single_layout.setContentsMargins(0, 0, 0, 0)
        single_layout.addWidget(self.image_result_single, 1)
        self.viewer_stack.addWidget(single_page)

        self.image_original_compare = ImagePanel(self.tr(""), framed=False, background="#202020")
        self.image_result_compare = ImagePanel(self.tr(""), framed=False, background="#202020")
        self.image_result_compare.imageClicked.connect(self._on_result_image_click)
        self.image_result_compare.sampleRegionMoved.connect(self._on_manual_chart_sample_region_moved)
        self.image_result_compare.roiSelected.connect(self._on_viewer_roi_selected)
        self.image_original_compare.lineSelected.connect(self._on_viewer_line_selected)
        self.image_result_compare.lineSelected.connect(self._on_viewer_line_selected)
        self.image_original_compare.viewTransformChanged.connect(self._on_viewer_panel_transform_changed)
        self.image_result_compare.viewTransformChanged.connect(self._on_viewer_panel_transform_changed)
        self.compare_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.compare_splitter.setChildrenCollapsible(True)
        self.compare_splitter.setHandleWidth(3)
        self.compare_splitter.setStyleSheet(
            "QSplitter::handle:horizontal {"
            "background-color: #1a1a1a;"
            "border-left: 1px solid #4a4a4a;"
            "border-right: 1px solid #4a4a4a;"
            "}"
        )
        self.compare_splitter.addWidget(self.image_original_compare)
        self.compare_splitter.addWidget(self.image_result_compare)
        self.compare_splitter.setSizes([560, 560])
        compare_page = QtWidgets.QWidget()
        compare_layout = QtWidgets.QVBoxLayout(compare_page)
        compare_layout.setContentsMargins(0, 0, 0, 0)
        compare_layout.setSpacing(0)
        compare_header = QtWidgets.QWidget()
        compare_header.setStyleSheet("background-color: #202020;")
        compare_header_layout = QtWidgets.QHBoxLayout(compare_header)
        compare_header_layout.setContentsMargins(0, 2, 0, 2)
        compare_header_layout.setSpacing(0)
        compare_header_layout.addStretch(1)
        before_label = QtWidgets.QLabel(self.tr("Antes"))
        after_label = QtWidgets.QLabel(self.tr("Despues"))
        for label in (before_label, after_label):
            label.setAlignment(QtCore.Qt.AlignCenter)
            label.setMinimumWidth(72)
            label.setStyleSheet(
                "QLabel {"
                "background-color: #7a7d82;"
                "color: #f7f7f7;"
                "font-size: 11px;"
                "font-weight: 600;"
                "padding: 1px 8px;"
                "border: 1px solid #8f9399;"
                "}"
            )
        compare_header_layout.addWidget(before_label, 0, QtCore.Qt.AlignHCenter)
        compare_header_layout.addWidget(after_label, 0, QtCore.Qt.AlignHCenter)
        compare_header_layout.addStretch(1)
        compare_layout.addWidget(compare_header, 0)
        compare_layout.addWidget(self.compare_splitter, 1)
        self.viewer_stack.addWidget(compare_page)
        self.viewer_stack.setCurrentIndex(0)

        self.viewer_area = QtWidgets.QWidget()
        viewer_area_layout = QtWidgets.QVBoxLayout(self.viewer_area)
        viewer_area_layout.setContentsMargins(0, 0, 0, 0)
        viewer_area_layout.setSpacing(4)
        self.viewer_toolbar = self._build_viewer_toolbar()
        viewer_area_layout.addWidget(self.viewer_toolbar, 0)
        viewer_area_layout.addWidget(self.viewer_stack, 1)

        self.viewer_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.viewer_splitter.setChildrenCollapsible(True)
        self.viewer_splitter.setHandleWidth(8)
        self.viewer_splitter.addWidget(self.viewer_area)
        self.viewer_splitter.addWidget(self._build_thumbnails_pane())
        self.viewer_splitter.setStretchFactor(0, 1)
        self.viewer_splitter.setStretchFactor(1, 0)
        self.viewer_splitter.setSizes([760, 240])
        layout.addWidget(self.viewer_splitter, 1)
        return pane

    def _build_right_pane(self) -> QtWidgets.QWidget:
        pane = QtWidgets.QWidget()
        pane.setMinimumWidth(280)
        layout = QtWidgets.QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.right_workflow_tabs = QtWidgets.QTabWidget()
        self.right_workflow_tabs.setDocumentMode(True)

        color_scroll = QtWidgets.QScrollArea()
        color_scroll.setWidgetResizable(True)
        color_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        color_scroll.setWidget(self._build_color_management_calibration_panel())
        self.right_workflow_tabs.addTab(color_scroll, self.tr("Color / calibración"))
        self.right_workflow_tabs.setTabToolTip(0, self.tr("Gestion ICC, perfiles de sesion y perfilado con carta"))

        self.config_tabs = CollapsibleToolPanel()
        self.config_tabs.addItem(self._build_tab_color_adjustments(), self.tr("Color"), expanded=True)
        self.config_tabs.addItem(self._build_tab_brightness_contrast(), self.tr("Claro"), expanded=True)
        self.config_tabs.addItem(self._build_tab_color_grading(), self.tr("Gradacion de color"), expanded=False)
        self.config_tabs.addItem(self._build_tab_libraw_color_settings(), self.tr("Revelado base"), expanded=False)
        personalized_page = QtWidgets.QWidget()
        personalized_layout = QtWidgets.QVBoxLayout(personalized_page)
        personalized_layout.setContentsMargins(0, 0, 0, 0)
        personalized_layout.setSpacing(6)
        personalized_layout.addWidget(self._build_histogram_header_panel(), 0)
        personalized_layout.addWidget(self.config_tabs, 1)
        self.right_workflow_tabs.addTab(personalized_page, self.tr("Color y contraste"))
        self.right_workflow_tabs.setTabToolTip(1, self.tr("Ajustes visuales persistentes por imagen"))

        sharpness_page = QtWidgets.QWidget()
        sharpness_layout = QtWidgets.QVBoxLayout(sharpness_page)
        sharpness_layout.setContentsMargins(0, 0, 0, 0)
        sharpness_layout.setSpacing(6)
        sharpness_layout.addWidget(self._build_mtf_analysis_panel(), 0)
        sharpness_scroll = QtWidgets.QScrollArea()
        sharpness_scroll.setWidgetResizable(True)
        sharpness_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        sharpness_scroll.setWidget(self._build_tab_preview_settings())
        sharpness_layout.addWidget(sharpness_scroll, 1)
        self.right_workflow_tabs.addTab(sharpness_page, self.tr("Nitidez"))
        self.right_workflow_tabs.setTabToolTip(2, self.tr("MTF, enfoque, ruido y aberracion cromatica"))

        self.raw_export_tabs = CollapsibleToolPanel()
        self._advanced_raw_config = self._build_tab_raw_config(self.tr("Criterios RAW globales"))
        self.raw_export_tabs.addItem(self._advanced_raw_config, self.tr("RAW Global"), expanded=True)
        self._development_profiles_panel = self._build_development_profiles_panel()
        self._development_profiles_panel.setParent(self.raw_export_tabs)
        self._development_profiles_panel.hide()
        self.raw_export_tabs.addItem(self._build_tab_batch_config(), self.tr("Exportar derivados"), expanded=True)
        self.right_workflow_tabs.addTab(self.raw_export_tabs, self.tr("RAW / exportación"))
        self.right_workflow_tabs.setTabToolTip(3, self.tr("Criterios RAW, perfiles basicos y exportacion TIFF"))

        layout.addWidget(self.right_workflow_tabs, 1)
        self.right_workflow_tabs.currentChanged.connect(self._on_mtf_context_visibility_changed)

        return pane
