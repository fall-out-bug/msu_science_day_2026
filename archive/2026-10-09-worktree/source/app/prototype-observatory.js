// THROWAWAY: richer game interface for variant A; B/C remain comparison controls.
let blinkTimer;
const sectorPositions = [[23, 23], [70, 16], [45, 46], [78, 66], [19, 77], [48, 87]];
function recordObservation(text) {
  s.log.push({ number: ++s.logNumber, text });
  if (s.log.length > 20) s.log.shift();
}
const observationLabels = { changed: 'Вижу изменение', same: 'Не вижу изменения', unsure: 'Пока не могу понять' };
const verdictLabels = { sky: 'Изменился объект на небе', artifact: 'Похоже на помеху', stable: 'Убедительного изменения нет', uncertain: 'Пока не знаю' };
function investigationStep(c) {
  if (!s.predictions[c.id]) return 0;
  if (!s.checks.has(c.id)) return 1;
  if (!s.decisions[c.id] || s.revising === c.id) return 2;
  return 3;
}
function briefing() {
  return `<section class="first-briefing">
    <div class="briefing-copy"><span class="console-kicker">АРХИВ НЕИЗВЕСТНОГО / ВАШЕ ЗАДАНИЕ</span>
      <h1>Найдите то,<br>что изменилось.</h1>
      <p class="briefing-lead">Телескоп несколько раз снял одни и те же участки неба. Ваша задача — заметить изменения и разобраться, что могло их вызвать.</p>
      <ol class="briefing-steps">
        <li><b>1</b><span><strong>Сравните два снимка</strong>Ищите точку, которая сдвинулась, появилась или стала ярче.</span></li>
        <li><b>2</b><span><strong>Проверьте догадку</strong>Получите третий снимок: повторяется ли замеченное изменение? Подсказка алгоритма доступна отдельно, но не обязательна.</span></li>
        <li><b>3</b><span><strong>Выберите объяснение</strong>Изменился объект? Это помеха? Не уверены? Ответ «пока не знаю» тоже подходит.</span></li>
      </ol>
      <button class="primary start-investigation" data-action="start-investigation">${s.started ? 'Вернуться к исследованию' : 'Начать с первого участка'} →</button>
      <p class="briefing-note">Шесть участков · без таймера и штрафов · в конце — разбор ваших версий</p>
      <button class="text-button discovery-link" data-action="discovery">А что ИИ уже помог открыть в настоящем космосе? →</button>
    </div>
    <div class="briefing-preview"><span class="console-kicker">ОДИН УЧАСТОК НЕБА. ДВА МОМЕНТА.</span>
      <div class="briefing-pair">${[0, 1].map(e => `<figure><img src="${cases[0].frames[e]}" alt="Первый учебный участок, снимок ${e + 1}"><figcaption>Снимок ${e + 1}</figcaption></figure>`).join('')}</div>
      <p>Светлые точки — изображения источников света. Не каждое отличие означает открытие: иногда это шум или помеха.</p>
      <span class="briefing-note">Снимки учебные, синтетические. Знание астрономии не требуется.</span>
    </div>
  </section>`;
}
function investigationActions(c, step) {
  if (step === 0) return `<div class="first-answer">${Object.entries(observationLabels).map(([value, label]) => `<button data-action="first-answer" data-value="${value}">${label}</button>`).join('')}</div><p class="action-note">Записываем только то, что вы заметили. Причину изменения будем обсуждать после проверки.</p>`;
  if (step === 1) return `<p class="answer-receipt">Ваше наблюдение: <strong>${observationLabels[s.predictions[c.id]]}</strong></p><p class="action-note evidence-purpose">На двух снимках помеха может выглядеть как интересный объект. Третий снимок даст ещё одно наблюдение — без подсказки готового ответа.</p><button class="primary next-action" data-action="check">Получить третий снимок →</button>`;
  if (step === 2) {
    const meanings = {sky:'Похоже, сместилась светлая точка или изменилась её яркость.',artifact:'Подозреваю ошибку камеры или обработки, а не изменение в небе.',stable:'Не вижу отличия, которое можно уверенно отделить от шума.',uncertain:'Вижу не всё или не могу объяснить отличие по этим снимкам.'};
    return `<div class="guided-verdicts">${Object.entries(verdictLabels).map(([value, label]) => `<button data-action="decision" data-id="${c.id}" data-value="${value}" aria-pressed="${s.decisions[c.id] === value}" class="${s.decisions[c.id] === value ? 'active' : ''}"><strong>${label}</strong><span>${meanings[value]}</span></button>`).join('')}</div><p class="action-note">Это рабочая версия, не доказательство. Даже третий снимок не всегда снимает сомнения.</p>`;
  }
  const finished = Object.keys(s.decisions).length === cases.length;
  return `<p class="answer-receipt">Сохранено: <strong>${verdictLabels[s.decisions[c.id]]}</strong></p><div class="flow-buttons"><button class="primary next-action" data-action="${finished ? 'finish' : 'next-sector'}">${finished ? 'Все участки разобраны — к итогам' : 'Перейти к следующему участку'} →</button><button class="text-button" data-action="revise">Изменить версию</button></div>`;
}
function comparisonTools(c) {
  const frames = [0, 1, ...(s.checks.has(c.id) ? [2] : [])];
  return `<div class="comparison-tools" aria-label="Управление снимками">
    <div class="instrument-modes" aria-label="Способ сравнения">${[['pair', 'Два рядом'], ['single', 'По одному'], ['compare', 'Ползунок'], ['blink', 'Мигание']].map(([value, label]) => `<button data-action="instrument-mode" data-value="${value}" aria-pressed="${s.mode === value}" class="${s.mode === value ? 'selected' : ''}" ${value === 'blink' && matchMedia('(prefers-reduced-motion: reduce)').matches ? 'disabled title="Анимация отключена настройкой уменьшения движения"' : ''}>${label}</button>`).join('')}</div>
    <div class="frame-selection"><span>${s.mode === 'single' ? 'Показать:' : 'Сравнить снимки:'}</span>${s.mode === 'single' ? frames.map(e => `<button data-action="epoch" data-n="${e}" aria-pressed="${s.epoch === e}" class="${s.epoch === e ? 'selected' : ''}">${e + 1}${e === 2 ? ' · новый' : ''}</button>`).join('') : (frames.length === 3 ? [[0,1],[0,2],[1,2]] : [[0,1]]).map(pair => `<button data-action="frame-pair" data-value="${pair.join(',')}" aria-pressed="${s.pair[0] === pair[0] && s.pair[1] === pair[1]}" class="${s.pair[0] === pair[0] && s.pair[1] === pair[1] ? 'selected' : ''}">${pair[0] + 1} и ${pair[1] + 1}</button>`).join('')}</div>
    <div class="image-assistant"><span>Нужен ещё один взгляд?</span><button class="hint-launch" data-action="ai">${s.insights.has(c.id) ? 'Открыть подсказку снова' : 'Спросить алгоритм'} <small>необязательно</small></button></div>
  </div>`;
}
function instrument(c) {
  const [first, second] = s.pair;
  if (s.mode === 'pair') return `<div class="paired-observations">${[first, second].map(e => `<figure><img src="${c.frames[e]}" alt="${c.name}: снимок ${e + 1}"><figcaption><b>Снимок ${e + 1}</b><span>${e === 0 ? 'Первое наблюдение' : e === 2 ? 'Третье · проверка' : 'Повторное наблюдение'}</span></figcaption></figure>`).join('')}</div><p class="instrument-help">Один участок неба, два момента. Сравнивайте положение и яркость светлых точек, а не каждую крупинку серого фона.</p>`;
  const comparing = s.mode === 'compare';
  const shown = s.mode === 'blink' ? first : comparing ? second : s.epoch;
  return `<div class="instrument" data-mode="${s.mode}" style="--split:${s.split}%">
    <div class="instrument-corner top-left"></div><div class="instrument-corner bottom-right"></div>
    <div class="scope-meta"><span>УЧАСТОК ${String(s.focus + 1).padStart(2, '0')}</span><span>${comparing ? `СНИМКИ ${first + 1} И ${second + 1}` : s.mode === 'blink' ? 'АВТОМАТИЧЕСКАЯ СМЕНА' : `СНИМОК ${s.epoch + 1}`}</span></div>
    <div class="observation-window">
      <img class="observation-base" src="${c.frames[shown]}" alt="${c.name}: снимок ${shown + 1}">
      ${comparing ? `<img class="observation-overlay" src="${c.frames[first]}" alt="${c.name}: снимок ${first + 1}"><span class="comparison-divider"><b>↔</b></span><span class="image-label left">СНИМОК ${first + 1}</span><span class="image-label right">СНИМОК ${second + 1}</span>` : ''}
      <span class="scope-crosshair" aria-hidden="true"></span>
    </div>
    <div class="scope-bottom"><span>${s.mode === 'blink' ? `<span id="blink-frame">СНИМОК ${first + 1}</span>` : 'УЧЕБНЫЙ СНИМОК'}</span><span>ОДИН МАСШТАБ ДЛЯ ВСЕХ КАДРОВ</span></div>
  </div>${comparing ? `<label class="compare-control"><span>Двигайте границу ↔</span><input type="range" min="0" max="100" value="${s.split}" data-control="comparison" aria-label="Граница между снимками"><output>${s.split}%</output></label><p class="instrument-help">Потяните линию на изображении или ползунок под ним. Слева открывается снимок ${first + 1}, справа — снимок ${second + 1}. Это не настройка яркости.</p>` : `<p class="instrument-help">${s.mode === 'blink' ? `Снимки ${first + 1} и ${second + 1} чередуются. Ищите точку, которая «прыгает» или меняет яркость. Кнопка «Два рядом» остановит мигание.` : `Сейчас открыт снимок ${s.epoch + 1}. Для переключения нажмите номер над изображением. Масштаб при смене снимка не меняется.`}</p>`}`;
}
function VariantA() {
  if (!s.started || s.briefing) return briefing();
  const c = cases[s.focus];
  const resolved = Object.keys(s.decisions).length;
  const step = investigationStep(c);
  const prompts = [
    ['Что изменилось между снимками?', 'Снимки сделаны в разные моменты. Посмотрите, не сдвинулась ли светлая точка, не появилась ли новая, не изменилась ли её яркость. Способ сравнения можно выбрать прямо над изображениями.'],
    ['Проверим первое впечатление', 'Вы уже записали, что заметили. Теперь запросите третий снимок: он поможет проверить догадку. Обращаться к алгоритму для этого не нужно.'],
    ['Что говорят три снимка?', 'Проверьте, повторяется ли замеченное изменение на новом снимке. Кнопками над изображениями можно сравнить любую пару или открыть каждый кадр отдельно. Выберите наиболее подходящее объяснение.'],
    ['Этот участок разобран', 'Версия записана, но не стала фактом. Вы можете её пересмотреть, спросить алгоритм или перейти дальше. В конце сравним версии с тем, что было заложено в учебные снимки.']
  ];
  return `<section class="mission-banner">
    <div class="mission-emblem" aria-hidden="true"><span>✦</span><small>07</small></div>
    <div class="mission-title"><span class="console-kicker">ЭКСПЕДИЦИЯ 07 / НОЧНАЯ СМЕНА</span><h1>Архив неизвестного</h1><p>Сравнивайте снимки и проверяйте свои догадки. <button class="text-button" data-action="briefing">Как играть?</button> <button class="text-button discovery-link" data-action="discovery">Реальные открытия ИИ ↗</button></p></div>
    <div class="mission-tally"><div class="tally-ring" style="--progress:${resolved / 6 * 360}deg"><span>${resolved}<small>/ 6</small></span></div><div><strong>участков разобрано</strong><span>Версии можно менять</span></div></div>
  </section>
  <div class="cockpit guided-cockpit">
    <aside class="navigation-deck">
      <div class="deck-heading"><span class="console-kicker">УЧАСТКИ НЕБА</span><span class="status-light">${resolved} / 6</span></div>
      <div class="sector-chart">
        <div class="chart-orbit orbit-one"></div><div class="chart-orbit orbit-two"></div>
        <svg class="chart-lines" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><path d="M23 23 L70 16 L45 46 L78 66 L48 87 L19 77 Z M23 23 L45 46 L19 77 M45 46 L48 87"/></svg>
        <span class="chart-title">КАРТА ЭКСПЕДИЦИИ</span>
        ${cases.map((p, i) => `<button class="chart-node ${s.focus === i ? 'selected' : ''} ${s.marks.has(p.id) ? 'flagged' : ''} ${s.decisions[p.id] ? 'resolved' : ''}" style="left:${sectorPositions[i][0]}%;top:${sectorPositions[i][1]}%" data-action="focus" data-n="${i}" aria-label="Открыть участок ${p.name}" aria-pressed="${s.focus === i}"><i>${s.decisions[p.id] ? '✓' : '0' + (i + 1)}</i><span>${p.name}</span></button>`).join('')}
        <span class="chart-note">Схема, не карта звёздного неба</span>
      </div>
      <div class="sector-roster">${cases.map((p, i) => `<button data-action="focus" data-n="${i}" class="${s.focus === i ? 'selected' : ''}" aria-pressed="${s.focus === i}"><span class="roster-number">0${i + 1}</span><img src="${p.frames[0]}" alt=""><span><strong>${p.name}</strong><small>${s.decisions[p.id] ? 'Версия сохранена' : s.predictions[p.id] ? 'Исследование начато' : 'Ещё не смотрели'}</small></span><i>${s.decisions[p.id] ? '✓' : '·'}</i></button>`).join('')}</div>
      <p class="navigation-hint">Можно вернуться к любому участку. Ваши ответы сохранятся до перезапуска.</p>
    </aside>
    <section class="observation-deck">
      <div class="deck-heading"><span class="console-kicker">УЧАСТОК ${s.focus + 1} ИЗ 6 · ${c.name}</span><button class="icon-button" data-action="zoom" aria-label="Увеличить снимки участка ${c.name}">⤢ <span>Увеличить</span></button></div>
      <div class="flow-heading" tabindex="-1"><span class="console-kicker">${step === 3 ? 'ГОТОВО' : `ШАГ ${step + 1} ИЗ 3`}</span><h2>${prompts[step][0]}</h2><p>${prompts[step][1]}</p></div>
      ${comparisonTools(c)}
      ${instrument(c)}
      <div class="flow-actions" tabindex="-1" aria-label="Следующее действие">${investigationActions(c, step)}</div>
    </section>
    <aside class="investigation-deck guided-reference">
      <div class="deck-heading"><span class="console-kicker">КАК ПРОХОДИТ ИССЛЕДОВАНИЕ</span></div>
      <ol class="route-checklist">${[['Сравните снимки', 'Запишите, что вы заметили'], ['Получите третий снимок', 'Проверьте свою догадку'], ['Выберите объяснение', 'Не уверены? Это тоже ответ']].map(([title, text], i) => `<li class="${step > i ? 'done' : step === i ? 'current' : ''}" ${step === i ? 'aria-current="step"' : ''}><span>${step > i ? '✓' : i + 1}</span><div><strong>${title}</strong><small>${text}</small></div></li>`).join('')}</ol>
      ${s.predictions[c.id] ? `<div class="case-notes"><span class="console-kicker">ВАШИ ЗАПИСИ / ${c.name}</span><p>Первое впечатление:<br><strong>${observationLabels[s.predictions[c.id]]}</strong></p>${s.decisions[c.id] ? `<p>Рабочая версия:<br><strong>${verdictLabels[s.decisions[c.id]]}</strong></p>` : ''}</div>` : '<p class="reference-note">Не нужно знать названия звёзд или разбираться в телескопах. Сначала просто сравните две картинки.</p>'}
      <p class="reference-note hint-independence">${s.insights.has(c.id) ? 'Вы открывали подсказку для этого участка. Она не меняет вашу версию и не заменяет проверку.' : 'Подсказка алгоритма — отдельная кнопка у снимков. Её можно не использовать: весь маршрут доступен без неё.'}</p>
      <button class="discovery-teaser" data-action="discovery"><span class="console-kicker">ЗА ПРЕДЕЛАМИ ТРЕНАЖЁРА</span><strong>ИИ уже помогает<br>исследовать космос</strong><span>Две реальные истории →</span></button>
    </aside>
  </div>
  <section class="expedition-log"><div class="log-title"><span class="console-kicker">ЖУРНАЛ ЭКСПЕДИЦИИ</span><h3>${s.log.length ? 'Ваши последние действия' : 'Исследование начинается'}</h3></div><ol>${s.log.length ? s.log.slice(-3).reverse().map(entry => `<li><span>${String(entry.number).padStart(2, '0')}</span>${entry.text}</li>`).join('') : '<li><span>00</span>Сравните снимки и выберите ответ под ними.</li>'}</ol>${resolved ? '<button class="council-button" data-action="finish">Перейти к разбору <span>→</span><small>Можно закончить, не исследовав все участки</small></button>' : '<p class="log-end-note">После первой сохранённой версии можно перейти к итогам.</p>'}</section>`;
}
function startObservatory() {
  clearInterval(blinkTimer);
  if (variant !== 'A' || !s.started || s.briefing || s.end || s.mode !== 'blink') return;
  const c = current();
  const [first, second] = s.pair;
  let frame = first;
  blinkTimer = setInterval(() => {
    if (document.hidden || document.querySelector('dialog[open]')) return;
    frame = frame === first ? second : first;
    const image = document.querySelector('.observation-base');
    if (!image) return;
    image.src = c.frames[frame];
    image.alt = `${c.name}: наблюдение ${frame + 1}`;
    document.querySelector('#blink-frame').textContent = `СНИМОК ${frame + 1}`;
  }, 800);
}
function setComparison(value) {
  s.split = Math.max(0, Math.min(100, Math.round(value)));
  document.querySelector('.instrument').style.setProperty('--split', s.split + '%');
  document.querySelector('.compare-control input').value = s.split;
  document.querySelector('.compare-control output').textContent = s.split + '%';
}
document.addEventListener('input', event => {
  if (event.target.dataset.control === 'comparison') setComparison(Number(event.target.value));
});
function moveComparison(event, target) {
  const bounds = target.getBoundingClientRect();
  setComparison((event.clientX - bounds.left) / bounds.width * 100);
}
document.addEventListener('pointerdown', event => {
  const target = event.target.closest('.instrument[data-mode="compare"] .observation-window');
  if (!target || event.button !== 0) return;
  event.preventDefault();
  target.setPointerCapture(event.pointerId);
  moveComparison(event, target);
});
document.addEventListener('pointermove', event => {
  const target = event.target.closest('.observation-window');
  if (target?.hasPointerCapture(event.pointerId)) moveComparison(event, target);
});
document.addEventListener('pointerup', event => {
  const target = event.target.closest('.observation-window');
  if (target?.hasPointerCapture(event.pointerId)) target.releasePointerCapture(event.pointerId);
});

