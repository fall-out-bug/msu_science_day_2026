/* Session continuity belongs to this tab; scientific results are never stored. */
(function (root) {
  'use strict';
  const key = 'science-day.lesson.v1';
  let storage = 'session', warning = null;
  function read() {
    try {
      const raw = sessionStorage.getItem(key);
      if (!raw) return null;
      if (raw.length > 32768) throw new Error('oversize');
      const value = JSON.parse(raw);
      if (!value || value.schema !== 1 || !value.lesson || !value.ui ||
          !Array.isArray(value.ui.found) || !['welcome','story','collect','work','free'].includes(value.ui.journey) ||
          !Number.isInteger(value.ui.cardIndex) || value.ui.cardIndex < 0 || value.ui.cardIndex > 9) throw new Error('invalid');
      return value;
    } catch (error) {
      warning = 'Сохранённую смену открыть не удалось. Можно начать новую.';
      if (error.name === 'SecurityError') storage = 'memory';
      return null;
    }
  }
  function write(lesson, ui) {
    try {
      sessionStorage.setItem(key, JSON.stringify({schema:1,lesson,ui}));
      storage = 'session';
      return true;
    } catch (_) {
      storage = 'memory';
      warning = 'Браузер не сохраняет смену. Она доступна до перезагрузки вкладки.';
      return false;
    }
  }
  function clear() { try { sessionStorage.removeItem(key); } catch (_) {} }
  root.GalaxyLessonStorage = {read,write,clear,diagnostics:() => ({storage,warning})};
})(globalThis);
