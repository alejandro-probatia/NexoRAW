# Manual de usuario de ProbRAW

_English version: [MANUAL_USUARIO.md](MANUAL_USUARIO.md)_

ProbRAW es una aplicación gratuita y abierta para revelado RAW/TIFF con
criterios reproducibles, gestión de color ICC y trazabilidad. Está pensada para
fotografía técnico-científica, documental, patrimonial y forense: el RAW
original no se modifica nunca y cada TIFF final queda vinculado a sus ajustes,
perfiles, hashes y artefactos de auditoría.

![ProbRAW: interfaz principal de revelado y perfilado](assets/screenshots/probraw-portada.png)

Este manual cubre el flujo completo de ProbRAW 0.4.x: creación de sesión,
perfilado con carta, perfil manual sin carta, copia de ajustes, cola de revelado,
exportación TIFF, metadatos, Proof, C2PA, diagnóstico Gamut 3D/Lab 2D, muestras
Lab con cuentagotas, conjuntos comparativos de color, gestión de referencias de
carta, estadísticas de sesión, histograma colorimétrico, análisis MTF de nitidez,
configuración global y significado de todas las opciones visibles en la
interfaz.

## 1. Instalación y arranque

ProbRAW se instala mediante los paquetes publicados para cada plataforma. El
usuario no debe instalar Python, dependencias ni herramientas externas a mano.
El instalador deja disponibles:

- la aplicación gráfica `ProbRAW`;
- los comandos `probraw` y `probraw-ui` para usos avanzados;
- el icono de aplicación;
- los componentes necesarios para revelar, perfilar, firmar y leer metadatos.

En Linux, macOS y Windows, abre ProbRAW desde el menú de aplicaciones. En Linux
debe aparecer en la categoría de gráficos/fotografía.

Documentación relacionada con instalación y publicación:

- [Publicación de instaladores](RELEASE_INSTALLERS.md)
- [Paquete Debian](DEBIAN_PACKAGE.md)
- [Instalador Windows](WINDOWS_INSTALLER.md)

## 2. Conceptos de trabajo

### Sesión

Una sesión es la carpeta completa del proyecto. Contiene originales, ajustes,
lecturas de carta, perfiles, recetas, derivados, caché y artefactos de auditoría.

Estructura persistente:

| Carpeta | Uso |
| --- | --- |
| `00_configuraciones/` | `session.json`, recetas, referencias personalizadas, perfiles de ajuste, perfiles ICC, reportes, caché, intermedios y artefactos de trabajo. |
| `01_ORG/` | RAW originales, DNG, TIFF originales y capturas RAW/DNG de carta. Es el directorio de fuentes. |
| `02_DRV/` | TIFF derivados, previsualizaciones, manifiestos y salidas finales. |

Las sesiones antiguas con carpetas `raw/`, `charts/`, `exports/`, `profiles/`,
`config/` o `work/` se abren en modo compatible. ProbRAW resuelve esas rutas
contra la estructura actual cuando es posible, sin conversión destructiva.

### Perfiles de ajuste

ProbRAW guarda cuatro familias de ajustes independientes. Todas pueden vivir en
la mochila de cada RAW y también pueden guardarse como perfiles de sesión para
reutilizarlas:

- **Perfil ICC de la imagen**: perfil que describe cómo interpretar la imagen.
  Puede ser un perfil ICC RGB estándar, un ICC generado en la sesión o un perfil
  ICC de cámara localizado en el sistema.
- **Color y contraste**: brillo, niveles, contraste, curvas, iluminante,
  temperatura, matiz y punto neutro.
- **Nitidez**: enfoque, radio, reducción de ruido, corrección de aberración
  cromática lateral y, si existe, resultado de auto nitidez basado en MTF.
- **RAW / exportación**: lectura RAW, método de desentramado, opciones
  específicas del algoritmo y punto negro RAW.

El ajuste puede existir aunque todavía no se haya guardado como perfil nombrado:
ProbRAW actualiza la mochila del RAW al mover los controles. Guardar un perfil
de sesión sirve para reutilizarlo de forma explícita en otros archivos.

### Mochila ProbRAW

La mochila es el sidecar `RAW.probraw.json` que queda junto al RAW. Guarda los
ajustes asignados a esa imagen concreta. Las miniaturas muestran iconos discretos
bajo la imagen, sin tapar la fotografía:

- `ICC`: la imagen tiene un perfil ICC aplicado.
- tres círculos RGB: hay ajustes de color y contraste.
- círculo medio blanco y medio negro: hay ajustes de nitidez/detalle.
- cuatro píxeles Bayer 2x2: hay ajustes RAW / exportación.

Al cambiar de imagen, ProbRAW lee la mochila de ese RAW concreto. Si no existe
mochila, los controles de receta, detalle, nitidez, ruido, aberración cromática,
color y contraste vuelven a un estado neutro; la preview se prepara como RAW sin
perfil personalizado usando ProPhoto RGB como perfil ICC RGB estándar
predeterminado y balance de blancos de cámara.

### Política de color

ProbRAW evita añadir una capa DCP subjetiva encima del flujo ICC. La base de
trabajo recomendada es científica y reproducible:

- con carta: se mide una referencia colorimétrica, se genera una receta
  calibrada y se crea un perfil ICC de entrada propio de la sesión;
- sin carta o sin ICC específico: se usa un perfil ICC RGB estándar real
  (`sRGB`, `Adobe RGB (1998)` o `ProPhoto RGB`) como perfil de la imagen;
- el perfil del monitor solo afecta a la visualización en pantalla. Nunca cambia
  el TIFF, el perfil de sesión, los hashes, los manifiestos ni el histograma de
  análisis.
- si existe un ICC de entrada generado con carta o elegido para la imagen, la
  preview y el histograma colorimétrico deben usar ese perfil antes de aplicar el
  ICC del monitor.

Regla práctica:

| Situación | Salida recomendada |
| --- | --- |
| Hay carta válida | TIFF en RGB de cámara/sesión con ICC de entrada generado e incrustado. |
| No hay carta | TIFF revelado con el perfil ICC RGB estándar elegido e ICC incrustado. |
| Revisión en pantalla | Perfil ICC del monitor aplicado solo al preview, como última capa de salida. |
| Histograma de análisis | Señal colorimétrica de preview antes del ICC del monitor. |

## 3. Mapa de interfaz

### Barra superior

| Control | Función |
| --- | --- |
| `Inicio` | Navega al directorio personal del usuario. |
| `Abrir carpeta...` | Abre una carpeta; si pertenece a una sesión, ProbRAW reconoce la raíz. |
| `Recargar` | Vuelve a listar el directorio actual y refresca miniaturas. |
| `Pantalla completa` | Alterna pantalla completa. Equivale a `F11`. |
| Barra de estado/progreso | Muestra la tarea activa, estados de carga y progreso global. |

### Menús

| Menú | Opciones |
| --- | --- |
| `Archivo` | Crear sesión, abrir sesión, guardar sesión (`Ctrl+Shift+S`), abrir carpeta (`Ctrl+O`), guardar preview PNG (`Ctrl+S`), aplicar ajustes a selección (`Ctrl+R`) y salir (`Ctrl+Q`). |
| `Configuración` | Cargar receta, guardar receta, restaurar receta por defecto, abrir configuración global y saltar a las pestañas Sesión/Revelado/Cola. |
| `Perfil ICC` | Cargar perfil activo, usar perfil generado y comparar reportes QA. |
| `Vista` | Comparar original/resultado, ir a Nitidez, pantalla completa y restablecer distribución de paneles. |
| `Ayuda` | Diagnóstico de herramientas, búsqueda de actualizaciones y acerca de ProbRAW. |

