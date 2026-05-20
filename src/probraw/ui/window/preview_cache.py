from __future__ import annotations

from ._imports import *  # noqa: F401,F403


class PreviewCacheMixin:
    @staticmethod
    def _system_total_memory_bytes() -> int | None:
        if os.name == "nt":
            try:
                import ctypes

                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]

                status = MEMORYSTATUSEX()
                status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                    return int(status.ullTotalPhys)
            except Exception:
                return None
        try:
            page_size = int(os.sysconf("SC_PAGE_SIZE"))
            pages = int(os.sysconf("SC_PHYS_PAGES"))
            if page_size > 0 and pages > 0:
                return int(page_size * pages)
        except Exception:
            return None
        return None

    @staticmethod
    def _system_available_memory_bytes() -> int | None:
        if os.name == "nt":
            try:
                import ctypes

                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]

                status = MEMORYSTATUSEX()
                status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                    return int(status.ullAvailPhys)
            except Exception:
                return None
        try:
            page_size = int(os.sysconf("SC_PAGE_SIZE"))
            pages = int(os.sysconf("SC_AVPHYS_PAGES"))
            if page_size > 0 and pages > 0:
                return int(page_size * pages)
        except Exception:
            return None
        return None

    def _preview_cache_override_bytes(self) -> int | None:
        settings_value = None
        if hasattr(self, "_settings"):
            try:
                settings_value = self._settings.value("performance/preview_cache_mb", None)
            except Exception:
                settings_value = None
        for raw in (
            os.environ.get("PROBRAW_PREVIEW_CACHE_MB"),
            os.environ.get("NEXORAW_PREVIEW_CACHE_MB"),
            settings_value,
        ):
            if raw is None or str(raw).strip() == "":
                continue
            try:
                mb = float(raw)
            except Exception:
                continue
            if np.isfinite(mb) and mb > 0.0:
                return int(max(256.0, mb) * 1024.0 * 1024.0)
        return None

    def _preview_cache_max_bytes(self) -> int:
        override = self._preview_cache_override_bytes()
        if override is not None:
            return int(override)
        legacy_floor = int(PREVIEW_CACHE_MAX_BYTES)
        workstation_floor = 1536 * 1024 * 1024
        maximum = 12 * 1024 * 1024 * 1024
        total = self._system_total_memory_bytes()
        if total is None or int(total) <= 0:
            return int(max(legacy_floor, workstation_floor))
        adaptive = int(int(total) * 0.12)
        return int(max(legacy_floor, min(max(workstation_floor, adaptive), maximum)))

    def _preview_recipe_signature(self, recipe: Recipe) -> str:
        wb = ",".join(f"{float(v):.6g}" for v in recipe.wb_multipliers)
        return "|".join(
            [
                recipe.raw_developer,
                recipe.demosaic_algorithm,
                recipe.white_balance_mode,
                recipe.black_level_mode,
                recipe.tone_curve,
                f"{float(recipe.exposure_compensation):.3g}",
                recipe.output_space,
                str(bool(recipe.profiling_mode)),
                wb,
            ]
        )

    def _preview_base_signature(
        self,
        *,
        selected: Path,
        recipe: Recipe,
        input_profile_path: Path | None = None,
    ) -> str:
        try:
            st = selected.stat()
            stamp = f"{st.st_mtime_ns}:{st.st_size}"
        except Exception:
            stamp = "nostat"
        recipe_sig = self._preview_recipe_signature(recipe)
        input_profile_sig = self._preview_input_profile_signature(input_profile_path)
        return f"{self._cache_path_identity(selected)}|{stamp}|preview-v5|{recipe_sig}|ip={input_profile_sig}"

    def _preview_cache_key(
        self,
        *,
        selected: Path,
        recipe: Recipe,
        fast_raw: bool,
        max_preview_side: int,
        input_profile_path: Path | None = None,
    ) -> str:
        base_sig = self._preview_base_signature(
            selected=selected,
            recipe=recipe,
            input_profile_path=input_profile_path,
        )
        fast_token = int(bool(fast_raw))
        return f"{base_sig}|{fast_token}|fr={fast_token}|ms={int(max_preview_side)}"

    def _preview_input_profile_signature(self, input_profile_path: Path | None) -> str:
        if input_profile_path is None:
            return "none"
        try:
            resolved = Path(input_profile_path).expanduser().resolve()
            st = resolved.stat()
            return f"{resolved}|{st.st_mtime_ns}|{st.st_size}"
        except Exception:
            return str(input_profile_path)

    def _display_preview_cache_key(
        self,
        *,
        source_key: str,
        detail_kwargs: dict[str, float],
        render_kwargs: dict[str, Any],
        output_space: str,
        source_profile: Path | None,
        monitor_profile: Path | None,
        max_side_limit: int,
        bypass_profile: bool,
    ) -> str:
        payload = {
            "source": str(source_key),
            "detail": {str(k): round(float(v), 8) for k, v in sorted(detail_kwargs.items())},
            "render": {
                str(k): (round(float(v), 8) if isinstance(v, (int, float, np.floating)) else v)
                for k, v in sorted(render_kwargs.items())
            },
            "output_space": str(output_space),
            "source_profile": self._preview_input_profile_signature(source_profile),
            "monitor_profile": self._preview_input_profile_signature(monitor_profile),
            "max_side": int(max_side_limit),
            "bypass": bool(bypass_profile),
            "display_cache": 1,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _cache_display_preview(
        self,
        key: str,
        *,
        display_u8: np.ndarray,
        colorimetric_u8: np.ndarray | None,
        preview_srgb: np.ndarray | None,
        analysis_text: str,
    ) -> None:
        display = np.ascontiguousarray(np.asarray(display_u8, dtype=np.uint8)[..., :3]).copy()
        colorimetric = (
            None
            if colorimetric_u8 is None
            else np.ascontiguousarray(np.asarray(colorimetric_u8, dtype=np.uint8)[..., :3]).copy()
        )
        preview = (
            None
            if preview_srgb is None
            else np.ascontiguousarray(np.asarray(preview_srgb, dtype=np.float32)[..., :3]).copy()
        )
        if key in self._display_preview_cache:
            self._display_preview_cache.pop(key, None)
            self._display_preview_cache_order = [k for k in self._display_preview_cache_order if k != key]
        self._display_preview_cache[key] = (display, colorimetric, preview, str(analysis_text or ""))
        self._display_preview_cache_order.append(key)
        while len(self._display_preview_cache_order) > 6:
            old = self._display_preview_cache_order.pop(0)
            self._display_preview_cache.pop(old, None)

    def _cached_display_preview(
        self,
        key: str,
    ) -> tuple[np.ndarray, np.ndarray | None, np.ndarray | None, str] | None:
        cached = self._display_preview_cache.get(key)
        if cached is None:
            return None
        self._display_preview_cache_order = [k for k in self._display_preview_cache_order if k != key]
        self._display_preview_cache_order.append(key)
        display, colorimetric, preview, analysis_text = cached
        return (
            display.copy(),
            None if colorimetric is None else colorimetric.copy(),
            None if preview is None else preview.copy(),
            str(analysis_text),
        )

    @staticmethod
    def _run_preview_load_inline() -> bool:
        # Tests expect deterministic preview loading without waiting for Qt threads.
        return bool(
            os.environ.get("PYTEST_CURRENT_TEST")
            or os.environ.get("PROBRAW_SYNC_PREVIEW_LOAD")
        )

    def _cache_preview_memory(self, key: str, image: np.ndarray, *, copy: bool = True) -> None:
        if key in self._preview_cache:
            self._preview_cache.pop(key, None)
            self._preview_cache_order = [k for k in self._preview_cache_order if k != key]
        array = np.asarray(image, dtype=np.float32)
        if copy:
            cached = array.copy()
        elif array.ndim == 3 and array.shape[2] == 3 and array.flags.c_contiguous:
            cached = array
        else:
            cached = np.ascontiguousarray(array[..., :3])
        self._preview_cache[key] = cached
        self._preview_cache_order.append(key)
        max_bytes = int(self._preview_cache_max_bytes())
        while (
            len(self._preview_cache_order) > PREVIEW_CACHE_MAX_ENTRIES
            or self._preview_cache_bytes() > max_bytes
        ):
            old = self._preview_cache_order.pop(0)
            self._preview_cache.pop(old, None)

    def _cache_preview_image(self, key: str, image: np.ndarray, *, selected: Path | None = None) -> None:
        self._cache_preview_memory(key, image)
        self._write_preview_to_disk_cache(key, image, selected=selected)

    def _cached_preview_image(self, key: str, *, selected: Path | None = None) -> np.ndarray | None:
        image = self._preview_cache.get(key)
        if image is not None:
            self._preview_cache_order = [k for k in self._preview_cache_order if k != key]
            self._preview_cache_order.append(key)
            return image
        image = self._read_preview_from_disk_cache(key, selected=selected)
        if image is None:
            image = self._read_preview_from_pyramid_cache(key, selected=selected)
        if image is not None:
            self._cache_preview_memory(key, image, copy=False)
            return image
        self._preview_cache_order = [k for k in self._preview_cache_order if k != key]
        return None

    def _preview_disk_cache_dir(self, selected: Path | None = None) -> Path:
        return self._disk_cache_dirs(selected, "previews")[0]

    def _preview_decode_cache_dir(self, selected: Path | None = None) -> Path:
        return self._disk_cache_dirs(selected, "raw-demosaic")[0]

    def _preview_disk_cache_path(self, key: str, *, base_dir: Path | None = None, selected: Path | None = None) -> Path:
        return self._disk_cache_path(base_dir or self._preview_disk_cache_dir(selected), key, ".npy")

    def _read_preview_from_disk_cache(self, key: str, *, selected: Path | None = None) -> np.ndarray | None:
        for cache_dir in self._disk_cache_dirs(selected, "previews"):
            cache_path = self._preview_disk_cache_path(key, base_dir=cache_dir)
            if not cache_path.is_file():
                continue
            try:
                with cache_path.open("rb") as handle:
                    image = np.load(handle, allow_pickle=False)
                image = np.asarray(image, dtype=np.float32)
                if image.ndim != 3 or image.shape[-1] < 3:
                    continue
                try:
                    os.utime(cache_path, None)
                except Exception:
                    pass
                return np.ascontiguousarray(image[..., :3])
            except Exception:
                continue
        return None

    def _write_preview_to_disk_cache(self, key: str, image: np.ndarray, *, selected: Path | None = None) -> None:
        try:
            cache_dir = self._preview_disk_cache_dir(selected)
            cache_path = self._preview_disk_cache_path(key, base_dir=cache_dir)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = cache_path.with_name(f"{cache_path.name}.tmp")
            array = np.ascontiguousarray(np.asarray(image, dtype=np.float32)[..., :3])
            with tmp_path.open("wb") as handle:
                np.save(handle, array, allow_pickle=False)
            os.replace(tmp_path, cache_path)
            self._prune_disk_cache(
                cache_dir,
                pattern="*.npy",
                max_entries=PREVIEW_DISK_CACHE_MAX_ENTRIES,
                max_bytes=PREVIEW_DISK_CACHE_MAX_BYTES,
            )
            self._write_preview_pyramid_to_disk_cache(key, array, selected=selected)
        except Exception:
            return

    def _preview_pyramid_base_key(self, key: str) -> str | None:
        marker = "|ms="
        if marker not in key:
            return None
        return key.rsplit(marker, 1)[0]

    def _preview_requested_max_side(self, key: str) -> int:
        marker = "|ms="
        if marker not in key:
            return 0
        try:
            return int(key.rsplit(marker, 1)[1])
        except Exception:
            return 0

    def _preview_pyramid_disk_cache_path(
        self,
        base_key: str,
        side: int,
        *,
        base_dir: Path | None = None,
        selected: Path | None = None,
    ) -> Path:
        return self._disk_cache_path(
            base_dir or self._preview_disk_cache_dir(selected),
            f"{base_key}|pyramid|side={int(side)}",
            ".npy",
        )

    def _write_preview_pyramid_to_disk_cache(self, key: str, image: np.ndarray, *, selected: Path | None = None) -> None:
        base_key = self._preview_pyramid_base_key(key)
        if base_key is None:
            return
        rgb = np.asarray(image, dtype=np.float32)
        if rgb.ndim != 3 or rgb.shape[-1] < 3:
            return
        h, w = int(rgb.shape[0]), int(rgb.shape[1])
        source_side = max(h, w)
        if source_side <= 0:
            return
        cache_dir = self._preview_disk_cache_dir(selected)
        requested = self._preview_requested_max_side(key)
        levels = self._preview_pyramid_levels_to_write(source_side=source_side, requested_side=requested)
        for side in levels:
            if side >= source_side:
                continue
            try:
                level = self._downscale_preview_cache_level(rgb, max_side=side)
                path = self._preview_pyramid_disk_cache_path(base_key, side, base_dir=cache_dir)
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp_path = path.with_name(f"{path.name}.tmp")
                with tmp_path.open("wb") as handle:
                    np.save(handle, level, allow_pickle=False)
                os.replace(tmp_path, path)
            except Exception:
                continue

    @staticmethod
    def _preview_pyramid_levels_to_write(*, source_side: int, requested_side: int) -> list[int]:
        levels = [4096, 3200, 2600, 2048, 1600, 1200, 800]
        source = int(source_side)
        requested = int(requested_side)
        if source <= 0:
            return []
        if requested <= 0:
            requested = source
        candidates = [side for side in levels if side < source and side >= requested]
        if candidates:
            return candidates[:2]
        smaller = [side for side in levels if side < source]
        return smaller[:1]

    def _read_preview_from_pyramid_cache(self, key: str, *, selected: Path | None = None) -> np.ndarray | None:
        requested = self._preview_requested_max_side(key)
        if requested <= 0:
            return None
        base_key = self._preview_pyramid_base_key(key)
        if base_key is None:
            return None
        candidates: list[tuple[int, Path]] = []
        for cache_dir in self._disk_cache_dirs(selected, "previews"):
            for side in [4096, 3200, 2600, 2048, 1600, 1200, 800]:
                if side < requested:
                    continue
                path = self._preview_pyramid_disk_cache_path(base_key, side, base_dir=cache_dir)
                if path.is_file():
                    candidates.append((side, path))
        for _side, path in sorted(candidates, key=lambda item: item[0]):
            try:
                with path.open("rb") as handle:
                    image = np.load(handle, allow_pickle=False)
                image = np.asarray(image, dtype=np.float32)
                if image.ndim != 3 or image.shape[-1] < 3:
                    continue
                try:
                    os.utime(path, None)
                except Exception:
                    pass
                return self._downscale_preview_cache_level(image[..., :3], max_side=requested)
            except Exception:
                continue
        return None

    def _downscale_preview_cache_level(self, image: np.ndarray, *, max_side: int) -> np.ndarray:
        rgb = np.asarray(image, dtype=np.float32)
        h, w = int(rgb.shape[0]), int(rgb.shape[1])
        if max(h, w) <= int(max_side):
            return np.ascontiguousarray(rgb[..., :3])
        scale = float(max_side) / float(max(h, w))
        resized = cv2.resize(
            rgb[..., :3],
            (max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
            interpolation=cv2.INTER_AREA,
        )
        return np.ascontiguousarray(np.clip(resized, 0.0, 1.0).astype(np.float32, copy=False))

    def _preview_cache_bytes(self) -> int:
        return int(sum(int(image.nbytes) for image in self._preview_cache.values()))

    def _invalidate_preview_cache(self) -> None:
        self._preview_cache.clear()
        self._preview_cache_order.clear()
        self._display_preview_cache.clear()
        self._display_preview_cache_order.clear()
        self._last_loaded_preview_key = None
        self._loaded_preview_base_signature = None
        self._loaded_preview_fast_raw = None
        self._loaded_preview_source_max_side = 0
        self._loaded_preview_max_side_request = None
        self._loaded_preview_source_profile_path = None
        self._tone_curve_histogram_key = None
        self._tone_curve_histogram_expected_key = None
        self._tone_curve_histogram_pending_request = None
        self._preview_load_pending_request = None
        self._profile_preview_pending_request = None
        self._profile_preview_expected_key = None
        self._profile_preview_error_key = None
        self._interactive_preview_pending_request = None
        self._interactive_preview_expected_key = None
        self._interactive_preview_inflight_viewport_rect = None
        self._interactive_preview_inflight_include_analysis = False
        self._interactive_histogram_last_started_at = 0.0
        self._interactive_preview_request_seq = 0
        self._profile_preview_cache.clear()
        self._profile_preview_cache_order.clear()
        self._clear_adjustment_caches()
        if hasattr(self, "_clear_mtf_image_caches"):
            self._clear_mtf_image_caches()
        self._set_interactive_preview_busy(False)
