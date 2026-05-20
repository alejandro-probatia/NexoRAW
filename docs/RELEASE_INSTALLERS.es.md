# Publicacion de instaladores

La publicacion de instaladores de ProbRAW tiene una regla simple: ningun
artefacto se sube al repositorio ni a GitHub Releases sin pasar primero las
validaciones de paquete e instalacion.

## Linux `.deb`

Construir siempre con AMaZE exigido:

```bash
PROBRAW_BUILD_AMAZE=1 PROBRAW_REQUIRE_AMAZE=1 bash packaging/debian/build_deb.sh
```

Validar el paquete antes de instalar o subir:

```bash
packaging/debian/validate_deb.sh dist/probraw_<version>_amd64.deb
sha256sum dist/probraw_<version>_amd64.deb > dist/probraw_<version>_amd64.deb.sha256
```

Validar en una instalacion real:

```bash
sudo apt purge nexoraw iccraw probraw
sudo apt install ./dist/probraw_<version>_amd64.deb
scripts/validate_linux_install.sh
probraw --version
probraw check-tools --strict
probraw check-amaze
```

La validacion comprueba nombre `ProbRAW`, lanzadores `probraw`/`probraw-ui`,
ausencia de ejecutables heredados `nexoraw`/`iccraw`, icono hicolor completo, fallback
`/usr/share/pixmaps/probraw.png`, categoria de menu `Graphics;Photography`,
C2PA, herramientas externas y AMaZE.

Smoke GUI minimo antes de publicar:

- abrir ProbRAW desde el menu del sistema;
- confirmar que aparece en `Graficos/Fotografia` con icono ProbRAW;
- crear una sesion nueva y verificar carpetas `00_configuraciones/`, `01_ORG/`
  y `02_DRV/`;
- abrir la raiz del proyecto y confirmar que el navegador entra en `01_ORG/`;
- cambiar a otro proyecto y confirmar que no quedan miniaturas de la sesion
  anterior;
- seleccionar un RAW y comprobar que la miniatura muestra imagen, no solo icono
  generico;
- generar o guardar un perfil basico y confirmar mochila `RAW.probraw.json`;
- probar copiar/pegar perfil de ajuste entre dos miniaturas;
- revisar `Configuracion > Configuracion global` y confirmar deteccion o
  fallback del perfil ICC del monitor.

## Linux Arch/CachyOS

El paquete Arch/CachyOS se construye desde `packaging/arch/build_pkg.sh` y usa
el `PKGBUILD` versionado del repositorio:

```bash
PROBRAW_ARCH_PKGREL=3 \
PROBRAW_ARCH_NATIVE=1 \
PROBRAW_BUILD_AMAZE=1 \
packaging/arch/build_pkg.sh
```

Para una build local optimizada de CachyOS, `PROBRAW_ARCH_NATIVE=1` activa
`-O3 -march=native -mtune=native` en extensiones C/C++. No debe usarse para un
paquete que se vaya a distribuir a maquinas con CPU distinta. El paquete instala
la aplicacion en `/opt/probraw/venv`, expone solo `probraw` y `probraw-ui`,
declara conflicto/reemplazo de `iccraw`/`nexoraw` e incluye documentacion de
validacion en `/usr/share/doc/probraw/`.

Instalacion limpia local sin borrar datos de usuario:

```bash
sudo pacman -R --noconfirm probraw || true
sudo rm -rf /opt/probraw
sudo rm -f /usr/bin/probraw /usr/bin/probraw-ui /usr/bin/iccraw /usr/bin/iccraw-ui
sudo pacman -U --noconfirm build/arch/probraw-<version>-<pkgrel>-x86_64.pkg.tar.zst
```

Validacion obligatoria en la instalacion real:

```bash
pacman -Qkk probraw
bash /usr/share/doc/probraw/validate_cachyos_install.sh
probraw check-tools --strict
probraw check-amaze
probraw check-color-environment --out color_environment.json
```

