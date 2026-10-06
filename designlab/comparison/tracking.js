/* A conservative association of measured peaks, never an object classifier.
 * Selection reads two epochs only. The third epoch tests a frozen prediction.
 * Peak amplitudes are only a fixed compatibility heuristic, not photometry:
 * seeing, variability and a missed detection can leave a real track unresolved.
 */
(function (root) {
  'use strict';
  const LIMITS = Object.freeze({ clickRadiusPx: 5, clickAmbiguityPx: 1,
    stationaryRadiusPx: 2, associationRadiusPx: 3, confirmationRadiusPx: 3,
    peakRatioLimit: 3 });
  const distance = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
  const point = source => source ? Object.freeze({ x: source.x, y: source.y }) : null;
  function sources(caseObj, epoch) {
    const rows = caseObj.sources && caseObj.sources[epoch];
    if (!Array.isArray(rows) || rows.some(s => !s || !Number.isFinite(s.x) ||
        !Number.isFinite(s.y) || !Number.isFinite(s.peak) || s.peak <= 0)) {
      throw new TypeError('Expected measured {x,y,peak} sources for this epoch');
    }
    return rows;
  }
  const within = (rows, target, radius) => rows.filter(s => distance(s, target) <= radius);
  function selected(status, chosen, origin, prediction, kind, reason, extra = {}) {
    return Object.freeze({ status, point: point(chosen), origin: point(origin),
      prediction: point(prediction), kind, reason, ...extra });
  }
  function select(caseObj, x, y) {
    if (!Number.isFinite(x) || !Number.isFinite(y) || x < 0 || x >= 128 || y < 0 || y >= 128) {
      return selected('empty', null, null, null, 'unresolved', 'outside_frame');
    }
    const first = sources(caseObj, 0), second = sources(caseObj, 1);
    const click = { x, y };
    const candidates = within(second, click, LIMITS.clickRadiusPx)
      .map(s => ({ source: s, distance: distance(s, click) }))
      .sort((a, b) => a.distance - b.distance || a.source.y - b.source.y || a.source.x - b.source.x);
    if (!candidates.length) return selected('empty', null, null, null, 'unresolved', 'no_peak_near_click');
    if (candidates.length > 1 && candidates[1].distance - candidates[0].distance <= LIMITS.clickAmbiguityPx) {
      return selected('ambiguous', click, null, null, 'unresolved', 'several_peaks_near_click',
        { candidateCount: candidates.length });
    }
    const chosen = candidates[0].source;
    const staticOrigins = within(first, chosen, LIMITS.stationaryRadiusPx);
    if (staticOrigins.length === 1 && within(second, staticOrigins[0], LIMITS.stationaryRadiusPx).length === 1) {
      return selected('selected', chosen, staticOrigins[0], chosen, 'stationary', 'same_position_in_first_two');
    }
    // A near neighbour could be centroid jitter or blending. Do not invent motion.
    if (within(first, chosen, LIMITS.associationRadiusPx).length) {
      return selected('selected', chosen, null, null, 'unresolved', 'ambiguous_nearby_origin');
    }
    const disappeared = first.filter(s => !within(second, s, LIMITS.associationRadiusPx).length);
    const compatible = disappeared.filter(s => {
      const ratio = s.peak / chosen.peak;
      return ratio >= 1 / LIMITS.peakRatioLimit && ratio <= LIMITS.peakRatioLimit;
    });
    if (compatible.length !== 1) {
      return selected('selected', chosen, null, null, 'unresolved',
        compatible.length ? 'several_possible_origins' : 'no_compatible_origin',
        { originCandidateCount: compatible.length, disappearedCount: disappeared.length });
    }
    const origin = compatible[0];
    // Two new peaks competing for the same disappeared peak are unresolved too.
    const competing = second.filter(s => !within(first, s, LIMITS.associationRadiusPx).length)
      .filter(s => s.peak / origin.peak >= 1 / LIMITS.peakRatioLimit &&
        s.peak / origin.peak <= LIMITS.peakRatioLimit);
    if (competing.length !== 1) {
      return selected('selected', chosen, null, null, 'unresolved', 'several_possible_destinations',
        { destinationCandidateCount: competing.length });
    }
    const times = [0, 1, 2].map(i => Date.parse(caseObj.dates && caseObj.dates[i]));
    if (!times.every(Number.isFinite) || times[1] <= times[0] || times[2] <= times[1]) {
      return selected('selected', chosen, origin, null, 'unresolved', 'invalid_observation_times');
    }
    const timeRatio = (times[2] - times[1]) / (times[1] - times[0]);
    const prediction = { x: chosen.x + (chosen.x - origin.x) * timeRatio,
      y: chosen.y + (chosen.y - origin.y) * timeRatio };
    return selected('selected', chosen, origin, prediction, 'moving', 'unique_compatible_displacement',
      { timeRatio, originCandidateCount: compatible.length, disappearedCount: disappeared.length });
  }
  function confirm(caseObj, selection) {
    const third = sources(caseObj, 2);
    const positions = [point(selection.origin), point(selection.point), null];
    const result = (outcome, reason, observed = null, extra = {}) => {
      const actualPositions = positions.slice(); actualPositions[2] = point(observed);
      return Object.freeze({ outcome, reason, positions: Object.freeze(actualPositions),
        prediction: point(selection.prediction), distancePx: observed && selection.prediction ?
          distance(observed, selection.prediction) : null, ...extra });
    };
    if (selection.status !== 'selected') return result('unresolved', 'no_selected_peak');
    if (!selection.prediction || selection.kind === 'unresolved') {
      const atSelection = within(third, selection.point, LIMITS.confirmationRadiusPx);
      return result('unresolved', selection.reason, null,
        { observationAtSelection: atSelection.length === 1 ? point(atSelection[0]) : null,
          samePositionDetected: atSelection.length > 0 });
    }
    const matches = within(third, selection.prediction, LIMITS.confirmationRadiusPx);
    if (!matches.length) return result('lost', 'no_peak_at_prediction');
    if (matches.length !== 1) return result('unresolved', 'several_peaks_at_prediction', null,
      { confirmationCandidateCount: matches.length });
    const observed = matches[0];
    if (selection.kind === 'stationary') return result('stationary', 'same_position_in_three', observed);
    if (distance(observed, selection.point) <= LIMITS.associationRadiusPx ||
        distance(observed, selection.origin) <= LIMITS.associationRadiusPx) {
      return result('unresolved', 'third_displacement_too_small', observed);
    }
    // Coinciding with an already present background source is not track evidence.
    if (within(sources(caseObj, 0), observed, LIMITS.associationRadiusPx).length ||
        within(sources(caseObj, 1), observed, LIMITS.associationRadiusPx).length) {
      return result('unresolved', 'prediction_matches_existing_source', observed);
    }
    return result('moving', 'third_peak_supports_linear_prediction', observed);
  }
  root.TrackingModel = Object.freeze({ select, confirm, limits: LIMITS });
})(typeof window === 'undefined' ? globalThis : window);
