(function () {
  'use strict';
  const baseData = globalThis.GALAXY_DATA;
  let storage; try { storage=globalThis.localStorage; } catch {}
  let data, model, byId;
  function newShift() {
    QuestScene.reset();
    data=GalaxySession.create(baseData,GALAXY_ARCHIVE,GalaxySession.choose(baseData,GALAXY_ARCHIVE,storage));
    globalThis.GALAXY_DATA=data;
    model=GalaxyModel.create(data);
    byId=Object.fromEntries(data.images.map(image=>[image.id,image]));
  }
  newShift();
  const root = document.querySelector('#game');
  let quest = null;
  let cardIndex = 0, modal = null, modalTrigger = null, busy = false, view = null;
  let soundEnabled = false, audio = null, cnnSecond = false, sky = null;
  // This UI-only route keeps the lesson model focused on labels and results.
  // It deliberately does not add a science-state transition to GalaxyModel.
  let journey = 'welcome';
  const found = new Set();
  const esc = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const label = id => data.classes.find(item => item.id === id)?.label || id;
  const source = image => `<p class="source">${esc(image.credit)} · <a href="${esc(image.source)}" target="_blank" rel="noreferrer">Источник снимка ↗</a></p>`;
  function chime() {
    if (!soundEnabled) return;
    audio ||= new (window.AudioContext || window.webkitAudioContext)();
    audio.resume();
    [440,660].forEach((frequency,index) => {
      const oscillator=audio.createOscillator(),gain=audio.createGain();
      oscillator.type='sine';oscillator.frequency.value=frequency;
      gain.gain.setValueAtTime(0,audio.currentTime+index*.075);
      gain.gain.linearRampToValueAtTime(.035,audio.currentTime+index*.075+.01);
      gain.gain.exponentialRampToValueAtTime(.001,audio.currentTime+index*.075+.22);
      oscillator.connect(gain);gain.connect(audio.destination);
      oscillator.start(audio.currentTime+index*.075);oscillator.stop(audio.currentTime+index*.075+.23);
    });
  }
  function nav() {
    const explore = journey === 'free' || model.state.phase === 'final';
    return `<header class="hud"><div class="top-actions"><button class="quiet sound" data-action="sound" aria-pressed="${soundEnabled}" aria-label="${soundEnabled?'Выключить':'Включить'} звук">${soundEnabled?'Звук вкл.':'Звук выкл.'}</button>${explore?'<button class="quiet" data-action="sky">Карта неба</button><button class="quiet" data-action="astronomy">ИИ в астрономии</button>':''}<button class="quiet" data-action="about">О проекте</button>${model.state.phase !== 'intro' ? '<button class="quiet" data-action="home">↗ Обсерватория</button>' : ''}</div></header>`;
  }
  function mentor(text, opening=false, mood='warm') {
    return `<aside class="mentor${opening?' room-dialogue':''}"><span class="mentor-portrait"><img src="assets/art/nika-${mood}-v1.png" alt="Ника, астроном" data-mood="${mood}"></span><div><span class="speaker">НИКА <i>астроном</i></span><p>${text}</p></div></aside>`;
  }
  function companion(image, phase, prediction) {
    const correct=prediction&&prediction.predicted===prediction.expected;
    const mood=prediction?(correct?'warm':'thinking'):phase==='repair'?'thinking':model.state.labels[image.id]?'warm':'curious';
    const words=prediction?(correct?'Ответ совпал. Хочешь посмотреть, какой пример помог модели?':'Здесь ответ не совпал. Давай вместе найдём, откуда взялась эта метка.'):
      phase==='repair'?'Старая подпись тоже может быть ошибочной. Что видно на самом снимке?':model.state.labels[image.id]?'Метка сохранена. Когда соберём все три, проверим ответы на других снимках.':'Что первым бросается в глаза? Можем рассмотреть снимок вместе.';
    return `<div class="photo-companion">${mentor(words,false,mood)}<button class="text-button" data-action="talk" data-image-id="${esc(image.id)}">Поговорить с Никой →</button></div>`;
  }
  function talk(id, storyId) {
    if(quest && !sky && !modal && !storyId && root.querySelector("#quest-scene")?.dataset.imageId===id){quest.startConversation();return;}
    const story=storyId?GALAXY_DISCOVERIES.find(i=>i.id===storyId):null;
    const image=story?{id:story.id,name:story.title,src:story.image,explanation:story.text}:byId[id];
    const prediction=[...(model.state.current?.review.predictions||[]),...(model.state.current?.final.predictions||[])].find(p=>p.id===id);
    NikaDialogue.open({image,story,phase:model.state.phase,prediction,neighbor:prediction?byId[prediction.neighborId]:null});
  }
  function progress(phase) {
    const steps=[['tutorial','Знакомство'],['labels','Примеры'],['results','Проверка'],['repair','Исправление'],['final','Результат']];
    const active=Math.max(0,steps.findIndex(s=>s[0]===phase));
    return `<ol class="progress" aria-label="Этапы смены">${steps.map(([id,name],i)=>`<li class="${i===active?'active':i<active?'done':''}"><span>${i<active?'✓':i+1}</span><b>${name}</b></li>`).join('')}</ol>`;
  }
  function photo(image, draggable=false) {
    return `<figure class="galaxy-frame"><img src="${esc(image.src)}" alt="${esc(image.name)}" ${draggable?'draggable="true" data-drag-id="'+esc(image.id)+'"':''}><figcaption><span>HUBBLE · ${esc(image.name)}</span><button class="zoom" data-action="zoom" data-image-id="${esc(image.id)}" aria-label="Открыть снимок ${esc(image.name)}">⤢</button></figcaption></figure>`;
  }
  function intro() {
    const resumable=journey==='work'||model.state.resumePhase!=='tutorial'||model.state.baseline!==null;
    if (resumable) return `<section class="room">${nav()}<h1 class="sr-only">Обсерватория</h1><div class="welcome">${mentor('Снимки и твои метки остались на столе. Продолжим исследование?',true)}<button class="primary" data-action="resume">Продолжить работу <span>→</span></button></div></section>`;
    return `<section class="room">${nav()}<h1 class="sr-only">Обсерватория</h1><div class="welcome">${mentor('Привет, я Ника! В архиве Hubble много готовых снимков галактик. Помоги мне собрать три понятных примера, чтобы затем проверить учебную модель.',true)}<button class="primary" data-action="start-route">Помочь Нике <span>→</span></button></div></section>`;
  }
  function storyGate() {
    const story=GalaxyAstronomy.cases[0];
    const collected=found.size;
    const ready=collected===data.childIds.length;
    return `<section class="room route-story">${nav()}<article class="route-story__card"><span class="eyebrow">01 / ИИ В АСТРОНОМИИ</span><h1 tabindex="-1">${esc(story.title)}</h1><p>${esc(story.text)}</p><p class="route-story__question">${esc(story.question)}</p><p class="source">${esc(story.sourceLabel)} · <a href="${esc(story.sourceURL)}" target="_blank" rel="noreferrer">Источник ↗</a></p>${mentor(ready?'Все три снимка уже в подборке. Перейдём к столу и разберём один пример вместе.':collected?`В подборке уже ${collected} из 3 снимков. Вернёмся к карте и соберём остальные.`:'Люди отмечают видимые признаки на снимках, а программа помогает разбирать большой архив. Соберём нашу маленькую подборку?',false,'curious')}<button class="primary" data-action="${ready?'complete-collection':'collect-map'}">${ready?'К рабочему столу':'Найти галактики на карте'} <span>→</span></button></article></section>`;
  }
  function station(title,subtitle,phase,content,footer='',words='') {
    return `<section class="workbench${content.includes('id="quest-scene"')?' workbench--quest':''}">${nav()}${progress(phase)}<div class="station"><div class="station-head"><div><span class="eyebrow">${subtitle}</span><h1>${title}</h1></div></div>${content}${footer}</div>${words&&!['labels','repair'].includes(phase)?mentor(words,false,phase==='results'?'thinking':'curious'):''}</section>`;
  }
  function tutorial() {
    const image=byId[data.tutorialId];
    return station('Как ИИ помогает астрономам?','02 / РАЗБИРАЕМ ПРИМЕР ВМЕСТЕ','tutorial',`<div id="quest-scene" data-image-id="${image.id}"></div><p class="tutorial-next">Рассмотри пример вместе с Никой: выбери, что замечаешь, и нажми на интересующую деталь. Потом разметим три снимка, которые ты собрал на карте.</p><div class="film-footer"><div class="navigation"><button class="secondary" data-action="zoom" data-image-id="${image.id}">Открыть снимок целиком</button><button class="primary" data-action="labels">Перейти к моей подборке →</button></div></div><details class="credits"><summary>Источник снимка</summary>${source(image)}</details>`);
  }
  function samples(ids) {
    return `<div class="samples" aria-label="Снимки этой подборки">${ids.map((id,i)=>`<button data-action="sample" data-index="${i}" class="sample ${i===cardIndex?'selected':''}" aria-label="Снимок ${i+1}: ${esc(byId[id].name)}" aria-current="${i===cardIndex}">${found.has(id)||data.oldIds.includes(id)?`<img src="${esc(byId[id].src)}" alt="">`:'<span class="unfound">✦</span>'}<span>${i+1}</span><i>${model.state.labels[id]? '✓' : '·'}</i></button>`).join('')}</div>`;
  }
  function labelsView(old=false) {
    const state=model.state,ids=old?data.oldIds:data.childIds,image=byId[ids[cardIndex]],missing=ids.filter(id=>!state.labels[id]).length;
    const available=old||found.has(image.id);
    const content=`${available?`<div id="quest-scene" data-image-id="${image.id}"></div>`:`<div class="missing-photo"><span>✦</span><h2>${esc(image.name)}</h2><p>Найди эту галактику на карте неба, чтобы открыть её архивный снимок.</p><button class="primary" data-action="sky" data-image-id="${image.id}">К звёздному небу →</button></div>`}<div class="film-footer">${samples(ids)}<div class="navigation"><button class="secondary" data-action="sky" data-image-id="${image.id}">Карта неба</button><button class="secondary" data-action="previous" ${cardIndex===0?'disabled':''} aria-label="Предыдущий снимок">←</button><button class="secondary" data-action="next" ${cardIndex===ids.length-1?'disabled':''}>Следующий →</button><button class="primary" data-action="run" ${!old&&missing?'disabled':''}>${old?'Проверить снова':missing?'Поставь все 3 метки':'Проверить модель'} <span>↗</span></button></div></div><details class="credits"><summary>Источник и условия опыта</summary>${source(image)}<p>Признаки снимков измерены заранее. Программа сравнивает учебные примеры этой смены.${old?' Две старые метки намеренно перепутаны авторами учебной истории.':''}</p></details>`;
    return station(old?'Заглянем в старые примеры':'Разметим учебные примеры',`${old?'04 / ПРОВЕРЯЕМ ДАННЫЕ':'02 / РАЗМЕЧАЕМ'} · ${cardIndex+1} ИЗ ${ids.length}`,old?'repair':'labels',content,'',old?'Посмотри на снимок и выбери метку. В старой подборке тоже бывают ошибки.':'Выбери метку по тому, что видно на снимке. Потом проверим ответы модели на других галактиках.');
  }
  function predictionCard(prediction,previous,final=false) {
    const image=byId[prediction.id],ok=prediction.predicted===prediction.expected;
    const changed=previous&&previous.predicted!==prediction.predicted;
    return `<article class="result ${ok?'correct':'incorrect'}">${photo(image)}<div class="result-info"><div class="result-name"><b>${esc(image.name)}</b><span>${ok?'Совпало ✓':'Проверим ?'}</span></div>${previous?`<p class="before-answer">Было: ${esc(label(previous.predicted))}</p>`:''}<p>Модель: <strong>${esc(label(prediction.predicted))}</strong>${changed?'<em>Новый ответ</em>':''}</p><p class="reference">Метка для проверки: ${esc(label(prediction.expected))}</p><button class="text-button" data-action="explain" data-image-id="${esc(image.id)}">${final?'Почему такой ответ?':'Найти учебный пример →'}</button><button class="nika-result-talk" data-action="talk" data-image-id="${esc(image.id)}"><img src="assets/art/nika-${ok?'warm':'thinking'}-v1.png" alt=""><span>Обсудить с Никой</span></button></div></article>`;
  }
  function results() {
    const state=model.state,current=state.current,baseline=state.baseline,review=current.review,checked=state.repairCheckedKey===current.key,changed=baseline.key!==current.key,unchangedError=review.predictions.find(p=>p.predicted!==p.expected&&!data.editableIds.includes(p.neighborId));
    const before=Object.fromEntries(baseline.review.predictions.map(p=>[p.id,p]));
    const words=checked?(review.correct>baseline.review.correct?'Исправление данных помогло! Посмотри, какой ответ изменился. Но каждой галактике всё ещё нужна проверка.':'Ответы следуют меткам примеров. Если результат не улучшился, проверим ограничения модели — кнопка сама по себе её не улучшает.'):(review.correct===review.total?'На этих снимках все ответы совпали с метками для проверки. Посмотрим и старые учебные примеры.':'Модель ошиблась. Откуда пришёл ответ? Нажми «Найти учебный пример» у снимка и загляни в данные.');
    return station(checked?'Что изменилось после правок?':'Ответы модели нужно проверить',checked?'05 / СРАВНИВАЕМ':'03 / ПРОВЕРЯЕМ',checked?'repair':'results',`<div class="score-strip">${changed?`<span>Первая проверка <b>${baseline.review.correct}<small> / ${baseline.review.total}</small></b></span><i>→</i>`:''}<span>${changed?'После правок':'Верные ответы'} <b>${review.correct}<small> / ${review.total}</small></b></span><p>Те же проверочные снимки.<br>Сравниваем конкретные ответы.</p></div>${state.notice?`<p class="callout">${esc(state.notice)}</p>`:''}${checked&&unchangedError?`<p class="callout" data-review-limitation>Один ответ всё ещё следует фиксированному учебному примеру «${esc(byId[unchangedError.neighborId].name)}». Правка старых меток на него не влияет: открой «Найти учебный пример», чтобы разобраться, почему модель ошиблась.</p>`:''}<div class="result-grid">${review.predictions.map(p=>predictionCard(p,changed?before[p.id]:null)).join('')}</div>`,`<div class="navigation result-nav"><button class="secondary" data-action="labels">← Мои примеры</button><div><button class="${checked?'secondary':'primary'}" data-action="repair">${checked?'Снова посмотреть старые метки':'Открыть старую подборку'} →</button>${checked?'<button class="primary" data-action="finish">На доску исследований ↗</button>':''}</div></div>`,words);
  }
  function final() {
    const state=model.state,exp=state.current.final,review=state.current.review,baseline=state.baseline.review,changed=state.baseline.key!==state.current.key,all=exp.correct===exp.total;
    return `<section class="room final-room">${nav()}<div class="completed-seal"><span>✦</span><b>Подборка проверена</b><small>Примеры → проверка → исследование</small></div><article class="research-board"><div class="board-heading"><span class="eyebrow">ДОСКА ИССЛЕДОВАНИЙ</span><h1>${all?'Новая подборка разобрана':'Мы проверили новую подборку'}</h1><div class="board-score-summary" aria-label="Результаты проверки модели"><section data-score-scope="review-before"><span>На знакомых проверочных снимках</span><b>До проверки старых меток: ${baseline.correct} из ${baseline.total}</b></section><section data-score-scope="review-after"><span>${changed?'На тех же снимках после правок':'На тех же снимках, повторная проверка'}</span><b>Модель: ${review.correct} из ${review.total}</b></section><section class="board-final-score" data-score-scope="final" data-final-independent><span>На трёх других снимках</span><b>Модель: ${exp.correct} из ${exp.total}</b><small>Это другая подборка. Здесь модель может ответить иначе.</small></section></div><p class="board-score-note">Верные метки помогают проверить данные, но не делают эту небольшую модель безошибочной. Число относится к её ответам, а не к твоей работе.</p></div><div class="result-grid">${exp.predictions.map(p=>predictionCard(p,null,true)).join('')}</div><p class="final-note">${esc(state.notice)}</p><div class="navigation"><button class="secondary" data-action="labels">Вернуться к примерам</button><div>${globalThis.GALAXY_CNN?'<button class="primary" data-action="cnn">Лаборатория нейросетей →</button>':''}<button class="secondary" data-action="reset">Новая смена</button></div></div></article><div class="closing">${mentor(all?'Спасибо! Ты подготовил примеры и проверил ответы. Следующий шаг — проверить модель на большей подборке.':'Спасибо! Ты подготовил примеры и проверил ответы. Мы знаем, какие ответы модели ещё нужно проверить по снимкам.')}<button class="text-button room-link" data-action="journal">Что мы узнали за смену?</button></div></section>`;
  }
  function cnnView() {
    const cnn=globalThis.GALAXY_CNN;
    return station('Сравним две нейронные сети','ДОПОЛНИТЕЛЬНЫЙ ОПЫТ · ГОТОВЫЙ ИСПРАВЛЕННЫЙ НАБОР','repair',`<p class="cnn-intro">Это свёрточные нейронные сети — CNN. Свёртка обрабатывает маленькие участки снимка. Добавим второй блок и сравним ответы.</p><div class="model-config"><button class="${!cnnSecond?'primary':'secondary'}" data-action="cnn-one" aria-pressed="${!cnnSecond}">Один блок</button><button class="${cnnSecond?'primary':'secondary'}" data-action="cnn-two" aria-pressed="${cnnSecond}">${cnnSecond?'Второй блок добавлен ✓':'+ Добавить второй блок'}</button><p role="status">${cnnSecond?'Блоков стало больше. А ответы изменились?':'Открой второй вариант и сравни ответы.'}</p></div><div class="cnn-models">${cnn.models.filter((m,i)=>i===0||cnnSecond).map(m=>`<article class="cnn-model"><h2>${esc(m.name)}</h2><div class="network-diagram"><span>Снимок</span>${Array.from({length:m.blocks},(_,i)=>`<i>→</i><b>Блок ${i+1}<small>свёртка</small></b>`).join('')}<i>→</i><span>Подпись</span></div><p class="note">Параметров: ${Number(m.parameters).toLocaleString('ru-RU')}</p><div class="cnn-answers">${m.predictions.map(p=>`<div><img src="${esc(byId[p.id].src)}" alt="${esc(byId[p.id].name)}"><span>${esc(label(p.predicted))}<small>${p.predicted===p.expected?'Совпало ✓':'Не совпало'}</small></span></div>`).join('')}</div><p class="cnn-score">Верно <b>${m.correct} из ${m.total}</b></p></article>`).join('')}${!cnnSecond?'<button class="cnn-placeholder" data-action="cnn-two"><b>＋</b><span>Добавь второй блок<br>и проверь результат</span></button>':''}</div><p class="callout">Отдельный подготовленный опыт на 9 учебных галактиках с проверенными метками. Он не меняет твою модель. ${cnnSecond?'На этой подборке оба варианта дали одинаковые ответы. Больше блоков не всегда помогает.':'Мы ещё не знаем, поможет ли второй блок.'}</p><details class="credits"><summary>Как рассчитано сравнение</summary><p>${esc(cnn.note)}</p></details>`,`<div class="navigation"><button class="primary" data-action="close-cnn">Вернуться к результату смены ↗</button></div>`,'Здесь отдельный подготовленный набор с проверенными метками. Мы сравниваем два заранее обученных варианта, а не меняем твою модель.');
  }
  function about() {
    return `<span class="eyebrow">О ПРОЕКТЕ</span><h2>ИИ в астрономии</h2><p>Галактики на снимках настоящие: архив NASA/ESA Hubble. Обсерватория и Ника — художественные иллюстрации. На интерактивной карте показаны звёздный атлас NASA и координаты объектов. Мы открываем архивные снимки, а не делаем новые наблюдения.</p><p>В каждой смене — три случайных снимка из архива из 24 галактик. Программа сравнивает заранее измеренные признаки снимков и выбирает ближайший учебный пример. Все расчёты воспроизводимы.</p><p>Модель: <b>${esc(data.model.name)}</b>. ${esc(data.model.description)}</p><p>«Гладкая», «видна спираль» и «вид с ребра» — признаки видимого облика. Спиральная галактика тоже может быть видна с ребра.</p><p>Разметка человека, ответ модели и справочная метка — разные вещи. Повторная проверка показывает изменения, а не независимую научную оценку качества.</p><p><a href="DATA-NOTES.md" target="_blank">Данные и метод ↗</a> · <a href="provenance.json" target="_blank">Источники ↗</a> · <a href="assets/art/ART-CREDITS.md" target="_blank">Иллюстрации ↗</a></p>`;
  }
  const categories={discovery:'Открытия с ИИ',object:'Объекты',image:'Снимки',research:'Исследования'};
  function astronomy() {
    return `<span class="eyebrow">ИИ В АСТРОНОМИИ</span><h2>Открытия и исследования</h2><p>Открой историю: что заметила программа, что проверили астрономы и какие вопросы остались.</p><div class="discovery-grid">${GALAXY_DISCOVERIES.map(item=>`<button class="library-card" data-action="discovery" data-id="${esc(item.id)}"><img src="${esc(item.image)}" alt="${esc(item.alt)}"><span><small>${esc(categories[item.category])} · ${esc(item.date||'')}</small><b>${esc(item.title)}</b></span></button>`).join('')}</div><button class="secondary" data-action="archive">Архив галактик →</button>`;
  }
  function discovery(id) {
    const item=GALAXY_DISCOVERIES.find(i=>i.id===id);
    if(!item)return;
    openModal(`<span class="eyebrow">${esc(categories[item.category])} · ${esc(item.date||'')}</span><h2>${esc(item.title)}</h2><figure class="discovery-figure"><img src="${esc(item.image)}" alt="${esc(item.alt)}"><figcaption>${esc(item.alt)}</figcaption></figure><p>${esc(item.text)}</p><p>${esc(item.detail)}</p><p class="note">${esc(item.locationNote)}${item.coordinateSource?` · <a href="${esc(item.coordinateSource.startsWith('https://')?item.coordinateSource:'https://simbad.cds.unistra.fr/simbad/sim-id?Ident='+encodeURIComponent(item.coordinateSource.replace(/^SIMBAD: /,'')))}" target="_blank" rel="noreferrer">Координаты ↗</a>`:''}</p><p class="source">${esc(item.credit)} · <a href="${esc(item.imageSource)}" target="_blank" rel="noreferrer">Источник изображения ↗</a> · <a href="${esc(item.source)}" target="_blank" rel="noreferrer">Исследование ↗</a></p><div class="photo-companion">${mentor('У каждого открытия есть своя история. Обсудим, что здесь нашли?',false,'curious')}<button class="text-button" data-action="talk" data-story-id="${esc(item.id)}">Поговорить с Никой →</button></div><button class="secondary" data-action="astronomy">Все истории</button>`);
  }
  function archive() {
    return `<span class="eyebrow">АРХИВ HUBBLE</span><h2>${GALAXY_ARCHIVE.images.length} галактики</h2><p>В каждой смене ты разбираешь три снимка. Здесь можно рассмотреть всю коллекцию и прочитать о каждом объекте.</p><div class="discovery-grid">${GALAXY_ARCHIVE.images.map(i=>`<button class="library-card" data-action="archive-image" data-id="${esc(i.id)}"><img src="${esc(i.src)}" alt="${esc(i.name)}"><span><b>${esc(i.name)}</b></span></button>`).join('')}</div>`;
  }
  function archiveImage(id) {
    const image=byId[id];if(!image)return;
    openModal(`<span class="eyebrow">АРХИВ HUBBLE</span><h2>${esc(image.name)}</h2>${photo(image)}<p>${esc(image.explanation)}</p>${source(image)}${companion(image,'archive')}<button class="secondary" data-action="archive">Весь архив</button>`);
  }
  function openSky(initialTarget) {
    if(sky||busy)return;
    closeModal();const trigger=document.activeElement;root.inert=true;
    const collecting=journey==='collect';
    sky=GalaxySky.open({initialTarget, collectedIds:collecting?[...found]:[], guided:collecting, onDiscovery:discovery,onArchive:archiveImage,onTasks(){openSky(data.childIds.find(id=>!found.has(id))||data.childIds[0]);},onClose(){sky=null;root.inert=false;if(journey==='collect'&&model.state.phase==='intro'){journey='story';render();root.querySelector('.route-story__card h1')?.focus({preventScroll:true});return;}if(trigger?.isConnected)trigger.focus({preventScroll:true});},onCollect(id){
      found.add(id); cardIndex=data.childIds.indexOf(id); chime();
    },onComplete(){
      journey='work'; cardIndex=0; dispatch('START');
    },onSelect(id){
      found.add(id);cardIndex=data.childIds.indexOf(id);
      if(model.state.phase==='labels'){render();chime();return;}
      openModal(`<h2>${esc(byId[id].name)}</h2>${photo(byId[id])}${source(byId[id])}`);
    }});
  }
  function journal() {
    return `<span class="eyebrow">ДОСКА ИССЛЕДОВАНИЙ</span><h2>Как научить модель — и проверить её</h2><div class="journal-steps"><p><b>01 · Наблюдаем.</b> Что видно на снимке?</p><p><b>02 · Собираем данные.</b> Снимок с меткой — учебный пример для модели.</p><p><b>03 · Проверяем.</b> Смотрим её ответы на других снимках.</p><p><b>04 · Исследуем ошибку.</b> Проверяем метки учебных примеров.</p><p><b>05 · Сравниваем.</b> Видим, какие ответы действительно изменились.</p></div><p>${esc(GalaxyAstronomy.afterExperience.text)}</p><button class="primary" data-action="astronomy">Где это применяют в астрономии?</button>`;
  }
  function explain(image) {
    const state=model.state,predictions=state.phase==='final'?state.current.final.predictions:state.current.review.predictions,prediction=predictions.find(p=>p.id===image.id),neighbor=byId[prediction.neighborId];
    return `<span class="eyebrow">ИЩЕМ ПРИЧИНУ ОТВЕТА</span><h2>Откуда взялась эта метка?</h2><div class="explain-grid"><div><h3>Проверяемый снимок</h3><img src="${esc(image.src)}" alt="${esc(image.name)}"><b>${esc(image.name)}</b></div><div><h3>Ближайший учебный пример</h3><img src="${esc(neighbor.src)}" alt="${esc(neighbor.name)}"><b>${esc(neighbor.name)}</b></div></div><p>Программа измеряет распределение света на снимке. Такие измерения называют признаками. Она нашла ближайший пример по этим признакам и взяла его метку: <b>${esc(label(prediction.predicted))}</b>. Похожие числовые признаки не всегда означают одинаковый вид галактики.</p>${data.oldIds.includes(neighbor.id)&&state.phase!=='final'?`<button class="primary" data-action="inspect-old" data-image-id="${esc(neighbor.id)}">Проверить метку этого примера →</button>`:'<p>Если метка верная, ошибка может быть в способе сравнения изображений.</p>'}${source(neighbor)}`;
  }
  function openModal(content,isImage=false) {
    closeModal();modalTrigger=document.activeElement;modal=document.createElement('div');modal.className='modal';modal.setAttribute('role','dialog');modal.setAttribute('aria-modal','true');modal.setAttribute('aria-label',isImage?'Снимок галактики':'Записи лаборатории');modal.innerHTML=`<div class="modal-box${isImage?' image-box':''}"><button class="secondary modal-close" data-action="close-modal">Закрыть ×</button>${content}</div>`;document.body.append(modal);root.inert=true;const atlas=document.querySelector('.sky-atlas');if(atlas)atlas.inert=true;modal.querySelector('button').focus();
  }
  function closeModal(){if(!modal)return;modal.remove();modal=null;root.inert=Boolean(sky);const atlas=document.querySelector('.sky-atlas');if(atlas)atlas.inert=false;if(modalTrigger?.isConnected)modalTrigger.focus();}
  function render() {
    const phase=model.state.phase;
    document.body.dataset.phase=view==='cnn'?'cnn':phase;
    galaxyWorld.setPhase(view==='cnn'?'repair':phase);
    quest?.destroy();quest=null;
    root.innerHTML=view==='cnn'?cnnView():journey==='story'?storyGate():phase==='intro'?intro():phase==='tutorial'?tutorial():phase==='labels'?labelsView():phase==='results'?results():phase==='repair'?labelsView(true):final();
    const host=root.querySelector('#quest-scene');
    if(host){
      const image=byId[host.dataset.imageId];
      quest=QuestScene.mount(host,{image,phase,classes:data.classes,selected:model.state.labels[image.id],initialSelected:model.state.labels[image.id],initialOldLabel:phase==='repair'?label(data.initialOldLabels[image.id]):null,
        opening:phase==='tutorial'?'У телескопов миллионы снимков. Люди дают программе примеры с метками, а она ищет похожие признаки. Рассмотрим один пример вместе.':null,
        onLabel:value=>choose(image.id,value)});
    }
    globalThis.galaxyGame={model,render,get quest(){return quest;},get view(){return view;},get busy(){return busy;},get sky(){return sky;},get found(){return [...found];}};
  }
  function dispatch(type,payload={}) {
    try{model.dispatch({type,...payload});if(type==='LABELS'||type==='REPAIR')cardIndex=0;view=null;render();if(type!=='SET_LABEL'){window.scrollTo({top:0,behavior:'instant'});const heading=root.querySelector('h1');heading?.setAttribute('tabindex','-1');heading?.focus({preventScroll:true});}chime();}
    catch(error){openModal(`<h2>Нужен ещё один шаг</h2><p>${esc(error.message)}</p>`);}
  }
  function choose(id,value){if(busy||sky||model.state.phase==='labels'&&!found.has(id))return;dispatch('SET_LABEL',{id,label:value});const stamp=document.createElement('span');stamp.className='stamp-feedback';stamp.textContent=label(value)+' ✓';root.querySelector('.quest-scene__photo-shell, .photo-stage .galaxy-frame')?.append(stamp);setTimeout(()=>stamp.remove(),900);const selected=root.querySelector(`[data-label-id="${id}"][data-label="${value}"]`);selected?.focus({preventScroll:true});}
  function runExperience() {
    if(busy)return;busy=true;const overlay=document.createElement('div');overlay.className='experiment-loading';overlay.setAttribute('role','status');overlay.innerHTML=`<div class="scanning"><div class="scan-images">${data.childIds.map(id=>`<img src="${esc(byId[id].src)}" alt="">`).join('')}</div><span class="scan-beam"></span><h2>Сравниваем снимки</h2><p>Снимки + твои метки → ответы модели</p><small>Сравниваем признаки и берём метку ближайшего примера.</small></div>`;document.body.append(overlay);root.inert=true;
    setTimeout(()=>{overlay.remove();root.inert=false;busy=false;dispatch('RUN');},matchMedia('(prefers-reduced-motion: reduce)').matches?120:1000);
  }
  document.addEventListener('click',event=>{
    const button=event.target.closest('button');if(!button||busy)return;const action=button.dataset.action;
    if(button.dataset.labelId){choose(button.dataset.labelId,button.dataset.label);return;}
    if(action==='talk'){talk(button.dataset.imageId,button.dataset.storyId);return;}
    if(action==='sound'){soundEnabled=!soundEnabled;button.setAttribute('aria-pressed',String(soundEnabled));button.setAttribute('aria-label',(soundEnabled?'Выключить':'Включить')+' звук');button.textContent=soundEnabled?'Звук вкл.':'Звук выкл.';chime();return;}
    if(action==='start-route'){journey='story';render();return;}
    if(action==='collect-map'){journey='collect';openSky(data.childIds.find(id=>!found.has(id))||data.childIds[0]);return;}
    if(action==='complete-collection'){journey='work';cardIndex=0;dispatch('START');return;}
    if(action==='sky'){openSky(button.dataset.imageId);return;}
    if(action==='astronomy'){openModal(astronomy());return;}
    if(action==='discovery'){discovery(button.dataset.id);return;}
    if(action==='archive-image'){archiveImage(button.dataset.id);return;}
    if(action==='labels'){dispatch('LABELS');if(!found.has(data.childIds[cardIndex]))openSky(data.childIds[cardIndex]);return;}
    if(action==='zoom'){const image=byId[button.dataset.imageId];openModal(`<img class="modal-image" src="${esc(image.src)}" alt="${esc(image.name)}">${source(image)}`,true);return;}
    if(action==='help'){if(quest){quest.hint();return;}const image=byId[button.dataset.imageId];openModal(`<span class="eyebrow">СМОТРИМ ВМЕСТЕ С НИКОЙ</span><h2>Посмотрим на снимок</h2><img class="hint-image" src="${esc(image.src)}" alt="${esc(image.name)}"><p>${esc(image.explanation)}</p><p>Посмотри, видны ли спиральные рукава, ровное свечение или тонкая полоса диска.</p>${source(image)}`);return;}
    if(action==='explain'){openModal(explain(byId[button.dataset.imageId]));return;}
    if(action==='about'){openModal(about());return;}
    if(action==='journal'){openModal(journal());return;}
    if(action==='archive'){openModal(archive());return;}
    if(action==='start-from-archive'){closeModal();dispatch(model.state.resumePhase!=='tutorial'||model.state.baseline!==null?'RESUME':'START');return;}
    if(action==='close-modal'){closeModal();return;}
    if(action==='inspect-old'){closeModal();dispatch('REPAIR');cardIndex=data.oldIds.indexOf(button.dataset.imageId);render();return;}
    if(action==='sample'){cardIndex=Number(button.dataset.index);render();return;}
    if(action==='next'||action==='previous'){const ids=model.state.phase==='labels'?data.childIds:data.oldIds;cardIndex=Math.max(0,Math.min(ids.length-1,cardIndex+(action==='next'?1:-1)));render();return;}
    if(action==='run'){runExperience();return;}
    if(action==='cnn'){view='cnn';cnnSecond=false;render();return;}
    if(action==='cnn-one'||action==='cnn-two'){cnnSecond=action==='cnn-two';render();chime();return;}
    if(action==='close-cnn'){view=null;render();return;}
    if(action==='reset'){if(confirm('Начать новую смену? Метки этой смены исчезнут.')){found.clear();cardIndex=0;view=null;journey='welcome';newShift();render();}return;}
    const actions={labels:'LABELS',repair:'REPAIR',finish:'FINISH',home:'HOME',resume:'RESUME'};if(actions[action]){dispatch(actions[action]);if(action==='finish')journey='free';}
  });
  document.addEventListener('dragstart',event=>{const image=event.target.closest('[data-drag-id]');if(!image)return;event.dataTransfer.setData('text/plain',image.dataset.dragId);event.dataTransfer.effectAllowed='copy';document.body.classList.add('dragging-photo');});
  document.addEventListener('dragend',()=>document.body.classList.remove('dragging-photo'));
  document.addEventListener('dragover',event=>{const stamp=event.target.closest('[data-label]');if(stamp){event.preventDefault();event.dataTransfer.dropEffect='copy';}});
  document.addEventListener('drop',event=>{const stamp=event.target.closest('[data-label]');if(stamp&&event.dataTransfer.getData('text/plain')===stamp.dataset.labelId){event.preventDefault();document.body.classList.remove('dragging-photo');choose(stamp.dataset.labelId,stamp.dataset.label);}});
  document.addEventListener('keydown',event=>{
    if(modal){if(event.key==='Escape'){event.preventDefault();closeModal();}if(event.key==='Tab'){const focusable=[...modal.querySelectorAll('button,a[href]')],first=focusable[0],last=focusable.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}}return;}
    if(busy||sky||view||!['labels','repair'].includes(model.state.phase)||event.target.closest('a,summary,input'))return;
    const category=Number(event.key)-1;if(category>=0&&category<3){const ids=model.state.phase==='labels'?data.childIds:data.oldIds;choose(ids[cardIndex],data.classes[category].id);}
  });
  render();
})();
