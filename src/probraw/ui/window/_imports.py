"""Shared namespace for the split main-window mixins.

The original GUI was a single module, so tests and some integrations monkeypatch
selected callables on the public GUI module. The wrappers below keep that
behavior while the implementation lives in smaller modules.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageOps
import yaml

from ...chart.detection import detect_chart_from_corners_array, draw_detection_overlay_array
from ...chart.sampling import (
    ReferenceCatalog,
    bundled_reference_catalogs,
    reference_catalog_label,
    reference_catalog_template,
)
from ...analysis.mtf import MTFResult, analyze_slanted_edge_mtf
from ...core.color import delta_e76, delta_e2000
from ...core.models import Point2, Recipe, to_json_dict, write_json
from ...core.recipe import load_recipe, save_recipe
from ...core.external import external_tool_path, run_external
from ...core.utils import (
    RAW_EXTENSIONS,
    read_image as _read_image,
    resolve_tiff_maxworkers,
    versioned_output_path,
    write_tiff16,
)
from ...display_color import (
    cache_display_profile_bytes,
    detect_system_display_profile as _detect_system_display_profile,
    display_profile_label,
    prewarm_profiled_display_lut,
    profiled_float_to_display_u8,
    profiled_u8_to_display_u8,
    rgb_float_to_u8,
    srgb_to_display_u8,
    srgb_u8_to_display_u8,
)
from ...gui_config import *  # noqa: F403
from ...metadata_viewer import inspect_file_metadata, metadata_display_sections, metadata_sections_text
from ...profile.export import (
    _resolve_batch_workers as resolve_batch_workers,
    profile_path_for_render_settings,
    write_signed_profiled_tiff as _write_signed_profiled_tiff,
)
from ...profile.generic import (
    ensure_generic_output_profile,
    generic_output_profile,
    is_generic_output_space,
    standard_profile_search_dirs,
)
from ...profile.gamut import (
    build_gamut_diagnostics as _build_gamut_diagnostics,
    build_gamut_pair_diagnostics as _build_gamut_pair_diagnostics,
    evaluate_lab_gamut_membership as _evaluate_lab_gamut_membership,
)
from ...profile.builder import _lookup_lab_with_icc as _lookup_lab_with_icc
from ...provenance.c2pa import C2PASignConfig, DEFAULT_TIMESTAMP_URL, auto_c2pa_config
from ...provenance.probraw_proof import (
    ProbRawProofConfig,
    generate_ed25519_identity,
    proof_config_from_environment,
)
from ...qa_compare import compare_qa_reports
from ...raw.pipeline import (
    develop_image_array as _develop_image_array,
    develop_standard_output_array,
    is_standard_output_space,
    is_libraw_demosaic_supported,
    rawpy_feature_flags,
    rawpy_postprocess_parameter_supported,
    unavailable_demosaic_reason,
)
from ...raw.metadata import estimate_pixel_pitch_um
from ...raw.preview import (
    apply_adjustments as _apply_adjustments,
    apply_render_adjustments,
    apply_profile_preview,
    estimate_temperature_tint_from_neutral_sample,
    extract_embedded_preview as _extract_embedded_preview,
    extract_embedded_thumbnail as _extract_embedded_thumbnail,
    linear_to_srgb_display,
    load_image_for_preview as _load_image_for_preview,
    normalize_tone_curve_points,
    preview_analysis_text,
    render_adjustments_affine_u8,
    standard_profile_to_srgb_display,
    standard_profile_to_srgb_u8_display,
)
from ...reporting import check_amaze_backend, check_external_tools
from ...session import create_session, ensure_session_structure, load_session, save_session, session_file_path
from ...sidecar import (
    LEGACY_RAW_SIDECAR_SUFFIXES,
    load_raw_sidecar,
    raw_sidecar_path,
    write_raw_color_samples as _write_raw_color_samples,
    write_raw_mtf_analysis as _write_raw_mtf_analysis,
    write_raw_sidecar as _write_raw_sidecar,
)
from ...update import auto_update, check_latest_release, default_update_download_dir
from ...version import __version__
from ...workflow import (
    DEFAULT_QA_MAX_DELTA_E2000_MAX,
    DEFAULT_QA_MEAN_DELTA_E2000_MAX,
    auto_generate_profile_from_charts as _auto_generate_profile_from_charts,
)
from ..widgets import (
    CollapsibleToolPanel,
    ColorSampleGamutWidget,
    Gamut3DWidget,
    ImagePanel,
    MTFComparisonPlotWidget,
    MTFPlotWidget,
    PersistentSideTabWidget,
    RGBHistogramWidget,
    ToneCurveEditor,
)
from .core import TaskThread

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except Exception:  # pragma: no cover - entorno sin GUI
    QtCore = None
    QtGui = None
    QtWidgets = None


def _gui_callable(name: str, fallback):
    for module_name in ("probraw.gui",):
        module = sys.modules.get(module_name)
        candidate = getattr(module, name, None) if module is not None else None
        if candidate is not None and candidate is not globals().get(name):
            return candidate
    return fallback


def read_image(*args, **kwargs):
    return _gui_callable("read_image", _read_image)(*args, **kwargs)


def detect_system_display_profile(*args, **kwargs):
    return _gui_callable("detect_system_display_profile", _detect_system_display_profile)(*args, **kwargs)


def write_signed_profiled_tiff(*args, **kwargs):
    return _gui_callable("write_signed_profiled_tiff", _write_signed_profiled_tiff)(*args, **kwargs)


def develop_image_array(*args, **kwargs):
    return _gui_callable("develop_image_array", _develop_image_array)(*args, **kwargs)


def apply_adjustments(*args, **kwargs):
    return _gui_callable("apply_adjustments", _apply_adjustments)(*args, **kwargs)


def extract_embedded_preview(*args, **kwargs):
    return _gui_callable("extract_embedded_preview", _extract_embedded_preview)(*args, **kwargs)


def extract_embedded_thumbnail(*args, **kwargs):
    return _gui_callable("extract_embedded_thumbnail", _extract_embedded_thumbnail)(*args, **kwargs)


def load_image_for_preview(*args, **kwargs):
    return _gui_callable("load_image_for_preview", _load_image_for_preview)(*args, **kwargs)


def write_raw_sidecar(*args, **kwargs):
    return _gui_callable("write_raw_sidecar", _write_raw_sidecar)(*args, **kwargs)


def write_raw_mtf_analysis(*args, **kwargs):
    return _gui_callable("write_raw_mtf_analysis", _write_raw_mtf_analysis)(*args, **kwargs)


def write_raw_color_samples(*args, **kwargs):
    return _gui_callable("write_raw_color_samples", _write_raw_color_samples)(*args, **kwargs)


def auto_generate_profile_from_charts(*args, **kwargs):
    return _gui_callable("auto_generate_profile_from_charts", _auto_generate_profile_from_charts)(*args, **kwargs)


def build_gamut_diagnostics(*args, **kwargs):
    return _gui_callable("build_gamut_diagnostics", _build_gamut_diagnostics)(*args, **kwargs)


def build_gamut_pair_diagnostics(*args, **kwargs):
    return _gui_callable("build_gamut_pair_diagnostics", _build_gamut_pair_diagnostics)(*args, **kwargs)


def evaluate_lab_gamut_membership(*args, **kwargs):
    return _gui_callable("evaluate_lab_gamut_membership", _evaluate_lab_gamut_membership)(*args, **kwargs)


def lookup_lab_with_icc(*args, **kwargs):
    return _gui_callable("lookup_lab_with_icc", _lookup_lab_with_icc)(*args, **kwargs)
