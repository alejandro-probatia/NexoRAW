from __future__ import annotations

from ._imports import *  # noqa: F401,F403


class SessionStateMixin:
    def _use_current_dir_as_session_root(self) -> None:
        root = self._project_root_for_path(self._current_dir) or self._current_dir
        self.session_root_path.setText(str(root))
        self.session_name_edit.setText(root.name)
        self._populate_session_directory_fields(self._session_paths_from_root(root))
        self._refresh_session_statistics()
        self._set_status(self.tr("Raiz de sesion:") + f" {root}")

    def _on_session_root_edited(self) -> None:
        text = self.session_root_path.text().strip()
        if not text:
            return
        root = Path(text).expanduser()
        if not self.session_name_edit.text().strip() and root.name:
            self.session_name_edit.setText(root.name)
        self._populate_session_directory_fields(self._session_paths_from_root(root))
        self._refresh_session_statistics()

    def _recent_session_roots(self) -> list[Path]:
        raw = self._settings.value("session/recent_roots", "")
        values: list[str] = []
        if isinstance(raw, (list, tuple)):
            values = [str(item) for item in raw]
        elif isinstance(raw, str) and raw.strip():
            try:
                decoded = json.loads(raw)
                if isinstance(decoded, list):
                    values = [str(item) for item in decoded]
                else:
                    values = [raw]
            except Exception:
                values = [raw]

        roots: list[Path] = []
        seen: set[str] = set()
        for value in values:
            text = str(value).strip()
            if not text:
                continue
            path = Path(text).expanduser()
            try:
                resolved = path.resolve(strict=False)
            except Exception:
                resolved = path
            key = str(resolved)
            if key in seen or not session_file_path(resolved).exists():
                continue
            seen.add(key)
            roots.append(resolved)
        return roots

    def _store_recent_session_roots(self, roots: list[Path]) -> None:
        self._settings.setValue("session/recent_roots", json.dumps([str(path) for path in roots[:10]]))

    def _remember_recent_session(self, root: Path) -> None:
        try:
            resolved = Path(root).expanduser().resolve(strict=False)
        except Exception:
            resolved = Path(root).expanduser()
        roots = [resolved]
        roots.extend(path for path in self._recent_session_roots() if path != resolved)
        self._store_recent_session_roots(roots)
        self._refresh_recent_sessions_combo()

    def _refresh_recent_sessions_combo(self) -> None:
        combo = getattr(self, "recent_sessions_combo", None)
        if combo is None:
            return
        current_data = str(combo.currentData() or "")
        combo.blockSignals(True)
        combo.clear()
        roots = self._recent_session_roots()
        for root in roots:
            try:
                payload = load_session(root)
                name = str(payload.get("metadata", {}).get("name") or root.name)
            except Exception:
                name = root.name
            combo.addItem(f"{name} - {root}", str(root))
        if not roots:
            combo.addItem(self.tr("No hay sesiones recientes"), "")
        elif current_data:
            idx = combo.findData(current_data)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        combo.blockSignals(False)

    def _open_selected_recent_session(self) -> None:
        combo = getattr(self, "recent_sessions_combo", None)
        if combo is None:
            return
        root_text = str(combo.currentData() or "").strip()
        if not root_text:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("No hay una sesión reciente seleccionada."))
            return
        root = Path(root_text).expanduser()
        try:
            payload = load_session(root)
        except Exception as exc:
            QtWidgets.QMessageBox.information(
                self,
                self.tr("Info"),
                self.tr("No se pudo abrir la sesión reciente:") + f"\n{exc}",
            )
            self._refresh_recent_sessions_combo()
            return
        self._activate_session(root, payload)

    def _refresh_session_statistics(self) -> None:
        labels = getattr(self, "session_stats_labels", None)
        if not isinstance(labels, dict):
            return
        root_text = ""
        if getattr(self, "_active_session_root", None) is not None:
            root_text = str(self._active_session_root)
        elif hasattr(self, "session_root_path"):
            root_text = self.session_root_path.text().strip()

        root = Path(root_text).expanduser() if root_text else None
        stats = {
            "raw_images": 0,
            "tiff_images": 0,
            "icc_profiles": 0,
            "development_profiles": len(getattr(self, "_development_profiles", []) or []),
            "raw_sidecars": 0,
            "queue_items": len(getattr(self, "_develop_queue", []) or []),
        }

        if root is not None:
            paths = self._session_paths_from_root(root)
            stats["raw_images"] = self._count_files_with_suffixes(paths["raw"], RAW_EXTENSIONS)
            stats["tiff_images"] = self._count_files_with_suffixes(paths["exports"], {".tif", ".tiff"})
            stats["icc_profiles"] = self._count_files_with_suffixes(paths["profiles"], {".icc", ".icm"})
            stats["raw_sidecars"] = self._count_files_with_suffixes(paths["raw"], {".json"}, suffix_text=".probraw.json")

        for key, value in stats.items():
            label = labels.get(key)
            if label is not None:
                label.setText(str(int(value)))

        status_label = getattr(self, "session_stats_updated_label", None)
        if status_label is not None:
            if root is None:
                status_label.setText(self.tr("Sin sesión activa"))
            else:
                status_label.setText(self.tr("Actualizado para:") + f"\n{root}")

    def _count_files_with_suffixes(
        self,
        directory: Path,
        suffixes: set[str],
        *,
        suffix_text: str | None = None,
    ) -> int:
        try:
            base = Path(directory).expanduser()
            if not base.exists():
                return 0
            count = 0
            normalized = {str(s).lower() for s in suffixes}
            for path in base.rglob("*"):
                if not path.is_file():
                    continue
                name = path.name.lower()
                if suffix_text is not None:
                    if name.endswith(suffix_text):
                        count += 1
                elif path.suffix.lower() in normalized:
                    count += 1
            return count
        except Exception:
            return 0

    def _session_state_snapshot(self) -> dict[str, Any]:
        self._sync_session_icc_profiles_from_disk()
        chart_files, _rejected_chart_files = self._filter_profile_reference_files(self._selected_chart_files)
        active_profile = self.path_profile_active.text().strip()
        active_profile_path = Path(active_profile).expanduser() if active_profile else None
        allow_rejected = self._active_icc_profile_matches_path(active_profile_path)
        active_profile_valid = (
            active_profile_path is not None
            and self._profile_can_be_active(active_profile_path, allow_rejected=allow_rejected)
        )
        if not active_profile_valid:
            self._active_icc_profile_id = ""
        return {
            "profile_charts_dir": self.profile_charts_dir.text().strip(),
            "profile_chart_files": [str(p) for p in chart_files],
            "reference_path": self.path_reference.text().strip(),
            "profile_output_path": self.profile_out_path_edit.text().strip(),
            "profile_report_path": self.profile_report_out.text().strip(),
            "profile_workdir": self.profile_workdir.text().strip(),
            "development_profile_path": self.develop_profile_out.text().strip(),
            "calibrated_recipe_path": self.calibrated_recipe_out.text().strip(),
            "profile_chart_type": self.profile_chart_type.currentText().strip(),
            "profile_min_confidence": float(self.profile_min_conf.value()),
            "profile_allow_fallback_detection": bool(self.profile_allow_fallback.isChecked()),
            "profile_camera": self.profile_camera.text().strip(),
            "profile_lens": self.profile_lens.text().strip(),
            "recipe_path": self.path_recipe.text().strip(),
            "profile_active_path": active_profile if active_profile_valid else "",
            "icc_profiles": self._session_icc_profiles_snapshot(),
            "active_icc_profile_id": self._active_icc_profile_id if active_profile_valid else "",
            "development_profiles": list(self._development_profiles),
            "active_development_profile_id": self._active_development_profile_id,
            "color_contrast_profiles": list(getattr(self, "_color_contrast_profiles", [])),
            "active_color_contrast_profile_id": getattr(self, "_active_color_contrast_profile_id", ""),
            "detail_profiles": list(getattr(self, "_detail_profiles", [])),
            "active_detail_profile_id": getattr(self, "_active_detail_profile_id", ""),
            "raw_export_profiles": list(getattr(self, "_raw_export_profiles", [])),
            "active_raw_export_profile_id": getattr(self, "_active_raw_export_profile_id", ""),
            "batch_input_dir": self.batch_input_dir.text().strip(),
            "batch_output_dir": self.batch_out_dir.text().strip(),
            "preview_png_path": str(self._session_default_outputs()["preview"]),
            "preview_apply_profile": active_profile_valid,
            "batch_embed_profile": True,
            "batch_apply_adjustments": bool(self.batch_apply_adjustments.isChecked()),
            "tiff_compression": self._selected_tiff_compression(),
            "tiff_maxworkers": self._selected_tiff_maxworkers() or 0,
            "fast_raw_preview": False,
            "preview_max_side": 0,
            "adjustments": self._detail_adjustment_state(),
            "render_adjustments": self._render_adjustment_state(),
            "recipe": asdict(self._build_effective_recipe()),
        }

    def _default_detail_adjustment_state(self) -> dict[str, int]:
        return {
            "sharpen": 0,
            "radius": 10,
            "noise_luma": 0,
            "noise_color": 0,
            "ca_red": 0,
            "ca_blue": 0,
        }

    def _default_render_adjustment_state(self) -> dict[str, Any]:
        return {
            "illuminant": "D50 (5003 K)",
            "temperature_kelvin": 5003,
            "tint": 0.0,
            "brightness_ev": 0.0,
            "black_point": 0.0,
            "white_point": 1.0,
            "contrast": 0.0,
            "highlights": 0.0,
            "shadows": 0.0,
            "whites": 0.0,
            "blacks": 0.0,
            "midtone": 1.0,
            "vibrance": 0.0,
            "saturation": 0.0,
            "grade_shadows_hue": 240.0,
            "grade_shadows_saturation": 0.0,
            "grade_midtones_hue": 45.0,
            "grade_midtones_saturation": 0.0,
            "grade_highlights_hue": 50.0,
            "grade_highlights_saturation": 0.0,
            "grade_blending": 0.5,
            "grade_balance": 0.0,
            "tone_curve_enabled": False,
            "tone_curve_preset": "linear",
            "tone_curve_channel": "luminance",
            "tone_curve_black_point": 0.0,
            "tone_curve_white_point": 1.0,
            "tone_curve_points": [[0.0, 0.0], [1.0, 1.0]],
            "tone_curve_channel_points": {
                "luminance": [[0.0, 0.0], [1.0, 1.0]],
                "red": [[0.0, 0.0], [1.0, 1.0]],
                "green": [[0.0, 0.0], [1.0, 1.0]],
                "blue": [[0.0, 0.0], [1.0, 1.0]],
            },
            "tone_curve_channel_presets": {
                "luminance": "linear",
                "red": "linear",
                "green": "linear",
                "blue": "linear",
            },
            "libraw": {
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
            },
        }

    def _new_session_initial_state(self, root: Path, session_name: str) -> dict[str, Any]:
        paths = self._session_paths_from_root(root)
        defaults = self._session_default_outputs(paths=paths, session_name=session_name)
        return {
            "profile_charts_dir": str(paths["charts"]),
            "profile_chart_files": [],
            "reference_path": self.path_reference.text().strip(),
            "profile_output_path": str(defaults["profile_out"]),
            "profile_report_path": str(defaults["profile_report"]),
            "profile_workdir": str(defaults["workdir"]),
            "development_profile_path": str(defaults["development_profile"]),
            "calibrated_recipe_path": str(defaults["calibrated_recipe"]),
            "profile_chart_type": "colorchecker24",
            "profile_min_confidence": 0.35,
            "profile_allow_fallback_detection": False,
            "profile_camera": "",
            "profile_lens": "",
            "recipe_path": str(defaults["recipe"]),
            "profile_active_path": "",
            "icc_profiles": [],
            "active_icc_profile_id": "",
            "development_profiles": [],
            "active_development_profile_id": "",
            "color_contrast_profiles": [],
            "active_color_contrast_profile_id": "",
            "detail_profiles": [],
            "active_detail_profile_id": "",
            "raw_export_profiles": [],
            "active_raw_export_profile_id": "",
            "batch_input_dir": str(paths["raw"]),
            "batch_output_dir": str(defaults["tiff_dir"]),
            "preview_png_path": str(defaults["preview"]),
            "preview_apply_profile": False,
            "batch_embed_profile": True,
            "batch_apply_adjustments": True,
            "tiff_compression": "none",
            "tiff_maxworkers": 0,
            "fast_raw_preview": False,
            "preview_max_side": 0,
            "adjustments": self._default_detail_adjustment_state(),
            "render_adjustments": self._default_render_adjustment_state(),
            "recipe": asdict(Recipe()),
        }

    def _apply_state_to_ui_from_session(
        self,
        *,
        state: dict[str, Any],
        directories: dict[str, str],
        session_name: str,
    ) -> None:
        raw_paths = {k: Path(v) for k, v in directories.items() if isinstance(v, str)}
        session_root = raw_paths.get("root", self._active_session_root)
        if session_root is not None:
            directories = self._project_aligned_session_directories(directories, session_root)
        paths = {k: Path(v) for k, v in directories.items() if isinstance(v, str)}
        session_root = paths.get("root", session_root)
        charts_dir = self._session_state_dir_or_default(
            state.get("profile_charts_dir"),
            paths.get("charts", Path.cwd()),
            root=session_root,
        )
        if self._profile_reference_rejection_reason(charts_dir, paths=paths) is not None:
            charts_dir = paths.get("raw") or paths.get("charts") or charts_dir
        raw_dir = self._session_state_dir_or_default(
            state.get("batch_input_dir"),
            paths.get("raw", Path.cwd()),
            root=session_root,
        )
        defaults = self._session_default_outputs(paths=paths, session_name=session_name)
        raw_profiles = state.get("development_profiles")
        self._development_profiles = [
            dict(profile)
            for profile in raw_profiles
            if isinstance(profile, dict) and str(profile.get("id") or "").strip()
        ] if isinstance(raw_profiles, list) else []
        self._active_development_profile_id = str(state.get("active_development_profile_id") or "")
        self._refresh_development_profile_combo()
        self._color_contrast_profiles = [
            dict(profile)
            for profile in state.get("color_contrast_profiles", [])
            if isinstance(profile, dict) and str(profile.get("id") or "").strip()
        ] if isinstance(state.get("color_contrast_profiles"), list) else []
        self._active_color_contrast_profile_id = str(state.get("active_color_contrast_profile_id") or "")
        self._detail_profiles = [
            dict(profile)
            for profile in state.get("detail_profiles", [])
            if isinstance(profile, dict) and str(profile.get("id") or "").strip()
        ] if isinstance(state.get("detail_profiles"), list) else []
        self._active_detail_profile_id = str(state.get("active_detail_profile_id") or "")
        self._raw_export_profiles = [
            dict(profile)
            for profile in state.get("raw_export_profiles", [])
            if isinstance(profile, dict) and str(profile.get("id") or "").strip()
        ] if isinstance(state.get("raw_export_profiles"), list) else []
        self._active_raw_export_profile_id = str(state.get("active_raw_export_profile_id") or "")
        self._refresh_named_adjustment_profile_combos()
        self._load_session_icc_profiles(state, paths=paths, defaults=defaults)

        self.profile_charts_dir.setText(str(charts_dir))
        chart_files_state = state.get("profile_chart_files")
        if isinstance(chart_files_state, list):
            chart_files = [
                Path(str(p)).expanduser()
                for p in chart_files_state
                if str(p).strip() and Path(str(p)).expanduser().exists()
            ]
            if session_root is not None:
                chart_files = [p for p in chart_files if self._path_is_inside(p, session_root)]
            self._selected_chart_files, _rejected_chart_files = self._filter_profile_reference_files(
                chart_files,
                paths=paths,
            )
        else:
            self._selected_chart_files = []
        self._sync_profile_chart_selection_label()
        self.path_reference.setText(str(state.get("reference_path") or self.path_reference.text().strip()))
        self._refresh_reference_catalog_combo()
        self._update_reference_status()
        self.profile_out_path_edit.setText(
            str(
                self._session_output_path_or_default(
                    state.get("profile_output_path"),
                    defaults["profile_out"],
                    root=session_root,
                )
            )
        )
        self.path_profile_out.setText(self.profile_out_path_edit.text().strip())
        self.profile_report_out.setText(
            str(
                self._session_output_path_or_default(
                    state.get("profile_report_path"),
                    defaults["profile_report"],
                    root=session_root,
                )
            )
        )
        self.profile_workdir.setText(
            str(
                self._session_output_path_or_default(
                    state.get("profile_workdir"),
                    defaults["workdir"],
                    root=session_root,
                )
            )
        )
        self.develop_profile_out.setText(
            str(
                self._session_output_path_or_default(
                    state.get("development_profile_path"),
                    defaults["development_profile"],
                    root=session_root,
                )
            )
        )
        self.calibrated_recipe_out.setText(
            str(
                self._session_output_path_or_default(
                    state.get("calibrated_recipe_path"),
                    defaults["calibrated_recipe"],
                    root=session_root,
                )
            )
        )
        self.batch_input_dir.setText(str(raw_dir))
        self.batch_out_dir.setText(
            str(
                self._session_output_path_or_default(
                    state.get("batch_output_dir"),
                    defaults["tiff_dir"],
                    root=session_root,
                )
            )
        )
        self.path_preview_png.setText(str(defaults["preview"]))
        recipe_path = state.get("recipe_path")
        recipe_default = defaults["calibrated_recipe"] if defaults["calibrated_recipe"].exists() else defaults["recipe"]
        self.path_recipe.setText(
            str(self._session_state_path_or_default(recipe_path, recipe_default, root=session_root))
        )

        profile_active = str(state.get("profile_active_path") or "").strip()
        active_candidate: Path | None = None
        active_profile_descriptor = self._icc_profile_by_id(self._active_icc_profile_id)
        active_descriptor_path = (
            self._session_stored_path(active_profile_descriptor.get("path"))
            if active_profile_descriptor is not None
            else None
        )
        if active_descriptor_path is not None:
            active_candidate = active_descriptor_path
        elif profile_active and not self._is_legacy_temp_output_path(profile_active):
            active_candidate = Path(profile_active).expanduser()
        elif defaults["profile_out"].exists():
            active_candidate = defaults["profile_out"]

        allow_rejected_active = active_descriptor_path is not None
        if active_candidate is not None and self._profile_can_be_active(
            active_candidate,
            allow_rejected=allow_rejected_active,
        ):
            self.path_profile_active.setText(str(active_candidate))
        else:
            self.path_profile_active.clear()
            self._active_icc_profile_id = ""
        self._sync_active_icc_profile_id_from_path()
        self._refresh_profile_management_views()
        self._refresh_chart_diagnostics_from_session(focus=False)

        chart_type = str(state.get("profile_chart_type") or "colorchecker24")
        self._set_combo_text(self.profile_chart_type, chart_type)
        try:
            self.profile_min_conf.setValue(float(state.get("profile_min_confidence", 0.35)))
        except Exception:
            self.profile_min_conf.setValue(0.35)
        self.profile_allow_fallback.setChecked(bool(state.get("profile_allow_fallback_detection", False)))

        self.profile_camera.setText(str(state.get("profile_camera") or ""))
        self.profile_lens.setText(str(state.get("profile_lens") or ""))

        self.chk_apply_profile.setChecked(bool(self.path_profile_active.text().strip()))
        self.batch_embed_profile.setChecked(True)
        self.batch_apply_adjustments.setChecked(bool(state.get("batch_apply_adjustments", self.batch_apply_adjustments.isChecked())))
        if hasattr(self, "combo_tiff_compression"):
            self._set_combo_data(self.combo_tiff_compression, str(state.get("tiff_compression") or "none"))
        if hasattr(self, "spin_tiff_maxworkers"):
            try:
                self.spin_tiff_maxworkers.setValue(max(0, int(state.get("tiff_maxworkers") or 0)))
            except Exception:
                self.spin_tiff_maxworkers.setValue(0)

        try:
            self.spin_preview_max_side.setValue(0)
        except Exception:
            pass

        adjustments = state.get("adjustments") if isinstance(state.get("adjustments"), dict) else {}
        try:
            self._apply_detail_adjustment_state(adjustments)
        except Exception:
            pass

        render_adjustments = state.get("render_adjustments") if isinstance(state.get("render_adjustments"), dict) else {}
        try:
            self._apply_render_adjustment_state(render_adjustments)
        except Exception:
            pass

        recipe_payload = state.get("recipe")
        if isinstance(recipe_payload, dict):
            try:
                allowed_keys = set(Recipe.__dataclass_fields__.keys())
                filtered = {k: v for k, v in recipe_payload.items() if k in allowed_keys}
                self._apply_recipe_to_controls(Recipe(**filtered))
            except Exception:
                pass

    def _activate_session(self, root: Path, payload: dict[str, Any]) -> None:
        self._active_session_root = root.expanduser().resolve()
        self._active_session_payload = payload

        metadata = payload.get("metadata", {})
        directories = payload.get("directories", {})
        state = payload.get("state", {})
        queue = payload.get("queue", [])
        directories = self._project_aligned_session_directories(
            directories if isinstance(directories, dict) else {},
            self._active_session_root,
        )
        if isinstance(self._active_session_payload, dict):
            self._active_session_payload = dict(self._active_session_payload)
            self._active_session_payload["directories"] = directories

        session_name = str(metadata.get("name") or self._active_session_root.name)
        self.session_root_path.setText(str(self._active_session_root))
        self.session_name_edit.setText(session_name)
        self.session_illumination_edit.setText(str(metadata.get("illumination_notes") or ""))
        self.session_capture_edit.setText(str(metadata.get("capture_notes") or ""))

        if isinstance(directories, dict) and directories:
            self.session_dir_charts.setText(str(directories.get("charts") or ""))
            self.session_dir_raw.setText(str(directories.get("raw") or ""))
            self.session_dir_profiles.setText(str(directories.get("profiles") or ""))
            self.session_dir_exports.setText(str(directories.get("exports") or ""))
            self.session_dir_config.setText(str(directories.get("config") or ""))
            self.session_dir_work.setText(str(directories.get("work") or ""))
        else:
            self._populate_session_directory_fields(self._session_paths_from_root(self._active_session_root))

        self._apply_state_to_ui_from_session(
            state=state if isinstance(state, dict) else {},
            directories=directories if isinstance(directories, dict) else {},
            session_name=session_name,
        )
        self._settings.setValue("session/last_root", str(self._active_session_root))
        self._remember_recent_session(self._active_session_root)

        self._develop_queue = [
            {
                "source": str(item.get("source") or ""),
                "status": str(item.get("status") or "pending"),
                "progress": self._queue_normalized_progress(item.get("progress")),
                "output_tiff": str(item.get("output_tiff") or ""),
                "message": str(item.get("message") or ""),
                "development_profile_id": str(item.get("development_profile_id") or ""),
            }
            for item in queue
            if isinstance(item, dict) and str(item.get("source") or "").strip()
        ]
        self._refresh_queue_table()

        start_dir = self._preferred_session_start_directory(
            directories if isinstance(directories, dict) else {},
            state if isinstance(state, dict) else {},
        )
        self._set_current_directory(start_dir)

        self.session_active_label.setText(
            self.tr("Sesion activa:") + f" {session_name}\n"
            + self.tr("Raiz:") + f" {self._active_session_root}\n"
            + self.tr("Configuracion:") + f" {session_file_path(self._active_session_root)}"
        )
        self._refresh_session_statistics()
        self._set_status(self.tr("Sesion activa:") + f" {session_name}")
        self._save_active_session(silent=True)

    def _on_create_session(self) -> None:
        root_text = self.session_root_path.text().strip()
        if not root_text:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("Indica un directorio raiz para la sesion."))
            return

        root = Path(root_text).expanduser()
        existing_session = session_file_path(root)
        if existing_session.exists():
            resp = QtWidgets.QMessageBox.question(
                self,
                self.tr("Sesión existente"),
                self.tr("Ya existe una sesion en ese directorio. Sobrescribir configuracion?"),
            )
            if resp != QtWidgets.QMessageBox.Yes:
                return
        name = self.session_name_edit.text().strip() or root.name
        illumination = self.session_illumination_edit.text().strip()
        capture = self.session_capture_edit.text().strip()
        payload = create_session(
            root,
            name=name,
            illumination_notes=illumination,
            capture_notes=capture,
            state=self._new_session_initial_state(root, name),
            queue=[],
        )
        self._activate_session(root, payload)

    def _on_open_session(self) -> None:
        start = self.session_root_path.text().strip() or str(self._current_dir)
        selected = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            self.tr("Abrir sesion (directorio raiz)"),
            start,
        )
        if not selected:
            return
        root = Path(selected)
        try:
            payload = load_session(root)
        except FileNotFoundError:
            QtWidgets.QMessageBox.information(
                self,
                self.tr("Info"),
                self.tr("No se encontro configuracion de sesion en:") + f"\n{session_file_path(root)}",
            )
            return
        self._activate_session(root, payload)

    def _save_active_session(self, *, silent: bool) -> bool:
        if self._active_session_root is None and silent:
            return False

        root_text = self.session_root_path.text().strip()
        if not root_text:
            if not silent:
                QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("Define un directorio de sesion."))
            return False

        root = Path(root_text).expanduser()
        ensure_session_structure(root)

        metadata_existing = {}
        directories_existing = {}
        if isinstance(self._active_session_payload, dict):
            metadata_existing = self._active_session_payload.get("metadata", {})
            directories_existing = self._active_session_payload.get("directories", {})
        if isinstance(directories_existing, dict):
            current_root = str(directories_existing.get("root") or "")
            if current_root and Path(current_root).expanduser().resolve() != root.resolve():
                directories_existing = {}

        payload = {
            "version": 1,
            "metadata": {
                "name": self.session_name_edit.text().strip() or root.name,
                "illumination_notes": self.session_illumination_edit.text().strip(),
                "capture_notes": self.session_capture_edit.text().strip(),
                "created_at": metadata_existing.get("created_at", ""),
                "updated_at": metadata_existing.get("updated_at", ""),
            },
            "directories": directories_existing if isinstance(directories_existing, dict) else {},
            "state": self._session_state_snapshot(),
            "queue": self._develop_queue,
        }
        saved = save_session(root, payload)
        self._active_session_payload = saved
        self._active_session_root = root.resolve()
        self._settings.setValue("session/last_root", str(self._active_session_root))
        self._remember_recent_session(self._active_session_root)
        self.session_active_label.setText(
            self.tr("Sesion activa:") + f" {saved['metadata']['name']}\n"
            + self.tr("Raiz:") + f" {self._active_session_root}\n"
            + self.tr("Configuracion:") + f" {session_file_path(self._active_session_root)}"
        )
        self._refresh_session_statistics()
        if not silent:
            self._set_status(self.tr("Sesion guardada:") + f" {session_file_path(self._active_session_root)}")
        return True

    def _on_save_session(self) -> None:
        if self._active_session_root is None:
            self._on_create_session()
            return
        self._save_active_session(silent=False)
