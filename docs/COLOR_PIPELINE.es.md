# Pipeline de Color

_English version: [COLOR_PIPELINE.md](COLOR_PIPELINE.md)_

## Estado Operativo

ProbRAW 0.3.10 implementa el flujo ICC principal y la interfaz de trabajo por
sesión. La aplicación es apta para pruebas controladas y validación de release,
pero todavía no debe presentarse como sistema certificado de producción
científica/forense.

La metodología completa se describe en
[Metodología de revelado RAW y gestión ICC](METODOLOGIA_COLOR_RAW.es.md).
La integracion especifica con perfiles del sistema, LittleCMS2, WCS/ICM,
ColorSync, colord, KDE/Wayland y validacion de entorno se documenta en
[Gestión de Color del Sistema en ProbRAW](GESTION_COLOR_LINUX_PROBRAW.es.md).

## Principio de Diseño

El pipeline separa:

1. revelado RAW reproducible;
2. perfil de ajuste paramétrico;
3. perfil ICC de entrada de la imagen;
4. perfil ICC de monitor solo para visualización;
5. auditoría mediante mochilas, manifiestos, Proof y C2PA opcional.

ProbRAW asigna perfiles de entrada a las imagenes. Esos perfiles de entrada son
perfiles ICC de sesion/camara creados con referencias colorimetricas, o perfiles
ICC genericos usados como fallback explicito cuando no existe referencia de
sesion. Los valores RGB generados desde un RAW son relativos al dispositivo o al
espacio de revelado; sin una etiqueta ICC de entrada no identifican de forma
objetiva a que color corresponde cada triplete RGB. La invencion de perfiles
adicionales y las conversiones implicitas a espacios ajenos no forman parte del
analisis objetivo.

El analisis Lab por cuentagotas sigue el mismo criterio. ProbRAW puede convertir
un RGB de imagen a Lab cuando existe un ICC asignado, pero la lectura solo es una
medicion colorimetrica rigurosa si ese ICC es un perfil de sesion generado por
ProbRAW para la misma camara, receta e iluminante. Con ICC genericos, el Lab y
DeltaE son diagnosticos orientativos del espacio asignado.

DCP no forma parte del pipeline activo de la serie 0.3.

## Modo Científico (`profiling_mode`)

Objetivo: neutralidad y reproducibilidad, no apariencia creativa.

Reglas:

1. sin sharpen creativo durante medición de carta;
2. sin denoise agresivo durante medición de carta;
3. sin curvas tonales artísticas;
4. balance de blancos fijo o explícito;
5. señal lineal para perfilado;
6. geometría de carta reutilizable entre pasadas.

## Fases

1. `raw-info`: lectura de metadatos técnicos.
2. `develop`: revelado base controlado con LibRaw/rawpy.
3. `detect-chart`: detección de carta, homografía y parches.
4. `sample-chart`: medición robusta por parche.
5. `build-develop-profile`: neutralidad, densidad y EV desde la fila neutra.
6. Receta calibrada: WB fijo, EV limitado por preservación de altas luces,
   señal lineal y sin procesos creativos.
7. Segunda medición de carta con la misma geometría y receta calibrada.
8. `build-profile`: ArgyllCMS (`colprof`) genera el ICC de entrada.
9. `validate-profile`: validación DeltaE 76/2000 del ICC real.
10. `batch-develop`: revelado de lote con perfil de ajuste e ICC asignado.

Las referencias de carta personalizadas se guardan en
`00_configuraciones/references/`. Cada ejecución avanzada de perfilado deja sus
artefactos en `00_configuraciones/profile_runs/`, y los ICC resultantes quedan
registrados como perfiles de sesión activables.

## Invariantes Críticas

1. La receta ejecutada debe coincidir con la receta declarada.
2. El TIFF de auditoría lineal debe escribirse antes de curvas tonales o
   operaciones de codificacion/exportacion.
3. La gestión ICC separa asignación de perfil de entrada y visualización en
   monitor; el análisis no debe inventar perfiles adicionales.
4. La validación comprueba el ICC real generado, no solo matrices auxiliares.
5. El fallback de detección de carta no genera perfiles automáticamente sin modo
   explícito o revisión.
6. La geometría de carta de la pasada base puede reutilizarse en la pasada
   calibrada.
7. El ICC no debe compensar exposición/densidad básica si la carta permite
   construir antes una receta calibrada.
8. Con carta, el TIFF maestro conserva RGB lineal de cámara/sesión e incrusta el
   ICC de entrada.
9. Sin carta, la imagen recibe igualmente un perfil ICC generico real de entrada
   que da significado colorimetrico a los valores RGB; no es un perfil
   alternativo inventado.
10. La visualización en pantalla usa solo la conversion desde el ICC de entrada
    activo hacia el perfil ICC del monitor configurado.
11. El histograma y el overlay de clipping de la GUI se calculan sobre la señal
    colorimétrica de preview antes de aplicar el ICC del monitor.
12. El diagnostico Gamut 3D/Lab 2D es una comparacion visual de perfiles; no
    modifica recetas, pixeles, perfiles activos ni manifiestos.
13. Ninguna preview ni imagen gestionada por la GUI puede quedar sin perfil de
    entrada: debe existir un ICC de sesion/imagen o un perfil generico estandar
    real que de significado colorimetrico a los valores RGB.
14. El cuentagotas Lab y las comparaciones de muestras deben usar pixeles reales
    de la imagen cargada a resolucion completa; no se aceptan medidas
    colorimetricas desde miniaturas o previews reducidas.
15. Las muestras se guardan por imagen en la mochila RAW y se comparan por
    conjuntos. No existe una referencia primaria dentro de un conjunto; la
    referencia comparativa es el conjunto de referencia activo.

