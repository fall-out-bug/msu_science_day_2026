#!/usr/bin/env bun
/* Фокусные регрессионные тесты модели app/model.js (без DOM).
 *
 * Запуск: bun tools/check_model.mjs [--dump OUT.json]
 *   без флагов  — прогон всех проверок на фикстуре + (если есть app/data.js)
 *                 проверка контракта реальных данных;
 *   --dump FILE — выгрузить сводку реальных данных (meta, счёты, типы) в JSON
 *                 для перекрёстной сверки генератора в tools/check_artifacts.py
 *                 (в этом режиме тесты не прогоняются).
 *
 * Коды выхода: 0 — все проверки прошли; 1 — есть провалы/ошибки.
 */
import { readFileSync, existsSync, writeFileSync } from 'node:fs';
import vm from 'node:vm';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const MODEL = join(ROOT, 'app', 'model.js');
const DATA = join(ROOT, 'app', 'data.js');

vm.runInThisContext(readFileSync(MODEL, 'utf8'), { filename: 'app/model.js' });
const GameSession = globalThis.GameSession;

/* ---------- фикстура: 12 участков, детерминированная интерливинг-структура ---------- */

function makeFixture() {
  const spec = [
    // [id, type, score] — 4 normal, 2 mover, 2 variable, 2 artifact, 1 weak, 1 weak_mid
    ['c01', 'normal', 0.4], ['c02', 'mover', 5.2], ['c03', 'normal', 1.2],
    ['c04', 'variable', 4.1], ['c05', 'normal', 0.7], ['c06', 'artifact', 6.0],
    ['c07', 'normal', 0.3], ['c08', 'weak', 0.6], ['c09', 'mover', 5.0],
    ['c10', 'variable', 4.4], ['c11', 'artifact', 5.5], ['c12', 'weak_mid', 2.0],
  ];
  // expectedVerdict повторяет зафиксированные ожидания типов: счётчики результатов
  // считаются от ожидаемого вердикта реального источника, не от подтипа как такового.
  const EXPECTED = { normal: 'stable', mover: 'sky', variable: 'sky',
                     weak: 'sky', weak_mid: 'sky', artifact: 'artifact' };
  const px = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUg==';
  const contact = spec.map(([id, type, score], i) => ({
    id, type, score,
    expectedVerdict: EXPECTED[type],
    name: `Участок ${i + 1}`,
    frames: [px, px, px],
    features: { max_diff: 10 + i, area: i, peak: 100 },
    z: [i * 0.5, i * 0.4, score],
    explanation: `Пояснение ${i + 1}`,
  }));
  return {
    meta: { synthetic: true, thresholds: { soft: 1.0, strict: 3.0 } },
    contact,
    demo: contact.slice(0, 3),
    // 2 normal, 1 mover, 1 variable, 1 artifact, 1 weak_mid — по контракту
    shortIds: ['c01', 'c03', 'c02', 'c04', 'c06', 'c12'],
  };
}

/* ---------- мини-раннер ---------- */

const failures = [];
let passed = 0;

function check(name, fn) {
  try {
    fn();
    passed += 1;
    console.log(`  ok  ${name}`);
  } catch (e) {
    failures.push({ name, error: String(e && e.message || e) });
    console.log(`FAIL  ${name}: ${e && e.message}`);
  }
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg || 'условие ложно');
}

function assertEq(actual, expected, what) {
  const a = JSON.stringify(actual);
  const b = JSON.stringify(expected);
  if (a !== b) throw new Error(`${what}: получено ${a}, ожидалось ${b}`);
}

function assertThrows(fn, ErrClass, fragment) {
  let threw = null;
  try {
    fn();
  } catch (e) {
    threw = e;
  }
  assert(threw, `ожидали исключение${fragment ? ` «${fragment}»` : ''}, но его не было`);
  assert(threw instanceof ErrClass,
    `ожидали ${ErrClass.name}, получено ${threw.constructor.name}: ${threw.message}`);
  if (fragment) assert(String(threw.message).includes(fragment), `в ошибке нет «${fragment}»: ${threw.message}`);
}

const clone = (x) => JSON.parse(JSON.stringify(x));

/* ---------- проверки фикстуры ---------- */

