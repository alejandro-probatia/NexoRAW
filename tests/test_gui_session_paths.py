from __future__ import annotations

import json
import os
from pathlib import Path
import time

import cv2
import pytest
from PIL import Image, ImageCms

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")
from PySide6 import QtCore, QtGui, QtTest, QtWidgets  # noqa: E402

import probraw.gui as gui_module  # noqa: E402
import probraw.ui.window.display as display_module  # noqa: E402
import probraw.ui.window.preview_export as preview_export_module  # noqa: E402
import probraw.ui.window.preview_recipe as preview_recipe_module  # noqa: E402
import probraw.ui.window.preview_render as preview_render_module  # noqa: E402
from probraw.analysis.mtf import MTFResult  # noqa: E402
from probraw.chart.sampling import ReferenceCatalog  # noqa: E402
from probraw.core.models import Recipe  # noqa: E402
from probraw.core.utils import write_tiff16  # noqa: E402
from probraw.gui import ICCRawMainWindow  # noqa: E402
from probraw.display_color import profiled_float_to_display_u8, srgb_to_display_u8  # noqa: E402
from probraw.gui_config import PREVIEW_INTERACTIVE_TONAL_MAX_SIDE  # noqa: E402
from probraw.provenance.c2pa import C2PASignConfig  # noqa: E402
from probraw.provenance.probraw_proof import ProbRawProofConfig, ProbRawProofResult  # noqa: E402
from probraw.raw import pipeline  # noqa: E402
from probraw.raw.preview import standard_profile_to_srgb_display  # noqa: E402
from probraw.session import create_session, load_session  # noqa: E402
from probraw.sidecar import load_raw_sidecar, raw_sidecar_path, write_raw_sidecar  # noqa: E402


