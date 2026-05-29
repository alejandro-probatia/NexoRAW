from __future__ import annotations

from ._imports import *  # noqa: F401,F403


class PreviewRenderMixin:
    def _mark_preview_control_interaction(self, *, duration_ms: int = 900, detail: bool = False) -> None:
        until = time.perf_counter() + max(1, int(duration_ms)) / 1000.0
        self._preview_recent_interaction_until = max(
            float(getattr(self, "_preview_recent_interaction_until", 0.0) or 0.0),
            until,
        )
        if bool(detail):
            self._preview_recent_detail_interaction_until = max(
                float(getattr(self, "_preview_recent_detail_interaction_until", 0.0) or 0.0),
                until,
            )

    def _current_adjusted_linear_signature(self) -> str:
        source_key = self._last_loaded_preview_key or str(id(self._original_linear))
        shape: tuple[int, ...] = ()
        if self._original_linear is not None:
            try:
                shape = tuple(int(v) for v in np.asarray(self._original_linear).shape)
            except Exception:
                shape = ()
        detail_kwargs = {
            "denoise_luminance": float(self.slider_noise_luma.value() / 100.0),
            "denoise_color": float(self.slider_noise_color.value() / 100.0),
            "sharpen_amount": float(self.slider_sharpen.value() / 100.0),
            "sharpen_radius": float(self.slider_radius.value() / 10.0),
        }
        ca_red, ca_blue = self._ca_scale_factors()
        detail_kwargs["lateral_ca_red_scale"] = float(ca_red)
        detail_kwargs["lateral_ca_blue_scale"] = float(ca_blue)
        return json.dumps(
            {
                "source": source_key,
                "shape": shape,
                "detail": detail_kwargs,
                "render": self._render_adjustment_kwargs(),
            },
            sort_keys=True,
            default=str,
        )

    def _recent_preview_control_interaction_active(self) -> bool:
        now = time.perf_counter()
        return (
            now < float(getattr(self, "_preview_recent_interaction_until", 0.0) or 0.0)
            or now < float(getattr(self, "_preview_recent_detail_interaction_until", 0.0) or 0.0)
        )

    def _recent_detail_control_interaction_active(self) -> bool:
        return time.perf_counter() < float(getattr(self, "_preview_recent_detail_interaction_until", 0.0) or 0.0)

    def _on_slider_change(self) -> None:
        if (
            int(getattr(self, "_suspend_render_adjustment_autosave", 0) or 0) > 0
            or int(getattr(self, "_suspend_detail_adjustment_autosave", 0) or 0) > 0
        ):
            return
        sender = self.sender()
        render_sliders = (
            getattr(self, "slider_brightness", None),
            getattr(self, "slider_black_point", None),
            getattr(self, "slider_white_point", None),
            getattr(self, "slider_contrast", None),
            getattr(self, "slider_highlights", None),
            getattr(self, "slider_shadows", None),
            getattr(self, "slider_whites", None),
            getattr(self, "slider_blacks", None),
            getattr(self, "slider_midtone", None),
            getattr(self, "slider_vibrance", None),
            getattr(self, "slider_saturation", None),
            getattr(self, "slider_grade_midtones_hue", None),
            getattr(self, "slider_grade_midtones_sat", None),
            getattr(self, "slider_grade_shadows_hue", None),
            getattr(self, "slider_grade_shadows_sat", None),
            getattr(self, "slider_grade_highlights_hue", None),
            getattr(self, "slider_grade_highlights_sat", None),
            getattr(self, "slider_grade_blending", None),
            getattr(self, "slider_grade_balance", None),
            getattr(self, "slider_tone_curve_black", None),
            getattr(self, "slider_tone_curve_white", None),
        )
        detail_sliders = (
            getattr(self, "slider_sharpen", None),
            getattr(self, "slider_radius", None),
            getattr(self, "slider_noise_luma", None),
            getattr(self, "slider_noise_color", None),
            getattr(self, "slider_ca_red", None),
            getattr(self, "slider_ca_blue", None),
        )
        if (
            sender in detail_sliders
            and not bool(getattr(sender, "isSliderDown", lambda: False)())
            and hasattr(self, "_push_edit_history_snapshot")
        ):
            self._push_edit_history_snapshot("detail")
        if self._original_linear is not None:
            if sender in detail_sliders:
                self._preview_last_slider_group = "detail"
                if bool(getattr(sender, "isSliderDown", lambda: False)()):
                    self._mark_preview_control_interaction(duration_ms=900, detail=True)
                else:
                    self._preview_recent_interaction_until = 0.0
                    self._preview_recent_detail_interaction_until = 0.0
            elif sender in render_sliders or sender is None:
                self._preview_last_slider_group = "render"
                self._mark_preview_control_interaction(duration_ms=900)
            self._schedule_preview_refresh()
            self._schedule_exact_histogram_refresh(delay_ms=80, mark_pending=False)
            if sender in detail_sliders:
                self._schedule_post_interaction_exact_preview_refresh(delay_ms=480)
            elif sender in render_sliders or sender is None:
                self._schedule_post_interaction_exact_preview_refresh(delay_ms=260)
        if sender in detail_sliders:
            if hasattr(self, "_set_active_named_adjustment_profile_id"):
                self._set_active_named_adjustment_profile_id("detail", "")
            if hasattr(self, "_refresh_named_adjustment_profile_combo"):
                self._refresh_named_adjustment_profile_combo("detail")
            if hasattr(self, "_schedule_detail_adjustment_sidecar_persist"):
                self._schedule_detail_adjustment_sidecar_persist()
        if hasattr(self, "_schedule_mtf_refresh"):
            self._schedule_mtf_refresh(
                interactive=self._is_preview_interaction_active(),
                require_auto_update=sender not in detail_sliders,
            )

    def _on_slider_release(self) -> None:
        if (
            int(getattr(self, "_suspend_render_adjustment_autosave", 0) or 0) > 0
            or int(getattr(self, "_suspend_detail_adjustment_autosave", 0) or 0) > 0
        ):
            return
        sender = self.sender()
        render_sliders = (
            getattr(self, "slider_brightness", None),
            getattr(self, "slider_black_point", None),
            getattr(self, "slider_white_point", None),
            getattr(self, "slider_contrast", None),
            getattr(self, "slider_highlights", None),
            getattr(self, "slider_shadows", None),
            getattr(self, "slider_whites", None),
            getattr(self, "slider_blacks", None),
            getattr(self, "slider_midtone", None),
            getattr(self, "slider_vibrance", None),
            getattr(self, "slider_saturation", None),
            getattr(self, "slider_grade_midtones_hue", None),
            getattr(self, "slider_grade_midtones_sat", None),
            getattr(self, "slider_grade_shadows_hue", None),
            getattr(self, "slider_grade_shadows_sat", None),
            getattr(self, "slider_grade_highlights_hue", None),
            getattr(self, "slider_grade_highlights_sat", None),
            getattr(self, "slider_grade_blending", None),
            getattr(self, "slider_grade_balance", None),
            getattr(self, "slider_tone_curve_black", None),
            getattr(self, "slider_tone_curve_white", None),
        )
        detail_sliders = (
            getattr(self, "slider_sharpen", None),
            getattr(self, "slider_radius", None),
            getattr(self, "slider_noise_luma", None),
            getattr(self, "slider_noise_color", None),
            getattr(self, "slider_ca_red", None),
            getattr(self, "slider_ca_blue", None),
        )
        if hasattr(self, "_push_edit_history_snapshot"):
            if sender in detail_sliders or str(getattr(self, "_preview_last_slider_group", "") or "") == "detail":
                self._push_edit_history_snapshot("detail")
            elif sender in render_sliders or str(getattr(self, "_preview_last_slider_group", "") or "") == "render":
                self._push_edit_history_snapshot("render")
        if (
            sender in (getattr(self, "slider_tone_curve_black", None), getattr(self, "slider_tone_curve_white", None))
            and hasattr(self, "_on_tone_curve_range_interaction_finished")
        ):
            self._on_tone_curve_range_interaction_finished()
            return
        if self._original_linear is not None:
            last_group = str(getattr(self, "_preview_last_slider_group", "") or "")
            render_release = sender in render_sliders or (sender is None and last_group == "render")
            detail_release = sender in detail_sliders or (sender is None and last_group == "detail")
            if render_release:
                self._mark_preview_control_interaction(duration_ms=250)
                self._schedule_preview_refresh()
                self._schedule_post_interaction_exact_preview_refresh(delay_ms=260)
            elif detail_release:
                self._mark_preview_control_interaction(duration_ms=450, detail=True)
                self._schedule_preview_refresh()
                self._schedule_post_interaction_exact_preview_refresh(delay_ms=480)
            else:
                self._schedule_preview_refresh()
            self._schedule_exact_histogram_refresh(delay_ms=80)
        if (
            sender in render_sliders
            or str(getattr(self, "_preview_last_slider_group", "") or "") == "render"
        ) and hasattr(self, "_schedule_render_adjustment_sidecar_persist"):
            self._schedule_render_adjustment_sidecar_persist(immediate=True)
        if (
            sender in detail_sliders
            or str(getattr(self, "_preview_last_slider_group", "") or "") == "detail"
        ) and hasattr(self, "_schedule_detail_adjustment_sidecar_persist"):
            self._schedule_detail_adjustment_sidecar_persist(immediate=True)
        if hasattr(self, "_schedule_mtf_refresh"):
            self._schedule_mtf_refresh(
                interactive=False,
                require_auto_update=sender not in detail_sliders,
            )

    def _is_direct_preview_interaction_active(self) -> bool:
        slider_names = (
            "slider_sharpen",
            "slider_radius",
            "slider_noise_luma",
            "slider_noise_color",
            "slider_ca_red",
            "slider_ca_blue",
            "slider_brightness",
            "slider_black_point",
            "slider_white_point",
            "slider_contrast",
            "slider_highlights",
            "slider_shadows",
            "slider_whites",
            "slider_blacks",
            "slider_midtone",
            "slider_vibrance",
            "slider_saturation",
            "slider_grade_midtones_hue",
            "slider_grade_midtones_sat",
            "slider_grade_shadows_hue",
            "slider_grade_shadows_sat",
            "slider_grade_highlights_hue",
            "slider_grade_highlights_sat",
            "slider_grade_blending",
            "slider_grade_balance",
            "slider_tone_curve_black",
            "slider_tone_curve_white",
        )
        for name in slider_names:
            slider = getattr(self, name, None)
            if slider is not None and bool(slider.isSliderDown()):
                return True
        editor = getattr(self, "tone_curve_editor", None)
        return bool(editor is not None and editor.is_dragging())

    def _is_preview_interaction_active(self) -> bool:
        return self._is_direct_preview_interaction_active() or self._recent_preview_control_interaction_active()

    def _is_detail_interaction_active(self) -> bool:
        detail_slider_names = (
            "slider_sharpen",
            "slider_radius",
            "slider_noise_luma",
            "slider_noise_color",
            "slider_ca_red",
            "slider_ca_blue",
        )
        for name in detail_slider_names:
            slider = getattr(self, name, None)
            if slider is not None and bool(slider.isSliderDown()):
                return True
        return self._recent_detail_control_interaction_active()

    def _interactive_preview_source(
        self,
        image: np.ndarray,
        *,
        max_side_limit: int = 0,
    ) -> np.ndarray:
        rgb = np.asarray(image, dtype=np.float32)
        if int(max_side_limit) <= 0:
            return rgb
        cache_key = (
            id(image),
            tuple(int(v) for v in rgb.shape),
            str(rgb.dtype),
            int(max_side_limit),
        )
        if (
            getattr(self, "_interactive_source_cache_key", None) == cache_key
            and getattr(self, "_interactive_source_cache_image", None) is not None
        ):
            return self._interactive_source_cache_image
        cache_images = getattr(self, "_interactive_source_cache_images", None)
        if isinstance(cache_images, dict):
            cached = cache_images.get(cache_key)
            if cached is not None:
                self._interactive_source_cache_key = cache_key
                self._interactive_source_cache_image = cached
                return cached
        h, w = int(rgb.shape[0]), int(rgb.shape[1])
        max_side = max(h, w)
        if max_side <= int(max_side_limit):
            return rgb
        scale = float(max_side_limit) / float(max_side)
        nw = max(1, int(round(w * scale)))
        nh = max(1, int(round(h * scale)))
        resized = np.clip(
            cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_AREA),
            0.0,
            1.0,
        ).astype(np.float32)
        self._interactive_source_cache_key = cache_key
        self._interactive_source_cache_image = resized
        if isinstance(cache_images, dict):
            cache_images[cache_key] = resized
            while len(cache_images) > 4:
                cache_images.pop(next(iter(cache_images)))
        return resized

    def _profile_preview_profile_stamp(self, profile_path: Path) -> str:
        try:
            resolved = profile_path.expanduser().resolve()
            st = resolved.stat()
            return f"{resolved}|{st.st_mtime_ns}|{st.st_size}"
        except OSError:
            return str(profile_path)

    def _preview_profile_settings_signature(self) -> str:
        detail_state = self._detail_adjustment_state()
        render_state = self._render_adjustment_state()
        tone_points = render_state.get("tone_curve_points") or []
        tone_sig = ",".join(
            f"{float(x):.4f}:{float(y):.4f}"
            for x, y in normalize_tone_curve_points(
                [
                    (p[0], p[1])
                    for p in tone_points
                    if isinstance(p, (list, tuple)) and len(p) >= 2
                ]
            )
        )
        tone_channel_points = render_state.get("tone_curve_channel_points")
        channel_sig_parts: list[str] = []
        if isinstance(tone_channel_points, dict):
            for channel in ("luminance", "red", "green", "blue"):
                points = tone_channel_points.get(channel) or []
                channel_points = normalize_tone_curve_points(
                    [
                        (p[0], p[1])
                        for p in points
                        if isinstance(p, (list, tuple)) and len(p) >= 2
                    ]
                )
                channel_sig_parts.append(
                    channel
                    + "="
                    + ",".join(f"{float(x):.4f}:{float(y):.4f}" for x, y in channel_points)
                )
        source_key = self._last_loaded_preview_key or str(id(self._original_linear))
        return "|".join(
            [
                source_key,
                f"sh={int(detail_state.get('sharpen', 0))}",
                f"sr={int(detail_state.get('radius', 10))}",
                f"nl={int(detail_state.get('noise_luma', 0))}",
                f"nc={int(detail_state.get('noise_color', 0))}",
                f"cr={int(detail_state.get('ca_red', 0))}",
                f"cb={int(detail_state.get('ca_blue', 0))}",
                f"tk={int(render_state.get('temperature_kelvin', 5003))}",
                f"ti={float(render_state.get('tint', 0.0)):.3f}",
                f"be={float(render_state.get('brightness_ev', 0.0)):.3f}",
                f"bp={float(render_state.get('black_point', 0.0)):.4f}",
                f"wp={float(render_state.get('white_point', 1.0)):.4f}",
                f"ct={float(render_state.get('contrast', 0.0)):.3f}",
                f"hi={float(render_state.get('highlights', 0.0)):.3f}",
                f"shd={float(render_state.get('shadows', 0.0)):.3f}",
                f"wh={float(render_state.get('whites', 0.0)):.3f}",
                f"bl={float(render_state.get('blacks', 0.0)):.3f}",
                f"mt={float(render_state.get('midtone', 1.0)):.3f}",
                f"vib={float(render_state.get('vibrance', 0.0)):.3f}",
                f"sat={float(render_state.get('saturation', 0.0)):.3f}",
                f"gsh={float(render_state.get('grade_shadows_hue', 240.0)):.2f}:{float(render_state.get('grade_shadows_saturation', 0.0)):.3f}",
                f"gmi={float(render_state.get('grade_midtones_hue', 45.0)):.2f}:{float(render_state.get('grade_midtones_saturation', 0.0)):.3f}",
                f"ghi={float(render_state.get('grade_highlights_hue', 50.0)):.2f}:{float(render_state.get('grade_highlights_saturation', 0.0)):.3f}",
                f"gbl={float(render_state.get('grade_blending', 0.5)):.3f}",
                f"gba={float(render_state.get('grade_balance', 0.0)):.3f}",
                f"te={int(bool(render_state.get('tone_curve_enabled', False)))}",
                f"tb={float(render_state.get('tone_curve_black_point', 0.0)):.4f}",
                f"tw={float(render_state.get('tone_curve_white_point', 1.0)):.4f}",
                f"tp={tone_sig}",
                f"tc={render_state.get('tone_curve_channel', 'luminance')}",
                f"tcp={';'.join(channel_sig_parts)}",
            ]
        )

    def _profile_preview_request_key(self, profile_path: Path) -> str:
        max_side_limit = self._profile_preview_max_side_limit()
        return "|".join(
            [
                self._preview_profile_settings_signature(),
                self._profile_preview_profile_stamp(profile_path),
                f"pm={int(max_side_limit)}",
            ]
        )

    def _profile_preview_max_side_limit(self) -> int:
        scale = self._viewer_display_scale()
        if (
            bool(getattr(self, "_viewer_full_detail_requested", False))
            or (scale is not None and float(scale) >= 0.98)
        ):
            return 0
        return int(PREVIEW_PROFILE_APPLY_MAX_SIDE)

    def _final_adjustment_preview_max_side(self) -> int:
        if bool(getattr(self, "_preview_export_parity_requested", False)):
            return 0
        if bool(getattr(self, "_viewer_full_detail_requested", False)):
            return 0
        return int(PREVIEW_FINAL_ADJUSTMENT_MAX_SIDE)

    def _interactive_preview_timeout_ms(self, *, source_linear: np.ndarray, max_side_limit: int) -> int:
        try:
            pixels = int(source_linear.shape[0]) * int(source_linear.shape[1])
        except Exception:
            pixels = 0
        if int(max_side_limit) <= 0 or pixels > 20_000_000:
            return 90_000
        if pixels > 8_000_000:
            return 30_000
        return int(PREVIEW_INTERACTIVE_STUCK_TIMEOUT_MS)

    def _detail_kwargs_have_effect(self, detail_kwargs: dict[str, float]) -> bool:
        return any(
            abs(float(detail_kwargs.get(name, default)) - float(default)) > 1e-6
            for name, default in (
                ("denoise_luminance", 0.0),
                ("denoise_color", 0.0),
                ("sharpen_amount", 0.0),
                ("lateral_ca_red_scale", 1.0),
                ("lateral_ca_blue_scale", 1.0),
            )
        ) or abs(float(detail_kwargs.get("sharpen_radius", 1.0)) - 1.0) > 1e-6

    def _apply_render_adjustments_tiled(
        self,
        source: np.ndarray,
        render_kwargs: dict[str, Any],
        *,
        target_tile_pixels: int = 1_200_000,
    ) -> np.ndarray:
        rgb = np.asarray(source, dtype=np.float32)
        h, w = int(rgb.shape[0]), int(rgb.shape[1])
        if h <= 0 or w <= 0:
            return apply_render_adjustments(rgb, **render_kwargs)
        pixels = h * w
        if pixels <= int(target_tile_pixels):
            return apply_render_adjustments(rgb, **render_kwargs)

        rows = max(32, min(h, int(target_tile_pixels) // max(1, w)))
        out = np.empty_like(rgb, dtype=np.float32)
        for y0 in range(0, h, rows):
            y1 = min(h, y0 + rows)
            out[y0:y1] = apply_render_adjustments(rgb[y0:y1], **render_kwargs)
            time.sleep(0)
        return out

    def _row_tile_slices(self, image: np.ndarray, *, target_tile_pixels: int = 1_200_000):
        h, w = int(image.shape[0]), int(image.shape[1])
        if h <= 0 or w <= 0:
            return
        rows = max(32, min(h, int(target_tile_pixels) // max(1, w)))
        for y0 in range(0, h, rows):
            yield y0, min(h, y0 + rows)

    def _standard_profile_to_srgb_display_tiled(self, image_rgb: np.ndarray, output_space: str) -> np.ndarray:
        rgb = np.asarray(image_rgb, dtype=np.float32)
        if int(rgb.shape[0]) * int(rgb.shape[1]) <= 1_200_000:
            return standard_profile_to_srgb_display(rgb, output_space)
        out = np.empty_like(rgb, dtype=np.float32)
        for y0, y1 in self._row_tile_slices(rgb):
            out[y0:y1] = standard_profile_to_srgb_display(rgb[y0:y1], output_space)
            time.sleep(0)
        return out

    def _srgb_to_display_u8_tiled(self, image_srgb: np.ndarray, monitor_profile: Path | None) -> np.ndarray:
        srgb = np.asarray(image_srgb, dtype=np.float32)
        if int(srgb.shape[0]) * int(srgb.shape[1]) <= 1_200_000:
            return srgb_to_display_u8(srgb, monitor_profile)
        out = np.empty(srgb.shape[:2] + (3,), dtype=np.uint8)
        for y0, y1 in self._row_tile_slices(srgb):
            out[y0:y1] = srgb_to_display_u8(srgb[y0:y1], monitor_profile)
            time.sleep(0)
        return out

    def _profiled_float_to_display_u8_tiled(
        self,
        image_rgb: np.ndarray,
        source_profile: Path,
        monitor_profile: Path | None,
    ) -> np.ndarray:
        rgb = np.asarray(image_rgb, dtype=np.float32)
        if int(rgb.shape[0]) * int(rgb.shape[1]) <= 1_200_000:
            return profiled_float_to_display_u8(rgb, source_profile, monitor_profile)
        out = np.empty(rgb.shape[:2] + (3,), dtype=np.uint8)
        for y0, y1 in self._row_tile_slices(rgb):
            out[y0:y1] = profiled_float_to_display_u8(rgb[y0:y1], source_profile, monitor_profile)
            time.sleep(0)
        return out

    def _interactive_preview_worker_count(self, pixels: int) -> int:
        px = max(0, int(pixels))
        if px < int(PREVIEW_INTERACTIVE_PARALLEL_MIN_PIXELS):
            return 1
        override = self._interactive_preview_worker_override()
        if override is not None:
            return override
        candidates = self._interactive_preview_worker_candidates(px)
        if not candidates:
            return 1
        bucket = self._interactive_worker_perf_bucket(px)
        perf = getattr(self, "_interactive_worker_perf", {}).get(bucket, {})
        for candidate in candidates[:2]:
            if candidate not in perf:
                return int(candidate)
        return int(min(candidates, key=lambda item: float(perf.get(item, float("inf")))))

    def _interactive_preview_worker_override(self) -> int | None:
        settings_value = None
        if hasattr(self, "_settings"):
            try:
                settings_value = self._settings.value("performance/interactive_render_workers", None)
            except Exception:
                settings_value = None
        raw = os.environ.get("PROBRAW_INTERACTIVE_RENDER_WORKERS", "").strip()
        for candidate in (raw, settings_value):
            if candidate is None or str(candidate).strip() == "":
                continue
            try:
                configured = int(candidate)
            except Exception:
                configured = 0
            if configured > 0:
                return max(1, min(16, configured))
        return None

    def _interactive_preview_worker_candidates(self, pixels: int) -> list[int]:
        cap = self._interactive_preview_worker_hardware_cap(int(pixels))
        if cap <= 1:
            return [1]
        px = max(0, int(pixels))
        if px >= 2_800_000:
            raw = [8, 6, 10, 4, 12]
        elif px >= 800_000:
            raw = [4, 6, 8, 2, 10]
        elif px >= 250_000:
            raw = [4, 6, 2, 8]
        else:
            raw = [2, 4]
        return [
            value
            for value in dict.fromkeys(max(1, int(v)) for v in raw)
            if 1 < value <= int(cap)
        ]

    def _interactive_preview_worker_hardware_cap(self, pixels: int) -> int:
        px = max(0, int(pixels))
        if px < int(PREVIEW_INTERACTIVE_PARALLEL_MIN_PIXELS):
            return 1
        cpu_count = os.cpu_count() or 1
        if cpu_count <= 2:
            return 1
        total = self._system_total_memory_bytes() if hasattr(self, "_system_total_memory_bytes") else None
        available = self._system_available_memory_bytes() if hasattr(self, "_system_available_memory_bytes") else None
        gib = 1024 * 1024 * 1024
        if available is not None and int(available) < 2 * gib:
            memory_cap = 2
        elif total is not None and int(total) >= 96 * gib:
            memory_cap = 12
        elif total is not None and int(total) >= 48 * gib:
            memory_cap = 10
        elif total is not None and int(total) >= 24 * gib:
            memory_cap = 8
        else:
            memory_cap = 6
        if px >= 1_200_000:
            pixel_cap = 12
        elif px >= 800_000:
            pixel_cap = 10
        elif px >= 500_000:
            pixel_cap = 8
        elif px >= 250_000:
            pixel_cap = 6
        else:
            pixel_cap = 4
        return max(1, min(int(cpu_count) - 1, int(memory_cap), int(pixel_cap), 16))

    @staticmethod
    def _interactive_worker_perf_bucket(pixels: int) -> int:
        px = max(0, int(pixels))
        if px < 250_000:
            return 250_000
        if px < 500_000:
            return 500_000
        if px < 800_000:
            return 800_000
        if px < 1_200_000:
            return 1_200_000
        if px < 2_500_000:
            return 2_500_000
        if px < 5_000_000:
            return 5_000_000
        return 8_000_000

    def _record_interactive_worker_performance(self, pixels: int, workers: int, elapsed_ms: float) -> None:
        worker_count = int(workers)
        elapsed = float(elapsed_ms)
        if worker_count <= 1 or not np.isfinite(elapsed) or elapsed <= 0.0:
            return
        bucket = self._interactive_worker_perf_bucket(int(pixels))
        perf = getattr(self, "_interactive_worker_perf", None)
        if not isinstance(perf, dict):
            perf = {}
            self._interactive_worker_perf = perf
        bucket_perf = perf.setdefault(bucket, {})
        previous = bucket_perf.get(worker_count)
        bucket_perf[worker_count] = elapsed if previous is None else float(previous) * 0.72 + elapsed * 0.28

    def _interactive_parallel_row_ranges(self, height: int, workers: int) -> list[tuple[int, int]]:
        h = max(0, int(height))
        count = max(1, int(workers))
        if h <= 0:
            return []
        rows = max(32, int(np.ceil(float(h) / float(count))))
        return [(y0, min(h, y0 + rows)) for y0 in range(0, h, rows)]

    def _render_interactive_viewport_parallel(
        self,
        source: np.ndarray,
        render_kwargs: dict[str, Any],
        *,
        output_space: str,
        source_profile: Path | None,
        monitor_profile: Path | None,
        include_srgb_patch: bool,
        workers: int,
    ) -> tuple[np.ndarray | None, np.ndarray]:
        rgb = np.asarray(source, dtype=np.float32)
        h, w = int(rgb.shape[0]), int(rgb.shape[1])
        row_ranges = self._interactive_parallel_row_ranges(h, workers)
        if len(row_ranges) <= 1:
            if source_profile is not None:
                rgb_u8 = render_adjustments_affine_u8(rgb, **render_kwargs)
                if rgb_u8 is not None:
                    display_u8 = profiled_u8_to_display_u8(rgb_u8, source_profile, monitor_profile)
                    if include_srgb_patch:
                        srgb_u8 = profiled_u8_to_display_u8(rgb_u8, source_profile, None)
                        return np.asarray(srgb_u8, dtype=np.uint8), np.asarray(display_u8, dtype=np.uint8)
                    return None, np.asarray(display_u8, dtype=np.uint8)
                adjusted = apply_render_adjustments(rgb, **render_kwargs)
                adjusted_u8 = rgb_float_to_u8(adjusted)
                display_u8 = profiled_u8_to_display_u8(adjusted_u8, source_profile, monitor_profile)
                if include_srgb_patch:
                    srgb_u8 = profiled_u8_to_display_u8(adjusted_u8, source_profile, None)
                    return np.asarray(srgb_u8, dtype=np.uint8), np.asarray(display_u8, dtype=np.uint8)
                return None, np.asarray(display_u8, dtype=np.uint8)
            adjusted = apply_render_adjustments(rgb, **render_kwargs)
            srgb_u8 = standard_profile_to_srgb_u8_display(adjusted, output_space)
            display_u8 = srgb_u8_to_display_u8(srgb_u8, monitor_profile)
            return (
                np.asarray(srgb_u8, dtype=np.uint8) if include_srgb_patch else None,
                np.asarray(display_u8, dtype=np.uint8),
            )

        display_u8 = np.empty((h, w, 3), dtype=np.uint8)
        if source_profile is not None:
            srgb_u8 = np.empty((h, w, 3), dtype=np.uint8) if include_srgb_patch else None
            # Build/cache the LCMS transforms and, on workstation-class memory,
            # the exact 8-bit dense ICC LUT before parallel work. The LUT is
            # derived from LCMS for every possible RGB triplet, so it accelerates
            # repeated viewport renders without changing the color result.
            profiled_float_to_display_u8(rgb[:1, :1], source_profile, monitor_profile)
            if include_srgb_patch:
                profiled_float_to_display_u8(rgb[:1, :1], source_profile, None)
            if h * w >= int(PREVIEW_INTERACTIVE_PARALLEL_MIN_PIXELS):
                prewarm_profiled_display_lut(source_profile, monitor_profile)
                if include_srgb_patch:
                    prewarm_profiled_display_lut(source_profile, None)

            def profile_job(row_range: tuple[int, int]):
                y0, y1 = row_range
                source_rows = rgb[y0:y1]
                rgb_u8 = render_adjustments_affine_u8(source_rows, **render_kwargs)
                if rgb_u8 is not None:
                    display = profiled_u8_to_display_u8(rgb_u8, source_profile, monitor_profile)
                    srgb = profiled_u8_to_display_u8(rgb_u8, source_profile, None) if include_srgb_patch else None
                    return y0, y1, display, srgb
                adjusted = apply_render_adjustments(source_rows, **render_kwargs)
                adjusted_u8 = rgb_float_to_u8(adjusted)
                display = profiled_u8_to_display_u8(adjusted_u8, source_profile, monitor_profile)
                srgb = profiled_u8_to_display_u8(adjusted_u8, source_profile, None) if include_srgb_patch else None
                return y0, y1, display, srgb

            with ThreadPoolExecutor(max_workers=max(1, int(workers))) as executor:
                for y0, y1, display, srgb in executor.map(profile_job, row_ranges):
                    display_u8[y0:y1] = display
                    if srgb_u8 is not None and srgb is not None:
                        srgb_u8[y0:y1] = srgb
            if srgb_u8 is None:
                return None, display_u8
            return srgb_u8, display_u8

        result_srgb = np.empty((h, w, 3), dtype=np.uint8) if include_srgb_patch else None
        if monitor_profile is not None:
            srgb_to_display_u8(np.zeros((1, 1, 3), dtype=np.float32), monitor_profile)

        def standard_job(row_range: tuple[int, int]):
            y0, y1 = row_range
            adjusted = apply_render_adjustments(rgb[y0:y1], **render_kwargs)
            srgb = standard_profile_to_srgb_u8_display(adjusted, output_space)
            display = srgb_u8_to_display_u8(srgb, monitor_profile)
            return y0, y1, display, srgb

        with ThreadPoolExecutor(max_workers=max(1, int(workers))) as executor:
            for y0, y1, display, srgb in executor.map(standard_job, row_ranges):
                display_u8[y0:y1] = display
                if result_srgb is not None:
                    result_srgb[y0:y1] = srgb
        return result_srgb, display_u8

    def _histogram_u8_from_colorimetric_preview_patch(self, patch: np.ndarray | None) -> np.ndarray | None:
        if patch is None:
            return None
        array = np.asarray(patch)
        if array.ndim != 3 or array.shape[2] < 3:
            return None
        if array.dtype == np.uint8:
            return np.ascontiguousarray(array[..., :3])
        return np.asarray(srgb_to_display_u8(array[..., :3], None), dtype=np.uint8)

    @staticmethod
    def _preview_candidate_to_float(candidate: np.ndarray | None) -> np.ndarray | None:
        if candidate is None:
            return None
        arr = np.asarray(candidate)
        if arr.dtype == np.uint8:
            return arr.astype(np.float32) / np.float32(255.0)
        return np.asarray(arr, dtype=np.float32)

    def _viewer_histogram_full_source(self, image: np.ndarray) -> np.ndarray:
        rgb = np.asarray(image, dtype=np.float32)
        if rgb.ndim != 3 or rgb.shape[2] < 3:
            return np.ascontiguousarray(rgb)
        return np.ascontiguousarray(rgb[..., :3])

    def _render_viewer_histogram_u8(
        self,
        source_linear: np.ndarray,
        detail_kwargs: dict[str, float],
        render_kwargs: dict[str, Any],
        *,
        apply_detail: bool,
        output_space: str,
        source_profile: Path | None,
    ) -> np.ndarray | None:
        source = self._viewer_histogram_full_source(source_linear)
        if source.ndim != 3 or source.shape[2] < 3:
            return None
        if bool(apply_detail):
            source = apply_adjustments(
                source,
                denoise_luminance=float(detail_kwargs.get("denoise_luminance", 0.0)),
                denoise_color=float(detail_kwargs.get("denoise_color", 0.0)),
                sharpen_amount=float(detail_kwargs.get("sharpen_amount", 0.0)),
                sharpen_radius=float(detail_kwargs.get("sharpen_radius", 1.0)),
                lateral_ca_red_scale=float(detail_kwargs.get("lateral_ca_red_scale", 1.0)),
                lateral_ca_blue_scale=float(detail_kwargs.get("lateral_ca_blue_scale", 1.0)),
            )
        adjusted = apply_render_adjustments(source, **render_kwargs)
        if source_profile is not None:
            adjusted_u8 = rgb_float_to_u8(adjusted)
            return np.asarray(profiled_u8_to_display_u8(adjusted_u8, source_profile, None), dtype=np.uint8)
        return np.asarray(standard_profile_to_srgb_u8_display(adjusted, output_space), dtype=np.uint8)

    def _loaded_preview_has_real_pixels_for_viewport(self) -> bool:
        selected = getattr(self, "_selected_file", None)
        if selected is None:
            return True
        try:
            is_raw = Path(selected).suffix.lower() in RAW_EXTENSIONS
        except Exception:
            is_raw = False
        loaded_request = getattr(self, "_loaded_preview_max_side_request", None)
        loaded_fast = bool(getattr(self, "_loaded_preview_fast_raw", False))
        if is_raw:
            return loaded_request == 0 and not loaded_fast
        if loaded_request is None:
            return True
        return int(loaded_request) <= 0

    def _real_pixel_view_requested(self) -> bool:
        if bool(getattr(self, "_viewer_full_detail_requested", False)):
            return True
        panel = getattr(self, "image_result_single", None)
        if panel is None or not hasattr(panel, "current_display_scale"):
            return False
        scale = panel.current_display_scale()
        return bool(scale is not None and float(scale) >= 0.98)

    def _interactive_viewport_rect(self, *, compare_enabled: bool, apply_detail: bool) -> tuple[int, int, int, int] | None:
        del apply_detail
        if compare_enabled:
            return None
        if self._original_linear is None:
            return None
        panel = getattr(self, "image_result_single", None)
        if panel is None or not hasattr(panel, "visible_image_rect"):
            return None
        rect = panel.visible_image_rect(margin=PREVIEW_INTERACTIVE_VIEWPORT_MARGIN_PX)
        if rect is None:
            return None
        x, y, w, h = (int(v) for v in rect)
        if w <= 0 or h <= 0:
            return None
        current_display = getattr(self, "_current_result_display_u8", None)
        if current_display is None:
            return None
        current_display = np.asarray(current_display)
        if current_display.ndim != 3:
            return None
        source_h, source_w = int(self._original_linear.shape[0]), int(self._original_linear.shape[1])
        if current_display.shape[0] != source_h or current_display.shape[1] != source_w:
            return None
        if x >= source_w or y >= source_h:
            return None
        w = min(w, source_w - x)
        h = min(h, source_h - y)
        if w * h >= source_w * source_h:
            return None
        return x, y, w, h

    def _tone_curve_histogram_render_kwargs(self, render_kwargs: dict[str, Any]) -> dict[str, Any]:
        return dict(render_kwargs)

    def _tone_curve_points_signature(self, points: Any) -> str:
        if not isinstance(points, (list, tuple)):
            return ""
        normalized = normalize_tone_curve_points(
            [
                (point[0], point[1])
                for point in points
                if isinstance(point, (list, tuple)) and len(point) >= 2
            ]
        )
        return ",".join(f"{float(x):.4f}:{float(y):.4f}" for x, y in normalized)

    def _tone_curve_channel_points_signature(self, channel_points: Any) -> str:
        if not isinstance(channel_points, dict):
            return ""
        parts: list[str] = []
        for channel in ("luminance", "red", "green", "blue"):
            parts.append(f"{channel}={self._tone_curve_points_signature(channel_points.get(channel))}")
        return ";".join(parts)

    def _tone_curve_histogram_signature(
        self,
        source_key: str,
        render_kwargs: dict[str, Any],
        *,
        max_side_limit: int,
    ) -> str:
        return "|".join(
            [
                str(source_key),
                f"source_max_side={int(max_side_limit)}",
                f"channel={self._tone_curve_channel_key()}",
                f"tk={float(render_kwargs.get('temperature_kelvin', 5003.0)):.3f}",
                f"tint={float(render_kwargs.get('tint', 0.0)):.3f}",
                f"bright={float(render_kwargs.get('brightness_ev', 0.0)):.4f}",
                f"black={float(render_kwargs.get('black_point', 0.0)):.4f}",
                f"white={float(render_kwargs.get('white_point', 1.0)):.4f}",
                f"contrast={float(render_kwargs.get('contrast', 0.0)):.4f}",
                f"highlights={float(render_kwargs.get('highlights', 0.0)):.4f}",
                f"shadows={float(render_kwargs.get('shadows', 0.0)):.4f}",
                f"whites={float(render_kwargs.get('whites', 0.0)):.4f}",
                f"blacks={float(render_kwargs.get('blacks', 0.0)):.4f}",
                f"midtone={float(render_kwargs.get('midtone', 1.0)):.4f}",
                f"vibrance={float(render_kwargs.get('vibrance', 0.0)):.4f}",
                f"saturation={float(render_kwargs.get('saturation', 0.0)):.4f}",
                f"grade_shadows={float(render_kwargs.get('grade_shadows_hue', 240.0)):.2f}:{float(render_kwargs.get('grade_shadows_saturation', 0.0)):.4f}",
                f"grade_midtones={float(render_kwargs.get('grade_midtones_hue', 45.0)):.2f}:{float(render_kwargs.get('grade_midtones_saturation', 0.0)):.4f}",
                f"grade_highlights={float(render_kwargs.get('grade_highlights_hue', 50.0)):.2f}:{float(render_kwargs.get('grade_highlights_saturation', 0.0)):.4f}",
                f"grade_blending={float(render_kwargs.get('grade_blending', 0.5)):.4f}",
                f"grade_balance={float(render_kwargs.get('grade_balance', 0.0)):.4f}",
                f"curve_black={float(render_kwargs.get('tone_curve_black_point', 0.0)):.4f}",
                f"curve_white={float(render_kwargs.get('tone_curve_white_point', 1.0)):.4f}",
                f"curve={self._tone_curve_points_signature(render_kwargs.get('tone_curve_points'))}",
                f"curve_channels={self._tone_curve_channel_points_signature(render_kwargs.get('tone_curve_channel_points'))}",
                "curve_stage=output",
            ]
        )

    def _update_tone_curve_histogram(
        self,
        source: np.ndarray,
        render_kwargs: dict[str, Any],
        *,
        source_key: str,
        max_side_limit: int,
        async_update: bool = False,
        force: bool = False,
    ) -> None:
        if not hasattr(self, "tone_curve_editor"):
            return
        key = self._tone_curve_histogram_signature(
            source_key,
            render_kwargs,
            max_side_limit=int(max_side_limit),
        )
        if not force and self._tone_curve_histogram_key == key:
            return
        if bool(async_update):
            self._queue_tone_curve_histogram_request(
                (
                    key,
                    np.asarray(source, dtype=np.float32),
                    dict(render_kwargs),
                    self._tone_curve_channel_key(),
                )
            )
            return
        try:
            histogram_source = apply_render_adjustments(
                np.asarray(source, dtype=np.float32),
                **self._tone_curve_histogram_render_kwargs(render_kwargs),
            )
            self.tone_curve_editor.set_histogram_from_image(
                histogram_source,
                channel=self._tone_curve_channel_key(),
            )
            self._tone_curve_histogram_key = key
        except Exception as exc:
            self._tone_curve_histogram_key = None
            self._log_preview(f"Aviso: no se pudo actualizar histograma de curva: {exc}")

    def _queue_tone_curve_histogram_request(
        self,
        request: tuple[str, np.ndarray, dict[str, Any], str],
    ) -> None:
        request_key = request[0]
        self._tone_curve_histogram_expected_key = request_key
        if bool(getattr(self, "_tone_curve_histogram_task_active", False)):
            self._tone_curve_histogram_pending_request = request
            return
        self._tone_curve_histogram_pending_request = None
        self._start_tone_curve_histogram_task(request)

    def _start_tone_curve_histogram_task(
        self,
        request: tuple[str, np.ndarray, dict[str, Any], str],
    ) -> None:
        request_key, source, render_kwargs, channel = request
        self._tone_curve_histogram_task_active = True

        def task():
            histogram_source = apply_render_adjustments(
                np.asarray(source, dtype=np.float32),
                **self._tone_curve_histogram_render_kwargs(render_kwargs),
            )
            return request_key, histogram_source, channel

        thread = TaskThread(task)
        self._threads.append(thread)

        def cleanup() -> None:
            if thread in self._threads:
                self._threads.remove(thread)
            thread.deleteLater()
            pending = getattr(self, "_tone_curve_histogram_pending_request", None)
            self._tone_curve_histogram_pending_request = None
            if pending is not None:
                self._start_tone_curve_histogram_task(pending)
                return
            self._tone_curve_histogram_task_active = False

        def ok(payload) -> None:
            try:
                key, histogram_source, payload_channel = payload
                if key != getattr(self, "_tone_curve_histogram_expected_key", None):
                    return
                if not hasattr(self, "tone_curve_editor"):
                    return
                self.tone_curve_editor.set_histogram_from_image(
                    histogram_source,
                    channel=str(payload_channel or self._tone_curve_channel_key()),
                )
                self._tone_curve_histogram_key = key
            finally:
                cleanup()

        def fail(trace: str) -> None:
            try:
                self._tone_curve_histogram_key = None
                line = trace.strip().splitlines()[-1] if trace.strip() else "error desconocido"
                self._log_preview(f"Aviso: no se pudo actualizar histograma de curva: {line}")
            finally:
                cleanup()

        thread.succeeded.connect(ok)
        thread.failed.connect(fail)
        thread.start()

    def _tone_curve_histogram_enabled(self) -> bool:
        return bool(hasattr(self, "tone_curve_editor"))

    def _tone_curve_histogram_interaction_active(self) -> bool:
        if not self._tone_curve_histogram_enabled():
            return False
        editor = getattr(self, "tone_curve_editor", None)
        if editor is not None and bool(editor.is_dragging()):
            return True
        for name in ("slider_tone_curve_black", "slider_tone_curve_white"):
            slider = getattr(self, name, None)
            if slider is not None and bool(slider.isSliderDown()):
                return True
        return False

    def _update_tone_curve_histogram_for_current_controls(
        self,
        *,
        max_side_limit: int = 0,
        async_update: bool = False,
        force: bool = False,
    ) -> None:
        if self._original_linear is None:
            return
        if not force and not self._tone_curve_histogram_enabled():
            return
        source_key = self._last_loaded_preview_key or str(id(self._original_linear))
        source = self._interactive_preview_source(
            self._original_linear,
            max_side_limit=int(max_side_limit),
        )
        self._update_tone_curve_histogram(
            source,
            self._render_adjustment_kwargs(),
            source_key=source_key,
            max_side_limit=int(max_side_limit),
            async_update=bool(async_update),
            force=force,
        )

    def _update_tone_curve_histogram_from_preview(self, preview_srgb: np.ndarray) -> None:
        if not self._tone_curve_histogram_enabled():
            return
        try:
            self.tone_curve_editor.set_histogram_from_image(
                preview_srgb,
                channel=self._tone_curve_channel_key(),
            )
            self._tone_curve_histogram_key = self._last_loaded_preview_key or str(id(self._original_linear))
        except Exception as exc:
            self._tone_curve_histogram_key = None
            self._log_preview(f"Aviso: no se pudo actualizar histograma de curva: {exc}")

    def _cached_profile_preview_image(self, key: str) -> np.ndarray | None:
        image = self._profile_preview_cache.get(key)
        if image is None:
            return None
        self._profile_preview_cache_order = [k for k in self._profile_preview_cache_order if k != key]
        self._profile_preview_cache_order.append(key)
        return image

    def _cache_profile_preview_image(self, key: str, image: np.ndarray) -> None:
        if key in self._profile_preview_cache:
            self._profile_preview_cache.pop(key, None)
            self._profile_preview_cache_order = [k for k in self._profile_preview_cache_order if k != key]
        self._profile_preview_cache[key] = np.asarray(image, dtype=np.float32).copy()
        self._profile_preview_cache_order.append(key)
        while len(self._profile_preview_cache_order) > PREVIEW_PROFILE_CACHE_MAX_ENTRIES:
            old = self._profile_preview_cache_order.pop(0)
            self._profile_preview_cache.pop(old, None)

    def _profile_preview_source_for_async(
        self,
        image: np.ndarray,
        *,
        max_side_limit: int,
    ) -> tuple[np.ndarray, bool]:
        rgb = np.asarray(image, dtype=np.float32)
        if int(max_side_limit) <= 0:
            return rgb, False
        h, w = int(rgb.shape[0]), int(rgb.shape[1])
        max_side = max(h, w)
        if max_side <= int(max_side_limit):
            return rgb, False
        scale = float(max_side_limit) / float(max_side)
        nw = max(1, int(round(w * scale)))
        nh = max(1, int(round(h * scale)))
        resized = cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_AREA)
        return np.clip(resized, 0.0, 1.0).astype(np.float32), True

    def _queue_profile_preview_request(
        self,
        request_key: str,
        profile_path: Path,
        image_linear: np.ndarray,
        target_shape: tuple[int, int],
    ) -> None:
        image_copy = np.asarray(image_linear, dtype=np.float32).copy()
        if self._profile_preview_task_active:
            if self._profile_preview_inflight_key == request_key:
                return
            self._profile_preview_pending_request = (
                request_key,
                profile_path,
                image_copy,
                target_shape,
            )
            return
        self._start_profile_preview_task(
            (
                request_key,
                profile_path,
                image_copy,
                target_shape,
            )
        )

    def _start_profile_preview_task(
        self,
        request: tuple[str, Path, np.ndarray, tuple[int, int]],
    ) -> None:
        request_key, profile_path, image_linear, target_shape = request
        max_side_limit = self._profile_preview_max_side_limit()

        def task():
            source, downscaled = self._profile_preview_source_for_async(
                image_linear,
                max_side_limit=max_side_limit,
            )
            candidate = apply_profile_preview(source, profile_path)
            if downscaled:
                target_h, target_w = target_shape
                candidate = cv2.resize(
                    np.asarray(candidate, dtype=np.float32),
                    (max(1, int(target_w)), max(1, int(target_h))),
                    interpolation=cv2.INTER_LINEAR,
                )
            return request_key, np.asarray(candidate, dtype=np.float32)

        thread = TaskThread(task)
        self._profile_preview_task_active = True
        self._profile_preview_inflight_key = request_key
        self._threads.append(thread)

        def cleanup() -> None:
            self._profile_preview_task_active = False
            self._profile_preview_inflight_key = None
            if thread in self._threads:
                self._threads.remove(thread)
            thread.deleteLater()
            pending = self._profile_preview_pending_request
            self._profile_preview_pending_request = None
            if pending is not None:
                self._start_profile_preview_task(pending)

        def ok(payload) -> None:
            try:
                key, candidate = payload
                if self._looks_broken_profile_preview(candidate):
                    self._log_preview(
                        "Aviso: preview del perfil ICC parece no fiable "
                        "(dominante/clipping extremo). Se muestra vista sin perfil."
                    )
                    return
                self._cache_profile_preview_image(key, candidate)
                if key != self._profile_preview_expected_key:
                    return
                self._preview_srgb = np.asarray(candidate, dtype=np.float32)
                display_u8 = self._display_u8_for_screen(self._preview_srgb, bypass_profile=False)
                self._set_result_display_u8(display_u8, compare_enabled=bool(self.chk_compare.isChecked()))
            finally:
                cleanup()

        def fail(trace: str) -> None:
            try:
                key = f"{request_key}|{trace.strip().splitlines()[-1] if trace.strip() else 'error'}"
                if self._profile_preview_error_key != key:
                    self._profile_preview_error_key = key
                    self._log_preview(
                        f"Aviso: no se pudo aplicar preview ICC con LittleCMS: "
                        f"{trace.strip().splitlines()[-1] if trace.strip() else 'error'}"
                    )
            finally:
                cleanup()

        thread.succeeded.connect(ok)
        thread.failed.connect(fail)
        thread.start()

    def _source_profile_for_preview_recipe(self, recipe: Recipe) -> Path:
        profile_path = self._active_session_icc_for_settings()
        if profile_path is not None:
            return profile_path
        if not is_generic_output_space(recipe.output_space):
            raise RuntimeError(
                "La preview no puede continuar sin perfil ICC de entrada. "
                f"Receta no gestionada: output_space={recipe.output_space!r}."
            )
        try:
            return ensure_generic_output_profile(
                recipe.output_space,
                directory=self._session_generic_profile_dir(),
            )
        except Exception as exc:
            key = f"generic-preview-profile|{recipe.output_space}|{exc}"
            if self._profile_preview_error_key != key:
                self._profile_preview_error_key = key
                self._log_preview(f"Aviso: perfil ICC estandar no disponible para vista previa directa: {exc}")
            raise RuntimeError(
                f"No se puede visualizar {recipe.output_space} con garantia colorimetrica: "
                "falta el perfil ICC estandar. Instala/configura el ICC correspondiente."
            ) from exc

    def _color_managed_preview_recipe(self, recipe: Recipe) -> Recipe:
        input_profile_path = self._active_session_icc_for_settings()
        if hasattr(self, "_visible_export_recipe_for_color_management"):
            managed = self._visible_export_recipe_for_color_management(
                recipe,
                input_profile_path=input_profile_path,
            )
        else:
            managed = Recipe(**asdict(recipe))
            if input_profile_path is None and not is_generic_output_space(managed.output_space):
                profile = generic_output_profile("prophoto_rgb")
                managed.output_space = profile.key
                managed.output_linear = False
                managed.tone_curve = f"gamma:{profile.gamma:.3g}"
                managed.profiling_mode = False
        # Hard invariant: from here on the preview has a real source ICC
        # (session-specific or generic). Unprofiled display is a color bug.
        self._source_profile_for_preview_recipe(managed)
        return managed

    def _queue_interactive_preview_request(
        self,
        request: tuple[
            str,
            str | None,
            np.ndarray,
            dict[str, float],
            dict[str, Any],
            bool,
            bool,
            int,
            bool,
            bool,
            str,
            Path | None,
            Path | None,
            tuple[int, int, int, int] | None,
            bool,
            bool,
        ],
    ) -> None:
        (
            request_key,
            _source_key,
            _source_linear,
            _detail_kwargs,
            _render_kwargs,
            _compare_enabled,
            _bypass,
            _max_side_limit,
            _apply_detail,
            _include_analysis,
            _output_space,
            _source_profile,
            _monitor_profile,
            viewport_rect,
            _include_histogram,
            _include_colorimetric_patch,
        ) = request
        self._interactive_preview_expected_key = request_key
        if self._interactive_preview_task_active:
            if self._interactive_preview_inflight_key == request_key:
                return
            inflight_viewport_rect = getattr(self, "_interactive_preview_inflight_viewport_rect", None)
            inflight_include_analysis = bool(getattr(self, "_interactive_preview_inflight_include_analysis", False))
            if viewport_rect is not None and (inflight_viewport_rect is None or inflight_include_analysis):
                self._preempt_interactive_preview_task(request)
                return
            self._interactive_preview_pending_request = request
            return
        self._interactive_preview_pending_request = None
        self._start_interactive_preview_task(request)

    def _preempt_interactive_preview_task(
        self,
        request: tuple[
            str,
            str | None,
            np.ndarray,
            dict[str, float],
            dict[str, Any],
            bool,
            bool,
            int,
            bool,
            bool,
            str,
            Path | None,
            Path | None,
            tuple[int, int, int, int] | None,
            bool,
            bool,
        ],
    ) -> None:
        self._interactive_preview_task_token = int(getattr(self, "_interactive_preview_task_token", 0)) + 1
        self._interactive_preview_task_active = False
        self._interactive_preview_inflight_key = None
        self._interactive_preview_inflight_viewport_rect = None
        self._interactive_preview_inflight_include_analysis = False
        self._interactive_preview_pending_request = None
        self._start_interactive_preview_task(request)

    def _start_interactive_preview_task(
        self,
        request: tuple[
            str,
            str | None,
            np.ndarray,
            dict[str, float],
            dict[str, Any],
            bool,
            bool,
            int,
            bool,
            bool,
            str,
            Path | None,
            Path | None,
            tuple[int, int, int, int] | None,
            bool,
            bool,
        ],
    ) -> None:
        (
            request_key,
            source_key,
            source_linear,
            detail_kwargs,
            render_kwargs,
            compare_enabled,
            bypass_display_profile,
            max_side_limit,
            apply_detail,
            include_analysis,
            output_space,
            source_profile,
            monitor_profile,
            viewport_rect,
            include_histogram,
            include_colorimetric_patch,
        ) = request
        self._interactive_preview_task_token = int(getattr(self, "_interactive_preview_task_token", 0)) + 1
        task_token = int(self._interactive_preview_task_token)

        def task():
            warnings: list[str] = []
            histogram_u8: np.ndarray | None = None

            def srgb_display_u8(image_srgb: np.ndarray) -> np.ndarray:
                try:
                    if render_tiled:
                        return self._srgb_to_display_u8_tiled(image_srgb, monitor_profile)
                    return srgb_to_display_u8(image_srgb, monitor_profile)
                except Exception as exc:
                    raise RuntimeError(f"No se pudo convertir la vista previa sRGB al ICC de monitor: {exc}") from exc

            source = self._interactive_preview_source(
                np.asarray(source_linear, dtype=np.float32),
                max_side_limit=int(max_side_limit),
            )
            full_histogram_source = source if int(max_side_limit) > 0 else np.asarray(source_linear, dtype=np.float32)
            if viewport_rect is not None:
                vx, vy, vw, vh = (int(v) for v in viewport_rect)
                source = source[vy : vy + vh, vx : vx + vw]
            render_tiled = (
                int(max_side_limit) <= 0
                and int(source.shape[0]) * int(source.shape[1]) > 4_000_000
                and (not bool(apply_detail) or not self._detail_kwargs_have_effect(detail_kwargs))
            )
            viewport_workers = (
                self._interactive_preview_worker_count(int(source.shape[0]) * int(source.shape[1]))
                if viewport_rect is not None and not bool(apply_detail)
                else 1
            )
            if viewport_workers > 1:
                source_pixels = int(source.shape[0]) * int(source.shape[1])
                work_started = time.perf_counter()
                result_srgb, display_u8 = self._render_interactive_viewport_parallel(
                    source,
                    render_kwargs,
                    output_space=output_space,
                    source_profile=source_profile,
                    monitor_profile=monitor_profile,
                    include_srgb_patch=bool(include_colorimetric_patch),
                    workers=viewport_workers,
                )
                worker_perf = (source_pixels, int(viewport_workers), (time.perf_counter() - work_started) * 1000.0)
                if bool(include_histogram):
                    histogram_u8 = self._render_viewer_histogram_u8(
                        full_histogram_source,
                        detail_kwargs,
                        render_kwargs,
                        apply_detail=bool(apply_detail),
                        output_space=output_space,
                        source_profile=source_profile,
                    )
                analysis_text = None
                return (
                    request_key,
                    source_key,
                    None if result_srgb is None else np.asarray(result_srgb),
                    np.asarray(display_u8, dtype=np.uint8),
                    bool(compare_enabled),
                    bool(bypass_display_profile),
                    viewport_rect,
                    None if histogram_u8 is None else np.asarray(histogram_u8, dtype=np.uint8),
                    analysis_text,
                    "; ".join(dict.fromkeys(warnings)) if warnings else None,
                    worker_perf,
                )
            if apply_detail:
                detail_adjusted = apply_adjustments(
                    source,
                    denoise_luminance=float(detail_kwargs.get("denoise_luminance", 0.0)),
                    denoise_color=float(detail_kwargs.get("denoise_color", 0.0)),
                    sharpen_amount=float(detail_kwargs.get("sharpen_amount", 0.0)),
                    sharpen_radius=float(detail_kwargs.get("sharpen_radius", 1.0)),
                    lateral_ca_red_scale=float(detail_kwargs.get("lateral_ca_red_scale", 1.0)),
                    lateral_ca_blue_scale=float(detail_kwargs.get("lateral_ca_blue_scale", 1.0)),
                )
            else:
                # During tonal curve/slider drag prioritize responsiveness and
                # defer detail operators to the final non-interactive refresh.
                detail_adjusted = source
            if (
                not bool(include_analysis)
                and source_profile is None
                and not bool(apply_detail)
                and is_generic_output_space(output_space)
                and generic_output_profile(output_space).key == "srgb"
            ):
                fast_srgb_u8 = render_adjustments_affine_u8(detail_adjusted, **render_kwargs)
                if fast_srgb_u8 is not None:
                    display_u8 = srgb_u8_to_display_u8(fast_srgb_u8, monitor_profile)
                    return (
                        request_key,
                        source_key,
                        np.asarray(fast_srgb_u8, dtype=np.uint8) if bool(include_colorimetric_patch) else None,
                        np.asarray(display_u8, dtype=np.uint8),
                        bool(compare_enabled),
                        bool(bypass_display_profile),
                        viewport_rect,
                        np.asarray(fast_srgb_u8, dtype=np.uint8) if bool(include_histogram) else None,
                        None,
                        "; ".join(dict.fromkeys(warnings)) if warnings else None,
                        None,
                    )
            if render_tiled:
                adjusted = self._apply_render_adjustments_tiled(detail_adjusted, render_kwargs)
            else:
                adjusted = apply_render_adjustments(detail_adjusted, **render_kwargs)
            if source_profile is not None:
                result_srgb = None
                try:
                    if render_tiled:
                        adjusted_u8 = None
                        display_u8 = self._profiled_float_to_display_u8_tiled(adjusted, source_profile, monitor_profile)
                    else:
                        adjusted_u8 = rgb_float_to_u8(adjusted)
                        display_u8 = profiled_u8_to_display_u8(adjusted_u8, source_profile, monitor_profile)
                except Exception as exc:
                    raise RuntimeError(f"No se pudo convertir la vista previa del ICC de imagen al ICC de monitor: {exc}") from exc
                if bool(include_colorimetric_patch):
                    try:
                        result_srgb_u8 = (
                            self._profiled_float_to_display_u8_tiled(adjusted, source_profile, None)
                            if render_tiled
                            else profiled_u8_to_display_u8(adjusted_u8, source_profile, None)
                        )
                        result_srgb = np.asarray(result_srgb_u8, dtype=np.uint8)
                    except Exception as exc:
                        raise RuntimeError(f"No se pudo convertir la vista previa con el ICC de imagen: {exc}") from exc
            else:
                if render_tiled:
                    result_srgb = self._standard_profile_to_srgb_display_tiled(adjusted, output_space)
                    display_u8 = srgb_display_u8(result_srgb)
                else:
                    result_srgb_u8 = standard_profile_to_srgb_u8_display(adjusted, output_space)
                    display_u8 = srgb_u8_to_display_u8(result_srgb_u8, monitor_profile)
                    result_srgb = (
                        np.asarray(result_srgb_u8, dtype=np.uint8)
                        if bool(include_colorimetric_patch)
                        else None
                    )
            if bool(include_histogram):
                if viewport_rect is None and result_srgb is not None:
                    histogram_u8 = self._histogram_u8_from_colorimetric_preview_patch(result_srgb)
                if histogram_u8 is None:
                    histogram_u8 = self._render_viewer_histogram_u8(
                        full_histogram_source,
                        detail_kwargs,
                        render_kwargs,
                        apply_detail=bool(apply_detail),
                        output_space=output_space,
                        source_profile=source_profile,
                    )
            analysis_text = preview_analysis_text(source, adjusted) if include_analysis else None
            return (
                request_key,
                source_key,
                None if result_srgb is None else np.asarray(result_srgb),
                np.asarray(display_u8, dtype=np.uint8),
                bool(compare_enabled),
                bool(bypass_display_profile),
                viewport_rect,
                None if histogram_u8 is None else np.asarray(histogram_u8, dtype=np.uint8),
                analysis_text,
                "; ".join(dict.fromkeys(warnings)) if warnings else None,
                None,
            )

        thread = TaskThread(task)
        started_at = time.perf_counter()
        self._interactive_preview_task_active = True
        self._interactive_preview_inflight_key = request_key
        self._interactive_preview_inflight_viewport_rect = viewport_rect
        self._interactive_preview_inflight_include_analysis = bool(include_analysis)
        self._set_interactive_preview_busy(True)
        self._threads.append(thread)

        def cleanup() -> None:
            stale = (
                int(getattr(self, "_interactive_preview_task_token", 0)) != task_token
                or self._interactive_preview_inflight_key != request_key
            )
            if thread in self._threads:
                self._threads.remove(thread)
            thread.deleteLater()
            if stale:
                return
            self._interactive_preview_task_active = False
            self._interactive_preview_inflight_key = None
            self._interactive_preview_inflight_viewport_rect = None
            self._interactive_preview_inflight_include_analysis = False
            pending = self._interactive_preview_pending_request
            self._interactive_preview_pending_request = None
            if pending is not None:
                self._start_interactive_preview_task(pending)
                return
            self._set_interactive_preview_busy(False)

        def ok(payload) -> None:
            try:
                (
                    key,
                    payload_source_key,
                    candidate,
                    display_u8,
                    payload_compare_enabled,
                    payload_bypass_display_profile,
                    payload_viewport_rect,
                    histogram_candidate,
                    analysis_text,
                    warning,
                    worker_perf,
                ) = payload
                if isinstance(worker_perf, tuple) and len(worker_perf) == 3:
                    self._record_interactive_worker_performance(
                        int(worker_perf[0]),
                        int(worker_perf[1]),
                        float(worker_perf[2]),
                    )
                applied = False
                stale_task = (
                    int(getattr(self, "_interactive_preview_task_token", 0)) != task_token
                    or self._interactive_preview_inflight_key != request_key
                )
                if stale_task:
                    return
                if payload_source_key is not None and payload_source_key != self._last_loaded_preview_key:
                    return
                if payload_viewport_rect is None and key != self._interactive_preview_expected_key:
                    return
                if payload_viewport_rect is not None:
                    preview_patch = None if candidate is None else np.asarray(candidate)
                    applied = self._apply_result_display_u8_region(
                        display_u8,
                        preview_patch,
                        payload_viewport_rect,
                        compare_enabled=bool(payload_compare_enabled and self.chk_compare.isChecked()),
                        bypass_profile=bool(payload_bypass_display_profile),
                    )
                    if histogram_candidate is not None:
                        self._update_viewer_histogram(np.asarray(histogram_candidate, dtype=np.uint8))
                else:
                    if candidate is None:
                        return
                    self._preview_srgb = self._preview_candidate_to_float(candidate)
                    self._set_result_display_u8(
                        display_u8,
                        compare_enabled=bool(payload_compare_enabled and self.chk_compare.isChecked()),
                        bypass_profile=bool(payload_bypass_display_profile),
                        update_histogram=histogram_candidate is None,
                    )
                    if histogram_candidate is not None:
                        self._update_viewer_histogram(np.asarray(histogram_candidate, dtype=np.uint8))
                    applied = True
                if applied:
                    if warning:
                        key_warning = f"interactive-preview-profile|{warning}"
                        if self._profile_preview_error_key != key_warning:
                            self._profile_preview_error_key = key_warning
                            self._log_preview(warning)
                    if isinstance(analysis_text, str) and hasattr(self, "preview_analysis"):
                        self.preview_analysis.setPlainText(analysis_text)
                    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
                    self._interactive_preview_last_ms = float(max(elapsed_ms, 0.0))
                    self._update_interactive_preview_time_label()
            finally:
                cleanup()

        def fail(trace: str) -> None:
            line = trace.strip().splitlines()[-1] if trace.strip() else "error desconocido"
            key = f"interactive-preview-failed|{request_key}|{line}"
            if self._profile_preview_error_key != key:
                self._profile_preview_error_key = key
                self._log_preview(f"Aviso: fallo en vista previa interactiva; se conserva la ultima vista: {line}")
                self._set_status(self.tr("Vista previa interactiva fallida; puedes seguir ajustando."))
            cleanup()

        thread.succeeded.connect(ok)
        thread.failed.connect(fail)
        thread.start()
        QtCore.QTimer.singleShot(
            self._interactive_preview_timeout_ms(
                source_linear=source_linear,
                max_side_limit=int(max_side_limit),
            ),
            lambda: self._abandon_stuck_interactive_preview(task_token, request_key),
        )

    def _abandon_stuck_interactive_preview(self, task_token: int, request_key: str) -> None:
        if not bool(getattr(self, "_interactive_preview_task_active", False)):
            return
        if int(getattr(self, "_interactive_preview_task_token", 0)) != int(task_token):
            return
        if getattr(self, "_interactive_preview_inflight_key", None) != request_key:
            return
        self._interactive_preview_task_token = int(getattr(self, "_interactive_preview_task_token", 0)) + 1
        self._interactive_preview_task_active = False
        self._interactive_preview_inflight_key = None
        self._interactive_preview_inflight_viewport_rect = None
        self._interactive_preview_inflight_include_analysis = False
        pending = self._interactive_preview_pending_request
        self._interactive_preview_pending_request = None
        self._log_preview("Aviso: vista previa interactiva cancelada por tiempo de espera; se reanuda la cola de ajustes.")
        if pending is not None:
            self._start_interactive_preview_task(pending)
        else:
            self._interactive_preview_expected_key = None
            self._set_interactive_preview_busy(False)

    def _reset_adjustments(self) -> None:
        history_suspend = int(getattr(self, "_suspend_edit_history", 0) or 0)
        self._suspend_edit_history = history_suspend + 1
        self.slider_sharpen.setValue(0)
        self.slider_radius.setValue(10)
        self.slider_noise_luma.setValue(0)
        self.slider_noise_color.setValue(0)
        self.slider_ca_red.setValue(0)
        self.slider_ca_blue.setValue(0)
        self._suspend_edit_history = history_suspend
        if hasattr(self, "_push_edit_history_snapshot"):
            self._push_edit_history_snapshot("reset_detail")
        if self._original_linear is not None:
            self._refresh_preview()
        if hasattr(self, "_schedule_detail_adjustment_sidecar_persist"):
            self._schedule_detail_adjustment_sidecar_persist(immediate=True)

    def _refresh_preview(self, *, force_final: bool = False) -> None:
        if self._original_linear is None:
            return
        self._preview_refresh_timer.stop()
        try:
            recipe = self._color_managed_preview_recipe(self._build_effective_recipe())
            interactive = False if bool(force_final) else self._is_preview_interaction_active()
            detail_interactive = interactive and self._is_detail_interaction_active()
            bypass_display_profile = bool(interactive and self._interactive_bypass_display_icc)
            nl = self.slider_noise_luma.value() / 100.0
            nc = self.slider_noise_color.value() / 100.0
            sharpen = self.slider_sharpen.value() / 100.0
            radius = self.slider_radius.value() / 10.0
            ca_red, ca_blue = self._ca_scale_factors()
            detail_kwargs: dict[str, float] = {
                "denoise_luminance": float(nl),
                "denoise_color": float(nc),
                "sharpen_amount": float(sharpen),
                "sharpen_radius": float(radius),
                "lateral_ca_red_scale": float(ca_red),
                "lateral_ca_blue_scale": float(ca_blue),
            }
            render_kwargs = self._render_adjustment_kwargs()

            compare_enabled = bool(self.chk_compare.isChecked())
            if compare_enabled:
                self._ensure_original_compare_panel(bypass_profile=bypass_display_profile)

            source_key = self._last_loaded_preview_key or str(id(self._original_linear))
            source_profile = self._source_profile_for_preview_recipe(recipe)
            monitor_profile = None if bypass_display_profile else self._active_display_profile_path()
            final_display_max_side = int(self._final_adjustment_preview_max_side())
            final_display_cache_key = None
            if not interactive:
                final_display_cache_key = self._display_preview_cache_key(
                    source_key=source_key,
                    detail_kwargs=detail_kwargs,
                    render_kwargs=render_kwargs,
                    output_space=str(recipe.output_space),
                    source_profile=source_profile,
                    monitor_profile=monitor_profile,
                    max_side_limit=final_display_max_side,
                    bypass_profile=bypass_display_profile,
                )
                cached_display = self._cached_display_preview(final_display_cache_key)
                if cached_display is not None:
                    display_u8, colorimetric_u8, preview_srgb, analysis_text = cached_display
                    if preview_srgb is not None:
                        self._preview_srgb = preview_srgb
                    self._set_result_u8_pair(
                        display_u8,
                        colorimetric_u8,
                        compare_enabled=compare_enabled,
                        bypass_profile=bypass_display_profile,
                    )
                    self._update_tone_curve_histogram_for_current_controls(
                        max_side_limit=PREVIEW_INTERACTIVE_TONAL_MAX_SIDE,
                        async_update=False,
                    )
                    self.preview_analysis.setPlainText(analysis_text)
                    return
            if interactive:
                apply_detail = bool(detail_interactive or self._detail_kwargs_have_effect(detail_kwargs))
                viewport_rect = self._interactive_viewport_rect(
                    compare_enabled=compare_enabled,
                    apply_detail=bool(apply_detail),
                )
                if viewport_rect is not None:
                    max_side_limit = 0
                elif self._real_pixel_view_requested() and self._loaded_preview_has_real_pixels_for_viewport():
                    max_side_limit = 0
                else:
                    max_side_limit = (
                        PREVIEW_INTERACTIVE_DRAG_MAX_SIDE
                        if apply_detail
                        else PREVIEW_INTERACTIVE_TONAL_MAX_SIDE
                    )
                overlay_enabled = bool(
                    getattr(self, "check_image_clip_overlay", None)
                    and self.check_image_clip_overlay.isChecked()
                )
                defer_exact_histogram = self._is_preview_interaction_active()
                include_colorimetric_patch = bool(
                    viewport_rect is None
                    or overlay_enabled
                    or not defer_exact_histogram
                )
                if defer_exact_histogram:
                    include_histogram = bool(self._interactive_histogram_due(interval_ms=80))
                else:
                    include_histogram = bool(
                        True
                        if viewport_rect is None or overlay_enabled
                        else self._interactive_histogram_due()
                    )
                self._update_tone_curve_histogram_for_current_controls(
                    max_side_limit=PREVIEW_INTERACTIVE_TONAL_MAX_SIDE,
                    async_update=True,
                )
                self._interactive_preview_request_seq += 1
                request_key = f"{source_key}|interactive|{self._interactive_preview_request_seq}"
                self._profile_preview_expected_key = None
                self._profile_preview_pending_request = None
                self._queue_interactive_preview_request(
                    (
                        request_key,
                        source_key,
                        self._original_linear,
                        detail_kwargs,
                        render_kwargs,
                        compare_enabled,
                        bypass_display_profile,
                        int(max_side_limit),
                        bool(apply_detail),
                        False,
                        str(recipe.output_space),
                        source_profile,
                        monitor_profile,
                        viewport_rect,
                        bool(include_histogram),
                        bool(include_colorimetric_patch),
                    )
                )
                return

            self._interactive_preview_expected_key = None
            self._interactive_preview_pending_request = None
            self._set_interactive_preview_busy(False)

            if self._should_async_final_preview():
                self._update_tone_curve_histogram_for_current_controls(
                    max_side_limit=final_display_max_side,
                )
                self._interactive_preview_request_seq += 1
                request_key = f"{source_key}|final|{self._interactive_preview_request_seq}"
                self._queue_interactive_preview_request(
                    (
                        request_key,
                        source_key,
                        self._original_linear,
                        detail_kwargs,
                        render_kwargs,
                        compare_enabled,
                        False,
                        final_display_max_side,
                        True,
                        True,
                        str(recipe.output_space),
                        source_profile,
                        self._active_display_profile_path(),
                        None,
                        False,
                        True,
                    )
                )
                return

            preview_source = self._interactive_preview_source(
                self._original_linear,
                max_side_limit=final_display_max_side,
            )
            self._update_tone_curve_histogram_for_current_controls(
                max_side_limit=0,
            )
            detail_adjusted = self._detail_adjusted_preview(
                preview_source,
                denoise_luma=nl,
                denoise_color=nc,
                sharpen_amount=sharpen,
                sharpen_radius=radius,
                lateral_ca_red_scale=ca_red,
                lateral_ca_blue_scale=ca_blue,
            )
            adjusted = apply_render_adjustments(detail_adjusted, **render_kwargs)
            self._adjusted_linear = adjusted
            self._adjusted_linear_signature = self._current_adjusted_linear_signature()
            active_session_profile = self._active_session_icc_for_settings()
            raw_profile_text = self.path_profile_active.text().strip() if hasattr(self, "path_profile_active") else ""

            if source_profile is not None:
                try:
                    result_srgb = profiled_float_to_display_u8(adjusted, source_profile, None).astype(np.float32) / 255.0
                except Exception as exc:
                    raise RuntimeError(f"No se pudo calcular la vista previa colorimetrica desde el ICC de entrada: {exc}") from exc
            else:
                result_srgb = standard_profile_to_srgb_display(adjusted, recipe.output_space)

            if raw_profile_text and active_session_profile is None:
                p = Path(raw_profile_text).expanduser()
                status = self._profile_status_for_path(p) or "no disponible"
                self._log_preview(
                    f"Aviso: perfil ICC no aplicado porque su estado QA es {status}."
                )
                self.path_profile_active.clear()
                if hasattr(self, "chk_apply_profile"):
                    self.chk_apply_profile.setChecked(False)
                self._profile_preview_expected_key = None
            else:
                self._profile_preview_expected_key = None

            self._preview_srgb = np.asarray(result_srgb, dtype=np.float32)
            if source_profile is not None:
                display_u8 = self._profiled_display_u8_for_screen(
                    adjusted,
                    source_profile,
                    bypass_profile=bypass_display_profile,
                )
            else:
                display_u8 = self._display_u8_for_screen(
                    self._preview_srgb,
                    bypass_profile=bypass_display_profile,
                )
            colorimetric_u8 = self._preview_colorimetric_u8(display_u8)
            self._set_result_u8_pair(
                display_u8,
                colorimetric_u8,
                compare_enabled=compare_enabled,
                bypass_profile=bypass_display_profile,
            )
            analysis_text = preview_analysis_text(preview_source, adjusted)
            self.preview_analysis.setPlainText(analysis_text)
            if final_display_cache_key is not None:
                self._cache_display_preview(
                    final_display_cache_key,
                    display_u8=display_u8,
                    colorimetric_u8=colorimetric_u8,
                    preview_srgb=self._preview_srgb,
                    analysis_text=analysis_text,
                )
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, self.tr("Aviso"), str(exc))

    def _schedule_preview_refresh(self) -> None:
        if self._original_linear is None:
            return
        if hasattr(self, "_mark_color_picker_samples_pending_for_adjustment_change"):
            self._mark_color_picker_samples_pending_for_adjustment_change()
        if self._is_preview_interaction_active():
            if not self._preview_refresh_timer.isActive():
                self._preview_refresh_timer.start(PREVIEW_REFRESH_THROTTLE_MS)
            return
        self._preview_refresh_timer.start(PREVIEW_REFRESH_DEBOUNCE_MS)

    def _schedule_tone_curve_drag_preview_refresh(self) -> None:
        if self._original_linear is None:
            return
        self._mark_preview_control_interaction(duration_ms=450)
        timer = getattr(self, "_tone_curve_preview_timer", None)
        editor = getattr(self, "tone_curve_editor", None)
        range_dragging = bool(
            editor is not None
            and hasattr(editor, "is_range_dragging")
            and editor.is_range_dragging()
        )
        delay = 0 if range_dragging else max(1, int(PREVIEW_TONE_CURVE_DRAG_THROTTLE_MS))
        if timer is None:
            QtCore.QTimer.singleShot(delay, self._run_tone_curve_drag_preview_refresh)
            return
        if not timer.isActive():
            timer.start(delay)

    def _run_tone_curve_drag_preview_refresh(self) -> None:
        if self._original_linear is None:
            return
        if not bool(getattr(self, "check_tone_curve_enabled", None) and self.check_tone_curve_enabled.isChecked()):
            return
        if self._is_direct_preview_interaction_active():
            self._mark_preview_control_interaction(duration_ms=450)
        self._schedule_preview_refresh()

    def _schedule_post_interaction_exact_preview_refresh(self, *, delay_ms: int) -> None:
        if self._original_linear is None:
            return
        timer = getattr(self, "_preview_exact_after_interaction_timer", None)
        if timer is None:
            timer = QtCore.QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._run_post_interaction_exact_preview_refresh)
            self._preview_exact_after_interaction_timer = timer
        timer.start(max(1, int(delay_ms)))

    def _run_post_interaction_exact_preview_refresh(self) -> None:
        if self._original_linear is None:
            return
        if self._is_direct_preview_interaction_active():
            self._schedule_post_interaction_exact_preview_refresh(delay_ms=180)
            return
        self._preview_recent_interaction_until = 0.0
        self._preview_recent_detail_interaction_until = 0.0
        self._refresh_preview(force_final=True)

    def _schedule_exact_histogram_refresh(self, *, delay_ms: int, mark_pending: bool = True) -> None:
        if self._original_linear is None:
            return
        histogram = getattr(self, "viewer_histogram", None)
        if bool(mark_pending) and histogram is not None and hasattr(histogram, "set_pending"):
            histogram.set_pending(self.tr("Actualizando..."))
        if bool(mark_pending) and hasattr(self, "histogram_shadow_label") and hasattr(self, "histogram_highlight_label"):
            self.histogram_shadow_label.setText(self.tr("Sombras: recalculando..."))
            self.histogram_highlight_label.setText(self.tr("Luces: recalculando..."))
            pending_style = "font-size: 12px; color: #a6a6a6;"
            self.histogram_shadow_label.setStyleSheet(pending_style)
            self.histogram_highlight_label.setStyleSheet(pending_style)
        timer = getattr(self, "_exact_histogram_refresh_timer", None)
        if timer is None:
            timer = QtCore.QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._run_exact_histogram_refresh)
            self._exact_histogram_refresh_timer = timer
        timer.start(max(1, int(delay_ms)))

    def _run_exact_histogram_refresh(self) -> None:
        if self._original_linear is None:
            return
        if self._is_direct_preview_interaction_active():
            self._schedule_exact_histogram_refresh(delay_ms=160, mark_pending=False)
            return
        try:
            recipe = self._color_managed_preview_recipe(self._build_effective_recipe())
            nl = self.slider_noise_luma.value() / 100.0
            nc = self.slider_noise_color.value() / 100.0
            sharpen = self.slider_sharpen.value() / 100.0
            radius = self.slider_radius.value() / 10.0
            ca_red, ca_blue = self._ca_scale_factors()
            detail_kwargs: dict[str, float] = {
                "denoise_luminance": float(nl),
                "denoise_color": float(nc),
                "sharpen_amount": float(sharpen),
                "sharpen_radius": float(radius),
                "lateral_ca_red_scale": float(ca_red),
                "lateral_ca_blue_scale": float(ca_blue),
            }
            source_key = self._last_loaded_preview_key or str(id(self._original_linear))
            selected = getattr(self, "_selected_file", None)
            load_full_source = False
            self._exact_histogram_request_seq = int(getattr(self, "_exact_histogram_request_seq", 0)) + 1
            request_key = f"{source_key}|hist|{self._exact_histogram_request_seq}"
            request = (
                request_key,
                source_key,
                self._original_linear,
                Path(selected) if selected is not None else None,
                Recipe(**asdict(recipe)),
                self._active_session_icc_for_settings(),
                self._preview_decode_cache_dir(Path(selected)) if selected is not None else None,
                load_full_source,
                detail_kwargs,
                self._render_adjustment_kwargs(),
                bool(self._detail_kwargs_have_effect(detail_kwargs)),
                str(recipe.output_space),
                self._source_profile_for_preview_recipe(recipe),
            )
            self._queue_exact_histogram_request(request)
        except Exception as exc:
            self._log_preview(f"Aviso: no se pudo preparar histograma exacto: {exc}")

    def _queue_exact_histogram_request(
        self,
        request: tuple[
            str,
            str | None,
            np.ndarray,
            Path | None,
            Recipe,
            Path | None,
            Path | None,
            bool,
            dict[str, float],
            dict[str, Any],
            bool,
            str,
            Path | None,
        ],
    ) -> None:
        request_key = request[0]
        self._exact_histogram_expected_key = request_key
        if bool(getattr(self, "_exact_histogram_task_active", False)):
            self._exact_histogram_pending_request = request
            return
        self._exact_histogram_pending_request = None
        self._start_exact_histogram_task(request)

    def _start_exact_histogram_task(
        self,
        request: tuple[
            str,
            str | None,
            np.ndarray,
            Path | None,
            Recipe,
            Path | None,
            Path | None,
            bool,
            dict[str, float],
            dict[str, Any],
            bool,
            str,
            Path | None,
        ],
    ) -> None:
        (
            request_key,
            source_key,
            source_linear,
            selected,
            recipe,
            input_profile_path,
            cache_dir,
            load_full_source,
            detail_kwargs,
            render_kwargs,
            apply_detail,
            output_space,
            source_profile,
        ) = request
        self._exact_histogram_task_active = True

        def task():
            histogram_source = np.asarray(source_linear, dtype=np.float32)
            if bool(load_full_source) and selected is not None:
                histogram_source, _msg = load_image_for_preview(
                    Path(selected),
                    recipe=recipe,
                    fast_raw=False,
                    max_preview_side=0,
                    input_profile_path=input_profile_path,
                    cache_dir=cache_dir,
                )
            histogram_u8 = self._render_viewer_histogram_u8(
                np.asarray(histogram_source, dtype=np.float32),
                detail_kwargs,
                render_kwargs,
                apply_detail=bool(apply_detail),
                output_space=output_space,
                source_profile=source_profile,
            )
            return request_key, source_key, histogram_u8

        thread = TaskThread(task)
        self._threads.append(thread)

        def cleanup() -> None:
            if thread in self._threads:
                self._threads.remove(thread)
            thread.deleteLater()
            pending = getattr(self, "_exact_histogram_pending_request", None)
            self._exact_histogram_pending_request = None
            if pending is not None:
                self._start_exact_histogram_task(pending)
                return
            self._exact_histogram_task_active = False

        def ok(payload) -> None:
            try:
                key, payload_source_key, histogram_u8 = payload
                if key != getattr(self, "_exact_histogram_expected_key", None):
                    return
                if payload_source_key is not None and payload_source_key != self._last_loaded_preview_key:
                    return
                if histogram_u8 is None:
                    return
                histogram = np.asarray(histogram_u8, dtype=np.uint8)
                self._update_viewer_histogram(histogram)
            finally:
                cleanup()

        def fail(trace: str) -> None:
            try:
                line = trace.strip().splitlines()[-1] if trace.strip() else "error desconocido"
                self._log_preview(f"Aviso: fallo actualizando histograma exacto: {line}")
            finally:
                cleanup()

        thread.succeeded.connect(ok)
        thread.failed.connect(fail)
        thread.start()

    def _schedule_visible_viewport_preview_refresh(self, *, duration_ms: int = 450) -> None:
        if self._original_linear is None:
            return
        if getattr(self, "_current_result_display_u8", None) is None:
            return
        self._mark_preview_control_interaction(duration_ms=max(1, int(duration_ms)))
        self._schedule_preview_refresh()

    def _automatic_full_final_preview_enabled(self) -> bool:
        raw = os.environ.get(PREVIEW_AUTOMATIC_FULL_FINAL_REFRESH_ENV, "").strip().lower()
        if raw in {"1", "true", "yes", "on"}:
            return True
        if raw in {"0", "false", "no", "off"}:
            return False
        return False

    def _schedule_deferred_final_preview_refresh(self, *, delay_ms: int = PREVIEW_FINAL_REFRESH_IDLE_DELAY_MS) -> None:
        if self._original_linear is None:
            return
        if not self._automatic_full_final_preview_enabled():
            timer = getattr(self, "_preview_final_refresh_timer", None)
            if timer is not None:
                timer.stop()
            return
        timer = getattr(self, "_preview_final_refresh_timer", None)
        if timer is None:
            QtCore.QTimer.singleShot(max(1, int(delay_ms)), lambda: self._refresh_preview(force_final=True))
            return
        timer.start(max(1, int(delay_ms)))

    def _run_deferred_final_preview_refresh(self) -> None:
        if self._original_linear is None:
            return
        if self._is_direct_preview_interaction_active():
            self._schedule_deferred_final_preview_refresh()
            return
        self._preview_recent_interaction_until = 0.0
        self._refresh_preview(force_final=True)

    def _interactive_histogram_due(self, *, interval_ms: int = 120) -> bool:
        now = time.perf_counter()
        last = float(getattr(self, "_interactive_histogram_last_started_at", 0.0) or 0.0)
        if last <= 0.0 or (now - last) * 1000.0 >= max(1, int(interval_ms)):
            self._interactive_histogram_last_started_at = now
            return True
        return False

    def _should_async_final_preview(self) -> bool:
        if self._original_linear is None:
            return False
        try:
            pixels = int(self._original_linear.shape[0]) * int(self._original_linear.shape[1])
        except Exception:
            return False
        return pixels > 2_000_000

    def _looks_broken_profile_preview(self, image_srgb: np.ndarray) -> bool:
        x = np.clip(np.asarray(image_srgb, dtype=np.float32), 0.0, 1.0)
        if x.ndim != 3 or x.shape[2] < 3:
            return True
        if not np.isfinite(x).all():
            return True

        means = np.mean(x[..., :3], axis=(0, 1))
        clipped_hi = np.mean(x[..., :3] >= 0.995, axis=(0, 1))
        clipped_channels = int(np.count_nonzero(clipped_hi > 0.80))
        chroma_ratio = float((np.max(means) + 1e-6) / (np.min(means) + 1e-6))

        # Heuristic safeguard for clearly wrong matrix/profile assignments.
        return clipped_channels >= 2 and chroma_ratio > 3.5