### Actualización asistida

`Ayuda > Buscar actualizaciones...` abre el asistente de actualización. El
asistente comprueba GitHub Releases, muestra la versión actual, la última
release publicada, el instalador detectado para el sistema, su tamaño y si hay
verificación SHA-256 disponible. Al continuar, descarga el instalador en
`Downloads/ProbRAW updates`, verifica el hash cuando la release lo publica y
abre el instalador en modo visible para que puedas confirmar los pasos.
Los nombres de instalador y checksum se validan antes de escribir en disco para
evitar rutas externas al directorio de descargas. En Linux se aceptan paquetes
`.deb`, `.rpm`, AppImage y Arch `pkg.tar.*` cuando pertenecen a la plataforma.

Antes de instalar, guarda el trabajo abierto. Si el instalador lo solicita,
cierra ProbRAW y vuelve a abrirlo tras finalizar para confirmar la versión en
`Ayuda > Acerca de ProbRAW`.

### Pestañas principales

| Pestaña | Uso |
| --- | --- |
| `1. Sesión` | Crea o abre la estructura del proyecto y guarda notas de captura. |
| `2. Ajustar / Aplicar` | Navega archivos, previsualiza, ajusta, perfila, copia ajustes y prepara exportaciones. |
| `3. Cola de Revelado` | Procesa lotes con el perfil asignado a cada archivo. |

## 4. Crear o abrir una sesión

![Gestión de sesión](assets/screenshots/probraw-sesion.png)

En `1. Sesión`:

| Opción | Explicación |
| --- | --- |
| `Directorio raíz de sesión` | Carpeta principal del proyecto. Dentro se crean `00_configuraciones`, `01_ORG` y `02_DRV`. |
| `Nombre de sesión` | Nombre humano del proyecto, guardado en `00_configuraciones/session.json`. |
| `Condiciones de iluminación` | Nota libre sobre luz, carta, temperatura, flash, escena o entorno. |
| `Notas de toma` | Nota libre sobre cámara, óptica, exposición, trípode, procedimiento o incidencias. |
| `Usar carpeta actual` | Copia el directorio del navegador como raíz de sesión. Si estás dentro de `01_ORG`, detecta la raíz. |
| `Crear sesión` | Crea carpetas y un `session.json` nuevo. |
| `Abrir sesión` | Abre una sesión existente desde su raíz. |
| `Guardar sesión` | Guarda metadatos, estado de interfaz, selección, cola y rutas persistidas. |
| `Sesiones recientes` | Permite volver a abrir sesiones usadas recientemente sin buscar la carpeta. |
| `Resumen de sesión` | Muestra RAW, TIFF, perfiles ICC, perfiles de ajuste, mochilas RAW y cola activa. |

Flujo mínimo:

1. Elige una carpeta raíz para el proyecto.
2. Escribe nombre, iluminación y notas de toma si procede.
3. Pulsa `Crear sesión` o `Abrir sesión`.
4. Coloca los RAW de escena y los RAW/DNG de carta en `01_ORG/`.
5. Entra en `2. Ajustar / Aplicar`.

Al abrir una sesión existente, ProbRAW normaliza las carpetas persistidas para
que `00_configuraciones/`, `01_ORG/`, `02_DRV/`, perfiles, referencias, trabajo
y caché queden dentro de la raíz de sesión. Si un `session.json` antiguo o
copiado desde otro sistema contiene rutas absolutas externas, se sustituyen por
las rutas canónicas del proyecto.

## 5. Panel izquierdo: navegación, diagnóstico y metadatos

En `2. Ajustar / Aplicar`, el panel izquierdo tiene pestañas verticales. La
pestaña `Visor` ya no existe: sus acciones se han movido a la barra horizontal
del visor central para ahorrar espacio.

### Explorador

| Opción | Explicación |
| --- | --- |
| `Unidad / raíz` | Selecciona la unidad o punto de montaje visible para el navegador. |
| `Actualizar` | Relee unidades montadas y refresca el árbol. |
| Árbol de carpetas | Cambia el directorio actual. ProbRAW lista archivos compatibles en la tira de miniaturas. |
| Clic derecho sobre carpeta | Abre esa carpeta en el explorador de archivos del sistema. |

Archivos navegables: RAW soportados por el motor, DNG, TIFF, PNG, JPEG y JPG.
Para referencias colorimétricas de perfil ICC de cámara/sesión solo se aceptan
RAW/DNG originales. Los TIFF, incluso lineales, son salidas de auditoría o
visualización y no se usan como fuente de perfilado de cámara.

### Diagnóstico

| Opción | Explicación |
| --- | --- |
| `Imagen` | Análisis técnico lineal del preview: rangos, clipping y medidas útiles para revisar si los ajustes son estables. |
| `Carta` | Tabla de parches Lab de referencia, Lab estimado por ICC y DeltaE76/DeltaE2000. Se rellena al generar perfil y se recupera desde `profile_report.json` al abrir la sesión. |
| Botón actualizar en `Carta` | Relee datos de carta desde el reporte de perfil activo o los reportes registrados en la sesión. |
| `Gamut 3D` | Comparación visual por pares entre ICC de sesión, monitor, espacios estándar o ICC personalizado. Puede verse como Lab 3D o como corte bidimensional Lab a*b* con selector vertical de L*. |
| `Muestras` | Cuentagotas Lab para medir píxeles reales, guardar tomas por imagen, agruparlas en conjuntos y comparar grupos mediante medias, DeltaE y gamut de muestras. |

### Metadatos

![Visor de metadatos](assets/screenshots/probraw-metadatos.png)

| Opción | Explicación |
| --- | --- |
| `Leer metadatos` | Relee metadatos del archivo seleccionado. |
| `JSON completo` | Cambia a la pestaña con el volcado completo. |
| `Resumen` | Campos técnicos principales. |
| `EXIF` | Datos EXIF y de fabricante disponibles. |
| `GPS` | Coordenadas si existen. |
| `C2PA` | Información de manifiesto C2PA/CAI si está presente. |
| `Todo` | JSON completo de lectura. |

### Log

Muestra eventos de preview, advertencias, trazas de ejecución y mensajes de flujo.

## 6. Visor central y miniaturas

| Opción | Explicación |
| --- | --- |
| Barra de herramientas superior | Acceso horizontal a comparación A/B, aplicación ICC, enfoque de columnas, zoom, 1:1, giro, encaje y precaché. |
| `A/B` | Compara original/resultado. Al activarla, ProbRAW fuerza preview de máxima calidad cuando es necesario. |
| Icono de validación ICC | Fuerza el recálculo del preview con el ICC elegido para la imagen. Ese ICC debe corresponder a cámara, receta e iluminación actuales. |
| Icono de columnas | Oculta/restaura columnas laterales para revisar la imagen con más espacio. |
| `-` / `+` | Reduce o aumenta zoom. |
| Lupa `1:1` | Muestra a píxel real. |
| Flechas circulares | Rotan la visualización a izquierda o derecha. No modifican el RAW. |
| Encajar | Ajusta la imagen al visor. |
| Iconos de caché | Calculan previews normales o 1:1 para los RAW visibles. |
| Visor `Resultado` | Preview del RAW con ajustes actuales. |
| Vista `Antes` / `Después` | Aparece al activar comparar original/resultado. |
| Tira `Miniaturas` | Lista los archivos compatibles del directorio actual. Permite selección múltiple. |
| Slider de miniaturas | Cambia tamaño entre los límites de la aplicación. |

