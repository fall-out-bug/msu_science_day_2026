/* Модель игры «Архив неизвестного» — чистая логика без DOM и таймеров.
 *
 * Экспорт: globalThis.GameSession (классический скрипт, работает с file://).
 * Экземпляр для инспекции создаёт game.js: window.game = new GameSession(GAME_DATA, mode).
 *
 * Контракт состояний:
 *   state = { mode, focus, view, page, predictions, decisions, checked, hints, revealed,
 *             threshold, elapsedMs, timerStartedAt }
 *   view: 'map' | 'cards'; page: 'briefing' | 'overview' | 'inspect' | 'results'.
 *   Поля представления (view/page/focus) родительский UI может менять напрямую,
 *   но предпочтительны методы. Остальные поля меняются только методами модели.
 *
 * Точные формулы results() (сознательно отвечают на разные вопросы):
 *   found     = число участков с подтверждённым expectedVerdict='sky',
 *               по которым игрок выбрал 'sky'.
 *   missed    = остальные подтверждённые изменения, включая неразобранные.
 *   artifacts = expectedVerdict='artifact' с решением игрока 'artifact'.
 *   extra     = expectedVerdict='stable', на которые потрачена заявка.
 *               Это не штраф: проверка спокойного поля тоже даёт информацию.
 *   Неоднозначные случаи (expectedVerdict='uncertain') не считаются
 *   доказанными изменениями или помехами, независимо от игрового решения.
 *   Счётчики отражают текущие версии, включая пересмотр после разбора.
 *   revealed хранит версию до первого раскрытия (null, если её не было),
 *   чтобы UI мог отличить её от последующего уточнения. Это не второй зачёт.
 *
 * Таймер: модель только накапливает прошедшее время (elapsed-up) по явным
 * startTimer/pauseTimer с внешним `now`. Скрытых таймеров нет; один
 * интервальный дисплей принадлежит UI. reset() обнуляет elapsedMs и
 * останавливает накопление (timerStartedAt = null).
 *
 * Идемпотентность: повтор вызова с ТЕМ ЖЕ значением ничего не меняет. Повтор
 * с другим валидным значением ПЕРЕЗАПИСЫВАЕТ первое впечатление/решение —
 * их можно пересмотреть до финала (это часть игры), без списания жетонов и
 * без изменения checked. Повторный request возвращает true без повторного
 * списания жетона.
 * Ошибки: неизвестные id и недопустимые перечисления/числа — RangeError,
 * некорректные данные конструктора — TypeError. request при исчерпанных
 * жетонах и без первого впечатления НЕ бросает, а возвращает false.
 */