@pytest.fixture
def qapp(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PROBRAW_SETTINGS_DIR", str(tmp_path / "qt_settings"))
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    return app


def _activate_fake_session_icc(window: ICCRawMainWindow, root: Path) -> Path:
    profile = root / "00_configuraciones" / "profiles" / "session-input.icc"
    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_bytes(b"fake icc profile bytes" * 16)
    window.path_profile_active.setText(str(profile))
    window.chk_apply_profile.setChecked(True)
    return profile


def test_activate_session_migrates_temp_outputs_to_session_paths(tmp_path: Path, monkeypatch, qapp):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg_config"))
    root = tmp_path / "session_root"
    window = ICCRawMainWindow()
    paths = window._session_paths_from_root(root)
    directories = {key: str(path) for key, path in paths.items()}

    payload = {
        "version": 1,
        "metadata": {"name": "case_a"},
        "directories": directories,
        "state": {
            "profile_charts_dir": str(tmp_path / "stale_pytest_paths" / "charts"),
            "profile_output_path": "/tmp/camera_profile_gui.icc",
            "profile_report_path": "/tmp/profile_report_gui.json",
            "profile_workdir": "/tmp/probraw_profile_work",
            "development_profile_path": "/tmp/development_profile_gui.json",
            "calibrated_recipe_path": "/tmp/recipe_calibrated_gui.yml",
            "recipe_path": str(tmp_path / "stale_pytest_paths" / "config" / "recipe_calibrated.yml"),
            "profile_active_path": "/tmp/camera_profile_gui.icc",
            "batch_input_dir": str(tmp_path / "stale_pytest_paths" / "raw"),
            "batch_output_dir": "/tmp/probraw_batch_tiffs",
            "preview_png_path": "/tmp/probraw_preview.png",
        },
        "queue": [],
    }

    try:
        window._activate_session(root, payload)
        defaults = window._session_default_outputs(paths=paths, session_name="case_a")

        assert window.profile_out_path_edit.text() == str(defaults["profile_out"])
        assert window.path_profile_out.text() == str(defaults["profile_out"])
        assert window.profile_report_out.text() == str(defaults["profile_report"])
        assert window.profile_workdir.text() == str(defaults["workdir"])
        assert window.develop_profile_out.text() == str(defaults["development_profile"])
        assert window.calibrated_recipe_out.text() == str(defaults["calibrated_recipe"])
        assert window.path_recipe.text() == str(defaults["recipe"])
        assert window.profile_charts_dir.text() == str(paths["charts"])
        assert window.batch_input_dir.text() == str(paths["raw"])
        assert window.batch_out_dir.text() == str(defaults["tiff_dir"])
        assert window.path_preview_png.text() == str(defaults["preview"])
        assert window.path_profile_active.text() == ""

        saved_state = load_session(root)["state"]
        assert saved_state["profile_output_path"] == str(defaults["profile_out"])
        assert saved_state["recipe_path"] == str(defaults["recipe"])
        assert saved_state["batch_output_dir"] == str(defaults["tiff_dir"])
    finally:
        window.close()


def test_activate_session_sanitizes_profile_reference_outputs_and_rejected_profile(tmp_path: Path, monkeypatch, qapp):
    root = tmp_path / "session_root"
    window = ICCRawMainWindow()
    monkeypatch.setattr(window, "_is_legacy_temp_output_path", lambda _value: False)
    paths = window._session_paths_from_root(root)
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    export_tiff_dir = paths["exports"] / "tiff"
    export_tiff_dir.mkdir(parents=True, exist_ok=True)
    raw_file = paths["raw"] / "chart_01.NEF"
    derived_tiff = export_tiff_dir / "chart_01.tiff"
    raw_file.write_bytes(b"raw bytes")
    derived_tiff.write_bytes(b"derived tiff bytes")

    profile = paths["profiles"] / "case_a.icc"
    profile.write_bytes(b"icc bytes")
    profile.with_suffix(".profile.json").write_text('{"profile_status": "rejected"}', encoding="utf-8")

    payload = {
        "version": 1,
        "metadata": {"name": "case_a"},
        "directories": {key: str(path) for key, path in paths.items()},
        "state": {
            "profile_charts_dir": str(export_tiff_dir),
            "profile_chart_files": [str(derived_tiff), str(raw_file)],
            "profile_active_path": str(profile),
            "preview_apply_profile": True,
        },
        "queue": [],
    }

    try:
        window._activate_session(root, payload)

        assert window.profile_charts_dir.text() == str(paths["raw"])
        assert window._selected_chart_files == [raw_file]
        assert window.path_profile_active.text() == ""
        assert not window.chk_apply_profile.isChecked()

        saved_state = load_session(root)["state"]
        assert saved_state["profile_charts_dir"] == str(paths["raw"])
        assert saved_state["profile_chart_files"] == [str(raw_file)]
        assert saved_state["profile_active_path"] == ""
        assert saved_state["preview_apply_profile"] is False
    finally:
        window.close()


def test_create_session_does_not_inherit_previous_project_images_or_profiles(tmp_path: Path, qapp):
    old_root = tmp_path / "old_session"
    old_raw = old_root / "raw"
    old_raw.mkdir(parents=True)
    old_image = old_raw / "old_capture.tif"
    Image.new("RGB", (16, 16), (80, 120, 160)).save(old_image)
    old_exports = old_root / "02_DRV"
    old_profiles = old_root / "00_configuraciones" / "profiles"
    old_config = old_root / "00_configuraciones"
    old_work = old_config / "work" / "profile_generation"
    old_exports.mkdir(parents=True)
    old_profiles.mkdir(parents=True)
    old_work.mkdir(parents=True)

    old_payload = create_session(
        old_root,
        name="old",
        state={
            "profile_charts_dir": str(old_raw),
            "profile_chart_files": [str(old_image)],
            "batch_input_dir": str(old_raw),
            "batch_output_dir": str(old_exports),
            "profile_output_path": str(old_profiles / "old.icc"),
            "profile_report_path": str(old_config / "profile_report.json"),
            "profile_workdir": str(old_work),
            "development_profile_path": str(old_config / "development_profile.json"),
            "calibrated_recipe_path": str(old_config / "recipe_calibrated.yml"),
            "development_profiles": [{"id": "old-profile", "name": "Old profile"}],
            "active_development_profile_id": "old-profile",
        },
        queue=[{"source": str(old_image), "status": "pending"}],
    )
    new_root = tmp_path / "new_session"

    window = ICCRawMainWindow()
    try:
        window._activate_session(old_root, old_payload)
        window._set_current_directory(old_raw)
        assert window.file_list.count() == 1

        window.session_root_path.setText(str(new_root))
        window.session_name_edit.setText("new")
        window._on_create_session()

        new_paths = window._session_paths_from_root(new_root)
        saved = load_session(new_root)
        serialized = gui_module.json.dumps(saved)

        assert window._active_session_root == new_root.resolve()
        assert window._current_dir == new_paths["raw"]
        assert window.file_list.count() == 0
        assert window.profile_charts_dir.text() == str(new_paths["charts"])
        assert window.batch_input_dir.text() == str(new_paths["raw"])
        new_defaults = window._session_default_outputs(paths=new_paths, session_name="new")
        assert window.batch_out_dir.text() == str(new_defaults["tiff_dir"])
        assert window.profile_out_path_edit.text() == str(new_defaults["profile_out"])
        assert window.path_profile_out.text() == str(new_defaults["profile_out"])
        assert window.profile_report_out.text() == str(new_defaults["profile_report"])
        assert window.profile_workdir.text() == str(new_defaults["workdir"])
        assert window.develop_profile_out.text() == str(new_defaults["development_profile"])
        assert window.calibrated_recipe_out.text() == str(new_defaults["calibrated_recipe"])
        assert window.path_preview_png.text() == str(new_defaults["preview"])
        assert window._selected_chart_files == []
        assert window._develop_queue == []
        assert window._development_profiles == []
        assert str(old_root) not in serialized
    finally:
        window.close()


def test_activate_session_rejects_existing_state_paths_outside_project_root(tmp_path: Path, qapp):
    old_root = tmp_path / "old_session"
    old_raw = old_root / "raw"
    old_raw.mkdir(parents=True)
    old_image = old_raw / "old_chart.tif"
    Image.new("RGB", (16, 16), (80, 120, 160)).save(old_image)
    old_exports = old_root / "02_DRV"
    old_config = old_root / "00_configuraciones"
    old_profiles = old_config / "profiles"
    old_work = old_config / "work" / "profile_generation"
    for folder in (old_exports, old_config, old_profiles, old_work):
        folder.mkdir(parents=True, exist_ok=True)
    old_profile = old_profiles / "old.icc"
    old_report = old_config / "profile_report.json"
    old_development = old_config / "development_profile.json"
    old_recipe = old_config / "recipe.yml"
    old_calibrated = old_config / "recipe_calibrated.yml"
    old_preview = old_exports / "preview.png"
    for file_path in (old_profile, old_report, old_development, old_recipe, old_calibrated, old_preview):
        file_path.write_text("old", encoding="utf-8")

    new_root = tmp_path / "new_session"
    window = ICCRawMainWindow()
    paths = window._session_paths_from_root(new_root)
    payload = create_session(
        new_root,
        name="new",
        state={
            "profile_charts_dir": str(old_raw),
            "profile_chart_files": [str(old_image)],
            "batch_input_dir": str(old_raw),
            "batch_output_dir": str(old_exports),
            "profile_output_path": str(old_profile),
            "profile_report_path": str(old_report),
            "profile_workdir": str(old_work),
            "development_profile_path": str(old_development),
            "calibrated_recipe_path": str(old_calibrated),
            "recipe_path": str(old_recipe),
            "preview_png_path": str(old_preview),
        },
    )
    payload["directories"].update(
        {
            "raw": str(old_raw),
            "charts": str(old_raw),
            "exports": str(old_exports),
            "profiles": str(old_profiles),
            "config": str(old_config),
            "work": str(old_config / "work"),
        }
    )

    try:
        window._activate_session(new_root, payload)
        defaults = window._session_default_outputs(paths=paths, session_name="new")

        assert window._current_dir == paths["raw"]
        assert window.file_list.count() == 0
        assert window.session_dir_raw.text() == str(paths["raw"])
        assert window.session_dir_charts.text() == str(paths["charts"])
        assert window.session_dir_exports.text() == str(paths["exports"])
        assert window.session_dir_profiles.text() == str(paths["profiles"])
        assert window.session_dir_config.text() == str(paths["config"])
        assert window.session_dir_work.text() == str(paths["work"])
        assert window.profile_charts_dir.text() == str(paths["charts"])
        assert window.batch_input_dir.text() == str(paths["raw"])
        assert window.batch_out_dir.text() == str(defaults["tiff_dir"])
        assert window.profile_out_path_edit.text() == str(defaults["profile_out"])
        assert window.path_profile_out.text() == str(defaults["profile_out"])
        assert window.profile_report_out.text() == str(defaults["profile_report"])
        assert window.profile_workdir.text() == str(defaults["workdir"])
        assert window.develop_profile_out.text() == str(defaults["development_profile"])
        assert window.calibrated_recipe_out.text() == str(defaults["calibrated_recipe"])
        assert window.path_recipe.text() == str(defaults["recipe"])
        assert window.path_preview_png.text() == str(defaults["preview"])
        assert window._selected_chart_files == []
        assert str(old_root) not in gui_module.json.dumps(load_session(new_root))
    finally:
        window.close()


def _custom_reference_payload(name: str = "ColorChecker personalizada") -> dict:
    return {
        "chart_name": name,
        "chart_version": "unit",
        "reference_source": "unit-test",
        "illuminant": "D50",
        "observer": "2",
        "patches": [
            {"patch_id": f"P{i:02d}", "patch_name": f"Patch {i:02d}", "reference_lab": [50.0, 0.0, 0.0]}
            for i in range(1, 25)
        ],
    }


def test_session_can_save_and_reload_custom_reference_catalog(tmp_path: Path, qapp):
    root = tmp_path / "session"
    payload = create_session(root, name="Sesion referencias")

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        saved = window._save_reference_payload_to_session(
            _custom_reference_payload(),
            desired_name="mi carta",
        )

        assert saved.parent == root / "00_configuraciones" / "references"
        assert window.path_reference.text() == str(saved)
        assert "ColorChecker personalizada" in window.reference_status_label.text()
        assert window.reference_catalog_combo.findData(str(saved)) >= 0

        state = load_session(root)["state"]
        assert state["reference_path"] == str(saved)
    finally:
        window.close()

    second = ICCRawMainWindow()
    try:
        second._activate_session(root, load_session(root))

        assert second.path_reference.text() == str(saved)
        assert second.reference_catalog_combo.findData(str(saved)) >= 0
        assert "ColorChecker personalizada" in second.reference_status_label.text()
    finally:
        second.close()


def test_invalid_custom_reference_is_rejected_by_session_save(tmp_path: Path, qapp):
    root = tmp_path / "session"
    payload = create_session(root, name="Sesion referencias")
    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        bad = _custom_reference_payload()
        bad["patches"] = bad["patches"][:3]

        with pytest.raises(RuntimeError, match="Referencia de carta invalida"):
            window._save_reference_payload_to_session(bad, desired_name="incompleta")
    finally:
        window.close()


def test_reference_table_generates_custom_reference_payload(qapp):
    window = ICCRawMainWindow()
    try:
        table = QtWidgets.QTableWidget()
        window._populate_reference_table(table, _custom_reference_payload())
        table.item(0, 3).setText("37.9856")
        table.item(0, 4).setText("13.5551")
        table.item(0, 5).setText("14.0501")

        payload = window._reference_payload_from_table(
            table,
            chart_name="ColorChecker personalizada",
            chart_version="medida",
            reference_source="espectro personalizado",
            illuminant="D50",
            observer="2",
            patch_order="row-major",
        )

        assert payload["chart_name"] == "ColorChecker personalizada"
        assert payload["patches"][0]["reference_lab"] == [37.9856, 13.5551, 14.0501]
        assert ReferenceCatalog(payload, strict=True).patch_map["P01"]["reference_lab"] == [37.9856, 13.5551, 14.0501]
    finally:
        window.close()


def test_reference_lab_swatch_updates_from_lab_values(qapp):
    window = ICCRawMainWindow()
    try:
        table = QtWidgets.QTableWidget()
        window._populate_reference_table(table, _custom_reference_payload())

        table.item(0, 3).setText("50")
        table.item(0, 4).setText("0")
        table.item(0, 5).setText("0")
        rgb = window._lab_reference_to_srgb_u8([50.0, 0.0, 0.0])
        color = table.item(0, 0).background().color()

        assert max(rgb) - min(rgb) <= 4
        assert 115 <= rgb[0] <= 125
        assert color.red() == rgb[0]
        assert color.green() == rgb[1]
        assert color.blue() == rgb[2]
    finally:
        window.close()


def test_file_icons_do_not_decode_image_data(tmp_path: Path, monkeypatch, qapp):
    image_path = tmp_path / "frame.tiff"
    raw_path = tmp_path / "capture.dng"
    image_path.write_bytes(b"not a real image")
    raw_path.write_bytes(b"not a real raw")

    def fail_read_image(*_args, **_kwargs):
        raise AssertionError("file-list icons must not decode image data")

    monkeypatch.setattr(gui_module, "read_image", fail_read_image)

    window = ICCRawMainWindow()
    try:
        assert not window._icon_for_file(image_path).isNull()
        assert not window._icon_for_file(raw_path).isNull()
    finally:
        window.close()


def test_raw_develop_layout_prioritizes_viewer_area(qapp):
    window = ICCRawMainWindow()
    try:
        assert isinstance(window.left_tabs, gui_module.PersistentSideTabWidget)
        assert window.left_tabs.tabPosition() == QtWidgets.QTabWidget.West
        labels = [window.left_tabs.tabText(i) for i in range(window.left_tabs.count())]
        assert labels == ["Explorador", "Diagnóstico", "Metadatos", "Log"]
        analysis_labels = [window.analysis_tabs.tabText(i) for i in range(window.analysis_tabs.count())]
        assert analysis_labels == ["Imagen", "Carta", "Gamut 3D"]
        assert isinstance(window.gamut_3d_widget, gui_module.Gamut3DWidget)
        assert window.viewer_splitter.count() == 2
        assert window.viewer_splitter.widget(0) is window.viewer_area
        assert window.viewer_stack.parentWidget() is window.viewer_area
        thumbnail_pane = window.viewer_splitter.widget(1)
        assert not thumbnail_pane.findChildren(QtWidgets.QPushButton)
        assert isinstance(window.chk_compare, QtGui.QAction)
        assert isinstance(window.chk_apply_profile, QtGui.QAction)
        assert isinstance(window._action_side_columns_focus, QtGui.QAction)
        toolbar_buttons = window.viewer_toolbar.findChildren(QtWidgets.QToolButton)
        assert len(toolbar_buttons) >= 10
        assert not any(button.defaultAction() is window.chk_apply_profile for button in toolbar_buttons)
        assert not any(button.menu() is not None for button in toolbar_buttons)
        assert not window.raw_splitter.widget(0).isHidden()
        assert not window.raw_splitter.widget(2).isHidden()
        window._action_side_columns_focus.setChecked(True)
        qapp.processEvents()
        assert window.raw_splitter.widget(0).isHidden()
        assert window.raw_splitter.widget(2).isHidden()
        window._action_side_columns_focus.setChecked(False)
        qapp.processEvents()
        assert not window.raw_splitter.widget(0).isHidden()
        assert not window.raw_splitter.widget(2).isHidden()
        assert any(
            window.viewer_histogram is child
            for child in window.right_workflow_tabs.widget(1).findChildren(gui_module.RGBHistogramWidget)
        )
        assert hasattr(window, "thumbnail_size_slider")
        if hasattr(QtWidgets.QFileSystemModel, "DontWatchForChanges"):
            assert window._dir_model.testOption(QtWidgets.QFileSystemModel.DontWatchForChanges)
        if os.name != "nt":
            assert window._dir_model_root_path != "/"
    finally:
        window.close()


def test_directory_tree_can_open_folder_in_system_file_browser(tmp_path: Path, monkeypatch, qapp):
    opened: list[str] = []

    def fake_open_url(url):
        opened.append(url.toLocalFile())
        return True

    monkeypatch.setattr(gui_module.QtGui.QDesktopServices, "openUrl", fake_open_url)

    window = ICCRawMainWindow()
    try:
        window._open_directory_in_system_file_browser(tmp_path)

        assert [Path(path) for path in opened] == [tmp_path]
        assert "explorador del sistema" in window.statusBar().currentMessage()
    finally:
        window.close()


def test_gamut_widget_resets_camera_when_payload_changes(qapp):
    widget = gui_module.Gamut3DWidget()
    try:
        series_a = [
            {
                "label": "Perfil A",
                "path": "/tmp/profile-a.icc",
                "color": "#f8fafc",
                "role": "wire",
                "points_lab": gui_module.np.asarray(
                    [[50.0, 0.0, 0.0], [65.0, 25.0, -18.0]],
                    dtype=gui_module.np.float64,
                ),
                "surface_rgb": gui_module.np.asarray(
                    [[0.0, 0.0, 0.0], [1.0, 0.4, 0.2]],
                    dtype=gui_module.np.float64,
                ),
                "quads": [],
            }
        ]
        series_b = [
            {
                **series_a[0],
                "label": "Perfil B",
                "path": "/tmp/profile-b.icc",
                "points_lab": gui_module.np.asarray(
                    [[50.0, 0.0, 0.0], [80.0, 60.0, -40.0]],
                    dtype=gui_module.np.float64,
                ),
            }
        ]

        widget.set_series(series_a)
        widget._azimuth = 10.0
        widget._elevation = 76.0
        widget._zoom = 2.4
        widget.set_series(series_a)

        assert widget._azimuth == 10.0
        assert widget._elevation == 76.0
        assert widget._zoom == 2.4

        widget.set_series(series_b)

        assert widget._azimuth == widget.DEFAULT_AZIMUTH
        assert widget._elevation == widget.DEFAULT_ELEVATION
        assert widget._zoom == widget.DEFAULT_ZOOM
    finally:
        widget.close()


def test_left_vertical_tabs_remain_available_when_sidebar_is_compacted(qapp):
    window = ICCRawMainWindow()
    try:
        window.resize(1280, 760)
        window.main_tabs.setCurrentIndex(1)
        window.show()
        qapp.processEvents()

        collapsed_width = window.left_tabs.collapsedWidth()
        window.raw_splitter.setSizes([0, 960, 300])
        qapp.processEvents()

        sizes = window.raw_splitter.sizes()
        assert sizes[0] >= collapsed_width
        assert window.left_tabs.tabBar().isVisible()
        assert window.left_tabs.tabBar().width() > 0

        window.left_tabs.setCurrentIndex(1)
        qapp.processEvents()

        assert window.raw_splitter.sizes()[0] >= 260
    finally:
        window.close()


def test_main_window_omits_redundant_app_title_header(qapp):
    window = ICCRawMainWindow()
    try:
        label_texts = [label.text() for label in window.centralWidget().findChildren(QtWidgets.QLabel)]
        assert gui_module.APP_NAME not in label_texts
        assert not any("RAW -> ajuste por archivo" in text for text in label_texts)
    finally:
        window.close()


def test_image_panels_use_neutral_gray_background(qapp):
    window = ICCRawMainWindow()
    try:
        stylesheet = window.image_result_single.styleSheet().lower()
        assert gui_module.IMAGE_PANEL_BACKGROUND == "#2b2b2b"
        assert "background-color: #2b2b2b" in stylesheet
        assert "#111827" not in stylesheet
    finally:
        window.close()


def test_viewer_zoom_percentage_tracks_real_pixel_scale(qapp):
    window = ICCRawMainWindow()
    try:
        image = gui_module.np.zeros((200, 400, 3), dtype=gui_module.np.uint8)
        window.image_result_single.setFixedSize(200, 100)
        window.image_result_single.set_rgb_u8_image(image)

        window._viewer_fit()
        assert window.viewer_zoom_label.text() == "50%"

        window._viewer_zoom_100()
        assert window.viewer_zoom_label.text() == "100%"
        assert window.image_result_single.current_display_scale() == pytest.approx(1.0)
    finally:
        window.close()


def test_image_panel_magnification_uses_pixel_exact_sampling(qapp):
    panel = gui_module.ImagePanel("test", framed=False)
    try:
        panel.setFixedSize(4, 2)
        image = gui_module.np.asarray([[[0, 0, 0], [255, 255, 255]]], dtype=gui_module.np.uint8)
        panel.set_rgb_u8_image(image)
        panel.show()
        qapp.processEvents()

        assert panel.current_display_scale() == pytest.approx(2.0)
        assert panel._pixel_exact_rendering_enabled(panel.current_display_scale())

        grabbed = panel.grab().toImage().convertToFormat(QtGui.QImage.Format_RGB888)
        left = QtGui.QColor(grabbed.pixel(1, 1)).red()
        right = QtGui.QColor(grabbed.pixel(2, 1)).red()

        assert left == 0
        assert right == 255
    finally:
        panel.close()


def test_image_panel_does_not_tag_device_rgb_after_monitor_conversion(qapp):
    if not hasattr(QtGui.QImage, "colorSpace"):
        pytest.skip("Qt sin QImage.colorSpace")

    panel = gui_module.ImagePanel("test", framed=False)
    try:
        image = gui_module.np.zeros((2, 2, 3), dtype=gui_module.np.uint8)

        panel.set_rgb_u8_image(image, color_space="srgb")
        assert isinstance(panel._base_pixmap, QtGui.QImage)
        assert panel._base_pixmap.colorSpace().isValid()

        panel.set_rgb_u8_image(image, color_space="device")
        assert isinstance(panel._base_pixmap, QtGui.QImage)
        assert not panel._base_pixmap.colorSpace().isValid()
    finally:
        panel.close()


def test_image_panel_pixel_grid_appears_only_at_analysis_magnification(qapp):
    panel = gui_module.ImagePanel("test", framed=False)
    try:
        panel.setFixedSize(160, 160)
        panel.set_rgb_u8_image(gui_module.np.zeros((16, 16, 3), dtype=gui_module.np.uint8))

        assert panel._pixel_grid_visible(7.99) is False
        assert panel._pixel_grid_visible(8.0) is True

        panel.set_view_transform(zoom=1.0, rotation=90)
        assert panel._pixel_grid_visible(10.0) is False
    finally:
        panel.close()


def test_image_panel_zoom_preserves_current_view_center(qapp):
    panel = gui_module.ImagePanel("test", framed=False)
    try:
        panel.setFixedSize(100, 100)
        panel.set_rgb_u8_image(gui_module.np.zeros((100, 100, 3), dtype=gui_module.np.uint8))
        panel.set_view_transform(zoom=2.0, rotation=0)
        panel._pan = QtCore.QPointF(-50.0, 0.0)

        center = QtCore.QPointF(50.0, 50.0)
        before = panel._map_widget_to_image(center)
        panel.set_view_transform(zoom=4.0, rotation=0)
        after = panel._map_widget_to_image(center)

        assert before is not None
        assert after is not None
        assert after[0] == pytest.approx(before[0])
        assert after[1] == pytest.approx(before[1])
    finally:
        panel.close()


def test_image_crop_tool_uses_viewer_roi_dispatch(qapp):
    window = ICCRawMainWindow()
    try:
        window._original_linear = gui_module.np.zeros((120, 160, 3), dtype=gui_module.np.float32)
        window.image_result_single.set_rgb_u8_image(gui_module.np.zeros((120, 160, 3), dtype=gui_module.np.uint8))
        window._toggle_image_crop_selection(True)

        assert window._image_crop_selection_active is True
        assert window.image_result_single._roi_selection_enabled is True
        window._on_viewer_roi_selected(10.2, 20.6, 50.4, 40.2)

        assert window._image_crop_rect == (10, 21, 50, 40)
        assert window._image_crop_selection_active is False
        assert window.action_image_crop_select.isChecked() is False
        assert window.image_result_single._roi_rect is None
        assert window.image_result_single.view_crop_rect() == (10, 21, 50, 40)
        assert window._image_crop_base_size == (160, 120)
        assert window._image_crop_normalized_rect == pytest.approx((10 / 160, 21 / 120, 50 / 160, 40 / 120))
    finally:
        window.close()


def test_image_crop_action_is_shared_between_menu_and_toolbar(qapp):
    window = ICCRawMainWindow()
    try:
        actions = [
            action
            for action in window.findChildren(QtGui.QAction)
            if action.text() == "Seleccionar recorte"
        ]

        assert actions == [window.action_image_crop_select]

        window._set_image_crop_selection_active(True)
        assert actions[0].isChecked() is True
    finally:
        window.close()


def test_viewer_roi_dispatch_still_routes_to_mtf_when_crop_inactive(qapp):
    window = ICCRawMainWindow()
    try:
        calls: list[tuple[float, float, float, float]] = []
        window._on_mtf_roi_selected = lambda *args: calls.append(args)

        window._on_viewer_roi_selected(1.0, 2.0, 30.0, 40.0)

        assert calls == [(1.0, 2.0, 30.0, 40.0)]
    finally:
        window.close()


def test_image_level_horizontal_sets_fractional_viewer_rotation(qapp):
    window = ICCRawMainWindow()
    try:
        window._original_linear = gui_module.np.zeros((120, 160, 3), dtype=gui_module.np.float32)
        window._start_image_level_tool("horizontal")

        assert window._handle_image_tool_click(0.0, 0.0) is True
        assert window._handle_image_tool_click(100.0, 10.0) is True

        signed_rotation = ((float(window._viewer_rotation) + 180.0) % 360.0) - 180.0
        assert signed_rotation == pytest.approx(-5.7106, abs=1e-3)
        assert window._image_level_selection_active is False
        assert window.image_result_single._overlay_points == []
    finally:
        window.close()


def test_image_tools_accept_real_mouse_events_on_viewer(qapp):
    window = ICCRawMainWindow()
    try:
        window._original_linear = gui_module.np.zeros((100, 100, 3), dtype=gui_module.np.float32)
        window.image_result_single.setFixedSize(200, 200)
        window.image_result_single.set_rgb_u8_image(gui_module.np.zeros((100, 100, 3), dtype=gui_module.np.uint8))
        window.show()
        qapp.processEvents()

        window._toggle_image_crop_selection(True)
        QtTest.QTest.mousePress(window.image_result_single, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, QtCore.QPoint(20, 20))
        QtTest.QTest.mouseMove(window.image_result_single, QtCore.QPoint(120, 100))
        QtTest.QTest.mouseRelease(window.image_result_single, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, QtCore.QPoint(120, 100))
        qapp.processEvents()

        assert window._image_crop_rect == (10, 10, 50, 40)

        window._start_image_level_tool("horizontal")
        QtTest.QTest.mousePress(window.image_result_single, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, QtCore.QPoint(20, 20))
        QtTest.QTest.mouseMove(window.image_result_single, QtCore.QPoint(120, 100))
        QtTest.QTest.mouseRelease(window.image_result_single, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, QtCore.QPoint(120, 100))
        qapp.processEvents()

        signed_rotation = ((float(window._viewer_rotation) + 180.0) % 360.0) - 180.0
        assert signed_rotation == pytest.approx(-38.6598, abs=1e-3)
    finally:
        window.close()


def test_image_level_drag_line_sets_rotation_and_angle_overlay(qapp):
    window = ICCRawMainWindow()
    try:
        window._original_linear = gui_module.np.zeros((100, 100, 3), dtype=gui_module.np.float32)
        window.image_result_single.setFixedSize(200, 200)
        window.image_result_single.set_rgb_u8_image(gui_module.np.zeros((100, 100, 3), dtype=gui_module.np.uint8))
        window.show()
        qapp.processEvents()

        window._start_image_level_tool("horizontal")
        assert window.image_result_single._line_selection_enabled is True
        QtTest.QTest.mousePress(window.image_result_single, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, QtCore.QPoint(20, 20))
        QtTest.QTest.mouseMove(window.image_result_single, QtCore.QPoint(120, 100))
        qapp.processEvents()

        assert window.image_result_single._level_line_angle_text() == "H +38.66 grados"
        QtTest.QTest.mouseRelease(window.image_result_single, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, QtCore.QPoint(120, 100))
        qapp.processEvents()

        signed_rotation = ((float(window._viewer_rotation) + 180.0) % 360.0) - 180.0
        assert signed_rotation == pytest.approx(-38.6598, abs=1e-3)
        assert window._image_level_selection_active is False
        assert window.image_result_single._line_selection_enabled is False
    finally:
        window.close()


def test_image_crop_reprojects_when_display_resolution_changes(qapp):
    window = ICCRawMainWindow()
    try:
        window.image_result_single.set_rgb_u8_image(gui_module.np.zeros((120, 160, 3), dtype=gui_module.np.uint8))
        window._original_linear = gui_module.np.zeros((120, 160, 3), dtype=gui_module.np.float32)
        window._on_image_crop_selected(10, 20, 50, 40)
        assert window.image_result_single.view_crop_rect() == (10, 20, 50, 40)

        window.image_result_single.set_rgb_u8_image(gui_module.np.zeros((240, 320, 3), dtype=gui_module.np.uint8))
        window._sync_image_tool_overlays()

        assert window.image_result_single.view_crop_rect() == (20, 40, 100, 80)
    finally:
        window.close()


def test_zoom_100_keeps_crop_after_full_detail_replaces_preview(qapp):
    window = ICCRawMainWindow()
    try:
        window.image_result_single.setFixedSize(200, 200)
        window.image_result_single.set_rgb_u8_image(gui_module.np.zeros((100, 100, 3), dtype=gui_module.np.uint8))
        window._original_linear = gui_module.np.zeros((100, 100, 3), dtype=gui_module.np.float32)
        window._on_image_crop_selected(10, 10, 50, 40)

        window._viewer_zoom = window.image_result_single.view_zoom_for_display_scale(1.0)
        window._viewer_real_pixel_sync_pending = True
        window._loaded_preview_max_side_request = 0
        window._loaded_preview_fast_raw = False
        window._sync_viewer_transform()

        window._set_result_display_u8(
            gui_module.np.zeros((200, 200, 3), dtype=gui_module.np.uint8),
            compare_enabled=False,
            update_histogram=False,
        )

        assert window.image_result_single.view_crop_rect() == (20, 20, 100, 80)
        assert window.image_result_single.current_display_scale() == pytest.approx(1.0)
        assert window._viewer_real_pixel_sync_pending is False
    finally:
        window.close()


def test_mtf_roi_overlay_remains_visible_after_visual_crop(monkeypatch, qapp):
    window = ICCRawMainWindow()
    try:
        window.image_result_single.set_rgb_u8_image(gui_module.np.zeros((100, 100, 3), dtype=gui_module.np.uint8))
        window._image_crop_rect = (10, 10, 80, 80)
        window._image_crop_base_size = (100, 100)
        window._image_crop_normalized_rect = (0.1, 0.1, 0.8, 0.8)
        window._mtf_roi = (20, 20, 30, 30)
        monkeypatch.setattr(window, "_mtf_roi_overlay_should_be_visible", lambda: True)

        window._sync_image_tool_overlays()

        assert window.image_result_single.view_crop_rect() == (10, 10, 80, 80)
        assert window.image_result_single._roi_rect == pytest.approx((20, 20, 30, 30))
        assert window.image_result_single._roi_label == "MTF"
    finally:
        window.close()


def test_edit_menu_undo_redo_tracks_adjustment_changes(qapp):
    window = ICCRawMainWindow()
    try:
        window._initialize_edit_history()
        initial = window.slider_brightness.value()

        window.slider_brightness.setValue(35)
        window._on_slider_release()

        assert window.slider_brightness.value() == 35
        assert window.action_edit_undo.isEnabled() is True

        window._edit_undo()
        assert window.slider_brightness.value() == initial
        assert window.action_edit_redo.isEnabled() is True

        window._edit_redo()
        assert window.slider_brightness.value() == 35
    finally:
        window.close()


def test_edit_clear_adjustments_resets_recipe_render_detail_and_viewer(qapp):
    window = ICCRawMainWindow()
    try:
        window._initialize_edit_history()
        window.slider_brightness.setValue(25)
        window.slider_sharpen.setValue(40)
        window._image_crop_rect = (10, 20, 30, 40)
        window._viewer_rotation = 7.5
        window._sync_viewer_transform()
        window._sync_image_tool_overlays()
        window._push_edit_history_snapshot("test_changes")

        window._edit_clear_adjustments()

        assert window.slider_brightness.value() == 0
        assert window.slider_sharpen.value() == 0
        assert window._image_crop_rect is None
        assert float(window._viewer_rotation) == pytest.approx(0.0)
        assert window.action_edit_undo.isEnabled() is True

        window._edit_undo()
        assert window.slider_brightness.value() == 25
        assert window.slider_sharpen.value() == 40
        assert window._image_crop_rect == (10, 20, 30, 40)
        assert float(window._viewer_rotation) == pytest.approx(7.5)
    finally:
        window.close()


def test_edit_undo_crop_only_does_not_force_preview_refresh(qapp):
    window = ICCRawMainWindow()
    try:
        window._original_linear = gui_module.np.zeros((100, 120, 3), dtype=gui_module.np.float32)
        window._current_result_display_u8 = gui_module.np.zeros((100, 120, 3), dtype=gui_module.np.uint8)
        window._initialize_edit_history()

        calls: list[bool] = []
        window._refresh_preview = lambda *args, **kwargs: calls.append(bool(kwargs.get("force_final")))

        window._on_image_crop_selected(10, 12, 40, 30)
        assert window._image_crop_rect == (10, 12, 40, 30)

        window._edit_undo()

        assert window._image_crop_rect is None
        assert calls == []
    finally:
        window.close()


def test_edit_menu_shortcuts_are_registered(qapp):
    window = ICCRawMainWindow()
    try:
        assert window.action_edit_undo.shortcut().toString() == "Ctrl+Z"
        assert window.action_edit_redo.shortcut().toString() == "Ctrl+Y"
    finally:
        window.close()


def test_viewer_zoom_100_requests_full_detail_for_raw(tmp_path: Path, monkeypatch, qapp):
    raw = tmp_path / "capture.NEF"
    raw.write_bytes(b"raw")
    window = ICCRawMainWindow()
    try:
        calls: list[dict[str, object]] = []
        window._selected_file = raw
        window._original_linear = gui_module.np.zeros((200, 400, 3), dtype=gui_module.np.float32)
        window._loaded_preview_fast_raw = False
        window._loaded_preview_max_side_request = 2600
        window.image_result_single.setFixedSize(200, 100)
        window.image_result_single.set_rgb_u8_image(
            gui_module.np.zeros((200, 400, 3), dtype=gui_module.np.uint8)
        )
        monkeypatch.setattr(window, "_on_load_selected", lambda *args, **kwargs: calls.append(dict(kwargs)))

        window._viewer_zoom_100()

        assert window.viewer_zoom_label.text() == "100%"
        assert window._viewer_full_detail_requested is True
        assert window._effective_preview_max_side() == 0
        assert calls == [{"show_message": False}]
    finally:
        window.close()


def test_viewer_zoom_100_realigns_after_full_detail_replaces_preview(tmp_path: Path, qapp):
    raw = tmp_path / "capture.NEF"
    raw.write_bytes(b"raw")
    window = ICCRawMainWindow()
    try:
        window._selected_file = raw
        window.image_result_single.setFixedSize(200, 100)
        window.image_result_single.set_rgb_u8_image(
            gui_module.np.zeros((200, 400, 3), dtype=gui_module.np.uint8)
        )
        window._viewer_zoom_100()

        assert window.image_result_single.current_display_scale() == pytest.approx(1.0)

        window._loaded_preview_fast_raw = False
        window._loaded_preview_max_side_request = 0
        window._set_result_display_u8(
            gui_module.np.zeros((400, 800, 3), dtype=gui_module.np.uint8),
            compare_enabled=False,
        )

        assert window.viewer_zoom_label.text() == "100%"
        assert window.image_result_single.current_display_scale() == pytest.approx(1.0)
    finally:
        window.close()


def test_viewer_zoom_above_100_is_not_reset_by_preview_update(qapp):
    window = ICCRawMainWindow()
    try:
        window._loaded_preview_fast_raw = False
        window._loaded_preview_max_side_request = 0
        window.image_result_single.setFixedSize(200, 100)
        window.image_result_single.set_rgb_u8_image(
            gui_module.np.zeros((200, 400, 3), dtype=gui_module.np.uint8)
        )

        window._viewer_zoom_100()
        window._viewer_zoom_in()
        assert window.viewer_zoom_label.text() == "125%"

        window._set_result_display_u8(
            gui_module.np.zeros((200, 400, 3), dtype=gui_module.np.uint8),
            compare_enabled=False,
        )

        assert window.viewer_zoom_label.text() == "125%"
        assert window.image_result_single.current_display_scale() == pytest.approx(1.25)
    finally:
        window.close()


def test_panel_zoom_to_real_scale_requests_full_detail_for_raw(tmp_path: Path, monkeypatch, qapp):
    raw = tmp_path / "capture.NEF"
    raw.write_bytes(b"raw")
    window = ICCRawMainWindow()
    try:
        calls: list[dict[str, object]] = []
        window._selected_file = raw
        window._original_linear = gui_module.np.zeros((200, 400, 3), dtype=gui_module.np.float32)
        window._loaded_preview_fast_raw = False
        window._loaded_preview_max_side_request = 2600
        window.image_result_single.setFixedSize(200, 100)
        window.image_result_single.set_rgb_u8_image(
            gui_module.np.zeros((200, 400, 3), dtype=gui_module.np.uint8)
        )
        monkeypatch.setattr(window, "_on_load_selected", lambda *args, **kwargs: calls.append(dict(kwargs)))

        window.image_result_single.set_view_transform(zoom=2.0, rotation=0)

        assert window.viewer_zoom_label.text() == "100%"
        assert window._viewer_full_detail_requested is True
        assert window._effective_preview_max_side() == 0
        assert calls == [{"show_message": False}]
    finally:
        window.close()


def test_precache_selected_preview_only_uses_current_raw(tmp_path: Path, monkeypatch, qapp):
    raw_a = tmp_path / "a.NEF"
    raw_b = tmp_path / "b.NEF"
    raw_a.write_bytes(b"a")
    raw_b.write_bytes(b"b")
    window = ICCRawMainWindow()
    try:
        captured: dict[str, object] = {}
        window._selected_file = raw_a
        window._file_list_paths = lambda: [raw_a, raw_b]

        def fake_start(files, *, full_resolution, scope_label=None):
            captured["files"] = list(files)
            captured["full_resolution"] = bool(full_resolution)
            captured["scope_label"] = scope_label

        monkeypatch.setattr(window, "_start_precache_visible_previews", fake_start)

        window._on_precache_selected_preview()

        assert captured["files"] == [raw_a]
        assert captured["full_resolution"] is True
        assert captured["scope_label"]
    finally:
        window.close()


def test_full_detail_request_does_not_accept_reduced_hq_preview(tmp_path: Path, monkeypatch, qapp):
    raw = tmp_path / "capture.NEF"
    raw.write_bytes(b"raw")
    window = ICCRawMainWindow()
    try:
        queued: list[tuple] = []
        window._selected_file = raw
        recipe = window._build_effective_recipe()
        if raw.suffix.lower() in gui_module.RAW_EXTENSIONS:
            recipe.demosaic_algorithm = window._balanced_preview_demosaic()
        window._original_linear = gui_module.np.zeros((1732, 2600, 3), dtype=gui_module.np.float32)
        window._loaded_preview_base_signature = window._preview_base_signature(selected=raw, recipe=recipe)
        window._last_loaded_preview_key = "loaded-reduced-hq"
        window._loaded_preview_fast_raw = False
        window._loaded_preview_max_side_request = 2600
        window._viewer_full_detail_requested = True
        monkeypatch.setattr(window, "_queue_preview_load_request", lambda request: queued.append(request))

        window._on_load_selected(show_message=False)

        assert len(queued) == 1
        _selected, _recipe, fast_raw, max_preview_side, _cache_key, _input_profile_path = queued[0]
        assert fast_raw is False
        assert max_preview_side == 0
    finally:
        window.close()


def test_standard_output_space_preview_keeps_source_profile_for_monitor_conversion(qapp):
    window = ICCRawMainWindow()
    try:
        recipe = Recipe(output_space="prophoto_rgb")

        source_profile = window._source_profile_for_preview_recipe(recipe)

        assert source_profile is not None
        assert source_profile.exists()
        assert source_profile.suffix.lower() in {".icc", ".icm"}
    finally:
        window.close()


def test_color_managed_preview_recipe_defaults_unprofiled_camera_rgb_to_prophoto(qapp):
    window = ICCRawMainWindow()
    try:
        recipe = window._color_managed_preview_recipe(
            Recipe(output_space="scene_linear_camera_rgb", output_linear=True)
        )
        source_profile = window._source_profile_for_preview_recipe(recipe)

        assert recipe.output_space == "prophoto_rgb"
        assert recipe.output_linear is False
        assert source_profile is not None
        assert source_profile.exists()
    finally:
        window.close()


def test_source_profile_for_preview_rejects_unmanaged_recipe(qapp):
    window = ICCRawMainWindow()
    try:
        with pytest.raises(RuntimeError, match="sin perfil ICC de entrada"):
            window._source_profile_for_preview_recipe(Recipe(output_space="scene_linear_camera_rgb"))
    finally:
        window.close()


def test_preview_load_uses_color_managed_recipe_without_session_icc(tmp_path: Path, monkeypatch, qapp):
    raw = tmp_path / "capture.NEF"
    raw.write_bytes(b"raw")
    window = ICCRawMainWindow()
    try:
        queued: list[tuple] = []
        window._selected_file = raw
        monkeypatch.setattr(window, "_queue_preview_load_request", lambda request: queued.append(request))

        window._on_load_selected(show_message=False)

        assert len(queued) == 1
        recipe = queued[0][1]
        assert recipe.output_space == "prophoto_rgb"
        assert recipe.output_linear is False
    finally:
        window.close()


def test_session_icc_preview_never_uses_standard_srgb_route(tmp_path: Path, qapp, monkeypatch):
    window = ICCRawMainWindow()
    try:
        profile = tmp_path / "source.icc"
        profile.write_bytes(ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes())
        image = gui_module.np.full((24, 32, 3), 0.25, dtype=gui_module.np.float32)
        expected = gui_module.np.full((24, 32, 3), 64, dtype=gui_module.np.uint8)
        calls: list[tuple[Path, Path | None]] = []
        window._original_linear = image
        window._last_loaded_preview_key = "profiled-preview"
        monkeypatch.setattr(window, "_build_effective_recipe", lambda: Recipe(output_space="prophoto_rgb"))
        monkeypatch.setattr(window, "_active_session_icc_for_settings", lambda: profile)
        monkeypatch.setattr(
            preview_render_module,
            "standard_profile_to_srgb_display",
            lambda *_args, **_kwargs: pytest.fail("profiled preview must not route through standard sRGB display"),
        )

        def fake_profiled_float_to_display_u8(_image, source_profile, monitor_profile):
            calls.append((Path(source_profile), monitor_profile))
            return expected

        monkeypatch.setattr(preview_render_module, "profiled_float_to_display_u8", fake_profiled_float_to_display_u8)
        monkeypatch.setattr(window, "_profiled_display_u8_for_screen", lambda *_args, **_kwargs: expected)

        window._refresh_preview(force_final=True)

        assert calls
        assert all(source.suffix.lower() in {".icc", ".icm"} for source, _monitor in calls)
        assert gui_module.np.array_equal(window._current_result_display_u8, expected)
    finally:
        window.close()


def test_profiled_interactive_render_never_uses_standard_srgb_route(tmp_path: Path, qapp, monkeypatch):
    window = ICCRawMainWindow()
    try:
        profile = tmp_path / "source.icc"
        profile.write_bytes(ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes())
        image = gui_module.np.full((64, 80, 3), 0.25, dtype=gui_module.np.float32)
        monkeypatch.setattr(
            preview_render_module,
            "standard_profile_to_srgb_u8_display",
            lambda *_args, **_kwargs: pytest.fail("profiled interactive preview must not route through standard sRGB"),
        )

        _srgb, display = window._render_interactive_viewport_parallel(
            image,
            {"brightness_ev": 0.2},
            output_space="prophoto_rgb",
            source_profile=profile,
            monitor_profile=None,
            include_srgb_patch=False,
            workers=1,
        )

        assert display.shape == image.shape
    finally:
        window.close()


def test_viewer_zoom_actions_use_magnifier_icons_and_shortcuts(qapp):
    window = ICCRawMainWindow()
    try:
        shortcuts_in = {shortcut.toString() for shortcut in window.action_viewer_zoom_in.shortcuts()}
        shortcuts_out = {shortcut.toString() for shortcut in window.action_viewer_zoom_out.shortcuts()}

        assert shortcuts_in & {"Ctrl++", "Ctrl+="}
        assert "Ctrl+-" in shortcuts_out
        assert not window.action_viewer_zoom_in.icon().isNull()
        assert not window.action_viewer_zoom_out.icon().isNull()
    finally:
        window.close()


def test_space_bar_enables_viewer_hand_pan_cursor(qapp):
    window = ICCRawMainWindow()
    try:
        image = gui_module.np.zeros((200, 400, 3), dtype=gui_module.np.uint8)
        window.image_result_single.setFixedSize(200, 100)
        window.image_result_single.set_rgb_u8_image(image)
        window._viewer_fit()

        assert window.image_result_single.cursor().shape() != QtCore.Qt.OpenHandCursor
        window._set_viewer_space_pan_active(True)
        assert window.image_result_single.cursor().shape() == QtCore.Qt.OpenHandCursor
        window._set_viewer_space_pan_active(False)
        assert window.image_result_single.cursor().shape() != QtCore.Qt.OpenHandCursor
    finally:
        window.close()


def test_thumbnail_size_control_resizes_file_list(qapp):
    window = ICCRawMainWindow()
    try:
        assert window.file_list.flow() == QtWidgets.QListView.LeftToRight
        assert not window.file_list.isWrapping()
        assert window.file_list.horizontalScrollBarPolicy() == QtCore.Qt.ScrollBarAsNeeded
        assert window.file_list.verticalScrollBarPolicy() == QtCore.Qt.ScrollBarAlwaysOff
        assert not window.file_list.uniformItemSizes()
        window.thumbnail_size_slider.setValue(180)
        assert window.file_list.iconSize().width() == 180
        assert not window.file_list.gridSize().isValid()
        assert int(window._settings.value("view/thumbnail_size")) == 180
    finally:
        window.close()


def test_thumbnail_icon_uses_image_aspect_instead_of_square_canvas(tmp_path: Path, qapp):
    image_path = tmp_path / "landscape.png"
    window = ICCRawMainWindow()
    try:
        window._apply_thumbnail_size(120)
        base_icon = window._icon_from_thumbnail_array(
            gui_module.np.full((40, 120, 3), 128, dtype=gui_module.np.uint8),
            target_size=QtCore.QSize(120, 120),
        )
        base_pixmap = base_icon.pixmap(QtCore.QSize(120, 120))
        assert base_pixmap.width() == 120
        assert base_pixmap.height() == 40

        display_icon = window._display_icon_for_path(image_path, base_icon)
        display_pixmap = display_icon.pixmap(window.file_list.iconSize())
        assert display_pixmap.width() == 120
        assert display_pixmap.height() == 40

        item = QtWidgets.QListWidgetItem("")
        window._set_file_item_display_icon(item, image_path, base_icon)
        assert item.sizeHint().width() == 124
        assert item.sizeHint().height() == 44
    finally:
        window.close()


def test_thumbnail_resize_keeps_cache_and_existing_icons(tmp_path: Path, qapp):
    image_path = tmp_path / "patch.png"
    Image.new("RGB", (96, 48), (20, 120, 220)).save(image_path)

    window = ICCRawMainWindow()
    try:
        assert window._thumbnail_cache_key(image_path, 72) == window._thumbnail_cache_key(image_path, 180)

        def fail_placeholder_reset():
            raise AssertionError("thumbnail resize must keep existing preview icons")

        window._set_file_list_placeholder_icons = fail_placeholder_reset
        window._on_thumbnail_size_changed(180)
        assert window.file_list.iconSize().width() == 180
    finally:
        window.close()


def test_legacy_raw_directory_selection_maps_to_new_org_directory(tmp_path: Path, qapp):
    root = tmp_path / "project"
    raw_dir = root / "01_ORG"
    raw_dir.mkdir(parents=True)
    (root / "00_configuraciones").mkdir()
    (root / "02_DRV").mkdir()
    raw_path = raw_dir / "capture.NEF"
    raw_path.write_bytes(b"raw")

    window = ICCRawMainWindow()
    try:
        window._active_session_root = root
        window._set_current_directory(root / "raw")

        assert window._current_dir == raw_dir.resolve()
        assert window.file_list.count() == 1
        assert Path(window.file_list.item(0).data(QtCore.Qt.UserRole)) == raw_path.resolve()
    finally:
        window.close()


def test_project_root_selection_opens_org_directory_for_browsing(tmp_path: Path, qapp):
    root = tmp_path / "project"
    raw_dir = root / "01_ORG"
    raw_dir.mkdir(parents=True)
    (root / "00_configuraciones").mkdir()
    (root / "02_DRV").mkdir()
    raw_path = raw_dir / "capture.NEF"
    raw_path.write_bytes(b"raw")

    window = ICCRawMainWindow()
    try:
        window._set_current_directory(root)

        assert window._current_dir == raw_dir.resolve()
        assert window.file_list.count() == 1
        assert Path(window.file_list.item(0).data(QtCore.Qt.UserRole)) == raw_path.resolve()
    finally:
        window.close()


def test_use_current_dir_as_session_root_promotes_org_directory_to_project_root(tmp_path: Path, qapp):
    root = tmp_path / "project"
    raw_dir = root / "01_ORG"
    raw_dir.mkdir(parents=True)
    (root / "00_configuraciones").mkdir()
    (root / "02_DRV").mkdir()

    window = ICCRawMainWindow()
    try:
        window._set_current_directory(raw_dir)
        window._use_current_dir_as_session_root()

        assert Path(window.session_root_path.text()) == root.resolve()
        assert window.session_name_edit.text() == root.name
        assert Path(window.session_dir_raw.text()) == root.resolve() / "01_ORG"
    finally:
        window.close()


def test_legacy_raw_thumbnail_item_maps_to_existing_org_file(tmp_path: Path, qapp):
    root = tmp_path / "project"
    raw_dir = root / "01_ORG"
    raw_dir.mkdir(parents=True)
    (root / "00_configuraciones").mkdir()
    (root / "02_DRV").mkdir()
    raw_path = raw_dir / "capture.NEF"
    raw_path.write_bytes(b"raw")

    window = ICCRawMainWindow()
    try:
        window._active_session_root = root
        stale_path = root / "raw" / raw_path.name
        item = QtWidgets.QListWidgetItem(raw_path.name)
        item.setData(QtCore.Qt.UserRole, str(stale_path))
        window.file_list.addItem(item)
        item.setSelected(True)
        window.file_list.setCurrentItem(item)
        window._on_file_selection_changed()
        window._selection_load_timer.stop()
        window._metadata_timer.stop()

        assert window._selected_file == raw_path.resolve()
        assert Path(item.data(QtCore.Qt.UserRole)) == raw_path.resolve()
        assert str(raw_path) in window.selected_file_label.text()
    finally:
        window.close()


def test_image_thumbnail_payload_uses_real_preview(tmp_path: Path, qapp):
    image_path = tmp_path / "patch.png"
    Image.new("RGB", (96, 48), (20, 120, 220)).save(image_path)

    payloads = ICCRawMainWindow._build_thumbnail_payloads([image_path], 64)

    assert len(payloads) == 1
    raw_path, key, rgb = payloads[0]
    assert raw_path == str(image_path)
    assert str(image_path) in key
    assert rgb.dtype.name == "uint8"
    assert max(rgb.shape[:2]) <= gui_module.MAX_THUMBNAIL_SIZE
    assert rgb.shape[2] == 3


def test_raw_thumbnail_payload_skips_raw_decode_during_folder_browsing(tmp_path: Path, monkeypatch, qapp):
    import probraw.ui.window.browser as browser_module

    raw_path = tmp_path / "capture.NEF"
    raw_path.write_bytes(b"not a real raw but enough for the thumbnail test")

    monkeypatch.setattr(browser_module, "external_tool_path", lambda _name: None)
    monkeypatch.setattr(
        gui_module,
        "develop_image_array",
        lambda _path, _recipe, half_size=False: pytest.fail(
            "RAW thumbnails must not demosaic during folder browsing"
        ),
    )

    payloads = ICCRawMainWindow._build_thumbnail_payloads([raw_path], 64)

    assert payloads == []


def test_raw_thumbnail_payload_uses_exiftool_embedded_preview(tmp_path: Path, monkeypatch, qapp):
    import probraw.ui.window.browser as browser_module

    raw_path = tmp_path / "capture.NEF"
    raw_path.write_bytes(b"not a real raw but enough for the thumbnail test")
    preview_path = tmp_path / "embedded.jpg"
    Image.new("RGB", (160, 90), (20, 120, 220)).save(preview_path, format="JPEG")
    preview_bytes = preview_path.read_bytes()
    calls: list[list[str]] = []

    class Proc:
        returncode = 0
        stdout = preview_bytes

    def fake_run_external(cmd, **_kwargs):
        calls.append([str(part) for part in cmd])
        return Proc()

    monkeypatch.setattr(browser_module, "external_tool_path", lambda name: "exiftool" if name == "exiftool" else None)
    monkeypatch.setattr(browser_module, "run_external", fake_run_external)
    monkeypatch.setattr(
        gui_module,
        "develop_image_array",
        lambda _path, _recipe, half_size=False: pytest.fail(
            "RAW thumbnails must not demosaic during folder browsing"
        ),
    )

    payloads = ICCRawMainWindow._build_thumbnail_payloads([raw_path], 64)

    assert len(payloads) == 1
    raw_path_text, key, rgb = payloads[0]
    assert raw_path_text == str(raw_path)
    assert str(raw_path) in key
    assert calls[0][1:3] == ["-b", "-PreviewImage"]
    assert rgb.dtype.name == "uint8"
    assert max(rgb.shape[:2]) <= gui_module.MAX_THUMBNAIL_SIZE
    assert rgb.shape[2] == 3


def test_thumbnail_disk_cache_restores_icon(tmp_path: Path, qapp):
    window = ICCRawMainWindow()
    try:
        window._disk_cache_dirs = lambda _path=None, _kind="thumbnails": [tmp_path / "thumb-cache"]
        key = "example|123|thumb-v2"
        rgb = gui_module.np.full((24, 16, 3), (20, 120, 220), dtype=gui_module.np.uint8)

        window._write_thumbnail_to_disk_cache(key, rgb)
        window._image_thumb_cache.clear()

        icon = window._cached_thumbnail_icon(key)

        assert icon is not None
        assert not icon.pixmap(16, 16).isNull()
        assert key in window._image_thumb_cache
    finally:
        window.close()


def test_session_thumbnail_cache_uses_relative_project_key(tmp_path: Path, qapp):
    root = tmp_path / "session"
    raw_path = root / "01_ORG" / "capture.NEF"
    raw_path.parent.mkdir(parents=True)
    raw_path.write_bytes(b"raw")

    window = ICCRawMainWindow()
    try:
        window._active_session_root = root.resolve()
        key = window._thumbnail_cache_key(raw_path, 64)
        rgb = gui_module.np.full((24, 16, 3), (20, 120, 220), dtype=gui_module.np.uint8)

        window._write_thumbnail_to_disk_cache(key, rgb, path=raw_path)
        window._image_thumb_cache.clear()
        icon = window._cached_thumbnail_icon(key, path=raw_path)

        assert key.startswith("session:01_ORG/capture.NEF|")
        assert icon is not None
        assert list((root / "00_configuraciones" / "work" / "cache" / "thumbnails").glob("*/*.png"))
    finally:
        window.close()


def test_session_preview_cache_survives_memory_clear(tmp_path: Path, qapp):
    root = tmp_path / "session"
    raw_path = root / "01_ORG" / "capture.NEF"
    raw_path.parent.mkdir(parents=True)
    raw_path.write_bytes(b"raw")

    window = ICCRawMainWindow()
    try:
        window._active_session_root = root.resolve()
        key = window._preview_cache_key(
            selected=raw_path,
            recipe=Recipe(),
            fast_raw=True,
            max_preview_side=900,
        )
        image = gui_module.np.linspace(0.0, 1.0, 8 * 6 * 3, dtype=gui_module.np.float32).reshape(8, 6, 3)

        window._cache_preview_image(key, image, selected=raw_path)
        window._preview_cache.clear()
        window._preview_cache_order.clear()

        restored = window._cached_preview_image(key, selected=raw_path)

        assert key.startswith("session:01_ORG/capture.NEF|")
        assert restored is not None
        assert gui_module.np.allclose(restored, image)
        assert list((root / "00_configuraciones" / "work" / "cache" / "previews").glob("*/*.npy"))
    finally:
        window.close()


def test_preview_memory_cache_budget_scales_with_workstation_ram(qapp, monkeypatch):
    window = ICCRawMainWindow()
    try:
        monkeypatch.delenv("PROBRAW_PREVIEW_CACHE_MB", raising=False)
        monkeypatch.delenv("NEXORAW_PREVIEW_CACHE_MB", raising=False)
        monkeypatch.setattr(window, "_system_total_memory_bytes", lambda: 64 * 1024 * 1024 * 1024)

        assert window._preview_cache_max_bytes() >= 7 * 1024 * 1024 * 1024
    finally:
        window.close()


def test_preview_memory_cache_retains_large_full_resolution_source(qapp, monkeypatch):
    window = ICCRawMainWindow()
    try:
        image = gui_module.np.zeros((128, 256, 3), dtype=gui_module.np.float32)
        key = "large-full-resolution"
        monkeypatch.setattr(window, "_preview_cache_max_bytes", lambda: int(image.nbytes) + 1024)

        window._cache_preview_memory(key, image)

        assert key in window._preview_cache
        assert window._cached_preview_image(key) is not None
    finally:
        window.close()


def test_preview_disk_cache_restores_with_single_working_copy(tmp_path: Path, qapp):
    root = tmp_path / "session"
    raw_path = root / "01_ORG" / "capture.NEF"
    raw_path.parent.mkdir(parents=True)
    raw_path.write_bytes(b"raw")

    window = ICCRawMainWindow()
    try:
        window._active_session_root = root.resolve()
        key = window._preview_cache_key(
            selected=raw_path,
            recipe=Recipe(),
            fast_raw=False,
            max_preview_side=0,
        )
        image = gui_module.np.linspace(0.0, 1.0, 8 * 6 * 3, dtype=gui_module.np.float32).reshape(8, 6, 3)

        window._write_preview_to_disk_cache(key, image, selected=raw_path)
        restored = window._cached_preview_image(key, selected=raw_path)

        assert restored is not None
        assert window._preview_cache[key] is restored
    finally:
        window.close()


def test_preview_disk_cache_reuses_pyramid_level(tmp_path: Path, qapp):
    root = tmp_path / "session"
    raw_path = root / "01_ORG" / "capture.NEF"
    raw_path.parent.mkdir(parents=True)
    raw_path.write_bytes(b"raw")

    window = ICCRawMainWindow()
    try:
        window._active_session_root = root.resolve()
        recipe = Recipe()
        full_key = window._preview_cache_key(
            selected=raw_path,
            recipe=recipe,
            fast_raw=False,
            max_preview_side=0,
        )
        requested_key = window._preview_cache_key(
            selected=raw_path,
            recipe=recipe,
            fast_raw=False,
            max_preview_side=2600,
        )
        image = gui_module.np.linspace(0.0, 1.0, 5000 * 20 * 3, dtype=gui_module.np.float32).reshape(5000, 20, 3)

        window._write_preview_to_disk_cache(full_key, image, selected=raw_path)
        restored = window._cached_preview_image(requested_key, selected=raw_path)

        assert restored is not None
        assert max(restored.shape[:2]) == 2600
        assert requested_key in window._preview_cache
    finally:
        window.close()


def test_raw_embedded_preview_placeholder_updates_display_without_loaded_source(tmp_path: Path, monkeypatch, qapp):
    raw_path = tmp_path / "sample.NEF"
    raw_path.write_bytes(b"raw")
    rgb = gui_module.np.zeros((20, 30, 3), dtype=gui_module.np.uint8)
    rgb[..., 0] = 30
    rgb[..., 1] = 120
    rgb[..., 2] = 220
    thumbnail_orientation_flags: list[bool] = []

    def fake_extract_embedded_thumbnail(_path, max_side=0, apply_orientation=True):
        thumbnail_orientation_flags.append(bool(apply_orientation))
        return rgb

    monkeypatch.setattr(gui_module, "extract_embedded_thumbnail", fake_extract_embedded_thumbnail)

    window = ICCRawMainWindow()
    try:
        window._selected_file = raw_path

        window._queue_raw_embedded_preview(
            selected=raw_path,
            max_preview_side=700,
            final_cache_key="final-key",
        )

        assert window._original_linear is None
        assert window._current_result_display_u8 is not None
        assert gui_module.np.array_equal(window._current_result_colorimetric_u8, rgb)
        assert thumbnail_orientation_flags == [False]
        assert "embebida" in window.preview_analysis.toPlainText()
    finally:
        window.close()


def test_preview_load_new_request_preempts_inflight_load(tmp_path: Path, monkeypatch, qapp):
    raw_path = tmp_path / "sample.NEF"
    raw_path.write_bytes(b"raw")
    window = ICCRawMainWindow()
    try:
        request = (raw_path, Recipe(), False, 700, "new-key", None)
        preempted: list[tuple] = []
        window._preview_load_task_active = True
        window._preview_load_inflight_key = "old-key"
        monkeypatch.setattr(window, "_preempt_preview_load_task", lambda payload: preempted.append(payload))

        window._queue_preview_load_request(request)

        assert preempted == [request]
    finally:
        window.close()


def test_adjacent_preview_prefetch_paths_follow_file_list_order(tmp_path: Path, qapp):
    paths = [tmp_path / f"image_{index}.jpg" for index in range(4)]
    for path in paths:
        Image.new("RGB", (8, 8), (20, 120, 220)).save(path)
    window = ICCRawMainWindow()
    try:
        window.file_list.clear()
        for path in paths:
            item = QtWidgets.QListWidgetItem(path.name)
            item.setData(QtCore.Qt.UserRole, str(path))
            window.file_list.addItem(item)

        adjacent = window._adjacent_preview_prefetch_paths(paths[1], limit=2)

        assert adjacent == [paths[2], paths[0]]
    finally:
        window.close()


def test_display_preview_cache_roundtrips_arrays(qapp):
    window = ICCRawMainWindow()
    try:
        display = gui_module.np.full((6, 8, 3), 40, dtype=gui_module.np.uint8)
        colorimetric = gui_module.np.full((6, 8, 3), 80, dtype=gui_module.np.uint8)
        preview = gui_module.np.full((6, 8, 3), 0.25, dtype=gui_module.np.float32)

        window._cache_display_preview(
            "display-key",
            display_u8=display,
            colorimetric_u8=colorimetric,
            preview_srgb=preview,
            analysis_text="analysis",
        )
        restored = window._cached_display_preview("display-key")

        assert restored is not None
        restored_display, restored_colorimetric, restored_preview, analysis = restored
        assert gui_module.np.array_equal(restored_display, display)
        assert gui_module.np.array_equal(restored_colorimetric, colorimetric)
        assert gui_module.np.allclose(restored_preview, preview)
        assert analysis == "analysis"
    finally:
        window.close()


def test_raw_preview_uses_bounded_high_quality_mode(tmp_path: Path, monkeypatch, qapp):
    raw_path = tmp_path / "sample.NEF"
    raw_path.write_bytes(b"raw")
    captured: dict[str, object] = {}

    def fake_load_image_for_preview(_path, *, recipe, fast_raw, max_preview_side, input_profile_path=None, cache_dir=None):
        captured["demosaic"] = recipe.demosaic_algorithm
        captured["output_space"] = recipe.output_space
        captured["output_linear"] = recipe.output_linear
        captured["fast_raw"] = bool(fast_raw)
        captured["max_preview_side"] = int(max_preview_side)
        captured["input_profile_path"] = input_profile_path
        captured["cache_dir"] = cache_dir
        return gui_module.np.zeros((24, 32, 3), dtype=gui_module.np.float32), "ok"

    monkeypatch.setattr(gui_module, "load_image_for_preview", fake_load_image_for_preview)

    window = ICCRawMainWindow()
    try:
        window._start_background_task = lambda _label, task, on_success: on_success(task())
        window._selected_file = raw_path
        window._set_combo_data(window.combo_demosaic, "linear")
        window.chk_compare.setChecked(False)

        window._on_load_selected(show_message=False)

        assert captured["fast_raw"] is False
        assert captured["demosaic"] == "linear"
        assert captured["max_preview_side"] == gui_module.PREVIEW_AUTO_BASE_MAX_SIDE
        assert captured["output_space"] == "prophoto_rgb"
        assert captured["output_linear"] is False
        assert window._loaded_preview_source_profile_path is not None
        assert window._loaded_preview_source_profile_path.exists()
    finally:
        window.close()


def test_generic_output_preview_loads_bounded_with_recipe_demosaic(tmp_path: Path, monkeypatch, qapp):
    raw_path = tmp_path / "sample.NEF"
    raw_path.write_bytes(b"raw")
    calls: list[dict[str, object]] = []

    def fake_load_image_for_preview(_path, *, recipe, fast_raw, max_preview_side, input_profile_path=None, cache_dir=None):
        calls.append(
            {
                "demosaic": recipe.demosaic_algorithm,
                "output_space": recipe.output_space,
                "fast_raw": bool(fast_raw),
                "max_preview_side": int(max_preview_side),
                "input_profile_path": input_profile_path,
                "cache_dir": cache_dir,
            }
        )
        return gui_module.np.zeros((24, 32, 3), dtype=gui_module.np.float32), "ok"

    monkeypatch.setattr(gui_module, "load_image_for_preview", fake_load_image_for_preview)

    window = ICCRawMainWindow()
    try:
        window._selected_file = raw_path
        window._set_combo_text(window.combo_output_space, "prophoto_rgb")
        window._set_combo_data(window.combo_demosaic, "ahd")
        window.chk_compare.setChecked(False)

        window._on_load_selected(show_message=False)

        assert len(calls) == 1
        assert calls[0]["fast_raw"] is False
        assert calls[0]["max_preview_side"] == gui_module.PREVIEW_AUTO_BASE_MAX_SIDE
        assert calls[0]["demosaic"] == "ahd"
        assert calls[0]["output_space"] == "prophoto_rgb"
        assert calls[0]["input_profile_path"] is None
        assert window._loaded_preview_source_profile_path is not None
        assert window._loaded_preview_source_profile_path.exists()
    finally:
        window.close()


def test_compare_toggle_keeps_raw_preview_at_loaded_quality(tmp_path: Path, monkeypatch, qapp):
    raw_path = tmp_path / "sample.NEF"
    raw_path.write_bytes(b"raw")
    calls: list[dict[str, object]] = []

    def fake_load_image_for_preview(_path, *, recipe, fast_raw, max_preview_side, input_profile_path=None, cache_dir=None):
        _ = recipe
        assert input_profile_path is None
        assert cache_dir is not None
        calls.append({"fast_raw": bool(fast_raw), "max_preview_side": int(max_preview_side)})
        return gui_module.np.full((24, 32, 3), 0.5, dtype=gui_module.np.float32), "ok"

    monkeypatch.setattr(gui_module, "load_image_for_preview", fake_load_image_for_preview)

    window = ICCRawMainWindow()
    try:
        window._start_background_task = lambda _label, task, on_success: on_success(task())
        window._selected_file = raw_path
        window.chk_compare.setChecked(False)
        window._on_load_selected(show_message=False)
        assert calls[-1] == {"fast_raw": False, "max_preview_side": gui_module.PREVIEW_AUTO_BASE_MAX_SIDE}

        window.chk_compare.setChecked(True)
        qapp.processEvents()
        assert calls[-1] == {"fast_raw": False, "max_preview_side": gui_module.PREVIEW_AUTO_BASE_MAX_SIDE}
        assert f"ms={gui_module.PREVIEW_AUTO_BASE_MAX_SIDE}" in (window._last_loaded_preview_key or "")

        window.chk_compare.setChecked(False)
        qapp.processEvents()
        assert f"ms={gui_module.PREVIEW_AUTO_BASE_MAX_SIDE}" in (window._last_loaded_preview_key or "")
    finally:
        window.close()


def test_thumbnail_batch_limits_background_work(tmp_path: Path, qapp):
    window = ICCRawMainWindow()
    try:
        paths = []
        for index in range(gui_module.THUMBNAIL_BATCH_SIZE + 5):
            path = tmp_path / f"image_{index:02d}.png"
            path.write_bytes(b"placeholder")
            paths.append(path)

        batch = window._next_thumbnail_batch(paths, 64)

        assert len(batch) == gui_module.THUMBNAIL_BATCH_SIZE
        assert batch == paths[: gui_module.THUMBNAIL_BATCH_SIZE]
        assert window._thumbnail_scan_index == gui_module.THUMBNAIL_BATCH_SIZE
    finally:
        window.close()


def test_selected_color_reference_images_update_reference_label_without_profile_marker(tmp_path: Path, qapp):
    image_path = tmp_path / "reference.tiff"
    Image.new("RGB", (96, 48), (20, 120, 220)).save(image_path)

    window = ICCRawMainWindow()
    try:
        window._set_current_directory(tmp_path)
        base_icon = window._icon_from_thumbnail_array(
            gui_module.np.full((64, 64, 3), (48, 48, 48), dtype=gui_module.np.uint8)
        )
        window._image_thumb_cache[window._thumbnail_cache_key(image_path, 72)] = base_icon
        window._apply_cached_thumbnails([image_path], 72)

        item = window.file_list.item(0)
        item.setSelected(True)
        window.file_list.setCurrentItem(item)
        window._use_selected_files_as_profile_charts()

        assert window._profile_chart_files_or_none() == [image_path]
        assert "Referencias colorimétricas seleccionadas: 1" in window.profile_chart_selection_label.text()
        assert "Referencia colorimétrica seleccionada" in item.toolTip()

        pixmap = item.icon().pixmap(window.file_list.iconSize())
        image = pixmap.toImage().convertToFormat(QtGui.QImage.Format_RGB32)
        top = QtGui.QColor(image.pixel(image.width() // 2, 1))
        bottom = QtGui.QColor(image.pixel(image.width() // 2, image.height() - 2))
        assert not (top.blue() > 160 and top.red() < 120)
        assert not (bottom.blue() > 160 and bottom.red() < 120)
        assert not (bottom.green() > 160 and bottom.red() < 120 and bottom.blue() < 140)
    finally:
        window.close()


def test_manual_development_profile_is_saved_relative_to_session(tmp_path: Path, qapp):
    root = tmp_path / "session"
    payload = create_session(root, name="Sesion perfiles")

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        _activate_fake_session_icc(window, root)
        window.development_profile_name_edit.setText("Luz norte")
        window.spin_exposure.setValue(0.65)
        window.slider_brightness.setValue(12)

        window._save_current_development_profile()

        assert len(window._development_profiles) == 1
        profile = window._development_profiles[0]
        assert profile["id"] == "luz-norte"
        assert profile["recipe_path"] == "00_configuraciones/development_profiles/luz-norte/recipe.yml"
        assert profile["manifest_path"] == "00_configuraciones/development_profiles/luz-norte/development_profile.json"
        assert (root / profile["recipe_path"]).exists()
        assert (root / profile["manifest_path"]).exists()

        saved_state = load_session(root)["state"]
        assert saved_state["active_development_profile_id"] == "luz-norte"
        assert saved_state["development_profiles"][0]["id"] == "luz-norte"
    finally:
        window.close()


def test_manual_camera_rgb_profile_requires_active_icc(tmp_path: Path, monkeypatch, qapp):
    root = tmp_path / "session"
    payload = create_session(root, name="Sesion perfiles")
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "warning",
        lambda _parent, title, text: warnings.append((title, text)),
    )

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        window.development_profile_name_edit.setText("Sin ICC")

        window._save_current_development_profile()

        assert window._development_profiles == []
        assert warnings
        assert "RGB de cámara" in warnings[0][1]
    finally:
        window.close()


def test_manual_development_profile_can_use_generic_icc_without_chart(tmp_path: Path, monkeypatch, qapp):
    standard_profiles = tmp_path / "standard-profiles"
    standard_profiles.mkdir()
    (standard_profiles / "ProPhoto.icm").write_bytes(b"p" * 256)
    monkeypatch.setenv("PROBRAW_STANDARD_ICC_DIR", str(standard_profiles))
    root = tmp_path / "session"
    payload = create_session(root, name="Sesion sin carta")

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        window.development_profile_name_edit.setText("A ojo ProPhoto")
        index = window.development_output_space_combo.findData("prophoto_rgb")
        assert index >= 0
        window.development_output_space_combo.setCurrentIndex(index)
        window.spin_exposure.setValue(0.35)

        window._save_current_development_profile()

        profile = window._development_profiles[0]
        manifest = load_session(root)["state"]["development_profiles"][0]
        manifest_path = root / profile["manifest_path"]
        payload = gui_module.json.loads(manifest_path.read_text(encoding="utf-8"))
        assert payload["kind"] == "manual"
        assert payload["recipe"]["output_space"] == "prophoto_rgb"
        assert payload["recipe"]["output_linear"] is False
        assert payload["generic_output_space"] == "prophoto_rgb"
        assert payload["icc_profile_path"] == ""
        assert payload["output_icc_profile_path"] == "00_configuraciones/profiles/standard/ProPhoto.icm"
        assert (root / payload["output_icc_profile_path"]).exists()
        assert manifest["generic_output_space"] == "prophoto_rgb"
    finally:
        window.close()


def test_output_space_combo_synchronizes_linear_state_and_basic_selector(qapp):
    window = ICCRawMainWindow()
    try:
        window.combo_output_space.setCurrentText("srgb")
        assert window.development_output_space_combo.currentData() == "srgb"
        assert not window.check_output_linear.isChecked()
        assert window.combo_tone_curve.currentData() == "srgb"

        window.combo_output_space.setCurrentText("scene_linear_camera_rgb")
        assert window.development_output_space_combo.currentData() == "scene_linear_camera_rgb"
        assert window.check_output_linear.isChecked()
        assert window.combo_tone_curve.currentData() == "linear"

        window.combo_output_space.setCurrentText("prophoto_rgb")
        window.check_output_linear.setChecked(True)
        assert not window.check_output_linear.isChecked()
        assert window.combo_tone_curve.currentData() == "gamma"
    finally:
        window.close()


def test_output_space_change_reloads_raw_preview_source(tmp_path: Path, monkeypatch, qapp):
    root = tmp_path / "session"
    raw = root / "01_ORG" / "image.NEF"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"raw")
    payload = create_session(root, name="Sesion color")
    calls: list[dict[str, object]] = []

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        window._selected_file = raw
        window._original_linear = gui_module.np.zeros((12, 16, 3), dtype=gui_module.np.float32)
        window._last_loaded_preview_key = "old-preview"
        monkeypatch.setattr(window, "_on_load_selected", lambda *args, **kwargs: calls.append(dict(kwargs)))

        window.combo_output_space.blockSignals(True)
        window._set_combo_text(window.combo_output_space, "prophoto_rgb")
        window.combo_output_space.blockSignals(False)
        window._on_output_space_changed()

        assert calls == [{"show_message": False}]
        assert window._last_loaded_preview_key is None
        assert window.development_output_space_combo.currentData() == "prophoto_rgb"
    finally:
        window.close()


def test_generic_icc_selection_reloads_raw_preview_once(tmp_path: Path, monkeypatch, qapp):
    root = tmp_path / "session"
    raw = root / "01_ORG" / "image.NEF"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"raw")
    payload = create_session(root, name="Sesion color")
    calls: list[dict[str, object]] = []

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        window._selected_file = raw
        window._original_linear = gui_module.np.zeros((12, 16, 3), dtype=gui_module.np.float32)
        monkeypatch.setattr(window, "_on_load_selected", lambda *args, **kwargs: calls.append(dict(kwargs)))
        window.combo_generic_icc_space.blockSignals(True)
        window.combo_generic_icc_space.setCurrentIndex(window.combo_generic_icc_space.findData("prophoto_rgb"))
        window.combo_generic_icc_space.blockSignals(False)

        window._apply_generic_icc_workflow_to_controls()

        assert calls == [{"show_message": False}]
        assert window.combo_output_space.currentText().strip() == "prophoto_rgb"
        assert not window.check_output_linear.isChecked()
    finally:
        window.close()


def test_color_managed_preview_keeps_fast_initial_size_then_allows_export_parity(tmp_path: Path, monkeypatch, qapp):
    root = tmp_path / "session"
    payload = create_session(root, name="Sesion rendimiento")
    profile = root / "00_configuraciones" / "profiles" / "session.icc"
    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_bytes(b"fake profile" * 32)

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        window._original_linear = gui_module.np.zeros((3000, 4500, 3), dtype=gui_module.np.float32)
        monkeypatch.setattr(window, "_active_session_icc_for_settings", lambda: profile)

        assert window._preview_requires_max_quality()
        assert window._effective_preview_max_side() == gui_module.PREVIEW_AUTO_BASE_MAX_SIDE
        assert window._final_adjustment_preview_max_side() == gui_module.PREVIEW_FINAL_ADJUSTMENT_MAX_SIDE
        assert window._should_async_final_preview()

        window._preview_export_parity_requested = True
        assert window._effective_preview_max_side() == 0
        window._preview_export_parity_requested = False

        window.check_precision_detail_preview.setChecked(True)
        assert window._effective_preview_max_side() == gui_module.PREVIEW_AUTO_BASE_MAX_SIDE
        assert window._final_adjustment_preview_max_side() == gui_module.PREVIEW_FINAL_ADJUSTMENT_MAX_SIDE
        window._viewer_full_detail_requested = True
        assert window._effective_preview_max_side() == 0
        assert window._final_adjustment_preview_max_side() == 0
    finally:
        window.close()


def test_interactive_preview_source_uses_bounded_cache(qapp):
    window = ICCRawMainWindow()
    try:
        image = gui_module.np.linspace(0.0, 1.0, 900 * 1200 * 3, dtype=gui_module.np.float32).reshape((900, 1200, 3))

        first = window._interactive_preview_source(image, max_side_limit=300)
        second = window._interactive_preview_source(image, max_side_limit=300)
        third = window._interactive_preview_source(image, max_side_limit=240)

        assert first.shape == (225, 300, 3)
        assert second is first
        assert third.shape == (180, 240, 3)
        assert third is not first
    finally:
        window.close()


def test_interactive_refresh_uses_bounded_source_without_real_viewport(qapp, monkeypatch):
    window = ICCRawMainWindow()
    try:
        image = gui_module.np.zeros((900, 1400, 3), dtype=gui_module.np.float32)
        captured: dict[str, object] = {}
        window._original_linear = image
        window._last_loaded_preview_key = "full-res-source"
        window.slider_brightness.setSliderDown(True)

        def fake_queue(request):
            captured["request"] = request

        monkeypatch.setattr(window, "_queue_interactive_preview_request", fake_queue)

        window._refresh_preview()

        request = captured["request"]
        assert request[2] is image
        assert request[7] == PREVIEW_INTERACTIVE_TONAL_MAX_SIDE
        assert request[13] is None
        assert request[14] is True
        assert request[15] is True
    finally:
        window.slider_brightness.setSliderDown(False)
        window.close()


def test_interactive_refresh_queues_tone_curve_histogram_without_blocking_when_curve_disabled(qapp, monkeypatch):
    window = ICCRawMainWindow()
    try:
        values = gui_module.np.linspace(0.0, 0.8, 900 * 1400, dtype=gui_module.np.float32).reshape((900, 1400, 1))
        image = gui_module.np.repeat(values, 3, axis=2)
        captured: dict[str, object] = {}
        histogram_requests: list[tuple[str, gui_module.np.ndarray, dict[str, object], str]] = []
        window._original_linear = image
        window._last_loaded_preview_key = "live-histogram-source"
        window.slider_brightness.blockSignals(True)
        window.slider_brightness.setValue(100)
        window.slider_brightness.blockSignals(False)
        window.slider_brightness.setSliderDown(True)
        window.check_tone_curve_enabled.setChecked(False)

        monkeypatch.setattr(window, "_queue_interactive_preview_request", lambda request: captured.setdefault("request", request))
        monkeypatch.setattr(window, "_queue_tone_curve_histogram_request", lambda request: histogram_requests.append(request))
        monkeypatch.setattr(
            preview_render_module,
            "apply_render_adjustments",
            lambda *_args, **_kwargs: pytest.fail("interactive histogram must not render synchronously"),
        )

        window._refresh_preview()

        assert "request" in captured
        assert len(histogram_requests) == 1
        key, source, render_kwargs, channel = histogram_requests[0]
        assert source.shape[0] <= PREVIEW_INTERACTIVE_TONAL_MAX_SIDE
        assert source.shape[1] <= PREVIEW_INTERACTIVE_TONAL_MAX_SIDE
        assert render_kwargs["brightness_ev"] == pytest.approx(1.0)
        assert channel == "luminance"
        assert "bright=1.0000" in key
        assert f"source_max_side={PREVIEW_INTERACTIVE_TONAL_MAX_SIDE}" in key
    finally:
        window.slider_brightness.setSliderDown(False)
        window.close()


def test_interactive_refresh_uses_visible_viewport_rect_without_downscaling(qapp, monkeypatch):
    window = ICCRawMainWindow()
    try:
        image = gui_module.np.zeros((800, 1200, 3), dtype=gui_module.np.float32)
        display = gui_module.np.zeros((800, 1200, 3), dtype=gui_module.np.uint8)
        captured: dict[str, object] = {}
        window._original_linear = image
        window._preview_srgb = image.copy()
        window._current_result_display_u8 = display.copy()
        window._last_loaded_preview_key = "full-res-source"
        window.check_image_clip_overlay.setChecked(False)
        window.image_result_single.resize(240, 160)
        window.image_result_single.set_rgb_u8_image(display)
        window.image_result_single.set_view_transform(
            zoom=window.image_result_single.view_zoom_for_display_scale(1.0),
            rotation=0,
        )
        window.slider_brightness.setSliderDown(True)

        monkeypatch.setattr(window, "_queue_interactive_preview_request", lambda request: captured.setdefault("request", request))

        window._refresh_preview()

        request = captured["request"]
        assert request[2] is image
        assert request[7] == 0
        assert request[13] is not None
        x, y, w, h = request[13]
        assert 0 <= x < image.shape[1]
        assert 0 <= y < image.shape[0]
        assert 0 < w <= image.shape[1] - x
        assert 0 < h <= image.shape[0] - y
        assert w * h < image.shape[0] * image.shape[1]
        assert request[14] is True
        assert request[15] is False
    finally:
        window.slider_brightness.setSliderDown(False)
        window.close()


def test_detail_interactive_refresh_uses_real_pixel_viewport(qapp, monkeypatch):
    window = ICCRawMainWindow()
    try:
        image = gui_module.np.zeros((800, 1200, 3), dtype=gui_module.np.float32)
        display = gui_module.np.zeros((800, 1200, 3), dtype=gui_module.np.uint8)
        captured: dict[str, object] = {}
        window._original_linear = image
        window._preview_srgb = image.copy()
        window._current_result_display_u8 = display.copy()
        window._last_loaded_preview_key = "full-res-source"
        window.check_image_clip_overlay.setChecked(False)
        window.image_result_single.resize(240, 160)
        window.image_result_single.set_rgb_u8_image(display)
        window.image_result_single.set_view_transform(
            zoom=window.image_result_single.view_zoom_for_display_scale(1.0),
            rotation=0,
        )
        window.slider_sharpen.setSliderDown(True)

        monkeypatch.setattr(window, "_queue_interactive_preview_request", lambda request: captured.setdefault("request", request))

        window._refresh_preview()

        request = captured["request"]
        assert request[7] == 0
        assert request[8] is True
        assert request[13] is not None
        assert request[14] is True
        assert request[15] is False
    finally:
        window.slider_sharpen.setSliderDown(False)
        window.close()


def test_raw_cached_preview_uses_viewport_without_real_pixel_request(tmp_path: Path, qapp, monkeypatch):
    raw = tmp_path / "capture.NEF"
    raw.write_bytes(b"raw")
    window = ICCRawMainWindow()
    try:
        image = gui_module.np.zeros((800, 1200, 3), dtype=gui_module.np.float32)
        display = gui_module.np.zeros((800, 1200, 3), dtype=gui_module.np.uint8)
        captured: dict[str, object] = {}
        window._selected_file = raw
        window._loaded_preview_fast_raw = False
        window._loaded_preview_max_side_request = 2600
        window._original_linear = image
        window._preview_srgb = image.copy()
        window._current_result_display_u8 = display.copy()
        window._last_loaded_preview_key = "cached-raw-source"
        window.check_image_clip_overlay.setChecked(False)
        window.image_result_single.resize(240, 160)
        window.image_result_single.set_rgb_u8_image(display)
        window.image_result_single.set_view_transform(
            zoom=window.image_result_single.view_zoom_for_display_scale(1.0),
            rotation=0,
        )
        window.slider_brightness.setSliderDown(True)

        monkeypatch.setattr(window, "_queue_interactive_preview_request", lambda request: captured.setdefault("request", request))

        window._refresh_preview()

        request = captured["request"]
        assert request[7] == 0
        assert request[13] is not None
        assert request[14] is True
        assert request[15] is False
    finally:
        window.slider_brightness.setSliderDown(False)
        window.close()


def test_real_pixel_request_restores_full_source_when_display_is_proxy(qapp, monkeypatch):
    window = ICCRawMainWindow()
    try:
        image = gui_module.np.zeros((800, 1200, 3), dtype=gui_module.np.float32)
        proxy_display = gui_module.np.zeros((160, 240, 3), dtype=gui_module.np.uint8)
        captured: dict[str, object] = {}
        window._original_linear = image
        window._preview_srgb = image.copy()
        window._current_result_display_u8 = proxy_display.copy()
        window._last_loaded_preview_key = "full-source-with-proxy-display"
        window._viewer_full_detail_requested = True
        window.check_image_clip_overlay.setChecked(False)
        window.image_result_single.resize(240, 160)
        window.image_result_single.set_rgb_u8_image(proxy_display)
        window.slider_brightness.setSliderDown(True)

        monkeypatch.setattr(window, "_queue_interactive_preview_request", lambda request: captured.setdefault("request", request))

        window._refresh_preview()

        request = captured["request"]
        assert request[7] == 0
        assert request[13] is None
        assert request[14] is True
        assert request[15] is True
    finally:
        window.slider_brightness.setSliderDown(False)
        window.close()


def test_view_change_at_fit_schedules_proxy_refresh(qapp, monkeypatch):
    window = ICCRawMainWindow()
    try:
        calls: list[bool] = []
        window._original_linear = gui_module.np.zeros((800, 1200, 3), dtype=gui_module.np.float32)
        window._current_result_display_u8 = gui_module.np.zeros((800, 1200, 3), dtype=gui_module.np.uint8)
        monkeypatch.setattr(window, "_schedule_preview_refresh", lambda: calls.append(True))

        window._schedule_visible_viewport_preview_refresh(duration_ms=50)

        assert calls == [True]
        assert window._recent_preview_control_interaction_active()
    finally:
        window.close()


def test_interactive_refresh_uses_visible_viewport_rect_with_clip_overlay(qapp, monkeypatch):
    window = ICCRawMainWindow()
    try:
        image = gui_module.np.zeros((800, 1200, 3), dtype=gui_module.np.float32)
        display = gui_module.np.zeros((800, 1200, 3), dtype=gui_module.np.uint8)
        captured: dict[str, object] = {}
        window._original_linear = image
        window._preview_srgb = image.copy()
        window._current_result_display_u8 = display.copy()
        window._last_loaded_preview_key = "full-res-source"
        window.check_image_clip_overlay.setChecked(True)
        window.image_result_single.resize(240, 160)
        window.image_result_single.set_rgb_u8_image(display)
        window.image_result_single.set_view_transform(
            zoom=window.image_result_single.view_zoom_for_display_scale(1.0),
            rotation=0,
        )
        window.slider_brightness.setSliderDown(True)

        monkeypatch.setattr(window, "_queue_interactive_preview_request", lambda request: captured.setdefault("request", request))

        window._refresh_preview()

        request = captured["request"]
        assert request[13] is not None
        assert request[14] is True
        assert request[15] is True
    finally:
        window.slider_brightness.setSliderDown(False)
        window.close()


def test_region_preview_updates_clip_overlay_region(qapp):
    window = ICCRawMainWindow()
    try:
        base_display = gui_module.np.zeros((4, 5, 3), dtype=gui_module.np.uint8)
        window._preview_srgb = gui_module.np.zeros((4, 5, 3), dtype=gui_module.np.float32)
        window._current_result_display_u8 = base_display.copy()
        window._current_result_colorimetric_u8 = base_display.copy()
        window.check_image_clip_overlay.setChecked(True)
        window.image_result_single.set_rgb_u8_image(base_display)

        preview_patch = gui_module.np.asarray(
            [
                [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]],
                [[1.0, 0.0, 0.0], [0.5, 0.5, 0.5]],
            ],
            dtype=gui_module.np.float32,
        )
        display_patch = gui_module.np.round(preview_patch * 255).astype(gui_module.np.uint8)

        applied = window._apply_result_display_u8_region(
            display_patch,
            preview_patch,
            (1, 1, 2, 2),
            compare_enabled=False,
            bypass_profile=False,
        )

        overlay = window.image_result_single._clip_overlay_pixmap
        assert applied is True
        assert isinstance(overlay, QtGui.QImage)
        assert overlay.pixelIndex(1, 1) == 1
        assert overlay.pixelIndex(2, 1) == 2
        assert overlay.pixelIndex(1, 2) == 2
        assert overlay.pixelIndex(2, 2) == 0
    finally:
        window.close()


def test_region_preview_does_not_refresh_histogram_from_partial_patch(monkeypatch, qapp):
    window = ICCRawMainWindow()
    try:
        base_display = gui_module.np.zeros((4, 5, 3), dtype=gui_module.np.uint8)
        window._preview_srgb = gui_module.np.zeros((4, 5, 3), dtype=gui_module.np.float32)
        window._current_result_display_u8 = base_display.copy()
        window._current_result_colorimetric_u8 = base_display.copy()
        window.image_result_single.set_rgb_u8_image(base_display)
        calls: list[gui_module.np.ndarray] = []
        monkeypatch.setattr(
            window,
            "_update_viewer_histogram",
            lambda image: calls.append(gui_module.np.asarray(image).copy()),
        )

        preview_patch = gui_module.np.ones((2, 2, 3), dtype=gui_module.np.float32)
        display_patch = gui_module.np.full((2, 2, 3), 255, dtype=gui_module.np.uint8)

        applied = window._apply_result_display_u8_region(
            display_patch,
            preview_patch,
            (1, 1, 2, 2),
            compare_enabled=False,
            bypass_profile=False,
        )

        assert applied is True
        assert calls == []
    finally:
        window.close()


def test_viewer_histogram_source_uses_full_image_real_pixels(qapp):
    window = ICCRawMainWindow()
    try:
        image = gui_module.np.zeros((4, 4, 3), dtype=gui_module.np.float32)
        image[0, 0] = [1.0, 0.0, 0.0]
        image[3, 3] = [0.0, 0.0, 1.0]

        sample = window._viewer_histogram_full_source(image)
        rendered = window._render_viewer_histogram_u8(
            image,
            {},
            {},
            apply_detail=False,
            output_space="srgb",
            source_profile=None,
        )

        assert sample.shape == image.shape
        assert gui_module.np.array_equal(sample[0, 0], image[0, 0])
        assert gui_module.np.array_equal(sample[3, 3], image[3, 3])
        assert rendered is not None
        assert rendered.shape == image.shape
        assert int(rendered[0, 0, 0]) == 255
        assert int(rendered[3, 3, 2]) == 255
    finally:
        window.close()


def test_viewer_histogram_exact_render_honors_tone_curve_white_point(qapp):
    window = ICCRawMainWindow()
    try:
        values = gui_module.np.linspace(0.0, 1.0, 100 * 120, dtype=gui_module.np.float32).reshape((100, 120, 1))
        image = gui_module.np.repeat(values, 3, axis=2)
        render_kwargs = window._render_adjustment_kwargs_from_state(
            {
                "tone_curve_enabled": True,
                "tone_curve_points": [[0.0, 0.0], [1.0, 1.0]],
                "tone_curve_channel_points": {},
                "tone_curve_black_point": 0.0,
                "tone_curve_white_point": 0.877,
            }
        )

        rendered = window._render_viewer_histogram_u8(
            image,
            {},
            render_kwargs,
            apply_detail=False,
            output_space="srgb",
            source_profile=None,
        )
        window.viewer_histogram.set_image_u8(rendered)
        metrics = window.viewer_histogram.clip_metrics()

        assert metrics["highlight_any"] > 0.10
    finally:
        window.close()


def test_rgb_histogram_counts_all_pixels_without_sampling(qapp):
    widget = gui_module.RGBHistogramWidget()
    try:
        image = gui_module.np.zeros((600, 600, 3), dtype=gui_module.np.uint8)
        image[1, 1] = [255, 0, 0]

        widget.set_image_u8(image)

        metrics = widget.clip_metrics()
        assert metrics["highlight_r"] == pytest.approx(1.0 / float(600 * 600))
        assert widget._hist_r[255] > 0.0
    finally:
        widget.deleteLater()


def test_rgb_histogram_pending_state_is_cleared_by_new_image(qapp):
    widget = gui_module.RGBHistogramWidget()
    try:
        image = gui_module.np.zeros((8, 8, 3), dtype=gui_module.np.uint8)
        widget.set_image_u8(image)
        widget.set_pending("Actualizando...")

        assert widget._pending_label == "Actualizando..."

        widget.set_image_u8(image)

        assert widget._pending_label is None
    finally:
        widget.deleteLater()


def test_scheduling_exact_histogram_marks_current_histogram_as_pending(qapp):
    window = ICCRawMainWindow()
    try:
        window._original_linear = gui_module.np.zeros((8, 8, 3), dtype=gui_module.np.float32)
        window.viewer_histogram.set_image_u8(gui_module.np.zeros((8, 8, 3), dtype=gui_module.np.uint8))

        window._schedule_exact_histogram_refresh(delay_ms=1000)

        assert window.viewer_histogram._pending_label == "Actualizando..."
        assert "recalculando" in window.histogram_highlight_label.text().lower()
        window._exact_histogram_refresh_timer.stop()
    finally:
        window.close()


def test_preview_candidate_to_float_normalizes_u8(qapp):
    window = ICCRawMainWindow()
    try:
        patch = gui_module.np.asarray([[[0, 128, 255]]], dtype=gui_module.np.uint8)

        normalized = window._preview_candidate_to_float(patch)

        assert normalized.dtype == gui_module.np.float32
        assert normalized[0, 0, 0] == pytest.approx(0.0)
        assert normalized[0, 0, 1] == pytest.approx(128.0 / 255.0)
        assert normalized[0, 0, 2] == pytest.approx(1.0)
    finally:
        window.close()


def test_recent_render_control_change_uses_visible_viewport_even_without_slider_down(qapp, monkeypatch):
    window = ICCRawMainWindow()
    try:
        image = gui_module.np.zeros((800, 1200, 3), dtype=gui_module.np.float32)
        display = gui_module.np.zeros((800, 1200, 3), dtype=gui_module.np.uint8)
        captured: dict[str, object] = {}
        window._original_linear = image
        window._preview_srgb = image.copy()
        window._current_result_display_u8 = display.copy()
        window._last_loaded_preview_key = "full-res-source"
        window.check_image_clip_overlay.setChecked(False)
        window.image_result_single.resize(240, 160)
        window.image_result_single.set_rgb_u8_image(display)
        window.image_result_single.set_view_transform(
            zoom=window.image_result_single.view_zoom_for_display_scale(1.0),
            rotation=0,
        )

        monkeypatch.setattr(window, "_queue_interactive_preview_request", lambda request: captured.setdefault("request", request))

        window._mark_preview_control_interaction()
        window._refresh_preview()

        request = captured["request"]
        assert request[7] == 0
        assert request[9] is False
        assert request[13] is not None
        assert request[14] is True
        assert request[15] is False
    finally:
        window.close()


def test_slider_value_change_without_drag_uses_visible_viewport(qapp, monkeypatch):
    window = ICCRawMainWindow()
    try:
        image = gui_module.np.zeros((800, 1200, 3), dtype=gui_module.np.float32)
        display = gui_module.np.zeros((800, 1200, 3), dtype=gui_module.np.uint8)
        captured: dict[str, object] = {}
        window._original_linear = image
        window._preview_srgb = image.copy()
        window._current_result_display_u8 = display.copy()
        window._last_loaded_preview_key = "full-res-source"
        window.check_image_clip_overlay.setChecked(False)
        window.image_result_single.resize(240, 160)
        window.image_result_single.set_rgb_u8_image(display)
        window.image_result_single.set_view_transform(
            zoom=window.image_result_single.view_zoom_for_display_scale(1.0),
            rotation=0,
        )

        monkeypatch.setattr(window, "_queue_interactive_preview_request", lambda request: captured.setdefault("request", request))

        window._on_slider_change()
        window._refresh_preview()

        request = captured["request"]
        assert request[7] == 0
        assert request[9] is False
        assert request[13] is not None
        assert request[14] is True
        assert request[15] is False
    finally:
        window.close()


def test_deferred_full_final_refresh_is_opt_in(qapp, monkeypatch):
    window = ICCRawMainWindow()
    try:
        window._original_linear = gui_module.np.zeros((800, 1200, 3), dtype=gui_module.np.float32)
        monkeypatch.delenv("PROBRAW_AUTOMATIC_FULL_FINAL_REFRESH", raising=False)

        window._schedule_deferred_final_preview_refresh()
        assert not window._preview_final_refresh_timer.isActive()

        monkeypatch.setenv("PROBRAW_AUTOMATIC_FULL_FINAL_REFRESH", "1")
        window._schedule_deferred_final_preview_refresh(delay_ms=50)
        assert window._preview_final_refresh_timer.isActive()
        window._preview_final_refresh_timer.stop()
    finally:
        window.close()


def test_histogram_reuses_full_colorimetric_preview_patch(qapp, monkeypatch):
    window = ICCRawMainWindow()
    try:
        patch = gui_module.np.asarray(
            [
                [[0, 0, 0], [255, 255, 255]],
                [[255, 0, 0], [0, 255, 0]],
            ],
            dtype=gui_module.np.uint8,
        )
        calls: list[str] = []
        monkeypatch.setattr(
            window,
            "_render_viewer_histogram_u8",
            lambda *_args, **_kwargs: calls.append("recomputed") or None,
        )

        histogram = window._histogram_u8_from_colorimetric_preview_patch(patch)

        assert gui_module.np.array_equal(histogram, patch)
        assert calls == []
    finally:
        window.close()


def test_histogram_reuse_still_updates_for_each_adjustment(qapp):
    window = ICCRawMainWindow()
    try:
        first = gui_module.np.zeros((2, 2, 3), dtype=gui_module.np.uint8)
        second = gui_module.np.full((2, 2, 3), 255, dtype=gui_module.np.uint8)

        hist_first = window._histogram_u8_from_colorimetric_preview_patch(first)
        hist_second = window._histogram_u8_from_colorimetric_preview_patch(second)

        assert gui_module.np.array_equal(hist_first, first)
        assert gui_module.np.array_equal(hist_second, second)
        assert not gui_module.np.array_equal(hist_first, hist_second)
    finally:
        window.close()


def test_deferred_final_refresh_uses_bounded_display_without_histogram(qapp, monkeypatch):
    window = ICCRawMainWindow()
    try:
        image = gui_module.np.zeros((1500, 1500, 3), dtype=gui_module.np.float32)
        display = gui_module.np.zeros((1500, 1500, 3), dtype=gui_module.np.uint8)
        captured: dict[str, object] = {}
        window._original_linear = image
        window._preview_srgb = image.copy()
        window._current_result_display_u8 = display.copy()
        window._last_loaded_preview_key = "full-res-source"
        window.check_image_clip_overlay.setChecked(False)
        window.image_result_single.resize(240, 160)
        window.image_result_single.set_rgb_u8_image(display)
        window.image_result_single.set_view_transform(
            zoom=window.image_result_single.view_zoom_for_display_scale(1.0),
            rotation=0,
        )

        monkeypatch.setattr(window, "_queue_interactive_preview_request", lambda request: captured.setdefault("request", request))

        window._mark_preview_control_interaction()
        window._refresh_preview(force_final=True)

        request = captured["request"]
        assert request[7] == gui_module.PREVIEW_FINAL_ADJUSTMENT_MAX_SIDE
        assert request[9] is True
        assert request[13] is None
        assert request[14] is False
        assert request[15] is True
    finally:
        window.close()


def test_slider_change_schedules_post_interaction_exact_refresh(qapp, monkeypatch):
    window = ICCRawMainWindow()
    try:
        refreshes: list[bool] = []
        histogram_delays: list[int] = []
        delays: list[int] = []
        window._original_linear = gui_module.np.zeros((100, 120, 3), dtype=gui_module.np.float32)
        monkeypatch.setattr(window, "_schedule_preview_refresh", lambda: refreshes.append(True))
        monkeypatch.setattr(
            window,
            "_schedule_exact_histogram_refresh",
            lambda *, delay_ms, **_kwargs: histogram_delays.append(int(delay_ms)),
        )
        monkeypatch.setattr(
            window,
            "_schedule_post_interaction_exact_preview_refresh",
            lambda *, delay_ms: delays.append(int(delay_ms)),
        )

        window._on_slider_change()

        assert refreshes == [True]
        assert histogram_delays == [80]
        assert delays == [260]
    finally:
        window.close()


def test_exact_histogram_refresh_queues_full_adjusted_source(qapp, monkeypatch):
    window = ICCRawMainWindow()
    try:
        image = gui_module.np.zeros((100, 120, 3), dtype=gui_module.np.float32)
        queued: list[tuple[object, ...]] = []
        window._original_linear = image
        window._last_loaded_preview_key = "full-source"
        window.slider_brightness.setValue(100)
        monkeypatch.setattr(window, "_queue_exact_histogram_request", lambda request: queued.append(request))

        window._run_exact_histogram_refresh()

        assert len(queued) == 1
        request = queued[0]
        assert request[1] == "full-source"
        assert request[2] is image
        assert request[7] is False
        assert request[9]["brightness_ev"] == pytest.approx(1.0)
    finally:
        window.close()


def test_exact_histogram_uses_loaded_source_when_preview_is_reduced(tmp_path: Path, qapp, monkeypatch):
    window = ICCRawMainWindow()
    image_path = tmp_path / "source.tiff"
    write_tiff16(image_path, gui_module.np.zeros((80, 120, 3), dtype=gui_module.np.float32))
    try:
        preview = gui_module.np.zeros((20, 30, 3), dtype=gui_module.np.float32)
        queued: list[tuple[object, ...]] = []
        window._selected_file = image_path
        window._original_linear = preview
        window._last_loaded_preview_key = "reduced-source"
        window._loaded_preview_max_side_request = 30
        window._loaded_preview_fast_raw = False
        monkeypatch.setattr(window, "_queue_exact_histogram_request", lambda request: queued.append(request))

        window._run_exact_histogram_refresh()

        assert len(queued) == 1
        request = queued[0]
        assert request[2] is preview
        assert request[3] == image_path
        assert request[7] is False
    finally:
        window.close()


def test_exact_histogram_reduced_preview_does_not_block_on_full_source(tmp_path: Path, qapp, monkeypatch):
    window = ICCRawMainWindow()
    image_path = tmp_path / "source.tiff"
    write_tiff16(image_path, gui_module.np.zeros((80, 120, 3), dtype=gui_module.np.float32))
    try:
        delays: list[int] = []
        queued: list[tuple[object, ...]] = []
        window._selected_file = image_path
        window._original_linear = gui_module.np.zeros((20, 30, 3), dtype=gui_module.np.float32)
        window._last_loaded_preview_key = "reduced-source"
        window._loaded_preview_max_side_request = 30
        window._loaded_preview_fast_raw = False
        window._mark_preview_control_interaction(duration_ms=900)
        monkeypatch.setattr(
            window,
            "_schedule_exact_histogram_refresh",
            lambda *, delay_ms, **_kwargs: delays.append(int(delay_ms)),
        )
        monkeypatch.setattr(window, "_queue_exact_histogram_request", lambda request: queued.append(request))

        window._run_exact_histogram_refresh()

        assert delays == []
        assert len(queued) == 1
        assert queued[0][7] is False
    finally:
        window.close()


def test_exact_histogram_refresh_waits_while_slider_is_dragging(qapp, monkeypatch):
    window = ICCRawMainWindow()
    try:
        delays: list[int] = []
        queued: list[object] = []
        window._original_linear = gui_module.np.zeros((100, 120, 3), dtype=gui_module.np.float32)
        window.slider_brightness.setSliderDown(True)
        monkeypatch.setattr(
            window,
            "_schedule_exact_histogram_refresh",
            lambda *, delay_ms, **_kwargs: delays.append(int(delay_ms)),
        )
        monkeypatch.setattr(window, "_queue_exact_histogram_request", lambda request: queued.append(request))

        window._run_exact_histogram_refresh()

        assert delays == [160]
        assert queued == []
    finally:
        window.slider_brightness.setSliderDown(False)
        window.close()


def test_profile_preview_source_downscales_below_one_to_one_view(qapp):
    window = ICCRawMainWindow()
    try:
        image = gui_module.np.zeros((900, 1400, 3), dtype=gui_module.np.float32)

        source, downscaled = window._profile_preview_source_for_async(image, max_side_limit=128)

        assert source is not image
        assert source.shape == (82, 128, 3)
        assert downscaled is True
        assert window._profile_preview_max_side_limit() == gui_module.PREVIEW_PROFILE_APPLY_MAX_SIDE
        assert window._profile_preview_request_key(Path("monitor.icc")).endswith(
            f"|pm={gui_module.PREVIEW_PROFILE_APPLY_MAX_SIDE}"
        )
    finally:
        window.close()


def test_tiled_render_adjustments_match_full_render(qapp):
    window = ICCRawMainWindow()
    try:
        image = gui_module.np.linspace(0.0, 1.0, 96 * 128 * 3, dtype=gui_module.np.float32).reshape((96, 128, 3))
        kwargs = {
            "brightness_ev": 0.15,
            "contrast": 0.12,
            "vibrance": 0.18,
            "saturation": -0.08,
            "tone_curve_points": [(0.0, 0.0), (0.45, 0.58), (1.0, 1.0)],
        }

        full = gui_module.apply_render_adjustments(image, **kwargs)
        tiled = window._apply_render_adjustments_tiled(image, kwargs, target_tile_pixels=2048)

        assert gui_module.np.allclose(tiled, full, atol=2e-6)
    finally:
        window.close()


def test_tiled_display_conversion_matches_full_conversion(qapp):
    window = ICCRawMainWindow()
    try:
        image = gui_module.np.linspace(0.0, 1.0, 80 * 90 * 3, dtype=gui_module.np.float32).reshape((80, 90, 3))

        full_srgb = standard_profile_to_srgb_display(image, "scene_linear_camera_rgb")
        tiled_srgb = window._standard_profile_to_srgb_display_tiled(image, "scene_linear_camera_rgb")
        full_u8 = srgb_to_display_u8(full_srgb, None)
        tiled_u8 = window._srgb_to_display_u8_tiled(tiled_srgb, None)

        assert gui_module.np.allclose(tiled_srgb, full_srgb, atol=2e-6)
        assert gui_module.np.array_equal(tiled_u8, full_u8)
    finally:
        window.close()


def test_parallel_interactive_viewport_matches_sequential_icc(tmp_path: Path, qapp, monkeypatch):
    monkeypatch.setenv("PROBRAW_INTERACTIVE_RENDER_WORKERS", "4")
    window = ICCRawMainWindow()
    try:
        profile = tmp_path / "srgb.icc"
        profile.write_bytes(ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes())
        image = gui_module.np.linspace(0.0, 1.0, 96 * 128 * 3, dtype=gui_module.np.float32).reshape((96, 128, 3))
        kwargs = {
            "brightness_ev": 0.35,
            "contrast": 0.1,
            "blacks": -0.18,
            "tone_curve_points": [(0.0, 0.0), (0.42, 0.55), (1.0, 1.0)],
        }

        expected_adjusted = gui_module.apply_render_adjustments(image, **kwargs)
        expected_display = profiled_float_to_display_u8(expected_adjusted, profile, profile)
        expected_srgb = profiled_float_to_display_u8(expected_adjusted, profile, None)

        actual_srgb, actual_display = window._render_interactive_viewport_parallel(
            image,
            kwargs,
            output_space="srgb",
            source_profile=profile,
            monitor_profile=profile,
            include_srgb_patch=True,
            workers=4,
        )

        assert gui_module.np.array_equal(actual_display, expected_display)
        assert actual_srgb is not None
        assert gui_module.np.array_equal(actual_srgb, expected_srgb)
    finally:
        window.close()


def test_export_preview_color_parity_accepts_matching_tiff(tmp_path: Path, qapp):
    window = ICCRawMainWindow()
    try:
        image = gui_module.np.zeros((20, 24, 3), dtype=gui_module.np.float32)
        image[..., 0] = 0.25
        image[..., 1] = 0.50
        image[..., 2] = 0.75
        out = tmp_path / "matching.tiff"
        Image.fromarray(gui_module.np.round(image * 255).astype(gui_module.np.uint8), "RGB").save(out)

        metrics = window._verify_export_preview_color_parity(
            out,
            image,
            recipe=Recipe(output_space="srgb", output_linear=False),
            profile_path=None,
        )

        assert metrics is not None
        assert metrics["max_delta_u8"] == 0
    finally:
        window.close()


def test_export_preview_color_parity_uses_icc_for_generic_profile(tmp_path: Path, monkeypatch, qapp):
    window = ICCRawMainWindow()
    try:
        image = gui_module.np.zeros((6, 8, 3), dtype=gui_module.np.float32)
        expected = gui_module.np.full((6, 8, 3), 123, dtype=gui_module.np.uint8)
        profile = tmp_path / "ProPhoto.icm"
        profile.write_bytes(b"profile" * 64)
        calls: dict[str, object] = {}

        monkeypatch.setattr(preview_export_module, "ensure_generic_output_profile", lambda *_args, **_kwargs: profile)

        def fake_profiled_float_to_display_u8(image_rgb, source_profile, monitor_profile):
            calls["source_profile"] = source_profile
            calls["monitor_profile"] = monitor_profile
            return expected

        monkeypatch.setattr(preview_export_module, "profiled_float_to_display_u8", fake_profiled_float_to_display_u8)

        actual = window._expected_export_preview_srgb_u8(
            image,
            recipe=Recipe(output_space="prophoto_rgb", output_linear=False),
            profile_path=None,
        )

        assert gui_module.np.array_equal(actual, expected)
        assert calls["source_profile"] == profile
        assert calls["monitor_profile"] is None
    finally:
        window.close()


def test_display_u8_for_screen_passes_active_monitor_profile(monkeypatch, qapp):
    # _display_u8_for_screen must forward whatever _active_display_profile_path() returns
    # to srgb_to_display_u8. The conversion is always done by LittleCMS (source ICC -> monitor ICC),
    # never by tagging pixels as sRGB and delegating the transform to Qt.
    window = ICCRawMainWindow()
    try:
        profile = Path("monitor.icc")
        calls: list[object] = []

        def spy_srgb_to_display_u8(image_srgb, monitor_profile):
            calls.append(monitor_profile)
            return gui_module.np.zeros((2, 2, 3), dtype=gui_module.np.uint8)

        monkeypatch.setattr(window, "_active_display_profile_path", lambda: profile)
        monkeypatch.setattr(display_module, "srgb_to_display_u8", spy_srgb_to_display_u8)

        window._display_u8_for_screen(gui_module.np.zeros((2, 2, 3), dtype=gui_module.np.float32))
        assert len(calls) == 1
        assert calls[0] == profile, (
            f"_display_u8_for_screen must pass _active_display_profile_path() to srgb_to_display_u8; "
            f"got {calls[0]!r}, expected {profile!r}"
        )
    finally:
        window.close()


def test_display_conversion_failure_does_not_fallback_to_unmanaged_srgb(tmp_path: Path, monkeypatch, qapp):
    window = ICCRawMainWindow()
    try:
        profile = tmp_path / "monitor.icc"
        profile.write_bytes(b"bad profile")

        def fail_srgb_to_display_u8(_image_srgb, monitor_profile):
            if monitor_profile == profile:
                raise RuntimeError("broken monitor profile")
            return gui_module.np.zeros((2, 2, 3), dtype=gui_module.np.uint8)

        monkeypatch.setattr(window, "_active_display_profile_path", lambda: profile)
        monkeypatch.setattr(display_module, "srgb_to_display_u8", fail_srgb_to_display_u8)

        with pytest.raises(RuntimeError, match="Fallo de gestion ICC de monitor"):
            window._display_u8_for_screen(gui_module.np.zeros((2, 2, 3), dtype=gui_module.np.float32))
    finally:
        window.close()


def test_export_preview_color_parity_rejects_mismatching_tiff(tmp_path: Path, qapp):
    window = ICCRawMainWindow()
    try:
        image = gui_module.np.zeros((20, 24, 3), dtype=gui_module.np.float32)
        image[..., 0] = 0.25
        image[..., 1] = 0.50
        image[..., 2] = 0.75
        wrong = image.copy()
        wrong[..., 0] = 0.95
        out = tmp_path / "wrong.tiff"
        Image.fromarray(gui_module.np.round(wrong * 255).astype(gui_module.np.uint8), "RGB").save(out)

        with pytest.raises(RuntimeError, match="paridad colorimetrica preview/export"):
            window._verify_export_preview_color_parity(
                out,
                image,
                recipe=Recipe(output_space="srgb", output_linear=False),
                profile_path=None,
            )
    finally:
        window.close()


def test_interactive_preview_uses_monitor_icc_by_default(qapp):
    window = ICCRawMainWindow()
    try:
        assert window._interactive_bypass_display_icc is False
    finally:
        window.close()


def test_tone_curve_drag_handler_defers_synchronous_histogram_update(qapp, monkeypatch):
    window = ICCRawMainWindow()
    try:
        calls: list[bool] = []
        refreshes: list[bool] = []
        window._original_linear = gui_module.np.zeros((120, 160, 3), dtype=gui_module.np.float32)
        window.check_tone_curve_enabled.setChecked(True)
        window._set_tone_curve_controls_enabled(True)
        monkeypatch.setattr(
            window,
            "_update_tone_curve_histogram_for_current_controls",
            lambda *, force=False, **_kwargs: calls.append(bool(force)),
        )
        monkeypatch.setattr(window, "_schedule_tone_curve_drag_preview_refresh", lambda: refreshes.append(True))
        monkeypatch.setattr(window, "_schedule_deferred_final_preview_refresh", lambda **_kwargs: None)

        window.tone_curve_editor._drag_index = 1
        window._on_tone_curve_points_changed([(0.0, 0.0), (0.5, 0.55), (1.0, 1.0)])
        assert calls == []
        assert refreshes == [True]

        window.tone_curve_editor._drag_index = None
        window._on_tone_curve_points_changed([(0.0, 0.0), (0.5, 0.60), (1.0, 1.0)])
        assert calls == [True]
    finally:
        window.close()


def test_tone_curve_editor_drag_does_not_emit_until_release(qapp):
    editor = gui_module.ToneCurveEditor()
    try:
        editor.resize(320, 320)
        editor.set_points([(0.0, 0.0), (0.5, 0.5), (1.0, 1.0)], emit=False)
        emissions: list[object] = []
        finishes: list[bool] = []
        editor.pointsChanged.connect(lambda points: emissions.append(points))
        editor.interactionFinished.connect(lambda: finishes.append(True))

        editor._drag_index = 1

        class _MoveEvent:
            def position(self):
                return QtCore.QPointF(190, 112)

        editor.mouseMoveEvent(_MoveEvent())

        assert emissions == []
        assert finishes == []
        assert editor.points()[1] != (0.5, 0.5)

        release = QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonRelease,
            QtCore.QPointF(190, 112),
            QtCore.Qt.LeftButton,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
        )
        editor.mouseReleaseEvent(release)

        assert emissions == []
        assert finishes == [True]
    finally:
        editor.deleteLater()


