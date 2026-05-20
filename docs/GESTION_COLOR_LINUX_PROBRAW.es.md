# Gestión de Color del Sistema en ProbRAW

## Objetivo

Este documento recoge las mejoras de implementacion derivadas del documento
local:

`/home/alejandro/Documentos/Notas/Notas MD/FOTOGRAFÍA/Tecnología de imagen digital/Procesado digital de imágenes/gestión de color en linux.md`

La conclusion principal es que ProbRAW no debe tratar el color como una propiedad
implicita del archivo, del monitor o de Qt, sino como una cadena explicita de
estados y transformaciones:

```text
entrada -> espacio de trabajo -> preview/display -> exportacion -> prueba/soft-proof
```

El perfil de monitor nunca debe actuar como espacio de trabajo ni modificar
TIFF, hashes, manifiestos, Proof o C2PA.

## Estado Actual de ProbRAW

ProbRAW ya tiene una base ICC solida:

- separa perfil ICC de entrada, perfil generico estandar y perfil ICC de
  monitor;
- genera ICC de entrada de sesion con ArgyllCMS;
- usa ArgyllCMS `cctiff` para conversiones ICC de exportacion;
- usa Pillow/ImageCms LittleCMS para preview gestionada hacia monitor y para la
  previsualizacion ICC de perfil;
- evita exportar RGB de camara sin perfil;
- registra hashes de RAW, TIFF, receta, ajustes e ICC usado en Proof/manifiestos;
- limita la gestion ICC del monitor a la visualizacion.

La implementacion, sin embargo, aun puede mejorar en integracion con Linux
moderno, Wayland/KWin, colord, metadatos de color no ICC, trazabilidad de
entorno y pruebas de robustez con perfiles externos.

## Contrato Multiplataforma

ProbRAW debe ser portable entre Windows, Linux y macOS. La regla de arquitectura
es separar motor de transformacion, proveedor del perfil de pantalla y politica
de superficie:

```text
Transformacion ICC de preview: LittleCMS2 via Pillow ImageCms
Creacion de ICC de sesion:     ArgyllCMS colprof
Validacion de ICC generado:    ArgyllCMS xicclu/icclu
Perfil de pantalla Windows:    WCS/ICM, GetICMProfileW
Perfil de pantalla macOS:      ColorSync/CoreGraphics
Perfil de pantalla Linux:      colord; _ICC_PROFILE en X11 como fallback
Wayland/KWin:                  compositor activo; evitar doble conversion
```

Esto implica:

- no condicionar la preview ICC a herramientas externas de ArgyllCMS;
- no tratar el perfil de monitor como espacio de trabajo;
- no asumir que Windows, macOS y Linux exponen el perfil activo de la misma
  manera;
- registrar en `probraw check-color-environment` que proveedor de perfil,
  motor CMM y politica de superficie se han usado;
- mantener seleccion manual de ICC de monitor como escape portable cuando el
  sistema no expone un perfil fiable.

## Mejoras ya Incorporadas en la Rama Actual

El analisis ya se ha convertido en cambios concretos en estas areas.

### Perfiles Estandar del Sistema

`src/probraw/profile/generic.py` busca perfiles estandar RGB en ubicaciones
habituales de Linux, macOS/Homebrew y entornos empaquetados, no solo en una ruta
fija:

- `PROBRAW_STANDARD_ICC_DIR`;
- rutas de referencia de ArgyllCMS, incluida `/usr/share/argyllcms/ref`;
- `$XDG_DATA_HOME/color/icc` y `$XDG_DATA_HOME/icc`;
- entradas de `$XDG_DATA_DIRS`, por ejemplo `/usr/share/color/icc`;
- `/usr/share/color/icc/colord`;
- `/usr/share/icc`;
- `/usr/local/share/color/icc`;
- `/usr/local/share/icc`;
- `/opt/homebrew/share/color/icc`;
- `/opt/homebrew/share/argyllcms/ref`;
- `/var/lib/colord/icc`;
- `~/.local/share/color/icc`.

Tambien busca de forma recursiva por nombre de archivo y por descripcion interna
ICC, lo que permite usar perfiles instalados por el sistema aunque no tengan el
nombre historico esperado.

