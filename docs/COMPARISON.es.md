# Comparativa de herramientas

Esta comparativa resume capacidades para evaluar encaje operativo. No pretende
medir calidad artistica ni UX general. Se centra en reproducibilidad,
trazabilidad y validacion tecnico-cientifica.

Leyenda: `✅` disponible, `⚠️ parcial` disponible con limites o flujo manual,
`❌` no disponible/no es foco principal.

| Eje | ProbRAW | Darktable | RawTherapee | Lightroom + dcamprof | basICColor |
| --- | --- | --- | --- | --- | --- |
| Revelado RAW lineal auditable (sin curvas creativas no declaradas) | ✅ | ⚠️ parcial (historial de ajustes, orientado a revelado creativo) | ⚠️ parcial (parametrico, orientado a revelado creativo) | ⚠️ parcial (flujo propietario, trazabilidad limitada) | ❌ (no es revelador RAW generalista) |
| Perfil ICC por sesion (no permanente de camara) | ✅ | ⚠️ parcial (posible con flujo manual) | ⚠️ parcial (posible con flujo manual) | ⚠️ parcial (dcamprof permite perfilado, no integrado por sesion de forma nativa) | ✅ |
| Doble pasada carta -> receta calibrada -> ICC | ✅ | ❌ | ❌ | ❌ | ❌ |
| Manifiesto y sidecars JSON con hashes | ✅ | ❌ | ❌ | ❌ | ❌ |
| Firma C2PA / cadena de custodia | ✅ | ❌ | ❌ | ❌ | ❌ |
| Validacion colorimetrica con holdout independiente | ✅ | ❌ | ❌ | ⚠️ parcial (depende de pipeline externo) | ⚠️ parcial (validacion fuerte, holdout formal depende del operador) |
| Muestras Lab por imagen con conjuntos y comparacion DeltaE | ✅ | ❌ | ❌ | ⚠️ parcial (requiere herramientas externas o flujo manual) | ✅ |
| Estado operacional del perfil (`draft`/`validated`/`rejected`/`expired`) | ✅ | ❌ | ❌ | ❌ | ❌ |
| Licencia | AGPL-3.0-or-later | GPL-3.0 | GPL-3.0 | Propietario + componentes externos | Propietario |
| Caso de uso optimo | Forense/cientifico con auditoria y sesiones trazables | Revelado fotografico avanzado y creativo | Revelado RAW de alta calidad con control manual | Flujo fotografico comercial con ecosistema Adobe | Colorimetria industrial y gestion de color en entornos comerciales |

## Lectura rapida

- ProbRAW no compite en herramientas creativas avanzadas frente a Darktable o
  RawTherapee.
- basICColor es referencia colorimetrica industrial, pero no prioriza
  trazabilidad forense abierta con sidecars/manifiestos.
- El diferencial de ProbRAW es la combinacion de reproducibilidad operativa,
  auditoria y perfilado por sesion con evidencia tecnica exportable.
