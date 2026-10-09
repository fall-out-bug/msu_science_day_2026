"use strict";
(() => {
  if (new URLSearchParams(location.search).get("archive") !== "1") return;
  document.body.dataset.experience = "archive";
  const D = window.GAME_DATA,
    C = window.GAME_CONTENT;
  const app = document.querySelector("#app"),
    dialog = document.querySelector("#dialog");
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
  const fmt = (n) => Number(n).toFixed(2).replace(".", ",");
  window.game = new GameSession(D, "full");
  let welcome = true,
    map = null,
    blink = null,
    lastFocus = null,
    announcement;
  let ui = { tool: "pair", pair: [0, 1], epoch: 0, split: 50, revising: false };
  const current = () => game.cases.find((c) => c.id === game.state.focus);
  const checked = (c) => game.state.checked.includes(c.id);
  const thirdAvailable = (c) => game.hasThirdFrame(c.id);
  const status = (c) =>
    game.state.decisions[c.id]
      ? "decided"
      : checked(c)
        ? "checked"
        : game.state.predictions[c.id]
          ? "noticed"
          : "new";
  const statusLabel = (c) =>
    ({
      new: "Ещё не исследован",
      noticed: "Первое впечатление записано",
      checked: "Третий снимок получен",
      decided: "Версия сохранена",
    })[status(c)];
  const statuses = () =>
    Object.fromEntries(game.cases.map((c) => [c.id, status(c)]));
  const button = (action, label, value = "", extra = "") =>
    `<button data-action="${action}" ${value !== "" ? `data-value="${esc(value)}"` : ""} ${extra}>${label}</button>`;
  const sourceLink = (label, url) =>
    `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a>`;
  const dateFormat = new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium", timeStyle: "medium", timeZone: "UTC",
  });
  const coordinates = (c) =>
    `α ${Number(c.ra).toFixed(4)}° · δ ${Number(c.dec).toFixed(4)}° · ICRS`;
  function observationLabel(c, epoch) {
    const o = c.observations[epoch];
    return `${dateFormat.format(new Date(o.date))} UTC · фильтр ${o.filter}`;
  }
  function skyContext(c) {
    const region = c.skyContext;
    return `<details class="field-context"><summary>Где мы на небе · ${esc(region.constellation.name)}</summary>
      <p>${esc(region.intro)}</p><p class="quiet">${esc(region.scaleNote)}</p>
      <p><b>Попробуйте заметить.</b> ${esc(region.lookFor)}</p>
      <details><summary>Об этой области неба</summary><ul>${region.sources.map(([label, url]) => `<li>${sourceLink(label, url)}</li>`).join("")}</ul><p class="quiet">Рассказ сохранён в игре. Ссылки на источники открываются с интернетом.</p></details></details>`;
  }
  function observationDetails(c, revealAll = false) {
    const available = revealAll || thirdAvailable(c) ? [0, 1, 2] : [0, 1];
    return `${skyContext(c)}<details class="observation-source"><summary>Когда и как снято · ${esc(coordinates(c))}</summary>
      <p>Это снимки обзора ZTF: телескоп в Паломарской обсерватории возвращается к одним и тем же областям неба, чтобы искать изменения.</p>
      <p>Все даты указаны по всемирному времени UTC, не по местным часам. Фильтр r пропускает красную часть видимого света; цвет наших изображений условный.</p>
      <p>${sourceLink(c.source.label, c.source.url)}</p>
      <ol>${available.map((e) => {
        const o = c.observations[e];
        return `<li><b>Кадр ${e + 1}:</b> ${esc(observationLabel(c, e))} · экспозиция ${esc(o.exposure)} с
          ${sourceLink("Исходные данные", o.source)}</li>`;
      }).join("")}</ol>
      <p>α — прямое восхождение, δ — склонение: координаты направления на небе, похожие на долготу и широту на земной карте. Здесь они даны в градусах, в системе ICRS.</p>
      <details><summary>Обработка снимков и благодарности обзору</summary><p>${esc(D.meta.display.note)}</p><p class="attribution">${esc(c.source.credit)}</p></details>
      </details>`;
  }
  const timeText = () => {
    const t = Math.floor(game.elapsed() / 1000);
    return `${Math.floor(t / 60)
      .toString()
      .padStart(2, "0")}:${(t % 60).toString().padStart(2, "0")}`;
  };
  function announce(text) {
    const node = document.querySelector("#announce");
    node.textContent = text;
    clearTimeout(announcement);
    announcement = setTimeout(() => (node.textContent = ""), 3500);
  }
  function header() {
    return `<header class="topbar"><a class="brand" href="#app" aria-label="Архив неизвестного"><svg viewBox="0 0 48 48" aria-hidden="true"><circle cx="24" cy="24" r="17"/><ellipse cx="24" cy="24" rx="23" ry="8" transform="rotate(-35 24 24)"/><circle cx="35" cy="11" r="3"/></svg><span>АРХИВ<br><b>НЕИЗВЕСТНОГО</b></span></a><div class="session-label">НАУКА 0+ <span>КОСМИЧЕСКОЕ ДЕТЕКТИВНОЕ АГЕНТСТВО</span></div><div class="top-actions">${button("stories", "ИИ в астрономии")}${button("presenter", "Ведущему")}${!welcome ? button("new-group", "Новая группа") : ""}</div></header>`;
  }
  const footer = () =>
    `<footer class="footer"><span>Настоящие наблюдения · Оценки рассчитаны заранее</span><span>Необычность — повод проверить, а не объявить открытие</span></footer>`;
  function landing() {
    return `<section class="welcome"><div class="welcome-copy">
      <p class="eyebrow">ОХОТА ЗА ЗВЁЗДНЫМИ АНОМАЛИЯМИ</p>
      <h1>В небе что-то<br><em>изменилось.</em></h1>
      <p class="lead">Перед вами два снимка одного кусочка неба. Между ними прошло время. Удастся заметить, что изменилось?</p>
      <p>Это настоящие кадры телескопа. Сравните их, обсудите свою догадку и решите, нужен ли третий снимок. Можно спросить алгоритм — но последнее слово останется за вами.</p>
      <div class="start-options">${button("start-full", "<strong>Открыть смену →</strong><span>12 участков · 3 заявки · 15–20 минут</span>", "", 'class="primary start-button"')}${button("start-short", "<strong>Быстрое расследование</strong><span>6 участков · 1 заявка · 5–7 минут</span>", "", 'class="start-button"')}</div>
      <p class="quiet">Для одного исследователя или пары. Снимки и данные уже на этом устройстве; интернет не нужен.</p>
      </div><figure class="atlas-preview"><img class="atlas-background" src="${window.SKY_DATA.texture}" alt="Млечный Путь на координатной карте звёзд NASA">
      <div class="archive-previews">${D.contact.slice(0, 2).map(c => `<figure><img src="${c.frames[0]}" alt="Архивный снимок ${esc(c.name)}"><figcaption>${esc(c.name)}<br>${esc(observationLabel(c, 0))}</figcaption></figure>`).join("")}</div>
      <figcaption>ЗВЁЗДНАЯ КАРТА · NASA SVS<br><span>Карта составлена по каталогам звёзд. Маленькие вставки — снимки телескопа ZTF.</span></figcaption></figure></section>`;
  }
  function briefing() {
    return `<section class="briefing panel"><p class="eyebrow">${game.state.mode === "full" ? "ПОЛНАЯ" : "КОРОТКАЯ"} СМЕНА · ПЕРЕД СТАРТОМ</p><h1>Посмотрите.<br>Сравните. Обсудите.</h1><p class="lead">Звёздная точка стала ярче? Сдвинулась? Или изменился сам снимок? Попробуем разобраться по настоящим наблюдениям.</p><ol class="brief-steps"><li><b>Заметьте</b><span>Выберите участок на карте или карточку. Сравните два кадра. Сначала просто запишите, видите ли вы различие: объяснять его пока не нужно.</span></li><li><b>Проверьте</b><span>У вас ${game.budget} ${game.budget === 1 ? "заявка" : "заявки"} на третьи снимки. Решите, где ещё один кадр поможет больше всего. Подсказки алгоритма бесплатны.</span></li><li><b>Объясните</b><span>Выберите версию. Не уверены? Ответ «Недостаточно данных» здесь уместен. В конце вместе посмотрим, что известно об этих объектах.</span></li></ol><p>Играете вдвоём? Один ищет различия, другой придумывает, как проверить догадку. Потом поменяйтесь.</p>${button("begin", "Начать исследование →", "", 'class="primary"')}<p class="quiet">Все снимки уже лежат в архиве игры. Заявка открывает ещё один из них, а не отправляет команду телескопу.</p></section>`;
  }
  function missionBar() {
    return `<section class="mission-strip"><div><span class="eyebrow">${game.state.mode === "full" ? "ПОЛНАЯ" : "КОРОТКАЯ"} СМЕНА</span><h1>${game.state.page === "inspect" ? esc(current().name) : game.state.page === "results" ? "Научный совет" : "Атлас наблюдений"}</h1></div><div class="mission-stats"><span><b>${Object.keys(game.state.decisions).length} / ${game.cases.length}</b>версий записано</span><span><b id="remaining">${game.remaining}</b>заявок осталось</span><span><b id="timer">${timeText()}</b>время смены</span></div></section>`;
  }
  function navigation() {
    return `<nav class="view-tabs" aria-label="Способ навигации">${button("nav-map", "Карта неба", "", `aria-pressed="${game.state.view === "map"}"`)}${button("nav-cards", "Карточки", "", `aria-pressed="${game.state.view === "cards"}"`)}<p>Выбирайте, как удобнее искать. При переключении ответы сохранятся.</p></nav>`;
  }
  function overview() {
    const c = current();
    return `${missionBar()}${navigation()}<div class="overview-grid">
      <section class="panel navigator">${game.state.view === "map" ? '<div id="map-host"></div>' : `<div id="cards">${game.cases.map((p, i) => `<button class="sector-card ${p.id === c.id ? "selected" : ""}" data-action="select" data-id="${p.id}" aria-label="${esc(p.name)}. ${statusLabel(p)}"><span class="card-number">${String(i + 1).padStart(2, "0")}</span><img src="${p.frames[0]}" alt="Первый снимок: ${esc(p.name)}"><strong>${esc(p.name)}</strong><small>${esc(coordinates(p))}</small><span class="card-status">${statusLabel(p)}</span></button>`).join("")}</div>`}</section>
      <aside class="panel route-panel"><div><p class="eyebrow">ВЫБРАННЫЙ УЧАСТОК</p><h2>${esc(c.name)}</h2><p>Созвездие: <strong>${esc(c.skyContext.constellation.name)}</strong></p><p class="coordinates">${esc(coordinates(c))}</p></div>
      <div class="selected-preview"><img src="${c.frames[0]}" alt="${esc(c.name)}"><div><p>${statusLabel(c)}</p><p class="quiet">${esc(c.skyContext.lookFor)}</p></div></div>
      <div class="route-actions">${button("observe", "Сравнить снимки →", "", 'class="primary"')}${button("finish", "Итоги и разбор", "", 'class="quiet-button"')}</div></aside></div>`;
  }
  function comparisons(c) {
    const available = thirdAvailable(c) ? [0, 1, 2] : [0, 1];
    const pairs = thirdAvailable(c)
      ? [
          [0, 1],
          [0, 2],
          [1, 2],
        ]
      : [[0, 1]];
    return `<div class="comparison-tools"><div class="instrument-modes">${[
      ["pair", "Два рядом"],
      ["single", "По одному"],
      ["compare", "Ползунок"],
      ["blink", "Чередовать кадры"],
    ]
      .map(([value, label]) =>
        button(
          "tool",
          label,
          value,
          `aria-pressed="${ui.tool === value}"`,
        ),
      )
      .join(
        "",
      )}</div><div class="frame-tools"><span>${ui.tool === "single" ? "Показать снимок:" : "Сравнить снимки:"}</span>${ui.tool === "single" ? available.map((e) => button("epoch", String(e + 1), e, `aria-pressed="${ui.epoch === e}"`)).join("") : pairs.map((p) => button("pair", `${p[0] + 1} и ${p[1] + 1}`, p.join(","), `aria-pressed="${ui.pair.join(",") === p.join(",")}"`)).join("")}${button("hint", "Спросить алгоритм <small>необязательно</small>", "", 'class="hint-button"')}</div></div>`;
  }
  function photographs(c) {
    const [a, b] = ui.pair;
    if (ui.tool === "pair")
      return `<div class="photo-pair">${[a, b].map((e) => `<figure><img src="${c.frames[e]}" alt="${esc(c.name)}: снимок ${e + 1}"><figcaption><b>Кадр ${e + 1}</b><span>${esc(observationLabel(c, e))}</span></figcaption></figure>`).join("")}</div>`;
    const epoch = ui.tool === "single" ? ui.epoch : ui.tool === "compare" ? b : a;
    return `<div class="scope ${ui.tool}" style="--split:${ui.split}%">
      <div class="scope-label">${ui.tool === "compare" ? `КАДРЫ ${a + 1} И ${b + 1}` : `КАДР <span id="blink-epoch">${epoch + 1}</span>`}</div>
      <div class="image-window"><img class="base-image" src="${c.frames[epoch]}" alt="${esc(c.name)}: снимок ${epoch + 1}">
      ${ui.tool === "compare" ? `<img class="overlay-image" src="${c.frames[a]}" alt="${esc(c.name)}: снимок ${a + 1}"><span class="divider" aria-hidden="true"></span><span class="image-tag tag-left">${a + 1}</span><span class="image-tag tag-right">${b + 1}</span>` : ""}</div></div>
      <p class="frame-dates">${(ui.tool === "single" ? [epoch] : [a, b]).map(e => `<span><b>Кадр ${e + 1}</b> · ${esc(observationLabel(c, e))}</span>`).join("")}</p>
      ${ui.tool === "compare" ? `<label class="range-label">Граница между кадрами<input id="comparison" type="range" min="0" max="100" value="${ui.split}" aria-label="Граница между снимками"><output id="split-output">${ui.split}%</output></label>` : ""}`;
  }
  function investigation() {
    const c = current(),
      prediction = game.state.predictions[c.id],
      decision = game.state.decisions[c.id];
    const canChoose = prediction && (!decision || ui.revising);
    return `${missionBar()}${navigation()}<div class="investigation-grid"><section id="inspection" class="panel observation"><div class="panel-heading"><span class="eyebrow">УЧАСТОК ${game.cases.indexOf(c) + 1} ИЗ ${game.cases.length}</span>${button("zoom", "Увеличить снимок")}</div><div class="question"><p class="eyebrow">${!prediction ? "1 · ВАШЕ НАБЛЮДЕНИЕ" : thirdAvailable(c) ? "3 · ВАША ВЕРСИЯ" : "2 · НУЖНА ЛИ ПРОВЕРКА?"}</p><h2>${!prediction ? "Что изменилось между кадрами?" : thirdAvailable(c) ? "Что добавил третий кадр?" : "Какую догадку стоит проверить?"}</h2><p>${!prediction ? "Присмотритесь к светлым точкам: все ли остались на своих местах, все ли светят так же? Сравните и соседние точки: они тоже изменились?" : thirdAvailable(c) ? "Теперь снимков три. Ваша догадка по-прежнему подходит? Посмотрите на даты: между кадрами могли пройти часы, месяцы или годы." : "Поможет ли третий снимок выбрать между версиями? Можно потратить заявку — или пока ответить по двум кадрам. Если уверенности нет, так и ответьте."}</p></div>${game.isRevealed(c.id) ? '<p class="receipt review-notice">Разбор этого участка уже открыт. Следующие версии будут уточнениями после знакомства с ответом.</p>' : ""}${comparisons(c)}${photographs(c)}<p class="image-help">${ui.tool === "compare" ? "Двигайте границу: слева и справа от неё видны разные кадры." : ui.tool === "blink" ? "Снимки чередуются: так легче заметить движение или перемену яркости. Остановить можно кнопкой «Два рядом» или «По одному»." : "Можно увеличить снимок, чтобы рассмотреть его удобнее. Новых деталей от увеличения не появится."}</p>${observationDetails(c)}<section class="flow-actions" tabindex="-1">${
      !prediction
        ? `<div class="choice-row">${Object.entries(C.observations)
            .map(([v, l]) => button("predict", l, v))
            .join(
              "",
            )}</div><p class="quiet">Это первое впечатление. Объяснение будем выбирать отдельно.</p>`
        : `<p class="receipt">Первое впечатление: <strong>${C.observations[prediction]}</strong> ${button("edit-prediction", "Изменить", "", 'class="text-button"')}</p><div class="evidence-request">${button("request", thirdAvailable(c) ? "Третий снимок открыт" : game.remaining ? `Получить третий снимок · 1 заявка` : "Все заявки использованы", "", `${thirdAvailable(c) ? "" : 'class="primary"'} ${!thirdAvailable(c) && !game.remaining ? "disabled" : ""}`)}<span>${thirdAvailable(c) ? (game.isRevealed(c.id) && !checked(c) ? "Кадр открыт в разборе; заявка не потрачена." : "Повторный просмотр бесплатный.") : `Осталось ${game.remaining} из ${game.budget}.`}</span></div>${
            canChoose
              ? `<h3>Какое объяснение оставим?</h3><div class="verdicts">${Object.entries(
                  C.verdicts,
                )
                  .map(([v, l]) =>
                    button(
                      "decide",
                      `<strong>${l}</strong><span>${C.meanings[v]}</span>`,
                      v,
                      `aria-pressed="${decision === v}"`,
                    ),
                  )
                  .join("")}</div>`
              : `<p class="receipt saved">Версия сохранена: <strong>${C.verdicts[decision]}</strong></p><div class="flow-buttons">${button("review-case", game.isRevealed(c.id) ? "Открыть разбор ещё раз" : "Что показали наблюдения?", "", game.nextCaseId() ? 'class="primary"' : "")}${button("next", game.nextCaseId() ? "Следующий участок →" : "Посмотреть итоги →", "", game.nextCaseId() ? "" : 'class="primary"')}${button("revise", "Пересмотреть версию")}</div><p class="quiet">${game.isRevealed(c.id) ? "Разбор уже открыт. Вы можете уточнить свою версию; исходная сохранится рядом с ней." : "Разбор раскроет ответ и третий кадр только этого участка. Остальные дела останутся для вашего исследования."}</p>`
          }`
    }</section></section><aside class="panel investigation-aside"><p class="eyebrow">МАРШРУТ ИССЛЕДОВАНИЯ</p><ol class="route-steps"><li class="${prediction ? "done" : ""}"><b>1</b><span>Сравните два снимка<small>Запишите своё впечатление</small></span></li><li class="${thirdAvailable(c) ? "done" : ""}"><b>2</b><span>Выберите проверку<small>${checked(c) ? "Третий кадр открыт по заявке" : game.isRevealed(c.id) ? "Третий кадр открыт в разборе" : "Третий кадр — за заявку"}</small></span></li><li class="${decision ? "done" : ""}"><b>3</b><span>Сохраните версию<small>Не уверены? Это тоже ответ</small></span></li></ol><p>Алгоритм можно вызвать в любой момент. Его высокая оценка не доказывает, что перед вами открытие.</p><div class="aside-actions">${button("back", game.state.view === "map" ? "Вернуться к карте" : "Вернуться к карточкам")}${button("finish", "Итоги и разбор")}${button("stories", "Как ИИ помогает настоящей астрономии →", "", 'class="story-teaser"')}</div></aside></div>`;
  }
  function caseMeasurements(c) {
    const epochs = c.photometry?.epochs;
    if (!epochs || epochs.length !== 3 || c.type === "mover") return "";
    let rows = [], reference = 0;
    if (epochs.every(e => Array.isArray(e.source_fluxes) && e.source_fluxes.length === epochs[0].source_fluxes.length)) {
      rows = epochs[0].source_fluxes.map((flux, i) => ({
        label: `Контрольная звезда ${i + 1}`,
        values: epochs.map(e => flux > 0 ? 100 * e.source_fluxes[i] / flux : null),
      }));
    } else if (epochs.every(e => Number.isFinite(e.mag))) {
      rows = [{ label: "Источник", values: epochs.map(e => 100 * 10 ** (-0.4 * (e.mag - epochs[0].mag))) }];
    } else if (epochs.some(e => Number.isFinite(e.mag_diff))) {
      reference = epochs.findIndex(e => Number.isFinite(e.mag_diff));
      rows = [{ label: "Изменяющаяся часть света", values: epochs.map(e => Number.isFinite(e.mag_diff) ? 100 * 10 ** (-0.4 * (e.mag_diff - epochs[reference].mag_diff)) : null) }];
    }
    if (!rows.length) return "";
    return `<div class="case-measurements"><table><caption>Сравнение измерений яркости</caption>
      <thead><tr><th scope="col">Что измерено</th>${epochs.map((_, i) => `<th scope="col">Кадр ${i + 1}</th>`).join("")}</tr></thead>
      <tbody>${rows.map(row => `<tr><th scope="row">${row.label}</th>${row.values.map(v => `<td>${Number.isFinite(v) ? `${v.toFixed(1).replace(".", ",")}%` : '<span aria-label="Нет измерения">—</span>'}</td>`).join("")}</tr>`).join("")}</tbody></table>
      <p class="quiet">Количество света в кадре ${reference + 1} принято за 100% для каждого источника. Это измерения света, а не яркости одного пикселя. Прочерк означает отсутствие измерения.</p>
      <details><summary>Как измерялся свет</summary><p>${esc(c.photometry.note)}</p></details></div>`;
  }
  function caseReview(c, expanded = false) {
    const decision = game.state.decisions[c.id];
    const before = game.state.revealed[c.id];
    return `<article class="panel result-card" data-case-id="${esc(c.id)}">
      <div class="panel-heading"><h3>${esc(c.name)}</h3><span class="score">${fmt(c.score)} · АЛГОРИТМ</span></div>
      <p>Ваша версия до разбора: <strong>${before ? C.verdicts[before] : "не записана"}</strong></p>
      ${decision && decision !== before ? `<p>Уточнённая версия: <strong>${C.verdicts[decision]}</strong></p>` : ""}
      ${before === "uncertain" ? '<p class="quiet">Вы оставили вопрос открытым. Сравним доступные вам снимки с дополнительными измерениями.</p>' : ""}
      <div class="result-photos">${c.frames.map((src, e) => `<figure><img src="${src}" alt="${esc(c.name)}, снимок ${e + 1}"><figcaption><b>Кадр ${e + 1}</b><br>${esc(observationLabel(c, e))}</figcaption></figure>`).join("")}</div>
      <h4>${C.types[c.type]}</h4><p>${esc(c.explanation)}</p>
      ${caseMeasurements(c)}
      <details class="case-evidence" ${expanded ? "open" : ""}><summary>На чём основан разбор?</summary><p>${esc(c.evidence)}</p><h4>Чего мы не знаем</h4><p>${esc(c.limitations)}</p></details>
      <p class="case-algorithm"><b>Что сообщил алгоритм.</b> Оценка ${fmt(c.score)}: ${c.score >= 3 ? "участок проходит пороги 1 и 3" : c.score >= 1 ? "участок проходит порог 1, но не порог 3" : "участок ниже обоих порогов — 1 и 3"}.
      ${c.expectedVerdict === "sky" && c.score < 1 ? "Измерения подтверждают изменение, которое этот детектор пропустил." : c.expectedVerdict === "artifact" && c.score >= 1 ? "Необычным оказался кадр с помехой. Высокая оценка не устанавливает природу различия." : "Оценка описывает необычность; вывод об объекте основан на наблюдениях и проверке."}</p>
      ${observationDetails(c, true)}
      <p class="quiet">${checked(c) ? "Третий кадр был открыт по вашей заявке." : "Третий кадр открыт в разборе; заявка не потрачена."} Теперь все три снимка доступны в инструментах сравнения. Версию можно уточнить.</p></article>`;
  }
  function finish() {
    if (dialog.open) dialog.close();
    game.revealAll();
    game.pauseTimer();
    game.state.page = "results";
    render(true);
  }
  function openResults() {
    const unanswered = game.cases.filter(c => !game.state.decisions[c.id]).length;
    if (unanswered && game.cases.some(c => !game.isRevealed(c.id))) {
      showDialog("Открыть ответы всех участков?",
        `<p>Без вашей версии осталось участков: ${unanswered} из ${game.cases.length}.</p><p>«Итоги и разбор» откроет объяснения и третьи снимки всей смены, включая ещё не исследованные участки. Можно вернуться к игре и уточнять версии после разбора.</p><div class="flow-buttons">${button("confirm-finish", "Открыть все ответы", "", 'class="primary"')}${button("close-dialog", "Продолжить исследование")}</div>`);
    } else finish();
  }
  function results() {
    const r = game.results();
    return `${missionBar()}<section class="council-intro"><p class="eyebrow">НАУЧНЫЙ СОВЕТ</p>
      <h2>Что говорят<br><em>наблюдения?</em></h2>
      <p>Сравним ваши догадки с тем, что удалось измерить. Для каждого участка есть рассказ: что мы видим, чем это подтверждается и какие вопросы ещё остаются.</p></section>
      <section id="summary" class="summary-grid">${[
        ["found", "Изменений найдено", "Изменение подтверждено, и ваша текущая версия — «изменился сам объект»"],
        ["missed", "Изменений пропущено", "Изменение подтвердилось, но ваша версия была другой — или вы ещё не дошли до этого участка"],
        ["artifacts", "Помех распознано", "Ваша текущая версия совпала с подтверждённой помехой на снимке"],
        ["extra", "Проверок спокойных полей", "Столько заявок ушло на поля без заметных изменений. Проверить догадку — не ошибка"],
      ].map(([key, label, note]) => `<div class="panel"><b data-count="${key}">${r[key]}</b><h3>${label}</h3><p>${note}</p></div>`).join("")}</section>
      <p class="quiet">Счётчики отражают текущие версии, включая уточнения после разбора. Версия до раскрытия сохранена у каждого участка. Общего балла нет. Участки с неустановленным объяснением не входят в счётчики доказанных изменений и помех. Слабое изменение учитывается, если его подтверждают измерения.</p>
      <p class="quiet">Участков без вашей версии: ${game.cases.filter(c => !game.state.decisions[c.id]).length} из ${game.cases.length}. Они тоже входят в общий разбор.</p>
      <section class="result-grid">${game.cases.map(c => caseReview(c)).join("")}</section>
      <section class="panel closing"><h2>А что проверим дальше?</h2><p>Выберите участок, о котором хочется узнать больше. Хватит ли ещё одного снимка? Может, нужно точнее измерить яркость или разложить свет в спектр, чтобы узнать состав и движение объекта? Обсудите, какое наблюдение поможет отличить ваши версии.</p>
      <div class="flow-buttons">${button("stories", "От наблюдения к открытию")}${button("back", "Вернуться к исследованию")}${button("new-group", "Новая группа", "", 'class="primary"')}</div></section>`;
  }
  function render(focus = false) {
    if (map) {
      map.destroy();
      map = null;
    }
    clearInterval(blink);
    blink = null;
    app.innerHTML = `${header()}<main id="main" tabindex="-1">${welcome ? landing() : game.state.page === "briefing" ? briefing() : game.state.page === "overview" ? overview() : game.state.page === "inspect" ? investigation() : results()}</main>${footer()}`;
    if (!welcome && game.state.page === "overview" && game.state.view === "map")
      map = new SkyMap(document.querySelector("#map-host"), {
        cases: game.cases,
        selected: game.state.focus,
        statuses: statuses(),
        onSelect: choose,
      });
    if (
      !welcome &&
      game.state.page === "inspect" &&
      ui.tool === "blink"
    ) {
      let e = ui.pair[0];
      blink = setInterval(() => {
        if (document.hidden || dialog.open) return;
        e = e === ui.pair[0] ? ui.pair[1] : ui.pair[0];
        const img = document.querySelector(".base-image");
        if (!img) return;
        img.src = current().frames[e];
        img.alt = `${current().name}: снимок ${e + 1}`;
        document.querySelector("#blink-epoch").textContent = e + 1;
      }, 850);
    }
    if (focus) {
      document.querySelector("#main").focus({ preventScroll: true });
      window.scrollTo({ top: 0, behavior: "instant" });
    }
  }
  function resetInstrument() {
    ui = {
      tool: "pair",
      pair: thirdAvailable(current()) ? [1, 2] : [0, 1],
      epoch: 0,
      split: 50,
      revising: false,
    };
  }
  async function choose(id) {
    game.select(id);
    resetInstrument();
    const activeMap = map;
    if (activeMap) {
      activeMap.update({ selected: id, statuses: statuses() });
      await activeMap.flyTo(id);
      if (map !== activeMap) return;
    }
    game.state.page = "inspect";
    render(true);
  }
  function showDialog(title, html, kind = "") {
    lastFocus = dialog.open ? lastFocus : document.activeElement;
    dialog.className = kind;
    dialog.innerHTML = `<div class="dialog-heading"><h2 id="dialog-title" tabindex="-1">${title}</h2>${button("close-dialog", "Закрыть")}</div><div class="dialog-body">${html}</div>`;
    if (!dialog.open) dialog.showModal();
    dialog.scrollTop = 0;
    document.querySelector("#dialog-title").focus({ preventScroll: true });
  }
  function hint() {
    const c = current();
    game.hint(c.id);
    const rank =
      [...game.cases]
        .sort((a, b) => b.score - a.score)
        .findIndex((p) => p.id === c.id) + 1;
    showDialog(
      "Другой взгляд — не готовый ответ",
      `<p class="eyebrow">${esc(c.name)} · РАСЧЁТ ПО СНИМКАМ</p><div class="hint-score"><b>${fmt(c.score)}</b><span>оценка необычности<br>${rank}-е место из ${game.cases.length}</span></div><p class="lead">${c.score >= 3 ? "Для алгоритма эта пара выглядит очень необычно. Но он ещё не знает, что перед ним: изменение в небе или помеха. Сверьте подсказку со снимками." : c.score >= 1 ? "Эта пара попала в список для проверки при мягком отборе. Какое различие вы видите сами — и чем его можно объяснить?" : "Алгоритм не выделил эту пару как необычную. Не торопитесь с выводом: он умеет замечать не всё. Если вы видите изменение, низкая оценка его не отменяет."}</p><p>Это <strong>не вероятность открытия</strong> и не ответ на вопрос «что случилось?». Алгоритм только сравнивает несколько чисел.</p><details><summary>Какие числа он сравнивает?</summary><p>Сначала мы взяли ${D.meta.training.n_rows} других участков неба. На них алгоритм узнал типичный размер различий между снимками: насколько сильно меняется свет в отдельных пикселях и сколько пикселей меняется заметно. Затем тем же способом оценили игровые участки. Это простой статистический детектор, не нейросеть.</p><p>Чем сильнее признаки отличаются от типичных, тем выше оценка. Наши игровые примеры не участвовали в обучении. Расчёт уже выполнен — кнопка показывает его результат.</p><details><summary>Формула и ограничения</summary><p>${esc(D.meta.score_formula)}</p><p>${esc(D.meta.training.limitations)}</p></details></details>`,
      "hint-dialog",
    );
  }
  function keplerPlot(averages) {
    const data = window.DISCOVERY_DATA.kepler90;
    const extent = averages ? 200 : 600;
    const x = h => 76 + (h + 12) / 24 * 650;
    const y = ppm => 175 - ppm / extent * 120;
    const marks = averages
      ? data.bins.map(([hour, flux, error, count]) => `<g><title>${hour} ч: ${flux} ppm ± ${error}; ${count} измерений</title><path d="M${x(hour)} ${y(flux - error)}V${y(flux + error)}" stroke="#d4b678"/><circle cx="${x(hour)}" cy="${y(flux)}" r="4" fill="#f8d48a"/></g>`).join("")
      : data.points.map(([hour, flux]) => `<circle cx="${x(hour)}" cy="${y(flux)}" r="1.8" fill="#95bbcf" opacity=".45"/>`).join("");
    return `<div class="plot-tools">${button("story-plot", "Отдельные измерения", "raw", `aria-pressed="${!averages}"`)}${button("story-plot", "Средние значения", "mean", `aria-pressed="${averages}"`)}</div>
      <figure class="lightcurve"><svg viewBox="0 0 770 350" role="img" aria-label="Измеренная яркость звезды Кеплер-90 по фазе орбиты Кеплер-90i. ${averages ? "Средние значения с ошибками: у нуля виден слабый провал яркости." : "Отдельные измерения с заметным разбросом."}">
      <defs><clipPath id="plot-clip"><rect x="76" y="55" width="650" height="240"/></clipPath></defs>
      ${[-extent, 0, extent].map(v => `<path d="M76 ${y(v)}H726" stroke="#3b5263" stroke-dasharray="4 5"/><text x="64" y="${y(v) + 5}" text-anchor="end">${v > 0 ? "+" : ""}${(v / 10000).toLocaleString("ru-RU")}%</text>`).join("")}
      ${[-12, -6, 0, 6, 12].map(h => `<text x="${x(h)}" y="325" text-anchor="middle">${h > 0 ? "+" : ""}${h}</text>`).join("")}
      <text x="76" y="23">Отклонение яркости от уровня вне транзита</text>
      <g clip-path="url(#plot-clip)">${marks}</g><text x="401" y="346" text-anchor="middle">Время относительно середины транзита, ч</text></svg>
      <figcaption>${averages ? "Средние за 30 минут. Вертикальные отрезки — стандартные ошибки среднего; масштаб по яркости увеличен втрое." : `${data.count.toLocaleString("ru-RU")} настоящих измерений, сложенных по периоду 14,44912 суток. Вертикальная шкала ограничена ±0,06%; выбросы за её пределами не показаны.`}</figcaption></figure>
      <p class="attribution">${esc(data.credit)} ${sourceLink("Архив измерений", data.source)}</p>
      <details><summary>Как построен график</summary><p>${esc(data.note)}</p></details>`;
  }
  function supernovaView(processed) {
    const data = window.DISCOVERY_DATA.sn2023tyk;
    const product = processed ? "difference" : "science";
    return `<div class="plot-tools">${button("story-process", "Кадры телескопа", "science", `aria-pressed="${!processed}"`)}${button("story-process", "Разность с опорным кадром", "difference", `aria-pressed="${processed}"`)}</div>
      <div class="photo-pair story-observations">${data.frames.map(frame => `<figure><div class="story-target"><img src="${frame[product]}" alt="SN 2023tyk в центре: ${esc(dateFormat.format(new Date(frame.date)))} UTC; ${processed ? "разность с опорным изображением" : "кадр телескопа"}"><span class="target-ring" aria-hidden="true"></span></div><figcaption>${esc(dateFormat.format(new Date(frame.date)))} UTC · r · 30 с</figcaption></figure>`).join("")}</div>
      <p>${processed ? "Постоянные источники в основном вычтены. В круге виден свет сверхновой: к ноябрю она стала слабее. Серый — нулевая разность, светлое — положительная, тёмное — отрицательная. Остатки у других звёзд показывают, что вычитание не идеально." : "Круг отмечает положение сверхновой. На обычных снимках её свет смешивается со светом соседнего источника. Переключите вид: вычитание более раннего опорного кадра помогает выделить изменение."}</p>
      <p class="attribution">${esc(data.credit)} · RA ${data.ra.toFixed(5)}°, Dec ${data.dec.toFixed(5)}° (ICRS).</p>
      <details><summary>Какие данные здесь показаны?</summary><p>${esc(data.note)}</p><ul>${data.frames.map(frame => `<li>${esc(dateFormat.format(new Date(frame.date)))} UTC: ${sourceLink("Кадр", frame.scienceSource)} · ${sourceLink("Разность ZTF", frame.differenceSource)}</li>`).join("")}</ul></details>`;
  }
  function stories(index = 0, averages = false) {
    const s = C.stories[index];
    const observation = s.kind === "kepler" ? keplerPlot(averages)
      : s.kind === "supernova" ? supernovaView(averages) : "";
    showDialog(
      "Где ИИ помогает астрономам",
      `<nav class="story-tabs" aria-label="Примеры ИИ в астрономии">${C.stories.map((p, i) => button("story", esc(p.tab), i, `aria-pressed="${index === i}"`)).join("")}</nav>
      <p class="eyebrow">${esc(s.year)} · ИЗ НАСТОЯЩИХ ИССЛЕДОВАНИЙ</p>
      <h2 class="story-title">${esc(s.title)}</h2><p class="lead">${esc(s.summary)}</p>${observation}
      <div class="story-evidence"><section><h3>Что сделал алгоритм</h3><p>${esc(s.ai)}</p></section><section><h3>Как проверяли результат</h3><p>${esc(s.evidence)}</p></section></div>
      <p class="quiet"><b>Где стоит быть осторожнее.</b> ${esc(s.caveat)}</p>
      <blockquote>${esc(s.connection)}</blockquote>
      <section class="story-discussion"><h3>Вопрос для вашей команды</h3><p>${esc(s.discussion)}</p></section>
      <details><summary>Откуда мы это знаем</summary><ul>${s.sources.map(([label, url]) => `<li>${sourceLink(label, url)}</li>`).join("")}</ul><p>Рассказ и показанные данные работают без сети. Интернет нужен только для перехода к первоисточникам.</p></details>`,
      "story-dialog",
    );
  }
  function real() {
    showDialog(
      "Из настоящих наблюдений",
      `<p>Эти изображения не участвовали в обучении или оценке нашей модели. Они показывают связь учебной задачи с астрономией.</p>${C.real.map((p) => `<article class="real-example"><h3>${p.title}</h3><img src="${p.image}" alt="${p.title}"><p class="attribution">${esc(p.credit)}</p><p class="quiet">${p.license} · ${sourceLink("Источник", p.source)}</p><p>${p.text}</p></article>`).join("")}`,
      "story-dialog",
    );
  }
  function rankingRows(cases) {
    return [...cases]
      .sort((a, b) => b.score - a.score)
      .map(
        (c) =>
          `<tr class="${c.score >= game.state.threshold ? "passes" : ""}"><td>${esc(c.name)}</td><td>${fmt(c.score)}</td><td>${c.score >= game.state.threshold ? "Отобран" : "Ниже порога"}</td></tr>`,
      )
      .join("");
  }
  function presenter() {
    showDialog(
      "Пульт ведущего",
      `<p>Здесь доступны разборы и архивные сведения. Откройте их группе после самостоятельного исследования.</p>
      <section class="presenter-timer"><strong data-timer>${timeText()}</strong>${button("timer-toggle", game.state.timerStartedAt === null ? "Запустить таймер" : "Пауза")}${button("timer-reset", "Сбросить таймер")}${button("new-group", "Новая группа")}</section>
      <section><h3>Порог отбора</h3><p>Выше порог — меньше кандидатов. Слабое изменение при этом может остаться без внимания. Порог меняет отбор, а не сами оценки.</p>
      <label class="range-label">Порог<input id="threshold" type="range" min="0.5" max="5" step="0.1" value="${game.state.threshold}"><output id="threshold-output">${fmt(game.state.threshold)}</output></label>
      <div class="flow-buttons">${button("threshold", "Мягкий · 1", 1)}${button("threshold", "Строгий · 3", 3)}</div><p id="ranking-count"></p>
      <details open><summary>Рейтинг текущей смены · рассчитан заранее</summary><table><thead><tr><th>Участок</th><th>Оценка</th><th>Отбор</th></tr></thead><tbody id="ranking">${rankingRows(game.cases)}</tbody></table></details>
      <details><summary>Расширенный набор · ${D.demo.length} участков</summary><p>Архивные наблюдения, обработанные тем же детектором. Оценки рассчитаны заранее. Этот экран не измеряет скорость алгоритма.</p>
      <table><thead><tr><th>Участок</th><th>Оценка</th><th>Отбор</th></tr></thead><tbody id="demo-ranking">${rankingRows(D.demo)}</tbody></table></details></section>
      <details><summary>Разборы всех участков смены</summary>${game.cases.map(c => `<section class="key-entry"><h4>${esc(c.name)} · ${C.types[c.type]}</h4><p>${esc(c.explanation)}</p><p><b>Основание:</b> ${esc(c.evidence)}</p><p><b>Ограничения:</b> ${esc(c.limitations)}</p>${observationDetails(c, true)}</section>`).join("")}</details>
      <details><summary>Сценарии ведущего</summary>${C.scenarios.map(s => `<h3>${s.title}</h3><ol>${s.steps.map(x => `<li>${x}</li>`).join("")}</ol>`).join("")}</details>
      <details><summary>Ответы на вопросы и правила итогов</summary>${C.faq.map(([q, a]) => `<h4>${q}</h4><p>${a}</p>`).join("")}</details>
      <div class="flow-buttons">${button("real", "Другие наблюдения")}${button("stories", "ИИ в астрономии")}</div>`,
      "presenter-dialog",
    );
    updateRanking();
  }
  function updateRanking() {
    const count = document.querySelector("#ranking-count");
    if (!count) return;
    document.querySelector("#threshold-output").textContent = fmt(
      game.state.threshold,
    );
    document.querySelector("#threshold").value = game.state.threshold;
    document.querySelector("#ranking").innerHTML = rankingRows(game.cases);
    document.querySelector("#demo-ranking").innerHTML = rankingRows(D.demo);
    count.textContent = `Отобрано ${game.cases.filter((c) => c.score >= game.state.threshold).length} из ${game.cases.length}; в расширенном наборе — ${D.demo.filter((c) => c.score >= game.state.threshold).length} из ${D.demo.length}.`;
  }
  function zoom(epoch = ui.epoch) {
    const c = current();
    const available = thirdAvailable(c) ? [0, 1, 2] : [0, 1];
    if (!available.includes(epoch)) epoch = 0;
    showDialog(
      `${esc(c.name)} · снимок ${epoch + 1}`,
      `<img class="zoom-image" src="${c.frames[epoch]}" alt="${esc(c.name)}: снимок ${epoch + 1}"><p class="frame-dates">${esc(observationLabel(c, epoch))}</p><div class="flow-buttons">${available.map((e) => button("zoom-epoch", `Снимок ${e + 1}`, e, `aria-pressed="${e === epoch}"`)).join("")}</div><p>Увеличение меняет размер отображения, не данные.</p>${observationDetails(c)}`,
      "zoom-dialog",
    );
  }
  dialog.addEventListener("close", () => {
    if (lastFocus?.isConnected) lastFocus.focus({ preventScroll: true });
  });
  document.addEventListener("click", async (event) => {
    const target = event.target.closest("[data-action]");
    if (!target || target.disabled) return;
    const action = target.dataset.action,
      value = target.dataset.value;
    if (action === "close-dialog") {
      dialog.close();
      return;
    }
    if (action === "story-plot" || action === "story-process") {
      const scroll = dialog.scrollTop;
      stories(action === "story-plot" ? 0 : 1, value === "mean" || value === "difference");
      dialog.scrollTop = scroll;
      dialog.querySelector(`[data-action="${action}"][data-value="${value}"]`).focus({ preventScroll: true });
      return;
    }
    if (action === "stories" || action === "story") {
      stories(action === "story" ? Number(value) : 0);
      return;
    }
    if (action === "real") {
      real();
      return;
    }
    if (action === "presenter") {
      presenter();
      return;
    }
    if (action === "hint") {
      hint();
      return;
    }
    if (action === "zoom" || action === "zoom-epoch") {
      zoom(action === "zoom-epoch" ? Number(value) : ui.epoch);
      return;
    }
    if (action === "new-group") {
      showDialog(
        "Начать новую смену?",
        `<p>Все версии, открытые наблюдения и таймер текущей группы будут сброшены.</p><div class="flow-buttons">${button("confirm-reset", "Да, новая группа", "", 'class="primary"')}${button("close-dialog", "Продолжить исследование")}</div>`,
      );
      return;
    }
    if (action === "confirm-reset") {
      dialog.close();
      game.reset();
      welcome = true;
      resetInstrument();
      render(true);
      return;
    }
    if (action === "timer-toggle") {
      game.state.timerStartedAt === null
        ? game.startTimer()
        : game.pauseTimer();
      presenter();
      return;
    }
    if (action === "timer-reset") {
      game.pauseTimer();
      game.state.elapsedMs = 0;
      presenter();
      return;
    }
    if (action === "threshold") {
      game.setThreshold(Number(value));
      updateRanking();
      return;
    }
    if (action === "start-full" || action === "start-short") {
      game.reset(action === "start-full" ? "full" : "short");
      welcome = false;
      resetInstrument();
      render(true);
      return;
    }
    if (action === "begin") {
      game.state.page = "overview";
      game.startTimer();
      render(true);
      return;
    }
    if (action === "nav-map" || action === "nav-cards") {
      game.setView(action === "nav-map" ? "map" : "cards");
      game.state.page = "overview";
      render(true);
      return;
    }
    if (action === "select") {
      await choose(target.dataset.id);
      return;
    }
    if (action === "observe") {
      await choose(game.state.focus);
      return;
    }
    if (action === "back") {
      game.state.page = "overview";
      render(true);
      return;
    }
    if (action === "finish") {
      openResults();
      return;
    }
    if (action === "confirm-finish") {
      finish();
      return;
    }
    if (action === "review-case") {
      const c = current();
      if (!game.reveal(c.id)) return;
      render();
      showDialog("Разбор одного участка", caseReview(c, true), "review-dialog");
      lastFocus = document.querySelector('[data-action="review-case"]');
      return;
    }
    if (action === "next") {
      const id = game.nextCaseId();
      if (id) await choose(id);
      else openResults();
      return;
    }
    if (action === "predict") {
      game.predict(current().id, value);
      render();
      document.querySelector(".flow-actions").focus();
      return;
    }
    if (action === "edit-prediction") {
      showDialog(
        "Уточнить первое впечатление",
        `<div class="choice-row">${Object.entries(C.observations)
          .map(([v, l]) => button("change-prediction", l, v))
          .join(
            "",
          )}</div><p>Рабочая версия и открытый по заявке снимок сохранятся.</p>`,
      );
      return;
    }
    if (action === "change-prediction") {
      game.predict(current().id, value);
      dialog.close();
      render();
      return;
    }
    if (action === "request") {
      if (game.request(current().id)) {
        ui.pair = [1, 2];
        ui.tool = "pair";
        ui.epoch = 2;
        render();
        announce("Третий снимок открыт. Сравните его с предыдущими.");
      } else
        announce(
          "Нет свободных заявок. Можно записать предварительную версию.",
        );
      return;
    }
    if (action === "decide") {
      game.decide(current().id, value);
      ui.revising = false;
      render();
      document.querySelector(".flow-actions").focus();
      announce("Рабочая версия сохранена.");
      return;
    }
    if (action === "revise") {
      ui.revising = true;
      render();
      document.querySelector(".flow-actions").focus();
      return;
    }
    if (action === "tool") {
      ui.tool = value;
      render();
      return;
    }
    if (action === "epoch") {
      const epoch = Number(value);
      if (epoch === 2 && !thirdAvailable(current())) return;
      ui.epoch = epoch;
      render();
      return;
    }
    if (action === "pair") {
      const pair = value.split(",").map(Number);
      if (pair.includes(2) && !thirdAvailable(current())) return;
      ui.pair = pair;
      render();
    }
  });
  function setSplit(value) {
    ui.split = Math.max(0, Math.min(100, Math.round(value)));
    const scope = document.querySelector(".scope");
    if (scope) scope.style.setProperty("--split", ui.split + "%");
    const input = document.querySelector("#comparison");
    if (input) input.value = ui.split;
    const out = document.querySelector("#split-output");
    if (out) out.textContent = ui.split + "%";
  }
  document.addEventListener("input", (e) => {
    if (e.target.id === "comparison") setSplit(Number(e.target.value));
    if (e.target.id === "threshold") {
      game.setThreshold(Number(e.target.value));
      updateRanking();
    }
  });
  document.addEventListener("pointerdown", (e) => {
    const node = e.target.closest(".scope.compare .image-window");
    if (!node || e.button !== 0) return;
    e.preventDefault();
    node.setPointerCapture(e.pointerId);
    const b = node.getBoundingClientRect();
    setSplit(((e.clientX - b.left) / b.width) * 100);
  });
  document.addEventListener("pointermove", (e) => {
    const node = e.target.closest(".scope.compare .image-window");
    if (!node?.hasPointerCapture(e.pointerId)) return;
    const b = node.getBoundingClientRect();
    setSplit(((e.clientX - b.left) / b.width) * 100);
  });
  document.addEventListener("pointerup", (e) => {
    const node = e.target.closest(".scope.compare .image-window");
    if (node?.hasPointerCapture(e.pointerId))
      node.releasePointerCapture(e.pointerId);
  });
  setInterval(() => {
    for (const node of document.querySelectorAll("#timer,[data-timer]"))
      node.textContent = timeText();
  }, 500);
  render();
})();
