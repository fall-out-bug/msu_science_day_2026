/* Instrument adventure. Science images, times and measurements stay in GAME_DATA.
 * The illustration is scenery; evidence overlays use the verified pixel transform.
 */
(() => {
  "use strict";
  if (new URLSearchParams(location.search).get("archive") === "1") return;
  const D = window.GAME_DATA,
    C = window.NIGHTSHIFT_CONTENT,
    E = window.NIGHTSHIFT_EVIDENCE;
  const app = document.querySelector("#app");
  const esc = (value) =>
    String(value ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  const b = (action, label, value = "", extra = "") =>
    `<button type="button" data-ns="${action}" data-value="${esc(value)}" ${extra}>${label}</button>`;
  const date = new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  });
  const fmt = (n) =>
    Number(n).toLocaleString("ru-RU", { maximumFractionDigits: 1 });
  window.nightshift = new NightShiftSession(D, 3);
  const s = window.nightshift;
  let scene = "welcome",
    level = 3,
    map = null,
    blink = null,
    toastTimer = null,
    flying = false;
  let motion = !matchMedia("(prefers-reduced-motion: reduce)").matches;
  let ui = {
    epoch: 0,
    tool: "mark",
    zoom: 1,
    measure: false,
    cursor: { x: 0.5, y: 0.5 },
  };
  const note = () => s.note(s.current.id);
  const countLabel = () => `${s.completed} / ${s.cases.length}`;
  const caseLabel = (c) =>
    `Поле ${String(s.cases.indexOf(c) + 1).padStart(2, "0")}`;
  const coords = (c) =>
    `α ${Number(c.ra).toFixed(3)}° · δ ${Number(c.dec).toFixed(3)}°`;
  const stamp = (c, e) =>
    `${date.format(new Date(c.observations[e].date))} UTC · ${c.observations[e].filter}`;
  const status = (c) =>
    s.note(c.id).decision
      ? "decided"
      : s.note(c.id).checked
        ? "checked"
        : s.note(c.id).prediction
          ? "noticed"
          : "new";
  const statuses = () =>
    Object.fromEntries(s.cases.map((c) => [c.id, status(c)]));
  function announce(message) {
    document.querySelector("#announce").textContent = message;
    const el = document.querySelector(".ns-toast");
    if (el) {
      el.textContent = message;
      el.classList.add("is-visible");
    }
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el?.classList.remove("is-visible"), 4200);
  }
  const icon = (name) => ({ sky: "✦", observe: "◉", board: "▤" })[name];
  function mentor(message, large = false) {
    return `<div class="${large ? "ns-dialogue" : "ns-mentor"}"><div class="ns-portrait">${window.NIGHTSHIFT_ART.mentor ? `<img src="${window.NIGHTSHIFT_ART.mentor}" alt="Ника, дежурный астроном">` : '<span class="ns-avatar" aria-hidden="true">Н</span>'}</div><div class="ns-bubble"><span class="ns-eyebrow">${esc(C.character)}</span><p>${esc(message)}</p></div></div>`;
  }
  function header() {
    return `<header class="ns-topbar"><button class="ns-brand" data-ns="${scene === "welcome" ? "welcome" : "room"}" aria-label="В обсерваторию"><span aria-hidden="true">✦</span> НОЧНАЯ СМЕНА</button>${scene !== "welcome" ? `<div class="ns-progress"><span>Утренний отчёт <b>${countLabel()}</b></span><progress max="${s.cases.length}" value="${s.completed}" aria-label="Исследовано полей"></progress></div><nav class="ns-nav" aria-label="Рабочие места">${b("sky", "Карта неба", "", `aria-current="${scene === "sky" ? "page" : "false"}"`)}${b("board", "Отчёт", "", `aria-current="${scene === "board" ? "page" : "false"}"`)}<span class="ns-pill" title="Заявки на третий архивный кадр">✧ ${s.remaining} / ${s.budget}</span></nav>` : '<span class="ns-tag">НАУКА 0+ · ИГРА С НАСТОЯЩИМ НЕБОМ</span>'}${b("motion", motion ? "◌ Анимация" : "◌ Без анимации", "", `class="ns-motion" aria-pressed="${motion}"`)}</header>`;
  }
  function welcome() {
    return `<section class="ns-scene ns-welcome"><div class="ns-hero"><p class="ns-eyebrow">ОБСЕРВАТОРИЯ ЖДЁТ ТВОЮ КОМАНДУ</p><h1>Ночная<br><em>смена</em><span class="ns-title-star" aria-hidden="true">✦</span></h1><p class="ns-lead">В небе что-то изменилось.<br>К утру выясним, что именно.</p><p class="ns-muted">Наводи телескоп. Сравнивай настоящие снимки.<br>Собирай улики — и свою историю наблюдений.</p><div class="ns-levels" role="group" aria-label="Сложность смены">${[3, 6, 9].map((n) => b("level", `<strong>${n}</strong><span>${esc(C.levels[n].label)}</span><small>${n / 3} ${n === 3 ? "заявка" : "заявки"}</small>`, n, `class="ns-level" aria-pressed="${level === n}"`)).join("")}</div>${b("start", 'Заступить на смену <span aria-hidden="true">→</span>', "", 'class="ns-primary"')}<p class="ns-muted ns-fine">${esc(C.levels[level].description)}</p></div><div class="ns-welcome-note"><span class="ns-beacon" aria-hidden="true"></span>Обсерватория на связи<br><small>Всё для смены уже на этом устройстве</small></div></section>`;
  }
  function intro() {
    return `<section class="ns-scene ns-intro"><div class="ns-intro-heading"><p class="ns-eyebrow">ТВОЯ ПЕРВАЯ НОЧЬ В ОБСЕРВАТОРИИ</p><h1>На связи — Ника.</h1></div>${mentor(C.intro, true)}<div class="ns-paper"><p><b>Задача смены:</b> исследовать ${s.cases.length} участков неба и передать утренней команде свои выводы.</p><p>${esc(C.archiveNote)}</p><p>Для сложных дел есть ${s.budget} ${s.budget === 1 ? "заявка" : "заявки"}. «Недостаточно данных» — тоже обоснованный вывод.</p>${b("begin", "Показать обсерваторию →", "", 'class="ns-primary"')}</div></section>`;
  }
  function room() {
    return `<section class="ns-scene ns-room"><div class="ns-room-heading"><p class="ns-eyebrow">${s.completed === s.cases.length ? "РАССВЕТ УЖЕ БЛИЗКО" : "ОБСЕРВАТОРИЯ · НОЧНАЯ СМЕНА"}</p><h1>${s.completed === s.cases.length ? "Отчёт готов к передаче." : "Всё начинается с неба."}</h1><p>${s.completed ? `В отчёте ${s.completed} из ${s.cases.length} полей. Каждую версию можно уточнить.` : "Выбери рабочее место. Ника поможет разобраться по ходу дела."}</p></div><div class="ns-stations">${[
      ["sky", "01", "Карта неба", "Найти участок и навести телескоп"],
      [
        "observe",
        "02",
        "Станция наблюдений",
        "Сравнить снимки и отметить изменения",
      ],
      ["board", "03", "Доска расследования", "Собрать выводы в утренний отчёт"],
    ]
      .map(([key, n, title, copy]) =>
        b(
          key,
          `<span class="ns-hotspot-icon" aria-hidden="true">${icon(key)}</span><small>${n} / РАБОЧЕЕ МЕСТО</small><strong>${title}</strong><span>${copy}</span>`,
          "",
          `class="ns-hotspot" data-station="${key}"`,
        ),
      )
      .join(
        "",
      )}</div><p class="ns-room-caption">Комната — вымышленная. Звёзды, снимки и измерения — настоящие.</p></section>`;
  }
  function fieldPanel() {
    const c = s.current;
    return `<p class="ns-eyebrow">НАПРАВЛЕНИЕ НАБЛЮДЕНИЯ</p><h2>${caseLabel(c)}</h2><p>${esc(c.skyContext.constellation.name)}</p><p class="ns-coordinates">${coords(c)} · ICRS</p><img class="ns-field-preview" src="${c.frames[0]}" alt="Первый архивный кадр выбранного поля"><p>${esc(c.skyContext.intro)}</p>${b("aim", "Навести телескоп →", "", 'class="ns-primary"')}<p class="ns-muted ns-fine">Перелёт покажет направление на каталожной карте. Затем откроются архивные снимки ZTF.</p>`;
  }
  function sky() {
    return `<section class="ns-scene ns-sky ns-workspace"><div class="ns-screen-heading"><div><p class="ns-eyebrow">01 / КАРТА НЕБА</p><h1>Выбери, куда смотреть</h1></div><span class="ns-tag">РЕАЛЬНЫЕ КООРДИНАТЫ · КАТАЛОГ ЗВЁЗД</span></div><div class="ns-case-nav" aria-label="Поля смены">${s.cases.map((c) => b("field", `${status(c) === "decided" ? "✓ " : ""}${caseLabel(c)}`, c.id, `aria-pressed="${c.id === s.current.id}"`)).join("")}</div><div class="ns-sky-layout"><div id="ns-map"></div><aside id="ns-field-panel" class="ns-panel">${fieldPanel()}</aside></div></section>`;
  }
  function overlay(c, epoch, reveal = false) {
    const e = E[c.id],
      mark = s.note(c.id).marks[epoch];
    let shapes = "";
    if (mark)
      shapes += `<circle cx="${mark.x * 128}" cy="${mark.y * 128}" r="5" fill="none" stroke="#ffc875" stroke-width=".8"/><path d="M${mark.x * 128 - 8} ${mark.y * 128}h3m10 0h3M${mark.x * 128} ${mark.y * 128 - 8}v3m0 10v3" stroke="#ffc875" stroke-width=".6"/>`;
    if (reveal) {
      const target = e.targets[epoch];
      if (e.kind === "motion")
        shapes += `<polyline points="${e.targets
          .filter(Boolean)
          .map((p) => `${p.x + 0.5},${p.y + 0.5}`)
          .join(
            " ",
          )}" fill="none" stroke="#83e8e4" stroke-width=".5" stroke-dasharray="2 2"/>`;
      if (target)
        shapes += `<circle cx="${target.x + 0.5}" cy="${target.y + 0.5}" r="${c.id === "s08" ? 4 : 6}" fill="none" stroke="#83e8e4" stroke-width=".8"/>`;
      for (const p of e.controls || [])
        shapes += `<rect x="${p.x - 3.5}" y="${p.y - 3.5}" width="8" height="8" fill="none" stroke="#bcabef" stroke-width=".6"/>`;
    }
    return `<svg class="ns-overlays" viewBox="0 0 128 128" aria-hidden="true">${shapes}</svg>`;
  }
  function framePlane(c) {
    const n = note();
    return `<div class="ns-image-plane" style="transform:scale(${ui.zoom})"><img class="ns-frame" draggable="false" src="${c.frames[ui.epoch]}" alt="${caseLabel(c)}, кадр ${ui.epoch + 1}">${overlay(c, ui.epoch, n.revealed)}<span class="ns-reticle" style="left:${ui.cursor.x * 100}%;top:${ui.cursor.y * 100}%" aria-hidden="true"></span></div>`;
  }
  function measurements(c, all = false) {
    if (!c.photometry || E[c.id].kind === "motion")
      return `<p class="ns-muted">${E[c.id].kind === "motion" ? "Для этого поля сравнивай положение точки относительно соседних звёзд: отметь её на каждом кадре." : "Для этого поля числовой ряд яркости не подготовлен. Сравни форму детали и её повторяемость на кадрах."}</p>`;
    const rows = c.photometry.epochs.slice(0, all || s.hasThird(c.id) ? 3 : 2);
    const key = c.id === "s03" ? "mag_diff" : "mag";
    const base = rows.find((r) => Number.isFinite(r[key]));
    const values = rows.map((r) =>
      r.source_fluxes
        ? (100 * r.source_fluxes[0]) / rows[0].source_fluxes[0]
        : base && Number.isFinite(r[key])
          ? 100 * Math.pow(10, -0.4 * (r[key] - base[key]))
          : null,
    );
    const max = Math.max(100, ...values.filter((v) => v !== null));
    return `<div class="ns-chart"><h3>${c.id === "s03" ? "Изменяющаяся часть света" : "Измеренная яркость"}</h3><p class="ns-muted ns-fine">${c.id === "s03" ? "Кадр 2 = 100%. После вычитания опорного снимка; не полный свет источника." : "Кадр 1 = 100%. Свет всего источника, а не одного пикселя."}</p>${values.map((v, i) => `<div class="ns-bar" style="--value:${v === null ? 0 : (100 * v) / max}%;--i:${i}"><span>Кадр ${i + 1}</span><span class="ns-meter"><i></i></span><b>${v === null ? "нет измерения" : fmt(v) + "%"}</b></div>`).join("")}<p class="ns-muted ns-fine">${c.id === "s01" ? "Измерения одной из ярких звёзд сравнения." : "Измерения выбранного в архиве источника, не произвольной отметки игрока."}</p><details><summary>Метод измерения</summary><p>${esc(c.photometry.note)}</p></details></div>`;
  }
  function observe() {
    const c = s.current,
      n = note();
    return `<section class="ns-scene ns-observe ns-workspace"><div class="ns-screen-heading"><div><p class="ns-eyebrow">02 / СТАНЦИЯ НАБЛЮДЕНИЙ</p><h1>${caseLabel(c)} <span class="ns-muted">/ ${esc(c.skyContext.constellation.name)}</span></h1></div>${b("sky", "↖ Карта неба", "", 'class="ns-secondary"')}</div><div class="ns-lab"><div class="ns-viewer"><div class="ns-tools" role="group" aria-label="Инструменты наблюдения">${b("blink", "▶ Чередовать", "", 'aria-pressed="false"')}${b("zoom", `⌕ Увеличение ×${ui.zoom}`, "", `aria-pressed="${ui.zoom === 2}"`)}${b("measure", "▥ Измерения", "", `aria-pressed="${ui.measure}"`)}</div><div class="ns-frame-tabs" role="group" aria-label="Архивные кадры">${[0, 1, 2].map((e) => b("epoch", `Кадр ${e + 1}${e === 2 && !s.hasThird(c.id) ? " · закрыт" : ""}`, e, `aria-pressed="${e === ui.epoch}" ${e === 2 && !s.hasThird(c.id) ? "disabled" : ""}`)).join("")}</div><div class="ns-image-wrap" data-epoch="${ui.epoch}" tabindex="0" role="group" aria-label="Снимок. Нажми на деталь, чтобы отметить её. Стрелки перемещают прицел, Enter ставит отметку.">${framePlane(c)}</div><div class="ns-frame-meta"><b id="ns-frame-label">Кадр ${ui.epoch + 1}</b><span id="ns-frame-date">${esc(stamp(c, ui.epoch))}</span></div><p class="ns-hint">Нажми на интересную деталь. Затем переключи кадр и найди её снова. <span class="ns-muted">Клавиатура: стрелки и Enter.</span></p>${n.revealed ? '<p class="ns-hint">Золотая отметка — твоя. Бирюзовая — объект из разбора. Фиолетовая — звезда сравнения.</p>' : ""}<div id="ns-measurements" ${ui.measure ? "" : "hidden"}>${measurements(c)}</div><details class="ns-source"><summary>Паспорт наблюдения · ${coords(c)}</summary><p>Настоящие архивные кадры телескопа ZTF, Паломарская обсерватория. Даты приведены в UTC; r — красный фильтр. Каждый снимок содержит 128 × 128 пикселей.</p><p>${esc(D.meta.display.note)}</p><p><a href="${esc(c.source.url)}" target="_blank" rel="noopener noreferrer">${esc(c.source.label)} ↗</a></p><p>${esc(c.source.credit)}</p></details></div><aside class="ns-panel"><p class="ns-eyebrow">ИССЛЕДОВАТЕЛЬСКИЙ ЖУРНАЛ</p><h2>Что происходит в поле?</h2><p>${esc(C.cases[c.id].prompt)}</p><div class="ns-choices" role="group" aria-label="Моё наблюдение">${Object.entries(
      C.predictions,
    )
      .map(([v, label]) =>
        b(
          "predict",
          esc(label),
          v,
          `class="ns-choice" aria-pressed="${n.prediction === v}"`,
        ),
      )
      .join(
        "",
      )}</div><div class="ns-request"><span class="ns-eyebrow">ПРОВЕРКА ГИПОТЕЗЫ</span><p>${s.hasThird(c.id) ? "Третий кадр доступен. Проверь, выдержит ли твоя версия ещё одно наблюдение." : "Третий кадр поможет отличить движение, изменение света и случайную помеху. На какие дела потратить заявки — решаешь ты."}</p>${b("request", s.hasThird(c.id) ? "Открыть третий кадр" : `Запросить третий кадр · ${s.remaining} осталось`, "", `class="ns-secondary" ${!n.prediction || (!s.hasThird(c.id) && !s.remaining) ? "disabled" : ""}`)}${!n.prediction ? '<small class="ns-muted">Сначала запиши наблюдение выше.</small>' : ""}</div><div class="ns-verdicts"><h3>${n.revealed ? "Уточнить вывод" : "Передать вывод Нике"}</h3>${Object.entries(
      C.verdicts,
    )
      .map(([v, label]) =>
        b(
          "verdict",
          esc(label),
          v,
          `class="ns-choice" ${!n.prediction ? "disabled" : ""} aria-pressed="${n.decision === v}"`,
        ),
      )
      .join(
        "",
      )}</div>${n.revealed ? `<p class="ns-muted">До разбора: ${esc(C.verdicts[n.beforeReveal] || "версия не записана")}.</p>` : '<p class="ns-muted ns-fine">«Недостаточно данных» оставит вопрос открытым. После вывода мы вместе разберём доказательства.</p>'}</aside></div></section>`;
  }
  function review() {
    const c = s.current,
      n = note();
    return `<section class="ns-scene ns-review ns-workspace"><div class="ns-screen-heading"><div><p class="ns-eyebrow">УЛИКА ДОБАВЛЕНА В ОТЧЁТ</p><h1>${caseLabel(c)}: что говорят наблюдения</h1></div><span class="ns-pill">✓ ${countLabel()}</span></div>${mentor(C.cases[c.id].mentor)}<div class="ns-review-grid"><div><div class="ns-evidence-strip">${[0, 1, 2].map((e) => `<figure class="ns-evidence-frame" style="--i:${e}"><div><img src="${c.frames[e]}" alt="Архивный кадр ${e + 1}">${overlay(c, e, true)}</div><figcaption><b>Кадр ${e + 1}</b><small>${esc(stamp(c, e))}</small></figcaption></figure>`).join("")}</div><p class="ns-muted ns-fine">Бирюзовый — объект из разбора${E[c.id].kind === "motion" ? " и его положения на трёх кадрах" : ""}. Золотой — твои отметки.${c.id === "s08" ? " Кружок показывает фрагмент протяжённого следа." : ""} После разбора третий кадр открыт бесплатно.</p>${measurements(c, true)}<details><summary>Доказательства и пределы вывода</summary><p>${esc(c.evidence)}</p><p>${esc(c.limitations)}</p><p>${esc(E[c.id].note)}</p></details><details><summary>Что заметил алгоритм</summary><p>Оценка необычности: <b>${Number(c.score).toFixed(3)}</b>. Это заранее рассчитанная оценка игрового детектора, не вероятность открытия.</p><p>${c.score < D.meta.thresholds.soft ? "На мягком пороге 1 этот детектор не выделил бы поле. Низкая оценка не отменяет изменения, которое подтверждают наблюдения." : "На мягком пороге 1 детектор выделил бы поле. Высокая оценка сама по себе ещё не отличает событие на небе от помехи."}</p></details></div><aside class="ns-receipt"><span class="ns-eyebrow">ЗАПИСЬ В ЖУРНАЛЕ</span><h2>${esc(C.verdicts[n.decision])}</h2><dl><dt>Твоя версия до разбора</dt><dd>${esc(C.verdicts[n.beforeReveal] || "Не записана")}</dd><dt>Вывод по архивным данным</dt><dd>${esc(C.verdicts[c.expectedVerdict])}</dd></dl><p>${n.decision === "uncertain" ? "Вопрос остаётся открытым в твоём отчёте. Теперь можно вернуться к снимкам и уточнить вывод." : n.decision === c.expectedVerdict ? "Твоя текущая версия согласуется с архивными данными." : "Архивные данные поддерживают другой вывод. Вернись к снимкам и проверь, что повлияло на твою версию."}</p>${b("revise", "Вернуться к снимкам", "", 'class="ns-secondary"')}${b("next", s.nextId() ? "К следующему полю →" : "Передать утренний отчёт →", "", 'class="ns-primary"')}</aside></div></section>`;
  }
  function board() {
    const r = s.report(),
      done = r.answered === r.total;
    return `<section class="ns-scene ns-board ns-workspace"><div class="ns-screen-heading"><div><p class="ns-eyebrow">03 / ДОСКА РАССЛЕДОВАНИЯ</p><h1>${done ? "Небо стало чуть понятнее." : "Утренний отчёт"}</h1></div><span class="ns-pill">${done ? "СМЕНА ЗАВЕРШЕНА" : "СМЕНА ПРОДОЛЖАЕТСЯ"}</span></div>${mentor(done ? "Утренняя команда получила твои записи. Мы сохранили первые версии и уточнения: путь к выводу так же важен, как сам вывод. Небо ещё приготовит нам вопросы." : "Здесь собирается история твоей смены. Выбирай любое поле, чтобы продолжить исследование или проверить прежнюю версию.")}<div class="ns-summary"><div><b>${r.answered} / ${r.total}</b><span>полей исследовано</span></div><div><b>${r.open}</b><span>вопросов оставлено открытыми</span></div><div><b>${r.revised}</b><span>версий уточнено после разбора</span></div></div><div class="ns-case-grid">${s.cases
      .map((c, i) => {
        const n = s.note(c.id);
        return b(
          "open-card",
          `<span class="ns-card-photo"><img src="${c.frames[n.decision ? 1 : 0]}" alt="">${n.decision ? '<span class="ns-stamp">В ОТЧЁТЕ ✓</span>' : '<span class="ns-stamp">ЖДЁТ НАБЛЮДЕНИЯ</span>'}</span><span class="ns-eyebrow">${caseLabel(c)} · ${esc(c.skyContext.constellation.name)}</span><strong>${esc(n.decision ? C.verdicts[n.decision] : "Что скрывается в этом поле?")}</strong><span class="ns-muted">${n.revealed && n.beforeReveal !== n.decision ? `До разбора: ${esc(C.verdicts[n.beforeReveal] || "нет версии")}` : n.decision ? "Открыть улики и уточнить вывод →" : "Навести телескоп →"}</span>`,
          c.id,
          `class="ns-case-card" style="--i:${i}"`,
        );
      })
      .join(
        "",
      )}</div><div class="ns-end">${done ? `${b("restart", "Ещё одна смена", "", 'class="ns-primary"')}<p class="ns-muted">Попробуй больше полей или исследуй их с напарником.</p>` : b("next", "Продолжить исследование →", "", 'class="ns-primary"')}</div></section>`;
  }
  function stopBlink() {
    clearInterval(blink);
    blink = null;
  }
  function render(focus = true) {
    flying = false;
    stopBlink();
    map?.destroy();
    map = null;
    app.innerHTML = `<main class="ns-game" data-scene="${scene}" data-motion="${motion ? "on" : "off"}"><div class="ns-backdrop" aria-hidden="true"><img src="${window.NIGHTSHIFT_ART.room}" alt=""></div><div class="ns-atmosphere" aria-hidden="true"><span></span><span></span><span></span></div>${header()}<div class="ns-stage">${{ welcome, intro, room, sky, observe, review, board }[scene]()}</div><div class="ns-toast" aria-hidden="true"></div><footer class="ns-footer"><span>Настоящие снимки ZTF · архивные наблюдения</span><a href="?archive=1">Классический архив</a></footer></main>`;
    if (scene === "sky")
      map = new SkyMap(document.querySelector("#ns-map"), {
        cases: s.cases,
        selected: s.current.id,
        statuses: statuses(),
        motion: motion ? "animated" : "instant",
        onSelect: selectField,
      });
    if (focus) {
      const h = app.querySelector("h1");
      h?.setAttribute("tabindex", "-1");
      h?.focus({ preventScroll: true });
      window.scrollTo({ top: 0, behavior: "instant" });
    }
  }
  function go(next) {
    flying = false;
    scene = next;
    render();
  }
  function selectField(id) {
    if (flying) return;
    s.select(id);
    ui = {
      epoch: 0,
      tool: "mark",
      zoom: 1,
      measure: false,
      cursor: { x: 0.5, y: 0.5 },
    };
    map?.update({ selected: id, statuses: statuses() });
    const panel = document.querySelector("#ns-field-panel");
    if (panel) panel.innerHTML = fieldPanel();
    app
      .querySelectorAll('[data-ns="field"]')
      .forEach((el) =>
        el.setAttribute("aria-pressed", el.dataset.value === id),
      );
  }
  function updateFrame() {
    const wrap = app.querySelector(".ns-image-wrap");
    if (!wrap) return;
    wrap.dataset.epoch = ui.epoch;
    wrap.innerHTML = framePlane(s.current);
    app.querySelector("#ns-frame-label").textContent = `Кадр ${ui.epoch + 1}`;
    app.querySelector("#ns-frame-date").textContent = stamp(
      s.current,
      ui.epoch,
    );
    app
      .querySelectorAll('[data-ns="epoch"]')
      .forEach((el) =>
        el.setAttribute("aria-pressed", Number(el.dataset.value) === ui.epoch),
      );
  }
  function resetUI() {
    ui = {
      epoch: 0,
      tool: "mark",
      zoom: 1,
      measure: false,
      cursor: { x: 0.5, y: 0.5 },
    };
  }
  app.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-ns]");
    if (!button || button.disabled) return;
    const action = button.dataset.ns,
      v = button.dataset.value;
    if (action === "motion") {
      motion = !motion;
      render(false);
      app.querySelector('[data-ns="motion"]')?.focus();
      return;
    }
    if (action === "level") {
      level = Number(v);
      render(false);
      app.querySelector(`[data-ns="level"][data-value="${v}"]`)?.focus();
      return;
    }
    if (action === "start") {
      s.reset(level);
      resetUI();
      go("intro");
      return;
    }
    if (action === "begin") {
      go("room");
      return;
    }
    if (["welcome", "room", "sky", "board"].includes(action)) {
      go(action);
      return;
    }
    if (action === "field") {
      selectField(v);
      return;
    }
    if (action === "observe") {
      go("observe");
      return;
    }
    if (action === "aim") {
      if (flying) return;
      flying = true;
      button.disabled = true;
      button.textContent = "Наводим телескоп…";
      const activeMap = map;
      await activeMap?.flyTo(s.current.id);
      if (scene === "sky" && map === activeMap) {
        flying = false;
        go("observe");
      }
      return;
    }
    if (action === "epoch") {
      stopBlink();
      ui.epoch = Number(v);
      updateFrame();
      const bt = app.querySelector('[data-ns="blink"]');
      bt.textContent = "▶ Чередовать";
      bt.setAttribute("aria-pressed", "false");
      return;
    }
    if (action === "blink") {
      if (blink) stopBlink();
      else
        blink = setInterval(() => {
          ui.epoch = (ui.epoch + 1) % (s.hasThird(s.current.id) ? 3 : 2);
          updateFrame();
        }, 900);
      button.textContent = blink ? "Ⅱ Остановить" : "▶ Чередовать";
      button.setAttribute("aria-pressed", !!blink);
      return;
    }
    if (action === "zoom") {
      ui.zoom = ui.zoom === 1 ? 2 : 1;
      button.textContent = `⌕ Увеличение ×${ui.zoom}`;
      button.setAttribute("aria-pressed", ui.zoom === 2);
      updateFrame();
      return;
    }
    if (action === "measure") {
      ui.measure = !ui.measure;
      button.setAttribute("aria-pressed", ui.measure);
      app.querySelector("#ns-measurements").hidden = !ui.measure;
      return;
    }
    if (action === "predict") {
      s.predict(s.current.id, v);
      render(false);
      app.querySelector(`[data-ns="predict"][data-value="${v}"]`)?.focus();
      announce(
        "Наблюдение записано. Теперь можно запросить кадр или передать вывод.",
      );
      return;
    }
    if (action === "request") {
      if (s.request(s.current.id)) {
        ui.epoch = 2;
        render(false);
        app.querySelector('[data-ns="epoch"][data-value="2"]')?.focus();
        announce("Третий архивный кадр открыт.");
      }
      return;
    }
    if (action === "verdict") {
      s.decide(s.current.id, v);
      s.reveal(s.current.id);
      go("review");
      return;
    }
    if (action === "revise") {
      go("observe");
      return;
    }
    if (action === "next") {
      const id = s.nextId();
      if (id) {
        s.select(id);
        resetUI();
        go("sky");
      } else go("board");
      return;
    }
    if (action === "open-card") {
      s.select(v);
      resetUI();
      go(s.note(v).revealed ? "review" : "sky");
      return;
    }
    if (action === "restart") {
      if (confirm("Начать новую смену? Текущий отчёт будет очищен.")) {
        s.reset(level);
        resetUI();
        go("welcome");
      }
      return;
    }
  });
  app.addEventListener("pointerdown", (event) => {
    const wrap = event.target.closest(".ns-image-wrap");
    if (!wrap || event.button !== 0) return;
    stopBlink();
    const rect = wrap.querySelector(".ns-image-plane").getBoundingClientRect();
    const x = Math.max(
        0,
        Math.min(1, (event.clientX - rect.left) / rect.width),
      ),
      y = Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height));
    ui.cursor = { x, y };
    s.mark(s.current.id, ui.epoch, x, y);
    updateFrame();
    wrap.focus({ preventScroll: true });
    const bt = app.querySelector('[data-ns="blink"]');
    bt.textContent = "▶ Чередовать";
    bt.setAttribute("aria-pressed", "false");
    announce(`Отметка сохранена на кадре ${ui.epoch + 1}.`);
  });
  app.addEventListener("keydown", (event) => {
    if (!event.target.matches(".ns-image-wrap")) return;
    if (
      [
        "ArrowLeft",
        "ArrowRight",
        "ArrowUp",
        "ArrowDown",
        "Enter",
        " ",
      ].includes(event.key)
    ) {
      stopBlink();
      const button = app.querySelector('[data-ns="blink"]');
      button.textContent = "▶ Чередовать";
      button.setAttribute("aria-pressed", "false");
    }
    const delta = {
      ArrowLeft: [-0.015, 0],
      ArrowRight: [0.015, 0],
      ArrowUp: [0, -0.015],
      ArrowDown: [0, 0.015],
    }[event.key];
    if (delta) {
      event.preventDefault();
      ui.cursor.x = Math.max(0, Math.min(1, ui.cursor.x + delta[0]));
      ui.cursor.y = Math.max(0, Math.min(1, ui.cursor.y + delta[1]));
      updateFrame();
    }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      s.mark(s.current.id, ui.epoch, ui.cursor.x, ui.cursor.y);
      updateFrame();
      announce(`Отметка сохранена на кадре ${ui.epoch + 1}.`);
    }
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      stopBlink();
      const bt = app.querySelector('[data-ns="blink"]');
      if (bt) {
        bt.textContent = "▶ Чередовать";
        bt.setAttribute("aria-pressed", "false");
      }
    }
  });
  render(false);
})();
