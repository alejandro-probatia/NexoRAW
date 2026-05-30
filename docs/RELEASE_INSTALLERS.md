_Spanish version: [RELEASE_INSTALLERS.es.md](RELEASE_INSTALLERS.es.md)_

# Publication of installers

The ProbRAW installer release has a simple rule: no
artifact is uploaded to the repository or GitHub Releases without first passing the
package and installation validations.

## Release 0.4.3

0.4.3 is a precision release for RAW/DNG ICC profiling, manual chart marking and
Lab diagnostics. Before publishing artifacts, verify:

- local test suite and Python compilation complete without errors;
- manually marked charts show small, movable central reading regions saved in
  the overlay;
- the Lab eyedropper requires real-pixel sources and recalculates pending detail
  adjustments before saving the sample;
- Lab samples support compact cards, marker color, selected-sample highlighting
  and an expanded Lab a*b* graph;
- thumbnails keep the filename above profile badges;
- exposure, contrast, color and curve sliders keep bounded interactive previews
  and postpone exact histogram/final refinement until controls are idle;
- the Linux Debian/Ubuntu build generates `probraw_0.4.3_amd64.deb`, validates
  with `packaging/debian/validate_deb.sh`, and has SHA256
  `16e1329bff4514374f0d6d7866b602a1866bd6f95035422d3f51211df4f4050c`;
- the Linux Arch/CachyOS build generates
  `probraw-0.4.3-1-x86_64.pkg.tar.zst` with the `arch-cachyos-native` profile,
  includes AMaZE, and has SHA256
  `f1061fbf65a9c5ff7cb4ff97e5d82fda4cccf3994ed630678116b2b91a393557`;
- the Windows build generates `ProbRAW-0.4.3-Setup.exe` and its `.sha256`,
  documented in `docs/releases/0.4.3.md`; its SHA256 is
  `c171576e88add213e812a3b13ea8f0f46ba529a170c3bc1b6d54a4d6f9639c57`.

## Release 0.4.2

0.4.2 is a reliability release for ICC profiling, update handling and
cross-platform installers. Before publishing artifacts, verify:

- full local suite: `523 passed, 1 skipped, 2 warnings`;
- `download_update_asset` rejects asset/checksum names that contain external
  paths;
- Linux recognizes `.deb`, `.rpm`, AppImage and Arch `pkg.tar.*` without
  selecting wheels or source tarballs as installers;
- persisted `session.json` directories remain confined to the session root;
- missing independent validation does not mark the profile as `draft` by itself
  when QA against the chart colorimetric reference passes;
- `rejected` profiles never autoactivate and require explicit operator
  confirmation before manual activation;
- profile metadata reports the real ArgyllCMS model instead of always reporting
  `matrix3x3`;
- the Linux Debian/Ubuntu build generates `probraw_0.4.2_amd64.deb`, validates
  with `packaging/debian/validate_deb.sh`, and has SHA256
  `269fa680103119763bc215e297181aed716a9503a4a176442f1f20e4224be579`;
- the Windows build generates `ProbRAW-0.4.2-Setup.exe` and its `.sha256`:
  `69372cafa12e13651278228781c2db042423a6d9cf0244cf6f50d198ae0cab11`.

## Linux `.deb`

Always build with AMaZE required:
```bash
PROBRAW_BUILD_AMAZE=1 PROBRAW_REQUIRE_AMAZE=1 bash packaging/debian/build_deb.sh
```
Validate the package before installing or uploading:
```bash
packaging/debian/validate_deb.sh dist/probraw_<version>_amd64.deb
sha256sum dist/probraw_<version>_amd64.deb > dist/probraw_<version>_amd64.deb.sha256
```
Validate on a real installation:
```bash
sudo apt purge nexoraw iccraw probraw
sudo apt install ./dist/probraw_<version>_amd64.deb
scripts/validate_linux_install.sh
probraw --version
probraw check-tools --strict
probraw check-amaze
```
The validation checks name `ProbRAW`, launchers `probraw`/`probraw-ui`,
absence of legacy executables `nexoraw`/`iccraw`, full hicolor icon, fallback
`/usr/share/pixmaps/probraw.png`, menu category `Graphics;Photography`,
C2PA, external tools and AMaZE.

