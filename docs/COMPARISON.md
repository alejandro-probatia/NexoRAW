_Spanish version: [COMPARISON.es.md](COMPARISON.es.md)_

# Tool comparison

This comparison summarizes capabilities to evaluate operational fit. Does not intend
measure artistic quality or general UX. Focuses on reproducibility,
traceability and technical-scientific validation.

Legend: `✅` available, `⚠️ parcial` available with limits or manual flow,
`❌` not available/not primary focus.

| Axis | ProbRAW | Darktable | RawTherapee | Lightroom + dcamprof | basICColor |
| --- | --- | --- | --- | --- | --- |
| Audible linear RAW development (no undeclared creative curves) | ✅ | ⚠️ partial (adjustment history, aimed at creative development) | ⚠️ partial (parametric, aimed at creative development) | ⚠️ partial (proprietary flow, limited traceability) | ❌ (it is not revealing general RAW) |
| ICC profile per session (not permanent camera) | ✅ | ⚠️ partial (possible with manual flow) | ⚠️ partial (possible with manual flow) | ⚠️ partial (dcamprof allows profiling, not natively integrated per session) | ✅ |
| Double pass letter -> calibrated recipe -> ICC | ✅ | ❌ | ❌ | ❌ | ❌ |
| JSON manifest and sidecars with hashes | ✅ | ❌ | ❌ | ❌ | ❌ |
| C2PA signature / chain of custody | ✅ | ❌ | ❌ | ❌ | ❌ |
| Colorimetric validation with independent holdout | ✅ | ❌ | ❌ | ⚠️ partial (depends on external pipeline) | ⚠️ partial (strong validation, formal holdout depends on the operator) |
| Per-image Lab samples with sets and DeltaE comparison | ✅ | ❌ | ❌ | ⚠️ partial (requires external tools or manual workflow) | ✅ |
| Profile operational status (`draft`/`validated`/`rejected`/`expired`) | ✅ | ❌ | ❌ | ❌ | ❌ |
| License | AGPL-3.0-or-later | GPL-3.0 | GPL-3.0 | Owner + external components | Owner |
| Optimal use case | Forensic/scientific with audit and traceable sessions | Advanced and creative photographic development | High-quality RAW development with manual control | Commercial photography flow with Adobe ecosystem | Industrial colorimetry and color management in commercial environments |

## Quick reading- ProbRAW does not compete in advanced creative tools against Darktable or
  RawTherapee.
- basICColor is an industrial colorimetric reference, but it does not prioritize
  open forensic traceability with sidecars/manifests.
- The differential of ProbRAW is the combination of operational reproducibility,
  audit and profiling per session with exportable technical evidence.
