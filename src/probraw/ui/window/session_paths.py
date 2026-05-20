from __future__ import annotations

from ._imports import *  # noqa: F401,F403


class SessionPathsMixin:
    def _initialize_session_tab_defaults(self) -> None:
        suggested = (self._current_dir / "probraw_session").resolve()
        self.session_root_path.setText(str(suggested))
        self.session_name_edit.setText(suggested.name)
        self._populate_session_directory_fields(self._session_paths_from_root(suggested))

    def _session_paths_from_root(self, root: Path) -> dict[str, Path]:
        absolute = root.expanduser().resolve()
        return {
            "root": absolute,
            "config": absolute / "00_configuraciones",
            "raw": absolute / "01_ORG",
            "exports": absolute / "02_DRV",
            "charts": absolute / "01_ORG",
            "profiles": absolute / "00_configuraciones" / "profiles",
            "references": absolute / "00_configuraciones" / "references",
            "work": absolute / "00_configuraciones" / "work",
        }

    def _populate_session_directory_fields(self, paths: dict[str, Path]) -> None:
        self.session_dir_charts.setText(str(paths["charts"]))
        self.session_dir_raw.setText(str(paths["raw"]))
        self.session_dir_profiles.setText(str(paths["profiles"]))
        self.session_dir_exports.setText(str(paths["exports"]))
        self.session_dir_config.setText(str(paths["config"]))
        self.session_dir_work.setText(str(paths["work"]))

    def _project_aligned_session_directories(self, directories: dict[str, Any], root: Path | str) -> dict[str, str]:
        root = Path(root).expanduser()
        defaults = self._session_paths_from_root(root)
        aligned = {key: str(path) for key, path in defaults.items()}
        raw_dirs = directories if isinstance(directories, dict) else {}
        for key, default in defaults.items():
            if key == "root":
                continue
            raw_value = raw_dirs.get(key)
            if not isinstance(raw_value, (str, Path)) or not str(raw_value).strip():
                continue
            candidate = Path(str(raw_value)).expanduser()
            if not candidate.is_absolute() and not candidate.anchor:
                candidate = defaults["root"] / candidate
            if not self._path_is_inside(candidate, defaults["root"]):
                continue
            try:
                aligned[key] = str(candidate.resolve(strict=False))
            except Exception:
                aligned[key] = str(default)
        return aligned

    def _path_is_inside(self, path: Path, root: Path) -> bool:
        try:
            path.expanduser().resolve(strict=False).relative_to(root.expanduser().resolve(strict=False))
            return True
        except Exception:
            return False

    def _session_relative_or_absolute(self, path: Path | str | None) -> str:
        if path is None:
            return ""
        candidate = Path(str(path)).expanduser()
        if self._active_session_root is not None:
            try:
                root = self._active_session_root.expanduser().resolve(strict=False)
                resolved = candidate.resolve(strict=False)
                return resolved.relative_to(root).as_posix()
            except Exception:
                pass
        return str(candidate)

    def _session_stored_path(self, value: Any) -> Path | None:
        text = str(value or "").strip()
        if not text:
            return None
        candidate = Path(text).expanduser()
        if candidate.is_absolute() or self._active_session_root is None:
            return candidate
        return self._active_session_root / candidate

    def _session_reference_source_dirs(self, *, paths: dict[str, Path] | None = None) -> list[tuple[str, Path]]:
        if paths is None:
            paths = self._session_paths_from_root(self._active_session_root) if self._active_session_root else {}
            if isinstance(self._active_session_payload, dict) and isinstance(
                self._active_session_payload.get("directories"),
                dict,
            ):
                paths = {
                    key: Path(str(value)).expanduser()
                    for key, value in self._active_session_payload["directories"].items()
                    if isinstance(value, str) and value.strip()
                }
        seen: set[str] = set()
        result: list[tuple[str, Path]] = []
        for key in ("raw", "charts"):
            p = paths.get(key)
            if p is None:
                continue
            try:
                marker = str(p.expanduser().resolve(strict=False))
            except Exception:
                marker = str(p)
            if marker in seen:
                continue
            seen.add(marker)
            result.append((key, p))
        return result

    def _preferred_profile_reference_dir(self, *, paths: dict[str, Path] | None = None) -> Path | None:
        for key, candidate in self._session_reference_source_dirs(paths=paths):
            if candidate.exists() and candidate.is_dir():
                if self._directory_has_chart_captures(candidate) or key == "raw":
                    return candidate
        return None

    def _profile_reference_rejection_reason(
        self,
        path: Path,
        *,
        paths: dict[str, Path] | None = None,
    ) -> str | None:
        if paths is None:
            paths = {}
            if self._active_session_root is not None:
                paths.update(self._session_paths_from_root(self._active_session_root))
            if isinstance(self._active_session_payload, dict) and isinstance(
                self._active_session_payload.get("directories"),
                dict,
            ):
                paths.update(
                    {
                        key: Path(str(value)).expanduser()
                        for key, value in self._active_session_payload["directories"].items()
                        if isinstance(value, str) and value.strip()
                    }
                )

        for key, label in PROFILE_REFERENCE_FORBIDDEN_DIRS.items():
            root = paths.get(key)
            if root is not None and self._path_is_inside(path, root):
                return f"{label} de la sesion"
        return None

    def _profile_status_for_path(self, profile_path: Path) -> str | None:
        sidecars = [profile_path.with_suffix(".profile.json")]
        registered_profile = self._icc_profile_by_path(profile_path) if hasattr(self, "_icc_profile_by_path") else None
        if registered_profile is not None:
            registered_report = self._session_stored_path(registered_profile.get("profile_report_path"))
            if registered_report is not None:
                sidecars.append(registered_report)
        if self._active_session_root is not None:
            defaults = self._session_default_outputs()
            sidecars.append(defaults["profile_report"])

        for sidecar in sidecars:
            try:
                if not sidecar.exists():
                    continue
                data = json.loads(sidecar.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            if sidecar.name == "profile_report.json":
                reported = str(data.get("output_icc") or "").strip()
                if not reported:
                    continue
                try:
                    if Path(reported).expanduser().resolve(strict=False) != profile_path.expanduser().resolve(strict=False):
                        continue
                except Exception:
                    continue
            if self._profile_payload_has_rejected_training_error(data):
                return "rejected"
            metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
            candidates = [
                data.get("profile_status"),
                data.get("session_profile_status"),
                metadata.get("profile_status"),
                metadata.get("session_profile_status"),
            ]
            for candidate in candidates:
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip().lower()
                if isinstance(candidate, dict):
                    status = str(candidate.get("status") or "").strip().lower()
                    if status:
                        return status
        if registered_profile is not None:
            status = str(registered_profile.get("status") or "").strip().lower()
            if status and status != "unknown":
                return status
        return None

    def _profile_payload_has_rejected_training_error(self, data: dict[str, Any]) -> bool:
        metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        status_payloads = [
            data.get("profile_status"),
            data.get("session_profile_status"),
            metadata.get("profile_status"),
            metadata.get("session_profile_status"),
        ]
        thresholds: dict[str, Any] = {}
        error_summary: dict[str, Any] | None = None
        for candidate in status_payloads:
            if not isinstance(candidate, dict):
                continue
            if str(candidate.get("training_status") or "").strip().lower() == "rejected":
                return True
            if not thresholds and isinstance(candidate.get("thresholds"), dict):
                thresholds = candidate["thresholds"]
            if error_summary is None and isinstance(candidate.get("training_error_summary"), dict):
                error_summary = candidate["training_error_summary"]

        if error_summary is None and isinstance(data.get("error_summary"), dict):
            error_summary = data["error_summary"]
        if error_summary is None and isinstance(data.get("profile"), dict):
            profile_error = data["profile"].get("error_summary")
            if isinstance(profile_error, dict):
                error_summary = profile_error
        if error_summary is None:
            return False

        try:
            mean_de = float(error_summary.get("mean_delta_e2000", 0.0))
            max_de = float(error_summary.get("max_delta_e2000", 0.0))
            mean_limit = float(thresholds.get("mean_delta_e2000_max", DEFAULT_QA_MEAN_DELTA_E2000_MAX))
            max_limit = float(thresholds.get("max_delta_e2000_max", DEFAULT_QA_MAX_DELTA_E2000_MAX))
        except (TypeError, ValueError):
            return True
        return mean_de > mean_limit or max_de > max_limit

    def _profile_can_be_active(self, profile_path: Path) -> bool:
        if not profile_path.exists():
            return False
        status = self._profile_status_for_path(profile_path)
        return status not in {"rejected", "expired"}

    def _filter_profile_reference_files(
        self,
        files: list[Path],
        *,
        paths: dict[str, Path] | None = None,
    ) -> tuple[list[Path], list[tuple[Path, str]]]:
        accepted: list[Path] = []
        rejected: list[tuple[Path, str]] = []
        seen: set[str] = set()
        for path in files:
            if path.suffix.lower() not in PROFILE_CHART_EXTENSIONS:
                continue
            reason = self._profile_reference_rejection_reason(path, paths=paths)
            if reason is not None:
                rejected.append((path, reason))
                continue
            try:
                key = str(path.expanduser().resolve(strict=False))
            except Exception:
                key = str(path.expanduser())
            if key in seen:
                continue
            seen.add(key)
            accepted.append(path)
        return accepted, rejected

    def _set_profile_reference_dir(self, folder: Path) -> bool:
        reason = self._profile_reference_rejection_reason(folder)
        if reason is None:
            self.profile_charts_dir.setText(str(folder))
            return True

        fallback = self._preferred_profile_reference_dir()
        if fallback is not None:
            self.profile_charts_dir.setText(str(fallback))
            self._set_status(
                f"No se usan {reason} como referencias colorimétricas; se usa {fallback}"
            )
            return False

        self._set_status(self.tr("No se usan") + f" {reason} " + self.tr("como referencias colorimétricas."))
        return False

    def _folder_has_browsable_files(self, folder: Path) -> bool:
        try:
            return any(
                p.is_file() and p.suffix.lower() in BROWSABLE_EXTENSIONS
                for p in folder.iterdir()
            )
        except OSError:
            return False

    def _session_state_path_or_default(
        self,
        value: Any,
        default: Path,
        *,
        root: Path | None = None,
    ) -> Path:
        text = str(value or "").strip()
        default = default.expanduser()
        if not text or self._is_legacy_temp_output_path(text):
            return default

        candidate = Path(text).expanduser()
        session_root = root or self._active_session_root
        if session_root is not None and not candidate.is_absolute() and not candidate.anchor:
            candidate = session_root / candidate
        try:
            if candidate.resolve(strict=False) == Path.home().resolve(strict=False):
                return default
        except Exception:
            return default

        if session_root is not None and not self._path_is_inside(candidate, session_root):
            return default

        if not candidate.exists() and default.exists():
            return default
        return candidate

    def _session_state_dir_or_default(
        self,
        value: Any,
        default: Path,
        *,
        root: Path | None = None,
    ) -> Path:
        candidate = self._session_state_path_or_default(value, default)
        session_root = root or self._active_session_root
        if session_root is not None and not self._path_is_inside(candidate, session_root):
            return default.expanduser()
        return candidate

    def _is_legacy_temp_output_path(self, value: Any) -> bool:
        text = str(value or "").strip()
        if not text:
            return False
        candidate = Path(text).expanduser()
        try:
            resolved = candidate.resolve(strict=False)
            temp_root = Path(tempfile.gettempdir()).resolve(strict=False)
            if resolved == temp_root or temp_root in resolved.parents:
                return True
        except Exception:
            pass
        return candidate.name in LEGACY_TEMP_OUTPUT_NAMES

    def _session_output_path_or_default(
        self,
        value: Any,
        default: Path,
        *,
        root: Path | None = None,
    ) -> Path:
        text = str(value or "").strip()
        default = default.expanduser()
        if not text or self._is_legacy_temp_output_path(text):
            return default

        candidate = Path(text).expanduser()
        session_root = root or self._active_session_root
        if session_root is not None and not candidate.is_absolute() and not candidate.anchor:
            candidate = session_root / candidate
        try:
            if candidate.resolve(strict=False) == Path.home().resolve(strict=False):
                return default
        except Exception:
            return default
        if session_root is not None and not self._path_is_inside(candidate, session_root):
            return default
        return candidate

    def _session_default_outputs(
        self,
        *,
        paths: dict[str, Path] | None = None,
        session_name: str | None = None,
    ) -> dict[str, Path]:
        if paths is None:
            if isinstance(self._active_session_payload, dict) and isinstance(
                self._active_session_payload.get("directories"),
                dict,
            ):
                paths = {
                    k: Path(v)
                    for k, v in self._active_session_payload["directories"].items()
                    if isinstance(v, str)
                }
            elif self._active_session_root is not None:
                paths = self._session_paths_from_root(self._active_session_root)
            else:
                paths = {}

        root = paths.get("root", self._active_session_root or Path.cwd())
        paths = {
            key: Path(value)
            for key, value in self._project_aligned_session_directories(paths, root).items()
        }
        root = paths.get("root", root)
        exports_dir = paths.get("exports", root / "02_DRV")
        profiles_dir = paths.get("profiles", root / "00_configuraciones" / "profiles")
        config_dir = paths.get("config", root / "00_configuraciones")
        work_dir = paths.get("work", root / "00_configuraciones" / "work")

        safe_name = (session_name or self.session_name_edit.text().strip() or root.name or "session").strip()
        return {
            "profile_out": profiles_dir / f"{safe_name}.icc",
            "profile_report": config_dir / "profile_report.json",
            "workdir": work_dir / "profile_generation",
            "development_profile": config_dir / "development_profile.json",
            "calibrated_recipe": config_dir / "recipe_calibrated.yml",
            "recipe": config_dir / "recipe.yml",
            "preview": exports_dir / "preview.png",
            "tiff_dir": exports_dir,
        }

    def _ensure_session_output_controls(self) -> None:
        defaults = self._session_default_outputs()
        replacements = [
            (self.profile_out_path_edit, defaults["profile_out"]),
            (self.path_profile_out, defaults["profile_out"]),
            (self.profile_report_out, defaults["profile_report"]),
            (self.profile_workdir, defaults["workdir"]),
            (self.develop_profile_out, defaults["development_profile"]),
            (self.calibrated_recipe_out, defaults["calibrated_recipe"]),
            (self.path_recipe, defaults["calibrated_recipe"]),
            (self.path_preview_png, defaults["preview"]),
            (self.batch_out_dir, defaults["tiff_dir"]),
        ]
        for widget, default in replacements:
            current = widget.text().strip()
            normalized = self._session_output_path_or_default(
                current,
                default,
                root=self._active_session_root,
            )
            if str(normalized) != current:
                widget.setText(str(normalized))
        if self.path_profile_out.text().strip() != self.profile_out_path_edit.text().strip():
            self.path_profile_out.setText(self.profile_out_path_edit.text().strip())

    def _preferred_session_start_directory(self, directories: dict[str, Any], state: dict[str, Any]) -> Path:
        root = self._active_session_root or Path.cwd()
        directories = self._project_aligned_session_directories(directories, root)
        paths = {
            k: Path(str(v)).expanduser()
            for k, v in directories.items()
            if isinstance(v, (str, Path)) and str(v).strip()
        }

        charts_default = paths.get("charts", root)
        raw_default = paths.get("raw", root)
        charts_state = self._session_state_dir_or_default(
            state.get("profile_charts_dir"),
            charts_default,
            root=root,
        )
        raw_state = self._session_state_dir_or_default(
            state.get("batch_input_dir"),
            raw_default,
            root=root,
        )

        candidates: list[Path] = []
        for chart_file in self._selected_chart_files:
            if chart_file.exists() and chart_file.is_file():
                candidates.append(chart_file.parent)
                break
        candidates.extend([raw_state, charts_state, raw_default, charts_default, root])

        seen: set[str] = set()
        unique_candidates: list[Path] = []
        for candidate in candidates:
            try:
                key = str(candidate.expanduser().resolve(strict=False))
            except Exception:
                key = str(candidate.expanduser())
            if key not in seen:
                seen.add(key)
                unique_candidates.append(candidate)

        for candidate in unique_candidates:
            if candidate.exists() and candidate.is_dir() and self._folder_has_browsable_files(candidate):
                return candidate
        for candidate in unique_candidates:
            if candidate.exists() and candidate.is_dir():
                return candidate
        return root

    def _should_replace_operational_dir(self, current_value: str, new_folder: Path) -> bool:
        text = current_value.strip()
        if not text:
            return True

        current = Path(text).expanduser()
        try:
            if current.resolve(strict=False) == Path.home().resolve(strict=False):
                return True
        except Exception:
            return True

        if not current.exists():
            return True

        if self._active_session_root is not None:
            inside_current_session = self._path_is_inside(current, self._active_session_root)
            inside_new_session = self._path_is_inside(new_folder, self._active_session_root)
            if inside_new_session and not inside_current_session:
                return True
        return False

    def _sync_operational_dirs_from_browser(self, folder: Path) -> None:
        if not self._folder_has_browsable_files(folder):
            return
        if (
            self._should_replace_operational_dir(self.profile_charts_dir.text(), folder)
            and self._profile_reference_rejection_reason(folder) is None
        ):
            self.profile_charts_dir.setText(str(folder))
        if self._should_replace_operational_dir(self.batch_input_dir.text(), folder):
            self.batch_input_dir.setText(str(folder))
