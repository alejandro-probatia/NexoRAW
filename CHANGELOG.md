_Spanish version: [CHANGELOG.es.md](CHANGELOG.es.md)_

# Changelog

All relevant ProbRAW changes are documented in this file.

This project follows:

- format inspired by Keep a Changelog,
- versioned SemVer,
- traceability of changes aimed at scientific and forensic use.

## Update policy

To maintain full traceability, each change must:

1. add a line in `Unreleased` before merge/push,
2. move entries to a dated version in each release,
3. reference, when applicable, impact on reproducibility, legality or chain of custody.

## [Unreleased]

No entries yet.

## [0.4.0] - 2026-05-21

### Added

- Added Lab 2D gamut diagnostics with a vertical L* selector alongside the Gamut
  3D comparator.
- Added Lab eyedropper in `Diagnóstico > Muestras`, with real-pixel magnifier,
  sampling matrices, numbered image markers and per-image persistence in
  `RAW.probraw.json`.
- Added sample sets, table/card views, editable name/note fields, set comparison
  with means, DeltaE, similarity percentage and sample gamut in Lab a*b*.

### Changed

- Sample comparison no longer uses a primary sample inside a set; the comparative
  reference is selected at set level.
- User manual, README, color pipeline, methodology, architecture,
  reproducibility, comparison and roadmap docs updated for the Lab sample
  workflow and its colorimetric limits.

### Tests

- Added GUI regression coverage for Lab sample picking, real-pixel reload guard,
  per-image sidecar persistence, sample-set editing and Lab 2D gamut mode.
- Added profile/gamut tests for out-of-gamut markers and Lab membership across
  two compared profiles.

## [0.3.22] - 2026-05-20

### Fixed

- Fixed manual selection of generated session ICC profiles with QA status
  `rejected`: they remain blocked for automatic activation, but can be
  explicitly selected from the session-profile combo, the manual load menu or
  "Use generated ICC".
- Fixed RAW sidecar persistence for those profiles: assigning them to an image
  now stores the profile identifier together with the ICC path, and reloads only
  when both match.
- Fixed the risk of a `rejected` ICC path becoming active through a stale ID or
  through a reopened session without an explicit selection.

### Changed

- The session ICC profile combo remains available when profiles are registered,
  even if the active mode is a standard RGB space, so the operator can
  explicitly switch to a session profile.
- The UI logs/statuses manual activation of `rejected` profiles, preserving
  traceability without blocking the workflow.

### Tests

- Added regression coverage for manual `rejected` ICC selection, menu loading,
  use of generated ICC, RAW sidecar roundtrip, session reopen and rejection of
  inconsistent profile IDs.
- Validated with a real Qt window smoke test in `offscreen` mode, the full
  Windows-build suite (`489 passed, 2 warnings`), `check-amaze`,
  `check-tools --strict`, `check-c2pa` and the update assistant check.

## [0.3.21] - 2026-05-20

### Fixed

- Fixed the ICC generation failure in release 0.3.20 when a manually marked
  chart was reserved as validation and the remaining capture was rejected as
  `fallback_detection`: manual detections are now kept in training, while
  invalid automatic captures become validation/skipped entries without blocking
  generation when useful samples exist.
- Fixed the blue cast in previews using a generated input ICC: the camera RGB
  display-balance compensation is no longer applied when an input ICC profile is
  active.
- The tone-curve histogram now initializes even when the curve effect is
  disabled and recalculates from all tonal and curve adjustments instead of only
  the curve input.
- Curve edits no longer block the interface: the tonal histogram is calculated
  in the background while dragging and only the latest valid result is painted.

### Changed

- Profiling QA keeps the ICC as a usable `draft` when independent validation is
  missing instead of treating that condition as a blocking error.
- Profiling reports include neutral-row a*/b* residuals and non-blocking
  workflow recommendations for lighting, chart reference, profile model and
  validation review.
- The viewer histogram reuses the same already-computed colorimetric preview
  patch when available, reducing repeated work without changing the
  `input ICC -> monitor ICC` path.

### Tests

- Added regression coverage for training/validation splitting with manual
  detections, asynchronous tone-curve histogram queuing, tonal changes that
  modify the histogram and colorimetric preview patch reuse.

## [0.3.20] - 2026-05-20

### Fixed

- Fixed ICC profile generation from a manually marked chart when the previous
  capture selection still pointed at another image: the GUI now prioritizes the
  active capture and keeps the previous selection only as additional captures.
- Fixed session activation/creation so the browser, references, RAW input, TIFF
  exports and profiling artifacts align with the active project root instead of
  inheriting paths from other projects.
- ICC profiling errors now explain why chart captures were skipped, including
  detection mode, confidence, threshold and relevant warnings.
- Fixed the double-conversion risk in display preview: when ProbRAW already
  converts preview pixels to the monitor ICC with LittleCMS, the `QImage` is
  handed to Qt as untagged device RGB without an extra `QColorSpace` tag.

### Changed

- The linear audit TIFF is written before output conversions, tone curves or
  final encoding, and the sidecar preserves the effective RAW processing
  settings used for export.
- Chart samples record the sampling parameters used (`strategy`,
  `trim_percent`, `reject_saturated`) to improve traceability and
  reproducibility.
- RAW backend validation rejects unsupported settings instead of applying
  silent substitutions.
- Monitor color management is documented as a display-only layer: exported
  TIFFs keep the selected input ICC and do not use the monitor profile.
- Active monitor ICC detection is cached by screen and settings, reducing
  repeated system profile probes during previews, thumbnails and interactive
  refreshes.

### Tests

- Added regression coverage for sessions carrying paths from old projects,
  pending manual chart marking, linear audit TIFF output, RAW sidecar metadata
  and detailed profiling errors.
- Validated with `pytest -q tests/test_gui_session_paths.py -k "session"`,
  focused manual-marking GUI tests, `pytest -q tests
  --ignore=tests/test_gui_session_paths.py` and `git diff --check`.
- Added coverage to ensure monitor-converted buffers are not tagged with a
  `QColorSpace`, and to ensure monitor ICC conversion failures do not silently
  fall back to unmanaged sRGB.
- Release build validated with the full Windows installer workflow:
  `473 passed, 2 warnings`, strict tool checks, packaged CLI/C2PA/AMaZE smoke
  checks and `rawpy-demosaic 0.10.1`.

## [0.3.19] - 2026-05-11

### Added

- Added macOS packaging under `packaging/macos/` with a PyInstaller spec,
  GUI/CLI launchers and `build_app.sh` to generate `ProbRAW.app`, a packaged
  CLI, zip and SHA-256 from a macOS host.
- Added the optional `macos` extra to install GUI build, PyInstaller and C2PA
  dependencies through one selector.
- Documented the macOS install/build flow, artifact validation, AMaZE variables,
  optional signing and Python 3.11/3.12 recommendations.
- Added native Arch/CachyOS packaging with `PKGBUILD`,
  `packaging/arch/build_pkg.sh`, installation under `/opt/probraw/venv`,
  `probraw`/`probraw-ui` launchers, `validate_cachyos_install.sh` validation
  and optimized AMaZE build support.
