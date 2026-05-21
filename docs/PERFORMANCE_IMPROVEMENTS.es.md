_English version: [PERFORMANCE_IMPROVEMENTS.md](PERFORMANCE_IMPROVEMENTS.md)_

# Plan de mejoras de rendimiento

Analisis y plan de implementacion de mejoras de rendimiento para ProbRAW sin
alterar la correccion cientifica ni los bytes canonicos de salida.

**Fecha de analisis:** 2026-05-07  
**Version base:** 0.3.16  
**Analista:** Claude Sonnet 4.6

---

## Regla fundamental

Las rutas canonicas (`pipeline.py -> render_recipe_output_array`, `write_tiff16`,
`export.py`) **no se modifican**. Todas las mejoras propuestas se aplican solo a
**rutas de visualizacion**, **gestion de cache de demosaico** y **operaciones
repetidas en sesiones GUI**.

Cualquier cambio que afecte a los bytes de salida canonica debe documentarse
como cambio de reproducibilidad (ver `REPRODUCIBILITY.es.md`) y obliga a
regenerar hashes golden.

---

## Contexto: optimizaciones ya existentes

Antes de estas mejoras, ProbRAW ya dispone de:

- cache LRU de demosaico (`.npy`, clave SHA-256, limite de 5 GiB);
- `ProcessPoolExecutor` para lote con numero de workers calculado por RAM;
- worker asincrono de preview final para imagenes mayores de 2 MP;
- curva tonal por LUT con `@lru_cache(maxsize=512)`;
- ruta rapida `render_adjustments_affine_u8` para ajustes afines;
- proceso externo para preparar ROI MTF fria;
- proxy acotado durante arrastre y preview completa al soltar;
- cache `_RAW_SHA_CACHE` en proceso para claves de demosaico;
- `@lru_cache` en `_cct_linear_srgb_white`;
- LUT ICC densa de 8 bits en RAM y disco para transformaciones de pantalla.

Las mejoras siguientes atacan las rutas calientes que aun no estaban cubiertas.

---

## Linea base de benchmark

RAW Nikon D850, 8288x5520, 51,5 MiB:

| Caso | Tiempo |
|------|-----:|
| Demosaico `linear` completo | 1,52 s |
| Demosaico `dcb` completo | 5,36 s |
| Demosaico `amaze` completo | 5,57 s |
| Poblar cache `dcb` | 5,63 s |
| Hit de cache `dcb` | 0,16 s |
| Preview half-size `dcb` | 0,85-0,88 s |
| Preview interactiva, brillo | ~41-44 ms |
| Preview interactiva, curva tonal | ~62 ms |
| Preview final D850 half-size | 272-443 ms |

---

## Mejora 1: LUT precalculada para `linear_to_srgb_display_u8`

**Archivos:** `src/probraw/raw/_srgb_lut.py` nuevo y
`src/probraw/raw/preview.py`

**Funciones:** `linear_to_srgb_display_u8`, `linear_to_srgb_display`

### Problema

Cada creacion de buffer `QImage` llama a `linear_to_srgb_display_u8` sobre la
imagen de preview completa. La implementacion actual ejecuta `np.power`, mascara
booleana, `np.where` y redondeo escalar: seis operaciones vectorizadas grandes
sobre una imagen `float32`.

En una preview half-size de D850 (2760x4144x3):

- acceso actual a memoria: ~6 x 130 MB, aproximadamente 780 MB;
- con LUT `uint8` de 65536 entradas: cuantizacion a `uint16` y busqueda en tabla,
  aproximadamente 40 MB.

### Cambio propuesto

Crear `src/probraw/raw/_srgb_lut.py` con LUTs inmutables `SRGB_ENCODE_U8_LUT` y
`SRGB_ENCODE_F32_LUT`, calculadas con la misma OETF sRGB. En `preview.py`,
convertir la imagen lineal a indices `uint16` y consultar la LUT.

### Impacto esperado

Reduccion aproximada del 40-55 % en la conversion de pantalla usada por la ruta
de preview interactiva.

### Seguridad

La formula es la misma. La cuantizacion de 1/65535 queda muy por debajo de la
cuantizacion final `uint8` de 1/255. Es ruta de visualizacion; los TIFF canonicos
no cambian.

---

## Mejora 2: cache de mapas radiales para correccion CA lateral

**Archivo:** `src/probraw/raw/preview.py`

**Funciones:** `_scale_channel_radially`, `apply_lateral_chromatic_aberration`

### Problema

`apply_lateral_chromatic_aberration` llama a `_scale_channel_radially` para los
canales rojo y azul. Cada llamada crea `np.indices((h, w), dtype=np.float32)`;
en una preview D850 half-size eso implica dos arrays de 91 MB para coordenadas,
mas mapas adicionales. El coste se repite mientras el usuario arrastra el
control de aberracion cromatica.

El mapa depende solo de `(h, w, scale)`. Durante una sesion GUI el tamano de la
imagen suele ser estable.

### Cambio propuesto

Mantener una cache acotada `_RADIAL_MAP_CACHE` con clave
`(alto, ancho, escala_redondeada)`. El primer uso calcula `map_x` y `map_y`; los
siguientes reutilizan los mapas y llaman directamente a `cv2.remap`.

### Impacto esperado

