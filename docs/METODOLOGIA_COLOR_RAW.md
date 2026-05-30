_Versión en español: [METODOLOGIA_COLOR_RAW.es.md](METODOLOGIA_COLOR_RAW.es.md)_

# RAW Development Methodology and ICC Management

This document defines ProbRAW's methodological criteria for separating
parametric RAW development, development profiles, image input ICC profiles and
monitor ICC profiles.

The current decision is to keep a scientific ICC-centered workflow. DCP
integration was evaluated as a possible future direction, but it is not active
scope for the 0.4 series because it adds complexity and can mix colorimetric
decisions with appearance decisions.

## References

- RawTherapee, `Sidecar Files - Processing Profiles`:
  https://rawpedia.rawtherapee.com/Sidecar_Files_-_Processing_Profiles
- RawTherapee, `Color Management`:
  https://rawpedia.rawtherapee.com/Color_Management
- RawTherapee, `ICC Profile Creator`:
  https://rawpedia.rawtherapee.com/ICC_Profile_Creator

## Conceptual Criterion

A RAW file is not a final RGB image. It is a capture of sensor data that must be
interpreted through a development recipe: demosaic, white balance, black level,
exposure compensation, tone curve, assigned image ICC and other parameters.

In ProbRAW, the input ICC profile is not computed from the bare RAW file. It is
computed after developing a chart capture with a controlled recipe, because
measurements are made on RGB values produced by the developer. Once generated,
that ICC describes how to interpret the camera/session RGB produced by the same
recipe, camera and illuminant.

RGB values are relative to the device or development space that produced them.
The input ICC tags those values and defines their objective correspondence to
PCS/Lab/XYZ colorimetry. Without that tag, an RGB triplet is not an objectively
reproducible color.

The image Lab eyedropper applies exactly the same principle. The RGB value of a
pixel or pixel matrix can become a rigorous Lab measurement only when the image
has a ProbRAW-generated session ICC assigned for that camera, recipe and
illuminant. A generic ICC allows mathematical Lab coordinates to be calculated,
but it does not turn the scene into a measured colorimetric reference.

Therefore:

- the recipe corrects and documents base development;
- the development profile stores per-file parametric decisions;
- the input ICC describes the measured colorimetric response of the session;
- when there is no measured session ICC, a real generic ICC such as ProPhoto RGB
  is assigned as an input profile fallback, not invented as another profile;
- the monitor ICC corrects display only.

## Recommended Technical Flow

The methodological RAW contract is:

1. Open the RAW with LibRaw/rawpy.
2. Read camera model, CFA, black level, white level, as-shot white balance,
   camera matrix and embedded profile when available.
3. Normalize RAW data to linear `float32`.
4. Apply black subtraction and white normalization.
5. Apply white balance in camera space.
6. Run demosaic.
7. Produce camera/session RGB with an assigned input ICC. When there is no chart,
   assign a real generic input ICC fallback such as ProPhoto RGB.
8. Apply documented parametric adjustments.
9. For display, convert directly from the image input ICC to the monitor ICC
   profile configured by the operating system.
10. For export, embed the associated image input ICC and record provenance.
11. For sample analysis, always measure from the real full-resolution image and
    record coordinate, matrix, RGB, Lab, ICC used and comparison group in the
    file backpack.

Current implementation:

- with a chart, ProbRAW preserves linear camera/session RGB and embeds the
  generated input ICC;
- without a chart, ProbRAW assigns a real generic ICC input profile fallback
  instead of inventing a session profile or any other profile;
- managed preview converts only `input ICC -> monitor ICC`;
- the monitor profile never changes TIFFs, hashes, manifests or Proof data.

## Per-file Development Profile

ProbRAW treats parametric development as a property assigned to each RAW file
through its backpack:

```text
capture.NEF
capture.NEF.probraw.json
```

A session can contain several development profiles. This avoids assuming that a
whole folder is homogeneous: one session may include changes in lighting, lens,
exposure or delivery criteria.

Types:

- **Advanced profile**: created from a color chart and optionally tied to a
  session input ICC.
- **Basic profile**: created from manual adjustments and associated with a real
  generic input ICC when no chart exists.

## Workflow With a Color Chart

When a valid chart capture exists:

1. Develop the chart with a base scientific recipe.
2. Detect and measure chart patches.
3. Build a development profile: white balance, density and exposure derived from
   the chart.
4. Measure the chart again with the calibrated recipe.
5. Generate the session input ICC with ArgyllCMS from measured RGB values and
   colorimetric references.
