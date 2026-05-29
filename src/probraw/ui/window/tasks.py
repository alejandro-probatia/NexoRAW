from __future__ import annotations

import warnings

from ._imports import *  # noqa: F401,F403


_SHUTDOWN_THREAD_GRAVEYARD: list[Any] = []


def _bounded_shutdown_wait_ms(deadline: float, *, cap_ms: int, floor_ms: int = 1) -> int:
    remaining_ms = int((deadline - time.monotonic()) * 1000.0)
    return max(int(floor_ms), min(int(cap_ms), remaining_ms))


class TaskStatusMixin:
    def _shutdown_background_threads(self, *, timeout_ms: int = 8000) -> None:
        if bool(getattr(self, "_background_threads_shutdown", False)):
            return
        self._background_threads_shutdown = True
        self._stop_background_timers_for_shutdown()
        self._clear_pending_background_work_for_shutdown()

        threads = list(getattr(self, "_threads", []))
        if not threads:
            return

        try:
            self._set_status(self.tr("Cerrando tareas en segundo plano..."))
        except Exception:
            pass

        deadline = time.monotonic() + max(0.1, float(timeout_ms) / 1000.0)
        for thread in threads:
            if thread is None:
                continue
            try:
                for signal_name in ("succeeded", "failed"):
                    signal = getattr(thread, signal_name, None)
                    if signal is not None:
                        try:
                            with warnings.catch_warnings():
                                warnings.simplefilter("ignore", RuntimeWarning)
                                signal.disconnect()
                        except Exception:
                            pass
                if thread.isRunning():
                    remaining_ms = int(max(1.0, (deadline - time.monotonic()) * 1000.0))
                    if not thread.wait(remaining_ms):
                        try:
                            thread.requestInterruption()
                        except Exception:
                            pass
                        try:
                            thread.quit()
                        except Exception:
                            pass
                        remaining_ms = int(max(1.0, (deadline - time.monotonic()) * 1000.0))
                        if not thread.wait(min(250, remaining_ms)):
                            try:
                                thread.terminate()
                            except Exception:
                                pass
                            try:
                                thread.wait(_bounded_shutdown_wait_ms(deadline, cap_ms=1000, floor_ms=100))
                            except Exception:
                                pass
                if thread in self._threads:
                    self._threads.remove(thread)
                if not thread.isRunning():
                    thread.deleteLater()
                else:
                    _SHUTDOWN_THREAD_GRAVEYARD.append(thread)
            except RuntimeError:
                if thread in self._threads:
                    self._threads.remove(thread)
            except Exception:
                if thread in self._threads:
                    self._threads.remove(thread)

        self._threads.clear()
        app = QtWidgets.QApplication.instance()
        if app is not None:
            event_budget_ms = int(max(0.0, min(50.0, (deadline - time.monotonic()) * 1000.0)))
            if event_budget_ms > 0:
                try:
                    app.processEvents(QtCore.QEventLoop.ExcludeUserInputEvents, event_budget_ms)
                except TypeError:
                    app.processEvents(QtCore.QEventLoop.ExcludeUserInputEvents)

    def _stop_background_timers_for_shutdown(self) -> None:
        for name in (
            "_selection_load_timer",
            "_preview_load_progress_timer",
            "_preview_refresh_timer",
            "_preview_final_refresh_timer",
            "_interactive_preview_global_timer",
            "_thumbnail_timer",
            "_metadata_timer",
            "_mtf_refresh_timer",
            "_mtf_persist_timer",
            "_mtf_progress_timer",
            "_session_root_update_timer",
        ):
            timer = getattr(self, name, None)
            if timer is not None:
                try:
                    timer.stop()
                except Exception:
                    pass

    def _clear_pending_background_work_for_shutdown(self) -> None:
        self._pending_thumbnail_paths = []
        self._thumbnail_scan_index = 0
        self._metadata_pending_request = None
        self._preview_load_pending_request = None
        self._preview_prefetch_pending_request = None
        self._raw_embedded_preview_expected_key = None
        self._profile_preview_pending_request = None
        self._interactive_preview_pending_request = None
        self._mtf_base_roi_pending_request = None
        self._profile_preview_expected_key = None
        self._interactive_preview_expected_key = None
        self._interactive_preview_inflight_viewport_rect = None
        self._interactive_preview_inflight_include_analysis = False
        self._interactive_histogram_last_started_at = 0.0

    def _start_background_task(self, label: str, task, on_success, *, on_progress=None) -> None:
        self._set_status(self.tr("Ejecutando:") + f" {label}")
        task_row = self._monitor_task_start(label)
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.processEvents(QtCore.QEventLoop.ExcludeUserInputEvents)
        thread = TaskThread(task, progress_enabled=on_progress is not None)
        if on_progress is not None:
            thread.progress.connect(on_progress)
        self._threads.append(thread)

        def cleanup() -> None:
            if thread in self._threads:
                self._threads.remove(thread)
            thread.deleteLater()

        def ok(payload) -> None:
            try:
                on_success(payload)
                self._set_status(self.tr("Completado:") + f" {label}")
                self._monitor_task_finish(task_row, self.tr("Completado"), "OK")
            finally:
                cleanup()

        def fail(trace: str) -> None:
            cleanup()
            self._log_preview(trace[-1200:])
            self._set_status(self.tr("Error en:") + f" {label}")
            self._monitor_task_finish(task_row, self.tr("Error"), trace.strip().splitlines()[-1] if trace.strip() else self.tr("Error"))
            QtWidgets.QMessageBox.critical(self, self.tr("Error"), trace[-4000:])

        thread.succeeded.connect(ok)
        thread.failed.connect(fail)
        thread.start()

    def _log_preview(self, text: str) -> None:
        self.preview_log.appendPlainText(text)
        self.monitor_log.appendPlainText(text)

    def _monitor_task_start(self, label: str) -> int:
        self._task_counter += 1
        self._active_tasks += 1

        row = self.monitor_tasks.rowCount()
        self.monitor_tasks.insertRow(row)
        self.monitor_tasks.setItem(row, 0, QtWidgets.QTableWidgetItem(str(self._task_counter)))
        self.monitor_tasks.setItem(row, 1, QtWidgets.QTableWidgetItem(label))
        self.monitor_tasks.setItem(row, 2, QtWidgets.QTableWidgetItem("En curso"))
        self.monitor_tasks.setItem(row, 3, QtWidgets.QTableWidgetItem(""))
        self.monitor_tasks.scrollToBottom()

        self.monitor_status_label.setText(f"Ejecutando: {label}")
        self.monitor_progress.setRange(0, 0)
        self._set_global_operation_progress(
            "task",
            f"{self.tr('Ejecutando:')} {label}",
            time_text=self.tr("En curso"),
            phase_text=self.tr("Tarea en segundo plano"),
            minimum=0,
            maximum=0,
            value=0,
        )
        return row

    def _monitor_task_finish(self, row: int, status: str, detail: str) -> None:
        self._active_tasks = max(0, self._active_tasks - 1)
        self.monitor_tasks.setItem(row, 2, QtWidgets.QTableWidgetItem(status))
        self.monitor_tasks.setItem(row, 3, QtWidgets.QTableWidgetItem(detail))
        self.monitor_tasks.scrollToBottom()

        if self._active_tasks == 0:
            self.monitor_progress.setRange(0, 1)
            self.monitor_progress.setValue(1 if status == "Completado" else 0)
            self.monitor_status_label.setText(self.tr("Sin tareas en ejecucion"))
            self._set_global_operation_progress(
                "task",
                f"{status}: {detail}",
                time_text=self.tr("Finalizado"),
                phase_text=self.tr("Sin tareas en ejecución"),
                minimum=0,
                maximum=1,
                value=1 if status == "Completado" else 0,
            )
            QtCore.QTimer.singleShot(1800, self._reset_global_progress_if_idle)

    def _reset_global_progress_if_idle(self) -> None:
        self._reset_global_operation_progress(owner="task")

    def _set_global_operation_progress(
        self,
        owner: str,
        title: str,
        *,
        time_text: str = "",
        phase_text: str = "",
        minimum: int = 0,
        maximum: int = 1,
        value: int = 0,
    ) -> None:
        if not hasattr(self, "global_status_label"):
            return
        self._global_progress_owner = str(owner or "task")
        self.global_status_label.setText(str(title or self.tr("Procesando...")))
        if hasattr(self, "global_progress_time_label"):
            self.global_progress_time_label.setText(str(time_text or self.tr("Tiempo: --")))
        if hasattr(self, "global_progress_phase_label"):
            self.global_progress_phase_label.setText(str(phase_text or ""))
        self.global_progress.setRange(int(minimum), int(maximum))
        if int(minimum) != 0 or int(maximum) != 0:
            self.global_progress.setValue(int(value))

    def _reset_global_operation_progress(self, *, owner: str | None = None, force: bool = False) -> None:
        if not force and self._active_tasks != 0:
            return
        if not hasattr(self, "global_status_label"):
            return
        if owner is not None and getattr(self, "_global_progress_owner", None) != owner:
            return
        self._global_progress_owner = None
        self.global_status_label.setText(self.tr("Listo"))
        if hasattr(self, "global_progress_time_label"):
            self.global_progress_time_label.setText(self.tr("Tiempo: --"))
        if hasattr(self, "global_progress_phase_label"):
            self.global_progress_phase_label.setText(self.tr("Sin operación en curso"))
        self.global_progress.setRange(0, 1)
        self.global_progress.setValue(0)

    def _setup_interactive_preview_status_widgets(self) -> None:
        self._interactive_preview_spinner = QtWidgets.QProgressBar()
        self._interactive_preview_spinner.setTextVisible(False)
        self._interactive_preview_spinner.setRange(0, 1)
        self._interactive_preview_spinner.setValue(0)
        self._interactive_preview_spinner.setFixedWidth(84)
        self._interactive_preview_spinner.setMaximumHeight(9)
        self._interactive_preview_time_label = QtWidgets.QLabel(self.tr("Ultimo ajuste: -- ms"))
        self._interactive_preview_time_label.setStyleSheet("color: #d4d4d4;")
        self._interactive_preview_global_timer = QtCore.QTimer(self)
        self._interactive_preview_global_timer.setInterval(250)
        self._interactive_preview_global_timer.timeout.connect(self._update_interactive_preview_global_progress)
        status = self.statusBar()
        status.addPermanentWidget(self._interactive_preview_spinner)
        status.addPermanentWidget(self._interactive_preview_time_label)

    def _set_interactive_preview_busy(self, busy: bool) -> None:
        if bool(busy):
            if getattr(self, "_interactive_preview_busy_started_at", None) is None:
                self._interactive_preview_busy_started_at = time.perf_counter()
                self._interactive_preview_global_visible = False
            timer = getattr(self, "_interactive_preview_global_timer", None)
            if timer is not None and not timer.isActive():
                timer.start()
        else:
            timer = getattr(self, "_interactive_preview_global_timer", None)
            if timer is not None:
                timer.stop()
            started = getattr(self, "_interactive_preview_busy_started_at", None)
            elapsed = (time.perf_counter() - started) if started is not None else None
            was_global_visible = bool(getattr(self, "_interactive_preview_global_visible", False))
            self._interactive_preview_busy_started_at = None
            self._interactive_preview_global_visible = False
            owner = getattr(self, "_global_progress_owner", None)
            if was_global_visible and owner in (None, "preview"):
                self._set_global_operation_progress(
                    "preview",
                    self.tr("Ajuste completado"),
                    time_text=(self.tr("Total:") + f" {elapsed:.1f} s") if elapsed is not None else self.tr("Finalizado"),
                    phase_text=self.tr("Vista previa actualizada"),
                    minimum=0,
                    maximum=1,
                    value=1,
                )
                QtCore.QTimer.singleShot(1200, lambda: self._reset_global_operation_progress(owner="preview"))
        spinner = getattr(self, "_interactive_preview_spinner", None)
        if spinner is not None:
            if busy:
                spinner.setRange(0, 0)
            else:
                spinner.setRange(0, 1)
                spinner.setValue(0)
        label = getattr(self, "_interactive_preview_time_label", None)
        if label is not None and bool(busy):
            label.setText(self.tr("Ajustando..."))
        elif label is not None:
            self._update_interactive_preview_time_label()

    def _update_interactive_preview_global_progress(self) -> None:
        started = getattr(self, "_interactive_preview_busy_started_at", None)
        if started is None:
            return
        elapsed = max(0.0, time.perf_counter() - float(started))
        if elapsed < 1.0 and not bool(getattr(self, "_interactive_preview_global_visible", False)):
            return
        owner = getattr(self, "_global_progress_owner", None)
        if owner not in (None, "preview"):
            return
        self._interactive_preview_global_visible = True
        self._set_global_operation_progress(
            "preview",
            self.tr("Ajustando vista previa..."),
            time_text=self.tr("Tiempo:") + f" {elapsed:.1f} s",
            phase_text=self.tr("Aplicando ajustes de color y contraste"),
            minimum=0,
            maximum=0,
            value=0,
        )

    def _update_interactive_preview_time_label(self) -> None:
        label = getattr(self, "_interactive_preview_time_label", None)
        if label is None:
            return
        if self._interactive_preview_last_ms is None:
            label.setText(self.tr("Ultimo ajuste: -- ms"))
            return
        label.setText(self.tr("Ultimo ajuste:") + f" {int(round(self._interactive_preview_last_ms))} ms")

    def _set_status(self, text: str) -> None:
        self.statusBar().showMessage(text, 8000)
