# Architecture

## Objetivo

Pipeline científico reproducible:

`RAW -> ajuste parametrico por archivo -> mochila -> perfil avanzado con carta o perfil basico manual -> ICC de entrada o ICC generico -> cola -> TIFF 16-bit -> proof/manifiesto`

El flujo con carta mantiene la cadena tecnica completa:

`RAW carta -> develop base -> detect-chart -> sample-chart -> perfil de ajuste avanzado -> receta calibrada -> sample-chart calibrado -> build-profile ICC -> asignar perfil al RAW -> copiar/pegar a RAW equivalentes -> batch-develop`

Gobernanza y licencia:

- proyecto liderado por **Probatia Forensics SL** (https://probatia.com) en
  colaboracion con la **Asociacion Espanola de Imagen Cientifica y Forense**
  (https://imagencientifica.es).
- licencia del repositorio: `AGPL-3.0-or-later`.

## Layout del paquete

El código vive en `src/probraw/`, organizado por dominio para permitir crecer sin archivos flat de tamaño desbordante:

```text
src/probraw/
  __init__.py, __main__.py, version.py
  cli.py                       # interfaz de línea de comandos
  gui.py                       # ventana principal Qt/PySide6 y orquestación de UI
  gui_config.py                # constantes visuales, cache y compatibilidad de GUI
  workflow.py                  # orquestación end-to-end
  session.py                   # modelo y persistencia de sesiones
  sidecar.py                   # mochilas RAW.probraw.json por imagen, MTF y muestras Lab
  display_color.py             # perfil ICC de monitor por plataforma
  reporting.py                 # contexto de ejecución y trazabilidad

  core/                        # dominio compartido, sin deps cruzadas al resto
    models.py                  # dataclasses + I/O JSON
    recipe.py                  # carga de receta + scientific_guard
    color.py                   # DeltaE 76/2000
    utils.py                   # I/O imagen, hashes, TIFF 16-bit

  raw/                         # ingesta y revelado RAW
    metadata.py                # raw_info (exiftool + rawpy/LibRaw)
    pipeline.py                # develop_controlled con backend LibRaw
    preview.py                 # preview rápido + ajustes técnicos

  chart/                       # cartas de color
    detection.py               # localización + homografía + parches
    sampling.py                # muestreo robusto + ReferenceCatalog

  profile/                     # perfil ICC y export
    development.py             # perfil de revelado cientifico: WB + densidad + EV
    builder.py                 # build_profile / validate_profile (ArgyllCMS)
    gamut.py                   # diagnostico de gamut, Lab 2D y pertenencia de muestras
    generic.py                 # perfiles ICC genericos para flujos sin carta
    export.py                  # batch_develop + export ICC/CMM + matriz diagnostica

  ui/                          # widgets Qt reutilizables, sin lógica de sesión
    widgets.py                 # visor de imagen, histograma y curva tonal
    window/                    # comportamiento de ProbRawMainWindow por dominio
      layout.py                # menús, pestañas y paneles principales
      control_panels.py        # pestañas de controles de revelado/exportación
      settings.py              # diálogo global, idioma, firmas y color monitor
      display.py               # utilidades visuales, ajustes y color de pantalla
      session.py               # fachada de sesión
      session_paths.py         # rutas de proyecto, referencias y salidas
      session_development.py   # perfiles de ajuste y sidecars RAW
      session_state.py         # snapshot, activación, creación y guardado
      session_queue.py         # tabla y proceso de cola
      browser.py               # explorador, miniaturas, cachés y metadatos
      preview.py               # fachada de preview
      preview_menu.py          # acciones de menú, ayuda, QA y recetas
      preview_recipe.py        # controles de receta, histograma, curva tonal y muestras Lab
      preview_cache.py         # claves y cache de preview
      preview_load.py          # carga de imagen y precache visible
      preview_render.py        # preview interactivo, ICC y refresco final
      preview_export.py        # guardar preview y revelado individual
      profile.py               # selección de carta, perfilado ICC y marcado manual
      batch.py                 # revelado por lotes y exportación firmada
      tasks.py                 # tareas de fondo, monitor y estado global
```

## Estructura de proyecto

Una sesion ProbRAW 0.2 usa tres carpetas principales:

```text
proyecto/
  00_configuraciones/          # session.json, perfiles, ICC, reportes, cache
    cache/                     # cache numerica persistente por sesion
  01_ORG/                      # originales RAW y cartas
  02_DRV/                      # TIFF, previews, manifiestos y proof
```

Las sesiones heredadas con `charts/`, `raw/`, `profiles/`, `exports/`,
`config/` y `work/` se abren por compatibilidad. La GUI resuelve rutas antiguas
como `raw/captura.NEF` contra `01_ORG/captura.NEF` cuando existe el archivo.

## Reglas de dependencia

- `core/` no importa del resto del paquete.
- `raw/` y `chart/` dependen sólo de `core/`.
- `profile/` depende de `core/` y `raw/`.
- `workflow.py`, `cli.py`, `gui.py` orquestan — pueden importar de cualquier subpaquete, nunca al revés.
- `ui/` sólo contiene widgets y controles reutilizables; no debe conocer rutas de sesión ni ejecutar procesos RAW.
- `ui/window/` divide la ventana principal en mixins por responsabilidad; cada módulo puede depender del dominio, pero evita crear lógica nueva dentro de `gui.py`.
- `session.py` y `reporting.py` son standalone.

## Perfil ICC

- Motor único: `ArgyllCMS (colprof)`.
- Siempre se guarda sidecar `.profile.json` con matriz, recipe y métricas para reproducibilidad.
- Si hay carta, el ICC se trata como perfil de entrada de sesion y se incrusta
  en el TIFF maestro sin convertir a un espacio generico.
- Si no hay carta, ProbRAW asigna un ICC generico real como perfil de entrada de
  imagen, normalmente ProPhoto RGB. No inventa otros perfiles ni usa
  conversiones a espacios ajenos para el analisis objetivo.
- La visualizacion gestionada es directa `ICC entrada -> ICC monitor`.
- El diagnostico de muestras Lab convierte RGB de imagen a Lab mediante el ICC
  activo; solo se considera medicion rigurosa cuando ese ICC fue generado por
  ProbRAW para la sesion de captura.

## Perfiles de ajuste

- El perfil avanzado nace de carta de color, queda marcado en azul y puede
  llevar ICC de entrada de sesion asociado.
- El perfil basico nace de ajustes manuales, queda marcado en verde y puede usar
  ICC generico de entrada.
- Ambos se asignan a RAW concretos mediante mochilas y se pueden copiar/pegar
  entre miniaturas.

## Reproducibilidad

Se registra:

- versión software,
- commit hash (si aplica),
- recipe exacta,
- metadatos RAW,
- detección de carta,
- muestras por parche,
- muestras Lab por imagen con coordenada real, matriz, grupo, nombre y nota,
- DeltaE 76/2000,
- comparaciones de conjuntos de muestras: media Lab, dispersion DE00, similitud
  y gamut de muestras,
- hashes de entradas/salidas,
- manifiesto de lote.

## Rendimiento y cache

- `batch-develop` y la fase batch de `auto-profile-batch` paralelizan a nivel
  de imagen con procesos cuando `workers > 1`. El manifiesto se ordena por el
  plan de entrada, no por orden de finalizacion.
- La cache de demosaico RAW es opt-in (`use_cache: true` en receta o control
  equivalente) y guarda arrays `.npy` en `00_configuraciones/cache/demosaic/`
  cuando se puede inferir la sesion. El modo canonico de regresion usa
  `use_cache: false`.
- La clave de cache incluye nombre, tamano, SHA-256 completo del RAW,
  parametros LibRaw que afectan al demosaico/WB/negro y firma del backend
  rawpy/LibRaw. Cambiar algoritmo de demosaico invalida la entrada.
- La cache aplica poda LRU por tamano maximo. Por defecto usa 5 GiB,
  configurable con `PROBRAW_DEMOSAIC_CACHE_MAX_GB`.

## Principio clave

El perfil es condicional (cámara + óptica + iluminante + recipe + versión). No se considera universal.
