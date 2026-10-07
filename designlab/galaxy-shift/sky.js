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

  function open(options) {
    if (!globalThis.OBSERVATORY_SKY_DATA) throw new Error('Load sky-data.js before sky.js');
    const data = globalThis.OBSERVATORY_SKY_DATA;
    const ids = Object.keys(TARGETS);
    const host = document.createElement('section');
    host.className = 'sky-atlas';
    host.setAttribute('role', 'dialog');
    host.setAttribute('aria-modal', 'true');
    host.setAttribute('aria-label', 'Архивная карта неба');
    host.innerHTML = `<canvas class="sky-atlas__canvas" tabindex="0" aria-label="Архивная карта неба. Тяните мышью или пальцем, колесо меняет масштаб. Стрелки перемещают карту."></canvas>
      <header class="sky-atlas__head"><div><span>КАРТА ЗВЁЗДНОГО НЕБА</span><h2>Найди галактику на карте</h2></div><button type="button" class="sky-atlas__close" aria-label="Закрыть карту">×</button></header>
      <nav class="sky-atlas__controls" aria-label="Масштаб карты"><button type="button" data-scale="in" aria-label="Увеличить карту">+</button><button type="button" data-scale="out" aria-label="Уменьшить карту">−</button><button type="button" data-scale="all">Всё небо</button></nav>
      <aside class="sky-atlas__panel"><p class="sky-atlas__truth">Найдём положение галактики на карте и откроем её архивный снимок Hubble.</p><div class="sky-atlas__targets">${ids.map(id => `<button type="button" data-target="${id}">${TARGETS[id].name}<small>RA ${formatRa(TARGETS[id].ra)} · Dec ${formatDec(TARGETS[id].dec)}</small></button>`).join('')}</div><p class="sky-atlas__hint" aria-live="polite">Выбери объект в списке или найди его на карте.</p><button type="button" class="sky-atlas__open" disabled>Открыть архивный снимок</button><details class="sky-atlas__sources"><summary>Источники карты</summary><a href="sky-provenance.json" target="_blank" rel="noopener">NASA SVS и каталог HYG</a></details></aside>
      <footer class="sky-atlas__foot">NASA SVS Deep Star Maps 2020 · звёзды HYG v4.1 (CC BY-SA 4.0) · ICRS/J2000</footer>`;
    document.body.append(host);
    const canvas = host.querySelector('canvas'), ctx = canvas.getContext('2d');
    const hint = host.querySelector('.sky-atlas__hint'), openButton = host.querySelector('.sky-atlas__open');
    const targetButtons = [...host.querySelectorAll('[data-target]')];
    const texture = new Image();
    const returnFocus = document.activeElement;
    let width = 1, height = 1, dpr = 1, camera = {ra: 220, dec: 18, zoom: 2.6}, active = null, aligned = false;
    let drag = null, last = 0, raf = 0, closed = false;

    function formatRa(ra) { const h = ra / 15; const hh = Math.floor(h); const mm = Math.round((h - hh) * 60); return `${String(hh).padStart(2, '0')}ʰ ${String(mm).padStart(2, '0')}ᵐ`; }
    function formatDec(dec) { return `${dec < 0 ? '−' : '+'}${Math.abs(dec).toFixed(1)}°`; }
    function aim() { if (width >= 701 && height <= 500) return [width * .72, height * .55]; return width < 700 ? [width * .55, height * .4] : [width / 2, height / 2]; }
    // NASA's plate carrée texture maps increasing RA to the left. Keep the
    // catalog points in the exact same frame: x = ((180 - RA) mod 360).
    function project(ra, dec) { const [ax, ay] = aim(); return [ax - delta(ra - camera.ra) * camera.zoom, ay - (dec - camera.dec) * camera.zoom]; }
    function targetPixel() { return active ? project(TARGETS[active].ra, TARGETS[active].dec) : null; }
    function separation(target) { const d = (target.dec - camera.dec) * Math.PI / 180, a = delta(target.ra - camera.ra) * Math.PI / 180; return 2 * Math.asin(Math.sqrt(clamp(Math.sin(d / 2) ** 2 + Math.cos(target.dec * Math.PI / 180) * Math.cos(camera.dec * Math.PI / 180) * Math.sin(a / 2) ** 2, 0, 1))) * 180 / Math.PI; }
    function updateAlignment() { if (!active) { aligned = false; openButton.disabled = true; return; } const p = targetPixel(), target = TARGETS[active]; aligned = Math.hypot(p[0] - aim()[0], p[1] - aim()[1]) <= 22 && separation(target) <= 1.2; openButton.disabled = !aligned; hint.textContent = aligned ? `Галактика ${target.name} в прицеле. Открой её архивный снимок Hubble.` : `Перетащи карту, чтобы ${target.name} попала в прицел. Или нажми на неё.`; }
    function resize() { const r = canvas.getBoundingClientRect(); width = Math.max(1, r.width); height = Math.max(1, r.height); dpr = Math.min(2, devicePixelRatio || 1); canvas.width = width * dpr; canvas.height = height * dpr; updateAlignment(); draw(); }
    function request() { if (!raf) raf = requestAnimationFrame(() => { raf = 0; draw(); }); }
    function draw() {
      if (closed) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const g = ctx.createRadialGradient(width * .52, height * .45, 0, width * .52, height * .45, Math.max(width, height) * .76);
      g.addColorStop(0, '#112744'); g.addColorStop(.55, '#061323'); g.addColorStop(1, '#020712'); ctx.fillStyle = g; ctx.fillRect(0, 0, width, height);
      if (texture.complete && texture.naturalWidth) {
        const [ax, ay] = aim(), world = 360 * camera.zoom, worldX = wrap(180 - camera.ra), x = ax - worldX * camera.zoom, y = ay - (90 - camera.dec) * camera.zoom;
        ctx.globalAlpha = .44;
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
      for (const id of ids) drawTarget(id);
      const [ax, ay] = aim(); ctx.strokeStyle = aligned ? '#b9ecd9' : 'rgba(230,244,255,.88)'; ctx.lineWidth = 1.3; ctx.beginPath(); ctx.arc(ax, ay, 25, 0, Math.PI * 2); ctx.stroke(); ctx.beginPath(); ctx.moveTo(ax - 42, ay); ctx.lineTo(ax - 16, ay); ctx.moveTo(ax + 16, ay); ctx.lineTo(ax + 42, ay); ctx.moveTo(ax, ay - 42); ctx.lineTo(ax, ay - 16); ctx.moveTo(ax, ay + 16); ctx.lineTo(ax, ay + 42); ctx.stroke();
      ctx.font = '600 12px system-ui, sans-serif'; ctx.textAlign = 'center'; ctx.fillStyle = 'rgba(229,241,255,.72)';
      ctx.fillText(`RA ${formatRa(wrap(camera.ra))} · Dec ${formatDec(camera.dec)}`, width / 2, height - 22);
    }
    function drawTarget(id) {
      const target = TARGETS[id], [x, y] = project(target.ra, target.dec); if (x < -80 || x > width + 80 || y < -80 || y > height + 80) return;
      const selected = active === id, pulse = reduce() ? 1 : 1 + Math.sin(performance.now() / 450) * .12;
      ctx.strokeStyle = selected ? '#a9ffe0' : '#ffd88c'; ctx.lineWidth = selected ? 2.5 : 1.5; ctx.globalAlpha = .95;
      ctx.beginPath(); ctx.arc(x, y, 14 * pulse, 0, Math.PI * 2); ctx.stroke(); ctx.beginPath(); ctx.moveTo(x - 23, y); ctx.lineTo(x - 10, y); ctx.moveTo(x + 10, y); ctx.lineTo(x + 23, y); ctx.moveTo(x, y - 23); ctx.lineTo(x, y - 10); ctx.moveTo(x, y + 10); ctx.lineTo(x, y + 23); ctx.stroke();
      ctx.font = '700 13px system-ui, sans-serif'; const tw = ctx.measureText(target.name).width;
      if (x - tw / 2 - 8 >= 4 && x + tw / 2 + 8 <= width - 4 && y - 46 >= 74 && y - 20 <= height - 4) { ctx.fillStyle = 'rgba(1,8,18,.82)'; ctx.fillRect(x - tw / 2 - 8, y - 43, tw + 16, 22); ctx.fillStyle = selected ? '#bfffe7' : '#ffe0a1'; ctx.textAlign = 'center'; ctx.fillText(target.name, x, y - 28); }
    }
    function select(id, move) {
      active = id; const t = TARGETS[id]; openButton.disabled = true;
      targetButtons.forEach(b => b.classList.toggle('active', b.dataset.target === id));
      hint.textContent = `Цель: ${t.name}. Перетащи карту, чтобы галактика попала в прицел.`;
      if (move) focus(id); updateAlignment(); request();
    }
    function focus(id) {
      const t = TARGETS[id], start = {...camera}, zoom = Math.max(7.5, Math.min(width / 28, height / 18)), end = {ra: wrap(t.ra - width * .15 / zoom), dec: clamp(t.dec + height * .1 / zoom, -85, 85), zoom};
      if (reduce()) { camera = end; updateAlignment(); request(); return; }
      const begun = performance.now(); const tick = now => { const p = clamp((now - begun) / 600, 0, 1), e = p * p * (3 - 2 * p); camera = {ra: wrap(start.ra + delta(end.ra - start.ra) * e), dec: start.dec + (end.dec - start.dec) * e, zoom: start.zoom + (end.zoom - start.zoom) * e}; updateAlignment(); request(); if (p < 1 && !closed) requestAnimationFrame(tick); }; requestAnimationFrame(tick);
    }
    function pick(x, y) { for (const id of ids) { const p = project(TARGETS[id].ra, TARGETS[id].dec); if (Math.hypot(p[0] - x, p[1] - y) < 35) { active = id; targetButtons.forEach(b => b.classList.toggle('active', b.dataset.target === id)); camera.ra = TARGETS[id].ra; camera.dec = TARGETS[id].dec; updateAlignment(); request(); return true; } } return false; }
    function point(e) { const r = canvas.getBoundingClientRect(); return {x: e.clientX - r.left, y: e.clientY - r.top}; }
    function close() { if (closed) return; closed = true; cancelAnimationFrame(raf); observer.disconnect(); host.remove(); if (returnFocus?.focus) returnFocus.focus({preventScroll: true}); options.onClose?.(); }
    const observer = new ResizeObserver(resize); observer.observe(canvas);
    texture.onload = request; texture.src = data.texture;
    canvas.addEventListener('pointerdown', e => { const p = point(e); drag = {x: p.x, y: p.y, moved: false, pointer: e.pointerId}; canvas.setPointerCapture(e.pointerId); canvas.focus({preventScroll: true}); });
    canvas.addEventListener('pointermove', e => { const p = point(e); if (!drag || drag.pointer !== e.pointerId) return; const dx = p.x - drag.x, dy = p.y - drag.y; if (Math.hypot(dx, dy) > 5) drag.moved = true; camera.ra = wrap(camera.ra + dx / camera.zoom); camera.dec = clamp(camera.dec + dy / camera.zoom, -85, 85); drag.x = p.x; drag.y = p.y; updateAlignment(); request(); });
    function releasePointer(e) { if (!drag || drag.pointer !== e.pointerId) return; const p = point(e), was = drag; drag = null; if (canvas.hasPointerCapture(e.pointerId)) canvas.releasePointerCapture(e.pointerId); if (e.type === 'pointerup' && !was.moved) pick(p.x, p.y); }
    canvas.addEventListener('pointerup', releasePointer); canvas.addEventListener('pointercancel', releasePointer); canvas.addEventListener('lostpointercapture', releasePointer);
    canvas.addEventListener('wheel', e => { e.preventDefault(); camera.zoom = clamp(camera.zoom * Math.exp(-e.deltaY * .0015), .7, 80); updateAlignment(); request(); }, {passive: false});
    canvas.addEventListener('keydown', e => { const step = (e.shiftKey ? 80 : 28) / camera.zoom; if (e.key === 'ArrowLeft') camera.ra = wrap(camera.ra - step); else if (e.key === 'ArrowRight') camera.ra = wrap(camera.ra + step); else if (e.key === 'ArrowUp') camera.dec = clamp(camera.dec + step, -85, 85); else if (e.key === 'ArrowDown') camera.dec = clamp(camera.dec - step, -85, 85); else if (e.key === '+' || e.key === '=') camera.zoom = clamp(camera.zoom * 1.25, .7, 80); else if (e.key === '-' || e.key === '_') camera.zoom = clamp(camera.zoom / 1.25, .7, 80); else if (e.key === 'Escape') { close(); return; } else return; e.preventDefault(); updateAlignment(); request(); });
    host.querySelector('.sky-atlas__close').addEventListener('click', close);
    host.querySelectorAll('[data-scale]').forEach(button => button.addEventListener('click', () => { const action = button.dataset.scale; if (action === 'all') camera = {ra: 180, dec: 0, zoom: Math.max(.7, Math.min(width / 360, height / 180))}; else camera.zoom = clamp(camera.zoom * (action === 'in' ? 1.3 : 1 / 1.3), .7, 80); updateAlignment(); request(); canvas.focus({preventScroll: true}); }));
    targetButtons.forEach(button => button.addEventListener('click', () => select(button.dataset.target, true)));
    openButton.addEventListener('click', () => { if (!aligned || !active) return; const id = active; close(); options.onSelect?.(id); });
    host.addEventListener('keydown', e => { if (e.key === 'Escape') close(); if (e.key === 'Tab') { const focusable = [...host.querySelectorAll('button,[tabindex]:not([tabindex="-1"])')].filter(el => !el.disabled); const index = focusable.indexOf(document.activeElement); if (e.shiftKey && index <= 0) { e.preventDefault(); focusable.at(-1).focus(); } else if (!e.shiftKey && index === focusable.length - 1) { e.preventDefault(); focusable[0].focus(); } } });
    resize();
    const initial = TARGETS[options.initialTarget] ? options.initialTarget : ids[0]; select(initial, true); canvas.focus({preventScroll: true});
    last = performance.now();
    (function alive(now) { if (closed) return; if (!reduce() && now - last > 30) { last = now; request(); } requestAnimationFrame(alive); })(last);
    return {close, focusTarget: id => TARGETS[id] && select(id, true), state: () => ({active, aligned, camera: {...camera}, targets: ids.slice()}), snapshot: () => ({active, aligned, targetPixel: targetPixel() && {x: targetPixel()[0], y: targetPixel()[1]}, aim: {x: aim()[0], y: aim()[1]}, camera: {...camera}, source: data.source})};
  }
  globalThis.GalaxySky = {open};
})();
