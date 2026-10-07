/* Desktop workbench scene. State that belongs to the lesson remains with the
   caller; this component only records an optional place the learner inspected. */
(function (root) {
  'use strict';
  const points = new Map();
  const observations = {
    arms: 'Тебе бросились в глаза рукава. Теперь нажми на ту часть снимка, которую хочешь рассмотреть ближе.',
    smooth: 'Твоё наблюдение — ровный свет. Нажми на участок снимка, который хочешь рассмотреть ближе.',
    edge: 'Тебе заметен диск с ребра. Нажми на ту часть снимка, которую хочешь рассмотреть ближе.'
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
    let observation = null;
    let resizeObserver = null;
    let point = points.get(options.image.id) || null;
    const image = options.image;
    const classes = Array.isArray(options.classes) ? options.classes : [];
    const isTutorial = options.phase === 'tutorial';
    const old = options.initialOldLabel;
    const selectedClass = classes.find(item => item.id === (options.initialSelected || options.selected));
    function portraitMood() {
      if (options.phase === 'repair' || stage === 'hint') return 'thinking';
      return stage === 'inspected' || options.initialSelected ? 'warm' : 'curious';
    }

    function dialogue() {
      if (stage === 'observed') return observations[observation];
      if (stage === 'inspected') return 'Это выбранный тобой участок. Увеличение помогает рассмотреть изображение, но метку выбираешь ты.';
      if (stage === 'hint') return image.explanation || 'Посмотри на форму света, а затем выбери метку сам.';
      if (options.opening) return options.opening;
      if (options.initialSelected) return typeof options.initialSelected === 'string' && !selectedClass
        ? options.initialSelected
        : `Твоя метка «${selectedClass?.label || options.initialSelected}» сохранена. Можно ещё раз посмотреть на снимок или перейти к следующему примеру.`;
      return 'Что первым бросается в глаза на этом снимке?';
    }
    function render() {
      if (destroyed) return;
      resizeObserver?.disconnect();
      const labels = isTutorial ? '' : `<section class="quest-scene__labels" aria-label="Выбор метки">
        <div class="quest-scene__label-heading"><span>ТВОЯ МЕТКА</span><b>${old ? 'Старая подпись — только повод проверить снимок' : 'Выбери метку после наблюдения'}</b></div>
        ${old ? `<p class="quest-scene__old">В архиве было: <b>${esc(old)}</b></p>` : ''}
        <div class="quest-scene__label-list">${classes.map(item => `<button type="button" class="quest-scene__label ${esc(item.id)} ${options.selected === item.id ? 'is-selected' : ''}" data-quest-label="${esc(item.id)}" data-label-id="${esc(image.id)}" data-label="${esc(item.id)}" aria-pressed="${options.selected === item.id}"><i aria-hidden="true"></i><span><b>${esc(item.label)}</b><small>${esc(item.hint || '')}</small></span><em aria-hidden="true">${options.selected === item.id ? '✓' : '+'}</em></button>`).join('')}</div>
      </section>`;
      host.innerHTML = `<section class="quest-scene" data-quest-phase="${esc(options.phase || '')}">
        <div class="quest-scene__main">
          <section class="quest-scene__photo-area" aria-label="Снимок ${esc(imageName(image))}">
            <div class="quest-scene__photo-shell ${zoomed ? 'is-zoomed' : ''}" ${pointStyle(point)}>
            <img class="quest-scene__photo" src="${esc(imageSrc(image))}" alt="${esc(imageName(image))}" data-quest-photo>
              ${point ? '<span class="quest-scene__ring" aria-hidden="true"></span>' : ''}
            </div>
            <div class="quest-scene__photo-caption"><span>HUBBLE · ${esc(imageName(image))}</span><span>${point ? 'Выбранный участок отмечен' : 'Нажми на изображение, чтобы рассмотреть деталь'}</span></div>
            <div class="quest-scene__inspect-controls">
              <button type="button" data-quest="center">Отметить центр снимка</button>
              <button type="button" data-quest="zoom" ${point ? '' : 'disabled'}>${zoomed ? 'Вернуться к снимку целиком' : 'Увеличить выбранный участок'}</button>
            </div>
          </section>
          <aside class="quest-scene__nika" aria-label="Ника">
            <img src="assets/art/nika-${portraitMood()}-v1.png" alt="Ника, астроном" data-quest-mood="${portraitMood()}">
          </aside>
        </div>
        <section class="quest-scene__conversation" aria-label="Разговор с Никой">
          <div class="quest-scene__line"><span>НИКА</span><p role="status" aria-live="polite">${esc(dialogue())}</p></div>
          <div class="quest-scene__observation" aria-label="Наблюдение на снимке">
            <span>СНАЧАЛА НАБЛЮДЕНИЕ</span>
            <div><button type="button" data-quest-observation="arms" aria-pressed="${observation === 'arms'}">Вижу рукава</button><button type="button" data-quest-observation="smooth" aria-pressed="${observation === 'smooth'}">Вижу ровный свет</button><button type="button" data-quest-observation="edge" aria-pressed="${observation === 'edge'}">Вижу диск с ребра</button><button type="button" data-quest="hint" class="quest-scene__quiet">Подсказка Ники</button></div>
          </div>
        </section>
        ${labels}
      </section>`;
      installGeometry();
    }
    function focus(selector) { host.querySelector(selector)?.focus({ preventScroll: true }); }
    function installGeometry() {
      const shell = host.querySelector('.quest-scene__photo-shell');
      const photo = host.querySelector('[data-quest-photo]');
      const ring = host.querySelector('.quest-scene__ring');
      if (!shell || !photo || !ring || !point) return;
      const sync = () => {
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
      photo.addEventListener('load', sync, { once: true });
      resizeObserver = typeof ResizeObserver === 'function' ? new ResizeObserver(sync) : null;
      resizeObserver?.observe(shell);
      sync();
    }
    function setPoint(next) {
      point = next;
      points.set(image.id, point);
      zoomed = false;
      stage = 'inspected';
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
      const observationButton = event.target.closest('[data-quest-observation]');
      if (observationButton) { observation = observationButton.dataset.questObservation; stage = 'observed'; render(); focus(`[data-quest-observation="${observation}"]`); return; }
      const label = event.target.closest('[data-quest-label]');
      if (label) { event.stopPropagation(); options.onLabel?.(label.dataset.questLabel); return; }
      const action = event.target.closest('[data-quest]')?.dataset.quest;
      if (action === 'hint') { stage = 'hint'; render(); focus('[data-quest="hint"]'); return; }
      if (action === 'center') { setPoint({ x: .5, y: .5 }); return; }
      if (action === 'zoom' && point) { zoomed = !zoomed; options.onZoom?.({ image, point, zoomed }); render(); focus('[data-quest="zoom"]'); return; }
      const photo = event.target.closest('[data-quest-photo]');
      if (photo) {
        if (zoomed) { zoomed = false; stage = 'inspected'; render(); focus('[data-quest="zoom"]'); return; }
        const selected = imagePoint(event, photo);
        if (selected) setPoint(selected);
      }
    }
    host.addEventListener('click', onClick);
    render();
    return {
      destroy() { if (!destroyed) { destroyed = true; resizeObserver?.disconnect(); host.removeEventListener('click', onClick); host.replaceChildren(); } },
      startConversation() { if (!destroyed) { stage = 'question'; observation = null; render(); focus('[data-quest-observation="arms"]'); } },
      hint() { if (!destroyed) { stage = 'hint'; render(); focus('[data-quest="hint"]'); } },
      get point() { return point && { ...point }; }
    };
  }
  root.QuestScene = { mount, reset() { points.clear(); } };
})(globalThis);
