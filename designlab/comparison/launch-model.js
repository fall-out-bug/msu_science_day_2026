/* Blind proposals over every detected source. No catalogue targets or labels.
 * Movement uses two epochs and a frozen prediction, then verifies epoch three.
 * Fading uses science aperture flux: the numeric check repeats the scan, while
 * the third exposure independently describes subsequent brightness only.
 */
(function (root) {
  'use strict';
  const SIZE = 128;
  const limits = Object.freeze({ apertureRadiusPx: 4, annulusInnerPx: 8,
    annulusOuterPx: 12, stationaryRadiusPx: 2, correlationFactor: 3,
    minimumFadeFraction: .35, noiseMultiplier: 5, systematicFraction: .05,
    minimumControls: 2, maximumControlScatter: .15, maximumCommonChange: .25 });
  const distance = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
  const point = p => Object.freeze({ x: p.x, y: p.y });
  const median = values => {
    const v = values.slice().sort((a, b) => a - b), m = Math.floor(v.length / 2);
    return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2;
  };
  function rows(data, epoch) {
    const result = data.sources && data.sources[epoch];
    if (!Array.isArray(result) || result.some(s => !s || !Number.isFinite(s.x) ||
        !Number.isFinite(s.y) || !Number.isFinite(s.peak) || s.peak <= 0)) {
      throw new TypeError('Expected measured source peaks');
    }
    return result;
  }
  function aperture(array, chosen) {
    if (!array || array.length !== SIZE * SIZE) throw new TypeError('Expected 128x128 science pixels');
    const margin = limits.annulusOuterPx;
    if (chosen.x < margin || chosen.y < margin || chosen.x > SIZE - 1 - margin ||
        chosen.y > SIZE - 1 - margin) return null;
    const inside = [], ring = [];
    for (let y = Math.ceil(chosen.y - margin); y <= Math.floor(chosen.y + margin); y++) {
      for (let x = Math.ceil(chosen.x - margin); x <= Math.floor(chosen.x + margin); x++) {
        const d2 = (x - chosen.x) ** 2 + (y - chosen.y) ** 2;
        if (d2 > margin ** 2) continue;
        const value = array[y * SIZE + x];
        if (!Number.isFinite(value)) throw new TypeError('Non-finite science aperture');
        if (d2 <= limits.apertureRadiusPx ** 2) inside.push(value);
        if (d2 >= limits.annulusInnerPx ** 2) ring.push(value);
      }
    }
    const background = median(ring);
    const localSigma = 1.4826 * median(ring.map(v => Math.abs(v - background)));
    const flux = inside.reduce((sum, v) => sum + v - background, 0);
    return Object.freeze({ flux, scienceFlux: flux, background, localSigma,
      noiseScale: Math.max(1e-12, localSigma * Math.sqrt(inside.length) * limits.correlationFactor),
      aperturePixels: inside.length, annulusPixels: ring.length });
  }
  function stationary(data, source, epoch) {
    const matches = rows(data, epoch).filter(s => distance(s, source) <= limits.stationaryRadiusPx);
    return matches.length === 1 && rows(data, 0).filter(s =>
      distance(s, matches[0]) <= limits.stationaryRadiusPx).length === 1;
  }
  function samplePair(data, epoch) {
    return rows(data, 0).map(source => {
      const measurements = [0, epoch].map(i => aperture(data.arrays[i], source));
      const valid = measurements.every(m => m && m.flux > limits.noiseMultiplier * m.noiseScale)
        && stationary(data, source, epoch);
      return { source, measurements, valid,
        ratio: valid ? measurements[1].flux / measurements[0].flux : null };
    });
  }
  function controls(samples) {
    const ratios = samples.filter(s => s.valid).map(s => s.ratio);
    if (ratios.length < limits.minimumControls) return Object.freeze({ count: ratios.length,
      ratio: null, scatter: null, valid: false });
    const ratio = median(ratios), scatter = 1.4826 * median(ratios.map(v => Math.abs(v / ratio - 1)));
    return Object.freeze({ count: ratios.length, ratio, scatter,
      valid: scatter <= limits.maximumControlScatter && Math.abs(ratio - 1) <= limits.maximumCommonChange });
  }
  function photometry(sample, field) {
    const [first, second] = sample.measurements;
    if (!sample.valid || !field.valid) return null;
    const relativeRatio = sample.ratio / field.ratio;
    const combinedNoiseScale = Math.hypot(first.noiseScale, second.noiseScale / field.ratio,
      first.flux * Math.max(limits.systematicFraction, field.scatter));
    const absoluteChange = second.flux / field.ratio - first.flux;
    const significance = Math.abs(absoluteChange) / combinedNoiseScale;
    const faded = relativeRatio <= 1 - limits.minimumFadeFraction &&
      -absoluteChange > limits.noiseMultiplier * combinedNoiseScale;
    return Object.freeze({ outcome: faded ? 'faded' : 'unresolved',
      reason: faded ? 'science_aperture_decreased' : 'no_clear_science_fade',
      point: point(sample.source), firstFlux: first.flux, secondFlux: second.flux,
      ratio: sample.ratio, relativeRatio, changeFraction: sample.ratio - 1,
      absoluteChange, combinedNoiseScale, significance,
      measurements: Object.freeze(sample.measurements), controls: field,
      fluxUnits: 'relative science aperture flux at photometric zero point 25',
      product: 'science', independentConfirmation: false });
  }
  function scan(data, mode) {
    let candidates, inspectedCount, reason, field = null;
    if (mode === 'movement') {
      if (!root.TrackingModel) throw new Error('TrackingModel must load before LaunchModel');
      const sources = rows(data, 1);
      inspectedCount = sources.length;
      candidates = sources.map(source => root.TrackingModel.select(data, source.x, source.y))
        .filter(selection => selection.status === 'selected' && selection.kind === 'moving')
        .map(selection => Object.freeze({ id: `movement:${selection.point.x}:${selection.point.y}`,
          point: selection.point, origin: selection.origin, prediction: selection.prediction,
          selection, score: distance(selection.point, selection.origin),
          preview: Object.freeze({ kind: selection.kind, reason: selection.reason,
            displacementPx: distance(selection.point, selection.origin) }) }));
      reason = candidates.length ? 'motion_proposals_from_two_epochs' : 'no_unique_motion_candidate';
    } else if (mode === 'fading') {
      const samples = samplePair(data, 1);
      field = controls(samples);
      inspectedCount = samples.length;
      candidates = samples.map(s => photometry(s, field)).filter(p => p && p.outcome === 'faded')
        .map(preview => Object.freeze({ id: `fading:${preview.point.x}:${preview.point.y}`,
          point: preview.point, score: 1 - preview.relativeRatio, preview,
          selection: Object.freeze({ status: 'selected', point: preview.point,
            reason: 'blind_science_aperture_proposal' }) }));
      reason = candidates.length ? 'science_fade_proposals_from_two_epochs' :
        field.valid ? 'no_science_fade_candidate' : 'insufficient_stable_field_controls';
    } else throw new TypeError('Expected movement or fading mode');
    candidates.sort((a, b) => b.score - a.score || a.point.y - b.point.y || a.point.x - b.point.x);
    return Object.freeze({ mode, candidates: Object.freeze(candidates), inspectedCount, reason, controls: field });
  }
  function verify(data, mode, candidate) {
    if (!candidate || !candidate.point) return Object.freeze({ outcome: 'unresolved', reason: 'no_selected_candidate' });
    // Recompute the proposal; do not trust saved scores, outcomes or selections.
    const proposed = scan(data, mode).candidates.find(c => c.id === candidate.id &&
      distance(c.point, candidate.point) < 1e-9);
    if (!proposed) return Object.freeze({ outcome: 'unresolved', reason: 'candidate_not_in_scan' });
    if (mode === 'movement') return root.TrackingModel.confirm(data, proposed.selection);
    const result = proposed.preview;
    if (!data.arrays[2] || !data.sources[2]) return Object.freeze({ ...result,
      thirdOutcome: 'unavailable', sustainedFade: null });
    const thirdSamples = samplePair(data, 2), thirdControls = controls(thirdSamples);
    const thirdSample = thirdSamples.find(s => distance(s.source, proposed.point) < 1e-9);
    const third = thirdSample.measurements[1];
    let thirdOutcome = 'unresolved', sustainedFade = null, thirdRelativeRatio = null,
      thirdChangeNoiseScale = null, thirdChangeSignificance = null;
    if (thirdSample.valid && thirdControls.valid) {
      thirdRelativeRatio = thirdSample.ratio / thirdControls.ratio;
      const relativeToSecond = thirdRelativeRatio / result.relativeRatio;
      const thirdChange = third.flux / thirdControls.ratio - result.secondFlux / result.controls.ratio;
      thirdChangeNoiseScale = Math.hypot(third.noiseScale / thirdControls.ratio,
        result.measurements[1].noiseScale / result.controls.ratio,
        result.firstFlux * Math.max(limits.systematicFraction, thirdControls.scatter, result.controls.scatter));
      thirdChangeSignificance = Math.abs(thirdChange) / thirdChangeNoiseScale;
      if (relativeToSecond >= 1 + limits.minimumFadeFraction &&
          thirdChange > limits.noiseMultiplier * thirdChangeNoiseScale) {
        thirdOutcome = 'rebrightened'; sustainedFade = false;
      } else if (photometry(thirdSample, thirdControls).outcome === 'faded') {
        thirdOutcome = 'still_faint'; sustainedFade = true;
      } else { thirdOutcome = 'no_persistent_fade'; sustainedFade = false; }
    }
    return Object.freeze({ ...result, thirdFlux: third ? third.flux : null,
      thirdMeasurement: third, thirdControls, thirdRelativeRatio, thirdOutcome, sustainedFade,
      thirdChangeNoiseScale, thirdChangeSignificance,
      positions: Object.freeze([proposed.point, proposed.point, thirdSample.valid ? proposed.point : null]) });
  }
  root.LaunchModel = Object.freeze({ scan, verify, limits, aperture });
})(typeof window === 'undefined' ? globalThis : window);