Los botones que antes aparecían bajo las miniaturas se han eliminado. Las
acciones de archivo están en el menú contextual de miniatura y en los paneles de
la derecha.

El menú contextual de miniatura ofrece:

- `Guardar ajustes actuales en imagen`: fuerza la escritura de la mochila del
  RAW seleccionado.
- `Copiar ajustes`: permite copiar todos los ajustes aplicados o solo una
  categoría: `Perfil ICC`, `Color y contraste`, `Nitidez` o `RAW / exportación`.
- `Pegar ajustes copiados`: pega en la selección únicamente las categorías
  copiadas, sin tocar las demás.
- `Usar como referencia colorimétrica`: marca la selección RAW/DNG como captura
  de carta para el flujo de generación ICC.
- `Comparar MTF de selección`: disponible cuando hay dos miniaturas
  seleccionadas con datos MTF.
- `Anadir a cola`: envía los archivos seleccionados a la cola de revelado.

## 7. Flujo completo con carta de color

Este es el flujo preferente cuando se busca un perfil ICC de cámara/sesión
medido con una carta de color.

![Flujo con carta de color](assets/screenshots/probraw-flujo-con-carta.png)

1. Crea o abre la sesión.
2. Copia los RAW/DNG de carta y los RAW de escena a `01_ORG/`.
3. En `Color / calibración`, elige `Generar perfil ICC`.
4. Selecciona la captura o capturas RAW/DNG de carta en las miniaturas y usa el
   menú contextual `Usar como referencia colorimétrica`.
5. Revisa `Referencia de carta`, `Tipo de carta`, `Formato ICC`, `Tipo de perfil
   ICC` y `Calidad colprof`.
6. En `RAW / exportación`, revisa solo los criterios de lectura RAW relevantes
   para la medición: método de desentramado, opciones del algoritmo y punto
   negro RAW. La generación ICC no depende de ajustes de color, contraste ni
   nitidez.
7. Si la detección automática no es suficiente, pulsa `Marcar en visor`. El
   puntero cambia a cruz. Marca las cuatro esquinas visibles de la carta en el
   orden que muestra el overlay. ProbRAW dibuja entonces las 24 zonas centrales
   de lectura; revísalas, arrastra cualquier zona que caiga sobre polvo, borde,
   brillo o mancha y pulsa `Guardar detección`.
8. Pulsa `Generar ICC con carta`.
9. Revisa el JSON de resultado, los overlays, el reporte QA y el estado del
   perfil.
10. Pulsa `Usar ICC generado` si quieres activarlo en la imagen actual.
11. Usa `Aplicar ICC a selección` o `Aplicar ICC a sesión` para asignarlo a
    imágenes tomadas bajo la misma cámara, óptica, luz y receta.
12. Revela la cola y revisa los TIFF en `02_DRV/`.

Resultado esperado:

- receta calibrada en `00_configuraciones/`;
- ICC de entrada en `00_configuraciones/profiles/`;
- registro del ICC en la sesión junto a la receta calibrada que debe usarse con
  ese perfil;
- referencias personalizadas en `00_configuraciones/references/`, si se han
  creado o importado;
- reportes de perfil, QA, overlays y caché en
  `00_configuraciones/profile_runs/` y `00_configuraciones/work/`;
- mochila `RAW.probraw.json` en los RAW a los que se aplique ese ICC.

### Referencias de carta y cartas personalizadas

![Gestión de referencias de carta y perfiles ICC](assets/screenshots/probraw-referencias-y-perfiles.png)

La referencia incluida por defecto es ColorChecker 24 / ColorChecker 2005 / D50.
También puedes importar un JSON existente o crear una referencia personalizada de
sesión. Las referencias propias se guardan en
`00_configuraciones/references/`, aparecen en el selector `Referencia de carta`
y se conservan al cerrar y abrir la sesión.

Para una carta personalizada, usa `Nueva personalizada` o `Editar tabla`. El
editor muestra una fila por parche con identificador, nombre y valores Lab D50;
la primera columna pinta una muestra aproximada del color introducido para
detectar errores obvios de tecleo. Al guardar, ProbRAW genera el JSON de
referencia que usará el perfilador.

![Editor tabular de referencia Lab](assets/screenshots/probraw-editor-referencia-lab.png)

Buenas prácticas:

- los `patch_id` deben coincidir con el orden de detección de la carta;
- usa valores Lab D50 con observador 2 grados para el flujo ICC actual;
- documenta la fuente de medición en `Fuente`;
- pulsa `Validar` antes de generar el perfil.

Las comprobaciones QA no impiden generar el ICC salvo que no existan muestras de
carta válidas o que el error contra la referencia colorimétrica supere los
umbrales definidos. La validación independiente queda como diagnóstico adicional:
si falta o no es concluyente, no convierte por sí sola el perfil en pendiente QA.
En ColorChecker 24,
`shaper+matrix (-as)`
es la opción conservadora; los modos cLUT siguen disponibles como opción avanzada
y se documentan como posible sobreajuste si no hay una carta con más parches.
Un perfil mostrado como `rechazado` conserva internamente el estado `rejected`,
no se activa automáticamente y, si se intenta activar desde la lista de sesión o
   desde el menú, ProbRAW muestra una confirmación explícita porque ese ICC puede
   introducir dominantes, clipping o conversiones no fiables.
   Además, los perfiles `rechazado` no cargan su receta calibrada como ajuste
   activo ni se asignan automáticamente a los RAW de carta.

Durante el perfilado, ProbRAW mide la carta con una receta científica neutral:
balance de blancos fijo `[1, 1, 1, 1]`, 0 EV, salida lineal y RGB de
cámara/sesión. Esta receta evita que un ajuste visual, una receta calibrada
anterior o una compensación de exposición acumulada saturen el render usado para
medir parches. Si el informe indica saturación, se refiere a ese render
científico de muestreo; no implica necesariamente que el RAW estuviera saturado
en cámara.

### Datos de carta, perfiles ICC de sesión y comparación Gamut 3D

Cada perfil ICC generado queda registrado en la sesión con nombre, ruta, estado y
origen. Esto permite tener varias versiones del mismo perfil, por ejemplo matriz,
cLUT, diferentes referencias o diferentes argumentos de ArgyllCMS, sin perder el
historial. El selector `Perfil de sesión` permite activar cualquiera de esas
versiones como ICC de la imagen.

La pestaña `Diagnóstico > Carta` muestra los datos de la carta en curso:
identificador de parche, Lab de referencia, Lab estimado tras el ICC generado y
DeltaE. Si reabres una sesión, ProbRAW busca el `profile_report.json` asociado al
ICC activo o a los perfiles registrados y vuelve a poblar la tabla. El botón de
actualización fuerza esa lectura si has copiado reportes después de abrir la
sesión.

![Diagnóstico de carta con DeltaE por parche](assets/screenshots/probraw-diagnostico-carta.jpeg)