Smoke GUI minimum before publishing:

- open ProbRAW from the system menu;
- confirm that it appears in `Graficos/Fotografia` with ProbRAW icon;
- create a new session and verify folders `00_configuraciones/`, `01_ORG/`
  and `02_DRV/`;
- open the root of the project and confirm that the browser enters `01_ORG/`;
- switch to another project and confirm that there are no thumbnails left from the session
  previous;
- select a RAW and check that the thumbnail shows an image, not just an icon
  generic;
- generate or save a basic profile and confirm backpack `RAW.probraw.json`;
- try copy/paste setting profile between two thumbnails;
- check `Configuracion > Configuracion global` and confirm detection or
  monitor ICC profile fallback.

## Linux Arch/CachyOS

The Arch/CachyOS package is built from `packaging/arch/build_pkg.sh` using the
versioned `PKGBUILD` in this repository:

```bash
PROBRAW_ARCH_PKGREL=3 \
PROBRAW_ARCH_NATIVE=1 \
PROBRAW_BUILD_AMAZE=1 \
packaging/arch/build_pkg.sh
```

For a local optimized CachyOS build, `PROBRAW_ARCH_NATIVE=1` enables
`-O3 -march=native -mtune=native` for C/C++ extensions. Do not use it for a
package intended for machines with different CPUs. The package installs the app
under `/opt/probraw/venv`, exposes only `probraw` and `probraw-ui`,
conflicts/replaces `iccraw`/`nexoraw` and installs validation documentation under
`/usr/share/doc/probraw/`.

Clean local reinstall without deleting user data:

```bash
sudo pacman -R --noconfirm probraw || true
sudo rm -rf /opt/probraw
sudo rm -f /usr/bin/probraw /usr/bin/probraw-ui /usr/bin/iccraw /usr/bin/iccraw-ui
sudo pacman -U --noconfirm build/arch/probraw-<version>-<pkgrel>-x86_64.pkg.tar.zst
```

Required validation on the real installation:

```bash
pacman -Qkk probraw
bash /usr/share/doc/probraw/validate_cachyos_install.sh
probraw check-tools --strict
probraw check-amaze
probraw check-color-environment --out color_environment.json
```

`check-color-environment` may return `warning` when the system does not expose
an active monitor ICC profile. That records visual sRGB fallback, not an
installation failure. The build is publishable only when standard profiles,
LittleCMS2, ArgyllCMS and AMaZE are verified.

## Windows

The Windows installer must be generated from `packaging/windows/build_installer.ps1`
with `-RequireAmaze` and a plotted wheel when PyPI does not offer a compatible one:
```powershell
.\packaging\windows\build_installer.ps1 -RawpyDemosaicWheel $wheel -RequireAmaze
```
The build should not generate `nexoraw.exe`, `nexoraw-ui.exe`, `iccraw.exe` or
`iccraw-ui.exe`. The shortcuts should point to `probraw-ui.exe` and use the
`probraw-icon.ico` icon.

## macOS

The macOS artifact is generated from a macOS host with PyInstaller:

```bash
PROBRAW_REQUIRE_AMAZE=1 \
PROBRAW_MACOS_STRICT_TOOLS=1 \
bash packaging/macos/build_app.sh
```

Expected outputs:

- `dist/macos/ProbRAW.app`
- `dist/macos/probraw/probraw`
- `dist/macos/ProbRAW-<version>-macos-<arch>.zip`
- `dist/macos/ProbRAW-<version>-macos-<arch>.zip.sha256`

Validate the build at minimum with:

