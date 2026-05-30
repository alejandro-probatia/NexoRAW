#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import statistics
import sys
import time


def _ensure_probraw_importable() -> None:
    if importlib.util.find_spec("probraw") is not None:
        return
    packaged_python = Path("/opt/probraw/venv/bin/python")
    if packaged_python.exists() and Path(sys.executable).resolve() != packaged_python.resolve():
        os.execv(str(packaged_python), [str(packaged_python), *sys.argv])


_ensure_probraw_importable()

from probraw.core.models import Recipe
from probraw.display_color import profiled_float_to_display_u8
from probraw.performance import configure_runtime
from probraw.profile.generic import ensure_generic_output_profile, generic_output_profile
from probraw.raw.preview import extract_embedded_thumbnail, load_image_for_preview


def _recipe(output_space: str, demosaic: str) -> Recipe:
    profile = generic_output_profile(output_space)
    return Recipe(
        output_space=profile.key,
        output_linear=False,
        tone_curve=f"gamma:{profile.gamma:.3g}",
        profiling_mode=False,
        white_balance_mode="camera_metadata",
        demosaic_algorithm=demosaic,
    )


def _bench(label: str, runs: int, func):
    values: list[float] = []
    result = None
    for index in range(max(1, int(runs))):
        started = time.perf_counter()
        result = func()
        elapsed = time.perf_counter() - started
        values.append(elapsed)
        shape = getattr(result, "shape", None)
        if isinstance(result, tuple):
            shape = getattr(result[0], "shape", None)
        print(f"{label} #{index + 1}: {elapsed:.3f}s shape={shape}")
    print(
        f"{label}: median={statistics.median(values):.3f}s "
        f"min={min(values):.3f}s max={max(values):.3f}s"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark real de carga de preview ProbRAW.")
    parser.add_argument("raw", type=Path, help="RAW o imagen a medir")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--max-side", type=int, default=2600)
    parser.add_argument("--output-space", default="prophoto_rgb")
    parser.add_argument("--demosaic", default="dcb")
    parser.add_argument("--full", action="store_true", help="Incluye una pasada 1:1 completa")
    args = parser.parse_args()

    configure_runtime()
    source = args.raw.expanduser().resolve()
    recipe = _recipe(args.output_space, args.demosaic)
    print(f"source={source}")
    print(f"size={source.stat().st_size if source.exists() else 'missing'} bytes")
    print(f"output_space={recipe.output_space} demosaic={recipe.demosaic_algorithm}")

    _bench(
        f"embedded preview placeholder max_side={args.max_side}",
        args.runs,
        lambda: extract_embedded_thumbnail(source, max_side=args.max_side, apply_orientation=False),
    )
    image, _message = _bench(
        f"raw preview load max_side={args.max_side}",
        args.runs,
        lambda: load_image_for_preview(
            source,
            recipe=recipe,
            fast_raw=False,
            max_preview_side=args.max_side,
            cache_dir=None,
        ),
    )
    source_profile = ensure_generic_output_profile(recipe.output_space)
    _bench(
        f"icc display {recipe.output_space}->sRGB max_side={args.max_side}",
        args.runs,
        lambda: profiled_float_to_display_u8(image, source_profile, None),
    )

    if args.full:
        full, _message = _bench(
            "raw preview load 1:1",
            1,
            lambda: load_image_for_preview(
                source,
                recipe=recipe,
                fast_raw=False,
                max_preview_side=0,
                cache_dir=None,
            ),
        )
        _bench(
            f"icc display {recipe.output_space}->sRGB 1:1",
            1,
            lambda: profiled_float_to_display_u8(full, source_profile, None),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