La pestaña `Diagnóstico > Gamut 3D` compara siempre un par de perfiles, no todos
a la vez. Elige `Perfil A` y `Perfil B` entre perfiles de sesión, el ICC activo,
el monitor, sRGB, Adobe RGB, ProPhoto RGB o un ICC personalizado. En `Lab 3D`, la
superficie sólida representa el segundo perfil y la malla el primero. En `Lab 2D`
se muestra un corte bidimensional a*b*; el selector vertical `L*` desplaza el
corte de luminosidad y ayuda a revisar diferencias de saturación y zonas fuera
de gama sin depender de la perspectiva 3D. El texto superior indica qué
porcentaje del perfil A queda dentro del perfil B y avisa cuando el ICC generado
tiene coordenadas Lab extremas.

![Comparador Gamut 3D por pares](assets/screenshots/probraw-gamut-3d-comparacion-actual.jpeg)

### Muestras Lab, conjuntos y comparación de color

La pestaña `Diagnóstico > Muestras` permite medir colores directamente sobre la
imagen visualizada. Activa `Cuentagotas Lab`, elige la matriz de muestreo (`1x1`,
`3x3`, `5x5`, `9x9` o `17x17`) y haz clic en el visor. Mientras la herramienta
está activa, el visor muestra una lupa con la cuadrícula de píxeles reales para
elegir con precisión el píxel o grupo de píxeles que se va a medir.

![Muestras Lab agrupadas y marcadores sobre la imagen](assets/screenshots/probraw-muestras-lab-conjuntos.jpeg)

Cada toma queda numerada en la imagen y en la tabla. El marcador usa como fondo
el color obtenido o el color manual elegido para distinguir la zona medida. Al
seleccionar una muestra, el visor la resalta con contorno amarillo para revisar
su posición. Las tomas se guardan en la mochila `RAW.probraw.json` de la imagen,
de modo que cada archivo puede conservar su propio conjunto de mediciones.

La tabla de muestras muestra posición, matriz, RGB normalizado, Lab, C*, estado
dentro/fuera de los perfiles comparados, pertenencia a gama común y diferencias
`DE76 ref`, `DE00 ref` y `DC* ref` frente al conjunto de referencia activo. Las
columnas `Conjunto`, `Nombre` y `Nota` son editables: usa `Conjunto` para agrupar
mediciones que representan una misma tinta, zona o material, y `Nombre`/`Nota`
para documentar el criterio de toma. Las columnas se autoajustan al cargar la
tabla, pero pueden redimensionarse manualmente.

El modo `Fichas` muestra la misma información como tarjetas compactas. Cada ficha
incluye selección rápida y controles para cambiar el color visual del marcador
sin alterar la lectura RGB/Lab. La tabla de conjuntos calcula RGB medio, Lab
medio, C*, dispersión interna `DE00`, máximo interno `DE00`, similitud
porcentual frente al conjunto de referencia y mínimos, medias y máximos de
DeltaE entre conjuntos. El gráfico inferior dibuja el gamut de cada conjunto de
muestras en Lab a*b*, con puntos y envolvente visual cuando hay suficientes
tomas; el botón de ampliación abre el mismo gráfico en una ventana grande. No
existe ya una muestra primaria dentro de un conjunto: la referencia comparativa
se elige a nivel de conjunto.

Precisión colorimétrica:

- el RGB de la muestra procede de la imagen cargada a tamaño real; si ProbRAW
  detecta que se está trabajando con una preview reducida, solicita recarga a
  resolución completa antes de medir;
- si nitidez, reducción de ruido o corrección de aberración cromática necesitan
  un recálculo exacto a tamaño real, ProbRAW lo ejecuta antes de guardar la
  muestra;
- el valor Lab y los DeltaE solo son rigurosos cuando la imagen usa un ICC de
  sesión generado por ProbRAW para esa cámara, receta e iluminación;
- si se usa sRGB, Adobe RGB, ProPhoto RGB u otro perfil genérico, el resultado
  Lab es una lectura orientativa del espacio asignado, no una medición
  colorimétrica validada de la escena;
- las comparaciones de gamut de perfiles y las comparaciones de conjuntos son
  herramientas de diagnóstico: no modifican recetas, píxeles, perfiles activos
  ni exportaciones.

## 8. Flujo completo sin carta de color

Este flujo es válido cuando no existe referencia colorimétrica. Es menos
objetivo, pero sigue siendo paramétrico y trazable.

![Flujo sin carta de color](assets/screenshots/probraw-flujo-sin-carta.png)

1. Selecciona una imagen representativa.
2. En `Color / calibración`, deja `Perfil ICC RGB estándar` o elige otro ICC
   disponible. Si no haces nada, ProbRAW usa `ProPhoto RGB`.
3. Ajusta `Color y contraste`, `Nitidez` y, si es necesario, `RAW / exportación`.
   Cada cambio se guarda en la mochila del RAW seleccionado.
4. Si quieres reutilizar el ajuste como perfil de sesión, usa `Perfiles
   guardados` en la pestaña correspondiente y pulsa `Guardar`.
5. Copia y pega los ajustes a otras imágenes equivalentes desde el menú
   contextual de miniatura, eligiendo todos los ajustes o solo una categoría.
6. Añade las imágenes a la cola y revela.

Resultado esperado:

- mochila `RAW.probraw.json` con el ICC de la imagen y los ajustes aplicados;
- perfiles de sesión en `00_configuraciones/development_profiles/` si los has
  guardado;
- TIFF final en `02_DRV/` con el ICC elegido incrustado.

El panel RAW no decide un perfil de salida. La decisión ICC vive en
`Color / calibración`; RAW solo controla cómo se lee y se desentraman los datos
del sensor antes de aplicar visualización, color, contraste o nitidez.

## 9. Copiar ajustes y mochilas

![Mochilas y copia de ajustes](assets/screenshots/probraw-mochila-ajustes.png)

ProbRAW trata el revelado como edición paramétrica por archivo.

1. Selecciona la imagen con los ajustes correctos.
2. Si quieres forzar la escritura antes de copiar, abre el menú contextual y
   pulsa `Guardar ajustes actuales en imagen`.
3. Abre `Copiar ajustes` y elige `Todos los ajustes aplicados` o una categoría:
   `Perfil ICC`, `Color y contraste`, `Nitidez` o `RAW / exportación`.
4. Selecciona una o varias imágenes de destino.
5. Pulsa `Pegar ajustes copiados`.
6. Revisa los iconos bajo la miniatura y, si procede, añade a cola.

El pegado es parcial: si copias solo `Nitidez`, ProbRAW no sustituye el ICC, los
ajustes cromáticos ni los ajustes RAW de destino. Si copias todas las categorías,
la imagen de destino queda con la misma mochila técnica que la imagen origen.

Buenas prácticas:

- no pegues ajustes cromáticos entre escenas con iluminación distinta;
- no mezcles perfiles ICC de una cámara/óptica con otra combinación;
- copia RAW / exportación solo entre archivos que deben compartir el mismo
  método de lectura y desentramado;
- conserva las mochilas junto a los RAW si mueves la sesión.

## 10. Cola de revelado y exportación

![Cola de revelado](assets/screenshots/probraw-cola-revelado.png)

La cola procesa una selección o lote completo sin perder qué perfil corresponde
a cada archivo.

### Pestaña `3. Cola de Revelado`

