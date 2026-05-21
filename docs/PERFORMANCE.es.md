_English version: [PERFORMANCE.md](PERFORMANCE.md)_

# Performance

Este documento recoge la politica practica de medicion de rendimiento en
ProbRAW. Las optimizaciones que afecten al flujo canonico deben conservar los
bytes del TIFF firmado salvo que se documenten como cambio de reproducibilidad.

Regla de precision colorimetrica: una mejora de rendimiento no puede cambiar la
apariencia de la previsualizacion, la ruta `ICC fuente -> ICC monitor`, la
precision de los valores RGB mostrados ni los bytes de salida canonica. Las
optimizaciones aceptables eliminan trabajo redundante, reducen asignaciones,
reutilizan caches o mueven trabajo fuera del hilo de interfaz, pero no sustituyen
calculos colorimetricos por aproximaciones que alteren la imagen.

El plan complementario de implementacion se mantiene en
[Plan de mejoras de rendimiento](PERFORMANCE_IMPROVEMENTS.es.md). Ese documento
recoge optimizaciones candidatas de visualizacion/cache y sus requisitos de
validacion antes de poder fusionarlas.

## Herramientas

Perfil granular de comandos reales:

```powershell
python scripts/profile_pipeline.py --out-dir .\profile-out --top 80 -- batch-develop .\raws --recipe .\recipe.yml --profile .\camera.icc --out .\out --workers 1
```

El script escribe:

- `profile.txt`: salida de `cProfile` ordenada por tiempo acumulado.
- `profile.svg`: flamegraph de `py-spy` si esta instalado.

Para comparar batch serial contra paralelo, ejecutar el mismo comando cambiando
solo `--workers 1` por `--workers 0` o por un numero fijo.

Benchmark RAW reproducible en Windows, macOS y Linux:

```powershell
python scripts/benchmark_raw_pipeline.py .\ruta\a\captura.NEF --out .\tmp\raw_benchmark\results.json --cache-dir .\tmp\raw_benchmark\cache --algorithms linear,dcb,amaze --cache-algorithm dcb --process-jobs 4 --process-workers 1,2,4
```

El script mide tiempo de pared, CPU, shape/dtype, tamano del array y pico de
memoria residente del proceso cuando el sistema operativo lo expone.

Benchmark de fluidez GUI:

```powershell
$env:QT_QPA_PLATFORM="offscreen"
python scripts/benchmark_gui_interaction.py --raw .\ruta\a\captura.NEF --algorithm dcb --full-resolution --out .\tmp\gui_benchmark\d850_full_ui.json
```

Comparacion automatica de regresiones a partir de JSON ya generados:

```powershell
python scripts/check_performance_regression.py --baseline-raw .\baseline\raw.json --current-raw .\tmp\raw_benchmark\results.json --baseline-gui .\baseline\gui.json --current-gui .\tmp\gui_benchmark\d850_full_ui.json --tolerance 0.20
```

Este test simula arrastres reales de slider y curva tonal. Mide:

- coste inmediato de `setValue`/emision de puntos de curva,
- p95/p99/max de huecos del event loop Qt,
- tiempo de la ultima preview interactiva,
- hilos pendientes al terminar.

## Politica de workers

`batch-develop` y la fase batch de `auto-profile-batch` aceptan `--workers`.

- Omitido o `0`: seleccion automatica segun CPU y RAM.
- `1`: ejecucion serial para depuracion y regresion.
- `N > 1`: paralelismo real por proceso, acotado por el numero de archivos.

La salida se mantiene estable porque el manifiesto conserva el orden planificado
de entrada, no el orden de finalizacion de los trabajadores.

Si se inyecta un cliente C2PA Python no serializable, el lote usa hilos como
fallback conservador. La ruta normal de CLI usa procesos.

Variables de control:

- `PROBRAW_BATCH_WORKERS`: workers por defecto.
- `PROBRAW_BATCH_MEMORY_RESERVE_MB`: RAM libre reservada antes de calcular
  workers automaticos.
- `PROBRAW_BATCH_WORKER_RAM_MB`: presupuesto estimado por worker.
  Por defecto son 2800 MiB, ajustado a partir de una D850 de 45,7 MP: el
  demosaico DCB consume ~1,52 GiB por proceso y el batch real necesita margen
  adicional para escribir TIFF lineal/final.