### Compatibilidad Arch/CachyOS

En Arch/CachyOS los perfiles de referencia de ArgyllCMS pueden vivir en:

```text
/usr/share/argyllcms/ref
```

ProbRAW ahora contempla esa ruta tanto para perfiles genericos estandar como
para conversiones de exportacion. Esto evita el fallo en el que ProPhoto RGB no
se encontraba aunque ArgyllCMS estuviera instalado correctamente.

### Seleccion Segura de ProPhoto RGB

ProPhoto RGB tiene variantes lineales y no lineales. ProbRAW acepta perfiles con
descripcion compatible con ProPhoto/ROMM RGB, pero rechaza descripciones que
incluyan `Linear` cuando se necesita el perfil generico ProPhoto RGB de gamma
1.8. Esto evita seleccionar accidentalmente `ProPhotoLin.icm`.

### Validacion de Herramientas y Perfiles

`probraw check-tools --strict` comprueba ahora que esten disponibles:

- `colprof`;
- `xicclu` o `icclu`;
- `cctiff`;
- `exiftool`;
- perfiles estandar reales para sRGB, Adobe RGB (1998) y ProPhoto RGB.

La ausencia de un perfil estandar requerido se considera fallo de entorno, no un
detalle menor que pueda degradar silenciosamente la gestion de color.

### Dialogos ICC

Los dialogos de seleccion de perfiles ICC en la GUI parten de ubicaciones del
sistema donde es probable encontrar perfiles reales. Esto reduce el uso de
perfiles copiados a mano y favorece perfiles instalados o asociados por el
sistema.

## Mejoras P0: Corregir Ambiguedades de Color de Entrada

Estas mejoras afectan directamente a la interpretacion objetiva de pixeles y
deben tener prioridad alta.

### Crear un Modelo Interno de Estado de Color

ProbRAW necesita una estructura explicita para describir el color de cada
entrada y cada transformacion. Modelo minimo recomendado:

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

Este estado debe vivir fuera de los arrays NumPy. Los pixeles no se deben
considerar colorimetricamente interpretables sin ese contexto.

### Leer y Preservar ICC Embebido en Imagenes No RAW

`core.utils.read_image()` convierte actualmente con Pillow/tifffile hacia RGB
float para muchos formatos. El siguiente paso es devolver, ademas del array, los
bytes ICC originales y su hash.

Formatos prioritarios:

- JPEG: marcadores APP2 ICC;
- TIFF: tag ICC 34675;
- PNG: chunk iCCP;
- WebP/AVIF/HEIF si se incorporan como entrada soportada.

El ICC embebido debe conservarse como bytes exactos, aunque despues se convierta
a otro espacio para procesar o previsualizar.

### Detectar Metadatos de Color No ICC

No todos los archivos declaran color mediante ICC. ProbRAW debe detectar y
registrar:

- PNG `gAMA`, `cHRM`, `sRGB`, `iCCP`;
- EXIF `ColorSpace`;
- TIFF/EXIF `ProfileName` cuando exista;
- CICP/nclx en formatos modernos;
- matriz YCbCr, rango completo/limitado y chroma siting si se incorporan flujos
  de video o imagenes codificadas como YCbCr.

La politica debe definir prioridad cuando coexistan varias declaraciones.

### Politica de Imagenes Sin Perfil

Una imagen sin perfil no debe convertirse silenciosamente. Politica recomendada:

- conservar estado original `untagged`;
- permitir preview bajo asuncion explicita, normalmente sRGB;
- registrar que la asuncion es solo de preview;
- bloquear mediciones colorimetricas absolutas si el espacio fuente es
  desconocido;
- permitir asignacion manual de perfil;
- distinguir en UI y sidecars entre "asignar perfil" y "convertir a perfil".

### No Confundir Asignacion y Conversion

La documentacion de Qt y la practica ICC distinguen:

```text
asignar perfil  -> cambia la interpretacion, no cambia los valores RGB
convertir perfil -> transforma los valores RGB
```

ProbRAW ya aplica esta separacion en RAW/exportacion. Debe extenderla a toda
entrada raster no RAW, previews, miniaturas y exportaciones derivadas.

## Mejoras P1: Integracion Linux/KDE/Wayland