def test_tone_curve_editor_drag_paint_uses_lightweight_mode(qapp, monkeypatch):
    editor = gui_module.ToneCurveEditor()
    try:
        editor.resize(320, 320)
        editor.set_points([(0.0, 0.0), (0.5, 0.5), (1.0, 1.0)], emit=False)
        editor._drag_index = 1
        calls: list[str] = []
        curve_sizes: list[int] = []
        monkeypatch.setattr(editor, "_draw_histogram_columns", lambda *_args, **_kwargs: calls.append("histogram"))
        monkeypatch.setattr(editor, "_draw_channel_curve_overlays", lambda *_args, **_kwargs: calls.append("overlays"))
        original_draw_curve = editor._draw_curve

        def draw_curve(*args, **kwargs):
            curve_sizes.append(int(kwargs.get("lut_size", 256)))
            return original_draw_curve(*args, **kwargs)

        monkeypatch.setattr(editor, "_draw_curve", draw_curve)
        image = QtGui.QImage(320, 320, QtGui.QImage.Format_ARGB32)
        image.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(image)
        painter.end()

        editor.render(image)

        assert calls == ["histogram"]
        assert curve_sizes
        assert min(curve_sizes) <= 96
    finally:
        editor.deleteLater()


def test_tone_curve_release_runs_single_preview_update(qapp, monkeypatch):
    window = ICCRawMainWindow()
    try:
        refreshes: list[bool] = []
        histograms: list[tuple[bool, bool]] = []
        window._original_linear = gui_module.np.zeros((120, 160, 3), dtype=gui_module.np.float32)
        window.check_tone_curve_enabled.setChecked(True)
        window._set_tone_curve_controls_enabled(True)
        monkeypatch.setattr(window, "_schedule_preview_refresh", lambda: refreshes.append(True))
        monkeypatch.setattr(
            window,
            "_update_tone_curve_histogram_for_current_controls",
            lambda *, force=False, async_update=False, **_kwargs: histograms.append((bool(force), bool(async_update))),
        )
        monkeypatch.setattr(window, "_schedule_deferred_final_preview_refresh", lambda **_kwargs: None)

        window.tone_curve_editor.set_points([(0.0, 0.0), (0.5, 0.58), (1.0, 1.0)], emit=False)
        window._on_tone_curve_interaction_finished()

        assert histograms == [(True, True)]
        assert refreshes == [True]
    finally:
        window.close()