`check-color-environment` puede devolver `warning` si el sistema no expone un
perfil ICC activo de monitor; eso documenta fallback visual sRGB, no un fallo de
instalacion. La build solo es publicable si perfiles estandar, LittleCMS2,
ArgyllCMS y AMaZE quedan verificados.

## Windows

El instalador Windows debe generarse desde `packaging/windows/build_installer.ps1`
con `-RequireAmaze` y una wheel trazada cuando PyPI no ofrezca una compatible:

```powershell
.\packaging\windows\build_installer.ps1 -RawpyDemosaicWheel $wheel -RequireAmaze
```

El build no debe generar `nexoraw.exe`, `nexoraw-ui.exe`, `iccraw.exe` ni
`iccraw-ui.exe`. Los accesos directos deben apuntar a `probraw-ui.exe` y usar el
icono `probraw-icon.ico`.

## macOS

El artefacto macOS se genera desde un host macOS con PyInstaller:

```bash
PROBRAW_REQUIRE_AMAZE=1 \
PROBRAW_MACOS_STRICT_TOOLS=1 \
bash packaging/macos/build_app.sh
```

Salidas esperadas:

- `dist/macos/ProbRAW.app`
- `dist/macos/probraw/probraw`
- `dist/macos/ProbRAW-<version>-macos-<arch>.zip`
- `dist/macos/ProbRAW-<version>-macos-<arch>.zip.sha256`

La build debe validarse al menos con:

```bash
dist/macos/probraw/probraw --version
dist/macos/probraw/probraw check-tools --strict
dist/macos/probraw/probraw check-amaze
open dist/macos/ProbRAW.app
```

La firma Developer ID y la notarizacion no se ejecutan por defecto. Para firmar
localmente el `.app` generado, usar `PROBRAW_MACOS_CODESIGN_IDENTITY`. Un asset
publico debe documentar si esta firmado/notarizado o si es un zip local para
pruebas.

## Releases

1. Ejecutar tests del proyecto.
2. Ejecutar benchmarks de rendimiento/GUI cuando se hayan tocado preview,
   pipeline RAW, cache o paralelismo.
3. Actualizar `src/probraw/version.py`, `CHANGELOG.md`, README y documentacion
   de instaladores.
4. Construir instaladores desde scripts versionados, no manualmente.
5. Ejecutar las validaciones de cada plataforma.
6. Generar `.sha256` despues de validar.
7. Subir solo los artefactos validados.
8. Si un asset publicado resulta defectuoso y GitHub no permite reemplazarlo,
   crear una revision nueva de la release y marcar la anterior con un aviso.

## Release 0.3.22

La release 0.3.22 corrige el flujo de seleccion de perfiles ICC generados en la
sesion:

- los perfiles `rejected` siguen sin autoactivarse,
- la seleccion manual desde combo, menu o "Usar ICC generado" queda permitida,
- la mochila RAW conserva ruta e identificador del ICC y solo restaura perfiles
  `rejected` cuando ambos coinciden,
- cambiar a una imagen sin mochila o con ID incoherente limpia el ICC activo.

Artefactos esperados para la release Windows:

- `ProbRAW-0.3.22-Setup.exe`
- `ProbRAW-0.3.22-Setup.exe.sha256`
- `probraw-0.3.22.tar.gz`
- `probraw-0.3.22-py3-none-any.whl`
- `probraw_0.3.22_python_artifacts.sha256`

## Release 0.3.21

La release 0.3.21 sustituye a la 0.3.20 por el fallo de generacion ICC con
carta marcada manualmente y capturas adicionales descartadas por deteccion
fallback:

- las detecciones manuales se mantienen como entrenamiento antes de reservar
  capturas para validacion,
- la ausencia de validacion independiente deja el ICC como `draft` utilizable,
  no como error bloqueante,
- el histograma de curva se calcula en segundo plano durante el arrastre y
  refleja los ajustes tonales aplicados,
