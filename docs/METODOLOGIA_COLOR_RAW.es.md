# Metodología de Revelado RAW y Gestión ICC

_English version: [METODOLOGIA_COLOR_RAW.md](METODOLOGIA_COLOR_RAW.md)_

Este documento fija el criterio metodológico de ProbRAW para separar revelado
paramétrico, perfil de ajuste, perfiles ICC de entrada de imagen y perfil ICC
del monitor.

La decisión vigente es mantener un flujo científico centrado en ICC. La
integración DCP fue evaluada como posibilidad futura, pero no forma parte del
alcance activo de la serie 0.3 porque añade complejidad y puede mezclar
decisiones colorimétricas con decisiones de apariencia.

## Referencias Consultadas

- RawTherapee, `Sidecar Files - Processing Profiles`:
  https://rawpedia.rawtherapee.com/Sidecar_Files_-_Processing_Profiles
- RawTherapee, `Color Management`:
  https://rawpedia.rawtherapee.com/Color_Management
- RawTherapee, `ICC Profile Creator`:
  https://rawpedia.rawtherapee.com/ICC_Profile_Creator
- International Color Consortium, `ICC.1:2022`:
  https://www.color.org/specification/ICC.1-2022-05.pdf
- ISO 17321-1:2012, caracterización de color de cámaras digitales.
- Sharma, Wu y Dalal, `The CIEDE2000 color-difference formula` (2005).
- Danny Pascale, `RGB coordinates of the Macbeth ColorChecker` (2006).
- Rong, Fleming y Sharma, `Quantitative analysis of ICC profile quality for
  scanners` (2004).

## Criterio Conceptual

Un RAW no es una imagen RGB final. Es una captura de datos del sensor que debe
interpretarse mediante una receta de revelado: demosaico, balance de blancos,
nivel negro, compensación de exposición, curva tonal, ICC de imagen asignado y
otros parámetros.

En ProbRAW, el perfil ICC de entrada no se calcula sobre el RAW desnudo. Se
calcula después de revelar una captura de carta con una receta controlada,
porque las mediciones se hacen sobre valores RGB producidos por el revelador.
Una vez generado, ese ICC describe cómo interpretar los RGB de cámara/sesión
producidos por esa misma receta, cámara e iluminante.

Los valores RGB son relativos al dispositivo o al espacio de revelado que los
produce. El ICC de entrada etiqueta esos valores y define su correspondencia
objetiva con colorimetria PCS/Lab/XYZ. Sin esa etiqueta, el triplete RGB no es un
color objetivo reproducible.

El cuentagotas Lab de imagen aplica exactamente este principio. El valor RGB de
un píxel o matriz de píxeles solo puede convertirse en una medición Lab rigurosa
si la imagen tiene asignado un ICC de sesión generado por ProbRAW para esa
cámara, receta e iluminante. Un ICC genérico permite calcular coordenadas Lab de
forma matemática, pero no convierte la escena en una referencia colorimétrica
medida.

Por tanto:

- la receta corrige y documenta el revelado base;
- el perfil de ajuste guarda decisiones paramétricas por archivo;
- el ICC de entrada describe la respuesta colorimétrica medida de la sesión;
- cuando no hay ICC de sesion medido, un ICC generico real como ProPhoto RGB se
  asigna como perfil de entrada fallback, no se inventa como otro perfil;
- el ICC de monitor solo corrige la visualización.

## Flujo Técnico Recomendado

El contrato metodológico para RAW es:

1. Abrir el RAW con LibRaw/rawpy.
2. Leer modelo de cámara, CFA, black level, white level, white balance as-shot,
   matriz de cámara y perfil embebido cuando existan.
3. Normalizar datos RAW a `float32` lineal.
4. Aplicar sustracción de negro y normalización por blanco.
5. Aplicar balance de blancos en espacio de cámara.
6. Ejecutar demosaico.
7. Producir RGB de camara/sesion con un ICC de entrada asignado. Cuando no hay
   carta, asignar un ICC generico real de fallback como ProPhoto RGB.