function runFixtureTests() {
  console.log('== Конструктор и режимы ==');
  const D = makeFixture();
  check('full: 12 участков, фокус = первому, состояние по контракту', () => {
    const g = new GameSession(D, 'full');
    assertEq(g.cases.map((c) => c.id), D.contact.map((c) => c.id), 'порядок cases');
    assertEq(g.state, {
      mode: 'full', focus: 'c01', view: 'map', page: 'briefing',
      predictions: {}, decisions: {}, checked: [], hints: [], revealed: {}, threshold: 1,
      elapsedMs: 0, timerStartedAt: null,
    }, 'начальное state');
  });
  check('short: подмножество shortIds в их порядке, бюджет 1', () => {
    const g = new GameSession(D, 'short');
    assertEq(g.cases.map((c) => c.id), D.shortIds, 'cases short');
    assertEq(g.budget, 1, 'budget');
    assertEq(g.remaining, 1, 'remaining');
    assertEq(g.state.focus, 'c01', 'focus');
  });
  check('full: бюджет 3', () => {
    assertEq(new GameSession(D, 'full').budget, 3, 'budget');
  });
  check('конструктор по умолчанию = full', () => {
    assertEq(new GameSession(D).state.mode, 'full', 'mode');
  });
  check('неизвестный режим отклонён', () => {
    assertThrows(() => new GameSession(D, 'demo'), RangeError, 'режим');
  });
  check('битые данные отклонены (TypeError)', () => {
    assertThrows(() => new GameSession(null), TypeError);
    assertThrows(() => new GameSession({}), TypeError);
    assertThrows(() => new GameSession({ contact: [], shortIds: ['c01'] }), TypeError);
    assertThrows(() => new GameSession({ contact: [{ id: 'a' }, { id: 'a' }], shortIds: ['a'] }), TypeError, 'дубликат');
    assertThrows(() => new GameSession({ contact: [{ id: 'a' }], shortIds: ['zzz'] }), TypeError, 'неизвестный');
  });
  check('GAME_DATA не мутируется операциями модели', () => {
    const snapshot = clone(D);
    const g = new GameSession(D, 'full');
    g.select('c02'); g.predict('c02', 'changed'); g.request('c02');
    g.decide('c02', 'sky'); g.hint('c02'); g.setThreshold(3); g.startTimer(1); g.pauseTimer(2);
    g.reset('short'); g.reset('full');
    assertEq(D, snapshot, 'GAME_DATA изменился');
  });

  console.log('== select / setView ==');
  check('select меняет фокус', () => {
    const g = new GameSession(D);
    assertEq(g.select('c07'), 'c07', 'return');
    assertEq(g.state.focus, 'c07', 'focus');
  });
  check('select неизвестного id отклонён', () => {
    const g = new GameSession(D);
    assertThrows(() => g.select('c99'), RangeError, 'неизвестный id');
    assertThrows(() => g.select(42), RangeError);
  });
  check('setView принимает map/cards, остальное отклоняет', () => {
    const g = new GameSession(D);
    g.setView('cards'); assertEq(g.state.view, 'cards', 'cards');
    g.setView('map'); assertEq(g.state.view, 'map', 'map');
    assertThrows(() => g.setView('grid'), RangeError);
    assertThrows(() => g.setView(undefined), RangeError);
  });

  console.log('== predict: первое впечатление, идемпотентность ==');
  check('predict записывает значение', () => {
    const g = new GameSession(D);
    assertEq(g.predict('c02', 'changed'), true, 'return');
    assertEq(g.state.predictions, { c02: 'changed' }, 'predictions');
  });
  check('predict: тот же повтор — no-op, другое значение пересматривает', () => {
    const g = new GameSession(D);
    assertEq(g.predict('c02', 'changed'), true, 'первая запись');
    assertEq(g.predict('c02', 'changed'), false, 'повтор того же значения');
    assertEq(g.state.predictions.c02, 'changed', 'значение');
    assertEq(g.predict('c02', 'same'), true, 'правка другим значением');
    assertEq(g.state.predictions.c02, 'same', 'впечатление переписано');
    assertEq(g.predict('c02', 'unsure'), true, 'ещё одна правка');
    assertEq(g.state.predictions.c02, 'unsure', 'changed→same→unsure');
  });
  check('predict недопустимое значение/неизвестный id отклонены', () => {
    const g = new GameSession(D);
    assertThrows(() => g.predict('c02', 'bright'), RangeError);
    assertThrows(() => g.predict('zz', 'changed'), RangeError);
  });

  console.log('== request: жетоны, овердрафт, идемпотентность ==');
  check('request без первого впечатления → false', () => {
    const g = new GameSession(D);
    assertEq(g.request('c02'), false, 'return');
    assertEq(g.state.checked, [], 'checked');
  });
  check('request списывает жетон, повтор → true без двойного списания', () => {
    const g = new GameSession(D);
    g.predict('c02', 'changed');
    assertEq(g.request('c02'), true, 'первый');
    assertEq(g.state.checked, ['c02'], 'checked');
    assertEq(g.remaining, 2, 'remaining');
    assertEq(g.request('c02'), true, 'повтор');
    assertEq(g.state.checked, ['c02'], 'checked после повтора');
    assertEq(g.remaining, 2, 'remaining после повтора');
  });
  check('овердрафт невозможен: 3 жетона full, 4-й → false', () => {
    const g = new GameSession(D);
    for (const id of ['c01', 'c02', 'c03']) {
      g.predict(id, 'unsure');
      assertEq(g.request(id), true, `жетон на ${id}`);
    }
    assertEq(g.remaining, 0, 'remaining 0');
    g.predict('c04', 'unsure');
    assertEq(g.request('c04'), false, '4-й request');
    assertEq(g.state.checked.length, 3, 'checked не вырос');
    assertEq(g.remaining, 0, 'remaining не ушёл в минус');
  });
  check('short: единственный жетон, второй участок → false', () => {
    const g = new GameSession(D, 'short');
    g.predict('c01', 'unsure'); g.request('c01');
    assertEq(g.remaining, 0, 'remaining');
    g.predict('c02', 'unsure');
    assertEq(g.request('c02'), false, 'второй request');
    assertEq(g.state.checked, ['c01'], 'checked');
  });
  check('request неизвестного id отклонён (даже при нуле жетонов)', () => {
    const g = new GameSession(D);
    assertThrows(() => g.request('zz'), RangeError);
  });

  console.log('== decide: решение после впечатления, без третьего кадра ==');
  check('decide без первого впечатления отклонён', () => {
    const g = new GameSession(D);
    assertThrows(() => g.decide('c02', 'sky'), RangeError, 'впечатления');
  });
  check('decide работает без request (третий кадр не нужен)', () => {
    const g = new GameSession(D);
    g.predict('c02', 'changed');
    assertEq(g.decide('c02', 'sky'), true, 'return');
    assertEq(g.state.decisions.c02, 'sky', 'решение');
    assertEq(g.state.checked, [], 'жетон не потрачен');
  });
  check('decide: тот же повтор — no-op, цепочка sky→artifact→uncertain пересматривает', () => {
    const g = new GameSession(D);
    g.predict('c02', 'unsure');
    g.request('c02'); // жетон потрачен до пересмотров
    assertEq(g.decide('c02', 'sky'), true, 'первое решение');
    assertEq(g.decide('c02', 'sky'), false, 'повтор того же значения');
    assertEq(g.decide('c02', 'artifact'), true, 'sky→artifact');
    assertEq(g.decide('c02', 'uncertain'), true, 'artifact→uncertain');
    assertEq(g.state.decisions.c02, 'uncertain', 'итог пересмотра');
    assertEq(g.state.checked, ['c02'], 'checked не изменился от пересмотра');
    assertEq(g.remaining, 2, 'жетоны не тронуты пересмотром');
    // впечатление тоже правится без последствий для жетонов
    assertEq(g.predict('c02', 'changed'), true, 'правка впечатления');
    assertEq(g.state.predictions.c02, 'changed', 'changed→… впечатление');
    assertEq(g.state.checked, ['c02'], 'checked не изменился от правки впечатления');
    assertEq(g.remaining, 2, 'жетоны не тронуты правкой впечатления');
  });
  check('decide недопустимое значение отклонено', () => {
    const g = new GameSession(D);
    g.predict('c02', 'unsure');
    assertThrows(() => g.decide('c02', 'comet'), RangeError);
    assertThrows(() => g.decide('zz', 'sky'), RangeError);
  });

  console.log('== hint: независимая подсказка, фазу не трогает ==');
  check('hint фиксирует обращение и считает вердикт по порогу', () => {
    const g = new GameSession(D);
    const h = g.hint('c02');
    assertEq(g.state.hints, ['c02'], 'hints');
    assertEq(h, { verdict: 'candidate', score: 5.2, threshold: 1 }, 'вердикт');
  });
  check('hint идемпотентен', () => {
    const g = new GameSession(D);
    g.hint('c02'); g.hint('c02');
    assertEq(g.state.hints, ['c02'], 'без дублей');
  });
  check('hint не меняет фазу: page/focus/view/жетоны/checked/решения', () => {
    const g = new GameSession(D);
    g.select('c04'); g.setView('cards');
    g.predict('c04', 'changed'); g.request('c04'); g.decide('c04', 'sky');
    const before = clone(g.state);
    g.hint('c08');
    const after = g.state;
    assertEq(after.page, before.page, 'page');
    assertEq(after.focus, before.focus, 'focus');
    assertEq(after.view, before.view, 'view');
    assertEq(after.checked, before.checked, 'checked');
    assertEq(after.decisions, before.decisions, 'decisions');
    assertEq(after.predictions, before.predictions, 'predictions');
    assertEq(after.threshold, before.threshold, 'threshold');
    assertEq(g.remaining, 2, 'жетоны');
  });
  check('вердикт подсказки зависит от порога (шум↔кандидат)', () => {
    const g = new GameSession(D);
    g.setThreshold(3);
    assertEq(g.hint('c08').verdict, 'noise', 'weak при строгом пороге');
    assertEq(g.hint('c02').verdict, 'candidate', 'mover при строгом пороге');
    g.setThreshold(0.5);
    assertEq(g.hint('c08').verdict, 'candidate', 'weak при мягком пороге');
  });
  check('hint неизвестного id отклонён', () => {
    const g = new GameSession(D);
    assertThrows(() => g.hint('zz'), RangeError);
  });

  console.log('== setThreshold: границы [0.5; 5] ==');
  check('граничные и промежуточные значения принимаются', () => {
    const g = new GameSession(D);
    g.setThreshold(0.5); assertEq(g.state.threshold, 0.5, '0.5');
    g.setThreshold(5); assertEq(g.state.threshold, 5, '5');
    g.setThreshold(2.5); assertEq(g.state.threshold, 2.5, '2.5');
  });
  check('вне диапазона и не-числа отклонены', () => {
    const g = new GameSession(D);
    assertThrows(() => g.setThreshold(0.49), RangeError);
    assertThrows(() => g.setThreshold(5.01), RangeError);
    assertThrows(() => g.setThreshold(-1), RangeError);
    assertThrows(() => g.setThreshold(NaN), RangeError);
    assertThrows(() => g.setThreshold('3'), RangeError);
  });

  console.log('== таймер: elapsed-up, пауза, сброс ==');
  check('start→elapsed растёт от внешнего now; повторный start — no-op', () => {
    const g = new GameSession(D);
    g.startTimer(1000);
    g.startTimer(2000); // не должен перезаписать точку старта
    assertEq(g.state.timerStartedAt, 1000, 'timerStartedAt');
    assertEq(g.elapsed(6000), 5000, 'elapsed');
  });
  check('pause накапливает; после паузы elapsed заморожен', () => {
    const g = new GameSession(D);
    g.startTimer(1000);
    g.pauseTimer(8000);
    assertEq(g.state.elapsedMs, 7000, 'elapsedMs');
    assertEq(g.state.timerStartedAt, null, 'остановлен');
    assertEq(g.elapsed(99000), 7000, 'elapsed после паузы');
  });
  check('несколько отрезков суммируются', () => {
    const g = new GameSession(D);
    g.startTimer(0); g.pauseTimer(4000);
    g.startTimer(10000); g.pauseTimer(15000);
    assertEq(g.elapsed(999999), 9000, 'сумма');
  });
  check('pause без start — no-op; elapsed без старта = 0', () => {
    const g = new GameSession(D);
    g.pauseTimer(100);
    assertEq(g.elapsed(5000), 0, 'elapsed');
    assertEq(g.state.timerStartedAt, null, 'не запустился');
  });
  check('reset обнуляет время и останавливает отсчёт', () => {
    const g = new GameSession(D);
    g.startTimer(0);
    g.reset();
    assertEq(g.state.elapsedMs, 0, 'elapsedMs');
    assertEq(g.state.timerStartedAt, null, 'остановлен');
    assertEq(g.elapsed(12345), 0, 'elapsed');
  });

  console.log('== reset: полный сброс и переключение режима ==');
  check('reset очищает прогресс, сохраняя режим', () => {
    const g = new GameSession(D, 'full');
    g.select('c05'); g.setView('cards');
    g.predict('c05', 'same'); g.request('c05'); g.decide('c05', 'sky');
    g.hint('c06'); g.setThreshold(3); g.startTimer(0);
    g.reset();
    assertEq(g.state, {
      mode: 'full', focus: 'c01', view: 'map', page: 'briefing',
      predictions: {}, decisions: {}, checked: [], hints: [], revealed: {}, threshold: 1,
      elapsedMs: 0, timerStartedAt: null,
    }, 'state после reset');
    assertEq(g.remaining, 3, 'жетоны восстановлены');
    assertEq(g.budget, 3, 'бюджет режима');
  });
  check("reset('short') переключает режим, reset() без аргумента сохраняет", () => {
    const g = new GameSession(D, 'full');
    g.reset('short');
    assertEq(g.state.mode, 'short', 'mode');
    assertEq(g.cases.map((c) => c.id), D.shortIds, 'cases');
    assertEq(g.budget, 1, 'budget');
    g.reset();
    assertEq(g.state.mode, 'short', 'mode сохранён');
  });
  check("reset с неизвестным режимом отклонён", () => {
    const g = new GameSession(D);
    assertThrows(() => g.reset('demo'), RangeError);
  });

  console.log('== раскрытие ответа и завершение ==');
  for (const mode of ['full', 'short']) {
    check(`${mode}: следующий незавершённый участок в произвольном порядке, затем null`, () => {
      const g = new GameSession(D, mode);
      const ids = g.cases.map(c => c.id);
      for (const id of ids.slice().reverse()) {
        g.select(id);
        g.predict(id, 'unsure');
        g.decide(id, 'uncertain');
        const next = g.nextCaseId();
        assert(next === null || !g.state.decisions[next], 'не возвращаемся к решённому делу');
      }
      assertEq(g.nextCaseId(), null, 'все версии сохранены');
      g.select(ids[0]);
      g.decide(ids[0], 'sky');
      assertEq(g.nextCaseId(), null, 'пересмотр не возобновляет круг');
    });
  }
  check('разбор одного дела требует версии и не раскрывает остальные', () => {
    const g = new GameSession(D);
    assertEq(g.reveal('c02'), false, 'без решения закрыт');
    g.predict('c02', 'unsure');
    assertEq(g.reveal('c02'), false, 'одного впечатления недостаточно');
    g.decide('c02', 'uncertain');
    assertEq(g.reveal('c02'), true, 'разбор доступен');
    assertEq(g.state.revealed, { c02: 'uncertain' }, 'раскрыто одно дело');
    assertEq(g.hasThirdFrame('c02'), true, 'третий снимок доступен в разборе');
    assertEq(g.hasThirdFrame('c01'), false, 'чужой кадр закрыт');
    assertEq(g.request('c02'), true, 'повторно открывается без заявки');
    assertEq(g.remaining, 3, 'разбор не расходует заявки');
    assertEq(g.state.checked, [], 'разбор не выдаётся за заявку');
    assertThrows(() => g.reveal('missing'), RangeError);
  });
  check('после пересмотра сохраняется версия до раскрытия; итоги используют текущую', () => {
    const g = new GameSession(D);
    g.predict('c02', 'unsure'); g.decide('c02', 'uncertain'); g.reveal('c02');
    g.decide('c02', 'sky'); g.reveal('c02');
    assertEq(g.state.revealed.c02, 'uncertain', 'исходная версия не перезаписана');
    assertEq(g.state.decisions.c02, 'sky', 'пересмотр разрешён');
    assertEq(g.results().found, 1, 'счётчик отражает текущую версию');
  });
  check('общий разбор сохраняет исходные версии и явно отмечает неотвеченные', () => {
    const g = new GameSession(D, 'short');
    g.predict('c01', 'same'); g.request('c01'); g.decide('c01', 'stable');
    g.reveal('c01'); g.decide('c01', 'uncertain');
    g.revealAll();
    assertEq(Object.keys(g.state.revealed), g.cases.map(c => c.id), 'раскрыта только текущая смена');
    assertEq(g.state.revealed.c01, 'stable', 'общий разбор не стирает исходную версию');
    assertEq(g.state.revealed.c02, null, 'версии до разбора не было');
    g.predict('c02', 'changed'); g.decide('c02', 'sky'); g.revealAll();
    assertEq(g.state.revealed.c02, null, 'последующее решение не выдано за исходное');
    assertEq(g.state.checked, ['c01'], 'платная заявка сохранена');
    assertEq(g.results().extra, 1, 'бесплатные кадры не считаются заявками');
    g.reset('full');
    assertEq(g.state.revealed, {}, 'новая группа не наследует раскрытие');
    assertEq(g.hasThirdFrame('c01'), false, 'третий снимок снова закрыт');
  });

  console.log('== results: точные формулы счётчиков ==');
  check('смешанный сценарий: found/missed/artifacts/extra по формулам', () => {
    const g = new GameSession(D, 'full');
    // найдено: оба mover + variable c10 (interesting в фикстуре: c02,c04,c08,c09,c10,c12)
    g.predict('c02', 'changed'); g.decide('c02', 'sky');
    g.predict('c09', 'changed'); g.decide('c09', 'sky');
    g.predict('c10', 'changed'); g.decide('c10', 'sky');
    // пропущено: variable c04 решён «не sky», weak c08 и weak_mid c12 не решены
    g.predict('c04', 'unsure'); g.decide('c04', 'uncertain');
    // артефакт распознан только c06; c11 решён мимо (в artifacts не попадает)
    g.predict('c06', 'unsure'); g.request('c06'); g.decide('c06', 'artifact');
    g.predict('c11', 'unsure'); g.decide('c11', 'sky');
    // лишняя проверка нормального поля
    g.predict('c01', 'unsure'); g.request('c01');
    // normal c03 решён sky — в found НЕ попадает
    g.predict('c03', 'changed'); g.decide('c03', 'sky');
    assertEq(g.results(), { found: 3, missed: 3, artifacts: 1, extra: 1 }, 'счётчики');
  });
  check('нормальное поле с жетоном и решением sky — только extra', () => {
    const g = new GameSession(D);
    g.predict('c01', 'changed'); g.request('c01'); g.decide('c01', 'sky');
    // остальные интересные (6) остались без решения sky → missed
    assertEq(g.results(), { found: 0, missed: 6, artifacts: 0, extra: 1 }, 'счётчики');
  });
  check('слабый сигнал с жетоном не считается extra (он интересный)', () => {
    const g = new GameSession(D);
    g.predict('c08', 'changed'); g.request('c08'); g.decide('c08', 'sky');
    assertEq(g.results(), { found: 1, missed: 5, artifacts: 0, extra: 0 }, 'счётчики');
  });
  check('в short учитываются только участки короткого набора', () => {
    const g = new GameSession(D, 'short');
    g.predict('c02', 'changed'); g.decide('c02', 'sky');      // mover → found
    g.predict('c06', 'unsure'); g.decide('c06', 'artifact');  // artifact → artifacts
    assertEq(g.results(), { found: 1, missed: 2, artifacts: 1, extra: 0 }, 'счётчики short');
  });
  check('чистая сессия: все счётчики нули (всё пропущено = missed)', () => {
    const g = new GameSession(D);
    assertEq(g.results(), { found: 0, missed: 6, artifacts: 0, extra: 0 }, 'счётчики');
    g.reset();
    assertEq(g.results(), { found: 0, missed: 6, artifacts: 0, extra: 0 }, 'после reset');
  });
}

