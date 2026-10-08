/* The desktop lesson reads only an exhaustive, offline CNN experiment table.
   It never substitutes a 1-NN answer or trains in the browser. */
(function (root) {
  'use strict';

  function create(data, table) {
    if (!data || !table || !table.experiments || !table.protocol) {
      throw new Error('Не удалось открыть подготовленный CNN-опыт.');
    }

    const protocol = table.protocol;
    const classes = (protocol.classes || data.classes || []).map(item =>
      typeof item === 'string' ? item : item.id
    );
    const editable = protocol.editableIds || data.editableIds;
    const childIds = protocol.childIds || data.childIds;
    const oldIds = protocol.oldIds || data.oldIds;
    const suppliedInitial = protocol.initialLabels || data.initialOldLabels || {};

    // A generated table may contain all nine canonical training labels. At the
    // start, a learner owns only the two existing labels; new images are blank.
    const initial = Object.fromEntries(
      oldIds.map(id => [id, suppliedInitial[id] || data.initialOldLabels?.[id]])
    );

    if (
      !Array.isArray(editable) ||
      editable.length !== 5 ||
      editable.join('|') !== [...childIds, ...oldIds].join('|') ||
      childIds.length !== 3 ||
      oldIds.length !== 2 ||
      !classes.length
    ) {
      throw new Error('Неверный контракт CNN-опыта.');
    }

    function signature(labels) {
      if (editable.some(id => !classes.includes(labels[id]))) return null;
      return editable.map(id => classes.indexOf(labels[id])).join('');
    }

    function lookup(labels, architecture) {
      const key = signature(labels);
      const experiment = key && table.experiments[key];
      const run = experiment?.architectures?.[architecture];

      if (!run || run.key !== key || run.blocks !== Number(architecture)) {
        throw new Error('Для этих меток и устройства модели нет подготовленного опыта.');
      }
      return { key, architecture: String(architecture), run };
    }

    function fresh() {
      return {
        phase: 'intro',
        resumePhase: 'tutorial',
        labels: {
          ...initial,
          ...Object.fromEntries(childIds.map(id => [id, null]))
        },
        architecture: '1',
        labelKey: null,
        current: null,
        baseline: null,
        correctedReview: null,
        architectureBaseline: null,
        repairCheckedLabelKey: null,
        modelSettings: false,
        finalSeen: false,
        notice: ''
      };
    }

    let state = fresh();

    function snapshot() {
      return { ...state, labels: { ...state.labels } };
    }

    function requirePhase(...allowed) {
      if (!allowed.includes(state.phase)) {
        throw new Error('Сначала заверши текущий шаг.');
      }
    }

    function dispatch(action) {
      switch (action.type) {
        case 'START':
          requirePhase('intro');
          state = { ...state, phase: 'tutorial', notice: '' };
          break;

        case 'LABELS':
          requirePhase('tutorial', 'labels', 'review', 'repair', 'final');
          // Keep comparison snapshots, but never leave the settings panel active.
          state = { ...state, phase: 'labels', modelSettings: false, notice: '' };
          break;

        case 'SET_LABEL': {
          const allowed = state.phase === 'labels' ? childIds : state.phase === 'repair' ? oldIds : [];
          if (!allowed.includes(action.id) || !classes.includes(action.label)) {
            throw new Error('Выбери одну из трёх меток к текущему снимку.');
          }
          if (state.labels[action.id] === action.label) {
            state = { ...state, notice: 'Метка не изменилась.' };
            break;
          }

          const labels = { ...state.labels, [action.id]: action.label };
          state = {
            ...state,
            labels,
            labelKey: signature(labels),
            current: null,
            repairCheckedLabelKey: null,
            architectureBaseline: null,
            correctedReview: null,
            modelSettings: false,
            notice: state.baseline ? 'Метки изменились. Обучи и проверь модель ещё раз.' : ''
          };
          break;
        }

        case 'SET_ARCHITECTURE': {
          requirePhase('review');
          const architecture = String(action.architecture);
          if (!['1', '2'].includes(architecture)) {
            throw new Error('Можно сравнить только один или два свёрточных блока.');
          }
          if (!state.repairCheckedLabelKey || state.repairCheckedLabelKey !== signature(state.labels)) {
            throw new Error('Сначала исправь старые метки и повтори проверку.');
          }
          if (state.architecture === architecture) {
            state = { ...state, notice: 'Устройство модели не изменилось.' };
            break;
          }

          state = {
            ...state,
            architecture,
            architectureBaseline: state.current || state.architectureBaseline,
            current: null,
            modelSettings: true,
            notice: 'Устройство модели изменилось. Обучи и проверь её на тех же снимках.'
          };
          break;
        }

        case 'MODEL_SETTINGS':
          requirePhase('review');
          if (!state.repairCheckedLabelKey || state.repairCheckedLabelKey !== signature(state.labels)) {
            throw new Error('Сначала исправь старые метки и повтори проверку.');
          }
          state = {
            ...state,
            modelSettings: true,
            notice: 'Выбери устройство модели и повтори проверку.'
          };
          break;

        case 'RUN': {
          requirePhase('labels', 'review', 'repair');
          const found = lookup(state.labels, state.architecture);
          const current = {
            labelKey: found.key,
            resultKey: found.run.key,
            architecture: found.architecture,
            result: found.run
          };
          const unchanged = state.current && state.current.resultKey === current.resultKey;
          const repaired = state.phase === 'repair';

          state = {
            ...state,
            phase: 'review',
            labelKey: found.key,
            current,
            modelSettings: false,
            baseline: state.baseline || current,
            correctedReview: repaired ? current : state.correctedReview,
            repairCheckedLabelKey: repaired ? found.key : state.repairCheckedLabelKey,
            notice: unchanged ? 'Метки и устройство те же: показан тот же подготовленный опыт.' : ''
          };
          break;
        }

        case 'REPAIR':
          requirePhase('review', 'labels', 'repair');
          if (!state.baseline) throw new Error('Сначала обучи и проверь модель.');
          // The comparison snapshot survives opening old labels.
          state = { ...state, phase: 'repair', modelSettings: false, notice: '' };
          break;

        case 'FINISH':
          requirePhase('review');
          if (!state.current || state.current.labelKey !== state.repairCheckedLabelKey) {
            throw new Error('Сначала проверь старые метки и повтори опыт.');
          }
          state = {
            ...state,
            phase: 'final',
            notice: state.finalSeen
              ? 'Эти итоговые снимки уже были открыты. Это повторный просмотр.'
              : 'Это другие снимки, которых не было в обучении. Проверим ответы.',
            finalSeen: true
          };
          break;

        case 'HOME':
          if (state.phase !== 'intro') {
            state = { ...state, resumePhase: state.phase, phase: 'intro' };
          }
          break;

        case 'RESUME':
          requirePhase('intro');
          state = { ...state, phase: state.resumePhase };
          break;

        case 'RESET':
          state = fresh();
          break;

        default:
          throw new Error('Неизвестное действие.');
      }
      return snapshot();
    }

    return {
      get state() {
        return snapshot();
      },
      dispatch,
      protocol
    };
  }

  root.GalaxyCNNLesson = { create };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = root.GalaxyCNNLesson;
  }
})(typeof globalThis !== 'undefined' ? globalThis : window);