function showAlgorithmHint() {
  const c = current();
  const rank = [...cases].sort((a, b) => b.score - a.score).findIndex(p => p.id === c.id) + 1;
  const dialog = document.querySelector('#algorithm-hint');
  dialog.innerHTML = `<div class="row spread"><span class="console-kicker">ОТДЕЛЬНЫЙ ПОМОЩНИК / ${c.name}</span><button data-action="close-hint" aria-label="Закрыть подсказку">Закрыть</button></div>
    <h2 id="hint-title">Куда алгоритм предлагает посмотреть?</h2>
    <p class="hint-lead">Среди шести учебных участков этот занимает <strong>${rank}-е место по необычности</strong>. Первое место — самый необычный для алгоритма, а не «точно открытие».</p>
    <div class="hint-ranking" aria-label="Место ${rank} из 6">${cases.map((_, i) => `<span class="${i + 1 === rank ? 'chosen' : ''}">${i + 1}</span>`).join('')}</div>
    <div class="hint-warning"><strong>Не принимайте подсказку за объяснение.</strong><p>Высокий балл может получить и помеха. Слабое настоящее изменение может оказаться ниже в списке. Проверяйте снимки, а не соглашайтесь с числом.</p></div>
    <details class="hint-method"><summary>Откуда взялась подсказка?</summary><p>В прототипе открывается заранее рассчитанный балл учебного набора: <strong>${score(c)}</strong>. Это не процент вероятности и не ответ о природе объекта. Новая нейросеть в браузере не запускается.</p></details>
    <p class="hint-receipt">${s.predictions[c.id] ? `Ваше первое впечатление: «${observationLabels[s.predictions[c.id]]}».` : 'Вы ещё не записали своё впечатление. Закройте подсказку и сравните снимки сами.'} ${s.decisions[c.id] ? `Сохранённая версия: «${verdictLabels[s.decisions[c.id]]}».` : ''} Подсказка не меняет ваши ответы.</p>
    <button class="primary" data-action="close-hint">Вернуться к снимкам</button>`;
  dialog.showModal();
}
document.querySelector('#algorithm-hint').addEventListener('close', () => {
  if (variant === 'A') document.querySelector('.hint-launch')?.focus({ preventScroll: true });
});
function discoveryArt(kind) {
  const stars = [[23,33],[51,187],[91,67],[135,211],[190,35],[254,215],[310,23],[401,44],[448,201],[529,47],[567,143],[341,217],[473,97]];
  const field = stars.map(([x,y],i) => `<circle cx="${x}" cy="${y}" r="${i % 3 ? 1.3 : 2.1}" fill="#d5edff" opacity="${i % 2 ? '.7' : '.4'}"/>`).join('');
  if (kind === 'planet') return `<svg class="discovery-art" viewBox="0 0 600 250" role="img" aria-label="Условная иллюстрация планеты и её звезды, не фотография"><defs><radialGradient id="story-star"><stop stop-color="#fff9d9"/><stop offset=".3" stop-color="#ffc276"/><stop offset="1" stop-color="#ff8a3d" stop-opacity="0"/></radialGradient><radialGradient id="story-planet" cx=".28" cy=".23"><stop stop-color="#a7b5a5"/><stop offset=".38" stop-color="#546b6f"/><stop offset=".78" stop-color="#1e3445"/><stop offset="1" stop-color="#0b1325"/></radialGradient></defs><rect width="600" height="250" fill="#091627"/>${field}<circle cx="139" cy="94" r="107" fill="url(#story-star)"/><circle cx="139" cy="94" r="18" fill="#fff3c4"/><ellipse cx="281" cy="123" rx="212" ry="60" fill="none" stroke="#8d9faf" stroke-opacity=".25" transform="rotate(-17 281 123)"/><circle cx="383" cy="143" r="91" fill="url(#story-planet)" stroke="#9dc9ce" stroke-opacity=".35"/><path d="M311 98q60 -32 116 10M309 119q69 -23 140 10M309 142q74 -12 151 12" fill="none" stroke="#b2c2a4" stroke-opacity=".13" stroke-width="9"/><text x="22" y="232" fill="#8ba8bd" font-size="10" font-family="monospace">УСЛОВНАЯ ИЛЛЮСТРАЦИЯ · НЕ СНИМОК KEPLER</text></svg>`;
  return `<svg class="discovery-art" viewBox="0 0 600 250" role="img" aria-label="Условная иллюстрация вспышки в галактике, не фотография"><defs><radialGradient id="story-galaxy"><stop stop-color="#ffdfb5"/><stop offset=".14" stop-color="#d8b4f0" stop-opacity=".8"/><stop offset=".5" stop-color="#5874a8" stop-opacity=".5"/><stop offset="1" stop-color="#13233c" stop-opacity="0"/></radialGradient><radialGradient id="story-flash"><stop stop-color="white"/><stop offset=".08" stop-color="#f4faff"/><stop offset=".28" stop-color="#9bdaff" stop-opacity=".7"/><stop offset="1" stop-color="#759aff" stop-opacity="0"/></radialGradient></defs><rect width="600" height="250" fill="#081323"/>${field}<ellipse cx="290" cy="126" rx="238" ry="77" fill="url(#story-galaxy)" transform="rotate(-18 290 126)"/><path d="M87 150c79 -66 263 -113 365 -60M111 180c95 16 270 -52 351 -107" fill="none" stroke="#bdc8ed" stroke-width="5" stroke-opacity=".15"/><circle cx="378" cy="76" r="76" fill="url(#story-flash)"/><path d="M378 25v102M327 76h102" stroke="#d7f0ff" stroke-opacity=".7"/><circle cx="378" cy="76" r="5" fill="white"/><text x="22" y="232" fill="#8ba8bd" font-size="10" font-family="monospace">УСЛОВНАЯ ИЛЛЮСТРАЦИЯ · НЕ СНИМОК SN 2023TYK</text></svg>`;
}
function showDiscovery(id) {
  const stories = window.PROTOTYPE_DISCOVERIES;
  const story = stories.find(item => item.id === id) || stories[0];
  const dialog = document.querySelector('#discovery-story');
  const wasOpen = dialog.open;
  dialog.innerHTML = `<div class="row spread discovery-top"><span class="console-kicker">НАСТОЯЩАЯ НАУКА · НЕ УЧЕБНЫЙ СЕКТОР</span><button data-action="close-discovery">Вернуться в игру</button></div>
    <div class="discovery-tabs" aria-label="История открытия">${stories.map(item => `<button data-action="discovery" data-id="${item.id}" aria-pressed="${story.id === item.id}" class="${story.id === item.id ? 'active' : ''}">${item.kind === 'planet' ? 'Планета в архиве' : 'Вспышка звезды'} <small>${item.year}</small></button>`).join('')}</div>
    <div class="discovery-hero">${discoveryArt(story.kind)}<span class="discovery-year">${story.year}</span></div>
    <div class="discovery-body"><span class="console-kicker">${story.kicker}</span><h2 id="discovery-title" tabindex="-1">${story.title}</h2><p class="discovery-summary">${story.summary}</p>
    <div class="discovery-evidence"><section><h3>Что сделал ИИ</h3><p>${story.aiRole}</p></section><section><h3>Как проверили результат</h3><p>${story.confirmation}</p></section></div>
    <div class="discovery-connection"><h3>Как это связано с нашей игрой</h3><p>${story.connection}</p></div>
    <details class="discovery-sources"><summary>Важные оговорки и первоисточники</summary><p>${story.caveat}</p><ul>${story.sources.map(source => `<li><a href="${source.url}" target="_blank" rel="noopener noreferrer">${source.label} ↗</a></li>`).join('')}</ul><p>История доступна без интернета. Для открытия внешних источников нужна сеть.</p></details></div>`;
  if (!wasOpen) dialog.showModal();
  else document.querySelector('#discovery-title').focus({ preventScroll: true });
  dialog.scrollTop = 0;
}
