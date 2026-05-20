_Versión en español: [COLOR_PIPELINE.es.md](COLOR_PIPELINE.es.md)_

# Color Pipeline

## Operational Status

ProbRAW 0.3.10 implements the main ICC workflow and the session-based GUI. The
application is suitable for controlled testing and release validation, but it
should not yet be presented as a certified scientific or forensic production
system.

The complete methodology is described in
[RAW development methodology and ICC management](METODOLOGIA_COLOR_RAW.md).
The operating-system integration with system profiles, LittleCMS2, WCS/ICM,
ColorSync, colord, KDE/Wayland and environment validation is documented in
[System Color Management in ProbRAW](GESTION_COLOR_LINUX_PROBRAW.md).

## Design Principle

The pipeline separates:

1. reproducible RAW development;
2. parametric development profile;
3. image input ICC profile;
4. monitor ICC profile for display only;
5. audit through backpacks, manifests, Proof and optional C2PA.

ProbRAW assigns input profiles to images. Those input profiles are either
session/camera ICC profiles built from colorimetric references, or generic ICC
profiles used as explicit fallback when no session reference exists. Output
RGB values generated from RAW are relative to the device or development space;
without an input ICC tag they do not objectively identify the color represented
by each RGB triplet. Inventing additional profiles and implicit conversion to
unrelated spaces are not part of the objective analysis path.

DCP is not part of the active 0.3 pipeline.

## Scientific Mode (`profiling_mode`)

Objective: neutrality and reproducibility, not creative appearance.

Rules:

1. no creative sharpening during chart measurement;
2. no aggressive denoise during chart measurement;
3. no artistic tone curves;
4. fixed or explicit white balance;
5. linear signal for profiling;
6. chart geometry reusable between passes.

## Phases

1. `raw-info`: read technical metadata.
2. `develop`: controlled base development with LibRaw/rawpy.
3. `detect-chart`: chart detection, homography and patches.
4. `sample-chart`: robust per-patch measurement.
5. `build-develop-profile`: neutrality, density and EV from the neutral row.
6. Calibrated recipe: fixed WB, EV limited by highlight preservation, linear
   signal and no creative processing.
7. Second chart measurement with the same geometry and calibrated recipe.
8. `build-profile`: ArgyllCMS (`colprof`) generates the input ICC.
9. `validate-profile`: DeltaE 76/2000 validation of the real ICC.
10. `batch-develop`: batch rendering with assigned development profile and ICC.

Custom chart references are stored in `00_configuraciones/references/`. Each
advanced profiling run writes its artifacts under
`00_configuraciones/profile_runs/`, and resulting ICC files are registered as
activatable session profiles.

## Critical Invariants

1. The executed recipe must match the declared recipe.
2. The linear audit TIFF must be written before tone curves or output
   encoding/export operations.
3. ICC management separates input profile assignment and monitor visualization;
   analysis must not invent additional profiles.
4. Validation checks the real generated ICC, not only auxiliary matrices.
5. Chart detection fallback must not generate profiles automatically without an
   explicit mode or review.
6. Chart geometry from the base pass can be reused in the calibrated pass.
7. The ICC must not compensate basic exposure/density if the chart allows a
   calibrated recipe to be built first.
8. With a chart, the master TIFF preserves linear camera/session RGB and embeds
   the input ICC.
9. Without a chart, the image still receives a real generic input ICC profile
   that gives colorimetric meaning to RGB values; it is not an invented
   alternate profile.
10. On-screen display uses only the display conversion from the active input ICC
    profile to the configured monitor ICC profile.
11. The GUI histogram and clipping overlay are computed from the colorimetric
    preview signal before applying the monitor ICC.
12. The 3D gamut diagnostic is a visual profile comparison; it does not modify
    recipes, pixels, active profiles or manifests.
13. No GUI-managed preview or image may be left without an input profile: there
    must be a session/image ICC or a real standard generic profile that gives
    colorimetric meaning to RGB values.

## Display Color Contract

This is a non-negotiable rule for ProbRAW:

- The image/device profile, whether session-specific or generic standard, is
  never converted to sRGB for on-screen display.
- Managed display converts directly from the active source ICC to the monitor
  ICC configured by the operating system or explicitly selected by the user, and
  then hands the already-converted preview to Qt as device RGB.
- Image RGB values have objective colorimetric meaning only when tagged by their
  input ICC.
- ProbRAW does not invent additional profiles for objective image analysis. Any
  exported derivative must stay outside preview, histogram, MTF, sampling and
  profile QA.
- sRGB can appear as a generic input ICC if explicitly chosen, as an explicit
  recipe encoding curve (`tone_curve: srgb`), or as an internal
  diagnostic/reference signal for histogram/parity checks. It must not replace
  the image input ICC or the monitor ICC in managed display.
- A missing or broken monitor ICC is a display configuration problem. ProbRAW
  may use visual sRGB fallback only when it is explicit and reported, without
  replacing the input ICC or converting analysis data.

## Monitor Color Management

The monitor ICC profile does not participate in development, master TIFF or
export. It only corrects the visual representation of previews and thumbnails.

Detection:

- Windows: WCS/ICM.
- macOS: ColorSync.
- Linux/BSD: `colord`, `colormgr` or `_ICC_PROFILE`.

If the monitor profile disappears or cannot be opened, ProbRAW logs the problem
and marks the state as visual sRGB fallback until a valid monitor ICC is detected
or selected. That fallback is display-only; it does not remove or replace the
image input profile and does not participate in recipes, colorimetric
histograms, TIFFs, Proof records or manifests.

## Preview and Histogram

The GUI separates the analysis signal from the display signal:

1. The RAW is developed or previewed as normalized RGB in the image-selected
   signal with an assigned input ICC: a session/camera ICC built from
   colorimetric references, or a real generic ICC fallback such as ProPhoto RGB.
2. Parametric adjustments are applied before visualization.
3. If a source ICC is active, pixels sent to the widget are converted directly
   from that source ICC to the configured monitor ICC and handed to Qt as device
   RGB so Qt/compositor color management does not convert them a second time.
4. The internal sRGB signal is limited to RGB histogram, clipping overlay and
   diagnostics; it does not replace direct monitor conversion when a source ICC
   exists.
5. The monitor ICC is never mixed into analysis data, recipes or exported TIFFs.

This prevents a narrow, defective or machine-specific monitor profile from
altering analysis data. At the same time, the user must calibrate the monitor
and configure the correct ICC in the operating system for the visual appearance
of the preview to be reliable.

## ICC Preview Performance Note

To avoid applying ICC profiles to embedded previews that do not represent the
developed RAW, views with a session ICC or generic profile avoid the embedded
thumbnail and use LibRaw development. Normal preview remains bounded by
`PREVIEW_AUTO_BASE_MAX_SIDE`; only 1:1 precision, compare and chart marking
force full resolution. During 100% work, interactions apply adjustments to the
visible crop, update viewer regions and reuse dense ICC LUT caches generated by
LittleCMS so performance does not sacrifice colorimetric precision. Tone curves
reuse tonal LUTs and share RGB quantization before the `source ICC -> monitor
ICC` and instrument conversions.

## Profile Validity

The profile depends on:

- camera;
- lens;
- illuminant;
- recipe;
- software version;
- relevant RAW pipeline configuration.

Changing those factors can degrade or invalidate colorimetric validity.
