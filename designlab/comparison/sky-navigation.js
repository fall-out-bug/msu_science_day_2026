/* Offline celestial navigation. Load sky-navigation-data.js first.
   Positions are ICRF/J2000 decimal degrees. Texture projection is the existing
   NASA plate carrée atlas: north up; RA increases left. No simulated stars.
   ObservatorySky({canvas,onAim}).show({id,ra,dec,title}); see sky-provenance.json. */
(function () {
  'use strict';
  const DEG = Math.PI / 180;
  const clamp = (n, a, b) => Math.max(a, Math.min(b, n));
  const wrap = n => ((n % 360) + 360) % 360;
  const delta = n => wrap(n + 180) - 180;

  function ObservatorySky(options) {
    if (!(this instanceof ObservatorySky)) return new ObservatorySky(options);
    options = options || {};
    const canvas = options.canvas;
    if (!canvas || typeof canvas.getContext !== 'function') throw new TypeError('ObservatorySky needs a canvas');
    const data = window.OBSERVATORY_SKY_DATA;
    if (!data || !data.texture || !Array.isArray(data.stars)) throw new Error('Load sky-navigation-data.js first');
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('A 2D canvas is required');
    const previous = {
      hidden: canvas.hidden,
      cursor: canvas.style.cursor,
      touchAction: canvas.style.touchAction,
      tab: canvas.getAttribute('tabindex'),
      role: canvas.getAttribute('role'),
      label: canvas.getAttribute('aria-label')
    };
    const listeners = [], pointers = new Map();
    let active = false, destroyed = false, target = null, aligned = false, pendingStart = false;
    let width = 0, height = 0, dpr = 1, zoom = 8, cameraX = 180, cameraY = 90, frame = 0;
    let textureReady = false, paused = false, showLines = true, pattern = null, press = null, revealAt = 0;
    let labels = [];
    const constellations = window.NIGHT_CONSTELLATIONS || [], objects = window.NIGHT_STORIES?.sky || [];
    const reduced = matchMedia('(prefers-reduced-motion: reduce)');
    const texture = new Image();
    canvas.style.touchAction = 'none';
    canvas.style.cursor = 'grab';
    canvas.setAttribute('tabindex', '0');
    canvas.setAttribute('role', 'group');

    function on(element, type, listener, config) {
      element.addEventListener(type, listener, config);
      listeners.push(() => element.removeEventListener(type, listener, config));
    }
    function limits() {
      return {min: Math.max(width / 260, height / 160, 1), max: Math.max(80, width / 4)};
    }
    function project(ra, dec) {
      return [width / 2 + delta(wrap(180 - ra) - cameraX) * zoom,
        height / 2 + (90 - dec - cameraY) * zoom];
    }
    function separation() {
      const aimDec = 90 - cameraY;
      const d = (target.dec - aimDec) * DEG;
      const a = delta(target.ra - wrap(180 - cameraX)) * DEG;
      const hav = Math.sin(d / 2) ** 2 + Math.cos(target.dec * DEG) * Math.cos(aimDec * DEG) * Math.sin(a / 2) ** 2;
      return 2 * Math.asin(Math.sqrt(clamp(hav, 0, 1))) / DEG;
    }
    function updateAim() {
      let next = false;
      if (active && target && !pendingStart && width && height) {
        const p = project(target.ra, target.dec);
        next = Math.hypot(p[0] - width / 2, p[1] - height / 2) <= 22 && separation() <= 1.2;
      }
      if (next !== aligned) {
        aligned = next;
        if (typeof options.onAim === 'function') options.onAim(next);
      }
    }
    function requestDraw() {
      if (!frame && active && !destroyed && !paused && !document.hidden) {
        frame = requestAnimationFrame(() => {
          frame = 0;
          const box = canvas.getBoundingClientRect();
          if (box.width !== width || box.height !== height || (pendingStart && box.width && box.height)) resize();
          draw();
        });
      }
    }
    function changed() {
      cameraX = wrap(cameraX);
      cameraY = clamp(cameraY, 0, 180);
      updateAim();
      requestDraw();
    }
    function resize() {
      if (destroyed || !active) return;
      const box = canvas.getBoundingClientRect();
      width = box.width;
      height = box.height;
      // Integration may reveal the parent immediately after show(). Wait for a
      // measurable viewport before setting the initial off-axis camera.
      if (pendingStart && width && height) {
        zoom = Math.max(width / 85, height / 65, 2);
        cameraX = wrap(180 - target.ra) - width * .17 / zoom;
        cameraY = 90 - target.dec + height * .1 / zoom;
        pendingStart = false;
      }
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.max(1, Math.round(width * dpr));
      canvas.height = Math.max(1, Math.round(height * dpr));
      const bounds = limits();
      zoom = clamp(zoom, bounds.min, bounds.max);
      changed();
    }
    function zoomAt(x, y, factor) {
      const bounds = limits(), old = zoom;
      zoom = clamp(zoom * factor, bounds.min, bounds.max);
      cameraX += (x - width / 2) * (1 / old - 1 / zoom);
      cameraY += (y - height / 2) * (1 / old - 1 / zoom);
      changed();
    }
    function clearPointers() {
      for (const id of pointers.keys()) {
        if (canvas.hasPointerCapture(id)) canvas.releasePointerCapture(id);
      }
      pointers.clear();
      canvas.style.cursor = 'grab';
    }
    function draw() {
      if (!active || destroyed || !width || !height) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.globalAlpha = 1;
      ctx.fillStyle = '#030912';
      ctx.fillRect(0, 0, width, height);
      if (textureReady) {
        const worldWidth = 360 * zoom;
        const left = width / 2 - cameraX * zoom;
        const top = height / 2 - cameraY * zoom;
        for (let k = -1; k <= 1; k++) {
          const x = left + k * worldWidth;
          if (x <= width && x + worldWidth >= 0) ctx.drawImage(texture, x, top, worldWidth, worldWidth / 2);
        }
      }
      // Catalog positions remain visible while the large offline texture decodes.
      // Their visual sizes express magnitude; no extra random star field is added.
      ctx.fillStyle = '#dfebff';
      for (const star of data.stars) {
        const p = project(star[0], star[1]);
        if (p[0] < -4 || p[0] > width + 4 || p[1] < -4 || p[1] > height + 4) continue;
        const radius = clamp(1.9 - (star[2] + 1.4) * .23, .35, 1.9);
        ctx.globalAlpha = textureReady ? .36 : .85;
        ctx.beginPath(); ctx.arc(p[0], p[1], radius, 0, Math.PI * 2); ctx.fill();
      }
      ctx.globalAlpha = 1;
      drawExploration();
      if (target) drawTarget();
      drawReticle();
      // Visible attribution accompanies this adapted HYG dataset.
      ctx.font = '10px system-ui, sans-serif';
      ctx.textAlign = 'left';
      ctx.fillStyle = 'rgba(209,222,239,.65)';
      ctx.fillText('NASA SVS · HYG v4.1 / Astronexus · CC BY-SA 4.0', 12, height - 12);
    }
    function drawExploration() {
      labels = [];
      const progress = reduced.matches ? 1 : clamp((performance.now()-revealAt)/800,0,1);
      if(showLines) for(const c of constellations) {
        if(pattern?.name===c.name) continue;
        ctx.strokeStyle='rgba(137,194,225,.38)';ctx.lineWidth=1;ctx.globalAlpha=progress;
        for(const line of c.lines) for(let i=1;i<line.length;i++) {
          const a=project(...line[i-1]),b=project(...line[i]);
          if(Math.abs(a[0]-b[0])>180*zoom)continue;
          ctx.beginPath();ctx.moveTo(...a);ctx.lineTo(a[0]+(b[0]-a[0])*progress,a[1]+(b[1]-a[1])*progress);ctx.stroke();
        }
        const [x,y]=project(c.ra,c.dec);
        if(x<25||x>width-25||y<25||y>height-30)continue;
        ctx.font='12px system-ui';const w=ctx.measureText(c.name).width;
        if(labels.some(l=>Math.abs(l.x-x)<(l.w+w)/2+12&&Math.abs(l.y-y)<26))continue;
        ctx.fillStyle='#bdd9ed';ctx.textAlign='center';ctx.fillText(c.name,x,y);
        labels.push({x,y,w,item:{title:c.name,constellation:c.name,text:'Линии помогают запомнить рисунок звёзд. Это условная фигура на карте: сами звёзды могут находиться далеко друг от друга.'}});
      }
      ctx.globalAlpha=1;
      if(!pattern) for(const item of objects) {
        const [x,y]=project(item.ra,item.dec);if(x<0||x>width||y<0||y>height)continue;
        ctx.strokeStyle='#ffd494';ctx.lineWidth=1.5;ctx.beginPath();ctx.arc(x,y,10,0,Math.PI*2);ctx.stroke();
        ctx.font='600 12px system-ui';ctx.textAlign='left';ctx.fillStyle='#ffdda5';ctx.fillText(item.title,x+15,y-12);
      }
      if(pattern) {
        const pts=pattern.points.map(p=>project(...p));ctx.strokeStyle='#ffe0a1';ctx.lineWidth=3;
        ctx.beginPath();pts.slice(0,pattern.count).forEach((p,i)=>i?ctx.lineTo(...p):ctx.moveTo(...p));ctx.stroke();
        pts.forEach(([x,y],i)=>{ctx.beginPath();ctx.fillStyle=i<pattern.count?'#9ef3d1':'#182d42';ctx.strokeStyle=i===pattern.count?'#ffe4aa':'#90abc0';ctx.arc(x,y,15,0,Math.PI*2);ctx.fill();ctx.stroke();ctx.font='bold 13px system-ui';ctx.textAlign='center';ctx.fillStyle=i<pattern.count?'#0b2429':'#fff';ctx.fillText(String(i+1),x,y+5);});
      }
      if(progress<1)requestDraw();
    }
    function pickExploration(x,y) {
      if(pattern) {
        const p=pattern.points[pattern.count];
        if(p){const q=project(...p);if(Math.hypot(q[0]-x,q[1]-y)<26){pattern.count++;options.onPattern?.({name:pattern.name,count:pattern.count,total:pattern.points.length});requestDraw();}}
        return;
      }
      const item=objects.find(o=>{const p=project(o.ra,o.dec);return Math.hypot(p[0]-x,p[1]-y)<22;}) || labels.find(l=>Math.abs(l.x-x)<l.w/2+6&&Math.abs(l.y-y+5)<14)?.item;
      if(item) options.onExplore?.(item);
    }
    function focus(ra,dec,span=65) {
      pendingStart=false;cameraX=wrap(180-ra);cameraY=90-dec;zoom=clamp(Math.min(width/span,height/(span*.8)),limits().min,limits().max);revealAt=performance.now();changed();
    }
    this.focusConstellation=function(name){const c=constellations.find(c=>c.name===name);if(!c)return;pattern=null;options.onPattern?.(null);showLines=true;focus(c.ra,c.dec,70);};
    this.focusObject=function(id){const item=objects.find(o=>o.id===id);if(item){pattern=null;options.onPattern?.(null);focus(item.ra,item.dec,45);}};
    this.startPattern=function(){const c=constellations.find(c=>c.name==='Кассиопея');if(!c)return;pattern={name:c.name,points:c.lines[0],count:0};focus(c.ra,c.dec,60);options.onPattern?.({name:c.name,count:0,total:pattern.points.length});};
    this.connectPatternPoint=function(index){if(!pattern||index!==pattern.count)return;pickExploration(...project(...pattern.points[index]));};
    this.setConstellations=function(value){showLines=value;revealAt=performance.now();requestDraw();};
    this.pause=function(){paused=true;clearPointers();if(frame)cancelAnimationFrame(frame);frame=0;};
    this.resume=function(){paused=false;requestDraw();};
    function drawTarget() {
      const p = project(target.ra, target.dec);
      if (p[0] < -30 || p[0] > width + 30 || p[1] < -30 || p[1] > height + 30) return;
      ctx.strokeStyle = aligned ? '#b9ecd9' : '#f5d58d';
      ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.arc(p[0], p[1], 14, 0, Math.PI * 2); ctx.stroke();
      ctx.beginPath(); ctx.arc(p[0], p[1], 3, 0, Math.PI * 2); ctx.stroke();
      const label = target.title;
      if (!label) return;
      ctx.font = '600 14px system-ui, sans-serif';
      const maxLabelWidth = Math.max(30, width - 24);
      const labelWidth = Math.min(ctx.measureText(label).width, maxLabelWidth);
      const x = clamp(p[0], labelWidth / 2 + 12, width - labelWidth / 2 - 12);
      const y = clamp(p[1] - 27, 24, height - 40);
      ctx.textAlign = 'center';
      ctx.fillStyle = 'rgba(3,9,18,.8)';
      ctx.fillRect(x - labelWidth / 2 - 6, y - 16, labelWidth + 12, 23);
      ctx.fillStyle = aligned ? '#b9ecd9' : '#f5d58d';
      ctx.fillText(label, x, y, maxLabelWidth);
    }
    function drawReticle() {
      const x = width / 2, y = height / 2;
      ctx.strokeStyle = aligned ? '#b9ecd9' : 'rgba(225,239,255,.8)';
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.arc(x, y, 26, 0, Math.PI * 2); ctx.stroke();
      ctx.beginPath();
      for (const axis of [[-42, 0, -17, 0], [17, 0, 42, 0], [0, -42, 0, -17], [0, 17, 0, 42]]) {
        ctx.moveTo(x + axis[0], y + axis[1]); ctx.lineTo(x + axis[2], y + axis[3]);
      }
      ctx.stroke();
    }

    on(canvas, 'pointerdown', e => {
      if (!active || paused || e.button !== 0) return;
      press={x:e.clientX,y:e.clientY,id:e.pointerId,moved:false};
      e.preventDefault();
      resize();
      canvas.focus({preventScroll: true});
      canvas.setPointerCapture(e.pointerId);
      pointers.set(e.pointerId, [e.clientX, e.clientY]);
      canvas.style.cursor = 'grabbing';
    });
    on(canvas, 'pointermove', e => {
      if (!active || paused || !pointers.has(e.pointerId)) return;
      if(press&&(pointers.size>1||Math.hypot(e.clientX-press.x,e.clientY-press.y)>8))press.moved=true;
      const old = pointers.get(e.pointerId);
      const before = Array.from(pointers.values());
      pointers.set(e.pointerId, [e.clientX, e.clientY]);
      if (pointers.size === 2) {
        const after = Array.from(pointers.values());
        const cx = (after[0][0] + after[1][0]) / 2, cy = (after[0][1] + after[1][1]) / 2;
        cameraX -= (cx - (before[0][0] + before[1][0]) / 2) / zoom;
        cameraY -= (cy - (before[0][1] + before[1][1]) / 2) / zoom;
        const from = Math.hypot(before[0][0] - before[1][0], before[0][1] - before[1][1]);
        const to = Math.hypot(after[0][0] - after[1][0], after[0][1] - after[1][1]);
        const box = canvas.getBoundingClientRect();
        zoomAt(cx - box.left, cy - box.top, from > 1 ? to / from : 1);
      } else {
        cameraX -= (e.clientX - old[0]) / zoom;
        cameraY -= (e.clientY - old[1]) / zoom;
        changed();
      }
    });
    function release(e) {
      const click=e.type==='pointerup'&&active&&!paused&&press?.id===e.pointerId&&!press.moved;press=null;
      pointers.delete(e.pointerId);
      if (canvas.hasPointerCapture(e.pointerId)) canvas.releasePointerCapture(e.pointerId);
      if (!pointers.size) canvas.style.cursor = 'grab';
      if(click){const r=canvas.getBoundingClientRect();pickExploration(e.clientX-r.left,e.clientY-r.top);}
    }
    on(canvas, 'pointerup', release);
    on(canvas, 'pointercancel', release);
    on(canvas, 'lostpointercapture', release);
    on(canvas, 'wheel', e => {
      if (!active || paused) return;
      e.preventDefault();
      resize();
      const box = canvas.getBoundingClientRect();
      const dy = e.deltaY * (e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? height : 1);
      zoomAt(e.clientX - box.left, e.clientY - box.top, Math.exp(-clamp(dy, -500, 500) * .0015));
    }, {passive: false});
    on(canvas, 'keydown', e => {
      if (!active || paused || e.altKey || e.ctrlKey || e.metaKey) return;
      resize();
      const step = (e.shiftKey ? 100 : 28) / zoom;
      switch (e.key) {
        case 'ArrowLeft': cameraX += step; break;
        case 'ArrowRight': cameraX -= step; break;
        case 'ArrowUp': cameraY += step; break;
        case 'ArrowDown': cameraY -= step; break;
        case '+': case '=': zoomAt(width / 2, height / 2, 1.3); break;
        case '-': case '_': zoomAt(width / 2, height / 2, 1 / 1.3); break;
        case 'Home': this.focusTarget(); break;
        default: return;
      }
      e.preventDefault(); changed();
    });
    on(document, 'visibilitychange', () => {
      if (document.hidden && frame) { cancelAnimationFrame(frame); frame = 0; }
      else requestDraw();
    });
    on(window, 'resize', resize);
    const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(resize) : null;
    if (observer) observer.observe(canvas);
    texture.onload = () => { textureReady = true; requestDraw(); };
    texture.src = data.texture;

    this.show = function (value) {
      if (destroyed) return;
      if (!value || !Number.isFinite(value.ra) || !Number.isFinite(value.dec) || value.dec < -90 || value.dec > 90) {
        throw new TypeError('show needs real RA/Dec in decimal degrees; Dec must be within [-90,90]');
      }
      pattern=null;options.onPattern?.(null);revealAt=performance.now();
      target = {id: value.id, ra: wrap(value.ra), dec: value.dec, title: String(value.title || '')};
      clearPointers();
      active = true;
      canvas.hidden = false;
      canvas.setAttribute('aria-label', 'Карта неба. Цель: ' + target.title + '. Тяните небо к прицелу. Стрелки — обзор; плюс и минус — масштаб; Home — навести на цель.');
      // Start nearby but visibly off the telescope axis, on every new visit.
      pendingStart = true;
      resize();
    };
    this.hide = function () {
      if (destroyed) return;
      active = false;
      clearPointers();
      if (frame) cancelAnimationFrame(frame);
      frame = 0;
      canvas.hidden = true;
      updateAim();
    };
    this.focusTarget = function () {
      if (destroyed || !active || !target) return;
      pattern=null;options.onPattern?.(null);
      resize();
      pendingStart = false;
      cameraX = wrap(180 - target.ra);
      cameraY = 90 - target.dec;
      changed();
    };
    this.isAligned = function () { return !destroyed && active && aligned; };
    this.destroy = function () {
      if (destroyed) return;
      this.hide();
      destroyed = true;
      listeners.forEach(remove => remove());
      if (observer) observer.disconnect();
      texture.onload = null;
      canvas.hidden = previous.hidden;
      canvas.style.cursor = previous.cursor;
      canvas.style.touchAction = previous.touchAction;
      for (const [attr, value] of [['tabindex', previous.tab], ['role', previous.role], ['aria-label', previous.label]]) {
        if (value === null) canvas.removeAttribute(attr); else canvas.setAttribute(attr, value);
      }
    };
  }
  window.ObservatorySky = ObservatorySky;
})();