- la preview con ICC de entrada generado evita compensaciones visuales de camara
  que producian dominantes azules.

Artefactos esperados para la release Windows:

- `ProbRAW-0.3.21-Setup.exe`
- `ProbRAW-0.3.21-Setup.exe.sha256`
- `probraw-0.3.21.tar.gz`
- `probraw-0.3.21-py3-none-any.whl`
- `probraw_0.3.21_python_artifacts.sha256`

## Release 0.3.20

La release 0.3.20 consolida las correcciones de rutas de sesion y preview de
monitor:

- las sesiones nuevas alinean el navegador de archivos, la carpeta de
  referencias de carta y la carpeta de exportacion TIFF derivada con el proyecto
  activo,
- el marcado manual de carta puede construir un perfil ICC aunque la deteccion
  automatica no produjera candidatos utilizables,
- la conversion ICC de monitor sigue siendo exclusiva de visualizacion: los TIFF
  exportados conservan el ICC de entrada seleccionado,
- los pixeles de preview ya convertidos al ICC de monitor con LittleCMS se
  entregan a Qt como RGB de dispositivo, evitando una segunda conversion
  `QColorSpace`.

Artefactos esperados para la release Windows:

- `ProbRAW-0.3.20-Setup.exe`
- `ProbRAW-0.3.20-Setup.exe.sha256`
- `probraw-0.3.20.tar.gz`
- `probraw-0.3.20-py3-none-any.whl`
- `probraw_0.3.20_python_artifacts.sha256`

## Release 0.3.19

La release 0.3.19 consolida el trabajo posterior a 0.3.18 en empaquetado y
preview:

- el empaquetado macOS queda disponible desde scripts versionados y documentado
  para validacion, firma opcional y checks AMaZE,
- el empaquetado Arch/CachyOS y la busqueda de perfiles ICC del sistema siguen
  documentados para builds nativas,
- la primera carga de preview RAW puede mostrar una preview embebida
  provisional orientada mientras se prepara el render completo,
- las escrituras de geometria del visor en sidecar se vacian durante cambios
  rapidos de archivo.

Artefactos esperados para la release Windows:

- `ProbRAW-0.3.19-Setup.exe`
- `ProbRAW-0.3.19-Setup.exe.sha256`
- `probraw-0.3.19.tar.gz`
- `probraw-0.3.19-py3-none-any.whl`
- `probraw_0.3.19_python_artifacts.sha256`

## Release 0.3.18

La release 0.3.18 corrige deshacer tras cambios de geometria de visor:

- deshacer/rehacer solo recorte o solo nivelado ya no fuerza una reconstruccion
  final de preview,
- volver atras tras reencuadrar una preview RAW grande evita el cuelgue aparente
  causado por recomputacion innecesaria de preview.
- la revision `0.3.18-3` para Arch/CachyOS incorpora busqueda de perfiles ICC
  del sistema, preview ICC con LittleCMS2, validacion `check-color-environment`
  y paquete nativo optimizado con AMaZE.

Artefactos esperados:

- `ProbRAW-0.3.18-Setup.exe`
- `ProbRAW-0.3.18-Setup.exe.sha256`
- `probraw-0.3.18-<pkgrel>-x86_64.pkg.tar.zst`
- `probraw-0.3.18.tar.gz`
- `probraw-0.3.18-py3-none-any.whl`
- `probraw_0.3.18_python_artifacts.sha256`

## Release 0.3.17

La release 0.3.17 mejora el rendimiento de preview interactiva y sesiones RAW
con cache:

- las coordenadas de remapeo de aberracion cromatica lateral se reutilizan en
  ediciones repetidas de preview,
- los ajustes de vibrance/saturacion de preview asignan menos arrays temporales,
- la poda de cache de demosaic queda limitada por tiempo durante escrituras de
  batch/cache,
