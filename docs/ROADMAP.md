_Versión en español: [ROADMAP.es.md](ROADMAP.es.md)_

# Roadmap

This roadmap describes the active direction of ProbRAW after the 0.3.0
reorganization. It favors a stable, reproducible ICC workflow over adding
parallel color-profile layers.

## Completed Foundation

- Modular Python package under `src/probraw`.
- Canonical CLI and GUI entry points: `probraw` and `probraw-ui`.
- Debian package under the ProbRAW name, with no legacy `iccraw` launchers.
- Qt GUI with session, adjustment/profile and render queue tabs.
- Persistent session structure:
  - `00_configuraciones/`
  - `01_ORG/`
  - `02_DRV/`
- Per-file development backpacks (`RAW.probraw.json`).
- Chart-based advanced development profiles.
- Session input ICC generation with ArgyllCMS.
- Persistent session ICC profile catalog with several activatable versions.
- Chart references managed from the interface, including a Lab table editor for
  custom charts.
- Pairwise 3D/Lab 2D gamut diagnostics for session profiles, monitor profile,
  standard spaces and custom ICC files.
- Lab eyedropper with real-pixel magnifier, per-image persistent samples, sample
  sets and DeltaE/gamut comparison between sets.
- Standard output ICC workflow for no-chart sessions.
- Monitor ICC management for preview only.
- Manual four-corner chart marking in the viewer.
- ProbRAW Proof and optional C2PA metadata.
- Full test suite passing for 0.3.0 packaging validation.

## Current Principle

The active color-management line is:

```text
RAW -> reproducible recipe -> development profile -> ICC workflow -> TIFF + proof
```

DCP support is not an active 0.2 objective. The archived planning document is
kept only for traceability: [Archived DCP + ICC roadmap](ROADMAP_DCP_ICC.md).

## Phase 1 - Stability and Real-World QA

Objective: make the current GUI workflow robust with real RAW sessions.

- Exercise the installed application with real chart captures and target RAWs.
- Improve chart-selection interaction, cursor states and overlay consistency.
- Harden long-running batch rendering and cross-profile validation.
- Expand regression tests around manual chart marking and queue processing.
- Keep AMaZE availability visible and verifiable in packaged builds.

## Phase 2 - Documentation and Release Readiness

Objective: make the project understandable and reproducible for external users.

- Keep the bilingual user manual current with real screenshots.
- Keep README, methodology, color pipeline and installer docs aligned.
- Document every GUI option and global setting.
- Maintain release notes and package checksums for each published build.
- Avoid stale implementation names, old folder layouts and obsolete plans.

## Phase 3 - Colorimetric Validation Depth

Objective: improve confidence in profiles generated from references.

- Strengthen QA reports for chart detection, sampling and profile status.
- Improve comparison of QA reports between sessions.
- Add discipline-specific DeltaE thresholds and warnings.
- Improve holdout/validation workflows when several chart captures exist.
- Make failure states clearer in GUI and CLI.

## Phase 4 - Performance and Large Sessions

Objective: keep ProbRAW responsive as sessions grow.

- Continue optimizing persistent preview and thumbnail caches.
- Benchmark RAW browsing, 1:1 preview and profile preview on representative
  hardware.
- Improve cancellation/progress feedback for long tasks.
- Keep final renders reproducible even when interactive preview uses faster
  bounded sources.

## Phase 5 - Distribution and Portability

Objective: make installation and verification repeatable across platforms.

- Keep Debian packaging reproducible.
- Continue Windows and macOS installer work.
- Validate external-tool detection on supported platforms.
- Preserve sidecar/session portability across machines.
- Maintain license and third-party notices for bundled dependencies.

## Future Research

Possible future work must not weaken the ICC-centered scientific workflow:

- fuller IT8 support;
- profile comparison across illuminants and sessions;
- additional QA visualizations;
- richer C2PA manifests;
- external interoperability for sidecar exchange.