- Added `probraw check-color-environment` to audit the display-profile provider,
  LittleCMS2, ArgyllCMS, Qt/PySide, colord, KWin/Wayland and system standard
  ICC profiles.
- Documented system color management for Linux/Windows/macOS and the CMM
  contract: LittleCMS2 for preview, ArgyllCMS for creation, validation and
  derived conversions.
- Added first-preview load progress and timing estimates for slower RAW opens.
- Added regression coverage for preview loading, provisional RAW orientation,
  MTF behavior and pending sidecar geometry writes.

### Changed

- The update asset selector now prefers `.dmg`, `.pkg` and `.zip` on macOS
  before source tarballs.
- Shell scripts are normalized to LF through `.gitattributes` to avoid problems
  when preparing macOS builds from Windows.
- Generic sRGB, Adobe RGB and ProPhoto RGB profile discovery now uses
  XDG/colord/ArgyllCMS/Homebrew system paths and validates ICC descriptions to
  avoid selecting linear ProPhoto as gamma 1.8 ProPhoto RGB.
- ICC profile preview now uses LittleCMS2 through Pillow `ImageCms`;
  `xicclu`/`icclu` remain for generated ICC validation and `cctiff` for derived
  exports.
- ICC selection dialogs now start in system profile directories when no previous
  path is available.
- The `rawpy-demosaic` build adapts to current toolchains with a minimum CMake
  policy, `Cython>=3.1`, `numpy` and `np.set_array_base`.
- RAW preview loading can show a correctly oriented provisional embedded
  preview while the full render is prepared.
- Viewer crop, rotation and leveling sidecar writes are flushed before file
  changes so geometry is not lost during fast navigation.
- Display cache and preview cache handling avoid unnecessary rebuilds while
  keeping final TIFF rendering and ProbRAW Proof output reproducible.

### Tests

- Validated with `bash -n packaging/macos/build_app.sh`, `python -m compileall`,
  macOS spec syntax checking and `pytest` for docs/update/external coverage.
- Validated on CachyOS with installed package `probraw 0.3.18-3`: `pacman -Qkk`
  with no altered files, `validate_cachyos_install.sh`, `check-tools --strict`,
  `check-amaze` and offscreen `probraw-ui` smoke.
- Windows release build: `465 passed, 2 warnings`, `check-tools --strict`,
  packaged CLI `--version`/`--help`, packaged `check-tools --strict`, C2PA and
  AMaZE smoke checks.

## [0.3.18] - 2026-05-07

### Fixed

- Undo/redo of viewer-only crop or leveling geometry no longer forces a final
  preview rebuild. This avoids an apparent hang when going back immediately
  after recropping a large RAW preview.

### Tests

- Full suite: `439 passed, 2 warnings`.
- Added regression coverage for crop-only undo avoiding preview refresh.

## [0.3.17] - 2026-05-07

### Changed

- Reused lateral chromatic-aberration remap coordinates during repeated preview
  edits to reduce large per-frame allocations.
- Reduced temporary allocations in preview vibrance/saturation adjustments.
- Rate-limited demosaic cache pruning after cache writes to avoid repeated
  directory scans in batch sessions.
- Reduced temporary allocations in local false-color suppression without
  changing canonical regression hashes.

### Tests

- Full suite: `438 passed, 2 warnings`.
- Regression hashes: `2 passed`.
- GUI benchmark smoke: `scripts/benchmark_gui_interaction.py --synthetic-size
  900x1350 --steps 8`.

## [0.3.16] - 2026-05-07

### Added

- Added TIFF compression choices for final exports: none, ZIP/Deflate, LZW,
  JPEG and ZSTD, backed by `imagecodecs`.
- Added bounded TIFF compression worker controls in GUI, CLI
  (`--tiff-workers`) and `PROBRAW_TIFF_MAXWORKERS`.
- Added draggable horizontal/vertical leveling lines with live angle feedback.
- Added a folder-tree context action to open directories in the system file
  browser.
- Added per-file render progress bars to the queue table.

### Changed

- Compressed batch TIFF export now distributes compression threads across active
  batch workers to avoid oversubscribing CPU cores.
- TIFF compression metadata is recorded in render settings/Proof context.

### Fixed

- Leveling export crops the valid rotated image area so black canvas borders are
  not written into final TIFFs.
- ArgyllCMS output conversions are recompressed after `cctiff` when a TIFF
  compression mode is selected.

### Tests

- Full suite: `438 passed, 2 warnings`.
- Added regression coverage for TIFF codecs, TIFF compression worker dispatch,
  draggable leveling, export border cropping, folder-tree open action and queue
  progress bars.

## [0.3.15] - 2026-05-06

### Added

- Added `scripts/check_performance_regression.py` to compare stored benchmark
  JSON files and fail on configured regressions.
- Added profile-generation worker/artifact controls for CLI workflows.

### Changed

- Chart sampling now builds local patch masks instead of full-frame masks.
- MTF edge-spread distance grids allocate less temporary memory.
- Preview disk cache can reuse reduced pyramid levels while limiting the number
  written synchronously.
- Batch worker auto-selection now considers capture size, demosaic algorithm and
  a conservative floor for compressed RAW files.
- Temperature/tint preview multipliers are now derived from CCT chromaticity and
  linear sRGB white ratios instead of the previous heuristic.
- GUI profile generation defaults to a single worker to avoid implicit heavy
  process spawning from Qt on Windows.

### Fixed

- Exported TIFFs now apply visual crop and leveling geometry in the render path.
- Multi-file GUI batch exports no longer apply the currently selected image's
  crop/leveling geometry to every file.
- Export crop rounding now matches the viewer's floor/ceil behavior.
- Removed the experimental 8-bit LittleCMS/Pillow TIFF16 export path; ICC output
  conversion remains on ArgyllCMS `cctiff` to preserve tonal precision.
- RAW SHA-256 caching can be disabled with `PROBRAW_RAW_SHA_CACHE=0` for strict
  rehashing in audit workflows.

### Tests

- Full suite: `426 passed, 2 warnings`.
- Added regression coverage for export geometry, batch geometry policy, preview
  pyramid selection, RAW SHA strict mode and 16-bit ICC export precision policy.

## [0.3.14] - 2026-05-06

### Added

- New `Edit` menu with undo, redo, clear adjustments and `Ctrl+Z`/`Ctrl+Y`
  shortcuts for development, render, detail, crop and visual leveling state.
- New `Image adjustments` tools for visual crop selection, horizontal or
  vertical leveling from a reference line, and clearing crop/leveling.

### Changed

- Interactive preview keeps the current performance/accuracy balance: it uses
  bounded sources during drags, preserves exact refreshes once interaction
  settles, and updates sampled histogram/levels data in real time when the
  throttle allows it.
- The tone-curve editor keeps its histogram visible during drag, and `Curve
  black`/`Curve white` refresh levels without blocking the UI.
- The viewer supports visual crop, fractional leveling rotation and crop
  reprojection when preview resolution changes or real-pixel view is requested.

### Fixed

- The MTF analysis ROI remains visible after applying a visual crop.
- 100% zoom after crop keeps real-pixel correspondence and avoids unnecessary
  full-frame rebuilds.