def test_tone_curve_range_slider_drag_defers_heavy_updates(qapp, monkeypatch):
    window = ICCRawMainWindow()
    try:
        drag_refreshes: list[bool] = []
        preview_refreshes: list[bool] = []
        histograms: list[bool] = []
        exact_histogram_calls: list[tuple[int, bool]] = []
        window.check_tone_curve_enabled.setChecked(True)
        window._original_linear = gui_module.np.zeros((120, 160, 3), dtype=gui_module.np.float32)
        monkeypatch.setattr(window, "_schedule_tone_curve_drag_preview_refresh", lambda: drag_refreshes.append(True))
        monkeypatch.setattr(window, "_schedule_preview_refresh", lambda: preview_refreshes.append(True))
        monkeypatch.setattr(
            window,
            "_schedule_exact_histogram_refresh",
            lambda *, delay_ms, mark_pending=True, **_kwargs: exact_histogram_calls.append((int(delay_ms), bool(mark_pending))),
        )
        monkeypatch.setattr(
            window,
            "_update_tone_curve_histogram_for_current_controls",
            lambda *, force=False, **_kwargs: histograms.append(bool(force)),
        )

        window.slider_tone_curve_black.setSliderDown(True)
        window.slider_tone_curve_black.setValue(80)

        assert drag_refreshes == [True]
        assert preview_refreshes == []
        assert histograms == []
        assert exact_histogram_calls == [(80, False)]
        assert window.tone_curve_editor.is_range_dragging()
        assert window.tone_curve_editor._black_point == pytest.approx(0.08)
        assert window.tone_curve_editor._white_point == pytest.approx(1.0)
    finally:
        window.slider_tone_curve_black.setSliderDown(False)
        window.close()


def test_tone_curve_range_drag_preview_refresh_is_immediate(qapp):
    window = ICCRawMainWindow()
    original_timer = getattr(window, "_tone_curve_preview_timer", None)
    try:
        starts: list[int] = []

        class _Timer:
            def isActive(self) -> bool:
                return False

            def start(self, delay: int) -> None:
                starts.append(int(delay))

        window._original_linear = gui_module.np.zeros((120, 160, 3), dtype=gui_module.np.float32)
        window._tone_curve_preview_timer = _Timer()

        window.tone_curve_editor.set_range_dragging(True)
        window._schedule_tone_curve_drag_preview_refresh()

        window.tone_curve_editor.set_range_dragging(False)
        window._schedule_tone_curve_drag_preview_refresh()

        assert starts == [0, preview_render_module.PREVIEW_TONE_CURVE_DRAG_THROTTLE_MS]
    finally:
        if original_timer is not None:
            window._tone_curve_preview_timer = original_timer
        window.close()


def test_tone_curve_range_slider_release_consolidates_once(qapp, monkeypatch):
    window = ICCRawMainWindow()
    try:
        refreshes: list[bool] = []
        histograms: list[tuple[bool, bool]] = []
        syncs: list[bool] = []
        exact_histogram_calls: list[tuple[int, bool]] = []
        exact_preview_delays: list[int] = []
        window.check_tone_curve_enabled.setChecked(True)
        window._original_linear = gui_module.np.zeros((120, 160, 3), dtype=gui_module.np.float32)
        monkeypatch.setattr(window, "_sync_tone_curve_editor_channel_overlay", lambda: syncs.append(True))
        monkeypatch.setattr(window, "_schedule_preview_refresh", lambda: refreshes.append(True))
        monkeypatch.setattr(window, "_schedule_deferred_final_preview_refresh", lambda **_kwargs: None)
        monkeypatch.setattr(
            window,
            "_update_tone_curve_histogram_for_current_controls",
            lambda *, force=False, async_update=False, **_kwargs: histograms.append((bool(force), bool(async_update))),
        )
        monkeypatch.setattr(
            window,
            "_schedule_exact_histogram_refresh",
            lambda *, delay_ms, mark_pending=True, **_kwargs: exact_histogram_calls.append((int(delay_ms), bool(mark_pending))),
        )
        monkeypatch.setattr(
            window,
            "_schedule_post_interaction_exact_preview_refresh",
            lambda *, delay_ms: exact_preview_delays.append(int(delay_ms)),
        )

        window.slider_tone_curve_white.setSliderDown(True)
        window.slider_tone_curve_white.setValue(920)
        window.slider_tone_curve_white.setSliderDown(False)

        assert syncs == [True]
        assert histograms == [(True, True)]
        assert refreshes == [True]
        assert exact_histogram_calls == [(80, False), (80, True)]
        assert exact_preview_delays == [260]
        assert not window.tone_curve_editor.is_range_dragging()
    finally:
        window.slider_tone_curve_white.setSliderDown(False)
        window.close()


def test_tone_curve_range_slider_paint_uses_lightweight_mode(qapp, monkeypatch):
    editor = gui_module.ToneCurveEditor()
    try:
        editor.resize(320, 320)
        editor.set_histogram_from_image(gui_module.np.ones((32, 32, 3), dtype=gui_module.np.float32))
        editor.set_range_dragging(True)
        calls: list[str] = []
        curve_sizes: list[int] = []
        monkeypatch.setattr(editor, "_draw_histogram_columns", lambda *_args, **_kwargs: calls.append("histogram"))
        monkeypatch.setattr(editor, "_draw_channel_curve_overlays", lambda *_args, **_kwargs: calls.append("overlays"))
        original_draw_curve = editor._draw_curve

        def draw_curve(*args, **kwargs):
            curve_sizes.append(int(kwargs.get("lut_size", 256)))
            return original_draw_curve(*args, **kwargs)

        monkeypatch.setattr(editor, "_draw_curve", draw_curve)
        image = QtGui.QImage(320, 320, QtGui.QImage.Format_ARGB32)
        image.fill(QtCore.Qt.transparent)

        editor.render(image)

        assert calls == ["histogram"]
        assert curve_sizes
        assert min(curve_sizes) <= 96
    finally:
        editor.deleteLater()


def test_tone_curve_can_be_edited_while_effect_disabled(qapp, monkeypatch):
    window = ICCRawMainWindow()
    try:
        refreshes: list[bool] = []
        persists: list[bool] = []
        window._original_linear = gui_module.np.zeros((80, 90, 3), dtype=gui_module.np.float32)
        monkeypatch.setattr(window, "_schedule_preview_refresh", lambda: refreshes.append(True))
        monkeypatch.setattr(window, "_schedule_deferred_final_preview_refresh", lambda **_kwargs: refreshes.append(True))
        monkeypatch.setattr(window, "_schedule_render_adjustment_sidecar_persist", lambda *_, **__: persists.append(True))

        assert not window.check_tone_curve_enabled.isChecked()
        assert window.tone_curve_editor.isEnabled()

        window.tone_curve_editor.set_points([(0.0, 0.0), (0.45, 0.70), (1.0, 1.0)])
        state = window._render_adjustment_state()
        kwargs = window._render_adjustment_kwargs_from_state(state)

        assert refreshes == []
        assert persists
        assert state["tone_curve_enabled"] is False
        assert state["tone_curve_points"][1] == [0.45, 0.70]
        assert kwargs["tone_curve_points"] is None

        window.check_tone_curve_enabled.setChecked(True)
        enabled_kwargs = window._render_adjustment_kwargs()
        assert enabled_kwargs["tone_curve_points"][1] == [0.45, 0.70]
    finally:
        window.close()


def test_tone_curve_disable_cancels_pending_drag(qapp):
    window = ICCRawMainWindow()
    try:
        window.check_tone_curve_enabled.setChecked(True)
        window.tone_curve_editor.set_points([(0.0, 0.0), (0.5, 0.5), (1.0, 1.0)], emit=False)
        window.tone_curve_editor._drag_index = 1

        window.check_tone_curve_enabled.setChecked(False)

        assert window.tone_curve_editor.isEnabled()
        assert not window.tone_curve_editor.is_dragging()
    finally:
        window.close()


def test_tone_curve_drag_does_not_resync_editor_overlay_each_mouse_move(qapp, monkeypatch):
    window = ICCRawMainWindow()
    try:
        syncs: list[bool] = []
        window._original_linear = gui_module.np.zeros((80, 90, 3), dtype=gui_module.np.float32)
        window.check_tone_curve_enabled.setChecked(True)
        window._set_tone_curve_controls_enabled(True)
        monkeypatch.setattr(window, "_sync_tone_curve_editor_channel_overlay", lambda: syncs.append(True))
        monkeypatch.setattr(window, "_schedule_tone_curve_drag_preview_refresh", lambda: None)

        window.tone_curve_editor.set_points([(0.0, 0.0), (0.45, 0.62), (1.0, 1.0)], emit=False)
        window.tone_curve_editor._drag_index = 1
        window._on_tone_curve_points_changed([(0.0, 0.0), (0.45, 0.62), (1.0, 1.0)])

        assert syncs == []
        assert window._tone_curve_channel_points["luminance"][1] == (0.45, 0.62)

        window.tone_curve_editor._drag_index = None
        window._on_tone_curve_interaction_finished()

        assert syncs == [True]
    finally:
        window.close()


def test_interactive_worker_count_adapts_to_hardware(qapp, monkeypatch):
    window = ICCRawMainWindow()
    try:
        monkeypatch.delenv("PROBRAW_INTERACTIVE_RENDER_WORKERS", raising=False)
        monkeypatch.setattr(preview_render_module.os, "cpu_count", lambda: 16)
        monkeypatch.setattr(window, "_system_total_memory_bytes", lambda: 64 * 1024 * 1024 * 1024)
        monkeypatch.setattr(window, "_system_available_memory_bytes", lambda: 32 * 1024 * 1024 * 1024)

        assert window._interactive_preview_worker_count(100_000) == 1
        assert window._interactive_preview_worker_count(500_000) == 4
        window._record_interactive_worker_performance(500_000, 4, 30.0)
        assert window._interactive_preview_worker_count(500_000) == 6
        window._record_interactive_worker_performance(500_000, 6, 18.0)
        assert window._interactive_preview_worker_count(500_000) == 6
        assert window._interactive_preview_worker_count(1_500_000) == 4

        monkeypatch.setenv("PROBRAW_INTERACTIVE_RENDER_WORKERS", "3")
        assert window._interactive_preview_worker_count(1_500_000) == 3
    finally:
        window.close()


def test_stuck_interactive_preview_watchdog_releases_queue(qapp):
    window = ICCRawMainWindow()
    try:
        messages: list[str] = []
        window._interactive_preview_task_active = True
        window._interactive_preview_task_token = 10
        window._interactive_preview_inflight_key = "stuck"
        window._interactive_preview_inflight_viewport_rect = None
        window._interactive_preview_inflight_include_analysis = True
        window._interactive_preview_expected_key = "stuck"
        window._interactive_preview_pending_request = None
        window._log_preview = lambda message: messages.append(str(message))

        window._abandon_stuck_interactive_preview(10, "stuck")

        assert not window._interactive_preview_task_active
        assert window._interactive_preview_inflight_key is None
        assert window._interactive_preview_inflight_viewport_rect is None
        assert not window._interactive_preview_inflight_include_analysis
        assert window._interactive_preview_expected_key is None
        assert messages
    finally:
        window.close()


def test_visible_viewport_request_preempts_full_interactive_render(qapp, monkeypatch):
    window = ICCRawMainWindow()
    try:
        image = gui_module.np.zeros((100, 120, 3), dtype=gui_module.np.float32)
        request = (
            "new-visible",
            "source",
            image,
            {},
            {},
            False,
            False,
            0,
            False,
            False,
            "srgb",
            None,
            None,
            (10, 12, 40, 36),
            True,
            True,
        )
        started: list[tuple[object, ...]] = []
        window._interactive_preview_task_active = True
        window._interactive_preview_task_token = 7
        window._interactive_preview_inflight_key = "old-full"
        window._interactive_preview_inflight_viewport_rect = None
        window._interactive_preview_inflight_include_analysis = True
        window._interactive_preview_pending_request = None

        monkeypatch.setattr(window, "_start_interactive_preview_task", lambda queued: started.append(queued))

        window._queue_interactive_preview_request(request)

        assert started == [request]
        assert window._interactive_preview_expected_key == "new-visible"
        assert window._interactive_preview_pending_request is None
        assert window._interactive_preview_task_token == 8
    finally:
        window.close()


def test_visible_viewport_request_waits_for_inflight_viewport_render(qapp, monkeypatch):
    window = ICCRawMainWindow()
    try:
        image = gui_module.np.zeros((100, 120, 3), dtype=gui_module.np.float32)
        request = (
            "new-visible",
            "source",
            image,
            {},
            {},
            False,
            False,
            0,
            False,
            False,
            "srgb",
            None,
            None,
            (10, 12, 40, 36),
            True,
            True,
        )
        started: list[tuple[object, ...]] = []
        window._interactive_preview_task_active = True
        window._interactive_preview_task_token = 7
        window._interactive_preview_inflight_key = "old-visible"
        window._interactive_preview_inflight_viewport_rect = (0, 0, 40, 36)
        window._interactive_preview_inflight_include_analysis = False
        window._interactive_preview_pending_request = None

        monkeypatch.setattr(window, "_start_interactive_preview_task", lambda queued: started.append(queued))

        window._queue_interactive_preview_request(request)

        assert started == []
        assert window._interactive_preview_expected_key == "new-visible"
        assert window._interactive_preview_pending_request == request
        assert window._interactive_preview_task_token == 7
    finally:
        window.close()


def test_tone_curve_histogram_follows_brightness_adjustment(qapp):
    window = ICCRawMainWindow()
    try:
        values = gui_module.np.linspace(0.02, 0.48, 90 * 120, dtype=gui_module.np.float32).reshape((90, 120, 1))
        image = gui_module.np.repeat(values**1.7, 3, axis=2)
        window._original_linear = image
        window._last_loaded_preview_key = "histogram-test"

        window.slider_brightness.blockSignals(True)
        window.slider_brightness.setValue(0)
        window.slider_brightness.blockSignals(False)
        window._update_tone_curve_histogram_for_current_controls(force=True)
        before = window.tone_curve_editor._histogram.copy()

        window.slider_brightness.blockSignals(True)
        window.slider_brightness.setValue(100)
        window.slider_brightness.blockSignals(False)
        window._update_tone_curve_histogram_for_current_controls(force=True)
        after = window.tone_curve_editor._histogram.copy()

        assert before.shape == after.shape
        assert not gui_module.np.allclose(before, after)
        assert "bright=1.0000" in window._tone_curve_histogram_key
    finally:
        window.close()


def test_tone_curve_histogram_initializes_when_curve_is_disabled(qapp):
    window = ICCRawMainWindow()
    try:
        values = gui_module.np.linspace(0.01, 0.72, 80 * 100, dtype=gui_module.np.float32).reshape((80, 100, 1))
        image = gui_module.np.concatenate((values, values**1.4, gui_module.np.sqrt(values)), axis=2)
        window._original_linear = image
        window._last_loaded_preview_key = "disabled-curve-histogram"
        window.check_tone_curve_enabled.setChecked(False)

        window._update_tone_curve_histogram_for_current_controls()

        assert window.tone_curve_editor._histogram is not None
        assert window.tone_curve_editor._histogram_luminance is not None
        assert "curve_stage=output" in window._tone_curve_histogram_key
    finally:
        window.close()


def test_tone_curve_histogram_async_queue_keeps_latest_pending_request(qapp, monkeypatch):
    window = ICCRawMainWindow()
    try:
        image = gui_module.np.zeros((12, 16, 3), dtype=gui_module.np.float32)
        started: list[tuple[str, gui_module.np.ndarray, dict[str, object], str]] = []
        monkeypatch.setattr(window, "_start_tone_curve_histogram_task", lambda request: started.append(request))

        first = ("hist-1", image, {"brightness_ev": 0.0}, "luminance")
        second = ("hist-2", image, {"brightness_ev": 0.5}, "luminance")

        window._tone_curve_histogram_task_active = True
        window._queue_tone_curve_histogram_request(first)
        window._queue_tone_curve_histogram_request(second)

        assert started == []
        assert window._tone_curve_histogram_expected_key == "hist-2"
        assert window._tone_curve_histogram_pending_request == second
    finally:
        window.close()


def test_tone_curve_histogram_follows_curve_points_change(qapp):
    window = ICCRawMainWindow()
    try:
        values = gui_module.np.linspace(0.02, 0.82, 90 * 120, dtype=gui_module.np.float32).reshape((90, 120, 1))
        image = gui_module.np.concatenate(
            (
                values,
                gui_module.np.sqrt(values),
                values**1.8,
            ),
            axis=2,
        )
        window._original_linear = image
        window._last_loaded_preview_key = "curve-histogram-test"
        window.check_tone_curve_enabled.blockSignals(True)
        window.check_tone_curve_enabled.setChecked(True)
        window.check_tone_curve_enabled.blockSignals(False)
        window._set_tone_curve_controls_enabled(True)
        window.tone_curve_editor.set_points([(0.0, 0.0), (1.0, 1.0)], emit=False)
        window._save_visible_tone_curve_channel_state()
        window._update_tone_curve_histogram_for_current_controls(force=True)
        before = window.tone_curve_editor._histogram.copy()

        window.tone_curve_editor.set_points([(0.0, 0.0), (0.32, 0.78), (1.0, 1.0)], emit=False)
        window._on_tone_curve_points_changed(window.tone_curve_editor.points())
        after = window.tone_curve_editor._histogram.copy()

        assert before.shape == after.shape
        assert not gui_module.np.allclose(before, after)
        assert window.tone_curve_editor._histogram_luminance is not None
        assert window.tone_curve_editor._histogram_r is not None
        assert window.tone_curve_editor._histogram_g is not None
        assert window.tone_curve_editor._histogram_b is not None
        assert "curve_stage=output" in window._tone_curve_histogram_key
        assert "curve=0.0000:0.0000,0.3200:0.7800,1.0000:1.0000" in window._tone_curve_histogram_key
    finally:
        window.close()


def test_tone_curve_histogram_follows_curve_range_change(qapp):
    window = ICCRawMainWindow()
    try:
        values = gui_module.np.linspace(0.02, 0.92, 90 * 120, dtype=gui_module.np.float32).reshape((90, 120, 1))
        image = gui_module.np.repeat(values, 3, axis=2)
        window._original_linear = image
        window._last_loaded_preview_key = "curve-range-histogram-test"
        window.check_tone_curve_enabled.blockSignals(True)
        window.check_tone_curve_enabled.setChecked(True)
        window.check_tone_curve_enabled.blockSignals(False)
        window._set_tone_curve_controls_enabled(True)

        window._update_tone_curve_histogram_for_current_controls(force=True)
        before = window.tone_curve_editor._histogram.copy()

        window.slider_tone_curve_white.blockSignals(True)
        window.slider_tone_curve_white.setValue(877)
        window.slider_tone_curve_white.blockSignals(False)
        window.tone_curve_editor.set_input_range(0.0, 0.877)
        window._update_tone_curve_histogram_for_current_controls(force=True)
        after = window.tone_curve_editor._histogram.copy()

        assert before.shape == after.shape
        assert not gui_module.np.allclose(before, after)
        assert "curve_stage=output" in window._tone_curve_histogram_key
        assert "curve_white=0.8770" in window._tone_curve_histogram_key
    finally:
        window.close()


def test_tone_curve_editor_uses_active_rgb_channel_histogram_and_keeps_overlays(qapp):
    window = ICCRawMainWindow()
    try:
        values = gui_module.np.linspace(0.02, 0.92, 96 * 128, dtype=gui_module.np.float32).reshape((96, 128, 1))
        image = gui_module.np.concatenate(
            (
                values,
                values**1.8,
                gui_module.np.sqrt(values),
            ),
            axis=2,
        )
        window._original_linear = image
        window._last_loaded_preview_key = "curve-channel-histogram-test"
        window.check_tone_curve_enabled.setChecked(True)
        window._set_tone_curve_controls_enabled(True)

        window._set_combo_data(window.combo_tone_curve_channel, "red")
        window._update_tone_curve_histogram_for_current_controls(force=True)
        editor = window.tone_curve_editor
        assert editor._active_channel == "red"
        assert editor._histogram is not None
        assert gui_module.np.allclose(editor._histogram, editor._histogram_r)
        assert not gui_module.np.allclose(editor._histogram, editor._histogram_g)

        editor.set_points([(0.0, 0.0), (0.30, 0.62), (1.0, 1.0)], emit=False)
        window._on_tone_curve_points_changed(editor.points())

        window._set_combo_data(window.combo_tone_curve_channel, "green")
        editor.set_points([(0.0, 0.0), (0.58, 0.74), (1.0, 1.0)], emit=False)
        window._on_tone_curve_points_changed(editor.points())

        assert editor._active_channel == "green"
        assert editor._channel_curves["red"][1] == pytest.approx((0.30, 0.62))
        assert editor._channel_curves["green"][1] == pytest.approx((0.58, 0.74))
    finally:
        window.close()


def test_colprof_args_default_to_restricted_input_gamut(qapp):
    window = ICCRawMainWindow()
    try:
        assert window._build_colprof_args() == ["-qm", "-as", "-u", "-R"]

        window._apply_recipe_to_controls(Recipe(argyll_colprof_args=["-qh", "-al"]))

        assert window.combo_profile_quality.currentData() == "h"
        assert window.combo_profile_algo.currentData() == "-al"
        assert window._build_colprof_args() == ["-qh", "-al", "-u", "-R"]
    finally:
        window.close()


def test_loading_or_using_icc_profile_enables_apply_profile(tmp_path: Path, monkeypatch, qapp):
    root = tmp_path / "session"
    payload = create_session(root, name="Sesion perfiles")

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        profile = root / "00_configuraciones" / "profiles" / "loaded.icc"
        profile.parent.mkdir(parents=True, exist_ok=True)
        profile.write_bytes(b"fake profile" * 32)
        monkeypatch.setattr(
            QtWidgets.QFileDialog,
            "getOpenFileName",
            lambda *_args, **_kwargs: (str(profile), "ICC Profiles (*.icc *.icm)"),
        )

        window.chk_apply_profile.setChecked(False)
        window._menu_load_profile()

        assert window.chk_apply_profile.isChecked()
        assert window._active_session_icc_for_settings() == profile

        generated = Path(window.profile_out_path_edit.text())
        generated.parent.mkdir(parents=True, exist_ok=True)
        generated.write_bytes(b"generated profile" * 32)
        window.chk_apply_profile.setChecked(False)
        window._use_generated_profile_as_active()

        assert window.chk_apply_profile.isChecked()
        assert window._active_session_icc_for_settings() == generated
    finally:
        window.close()


def test_activate_session_loads_generated_icc_profile_catalog(tmp_path: Path, monkeypatch, qapp):
    root = tmp_path / "session"
    payload = create_session(
        root,
        name="Sesion perfiles",
        state={"preview_apply_profile": True},
    )
    window = ICCRawMainWindow()
    try:
        monkeypatch.setattr(window, "_is_legacy_temp_output_path", lambda _value: False)
        paths = window._session_paths_from_root(root)
        first = paths["profiles"] / "d50.icc"
        second = paths["profiles"] / "led.icc"
        first.parent.mkdir(parents=True, exist_ok=True)
        first.write_bytes(b"d50 profile" * 32)
        second.write_bytes(b"led profile" * 32)
        first.with_suffix(".profile.json").write_text('{"profile_status": "validated"}', encoding="utf-8")
        second.with_suffix(".profile.json").write_text('{"profile_status": "draft"}', encoding="utf-8")
        payload["state"]["profile_active_path"] = str(second)

        window._activate_session(root, payload)

        assert [Path(profile["path"]).name for profile in window._icc_profiles] == ["led.icc", "d50.icc"]
        assert Path(window.path_profile_active.text()) == second
        assert window.chk_apply_profile.isChecked()
        assert window.icc_profile_combo.count() == 3
        assert window.icc_profile_combo.currentData() == window._active_icc_profile_id
        assert window.gamut_profile_a_combo.findData(f"managed:{window._active_icc_profile_id}") >= 0
        first_profile_id = next(profile["id"] for profile in window._icc_profiles if Path(profile["path"]).name == "d50.icc")
        window.icc_profile_combo.setCurrentIndex(window.icc_profile_combo.findData(first_profile_id))
        assert Path(window.path_profile_active.text()) == first
        assert window._active_icc_profile_id == first_profile_id
        assert window.combo_output_space.currentText().strip() == "scene_linear_camera_rgb"
        assert window.check_output_linear.isChecked()

        saved_state = load_session(root)["state"]
        assert [Path(profile["path"]).name for profile in saved_state["icc_profiles"]] == ["led.icc", "d50.icc"]
        assert saved_state["active_icc_profile_id"] == window._active_icc_profile_id
    finally:
        window.close()