(() => {
  "use strict";

  const MODES = ["full", "short"];
  const VIEWS = ["map", "cards"];
  const PREDICTION_VALUES = ["changed", "same", "unsure"];
  const DECISION_VALUES = ["sky", "artifact", "stable", "uncertain"];
  const BUDGET_BY_MODE = { full: 3, short: 1 };
  const THRESHOLD_MIN = 0.5;
  const THRESHOLD_MAX = 5;

  class GameSession {
    /**
     * @param {object} data window.GAME_DATA: {meta, contact:[Case], demo:[Case], shortIds:[id]}
     * @param {'full'|'short'} mode
     */
    constructor(data, mode = "full") {
      if (!data || typeof data !== "object") {
        throw new TypeError("GameSession: нужен объект данных GAME_DATA");
      }
      if (!Array.isArray(data.contact) || data.contact.length === 0) {
        throw new TypeError(
          "GameSession: data.contact должен быть непустым массивом участков",
        );
      }
      if (!MODES.includes(mode)) {
        throw new RangeError(
          `GameSession: неизвестный режим «${mode}» (допустимо: ${MODES.join(", ")})`,
        );
      }
      const ids = new Set();
      for (const c of data.contact) {
        if (!c || typeof c.id !== "string") {
          throw new TypeError(
            "GameSession: у каждого участка должен быть строковый id",
          );
        }
        if (ids.has(c.id)) {
          throw new TypeError(`GameSession: дубликат id участка «${c.id}»`);
        }
        ids.add(c.id);
      }
      if (!Array.isArray(data.shortIds) || data.shortIds.length === 0) {
        throw new TypeError(
          "GameSession: data.shortIds должен быть непустым массивом id",
        );
      }
      for (const id of data.shortIds) {
        if (!ids.has(id)) {
          throw new TypeError(
            `GameSession: shortIds содержит неизвестный id «${id}»`,
          );
        }
      }

      this.data = data;
      this.state = {
        mode,
        focus: null,
        view: "map",
        page: "briefing",
        predictions: {},
        decisions: {},
        checked: [],
        hints: [],
        revealed: {},
        threshold: 1,
        elapsedMs: 0,
        timerStartedAt: null,
      };
      this._applyMode(mode);
    }

    /** Жетоны доп-наблюдений: 3 в полном сезоне, 1 в коротком. */
    get budget() {
      return BUDGET_BY_MODE[this.state.mode];
    }

    /** Сколько жетонов осталось (не уходит ниже нуля). */
    get remaining() {
      return Math.max(0, this.budget - this.state.checked.length);
    }

    /** Пересобирает состояние под режим; общий сброс — см. reset(). */
    _applyMode(mode) {
      if (mode === "short") {
        const byId = new Map(this.data.contact.map((c) => [c.id, c]));
        this.cases = this.data.shortIds.map((id) => byId.get(id));
      } else {
        this.cases = this.data.contact.slice();
      }
      this.state.mode = mode;
      this.state.focus = this.cases[0].id;
    }

    _case(id) {
      return this.cases.find((c) => c.id === id) || null;
    }

    _requireCase(id) {
      if (typeof id !== "string" || !this._case(id)) {
        throw new RangeError(`GameSession: неизвестный id участка «${id}»`);
      }
    }

    _requireEnum(value, allowed, what) {
      if (!allowed.includes(value)) {
        throw new RangeError(
          `GameSession: недопустимое значение ${what} «${value}» (допустимо: ${allowed.join(", ")})`,
        );
      }
    }

    /** Сброс сессии; reset('short'|'full') заодно переключает режим. */
    reset(mode = this.state.mode) {
      this._requireEnum(mode, MODES, "режима");
      Object.assign(this.state, {
        mode,
        view: "map",
        page: "briefing",
        predictions: {},
        decisions: {},
        checked: [],
        hints: [],
        revealed: {},
        threshold: 1,
        elapsedMs: 0,
        timerStartedAt: null,
      });
      this._applyMode(mode);
      return this.state;
    }

    /** Выбор участка; единое состояние для карты и карточек. */
    select(id) {
      this._requireCase(id);
      this.state.focus = id;
      return id;
    }

    setView(view) {
      this._requireEnum(view, VIEWS, "вида навигации");
      this.state.view = view;
      return view;
    }

    /** Следующий участок без версии; null — версии есть у всей смены. */
    nextCaseId() {
      const start = this.cases.findIndex((c) => c.id === this.state.focus);
      const ordered = this.cases.slice(start + 1).concat(this.cases.slice(0, start + 1));
      return ordered.find((c) => !this.state.decisions[c.id])?.id ?? null;
    }

    isRevealed(id) {
      this._requireCase(id);
      return Object.prototype.hasOwnProperty.call(this.state.revealed, id);
    }

    /** Научный разбор одного дела доступен после собственной версии. */
    reveal(id) {
      this._requireCase(id);
      if (this.isRevealed(id)) return true;
      if (!this.state.decisions[id]) return false;
      this.state.revealed[id] = this.state.decisions[id];
      return true;
    }

    /** Общий разбор явно раскрывает и ещё не исследованные случаи. */
    revealAll() {
      for (const c of this.cases) {
        if (!this.isRevealed(c.id)) {
          this.state.revealed[c.id] = this.state.decisions[c.id] ?? null;
        }
      }
    }

    /** В разборе третий кадр открыт бесплатно; checked хранит только заявки. */
    hasThirdFrame(id) {
      return this.isChecked(id) || this.isRevealed(id);
    }

    /**
     * Первое впечатление по кадрам 1–2. Пересматривается: повтор с тем же
     * значением — no-op, с другим валидным — перезаписывает. Жетоны и
     * checked не затрагиваются.
     * @returns {boolean} true — значение изменилось, false — было тем же.
     */
    predict(id, value) {
      this._requireCase(id);
      this._requireEnum(value, PREDICTION_VALUES, "впечатления");
      if (this.state.predictions[id] === value) {
        return false;
      }
      this.state.predictions[id] = value;
      return true;
    }

    /**
     * Запрос третьего кадра (доп-наблюдение) за жетон.
     * Требует первого впечатления. Возвраты без исключений:
     *   false — впечатления нет или жетонов не осталось;
     *   true  — кадр открыт (в т.ч. повторный вызов: без двойного списания).
     */
    request(id) {
      this._requireCase(id);
      if (!Object.prototype.hasOwnProperty.call(this.state.predictions, id)) {
        return false;
      }
      if (this.hasThirdFrame(id)) {
        return true;
      }
      if (this.remaining <= 0) {
        return false;
      }
      this.state.checked.push(id);
      return true;
    }

    /** Была оплачена заявка? Доступ к третьему кадру проверяет hasThirdFrame(). */
    isChecked(id) {
      this._requireCase(id);
      return this.state.checked.includes(id);
    }

    /**
     * Решение совета. Разрешено после первого впечатления даже без третьего
     * кадра — жетоны редки. Пересматривается: повтор с тем же значением —
     * no-op, с другим валидным — перезаписывает (sky→artifact→uncertain
     * допустима до финала); жетоны и checked не затрагиваются.
     * @returns {boolean} true — значение изменилось, false — было тем же.
     */
    decide(id, value) {
      this._requireCase(id);
      this._requireEnum(value, DECISION_VALUES, "решения");
      if (!Object.prototype.hasOwnProperty.call(this.state.predictions, id)) {
        throw new RangeError(
          "GameSession: решение требует первого впечатления — сначала predict()",
        );
      }
      if (this.state.decisions[id] === value) {
        return false;
      }
      this.state.decisions[id] = value;
      return true;
    }

    /**
     * Подсказка независимого алгоритма-помощника. Не влияет на фазу игры
     * (page/focus/view/жетоны/кадры не трогает), только фиксирует факт
     * обращения. Порог берётся текущий (state.threshold): подсказка честно
     * меняется вместе с настройкой порога игрока.
     * @returns {{verdict:'candidate'|'noise', score:number, threshold:number}}
     */
    hint(id) {
      this._requireCase(id);
      if (!this.state.hints.includes(id)) {
        this.state.hints.push(id);
      }
      const c = this._case(id);
      const verdict = c.score >= this.state.threshold ? "candidate" : "noise";
      return { verdict, score: c.score, threshold: this.state.threshold };
    }

    /**
     * Порог алгоритма-помощника, диапазон [0.5; 5] (пресеты UI: 1 и 3).
     * @param {number} value
     */
    setThreshold(value) {
      if (typeof value !== "number" || !Number.isFinite(value)) {
        throw new RangeError(
          `GameSession: порог должен быть числом, получено «${value}»`,
        );
      }
      if (value < THRESHOLD_MIN || value > THRESHOLD_MAX) {
        throw new RangeError(
          `GameSession: порог ${value} вне диапазона [${THRESHOLD_MIN}; ${THRESHOLD_MAX}]`,
        );
      }
      this.state.threshold = value;
      return value;
    }

    /** Включает отсчёт (elapsed-up). Повторный запуск без паузы — no-op. */
    startTimer(now = Date.now()) {
      if (this.state.timerStartedAt === null) {
        this.state.timerStartedAt = now;
      }
    }

    /** Ставит отсчёт на паузу, накапливая elapsedMs. Без запуска — no-op. */
    pauseTimer(now = Date.now()) {
      if (this.state.timerStartedAt !== null) {
        this.state.elapsedMs += Math.max(0, now - this.state.timerStartedAt);
        this.state.timerStartedAt = null;
      }
    }

    /** Прошедшее время игры, мс: накопленное + текущий отрезок. */
    elapsed(now = Date.now()) {
      const running =
        this.state.timerStartedAt !== null
          ? Math.max(0, now - this.state.timerStartedAt)
          : 0;
      return this.state.elapsedMs + running;
    }

    /**
     * Честные счётчики итогов; точные формулы — в шапке файла.
     * @returns {{found:number, missed:number, artifacts:number, extra:number}}
     */
    results() {
      let found = 0;
      let missed = 0;
      let artifacts = 0;
      let extra = 0;
      for (const c of this.cases) {
        const decision = this.state.decisions[c.id];
        if (c.expectedVerdict === "sky") {
          if (decision === "sky") {
            found += 1;
          } else {
            missed += 1;
          }
        } else if (c.expectedVerdict === "artifact" && decision === "artifact") {
          artifacts += 1;
        }
        if (c.expectedVerdict === "stable" && this.state.checked.includes(c.id)) {
          extra += 1;
        }
      }
      return { found, missed, artifacts, extra };
    }
  }

  globalThis.GameSession = GameSession;
})();
