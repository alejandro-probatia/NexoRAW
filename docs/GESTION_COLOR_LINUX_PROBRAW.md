_Spanish version: [GESTION_COLOR_LINUX_PROBRAW.es.md](GESTION_COLOR_LINUX_PROBRAW.es.md)_

# System Color Management in ProbRAW

## Goal

This document records the implementation decisions derived from the local Linux
color-management notes used during the ProbRAW review:

`/home/alejandro/Documentos/Notas/Notas MD/FOTOGRAFÍA/Tecnología de imagen digital/Procesado digital de imágenes/gestión de color en linux.md`

The main conclusion is that ProbRAW must not treat color as an implicit property
of a file, a monitor or Qt. Color must be represented as an explicit chain of
states and transforms:

```text
input -> working space -> preview/display -> export -> proof/soft-proof
```

The monitor profile must never act as working space, and it must never change
TIFF pixels, hashes, manifests, ProbRAW Proof records or C2PA data.

## Current State

ProbRAW already has a solid ICC base:

- it separates input ICC profiles, standard generic profiles and monitor ICC
  profiles;
- it creates session input ICC profiles with ArgyllCMS `colprof`;
- it uses ArgyllCMS `cctiff` for explicit derived ICC export conversions;
- it uses LittleCMS2 through Pillow `ImageCms` for managed preview and ICC
  profile-preview LUTs;
- it refuses camera RGB exports without an input profile;
- it records hashes for RAW, TIFF, recipes, settings and ICC files in Proof and
  manifests;
- it limits monitor ICC management to display.

The remaining work is mostly about richer system integration, better metadata
capture for non-RAW images, multi-monitor handling and stronger tests with
external profiles.

## Cross-Platform Contract

ProbRAW must remain portable across Windows, Linux and macOS. The architecture
therefore separates the transform engine, the display-profile provider and the
surface policy:

```text
Preview ICC transform:      LittleCMS2 via Pillow ImageCms
Session ICC creation:       ArgyllCMS colprof
Generated ICC validation:   ArgyllCMS xicclu/icclu
Windows display profile:    WCS/ICM, GetICMProfileW
macOS display profile:      ColorSync/CoreGraphics
Linux display profile:      colord, _ICC_PROFILE on X11 as fallback
Wayland/KWin:               compositor is active; avoid double conversion
```

Consequences:

- ICC preview must not depend on external ArgyllCMS command-line tools;
- the monitor profile must not be treated as working space;
- Windows, macOS and Linux cannot be assumed to expose the active display
  profile in the same way;
- `probraw check-color-environment` must record the profile provider, preview
  CMM and surface policy actually used;
- manual monitor ICC selection must remain available as a portable escape hatch
  when the operating system does not expose a reliable profile.

## Implemented Improvements

### System Standard Profiles

`src/probraw/profile/generic.py` now searches standard RGB profiles in common
system locations rather than one fixed path:

- `PROBRAW_STANDARD_ICC_DIR`;
- ArgyllCMS reference paths, including `/usr/share/argyllcms/ref`;
- `$XDG_DATA_HOME/color/icc` and `$XDG_DATA_HOME/icc`;
- entries from `$XDG_DATA_DIRS`, for example `/usr/share/color/icc`;
- `/usr/share/color/icc/colord`;
- `/usr/share/icc`;
- `/usr/local/share/color/icc`;
- `/usr/local/share/icc`;
- `/opt/homebrew/share/color/icc`;
- `/opt/homebrew/share/argyllcms/ref`;
- `/var/lib/colord/icc`;
- `~/.local/share/color/icc`.

The search is recursive and matches both file names and ICC profile
descriptions. That allows ProbRAW to use profiles installed by the system even
when their file names differ from the old expected names.

### Arch/CachyOS Compatibility

On Arch and CachyOS, ArgyllCMS reference profiles can live in:

```text
/usr/share/argyllcms/ref
```

ProbRAW now checks that path for both standard generic profiles and export
reference profiles. This avoids the failure where ProPhoto RGB was missing even
though ArgyllCMS was correctly installed.

### Safe ProPhoto RGB Selection

ProPhoto RGB has linear and non-linear variants. ProbRAW accepts descriptions
compatible with ProPhoto/ROMM RGB but rejects descriptions containing `Linear`
when the standard gamma 1.8 ProPhoto RGB profile is required. This prevents
accidentally selecting `ProPhotoLin.icm`.

