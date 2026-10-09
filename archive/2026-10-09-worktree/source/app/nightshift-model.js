/* «Ночная смена»: чистая логика, без DOM, таймеров и случайности.
 * Классический скрипт; экспорт globalThis.NightShiftSession.
 * epoch — индекс frames: 0, 1 или 2. Третий кадр доступен после платной
 * заявки либо бесплатно после разбора. checked означает только платную заявку.
 *
 * report() описывает текущие версии, включая уточнения после разбора:
 * answered — решения, отличные от null; total — размер смены;
 * revised — раскрытые дела, где была версия до разбора и текущая отличается;
 * matched — текущие решения, совпадающие с архивным expectedVerdict;
 * open — текущие решения uncertain; unanswered — решения null.
 * revised не считает ответ, впервые записанный после общего разбора.
 * Это описательные счётчики, а не баллы или оценка первой попытки.
 */
(() => {
  "use strict";

  const IDS = Object.freeze(["s02", "s08", "s10", "s01", "s07", "s11", "s04", "s06", "s03"]);
  const COUNTS = Object.freeze([3, 6, 9]);
  const PREDICTIONS = Object.freeze(["motion", "brightness", "artifact", "stable", "uncertain"]);
  const VERDICTS = Object.freeze(["sky", "artifact", "stable", "uncertain"]);

  class NightShiftSession {
    constructor(data, count = 3) {
      if (!data || !Array.isArray(data.contact)) {
        throw new TypeError("NightShiftSession: нужен массив data.contact");
      }
      const byId = new Map();
      for (const c of data.contact) {
        if (!c || typeof c.id !== "string" || byId.has(c.id)) {
          throw new TypeError("NightShiftSession: у дел должны быть уникальные строковые id");
        }
        byId.set(c.id, c);
      }
      for (const id of IDS) {
        if (!byId.has(id) || !VERDICTS.includes(byId.get(id).expectedVerdict)) {
          throw new TypeError(`NightShiftSession: нет архивного дела с допустимым expectedVerdict: ${id}`);
        }
      }
      this._archive = byId;
      this.reset(count);
    }

    get cases() { return this._cases; }
    get current() { return this._archive.get(this.state.focus); }
    get budget() { return this.state.count / 3; }
    get remaining() {
      return this.budget - this.cases.filter(c => this.note(c.id).checked).length;
    }
    get completed() {
      return this.cases.filter(c => this.note(c.id).decision !== null).length;
    }

    note(id) {
      if (typeof id !== "string" || !Object.hasOwn(this.state.notes, id)) {
        throw new RangeError("NightShiftSession: неизвестное дело в этой смене");
      }
      return this.state.notes[id];
    }

    _enum(value, allowed) {
      if (!allowed.includes(value)) {
        throw new RangeError("NightShiftSession: недопустимое значение");
      }
    }

    select(id) {
      this.note(id);
      this.state.focus = id;
      return id;
    }

    mark(id, epoch, x, y) {
      const note = this.note(id);
      if (!Number.isInteger(epoch) || epoch < 0 || epoch > 2 || (epoch === 2 && !this.hasThird(id))) {
        throw new RangeError("NightShiftSession: кадр недоступен");
      }
      if (![x, y].every(v => typeof v === "number" && Number.isFinite(v) && v >= 0 && v <= 1)) {
        throw new RangeError("NightShiftSession: координаты отметки должны быть в диапазоне [0; 1]");
      }
      if (note.marks[epoch]?.x === x && note.marks[epoch]?.y === y) return false;
      note.marks[epoch] = { x, y };
      return true;
    }

    predict(id, value) {
      const note = this.note(id);
      this._enum(value, PREDICTIONS);
      if (note.prediction === value) return false;
      note.prediction = value;
      return true;
    }

    request(id) {
      const note = this.note(id);
      if (note.prediction === null) return false;
      if (this.hasThird(id)) return true;
      if (this.remaining === 0) return false;
      note.checked = true;
      return true;
    }

    decide(id, value) {
      const note = this.note(id);
      this._enum(value, VERDICTS);
      if (note.prediction === null) {
        throw new RangeError("NightShiftSession: сначала запиши наблюдение через predict()");
      }
      if (note.decision === value) return false;
      note.decision = value;
      return true;
    }

    reveal(id) {
      const note = this.note(id);
      if (note.revealed) return true;
      if (note.decision === null) return false;
      note.beforeReveal = note.decision;
      note.revealed = true;
      return true;
    }

    revealAll() {
      for (const c of this.cases) {
        const note = this.note(c.id);
        if (!note.revealed) {
          note.beforeReveal = note.decision;
          note.revealed = true;
        }
      }
    }

    hasThird(id) {
      const note = this.note(id);
      return note.checked || note.revealed;
    }

    nextId() {
      const start = this.cases.findIndex(c => c.id === this.state.focus);
      const ordered = this.cases.slice(start + 1).concat(this.cases.slice(0, start + 1));
      return ordered.find(c => this.note(c.id).decision === null)?.id ?? null;
    }

    reset(count = this.state?.count ?? 3) {
      this._enum(count, COUNTS);
      this._cases = Object.freeze(IDS.slice(0, count).map(id => this._archive.get(id)));
      const notes = {};
      for (const c of this.cases) {
        notes[c.id] = {
          marks: {}, prediction: null, checked: false, decision: null,
          beforeReveal: null, revealed: false,
        };
      }
      this.state = { count, focus: this.cases[0].id, notes };
      return this.state;
    }

    report() {
      let revised = 0, matched = 0, open = 0;
      for (const c of this.cases) {
        const note = this.note(c.id);
        if (note.revealed && note.beforeReveal !== null && note.decision !== note.beforeReveal) revised++;
        if (note.decision === c.expectedVerdict) matched++;
        if (note.decision === "uncertain") open++;
      }
      return {
        answered: this.completed, total: this.state.count, revised, matched, open,
        unanswered: this.state.count - this.completed,
      };
    }
  }

  globalThis.NightShiftSession = NightShiftSession;
  globalThis.NIGHTSHIFT_CASE_IDS = IDS;
})();
