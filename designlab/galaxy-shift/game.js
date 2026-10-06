(function () {
  'use strict';
  const data = globalThis.GALAXY_DATA;
  const model = globalThis.GalaxyModel.create(data);
  const root = document.querySelector('#game');
  const byId = Object.fromEntries(data.images.map(image => [image.id, image]));
  let cardIndex = 0;
  let modal = null;
  let modalTrigger = null;

  const esc = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const label = id => data.classes.find(item => item.id === id)?.label || id;
  const source = image => `<p class="source">${esc(image.credit)} · <a href="${esc(image.source)}" target="_blank" rel="noreferrer">источник снимка</a></p>`;
  const nav = () => `<div class="topbar"><span class="brand">Первая смена · атлас галактик</span><div class="top-actions"><button class="quiet" data-action="about">О проекте</button>${model.state.phase !== 'intro' ? '<button class="quiet" data-action="home">Лаборатория</button>' : ''}</div></div>`;
  const mentor = text => `<aside class="mentor"><img src="assets/art/nika.png" alt=""><p><b>Ника</b><br>${text}</p></aside>`;
  const progress = phase => {
    const order = ['tutorial','labels','results','repair','final'];
    const active = Math.max(0, order.indexOf(phase));
    return `<div class="progress" aria-label="Шаг ${active + 1} из ${order.length}">${order.map((_, i) => `<i class="${i <= active ? 'on' : ''}"></i>`).join('')}</div>`;
  };
  function photo(image) {
    return `<div class="galaxy-frame"><img src="${esc(image.src)}" alt="${esc(image.name)}"><button class="zoom" data-action="zoom" data-image-id="${esc(image.id)}" aria-label="Открыть снимок ${esc(image.name)}">⌕</button></div>`;
  }
  function chooser(image, selected, old) {
    return `<div class="facts"><span class="eyebrow">${old ? 'Старая учебная подпись' : 'Учебный снимок'}</span><h2>${esc(image.name)}</h2><p>${old ? 'Посмотри на сам снимок и реши, какая подпись точнее.' : 'Выбери метку по тому, что видно на снимке.'}</p>${old ? `<p class="old-tag">Было: ${esc(label(data.initialOldLabels[image.id]))}</p>` : ''}<div class="class-list">${data.classes.map(item => `<button class="label-btn" data-label-id="${esc(image.id)}" data-label="${item.id}" aria-pressed="${selected === item.id}"><b>${esc(item.label)}</b><small>${esc(item.hint)}</small></button>`).join('')}</div><div class="hint-row"><button class="text-button" data-action="help" data-image-id="${esc(image.id)}">Помоги разобраться</button></div>${source(image)}</div>`;
  }
  function intro() {
    const resumable = model.state.phase === 'intro' && model.state.labels[data.childIds[0]] !== undefined && (model.state.resumePhase !== 'tutorial' || model.state.baseline !== null);
    return `<section class="scene">${nav()}<div class="laboratory-art" aria-hidden="true"><img class="room-nika" src="assets/art/nika.png" alt=""><img class="room-desk" src="assets/art/workstation.png" alt=""></div><article class="card"><div class="intro-grid"><div><span class="eyebrow">Дневная лаборатория в горах</span><h1>Поможем Нике разобрать галактики</h1><p>Новый орбитальный телескоп пришлёт очень много снимков. Подготовим модель: дадим ей примеры с подписями и проверим ответы на других галактиках.</p><p class="note">В игре используются архивные снимки Hubble. Мы готовимся к будущему потоку данных от Roman.</p><button class="primary" data-action="${resumable ? 'resume' : 'start'}">${resumable ? 'Продолжить работу' : 'Начать смену'}</button></div></div></article></section>`;
  }
  function tutorial() {
    const image = byId[data.tutorialId];
    return `<section class="workbench">${nav()}${progress('tutorial')}<article class="panel"><div class="photo-stage">${photo(image)}<div class="facts"><span class="eyebrow">Первый пример вместе с Никой</span><h1>Ищем видимый облик</h1><p>У этой галактики ровное овальное свечение: заметных рукавов нет. Поэтому подпись — <b>«гладкая»</b>.</p><p>Сегодня мы учим ИИ различать галактики. Модель получает снимки с подписями и предлагает подписи для других снимков.</p>${source(image)}<div class="navigation"><button class="primary" data-action="labels">Попробовать самому</button></div></div></div>${mentor('Подпись — это пример для модели. Посмотрим на снимок, а потом выберем, что на нём видно.')}</article></section>`;
  }
  function labelsView() {
    const state = model.state, ids = data.childIds, image = byId[ids[cardIndex]];
    const missing = ids.filter(id => !state.labels[id]).length;
    return `<section class="workbench">${nav()}${progress('labels')}<article class="panel"><div class="panel-head"><div><span class="eyebrow">Разметка · ${cardIndex + 1} из ${ids.length}</span><h1>Подпишем снимки для модели</h1></div><span class="status">Осталось: ${missing}</span></div><div class="photo-stage">${photo(image)}${chooser(image, state.labels[image.id], false)}</div><div class="navigation"><button class="secondary" data-action="previous" ${cardIndex === 0 ? 'disabled' : ''}>← Предыдущий</button><div><button class="secondary" data-action="next" ${cardIndex === ids.length - 1 ? 'disabled' : ''}>Следующий →</button><button class="primary" data-action="run" ${missing ? 'disabled' : ''}>Проверить модель</button></div></div><p class="note">Опыты с разными подписями рассчитаны заранее. Откроем результат для твоего набора.</p></article></section>`;
  }
  function predictionCard(prediction, previous) {
    const image = byId[prediction.id], ok = prediction.predicted === prediction.expected;
    const changed = previous && previous.predicted !== prediction.predicted;
    return `<article class="result">${photo(image)}<strong>${esc(image.name)}</strong>${previous ? `<span class="before-answer">До правок: ${esc(label(previous.predicted))}</span>` : ''}<span>${previous ? 'После правок' : 'Модель'}: <b class="${ok ? 'good' : 'bad'}">${esc(label(prediction.predicted))}</b>${changed ? ' · ответ изменился' : ''}</span><span>Справочный ответ: ${esc(label(prediction.expected))}</span>${!ok ? '<span class="bad">Ответ пока неверный</span>' : ''}<button class="text-button" data-action="explain" data-image-id="${esc(image.id)}">Как модель решила?</button>${source(image)}</article>`;
  }
  function results() {
    const state = model.state, current = state.current, baseline = state.baseline;
    const changed = baseline.key !== current.key;
    const review = current.review, checked = state.repairCheckedKey === current.key;
    const before = Object.fromEntries(baseline.review.predictions.map(p => [p.id, p]));
    const message = checked
      ? 'Мы проверили старые подписи и оставили тот же способ работы модели. Сравним ответы на тех же снимках.'
      : review.correct === review.total
        ? 'На этих трёх снимках все ответы совпали со справочными. Проверим ещё старые учебные подписи: маленькая проверка не говорит, что ошибок больше не будет.'
        : 'Нашли расхождение! Причиной могут быть подписи в учебной подборке или ограничения самой модели. Проверим старые примеры.';
    return `<section class="workbench">${nav()}${progress(checked ? 'repair' : 'results')}<article class="panel"><div class="panel-head"><div><span class="eyebrow">Подготовленный опыт</span><h1>Проверяем ответы модели</h1></div><span class="status">Верно ${review.correct} из ${review.total}</span></div>${state.notice ? `<p class="callout">${esc(state.notice)}</p>` : ''}${mentor(message)}${changed ? `<div class="compare"><div class="score previous"><span>Первая проверка</span><b>${baseline.review.correct} / ${baseline.review.total}</b></div><div class="score"><span>После изменения подписей</span><b>${review.correct} / ${review.total}</b></div></div>` : ''}<div class="result-grid">${review.predictions.map(p => predictionCard(p, changed ? before[p.id] : null)).join('')}</div><div class="navigation"><button class="secondary" data-action="labels">К своим снимкам</button><div><button class="${checked ? 'secondary' : 'primary'}" data-action="repair">Проверить старые подписи</button>${checked ? '<button class="primary" data-action="finish">Завершить смену</button>' : ''}</div></div></article></section>`;
  }
  function repair() {
    const state = model.state, ids = data.oldIds, image = byId[ids[cardIndex]];
    return `<section class="workbench">${nav()}${progress('repair')}<article class="panel"><div class="panel-head"><div><span class="eyebrow">Старая подборка · ${cardIndex + 1} из ${ids.length}</span><h1>Какая подпись здесь точнее?</h1></div><span class="status">Изменено: ${ids.filter(id => state.labels[id] !== data.initialOldLabels[id]).length}</span></div><div class="photo-stage">${photo(image)}${chooser(image, state.labels[image.id], true)}</div><div class="navigation"><button class="secondary" data-action="previous" ${cardIndex === 0 ? 'disabled' : ''}>← Предыдущий</button><div><button class="secondary" data-action="next" ${cardIndex === ids.length - 1 ? 'disabled' : ''}>Следующий →</button><button class="primary" data-action="run">Проверить снова</button></div></div><p class="note">В этой учебной истории две старые подписи намеренно перепутаны авторами игры.</p></article></section>`;
  }
  function final() {
    const state = model.state, exp = state.current.final;
    return `<section class="workbench">${nav()}${progress('final')}<article class="panel"><div class="final-grid"><div><span class="eyebrow">Итог смены</span><h1>${exp.correct === exp.total ? "Проверка пройдена — продолжим исследование" : "Нашли границы модели"}</h1><p>Ты подготовил примеры, проверил ответы модели и пересмотрел старые подписи. На итоговой подборке верно ${exp.correct} из ${exp.total}: ${exp.correct === exp.total ? "Это маленькая подборка: дальше ответы тоже нужно проверять." : "Эта модель ещё не готова к самостоятельной сортировке."}</p><p class="callout">${esc(state.notice)}</p></div><img class="nika" src="assets/art/nika.png" alt="Ника благодарит за работу"></div><h2>Итоговая подборка</h2><div class="result-grid">${exp.predictions.map(p => predictionCard(p)).join('')}</div><div class="navigation"><button class="secondary" data-action="labels">К своим снимкам</button><button class="primary" data-action="reset">Начать новую смену</button></div></article></section>`;
  }
  function explain(image) {
    const state = model.state;
    const predictions = state.phase === 'final' ? state.current.final.predictions : state.current.review.predictions;
    const prediction = predictions.find(p => p.id === image.id);
    const neighbor = byId[prediction.neighborId];
    return `<h2>Ответ пришёл из учебного примера</h2><p>Этот простой способ сравнивает уменьшенные чёрно-белые снимки. Ближайшим учебным примером оказался ${esc(neighbor.name)}. Модель взяла его текущую подпись: <b>${esc(label(prediction.predicted))}</b>.</p><div class="explain-grid"><div><h3>Проверяемый снимок</h3><img src="${esc(image.src)}" alt="${esc(image.name)}"></div><div><h3>Учебный пример</h3><img src="${esc(neighbor.src)}" alt="${esc(neighbor.name)}"></div></div><p>Похожесть пикселей не всегда означает одинаковый облик галактики. Поэтому проверяем ответ по справочной подписи.</p>${source(neighbor)}`;
  }
  function about() {
    return `<h2>Как устроен этот опыт</h2><p>Это учебная симуляция: опыты с разными подписями рассчитаны заранее. Когда ты меняешь подпись, игра показывает соответствующий результат.</p><p>Модель: ${esc(data.model.name)}. ${esc(data.model.description)}</p><p>«Гладкая», «видна спираль» и «диск с ребра» — признаки видимого облика. Спиральная галактика тоже может быть видна с ребра.</p><p class="compact">Повторная проверка служит для сравнения, а не для независимой научной оценки. В игре нет управления телескопом и отправки данных.</p><p><a href="DATA-NOTES.md" target="_blank">Описание расчёта и данных</a> · <a href="provenance.json" target="_blank">Источники и контрольные суммы</a></p>`;
  }
  function openModal(content, isImage = false) {
    closeModal();
    modalTrigger = document.activeElement;
    modal = document.createElement('div');
    modal.className = 'modal';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-label', isImage ? 'Снимок галактики' : 'Помощь и описание опыта');
    modal.innerHTML = `<div class="modal-box${isImage ? ' image-box' : ''}"><button class="secondary modal-close" data-action="close-modal">Закрыть</button>${content}</div>`;
    document.body.append(modal);
    root.inert = true;
    modal.querySelector('button').focus();
  }
  function closeModal() {
    if (!modal) return;
    modal.remove(); modal = null;
    root.inert = false;
    if (modalTrigger?.isConnected) modalTrigger.focus();
  }
  function render() {
    const phase = model.state.phase;
    root.innerHTML = phase === 'intro' ? intro() : phase === 'tutorial' ? tutorial() : phase === 'labels' ? labelsView() : phase === 'results' ? results() : phase === 'repair' ? repair() : final();
    globalThis.galaxyGame = {model, render};
  }
  function dispatch(type, payload = {}) {
    try {
      model.dispatch({type, ...payload});
      if (type === 'LABELS' || type === 'REPAIR') cardIndex = 0;
      render();
    } catch (error) { alert(error.message); }
  }
  document.addEventListener('click', event => {
    const button = event.target.closest('button');
    if (!button) return;
    const action = button.dataset.action;
    if (button.dataset.labelId) {dispatch('SET_LABEL', {id: button.dataset.labelId, label: button.dataset.label}); return;}
    if (action === 'zoom') {const image = byId[button.dataset.imageId]; openModal(`<img class="modal-image" src="${esc(image.src)}" alt="${esc(image.name)}">`, true); return;}
    if (action === 'help') {const image = byId[button.dataset.imageId]; openModal(`<h2>Как смотреть на снимок</h2><p>${esc(image.explanation)}</p><p>Смотри на общий вид: рукава, ровное свечение или тонкая полоса диска.</p>${source(image)}`); return;}
    if (action === 'explain') {openModal(explain(byId[button.dataset.imageId])); return;}
    if (action === 'about') {openModal(about()); return;}
    if (action === 'close-modal') {closeModal(); return;}
    if (action === 'next') {const max = model.state.phase === 'labels' ? data.childIds.length - 1 : data.oldIds.length - 1; cardIndex = Math.min(max, cardIndex + 1); render(); return;}
    if (action === 'previous') {cardIndex = Math.max(0, cardIndex - 1); render(); return;}
    if (action === 'reset') {if (confirm('Начать смену заново? Все подписи этой смены исчезнут.')) {cardIndex = 0; dispatch('RESET');} return;}
    const map = {start:'START', labels:'LABELS', run:'RUN', repair:'REPAIR', finish:'FINISH', home:'HOME', resume:'RESUME'};
    if (map[action]) dispatch(map[action]);
  });
  document.addEventListener('keydown', event => {
    if (!modal) return;
    if (event.key === 'Escape') {event.preventDefault(); closeModal();}
    if (event.key === 'Tab') {
      const focusable = [...modal.querySelectorAll('button, a[href]')];
      const first = focusable[0], last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) {event.preventDefault(); last.focus();}
      else if (!event.shiftKey && document.activeElement === last) {event.preventDefault(); first.focus();}
    }
  });
  render();
})();