### Tool and Profile Validation

`probraw check-tools --strict` now checks:

- `colprof`;
- `xicclu` or `icclu`;
- `cctiff`;
- `exiftool`;
- real standard profiles for sRGB, Adobe RGB (1998) and ProPhoto RGB.

Missing standard profiles are treated as environment failures, not as a minor
detail that can silently degrade color handling.

### ICC File Dialogs

GUI ICC file dialogs now start from likely system ICC directories. This reduces
manual profile copying and encourages use of profiles installed or assigned by
the operating system.

### Environment Audit

`probraw check-color-environment` reports the system color contract actually
seen by the installed application:

- operating system and desktop/session details;
- Windows WCS/ICM, macOS ColorSync/CoreGraphics or Linux colord/X11/Wayland
  display-profile provider;
- LittleCMS2/Pillow versions used for preview;
- ArgyllCMS tools used for profile creation, validation and derived export;
- Qt/PySide versions;
- relevant Linux packages and Wayland color-management protocol availability;
- active display profile when it can be detected, otherwise explicit sRGB visual
  fallback.

`check-tools --strict` validates operational dependencies. `check-color-environment`
documents how ProbRAW adapts to the real graphics stack.

## Priority Work

### Explicit Color State

ProbRAW should describe the color state of every input and transform outside the
NumPy pixel arrays. A minimal model should include:

```json
{
  "source_profile_origin": "embedded|system|user|assumed|none",
  "source_profile_sha256": "...",
  "source_color_declaration": "ICC|sRGB_chunk|gAMA_cHRM|EXIF|CICP|untagged",
  "working_space_id": "...",
  "working_transfer": "linear|srgb|gamma|custom",
  "cmm": "lcms2|argyllcms",
  "cmm_version": "...",
  "rendering_intent": "relative_colorimetric",
  "black_point_compensation": true,
  "export_profile_sha256": "...",
  "display_profile_sha256": "..."
}
```

Pixels are not objectively colorimetric without this context.

### Embedded ICC and Non-ICC Declarations

For non-RAW raster inputs, `core.utils.read_image()` should eventually return
both the pixel array and the original color declaration:

- JPEG APP2 ICC;
- TIFF tag 34675 ICC;
- PNG `iCCP`;
- PNG `gAMA`, `cHRM` and `sRGB`;
- EXIF `ColorSpace`;
- CICP/nclx if newer formats are added.

Embedded ICC bytes should be preserved exactly and hashed before any conversion.

### Untagged Images

Untagged images must not be silently converted. Recommended policy:

- keep the original state as `untagged`;
- allow preview under an explicit assumption, usually sRGB;
- record that the assumption is display-only;
- block absolute colorimetric measurements until the source space is known;
- allow manual profile assignment;
- clearly separate assign-profile from convert-profile in UI and sidecars.

### colord, Wayland and Multi-Monitor

Path search is suitable for standard profiles, but an active monitor profile
should preferably come from the operating system:

- record device id, profile id, path and SHA-256;
- listen for profile/device changes when possible;
- distinguish monitor, camera, printer and generic RGB profiles;
- never assume the first ICC found on disk is the active display profile.

On Wayland, the compositor is part of the pipeline. ProbRAW must keep an
explicit platform decision:

- stable current mode: when an active monitor ICC exists, ProbRAW converts
  preview pixels with LittleCMS2 to that monitor profile and hands the Qt image
  over as device RGB, without an additional `QColorSpace` tag;
- explicit fallback: when no monitor ICC is available, preview remains visual
  sRGB and the Qt image is tagged as sRGB;
- experimental compositor-delegated mode: tag the surface and delegate the final
  conversion to the compositor only after a validated Qt/KWin/Wayland test
  matrix exists;
- the monitor ICC is never used for TIFF/export data, which stays tied to the
  selected input ICC and export policy;
- screenshots are not conclusive colorimetric proof.

Multi-monitor support must eventually detect the active screen for the viewer,
invalidate display LUTs when the window moves and record which output profile
was used.

### Soft-Proofing

Soft-proofing is not just another preview. It should be an explicit transform:

```text
source/working -> proof profile -> display profile
```

It needs its own proof profile, intents, black-point compensation, out-of-gamut
warnings and provenance records. The existing 3D gamut diagnostic helps compare
profiles, but it does not replace a reproducible soft-proof pipeline.

## CachyOS/Arch Build

The native Arch/CachyOS package is built with:

