# Bounded experiment: examples change a motion search

2026-10-03. Protocol fixed before examining model rankings. One learner, one
feature set, no parameter sweep or tuning against the second field.

Question: can one correction of a false association visibly change a simple
example-based search, including on another real field? Not a test of fun or
general astronomical accuracy. This is a local technical experiment, not a game.

Inputs: existing calibrated ZTF stacks from `generate_data.field_stack`.
`mover1` / Amosov is development/training; `mover2` / Gianni is the transfer probe.
Both fields are previously curated and known to contain movers, not a newly
blinded scientific test set. All three images are inputs to track association;
there is no claim of a blind third-epoch forecast.

Detection: existing `realdata.detect_sources(k=5)`, unmodified, all returned peaks.
Every Cartesian product of one detection per frame is a candidate track. No
ephemeris seeds or known target positions enter candidate extraction or features.

Features: log(1 + mean segment speed in arcsec/hour), log(1 + difference between
segment velocity vectors in arcsec/hour), log(max peak/min peak). Intervals come
from manifest MJD. Standard deviations fitted only to training-field candidates
set the three feature scales. Peak ratios are rough appearance descriptors, not
calibrated source photometry or a guaranteed invariant across exposures.

Learner: nearest positive / nearest negative exemplar distance margin
`(d_negative - d_positive)/(d_negative + d_positive)`. This is a small
nearest-exemplar classifier, with an explicit ranking score, not a probability.
Decision threshold is zero. Deterministic tie-breaking uses candidate index.

Initial examples: one independently verified mover track and up to four
cross-epoch persistent stationary tracks from mover1. Stationary matches use
unique mutual-nearest matches within 1.5 pixels, supported across all three
frames. They are operational stationary controls, not catalog-confirmed stars.
They are negatives for the task "moving track", not false same-source matches.

Choose two distinct false associations with the highest initial scores in the
training field, restricted to tracks whose detections all belong to verified
mover/persistent-control identities but mix identities. Each is a separate
plausible correction from the same initial model, adding one negative example.
Also test both corrections together, an intentionally wrong positive label for
the first false track, and undo. No corrections are selected from mover2.
If initial false candidates are not accepted, record that the proposed correction
scene is unsupported rather than injecting an error.

Report separately: known mover rank/score, accepted known false or stationary
tracks, accepted unlabelled tracks, top-ranked coordinates, score/rank changes.
No whole-field accuracy/recall; mixed tracks of unverified identity remain unknown.

Comparator: a fixed geometric rule ranks moving candidates (both segment
displacements >=2 pixels) by distance of the middle position from constant-velocity
interpolation of endpoints, using actual unequal time intervals. This rule has
no player training. If it already finds the target first, record that the ML
experiment has not demonstrated a need for learning over this baseline.

Acceptance: honest pass/partial/fail for causal change, transfer, usefulness,
and proposed correction scene. A failure is a valid result. No additional model
family or parameter search in this experiment. Preserve evidence and discuss
the design implication instead of manufacturing success.

Reference for nearest-neighbor learning:
https://scikit-learn.org/stable/modules/neighbors.html