- la supresion local de falso color reduce asignaciones temporales y preserva
  los hashes canonicos de regresion.

Artefactos esperados:

- `ProbRAW-0.3.17-Setup.exe`
- `ProbRAW-0.3.17-Setup.exe.sha256`
- `probraw-0.3.17.tar.gz`
- `probraw-0.3.17-py3-none-any.whl`
- `probraw_0.3.17_python_artifacts.sha256`

## Release 0.3.16

La release 0.3.16 mejora el control de exportacion TIFF y la revision en GUI:

- los TIFF finales pueden exportarse sin compresion o con ZIP/Deflate, LZW,
  JPEG o ZSTD,
- `imagecodecs` queda incluido en runtime y empaquetado Windows para codecs
  TIFF,
- la exportacion TIFF comprimida puede acotar workers por TIFF y el lote reparte
  CPU entre trabajos activos,
- el nivelado horizontal/vertical usa una linea arrastrable y las rotaciones
  exportadas se recortan para evitar bordes negros,
- el arbol de carpetas puede abrir directorios en el explorador del sistema,
- la cola de revelado muestra barras de progreso por archivo.

Artefactos esperados:

- `ProbRAW-0.3.16-Setup.exe`
- `ProbRAW-0.3.16-Setup.exe.sha256`
- `probraw-0.3.16.tar.gz`
- `probraw-0.3.16-py3-none-any.whl`
- `probraw_0.3.16_python_artifacts.sha256`

## Release 0.3.15

La release 0.3.15 corrige fidelidad de exportacion y reduce trabajo pesado en
flujos de preview, perfilado y batch:

- los TIFF renderizados aplican recorte y nivelado visual en la ruta de salida,
- los lotes con varios archivos ya no propagan la geometria de la imagen activa
  a todos los elementos,
- la conversion ICC TIFF16 vuelve a depender solo de ArgyllCMS `cctiff`,
- el redondeo de recorte exportado coincide con el visor,
- el muestreo de cartas, MTF y cache de previews reducen memoria/IO,
- el perfilado GUI evita workers de proceso implicitos en Windows.

Artefactos esperados:

- `ProbRAW-0.3.15-Setup.exe`
- `ProbRAW-0.3.15-Setup.exe.sha256`
- `probraw-0.3.15.tar.gz`
- `probraw-0.3.15-py3-none-any.whl`
- `probraw_0.3.15_python_artifacts.sha256`

## Release 0.3.14

La release 0.3.14 estabiliza el equilibrio entre rendimiento interactivo y
precision de lectura en GUI:

- los histogramas y niveles se actualizan durante arrastres con throttle, sin
  bloquear la interfaz ni perder el refresco exacto al soltar,
- la curva tonal mantiene visible su histograma mientras se editan puntos o el
  rango negro/blanco,
- el visor incorpora recorte visual, nivelado horizontal/vertical, rotacion
  fraccional y reproyeccion de recorte en vista a pixeles reales,
- el menu `Editar` anade deshacer, rehacer, eliminar ajustes y atajos
  `Ctrl+Z`/`Ctrl+Y`,
- el descargador de actualizaciones omite metadatos y exige SHA-256 verificable
  para instaladores.

Artefactos esperados:

- `ProbRAW-0.3.14-Setup.exe`
- `ProbRAW-0.3.14-Setup.exe.sha256`
- `probraw-0.3.14.tar.gz`
- `probraw-0.3.14-py3-none-any.whl`
- `probraw_0.3.14_python_artifacts.sha256`

## Release 0.3.13

La release 0.3.13 corrige la incoherencia de niveles/histograma de curva
detectada en 0.3.12:

- el histograma del editor de curva representa ahora los datos que entran en la
  curva, no la salida ya recortada por el rango de curva,
- el histograma RGB de imagen completa queda marcado como actualizando mientras
  se recalculan las metricas exactas de clipping tras cambios de niveles/curva,
