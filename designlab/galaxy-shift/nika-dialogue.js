/* Contextual, non-grading conversation with Nika. It is independent from the
   game state machine: callers supply the current image and, after a run, the
   actual prediction and nearest example. */
(function (root) {
  'use strict';
  let active = null;
  const labelNames = { smooth: 'гладкая', spiral: 'видна спираль', edge_on: 'вид с ребра' };
  const observe = {
    arms: 'рукава', smooth: 'ровный свет', edge: 'диск с ребра'
  };

  function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
  }
  function label(value) { return labelNames[value] || String(value || 'метка'); }
  function portrait(mood) { return `assets/art/nika-${mood}-v1.png`; }
  function focusable(dialog) { return [...dialog.querySelectorAll('button:not([disabled]),a[href],input:not([disabled])')]; }

  function open(options) {
    if (!options?.image) throw new Error('Для разговора нужен снимок.');
    active?.close();
    const image = options.image;
    const previousFocus = document.activeElement;
    const protectedNodes = [document.querySelector('#game'), document.querySelector('.sky-atlas'), document.querySelector('.modal')].filter(Boolean)
      .map(node => ({ node, inert: node.inert }));
    protectedNodes.forEach(({ node }) => { node.inert = true; });

    const overlay = document.createElement('div');
    overlay.className = 'nika-dialogue';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-label', 'Разговор с Никой о снимке ' + image.name);
    document.body.append(overlay);
    let closed = false;
    const story = options.story || null;
    let mode = story ? 'story-start' : (options.prediction ? 'result-start' : 'observe-start');
    let answer = null;

    function close() {
      if (closed) return;
      closed = true;
      document.removeEventListener('keydown', onKeydown, true);
      overlay.remove();
      protectedNodes.forEach(({ node, inert }) => { if (node.isConnected) node.inert = inert; });
      if (previousFocus?.isConnected) previousFocus.focus({ preventScroll: true });
      options.onClose?.();
      if (active?.element === overlay) active = null;
    }

    function header(mood, eyebrow, text) {
      return `<header class="nika-dialogue__head"><img src="${portrait(mood)}" alt="Ника, астроном" data-mood="${mood}"><div><span>${eyebrow}</span><b>Ника</b><p>${text}</p></div><button type="button" class="nika-dialogue__close" data-nika="close" aria-label="Закрыть разговор">×</button></header>`;
    }
    function actions(items) {
      return `<div class="nika-dialogue__actions">${items.map(item => `<button type="button" data-nika="${item.id}" class="${item.primary ? 'nika-dialogue__primary' : ''}">${item.text}</button>`).join('')}</div>`;
    }
    function imagePanel(item = image, caption = `Снимок · ${item.name}`) {
      return `<figure class="nika-dialogue__image"><img src="${esc(item.src)}" alt="${esc(item.name)}"><figcaption>${esc(caption)}</figcaption></figure>`;
    }
    function storyDetail(includeKind = false) {
      const parts = [];
      if (includeKind && story.kind) parts.push(`Раздел карточки: ${story.kind}`);
      if (story.detail) parts.push(story.detail);
      if (story.locationNote) parts.push(story.locationNote);
      return parts.length ? parts.map(esc).join('<br><br>') : 'В этой карточке нет дополнительного пояснения.';
    }
    function observationStart() {
      return `${header('curious', 'СМОТРИМ НА СНИМОК', `Посмотри на ${esc(image.name)}. Не спеши с меткой: какая деталь заметнее всего?`)}
        ${imagePanel()}
        <p class="nika-dialogue__prompt">Посмотри на форму и распределение света.</p>
        ${actions([{ id: 'arms', text: 'Вижу рукава' }, { id: 'smooth', text: 'Вижу ровный свет' }, { id: 'edge', text: 'Вижу диск с ребра' }])}`;
    }
    function observationReply() {
      const followup={arms:'Попробуй проследить один рукав от центра наружу. Он изгибается? Видны ли похожие детали с другой стороны?',smooth:'Сравни центр и края: свет плавно тускнеет или распадается на отдельные полосы и пятна?',edge:'Посмотри, насколько вытянута галактика. Видна узкая полоса? Отличается ли её середина от краёв?'}[answer];
      return `${header('thinking', 'ТВОЁ НАБЛЮДЕНИЕ', `${followup}`)}
        ${imagePanel()}
        <div class="nika-dialogue__quote">Ты: «Вижу ${esc(observe[answer])}».</div>
        <p>Можно ещё рассмотреть детали или вернуться к снимку и выбрать метку.</p>
        ${actions([{ id: 'hint', text: 'Попросить подсказку' }, { id: 'back', text: 'Посмотреть ещё раз', primary: true }, { id: 'close', text: 'Вернуться к снимку' }])}`;
    }
    function hint() {
      return `${header('warm', 'ПОДСКАЗКА К СНИМКУ', `В описании ${esc(image.name)} есть такая деталь:`)}
        ${imagePanel()}
        <div class="nika-dialogue__quote">${esc(image.explanation)}</div>
        <p>Покажи её пальцем на изображении. Затем сам реши, какая метка лучше описывает то, что видно.</p>
        ${actions([{ id: 'back', text: 'Посмотреть снимок ещё раз', primary: true }, { id: 'close', text: 'Закрыть разговор' }])}`;
    }
    function resultStart() {
      return `${header('curious', 'РАЗБИРАЕМ ОТВЕТ', `У ${esc(image.name)} есть ответ модели. Давай выясним, откуда он взялся, а не будем ему просто верить.`)}
        ${imagePanel(image, `Проверяемый снимок · ${image.name}`)}
        ${actions([{ id: 'why', text: 'Почему такой ответ?', primary: true }, { id: 'change', text: 'Поможет другая метка?' }, { id: 'limits', text: 'Насколько модель уверена?' }])}`;
    }
    function why() {
      const prediction = options.prediction || {};
      const neighbor = options.neighbor;
      const neighborText = neighbor ? `Ближайшим учебным примером оказался ${esc(neighbor.name)}. Его метка — «${esc(label(prediction.predicted || neighbor.label))}».` : 'Ближайший учебный пример не передан в этот разговор.';
      return `${header('thinking', 'ОТКУДА ОТВЕТ', neighborText)}
        ${neighbor ? `<div class="nika-dialogue__pair">${imagePanel(image, `Проверяемый снимок · ${image.name}`)}${imagePanel(neighbor, `Ближайший учебный пример · ${neighbor.name}`)}</div>` : imagePanel(image, `Проверяемый снимок · ${image.name}`)}
        <p>Программа сравнила заранее измеренные признаки яркости, а не прочитала название объекта и не увидела смысл снимка как человек. Похожие числа могут встретиться у галактик разного вида.</p>
        ${actions([{ id: 'change', text: 'Поможет другая метка?' }, { id: 'limits', text: 'Насколько модель уверена?' }, { id: 'result-back', text: 'К вопросам', primary: true }])}`;
    }
    function change() {
      const neighbor = options.neighbor;
      const editable = ['child', 'old'].includes(neighbor?.role);
      const text = !neighbor ? 'Сначала нужно увидеть ближайший учебный пример.' : editable
        ? `Да, если изменить метку у ${esc(neighbor.name)}, этот ответ изменится: программа повторяет метку ближайшего примера. Но сначала проверь снимок и причину исправления.`
        : `Не в этом случае. Ближайший пример — ${esc(neighbor.name)}, а его метку в задании не меняют. Другая метка у далёкого примера на этот ответ не повлияет.`;
      return `${header(editable ? 'warm' : 'warm', 'ПРОВЕРЯЕМ ПРИЧИНУ', text)}
        ${imagePanel(image, `Проверяемый снимок · ${image.name}`)}
        <p>Изменение метки не меняет сами признаки и не делает изображение ближе или дальше. Оно меняет только подпись, которую модель может повторить.</p>
        ${actions([{ id: 'why', text: 'Почему это ближайший пример?' }, { id: 'limits', text: 'Насколько модель уверена?' }, { id: 'result-back', text: 'К вопросам', primary: true }])}`;
    }
    function limits() {
      return `${header('warm', 'ЧЕСТНЫЙ ОТВЕТ', 'У этой модели нет числа уверенности, которому можно просто поверить.')}
        ${imagePanel(image, `Проверяемый снимок · ${image.name}`)}
        <p>Она сравнивает только девять учебных примеров текущей смены и несколько чисел из яркости изображения. Маленькое расстояние не доказывает, что ответ верный. Поэтому мы смотрим на справочную метку и проверяем ошибки.</p>
        ${actions([{ id: 'why', text: 'Почему такой ответ?' }, { id: 'change', text: 'Поможет другая метка?' }, { id: 'result-back', text: 'К вопросам', primary: true }])}`;
    }
    function storyStart() {
      return `${header('curious', 'КАРТОЧКА НА КАРТЕ', `${esc(story.title || image.name)}. Что хочешь узнать об этой истории?`)}
        ${imagePanel(image, `Снимок к карточке · ${image.name}`)}
        ${actions([{ id: 'story-found', text: 'Расскажи об этом', primary: true }, { id: 'story-ai', text: 'Что мы видим на картинке?' }, { id: 'story-check', text: 'Что важно учесть?' }])}`;
    }
    function storyFound() {
      return `${header('warm', 'ОБ ЭТОЙ ИСТОРИИ', esc(story.title || image.name))}
        ${imagePanel(image, `Снимок к карточке · ${image.name}`)}
        <div class="nika-dialogue__quote">${esc(story.text || 'В карточке нет описания находки.')}</div>
        ${actions([{ id: 'story-ai', text: 'Что мы видим на картинке?' }, { id: 'story-check', text: 'Что важно учесть?' }, { id: 'story-back', text: 'К вопросам', primary: true }])}`;
    }
    function storyAi() {
      return `${header('thinking', 'СМОТРИМ НА ИЗОБРАЖЕНИЕ', esc(story.title || image.name))}
        ${imagePanel(image, `Снимок к карточке · ${image.name}`)}
        <div class="nika-dialogue__quote">${esc(story.alt)}<br>${esc(story.locationNote)}</div>
        ${actions([{ id: 'story-found', text: 'Расскажи об этом' }, { id: 'story-check', text: 'Что важно учесть?' }, { id: 'story-back', text: 'К вопросам', primary: true }])}`;
    }
    function storyCheck() {
      return `${header('warm', 'ЧТО ВАЖНО УЧЕСТЬ', esc(story.title || image.name))}
        ${imagePanel(image, `Снимок к карточке · ${image.name}`)}
        <div class="nika-dialogue__quote">${storyDetail()}</div>
        ${actions([{ id: 'story-found', text: 'Расскажи об этом' }, { id: 'story-ai', text: 'Что мы видим на картинке?' }, { id: 'story-back', text: 'К вопросам', primary: true }])}`;
    }
    function render() {
      const views = { 'observe-start': observationStart, 'observe-reply': observationReply, hint, 'result-start': resultStart, why, change, limits, 'story-start': storyStart, 'story-found': storyFound, 'story-ai': storyAi, 'story-check': storyCheck };
      overlay.innerHTML = `<section class="nika-dialogue__card">${views[mode]()}</section>`;
      overlay.querySelector('[data-nika]')?.focus({ preventScroll: true });
    }
    function act(id) {
      if (id === 'close') return close();
      if (id === 'arms' || id === 'smooth' || id === 'edge') { answer = id; mode = 'observe-reply'; }
      else if (id === 'back') mode = 'observe-start';
      else if (id === 'result-back') mode = 'result-start';
      else if (id === 'story-back') mode = 'story-start';
      else mode = id;
      render();
    }
    function onClick(event) {
      if (event.target === overlay) return close();
      const button = event.target.closest('[data-nika]');
      if (button) act(button.dataset.nika);
    }
    function onKeydown(event) {
      if (!overlay.contains(event.target)) return;
      event.stopPropagation();
      if (event.key === 'Escape') { event.preventDefault(); close(); return; }
      if (event.key !== 'Tab') return;
      const items = focusable(overlay);
      const first = items[0], last = items.at(-1);
      if (!first) return;
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
    overlay.addEventListener('click', onClick);
    document.addEventListener('keydown', onKeydown, true);
    const controller = { element: overlay, close };
    active = controller;
    render();
    return controller;
  }
  root.NikaDialogue = { open };
})(globalThis);