| Opción | Explicación |
| --- | --- |
| `Añadir selección` | Añade los archivos seleccionados en miniaturas. |
| `Añadir RAW de sesión` | Añade todos los archivos compatibles de la carpeta de entrada configurada. |
| `Asignar perfil activo` | Asigna el perfil activo disponible a las filas seleccionadas o a la cola. |
| `Quitar seleccionados` | Elimina filas seleccionadas de la cola. |
| `Limpiar cola` | Vacía la cola. |
| `Revelar cola` | Ejecuta el revelado TIFF de los elementos válidos. |
| Tabla `Archivo` | Fuente RAW/TIFF/imagen. |
| Tabla `Perfil` | Perfil o ajustes asignados al archivo. |
| Tabla `Estado` | `pending`, `queued`, `processing`, `done` o `error`. |
| Tabla `Progreso` | Barra interactiva por archivo: lectura, ajustes, escritura TIFF, completado o error. |
| Tabla `TIFF salida` | Ruta del TIFF generado. |
| Tabla `Mensaje` | Mensaje de proceso o error. |
| `Monitoreo de ejecución` | Estado global, progreso, tabla de tareas y log. |

Si el TIFF de salida ya existe, ProbRAW crea una versión nueva:
`captura.tiff`, `captura_v002.tiff`, `captura_v003.tiff`, etc.

Al revelar la cola, cada RAW usa su mochila guardada: ICC de imagen, color y
contraste, nitidez y RAW / exportación. Estos valores no se toman de otro
archivo ni de los sliders actuales.

### Panel `Exportar derivados`

| Opción | Explicación |
| --- | --- |
| `RAW a revelar (carpeta)` | Carpeta fuente usada por `Aplicar a carpeta` o `Añadir RAW de sesión`. |
| `Salida TIFF derivados` | Carpeta donde se guardan los TIFF finales. En una sesión normal apunta a `02_DRV/`. |
| `Incrustar/aplicar ICC en TIFF` | Siempre activo. Incrusta el ICC elegido para la imagen: ICC de cámara/sesión o perfil ICC RGB estándar. |
| `Aplicar ajustes básicos y de nitidez` | Aplica al TIFF los ajustes de tono, color, nitidez, ruido y CA del perfil. |
| `Compresión` | Modo TIFF final: sin compresión, ZIP/Deflate, LZW, JPEG o ZSTD. ZIP, LZW y ZSTD son sin pérdida; JPEG puede alterar píxeles. |
| `Hilos compresión` | `Auto` reparte CPU durante lotes; un valor fijo fuerza hilos por TIFF. |
| `Usar carpeta actual` | Usa el directorio del navegador como entrada de lote. |
| `Aplicar a selección` | Revela la selección actual. |
| `Aplicar a carpeta` | Revela todos los archivos compatibles de la carpeta de entrada. |
| `Salida JSON de exportación` | Resultado técnico del proceso de exportación. |

Cada TIFF puede generar TIFF 16-bit final, TIFF lineal de auditoría,
`*.probraw.proof.json`, mochila, `batch_manifest.json` y metadatos C2PA si
están configurados.

## 11. Panel derecho: referencia completa de ajustes

La columna derecha de `2. Ajustar / Aplicar` induce el flujo de trabajo:

| Pestaña | Uso |
| --- | --- |
| `Color / calibración` | Estado ICC de la imagen, elección de ICC RGB estándar, ICC de sesión o generación ICC con carta. |
| `Color y contraste` | Histograma colorimétrico siempre visible y controles de brillo, contraste y color. |
| `Nitidez` | Controles de acutancia, radio de enfoque, reducción de ruido y corrección de aberración cromática lateral. |
| `RAW / exportación` | Lectura RAW, desentramado, punto negro RAW, perfiles RAW/exportación y salida de derivados TIFF. |

El histograma de `Color y contraste` se calcula sobre la señal
colorimétrica previa al ICC del monitor. Si el perfil ICC de entrada está
activado, mide la preview resultante de ese perfil; después ProbRAW aplica el
perfil del monitor solo para mostrar correctamente en pantalla.

### Brillo y contraste

| Opción | Rango/valores | Explicación |
| --- | --- | --- |
| `Brillo` | `-2.00` a `+2.00 EV` | Compensación tonal final del preview/render. |
| `Nivel negro` | `0.000` a `0.300` | Recorta o levanta el punto negro de salida. |
| `Nivel blanco` | `0.500` a `1.000` | Define el punto blanco de salida. |
| `Contraste` | `-1.00` a `+1.00` | Ajuste de contraste global. |
| `Curva medios` | `0.50` a `2.00` | Modifica la respuesta de medios tonos. |
| `Curva tonal avanzada` | activada/desactivada | Habilita editor de curva y controles de rango. |
| `Canal curva` | Luminosidad, Rojo, Verde, Azul | Selecciona qué curva se edita. Luminosidad conserva mejor el tono; los canales modifican RGB directamente. |
| `Preset curva` | Lineal, Contraste suave, Similar a película, Sombras levantadas, Alto contraste, Personalizada | Carga una forma de curva editable. |
| `Negro curva` | `0.000` a `0.950` | Límite negro interno de la curva avanzada. |
| `Blanco curva` | `0.050` a `1.000` | Límite blanco interno de la curva avanzada. |
| Editor de curva | puntos arrastrables | Ajusta manualmente la curva tonal. |
| `Restablecer curva` | acción | Vuelve la curva avanzada a su estado base. |
| `Restablecer brillo y contraste` | acción | Restaura los controles tonales. |

El histograma del editor se actualiza en tiempo real con los ajustes de brillo,
niveles, contraste y curva. En `Luminosidad` muestra luminancia y columnas RGB.
Al editar `Rojo`, `Verde` o `Azul`, muestra solo el histograma de ese canal en
su color. Las curvas RGB no lineales permanecen visibles como referencia, la
curva activa se dibuja con el color del canal y una referencia punteada muestra
el efecto global sobre la luminosidad.

### Color

| Opción | Rango/valores | Explicación |
| --- | --- | --- |
| `Iluminante final` | A/tungsteno, D50, D55, Flash/D55, D60, D65, D75, Personalizado | Punto blanco objetivo para render. |
| `Temperatura (K)` | `2000` a `12000` | Temperatura manual cuando el iluminante es personalizado o se ajusta finamente. |
| `Matiz` | `-100.0` a `+100.0` | Corrección verde/magenta. |
| `Cuentagotas neutro` | activado/desactivado | Al activarlo, haz clic en una zona neutra del visor; el puntero cambia a cruz. |
| `Punto neutro` | lectura | Muestra el resultado de la muestra neutra. |
| `Restablecer color` | acción | Restaura iluminante, temperatura y matiz. |

### Nitidez

La parte superior de la pestaña incluye análisis MTF para un borde inclinado.
Pulsa `Seleccionar borde`, arrastra una ROI sobre el borde fotografiado y usa
las subpestañas `ESF`, `LSF`, `MTF` y `CA lateral` para revisar la respuesta. `Actualizar`
recalcula la medida; si `Actualizar MTF con los ajustes` está activo, se
recalcula al modificar nitidez, ruido o aberración cromática. `Ampliar` abre el
gráfico en una ventana mayor.

La ROI, las métricas y las curvas quedan guardadas en la mochila sidecar del
RAW. Al volver a cargar la captura, ProbRAW recupera el rectángulo y las curvas
sin tener que seleccionar de nuevo el borde; `Actualizar` recalcula la curva con
esa misma ROI. Desde dos miniaturas con MTF guardada puedes usar `Comparar MTF
de selección` para ver la tabla numérica y las curvas `ESF`, `LSF`, `MTF` y `CA lateral`
superpuestas.

