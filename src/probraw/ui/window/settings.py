from __future__ import annotations

from ._imports import *  # noqa: F401,F403


class SettingsMixin:
    def _build_global_settings_dialog(self) -> None:
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(self.tr("Configuracion global de ProbRAW"))
        dialog.setModal(False)
        dialog.resize(760, 620)
        self.global_settings_dialog = dialog

        layout = QtWidgets.QVBoxLayout(dialog)
        intro = QtWidgets.QLabel(
            self.tr(
                "Ajustes globales de trazabilidad, C2PA, previsualizacion y gestion de color del monitor. "
                "Estos controles no modifican la imagen por si mismos; definen infraestructura de firma y visualizacion."
            )
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("font-size: 12px; color: #6b7280;")
        layout.addWidget(intro)

        self.global_settings_tabs = QtWidgets.QTabWidget()
        self.global_settings_tabs.addTab(
            self._settings_scroll_area(self._build_general_settings_panel()),
            self.tr("General"),
        )
        self.global_settings_tabs.addTab(
            self._settings_scroll_area(self._build_signature_settings_panel()),
            self.tr("Firma / C2PA"),
        )
        self.global_settings_tabs.addTab(
            self._settings_scroll_area(self._build_preview_monitor_settings_panel()),
            self.tr("Preview / monitor"),
        )
        layout.addWidget(self.global_settings_tabs, 1)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self._button(self.tr("Guardar configuracion"), self._save_global_settings))
        buttons.addWidget(self._button(self.tr("Cerrar"), dialog.hide))
        layout.addLayout(buttons)

    def _settings_scroll_area(self, widget: QtWidgets.QWidget) -> QtWidgets.QScrollArea:
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)
        return scroll

    def _build_general_settings_panel(self) -> QtWidgets.QWidget:
        from ...i18n import AUTO_LANG, detect_system_language

        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)

        lang_box = QtWidgets.QGroupBox(self.tr("Idioma"))
        lang_grid = QtWidgets.QGridLayout(lang_box)

        lang_grid.addWidget(QtWidgets.QLabel(self.tr("Idioma de la interfaz")), 0, 0)
        self.combo_app_language = QtWidgets.QComboBox()
        detected = detect_system_language()
        self.combo_app_language.addItem(
            self.tr("Sistema") + f" (Auto: {detected})", AUTO_LANG
        )
        self.combo_app_language.addItem(self.tr("Español"), "es")
        self.combo_app_language.addItem("English", "en")

        current_pref = str(self._settings.value("app/language", AUTO_LANG) or AUTO_LANG).strip().lower()
        idx = self.combo_app_language.findData(current_pref)
        self.combo_app_language.setCurrentIndex(idx if idx >= 0 else 0)
        self.combo_app_language.currentIndexChanged.connect(self._on_app_language_changed)
        lang_grid.addWidget(self.combo_app_language, 0, 1)

        lang_note = QtWidgets.QLabel(
            self.tr(
                "El cambio de idioma se aplica al reiniciar ProbRAW. No se cierra automáticamente "
                "para no perder cambios sin guardar de la sesión actual."
            )
        )
        lang_note.setWordWrap(True)
        lang_note.setStyleSheet("font-size: 12px; color: #6b7280; padding-top: 4px;")
        lang_grid.addWidget(lang_note, 1, 0, 1, 2)

        layout.addWidget(lang_box)
        layout.addStretch(1)
        return tab

    def _on_app_language_changed(self, _index: int) -> None:
        from ...i18n import AUTO_LANG

        value = self.combo_app_language.currentData()
        if not isinstance(value, str) or not value:
            value = AUTO_LANG
        previous = str(self._settings.value("app/language", AUTO_LANG) or AUTO_LANG).strip().lower()
        if value == previous:
            return
        self._settings.setValue("app/language", value)
        self._settings.sync()
        QtWidgets.QMessageBox.information(
            self,
            self.tr("Idioma actualizado"),
            self.tr("Reinicia ProbRAW para aplicar el nuevo idioma."),
        )

    def _build_signature_settings_panel(self) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)

        proof_box = QtWidgets.QGroupBox(self.tr("ProbRAW Proof"))
        proof_grid = QtWidgets.QGridLayout(proof_box)

        self.batch_proof_key_path = QtWidgets.QLineEdit(str(self._settings.value("proof/key_path") or ""))
        self._add_path_row(proof_grid, 0, self.tr("Clave privada Proof (Ed25519)"), self.batch_proof_key_path, file_mode=True, save_mode=False, dir_mode=False)

        self.batch_proof_public_key_path = QtWidgets.QLineEdit(str(self._settings.value("proof/public_key_path") or ""))
        self._add_path_row(proof_grid, 1, self.tr("Clave publica Proof"), self.batch_proof_public_key_path, file_mode=True, save_mode=False, dir_mode=False)

        proof_grid.addWidget(QtWidgets.QLabel(self.tr("Frase clave Proof")), 2, 0)
        self.batch_proof_key_passphrase = QtWidgets.QLineEdit("")
        self.batch_proof_key_passphrase.setEchoMode(QtWidgets.QLineEdit.Password)
        self.batch_proof_key_passphrase.setPlaceholderText(self.tr("No se guarda"))
        proof_grid.addWidget(self.batch_proof_key_passphrase, 2, 1, 1, 2)

        proof_grid.addWidget(QtWidgets.QLabel(self.tr("Firmante Proof")), 3, 0)
        self.batch_proof_signer_name = QtWidgets.QLineEdit(str(self._settings.value("proof/signer_name") or "ProbRAW local signer"))
        proof_grid.addWidget(self.batch_proof_signer_name, 3, 1, 1, 2)

        proof_grid.addWidget(self._button(self.tr("Generar identidad local Proof"), self._generate_local_proof_identity), 4, 0, 1, 3)

        proof_note = QtWidgets.QLabel(
            self.tr(
                "Firma autonoma obligatoria para los TIFF finales. Vincula RAW, TIFF, receta, perfil y ajustes "
                "sin depender de una autoridad central."
            )
        )
        proof_note.setWordWrap(True)
        proof_note.setStyleSheet("font-size: 12px; color: #6b7280; padding-top: 4px;")
        proof_grid.addWidget(proof_note, 5, 0, 1, 3)
        layout.addWidget(proof_box)

        c2pa_box = QtWidgets.QGroupBox(self.tr("C2PA / CAI"))
        c2pa_grid = QtWidgets.QGridLayout(c2pa_box)

        self.batch_c2pa_cert_path = QtWidgets.QLineEdit(str(self._settings.value("c2pa/cert_path") or ""))
        self._add_path_row(c2pa_grid, 0, self.tr("Certificado C2PA opcional (PEM)"), self.batch_c2pa_cert_path, file_mode=True, save_mode=False, dir_mode=False)

        self.batch_c2pa_key_path = QtWidgets.QLineEdit(str(self._settings.value("c2pa/key_path") or ""))
        self._add_path_row(c2pa_grid, 1, self.tr("Clave privada C2PA opcional"), self.batch_c2pa_key_path, file_mode=True, save_mode=False, dir_mode=False)

        c2pa_grid.addWidget(QtWidgets.QLabel(self.tr("Frase clave C2PA")), 2, 0)
        self.batch_c2pa_key_passphrase = QtWidgets.QLineEdit("")
        self.batch_c2pa_key_passphrase.setEchoMode(QtWidgets.QLineEdit.Password)
        self.batch_c2pa_key_passphrase.setPlaceholderText(self.tr("No se guarda"))
        c2pa_grid.addWidget(self.batch_c2pa_key_passphrase, 2, 1, 1, 2)

        c2pa_grid.addWidget(QtWidgets.QLabel(self.tr("Algoritmo C2PA")), 3, 0)
        self.batch_c2pa_alg = QtWidgets.QComboBox()
        self.batch_c2pa_alg.addItems(["ps256", "ps384", "es256", "es384"])
        self._set_combo_text(self.batch_c2pa_alg, str(self._settings.value("c2pa/alg") or "ps256"))
        c2pa_grid.addWidget(self.batch_c2pa_alg, 3, 1, 1, 2)

        c2pa_grid.addWidget(QtWidgets.QLabel(self.tr("Servidor TSA")), 4, 0)
        self.batch_c2pa_timestamp_url = QtWidgets.QLineEdit(
            str(self._settings.value("c2pa/timestamp_url") or DEFAULT_TIMESTAMP_URL)
        )
        c2pa_grid.addWidget(self.batch_c2pa_timestamp_url, 4, 1, 1, 2)

        c2pa_grid.addWidget(QtWidgets.QLabel(self.tr("Firmante C2PA")), 5, 0)
        self.batch_c2pa_signer_name = QtWidgets.QLineEdit(str(self._settings.value("c2pa/signer_name") or APP_NAME))
        c2pa_grid.addWidget(self.batch_c2pa_signer_name, 5, 1, 1, 2)

        c2pa_note = QtWidgets.QLabel(
            self.tr(
                "C2PA se usa automaticamente con una identidad local de laboratorio cuando no hay certificado externo. "
                "Los certificados CAI oficiales solo son necesarios si se quiere aparecer como firmante reconocido por su lista de confianza."
            )
        )
        c2pa_note.setWordWrap(True)
        c2pa_note.setStyleSheet("font-size: 12px; color: #6b7280; padding-top: 4px;")
        c2pa_grid.addWidget(c2pa_note, 6, 0, 1, 3)
        layout.addWidget(c2pa_box)

        for widget in (
            self.batch_proof_key_path,
            self.batch_proof_public_key_path,
            self.batch_proof_signer_name,
            self.batch_c2pa_cert_path,
            self.batch_c2pa_key_path,
            self.batch_c2pa_timestamp_url,
            self.batch_c2pa_signer_name,
        ):
            widget.editingFinished.connect(self._save_signature_settings)
        self.batch_c2pa_alg.currentTextChanged.connect(lambda _value: self._save_signature_settings())

        layout.addStretch(1)
        return tab

    def _build_preview_monitor_settings_panel(self) -> QtWidgets.QWidget:
        self._migrate_display_color_settings()
        tab = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(tab)

        note = QtWidgets.QLabel(
            self.tr(
                "Opciones globales de navegacion y visualizacion. La vista RAW se mantiene siempre a 100% de pixeles "
                "reales para conservar la referencia colorimetrica y de nitidez."
            )
        )
        note.setWordWrap(True)
        note.setStyleSheet("font-size: 12px; color: #6b7280; padding-bottom: 6px;")
        grid.addWidget(note, 0, 0, 1, 3)

        preview_policy = QtWidgets.QLabel(
            self.tr("Politica fija: preview RAW exacta 1:1, sin saltos automaticos de resolucion.")
        )
        preview_policy.setWordWrap(True)
        preview_policy.setStyleSheet("font-size: 12px; color: #9ca3af;")
        grid.addWidget(preview_policy, 1, 0, 1, 3)

        # Compat attribute kept for tests/legacy sessions. Policy is now fixed.
        self.check_fast_raw_preview = QtWidgets.QCheckBox(
            self.tr("Modo preview RAW rapido")
        )
        self.check_fast_raw_preview.setChecked(False)
        self.check_fast_raw_preview.setEnabled(False)
        self.check_fast_raw_preview.hide()
        grid.addWidget(self.check_fast_raw_preview, 1, 0, 1, 3)

        grid.addWidget(QtWidgets.QLabel(self.tr("Resolucion de preview")), 2, 0)
        self.preview_resolution_policy_label = QtWidgets.QLabel(
            self.tr("Fija: siempre usa la fuente completa a 100% de pixeles reales.")
        )
        self.preview_resolution_policy_label.setWordWrap(True)
        self.preview_resolution_policy_label.setStyleSheet("font-size: 12px; color: #9ca3af;")
        grid.addWidget(self.preview_resolution_policy_label, 2, 1, 1, 2)

        # Legacy backing value kept for session compatibility; no longer user-editable.
        self.spin_preview_max_side = QtWidgets.QSpinBox()
        self.spin_preview_max_side.setRange(0, 6000)
        self.spin_preview_max_side.setSingleStep(100)
        self.spin_preview_max_side.setValue(0)
        self.spin_preview_max_side.hide()

        self.check_display_color_management = QtWidgets.QCheckBox(self.tr("Gestion de color del monitor (SO/Qt)"))
        self.check_display_color_management.setToolTip(
            self.tr(
                "Siempre activo: ProbRAW obtiene el perfil ICC del monitor desde el SO/Qt "
                "cuando esta disponible y convierte la preview con LittleCMS. "
                "Los pixeles ya convertidos se entregan como RGB de dispositivo para evitar "
                "una segunda conversion del compositor. El TIFF no usa este perfil."
            )
        )
        self.check_display_color_management.setChecked(True)
        self.check_display_color_management.setEnabled(False)
        self.check_display_color_management.toggled.connect(self._on_display_color_settings_changed)
        grid.addWidget(self.check_display_color_management, 3, 0, 1, 3)

        self.check_manual_profile_override = QtWidgets.QCheckBox(
            self.tr("Override manual: usar perfil ICC especifico")
        )
        self.check_manual_profile_override.setToolTip(
            self.tr(
                "Activa para usar este ICC como destino de monitor en LittleCMS. "
                "Util para soft-proofing o cuando el SO no reporta el perfil correcto."
            )
        )
        self.check_manual_profile_override.setChecked(
            self._settings_bool("display/manual_override_enabled", False)
        )
        self.check_manual_profile_override.toggled.connect(self._on_display_color_settings_changed)
        grid.addWidget(self.check_manual_profile_override, 4, 0, 1, 3)

        self.path_display_profile = QtWidgets.QLineEdit(str(self._settings.value("display/monitor_profile") or ""), tab)
        self.path_display_profile.editingFinished.connect(self._on_display_color_settings_changed)
        self._add_path_row(grid, 5, self.tr("Perfil ICC monitor"), self.path_display_profile, file_mode=True, save_mode=False, dir_mode=False)

        display_row = QtWidgets.QHBoxLayout()
        display_row.addWidget(self._button(self.tr("Detectar"), self._detect_display_profile))
        self.display_profile_status = QtWidgets.QLabel(self.tr(""))
        self.display_profile_status.setWordWrap(True)
        self.display_profile_status.setStyleSheet("font-size: 12px; color: #6b7280;")
        display_row.addWidget(self.display_profile_status, 1)
        grid.addLayout(display_row, 6, 0, 1, 3)
        self._ensure_display_profile_if_enabled()
        self._update_display_profile_status()

        self.path_preview_png = QtWidgets.QLineEdit(str(self._session_default_outputs()["preview"]))
        self.path_preview_png.hide()
        self.path_preview_png.editingFinished.connect(self._save_preview_monitor_settings)

        self.preview_png_policy_label = QtWidgets.QLabel(
            self.tr("Exportacion PNG: se elige destino con 'Guardar preview PNG' (Guardar como...).")
        )
        self.preview_png_policy_label.setWordWrap(True)
        self.preview_png_policy_label.setStyleSheet("font-size: 12px; color: #9ca3af;")
        grid.addWidget(self.preview_png_policy_label, 7, 0, 1, 3)

        cache_row = QtWidgets.QHBoxLayout()
        cache_row.addWidget(self._button(self.tr("Limpiar cache"), self._on_clear_preview_caches))
        cache_row.addStretch(1)
        grid.addLayout(cache_row, 8, 0, 1, 3)

        grid.setRowStretch(9, 1)
        return tab

    def _migrate_display_color_settings(self) -> None:
        marker = "display/system_profile_default_v1"
        if self._settings_bool(marker, False):
            return
        detected = detect_system_display_profile()
        self._settings.setValue("display/color_management_enabled", True)
        if detected is not None and not str(self._settings.value("display/monitor_profile") or "").strip():
            self._settings.setValue("display/monitor_profile", str(detected))
        self._settings.setValue(marker, True)
        self._settings.sync()

    def _open_global_settings_dialog(self, *_args) -> None:
        if not hasattr(self, "global_settings_dialog"):
            self._build_global_settings_dialog()
        self.global_settings_dialog.show()
        self.global_settings_dialog.raise_()
        self.global_settings_dialog.activateWindow()

    def _save_preview_monitor_settings(self) -> None:
        if not hasattr(self, "path_preview_png"):
            return
        self._settings.setValue("preview/fast_raw_preview", False)
        self._settings.setValue("preview/max_side", 0)
        if hasattr(self, "check_precision_detail_preview"):
            self._settings.setValue(
                "preview/precision_detail_1to1",
                bool(self.check_precision_detail_preview.isChecked()),
            )
        self._settings.remove("preview/png_path")
        self._settings.sync()

    def _cache_dirs_for_cleanup(self) -> list[Path]:
        dirs: list[Path] = [
            self._user_disk_cache_dir("previews"),
            self._user_disk_cache_dir("raw-demosaic"),
            self._user_disk_cache_dir("thumbnails"),
        ]
        if self._active_session_root is not None:
            work_cache = self._session_paths_from_root(self._active_session_root)["work"] / "cache"
            dirs.extend(
                [
                    work_cache / "previews",
                    work_cache / "raw-demosaic",
                    work_cache / "thumbnails",
                ]
            )
        unique: list[Path] = []
        seen: set[str] = set()
        for d in dirs:
            key = str(d.resolve(strict=False))
            if key in seen:
                continue
            seen.add(key)
            unique.append(d)
        return unique

    def _on_clear_preview_caches(self) -> None:
        reply = QtWidgets.QMessageBox.question(
            self,
            self.tr("Limpiar cache"),
            self.tr(
                "Se eliminaran caches de previews y miniaturas (sesion y usuario).\n"
                "Se regeneraran cuando sea necesario.\n\n"
                "¿Continuar?"
            ),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.Yes,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return

        removed_files = 0
        removed_dirs = 0
        errors: list[str] = []
        for cache_dir in self._cache_dirs_for_cleanup():
            if not cache_dir.exists():
                continue
            try:
                removed_files += sum(1 for p in cache_dir.rglob("*") if p.is_file())
            except Exception:
                pass
            try:
                shutil.rmtree(cache_dir)
                removed_dirs += 1
            except Exception as exc:
                errors.append(f"{cache_dir}: {exc}")

        self._thumb_cache.clear()
        self._image_thumb_cache.clear()
        self._thumbnail_disk_writes_since_prune = 0
        self._invalidate_preview_cache()
        self._save_preview_monitor_settings()

        if hasattr(self, "file_list"):
            self._queue_thumbnail_generation(self._file_list_paths(), delay_ms=0)
        if self._selected_file is not None:
            self._on_load_selected(show_message=False)

        self._set_status(self.tr("Cache limpiada:") + f" {removed_dirs} " + self.tr("carpetas,") + f" {removed_files} " + self.tr("archivos."))
        self._log_preview(f"Cache limpiada ({removed_dirs} carpetas, {removed_files} archivos).")
        if errors:
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("Cache parcialmente limpiada"),
                "\n".join(errors[:6]),
            )

    def _precision_detail_preview_enabled(self) -> bool:
        checkbox = getattr(self, "check_precision_detail_preview", None)
        return bool(checkbox is not None and checkbox.isChecked())

    def _effective_preview_max_side(self) -> int:
        if bool(getattr(self, "_preview_export_parity_requested", False)):
            return 0
        if bool(getattr(self, "_viewer_full_detail_requested", False)):
            return 0
        return int(PREVIEW_AUTO_BASE_MAX_SIDE)

    def _on_precision_detail_preview_toggled(self, enabled: bool) -> None:
        self._save_preview_monitor_settings()
        if self._original_linear is not None:
            self._schedule_preview_refresh()
        if bool(enabled):
            self._set_status(self.tr("Vista exacta 1:1 activa para RAW; la imagen ya se carga con detalle real."))

    def _save_global_settings(self) -> None:
        self._save_signature_settings()
        self._save_preview_monitor_settings()
        self._on_display_color_settings_changed()
        self._set_status(self.tr("Configuracion global guardada"))

    def _save_signature_settings(self) -> None:
        self._settings.setValue("proof/key_path", self.batch_proof_key_path.text().strip())
        self._settings.setValue("proof/public_key_path", self.batch_proof_public_key_path.text().strip())
        self._settings.setValue("proof/signer_name", self.batch_proof_signer_name.text().strip() or "ProbRAW local signer")
        self._settings.remove("proof/key_passphrase")
        self._settings.setValue("c2pa/cert_path", self.batch_c2pa_cert_path.text().strip())
        self._settings.setValue("c2pa/key_path", self.batch_c2pa_key_path.text().strip())
        self._settings.setValue("c2pa/alg", self.batch_c2pa_alg.currentText().strip() or "ps256")
        self._settings.setValue("c2pa/timestamp_url", self.batch_c2pa_timestamp_url.text().strip())
        self._settings.setValue("c2pa/signer_name", self.batch_c2pa_signer_name.text().strip() or APP_NAME)
        self._settings.remove("c2pa/key_passphrase")
        self._settings.sync()

    def _save_c2pa_settings(self) -> None:
        self._save_signature_settings()

    def _generate_local_proof_identity(self) -> None:
        base = Path.home().expanduser() / ".probraw" / "proof"
        private_key = base / "probraw-proof-private.pem"
        public_key = base / "probraw-proof-public.pem"
        try:
            result = generate_ed25519_identity(
                private_key_path=private_key,
                public_key_path=public_key,
                passphrase=self.batch_proof_key_passphrase.text() or None,
                overwrite=False,
            )
        except FileExistsError:
            self.batch_proof_key_path.setText(str(private_key))
            self.batch_proof_public_key_path.setText(str(public_key))
            self._save_signature_settings()
            QtWidgets.QMessageBox.information(
                self,
                self.tr("Identidad Proof existente"),
                self.tr("Ya existe una identidad local ProbRAW Proof. Se han cargado sus rutas."),
            )
            return
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, self.tr("Error Proof"), str(exc))
            return
        self.batch_proof_key_path.setText(result["private_key"])
        self.batch_proof_public_key_path.setText(result["public_key"])
        self._save_signature_settings()
        QtWidgets.QMessageBox.information(
            self,
            self.tr("Identidad Proof generada"),
            self.tr("Clave publica SHA-256:") + f"\n{result['public_key_sha256']}",
        )

    def _technical_manifest_path_for_c2pa(self) -> Path | None:
        profile_report_text = self.profile_report_out.text().strip()
        if profile_report_text:
            profile_report = Path(profile_report_text).expanduser()
            if profile_report.exists():
                return profile_report
        if self._active_session_root is not None:
            session_path = session_file_path(self._active_session_root)
            if session_path.exists():
                return session_path
        return None

    def _session_id_for_c2pa(self) -> str | None:
        if self._active_session_root is not None:
            return str(self._active_session_root)
        try:
            session_name = self.session_name_edit.text().strip()
        except Exception:
            session_name = ""
        return session_name or None

    def _c2pa_config_from_controls(self) -> C2PASignConfig | None:
        cert_text = self.batch_c2pa_cert_path.text().strip()
        key_text = self.batch_c2pa_key_path.text().strip()
        if not cert_text and not key_text:
            return None
        if not cert_text or not key_text:
            raise RuntimeError("Configura certificado y clave privada C2PA, o deja ambos campos vacios.")

        cert_path = Path(os.path.expandvars(cert_text)).expanduser()
        key_path = Path(os.path.expandvars(key_text)).expanduser()
        if not cert_path.exists():
            raise RuntimeError(f"No existe certificado C2PA: {cert_path}")
        if not key_path.exists():
            raise RuntimeError(f"No existe clave privada C2PA: {key_path}")

        return C2PASignConfig(
            cert_path=cert_path,
            key_path=key_path,
            alg=self.batch_c2pa_alg.currentText().strip() or "ps256",
            timestamp_url=self.batch_c2pa_timestamp_url.text().strip() or None,
            signer_name=self.batch_c2pa_signer_name.text().strip() or APP_NAME,
            technical_manifest_path=self._technical_manifest_path_for_c2pa(),
            session_id=self._session_id_for_c2pa(),
            key_passphrase=self.batch_c2pa_key_passphrase.text() or None,
        )

    def _proof_config_from_controls(self) -> ProbRawProofConfig | None:
        key_text = self.batch_proof_key_path.text().strip()
        public_text = self.batch_proof_public_key_path.text().strip()
        if not key_text:
            return None
        key_path = Path(os.path.expandvars(key_text)).expanduser()
        public_path = Path(os.path.expandvars(public_text)).expanduser() if public_text else None
        if not key_path.exists():
            raise RuntimeError(f"No existe clave privada ProbRAW Proof: {key_path}")
        if public_path is not None and not public_path.exists():
            raise RuntimeError(f"No existe clave publica ProbRAW Proof: {public_path}")
        return ProbRawProofConfig(
            private_key_path=key_path,
            public_key_path=public_path,
            key_passphrase=self.batch_proof_key_passphrase.text() or None,
            signer_name=self.batch_proof_signer_name.text().strip() or "ProbRAW local signer",
            signer_id=self._session_id_for_c2pa(),
        )

    def _resolve_proof_config_for_gui(self) -> ProbRawProofConfig:
        control_config = self._proof_config_from_controls()
        if control_config is not None:
            self._save_signature_settings()
            return control_config
        return proof_config_from_environment()

    def _resolve_c2pa_config_for_gui(self) -> C2PASignConfig | None:
        control_config = self._c2pa_config_from_controls()
        if control_config is not None:
            self._save_signature_settings()
            return control_config
        return auto_c2pa_config(
            technical_manifest_path=self._technical_manifest_path_for_c2pa(),
            session_id=self._session_id_for_c2pa(),
            signer_name=self.batch_c2pa_signer_name.text().strip()
            or self.batch_proof_signer_name.text().strip()
            or APP_NAME,
            timestamp_url=self.batch_c2pa_timestamp_url.text().strip() or DEFAULT_TIMESTAMP_URL,
        )

    def _show_signature_config_error(self, exc: Exception) -> None:
        QtWidgets.QMessageBox.warning(
            self,
            self.tr("Firma forense requerida"),
            f"{exc}\n\n"
            + self.tr(
                "ProbRAW crea por defecto una identidad local Proof y una identidad C2PA local. "
                "Revisa Configuracion > Configuracion global si quieres usar credenciales propias."
            ),
        )

    def _show_c2pa_config_error(self, exc: Exception) -> None:
        self._show_signature_config_error(exc)