Estas tareas mejoran universalidad y reducen diferencias entre sistemas.

### Integrar Mejor colord para Perfiles de Dispositivo

La busqueda por rutas sirve para perfiles estandar, pero el perfil activo de un
monitor debe obtenerse preferiblemente via colord o el toolkit. Mejoras
recomendadas:

- guardar `device_id`, `profile_id`, ruta y SHA-256 del perfil activo;
- escuchar cambios de perfil/dispositivo cuando sea posible;
- distinguir perfiles de monitor, camara, impresora y perfiles genericos RGB;
- no asumir que el primer ICC encontrado en disco es el perfil activo real.

`display_color.py` ya consulta `colormgr`; debe evolucionar hacia un registro
mas rico del dispositivo y del origen de la decision.

### Registrar Entorno Grafico

`probraw check-color-environment` debe registrar una auditoria de color
multiplataforma:

- proveedor de perfil de pantalla: Windows WCS/ICM, macOS ColorSync o
  Linux colord/X11/Wayland;
- CMM usado para preview: LittleCMS2 via Pillow `ImageCms`;
- motor de creacion/validacion ICC: ArgyllCMS `colprof` y `xicclu/icclu`;
- `XDG_SESSION_TYPE`, `WAYLAND_DISPLAY` y `DISPLAY` en Linux;
- escritorio/compositor (`KDE`, `KWin`, `GNOME`, X11, XWayland) en Linux;
- versiones de Qt/PySide, KWin, Plasma, `wayland-protocols`, colord, lcms2,
  ArgyllCMS y Pillow cuando apliquen;
- salida fisica activa, EDID si es accesible, escala, HDR, VRR y profundidad de
  color si el sistema lo expone;
- protocolos Wayland disponibles relacionados con color/HDR en Linux;
- perfil de monitor activo y SHA-256.

`check-tools --strict` valida dependencias operativas. `check-color-environment`
no sustituye esa validacion: documenta como se ha adaptado ProbRAW al sistema
grafico real.

### Politica Wayland/KWin

En Wayland el compositor forma parte activa del pipeline. ProbRAW debe mantener
una decision explicita por plataforma:

- modo actual estable: cuando existe un ICC de monitor activo, ProbRAW convierte
  pixeles de preview con LittleCMS hacia ese perfil de monitor y entrega la
  imagen Qt como RGB de dispositivo, sin etiqueta `QColorSpace` adicional;
- fallback explicito: cuando no hay ICC de monitor disponible, la preview queda
  como sRGB visual y la imagen Qt se etiqueta como sRGB;
- modo experimental delegado al compositor: etiquetar la superficie y delegar la
  conversion final en el compositor solo cuando exista una matriz Qt/KWin/Wayland
  validada;
- el ICC de monitor nunca se usa para TIFF/exportacion, que siguen ligados al
  ICC de entrada seleccionado y a la politica de exportacion;
- no usar capturas de pantalla como prueba colorimetrica concluyente.

La variable `PROBRAW_PREVIEW_SYSTEM_DISPLAY_COLOR_MANAGEMENT` debe considerarse
un modo de compatibilidad/validacion hasta que exista una matriz de pruebas
Wayland/KWin documentada.

### Multi-monitor

El perfil de display puede cambiar al mover la ventana entre monitores. ProbRAW
debe:

- detectar pantalla activa del visor;
- invalidar caches/LUTs de display al cambiar de salida;
- recalcular preview de pantalla cuando cambie el ICC de monitor;
- registrar que perfil de salida se uso para cada visualizacion o prueba.

### Seguridad de Perfiles ICC Externos

Los ICC cargados desde imagenes o elegidos por el usuario son entrada no
confiable. Requisitos:

- limite de tamano, por ejemplo 32 MiB para perfiles destinados a Wayland;
- validacion de tamano minimo, firma y apertura con LittleCMS;
- errores explicitos ante perfil corrupto;
- hash SHA-256 antes de usarlo;
- cache de perfiles abiertos y transformaciones por hash/mtime/tamano;
- tests con perfiles malformados.

## Mejoras P1: Transformaciones y Soft-proofing

### Hacer Explicitos Intent, Flags y Version CMM

