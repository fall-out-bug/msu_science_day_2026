/* Pure state for the prepared galaxy experiment. No rendering or training here. */
(function (root) {
  'use strict';
  function create(data) {
    const classes = data.classes.map(item => item.id);
    const imageIds = new Set(data.images.map(item => item.id));
    if (classes.length !== 3 || new Set(classes).size !== 3 || data.editableIds.length !== 5 ||
        new Set(data.editableIds).size !== 5 || data.childIds.length !== 3 || data.oldIds.length !== 2 ||
        data.editableIds.join('|') !== [...data.childIds, ...data.oldIds].join('|') ||
        data.editableIds.some(id => !imageIds.has(id)) ||
        data.oldIds.some(id => !classes.includes(data.initialOldLabels[id]))) {
      throw new Error('Набор опыта повреждён. Нужна полная копия игры.');
    }
    function fresh() {
      return { phase: 'intro', resumePhase: 'tutorial', labels: {
        ...Object.fromEntries(data.childIds.map(id => [id, null])), ...data.initialOldLabels
      }, key: null, current: null, baseline: null, repairCheckedKey: null, finalSeen: false, notice: '' };
    }
    let state = fresh();
    function key(labels) {
      if (data.editableIds.some(id => !classes.includes(labels[id]))) return null;
      return data.editableIds.map(id => classes.indexOf(labels[id])).join('');
    }
    function requirePhase(...phases) {
      if (!phases.includes(state.phase)) throw new Error('Сначала заверши текущий шаг.');
    }
    function dispatch(action) {
      switch (action.type) {
        case 'START':
          requirePhase('intro');
          state = { ...state, phase: 'tutorial', notice: '' };
          break;
        case 'LABELS':
          requirePhase('tutorial', 'labels', 'results', 'repair', 'final');
          state = { ...state, phase: 'labels', notice: '' };
          break;
        case 'SET_LABEL': {
          const allowed = state.phase === 'labels' ? data.childIds : state.phase === 'repair' ? data.oldIds : [];
          if (!allowed.includes(action.id) || !classes.includes(action.label)) {
            throw new Error('Выбери одну из трёх подписей к текущему снимку.');
          }
          if (state.labels[action.id] === action.label) {
            state = { ...state, notice: 'Подпись не изменилась.' };
            break;
          }
          const labels = { ...state.labels, [action.id]: action.label };
          state = { ...state, labels, key: key(labels), current: null, repairCheckedKey: null,
            notice: state.baseline ? 'Подписи изменились. Открой новый опыт, чтобы проверить результат.' : '' };
          break;
        }
        case 'RUN': {
          requirePhase('labels', 'repair');
          const signature = key(state.labels);
          if (signature === null) throw new Error('Сначала выбери подписи для всех трёх снимков.');
          const experiment = data.experiments[signature];
          if (!experiment || experiment.key !== signature) {
            throw new Error('Для этих подписей опыт отсутствует. Позови стендиста.');
          }
          const unchanged = state.baseline && signature === state.baseline.key;
          state = { ...state, phase: 'results', key: signature, current: experiment,
            repairCheckedKey: state.phase === 'repair' ? signature : state.repairCheckedKey,
            baseline: state.baseline || experiment,
            notice: unchanged ? 'Подписи те же, что в первой проверке: показан тот же опыт.' : '' };
          break;
        }
        case 'REPAIR':
          requirePhase('results', 'labels', 'repair');
          if (!state.baseline) throw new Error('Сначала проверь ответы модели.');
          state = { ...state, phase: 'repair', notice: '' };
          break;
        case 'FINISH':
          requirePhase('results');
          if (!state.current || state.current.key !== key(state.labels) || state.repairCheckedKey !== state.current.key) {
            throw new Error('Сначала проверь старые подписи и открой повторный опыт.');
          }
          state = { ...state, phase: 'final', notice: state.finalSeen
            ? 'Эти итоговые снимки уже были открыты. Это повторный просмотр.'
            : 'Эти галактики не использовались для обучения и выбора модели.', finalSeen: true };
          break;
        case 'HOME':
          if (state.phase !== 'intro') state = { ...state, resumePhase: state.phase, phase: 'intro' };
          break;
        case 'RESUME':
          requirePhase('intro');
          state = { ...state, phase: state.resumePhase };
          break;
        case 'RESET': state = fresh(); break;
        default: throw new Error('Неизвестное действие.');
      }
      return snapshot();
    }
    function snapshot() { return { ...state, labels: { ...state.labels } }; }
    return { get state() { return snapshot(); }, dispatch };
  }
  root.GalaxyModel = { create };
  if (typeof module !== 'undefined' && module.exports) module.exports = root.GalaxyModel;
})(typeof globalThis !== 'undefined' ? globalThis : window);