8. Aplicar ajustes paramétricos documentados.
9. Para pantalla, convertir directamente desde el ICC de entrada de la imagen al
   ICC de monitor configurado por el sistema operativo.
10. Para exportacion, incrustar el ICC de entrada asociado y registrar
    procedencia.
11. Para análisis de muestras, medir siempre sobre la imagen real a resolución
    completa, registrar coordenada, matriz, RGB, Lab, ICC usado y grupo de
    comparación en la mochila del archivo.

Implementación actual:

- con carta, ProbRAW conserva RGB lineal de cámara/sesión e incrusta el ICC de
  entrada generado;
- sin carta, ProbRAW asigna un ICC generico real de entrada como fallback en vez
  de inventar un perfil de sesion o de salida;
- la preview gestionada convierte solo `ICC entrada -> ICC monitor`;
- el perfil del monitor nunca modifica TIFF, hashes, manifiestos ni Proof.

## Perfil de Ajuste por Archivo

ProbRAW 0.2 trata el revelado paramétrico como una propiedad asignada a cada RAW
mediante su mochila:

```text
captura.NEF
captura.NEF.probraw.json
```

Una sesión puede contener varios perfiles de ajuste. Esto evita asumir que toda
la sesión es homogénea: una carpeta puede incluir cambios de luz, óptica,
exposición o criterio de entrega.

Tipos:

- **Perfil avanzado**: nace de una carta de color y puede incluir ICC de entrada
  de sesión.
- **Perfil básico**: nace de ajustes manuales y se asocia a un ICC generico real
  de entrada si no hay carta.

## Flujo Con Carta de Color

Cuando existe una captura válida de carta:

1. Revelar la carta con una receta científica base.
2. Detectar y medir parches de la carta.
3. Generar un perfil de revelado: balance de blancos, densidad y exposición
   derivados de la carta.
4. Medir de nuevo la carta con la receta calibrada.
5. Generar el ICC de entrada de sesión con ArgyllCMS a partir de RGB medidos y
   referencias colorimétricas.
6. Guardar por separado perfil de ajuste, receta calibrada, ICC de entrada,
   reportes QA y overlays.
7. Revelar los RAW equivalentes con ese perfil.
8. Crear TIFF maestro manteniendo RGB de cámara/sesión e incrustando el ICC de
   entrada.

El perfil avanzado puede copiarse a imágenes tomadas bajo condiciones
comparables de cámara, óptica, iluminante, exposición base y receta.

## Análisis de Muestras Lab

El análisis de muestras Lab está pensado para comparar zonas reales de una
imagen, por ejemplo varias tomas de una misma tinta impresa sobre papel. Una sola
toma puede depender de textura, ruido, velocidad de trazo, acumulación local de
tinta o iluminación microscópica. Agrupar varias tomas en un conjunto permite
estimar mejor la variación cromática real de ese material.

Reglas metodológicas:

- medir solo sobre píxeles reales de la imagen cargada a tamaño completo;
- documentar matriz, coordenada, nombre y nota de cada muestra;
- agrupar muestras que pertenecen al mismo material o hipótesis de comparación;
- comparar conjuntos mediante media Lab, dispersión interna, DeltaE frente al
  conjunto de referencia y gamut de muestras en Lab a*b*;
- no usar una muestra primaria dentro del conjunto, porque la referencia
  operacional es el conjunto completo.

La lectura RGB siempre es trazable. La lectura Lab, DeltaE y gamut de muestras
solo son colorimétricamente rigurosos cuando el ICC de entrada de la imagen es
un perfil generado por ProbRAW para ese caso de captura. Con perfiles genéricos,
el análisis debe rotularse como orientativo.

## Criterios de Mejora No Bloqueantes

