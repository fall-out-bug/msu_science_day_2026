/* Interactive archival sky atlas. Load sky-data.js first. Coordinates are
   the ICRS/J2000 centres published on the linked ESA/Hubble image pages. */
(function () {
  'use strict';
  const TARGETS = {
    child_m85: {name: 'Messier 85', ra: 186.35, dec: 18.18793, source: 'ESA/Hubble · potw1905a'},
    child_ic5332: {name: 'IC 5332', ra: 353.61058, dec: -36.10005, source: 'ESA/Hubble · potw2342a'},
    child_ngc5023: {name: 'NGC 5023', ra: 198.05117, dec: 44.04015, source: 'ESA/Hubble · potw1512a'}
  };
  const clamp = (v, min, max) => Math.max(min, Math.min(max, v));
  const wrap = n => (n % 360 + 360) % 360;
  const delta = n => wrap(n + 180) - 180;
  const reduce = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
  // Exact subset of the admitted Stellarium western sky culture (see sky-provenance.json).
  const FALLBACK_CONSTELLATIONS = [{"name":"Скульптор","lines":[[[353.24,-37.82],[14.65,-29.36],[349.71,-32.53],[353.24,-37.82]]],"ra":357.95,"dec":-34.8},{"name":"Кассиопея","lines":[[[28.6,63.67],[21.45,60.24],[14.18,60.72],[10.13,56.54],[2.29,59.15]]],"ra":14.85,"dec":60.36},{"name":"Волосы Вероники","lines":[[[197.5,17.53],[197.97,27.88],[186.73,28.27]]],"ra":194.17,"dec":24.65},{"name":"Гончие Псы","lines":[[[188.44,41.36],[194.01,38.32]]],"ra":191.29,"dec":39.87},{"name":"Лебедь","lines":[[[289.28,53.37],[292.43,51.73],[296.24,45.13],[305.56,40.26],[311.55,33.97],[318.23,30.23],[326.04,28.74]],[[292.68,27.96],[299.08,35.08],[305.56,40.26],[310.36,45.28]]],"ra":305.08,"dec":39.81},{"name":"Большая Медведица","lines":[[[206.89,49.31],[200.98,54.93],[193.51,55.96],[183.86,57.03],[178.46,53.69],[165.46,56.38],[148.03,54.06],[143.22,51.68],[134.8,48.04]],[[183.86,57.03],[165.93,61.75],[165.46,56.38]],[[178.46,53.69],[176.51,47.78],[167.42,44.5],[155.58,41.5]],[[167.42,44.5],[154.27,42.91]],[[143.22,51.68],[135.91,47.16]],[[148.03,54.06],[147.75,59.04],[127.57,60.72],[142.88,63.06],[165.93,61.75]]],"ra":163.1,"dec":54.92},{"name":"Лира","lines":[[[279.23,38.78],[281.19,37.61],[282.52,33.36],[284.74,32.69],[283.63,36.9],[281.19,37.61]]],"ra":282.12,"dec":36.17},{"name":"Орион","lines":[[[81.28,6.35],[83.78,9.93],[88.79,7.41],[85.19,-1.94],[84.05,-1.2],[83.0,-0.3],[81.28,6.35],[72.46,6.96],[72.65,8.9],[73.72,10.15]],[[92.98,14.21],[91.89,14.77],[88.6,20.28],[90.98,20.14],[93.01,16.13],[92.98,14.21],[90.6,9.65],[88.79,7.41]],[[85.19,-1.94],[86.94,-9.67],[78.63,-8.2],[83.0,-0.3]],[[72.46,6.96],[72.8,5.61],[73.34,2.51],[74.64,1.71]],[[91.89,14.77],[90.6,9.65]]],"ra":83.71,"dec":6.86}];

  function open(options) {
    if (!globalThis.OBSERVATORY_SKY_DATA) throw new Error('Load sky-data.js before sky.js');
    const data = globalThis.OBSERVATORY_SKY_DATA;
    const gameData = globalThis.GALAXY_DATA || {images: [], childIds: []};
    const imageById = Object.fromEntries((gameData.images || []).map(image => [image.id, image]));
    const taskIds = (gameData.childIds || Object.keys(TARGETS)).filter(id => imageById[id] || TARGETS[id]);
    for (const id of taskIds) { const image = imageById[id] || {}; TARGETS[id] = {name:image.name || TARGETS[id]?.name || id, ra:Number(image.ra ?? TARGETS[id]?.ra), dec:Number(image.dec ?? TARGETS[id]?.dec), source:image.source || TARGETS[id]?.source}; }
    const hasCoordinates = item => typeof item?.ra === 'number' && Number.isFinite(item.ra) && typeof item?.dec === 'number' && Number.isFinite(item.dec);
    const archives = (globalThis.GALAXY_ARCHIVE?.images || []).filter(hasCoordinates);
    const archiveById = Object.fromEntries(archives.map(image => [image.id, image]));
    const discoveryEntries = globalThis.GALAXY_DISCOVERIES || [];
    const discoveries = discoveryEntries.filter(hasCoordinates);
    const researchWithoutCoordinates = discoveryEntries.filter(item => !hasCoordinates(item));
    const constellations = (globalThis.NIGHT_CONSTELLATIONS || FALLBACK_CONSTELLATIONS).filter(item => item.lines).slice(0, 8);
    const mode = options.initialTarget ? 'task' : 'browse';
    const guided = Boolean(options.guided);
    const collected = new Set(options.collectedIds || []);
    const ids = taskIds.length ? taskIds : Object.keys(TARGETS);
    const host = document.createElement('section');
    host.className = 'sky-atlas';
    host.setAttribute('role', 'dialog');
    host.setAttribute('aria-modal', 'true');
    host.setAttribute('aria-label', 'Архивная карта неба');
    host.innerHTML = `<canvas class="sky-atlas__canvas" tabindex="0" aria-label="Архивная карта неба. Тяните мышью или пальцем, колесо меняет масштаб. Стрелки перемещают карту."></canvas>
      <header class="sky-atlas__head"><div><span>КАРТА ЗВЁЗДНОГО НЕБА</span><h2>${mode === 'task' ? (guided ? 'Собери архивные снимки' : 'Найди галактику на карте') : 'Исследуй небо'}</h2></div><button type="button" class="sky-atlas__close" aria-label="Закрыть карту">×</button></header>
      <nav class="sky-atlas__controls" aria-label="Масштаб карты"><button type="button" data-scale="in" aria-label="Увеличить карту">+</button><button type="button" data-scale="out" aria-label="Уменьшить карту">−</button><button type="button" data-scale="all">Всё небо</button></nav>
      <aside class="sky-atlas__panel ${mode}">${mode === 'task' ? '<div class="sky-atlas__task-content"></div>' : `<p class="sky-atlas__truth">Здесь отмечены реальные архивные снимки и истории исследований.</p><p class="sky-atlas__legend">□ Снимки · ◇ Истории · ○ Задание</p><div class="sky-atlas__filters" role="group" aria-label="Фильтр карты"><button class="active" data-filter="all">Всё</button><button data-filter="ai">Открытия ИИ</button><button data-filter="image">Снимки</button><button data-filter="research">Исследования</button><button data-filter="task">Наше задание</button></div><div class="sky-atlas__research-list">${researchWithoutCoordinates.map(item => `<button type="button" data-category="${item.category}" data-research-id="${String(item.id).replace(/&/g,'&amp;').replace(/"/g,'&quot;')}">${item.title || 'Исследование'}</button>`).join('')}</div><button type="button" class="sky-atlas__tasks">Найти снимки для модели</button><p class="sky-atlas__hint" aria-live="polite">Тяни карту, приближай и нажимай цветные метки.</p>`}<details class="sky-atlas__sources"><summary>Источники карты</summary><a href="sky-provenance.json" target="_blank" rel="noopener">NASA SVS и каталог HYG</a></details></aside>
      <footer class="sky-atlas__foot">NASA SVS Deep Star Maps 2020 · звёзды HYG v4.1 (CC BY-SA 4.0) · ICRS/J2000</footer>`;
    document.body.append(host);
    const canvas = host.querySelector('canvas'), ctx = canvas.getContext('2d');
    let hint=host.querySelector('.sky-atlas__hint'), openButton, completeButton, targetButtons=[];
    const texture = new Image();
    const returnFocus = document.activeElement;
    let width = 1, height = 1, dpr = 1, camera = {ra: 180, dec: 0, zoom: 2.6}, active = null, aligned = false, filter = 'all', hovered = null;
    let drag = null, last = 0, raf = 0, closed = false;

    function formatRa(ra) { const h = ra / 15; const hh = Math.floor(h); const mm = Math.round((h - hh) * 60); return `${String(hh).padStart(2, '0')}ʰ ${String(mm).padStart(2, '0')}ᵐ`; }
    function formatDec(dec) { return `${dec < 0 ? '−' : '+'}${Math.abs(dec).toFixed(1)}°`; }
    function aim() { if (width >= 701 && height <= 500) return [width * .72, height * .55]; return width < 700 ? [width * .55, height * .4] : [width / 2, height / 2]; }
    // NASA's plate carrée texture maps increasing RA to the left. Keep the
    // catalog points in the exact same frame: x = ((180 - RA) mod 360).
    function project(ra, dec) { const [ax, ay] = aim(); return [ax - delta(ra - camera.ra) * camera.zoom, ay - (dec - camera.dec) * camera.zoom]; }
    function targetPixel() { return active ? project(TARGETS[active].ra, TARGETS[active].dec) : null; }
    function separation(target) { const d = (target.dec - camera.dec) * Math.PI / 180, a = delta(target.ra - camera.ra) * Math.PI / 180; return 2 * Math.asin(Math.sqrt(clamp(Math.sin(d / 2) ** 2 + Math.cos(target.dec * Math.PI / 180) * Math.cos(camera.dec * Math.PI / 180) * Math.sin(a / 2) ** 2, 0, 1))) * 180 / Math.PI; }
    function updateAlignment() { if (mode !== 'task' || !active || collected.has(active)) { aligned = false; if (openButton) openButton.disabled = true; return; } const p = targetPixel(), target = TARGETS[active]; aligned = Math.hypot(p[0] - aim()[0], p[1] - aim()[1]) <= 22 && separation(target) <= 1.2; if (openButton) openButton.disabled = !aligned; if (hint) hint.textContent = aligned ? `Галактика ${target.name} в прицеле. Добавь её архивный снимок в подборку.` : `Перетащи карту, чтобы ${target.name} попала в прицел. Или нажми на неё.`; }
    function resize() { const r = canvas.getBoundingClientRect(); width = Math.max(1, r.width); height = Math.max(1, r.height); dpr = Math.min(2, devicePixelRatio || 1); canvas.width = width * dpr; canvas.height = height * dpr; if (mode === 'browse' && camera.zoom === 2.6) camera.zoom = Math.max(2.4, Math.min(width / 360, height / 180)); updateAlignment(); draw(); }
    function request() { if (!raf) raf = requestAnimationFrame(() => { raf = 0; draw(); }); }
    function draw() {
      if (closed) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const g = ctx.createRadialGradient(width * .52, height * .45, 0, width * .52, height * .45, Math.max(width, height) * .76);
      g.addColorStop(0, '#112744'); g.addColorStop(.55, '#061323'); g.addColorStop(1, '#020712'); ctx.fillStyle = g; ctx.fillRect(0, 0, width, height);
      if (texture.complete && texture.naturalWidth) {
        const [ax, ay] = aim(), world = 360 * camera.zoom, worldX = wrap(180 - camera.ra), x = ax - worldX * camera.zoom, y = ay - (90 - camera.dec) * camera.zoom;
        ctx.globalAlpha = .68;
        for (let i = -1; i <= 1; i++) ctx.drawImage(texture, x + i * world, y, world, world / 2);
      }
      ctx.globalAlpha = 1;
      for (const star of data.stars) {
        const p = project(star[0], star[1]); if (p[0] < -4 || p[0] > width + 4 || p[1] < -4 || p[1] > height + 4) continue;
        const radius = clamp(2.6 - (star[2] + 1.5) * .38, .45, 2.7);
        ctx.fillStyle = star[2] < 1.2 ? '#fff7d4' : '#dceaff'; ctx.globalAlpha = .38 + (5.5 - star[2]) * .08;
        ctx.beginPath(); ctx.arc(p[0], p[1], radius, 0, Math.PI * 2); ctx.fill();
      }
      ctx.globalAlpha = 1;
      drawConstellations(); drawExploreMarkers();
      if (mode === 'task') for (const id of ids) drawTarget(id);
      if (mode === 'task') { const [ax, ay] = aim(); ctx.strokeStyle = aligned ? '#b9ecd9' : 'rgba(230,244,255,.88)'; ctx.lineWidth = 1.3; ctx.beginPath(); ctx.arc(ax, ay, 25, 0, Math.PI * 2); ctx.stroke(); ctx.beginPath(); ctx.moveTo(ax - 42, ay); ctx.lineTo(ax - 16, ay); ctx.moveTo(ax + 16, ay); ctx.lineTo(ax + 42, ay); ctx.moveTo(ax, ay - 42); ctx.lineTo(ax, ay - 16); ctx.moveTo(ax, ay + 16); ctx.lineTo(ax, ay + 42); ctx.stroke(); }
      ctx.font = '600 12px system-ui, sans-serif'; ctx.textAlign = 'center'; ctx.fillStyle = 'rgba(229,241,255,.72)';
      ctx.fillText(`RA ${formatRa(wrap(camera.ra))} · Dec ${formatDec(camera.dec)}`, width / 2, height - 22);
    }
    function visible(marker) { if (guided) return marker.type === 'task'; if (filter === 'all') return true; if (filter === 'task') return marker.type === 'task'; if (filter === 'image') return marker.type === 'archive' || marker.category === 'image' || marker.category === 'object'; if (filter === 'research') return marker.category === 'research' || marker.kind === 'research'; return marker.type === 'discovery' && (marker.category==='discovery'|| /ии|ai|machine|нейросет/i.test([marker.category, marker.kind, marker.title, marker.text].join(' '))); }
    function drawConstellations() { if (camera.zoom > 7) return; for (const c of constellations) { ctx.globalAlpha = .62; ctx.strokeStyle = '#72a8d8'; ctx.lineWidth = 1; for (const line of c.lines) for (let i = 1; i < line.length; i++) { const a=project(...line[i-1]),b=project(...line[i]); if (Math.abs(a[0]-b[0]) > 180*camera.zoom) continue; ctx.beginPath();ctx.moveTo(...a);ctx.lineTo(...b);ctx.stroke(); } const p=project(c.ra,c.dec); if(p[0]>38&&p[0]<width-38&&p[1]>76&&p[1]<height-25){ctx.globalAlpha=.9;ctx.font='600 12px system-ui';ctx.textAlign='center';ctx.fillStyle='#b7d9f2';ctx.fillText(c.name,p[0],p[1]);} } ctx.globalAlpha=1; }
    function markers() { return [...ids.map(id => ({...TARGETS[id],id,type:'task',category:'task'})),...archives.map(item=>({...item,type:'archive'})),...discoveries.map(item=>({...item,type:'discovery'}))]; }
    function drawExploreMarkers() { for (const marker of markers()) { if (!visible(marker) || (mode === 'task' && marker.type === 'task')) continue; const p=project(Number(marker.ra),Number(marker.dec));if(p[0]<-20||p[0]>width+20||p[1]<-20||p[1]>height+20)continue;const hover=hovered?.id===marker.id&&hovered?.type===marker.type;const color=marker.type==='archive'?'#77d6ff':marker.type==='task'?'#ffd88c':marker.category==='research'||marker.kind==='research'?'#d4a6ff':(marker.category==='discovery'||/ии|ai|machine|нейросет/i.test([marker.category,marker.kind,marker.title,marker.text].join(' ')))?'#83f1b8':'#ff9ec5';ctx.globalAlpha=.95;ctx.strokeStyle=color;ctx.fillStyle='#061525';ctx.lineWidth=hover?3:2;ctx.beginPath();if(marker.type==='archive')ctx.rect(p[0]-6,p[1]-6,12,12);else if(marker.type==='task')ctx.arc(p[0],p[1],8,0,Math.PI*2);else{ctx.moveTo(p[0],p[1]-8);ctx.lineTo(p[0]+8,p[1]);ctx.lineTo(p[0],p[1]+8);ctx.lineTo(p[0]-8,p[1]);ctx.closePath();}ctx.fill();ctx.stroke();if(hover){const title=marker.title||marker.name;ctx.font='700 12px system-ui';const tw=ctx.measureText(title).width,lx=clamp(p[0],tw/2+10,width-tw/2-10),ly=clamp(p[1]-18,90,height-20);ctx.fillStyle='rgba(1,8,18,.88)';ctx.fillRect(lx-tw/2-6,ly-15,tw+12,21);ctx.fillStyle=color;ctx.textAlign='center';ctx.fillText(title,lx,ly);}}ctx.globalAlpha=1; }
    function drawTarget(id) {
      const target = TARGETS[id], [x, y] = project(target.ra, target.dec); if (x < -80 || x > width + 80 || y < -80 || y > height + 80) return;
      const selected = active === id, pulse = reduce() ? 1 : 1 + Math.sin(performance.now() / 450) * .12;
      ctx.strokeStyle = selected ? '#a9ffe0' : '#ffd88c'; ctx.lineWidth = selected ? 2.5 : 1.5; ctx.globalAlpha = .95;
      ctx.beginPath(); ctx.arc(x, y, 14 * pulse, 0, Math.PI * 2); ctx.stroke(); ctx.beginPath(); ctx.moveTo(x - 23, y); ctx.lineTo(x - 10, y); ctx.moveTo(x + 10, y); ctx.lineTo(x + 23, y); ctx.moveTo(x, y - 23); ctx.lineTo(x, y - 10); ctx.moveTo(x, y + 10); ctx.lineTo(x, y + 23); ctx.stroke();
      ctx.font = '700 13px system-ui, sans-serif'; const tw = ctx.measureText(target.name).width;
      if (x - tw / 2 - 8 >= 4 && x + tw / 2 + 8 <= width - 4 && y - 46 >= 74 && y - 20 <= height - 4) { ctx.fillStyle = 'rgba(1,8,18,.82)'; ctx.fillRect(x - tw / 2 - 8, y - 43, tw + 16, 22); ctx.fillStyle = selected ? '#bfffe7' : '#ffe0a1'; ctx.textAlign = 'center'; ctx.fillText(target.name, x, y - 28); }
    }
    function attachTaskPanel() {
      const taskHost=host.querySelector('.sky-atlas__task-content');
      if (!taskHost) return;
      if (!guided) {
        taskHost.innerHTML=`<p class="sky-atlas__truth">Найдём положение галактики на карте и откроем её архивный снимок Hubble.</p><div class="sky-atlas__targets">${ids.map(id => `<button type="button" data-target="${id}">${TARGETS[id].name}<small>RA ${formatRa(TARGETS[id].ra)} · Dec ${formatDec(TARGETS[id].dec)}</small></button>`).join('')}</div><p class="sky-atlas__hint" aria-live="polite">Выбери объект в списке или найди его на карте.</p><button type="button" class="sky-atlas__open" disabled>Открыть архивный снимок</button>`;
        hint=taskHost.querySelector('.sky-atlas__hint'); openButton=taskHost.querySelector('.sky-atlas__open'); completeButton=null; targetButtons=[...taskHost.querySelectorAll('[data-target]')];
        targetButtons.forEach(button=>button.addEventListener('click',()=>select(button.dataset.target,true)));
        openButton.addEventListener('click',()=>{if(!aligned||!active)return;const id=active;close();options.onSelect?.(id);});
        return;
      }
      const remaining=ids.filter(id=>!collected.has(id));
      taskHost.innerHTML=`<p class="sky-atlas__truth">${guided?'Собери три уже существующих архивных снимка Hubble для учебной подборки.':'Найдём положение галактики на карте и откроем её архивный снимок Hubble.'}</p><div class="sky-atlas__targets">${ids.map(id=>{const done=collected.has(id),image=imageById[id];return `<button type="button" data-target="${id}" class="${done?'is-collected':''}" ${done?'disabled':''}>${done&&image?`<img src="${image.src}" alt="">`:''}<span>${TARGETS[id].name}<small>${done?'Добавлено в подборку ✓':`RA ${formatRa(TARGETS[id].ra)} · Dec ${formatDec(TARGETS[id].dec)}`}</small></span></button>`;}).join('')}</div><p class="sky-atlas__hint" aria-live="polite">${remaining.length?`Собрано ${collected.size} из ${ids.length}. Выбери объект в списке или найди его на карте.`:'Подборка собрана: три снимка готовы к разметке.'}</p>${remaining.length?'<button type="button" class="sky-atlas__open" disabled>Добавить архивный снимок</button>':'<button type="button" class="sky-atlas__complete">К рабочему столу →</button>'}`;
      hint=taskHost.querySelector('.sky-atlas__hint'); openButton=taskHost.querySelector('.sky-atlas__open'); completeButton=taskHost.querySelector('.sky-atlas__complete'); targetButtons=[...taskHost.querySelectorAll('[data-target]')];
      targetButtons.forEach(button=>button.addEventListener('click',()=>select(button.dataset.target,true)));
      openButton?.addEventListener('click',collectActive);
      completeButton?.addEventListener('click',()=>{close();options.onComplete?.();});
    }
    function select(id, move) {
      active = id; const t = TARGETS[id]; if (openButton) openButton.disabled = true;
      targetButtons.forEach(b => b.classList.toggle('active', b.dataset.target === id));
      hint.textContent = `Цель: ${t.name}. Перетащи карту, чтобы галактика попала в прицел.`;
      if (move) focus(id); updateAlignment(); request();
    }
    function collectActive() {
      if (!aligned || !active || collected.has(active)) return;
      const id=active; collected.add(id); options.onCollect?.(id);
      attachTaskPanel();
      const next=ids.find(item=>!collected.has(item));
      if (next) select(next,true); else { active=null; aligned=false; request(); }
    }
    function focus(id) {
      const t = TARGETS[id], start = {...camera}, zoom = Math.max(7.5, Math.min(width / 28, height / 18)), end = {ra: wrap(t.ra - width * .15 / zoom), dec: clamp(t.dec + height * .1 / zoom, -85, 85), zoom};
      if (reduce()) { camera = end; updateAlignment(); request(); return; }
      const begun = performance.now(); const tick = now => { const p = clamp((now - begun) / 600, 0, 1), e = p * p * (3 - 2 * p); camera = {ra: wrap(start.ra + delta(end.ra - start.ra) * e), dec: start.dec + (end.dec - start.dec) * e, zoom: start.zoom + (end.zoom - start.zoom) * e}; updateAlignment(); request(); if (p < 1 && !closed) requestAnimationFrame(tick); }; requestAnimationFrame(tick);
    }
    function markerAt(x, y) { const ordered=markers().filter(marker=>visible(marker)&&!(mode==='task'&&marker.type==='task'&&collected.has(marker.id))).reverse();if(mode==='task')ordered.sort((a,b)=>(a.id===active&&a.type==='task'?-2:a.type==='task'?-1:0)-(b.id===active&&b.type==='task'?-2:b.type==='task'?-1:0));return ordered.find(marker => { const p = project(Number(marker.ra), Number(marker.dec)); return Math.hypot(p[0] - x, p[1] - y) < 22; }); }
    function pick(x, y) { const marker = markerAt(x, y); if (!marker) return false; if (marker.type === 'task' && mode === 'task') { active = marker.id; targetButtons.forEach(b => b.classList.toggle('active', b.dataset.target === marker.id)); camera.ra = marker.ra; camera.dec = marker.dec; updateAlignment(); request(); return true; } if (marker.type === 'archive' || marker.type === 'task') { options.onArchive?.(marker.id); return true; } if (marker.type === 'discovery') { options.onDiscovery?.(marker.id); return true; } return true; }
    function point(e) { const r = canvas.getBoundingClientRect(); return {x: e.clientX - r.left, y: e.clientY - r.top}; }
    function close() { if (closed) return; closed = true; cancelAnimationFrame(raf); observer.disconnect(); host.remove(); if (returnFocus?.focus) returnFocus.focus({preventScroll: true}); options.onClose?.(); }
    const observer = new ResizeObserver(resize); observer.observe(canvas);
    texture.onload = request; texture.src = data.texture;
    canvas.addEventListener('pointerdown', e => { const p = point(e); drag = {x: p.x, y: p.y, moved: false, pointer: e.pointerId}; canvas.setPointerCapture(e.pointerId); canvas.focus({preventScroll: true}); });
    canvas.addEventListener('pointermove', e => { const p = point(e); if (!drag || drag.pointer !== e.pointerId) { const next = markerAt(p.x, p.y) || null; if (next?.id !== hovered?.id || next?.type !== hovered?.type) { hovered = next; canvas.style.cursor = next ? 'pointer' : 'grab'; request(); } return; } const dx = p.x - drag.x, dy = p.y - drag.y; if (Math.hypot(dx, dy) > 5) drag.moved = true; camera.ra = wrap(camera.ra + dx / camera.zoom); camera.dec = clamp(camera.dec + dy / camera.zoom, -85, 85); drag.x = p.x; drag.y = p.y; updateAlignment(); request(); });
    function releasePointer(e) { if (!drag || drag.pointer !== e.pointerId) return; const p = point(e), was = drag; drag = null; if (canvas.hasPointerCapture(e.pointerId)) canvas.releasePointerCapture(e.pointerId); if (e.type === 'pointerup' && !was.moved) pick(p.x, p.y); }
    canvas.addEventListener('pointerup', releasePointer); canvas.addEventListener('pointercancel', releasePointer); canvas.addEventListener('lostpointercapture', releasePointer);
    canvas.addEventListener('wheel', e => { e.preventDefault(); camera.zoom = clamp(camera.zoom * Math.exp(-e.deltaY * .0015), .7, 80); updateAlignment(); request(); }, {passive: false});
    canvas.addEventListener('keydown', e => { const step = (e.shiftKey ? 80 : 28) / camera.zoom; if (e.key === 'ArrowLeft') camera.ra = wrap(camera.ra - step); else if (e.key === 'ArrowRight') camera.ra = wrap(camera.ra + step); else if (e.key === 'ArrowUp') camera.dec = clamp(camera.dec + step, -85, 85); else if (e.key === 'ArrowDown') camera.dec = clamp(camera.dec - step, -85, 85); else if (e.key === '+' || e.key === '=') camera.zoom = clamp(camera.zoom * 1.25, .7, 80); else if (e.key === '-' || e.key === '_') camera.zoom = clamp(camera.zoom / 1.25, .7, 80); else if (e.key === 'Escape') { close(); return; } else return; e.preventDefault(); updateAlignment(); request(); });
    host.querySelector('.sky-atlas__close').addEventListener('click', close);
    host.querySelectorAll('[data-scale]').forEach(button => button.addEventListener('click', () => { const action = button.dataset.scale; if (action === 'all') camera = {ra: 180, dec: 0, zoom: Math.max(.7, Math.min(width / 360, height / 180))}; else camera.zoom = clamp(camera.zoom * (action === 'in' ? 1.3 : 1 / 1.3), .7, 80); updateAlignment(); request(); canvas.focus({preventScroll: true}); }));
    host.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => { filter = button.dataset.filter; host.querySelectorAll('[data-filter]').forEach(item => item.classList.toggle('active', item === button)); const list = host.querySelector('.sky-atlas__research-list'); if(list){for(const row of list.querySelectorAll('[data-category]'))row.hidden=!(filter==='all'||filter==='ai'&&row.dataset.category==='discovery'||filter===row.dataset.category||filter==='image'&&row.dataset.category==='object');list.hidden=![...list.children].some(row=>!row.hidden);} hint.textContent = filter === 'task' ? 'Здесь — три снимка для учебной модели.' : filter === 'research' ? (researchWithoutCoordinates.length ? 'Выбери исследование из списка или цветную метку на карте.' : 'Нажимай фиолетовые метки исследований на карте.') : 'Тяни карту, приближай и нажимай цветные метки.'; request(); }));
    host.querySelectorAll('[data-research-id]').forEach(button => button.addEventListener('click', () => options.onDiscovery?.(button.dataset.researchId)));
    host.querySelector('.sky-atlas__tasks')?.addEventListener('click', () => { if (typeof options.onTasks === 'function') { close(); options.onTasks(); } else hint.textContent = 'Открой карту из задания — она приведёт к трём снимкам для модели.'; });
    host.addEventListener('keydown', e => { if (e.key === 'Escape') close(); if (e.key === 'Tab') { const focusable = [...host.querySelectorAll('button,[tabindex]:not([tabindex="-1"])')].filter(el => !el.disabled && el.getClientRects().length && !el.closest('[hidden]')); const index = focusable.indexOf(document.activeElement); if (e.shiftKey && index <= 0) { e.preventDefault(); focusable.at(-1).focus(); } else if (!e.shiftKey && index === focusable.length - 1) { e.preventDefault(); focusable[0].focus(); } } });
    if (mode === 'task') attachTaskPanel();
    resize();
    if (mode === 'task') { const initial = TARGETS[options.initialTarget] ? options.initialTarget : ids[0]; select(initial, true); } canvas.focus({preventScroll: true});
    last = performance.now();
    (function alive(now) { if (closed) return; if (!reduce() && now - last > 30) { last = now; request(); } requestAnimationFrame(alive); })(last);
    return {close, focusTarget: id => TARGETS[id] && select(id, true), state: () => ({active, aligned, camera: {...camera}, targets: ids.slice()}), snapshot: () => ({active, aligned, targetPixel: targetPixel() && {x: targetPixel()[0], y: targetPixel()[1]}, aim: {x: aim()[0], y: aim()[1]}, camera: {...camera}, source: data.source})};
  }
  globalThis.GalaxySky = {open};
})();