- `PROBRAW_TIFF_MAXWORKERS`: hilos de compresion por TIFF para `tifffile`.
  Si se omite, ProbRAW reparte CPU automaticamente en lotes comprimidos; en una
  exportacion individual `tifffile` mantiene su modo automatico.

Desde la serie posterior, el modo automatico ajusta ese presupuesto usando el
tamano de las capturas y el algoritmo de demosaico. `PROBRAW_BATCH_WORKER_RAM_MB`
sigue teniendo prioridad para fijar un valor manual.

El perfilado de cartas tambien puede paralelizar la fase de revelar/detectar/
muestrear:

```powershell
python -m probraw auto-profile-batch --charts .\cartas --targets .\raws --recipe .\recipe.yml --reference colorchecker24_colorchecker2005_d50.json --profile-out .\camera.icc --profile-report .\profile_report.json --out .\out --workdir .\work --profile-workers 4
```

`--profile-artifacts minimal` conserva detecciones y muestras JSON, pero omite
TIFFs desarrollados y overlays PNG intermedios para medir o ejecutar sesiones
rapidas. El modo por defecto `full` mantiene todos los artefactos de auditoria.

## Cache numerica de demosaico

La cache de demosaico es opt-in. Se activa en receta con:

```yaml
use_cache: true
```

Y puede ubicarse desde CLI con `develop`, `batch-develop` y
`auto-profile-batch`:

```powershell
python -m probraw batch-develop .\01_ORG --recipe .\recipe.yml --profile .\camera.icc --out .\02_DRV --cache-dir .\00_configuraciones\cache
```

Si no se indica `--cache-dir`, ProbRAW intenta usar
`00_configuraciones/cache/` de la sesion. Si no puede inferir una sesion, usa
`~/.probraw/cache/`.

La clave incluye SHA-256 completo del RAW, algoritmo de demosaico, balance de
blancos, modo de negro y firma del backend rawpy/LibRaw. No incluye ajustes de
render que se aplican despues de la escena lineal, como exposicion o curva.

La poda LRU se controla con `PROBRAW_DEMOSAIC_CACHE_MAX_GB` y por defecto
limita la cache a 5 GiB.

## Goldens canonicos

Los tests de `tests/regression/` validan SHA-256 canonicos de salida y TIFF
lineal de auditoria. La receta golden fuerza `use_cache: false` para que la
regresion mida bytes canonicos, no comportamiento de cache.

Regeneracion intencional:

```powershell
python scripts/regenerate_golden_hashes.py --confirm --note "motivo del cambio"
```

Una regeneracion debe ir acompanada de explicacion en changelog si cambia la
reproducibilidad.

## Benchmark local D850

Equipo usado: Windows 11, Python 3.12.4, 32 hilos logicos, RAW Nikon D850
8288x5520 de 51,5 MiB aportado localmente para benchmark. El RAW no forma
parte del repositorio.

| Caso | Tiempo |
| --- | ---: |
| Demosaico `linear` completo | 1,52 s |
| Demosaico `dcb` completo | 5,36 s |
| Demosaico `amaze` completo | 5,57 s |
| Cache populate `dcb` | 5,63 s |
| Cache hit `dcb` | 0,16 s |
| Preview half-size `dcb` | 0,85-0,88 s |
| CLI `develop` sin cache, audit + TIFF final | 7,24 s |
| CLI `develop` con cache hit, audit + TIFF final | 1,59 s |

Benchmark GUI con el mismo RAW, Qt `offscreen`, 80 pasos por control:

| Fuente | Control | p95 evento UI | p95 event loop | max event loop | Preview final |
| --- | --- | ---: | ---: | ---: | ---: |
| D850 half-size 2760x4144 | brillo | 0,063 ms | 16,84 ms | 55,32 ms | 272 ms |
| D850 half-size 2760x4144 | curva tonal | 0,128 ms | 16,87 ms | 49,41 ms | 434 ms |
| D850 completa 5520x8288 | brillo | 0,053 ms | 16,72 ms | 58,94 ms | 275 ms |
| D850 completa 5520x8288 | curva tonal | 0,094 ms | 16,78 ms | 49,51 ms | 443 ms |

Antes de encolar el refresco final pesado, el max del event loop al soltar
controles llegaba a ~0,6-1,0 s en half-size. Tras el cambio queda alrededor de
50-60 ms y el trabajo pesado aparece como preview final asincrona.

Escalado de demosaico `dcb` por procesos:

