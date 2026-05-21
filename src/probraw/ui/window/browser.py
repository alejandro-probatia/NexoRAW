from __future__ import annotations

from ._imports import *  # noqa: F401,F403


class BrowserMetadataMixin:
    def _pick_directory(self) -> None:
        p = QtWidgets.QFileDialog.getExistingDirectory(self, self.tr("Selecciona directorio"))
        if not p:
            return
        selected = Path(p)
        project_root = self._project_root_for_path(selected)
        if project_root is not None:
            self.session_root_path.setText(str(project_root))
            self._on_session_root_edited()
        self.dir_tree.setCurrentIndex(self._dir_model.index(str(selected)))
        self._set_current_directory(selected)

    def _detect_storage_roots(self) -> list[Path]:
        roots: list[Path] = []
        if sys.platform.startswith("win"):
            for fi in QtCore.QDir.drives():
                p = Path(fi.absoluteFilePath())
                if p not in roots:
                    roots.append(p)
        else:
            roots.append(Path("/"))

        if hasattr(QtCore, "QStorageInfo"):
            for vol in QtCore.QStorageInfo.mountedVolumes():
                try:
                    if not vol.isValid() or not vol.isReady():
                        continue
                    p = Path(vol.rootPath())
                    if p not in roots:
                        roots.append(p)
                except Exception:
                    continue

        roots = sorted(roots, key=lambda p: str(p))
        return roots

    def _refresh_storage_roots(self) -> None:
        roots = self._detect_storage_roots()
        self._storage_roots = roots
        current_dir = self._current_dir

        self.storage_root_combo.blockSignals(True)
        self.storage_root_combo.clear()
        best_idx = -1
        best_len = -1

        for idx, root in enumerate(roots):
            label = str(root)
            self.storage_root_combo.addItem(label, str(root))
            if str(current_dir).startswith(str(root)) and len(str(root)) > best_len:
                best_idx = idx
                best_len = len(str(root))

        if best_idx >= 0:
            self.storage_root_combo.setCurrentIndex(best_idx)
        self.storage_root_combo.blockSignals(False)

    def _on_storage_root_changed(self, idx: int) -> None:
        if idx < 0:
            return
        data = self.storage_root_combo.itemData(idx)
        if not data:
            return
        root = Path(str(data))
        self.dir_tree.setCurrentIndex(self._dir_model.index(str(root)))
        self._set_current_directory(root)

    def _on_tree_clicked(self, index) -> None:
        p = Path(self._dir_model.filePath(index))
        self._set_current_directory(p)

    def _show_directory_tree_context_menu(self, pos: QtCore.QPoint) -> None:
        index = self.dir_tree.indexAt(pos)
        folder = self._directory_tree_path_for_index(index)
        if folder is None:
            folder = self._current_dir
        else:
            self.dir_tree.setCurrentIndex(index)

        menu = QtWidgets.QMenu(self)
        open_action = menu.addAction(
            self.tr("Abrir en el explorador del sistema"),
            lambda p=folder: self._open_directory_in_system_file_browser(p),
        )
        open_action.setEnabled(folder.exists() and folder.is_dir())
        menu.exec(self.dir_tree.viewport().mapToGlobal(pos))

    def _directory_tree_path_for_index(self, index: QtCore.QModelIndex) -> Path | None:
        if not index.isValid():
            return None
        path_text = self._dir_model.filePath(index)
        if not path_text:
            return None
        folder = Path(path_text)
        return folder if folder.exists() and folder.is_dir() else None

    def _open_directory_in_system_file_browser(self, folder: Path) -> None:
        folder = Path(folder)
        if not folder.exists() or not folder.is_dir():
            self._set_status(self.tr("Directorio no encontrado:") + f" {folder}")
            return
        ok = QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(folder)))
        if ok:
            self._set_status(self.tr("Carpeta abierta en el explorador del sistema:") + f" {folder}")
        else:
            self._set_status(self.tr("No se pudo abrir el explorador del sistema para:") + f" {folder}")

    def _set_current_directory(self, folder: Path) -> None:
        resolved_folder = self._resolve_existing_directory(folder)
        if resolved_folder is None:
            self._set_status(self.tr("Directorio no encontrado:") + f" {folder}")
            return
        folder = self._preferred_browsing_directory(resolved_folder)
        self._current_dir = folder
        self.current_dir_label.setText(str(folder))
        self._settings.setValue("browser/last_dir", str(folder))
        self._refresh_storage_roots()
        self._set_filesystem_model_root(folder)
        index = self._dir_model.index(str(folder))
        if index.isValid():
            self.dir_tree.blockSignals(True)
            self.dir_tree.setCurrentIndex(index)
            self.dir_tree.scrollTo(index)
            self.dir_tree.blockSignals(False)
        self._sync_operational_dirs_from_browser(folder)
        self._populate_file_list(folder)
        self._set_status(self.tr("Directorio actual:") + f" {folder}")

    def _reload_current_directory(self) -> None:
        self._populate_file_list(self._current_dir)

    def _populate_file_list(self, folder: Path) -> None:
        self._selection_load_timer.stop()
        self.file_list.clear()
        self._file_items_by_key.clear()
        self._preview_load_pending_request = None
        self._profile_preview_pending_request = None
        self._profile_preview_expected_key = None
        self._metadata_pending_request = None
        self._selected_file = None
        self._clear_manual_chart_points_for_file_change()
        self._clear_mtf_roi_for_file_change()
        if hasattr(self, "_clear_color_picker_samples_for_file_change"):
            self._clear_color_picker_samples_for_file_change()
        self._last_loaded_preview_key = None
        self._loaded_preview_source_profile_path = None
        self.selected_file_label.setText(self.tr("Sin archivo seleccionado"))
        self._clear_metadata_view()
        self._clear_viewer_histogram()

        max_items = 500
        shown: list[Path] = []
        truncated = False
        try:
            for p in folder.iterdir():
                if not p.is_file() or p.suffix.lower() not in BROWSABLE_EXTENSIONS:
                    continue
                shown.append(p)
                if len(shown) >= max_items:
                    truncated = True
                    break
        except OSError as exc:
            self._log_preview(f"No se pudo listar carpeta: {exc}")
            return

        shown.sort(key=lambda p: p.name.lower())

        for p in shown:
            item = QtWidgets.QListWidgetItem("")
            item.setData(QtCore.Qt.UserRole, str(p))
            item.setData(QtCore.Qt.UserRole + 1, p.name)
            item.setTextAlignment(QtCore.Qt.AlignHCenter)
            item.setToolTip(self._file_item_tooltip(p))
            self._set_file_item_display_icon(item, p, self._icon_for_file(p))
            self.file_list.addItem(item)
            self._file_items_by_key[self._normalized_path_key(p)] = item

        if truncated:
            i = QtWidgets.QListWidgetItem("... mas archivos no mostrados")
            i.setFlags(QtCore.Qt.NoItemFlags)
            self.file_list.addItem(i)

        self._queue_thumbnail_generation(shown)

    def _file_list_paths(self) -> list[Path]:
        paths: list[Path] = []
        for row in range(self.file_list.count()):
            item = self.file_list.item(row)
            raw_path = item.data(QtCore.Qt.UserRole)
            if raw_path:
                path = self._resolve_existing_browsable_path(Path(str(raw_path)))
                if path is not None:
                    if self._normalized_path_key(path) != self._normalized_path_key(Path(str(raw_path))):
                        self._update_file_item_path(item, path)
                    paths.append(path)
        return paths

    def _set_file_list_placeholder_icons(self) -> None:
        for row in range(self.file_list.count()):
            item = self.file_list.item(row)
            raw_path = item.data(QtCore.Qt.UserRole)
            if raw_path:
                path = Path(str(raw_path))
                item.setToolTip(self._file_item_tooltip(path))
                self._set_file_item_display_icon(item, path, self._icon_for_file(path))

    def _queue_thumbnail_generation(self, paths: list[Path], *, delay_ms: int = 220) -> None:
        self._thumbnail_generation += 1
        self._pending_thumbnail_paths = list(paths)
        self._thumbnail_scan_index = 0
        if not self._pending_thumbnail_paths:
            self._thumbnail_timer.stop()
            return
        self._thumbnail_timer.start(max(0, int(delay_ms)))

    def _start_pending_thumbnail_generation(self) -> None:
        if self._thumbnail_task_active:
            return
        paths = [p for p in self._pending_thumbnail_paths if p.exists() and p.is_file()]
        if not paths:
            return

        size = int(self.file_list.iconSize().width() or DEFAULT_THUMBNAIL_SIZE)
        generation = self._thumbnail_generation
        self._apply_cached_thumbnails(paths, size)
        missing = self._next_thumbnail_batch(paths, size)
        if not missing:
            return

        payload_inputs = [(path, self._thumbnail_cache_key(path, size)) for path in missing]

        def task():
            return generation, size, self._build_thumbnail_payloads_for_keys(payload_inputs, size)

        thread = TaskThread(task)
        self._thumbnail_task_active = True
        self._threads.append(thread)

        def cleanup() -> None:
            self._thumbnail_task_active = False
            if thread in self._threads:
                self._threads.remove(thread)
            thread.deleteLater()
            if self._pending_thumbnail_paths and generation != self._thumbnail_generation:
                self._thumbnail_timer.start(0)

        def ok(payload) -> None:
            try:
                payload_generation, payload_size, thumbnails = payload
                if payload_generation != self._thumbnail_generation:
                    return
                touched_cache_dirs: set[Path] = set()
                target_icon_size = QtCore.QSize(int(payload_size), int(payload_size))
                for raw_path, key, rgb_u8 in thumbnails:
                    icon = self._icon_from_thumbnail_array(rgb_u8, target_size=target_icon_size)
                    self._image_thumb_cache[key] = icon
                    path = Path(raw_path)
                    cache_dir = self._write_thumbnail_to_disk_cache(key, rgb_u8, path=path, prune=False)
                    if cache_dir is not None:
                        touched_cache_dirs.add(cache_dir)
                    self._set_item_icon_for_path(path, icon)
                if touched_cache_dirs:
                    self._thumbnail_disk_writes_since_prune += len(thumbnails)
                    if self._thumbnail_disk_writes_since_prune >= THUMBNAIL_DISK_PRUNE_INTERVAL_WRITES:
                        for cache_dir in touched_cache_dirs:
                            self._prune_disk_cache(
                                cache_dir,
                                pattern="*.png",
                                max_entries=THUMBNAIL_DISK_CACHE_MAX_ENTRIES,
                                max_bytes=THUMBNAIL_DISK_CACHE_MAX_BYTES,
                            )
                        self._thumbnail_disk_writes_since_prune = 0
                self._prune_thumbnail_cache()
                self._apply_cached_thumbnails(self._file_list_paths(), int(payload_size))
                if self._should_prefetch_more_thumbnails():
                    self._thumbnail_timer.start(80)
            finally:
                cleanup()

        def fail(trace: str) -> None:
            cleanup()
            self._log_preview(f"No se pudieron generar miniaturas: {trace.strip().splitlines()[-1] if trace.strip() else 'error'}")

        thread.succeeded.connect(ok)
        thread.failed.connect(fail)
        thread.start()

    def _next_thumbnail_batch(self, paths: list[Path], size: int) -> list[Path]:
        batch: list[Path] = []
        while self._thumbnail_scan_index < len(paths) and len(batch) < THUMBNAIL_BATCH_SIZE:
            path = paths[self._thumbnail_scan_index]
            self._thumbnail_scan_index += 1
            if self._cached_thumbnail_icon(self._thumbnail_cache_key(path, size), path=path) is None:
                batch.append(path)
        return batch

    def _on_thumbnail_scroll_changed(self, _value: int) -> None:
        if self._thumbnail_task_active or not self._pending_thumbnail_paths:
            return
        if self._thumbnail_scan_index >= len(self._pending_thumbnail_paths):
            return
        if self._should_prefetch_more_thumbnails():
            self._thumbnail_timer.start(80)

    def _should_prefetch_more_thumbnails(self) -> bool:
        if not hasattr(self, "file_list"):
            return False
        if self._thumbnail_scan_index >= len(self._pending_thumbnail_paths):
            return False
        scrollbar = self.file_list.horizontalScrollBar()
        maximum = int(scrollbar.maximum())
        if maximum <= 0:
            return False
        margin = max(1, int(scrollbar.pageStep()) * THUMBNAIL_PREFETCH_MARGIN_PAGES)
        return int(scrollbar.value()) >= maximum - margin

    def _apply_cached_thumbnails(self, paths: list[Path], size: int) -> None:
        for p in paths:
            icon = self._cached_thumbnail_icon(self._thumbnail_cache_key(p, size), path=p)
            if icon is not None:
                self._set_item_icon_for_path(p, icon)

    def _cached_thumbnail_icon(self, key: str, *, path: Path | None = None) -> QtGui.QIcon | None:
        icon = self._image_thumb_cache.get(key)
        if icon is not None:
            return icon
        icon = self._read_thumbnail_from_disk_cache(key, path=path)
        if icon is None:
            return None
        self._image_thumb_cache[key] = icon
        self._prune_thumbnail_cache()
        return icon

    def _cached_raw_sidecar_payload(self, path: Path) -> dict[str, Any] | None:
        cache = getattr(self, "_raw_sidecar_cache", None)
        if not isinstance(cache, dict):
            cache = {}
            self._raw_sidecar_cache = cache
        key = self._normalized_path_key(path)
        stamp = self._raw_sidecar_cache_stamp(path)
        cached = cache.get(key)
        if cached is not None and cached[0] == stamp:
            return cached[1]
        try:
            payload = load_raw_sidecar(path)
            if not isinstance(payload, dict):
                payload = None
        except Exception:
            payload = None
        cache[key] = (stamp, payload)
        while len(cache) > 1024:
            cache.pop(next(iter(cache)))
        return payload

    def _invalidate_raw_sidecar_cache_for_path(self, path: Path) -> None:
        cache = getattr(self, "_raw_sidecar_cache", None)
        if isinstance(cache, dict):
            cache.pop(self._normalized_path_key(path), None)

    def _raw_sidecar_cache_stamp(self, path: Path) -> tuple[object, ...]:
        source = Path(path)
        candidates = [raw_sidecar_path(source)]
        candidates.extend(source.with_name(source.name + suffix) for suffix in LEGACY_RAW_SIDECAR_SUFFIXES)
        for candidate in candidates:
            try:
                stat = candidate.stat()
            except OSError:
                continue
            try:
                resolved = str(candidate.expanduser().resolve(strict=False))
            except Exception:
                resolved = str(candidate)
            return (resolved, int(stat.st_mtime_ns), int(stat.st_size))
        return ("missing",)

    def _user_disk_cache_dir(self, kind: str) -> Path:
        if sys.platform == "win32":
            base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Caches"
        else:
            base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
        return base / APP_NAME / kind

    def _project_disk_cache_dir(self, path: Path | None, kind: str) -> Path | None:
        if path is None or self._active_session_root is None:
            return None
        if not self._path_is_inside(path, self._active_session_root):
            return None
        return self._session_paths_from_root(self._active_session_root)["work"] / "cache" / kind

    def _disk_cache_dirs(self, path: Path | None, kind: str) -> list[Path]:
        dirs: list[Path] = []
        project_dir = self._project_disk_cache_dir(path, kind)
        if project_dir is not None:
            dirs.append(project_dir)
        user_dir = self._user_disk_cache_dir(kind)
        if user_dir not in dirs:
            dirs.append(user_dir)
        return dirs

    def _thumbnail_disk_cache_dir(self, path: Path | None = None) -> Path:
        return self._disk_cache_dirs(path, "thumbnails")[0]

    def _disk_cache_path(self, base_dir: Path, key: str, suffix: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8", errors="surrogatepass")).hexdigest()
        return base_dir / digest[:2] / f"{digest}{suffix}"

    def _thumbnail_disk_cache_path(self, key: str, *, base_dir: Path | None = None, path: Path | None = None) -> Path:
        return self._disk_cache_path(base_dir or self._thumbnail_disk_cache_dir(path), key, ".png")

    def _read_thumbnail_from_disk_cache(self, key: str, *, path: Path | None = None) -> QtGui.QIcon | None:
        for cache_dir in self._disk_cache_dirs(path, "thumbnails"):
            cache_path = self._thumbnail_disk_cache_path(key, base_dir=cache_dir)
            if not cache_path.is_file():
                continue
            pixmap = QtGui.QPixmap(str(cache_path))
            if pixmap.isNull():
                continue
            try:
                os.utime(cache_path, None)
            except Exception:
                pass
            return QtGui.QIcon(pixmap)
        return None

    def _write_thumbnail_to_disk_cache(
        self,
        key: str,
        rgb_u8: np.ndarray,
        *,
        path: Path | None = None,
        prune: bool = True,
    ) -> Path | None:
        try:
            cache_dir = self._thumbnail_disk_cache_dir(path)
            cache_path = self._thumbnail_disk_cache_path(key, base_dir=cache_dir)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            image = np.asarray(rgb_u8, dtype=np.uint8)
            if image.ndim == 2:
                image = np.repeat(image[..., None], 3, axis=2)
            if image.shape[-1] > 3:
                image = image[..., :3]
            Image.fromarray(np.ascontiguousarray(image)).save(cache_path, format="PNG")
            if prune:
                self._prune_disk_cache(
                    cache_dir,
                    pattern="*.png",
                    max_entries=THUMBNAIL_DISK_CACHE_MAX_ENTRIES,
                    max_bytes=THUMBNAIL_DISK_CACHE_MAX_BYTES,
                )
            return cache_dir
        except Exception:
            return None

    def _prune_disk_cache(self, cache_dir: Path, *, pattern: str, max_entries: int, max_bytes: int) -> None:
        try:
            files = [p for p in cache_dir.glob(f"*/*{pattern.removeprefix('*')}") if p.is_file()]
        except Exception:
            return
        records: list[tuple[float, int, Path]] = []
        total_bytes = 0
        for file_path in files:
            try:
                stat = file_path.stat()
            except OSError:
                continue
            size = int(stat.st_size)
            total_bytes += size
            records.append((float(stat.st_mtime), size, file_path))
        records.sort(key=lambda item: item[0])
        while records and (len(records) > max_entries or total_bytes > max_bytes):
            _mtime, size, file_path = records.pop(0)
            try:
                file_path.unlink()
                total_bytes -= size
            except OSError:
                pass

    def _prune_thumbnail_cache(self) -> None:
        overflow = len(self._image_thumb_cache) - THUMBNAIL_CACHE_MAX_ENTRIES
        if overflow <= 0:
            return
        for key in list(self._image_thumb_cache.keys())[:overflow]:
            self._image_thumb_cache.pop(key, None)

    def _set_item_icon_for_path(self, path: Path, icon: QtGui.QIcon) -> None:
        key = self._normalized_path_key(path)
        item = self._file_items_by_key.get(key)
        if item is not None and self.file_list.row(item) >= 0:
            self._set_file_item_display_icon(item, path, icon)
            return
        self._file_items_by_key.pop(key, None)

    def _refresh_color_reference_thumbnail_markers(self) -> None:
        if not hasattr(self, "file_list"):
            return
        for row in range(self.file_list.count()):
            item = self.file_list.item(row)
            raw_path = item.data(QtCore.Qt.UserRole)
            if not raw_path:
                continue
            self._refresh_thumbnail_marker_for_path(Path(str(raw_path)))

    def _refresh_thumbnail_marker_for_path(self, path: Path) -> None:
        if not hasattr(self, "file_list"):
            return
        key = self._normalized_path_key(path)
        item = self._file_items_by_key.get(key)
        if item is None or self.file_list.row(item) < 0:
            return
        icon_size = int(self.file_list.iconSize().width() or DEFAULT_THUMBNAIL_SIZE)
        icon = self._cached_thumbnail_icon(self._thumbnail_cache_key(path, icon_size), path=path)
        if icon is None:
            icon = self._icon_for_file(path)
        item.setToolTip(self._file_item_tooltip(path))
        self._set_file_item_display_icon(item, path, icon)

    def _set_file_item_display_icon(
        self,
        item: QtWidgets.QListWidgetItem,
        path: Path,
        source_icon: QtGui.QIcon,
    ) -> None:
        display_icon = self._display_icon_for_path(path, source_icon)
        item.setIcon(display_icon)
        self._apply_thumbnail_item_size_hint(item, display_icon)

    def _apply_thumbnail_item_size_hint(
        self,
        item: QtWidgets.QListWidgetItem,
        icon: QtGui.QIcon | None = None,
    ) -> None:
        if not hasattr(self, "file_list"):
            return
        display_icon = icon or item.icon()
        pixmap = display_icon.pixmap(self.file_list.iconSize())
        if pixmap.isNull():
            size = self.file_list.iconSize()
        else:
            size = pixmap.size()
        item.setSizeHint(QtCore.QSize(max(1, int(size.width()) + 4), max(1, int(size.height()) + 4)))

    def _display_icon_for_path(self, path: Path, icon: QtGui.QIcon) -> QtGui.QIcon:
        size = int(self.file_list.iconSize().width() or DEFAULT_THUMBNAIL_SIZE)
        size = int(np.clip(size, MIN_THUMBNAIL_SIZE, MAX_THUMBNAIL_SIZE))
        return self._icon_with_thumbnail_markers(
            icon,
            size=size,
            badges=self._raw_adjustment_profile_badges(path),
        )

    def _file_item_tooltip(self, path: Path) -> str:
        lines = [str(path)]
        summary = self._raw_sidecar_development_summary(path)
        if summary:
            lines.append(summary)
        profile_summary = self._raw_adjustment_profile_badge_summary(path)
        if profile_summary:
            lines.append(profile_summary)
        if hasattr(self, "_raw_sidecar_mtf_summary"):
            mtf_summary = self._raw_sidecar_mtf_summary(path)
            if mtf_summary:
                lines.append(mtf_summary)
        if self._is_color_reference_file(path):
            lines.append("Referencia colorimétrica seleccionada")
        return "\n".join(lines)

    def _is_color_reference_file(self, path: Path) -> bool:
        key = self._normalized_path_key(path)
        return key in self._selected_chart_file_key_set()

    def _selected_chart_file_key_set(self) -> set[str]:
        files = tuple(str(p) for p in getattr(self, "_selected_chart_files", []))
        if getattr(self, "_selected_chart_file_key_source", None) != files:
            self._selected_chart_file_key_source = files
            self._selected_chart_file_keys = {self._normalized_path_key(Path(p)) for p in files}
        return getattr(self, "_selected_chart_file_keys", set())

    @staticmethod
    def _normalized_path_key(path: Path) -> str:
        try:
            return str(path.expanduser().resolve(strict=False)).lower()
        except Exception:
            return str(path).lower()

    def _icon_with_color_reference_marker(self, icon: QtGui.QIcon, *, size: int) -> QtGui.QIcon:
        return self._icon_with_thumbnail_markers(icon, size=size, badges=[])

    def _thumbnail_badge_strip_height(self, size: int) -> int:
        return int(np.clip(round(float(size) * 0.17), 12, 22))

    def _raw_adjustment_profile_badges(self, path: Path) -> list[str]:
        if path.suffix.lower() not in RAW_EXTENSIONS:
            return []
        payload = self._cached_raw_sidecar_payload(path)
        if payload is None:
            return []
        profiles = payload.get("adjustment_profiles") if isinstance(payload.get("adjustment_profiles"), dict) else {}
        badges: list[str] = []
        for key in ("icc", "color_contrast", "detail", "raw_export"):
            profile = profiles.get(key) if isinstance(profiles, dict) else None
            present = False
            if isinstance(profile, dict):
                present = bool(str(profile.get("id") or profile.get("name") or "").strip())
            if key == "color_contrast" and not present:
                render = payload.get("render_adjustments") if isinstance(payload.get("render_adjustments"), dict) else {}
                present = bool(self._render_adjustment_state_has_effect(render))
            if key == "detail" and not present:
                detail = payload.get("detail_adjustments") if isinstance(payload.get("detail_adjustments"), dict) else {}
                present = bool(self._detail_adjustment_state_has_effect(detail))
            if key == "raw_export" and not present:
                recipe = self._recipe_from_payload(payload.get("recipe"))
                present = bool(self._raw_export_recipe_has_effect(recipe))
            if key == "icc" and not present:
                color = payload.get("color_management") if isinstance(payload.get("color_management"), dict) else {}
                present = bool(str(color.get("icc_profile_path") or "").strip())
            if present:
                badges.append(key)
        return badges

    def _raw_adjustment_profile_badge_summary(self, path: Path) -> str:
        if path.suffix.lower() not in RAW_EXTENSIONS:
            return ""
        payload = self._cached_raw_sidecar_payload(path)
        if payload is None:
            return ""
        profiles = payload.get("adjustment_profiles") if isinstance(payload.get("adjustment_profiles"), dict) else {}
        labels = {
            "icc": "ICC",
            "color_contrast": "Color/contraste",
            "detail": "Nitidez",
            "raw_export": "RAW",
        }
        parts: list[str] = []
        for key in ("icc", "color_contrast", "detail", "raw_export"):
            profile = profiles.get(key) if isinstance(profiles, dict) else None
            name = ""
            if isinstance(profile, dict):
                name = str(profile.get("name") or profile.get("id") or "").strip()
            if key == "icc" and not name:
                color = payload.get("color_management") if isinstance(payload.get("color_management"), dict) else {}
                raw_path = str(color.get("icc_profile_path") or "").strip()
                if raw_path:
                    name = Path(raw_path).name
            if key == "color_contrast" and not name:
                render = payload.get("render_adjustments") if isinstance(payload.get("render_adjustments"), dict) else {}
                if self._render_adjustment_state_has_effect(render):
                    name = "ajustes propios"
            if key == "detail" and not name:
                detail = payload.get("detail_adjustments") if isinstance(payload.get("detail_adjustments"), dict) else {}
                if self._detail_adjustment_state_has_effect(detail):
                    name = "ajustes propios"
            if key == "raw_export" and not name:
                recipe = self._recipe_from_payload(payload.get("recipe"))
                if self._raw_export_recipe_has_effect(recipe):
                    name = "ajustes propios"
            if name:
                parts.append(f"{labels[key]}: {name}")
        return "Perfiles aplicados: " + " | ".join(parts) if parts else ""

    def _icon_with_thumbnail_markers(
        self,
        icon: QtGui.QIcon,
        *,
        size: int,
        badges: list[str],
    ) -> QtGui.QIcon:
        pixmap = icon.pixmap(QtCore.QSize(size, size))
        if pixmap.isNull():
            return icon
        content_w = max(1, int(pixmap.width()))
        content_h = max(1, int(pixmap.height()))
        strip_h = self._thumbnail_badge_strip_height(size) if badges else 0
        marked = QtGui.QPixmap(content_w, content_h + strip_h)
        marked.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(marked)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.drawPixmap(0, 0, pixmap)
        if badges:
            painter.fillRect(0, content_h, content_w, strip_h, QtGui.QColor("#111418"))
            max_badge_side = int(np.clip(strip_h - 4, 6, 18))
            spacing = max(1, int(round(max_badge_side * 0.25)))
            available = max(1, content_w - 4)
            badge_side = max_badge_side
            if len(badges) > 1:
                badge_side = min(badge_side, max(6, (available - (len(badges) - 1) * spacing) // len(badges)))
            total_w = len(badges) * badge_side + (len(badges) - 1) * spacing
            x = max(2, (content_w - total_w) // 2)
            y = content_h + max(1, (strip_h - badge_side) // 2)
            for badge in badges:
                rect = QtCore.QRectF(float(x), float(y), float(badge_side), float(badge_side))
                self._draw_thumbnail_profile_badge(painter, rect, badge)
                x += badge_side + spacing
        painter.end()
        return QtGui.QIcon(marked)

    def _draw_thumbnail_profile_badge(self, painter: QtGui.QPainter, rect: QtCore.QRectF, badge: str) -> None:
        if badge == "icc":
            painter.setPen(QtGui.QPen(QtGui.QColor("#cbd5e1"), 1))
            painter.setBrush(QtGui.QColor("#1f2937"))
            painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 2.0, 2.0)
            font = painter.font()
            font.setBold(True)
            font.setPixelSize(max(6, int(rect.height() * 0.38)))
            painter.setFont(font)
            painter.setPen(QtGui.QColor("#e5e7eb"))
            painter.drawText(rect, QtCore.Qt.AlignCenter, "ICC")
            return
        if badge == "color_contrast":
            radius = rect.width() * 0.31
            centers = [
                (rect.left() + rect.width() * 0.42, rect.top() + rect.height() * 0.42, "#ef4444"),
                (rect.left() + rect.width() * 0.58, rect.top() + rect.height() * 0.42, "#22c55e"),
                (rect.left() + rect.width() * 0.50, rect.top() + rect.height() * 0.60, "#3b82f6"),
            ]
            painter.setPen(QtCore.Qt.NoPen)
            for cx, cy, color in centers:
                painter.setBrush(QtGui.QColor(color))
                painter.drawEllipse(QtCore.QPointF(float(cx), float(cy)), float(radius), float(radius))
            return
        if badge == "detail":
            ellipse = rect.adjusted(1.0, 1.0, -1.0, -1.0)
            painter.setPen(QtGui.QPen(QtGui.QColor("#cbd5e1"), 1))
            painter.setBrush(QtGui.QColor("#ffffff"))
            painter.drawPie(ellipse, 90 * 16, 180 * 16)
            painter.setBrush(QtGui.QColor("#050505"))
            painter.drawPie(ellipse, -90 * 16, 180 * 16)
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawEllipse(ellipse)
            return
        if badge == "raw_export":
            gap = max(1.0, rect.width() * 0.08)
            cell = (rect.width() - gap) / 2.0
            cells = [
                (0, 0, "#22c55e"),
                (1, 0, "#2563eb"),
                (0, 1, "#ef4444"),
                (1, 1, "#22c55e"),
            ]
            painter.setPen(QtCore.Qt.NoPen)
            for col, row, color in cells:
                cell_rect = QtCore.QRectF(
                    rect.left() + col * (cell + gap),
                    rect.top() + row * (cell + gap),
                    cell,
                    cell,
                )
                painter.setBrush(QtGui.QColor(color))
                painter.drawRect(cell_rect)

    def _thumbnail_cache_key(self, path: Path, size: int | None = None) -> str:
        try:
            st = path.stat()
            stamp = f"{st.st_mtime_ns}:{st.st_size}"
        except OSError:
            stamp = "nostat"
        return f"{self._cache_path_identity(path)}|{stamp}|thumb-v4"

    def _cache_path_identity(self, path: Path) -> str:
        try:
            resolved = path.expanduser().resolve(strict=False)
        except Exception:
            resolved = path
        if self._active_session_root is not None:
            try:
                root = self._active_session_root.expanduser().resolve(strict=False)
                relative = resolved.relative_to(root)
                return f"session:{relative.as_posix()}"
            except Exception:
                pass
        return str(resolved)

    def _legacy_project_path_candidate(self, path: Path) -> Path | None:
        candidate = Path(path).expanduser()
        roots: list[Path] = []
        if self._active_session_root is not None:
            roots.append(self._active_session_root)
        for parent in candidate.parents:
            if (parent / "00_configuraciones").is_dir() or (parent / "01_ORG").is_dir() or (parent / "02_DRV").is_dir():
                roots.append(parent)
                break

        seen: set[str] = set()
        for root in roots:
            try:
                root = root.expanduser().resolve(strict=False)
                rel = candidate.resolve(strict=False).relative_to(root)
            except Exception:
                continue
            if not rel.parts:
                continue
            replacement = LEGACY_PROJECT_DIR_RENAMES.get(rel.parts[0])
            if replacement is None:
                continue
            mapped = root / replacement
            if len(rel.parts) > 1:
                mapped = mapped.joinpath(*rel.parts[1:])
            key = str(mapped)
            if key in seen:
                continue
            seen.add(key)
            if mapped.exists():
                return mapped
        return None

    def _project_root_for_path(self, path: Path) -> Path | None:
        candidate = Path(path).expanduser()
        search = [candidate, *candidate.parents]
        for parent in search:
            if (
                (parent / "00_configuraciones").is_dir()
                and (parent / "01_ORG").is_dir()
                and (parent / "02_DRV").is_dir()
            ):
                try:
                    return parent.resolve()
                except Exception:
                    return parent
        return None

    def _preferred_browsing_directory(self, folder: Path) -> Path:
        project_root = self._project_root_for_path(folder)
        if project_root is not None:
            org_dir = project_root / "01_ORG"
            if folder == project_root and org_dir.is_dir():
                return org_dir.resolve()
        return folder

    def _resolve_existing_directory(self, folder: Path) -> Path | None:
        candidate = Path(folder).expanduser()
        if candidate.exists() and candidate.is_dir():
            return candidate.resolve()
        mapped = self._legacy_project_path_candidate(candidate)
        if mapped is not None and mapped.exists() and mapped.is_dir():
            return mapped.resolve()
        return None

    def _resolve_existing_browsable_path(self, path: Path) -> Path | None:
        candidate = Path(path).expanduser()
        if candidate.exists() and candidate.is_file() and candidate.suffix.lower() in BROWSABLE_EXTENSIONS:
            return candidate.resolve()
        mapped = self._legacy_project_path_candidate(candidate)
        if mapped is not None and mapped.exists() and mapped.is_file() and mapped.suffix.lower() in BROWSABLE_EXTENSIONS:
            return mapped.resolve()
        return None

    def _update_file_item_path(self, item: QtWidgets.QListWidgetItem, path: Path) -> None:
        old_raw_path = item.data(QtCore.Qt.UserRole)
        if old_raw_path:
            self._file_items_by_key.pop(self._normalized_path_key(Path(str(old_raw_path))), None)
        item.setData(QtCore.Qt.UserRole, str(path))
        item.setToolTip(self._file_item_tooltip(path))
        self._file_items_by_key[self._normalized_path_key(path)] = item
        icon_size = int(self.file_list.iconSize().width() or DEFAULT_THUMBNAIL_SIZE)
        icon = self._cached_thumbnail_icon(self._thumbnail_cache_key(path, icon_size), path=path)
        if icon is None:
            icon = self._icon_for_file(path)
        self._set_file_item_display_icon(item, path, icon)

    def _remove_stale_file_item(self, item: QtWidgets.QListWidgetItem, path: Path) -> None:
        self._file_items_by_key.pop(self._normalized_path_key(path), None)
        row = self.file_list.row(item)
        if row >= 0:
            self.file_list.takeItem(row)
        self._selected_file = None
        self._clear_manual_chart_points_for_file_change()
        self.selected_file_label.setText(self.tr("Sin archivo seleccionado"))
        self._selection_load_timer.stop()
        self._metadata_timer.stop()
        self._clear_metadata_view()
        self._set_status(self.tr("Archivo no encontrado, miniatura retirada:") + f" {path.name}")

    @staticmethod
    def _build_thumbnail_payloads(paths: list[Path], size: int) -> list[tuple[str, str, np.ndarray]]:
        return BrowserMetadataMixin._build_thumbnail_payloads_for_keys(
            [(path, BrowserMetadataMixin._thumbnail_cache_key_for_path(path, size)) for path in paths],
            size,
        )

    @staticmethod
    def _build_thumbnail_payloads_for_keys(
        items: list[tuple[Path, str]], size: int
    ) -> list[tuple[str, str, np.ndarray]]:
        payloads: list[tuple[str, str, np.ndarray]] = []
        for path, key in items:
            try:
                rgb_u8 = BrowserMetadataMixin._thumbnail_array_for_path(path, MAX_THUMBNAIL_SIZE)
            except Exception:
                continue
            if rgb_u8 is None:
                continue
            payloads.append((str(path), key, rgb_u8))
        return payloads

    @staticmethod
    def _thumbnail_cache_key_for_path(path: Path, size: int | None = None) -> str:
        try:
            st = path.stat()
            stamp = f"{st.st_mtime_ns}:{st.st_size}"
        except OSError:
            stamp = "nostat"
        try:
            identity = str(path.expanduser().resolve(strict=False))
        except Exception:
            identity = str(path)
        return f"{identity}|{stamp}|thumb-v5"

    @staticmethod
    def _thumbnail_array_for_path(path: Path, size: int) -> np.ndarray | None:
        suffix = path.suffix.lower()
        if suffix in RAW_EXTENSIONS:
            return BrowserMetadataMixin._raw_embedded_thumbnail_array(path, size)

        try:
            with Image.open(path) as img:
                img = ImageOps.exif_transpose(img)
                if "A" in img.getbands():
                    rgba = img.convert("RGBA")
                    base = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                    base.alpha_composite(rgba)
                    img = base.convert("RGB")
                else:
                    img = img.convert("RGB")
                img.thumbnail((size, size), Image.Resampling.LANCZOS)
                return np.asarray(img, dtype=np.uint8).copy()
        except Exception:
            image = read_image(path)
            return BrowserMetadataMixin._thumbnail_u8(linear_to_srgb_display(image), size)

    @staticmethod
    def _raw_embedded_thumbnail_array(path: Path, size: int) -> np.ndarray | None:
        try:
            from ...raw.preview import extract_embedded_thumbnail

            thumb = extract_embedded_thumbnail(path, max_side=int(size))
            if thumb is not None:
                return thumb
        except Exception:
            pass

        exiftool = external_tool_path("exiftool")
        if exiftool is None:
            return None

        # Prefer already-small previews. JpgFromRaw can be much larger, but it is
        # still only decoded as a JPEG thumbnail and never through LibRaw.
        for tag in ("PreviewImage", "ThumbnailImage", "JpgFromRaw"):
            try:
                proc = run_external(
                    [exiftool, "-b", f"-{tag}", str(path)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    timeout=6,
                )
            except subprocess.TimeoutExpired:
                continue
            except Exception:
                continue
            if proc.returncode != 0:
                continue
            data = proc.stdout if isinstance(proc.stdout, (bytes, bytearray)) else b""
            if len(data) < 16:
                continue
            thumb = BrowserMetadataMixin._thumbnail_u8_from_encoded_bytes(bytes(data), size)
            if thumb is not None:
                return thumb
        return None

    @staticmethod
    def _thumbnail_u8_from_encoded_bytes(data: bytes, size: int) -> np.ndarray | None:
        try:
            with Image.open(io.BytesIO(data)) as img:
                try:
                    img.draft("RGB", (int(size), int(size)))
                except Exception:
                    pass
                img = ImageOps.exif_transpose(img)
                if "A" in img.getbands():
                    rgba = img.convert("RGBA")
                    base = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                    base.alpha_composite(rgba)
                    img = base.convert("RGB")
                else:
                    img = img.convert("RGB")
                img.thumbnail((int(size), int(size)), Image.Resampling.LANCZOS)
                return np.asarray(img, dtype=np.uint8).copy()
        except Exception:
            return None

    @staticmethod
    def _thumbnail_u8(image_rgb: np.ndarray, size: int) -> np.ndarray:
        rgb = np.asarray(image_rgb)
        if rgb.ndim == 2:
            rgb = np.repeat(rgb[..., None], 3, axis=2)
        if rgb.shape[-1] > 3:
            rgb = rgb[..., :3]
        if np.issubdtype(rgb.dtype, np.integer):
            maxv = float(np.iinfo(rgb.dtype).max)
            rgb_f = np.clip(rgb.astype(np.float32) / maxv, 0.0, 1.0)
        else:
            rgb_f = np.clip(rgb.astype(np.float32), 0.0, 1.0)

        h, w = int(rgb_f.shape[0]), int(rgb_f.shape[1])
        if h <= 0 or w <= 0:
            return np.zeros((1, 1, 3), dtype=np.uint8)
        scale = min(float(size) / float(max(w, h)), 1.0)
        if scale < 1.0:
            nw = max(1, int(round(w * scale)))
            nh = max(1, int(round(h * scale)))
            rgb_f = cv2.resize(rgb_f, (nw, nh), interpolation=cv2.INTER_AREA)
        return np.ascontiguousarray(np.clip(np.round(rgb_f * 255.0), 0, 255).astype(np.uint8))

    def _icon_from_thumbnail_array(
        self,
        rgb_u8: np.ndarray,
        *,
        target_size: QtCore.QSize | None = None,
    ) -> QtGui.QIcon:
        rgb_u8 = self._thumbnail_u8_for_screen(rgb_u8)
        if target_size is not None:
            target_w = max(1, int(target_size.width()))
            target_h = max(1, int(target_size.height()))
            src_h, src_w = int(rgb_u8.shape[0]), int(rgb_u8.shape[1])
            if src_h > 0 and src_w > 0:
                scale = min(float(target_w) / float(src_w), float(target_h) / float(src_h))
                dest_w = max(1, int(round(src_w * scale)))
                dest_h = max(1, int(round(src_h * scale)))
                if dest_w != src_w or dest_h != src_h:
                    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
                    rgb_u8 = cv2.resize(rgb_u8, (dest_w, dest_h), interpolation=interpolation)
        rgb_u8 = np.ascontiguousarray(rgb_u8.astype(np.uint8))
        h, w = int(rgb_u8.shape[0]), int(rgb_u8.shape[1])
        qimg = QtGui.QImage(rgb_u8.data, w, h, 3 * w, QtGui.QImage.Format_RGB888).copy()
        return QtGui.QIcon(QtGui.QPixmap.fromImage(qimg))

    def _icon_for_file(self, path: Path) -> QtGui.QIcon:
        suffix = path.suffix.lower()
        key = "raw" if suffix in RAW_EXTENSIONS else "image"
        cached = self._thumb_cache.get(key)
        if cached is not None:
            return cached

        icon = self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon)
        self._thumb_cache[key] = icon
        return icon

    def _on_file_selection_changed(self) -> None:
        item = self.file_list.currentItem()
        if item is None:
            if hasattr(self, "_flush_pending_adjustment_sidecar_persists_for_file_change"):
                self._flush_pending_adjustment_sidecar_persists_for_file_change()
            self._selected_file = None
            self._clear_manual_chart_points_for_file_change()
            self._clear_mtf_roi_for_file_change()
            if hasattr(self, "_clear_color_picker_samples_for_file_change"):
                self._clear_color_picker_samples_for_file_change()
            self.selected_file_label.setText(self.tr("Sin archivo seleccionado"))
            self._selection_load_timer.stop()
            self._metadata_timer.stop()
            self._clear_metadata_view()
            self._clear_viewer_histogram()
            self._refresh_selected_icc_profile_info()
            return
        raw_path = item.data(QtCore.Qt.UserRole)
        if not raw_path:
            if hasattr(self, "_flush_pending_adjustment_sidecar_persists_for_file_change"):
                self._flush_pending_adjustment_sidecar_persists_for_file_change()
            self._selected_file = None
            self._clear_manual_chart_points_for_file_change()
            self._clear_mtf_roi_for_file_change()
            if hasattr(self, "_clear_color_picker_samples_for_file_change"):
                self._clear_color_picker_samples_for_file_change()
            self._selection_load_timer.stop()
            self._metadata_timer.stop()
            self._clear_metadata_view()
            self._clear_viewer_histogram()
            self._refresh_selected_icc_profile_info()
            return
        stale_path = Path(str(raw_path))
        selected = self._resolve_existing_browsable_path(stale_path)
        if selected is None:
            self._remove_stale_file_item(item, stale_path)
            return
        if self._normalized_path_key(selected) != self._normalized_path_key(stale_path):
            self._update_file_item_path(item, selected)
        selection_changed = (
            self._selected_file is None
            or self._normalized_path_key(self._selected_file) != self._normalized_path_key(selected)
        )
        if selection_changed and hasattr(self, "_flush_pending_adjustment_sidecar_persists_for_file_change"):
            self._flush_pending_adjustment_sidecar_persists_for_file_change()
        if selection_changed:
            self._clear_manual_chart_points_for_file_change()
            self._clear_mtf_roi_for_file_change()
        self._selected_file = selected
        self.selected_file_label.setText(str(self._selected_file))
        if not self._apply_raw_sidecar_to_controls(self._selected_file):
            self._reset_development_controls_for_unconfigured_file()
        if hasattr(self, "_load_color_picker_samples_for_selected"):
            self._load_color_picker_samples_for_selected(self._selected_file)
        self._refresh_selected_icc_profile_info()
        self._queue_metadata_load(self._selected_file, include_c2pa=False)
        if self._selected_file.suffix.lower() in BROWSABLE_EXTENSIONS:
            self._set_status(self.tr("Seleccionado:") + f" {self._selected_file.name}. " + self.tr("Cargando preview..."))
            self._selection_load_timer.start(250)

    def _on_file_double_clicked(self, _item) -> None:
        self._selection_load_timer.stop()
        self._on_load_selected()

    def _show_file_list_context_menu(self, pos: QtCore.QPoint) -> None:
        item = self.file_list.itemAt(pos)
        if item is not None and not item.isSelected():
            self.file_list.clearSelection()
            item.setSelected(True)
            self.file_list.setCurrentItem(item)

        menu = QtWidgets.QMenu(self)
        menu.addAction(self.tr("Guardar ajustes actuales en imagen"), self._save_current_development_settings_to_selected)
        copy_menu = menu.addMenu(self.tr("Copiar ajustes"))
        copy_menu.addAction(
            self.tr("Todos los ajustes aplicados"),
            lambda: self._copy_adjustments_from_selected(self._all_adjustment_copy_categories()),
        )
        copy_menu.addSeparator()
        for category in self._all_adjustment_copy_categories():
            copy_menu.addAction(
                self._adjustment_copy_category_title(category),
                lambda _checked=False, c=category: self._copy_adjustments_from_selected((c,)),
            )
        paste_action = menu.addAction(self.tr("Pegar ajustes copiados"), self._paste_adjustments_to_selected)
        paste_action.setEnabled(self._has_adjustment_settings_clipboard())
        menu.addSeparator()
        menu.addAction(self.tr("Usar como referencia colorimétrica"), self._use_selected_files_as_profile_charts)
        compare_mtf_action = menu.addAction(self.tr("Comparar MTF de selección"), self._compare_mtf_for_selected_thumbnails)
        compare_mtf_action.setEnabled(len(self.file_list.selectedItems()) == 2)
        menu.addAction(self.tr("Anadir a cola"), self._queue_add_selected)
        menu.exec(self.file_list.mapToGlobal(pos))

    def _queue_metadata_load(self, path: Path, *, delay_ms: int = 180, include_c2pa: bool = True) -> None:
        self._metadata_generation += 1
        self._queued_metadata_include_c2pa = bool(include_c2pa)
        if hasattr(self, "metadata_file_label"):
            self.metadata_file_label.setText(self.tr("Metadatos:") + f" {path.name}")
        if hasattr(self, "metadata_summary"):
            self._metadata_tree_message(self.metadata_summary, self.tr("Leyendo metadatos..."))
        self._metadata_timer.start(max(0, int(delay_ms)))

    def _load_metadata_from_timer(self) -> None:
        self._refresh_metadata_view(include_c2pa=self._queued_metadata_include_c2pa)

    def _refresh_metadata_view(self, _checked: bool = False, *, include_c2pa: bool = True) -> None:
        if self._selected_file is None:
            self._clear_metadata_view()
            return
        selected = self._selected_file
        if hasattr(self, "metadata_file_label"):
            self.metadata_file_label.setText(self.tr("Metadatos:") + f" {selected}")
        if hasattr(self, "metadata_summary"):
            self._metadata_tree_message(self.metadata_summary, self.tr("Leyendo metadatos..."))
        if self._metadata_task_active:
            self._metadata_pending_request = (selected, bool(include_c2pa))
            return
        self._start_metadata_refresh_task(selected, bool(include_c2pa))

    def _start_metadata_refresh_task(self, selected: Path, include_c2pa: bool) -> None:
        self._metadata_generation += 1
        generation = self._metadata_generation

        def task():
            return generation, selected, inspect_file_metadata(selected, include_c2pa=include_c2pa)

        thread = TaskThread(task)
        self._metadata_task_active = True
        self._threads.append(thread)

        def cleanup() -> None:
            self._metadata_task_active = False
            if thread in self._threads:
                self._threads.remove(thread)
            thread.deleteLater()
            pending = self._metadata_pending_request
            self._metadata_pending_request = None
            if pending is not None:
                _pending_path, pending_c2pa = pending
                if self._selected_file is not None:
                    self._start_metadata_refresh_task(self._selected_file, pending_c2pa)

        def ok(payload) -> None:
            try:
                payload_generation, payload_path, metadata = payload
                if payload_generation != self._metadata_generation or self._selected_file != payload_path:
                    return
                self._apply_metadata_payload(payload_path, metadata)
            finally:
                cleanup()

        def fail(trace: str) -> None:
            try:
                if self._selected_file == selected:
                    msg = trace.strip().splitlines()[-1] if trace.strip() else "No se pudieron leer metadatos"
                    self._metadata_tree_message(self.metadata_summary, msg)
                    self.metadata_exif.clear()
                    self.metadata_gps.clear()
                    self.metadata_c2pa.clear()
                    self.metadata_all.setPlainText(trace[-4000:])
            finally:
                cleanup()

        thread.succeeded.connect(ok)
        thread.failed.connect(fail)
        thread.start()

    def _apply_metadata_payload(self, path: Path, payload: dict[str, Any]) -> None:
        sections = metadata_sections_text(payload)
        display = metadata_display_sections(payload)
        self.metadata_file_label.setText(self.tr("Metadatos:") + f" {path}")
        self._populate_metadata_tree(self.metadata_summary, display["summary"])
        self._populate_metadata_tree(self.metadata_exif, display["exif"])
        self._populate_metadata_tree(self.metadata_gps, display["gps"])
        self._populate_metadata_tree(self.metadata_c2pa, display["c2pa"])
        self.metadata_all.setPlainText(sections["all"])

    def _clear_metadata_view(self) -> None:
        if not hasattr(self, "metadata_summary"):
            return
        self.metadata_file_label.setText(self.tr("Sin archivo seleccionado"))
        for widget in (
            self.metadata_summary,
            self.metadata_exif,
            self.metadata_gps,
            self.metadata_c2pa,
        ):
            widget.clear()
        self.metadata_all.clear()

    def _show_metadata_all_tab(self) -> None:
        if hasattr(self, "metadata_tabs"):
            self.metadata_tabs.setCurrentWidget(self.metadata_all)

    def _metadata_tree_message(self, tree: QtWidgets.QTreeWidget, message: str) -> None:
        tree.clear()
        item = QtWidgets.QTreeWidgetItem([str(message), ""])
        tree.addTopLevelItem(item)

    def _populate_metadata_tree(self, tree: QtWidgets.QTreeWidget, groups: Any) -> None:
        tree.clear()
        if not groups:
            self._metadata_tree_message(tree, "Sin datos")
            return
        if isinstance(groups, list):
            for group in groups:
                self._add_metadata_group(tree, group)
        elif isinstance(groups, dict):
            self._add_metadata_dict(tree, None, groups)
        else:
            self._metadata_tree_message(tree, str(groups))
        tree.expandToDepth(0)

    def _add_metadata_group(self, tree: QtWidgets.QTreeWidget, group: dict[str, Any]) -> None:
        title = str(group.get("title") or "Metadatos")
        parent = QtWidgets.QTreeWidgetItem([title, ""])
        font = parent.font(0)
        font.setBold(True)
        parent.setFont(0, font)
        parent.setFirstColumnSpanned(False)
        tree.addTopLevelItem(parent)
        for item in group.get("items") or []:
            if isinstance(item, dict):
                child = QtWidgets.QTreeWidgetItem([str(item.get("label", "")), str(item.get("value", ""))])
                child.setToolTip(1, str(item.get("value", "")))
                parent.addChild(child)

    def _add_metadata_dict(self, tree: QtWidgets.QTreeWidget, parent: QtWidgets.QTreeWidgetItem | None, payload: dict[str, Any]) -> None:
        for key, value in sorted(payload.items()):
            if isinstance(value, dict):
                node = QtWidgets.QTreeWidgetItem([str(key), ""])
                if parent is None:
                    tree.addTopLevelItem(node)
                else:
                    parent.addChild(node)
                self._add_metadata_dict(tree, node, value)
            elif isinstance(value, list):
                node = QtWidgets.QTreeWidgetItem([str(key), f"{len(value)} elementos"])
                if parent is None:
                    tree.addTopLevelItem(node)
                else:
                    parent.addChild(node)
                for idx, item in enumerate(value):
                    child = QtWidgets.QTreeWidgetItem([str(idx + 1), json.dumps(item, ensure_ascii=False) if isinstance(item, (dict, list)) else str(item)])
                    node.addChild(child)
            else:
                node = QtWidgets.QTreeWidgetItem([str(key), str(value)])
                node.setToolTip(1, str(value))
                if parent is None:
                    tree.addTopLevelItem(node)
                else:
                    parent.addChild(node)