ProbRAW usa intent relativo colorimetrico en preview mediante LittleCMS2 y
`cctiff -ir` en conversiones ArgyllCMS de exportacion derivada. Debe
registrarse de forma uniforme:

- CMM usado (`lcms2` via Pillow/ImageCms para preview, `argyllcms` via `cctiff`
  para exportacion derivada mientras siga vigente esa ruta);
- version del CMM;
- rendering intent;
- black point compensation;
- perfiles origen/destino/proof;
- formato de pixel de entrada/salida;
- hash de cada perfil.

La clave de cache de transformaciones debe incluir esos campos para evitar
reutilizar una LUT bajo parametros distintos.

### Separar Display Transform y Soft-proof

Soft-proof no es "otra preview". Es una transformacion explicita:

```text
source/working -> proof profile -> display profile
```

Debe tener controles y registro propios:

- perfil de salida simulado;
- intent de prueba;
- intent de conversion final;
- compensacion de punto negro;
- aviso de fuera de gamut;
- separacion total frente a la exportacion real.

El diagnostico Gamut 3D actual ayuda a comparar perfiles, pero no sustituye un
pipeline de soft-proof reproducible.

## Mejoras P2: Formatos, HDR y Empaquetado

### Build Optimizada para CachyOS

La build nativa de CachyOS/Arch debe construirse con el empaquetado Arch:

```bash
PROBRAW_ARCH_PKGREL=3 PROBRAW_ARCH_NATIVE=1 PROBRAW_BUILD_AMAZE=1 packaging/arch/build_pkg.sh
```

Opciones relevantes:

- `PROBRAW_ARCH_PKGREL`: revision del paquete Arch. Permite publicar nuevas
  compilaciones de la misma version upstream sin alterar `src/probraw/version.py`.
- `PROBRAW_ARCH_NATIVE=1`: compila extensiones C/C++ con `-O3 -march=native
  -mtune=native`. Es lo adecuado para una build local optimizada, pero no para
  un paquete que se vaya a distribuir a equipos con otra CPU.
- `PROBRAW_BUILD_AMAZE=1`: compila e instala `rawpy-demosaic` con soporte AMaZE.
- `PROBRAW_ARCH_SYNCDEPS=1`: permite a `makepkg` instalar dependencias con
  pacman si el entorno lo permite.
- `PROBRAW_MAKEPKG_ARGS="--cleanbuild"`: fuerza una reconstruccion limpia.

La build instala ProbRAW en `/opt/probraw/venv`, expone solo los lanzadores
`probraw` y `probraw-ui`, declara conflicto/reemplazo de `iccraw`/`nexoraw` y
registra metadatos de la wheel `rawpy-demosaic` usada para AMaZE en
`/usr/share/doc/probraw/third_party/rawpy-demosaic/`.

Para una instalacion limpia local sin borrar datos de usuario:

```bash
sudo pacman -R --noconfirm probraw || true
sudo rm -rf /opt/probraw
sudo rm -f /usr/bin/probraw /usr/bin/probraw-ui /usr/bin/iccraw /usr/bin/iccraw-ui
sudo pacman -U --noconfirm build/arch/probraw-<version>-<pkgrel>-x86_64.pkg.tar.zst
```

Validacion despues de instalar desde el paquete real:

```bash
pacman -Qkk probraw
bash /usr/share/doc/probraw/validate_cachyos_install.sh
probraw check-tools --strict
probraw check-color-environment --out color_environment.json
```

La build debe demostrar que encuentra perfiles estandar del sistema, que
LittleCMS2 esta disponible para preview y que ArgyllCMS esta disponible para
crear/validar perfiles ICC.

### Compatibilidad rawpy-demosaic en CachyOS Actual

El script `scripts/build_rawpy_demosaic_wheel.py` aplica parches de build para
mantener `rawpy-demosaic` utilizable en toolchains actuales:

- fuerza una politica CMake minima compatible con fuentes heredadas de LibRaw;
- usa `Cython>=3.1` y `numpy` para soportar Python moderno;
- sustituye asignaciones C-level de `ndarr.base` por `np.set_array_base`, evitando
  errores de compilacion con Cython reciente.

Estos cambios son de empaquetado/build; no alteran la politica de color de
ProbRAW ni la semantica de AMaZE.