/* ---------- контракт реальных данных (app/data.js), если он уже собран ---------- */

function loadRealData() {
  if (!existsSync(DATA)) return null;
  globalThis.window = {};
  vm.runInThisContext(readFileSync(DATA, 'utf8'), { filename: 'app/data.js' });
  return globalThis.window.GAME_DATA || null;
}

function dumpData() {
  const d = loadRealData();
  if (!d) {
    console.error('app/data.js не найден — нечего выгружать (сначала сборка data).');
    process.exit(2);
  }
  const strip = (c) => ({
    id: c.id, type: c.type, score: c.score, features: c.features, z: c.z,
    name: c.name, explanation: c.explanation,
    expectedVerdict: c.expectedVerdict, skyContext: c.skyContext,
    ra: c.ra, dec: c.dec,
    observations: c.observations, source: c.source,
    evidence: c.evidence, limitations: c.limitations, photometry: c.photometry,
    frames_len: Array.isArray(c.frames) ? c.frames.length : -1,
  });
  writeFileSync(process.argv[process.argv.indexOf('--dump') + 1], JSON.stringify({
    meta: d.meta,
    shortIds: d.shortIds,
    contact: d.contact.map(strip),
    demo_cases: d.demo.map(strip),
    demo_types: d.demo.map((c) => c.type),
    demo_scores: d.demo.map((c) => c.score),
    demo_ids: d.demo.map((c) => c.id),
  }, null, 1));
  console.log(`dump ok: contact=${d.contact.length} demo=${d.demo.length}`);
}