```bash
PROBRAW_ARCH_PKGREL=3 PROBRAW_ARCH_NATIVE=1 PROBRAW_BUILD_AMAZE=1 packaging/arch/build_pkg.sh
```

Important variables:

- `PROBRAW_ARCH_PKGREL`: Arch package release for rebuilds of the same upstream
  version.
- `PROBRAW_ARCH_NATIVE=1`: builds C/C++ extensions with `-O3 -march=native
  -mtune=native`. Good for local optimized packages, not for portable packages
  for other CPUs.
- `PROBRAW_BUILD_AMAZE=1`: builds and installs `rawpy-demosaic` with AMaZE.
- `PROBRAW_ARCH_SYNCDEPS=1`: lets `makepkg` install dependencies with pacman.
- `PROBRAW_MAKEPKG_ARGS="--cleanbuild"`: forces a clean rebuild.

The package installs ProbRAW under `/opt/probraw/venv`, exposes only `probraw`
and `probraw-ui`, conflicts/replaces `iccraw` and `nexoraw`, and stores
`rawpy-demosaic` AMaZE metadata under
`/usr/share/doc/probraw/third_party/rawpy-demosaic/`.

Clean local reinstall without deleting user data:

```bash
sudo pacman -R --noconfirm probraw || true
sudo rm -rf /opt/probraw
sudo rm -f /usr/bin/probraw /usr/bin/probraw-ui /usr/bin/iccraw /usr/bin/iccraw-ui
sudo pacman -U --noconfirm build/arch/probraw-<version>-<pkgrel>-x86_64.pkg.tar.zst
```

Validation after installing the real package:

```bash
pacman -Qkk probraw
bash /usr/share/doc/probraw/validate_cachyos_install.sh
probraw check-tools --strict
probraw check-color-environment --out color_environment.json
```

The validation must prove that system standard profiles are found, LittleCMS2 is
available for preview and ArgyllCMS is available for ICC creation/validation.

### rawpy-demosaic Build Compatibility

`scripts/build_rawpy_demosaic_wheel.py` applies build patches needed by current
CachyOS/Python toolchains:

- sets a minimum CMake policy compatible with older LibRaw sources;
- uses `Cython>=3.1` and `numpy` for modern Python support;
- replaces C-level `ndarr.base` assignments with `np.set_array_base`, avoiding
  Cython build errors.

These are packaging/build changes. They do not change ProbRAW color policy or
AMaZE semantics.

## Test Corpus

Recommended image/profile coverage:

- sRGB ICC v2/v4;
- Adobe RGB v2/v4;
- ProPhoto RGB gamma 1.8 and linear ProPhoto;
- Display P3 and Rec.2020;
- TIFF/JPEG/PNG with embedded ICC;
- PNG with `gAMA`, `cHRM` or `sRGB` but no ICC;
- untagged image;
- gray image with profile;
- malformed, truncated, huge or unexpected-class ICC profiles;
- CachyOS KDE Plasma Wayland/KWin, KDE X11, GNOME Wayland and multi-monitor
  setups with different profiles.

## Acceptance Criteria

A color-management improvement is complete only when it:

- avoids silent conversions;
- documents whether an operation assigns or converts a profile;
- preserves original ICC bytes when they come from the file;
- computes SHA-256 for profiles used;
- records CMM, version, intent and flags;
- keeps the monitor profile out of TIFF/export data;
- fails explicitly when a required profile is missing;
- includes tests with real system profiles and controlled fixtures;
- is verified in the installed application, not only the editable source tree.

## Code Areas to Evolve

- `src/probraw/core/utils.py`: separate pixel reading from color
  state/metadata reading.
- `src/probraw/raw/preview.py`: preserve ICC and color declarations for embedded
  previews when used.
- `src/probraw/display_color.py`: enrich colord/Wayland and multi-monitor
  detection.
- `src/probraw/profile/generic.py`: keep system profile search and extend ICC
  validation.
- `src/probraw/profile/export.py`: record intent/flags/CMM and full origin of
  standard profiles copied into the session.
- `src/probraw/reporting.py`: capture Windows, macOS and Linux graphics/color
  environment details.
- `src/probraw/provenance/probraw_proof.py`: include origin, source path,
  description and SHA-256 for input/output/proof profiles.
- `tests/`: add ICC fixtures, untagged images, PNG color chunks, JPEG/TIFF ICC
  samples and colord/Wayland simulations.
