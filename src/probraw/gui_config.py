from __future__ import annotations

import os
from importlib import resources
from pathlib import Path

from .core.utils import RAW_EXTENSIONS

IMAGE_EXTENSIONS = {".tif", ".tiff", ".png", ".jpg", ".jpeg"}
BROWSABLE_EXTENSIONS = RAW_EXTENSIONS.union(IMAGE_EXTENSIONS)
PROFILE_CHART_EXTENSIONS = set(RAW_EXTENSIONS)
PROFILE_REFERENCE_FORBIDDEN_DIRS = {
    "exports": "exportaciones TIFF",
    "work": "intermedios de trabajo",
    "profiles": "perfiles ICC",
    "config": "configuracion",
}

LAYOUT_VERSION = 5
APP_NAME = "ProbRAW"
ORG_NAME = "ProbRAW"
APP_ICON_RESOURCE = "icons/probraw-icon.png"
PROJECT_DIRECTOR_NAME = (
    (
        os.environ.get("PROBRAW_PROJECT_DIRECTOR")
        or os.environ.get("NEXORAW_PROJECT_DIRECTOR")
        or "Alejandro Maestre Gasteazi"
    ).strip()
    or "Alejandro Maestre Gasteazi"
)
PROJECT_CONTACT_EMAIL = (os.environ.get("PROBRAW_CONTACT_EMAIL") or "alejandro.maestre@imagencientifica.es").strip()
PROJECT_COLLABORATORS = (
    ("PROBATIA", "https://probatia.com"),
    ("AEICF", "https://imagencientifica.es"),
)

DEFAULT_THUMBNAIL_SIZE = 132
MIN_THUMBNAIL_SIZE = 72
MAX_THUMBNAIL_SIZE = 220
PREVIEW_CACHE_MAX_ENTRIES = 8
PREVIEW_CACHE_MAX_BYTES = 384 * 1024 * 1024
PREVIEW_DISK_CACHE_MAX_ENTRIES = 48
PREVIEW_DISK_CACHE_MAX_BYTES = 2 * 1024 * 1024 * 1024
THUMBNAIL_CACHE_MAX_ENTRIES = 512
THUMBNAIL_DISK_CACHE_MAX_ENTRIES = 4096
THUMBNAIL_DISK_CACHE_MAX_BYTES = 512 * 1024 * 1024
THUMBNAIL_DISK_PRUNE_INTERVAL_WRITES = 512
THUMBNAIL_BATCH_SIZE = 48
THUMBNAIL_PREFETCH_MARGIN_PAGES = 2
MTF_ROI_DISK_CACHE_MAX_ENTRIES = 256
MTF_ROI_DISK_CACHE_MAX_BYTES = 1024 * 1024 * 1024

PREVIEW_REFRESH_DEBOUNCE_MS = 120
PREVIEW_REFRESH_THROTTLE_MS = 65
PREVIEW_TONE_CURVE_DRAG_THROTTLE_MS = 90
PREVIEW_FINAL_REFRESH_IDLE_DELAY_MS = 8000
PREVIEW_INTERACTIVE_VIEWPORT_MARGIN_PX = 32
PREVIEW_INTERACTIVE_PARALLEL_MIN_PIXELS = 180_000
PREVIEW_AUTO_BASE_MAX_SIDE = 2600
PREVIEW_FINAL_ADJUSTMENT_MAX_SIDE = 1800
PREVIEW_INTERACTIVE_MAX_SIDE = 1200
PREVIEW_INTERACTIVE_DRAG_MAX_SIDE = 720
PREVIEW_INTERACTIVE_TONAL_MAX_SIDE = 560
PREVIEW_INTERACTIVE_STUCK_TIMEOUT_MS = 8000
PREVIEW_PRECISION_MIN_MAX_SIDE = 6000
PREVIEW_PROFILE_CACHE_MAX_ENTRIES = 8
PREVIEW_PROFILE_APPLY_MAX_SIDE = 1400
PREVIEW_INTERACTIVE_BYPASS_DISPLAY_ICC_ENV = "PROBRAW_PREVIEW_INTERACTIVE_BYPASS_DISPLAY_ICC"
PREVIEW_SYSTEM_DISPLAY_COLOR_MANAGEMENT_ENV = "PROBRAW_SYSTEM_DISPLAY_COLOR_MANAGEMENT"
PREVIEW_AUTOMATIC_FULL_FINAL_REFRESH_ENV = "PROBRAW_AUTOMATIC_FULL_FINAL_REFRESH"