6. Save development profile, calibrated recipe, input ICC, QA reports and
   overlays separately.
7. Develop equivalent RAW files with that profile.
8. Create a master TIFF preserving camera/session RGB and embedding the input
   ICC.

The advanced profile can be copied to images captured under comparable camera,
lens, illuminant, base exposure and recipe conditions.

## ICC Profile QA State

ProbRAW must allow profile generation even when the working case is not ideal.
Methodological checks become state, warning or recommendation, not a hard block,
except when there are no valid chart samples or when available independent
validation proves the colorimetric error is outside threshold.

Operational recommendations:

- when more than one chart capture exists, reserve one for independent
  validation when possible;
- with only one capture, generate the ICC as `draft` and record the missing
  independent validation;
- with ColorChecker 24, default to `shaper+matrix (-as)`; cLUT profiles remain
  available as an advanced option, but they are documented as an overfit risk
  without a chart with many more patches;
- review the neutral row separately: a*/b* residuals, casts, exposure and light
  uniformity can reveal issues that a mean DeltaE does not show;
- for critical work, prefer measured D50 Lab values for the physical chart in
  use, including serial, date and instrument, instead of a generic ColorChecker
  reference.

States:

- `validated`: usable independent validation exists and passes thresholds;
- `draft`: the profile was generated, but independent validation is missing or
  inconclusive; the operator may activate it manually;
- `rejected`: available validation or training error exceeds the configured
  thresholds; it never autoactivates and can only be activated with explicit
  confirmation for diagnosis or comparison;
- `expired`: the validated profile exceeded its configured validity window.

Profile metadata must report the real model requested from ArgyllCMS:
`argyll_shaper_matrix`, `argyll_gamma_matrix`, `argyll_matrix`,
`argyll_lab_clut`, `argyll_xyz_clut` or `argyll_custom`. The 3x3 matrix stored in
the report is diagnostic when the real ICC was generated with a cLUT.

## Lab Sample Analysis

Lab sample analysis is intended for comparing real image areas, for example
several measurements of the same ink printed on paper. A single sample may depend
on texture, noise, stroke speed, local ink accumulation or microscopic
illumination. Grouping several samples into a set gives a better estimate of the
real chromatic variation of that material.

Methodological rules:

- measure only real pixels from the full-size loaded image;
- document matrix, coordinate, name and note for each sample;
- group samples that belong to the same material or comparison hypothesis;
- compare sets through mean Lab, internal dispersion, DeltaE against the
  reference set and sample gamut in Lab a*b*;
- do not use a primary sample inside the set, because the operational reference
  is the complete set.

RGB readings are always traceable. Lab readings, DeltaE and sample gamut are
colorimetrically rigorous only when the image input ICC is a ProbRAW-generated
profile for that capture case. With generic profiles, the analysis must be
labelled as informative.

## Workflow Without a Color Chart

When no chart exists:

1. ProbRAW does not invent a session ICC.
2. The user saves a manual development profile.
3. ProbRAW assigns a real generic input ICC fallback, normally ProPhoto RGB,
   unless the session explicitly chooses another generic input profile.
4. ProbRAW keeps that ICC as the image input profile for analysis and display
   management.
5. Traceability states that there is no measured session input profile and names
   the generic input ICC used.

This workflow is reproducible and functional, but it does not replace the
precision of a measured colorimetric reference.

Lab samples taken in this no-chart workflow have the same limitation: they are
useful for internal comparison within the same generic space, but they must not
be presented as validated scene Lab measurements.

## Master TIFF and Derivatives

ProbRAW distinguishes:

- **Chart-based master TIFF**: camera/session RGB, calibrated development
  profile, session input ICC, ProbRAW Proof and optional C2PA.
- **Manual no-chart TIFF**: RAW developed with a per-file development backpack
  and a real generic input ICC fallback.
- **Explicit derivative TIFF**: a non-analysis export requested by the user. It
  must never feed back into preview, histogram, sampling, MTF or profile QA.

Existing outputs are not overwritten. ProbRAW creates `_v002`, `_v003`, etc.

## Backpacks and Audit

The backpack sidecar records:

- RAW identity and hash;
- applied development recipe;
- assigned development profile;
- associated ICC and hash when available;
- detail and render settings;
- per-image Lab samples, with real coordinates, groups, notes and set
  comparison;
- latest generated TIFF outputs.

The backpack does not replace the RAW or the batch manifest. Its purpose is to
transport per-file parametric settings in an auditable and portable way.
