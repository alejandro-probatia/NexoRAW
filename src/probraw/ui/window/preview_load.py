from __future__ import annotations

from ._imports import *  # noqa: F401,F403


class PreviewLoadMixin:
    def _load_selected_from_timer(self) -> None:
        if self._selected_file is None:
            return
        self._on_load_selected(show_message=False)

    def _preview_load_format_duration(self, seconds: float | None) -> str:
        if seconds is None:
            return "--"
        value = max(0.0, float(seconds))
        if value < 60.0:
            return f"{value:.1f}s"
        minutes = int(value // 60)
        rest = int(round(value - minutes * 60))
        return f"{minutes}m {rest:02d}s"

    def _preview_load_settings_float(self, key: str, default: float) -> float:
        try:
            value = float(self._settings.value(key, default))
        except Exception:
            return float(default)
        return value if np.isfinite(value) and value > 0.0 else float(default)

    def _record_preview_load_timing(self, seconds: float) -> None:
        value = float(seconds)
        if not np.isfinite(value) or value <= 0.0:
            return
        key = "performance/preview_load_seconds_ewma"
        try:
            previous = float(self._settings.value(key, 0.0))
        except Exception:
            previous = 0.0
        averaged = value if previous <= 0.0 else previous * 0.65 + value * 0.35
        try:
            self._settings.setValue(key, float(averaged))
            self._settings.sync()
        except Exception:
            pass

    def _preview_load_estimate_seconds(self, selected: Path, fast_raw: bool, max_preview_side: int) -> float:
        if selected.suffix.lower() not in RAW_EXTENSIONS:
            default = 0.6
        elif int(max_preview_side) <= 0:
            default = 3.0
        elif bool(fast_raw):
            default = 1.2
        else:
            default = 2.0
        return self._preview_load_settings_float("performance/preview_load_seconds_ewma", default)

    def _start_preview_load_progress(self, selected: Path, fast_raw: bool, max_preview_side: int) -> None:
        estimate = self._preview_load_estimate_seconds(selected, fast_raw, max_preview_side)
        self._preview_load_progress_started_at = time.perf_counter()
        self._preview_load_progress_estimated_seconds = float(estimate)
        self._preview_load_progress_label = self.tr("Vista previa: cargando") + f" {selected.name}"
        self._preview_load_progress_visible = bool(estimate >= 1.0)
        timer = getattr(self, "_preview_load_progress_timer", None)
        if timer is not None and not timer.isActive():
            timer.start()
        self._update_preview_load_progress_status()

    def _update_preview_load_progress_status(self) -> None:
        started = getattr(self, "_preview_load_progress_started_at", None)
        if started is None:
            return
        elapsed = max(0.0, time.perf_counter() - float(started))
        estimate = getattr(self, "_preview_load_progress_estimated_seconds", None)
        if not bool(getattr(self, "_preview_load_progress_visible", False)) and elapsed < 1.0:
            return
        self._preview_load_progress_visible = True
        label = str(getattr(self, "_preview_load_progress_label", "") or self.tr("Vista previa: cargando"))
        if estimate is not None and float(estimate) > 0.0:
            remaining = max(0.0, float(estimate) - elapsed)
            time_text = (
                self.tr("Transcurrido")
                + f" {self._preview_load_format_duration(elapsed)} | "
                + self.tr("estimado")
                + f" ~{self._preview_load_format_duration(float(estimate))} | "
                + self.tr("restante")
                + f" {self._preview_load_format_duration(remaining)}"
            )
            value = 95 if elapsed > float(estimate) else int(np.clip((elapsed / float(estimate)) * 90.0, 0.0, 90.0))
            self._set_global_operation_progress(
                "preview",
                label,
                time_text=time_text,
                phase_text=self.tr("RAW/archivo: activo | Vista previa: pendiente | Caché: pendiente"),
                minimum=0,
                maximum=100,
                value=value,
            )
        else:
            self._set_global_operation_progress(
                "preview",
                label,
                time_text=self.tr("Transcurrido") + f" {self._preview_load_format_duration(elapsed)}",
                phase_text=self.tr("RAW/archivo: activo | Vista previa: pendiente | Caché: pendiente"),
                minimum=0,
                maximum=0,
                value=0,
            )

    def _finish_preview_load_progress(self, *, success: bool, detail: str, elapsed_seconds: float | None = None) -> None:
        timer = getattr(self, "_preview_load_progress_timer", None)
        if timer is not None:
            timer.stop()
        started = getattr(self, "_preview_load_progress_started_at", None)
        elapsed = (
            float(elapsed_seconds)
            if elapsed_seconds is not None
            else (time.perf_counter() - float(started) if started is not None else None)
        )
        visible = bool(getattr(self, "_preview_load_progress_visible", False))
        self._preview_load_progress_started_at = None
        self._preview_load_progress_estimated_seconds = None
        self._preview_load_progress_label = ""
        self._preview_load_progress_visible = False
        if elapsed is not None:
            self._record_preview_load_timing(float(elapsed))
        if visible:
            self._set_global_operation_progress(
                "preview",
                detail,
                time_text=self.tr("Total:") + f" {self._preview_load_format_duration(elapsed)}",
                phase_text=(
                    self.tr("RAW/archivo: listo | Vista previa: lista | Caché: actualizada")
                    if success
                    else self.tr("RAW/archivo: error | Vista previa: detenida | Caché: sin actualizar")
                ),
                minimum=0,
                maximum=100,
                value=100 if success else 0,
            )
            QtCore.QTimer.singleShot(1800, lambda: self._reset_global_operation_progress(owner="preview"))

    def _clear_loaded_preview_for_pending_load(self, base_signature: str) -> None:
        if self._loaded_preview_base_signature == base_signature:
            return
        if self._original_linear is not None and self._loaded_preview_base_signature is None:
            return
        self._original_linear = None
        self._adjusted_linear = None
        self._adjusted_linear_signature = None
        self._preview_srgb = None
        self._last_loaded_preview_key = None
        self._loaded_preview_base_signature = None
        self._loaded_preview_fast_raw = None
        self._loaded_preview_source_max_side = 0
        self._loaded_preview_max_side_request = None
        self._loaded_preview_source_profile_path = None
        self._clear_adjustment_caches()

    def _raw_embedded_preview_cache_key(
        self,
        selected: Path,
        max_preview_side: int,
        *,
        apply_orientation: bool = True,
    ) -> str:
        try:
            st = selected.stat()
            stamp = f"{st.st_mtime_ns}:{st.st_size}"
        except Exception:
            stamp = "nostat"
        orientation_key = 1 if bool(apply_orientation) else 0
        return (
            f"{self._cache_path_identity(selected)}|{stamp}|embedded-preview-u8|"
            f"ms={int(max_preview_side)}|orient={orientation_key}"
        )

    def _cached_raw_embedded_preview_u8(self, key: str) -> np.ndarray | None:
        cached = self._raw_embedded_preview_cache.get(key)
        if cached is None:
            return None
        self._raw_embedded_preview_cache_order = [k for k in self._raw_embedded_preview_cache_order if k != key]
        self._raw_embedded_preview_cache_order.append(key)
        return cached.copy()

    def _cache_raw_embedded_preview_u8(self, key: str, rgb_u8: np.ndarray) -> None:
        rgb = np.asarray(rgb_u8, dtype=np.uint8)
        if rgb.ndim != 3 or rgb.shape[2] < 3:
            return
        if key in self._raw_embedded_preview_cache:
            self._raw_embedded_preview_cache.pop(key, None)
            self._raw_embedded_preview_cache_order = [k for k in self._raw_embedded_preview_cache_order if k != key]
        self._raw_embedded_preview_cache[key] = np.ascontiguousarray(rgb[..., :3]).copy()
        self._raw_embedded_preview_cache_order.append(key)
        while len(self._raw_embedded_preview_cache_order) > 16:
            old = self._raw_embedded_preview_cache_order.pop(0)
            self._raw_embedded_preview_cache.pop(old, None)

    def _queue_raw_embedded_preview(
        self,
        *,
        selected: Path,
        max_preview_side: int,
        final_cache_key: str,
    ) -> None:
        if selected.suffix.lower() not in RAW_EXTENSIONS:
            return
        if self._last_loaded_preview_key == final_cache_key and self._original_linear is not None:
            return
        apply_orientation = False
        request_key = self._raw_embedded_preview_cache_key(
            selected,
            max_preview_side,
            apply_orientation=apply_orientation,
        )
        self._raw_embedded_preview_expected_key = request_key
        cached = self._cached_raw_embedded_preview_u8(request_key)
        if cached is not None:
            self._apply_raw_embedded_preview_u8(
                selected=selected,
                request_key=request_key,
                final_cache_key=final_cache_key,
                rgb_u8=cached,
            )
            return

        def task():
            side = int(max_preview_side) if int(max_preview_side) > 0 else PREVIEW_AUTO_BASE_MAX_SIDE
            rgb_u8 = extract_embedded_thumbnail(
                selected,
                max_side=side,
                apply_orientation=apply_orientation,
            )
            return selected, request_key, final_cache_key, rgb_u8

        def ok(payload) -> None:
            loaded_selected, loaded_request_key, loaded_final_key, rgb_u8 = payload
            if rgb_u8 is None:
                return
            self._cache_raw_embedded_preview_u8(loaded_request_key, rgb_u8)
            self._apply_raw_embedded_preview_u8(
                selected=loaded_selected,
                request_key=loaded_request_key,
                final_cache_key=loaded_final_key,
                rgb_u8=rgb_u8,
            )

        def fail(_trace: str) -> None:
            return

        if self._run_preview_load_inline():
            try:
                ok(task())
            except Exception:
                fail(traceback.format_exc())
            return

        thread = TaskThread(task)
        self._threads.append(thread)

        def cleanup() -> None:
            if thread in self._threads:
                self._threads.remove(thread)
            thread.deleteLater()

        def ok_and_cleanup(payload) -> None:
            try:
                ok(payload)
            finally:
                cleanup()

        def fail_and_cleanup(trace: str) -> None:
            try:
                fail(trace)
            finally:
                cleanup()

        thread.succeeded.connect(ok_and_cleanup)
        thread.failed.connect(fail_and_cleanup)
        thread.start()

    def _apply_raw_embedded_preview_u8(
        self,
        *,
        selected: Path,
        request_key: str,
        final_cache_key: str,
        rgb_u8: np.ndarray,
    ) -> None:
        if self._raw_embedded_preview_expected_key != request_key:
            return
        if self._selected_file != selected:
            return
        if self._last_loaded_preview_key == final_cache_key and self._original_linear is not None:
            return
        rgb = np.asarray(rgb_u8, dtype=np.uint8)
        if rgb.ndim != 3 or rgb.shape[2] < 3:
            return
        rgb = np.ascontiguousarray(rgb[..., :3])
        self._preview_srgb = rgb.astype(np.float32) / np.float32(255.0)
        display_u8 = srgb_u8_to_display_u8(rgb, self._active_display_profile_path())
        self._set_result_display_u8(
            display_u8,
            compare_enabled=bool(self.chk_compare.isChecked()),
            bypass_profile=False,
        )
        self.preview_analysis.setPlainText(self.tr("Vista previa RAW embebida provisional; revelando imagen colorimetrica..."))
        self._set_status(self.tr("Vista previa RAW embebida:") + f" {selected.name}")

    def _on_load_selected(self, _checked: bool = False, *, show_message: bool = True) -> None:
        if self._selected_file is None:
            self._clear_viewer_histogram()
            if show_message:
                QtWidgets.QMessageBox.information(self, self.tr("Info"), "Selecciona primero un archivo.")
            return

        original_selected = self._selected_file
        selected = self._resolve_existing_browsable_path(original_selected)
        if selected is None:
            self._selection_load_timer.stop()
            self._metadata_timer.stop()
            self._selected_file = None
            self._last_loaded_preview_key = None
            self._clear_manual_chart_points_for_file_change()
            self._clear_mtf_roi_for_file_change()
            if hasattr(self, "_clear_color_picker_samples_for_file_change"):
                self._clear_color_picker_samples_for_file_change()
            self.selected_file_label.setText(self.tr("Sin archivo seleccionado"))
            self._clear_metadata_view()
            self._clear_viewer_histogram()
            self._set_status(self.tr("Archivo no encontrado:") + f" {original_selected}")
            if show_message:
                QtWidgets.QMessageBox.information(self, self.tr("Info"), f"No existe el archivo:\n{original_selected}")
            return
        if self._normalized_path_key(selected) != self._normalized_path_key(original_selected):
            self._selected_file = selected
            self.selected_file_label.setText(str(selected))
        recipe = self._color_managed_preview_recipe(self._build_effective_recipe())
        is_raw = selected.suffix.lower() in RAW_EXTENSIONS
        fast_raw = False
        max_preview_side = self._effective_preview_max_side()
        input_profile_path = self._active_session_icc_for_settings()
        base_signature = self._preview_base_signature(
            selected=selected,
            recipe=recipe,
            input_profile_path=input_profile_path,
        )
        cache_key = self._preview_cache_key(
            selected=selected,
            recipe=recipe,
            fast_raw=fast_raw,
            max_preview_side=max_preview_side,
            input_profile_path=input_profile_path,
        )

        if (
            self._original_linear is not None
            and self._loaded_preview_base_signature == base_signature
            and self._last_loaded_preview_key is not None
        ):
            current_side = int(max(self._original_linear.shape[0], self._original_linear.shape[1]))
            loaded_fast_raw = bool(self._loaded_preview_fast_raw)
            loaded_side_request = getattr(self, "_loaded_preview_max_side_request", None)
            same_or_higher_quality = (
                (max_preview_side <= 0 and not loaded_fast_raw and loaded_side_request == 0)
                or (max_preview_side > 0 and current_side >= int(max_preview_side))
            )
            # Never downgrade quality/source size implicitly while staying on
            # the same file + processing recipe.
            if (not loaded_fast_raw and fast_raw) or same_or_higher_quality:
                if self._manual_chart_marking_after_reload:
                    self._manual_chart_marking_after_reload = False
                    self._begin_manual_chart_marking()
                if cache_key == self._last_loaded_preview_key:
                    return
                self._refresh_preview()
                return

        if cache_key == self._last_loaded_preview_key and self._original_linear is not None:
            if self._manual_chart_marking_after_reload:
                self._manual_chart_marking_after_reload = False
                self._begin_manual_chart_marking()
            return

        cached = self._cached_preview_image(cache_key, selected=selected)
        if cached is not None:
            self._original_linear = cached.copy()
            self._adjusted_linear = self._original_linear
            self._adjusted_linear_signature = None
            self._last_loaded_preview_key = cache_key
            self._loaded_preview_base_signature = base_signature
            self._loaded_preview_fast_raw = bool(fast_raw)
            self._loaded_preview_max_side_request = int(max_preview_side)
            self._loaded_preview_source_max_side = int(max(self._original_linear.shape[0], self._original_linear.shape[1]))
            self._loaded_preview_source_profile_path = self._source_profile_for_preview_recipe(recipe)
            self._clear_adjustment_caches()
            self._clear_mtf_roi_for_file_change()
            self._auto_update_mtf_pixel_pitch_from_file(selected)
            self._refresh_preview()
            self._restore_persisted_mtf_analysis_for_selected(selected)
            if hasattr(self, "_load_color_picker_samples_for_selected"):
                self._load_color_picker_samples_for_selected(selected)
                if getattr(self, "_color_picker_samples", None):
                    self._ensure_color_picker_real_pixel_source()
            self._log_preview(f"Vista previa cargada desde caché: {selected.name}")
            self._set_status(self.tr("Vista previa en caché:") + f" {selected.name}")
            self._schedule_export_parity_preview_if_needed(
                selected=selected,
                max_preview_side=max_preview_side,
                fast_raw=fast_raw,
            )
            if self._manual_chart_marking_after_reload:
                self._manual_chart_marking_after_reload = False
                self._begin_manual_chart_marking()
            self._schedule_adjacent_preview_prefetch(
                selected=selected,
                recipe=recipe,
                max_preview_side=max_preview_side,
                input_profile_path=input_profile_path,
            )
            return

        self._clear_loaded_preview_for_pending_load(base_signature)
        if is_raw:
            self._queue_raw_embedded_preview(
                selected=selected,
                max_preview_side=max_preview_side,
                final_cache_key=cache_key,
            )
        recipe_request = Recipe(**asdict(recipe))
        self._queue_preview_load_request((selected, recipe_request, fast_raw, max_preview_side, cache_key, input_profile_path))

    def _queue_preview_load_request(
        self,
        request: tuple[Path, Recipe, bool, int, str, Path | None],
    ) -> None:
        selected, _recipe, _fast_raw, _max_preview_side, cache_key, _input_profile_path = request
        if self._preview_load_task_active:
            if self._preview_load_inflight_key == cache_key:
                return
            self._preempt_preview_load_task(request)
            return
        self._preview_load_pending_request = None
        self._start_preview_load_task(request)
        self._set_status(self.tr("Cargando vista previa:") + f" {selected.name}")

    def _preempt_preview_load_task(
        self,
        request: tuple[Path, Recipe, bool, int, str, Path | None],
    ) -> None:
        selected, _recipe, _fast_raw, _max_preview_side, _cache_key, _input_profile_path = request
        self._preview_load_task_token = int(getattr(self, "_preview_load_task_token", 0)) + 1
        self._preview_load_task_active = False
        self._preview_load_inflight_key = None
        self._preview_load_pending_request = None
        self._start_preview_load_task(request)
        self._set_status(self.tr("Cargando vista previa:") + f" {selected.name}")

    def _start_preview_load_task(
        self,
        request: tuple[Path, Recipe, bool, int, str, Path | None],
    ) -> None:
        selected, recipe, fast_raw, max_preview_side, cache_key, input_profile_path = request
        self._preview_load_task_token = int(getattr(self, "_preview_load_task_token", 0)) + 1
        task_token = int(self._preview_load_task_token)

        def task():
            started = time.perf_counter()
            image_linear, msg = load_image_for_preview(
                selected,
                recipe=recipe,
                fast_raw=fast_raw,
                max_preview_side=max_preview_side,
                input_profile_path=input_profile_path,
                cache_dir=self._preview_decode_cache_dir(selected),
            )
            return selected, cache_key, image_linear, msg, float(time.perf_counter() - started)

        self._preview_load_task_active = True
        self._preview_load_inflight_key = cache_key
        self._start_preview_load_progress(selected, fast_raw, max_preview_side)
        thread: TaskThread | None = None

        def cleanup() -> None:
            stale = (
                int(getattr(self, "_preview_load_task_token", 0)) != task_token
                or self._preview_load_inflight_key != cache_key
            )
            if thread is not None and thread in self._threads:
                self._threads.remove(thread)
            if thread is not None:
                thread.deleteLater()
            if stale:
                return
            self._preview_load_task_active = False
            self._preview_load_inflight_key = None
            pending = self._preview_load_pending_request
            self._preview_load_pending_request = None
            if pending is not None:
                self._start_preview_load_task(pending)

        def ok(payload) -> None:
            try:
                loaded_selected, loaded_key, image_linear, msg, elapsed = payload
                stale_task = (
                    int(getattr(self, "_preview_load_task_token", 0)) != task_token
                    or self._preview_load_inflight_key != cache_key
                )
                if stale_task:
                    self._write_preview_to_disk_cache(
                        loaded_key,
                        np.asarray(image_linear, dtype=np.float32),
                        selected=loaded_selected,
                    )
                    return
                if self._selected_file != loaded_selected:
                    self._finish_preview_load_progress(
                        success=False,
                        detail=self.tr("Vista previa descartada:") + f" {loaded_selected.name}",
                        elapsed_seconds=elapsed,
                    )
                    return
                self._original_linear = np.asarray(image_linear, dtype=np.float32)
                self._adjusted_linear = self._original_linear
                self._adjusted_linear_signature = None
                self._last_loaded_preview_key = loaded_key
                self._loaded_preview_base_signature = self._preview_base_signature(
                    selected=selected,
                    recipe=recipe,
                    input_profile_path=input_profile_path,
                )
                self._loaded_preview_fast_raw = bool(fast_raw)
                self._loaded_preview_max_side_request = int(max_preview_side)
                self._loaded_preview_source_max_side = int(
                    max(self._original_linear.shape[0], self._original_linear.shape[1])
                )
                self._loaded_preview_source_profile_path = self._source_profile_for_preview_recipe(recipe)
                self._clear_adjustment_caches()
                self._clear_mtf_roi_for_file_change()
                self._auto_update_mtf_pixel_pitch_from_file(loaded_selected)
                self._cache_preview_image(loaded_key, self._original_linear, selected=loaded_selected)
                self._refresh_preview()
                self._restore_persisted_mtf_analysis_for_selected(loaded_selected)
                if hasattr(self, "_load_color_picker_samples_for_selected"):
                    self._load_color_picker_samples_for_selected(loaded_selected)
                    if getattr(self, "_color_picker_samples", None):
                        self._ensure_color_picker_real_pixel_source()
                self._log_preview(msg)
                self._set_status(self.tr("Vista previa cargada:") + f" {loaded_selected.name}")
                self._finish_preview_load_progress(
                    success=True,
                    detail=self.tr("Vista previa cargada:") + f" {loaded_selected.name}",
                    elapsed_seconds=elapsed,
                )
                self._schedule_export_parity_preview_if_needed(
                    selected=loaded_selected,
                    max_preview_side=max_preview_side,
                    fast_raw=fast_raw,
                )
                self._schedule_adjacent_preview_prefetch(
                    selected=loaded_selected,
                    recipe=recipe,
                    max_preview_side=max_preview_side,
                    input_profile_path=input_profile_path,
                )
                if self._manual_chart_marking_after_reload:
                    self._manual_chart_marking_after_reload = False
                    self._begin_manual_chart_marking()
            finally:
                cleanup()

        def fail(trace: str) -> None:
            try:
                stale_task = (
                    int(getattr(self, "_preview_load_task_token", 0)) != task_token
                    or self._preview_load_inflight_key != cache_key
                )
                if stale_task:
                    return
                self._log_preview(trace[-1200:])
                if self._selected_file == selected:
                    self._set_status(self.tr("Error de vista previa:") + f" {selected.name}")
                self._finish_preview_load_progress(
                    success=False,
                    detail=self.tr("Error de vista previa:") + f" {selected.name}",
                )
            finally:
                cleanup()

        if self._run_preview_load_inline():
            try:
                ok(task())
            except Exception:
                fail(traceback.format_exc())
            return

        thread = TaskThread(task)
        self._threads.append(thread)
        thread.succeeded.connect(ok)
        thread.failed.connect(fail)
        thread.start()

    def _schedule_adjacent_preview_prefetch(
        self,
        *,
        selected: Path,
        recipe: Recipe,
        max_preview_side: int,
        input_profile_path: Path | None,
    ) -> None:
        if int(max_preview_side) <= 0:
            return
        if bool(getattr(self, "_background_threads_shutdown", False)):
            return
        if self._run_preview_load_inline():
            return
        self._preview_prefetch_pending_request = (
            selected,
            Recipe(**asdict(recipe)),
            int(max_preview_side),
            input_profile_path,
        )
        QtCore.QTimer.singleShot(120, self._start_pending_adjacent_preview_prefetch)

    def _start_pending_adjacent_preview_prefetch(self) -> None:
        request = getattr(self, "_preview_prefetch_pending_request", None)
        if request is None:
            return
        if bool(getattr(self, "_preview_load_task_active", False)):
            QtCore.QTimer.singleShot(250, self._start_pending_adjacent_preview_prefetch)
            return
        if bool(getattr(self, "_preview_prefetch_task_active", False)):
            return
        self._preview_prefetch_pending_request = None
        selected, recipe, max_preview_side, input_profile_path = request
        candidates = self._adjacent_preview_prefetch_paths(selected, limit=2)
        if not candidates:
            return
        jobs: list[tuple[Path, str]] = []
        for path in candidates:
            if path.suffix.lower() not in BROWSABLE_EXTENSIONS:
                continue
            key = self._preview_cache_key(
                selected=path,
                recipe=recipe,
                fast_raw=False,
                max_preview_side=max_preview_side,
                input_profile_path=input_profile_path,
            )
            if self._preview_cache_has_exact_entry(key, selected=path):
                continue
            jobs.append((path, key))
        if not jobs:
            return

        self._preview_prefetch_generation = int(getattr(self, "_preview_prefetch_generation", 0)) + 1
        generation = int(self._preview_prefetch_generation)
        recipe_payload = asdict(recipe)

        def task():
            built: list[str] = []
            skipped = 0
            errors: list[str] = []
            for path, key in jobs:
                try:
                    if self._preview_cache_has_exact_entry(key, selected=path):
                        skipped += 1
                        continue
                    image_linear, _msg = load_image_for_preview(
                        path,
                        recipe=Recipe(**recipe_payload),
                        fast_raw=False,
                        max_preview_side=max_preview_side,
                        input_profile_path=input_profile_path,
                        cache_dir=self._preview_decode_cache_dir(path),
                    )
                    self._write_preview_to_disk_cache(
                        key,
                        np.asarray(image_linear, dtype=np.float32),
                        selected=path,
                    )
                    built.append(path.name)
                except Exception as exc:
                    errors.append(f"{path.name}: {exc}")
            return generation, built, skipped, errors

        thread = TaskThread(task)
        self._preview_prefetch_task_active = True
        self._threads.append(thread)

        def cleanup() -> None:
            if thread in self._threads:
                self._threads.remove(thread)
            thread.deleteLater()
            self._preview_prefetch_task_active = False
            if self._preview_prefetch_pending_request is not None:
                QtCore.QTimer.singleShot(80, self._start_pending_adjacent_preview_prefetch)

        def ok(payload) -> None:
            try:
                payload_generation, built, _skipped, errors = payload
                if int(payload_generation) != int(getattr(self, "_preview_prefetch_generation", 0)):
                    return
                if built:
                    self._log_preview("Precarga de vistas previas: " + ", ".join(built))
                if errors:
                    self._log_preview("Aviso: precarga de vista previa omitida: " + errors[0])
            finally:
                cleanup()

        def fail(trace: str) -> None:
            try:
                self._log_preview(f"Aviso: precarga de vista previa fallida: {trace.strip().splitlines()[-1] if trace.strip() else 'error'}")
            finally:
                cleanup()

        thread.succeeded.connect(ok)
        thread.failed.connect(fail)
        thread.start()

    def _adjacent_preview_prefetch_paths(self, selected: Path, *, limit: int) -> list[Path]:
        if not hasattr(self, "file_list"):
            return []
        selected_key = self._normalized_path_key(selected)
        items: list[Path] = []
        selected_index = -1
        for index in range(self.file_list.count()):
            item = self.file_list.item(index)
            raw = item.data(QtCore.Qt.UserRole) if item is not None else None
            if not raw:
                continue
            path = Path(str(raw))
            items.append(path)
            if self._normalized_path_key(path) == selected_key:
                selected_index = len(items) - 1
        if selected_index < 0:
            return []
        ordered: list[Path] = []
        for offset in range(1, max(1, int(limit)) + 1):
            for idx in (selected_index + offset, selected_index - offset):
                if 0 <= idx < len(items):
                    candidate = self._resolve_existing_browsable_path(items[idx])
                    if candidate is not None and candidate not in ordered:
                        ordered.append(candidate)
                if len(ordered) >= int(limit):
                    return ordered
        return ordered

    def _preview_cache_has_exact_entry(self, key: str, *, selected: Path | None = None) -> bool:
        if key in getattr(self, "_preview_cache", {}):
            return True
        for cache_dir in self._disk_cache_dirs(selected, "previews"):
            if self._preview_disk_cache_path(key, base_dir=cache_dir).is_file():
                return True
        return False

    def _schedule_export_parity_preview_if_needed(
        self,
        *,
        selected: Path,
        max_preview_side: int,
        fast_raw: bool,
    ) -> None:
        if int(max_preview_side) <= 0:
            return
        if hasattr(self, "_automatic_full_final_preview_enabled") and not self._automatic_full_final_preview_enabled():
            return
        if bool(fast_raw):
            return
        if selected.suffix.lower() not in RAW_EXTENSIONS:
            return
        if bool(getattr(self, "_preview_export_parity_requested", False)):
            return
        try:
            if not self._preview_requires_max_quality():
                return
        except Exception:
            return
        try:
            if self._normalized_path_key(getattr(self, "_selected_file", selected)) != self._normalized_path_key(selected):
                return
        except Exception:
            if getattr(self, "_selected_file", selected) != selected:
                return
        self._preview_export_parity_requested = True
        self._set_status(self.tr("Refinando vista previa exacta de exportacion:") + f" {selected.name}")
        try:
            self._on_load_selected(show_message=False)
        finally:
            self._preview_export_parity_requested = False

    def _on_precache_visible_previews(self, *, full_resolution: bool) -> None:
        files = [p for p in self._file_list_paths() if p.suffix.lower() in RAW_EXTENSIONS]
        if not files:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), "No hay RAW visibles para precalcular.")
            return
        mode_label = "1:1" if full_resolution else "normal"
        reply = QtWidgets.QMessageBox.question(
            self,
            self.tr("Precálculo de vistas previas"),
            (
                self.tr("Se van a precalcular") + f" {len(files)} " + self.tr("vistas previas RAW en modo") + f" {mode_label}.\n\n"
                + self.tr("Este proceso puede tardar, pero mejora la respuesta posterior.\nContinuar?")
            ),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.Yes,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return
        self._start_precache_visible_previews(files, full_resolution=full_resolution)

    def _on_precache_selected_preview(self) -> None:
        if self._selected_file is None:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("Selecciona primero un RAW."))
            return
        selected = self._resolve_existing_browsable_path(self._selected_file)
        if selected is None:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("No existe el archivo seleccionado."))
            return
        if selected.suffix.lower() not in RAW_EXTENSIONS:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("El archivo seleccionado no es RAW."))
            return
        self._start_precache_visible_previews([selected], full_resolution=True, scope_label=self.tr("actual"))

    def _start_precache_visible_previews(
        self,
        files: list[Path],
        *,
        full_resolution: bool,
        scope_label: str | None = None,
    ) -> None:
        recipe_base = self._color_managed_preview_recipe(self._build_effective_recipe())
        recipe_base_payload = asdict(recipe_base)
        max_preview_side = 0
        mode_label = "1:1"
        if scope_label:
            mode_label = f"{mode_label} {scope_label}"

        def task():
            built = 0
            skipped = 0
            errors: list[dict[str, str]] = []
            for src in files:
                try:
                    recipe = Recipe(**recipe_base_payload)
                    is_raw = src.suffix.lower() in RAW_EXTENSIONS
                    fast_raw = False
                    cache_key = self._preview_cache_key(
                        selected=src,
                        recipe=recipe,
                        fast_raw=fast_raw,
                        max_preview_side=max_preview_side,
                        input_profile_path=self._active_session_icc_for_settings(),
                    )
                    if self._read_preview_from_disk_cache(cache_key, selected=src) is not None:
                        skipped += 1
                        continue
                    image_linear, _msg = load_image_for_preview(
                        src,
                        recipe=recipe,
                        fast_raw=fast_raw,
                        max_preview_side=max_preview_side,
                        input_profile_path=self._active_session_icc_for_settings(),
                        cache_dir=self._preview_decode_cache_dir(src),
                    )
                    self._write_preview_to_disk_cache(
                        cache_key,
                        np.asarray(image_linear, dtype=np.float32),
                        selected=src,
                    )
                    built += 1
                except Exception as exc:
                    errors.append({"source": str(src), "error": str(exc)})
            return {
                "mode": mode_label,
                "total": len(files),
                "built": built,
                "skipped": skipped,
                "errors": errors,
            }

        def on_success(payload) -> None:
            total = int(payload.get("total", 0))
            built = int(payload.get("built", 0))
            skipped = int(payload.get("skipped", 0))
            errors = payload.get("errors", [])
            self._log_preview(
                f"Precache {payload.get('mode', self.tr('normal'))}: "
                f"{built} generadas, {skipped} ya en cache, {len(errors)} errores (total {total})."
            )
            self._set_status(
                f"Precache {payload.get('mode', self.tr('normal'))} completada: "
                f"{built} nuevas, {skipped} reutilizadas."
            )
            if full_resolution and self._selected_file is not None:
                self._last_loaded_preview_key = None
                self._on_load_selected(show_message=False)

        self._start_background_task(
            f"Precache previews RAW ({mode_label})",
            task,
            on_success,
        )