- las pruebas de regresion cubren clipping por blanco de curva y estado antiguo
  del histograma exacto.

Artefactos esperados:

- `ProbRAW-0.3.13-Setup.exe`
- `ProbRAW-0.3.13-Setup.exe.sha256`
- `probraw-0.3.13.tar.gz`
- `probraw-0.3.13-py3-none-any.whl`
- `probraw_0.3.13_python_artifacts.sha256`

## Release 0.3.12

La release 0.3.12 recupera el ritmo de preview mas suave de la 0.3.8 sin perder
las correcciones posteriores de precision:

- los refrescos de preview durante sliders y curvas aplican throttle en lugar
  de programarse en cada evento,
- las previews de perfiles ICC usan fuentes acotadas por debajo de 1:1 y fuente
  completa en inspeccion de pixel real,
- los histogramas de imagen completa siguen siendo exactos y se refrescan al
  estabilizar la interaccion,
- los arrastres de puntos de curva y los sliders de negro/blanco de curva
  evitan trabajo caro de histograma durante el movimiento y consolidan al
  soltar,
- el asistente de actualizacion descarga el instalador en una carpeta
  reconocible y lo lanza de forma visible.

Artefactos esperados:

- `ProbRAW-0.3.12-Setup.exe`
- `ProbRAW-0.3.12-Setup.exe.sha256`
- `probraw-0.3.12.tar.gz`
- `probraw-0.3.12-py3-none-any.whl`
- `probraw_0.3.12_python_artifacts.sha256`

## Release 0.3.11

La release 0.3.11 corrige la fluidez interactiva de preview y nitidez sin
rebajar la gestion ICC ni confundir proxies con pixeles reales:

- los ajustes de color, contraste, curvas y nitidez vuelven a usar fuentes
  proxy acotadas durante el arrastre cuando no se esta inspeccionando a 1:1,
- el visor recupera fuente completa cuando el usuario solicita pixeles reales,
  y las previews RAW cacheadas/reducidas no se etiquetan como 100% real,
- los cambios de zoom y encuadre reprograman la preview del viewport visible
  para mostrar toda la region con los ajustes activos,
- las graficas ESF/LSF/MTF se refrescan en tiempo real durante el arrastre de
  nitidez si la ROI full-res ya esta caliente,
- la documentacion fija que la visualizacion es `ICC entrada -> ICC monitor` y
  que la OETF sRGB solo pertenece a la curva tonal explicita.

Artefactos esperados:

- `ProbRAW-0.3.11-Setup.exe`
- `ProbRAW-0.3.11-Setup.exe.sha256`
- `probraw-0.3.11.tar.gz`
- `probraw-0.3.11-py3-none-any.whl`
- `probraw_0.3.11_python_artifacts.sha256`

## Release 0.3.10

La release 0.3.10 corrige la invariante de perfilado de preview y mejora el
rendimiento interactivo a 100% sin degradar color ni nitidez:

- toda imagen gestionada tiene perfil de entrada obligatorio: ICC de
  sesion/imagen o perfil generico real,
- la visualizacion perfilada usa conversion directa `ICC fuente -> ICC monitor`,
  sin rutas estandar sRGB para pantalla cuando hay perfil fuente,
- cache densa de LUT ICC de 8 bits generada por LittleCMS, persistida en disco y
  reutilizada para previews grandes,
- actualizacion por region visible, zoom 1:1 estable y ampliacion por encima del
  100% sin retorno automatico,
- sliders de color/contraste casi instantaneos y curvas mas rapidas por cache de
  LUT tonal y cuantizacion RGB compartida,
- botones de cache separados para imagen seleccionada 1:1 y directorio visible,
- benchmark GUI real documentado con RAW completo, ICC de monitor y overlay.

Artefactos esperados:

- `ProbRAW-0.3.10-Setup.exe`
- `ProbRAW-0.3.10-Setup.exe.sha256`
- `probraw-0.3.10.tar.gz`
- `probraw-0.3.10-py3-none-any.whl`
- `probraw_0.3.10_python_artifacts.sha256`

