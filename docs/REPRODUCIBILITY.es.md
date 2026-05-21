# Reproducibilidad

ProbRAW separa tres niveles:

- RAW original: nunca se modifica.
- Escena lineal: salida numerica despues de LibRaw/demosaico/WB/negro.
- Render final: exposicion, curva, gestion de color, firma y pruebas.
- Diagnostico por imagen: MTF y muestras Lab guardadas en la mochila del RAW,
  siempre referidas a coordenadas reales cuando requieren medicion.

## Tests golden

Los casos canonicos estan en `testdata/regression/MANIFEST.json`.
Cada caso declara:

- entrada,
- receta,
- SHA-256 del TIFF final,
- SHA-256 del TIFF lineal de auditoria.

El test `tests/regression/test_canonical_hashes.py` revela cada caso en un
directorio temporal y compara hashes byte a byte.

## Regenerar hashes

Solo debe hacerse cuando un cambio de algoritmo o dependencia modifica la
salida de forma intencional:

```powershell
python scripts/regenerate_golden_hashes.py --confirm --note "descripcion breve"
```

El script desactiva `use_cache` antes de revelar, actualiza el manifest y anade
una entrada en `tests/regression/golden/REGENERATION_LOG.md`.

## Cache y reproducibilidad

La cache de demosaico guarda arrays `.npy` de escena lineal para rendimiento.
Es opt-in y su clave contiene el SHA-256 completo del RAW y los parametros que
afectan a LibRaw. Los tests golden no usan cache para evitar falsos positivos
de infraestructura.

## Muestras Lab y reproducibilidad

Las muestras Lab se guardan en `RAW.probraw.json` junto a la imagen que las
originó. Cada registro conserva coordenada, matriz, RGB, Lab, C*, estado de
gamut, grupo, nombre, nota y color del marcador. Al reabrir la imagen, ProbRAW
recupera las muestras y las vuelve a dibujar numeradas sobre el visor.

La reproducibilidad de coordenadas exige que la medición se haga sobre la imagen
a tamaño completo. ProbRAW fuerza o solicita recarga de fuente real cuando una
preview reducida no permite garantizar píxeles exactos. La reproducibilidad
colorimétrica exige además que el ICC asignado a la imagen sea el mismo perfil
de sesión generado para la captura; con perfiles genéricos, las muestras siguen
siendo trazables, pero sus Lab/DeltaE son diagnósticos orientativos.
