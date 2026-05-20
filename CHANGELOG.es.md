# Changelog

Todos los cambios relevantes de ProbRAW se documentan en este archivo.

Este proyecto sigue:

- formato inspirado en Keep a Changelog,
- versionado SemVer,
- trazabilidad de cambios orientada a uso científico y forense.

## Política de actualización

Para mantener trazabilidad completa, cada cambio debe:

1. añadir una línea en `Unreleased` antes de merge/push,
2. mover entradas a una versión fechada en cada release,
3. referenciar, cuando aplique, impacto en reproducibilidad, legalidad o cadena de custodia.

## [Unreleased]

Sin entradas todavia.

## [0.3.21] - 2026-05-20

### Fixed

- Corregido el fallo de generacion ICC de la release 0.3.20 cuando una carta
  marcada manualmente quedaba reservada como validacion y la captura restante
  era descartada por `fallback_detection`: las detecciones manuales se mantienen
  ahora en entrenamiento y las capturas automaticas no validas quedan como
  validacion/omision sin bloquear si hay muestras utiles.
- Corregida la dominante azul en previews con ICC de entrada generado: la
  compensacion visual de balance de camara ya no se aplica cuando la imagen se
  esta visualizando con un perfil ICC de entrada activo.
- El histograma de curva se inicializa aunque la curva este desactivada y se
  recalcula con todos los ajustes tonales y de curva, no solo con la entrada de
  la curva.
- Los cambios de curva ya no bloquean la interfaz: el histograma tonal se
  calcula en segundo plano durante el arrastre y solo se publica el ultimo
  resultado valido.

### Changed

- La QA de perfilado conserva el ICC como `draft` utilizable cuando falta una
  validacion independiente, en vez de tratarlo como error bloqueante.
- Los informes de perfilado incluyen residuo a*/b* de la fila neutra y
  recomendaciones no bloqueantes para revisar iluminacion, referencia de carta,
  modelo de perfil y validacion.
- El histograma del visor reutiliza la misma muestra colorimetrica ya calculada
  para preview cuando esta disponible, reduciendo trabajo repetido sin cambiar
  la ruta `ICC de entrada -> ICC de monitor`.

### Tests

- Anadida cobertura de regresion para reparto entrenamiento/validacion con
  detecciones manuales, cola asincrona del histograma de curva, cambios tonales
  que modifican el histograma y reutilizacion del parche colorimetrico.

## [0.3.20] - 2026-05-20

### Fixed

- Corregida la generacion de perfiles ICC desde una carta marcada manualmente
  cuando la seleccion previa de capturas seguia apuntando a otra imagen: la GUI
  prioriza ahora la captura activa y conserva la seleccion anterior solo como
  capturas adicionales.
- Corregida la activacion/creacion de sesiones para que el explorador, las
  referencias, la entrada RAW, las exportaciones TIFF y los artefactos de
  perfilado se alineen con la raiz del proyecto activo en vez de heredar rutas
  de otros proyectos.
- Los errores de perfilado ICC explican ahora por que se descartaron capturas
  de carta, incluyendo modo de deteccion, confianza, umbral y avisos
  relevantes.
- Corregido el riesgo de doble conversion en la visualizacion: cuando ProbRAW
  ya convierte la preview al ICC del monitor con LittleCMS, el `QImage` se
  entrega como RGB de dispositivo sin etiqueta `QColorSpace` adicional.

### Changed

- El TIFF lineal de auditoria se escribe antes de conversiones de salida,
  curvas tonales o codificacion final, y el sidecar conserva los parametros
  efectivos de procesado RAW usados para exportar.
- Las muestras de carta registran los parametros de muestreo usados
  (`strategy`, `trim_percent`, `reject_saturated`) para mejorar trazabilidad y
  reproducibilidad.
- La validacion del backend RAW rechaza configuraciones no soportadas en lugar
  de aplicar sustituciones silenciosas.
- La gestion de color de monitor queda documentada como una capa exclusiva de
  visualizacion: el TIFF exportado conserva el ICC de entrada seleccionado y no
  usa el perfil de monitor.
- La deteccion del perfil ICC de monitor activo queda cacheada por pantalla y
  ajustes, reduciendo consultas repetidas al sistema durante previews,
  miniaturas y refrescos interactivos.

### Tests

- Anadida cobertura de regresion para sesiones que arrastran rutas de proyectos
  antiguos, marcado manual de carta pendiente, TIFF lineal de auditoria,
  metadatos RAW en sidecar y detalle de errores de perfilado.
- Validado con `pytest -q tests/test_gui_session_paths.py -k "session"`,
  pruebas GUI puntuales de marcado manual, `pytest -q tests
  --ignore=tests/test_gui_session_paths.py` y `git diff --check`.
- Anadida cobertura para impedir que buffers ya convertidos a monitor queden
  etiquetados como `QColorSpace`, y para garantizar que fallos de conversion ICC
  de monitor no caen silenciosamente a sRGB sin gestionar.
- Build de release validada con el flujo completo del instalador Windows:
  `473 passed, 2 warnings`, checks estrictos de herramientas, smoke checks
  empaquetados CLI/C2PA/AMaZE y `rawpy-demosaic 0.10.1`.

## [0.3.19] - 2026-05-11

### Added

- Anadido empaquetado macOS en `packaging/macos/` con spec PyInstaller,
  launchers GUI/CLI y script `build_app.sh` para generar `ProbRAW.app`, CLI
  empaquetada, zip y SHA-256 desde un host macOS.
- Anadido extra opcional `macos` para instalar dependencias de build GUI,
  PyInstaller y C2PA con un unico selector.
- Documentado el flujo de instalacion/build macOS, validacion de artefactos,
  variables de AMaZE, firma opcional y recomendaciones de Python 3.11/3.12.
- Anadido empaquetado nativo Arch/CachyOS con `PKGBUILD`, script
  `packaging/arch/build_pkg.sh`, instalacion en `/opt/probraw/venv`, lanzadores
  `probraw`/`probraw-ui`, validacion `validate_cachyos_install.sh` y soporte de
  build AMaZE optimizada.
- Anadido `probraw check-color-environment` para auditar proveedor de perfil de
  pantalla, LittleCMS2, ArgyllCMS, Qt/PySide, colord, KWin/Wayland y perfiles
  ICC estandar del sistema.
- Documentada la gestion de color del sistema en Linux/Windows/macOS y el
  contrato de CMM: LittleCMS2 para preview, ArgyllCMS para creacion,
  validacion y conversiones derivadas.
- Anadido progreso de primera carga de preview y estimaciones de tiempo para
  aperturas RAW lentas.
- Anadida cobertura de regresion para carga de preview, orientacion provisional
  RAW, comportamiento MTF y escrituras pendientes de geometria en sidecar.

### Changed

- El selector de assets de actualizacion en macOS prefiere `.dmg`, `.pkg` y
  `.zip` antes de tarballs de fuente.
- Los scripts `.sh` quedan normalizados a LF mediante `.gitattributes` para
  evitar problemas al preparar builds macOS desde Windows.
- La busqueda de perfiles genericos sRGB, Adobe RGB y ProPhoto RGB usa rutas de
  sistema XDG/colord/ArgyllCMS/Homebrew y valida descripciones ICC para evitar
  seleccionar ProPhoto lineal como ProPhoto RGB gamma 1.8.
- La preview ICC de perfil usa LittleCMS2 via Pillow `ImageCms`; `xicclu`/`icclu`
  quedan para validacion del ICC generado y `cctiff` para exportaciones
  derivadas.
- Los dialogos de seleccion ICC empiezan ahora en directorios de perfiles del
  sistema cuando no hay ruta previa.
- La build `rawpy-demosaic` se adapta a toolchains actuales con CMake policy
  minima, `Cython>=3.1`, `numpy` y `np.set_array_base`.
- La carga de preview RAW puede mostrar una preview embebida provisional con
  orientacion correcta mientras se prepara el render completo.
- Las escrituras de recorte, rotacion y nivelado del visor en sidecar se
  vacian antes de cambiar de archivo para no perder geometria durante
  navegacion rapida.
- La gestion de cache de display y preview evita reconstrucciones innecesarias
  manteniendo reproducible el render TIFF final y ProbRAW Proof.

### Tests

- Validado con `bash -n packaging/macos/build_app.sh`, `python -m compileall`,
  comprobacion sintactica del spec macOS y `pytest` sobre docs/update/external.
