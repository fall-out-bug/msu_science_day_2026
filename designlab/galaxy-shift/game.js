(async function () {
  "use strict";
  const data = globalThis.GALAXY_DATA,
    archiveData = globalThis.GALAXY_ARCHIVE;
  const root = document.querySelector("#game");
  if (document.body.dataset.coreResourceFailure) return;
  if (!data || !archiveData) {
    globalThis.galaxyCoreFailure?.();
    return;
  }
  let model;
  const byId = Object.fromEntries(
    [...data.images, ...archiveData.images].map((image) => [image.id, image]),
  );
  const found = new Set();
  try {
    model = GalaxyCNNLesson.create(data, globalThis.GALAXY_CNN_EXPERIMENTS);
  } catch (error) {
    globalThis.galaxyCoreFailure?.();
    return;
  }
  let journey = "welcome",
    cardIndex = 0,
    quest = null,
    modal = null,
    modalTrigger = null,
    sky = null;
  let cnnImageId = null, cnnImageRequest = 0;
  let running = false, restoredJourney = null, lastScreen = null, restoreWarning = null;
  const telemetryMeta = {gameVersion: GALAXY_BUILD_VERSION, protocolVersion: model.protocol.protocolVersion};
  function eventRecord(type, detail = {}) { try { GalaxyTelemetry.record(type, detail); } catch (_) {} }
  function persist() { GalaxyLessonStorage.write(model.serialize(), {journey,cardIndex,found:[...found]}); }
  const esc = (value) =>
    String(value).replace(
      /[&<>"']/g,
      (char) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[char],
    );
  const classLabel = (id) =>
    data.classes.find((item) => item.id === id)?.label || id;
  const architectureCatalog = () => globalThis.GalaxyArchitectures?.configurations || [];
  const architectureById = (id) => globalThis.GalaxyArchitectures?.get?.(id)
    || architectureCatalog().find((item) => item.id === id);
  const architectureLabel = (id) => architectureById(id)?.label || id;
  const source = (image) =>
    `<p class="source">${esc(image.credit)} · <a href="${esc(image.source)}" target="_blank" rel="noreferrer">Источник снимка ↗</a></p>`;
  function mentor(text, mood = "warm", opening = false, portrait = !opening) {
    return `<aside class="mentor${opening ? " room-dialogue" : ""}">${!portrait ? "" : `<span class="mentor-portrait"><img src="assets/art/nika-${mood}-v1.png" alt="Ника, астроном"></span>`}<div><span class="speaker">НИКА <i>астроном</i></span><p>${text}</p></div></aside>`;
  }
  let soundEnabled = false,
    audio = null;
  function chime() {
    if (!soundEnabled) return;
    audio ||= new (window.AudioContext || window.webkitAudioContext)();
    audio.resume();
    [440, 660].forEach((frequency, index) => {
      const oscillator = audio.createOscillator(),
        gain = audio.createGain();
      oscillator.type = "sine";
      oscillator.frequency.value = frequency;
      gain.gain.setValueAtTime(0, audio.currentTime + index * 0.075);
      gain.gain.linearRampToValueAtTime(
        0.035,
        audio.currentTime + index * 0.075 + 0.01,
      );
      gain.gain.exponentialRampToValueAtTime(
        0.001,
        audio.currentTime + index * 0.075 + 0.22,
      );
      oscillator.connect(gain);
      gain.connect(audio.destination);
      oscillator.start(audio.currentTime + index * 0.075);
      oscillator.stop(audio.currentTime + index * 0.075 + 0.23);
    });
  }
  function nav() {
    const free = journey === "free" || model.state.phase === "final";
    return `<header class="hud"><div class="top-actions"><button class="quiet sound" data-action="sound" aria-pressed="${soundEnabled}" aria-label="${soundEnabled ? "Выключить" : "Включить"} звук">${soundEnabled ? "Звук вкл." : "Звук выкл."}</button>${free ? '<button class="quiet" data-action="sky">Открытия на небе</button>' : ""}<button class="quiet" data-action="about">О проекте</button>${model.state.phase !== "intro" ? '<button class="quiet" data-action="home">↗ Обсерватория</button>' : ""}</div></header>`;
  }
  function photo(image) {
    return `<figure class="galaxy-frame"><img src="${esc(image.src)}" alt="${esc(image.name)}"><figcaption><span>HUBBLE · ${esc(image.name)}</span><button class="zoom" data-action="zoom" data-image-id="${esc(image.id)}" aria-label="Открыть снимок ${esc(image.name)}">⤢</button></figcaption></figure>`;
  }
  function progress(phase) {
    const compared = phase === 'review' && model.state.repairCheckedLabelKey === model.state.labelKey;
    const current = compared ? 'compare' : phase;
    const steps = [
      ['tutorial','Пример'],['labels','Разметка'],['review','Проверка'],
      ['repair','Старые метки'],['compare',(model.state.modelSettings || !["intro","complete"].includes(model.state.cnnGuide)) ? 'Архитектура' : 'Сравнение'],['final','Итог'],
    ];
    const active = Math.max(0, steps.findIndex(item => item[0] === current));
    return `<ol class="progress" aria-label="Ход опыта">${steps.map(([id,name],index) => `<li class="${index === active ? 'active' : index < active ? 'done' : ''}" ${index === active ? 'aria-current="step"' : ''}><span>${index < active ? '✓' : index + 1}</span><b>${name}</b></li>`).join('')}</ol>`;
  }
  function intro() {
    const resumed =
      model.state.resumePhase !== "tutorial" ||
      found.size ||
      model.state.baseline;
    return `<section class="room opening-room">${nav()}<h1 class="opening-title" tabindex="-1">Ночь открытий<span>Приключение в обсерватории</span></h1><div class="opening-speech">${mentor(resumed ? "Снимки и твои метки остались на столе. Продолжим?" : "Привет, я Ника! Поможешь мне научить модель различать галактики? Начнём за компьютером.", "warm", true)}</div><div class="opening-computer"><button class="primary" data-action="${resumed ? "resume" : "start-route"}">${resumed ? "Продолжить" : "Помочь Нике"}</button>${resumed ? '<button class="secondary" data-action="reset">Новая смена</button>' : ""}</div></section>`;
  }
  function story() {
    const ready = found.size === data.childIds.length,
      astronomy = GalaxyAstronomy.cases[0];
    return `<section class="room route-story">${nav()}<article class="route-story__card">
      <header><span class="eyebrow">ИИ В АСТРОНОМИИ</span><h1 tabindex="-1">${esc(astronomy.title)}</h1></header>
      <div class="route-story__body">
        <section class="route-story__example"><p>В проекте Euclid Galaxy Zoo люди отмечают форму галактик на снимках телескопа Euclid. На этих примерах модель ZooBot учится разбирать похожие галактики. Неуверенные ответы проверяют люди.</p><p class="source">${esc(astronomy.sourceLabel)} · <a href="${esc(astronomy.sourceURL)}" target="_blank" rel="noreferrer">Источник ↗</a></p></section>
        <section class="route-story__terms" aria-label="Понятия для нашего опыта"><p><b>Искусственный интеллект (ИИ)</b> — область создания систем для таких задач, как распознавание изображений.</p><p><b>Машинное обучение</b> — подход к ИИ: модель учится на примерах.</p><p>В <b>Data Science (DS), науке о данных</b>, ставят вопросы, готовят данные и проверяют выводы.</p></section>
      </div>
      <footer class="route-story__next">${mentor(ready ? "Все четыре снимка собраны. Теперь разметим один пример вместе." : found.size ? `Собрано ${found.size} из ${data.childIds.length} снимков. Вернёмся к карте и закончим.` : "Найдём четыре архивных снимка. Затем ты разметишь их и проверишь ответы модели.", "curious", false, false)}<button class="primary" data-action="${ready ? "complete-collection" : "collect-map"}">${ready ? "К рабочему столу" : "Найти галактики на карте"} <span>→</span></button></footer>
    </article></section>`;
  }
  function station(title, kicker, phase, body, footer = "") {
    return `<section class="workbench${body.includes('id="quest-scene"') ? " workbench--quest" : body.includes('class="cnn-workbench') ? " workbench--cnn" : ""}">${nav()}${progress(phase)}<div class="station"><div class="station-head"><div><span class="eyebrow">${kicker}</span><h1 tabindex="-1">${title}</h1></div></div>${body}${footer}</div></section>`;
  }
  function tutorial() {
    const image = byId[data.tutorialId];
    return station(
      "Разберём один снимок",
      "ПРОБУЕМ РАЗМЕТКУ",
      "tutorial",
      `<div id="quest-scene" data-image-id="${image.id}"></div><div class="navigation tutorial-navigation"><button class="secondary" data-action="zoom" data-image-id="${image.id}">Открыть снимок</button><button class="primary" data-action="labels">Перейти к разметке →</button></div><details class="credits"><summary>Источник снимка</summary>${source(image)}</details>`,
    );
  }
  function labels() {
    const state = model.state,
      ids = data.childIds,
      image = byId[ids[cardIndex]],
      missing = ids.filter((id) => !state.labels[id]).length;
    return station(
      "Разметим учебные примеры",
      "РАЗМЕЧАЕМ · " + (cardIndex + 1) + " ИЗ " + ids.length,
      "labels",
      `${programBar()}<div id="quest-scene" data-image-id="${image.id}"></div><div class="film-footer">${samples(ids)}<div class="navigation"><button class="secondary" data-action="previous" ${cardIndex === 0 ? "disabled" : ""}>←</button><button class="secondary" data-action="next" ${cardIndex === ids.length - 1 ? "disabled" : ""}>Следующий →</button><button class="primary" data-action="run" ${missing ? "disabled" : ""}>${missing ? "Поставь все метки" : "Проверить на других снимках"} →</button></div></div><details class="credits"><summary>О метках</summary>${source(image)}<p>Снимки с метками составляют обучающую выборку — примеры, на которых учится модель. Для всех вариантов меток обучение выполнено заранее; здесь открывается соответствующий результат.</p></details>`,
    );
  }
  function samples(ids) {
    return `<div class="samples">${ids.map((id, index) => `<button data-action="sample" data-index="${index}" aria-label="Снимок ${index + 1}: ${esc(byId[id].name)}" class="sample ${index === cardIndex ? "selected" : ""}" aria-current="${index === cardIndex}"><img src="${esc(byId[id].src)}" alt=""><span>${index + 1}</span><i>${(model.state.phase === "repair" ? model.state.reviewedOldIds?.includes(id) : model.state.labels[id]) ? "✓" : "·"}</i></button>`).join("")}</div>`;
  }
  function programBar() {
    const state = model.state,
      canChange =
        state.phase === "review" &&
        state.repairCheckedLabelKey === state.labelKey && state.cnnGuide === "complete";
    const folder = '<button class="program-quiet" data-action="folder">Обучающая выборка: 9 снимков</button>';
    if (state.phase === "labels" || state.phase === "repair") return `<section class="cnn-programs" aria-label="Справочные материалы">${folder}</section>`;
    return `<section class="cnn-programs" aria-label="Навигация опыта"><button data-action="labels">Вернуться к разметке</button>${canChange ? '<button data-action="model-settings">Конструктор сети</button>' : ""}${folder}</section>`;
  }
  function metricDetails(run, scope = 'review') {
    const result = run[scope], classes = data.classes.map(item => item.id);
    const metrics = GalaxyMetrics.calculate(result.predictions, classes);
    const format = value => value === null ? "не определено" : value.toFixed(2).replace(".", ",");
    return `<details class="metrics" data-metric-scope="${scope}"><summary>Как оценивают классификацию</summary><p><b>${scope === 'final' ? 'Итоговая' : 'Проверочная'} выборка: ${result.total} снимка.</b> Доля правильных ответов (accuracy): ${result.correct}/${result.total} = ${format(metrics.accuracy)}. Это результат на этой выборке; её недостаточно для надёжной оценки качества модели на других галактиках.</p><h3>Матрица ошибок</h3><p>Строка — справочная метка, столбец — предсказание модели. Числа на диагонали показывают совпадения.</p><table class="metric-table"><thead><tr><th scope="col">Справочная метка / предсказание</th>${classes.map(id => `<th scope="col">${esc(classLabel(id))}</th>`).join('')}</tr></thead><tbody>${classes.map((id, row) => `<tr><th scope="row">${esc(classLabel(id))}</th>${metrics.matrix[row].map(value => `<td>${value}</td>`).join('')}</tr>`).join('')}</tbody></table><p>Для каждого класса TP — верные предсказания этого класса, FP — ошибочно отнесённые к нему снимки, FN — его пропущенные снимки.</p><dl><dt>Точность (precision) = TP / (TP + FP)</dt><dd>Какая доля снимков, отнесённых моделью к классу, действительно к нему относится.</dd><dt>Полнота (recall) = TP / (TP + FN)</dt><dd>Какую долю снимков класса модель нашла.</dd><dt>F1 = 2TP / (2TP + FP + FN)</dt><dd>Объединяет точность и полноту в одном показателе.</dd></dl><ul>${metrics.perClass.map(item => `<li><b>${esc(classLabel(item.id))}</b>: TP ${item.tp}, FP ${item.fp}, FN ${item.fn}; precision ${format(item.precision)}, recall ${format(item.recall)}, F1 ${format(item.f1)}.</li>`).join('')}</ul><p><b>Macro-F1: ${format(metrics.macroF1)}</b> — среднее F1 трёх классов с одинаковым весом. При нулевом знаменателе соответствующий показатель не определён. Для Macro-F1 неопределённое F1 учитывается как 0; состав классов остаётся тем же.</p></details>`;
  }
  const layerNotes = {
    r: ['ReLU', 'ReLU — функция активации: она заменяет отрицательные значения нулями. Это позволяет сети описывать нелинейные зависимости.'],
    bn: ['BatchNorm', 'BatchNorm (пакетная нормализация) нормализует значения по статистикам обучающего пакета; при проверке использует накопленные статистики обучения. У слоя есть обучаемые параметры масштаба и сдвига.'],
    d: ['Dropout', 'Dropout при обучении случайно обнуляет 20% значений и увеличивает оставшиеся в 1 / 0,8 раза. При проверке Dropout не изменяет значения. Его добавление не гарантирует улучшения результата.'],
  };
  function architectureEditor(state) {
    return station('Как сеть различает галактики', 'СНИМОК → СЕТЬ → ПРЕДСКАЗАНИЕ', 'review',
      GalaxyCNNGuide.render(state, {data, byId, activeImageId: cnnImageId}));
  }
  function updateArchitectureView(prepared = null, decodedPhoto = null) {
    const nextSurface = prepared || document.createElement('div');
    if (!prepared) nextSurface.innerHTML = architectureEditor(model.state);
    const fresh = nextSurface.querySelector('.cnn-workbench');
    if (decodedPhoto) {
      const nextImage = fresh.querySelector('.cnn-workbench__frame img');
      decodedPhoto.alt = nextImage.alt;
      nextImage.replaceWith(decodedPhoto);
    }
    const workspace = root.querySelector('.cnn-workbench');
    const editor = workspace.querySelector('.architecture-editor');
    const nextEditor = fresh.querySelector('.architecture-editor');
    workspace.className = fresh.className;
    for (const [key, value] of Object.entries(fresh.dataset)) workspace.dataset[key] = value;
    editor.className = nextEditor.className;
    for (const [key, value] of Object.entries(nextEditor.dataset)) editor.dataset[key] = value;
    // Reuse photographs and portraits when their surrounding explanation changes.
    function syncRegion(current, next) {
      if (!current || !next || current.innerHTML === next.innerHTML) return;
      const images = [...current.querySelectorAll('img')];
      for (const img of next.querySelectorAll('img')) {
        const old = images.find(item => item.getAttribute('src') === img.getAttribute('src'));
        if (old) {
          images.splice(images.indexOf(old), 1);
          for (const attribute of [...old.attributes]) {
            if (!img.hasAttribute(attribute.name)) old.removeAttribute(attribute.name);
          }
          for (const attribute of img.attributes) {
            if (old.getAttribute(attribute.name) !== attribute.value) old.setAttribute(attribute.name, attribute.value);
          }
          img.replaceWith(old);
        }
      }
      const openDetails = new Set([...current.querySelectorAll('details[open]')].map(item => item.querySelector('summary')?.textContent));
      for (const details of next.querySelectorAll('details')) {
        if (openDetails.has(details.querySelector('summary')?.textContent)) details.open = true;
      }
      current.replaceChildren(...next.childNodes);
    }
    for (const button of editor.querySelectorAll('[data-action="architecture-depth"]')) {
      const next = nextEditor.querySelector(`[data-action="architecture-depth"][data-depth="${button.dataset.depth}"]`);
      button.className = next.className;
      button.disabled = next.disabled;
      button.setAttribute('aria-pressed', next.getAttribute('aria-pressed'));
    }
    syncRegion(editor.querySelector('.architecture-fixed'), nextEditor.querySelector('.architecture-fixed'));
    const list = editor.querySelector('[data-architecture-tail]');
    const nextList = nextEditor.querySelector('[data-architecture-tail]');
    for (const item of [...list.children]) {
      if (!nextList.querySelector(`[data-layer="${item.dataset.layer}"]`)) item.remove();
    }
    for (const next of [...nextList.children]) {
      let item = list.querySelector(`[data-layer="${next.dataset.layer}"]`);
      if (!item) item = next;
      else {
        item.dataset.layerIndex = next.dataset.layerIndex;
        item.setAttribute('aria-label', next.getAttribute('aria-label'));
        item.draggable = next.draggable;
        item.tabIndex = next.tabIndex;
        for (const button of item.querySelectorAll('button')) {
          const nextButton = next.querySelector(`[data-action="${button.dataset.action}"]`);
          button.disabled = nextButton.disabled;
          if (nextButton.dataset.layerIndex !== undefined) button.dataset.layerIndex = nextButton.dataset.layerIndex;
        }
      }
      const index = Number(next.dataset.layerIndex);
      if (list.children[index] !== item) list.insertBefore(item, list.children[index] || null);
    }
    for (const button of editor.querySelectorAll('[data-action="layer-add"]')) {
      button.disabled = nextEditor.querySelector(`[data-action="layer-add"][data-layer="${button.dataset.layer}"]`).disabled;
    }
    syncRegion(editor.querySelector('.architecture-current'), nextEditor.querySelector('.architecture-current'));
    const guideAction = editor.querySelector('[data-action="guide-add-convolution"]');
    if (guideAction && !nextEditor.querySelector('[data-action="guide-add-convolution"]')) guideAction.remove();
    for (const region of workspace.querySelectorAll('[data-cnn-region]:not(.architecture-editor)')) {
      if (region.dataset.cnnRegion === 'photo') {
        const next = fresh.querySelector('[data-cnn-region="photo"]');
        const oldImage = region.querySelector('.cnn-workbench__frame img');
        const nextImage = next.querySelector('.cnn-workbench__frame img');
        if (oldImage.getAttribute('src') !== nextImage.getAttribute('src')) oldImage.replaceWith(nextImage);
        else oldImage.alt = nextImage.alt;
        syncRegion(region.querySelector('figcaption'), next.querySelector('figcaption'));
        const open = region.querySelector('.cnn-workbench__open'), nextOpen = next.querySelector('.cnn-workbench__open');
        open.dataset.imageId = nextOpen.dataset.imageId;
        open.setAttribute('aria-label', nextOpen.getAttribute('aria-label'));
        for (const button of region.querySelectorAll('[data-action="cnn-image"]')) {
          const nextButton = next.querySelector(`[data-image-id="${button.dataset.imageId}"][data-action="cnn-image"]`);
          button.className = nextButton.className;
          button.setAttribute('aria-pressed', nextButton.getAttribute('aria-pressed'));
        }
        continue;
      }
      syncRegion(region, fresh.querySelector(`[data-cnn-region="${region.dataset.cnnRegion}"]`));
    }
    persist();
  }
  function selectArchitecture(depth, tail) {
    const active = document.activeElement;
    const action = active?.dataset.action, layer = active?.closest("li[data-layer]")?.dataset.layer, depthButton = active?.dataset.depth;
    const next = globalThis.GalaxyArchitectures?.find?.(depth, tail)
      || architectureCatalog().find(item => item.depth === depth && (item.tail || []).join("|") === tail.join("|"));
    if (!next) return;
    dispatch("SET_ARCHITECTURE", { architecture: next.id });
    const nextLayer = layer && root.querySelector(`li[data-layer="${layer}"]`);
    const target = nextLayer?.querySelector(`[data-action="${action}"]:not(:disabled)`) || nextLayer ||
      root.querySelector(`[data-action="${action}"]${depthButton ? `[data-depth="${depthButton}"]` : ':not(:disabled)'}`) || root.querySelector('[data-action="architecture-save"]');
    target?.focus({preventScroll:true});
  }
  function resultCard(prediction, previous = null) {
    const image = byId[prediction.id],
      ok = prediction.predicted === prediction.expected;
    return `<article class="result ${ok ? "correct" : "incorrect"}">${photo(image)}<div class="result-info"><div class="result-name"><b>${esc(image.name)}</b><span>${ok ? "Совпало ✓" : "Проверим ?"}</span></div><p>${previous ? `До: <strong>${esc(classLabel(previous.predicted))}</strong><br>После` : "Модель"}: <strong>${esc(classLabel(prediction.predicted))}</strong>${previous ? `<br><small>${previous.predicted === prediction.predicted ? "Ответ не изменился" : "Ответ изменился"}</small>` : ""}</p><p class="reference">Справочная метка: ${esc(classLabel(prediction.expected))}</p><button class="text-button" data-action="talk" data-image-id="${esc(image.id)}">Обсудить с Никой →</button></div></article>`;
  }
  function review() {
    const state = model.state,
      baseline = state.baseline,
      corrected = state.correctedReview;
    const checked = state.repairCheckedLabelKey === state.labelKey && Boolean(state.labelKey);
    if (checked || state.modelSettings || !state.current) return architectureEditor(state);
    const run = state.current.result;
    const remaining = run.review.total - run.review.correct;
    const nextStep = `<section class="review-next" aria-label="Следующий шаг"><p>Сначала проверим старые метки в обучающей выборке: ошибки в них могут повлиять на ответы модели.</p><button class="primary" data-action="repair">Проверить старые метки →</button></section>`;
    const previous = state.architectureBaseline?.labelKey === state.current.labelKey
      ? state.architectureBaseline : corrected && baseline ? baseline : null;
    let compare = '';
    if (previous) {
      const changed = run.review.predictions.filter(prediction => prediction.predicted !== previous.result.review.predictions.find(item => item.id === prediction.id)?.predicted).length;
      const difference = run.review.correct - previous.result.review.correct;
      const inputs = previous.labelKey !== state.current.labelKey;
      const architecture = previous.architecture !== state.current.architecture;
      const cause = inputs && architecture ? 'Изменены и метки, и архитектура: их влияние здесь нельзя разделить.'
        : architecture ? 'Метки те же; изменена архитектура.'
          : inputs ? 'Архитектура та же; изменены метки обучающих снимков.'
            : 'Метки и архитектура те же.';
      const outcome = difference > 0 ? `Правильных ответов стало больше: ${previous.result.review.correct} → ${run.review.correct}.`
        : difference < 0 ? `Правильных ответов стало меньше: ${previous.result.review.correct} → ${run.review.correct}. Изменение не гарантирует улучшения.`
          : `Число правильных ответов не изменилось: ${run.review.correct} из ${run.review.total}.`;
      compare = `<p class="callout" data-comparison><b>До и после на тех же проверочных снимках.</b> ${cause} ${changed ? `Изменилось ответов: ${changed} из ${run.review.total}.` : 'Предсказания не изменились.'} ${outcome}</p>`;
    }
    return station(
      "Проверим ответы модели",
      "ОБУЧЕНИЕ И ПРОВЕРКА",
      "review",
      `${programBar()}<div class="score-strip"><span>На проверочной выборке верно классифицировано <b>${run.review.correct}<small> / ${run.review.total}</small></b></span><p>Это результат модели, а не оценка тебе.<br>Архитектура: ${esc(architectureLabel(state.architecture))}.<br>Обучение выполнено заранее для твоих меток.</p></div>${state.notice ? `<p class="callout">${esc(state.notice)}</p>` : ""}${compare}${nextStep}<div class="result-grid">${run.review.predictions.map(prediction => resultCard(prediction, previous?.result.review.predictions.find(item => item.id === prediction.id))).join("")}</div>${metricDetails(run)}<div class="navigation result-nav"><button class="secondary" data-action="labels">← Разметить снимки</button><div><button class="secondary" data-action="repair">Вернуться к старым меткам</button></div></div>`,
    );
  }
  function repair() {
    const state = model.state,
      ids = data.oldIds,
      image = byId[ids[cardIndex]];
    return station(
      "Проверим старые метки",
      "ПРОВЕРЯЕМ СТАРЫЕ МЕТКИ · " + (cardIndex + 1) + " ИЗ " + ids.length,
      "repair",
      `${programBar()}<div id="quest-scene" data-image-id="${image.id}"></div><div class="film-footer">${samples(ids)}<div class="navigation"><button class="secondary" data-action="previous" ${cardIndex === 0 ? "disabled" : ""}>←</button><button class="secondary" data-action="next" ${cardIndex === ids.length - 1 ? "disabled" : ""}>Следующий →</button><button class="primary" data-action="run" ${ids.some(id => !state.reviewedOldIds?.includes(id)) ? "disabled" : ""}>${ids.some(id => !state.reviewedOldIds?.includes(id)) ? "Проверь все старые метки" : "Повторить проверку →"}</button></div></div>`,
    );
  }
  function final() {
    const state = model.state,
      run = state.current.result,
      initial = state.baseline.result;
    return `<section class="room final-room">${nav()}<section class="final-summary"><span class="eyebrow">СМЕНА ЗАВЕРШЕНА</span><h1 tabindex="-1">Ты проверил ответы модели</h1><p class="final-result">Совпадений со справочными метками на итоговой выборке: <b>${run.final.correct} из ${run.final.total}</b>.</p>${mentor("Ты собрал архивные снимки, разметил обучающую выборку и проверил предсказания. Ещё ты изменил устройство сети и сравнил ответы на тех же данных. Так работают с данными в Data Science — науке о данных: ставят вопрос, готовят данные и проверяют выводы. Трёх итоговых снимков мало, чтобы судить о качестве модели на других галактиках.", "warm", false, false)}<div class="navigation"><button class="primary" data-action="sky">Исследовать звёздное небо →</button><button class="secondary" data-action="reset">Новая смена</button></div></section><details class="research-board"><summary><span class="eyebrow">ДОСКА ИССЛЕДОВАНИЙ</span><b>Результаты и метрики</b></summary><div class="board-score-summary"><section data-score-scope="review-before"><span>Первая проверка: ${esc(architectureLabel(state.baseline.architecture))}</span><b>${initial.review.correct} из ${initial.review.total}</b></section><section data-score-scope="review-after"><span>Текущая проверка: ${esc(architectureLabel(state.current.architecture))}</span><b>${run.review.correct} из ${run.review.total}</b></section><section class="board-final-score" data-score-scope="final"><span>На итоговой выборке</span><b>${run.final.correct} из ${run.final.total}</b></section></div><div class="result-grid">${run.final.predictions.map(prediction => resultCard(prediction)).join("")}</div>${metricDetails(run, "final")}<p class="final-note">Итоговая выборка не участвовала в обучении, но уже изучалась авторами; она не доказывает качество модели на всех других данных. ${esc(state.notice)}</p><div class="navigation"><button class="secondary" data-action="labels">Вернуться к примерам</button></div></details></section>`;
  }
  function folder() {
    const state = model.state,
      editable = new Set(model.protocol.editableIds);
    return `<section class="folder-panel"><h2>Обучающая выборка: 9 снимков</h2><p>Все девять снимков с метками используются при обучении. Новых снимков для разметки: ${data.childIds.length}; старых меток для проверки: ${data.oldIds.length}. Остальные ${model.protocol.trainingIds.length - model.protocol.editableIds.length} метки подготовлены авторами.</p><div class="folder-grid">${model.protocol.trainingIds
      .map((id) => {
        const image = byId[id],
          current = state.labels[id] ?? (editable.has(id) ? null : image.label);
        return `<article>${photo(image)}<b>${esc(image.name)}</b><span>${current ? esc(classLabel(current)) : "Без метки"}${editable.has(id) ? " · можно проверить" : ""}</span><button class="text-button" data-action="zoom" data-image-id="${esc(id)}">Открыть снимок</button></article>`;
      })
      .join("")}</div></section>`;
  }
  const categories = {
    discovery: "Открытия с ИИ",
    object: "Объекты",
    image: "Снимки",
    research: "Исследования",
  };
  function journal() {
    return `<span class="eyebrow">ДОСКА ИССЛЕДОВАНИЙ</span><h2>Как научить модель — и проверить её</h2><div class="journal-steps"><p><b>01 · Наблюдаем.</b> Что видно на снимке?</p><p><b>02 · Собираем данные.</b> Снимок с меткой — учебный пример для модели.</p><p><b>03 · Проверяем.</b> Смотрим её ответы на других снимках.</p><p><b>04 · Исследуем ошибку.</b> Проверяем метки учебных примеров.</p><p><b>05 · Сравниваем.</b> Видим, какие ответы действительно изменились.</p></div><p>${esc(GalaxyAstronomy.afterExperience.text)}</p><button class="primary" data-action="astronomy">Где это применяют в астрономии?</button>`;
  }
  function archiveImage(id) {
    const image = byId[id];
    if (!image) return;
    openModal(
      `<span class="eyebrow">АРХИВ HUBBLE</span><h2>${esc(image.name)}</h2>${photo(image)}<p>${esc(image.explanation)}</p>${source(image)}<button class="text-button" data-action="talk" data-image-id="${esc(image.id)}">Рассмотреть с Никой →</button><button class="secondary" data-action="return-sky">Вернуться к небу</button>`,
    );
  }
  function discovery(id) {
    const item = GALAXY_DISCOVERIES.find((i) => i.id === id);
    if (!item) return;
    openModal(
      `<span class="eyebrow">${esc(categories[item.category])} · ${esc(item.date || "")}</span><h2>${esc(item.title)}</h2><figure class="discovery-figure"><img src="${esc(item.image)}" alt="${esc(item.alt)}"><figcaption>${esc(item.alt)}</figcaption></figure><p>${esc(item.text)}</p><p>${esc(item.detail)}</p><p class="note">${esc(item.locationNote)}${item.coordinateSource ? ` · <a href="${esc(item.coordinateSource.startsWith("https://") ? item.coordinateSource : "https://simbad.cds.unistra.fr/simbad/sim-id?Ident=" + encodeURIComponent(item.coordinateSource.replace(/^SIMBAD: /, "")))}" target="_blank" rel="noreferrer">Координаты ↗</a>` : ""}</p><p class="source">${esc(item.credit)} · <a href="${esc(item.imageSource)}" target="_blank" rel="noreferrer">Источник изображения ↗</a> · <a href="${esc(item.source)}" target="_blank" rel="noreferrer">Исследование ↗</a></p><div class="photo-companion">${mentor("Можем обсудить содержание карточки, изображение и ограничения выводов.", "curious")}<button class="text-button" data-action="talk" data-story-id="${esc(item.id)}">Поговорить с Никой →</button></div><button class="secondary" data-action="return-sky">Вернуться к небу</button>`,
    );
  }
  function openSky(target) {
    if (sky) return;
    closeModal();
    const guided = journey === "collect";
    eventRecord("phase_entered", {phase: guided ? "collect" : "free"});
    persist();
    root.inert = true;
    sky = GalaxySky.open({
      initialTarget: target,
      guided,
      taskIds: data.childIds,
      collectedIds: [...found],
      onSelect: (id) => archiveImage(id),
      onArchive: archiveImage,
      onDiscovery: discovery,
      onCollect: (id) => {
        if (!found.has(id)) eventRecord('map_target_collected', {imageId:id});
        found.add(id);
        persist();
      },
      onComplete: () => {
        journey = "work";
        sky = null;
        root.inert = false;
        cardIndex = 0;
        dispatch("START");
      },
      onClose: () => {
        if (journey === "collect") journey = "story";
        sky = null;
        root.inert = Boolean(modal);
        render();
        focusHeading();
      },
    });
  }
  function about() {
    return `<span class="eyebrow">О ПРОЕКТЕ</span><h2>Ночь открытий: приключение в обсерватории</h2><p>Игра «Ночь открытий: приключение в обсерватории» создана на <b>факультете искусственного интеллекта МГУ имени М. В. Ломоносова</b>. Факультет объединяет образование, научные исследования и практическое применение искусственного интеллекта. <a href="https://ai.msu.ru/" target="_blank" rel="noreferrer">О факультете ↗</a></p><p><b>Анастасия Колесникова</b> — магистрант факультета ИИ. Научное содержание и проверка фактов: чтобы галактики оставались галактиками.</p><p><b>Андрей Жуков</b> — преподаватель факультета ИИ. Техника и игровые механики: чтобы обсерватория открывалась, а кнопки делали обещанное.</p><p><b>GPT-6 Astra</b> — генеративный ИИ. Код, тексты и сборка. Работает без кофе, но под присмотром.</p><details><summary>Понятия из игры</summary><dl><dt>Искусственный интеллект (ИИ)</dt><dd>Область создания систем для таких задач, как распознавание изображений.</dd><dt>Машинное обучение</dt><dd>Подход к созданию моделей, которые учатся на примерах.</dd><dt>Data Science (DS), наука о данных</dt><dd>Работа с данными: постановка вопроса, сбор и подготовка данных, анализ и проверка выводов.</dd><dt>Класс, метка и разметка</dt><dd>Класс — категория снимков. Метка указывает выбранный для снимка класс; разметка — назначение таких меток.</dd><dt>Выборка</dt><dd>Набор примеров для определённой задачи. На обучающей выборке модель подбирает параметры, на проверочной мы сравниваем её предсказания со справочными метками.</dd><dt>Архитектура и слой</dt><dd>Архитектура задаёт устройство нейронной сети: типы и порядок слоёв. Каждый слой преобразует полученные данные.</dd></dl></details><h3>Что настоящее, а что учебное</h3><p>Галактики на снимках настоящие: архив NASA/ESA Hubble. Обсерватория и Ника — художественные иллюстрации. На карте показаны звёздный атлас NASA и координаты объектов. Мы открываем архивные снимки, а не делаем новые наблюдения.</p><p>В основном опыте девять учебных снимков. Можно менять метки новых снимков (${data.childIds.length}) и старые метки (${data.oldIds.length}). Мы используем свёрточные нейронные сети (CNN). Для каждого сочетания меток и всех 22 архитектур обучение выполнено заранее. Браузер открывает точный результат выбранного опыта; он не обучает модель заново.</p><p>В этом задании мы классифицируем снимки — относим их к трём категориям по видимым признакам. «Гладкая» означает плавное свечение без заметных рукавов. «Видна спираль» — заметны спиральные рукава. «Вид с ребра» — мы смотрим на диск сбоку. Это ракурс, а не отдельный тип галактики.</p><p>Разметка человека, ответ модели и справочная метка — разные вещи. Повторная проверка показывает изменения на знакомых снимках. Итоговые снимки не входят в обучение, но уже изучались авторами: это учебный опыт, не новая независимая оценка качества.</p><p>На сайте сохраняются обезличенные события прохождения: переходы, метки и запуски опытов. Они помогают находить непонятные места. Имена и контакты не собираются; записи удаляются через 30 дней. Автономная версия хранит журнал только в этой вкладке и ничего не отправляет.</p><button class="secondary" data-action="diagnostics">Для стендиста: журнал смены</button><p><a href="DATA-NOTES.md" target="_blank">Данные и метод ↗</a> · <a href="provenance.json" target="_blank">Источники ↗</a> · <a href="assets/art/ART-CREDITS.md" target="_blank">Иллюстрации ↗</a></p>`;
  }
  function openModal(content, isImage = false) {
    closeModal();
    modalTrigger = document.activeElement;
    modal = document.createElement("div");
    modal.className = "modal";
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    modal.setAttribute(
      "aria-label",
      isImage ? "Снимок галактики" : "Записи лаборатории",
    );
    modal.innerHTML = `<div class="modal-box${isImage ? " image-box" : ""}"><button class="secondary modal-close" data-action="close-modal">Закрыть ×</button>${content}</div>`;
    document.body.append(modal);
    root.inert = true;
    const atlas = document.querySelector(".sky-atlas");
    if (atlas) atlas.inert = true;
    modal.querySelector("button").focus();
  }
  function closeModal() {
    if (!modal) return;
    modal.remove();
    modal = null;
    root.inert = Boolean(sky);
    const atlas = document.querySelector(".sky-atlas");
    if (atlas) atlas.inert = false;
    if (modalTrigger?.isConnected) modalTrigger.focus();
  }
  function render(prepared = null) {
    if (document.body.dataset.coreResourceFailure) return;
    const phase = model.state.phase;
    quest?.destroy();
    quest = null;
    document.body.dataset.phase = phase;
    galaxyWorld.setPhase(phase);
    if (prepared) root.replaceChildren(prepared);
    else root.innerHTML =
      journey === "story"
        ? story()
        : phase === "intro"
          ? intro()
          : phase === "tutorial"
            ? tutorial()
            : phase === "labels"
              ? labels()
              : phase === "review"
                ? review()
                : phase === "repair"
                  ? repair()
                  : final();
    const host = root.querySelector("#quest-scene");
    if (host) {
      const image = byId[host.dataset.imageId];
      quest = QuestScene.mount(host, {
        image,
        phase,
        classes: data.classes,
        selected: phase === "repair" && !model.state.reviewedOldIds?.includes(image.id)
          ? null : model.state.labels[image.id],
        initialOldLabel:
          phase === "repair"
            ? classLabel(data.initialOldLabels[image.id])
            : null,
        opening:
          phase === "tutorial"
            ? "Класс — категория снимков с общими признаками. Метка класса указывает, к какому классу мы отнесли снимок. Разметка — назначение таких меток. Попробуем на одном примере: выбери класс по форме галактики."
            : phase === "repair"
              ? "В старой выборке тоже могут быть ошибки. Проверь подпись по снимку, затем повторим опыт."
              : "Обучающая выборка — снимки с метками, на которых учится модель. При обучении она подбирает параметры по этим примерам. Предсказания — предполагаемые классы других снимков. Проверочная выборка не участвует в обучении. Выбери метку этого снимка.",
        onLabel: (value) => choose(image.id, value),
      });
    }
    persist();
    const screen = journey === 'story' ? 'story' : phase === 'review' && root.querySelector('.cnn-workbench') ? 'model' : phase;
    if (screen !== lastScreen) { eventRecord('phase_entered', {phase:screen}); lastScreen = screen; }
    globalThis.galaxyGame = {
      model,
      render,
      get quest() {
        return quest;
      },
      get found() {
        return [...found];
      },
      get sky() {
        return sky;
      },
    };
  }
  function focusHeading() {
    const heading = root.querySelector("h1");
    heading?.focus({ preventScroll: true });
  }
  async function dispatch(type, payload = {}) {
    if (running) return;
    const before = model.serialize(), beforeJourney = journey;
    let advanced = false;
    try {
      if (type === 'RUN' || type === 'FINISH') {
        running = true;
        root.inert = true;
        const status = document.createElement('p');
        status.id = 'experience-loading'; status.className = 'cnn-run-status'; status.setAttribute('role', 'status');
        status.textContent = 'Открываем рассчитанный результат этой архитектуры…';
        document.body.append(status);
        if (type === 'RUN') await GalaxyCNNResults.ensure(model.state.architecture);
      }
      model.dispatch({ type, ...payload });
      advanced = true;
      const current = model.state;
      if (['SET_ARCHITECTURE', 'GUIDE_ADD_CONVOLUTION'].includes(type)) eventRecord('architecture_selected', {architecture:current.architecture});
      if (type === 'FINISH') journey = 'free';
      if (type === 'RESET') { GalaxyTelemetry.reset(telemetryMeta); lastScreen = null; restoreWarning = null; }
      if (type === 'RESUME') journey = current.phase === 'final' ? 'free' : 'work';
      if (type === "LABELS" || type === "REPAIR") cardIndex = 0;
      const sameWorkspace = root.querySelector('.cnn-workbench') && ['SET_ARCHITECTURE','GUIDE_ADD_CONVOLUTION','GUIDE_CONFIRM_COMPARE','MODEL_SETTINGS','RUN'].includes(type);
      if (sameWorkspace && type !== 'RUN') updateArchitectureView();
      else if (type === 'RUN' || type === 'FINISH') {
        // Decode the actual next image nodes before swapping surfaces. Recreating
        // even a cached <img> can otherwise leave one empty animation frame.
        const nextSurface = document.createElement('div');
        nextSurface.innerHTML = type === 'FINISH' ? final() : review();
        try { await Promise.all([...nextSurface.querySelectorAll('img')].map(img => img.decode())); }
        catch (_) { throw new Error('Не удалось загрузить снимок. Повтори действие; для автономной игры распакуй архив целиком.'); }
        const fragment = document.createDocumentFragment();
        fragment.append(...nextSurface.childNodes);
        if (sameWorkspace) {
          const next = document.createElement('div'); next.append(fragment);
          updateArchitectureView(next);
        } else render(fragment);
      } else render();
      if (type === 'RUN') {
        eventRecord('run_opened', {experimentKey:current.labelKey, architecture:current.architecture, scope:'review'});
        eventRecord('result_opened', {scope:'review',correct:current.current.result.review.correct,total:current.current.result.review.total});
      }
      if (type === 'FINISH') { eventRecord('final_opened'); eventRecord('result_opened',{scope:'final',correct:current.current.result.final.correct,total:current.current.result.final.total}); }
      root.inert = Boolean(modal || sky);
      chime();
      if (sameWorkspace) {
        const action = root.querySelector('[data-cnn-region="actions"] .primary:not(:disabled)');
        if (!["SET_ARCHITECTURE", "MODEL_SETTINGS"].includes(type)) action?.focus({preventScroll:true});
      } else if (!["SET_LABEL", "SET_ARCHITECTURE"].includes(type)) {
        window.scrollTo({ top: 0, behavior: "instant" });
        focusHeading();
      }
    } catch (error) {
      if (advanced && (type === 'RUN' || type === 'FINISH')) {
        model.restore(before);
        model.dispatch({type:'RESUME'});
        journey = beforeJourney;
      }
      eventRecord("known_error", {code:"invalid_response"});
      openModal(`<h2>Не удалось продолжить</h2><p>${esc(error.message)}</p><p>Закрой сообщение и повтори действие. Для автономной игры распакуй архив целиком.</p>`);
    } finally {
      running = false;
      document.querySelector('#experience-loading')?.remove();
      root.inert = Boolean(modal || sky);
    }
  }
  function talk(id, storyId) {
    const story = storyId
      ? GALAXY_DISCOVERIES.find((item) => item.id === storyId)
      : null;
    const image = story
      ? {
          id: story.id,
          name: story.title,
          src: story.image,
          explanation: story.text,
        }
      : byId[id];
    const current = model.state.current?.result;
    const prediction = [
      ...(current?.review.predictions || []),
      ...(current?.final.predictions || []),
    ].find((item) => item.id === id);
    eventRecord("help_opened");
    NikaDialogue.open({ image, story, phase: model.state.phase, prediction });
  }
  function choose(id, value) {
    if (sky || modal) return;
    try {
      // A label changes the answer, not the scene, photo or scroll position.
      const before = model.state.labels[id];
      model.dispatch({ type: "SET_LABEL", id, label: value });
      eventRecord(model.state.phase === 'repair' && before === value ? 'old_label_confirmed' : 'label_set',
        {imageId:id,after:value,...(before ? {before} : {})});
      persist();
      quest.updateSelection(value);
      const state = model.state;
      const ids = state.phase === "repair" ? data.oldIds : data.childIds;
      const answered = item => state.phase === "repair"
        ? state.reviewedOldIds?.includes(item) : Boolean(state.labels[item]);
      root.querySelectorAll('.sample').forEach((button, index) => {
        button.querySelector('i').textContent = answered(ids[index]) ? '✓' : '·';
      });
      const missing = ids.some(item => !answered(item));
      root.querySelectorAll('[data-action="run"]').forEach(button => {
        button.disabled = missing;
        if (!button.closest('.cnn-programs')) button.textContent = state.phase === "repair"
          ? (missing ? "Проверь все старые метки" : "Повторить проверку →")
          : (missing ? "Поставь все метки →" : "Проверить на других снимках →");
      });
      chime();
    } catch (error) {
      openModal(`<h2>Нужен ещё один шаг</h2><p>${esc(error.message)}</p>`);
    }
  }
  document.addEventListener("keydown", (event) => {
    if (!modal && model.state.phase === "review" && model.state.cnnGuide === "complete" && event.target.matches?.("[data-layer-index]") && (event.altKey || event.ctrlKey) && ["ArrowLeft", "ArrowRight"].includes(event.key)) {
      event.preventDefault();
      const current = architectureById(model.state.architecture), index = Number(event.target.dataset.layerIndex), shift = event.key === "ArrowLeft" ? -1 : 1;
      if (current && index + shift >= 0 && index + shift < current.tail.length) {
        const tail = [...current.tail]; [tail[index], tail[index + shift]] = [tail[index + shift], tail[index]];
        selectArchitecture(current.depth, tail);
      }
      return;
    }
    if (!modal) {
      if (
        sky ||
        !["labels", "repair"].includes(model.state.phase) ||
        event.target.closest("a,summary,input")
      )
        return;
      const index = Number(event.key) - 1;
      if (index >= 0 && index < 3) {
        const ids =
          model.state.phase === "labels" ? data.childIds : data.oldIds;
        choose(ids[cardIndex], data.classes[index].id);
      }
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      closeModal();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = [...modal.querySelectorAll("button,a[href]")].filter(
      (item) => !item.disabled,
    );
    const first = focusable[0],
      last = focusable.at(-1);
    if (!first) return;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });
  document.addEventListener("dragstart", event => {
    const item = event.target.closest?.("[data-layer-index]");
    if (item) event.dataTransfer?.setData("text/plain", item.dataset.layerIndex);
  });
  document.addEventListener("dragover", event => {
    if (event.target.closest?.("[data-layer-index]")) event.preventDefault();
  });
  document.addEventListener("drop", event => {
    const target = event.target.closest?.("[data-layer-index]"), from = Number(event.dataTransfer?.getData("text/plain")), to = Number(target?.dataset.layerIndex), current = architectureById(model.state.architecture);
    if (!target || !current || !Number.isInteger(from) || !Number.isInteger(to) || from < 0 || from >= current.tail.length || to < 0 || to >= current.tail.length || from === to) return;
    event.preventDefault(); const tail = [...current.tail], [layer] = tail.splice(from, 1); tail.splice(to, 0, layer); selectArchitecture(current.depth, tail);
  });
  document.addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    const action = button.dataset.action;
    if (button.dataset.labelId) {
      choose(button.dataset.labelId, button.dataset.label);
      return;
    }
    if (action === "sound") {
      soundEnabled = !soundEnabled;
      button.setAttribute("aria-pressed", String(soundEnabled));
      button.setAttribute(
        "aria-label",
        (soundEnabled ? "Выключить" : "Включить") + " звук",
      );
      button.textContent = soundEnabled ? "Звук вкл." : "Звук выкл.";
      chime();
      return;
    }
    if (action === 'resume' && model.state.resumePhase === 'tutorial' && found.size < data.childIds.length) {
      journey = 'story'; restoredJourney = null; render(); focusHeading(); return;
    }
    if (action === 'diagnostics') {
      const report = GalaxyTelemetry.diagnostics(), storage = GalaxyLessonStorage.diagnostics();
      openModal(`<h2>Журнал смены</h2><p>Смен в журнале: ${report.sessions}. Ожидают отправки: ${report.queued}. Пропущено событий: ${report.dropped}.</p><p>${esc(storage.warning || 'Смена сохраняется в этой вкладке.')} ${esc(report.warning || '')}</p><p>В автономной версии сохрани журнал до закрытия вкладки.</p><button class="primary" data-action="export-journal">Сохранить журнал</button>`);
      return;
    }
    if (action === 'export-journal') {
      const url = URL.createObjectURL(new Blob([GalaxyTelemetry.export()], {type:'application/json'}));
      const a = document.createElement('a'); a.href=url; a.download='science-day-journal.json'; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000); return;
    }
    if (action === "start-route") {
      journey = "story";
      render();
      focusHeading();
      return;
    }
    if (action === "collect-map") {
      journey = "collect";
      openSky(data.childIds.find((id) => !found.has(id)));
      return;
    }
    if (action === "complete-collection") {
      journey = "work";
      dispatch("START");
      return;
    }
    if (action === "sky") {
      openSky();
      return;
    }
    if (action === "zoom") {
      const image = byId[button.dataset.imageId];
      openModal(
        `<img class="modal-image" src="${esc(image.src)}" alt="${esc(image.name)}">${source(image)}`,
        true,
      );
      return;
    }
    if (action === "about") {
      openModal(about());
      return;
    }
    if (action === "astronomy") {
      closeModal(); openSky();
      return;
    }
    if (action === "discovery") {
      discovery(button.dataset.id);
      return;
    }
    if (action === "archive" || action === "return-sky") {
      closeModal(); openSky();
      return;
    }
    if (action === "archive-image") {
      archiveImage(button.dataset.id);
      return;
    }
    if (action === "talk") {
      talk(button.dataset.imageId, button.dataset.storyId);
      return;
    }
    if (action === "journal") {
      openModal(journal());
      return;
    }
    if (action === "folder") {
      openModal(folder());
      return;
    }
    if (action === "close-modal") {
      closeModal();
      return;
    }
    if (action === "sample") {
      cardIndex = Number(button.dataset.index);
      render();
      return;
    }
    if (action === "next" || action === "previous") {
      const ids = model.state.phase === "repair" ? data.oldIds : data.childIds;
      cardIndex = Math.max(
        0,
        Math.min(ids.length - 1, cardIndex + (action === "next" ? 1 : -1)),
      );
      render();
      return;
    }
    if (action === "cnn-image") {
      const activeId = button.dataset.imageId;
      if (!byId[activeId]) return;
      const request = ++cnnImageRequest;
      const image = new Image(); image.src = byId[activeId].src;
      try { await image.decode(); } catch (_) { return; }
      if (request !== cnnImageRequest || !button.isConnected || running || !root.querySelector('.cnn-workbench')) return;
      cnnImageId = activeId;
      updateArchitectureView(null, image);
      root.querySelector(`[data-action="cnn-image"][data-image-id="${activeId}"]`)?.focus({preventScroll:true});
      return;
    }
    if (action === "metrics") {
      const run = model.state.current || model.state.architectureBaseline;
      if (run) {
        openModal(`<h2>Как оценивают классификацию</h2><p>Последняя проверенная схема: ${esc(architectureLabel(run.architecture))}.${model.state.current ? '' : ' Новая схема ещё не проверена.'}</p>${metricDetails(run.result)}`);
        modal.querySelector('details.metrics').open = true;
      }
      return;
    }
    if (action === "cnn-filter") {
      eventRecord("explanation_opened");
      openModal(`<h2>Как работает свёртка</h2>${GalaxyCNNGuide.filterExample()}`);
      return;
    }
    if (action === "cnn-layers") {
      eventRecord("explanation_opened");
      openModal(`<h2>От снимка к классу</h2><p>На вход сеть получает изображение 32 × 32 пикселя в оттенках серого. Свёрточный слой обрабатывает участки изображения обучаемыми фильтрами. Каждый фильтр создаёт карту признаков — таблицу чисел, расположенных как участки снимка.</p>${Object.values(layerNotes).map(([, explanation]) => `<p>${esc(explanation)}</p>`).join('')}<p>Глобальное усреднение вычисляет среднее по каждой карте признаков. Линейный слой получает оценки классов, а softmax преобразует их в числа от 0 до 1 с суммой 1. Выбирается класс с наибольшим числом. Это число не гарантирует правильность ответа.</p><p>Доступны 22 схемы: одна или две свёртки; после последней свёртки — блок из обязательной ReLU и необязательных BatchNorm и Dropout. В этом блоке можно менять порядок слоёв. Каждый тип встречается не больше одного раза. При двух свёртках после первой всегда стоит ReLU. Остальная часть сети фиксирована.</p><p>Обучение для всех допустимых вариантов меток и схем выполнено заранее. Браузер открывает соответствующие результаты. Дополнительный слой и другой порядок слоёв не гарантируют улучшения.</p>`);
      return;
    }
    if (action === "model-settings") {
      dispatch("MODEL_SETTINGS");
      return;
    }
    if (action === "architecture-depth") {
      const current = architectureById(model.state.architecture);
      if (current) selectArchitecture(Number(button.dataset.depth), current.tail || ["r"]);
      return;
    }
    if (action === "layer-info") {
      const note = layerNotes[button.dataset.layer];
      if (note) { eventRecord('explanation_opened'); openModal(`<h2>${esc(note[0])}</h2><p>${esc(note[1])}</p>`); }
      return;
    }
    if (action === "layer-add") {
      const current = architectureById(model.state.architecture);
      if (current) selectArchitecture(current.depth, [...(current.tail || ["r"]), button.dataset.layer]);
      return;
    }
    if (action === 'layer-remove') {
      const current = architectureById(model.state.architecture), layer = button.dataset.layer;
      if (current && ['bn','d'].includes(layer)) selectArchitecture(current.depth, current.tail.filter(item => item !== layer));
      return;
    }
    if (action === "layer-earlier" || action === "layer-later") {
      const current = architectureById(model.state.architecture);
      const index = Number(button.dataset.layerIndex);
      if (current && Number.isInteger(index)) {
        const tail = [...(current.tail || ["r"])], other = index + (action === "layer-earlier" ? -1 : 1);
        if (other >= 0 && other < tail.length) [tail[index], tail[other]] = [tail[other], tail[index]];
        selectArchitecture(current.depth, tail);
      }
      return;
    }
    if (action === "architecture-save") {
      dispatch("RUN");
      return;
    }
    if (action === "architecture") {
      dispatch("SET_ARCHITECTURE", {
        architecture: button.dataset.architecture,
      });
      return;
    }
    if (action === "reset") {
      if (!confirm("Начать новую смену? Текущие метки и результаты будут сброшены.")) return;
      eventRecord("session_reset");
      GalaxyLessonStorage.clear();
      QuestScene.reset();
      found.clear();
      journey = "welcome";
      cardIndex = 0;
      dispatch("RESET");
      return;
    }
    const actions = {
      "guide-add-convolution": "GUIDE_ADD_CONVOLUTION",
      "guide-confirm-compare": "GUIDE_CONFIRM_COMPARE",
      labels: "LABELS",
      repair: "REPAIR",
      run: "RUN",
      finish: "FINISH",
      home: "HOME",
      resume: "RESUME",
    };
    if (actions[action]) {
      dispatch(actions[action]);

    }
  });
  document.addEventListener('click', event => {
    if (event.target.closest('[data-quest="hint"], [data-dialogue-question]')) eventRecord('help_opened');
  });
  document.addEventListener('toggle', event => {
    if (event.target.tagName === 'DETAILS' && event.target.open) eventRecord('explanation_opened');
  }, true);
  const saved = GalaxyLessonStorage.read();
  if (saved) {
    try {
      if (saved.lesson.protocolVersion !== model.protocol.protocolVersion || saved.lesson.datasetVersion !== model.protocol.datasetVersion ||
          saved.ui.found.some(id => !data.childIds.includes(id)) || new Set(saved.ui.found).size !== saved.ui.found.length) throw new Error('incompatible');
      const refs = ['current','baseline','correctedReview','architectureBaseline'].map(name => saved.lesson.state?.[name]?.architecture).filter(Boolean);
      if (refs.some(id => !GalaxyArchitectures.get(id))) throw new Error('invalid architecture');
      try { await Promise.all([...new Set(refs)].map(id => GalaxyCNNResults.ensure(id))); }
      catch (error) { error.restoreResourceFailure = true; throw error; }
      model.restore(saved.lesson);
      saved.ui.found.forEach(id => found.add(id));
      cardIndex = Math.min(saved.ui.cardIndex, (model.state.resumePhase === 'repair' ? data.oldIds.length : data.childIds.length) - 1);
      restoredJourney = saved.ui.journey;
      journey = 'welcome';
      GalaxyTelemetry.restore(telemetryMeta);
    } catch (error) {
      if (error.restoreResourceFailure) {
        document.querySelector('#loading')?.remove();
        root.innerHTML = '<section class="workbench"><section class="station resource-failure"><h1 tabindex="-1">Продолжим, когда загрузятся результаты</h1><p>Не удалось открыть результаты сохранённой смены. Твои метки и схема сохранены. Проверь соединение; если игра открыта из ZIP, распакуй архив целиком.</p><div class="navigation"><button class="primary" data-restore-retry>Повторить загрузку</button><button class="secondary" data-restore-new>Начать новую смену</button></div></section></section>';
        root.querySelector('[data-restore-retry]').addEventListener('click', () => location.reload());
        root.querySelector('[data-restore-new]').addEventListener('click', () => {
          if (confirm('Начать новую смену? Сохранённые метки и результаты будут сброшены.')) {
            GalaxyLessonStorage.clear(); location.reload();
          }
        });
        root.querySelector('h1').focus();
        return;
      }
      restoreWarning = 'Сохранённая смена несовместима с этой версией или повреждена. Начни новую смену.';
      GalaxyLessonStorage.clear();
      GalaxyTelemetry.start(telemetryMeta);
    }
  } else {
    restoreWarning = GalaxyLessonStorage.diagnostics().warning;
    GalaxyTelemetry.start(telemetryMeta);
  }
  render();
  if (restoreWarning) openModal(`<h2>Начнём новую смену</h2><p>${esc(restoreWarning)}</p>`);
})();