- The update downloader skips metadata assets and fails closed if it cannot
  verify the installer SHA-256.

### Tests

- Full suite: `414 passed, 2 warnings`.
- Added regression coverage for crop, leveling, undo/redo, interactive
  histograms, tone-curve drag behavior and SHA-256 verified updates.

## [0.3.13] - 2026-05-05

### Fixed

- Fixed a levels/tone-curve histogram inconsistency in 0.3.12: the tone-curve
  editor now plots the image data entering the curve, not the output already
  clipped by the curve black/white range.
- The full-image RGB clipping histogram is now marked as updating while exact
  real-pixel metrics are recalculated, preventing stale `L 0.00%`/`S 0.00%`
  readings from being mistaken for the current levels state.

### Tests

- Added regression coverage for curve input histograms, curve white-point
  clipping, and pending exact-histogram state.

## [0.3.12] - 2026-05-05

### Added

- The update checker now opens a guided assistant showing current version,
  latest release, detected installer, size, release page and SHA-256
  verification availability before starting the download.

### Changed

- GUI updates now download the installer to a recognizable user folder, verify
  SHA-256 when the release publishes it, and open the installer visibly instead
  of launching it as a silent process.
- Interactive preview recovers the 0.3.8-style cadence by throttling drag-time
  refreshes to 65 ms and using bounded profile-preview sources below 1:1 view.
- The exact full-image histogram, tone-curve histogram and final preview remain
  deferred until interaction settles, preserving real-pixel accuracy without
  saturating the UI event loop.

## [0.3.11] - 2026-05-05

### Changed

- Interactive preview restores a responsive bounded-cache path for color,
  contrast, curves and sharpness adjustments while keeping the exact real-pixel
  path when the user works at 100% or requests detail.
- Automatic MTF refresh during sharpness drags now uses throttling instead of
  debouncing: when the full-resolution ROI is already hot, ESF/LSF/MTF plots
  update during movement without waiting for slider release.
- The sRGB OETF conversion is documented and constrained to explicit
  `tone_curve: srgb`; it is not part of ICC-managed display.

### Fixed

- Cached or reduced RAW previews are no longer treated as real pixels during
  1:1 inspection, avoiding sharpness analysis on a proxy version.
- Zoom and viewport changes refresh the visible region with active adjustments,
  so the whole visible image keeps coherent color/contrast/sharpness while
  navigating.
- Color documentation consolidates that ProbRAW uses input ICC profiles and
  displays through direct conversion to the system monitor profile, with no
  mandatory intermediate conversion to sRGB.

## [0.3.10] - 2026-05-04

### Added

- ICC-managed preview now maintains a dense 8-bit RGB LUT cache for each
  `image profile -> monitor profile` pair, generated with LittleCMS and
  persisted on disk, to speed up repeated visible renders without changing the
  colorimetric result.
- The GUI benchmark now measures real 100% interactions, clipping overlay,
  monitor ICC management, window size and the effective color-managed recipe.

### Changed

- The preview path now requires every image to have an input profile: the
  session/image ICC when available, or a real generic ProPhoto/sRGB/Adobe RGB
  profile when no specific ICC exists.
- Interactive adjustments update only the visible 100% crop when possible,
  reuse QImage regions and avoid full-frame recomputation for sliders, curves
  and clipping indicators.
- Tone curves reuse normalized LUTs and share RGB quantization before the ICC
  conversions needed for the display and instruments.
- Automatic interactive worker selection considers CPU, RAM and local timings so
  workstation hardware is used without freezing the GUI.
- 1:1 zoom remains aligned to real pixels, but no longer forces the viewer back
  to 100% when the user magnifies above that scale.

### Fixed

- Profiled preview no longer passes through standard sRGB routes when an input
  profile exists; visible conversion is direct `source ICC -> monitor ICC`.
- Cache buttons distinguish between caching the selected image at 1:1 and
  caching the visible directory, avoiding always processing every image.
- Histogram and clipping overlay now update from the correct colorimetric
  signal, without mixing the monitor conversion or unnormalised `uint8` buffers.
- Color/contrast adjustments no longer trigger unnecessary MTF recalculation;
  sharpness analysis still uses real-resolution data when analysis is requested.
- Image load/switching invalidates the source profile associated with cached
  previews so stale ICC state is not reused.

## [0.3.9] - 2026-05-03

### Added

- Lateral chromatic-aberration analysis now reuses the selected slanted-edge
  ROI and displays RGB edge-profile differences, CA area, channel shifts and a
  nearest-neighbour pixel strip for scientific inspection.

### Changed

- ESF and MTF plots are easier to read: ESF focuses on the local edge window
  with a pixel-tone strip, and MTF shows clearer cycles/pixel scales plus
  MTF50/MTF30/MTF10 reference levels.
- MTF/CA analysis classes and helpers now include focused annotations and
  sectioning to make future team development safer.

## [0.3.8] - 2026-05-03

### Changed

- RAW preview keeps the exact render path shared with export, while adding a
  persistent demosaic cache to speed up reloads, exact refinements and later
  renders without changing color routing or the effective recipe.
- Single-image export, batch export and the development queue reuse that
  demosaic cache when applicable, reducing repeated work on large RAW files
  while preserving original-recipe traceability.

### Fixed

- Preview again matches the rendered TIFF in color-managed applications by
  avoiding alternate display paths that could hide color casts or chromatic
  adjustments visible in the exported file.
- Development queue items are removed automatically after successful rendering,
  preventing accidental reprocessing; failed items stay in the queue with their
  error message for correction or retry.

## [0.3.7] - 2026-05-03

### Added

- The Color and Contrast tab now provides a broader manual adjustment workflow:
  white balance first, light/contrast controls, saturation, vibrance and color
  grading separated from ICC calibration.
- The viewer renders magnified images without interpolation at real pixel scale
  and draws a pixel grid at analysis magnifications for scientific inspection
  of the digital data.
- ESF/LSF/MTF plots now show ROI context, sample counts, gradual pixel scale
  and MTF50/MTF50P metrics inspired by slanted-edge analysis workflows.

### Changed

- Visible preview and exported TIFF now share the same effective recipe and the
  same image-ICC to monitor/output path, preventing chromatic adjustments from
  appearing only after opening the TIFF in another color-managed application.
- Zoom preserves the current visible center when magnifying, so the inspected
  area remains in view.
- Auto Sharpness now uses MTF50P, halo and post-Nyquist energy metrics to
  penalize oversharpened peaks and prefer more stable results.
- Chart-generated ICC profiles no longer carry visible color, contrast or
  detail adjustments: ICC calibration and manual adjustments stay separate.

### Fixed

- Automatic MTF recalculation stops when leaving Sharpness and is deferred until
  that tab is opened again, so chromatic adjustments no longer pay the ROI/MTF
  cost in the background.
- Generic ICC space selection avoids duplicate preview reloads and normalizes
  legacy ProPhoto/sRGB profiles toward camera white balance and non-profiling
  mode when there is no input ICC.
- The top progress bar now tracks slow interactive adjustments instead of
  relying on subtle lower indicators for operations lasting more than one
  second.

## [0.3.6] - 2026-05-02

### Added