- Validado en CachyOS con paquete instalado `probraw 0.3.18-3`: `pacman -Qkk`
  sin ficheros alterados, `validate_cachyos_install.sh`, `check-tools --strict`,
  `check-amaze` y smoke `probraw-ui` offscreen.
- Build de release Windows: `465 passed, 2 warnings`, `check-tools --strict`,
  smoke de CLI empaquetada `--version`/`--help`, `check-tools --strict`
  empaquetado, C2PA y AMaZE.

## [0.3.18] - 2026-05-07

### Fixed

- Deshacer/rehacer cambios de geometria de visor, solo recorte o nivelado, ya
  no fuerza una reconstruccion final de preview. Esto evita un cuelgue aparente
  al volver atras justo despues de reencuadrar una preview RAW grande.

### Tests

- Suite completa: `439 passed, 2 warnings`.
- Anadida cobertura de regresion para evitar refresco de preview al deshacer
  solo recorte.

## [0.3.17] - 2026-05-07

### Changed

- Reutilizados los mapas de remapeo de aberracion cromatica lateral durante
  ediciones repetidas de preview para reducir asignaciones grandes por frame.
- Reducidas las asignaciones temporales en ajustes de vibrance/saturacion de
  preview.
- Limitada por tiempo la poda de cache de demosaic tras escrituras de cache
  para evitar escaneos repetidos de directorio en sesiones batch.
- Reducidas las asignaciones temporales en la supresion local de falso color
  sin cambiar hashes canonicos de regresion.

### Tests

- Suite completa: `438 passed, 2 warnings`.
- Hashes de regresion: `2 passed`.
- Smoke benchmark GUI: `scripts/benchmark_gui_interaction.py --synthetic-size
  900x1350 --steps 8`.

## [0.3.16] - 2026-05-07

### Added

- Anadidas opciones de compresion TIFF para exportaciones finales: ninguna,
  ZIP/Deflate, LZW, JPEG y ZSTD, respaldadas por `imagecodecs`.
- Anadido control acotado de workers de compresion TIFF en GUI, CLI
  (`--tiff-workers`) y `PROBRAW_TIFF_MAXWORKERS`.
- Anadido nivelado horizontal/vertical con linea arrastrable y lectura de
  angulo en vivo.
- Anadida accion contextual en el arbol de carpetas para abrir directorios en
  el explorador del sistema.
- Anadidas barras de progreso por archivo en la tabla de cola de revelado.

### Changed

- La exportacion TIFF comprimida en lote reparte los hilos de compresion entre
  workers activos para evitar sobresaturar la CPU.
- La compresion TIFF queda registrada en ajustes de render/Proof.

### Fixed

- La exportacion con nivelado recorta el area valida de la imagen rotada para no
  escribir bordes negros en los TIFF finales.
- Las conversiones de salida de ArgyllCMS se recomprimen despues de `cctiff`
  cuando se elige un modo de compresion TIFF.

### Tests

- Suite completa: `438 passed, 2 warnings`.
- Anadida cobertura de regresion para codecs TIFF, dispatch de workers de
  compresion TIFF, nivelado arrastrable, recorte de bordes en exportacion,
  accion de abrir carpetas y barras de progreso en cola.

## [0.3.15] - 2026-05-06

### Added

- Anadido `scripts/check_performance_regression.py` para comparar JSON de
  benchmarks guardados y fallar ante regresiones configuradas.
- Anadidos controles de workers y artefactos de perfilado para flujos CLI.

### Changed

- El muestreo de cartas usa ahora mascaras locales por parche en lugar de
  mascaras de fotograma completo.
- El analisis MTF reduce temporales de memoria en las distancias ESF.
- La cache de preview puede reutilizar niveles reducidos de piramide y limita
  cuantos escribe de forma sincrona.
- La seleccion automatica de workers de batch considera tamano de captura,
  algoritmo de demosaico y un suelo conservador para RAWs comprimidos.
- Los multiplicadores de temperatura/tinte de preview se derivan ahora de
  cromaticidad CCT y ratios de blanco en sRGB lineal, no de la heuristica
  anterior.
- El perfilado lanzado desde GUI usa por defecto un unico worker para evitar
  procesos pesados implicitos desde Qt en Windows.

### Fixed

- Los TIFF exportados aplican ahora la geometria visual de recorte y nivelado en
  la ruta de render.
- Los lotes GUI con varios archivos ya no aplican el recorte/nivelado de la
  imagen seleccionada a todos los archivos.
- El redondeo de recorte exportado coincide con la regla `floor/ceil` del visor.
- Eliminada la ruta experimental LittleCMS/Pillow de 8 bits para TIFF16; la
  conversion ICC de salida sigue en ArgyllCMS `cctiff` para preservar precision
  tonal.
- La cache SHA-256 de RAW puede desactivarse con `PROBRAW_RAW_SHA_CACHE=0` para
  rehash estricto en flujos de auditoria.

### Tests

- Suite completa: `426 passed, 2 warnings`.
- Anadida cobertura de regresion para geometria de exportacion, politica de
  geometria en batch, seleccion de piramide de preview, modo SHA estricto y
  politica de precision ICC TIFF16.

## [0.3.14] - 2026-05-06

### Added

- Nuevo menu `Editar` con deshacer, rehacer, eliminar ajustes y atajos
  `Ctrl+Z`/`Ctrl+Y` para los ajustes de revelado, render, detalle, recorte y
  nivelado visual.
- Nuevas herramientas en `Ajustes de imagen` para seleccionar recorte visual,
  nivelar con una referencia horizontal o vertical y limpiar recorte/nivelado.

### Changed

- La preview interactiva mantiene el equilibrio de rendimiento y precision:
  usa fuentes acotadas durante arrastres, conserva la ruta exacta al estabilizar
  la interaccion y actualiza muestras de histograma/niveles en tiempo real
  cuando toca por throttle.
- El editor de curva tonal mantiene visible su histograma durante el arrastre y
  los controles `Negro curva`/`Blanco curva` refrescan niveles sin bloquear la
  interfaz.
- El visor soporta recorte visual, rotacion fraccional de nivelado y
  reproyeccion del recorte cuando cambia la resolucion de preview o se solicita
  vista a pixeles reales.

### Fixed

- La ROI de analisis MTF vuelve a permanecer visible despues de aplicar un
  recorte visual.
- El zoom al 100% tras aplicar recorte conserva la correspondencia con pixeles
  reales y evita reconstrucciones completas innecesarias.
- El descargador de actualizaciones omite assets de metadatos y falla cerrado
  si no puede verificar SHA-256 del instalador.

### Tests

- Suite completa: `414 passed, 2 warnings`.
- Anadida cobertura de regresion para recorte, nivelado, undo/redo,
  histogramas interactivos, curva tonal durante arrastre y actualizaciones
  verificadas por SHA-256.

## [0.3.13] - 2026-05-05

### Fixed

- Corregida una incoherencia de niveles/histograma de curva en 0.3.12: el
  editor de curva muestra ahora los datos que entran en la curva, no la salida
  ya recortada por el rango negro/blanco de curva.
- El histograma RGB de clipping de imagen completa queda marcado como
  actualizando mientras se recalculan las metricas exactas de pixeles reales,
  evitando interpretar lecturas antiguas `L 0.00%`/`S 0.00%` como estado actual.

### Tests

- Anadida cobertura de regresion para histogramas de entrada de curva, clipping
  por blanco de curva y estado pendiente del histograma exacto.

## [0.3.12] - 2026-05-05

### Added

- El comprobador de actualizaciones abre ahora un asistente guiado que muestra
  version actual, ultima release, instalador detectado, tamano, pagina de
  release y disponibilidad de verificacion SHA-256 antes de iniciar la descarga.

### Changed

- La actualizacion desde la GUI descarga el instalador en una carpeta
  reconocible del usuario, verifica SHA-256 cuando la release lo publica y abre
  el instalador en modo visible en lugar de lanzarlo como proceso silencioso.
- La preview interactiva recupera el ritmo de la 0.3.8: los refrescos durante
  arrastre vuelven a agruparse cada 65 ms y las previews de perfil usan fuentes
  acotadas cuando la vista no esta a 1:1.
- El histograma exacto de imagen completa, el histograma de curva y la preview
  final siguen diferidos hasta que termina la interaccion, manteniendo precision
  de pixeles reales sin saturar el bucle de eventos.

## [0.3.11] - 2026-05-05