| Jobs | Workers | Tiempo total | Pico por worker |
| ---: | ---: | ---: | ---: |
| 4 | 1 | 21,31 s | ~1,52 GiB |
| 4 | 4 | 5,97 s | ~1,52 GiB |
| 8 | 8 | 7,17 s | ~1,52 GiB |

Conclusion operativa: el demosaico escala bien por procesos, pero la seleccion
automatica debe limitarse por RAM. En batch real cada worker necesita mas margen
que el demosaico aislado porque tambien genera TIFF lineal y final.

## Preview con gestion ICC

La ruta de preview colorimetrica evita la miniatura embebida cuando hay ICC de
sesion o perfil generico, porque esa miniatura puede estar ya cocinada en otro
espacio y no sirve para validar color. Para que esto no bloquee al ajustar
curvas:

- ninguna imagen gestionada queda sin perfil de entrada; si no hay ICC de
  sesion/imagen, la preview usa un perfil generico real;
- la carga usa revelado LibRaw acotado por `PREVIEW_AUTO_BASE_MAX_SIDE`, salvo
  precision 1:1, comparar o marcado de carta;
- a 100%, sliders y curvas actualizan el recorte visible y copian solo regiones
  del `QImage` cuando es posible;
- la conversion visible se mantiene como `ICC fuente -> ICC monitor`; las LUT
  densas de 8 bits se generan con LittleCMS, se cachean en RAM/disco y aceleran
  la transformacion sin cambiar el resultado;
- las curvas reutilizan LUTs tonales y comparten la cuantizacion RGB antes de
  aplicar las conversiones ICC para pantalla e instrumentos;
- la preview final pesada se ejecuta en un worker asincrono cuando la imagen
  supera 2 MP;
- un watchdog abandona workers interactivos que no responden y reanuda la cola
  de ajustes para evitar que la interfaz quede atrapada en "Ajustando...".

Benchmark GUI real con `G:\ProbRAW-TEST\01_ORG\f_16,0.NEF`, DCB, 100%,
ProPhoto RGB, ICC de monitor y overlay activo:

| Control | Ultima preview visible |
| --- | ---: |
| Brillo/cambios normales | ~41-44 ms |
| Curva tonal | ~62 ms |

Esto preserva la seriedad de la gestion de color y reduce los bloqueos largos
sin sacrificar colorimetria ni nitidez.

### Carga rapida y geometria de visor

La ruta de carga reciente toma varias ideas de visores rapidos como Gwenview,
pero las adapta a las restricciones colorimetricas de ProbRAW:

- las imagenes no RAW usan decodificacion escalada con Pillow (`draft` +
  `thumbnail`) antes de convertir a `float32`, evitando decodificar el archivo
  completo cuando el visor solo necesita una preview acotada;
- los RAW muestran una preview embebida provisional en 8 bits mientras el
  revelado LibRaw final sigue en segundo plano;
- esa preview embebida se cachea por archivo, tamano solicitado y politica de
  orientacion, y se muestra con la misma ruta ICC de pantalla que el resto del
  visor;
- la preview embebida provisional mantiene la orientacion de sensor para
  coincidir con el revelado final `rawpy`/LibRaw configurado con `user_flip=0`,
  evitando saltos de rotacion cuando llega la imagen definitiva;
- una nueva solicitud de carga invalida la tarea en vuelo y permite que los
  resultados obsoletos solo alimenten cache, sin tocar la imagen visible;
- tras cargar una imagen se precalculan previews adyacentes de la tira de
  miniaturas cuando no compiten con la carga activa;
- la cache de preview lista para pantalla evita repetir ajustes, conversion ICC
  de monitor y cuantizacion cuando no cambia la receta visible.

La geometria de visor (recorte, nivelado y giros de 90 grados) se guarda en la
mochila RAW como parte de los ajustes de render. Antes de cambiar de archivo,
ProbRAW vacia cualquier guardado pendiente para que el giro aplicado al RAW
actual no pueda persistirse accidentalmente sobre el siguiente RAW seleccionado.
Los archivos sin mochila, o con mochilas parciales sin bloque de geometria,
restablecen siempre giro y recorte a cero.

La ruta MTF no cambia sus calculos ni sus graficas. El nucleo numerico
`probraw.analysis.mtf` no participa en esta optimizacion; la unica interaccion
relacionada es la invalidacion de la cache de mochila despues de guardar MTF,
para que los indicadores de miniatura y las comparaciones lean el sidecar
actualizado. Las regresiones cubren ROI, recorte full-res, auto-nitidez,
persistencia MTF y widgets ESF/LSF/MTF/CA.