- Separate project-scoped adjustment profiles for color/contrast, sharpness and
  RAW export settings, with save, apply, copy and paste workflows per image.
- RAW sidecars now record the specific ICC, color/contrast, sharpness and RAW
  export profile identifiers applied to each file for clearer reproducibility.
- RAW thumbnails show a discreet lower badge strip for applied ICC,
  color/contrast, sharpness and RAW export profiles.
- The Color/Calibration workflow now starts with an ICC choice between generic
  standard output profiles, existing camera ICC profiles and chart-based ICC
  generation, followed by status for the selected image and session.
- The existing-ICC choice now states when the project has no saved ICC profiles
  and keeps system camera ICC loading available as the fallback.
- The RAW panel now exposes algorithm-dependent demosaic options (4-color
  interpolation, edge quality and false-color suppression) and records those
  capabilities in recipes when the LibRaw/rawpy backend supports them.
- RAW false-color suppression now has a local chroma-only postprocess that
  preserves luminance when the LibRaw/rawpy backend does not expose
  `median_filter_passes`, allowing it to be used with AMaZE.

### Changed

- GUI preview now applies display color management with a direct
  `image ICC -> monitor ICC` conversion whenever a source profile exists,
  keeping sRGB only as a technical histogram/diagnostic signal or fallback.
- Activating a session ICC now forces preview development into linear camera
  RGB and reloads the RAW source, preventing a camera ICC from being applied to
  pixels already developed into ProPhoto/sRGB.
- RAW / export no longer presents output-profile, curve, exposure, noise or
  contrast decisions: the panel is limited to RAW read/demosaic controls and
  black points, while ICC management remains in Color/Calibration.
- RAW export profiles now save and apply only RAW parameters (engine,
  algorithm, demosaic options and black level), without overwriting chromatic
  adjustments or the image ICC decision.
- RAW edits are now written automatically to the selected image sidecar and
  activate the RAW thumbnail badge even before a named RAW profile is saved;
  the redundant RAW Profiles accordion is hidden from the UI.
- The RAW "Edge quality" control is now labeled as "Border" and behaves like
  RawTherapee's border control: it crops peripheral pixels after demosaicing
  instead of being mapped to DCB iterations.
- The tone-curve editor now shows only the active red, green or blue channel
  histogram when editing that channel, colors the active curve accordingly and
  keeps adjusted RGB curves visible with a global luminance reference.
- Documentation and the user manual now reflect the current ICC workflow,
  independent profile categories, thumbnail markers, RGB curves and RAW panel
  limited to reading/demosaicing.

### Fixed

- Packaged Windows MTF ROI preparation now launches the internal CLI worker
  instead of reopening the GUI executable, so selecting an MTF area completes
  without spawning a second ProbRAW window.
- Contrast curves no longer force a final ICC preview at full resolution on the
  main thread: the interactive source is cached at reduced size and heavy final
  preview runs in an asynchronous worker.
- Interactive preview now has a watchdog: if an ICC worker gets stuck, that task
  is abandoned, the warning is logged and the adjustment queue can continue.
- The tone-curve editor histogram now updates from the image after prior
  color/exposure/contrast adjustments, without applying the curve itself, so the
  displayed levels match the current working state.
- Color/contrast adjustments are now written automatically to the selected RAW
  sidecar while controls are moved, refresh the chromatic thumbnail indicator
  and make the render queue prefer that sidecar over a queued profile snapshot.
- The tone-curve editor histogram now updates in real time with the curve
  applied and displays RGB columns in addition to luminance.
- The thumbnail context menu can now copy all applied adjustments or only ICC,
  color/contrast, sharpness or RAW/export settings, then paste them onto one or
  multiple selected images without overwriting unrelated categories.
- Auto sharpness and the detail controls now write sharpness, radius, noise and
  CA into the selected RAW sidecar in real time, refreshing the sharpness badge
  and keeping final TIFF output aligned with the visible adjustment.

### Known Issues

- The stricter colorimetric path remains more expensive than embedded preview.
  Reduced ICC transform caching by profile/recipe is still pending to improve
  continuous drags without relaxing color correctness.

## [0.3.5] - 2026-05-02

### Added

- Global long-operation progress viewer for RAW preview loading, MTF ROI
  preparation and background tasks, with elapsed time, estimated duration,
  remaining time and phase.
- Persistent full-resolution MTF ROI cache prepared by an external worker
  process, so cold RAW analysis does not block the Qt UI thread.
- Performance documentation with real NEF timings, implementation decision,
  alternatives evaluated and references to Imatest, rawpy, LibRaw and darktable.

### Changed

- Cold MTF recalculation now starts explicitly when the full-resolution ROI cache
  is cold; automatic refreshes use hot ROI data and no longer launch expensive
  RAW work during slider interaction.
- The `Nitidez` tab no longer duplicates the local progress panel; long analysis
  status is reported from the always-visible global bar.
- RAW preview loading publishes global progress when a load is expected or
  observed to take roughly more than one second.

### Fixed

- Batch rendering now uses each RAW backpack when there is no registered
  development-profile id, so sharpening, denoise, chromatic aberration, color
  and contrast settings reach the rendered TIFF instead of leaking from the
  current sliders.
- Selecting an unconfigured image resets recipe, detail, color, contrast and
  active ICC controls to the neutral ProPhoto/camera-WB policy instead of
  carrying adjustments from the previous file.
- Generic no-chart output spaces disable profiling mode and identity fixed white
  balance for visible/final rendering, keeping preview and TIFF color policy
  aligned.
- Camera RGB output without an active input ICC is rejected before writing a
  TIFF, preventing green/dark files in external viewers.

## [0.3.4] - 2026-05-01

### Added

- The `Nitidez` tab now includes persistent slanted-edge MTF analysis with
  `ESF`, `LSF` and `MTF` curves saved in each RAW sidecar.
- Saved MTF measurements can be compared visually from two selected thumbnails,
  with overlaid `ESF`, `LSF` and `MTF` curves plus the numeric metric table.
- User manuals now document the sharpness-analysis workflow, persisted curves
  and how ProbRAW maps viewer ROI coordinates to analysis coordinates.

### Changed

- MTF recalculation loads the selected source at full resolution and maps the
  viewer ROI onto that real analysis image, avoiding measurements on thumbnails
  or reduced previews.
- Pixel-pitch and lp/mm reporting now use the analysis image dimensions, EXIF
  metadata or the manual sensor-size controls instead of downscaled preview
  dimensions.
- The English Qt translation catalog was regenerated and completed for the new
  session, color, chart, histogram and MTF controls.

### Fixed

- Reopening an image with saved MTF data restores the ROI and curves without
  requiring the edge to be selected again, including when the current preview
  size differs from the one used when the measurement was saved.
- Updating MTF data in a RAW sidecar preserves existing development settings and
  output history.

## [0.3.3] - 2026-04-30

### Added

- The `1. Sesión` tab now shows active-session statistics: RAW images, derived
  TIFFs, ICC profiles, development profiles, RAW sidecars and queued items.
- Direct access to recent sessions from the session tab.
- The `Carta` diagnostics tab can reload patch data from saved
  `profile_report.json` files and restores it automatically when a session is
  opened.
