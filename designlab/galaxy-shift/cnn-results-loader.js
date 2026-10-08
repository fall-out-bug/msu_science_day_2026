/* Static scripts keep the same lazy-loading path on HTTPS and file://. */
(function(root) {
  'use strict';
  const loaded = new Map(), records = new Map();
  function register(id, payload) {
    const table = root.GALAXY_CNN_EXPERIMENTS, config = root.GalaxyArchitectures?.get(id);
    if (!table || !config || !payload || payload.architectureId !== id || !payload.protocol || !payload.experiments) throw new Error('Некорректный файл результатов CNN.');
    for (const field of ['protocolSha256','cnnPrepareSha256','generatorSha256']) {
      if (!payload.source || typeof payload.source[field] !== 'string' || payload.source[field] !== table.source?.[field]) throw new Error('Результаты относятся к другой версии расчётного кода.');
    }
    for (const field of ['protocolVersion','datasetVersion','classes','editableIds','trainingIds','reviewIds','finalIds']) {
      if (JSON.stringify(payload.protocol[field]) !== JSON.stringify(table.protocol[field])) throw new Error('Версия результатов CNN не совпадает с основной таблицей.');
    }
    const keys = Object.keys(table.experiments);
    if (Object.keys(payload.experiments).length !== keys.length) throw new Error('Файл результатов CNN неполный.');
    for (const key of keys) {
      const run = payload.experiments[key];
      if (!run || run.key !== key || run.architectureId !== id || run.blocks !== config.depth) throw new Error('Неверная строка результатов CNN.');
    }
    // Admit the entire shard before publishing any of its rows.
    for (const key of keys) table.experiments[key].architectures[id] = payload.experiments[key];
    records.set(id,payload);
  }
  function ensure(id) {
    if (!root.GalaxyArchitectures?.get(id)) return Promise.reject(new Error('Такая архитектура не входит в подготовленный опыт.'));
    if (records.has(id)) return Promise.resolve(records.get(id));
    if (id === 'd1-r') {
      const table = root.GALAXY_CNN_EXPERIMENTS;
      try {
        register(id,{architectureId:id,protocol:table.protocol,source:table.source,experiments:Object.fromEntries(Object.entries(table.experiments).map(([key,row])=>[key,row.architectures[id]]))});
        return Promise.resolve(records.get(id));
      } catch(error) { return Promise.reject(error); }
    }
    if (loaded.has(id)) return loaded.get(id);
    const promise = new Promise((resolve,reject) => {
      const script = document.createElement('script');
      let settled = false;
      const finish = error => {
        if (settled) return;
        settled = true; clearTimeout(timeout); script.onload = script.onerror = null; script.remove();
        if (error) { loaded.delete(id); reject(error); }
        else resolve(records.get(id));
      };
      const timeout = setTimeout(()=>finish(new Error('Истекло время загрузки результатов. Повтори проверку.')),15000);
      script.src = `cnn-results/${encodeURIComponent(id)}.js`; script.async = true;
      script.onload = () => finish(records.has(id) ? null : new Error('Файл не содержит результатов этой архитектуры.'));
      script.onerror = () => finish(new Error('Не удалось открыть результаты архитектуры. Повтори проверку или распакуй архив целиком.'));
      document.head.append(script);
    });
    loaded.set(id,promise);
    return promise;
  }
  root.GalaxyCNNResults = Object.freeze({register,ensure,get:id=>records.get(id)||null});
})(globalThis);