### Changed

- La preview interactiva recupera una ruta agil basada en caches acotadas para
  ajustes de color, contraste, curvas y nitidez, manteniendo la ruta exacta de
  pixeles reales cuando el usuario trabaja a 100% o solicita detalle.
- El refresco automatico de MTF durante arrastres de nitidez pasa de debounce a
  throttle: si la ROI full-res ya esta caliente, las graficas ESF/LSF/MTF se
  actualizan durante el movimiento sin esperar a soltar el control.
- La conversion OETF sRGB queda documentada y acotada a la curva tonal explicita
  `tone_curve: srgb`; no forma parte de la visualizacion gestionada por ICC.

### Fixed

- Las previews RAW cacheadas o reducidas ya no se tratan como pixeles reales en
  inspeccion 1:1, evitando analizar nitidez sobre una version proxy.
- Los cambios de zoom o encuadre vuelven a refrescar el viewport con los ajustes
  activos, de forma que toda la imagen visible mantiene color/contraste/nitidez
  coherentes mientras se navega.
- La documentacion de color consolida que ProbRAW usa perfiles ICC de entrada y
  visualiza mediante conversion directa al perfil de monitor del sistema, sin
  conversion intermedia obligatoria a sRGB.

## [0.3.10] - 2026-05-04

### Added

- La preview con gestion ICC mantiene una cache densa de LUT RGB de 8 bits por
  par `perfil de imagen -> perfil de monitor`, generada con LittleCMS y
  persistida en disco, para acelerar renders visibles repetidos sin cambiar el
  resultado colorimetrico.
- El benchmark GUI mide ahora interacciones reales a 100%, overlay de clipping,
  gestion ICC de monitor, tamano de ventana y receta efectiva colorimetrica.

### Changed

- La ruta de preview obliga a que toda imagen tenga perfil de entrada: ICC de
  sesion/imagen cuando existe, o perfil generico real ProPhoto/sRGB/Adobe RGB
  cuando no hay ICC especifico.
- Los ajustes interactivos actualizan solo el recorte visible a 100% cuando es
  posible, reutilizan QImage por regiones y evitan recalcular la imagen completa
  para sliders, curvas e indicadores de clipping.
- Las curvas tonales reutilizan LUTs normalizadas y comparten la cuantizacion RGB
  previa a las conversiones ICC necesarias para pantalla e instrumentos.
- La seleccion automatica de workers interactivos tiene en cuenta CPU, RAM y
  mediciones locales para aprovechar estaciones de trabajo sin bloquear la GUI.
- El zoom 1:1 queda sincronizado con pixeles reales, pero ya no fuerza volver a
  100% cuando el usuario amplia por encima de esa escala.

### Fixed

- La preview perfilada deja de pasar por rutas estandar sRGB cuando existe un
  perfil de entrada; la conversion visible es directa `ICC fuente -> ICC monitor`.
- Los botones de cache distinguen entre cachear la imagen seleccionada a 1:1 y
  cachear el directorio visible, evitando procesar siempre todas las imagenes.
- El histograma y el overlay de clipping se actualizan desde la senal
  colorimetrica correcta, sin mezclar la conversion de monitor ni buffers `uint8`
  sin normalizar.
- Los ajustes de color/contraste ya no disparan recalculos MTF innecesarios; la
  nitidez mantiene su ruta de analisis a resolucion real cuando se analiza.
- La carga y cambio de imagen invalidan correctamente el perfil fuente asociado
  a la preview cacheada para no reutilizar estado ICC obsoleto.

## [0.3.9] - 2026-05-03

### Added

- El análisis de aberración cromática lateral reutiliza ahora la ROI de borde
  inclinado seleccionada y muestra diferencias de perfiles RGB, área CA,
  desplazamientos entre canales y una tira de píxeles por vecino más próximo
  para inspección científica.

### Changed

- Los gráficos ESF y MTF son más legibles: ESF se centra en la ventana local del
  borde con tira tonal de píxeles, y MTF muestra una escala ciclos/píxel más
  clara junto a niveles de referencia MTF50/MTF30/MTF10.
- Las clases y helpers de análisis MTF/CA incorporan anotaciones y secciones
  focalizadas para facilitar futuros desarrollos en equipo.

## [0.3.8] - 2026-05-03

### Changed

- La previsualizacion RAW mantiene el render exacto compartido con la
  exportacion, pero anade una cache persistente de demosaico para acelerar
  recargas, refinados exactos y revelados posteriores sin cambiar la ruta de
  color ni la receta efectiva.
- La exportacion individual, el lote y la cola reutilizan esa cache de demosaico
  cuando procede, reduciendo trabajo repetido en RAW grandes y manteniendo la
  trazabilidad de la receta original.

### Fixed

- La previsualizacion vuelve a coincidir con el TIFF revelado en aplicaciones
  con gestion de color al evitar rutas de visualizacion alternativas que podian
  ocultar dominantes o ajustes cromaticos visibles en la exportacion.
- Los elementos de la cola de revelado se retiran automaticamente cuando se
  revelan correctamente, evitando reprocesarlos por accidente; los errores
  permanecen en cola con su mensaje para poder corregirlos o reintentarlos.

## [0.3.7] - 2026-05-03

### Added

- La pestaña Color y contraste incorpora un flujo ampliado de ajustes manuales:
  balance de blancos en primer lugar, controles de luz/contraste, saturacion,
  intensidad y gradacion de color separados de la calibracion ICC.
- El visor muestra la imagen ampliada sin interpolacion a escala real y dibuja
  una reticula de pixeles en magnificaciones de analisis para inspeccion
  cientifica de la informacion digital.
- Los graficos ESF/LSF/MTF muestran contexto de ROI, conteo de muestras,
  escala gradual en pixeles y metricas MTF50/MTF50P inspiradas en flujos de
  lectura slanted-edge.

### Changed

- La preview visible y el TIFF exportado comparten ahora la misma receta
  efectiva y la misma ruta ICC de imagen a monitor/salida, evitando que un
  ajuste cromatico aparezca solo al abrir el TIFF en otra aplicacion con
  gestion de color.
- El zoom conserva el centro visible actual al ampliar, para no perder la zona
  que se esta inspeccionando.
- Auto nitidez usa las nuevas metricas MTF50P, halo y energia post-Nyquist para
  penalizar picos de sobreenfoque y priorizar resultados mas estables.
- Los perfiles ICC generados con carta ya no arrastran ajustes de color,
  contraste o detalle visibles: calibracion ICC y ajustes manuales quedan
  separados.

### Fixed

- Los recalculos automaticos de MTF se detienen al salir de Nitidez y quedan
  diferidos hasta volver a esa pestaña, evitando que los ajustes cromaticos
  sigan pagando el coste del ROI/MTF en segundo plano.
- La seleccion de espacio ICC generico evita recargas duplicadas de preview y
  normaliza perfiles legados ProPhoto/sRGB hacia balance de camara y modo no
  profiling cuando no hay ICC de entrada.
- La barra superior de progreso recoge ajustes interactivos lentos y deja de
  depender de indicadores inferiores discretos para operaciones que superan un
  segundo.

## [0.3.6] - 2026-05-02

### Added

- Perfiles de ajuste separados y guardados en el proyecto para color/contraste,
  nitidez y ajustes de exportacion RAW, con flujos de guardar, aplicar, copiar y
  pegar por imagen.
- Las mochilas RAW registran ahora los identificadores concretos de perfil ICC,
  color/contraste, nitidez y exportacion RAW aplicados a cada archivo para
  reforzar la reproducibilidad.
- Las miniaturas RAW muestran una banda inferior discreta con indicadores de
  perfiles ICC, color/contraste, nitidez y exportacion RAW aplicados.
- El flujo Color/Calibracion empieza ahora con la eleccion entre perfiles
  genericos estandar, ICC de camara existentes y generacion de ICC con carta,
  seguida del estado ICC de la imagen seleccionada y la sesion.
- La opcion de ICC existente indica ahora cuando el proyecto no tiene perfiles
  ICC guardados y mantiene la carga de ICC de camara del sistema como salida.
- El panel RAW incorpora opciones de destramado dependientes del algoritmo
  (4 colores, calidad de borde y supresion de falso color) y registra esas
  capacidades en las recetas cuando el backend LibRaw/rawpy las soporte.
- La supresion de falso color RAW cuenta ahora con un postproceso propio de
  crominancia que preserva luminancia cuando el backend LibRaw/rawpy no expone
  `median_filter_passes`, permitiendo usarla con AMaZE.