IMAGE_PANEL_BACKGROUND = "#2b2b2b"
IMAGE_PANEL_BORDER = "#5a5a5a"
IMAGE_PANEL_TEXT = "#e6e6e6"
VIEWER_HISTOGRAM_SHADOW_CLIP_U8 = 1
VIEWER_HISTOGRAM_HIGHLIGHT_CLIP_U8 = 254
VIEWER_HISTOGRAM_CLIP_ALERT_RATIO = 5e-4

LEGACY_PROJECT_DIR_RENAMES = {
    "charts": Path("01_ORG"),
    "raw": Path("01_ORG"),
    "exports": Path("02_DRV"),
    "config": Path("00_configuraciones"),
    "profiles": Path("00_configuraciones") / "profiles",
    "work": Path("00_configuraciones") / "work",
}

SETTINGS_DIR_ENV = "PROBRAW_SETTINGS_DIR"
LEGACY_SETTINGS_DIR_ENV = "NEXORAW_SETTINGS_DIR"

DEMOSAIC_OPTIONS = [
    ("DCB (LibRaw, alta calidad)", "dcb"),
    ("DHT", "dht"),
    ("AHD", "ahd"),
    ("AAHD", "aahd"),
    ("VNG", "vng"),
    ("PPG", "ppg"),
    ("Lineal", "linear"),
    ("AMaZE (GPL3)", "amaze"),
]
PREVIEW_BALANCED_DEMOSAIC_ORDER = ("dcb", "ahd", "dht", "aahd", "ppg", "vng", "linear")

ILLUMINANT_OPTIONS = [
    ("A / tungsteno (2856 K)", 2856, 0),
    ("D50 (5003 K)", 5003, 0),
    ("D55 (5503 K)", 5503, 0),
    ("Flash / D55 (5500 K)", 5500, 0),
    ("D60 (6000 K)", 6000, 0),
    ("D65 (6504 K)", 6504, 0),
    ("D75 (7504 K)", 7504, 0),
    ("Personalizado", None, None),
]

WB_MODE_OPTIONS = [
    ("Fijo (multiplicadores manuales)", "fixed"),
    ("Desde metadatos de camara", "camera_metadata"),
    ("Automatico LibRaw", "auto"),
]

BLACK_MODE_OPTIONS = [
    ("Metadata", "metadata"),
    ("Fijo", "fixed"),
    ("White level", "white"),
]

LIBRAW_HIGHLIGHT_MODE_OPTIONS = [
    ("Recortar", "clip"),
    ("Ignorar", "ignore"),
    ("Mezclar", "blend"),
    ("Reconstruir", "reconstruct"),
]

TONE_OPTIONS = [
    ("Lineal", "linear"),
    ("sRGB", "srgb"),
    ("Gamma", "gamma"),
]

TONE_CURVE_PRESETS: list[tuple[str, str, list[tuple[float, float]]]] = [
    ("Lineal", "linear", [(0.0, 0.0), (1.0, 1.0)]),
    (
        "Contraste suave",
        "soft_contrast",
        [(0.0, 0.0), (0.24, 0.18), (0.50, 0.50), (0.76, 0.84), (1.0, 1.0)],
    ),
    (
        "Similar a película",
        "film_like",
        [(0.0, 0.0), (0.06, 0.015), (0.22, 0.18), (0.52, 0.66), (0.82, 0.92), (1.0, 1.0)],
    ),
    (
        "Sombras levantadas",
        "lift_shadows",
        [(0.0, 0.0), (0.14, 0.20), (0.45, 0.50), (0.78, 0.82), (1.0, 1.0)],
    ),
    (
        "Alto contraste",
        "high_contrast",
        [(0.0, 0.0), (0.18, 0.09), (0.50, 0.50), (0.82, 0.93), (1.0, 1.0)],
    ),
    ("Personalizada", "custom", [(0.0, 0.0), (1.0, 1.0)]),
]

SPACE_OPTIONS = [
    "scene_linear_camera_rgb",
    "srgb",
    "adobe_rgb",
    "prophoto_rgb",
    "camera_rgb",
]
CAMERA_OUTPUT_SPACES = {"scene_linear_camera_rgb", "camera_rgb", "camera"}

SAMPLE_OPTIONS = [
    "trimmed_mean",
    "median",
]

FILTER_MODE_OPTIONS = [
    "off",
    "mild",
    "medium",
    "strong",
]

TIFF_COMPRESSION_OPTIONS = [
    ("Sin compresion", "none"),
    ("ZIP / Deflate", "zip"),
    ("LZW", "lzw"),
    ("JPEG", "jpeg"),
    ("ZSTD", "zstd"),
]