El primer uso no cambia. Las llamadas repetidas con mismo tamano y escala evitan
centenares de MB de asignaciones y el coste de `np.indices`.

### Presupuesto de memoria

Ocho entradas pueden llegar a unos 730 MB en D850 half-size. En equipos con poca
RAM, reducir el limite a cuatro entradas.

---

## Mejora 3: limitacion de frecuencia para `_prune_demosaic_cache`

**Archivo:** `src/probraw/raw/pipeline.py`

**Funcion:** `_prune_demosaic_cache`

### Problema

La poda de cache se ejecuta de forma sincrona despues de cada escritura. En un
lote de N archivos con cache activa, eso implica N recorridos completos del
directorio (`glob` y `stat`). Con 50 imagenes y 200 entradas de cache se producen
unos 10.000 `stat` redundantes.

### Cambio propuesto

Guardar el ultimo instante de poda por raiz de cache y no repetir el escaneo si
no han pasado 120 segundos. En lote multiproceso cada worker conserva su propio
estado, de modo que el limite practico pasa de N escaneos a como maximo W
escaneos por intervalo.

### Impacto esperado

Reduce IO redundante en lotes con cache, sin tocar el resultado numerico.

### Seguridad

La poda es solo mantenimiento. Retrasarla hasta 120 segundos no afecta a la
salida cientifica; la cache solo puede exceder temporalmente el limite por un
ciclo de escritura.

---

## Mejora 4: menos asignaciones en `_apply_vibrance_saturation`

**Archivo:** `src/probraw/raw/preview.py`

**Funcion:** `_apply_vibrance_saturation`

### Problema

Se ejecuta en cada frame interactivo cuando `vibrance != 0` o
`saturation != 0`. En una imagen `float32` de 2760x4144x3 crea varios arrays
intermedios grandes: copia, luminancia, crominancia, factor de vibrance,
diferencias, producto y resultado ajustado.

### Cambio propuesto

Calcular luminancia con combinacion explicita de canales, reutilizar el buffer de
croma como factor combinado, y aplicar la formula
`out = luma + (out - luma) * factor` in-place sobre una copia de trabajo.

### Impacto esperado

Reduce asignaciones grandes y baja el pico de RAM en la ruta de preview
interactiva. En D850 half-size puede ahorrar alrededor de 260 MB por llamada.

### Seguridad

La operacion se realiza sobre una copia fresca de la imagen de entrada. La
formula es algebraicamente equivalente a la actual.

---

## Mejora 5: microoptimizacion de `suppress_false_color`

**Archivo:** `src/probraw/raw/pipeline.py`

**Funcion:** `suppress_false_color`

### Problema

El bucle por pasada usa `np.tensordot` para una forma pequena y crea varios
arrays grandes por iteracion, incluido un `np.stack` final para recomponer los
canales.

### Cambio propuesto

Calcular luminancia con combinacion explicita de canales y escribir rojo, verde
y azul de vuelta en el array `out` preasignado, evitando el `np.stack`.

### Impacto esperado

Elimina una asignacion grande por pasada. En una D850 completa con tres pasadas
puede ahorrar alrededor de 390 MB de asignaciones acumuladas.

### Seguridad

Las asignaciones por canal escriben en vistas del buffer `out`. Los cromas
filtrados por `cv2.medianBlur` no aliasan ese buffer, por lo que no hay
sobrescritura accidental.

---

## Resumen de cambios

| # | Archivo | Funcion(es) | Tipo | Impacto |
|---|------|-------------|------|--------|
| 1 | `raw/_srgb_lut.py` nuevo + `raw/preview.py` | `linear_to_srgb_display_u8`, `linear_to_srgb_display` | LUT precalculada | Alto, cada frame de pantalla |
| 2 | `raw/preview.py` | `_scale_channel_radially` | Cache de mapas | Alto, slider CA |
| 3 | `raw/pipeline.py` | `_prune_demosaic_cache` | Limitacion de escaneo en disco | Medio, lote con cache |
| 4 | `raw/preview.py` | `_apply_vibrance_saturation` | NumPy in-place | Medio, preview interactiva |
| 5 | `raw/pipeline.py` | `suppress_false_color` | NumPy in-place | Bajo-medio, funcion opcional |

## Que no se modifica

- `_apply_srgb_oetf`, usado por salida canonica.
- `write_tiff16`.
- `render_recipe_output_array`.
- `_process_batch_develop_job`.
- `apply_profile_matrix`.
- `_apply_srgb_lut`, ya vectorizada para preview ICC.
- `tone_curve_lut` / `apply_tone_curve`, ya basadas en LUT con `lru_cache`.

Los bytes del TIFF firmado, las firmas ProbRAW Proof y los hashes SHA-256
canonicos deben permanecer identicos tras estas mejoras.

---

## Plan de validacion

Antes de fusionar cada mejora:

1. Ejecutar `pytest tests/`; toda la suite debe pasar.
2. Ejecutar `pytest tests/regression/`; los hashes golden canonicos deben
   coincidir.
3. Ejecutar `python scripts/benchmark_gui_interaction.py` y comparar tiempos de
   preview interactiva contra la linea base.
4. Para las mejoras 4 y 5, comparar arrays de salida con `np.allclose` frente a
   las funciones originales usando imagenes representativas.