def test_profile_generation_versions_session_icc_outputs_and_registers_profile(tmp_path: Path, monkeypatch, qapp):
    chart = tmp_path / "chart.tiff"
    Image.new("RGB", (16, 16), (20, 120, 220)).save(chart)
    root = tmp_path / "session"
    payload = create_session(root, name="Sesion perfiles")
    captured: dict[str, Path] = {}

    def fake_auto_generate_profile_from_charts(**kwargs):
        captured.update(
            {
                "profile_out": kwargs["profile_out"],
                "profile_report_out": kwargs["profile_report_out"],
                "development_profile_out": kwargs["development_profile_out"],
                "calibrated_recipe_out": kwargs["calibrated_recipe_out"],
                "work_dir": kwargs["work_dir"],
            }
        )
        kwargs["profile_out"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["profile_out"].write_bytes(b"new profile" * 32)
        kwargs["profile_report_out"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["profile_report_out"].write_text("{}", encoding="utf-8")
        kwargs["development_profile_out"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["development_profile_out"].write_text("{}", encoding="utf-8")
        gui_module.save_recipe(Recipe(), kwargs["calibrated_recipe_out"])
        return {
            "chart_captures_used": 1,
            "training_captures_total": 1,
            "development_profile_path": str(kwargs["development_profile_out"]),
            "calibrated_recipe_path": str(kwargs["calibrated_recipe_out"]),
            "profile_report_path": str(kwargs["profile_report_out"]),
            "profile_status": {
                "status": "validated",
                "generated_at": "2026-04-29T12:00:00+00:00",
            },
            "profile": {"error_summary": {}, "patch_errors": []},
        }

    def run_task(_label, task, on_success):
        on_success(task())

    monkeypatch.setattr(gui_module.ReferenceCatalog, "from_path", staticmethod(lambda _path: object()))
    monkeypatch.setattr(gui_module, "auto_generate_profile_from_charts", fake_auto_generate_profile_from_charts)

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        defaults = window._session_default_outputs()
        defaults["profile_out"].parent.mkdir(parents=True, exist_ok=True)
        defaults["profile_out"].write_bytes(b"existing profile" * 32)
        window._start_background_task = run_task
        window._selected_chart_files = [chart]
        window.profile_charts_dir.setText(str(tmp_path))

        window._on_generate_profile()

        assert captured["profile_out"].name == "Sesion perfiles_v002.icc"
        assert captured["profile_report_out"].parent == root / "00_configuraciones" / "profile_runs" / "Sesion perfiles_v002"
        assert captured["work_dir"] == root / "00_configuraciones" / "work" / "profile_generation" / "Sesion perfiles_v002"
        assert Path(window.path_profile_active.text()) == captured["profile_out"]
        assert window.chk_apply_profile.isChecked()
        assert window.icc_profile_combo.currentData() == window._active_icc_profile_id
        assert [Path(profile["path"]).name for profile in window._icc_profiles][:2] == [
            "Sesion perfiles_v002.icc",
            "Sesion perfiles.icc",
        ]

        saved_state = load_session(root)["state"]
        assert Path(saved_state["icc_profiles"][0]["path"]).name == "Sesion perfiles_v002.icc"
        assert saved_state["active_icc_profile_id"] == window._active_icc_profile_id
        assert window._next_generated_icc_profile_path(captured["profile_out"]).name == "Sesion perfiles_v003.icc"
    finally:
        window.close()


def test_profile_report_with_high_training_error_is_not_activable(tmp_path: Path, qapp):
    root = tmp_path / "session"
    payload = create_session(root, name="perfil_malo")

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        defaults = window._session_default_outputs()
        profile = defaults["profile_out"]
        profile.parent.mkdir(parents=True, exist_ok=True)
        profile.write_bytes(b"fake icc profile bytes" * 16)
        defaults["profile_report"].write_text(
            json.dumps(
                {
                    "output_icc": str(profile),
                    "error_summary": {
                        "mean_delta_e2000": 26.8,
                        "max_delta_e2000": 46.9,
                    },
                    "metadata": {"profile_status": "draft"},
                }
            ),
            encoding="utf-8",
        )

        assert window._profile_status_for_path(profile) == "rejected"
        assert not window._profile_can_be_active(profile)
    finally:
        window.close()


def test_session_activation_loads_saved_chart_diagnostics(tmp_path: Path, qapp):
    root = tmp_path / "session"
    payload = create_session(root, name="perfil_carta")
    profile_path = root / "00_configuraciones" / "profiles" / "perfil_carta.icc"
    report_path = root / "00_configuraciones" / "profile_runs" / "perfil_carta" / "profile_report.json"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_bytes(b"fake icc profile bytes" * 16)
    report_path.write_text(
        json.dumps(
            {
                "output_icc": str(profile_path),
                "error_summary": {
                    "mean_delta_e2000": 2.4,
                    "median_delta_e2000": 2.1,
                    "p95_delta_e2000": 3.8,
                    "max_delta_e2000": 4.2,
                },
                "patch_errors": [
                    {
                        "patch_id": "P01",
                        "reference_lab": [37.99, 13.56, 14.06],
                        "profile_lab": [38.45, 12.91, 15.10],
                        "delta_e76": 1.3,
                        "delta_e2000": 1.1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    payload["state"].update(
        {
            "profile_output_path": str(profile_path),
            "profile_report_path": str(report_path),
            "profile_active_path": str(profile_path),
            "icc_profiles": [
                {
                    "id": "icc-perfil-carta",
                    "name": "perfil_carta",
                    "path": profile_path.relative_to(root).as_posix(),
                    "profile_report_path": report_path.relative_to(root).as_posix(),
                    "status": "validated",
                }
            ],
            "active_icc_profile_id": "icc-perfil-carta",
        }
    )

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)

        assert window.chart_diagnostics_table.rowCount() == 1
        assert window.chart_diagnostics_table.item(0, 0).text() == "P01"
        assert "DeltaE2000 media 2.40" in window.chart_diagnostics_summary.text()
        assert window.chart_diagnostics_summary.toolTip() == str(report_path)
    finally:
        window.close()


def test_manual_chart_points_use_display_coordinate_space(tmp_path: Path, qapp):
    root = tmp_path / "session"
    raw = root / "01_ORG" / "chart.NEF"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"raw")
    payload = create_session(root, name="manual")

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        window._selected_file = raw
        window._manual_chart_points_source = raw
        window._original_linear = gui_module.np.zeros((1000, 2000, 3), dtype=gui_module.np.float32)
        window.image_result_single.set_rgb_u8_image(
            gui_module.np.zeros((500, 1000, 3), dtype=gui_module.np.uint8)
        )
        window._manual_chart_points = [(100.0, 80.0), (900.0, 80.0), (900.0, 420.0), (100.0, 420.0)]

        pending = window._pending_manual_detection_request([raw])

        assert pending is not None
        assert pending["preview_shape"] == (500, 1000)
        assert window._preview_requires_max_quality()
    finally:
        window.close()


def test_generate_profile_prefers_pending_manual_points_over_stale_chart_selection(tmp_path: Path, monkeypatch, qapp):
    current = tmp_path / "current.NEF"
    stale = tmp_path / "stale.NEF"
    current.write_bytes(b"current raw")
    stale.write_bytes(b"stale raw")
    captured: dict[str, object] = {}

    def fake_auto_generate_profile_from_charts(**kwargs):
        captured.update(kwargs)
        return {
            "chart_captures_used": 1,
            "training_captures_total": 1,
            "profile_status": {"status": "draft"},
            "profile": {"error_summary": {}, "patch_errors": []},
        }

    def run_task(_label, task, on_success):
        on_success(task())

    monkeypatch.setattr(gui_module.ReferenceCatalog, "from_path", staticmethod(lambda _path: object()))
    monkeypatch.setattr(gui_module, "auto_generate_profile_from_charts", fake_auto_generate_profile_from_charts)

    window = ICCRawMainWindow()
    try:
        window._start_background_task = run_task
        window._selected_chart_files = [stale]
        window.profile_charts_dir.setText(str(tmp_path))
        window._selected_file = current
        window._original_linear = gui_module.np.zeros((100, 200, 3), dtype=gui_module.np.float32)
        window.image_result_single.set_rgb_u8_image(
            gui_module.np.zeros((50, 100, 3), dtype=gui_module.np.uint8)
        )
        window._manual_chart_points_source = current.resolve()
        window._manual_chart_points = [(10.0, 5.0), (90.0, 5.0), (90.0, 45.0), (10.0, 45.0)]
        monkeypatch.setattr(
            window,
            "_build_pending_manual_detection",
            lambda request, **_kwargs: (Path(str(request["source"])).resolve(), {"detection_mode": "manual"}),
        )

        window._on_generate_profile()

        chart_files = captured["chart_capture_files"]
        assert isinstance(chart_files, list)
        assert Path(chart_files[0]) == current.resolve()
        assert stale in chart_files
        manual_detections = captured["manual_detections"]
        assert isinstance(manual_detections, dict)
        assert current.resolve() in manual_detections
    finally:
        window.close()


def test_start_manual_chart_marking_is_immediate_and_sets_crosshair(tmp_path: Path, monkeypatch, qapp):
    root = tmp_path / "session"
    raw = root / "01_ORG" / "chart.NEF"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"raw")
    payload = create_session(root, name="manual")
    reload_calls = {"count": 0}

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        window._selected_file = raw
        window._original_linear = gui_module.np.zeros((500, 1000, 3), dtype=gui_module.np.float32)
        window.image_result_single.set_rgb_u8_image(
            gui_module.np.zeros((500, 1000, 3), dtype=gui_module.np.uint8)
        )
        monkeypatch.setattr(window, "_on_load_selected", lambda *args, **kwargs: reload_calls.__setitem__("count", 1))

        window._start_manual_chart_marking()

        assert reload_calls["count"] == 0
        assert window._manual_chart_marking
        assert window.image_result_single.cursor().shape() == QtCore.Qt.CrossCursor

        window._on_manual_chart_click(100, 100)
        window._on_manual_chart_click(900, 100)
        window._on_manual_chart_click(900, 400)
        window._on_manual_chart_click(100, 400)

        assert not window._manual_chart_marking
        assert window.image_result_single.cursor().shape() != QtCore.Qt.CrossCursor
    finally:
        window.close()


def test_generate_profile_draft_does_not_auto_activate(tmp_path: Path, monkeypatch, qapp):
    chart = tmp_path / "chart.tiff"
    Image.new("RGB", (16, 16), (20, 120, 220)).save(chart)

    def fake_auto_generate_profile_from_charts(**_kwargs):
        return {
            "chart_captures_used": 1,
            "training_captures_total": 1,
            "profile_status": {
                "status": "draft",
                "reasons": ["sin_validacion_independiente"],
            },
            "profile": {
                "error_summary": {
                    "mean_delta_e2000": 2.0,
                    "median_delta_e2000": 1.8,
                    "p95_delta_e2000": 3.5,
                    "max_delta_e2000": 4.0,
                },
                "patch_errors": [
                    {
                        "patch_id": "P01",
                        "reference_lab": [37.99, 13.56, 14.06],
                        "profile_lab": [38.45, 12.91, 15.10],
                        "delta_e76": 1.3,
                        "delta_e2000": 1.1,
                    }
                ],
            },
        }

    def run_task(_label, task, on_success):
        on_success(task())

    monkeypatch.setattr(gui_module.ReferenceCatalog, "from_path", staticmethod(lambda _path: object()))
    monkeypatch.setattr(gui_module, "auto_generate_profile_from_charts", fake_auto_generate_profile_from_charts)

    window = ICCRawMainWindow()
    try:
        window._start_background_task = run_task
        window._selected_chart_files = [chart]
        window.profile_charts_dir.setText(str(tmp_path))
        window.path_profile_active.setText(str(tmp_path / "old.icc"))
        window.chk_apply_profile.setChecked(True)

        window._on_generate_profile()

        assert window.path_profile_active.text() == ""
        assert not window.chk_apply_profile.isChecked()
        assert window.chart_diagnostics_table.rowCount() == 1
        assert window.chart_diagnostics_table.item(0, 0).text() == "P01"
        assert "DeltaE2000 media 2.00" in window.chart_diagnostics_summary.text()
    finally:
        window.close()


def test_large_profile_payload_is_summarized_for_ui(qapp):
    payload = {
        "chart_captures_total": 1,
        "training_captures_total": 1,
        "chart_captures_used": 1,
        "profile_report_path": "/tmp/profile_report.json",
        "profile_status": {"status": "draft"},
        "profile": {
            "error_summary": {"mean_delta_e2000": 1.2, "max_delta_e2000": 3.4},
            "patch_errors": [
                {
                    "patch_id": f"P{i:03d}",
                    "delta_e76": float(i),
                    "delta_e2000": float(i),
                    "reference_lab": [50.0, 0.0, 0.0],
                    "profile_lab": [51.0, 0.0, 0.0],
                }
                for i in range(40)
            ],
        },
        "bulky_debug_blob": ["x" * 1000 for _ in range(80)],
    }

    window = ICCRawMainWindow()
    try:
        text = window._profile_output_text(payload)

        assert "La salida completa es grande" in text
        assert "worst_patch_errors" in text
        assert "bulky_debug_blob" not in text
    finally:
        window.close()


def test_gamut_refresh_populates_diagnostic_widget(tmp_path: Path, monkeypatch, qapp):
    profile = tmp_path / "camera.icc"
    profile.write_bytes(b"fake icc" * 32)
    captured: dict[str, object] = {}

    def fake_build_gamut_pair_diagnostics(**kwargs):
        captured.update(kwargs)
        return {
            "series": [
                {
                    "label": "ICC generado",
                    "color": "#f8fafc",
                    "role": "wire",
                    "points_lab": gui_module.np.asarray(
                        [[50.0, 0.0, 0.0], [60.0, 20.0, 10.0]],
                        dtype=gui_module.np.float64,
                    ),
                    "surface_rgb": gui_module.np.asarray(
                        [[0.0, 0.0, 0.0], [1.0, 0.5, 0.25]],
                        dtype=gui_module.np.float64,
                    ),
                    "quads": [],
                },
                {
                    "label": "sRGB",
                    "color": "#f97316",
                    "role": "solid",
                    "points_lab": gui_module.np.asarray(
                        [[50.0, 0.0, 0.0], [60.0, 20.0, 10.0]],
                        dtype=gui_module.np.float64,
                    ),
                    "surface_rgb": gui_module.np.asarray(
                        [[0.0, 0.0, 0.0], [1.0, 0.5, 0.25]],
                        dtype=gui_module.np.float64,
                    ),
                    "quads": [],
                }
            ],
            "comparisons": [{"source": "ICC generado", "target": "sRGB", "inside_ratio": 1.0}],
            "skipped": [],
        }

    def run_task(_label, task, on_success):
        on_success(task())

    monkeypatch.setattr(gui_module, "build_gamut_pair_diagnostics", fake_build_gamut_pair_diagnostics)
    monkeypatch.setattr(gui_module, "detect_system_display_profile", lambda: None)

    window = ICCRawMainWindow()
    try:
        window._start_background_task = run_task
        window.profile_out_path_edit.setText(str(profile))

        window._on_refresh_gamut_diagnostics()

        assert captured["profile_a"]["path"] == str(profile)
        assert captured["profile_b"] == {"kind": "standard", "key": "srgb"}
        assert len(window.gamut_3d_widget._series) == 2
        assert "ICC generado en sRGB: 100.0% dentro" in window.gamut_status_label.text()
        assert window.analysis_tabs.tabText(window.analysis_tabs.currentIndex()) == "Gamut 3D"
    finally:
        window.close()


def test_development_profile_applies_to_controls_and_queue(tmp_path: Path, qapp):
    root = tmp_path / "session"
    raw = root / "01_ORG" / "capture.NEF"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"raw")
    payload = create_session(root, name="Sesion perfiles")

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        _activate_fake_session_icc(window, root)
        window.development_profile_name_edit.setText("Ajuste base")
        window.spin_exposure.setValue(0.4)
        window.slider_noise_luma.setValue(18)
        window._save_current_development_profile()
        profile_id = window._active_development_profile_id

        window.spin_exposure.setValue(-0.6)
        window.slider_noise_luma.setValue(0)
        window._apply_development_profile_to_controls(profile_id)
        assert abs(window.spin_exposure.value() - 0.4) < 0.001
        assert window.slider_noise_luma.value() == 18

        window._queue_add_files([raw])
        assert window._develop_queue[0]["development_profile_id"] == profile_id
        saved_queue = load_session(root)["queue"]
        assert saved_queue[0]["development_profile_id"] == profile_id
    finally:
        window.close()


def test_legacy_generic_development_profile_normalizes_visible_controls(tmp_path: Path, qapp):
    root = tmp_path / "session"
    payload = create_session(root, name="Sesion perfil legado")
    manifest_path = root / "00_configuraciones" / "development_profiles" / "legacy" / "development_profile.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "id": "legacy",
                "name": "Legacy ProPhoto",
                "kind": "manual",
                "profile_type": "basic",
                "recipe": {
                    "output_space": "prophoto_rgb",
                    "output_linear": False,
                    "tone_curve": "gamma:1.8",
                    "white_balance_mode": "fixed",
                    "wb_multipliers": [1.0, 1.0, 1.0, 1.0],
                    "profiling_mode": True,
                },
                "detail_adjustments": {"sharpen": 40, "radius": 14, "noise_luma": 0, "noise_color": 0, "ca_red": 0, "ca_blue": 0},
                "render_adjustments": {},
            }
        ),
        encoding="utf-8",
    )

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        window._register_development_profile(
            {
                "id": "legacy",
                "name": "Legacy ProPhoto",
                "kind": "manual",
                "profile_type": "basic",
                "manifest_path": window._session_relative_or_absolute(manifest_path),
            },
            activate=False,
        )

        window._apply_development_profile_to_controls("legacy")

        assert window.combo_wb_mode.currentData() == "camera_metadata"
        assert window.check_profiling_mode.isChecked() is False
        assert window.slider_sharpen.value() == 40
    finally:
        window.close()


def test_queue_assignment_writes_and_reuses_raw_sidecar(tmp_path: Path, qapp):
    root = tmp_path / "session"
    raw = root / "01_ORG" / "capture.NEF"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"raw")
    payload = create_session(root, name="Sesion mochila")

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        _activate_fake_session_icc(window, root)
        window.development_profile_name_edit.setText("Carta base")
        window.spin_exposure.setValue(0.35)
        window._save_current_development_profile()
        profile_id = window._active_development_profile_id

        window._queue_add_files([raw])
        window.queue_table.selectRow(0)
        window._queue_assign_active_development_profile()

        assert raw_sidecar_path(raw).exists()
        sidecar = load_raw_sidecar(raw)
        assert sidecar["development_profile"]["id"] == profile_id
        assert sidecar["recipe"]["exposure_compensation"] == 0.35

        window._develop_queue = []
        window._active_development_profile_id = ""
        window._queue_add_files([raw])
        assert window._develop_queue[0]["development_profile_id"] == profile_id
    finally:
        window.close()


def test_queue_table_shows_per_file_progress_bar(tmp_path: Path, qapp):
    raw = tmp_path / "capture.NEF"
    raw.write_bytes(b"raw")

    window = ICCRawMainWindow()
    try:
        window._queue_add_files([raw])

        assert window.queue_table.columnCount() == 6
        progress = window.queue_table.cellWidget(0, 3)
        assert isinstance(progress, QtWidgets.QProgressBar)
        assert progress.value() == 0

        window._apply_queue_render_progress(
            {
                "source": str(raw),
                "status": "processing",
                "progress": 70,
                "message": "Escribiendo TIFF",
            }
        )

        progress = window.queue_table.cellWidget(0, 3)
        assert isinstance(progress, QtWidgets.QProgressBar)
        assert progress.value() == 70
        assert window._develop_queue[0]["status"] == "processing"
        assert window._develop_queue[0]["message"] == "Escribiendo TIFF"
        assert window.queue_table.item(0, 2).text() == "processing"
        assert window.queue_table.item(0, 5).text() == "Escribiendo TIFF"
    finally:
        window.close()


def test_queue_process_uses_inline_raw_sidecar_sharpening(tmp_path: Path, monkeypatch, qapp):
    root = tmp_path / "session"
    raw = root / "01_ORG" / "capture.NEF"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"raw")
    payload = create_session(root, name="Sesion cola mochila")
    recipe = Recipe(
        white_balance_mode="camera_metadata",
        output_space="prophoto_rgb",
        output_linear=False,
        tone_curve="gamma:1.8",
        profiling_mode=False,
    )
    write_raw_sidecar(
        raw,
        recipe=recipe,
        development_profile={"id": "", "name": "Ajustes imagen", "kind": "manual", "profile_type": "basic"},
        detail_adjustments={"sharpen": 72, "radius": 24, "noise_luma": 8, "noise_color": 3, "ca_red": 0, "ca_blue": 0},
        render_adjustments={"brightness_ev": 0.18, "contrast": 0.11},
        session_root=root,
        status="configured",
    )
    captured: dict[str, Any] = {}

    def run_task(_label, task, on_success):
        on_success(task())

    def fake_process_batch_files(**kwargs):
        captured.update(kwargs)
        src = kwargs["files"][0]
        out_path = Path(kwargs["out_dir"]) / f"{src.stem}.tiff"
        return {
            "input_files": len(kwargs["files"]),
            "output_dir": str(kwargs["out_dir"]),
            "outputs": [{"source": str(src), "output": str(out_path)}],
            "errors": [],
        }

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        window._start_background_task = run_task
        window._process_batch_files = fake_process_batch_files
        monkeypatch.setattr(window, "_resolve_proof_config_for_gui", lambda: ProbRawProofConfig(private_key_path=None))
        monkeypatch.setattr(window, "_resolve_c2pa_config_for_gui", lambda: None)
        window.slider_sharpen.setValue(0)
        window.slider_radius.setValue(10)
        window.slider_brightness.setValue(0)

        window._queue_add_files([raw])
        assert window._develop_queue[0]["development_profile_id"] == ""

        window._queue_process()

        assert captured["files"] == [raw]
        assert captured["apply_adjust"] is True
        assert captured["sharpen_amount"] == pytest.approx(0.72)
        assert captured["sharpen_radius"] == pytest.approx(2.4)
        assert captured["denoise_luma"] == pytest.approx(0.08)
        assert captured["render_adjustments"]["brightness_ev"] == pytest.approx(0.18)
        assert captured["render_adjustments"]["contrast"] == pytest.approx(0.11)
        assert captured["sidecar_detail_adjustments"]["sharpen"] == 72
        assert captured["development_profile"]["name"] == "Ajustes imagen"
        assert captured["development_profile"]["profile_type"] == "basic"
        assert captured["recipe"].output_space == "prophoto_rgb"
        assert window._develop_queue == []
    finally:
        window.close()


def test_batch_render_syncs_open_preview_with_written_sidecar(tmp_path: Path, monkeypatch, qapp):
    root = tmp_path / "session"
    raw = root / "01_ORG" / "capture.NEF"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"raw")
    payload = create_session(root, name="Sesion lote sync")
    recipe = Recipe(output_space="prophoto_rgb", output_linear=False, tone_curve="gamma:1.8")
    out_tiff = root / "02_DRV" / "capture.tiff"
    proof = out_tiff.with_suffix(out_tiff.suffix + ".probraw.proof.json")
    write_raw_sidecar(
        raw,
        recipe=recipe,
        development_profile={"id": "", "name": "Ajustes lote", "kind": "manual", "profile_type": "basic"},
        detail_adjustments={"sharpen": 190, "radius": 8, "noise_luma": 0, "noise_color": 63, "ca_red": 0, "ca_blue": 0},
        render_adjustments={"temperature_kelvin": 6360, "tint": 100.0, "brightness_ev": 0.58, "white_point": 0.879},
        session_root=root,
        output_tiff=out_tiff,
        proof_path=proof,
        status="rendered",
    )
    reloads: list[dict[str, object]] = []

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        window._selected_file = raw
        window._original_linear = gui_module.np.zeros((12, 16, 3), dtype=gui_module.np.float32)
        monkeypatch.setattr(window, "_on_load_selected", lambda *args, **kwargs: reloads.append(dict(kwargs)))
        window.spin_render_tint.setValue(0)
        window.slider_brightness.setValue(0)
        window.slider_sharpen.setValue(0)
        reloads.clear()

        window._sync_selected_after_batch_render(
            {
                "outputs": [
                    {
                        "source": str(raw),
                        "output": str(out_tiff),
                        "raw_sidecar": str(raw_sidecar_path(raw)),
                    }
                ]
            }
        )

        assert window.spin_render_tint.value() == pytest.approx(100.0)
        assert window.slider_brightness.value() == 58
        assert window.slider_sharpen.value() == 190
        assert window.slider_noise_color.value() == 63
        assert reloads == [{"show_message": False}]
    finally:
        window.close()


def test_color_contrast_adjustments_autosave_to_raw_sidecar_and_badge(tmp_path: Path, qapp):
    root = tmp_path / "session"
    raw = root / "01_ORG" / "capture.NEF"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"raw")
    payload = create_session(root, name="Sesion autosave color")

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        _activate_fake_session_icc(window, root)
        window._selected_file = raw

        window.slider_brightness.setValue(25)
        assert window._render_adjustment_sidecar_timer.isActive()
        window._flush_render_adjustment_sidecar_persist()

        sidecar = load_raw_sidecar(raw)
        assert sidecar["render_adjustments"]["brightness_ev"] == pytest.approx(0.25)
        assert "color_contrast" in window._raw_adjustment_profile_badges(raw)
        assert "Color/contraste: ajustes propios" in window._raw_adjustment_profile_badge_summary(raw)

        window.slider_contrast.setValue(17)
        window._flush_render_adjustment_sidecar_persist()
        updated = load_raw_sidecar(raw)
        assert updated["render_adjustments"]["brightness_ev"] == pytest.approx(0.25)
        assert updated["render_adjustments"]["contrast"] == pytest.approx(0.17)
    finally:
        window.close()


def test_detail_adjustments_autosave_to_raw_sidecar_and_badge(tmp_path: Path, qapp):
    root = tmp_path / "session"
    raw = root / "01_ORG" / "capture.NEF"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"raw")
    payload = create_session(root, name="Sesion autosave nitidez")

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        _activate_fake_session_icc(window, root)
        window._selected_file = raw

        window.slider_sharpen.setValue(82)
        assert window._detail_adjustment_sidecar_timer.isActive()
        window._flush_detail_adjustment_sidecar_persist()

        sidecar = load_raw_sidecar(raw)
        assert sidecar["detail_adjustments"]["sharpen"] == 82
        assert "detail" in window._raw_adjustment_profile_badges(raw)
        assert "Nitidez: ajustes propios" in window._raw_adjustment_profile_badge_summary(raw)

        window.slider_radius.setValue(21)
        window._flush_detail_adjustment_sidecar_persist()
        updated = load_raw_sidecar(raw)
        assert updated["detail_adjustments"]["sharpen"] == 82
        assert updated["detail_adjustments"]["radius"] == 21
    finally:
        window.close()


def test_queue_process_prefers_raw_sidecar_over_registered_profile_id(tmp_path: Path, monkeypatch, qapp):
    root = tmp_path / "session"
    raw = root / "01_ORG" / "capture.NEF"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"raw")
    payload = create_session(root, name="Sesion cola mochila prioritaria")
    recipe = Recipe(
        white_balance_mode="camera_metadata",
        output_space="prophoto_rgb",
        output_linear=False,
        tone_curve="gamma:1.8",
        profiling_mode=False,
    )
    captured: dict[str, Any] = {}

    def run_task(_label, task, on_success):
        on_success(task())

    def fake_process_batch_files(**kwargs):
        captured.update(kwargs)
        src = kwargs["files"][0]
        out_path = Path(kwargs["out_dir"]) / f"{src.stem}.tiff"
        return {
            "input_files": len(kwargs["files"]),
            "output_dir": str(kwargs["out_dir"]),
            "outputs": [{"source": str(src), "output": str(out_path)}],
            "errors": [],
        }

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        _activate_fake_session_icc(window, root)
        window.development_profile_name_edit.setText("Perfil registrado")
        window.slider_brightness.setValue(3)
        window._save_current_development_profile()
        profile_id = window._active_development_profile_id

        write_raw_sidecar(
            raw,
            recipe=recipe,
            development_profile={
                "id": profile_id,
                "name": "Ajustes imagen",
                "kind": "manual",
                "profile_type": "basic",
            },
            detail_adjustments={"sharpen": 0, "radius": 10, "noise_luma": 0, "noise_color": 0, "ca_red": 0, "ca_blue": 0},
            render_adjustments={"brightness_ev": 0.44, "contrast": 0.21},
            session_root=root,
            status="configured",
        )

        window._start_background_task = run_task
        window._process_batch_files = fake_process_batch_files
        monkeypatch.setattr(window, "_resolve_proof_config_for_gui", lambda: ProbRawProofConfig(private_key_path=None))
        monkeypatch.setattr(window, "_resolve_c2pa_config_for_gui", lambda: None)

        window._queue_add_files([raw])
        assert window._develop_queue[0]["development_profile_id"] == profile_id
        window._queue_process()

        assert captured["render_adjustments"]["brightness_ev"] == pytest.approx(0.44)
        assert captured["render_adjustments"]["contrast"] == pytest.approx(0.21)
        assert captured["development_profile"]["id"] == profile_id
        assert window._develop_queue == []
    finally:
        window.close()


def test_queue_process_removes_successes_but_keeps_errors(tmp_path: Path, monkeypatch, qapp):
    root = tmp_path / "session"
    ok_raw = root / "01_ORG" / "ok.NEF"
    bad_raw = root / "01_ORG" / "bad.NEF"
    ok_raw.parent.mkdir(parents=True)
    ok_raw.write_bytes(b"raw")
    bad_raw.write_bytes(b"raw")
    payload = create_session(root, name="Sesion cola mixta")

    def run_task(_label, task, on_success):
        on_success(task())

    def fake_process_batch_files(**kwargs):
        outputs = []
        errors = []
        for src in kwargs["files"]:
            if Path(src).name == "ok.NEF":
                outputs.append({"source": str(src), "output": str(Path(kwargs["out_dir"]) / f"{src.stem}.tiff")})
            else:
                errors.append({"source": str(src), "error": "fallo simulado"})
        return {
            "input_files": len(kwargs["files"]),
            "output_dir": str(kwargs["out_dir"]),
            "outputs": outputs,
            "errors": errors,
        }

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        _activate_fake_session_icc(window, root)
        window._start_background_task = run_task
        window._process_batch_files = fake_process_batch_files
        monkeypatch.setattr(window, "_resolve_proof_config_for_gui", lambda: ProbRawProofConfig(private_key_path=None))
        monkeypatch.setattr(window, "_resolve_c2pa_config_for_gui", lambda: None)

        window._queue_add_files([ok_raw, bad_raw])
        window._queue_process()

        assert [Path(item["source"]).name for item in window._develop_queue] == ["bad.NEF"]
        assert window._develop_queue[0]["status"] == "error"
        assert window._develop_queue[0]["message"] == "fallo simulado"
        saved_queue = load_session(root)["queue"]
        assert [Path(item["source"]).name for item in saved_queue] == ["bad.NEF"]
    finally:
        window.close()


def test_raw_sidecar_without_registered_profile_clears_stale_active_profile(tmp_path: Path, qapp):
    root = tmp_path / "session"
    raw = root / "01_ORG" / "capture.NEF"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"raw")
    payload = create_session(root, name="Sesion perfil basico")

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        _activate_fake_session_icc(window, root)
        window.development_profile_name_edit.setText("Perfil anterior")
        window.spin_exposure.setValue(-0.35)
        window._save_current_development_profile()
        stale_profile_id = window._active_development_profile_id
        assert stale_profile_id

        write_raw_sidecar(
            raw,
            recipe=Recipe(exposure_compensation=0.75),
            development_profile={"id": "", "name": "Ajustes actuales", "kind": "manual", "profile_type": "basic"},
            detail_adjustments={"sharpen": 30, "radius": 12, "noise_luma": 5, "noise_color": 7, "ca_red": 0, "ca_blue": 0},
            render_adjustments={"brightness_ev": 0.22, "contrast": 0.18},
            session_root=root,
            status="configured",
        )

        assert window._apply_raw_sidecar_to_controls(raw) is True

        assert window._active_development_profile_id == ""
        assert window.spin_exposure.value() == pytest.approx(0.75)
        assert window.slider_brightness.value() == 22
        assert window.slider_contrast.value() == 18
        settings = window._development_profile_settings(window._active_development_profile_id)
        assert settings["render_adjustments"]["brightness_ev"] == pytest.approx(0.22)
        assert settings["render_adjustments"]["contrast"] == pytest.approx(0.18)
    finally:
        window.close()


def test_file_selection_without_sidecar_resets_previous_adjustment_controls(tmp_path: Path, qapp):
    root = tmp_path / "session"
    raw_dir = root / "01_ORG"
    adjusted = raw_dir / "adjusted.NEF"
    unconfigured = raw_dir / "unconfigured.NEF"
    raw_dir.mkdir(parents=True)
    adjusted.write_bytes(b"adjusted raw")
    unconfigured.write_bytes(b"unconfigured raw")
    payload = create_session(root, name="Sesion cambio ajustes")
    write_raw_sidecar(
        adjusted,
        recipe=Recipe(
            exposure_compensation=0.85,
            white_balance_mode="fixed",
            wb_multipliers=[1.15, 1.0, 0.92, 1.0],
            output_space="scene_linear_camera_rgb",
            output_linear=True,
            tone_curve="linear",
            profiling_mode=True,
        ),
        development_profile={"id": "", "name": "Ajustes actuales", "kind": "manual", "profile_type": "basic"},
        detail_adjustments={"sharpen": 55, "radius": 18, "noise_luma": 12, "noise_color": 9, "ca_red": 25, "ca_blue": -15},
        render_adjustments={"brightness_ev": 0.31, "contrast": 0.22, "black_point": 0.04, "midtone": 1.12},
        session_root=root,
        status="configured",
    )

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        window._set_current_directory(raw_dir)
        items = {
            Path(str(window.file_list.item(row).data(QtCore.Qt.UserRole))).name: window.file_list.item(row)
            for row in range(window.file_list.count())
        }

        window.file_list.setCurrentItem(items[adjusted.name])
        window._selection_load_timer.stop()
        window._metadata_timer.stop()

        assert window._selected_file == adjusted
        assert window.spin_exposure.value() == pytest.approx(0.85)
        assert window.slider_sharpen.value() == 55
        assert window.slider_brightness.value() == 31
        assert window.slider_contrast.value() == 22

        window._viewer_rotation = 90.0
        window._image_crop_rect = (4, 5, 20, 30)
        window._image_crop_normalized_rect = (0.1, 0.1, 0.4, 0.5)
        _activate_fake_session_icc(window, root)
        assert window.chk_apply_profile.isChecked()
        window._active_development_profile_id = "stale-profile"
        window.file_list.setCurrentItem(items[unconfigured.name])
        window._selection_load_timer.stop()
        window._metadata_timer.stop()

        assert window._selected_file == unconfigured
        assert window._active_development_profile_id == ""
        assert window.path_profile_active.text() == ""
        assert window.chk_apply_profile.isChecked() is False
        assert window.spin_exposure.value() == pytest.approx(0.0)
        assert window.combo_wb_mode.currentData() == "camera_metadata"
        assert window.combo_output_space.currentText().strip() == "prophoto_rgb"
        assert window.check_output_linear.isChecked() is False
        assert window.check_profiling_mode.isChecked() is False
        assert window.slider_sharpen.value() == 0
        assert window.slider_radius.value() == 10
        assert window.slider_noise_luma.value() == 0
        assert window.slider_noise_color.value() == 0
        assert window.slider_ca_red.value() == 0
        assert window.slider_ca_blue.value() == 0
        assert window.slider_brightness.value() == 0
        assert window.slider_black_point.value() == 0
        assert window.slider_contrast.value() == 0
        assert window.slider_midtone.value() == 100
        assert float(window._viewer_rotation) == pytest.approx(0.0)
        assert window._image_crop_rect is None
        assert window._image_crop_normalized_rect is None
    finally:
        window._selection_load_timer.stop()
        window._metadata_timer.stop()
        window.close()


