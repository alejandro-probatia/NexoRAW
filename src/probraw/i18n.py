"""
Sistema de internacionalización (i18n) para ProbRAW.

Idioma nativo: español (es). Sin fichero .qm cargado, la app muestra español.
Las traducciones se almacenan en src/probraw/resources/locales/<lang>.qm
y sus fuentes editables en locales/<lang>.ts (en la raíz del proyecto).

Uso básico
----------
# En main(), después de crear QApplication:
    from .i18n import install_translator
    install_translator(app, lang)           # lang: "es" | "en" | ...

# En módulos que no heredan de QObject (listas de opciones, etc.):
    from .i18n import _tr
    LABEL = _tr("Texto visible")            # se traduce en runtime

# En clases QObject/QWidget, usar el mecanismo nativo de Qt:
    self.tr("Texto visible")

Workflow para añadir o actualizar traducciones
----------------------------------------------
1. Extraer cadenas nuevas del código fuente:
       pyside6-lupdate src/probraw/gui.py [otros .py] -ts locales/en.ts

2. Editar locales/en.ts con un editor de texto o Qt Linguist y rellenar
   los elementos <translation> vacíos.

3. Compilar a binario:
       pyside6-lrelease locales/en.ts -qm src/probraw/resources/locales/en.qm

4. Hacer commit de ambos ficheros: .ts (fuente) y .qm (compilado).
"""
from __future__ import annotations

from importlib import resources
from pathlib import Path

try:
    from PySide6 import QtCore, QtWidgets
except ImportError:  # pragma: no cover
    QtCore = None
    QtWidgets = None

# Idiomas soportados: código ISO 639-1 → nombre legible.
#
# La aplicación tiene el español como idioma fuente. Mientras la traducción
# inglesa no cubra todas las cadenas de la interfaz, resolvemos siempre a
# español para evitar mezclar idiomas en la UI.
SUPPORTED_LANGUAGES: dict[str, str] = {
    "es": "Español",
}

# Valor especial para QSettings "app/language": sigue al idioma del SO.
AUTO_LANG = "auto"

_active_translator: "QtCore.QTranslator | None" = None
_active_lang: str = "es"


def detect_system_language() -> str:
    """Devuelve el idioma efectivo soportado por la interfaz."""
    return "es"


def resolve_language(setting_value: str | None) -> str:
    """Convierte el valor guardado en QSettings al idioma efectivo a instalar.

    - "" / None / "auto" → español.
    - "es" → respeta la elección manual.
    - Cualquier otro valor desconocido → español.
    """
    raw = (setting_value or "").strip().lower()
    if raw in SUPPORTED_LANGUAGES:
        return raw
    return "es"


def install_translator(
    app: "QtWidgets.QApplication",
    lang: str,
) -> "QtCore.QTranslator | None":
    """Carga el traductor para `lang` e instálalo en `app`.

    Devuelve el QTranslator instalado, o None si:
    - `lang` es "es" (idioma nativo, no hace falta .qm)
    - no existe el fichero .qm para ese idioma
    - PySide6 no está disponible
    """
    global _active_translator, _active_lang

    if QtCore is None:
        return None

    # Desinstalar cualquier traductor previo
    if _active_translator is not None:
        app.removeTranslator(_active_translator)
        _active_translator = None

    _active_lang = lang if lang in SUPPORTED_LANGUAGES else "es"

    if _active_lang == "es":
        # Español es el idioma nativo; sin traductor la app ya muestra español.
        return None

    qm_path = _qm_path(_active_lang)
    if qm_path is None:
        return None

    translator = QtCore.QTranslator(app)
    if translator.load(str(qm_path)):
        app.installTranslator(translator)
        _active_translator = translator
        return translator

    return None


def active_lang() -> str:
    """Devuelve el código del idioma activo ("es", "en", …)."""
    return _active_lang


def _qm_path(lang: str) -> Path | None:
    """Devuelve la ruta al fichero .qm para `lang`, o None si no existe."""
    try:
        locale_dir = resources.files("probraw.resources").joinpath("locales")
        qm = locale_dir / f"{lang}.qm"
        path = Path(str(qm))
        return path if path.is_file() else None
    except Exception:
        return None


def _tr(text: str, context: str = "global") -> str:
    """Traducción para uso fuera de clases QObject (listas de opciones, etc.).

    En tiempo de carga de módulo retorna el texto tal cual (el texto en
    español sirve como fallback). Llámala desde funciones o propiedades
    evaluadas en runtime para que la traducción surta efecto.

    Ejemplo:
        def demosaic_options():
            return [(_tr("Alta calidad"), "dcb"), ...]
    """
    if QtCore is None:
        return text
    return QtCore.QCoreApplication.translate(context, text)