function runRealDataTests() {
  const d = loadRealData();
  if (!d) {
    console.log('== Реальные данные: app/data.js отсутствует — пропуск (допустимо до сборки) ==');
    return;
  }
  console.log('== Реальные данные app/data.js ==');
  check('GAME_DATA: 12 contact + demo + shortIds=6', () => {
    assertEq(d.contact.length, 12, 'contact');
    assert(Array.isArray(d.demo) && d.demo.length === 200, `demo.length=${d.demo && d.demo.length}`);
    assertEq(d.shortIds.length, 6, 'shortIds');
  });
  check('каждый Case: 3 data-URI кадра, числовые score/features/z, тип и объяснение', () => {
    for (const c of d.contact) {
      assert(typeof c.id === 'string' && c.id, `id у ${c.id}`);
      assert(Array.isArray(c.frames) && c.frames.length === 3, `frames у ${c.id}`);
      for (const f of c.frames) assert(typeof f === 'string' && f.startsWith('data:image/'), `data-URI у ${c.id}`);
      assert(typeof c.score === 'number' && Number.isFinite(c.score), `score у ${c.id}`);
      assert(c.features && ['max_diff', 'area', 'peak'].every((k) => k in c.features), `features у ${c.id}`);
      assert(Array.isArray(c.z) && c.z.length === 3, `z у ${c.id}`);
      assert(['normal', 'mover', 'variable', 'artifact', 'weak', 'weak_mid', 'unresolved'].includes(c.type), `type у ${c.id}`);
      const expected = { normal: 'stable', mover: 'sky', variable: 'sky',
        artifact: 'artifact', weak: 'sky', weak_mid: 'sky', unresolved: 'uncertain' };
      assertEq(c.expectedVerdict, expected[c.type], `научный вердикт у ${c.id}`);
      assert(typeof c.explanation === 'string' && c.explanation.length > 10, `explanation у ${c.id}`);
      assert(typeof c.name === 'string' && c.name.length > 1, `name у ${c.id}`);
    }
  });
  check('каждый Case: координаты ICRS и три датированных наблюдения из разных FITS', () => {
    for (const c of d.contact) {
      assert(Number.isFinite(c.ra) && c.ra >= 0 && c.ra < 360, `ra у ${c.id}`);
      assert(Number.isFinite(c.dec) && c.dec >= -90 && c.dec <= 90, `dec у ${c.id}`);
      assert(Array.isArray(c.observations) && c.observations.length === 3, `observations у ${c.id}`);
      const dates = c.observations.map((o) => o.date);
      const srcs = c.observations.map((o) => o.source);
      for (const o of c.observations) {
        assert(typeof o.date === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(o.date), `дата у ${c.id}`);
        assert(Number.isFinite(Date.parse(o.date)), `некорректная UTC-дата у ${c.id}`);
        assert(typeof o.filter === 'string' && o.filter, `фильтр у ${c.id}`);
        assert(typeof o.exposure === 'number' && o.exposure > 0, `выдержка у ${c.id}`);
        assert(typeof o.mjd === 'number', `mjd у ${c.id}`);
        assert(typeof o.source === 'string' && o.source.startsWith('https://'), `источник FITS у ${c.id}`);
      }
      assert(new Set(dates).size === 3, `даты различаются у ${c.id}`);
      assert(new Set(srcs).size === 3, `три разных файла-источника у ${c.id}`);
      assert(c.source && c.source.label && String(c.source.url).startsWith('https://')
        && typeof c.source.credit === 'string' && c.source.credit.length > 10, `source у ${c.id}`);
      assert(typeof c.evidence === 'string' && c.evidence.length > 10, `evidence у ${c.id}`);
      assert(typeof c.limitations === 'string' && c.limitations.length > 10, `limitations у ${c.id}`);
      if (c.photometry !== undefined && c.photometry !== null) {
        assert(typeof c.photometry.note === 'string' && c.photometry.note
          && Array.isArray(c.photometry.epochs) && c.photometry.epochs.length === 3,
          `photometry у ${c.id}`);
      }
    }
  });
  check('демо: все 200 полей без выдуманной классификации (unresolved/uncertain)', () => {
    for (const c of d.demo) {
      assertEq(c.type, 'unresolved', `demo type у ${c.id}`);
      assertEq(c.expectedVerdict, 'uncertain', `demo expectedVerdict у ${c.id}`);
    }
  });
  check('shortIds: 6 уникальных id из contact, состав совпадает с meta.short_composition', () => {
    const byId = new Map(d.contact.map((c) => [c.id, c]));
    assert(d.shortIds.length === 6 && new Set(d.shortIds).size === 6
      && d.shortIds.every((id) => byId.has(id)), `shortIds=${JSON.stringify(d.shortIds)}`);
    const sc = d.meta.short_composition;
    if (sc && typeof sc === 'object') {
      const counts = {};
      for (const id of d.shortIds) counts[byId.get(id).type] = (counts[byId.get(id).type] || 0) + 1;
      assertEq(counts, Object.fromEntries(Object.entries(sc).map(([k, v]) => [k, Number(v)])),
        'состав shortIds против meta.short_composition');
    }
  });
  check('meta: синтетика выключена, счёт предвычислен, пороги и формула сохранены', () => {
    const m = d.meta;
    assertEq(m.synthetic, false, 'synthetic');
    assertEq(m.precomputed, true, 'precomputed');
    assert(m.thresholds && m.thresholds.soft === 1.0 && m.thresholds.strict === 3.0,
      `thresholds=${JSON.stringify(m.thresholds)}`);
    assert(typeof m.score_formula === 'string' && m.score_formula.length > 5, 'score_formula');
  });
  check('meta: происхождение — обучение, набор данных и благодарности обзора', () => {
    const m = d.meta;
    assert(m.training && m.training.n_rows === 300 && typeof m.training.rule === 'string'
      && m.training.rule && /^[0-9a-f]{64}$/.test(m.training.digest || ''),
      `training=${JSON.stringify(m.training)}`);
    assert(m.dataset && typeof m.dataset.manifest === 'string' && m.dataset.manifest
      && /^[0-9a-f]{64}$/.test(m.dataset.manifest_sha256 || '')
      && typeof m.dataset.survey === 'string' && m.dataset.survey,
      `dataset=${JSON.stringify(m.dataset)}`);
    assert(m.acknowledgments && typeof m.acknowledgments === 'object'
      && Object.values(m.acknowledgments).every((v) => typeof v === 'string' && v.length > 10),
      `acknowledgments=${JSON.stringify(m.acknowledgments)}`);
  });
  check('GameSession на реальных данных: бюджеты и подмножества', () => {
    const g = new GameSession(d, 'full');
    assertEq(g.budget, 3, 'full budget');
    assertEq(g.cases.length, 12, 'full cases');
    const s = new GameSession(d, 'short');
    assertEq(s.budget, 1, 'short budget');
    assertEq(s.cases.map((c) => c.id), d.shortIds, 'short cases');
  });
  check('имена участков уникальны', () => {
    const names = d.contact.map((c) => c.name);
    assertEq(new Set(names).size, names.length, 'уникальность');
  });
}

/* ---------- main ---------- */

const argv = process.argv.slice(2);
if (argv.includes('--dump')) {
  dumpData();
} else {
  console.log(`model.js: ${MODEL}`);
  runFixtureTests();
  runRealDataTests();
  console.log(`\nПроверок пройдено: ${passed}, провалено: ${failures.length}`);
  if (failures.length) {
    console.error('ПРОВАЛЫ МОДЕЛИ:');
    for (const f of failures) console.error(` - ${f.name}: ${f.error}`);
    process.exit(1);
  }
  console.log('МОДЕЛЬ OK');
}
