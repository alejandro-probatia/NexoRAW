_Spanish version: [INTEGRACION_LIBRAW_ARGYLL.es.md](INTEGRACION_LIBRAW_ARGYLL.es.md)_

# LibRaw and ArgyllCMS integration in ProbRAW

## Objective

ProbRAW uses a single RAW development engine:

- **LibRaw**, using the Python `rawpy` dependency, for decoding and
  RAW interpolation.
- **ArgyllCMS** (`colprof`) as ICC profiling engine.
- **ArgyllCMS** (`xicclu`/`icclu`) as validation tool for the generated ICC.
- **LittleCMS2**, through Pillow `ImageCms`, as ICC preview CMM.
- **ArgyllCMS** (`cctiff`) is kept for now for explicit output ICC conversions.

The goal is to maintain a reproducible and auditable scientific flow with less
code branches and no implicit mappings between different RAW engines.

## System installation

For end users, external dependencies must be reached through the
ProbRAW installers. The following manual installation is reserved for
development, CI or test environments.
```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .[gui]
sudo apt-get install -y argyll exiftool
```
On macOS with Homebrew:
```bash
brew install argyll-cms exiftool
```
`rawpy`/LibRaw is installed as a Python dependency of the project. For AMaZE
requires a GPL3 build with `DEMOSAIC_PACK_GPL3=True`; see
`docs/AMAZE_GPL3.md`.

Verification:
```bash
bash scripts/check_tools.sh
probraw check-tools --strict --out tools_report.json
```
`probraw check-tools` records availability of ArgyllCMS and `exiftool`.
`probraw check-color-environment` also records LittleCMS2, Qt/PySide, colord,
Wayland/KWin and system ICC profiles. The versions of `rawpy` and LibRaw are
registered in the execution context (`run_context`).

## LibRaw/rawpy integration

Key file:

- `src/probraw/raw/pipeline.py`

For RAW inputs, ProbRAW runs `rawpy.imread(...).postprocess(...)` with a
explicit contract:

- 16 bit output,
- `gamma=(1, 1)` to maintain linear output,
- `no_auto_bright=True`,
- `highlight_mode=Clip`,
- `user_flip=0`,
- `output_color=raw` to preserve camera RGB,
- white balance from metadata or fixed multipliers according to recipe,
- manual black/white level only if the recipe declares it.

Mapping of `recipe`:

- `raw_developer`: must be `libraw`.
- `demosaic_algorithm`: values supported by `rawpy`, including `dcb`,
  `dht`, `ahd`, `vng`, `ppg`, `linear` and, if the build includes it, `amaze`.
- `white_balance_mode` + `wb_multipliers`: `camera_metadata` or `fixed`.
- `black_level_mode`: optional `fixed:<valor>` or `white:<valor>`.

DCB (`demosaic_algorithm: dcb`) is the default because it offers high
quality and works with the standard `rawpy` wheels. AMaZE can be used with
a build of `rawpy`/LibRaw compiled with the GPL3 demosaic pack; if the build no
includes it, LibRaw returns an explicit error.

Operating rule:

- no alternative RAW engines or silent mappings allowed; a recipe that
  request a `raw_developer` other than `libraw` fails before processing.
- AMaZE requires `rawpy.flags["DEMOSAIC_PACK_GPL3"] == True`. If it is not
  available, the CLI/backend fails with an explicit error and the GUI degrades the
  interactive recipe to `dcb` to not block the calibration.

In release installers, AMaZE must be verified during build
and again in the installation with `probraw check-amaze`. An installer that does not
can demonstrate `amaze_supported: true` should not be published as build AMaZE.

## ArgyllCMS Integration

Key file:

- `src/probraw/profile/builder.py`

Flow:

1. A temporary `.ti3` is built with samples and reference.
2. Format used:
   - `DEVICE_CLASS "INPUT"`
   - `COLOR_REP "XYZ_RGB"`
   - `XYZ_X XYZ_Y XYZ_Z RGB_R RGB_G RGB_B` fields
3. `colprof` is executed to generate `.icc`.

Base command:
```bash
colprof -v -D "<description>" -qm -al -u -R <base_ti3>
```
Validation:

- `validate-profile` uses `xicclu` or `icclu` to query the actual ICC profile
  in forward mode towards Lab PCS.
- The `matrix_camera_to_xyz` matrix of the sidecar remains as a diagnosis, not as
  substitute for a real ICC conversion.

## CMM ICC with ArgyllCMS

Key file:

- `src/probraw/profile/export.py`

This section describes the current derived export path. The GUI ICC preview no
longer uses `xicclu`/`cctiff`: it builds its transforms with LittleCMS2 through
Pillow `ImageCms`, and caches LUTs by profile and CMM version.

Output modes:

1. `camera_rgb_with_input_icc`: Maintains pixels in camera RGB and embeds the
   input ICC profile generated for the session. It is the master TIFF mode
   when there is a color chart.
2. `converted_srgb`: Use `cctiff` as CMM to transform from ICC profile
   input to a standard sRGB output profile. There are equivalent modes
   `converted_adobe_rgb` and `converted_prophoto_rgb`.
3. `standard_<espacio>_output_icc`: for sessions without a letter. There is no ICC
   metered input; ProbRAW saves the manual recipe, reveals the RAW in sRGB,
   Adobe RGB (1998) or ProPhoto RGB with LibRaw, copies a real standard ICC into
   `00_configuraciones/profiles/standard/` (or `_profiles/` in batch CLI) and
   embeds as output profile. `assigned_<espacio>_output_icc` is preserved
   just as old metadata compatibility.

The complete methodology is documented in
[`docs/METODOLOGIA_COLOR_RAW.md`](METODOLOGIA_COLOR_RAW.md).

## Local validation
```bash
probraw develop /ruta/a/captura.dng \
  --recipe testdata/recipes/scientific_recipe.yml \
  --out /tmp/dev_out.tiff \
  --audit-linear /tmp/dev_linear.tiff
```

```bash
probraw auto-profile-batch \
  --charts testdata/batch_images \
  --targets testdata/batch_images \
  --recipe testdata/recipes/scientific_recipe.yml \
  --reference testdata/references/colorchecker24_colorchecker2005_d50.json \
  --profile-out /tmp/camera_profile.icc \
  --profile-report /tmp/profile_report.json \
  --out /tmp/batch_out \
  --workdir /tmp/work_auto \
  --min-confidence 0.0
```
## Common errors

- `No se puede revelar RAW: dependencia 'rawpy'/'LibRaw' no disponible.`
  - Solution: reinstall the package or run `pip install -e .`.
- `colprof no esta en PATH`
  - Solution: install `argyll`.
- `No se puede convertir ICC: 'cctiff' de ArgyllCMS no esta disponible en PATH.`
  - Solution: install full ArgyllCMS and check `cctiff -?`.

## C2PA/CAI integration

ProbRAW requires ProbRAW Proof to sign final TIFFs and declare a link
RAW -> TIFF based on SHA-256 of the original RAW. C2PA/CAI remains as a layer
optional interoperable if there is a compatible certificate. No layer replaces
sidecars or `batch_manifest.json`.

See:

- `docs/C2PA_CAI.md`
