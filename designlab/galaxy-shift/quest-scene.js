/* Desktop workbench scene. State that belongs to the lesson remains with the
   caller; this component only records an optional place the learner inspected. */
(function (root) {
  'use strict';
  const points = new Map();
  const observations = {
    arms: 'Проверим, видны ли на снимке спиральные рукава. Нажми на участок, который хочешь рассмотреть ближе.',
    smooth: 'Рассмотрим, насколько гладко распределён свет. Нажми на участок снимка, который хочешь увеличить.',
    edge: 'Проверим, похожа ли галактика на узкий диск, видимый с ребра. Нажми на участок, который хочешь рассмотреть ближе.'
  };

  function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
  }
  function imageName(image) { return image.name || image.title || 'снимок'; }
  function imageSrc(image) { return image.src || image.image || ''; }
  function pointStyle(point) {
    return point ? `style="--point-x:${point.x * 100}%;--point-y:${point.y * 100}%;"` : '';
  }

  function mount(host, options) {
    if (!host || !options?.image) throw new Error('QuestScene.mount: нужны host и image.');
    let destroyed = false;
    let stage = 'question';
    let zoomed = false;
    let tutorialChoice = null;
    let resizeObserver = null;
    let point = points.get(options.image.id) || { x: .5, y: .5 };
    const image = options.image;
    const classes = Array.isArray(options.classes) ? options.classes : [];
    const isTutorial = options.phase === 'tutorial';
    const old = options.initialOldLabel;
    const selectedClass = () => classes.find(item => item.id === (isTutorial ? tutorialChoice : options.selected));
    function portraitMood() {
      if (options.phase === 'repair' || stage === 'hint') return 'thinking';
      return stage === 'inspected' || (isTutorial ? tutorialChoice : options.selected) ? 'warm' : 'thinking';
    }

    function dialogue() {
      if (stage === 'tutorial-choice') return `Твоя пробная метка — «${selectedClass()?.label}». ${image.explanation || selectedClass()?.hint || ''} Она не входит в обучающую выборку.`;
      if (stage === 'inspected') return 'Это выбранный тобой участок. Увеличение помогает рассмотреть изображение, но метку выбираешь ты.';
      if (stage === 'hint') return image.explanation || 'Посмотри на форму света, а затем выбери метку сам.';
      if (stage === 'briefing') return options.opening || 'Рассмотри снимок и выбери одну метку.';
      if (options.opening) return options.opening;
      if (options.selected) return `Твоя метка «${selectedClass()?.label || options.selected}» сохранена. Можно перейти к следующему снимку или изменить выбор.`;
      return 'Рассмотри снимок и выбери одну метку. Если сомневаешься, попроси подсказку.';
    }
    function render() {
      if (destroyed) return;
      if (host.firstElementChild) { update(); return; }
      const selected = isTutorial ? tutorialChoice : options.selected;
      const labels = `<section class="quest-scene__labels ${isTutorial ? 'quest-scene__labels--tutorial' : ''}" aria-label="${isTutorial ? 'Пробная метка класса' : 'Выбор метки'}">
        <div class="quest-scene__label-heading"><span>${isTutorial ? 'ПРОБНАЯ МЕТКА' : 'ТВОЯ МЕТКА'}</span><b>${isTutorial ? 'Как выглядит галактика на снимке?' : old ? 'Подтверди старую метку или выбери другую' : 'Выбери одну метку для снимка'}</b></div>
        ${old ? `<p class="quest-scene__old">В архиве было: <b>${esc(old)}</b></p>` : ''}
        <div class="quest-scene__label-list">${classes.map(item => `<button type="button" class="quest-scene__label ${esc(item.id)} ${selected === item.id ? 'is-selected' : ''}" data-quest-label="${esc(item.id)}" data-label-id="${esc(image.id)}" data-label="${esc(item.id)}" aria-pressed="${selected === item.id}"><i class="morphology-symbol ${esc(item.id)}" aria-hidden="true"></i><span><b>${esc(item.label)}</b><small>${esc(item.hint || '')}</small></span><em aria-hidden="true">${selected === item.id ? '✓' : '+'}</em></button>`).join('')}</div>
      </section>`;
      host.innerHTML = `<section class="quest-scene" data-quest-phase="${esc(options.phase || '')}">
        <div class="quest-scene__main">
          <section class="quest-scene__photo-area" aria-label="Снимок ${esc(imageName(image))}">
            <div class="quest-scene__photo-shell ${zoomed ? 'is-zoomed' : ''}" ${pointStyle(point)}>
              <img class="quest-scene__photo" src="${esc(imageSrc(image))}" alt="${esc(imageName(image))}" data-quest-photo>
              <span class="quest-scene__ring" aria-hidden="true"></span>
            </div>
            <div class="quest-scene__photo-caption"><span>HUBBLE · ${esc(imageName(image))}</span><span data-quest-caption>${zoomed ? 'Участок увеличен' : 'Нажми на снимок, чтобы увеличить участок'}</span></div>
            <div class="quest-scene__inspect-controls"><button type="button" data-quest="zoom">${zoomed ? 'Вернуться к снимку целиком' : 'Увеличить снимок'}</button></div>
          </section>
          <section class="quest-scene__side" aria-label="Ника и выбор метки">
            <div class="quest-scene__mentor">
              <aside class="quest-scene__nika" aria-label="Ника"><img src="assets/art/nika-${portraitMood()}-v1.png" alt="Ника, астроном" data-quest-mood="${portraitMood()}"></aside>
              <section class="quest-scene__conversation" aria-label="Разговор с Никой"><div class="quest-scene__line"><span>НИКА</span><p role="status" aria-live="polite">${esc(dialogue())}</p></div><div class="quest-scene__observation" aria-label="Помощь Ники"><button type="button" data-quest="hint" class="quest-scene__quiet">${stage === 'hint' ? 'Вернуться к заданию' : 'Попросить подсказку'}</button></div></section>
            </div>
            ${labels}
          </section>
        </div>
      </section>`;
      installGeometry();
    }
    function update() {
      if (destroyed) return;
      host.querySelector('[role="status"]').textContent = dialogue();
      const portrait = host.querySelector('[data-quest-mood]');
      const mood = portraitMood();
      if (portrait.dataset.questMood !== mood) {
        portrait.dataset.questMood = mood;
        portrait.src = `assets/art/nika-${mood}-v1.png`;
      }
      host.querySelectorAll('[data-quest-label]').forEach(button => {
        const selected = button.dataset.questLabel === (isTutorial ? tutorialChoice : options.selected);
        button.setAttribute('aria-pressed', String(selected));
        button.classList.toggle('is-selected', selected);
        button.querySelector('em').textContent = selected ? '✓' : '+';
      });
      host.querySelector('.quest-scene__photo-shell').classList.toggle('is-zoomed', zoomed);
      host.querySelector('.quest-scene__ring').hidden = false;
      host.querySelector('[data-quest-caption]').textContent = zoomed ? 'Участок увеличен' : 'Нажми на снимок, чтобы увеличить участок';
      const zoom = host.querySelector('[data-quest="zoom"]');
      zoom.textContent = zoomed ? 'Вернуться к снимку целиком' : 'Увеличить снимок';
      const hint = host.querySelector('[data-quest="hint"]');
      hint.textContent = stage === 'hint' ? 'Вернуться к заданию' : 'Попросить подсказку';
      syncGeometry?.();
    }
    let syncGeometry = null;
    function focus(selector) { host.querySelector(selector)?.focus({ preventScroll: true }); }
    function installGeometry() {
      const shell = host.querySelector('.quest-scene__photo-shell');
      const photo = host.querySelector('[data-quest-photo]');
      const ring = host.querySelector('.quest-scene__ring');
      if (!shell || !photo || !ring) return;
      const sync = () => {
        if (!point) return;
        const width = photo.clientWidth, height = photo.clientHeight;
        const naturalWidth = photo.naturalWidth || width, naturalHeight = photo.naturalHeight || height;
        const scale = Math.min(width / naturalWidth, height / naturalHeight);
        const actualWidth = naturalWidth * scale, actualHeight = naturalHeight * scale;
        // client/offset dimensions ignore CSS transforms, so this stays correct while zoomed.
        const imageX = (width - actualWidth) / 2 + point.x * actualWidth;
        const imageY = (height - actualHeight) / 2 + point.y * actualHeight;
        ring.style.left = `${photo.offsetLeft + imageX}px`;
        ring.style.top = `${photo.offsetTop + imageY}px`;
        // The transformed element includes the letterbox. Use the contained-image
        // pixel, rather than a percentage of that wider element, as its anchor.
        photo.style.transformOrigin = `${imageX}px ${imageY}px`;
      };
      syncGeometry = sync;
      photo.addEventListener('load', sync, { once: true });
      resizeObserver = typeof ResizeObserver === 'function' ? new ResizeObserver(sync) : null;
      resizeObserver?.observe(shell);
      sync();
    }
    function setPoint(next, shouldZoom = false) {
      point = next;
      points.set(image.id, point);
      zoomed = shouldZoom;
      stage = 'inspected';
      options.onZoom?.({ image, point, zoomed });
      render();
      focus('[data-quest="zoom"]');
    }
    function imagePoint(event, photo) {
      const rect = photo.getBoundingClientRect();
      const naturalWidth = photo.naturalWidth || rect.width;
      const naturalHeight = photo.naturalHeight || rect.height;
      const scale = Math.min(rect.width / naturalWidth, rect.height / naturalHeight);
      const width = naturalWidth * scale, height = naturalHeight * scale;
      const left = rect.left + (rect.width - width) / 2, top = rect.top + (rect.height - height) / 2;
      if (event.clientX < left || event.clientX > left + width || event.clientY < top || event.clientY > top + height) return null;
      return { x: Math.max(0, Math.min(1, (event.clientX - left) / width)), y: Math.max(0, Math.min(1, (event.clientY - top) / height)) };
    }
    function onClick(event) {
      const label = event.target.closest('[data-quest-label]');
      if (label) { event.stopPropagation(); if (isTutorial) { tutorialChoice = label.dataset.questLabel; stage = 'tutorial-choice'; update(); focus(`[data-quest-label="${tutorialChoice}"]`); } else options.onLabel?.(label.dataset.questLabel); return; }
      const action = event.target.closest('[data-quest]')?.dataset.quest;
      if (action === 'hint') { stage = stage === 'hint' ? 'briefing' : 'hint'; update(); focus('[data-quest="hint"]'); return; }
      if (action === 'zoom') { zoomed = !zoomed; options.onZoom?.({ image, point, zoomed }); render(); focus('[data-quest="zoom"]'); return; }
      const photo = event.target.closest('[data-quest-photo]');
      if (photo) {
        if (zoomed) { zoomed = false; stage = 'inspected'; options.onZoom?.({ image, point, zoomed }); render(); focus('[data-quest="zoom"]'); return; }
        const selected = imagePoint(event, photo);
        if (selected) setPoint(selected, true);
      }
    }
    host.addEventListener('click', onClick);
    render();
    return {
      updateSelection(value) { options.selected = value; stage = 'selected'; update(); },
      destroy() { if (!destroyed) { destroyed = true; resizeObserver?.disconnect(); host.removeEventListener('click', onClick); host.replaceChildren(); } },
      startConversation() { if (!destroyed) { stage = 'question'; render(); focus(isTutorial ? '[data-quest-label]' : '[data-quest="hint"]'); } },
      hint() { if (!destroyed) { stage = 'hint'; update(); focus('[data-quest="hint"]'); } },
      get point() { return point && { ...point }; }
    };
  }
  root.QuestScene = { mount, reset() { points.clear(); } };
})(globalThis);
