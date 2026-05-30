# Integración de LibRaw y ArgyllCMS en ProbRAW

## Objetivo

ProbRAW usa un único motor de revelado RAW:

- **LibRaw**, mediante la dependencia Python `rawpy`, para decodificación e
  interpolación RAW.
- **ArgyllCMS** (`colprof`) como motor de generación de perfiles ICC.
- **ArgyllCMS** (`xicclu`/`icclu`) como herramienta de validación del ICC real
  generado.
- **LittleCMS2**, vía Pillow `ImageCms`, como CMM de previsualización ICC.
- **ArgyllCMS** (`cctiff`) se conserva por ahora para conversiones ICC de
  salida explícitas.

La meta es mantener un flujo científico reproducible y auditable con menos
ramas de código y sin mapeos implícitos entre motores RAW distintos.

## Instalación del sistema

Para usuarios finales, las dependencias externas deben llegar mediante los
instaladores de ProbRAW. La instalacion manual siguiente queda reservada a
desarrollo, CI o entornos de prueba.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .[gui]
sudo apt-get install -y argyll exiftool
```

En macOS con Homebrew:

```bash
brew install argyll-cms exiftool
```

`rawpy`/LibRaw se instala como dependencia Python del proyecto. Para AMaZE se
requiere una build GPL3 con `DEMOSAIC_PACK_GPL3=True`; ver
`docs/AMAZE_GPL3.md`.

Verificación:

```bash
bash scripts/check_tools.sh
probraw check-tools --strict --out tools_report.json
```

`probraw check-tools` registra disponibilidad de ArgyllCMS y `exiftool`.
`probraw check-color-environment` registra además LittleCMS2, Qt/PySide,
colord, Wayland/KWin y perfiles ICC del sistema. Las versiones de `rawpy` y
LibRaw quedan registradas en el contexto de ejecución (`run_context`).

## Integración LibRaw/rawpy

Archivo clave:

- `src/probraw/raw/pipeline.py`

Para entradas RAW, ProbRAW ejecuta `rawpy.imread(...).postprocess(...)` con un
contrato explícito:

- salida de 16 bit,
- `gamma=(1, 1)` para mantener salida lineal,
- `no_auto_bright=True`,
- `highlight_mode=Clip`,
- `user_flip=0`,
- `output_color=raw` para conservar RGB de cámara,
- balance de blancos desde metadatos o multiplicadores fijos según receta,
- black/white level manual solo si la receta lo declara.

Mapeo de `recipe`:

- `raw_developer`: debe ser `libraw`.
- `demosaic_algorithm`: valores soportados por `rawpy`, entre ellos `dcb`,
  `dht`, `ahd`, `vng`, `ppg`, `linear` y, si la build lo incluye, `amaze`.
- `white_balance_mode` + `wb_multipliers`: `camera_metadata` o `fixed`.
- `black_level_mode`: opcional `fixed:<valor>` o `white:<valor>`.

DCB (`demosaic_algorithm: dcb`) es el valor por defecto porque ofrece alta
calidad y funciona con los wheels estándar de `rawpy`. AMaZE puede usarse con
una build de `rawpy`/LibRaw compilada con el demosaic pack GPL3; si la build no
lo incluye, LibRaw devuelve un error explícito.

Regla operativa:

- no se permiten motores RAW alternativos ni mapeos silenciosos; una receta que
  pida un `raw_developer` distinto de `libraw` falla antes de procesar.
- AMaZE requiere `rawpy.flags["DEMOSAIC_PACK_GPL3"] == True`. Si no esta
  disponible, la CLI/backend fallan con error explicito y la GUI degrada la
  receta interactiva a `dcb` para no bloquear la calibracion.

En los instaladores de release, AMaZE debe verificarse durante la construccion
y de nuevo en la instalacion con `probraw check-amaze`. Un instalador que no
pueda demostrar `amaze_supported: true` no debe publicarse como build AMaZE.

## Integración ArgyllCMS

Archivo clave:

- `src/probraw/profile/builder.py`

Flujo:

1. Se construye un `.ti3` temporal con muestras y referencia.
2. Formato usado:
   - `DEVICE_CLASS "INPUT"`
   - `COLOR_REP "XYZ_RGB"`
   - campos `XYZ_X XYZ_Y XYZ_Z RGB_R RGB_G RGB_B`
3. Se ejecuta `colprof` para generar el `.icc`.

Comando base:

```bash
colprof -v -D "<descripcion>" -qm -al -u -R <base_ti3>
```

Validación:

- `validate-profile` usa `xicclu` o `icclu` para consultar el perfil ICC real
  en modo forward hacia Lab PCS.
- La matriz `matrix_camera_to_xyz` del sidecar queda como diagnóstico, no como
  sustituto de una conversión ICC real.

## CMM ICC con ArgyllCMS

Archivo clave:

- `src/probraw/profile/export.py`

Esta seccion describe la exportacion derivada actual. La previsualizacion ICC de
la GUI no usa `xicclu`/`cctiff`: construye sus transformaciones con LittleCMS2
mediante Pillow `ImageCms`, y cachea LUTs por perfil y version del CMM.

Modos de salida:

1. `camera_rgb_with_input_icc`: mantiene píxeles en RGB de cámara e incrusta el
   perfil ICC de entrada generado para la sesión. Es el modo del TIFF maestro
   cuando hay carta de color.
2. `converted_srgb`: usa `cctiff` como CMM para transformar desde el perfil ICC
   de entrada a un perfil sRGB estandar de salida. Existen modos equivalentes
   `converted_adobe_rgb` y `converted_prophoto_rgb`.
3. `standard_<espacio>_output_icc`: para sesiones sin carta. No hay ICC de
   entrada medido; ProbRAW guarda la receta manual, revela el RAW en sRGB,
   Adobe RGB (1998) o ProPhoto RGB con LibRaw, copia un ICC estandar real en
   `00_configuraciones/profiles/standard/` (o `_profiles/` en batch CLI) y lo
   incrusta como perfil de salida. `assigned_<espacio>_output_icc` se conserva
   solo como compatibilidad de metadatos antiguos.

La metodologia completa se documenta en
[`docs/METODOLOGIA_COLOR_RAW.md`](METODOLOGIA_COLOR_RAW.md).

## Validación local

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

## Errores comunes

- `No se puede revelar RAW: dependencia 'rawpy'/'LibRaw' no disponible.`
  - Solución: reinstalar el paquete o ejecutar `pip install -e .`.
- `colprof no esta en PATH`
  - Solución: instalar `argyll`.
- `No se puede convertir ICC: 'cctiff' de ArgyllCMS no esta disponible en PATH.`
  - Solución: instalar ArgyllCMS completo y verificar `cctiff -?`.

## Integracion C2PA/CAI

ProbRAW exige ProbRAW Proof para firmar TIFFs finales y declarar un vinculo
RAW -> TIFF basado en SHA-256 del RAW original. C2PA/CAI queda como capa
interoperable opcional si hay certificado compatible. Ninguna capa sustituye
los sidecars ni `batch_manifest.json`.

Ver:

- `docs/C2PA_CAI.md`