```bash
dist/macos/probraw/probraw --version
dist/macos/probraw/probraw check-tools --strict
dist/macos/probraw/probraw check-amaze
open dist/macos/ProbRAW.app
```

Developer ID signing and notarization are not run by default. To sign the
generated `.app` locally, use `PROBRAW_MACOS_CODESIGN_IDENTITY`. A public asset
must document whether it is signed/notarized or whether it is a local testing
zip.

## Releases

1. Run project tests.
2. Run performance/GUI benchmarks when previewed,
   RAW pipeline, cache or parallelism.
3. Update `src/probraw/version.py`, `CHANGELOG.md`, README and documentation
   of installers.
4. Build installers from versioned scripts, not manually.
5. Run validations for each platform.
6. Generate `.sha256` after validating.
7. Upload only validated artifacts.
8. If a published asset turns out to be defective and GitHub does not allow it to be replaced,
   create a new revision of the release and mark the previous one with a warning.

## Release 0.4.1

Release 0.4.1 is a Linux Arch/CachyOS corrective release for the Lab sample and
GUI workflow:

- saved Lab samples are invalidated and recalculated after color, exposure and
  contrast changes,
- partial interactive preview updates also refresh saved sample readings,
- sample RGB values are shown as 0-255 integers,
- the interface is consistently Spanish and uses a neutral dark-gray theme,
- precision and workflow notes are exposed through compact information buttons
  where possible.

Expected artifacts for the Linux Arch/CachyOS release:

- `probraw-0.4.1-1-x86_64.pkg.tar.zst`
- `probraw-0.4.1-1-x86_64.pkg.tar.zst.sha256`

## Release 0.4.0

Release 0.4.0 adds Lab sample diagnostics:

- real-pixel Lab eyedropper with sampling matrices and viewer magnifier,
- per-image persistence of samples in `RAW.probraw.json`,
- named sample sets with table/card views and editable name/note fields,
- set-level DeltaE, C*, dispersion, similarity and sample-gamut comparison,
- Lab 2D gamut slices with vertical L* selector next to the existing Lab 3D view.

Expected artifacts for the Windows release:

- `ProbRAW-0.4.0-Setup.exe`
- `ProbRAW-0.4.0-Setup.exe.sha256`
- `probraw-0.4.0.tar.gz`
- `probraw-0.4.0-py3-none-any.whl`
- `probraw_0.4.0_python_artifacts.sha256`

## Release 0.3.22

Release 0.3.22 fixes the session-generated ICC profile selection workflow:

- `rejected` profiles still do not autoactivate,
- manual selection from the combo, menu or "Use generated ICC" is allowed,
- RAW sidecars preserve both the ICC path and identifier, and restore
  `rejected` profiles only when both match,
- switching to an image without a sidecar or with an inconsistent ID clears the
  active ICC.

Expected artifacts for the Windows release:

- `ProbRAW-0.3.22-Setup.exe`
- `ProbRAW-0.3.22-Setup.exe.sha256`
- `probraw-0.3.22.tar.gz`
- `probraw-0.3.22-py3-none-any.whl`
- `probraw_0.3.22_python_artifacts.sha256`

## Release 0.3.21

Release 0.3.21 replaces 0.3.20 because of the ICC generation failure with a
manually marked chart and additional captures rejected by fallback detection:

- manual detections are kept as training data before reserving captures for
  validation,
- missing independent validation leaves the ICC as a usable `draft`, not a
  blocking error,
- the tone-curve histogram is calculated in the background during dragging and
  reflects the applied tonal adjustments,
- preview with a generated input ICC avoids camera display-balance compensation
  that caused blue casts.

Expected artifacts for the Windows release:

- `ProbRAW-0.3.21-Setup.exe`
- `ProbRAW-0.3.21-Setup.exe.sha256`
- `probraw-0.3.21.tar.gz`
- `probraw-0.3.21-py3-none-any.whl`
- `probraw_0.3.21_python_artifacts.sha256`

## Release 0.3.20