`CA lateral` reutiliza la misma ROI de borde inclinado para mostrar los perfiles
normalizados R, G y B, la diferencia RGB y las métricas de aberración lateral:
`CA area`, desplazamientos de cruce R-G/B-G/R-B y anchura 10-90 del borde. Es un
análisis de imagen; no modifica por sí mismo los controles de corrección.

El cálculo MTF no se hace sobre la miniatura ni sobre una preview reducida:
ProbRAW carga la imagen real a resolución completa, aplica los ajustes activos
sin reescalar y convierte la ROI del visor a coordenadas de análisis. El sidecar
guarda tanto la ROI real usada para el cálculo como la ROI del visor empleada
para redibujar el rectángulo.

La métrica principal se expresa en ciclos/píxel. ProbRAW intenta rellenar
automáticamente `Tamaño de píxel (µm)` a partir de metadatos de tamaño de sensor
o resolución de plano focal. Si esos datos no existen, introduce `Sensor ancho
(mm)` y, si lo conoces, `Sensor alto (mm)`; ProbRAW deriva el tamaño de píxel
con las dimensiones de la imagen cargada. También puedes escribir directamente
`Tamaño de píxel (µm)` si ya lo conoces. Con ese valor, ProbRAW añade la
conversión a líneas por milímetro (`lp/mm`):
`lp/mm = ciclos/píxel × 1000 / tamaño_píxel_µm`. La conversión depende de que el
tamaño de píxel sea correcto para el archivo analizado.

`Auto nitidez` usa la ROI MTF seleccionada para evaluar combinaciones de
intensidad y radio a resolución real. Busca mejorar MTF50/MTF30/acutancia sin
penalizaciones excesivas por halos o ruido, escribe los valores resultantes en
los controles de `Nitidez` y actualiza inmediatamente la mochila RAW y el icono
de nitidez en la miniatura.

| Opción | Rango/valores | Explicación |
| --- | --- | --- |
| `Nitidez (amount)` | `0.00` a `3.00` | Intensidad de enfoque. |
| `Radio nitidez` | `0.1` a `8.0` | Radio de enfoque. |
| `Ruido luminancia` | `0.00` a `1.00` | Reducción de ruido de luminancia. |
| `Ruido color` | `0.00` a `1.00` | Reducción de ruido cromático. |
| `CA lateral rojo/cian` | factor cercano a `1.0000` | Compensa aberración cromática lateral rojo/cian. |
| `CA lateral azul/amarillo` | factor cercano a `1.0000` | Compensa aberración cromática lateral azul/amarillo. |
| `Modo precisión 1:1 para nitidez` | activado/desactivado | Usa fuente a resolución real durante arrastres de nitidez/ruido/CA. Es más lento. |
| `Sensor ancho (mm)` / `Sensor alto (mm)` | `0.000` a `200.000` | Tamaño físico del sensor para derivar el tamaño de píxel si los metadatos no lo indican. |
| `Tamaño de píxel (µm)` | `0.000` a `50.000` | Pitch usado para convertir ciclos/píxel a `lp/mm`; puede ser automático, derivado del sensor manual o escrito directamente. |
| `Denoise modo receta` | off, mild, medium, strong | Metadato de receta de compatibilidad. No modifica píxeles en la GUI. |
| `Sharpen modo receta` | off, mild, medium, strong | Metadato de receta de compatibilidad. No modifica píxeles en la GUI. |
| `Restablecer nitidez` | acción | Restaura nitidez, ruido y CA. |

### Color / calibración

La primera decisión de este panel es qué ICC describe la imagen. ProbRAW usa ese
ICC para la preview, para el histograma colorimétrico y para el TIFF final; la
conversión adicional al monitor solo sirve para visualizar correctamente en cada
sistema.

#### Estado ICC

| Opción | Explicación |
| --- | --- |
| `Imagen seleccionada` | Informa si el RAW tiene mochila, si hay ICC aplicado y qué archivo ICC se está usando. |
| `Perfiles ICC de sesión` | Muestra cuántos ICC se han registrado en el proyecto y cuál está activo. |
| Nota de monitor | Recuerda que el ICC de la imagen y el ICC del monitor son capas distintas: el monitor no modifica la imagen ni la mochila. |

#### Perfil ICC de la imagen

| Opción | Explicación |
| --- | --- |
| `Perfil ICC RGB estandar` | Usa un perfil ICC RGB estándar. Técnicamente son espacios RGB estándar definidos mediante ICC; ProPhoto RGB es el valor predeterminado. |
| `Espacio RGB estandar` | `sRGB`, `Adobe RGB` o `ProPhoto RGB`. Al cambiarlo queda aplicado a la imagen seleccionada. |
| `Perfiles ICC de la sesion` | Permite elegir un ICC generado o registrado en el proyecto. Si todavía no existe ninguno, la interfaz lo indica y mantiene ProPhoto RGB como opción segura. |
| `Perfil de sesion` | Lista de ICC de sesión. Al elegir uno queda activo en la imagen seleccionada si su estado QA lo permite. Los perfiles mostrados como `rechazado` piden confirmación antes de activarse. |
| `Generar perfil ICC` | Muestra el flujo de carta para crear un nuevo ICC de cámara/sesión. |
| `Activar seleccionado` | Activa el ICC seleccionado en la lista de sesión. |
| `Cargar ICC de camara...` | Permite elegir un ICC externo existente en el sistema y registrarlo para usarlo en el proyecto. |
| `Usar ICC generado` | Activa el último ICC generado con carta. |
| `Aplicar ICC a seleccion` | Escribe el ICC activo en las mochilas de las miniaturas seleccionadas. |
| `Aplicar ICC a sesion` | Aplica el ICC activo a todos los RAW de la sesión. |

#### Generar ICC con carta de color

| Opción | Explicación |
| --- | --- |
| `Carpeta de referencias colorimétricas` | Carpeta donde están las capturas RAW/DNG originales de carta. Si hay selección explícita, se usan esas imágenes. |
| `Referencias colorimétricas seleccionadas` | Indica cuántas capturas RAW/DNG de carta se usarán. |
| `Referencia de carta` | Selector de referencias incluidas y referencias personalizadas guardadas en la sesión. |
| `Importar JSON` | Copia una referencia externa validada a `00_configuraciones/references/`. |
| `Nueva personalizada` | Crea una referencia editable de sesión a partir de una plantilla. |
| `Editar tabla` | Abre el editor tabular Lab con muestras de color por parche. |
| `Validar` | Comprueba estructura, iluminante, observador y valores Lab. |
| `Referencia carta JSON` | Ruta del JSON seleccionado o generado para la carta. |
| `Perfil ICC de entrada` | Ruta de salida del ICC generado. |
| `Reporte perfil JSON` | Ruta automática del reporte técnico de perfil. Normalmente queda en `00_configuraciones/work/`. |
| `Directorio artefactos` | Directorio automático de overlays, mediciones, intermedios y cachés del perfilado. |
| `Receta calibrada` | Ruta automática de la receta resultante tras medir la carta. |
| `Tipo de carta` | `colorchecker24` o `it8`. Debe coincidir con la referencia JSON. |
| `Confianza mínima` | `0.00` a `1.00`. Umbral de aceptación de la detección automática. |
| `Permitir fallback` | Permite continuar con criterios alternativos si la detección automática no llega al umbral. Úsalo solo si revisarás QA. |
| `Formato ICC` | `.icc` o `.icm`. |
| `Tipo de perfil ICC` | `Lab cLUT (-al)`, `shaper+matrix (-as)`, `gamma+matrix (-ag)`, `matrix only (-am)` o `XYZ cLUT (-ax)`. El preset recomendado es `-al` con calidad Medium y `-u -R`; `-as` queda disponible como modelo compacto y `-ax` como opcion avanzada. |
| `Calidad colprof` | Low, Medium, High, Ultra. A mayor calidad, más coste de cálculo. |
| `Args extra colprof` | Argumentos avanzados para ArgyllCMS, por ejemplo `-D "Perfil Cámara Museo"`. El valor por defecto usa `-u -R` para evitar perfiles con gamut irrealmente libre. |
| `Cámara (opcional)` | Campo reservado de metadatos de perfil. En la interfaz actual se rellena automáticamente u opera oculto. |
| `Lente (opcional)` | Campo reservado de metadatos de perfil. En la interfaz actual se rellena automáticamente u opera oculto. |
| `Marcar en visor` | Inicia marcado manual de cuatro esquinas. El cursor cambia a cruz. |
| `Limpiar puntos` | Borra el marcado manual. |
| `Guardar detección` | Guarda JSON y overlay de una detección manual. Tras marcar las esquinas, las zonas centrales de lectura pueden moverse antes de guardar. |
| `Generar ICC con carta` | Ejecuta medición, ICC de entrada y reportes. |
| `Resultado JSON` | Salida técnica de la generación de perfil. |