### Changed

- La preview de la GUI aplica ahora la gestion de color de pantalla con una
  conversion directa `ICC de imagen -> ICC de monitor` cuando hay perfil de
  fuente, reservando sRGB solo como senal tecnica para histograma/diagnostico o
  fallback.
- Al activar un ICC de sesion se fuerza el revelado preview en RGB lineal de
  camara y se recarga la fuente RAW, evitando aplicar un ICC de camara sobre
  pixeles ya revelados en ProPhoto/sRGB.
- RAW / exportacion deja de presentar decisiones de perfil de salida, curva,
  exposicion, ruido o contraste: el panel queda limitado a lectura/demosaico
  RAW y puntos de negro, mientras la gestion ICC permanece en Color/Calibracion.
- Los perfiles de exportacion RAW guardan y aplican solo parametros RAW
  (motor, algoritmo, opciones de destramado y nivel negro), sin sobrescribir
  ajustes cromaticos ni decisiones ICC de la imagen.
- Los cambios RAW se escriben ahora automaticamente en la mochila de la imagen
  seleccionada y activan el indicador RAW aunque no se haya guardado un perfil
  RAW con nombre; el acordeon redundante de Perfiles RAW se oculta de la UI.
- El control RAW "Calidad de borde" se renombra a "Borde" y pasa a comportarse
  como el control de borde de RawTherapee: recorta pixeles perifericos tras el
  demosaico en lugar de mapearse a iteraciones DCB.
- El editor de curva tonal muestra ahora, al editar rojo, verde o azul, solo el
  histograma del canal activo con el color correspondiente y mantiene visibles
  las curvas RGB ajustadas junto a una referencia de luminancia global.
- La documentacion y el manual de usuario reflejan el flujo actual de ICC,
  perfiles independientes, iconos de miniatura, curvas RGB y RAW limitado a
  lectura/desentramado.

### Fixed

- La preparacion de ROI MTF en el paquete Windows lanza ahora el worker CLI
  interno en vez de reabrir el ejecutable grafico, de modo que seleccionar un
  area MTF termina sin abrir una segunda ventana de ProbRAW.
- Las curvas de contraste ya no fuerzan una preview final ICC a resolucion
  completa en el hilo principal: la fuente interactiva se cachea reducida y la
  preview pesada pasa a worker asincrono.
- La preview interactiva cuenta ahora con un watchdog: si un worker ICC queda
  atascado, se abandona esa tarea, se registra el aviso y la cola de ajustes
  vuelve a avanzar.
- El histograma del editor de curva tonal se actualiza ahora con la imagen tras
  los ajustes previos de color/exposicion/contraste, sin aplicar la curva, para
  que los niveles mostrados coincidan con el estado real de trabajo.
- Los ajustes de Color/contraste se guardan automaticamente en la mochila RAW
  seleccionada al mover controles, actualizan el indicador cromatico de la
  miniatura y la cola de revelado prioriza esa mochila frente al perfil de cola.
- El histograma integrado del editor de curva tonal se actualiza ahora en
  tiempo real con la curva aplicada y muestra columnas RGB ademas de la
  luminancia.
- El menu contextual de miniaturas permite copiar todos los ajustes aplicados
  o solo ICC, color/contraste, nitidez o RAW/exportacion, y pegarlos sobre una
  o varias imagenes seleccionadas sin sobrescribir el resto de categorias.
- Auto nitidez y los controles de detalle escriben ahora nitidez, radio, ruido
  y CA en la mochila RAW seleccionada en tiempo real, actualizando el indicador
  de Nitidez y evitando que el TIFF revele ajustes distintos a los vistos.

### Known Issues

- La ruta colorimetrica estricta sigue siendo mas costosa que una preview
  embebida. Queda pendiente cachear transformaciones ICC reducidas por
  perfil/receta para mejorar arrastres continuos sin relajar la correccion de
  color.

## [0.3.5] - 2026-05-02

### Added

- Visor global de progreso para operaciones largas de carga de preview RAW,
  preparacion de ROI MTF y tareas de fondo, con tiempo transcurrido, estimacion,
  tiempo restante y fase.
- Cache persistente de ROI MTF a resolucion completa preparada por un proceso
  externo, para que el analisis RAW frio no bloquee el hilo Qt de interfaz.
- Documentacion de rendimiento con tiempos NEF reales, decision de
  implementacion, alternativas evaluadas y referencias a Imatest, rawpy, LibRaw
  y darktable.

### Changed

- El recalculo MTF frio se inicia explicitamente cuando la cache ROI full-res
  esta fria; los refrescos automaticos usan datos calientes y ya no lanzan
  trabajo RAW pesado durante la interaccion con sliders.
- La pestaña `Nitidez` ya no duplica el panel local de progreso; el estado de
  analisis largo se informa desde la barra global siempre visible.
- La carga de preview RAW publica progreso global cuando se espera o se observa
  una duracion aproximada superior a un segundo.

### Fixed

- El revelado de cola usa ahora la mochila de cada RAW cuando no hay id de
  perfil de ajuste registrado, de modo que nitidez, ruido, aberracion cromatica,
  color y contraste llegan al TIFF renderizado en vez de heredarse de los
  sliders actuales.
- Al seleccionar una imagen sin configurar se restablecen receta, detalle,
  color, contraste y perfil ICC activo a la politica neutra
  ProPhoto/balance-de-camara, en lugar de arrastrar ajustes del archivo previo.
- Los espacios genericos sin carta desactivan `Profiling mode` y el balance fijo
  identidad para el render visible/final, manteniendo alineada la politica de
  color entre preview y TIFF.
- La salida RGB de camara sin ICC de entrada activo se rechaza antes de escribir
  TIFF, evitando archivos verdes/oscuros en visores externos.

## [0.3.4] - 2026-05-01

### Added

- La pestaña `Nitidez` incluye ahora análisis MTF de borde inclinado persistente,
  con curvas `ESF`, `LSF` y `MTF` guardadas en la mochila sidecar de cada RAW.
- Las mediciones MTF guardadas pueden compararse visualmente desde dos
  miniaturas seleccionadas, con curvas `ESF`, `LSF` y `MTF` superpuestas además
  de la tabla numérica.
- Los manuales documentan el flujo de análisis de nitidez, la persistencia de
  curvas y cómo ProbRAW convierte coordenadas de ROI del visor a coordenadas de
  análisis.

### Changed

- El recálculo MTF carga la fuente seleccionada a resolución completa y mapea la
  ROI del visor sobre esa imagen real de análisis, evitando mediciones sobre
  miniaturas o previews reducidas.
- El pitch de píxel y el informe en lp/mm usan las dimensiones de la imagen de
  análisis, metadatos EXIF o los controles manuales de tamaño de sensor en lugar
  de dimensiones de preview reducida.
- El catálogo Qt en inglés se regeneró y completó para los nuevos controles de
  sesión, color, carta, histograma y MTF.

### Fixed

- Al reabrir una imagen con datos MTF guardados se recuperan ROI y curvas sin
  seleccionar de nuevo el borde, incluso cuando el tamaño de preview actual es
  distinto al usado al guardar la medición.
- La actualización de datos MTF en la mochila RAW conserva los ajustes de
  revelado y el historial de salidas existentes.

## [0.3.3] - 2026-04-30

### Added

- La pestaña `1. Sesión` muestra ahora estadísticas de la sesión activa:
  imágenes RAW, TIFF derivados, perfiles ICC, perfiles de ajuste, mochilas RAW
  y elementos en cola.
- Acceso directo a sesiones recientes desde la pestaña de sesión.
- El diagnóstico `Carta` puede recargar datos de parches desde el
  `profile_report.json` guardado y los restaura automáticamente al abrir la
  sesión.
- La curva tonal avanzada permite edición por canal: luminosidad, rojo, verde y
  azul.
- Nuevo botón de enfoque del visor para ocultar/restaurar columnas laterales en
  un clic.

### Changed

- Reorganizada la tercera columna de `2. Ajustar / Aplicar` en tres pestañas de
  flujo: `Color / calibración`, `Ajustes personalizados` y `RAW / exportación`.
- La pestaña vertical `Visor` desaparece del panel izquierdo: los controles de
  comparación, zoom, giro, encaje, caché y aplicación ICC viven ahora en una
  barra superior horizontal del visor central con iconos compactos.