- The advanced tone curve supports per-channel editing: luminance, red, green
  and blue.
- New viewer-focus button to hide/restore side columns with one click.

### Changed

- The third column in `2. Ajustar / Aplicar` is reorganized into three workflow
  tabs: `Color / calibración`, `Ajustes personalizados` and `RAW / exportación`.
- The vertical `Visor` tab was removed from the left pane: compare, zoom,
  rotate, fit, cache and ICC-preview controls now live in a compact horizontal
  toolbar above the central viewer.
- The histogram is always visible in the `Ajustes personalizados` header.
- Histogram and clipping overlay now read the colorimetric preview signal before
  monitor ICC conversion; monitor conversion remains the final display-only
  layer.
- User manuals and screenshots were updated for the new interface flow and color
  management policy.

### Fixed

- The `Gamut 3D` viewer now resets camera and zoom when the profile pair or Lab
  mesh changes, avoiding a previous high-elevation view making the gamut look
  stretched until the application is restarted.
- Reopening a session with generated profiles no longer leaves the `Carta` tab
  at `Sin datos de carta` when a profile report with per-patch errors exists.

## [0.3.2] - 2026-04-29

### Fixed

- The Linux desktop entry now uses the absolute pixmap
  `/usr/share/pixmaps/probraw.png` so Cinnamon and other menus show the ProbRAW
  icon even when they do not refresh the hicolor theme lookup correctly.
- Updated package and installation validations to check the real menu icon.

## [0.3.1] - 2026-04-29

### Changed

- Replaced the previous visual identity with a new ProbRAW logo and icon built
  around a `P` mark, RAW geometry and color calibration patches.
- Regenerated the SVG, PNG and ICO assets used by README, the application,
  Linux/Windows installers and distributable packages.

## [0.3.0] - 2026-04-29

### Changed

- Renamed the project and visible application identity to ProbRAW to avoid brand
  collision with existing projects.
- Renamed the Python package, CLI launchers, desktop files, icons, screenshots
  and release artifacts to the canonical `probraw` naming.
- Updated repository, installer and update metadata to point to
  `alejandro-probatia/ProbRAW`.