Release 0.3.20 consolidates the session-path and monitor preview fixes:

- new sessions align the file browser, chart reference folder and derivative
  TIFF export folder with the active project,
- manual chart marking can build an ICC profile even after automatic chart
  detection produced no usable candidates,
- monitor ICC conversion remains display-only: exported TIFF files keep the
  selected input ICC,
- preview pixels already converted to the monitor ICC with LittleCMS are handed
  to Qt as device RGB, avoiding a second `QColorSpace` conversion.

Expected artifacts for the Windows release:

- `ProbRAW-0.3.20-Setup.exe`
- `ProbRAW-0.3.20-Setup.exe.sha256`
- `probraw-0.3.20.tar.gz`
- `probraw-0.3.20-py3-none-any.whl`
- `probraw_0.3.20_python_artifacts.sha256`

## Release 0.3.19

Release 0.3.19 consolidates the post-0.3.18 packaging and preview work:

- macOS packaging is available from versioned scripts and documented for
  validation, optional signing and AMaZE checks,
- Arch/CachyOS packaging and system ICC profile discovery remain documented for
  native package builds,
- first RAW preview loading can show an oriented provisional embedded preview
  while the full render is prepared,
- viewer geometry sidecar writes are flushed during fast file changes.

Expected artifacts for the Windows release:

- `ProbRAW-0.3.19-Setup.exe`
- `ProbRAW-0.3.19-Setup.exe.sha256`
- `probraw-0.3.19.tar.gz`
- `probraw-0.3.19-py3-none-any.whl`
- `probraw_0.3.19_python_artifacts.sha256`

## Release 0.3.18

Release 0.3.18 fixes undo after viewer geometry changes:

- crop-only and leveling-only undo/redo no longer force a final preview rebuild,
- going back after recropping a large RAW preview avoids the apparent UI hang
  caused by unnecessary preview recomputation.
- Arch/CachyOS revision `0.3.18-3` adds system ICC profile discovery, ICC
  preview through LittleCMS2, `check-color-environment` validation and a native
  optimized AMaZE package.

Expected artifacts:

- `ProbRAW-0.3.18-Setup.exe`
- `ProbRAW-0.3.18-Setup.exe.sha256`
- `probraw-0.3.18-<pkgrel>-x86_64.pkg.tar.zst`
- `probraw-0.3.18.tar.gz`
- `probraw-0.3.18-py3-none-any.whl`
- `probraw_0.3.18_python_artifacts.sha256`

## Release 0.3.17

Release 0.3.17 improves interactive preview and cached RAW session performance:

- lateral chromatic-aberration remap coordinates are reused during repeated
  preview edits,
- vibrance/saturation preview adjustments allocate fewer temporary arrays,
- demosaic cache pruning is rate-limited during batch/cache writes,
- local false-color suppression reduces temporary allocations while preserving
  canonical regression hashes.

Expected artifacts:

- `ProbRAW-0.3.17-Setup.exe`
- `ProbRAW-0.3.17-Setup.exe.sha256`
- `probraw-0.3.17.tar.gz`
- `probraw-0.3.17-py3-none-any.whl`
- `probraw_0.3.17_python_artifacts.sha256`

## Release 0.3.16

Release 0.3.16 improves TIFF export control and GUI review workflows:

- final TIFFs can be exported uncompressed or with ZIP/Deflate, LZW, JPEG or
  ZSTD compression,
- `imagecodecs` is included in runtime and Windows packaging for TIFF codecs,
- compressed TIFF export can bound per-TIFF compression workers and batch export
  distributes CPU across active jobs,
- horizontal/vertical leveling uses a draggable line and exported rotations are
  cropped to avoid black canvas borders,
- the folder tree can open directories in the system file browser,
- the render queue shows per-file progress bars.

Expected artifacts:

- `ProbRAW-0.3.16-Setup.exe`
- `ProbRAW-0.3.16-Setup.exe.sha256`
- `probraw-0.3.16.tar.gz`
- `probraw-0.3.16-py3-none-any.whl`
- `probraw_0.3.16_python_artifacts.sha256`