- El histograma queda fijo en la cabecera de `Ajustes personalizados`.
- El histograma y el overlay de clipping leen la señal colorimétrica de preview
  antes de la conversión al perfil ICC del monitor; la conversión de monitor se
  mantiene como última capa exclusiva de visualización.
- Actualizados manuales y capturas para reflejar el nuevo flujo de interfaz y la
  política de gestión de color.

### Fixed

- El visor `Gamut 3D` reinicia cámara y zoom cuando cambian los perfiles o la
  malla Lab, evitando que una vista anterior con elevación extrema haga parecer
  el gamut estirado hasta reiniciar la aplicación.
- Al reabrir una sesión con perfiles generados, la pestaña `Carta` ya no queda
  en `Sin datos de carta` cuando existe un reporte de perfil con errores por
  parche.

## [0.3.2] - 2026-04-29

### Fixed

- La entrada de escritorio Linux usa ahora el pixmap absoluto
  `/usr/share/pixmaps/probraw.png` para que Cinnamon y otros menus muestren el
  icono de ProbRAW aunque no refresquen correctamente el tema hicolor.
- Actualizadas las validaciones de instalacion y paquete para comprobar el icono
  real del menu.

## [0.3.1] - 2026-04-29

### Changed

- Sustituida la identidad grafica anterior por un nuevo logo e icono ProbRAW
  basados en una marca `P`, geometria RAW y parches de calibracion de color.
- Regenerados los assets SVG, PNG e ICO usados en README, aplicacion,
  instaladores Linux/Windows y paquete distribuible.

## [0.3.0] - 2026-04-29

### Changed

- Renombrado el proyecto y la identidad visible de la aplicacion a ProbRAW para
  evitar conflicto de marca con proyectos existentes.
- Renombrados paquete Python, lanzadores CLI, archivos desktop, iconos, capturas
  y artefactos de release al nombre canonico `probraw`.
- Actualizados metadatos de repositorio, instaladores y actualizaciones hacia
  `alejandro-probatia/ProbRAW`.