### HDR y Wide-gamut

ProbRAW debe declarar explicitamente que la preview ICC actual es SDR. No se debe
tratar HDR como "un ICC mas". Para HDR haria falta modelar:

- EOTF (`PQ`, `HLG`, gamma, sRGB);
- primarios;
- luminancia de referencia y maxima;
- metadatos HDR;
- tone mapping;
- soporte real de Qt/Wayland/KWin.

Hasta entonces, cualquier imagen HDR o CICP debe quedar marcada como flujo no
gestionado completamente.

### Empaquetado Linux

Los paquetes nativos, Flatpak/AppImage o contenedores pueden ver perfiles y
D-Bus de forma distinta. Pruebas recomendadas:

- paquete nativo Arch/CachyOS;
- paquete Debian/Ubuntu;
- acceso a `/usr/share/argyllcms/ref`;
- acceso a `/usr/share/color/icc`, `/usr/share/color/icc/colord` y
  `/var/lib/colord/icc`;
- acceso D-Bus a colord;
- `check-tools --strict` dentro de la aplicacion instalada;
- smoke GUI con preview y miniaturas tras instalar.

## Corpus de Pruebas Recomendado

### Imagenes

- sRGB ICC v2 y v4;
- Adobe RGB v2/v4;
- ProPhoto RGB gamma 1.8 y ProPhoto lineal;
- Display P3;
- Rec.2020;
- TIFF con ICC;
- JPEG con ICC APP2;
- PNG con `gAMA/cHRM/sRGB` sin ICC;
- PNG con `iCCP`;
- imagen sin perfil;
- imagen gris con perfil;
- imagen con alfa recto y premultiplicado;
- CMYK si se decide soportarlo;
- HDR/PQ/HLG solo si se abre una ruta HDR real.

### Perfiles

- matrix/TRC;
- LUT/cLUT;
- perfiles ICC v2 y v4;
- DisplayClass y InputClass;
- perfil truncado;
- perfil enorme;
- perfil con tags inconsistentes;
- perfil con clase inesperada.

### Entorno Grafico

- CachyOS KDE Plasma Wayland/KWin;
- Arch KDE Wayland/KWin;
- Debian KDE Wayland/KWin;
- KDE X11;
- GNOME Wayland si se soporta;
- XWayland;
- multi-monitor con perfiles distintos;
- HDR on/off;
- Night Light on/off;
- escalado fraccional on/off.

## Criterios de Aceptacion

Una mejora de gestion de color en ProbRAW deberia considerarse completa solo si:

- no introduce conversiones silenciosas;
- documenta si una operacion asigna o convierte;
- conserva bytes ICC originales cuando proceden del archivo;
- calcula SHA-256 de perfiles usados;
- registra CMM, version, intent y flags;
- mantiene el perfil de monitor fuera de TIFF/exportacion;
- falla de forma explicita si falta un perfil requerido;
- incluye tests con perfiles reales del sistema y fixtures controlados;
- se verifica en la aplicacion instalada, no solo en el entorno editable.

## Areas de Codigo a Evolucionar

- `src/probraw/core/utils.py`: separar lectura de pixeles y lectura de estado de
  color/metadata.
- `src/probraw/raw/preview.py`: preservar el perfil ICC y la declaracion de
  color de previews embebidas cuando se usen.
- `src/probraw/display_color.py`: enriquecer deteccion colord/Wayland y estado
  multi-monitor.
- `src/probraw/profile/generic.py`: mantener busqueda de perfiles del sistema y
  ampliar validacion ICC.
- `src/probraw/profile/export.py`: registrar intent/flags/CMM y origen completo
  de perfiles estandar copiados a la sesion.
- `src/probraw/reporting.py`: capturar entorno grafico y colorimetrico de
  Windows, macOS y Linux, incluyendo el proveedor de perfil de pantalla de cada
  sistema.
- `src/probraw/provenance/probraw_proof.py`: incluir origen, ruta fuente,
  descripcion y SHA-256 de perfiles de entrada/salida/proof.
- `tests/`: añadir fixtures de ICC, imagenes sin perfil, PNG color chunks,
  JPEG/TIFF con ICC y simulaciones de colord/Wayland.
