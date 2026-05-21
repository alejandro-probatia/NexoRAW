_English version: [ROADMAP.md](ROADMAP.md)_

# Roadmap

Este roadmap describe la dirección activa de ProbRAW tras la reorganización
0.3.0. Prioriza un flujo ICC estable y reproducible frente a añadir capas
paralelas de perfilado de color.

## Base Completada

- Paquete Python modular bajo `src/probraw`.
- Entry points canónicos CLI y GUI: `probraw` y `probraw-ui`.
- Paquete Debian con nombre ProbRAW, sin lanzadores heredados `iccraw`.
- GUI Qt con pestañas de sesión, ajuste/perfilado y cola de revelado.
- Estructura persistente de sesión:
  - `00_configuraciones/`
  - `01_ORG/`
  - `02_DRV/`
- Mochilas de ajuste por archivo (`RAW.probraw.json`).
- Perfiles avanzados de ajuste desde carta.
- Generación de ICC de entrada de sesión con ArgyllCMS.
- Catálogo persistente de perfiles ICC de sesión con varias versiones activables.
- Referencias de carta gestionadas desde la interfaz, incluyendo editor tabular
  Lab para cartas personalizadas.
- Diagnóstico Gamut 3D/Lab 2D por pares para comparar perfiles de sesión,
  monitor, espacios estándar e ICC personalizados.
- Cuentagotas Lab con lupa de píxel real, muestras persistentes por imagen,
  conjuntos de muestras y comparación DeltaE/gamut entre conjuntos.
- Flujo con ICC estándar de salida para sesiones sin carta.
- Gestión ICC del monitor limitada al preview.
- Marcado manual de cuatro esquinas de carta en el visor.
- ProbRAW Proof y metadatos C2PA opcionales.
- Suite completa de tests superada para la validación de empaquetado 0.3.0.

## Principio Actual

La línea activa de gestión de color es:

```text
RAW -> receta reproducible -> perfil de ajuste -> flujo ICC -> TIFF + proof
```

El soporte DCP no es un objetivo activo de la serie 0.2. El documento de
planificación se conserva solo por trazabilidad:
[Roadmap DCP + ICC archivado](ROADMAP_DCP_ICC.md).

## Fase 1 - Estabilidad y QA con Uso Real

Objetivo: hacer robusto el flujo GUI actual con sesiones RAW reales.

- Probar la aplicación instalada con capturas reales de carta y RAW objetivo.
- Mejorar interacción de selección de carta, estados de cursor y consistencia de
  overlays.
- Endurecer revelado por lote de larga duración y validación cruzada de perfiles.
- Ampliar regresiones sobre marcado manual de carta y procesamiento de cola.
- Mantener AMaZE visible y verificable en builds empaquetadas.

## Fase 2 - Documentación y Preparación de Release

Objetivo: hacer el proyecto comprensible y reproducible para usuarios externos.

- Mantener el manual bilingüe actualizado con capturas reales.
- Alinear README, metodología, pipeline de color y documentación de instaladores.
- Documentar cada opción de GUI y configuración global.
- Mantener notas de release y checksums para cada build publicada.
- Evitar nombres de implementación antiguos, estructuras obsoletas y planes
  descartados.

## Fase 3 - Profundidad de Validación Colorimétrica

Objetivo: aumentar la confianza en perfiles generados desde referencias.

- Reforzar reportes QA de detección de carta, muestreo y estado de perfil.
- Mejorar comparación de reportes QA entre sesiones.
- Añadir umbrales DeltaE por disciplina y advertencias.
- Mejorar flujos holdout/validación cuando hay varias capturas de carta.
- Hacer más claros los estados de fallo en GUI y CLI.

## Fase 4 - Rendimiento y Sesiones Grandes

Objetivo: mantener ProbRAW fluido cuando las sesiones crecen.

- Seguir optimizando cachés persistentes de preview y miniaturas.
- Medir navegación RAW, preview 1:1 y preview de perfil en hardware
  representativo.
- Mejorar cancelación/progreso en tareas largas.
- Mantener renders finales reproducibles aunque el preview interactivo use
  fuentes acotadas más rápidas.

## Fase 5 - Distribución y Portabilidad

Objetivo: hacer repetibles instalación y verificación en varias plataformas.

- Mantener empaquetado Debian reproducible.
- Continuar trabajo de instaladores Windows y macOS.
- Validar detección de herramientas externas en plataformas soportadas.
- Preservar portabilidad de sesiones y sidecars entre equipos.
- Mantener avisos legales y licencias de dependencias empaquetadas.

## Investigación Futura

Cualquier ampliación futura debe preservar el flujo científico centrado en ICC:

- soporte IT8 más completo;
- comparación de perfiles entre iluminantes y sesiones;
- visualizaciones QA adicionales;
- manifiestos C2PA más ricos;
- interoperabilidad externa para intercambio de sidecars.
