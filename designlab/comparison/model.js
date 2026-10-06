/* A deterministic image-comparison instrument. No labels, truth or ML inputs. */
(function (root) {
  'use strict';
  const SIZE = 128, N = SIZE * SIZE, DISPLAY_GAIN = 8;
  function settings(amount, epoch = 1) {
    if (!Number.isFinite(amount) || amount < 0 || amount > 1) throw new RangeError('amount must be in [0,1]');
    if (epoch !== 1 && epoch !== 2) throw new RangeError('epoch must be 1 or 2');
    return Object.freeze({ amount, epoch });
  }
  function residual(caseObj, amount, epoch = 1) {
    settings(amount, epoch);
    const ref = caseObj.arrays[0], frame = caseObj.arrays[epoch];
    if (ref.length !== N || frame.length !== N) throw new Error('Expected 128×128 arrays');
    const values = new Float64Array(N);
    for (let i = 0; i < N; i++) values[i] = frame[i] - amount * ref[i];
    return values;
  }
  function render(caseObj, amount, epoch = 1) {
    const values = residual(caseObj, amount, epoch);
    const pixels = new Uint8ClampedArray(N * 4), smooth = new Float64Array(N);
    // Fixed gain for this small low-flux probe, identical in all modes/fields.
    // Does not affect residuals, thresholds or detection results.
    const top = caseObj.displayTop / DISPLAY_GAIN;
    if (!(top > 0) || !(caseObj.noise > 0)) throw new Error('Invalid display/noise scale');
    const colors = [[8, 14, 29], [29, 63, 106], [101, 169, 205], [230, 250, 255]];
    const minus = [[8, 14, 29], [86, 45, 39], [190, 107, 64], [255, 217, 163]];
    for (let i = 0; i < N; i++) {
      const t = Math.asinh(Math.min(1, Math.abs(values[i]) / top) * 5) / Math.asinh(5);
      const u = t * 3, j = Math.min(2, Math.floor(u)), f = u - j;
      // Negative values become visible as subtraction is introduced; raw noise stays dark.
      const palette = values[i] < 0 ? minus : colors;
      const visibility = values[i] < 0 ? amount : 1;
      for (let c = 0; c < 3; c++) {
        const channel = palette[j][c] * (1 - f) + palette[j + 1][c] * f;
        pixels[i * 4 + c] = palette[0][c] + visibility * (channel - palette[0][c]);
      }
      pixels[i * 4 + 3] = 255;
    }
    // Separable [1,2,1] kernel, signed residual then absolute value. Boundary ignored.
    for (let y = 1; y < SIZE - 1; y++) for (let x = 1; x < SIZE - 1; x++) {
      const i = y * SIZE + x;
      let value = 0;
      for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
        value += values[i + dy * SIZE + dx] * (dy === 0 ? 2 : 1) * (dx === 0 ? 2 : 1);
      }
      smooth[i] = value / 16;
    }
    const candidates = [], threshold = 5 * caseObj.noise;
    for (let y = 3; y < SIZE - 3; y++) for (let x = 3; x < SIZE - 3; x++) {
      const i = y * SIZE + x, magnitude = Math.abs(smooth[i]);
      if (magnitude <= threshold || (amount === 0 && smooth[i] < 0)) continue;
      let maximum = true;
      for (let dy = -2; dy <= 2 && maximum; dy++) for (let dx = -2; dx <= 2; dx++) {
        const other = i + dy * SIZE + dx;
        if (Math.abs(smooth[other]) > magnitude || (Math.abs(smooth[other]) === magnitude && other < i)) {
          maximum = false; break;
        }
      }
      if (maximum) candidates.push({ x, y, value: smooth[i] });
    }
    candidates.sort((a, b) => Math.abs(b.value) - Math.abs(a.value) || a.y - b.y || a.x - b.x);
    return { pixels, peaks: candidates, count: candidates.length, amount, epoch };
  }
  root.ComparisonModel = Object.freeze({ render, residual, buildSnapshot: settings,
    run: (snapshot, caseObj) => render(caseObj, snapshot.amount, snapshot.epoch) });
})(typeof window === 'undefined' ? globalThis : window);
