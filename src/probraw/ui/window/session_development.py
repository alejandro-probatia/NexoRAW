from __future__ import annotations

from ._imports import *  # noqa: F401,F403


class SessionDevelopmentMixin:
    def _profile_timestamp(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def _icc_profile_suffixes(self) -> set[str]:
        return {str(suffix).lower() for suffix in PROFILE_FORMAT_OPTIONS}

    def _profile_file_timestamp(self, path: Path) -> str:
        try:
            return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).replace(microsecond=0).isoformat()
        except Exception:
            return self._profile_timestamp()

    def _default_icc_browse_directory(self) -> str:
        for folder in standard_profile_search_dirs():
            try:
                if folder.exists() and folder.is_dir():
                    return str(folder)
            except Exception:
                continue
        return str(self._current_dir)

    def _icc_profile_id_for_path(self, path: Path) -> str:
        stored = self._session_relative_or_absolute(path)
        digest = hashlib.sha1(stored.encode("utf-8")).hexdigest()[:12]
        slug = self._slug_for_development_profile(Path(path).stem)
        return f"icc-{slug}-{digest}"

    def _icc_profile_by_id(self, profile_id: str) -> dict[str, Any] | None:
        for profile in self._icc_profiles:
            if str(profile.get("id") or "") == profile_id:
                return profile
        return None

    def _icc_profile_by_path(self, path: Path) -> dict[str, Any] | None:
        try:
            target = path.expanduser().resolve(strict=False)
        except Exception:
            target = path.expanduser()
        for profile in self._icc_profiles:
            stored = self._session_stored_path(profile.get("path"))
            if stored is None:
                continue
            try:
                candidate = stored.expanduser().resolve(strict=False)
            except Exception:
                candidate = stored.expanduser()
            if candidate == target:
                return profile
        return None

    def _normalize_icc_profile_descriptor(self, descriptor: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(descriptor, dict):
            return None
        raw_path = (
            descriptor.get("path")
            or descriptor.get("icc_profile_path")
            or descriptor.get("profile_path")
        )
        path = self._session_stored_path(raw_path)
        if path is None or path.suffix.lower() not in self._icc_profile_suffixes() or not path.exists():
            return None

        report_path = self._session_stored_path(descriptor.get("profile_report_path"))
        development_profile_path = self._session_stored_path(descriptor.get("development_profile_path"))
        recipe_path = self._session_stored_path(descriptor.get("recipe_path"))
        status = str(descriptor.get("status") or self._profile_status_for_path(path) or "").strip().lower()
        if not status:
            status = "unknown"
        created_at = str(descriptor.get("created_at") or self._profile_file_timestamp(path))
        updated_at = str(descriptor.get("updated_at") or created_at)
        name = str(descriptor.get("name") or path.stem).strip() or path.stem

        normalized = {
            "id": str(descriptor.get("id") or self._icc_profile_id_for_path(path)),
            "name": name,
            "source": str(descriptor.get("source") or "generated"),
            "path": self._session_relative_or_absolute(path),
            "profile_report_path": self._session_relative_or_absolute(report_path) if report_path is not None else "",
            "development_profile_id": str(descriptor.get("development_profile_id") or ""),
            "development_profile_path": self._session_relative_or_absolute(development_profile_path)
            if development_profile_path is not None
            else "",
            "recipe_path": self._session_relative_or_absolute(recipe_path) if recipe_path is not None else "",
            "status": status,
            "created_at": created_at,
            "updated_at": updated_at,
        }
        return normalized

    def _sort_icc_profiles(self) -> None:
        self._icc_profiles.sort(
            key=lambda item: (
                str(item.get("created_at") or ""),
                str(item.get("name") or item.get("id") or ""),
            ),
            reverse=True,
        )

    def _coalesce_icc_profile_descriptors(self, descriptors: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_id: dict[str, dict[str, Any]] = {}
        by_path: dict[str, str] = {}
        for descriptor in descriptors:
            normalized = self._normalize_icc_profile_descriptor(descriptor)
            if normalized is None:
                continue
            profile_id = str(normalized.get("id") or "")
            path_key = str(normalized.get("path") or "")
            target_id = by_path.get(path_key, profile_id)
            if target_id in by_id:
                merged = dict(by_id[target_id])
                for key, value in normalized.items():
                    if value not in ("", None):
                        if key == "status" and value == "unknown" and merged.get("status"):
                            continue
                        if key == "created_at" and merged.get("created_at"):
                            continue
                        if key == "source" and value == "generated" and merged.get("source") not in ("", None, "generated"):
                            continue
                        merged[key] = value
                by_id[target_id] = merged
                by_path[path_key] = target_id
            else:
                by_id[profile_id] = normalized
                by_path[path_key] = profile_id
        result = list(by_id.values())
        result.sort(
            key=lambda item: (
                str(item.get("created_at") or ""),
                str(item.get("name") or item.get("id") or ""),
            ),
            reverse=True,
        )
        return result

    def _session_icc_profile_scan_descriptors(self, *, paths: dict[str, Path] | None = None) -> list[dict[str, Any]]:
        if paths is None:
            if self._active_session_root is None:
                return []
            paths = self._session_paths_from_root(self._active_session_root)
        profiles_dir = paths.get("profiles")
        if profiles_dir is None or not profiles_dir.exists():
            return []
        descriptors: list[dict[str, Any]] = []
        try:
            candidates = sorted(
                p for p in profiles_dir.iterdir()
                if p.is_file() and p.suffix.lower() in self._icc_profile_suffixes()
            )
        except Exception:
            candidates = []
        for path in candidates:
            descriptors.append(
                {
                    "name": path.stem,
                    "source": "generated",
                    "path": str(path),
                    "created_at": self._profile_file_timestamp(path),
                    "updated_at": self._profile_file_timestamp(path),
                }
            )
        return descriptors

    def _icc_profile_descriptors_from_session_state(
        self,
        state: dict[str, Any],
        *,
        paths: dict[str, Path],
        defaults: dict[str, Path],
    ) -> list[dict[str, Any]]:
        descriptors: list[dict[str, Any]] = []
        raw_profiles = state.get("icc_profiles")
        if isinstance(raw_profiles, list):
            descriptors.extend(profile for profile in raw_profiles if isinstance(profile, dict))

        for key, source in (
            ("profile_active_path", "active"),
            ("profile_output_path", "generated"),
        ):
            path = self._session_stored_path(state.get(key))
            if path is not None and path.exists():
                descriptors.append({"path": str(path), "source": source, "name": path.stem})

        if defaults["profile_out"].exists():
            descriptors.append(
                {
                    "path": str(defaults["profile_out"]),
                    "source": "generated",
                    "name": defaults["profile_out"].stem,
                }
            )

        raw_development_profiles = state.get("development_profiles")
        if isinstance(raw_development_profiles, list):
            for profile in raw_development_profiles:
                if not isinstance(profile, dict):
                    continue
                icc_path = self._session_stored_path(profile.get("icc_profile_path"))
                if icc_path is None or not icc_path.exists():
                    continue
                descriptors.append(
                    {
                        "path": str(icc_path),
                        "source": "generated",
                        "name": str(profile.get("name") or icc_path.stem),
                        "development_profile_id": str(profile.get("id") or ""),
                        "development_profile_path": str(profile.get("manifest_path") or ""),
                        "profile_report_path": str(profile.get("profile_report_path") or ""),
                        "recipe_path": str(profile.get("recipe_path") or ""),
                    }
                )

        descriptors.extend(self._session_icc_profile_scan_descriptors(paths=paths))
        return descriptors

    def _load_session_icc_profiles(
        self,
        state: dict[str, Any],
        *,
        paths: dict[str, Path],
        defaults: dict[str, Path],
    ) -> None:
        self._icc_profiles = self._coalesce_icc_profile_descriptors(
            self._icc_profile_descriptors_from_session_state(state, paths=paths, defaults=defaults)
        )
        requested_active_id = str(state.get("active_icc_profile_id") or "")
        self._active_icc_profile_id = requested_active_id if self._icc_profile_by_id(requested_active_id) else ""

    def _sync_session_icc_profiles_from_disk(self) -> None:
        descriptors = list(self._icc_profiles)
        if self._active_session_root is not None:
            descriptors.extend(self._session_icc_profile_scan_descriptors())
        active = self.path_profile_active.text().strip() if hasattr(self, "path_profile_active") else ""
        if active:
            descriptors.append({"path": active, "source": "active", "name": Path(active).stem})
        self._icc_profiles = self._coalesce_icc_profile_descriptors(descriptors)
        self._sync_active_icc_profile_id_from_path()
        self._refresh_profile_management_views()

    def _sync_active_icc_profile_id_from_path(self) -> None:
        if not hasattr(self, "path_profile_active"):
            return
        text = self.path_profile_active.text().strip()
        if not text:
            self._active_icc_profile_id = ""
            return
        path = Path(text).expanduser()
        profile = self._icc_profile_by_path(path)
        if profile is None:
            self._active_icc_profile_id = ""
            return
        if self._profile_status_for_path(path) == "rejected" and not self._active_icc_profile_matches_path(path):
            self._active_icc_profile_id = ""
            return
        self._active_icc_profile_id = str(profile.get("id") or "")

    def _session_icc_profiles_snapshot(self) -> list[dict[str, Any]]:
        return [dict(profile) for profile in self._icc_profiles]

    def _icc_profile_combo_label(self, profile: dict[str, Any]) -> str:
        name = str(profile.get("name") or profile.get("id") or "ICC")
        status = str(profile.get("status") or "").strip()
        source = str(profile.get("source") or "generated")
        suffixes = []
        if status and status != "unknown":
            suffixes.append(status)
        if source and source not in {"generated", "active"}:
            suffixes.append(source)
        if suffixes:
            return f"{name} ({', '.join(suffixes)})"
        return name

    def _refresh_icc_profile_combo(self) -> None:
        if not hasattr(self, "icc_profile_combo"):
            self._refresh_selected_icc_profile_info()
            return
        current = self._active_icc_profile_id
        self.icc_profile_combo.blockSignals(True)
        self.icc_profile_combo.clear()
        self.icc_profile_combo.addItem(self.tr("Sin perfil ICC elegido"), "")
        for profile in self._icc_profiles:
            profile_id = str(profile.get("id") or "")
            if not profile_id:
                continue
            self.icc_profile_combo.addItem(self._icc_profile_combo_label(profile), profile_id)
        index = self.icc_profile_combo.findData(current)
        self.icc_profile_combo.setCurrentIndex(index if index >= 0 else 0)
        self.icc_profile_combo.blockSignals(False)
        if hasattr(self, "icc_profile_status_label"):
            active = self._icc_profile_by_id(current)
            active_label = self._icc_profile_combo_label(active) if active is not None else self.tr("ninguno")
            self.icc_profile_status_label.setText(
                f"Perfiles ICC de sesión: {len(self._icc_profiles)} | Activo: {active_label}"
            )

        self._refresh_selected_icc_profile_info()

    def _refresh_selected_icc_profile_info(self) -> None:
        self._refresh_existing_icc_availability_label()
        self._sync_icc_workflow_choice_from_state()
        active = self._icc_profile_by_id(getattr(self, "_active_icc_profile_id", ""))
        active_label = self._icc_profile_combo_label(active) if active is not None else self.tr("ninguno")
        session_text = f"Perfiles ICC de sesion: {len(getattr(self, '_icc_profiles', []) or [])} | Activo: {active_label}"
        if hasattr(self, "icc_session_info_label"):
            self.icc_session_info_label.setText(session_text)

        label = getattr(self, "icc_selected_file_info_label", None)
        if label is None:
            return
        selected = getattr(self, "_selected_file", None)
        if selected is None:
            label.setText(self.tr("Imagen seleccionada: ninguna") + "\n" + self.tr("No hay imagen activa para comprobar ICC."))
            return
        path = Path(selected)
        if path.suffix.lower() not in RAW_EXTENSIONS:
            label.setText(
                self.tr("Imagen seleccionada:")
                + f" {path.name}\n"
                + self.tr("No es un RAW gestionado con mochila ProbRAW; no hay ICC de entrada asignable.")
            )
            return
        try:
            payload = load_raw_sidecar(path)
        except FileNotFoundError:
            label.setText(
                self.tr("Imagen seleccionada:")
                + f" {path.name}\n"
                + self.tr("Sin mochila ProbRAW. Esta imagen todavia no tiene perfil ICC asignado.")
            )
            return
        except Exception as exc:
            label.setText(
                self.tr("Imagen seleccionada:")
                + f" {path.name}\n"
                + self.tr("No se pudo leer la mochila ICC:")
                + f" {exc}"
            )
            return

        profiles = payload.get("adjustment_profiles") if isinstance(payload.get("adjustment_profiles"), dict) else {}
        icc_profile = profiles.get("icc") if isinstance(profiles, dict) else {}
        icc_name = str(icc_profile.get("name") or icc_profile.get("id") or "").strip() if isinstance(icc_profile, dict) else ""
        color = payload.get("color_management") if isinstance(payload.get("color_management"), dict) else {}
        raw_icc_path = str(color.get("icc_profile_path") or "").strip()
        icc_path = self._session_stored_path(raw_icc_path) if raw_icc_path else None
        if not icc_name and icc_path is not None:
            profile = self._icc_profile_by_path(icc_path)
            icc_name = self._icc_profile_combo_label(profile) if profile is not None else icc_path.name
        if not icc_name:
            label.setText(
                self.tr("Imagen seleccionada:")
                + f" {path.name}\n"
                + self.tr("Sin perfil ICC aplicado a esta imagen.")
            )
            return
        role = str(color.get("icc_profile_role") or "").strip()
        detail = self.tr("ICC aplicado:") + f" {icc_name}"
        if icc_path is not None:
            detail += f"\n{self.tr('Archivo ICC:')} {icc_path}"
        if role:
            detail += f"\n{self.tr('Rol:')} {role}"
        label.setText(self.tr("Imagen seleccionada:") + f" {path.name}\n" + detail)

    def _refresh_existing_icc_availability_label(self) -> None:
        label = getattr(self, "icc_existing_availability_label", None)
        if label is None:
            return
        count = len(getattr(self, "_icc_profiles", []) or [])
        if count:
            label.setText(
                self.tr("Perfiles ICC disponibles en esta sesion:")
                + f" {count}. "
                + self.tr("Seleccionar uno lo activa en la imagen actual.")
            )
        else:
            label.setText(
                self.tr("Esta sesion todavia no tiene ICC generados. Usa la opcion Generar perfil ICC o deja ProPhoto RGB por defecto.")
            )

    def _sync_icc_workflow_choice_from_state(self) -> None:
        generic = getattr(self, "radio_icc_generic", None)
        existing = getattr(self, "radio_icc_existing", None)
        generate = getattr(self, "radio_icc_generate", None)
        if generic is None or existing is None or generate is None:
            return
        has_active_icc = bool(str(getattr(self, "_active_icc_profile_id", "") or "").strip())
        if not has_active_icc and hasattr(self, "path_profile_active"):
            raw_path = self.path_profile_active.text().strip()
            if raw_path:
                path = Path(raw_path).expanduser()
                allow_rejected = self._active_icc_profile_matches_path(path)
                has_active_icc = path.exists() and self._profile_can_be_active(path, allow_rejected=allow_rejected)
        generic.blockSignals(True)
        existing.blockSignals(True)
        generate.blockSignals(True)
        keep_generate = bool(generate.isChecked()) and not has_active_icc
        generate.setChecked(keep_generate)
        existing.setChecked(has_active_icc)
        generic.setChecked(not has_active_icc and not keep_generate)
        generic.blockSignals(False)
        existing.blockSignals(False)
        generate.blockSignals(False)
        self._on_icc_workflow_choice_changed()

    def _on_icc_workflow_choice_changed(self) -> None:
        generic = bool(getattr(getattr(self, "radio_icc_generic", None), "isChecked", lambda: True)())
        generate = bool(getattr(getattr(self, "radio_icc_generate", None), "isChecked", lambda: False)())
        existing = bool(getattr(getattr(self, "radio_icc_existing", None), "isChecked", lambda: False)())
        has_session_profiles = bool(getattr(self, "_icc_profiles", []) or [])
        combo = getattr(self, "combo_generic_icc_space", None)
        if combo is not None:
            combo.setEnabled(generic)
        session_combo = getattr(self, "icc_profile_combo", None)
        if session_combo is not None:
            session_combo.setEnabled(existing or has_session_profiles)
        status_label = getattr(self, "icc_profile_status_label", None)
        if status_label is not None:
            status_label.setEnabled(existing or has_session_profiles)
        generation_section = getattr(self, "_icc_profile_generation_section", None)
        if generation_section is not None:
            generation_section.setEnabled(generate)
        active_section = getattr(self, "_icc_active_profile_section", None)
        if active_section is not None:
            active_section.setEnabled(existing or generate)
        label = getattr(self, "icc_workflow_decision_label", None)
        if label is not None:
            if generic:
                label.setText(
                    self.tr(
                        "Perfil ICC RGB estandar: sRGB, Adobe RGB o ProPhoto RGB. "
                        "ProPhoto RGB se usa por defecto si no eliges otro perfil."
                    )
                )
            elif existing:
                count = len(getattr(self, "_icc_profiles", []) or [])
                if count:
                    label.setText(
                        self.tr(
                            "Perfiles de sesion: selecciona un ICC generado o registrado "
                            "en esta sesion para activarlo en la imagen."
                        )
                    )
                else:
                    label.setText(
                        self.tr(
                            "No hay ICC de sesion todavia. Mientras tanto se usa ProPhoto RGB "
                            "como perfil ICC RGB estandar."
                        )
                    )
            else:
                label.setText(
                    self.tr(
                        "Generar perfil ICC: selecciona la carta de color y crea un ICC "
                        "que quedara disponible en los perfiles de la sesion."
                    )
                )

    def _on_session_icc_profile_selected(self) -> None:
        combo = getattr(self, "icc_profile_combo", None)
        if combo is None:
            return
        profile_id = str(combo.currentData() or "")
        if not profile_id:
            return
        existing = getattr(self, "radio_icc_existing", None)
        if existing is not None and not existing.isChecked():
            existing.setChecked(True)
        if not self._activate_icc_profile_id(profile_id, save=True, refresh_preview=True, allow_rejected=True):
            self._refresh_icc_profile_combo()
            return
        self._auto_apply_current_icc_choice_to_selected_image()
        profile = self._icc_profile_by_id(profile_id)
        path = self._session_stored_path(profile.get("path")) if profile else None
        status = self._profile_status_for_path(path) if path is not None else ""
        if status == "rejected":
            self._log_preview(
                self.tr("Perfil ICC activado manualmente pese a estado QA rejected:") + f" {path}"
            )
            self._set_status(
                self.tr("Perfil ICC de sesion activo manualmente (QA rejected):")
                + f" {self._icc_profile_combo_label(profile) if profile else profile_id}"
            )
        else:
            self._set_status(
                self.tr("Perfil ICC de sesion activo:")
                + f" {self._icc_profile_combo_label(profile) if profile else profile_id}"
            )

    def _apply_generic_icc_workflow_to_controls(self) -> None:
        combo = getattr(self, "combo_generic_icc_space", None)
        output_space = str(combo.currentData() or "prophoto_rgb") if combo is not None else "prophoto_rgb"
        self._invalidate_preview_cache()
        output_change_handled = False
        if hasattr(self, "combo_output_space"):
            self.combo_output_space.blockSignals(True)
            self._set_combo_text(self.combo_output_space, output_space)
            self.combo_output_space.blockSignals(False)
            self._on_output_space_changed()
            output_change_handled = True
        self._clear_active_input_profile_for_unconfigured_file()
        if hasattr(self, "radio_icc_generic"):
            self.radio_icc_generic.setChecked(True)
        if not output_change_handled:
            self._reload_preview_source_for_color_management()
        self._auto_apply_current_icc_choice_to_selected_image()
        self._set_status(self.tr("Perfil ICC RGB estandar activo:") + f" {output_space}")

    def _set_camera_rgb_output_for_session_icc(self) -> None:
        if not hasattr(self, "combo_output_space"):
            return
        self.combo_output_space.blockSignals(True)
        self._set_combo_text(self.combo_output_space, "scene_linear_camera_rgb")
        self.combo_output_space.blockSignals(False)
        self._sync_development_output_space_combo("scene_linear_camera_rgb")
        self._apply_output_space_defaults_to_controls("scene_linear_camera_rgb")

    def _reload_preview_source_for_color_management(self) -> None:
        if getattr(self, "_original_linear", None) is None:
            return
        selected = getattr(self, "_selected_file", None)
        if selected is None or Path(selected).suffix.lower() not in RAW_EXTENSIONS:
            self._schedule_preview_refresh()
            return
        self._last_loaded_preview_key = None
        self._on_load_selected(show_message=False)

    def _auto_apply_current_icc_choice_to_selected_image(self) -> int:
        selected = getattr(self, "_selected_file", None)
        if selected is None:
            return 0
        path = Path(selected)
        if path.suffix.lower() not in RAW_EXTENSIONS:
            return 0
        try:
            if self._active_session_icc_for_settings() is not None:
                return self._assign_active_icc_profile_to_raw_files([path])
            sidecar = self._write_current_development_settings_to_raw(path, status="configured")
        except Exception as exc:
            self._log_preview(f"No se pudo aplicar ICC a {path.name}: {exc}")
            return 0
        if sidecar is not None:
            self._save_active_session(silent=True)
            return 1
        return 0


    def _managed_gamut_profile_items(self) -> list[tuple[str, str]]:
        return [
            (self.tr("Sesión:") + f" {self._icc_profile_combo_label(profile)}", f"managed:{profile.get('id')}")
            for profile in self._icc_profiles
            if str(profile.get("id") or "")
        ]

    def _refresh_gamut_profile_combos(self) -> None:
        for attr, default_key in (
            ("gamut_profile_a_combo", f"managed:{self._active_icc_profile_id}" if self._active_icc_profile_id else "generated"),
            ("gamut_profile_b_combo", "standard:srgb"),
        ):
            combo = getattr(self, attr, None)
            if combo is not None:
                self._populate_gamut_profile_combo(combo, default_key=default_key)
        if hasattr(self, "_sync_gamut_custom_controls"):
            self._sync_gamut_custom_controls()

    def _refresh_profile_management_views(self) -> None:
        self._refresh_icc_profile_combo()
        self._refresh_gamut_profile_combos()

    def _register_icc_profile(
        self,
        descriptor: dict[str, Any],
        *,
        activate: bool,
        save: bool = True,
        allow_rejected: bool = False,
    ) -> str:
        normalized = self._normalize_icc_profile_descriptor(descriptor)
        if normalized is None:
            return ""
        profile_id = str(normalized.get("id") or "")
        replaced = False
        for idx, existing in enumerate(self._icc_profiles):
            same_id = str(existing.get("id") or "") == profile_id
            same_path = str(existing.get("path") or "") == str(normalized.get("path") or "")
            if same_id or same_path:
                merged = dict(existing)
                for key, value in normalized.items():
                    if value in ("", None):
                        continue
                    if key == "status" and value == "unknown" and merged.get("status"):
                        continue
                    if key == "created_at" and merged.get("created_at"):
                        continue
                    if key == "source" and value == "generated" and merged.get("source") not in ("", None, "generated"):
                        continue
                    merged[key] = value
                self._icc_profiles[idx] = merged
                profile_id = str(merged.get("id") or profile_id)
                replaced = True
                break
        if not replaced:
            self._icc_profiles.append(normalized)
        self._sort_icc_profiles()
        if activate:
            self._activate_icc_profile_id(
                profile_id,
                save=False,
                refresh_preview=False,
                allow_rejected=allow_rejected,
            )
        else:
            self._refresh_profile_management_views()
        if save:
            self._save_active_session(silent=True)
        return profile_id

    def _activate_icc_profile_id(
        self,
        profile_id: str,
        *,
        save: bool = True,
        refresh_preview: bool = True,
        allow_rejected: bool = False,
    ) -> bool:
        if not profile_id:
            self._active_icc_profile_id = ""
            if hasattr(self, "path_profile_active"):
                self.path_profile_active.clear()
            if hasattr(self, "chk_apply_profile"):
                self.chk_apply_profile.setChecked(False)
            self._refresh_profile_management_views()
            self._refresh_chart_diagnostics_from_session(focus=False)
            if save:
                self._save_active_session(silent=True)
            return True

        profile = self._icc_profile_by_id(profile_id)
        path = self._session_stored_path(profile.get("path")) if profile else None
        if (
            profile is None
            or path is None
            or not path.exists()
            or not self._profile_can_be_active(path, allow_rejected=allow_rejected)
        ):
            return False
        self._active_icc_profile_id = profile_id
        self.path_profile_active.setText(str(path))
        self.chk_apply_profile.setChecked(True)
        self._set_camera_rgb_output_for_session_icc()
        self._refresh_profile_management_views()
        self._refresh_chart_diagnostics_from_session(focus=False)
        if refresh_preview:
            self._invalidate_preview_cache()
            self._reload_preview_source_for_color_management()
        if save:
            self._save_active_session(silent=True)
        return True

    def _activate_selected_icc_profile(self) -> None:
        profile_id = str(self.icc_profile_combo.currentData() or "") if hasattr(self, "icc_profile_combo") else ""
        if not profile_id:
            self._activate_icc_profile_id("", save=True)
            self._set_status(self.tr("Perfil ICC elegido desactivado"))
            return
        profile = self._icc_profile_by_id(profile_id)
        path = self._session_stored_path(profile.get("path")) if profile else None
        if (
            profile is None
            or path is None
            or not path.exists()
            or not self._profile_can_be_active(path, allow_rejected=True)
        ):
            status = self._profile_status_for_path(path) if path is not None else self.tr("no disponible")
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("Perfil no activable"),
                self.tr("No se activa el perfil porque su estado QA es") + f" '{status}'.",
            )
            self._refresh_icc_profile_combo()
            return
        self._activate_icc_profile_id(profile_id, save=True, allow_rejected=True)
        self._set_status(self.tr("Perfil activo:") + f" {path}")

    def _strip_version_suffix(self, stem: str) -> str:
        if len(stem) > 5 and stem[-5:-3] == "_v" and stem[-3:].isdigit():
            return stem[:-5]
        return stem

    def _next_generated_icc_profile_path(self, requested: Path) -> Path:
        requested = Path(requested).expanduser()
        base = requested.with_name(f"{self._strip_version_suffix(requested.stem)}{requested.suffix}")
        return versioned_output_path(base)

    def _profile_artifact_paths_for_generation(
        self,
        *,
        requested_profile_out: Path,
        requested_profile_report: Path,
        requested_workdir: Path,
        requested_development_profile: Path,
        requested_calibrated_recipe: Path,
    ) -> dict[str, Path]:
        profile_out = self._next_generated_icc_profile_path(requested_profile_out)
        if self._active_session_root is None:
            return {
                "profile_out": profile_out,
                "profile_report": versioned_output_path(requested_profile_report),
                "workdir": requested_workdir,
                "development_profile": versioned_output_path(requested_development_profile),
                "calibrated_recipe": versioned_output_path(requested_calibrated_recipe),
            }

        paths = self._session_paths_from_root(self._active_session_root)
        run_dir = paths["config"] / "profile_runs" / profile_out.stem
        return {
            "profile_out": profile_out,
            "profile_report": run_dir / "profile_report.json",
            "workdir": paths["work"] / "profile_generation" / profile_out.stem,
            "development_profile": run_dir / "development_profile.json",
            "calibrated_recipe": run_dir / "recipe_calibrated.yml",
        }

    def _slug_for_development_profile(self, name: str) -> str:
        raw = "".join(ch.lower() if ch.isalnum() else "-" for ch in name.strip())
        slug = "-".join(part for part in raw.split("-") if part) or "perfil"
        return slug[:48]

    def _unique_development_profile_id(self, name: str) -> str:
        base = self._slug_for_development_profile(name)
        existing = {str(profile.get("id") or "") for profile in self._development_profiles}
        if base not in existing:
            return base
        index = 2
        while f"{base}-{index}" in existing:
            index += 1
        return f"{base}-{index}"

    def _development_profile_dir(self, profile_id: str) -> Path:
        root = self._active_session_root or Path(self.session_root_path.text().strip() or Path.cwd())
        return self._session_paths_from_root(root)["config"] / "development_profiles" / profile_id

    def _session_generic_profile_dir(self) -> Path | None:
        root = self._active_session_root
        if root is None and hasattr(self, "session_root_path"):
            text = self.session_root_path.text().strip()
            root = Path(text).expanduser() if text else None
        if root is None:
            return None
        return self._session_paths_from_root(Path(root).expanduser())["profiles"] / "standard"

    def _render_profile_path_for_recipe(
        self,
        recipe: Recipe,
        *,
        input_profile_path: Path | None,
        color_management_mode: str,
    ) -> Path | None:
        try:
            return profile_path_for_render_settings(
                recipe,
                input_profile_path=input_profile_path,
                color_management_mode=color_management_mode,
                generic_profile_dir=self._session_generic_profile_dir(),
            )
        except Exception:
            return input_profile_path

    @staticmethod
    def _is_camera_output_space(output_space: str | None) -> bool:
        return str(output_space or "").strip().lower() in CAMERA_OUTPUT_SPACES

    def _color_management_issue_for_recipe(
        self,
        recipe: Recipe,
        *,
        input_profile_path: Path | None,
    ) -> str | None:
        output_space = str(recipe.output_space or "").strip()
        if is_generic_output_space(output_space):
            if recipe.output_linear:
                return self.tr(
                    "Los espacios de salida estándar requieren salida no lineal para "
                    "incrustar un perfil ICC estándar. Vuelve a seleccionar sRGB, "
                    "Adobe RGB o ProPhoto para sincronizar la receta."
                )
            return None

        if self._is_camera_output_space(output_space):
            if input_profile_path is None:
                return self.tr(
                    "La receta está en RGB de cámara, pero no hay un perfil ICC de entrada "
                    "elegido. Genera o carga un ICC de sesión para la imagen, "
                    "o elige sRGB, Adobe RGB o ProPhoto como espacio estándar sin carta."
                )
            if not input_profile_path.exists():
                return self.tr("No existe el perfil ICC de entrada activo:") + f" {input_profile_path}"
            return None

        return self.tr("Espacio de salida no soportado para gestión ICC:") + f" {output_space or '<vacío>'}"

    def _require_color_managed_recipe_for_ui(
        self,
        recipe: Recipe,
        *,
        input_profile_path: Path | None,
        title: str | None = None,
    ) -> bool:
        issue = self._color_management_issue_for_recipe(
            recipe,
            input_profile_path=input_profile_path,
        )
        if issue is None:
            return True
        QtWidgets.QMessageBox.warning(
            self,
            title or self.tr("Gestión de color incompleta"),
            issue,
        )
        self._set_status(self.tr("Gestión de color incompleta"))
        return False

    @staticmethod
    def _recipe_uses_identity_fixed_wb(recipe: Recipe) -> bool:
        if str(recipe.white_balance_mode or "").strip().lower() != "fixed":
            return False
        values = [float(v) for v in (recipe.wb_multipliers or [])]
        if len(values) < 3:
            return False
        return all(abs(v - 1.0) <= 1e-6 for v in values[:4])

    def _visible_export_recipe_for_color_management(
        self,
        recipe: Recipe,
        *,
        input_profile_path: Path | None,
    ) -> Recipe:
        export_recipe = Recipe(**asdict(recipe))
        if input_profile_path is None and not is_generic_output_space(export_recipe.output_space):
            profile = generic_output_profile("prophoto_rgb")
            export_recipe.output_space = profile.key
            export_recipe.output_linear = False
            export_recipe.tone_curve = f"gamma:{profile.gamma:.3g}"
            export_recipe.profiling_mode = False

        export_recipe = self._normalize_recipe_output_for_color_management(export_recipe)
        if input_profile_path is None and is_generic_output_space(export_recipe.output_space):
            if bool(getattr(export_recipe, "profiling_mode", False)):
                export_recipe.profiling_mode = False
            if self._recipe_uses_identity_fixed_wb(export_recipe):
                export_recipe.white_balance_mode = "camera_metadata"
        return export_recipe

    def _configured_color_profile_for_recipe(self, recipe: Recipe) -> tuple[Path | None, Path | None, str]:
        input_profile_path = self._active_session_icc_for_settings()
        issue = self._color_management_issue_for_recipe(
            recipe,
            input_profile_path=input_profile_path,
        )
        if issue is not None:
            raise RuntimeError(issue)
        if is_generic_output_space(recipe.output_space):
            output_profile = ensure_generic_output_profile(
                recipe.output_space,
                directory=self._session_generic_profile_dir(),
            )
            mode = (
                f"standard_{generic_output_profile(recipe.output_space).key}_output_icc"
                if input_profile_path is None
                else f"converted_{generic_output_profile(recipe.output_space).key}"
            )
            if generic_output_profile(recipe.output_space).key == "srgb" and input_profile_path is not None:
                mode = "converted_srgb"
            return input_profile_path, output_profile, mode
        if input_profile_path is not None:
            return input_profile_path, input_profile_path, "camera_rgb_with_input_icc"
        raise RuntimeError(self.tr("Gestión de color incompleta"))

    def _development_profile_by_id(self, profile_id: str) -> dict[str, Any] | None:
        for profile in self._development_profiles:
            if str(profile.get("id") or "") == profile_id:
                return profile
        return None

    @staticmethod
    def _adjustment_profile_type_for_kind(kind: str) -> str:
        return "advanced" if str(kind or "").strip().lower() in {"chart", "advanced"} else "basic"

    def _development_profile_label(self, profile_id: str) -> str:
        if not profile_id:
            return "Actual"
        profile = self._development_profile_by_id(profile_id)
        if profile is None:
            return profile_id
        return str(profile.get("name") or profile_id)

    def _refresh_development_profile_combo(self) -> None:
        if not hasattr(self, "development_profile_combo"):
            return
        current = self._active_development_profile_id
        self.development_profile_combo.blockSignals(True)
        self.development_profile_combo.clear()
        self.development_profile_combo.addItem(self.tr("Ajustes actuales"), "")
        for profile in self._development_profiles:
            profile_id = str(profile.get("id") or "").strip()
            if not profile_id:
                continue
            label = str(profile.get("name") or profile_id)
            kind = str(profile.get("kind") or "manual")
            self.development_profile_combo.addItem(f"{label} ({kind})", profile_id)
        index = self.development_profile_combo.findData(current)
        self.development_profile_combo.setCurrentIndex(index if index >= 0 else 0)
        self.development_profile_combo.blockSignals(False)
        if hasattr(self, "development_profile_status_label"):
            active = self._development_profile_label(current)
            self.development_profile_status_label.setText(
                f"Perfiles de ajuste: {len(self._development_profiles)} | Activo: {active}"
            )

    def _on_development_output_space_changed(self) -> None:
        if not hasattr(self, "development_output_space_combo") or not hasattr(self, "combo_output_space"):
            return
        if int(getattr(self, "_suspend_raw_export_autosave", 0) or 0) > 0:
            return
        output_space = str(self.development_output_space_combo.currentData() or "scene_linear_camera_rgb")
        self.combo_output_space.blockSignals(True)
        self._set_combo_text(self.combo_output_space, output_space)
        self.combo_output_space.blockSignals(False)
        self._apply_output_space_defaults_to_controls(output_space)
        if self._original_linear is not None:
            self._reload_preview_source_for_color_management()

    def _on_output_space_changed(self) -> None:
        if not hasattr(self, "combo_output_space"):
            return
        if int(getattr(self, "_suspend_raw_export_autosave", 0) or 0) > 0:
            return
        output_space = self.combo_output_space.currentText().strip()
        self._sync_development_output_space_combo(output_space)
        self._apply_output_space_defaults_to_controls(output_space)
        if self._original_linear is not None:
            self._reload_preview_source_for_color_management()

    def _on_output_linear_toggled(self, checked: bool) -> None:
        if not hasattr(self, "combo_output_space"):
            return
        if int(getattr(self, "_suspend_raw_export_autosave", 0) or 0) > 0:
            return
        output_space = self.combo_output_space.currentText().strip()
        if checked and is_generic_output_space(output_space):
            self.check_output_linear.blockSignals(True)
            self.check_output_linear.setChecked(False)
            self.check_output_linear.blockSignals(False)
            self._set_status(self.tr("Los espacios estándar se exportan con salida no lineal e ICC estándar."))
        elif not checked and self._is_camera_output_space(output_space):
            self.check_output_linear.blockSignals(True)
            self.check_output_linear.setChecked(True)
            self.check_output_linear.blockSignals(False)
            self._set_status(self.tr("RGB de cámara se mantiene lineal para el ICC de entrada de sesión."))
        if self._original_linear is not None:
            self._schedule_preview_refresh()

    def _apply_output_space_defaults_to_controls(self, output_space: str) -> None:
        if not all(hasattr(self, name) for name in ("check_output_linear", "combo_tone_curve", "spin_gamma")):
            return
        if self._is_camera_output_space(output_space):
            self.check_output_linear.blockSignals(True)
            self.check_output_linear.setChecked(True)
            self.check_output_linear.blockSignals(False)
            self._set_combo_data(self.combo_tone_curve, "linear")
            return
        if not is_generic_output_space(output_space):
            return
        profile = generic_output_profile(output_space)
        self.check_output_linear.blockSignals(True)
        self.check_output_linear.setChecked(False)
        self.check_output_linear.blockSignals(False)
        if hasattr(self, "check_profiling_mode"):
            self.check_profiling_mode.setChecked(False)
        if (
            hasattr(self, "combo_wb_mode")
            and hasattr(self, "edit_wb_multipliers")
            and str(self.combo_wb_mode.currentData() or "").strip().lower() == "fixed"
            and self._recipe_uses_identity_fixed_wb(self._build_effective_recipe())
        ):
            self.combo_wb_mode.blockSignals(True)
            self._set_combo_data(self.combo_wb_mode, "camera_metadata")
            self.combo_wb_mode.blockSignals(False)
        if profile.key == "srgb":
            self._set_combo_data(self.combo_tone_curve, "srgb")
            self.spin_gamma.setValue(2.2)
        else:
            self._set_combo_data(self.combo_tone_curve, "gamma")
            self.spin_gamma.setValue(float(profile.gamma))

    def _sync_development_output_space_combo(self, output_space: str) -> None:
        if not hasattr(self, "development_output_space_combo"):
            return
        target = output_space if is_generic_output_space(output_space) else "scene_linear_camera_rgb"
        index = self.development_output_space_combo.findData(target)
        if index >= 0 and self.development_output_space_combo.currentIndex() != index:
            self.development_output_space_combo.blockSignals(True)
            self.development_output_space_combo.setCurrentIndex(index)
            self.development_output_space_combo.blockSignals(False)

    def _register_development_profile(self, descriptor: dict[str, Any], *, activate: bool = True) -> None:
        profile_id = str(descriptor.get("id") or "").strip()
        if not profile_id:
            return
        now = self._profile_timestamp()
        descriptor = dict(descriptor)
        descriptor.setdefault("created_at", now)
        descriptor["updated_at"] = now
        replaced = False
        for idx, existing in enumerate(self._development_profiles):
            if str(existing.get("id") or "") == profile_id:
                merged = dict(existing)
                merged.update(descriptor)
                self._development_profiles[idx] = merged
                replaced = True
                break
        if not replaced:
            self._development_profiles.append(descriptor)
        self._development_profiles.sort(key=lambda item: str(item.get("name") or item.get("id") or ""))
        if activate:
            self._active_development_profile_id = profile_id
        self._refresh_development_profile_combo()
        self._save_active_session(silent=True)

    def _named_adjustment_profile_attrs(self, category: str) -> tuple[str, str, str, str, str]:
        mapping = {
            "color_contrast": (
                "_color_contrast_profiles",
                "_active_color_contrast_profile_id",
                "color_contrast_profile_combo",
                "color_contrast_profile_name_edit",
                "color_contrast_profile_status_label",
            ),
            "detail": (
                "_detail_profiles",
                "_active_detail_profile_id",
                "detail_profile_combo",
                "detail_profile_name_edit",
                "detail_profile_status_label",
            ),
            "raw_export": (
                "_raw_export_profiles",
                "_active_raw_export_profile_id",
                "raw_export_profile_combo",
                "raw_export_profile_name_edit",
                "raw_export_profile_status_label",
            ),
        }
        if category not in mapping:
            raise RuntimeError(f"Tipo de perfil de ajuste no soportado: {category}")
        return mapping[category]

    def _named_adjustment_profile_title(self, category: str) -> str:
        if category == "color_contrast":
            return self.tr("Color y contraste")
        if category == "detail":
            return self.tr("Nitidez")
        if category == "raw_export":
            return self.tr("Exportacion RAW")
        return category

    def _named_adjustment_profile_collection(self, category: str) -> list[dict[str, Any]]:
        collection_attr, _active_attr, _combo_attr, _name_attr, _status_attr = self._named_adjustment_profile_attrs(category)
        collection = getattr(self, collection_attr, None)
        if not isinstance(collection, list):
            collection = []
            setattr(self, collection_attr, collection)
        return collection

    def _raw_export_recipe_fields(self) -> tuple[str, ...]:
        return (
            "raw_developer",
            "demosaic_algorithm",
            "demosaic_edge_quality",
            "false_color_suppression_steps",
            "four_color_rgb",
            "black_level_mode",
        )

    def _raw_export_recipe_subset(self, recipe: Recipe) -> Recipe:
        raw_recipe = Recipe()
        for field_name in self._raw_export_recipe_fields():
            if hasattr(recipe, field_name):
                setattr(raw_recipe, field_name, getattr(recipe, field_name))
        return raw_recipe

    def _raw_export_recipe_has_effect(self, recipe: Recipe | None) -> bool:
        if recipe is None:
            return False
        default = Recipe()
        for field_name in self._raw_export_recipe_fields():
            current = getattr(recipe, field_name, None)
            baseline = getattr(default, field_name, None)
            if isinstance(current, str) or isinstance(baseline, str):
                if str(current or "").strip().lower() != str(baseline or "").strip().lower():
                    return True
                continue
            if current != baseline:
                return True
        return False

    def _raw_export_recipe_from_current_controls(self) -> Recipe:
        return self._raw_export_recipe_subset(self._build_effective_recipe())

    def _merge_raw_export_recipe(self, base: Recipe, raw_settings: Recipe) -> Recipe:
        merged = Recipe(**asdict(base))
        for field_name in self._raw_export_recipe_fields():
            if hasattr(raw_settings, field_name):
                setattr(merged, field_name, getattr(raw_settings, field_name))
        return merged

    def _merge_libraw_color_state_into_recipe(self, base: Recipe, render_state: dict[str, Any] | None) -> Recipe:
        merged = Recipe(**asdict(base))
        state = render_state.get("libraw") if isinstance(render_state, dict) else None
        if not isinstance(state, dict):
            return merged
        mapping = {
            "white_balance_mode": "white_balance_mode",
            "wb_multipliers": "wb_multipliers",
            "auto_bright": "libraw_auto_bright",
            "auto_bright_thr": "libraw_auto_bright_thr",
            "adjust_maximum_thr": "libraw_adjust_maximum_thr",
            "bright": "libraw_bright",
            "highlight_mode": "libraw_highlight_mode",
            "exp_shift": "libraw_exp_shift",
            "exp_preserve_highlights": "libraw_exp_preserve_highlights",
            "no_auto_scale": "libraw_no_auto_scale",
            "gamma_power": "libraw_gamma_power",
            "gamma_slope": "libraw_gamma_slope",
            "chromatic_aberration_red": "libraw_chromatic_aberration_red",
            "chromatic_aberration_blue": "libraw_chromatic_aberration_blue",
        }
        for source_key, field_name in mapping.items():
            if source_key not in state:
                continue
            value = state[source_key]
            if field_name == "wb_multipliers" and isinstance(value, (list, tuple)):
                setattr(merged, field_name, [float(v) for v in value])
            else:
                setattr(merged, field_name, value)
        return merged

    def _active_named_adjustment_profile_id(self, category: str) -> str:
        _collection_attr, active_attr, _combo_attr, _name_attr, _status_attr = self._named_adjustment_profile_attrs(category)
        return str(getattr(self, active_attr, "") or "")

    def _set_active_named_adjustment_profile_id(self, category: str, profile_id: str) -> None:
        _collection_attr, active_attr, _combo_attr, _name_attr, _status_attr = self._named_adjustment_profile_attrs(category)
        setattr(self, active_attr, str(profile_id or ""))

    def _named_adjustment_profile_by_id(self, category: str, profile_id: str) -> dict[str, Any] | None:
        for profile in self._named_adjustment_profile_collection(category):
            if str(profile.get("id") or "") == profile_id:
                return profile
        return None

    def _unique_named_adjustment_profile_id(self, category: str, name: str) -> str:
        base = self._slug_for_development_profile(name)
        existing = {str(profile.get("id") or "") for profile in self._named_adjustment_profile_collection(category)}
        if base not in existing:
            return base
        index = 2
        while f"{base}-{index}" in existing:
            index += 1
        return f"{base}-{index}"

    def _named_adjustment_profile_dir(self, category: str, profile_id: str) -> Path:
        root = self._active_session_root or Path(self.session_root_path.text().strip() or Path.cwd())
        return self._session_paths_from_root(root)["config"] / "adjustment_profiles" / category / profile_id

    def _named_adjustment_profile_manifest(self, profile: dict[str, Any]) -> dict[str, Any]:
        manifest_path = self._session_stored_path(profile.get("manifest_path"))
        if manifest_path is None or not manifest_path.exists():
            return {}
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _named_adjustment_profile_state(self, category: str, profile: dict[str, Any]) -> Any:
        manifest = self._named_adjustment_profile_manifest(profile)
        if category == "color_contrast":
            state = manifest.get("render_adjustments")
            return state if isinstance(state, dict) else self._default_render_adjustment_state()
        if category == "detail":
            state = manifest.get("detail_adjustments")
            return state if isinstance(state, dict) else self._default_detail_adjustment_state()
        if category == "raw_export":
            recipe = self._recipe_from_payload(manifest.get("recipe"))
            return self._raw_export_recipe_subset(recipe) if recipe is not None else self._raw_export_recipe_from_current_controls()
        raise RuntimeError(f"Tipo de perfil de ajuste no soportado: {category}")

    def _current_named_adjustment_profiles_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for category in ("color_contrast", "detail", "raw_export"):
            profile_id = self._active_named_adjustment_profile_id(category)
            profile = self._named_adjustment_profile_by_id(category, profile_id) if profile_id else None
            payload[category] = {
                "id": profile_id if profile else "",
                "name": str(profile.get("name") or profile_id) if profile else "",
                "kind": category,
            }
        if getattr(self, "_active_icc_profile_id", ""):
            profile = self._icc_profile_by_id(str(self._active_icc_profile_id))
            payload["icc"] = {
                "id": str(self._active_icc_profile_id),
                "name": str(profile.get("name") or self._active_icc_profile_id) if profile else str(self._active_icc_profile_id),
                "kind": "icc",
            }
        return payload

    def _refresh_named_adjustment_profile_combo(self, category: str) -> None:
        _collection_attr, _active_attr, combo_attr, _name_attr, status_attr = self._named_adjustment_profile_attrs(category)
        combo = getattr(self, combo_attr, None)
        if combo is None:
            return
        current = self._active_named_adjustment_profile_id(category)
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(self.tr("Ajustes actuales"), "")
        for profile in self._named_adjustment_profile_collection(category):
            profile_id = str(profile.get("id") or "").strip()
            if profile_id:
                combo.addItem(str(profile.get("name") or profile_id), profile_id)
        index = combo.findData(current)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)
        status = getattr(self, status_attr, None)
        if status is not None:
            active = current or self.tr("actuales")
            status.setText(
                f"{self._named_adjustment_profile_title(category)}: "
                f"{len(self._named_adjustment_profile_collection(category))} | Activo: {active}"
            )

    def _refresh_named_adjustment_profile_combos(self) -> None:
        for category in ("color_contrast", "detail", "raw_export"):
            self._refresh_named_adjustment_profile_combo(category)

    def _register_named_adjustment_profile(self, category: str, descriptor: dict[str, Any], *, activate: bool = True) -> None:
        profile_id = str(descriptor.get("id") or "").strip()
        if not profile_id:
            return
        now = self._profile_timestamp()
        descriptor = dict(descriptor)
        descriptor["category"] = category
        descriptor.setdefault("created_at", now)
        descriptor["updated_at"] = now
        collection = self._named_adjustment_profile_collection(category)
        for idx, existing in enumerate(collection):
            if str(existing.get("id") or "") == profile_id:
                merged = dict(existing)
                merged.update(descriptor)
                collection[idx] = merged
                break
        else:
            collection.append(descriptor)
        collection.sort(key=lambda item: str(item.get("name") or item.get("id") or ""))
        if activate:
            self._set_active_named_adjustment_profile_id(category, profile_id)
        self._refresh_named_adjustment_profile_combo(category)
        self._save_active_session(silent=True)

    def _save_named_adjustment_profile(self, category: str) -> None:
        if self._active_session_root is None:
            self._on_create_session()
            if self._active_session_root is None:
                return
        _collection_attr, _active_attr, _combo_attr, name_attr, _status_attr = self._named_adjustment_profile_attrs(category)
        name_widget = getattr(self, name_attr)
        name = name_widget.text().strip() or self._named_adjustment_profile_title(category)
        profile_id = self._unique_named_adjustment_profile_id(category, name)
        profile_dir = self._named_adjustment_profile_dir(category, profile_id)
        profile_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = profile_dir / "profile.json"
        manifest: dict[str, Any] = {
            "id": profile_id,
            "name": name,
            "category": category,
            "created_at": self._profile_timestamp(),
        }
        if category == "color_contrast":
            manifest["render_adjustments"] = self._render_adjustment_state()
        elif category == "detail":
            manifest["detail_adjustments"] = self._detail_adjustment_state()
        elif category == "raw_export":
            recipe = self._raw_export_recipe_from_current_controls()
            recipe_path = profile_dir / "recipe.yml"
            save_recipe(recipe, recipe_path)
            manifest["recipe_path"] = self._session_relative_or_absolute(recipe_path)
            manifest["recipe"] = asdict(recipe)
        else:
            raise RuntimeError(f"Tipo de perfil de ajuste no soportado: {category}")
        write_json(manifest_path, manifest)
        descriptor = {
            "id": profile_id,
            "name": name,
            "category": category,
            "manifest_path": self._session_relative_or_absolute(manifest_path),
        }
        if category == "raw_export":
            descriptor["recipe_path"] = manifest.get("recipe_path", "")
        self._register_named_adjustment_profile(category, descriptor, activate=True)
        self._set_status(self._named_adjustment_profile_title(category) + self.tr(" guardado:") + f" {name}")

    def _activate_selected_named_adjustment_profile(self, category: str) -> None:
        _collection_attr, _active_attr, combo_attr, _name_attr, _status_attr = self._named_adjustment_profile_attrs(category)
        combo = getattr(self, combo_attr)
        self._apply_named_adjustment_profile_to_controls(category, str(combo.currentData() or ""))

    def _apply_named_adjustment_profile_to_controls(self, category: str, profile_id: str) -> None:
        if not profile_id:
            self._set_active_named_adjustment_profile_id(category, "")
            self._refresh_named_adjustment_profile_combo(category)
            return
        profile = self._named_adjustment_profile_by_id(category, profile_id)
        if profile is None:
            QtWidgets.QMessageBox.warning(self, self.tr("Perfil no valido"), self.tr("No existe el perfil seleccionado."))
            return
        state = self._named_adjustment_profile_state(category, profile)
        if category == "color_contrast":
            self._apply_render_adjustment_state(state)
        elif category == "detail":
            self._apply_detail_adjustment_state(state)
        elif category == "raw_export":
            self._apply_raw_export_recipe_to_controls(state)
        self._set_active_named_adjustment_profile_id(category, profile_id)
        self._refresh_named_adjustment_profile_combo(category)
        self._invalidate_preview_cache()
        if self._original_linear is not None:
            self._schedule_preview_refresh()
        self._save_active_session(silent=True)
        if category == "color_contrast" and hasattr(self, "_schedule_render_adjustment_sidecar_persist"):
            self._schedule_render_adjustment_sidecar_persist(immediate=True)
        if category == "detail" and hasattr(self, "_schedule_detail_adjustment_sidecar_persist"):
            self._schedule_detail_adjustment_sidecar_persist(immediate=True)
        self._set_status(self._named_adjustment_profile_title(category) + self.tr(" aplicado:") + f" {profile.get('name') or profile_id}")

    def _sidecar_bundle_for_category_write(self, path: Path) -> dict[str, Any]:
        try:
            payload = load_raw_sidecar(path)
        except Exception:
            payload = {}
        recipe = self._recipe_from_payload(payload.get("recipe")) or self._build_effective_recipe()
        detail = payload.get("detail_adjustments") if isinstance(payload.get("detail_adjustments"), dict) else self._detail_adjustment_state()
        render = payload.get("render_adjustments") if isinstance(payload.get("render_adjustments"), dict) else self._render_adjustment_state()
        profile = payload.get("development_profile") if isinstance(payload.get("development_profile"), dict) else self._development_profile_payload_for_active_settings()
        adjustment_profiles = (
            dict(payload.get("adjustment_profiles"))
            if isinstance(payload.get("adjustment_profiles"), dict)
            else self._current_named_adjustment_profiles_payload()
        )
        color = payload.get("color_management") if isinstance(payload.get("color_management"), dict) else {}
        mode = str(color.get("mode") or "")
        profile_path = self._session_stored_path(color.get("icc_profile_path")) if color else None
        if profile_path is None or not profile_path.exists():
            try:
                _input_profile, profile_path, mode = self._configured_color_profile_for_recipe(recipe)
            except Exception:
                profile_path = None
                mode = "no_profile"
        return {
            "recipe": recipe,
            "detail_adjustments": detail,
            "render_adjustments": render,
            "development_profile": profile,
            "adjustment_profiles": adjustment_profiles,
            "profile_path": profile_path,
            "color_management_mode": mode,
        }

    def _profile_summary_payload(self, category: str, profile: dict[str, Any]) -> dict[str, str]:
        return {
            "id": str(profile.get("id") or ""),
            "name": str(profile.get("name") or profile.get("id") or ""),
            "kind": category,
        }

    def _apply_named_adjustment_profile_to_raw_files(self, category: str, profile_id: str, files: list[Path]) -> int:
        profile = self._named_adjustment_profile_by_id(category, profile_id)
        if profile is None:
            return 0
        state = self._named_adjustment_profile_state(category, profile)
        written = 0
        errors: list[tuple[Path, Exception]] = []
        for path in files:
            if path.suffix.lower() not in RAW_EXTENSIONS:
                continue
            try:
                bundle = self._sidecar_bundle_for_category_write(path)
                if category == "color_contrast":
                    bundle["render_adjustments"] = state
                    bundle["recipe"] = self._merge_libraw_color_state_into_recipe(bundle["recipe"], state)
                elif category == "detail":
                    bundle["detail_adjustments"] = state
                elif category == "raw_export":
                    merged_recipe = self._merge_raw_export_recipe(bundle["recipe"], state)
                    bundle["recipe"] = merged_recipe
                    _input_profile, rendered_profile, mode = self._configured_color_profile_for_recipe(merged_recipe)
                    bundle["profile_path"] = rendered_profile
                    bundle["color_management_mode"] = mode
                bundle["adjustment_profiles"][category] = self._profile_summary_payload(category, profile)
                sidecar = self._write_raw_settings_sidecar(path, status="configured", **bundle)
                if sidecar is not None:
                    written += 1
            except Exception as exc:
                errors.append((path, exc))
        if errors:
            first_path, first_error = errors[0]
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("No se pudo escribir mochila"),
                self.tr("Fallaron") + f" {len(errors)} " + self.tr("archivo(s). Primer error:")
                + f"\n{first_path}\n{first_error}",
            )
        if written:
            self._refresh_color_reference_thumbnail_markers()
            self._save_active_session(silent=True)
        return written

    def _assign_active_icc_profile_to_raw_files(self, files: list[Path]) -> int:
        icc_path = self._active_session_icc_for_settings()
        if icc_path is None:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("Activa primero un perfil ICC de sesion."))
            return 0
        icc_profile = self._icc_profile_by_path(icc_path)
        icc_payload = {
            "id": str(icc_profile.get("id") or self._active_icc_profile_id) if icc_profile else str(self._active_icc_profile_id or ""),
            "name": str(icc_profile.get("name") or icc_path.stem) if icc_profile else icc_path.stem,
            "kind": "icc",
        }
        written = 0
        for path in files:
            if path.suffix.lower() not in RAW_EXTENSIONS:
                continue
            bundle = self._sidecar_bundle_for_category_write(path)
            recipe = self._visible_export_recipe_for_color_management(
                bundle["recipe"],
                input_profile_path=icc_path,
            )
            bundle["recipe"] = recipe
            bundle["profile_path"] = icc_path
            bundle["color_management_mode"] = "camera_rgb_with_input_icc"
            bundle["adjustment_profiles"]["icc"] = icc_payload
            if self._write_raw_settings_sidecar(path, status="configured", **bundle) is not None:
                written += 1
        if written:
            self._refresh_color_reference_thumbnail_markers()
            self._save_active_session(silent=True)
        return written

    def _assign_active_icc_profile_to_selected(self) -> None:
        files = [p for p in self._selected_or_current_file_paths() if p.suffix.lower() in RAW_EXTENSIONS]
        if not files:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("Selecciona uno o mas RAW de destino."))
            return
        written = self._assign_active_icc_profile_to_raw_files(files)
        if self._selected_file is not None and any(self._normalized_path_key(self._selected_file) == self._normalized_path_key(p) for p in files):
            self._apply_raw_sidecar_to_controls(self._selected_file)
        self._set_status(self.tr("Perfil ICC aplicado a") + f" {written} " + self.tr("imagen(es)"))

    def _assign_active_icc_profile_to_session_raws(self) -> None:
        if self._active_session_root is None:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("Abre o crea primero una sesion."))
            return
        raw_dir = self._session_paths_from_root(self._active_session_root)["raw"]
        files = [p for p in sorted(raw_dir.iterdir()) if p.is_file() and p.suffix.lower() in RAW_EXTENSIONS]
        written = self._assign_active_icc_profile_to_raw_files(files)
        self._set_status(self.tr("Perfil ICC aplicado a") + f" {written} " + self.tr("RAW de sesion"))

    def _apply_selected_named_adjustment_profile_to_selected(self, category: str) -> None:
        profile_id = self._active_named_adjustment_profile_id(category)
        if not profile_id:
            _collection_attr, _active_attr, combo_attr, _name_attr, _status_attr = self._named_adjustment_profile_attrs(category)
            combo = getattr(self, combo_attr)
            profile_id = str(combo.currentData() or "")
        if not profile_id:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("Guarda o selecciona primero un perfil."))
            return
        files = [p for p in self._selected_or_current_file_paths() if p.suffix.lower() in RAW_EXTENSIONS]
        if not files:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("Selecciona uno o mas RAW de destino."))
            return
        written = self._apply_named_adjustment_profile_to_raw_files(category, profile_id, files)
        if self._selected_file is not None and any(self._normalized_path_key(self._selected_file) == self._normalized_path_key(p) for p in files):
            self._apply_raw_sidecar_to_controls(self._selected_file)
        self._set_status(self._named_adjustment_profile_title(category) + self.tr(" aplicado a") + f" {written} " + self.tr("imagen(es)"))

    def _copy_named_adjustment_profile_from_selected(self, category: str) -> None:
        files = [p for p in self._selected_or_current_file_paths() if p.suffix.lower() in RAW_EXTENSIONS]
        if not files:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("Selecciona un RAW con ajustes guardados."))
            return
        source = files[0]
        try:
            sidecar = load_raw_sidecar(source)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, self.tr("Mochila no valida"), str(exc))
            return
        if category == "color_contrast":
            state = sidecar.get("render_adjustments")
        elif category == "detail":
            state = sidecar.get("detail_adjustments")
        elif category == "raw_export":
            recipe = self._recipe_from_payload(sidecar.get("recipe"))
            state = asdict(self._raw_export_recipe_subset(recipe)) if recipe is not None else None
        else:
            state = None
        if not isinstance(state, dict):
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("La imagen no contiene ese tipo de ajuste."))
            return
        _collection_attr, _active_attr, _combo_attr, _name_attr, _status_attr = self._named_adjustment_profile_attrs(category)
        setattr(self, f"_{category}_profile_clipboard", {"source": str(source), "category": category, "state": state})
        self._set_status(self._named_adjustment_profile_title(category) + self.tr(" copiado desde ") + source.name)

    def _paste_named_adjustment_profile_to_selected(self, category: str) -> None:
        copied = getattr(self, f"_{category}_profile_clipboard", None)
        if not isinstance(copied, dict) or copied.get("category") != category:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("Copia primero ese tipo de ajuste desde una miniatura."))
            return
        files = [p for p in self._selected_or_current_file_paths() if p.suffix.lower() in RAW_EXTENSIONS]
        if not files:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("Selecciona uno o mas RAW de destino."))
            return
        state = copied.get("state")
        written = 0
        for path in files:
            bundle = self._sidecar_bundle_for_category_write(path)
            if category == "color_contrast" and isinstance(state, dict):
                bundle["render_adjustments"] = state
            elif category == "detail" and isinstance(state, dict):
                bundle["detail_adjustments"] = state
            elif category == "raw_export":
                recipe = self._recipe_from_payload(state)
                if recipe is None:
                    continue
                merged_recipe = self._merge_raw_export_recipe(bundle["recipe"], recipe)
                _input_profile, rendered_profile, mode = self._configured_color_profile_for_recipe(merged_recipe)
                bundle["recipe"] = merged_recipe
                bundle["profile_path"] = rendered_profile
                bundle["color_management_mode"] = mode
            else:
                continue
            if self._write_raw_settings_sidecar(path, status="configured", **bundle) is not None:
                written += 1
        if self._selected_file is not None and any(self._normalized_path_key(self._selected_file) == self._normalized_path_key(p) for p in files):
            self._apply_raw_sidecar_to_controls(self._selected_file)
        if written:
            self._refresh_color_reference_thumbnail_markers()
            self._save_active_session(silent=True)
        self._set_status(self._named_adjustment_profile_title(category) + self.tr(" pegado en") + f" {written} " + self.tr("imagen(es)"))

    def _development_profile_manifest(self, profile: dict[str, Any]) -> dict[str, Any]:
        manifest_path = self._session_stored_path(profile.get("manifest_path"))
        if manifest_path is None or not manifest_path.exists():
            return {}
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _development_profile_recipe(self, profile: dict[str, Any], manifest: dict[str, Any]) -> Recipe:
        recipe_path = self._session_stored_path(profile.get("recipe_path") or manifest.get("render_recipe_path"))
        if recipe_path is not None and recipe_path.exists():
            return load_recipe(recipe_path)
        recipe_payload = manifest.get("recipe") or manifest.get("calibrated_recipe")
        if isinstance(recipe_payload, dict):
            allowed = set(Recipe.__dataclass_fields__.keys())
            filtered = {k: v for k, v in recipe_payload.items() if k in allowed}
            return Recipe(**filtered)
        return self._build_effective_recipe()

    def _development_profile_settings(self, profile_id: str) -> dict[str, Any]:
        profile = self._development_profile_by_id(profile_id) if profile_id else None
        if profile is None:
            detail_state = self._detail_adjustment_state()
            render_state = self._render_adjustment_state()
            profile_path = self._active_session_icc_for_settings()
            return {
                "id": "",
                "name": "Ajustes actuales",
                "kind": "manual",
                "profile_type": "basic",
                "recipe": self._build_effective_recipe(),
                "detail_adjustments": detail_state,
                "render_adjustments": render_state,
                "icc_profile_path": profile_path,
                "output_icc_profile_path": None,
            }

        manifest = self._development_profile_manifest(profile)
        detail_state = (
            manifest.get("detail_adjustments")
            if isinstance(manifest.get("detail_adjustments"), dict)
            else self._detail_adjustment_state()
        )
        render_state = (
            manifest.get("render_adjustments")
            if isinstance(manifest.get("render_adjustments"), dict)
            else self._render_adjustment_state()
        )
        icc_profile_path = self._session_stored_path(profile.get("icc_profile_path") or manifest.get("icc_profile_path"))
        output_icc_profile_path = self._session_stored_path(
            profile.get("output_icc_profile_path") or manifest.get("output_icc_profile_path")
        )
        kind = str(profile.get("kind") or manifest.get("kind") or "manual")
        profile_type = str(profile.get("profile_type") or manifest.get("profile_type") or "")
        if profile_type not in {"advanced", "basic"}:
            profile_type = self._adjustment_profile_type_for_kind(kind)
        return {
            "id": str(profile.get("id") or ""),
            "name": str(profile.get("name") or profile.get("id") or ""),
            "kind": kind,
            "profile_type": profile_type,
            "recipe": self._development_profile_recipe(profile, manifest),
            "detail_adjustments": detail_state,
            "render_adjustments": render_state,
            "icc_profile_path": icc_profile_path,
            "output_icc_profile_path": output_icc_profile_path,
        }

    def _recipe_from_payload(self, payload: Any) -> Recipe | None:
        if not isinstance(payload, dict):
            return None
        try:
            allowed = set(Recipe.__dataclass_fields__.keys())
            filtered = {k: v for k, v in payload.items() if k in allowed}
            return Recipe(**filtered)
        except Exception:
            return None

    def _development_profile_from_sidecar(self, path: Path) -> str:
        if hasattr(self, "_cached_raw_sidecar_payload"):
            payload = self._cached_raw_sidecar_payload(path)
        else:
            try:
                payload = load_raw_sidecar(path)
            except Exception:
                payload = None
        if payload is None:
            return ""
        profile = payload.get("development_profile") if isinstance(payload, dict) else {}
        profile_id = str(profile.get("id") or "") if isinstance(profile, dict) else ""
        if profile_id and self._development_profile_by_id(profile_id) is not None:
            return profile_id
        return ""

    def _development_settings_from_raw_sidecar(self, path: Path) -> dict[str, Any] | None:
        if hasattr(self, "_cached_raw_sidecar_payload"):
            payload = self._cached_raw_sidecar_payload(path)
        else:
            try:
                payload = load_raw_sidecar(path)
            except Exception:
                payload = None
        if payload is None:
            return None
        recipe = self._recipe_from_payload(payload.get("recipe"))
        if recipe is None:
            return None

        detail_state = payload.get("detail_adjustments")
        render_state = payload.get("render_adjustments")
        profile = payload.get("development_profile") if isinstance(payload.get("development_profile"), dict) else {}
        kind = str(profile.get("kind") or "manual")
        profile_type = str(profile.get("profile_type") or "").strip().lower()
        if profile_type not in {"advanced", "basic"}:
            profile_type = self._adjustment_profile_type_for_kind(kind)

        color = payload.get("color_management") if isinstance(payload.get("color_management"), dict) else {}
        icc_role = str(color.get("icc_profile_role") or "")
        color_mode = str(color.get("mode") or "")
        icc_path = self._session_stored_path(color.get("icc_profile_path")) if color else None
        input_profile_path = (
            icc_path
            if icc_path is not None
            and icc_path.exists()
            and (
                icc_role == "session_input_icc"
                or color_mode == "camera_rgb_with_input_icc"
                or self._is_camera_output_space(recipe.output_space)
            )
            else None
        )
        return {
            "id": str(profile.get("id") or ""),
            "name": str(profile.get("name") or raw_sidecar_path(path).name),
            "kind": kind,
            "profile_type": profile_type,
            "recipe": recipe,
            "detail_adjustments": detail_state if isinstance(detail_state, dict) else self._default_detail_adjustment_state(),
            "render_adjustments": render_state if isinstance(render_state, dict) else self._default_render_adjustment_state(),
            "icc_profile_path": input_profile_path,
            "output_icc_profile_path": None,
        }

    def _development_profile_payload_for_active_settings(self) -> dict[str, str]:
        profile_id = self._active_development_profile_id
        if not profile_id and hasattr(self, "development_profile_combo"):
            profile_id = str(self.development_profile_combo.currentData() or "")
        profile = self._development_profile_by_id(profile_id) if profile_id else None
        if profile is None:
            return {"id": "", "name": "Ajustes actuales", "kind": "manual", "profile_type": "basic"}
        kind = str(profile.get("kind") or "manual")
        return {
            "id": profile_id,
            "name": str(profile.get("name") or profile_id),
            "kind": kind,
            "profile_type": str(profile.get("profile_type") or self._adjustment_profile_type_for_kind(kind)),
        }

    def _profile_payload_from_development_settings(self, settings: dict[str, Any]) -> dict[str, str]:
        kind = str(settings.get("kind") or "manual")
        profile_type = str(settings.get("profile_type") or self._adjustment_profile_type_for_kind(kind))
        return {
            "id": str(settings.get("id") or ""),
            "name": str(settings.get("name") or "Ajustes actuales"),
            "kind": kind,
            "profile_type": profile_type,
        }

    def _render_profile_and_mode_for_development_settings(
        self,
        settings: dict[str, Any],
    ) -> tuple[Path | None, str]:
        recipe = settings["recipe"]
        stored_input_profile = settings.get("icc_profile_path")
        input_profile = (
            stored_input_profile
            if isinstance(stored_input_profile, Path) and stored_input_profile.exists()
            else None
        )
        issue = self._color_management_issue_for_recipe(
            recipe,
            input_profile_path=input_profile,
        )
        if issue is not None:
            raise RuntimeError(issue)
        if is_generic_output_space(recipe.output_space):
            rendered_profile = ensure_generic_output_profile(
                recipe.output_space,
                directory=self._session_generic_profile_dir(),
            )
            generic_key = generic_output_profile(recipe.output_space).key
            if input_profile is not None:
                mode = "converted_srgb" if generic_key == "srgb" else f"converted_{generic_key}"
            else:
                mode = f"standard_{generic_key}_output_icc"
            return rendered_profile, mode
        if input_profile is not None:
            return input_profile, "camera_rgb_with_input_icc"
        raise RuntimeError(self.tr("Gestión de color incompleta"))

    def _assign_development_profile_to_raw_files(
        self,
        profile_id: str,
        files: list[Path],
        *,
        status: str = "assigned",
    ) -> int:
        if not profile_id:
            return 0
        settings = self._development_profile_settings(profile_id)
        rendered_profile, mode = self._render_profile_and_mode_for_development_settings(settings)
        development_profile = self._profile_payload_from_development_settings(settings)
        written = 0
        for path in files:
            if path.suffix.lower() not in RAW_EXTENSIONS:
                continue
            try:
                sidecar = self._write_raw_settings_sidecar(
                    path,
                    recipe=settings["recipe"],
                    development_profile=development_profile,
                    detail_adjustments=settings["detail_adjustments"],
                    render_adjustments=settings["render_adjustments"],
                    profile_path=rendered_profile,
                    color_management_mode=mode,
                    status=status,
                )
            except Exception as exc:
                self._log_preview(f"No se pudo escribir mochila ProbRAW para {path.name}: {exc}")
                continue
            if sidecar is not None:
                written += 1
        if written:
            self._refresh_color_reference_thumbnail_markers()
        return written

    def _active_session_icc_for_settings(self) -> Path | None:
        if not hasattr(self, "path_profile_active"):
            return None
        text = self.path_profile_active.text().strip()
        if not text:
            return None
        path = Path(text).expanduser()
        if not path.exists():
            return None
        allow_rejected = self._active_icc_profile_matches_path(path)
        return path if self._profile_can_be_active(path, allow_rejected=allow_rejected) else None

    def _write_current_development_settings_to_raw(
        self,
        path: Path,
        *,
        status: str = "configured",
        refresh_markers: bool = True,
    ) -> Path | None:
        recipe = self._build_effective_recipe()
        _input_profile, rendered_profile, mode = self._configured_color_profile_for_recipe(recipe)
        render_state = self._render_adjustment_state()
        if hasattr(self, "_output_geometry_adjustment_state"):
            render_state = {
                **render_state,
                "geometry": self._output_geometry_adjustment_state(),
            }
        sidecar = self._write_raw_settings_sidecar(
            path,
            recipe=recipe,
            development_profile=self._development_profile_payload_for_active_settings(),
            detail_adjustments=self._detail_adjustment_state(),
            render_adjustments=render_state,
            profile_path=rendered_profile,
            color_management_mode=mode,
            status=status,
        )
        if sidecar is not None and refresh_markers:
            self._refresh_color_reference_thumbnail_markers()
        return sidecar

    def _render_adjustment_sidecar_signature(self, path: Path) -> str:
        return json.dumps(
            {
                "source": str(path),
                "recipe": asdict(self._build_effective_recipe()),
                "development_profile": self._development_profile_payload_for_active_settings(),
                "detail": self._detail_adjustment_state(),
                "render": self._render_adjustment_state(),
                "geometry": self._output_geometry_adjustment_state() if hasattr(self, "_output_geometry_adjustment_state") else {},
                "profiles": self._current_named_adjustment_profiles_payload(),
                "icc": str(self._active_session_icc_for_settings() or ""),
            },
            sort_keys=True,
            default=str,
        )

    def _schedule_render_adjustment_sidecar_persist(self, *, immediate: bool = False) -> None:
        if int(getattr(self, "_suspend_render_adjustment_autosave", 0) or 0) > 0:
            return
        selected = getattr(self, "_selected_file", None)
        if selected is None or Path(selected).suffix.lower() not in RAW_EXTENSIONS:
            return
        path = Path(selected)
        has_named_color_profile = bool(self._active_named_adjustment_profile_id("color_contrast"))
        geometry_has_effect = bool(
            hasattr(self, "_output_geometry_adjustment_state_has_effect")
            and self._output_geometry_adjustment_state_has_effect()
        )
        if (
            not self._render_adjustment_state_has_effect()
            and not geometry_has_effect
            and not raw_sidecar_path(path).exists()
            and not has_named_color_profile
        ):
            return
        timer = getattr(self, "_render_adjustment_sidecar_timer", None)
        if timer is None:
            self._persist_render_adjustments_for_selected()
            return
        if immediate:
            timer.stop()
            self._persist_render_adjustments_for_selected()
            return
        timer.start(350)

    def _persist_render_adjustments_for_selected(self) -> None:
        selected = getattr(self, "_selected_file", None)
        if selected is None:
            return
        path = Path(selected)
        if path.suffix.lower() not in RAW_EXTENSIONS:
            return
        has_named_color_profile = bool(self._active_named_adjustment_profile_id("color_contrast"))
        geometry_has_effect = bool(
            hasattr(self, "_output_geometry_adjustment_state_has_effect")
            and self._output_geometry_adjustment_state_has_effect()
        )
        if (
            not self._render_adjustment_state_has_effect()
            and not geometry_has_effect
            and not raw_sidecar_path(path).exists()
            and not has_named_color_profile
        ):
            return
        try:
            signature = self._render_adjustment_sidecar_signature(path)
            if signature == getattr(self, "_render_adjustment_sidecar_key", None):
                return
            sidecar = self._write_current_development_settings_to_raw(
                path,
                status="configured",
                refresh_markers=False,
            )
        except Exception as exc:
            self._render_adjustment_sidecar_key = None
            self._log_preview(f"No se pudo actualizar mochila cromatica para {path.name}: {exc}")
            return
        if sidecar is not None:
            self._render_adjustment_sidecar_key = signature
            if hasattr(self, "_refresh_thumbnail_marker_for_path"):
                self._refresh_thumbnail_marker_for_path(path)
            self._save_active_session(silent=True)

    def _flush_render_adjustment_sidecar_persist(self) -> None:
        timer = getattr(self, "_render_adjustment_sidecar_timer", None)
        if timer is not None:
            timer.stop()
        self._persist_render_adjustments_for_selected()

    def _detail_adjustment_sidecar_signature(self, path: Path) -> str:
        return json.dumps(
            {
                "source": str(path),
                "recipe": asdict(self._build_effective_recipe()),
                "development_profile": self._development_profile_payload_for_active_settings(),
                "detail": self._detail_adjustment_state(),
                "render": self._render_adjustment_state(),
                "profiles": self._current_named_adjustment_profiles_payload(),
                "icc": str(self._active_session_icc_for_settings() or ""),
            },
            sort_keys=True,
            default=str,
        )

    def _schedule_detail_adjustment_sidecar_persist(self, *, immediate: bool = False) -> None:
        if int(getattr(self, "_suspend_detail_adjustment_autosave", 0) or 0) > 0:
            return
        selected = getattr(self, "_selected_file", None)
        if selected is None or Path(selected).suffix.lower() not in RAW_EXTENSIONS:
            return
        path = Path(selected)
        has_named_detail_profile = bool(self._active_named_adjustment_profile_id("detail"))
        if (
            not self._detail_adjustment_state_has_effect()
            and not raw_sidecar_path(path).exists()
            and not has_named_detail_profile
        ):
            return
        timer = getattr(self, "_detail_adjustment_sidecar_timer", None)
        if timer is None:
            self._persist_detail_adjustments_for_selected()
            return
        if immediate:
            timer.stop()
            self._persist_detail_adjustments_for_selected()
            return
        timer.start(350)

    def _persist_detail_adjustments_for_selected(self) -> None:
        selected = getattr(self, "_selected_file", None)
        if selected is None:
            return
        path = Path(selected)
        if path.suffix.lower() not in RAW_EXTENSIONS:
            return
        has_named_detail_profile = bool(self._active_named_adjustment_profile_id("detail"))
        if (
            not self._detail_adjustment_state_has_effect()
            and not raw_sidecar_path(path).exists()
            and not has_named_detail_profile
        ):
            return
        try:
            signature = self._detail_adjustment_sidecar_signature(path)
            if signature == getattr(self, "_detail_adjustment_sidecar_key", None):
                return
            sidecar = self._write_current_development_settings_to_raw(
                path,
                status="configured",
                refresh_markers=False,
            )
        except Exception as exc:
            self._detail_adjustment_sidecar_key = None
            self._log_preview(f"No se pudo actualizar mochila de nitidez para {path.name}: {exc}")
            return
        if sidecar is not None:
            self._detail_adjustment_sidecar_key = signature
            if hasattr(self, "_refresh_thumbnail_marker_for_path"):
                self._refresh_thumbnail_marker_for_path(path)
            self._save_active_session(silent=True)

    def _flush_detail_adjustment_sidecar_persist(self) -> None:
        timer = getattr(self, "_detail_adjustment_sidecar_timer", None)
        if timer is not None:
            timer.stop()
        self._persist_detail_adjustments_for_selected()

    def _raw_export_sidecar_signature(self, path: Path) -> str:
        return json.dumps(
            {
                "source": str(path),
                "raw_recipe": asdict(self._raw_export_recipe_from_current_controls()),
                "profiles": self._current_named_adjustment_profiles_payload(),
                "icc": str(self._active_session_icc_for_settings() or ""),
            },
            sort_keys=True,
            default=str,
        )

    def _schedule_raw_export_sidecar_persist(self, *, immediate: bool = False) -> None:
        if int(getattr(self, "_suspend_raw_export_autosave", 0) or 0) > 0:
            return
        selected = getattr(self, "_selected_file", None)
        if selected is None or Path(selected).suffix.lower() not in RAW_EXTENSIONS:
            return
        path = Path(selected)
        has_named_raw_profile = bool(self._active_named_adjustment_profile_id("raw_export"))
        has_raw_effect = self._raw_export_recipe_has_effect(self._build_effective_recipe())
        if not has_raw_effect and not raw_sidecar_path(path).exists() and not has_named_raw_profile:
            return
        timer = getattr(self, "_raw_export_sidecar_timer", None)
        if timer is None:
            self._persist_raw_export_settings_for_selected()
            return
        if immediate:
            timer.stop()
            self._persist_raw_export_settings_for_selected()
            return
        timer.start(350)

    def _persist_raw_export_settings_for_selected(self) -> None:
        selected = getattr(self, "_selected_file", None)
        if selected is None:
            return
        path = Path(selected)
        if path.suffix.lower() not in RAW_EXTENSIONS:
            return
        has_named_raw_profile = bool(self._active_named_adjustment_profile_id("raw_export"))
        has_raw_effect = self._raw_export_recipe_has_effect(self._build_effective_recipe())
        if not has_raw_effect and not raw_sidecar_path(path).exists() and not has_named_raw_profile:
            return
        try:
            signature = self._raw_export_sidecar_signature(path)
            if signature == getattr(self, "_raw_export_sidecar_key", None):
                return
            sidecar = self._write_current_development_settings_to_raw(
                path,
                status="configured",
                refresh_markers=False,
            )
        except Exception as exc:
            self._raw_export_sidecar_key = None
            self._log_preview(f"No se pudo actualizar mochila RAW para {path.name}: {exc}")
            return
        if sidecar is not None:
            self._raw_export_sidecar_key = signature
            if hasattr(self, "_refresh_thumbnail_marker_for_path"):
                self._refresh_thumbnail_marker_for_path(path)
            self._save_active_session(silent=True)

    def _flush_raw_export_sidecar_persist(self) -> None:
        timer = getattr(self, "_raw_export_sidecar_timer", None)
        if timer is not None:
            timer.stop()
        self._persist_raw_export_settings_for_selected()

    def _flush_pending_adjustment_sidecar_persists_for_file_change(self) -> None:
        pending_flushes = (
            ("_render_adjustment_sidecar_timer", self._persist_render_adjustments_for_selected),
            ("_detail_adjustment_sidecar_timer", self._persist_detail_adjustments_for_selected),
            ("_raw_export_sidecar_timer", self._persist_raw_export_settings_for_selected),
        )
        for timer_name, persist in pending_flushes:
            timer = getattr(self, timer_name, None)
            if timer is None or not timer.isActive():
                continue
            timer.stop()
            try:
                persist()
            except Exception as exc:
                self._log_preview(f"Aviso: no se pudo guardar ajustes pendientes antes de cambiar de archivo: {exc}")

    def _raw_sidecar_development_summary(self, path: Path) -> str:
        if hasattr(self, "_cached_raw_sidecar_payload"):
            payload = self._cached_raw_sidecar_payload(path)
        else:
            try:
                payload = load_raw_sidecar(path)
            except Exception:
                payload = None
        if payload is None:
            return ""
        profile = payload.get("development_profile") if isinstance(payload.get("development_profile"), dict) else {}
        profile_type = self._adjustment_profile_type_from_sidecar(payload)
        name = str(profile.get("name") or profile.get("id") or "").strip()
        status = str(payload.get("status") or "").strip()
        label = "Perfil de ajuste avanzado" if profile_type == "advanced" else "Perfil de ajuste básico"
        if name:
            return f"{label}: {name}"
        if isinstance(payload.get("recipe"), dict):
            return f"{label} guardado"
        if isinstance(payload.get("mtf_analysis"), dict):
            return ""
        return f"Mochila ProbRAW: {status}" if status else ""

    def _has_raw_development_settings(self, path: Path) -> bool:
        if path.suffix.lower() not in RAW_EXTENSIONS:
            return False
        return bool(self._raw_sidecar_development_summary(path))

    def _adjustment_profile_type_from_sidecar(self, payload: dict[str, Any]) -> str:
        profile = payload.get("development_profile") if isinstance(payload.get("development_profile"), dict) else {}
        profile_type = str(profile.get("profile_type") or "").strip().lower()
        if profile_type in {"advanced", "basic"}:
            return profile_type
        kind = str(profile.get("kind") or "").strip().lower()
        if kind in {"chart", "advanced"}:
            return "advanced"
        return "basic" if isinstance(payload.get("recipe"), dict) else ""

    def _raw_adjustment_profile_type(self, path: Path) -> str:
        if path.suffix.lower() not in RAW_EXTENSIONS:
            return ""
        if hasattr(self, "_cached_raw_sidecar_payload"):
            payload = self._cached_raw_sidecar_payload(path)
        else:
            try:
                payload = load_raw_sidecar(path)
            except Exception:
                payload = None
        if payload is None:
            return ""
        return self._adjustment_profile_type_from_sidecar(payload)

    def _development_settings_payload_from_sidecar(self, source: Path, sidecar: dict[str, Any]) -> dict[str, Any]:
        return {
            "source": str(source),
            "recipe": sidecar.get("recipe") if isinstance(sidecar.get("recipe"), dict) else {},
            "development_profile": sidecar.get("development_profile")
            if isinstance(sidecar.get("development_profile"), dict)
            else {},
            "adjustment_profiles": sidecar.get("adjustment_profiles")
            if isinstance(sidecar.get("adjustment_profiles"), dict)
            else {},
            "detail_adjustments": sidecar.get("detail_adjustments")
            if isinstance(sidecar.get("detail_adjustments"), dict)
            else {},
            "render_adjustments": sidecar.get("render_adjustments")
            if isinstance(sidecar.get("render_adjustments"), dict)
            else {},
            "color_management": sidecar.get("color_management")
            if isinstance(sidecar.get("color_management"), dict)
            else {},
        }

    def _selected_or_current_file_paths(self) -> list[Path]:
        files = self._collect_selected_file_paths()
        if files:
            return files
        if self._selected_file is not None and self._selected_file.exists():
            return [self._selected_file]
        return []

    def _save_current_development_settings_to_selected(self) -> None:
        files = [p for p in self._selected_or_current_file_paths() if p.suffix.lower() in RAW_EXTENSIONS]
        if not files:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("Selecciona uno o más RAW para guardar un perfil básico."))
            return
        written = 0
        errors: list[tuple[Path, Exception]] = []
        for path in files:
            try:
                if self._write_current_development_settings_to_raw(path) is not None:
                    written += 1
            except Exception as exc:
                errors.append((path, exc))
        if self._selected_file is not None and any(self._normalized_path_key(self._selected_file) == self._normalized_path_key(p) for p in files):
            self._apply_raw_sidecar_to_controls(self._selected_file)
        if errors:
            first_path, first_error = errors[0]
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("No se pudo escribir mochila"),
                self.tr("Fallaron") + f" {len(errors)} " + self.tr("archivo(s). Primer error:")
                + f"\n{first_path}\n{first_error}",
            )
        self._set_status(self.tr("Perfil básico guardado en") + f" {written} " + self.tr("imagen(es)"))

    def _all_adjustment_copy_categories(self) -> tuple[str, ...]:
        return ("icc", "color_contrast", "detail", "raw_export")

    def _adjustment_copy_category_title(self, category: str) -> str:
        labels = {
            "icc": self.tr("Perfil ICC"),
            "color_contrast": self.tr("Color y contraste"),
            "detail": self.tr("Nitidez"),
            "raw_export": self.tr("RAW / exportación"),
        }
        return labels.get(category, category)

    def _adjustment_copy_categories_label(self, categories: tuple[str, ...]) -> str:
        if set(categories) == set(self._all_adjustment_copy_categories()):
            return self.tr("todos los ajustes")
        return ", ".join(self._adjustment_copy_category_title(category) for category in categories)

    def _has_adjustment_settings_clipboard(self) -> bool:
        copied = getattr(self, "_adjustment_settings_clipboard", None)
        if isinstance(copied, dict) and copied.get("categories"):
            return True
        return bool(getattr(self, "_development_settings_clipboard", None))

    def _sidecar_has_adjustment_category(self, sidecar: dict[str, Any], category: str) -> bool:
        profiles = sidecar.get("adjustment_profiles") if isinstance(sidecar.get("adjustment_profiles"), dict) else {}
        profile = profiles.get(category) if isinstance(profiles, dict) else None
        if isinstance(profile, dict) and str(profile.get("id") or profile.get("name") or "").strip():
            return True
        if category == "icc":
            color = sidecar.get("color_management") if isinstance(sidecar.get("color_management"), dict) else {}
            return bool(str(color.get("icc_profile_path") or color.get("mode") or "").strip())
        if category == "color_contrast":
            render = sidecar.get("render_adjustments") if isinstance(sidecar.get("render_adjustments"), dict) else {}
            return bool(self._render_adjustment_state_has_effect(render))
        if category == "detail":
            detail = sidecar.get("detail_adjustments") if isinstance(sidecar.get("detail_adjustments"), dict) else {}
            return bool(self._detail_adjustment_state_has_effect(detail))
        if category == "raw_export":
            recipe = self._recipe_from_payload(sidecar.get("recipe"))
            return bool(self._raw_export_recipe_has_effect(recipe))
        return False

    def _adjustment_clipboard_payload_from_sidecar(
        self,
        source: Path,
        sidecar: dict[str, Any],
        categories: tuple[str, ...],
        *,
        copy_all: bool,
    ) -> dict[str, Any]:
        payload = self._development_settings_payload_from_sidecar(source, sidecar)
        payload["categories"] = list(categories)
        payload["copy_all"] = bool(copy_all)
        return payload

    def _copy_adjustments_from_selected(self, categories: tuple[str, ...]) -> None:
        requested = tuple(category for category in categories if category in self._all_adjustment_copy_categories())
        if not requested:
            return
        files = [p for p in self._selected_or_current_file_paths() if p.suffix.lower() in RAW_EXTENSIONS]
        if not files:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("Selecciona un RAW con ajustes guardados."))
            return
        source = files[0]
        try:
            sidecar = load_raw_sidecar(source)
        except FileNotFoundError:
            QtWidgets.QMessageBox.information(
                self,
                self.tr("Info"),
                self.tr("Esta imagen todavía no tiene mochila ProbRAW con ajustes guardados."),
            )
            return
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, self.tr("Mochila no válida"), str(exc))
            return

        all_categories = self._all_adjustment_copy_categories()
        copy_all = set(requested) == set(all_categories)
        if copy_all and self._recipe_from_payload(sidecar.get("recipe")) is None:
            QtWidgets.QMessageBox.information(
                self,
                self.tr("Info"),
                self.tr("La mochila de esta imagen no contiene ajustes copiables."),
            )
            return
        available_categories = tuple(category for category in all_categories if self._sidecar_has_adjustment_category(sidecar, category))
        copied_categories = all_categories if copy_all else tuple(
            category for category in requested if self._sidecar_has_adjustment_category(sidecar, category)
        )
        if not copied_categories:
            QtWidgets.QMessageBox.information(
                self,
                self.tr("Info"),
                self.tr("La imagen no contiene ese tipo de ajuste aplicado."),
            )
            return

        copied = self._adjustment_clipboard_payload_from_sidecar(
            source,
            sidecar,
            copied_categories,
            copy_all=copy_all,
        )
        self._adjustment_settings_clipboard = copied
        copied["available_categories"] = list(available_categories)
        if copy_all:
            self._development_settings_clipboard = copied
        for category in copied_categories:
            state = self._copied_category_state(copied, category)
            if isinstance(state, dict):
                setattr(self, f"_{category}_profile_clipboard", {"source": str(source), "category": category, "state": state})
        self._set_status(
            self.tr("Copiado")
            + " "
            + self._adjustment_copy_categories_label(tuple(copied_categories))
            + self.tr(" desde ")
            + source.name
        )

    def _copied_category_state(self, copied: dict[str, Any], category: str) -> dict[str, Any] | None:
        if category == "color_contrast":
            state = copied.get("render_adjustments")
            return dict(state) if isinstance(state, dict) else None
        if category == "detail":
            state = copied.get("detail_adjustments")
            return dict(state) if isinstance(state, dict) else None
        if category == "raw_export":
            recipe = self._recipe_from_payload(copied.get("recipe"))
            return asdict(self._raw_export_recipe_subset(recipe)) if recipe is not None else None
        if category == "icc":
            color = copied.get("color_management")
            return dict(color) if isinstance(color, dict) else None
        return None

    def _copied_adjustment_profile_payload(self, copied: dict[str, Any], category: str) -> dict[str, str]:
        profiles = copied.get("adjustment_profiles") if isinstance(copied.get("adjustment_profiles"), dict) else {}
        profile = profiles.get(category) if isinstance(profiles, dict) else None
        if isinstance(profile, dict) and str(profile.get("id") or profile.get("name") or "").strip():
            return {
                "id": str(profile.get("id") or ""),
                "name": str(profile.get("name") or profile.get("id") or ""),
                "kind": str(profile.get("kind") or category),
            }
        if category == "icc":
            color = copied.get("color_management") if isinstance(copied.get("color_management"), dict) else {}
            raw_path = str(color.get("icc_profile_path") or "").strip()
            name = Path(raw_path).name if raw_path else self.tr("ICC copiado")
        else:
            name = self.tr("Ajustes copiados")
        return {"id": "", "name": str(name), "kind": category}

    def _apply_copied_icc_to_bundle(
        self,
        bundle: dict[str, Any],
        copied: dict[str, Any],
        source_recipe: Recipe,
    ) -> None:
        recipe = Recipe(**asdict(bundle["recipe"]))
        for field_name in (
            "output_space",
            "output_linear",
            "tone_curve",
            "profiling_mode",
            "input_color_assumption",
            "illuminant_metadata",
        ):
            if hasattr(source_recipe, field_name):
                setattr(recipe, field_name, getattr(source_recipe, field_name))
        color = copied.get("color_management") if isinstance(copied.get("color_management"), dict) else {}
        mode = str(color.get("mode") or "")
        profile_path = self._icc_profile_path_from_copied_settings(copied)
        if profile_path is None and is_generic_output_space(recipe.output_space):
            profile_path = ensure_generic_output_profile(
                recipe.output_space,
                directory=self._session_generic_profile_dir(),
            )
            mode = mode or f"standard_{generic_output_profile(recipe.output_space).key}_output_icc"
        elif profile_path is not None and not mode:
            mode = "camera_rgb_with_input_icc" if not is_generic_output_space(recipe.output_space) else f"standard_{generic_output_profile(recipe.output_space).key}_output_icc"
        elif profile_path is None:
            mode = mode or "no_profile"
        bundle["recipe"] = recipe
        bundle["profile_path"] = profile_path
        bundle["color_management_mode"] = mode

    def _show_adjustment_paste_errors(self, errors: list[tuple[Path, Exception]]) -> None:
        if not errors:
            return
        first_path, first_error = errors[0]
        QtWidgets.QMessageBox.warning(
            self,
            self.tr("No se pudo escribir mochila"),
            self.tr("Fallaron") + f" {len(errors)} " + self.tr("archivo(s). Primer error:")
            + f"\n{first_path}\n{first_error}",
        )

    def _paste_full_copied_adjustments_to_files(self, copied: dict[str, Any], files: list[Path]) -> int:
        recipe = self._recipe_from_payload(copied.get("recipe"))
        if recipe is None:
            QtWidgets.QMessageBox.warning(self, self.tr("Mochila no válida"), self.tr("El ajuste copiado no contiene una receta válida."))
            return 0
        profile = copied.get("development_profile") if isinstance(copied.get("development_profile"), dict) else {}
        adjustment_profiles = copied.get("adjustment_profiles") if isinstance(copied.get("adjustment_profiles"), dict) else {}
        adjustment_profiles = dict(adjustment_profiles)
        profile_categories = copied.get("available_categories") or copied.get("categories") or self._all_adjustment_copy_categories()
        for category in profile_categories:
            if category in self._all_adjustment_copy_categories():
                adjustment_profiles[category] = self._copied_adjustment_profile_payload(copied, category)
        detail = copied.get("detail_adjustments") if isinstance(copied.get("detail_adjustments"), dict) else {}
        render = copied.get("render_adjustments") if isinstance(copied.get("render_adjustments"), dict) else {}
        icc_path = self._icc_profile_path_from_copied_settings(copied)
        mode = str((copied.get("color_management") or {}).get("mode") or "")
        input_profile_for_issue = icc_path if not is_generic_output_space(recipe.output_space) else None
        if not self._require_color_managed_recipe_for_ui(
            recipe,
            input_profile_path=input_profile_for_issue,
            title=self.tr("Perfil de ajuste incompleto"),
        ):
            return 0
        written = 0
        errors: list[tuple[Path, Exception]] = []
        profile_id = str(profile.get("id") or "")
        for path in files:
            try:
                sidecar = self._write_raw_settings_sidecar(
                    path,
                    recipe=recipe,
                    development_profile=profile,
                    adjustment_profiles=adjustment_profiles,
                    detail_adjustments=detail,
                    render_adjustments=render,
                    profile_path=icc_path,
                    color_management_mode=mode or ("camera_rgb_with_input_icc" if icc_path is not None else "no_profile"),
                    status="configured",
                )
            except Exception as exc:
                errors.append((path, exc))
                sidecar = None
            if sidecar is not None:
                written += 1
            if profile_id:
                for item in self._develop_queue:
                    if self._normalized_path_key(Path(str(item.get("source") or ""))) == self._normalized_path_key(path):
                        item["development_profile_id"] = profile_id
                        item["status"] = "pending"
                        item["message"] = ""
        self._show_adjustment_paste_errors(errors)
        return written

    def _paste_partial_copied_adjustments_to_files(self, copied: dict[str, Any], files: list[Path]) -> int:
        source_recipe = self._recipe_from_payload(copied.get("recipe"))
        if source_recipe is None:
            QtWidgets.QMessageBox.warning(self, self.tr("Mochila no válida"), self.tr("El ajuste copiado no contiene una receta válida."))
            return 0
        categories = tuple(category for category in copied.get("categories") or () if category in self._all_adjustment_copy_categories())
        written = 0
        errors: list[tuple[Path, Exception]] = []
        for path in files:
            try:
                bundle = self._sidecar_bundle_for_category_write(path)
                adjustment_profiles = bundle["adjustment_profiles"]
                for category in categories:
                    if category == "icc":
                        self._apply_copied_icc_to_bundle(bundle, copied, source_recipe)
                    elif category == "color_contrast":
                        state = copied.get("render_adjustments")
                        if isinstance(state, dict):
                            bundle["render_adjustments"] = dict(state)
                            bundle["recipe"] = self._merge_libraw_color_state_into_recipe(bundle["recipe"], state)
                    elif category == "detail":
                        state = copied.get("detail_adjustments")
                        if isinstance(state, dict):
                            bundle["detail_adjustments"] = dict(state)
                    elif category == "raw_export":
                        raw_state = self._raw_export_recipe_subset(source_recipe)
                        bundle["recipe"] = self._merge_raw_export_recipe(bundle["recipe"], raw_state)
                    adjustment_profiles[category] = self._copied_adjustment_profile_payload(copied, category)
                sidecar = self._write_raw_settings_sidecar(path, status="configured", **bundle)
            except Exception as exc:
                errors.append((path, exc))
                sidecar = None
            if sidecar is not None:
                written += 1
        self._show_adjustment_paste_errors(errors)
        return written

    def _paste_adjustments_to_selected(self) -> None:
        copied = getattr(self, "_adjustment_settings_clipboard", None)
        if not isinstance(copied, dict):
            copied = getattr(self, "_development_settings_clipboard", None)
            if isinstance(copied, dict):
                copied = self._adjustment_clipboard_payload_from_sidecar(
                    Path(str(copied.get("source") or "")),
                    copied,
                    self._all_adjustment_copy_categories(),
                    copy_all=True,
                )
        if not isinstance(copied, dict) or not copied.get("categories"):
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("Copia primero ajustes desde una miniatura."))
            return
        files = [p for p in self._selected_or_current_file_paths() if p.suffix.lower() in RAW_EXTENSIONS]
        if not files:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("Selecciona uno o más RAW de destino."))
            return
        targets = {self._normalized_path_key(path) for path in files}
        if bool(copied.get("copy_all")):
            written = self._paste_full_copied_adjustments_to_files(copied, files)
        else:
            written = self._paste_partial_copied_adjustments_to_files(copied, files)
        self._refresh_queue_table()
        self._refresh_color_reference_thumbnail_markers()
        self._save_active_session(silent=True)
        if self._selected_file is not None and self._normalized_path_key(self._selected_file) in targets:
            self._apply_raw_sidecar_to_controls(self._selected_file)
            if self._original_linear is not None:
                self._on_load_selected(show_message=False)
        self._set_status(
            self.tr("Pegado")
            + " "
            + self._adjustment_copy_categories_label(tuple(copied.get("categories") or ()))
            + self.tr(" en ")
            + f"{written} "
            + self.tr("imagen(es)")
        )

    def _copy_development_settings_from_selected(self) -> None:
        self._copy_adjustments_from_selected(self._all_adjustment_copy_categories())

    def _icc_profile_path_from_copied_settings(self, copied: dict[str, Any]) -> Path | None:
        color = copied.get("color_management") if isinstance(copied.get("color_management"), dict) else {}
        raw_path = str(color.get("icc_profile_path") or "").strip()
        if not raw_path:
            return None
        stored = self._session_stored_path(raw_path)
        if stored is not None and stored.exists():
            return stored
        path = Path(raw_path).expanduser()
        return path if path.exists() else None

    def _paste_development_settings_to_selected(self) -> None:
        self._paste_adjustments_to_selected()

    def _default_unconfigured_recipe(self) -> Recipe:
        recipe = Recipe(
            white_balance_mode="camera_metadata",
            output_space="prophoto_rgb",
            profiling_mode=False,
        )
        return self._normalize_recipe_output_for_color_management(recipe)

    def _clear_active_input_profile_for_unconfigured_file(self) -> None:
        if hasattr(self, "path_profile_active"):
            self.path_profile_active.clear()
        if hasattr(self, "chk_apply_profile"):
            self.chk_apply_profile.setChecked(False)
        self._active_icc_profile_id = ""
        self._refresh_profile_management_views()

    def _reset_development_controls_for_unconfigured_file(self) -> None:
        self._apply_recipe_to_controls(self._default_unconfigured_recipe())
        self._apply_detail_adjustment_state(self._default_detail_adjustment_state())
        self._apply_render_adjustment_state(self._default_render_adjustment_state())
        if hasattr(self, "_apply_output_geometry_adjustment_state"):
            self._apply_output_geometry_adjustment_state(None)
        self._active_development_profile_id = ""
        self._refresh_development_profile_combo()
        self._clear_active_input_profile_for_unconfigured_file()
        self._invalidate_preview_cache()
        if hasattr(self, "_reset_edit_history_to_current"):
            self._reset_edit_history_to_current()

    def _apply_raw_sidecar_to_controls(self, path: Path) -> bool:
        try:
            payload = load_raw_sidecar(path)
        except FileNotFoundError:
            return False
        except Exception as exc:
            self._log_preview(f"Aviso: no se pudo leer mochila ProbRAW ({raw_sidecar_path(path).name}): {exc}")
            return False

        raw_suspend = int(getattr(self, "_suspend_raw_export_autosave", 0) or 0)
        render_suspend = int(getattr(self, "_suspend_render_adjustment_autosave", 0) or 0)
        detail_suspend = int(getattr(self, "_suspend_detail_adjustment_autosave", 0) or 0)
        self._suspend_raw_export_autosave = raw_suspend + 1
        self._suspend_render_adjustment_autosave = render_suspend + 1
        self._suspend_detail_adjustment_autosave = detail_suspend + 1

        color = payload.get("color_management") if isinstance(payload.get("color_management"), dict) else {}
        icc_path = self._session_stored_path(color.get("icc_profile_path")) if color else None
        icc_role = str(color.get("icc_profile_role") or "") if color else ""
        adjustment_profiles = payload.get("adjustment_profiles") if isinstance(payload.get("adjustment_profiles"), dict) else {}
        icc_profile_payload = adjustment_profiles.get("icc") if isinstance(adjustment_profiles, dict) else {}
        icc_profile_id = str(icc_profile_payload.get("id") or "") if isinstance(icc_profile_payload, dict) else ""
        registered_icc_profile = self._icc_profile_by_id(icc_profile_id) if icc_profile_id else None
        registered_icc_path = self._session_stored_path(registered_icc_profile.get("path")) if registered_icc_profile else None
        allow_rejected_icc = bool(
            icc_path is not None
            and registered_icc_path is not None
            and self._paths_equivalent(registered_icc_path, icc_path)
        )
        input_profile_for_recipe = (
            icc_path
            if icc_role == "session_input_icc"
            and icc_path is not None
            and icc_path.exists()
            and self._profile_can_be_active(icc_path, allow_rejected=allow_rejected_icc)
            else None
        )
        recipe = self._recipe_from_payload(payload.get("recipe")) or self._default_unconfigured_recipe()
        recipe = self._visible_export_recipe_for_color_management(
            recipe,
            input_profile_path=input_profile_for_recipe,
        )
        self._apply_recipe_to_controls(recipe)
        detail_state = payload.get("detail_adjustments")
        self._apply_detail_adjustment_state(
            detail_state if isinstance(detail_state, dict) else self._default_detail_adjustment_state()
        )
        render_state = payload.get("render_adjustments")
        self._apply_render_adjustment_state(
            render_state if isinstance(render_state, dict) else self._default_render_adjustment_state()
        )
        geometry_state = render_state.get("geometry") if isinstance(render_state, dict) else None
        if hasattr(self, "_apply_output_geometry_adjustment_state"):
            self._apply_output_geometry_adjustment_state(geometry_state)

        profile = payload.get("development_profile") if isinstance(payload.get("development_profile"), dict) else {}
        profile_id = str(profile.get("id") or "")
        if profile_id and self._development_profile_by_id(profile_id) is not None:
            self._active_development_profile_id = profile_id
            self._refresh_development_profile_combo()
        else:
            self._active_development_profile_id = ""
            self._refresh_development_profile_combo()

        for category in ("color_contrast", "detail", "raw_export"):
            category_payload = adjustment_profiles.get(category) if isinstance(adjustment_profiles, dict) else {}
            category_id = str(category_payload.get("id") or "") if isinstance(category_payload, dict) else ""
            if category_id and self._named_adjustment_profile_by_id(category, category_id) is not None:
                self._set_active_named_adjustment_profile_id(category, category_id)
            else:
                self._set_active_named_adjustment_profile_id(category, "")
        self._refresh_named_adjustment_profile_combos()

        if (
            icc_role == "session_input_icc"
            and icc_path is not None
            and icc_path.exists()
            and self._profile_can_be_active(icc_path, allow_rejected=allow_rejected_icc)
        ):
            self.path_profile_active.setText(str(icc_path))
            self.chk_apply_profile.setChecked(True)
            self._active_icc_profile_id = icc_profile_id
            if not self._active_icc_profile_id:
                self._sync_active_icc_profile_id_from_path()
            self._refresh_profile_management_views()
        else:
            self._clear_active_input_profile_for_unconfigured_file()

        self._suspend_raw_export_autosave = raw_suspend
        self._suspend_render_adjustment_autosave = render_suspend
        self._suspend_detail_adjustment_autosave = detail_suspend
        self._invalidate_preview_cache()
        self._log_preview(f"Mochila ProbRAW aplicada: {raw_sidecar_path(path).name}")
        if hasattr(self, "_reset_edit_history_to_current"):
            self._reset_edit_history_to_current()
        return True

    def _sync_selected_sidecar_to_preview(self, path: Path, *, status_message: str | None = None) -> bool:
        selected = getattr(self, "_selected_file", None)
        if selected is None:
            return False
        try:
            selected_key = self._normalized_path_key(Path(selected))
            path_key = self._normalized_path_key(Path(path))
        except Exception:
            selected_key = str(selected)
            path_key = str(path)
        if selected_key != path_key:
            return False
        if not self._apply_raw_sidecar_to_controls(Path(selected)):
            return False
        if status_message:
            self._log_preview(status_message)
        if getattr(self, "_original_linear", None) is not None:
            self._on_load_selected(show_message=False)
        return True

    def _write_raw_settings_sidecar(
        self,
        source: Path,
        *,
        recipe: Recipe,
        development_profile: dict[str, Any] | None,
        detail_adjustments: dict[str, Any],
        render_adjustments: dict[str, Any],
        profile_path: Path | None,
        adjustment_profiles: dict[str, Any] | None = None,
        color_management_mode: str | None = None,
        output_tiff: Path | None = None,
        proof_path: Path | None = None,
        source_sha256: str | None = None,
        status: str = "configured",
    ) -> Path | None:
        if source.suffix.lower() not in RAW_EXTENSIONS:
            return None
        session_name = self.session_name_edit.text().strip() if hasattr(self, "session_name_edit") else ""
        sidecar = write_raw_sidecar(
            source,
            recipe=recipe,
            development_profile=development_profile,
            adjustment_profiles=adjustment_profiles or self._current_named_adjustment_profiles_payload(),
            detail_adjustments=detail_adjustments,
            render_adjustments=render_adjustments,
            icc_profile_path=profile_path,
            color_management_mode=color_management_mode,
            session_root=self._active_session_root,
            session_name=session_name,
            output_tiff=output_tiff,
            proof_path=proof_path,
            source_sha256=source_sha256,
            status=status,
        )
        if hasattr(self, "_invalidate_raw_sidecar_cache_for_path"):
            self._invalidate_raw_sidecar_cache_for_path(source)
        return sidecar

    def _save_current_development_profile(self) -> None:
        if self._active_session_root is None:
            self._on_create_session()
            if self._active_session_root is None:
                return
        name = self.development_profile_name_edit.text().strip() or "Perfil manual"
        profile_id = self._unique_development_profile_id(name)
        recipe = self._build_effective_recipe()
        active_icc = self._active_session_icc_for_settings()
        if not self._require_color_managed_recipe_for_ui(
            recipe,
            input_profile_path=active_icc,
            title=self.tr("Perfil de ajuste incompleto"),
        ):
            return
        output_icc = None
        if is_generic_output_space(recipe.output_space):
            try:
                output_icc = ensure_generic_output_profile(recipe.output_space, directory=self._session_generic_profile_dir())
            except Exception as exc:
                QtWidgets.QMessageBox.warning(
                    self,
                    self.tr("Perfil ICC estándar no disponible"),
                    str(exc),
                )
                return
        profile_dir = self._development_profile_dir(profile_id)
        profile_dir.mkdir(parents=True, exist_ok=True)
        recipe_path = profile_dir / "recipe.yml"
        manifest_path = profile_dir / "development_profile.json"
        save_recipe(recipe, recipe_path)
        manifest = {
            "id": profile_id,
            "name": name,
            "kind": "manual",
            "profile_type": "basic",
            "created_at": self._profile_timestamp(),
            "recipe_path": self._session_relative_or_absolute(recipe_path),
            "recipe": asdict(recipe),
            "detail_adjustments": self._detail_adjustment_state(),
            "render_adjustments": self._render_adjustment_state(),
            "icc_profile_path": self._session_relative_or_absolute(active_icc) if active_icc and active_icc.exists() else "",
            "generic_output_space": generic_output_profile(recipe.output_space).key if is_generic_output_space(recipe.output_space) else "",
            "output_icc_profile_path": self._session_relative_or_absolute(output_icc) if output_icc and output_icc.exists() else "",
        }
        write_json(manifest_path, manifest)
        self._register_development_profile(
            {
                "id": profile_id,
                "name": name,
                "kind": "manual",
                "profile_type": "basic",
                "recipe_path": self._session_relative_or_absolute(recipe_path),
                "manifest_path": self._session_relative_or_absolute(manifest_path),
                "icc_profile_path": manifest["icc_profile_path"],
                "generic_output_space": manifest["generic_output_space"],
                "output_icc_profile_path": manifest["output_icc_profile_path"],
            },
            activate=True,
        )
        self._set_status(self.tr("Perfil de ajuste básico guardado:") + f" {name}")

    def _activate_selected_development_profile(self) -> None:
        profile_id = str(self.development_profile_combo.currentData() or "")
        self._apply_development_profile_to_controls(profile_id)

    def _apply_development_profile_to_controls(self, profile_id: str) -> None:
        settings = self._development_profile_settings(profile_id)
        input_profile = settings.get("icc_profile_path")
        recipe = self._visible_export_recipe_for_color_management(
            settings["recipe"],
            input_profile_path=input_profile if isinstance(input_profile, Path) and input_profile.exists() else None,
        )
        self._apply_recipe_to_controls(recipe)
        profile = self._development_profile_by_id(profile_id) if profile_id else None
        recipe_path = self._session_stored_path(profile.get("recipe_path")) if profile else None
        if recipe_path is not None:
            self.path_recipe.setText(str(recipe_path))
        self._apply_detail_adjustment_state(settings["detail_adjustments"])
        self._apply_render_adjustment_state(settings["render_adjustments"])
        self._apply_output_space_defaults_to_controls(recipe.output_space)
        icc_path = settings.get("icc_profile_path")
        if (
            isinstance(icc_path, Path)
            and icc_path.exists()
            and self._profile_can_be_active(icc_path, allow_rejected=bool(profile_id))
        ):
            self.path_profile_active.setText(str(icc_path))
            self.chk_apply_profile.setChecked(True)
            self._sync_active_icc_profile_id_from_path()
            self._refresh_profile_management_views()
        elif is_generic_output_space(settings["recipe"].output_space):
            self.path_profile_active.clear()
            self.chk_apply_profile.setChecked(False)
            self._sync_active_icc_profile_id_from_path()
            self._refresh_profile_management_views()
        self._active_development_profile_id = profile_id
        self._refresh_development_profile_combo()
        self._invalidate_preview_cache()
        self._save_active_session(silent=True)
        self._set_status(self.tr("Perfil de ajuste activo:") + f" {settings['name']}")

    def _register_chart_development_profile(
        self,
        *,
        name: str,
        development_profile_path: Path,
        calibrated_recipe_path: Path,
        icc_profile_path: Path,
        profile_report_path: Path,
    ) -> str:
        if self._active_session_root is None:
            return ""
        profile_id = self._unique_development_profile_id(name)
        try:
            payload = json.loads(development_profile_path.read_text(encoding="utf-8")) if development_profile_path.exists() else {}
            if not isinstance(payload, dict):
                payload = {}
            payload.update(
                {
                    "id": profile_id,
                    "name": name,
                    "kind": "chart",
                    "profile_type": "advanced",
                    "recipe_path": self._session_relative_or_absolute(calibrated_recipe_path),
                    "icc_profile_path": self._session_relative_or_absolute(icc_profile_path),
                    "profile_report_path": self._session_relative_or_absolute(profile_report_path),
                    "detail_adjustments": {},
                    "render_adjustments": {},
                }
            )
            write_json(development_profile_path, payload)
        except Exception:
            pass
        self._register_development_profile(
            {
                "id": profile_id,
                "name": name,
                "kind": "chart",
                "profile_type": "advanced",
                "recipe_path": self._session_relative_or_absolute(calibrated_recipe_path),
                "manifest_path": self._session_relative_or_absolute(development_profile_path),
                "icc_profile_path": self._session_relative_or_absolute(icc_profile_path),
                "profile_report_path": self._session_relative_or_absolute(profile_report_path),
            },
            activate=True,
        )
        return profile_id

    def _queue_assign_active_development_profile(self) -> None:
        profile_id = self._active_development_profile_id
        if not profile_id and hasattr(self, "development_profile_combo"):
            profile_id = str(self.development_profile_combo.currentData() or "")
        if not profile_id:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), "Activa o guarda primero un perfil de ajuste.")
            return
        try:
            settings = self._development_profile_settings(profile_id)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, self.tr("Perfil de ajuste no válido"), str(exc))
            return
        rows = sorted({i.row() for i in self.queue_table.selectionModel().selectedRows()})
        if not rows:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), "Selecciona filas de la cola.")
            return
        try:
            rendered_profile, mode = self._render_profile_and_mode_for_development_settings(settings)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, self.tr("Perfil de ajuste incompleto"), str(exc))
            return
        development_profile = self._profile_payload_from_development_settings(settings)
        errors: list[tuple[Path, Exception]] = []
        for row in rows:
            if 0 <= row < len(self._develop_queue):
                self._develop_queue[row]["development_profile_id"] = profile_id
                self._develop_queue[row]["status"] = "pending"
                self._develop_queue[row]["message"] = ""
                source_path = Path(str(self._develop_queue[row].get("source") or ""))
                try:
                    self._write_raw_settings_sidecar(
                        source_path,
                        recipe=settings["recipe"],
                        development_profile=development_profile,
                        detail_adjustments=settings["detail_adjustments"],
                        render_adjustments=settings["render_adjustments"],
                        profile_path=rendered_profile,
                        color_management_mode=mode,
                        status="assigned",
                    )
                except Exception as exc:
                    errors.append((source_path, exc))
        self._refresh_queue_table()
        self._refresh_color_reference_thumbnail_markers()
        self._save_active_session(silent=True)
        if errors:
            first_path, first_error = errors[0]
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("No se pudo escribir mochila"),
                self.tr("Fallaron") + f" {len(errors)} " + self.tr("archivo(s). Primer error:")
                + f"\n{first_path}\n{first_error}",
            )
        self._set_status(self.tr("Perfil asignado a") + f" {len(rows)} " + self.tr("elemento(s) de cola"))
