(function () {
  "use strict";
  const data = globalThis.GALAXY_DATA,
    archiveData = globalThis.GALAXY_ARCHIVE;
  let model;
  const byId = Object.fromEntries(
    [...data.images, ...archiveData.images].map((image) => [image.id, image]),
  );
  const root = document.querySelector("#game"),
    found = new Set();
  try {
    model = GalaxyCNNLesson.create(data, globalThis.GALAXY_CNN_EXPERIMENTS);
  } catch (error) {
    document.querySelector("#loading")?.remove();
    root.innerHTML =
      '<section class="room"><div class="welcome"><h1>Не удалось открыть опыт</h1><p>В пакете нет подготовленного CNN-опыта. Переоткрой полный пакет материалов.</p></div></section>';
    return;
  }
  let journey = "welcome",
    cardIndex = 0,
    quest = null,
    modal = null,
    modalTrigger = null,
    sky = null;
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
  const blockCount = (value) => `${value} ${String(value) === "1" ? "блок" : "блока"}`;
  const source = (image) =>
    `<p class="source">${esc(image.credit)} · <a href="${esc(image.source)}" target="_blank" rel="noreferrer">Источник снимка ↗</a></p>`;
  function mentor(text, mood = "warm", opening = false) {
    return `<aside class="mentor${opening ? " room-dialogue" : ""}"><span class="mentor-portrait"><img src="assets/art/nika-${mood}-v1.png" alt="Ника, астроном"></span><div><span class="speaker">НИКА <i>астроном</i></span><p>${text}</p></div></aside>`;
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
    return `<header class="hud"><div class="top-actions"><button class="quiet sound" data-action="sound" aria-pressed="${soundEnabled}" aria-label="${soundEnabled ? "Выключить" : "Включить"} звук">${soundEnabled ? "Звук вкл." : "Звук выкл."}</button>${free ? '<button class="quiet" data-action="sky">Карта неба</button><button class="quiet" data-action="astronomy">ИИ в астрономии</button>' : ""}<button class="quiet" data-action="about">О проекте</button>${model.state.phase !== "intro" ? '<button class="quiet" data-action="home">↗ Обсерватория</button>' : ""}</div></header>`;
  }
  function photo(image) {
    return `<figure class="galaxy-frame"><img src="${esc(image.src)}" alt="${esc(image.name)}"><figcaption><span>HUBBLE · ${esc(image.name)}</span><button class="zoom" data-action="zoom" data-image-id="${esc(image.id)}" aria-label="Открыть снимок ${esc(image.name)}">⤢</button></figcaption></figure>`;
  }
  function progress(phase) {
    const steps = [
      ["tutorial", "Пример"],
      ["labels", "Разметка"],
      ["review", "Проверка"],
      ["repair", "Старые метки"],
      ["final", "Итог"],
    ];
    const active = Math.max(
      0,
      steps.findIndex((item) => item[0] === phase),
    );
    return `<ol class="progress" aria-label="Ход опыта">${steps.map(([id, name], index) => `<li class="${index === active ? "active" : index < active ? "done" : ""}"><span>${index < active ? "✓" : index + 1}</span><b>${name}</b></li>`).join("")}</ol>`;
  }
  function intro() {
    const resumed =
      model.state.resumePhase !== "tutorial" ||
      found.size ||
      model.state.baseline;
    return `<section class="room">${nav()}<h1 class="sr-only">Обсерватория</h1><div class="welcome">${mentor(resumed ? "Снимки и твои метки остались на столе. Продолжим?" : "Привет, я Ника! В архиве Hubble много готовых снимков галактик. Помоги собрать три примера для учебной модели.", "warm", true)}<button class="primary" data-action="${resumed ? "resume" : "start-route"}">${resumed ? "Продолжить работу" : "Помочь Нике"} <span>→</span></button></div></section>`;
  }
  function story() {
    const ready = found.size === 3,
      astronomy = GalaxyAstronomy.cases[0];
    return `<section class="room route-story">${nav()}<article class="route-story__card"><span class="eyebrow">01 / ИИ В АСТРОНОМИИ</span><h1 tabindex="-1">${esc(astronomy.title)}</h1><p>${esc(astronomy.text)}</p><p class="route-story__question">${esc(astronomy.question)}</p><p class="source">${esc(astronomy.sourceLabel)} · <a href="${esc(astronomy.sourceURL)}" target="_blank" rel="noreferrer">Источник ↗</a></p>${mentor(ready ? "Все три снимка в подборке. Теперь разметим один пример вместе." : found.size ? `В подборке ${found.size} из 3 снимков. Вернёмся к карте и закончим.` : "Люди отмечают признаки на готовых архивных снимках. Соберём маленькую подборку?", "curious")}<button class="primary" data-action="${ready ? "complete-collection" : "collect-map"}">${ready ? "К рабочему столу" : "Найти галактики на карте"} <span>→</span></button></article></section>`;
  }
  function station(title, kicker, phase, body, footer = "") {
    return `<section class="workbench${body.includes('id="quest-scene"') ? " workbench--quest" : ""}">${nav()}${progress(phase)}<div class="station"><div class="station-head"><div><span class="eyebrow">${kicker}</span><h1 tabindex="-1">${title}</h1></div></div>${body}${footer}</div></section>`;
  }
  function tutorial() {
    const image = byId[data.tutorialId];
    return station(
      "Как ИИ помогает астрономам?",
      "02 / РАЗБИРАЕМ ПРИМЕР ВМЕСТЕ",
      "tutorial",
      `<div id="quest-scene" data-image-id="${image.id}"></div><p class="tutorial-next">Метка — подпись с выбранной категорией. Разметить снимок — выбрать для него метку. Разберём пример вместе с Никой.</p><div class="navigation"><button class="secondary" data-action="zoom" data-image-id="${image.id}">Открыть снимок</button><button class="primary" data-action="labels">К моей подборке →</button></div><details class="credits"><summary>Источник снимка</summary>${source(image)}</details>`,
    );
  }
  function labels() {
    const state = model.state,
      ids = data.childIds,
      image = byId[ids[cardIndex]],
      missing = ids.filter((id) => !state.labels[id]).length;
    return station(
      "Разметим учебные примеры",
      "03 / РАЗМЕЧАЕМ · " + (cardIndex + 1) + " ИЗ 3",
      "labels",
      `${programBar()}<div id="quest-scene" data-image-id="${image.id}"></div><div class="film-footer">${samples(ids)}<div class="navigation"><button class="secondary" data-action="previous" ${cardIndex === 0 ? "disabled" : ""}>←</button><button class="secondary" data-action="next" ${cardIndex === 2 ? "disabled" : ""}>Следующий →</button><button class="primary" data-action="run" ${missing ? "disabled" : ""}>${missing ? "Поставь все 3 метки" : "Проверить модель"} →</button></div></div><details class="credits"><summary>О метках</summary>${source(image)}<p>Снимки с метками составляют обучающую выборку — примеры, на которых учится модель. Для всех вариантов меток обучение выполнено заранее; здесь открывается соответствующий результат.</p></details>`,
    );
  }
  function samples(ids) {
    return `<div class="samples">${ids.map((id, index) => `<button data-action="sample" data-index="${index}" aria-label="Снимок ${index + 1}: ${esc(byId[id].name)}" class="sample ${index === cardIndex ? "selected" : ""}" aria-current="${index === cardIndex}"><img src="${esc(byId[id].src)}" alt=""><span>${index + 1}</span><i>${model.state.labels[id] ? "✓" : "·"}</i></button>`).join("")}</div>`;
  }
  function programBar() {
    const state = model.state,
      canChange =
        state.phase === "review" &&
        state.repairCheckedLabelKey === state.labelKey;
    return `<section class="cnn-programs" aria-label="Программы рабочего стола"><button data-action="labels" class="${state.phase === "labels" ? "selected" : ""}">Разметить снимки</button><button data-action="run" ${state.phase === "labels" && data.childIds.some((id) => !state.labels[id]) ? "disabled" : ""}>Обучение и проверка</button><button data-action="model-settings" title="${canChange ? "Сравнить один и два свёрточных блока" : "Сначала проверь старые метки и повтори опыт"}" ${canChange ? "" : "disabled"}>Изменить модель</button><button data-action="folder">Папка: 9 примеров</button></section>`;
  }
  function resultCard(prediction) {
    const image = byId[prediction.id],
      ok = prediction.predicted === prediction.expected;
    return `<article class="result ${ok ? "correct" : "incorrect"}">${photo(image)}<div class="result-info"><div class="result-name"><b>${esc(image.name)}</b><span>${ok ? "Совпало ✓" : "Проверим ?"}</span></div><p>Модель: <strong>${esc(classLabel(prediction.predicted))}</strong></p><p class="reference">Справочная метка: ${esc(classLabel(prediction.expected))}</p><button class="text-button" data-action="talk" data-image-id="${esc(image.id)}">Обсудить с Никой →</button></div></article>`;
  }
  function review() {
    const state = model.state,
      baseline = state.baseline,
      corrected = state.correctedReview;
    if (state.modelSettings || !state.current) {
      const blocks =
        state.architecture === "2"
          ? "<article><b>Свёртка + ReLU</b><span>Обрабатывает карты признаков</span></article>"
          : "";
      return station(
        "Изменить модель",
        "04 / УСТРОЙСТВО МОДЕЛИ",
        "review",
        `${programBar()}<section class="cnn-model"><h2>Сколько свёрточных блоков?</h2><p>Это свёрточная нейронная сеть (CNN). В нашей модели каждый блок содержит свёрточный слой и функцию активации ReLU. Больше блоков не обязательно дают лучший результат.</p><div class="architecture-choice">${["1", "2"].map((blocks) => `<button data-action="architecture" data-architecture="${blocks}" class="${state.architecture === blocks ? "selected" : ""}">${blocks} ${blocks === "1" ? "свёрточный блок" : "свёрточных блока"}</button>`).join("")}</div><div class="cnn-layers"><article><b>Снимок</b><span>32 × 32 пикселя · оттенки серого</span></article><article><b>Свёртка + ReLU</b><span>Обрабатывает участки снимка</span></article>${blocks}<article><b>Усреднение</b><span>Среднее по каждой карте признаков</span></article><article><b>Классификатор</b><span>Выбирает одну из трёх меток</span></article></div><button class="primary" data-action="run">Проверить модель →</button><details class="credits"><summary>Что делают слои?</summary><p>Свёрточный слой обрабатывает небольшие участки изображения с помощью фильтров. Их числовые параметры подбираются при обучении. Результат каждого фильтра — карта признаков: таблица чисел, расположенных как участки изображения.</p><p>ReLU — функция активации: она заменяет отрицательные числа нулями, а остальные оставляет. Второй свёрточный слой получает карты признаков первого блока.</p><p>Затем сеть вычисляет среднее по каждой карте. По этим числам классификатор получает оценки трёх категорий. Функция softmax преобразует их в числа от 0 до 1 с суммой 1. Сеть выбирает категорию с наибольшим числом; это не гарантирует правильный ответ.</p></details></section>`,
      );
    }
    const run = state.current.result;
    const architectureChoice =
      state.repairCheckedLabelKey === state.labelKey
        ? `<div class="architecture-choice"><span>Устройство: </span>${["1", "2"].map((blocks) => `<button data-action="architecture" data-architecture="${blocks}" class="${state.architecture === blocks ? "selected" : ""}">${blocks} ${blocks === "1" ? "блок" : "блока"}</button>`).join("")}</div>`
        : "";
    const compare = state.architectureBaseline
      ? `<p class="callout">На тех же метках: ${blockCount(state.architectureBaseline.architecture)} — ${state.architectureBaseline.result.review.correct}/${state.architectureBaseline.result.review.total}; ${blockCount(state.current.architecture)} — ${run.review.correct}/${run.review.total}.</p>`
      : corrected && baseline && corrected.labelKey !== baseline.labelKey
        ? `<p class="callout">Первый опыт: ${blockCount(baseline.architecture)} — ${baseline.result.review.correct}/${baseline.result.review.total}; текущий: ${blockCount(corrected.architecture)} — ${corrected.result.review.correct}/${corrected.result.review.total}.</p>`
        : "";
    return station(
      "Проверим ответы модели",
      "04 / ОБУЧЕНИЕ И ПРОВЕРКА",
      "review",
      `${programBar()}<div class="score-strip"><span>Совпало со справочными метками <b>${run.review.correct}<small> / ${run.review.total}</small></b></span><p>Свёрточная нейросеть: ${state.architecture} ${state.architecture === "1" ? "блок" : "блока"}.<br>Обучение выполнено заранее. Это результат для твоих меток.</p></div>${state.notice ? `<p class="callout">${esc(state.notice)}</p>` : ""}${compare}<div class="result-grid">${run.review.predictions.map(resultCard).join("")}</div>${architectureChoice}<div class="navigation result-nav"><button class="secondary" data-action="labels">← Разметить снимки</button><div><button class="secondary" data-action="repair">Проверить старые метки →</button>${state.repairCheckedLabelKey === state.labelKey ? '<button class="primary" data-action="finish">К итогу →</button>' : ""}</div></div>`,
    );
  }
  function repair() {
    const state = model.state,
      ids = data.oldIds,
      image = byId[ids[cardIndex]];
    return station(
      "Проверим старые метки",
      "05 / ПРОВЕРИТЬ СТАРЫЕ МЕТКИ · " + (cardIndex + 1) + " ИЗ 2",
      "repair",
      `${programBar()}<div id="quest-scene" data-image-id="${image.id}"></div><div class="film-footer">${samples(ids)}<div class="navigation"><button class="secondary" data-action="previous" ${cardIndex === 0 ? "disabled" : ""}>←</button><button class="secondary" data-action="next" ${cardIndex === 1 ? "disabled" : ""}>Следующий →</button><button class="primary" data-action="run">Повторить проверку →</button></div></div>`,
    );
  }
  function final() {
    const state = model.state,
      run = state.current.result,
      initial = state.baseline.result;
    return `<section class="room final-room">${nav()}<article class="research-board"><span class="eyebrow">ДОСКА ИССЛЕДОВАНИЙ</span><h1>Подборка проверена</h1><div class="board-score-summary"><section data-score-scope="review-before"><span>Первая проверка, ${blockCount(state.baseline.architecture)}</span><b>${initial.review.correct} из ${initial.review.total}</b></section><section data-score-scope="review-after"><span>Текущая проверка, ${blockCount(state.current.architecture)}</span><b>${run.review.correct} из ${run.review.total}</b></section><section class="board-final-score" data-score-scope="final"><span>Другие снимки, которых не было в обучении</span><b>${run.final.correct} из ${run.final.total}</b></section></div><div class="result-grid">${run.final.predictions.map(resultCard).join("")}</div><p class="final-note">${esc(state.notice)}</p><div class="navigation"><button class="secondary" data-action="labels">Вернуться к примерам</button><button class="primary" data-action="sky">Исследовать звёздное небо →</button><button class="secondary" data-action="reset">Повторить опыт</button></div></article>${mentor("Спасибо! Ты собрал снимки, разметил их и проверил ответы модели.")}</section>`;
  }
  function folder() {
    const state = model.state,
      editable = new Set(model.protocol.editableIds);
    return `<section class="folder-panel"><h2>Обучающая выборка: 9 снимков</h2><p>Все девять снимков с метками используются при обучении. Пять меток можешь выбрать ты: три новые и две старые. Остальные четыре подготовлены авторами.</p><div class="folder-grid">${model.protocol.trainingIds
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
  function astronomy() {
    return `<span class="eyebrow">ИИ В АСТРОНОМИИ</span><h2>Открытия и исследования</h2><p>Открой историю: что заметила программа, что проверили астрономы и какие вопросы остались.</p><div class="discovery-grid">${GALAXY_DISCOVERIES.map((item) => `<button class="library-card" data-action="discovery" data-id="${esc(item.id)}"><img src="${esc(item.image)}" alt="${esc(item.alt)}"><span><small>${esc(categories[item.category])} · ${esc(item.date || "")}</small><b>${esc(item.title)}</b></span></button>`).join("")}</div><button class="secondary" data-action="archive">Архив галактик →</button>`;
  }
  function archive() {
    return `<span class="eyebrow">АРХИВ HUBBLE</span><h2>${GALAXY_ARCHIVE.images.length} галактики</h2><p>В основном опыте ты разбираешь три фиксированных снимка. Остальные здесь — для свободного исследования. Здесь можно рассмотреть всю коллекцию и прочитать о каждом объекте.</p><div class="discovery-grid">${GALAXY_ARCHIVE.images.map((i) => `<button class="library-card" data-action="archive-image" data-id="${esc(i.id)}"><img src="${esc(i.src)}" alt="${esc(i.name)}"><span><b>${esc(i.name)}</b></span></button>`).join("")}</div>`;
  }
  function journal() {
    return `<span class="eyebrow">ДОСКА ИССЛЕДОВАНИЙ</span><h2>Как научить модель — и проверить её</h2><div class="journal-steps"><p><b>01 · Наблюдаем.</b> Что видно на снимке?</p><p><b>02 · Собираем данные.</b> Снимок с меткой — учебный пример для модели.</p><p><b>03 · Проверяем.</b> Смотрим её ответы на других снимках.</p><p><b>04 · Исследуем ошибку.</b> Проверяем метки учебных примеров.</p><p><b>05 · Сравниваем.</b> Видим, какие ответы действительно изменились.</p></div><p>${esc(GalaxyAstronomy.afterExperience.text)}</p><button class="primary" data-action="astronomy">Где это применяют в астрономии?</button>`;
  }
  function archiveImage(id) {
    const image = byId[id];
    if (!image) return;
    openModal(
      `<span class="eyebrow">АРХИВ HUBBLE</span><h2>${esc(image.name)}</h2>${photo(image)}<p>${esc(image.explanation)}</p>${source(image)}<button class="text-button" data-action="talk" data-image-id="${esc(image.id)}">Рассмотреть с Никой →</button><button class="secondary" data-action="archive">Весь архив</button>`,
    );
  }
  function discovery(id) {
    const item = GALAXY_DISCOVERIES.find((i) => i.id === id);
    if (!item) return;
    openModal(
      `<span class="eyebrow">${esc(categories[item.category])} · ${esc(item.date || "")}</span><h2>${esc(item.title)}</h2><figure class="discovery-figure"><img src="${esc(item.image)}" alt="${esc(item.alt)}"><figcaption>${esc(item.alt)}</figcaption></figure><p>${esc(item.text)}</p><p>${esc(item.detail)}</p><p class="note">${esc(item.locationNote)}${item.coordinateSource ? ` · <a href="${esc(item.coordinateSource.startsWith("https://") ? item.coordinateSource : "https://simbad.cds.unistra.fr/simbad/sim-id?Ident=" + encodeURIComponent(item.coordinateSource.replace(/^SIMBAD: /, "")))}" target="_blank" rel="noreferrer">Координаты ↗</a>` : ""}</p><p class="source">${esc(item.credit)} · <a href="${esc(item.imageSource)}" target="_blank" rel="noreferrer">Источник изображения ↗</a> · <a href="${esc(item.source)}" target="_blank" rel="noreferrer">Исследование ↗</a></p><div class="photo-companion">${mentor("У каждого открытия есть своя история. Обсудим, что здесь нашли?", "curious")}<button class="text-button" data-action="talk" data-story-id="${esc(item.id)}">Поговорить с Никой →</button></div><button class="secondary" data-action="astronomy">Все истории</button>`,
    );
  }
  function openSky(target) {
    if (sky) return;
    closeModal();
    const guided = journey === "collect";
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
        found.add(id);
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
    return `<span class="eyebrow">О ПРОЕКТЕ</span><h2>ИИ в астрономии</h2><p>Галактики на снимках настоящие: архив NASA/ESA Hubble. Обсерватория и Ника — художественные иллюстрации. На карте показаны звёздный атлас NASA и координаты объектов. Мы открываем архивные снимки, а не делаем новые наблюдения.</p><p>В основном опыте девять учебных снимков. Три новые и две старые подписи можно менять. Мы используем свёрточные нейронные сети (CNN). Для каждого сочетания меток и обоих вариантов сети обучение выполнено заранее. Браузер открывает точный результат выбранного опыта; он не обучает модель заново.</p><p>В этом задании мы классифицируем снимки — относим их к трём категориям по видимым признакам. «Гладкая» означает плавное свечение без заметных рукавов. «Видна спираль» — заметны спиральные рукава. «Вид с ребра» — мы смотрим на диск сбоку. Это ракурс, а не отдельный тип галактики.</p><p>Разметка человека, ответ модели и справочная метка — разные вещи. Повторная проверка показывает изменения на знакомых снимках. Итоговые снимки не входят в обучение, но уже изучались авторами: это учебный опыт, не новая независимая оценка качества.</p><p><a href="DATA-NOTES.md" target="_blank">Данные и метод ↗</a> · <a href="provenance.json" target="_blank">Источники ↗</a> · <a href="assets/art/ART-CREDITS.md" target="_blank">Иллюстрации ↗</a></p>`;
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
  function render() {
    const phase = model.state.phase;
    quest?.destroy();
    quest = null;
    document.body.dataset.phase = phase;
    galaxyWorld.setPhase(phase);
    root.innerHTML =
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
        selected: model.state.labels[image.id],
        initialSelected: model.state.labels[image.id],
        initialOldLabel:
          phase === "repair"
            ? classLabel(data.initialOldLabels[image.id])
            : null,
        opening:
          phase === "tutorial"
            ? "У телескопов много готовых архивных снимков. Люди дают модели примеры с метками. Посмотрим один вместе."
            : phase === "repair"
              ? "В старой подборке тоже могут быть ошибки. Проверь подпись по снимку, затем повторим опыт."
              : null,
        onLabel: (value) => choose(image.id, value),
      });
    }
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
  function dispatch(type, payload = {}) {
    try {
      model.dispatch({ type, ...payload });
      if (type === "LABELS" || type === "REPAIR") cardIndex = 0;
      render();
      chime();
      if (type !== "SET_LABEL") {
        window.scrollTo({ top: 0, behavior: "instant" });
        focusHeading();
      }
    } catch (error) {
      openModal(`<h2>Нужен ещё один шаг</h2><p>${esc(error.message)}</p>`);
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
    NikaDialogue.open({ image, story, phase: model.state.phase, prediction });
  }
  function choose(id, value) {
    if (sky || modal) return;
    dispatch("SET_LABEL", { id, label: value });
    root
      .querySelector(`[data-label-id="${id}"][data-label="${value}"]`)
      ?.focus({ preventScroll: true });
  }
  document.addEventListener("keydown", (event) => {
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
  document.addEventListener("click", (event) => {
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
    if (action === "start-route") {
      journey = "story";
      render();
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
      openModal(astronomy());
      return;
    }
    if (action === "discovery") {
      discovery(button.dataset.id);
      return;
    }
    if (action === "archive") {
      openModal(archive());
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
    if (action === "model-settings") {
      dispatch("MODEL_SETTINGS");
      return;
    }
    if (action === "architecture") {
      dispatch("SET_ARCHITECTURE", {
        architecture: button.dataset.architecture,
      });
      return;
    }
    if (action === "reset") {
      if (!confirm("Повторить опыт? Текущие метки будут сброшены.")) return;
      QuestScene.reset();
      found.clear();
      journey = "welcome";
      cardIndex = 0;
      dispatch("RESET");
      return;
    }
    const actions = {
      labels: "LABELS",
      repair: "REPAIR",
      run: "RUN",
      finish: "FINISH",
      home: "HOME",
      resume: "RESUME",
    };
    if (actions[action]) {
      dispatch(actions[action]);
      if (action === "finish") journey = "free";
    }
  });
  render();
})();