- Declared project leadership by Probatia Forensics SL
  (https://probatia.com) in collaboration with the Asociación Española de Imagen
  Científica y Forense (https://imagencientifica.es).

### Compatibility

- New RAW sidecars are written as `RAW.probraw.json`, while existing
  `RAW.nexoraw.json` and `RAW.iccraw.json` files are still loaded and migrated
  when the session is saved again.
- New proof sidecars are written as `.probraw.proof.json`, while legacy
  `.nexoraw.proof.json` and `.iccraw.proof.json` files remain readable.
- C2PA and Proof verification accept previous beta assertion labels and
  environment variables as migration fallbacks.
- Linux packages now declare `Replaces/Conflicts: nexoraw, iccraw` and do not
  install legacy launchers.

## [0.2.6] - 2026-04-29

### Added

- `Gamut 3D` diagnostics tab for pairwise comparison between the session ICC,
  monitor profile, standard profiles (`sRGB`, `Adobe RGB (1998)`, `ProPhoto RGB`)
  and external ICC files.
- Persistent session ICC profile catalog with explicit activation, support for
  multiple generated versions and reload from `session.json`.
- Chart reference management from the interface: bundled reference catalog,
  external JSON import, custom session references and validation.
- Lab table editor with per-patch color swatches to create custom chart JSON
  references without editing the file manually.

### Changed

- Advanced profiling now records versioned artifacts under
  `00_configuraciones/profile_runs/` and keeps generated ICC profiles under
  `00_configuraciones/profiles/`.
- GUI profile generation runs in the background to avoid leaving the application
  blocked for a long time while an ICC is created.
- Default ArgyllCMS arguments include `-u -R` to reduce clearly unrealistic
  camera ICC gamuts.
- User manual and screenshots updated for reference management, session ICC
  profiles and pairwise 3D gamut comparison.

## [0.2.5] - 2026-04-29

### Changed

- Reorganized the codebase around the canonical `probraw` package and removed
  the old internal `iccraw` implementation namespace.
- Split the GUI into smaller UI/window modules to make session, preview,
  profile and batch workflows easier to maintain.
- Updated tests, scripts, installers and active documentation to use the
  `probraw` package and launcher names consistently.
- New C2PA outputs now use `org.probatia.probraw.*` assertion/action labels;
  verification keeps compatibility with earlier beta `org.probatia.iccraw.*`
  manifests.

## [0.2.4] - 2026-04-28

### Added

- Interface language selector in `Global settings -> General`, with options
  `System (Auto: es/en)`, `Spanish` and `English`. Persisted in `QSettings`
  under `app/language`.
- Automatic detection of the operating system language for new installations:
  if the OS is in Spanish the app starts in Spanish, in any other language it
  starts in English. Existing users with `app/language=es` already stored are
  not migrated, preserving their previous choice.
- Helpers `probraw.i18n.detect_system_language` and `probraw.i18n.resolve_language`
  with unit tests in `tests/test_i18n.py`.

### Changed

- Switching the language from the settings dialog no longer restarts the
  application automatically: a notice is shown and the change applies on the
  next launch, avoiding loss of unsaved session state.

## [0.2.3] - 2026-04-27

### Changed

- The flow without chart stops generating profiles `ProbRAW generic ...`: the RAW is
  reveals in a real standard RGB space (`sRGB`, `Adobe RGB (1998)` or
  `ProPhoto RGB`) with LibRaw and embed a standard ICC copied from the system or
  by ArgyllCMS.
- The render manifests register `raw_color_pipeline`, indicating whether the
  color transformation was solved by LibRaw, session ICC or ArgyllCMS/CMM.
- ProbRAW Proof/C2PA declare the full settings applied (`recipe`,
  detail/sharpness, contrast/render and color management); the settings hash
  It remains as an integrity control, not as the only visible data for audit.

### Added

- Real standard profile tests to prevent Adobe RGB from falling into a
  compatible profile when `AdobeRGB1998.icc` exists.

## [0.2.2] - 2026-04-27

### Added

- `scripts/profile_pipeline.py` to profile real commands with `cProfile`
  and, if installed, generate flamegraphs with `py-spy`.
- `scripts/benchmark_raw_pipeline.py` for cross-platform benchmark
  demosaic, numerical cache and process scaling with real RAWs.
- `scripts/benchmark_gui_interaction.py` to measure slider fluidity and curve
  tonal in Qt with real RAW or synthetic source.
- Flags `--workers` in `batch-develop` and `auto-profile-batch` to set the
  parallelism without depending on environment variables.
- Flag `--cache-dir` in `develop`, `batch-develop` and `auto-profile-batch` for
  locate the numerical cache of the demosaic when the recipe activates
  `use_cache: true`.
- Persistent RAW demo cache on `.npy` arrays, opt-in by recipe,
  with key based on SHA-256 complete RAW and LibRaw parameters that affect
  to the linear scene.
- Golden tests of canonical hashes in `tests/regression/` and script
  `scripts/regenerate_golden_hashes.py` to regenerate them explicitly.

### Changed

- GUI preview and histogram analysis samples before converting and
  Trim large arrays, reducing memory copies into 1:1 images.
- `batch-develop` uses real per-process multiprocessing when `workers > 1`;
  preserves fallback to threads only if a non-serializable C2PA client is injected.
- New projects have `00_configuraciones/cache/` as a location
  persistent cache per session.
- The automatic estimation of RAM per batch worker goes to 2800 MiB for
  reflect high resolution RAWs and real TIFF writing.
- `write_tiff16` reduces NumPy temporals using `out=` operations, lowering
  time and RAM peak during TIFF16 writing.
- The final preview refresh after dragging sliders/curve is queued in
  background for large images when there is no ICC preview active,
  avoiding noticeable Qt thread locks.

### Fixed

- The basic calls to `exiftool` and `git rev-parse` used for metadata and
  execution context have timeout to avoid indefinite locks.

## [0.2.1] - 2026-04-27

### Added

- `Ayuda > Acerca de` GUI expanded with:
  - configurable project manager (`PROBRAW_PROJECT_DIRECTOR`),
  - running version,
  - AMaZE operational status,
  - checking the latest version published in GitHub Releases,
  - automatic update that downloads and launches the release installer.
- New module `probraw.update` for querying releases, comparing
  versions, downloading assets and executing installers by platform.
- RGB histogram in the `Visor` tab with clipping reading in shadows and
  lights and visual witnesses.
- Clipping overlay on the preview image (blue shadows, red lights,
  magenta when they match), activatable from `Visor`.
- Unit tests for the update system (`tests/test_update.py`).

### Changed

- Windows script `packaging/windows/build_installer.ps1` requires AMaZE for
  default for release builds (explicit escape: `-AllowNoAmaze` for builds
  test).

## [0.2.0] - 2026-04-26

### Added

- User manual aimed at installers and GUI flows, with screenshots
  updated for session, flow with letter, flow without letter, backpacks,
  development queue, metadata and global configuration.
- Documented flow for non-chart sessions: manual development profile with ICC
  generic output (`sRGB`, `Adobe RGB (1998)` or `ProPhoto RGB`) and backpack
  `RAW.probraw.json` per image.
- Debian package release `0.2.0`, installable as a ProbRAW application with
  `probraw`/`probraw-ui` launchers, hicolor icons and AMaZE validated in build.

### Changed

- The manual stops explaining installation from code and manual dependencies;
  user installation is considered covered by installers
  multiplatform.
- The GUI treats profiles as settings assigned to RAW: advanced profile from
  letter marked in blue and basic/manual profile marked in green, both
  copyable and pasteable from thumbnails.
- The right column of `2. Ajustar / Aplicar` leaves the model
  "calibrate session" and groups the parameter settings per file in
  `Brillo y contraste`, `Color`, `Nitidez`, `Gestión de color y calibración` and
  `RAW Global`.
- The thumbnail strip works as a horizontal scroll with adjustable size and
  generates visual thumbnails for RAW even if there is no embedded preview,
  using a rapid cached development.
- Removed the persistent header with name/subtitle from the application to
  recover vertical work space.
- The choice of project directory is more reactive: the tree monitors changes
  system, a project root opens `01_ORG/` to browse RAW and
  `Usar carpeta actual` promotes `01_ORG/` to its project root.
- The structure of new projects is simplified to `00_configuraciones/`,
  `01_ORG/` and `02_DRV/`; legacy sessions with `config/session.json`
  They continue to open without destructive conversion.

### Fixed

- GUI: creating or opening a new session no longer inherits routes, thumbnails, queue or
  development profiles from the previous session; routes persisted outside the
  project root are migrated to the session's own structure.
- GUI: thumbnails and selections that still point to inherited routes
  `raw/archivo` automatically resolve against `01_ORG/archivo`, avoiding
  tracebacks when opening migrated projects.
- GUI: when generating a profile from a menu, the advanced profile is assigned to the
  RAW card using your `RAW.probraw.json` backpack.

## [0.1.0-beta.5] - 2026-04-25

### Changed

- The visible name of the project becomes ProbRAW. Entry points
  `probraw`/`probraw-ui` are added, with temporary legacy aliases for existing
  beta scripts. Those aliases are removed in 0.2.5.
- Unified CMM in ArgyllCMS: LittleCMS (`tificc`) is replaced by
  `cctiff`/`xicclu` for output ICC conversion, validation and preview of
  profile. The dependencies `liblcms2-utils` and `Pillow.ImageCms` disappear from the
  main flow.
- `apply_profile_preview` rebuilds the ICC preview from a
  LUT 17^3 calculated with `xicclu` and trilinear interpolation cached by
  profile; dependency on sidecar `.profile.json` to display is removed
  preview with active profile.
- `build_profile` reports DeltaE 76/2000 from the actual ICC generated by
  `colprof` (referring to `xicclu`). The lateral matrix
  `matrix_camera_to_xyz` is kept for diagnostic purposes only
  (`diagnostic_matrix_*`).
- `auto_generate_profile_from_charts` applies a strict scientific guard:
  rejects recipes with active `denoise`, `sharpen` or `tone_curve`, or with
  `output_linear=False` or `output_space` other than linear camera RGB.
- Card captures for profiling are restricted to linear RAW/DNG/TIFF;
  PNG/JPG are no longer accepted in either the CLI or GUI.
- Array-first refactor of the profiling workflow: `_collect_chart_samples` and
  `_collect_chart_geometries` use `develop_image_array` and variants
  `detect_chart_from_array` / `sample_chart_from_array` /
  `draw_detection_overlay_array`, avoiding roundtrips to TIFF.
- Windows installer packages `tools/argyll/ref/` (including `sRGB.icm`)
  so that the ICC conversion works without external profiles. It eliminates the
  copy of LittleCMS binaries and metadata.
- Debian package: `liblcms2-utils` is removed from declared dependencies.
- `probraw check-tools` requires `cctiff` (ArgyllCMS) instead of `tificc`.

### Fixed

- GUI: Tone curve editor histogram is recalculated only when
  changes the base image, avoiding recomputations with each curve movement.
- GUI: manual marking of four card corners survives reloads
  asynchronous images of the selected image.
- GUI: preview with ICC profile no longer requires `*.profile.json`
  associate; a `xicclu` fault is logged as a warning and is dropped to view without
  profile without blocking the viewer.

## [0.1.0-beta.4] - 2026-04-25

### Changed

- Windows AMaZE installer includes distribution metadata
  `rawpy-demosaic` inside the PyInstaller executable so that
  `probraw check-amaze` report the exact backend.
- Windows packaging copies notices/licenses from `rawpy-demosaic`, LibRaw,
  the GPL2/GPL3 and RawSpeed demosaic packs, along with wheel hash and commit
  source.

### Fixed

- AMaZE operational support on Windows via GPL3 wheel
  `rawpy-demosaic 0.10.1` linked to LibRaw 0.18.7 with
  `DEMOSAIC_PACK_GPL3=True`.

## [0.1.0-beta.3] - 2026-04-25

### Added

- `develop_image_array` function for RAW/TIFF array-first render and benchmark
  basic preview/render in `scripts/benchmark_pipeline.py`.
- `scripts/check_amaze_support.py` script to audit whether the LibRaw/rawpy environment
  includes the GPL3 demosaic pack necessary for AMaZE.
- Prepared the Windows packaging flow with PowerShell scripts,
  PyInstaller, Inno Setup template and testing documentation.

### Changed

- High quality preview, batch export and GUI development paths avoid
  Temporary TIFFs when not needed.
- The RAW preview in RGB/profiled camera mode applies a visual normalization
  for the viewer only, avoiding green casts when marking unaltered cards
  Audited TIFFs, sampling or export.
- The ICC generation options (`colprof`, quality, format and output) and the
  `RAW global` criteria are displayed within `Calibrar sesion`, before
  start calibration.
- Documented AMaZE/GPL3 policy: ProbRAW maintains `AGPL-3.0-or-later`, registers
  flags of `rawpy` and only enables AMaZE when `DEMOSAIC_PACK_GPL3=True`.
- Windows installer packages complete flow external tools
  (`colprof`/`xicclu`, `exiftool` and `tificc`) under `tools/`.
- GUI automatically loads preview when selecting thumbnails and
  Adds a top progress bar for long tasks.
- The viewfinder allows zooming, reframing by dragging and 90 degree rotation.
- New vertical processing panels: calibration with RAW criteria,
  basic correction, detail, active profile and session application.
- Basic preview/batch correction: final illuminant, temperature, hue,
  brightness, levels, contrast and midrange curve.
- Preview/batch detail adjustments: luminance/color noise reduction,
  sharpness and lateral chromatic aberration correction.

- The RAW backend completely moves from `dcraw` to LibRaw/rawpy, with DCB as
  demosaicing by default installable and AMaZE available only in builds of
  rawpy/LibRaw with demosaic pack GPL3.
- Redundant manual loading buttons on the viewer are removed; the selection of
  miniature becomes the main action.

### Fixed

- Support for ArgyllCMS on Windows when `colprof` generates `.icm` on
  instead of `.icc`.
- The RAW backend explicitly informs when a recipe calls for AMaZE without
  demosaic pack GPL3; the GUI avoids the crash by downgrading to `dcb` with warning.
- Profile generation from GUI automatically reuses the four
  pending manual corners, even if the JSON of
  manual detection.
- Sessions no longer restore temporary paths inherited from executions
  tests such as operational routes of letters, recipes, profiles or batch.
- The GUI persistent memory remembers last valid session/folder,
  ignore obsolete paths and use the user's home as the initial directory
  portable on Linux, macOS and Windows.

## [0.1.0-beta.2] - 2026-04-25

### Fixed

- ColorChecker 2005 D50 reference is packaged inside `probraw` and used
  as a fallback when the GUI/CLI is run from a `.deb` installation without the
  tree `testdata/` of the repository.

## [0.1.0-beta.1] - 2026-04-24

### Changed

- The GUI migrates routes inherited from `/tmp` to the session structure:
  profiles in `profiles/`, reports/recipes in `config/`, work in `work/`
  and TIFF/preview in `exports/`.
- `batch-develop` separates ICC management into explicit modes:
  - Camera RGB with embedded input ICC profile,
  - conversion to sRGB using LittleCMS (`tificc`) with embedded sRGB profile.
- The GUI reopens the last used session and positions the browser in the
  operating directory of the session instead of always booting to `$HOME`.
- `validate-profile` validates the actual ICC profile with ArgyllCMS (`xicclu`/`icclu`)
  instead of calculating DeltaE with the sidecar lateral matrix.
- Card detection by fallback is marked as `fallback` mode, with
  Low trust and default blocking in automatic flows.
- Chart sampling applies `sampling_trim_percent` and
  `sampling_reject_saturated` from the recipe.
- Letter references loaded from JSON are validated in strict mode
  (source, D50, observer 2 degrees, unique ids and full Lab).
- New `export-cgats` command to export samples to interoperable CGATS/CTI3.
- The `matrix_camera_to_xyz` matrix remains as a diagnostic/compatibility artifact,
  not as a substitute for the ICC conversion in batch export or the
  profile validation.
- The example recipes change from `demosaic_algorithm: rcd` to `ahd`, the mode
  supported by `dcraw`.
- The GUI stops offering demosaicing algorithms that the `dcraw` backend does not
  can execute.
- Structural reorganization of the project to grow as a single Python base:
  - removed Rust layer (`Cargo.toml`, `Cargo.lock`, `core/`, `cli/` Rust, `tests/` Rust) which was no longer used,
  - renamed package `icc_entrada` → `iccraw` aligned with repo and project name,
  - code organized in subpackages by domain: `core/`, `raw/`, `chart/`, `profile/`,
  - `__version__` centralized in `iccraw/version.py` and exposed by `__init__.py`,
  - CLI/GUI entry points renamed to `iccraw` and `iccraw-ui`,
  - `python -m iccraw` operational via `__main__.py`,
  - unified tests in `tests/` (previously `tests_py/`) with updated imports,
  - removed duplicate docs from root (canonical in `docs/`), absolute Linux
    paths replaced by relative paths in README.

### Added

- Debian beta package `0.1.0~beta1` with installation in `/opt/iccraw`,
  launchers `/usr/bin/iccraw` and `/usr/bin/iccraw-ui`, and external dependencies
  declared for `dcraw`, ArgyllCMS, LittleCMS and `exiftool`.
- `packaging/debian/build_deb.sh` reproducible script to build the `.deb`
  from the work tree.
- Strict validation of `demosaic_algorithm` for `dcraw` backend; a recipe
  with unsupported algorithm fails before processing.
- Integration of LittleCMS (`tificc`) as external CMM for ICC conversion to
  sRGB.
- Color management mode metadata in batch manifests.
- P0 tests for demosaicing not supported, `audit_linear_tiff` really linear and
  ICC/CMM export.
- P0 tests that demonstrate that `validate-profile` uses the real ICC even if it exists
  a sidecar with wrong matrix.
- P1 tests for low confidence fallback detection and controlled sampling
  recipe parameters.
- P1 tests for rejection of incomplete/incompatible letter references.
- P1 tests for CGATS/CTI3 export of samples.
- Session QA report includes worst DeltaE2000 patches and outliers by
  patch to diagnose localized chromatic deviations.
- The session QA incorporates capture diagnosis per card: luminance of
  patches, low level, densitometric dispersion of the neutral row and gradient
  lighting estimate.
- Session profiles declare operational status `draft`, `validated`,
  `rejected` or `expired`, with optional validity from CLI.
- `auto-profile-batch` does not apply to batch `rejected` or session profiles
  `expired`.
- New comparator of QA reports between sessions (`compare-qa-reports`) with
  status summary, DeltaE, outliers, new/resolved checks and access from
  the GUI.
- New diagnostic of external tools (`check-tools`) with JSON output and
  Access from GUI to check `dcraw`, ArgyllCMS, LittleCMS and `exiftool`.
- Continuous changelog maintenance template and update policy.
- `preview` module for image/RAW loading in preview, technical adjustments and linear analysis.
- New GUI based on Qt/PySide6 (`app-ui`, `app-ui-qt`) with:
  - technical preview with ICC profile,
  - sharpness and noise reduction adjustments,
  - auto flow executionmatic letter -> profile -> lot.
- Optional dependency `gui` on `pyproject.toml`.
- Script `scripts/run_ui_qt.sh`.
- Visual directory and RAW/image thumbnail browser integrated into GUI for key file selection.
- GUI action to reveal selected file to 16-bit TIFF with optional ICC profile.
- Separate noise adjustments in luminance and color.
- Top menu in GUI with access to configuration and operations (`Archivo`, `Configuracion`, `Perfil ICC`, `Vista`, `Ayuda`).
- Multi-drive browsing support in GUI to navigate the entire file system tree.
- Expanded RAW configuration panel (demosaic, WB, black/white level, tone curve, spaces, sampling, profiling mode).
- Extended ICC profile configuration panel (type `-a`, quality `-q`, extra args `colprof`, format `.icc/.icm`).
- RAW/DNG loading and preview optimization:
  - fast mode with embedded miniature or `dcraw -h` decoding,
  - configurable preview downscale to reduce latency in large files,
  - Preview cache per file+recipe for immediate reloads.
- New backend function `auto_generate_profile_from_charts` to generate ICC profile without executing batch.
- Functional reorganization in 3 main tabs:
  - ICC Profile Generation,
  - RAW development,
  - Flow Monitoring.
- Batch development integrated into the RAW Development tab (selection or complete directory).
- New module `session` for persistent session management with directory structure creation:
  - `charts/`, `raw/`, `profiles/`, `exports/`, `config/`, `work/`.
- New tab `1. Sesión` to create/open/save session with lighting and shooting metadata.
- New tab `3. Cola de Revelado` with file queue, status per image and batch execution from queue.
- Per-session state persistence in `config/session.json`:
  - operational routes,
  - development/profile settings,
  - active profile,
  - development queue.
- `tests_py/test_session.py` unit test for structure, loading and session normalization.

### Changed

- The previous GUI (tkinter) is completely replaced by a Qt implementation.
- `apply_profile_matrix` moved to public API in `icc_entrada.export` for reuse in preview.
- Documentation and roadmap updated to reflect Qt GUI and AGPL legal policy + dependencies.
- Redesign of GUI to a 3-panel layout (browser, main viewer, control panel) prioritizing image space and practical production flow.
- GUI reorganization for RAW developer type workflow (navigation, visual selection and maximum image space).
- Renamed visual settings tab from `Vista` to `Nitidez`.
- The profiling stream and the batch development stream are explicitly separated for operational clarity.
- The preview applies ICC profile deactivated by default to avoid dominants when the profile does not correspond to the active camera+lighting+recipe set.
- The Qt window saves/restores size and layout of panels to improve work on screens of different sizes.
- Reorganization of main tabs for session-centric flow:
  - `Sesión`,
  - `Revelado y Perfil ICC`,
  - `Cola de Revelado`.
- The working GUI is reorganized into two operational phases:
  - `1. Calibrar sesión`: card captures -> development profile + ICC,
  - `2. Aplicar sesión`: Target RAW/TIFF -> TIFF with calibrated recipe + ICC.
- Visible manual adjustment is limited to sharpness; exposure, density,
  White balance and colorimetric base come from the chart.
- Batch processing in GUI now tolerates per-file errors and returns `OK/errores` summary without aborting the entire batch.
- `auto_generate_profile_from_charts` accepts an explicit list of captures
  letter so that the GUI can use a selection of thumbnails instead of everything
  a directory.
- Session calibration tab hides internal artifact paths and
  redundant buttons; The generated profile is automatically activated along with
  your calibrated recipe.
- `Generar perfil de sesión` infers cards from miniature selection
  or from the uploaded file before resorting to the folder, avoiding searches
  accidentals in generic directories like `$HOME`.
- Manual detections saved from the GUI are associated with the RAW of
  letter and reuseized during session profile generation.
- `batch-develop` separates audit linear TIFFs into `_linear_audit/`
  so that they are not confused with the final inspection or delivery TIFFs.
- Automatic flow can reserve letter captures for hold-out validation,
  generate `qa_session_report.json` and classify the session as `validated`,
  `rejected` or `not_validated`.

### Docs

- Extended README with project objective, scope, limits and methodology
  applied to RAW flow -> letter -> development profile -> ICC -> batch.
- New document `docs/OPERATIVE_REVIEW_PLAN.md` with technical findings,
  acceptance criteria and professional phased plan to convert the
  prototype in operational and auditable pipeline.
- `ROADMAP.md`, `ISSUES.md`, `COLOR_PIPELINE.md` and `README.md` linked to
  operational plan and updated with P0-P3 priorities.
- Expanded legal policy for:
  - AGPL compatibility with non-commercial community objective,
  - ArgyllCMS, dcraw and PySide6 license notes,
  - redistribution and traceability obligations.
- New document `docs/THIRD_PARTY_LICENSES.md` with operational inventory of third-party licenses.
- Explicit warning in README and manual: current status is development and the application is not yet considered fully functional/validated for scientific or forensic production.

### Fixed

- `audit_linear_tiff` is written before exposure compensation and curves
  output, preserving the developed linear state.
- Quick RAW preview fix:
  - output `dcraw` for preview in sRGB space (`-o 1`) instead of native camera without conversion,
  - Embedded miniature to linear normalization to avoid double gamma correction.
- Safeguard in preview with ICC profile:
  - if sidecar `.profile.json` is missing or extreme clipping/dominance is detected, the view falls to profileless mode with a warning in the log.
- The generated calibrated recipe is immediately loaded into the GUI; the revealed
  later users can no longer be left using the base controls by accident.
- Quick preview based on lateral matrix adapts correctly
  from D50 to sRGB/D65 to avoid spurious yellow or greenish casts.

## [0.1.0] - 2026-04-23

### Added

- Initial structure of the modular project (`core`, `src`, `cli`, `docs`, `tests`).
- Functional CLI for technical flow: `raw-info`, `develop`, `detect-chart`, `sample-chart`, `build-profile`, `validate-profile`, `batch-develop`.
- Lightweight GUI in `tkinter` to operate the entire flow without command line.
- Automatic end-to-end flow (`auto-profile-batch`) for letter -> ICC profile -> 16-bit TIFF batch.
- External tools verification script: `scripts/check_tools.sh`.
- User manual in Spanish.
- Integration technical document `dcraw + ArgyllCMS`.
- Legal compliance document and licensing policy.

### Changed

- Graphic interface completely translated into Spanish.
- RAW development engine set to `dcraw` as the only supported backend.
- ICC profile engine fixed to ArgyllCMS (`colprof`) as the only supported backend.
- Updated project license metadata to `AGPL-3.0-or-later`.
- Governance declared for community maintenance by the Spanish Association of Scientific and Forensic Image.

### Fixed

- Adjusted `.ti3` format for `colprof` (`DEVICE_CLASS`/`COLOR_REP` and field order) for real compatibility with ArgyllCMS.
- Improved detection and registration of `dcraw` version in execution context.

### Docs

- Architecture, roadmap, decisions and manual aligned with:
  - strict pipeline `dcraw + ArgyllCMS`,
  - reproducibility requirements,
  - AGPL legal compliance for distribution and network use.
