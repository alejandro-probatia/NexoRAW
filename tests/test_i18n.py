"""Tests para el sistema de i18n: resolución de idioma coherente."""
from __future__ import annotations

from probraw import i18n


def test_resolve_language_keeps_spanish_as_effective_ui_language():
    assert i18n.resolve_language("es") == "es"
    assert i18n.resolve_language("en") == "es"
    assert i18n.resolve_language("auto") == "es"
    assert i18n.resolve_language("") == "es"
    assert i18n.resolve_language(None) == "es"


def test_resolve_language_unknown_value_falls_back_to_system():
    assert i18n.resolve_language("fr") == "es"
    assert i18n.resolve_language("xx") == "es"


def test_detect_system_language_returns_spanish_to_avoid_mixed_ui():
    assert i18n.detect_system_language() == "es"