ProbRAW debe permitir generar perfiles aunque el caso de trabajo no sea ideal.
Las comprobaciones metodológicas se tratan como estado, aviso o recomendación,
no como impedimento, salvo cuando no hay muestras de carta válidas o cuando una
validación independiente disponible demuestra un error colorimétrico fuera de
umbral.

Recomendaciones operativas:

- si existe más de una captura de carta, reservar una para validación
  independiente cuando sea posible;
- si solo hay una captura, generar el ICC como `draft` y registrar que falta
  validación independiente;
- con ColorChecker 24, usar por defecto `shaper+matrix (-as)`; los perfiles
  cLUT se permiten como opción avanzada, pero se documentan como riesgo de
  sobreajuste si no hay una carta con muchos más parches;
- revisar de forma separada la fila neutra: residuos a*/b*, dominantes,
  exposición y uniformidad de iluminación pueden revelar problemas que una
  media DeltaE no muestra;
- para trabajos críticos, preferir una referencia Lab D50 medida de la carta
  física utilizada, con serie, fecha e instrumento, en vez de una referencia
  genérica de ColorChecker.

Estados:

- `validated`: hay validación independiente utilizable y supera los umbrales;
- `draft`: el perfil se ha generado, pero falta validación independiente o esta
  no es concluyente; puede activarse manualmente bajo criterio del operador;
- `rejected`: una validación disponible o el entrenamiento superan los umbrales
  de error definidos; no se autoactiva y solo puede activarse con confirmación
  explícita para diagnóstico o comparación;
- `expired`: el perfil validado ha superado su ventana de vigencia configurada.

Los metadatos del perfil deben reflejar el modelo real solicitado a ArgyllCMS:
`argyll_shaper_matrix`, `argyll_gamma_matrix`, `argyll_matrix`,
`argyll_lab_clut`, `argyll_xyz_clut` o `argyll_custom`. La matriz 3x3 guardada
en el reporte es diagnóstica cuando el ICC real se ha generado con una cLUT.

## Flujo Sin Carta de Color

Cuando no existe carta:

1. No se inventa un ICC de sesión.
2. El usuario guarda un perfil de ajuste manual.
3. ProbRAW asigna un ICC generico real de entrada, normalmente ProPhoto RGB,
   salvo que la sesion elija explicitamente otro ICC generico de entrada.
4. ProbRAW mantiene ese ICC como perfil de entrada de imagen para analisis y
   gestion de pantalla.
5. La trazabilidad declara que no hay perfil de entrada de sesion medido y nombra
   el ICC generico de entrada usado.

Este flujo es reproducible y funcional, pero no sustituye la precisión de una
referencia colorimétrica medida.

Las muestras Lab tomadas en este flujo sin carta tienen la misma limitación: son
útiles para comparar de forma interna bajo el mismo espacio genérico, pero no
deben presentarse como medición Lab validada de la escena.

## TIFF Maestro y Derivados

ProbRAW distingue:

- **TIFF maestro con carta**: RGB de cámara/sesión, perfil de ajuste calibrado,
  ICC de entrada de sesión, ProbRAW Proof y C2PA opcional.
- **TIFF manual sin carta**: RAW revelado con mochila de ajuste por archivo y un
  ICC generico real de entrada.
- **TIFF derivado explicito**: exportacion no analitica solicitada por el
  usuario. Nunca debe alimentar preview, histograma, muestreo, MTF ni QA de
  perfil.

Las salidas existentes no se sobrescriben. ProbRAW crea versiones `_v002`,
`_v003`, etc.

## Mochilas y Auditoría

El sidecar de mochila registra:

- identidad y hash del RAW;
- receta de revelado aplicada;
- perfil de ajuste asignado;
- ICC asociado y hash cuando existe;
- ajustes de detalle y render;
- muestras Lab por imagen, con coordenadas reales, grupos, notas y comparación
  de conjuntos;
- últimas salidas TIFF generadas.

La mochila no sustituye al RAW ni al manifiesto de lote. Su función es transportar
ajustes paramétricos por archivo de forma auditable y portable.
