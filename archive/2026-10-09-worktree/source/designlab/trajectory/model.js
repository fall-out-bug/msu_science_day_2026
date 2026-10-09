/* Pure measurement model: prediction never receives truth coordinates. */
(function (global) {
  'use strict';
  const TOLERANCE = 4; // fixed interaction tolerance, source-image pixels
  const copy = p => p && { x: p.x, y: p.y };
  function predict(marks, dates) {
    if (!marks[0] || !marks[1]) return null;
    const times = dates.map(d => Date.parse(d));
    if (!times.every(Number.isFinite) || !(times[1] > times[0]) || !(times[2] > times[1])) {
      throw new RangeError('Observations must have increasing finite dates');
    }
    const ratio = (times[2] - times[1]) / (times[1] - times[0]);
    return { x: marks[1].x + (marks[1].x - marks[0].x) * ratio,
      y: marks[1].y + (marks[1].y - marks[0].y) * ratio, ratio };
  }
  class Investigation {
    constructor(item) { this.item = item; this.marks = [null, null];
      this.frozen = null; this.revealed = false; this.assisted = false; }
    mark(epoch, x, y) {
      if (![0, 1].includes(epoch) || ![x, y].every(Number.isFinite) ||
          x < -.5 || y < -.5 || x > 127.5 || y > 127.5) throw new RangeError('Invalid source coordinate');
      this.marks[epoch] = { x, y };
    }
    get prediction() { return predict(this.marks, this.item.observations.map(o => o.date)); }
    test() {
      if (!this.prediction) return false;
      if (!this.revealed) {
        this.frozen = Object.freeze({ marks: Object.freeze(this.marks.map(p => Object.freeze(copy(p)))),
          prediction: Object.freeze({ ...this.prediction }), assisted: this.assisted });
        this.revealed = true;
      }
      return true;
    }
    result(original = false) {
      if (!this.revealed) return null;
      const p = original ? this.frozen.prediction : this.prediction;
      if (!p) return null;
      const actual = this.item.truth.targets[2];
      const distance = Math.hypot(p.x - actual.x, p.y - actual.y);
      return { distance, withinTolerance: distance <= TOLERANCE };
    }
  }
  const api = { Investigation, predict, TOLERANCE };
  if (typeof module !== 'undefined') module.exports = api;
  global.TrajectoryModel = api;
})(globalThis);
