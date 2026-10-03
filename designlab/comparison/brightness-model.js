/* Fixed-position aperture measurements of genuine ZTF pipeline differences.
 * Coordinates come from the user's first-frame choice, never a known target.
 * All outcome gates are fixed diagnostics; no astrophysical type is inferred.
 */
(function (root) {
  'use strict';
  const SIZE = 128;
  const limits = Object.freeze({ clickRadiusPx: 5, ambiguityGapPx: 1,
    apertureRadiusPx: 4, annulusInnerPx: 8, annulusOuterPx: 12,
    correlationFactor: 3, noiseMultiplier: 5, minimumFadeFraction: .35,
    minimumChangeToScience: .1, stableScienceFraction: .1,
    stableDifferenceToScience: .05 });
  const point = p => p ? Object.freeze({ x: p.x, y: p.y }) : null;
  const distance = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
  function select(data, x, y) {
    const result = (status, chosen, reason) => Object.freeze({ status, point: point(chosen), reason });
    if (!Number.isFinite(x) || !Number.isFinite(y) || x < 0 || x >= SIZE || y < 0 || y >= SIZE) {
      return result('empty', null, 'outside_frame');
    }
    const rows = data.sources && data.sources[0];
    if (!Array.isArray(rows)) throw new TypeError('Expected first-epoch measured sources');
    const click = { x, y };
    const near = rows.map(s => ({ source: s, distance: distance(s, click) }))
      .filter(s => s.distance <= limits.clickRadiusPx)
      .sort((a, b) => a.distance - b.distance || a.source.y - b.source.y || a.source.x - b.source.x);
    if (!near.length) return result('empty', null, 'no_peak_near_click');
    if (near.length > 1 && near[1].distance - near[0].distance <= limits.ambiguityGapPx) {
      return result('ambiguous', click, 'several_peaks_near_click');
    }
    return result('selected', near[0].source, 'measured_first_epoch_peak');
  }
  function median(values) {
    const sorted = values.slice().sort((a, b) => a - b), middle = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
  }
  function aperture(array, chosen) {
    if (!array || array.length !== SIZE * SIZE) throw new TypeError('Expected a calibrated 128x128 array');
    const values = [], ring = [], r = limits.annulusOuterPx;
    for (let y = Math.ceil(chosen.y - r); y <= Math.floor(chosen.y + r); y++) {
      for (let x = Math.ceil(chosen.x - r); x <= Math.floor(chosen.x + r); x++) {
        const d2 = (x - chosen.x) ** 2 + (y - chosen.y) ** 2;
        if (d2 > r * r) continue;
        const value = array[y * SIZE + x];
        if (!Number.isFinite(value)) throw new TypeError('Non-finite aperture pixels');
        if (d2 <= limits.apertureRadiusPx ** 2) values.push(value);
        if (d2 >= limits.annulusInnerPx ** 2) ring.push(value);
      }
    }
    const background = median(ring), localSigma = 1.4826 * median(ring.map(v => Math.abs(v - background)));
    const flux = values.reduce((sum, v) => sum + v - background, 0);
    return Object.freeze({ flux, background, localSigma,
      noiseScale: Math.max(1e-12, localSigma * Math.sqrt(values.length) * limits.correlationFactor),
      aperturePixels: values.length, annulusPixels: ring.length });
  }
  function measure(data, selection) {
    const empty = reason => Object.freeze({ outcome: 'unresolved', reason, point: point(selection.point),
      firstFlux: null, secondFlux: null, ratio: null, changeFraction: null,
      measurements: Object.freeze([]), fluxUnits: 'relative aperture flux at zero point 25' });
    if (selection.status !== 'selected' || !selection.point) return empty('no_selected_peak');
    const chosen = selection.point, margin = limits.annulusOuterPx;
    if (chosen.x < margin || chosen.y < margin || chosen.x > SIZE - 1 - margin || chosen.y > SIZE - 1 - margin) {
      return empty('incomplete_background_annulus');
    }
    const measurements = [0, 1].map(epoch => {
      const difference = aperture(data.differenceArrays[epoch], chosen);
      const science = aperture(data.arrays[epoch], chosen);
      return Object.freeze({ ...difference, scienceFlux: science.flux,
        scienceBackground: science.background, scienceNoiseScale: science.noiseScale });
    });
    const [first, second] = measurements;
    const combinedNoiseScale = Math.hypot(first.noiseScale, second.noiseScale);
    const change = second.flux - first.flux;
    const ratio = first.flux > 0 ? second.flux / first.flux : null;
    const scienceChangeFraction = first.scienceFlux > 0 ?
      (second.scienceFlux - first.scienceFlux) / first.scienceFlux : null;
    let outcome = 'unresolved', reason = 'no_clear_fade_or_stability';
    const reliableScience = first.scienceFlux > limits.noiseMultiplier * first.scienceNoiseScale &&
      second.scienceFlux > limits.noiseMultiplier * second.scienceNoiseScale;
    if (reliableScience && first.flux > limits.noiseMultiplier * first.noiseScale &&
        -change > limits.noiseMultiplier * combinedNoiseScale &&
        -change >= limits.minimumFadeFraction * first.flux &&
        -change > limits.minimumChangeToScience * first.scienceFlux) {
      outcome = 'faded'; reason = 'difference_aperture_decreased';
    } else if (reliableScience && Math.abs(scienceChangeFraction) <= limits.stableScienceFraction &&
        Math.abs(first.flux) <= limits.stableDifferenceToScience * first.scienceFlux &&
        Math.abs(second.flux) <= limits.stableDifferenceToScience * first.scienceFlux) {
      outcome = 'stable'; reason = 'no_large_change_within_fixed_gates';
    }
    return Object.freeze({ outcome, reason, point: point(chosen), firstFlux: first.flux,
      secondFlux: second.flux, ratio, changeFraction: ratio === null ? null : ratio - 1,
      absoluteChange: change, scienceChangeFraction, combinedNoiseScale,
      measurements: Object.freeze(measurements), fluxUnits: 'relative aperture flux at zero point 25' });
  }
  root.BrightnessModel = Object.freeze({ select, measure, limits });
})(typeof window === 'undefined' ? globalThis : window);
