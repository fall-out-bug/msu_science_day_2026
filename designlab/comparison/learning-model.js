/* A tiny, inspectable nearest-example instrument.  It links measured peaks;
 * it does not identify astronomical objects or estimate a probability. */
(function (root) {
  'use strict';
  const finite = value => Number.isFinite(value);
  const hours = date => Date.parse(date) / 3600000;
  const distance = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

  function generate(field, pixelScaleArcsec) {
    if (!field || !Array.isArray(field.sources) || field.sources.length !== 3 ||
        !Array.isArray(field.dates) || field.dates.length !== 3) throw new TypeError('Expected three measured epochs');
    const times = field.dates.map(hours), dt = [times[1] - times[0], times[2] - times[1]];
    if (!times.every(finite) || dt.some(value => !finite(value) || value <= 0)) throw new TypeError('Expected increasing observation times');
    if (!finite(pixelScaleArcsec) || pixelScaleArcsec <= 0) throw new TypeError('Expected physical pixel scale in arcsec/pixel');
    const candidates = [];
    field.sources[0].forEach((a, i) => field.sources[1].forEach((b, j) => field.sources[2].forEach((c, k) => {
      for (const point of [a, b, c]) if (!point || !finite(point.x) || !finite(point.y) || !finite(point.peak) || point.peak <= 0) throw new TypeError('Expected measured positive peaks');
      const velocity = [[(b.x - a.x) * pixelScaleArcsec / dt[0], (b.y - a.y) * pixelScaleArcsec / dt[0]],
        [(c.x - b.x) * pixelScaleArcsec / dt[1], (c.y - b.y) * pixelScaleArcsec / dt[1]]];
      const speed = velocity.map(vector => Math.hypot(...vector));
      const feature = Object.freeze([
        Math.log1p((speed[0] + speed[1]) / 2),
        Math.log1p(Math.hypot(velocity[1][0] - velocity[0][0], velocity[1][1] - velocity[0][1])),
        Math.log(Math.max(a.peak, b.peak, c.peak) / Math.min(a.peak, b.peak, c.peak))
      ]);
      candidates.push(Object.freeze({ id: `${i}:${j}:${k}`, sourceIndices: Object.freeze([i, j, k]),
        points: Object.freeze([a, b, c].map(p => Object.freeze({ x: p.x, y: p.y, peak: p.peak }))), feature }));
    })));
    return Object.freeze({ caseId: field.id, hours: Object.freeze(times.map(value => value - times[0])), candidates: Object.freeze(candidates) });
  }

  function fit(train) {
    const rows = train && train.candidates;
    if (!Array.isArray(rows) || !rows.length) throw new TypeError('Expected non-empty training candidates');
    const scale = [0, 1, 2].map(column => {
      const mean = rows.reduce((sum, row) => sum + row.feature[column], 0) / rows.length;
      const variance = rows.reduce((sum, row) => sum + (row.feature[column] - mean) ** 2, 0) / rows.length;
      return Math.sqrt(variance) || 1;
    });
    return Object.freeze({ scale: Object.freeze(scale) });
  }

  function score(train, labels, query, fitted = fit(train)) {
    const rows = train && train.candidates, queries = query && query.candidates;
    if (!Array.isArray(rows) || !Array.isArray(queries) || !Array.isArray(labels)) throw new TypeError('Expected generated fields and labels');
    const byId = new Map(rows.map(row => [row.id, row]));
    const examples = new Map();
    for (const label of labels) {
      if (!label || !byId.has(label.id) || !['sameObject', 'wrongLink'].includes(label.label)) throw new TypeError('Label must target a training candidate');
      if (!examples.has(label.id)) examples.set(label.id, label.label); // repeated click is idempotent
    }
    const positive = [...examples].filter(([, label]) => label === 'sameObject').map(([id]) => byId.get(id));
    const negative = [...examples].filter(([, label]) => label === 'wrongLink').map(([id]) => byId.get(id));
    if (!positive.length || !negative.length) throw new TypeError('At least one example of each decision is required');
    const d = (left, right) => Math.hypot(...left.feature.map((value, i) => (value - right.feature[i]) / fitted.scale[i]));
    return Object.freeze(queries.map(row => {
      const nearestPositive = Math.min(...positive.map(example => d(row, example)));
      const nearestNegative = Math.min(...negative.map(example => d(row, example)));
      const acceptanceScore = (nearestNegative - nearestPositive) / Math.max(nearestNegative + nearestPositive, 1e-12);
      return Object.freeze({ id: row.id, acceptanceScore, accepted: acceptanceScore > 0 });
    }));
  }
  root.LearningModel = Object.freeze({ generate, fit, score });
})(typeof window === 'undefined' ? globalThis : window);