def test_partial_raw_sidecar_resets_missing_adjustment_blocks(tmp_path: Path, qapp):
    root = tmp_path / "session"
    raw = root / "01_ORG" / "partial.NEF"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"partial raw")
    payload = create_session(root, name="Sesion mochila parcial")
    raw_sidecar_path(raw).write_text(
        json.dumps(
            {
                "schema": "org.probatia.probraw.raw-sidecar.v1",
                "recipe": {"exposure_compensation": -0.4},
                "development_profile": {"id": "", "name": "", "kind": "", "profile_type": "basic"},
            }
        ),
        encoding="utf-8",
    )

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        window.slider_sharpen.setValue(80)
        window.slider_radius.setValue(24)
        window.slider_noise_luma.setValue(30)
        window.slider_brightness.setValue(45)
        window.slider_contrast.setValue(33)
        window._viewer_rotation = 270.0
        window._image_crop_rect = (4, 5, 20, 30)
        window._image_crop_normalized_rect = (0.1, 0.1, 0.4, 0.5)
        window._active_development_profile_id = "stale-profile"
        _activate_fake_session_icc(window, root)

        assert window._apply_raw_sidecar_to_controls(raw) is True

        assert window._active_development_profile_id == ""
        assert window.path_profile_active.text() == ""
        assert window.chk_apply_profile.isChecked() is False
        assert window.spin_exposure.value() == pytest.approx(-0.4)
        assert window.slider_sharpen.value() == 0
        assert window.slider_radius.value() == 10
        assert window.slider_noise_luma.value() == 0
        assert window.slider_brightness.value() == 0
        assert window.slider_contrast.value() == 0
        assert float(window._viewer_rotation) == pytest.approx(0.0)
        assert window._image_crop_rect is None
        assert window._image_crop_normalized_rect is None
    finally:
        window.close()


def test_raw_sidecar_restores_image_geometry(tmp_path: Path, qapp):
    root = tmp_path / "session"
    raw = root / "01_ORG" / "rotated.NEF"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"rotated raw")
    payload = create_session(root, name="Sesion geometria")
    write_raw_sidecar(
        raw,
        recipe=Recipe(output_space="prophoto_rgb", output_linear=False),
        development_profile={"id": "", "name": "Ajustes actuales", "kind": "manual", "profile_type": "basic"},
        detail_adjustments={},
        render_adjustments={
            "brightness_ev": 0.12,
            "geometry": {
                "crop_rect": [3, 4, 25, 30],
                "crop_normalized": [0.1, 0.2, 0.5, 0.6],
                "rotation_degrees": -90.0,
            },
        },
        session_root=root,
        status="configured",
    )

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)

        assert window._apply_raw_sidecar_to_controls(raw) is True

        assert window.slider_brightness.value() == 12
        assert float(window._viewer_rotation) == pytest.approx(270.0)
        assert window._image_crop_rect == (3, 4, 25, 30)
        assert window._image_crop_normalized_rect == pytest.approx((0.1, 0.2, 0.5, 0.6))
    finally:
        window.close()


def test_current_raw_settings_sidecar_persists_image_geometry(tmp_path: Path, qapp):
    root = tmp_path / "session"
    raw = root / "01_ORG" / "capture.NEF"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"raw")
    payload = create_session(root, name="Sesion geometria actual")

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        window._selected_file = raw
        window._set_combo_text(window.combo_output_space, "prophoto_rgb")
        window._apply_output_space_defaults_to_controls("prophoto_rgb")
        window._viewer_rotation = 90.0
        window._image_crop_rect = (3, 4, 25, 30)
        window._image_crop_normalized_rect = (0.1, 0.2, 0.5, 0.6)

        window._write_current_development_settings_to_raw(raw)

        sidecar = load_raw_sidecar(raw)
        geometry = sidecar["render_adjustments"]["geometry"]
        assert geometry["rotation_degrees"] == pytest.approx(90.0)
        assert geometry["crop_rect"] == [3, 4, 25, 30]
        assert geometry["crop_normalized"] == pytest.approx([0.1, 0.2, 0.5, 0.6])
    finally:
        window.close()


def test_file_selection_flushes_pending_geometry_to_previous_raw(tmp_path: Path, qapp):
    root = tmp_path / "session"
    raw_a = root / "01_ORG" / "a.NEF"
    raw_b = root / "01_ORG" / "b.NEF"
    raw_a.parent.mkdir(parents=True)
    raw_a.write_bytes(b"a")
    raw_b.write_bytes(b"b")
    payload = create_session(root, name="Sesion giro pendiente")

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        window.file_list.clear()
        window._file_items_by_key.clear()
        for raw in (raw_a, raw_b):
            item = QtWidgets.QListWidgetItem(raw.name)
            item.setData(QtCore.Qt.UserRole, str(raw))
            window.file_list.addItem(item)

        window.file_list.setCurrentRow(0)
        qapp.processEvents()
        window._selection_load_timer.stop()
        assert window._selected_file == raw_a

        window._viewer_rotation = 90.0
        window._schedule_render_adjustment_sidecar_persist()
        assert window._render_adjustment_sidecar_timer.isActive()

        window.file_list.setCurrentRow(1)
        qapp.processEvents()
        window._selection_load_timer.stop()

        assert window._selected_file == raw_b
        assert not window._render_adjustment_sidecar_timer.isActive()
        assert float(window._viewer_rotation) == pytest.approx(0.0)

        sidecar_a = load_raw_sidecar(raw_a)
        geometry_a = sidecar_a["render_adjustments"]["geometry"]
        assert geometry_a["rotation_degrees"] == pytest.approx(90.0)
        assert not raw_sidecar_path(raw_b).exists()
    finally:
        window._selection_load_timer.stop()
        window.close()


def test_raw_sidecar_generic_output_normalizes_profile_mode_for_controls(tmp_path: Path, qapp):
    root = tmp_path / "session"
    raw = root / "01_ORG" / "generic.NEF"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"generic raw")
    payload = create_session(root, name="Sesion prophoto visible")
    write_raw_sidecar(
        raw,
        recipe=Recipe(
            output_space="prophoto_rgb",
            output_linear=False,
            tone_curve="gamma:1.8",
            white_balance_mode="fixed",
            wb_multipliers=[1.0, 1.0, 1.0, 1.0],
            profiling_mode=True,
        ),
        development_profile={"id": "", "name": "Ajustes antiguos", "kind": "manual", "profile_type": "basic"},
        detail_adjustments={"sharpen": 10, "radius": 10, "noise_luma": 0, "noise_color": 0, "ca_red": 0, "ca_blue": 0},
        render_adjustments={},
        session_root=root,
        status="configured",
    )

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)

        assert window._apply_raw_sidecar_to_controls(raw) is True

        assert window.combo_output_space.currentText().strip() == "prophoto_rgb"
        assert window.combo_wb_mode.currentData() == "camera_metadata"
        assert window.check_profiling_mode.isChecked() is False
        assert window.slider_sharpen.value() == 10
    finally:
        window.close()


def test_file_selection_clears_stale_mtf_roi_before_sidecar_slider_updates(tmp_path: Path, qapp):
    root = tmp_path / "session"
    raw_dir = root / "01_ORG"
    first = raw_dir / "first.NEF"
    second = raw_dir / "second.NEF"
    raw_dir.mkdir(parents=True)
    first.write_bytes(b"first raw")
    second.write_bytes(b"second raw")
    payload = create_session(root, name="Sesion cambio MTF")
    write_raw_sidecar(
        second,
        recipe=Recipe(),
        development_profile={"id": "", "name": "Ajustes actuales", "kind": "manual", "profile_type": "basic"},
        detail_adjustments={"sharpen": 20, "radius": 10, "noise_luma": 0, "noise_color": 0, "ca_red": 0, "ca_blue": 0},
        render_adjustments={"brightness_ev": 0.31, "contrast": 0.12},
        session_root=root,
        status="configured",
    )

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        window._set_current_directory(raw_dir)
        second_item = next(
            window.file_list.item(row)
            for row in range(window.file_list.count())
            if window.file_list.item(row).data(QtCore.Qt.UserRole) == str(second)
        )
        image = gui_module.np.zeros((96, 96, 3), dtype=gui_module.np.float32)
        window._selected_file = first
        window._original_linear = image
        window._preview_srgb = image
        window._mtf_roi = (12, 12, 48, 48)
        window.check_mtf_auto_update.setChecked(True)

        window.file_list.setCurrentItem(second_item)
        window._selection_load_timer.stop()
        window._metadata_timer.stop()

        assert window._selected_file == second
        assert window._mtf_roi is None
        assert not window._mtf_refresh_timer.isActive()
        assert window.slider_brightness.value() == 31
    finally:
        window._selection_load_timer.stop()
        window._metadata_timer.stop()
        window._mtf_refresh_timer.stop()
        window.close()


def test_raw_sidecar_write_errors_propagate(tmp_path: Path, monkeypatch, qapp):
    root = tmp_path / "session"
    raw = root / "01_ORG" / "capture.NEF"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"raw")
    payload = create_session(root, name="Sesion mochila")

    def boom(*_args, **_kwargs):
        raise RuntimeError("disk full")

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        monkeypatch.setattr(gui_module, "write_raw_sidecar", boom)

        with pytest.raises(RuntimeError, match="disk full"):
            window._write_raw_settings_sidecar(
                raw,
                recipe=Recipe(output_space="scene_linear_camera_rgb", output_linear=True),
                development_profile=None,
                detail_adjustments={},
                render_adjustments={},
                profile_path=None,
                color_management_mode="no_profile",
            )
    finally:
        window.close()


def test_chart_profile_assignment_marks_raw_as_advanced_and_can_be_pasted(tmp_path: Path, qapp):
    root = tmp_path / "session"
    raw_dir = root / "01_ORG"
    source = raw_dir / "chart.NEF"
    target = raw_dir / "target.NEF"
    raw_dir.mkdir(parents=True)
    source.write_bytes(b"chart raw")
    target.write_bytes(b"target raw")
    payload = create_session(root, name="Sesion carta")

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        _activate_fake_session_icc(window, root)
        window._set_current_directory(raw_dir)

        paths = window._session_paths_from_root(root)
        profile_path = paths["profiles"] / "session.icc"
        profile_report = paths["config"] / "profile_report.json"
        recipe_path = paths["config"] / "recipe_calibrated.yml"
        manifest_path = paths["config"] / "development_profile.json"
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        profile_report.parent.mkdir(parents=True, exist_ok=True)
        profile_path.write_bytes(b"icc")
        profile_report.write_text("{}", encoding="utf-8")
        gui_module.save_recipe(Recipe(exposure_compensation=0.45), recipe_path)
        manifest_path.write_text("{}", encoding="utf-8")

        profile_id = window._register_chart_development_profile(
            name="Carta D50",
            development_profile_path=manifest_path,
            calibrated_recipe_path=recipe_path,
            icc_profile_path=profile_path,
            profile_report_path=profile_report,
        )
        assert window._assign_development_profile_to_raw_files(profile_id, [source]) == 1

        source_sidecar = load_raw_sidecar(source)
        assert source_sidecar["development_profile"]["kind"] == "chart"
        assert source_sidecar["development_profile"]["profile_type"] == "advanced"
        marked = window._display_icon_for_path(
            source,
            window._icon_from_thumbnail_array(gui_module.np.full((48, 48, 3), 96, dtype=gui_module.np.uint8)),
        )
        pixmap = marked.pixmap(window.file_list.iconSize())
        assert pixmap.height() > pixmap.width()
        assert window._raw_adjustment_profile_badges(source) == ["icc"]

        source_item = next(
            window.file_list.item(row)
            for row in range(window.file_list.count())
            if window.file_list.item(row).data(QtCore.Qt.UserRole) == str(source)
        )
        target_item = next(
            window.file_list.item(row)
            for row in range(window.file_list.count())
            if window.file_list.item(row).data(QtCore.Qt.UserRole) == str(target)
        )
        window.file_list.clearSelection()
        source_item.setSelected(True)
        window.file_list.setCurrentItem(source_item)
        window._selection_load_timer.stop()
        window._metadata_timer.stop()
        window._copy_development_settings_from_selected()

        window.file_list.clearSelection()
        target_item.setSelected(True)
        window.file_list.setCurrentItem(target_item)
        window._selection_load_timer.stop()
        window._metadata_timer.stop()
        window._paste_development_settings_to_selected()

        pasted = load_raw_sidecar(target)
        assert pasted["development_profile"]["kind"] == "chart"
        assert pasted["development_profile"]["profile_type"] == "advanced"
        assert pasted["recipe"]["exposure_compensation"] == 0.45
        assert "Perfil de ajuste avanzado" in target_item.toolTip()
        assert "Perfiles aplicados" in target_item.toolTip()
    finally:
        window.close()


def test_generate_profile_uses_explicit_color_reference_selection(tmp_path: Path, monkeypatch, qapp):
    chart_01 = tmp_path / "chart_01.tiff"
    chart_02 = tmp_path / "chart_02.tiff"
    Image.new("RGB", (16, 16), (20, 120, 220)).save(chart_01)
    Image.new("RGB", (16, 16), (220, 120, 20)).save(chart_02)

    captured: dict[str, object] = {}

    def fake_auto_generate_profile_from_charts(**kwargs):
        captured.update(kwargs)
        return {"chart_captures_used": 2}

    def run_task(_label, task, _on_success):
        captured["payload"] = task()

    monkeypatch.setattr(gui_module.ReferenceCatalog, "from_path", staticmethod(lambda _path: object()))
    monkeypatch.setattr(gui_module, "auto_generate_profile_from_charts", fake_auto_generate_profile_from_charts)

    window = ICCRawMainWindow()
    try:
        window._start_background_task = run_task
        window._selected_chart_files = [chart_02, chart_01]
        window.profile_charts_dir.setText(str(tmp_path / "unused"))

        window._on_generate_profile()

        assert captured["chart_capture_files"] == [chart_02, chart_01]
        assert captured["chart_captures_dir"] == tmp_path / "unused"
    finally:
        window.close()


def test_app_icon_resource_is_packaged(qapp):
    icon_path = gui_module._app_icon_path()
    assert icon_path is not None
    assert icon_path.name == "probraw-icon.png"
    assert icon_path.exists()
    assert not gui_module._app_icon().isNull()


def test_window_uses_probraw_app_icon(qapp):
    window = ICCRawMainWindow()
    try:
        assert not window.windowIcon().isNull()
    finally:
        window.close()


def test_startup_memory_ignores_stale_paths_and_falls_back_to_home(tmp_path: Path, qapp):
    settings = gui_module._make_app_settings()
    settings.setValue("session/last_root", str(tmp_path / "missing_session"))
    settings.setValue("browser/last_dir", str(tmp_path / "missing_dir"))
    settings.sync()

    window = ICCRawMainWindow()
    try:
        assert window._current_dir == Path.home().expanduser().resolve()
        assert window._settings.value("session/last_root") is None
        assert Path(str(window._settings.value("browser/last_dir"))).expanduser().resolve() == Path.home().resolve()
    finally:
        window.close()


def test_window_close_waits_for_running_task_thread(qapp):
    window = ICCRawMainWindow()
    thread = gui_module.TaskThread(lambda: QtCore.QThread.msleep(50))
    window._threads.append(thread)
    thread.start()
    try:
        window.close()

        assert not window._threads
        try:
            assert not thread.isRunning()
        except RuntimeError:
            pass
    finally:
        if thread in getattr(window, "_threads", []):
            window._threads.remove(thread)
        try:
            if thread.isRunning():
                thread.wait(1000)
        except RuntimeError:
            pass


def test_shutdown_background_threads_does_not_wait_forever(qapp):
    window = ICCRawMainWindow()
    thread = gui_module.TaskThread(lambda: QtCore.QThread.msleep(5000))
    window._threads.append(thread)
    thread.start()
    started = time.monotonic()
    try:
        window._shutdown_background_threads(timeout_ms=10)

        assert time.monotonic() - started < 2.0
        assert not window._threads
        try:
            assert not thread.isRunning()
        except RuntimeError:
            pass
    finally:
        if thread in getattr(window, "_threads", []):
            window._threads.remove(thread)
        try:
            if thread.isRunning():
                thread.terminate()
                thread.wait(1000)
        except RuntimeError:
            pass
        window.close()


def test_thumbnail_copy_paste_development_settings_writes_raw_sidecars(tmp_path: Path, qapp):
    root = tmp_path / "session"
    raw_dir = root / "01_ORG"
    source = raw_dir / "source.NEF"
    target = raw_dir / "target.NEF"
    raw_dir.mkdir(parents=True)
    source.write_bytes(b"source raw")
    target.write_bytes(b"target raw")
    payload = create_session(root, name="Sesion copiar pegar")

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        _activate_fake_session_icc(window, root)
        window._set_current_directory(raw_dir)

        source_item = next(
            window.file_list.item(row)
            for row in range(window.file_list.count())
            if window.file_list.item(row).data(QtCore.Qt.UserRole) == str(source)
        )
        target_item = next(
            window.file_list.item(row)
            for row in range(window.file_list.count())
            if window.file_list.item(row).data(QtCore.Qt.UserRole) == str(target)
        )

        window.file_list.clearSelection()
        source_item.setSelected(True)
        window.file_list.setCurrentItem(source_item)
        window._selection_load_timer.stop()
        window._metadata_timer.stop()
        window.spin_exposure.setValue(0.75)
        window.slider_brightness.setValue(22)
        window._save_current_development_settings_to_selected()

        assert raw_sidecar_path(source).exists()
        source_sidecar = load_raw_sidecar(source)
        assert source_sidecar["development_profile"]["profile_type"] == "basic"
        assert "Perfil de ajuste básico" in source_item.toolTip()
        marked = window._display_icon_for_path(
            source,
            window._icon_from_thumbnail_array(gui_module.np.full((48, 48, 3), 96, dtype=gui_module.np.uint8)),
        )
        pixmap = marked.pixmap(window.file_list.iconSize())
        assert pixmap.height() > pixmap.width()
        assert window._raw_adjustment_profile_badges(source) == ["icc", "color_contrast"]

        window._copy_development_settings_from_selected()

        window.file_list.clearSelection()
        target_item.setSelected(True)
        window.file_list.setCurrentItem(target_item)
        window._selection_load_timer.stop()
        window._metadata_timer.stop()
        window.spin_exposure.setValue(-0.5)
        window.slider_brightness.setValue(0)
        window._paste_development_settings_to_selected()

        pasted = load_raw_sidecar(target)
        assert pasted["development_profile"]["profile_type"] == "basic"
        assert pasted["recipe"]["exposure_compensation"] == 0.75
        assert pasted["render_adjustments"]["brightness_ev"] == 0.22
        assert "Perfiles aplicados" in target_item.toolTip()
        assert "Perfil de ajuste básico" in target_item.toolTip()
    finally:
        window.close()


def test_thumbnail_copy_paste_individual_adjustment_categories_to_multiple_targets(tmp_path: Path, qapp):
    root = tmp_path / "session"
    raw_dir = root / "01_ORG"
    source = raw_dir / "source.NEF"
    target_a = raw_dir / "target_a.NEF"
    target_b = raw_dir / "target_b.NEF"
    raw_dir.mkdir(parents=True)
    for path in (source, target_a, target_b):
        path.write_bytes(path.name.encode("utf-8"))
    payload = create_session(root, name="Sesion copiar ajustes separados")

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        icc_path = _activate_fake_session_icc(window, root)

        source_render = window._default_render_adjustment_state()
        source_render.update({"brightness_ev": 0.41, "contrast": 0.18})
        source_detail = window._default_detail_adjustment_state()
        source_detail.update({"sharpen": 92, "radius": 16})
        source_recipe = Recipe(
            output_space="scene_linear_camera_rgb",
            demosaic_algorithm="amaze",
            false_color_suppression_steps=3,
            four_color_rgb=True,
        )
        target_render = window._default_render_adjustment_state()
        target_detail = window._default_detail_adjustment_state()
        target_detail.update({"sharpen": 7, "radius": 11})
        target_recipe = Recipe(output_space="scene_linear_camera_rgb", demosaic_algorithm="ahd")

        window._write_raw_settings_sidecar(
            source,
            recipe=source_recipe,
            development_profile={"id": "source-full", "name": "Fuente", "kind": "manual", "profile_type": "basic"},
            adjustment_profiles={
                "icc": {"id": "icc-session", "name": "ICC sesion", "kind": "icc"},
                "color_contrast": {"id": "", "name": "Color fuente", "kind": "color_contrast"},
                "detail": {"id": "", "name": "Nitidez fuente", "kind": "detail"},
                "raw_export": {"id": "", "name": "RAW fuente", "kind": "raw_export"},
            },
            detail_adjustments=source_detail,
            render_adjustments=source_render,
            profile_path=icc_path,
            color_management_mode="camera_rgb_with_input_icc",
        )
        for target in (target_a, target_b):
            window._write_raw_settings_sidecar(
                target,
                recipe=target_recipe,
                development_profile={"id": "", "name": "Destino", "kind": "manual", "profile_type": "basic"},
                adjustment_profiles={},
                detail_adjustments=target_detail,
                render_adjustments=target_render,
                profile_path=icc_path,
                color_management_mode="camera_rgb_with_input_icc",
            )

        window._set_current_directory(raw_dir)
        items = {
            Path(str(window.file_list.item(row).data(QtCore.Qt.UserRole))).name: window.file_list.item(row)
            for row in range(window.file_list.count())
        }

        window.file_list.clearSelection()
        items[source.name].setSelected(True)
        window.file_list.setCurrentItem(items[source.name])
        window._copy_adjustments_from_selected(("color_contrast",))

        window.file_list.clearSelection()
        window.file_list.setCurrentItem(items[target_a.name])
        for target in (target_a, target_b):
            items[target.name].setSelected(True)
        window._paste_adjustments_to_selected()

        pasted_a = load_raw_sidecar(target_a)
        pasted_b = load_raw_sidecar(target_b)
        assert pasted_a["render_adjustments"]["brightness_ev"] == pytest.approx(0.41)
        assert pasted_b["render_adjustments"]["contrast"] == pytest.approx(0.18)
        assert pasted_a["detail_adjustments"]["sharpen"] == 7
        assert pasted_a["recipe"]["demosaic_algorithm"] == "ahd"
        assert "color_contrast" in window._raw_adjustment_profile_badges(target_a)

        window.file_list.clearSelection()
        items[source.name].setSelected(True)
        window.file_list.setCurrentItem(items[source.name])
        window._copy_adjustments_from_selected(("detail", "raw_export"))

        window.file_list.clearSelection()
        items[target_a.name].setSelected(True)
        window.file_list.setCurrentItem(items[target_a.name])
        window._paste_adjustments_to_selected()

        updated = load_raw_sidecar(target_a)
        assert updated["render_adjustments"]["brightness_ev"] == pytest.approx(0.41)
        assert updated["detail_adjustments"]["sharpen"] == 92
        assert updated["recipe"]["demosaic_algorithm"] == "amaze"
        assert updated["recipe"]["false_color_suppression_steps"] == 3
        assert {"color_contrast", "detail", "raw_export"}.issubset(set(window._raw_adjustment_profile_badges(target_a)))
    finally:
        window.close()


def test_raw_export_adjustments_autosave_to_raw_sidecar_and_badge(tmp_path: Path, qapp):
    root = tmp_path / "session"
    raw = root / "01_ORG" / "capture.NEF"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"raw")
    payload = create_session(root, name="Sesion autosave raw")

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        _activate_fake_session_icc(window, root)
        window._selected_file = raw

        window._set_combo_data(window.combo_demosaic, "ahd")
        assert window._raw_export_sidecar_timer.isActive()
        window._flush_raw_export_sidecar_persist()

        sidecar = load_raw_sidecar(raw)
        assert sidecar["recipe"]["demosaic_algorithm"] == "ahd"
        assert "raw_export" in window._raw_adjustment_profile_badges(raw)
        assert "RAW: ajustes propios" in window._raw_adjustment_profile_badge_summary(raw)

        window._set_combo_data(window.combo_black_mode, "fixed")
        window.spin_black_value.setValue(128)
        window._flush_raw_export_sidecar_persist()
        updated = load_raw_sidecar(raw)
        assert updated["recipe"]["demosaic_algorithm"] == "ahd"
        assert updated["recipe"]["black_level_mode"] == "fixed:128"
    finally:
        window.close()


def test_separate_adjustment_profiles_are_saved_and_applied_to_raw_sidecars(tmp_path: Path, qapp):
    root = tmp_path / "session"
    raw_dir = root / "01_ORG"
    raw_dir.mkdir(parents=True)
    raw = raw_dir / "target.NEF"
    raw.write_bytes(b"raw")
    payload = create_session(root, name="Sesion perfiles separados")

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        _activate_fake_session_icc(window, root)

        window.color_contrast_profile_name_edit.setText("Color caso")
        window.slider_brightness.setValue(24)
        window.slider_contrast.setValue(13)
        window.spin_libraw_bright.setValue(1.25)
        window._set_combo_data(window.combo_libraw_highlight_mode, "blend")
        window._save_named_adjustment_profile("color_contrast")
        color_profile_id = window._active_color_contrast_profile_id
        window.slider_brightness.setValue(0)
        window.spin_libraw_bright.setValue(1.0)
        window._set_combo_data(window.combo_libraw_highlight_mode, "clip")
        window._apply_named_adjustment_profile_to_controls("color_contrast", color_profile_id)
        assert window.slider_brightness.value() == 24
        assert window.spin_libraw_bright.value() == pytest.approx(1.25)
        assert window.combo_libraw_highlight_mode.currentData() == "blend"

        window.detail_profile_name_edit.setText("Nitidez caso")
        window.slider_sharpen.setValue(86)
        window.slider_radius.setValue(18)
        window._save_named_adjustment_profile("detail")
        detail_profile_id = window._active_detail_profile_id
        window.slider_sharpen.setValue(0)
        window._apply_named_adjustment_profile_to_controls("detail", detail_profile_id)
        assert window.slider_sharpen.value() == 86

        window.raw_export_profile_name_edit.setText("RAW caso")
        window._set_combo_data(window.combo_black_mode, "fixed")
        window.spin_black_value.setValue(64)
        window.check_four_color_rgb.setChecked(True)
        window._save_named_adjustment_profile("raw_export")
        raw_profile_id = window._active_raw_export_profile_id
        window._set_combo_data(window.combo_black_mode, "metadata")
        window.spin_black_value.setValue(0)
        window.check_four_color_rgb.setChecked(False)
        window._apply_named_adjustment_profile_to_controls("raw_export", raw_profile_id)
        assert window.combo_black_mode.currentData() == "fixed"
        assert window.spin_black_value.value() == 64
        assert window.check_four_color_rgb.isChecked() is True

        assert window._apply_named_adjustment_profile_to_raw_files("color_contrast", color_profile_id, [raw]) == 1
        assert window._apply_named_adjustment_profile_to_raw_files("detail", detail_profile_id, [raw]) == 1
        assert window._apply_named_adjustment_profile_to_raw_files("raw_export", raw_profile_id, [raw]) == 1

        sidecar = load_raw_sidecar(raw)
        assert sidecar["render_adjustments"]["brightness_ev"] == pytest.approx(0.24)
        assert sidecar["render_adjustments"]["contrast"] == pytest.approx(0.13)
        assert sidecar["render_adjustments"]["libraw"]["bright"] == pytest.approx(1.25)
        assert sidecar["render_adjustments"]["libraw"]["highlight_mode"] == "blend"
        assert sidecar["recipe"]["libraw_bright"] == pytest.approx(1.25)
        assert sidecar["recipe"]["libraw_highlight_mode"] == "blend"
        assert sidecar["detail_adjustments"]["sharpen"] == 86
        assert sidecar["detail_adjustments"]["radius"] == 18
        assert sidecar["recipe"]["black_level_mode"] == "fixed:64"
        assert sidecar["recipe"]["four_color_rgb"] is True
        assert sidecar["recipe"]["exposure_compensation"] == pytest.approx(0.0)
        assert sidecar["adjustment_profiles"]["color_contrast"]["id"] == color_profile_id
        assert sidecar["adjustment_profiles"]["detail"]["id"] == detail_profile_id
        assert sidecar["adjustment_profiles"]["raw_export"]["id"] == raw_profile_id
        assert window._raw_adjustment_profile_badges(raw) == ["icc", "color_contrast", "detail", "raw_export"]
        summary = window._raw_adjustment_profile_badge_summary(raw)
        assert "ICC:" in summary
        assert "Color/contraste: Color caso" in summary
        assert "Nitidez: Nitidez caso" in summary
        assert "RAW: RAW caso" in summary
        window._selected_file = raw
        window._refresh_selected_icc_profile_info()
        assert "ICC aplicado:" in window.icc_selected_file_info_label.text()
        assert raw.name in window.icc_selected_file_info_label.text()
        marked = window._display_icon_for_path(
            raw,
            window._icon_from_thumbnail_array(gui_module.np.full((48, 48, 3), 96, dtype=gui_module.np.uint8)),
        )
        pixmap = marked.pixmap(window.file_list.iconSize())
        assert pixmap.height() > pixmap.width()

        saved = load_session(root)["state"]
        assert saved["color_contrast_profiles"][0]["id"] == color_profile_id
        assert saved["detail_profiles"][0]["id"] == detail_profile_id
        assert saved["raw_export_profiles"][0]["id"] == raw_profile_id
    finally:
        window.close()

    reloaded = ICCRawMainWindow()
    try:
        reloaded._activate_session(root, load_session(root))
        assert reloaded._named_adjustment_profile_by_id("color_contrast", color_profile_id) is not None
        assert reloaded._named_adjustment_profile_by_id("detail", detail_profile_id) is not None
        assert reloaded._named_adjustment_profile_by_id("raw_export", raw_profile_id) is not None
    finally:
        reloaded.close()


def test_raw_adjustment_groups_follow_editor_flow(qapp):
    window = ICCRawMainWindow()
    try:
        workflow_labels = [
            window.right_workflow_tabs.tabText(i)
            for i in range(window.right_workflow_tabs.count())
        ]
        assert workflow_labels == [
            "Color / calibración",
            "Color y contraste",
            "Nitidez",
            "RAW / exportación",
        ]

        panel_labels = [window.config_tabs.itemText(i) for i in range(window.config_tabs.count())]
        assert panel_labels == [
            "Color",
            "Claro",
            "Gradacion de color",
            "Revelado base",
        ]
        raw_export_labels = [
            window.raw_export_tabs.itemText(i)
            for i in range(window.raw_export_tabs.count())
        ]
        assert raw_export_labels == [
            "RAW Global",
            "Exportar derivados",
        ]
        assert "Gestión de color y calibración" not in panel_labels
        assert "Calibrar sesión" not in panel_labels
        assert "Corrección básica" not in panel_labels
        assert "Ajustes personalizados" not in workflow_labels
        group_titles = [box.title() for box in window.findChildren(QtWidgets.QGroupBox)]
        assert "Perfil ICC de la imagen" in group_titles
        assert "Estado ICC" in group_titles
        assert "Perfiles de ajuste por archivo" not in group_titles
        assert window.radio_icc_generic.isChecked()
        assert window.radio_icc_generic.text() == "Perfil ICC RGB estandar"
        assert window.radio_icc_existing.text() == "Perfiles ICC de la sesion"
        assert window.radio_icc_generate.text() == "Generar perfil ICC"
        assert window.combo_generic_icc_space.currentData() == "prophoto_rgb"
        assert "todavia no tiene ICC generados" in window.icc_existing_availability_label.text()
        assert not window._icc_profile_generation_section.isEnabled()
        assert not window.icc_profile_combo.isEnabled()
        window.radio_icc_existing.setChecked(True)
        assert window.icc_profile_combo.isEnabled()
        assert not window._icc_profile_generation_section.isEnabled()
        assert "No hay ICC de sesion" in window.icc_workflow_decision_label.text()
        window.radio_icc_generate.setChecked(True)
        assert not window.icc_profile_combo.isEnabled()
        assert window._icc_profile_generation_section.isEnabled()
        window.radio_icc_generic.setChecked(True)
        window.combo_generic_icc_space.setCurrentIndex(window.combo_generic_icc_space.findData("srgb"))
        assert window.combo_output_space.currentText() == "srgb"
        assert "Imagen seleccionada: ninguna" in window.icc_selected_file_info_label.text()
        assert isinstance(window._advanced_raw_config, QtWidgets.QGroupBox)
        assert window._advanced_raw_config.title() == "Criterios RAW globales"
        mtf_tab_labels = [
            window.mtf_graph_tabs.tabText(i)
            for i in range(window.mtf_graph_tabs.count())
        ]
        assert mtf_tab_labels == ["ESF", "LSF", "MTF", "CA lateral", "Métricas MTF", "Contexto técnico"]
        assert isinstance(window.mtf_plot_mtf, gui_module.MTFPlotWidget)
        assert isinstance(window.mtf_plot_ca, gui_module.MTFPlotWidget)
        assert window.mtf_result_tabs is window.mtf_graph_tabs

        window._go_to_nitidez_tab()
        assert window.main_tabs.currentIndex() == 1
        assert window.right_workflow_tabs.tabText(window.right_workflow_tabs.currentIndex()) == "Nitidez"
    finally:
        window.close()


def test_about_dialog_opens_from_help_menu(qapp):
    window = ICCRawMainWindow()
    try:
        closed = {"done": False}

        def close_dialog():
            dialog = QtWidgets.QApplication.instance().activeModalWidget()
            assert dialog is not None
            assert "Acerca de" in dialog.windowTitle()
            label_texts = [
                widget.text()
                for widget in dialog.findChildren(QtWidgets.QLabel)
            ]
            joined = "\n".join(label_texts)
            assert "PROBATIA" in joined
            assert "AEICF" in joined
            assert "Alejandro Maestre Gasteazi" in joined
            assert "alejandro.maestre@imagencientifica.es" in joined
            closed["done"] = True
            dialog.accept()

        QtCore.QTimer.singleShot(20, close_dialog)
        window._menu_about()

        assert closed["done"] is True
    finally:
        window.close()


def test_mtf_roi_analysis_updates_metrics_and_lpmm(tmp_path: Path, qapp):
    size = 140
    yy, xx = gui_module.np.mgrid[0:size, 0:size].astype(gui_module.np.float32)
    dist = (xx - size / 2.0) + (yy - size / 2.0) * 0.12
    edge = (dist > 0.0).astype(gui_module.np.float32)
    edge = cv2.GaussianBlur(edge, (0, 0), sigmaX=1.2, sigmaY=1.2)
    image = gui_module.np.repeat(edge[..., None], 3, axis=2)

    window = ICCRawMainWindow()
    image_path = tmp_path / "edge.tiff"
    write_tiff16(image_path, image)
    try:
        window._selected_file = image_path
        window._original_linear = image
        window._preview_srgb = image
        window.spin_mtf_pixel_pitch_um.setValue(4.0)
        window._on_mtf_roi_selected(20, 20, 100, 100)

        assert window._mtf_roi == (20, 20, 100, 100)
        assert window._mtf_last_result is not None
        assert window.mtf_plot_mtf._result is window._mtf_last_result
        assert "MTF50" not in window.mtf_metrics_label.text()
        assert "lp/mm" in window.mtf_metrics_label.text()
        metric_rows = {
            window.mtf_metrics_table.item(row, 0).text(): window.mtf_metrics_table.item(row, 1).text()
            for row in range(window.mtf_metrics_table.rowCount())
        }
        context_rows = {
            window.mtf_context_table.item(row, 0).text(): window.mtf_context_table.item(row, 1).text()
            for row in range(window.mtf_context_table.rowCount())
        }
        assert "MTF50" in metric_rows
        assert "MTF30" in metric_rows
        assert "MTF10" in metric_rows
        assert "Nyquist" in metric_rows
        assert "CA area" in metric_rows
        assert "CA R-G" in metric_rows
        assert "125.00 lp/mm" in metric_rows["Nyquist"]
        assert "Post-Nyquist pico" in metric_rows
        assert "Fuente" in context_rows
        assert "ROI" in context_rows
        payload = window._mtf_analysis_payload(include_curves=True)
        assert payload is not None
        assert payload["summary"]["nyquist_cycles_per_pixel"] == pytest.approx(0.5)
        assert payload["summary"]["nyquist_lp_per_mm"] == pytest.approx(125.0)
        assert payload["summary"]["post_nyquist"]["samples"] > 0
        assert payload["summary"]["extended_frequency_range_cycles_per_pixel"][1] <= 1.0
        assert payload["summary"]["chromatic_aberration"]["samples"] > 0
        assert payload["curves"]["mtf"]
        assert payload["curves"]["mtf_extended"]
        assert payload["curves"]["chromatic_aberration"]
        assert max(point["frequency_cycles_per_pixel"] for point in payload["curves"]["mtf_extended"]) <= 1.0
        sidecar = load_raw_sidecar(image_path)
        assert sidecar["mtf_analysis"]["summary"]["mtf50"] == pytest.approx(payload["summary"]["mtf50"])
        assert sidecar["mtf_analysis"]["summary"]["mtf50_lp_per_mm"] == pytest.approx(payload["summary"]["mtf50_lp_per_mm"])
        assert sidecar["mtf_analysis"]["curves"]["mtf_extended"]
        assert sidecar["mtf_analysis"]["curves"]["chromatic_aberration"]
        assert "MTF guardada" in window._raw_sidecar_mtf_summary(image_path)
        assert window._raw_sidecar_development_summary(image_path) == ""
        csv_text = window._mtf_payload_to_csv(payload)
        assert "section,index,x,y,key,value" in csv_text
        assert "frequency_lp_per_mm" in csv_text
        assert "mtf_extended" in csv_text
        assert "chromatic_aberration" in csv_text
        assert not window.btn_mtf_select_roi.isChecked()
    finally:
        window.close()