## Release 0.3.15

Release 0.3.15 fixes export fidelity and reduces heavy work in preview,
profiling and batch workflows:

- rendered TIFFs apply visual crop and leveling geometry in the output path,
- multi-file batches no longer propagate the active image geometry to every
  item,
- TIFF16 ICC conversion remains only on ArgyllCMS `cctiff`,
- export crop rounding matches the viewer,
- chart sampling, MTF and preview cache reduce memory/IO work,
- GUI profiling avoids implicit process workers on Windows.

Expected artifacts:

- `ProbRAW-0.3.15-Setup.exe`
- `ProbRAW-0.3.15-Setup.exe.sha256`
- `probraw-0.3.15.tar.gz`
- `probraw-0.3.15-py3-none-any.whl`
- `probraw_0.3.15_python_artifacts.sha256`

## Release 0.3.14

Release 0.3.14 stabilizes the balance between interactive performance and
accurate GUI readings:

- histograms and levels update during drags with throttling, without blocking
  the UI or losing the exact refresh on release,
- the tone curve keeps its histogram visible while editing points or the
  black/white range,
- the viewer adds visual crop, horizontal/vertical leveling, fractional
  rotation and crop reprojection in real-pixel view,
- the `Edit` menu adds undo, redo, clear adjustments and `Ctrl+Z`/`Ctrl+Y`,
- the update downloader skips metadata and requires a verifiable SHA-256 for
  installers.

Expected artifacts:

- `ProbRAW-0.3.14-Setup.exe`
- `ProbRAW-0.3.14-Setup.exe.sha256`
- `probraw-0.3.14.tar.gz`
- `probraw-0.3.14-py3-none-any.whl`
- `probraw_0.3.14_python_artifacts.sha256`

## Release 0.3.13

Release 0.3.13 is a bugfix release for the levels/tone-curve histogram
inconsistency detected in 0.3.12:

- the tone-curve editor histogram now represents the input data entering the
  curve instead of the output already clipped by the curve range,
- the full-image RGB histogram is marked as updating while exact clipping
  metrics are recalculated after levels/curve changes,
- regression tests cover curve white-point clipping and stale exact-histogram
  state.

Artifacts expected:

- `ProbRAW-0.3.13-Setup.exe`
- `ProbRAW-0.3.13-Setup.exe.sha256`
- `probraw-0.3.13.tar.gz`
- `probraw-0.3.13-py3-none-any.whl`
- `probraw_0.3.13_python_artifacts.sha256`

## Release 0.3.12

Release 0.3.12 restores the smoother 0.3.8-style preview cadence while keeping
the later accuracy fixes:

- preview refreshes during slider and curve drags are throttled instead of
  scheduled on every event,
- ICC profile previews use bounded sources below 1:1 and full source at real
  pixel inspection,
- full-image viewer histograms remain exact and are refreshed after
  interaction settles,
- tone-curve point drags and black/white curve sliders avoid expensive
  histogram work while moving and consolidate once on release,
- the update assistant downloads the installer to a recognizable folder and
  launches it visibly.

Expected artifacts:

- `ProbRAW-0.3.12-Setup.exe`
- `ProbRAW-0.3.12-Setup.exe.sha256`
- `probraw-0.3.12.tar.gz`
- `probraw-0.3.12-py3-none-any.whl`
- `probraw_0.3.12_python_artifacts.sha256`

## Release 0.3.11

Release 0.3.11 fixes interactive preview and sharpness responsiveness without
weakening ICC management or confusing proxies with real pixels:

- color, contrast, curve and sharpness adjustments again use bounded proxy
  sources during drags when the viewer is not inspecting at 1:1,
- the viewer restores the full source when the user requests real pixels, and
  cached/reduced RAW previews are not labelled as real 100% pixels,