### RAW Global

| Opción | Valores | Explicación |
| --- | --- | --- |
| `Receta YAML/JSON` | ruta | Archivo de receta base. |
| `Cargar receta` | acción | Carga una receta existente en los controles. |
| `Guardar receta` | acción | Guarda los criterios actuales como receta. |
| `Receta por defecto` | acción | Restaura la receta base. |
| `Motor RAW` | `LibRaw / rawpy` | Motor de revelado. Es el único motor disponible. |
| `Método` | DCB, DHT, AHD, AAHD, VNG, PPG, Lineal, AMaZE | Algoritmo de desentramado RAW. AMaZE solo está disponible si la build informa `DEMOSAIC_PACK_GPL3=True`. |
| `Interpolar verdes por separado (4 colores)` | activado/desactivado | Usa interpolación de cuatro colores cuando el backend y el método lo soportan. |
| `Borde` | `0` a `32` | Parámetro de calidad de borde disponible para métodos/backend compatibles. Si no aplica al método elegido, queda deshabilitado. |
| `Pasos de supresión de falso color` | `0` a `10` | Pasos de supresión de falso color disponibles para métodos/backend compatibles. Si no aplica al método elegido, queda deshabilitado. |
| Estado de opciones | texto | Informa qué opciones están disponibles para el método seleccionado. |
| `Modo` en `Puntos de negro RAW` | Metadata, Fijo, White level | Origen del punto negro RAW. |
| Valor de negro | `0` a `65535` | Valor usado cuando el modo negro es fijo. |

Este panel controla solo la lectura y el desentramado del RAW. El ICC de cámara
se decide en `Color / calibración`; la conversión al monitor se aplica solo para
visualizar. Exposición, color, contraste, ruido y nitidez pertenecen a sus
paneles específicos.

#### Perfiles RAW / exportación

| Opción | Explicación |
| --- | --- |
| `Perfil` | Perfil RAW/exportación guardado en la sesión o `Ajustes actuales`. |
| `Nombre` | Nombre del perfil que se guardará. |
| `Guardar` | Guarda los controles RAW actuales como perfil de sesión. |
| `Aplicar a controles` | Carga el perfil seleccionado en los controles RAW. |
| `Aplicar a selección` | Escribe esos ajustes RAW en las mochilas de las miniaturas seleccionadas. |
| `Copiar de imagen` | Copia los ajustes RAW de la imagen seleccionada. |
| `Pegar a imagen` | Pega los ajustes RAW copiados en la imagen seleccionada. |

Los cambios RAW se guardan también en tiempo real en la mochila del archivo
activo, aunque no guardes un perfil de sesión.

## 12. Configuración global

Las opciones globales están en `Configuración > Configuración global...`.

![Configuración global](assets/screenshots/probraw-configuracion-global.png)

### General

| Opción | Explicación |
| --- | --- |
| `Idioma de la interfaz` | `Sistema`, `Español` o `English`. El cambio se aplica al reiniciar ProbRAW. |

### Firma / C2PA

| Opción | Explicación |
| --- | --- |
| `Clave privada Proof (Ed25519)` | Clave privada local para firmar ProbRAW Proof. |
| `Clave pública Proof` | Clave pública que permite verificar la firma. |
| `Frase clave Proof` | Frase de desbloqueo. No se guarda. |
| `Firmante Proof` | Nombre del firmante local en los sidecars Proof. |
| `Generar identidad local Proof` | Crea una identidad local para firmar TIFF finales. |
| `Certificado C2PA opcional (PEM)` | Certificado externo C2PA/CAI, si existe. |
| `Clave privada C2PA opcional` | Clave privada asociada al certificado C2PA. |
| `Frase clave C2PA` | Frase de desbloqueo. No se guarda. |
| `Algoritmo C2PA` | `ps256`, `ps384`, `es256` o `es384`. |
| `Servidor TSA` | URL de sellado temporal para C2PA. |
| `Firmante C2PA` | Nombre de firmante del manifiesto C2PA. |

ProbRAW Proof es la firma autónoma obligatoria del proyecto. C2PA/CAI es una
capa interoperable que se usa automáticamente con identidad local de laboratorio
si no hay certificado externo.

### Preview / monitor

| Opción | Explicación |
| --- | --- |
| Política de preview RAW | Automática: rápida al navegar y máxima calidad en comparar/1:1/precisión. No es editable. |
| `Resolución de preview` | Automática. Usa fuente completa cuando es necesario. |
| `Gestión ICC del monitor del sistema` | Usa el perfil ICC configurado para el monitor en el sistema operativo. |
| `Perfil ICC monitor` | Ruta manual de perfil de monitor si se necesita sobrescribir la detección. |
| `Detectar` | Busca el perfil de monitor del sistema. |
| Política de PNG | `Guardar preview PNG` siempre pregunta destino con `Guardar como...`. |
| `Limpiar caché` | Elimina cachés de previews y miniaturas de usuario y sesión. Se regeneran bajo demanda. |

Detección de monitor:

- macOS: ColorSync;
- Linux/BSD: `colord` o `_ICC_PROFILE`;
- Windows: WCS/ICM.

Si no se encuentra perfil, ProbRAW usa sRGB como fallback visual.

Aspectos relevantes:

- el perfil ICC del monitor debe estar bien asignado en el sistema operativo o
  seleccionado manualmente en ProbRAW;
- la conversión al monitor solo cambia la apariencia en pantalla, no los
  valores usados por el histograma colorimétrico;
- un monitor mal perfilado puede hacer que la imagen se vea mal aunque el ICC de
  entrada y el histograma sean coherentes;
- para revisar color, genera o activa primero el ICC de entrada de la sesión y
  confirma que `Gestión ICC del monitor del sistema` está activa.

## 13. Metadatos, Proof y trazabilidad

ProbRAW Proof vincula RAW, TIFF, receta, perfil, ajustes, hashes y clave pública.
El sidecar `*.probraw.proof.json` permite auditar que el TIFF corresponde a un
RAW y a una receta concreta. C2PA/CAI añade una capa compatible con herramientas
externas y listas de confianza cuando se dispone de certificado reconocido.