def test_mtf_sidecar_restores_roi_and_curves_without_reselecting_edge(tmp_path: Path, qapp):
    size = 140
    yy, xx = gui_module.np.mgrid[0:size, 0:size].astype(gui_module.np.float32)
    dist = (xx - size / 2.0) + (yy - size / 2.0) * 0.12
    edge = (dist > 0.0).astype(gui_module.np.float32)
    measured = cv2.GaussianBlur(edge, (0, 0), sigmaX=1.2, sigmaY=1.2)
    softer = cv2.GaussianBlur(edge, (0, 0), sigmaX=2.2, sigmaY=2.2)
    measured_rgb = gui_module.np.repeat(measured[..., None], 3, axis=2)
    softer_rgb = gui_module.np.repeat(softer[..., None], 3, axis=2)

    window = ICCRawMainWindow()
    image_path = tmp_path / "edge.tiff"
    write_tiff16(image_path, measured_rgb)
    try:
        window._selected_file = image_path
        window._original_linear = measured_rgb
        window._preview_srgb = measured_rgb
        window.spin_mtf_pixel_pitch_um.setValue(4.0)
        window._on_mtf_roi_selected(20, 20, 100, 100)
        persisted = window._mtf_last_result
        assert persisted is not None
        persisted_mtf50 = persisted.mtf50
        persisted_payload = load_raw_sidecar(image_path)["mtf_analysis"]
        persisted_extended = [
            point["modulation"]
            for point in persisted_payload["curves"]["mtf_extended"]
        ]
        persisted_ca = [
            point["difference"]
            for point in persisted_payload["curves"]["chromatic_aberration"]
        ]

        window._clear_mtf_roi_for_file_change()
        window.spin_mtf_pixel_pitch_um.setValue(0.0)

        window._selected_file = image_path
        window._original_linear = measured_rgb
        window._preview_srgb = measured_rgb
        window._restore_persisted_mtf_analysis_for_selected(image_path)

        restored = window._mtf_last_result
        assert restored is not None
        assert window._mtf_roi == (20, 20, 100, 100)
        assert window.image_result_single._roi_rect is None
        window._go_to_nitidez_tab()
        assert window.image_result_single._roi_rect == pytest.approx((20, 20, 100, 100))
        window.right_workflow_tabs.setCurrentIndex(1)
        assert window.image_result_single._roi_rect is None
        assert restored.mtf50 == pytest.approx(persisted_mtf50)
        assert restored.mtf_extended == pytest.approx(persisted_extended)
        assert restored.ca_diff == pytest.approx(persisted_ca)
        assert window.mtf_plot_mtf._result is restored
        assert window.mtf_plot_ca._result is restored
        assert window.spin_mtf_pixel_pitch_um.value() == pytest.approx(4.0)
        assert not window.btn_mtf_select_roi.isChecked()

        window._original_linear = softer_rgb
        window._preview_srgb = softer_rgb
        write_tiff16(image_path, softer_rgb)
        window._recalculate_mtf_analysis()

        assert window._mtf_roi == (20, 20, 100, 100)
        assert window._mtf_last_result is not restored
        assert window._mtf_last_result.mtf50 < persisted_mtf50
    finally:
        window.close()


def test_mtf_sidecar_restore_scales_roi_to_current_preview_size(tmp_path: Path, qapp):
    size = 140
    yy, xx = gui_module.np.mgrid[0:size, 0:size].astype(gui_module.np.float32)
    dist = (xx - size / 2.0) + (yy - size / 2.0) * 0.12
    edge = (dist > 0.0).astype(gui_module.np.float32)
    edge = cv2.GaussianBlur(edge, (0, 0), sigmaX=1.2, sigmaY=1.2)
    full_image = gui_module.np.repeat(edge[..., None], 3, axis=2)
    preview = cv2.resize(full_image, (70, 70), interpolation=cv2.INTER_AREA)

    window = ICCRawMainWindow()
    image_path = tmp_path / "edge.tiff"
    write_tiff16(image_path, full_image)
    try:
        window._selected_file = image_path
        window._original_linear = full_image
        window._preview_srgb = full_image
        window._on_mtf_roi_selected(20, 20, 100, 100)
        assert load_raw_sidecar(image_path)["mtf_analysis"]["summary"]["display_roi"] == [20, 20, 100, 100]

        window._clear_mtf_roi_for_file_change()
        window._selected_file = image_path
        window._original_linear = preview
        window._preview_srgb = preview
        window._restore_persisted_mtf_analysis_for_selected(image_path)

        assert window._mtf_roi == (10, 10, 50, 50)
        assert window.image_result_single._roi_rect is None
        window._go_to_nitidez_tab()
        assert window.image_result_single._roi_rect == pytest.approx((10, 10, 50, 50))

        window._recalculate_mtf_analysis()

        assert window._mtf_last_result is not None
        assert window._mtf_last_result.roi == (20, 20, 100, 100)
        payload = load_raw_sidecar(image_path)["mtf_analysis"]
        assert payload["summary"]["display_dimensions_px"] == [70, 70]
        assert payload["summary"]["display_roi"] == [10, 10, 50, 50]
        assert payload["summary"]["roi"] == [20, 20, 100, 100]
    finally:
        window.close()


def test_mtf_recalculation_scales_preview_roi_to_full_resolution_source(tmp_path: Path, qapp):
    size = 140
    yy, xx = gui_module.np.mgrid[0:size, 0:size].astype(gui_module.np.float32)
    dist = (xx - size / 2.0) + (yy - size / 2.0) * 0.12
    edge = (dist > 0.0).astype(gui_module.np.float32)
    edge = cv2.GaussianBlur(edge, (0, 0), sigmaX=1.2, sigmaY=1.2)
    full_image = gui_module.np.repeat(edge[..., None], 3, axis=2)
    preview = cv2.resize(full_image, (70, 70), interpolation=cv2.INTER_AREA)

    window = ICCRawMainWindow()
    image_path = tmp_path / "edge.tiff"
    write_tiff16(image_path, full_image)
    try:
        window._selected_file = image_path
        window._original_linear = preview
        window._preview_srgb = preview
        window._on_mtf_roi_selected(10, 10, 50, 50)

        assert window._mtf_roi == (10, 10, 50, 50)
        assert window._mtf_last_result is not None
        assert window._mtf_last_result.roi == (20, 20, 100, 100)
        payload = load_raw_sidecar(image_path)["mtf_analysis"]
        assert payload["summary"]["analysis_source"] == "full_resolution_image_data"
        assert payload["summary"]["image_dimensions_px"] == [140, 140]
        assert payload["summary"]["display_dimensions_px"] == [70, 70]
        assert payload["summary"]["roi"] == [20, 20, 100, 100]
        assert payload["summary"]["display_roi"] == [10, 10, 50, 50]
    finally:
        window.close()


def test_mtf_reuses_cached_full_resolution_roi_for_adjustment_changes(tmp_path: Path, monkeypatch, qapp):
    import probraw.ui.window.mtf as mtf_module

    size = 360
    yy, xx = gui_module.np.mgrid[0:size, 0:size].astype(gui_module.np.float32)
    dist = (xx - size / 2.0) + (yy - size / 2.0) * 0.12
    edge = (dist > 0.0).astype(gui_module.np.float32)
    edge = cv2.GaussianBlur(edge, (0, 0), sigmaX=1.2, sigmaY=1.2)
    full_image = gui_module.np.repeat(edge[..., None], 3, axis=2)

    read_calls = {"count": 0}
    adjustment_calls = {"count": 0, "shapes": []}
    original_apply_adjustments = mtf_module.apply_adjustments

    def fake_read_image(_path):
        read_calls["count"] += 1
        return full_image

    def counted_apply_adjustments(image, **kwargs):
        adjustment_calls["count"] += 1
        adjustment_calls["shapes"].append(tuple(image.shape))
        return original_apply_adjustments(image, **kwargs)

    monkeypatch.setattr(mtf_module, "read_image", fake_read_image)
    monkeypatch.setattr(mtf_module, "apply_adjustments", counted_apply_adjustments)

    window = ICCRawMainWindow()
    image_path = tmp_path / "edge.tiff"
    write_tiff16(image_path, full_image)
    try:
        window._selected_file = image_path
        window._original_linear = full_image
        window._preview_srgb = full_image
        window._on_mtf_roi_selected(130, 130, 100, 100)

        assert read_calls["count"] == 1
        assert adjustment_calls["count"] == 0

        window.slider_sharpen.blockSignals(True)
        window.slider_sharpen.setValue(80)
        window.slider_sharpen.blockSignals(False)
        window._recalculate_mtf_analysis()

        assert read_calls["count"] == 1
        assert adjustment_calls["count"] == 1
        assert adjustment_calls["shapes"][0][0] < size
        assert adjustment_calls["shapes"][0][1] < size

        window._recalculate_mtf_analysis()

        assert read_calls["count"] == 1
        assert adjustment_calls["count"] == 1

        window.slider_noise_luma.blockSignals(True)
        window.slider_noise_luma.setValue(25)
        window.slider_noise_luma.blockSignals(False)
        window.slider_sharpen.blockSignals(True)
        window.slider_sharpen.setValue(120)
        window.slider_sharpen.blockSignals(False)
        window._recalculate_mtf_analysis()

        assert read_calls["count"] == 1
        assert adjustment_calls["count"] == 3
        assert adjustment_calls["shapes"][1] == adjustment_calls["shapes"][0]
        assert adjustment_calls["shapes"][2] == adjustment_calls["shapes"][0]

        window.slider_sharpen.blockSignals(True)
        window.slider_sharpen.setValue(160)
        window.slider_sharpen.blockSignals(False)
        window._recalculate_mtf_analysis()

        assert read_calls["count"] == 1
        assert adjustment_calls["count"] == 4
        assert adjustment_calls["shapes"][3] == adjustment_calls["shapes"][0]
    finally:
        window.close()


def test_mtf_roi_block_matches_full_resolution_adjustment_result(tmp_path: Path, qapp):
    size = 360
    yy, xx = gui_module.np.mgrid[0:size, 0:size].astype(gui_module.np.float32)
    dist = (xx - size / 2.0) + (yy - size / 2.0) * 0.12
    edge = (dist > 0.0).astype(gui_module.np.float32)
    edge = cv2.GaussianBlur(edge, (0, 0), sigmaX=1.0, sigmaY=1.0)
    full_image = gui_module.np.repeat(edge[..., None], 3, axis=2)

    window = ICCRawMainWindow()
    image_path = tmp_path / "edge.tiff"
    write_tiff16(image_path, full_image)
    try:
        window._selected_file = image_path
        window._original_linear = full_image
        window._preview_srgb = full_image
        window.slider_sharpen.blockSignals(True)
        window.slider_sharpen.setValue(120)
        window.slider_sharpen.blockSignals(False)
        window.slider_radius.blockSignals(True)
        window.slider_radius.setValue(24)
        window.slider_radius.blockSignals(False)
        roi = (130, 130, 100, 100)

        roi_info = window._mtf_full_resolution_analysis_roi_image(roi)
        full_adjusted = window._mtf_full_resolution_analysis_image()

        assert roi_info is not None
        assert full_adjusted is not None
        x, y, width, height = roi_info["analysis_roi"]
        expected = full_adjusted[y : y + height, x : x + width, :3]
        assert gui_module.np.allclose(roi_info["image"], expected, atol=2e-6)
    finally:
        window.close()


def test_mtf_auto_update_is_scheduled_from_detail_slider_change(tmp_path: Path, qapp):
    size = 180
    yy, xx = gui_module.np.mgrid[0:size, 0:size].astype(gui_module.np.float32)
    dist = (xx - size / 2.0) + (yy - size / 2.0) * 0.15
    edge = (dist > 0.0).astype(gui_module.np.float32)
    edge = cv2.GaussianBlur(edge, (0, 0), sigmaX=1.2, sigmaY=1.2)
    image = gui_module.np.repeat(edge[..., None], 3, axis=2)

    window = ICCRawMainWindow()
    image_path = tmp_path / "edge.tiff"
    write_tiff16(image_path, image)
    try:
        window._go_to_nitidez_tab()
        window._selected_file = image_path
        window._original_linear = image
        window._preview_srgb = image
        window._on_mtf_roi_selected(55, 55, 70, 70)
        window._mtf_refresh_timer.stop()
        window.check_mtf_auto_update.setChecked(True)

        window.slider_sharpen.setSliderDown(True)
        window.slider_sharpen.setValue(30)

        assert window._mtf_refresh_timer.isActive()
    finally:
        window.slider_sharpen.setSliderDown(False)
        window._mtf_refresh_timer.stop()
        window.close()


def test_mtf_detail_slider_change_schedules_when_general_auto_update_is_off(tmp_path: Path, qapp):
    size = 180
    yy, xx = gui_module.np.mgrid[0:size, 0:size].astype(gui_module.np.float32)
    dist = (xx - size / 2.0) + (yy - size / 2.0) * 0.15
    edge = (dist > 0.0).astype(gui_module.np.float32)
    edge = cv2.GaussianBlur(edge, (0, 0), sigmaX=1.2, sigmaY=1.2)
    image = gui_module.np.repeat(edge[..., None], 3, axis=2)

    window = ICCRawMainWindow()
    image_path = tmp_path / "edge.tiff"
    write_tiff16(image_path, image)
    try:
        window._go_to_nitidez_tab()
        window._selected_file = image_path
        window._original_linear = image
        window._preview_srgb = image
        window._on_mtf_roi_selected(55, 55, 70, 70)
        assert window._mtf_has_hot_base_roi_cache(window._mtf_roi)
        window._mtf_refresh_timer.stop()
        window.check_mtf_auto_update.setChecked(False)

        window.slider_sharpen.setSliderDown(True)
        window.slider_sharpen.setValue(30)

        assert window._mtf_refresh_timer.isActive()
    finally:
        window.slider_sharpen.setSliderDown(False)
        window._mtf_refresh_timer.stop()
        window.close()


def test_mtf_interactive_auto_update_throttles_instead_of_debouncing(monkeypatch, qapp):
    class FakeTimer:
        def __init__(self) -> None:
            self.active = False
            self.starts: list[int] = []

        def isActive(self) -> bool:
            return self.active

        def start(self, delay: int) -> None:
            self.starts.append(int(delay))
            self.active = True

        def stop(self) -> None:
            self.active = False

    window = ICCRawMainWindow()
    fake_timer = FakeTimer()
    try:
        window._mtf_roi = (10, 10, 40, 40)
        window.check_mtf_auto_update.setChecked(True)
        monkeypatch.setattr(window, "_mtf_roi_overlay_should_be_visible", lambda: True)
        monkeypatch.setattr(window, "_mtf_has_hot_base_roi_cache", lambda _roi: True)
        window._mtf_refresh_timer.stop()
        window._mtf_refresh_timer = fake_timer

        window._schedule_mtf_refresh(interactive=True)
        window._schedule_mtf_refresh(interactive=True)

        assert fake_timer.starts == [window.MTF_INTERACTIVE_REFRESH_DELAY_MS]

        fake_timer.active = False
        window._schedule_mtf_refresh(interactive=True)
        window._schedule_mtf_refresh(interactive=False)

        assert fake_timer.starts == [
            window.MTF_INTERACTIVE_REFRESH_DELAY_MS,
            window.MTF_INTERACTIVE_REFRESH_DELAY_MS,
            window.MTF_SETTLED_REFRESH_DELAY_MS,
        ]
    finally:
        fake_timer.stop()
        window.close()


def test_mtf_auto_update_defers_when_restored_roi_cache_is_cold(tmp_path: Path, qapp):
    size = 180
    yy, xx = gui_module.np.mgrid[0:size, 0:size].astype(gui_module.np.float32)
    dist = (xx - size / 2.0) + (yy - size / 2.0) * 0.15
    edge = (dist > 0.0).astype(gui_module.np.float32)
    edge = cv2.GaussianBlur(edge, (0, 0), sigmaX=1.2, sigmaY=1.2)
    image = gui_module.np.repeat(edge[..., None], 3, axis=2)

    window = ICCRawMainWindow()
    image_path = tmp_path / "edge.tiff"
    write_tiff16(image_path, image)
    try:
        window._go_to_nitidez_tab()
        window._selected_file = image_path
        window._original_linear = image
        window._preview_srgb = image
        window._on_mtf_roi_selected(55, 55, 70, 70)
        assert window._mtf_has_hot_base_roi_cache(window._mtf_roi)

        window._mtf_refresh_timer.stop()
        window._clear_mtf_image_caches()
        window.check_mtf_auto_update.setChecked(True)
        window._schedule_mtf_refresh(interactive=False)

        assert not window._mtf_refresh_timer.isActive()

        window._mtf_full_resolution_base_roi(window._mtf_roi)
        window._schedule_mtf_refresh(interactive=False)

        assert window._mtf_refresh_timer.isActive()
        window._clear_mtf_image_caches()
        assert not window._mtf_refresh_timer.isActive()
    finally:
        window._mtf_refresh_timer.stop()
        window.close()


def test_mtf_auto_update_waits_until_sharpness_tab_is_visible(tmp_path: Path, qapp):
    size = 180
    yy, xx = gui_module.np.mgrid[0:size, 0:size].astype(gui_module.np.float32)
    dist = (xx - size / 2.0) + (yy - size / 2.0) * 0.15
    edge = (dist > 0.0).astype(gui_module.np.float32)
    edge = cv2.GaussianBlur(edge, (0, 0), sigmaX=1.2, sigmaY=1.2)
    image = gui_module.np.repeat(edge[..., None], 3, axis=2)

    window = ICCRawMainWindow()
    image_path = tmp_path / "edge.tiff"
    write_tiff16(image_path, image)
    try:
        window._go_to_nitidez_tab()
        window._selected_file = image_path
        window._original_linear = image
        window._preview_srgb = image
        window._on_mtf_roi_selected(55, 55, 70, 70)
        assert window._mtf_has_hot_base_roi_cache(window._mtf_roi)
        window._mtf_refresh_timer.stop()
        window.check_mtf_auto_update.setChecked(True)

        window.right_workflow_tabs.setCurrentIndex(1)
        window._schedule_mtf_refresh(interactive=False)

        assert not window._mtf_refresh_timer.isActive()
        assert window._mtf_auto_refresh_deferred_until_visible is True

        window._go_to_nitidez_tab()

        assert window._mtf_refresh_timer.isActive()
    finally:
        window._mtf_refresh_timer.stop()
        window.close()


def test_entering_sharpness_tab_refreshes_mtf_when_general_auto_update_is_off(tmp_path: Path, qapp):
    size = 180
    yy, xx = gui_module.np.mgrid[0:size, 0:size].astype(gui_module.np.float32)
    dist = (xx - size / 2.0) + (yy - size / 2.0) * 0.15
    edge = (dist > 0.0).astype(gui_module.np.float32)
    edge = cv2.GaussianBlur(edge, (0, 0), sigmaX=1.2, sigmaY=1.2)
    image = gui_module.np.repeat(edge[..., None], 3, axis=2)

    window = ICCRawMainWindow()
    image_path = tmp_path / "edge.tiff"
    write_tiff16(image_path, image)
    try:
        window._go_to_nitidez_tab()
        window._selected_file = image_path
        window._original_linear = image
        window._preview_srgb = image
        window._on_mtf_roi_selected(55, 55, 70, 70)
        assert window._mtf_has_hot_base_roi_cache(window._mtf_roi)
        window._mtf_refresh_timer.stop()
        window.check_mtf_auto_update.setChecked(False)
        window._mtf_last_result = None
        window._update_mtf_result_widgets()

        window.right_workflow_tabs.setCurrentIndex(1)
        assert not window._mtf_refresh_timer.isActive()

        window._go_to_nitidez_tab()

        assert window._mtf_refresh_timer.isActive()
    finally:
        window._mtf_refresh_timer.stop()
        window.close()


def test_mtf_cold_fullres_roi_is_queued_outside_ui(tmp_path: Path, monkeypatch, qapp):
    size = 180
    yy, xx = gui_module.np.mgrid[0:size, 0:size].astype(gui_module.np.float32)
    dist = (xx - size / 2.0) + (yy - size / 2.0) * 0.15
    edge = (dist > 0.0).astype(gui_module.np.float32)
    edge = cv2.GaussianBlur(edge, (0, 0), sigmaX=1.2, sigmaY=1.2)
    image = gui_module.np.repeat(edge[..., None], 3, axis=2)

    window = ICCRawMainWindow()
    image_path = tmp_path / "edge.tiff"
    write_tiff16(image_path, image)
    queued: list[dict] = []
    try:
        window._selected_file = image_path
        window._original_linear = image
        window._preview_srgb = image
        window._mtf_roi = (55, 55, 70, 70)
        monkeypatch.setattr(window, "_run_mtf_analysis_inline", lambda: False)
        monkeypatch.setattr(window, "_start_mtf_base_roi_worker", lambda request: queued.append(request))

        window._recalculate_mtf_analysis()

        assert queued
        assert queued[0]["display_roi"] == [55, 55, 70, 70]
        assert queued[0]["mode"] == "analysis"
        assert window._mtf_last_result is None
        assert "segundo plano" in window.mtf_metrics_label.text()
    finally:
        window._mtf_refresh_timer.stop()
        window.close()


def test_mtf_roi_worker_command_uses_module_in_source_run(tmp_path: Path, qapp):
    import probraw.ui.window.mtf as mtf_module

    window = ICCRawMainWindow()
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "output.npz"
    try:
        command = window._mtf_base_roi_worker_command(request_path, output_path)

        assert command == [
            mtf_module.sys.executable,
            "-m",
            "probraw.analysis.mtf_roi",
            str(request_path),
            str(output_path),
        ]
    finally:
        window.close()


def test_mtf_roi_worker_command_uses_cli_sibling_when_frozen(tmp_path: Path, monkeypatch, qapp):
    import probraw.ui.window.mtf as mtf_module

    gui_exe = tmp_path / "probraw-ui.exe"
    cli_exe = tmp_path / "probraw.exe"
    gui_exe.write_bytes(b"gui")
    cli_exe.write_bytes(b"cli")
    monkeypatch.setattr(mtf_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(mtf_module.sys, "executable", str(gui_exe))

    window = ICCRawMainWindow()
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "output.npz"
    try:
        assert window._mtf_base_roi_worker_command(request_path, output_path) == [
            str(cli_exe),
            "mtf-roi-worker",
            str(request_path),
            str(output_path),
        ]
    finally:
        window.close()


def test_mtf_progress_panel_reports_elapsed_estimate_and_completion(qapp):
    window = ICCRawMainWindow()
    try:
        assert window.mtf_progress_panel.isVisible() is False
        assert window.mtf_progress_bar.isVisible() is False

        window._start_mtf_progress(
            "prepare",
            detail="capture.NEF ROI 80x80",
            estimate_seconds=8.0,
        )
        window._mtf_progress_started_at -= 2.0
        window._update_mtf_progress_status()

        assert "capture.NEF" in window.mtf_progress_label.text()
        assert "Transcurrido" in window.mtf_progress_time_label.text()
        assert "estimado" in window.mtf_progress_time_label.text()
        assert window.mtf_progress_bar.value() > 0
        assert "activo" in window.mtf_phase_label.text()
        assert "capture.NEF" in window.global_status_label.text()
        assert "estimado" in window.global_progress_time_label.text()
        assert "activo" in window.global_progress_phase_label.text()
        assert window.global_progress.value() == window.mtf_progress_bar.value()
        assert window.mtf_progress_panel.isVisible() is False

        window._set_mtf_progress_steps(3, 10, detail="combinación 3/10")

        assert window.mtf_progress_bar.maximum() == 10
        assert window.mtf_progress_bar.value() == 3
        assert "3/10" in window.mtf_progress_time_label.text()
        assert window.global_progress.maximum() == 10
        assert window.global_progress.value() == 3

        window._finish_mtf_progress("complete", detail="curvas listas", elapsed_seconds=2.4)

        assert window.mtf_progress_bar.value() == 100
        assert "curvas listas" in window.mtf_progress_label.text()
        assert "2.4s" in window.mtf_progress_time_label.text()
        assert "curvas listas" in window.global_status_label.text()
        assert "2.4s" in window.global_progress_time_label.text()
        assert window.global_progress.value() == 100
    finally:
        window.close()


def test_global_progress_panel_tracks_preview_load_threshold(tmp_path: Path, qapp):
    window = ICCRawMainWindow()
    try:
        raw_path = tmp_path / "capture.NEF"
        raw_path.write_bytes(b"fake raw")
        window._settings.setValue("performance/preview_load_seconds_ewma", 2.0)

        window._start_preview_load_progress(raw_path, True, 2600)
        window._preview_load_progress_started_at -= 1.2
        window._update_preview_load_progress_status()

        assert "Preview" in window.global_status_label.text()
        assert "capture.NEF" in window.global_status_label.text()
        assert "estimado" in window.global_progress_time_label.text()
        assert "Preview: pendiente" in window.global_progress_phase_label.text()
        assert window.global_progress.value() > 0

        window._finish_preview_load_progress(
            success=True,
            detail="Preview cargada: capture.NEF",
            elapsed_seconds=1.4,
        )

        assert "Preview cargada" in window.global_status_label.text()
        assert "1.4s" in window.global_progress_time_label.text()
        assert window.global_progress.value() == 100
    finally:
        window.close()


def test_global_progress_panel_promotes_slow_interactive_adjustments(qapp):
    window = ICCRawMainWindow()
    try:
        window._set_interactive_preview_busy(True)
        window._interactive_preview_busy_started_at = time.perf_counter() - 1.2
        window._update_interactive_preview_global_progress()

        assert window._global_progress_owner == "preview"
        assert "Ajustando preview" in window.global_status_label.text()
        assert "1." in window.global_progress_time_label.text()
        assert window.global_progress.minimum() == 0
        assert window.global_progress.maximum() == 0

        window._set_interactive_preview_busy(False)

        assert window._global_progress_owner == "preview"
        assert "Ajuste completado" in window.global_status_label.text()
    finally:
        window.close()


def test_slow_interactive_adjustment_completion_does_not_replace_active_task(qapp):
    window = ICCRawMainWindow()
    try:
        window._set_interactive_preview_busy(True)
        window._interactive_preview_busy_started_at = time.perf_counter() - 1.2
        window._update_interactive_preview_global_progress()

        window._set_global_operation_progress(
            "task",
            "Exportando lote",
            time_text="En curso",
            phase_text="Exportacion",
            minimum=0,
            maximum=0,
        )
        window._set_interactive_preview_busy(False)

        assert window._global_progress_owner == "task"
        assert "Exportando lote" in window.global_status_label.text()
    finally:
        window.close()


def test_mtf_lateral_ca_roi_block_matches_full_resolution_adjustment(tmp_path: Path, monkeypatch, qapp):
    size = 420
    yy, xx = gui_module.np.mgrid[0:size, 0:size].astype(gui_module.np.float32)
    dist = (xx - size / 2.0) + (yy - size / 2.0) * 0.12
    edge = (dist > 0.0).astype(gui_module.np.float32)
    edge = cv2.GaussianBlur(edge, (0, 0), sigmaX=1.0, sigmaY=1.0)
    full_image = gui_module.np.repeat(edge[..., None], 3, axis=2)

    window = ICCRawMainWindow()
    image_path = tmp_path / "edge.tiff"
    write_tiff16(image_path, full_image)
    try:
        window._selected_file = image_path
        window._original_linear = full_image
        window._preview_srgb = full_image
        window.slider_noise_luma.blockSignals(True)
        window.slider_noise_luma.setValue(10)
        window.slider_noise_luma.blockSignals(False)
        window.slider_sharpen.blockSignals(True)
        window.slider_sharpen.setValue(90)
        window.slider_sharpen.blockSignals(False)
        window.slider_radius.blockSignals(True)
        window.slider_radius.setValue(18)
        window.slider_radius.blockSignals(False)
        window.slider_ca_red.blockSignals(True)
        window.slider_ca_red.setValue(60)
        window.slider_ca_red.blockSignals(False)
        window.slider_ca_blue.blockSignals(True)
        window.slider_ca_blue.setValue(-40)
        window.slider_ca_blue.blockSignals(False)
        roi = (150, 150, 100, 100)

        full_adjusted = window._mtf_full_resolution_analysis_image()

        def fail_full_image_path(*_args, **_kwargs):
            raise AssertionError("MTF ROI path should not process the full adjusted image for lateral CA")

        monkeypatch.setattr(window, "_mtf_full_resolution_analysis_image", fail_full_image_path)
        roi_info = window._mtf_full_resolution_analysis_roi_image(roi)

        assert roi_info is not None
        assert full_adjusted is not None
        x, y, width, height = roi_info["analysis_roi"]
        expected = full_adjusted[y : y + height, x : x + width, :3]
        assert gui_module.np.allclose(roi_info["image"], expected, atol=3e-4)
    finally:
        window.close()


def test_mtf_auto_sharpening_updates_sliders_and_improves_roi_mtf(tmp_path: Path, monkeypatch, qapp):
    size = 260
    yy, xx = gui_module.np.mgrid[0:size, 0:size].astype(gui_module.np.float32)
    dist = (xx - size / 2.0) + (yy - size / 2.0) * 0.12
    edge = (dist > 0.0).astype(gui_module.np.float32)
    edge = cv2.GaussianBlur(edge, (0, 0), sigmaX=2.4, sigmaY=2.4)
    edge = 0.18 + 0.64 * edge
    full_image = gui_module.np.repeat(edge[..., None], 3, axis=2)

    root = tmp_path / "session"
    raw = root / "01_ORG" / "edge.NEF"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"raw")
    payload = create_session(root, name="Sesion auto nitidez")

    window = ICCRawMainWindow()
    try:
        window._activate_session(root, payload)
        _activate_fake_session_icc(window, root)
        window._selected_file = raw
        window._original_linear = full_image
        window._preview_srgb = full_image
        monkeypatch.setattr(window, "_mtf_full_resolution_base_image", lambda _path, _recipe: full_image)
        window._on_mtf_roi_selected(60, 60, 140, 140)
        baseline = window._mtf_last_result
        assert baseline is not None
        assert baseline.mtf50 is not None

        window._auto_optimize_mtf_sharpening()

        optimized = window._mtf_last_result
        assert optimized is not None
        assert optimized.mtf50 is not None
        assert window.slider_sharpen.value() > 0
        assert optimized.mtf50 > baseline.mtf50
        assert optimized.roi == baseline.roi
        assert window._mtf_auto_sharpen_halo_metrics(optimized)["halo"] <= 0.025
        sidecar = load_raw_sidecar(raw)
        assert sidecar["mtf_analysis"]["summary"]["mtf50"] == pytest.approx(optimized.mtf50)
        assert sidecar["detail_adjustments"]["sharpen"] == window.slider_sharpen.value()
        assert sidecar["detail_adjustments"]["radius"] == window.slider_radius.value()
        assert "detail" in window._raw_adjustment_profile_badges(raw)
    finally:
        window.close()


def test_mtf_auto_sharpening_prefers_mtf50p_over_oversharpened_peak(qapp):
    window = ICCRawMainWindow()

    def make_candidate(
        *,
        amount_slider: int,
        radius_slider: int,
        mtf50: float,
        mtf50p: float,
        mtf30: float,
        halo: float,
        mtf_peak: float,
    ) -> dict:
        result = MTFResult(
            roi=(0, 0, 80, 80),
            roi_shape=(80, 80),
            edge_angle_degrees=85.0,
            edge_contrast=0.70,
            overshoot=halo / 2.0,
            undershoot=halo / 2.0,
            mtf50=mtf50,
            mtf50p=mtf50p,
            mtf30=mtf30,
            mtf10=0.34,
            acutance=0.70,
            esf_distance=[float(i) for i in range(20)],
            esf=[float(v) for v in gui_module.np.linspace(0.0, 1.0, 20)],
            lsf_distance=[float(i) for i in range(20)],
            lsf=[0.0] * 20,
            frequency=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5],
            mtf=[mtf_peak, 0.96, 0.72, 0.42, 0.18, 0.08],
            frequency_extended=[0.0, 0.5, 0.75, 1.0],
            mtf_extended=[mtf_peak, 0.08, 0.04, 0.02],
            warnings=[],
        )
        candidate = {
            "amount_slider": amount_slider,
            "radius_slider": radius_slider,
            "result": result,
        }
        candidate.update(window._mtf_auto_sharpen_quality_metrics(result))
        candidate.update(window._mtf_auto_sharpen_halo_metrics(result))
        candidate["score"] = window._mtf_auto_sharpen_score(
            result,
            amount=float(amount_slider) / 100.0,
            radius=float(radius_slider) / 10.0,
        )
        return candidate

    try:
        baseline = make_candidate(amount_slider=0, radius_slider=10, mtf50=0.12, mtf50p=0.12, mtf30=0.16, halo=0.0, mtf_peak=1.0)
        balanced = make_candidate(amount_slider=80, radius_slider=10, mtf50=0.19, mtf50p=0.18, mtf30=0.24, halo=0.008, mtf_peak=1.04)
        oversharpened = make_candidate(amount_slider=160, radius_slider=22, mtf50=0.30, mtf50p=0.13, mtf30=0.27, halo=0.012, mtf_peak=1.36)

        best = window._mtf_auto_sharpen_select_best([baseline, balanced, oversharpened])

        assert best is balanced
    finally:
        window.close()


def test_mtf_persisted_comparison_rows(qapp):
    window = ICCRawMainWindow()
    try:
        left = {
            "summary": {
                "measured_at": "2026-05-01T10:00:00+00:00",
                "roi": [1, 2, 40, 50],
                "mtf50": 0.20,
                "mtf50_lp_per_mm": 40.0,
                "mtf50p": 0.18,
                "mtf50p_lp_per_mm": 36.0,
                "mtf30": 0.32,
                "mtf30_lp_per_mm": 64.0,
                "mtf10": None,
                "mtf10_lp_per_mm": None,
                "nyquist_lp_per_mm": 100.0,
                "acutance": 0.60,
                "edge_angle_degrees": 5.0,
                "edge_contrast": 0.70,
                "overshoot": 0.01,
                "undershoot": 0.02,
                "post_nyquist": {"peak_frequency": 0.75, "peak_modulation": 0.04, "energy_ratio": 0.10},
            }
        }
        right = {
            "summary": {
                "measured_at": "2026-05-01T10:02:00+00:00",
                "roi": [3, 4, 40, 50],
                "mtf50": 0.25,
                "mtf50_lp_per_mm": 50.0,
                "mtf50p": 0.23,
                "mtf50p_lp_per_mm": 46.0,
                "mtf30": 0.36,
                "mtf30_lp_per_mm": 72.0,
                "mtf10": 0.48,
                "mtf10_lp_per_mm": 96.0,
                "nyquist_lp_per_mm": 100.0,
                "acutance": 0.66,
                "edge_angle_degrees": 6.0,
                "edge_contrast": 0.72,
                "overshoot": 0.03,
                "undershoot": 0.01,
                "post_nyquist": {"peak_frequency": 0.82, "peak_modulation": 0.06, "energy_ratio": 0.12},
            }
        }

        rows = window._mtf_comparison_rows(Path("a.NEF"), left, Path("b.NEF"), right)

        by_label = {row[0]: row for row in rows}
        assert by_label["MTF50 (c/p)"][1:] == ("0.200000 c/p", "0.250000 c/p", "+0.050000 c/p")
        assert by_label["MTF50 (lp/mm)"][1:] == ("40.00 lp/mm", "50.00 lp/mm", "+10.00 lp/mm")
        assert by_label["MTF50P (c/p)"][1:] == ("0.180000 c/p", "0.230000 c/p", "+0.050000 c/p")
        assert by_label["MTF10 (c/p)"][1:] == ("sin dato", "0.480000 c/p", "")
        assert by_label["Sobreimpulso (%)"][1:] == ("1.000%", "3.000%", "+2.000%")
        assert by_label["Post-Nyquist pico (c/p)"][2] == "0.820000 c/p"
    finally:
        window.close()


def test_mtf_plot_displays_nyquist_range_and_coordinate_labels(qapp):
    widget = gui_module.MTFPlotWidget("mtf")

    class Result:
        roi_shape = (80, 120)
        mtf50 = 0.31
        mtf50p = 0.29
        frequency = [0.0, 0.1, 0.2, 0.35, 0.5]
        mtf = [1.0, 0.86, 0.62, 0.31, 0.08]
        frequency_extended = [0.0, 0.25, 0.5, 0.75, 1.0]
        mtf_extended = [1.0, 0.5, 0.1, 0.04, 0.02]

    try:
        widget.set_result(Result())
        x_values = gui_module.np.asarray([0.0, 0.2, 0.4], dtype=gui_module.np.float64)

        assert widget._x_range(x_values) == (0.0, 0.5)
        assert widget._x_range(gui_module.np.asarray([0.0, 0.75])) == (0.0, 1.0)
        assert widget._x_range(gui_module.np.asarray([0.0, 2.0])) == (0.0, 1.0)
        assert widget._axis_ticks(0.0, 0.5) == pytest.approx([0.0, 0.125, 0.25, 0.375, 0.5])
        assert widget._axis_ticks(0.0, 1.0) == pytest.approx([0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0])
        assert widget._coordinate_label(0.5, 0.75) == "x=0.5  y=0.75"
        assert "post-Nyquist" in widget._coordinate_label(0.75, 0.2)
        assert widget._analysis_summary_lines()[0] == "ROI: 120 x 80 px (0.010 Mpix)"
        widget.resize(460, 300)
        widget._hover_pos = QtCore.QPointF(230, 120)
        pixmap = widget.grab()
        assert not pixmap.isNull()
    finally:
        widget.close()