## Release 0.3.9

La release 0.3.9 mejora la lectura del analisis de nitidez y anade inspeccion
de aberracion cromatica lateral:

- grafico CA lateral desde la misma ROI de borde inclinado, con diferencias
  RGB, area CA, desplazamientos entre canales y tira de pixeles del borde por
  vecino mas proximo,
- ventana local ESF con tira tonal de pixeles,
- escala ciclos/pixel MTF mas clara y referencias estandar MTF50/MTF30/MTF10,
- clases y helpers MTF/CA anotados para futuros desarrollos en equipo.

Artefactos esperados:

- `ProbRAW-0.3.9-Setup.exe`
- `ProbRAW-0.3.9-Setup.exe.sha256`
- `probraw-0.3.9.tar.gz`
- `probraw-0.3.9-py3-none-any.whl`
- `probraw_0.3.9_python_artifacts.sha256`

## Release 0.3.8

La release 0.3.8 corrige una divergencia grave entre preview y TIFF revelado y
mantiene el render exacto con mejor rendimiento:

- la preview RAW y la exportacion usan la misma ruta efectiva de render y color,
- el demosaico RAW exacto se cachea para recargas, refinado exacto, exportacion,
  lotes y cola,
- la lectura de cache reduce copias completas de memoria en imagenes grandes,
- la cola de revelado retira los elementos completados para evitar revelarlos
  de nuevo y conserva los fallidos con su mensaje.

Artefactos esperados:

- `ProbRAW-0.3.8-Setup.exe`
- `ProbRAW-0.3.8-Setup.exe.sha256`
- `probraw-0.3.8.tar.gz`
- `probraw-0.3.8-py3-none-any.whl`
- `probraw_0.3.8_python_artifacts.sha256`

## Release 0.3.7

La release 0.3.7 corrige la equivalencia visual entre ProbRAW y aplicaciones
externas con gestion de color, y refuerza las herramientas de analisis:

- la preview y los TIFF exportados usan la misma receta efectiva y ruta ICC,
- el zoom a 100% y superiores muestra pixeles reales sin interpolacion y
  conserva el centro de la zona analizada,
- ESF/LSF/MTF muestran conteo de muestras, escala de pixeles, MTF50 y MTF50P,
- Auto nitidez penaliza halos, picos sobreenfocados y energia post-Nyquist,
- los perfiles ICC de carta quedan separados de ajustes manuales de color,
  contraste y detalle,
- el recálculo automatico MTF se pausa fuera de Nitidez para que los ajustes
  cromaticos no ejecuten calculos MTF ocultos.

Artefactos esperados:

- `ProbRAW-0.3.7-Setup.exe`
- `ProbRAW-0.3.7-Setup.exe.sha256`
- `probraw-0.3.7.tar.gz`
- `probraw-0.3.7-py3-none-any.whl`
- `probraw_0.3.7_python_artifacts.sha256`

## Release 0.3.6

La release 0.3.6 consolida la trazabilidad por imagen de ICC, color/contraste,
nitidez y exportacion RAW:

- las mochilas RAW y miniaturas muestran las categorias de ajuste activas por
  imagen,
- Color/Calibracion separa ICC generico, ICC de camara existente e ICC generado
  con carta,
- la preview aplica conversion de ICC de imagen a ICC de monitor para
  visualizacion,
- RAW/exportacion se centra en lectura/demosaico RAW y puntos de negro,
- los histogramas de curva tonal se actualizan en tiempo real, muestran columnas
  RGB y aislan el canal cromatico activo al editarlo,
- Auto nitidez escribe nitidez/radio en la mochila RAW.

Artefactos esperados:

- `ProbRAW-0.3.6-Setup.exe`
- `ProbRAW-0.3.6-Setup.exe.sha256`
- `probraw-0.3.6.tar.gz`
- `probraw-0.3.6-py3-none-any.whl`
- `probraw_0.3.6_python_artifacts.sha256`

