from __future__ import annotations

from ._imports import *  # noqa: F401,F403


class SessionQueueMixin:
    def _queue_add_files(self, files: list[Path]) -> int:
        existing = {item["source"] for item in self._develop_queue if item.get("source")}
        added = 0
        for src in files:
            source = str(src)
            if source in existing:
                continue
            profile_id = self._development_profile_from_sidecar(src) or self._active_development_profile_id
            self._develop_queue.append(
                {
                    "source": source,
                    "development_profile_id": profile_id,
                    "status": "pending",
                    "progress": 0,
                    "output_tiff": "",
                    "message": "",
                }
            )
            existing.add(source)
            added += 1

        if added:
            self._refresh_queue_table()
            self._save_active_session(silent=True)
        return added

    def _queue_add_selected(self) -> None:
        if hasattr(self, "_flush_render_adjustment_sidecar_persist"):
            self._flush_render_adjustment_sidecar_persist()
        if hasattr(self, "_flush_detail_adjustment_sidecar_persist"):
            self._flush_detail_adjustment_sidecar_persist()
        files = self._collect_selected_file_paths()
        if not files:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("No hay seleccion para anadir a la cola."))
            return
        added = self._queue_add_files(files)
        self._set_status(self.tr("Cola actualizada:") + f" {added} " + self.tr("elementos anadidos"))

    def _queue_add_session_raws(self) -> None:
        source_dir = Path(self.batch_input_dir.text().strip() or self._current_dir)
        if not source_dir.exists() or not source_dir.is_dir():
            QtWidgets.QMessageBox.information(self, self.tr("Info"), f"Directorio inválido: {source_dir}")
            return
        files = [
            p for p in sorted(source_dir.iterdir())
            if p.is_file() and p.suffix.lower() in BROWSABLE_EXTENSIONS
        ]
        if not files:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("No hay RAW/imagenes compatibles en el directorio."))
            return
        added = self._queue_add_files(files)
        self._set_status(self.tr("Cola actualizada:") + f" {added} " + self.tr("archivos anadidos desde") + f" {source_dir}")

    def _queue_remove_selected(self) -> None:
        if not self._develop_queue:
            return
        rows = sorted({i.row() for i in self.queue_table.selectionModel().selectedRows()}, reverse=True)
        if not rows:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), "Selecciona filas de la cola para quitar.")
            return
        for row in rows:
            if 0 <= row < len(self._develop_queue):
                self._develop_queue.pop(row)
        self._refresh_queue_table()
        self._save_active_session(silent=True)

    def _queue_clear(self) -> None:
        self._develop_queue = []
        self._refresh_queue_table()
        self._save_active_session(silent=True)
        self._set_status(self.tr("Cola vaciada"))

    def _refresh_queue_table(self) -> None:
        if not hasattr(self, "queue_table"):
            return

        self.queue_table.setRowCount(0)
        pending = 0
        done = 0
        errors = 0

        for item in self._develop_queue:
            status = str(item.get("status") or "pending")
            if status == "done":
                done += 1
            elif status == "error":
                errors += 1
            else:
                pending += 1

            row = self.queue_table.rowCount()
            self.queue_table.insertRow(row)
            self.queue_table.setItem(row, 0, QtWidgets.QTableWidgetItem(str(item.get("source") or "")))
            self.queue_table.setItem(row, 1, QtWidgets.QTableWidgetItem(self._development_profile_label(str(item.get("development_profile_id") or ""))))
            self.queue_table.setItem(row, 2, QtWidgets.QTableWidgetItem(status))
            self.queue_table.setCellWidget(row, 3, self._queue_progress_widget(item, status))
            self.queue_table.setItem(row, 4, QtWidgets.QTableWidgetItem(str(item.get("output_tiff") or "")))
            self.queue_table.setItem(row, 5, QtWidgets.QTableWidgetItem(str(item.get("message") or "")))

        self.queue_status_label.setText(
            f"Elementos: {len(self._develop_queue)} | Pendientes: {pending} | OK: {done} | Error: {errors}"
        )
        self._refresh_session_statistics()

    def _queue_progress_widget(self, item: dict[str, Any], status: str) -> QtWidgets.QProgressBar:
        bar = QtWidgets.QProgressBar()
        bar.setMinimumWidth(150)
        bar.setMaximumHeight(18)
        bar.setTextVisible(True)
        progress = self._queue_item_progress_value(item, status)
        bar.setRange(0, 100)
        bar.setValue(progress)
        bar.setFormat(self._queue_progress_text(status, progress))
        if status == "error":
            bar.setStyleSheet("QProgressBar::chunk { background-color: #b91c1c; } QProgressBar { text-align: center; }")
        elif status == "done":
            bar.setStyleSheet("QProgressBar::chunk { background-color: #047857; } QProgressBar { text-align: center; }")
        elif status in {"processing", "queued"}:
            bar.setStyleSheet("QProgressBar::chunk { background-color: #4a4a4a; } QProgressBar { text-align: center; }")
        return bar

    def _queue_item_progress_value(self, item: dict[str, Any], status: str) -> int:
        if status == "done":
            return 100
        return self._queue_normalized_progress(item.get("progress", 0))

    def _queue_normalized_progress(self, value: Any) -> int:
        try:
            parsed = int(value or 0)
        except (TypeError, ValueError):
            parsed = 0
        return int(max(0, min(100, parsed)))

    def _queue_progress_text(self, status: str, progress: int) -> str:
        if status == "error":
            return self.tr("Error")
        if status == "done":
            return "100%"
        if status == "processing":
            return f"{progress}%"
        if status == "queued":
            return self.tr("En cola")
        return f"{progress}%"

    def _queue_row_for_source(self, source: str) -> int | None:
        for row, item in enumerate(self._develop_queue):
            if str(item.get("source") or "") == str(source):
                return row
        return None

    def _apply_queue_render_progress(self, event: Any) -> None:
        if not isinstance(event, dict):
            return
        row = self._queue_row_for_source(str(event.get("source") or ""))
        if row is None:
            return
        item = self._develop_queue[row]
        status = str(event.get("status") or item.get("status") or "pending")
        item["status"] = status
        if "progress" in event:
            item["progress"] = self._queue_normalized_progress(event.get("progress"))
        message = str(event.get("message") or "")
        if message:
            item["message"] = message
        output_tiff = str(event.get("output_tiff") or "")
        if output_tiff:
            item["output_tiff"] = output_tiff
        if row < self.queue_table.rowCount():
            self.queue_table.setItem(row, 2, QtWidgets.QTableWidgetItem(status))
            self.queue_table.setCellWidget(row, 3, self._queue_progress_widget(item, status))
            self.queue_table.setItem(row, 4, QtWidgets.QTableWidgetItem(str(item.get("output_tiff") or "")))
            self.queue_table.setItem(row, 5, QtWidgets.QTableWidgetItem(str(item.get("message") or "")))

    def _queue_process(self) -> None:
        if hasattr(self, "_flush_render_adjustment_sidecar_persist"):
            self._flush_render_adjustment_sidecar_persist()
        if hasattr(self, "_flush_detail_adjustment_sidecar_persist"):
            self._flush_detail_adjustment_sidecar_persist()
        if not self._develop_queue:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), "No hay elementos en cola.")
            return

        valid_entries: list[tuple[dict[str, Any], Path]] = []
        for item in self._develop_queue:
            src = Path(str(item.get("source") or ""))
            if src.exists() and src.is_file() and src.suffix.lower() in BROWSABLE_EXTENSIONS:
                valid_entries.append((item, src))
            else:
                item["status"] = "error"
                item["progress"] = 100
                item["message"] = "Archivo no encontrado o extensión incompatible"
                item["output_tiff"] = ""

        if not valid_entries:
            self._refresh_queue_table()
            self._save_active_session(silent=True)
            QtWidgets.QMessageBox.information(self, self.tr("Info"), "No hay archivos válidos para procesar en la cola.")
            return

        valid_sources = {str(p) for _item, p in valid_entries}
        for item in self._develop_queue:
            source = str(item.get("source") or "")
            if source and source in valid_sources:
                item["status"] = "pending"
                item["progress"] = 0
                item["message"] = ""
                item["output_tiff"] = ""
        self._refresh_queue_table()

        self._ensure_session_output_controls()
        out_dir = Path(self.batch_out_dir.text().strip())
        apply_adjust = bool(self.batch_apply_adjustments.isChecked())
        embed_profile = bool(self.batch_embed_profile.isChecked())
        groups: dict[str, list[Path]] = {}
        settings_by_group: dict[str, dict[str, Any]] = {}
        try:
            for item, src in valid_entries:
                sidecar_settings = self._development_settings_from_raw_sidecar(src)
                if sidecar_settings is not None:
                    group_key = f"sidecar:{self._normalized_path_key(src)}"
                    groups.setdefault(group_key, []).append(src)
                    settings_by_group[group_key] = sidecar_settings
                    continue

                profile_id = str(item.get("development_profile_id") or "")
                if profile_id:
                    group_key = f"profile:{profile_id}"
                    groups.setdefault(group_key, []).append(src)
                    if group_key not in settings_by_group:
                        settings_by_group[group_key] = self._development_profile_settings(profile_id)
                    continue

                group_key = "current:"
                groups.setdefault(group_key, []).append(src)
                if group_key not in settings_by_group:
                    settings_by_group[group_key] = self._development_profile_settings("")
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, self.tr("Perfil de ajuste no válido"), str(exc))
            return
        try:
            proof_config = self._resolve_proof_config_for_gui()
            c2pa_config = self._resolve_c2pa_config_for_gui()
        except Exception as exc:
            self._show_signature_config_error(exc)
            return

        def task(progress_emit=None):
            progress_emit = progress_emit or (lambda _event: None)
            combined = {"input_files": len(valid_entries), "output_dir": str(out_dir), "outputs": [], "errors": [], "profiles": []}
            for _item, src in valid_entries:
                progress_emit({"source": str(src), "status": "queued", "progress": 0, "message": self.tr("En cola")})
            for group_key, group_files in groups.items():
                settings = settings_by_group[group_key]
                detail = self._detail_adjustment_kwargs_from_state(settings["detail_adjustments"])
                profile_path = settings.get("icc_profile_path")
                use_profile = bool(embed_profile and isinstance(profile_path, Path) and profile_path.exists())
                payload = self._process_batch_files(
                    files=group_files,
                    out_dir=out_dir,
                    recipe=settings["recipe"],
                    apply_adjust=apply_adjust,
                    use_profile=use_profile,
                    profile_path=profile_path if use_profile else None,
                    denoise_luma=detail["denoise_luma"],
                    denoise_color=detail["denoise_color"],
                    sharpen_amount=detail["sharpen_amount"],
                    sharpen_radius=detail["sharpen_radius"],
                    lateral_ca_red_scale=detail["lateral_ca_red_scale"],
                    lateral_ca_blue_scale=detail["lateral_ca_blue_scale"],
                    render_adjustments=self._render_adjustment_kwargs_from_state(settings["render_adjustments"]),
                    sidecar_detail_adjustments=settings["detail_adjustments"],
                    sidecar_render_adjustments=settings["render_adjustments"],
                    c2pa_config=c2pa_config,
                    proof_config=proof_config,
                    development_profile=self._profile_payload_from_development_settings(settings),
                    progress_callback=progress_emit,
                )
                combined["outputs"].extend(payload.get("outputs", []))
                combined["errors"].extend(payload.get("errors", []))
                combined["profiles"].append({"id": settings["id"], "name": settings["name"], "files": len(group_files)})
            combined["task"] = "Cola de revelado"
            return combined

        def on_success(payload) -> None:
            ok_by_source = {str(o["source"]): str(o["output"]) for o in payload.get("outputs", [])}
            err_by_source = {str(e["source"]): str(e["error"]) for e in payload.get("errors", [])}

            kept_queue: list[dict[str, str]] = []
            removed_count = 0
            for item in self._develop_queue:
                source = str(item.get("source") or "")
                if source in ok_by_source:
                    item["status"] = "done"
                    item["progress"] = 100
                    item["output_tiff"] = ok_by_source[source]
                    item["message"] = "Completado"
                    removed_count += 1
                    continue
                elif source in err_by_source:
                    item["status"] = "error"
                    item["progress"] = 100
                    item["output_tiff"] = ""
                    item["message"] = err_by_source[source]
                kept_queue.append(item)

            if removed_count:
                self._develop_queue = kept_queue
            self._refresh_queue_table()
            self._save_active_session(silent=True)
            self._set_status(
                f"Cola procesada: {len(payload.get('outputs', []))} OK retirados / "
                f"{len(payload.get('errors', []))} errores"
            )

        try:
            self._start_background_task(
                self.tr("Procesar cola de revelado"),
                task,
                on_success,
                on_progress=self._apply_queue_render_progress,
            )
        except TypeError as exc:
            if "on_progress" not in str(exc):
                raise
            self._start_background_task(self.tr("Procesar cola de revelado"), task, on_success)