def test_mtf_esf_plot_reports_pixel_scale_and_rise(qapp):
    widget = gui_module.MTFPlotWidget("esf")

    class Result:
        roi_shape = (84, 128)
        esf_distance = [-6.0, -4.0, -2.0, -1.0, 0.0, 1.0, 2.0, 4.0, 6.0]
        esf = [0.0, 0.0, 0.05, 0.18, 0.5, 0.82, 0.95, 1.0, 1.0]

    try:
        widget.set_result(Result())

        assert widget._axis_ticks(-6.0, 6.0) == [-6.0, -4.0, -2.0, 0.0, 2.0, 4.0, 6.0]
        assert 1.0 in widget._minor_axis_ticks(-6.0, 6.0)
        assert widget._esf_rise_10_90() == pytest.approx((-1.6153846, 1.6153846, 3.2307692))
        assert widget._curve_sample_count() == len(Result.esf)
        widget.resize(460, 300)
        pixmap = widget.grab()
        assert not pixmap.isNull()
    finally:
        widget.close()


def test_mtf_ca_plot_reports_channel_profiles_and_metrics(qapp):
    widget = gui_module.MTFPlotWidget("ca")

    class Result:
        roi_shape = (84, 128)
        ca_distance = [-2.0, -1.0, 0.0, 1.0, 2.0]
        ca_red = [0.0, 0.1, 0.45, 0.9, 1.0]
        ca_green = [0.0, 0.2, 0.5, 0.8, 1.0]
        ca_blue = [0.0, 0.3, 0.6, 0.9, 1.0]
        ca_diff = [0.0, 0.15, 0.16, 0.14, 0.0]
        ca_area_pixels = 0.33
        ca_crossing_pixels = 0.22
        ca_red_green_shift_pixels = 0.12
        ca_blue_green_shift_pixels = -0.22
        ca_edge_width_10_90_pixels = 2.75

    try:
        widget.set_result(Result())

        x_values, y_values, title, x_label, y_label = widget._curve_payload()
        assert title == "CA lateral: diferencias RGB"
        assert x_label
        assert y_label
        assert x_values.tolist() == Result.ca_distance
        assert widget._curve_sample_count() == len(Result.ca_distance)
        assert widget._axis_ticks(-2.0, 2.0) == [-2.0, -1.0, 0.0, 1.0, 2.0]
        widget.resize(460, 300)
        pixmap = widget.grab()
        assert not pixmap.isNull()
    finally:
        widget.close()


def test_mtf_comparison_plot_overlays_persisted_curves(qapp):
    widget = gui_module.MTFComparisonPlotWidget("mtf")
    left = {
        "curves": {
            "mtf_extended": [
                {"frequency_cycles_per_pixel": 0.0, "modulation": 1.0},
                {"frequency_cycles_per_pixel": 0.5, "modulation": 0.4},
                {"frequency_cycles_per_pixel": 0.75, "modulation": 0.08},
            ]
        }
    }
    right = {
        "curves": {
            "mtf_extended": [
                {"frequency_cycles_per_pixel": 0.0, "modulation": 1.0},
                {"frequency_cycles_per_pixel": 0.5, "modulation": 0.3},
                {"frequency_cycles_per_pixel": 0.75, "modulation": 0.04},
            ]
        }
    }
    try:
        widget.set_payloads([("a.NEF", left), ("b.NEF", right)])

        assert len(widget._series) == 2
        assert widget._series[0][0] == "a.NEF"
        assert widget._x_range(gui_module.np.concatenate([series[1] for series in widget._series])) == (0.0, 1.0)
        widget.resize(620, 420)
        pixmap = widget.grab()
        assert not pixmap.isNull()
    finally:
        widget.close()


def test_mtf_pixel_pitch_is_estimated_from_loaded_file_metadata(tmp_path: Path, monkeypatch, qapp):
    import probraw.ui.window.mtf as mtf_module

    image_path = tmp_path / "edge.tiff"
    image_path.write_bytes(b"fake")
    captured: dict[str, object] = {}

    def fake_estimate(path: Path, *, image_dimensions=None):
        captured["path"] = path
        captured["dimensions"] = image_dimensions
        return 4.88, "sensor_width"

    monkeypatch.setattr(mtf_module, "estimate_pixel_pitch_um", fake_estimate)
    window = ICCRawMainWindow()
    try:
        window._selected_file = image_path
        window._original_linear = gui_module.np.zeros((30, 40, 3), dtype=gui_module.np.float32)
        window._mtf_last_analysis_image_dimensions = (40, 30)

        window._auto_update_mtf_pixel_pitch_from_file(image_path)

        assert captured["path"] == image_path
        assert captured["dimensions"] == (40, 30)
        assert window.spin_mtf_pixel_pitch_um.value() == pytest.approx(4.88)
        assert window._mtf_pixel_pitch_auto_source == "sensor_width"
        assert "anchura de sensor" in window.mtf_pixel_pitch_source_label.text()
    finally:
        window.close()


def test_mtf_pixel_pitch_resets_stale_auto_value_when_metadata_is_missing(tmp_path: Path, monkeypatch, qapp):
    import probraw.ui.window.mtf as mtf_module

    image_path = tmp_path / "edge.tiff"
    image_path.write_bytes(b"fake")
    monkeypatch.setattr(mtf_module, "estimate_pixel_pitch_um", lambda _path, *, image_dimensions=None: None)
    window = ICCRawMainWindow()
    try:
        window._selected_file = image_path
        window._original_linear = gui_module.np.zeros((30, 40, 3), dtype=gui_module.np.float32)
        window.spin_mtf_pixel_pitch_um.setValue(4.88)
        window._mtf_pixel_pitch_auto_source = "sensor_width"

        window._auto_update_mtf_pixel_pitch_from_file(image_path)

        assert window.spin_mtf_pixel_pitch_um.value() == pytest.approx(0.0)
        assert window._mtf_pixel_pitch_auto_source is None
        assert "no disponible" in window.mtf_pixel_pitch_source_label.text()
    finally:
        window.close()


def test_mtf_manual_sensor_size_derives_pixel_pitch_when_metadata_is_missing(tmp_path: Path, monkeypatch, qapp):
    import probraw.ui.window.mtf as mtf_module

    image_path = tmp_path / "edge.tiff"
    image_path.write_bytes(b"fake")
    monkeypatch.setattr(mtf_module, "estimate_pixel_pitch_um", lambda _path, *, image_dimensions=None: None)
    window = ICCRawMainWindow()
    try:
        window._selected_file = image_path
        window._original_linear = gui_module.np.zeros((4000, 6000, 3), dtype=gui_module.np.float32)
        window._mtf_last_analysis_image_dimensions = (6000, 4000)
        window.spin_mtf_sensor_width_mm.setValue(36.0)
        window.spin_mtf_sensor_height_mm.setValue(24.0)

        window._auto_update_mtf_pixel_pitch_from_file(image_path)

        assert window.spin_mtf_pixel_pitch_um.value() == pytest.approx(6.0)
        assert window._mtf_pixel_pitch_auto_source == "manual_sensor_size"
        assert "sensor manual" in window.mtf_pixel_pitch_source_label.text()
    finally:
        window.close()


def test_amaze_raw_options_enable_border_and_local_false_color(monkeypatch, qapp):
    monkeypatch.setattr(preview_recipe_module, "unavailable_demosaic_reason", lambda _algorithm: None)
    monkeypatch.setattr(
        preview_recipe_module,
        "rawpy_postprocess_parameter_supported",
        lambda name: name == "four_color_rgb",
    )

    window = ICCRawMainWindow()
    try:
        window._set_combo_data(window.combo_demosaic, "amaze")
        window._update_raw_algorithm_option_state()

        assert window.spin_demosaic_edge_quality.isEnabled()
        assert window.spin_false_color_suppression.isEnabled()
        assert "borde" in window.raw_algorithm_options_status_label.text()
        assert "falso color (ProbRAW)" in window.raw_algorithm_options_status_label.text()
        assert "ProbRAW" in window.spin_false_color_suppression.toolTip()
    finally:
        window.close()


def test_development_profile_controls_live_in_color_management_flow(qapp):
    window = ICCRawMainWindow()
    try:
        panel_labels = [window.config_tabs.itemText(i) for i in range(window.config_tabs.count())]
        workflow_labels = [
            window.right_workflow_tabs.tabText(i)
            for i in range(window.right_workflow_tabs.count())
        ]
        assert "Color / calibración" in workflow_labels
        assert "Nitidez" in workflow_labels
        assert "Gestión de color y calibración" not in panel_labels
        assert "Perfiles de revelado" not in panel_labels
        assert "Nitidez" not in panel_labels

        def is_descendant(widget: QtWidgets.QWidget, ancestor: QtWidgets.QWidget) -> bool:
            parent = widget.parentWidget()
            while parent is not None:
                if parent is ancestor:
                    return True
                parent = parent.parentWidget()
            return False

        assert not is_descendant(window.development_profile_combo, window.right_workflow_tabs.widget(0))
        assert not window._development_profiles_panel.isVisible()
        assert not any(
            window.raw_export_tabs.itemText(i) == "Perfiles RAW"
            for i in range(window.raw_export_tabs.count())
        )
        assert is_descendant(window.slider_sharpen, window.right_workflow_tabs.widget(2))
        assert not is_descendant(window.development_profile_combo, window.config_tabs)
        assert not is_descendant(window.slider_sharpen, window.config_tabs)
        assert not is_descendant(window.development_profile_combo, window.main_tabs.widget(0))
    finally:
        window.close()


def test_session_tab_shows_statistics_and_recent_sessions(tmp_path: Path, qapp):
    root_a = tmp_path / "session_a"
    root_b = tmp_path / "session_b"

    create_session(
        root_a,
        name="case_a",
        state={
            "development_profiles": [{"id": "basic-1", "name": "Manual", "profile_type": "basic"}],
        },
        queue=[{"source": str(root_a / "01_ORG" / "a.nef"), "status": "pending"}],
    )
    create_session(root_b, name="case_b", state={}, queue=[])

    (root_a / "01_ORG" / "a.nef").write_bytes(b"raw-a")
    (root_a / "01_ORG" / "b.CR3").write_bytes(b"raw-b")
    (root_a / "01_ORG" / "a.nef.probraw.json").write_text("{}", encoding="utf-8")
    (root_a / "02_DRV" / "a.tiff").write_bytes(b"tiff-a")
    (root_a / "00_configuraciones" / "profiles" / "session.icc").write_bytes(b"icc")

    window = ICCRawMainWindow()
    try:
        window._activate_session(root_a, load_session(root_a))

        assert window.session_stats_labels["raw_images"].text() == "2"
        assert window.session_stats_labels["tiff_images"].text() == "1"
        assert window.session_stats_labels["icc_profiles"].text() == "1"
        assert window.session_stats_labels["development_profiles"].text() == "1"
        assert window.session_stats_labels["raw_sidecars"].text() == "1"
        assert window.session_stats_labels["queue_items"].text() == "1"

        window._activate_session(root_b, load_session(root_b))
        recent_roots = [
            window.recent_sessions_combo.itemData(i)
            for i in range(window.recent_sessions_combo.count())
        ]
        assert str(root_a.resolve()) in recent_roots
        assert str(root_b.resolve()) in recent_roots

        window.recent_sessions_combo.setCurrentIndex(recent_roots.index(str(root_a.resolve())))
        window._open_selected_recent_session()
        assert window._active_session_root == root_a.resolve()
    finally:
        window.close()


def test_global_configuration_dialog_owns_non_image_settings(qapp):
    window = ICCRawMainWindow()
    try:
        panel_labels = [window.config_tabs.itemText(i) for i in range(window.config_tabs.count())]
        workflow_labels = [
            window.right_workflow_tabs.tabText(i)
            for i in range(window.right_workflow_tabs.count())
        ]
        assert "Nitidez" in workflow_labels
        assert "Nitidez" not in panel_labels
        assert "Detalle" not in panel_labels

        global_tabs = [
            window.global_settings_tabs.tabText(i)
            for i in range(window.global_settings_tabs.count())
        ]
        assert "Firma / C2PA" in global_tabs
        assert "Preview / monitor" in global_tabs

        def is_descendant(widget: QtWidgets.QWidget, ancestor: QtWidgets.QWidget) -> bool:
            parent = widget.parentWidget()
            while parent is not None:
                if parent is ancestor:
                    return True
                parent = parent.parentWidget()
            return False

        assert is_descendant(window.batch_c2pa_cert_path, window.global_settings_dialog)
        assert is_descendant(window.check_fast_raw_preview, window.global_settings_dialog)
        assert is_descendant(window.path_display_profile, window.global_settings_dialog)
        assert not is_descendant(window.batch_c2pa_cert_path, window.config_tabs)
        assert not is_descendant(window.check_fast_raw_preview, window.config_tabs)
        assert not is_descendant(window.path_display_profile, window.config_tabs)
    finally:
        window.close()


def test_display_color_management_defaults_to_system_profile(tmp_path: Path, monkeypatch, qapp):
    profile = tmp_path / "system-monitor.icc"
    srgb_profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
    profile.write_bytes(srgb_profile.tobytes())
    monkeypatch.setattr(gui_module, "detect_system_display_profile", lambda: profile)

    window = ICCRawMainWindow()
    try:
        assert window.check_display_color_management.isChecked()
        assert window.path_display_profile.text() == str(profile)
        assert "Monitor:" in window.display_profile_status.text()
    finally:
        window.close()


def test_display_color_settings_migrate_old_disabled_default(tmp_path: Path, monkeypatch, qapp):
    profile = tmp_path / "system-monitor.icc"
    srgb_profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
    profile.write_bytes(srgb_profile.tobytes())
    settings = gui_module._make_app_settings()
    settings.setValue("display/color_management_enabled", False)
    settings.remove("display/system_profile_default_v1")
    settings.sync()
    monkeypatch.setattr(gui_module, "detect_system_display_profile", lambda: profile)

    window = ICCRawMainWindow()
    try:
        assert window.check_display_color_management.isChecked()
        assert window.path_display_profile.text() == str(profile)
    finally:
        window.close()


def test_histogram_uses_colorimetric_preview_before_monitor_transform(tmp_path: Path, qapp):
    window = ICCRawMainWindow()
    try:
        profile = tmp_path / "generated-profile.icc"
        profile.write_bytes(b"fake profile" * 32)
        window.path_profile_active.setText(str(profile))
        window.chk_apply_profile.setChecked(False)
        window._preview_srgb = gui_module.np.asarray(
            [
                [
                    [1.0, 0.0, 0.0],
                    [0.0, 0.0, 0.0],
                ]
            ],
            dtype=gui_module.np.float32,
        )
        monitor_display = gui_module.np.zeros((1, 2, 3), dtype=gui_module.np.uint8)

        window._set_result_display_u8(monitor_display, compare_enabled=False)

        metrics = window.viewer_histogram.clip_metrics()
        assert metrics["highlight_r"] == pytest.approx(0.5)
        assert metrics["shadow_g"] == pytest.approx(1.0)
        assert "antes del ICC del monitor" in window.viewer_histogram.toolTip()
    finally:
        window.close()


def test_right_column_uses_independent_collapsible_sections(qapp):
    window = ICCRawMainWindow()
    try:
        assert isinstance(window.config_tabs, gui_module.CollapsibleToolPanel)
        assert not isinstance(window.config_tabs, QtWidgets.QToolBox)

        window.config_tabs.setItemExpanded(0, True)
        window.config_tabs.setItemExpanded(1, True)
        assert window.config_tabs.isItemExpanded(0)
        assert window.config_tabs.isItemExpanded(1)

        window.config_tabs.setItemExpanded(0, False)
        qapp.processEvents()
        assert not window.config_tabs.isItemExpanded(0)
        assert window.config_tabs.isItemExpanded(1)
        first_section = window.config_tabs._items[0]["section"]
        first_header = window.config_tabs._items[0]["header"]
        assert first_section.maximumHeight() <= first_header.sizeHint().height() + 4
        assert window.config_tabs._items[0]["body"].isHidden()
    finally:
        window.close()


def test_advanced_tone_curve_is_persisted_in_render_state(qapp):
    window = ICCRawMainWindow()
    try:
        window.check_tone_curve_enabled.setChecked(True)
        window._set_tone_curve_range_controls(0.08, 0.92)
        window.tone_curve_editor.set_points([(0.0, 0.0), (0.5, 0.72), (1.0, 1.0)])

        state = window._render_adjustment_state()
        kwargs = window._render_adjustment_kwargs()

        assert state["tone_curve_enabled"] is True
        assert state["tone_curve_preset"] == "custom"
        assert state["tone_curve_black_point"] == 0.08
        assert state["tone_curve_white_point"] == 0.92
        assert state["tone_curve_points"][1] == [0.5, 0.72]
        assert state["tone_curve_channel"] == "luminance"
        assert state["tone_curve_channel_points"]["luminance"][1] == [0.5, 0.72]
        assert kwargs["tone_curve_points"] == state["tone_curve_points"]
        assert kwargs["tone_curve_channel_points"] == state["tone_curve_channel_points"]
        assert kwargs["tone_curve_black_point"] == 0.08
        assert kwargs["tone_curve_white_point"] == 0.92
        assert window.tone_curve_editor.sizeHint().width() == window.tone_curve_editor.sizeHint().height()
        assert window.tone_curve_editor.hasHeightForWidth()
    finally:
        window.close()


def test_tone_curve_editor_preserves_per_channel_points(qapp):
    window = ICCRawMainWindow()
    try:
        window.check_tone_curve_enabled.setChecked(True)
        window.tone_curve_editor.set_points([(0.0, 0.0), (0.45, 0.7), (1.0, 1.0)])
        window._set_combo_data(window.combo_tone_curve_channel, "red")
        window.tone_curve_editor.set_points([(0.0, 0.0), (0.35, 0.58), (1.0, 1.0)])

        state = window._render_adjustment_state()
        kwargs = window._render_adjustment_kwargs()

        assert state["tone_curve_channel"] == "red"
        assert state["tone_curve_channel_points"]["luminance"][1] == [0.45, 0.7]
        assert state["tone_curve_channel_points"]["red"][1] == [0.35, 0.58]
        assert kwargs["tone_curve_points"] == state["tone_curve_channel_points"]["luminance"]
        assert kwargs["tone_curve_channel_points"]["red"][1] == [0.35, 0.58]
    finally:
        window.close()


def test_neutral_eyedropper_updates_temperature_and_tint(qapp):
    window = ICCRawMainWindow()
    try:
        sample = gui_module.np.array([0.18, 0.24, 0.34], dtype=gui_module.np.float32)
        window._original_linear = gui_module.np.tile(sample.reshape((1, 1, 3)), (24, 24, 1))

        window.btn_neutral_picker.click()
        assert window._neutral_picker_active is True

        window._on_result_image_click(12, 12)
        kwargs = window._render_adjustment_kwargs()
        corrected = gui_module.apply_render_adjustments(window._original_linear, **kwargs)[12, 12]

        assert window._neutral_picker_active is False
        assert window.combo_illuminant_render.currentText() == "Personalizado"
        assert "Punto neutro: RGB" in window.label_neutral_picker.text()
        assert float(gui_module.np.std(corrected)) < float(gui_module.np.std(sample)) * 0.4
    finally:
        window.close()


def test_manual_chart_marks_clear_when_selected_image_changes(tmp_path: Path, qapp):
    first = tmp_path / "chart_01.tiff"
    second = tmp_path / "chart_02.tiff"
    Image.new("RGB", (32, 32), (180, 180, 180)).save(first)
    Image.new("RGB", (32, 32), (90, 90, 90)).save(second)

    window = ICCRawMainWindow()
    try:
        window._set_current_directory(tmp_path)
        first_item = window.file_list.item(0)
        second_item = window.file_list.item(1)
        assert first_item is not None
        assert second_item is not None

        window.file_list.setCurrentItem(first_item)
        qapp.processEvents()
        window._original_linear = gui_module.np.ones((32, 32, 3), dtype=gui_module.np.float32)
        window._begin_manual_chart_marking()
        window._on_manual_chart_click(4, 4)
        window._on_manual_chart_click(24, 4)

        assert len(window._manual_chart_points) == 2
        assert len(window.image_result_single._overlay_points) == 2

        window.file_list.setCurrentItem(second_item)
        qapp.processEvents()

        assert window._manual_chart_points == []
        assert window._manual_chart_points_source is None
        assert window.image_result_single._overlay_points == []
        assert window.manual_chart_points_label.text() == "Puntos: 0/4"
    finally:
        window.close()


def test_preview_reuses_detail_adjustment_cache_for_tonal_changes(qapp, monkeypatch):
    calls = {"detail": 0}

    def fake_apply_adjustments(image, **_kwargs):
        calls["detail"] += 1
        return image.copy()

    monkeypatch.setattr(gui_module, "apply_adjustments", fake_apply_adjustments)

    window = ICCRawMainWindow()
    try:
        window._original_linear = gui_module.np.full((48, 64, 3), 0.25, dtype=gui_module.np.float32)
        window._last_loaded_preview_key = "unit-preview"

        window._refresh_preview()
        assert calls["detail"] == 1

        window.slider_brightness.setValue(12)
        window._preview_refresh_timer.stop()
        window._refresh_preview()
        assert calls["detail"] == 1

        window.slider_sharpen.setValue(30)
        window._preview_refresh_timer.stop()
        window._refresh_preview()
        assert calls["detail"] == 2
    finally:
        window.close()


def test_gui_downgrades_amaze_when_gpl3_pack_is_missing(qapp, monkeypatch):
    monkeypatch.setattr(pipeline.rawpy, "flags", {"DEMOSAIC_PACK_GPL3": False})
    window = ICCRawMainWindow()
    try:
        window._apply_recipe_to_controls(Recipe(demosaic_algorithm="amaze"))
        recipe = window._build_effective_recipe()
        assert recipe.demosaic_algorithm == "dcb"
    finally:
        window.close()


def test_gui_c2pa_config_reads_controls_without_persisting_passphrase(tmp_path: Path, qapp):
    cert_path = tmp_path / "probraw-cert.pem"
    key_path = tmp_path / "probraw-key.pem"
    manifest_path = tmp_path / "profile_report.json"
    cert_path.write_text("certificate", encoding="utf-8")
    key_path.write_text("private key", encoding="utf-8")
    manifest_path.write_text("{}", encoding="utf-8")

    window = ICCRawMainWindow()
    try:
        window.profile_report_out.setText(str(manifest_path))
        window.session_name_edit.setText("unit-session")
        window.batch_c2pa_cert_path.setText(str(cert_path))
        window.batch_c2pa_key_path.setText(str(key_path))
        window.batch_c2pa_key_passphrase.setText("test-passphrase")
        window.batch_c2pa_timestamp_url.setText("http://tsa.example.test")
        window.batch_c2pa_signer_name.setText("ProbRAW Test")
        window._set_combo_text(window.batch_c2pa_alg, "ps384")

        config = window._c2pa_config_from_controls()
        assert config is not None
        assert config.cert_path == cert_path
        assert config.key_path == key_path
        assert config.key_passphrase == "test-passphrase"
        assert config.alg == "ps384"
        assert config.timestamp_url == "http://tsa.example.test"
        assert config.signer_name == "ProbRAW Test"
        assert config.technical_manifest_path == manifest_path
        assert config.session_id == "unit-session"

        window._save_c2pa_settings()
        assert window._settings.value("c2pa/cert_path") == str(cert_path)
        assert window._settings.value("c2pa/key_path") == str(key_path)
        assert window._settings.value("c2pa/key_passphrase") is None
    finally:
        window.close()


def test_process_batch_files_passes_gui_c2pa_config_to_signer(tmp_path: Path, monkeypatch, qapp):
    image_path = tmp_path / "frame.png"
    out_dir = tmp_path / "out"
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    Image.new("RGB", (16, 16), (80, 120, 160)).save(image_path)
    cert_path.write_text("certificate", encoding="utf-8")
    key_path.write_text("private key", encoding="utf-8")
    c2pa_config = C2PASignConfig(cert_path=cert_path, key_path=key_path)
    proof_config = ProbRawProofConfig(private_key_path=key_path, public_key_path=None)
    captured: dict[str, object] = {}

    def fake_write_signed_profiled_tiff(out_tiff, image_linear_rgb, **kwargs):
        captured["c2pa_config"] = kwargs["c2pa_config"]
        captured["source_raw"] = kwargs["source_raw"]
        captured["recipe"] = kwargs["recipe"]
        captured["render_adjustments"] = kwargs["render_adjustments"]
        captured["tiff_compression"] = kwargs["tiff_compression"]
        captured["tiff_maxworkers"] = kwargs["tiff_maxworkers"]
        Path(out_tiff).parent.mkdir(parents=True, exist_ok=True)
        Path(out_tiff).write_bytes(b"signed tiff")
        return "embedded_profile", ProbRawProofResult(
            proof_path=str(Path(out_tiff).with_suffix(".proof.json")),
            proof_sha256="proof-sha",
            output_tiff_sha256="tiff-sha",
            raw_sha256="raw-sha",
            signer_public_key_sha256="pub-sha",
        )

    monkeypatch.setattr(gui_module, "write_signed_profiled_tiff", fake_write_signed_profiled_tiff)

    window = ICCRawMainWindow()
    try:
        payload = window._process_batch_files(
            files=[image_path],
            out_dir=out_dir,
            recipe=Recipe(output_space="srgb", output_linear=False),
            apply_adjust=False,
            use_profile=False,
            profile_path=None,
            denoise_luma=0.0,
            denoise_color=0.0,
            sharpen_amount=0.0,
            sharpen_radius=0.0,
            lateral_ca_red_scale=1.0,
            lateral_ca_blue_scale=1.0,
            render_adjustments={},
            c2pa_config=c2pa_config,
            proof_config=proof_config,
            tiff_compression="zip",
            tiff_maxworkers=3,
        )

        assert payload["errors"] == []
        assert len(payload["outputs"]) == 1
        assert captured["c2pa_config"] is c2pa_config
        assert captured["source_raw"] == image_path
        assert captured["recipe"].output_space == "srgb"
        assert captured["render_adjustments"] == {"applied": False}
        assert captured["tiff_compression"] == "zip"
        assert captured["tiff_maxworkers"] == 3
        assert payload["tiff_maxworkers"] == 3
    finally:
        window.close()


def test_process_batch_files_applies_sharpening_to_rendered_pixels(tmp_path: Path, monkeypatch, qapp):
    image_path = tmp_path / "edge.png"
    out_dir = tmp_path / "out"
    Image.new("RGB", (32, 32), (128, 128, 128)).save(image_path)
    x = gui_module.np.linspace(0.15, 0.85, 64, dtype=gui_module.np.float32)
    base = gui_module.np.repeat(x[None, :, None], 48, axis=0)
    base = gui_module.np.repeat(base, 3, axis=2)
    base[:, 32:, :] += 0.08
    base = gui_module.np.clip(base, 0.0, 1.0)
    captured: dict[str, object] = {}

    def fake_write_signed_profiled_tiff(out_tiff, image_linear_rgb, **kwargs):
        captured["image"] = gui_module.np.asarray(image_linear_rgb).copy()
        captured["detail_adjustments"] = kwargs["detail_adjustments"]
        Path(out_tiff).parent.mkdir(parents=True, exist_ok=True)
        Path(out_tiff).write_bytes(b"signed tiff")
        return "standard_srgb_output_icc", ProbRawProofResult(
            proof_path=str(Path(out_tiff).with_suffix(".proof.json")),
            proof_sha256="proof-sha",
            output_tiff_sha256="tiff-sha",
            raw_sha256="raw-sha",
            signer_public_key_sha256="pub-sha",
        )

    monkeypatch.setattr(gui_module, "read_image", lambda _path: base.copy())
    monkeypatch.setattr(gui_module, "write_signed_profiled_tiff", fake_write_signed_profiled_tiff)

    window = ICCRawMainWindow()
    try:
        payload = window._process_batch_files(
            files=[image_path],
            out_dir=out_dir,
            recipe=Recipe(output_space="srgb", output_linear=False),
            apply_adjust=True,
            use_profile=False,
            profile_path=None,
            denoise_luma=0.0,
            denoise_color=0.0,
            sharpen_amount=1.0,
            sharpen_radius=1.2,
            lateral_ca_red_scale=1.0,
            lateral_ca_blue_scale=1.0,
            render_adjustments={},
            c2pa_config=None,
            proof_config=ProbRawProofConfig(private_key_path=None),
        )

        expected = window._apply_output_adjustments(
            base,
            denoise_luma=0.0,
            denoise_color=0.0,
            sharpen_amount=1.0,
            sharpen_radius=1.2,
            lateral_ca_red_scale=1.0,
            lateral_ca_blue_scale=1.0,
            render_adjustments={},
        )
        assert payload["errors"] == []
        assert captured["detail_adjustments"]["sharpen_amount"] == pytest.approx(1.0)
        assert not gui_module.np.allclose(captured["image"], base)
        assert gui_module.np.allclose(captured["image"], expected)
    finally:
        window.close()


def test_output_adjustments_apply_view_crop_and_level_rotation(qapp):
    window = ICCRawMainWindow()
    try:
        image = gui_module.np.zeros((20, 30, 3), dtype=gui_module.np.float32)
        image[5:15, 10:20, 0] = 1.0
        window._image_crop_normalized_rect = (10 / 30, 5 / 20, 10 / 30, 10 / 20)
        window._viewer_rotation = 90.0

        out = window._apply_output_adjustments(
            image,
            denoise_luma=0.0,
            denoise_color=0.0,
            sharpen_amount=0.0,
            sharpen_radius=1.0,
            lateral_ca_red_scale=1.0,
            lateral_ca_blue_scale=1.0,
            render_adjustments={},
        )

        assert out.shape[:2] == (10, 10)
        assert float(gui_module.np.max(out[..., 0])) == pytest.approx(1.0)
        state = window._output_geometry_adjustment_state(image)
        assert state["crop_rect"] == [10, 5, 10, 10]
        assert state["rotation_degrees"] == pytest.approx(90.0)
    finally:
        window.close()


def test_output_level_rotation_crops_black_canvas_border(qapp):
    window = ICCRawMainWindow()
    try:
        image = gui_module.np.ones((80, 120, 3), dtype=gui_module.np.float32)
        window._viewer_rotation = 7.5

        out = window._apply_output_adjustments(
            image,
            denoise_luma=0.0,
            denoise_color=0.0,
            sharpen_amount=0.0,
            sharpen_radius=1.0,
            lateral_ca_red_scale=1.0,
            lateral_ca_blue_scale=1.0,
            render_adjustments={},
        )

        assert out.shape[0] < 80
        assert out.shape[1] < 120
        assert float(gui_module.np.min(out)) > 0.95
    finally:
        window.close()


def test_output_crop_uses_viewer_floor_ceil_rounding(qapp):
    window = ICCRawMainWindow()
    try:
        image = gui_module.np.zeros((20, 30, 3), dtype=gui_module.np.float32)
        window._image_crop_normalized_rect = (10.2 / 30.0, 5.2 / 20.0, 9.2 / 30.0, 9.2 / 20.0)

        assert window._export_crop_rect_for_image(image) == (10, 5, 10, 10)
    finally:
        window.close()


def test_process_batch_files_skips_global_geometry_for_multi_file_batches(tmp_path: Path, monkeypatch, qapp):
    files = [tmp_path / "a.png", tmp_path / "b.png"]
    out_dir = tmp_path / "out"
    for path in files:
        Image.new("RGB", (32, 32), (128, 128, 128)).save(path)
    base = gui_module.np.zeros((20, 30, 3), dtype=gui_module.np.float32)
    base[5:15, 10:20, 0] = 1.0
    captured: list[dict[str, object]] = []

    def fake_write_signed_profiled_tiff(out_tiff, image_linear_rgb, **kwargs):
        captured.append(
            {
                "image": gui_module.np.asarray(image_linear_rgb).copy(),
                "render_adjustments": kwargs["render_adjustments"],
            }
        )
        Path(out_tiff).parent.mkdir(parents=True, exist_ok=True)
        Path(out_tiff).write_bytes(b"signed tiff")
        return "standard_srgb_output_icc", ProbRawProofResult(
            proof_path=str(Path(out_tiff).with_suffix(".proof.json")),
            proof_sha256="proof-sha",
            output_tiff_sha256="tiff-sha",
            raw_sha256="raw-sha",
            signer_public_key_sha256="pub-sha",
        )

    monkeypatch.setattr(gui_module, "read_image", lambda _path: base.copy())
    monkeypatch.setattr(gui_module, "write_signed_profiled_tiff", fake_write_signed_profiled_tiff)

    window = ICCRawMainWindow()
    try:
        window._image_crop_normalized_rect = (10 / 30, 5 / 20, 10 / 30, 10 / 20)
        window._viewer_rotation = 90.0
        payload = window._process_batch_files(
            files=files,
            out_dir=out_dir,
            recipe=Recipe(output_space="srgb", output_linear=False),
            apply_adjust=True,
            use_profile=False,
            profile_path=None,
            denoise_luma=0.0,
            denoise_color=0.0,
            sharpen_amount=0.0,
            sharpen_radius=1.0,
            lateral_ca_red_scale=1.0,
            lateral_ca_blue_scale=1.0,
            render_adjustments={},
            c2pa_config=None,
            proof_config=ProbRawProofConfig(private_key_path=None),
        )

        assert payload["errors"] == []
        assert payload["geometry_policy"] == "single_file_only"
        assert len(captured) == 2
        for item in captured:
            assert item["image"].shape == base.shape
            assert item["render_adjustments"]["geometry"]["crop_rect"] is None
            assert item["render_adjustments"]["geometry"]["rotation_degrees"] == pytest.approx(0.0)
    finally:
        window.close()


def test_preview_pyramid_limits_synchronous_levels(qapp):
    window = ICCRawMainWindow()
    try:
        assert window._preview_pyramid_levels_to_write(source_side=6000, requested_side=1600) == [4096, 3200]
        assert window._preview_pyramid_levels_to_write(source_side=1900, requested_side=1600) == [1600]
        assert window._preview_pyramid_levels_to_write(source_side=1000, requested_side=1600) == [800]
    finally:
        window.close()


def test_visible_export_recipe_defaults_camera_rgb_without_icc_to_prophoto(qapp):
    window = ICCRawMainWindow()
    try:
        recipe = window._visible_export_recipe_for_color_management(
            Recipe(
                output_space="scene_linear_camera_rgb",
                output_linear=True,
                tone_curve="linear",
                white_balance_mode="fixed",
                wb_multipliers=[1.0, 1.0, 1.0, 1.0],
                profiling_mode=True,
            ),
            input_profile_path=None,
        )

        assert recipe.output_space == "prophoto_rgb"
        assert recipe.output_linear is False
        assert recipe.tone_curve.startswith("gamma:")
        assert recipe.white_balance_mode == "camera_metadata"
        assert recipe.profiling_mode is False
    finally:
        window.close()


def test_visible_export_recipe_normalizes_generic_output_without_icc(qapp):
    window = ICCRawMainWindow()
    try:
        recipe = window._visible_export_recipe_for_color_management(
            Recipe(
                output_space="prophoto_rgb",
                output_linear=False,
                tone_curve="gamma:1.8",
                white_balance_mode="fixed",
                wb_multipliers=[1.0, 1.0, 1.0, 1.0],
                profiling_mode=True,
            ),
            input_profile_path=None,
        )

        assert recipe.output_space == "prophoto_rgb"
        assert recipe.white_balance_mode == "camera_metadata"
        assert recipe.profiling_mode is False
    finally:
        window.close()


def test_generic_output_space_change_updates_visible_controls_without_icc(qapp):
    window = ICCRawMainWindow()
    try:
        window._apply_recipe_to_controls(
            Recipe(
                output_space="scene_linear_camera_rgb",
                output_linear=True,
                tone_curve="linear",
                white_balance_mode="fixed",
                wb_multipliers=[1.0, 1.0, 1.0, 1.0],
                profiling_mode=True,
            )
        )

        window._set_combo_text(window.combo_output_space, "prophoto_rgb")

        assert window.combo_wb_mode.currentData() == "camera_metadata"
        assert window.check_output_linear.isChecked() is False
        assert window.check_profiling_mode.isChecked() is False
    finally:
        window.close()