PROFILE_ALGO_OPTIONS = [
    ("Recomendado: Lab cLUT (-al)", "-al"),
    ("Matriz + curvas por canal (-as)", "-as"),
    ("Matriz + gamma comun (-ag)", "-ag"),
    ("Solo matriz colorimetrica (-am)", "-am"),
    ("Avanzado: tabla XYZ cLUT (-ax)", "-ax"),
]

PROFILE_ALGO_HELP = {
    "-as": (
        "Shaper + matrix. Ajusta una matriz 3x3 de camara a XYZ/Lab y curvas "
        "tonales por canal. Es un modelo compacto y conservador, pero puede no "
        "corregir bien desviaciones cromaticas de camara reales con algunas cartas."
    ),
    "-ag": (
        "Gamma + matrix. Similar al modo recomendado, pero usa una respuesta tonal "
        "mas simple. Puede servir para camaras muy regulares, aunque suele ser menos "
        "flexible que shaper + matrix."
    ),
    "-am": (
        "Matrix only. Solo calcula la matriz colorimetrica; no modela la respuesta "
        "tonal. Es util para pruebas tecnicas, no como opcion general de perfilado RAW."
    ),
    "-al": (
        "Lab cLUT. Genera una tabla de correccion en Lab. Es el preset recomendado "
        "para el flujo actual porque Argyll lo usa como modelo robusto por defecto "
        "y, combinado con -u -R, evita dominantes que el modelo shaper+matrix no "
        "siempre corrige."
    ),
    "-ax": (
        "XYZ cLUT. Genera una tabla de correccion en XYZ. Es una opcion avanzada con "
        "riesgo similar a Lab cLUT si hay pocos parches o una carta generica."
    ),
}

PROFILE_QUALITY_OPTIONS = [
    ("Low", "l"),
    ("Medium", "m"),
    ("High", "h"),
    ("Ultra", "u"),
]

PROFILE_QUALITY_HELP = {
    "l": "Baja. Mas rapida; adecuada solo para pruebas.",
    "m": "Media. Equilibrio recomendado para perfiles de sesion.",
    "h": "Alta. Mayor coste de calculo; util cuando hay buena senal y validacion.",
    "u": "Ultra. Coste alto; normalmente innecesaria con una ColorChecker 24.",
}

RECOMMENDED_COLPROF_EXTRA_ARGS = "-u -R"

COLPROF_OPTIONS_HELP = (
    "Tipo de perfil ICC:\n"
    "- Lab cLUT (-al): recomendado. Modela la relacion RGB de camara lineal -> Lab "
    "D50 con la tabla robusta de Argyll y reduce dominantes que una matriz simple "
    "puede dejar sin corregir.\n"
    "- Matriz + curvas por canal (-as): modelo compacto y conservador, util si una "
    "cLUT no es compatible con un flujo externo concreto.\n"
    "- Matriz + gamma comun (-ag): modelo matricial con respuesta tonal mas simple.\n"
    "- Solo matriz (-am): prueba tecnica; no modela respuesta tonal.\n"
    "- XYZ cLUT (-ax): tabla en XYZ; avanzada y menos robusta con cartas escasas o "
    "irregularmente distribuidas.\n\n"
    "Calidad colprof:\n"
    "- Low: rapido para pruebas.\n"
    "- Medium: recomendado por defecto.\n"
    "- High/Ultra: mas calculo; util solo si la captura y la validacion son solidas.\n\n"
    "Argumentos extra recomendados:\n"
    "- -u: en perfiles de entrada, escala automaticamente el punto blanco para permitir "
    "extrapolacion.\n"
    "- -R: restringe blanco <= 1.0 y mantiene negro/primarios positivos.\n\n"
    "Si aparecen avisos de altas luces, revisa exposicion, blancos y referencia Lab "
    "antes de endurecer la calidad o cambiar de modelo."
)

PROFILE_FORMAT_OPTIONS = [".icc", ".icm"]

LEGACY_TEMP_OUTPUT_NAMES = {
    "camera_profile.icc",
    "camera_profile_gui.icc",
    "profile_report_gui.json",
    "probraw_profile_work",
    "development_profile_gui.json",
    "recipe_calibrated_gui.yml",
    "probraw_preview.png",
    "probraw_batch_tiffs",
}


def _app_icon_path() -> Path | None:
    try:
        path = resources.files("probraw.resources").joinpath(APP_ICON_RESOURCE)
    except Exception:
        return None
    if not path.is_file():
        return None
    return Path(str(path))


def _env_flag(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return bool(default)
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return bool(default)