En una exportación completa puedes encontrar:

- TIFF final 16-bit;
- TIFF lineal de auditoría en `_linear_audit/`;
- `RAW.probraw.json`;
- `*.probraw.proof.json`;
- `batch_manifest.json`;
- manifiesto C2PA si está configurado.

## 14. Rendimiento y caché

ProbRAW separa navegación, preview y render final:

- las miniaturas usan caché rápida;
- los RAW usan primero preview embebido cuando existe;
- la revisión crítica puede cargar fuente 1:1;
- el render final usa el pipeline auditado.

Buenas prácticas:

- usa `Precache carpeta` antes de revisar muchos RAW;
- usa `Precache 1:1` antes de revisar nitidez o detalle crítico;
- activa comparar/1:1 solo cuando haga falta;
- no regeneres perfiles si solo cambias ajustes finales;
- conserva la estructura de sesión completa para que caché, sidecars y rutas
  relativas sigan siendo transportables.

## 15. Problemas frecuentes

### No veo AMaZE disponible

AMaZE solo aparece como disponible si la instalación incluye el backend GPL3 de
LibRaw/rawpy. Si no está disponible, usa DCB u otro algoritmo soportado. ProbRAW
lo registra en receta y reportes.

### La detección de carta falla

Usa una captura con la carta completa, sin reflejos, sin parches saturados y con
enfoque suficiente. Si falla la detección automática, usa `Marcar en visor`,
marca las cuatro esquinas, ajusta las zonas centrales de lectura para que no
toquen bordes ni defectos locales y guarda la detección.

### El marcado manual parece moverse

Los puntos se guardan en coordenadas del preview activo y se transforman al
archivo completo al guardar la detección. Si cambias de archivo, zoom extremo o
recarga de preview, revisa el overlay antes de guardar.

### El perfil produce dominante o clipping

Comprueba que carta, referencia JSON, cámara, óptica, iluminante y receta
coinciden. Revisa el reporte QA y no uses TIFF ni derivados como cartas de
entrada: el perfil ICC de cámara/sesión debe generarse desde RAW/DNG original.
Si el reporte menciona saturación en parches neutros, revisa si la receta activa
venía de un perfil anterior o tenía exposición/WB aplicados. ProbRAW neutraliza
esos campos para nuevos perfiles, pero los perfiles antiguos marcados como
`rechazado` deben mantenerse solo para diagnóstico.

### No hay carta de color

Usa el flujo sin carta: perfil ICC RGB estándar, ajustes paramétricos por
mochila y, si conviene, perfiles de sesión para reutilizarlos. Es trazable, pero
no sustituye la precisión de una referencia medida.

### El cuentagotas Lab muestra valores orientativos

Comprueba el estado ICC de la imagen. Para que el Lab de un píxel y sus DeltaE
sean mediciones colorimétricas rigurosas, la imagen debe tener asignado un ICC
generado por ProbRAW para la misma cámara, receta e iluminación. Con perfiles
genéricos, ProbRAW puede calcular Lab matemáticamente dentro de ese espacio, pero
lo advertirá como lectura orientativa.

### Las muestras no coinciden con el píxel esperado

Activa `Cuentagotas Lab`, revisa la lupa de píxeles y usa una matriz adecuada al
material. Una matriz `1x1` mide un píxel exacto; matrices mayores promedian una
zona y son más robustas para tintas, papeles o superficies con textura. Si la
imagen no está a tamaño real, ProbRAW solicita cargar la fuente completa antes de
guardar la muestra. Si hay ajustes de detalle pendientes a tamaño real, espera a
que termine el recálculo exacto antes de interpretar el valor Lab.

### La imagen ya tenía un TIFF exportado

ProbRAW no sobrescribe salidas existentes. Crea sufijos `_v002`, `_v003`, etc.

## 16. Glosario

| Término | Definición |
| --- | --- |
| AMaZE | Algoritmo de demosaico de alta calidad disponible solo con soporte GPL3 en LibRaw/rawpy. |
| ArgyllCMS | Conjunto de herramientas usado para crear perfiles ICC, especialmente `colprof`. |
| C2PA/CAI | Estándar de procedencia y autenticidad interoperable para contenido digital. |
| Caché | Datos temporales de previews, miniaturas o demosaico que aceleran trabajo posterior. |
| Carta de color | Referencia física con parches de color conocidos usada para medir desviaciones. |
| Clipping | Recorte de sombras o luces cuando la señal queda en negro o blanco sin detalle. |
| Conjunto de muestras | Grupo de tomas Lab asociadas a una misma tinta, zona o material; se compara mediante media, dispersión, DeltaE y gamut propio. |
| DCP | Perfil de cámara usado por algunos reveladores RAW. ProbRAW prioriza un flujo ICC reproducible. |
| DeltaE 2000 | Métrica de diferencia perceptual entre colores medidos y de referencia. |
| Demosaico | Interpolación que convierte el mosaico Bayer/X-Trans del RAW en RGB. |
| Gamut de muestras | Envolvente visual de las tomas de un conjunto en Lab a*b*. Sirve para comparar variación interna y similitud frente a otro conjunto. |
| ICC | Perfil de color que describe cómo interpretar o convertir valores de color. |
| ICC de entrada | Perfil que describe el RGB de cámara/sesión generado desde carta. |
| ICC estándar | Perfil conocido como sRGB, Adobe RGB o ProPhoto RGB. |
| Iluminante | Descripción del punto blanco o fuente de luz de referencia. |
| Lab | Espacio CIE L*a*b* usado como referencia perceptual. En ProbRAW el Lab de píxel es riguroso cuando el RGB de la imagen está descrito por un ICC de sesión válido. |
| Mochila | Sidecar `RAW.probraw.json` con ajustes asignados al RAW. |
| Perfil ICC de sesión | ICC generado o registrado dentro del proyecto, normalmente a partir de una carta de color. |
| Perfil de ajuste | Perfil guardado de una categoría concreta: ICC, color/contraste, nitidez o RAW/exportación. |
| Perfil del monitor | ICC usado solo para mostrar correctamente en pantalla. |
| Preview | Previsualización de trabajo. No sustituye al render final auditado. |
| Proof | Firma autónoma de ProbRAW que vincula RAW, TIFF, receta, perfil y hashes. |
| QA | Control de calidad del perfil, detección y colorimetría. |
| RAW Global | Panel de lectura RAW, desentramado, opciones del algoritmo y punto negro RAW. |
| Receta | Archivo YAML/JSON con parámetros de revelado y criterios técnicos. |
| Sidecar | Archivo auxiliar junto a una imagen que guarda metadatos o ajustes. |
| TIFF lineal de auditoría | TIFF intermedio lineal usado para verificación técnica. |

## 17. Documentación relacionada

- [Metodología de revelado RAW y gestión ICC](METODOLOGIA_COLOR_RAW.md)
- [ProbRAW Proof](PROBRAW_PROOF.md)
- [C2PA/CAI](C2PA_CAI.md)
- [Integración LibRaw + ArgyllCMS](INTEGRACION_LIBRAW_ARGYLL.md)
- [Publicación de instaladores](RELEASE_INSTALLERS.md)
- [Licencias de terceros](THIRD_PARTY_LICENSES.md)
- [Changelog](../CHANGELOG.md)