## Release 0.3.5

La release 0.3.5 es una release de rendimiento y fiabilidad para flujos RAW de
tamaño profesional:

- el analisis MTF frio prepara una ROI a resolucion completa en un proceso
  externo y reutiliza una cache ROI persistente para recalculos posteriores,
- la barra superior de progreso es ahora el visor global unico para operaciones
  largas de preview, MTF y tareas de fondo, con tiempo transcurrido y ETA,
- la pestaña `Nitidez` ya no duplica una segunda barra local de progreso,
- el revelado de cola aplica la mochila de cada RAW cuando no hay id de perfil
  de ajuste registrado, de modo que nitidez, ruido, CA, color y contraste llegan
  al TIFF final,
- cambiar a una imagen sin configurar restablece controles de revelado y estado
  ICC activo a la politica neutra ProPhoto/balance-de-camara,
- los espacios genericos sin carta desactivan profiling mode/WB identidad para
  el render visible/final, y RGB de camara sin ICC de entrada se rechaza antes
  de escribir TIFF.

Artefactos esperados:

- `probraw_0.3.5_amd64.deb`
- `probraw_0.3.5_amd64.deb.sha256`
- `probraw-0.3.5.tar.gz`
- `probraw-0.3.5-py3-none-any.whl`
- `probraw_0.3.5_python_artifacts.sha256`

## Release 0.3.4

La release 0.3.4 publica el análisis MTF de nitidez persistente a resolución
completa:

- las curvas `ESF`, `LSF` y `MTF` de borde inclinado se guardan en la mochila
  sidecar de cada RAW,
- al reabrir una imagen se recuperan ROI y curvas sin seleccionar de nuevo el
  borde,
- el recálculo mapea la ROI del visor sobre la fuente real a resolución
  completa, evitando mediciones sobre miniaturas o previews reducidas,
- dos miniaturas seleccionadas con MTF guardada pueden compararse con curvas
  superpuestas y tabla numérica,
- actualizados el catálogo Qt en inglés y los manuales de usuario para las
  nuevas herramientas.

Artefactos esperados:

- `probraw_0.3.4_amd64.deb`
- `probraw_0.3.4_amd64.deb.sha256`
- `probraw-0.3.4.tar.gz`
- `probraw-0.3.4-py3-none-any.whl`
- `probraw_0.3.4_python_artifacts.sha256`

## Release 0.3.3

La release 0.3.3 consolida el flujo gráfico de sesión, ajustes y gestión de
color:

- estadísticas y sesiones recientes en `1. Sesión`,
- tercera columna organizada por flujo: color/calibración, ajustes
  personalizados y RAW/exportación,
- barra de herramientas horizontal del visor con iconos compactos y botón para
  enfocar/restaurar columnas laterales,
- histograma RGB colorimétrico fijo en `Ajustes personalizados`,
- curvas por canal y recuperación automática de datos de carta desde
  `profile_report.json`,
- manuales y capturas actualizados con la política de previsualización: ICC de
  entrada para interpretar la imagen, ICC del monitor solo como última capa de
  visualización.

Artefactos esperados:

- `probraw_0.3.3_amd64.deb`
- `probraw_0.3.3_amd64.deb.sha256`
- `probraw-0.3.3.tar.gz`
- `probraw-0.3.3-py3-none-any.whl`
- `probraw_0.3.3_python_artifacts.sha256`

## Release 0.3.2

La release 0.3.2 corrige el icono de la aplicacion en menus Linux:

- la entrada `.desktop` usa `Icon=/usr/share/pixmaps/probraw.png` como ruta
  absoluta para evitar fallos de cache/resolucion del tema hicolor,
- las validaciones del paquete y de instalacion comprueban ese icono real.

Artefactos esperados:

- `probraw_0.3.2_amd64.deb`
- `probraw_0.3.2_amd64.deb.sha256`
- `probraw-0.3.2.tar.gz`
- `probraw-0.3.2-py3-none-any.whl`
- `probraw_0.3.2_python_artifacts.sha256`

## Release 0.3.1

La release 0.3.1 actualiza la identidad visual de ProbRAW:

- nuevo logo e icono ProbRAW sin restos de la marca anterior,
- assets SVG, PNG e ICO regenerados para README, aplicacion e instaladores,
- artefactos de distribucion publicados con los nombres `probraw_*` /
  `probraw-*`.

Artefactos esperados:

- `probraw_0.3.1_amd64.deb`
- `probraw_0.3.1_amd64.deb.sha256`
- `probraw-0.3.1.tar.gz`
- `probraw-0.3.1-py3-none-any.whl`
- `probraw_0.3.1_python_artifacts.sha256`

## Release 0.3.0

La release 0.3.0 introduce:

- cambio completo de marca a ProbRAW en metadatos de paquete, identidad GUI,
  comandos, iconos, documentacion y nombres de artefactos de release,
- metadatos Debian de sustitucion/conflicto para paquetes beta anteriores
  `nexoraw` e `iccraw`,
- compatibilidad de migracion para `.nexoraw.json`, `.nexoraw.proof.json` y
  etiquetas beta C2PA/Proof,
- declaracion explicita del liderazgo de Probatia Forensics SL
  (https://probatia.com) en colaboracion con la Asociacion Espanola de Imagen
  Cientifica y Forense (https://imagencientifica.es).

## Release 0.2.6

La release 0.2.6 introduce:

- generación de perfiles avanzada en segundo plano para mantener la GUI
  responsiva,
- catálogo persistente de perfiles ICC de sesión con varias versiones activables,
- comparador `Gamut 3D` por pares para perfiles de sesión, monitor, perfiles
  estándar e ICC personalizados,
- gestión visual de referencias de carta, incluyendo importación, creación,
  validación y editor tabular Lab con muestras de color,
- artefactos de perfilado versionados en `00_configuraciones/profile_runs/`.

## Release 0.2.5

La release 0.2.5 introduce:

- estructura canonica del paquete Python bajo `src/probraw`,
- retirada del antiguo namespace interno de compatibilidad,
- division de la GUI en modulos mas pequenos por area de flujo,
- nombres de empaquetado Linux y Windows actualizados,
- etiquetas C2PA de asercion/accion generadas como `org.probatia.probraw.*`,
  manteniendo compatibilidad de verificacion con manifiestos beta anteriores,
- documentacion bilingüe actualizada y roadmap DCP+ICC archivado a favor del
  flujo activo centrado en ICC.

## Release 0.2.4

La release 0.2.4 introduce:

- selector de idioma de interfaz con autodeteccion del idioma del sistema,
- preferencia de idioma persistida mediante Qt settings,
- cambio de idioma mas seguro: se aplica al proximo arranque en lugar de
  reiniciar automaticamente la aplicacion.

## Release 0.2.3

La release 0.2.3 introduce:

- flujo sin carta con perfiles estandar reales en lugar de perfiles genericos
  generados por ProbRAW,
- seleccion preferente de `AdobeRGB1998.icc` cuando existe en el sistema,
- manifiestos ProbRAW Proof/C2PA con ajustes completos de receta, nitidez,
  contraste/render y gestion de color,
- visor de metadatos ampliado para mostrar esos ajustes reproducibles.

## Release 0.2.2

La release 0.2.2 introduce:

- multiprocessing real por proceso en `batch-develop`,
- cache numerica opt-in de demosaico,
- tests golden de hashes canonicos,
- benchmarks reproducibles de RAW y GUI,
- refresco final de preview en segundo plano para evitar lag al soltar
  sliders/curva,
- heuristica de RAM por worker ajustada con RAW Nikon D850 real.