- zoom and viewport changes reschedule the visible viewport preview so the whole
  viewed region shows the active adjustments,
- ESF/LSF/MTF plots refresh in real time while dragging sharpness controls when
  the full-resolution ROI is already hot,
- documentation fixes the display contract as `input ICC -> monitor ICC`, and
  the sRGB OETF remains only an explicit tone-curve option.

Expected artifacts:

- `ProbRAW-0.3.11-Setup.exe`
- `ProbRAW-0.3.11-Setup.exe.sha256`
- `probraw-0.3.11.tar.gz`
- `probraw-0.3.11-py3-none-any.whl`
- `probraw_0.3.11_python_artifacts.sha256`

## Release 0.3.10

Release 0.3.10 fixes the preview-profile invariant and improves 100%
interactive performance without degrading color or sharpness:

- every managed image has a mandatory input profile: session/image ICC or a real
  generic profile,
- profiled display uses direct `source ICC -> monitor ICC` conversion, with no
  standard sRGB display route when a source profile exists,
- dense 8-bit ICC LUT cache generated by LittleCMS, persisted on disk and reused
  for large previews,
- visible-region updates, stable 1:1 zoom and magnification above 100% without
  automatic reset,
- near-instant color/contrast sliders and faster curves through tonal-LUT cache
  and shared RGB quantization,
- separate cache buttons for selected-image 1:1 preload and visible-directory
  preload,
- real GUI benchmark documented with full RAW, monitor ICC and clipping overlay.

Expected artifacts:

- `ProbRAW-0.3.10-Setup.exe`
- `ProbRAW-0.3.10-Setup.exe.sha256`
- `probraw-0.3.10.tar.gz`
- `probraw-0.3.10-py3-none-any.whl`
- `probraw_0.3.10_python_artifacts.sha256`

## Release 0.3.9

Release 0.3.9 improves sharpness-analysis readability and adds lateral
chromatic-aberration inspection:

- CA lateral graph from the same slanted-edge ROI, with RGB differences, CA
  area, channel shifts and nearest-neighbour edge pixel strip,
- ESF local edge window with pixel-tone strip,
- clearer MTF cycles/pixel scale and standard MTF50/MTF30/MTF10 references,
- annotated MTF/CA classes and helpers for future team development.

Expected artifacts:

- `ProbRAW-0.3.9-Setup.exe`
- `ProbRAW-0.3.9-Setup.exe.sha256`
- `probraw-0.3.9.tar.gz`
- `probraw-0.3.9-py3-none-any.whl`
- `probraw_0.3.9_python_artifacts.sha256`

## Release 0.3.8

Release 0.3.8 fixes a serious divergence between preview and rendered TIFF while
keeping the exact render path with better performance:

- RAW preview and export use the same effective render and color path,
- exact RAW demosaic output is cached for reloads, exact refinement, export,
  batches and queue processing,
- cache reads reduce full-frame memory copies on large images,
- the development queue removes completed items to avoid rendering them again
  and keeps failed items with their error message.

Expected artifacts:

- `ProbRAW-0.3.8-Setup.exe`
- `ProbRAW-0.3.8-Setup.exe.sha256`
- `probraw-0.3.8.tar.gz`
- `probraw-0.3.8-py3-none-any.whl`
- `probraw_0.3.8_python_artifacts.sha256`

## Release 0.3.7

Release 0.3.7 fixes visual equivalence between ProbRAW and external
color-managed applications, and strengthens analysis tooling:

- preview and exported TIFFs use the same effective recipe and ICC path,
- 100% and higher zoom shows real pixels without interpolation and preserves
  the center of the inspected area,
- ESF/LSF/MTF plots show sample counts, pixel scale, MTF50 and MTF50P,
- Auto Sharpness penalizes halos, oversharpened peaks and post-Nyquist energy,
- chart ICC profiles stay separate from manual color, contrast and detail
  adjustments,
