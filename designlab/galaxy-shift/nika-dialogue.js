/* Contextual, non-grading conversation with Nika. It is independent from the
   game state machine: callers supply the current image and, after a run, the
   actual CNN prediction. */
(function (root) {
  'use strict';
  let active = null;
  const labelNames = { smooth: 'гладкая', spiral: 'видна спираль', edge_on: 'вид с ребра' };
  const observe = {
    arms: 'рукава', smooth: 'гладкое свечение', edge: 'галактику с ребра'
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

    function view(mood, eyebrow, lead, content, choices) {
      return { mood, eyebrow, lead, content, choices };
    }
    function storyDetail(includeKind = false) {
      const parts = [];
      if (includeKind && story.kind) parts.push(`Раздел карточки: ${story.kind}`);
      if (story.detail) parts.push(story.detail);
      if (story.locationNote) parts.push(story.locationNote);
      return parts.length ? parts.map(esc).join('<br><br>') : 'В этой карточке нет дополнительного пояснения.';
    }
    function observationStart() {
      return view('curious', 'СМОТРИМ НА СНИМОК', `Посмотри на ${esc(image.name)}. Не спеши с меткой: какая деталь заметнее всего?`,
        '<p class="nika-dialogue__prompt">Посмотри на форму и на то, как распределён свет.</p>',
        [{ id: 'arms', text: 'Вижу рукава' }, { id: 'smooth', text: 'Вижу гладкое свечение' }, { id: 'edge', text: 'Вижу галактику с ребра' }]);
    }
    function observationReply() {
      const followup={arms:'Попробуй проследить один рукав от центра наружу. Он изгибается? Видны ли похожие детали с другой стороны?',smooth:'Сравни центр и края: свечение плавно слабеет или распадается на отдельные полосы и пятна?',edge:'Посмотри, насколько вытянута галактика. Видна узкая полоса? Отличается ли её середина от краёв?'}[answer];
      return view('thinking', 'ТВОЁ НАБЛЮДЕНИЕ', followup,
        `<div class="nika-dialogue__quote">Ты: «Вижу ${esc(observe[answer])}».</div><p>Можно ещё рассмотреть детали или вернуться к снимку и выбрать метку.</p>`,
        [{ id: 'hint', text: 'Попросить подсказку' }, { id: 'back', text: 'Посмотреть ещё раз', primary: true }, { id: 'close', text: 'Вернуться к снимку' }]);
    }
    function hint() {
      return view('warm', 'ПОДСКАЗКА К СНИМКУ', `В описании ${esc(image.name)} есть такая деталь:`,
        `<div class="nika-dialogue__quote">${esc(image.explanation)}</div><p>Покажи её пальцем на изображении. Затем сам реши, какая метка лучше описывает то, что видно.</p>`,
        [{ id: 'back', text: 'Посмотреть снимок ещё раз', primary: true }, { id: 'close', text: 'Закрыть разговор' }]);
    }
    function resultStart() {
      return view('curious', 'РАЗБИРАЕМ ОТВЕТ', `У ${esc(image.name)} есть ответ модели. Давай выясним, откуда он взялся, а не будем ему просто верить.`, '',
        [{ id: 'why', text: 'Почему такой ответ?', primary: true }, { id: 'change', text: 'Поможет другая метка?' }, { id: 'limits', text: 'Насколько модель уверена?' }]);
    }
    function why() {
      const prediction = options.prediction || {};
      return view('thinking', 'ОТКУДА ОТВЕТ', `Модель выбрала метку «${esc(label(prediction.predicted))}».`,
        '<p>Свёрточная сеть училась на девяти снимках с метками. Изображение состоит из маленьких элементов — пикселей. Числа описывают их яркость. Свёрточные слои обрабатывают эти числа на небольших участках. Затем сеть выбирает метку по результатам обработки.</p><p>Мы видим ответ, но этот экран не показывает, какие именно детали привели к выбору. Проверим ответ по снимку и справочной метке.</p>',
        [{ id: 'change', text: 'Поможет другая метка?' }, { id: 'limits', text: 'Насколько модель уверена?' }, { id: 'result-back', text: 'К вопросам', primary: true }]);
    }
    function change() {
      return view('warm', 'ПРОВЕРЯЕМ ПРИЧИНУ', 'Исправленная учебная метка может изменить ответы после нового обучения. Проверим это опытом.',
        '<p>Меняй подпись, если она не соответствует снимку. Затем сравни ответы на тех же проверочных изображениях при том же устройстве модели. Исправление не обязано устранить каждую ошибку.</p>',
        [{ id: 'why', text: 'Как получен ответ?' }, { id: 'limits', text: 'Насколько модель уверена?' }, { id: 'result-back', text: 'К вопросам', primary: true }]);
    }
    function limits() {
      return view('warm', 'ЧЕСТНЫЙ ОТВЕТ', 'Большая оценка выбранной категории ещё не гарантирует правильный ответ.',
        '<p>Модель обучалась всего на девяти примерах. Даже если она выделила одну метку сильнее других, это не доказывает, что ответ верный. Поэтому мы сравниваем ответы со справочными метками. Три проверочных снимка помогают разобрать этот опыт, но не показывают, насколько хорошо модель работает со всеми галактиками.</p>',
        [{ id: 'why', text: 'Почему такой ответ?' }, { id: 'change', text: 'Поможет другая метка?' }, { id: 'result-back', text: 'К вопросам', primary: true }]);
    }
    function storyStart() {
      return view('curious', 'КАРТОЧКА НА КАРТЕ', `${esc(story.title || image.name)}. Что хочешь узнать об этой истории?`, '',
        [{ id: 'story-found', text: 'Расскажи об этом', primary: true }, { id: 'story-ai', text: 'Что мы видим на картинке?' }, { id: 'story-check', text: 'Что важно учесть?' }]);
    }
    function storyFound() {
      return view('warm', 'ОБ ЭТОЙ ИСТОРИИ', esc(story.title || image.name),
        `<div class="nika-dialogue__quote">${esc(story.text || 'В карточке нет описания находки.')}</div>`,
        [{ id: 'story-ai', text: 'Что мы видим на картинке?' }, { id: 'story-check', text: 'Что важно учесть?' }, { id: 'story-back', text: 'К вопросам', primary: true }]);
    }
    function storyAi() {
      return view('thinking', 'СМОТРИМ НА ИЗОБРАЖЕНИЕ', esc(story.title || image.name),
        `<div class="nika-dialogue__quote">${esc(story.alt)}<br>${esc(story.locationNote)}</div>`,
        [{ id: 'story-found', text: 'Расскажи об этом' }, { id: 'story-check', text: 'Что важно учесть?' }, { id: 'story-back', text: 'К вопросам', primary: true }]);
    }
    function storyCheck() {
      return view('warm', 'ЧТО ВАЖНО УЧЕСТЬ', esc(story.title || image.name),
        `<div class="nika-dialogue__quote">${storyDetail()}</div>`,
        [{ id: 'story-found', text: 'Расскажи об этом' }, { id: 'story-ai', text: 'Что мы видим на картинке?' }, { id: 'story-back', text: 'К вопросам', primary: true }]);
    }
    function render() {
      const views = { 'observe-start': observationStart, 'observe-reply': observationReply, hint, 'result-start': resultStart, why, change, limits, 'story-start': storyStart, 'story-found': storyFound, 'story-ai': storyAi, 'story-check': storyCheck };
      const next = views[mode]();
      const card = overlay.querySelector('.nika-dialogue__card');
      card.querySelector('.nika-dialogue__portrait').src = portrait(next.mood);
      card.querySelector('.nika-dialogue__portrait').dataset.mood = next.mood;
      card.querySelector('.nika-dialogue__eyebrow').textContent = next.eyebrow;
      card.querySelector('.nika-dialogue__lead').innerHTML = next.lead;
      card.querySelector('.nika-dialogue__body').innerHTML = next.content;
      card.querySelector('.nika-dialogue__actions').innerHTML = next.choices.map(item => `<button type="button" data-nika="${item.id}" class="${item.primary ? 'nika-dialogue__primary' : ''}">${item.text}</button>`).join('');
      (next.content ? card.querySelector('.nika-dialogue__body') : card.querySelector('[data-nika]'))?.focus({ preventScroll: true });
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
    overlay.innerHTML = `<section class="nika-dialogue__card"><header class="nika-dialogue__head"><img class="nika-dialogue__portrait" src="${portrait('curious')}" alt="Ника, астроном"><div><span class="nika-dialogue__eyebrow"></span><b>Ника</b><p class="nika-dialogue__lead"></p></div><button type="button" class="nika-dialogue__close" data-nika="close" aria-label="Закрыть разговор">×</button></header><div class="nika-dialogue__context"><img src="${esc(image.src)}" alt="${esc(image.name)}"><span>Снимок · ${esc(image.name)}</span></div><div class="nika-dialogue__body" tabindex="-1"></div><div class="nika-dialogue__actions"></div></section>`;
    render();
    return controller;
  }
  root.NikaDialogue = { open };
})(globalThis);
