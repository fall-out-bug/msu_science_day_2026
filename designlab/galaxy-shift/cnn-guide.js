/* Persistent CNN workbench. It describes precomputed experiments and does not train in the browser. */
(function (root) {
  'use strict';
  const esc = value => String(value ?? '').replace(/[&<>"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[char]));
  const names = {r:'ReLU', bn:'BatchNorm', d:'Dropout'};
  function config(state) {
    const selected = root.GalaxyArchitectures?.get?.(state.architecture); if (!selected) throw new Error('Не найдена рассчитанная схема сети.'); return selected;
  }
  function runFor(state) { return state.current || state.architectureBaseline; }
  function predictions(state, data) {
    const result = runFor(state)?.result?.review?.predictions || [];
    if (!result.length) throw new Error('Нет рассчитанных ответов для проверочной выборки.'); return result.slice(0,3);
  }
  function photoRegion(state, options) {
    const cards = predictions(state, options.data);
    const selected = options.activeImageId || cards[0]?.id;
    const image = options.byId?.[selected] || options.byId?.[cards[0]?.id] || {};
    return `<section class="cnn-workbench__photo" data-cnn-region="photo" aria-label="Снимки для опыта"><figure class="cnn-workbench__frame"><button class="cnn-workbench__open" data-action="zoom" data-image-id="${esc(image.id)}" aria-label="Открыть снимок ${esc(image.name)}"><img src="${esc(image.src)}" alt="${esc(image.name || 'Снимок галактики')}"></button><figcaption><span>${esc(image.name || 'Снимок для проверки')}</span><small>Hubble · нажми на снимок для увеличения</small></figcaption></figure><div class="cnn-workbench__thumbs" aria-label="Три проверочных снимка">${cards.map((item,index)=>{const source=options.byId?.[item.id] || {};return `<button type="button" aria-pressed="${item.id===selected}" aria-label="Снимок ${index+1}: ${esc(source.name || item.id)}" class="${item.id===selected?'selected':''}" data-action="cnn-image" data-image-id="${esc(item.id)}"><img src="${esc(source.src)}" alt=""><span>${index+1}</span></button>`;}).join('')}</div></section>`;
  }
  function chain(selected) {
    const convolution = selected.depth === 2 ? '<b>Свёртка</b><i>→</i><b>ReLU</b><i>→</i><b>Свёртка</b><i>→</i>' : '<b>Свёртка</b><i>→</i>';
    return `<div class="architecture-fixed">Снимок <small>32 × 32 · оттенки серого</small><i>→</i>${convolution}</div>`;
  }
  function mentor(stage) {
    const copy = {
      bridge:'Мы проверили старые метки и снова получили ответы на тех же трёх снимках. Хочешь посмотреть, как устроена готовая сеть, которая их различает?',
      intro:'Это CNN — свёрточная нейронная сеть. Слои преобразуют снимок, а архитектура задаёт их типы и порядок. Свёртка ищет признаки, например границы света. Добавим вторую свёртку: изменятся ли ответы?',
      compare:'Вторая свёртка добавлена. Метки и проверочные снимки не менялись; браузер откроет заранее рассчитанный результат с двумя свёртками.',
      observe:'Сравни ответы на каждом снимке: совпадение со справочной меткой и изменение ответа — разные вещи. Хочешь разобраться, какие классы модель путает? Открой «Ошибки и метрики».',
      independent:'Теперь проведи один собственный опыт. Можно изменить число свёрток, добавить BatchNorm или Dropout либо поменять порядок слоёв. Выбери изменение и проверь сеть на тех же снимках.',
      'independent-observe':'Сравни ответы твоей схемы с предыдущей проверенной сетью. Улучшение не обязательно: важнее увидеть, что именно изменилось. В «Ошибках и метриках» посмотрим, какие классы модель путает.',
      complete:'Собственный опыт завершён. Хочешь продолжить — меняй схему и проверяй новые варианты. А можно перейти к итоговым снимкам при любом результате.'
    };
    return `<aside class="cnn-workbench__nika"><img src="assets/art/nika-thinking-v1.png" alt="Ника"><div><span>НИКА</span><p>${copy[stage] || copy.intro}</p></div></aside>`;
  }
  function resultRegion(state, options) {
    const current = state.current;
    const previous = state.architectureBaseline ||
      (current && state.baseline?.labelKey !== current.labelKey ? state.baseline : null);
    const before = previous?.result.review.predictions || [];
    const after = current?.result.review.predictions || [];
    const cards = predictions(state, options.data);
    const label = id => options.data.classes.find(item => item.id === id)?.label || '—';
    let comparison = '';
    if (previous && current) {
      const changes = after.filter(item => item.predicted !== before.find(old => old.id === item.id)?.predicted).length;
      const inputs = previous.labelKey !== current.labelKey;
      const architecture = previous.architecture !== current.architecture;
      const cause = inputs && architecture ? 'Изменены и метки, и архитектура: их влияние здесь нельзя разделить.'
        : architecture ? 'Метки те же; изменена архитектура.'
        : inputs ? 'Архитектура та же; изменены метки обучающих снимков.' : 'Метки и архитектура те же.';
      const difference = current.result.review.correct - previous.result.review.correct;
      const outcome = difference ? `Правильных ответов стало ${difference > 0 ? 'больше' : 'меньше'}: ${previous.result.review.correct} → ${current.result.review.correct}.`
        : `Число правильных ответов не изменилось: ${current.result.review.correct} из ${current.result.review.total}.`;
      comparison = `<p class="cnn-workbench__comparison" data-comparison>${cause} ${changes ? `Изменилось ответов: ${changes} из ${after.length}.` : 'Предсказания не изменились.'} ${outcome}</p>`;
    }
    const run = current || previous;
    return `<section class="cnn-workbench__results" data-cnn-region="results" aria-label="Ответы на трёх проверочных снимках"><header><b>${current ? 'Ответы модели' : 'Прежние ответы'}</b><small>Совпадений: ${run.result.review.correct} из ${run.result.review.total}</small></header><div>${cards.map((item,index) => {
      const old=before.find(value=>value.id===item.id), next=after.find(value=>value.id===item.id), source=options.byId[item.id];
      return `<article><img src="${esc(source.src)}" alt=""><p>${esc(source.name)}</p><small>Справочная: <b>${esc(label(item.expected))}</b></small>${old ? `<small>До: <b>${esc(label(old.predicted))}</b></small>` : ''}${next ? `<small>${old ? 'После' : 'Модель'}: <b>${esc(label(next.predicted))}</b></small>` : ''}</article>`;
    }).join('')}</div>${current ? comparison : '<p class="cnn-workbench__comparison">Новая схема ещё не проверена. Здесь ответы предыдущей сети.</p>'}</section>`;
  }
  function filterExample() {
    return `<p>Свёртка поэлементно умножает числа фильтра на значения пикселей небольшого участка, затем складывает произведения. Получается <b>отклик</b> фильтра.</p><div class="cnn-filter-example"><div><b>Участок</b><pre>1 0 1
0 1 0
1 0 1</pre></div><span>×</span><div><b>Фильтр</b><pre>1 0 1
0 1 0
1 0 1</pre></div><span>→</span><div><b>Отклик</b><p>5</p></div></div><p>1·1 + 0·0 + 1·1 + 0·0 + 1·1 + 0·0 + 1·1 + 0·0 + 1·1 = <b>5</b>.</p><p>Здесь 1 обозначает светлый пиксель, а 0 — тёмный. В обучаемой сети числа фильтра подбираются по примерам. Это учебная иллюстрация, <b>не активация рассчитанной сети</b>.</p>`;
  }
  function editor(state, stage) {
    const free = ['independent', 'complete'].includes(stage);
    const guided = !free;
    const selected = config(state);
    const tail=selected.tail || ['r'];
    const chips=tail.map((layer,index)=>`<li draggable="${guided?'false':'true'}" tabindex="${guided ? -1 : 0}" data-layer-index="${index}" data-layer="${layer}" aria-label="${names[layer]}, слой ${index+1}."><b>${names[layer]}</b><button class="text-button" data-action="layer-info" data-layer="${layer}">О слое</button><div><button class="text-button" data-action="layer-earlier" data-layer-index="${index}" ${guided||!index?'disabled':''}>← Раньше</button><button class="text-button" data-action="layer-later" data-layer-index="${index}" ${guided||index>=tail.length-1?'disabled':''}>Позже →</button>${layer !== 'r'?`<button class="text-button" data-action="layer-remove" data-layer="${layer}" ${guided?'disabled':''}>Удалить</button>`:'<small>Обязательный слой</small>'}</div></li>`).join('');
    const guideAction = stage === 'intro' ? '<button class="primary" data-action="guide-add-convolution">Добавить вторую свёртку →</button>' : '';
    const bridge = stage === 'bridge' ? '<div class="cnn-workbench__bridge-question"><p>Мы сравнили ответы после проверки меток. Следующий вопрос: как сама сеть рассматривает снимок?</p><button class="primary" data-action="guide-open">Посмотреть готовую сеть →</button></div>' : '';
    const locked = stage === 'bridge' ? ' aria-hidden="true" inert' : '';
    return `<section class="architecture-editor architecture-editor--${esc(stage)}" aria-label="Схема нейронной сети">${bridge}<div class="architecture-editor__scheme"${locked}><div class="architecture-depth"><span>Свёрточных слоёв</span>${[1,2].map(depth=>`<button data-action="architecture-depth" data-depth="${depth}" class="${selected.depth===depth?'selected':''}" aria-pressed="${selected.depth===depth}" ${guided?'disabled':''}>${depth}</button>`).join('')}</div><div class="architecture-tail">${chain(selected)}<ol data-architecture-tail>${chips}</ol><div class="architecture-output-step"><strong>Глобальное усреднение</strong><small>Среднее значение каждой карты признаков</small></div><div class="architecture-output-step"><strong>Линейный слой</strong><small>Вычисляет оценки классов</small></div><div class="architecture-output-step"><strong>Softmax</strong><small>Преобразует оценки в числа от 0 до 1 с суммой 1</small></div><div class="architecture-output-step"><strong>Класс</strong><small>Класс с наибольшим значением — ответ модели</small></div></div><div class="architecture-add">${guideAction}<button data-action="layer-add" data-layer="bn" ${guided||tail.includes('bn')?'disabled':''}>Добавить BatchNorm</button><button data-action="layer-add" data-layer="d" ${guided||tail.includes('d')?'disabled':''}>Добавить Dropout</button></div><p class="architecture-current" aria-live="polite">${guided ? (state.current ? `Проверена схема: ${esc(selected.label)}.` : 'Схема изменена. Проверь её на тех же снимках.') : `Выбрана <b>${esc(selected.label || selected.id)}</b>. Метки и проверочные снимки остаются теми же.`}</p></div></section>`;
  }
  function actions(stage, state, selected) {
    const independentNeedsChange = stage === 'independent' && (!state.independentBaseline ||
      state.architecture === state.independentBaseline.architecture || state.current);
    let primary = stage === 'bridge' ? ''
      : stage === 'intro' ? ''
      : stage === 'compare' ? '<button class="primary" data-action="run">Проверить на тех же снимках →</button>'
      : stage === 'observe' ? '<button class="primary" data-action="guide-confirm-compare">Я сравнил ответы →</button>'
      : stage === 'independent' ? `<button class="primary" data-action="architecture-save" data-architecture="${esc(selected.id)}" ${independentNeedsChange ? 'disabled' : ''}>Проверить своё изменение →</button>`
      : stage === 'independent-observe' ? '<button class="primary" data-action="independent-confirm">Я сравнил ответы →</button>'
      : `<button class="${state.current ? 'secondary' : 'primary'}" data-action="architecture-save" data-architecture="${esc(selected.id)}">${state.current ? 'Повторить проверку' : 'Проверить модель →'}</button>`;
    const metrics = ['observe','independent','independent-observe','complete'].includes(stage) ? '<button class="secondary" data-action="metrics">Ошибки и метрики</button>' : '';
    const secondary = stage === 'complete' ? `<button class="secondary" data-action="labels">К разметке</button><button class="secondary" data-action="folder">Обучающая выборка</button>${metrics}` : metrics;
    const finish = stage === 'complete' && state.current ? '<button class="primary" data-action="finish">К итоговым снимкам →</button>' : '';
    return `<footer class="cnn-workbench__actions" data-cnn-region="actions">${secondary}${primary}${finish}</footer>`;
  }
  function render(state, options = {}) {
    const stage=state.cnnGuide || 'intro', selected=config(state);
    const help = stage === 'bridge' ? '' : '<button class="text-button" data-action="cnn-filter">Как работает свёртка?</button><button class="text-button" data-action="cnn-layers">Что делают остальные слои?</button>';
    const guide = `<div class="cnn-workbench__guide" data-cnn-region="guide">${mentor(stage)}${help}</div>`;
    return `<section class="cnn-workbench cnn-workbench--${esc(stage)}" data-cnn-stage="${esc(stage)}">${photoRegion(state,options)}<div class="cnn-workbench__centre">${guide}</div>${editor(state,stage)}${resultRegion(state,options)}${actions(stage,state,selected)}</section>`;
  }
  root.GalaxyCNNGuide = Object.freeze({render, filterExample});
})(globalThis);