### Preview interactiva 0.3.11

La ruta interactiva vuelve a usar fuentes proxy acotadas durante arrastres de
color, contraste, curvas y nitidez cuando el visor no esta en una inspeccion
real 1:1. Esto recupera la agilidad observada en la serie 0.3.8 sin volver a
confundir una preview cacheada con pixeles reales.

Reglas operativas:

- si el visor esta a escala real y la fuente cargada contiene pixeles reales, la
  preview de nitidez trabaja sobre el viewport 1:1 sin downscale;
- si el usuario pide detalle real pero la pantalla actual viene de un proxy, se
  fuerza la fuente completa antes de analizar;
- si el RAW cargado procede de cache reducida, el viewport no se marca como
  real-pixel aunque la escala visual sea 100%;
- los cambios de zoom o encuadre reprograman la preview visible para que los
  ajustes activos se apliquen a toda la region que el usuario esta viendo.

Benchmark sintetico local tras el cambio:

| Caso | Antes | Despues |
| --- | ---: | ---: |
| Nitidez 2160x3240 | ~530 ms | ~91 ms |
| Nitidez 4000x6000 | ~1,75 s | ~86 ms |
| Color/curvas | ~20-62 ms | ~20-62 ms |

## Estrategia MTF RAW y visor global de operaciones

Problema detectado: el analisis MTF frio sobre RAW obliga a obtener una imagen
a resolucion real. Con `rawpy.postprocess()` no hay una API Python estable para
pedir solo un recorte revelado; por tanto, desarrollar el RAW completo dentro
del hilo de interfaz bloqueaba la aplicacion y podia provocar consumo alto de
memoria en ficheros grandes.

Investigacion aplicada:

- Imatest SFR trabaja el resultado MTF sobre ROI/crops de borde inclinado; esta
  es la unidad analitica natural del calculo, no la imagen completa.
- `rawpy` expone `postprocess()` para el RAW completo y `extract_thumb()` para
  previews embebidas, pero no un parametro de crop en la API documentada.
- LibRaw documenta `cropbox` y estructuras de recorte, pero esa ruta no queda
  expuesta de forma portable por `rawpy` y tiene implicaciones por formato RAW.
- darktable separa miniaturas/previews/cache por niveles de resolucion y usa
  cache persistente para evitar repetir trabajo pesado.

Decision implementada:

- El analisis MTF se limita a la ROI seleccionada y a un margen alrededor del
  borde. La imagen completa solo se revela cuando la ROI full-res no esta en
  cache.
- La preparacion de la ROI full-res se ejecuta en un proceso externo
  (`python -m probraw.analysis.mtf_roi`) para aislar CPU/RAM y evitar que la UI
  quede bloqueada si LibRaw necesita memoria temporal.
- La ROI full-res se guarda como bloque `.npz` pequeno en cache persistente con
  clave derivada del RAW, receta, dimensiones y ROI. Los recalculos posteriores
  de ESF/LSF/MTF trabajan sobre ese bloque.
- El recálculo automatico se pospone si la ROI full-res esta fria; el usuario
  debe pulsar `Actualizar` para iniciar el coste pesado de forma explicita.
- Con la ROI full-res caliente, los controles de nitidez refrescan ESF/LSF/MTF
  mediante throttle interactivo. El temporizador pendiente no se reinicia en
  cada evento de slider, de modo que las graficas pueden actualizarse durante el
  arrastre y no solo al soltar el control.
- La barra superior de ProbRAW pasa a ser un visor global de operaciones largas:
  MTF, carga de preview RAW y tareas de fondo publican estado, tiempo
  transcurrido, estimacion, tiempo restante y fase. La regla operativa es usarla
  para trabajos previstos o reales por encima de ~1 segundo. La pestaña
  `Nitidez` no duplica ya una segunda barra local de progreso.

Muestras visuales del visor global:

![Carga de preview RAW con estimacion global](assets/screenshots/probraw-global-operation-preview.png)

![Preparacion MTF de ROI full-res con estimacion global](assets/screenshots/probraw-global-operation-mtf.png)

Mediciones locales con 11 NEF de prueba:

| Caso | Resultado |
| --- | ---: |
| Miniaturas RAW frias, 11 archivos | ~1,10 s |
| Preview RAW `DSC_0312.NEF` tras optimizacion | ~2,95 s, pico ~957 MB |
| MTF frio: retorno del clic | ~0,08-0,13 s |
| MTF frio: worker ROI full-res | ~6,3-6,7 s |
| MTF caliente desde cache ROI | ~0,07-0,11 s |

Prueba real de MTF fria:

```text
call_return_seconds: 0.125
worker_wait_seconds: 6.718
mtf50: 0.117308
```

Alternativas evaluadas:

- ROI Bayer directa con demosaico OpenCV local: dio tiempos cercanos a 0,13 s en
  una ROI concreta, pero el MTF50 vario respecto al pipeline full-res
  (`~0,106` frente a `~0,117`). Se conserva como linea futura para modo
  "borrador/provisional", no como resultado canonico.
- Intentar recorte RAW real desde `rawpy`: descartado en esta fase porque la API
  documentada no expone crop de `postprocess()` y una integracion C++ directa
  con LibRaw aumentaria el coste de mantenimiento.

Referencias:

- Imatest SFR instructions: https://www.imatest.com/docs/sfr_instructions2/
- Imatest Bayer RAW SFR notes: https://imatest.atlassian.net/wiki/spaces/KB/pages/10882547817/SFR%2Bresults%2Bfrom%2BBayer%2Braw%2Bimages/
- rawpy `RawPy.postprocess()` / `extract_thumb()`: https://letmaik.github.io/rawpy/api/rawpy.RawPy.html
- rawpy `Params`: https://letmaik.github.io/rawpy/api/rawpy.Params.html
- LibRaw API notes, memoria y buffers: https://www.libraw.org/docs/API-notes.html
- LibRaw data structures, `cropbox`: https://www.libraw.org/docs/API-datastruct.html
- darktable thumbnail cache: https://docs.darktable.org/usermanual/3.6/en/special-topics/program-invocation/darktable-generate-cache/

## Cambios aplicados

- El muestreo de parches de carta usa mascaras locales por bounding box, no una
  mascara del tamano completo de la imagen por parche.
- La fase de perfilado puede procesar capturas de carta en paralelo por procesos
  y permite omitir artefactos de imagen intermedios con `--profile-artifacts
  minimal`.
- La clave de cache de demosaico reutiliza en memoria el SHA-256 del RAW cuando
  `(ruta, tamano, mtime_ns)` no cambia, evitando relecturas completas en hits
  sucesivos. Para rehash estricto en entornos de auditoria, desactivar con
  `PROBRAW_RAW_SHA_CACHE=0`.
- El calculo automatico de workers batch estima memoria por tamano de captura y
  algoritmo, mantiene un suelo conservador para RAWs comprimidos y respeta los
  overrides por variable de entorno.
- El analisis MTF evita construir mallas `x/y` completas separadas para las
  distancias de ESF/CA.
- La cache de previews escribe solo los niveles reducidos mas cercanos a la
  resolucion solicitada para limitar CPU/IO en la primera carga.
- La exportacion ICC mantiene ArgyllCMS `cctiff` como unica ruta canonica para
  no degradar precision tonal en salidas TIFF16.
- `scripts/check_performance_regression.py` compara JSON de benchmarks contra
  una linea base y falla si alguna metrica supera la tolerancia configurada.
- Los histogramas y el panel de analisis de preview muestrean antes de convertir
  y recortar arrays grandes. Esto reduce copias temporales al trabajar con
  previews 1:1 sin tocar el render canonico.
- Las llamadas externas de diagnostico basico (`exiftool`, `git rev-parse`)
  tienen timeout para evitar bloqueos indefinidos.
- La preview ICC usa ahora LittleCMS2 via Pillow `ImageCms`; `xicclu` permanece
  en la ruta de validacion de perfiles ICC generados.
- El batch de revelado ya no usa hilos para trabajo CPU-bound salvo fallback
  C2PA; cada imagen se procesa en un proceso independiente.
- El resultado numerico del demosaico puede persistirse como `.npy` para evitar
  repetir LibRaw cuando solo cambian ajustes posteriores.
- La escritura TIFF16 usa menos temporales intermedios que la expresion
  `round(clip(x) * 65535).astype(uint16)`.
- El analisis MTF frio se mueve a un worker externo con cache persistente de ROI
  full-res, y los tiempos se publican en el visor global de operaciones.
- La carga de preview RAW publica progreso global cuando la estimacion o el
  tiempo real superan aproximadamente un segundo.