- automatic MTF recalculation pauses outside Sharpness so chromatic adjustments
  do not run hidden MTF work.

Expected artifacts:

- `ProbRAW-0.3.7-Setup.exe`
- `ProbRAW-0.3.7-Setup.exe.sha256`
- `probraw-0.3.7.tar.gz`
- `probraw-0.3.7-py3-none-any.whl`
- `probraw_0.3.7_python_artifacts.sha256`

## Release 0.3.6

Release 0.3.6 consolidates per-image ICC, color/contrast, sharpness and RAW
export adjustment traceability:

- RAW sidecars and thumbnails show the active adjustment categories per image,
- Color/Calibration separates generic ICC, existing camera ICC and chart-based
  ICC generation,
- preview display applies image ICC to monitor ICC conversion for viewing,
- RAW/export controls focus on RAW read/demosaic options and black points,
- tone-curve histograms update in real time, show RGB columns and isolate the
  active chromatic channel when editing it,
- Auto Sharpness writes the selected sharpness/radius into the RAW sidecar.

Expected artifacts:

- `ProbRAW-0.3.6-Setup.exe`
- `ProbRAW-0.3.6-Setup.exe.sha256`
- `probraw-0.3.6.tar.gz`
- `probraw-0.3.6-py3-none-any.whl`
- `probraw_0.3.6_python_artifacts.sha256`

## Release 0.3.5

Release 0.3.5 is a performance and reliability release for professional-size
RAW workflows:

- cold MTF analysis prepares a full-resolution ROI in an external worker process
  and reuses a persistent ROI cache for later recalculations,
- the top progress bar is now the single global viewer for long preview, MTF and
  background operations, with elapsed time and ETA,
- the `Nitidez` tab no longer duplicates a second local progress bar,
- batch rendering applies each RAW backpack when no registered development
  profile id is assigned, so sharpening, denoise, CA, color and contrast reach
  the final TIFF,
- switching to an unconfigured image resets development controls and active ICC
  state to the neutral ProPhoto/camera-WB policy,
- generic no-chart output disables profiling mode/identity WB for visible/final
  rendering, and camera RGB without an input ICC is rejected before writing a
  TIFF.

Expected artifacts:

- `probraw_0.3.5_amd64.deb`
- `probraw_0.3.5_amd64.deb.sha256`
- `probraw-0.3.5.tar.gz`
- `probraw-0.3.5-py3-none-any.whl`
- `probraw_0.3.5_python_artifacts.sha256`

## Release 0.3.4

Release 0.3.4 publishes the persistent full-resolution MTF sharpness analysis:

- slanted-edge `ESF`, `LSF` and `MTF` curves are stored in each RAW sidecar,
- reopening an image restores the saved ROI and curves without reselecting the
  edge,
- recalculation maps the viewer ROI onto the real full-resolution source image,
  avoiding thumbnail or reduced-preview measurements,
- two selected thumbnails with saved MTF data can be compared with overlaid
  curves and a numeric metric table,
- English Qt translations and the user manuals were updated for the new tools.

Expected artifacts:

- `probraw_0.3.4_amd64.deb`
- `probraw_0.3.4_amd64.deb.sha256`
- `probraw-0.3.4.tar.gz`
- `probraw-0.3.4-py3-none-any.whl`
- `probraw_0.3.4_python_artifacts.sha256`

## Release 0.3.3

Release 0.3.3 consolidates the graphical session, adjustment and color
management workflow:

- statistics and recent sessions in `1. Sesión`,
- third column organized by workflow: color/calibration, custom adjustments and
  RAW/export,
- compact horizontal viewer toolbar with icons and a button to focus/restore
  side columns,
- fixed colorimetric RGB histogram in `Ajustes personalizados`,
- per-channel curves and automatic chart-data recovery from `profile_report.json`,
- updated manuals and screenshots documenting the preview policy: input ICC to
  interpret the image, monitor ICC only as the final display layer.

Expected artifacts:

