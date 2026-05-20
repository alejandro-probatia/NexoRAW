from __future__ import annotations

from ._imports import *  # noqa: F401,F403


PROFILE_OUTPUT_FULL_JSON_CHAR_LIMIT = 60_000
REFERENCE_TABLE_COLUMNS = {
    "swatch": 0,
    "patch_id": 1,
    "patch_name": 2,
    "l": 3,
    "a": 4,
    "b": 5,
}


class ProfileWorkflowMixin:
    def _lab_reference_to_srgb_u8(self, lab: list[float] | tuple[float, float, float]) -> tuple[int, int, int]:
        lab_arr = np.asarray(lab, dtype=np.float64).reshape(-1)
        if lab_arr.size < 3 or not np.all(np.isfinite(lab_arr[:3])):
            return (0, 0, 0)
        l_val, a_val, b_val = lab_arr[:3]
        fy = (float(l_val) + 16.0) / 116.0
        fx = fy + float(a_val) / 500.0
        fz = fy - float(b_val) / 200.0

        delta = 6.0 / 29.0

        def inv_f(t: float) -> float:
            return t ** 3 if t > delta else 3.0 * (delta ** 2) * (t - 4.0 / 29.0)

        xyz_d50 = np.asarray(
            [
                0.96422 * inv_f(fx),
                1.0 * inv_f(fy),
                0.82521 * inv_f(fz),
            ],
            dtype=np.float64,
        )
        bradford_d50_to_d65 = np.asarray(
            [
                [0.9554734, -0.0230985, 0.0632593],
                [-0.0283697, 1.0099956, 0.0210414],
                [0.0123140, -0.0205077, 1.3303659],
            ],
            dtype=np.float64,
        )
        xyz_d65 = bradford_d50_to_d65 @ xyz_d50
        xyz_to_srgb = np.asarray(
            [
                [3.2404542, -1.5371385, -0.4985314],
                [-0.9692660, 1.8760108, 0.0415560],
                [0.0556434, -0.2040259, 1.0572252],
            ],
            dtype=np.float64,
        )
        rgb_linear = np.clip(xyz_to_srgb @ xyz_d65, 0.0, 1.0)
        rgb = np.where(
            rgb_linear <= 0.0031308,
            12.92 * rgb_linear,
            1.055 * np.power(rgb_linear, 1.0 / 2.4) - 0.055,
        )
        return tuple(int(round(v)) for v in np.clip(rgb * 255.0, 0.0, 255.0))

    def _reference_session_dir(self) -> Path:
        root = self._active_session_root
        if root is None and hasattr(self, "session_root_path"):
            text = self.session_root_path.text().strip()
            root = Path(text).expanduser() if text else None
        if root is None:
            root = Path.cwd()
        return self._session_paths_from_root(Path(root).expanduser())["references"]

    def _reference_payload_from_path(self, path: Path) -> dict[str, Any]:
        candidate = Path(path).expanduser()
        if candidate.exists():
            payload = json.loads(candidate.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
            raise RuntimeError("El JSON de referencia debe ser un objeto.")
        catalog = ReferenceCatalog.from_path(candidate, strict=False)
        return {
            "chart_name": catalog.chart_name,
            "chart_version": catalog.chart_version,
            "reference_source": catalog.reference_source or "",
            "illuminant": catalog.illuminant,
            "observer": catalog.observer,
            "patch_order": "row-major, top-left to bottom-right",
            "patches": list(catalog.patches),
        }

    def _reference_catalog_label_for_path(self, path_text: str) -> str:
        try:
            catalog = ReferenceCatalog.from_path(Path(path_text), strict=False)
            return reference_catalog_label(catalog)
        except Exception:
            return Path(path_text).name or str(path_text)

    def _reference_path_is_session_reference(self, path: Path) -> bool:
        try:
            path.expanduser().resolve(strict=False).relative_to(
                self._reference_session_dir().expanduser().resolve(strict=False)
            )
            return True
        except Exception:
            return False

    def _reference_catalog_entries(self) -> list[tuple[str, str]]:
        entries: list[tuple[str, str]] = []
        for item in bundled_reference_catalogs():
            entries.append((self.tr("Incluida:") + f" {item['label']}", str(item["path"])))

        references_dir = self._reference_session_dir()
        try:
            files = sorted(
                p for p in references_dir.iterdir()
                if p.is_file() and p.suffix.lower() == ".json"
            )
        except Exception:
            files = []
        for path in files:
            entries.append((self.tr("Sesión:") + f" {self._reference_catalog_label_for_path(str(path))}", str(path)))
        return entries

    def _refresh_reference_catalog_combo(self) -> None:
        if not hasattr(self, "reference_catalog_combo"):
            return
        current = self.path_reference.text().strip() if hasattr(self, "path_reference") else ""
        entries = self._reference_catalog_entries()
        self.reference_catalog_combo.blockSignals(True)
        self.reference_catalog_combo.clear()
        for label, path in entries:
            self.reference_catalog_combo.addItem(label, path)

        index = self.reference_catalog_combo.findData(current)
        if index < 0 and current:
            index = self.reference_catalog_combo.findData(Path(current).name)
        if index < 0 and current:
            self.reference_catalog_combo.addItem(self.tr("Personalizada externa:") + f" {Path(current).name}", current)
            index = self.reference_catalog_combo.count() - 1
        self.reference_catalog_combo.setCurrentIndex(index if index >= 0 else 0)
        if not current and self.reference_catalog_combo.count():
            self.path_reference.setText(str(self.reference_catalog_combo.currentData() or ""))
        self.reference_catalog_combo.blockSignals(False)

    def _on_reference_catalog_selected(self, _index: int = 0) -> None:
        if not hasattr(self, "reference_catalog_combo"):
            return
        path = str(self.reference_catalog_combo.currentData() or "").strip()
        if not path:
            return
        self.path_reference.setText(path)
        self._update_reference_status()
        self._save_active_session(silent=True)

    def _on_reference_path_edited(self) -> None:
        self._refresh_reference_catalog_combo()
        self._update_reference_status()
        self._save_active_session(silent=True)

    def _update_reference_status(self) -> bool:
        if not hasattr(self, "reference_status_label"):
            return False
        text = self.path_reference.text().strip() if hasattr(self, "path_reference") else ""
        if not text:
            self.reference_status_label.setText(self.tr("Referencia de carta no configurada"))
            self.reference_status_label.setStyleSheet("font-size: 12px; color: #fca5a5;")
            return False
        try:
            catalog = ReferenceCatalog.from_path(Path(text), strict=True)
        except Exception as exc:
            self.reference_status_label.setText(self.tr("Referencia no válida:") + f" {exc}")
            self.reference_status_label.setStyleSheet("font-size: 12px; color: #fca5a5;")
            return False
        self.reference_status_label.setText(
            f"{reference_catalog_label(catalog)} | "
            f"{len(catalog.patches)} parches | {catalog.reference_source or self.tr('sin fuente')}"
        )
        self.reference_status_label.setStyleSheet("font-size: 12px; color: #d1fae5;")
        return True

    def _validate_current_reference_catalog(self) -> bool:
        valid = self._update_reference_status()
        if valid:
            QtWidgets.QMessageBox.information(
                self,
                self.tr("Referencia de carta"),
                self.tr("Referencia validada correctamente."),
            )
        else:
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("Referencia de carta"),
                self.reference_status_label.text(),
            )
        return valid

    def _save_reference_payload_to_session(
        self,
        payload: dict[str, Any],
        *,
        desired_name: str | None = None,
        target_path: Path | None = None,
    ) -> Path:
        catalog = ReferenceCatalog(payload, strict=True)
        references_dir = self._reference_session_dir()
        references_dir.mkdir(parents=True, exist_ok=True)
        if target_path is not None and self._reference_path_is_session_reference(target_path):
            out = target_path
        else:
            base_name = desired_name or reference_catalog_label(catalog) or "referencia-carta"
            slug = self._slug_for_development_profile(base_name)
            out = versioned_output_path(references_dir / f"{slug}.json")
        write_json(out, payload)
        self.path_reference.setText(str(out))
        self._refresh_reference_catalog_combo()
        self._update_reference_status()
        self._save_active_session(silent=True)
        return out

    def _import_reference_catalog(self) -> None:
        start = self.path_reference.text().strip() or str(self._current_dir)
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            self.tr("Importar referencia de carta"),
            start,
            "Referencias JSON (*.json);;Todos (*)",
        )
        if not path:
            return
        try:
            payload = self._reference_payload_from_path(Path(path))
            saved = self._save_reference_payload_to_session(payload, desired_name=Path(path).stem)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, self.tr("Referencia no válida"), str(exc))
            return
        self._set_status(self.tr("Referencia de carta importada:") + f" {saved}")

    def _new_custom_reference_catalog(self) -> None:
        payload: dict[str, Any]
        try:
            payload = self._reference_payload_from_path(Path(self.path_reference.text().strip()))
            payload = dict(payload)
            payload["chart_version"] = str(payload.get("chart_version") or "personalizada") + " personalizada"
            payload["reference_source"] = "Medición personalizada introducida en ProbRAW"
        except Exception:
            payload = reference_catalog_template(
                chart_name="ColorChecker personalizada"
                if self.profile_chart_type.currentText().strip() == "colorchecker24"
                else "Carta personalizada",
                patch_count=24,
            )
        self._open_reference_editor(payload, target_path=None)

    def _edit_current_reference_catalog(self) -> None:
        text = self.path_reference.text().strip()
        try:
            payload = self._reference_payload_from_path(Path(text)) if text else reference_catalog_template()
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, self.tr("Referencia no válida"), str(exc))
            return
        target = Path(text).expanduser() if text else None
        if target is not None and not self._reference_path_is_session_reference(target):
            target = None
        self._open_reference_editor(payload, target_path=target)

    def _open_reference_editor(self, payload: dict[str, Any], *, target_path: Path | None) -> None:
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(self.tr("Editar referencia de carta"))
        dialog.resize(940, 700)
        layout = QtWidgets.QVBoxLayout(dialog)

        form = QtWidgets.QGridLayout()
        chart_name = QtWidgets.QLineEdit(str(payload.get("chart_name") or "Carta personalizada"))
        chart_version = QtWidgets.QLineEdit(str(payload.get("chart_version") or "personalizada"))
        reference_source = QtWidgets.QLineEdit(
            str(payload.get("reference_source") or payload.get("source") or "Medición personalizada introducida en ProbRAW")
        )
        illuminant = QtWidgets.QLineEdit(str(payload.get("illuminant") or "D50"))
        observer = QtWidgets.QLineEdit(str(payload.get("observer") or "2"))
        form.addWidget(QtWidgets.QLabel(self.tr("Carta")), 0, 0)
        form.addWidget(chart_name, 0, 1)
        form.addWidget(QtWidgets.QLabel(self.tr("Versión")), 0, 2)
        form.addWidget(chart_version, 0, 3)
        form.addWidget(QtWidgets.QLabel(self.tr("Fuente")), 1, 0)
        form.addWidget(reference_source, 1, 1, 1, 3)
        form.addWidget(QtWidgets.QLabel(self.tr("Iluminante")), 2, 0)
        form.addWidget(illuminant, 2, 1)
        form.addWidget(QtWidgets.QLabel(self.tr("Observador")), 2, 2)
        form.addWidget(observer, 2, 3)
        form.setColumnStretch(1, 1)
        form.setColumnStretch(3, 1)
        layout.addLayout(form)

        table = QtWidgets.QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels([
            self.tr("Color"),
            self.tr("Parche"),
            self.tr("Nombre"),
            "L*",
            "a*",
            "b*",
        ])
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        header = table.horizontalHeader()
        header.setSectionResizeMode(REFERENCE_TABLE_COLUMNS["swatch"], QtWidgets.QHeaderView.Fixed)
        header.setSectionResizeMode(REFERENCE_TABLE_COLUMNS["patch_id"], QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(REFERENCE_TABLE_COLUMNS["patch_name"], QtWidgets.QHeaderView.Stretch)
        for column in ("l", "a", "b"):
            header.setSectionResizeMode(REFERENCE_TABLE_COLUMNS[column], QtWidgets.QHeaderView.ResizeToContents)
        table.setColumnWidth(REFERENCE_TABLE_COLUMNS["swatch"], 58)
        self._populate_reference_table(table, payload)
        table.itemChanged.connect(lambda item: self._on_reference_table_item_changed(table, item))
        layout.addWidget(table, 1)

        table_buttons = QtWidgets.QHBoxLayout()
        table_buttons.addWidget(self._button(self.tr("Añadir parche"), lambda: self._add_reference_table_row(table)))
        table_buttons.addWidget(self._button(self.tr("Eliminar selección"), lambda: self._remove_reference_table_rows(table)))
        table_buttons.addStretch(1)
        layout.addLayout(table_buttons)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        layout.addWidget(buttons)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        if dialog.exec() != QtWidgets.QDialog.Accepted:
            return
        try:
            edited = self._reference_payload_from_table(
                table,
                chart_name=chart_name.text(),
                chart_version=chart_version.text(),
                reference_source=reference_source.text(),
                illuminant=illuminant.text(),
                observer=observer.text(),
                patch_order=str(payload.get("patch_order") or "row-major, top-left to bottom-right"),
            )
            saved = self._save_reference_payload_to_session(edited, target_path=target_path)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, self.tr("Referencia no válida"), str(exc))
            return
        self._set_status(self.tr("Referencia de carta guardada:") + f" {saved}")

    def _populate_reference_table(self, table: QtWidgets.QTableWidget, payload: dict[str, Any]) -> None:
        patches = payload.get("patches") if isinstance(payload.get("patches"), list) else []
        table.blockSignals(True)
        if table.columnCount() < 6:
            table.setColumnCount(6)
        table.setRowCount(len(patches))
        for row, patch in enumerate(patches):
            patch = patch if isinstance(patch, dict) else {}
            lab = patch.get("reference_lab") if isinstance(patch.get("reference_lab"), list) else [50.0, 0.0, 0.0]
            values = [
                "",
                str(patch.get("patch_id") or f"P{row + 1:02d}"),
                str(patch.get("patch_name") or ""),
                f"{float(lab[0]):.4f}" if len(lab) > 0 else "50.0000",
                f"{float(lab[1]):.4f}" if len(lab) > 1 else "0.0000",
                f"{float(lab[2]):.4f}" if len(lab) > 2 else "0.0000",
            ]
            for column, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(value)
                if column == REFERENCE_TABLE_COLUMNS["swatch"]:
                    item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
                    item.setText("")
                elif column in {REFERENCE_TABLE_COLUMNS["l"], REFERENCE_TABLE_COLUMNS["a"], REFERENCE_TABLE_COLUMNS["b"]}:
                    item.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
                table.setItem(row, column, item)
            self._update_reference_table_row_swatch(table, row)
        table.blockSignals(False)

    def _add_reference_table_row(self, table: QtWidgets.QTableWidget) -> None:
        row = table.rowCount()
        table.insertRow(row)
        values = ["", f"P{row + 1:02d}", "", "50.0000", "0.0000", "0.0000"]
        for column, value in enumerate(values):
            item = QtWidgets.QTableWidgetItem(value)
            if column == REFERENCE_TABLE_COLUMNS["swatch"]:
                item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
                item.setText("")
            elif column in {REFERENCE_TABLE_COLUMNS["l"], REFERENCE_TABLE_COLUMNS["a"], REFERENCE_TABLE_COLUMNS["b"]}:
                item.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            table.setItem(row, column, item)
        self._update_reference_table_row_swatch(table, row)

    def _remove_reference_table_rows(self, table: QtWidgets.QTableWidget) -> None:
        rows = sorted({index.row() for index in table.selectionModel().selectedRows()}, reverse=True)
        for row in rows:
            table.removeRow(row)
        for row in range(table.rowCount()):
            self._update_reference_table_row_swatch(table, row)

    def _on_reference_table_item_changed(self, table: QtWidgets.QTableWidget, item: QtWidgets.QTableWidgetItem) -> None:
        if item.column() in {
            REFERENCE_TABLE_COLUMNS["l"],
            REFERENCE_TABLE_COLUMNS["a"],
            REFERENCE_TABLE_COLUMNS["b"],
        }:
            self._update_reference_table_row_swatch(table, item.row())

    def _reference_table_lab(self, table: QtWidgets.QTableWidget, row: int) -> list[float]:
        values: list[float] = []
        for column in (REFERENCE_TABLE_COLUMNS["l"], REFERENCE_TABLE_COLUMNS["a"], REFERENCE_TABLE_COLUMNS["b"]):
            item = table.item(row, column)
            text = item.text().strip().replace(",", ".") if item is not None else ""
            values.append(float(text))
        return values

    def _update_reference_table_row_swatch(self, table: QtWidgets.QTableWidget, row: int) -> None:
        swatch = table.item(row, REFERENCE_TABLE_COLUMNS["swatch"])
        if swatch is None:
            return
        try:
            rgb = self._lab_reference_to_srgb_u8(self._reference_table_lab(table, row))
        except Exception:
            rgb = (0, 0, 0)
        color = QtGui.QColor(*rgb)
        swatch.setBackground(color)
        swatch.setToolTip(f"sRGB preview: #{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}")

    def _reference_payload_from_table(
        self,
        table: QtWidgets.QTableWidget,
        *,
        chart_name: str,
        chart_version: str,
        reference_source: str,
        illuminant: str,
        observer: str,
        patch_order: str,
    ) -> dict[str, Any]:
        patches: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in range(table.rowCount()):
            patch_item = table.item(row, REFERENCE_TABLE_COLUMNS["patch_id"])
            patch_id = patch_item.text().strip() if patch_item is not None else ""
            if not patch_id:
                raise RuntimeError(f"Fila {row + 1}: falta patch_id")
            if patch_id in seen:
                raise RuntimeError(f"patch_id duplicado: {patch_id}")
            seen.add(patch_id)
            name_item = table.item(row, REFERENCE_TABLE_COLUMNS["patch_name"])
            lab = self._reference_table_lab(table, row)
            patches.append(
                {
                    "patch_id": patch_id,
                    "patch_name": name_item.text().strip() if name_item is not None else "",
                    "reference_lab": [round(float(v), 4) for v in lab],
                }
            )
        return {
            "chart_name": chart_name.strip() or "Carta personalizada",
            "chart_version": chart_version.strip() or "personalizada",
            "reference_source": reference_source.strip() or "Medición personalizada introducida en ProbRAW",
            "illuminant": illuminant.strip() or "D50",
            "observer": observer.strip() or "2",
            "patch_order": patch_order.strip() or "row-major, top-left to bottom-right",
            "patches": patches,
        }

    def _use_current_dir_as_profile_charts(self) -> None:
        accepted = self._set_profile_reference_dir(self._current_dir)
        self._selected_chart_files = []
        self._sync_profile_chart_selection_label()
        self._refresh_color_reference_thumbnail_markers()
        if accepted:
            self._set_status(self.tr("Directorio de referencias colorimétricas:") + f" {self._current_dir}")
        self._save_active_session(silent=True)

    def _use_selected_files_as_profile_charts(self) -> None:
        candidates = [
            p for p in self._collect_selected_file_paths()
            if p.suffix.lower() in PROFILE_CHART_EXTENSIONS
        ]
        files, rejected = self._filter_profile_reference_files(candidates)
        if not files:
            if rejected:
                reason = rejected[0][1]
                QtWidgets.QMessageBox.information(
                    self,
                    self.tr("Referencias no válidas"),
                    self.tr("Las referencias colorimétricas deben ser RAW/DNG o TIFFs originales de carta, no")
                    + f" {reason}. " + self.tr("Selecciona las capturas en 01_ORG."),
                )
                fallback = self._preferred_profile_reference_dir()
                if fallback is not None:
                    self.profile_charts_dir.setText(str(fallback))
                self._selected_chart_files = []
                self._sync_profile_chart_selection_label()
                self._refresh_color_reference_thumbnail_markers()
                self._save_active_session(silent=True)
                return
            QtWidgets.QMessageBox.information(
                self,
                self.tr("Info"),
                self.tr("Selecciona una o más capturas RAW/DNG/TIFF como referencias colorimétricas."),
            )
            return
        self._selected_chart_files = sorted(set(files), key=lambda p: str(p))
        parents = {p.parent for p in self._selected_chart_files}
        if len(parents) == 1:
            self.profile_charts_dir.setText(str(next(iter(parents))))
        self._sync_profile_chart_selection_label()
        self._refresh_color_reference_thumbnail_markers()
        suffix = ("; " + self.tr("ignoradas") + f" {len(rejected)} " + self.tr("no válidas")) if rejected else ""
        self._set_status(self.tr("Referencias colorimétricas seleccionadas:") + f" {len(self._selected_chart_files)}{suffix}")
        self._save_active_session(silent=True)

    def _sync_profile_chart_selection_label(self) -> None:
        if not hasattr(self, "profile_chart_selection_label"):
            return
        if not self._selected_chart_files:
            self.profile_chart_selection_label.setText(self.tr("Referencias colorimétricas: todas las compatibles de la carpeta indicada"))
            self._refresh_color_reference_thumbnail_markers()
            return
        preview = ", ".join(p.name for p in self._selected_chart_files[:4])
        if len(self._selected_chart_files) > 4:
            preview += f" (+{len(self._selected_chart_files) - 4} más)"
        self.profile_chart_selection_label.setText(
            self.tr("Referencias colorimétricas seleccionadas:") + f" {len(self._selected_chart_files)} - {preview}"
        )
        self._refresh_color_reference_thumbnail_markers()

    def _profile_chart_files_or_none(self) -> list[Path] | None:
        files, rejected = self._filter_profile_reference_files(
            [p for p in self._selected_chart_files if p.suffix.lower() in PROFILE_CHART_EXTENSIONS]
        )
        if rejected:
            self._selected_chart_files = files
            self._sync_profile_chart_selection_label()
        return files if files else None

    def _infer_profile_chart_files(self) -> list[Path] | None:
        files = self._profile_chart_files_or_none()
        if files:
            return files

        selected = [
            p for p in self._collect_selected_file_paths()
            if p.suffix.lower() in PROFILE_CHART_EXTENSIONS
        ]
        selected, rejected = self._filter_profile_reference_files(selected)
        if selected:
            self._selected_chart_files = sorted(set(selected), key=lambda p: str(p))
            self._sync_profile_chart_selection_label()
            parents = {p.parent for p in self._selected_chart_files}
            if len(parents) == 1:
                self.profile_charts_dir.setText(str(next(iter(parents))))
            self._refresh_color_reference_thumbnail_markers()
            self._set_status(self.tr("Referencias colorimétricas tomadas de la selección:") + f" {len(self._selected_chart_files)}")
            return list(self._selected_chart_files)

        if (
            self._selected_file is not None
            and self._selected_file.suffix.lower() in PROFILE_CHART_EXTENSIONS
            and self._profile_reference_rejection_reason(self._selected_file) is None
        ):
            self._selected_chart_files = [self._selected_file]
            self.profile_charts_dir.setText(str(self._selected_file.parent))
            self._sync_profile_chart_selection_label()
            self._refresh_color_reference_thumbnail_markers()
            self._set_status(self.tr("Referencia colorimétrica tomada del archivo cargado:") + f" {self._selected_file.name}")
            return list(self._selected_chart_files)

        if rejected:
            fallback = self._preferred_profile_reference_dir()
            if fallback is not None:
                self.profile_charts_dir.setText(str(fallback))
            self._set_status(self.tr("Se ignoraron referencias colorimétricas no válidas en carpetas operativas."))

        return None

    def _manual_detections_for_profile(self, chart_files: list[Path] | None) -> dict[Path, Any] | None:
        if not self._manual_chart_detections:
            return None
        if chart_files:
            selected_keys = {str(p.expanduser().resolve()) for p in chart_files}
            matches = {
                Path(path): detection
                for path, detection in self._manual_chart_detections.items()
                if path in selected_keys
            }
        else:
            matches = {Path(path): detection for path, detection in self._manual_chart_detections.items()}
        return matches or None

    def _pending_manual_detection_request(self, chart_files: list[Path] | None) -> dict[str, Any] | None:
        if self._selected_file is None or self._original_linear is None or len(self._manual_chart_points) != 4:
            return None

        source = self._selected_file.expanduser().resolve()
        if not self._manual_chart_points_match_selected_file():
            return None

        if str(source) in self._manual_chart_detections:
            return None

        preview_h, preview_w = self._manual_chart_point_space_shape()
        return {
            "source": source,
            "points_preview": list(self._manual_chart_points),
            "preview_shape": (int(preview_h), int(preview_w)),
        }

    def _profile_chart_files_with_pending_manual_detection(
        self,
        chart_files: list[Path] | None,
        pending_manual_detection: dict[str, Any] | None,
    ) -> list[Path] | None:
        if pending_manual_detection is None:
            return chart_files
        source = Path(str(pending_manual_detection["source"])).expanduser().resolve()
        if source.suffix.lower() not in PROFILE_CHART_EXTENSIONS:
            return chart_files
        files = list(chart_files or [])
        source_key = self._normalized_path_key(source)
        kept = [p for p in files if self._normalized_path_key(p) != source_key]
        return [source, *kept]

    def _manual_chart_point_space_shape(self) -> tuple[int, int]:
        panels = []
        if self._compare_view_active() and hasattr(self, "image_result_compare"):
            panels.append(self.image_result_compare)
        if hasattr(self, "image_result_single"):
            panels.append(self.image_result_single)
        if hasattr(self, "image_result_compare"):
            panels.append(self.image_result_compare)
        for panel in panels:
            size = panel.image_size()
            if size is None:
                continue
            width, height = size
            if width > 0 and height > 0:
                return int(height), int(width)
        if self._preview_srgb is not None:
            return int(self._preview_srgb.shape[0]), int(self._preview_srgb.shape[1])
        if self._adjusted_linear is not None:
            return int(self._adjusted_linear.shape[0]), int(self._adjusted_linear.shape[1])
        return int(self._original_linear.shape[0]), int(self._original_linear.shape[1])

    def _build_pending_manual_detection(
        self,
        request: dict[str, Any],
        *,
        recipe: Recipe,
        chart_type: str,
        workdir: Path,
    ) -> tuple[Path, Any]:
        source = Path(str(request["source"])).expanduser().resolve()
        points_preview = [(float(x), float(y)) for x, y in request["points_preview"]]
        preview_h, preview_w = request["preview_shape"]

        manual_dir = workdir / "manual_detections"
        manual_dir.mkdir(parents=True, exist_ok=True)
        if source.suffix.lower() in RAW_EXTENSIONS:
            target_image = manual_dir / f"{source.stem}.manual_for_profile.tiff"
            full_image = develop_image_array(source, recipe)
            write_tiff16(target_image, full_image)
        else:
            target_image = source
            full_image = read_image(target_image)

        full_h, full_w = full_image.shape[:2]
        sx = full_w / max(1, int(preview_w))
        sy = full_h / max(1, int(preview_h))
        corners = [(x * sx, y * sy) for x, y in points_preview]
        detection = detect_chart_from_corners_array(full_image, corners=corners, chart_type=chart_type)

        detection_path = manual_dir / f"{source.stem}.manual_for_profile.json"
        overlay_path = manual_dir / f"{source.stem}.manual_for_profile.overlay.png"
        write_json(detection_path, detection)
        draw_detection_overlay_array(full_image, detection, overlay_path)
        return source, detection

    def _directory_has_chart_captures(self, folder: Path) -> bool:
        try:
            return folder.exists() and folder.is_dir() and any(
                p.is_file() and p.suffix.lower() in PROFILE_CHART_EXTENSIONS
                for p in folder.iterdir()
            )
        except Exception:
            return False

    def _raw_files_for_chart_profile_assignment(
        self,
        charts: Path,
        chart_capture_files: list[Path] | None,
    ) -> list[Path]:
        candidates = list(chart_capture_files or [])
        if not candidates:
            try:
                candidates = [
                    p for p in sorted(charts.iterdir())
                    if p.is_file() and p.suffix.lower() in PROFILE_CHART_EXTENSIONS
                ]
            except Exception:
                candidates = []
        return [p for p in candidates if p.suffix.lower() in RAW_EXTENSIONS and p.exists()]

    def _use_current_dir_as_batch_input(self) -> None:
        self.batch_input_dir.setText(str(self._current_dir))
        self._set_status(self.tr("Directorio lote:") + f" {self._current_dir}")
        self._save_active_session(silent=True)

    def _on_generate_profile(self) -> None:
        self._ensure_session_output_controls()
        charts = Path(self.profile_charts_dir.text().strip())
        chart_capture_files = self._infer_profile_chart_files()
        pending_manual_detection = self._pending_manual_detection_request(chart_capture_files)
        chart_capture_files = self._profile_chart_files_with_pending_manual_detection(
            chart_capture_files,
            pending_manual_detection,
        )
        if pending_manual_detection is not None and chart_capture_files:
            source = Path(str(pending_manual_detection["source"])).expanduser().resolve()
            self._selected_chart_files = list(chart_capture_files)
            self.profile_charts_dir.setText(str(source.parent))
            charts = source.parent
            self._sync_profile_chart_selection_label()
            self._refresh_color_reference_thumbnail_markers()
            self._set_status(self.tr("Referencia colorimetrica tomada del marcado manual:") + f" {source.name}")
        if chart_capture_files is None:
            reason = self._profile_reference_rejection_reason(charts)
            if reason is not None:
                fallback = self._preferred_profile_reference_dir()
                if fallback is not None:
                    charts = fallback
                    self.profile_charts_dir.setText(str(charts))
                    self._set_status(
                        f"No se usan {reason} como referencias colorimétricas; se usa {charts}"
                    )
                else:
                    QtWidgets.QMessageBox.information(
                        self,
                        self.tr("Referencias no válidas"),
                        self.tr("La generación de perfil no puede usar carpetas operativas de la sesión")
                        + f" ({reason}). " + self.tr("Selecciona capturas RAW/DNG originales en 01_ORG."),
                    )
                    return
        if chart_capture_files is None and not self._directory_has_chart_captures(charts):
            if (
                self._profile_reference_rejection_reason(self._current_dir) is None
                and self._directory_has_chart_captures(self._current_dir)
            ):
                charts = self._current_dir
                self.profile_charts_dir.setText(str(charts))
            else:
                QtWidgets.QMessageBox.information(
                    self,
                    self.tr("Sin capturas de carta"),
                    self.tr("Selecciona una o mas miniaturas con carta, carga una carta en el visor o abre una carpeta con capturas RAW/DNG/TIFF."),
                )
                return
        manual_detections = self._manual_detections_for_profile(chart_capture_files)
        reference_path = Path(self.path_reference.text().strip())
        requested_profile_out = Path(self.profile_out_path_edit.text().strip())
        ext = self.combo_profile_format.currentText().strip().lower() or ".icc"
        if requested_profile_out.suffix.lower() != ext:
            requested_profile_out = requested_profile_out.with_suffix(ext)
        artifacts = self._profile_artifact_paths_for_generation(
            requested_profile_out=requested_profile_out,
            requested_profile_report=Path(self.profile_report_out.text().strip()),
            requested_workdir=Path(self.profile_workdir.text().strip()),
            requested_development_profile=Path(self.develop_profile_out.text().strip()),
            requested_calibrated_recipe=Path(self.calibrated_recipe_out.text().strip()),
        )
        profile_out = artifacts["profile_out"]
        profile_report = artifacts["profile_report"]
        workdir = artifacts["workdir"]
        development_profile_out = artifacts["development_profile"]
        calibrated_recipe_out = artifacts["calibrated_recipe"]
        validation_report_out = profile_report.with_name("qa_session_report.json")
        validation_holdout_count = 1 if self._profile_chart_candidate_count(charts, chart_capture_files) >= 2 else 0
        chart_type = self.profile_chart_type.currentText()
        min_confidence = float(self.profile_min_conf.value())
        allow_fallback_detection = bool(self.profile_allow_fallback.isChecked())
        camera = self.profile_camera.text().strip() or None
        lens = self.profile_lens.text().strip() or None
        recipe = self._build_effective_recipe()

        # Sync profile output path with RAW tab profile controls.
        self.profile_out_path_edit.setText(str(profile_out))
        self.path_profile_out.setText(str(profile_out))
        self.profile_report_out.setText(str(profile_report))
        self.profile_workdir.setText(str(workdir))
        self.develop_profile_out.setText(str(development_profile_out))
        self.calibrated_recipe_out.setText(str(calibrated_recipe_out))

        def task():
            task_manual_detections = dict(manual_detections or {})
            if pending_manual_detection is not None:
                source, detection = self._build_pending_manual_detection(
                    pending_manual_detection,
                    recipe=recipe,
                    chart_type=chart_type,
                    workdir=workdir,
                )
                task_manual_detections[source] = detection

            reference = ReferenceCatalog.from_path(reference_path)
            return auto_generate_profile_from_charts(
                chart_captures_dir=charts,
                chart_capture_files=chart_capture_files,
                recipe=recipe,
                reference=reference,
                profile_out=profile_out,
                profile_report_out=profile_report,
                validation_report_out=validation_report_out,
                work_dir=workdir,
                development_profile_out=development_profile_out,
                calibrated_recipe_out=calibrated_recipe_out,
                calibrate_development=True,
                chart_type=chart_type,
                min_confidence=min_confidence,
                allow_fallback_detection=allow_fallback_detection,
                camera_model=camera,
                lens_model=lens,
                manual_detections=task_manual_detections or None,
                validation_holdout_count=validation_holdout_count,
                profile_workers=1,
            )

        def on_success(payload) -> None:
            self._set_profile_output_payload(payload)
            self._update_chart_diagnostics(payload)
            normalizations = payload.get("recipe_profiling_normalizations")
            if isinstance(normalizations, list) and normalizations:
                summary = ", ".join(
                    f"{c.get('field')}: {c.get('from')} -> {c.get('to')}"
                    for c in normalizations
                    if isinstance(c, dict)
                )
                self._log_preview(f"Receta normalizada para perfilado cientifico: {summary}")
            profile_status = payload.get("profile_status") if isinstance(payload.get("profile_status"), dict) else {}
            status = str(profile_status.get("status") or "draft")
            if status == "validated":
                self.path_profile_active.setText(str(profile_out))
                self.chk_apply_profile.setChecked(True)
            else:
                self.path_profile_active.clear()
                self.chk_apply_profile.setChecked(False)
                if status == "draft":
                    reasons = profile_status.get("reasons") if isinstance(profile_status.get("reasons"), list) else []
                    detail = f" ({', '.join(str(r) for r in reasons[:3])})" if reasons else ""
                    self._log_preview(f"Perfil generado en estado draft{detail}; no se activa automaticamente.")
                else:
                    self._log_preview(f"Perfil no activado por estado: {status}")
            if payload.get("calibrated_recipe_path"):
                calibrated_recipe_path = Path(str(payload["calibrated_recipe_path"]))
                self.path_recipe.setText(str(calibrated_recipe_path))
                try:
                    self._apply_recipe_to_controls(load_recipe(calibrated_recipe_path))
                    self._invalidate_preview_cache()
                    QtCore.QTimer.singleShot(0, lambda: self._on_load_selected(show_message=False))
                except Exception as exc:
                    self._log_preview(f"No se pudo cargar receta calibrada en la GUI: {exc}")
            chart_profile_id = ""
            if payload.get("development_profile_path") and payload.get("calibrated_recipe_path"):
                session_label = self.session_name_edit.text().strip() or profile_out.stem
                base_stem = self._strip_version_suffix(profile_out.stem)
                chart_profile_name = f"{session_label} - carta"
                if profile_out.stem != base_stem:
                    chart_profile_name = f"{chart_profile_name} ({profile_out.stem})"
                profile_id = self._register_chart_development_profile(
                    name=chart_profile_name,
                    development_profile_path=Path(str(payload["development_profile_path"])),
                    calibrated_recipe_path=Path(str(payload["calibrated_recipe_path"])),
                    icc_profile_path=profile_out,
                    profile_report_path=profile_report,
                )
                chart_profile_id = profile_id
                assigned = self._assign_development_profile_to_raw_files(
                    profile_id,
                    self._raw_files_for_chart_profile_assignment(charts, chart_capture_files),
                    status="assigned",
                )
                if assigned:
                    self._log_preview(f"Perfil de ajuste avanzado asignado a {assigned} RAW de carta")
            profile_status = payload.get("profile_status") if isinstance(payload.get("profile_status"), dict) else {}
            self._register_icc_profile(
                {
                    "name": profile_out.stem,
                    "source": "generated",
                    "path": str(profile_out),
                    "profile_report_path": str(payload.get("profile_report_path") or profile_report),
                    "development_profile_id": chart_profile_id,
                    "development_profile_path": str(payload.get("development_profile_path") or ""),
                    "recipe_path": str(payload.get("calibrated_recipe_path") or ""),
                    "status": str(profile_status.get("status") or status),
                    "created_at": str(profile_status.get("generated_at") or ""),
                    "updated_at": self._profile_timestamp(),
                },
                activate=status == "validated",
                save=False,
            )
            if hasattr(self, "profile_summary_label"):
                self.profile_summary_label.setText(self._profile_success_summary(payload, profile_out))
            self._log_preview(f"Perfil de ajuste avanzado: {payload.get('development_profile_path')}")
            self._log_preview(f"Perfil ICC de entrada generado: {profile_out}")
            self._set_status(self.tr("Perfil avanzado con carta + ICC de entrada generado:") + f" {profile_out}")
            self._save_active_session(silent=True)
            self._refresh_gamut_diagnostics(profile_out=profile_out, focus=False)

        self._start_background_task(self.tr("Generacion de perfil avanzado con carta + ICC"), task, on_success)

    def _set_profile_output_payload(self, payload: Any) -> None:
        if not hasattr(self, "profile_output"):
            return
        self.profile_output.setPlainText(self._profile_output_text(payload))

    def _profile_output_text(self, payload: Any) -> str:
        if not isinstance(payload, dict):
            return str(payload)
        try:
            compact = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            return str(payload)
        if len(compact) <= PROFILE_OUTPUT_FULL_JSON_CHAR_LIMIT:
            return json.dumps(payload, indent=2, ensure_ascii=False)
        summary = self._profile_output_summary(payload, full_size=len(compact))
        return json.dumps(summary, indent=2, ensure_ascii=False)

    def _profile_output_summary(self, payload: dict[str, Any], *, full_size: int) -> dict[str, Any]:
        profile = payload.get("profile") if isinstance(payload.get("profile"), dict) else {}
        profile_status = payload.get("profile_status") if isinstance(payload.get("profile_status"), dict) else {}
        validation = payload.get("validation") if isinstance(payload.get("validation"), dict) else {}
        qa = validation.get("qa_report") if isinstance(validation.get("qa_report"), dict) else {}
        metadata = profile.get("metadata") if isinstance(profile.get("metadata"), dict) else {}
        errors = profile.get("patch_errors") if isinstance(profile.get("patch_errors"), list) else []
        worst = sorted(
            [e for e in errors if isinstance(e, dict)],
            key=lambda item: self._coerce_float(item.get("delta_e2000")),
            reverse=True,
        )[:24]
        return {
            "nota": (
                "La salida completa es grande y no se vuelca entera en la interfaz "
                "para evitar bloquear Qt."
            ),
            "full_json_chars": full_size,
            "chart_captures_total": payload.get("chart_captures_total", 0),
            "training_captures_total": payload.get(
                "training_captures_total",
                payload.get("chart_captures_total", 0),
            ),
            "chart_captures_used": payload.get("chart_captures_used", 0),
            "validation_captures_total": payload.get("validation_captures_total", 0),
            "validation_captures_used": payload.get("validation_captures_used", 0),
            "development_profile_path": payload.get("development_profile_path"),
            "calibrated_recipe_path": payload.get("calibrated_recipe_path"),
            "profile_report_path": payload.get("profile_report_path"),
            "qa_report_path": payload.get("qa_report_path"),
            "profile_status": profile_status,
            "neutral_axis_error": metadata.get("neutral_axis_error"),
            "workflow_recommendations": payload.get("workflow_recommendations", []),
            "error_summary": profile.get("error_summary"),
            "worst_patch_errors": worst,
            "validation_status": qa.get("status"),
            "validation_error_summary": qa.get("validation_error_summary"),
        }

    def _chart_diagnostics_profile_from_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        profile = payload.get("profile")
        if isinstance(profile, dict):
            return profile
        if isinstance(payload.get("patch_errors"), list) or isinstance(payload.get("error_summary"), dict):
            return payload
        metadata = payload.get("metadata")
        if isinstance(metadata, dict):
            patch_errors = metadata.get("diagnostic_matrix_patch_errors")
            error_summary = metadata.get("diagnostic_matrix_error_summary")
            if isinstance(patch_errors, list) or isinstance(error_summary, dict):
                return {
                    "patch_errors": patch_errors if isinstance(patch_errors, list) else [],
                    "error_summary": error_summary if isinstance(error_summary, dict) else {},
                }
        return {}

    def _chart_diagnostics_report_candidates(self) -> list[Path]:
        candidates: list[Path] = []
        seen: set[str] = set()

        def add(value: Any) -> None:
            path = self._session_stored_path(value)
            if path is None:
                return
            try:
                key = str(path.expanduser().resolve(strict=False))
            except Exception:
                key = str(path.expanduser())
            if key in seen:
                return
            seen.add(key)
            candidates.append(path.expanduser())

        if hasattr(self, "profile_report_out"):
            add(self.profile_report_out.text().strip())

        active_development_id = str(getattr(self, "_active_development_profile_id", "") or "")
        for profile in getattr(self, "_development_profiles", []) or []:
            if isinstance(profile, dict) and str(profile.get("id") or "") == active_development_id:
                add(profile.get("profile_report_path"))
                break

        active_icc = self._icc_profile_by_id(getattr(self, "_active_icc_profile_id", "")) if hasattr(self, "_icc_profile_by_id") else None
        if isinstance(active_icc, dict):
            add(active_icc.get("profile_report_path"))

        for profile in getattr(self, "_development_profiles", []) or []:
            if isinstance(profile, dict):
                add(profile.get("profile_report_path"))
        for profile in getattr(self, "_icc_profiles", []) or []:
            if isinstance(profile, dict):
                add(profile.get("profile_report_path"))

        if getattr(self, "_active_session_root", None) is not None:
            add(self._session_default_outputs()["profile_report"])

        return candidates

    def _load_chart_diagnostics_from_report(self, report_path: Path, *, focus: bool = False) -> bool:
        try:
            if not report_path.exists():
                return False
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:
            return False
        if not isinstance(payload, dict):
            return False

        profile = self._chart_diagnostics_profile_from_payload(payload)
        errors = profile.get("patch_errors") if isinstance(profile.get("patch_errors"), list) else []
        summary = profile.get("error_summary") if isinstance(profile.get("error_summary"), dict) else {}
        if not errors and not summary:
            return False

        normalized = dict(payload)
        if not isinstance(normalized.get("profile"), dict):
            normalized = {"profile": profile, "profile_report_path": str(report_path)}
        else:
            normalized.setdefault("profile_report_path", str(report_path))
        self._update_chart_diagnostics(normalized, focus=focus)
        if hasattr(self, "chart_diagnostics_summary"):
            self.chart_diagnostics_summary.setToolTip(str(report_path))
        return True

    def _refresh_chart_diagnostics_from_session(self, _checked: bool = False, *, focus: bool = False) -> bool:
        if not hasattr(self, "chart_diagnostics_table"):
            return False
        for report_path in self._chart_diagnostics_report_candidates():
            if self._load_chart_diagnostics_from_report(report_path, focus=focus):
                return True
        self._populate_chart_diagnostics_table([])
        self._update_chart_diagnostics_summary({}, [])
        if hasattr(self, "chart_diagnostics_summary"):
            self.chart_diagnostics_summary.setToolTip("")
        return False

    def _update_chart_diagnostics(self, payload: dict[str, Any], *, focus: bool = True) -> None:
        if not hasattr(self, "chart_diagnostics_table"):
            return
        profile = self._chart_diagnostics_profile_from_payload(payload)
        errors = profile.get("patch_errors") if isinstance(profile.get("patch_errors"), list) else []
        summary = profile.get("error_summary") if isinstance(profile.get("error_summary"), dict) else {}
        self._populate_chart_diagnostics_table(errors)
        self._update_chart_diagnostics_summary(summary, errors)
        if focus and hasattr(self, "analysis_tabs"):
            self.analysis_tabs.setCurrentIndex(1)

    def _populate_chart_diagnostics_table(self, errors: list[Any]) -> None:
        table = self.chart_diagnostics_table
        rows = [error for error in errors if isinstance(error, dict)]
        sorting_enabled = table.isSortingEnabled()
        table.setSortingEnabled(False)
        table.setUpdatesEnabled(False)
        try:
            table.clearContents()
            table.setRowCount(len(rows))
            for row, error in enumerate(rows):
                patch_id = str(error.get("patch_id") or "")
                reference_lab = self._coerce_lab_triplet(error.get("reference_lab"))
                profile_lab = self._coerce_lab_triplet(error.get("profile_lab"))
                values = [
                    patch_id,
                    *reference_lab,
                    *profile_lab,
                    self._coerce_float(error.get("delta_e76")),
                    self._coerce_float(error.get("delta_e2000")),
                ]
                for column, value in enumerate(values):
                    item = QtWidgets.QTableWidgetItem()
                    if isinstance(value, float):
                        item.setData(QtCore.Qt.DisplayRole, round(value, 3))
                    else:
                        item.setText(str(value))
                    if column == 8 and isinstance(value, float):
                        if value >= 10.0:
                            item.setBackground(QtGui.QColor("#7f1d1d"))
                            item.setForeground(QtGui.QColor("#fee2e2"))
                        elif value >= 5.0:
                            item.setBackground(QtGui.QColor("#78350f"))
                            item.setForeground(QtGui.QColor("#fef3c7"))
                    table.setItem(row, column, item)
        finally:
            table.setUpdatesEnabled(True)
            table.setSortingEnabled(sorting_enabled)
            table.viewport().update()

    def _update_chart_diagnostics_summary(self, summary: dict[str, Any], errors: list[Any]) -> None:
        if not hasattr(self, "chart_diagnostics_summary"):
            return
        if not errors and not summary:
            self.chart_diagnostics_summary.setText(self.tr("Sin datos de carta"))
            return
        mean_de = self._coerce_float(summary.get("mean_delta_e2000"))
        median_de = self._coerce_float(summary.get("median_delta_e2000"))
        p95_de = self._coerce_float(summary.get("p95_delta_e2000"))
        max_de = self._coerce_float(summary.get("max_delta_e2000"))
        worst = sorted(
            [e for e in errors if isinstance(e, dict)],
            key=lambda item: self._coerce_float(item.get("delta_e2000")),
            reverse=True,
        )[:3]
        worst_text = ", ".join(
            f"{str(item.get('patch_id') or '')}={self._coerce_float(item.get('delta_e2000')):.2f}"
            for item in worst
            if str(item.get("patch_id") or "")
        )
        patch_count = len([e for e in errors if isinstance(e, dict)])
        parts = [
            f"Parches: {patch_count}" if patch_count else self.tr("Resumen de carta sin tabla de parches"),
            f"DeltaE2000 media {mean_de:.2f}",
            f"mediana {median_de:.2f}",
            f"p95 {p95_de:.2f}",
            f"max {max_de:.2f}",
        ]
        if worst_text:
            parts.append(f"peores: {worst_text}")
        self.chart_diagnostics_summary.setText(" | ".join(parts))

    def _on_refresh_gamut_diagnostics(self, _checked: bool = False) -> None:
        self._refresh_gamut_diagnostics(focus=True)

    def _refresh_gamut_diagnostics(self, *, profile_out: Path | None = None, focus: bool = False) -> None:
        if not hasattr(self, "gamut_3d_widget"):
            return
        generated_profile = profile_out or self._candidate_generated_gamut_profile()
        snapshot = self._gamut_selection_snapshot(generated_profile=generated_profile)
        if hasattr(self, "gamut_status_label"):
            self.gamut_status_label.setText(self.tr("Gamut 3D: calculando..."))

        def task():
            task_monitor_profile = snapshot["monitor_profile"]
            if task_monitor_profile is None and (
                snapshot["selection_a"] == "monitor" or snapshot["selection_b"] == "monitor"
            ):
                try:
                    task_monitor_profile = detect_system_display_profile()
                except Exception:
                    task_monitor_profile = None
            spec_a = self._gamut_profile_spec_from_selection(
                snapshot["selection_a"],
                snapshot["custom_a"],
                generated_profile=snapshot["generated_profile"],
                monitor_profile=task_monitor_profile,
                label_suffix="A",
            )
            spec_b = self._gamut_profile_spec_from_selection(
                snapshot["selection_b"],
                snapshot["custom_b"],
                generated_profile=snapshot["generated_profile"],
                monitor_profile=task_monitor_profile,
                label_suffix="B",
            )
            payload = build_gamut_pair_diagnostics(profile_a=spec_a, profile_b=spec_b)
            payload["monitor_profile_path"] = str(task_monitor_profile) if task_monitor_profile else ""
            return payload

        def on_success(payload) -> None:
            self.gamut_3d_widget.set_gamut_payload(payload)
            task_monitor_text = str(payload.get("monitor_profile_path") or "") if isinstance(payload, dict) else ""
            task_monitor_profile = Path(task_monitor_text).expanduser() if task_monitor_text else snapshot["monitor_profile"]
            self._update_gamut_status(
                payload,
                generated_profile=snapshot["generated_profile"],
                monitor_profile=task_monitor_profile,
            )
            if focus and hasattr(self, "analysis_tabs"):
                index = self.analysis_tabs.indexOf(self.gamut_3d_widget.parentWidget())
                if index >= 0:
                    self.analysis_tabs.setCurrentIndex(index)

        self._start_background_task(self.tr("Diagnostico gamut 3D"), task, on_success)

    def _sync_gamut_custom_controls(self, *_args: object) -> None:
        for suffix in ("a", "b"):
            combo = getattr(self, f"gamut_profile_{suffix}_combo", None)
            visible = bool(combo is not None and str(combo.currentData() or "") == "custom")
            for name in (
                f"gamut_custom_{suffix}_label",
                f"gamut_custom_{suffix}_path",
                f"gamut_custom_{suffix}_browse",
            ):
                widget = getattr(self, name, None)
                if widget is not None:
                    widget.setVisible(visible)

    def _browse_gamut_custom_profile(self, target: QtWidgets.QLineEdit) -> None:
        start = target.text().strip() or self._default_icc_browse_directory()
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            self.tr("Selecciona perfil ICC"),
            start,
            "ICC Profiles (*.icc *.icm);;Todos (*)",
        )
        if path:
            target.setText(path)

    def _gamut_selection_snapshot(self, *, generated_profile: Path | None) -> dict[str, Any]:
        selection_a = (
            str(self.gamut_profile_a_combo.currentData() or "generated")
            if hasattr(self, "gamut_profile_a_combo")
            else "generated"
        )
        selection_b = (
            str(self.gamut_profile_b_combo.currentData() or "standard:srgb")
            if hasattr(self, "gamut_profile_b_combo")
            else "standard:srgb"
        )
        return {
            "selection_a": selection_a,
            "selection_b": selection_b,
            "custom_a": self.gamut_custom_a_path.text().strip() if hasattr(self, "gamut_custom_a_path") else "",
            "custom_b": self.gamut_custom_b_path.text().strip() if hasattr(self, "gamut_custom_b_path") else "",
            "generated_profile": generated_profile,
            "monitor_profile": self._monitor_profile_for_gamut(),
        }

    def _gamut_profile_spec_from_selection(
        self,
        selection: str,
        custom_path: str,
        *,
        generated_profile: Path | None,
        monitor_profile: Path | None,
        label_suffix: str,
    ) -> dict[str, str] | None:
        value = str(selection or "").strip()
        if value.startswith("managed:"):
            profile = self._icc_profile_by_id(value.split(":", 1)[1])
            path = self._session_stored_path(profile.get("path")) if profile else None
            if profile is None or path is None or not path.exists():
                return None
            return {
                "kind": "icc",
                "label": str(profile.get("name") or path.stem),
                "path": str(path),
                "color": "#e5e7eb" if label_suffix == "A" else "#22d3ee",
            }
        if value.startswith("standard:"):
            return {"kind": "standard", "key": value.split(":", 1)[1]}
        if value == "generated":
            if generated_profile is None or not generated_profile.exists():
                return None
            return {
                "kind": "icc",
                "label": "ICC generado",
                "path": str(generated_profile),
                "color": "#e5e7eb",
            }
        if value == "monitor":
            if monitor_profile is None or not monitor_profile.exists():
                return None
            return {
                "kind": "icc",
                "label": "Monitor",
                "path": str(monitor_profile),
                "color": "#60a5fa",
            }
        if value == "custom":
            path = Path(custom_path).expanduser() if custom_path else None
            if path is None or not path.exists():
                return None
            return {
                "kind": "icc",
                "label": f"ICC {label_suffix}: {path.name}",
                "path": str(path),
                "color": "#facc15",
            }
        return None

    def _candidate_generated_gamut_profile(self) -> Path | None:
        candidates: list[Path] = []
        if hasattr(self, "path_profile_active"):
            text = self.path_profile_active.text().strip()
            if text:
                candidates.append(Path(text).expanduser())
        if hasattr(self, "profile_out_path_edit"):
            text = self.profile_out_path_edit.text().strip()
            if text:
                candidates.append(Path(text).expanduser())
        for path in candidates:
            if path.exists():
                return path
        return candidates[0] if candidates else None

    def _monitor_profile_for_gamut(self) -> Path | None:
        if hasattr(self, "path_display_profile"):
            text = self.path_display_profile.text().strip()
            if text:
                path = Path(text).expanduser()
                if path.exists():
                    return path
        return None

    def _update_gamut_status(
        self,
        payload: dict[str, Any],
        *,
        generated_profile: Path | None,
        monitor_profile: Path | None,
    ) -> None:
        if not hasattr(self, "gamut_status_label"):
            return
        series = payload.get("series") if isinstance(payload.get("series"), list) else []
        comparisons = payload.get("comparisons") if isinstance(payload.get("comparisons"), list) else []
        skipped = payload.get("skipped") if isinstance(payload.get("skipped"), list) else []
        labels = [str(item.get("label") or "") for item in series if isinstance(item, dict)]
        parts: list[str] = [(" vs ".join(labels) if labels else self.tr("Sin perfiles comparables"))]
        if comparisons:
            compact = ", ".join(
                f"{item.get('source')} en {item.get('target')}: "
                f"{float(item.get('inside_ratio') or 0.0) * 100.0:.1f}% dentro"
                for item in comparisons
                if isinstance(item, dict)
            )
            if compact:
                parts.append(compact)
        elif generated_profile is not None and not generated_profile.exists():
            parts.append(self.tr("ICC generado no encontrado"))
        if monitor_profile is not None and not monitor_profile.exists():
            parts.append(self.tr("perfil de monitor no encontrado"))
        warnings: list[str] = []
        for item in series:
            if not isinstance(item, dict):
                continue
            health = item.get("health") if isinstance(item.get("health"), dict) else {}
            if str(health.get("status") or "") != "extreme":
                continue
            warnings.append(
                f"{item.get('label')}: L* {float(health.get('l_min') or 0.0):.0f}.."
                f"{float(health.get('l_max') or 0.0):.0f}, C* max "
                f"{float(health.get('chroma_max') or 0.0):.0f}"
            )
        if warnings:
            parts.append(self.tr("gamut ICC extremo:") + f" {', '.join(warnings[:2])}")
        if skipped:
            labels = ", ".join(str(item.get("label") or "?") for item in skipped[:3] if isinstance(item, dict))
            if labels:
                parts.append(self.tr("omitidos:") + f" {labels}")
        self.gamut_status_label.setText(" | ".join(parts))

    def _coerce_lab_triplet(self, value: Any) -> list[float]:
        if not isinstance(value, (list, tuple)) or len(value) < 3:
            return [0.0, 0.0, 0.0]
        return [self._coerce_float(value[0]), self._coerce_float(value[1]), self._coerce_float(value[2])]

    def _coerce_float(self, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _profile_chart_candidate_count(self, charts: Path, chart_capture_files: list[Path] | None) -> int:
        if chart_capture_files is not None:
            return len(chart_capture_files)
        try:
            return sum(
                1
                for p in charts.iterdir()
                if p.is_file() and p.suffix.lower() in PROFILE_CHART_EXTENSIONS
            )
        except Exception:
            return 0

    def _profile_success_summary(self, payload: dict[str, Any], profile_out: Path) -> str:
        profile = payload.get("profile") if isinstance(payload.get("profile"), dict) else {}
        error_summary = profile.get("error_summary") if isinstance(profile.get("error_summary"), dict) else {}
        de00 = error_summary.get("mean_delta_e2000")
        max_de00 = error_summary.get("max_delta_e2000")
        profile_status = payload.get("profile_status") if isinstance(payload.get("profile_status"), dict) else {}
        status = str(profile_status.get("status") or "draft")
        parts = [
            f"Estado perfil: {status}",
            f"ICC de entrada generado: {profile_out}",
            f"Entrenamiento: {payload.get('chart_captures_used', 0)}/{payload.get('training_captures_total', payload.get('chart_captures_total', 0))}",
            f"Receta calibrada: {payload.get('calibrated_recipe_path') or 'no generada'}",
        ]
        if isinstance(de00, (int, float)) and isinstance(max_de00, (int, float)):
            parts.append(f"DeltaE2000 entrenamiento: media {float(de00):.2f}, max {float(max_de00):.2f}")
        metadata = profile.get("metadata") if isinstance(profile.get("metadata"), dict) else {}
        neutral_error = metadata.get("neutral_axis_error") if isinstance(metadata.get("neutral_axis_error"), dict) else {}
        max_ab = neutral_error.get("max_ab_residual")
        if isinstance(max_ab, (int, float)):
            parts.append(f"Fila neutra: residuo a*/b* max {float(max_ab):.2f}")
        validation = payload.get("validation") if isinstance(payload.get("validation"), dict) else None
        if validation:
            qa = validation.get("qa_report") if isinstance(validation.get("qa_report"), dict) else {}
            v_error = qa.get("validation_error_summary") if isinstance(qa.get("validation_error_summary"), dict) else {}
            status = qa.get("status", "sin_estado")
            parts.append(
                f"Validación: {validation.get('validation_captures_used', 0)}/"
                f"{validation.get('validation_captures_total', 0)} ({status})"
            )
            mean_val = v_error.get("mean_delta_e2000")
            max_val = v_error.get("max_delta_e2000")
            if isinstance(mean_val, (int, float)) and isinstance(max_val, (int, float)):
                parts.append(f"DeltaE2000 validación: media {float(mean_val):.2f}, max {float(max_val):.2f}")
            checks = qa.get("checks") if isinstance(qa.get("checks"), list) else []
            failed_warnings = [
                str(check.get("id"))
                for check in checks
                if isinstance(check, dict)
                and check.get("severity") == "warning"
                and check.get("passed") is False
            ]
            if failed_warnings:
                parts.append(f"QA captura: {len(failed_warnings)} avisos ({', '.join(failed_warnings[:3])})")
        recommendations = payload.get("workflow_recommendations") if isinstance(payload.get("workflow_recommendations"), list) else []
        warning_recs = [
            str(item.get("id"))
            for item in recommendations
            if isinstance(item, dict) and item.get("severity") == "warning"
        ]
        if warning_recs:
            parts.append(f"Recomendaciones: {len(warning_recs)} avisos ({', '.join(warning_recs[:3])})")
        skipped = payload.get("chart_captures_skipped")
        if isinstance(skipped, list) and skipped:
            parts.append(f"Avisos/omisiones: {len(skipped)}")
        return "\n".join(parts)

    def _start_manual_chart_marking(self) -> None:
        if self._original_linear is None:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("Carga primero la captura de carta en el visor."))
            return
        if self._selected_file is None or self._selected_file.suffix.lower() not in PROFILE_CHART_EXTENSIONS:
            QtWidgets.QMessageBox.information(
                self,
                self.tr("Referencia no compatible"),
                self.tr("El marcado manual para perfilado cientifico solo acepta RAW/DNG/TIFF."),
            )
            return
        self._begin_manual_chart_marking()

    def _begin_manual_chart_marking(self) -> None:
        if self._original_linear is None:
            return
        if hasattr(self, "_set_mtf_roi_selection_active"):
            self._set_mtf_roi_selection_active(False)
        if hasattr(self, "_set_image_crop_selection_active"):
            self._set_image_crop_selection_active(False)
        if hasattr(self, "_deactivate_image_level_tool"):
            self._deactivate_image_level_tool()
        self._set_neutral_picker_active(False)
        self._manual_chart_marking = True
        self._manual_chart_points = []
        self._manual_chart_points_source = self._selected_file.expanduser().resolve(strict=False) if self._selected_file else None
        self._update_viewer_interaction_cursor()
        self._sync_manual_chart_overlay()
        self._set_status(self.tr("Marcado manual activo sobre preview de revelado: selecciona 4 esquinas en el visor"))

    def _clear_manual_chart_points(self) -> None:
        self._manual_chart_marking = False
        self._manual_chart_points = []
        self._manual_chart_points_source = None
        self._update_viewer_interaction_cursor()
        self._sync_manual_chart_overlay()
        self._set_status(self.tr("Marcado manual limpiado"))

    def _clear_manual_chart_points_for_file_change(self) -> None:
        if not self._manual_chart_points and not self._manual_chart_marking and self._manual_chart_points_source is None:
            return
        self._manual_chart_marking = False
        self._manual_chart_marking_after_reload = False
        self._manual_chart_points = []
        self._manual_chart_points_source = None
        self._update_viewer_interaction_cursor()
        self._sync_manual_chart_overlay()

    def _manual_chart_points_match_selected_file(self) -> bool:
        if not self._manual_chart_points:
            return True
        if self._selected_file is None or self._manual_chart_points_source is None:
            return False
        return self._normalized_path_key(self._manual_chart_points_source) == self._normalized_path_key(self._selected_file)

    def _on_result_image_click(self, x: float, y: float) -> None:
        if self._neutral_picker_active:
            self._apply_neutral_picker_at(x, y)
            return
        if hasattr(self, "_handle_image_tool_click") and self._handle_image_tool_click(x, y):
            return
        self._on_manual_chart_click(x, y)

    def _on_manual_chart_click(self, x: float, y: float) -> None:
        if not self._manual_chart_marking:
            return
        if not self._manual_chart_points_match_selected_file():
            self._manual_chart_points = []
            self._manual_chart_points_source = self._selected_file.expanduser().resolve(strict=False) if self._selected_file else None
        if len(self._manual_chart_points) >= 4:
            self._manual_chart_points = []
        self._manual_chart_points.append((float(x), float(y)))
        if len(self._manual_chart_points) == 4:
            self._manual_chart_marking = False
            self._update_viewer_interaction_cursor()
            self._set_status(self.tr("Cuatro esquinas marcadas; revisa y guarda la deteccion"))
        else:
            self._set_status(self.tr("Punto") + f" {len(self._manual_chart_points)}/4 " + self.tr("marcado"))
        self._sync_manual_chart_overlay()

    def _sync_manual_chart_overlay(self) -> None:
        points = self._manual_chart_points if self._manual_chart_points_match_selected_file() else []
        if hasattr(self, "manual_chart_points_label"):
            if points:
                coords = " | ".join(f"{idx}:{x:.0f},{y:.0f}" for idx, (x, y) in enumerate(points, start=1))
                self.manual_chart_points_label.setText(self.tr("Puntos:") + f" {len(points)}/4 - {coords}")
            else:
                self.manual_chart_points_label.setText(self.tr("Puntos: 0/4"))
        if hasattr(self, "image_result_single"):
            self.image_result_single.set_overlay_points(points)
        if hasattr(self, "image_result_compare"):
            self.image_result_compare.set_overlay_points(points)

    def _save_manual_chart_detection(self) -> None:
        if self._selected_file is None:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("Selecciona primero una captura de carta."))
            return
        if self._selected_file.suffix.lower() not in PROFILE_CHART_EXTENSIONS:
            QtWidgets.QMessageBox.information(
                self,
                self.tr("Referencia no compatible"),
                self.tr("Las detecciones de carta para perfilado cientifico solo aceptan RAW/DNG/TIFF."),
            )
            return
        if self._original_linear is None:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("Carga primero la captura de carta en el visor."))
            return
        if len(self._manual_chart_points) != 4:
            QtWidgets.QMessageBox.information(self, self.tr("Info"), self.tr("Marca exactamente 4 esquinas antes de guardar."))
            return
        if not self._manual_chart_points_match_selected_file():
            self._clear_manual_chart_points_for_file_change()
            QtWidgets.QMessageBox.information(
                self,
                self.tr("Marcado no valido"),
                self.tr("El marcado manual pertenecia a otra imagen. Marca de nuevo la carta en la captura actual."),
            )
            return

        workdir = Path(self.profile_workdir.text().strip() or "/tmp/probraw_profile_work")
        default_dir = workdir / "manual_detections"
        default_dir.mkdir(parents=True, exist_ok=True)
        default_path = default_dir / f"{self._selected_file.stem}.manual_detection.json"
        out_text, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            self.tr("Guardar deteccion manual"),
            str(default_path),
            "JSON (*.json)",
        )
        if not out_text:
            return

        selected = self._selected_file
        points_preview = list(self._manual_chart_points)
        preview_h, preview_w = self._manual_chart_point_space_shape()
        out_json = Path(out_text)
        chart_type = self.profile_chart_type.currentText()
        recipe = self._build_effective_recipe()

        def task():
            out_json.parent.mkdir(parents=True, exist_ok=True)
            overlay_path = out_json.with_name(f"{out_json.stem}.overlay.png")
            if selected.suffix.lower() in RAW_EXTENSIONS:
                target_image = out_json.with_name(f"{out_json.stem}.developed.tiff")
                full_image = develop_image_array(selected, recipe)
                write_tiff16(target_image, full_image)
            else:
                target_image = selected
                full_image = read_image(target_image)

            full_h, full_w = full_image.shape[:2]
            sx = full_w / max(1, preview_w)
            sy = full_h / max(1, preview_h)
            corners = [(x * sx, y * sy) for x, y in points_preview]
            detection = detect_chart_from_corners_array(full_image, corners=corners, chart_type=chart_type)
            write_json(out_json, detection)
            draw_detection_overlay_array(full_image, detection, overlay_path)
            return {
                "detection_json": str(out_json),
                "overlay": str(overlay_path),
                "image": str(target_image),
                "corners": corners,
                "source_raw": str(selected),
                "detection": to_json_dict(detection),
            }

        def on_success(payload) -> None:
            self.profile_output.setPlainText(json.dumps(payload, indent=2, ensure_ascii=False))
            source = Path(str(payload["source_raw"])).expanduser().resolve()
            self._manual_chart_detections[str(source)] = payload["detection"]
            if source not in {p.expanduser().resolve() for p in self._selected_chart_files}:
                self._selected_chart_files.append(source)
                self._selected_chart_files = sorted(set(self._selected_chart_files), key=lambda p: str(p))
                self._sync_profile_chart_selection_label()
            self.profile_charts_dir.setText(str(source.parent))
            self._log_preview(f"Detección manual guardada: {payload['detection_json']}")
            self._set_status(self.tr("Deteccion manual asociada a carta:") + f" {source.name}")

        self._start_background_task(self.tr("Deteccion manual de carta"), task, on_success)
