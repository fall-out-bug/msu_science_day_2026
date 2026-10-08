/* The desktop lesson reads only an exhaustive, offline CNN experiment table.
   It never substitutes a 1-NN answer or trains in the browser. */
(function (root) {
  'use strict';

  function create(data, table) {
    if (!data || !table || !table.experiments || !table.protocol) {
      throw new Error('Не удалось открыть подготовленный опыт с нейросетью.');
    }

    const protocol = table.protocol;
    if (typeof protocol.protocolVersion !== 'string' || protocol.datasetVersion !== data.datasetVersion) throw new Error('Версия учебного опыта не совпадает с данными.');
    const registry = root.GalaxyArchitectures;
    if (!registry?.configurations?.length) throw new Error('Не удалось открыть схемы нейронной сети.');
    const architectureInfo = id => registry.get(String(id));
    const phases = ['intro', 'tutorial', 'labels', 'review', 'repair', 'final'];
    const classes = (protocol.classes || data.classes || []).map(item =>
      typeof item === 'string' ? item : item.id
    );
    const editable = protocol.editableIds || data.editableIds;
    const childIds = protocol.childIds || data.childIds;
    const oldIds = protocol.oldIds || data.oldIds;
    const suppliedInitial = protocol.initialLabels || data.initialOldLabels || {};

    // A generated table may contain all canonical training labels. At the
    // start, a learner owns only the existing labels; new images are blank.
    const initial = Object.fromEntries(
      oldIds.map(id => [id, suppliedInitial[id] || data.initialOldLabels?.[id]])
    );

    if (
      !Array.isArray(editable) ||
      !Array.isArray(childIds) ||
      !Array.isArray(oldIds) ||
      !editable.length ||
      editable.join('|') !== [...childIds, ...oldIds].join('|') ||
      !childIds.length ||
      !oldIds.length ||
      !classes.length
    ) {
      throw new Error('Данные учебного опыта не согласованы.');
    }

    function signature(labels) {
      if (editable.some(id => !classes.includes(labels[id]))) return null;
      return editable.map(id => classes.indexOf(labels[id])).join('');
    }

    function lookup(labels, architecture) {
      const key = signature(labels);
      const experiment = key && table.experiments[key];
      const run = experiment?.architectures?.[architecture];

      if (!run || run.key !== key || run.architectureId !== String(architecture) || run.blocks !== architectureInfo(architecture)?.depth) {
        throw new Error('Для этих меток и архитектуры модели нет подготовленного опыта.');
      }
      for (const scope of ['review','final']) {
        const result = run[scope], ids = protocol[scope + 'Ids'];
        if (!result || !Array.isArray(result.predictions) || result.total !== ids.length || result.predictions.length !== ids.length ||
            result.predictions.some((item,i) => item.id !== ids[i] || !classes.includes(item.predicted) ||
              item.expected !== data.images.find(image => image.id === item.id)?.label) ||
            result.correct !== result.predictions.filter(item => item.expected === item.predicted).length) {
          throw new Error('Результат опыта повреждён. Нужна полная версия материалов.');
        }
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
        architecture: 'd1-r',
        labelKey: null,
        current: null,
        baseline: null,
        correctedReview: null,
        architectureBaseline: null,
        repairCheckedLabelKey: null,
        reviewedOldIds: [],
        modelSettings: false,
        finalSeen: false,
        notice: ''
      };
    }

    let state = fresh();

    function snapshot() {
      const reviewedOldIds = [...state.reviewedOldIds];
      const repairReady = oldIds.every(id => reviewedOldIds.includes(id));
      const exactReview = state.current && state.current.labelKey === state.repairCheckedLabelKey;
      let nextAction = null;
      if (state.phase === 'repair') nextAction = repairReady ? 'run_repair' : 'confirm_old_labels';
      if (state.phase === 'review') nextAction = exactReview ? 'compare_architecture_or_finish' : 'review_old_labels';
      return { ...state, labels: { ...state.labels }, reviewedOldIds, repairReady, nextAction };
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
          const reviewedOldIds = state.phase === 'repair' && !state.reviewedOldIds.includes(action.id)
            ? [...state.reviewedOldIds, action.id]
            : state.reviewedOldIds;
          if (state.labels[action.id] === action.label) {
            state = {
              ...state,
              reviewedOldIds,
              notice: state.phase === 'repair' ? 'Метка подтверждена.' : 'Метка не изменилась.'
            };
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
            reviewedOldIds: state.phase === 'labels' ? [] : reviewedOldIds,
            notice: state.baseline ? 'Метки изменились. Повтори проверку модели.' : ''
          };
          break;
        }

        case 'SET_ARCHITECTURE': {
          requirePhase('review');
          const architecture = String(action.architecture);
          if (!architectureInfo(architecture)) {
            throw new Error('Такая схема не входит в подготовленный опыт.');
          }
          if (!state.repairCheckedLabelKey || state.repairCheckedLabelKey !== signature(state.labels)) {
            throw new Error('Сначала проверь старые метки и повтори проверку.');
          }
          if (state.architecture === architecture) {
            state = { ...state, notice: 'Архитектура модели не изменилась.' };
            break;
          }

          state = {
            ...state,
            architecture,
            architectureBaseline: state.current || state.architectureBaseline,
            current: null,
            modelSettings: true,
            notice: 'Архитектура модели изменилась. Проверь её на тех же снимках.'
          };
          break;
        }

        case 'MODEL_SETTINGS':
          requirePhase('review');
          if (!state.repairCheckedLabelKey || state.repairCheckedLabelKey !== signature(state.labels)) {
            throw new Error('Сначала проверь старые метки и повтори проверку.');
          }
          state = {
            ...state,
            modelSettings: true,
            notice: 'Выбери архитектуру модели и повтори проверку.'
          };
          break;

        case 'RUN': {
          requirePhase('labels', 'review', 'repair');
          if (state.phase === 'repair' && !oldIds.every(id => state.reviewedOldIds.includes(id))) {
            throw new Error('Сначала подтверди метку на каждом старом снимке.');
          }
          const found = lookup(state.labels, state.architecture);
          const current = {
            labelKey: found.key,
            resultKey: found.run.key,
            architecture: found.architecture,
            result: found.run
          };
          const unchanged = state.current && state.current.resultKey === current.resultKey && state.current.architecture === current.architecture;
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
            notice: unchanged ? 'Метки и архитектура те же: показан тот же подготовленный опыт.' : ''
          };
          break;
        }

        case 'REPAIR':
          requirePhase('review', 'labels', 'repair');
          if (!state.baseline) throw new Error('Сначала проверь модель.');
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

    // Save inputs and result identities only. Restoring always resolves the
    // scientific answers from the verified table, never from browser storage.
    function serialize() {
      const reference = run => run ? { labelKey: run.labelKey, architecture: run.architecture } : null;
      return {
        schemaVersion: 1,
        datasetVersion: protocol.datasetVersion,
        protocolVersion: protocol.protocolVersion,
        state: {
          phase: state.phase, resumePhase: state.resumePhase,
          labels: { ...state.labels }, architecture: state.architecture,
          baseline: reference(state.baseline), current: reference(state.current),
          correctedReview: reference(state.correctedReview),
          architectureBaseline: reference(state.architectureBaseline),
          repairCheckedLabelKey: state.repairCheckedLabelKey,
          reviewedOldIds: [...state.reviewedOldIds],
          modelSettings: state.modelSettings, finalSeen: state.finalSeen
        }
      };
    }

    function restore(saved) {
      const fail = () => { throw new Error('Сохранённая смена несовместима с этой версией опыта. Начни новую смену.'); };
      if (!saved || saved.schemaVersion !== 1 || saved.datasetVersion !== protocol.datasetVersion ||
          saved.protocolVersion !== protocol.protocolVersion) fail();
      const input = saved.state;
      if (!input || !phases.includes(input.phase) || !phases.includes(input.resumePhase) ||
          input.resumePhase === 'intro' || !architectureInfo(input.architecture) ||
          !input.labels || Object.keys(input.labels).length !== editable.length ||
          editable.some(id => !Object.hasOwn(input.labels, id) ||
            !(classes.includes(input.labels[id]) || childIds.includes(id) && input.labels[id] === null)) ||
          !Array.isArray(input.reviewedOldIds) || input.reviewedOldIds.some(id => !oldIds.includes(id)) ||
          new Set(input.reviewedOldIds).size !== input.reviewedOldIds.length ||
          typeof input.modelSettings !== 'boolean' || typeof input.finalSeen !== 'boolean') fail();
      const key = signature(input.labels);
      const reference = ref => {
        if (ref === null) return null;
        if (!ref || typeof ref.labelKey !== 'string' || ref.labelKey.length !== editable.length ||
            !architectureInfo(ref.architecture) || [...ref.labelKey].some(char => !/^[0-2]$/.test(char))) fail();
        const labels = Object.fromEntries(editable.map((id, i) => [id, classes[Number(ref.labelKey[i])]]));
        const selected = lookup(labels, ref.architecture);
        return { labelKey: selected.key, resultKey: selected.key, architecture: selected.architecture, result: selected.run };
      };
      const current = reference(input.current), baseline = reference(input.baseline);
      const correctedReview = reference(input.correctedReview), architectureBaseline = reference(input.architectureBaseline);
      if (current && (current.labelKey !== key || current.architecture !== input.architecture)) fail();
      if (input.repairCheckedLabelKey !== null &&
          (input.repairCheckedLabelKey !== key || input.reviewedOldIds.length !== oldIds.length)) fail();
      const effectivePhase = input.phase === 'intro' ? input.resumePhase : input.phase;
      if (['review', 'repair', 'final'].includes(effectivePhase) && (!key || !baseline)) fail();
      if (effectivePhase === 'final' && (!current || input.repairCheckedLabelKey !== key || !input.finalSeen)) fail();
      if (input.modelSettings && (effectivePhase !== 'review' || input.repairCheckedLabelKey !== key)) fail();
      if (correctedReview && correctedReview.labelKey !== key || architectureBaseline && architectureBaseline.labelKey !== key) fail();
      state = {
        ...fresh(), ...input, labels: { ...input.labels }, reviewedOldIds: [...input.reviewedOldIds],
        labelKey: key, current, baseline, correctedReview, architectureBaseline,
        phase: 'intro', resumePhase: effectivePhase, notice: 'Смена восстановлена. Можно продолжить.'
      };
      return snapshot();
    }

    return {
      get state() {
        return snapshot();
      },
      dispatch,
      serialize,
      restore,
      protocol
    };
  }

  root.GalaxyCNNLesson = { create };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = root.GalaxyCNNLesson;
  }
})(typeof globalThis !== 'undefined' ? globalThis : window);
