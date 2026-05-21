_Spanish version: [REPRODUCIBILITY.es.md](REPRODUCIBILITY.es.md)_

# Reproducibility

ProbRAW separates three levels:

- Original RAW: never modified.
- Linear scene: numerical output after LibRaw/demosaic/WB/black.
- Final render: exposure, curve, color management, signature and tests.
- Per-image diagnostics: MTF and Lab samples saved in the RAW backpack, always
  referenced to real coordinates when measurement requires it.

## Tests golden

The canonical cases are in `testdata/regression/MANIFEST.json`.
Each case states:

- entrance,
- recipe,
- SHA-256 of the final TIFF,
- SHA-256 linear TIFF audit.

The `tests/regression/test_canonical_hashes.py` test reveals each case in a
temporary directory and compare hashes byte by byte.

## Regenerate hashes

This should only be done when an algorithm or dependency change modifies the
output intentionally:
```powershell
python scripts/regenerate_golden_hashes.py --confirm --note "descripcion breve"
```
The script disables `use_cache` before revealing, updates the manifest, and adds
an entry in `tests/regression/golden/REGENERATION_LOG.md`.

## Cache and reproducibility

The demo cache stores `.npy` linear scene arrays for performance.
It is opt-in and its key contains the complete SHA-256 of the RAW and the parameters that
affect LibRaw. Golden tests do not use cache to avoid false positives
of infrastructure.

## Lab Samples and Reproducibility

Lab samples are saved in `RAW.probraw.json` next to the image that produced them.
Each record keeps coordinate, matrix, RGB, Lab, C*, gamut state, group, name,
note and marker color. When the image is reopened, ProbRAW restores the samples
and draws them numbered over the viewer.

Coordinate reproducibility requires measurement from the full-size image. ProbRAW
forces or requests a real-source reload when a reduced preview cannot guarantee
exact pixels. Colorimetric reproducibility also requires the ICC assigned to the
image to be the same session profile generated for the capture; with generic
profiles, samples remain traceable, but their Lab/DeltaE values are informative
diagnostics.
