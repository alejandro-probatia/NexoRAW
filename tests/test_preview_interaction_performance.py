from __future__ import annotations

import numpy as np

import probraw.ui.window.preview_render as preview_render_module
from probraw.ui.window.preview_recipe import PreviewRecipeMixin
from probraw.ui.window.preview_render import PreviewRenderMixin


class _FakeTimer:
    def __init__(self) -> None:
        self.started: list[int] = []

    def start(self, delay_ms: int) -> None:
        self.started.append(int(delay_ms))


class _RenderChangeWindow(PreviewRecipeMixin):
    def __init__(self, *, interaction_active: bool) -> None:
        self._suspend_render_adjustment_autosave = 0
        self._original_linear = None
        self.interaction_active = interaction_active
        self.history_labels: list[str] = []
        self.persist_calls = 0

    def _is_direct_preview_interaction_active(self) -> bool:
        return self.interaction_active

    def _push_edit_history_snapshot(self, label: str = "") -> None:
        self.history_labels.append(str(label))

    def _active_named_adjustment_profile_id(self, _category: str) -> str:
        return ""

    def _schedule_render_adjustment_sidecar_persist(self) -> None:
        self.persist_calls += 1


class _ColorSampleRefreshWindow(PreviewRecipeMixin):
    def __init__(self, *, interaction_active: bool) -> None:
        self._color_picker_samples = [{"x": 10, "y": 12}]
        self._color_sample_refresh_timer = _FakeTimer()
        self.interaction_active = interaction_active
        self.reschedule_calls = 0
        self.sampled = False

    def _is_preview_interaction_active(self) -> bool:
        return self.interaction_active

    def _schedule_color_picker_samples_refresh(self) -> None:
        self.reschedule_calls += 1

    def _color_picker_source_is_real_pixels(self) -> bool:
        return True

    def _sample_color_patch(self, *_args, **_kwargs):
        self.sampled = True
        return {"rgb": [0.1, 0.2, 0.3], "x": 10, "y": 12, "count": 1, "matrix": "1x1"}

    def tr(self, text: str) -> str:
        return text


class _PreviewRenderWindow(PreviewRenderMixin):
    def __init__(self) -> None:
        self._last_loaded_preview_key = "source-a"
        self._original_linear = object()
        self._interactive_detail_source_cache = {}
        self._interactive_detail_source_cache_order = []


def test_render_control_change_skips_history_and_sidecar_while_dragging():
    window = _RenderChangeWindow(interaction_active=True)

    window._on_render_control_change(preview=False)

    assert window.history_labels == []
    assert window.persist_calls == 0


def test_render_control_change_records_history_when_settled():
    window = _RenderChangeWindow(interaction_active=False)

    window._on_render_control_change(preview=False)

    assert window.history_labels == ["render"]
    assert window.persist_calls == 1


def test_color_sample_refresh_timer_uses_longer_delay_during_interaction():
    window = _ColorSampleRefreshWindow(interaction_active=True)

    PreviewRecipeMixin._schedule_color_picker_samples_refresh(window)

    assert window._color_sample_refresh_timer.started == [650]


def test_color_sample_refresh_reschedules_while_interaction_is_active():
    window = _ColorSampleRefreshWindow(interaction_active=True)

    window._refresh_color_picker_samples_from_current_image()

    assert window.reschedule_calls == 1
    assert not window.sampled


def test_interactive_detail_source_reuses_cache_for_stable_detail(monkeypatch):
    window = _PreviewRenderWindow()
    image = np.zeros((10, 12, 3), dtype=np.float32)
    detail_kwargs = {
        "denoise_luminance": 0.0,
        "denoise_color": 0.0,
        "sharpen_amount": 0.4,
        "sharpen_radius": 1.2,
        "lateral_ca_red_scale": 1.0,
        "lateral_ca_blue_scale": 1.0,
    }
    calls = []

    def fake_apply_adjustments(source, **_kwargs):
        calls.append(np.asarray(source).shape)
        return np.asarray(source, dtype=np.float32) + np.float32(0.25)

    monkeypatch.setattr(preview_render_module, "apply_adjustments", fake_apply_adjustments)

    first = window._interactive_detail_adjusted_source(
        image,
        detail_kwargs,
        source_key="source-a",
        max_side_limit=560,
        viewport_rect=(0, 0, 12, 10),
        use_cache=True,
    )
    second = window._interactive_detail_adjusted_source(
        image,
        detail_kwargs,
        source_key="source-a",
        max_side_limit=560,
        viewport_rect=(0, 0, 12, 10),
        use_cache=True,
    )

    assert len(calls) == 1
    assert np.array_equal(first, second)
    assert len(window._interactive_detail_source_cache) == 1


def test_interactive_detail_source_can_bypass_cache(monkeypatch):
    window = _PreviewRenderWindow()
    image = np.zeros((8, 9, 3), dtype=np.float32)
    detail_kwargs = {
        "denoise_luminance": 0.2,
        "denoise_color": 0.0,
        "sharpen_amount": 0.0,
        "sharpen_radius": 1.0,
        "lateral_ca_red_scale": 1.0,
        "lateral_ca_blue_scale": 1.0,
    }
    calls = []

    def fake_apply_adjustments(source, **_kwargs):
        calls.append(np.asarray(source).shape)
        return np.asarray(source, dtype=np.float32)

    monkeypatch.setattr(preview_render_module, "apply_adjustments", fake_apply_adjustments)

    for _ in range(2):
        window._interactive_detail_adjusted_source(
            image,
            detail_kwargs,
            source_key="source-a",
            max_side_limit=560,
            viewport_rect=None,
            use_cache=False,
        )

    assert len(calls) == 2
    assert window._interactive_detail_source_cache == {}