- Declarado el liderazgo del proyecto por Probatia Forensics SL
  (https://probatia.com) en colaboracion con la Asociacion Espanola de Imagen
  Cientifica y Forense (https://imagencientifica.es).

### Compatibility

- Los nuevos sidecars RAW se escriben como `RAW.probraw.json`, pero los
  `RAW.nexoraw.json` y `RAW.iccraw.json` existentes se siguen leyendo y se
  migran al guardar de nuevo la sesion.
- Los nuevos sidecars de prueba se escriben como `.probraw.proof.json`, pero
  `.nexoraw.proof.json` y `.iccraw.proof.json` siguen siendo legibles.
- La verificacion C2PA y Proof acepta etiquetas de asercion y variables de
  entorno de betas anteriores como fallback de migracion.
- Los paquetes Linux declaran `Replaces/Conflicts: nexoraw, iccraw` y no instalan
  lanzadores heredados.

## [0.2.6] - 2026-04-29

### Added

- Diagnóstico `Gamut 3D` en la pestaña de diagnóstico para comparar por pares el
  ICC de sesión, el perfil del monitor, perfiles estándar (`sRGB`, `Adobe RGB
  (1998)`, `ProPhoto RGB`) e ICC externos.
- Catálogo persistente de perfiles ICC por sesión con activación explícita,
  soporte para varias versiones generadas y recarga desde `session.json`.
- Gestión de referencias de carta desde la interfaz: catálogo de referencias
  incluidas, importación de JSON externos, referencias personalizadas de sesión y
  validación.
- Editor tabular de referencias Lab con muestras de color por parche para crear
  JSON de cartas personalizadas sin editar el archivo a mano.

### Changed

- La generación avanzada de perfiles registra artefactos versionados en
  `00_configuraciones/profile_runs/` y conserva los perfiles ICC generados en
  `00_configuraciones/profiles/`.
- La ejecución de perfilado se lanza en segundo plano desde la GUI para evitar
  que crear un perfil deje la aplicación bloqueada durante un buen rato.
- Los argumentos por defecto de ArgyllCMS incluyen `-u -R` para reducir gamuts
  ICC de cámara claramente irreales.
- Manual de usuario y capturas actualizados con el flujo de referencias, perfiles
  ICC de sesión y comparación Gamut 3D.

## [0.2.5] - 2026-04-29

### Changed

- Reorganizada la base de codigo alrededor del paquete canonico `probraw` y
  retirada la antigua implementacion interna bajo el namespace `iccraw`.
- Dividida la interfaz en modulos UI/window mas pequenos para facilitar el
  mantenimiento de sesiones, preview, perfiles y cola de revelado.
- Actualizados tests, scripts, instaladores y documentacion activa para usar de
  forma consistente el paquete y los lanzadores `probraw`.
- Las nuevas salidas C2PA usan etiquetas de asercion/accion
  `org.probatia.probraw.*`; la verificacion mantiene compatibilidad con
  manifiestos beta anteriores `org.probatia.iccraw.*`.

## [0.2.4] - 2026-04-28

### Added

- Selector de idioma de la interfaz en `Configuracion global -> General`, con
  opciones `Sistema (Auto: es/en)`, `Espanol` e `English`. Persiste en
  `QSettings` bajo `app/language`.
- Auto-deteccion del idioma del sistema operativo en instalaciones nuevas: si
  el SO esta en espanol arranca en espanol, en cualquier otro idioma arranca
  en ingles. No se migra a usuarios existentes con `app/language=es` ya
  guardado para respetar la eleccion previa.
- Helpers `probraw.i18n.detect_system_language` y `probraw.i18n.resolve_language`
  con tests unitarios en `tests/test_i18n.py`.

### Changed

- El cambio de idioma desde la configuracion no reinicia automaticamente la
  aplicacion: muestra un aviso y se aplica al proximo arranque, evitando
  perdida de estado de sesion no guardado.

## [0.2.3] - 2026-04-27

### Changed

- El flujo sin carta deja de generar perfiles `ProbRAW generic ...`: el RAW se
  revela en un espacio RGB estandar real (`sRGB`, `Adobe RGB (1998)` o
  `ProPhoto RGB`) con LibRaw y se incrusta un ICC estandar copiado del sistema o
  de ArgyllCMS.
- Los manifiestos de render registran `raw_color_pipeline`, indicando si la
  transformacion de color la resolvio LibRaw, el ICC de sesion o ArgyllCMS/CMM.
- ProbRAW Proof/C2PA declaran los ajustes completos aplicados (`recipe`,
  detalle/nitidez, contraste/render y gestion de color); el hash de ajustes
  queda como control de integridad, no como unico dato visible para auditoria.

### Added

- Tests de perfiles estandar reales para evitar que Adobe RGB caiga en un
  perfil compatible cuando existe `AdobeRGB1998.icc`.

## [0.2.2] - 2026-04-27

### Added

- `scripts/profile_pipeline.py` para perfilar comandos reales con `cProfile`
  y, si esta instalado, generar flamegraph con `py-spy`.
- `scripts/benchmark_raw_pipeline.py` para benchmark multiplataforma de
  demosaico, cache numerica y escalado por procesos con RAWs reales.
- `scripts/benchmark_gui_interaction.py` para medir fluidez de sliders y curva
  tonal en Qt con RAW real o fuente sintetica.
- Flags `--workers` en `batch-develop` y `auto-profile-batch` para fijar el
  paralelismo sin depender de variables de entorno.
- Flag `--cache-dir` en `develop`, `batch-develop` y `auto-profile-batch` para
  ubicar la cache numerica de demosaico cuando la receta active
  `use_cache: true`.
- Cache persistente de demosaico RAW en arrays `.npy`, opt-in por receta,
  con clave basada en SHA-256 completo del RAW y parametros LibRaw que afectan
  a la escena lineal.
- Tests golden de hashes canonicos en `tests/regression/` y script
  `scripts/regenerate_golden_hashes.py` para regenerarlos de forma explicita.

### Changed

- El analisis de preview e histogramas de GUI muestrea antes de convertir y
  recortar arrays grandes, reduciendo copias de memoria en imagenes 1:1.
- `batch-develop` usa multiprocessing real por proceso cuando `workers > 1`;
  conserva fallback a hilos solo si se inyecta un cliente C2PA no serializable.
- Los proyectos nuevos disponen de `00_configuraciones/cache/` como ubicacion
  persistente de cache por sesion.
- La estimacion automatica de RAM por worker de batch pasa a 2800 MiB para
  reflejar RAWs de alta resolucion y escritura TIFF real.
- `write_tiff16` reduce temporales de NumPy usando operaciones `out=`, bajando
  tiempo y pico de RAM durante la escritura TIFF16.
- El refresco final de preview tras arrastrar sliders/curva se encola en
  segundo plano para imagenes grandes cuando no hay preview ICC activo,
  evitando bloqueos perceptibles del hilo Qt.

### Fixed

- Las llamadas basicas a `exiftool` y `git rev-parse` usadas para metadatos y
  contexto de ejecucion tienen timeout para evitar bloqueos indefinidos.

## [0.2.1] - 2026-04-27

### Added

- GUI `Ayuda > Acerca de` ampliada con:
  - director del proyecto configurable (`PROBRAW_PROJECT_DIRECTOR`),
  - version en ejecucion,
  - estado operativo de AMaZE,
  - comprobacion de ultima version publicada en GitHub Releases,
  - actualizacion automatica que descarga y lanza el instalador de release.
- Nuevo modulo `probraw.update` para consulta de releases, comparacion de
  versiones, descarga de assets y ejecucion de instaladores por plataforma.
- Histograma RGB en la pestaña `Visor` con lectura de clipping en sombras y
  luces y testigos visuales.
- Overlay de clipping en la imagen de preview (azul sombras, rojo luces,
  magenta cuando coinciden), activable desde `Visor`.
- Tests unitarios para el sistema de actualizacion (`tests/test_update.py`).

### Changed

- El script Windows `packaging/windows/build_installer.ps1` exige AMaZE por
  defecto para builds de release (escape explicito: `-AllowNoAmaze` para builds
  de prueba).

## [0.2.0] - 2026-04-26

### Added

- Manual de usuario orientado a instaladores y flujos GUI, con capturas
  actualizadas para sesion, flujo con carta, flujo sin carta, mochilas,
  cola de revelado, metadatos y configuracion global.
- Flujo documentado para sesiones sin carta: perfil de revelado manual con ICC
  generico de salida (`sRGB`, `Adobe RGB (1998)` o `ProPhoto RGB`) y mochila
  `RAW.probraw.json` por imagen.
- Paquete Debian de release `0.2.0`, instalable como aplicacion ProbRAW con
  lanzadores `probraw`/`probraw-ui`, iconos hicolor y AMaZE validado en build.

### Changed

- El manual deja de explicar instalacion desde codigo y dependencias manuales;
  la instalacion de usuario se considera cubierta por instaladores
  multiplataforma.
- La GUI trata los perfiles como ajustes asignados a RAW: perfil avanzado desde
  carta marcado en azul y perfil basico/manual marcado en verde, ambos
  copiables y pegables desde miniaturas.
- La columna derecha de `2. Ajustar / Aplicar` abandona el modelo de
  "calibrar sesion" y agrupa los ajustes parametricos por archivo en
  `Brillo y contraste`, `Color`, `Nitidez`, `Gestión de color y calibración` y
  `RAW Global`.
- La tira de miniaturas funciona como scroll horizontal con tamaño ajustable y
  genera miniaturas visuales para RAW aunque no exista preview embebida,
  usando un revelado rápido cacheado.
- Se elimina la cabecera persistente con nombre/subtítulo de la aplicación para
  recuperar espacio vertical de trabajo.
- La elección de directorio de proyecto es más reactiva: el árbol vigila cambios
  del sistema, una raíz de proyecto abre `01_ORG/` para navegar RAW y
  `Usar carpeta actual` promueve `01_ORG/` a su raíz de proyecto.
- La estructura de proyectos nuevos se simplifica a `00_configuraciones/`,
  `01_ORG/` y `02_DRV/`; las sesiones heredadas con `config/session.json`
  siguen abriendose sin conversion destructiva.

### Fixed

- GUI: crear o abrir una sesion nueva ya no hereda rutas, miniaturas, cola ni
  perfiles de revelado de la sesion anterior; las rutas persistidas fuera de la
  raiz de proyecto se migran a la estructura propia de la sesion.
- GUI: las miniaturas y selecciones que aun apunten a rutas heredadas
  `raw/archivo` se resuelven automaticamente contra `01_ORG/archivo`, evitando
  tracebacks al abrir proyectos migrados.
- GUI: al generar un perfil desde carta, el perfil avanzado queda asignado a los
  RAW de carta mediante su mochila `RAW.probraw.json`.

## [0.1.0-beta.5] - 2026-04-25

### Changed

- El nombre visible del proyecto pasa a ser ProbRAW. Se añaden entry points
  `probraw`/`probraw-ui`, con alias heredados temporales para scripts beta
  existentes. Esos alias se retiran en 0.2.5.
- CMM unificado en ArgyllCMS: se sustituye LittleCMS (`tificc`) por
  `cctiff`/`xicclu` para conversion ICC de salida, validacion y preview de
  perfil. Desaparecen las dependencias `liblcms2-utils` y `Pillow.ImageCms` del
  flujo principal.
- `apply_profile_preview` reconstruye la previsualizacion ICC a partir de un
  LUT 17^3 calculado con `xicclu` e interpolacion trilineal cacheada por
  perfil; se elimina la dependencia del sidecar `.profile.json` para mostrar
  preview con perfil activo.
- `build_profile` reporta DeltaE 76/2000 a partir del ICC real generado por
  `colprof` (consultando `xicclu`). La matriz lateral
  `matrix_camera_to_xyz` se conserva solo como diagnostico
  (`diagnostic_matrix_*`).
- `auto_generate_profile_from_charts` aplica un guard cientifico estricto:
  rechaza recetas con `denoise`, `sharpen` o `tone_curve` activos, o con
  `output_linear=False` u `output_space` distinto de RGB de camara lineal.
- Las capturas de carta para perfilado se restringen a RAW/DNG/TIFF lineal;
  PNG/JPG ya no se aceptan ni en CLI ni en GUI.
- Refactor array-first del workflow de perfilado: `_collect_chart_samples` y
  `_collect_chart_geometries` usan `develop_image_array` y variantes
  `detect_chart_from_array` / `sample_chart_from_array` /
  `draw_detection_overlay_array`, evitando roundtrips a TIFF.
- El instalador Windows empaqueta `tools/argyll/ref/` (incluido `sRGB.icm`)
  para que la conversion ICC funcione sin perfiles externos. Se elimina la
  copia de binarios y metadata de LittleCMS.
- Paquete Debian: se elimina `liblcms2-utils` de las dependencias declaradas.
- `probraw check-tools` requiere `cctiff` (ArgyllCMS) en lugar de `tificc`.

### Fixed

- GUI: el histograma del editor de curvas tonales se recalcula solo cuando
  cambia la imagen base, evitando recomputos en cada movimiento de curva.
- GUI: el marcado manual de cuatro esquinas de carta sobrevive a recargas
  asincronas de la imagen seleccionada.
- GUI: la previsualizacion con perfil ICC ya no requiere `*.profile.json`
  asociado; un fallo de `xicclu` se registra como aviso y se cae a vista sin
  perfil sin bloquear el visor.

## [0.1.0-beta.4] - 2026-04-25

### Changed

- El instalador Windows AMaZE incluye metadata de distribucion
  `rawpy-demosaic` dentro del ejecutable PyInstaller para que
  `probraw check-amaze` informe el backend exacto.
- El empaquetado Windows copia avisos/licencias de `rawpy-demosaic`, LibRaw,
  los demosaic packs GPL2/GPL3 y RawSpeed, junto con hash de wheel y commit de
  fuente.

### Fixed

- Soporte operativo de AMaZE en Windows mediante wheel GPL3 de
  `rawpy-demosaic 0.10.1` enlazada a LibRaw 0.18.7 con
  `DEMOSAIC_PACK_GPL3=True`.

## [0.1.0-beta.3] - 2026-04-25

### Added

- Funcion `develop_image_array` para render RAW/TIFF array-first y benchmark
  basico de preview/render en `scripts/benchmark_pipeline.py`.
- Script `scripts/check_amaze_support.py` para auditar si el entorno LibRaw/rawpy
  incluye el demosaic pack GPL3 necesario para AMaZE.
- Preparado el flujo de empaquetado Windows con scripts PowerShell,
  PyInstaller, plantilla Inno Setup y documentacion de pruebas.

### Changed

- Preview de alta calidad, exportacion batch y rutas GUI de revelado evitan
  TIFF temporales cuando no son necesarios.
- La preview RAW en modo camera RGB/perfilado aplica una normalizacion visual
  solo para el visor, evitando dominantes verdes al marcar cartas sin alterar
  TIFFs auditados, muestreo ni exportacion.
- Las opciones de generacion ICC (`colprof`, calidad, formato y salida) y los
  criterios `RAW global` se muestran dentro de `Calibrar sesion`, antes de
  iniciar la calibracion.
- Politica AMaZE/GPL3 documentada: ProbRAW mantiene `AGPL-3.0-or-later`, registra
  flags de `rawpy` y solo habilita AMaZE cuando `DEMOSAIC_PACK_GPL3=True`.
- El instalador Windows empaqueta herramientas externas del flujo completo
  (`colprof`/`xicclu`, `exiftool` y `tificc`) bajo `tools/`.
- La GUI carga automáticamente la previsualización al seleccionar miniaturas y
  añade una barra superior de progreso para tareas largas.
- El visor permite zoom, reencuadre por arrastre y rotación de 90 grados.
- Nuevos paneles verticales de procesado: calibracion con criterios RAW,
  corrección básica, detalle, perfil activo y aplicación de sesión.
- Corrección básica de preview/lote: iluminante final, temperatura, matiz,
  brillo, niveles, contraste y curva de medios.
- Ajustes de detalle de preview/lote: reducción de ruido de luminancia/color,
  nitidez y corrección de aberración cromática lateral.

- El backend RAW pasa completamente de `dcraw` a LibRaw/rawpy, con DCB como
  demosaicing por defecto instalable y AMaZE disponible solo en builds de
  rawpy/LibRaw con demosaic pack GPL3.
- Se eliminan botones redundantes de carga manual en el visor; la selección de
  miniatura pasa a ser la acción principal.

### Fixed

- Compatibilidad con ArgyllCMS en Windows cuando `colprof` genera `.icm` en
  lugar de `.icc`.
- El backend RAW informa de forma explicita cuando una receta pide AMaZE sin
  demosaic pack GPL3; la GUI evita el bloqueo degradando a `dcb` con aviso.
- La generacion de perfil desde GUI reutiliza automaticamente las cuatro
  esquinas manuales pendientes, aunque aun no se haya guardado el JSON de
  deteccion manual.
- Las sesiones ya no restauran rutas temporales heredadas de ejecuciones de
  tests como rutas operativas de cartas, receta, perfiles o lote.
- La memoria persistente de la GUI recuerda ultima sesion/carpeta valida,
  ignora rutas obsoletas y usa la home del usuario como directorio inicial
  portable en Linux, macOS y Windows.

## [0.1.0-beta.2] - 2026-04-25

### Fixed

- La referencia ColorChecker 2005 D50 se empaqueta dentro de `probraw` y se usa
  como fallback cuando la GUI/CLI se ejecuta desde una instalacion `.deb` sin el
  arbol `testdata/` del repositorio.

## [0.1.0-beta.1] - 2026-04-24

### Changed

- La GUI migra rutas heredadas de `/tmp` a la estructura de la sesión:
  perfiles en `profiles/`, reportes/recetas en `config/`, trabajo en `work/`
  y TIFF/preview en `exports/`.
- `batch-develop` separa gestion ICC en modos explicitos:
  - RGB de camara con perfil ICC de entrada incrustado,
  - conversion a sRGB mediante LittleCMS (`tificc`) con perfil sRGB incrustado.
- La GUI reabre la ultima sesion usada y posiciona el explorador en el
  directorio operativo de la sesion en lugar de arrancar siempre en `$HOME`.
- `validate-profile` valida el perfil ICC real con ArgyllCMS (`xicclu`/`icclu`)
  en lugar de calcular DeltaE con la matriz lateral del sidecar.
- La deteccion de carta por fallback queda marcada como modo `fallback`, con
  confianza baja y bloqueo por defecto en flujos automaticos.
- El muestreo de carta aplica `sampling_trim_percent` y
  `sampling_reject_saturated` desde la receta.
- Las referencias de carta cargadas desde JSON se validan en modo estricto
  (fuente, D50, observador 2 grados, ids únicos y Lab completo).
- Nuevo comando `export-cgats` para exportar muestras a CGATS/CTI3 interoperable.
- La matriz `matrix_camera_to_xyz` queda como artefacto diagnostico/compatibilidad,
  no como sustituto de la conversion ICC en exportacion de lote ni de la
  validacion del perfil.
- Las recetas de ejemplo pasan de `demosaic_algorithm: rcd` a `ahd`, el modo
  soportado por `dcraw`.
- La GUI deja de ofrecer algoritmos de demosaicing que el backend `dcraw` no
  puede ejecutar.
- Reorganización estructural del proyecto para crecer como base Python única:
  - eliminada la capa Rust (`Cargo.toml`, `Cargo.lock`, `core/`, `cli/` Rust, `tests/` Rust) que ya no se usaba,
  - paquete renombrado `icc_entrada` → `iccraw` alineado con el nombre del repo y del proyecto,
  - código organizado en subpaquetes por dominio: `core/`, `raw/`, `chart/`, `profile/`,
  - `__version__` centralizado en `iccraw/version.py` y expuesto por `__init__.py`,
  - entry points CLI/GUI renombrados a `iccraw` y `iccraw-ui`,
  - `python -m iccraw` operativo vía `__main__.py`,
  - tests unificados en `tests/` (antes `tests_py/`) con imports actualizados,
  - docs duplicadas eliminadas de la raíz (canónicas en `docs/`), rutas absolutas Linux sustituidas por relativas en README.

### Added

- Paquete Debian beta `0.1.0~beta1` con instalacion en `/opt/iccraw`,
  lanzadores `/usr/bin/iccraw` y `/usr/bin/iccraw-ui`, y dependencias externas
  declaradas para `dcraw`, ArgyllCMS, LittleCMS y `exiftool`.
- Script reproducible `packaging/debian/build_deb.sh` para construir el `.deb`
  desde el arbol de trabajo.
- Validacion estricta de `demosaic_algorithm` para backend `dcraw`; una receta
  con algoritmo no soportado falla antes de procesar.
- Integracion de LittleCMS (`tificc`) como CMM externo para conversion ICC a
  sRGB.
- Metadatos de modo de gestion de color en manifiestos de lote.
- Tests P0 para demosaicing no soportado, `audit_linear_tiff` realmente lineal y
  exportacion ICC/CMM.
- Tests P0 que demuestran que `validate-profile` usa el ICC real aunque exista
  un sidecar con matriz incorrecta.
- Tests P1 para deteccion fallback de baja confianza y muestreo controlado por
  parametros de receta.
- Tests P1 para rechazo de referencias de carta incompletas/incompatibles.
- Tests P1 para exportacion CGATS/CTI3 de muestras.
- El reporte QA de sesion incluye peores parches y outliers DeltaE2000 por
  parche para diagnosticar desviaciones cromaticas localizadas.
- El QA de sesion incorpora diagnostico de captura por carta: luminancia de
  parches, bajo nivel, dispersion densitometrica de la fila neutra y gradiente
  estimado de iluminacion.
- Los perfiles de sesion declaran estado operacional `draft`, `validated`,
  `rejected` o `expired`, con vigencia opcional desde CLI.
- `auto-profile-batch` no aplica a lote perfiles de sesion `rejected` o
  `expired`.
- Nuevo comparador de reportes QA entre sesiones (`compare-qa-reports`) con
  resumen de estados, DeltaE, outliers, checks nuevos/resueltos y acceso desde
  la GUI.
- Nuevo diagnostico de herramientas externas (`check-tools`) con salida JSON y
  acceso desde GUI para comprobar `dcraw`, ArgyllCMS, LittleCMS y `exiftool`.
- Plantilla de mantenimiento continuo del changelog y política de actualización.
- Módulo `preview` para carga de imagen/RAW en previsualización, ajustes técnicos y análisis lineal.
- GUI nueva basada en Qt/PySide6 (`app-ui`, `app-ui-qt`) con:
  - previsualización técnica con perfil ICC,
  - ajustes de nitidez y reducción de ruido,
  - ejecución de flujo automático carta -> perfil -> lote.
- Dependencia opcional `gui` en `pyproject.toml`.
- Script `scripts/run_ui_qt.sh`.
- Navegador visual de directorios y miniaturas RAW/imagen integrado en GUI para selección de archivos clave.
- Acción GUI para revelar archivo seleccionado a TIFF 16-bit con perfil ICC opcional.
- Ajustes de ruido separados en luminancia y color.
- Menu superior en GUI con accesos a configuracion y operaciones (`Archivo`, `Configuracion`, `Perfil ICC`, `Vista`, `Ayuda`).
- Soporte de exploracion multiunidad en GUI para navegar el arbol completo del sistema de archivos.
- Panel de configuracion RAW ampliado (demosaic, WB, black/white level, tone curve, espacios, sampling, profiling mode).
- Panel de configuracion de perfil ICC ampliado (tipo `-a`, calidad `-q`, args extra `colprof`, formato `.icc/.icm`).
- Optimizacion de carga y previsualizacion RAW/DNG:
  - modo rapido con miniatura embebida o decodificacion `dcraw -h`,
  - downscale configurable de preview para reducir latencia en archivos grandes,
  - cache de previews por archivo+recipe para recargas inmediatas.
- Nueva función de backend `auto_generate_profile_from_charts` para generar perfil ICC sin ejecutar batch.
- Reorganización funcional en 3 pestañas principales:
  - Generación Perfil ICC,
  - Revelado RAW,
  - Monitoreo Flujo.
- Revelado por lotes integrado en pestaña de Revelado RAW (selección o directorio completo).
- Nuevo módulo `session` para gestión persistente de sesiones con creación de estructura de directorios:
  - `charts/`, `raw/`, `profiles/`, `exports/`, `config/`, `work/`.
- Nueva pestaña `1. Sesión` para crear/abrir/guardar sesión con metadatos de iluminación y toma.
- Nueva pestaña `3. Cola de Revelado` con cola de archivos, estado por imagen y ejecución de lote desde cola.
- Persistencia de estado por sesión en `config/session.json`:
  - rutas operativas,
  - configuración de revelado/perfil,
  - perfil activo,
  - cola de revelado.
- Test unitario `tests_py/test_session.py` para estructura, carga y normalización de sesión.

### Changed

- Se reemplaza completamente la GUI anterior (tkinter) por implementación Qt.
- `apply_profile_matrix` pasa a API pública en `icc_entrada.export` para reutilización en previsualización.
- Documentación y roadmap actualizados para reflejar GUI Qt y política legal AGPL + dependencias.
- Rediseño de GUI a layout de 3 paneles (explorador, visor principal, panel de control) priorizando espacio de imagen y flujo práctico de producción.
- Reorganizacion de GUI para flujo de trabajo tipo revelador RAW (navegacion, seleccion visual y maximo espacio para imagen).
- Renombrada pestaña de ajustes visuales de `Vista` a `Nitidez`.
- El flujo de perfilado y el flujo de revelado por lotes se separan explícitamente para mayor claridad operativa.
- La previsualización aplica perfil ICC desactivado por defecto para evitar dominantes cuando el perfil no corresponde al set cámara+iluminación+recipe activo.
- La ventana Qt guarda/restaura tamaño y distribución de paneles para mejorar trabajo en pantallas de distinto tamaño.
- Reorganización de pestañas principales para flujo centrado en sesión:
  - `Sesión`,
  - `Revelado y Perfil ICC`,
  - `Cola de Revelado`.
- La GUI de trabajo se reorganiza en dos fases operativas:
  - `1. Calibrar sesión`: capturas de carta -> perfil de revelado + ICC,
  - `2. Aplicar sesión`: RAW/TIFF objetivo -> TIFF con receta calibrada + ICC.
- El ajuste manual visible queda limitado a nitidez; exposición, densidad,
  balance de blancos y base colorimétrica proceden de la carta.
- El procesamiento por lote en GUI ahora tolera errores por archivo y devuelve resumen `OK/errores` sin abortar todo el lote.
- `auto_generate_profile_from_charts` acepta una lista explícita de capturas de
  carta para que la GUI pueda usar una selección de miniaturas en vez de todo
  un directorio.
- La pestaña de calibración de sesión oculta rutas internas de artefactos y
  botones redundantes; el perfil generado se activa automáticamente junto con
  su receta calibrada.
- `Generar perfil de sesión` infiere las cartas desde la selección de miniaturas
  o desde el archivo cargado antes de recurrir a la carpeta, evitando búsquedas
  accidentales en directorios genéricos como `$HOME`.
- Las detecciones manuales guardadas desde la GUI quedan asociadas al RAW de
  carta y se reutilizan durante la generación del perfil de sesión.
- `batch-develop` separa los TIFF lineales de auditoría en `_linear_audit/`
  para que no se confundan con los TIFF finales de inspección o entrega.
- El flujo automático puede reservar capturas de carta para validación hold-out,
  generar `qa_session_report.json` y clasificar la sesión como `validated`,
  `rejected` o `not_validated`.

### Docs

- README ampliado con objetivo del proyecto, alcance, límites y metodología
  aplicada al flujo RAW -> carta -> perfil de revelado -> ICC -> lote.
- Nuevo documento `docs/OPERATIVE_REVIEW_PLAN.md` con hallazgos tecnicos,
  criterios de aceptacion y plan profesional por fases para convertir el
  prototipo en pipeline operativo y auditable.
- `ROADMAP.md`, `ISSUES.md`, `COLOR_PIPELINE.md` y `README.md` enlazados al
  plan operativo y actualizados con prioridades P0-P3.
- Política legal ampliada para:
  - compatibilidad AGPL con objetivo comunitario no comercial,
  - notas de licencia de ArgyllCMS, dcraw y PySide6,
  - obligaciones de redistribución y trazabilidad.
- Nuevo documento `docs/THIRD_PARTY_LICENSES.md` con inventario operativo de licencias de terceros.
- Advertencia explícita en README y manual: el estado actual es de desarrollo y la aplicación aún no se considera plenamente funcional/validada para producción científica o forense.

### Fixed

- `audit_linear_tiff` se escribe antes de compensacion de exposicion y curvas de
  salida, conservando el estado lineal desarrollado.
- Corrección de previsualización RAW rápida:
  - salida de `dcraw` para preview en espacio sRGB (`-o 1`) en lugar de cámara nativa sin conversión,
  - normalización de miniatura embebida a lineal para evitar doble corrección gamma.
- Salvaguarda en preview con perfil ICC:
  - si falta sidecar `.profile.json` o se detecta clipping/dominante extrema, la vista cae a modo sin perfil con aviso en log.
- La receta calibrada generada se carga inmediatamente en la GUI; los revelados
  posteriores ya no pueden quedarse usando los controles base por accidente.
- La previsualización rápida basada en la matriz lateral adapta correctamente
  de D50 a sRGB/D65 para evitar dominantes amarillas o verdosas espurias.

## [0.1.0] - 2026-04-23

### Added

- Estructura inicial del proyecto modular (`core`, `src`, `cli`, `docs`, `tests`).
- CLI funcional para flujo técnico: `raw-info`, `develop`, `detect-chart`, `sample-chart`, `build-profile`, `validate-profile`, `batch-develop`.
- GUI ligera en `tkinter` para operar el flujo completo sin línea de comandos.
- Flujo automático extremo a extremo (`auto-profile-batch`) para carta -> perfil ICC -> lote TIFF 16-bit.
- Script de verificación de herramientas externas: `scripts/check_tools.sh`.
- Manual de usuario en español.
- Documento técnico de integración `dcraw + ArgyllCMS`.
- Documento de cumplimiento legal y política de licencias.

### Changed

- Interfaz gráfica traducida completamente al español.
- Motor de revelado RAW fijado a `dcraw` como backend único soportado.
- Motor de perfil ICC fijado a ArgyllCMS (`colprof`) como backend único soportado.
- Metadatos de licencia del proyecto actualizados a `AGPL-3.0-or-later`.
- Gobernanza declarada para mantenimiento comunitario por la Asociación Española de Imagen Científica y Forense.

### Fixed

- Formato `.ti3` para `colprof` ajustado (`DEVICE_CLASS`/`COLOR_REP` y orden de campos) para compatibilidad real con ArgyllCMS.
- Detección y registro de versión `dcraw` en contexto de ejecución mejorada.

### Docs

- Arquitectura, roadmap, decisiones y manual alineados con:
  - pipeline estricto `dcraw + ArgyllCMS`,
  - requisitos de reproducibilidad,
  - cumplimiento legal AGPL para distribución y uso en red.