## Contrato de Color para Pantalla

Esta regla no es negociable en ProbRAW:

- El perfil de imagen/dispositivo, sea especifico de sesion o generico
  estandar, nunca se convierte a sRGB para visualizar en pantalla.
- La visualizacion gestionada convierte directamente desde el ICC fuente activo
  al ICC del monitor configurado por el sistema operativo o elegido
  explicitamente por el usuario, y entrega despues la preview ya convertida a Qt
  como RGB de dispositivo.
- Los RGB de la imagen solo tienen significado colorimetrico objetivo cuando
  estan etiquetados por su ICC de entrada.
- ProbRAW no inventa perfiles adicionales para el analisis objetivo de imagen.
  Cualquier derivado exportado debe quedar fuera de preview, histograma, MTF,
  muestreo y QA de perfil.
- sRGB puede aparecer como ICC generico de entrada si se elige explicitamente,
  como curva de codificacion explicita de receta (`tone_curve: srgb`) o como
  senal interna de diagnostico para histogramas/comprobaciones de paridad. No
  debe sustituir al ICC de entrada de la imagen ni al ICC de monitor en la
  visualizacion gestionada.
- Si falta el ICC del monitor o esta roto, es un problema de configuracion de
  pantalla. ProbRAW puede usar fallback visual sRGB solo de forma explicita y
  reportada, sin sustituir el ICC de entrada ni convertir datos de analisis.

## Gestión de Color del Monitor

El perfil ICC de monitor no participa en el revelado, en el TIFF maestro ni en la
exportación. Solo corrige la representación visual de previews y miniaturas.

Detección:

- Windows: WCS/ICM.
- macOS: ColorSync.
- Linux/BSD: `colord`, `colormgr` o `_ICC_PROFILE`.

Si el perfil de monitor desaparece o no puede abrirse, ProbRAW registra el
problema y marca el estado como fallback visual sRGB hasta que se detecte o
seleccione un ICC de monitor valido. Ese fallback es solo de visualizacion; no
elimina ni sustituye el perfil de entrada de la imagen ni participa en recetas,
histogramas colorimetricos, TIFF, Proof o manifiestos.

## Previsualización e Histograma

La GUI distingue entre señal de análisis y señal de pantalla:

1. El RAW se revela o previsualiza como señal RGB normalizada con un ICC de
   entrada asignado: ICC de sesion/camara creado con referencias colorimetricas,
   o un ICC generico real de fallback como ProPhoto RGB.
2. Los ajustes paramétricos se aplican antes de la visualizacion.
3. Si hay un ICC fuente activo, los pixeles que llegan al widget se convierten
   directamente desde ese ICC fuente al ICC del monitor configurado y se
   entregan a Qt como RGB de dispositivo para que Qt/compositor no los convierta
   una segunda vez.
4. La senal sRGB interna queda limitada a histograma RGB, overlay de clipping y
   diagnostico; no sustituye la conversion directa al monitor cuando hay ICC
   fuente.
5. El ICC del monitor nunca se mezcla con los datos de analisis, recetas ni
   TIFF exportados.
6. El muestreo Lab de pixel usa la misma separacion: RGB de imagen con ICC de
   entrada para analisis, y conversion al monitor solo para visualizacion.

Esto evita que un perfil de monitor estrecho, defectuoso o diferente entre
equipos altere los datos de análisis. A la vez, exige que el usuario calibre el
monitor y configure correctamente su ICC en el sistema operativo para que la
apariencia visual de la preview sea fiable.

## Nota de rendimiento de preview ICC

Para evitar aplicar ICC sobre una preview embebida que no corresponde al RAW
revelado, las vistas con ICC de sesion o perfil generico evitan la miniatura
embebida y usan revelado LibRaw. La preview normal se mantiene acotada por
`PREVIEW_AUTO_BASE_MAX_SIDE`; precision 1:1, comparar, marcado de carta,
muestreo Lab de pixel y mediciones MTF fuerzan resolucion completa cuando la
medicion necesita coordenadas reales. En trabajo a 100%, las interacciones
aplican los ajustes al recorte visible, actualizan regiones del visor y
reutilizan caches de LUT ICC densas generadas por LittleCMS para no sacrificar
precision colorimetrica. Las curvas reutilizan LUTs tonales y comparten la
cuantizacion RGB previa a las conversiones `ICC fuente -> ICC monitor` e
instrumentos.

## Diagnostico Lab de Muestras

La pestaña `Diagnostico > Muestras` es diagnostica y no altera el pipeline de
revelado. Cada muestra registra coordenada real, matriz de muestreo, RGB
normalizado, Lab, C*, pertenencia a gamut y el ICC usado para interpretar el RGB.
Las muestras se agrupan por conjunto para representar variaciones internas de
una tinta, papel, zona o material.

Las comparaciones entre conjuntos usan:

- medias RGB y Lab por conjunto;
- dispersion interna `DE00` respecto al centro del conjunto;
- DeltaE y diferencia de C* frente al conjunto de referencia activo;
- similitud porcentual basada en vecinos cercanos `DE00 <= 3`;
- gamut visual de las muestras en Lab a*b*.

Estos datos son validos para auditoria comparativa cuando proceden de una imagen
con ICC de sesion generado por ProbRAW. Con perfiles genericos, deben etiquetarse
como diagnostico orientativo.

## Validez del Perfil

El perfil depende de:

- cámara;
- óptica;
- iluminante;
- receta;
- versión de software;
- configuración relevante del pipeline RAW.

Cambiar esos factores puede degradar o invalidar la validez colorimétrica.
