/* sky-map.js — карта НЕБА на реальной каталожной текстуре NASA SVS 4851
   («Deep Star Maps 2020», Hipparcos+Tycho-2, каталожная визуализация, не фото).
   Офлайн: текстура и каталоги — data URI/JSON в app/sky-data.js (window.SKY_DATA).
   Проекция текстуры: plate carrée ICRF/J2000, RA 0h в центре, RA растёт влево:
   x = ((180° − RA) mod 360°)/360° · W, y = (90° − δ)/180° · H — как в NASA.

   Автономный классический скрипт: window.SkyMap(container, options).
   Интерфейс: constructor(container,{cases,selected,statuses,onSelect[,motion]}),
   update({selected,statuses}), flyTo(id) -> Promise, destroy().
   Кнопки: data-map-action in|out|home|skip|anim; узлы: data-sector = id дела.
   Настройка анимации — только явная (кнопка/опция/localStorage «skymap.animation»);
   prefers-reduced-motion НЕ влияет на перелёты (решение пользователя первично). */
(function () {
  "use strict";

  var TAU = Math.PI * 2;
  var WORLD_W = 360; // градусы прямой проекции
  var WORLD_H = 180;
  var DEG = Math.PI / 180;

  var STATUS_INFO = {
    new: { short: "НОВЫЙ", mark: "", long: "участок ещё не изучен" },
    noticed: {
      short: "ВПЕЧАТЛЕНИЕ",
      mark: "•",
      long: "есть первое впечатление",
    },
    checked: { short: "КАДР 3", mark: "3", long: "получен третий снимок" },
    decided: { short: "РЕШЁН", mark: "✓", long: "версия записана" },
  };

  var LS_KEY = "skymap.animation";

  /* ---------- утилиты ---------- */

  function clamp(v, a, b) {
    return v < a ? a : v > b ? b : v;
  }
  function lerp(a, b, t) {
    return a + (b - a) * t;
  }
  function easeInOut(t) {
    return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  }
  function easeOut(t) {
    return 1 - Math.pow(1 - t, 3);
  }
  function wrapDelta(dx) {
    return (((dx % 360) + 540) % 360) - 180;
  }
  function norm360(x) {
    return ((x % 360) + 360) % 360;
  }
  /* RA,Dec -> вектор */
  function toVec(ra, dec) {
    var a = ra * DEG, d = dec * DEG, cd = Math.cos(d);
    return [cd * Math.cos(a), cd * Math.sin(a), Math.sin(d)];
  }
  /* вектор -> [RA, Dec] в градусах */
  function toRaDec(v) {
    var hyp = Math.hypot(v[0], v[1]);
    return [norm360(Math.atan2(v[1], v[0]) / DEG), Math.asin(clamp(v[2], -1, 1)) / DEG];
  }
  function slerpVec(v0, v1, t) {
    var dot = clamp(v0[0] * v1[0] + v0[1] * v1[1] + v0[2] * v1[2], -1, 1);
    var om = Math.acos(dot);
    if (om < 1e-6) return v0.slice();
    var so = Math.sin(om);
    var k0 = Math.sin((1 - t) * om) / so, k1 = Math.sin(t * om) / so;
    return [
      v0[0] * k0 + v1[0] * k1,
      v0[1] * k0 + v1[1] * k1,
      v0[2] * k0 + v1[2] * k1,
    ];
  }
  function angBetween(v0, v1) {
    return Math.acos(clamp(v0[0] * v1[0] + v0[1] * v1[1] + v0[2] * v1[2], -1, 1));
  }
  /* RA в «05ч35м», Dec в «−05°23′» */
  function fmtRA(raDeg) {
    var h = raDeg / 15;
    var hh = Math.floor(h);
    var mm = Math.round((h - hh) * 60);
    if (mm === 60) { hh = (hh + 1) % 24; mm = 0; }
    return (hh < 10 ? "0" : "") + hh + "ч" + (mm < 10 ? "0" : "") + mm + "м";
  }
  function fmtDec(dec) {
    var sign = dec < 0 ? "−" : "+";
    var a = Math.abs(dec);
    var dd = Math.floor(a);
    var mm = Math.round((a - dd) * 60);
    if (mm === 60) { dd += 1; mm = 0; }
    return sign + (dd < 10 ? "0" : "") + dd + "°" + (mm < 10 ? "0" : "") + mm + "′";
  }

  /* ---------- модуль ---------- */

  function SkyMap(container, options) {
    if (!container || container.nodeType !== 1) {
      throw new TypeError("SkyMap: нужен DOM-элемент контейнера");
    }
    options = options || {};
    var cases = Array.isArray(options.cases) ? options.cases.slice() : [];

    this._destroyed = false;
    this._onSelect =
      typeof options.onSelect === "function" ? options.onSelect : null;
    this._selectedId =
      options.selected != null && typeof options.selected === "string"
        ? options.selected
        : null;
    this._cases = cases;

    var sky = window.SKY_DATA || null;
    this._sky = sky;
    if (!sky || !sky.texture) {
      console.error(
        "SkyMap: window.SKY_DATA не найден — подключите app/sky-data.js до sky-map.js",
      );
    }

    /* настройка анимации: опция > сохранённый выбор > «animated».
       prefers-reduced-motion намеренно не читается. */
    var saved = null;
    try {
      saved = localStorage.getItem(LS_KEY);
    } catch (e) { /* приватный режим */ }
    this._motion =
      options.motion === "instant" || options.motion === "animated"
        ? options.motion
        : saved === "instant" || saved === "animated"
          ? saved
          : "animated";

    this._view = { w: 0, h: 0, dpr: 1 };
    this._cam = { x: WORLD_W / 2, y: WORLD_H / 2, z: 0.5 };
    this._zoom = { fit: 0.5, min: 0.2, max: 30 };
    this._fitted = false;
    this._anim = null; // {kind:'fly'|'move', ...}
    this._tex = null; // HTMLImageElement
    this._texReady = false;
    this._raf = 0;
    this._running = true;
    this._dirty = true;
    this._camSig = "";

    this._buildDom(container);
    this._loadTexture();
    this._buildNodes();
    this._applyStatuses(options.statuses || {});
    this._refreshSelected();
    this._syncControls();

    var self = this;
    this._onVis = function () {
      if (document.hidden) {
        self._running = false;
        if (self._raf) {
          cancelAnimationFrame(self._raf);
          self._raf = 0;
        }
        if (self._anim && self._anim.kind === "fly") self._skipFlight();
      } else if (!self._destroyed) {
        self._running = true;
        self._dirty = true;
        self._kick();
      }
    };
    this._onDocKey = function (e) {
      if (!self._anim || self._anim.kind !== "fly") return;
      if (e.key === "Escape" || e.key === " " || e.code === "Space") {
        e.preventDefault();
        e.stopPropagation();
        self._skipFlight();
      }
    };
    document.addEventListener("visibilitychange", this._onVis);

    this._ro = new ResizeObserver(function () {
      self._resize();
    });
    this._ro.observe(this._viewport);

    this._kick();
  }

  /* ---------- DOM ---------- */

  SkyMap.prototype._el = function (tag, cls, parent, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    if (parent) parent.appendChild(e);
    return e;
  };

  SkyMap.prototype._buildDom = function (container) {
    var root = this._el("div", "sky-map");
    root.innerHTML =
      '<div class="sky-viewport" tabindex="0" role="group" aria-label="Карта неба. ' +
      "Стрелки — обзор, клавиши плюс и минус — масштаб, пробел во время перелёта — прибыть сразу.\">" +
      '<canvas class="sky-canvas" aria-hidden="true"></canvas>' +
      '<div class="sky-nodes"></div>' +
      '<div class="sky-head" aria-hidden="true"><span class="sky-title">КАРТА НЕБА</span>' +
      '<span class="sky-subnote">NASA SVS · звёздные каталоги · не фотография</span></div>' +
      '<div class="sky-readout" aria-hidden="true"><span class="sky-readout-a"></span><span class="sky-readout-b"></span></div>' +
      '<div class="sky-hint" aria-hidden="true">Тяните небо · колесо — масштаб · стрелки — обзор</div>' +
      '<div class="sky-hud" hidden>' +
      '<span class="sky-hud-kicker">ПЕРЕЛЁТ</span>' +
      '<span class="sky-hud-route"><b class="sky-hud-from"></b><i aria-hidden="true">→</i><b class="sky-hud-to"></b></span>' +
      '<span class="sky-hud-bar" aria-hidden="true"><i></i></span>' +
      '<span class="sky-hud-note">Пробел или клик по карте — прибыть сразу</span>' +
      "</div>" +
      '<div class="sky-controls" role="group" aria-label="Управление картой">' +
      '<button type="button" class="sky-ctl" data-map-action="out" aria-label="Отдалить карту">−</button>' +
      '<input class="sky-zoom" type="range" min="0" max="1000" step="1" value="500" aria-label="Масштаб карты">' +
      '<button type="button" class="sky-ctl" data-map-action="in" aria-label="Приблизить карту">+</button>' +
      '<span class="sky-zoom-value" aria-hidden="true">×1.00</span>' +
      '<span class="sky-ctl-sep" aria-hidden="true"></span>' +
      '<button type="button" class="sky-ctl sky-ctl--home" data-map-action="home" aria-label="Показать всю карту">⌂</button>' +
      '<button type="button" class="sky-ctl sky-ctl--anim" data-map-action="anim" aria-pressed="true">' +
      '<span>Перелёты</span></button>' +
      '<button type="button" class="sky-ctl sky-ctl--skip" data-map-action="skip" aria-label="Пропустить перелёт" disabled><span>Пропустить</span></button>' +
      "</div>" +
      '<p class="sky-live" role="status" aria-live="polite"></p>' +
      "</div>";
    this._root = root;
    container.appendChild(root);
    this._viewport = root.querySelector(".sky-viewport");
    this._canvas = root.querySelector(".sky-canvas");
    this._ctx = this._canvas.getContext("2d");
    this._nodesHost = root.querySelector(".sky-nodes");
    this._readoutA = root.querySelector(".sky-readout-a");
    this._readoutB = root.querySelector(".sky-readout-b");
    this._hud = root.querySelector(".sky-hud");
    this._hudFrom = root.querySelector(".sky-hud-from");
    this._hudTo = root.querySelector(".sky-hud-to");
    this._hudBar = root.querySelector(".sky-hud-bar i");
    this._zoomRange = root.querySelector(".sky-zoom");
    this._zoomValue = root.querySelector(".sky-zoom-value");
    this._skipBtn = root.querySelector('[data-map-action="skip"]');
    this._animBtn = root.querySelector('[data-map-action="anim"]');
    this._btnIn = root.querySelector('[data-map-action="in"]');
    this._btnOut = root.querySelector('[data-map-action="out"]');
    this._live = root.querySelector(".sky-live");
    this._syncMotionUi();

    this._bindEvents();
  };

  SkyMap.prototype._loadTexture = function () {
    var self = this;
    if (!this._sky || !this._sky.texture) return;
    var img = new Image();
    this._tex = img;
    img.onload = function () {
      if (self._destroyed) return;
      self._texReady = true;
      self._dirty = true;
      self._kick();
    };
    img.onerror = function () {
      if (self._destroyed) return;
      console.error("SkyMap: текстура SKY_DATA не декодировалась");
    };
    img.src = this._sky.texture;
  };

  /* ---------- узлы-участки ---------- */

  SkyMap.prototype._worldOf = function (c) {
    /* A missing coordinate must never create a plausible but fictitious pin. */
    var ra = c.ra;
    var dec = c.dec;
    if (!Number.isFinite(ra) || !Number.isFinite(dec) ||
        ra < 0 || ra >= 360 || dec < -90 || dec > 90) {
      throw new RangeError("Нет действительных координат участка: " + c.id);
    }
    return {
      x: norm360(180 - ra),
      y: 90 - dec,
      ra: ra,
      dec: dec,
    };
  };

  SkyMap.prototype._buildNodes = function () {
    this._nodes = [];
    this._byId = new Map();
    var sky = this._sky;
    for (var i = 0; i < this._cases.length; i++) {
      this._nodes.push(this._buildNode(this._cases[i], i));
    }
    this._catalog = {
      stars: (sky && Array.isArray(sky.stars) && sky.stars.filter(function (s) {
        return s && isFinite(s.ra) && isFinite(s.dec) && s.name;
      })) || [],
      consts: (sky && Array.isArray(sky.constellations) && sky.constellations.filter(function (c) {
        return c && Array.isArray(c.lines) && c.lines.length;
      })) || [],
    };
  };

  SkyMap.prototype._buildNode = function (c, index) {
    var name = String((c && c.name) || "Участок");
    var frame = (c && Array.isArray(c.frames) && c.frames[0]) || "";
    var w = this._worldOf(c);
    var b = this._el("button", "sky-node sky-node--new", this._nodesHost);
    b.type = "button";
    b.dataset.sector = String(c && c.id);
    b.setAttribute("aria-pressed", "false");
    var thumb = this._el("span", "sky-node-thumb", b);
    var img = this._el("img", "sky-node-photo", thumb);
    img.alt = "";
    img.draggable = false;
    if (frame) img.src = frame;
    this._el("span", "sky-node-idx", thumb, String(index + 1).padStart(2, "0"));
    var mark = this._el("span", "sky-node-mark", thumb, "");
    mark.setAttribute("aria-hidden", "true");
    var meta = this._el("span", "sky-node-meta", b);
    this._el("span", "sky-node-name", meta, name);
    var state = this._el("span", "sky-node-state", meta, STATUS_INFO.new.short);
    var node = {
      id: String(c && c.id),
      case: c,
      name: name,
      x: w.x,
      y: w.y,
      ra: w.ra,
      dec: w.dec,
      el: b,
      state: state,
      mark: mark,
      status: "new",
      dx: 34,
      dy: 30,
      pin: { sx: 0, sy: 0, visible: false },
      box: { x: 0, y: 0, w: 0, h: 0 },
    };
    var self = this;
    b.addEventListener("click", function () {
      if (!self._destroyed && self._onSelect) self._onSelect(node.id);
    });
    this._byId.set(node.id, node);
    return node;
  };

  SkyMap.prototype._bindEvents = function () {
    var self = this;
    var vp = this._viewport;

    vp.addEventListener("pointerdown", function (e) {
      if (self._destroyed) return;
      if (e.target.closest(".sky-node, .sky-controls, button, input")) return;
      if (self._anim && self._anim.kind === "fly") {
        self._skipFlight();
        return;
      }
      /* клик по настоящей булавке */
      var rect = vp.getBoundingClientRect();
      var px = e.clientX - rect.left, py = e.clientY - rect.top;
      var hit = self._pinAt(px, py);
      if (hit && self._onSelect) {
        self._onSelect(hit.id);
        return;
      }
      self._takeControl();
      vp.setPointerCapture(e.pointerId);
      self._pointers = self._pointers || new Map();
      self._pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (self._pointers.size === 1) {
        self._pinDist = 0;
        vp.classList.add("sky-panning");
      }
    });
    vp.addEventListener("pointermove", function (e) {
      var pts = self._pointers;
      if (self._destroyed || !pts || !pts.has(e.pointerId)) return;
      var prev = pts.get(e.pointerId);
      pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pts.size >= 2) {
        var ids = Array.from(pts.keys());
        var a = pts.get(ids[0]),
          b = pts.get(ids[1]);
        var dist = Math.hypot(a.x - b.x, a.y - b.y);
        var mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
        var pa = self._pinchPrev;
        if (pa && pa.dist > 0) {
          self._takeControl();
          var rect = vp.getBoundingClientRect();
          self._zoomAt(mid.x - rect.left, mid.y - rect.top, dist / pa.dist);
          self._panBy(
            (mid.x - pa.mid.x) / self._cam.z,
            (mid.y - pa.mid.y) / self._cam.z,
          );
        }
        self._pinchPrev = { dist: dist, mid: mid };
      } else {
        var dx = e.clientX - prev.x,
          dy = e.clientY - prev.y;
        self._pinDist = (self._pinDist || 0) + Math.abs(dx) + Math.abs(dy);
        self._panBy(dx / self._cam.z, dy / self._cam.z);
      }
    });
    var release = function (e) {
      if (self._pointers) self._pointers.delete(e.pointerId);
      if (!self._pointers || self._pointers.size === 0) {
        self._pinchPrev = null;
        vp.classList.remove("sky-panning");
      }
      if (vp.hasPointerCapture && vp.hasPointerCapture(e.pointerId))
        vp.releasePointerCapture(e.pointerId);
    };
    vp.addEventListener("pointerup", release);
    vp.addEventListener("pointercancel", release);

    vp.addEventListener(
      "wheel",
      function (e) {
        if (self._destroyed) return;
        e.preventDefault();
        self._takeControl();
        var rect = vp.getBoundingClientRect();
        var delta = e.deltaY;
        if (e.deltaMode === 1) delta *= 16;
        else if (e.deltaMode === 2) delta *= rect.height;
        self._zoomAt(
          e.clientX - rect.left,
          e.clientY - rect.top,
          Math.exp(-delta * 0.0016),
        );
      },
      { passive: false },
    );

    vp.addEventListener("dblclick", function (e) {
      if (self._destroyed) return;
      if (e.target.closest(".sky-node, .sky-controls")) return;
      self._takeControl();
      self._animateTo(
        {
          x: self._cam.x,
          y: self._cam.y,
          z: clamp(self._cam.z * 1.6, self._zoom.min, self._zoom.max),
        },
        240,
      );
    });

    vp.addEventListener("keydown", function (e) {
      if (self._destroyed) return;
      if (e.altKey || e.ctrlKey || e.metaKey) return;
      if (e.target !== vp) return;
      var step = ((e.shiftKey ? 3 : 1) * 96) / self._cam.z;
      var handled = true;
      switch (e.key) {
        case "ArrowLeft":
          self._takeControl();
          self._panBy(-step, 0);
          break;
        case "ArrowRight":
          self._takeControl();
          self._panBy(step, 0);
          break;
        case "ArrowUp":
          self._takeControl();
          self._panBy(0, -step);
          break;
        case "ArrowDown":
          self._takeControl();
          self._panBy(0, step);
          break;
        case "+":
        case "=":
          self._takeControl();
          self._zoomStep(1.35);
          break;
        case "-":
        case "_":
          self._takeControl();
          self._zoomStep(1 / 1.35);
          break;
        case "0":
        case "Home":
          self._takeControl();
          self._goHome();
          break;
        default:
          handled = false;
      }
      if (handled) e.preventDefault();
    });

    this._zoomRange.addEventListener("input", function () {
      if (self._destroyed) return;
      self._takeControl();
      var zMin = self._zoom.min,
        zMax = self._zoom.max;
      var v = Number(self._zoomRange.value) / 1000;
      self._cam.z = clamp(zMin * Math.pow(zMax / zMin, v), zMin, zMax);
      self._clampCam();
      self._dirty = true;
      self._kick();
    });

    var actions = {
      out: function () {
        self._takeControl();
        self._zoomStep(1 / 1.35);
      },
      in: function () {
        self._takeControl();
        self._zoomStep(1.35);
      },
      home: function () {
        self._takeControl();
        self._goHome();
      },
      skip: function () {
        self._skipFlight();
      },
      anim: function () {
        self._setMotion(self._motion === "animated" ? "instant" : "animated");
        self._live.textContent =
          self._motion === "animated"
            ? "Перелёты плавные"
            : "Перелёты мгновенные";
      },
    };
    var ctlButtons = this._root.querySelectorAll("[data-map-action]");
    for (var i = 0; i < ctlButtons.length; i++) {
      (function (btn) {
        btn.addEventListener("click", function () {
          var fn = actions[btn.dataset.mapAction];
          if (fn && !self._destroyed) fn();
        });
      })(ctlButtons[i]);
    }
  };

  /* ---------- настройка анимации ---------- */

  SkyMap.prototype._setMotion = function (mode) {
    this._motion = mode === "instant" ? "instant" : "animated";
    try {
      localStorage.setItem(LS_KEY, this._motion);
    } catch (e) { /* приватный режим */ }
    this._syncMotionUi();
    this._dirty = true;
    this._kick();
  };

  SkyMap.prototype._syncMotionUi = function () {
    if (!this._root) return;
    var animated = this._motion === "animated";
    this._root.classList.toggle("sky-map--instant", !animated);
    if (this._animBtn) {
      this._animBtn.setAttribute("aria-pressed", animated ? "true" : "false");
      this._animBtn.setAttribute(
        "aria-label",
        animated
          ? "Перелёты плавные — переключить на мгновенные"
          : "Перелёты мгновенные — переключить на плавные",
      );
      var span = this._animBtn.querySelector("span");
      if (span) span.textContent = animated ? "Перелёты плавно" : "Перелёты сразу";
    }
  };

  /* ---------- статусы и выбор ---------- */

  SkyMap.prototype._applyStatuses = function (statuses) {
    for (var i = 0; i < this._nodes.length; i++) {
      var n = this._nodes[i];
      var v =
        statuses && Object.prototype.hasOwnProperty.call(statuses, n.id)
          ? statuses[n.id]
          : null;
      var st = STATUS_INFO[v] ? v : "new";
      n.status = st;
      n.el.classList.remove(
        "sky-node--new",
        "sky-node--noticed",
        "sky-node--checked",
        "sky-node--decided",
      );
      n.el.classList.add("sky-node--" + st);
      n.state.textContent = STATUS_INFO[st].short;
      n.mark.textContent = STATUS_INFO[st].mark;
      n.el.setAttribute(
        "aria-label",
        n.name + " — " + STATUS_INFO[st].long,
      );
    }
  };

  SkyMap.prototype._refreshSelected = function () {
    for (var i = 0; i < this._nodes.length; i++) {
      var n = this._nodes[i];
      var sel = n.id === this._selectedId;
      n.el.setAttribute("aria-pressed", sel ? "true" : "false");
      n.el.classList.toggle("sky-node--selected", sel);
    }
    var selNode =
      this._selectedId != null ? this._byId.get(this._selectedId) : null;
    this._readoutA.textContent =
      "УЧАСТКОВ: " +
      this._nodes.length +
      (selNode ? " · ЦЕЛЬ: " + selNode.name.toUpperCase() : "");
    this._camSig = "";
  };

  /* ---------- публичный интерфейс ---------- */

  SkyMap.prototype.update = function (opts) {
    if (this._destroyed) return;
    opts = opts || {};
    if (opts.statuses && typeof opts.statuses === "object")
      this._applyStatuses(opts.statuses);
    if (Object.prototype.hasOwnProperty.call(opts, "selected")) {
      this._selectedId = opts.selected != null ? String(opts.selected) : null;
      this._refreshSelected();
      if (this._selectedId && this._fitted)
        this._glideToView(this._byId.get(this._selectedId));
    }
    this._dirty = true;
    this._kick();
  };

  SkyMap.prototype.flyTo = function (id) {
    var self = this;
    if (this._destroyed) return Promise.resolve();
    var node = this._byId.get(String(id));
    if (!node) return Promise.resolve();

    var prevId = this._selectedId;
    this._selectedId = node.id;
    this._refreshSelected();
    // flyTo is valid immediately after construction, before ResizeObserver fires.
    if (!this._fitted) this._resize();

    var snap =
      this._motion === "instant" ||
      document.hidden ||
      this._view.w < 2 ||
      !this._fitted;
    this._takeControl();
    if (snap) {
      this._cam = { x: node.x, y: node.y, z: this._focusZoom() };
      this._clampCam();
      this._dirty = true;
      this._kick();
      return Promise.resolve();
    }

    return new Promise(function (resolve) {
      var fromNode = self._byId.get(prevId) || node;
      var v0 = toVec(norm360(180 - self._cam.x), 90 - self._cam.y);
      var v1 = toVec(node.ra, node.dec);
      var om = angBetween(v0, v1);
      var dur = clamp(650 + 1500 * (om / Math.PI), 650, 2150);
      var dip = clamp(0.5 * (om / Math.PI), 0.06, 0.5);
      self._anim = {
        kind: "fly",
        v0: v0,
        v1: v1,
        om: om,
        z0: self._cam.z,
        z1: self._focusZoom(),
        dip: dip,
        dur: dur,
        t0: null,
        resolve: resolve,
        fromNode: fromNode,
        node: node,
      };
      self._hudFrom.textContent = fromNode === node ? "Обзор" : fromNode.name;
      self._hudTo.textContent = node.name;
      self._hudBar.style.transition = "none";
      self._hudBar.style.transform = "scaleX(0)";
      void self._hudBar.offsetWidth;
      self._hudBar.style.transition =
        "transform " + (dur + 220) + "ms linear";
      self._hudBar.style.transform = "scaleX(1)";
      self._hud.hidden = false;
      self._skipBtn.disabled = false;
      self._live.textContent =
        "Перелёт к участку «" + node.name + "» · " + fmtRA(node.ra) + " " + fmtDec(node.dec);
      document.addEventListener("keydown", self._onDocKey, true);
      self._kick();
    });
  };

  SkyMap.prototype.destroy = function () {
    if (this._destroyed) return;
    this._destroyed = true;
    this._takeControl();
    this._running = false;
    if (this._raf) {
      cancelAnimationFrame(this._raf);
      this._raf = 0;
    }
    if (this._ro) this._ro.disconnect();
    document.removeEventListener("visibilitychange", this._onVis);
    document.removeEventListener("keydown", this._onDocKey, true);
    if (this._tex) {
      this._tex.onload = null;
      this._tex.onerror = null;
      this._tex.src = "";
    }
    if (this._root && this._root.parentNode)
      this._root.parentNode.removeChild(this._root);
    this._nodes = [];
    if (this._byId) this._byId.clear();
    this._pointers = null;
  };

  /* ---------- камера ---------- */

  SkyMap.prototype._focusZoom = function () {
    return clamp(this._zoom.fit * 2.4, this._zoom.min * 1.05, this._zoom.max);
  };

  SkyMap.prototype._nodeScale = function () {
    var r = this._cam.z / Math.max(this._zoom.fit, 1e-6);
    return clamp(Math.pow(r, 0.4), 0.78, 1.4);
  };

  SkyMap.prototype._clampCam = function () {
    this._cam.z = clamp(this._cam.z, this._zoom.min, this._zoom.max);
    this._cam.x = norm360(this._cam.x); // долгота зациклена
    this._cam.y = clamp(this._cam.y, 0, WORLD_H);
  };

  SkyMap.prototype._panBy = function (dx, dy) {
    this._cam.x = norm360(this._cam.x + dx);
    this._cam.y = clamp(this._cam.y + dy, 0, WORLD_H);
    this._dirty = true;
    this._kick();
  };

  SkyMap.prototype._zoomAt = function (px, py, factor) {
    var z2 = clamp(this._cam.z * factor, this._zoom.min, this._zoom.max);
    if (z2 === this._cam.z) return;
    var wx = this._cam.x + (px - this._view.w / 2) / this._cam.z;
    var wy = this._cam.y + (py - this._view.h / 2) / this._cam.z;
    this._cam.x = norm360(wx - (px - this._view.w / 2) / z2);
    this._cam.y = clamp(wy - (py - this._view.h / 2) / z2, 0, WORLD_H);
    this._cam.z = z2;
    this._dirty = true;
    this._kick();
  };

  SkyMap.prototype._zoomStep = function (factor) {
    var target = clamp(this._cam.z * factor, this._zoom.min, this._zoom.max);
    this._animateTo({ x: this._cam.x, y: this._cam.y, z: target }, 200);
  };

  SkyMap.prototype._goHome = function () {
    this._animateTo(
      {
        x: WORLD_W / 2,
        y: WORLD_H / 2,
        z: clamp(this._zoom.fit * 1.02, this._zoom.min, this._zoom.max),
      },
      340,
    );
  };

  SkyMap.prototype._animateTo = function (to, dur) {
    if (this._motion === "instant" || document.hidden) {
      this._cam = { x: norm360(to.x), y: to.y, z: to.z };
      this._clampCam();
      this._dirty = true;
      this._kick();
      return;
    }
    this._anim = {
      kind: "move",
      from: { x: this._cam.x, y: this._cam.y, z: this._cam.z },
      to: to,
      dur: dur,
      t0: null,
      ease: easeOut,
    };
    this._kick();
  };

  SkyMap.prototype._glideToView = function (node) {
    if (!node || this._view.w < 2) return;
    if (this._anim && this._anim.kind === "fly") return;
    var w = this._view.w,
      h = this._view.h;
    var sx = w / 2 + wrapDelta(node.x - this._cam.x) * this._cam.z;
    var sy = h / 2 + (node.y - this._cam.y) * this._cam.z;
    var bx = clamp(sx, w * 0.14, w * 0.86),
      by = clamp(sy, h * 0.18, h * 0.82);
    var dx = (sx - bx) / this._cam.z,
      dy = (sy - by) / this._cam.z;
    if (Math.abs(dx) < 4 && Math.abs(dy) < 4) return;
    this._animateTo(
      { x: this._cam.x + dx, y: this._cam.y + dy, z: this._cam.z },
      420,
    );
  };

  /* пользователь вмешался — перелёт разрешается без прыжка в цель */
  SkyMap.prototype._takeControl = function () {
    var a = this._anim;
    if (!a) return;
    if (a.kind === "fly") this._endFlight(false);
    else this._anim = null;
  };

  SkyMap.prototype._skipFlight = function () {
    var a = this._anim;
    if (!a || a.kind !== "fly") return;
    this._cam = { x: norm360(180 - a.node.ra), y: 90 - a.node.dec, z: a.z1 };
    this._clampCam();
    this._endFlight(true);
  };

  SkyMap.prototype._endFlight = function (completed) {
    var a = this._anim;
    this._anim = null;
    this._flight = null;
    document.removeEventListener("keydown", this._onDocKey, true);
    this._hud.hidden = true;
    this._skipBtn.disabled = true;
    if (a && a.resolve) a.resolve();
    if (completed && a && a.node)
      this._live.textContent = "Прибытие на участок «" + a.node.name + "»";
    this._dirty = true;
    this._kick();
  };

  /* ---------- цикл кадров ---------- */

  SkyMap.prototype._kick = function () {
    if (!this._raf && this._running && !this._destroyed) {
      var self = this;
      this._raf = requestAnimationFrame(function (t) {
        self._tick(t);
      });
    }
  };

  SkyMap.prototype._tick = function (now) {
    this._raf = 0;
    if (this._destroyed) return;
    var again = false;

    if (this._anim) {
      this._advanceAnim(now);
      again = true;
    }

    if (this._view.w >= 2) {
      this._draw(now);
      this._syncScene();
    }
    this._dirty = false;

    /* мгновенный режим: кадры только по изменению; плавный: постоянный
       (пульс выбора и пунктир маршрута — по замыслу, не от ОС) */
    if (again || this._motion === "animated" || !this._texReady) this._kick();
  };

  SkyMap.prototype._advanceAnim = function (now) {
    var a = this._anim;
    if (a.t0 == null) a.t0 = now;
    var el = now - a.t0;

    if (a.kind === "fly") {
      var t = clamp(el / a.dur, 0, 1);
      var e = easeInOut(t);
      var v = slerpVec(a.v0, a.v1, e);
      var rd = toRaDec(v);
      var dip = 1 - a.dip * Math.sin(Math.PI * e);
      var z = Math.exp(lerp(Math.log(a.z0), Math.log(a.z1), e)) * dip;
      this._cam.x = norm360(180 - rd[0]);
      this._cam.y = clamp(90 - rd[1], 0, WORLD_H);
      this._cam.z = clamp(z, this._zoom.min * 0.96, this._zoom.max);
      this._flight = { t: t, node: a.node, from: a.fromNode, om: a.om };
      if (t >= 1) {
        this._cam = { x: norm360(180 - a.node.ra), y: clamp(90 - a.node.dec, 0, WORLD_H), z: a.z1 };
        this._endFlight(true);
      }
    } else {
      var mt = Math.min(1, el / a.dur);
      var me = a.ease(mt);
      var dx = a.to.x - a.from.x;
      if (Math.abs(dx) > 180) dx -= Math.sign(dx) * 360; // краткий путь по долготе
      this._cam.x = norm360(a.from.x + dx * me);
      this._cam.y = lerp(a.from.y, a.to.y, me);
      this._cam.z = lerp(a.from.z, a.to.z, me);
      if (mt >= 1) {
        this._cam = { x: norm360(a.to.x), y: a.to.y, z: a.to.z };
        this._anim = null;
      }
    }
  };

  /* ---------- геометрия сцены ---------- */

  SkyMap.prototype._project = function (wx, wy) {
    var w = this._view.w, h = this._view.h;
    return [
      w / 2 + wrapDelta(wx - this._cam.x) * this._cam.z,
      h / 2 + (wy - this._cam.y) * this._cam.z,
    ];
  };

  SkyMap.prototype._pinAt = function (px, py) {
    if (!this._nodes) return null;
    var best = null, bd = 18;
    for (var i = 0; i < this._nodes.length; i++) {
      var n = this._nodes[i];
      if (!n.pin.visible) continue;
      var d = Math.hypot(n.pin.sx - px, n.pin.sy - py);
      if (d < bd) { bd = d; best = n; }
    }
    return best;
  };

  /* ---------- отрисовка ---------- */

  SkyMap.prototype._draw = function (nowMs) {
    var ctx = this._ctx;
    var w = this._view.w,
      h = this._view.h;
    if (!ctx || w < 2 || h < 2) return;
    var dpr = this._view.dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    var z = this._cam.z;

    ctx.globalCompositeOperation = "source-over";
    ctx.globalAlpha = 1;
    ctx.fillStyle = "#04070d";
    ctx.fillRect(0, 0, w, h);

    if (this._texReady && this._tex) {
      var scale = 360 * z; // px на весь мир
      var left = w / 2 - this._cam.x * z - scale / 2;
      var top = h / 2 - this._cam.y * z;
      for (var k = -1; k <= 1; k++) {
        var sx = left + k * scale;
        if (sx + scale < -2 || sx > w + 2) continue;
        ctx.drawImage(this._tex, sx, top, scale, scale / 2);
      }
    } else {
      ctx.fillStyle = "rgba(150,190,230,0.5)";
      ctx.font = "12px system-ui, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("Загрузка звёздной карты…", w / 2, h / 2);
    }

    if (!this._labelRects) this._labelRects = [];
    this._labelRects.length = 0;
    this._drawGraticule(ctx, w, h, z);
    this._drawConstellations(ctx, w, h, z, nowMs);
    this._drawNamedStars(ctx, w, h, z, nowMs);
    this._drawRoute(ctx, z, nowMs);
  };

  SkyMap.prototype._drawGraticule = function (ctx, w, h, z) {
    ctx.strokeStyle = "rgba(150,190,235,0.10)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    var i, p, k, X;
    for (i = 0; i < 12; i++) {
      p = this._project(norm360(180 - i * 30), 90);
      for (k = -1; k <= 1; k++) {
        X = p[0] + k * 360 * z;
        if (X < -2 || X > w + 2) continue;
        ctx.moveTo(X, 0);
        ctx.lineTo(X, h);
      }
    }
    for (var d = -60; d <= 60; d += 30) {
      p = this._project(180, 90 - d);
      if (p[1] < -2 || p[1] > h + 2) continue;
      ctx.moveTo(0, p[1]);
      ctx.lineTo(w, p[1]);
    }
    ctx.stroke();

    /* подписи часов — только при обзоре всей карты */
    if (z > this._zoom.fit * 1.6) return;
    ctx.fillStyle = "rgba(170,205,235,0.5)";
    ctx.font = "10px Rubik, system-ui, sans-serif";
    ctx.textAlign = "center";
    for (i = 0; i < 12; i++) {
      p = this._project(norm360(180 - i * 30), 4);
      if (p[0] < 18 || p[0] > w - 18) continue;
      ctx.fillText(i * 2 + "ч", p[0], 14);
    }
  };

  SkyMap.prototype._drawConstellations = function (ctx, w, h, z, nowMs) {
    var consts = this._catalog ? this._catalog.consts : [];
    if (!consts.length) return;
    var r = z / Math.max(this._zoom.fit, 1e-6);
    ctx.strokeStyle = "rgba(155,200,245,0.26)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (var i = 0; i < consts.length; i++) {
      var lines = consts[i].lines;
      for (var j = 0; j < lines.length; j++) {
        var line = lines[j];
        var prev = null;
        for (var k = 0; k < line.length; k++) {
          var p = this._project(norm360(180 - line[k][0]), 90 - line[k][1]);
          if (prev && Math.abs(p[0] - prev[0]) < w * 0.5) {
            ctx.moveTo(prev[0], prev[1]);
            ctx.lineTo(p[0], p[1]);
          }
          prev = p;
        }
      }
    }
    ctx.stroke();

    /* русские названия созвездий — растворяются при сильном увеличении */
    var alpha = r <= 1.5 ? 0.62 : clamp(1.7 - r * 0.35, 0, 0.62);
    if (alpha <= 0.02) return;
    ctx.fillStyle = "rgba(196,224,250," + alpha.toFixed(3) + ")";
    ctx.font = "600 11px Rubik, system-ui, sans-serif";
    ctx.textAlign = "center";
    for (i = 0; i < consts.length; i++) {
      var c = consts[i];
      var p2 = this._project(norm360(180 - c.ra), 90 - c.dec);
      if (p2[0] < -60 || p2[0] > w + 60 || p2[1] < -20 || p2[1] > h + 20)
        continue;
      this._drawLabel(ctx, String(c.name || ""), p2[0], p2[1], true);
    }
  };

  SkyMap.prototype._drawNamedStars = function (ctx, w, h, z, nowMs) {
    var stars = this._catalog ? this._catalog.stars : [];
    if (!stars.length) return;
    var r = z / Math.max(this._zoom.fit, 1e-6);
    var showLabel = r >= 1.15;
    var alpha = showLabel ? clamp((r - 1.15) * 1.6, 0.15, 0.85) : 0;
    ctx.textAlign = "left";
    for (var i = 0; i < stars.length; i++) {
      var s = stars[i];
      var p = this._project(norm360(180 - s.ra), 90 - s.dec);
      if (p[0] < -40 || p[0] > w + 40 || p[1] < -20 || p[1] > h + 20) continue;
      var mag = isFinite(s.mag) ? s.mag : 3;
      var rad = clamp(2.6 - mag * 0.28, 0.8, 2.6);
      /* мягкое свечение поверх текстуры для читаемости подписи */
      ctx.globalAlpha = 0.5;
      ctx.fillStyle = "#e8f1ff";
      ctx.beginPath();
      ctx.arc(p[0], p[1], rad, 0, TAU);
      ctx.fill();
      if (showLabel && s.name) {
        ctx.globalAlpha = alpha;
        ctx.fillStyle = "rgba(232,241,255,0.95)";
        ctx.font = "10.5px Rubik, system-ui, sans-serif";
        this._drawLabel(ctx, String(s.name), p[0] + 6, p[1] + 3.5, false);
      }
    }
    ctx.globalAlpha = 1;
  };

  SkyMap.prototype._drawLabel = function (ctx, text, x, y, centered) {
    if (!text) return;
    var width = ctx.measureText(text).width;
    var left = centered ? x - width / 2 : x;
    var right = left + width, top = y - 12, bottom = y + 3;
    if (left < 6 || right > this._view.w - 6 || top < 58 ||
        bottom > this._view.h - this._cardSize.bottom) return;
    for (var i = 0; i < this._labelRects.length; i++) {
      var r = this._labelRects[i];
      if (left < r.right + 4 && right + 4 > r.left &&
          top < r.bottom + 4 && bottom + 4 > r.top) return;
    }
    for (var j = 0; j < this._nodes.length; j++) {
      var box = this._nodes[j].box;
      if (box.w && left < box.x + box.w + 3 && right + 3 > box.x &&
          top < box.y + box.h + 3 && bottom + 3 > box.y) return;
    }
    this._labelRects.push({ left: left, right: right, top: top, bottom: bottom });
    ctx.fillText(text, x, y);
  };

  SkyMap.prototype._drawRoute = function (ctx, z, nowMs) {
    var f = this._flight;
    if (!f) return;
    var a = this._anim;
    if (!a) return;
    /* путь большого круга — по настоящей сфере */
    ctx.save();
    ctx.setLineDash([7, 8]);
    ctx.lineDashOffset = -(nowMs * 0.02) % 15;
    ctx.strokeStyle = "rgba(121,224,194,0.5)";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    var prev = null;
    var steps = 36;
    for (var i = 0; i <= steps; i++) {
      var v = slerpVec(a.v0, a.v1, i / steps);
      var rd = toRaDec(v);
      var p = this._project(norm360(180 - rd[0]), clamp(90 - rd[1], 0, 180));
      if (prev && Math.abs(p[0] - prev[0]) < this._view.w * 0.5) {
        ctx.moveTo(prev[0], prev[1]);
        ctx.lineTo(p[0], p[1]);
      }
      prev = p;
    }
    ctx.stroke();
    ctx.restore();
  };

  /* ---------- DOM-синхронизация: булавки и выноски ---------- */

  SkyMap.prototype._syncScene = function () {
    if (!this._ready) {
      this._ready = true;
      this._root.classList.add("sky-ready");
    }
    var sig =
      this._cam.x.toFixed(2) +
      "|" +
      this._cam.y.toFixed(2) +
      "|" +
      this._cam.z.toFixed(3);
    if (sig !== this._camSig) {
      this._camSig = sig;
      this._layoutCallouts();
      this._syncControls();
      this._syncReadout();
    }
    var canvas = this._ctx.canvas;
    var cw = this._view.w || canvas.width / (this._view.dpr || 1),
      ch = this._view.h || canvas.height / (this._view.dpr || 1);
    /* лидеры и пульс рисуем поверх текстуры */
    this._drawPins(cw, ch, performance.now());
  };

  SkyMap.prototype._drawPins = function (w, h, nowMs) {
    var ctx = this._ctx;
    var s = this._nodeScale();
    ctx.save();
    for (var i = 0; i < this._nodes.length; i++) {
      var n = this._nodes[i];
      var p = this._project(n.x, n.y);
      var vis = p[0] > -30 && p[0] < w + 30 && p[1] > -30 && p[1] < h + 30;
      n.pin.sx = p[0];
      n.pin.sy = p[1];
      n.pin.visible = vis;
      if (!vis) continue;
      var sel = n.id === this._selectedId;
      /* линия-выноска к карточке */
      var bx = n.box.x, by = n.box.y, bw = n.box.w, bh = n.box.h;
      var hasBox = bw > 0 && n.el.style.display !== "none";
      if (hasBox && (n.dx || n.dy)) {
        var ax = clamp(p[0], bx, bx + bw);
        var ay = clamp(p[1], by, by + bh);
        ctx.strokeStyle = sel ? "rgba(121,224,194,0.85)" : "rgba(170,205,235,0.55)";
        ctx.lineWidth = sel ? 1.6 : 1;
        ctx.beginPath();
        ctx.moveTo(p[0], p[1]);
        ctx.lineTo(ax, ay);
        ctx.stroke();
      }
      /* булавка: кольцо + точка */
      ctx.strokeStyle = sel ? "#79e0c2" : "rgba(210,230,250,0.9)";
      ctx.fillStyle = sel ? "rgba(121,224,194,0.25)" : "rgba(10,20,32,0.55)";
      ctx.lineWidth = sel ? 2 : 1.4;
      ctx.beginPath();
      ctx.arc(p[0], p[1], (sel ? 8 : 6.5) * s, 0, TAU);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = sel ? "#79e0c2" : "#e8f1ff";
      ctx.beginPath();
      ctx.arc(p[0], p[1], (sel ? 3.2 : 2.4) * s, 0, TAU);
      ctx.fill();
      if (sel && this._motion === "animated" && !this._destroyed) {
        var ph = (nowMs * 0.0012) % 1;
        ctx.globalAlpha = (1 - ph) * 0.55;
        ctx.strokeStyle = "#79e0c2";
        ctx.lineWidth = 1.6;
        ctx.beginPath();
        ctx.arc(p[0], p[1], (8 + 26 * ph) * s, 0, TAU);
        ctx.stroke();
        ctx.globalAlpha = 1;
      }
    }
    ctx.restore();
  };

  SkyMap.prototype._layoutCallouts = function () {
    var w = this._view.w,
      h = this._view.h;
    if (w < 2) return;
    var size = this._cardSize;
    var placed = [];
    var selId = this._selectedId;
    var order = this._nodes.slice().sort(function (a, b) {
      var sa = a.id === selId ? 1 : 0;
      var sb = b.id === selId ? 1 : 0;
      return sb - sa;
    });
    for (var i = 0; i < order.length; i++) {
      var n = order[i];
      var p = this._project(n.x, n.y);
      n.pin.sx = p[0];
      n.pin.sy = p[1];
      n.pin.visible = p[0] > -30 && p[0] < w + 30 && p[1] > -30 && p[1] < h + 30;
      if (!n.pin.visible) {
        n.box.w = 0;
        n.el.style.display = "none";
        continue;
      }
      var pos = this._placeCallout(p[0], p[1], size, placed, w, h);
      n.dx = pos.dx;
      n.dy = pos.dy;
      n.box = pos.box;
      placed.push(pos.box);
      n.el.style.display = "";
      n.el.style.transform =
        "translate(" +
        (p[0] + pos.dx).toFixed(1) +
        "px," +
        (p[1] + pos.dy).toFixed(1) +
        "px)";
    }
  };

  SkyMap.prototype._placeCallout = function (px, py, size, placed, w, h) {
    /* Выноски занимают ближайшие свободные ячейки; метки остаются на RA/Dec.
       Одинаковые размеры в CSS и расчёте исключают перекрытие плотных полей.
       Верхняя и нижняя полосы оставлены для заголовка и управления. */
    var margin = 8, top = 64, bottom = size.bottom, gap = 6;
    var bestBox = null, bestScore = Infinity;
    for (var y = top; y + size.h <= h - bottom; y += size.h + gap) {
      for (var x = margin; x + size.w <= w - margin; x += size.w + gap) {
        var occupied = false;
        for (var i = 0; i < placed.length; i++) {
          if (placed[i].x === x && placed[i].y === y) {
            occupied = true;
            break;
          }
        }
        if (occupied) continue;
        var dx = x + size.w / 2 - px, dy = y + size.h / 2 - py;
        var score = dx * dx + dy * dy;
        if (px >= x && px <= x + size.w && py >= y && py <= y + size.h)
          score += w * w + h * h;
        if (score < bestScore) {
          bestScore = score;
          bestBox = { x: x, y: y, w: size.w, h: size.h };
        }
      }
    }
    if (!bestBox) throw new Error("Недостаточно места для выносок карты");
    return { dx: bestBox.x - px, dy: bestBox.y - py, box: bestBox };
  };

  SkyMap.prototype._syncControls = function () {
    var z = this._cam.z;
    var zMin = this._zoom.min,
      zMax = this._zoom.max;
    var v = Math.round((1000 * Math.log(z / zMin)) / Math.log(zMax / zMin));
    this._zoomRange.value = String(clamp(v, 0, 1000));
    this._zoomRange.setAttribute("aria-valuetext", "масштаб ×" + z.toFixed(2));
    var label = "×" + z.toFixed(2);
    if (this._zoomValue.textContent !== label)
      this._zoomValue.textContent = label;
    this._btnIn.disabled = z >= zMax - 0.001;
    this._btnOut.disabled = z <= zMin + 0.001;
  };

  SkyMap.prototype._syncReadout = function () {
    var ra = norm360(180 - this._cam.x);
    var dec = 90 - this._cam.y;
    var b = "ЦЕНТР: " + fmtRA(ra) + " · " + fmtDec(dec);
    if (this._readoutB.textContent !== b)
      this._readoutB.textContent = b;
  };

  SkyMap.prototype._resize = function () {
    if (this._destroyed) return;
    var rect = this._viewport.getBoundingClientRect();
    var w = Math.round(rect.width),
      h = Math.round(rect.height);
    if (w < 2 || h < 2) {
      this._view.w = 0;
      return;
    }
    this._root.classList.remove("sky-compact");
    var style = getComputedStyle(this._root);
    var fullWidth = parseFloat(style.getPropertyValue("--skm-callout-width"));
    var fullHeight = parseFloat(style.getPropertyValue("--skm-callout-height"));
    var fullBottom = parseFloat(style.getPropertyValue("--skm-callout-bottom"));
    var capacity = Math.floor((w - 10) / (fullWidth + 6)) *
      Math.max(0, Math.floor((h - 64 - fullBottom + 6) / (fullHeight + 6)));
    this._root.classList.toggle("sky-compact", w < 700 || capacity < this._nodes.length);
    this._cardSize = {
      w: parseFloat(style.getPropertyValue("--skm-callout-width")),
      h: parseFloat(style.getPropertyValue("--skm-callout-height")),
      bottom: parseFloat(style.getPropertyValue("--skm-callout-bottom")),
    };
    var columns = Math.max(1, Math.floor((w - 10) / (this._cardSize.w + 6)));
    var minHeight = Math.max(340, 64 + this._cardSize.bottom +
      Math.ceil(this._nodes.length / columns) * (this._cardSize.h + 6) - 6);
    this._root.style.minHeight = minHeight + "px";
    h = Math.round(this._viewport.getBoundingClientRect().height);
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    this._view = { w: w, h: h, dpr: dpr };
    this._canvas.width = Math.round(w * dpr);
    this._canvas.height = Math.round(h * dpr);
    this._canvas.style.width = w + "px";
    this._canvas.style.height = h + "px";

    var sky = this._sky;
    var texPxPerDeg = sky && sky.width ? sky.width / WORLD_W : 22.75;
    var fit = clamp(Math.min(w / WORLD_W, h / WORLD_H) * 0.94, 0.14, 8);
    this._zoom = {
      fit: fit,
      min: clamp(fit * 0.85, 0.12, 0.5),
      max: clamp(texPxPerDeg * 1.5, 4, 40),
    };
    if (!this._fitted) {
      this._fitted = true;
      this._cam = {
        x: WORLD_W / 2,
        y: WORLD_H / 2,
        z: clamp(fit * 1.02, this._zoom.min, this._zoom.max),
      };
    }
    this._clampCam();
    this._camSig = "";
    this._dirty = true;
    this._kick();
  };

  window.SkyMap = SkyMap;
})();