- `probraw_0.3.3_amd64.deb`
- `probraw_0.3.3_amd64.deb.sha256`
- `probraw-0.3.3.tar.gz`
- `probraw-0.3.3-py3-none-any.whl`
- `probraw_0.3.3_python_artifacts.sha256`

## Release 0.3.2

Release 0.3.2 fixes the application icon in Linux menus:

- the `.desktop` entry uses `Icon=/usr/share/pixmaps/probraw.png` as an
  absolute path to avoid hicolor theme lookup/cache failures,
- package and installation validations check that real menu icon.

Expected artifacts:

- `probraw_0.3.2_amd64.deb`
- `probraw_0.3.2_amd64.deb.sha256`
- `probraw-0.3.2.tar.gz`
- `probraw-0.3.2-py3-none-any.whl`
- `probraw_0.3.2_python_artifacts.sha256`

## Release 0.3.1

Release 0.3.1 updates the ProbRAW visual identity:

- new ProbRAW logo and icon with no leftovers from the previous brand,
- regenerated SVG, PNG and ICO assets for README, the application and
  installers,
- distribution artifacts published under `probraw_*` / `probraw-*` names.

Expected artifacts:

- `probraw_0.3.1_amd64.deb`
- `probraw_0.3.1_amd64.deb.sha256`
- `probraw-0.3.1.tar.gz`
- `probraw-0.3.1-py3-none-any.whl`
- `probraw_0.3.1_python_artifacts.sha256`

## Release 0.3.0

Release 0.3.0 introduces:

- complete product rename to ProbRAW across package metadata, GUI identity,
  commands, icons, documentation and release artifact filenames,
- Debian replacement/conflict metadata for previous `nexoraw` and `iccraw`
  beta packages,
- migration compatibility for existing `.nexoraw.json`,
  `.nexoraw.proof.json` and beta C2PA/Proof labels,
- explicit project leadership statement: Probatia Forensics SL
  (https://probatia.com) in collaboration with the Asociación Española de Imagen
  Científica y Forense (https://imagencientifica.es).

## Release 0.2.6

Release 0.2.6 introduces:

- advanced profile generation in the background to keep the GUI responsive,
- persistent session ICC profile catalog with several activatable versions,
- pairwise `Gamut 3D` comparison for session profiles, monitor profile, standard
  profiles and custom ICC files,
- visual chart reference management, including import, creation, validation and a
  Lab table editor with color swatches,
- versioned profiling artifacts under `00_configuraciones/profile_runs/`.

## Release 0.2.5

Release 0.2.5 introduces:

- canonical Python package layout under `src/probraw`,
- removal of the old internal compatibility namespace,
- GUI split into smaller modules by workflow area,
- updated Linux and Windows packaging names,
- C2PA assertion/action labels generated as `org.probatia.probraw.*` while
  keeping verification compatibility with earlier beta manifests,
- refreshed bilingual documentation and archived DCP+ICC planning in favor of the
  active ICC-centered workflow.

## Release 0.2.4

Release 0.2.4 introduces:

- interface language selector with system-language auto-detection,
- persisted language preference through Qt settings,
- safer language switching that applies on the next launch instead of
  restarting the app automatically.

## Release 0.2.3

Release 0.2.3 introduces:

- letterless flow with real standard profiles instead of generic profiles
  generated by ProbRAW,
- preferential selection of `AdobeRGB1998.icc` when it exists in the system,
- ProbRAW Proof/C2PA manifests with full recipe adjustments, sharpness,
  contrast/render and color management,
- Expanded metadata viewer to show those reproducible settings.

## Release 0.2.2

Release 0.2.2 introduces:

- real multiprocessing per process in `batch-develop`,
- demosaic opt-in numerical cache,
- golden tests of canonical hashes,
- playable RAW and GUI benchmarks,
- final refresh of preview in the background to avoid lag when releasing
  sliders/curve,
- RAM heuristic by worker adjusted with real Nikon D850 RAW.
