#!/usr/bin/env python3
"""Браузерная группа приёмки: реальный Chromium/Firefox по РЕАЛЬНОМУ flow app/game.js.

Принципы (после сверки с фактической реализацией UI):
  • клики идут только по настоящим активным управлениям; если открыт #dialog —
    кликаем только внутри диалога (глобальные кнопки под модальным слоем инертны);
  • проверяются потребительские исходы, а не факты клика: третий кадр появляется
    после заявки или явного раскрытия разбора (до них кнопки эпохи 3/пар с кадром 3 ОТСУТСТВУЮТ),
    ползунок compare реально двигает границу (--split), blink реально чередует
    кадры, таймер реально ставится на паузу и сбрасывается, рейтинг ведущего
    реально пересчитывается по порогу, истории — все шесть, реальные снимки — все три
    с дословными атрибуциями;
  • повторная заявка и пересмотры проверяются на модели (кнопки disabled/скрыты
    в UI — их не «кликают»);
  • офлайн: внешние запросы блокируются и обязаны быть равны нулю; ошибок
    консоли и необработанных исключений на странице не бывает.

Запуск (обычно из check_release.py):
  tools/check_browser.py [--app DIR] [--dist DIR] [--installed DIR] [--out DIR] [--engine auto|chromium|firefox]
Результаты: <out>/browser-results.json, скриншоты <out>/screenshots/, сеть <out>/network.json.
Коды выхода: 0 — всё прошло; 1 — есть провалы; 3 — браузер недоступен.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import tempfile
import sys
import threading
import time
import zipfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from verify_common import APP, DIST, ROOT, CheckResults, chromium_executable, eprint, firefox_executable  # noqa: E402

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout  # noqa: E402

ALL: list[tuple[str, CheckResults]] = []


def file_url(p: Path) -> str:
    return p.as_uri()


def group(title: str) -> CheckResults:
    res = CheckResults(title)
    ALL.append((title, res))
    return res


def safe(fn, *a) -> None:
    """Изоляция групп: падение одной не убивает остальные и запись результатов."""
    name = getattr(fn, "__name__", str(fn))
    try:
        fn(*a)
    except Exception as e:  # noqa: BLE001 — намеренно широкая страховка группы
        res = group(f"Сбой в группе {name}")
        res.add(f"{name} выполнен без исключения", False, repr(e))
        eprint(f"Группа {name} упала: {e!r}")


# ---------------------------------------------------------------- базовые помощники

def wait_game(page, timeout: int = 20000) -> None:
    page.wait_for_function("() => window.game && window.game.state", timeout=timeout)


def state(page):
    return page.evaluate("() => window.game.state")


def game_eval(page, expr: str):
    return page.evaluate(f"() => {{ const g = window.game; return ({expr}); }}")


def dialog_open(page) -> bool:
    return bool(page.evaluate("() => { const d = document.getElementById('dialog'); return !!d && d.open; }"))


def click_ui(page, res: CheckResults, action: str, value=None, id_: str | None = None,
             timeout: int = 6000) -> bool:
    """Клик только по реально доступному управлению: в открытом диалоге —
    только его кнопки, иначе — кнопки страницы. Иначе честный провал."""
    in_dialog = dialog_open(page)
    base = "#dialog" if in_dialog else "#app"
    s = f'{base} [data-action="{action}"]'
    if value is not None:
        s += f'[data-value="{value}"]'
    if id_ is not None:
        s += f'[data-id="{id_}"]'
    loc = page.locator(s)
    if loc.count() == 0:
        res.add(f"клик {action}" + (f"={value}" if value is not None else ""), False,
                f"кнопка недоступна ({'открыт диалог' if in_dialog else 'страница'}): {s}")
        return False
    loc.first.click(timeout=timeout)
    return True


def close_dialog(page, res: CheckResults) -> bool:
    if not dialog_open(page):
        return True
    return click_ui(page, res, "close-dialog")


def open_results(page, res: CheckResults) -> None:
    """Общий разбор с явным подтверждением, если остались дела без версии."""
    click_ui(page, res, "finish")
    if dialog_open(page) and page.locator('#dialog [data-action="confirm-finish"]').count():
        click_ui(page, res, "confirm-finish")


def wait_page(page, name: str, timeout: int = 8000) -> None:
    page.wait_for_function(f"() => window.game.state.page === '{name}'", timeout=timeout)


def open_inspect_from_overview(page, res: CheckResults, cid: str | None = None) -> None:
    """Реальный путь к осмотру: с обзора — observe (или карточка, которая тоже
    ведёт к осмотру). Ждём перелёт карты, если он есть."""
    if dialog_open(page):
        close_dialog(page, res)
    if state(page)["page"] == "inspect":
        click_ui(page, res, "back")
        wait_page(page, "overview")
    if cid is not None and game_eval(page, "g.state.focus") != cid:
        if state(page)["view"] != "cards":
            click_ui(page, res, "nav-cards")
            page.wait_for_function("() => window.game.state.view === 'cards'", timeout=6000)
        click_ui(page, res, "select", id_=cid)
    else:
        click_ui(page, res, "observe")
    try:
        wait_page(page, "inspect", timeout=9000)
    except PWTimeout:
        click_ui(page, res, "observe")
        wait_page(page, "inspect")


def next_undecided(page, res: CheckResults) -> None:
    """Кнопка «Следующий участок» после сохранённой версии."""
    click_ui(page, res, "next")
    wait_page(page, "inspect", timeout=9000)


def int_of(text: str) -> int | None:
    m = re.search(r"-?\d+", text or "")
    return int(m.group()) if m else None


def screenscan(page) -> dict:
    return page.evaluate("""() => {
        const t = document.body.innerText || '';
        return { prog: /\\d+\\s*\\/\\s*(6|12)\\b/.test(t) };
    }""")


def assert_screen_chrome(page, res: CheckResults, where: str) -> None:
    sc = screenscan(page)
    res.add(f"{where}: нумерованный прогресс",
            sc["prog"], json.dumps(sc))


def canvas_fingerprint(page) -> str | None:
    return page.evaluate("""() => {
        const c = document.querySelector('#map-host canvas.sky-canvas, #map-host canvas');
        if (!c) return null;
        let h = 0;
        const d = c.toDataURL ? c.toDataURL() : '';
        for (let i = 0; i < d.length; i += 97) h = (h * 31 + d.charCodeAt(i)) | 0;
        const root = c.closest('.sky-map') || c.parentElement;
        return JSON.stringify([d.length, h, c.style.transform, root && root.getAttribute('style')]);
    }""")


def overflow_px(page) -> int:
    return page.evaluate("() => document.scrollingElement.scrollWidth - window.innerWidth")


def shot(page, out: Path, name: str) -> None:
    p = out / "screenshots" / f"{name}.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(p), full_page=True)


class Session:
    """Контекст браузера с блокировкой внешних запросов и журналом ошибок."""

    def __init__(self, browser, out: Path, name: str, allow_prefixes=(), **ctx_opts):
        self.name = name
        self.out = out
        self.violations: list[str] = []
        self.console_errors: list[str] = []
        self.pageerrors: list[str] = []
        self.allow = list(allow_prefixes)
        self.ctx = browser.new_context(**ctx_opts)

        def route(r):
            u = r.request.url
            if u.startswith(("file://", "data:", "blob:", "about:")) or any(u.startswith(p) for p in self.allow):
                r.continue_()
            else:
                self.violations.append(f"{r.request.method} {u}")
                r.abort()

        self.ctx.route("**/*", route)
        self.page = self.ctx.new_page()
        self.page.on("console", lambda m: self.console_errors.append(m.text) if m.type == "error" else None)
        self.page.on("pageerror", lambda e: self.pageerrors.append(str(e)))

    def goto(self, url: str):
        self.page.goto(url, wait_until="load")
        wait_game(self.page)

    def boot_full(self, res: CheckResults, app: Path, mode: str = "full") -> None:
        self.goto(file_url(app / "index.html"))
        click_ui(self.page, res, f"start-{mode}")
        wait_page(self.page, "briefing")
        click_ui(self.page, res, "begin")
        wait_page(self.page, "overview")

    def assert_clean(self, res: CheckResults, label: str) -> None:
        res.add(f"{label}: нет запросов во внешнюю сеть", not self.violations, str(self.violations[:3]))
        res.add(f"{label}: нет ошибок консоли", not self.console_errors, str(self.console_errors[:3]))
        res.add(f"{label}: нет необработанных исключений страницы", not self.pageerrors, str(self.pageerrors[:3]))

    def close(self):
        self.out.mkdir(parents=True, exist_ok=True)
        with open(self.out / "network.json", "a", encoding="utf-8") as f:
            f.write(json.dumps({"session": self.name, "blocked": self.violations,
                                "console_errors": self.console_errors,
                                "pageerrors": self.pageerrors}, ensure_ascii=False) + "\n")
        self.ctx.close()


# ---------------------------------------------------------------- группы

def g_landing(browser, out: Path, app: Path):
    res = group("Запуск: приветствие, выбор режима, проводка модели")
    s = Session(browser, out, "landing")
    try:
        s.goto(file_url(app / "index.html"))
        res.add("window.game — экземпляр GameSession в полном режиме",
                game_eval(s.page, "g instanceof GameSession && g.state.mode === 'full' && g.cases.length === 12"),
                json.dumps(game_eval(s.page, "{mode: g.state.mode, n: g.cases.length}")))
        for act, mode in (("start-full", "full"), ("start-short", "short")):
            btn = s.page.locator(f'[data-action="{act}"]')
            if res.add(f"кнопка {act} видна", btn.count() == 1 and btn.first.is_visible()):
                btn.first.click()
                wait_page(s.page, "briefing")
                res.add(f"{act} переключает модель в {mode} и открывает брифинг",
                        game_eval(s.page, f"g.state.mode === '{mode}' && g.budget === {3 if mode == 'full' else 1}"))
                # возвращаемся к приветствию честным путём: новая группа → подтверждение
                if s.page.locator('[data-action="new-group"]').count():
                    click_ui(s.page, res, "new-group")
                    click_ui(s.page, res, "confirm-reset")
                    s.page.wait_for_timeout(200)
        res.add("шапка несёт истории и пульт ведущего",
                s.page.locator('[data-action="stories"]').count() >= 1
                and s.page.locator('[data-action="presenter"]').count() >= 1)
        res.add("нет переключателя вариантов прототипа",
                s.page.locator("[data-variant], a[href*='prototype']").count() == 0)
        res.add("живой регион #announce aria-live=polite",
                s.page.evaluate("() => { const a = document.getElementById('announce'); return !!a && a.getAttribute('aria-live') === 'polite'; }"))
        s.assert_clean(res, "landing")
    finally:
        s.close()


def _map_group(browser, out: Path, app: Path):
    res = group("Обзор: карта и карточки — одна сессия, перелёт к осмотру")
    s = Session(browser, out, "overview")
    try:
        s.boot_full(res, app)
        res.add("карта в #map-host с canvas", s.page.locator("#map-host .sky-map").count() == 1
                and s.page.locator("#map-host canvas").count() >= 1)
        res.add("canvas скрыт от скринридера",
                s.page.evaluate("() => { const c = document.querySelector('#map-host canvas'); return !!c && c.getAttribute('aria-hidden') === 'true'; }"))
        sectors = s.page.locator("#map-host [data-sector]")
        res.add("12 кнопок-участков с уникальными доступными именами",
                sectors.count() == 12 and s.page.evaluate(
                    """() => { const n = [...document.querySelectorAll('#map-host [data-sector]')]
                        .map(b => (b.getAttribute('aria-label') || b.innerText || '').trim());
                        return n.every(Boolean) && new Set(n).size === 12; }"""))
        kinds = s.page.evaluate("() => [...document.querySelectorAll('#map-host [data-map-action]')].map(b => b.getAttribute('data-map-action'))")
        res.add("управления карты in/out/home/skip/anim на месте", {"in", "out", "home", "skip", "anim"} <= set(kinds), str(kinds))
        fp0 = canvas_fingerprint(s.page)
        s.page.locator('[data-map-action="in"]').first.click()
        s.page.wait_for_timeout(350)
        res.add("зум видимо меняет сцену", fp0 is not None and canvas_fingerprint(s.page) != fp0)
        vp = s.page.evaluate("""() => {
            const c = [...document.querySelectorAll('#map-host .sky-map [tabindex]')]
                .filter(el => el.tagName !== 'BUTTON' && !el.disabled);
            if (!c.length) return null;
            c[0].focus();
            return c[0].tagName + '/' + c[0].getAttribute('tabindex');
        }""")
        if res.add("фокусируемый контейнер карты для клавиатурной панорамы", bool(vp), str(vp)):
            fpv0 = canvas_fingerprint(s.page)
            for _ in range(2):
                s.page.keyboard.press("ArrowLeft")
                s.page.wait_for_timeout(150)
            res.add("стрелки панорамируют сцену", canvas_fingerprint(s.page) != fpv0)

        s.page.locator('[data-map-action="home"]').click()
        sector_ids = s.page.evaluate("() => [...document.querySelectorAll('#map-host [data-sector]')].map(b => b.getAttribute('data-sector'))")
        target = sector_ids[2]
        s.page.locator(f'#map-host [data-sector="{target}"]').click()
        try:
            wait_page(s.page, "inspect", timeout=9000)  # перелёт, затем осмотр
        except PWTimeout:
            pass
        s.page.wait_for_function(f"() => window.game.state.focus === '{target}'", timeout=3000)
        res.add("выбор на карте открывает осмотр выбранного участка",
                state(s.page)["page"] == "inspect" and game_eval(s.page, "g.state.focus") == target,
                json.dumps({"page": state(s.page)["page"], "focus": game_eval(s.page, "g.state.focus")}))
        shot(s.page, out, "overview-map-select")
        click_ui(s.page, res, "back")
        wait_page(s.page, "overview")

        click_ui(s.page, res, "nav-cards")
        s.page.wait_for_function("() => window.game.state.view === 'cards'", timeout=6000)
        res.add("карточки: 12 .sector-card, фокус общий",
                s.page.locator("#cards .sector-card").count() == 12
                and game_eval(s.page, "g.state.focus") == target)
        other = sector_ids[5]
        s.page.locator(f'[data-action="select"][data-id="{other}"]').click()
        try:
            wait_page(s.page, "inspect", timeout=9000)
        except PWTimeout:
            pass
        s.page.wait_for_function(f"() => window.game.state.focus === '{other}'", timeout=3000)
        res.add("карточка открывает осмотр и меняет фокус",
                state(s.page)["page"] == "inspect" and game_eval(s.page, "g.state.focus") == other)
        shot(s.page, out, "overview-cards-select")
        click_ui(s.page, res, "back")
        click_ui(s.page, res, "nav-map")
        s.page.wait_for_function("() => window.game.state.view === 'map'", timeout=6000)
        res.add("возврат к карте сохраняет выбранный участок", game_eval(s.page, "g.state.focus") == other)
        assert_screen_chrome(s.page, res, "обзор")
        s.assert_clean(res, "overview")
    finally:
        s.close()


def g_inspection(browser, out: Path, app: Path):
    res = group("Осмотр: реальные инструменты, защита кадра 3, заявка, пересмотры")
    s = Session(browser, out, "inspect")
    try:
        s.boot_full(res, app)
        open_inspect_from_overview(s.page, res)
        cid = game_eval(s.page, "g.state.focus")
        frames = game_eval(s.page, "g.cases.find(c => c.id === g.state.focus).frames")
        f0, f1, f2 = frames
        res.add("осмотр смонтирован в #inspection с научными data-URI снимками",
                s.page.locator("#inspection").count() == 1
                and s.page.evaluate("() => [...document.querySelectorAll('#inspection img')].every(i => i.src.startsWith('data:image/'))"))
        res.add("кадры реально декодируются (naturalWidth>0) во всех открытых <img>",
                s.page.evaluate("() => [...document.querySelectorAll('#inspection img')].every(i => i.complete && i.naturalWidth > 0)"))
        res.add("в данных участка три наблюдения с реальными UTC-датами и фильтрами",
                game_eval(s.page, """(() => {
                    const c = g.cases.find(c => c.id === g.state.focus);
                    return Array.isArray(c.observations) && c.observations.length === 3
                        && c.observations.every(o => /^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(?:Z|\\+00:00)$/.test(o.date)
                            && Number.isFinite(Date.parse(o.date))
                            && typeof o.filter === 'string' && o.filter.length > 0
                            && typeof o.exposure === 'number' && o.exposure > 0);
                })()"""), json.dumps(game_eval(s.page, "g.cases.find(c => c.id === g.state.focus).observations.map(o => ({date: o.date, filter: o.filter, exposure: o.exposure}))")))

        # --- пара по умолчанию: два снимка 1 и 2, без #comparison ---
        res.add("пара по умолчанию: снимки 1 и 2, ползунка нет",
                s.page.evaluate("() => [...document.querySelectorAll('.photo-pair img')].map(i => i.getAttribute('src'))") == [f0, f1]
                and s.page.locator("#comparison").count() == 0)
        res.add("до заявки из пар доступна только «1 и 2»",
                s.page.evaluate("() => [...document.querySelectorAll('[data-action=pair]')].map(b => b.dataset.value)") == ["0,1"],
                "пары с кадром 3 видны до проверки!")

        # --- подсказка алгоритма: настоящий диалог, фазу не трогает ---
        rem_before = game_eval(s.page, "g.remaining")
        click_ui(s.page, res, "hint")
        hint_shown = dialog_open(s.page) and "hint-dialog" in (s.page.get_attribute("#dialog", "class") or "")
        score_txt = game_eval(s.page, "String(Number(g.cases.find(c => c.id === g.state.focus).score.toFixed(2))).replace('.', ',')")
        res.add("подсказка открывает диалог с оценкой участка (формат счёта)",
                hint_shown and score_txt in (s.page.inner_text("#dialog")),
                f"ожидали {score_txt}")
        res.add("подсказка записана в модели, жетоны и фаза не тронуты",
                cid in game_eval(s.page, "g.state.hints")
                and game_eval(s.page, "g.remaining") == rem_before
                and state(s.page)["page"] == "inspect")
        close_dialog(s.page, res)
        res.add("диалог подсказки закрывается", not dialog_open(s.page))

        # --- «по одному»: эпохи 1–2 доступны, третьей кнопки НЕТ до заявки ---
        click_ui(s.page, res, "tool", value="single")
        epochs = s.page.evaluate("() => [...document.querySelectorAll('[data-action=epoch]')].map(b => b.dataset.value)")
        res.add("до заявки кнопки эпох: только 1 и 2 (кадр 3 отсутствует)", epochs == ["0", "1"], str(epochs))
        click_ui(s.page, res, "epoch", value="0")
        src0 = s.page.get_attribute(".scope .base-image", "src")
        click_ui(s.page, res, "epoch", value="1")
        src1 = s.page.get_attribute(".scope .base-image", "src")
        res.add("переключение эпох меняет показанный снимок", src0 == f0 and src1 == f1,
                f"{src0[-16:]} → {src1[-16:]}")

        # --- ползунок: только у compare, реально двигает границу (клавиатура) ---
        click_ui(s.page, res, "tool", value="compare")
        res.add("ползунок #comparison появляется только в режиме «Ползунок»",
                s.page.locator("#comparison").count() == 1)
        s.page.locator("#comparison").focus()
        s.page.keyboard.press("Home")
        s.page.keyboard.press("ArrowRight")
        s.page.wait_for_timeout(120)
        clip = s.page.evaluate("() => getComputedStyle(document.querySelector('.overlay-image')).clipPath")
        split_css = s.page.evaluate("() => getComputedStyle(document.querySelector('.scope')).getPropertyValue('--split').trim()")
        res.add("клавиши ползунка двигают границу кадров (значение 1)",
                s.page.input_value("#comparison") == "1",
                f"value={s.page.input_value('#comparison')}")
        res.add("граница реально переклипает оверлей: --split на .scope и clipPath оверлея",
                split_css == "1%" and "99%" in clip,
                f"--split={split_css}, clipPath={clip}")
        res.add("экран показывает границу в процентах (#split-output)",
                s.page.inner_text("#split-output").strip() == "1%")

        # --- мигание: кадры действительно чередуются ---
        click_ui(s.page, res, "tool", value="blink")
        seq = []
        for _ in range(3):
            seq.append((s.page.get_attribute(".scope .base-image", "src"),
                        s.page.inner_text("#blink-epoch")))
            s.page.wait_for_timeout(950)
        res.add("мигание реально чередует два кадра", len({x[0] for x in seq}) >= 2
                and {x[0] for x in seq} == {f0, f1}, str([x[1] for x in seq]))
        click_ui(s.page, res, "tool", value="pair")

        # --- первое впечатление + правка через настоящий диалог ---
        click_ui(s.page, res, "predict", value="changed")
        res.add("впечатление записано (receipt показывает выбор)",
                game_eval(s.page, "g.state.predictions[g.state.focus]") == "changed"
                and "Вижу изменение" in s.page.inner_text(".flow-actions"))
        click_ui(s.page, res, "edit-prediction")
        click_ui(s.page, res, "change-prediction", value="same")
        res.add("впечатление пересматривается через «Изменить»",
                game_eval(s.page, "g.state.predictions[g.state.focus]") == "same"
                and "Не вижу изменения" in s.page.inner_text(".flow-actions"))

        # --- заявка: третий кадр появляется, повтор списания исключён ---
        res.add("заявка доступна и тратит жетон", click_ui(s.page, res, "request")
                and game_eval(s.page, "g.state.checked") == [cid]
                and game_eval(s.page, "g.remaining") == rem_before - 1)
        res.add("#remaining отражает остаток заявок",
                int_of(s.page.inner_text("#remaining")) == game_eval(s.page, "g.remaining"))
        after_srcs = s.page.evaluate("() => [...document.querySelectorAll('.photo-pair img')].map(i => i.getAttribute('src'))")
        res.add("после заявки показаны снимки 2 и 3 (третий кадр реально открыт)",
                after_srcs == [f1, f2], str([x[-12:] for x in after_srcs]))
        repeat = game_eval(s.page, f"g.request('{cid}')")
        res.add("повторная заявка на модели без двойного списания",
                repeat is True and game_eval(s.page, "g.state.checked.length") == 1)
        remaining_before_repeat = game_eval(s.page, "g.remaining")
        click_ui(s.page, res, "request")
        res.add("повторное открытие третьего кадра через UI бесплатно",
                game_eval(s.page, "g.remaining") == remaining_before_repeat
                and game_eval(s.page, "g.state.checked.length") == 1)
        click_ui(s.page, res, "tool", value="single")
        res.add("после заявки кнопка кадра 3 существует и работает",
                s.page.locator('[data-action="epoch"][data-value="2"]').count() == 1)
        click_ui(s.page, res, "epoch", value="2")
        res.add("кадр 3 переключается в «по одному»",
                s.page.get_attribute(".scope .base-image", "src") == f2)
        click_ui(s.page, res, "tool", value="pair")
        shot(s.page, out, "inspect-third-frame")

        # --- версия: сохранение, пересмотр sky→…→artifact через «Пересмотреть» ---
        click_ui(s.page, res, "decide", value="uncertain")
        res.add("версия сохранена, доступен пересмотр",
                game_eval(s.page, "g.state.decisions[g.state.focus]") == "uncertain"
                and s.page.locator('[data-action="revise"]').is_visible()
                and s.page.inner_text(".receipt.saved strong") ==
                    s.page.evaluate("window.GAME_CONTENT.verdicts.uncertain"))
        click_ui(s.page, res, "revise")
        click_ui(s.page, res, "decide", value="artifact")
        res.add("пересмотр заменяет прежнюю версию",
                game_eval(s.page, "g.state.decisions[g.state.focus]") == "artifact"
                and s.page.locator('[data-action="revise"]').is_visible()
                and s.page.inner_text(".receipt.saved strong") ==
                    s.page.evaluate("window.GAME_CONTENT.verdicts.artifact"))

        # --- зум: настоящий диалог, доступны только открытые кадры ---
        click_ui(s.page, res, "zoom")
        res.add("зум открывает диалог с увеличенным снимком",
                dialog_open(s.page) and (s.page.get_attribute("#dialog .zoom-image", "src") or "").startswith("data:image/"))
        zoom_epochs = s.page.evaluate("() => [...document.querySelectorAll('#dialog [data-action=zoom-epoch]')].map(b => b.dataset.value)")
        res.add("в зуме только реально открытые кадры (1–3 после заявки)", zoom_epochs == ["0", "1", "2"], str(zoom_epochs))
        close_dialog(s.page, res)
        assert_screen_chrome(s.page, res, "осмотр")
        s.assert_clean(res, "inspect")
    finally:
        s.close()


def g_presenter(browser, out: Path, app: Path):
    res = group("Пульт ведущего: порог, рейтинг, таймер; реальные снимки и истории")
    s = Session(browser, out, "presenter")
    try:
        s.boot_full(res, app)
        click_ui(s.page, res, "presenter")
        res.add("пульт ведущего открыт как диалог",
                dialog_open(s.page) and "presenter-dialog" in (s.page.get_attribute("#dialog", "class") or ""))

        # --- рейтинг: 12 строк по убыванию счёта, как в данных ---
        rows = s.page.evaluate("""() => [...document.querySelectorAll('#dialog #ranking tr')]
            .map(tr => [...tr.querySelectorAll('td')].map(td => td.innerText.trim()))""")
        expected_names = game_eval(s.page,
            "[...g.cases].sort((a,b) => b.score-a.score).map(c => c.name)")
        res.add("рейтинг содержит все участки в порядке убывания оценки",
                [row[0] for row in rows] == expected_names,
                f"строк={len(rows)}")

        # --- порог: пресеты и ползунок реально пересчитывают отбор ---
        click_ui(s.page, res, "threshold", value="3")
        passes3 = s.page.evaluate("() => document.querySelectorAll('#dialog #ranking tr.passes').length")
        expect3 = game_eval(s.page, "g.cases.filter(c => c.score >= 3).length")
        res.add("строгий порог 3: модель, поле и отметки «Отобран» согласованы",
                game_eval(s.page, "g.state.threshold") == 3
                and s.page.input_value("#threshold") == "3" and passes3 == expect3,
                f"passes={passes3}, ожидалось {expect3}")
        click_ui(s.page, res, "threshold", value="1")
        passes1 = s.page.evaluate("() => document.querySelectorAll('#dialog #ranking tr.passes').length")
        expect1 = game_eval(s.page, "g.cases.filter(c => c.score >= 1).length")
        res.add("мягкий порог 1: пересчёт согласован",
                game_eval(s.page, "g.state.threshold") == 1 and passes1 == expect1,
                f"passes={passes1}, ожидалось {expect1}")
        s.page.evaluate("() => { const el = document.querySelector('#threshold'); el.value = 2.5; el.dispatchEvent(new Event('input', {bubbles: true})); }")
        res.add("ползунок порога проводит значение в модель и вывод",
                game_eval(s.page, "g.state.threshold") == 2.5
                and s.page.inner_text("#threshold-output").strip() == "2,50")

        # --- таймер ведущего: реальная пауза и сброс ---
        s.page.wait_for_timeout(1200)
        t1 = game_eval(s.page, "g.elapsed()")
        res.add("таймер идёт со старта смены (elapsed-up)", t1 > 1000, f"{t1:.0f} мс")
        click_ui(s.page, res, "timer-toggle")
        e_a = game_eval(s.page, "g.elapsed()")
        s.page.wait_for_timeout(700)
        e_b = game_eval(s.page, "g.elapsed()")
        res.add("пауза таймера реально останавливает счёт",
                game_eval(s.page, "g.state.timerStartedAt") is None and e_a == e_b
                and "Запустить" in s.page.inner_text('[data-action="timer-toggle"]'),
                f"{e_a} == {e_b}")
        click_ui(s.page, res, "timer-reset")
        s.page.wait_for_timeout(600)  # интервал дисплея — 500 мс
        res.add("сброс таймера обнуляет время: диалог и строка миссии",
                game_eval(s.page, "g.elapsed()") == 0
                and s.page.inner_text("[data-timer]").strip() == "00:00"
                and s.page.evaluate("() => document.querySelector('body #timer') && document.querySelector('#timer').innerText.trim() === '00:00'"))

        # --- настоящие наблюдения: три лицензионных снимка загружены, атрибуции дословные ---
        click_ui(s.page, res, "real")
        s.page.wait_for_function("""() => {
            const images = [...document.querySelectorAll('#dialog .real-example img')];
            return images.length === 3 && images.every(i => i.complete && i.naturalWidth > 0);
        }""")
        credits = s.page.evaluate("""() => [...document.querySelectorAll('#dialog .real-example')].map(a => ({
            img: a.querySelector('img') ? a.querySelector('img').naturalWidth : -1,
            credit: (a.querySelector('.attribution') || {innerText: ''}).innerText }))
        """)
        all_credits = " ".join(c["credit"] for c in credits)
        res.add("настоящие наблюдения: все 3 снимка загружены (naturalWidth>0)",
                len(credits) == 3 and all(c["img"] > 0 for c in credits),
                json.dumps([c["img"] for c in credits]))
        res.add("атрибуции дословные: Martín, Riess/SH0ES, STScI",
                all(k in all_credits for k in ("P. G. Martín", "A. Riess and the SH0ES team", "NASA, ESA, STScI.")),
                all_credits[:120])
        shot(s.page, out, "real-examples")
        close_dialog(s.page, res)

        # Every selected story must show its own account, not another story's observations.
        click_ui(s.page, res, "presenter")
        click_ui(s.page, res, "stories")
        stories = s.page.evaluate("window.GAME_CONTENT.stories.map(s => ({title:s.title, kind:s.kind}))")
        for index, story in enumerate(stories):
            click_ui(s.page, res, "story", value=str(index))
            res.add(f"история {index + 1}: выбранный рассказ и соответствующий вид данных",
                    s.page.inner_text("#dialog .story-title") == story["title"]
                    and s.page.locator(f'[data-action="story"][data-value="{index}"]').get_attribute("aria-pressed") == "true"
                    and s.page.locator("#dialog .lightcurve").count() == int(story["kind"] == "kepler")
                    and s.page.locator("#dialog .story-observations").count() == int(story["kind"] == "supernova"))
        shot(s.page, out, "stories-ai")
        close_dialog(s.page, res)
        s.assert_clean(res, "presenter")
    finally:
        s.close()


def g_case_review(browser, out: Path, app: Path):
    res = group("Разбор одного дела, раскрытие ответов и завершение смены")
    for mode in ("short", "full"):
        s = Session(browser, out, f"review-{mode}", viewport={"width": 1440, "height": 1000})
        try:
            s.boot_full(res, app, mode)
            click_ui(s.page, res, "nav-cards")
            click_ui(s.page, res, "select", id_="s01")
            res.add(f"{mode}: ответ нельзя раскрыть до своей версии",
                    s.page.locator('[data-action="review-case"]').count() == 0)
            click_ui(s.page, res, "predict", value="unsure")
            click_ui(s.page, res, "decide", value="uncertain")
            remaining = game_eval(s.page, "g.remaining")
            click_ui(s.page, res, "review-case")
            s.page.wait_for_function("() => [...document.querySelectorAll('#dialog img')].every(i => i.complete && i.naturalWidth > 0)")
            res.add(f"{mode}: разбор раскрывает только выбранное дело и три кадра",
                    s.page.locator('#dialog .result-card[data-case-id="s01"]').count() == 1
                    and s.page.locator('#dialog .result-card').count() == 1
                    and s.page.locator('#dialog .result-photos img').count() == 3
                    and game_eval(s.page, "Object.keys(g.state.revealed).join(',')") == "s01")
            res.add(f"{mode}: разбор не тратит заявку и показывает исходную версию",
                    game_eval(s.page, "g.remaining") == remaining
                    and game_eval(s.page, "g.state.checked.length") == 0
                    and "Недостаточно данных" in s.page.inner_text('#dialog .result-card'))
            shot(s.page, out, f"review-{mode}-case")
            close_dialog(s.page, res)
            s.page.wait_for_function("document.activeElement.dataset.action === 'review-case'", timeout=3000)
            res.add(f"{mode}: закрытие возвращает фокус на кнопку разбора",
                    s.page.evaluate("document.activeElement.dataset.action") == "review-case")
            res.add(f"{mode}: третий кадр доступен в сравнении после разбора",
                    s.page.locator('[data-action="pair"][data-value="1,2"]').count() == 1
                    and "Третий кадр открыт в разборе" in s.page.inner_text('.route-steps'))
            click_ui(s.page, res, "revise")
            click_ui(s.page, res, "decide", value="stable")
            click_ui(s.page, res, "review-case")
            txt = s.page.inner_text('#dialog .result-card')
            res.add(f"{mode}: исходная и уточнённая версии различимы",
                    "Ваша версия до разбора: Недостаточно данных" in txt
                    and "Уточнённая версия: Заметных изменений нет" in txt
                    and game_eval(s.page, "g.state.revealed.s01") == "uncertain")
            close_dialog(s.page, res)
            before = state(s.page)
            click_ui(s.page, res, "finish")
            res.add(f"{mode}: ранний итог предупреждает о раскрытии всей смены",
                    dialog_open(s.page) and s.page.locator('#dialog [data-action="confirm-finish"]').count() == 1
                    and state(s.page) == before)
            close_dialog(s.page, res)
            res.add(f"{mode}: отмена общего раскрытия сохраняет состояние", state(s.page) == before)
            click_ui(s.page, res, "back")
            click_ui(s.page, res, "select", id_="s02")
            res.add(f"{mode}: соседнее дело сохраняет цену третьего кадра",
                    s.page.locator('[data-action="pair"][data-value="1,2"]').count() == 0)
            click_ui(s.page, res, "predict", value="changed")
            click_ui(s.page, res, "request")
            click_ui(s.page, res, "decide", value="sky")
            res.add(f"{mode}: настоящая заявка тратится отдельно",
                    game_eval(s.page, "g.remaining") == remaining - 1
                    and game_eval(s.page, "g.state.checked.join(',')") == "s02")
            open_results(s.page, res)
            wait_page(s.page, "results")
            count = 6 if mode == "short" else 12
            res.add(f"{mode}: подтверждение раскрывает всю смену",
                    s.page.locator('.result-card').count() == count
                    and game_eval(s.page, "Object.keys(g.state.revealed).length") == count)
            click_ui(s.page, res, "back")
            click_ui(s.page, res, "select", id_="s03")
            res.add(f"{mode}: возврат не скрывает знакомство с ответом",
                    s.page.locator('.review-notice').count() == 1
                    and game_eval(s.page, "g.hasThirdFrame('s03')")
                    and game_eval(s.page, "g.state.revealed.s03") is None)
            # Новая группа: полный маршрут в обратном порядке, без подмены состояния JS.
            click_ui(s.page, res, "new-group")
            click_ui(s.page, res, "confirm-reset")
            res.add(f"{mode}: новая группа очищает раскрытые ответы",
                    game_eval(s.page, "Object.keys(g.state.revealed).length") == 0)
            click_ui(s.page, res, f"start-{mode}")
            click_ui(s.page, res, "begin")
            click_ui(s.page, res, "nav-cards")
            ids = s.page.locator('[data-action="select"]').evaluate_all('(bs) => bs.map(b => b.dataset.id).reverse()')
            for index, cid in enumerate(ids):
                click_ui(s.page, res, "select", id_=cid)
                click_ui(s.page, res, "predict", value="unsure")
                click_ui(s.page, res, "decide", value="uncertain")
                if index < len(ids) - 1:
                    click_ui(s.page, res, "back")
            res.add(f"{mode}: последняя основная кнопка ведёт к итогам",
                    "Посмотреть итоги" in s.page.inner_text('[data-action="next"]')
                    and "primary" in (s.page.get_attribute('[data-action="next"]', 'class') or ''))
            click_ui(s.page, res, "revise")
            click_ui(s.page, res, "decide", value="stable")
            click_ui(s.page, res, "next")
            wait_page(s.page, "results")
            res.add(f"{mode}: после последней версии нет возврата по кругу",
                    state(s.page)['page'] == 'results' and s.page.locator('.result-card').count() == count)
            s.assert_clean(res, f"review-{mode}")
        finally:
            s.close()
    s = Session(browser, out, "review-narrow", viewport={"width": 390, "height": 844})
    try:
        s.boot_full(res, app, "short")
        click_ui(s.page, res, "nav-cards")
        for cid in ("s10", "s03"):
            click_ui(s.page, res, "select", id_=cid)
            click_ui(s.page, res, "predict", value="unsure")
            click_ui(s.page, res, "decide", value="uncertain")
            click_ui(s.page, res, "review-case")
            cells = s.page.locator('#dialog .case-measurements td').all_text_contents()
            if cid == "s10":
                res.add("измерение s10: 100%, ослабление примерно на 43%, возврат",
                        len(cells) == 3 and cells[0] == '100,0%' and 57 < float(cells[1].replace('%', '').replace(',', '.')) < 58)
            else:
                res.add("SN: отсутствие измерения не превращено в нулевой поток",
                        len(cells) == 3 and cells[0] == '—' and cells[1] == '100,0%'
                        and 'Изменяющаяся часть света' in s.page.inner_text('#dialog'))
            res.add(f"390px, {cid}: диалог и таблица помещаются по ширине",
                    overflow_px(s.page) <= 1 and s.page.evaluate("() => { const d=document.querySelector('#dialog'); return d.scrollWidth <= d.clientWidth + 1; }"))
            s.page.locator('#dialog .case-measurements').scroll_into_view_if_needed()
            shot(s.page, out, f"review-narrow-{cid}")
            close_dialog(s.page, res)
            click_ui(s.page, res, "back")
        s.assert_clean(res, "review-narrow")
    finally:
        s.close()


def g_completion_results(browser, out: Path, app: Path):
    res = group("Полная смена: 12 версий, 3 заявки, совет == results()")
    s = Session(browser, out, "results")
    try:
        s.boot_full(res, app)
        open_inspect_from_overview(s.page, res)
        verdicts = ["sky", "artifact", "stable", "uncertain"]
        for i in range(12):
            cid = game_eval(s.page, "g.state.focus")
            if not game_eval(s.page, f"!!g.state.predictions['{cid}']"):
                click_ui(s.page, res, "predict", value="changed")
            if i < 3 and not game_eval(s.page, f"g.state.checked.includes('{cid}')"):
                click_ui(s.page, res, "request")
            click_ui(s.page, res, "decide", value=verdicts[i % 4])
            if i < 11:
                next_undecided(s.page, res)
        res.add("12 версий записаны по маршруту «Следующий участок»",
                game_eval(s.page, "Object.keys(g.state.decisions).length") == 12)
        res.add("ровно 3 заявки за смену; 4-я отклонена моделью",
                game_eval(s.page, "g.state.checked.length") == 3
                and game_eval(s.page, "g.request(g.cases[5].id)") is False)
        rem_after = game_eval(s.page, "g.remaining")
        res.add("кнопка заявки показывает исчерпание и отключена",
                (s.page.get_attribute('[data-action="request"]', "disabled") == ""
                 or s.page.locator('[data-action="request"][disabled]').count() == 1)
                and "использованы" in s.page.inner_text('[data-action="request"]')
                and rem_after == 0,
                f"remaining={rem_after}")
        open_results(s.page, res)
        wait_page(s.page, "results")
        expected = game_eval(s.page, "g.results()")
        for key in ("found", "missed", "artifacts", "extra"):
            loc = s.page.locator(f'#summary [data-count="{key}"]')
            if not res.add(f"итог «{key}» показан", loc.count() == 1):
                continue
            dom = int_of(loc.first.inner_text())
            res.add(f"итог «{key}»: совет == results() ({expected[key]})", dom == expected[key],
                    f"DOM={dom}, модель={expected[key]}")
        card_scores = s.page.evaluate("() => [...document.querySelectorAll('.result-card .score')].map(e => e.innerText.trim())")
        model_scores = game_eval(s.page, "g.cases.map(c => Number(c.score).toFixed(2).replace('.', ','))")
        res.add("карточки совета показывают счёт алгоритма каждого участка",
                len(card_scores) == 12 and all(any(m in cs for cs in card_scores) for m in model_scores),
                f"{len(card_scores)} карточек")
        assert_screen_chrome(s.page, res, "итоги")
        shot(s.page, out, "results-full")
        s.assert_clean(res, "results")
    finally:
        s.close()


def g_dialog_reset(browser, out: Path, app: Path):
    res = group("Диалоги: новая группа — отмена ничего не меняет, подтверждение возвращает приветствие")
    s = Session(browser, out, "dialog")
    try:
        s.boot_full(res, app)
        open_inspect_from_overview(s.page, res)
        click_ui(s.page, res, "predict", value="unsure")
        click_ui(s.page, res, "request")
        click_ui(s.page, res, "decide", value="uncertain")
        before = game_eval(s.page, "({p: Object.keys(g.state.predictions).length, c: g.state.checked.length, d: Object.keys(g.state.decisions).length})")

        click_ui(s.page, res, "new-group")
        res.add("«Новая группа» открывает подтверждение", dialog_open(s.page))
        click_ui(s.page, res, "close-dialog")
        res.add("«Продолжить исследование» закрывает диалог без потерь",
                not dialog_open(s.page)
                and game_eval(s.page, "({p: Object.keys(g.state.predictions).length, c: g.state.checked.length, d: Object.keys(g.state.decisions).length})") == before
                and state(s.page)["page"] == "inspect")
        click_ui(s.page, res, "new-group")
        click_ui(s.page, res, "confirm-reset")
        s.page.wait_for_timeout(300)
        res.add("подтверждение возвращает приветствие с обеими сменами",
                not dialog_open(s.page)
                and s.page.locator('[data-action="start-full"]').count() == 1
                and s.page.locator('[data-action="start-short"]').count() == 1)
        h = game_eval(s.page, "g.state")
        res.add("модель полностью чиста после новой группы",
                not h["predictions"] and not h["decisions"] and not h["checked"]
                and not h["hints"] and h["elapsedMs"] == 0 and h["timerStartedAt"] is None
                and game_eval(s.page, "g.remaining") == 3, json.dumps(h))
        s.assert_clean(res, "dialog")
    finally:
        s.close()


def g_short_mode(browser, out: Path, app: Path):
    res = group("Короткая смена: 6 участков, 1 заявка, исчерпание видно в UI")
    s = Session(browser, out, "short")
    try:
        s.boot_full(res, app, mode="short")
        res.add("короткая смена: 6 участков на карте",
                s.page.locator("#map-host [data-sector]").count() == 6
                and game_eval(s.page, "g.budget === 1 && g.cases.length === 6"))
        open_inspect_from_overview(s.page, res)
        first = game_eval(s.page, "g.state.focus")
        click_ui(s.page, res, "predict", value="changed")
        click_ui(s.page, res, "request")
        res.add("единственная заявка потрачена", game_eval(s.page, "g.remaining") == 0)
        click_ui(s.page, res, "back")
        wait_page(s.page, "overview")
        click_ui(s.page, res, "nav-cards")
        second = game_eval(s.page, "g.cases.find(c => c.id !== g.state.focus).id")
        s.page.locator(f'[data-action="select"][data-id="{second}"]').click()
        try:
            wait_page(s.page, "inspect", timeout=9000)
        except PWTimeout:
            pass
        click_ui(s.page, res, "predict", value="same")
        req = s.page.locator('[data-action="request"]').first
        res.add("вторая заявка отключена: бюджет нельзя превысить",
                req.is_disabled()
                and game_eval(s.page, "g.state.checked") == [first]
                and game_eval(s.page, "g.remaining") == 0,
                req.inner_text()[:40])
        click_ui(s.page, res, "decide", value="sky")
        open_results(s.page, res)
        wait_page(s.page, "results")
        expected = game_eval(s.page, "g.results()")
        ok = True
        for key in ("found", "missed", "artifacts", "extra"):
            m = re.search(r"-?\d+", s.page.inner_text(f'#summary [data-count="{key}"]'))
            ok &= (int(m.group()) if m else -999) == expected[key]
        res.add("итоги короткой смены: совет == results()", ok, json.dumps(expected))
        sc = screenscan(s.page)
        res.add("короткая смена считает прогресс из 6", sc["prog"], json.dumps(sc))
        shot(s.page, out, "results-short")
        s.assert_clean(res, "short")
    finally:
        s.close()


def g_keyboard(browser, out: Path, app: Path):
    res = group("Клавиатура: запуск, вкладки, карточка — без мыши")
    s = Session(browser, out, "keyboard")
    try:
        s.goto(file_url(app / "index.html"))
        s.page.locator('[data-action="start-full"]').focus()
        s.page.keyboard.press("Enter")
        wait_page(s.page, "briefing")
        res.add("Enter на «Открыть смену» открывает брифинг", True)
        s.page.locator('[data-action="begin"]').focus()
        s.page.keyboard.press("Space")
        wait_page(s.page, "overview")
        res.add("Space на «Начать исследование» открывает обзор", True)
        seq = []
        for _ in range(14):
            s.page.keyboard.press("Tab")
            seq.append(s.page.evaluate("""() => { const a = document.activeElement;
                return a ? {tag: a.tagName, act: a.getAttribute('data-action'),
                            vis: !!(a.offsetWidth || a.offsetHeight || a.getClientRects().length)} : null; }"""))
        res.add("Tab обходит видимые интерактивные элементы",
                len([x for x in seq if x and x["tag"] in ("BUTTON", "A", "INPUT") and x["vis"]]) >= 6,
                json.dumps(seq[:6]))
        s.page.locator('[data-action="nav-cards"]').focus()
        s.page.keyboard.press("Enter")
        s.page.wait_for_function("() => window.game.state.view === 'cards'", timeout=6000)
        cid = game_eval(s.page, "g.cases[2].id")
        s.page.locator(f'[data-action="select"][data-id="{cid}"]').focus()
        s.page.keyboard.press("Enter")
        try:
            wait_page(s.page, "inspect", timeout=9000)
        except PWTimeout:
            pass
        res.add("Enter на карточке открывает осмотр участка",
                state(s.page)["page"] == "inspect" and game_eval(s.page, "g.state.focus") == cid)
        s.assert_clean(res, "keyboard")
    finally:
        s.close()


def g_narrow(browser, out: Path, app: Path):
    res = group("Узкий экран 390px: все экраны без горизонтальной прокрутки")
    s = Session(browser, out, "narrow", viewport={"width": 390, "height": 844})
    try:
        s.boot_full(res, app)
        res.add("обзор: прокрутки по X нет", overflow_px(s.page) <= 1, f"+{overflow_px(s.page)}px")
        shot(s.page, out, "narrow-overview")
        click_ui(s.page, res, "nav-cards")
        s.page.wait_for_timeout(250)
        res.add("карточки: прокрутки по X нет", overflow_px(s.page) <= 1, f"+{overflow_px(s.page)}px")
        shot(s.page, out, "narrow-cards")
        open_inspect_from_overview(s.page, res)
        click_ui(s.page, res, "predict", value="changed")
        res.add("осмотр: прокрутки по X нет", overflow_px(s.page) <= 1, f"+{overflow_px(s.page)}px")
        shot(s.page, out, "narrow-inspect")
        click_ui(s.page, res, "decide", value="sky")
        for _ in range(5):
            next_undecided(s.page, res)
            click_ui(s.page, res, "predict", value="unsure")
            click_ui(s.page, res, "decide", value="uncertain")
        open_results(s.page, res)
        wait_page(s.page, "results")
        res.add("итоги: прокрутки по X нет", overflow_px(s.page) <= 1, f"+{overflow_px(s.page)}px")
        shot(s.page, out, "narrow-results")
        s.assert_clean(res, "narrow")
    finally:
        s.close()


def _skymap_probe(page, motion) -> dict:
    return page.evaluate("""async (motion) => {
        const host = document.createElement('div');
        host.style.cssText = 'position:fixed;left:0;top:0;width:420px;height:320px;';
        document.body.appendChild(host);
        let got = null;
        const opts = {cases: window.game.cases, selected: window.game.cases[0].id,
                      statuses: {}, onSelect: (id) => { got = id; }};
        if (motion !== null) opts.motion = motion;
        const m = new SkyMap(host, opts);
        const t0 = performance.now();
        await m.flyTo(window.game.cases[2].id);
        const dt = performance.now() - t0;
        const node = host.querySelector('[data-sector]');
        const want = node ? node.getAttribute('data-sector') : null;
        if (node) node.click();
        await new Promise(r => setTimeout(r, 60));
        const selected = got;
        m.destroy();
        const emptied = !host.querySelector('.sky-map');
        let destroyTwice = true;
        try { m.destroy(); } catch (e) { destroyTwice = false; }
        host.remove();
        return {dt: Math.round(dt), emptied, destroyTwice, selected, want};
    }""", motion)


def g_motion(browser, out: Path, app: Path):
    res = group("Reduced-motion ОС: карта анимирует по умолчанию, явный выбор решает; blink работает")
    s = Session(browser, out, "reduced", reduced_motion="reduce")
    try:
        s.boot_full(res, app)
        probe = _skymap_probe(s.page, None)
        res.add("reduced-motion ОС: перелёт по умолчанию анимируется (250–5000 мс) — выбор не от ОС",
                250 <= probe["dt"] < 5000, f"{probe['dt']} мс")
        res.add("onSelect/destroy корректны и при reduced-motion",
                probe["selected"] == probe["want"] and probe["emptied"] and probe["destroyTwice"],
                json.dumps(probe))
        probe_i = _skymap_probe(s.page, "instant")
        res.add("reduced-motion ОС: явный motion:'instant' даёт мгновенный перелёт (<250 мс)",
                probe_i["dt"] < 250, f"{probe_i['dt']} мс")
        open_inspect_from_overview(s.page, res)
        frames = game_eval(s.page, "g.cases.find(c => c.id === g.state.focus).frames")
        f0, f1 = frames[0], frames[1]
        blink = s.page.locator('[data-action="tool"][data-value="blink"]')
        res.add("reduced-motion ОС: «Мигание» доступна (явный выбор анимации пользователем)",
                blink.count() == 1 and not blink.first.is_disabled())
        click_ui(s.page, res, "tool", value="blink")
        seq = []
        for _ in range(3):
            seq.append(s.page.get_attribute(".scope .base-image", "src"))
            s.page.wait_for_timeout(950)
        res.add("reduced-motion ОС: blink реально чередует кадры",
                len(set(seq)) >= 2 and set(seq) == {f0, f1}, str(len(set(seq))))
        s.assert_clean(res, "reduced")
    finally:
        s.close()

    res2 = group("Обычный режим: явные motion:'instant'/'animated' работают как заявлено")
    s2 = Session(browser, out, "motion")
    try:
        s2.boot_full(res2, app)
        probe_i = _skymap_probe(s2.page, "instant")
        res2.add("обычный режим: motion:'instant' разрешается сразу (<250 мс)",
                probe_i["dt"] < 250, f"{probe_i['dt']} мс")
        probe_a = _skymap_probe(s2.page, "animated")
        res2.add("обычный режим: motion:'animated' завершается (250–5000 мс)",
                250 <= probe_a["dt"] < 5000, f"{probe_a['dt']} мс")
        res2.add("onSelect срабатывает и в обычном режиме",
                probe_a["selected"] == probe_a["want"], json.dumps(probe_a))
        s2.assert_clean(res2, "motion")
    finally:
        s2.close()


def g_offline_http(browser, out: Path, app: Path):
    res = group("HTTP офлайн: смена играется с localhost, внешних запросов нет")

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(app)))
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    s = Session(browser, out, "http", allow_prefixes=[f"http://127.0.0.1:{port}/"])
    try:
        s.goto(f"http://127.0.0.1:{port}/index.html")
        res.add("страница открыта по HTTP", s.page.evaluate("() => location.protocol") == "http:")
        click_ui(s.page, res, "start-full")
        wait_page(s.page, "briefing")
        click_ui(s.page, res, "begin")
        wait_page(s.page, "overview")
        click_ui(s.page, res, "observe")
        wait_page(s.page, "inspect")
        click_ui(s.page, res, "predict", value="changed")
        click_ui(s.page, res, "request")
        click_ui(s.page, res, "decide", value="sky")
        res.add("впечатление, заявка и версия работают по HTTP",
                game_eval(s.page, "g.state.checked.length") == 1
                and game_eval(s.page, "Object.keys(g.state.decisions).length") == 1)
        res.add("внешние адреса не запрашивались", not s.violations, str(s.violations[:3]))
        shot(s.page, out, "http-inspect")
        s.assert_clean(res, "http")
    finally:
        s.close()
        srv.shutdown()


def g_installed(browser, out: Path, installed: Path):
    res = group("Установленная копия (дом с пробелами) играет офлайн")
    s = Session(browser, out, "installed")
    try:
        s.goto(file_url(installed / "index.html"))
        click_ui(s.page, res, "start-full")
        wait_page(s.page, "briefing")
        click_ui(s.page, res, "begin")
        wait_page(s.page, "overview")
        res.add("карта с 12 участками у установленной копии",
                s.page.locator("#map-host .sky-map").count() == 1
                and s.page.locator("#map-host [data-sector]").count() == 12)
        click_ui(s.page, res, "observe")
        wait_page(s.page, "inspect")
        click_ui(s.page, res, "predict", value="changed")
        click_ui(s.page, res, "request")
        click_ui(s.page, res, "decide", value="artifact")
        res.add("полный цикл работает из установленной папки",
                game_eval(s.page, "g.state.checked.length") == 1
                and game_eval(s.page, "Object.keys(g.state.decisions).length") == 1)
        shot(s.page, out, "installed-inspect")
        s.assert_clean(res, "installed")
    finally:
        s.close()


def g_phone(browser, out: Path, dist: Path):
    res = group("Изолированный phone.html: все 6 участков короткой смены на 390px")
    s = Session(browser, out, "phone", viewport={"width": 390, "height": 844})
    try:
        with tempfile.TemporaryDirectory(prefix="science-phone-") as folder:
            isolated = Path(folder) / "phone.html"
            shutil.copyfile(dist / "phone.html", isolated)
            s.goto(file_url(isolated))
            click_ui(s.page, res, "start-short")
            click_ui(s.page, res, "begin")
            wait_page(s.page, "overview")
            ok_canvas = True
            try:
                s.page.wait_for_function(
                    "() => document.querySelectorAll('#map-host canvas').length >= 1",
                    timeout=8000)
            except PWTimeout:
                ok_canvas = False
            res.add("телефон: встроенная карта неба рендерится (SKY_DATA встроен)",
                    ok_canvas and s.page.locator("#map-host canvas").count() >= 1)
            click_ui(s.page, res, "nav-cards")
            click_ui(s.page, res, "observe")
            wait_page(s.page, "inspect")
            for index in range(6):
                click_ui(s.page, res, "predict", value="unsure")
                if index == 0:
                    click_ui(s.page, res, "request")
                    shot(s.page, out, "phone-inspect")
                click_ui(s.page, res, "decide", value="uncertain")
                if index == 1:
                    click_ui(s.page, res, "review-case")
                    s.page.wait_for_function("() => [...document.querySelectorAll('#dialog img')].every(i => i.complete && i.naturalWidth > 0)")
                    res.add("телефон: разбор одного дела доступен при исчерпанной заявке",
                            s.page.locator('#dialog .result-card').count() == 1
                            and s.page.locator('#dialog .result-photos img').count() == 3
                            and game_eval(s.page, "Object.keys(g.state.revealed).length === 1 && g.remaining === 0"))
                    s.page.screenshot(path=str(out / "screenshots" / "phone-case-review.png"))
                    close_dialog(s.page, res)
                if index < 5:
                    click_ui(s.page, res, "next")
                    wait_page(s.page, "inspect")
            click_ui(s.page, res, "next")
            wait_page(s.page, "results")
            res.add("телефон: шесть решений, одна заявка, без подсказок",
                    game_eval(s.page, "Object.keys(g.state.decisions).length === 6 && "
                              "g.state.checked.length === 1 && g.remaining === 0 && g.state.hints.length === 0"))
            # Все решения «неопределено», единственный жетон — на первом участке.
            # Ожидаемые счётчики выводятся из expectedVerdict реальных участков модели,
            # а не из фиксированных подтипов.
            expected = game_eval(s.page, "g.results()")
            actual = {key: int(s.page.inner_text(f'#summary [data-count="{key}"]'))
                      for key in expected}
            res.add("телефон: итоговые счётчики == results() модели",
                    actual == expected, json.dumps({"ui": actual, "model": expected}))
            derived = game_eval(s.page, """(() => {
                const skyAll = g.cases.filter((c) => c.expectedVerdict === 'sky').length;
                const skyFound = g.cases.filter((c) => c.expectedVerdict === 'sky'
                                              && g.state.decisions[c.id] === 'sky').length;
                const art = g.cases.filter((c) => c.expectedVerdict === 'artifact'
                                              && g.state.decisions[c.id] === 'artifact').length;
                const extra = g.cases.filter((c) => c.expectedVerdict === 'stable'
                                             && g.state.checked.includes(c.id)).length;
                return {found: skyFound, missed: skyAll - skyFound, artifacts: art, extra};
            })()""")
            res.add("телефон: счётчики согласованы с expectedVerdict реальных участков",
                    actual == derived, json.dumps(derived))
            res.add("телефон: нет горизонтальной прокрутки", overflow_px(s.page) <= 1)
            shot(s.page, out, "phone-results")
            click_ui(s.page, res, "presenter")
            click_ui(s.page, res, "real")
            s.page.wait_for_function("() => [...document.querySelectorAll('#dialog img')].every(i => i.complete && i.naturalWidth > 0)")
            res.add("телефон: три реальных снимка доступны без соседних файлов",
                    s.page.locator("#dialog img").count() == 3)
            s.assert_clean(res, "phone")
    finally:
        s.close()


def g_apple(browser, out: Path, dist: Path):
    res = group("Apple Silicon ZIP: распакованный HTML играет офлайн в доступном Chromium")
    s = Session(browser, out, "apple-zip")
    try:
        with tempfile.TemporaryDirectory(prefix="science-apple-") as folder:
            with zipfile.ZipFile(dist / "apple-silicon.zip") as archive:
                archive.extractall(folder)
            s.boot_full(res, Path(folder) / "science-day", mode="short")
            click_ui(s.page, res, "observe")
            wait_page(s.page, "inspect")
            click_ui(s.page, res, "predict", value="same")
            click_ui(s.page, res, "request")
            click_ui(s.page, res, "decide", value="stable")
            res.add("распакованный Mac ZIP: третий кадр открыт, решение сохранено, бюджет списан",
                    game_eval(s.page, "g.remaining === 0 && g.state.checked.length === 1 && "
                              "g.state.decisions[g.state.focus] === 'stable'"))
            shot(s.page, out, "apple-zip-inspect")
            open_results(s.page, res)
            wait_page(s.page, "results")
            model_extra = game_eval(s.page, "g.results().extra")
            res.add("распакованный Mac ZIP: совет показывает потраченную проверку по results()",
                    s.page.inner_text('#summary [data-count="extra"]') == str(model_extra),
                    f"model extra={model_extra}")
            s.assert_clean(res, "apple-zip")
    finally:
        s.close()


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description="Браузерная группа приёмки (Playwright)")
    ap.add_argument("--app", default=str(APP))
    ap.add_argument("--dist", default=str(DIST))
    ap.add_argument("--installed", default="")
    ap.add_argument("--out", default=str(ROOT / "verification"))
    ap.add_argument("--engine", default="auto", choices=("auto", "chromium", "firefox"))
    args = ap.parse_args()
    app, dist, out = Path(args.app).resolve(), Path(args.dist).resolve(), Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / "network.json").write_text("", encoding="utf-8")

    t0 = time.monotonic()
    engine_name = ""
    with sync_playwright() as pw:
        browser = None
        if args.engine in ("auto", "chromium"):
            exe = chromium_executable()
            if exe:
                try:
                    browser = pw.chromium.launch(headless=True, executable_path=str(exe))
                    engine_name = f"chromium ({exe})"
                except Exception as e:
                    eprint(f"Chromium {exe} не запустился: {e}")
        if browser is None and args.engine in ("auto", "firefox"):
            fexe = firefox_executable()
            if fexe:
                browser = pw.firefox.launch(headless=True, executable_path=str(fexe))
                engine_name = f"firefox ({fexe})"
        if browser is None:
            eprint("Ни Chromium (~/.cache/ms-playwright/chromium-1234), ни Firefox не найдены. "
                   "Установите: .venv/bin/playwright install chromium")
            return 3
        try:
            print(f"Движок: {engine_name}")
            safe(g_landing, browser, out, app)
            safe(_map_group, browser, out, app)
            safe(g_inspection, browser, out, app)
            safe(g_presenter, browser, out, app)
            safe(g_case_review, browser, out, app)
            safe(g_completion_results, browser, out, app)
            safe(g_dialog_reset, browser, out, app)
            safe(g_short_mode, browser, out, app)
            safe(g_keyboard, browser, out, app)
            safe(g_narrow, browser, out, app)
            safe(g_motion, browser, out, app)
            safe(g_offline_http, browser, out, app)
            safe(g_apple, browser, out, dist)
            if args.installed and Path(args.installed).is_dir():
                safe(g_installed, browser, out, Path(args.installed).resolve())
            else:
                res = group("Установленная копия (дом с пробелами) играет офлайн")
                res.add("каталог установки передан (--installed)", False,
                        "нет каталога установки — архив/установщик не собрались")
            if (dist / "phone.html").is_file():
                safe(g_phone, browser, out, dist)
            else:
                res = group("Автономный phone.html в узком экране")
                res.add("dist/phone.html существует", False, "не собран")
        finally:
            browser.close()

    total_fail = sum(len(r.failures) for _t, r in ALL)
    doc = {"engine": engine_name, "duration_s": round(time.monotonic() - t0, 1),
           "ok": total_fail == 0,
           "groups": [{"title": t, "ok": r.ok, "failures": r.failures, "checks": r.rows}
                      for t, r in ALL]}
    (out / "browser-results.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    for t, r in ALL:
        print(f"{'  ok ' if r.ok else 'FAIL '} {t}: проверок {len(r.rows)}, провалов {len(r.failures)}")
        for f in r.failures:
            print(f"        - {f}")
    print(f"\nБРАУЗЕР {'OK' if total_fail == 0 else 'ПРОВАЛ'} "
          f"({engine_name}, {doc['duration_s']} с, провалов {total_fail})")
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
