#!/usr/bin/env python3
"""Targeted real-browser QA for Night Shift; independent of the legacy release gate.

Uses the existing Playwright installation. No dependency installs, host/container
changes, science imports, release ledger updates or model-state mutation.
--base-url accepts the app directory or its index.html; default is offline file://.
--out is an absolute directory for screenshots and a compact machine-readable report.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit, urlunsplit

from playwright.sync_api import sync_playwright

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from verify_common import ROOT, chromium_executable, firefox_executable

IDS = ['s02', 's08', 's10', 's01', 's07', 's11', 's04', 's06', 's03']
SCENE = '#app .ns-game'


def entry_url(base):
    if base is None:
        return (ROOT / 'app/index.html').as_uri()
    parts = urlsplit(base)
    if parts.scheme not in ('http', 'https', 'file'):
        raise ValueError('--base-url must be an http(s) or file URL')
    path = parts.path if parts.path.endswith('.html') else parts.path.rstrip('/') + '/index.html'
    return urlunsplit(parts._replace(path=path))


def archive_url(url):
    parts = urlsplit(url)
    query = parts.query + ('&' if parts.query else '') + 'archive=1'
    return urlunsplit(parts._replace(query=query))


def model(page, expression):
    return page.evaluate(f'() => {{ const g = window.nightshift; return ({expression}); }}')


def wait_scene(page, scene):
    page.locator(f'{SCENE}[data-scene="{scene}"]').wait_for(state='visible', timeout=20000)


def action(page, name, value=None):
    selector = f'#app [data-ns="{name}"]'
    if value is not None:
        selector += f'[data-value="{value}"]'
    return page.locator(selector).first


def click(page, name, value=None):
    action(page, name, value).click(timeout=15000)


def disabled_or_absent(locator):
    return locator.count() == 0 or not locator.is_visible() or locator.is_disabled()


class Run:
    def __init__(self, browser, out, name, url, *, mobile=False, reduced=False):
        self.name, self.out, self.rows = name, out, []
        self.reduced = reduced
        self.errors, self.console, self.network = [], [], []
        self.origin = urlsplit(url)
        self.context = browser.new_context(viewport={'width': 390, 'height': 844} if mobile else {'width': 1440, 'height': 1000},
                                           device_scale_factor=1, reduced_motion='reduce' if reduced else 'no-preference',
                                           service_workers='block')
        self.context.route('**/*', self.route)
        self.page = self.context.new_page()
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.on('console', lambda message: self.console.append(message.text) if message.type == 'error' else None)
        self.page.set_default_timeout(15000)
        self.url = url

    def route(self, route):
        url = route.request.url
        parts = urlsplit(url)
        local = parts.scheme in ('file', 'data', 'blob', 'about')
        same_origin = (self.origin.scheme in ('http', 'https') and
                       (parts.scheme, parts.netloc) == (self.origin.scheme, self.origin.netloc))
        if local or same_origin:
            route.continue_()
        else:
            self.network.append({'method': route.request.method, 'url': url})
            route.abort()

    def check(self, name, passed, detail=''):
        self.rows.append({'name': name, 'ok': bool(passed), 'detail': detail})
        print(f'{"PASS" if passed else "FAIL"} {self.name}: {name}', flush=True)
        if not passed:
            raise AssertionError(f'{name}: {detail}')

    def screenshot(self, name):
        path = self.out / 'screenshots' / f'{self.name}-{name}.png'
        path.parent.mkdir(parents=True, exist_ok=True)
        self.page.evaluate('''async () => {
            await document.fonts.ready;
            await Promise.all(document.getAnimations().filter(animation => {
                const timing = animation.effect?.getComputedTiming();
                return timing && Number.isFinite(timing.endTime) && timing.endTime <= 6000;
            }).map(animation => animation.finished.catch(() => {})));
        }''')
        self.page.screenshot(path=str(path), full_page=True)

    def boot(self, count=3):
        page = self.page
        page.goto(self.url, wait_until='load')
        page.wait_for_function('() => window.nightshift instanceof NightShiftSession')
        wait_scene(page, 'welcome')
        self.check('new game is the default, with meaningful landing',
                   page.locator(SCENE).inner_text().strip() != '' and not page.evaluate('() => !!window.game'))
        self.screenshot('landing')
        click(page, 'level', count)
        click(page, 'start')
        wait_scene(page, 'intro')
        click(page, 'begin')
        wait_scene(page, 'room')
        self.check('selected level has exact cases and request budget',
                   model(page, 'g.cases.map(c => c.id)') == IDS[:count] and
                   model(page, 'g.remaining') == count // 3)
        self.screenshot('room')

    def open_sky_case(self, cid):
        page = self.page
        if page.locator(SCENE).get_attribute('data-scene') != 'sky':
            click(page, 'sky')
        wait_scene(page, 'sky')
        click(page, 'field', cid)
        self.check('field selection changes current case', model(page, 'g.current.id') == cid)
        click(page, 'aim')
        wait_scene(page, 'observe')

    def all_images(self):
        result = self.page.evaluate('''async ids => {
            const cases = window.GAME_DATA.contact.filter(c => ids.includes(c.id));
            const rows = await Promise.all(cases.flatMap(c => c.frames.map((src, epoch) =>
                new Promise(resolve => {
                    const image = new Image();
                    image.onload = () => resolve({id:c.id, epoch, ok:image.naturalWidth === 128 && image.naturalHeight === 128});
                    image.onerror = () => resolve({id:c.id, epoch, ok:false});
                    image.src = src;
                }))));
            return rows;
        }''', IDS)
        self.check('all 27 original observation images decode at 128 × 128',
                   len(result) == 27 and all(row['ok'] for row in result), json.dumps(result))

    def finish(self):
        for name, rows in [('no unhandled page exceptions', self.errors),
                           ('no console errors', self.console),
                           ('no external network requests', self.network)]:
            self.rows.append({'name': name, 'ok': not rows, 'detail': json.dumps(rows, ensure_ascii=False)})
            print(f'{"PASS" if not rows else "FAIL"} {self.name}: {name}', flush=True)
        result = {'name': self.name, 'url': self.url, 'checks': self.rows,
                  'pageerrors': self.errors, 'console_errors': self.console, 'blocked_requests': self.network}
        self.context.close()
        return result


def mark_and_tools(run):
    page = run.page
    cid = model(page, 'g.current.id')
    wrap = page.locator('.ns-image-wrap[data-epoch="0"]').first
    wrap.click(position={'x': wrap.bounding_box()['width'] * 0.25,
                         'y': wrap.bounding_box()['height'] * 0.65})
    saved = model(page, f'g.note("{cid}").marks[0]')
    run.check('pointer saves normalized mark on selected frame',
              saved is not None and abs(saved['x'] - 0.25) < 0.03 and abs(saved['y'] - 0.65) < 0.03)
    wrap = page.locator('.ns-image-wrap[data-epoch="0"]').first
    wrap.focus()
    wrap.press('ArrowRight')
    wrap.press('Enter')
    moved = model(page, f'g.note("{cid}").marks[0]')
    run.check('keyboard reticle moves and Enter saves a new mark', moved['x'] > saved['x'])
    click(page, 'epoch', 1)
    run.check('epoch selector changes visible observation',
              page.locator('.ns-image-wrap[data-epoch="1"]').is_visible())
    click(page, 'blink')
    page.wait_for_timeout(800)
    blink_epoch = page.locator('.ns-image-wrap').first.get_attribute('data-epoch')
    page.wait_for_function('previous => document.querySelector(".ns-image-wrap")?.dataset.epoch !== previous', arg=blink_epoch,
                           timeout=4000)
    run.check('blink actually alternates visible frames', True)
    click(page, 'blink')
    click(page, 'measure')
    panel = page.locator('#ns-measurements')
    run.check('motion field explains why position comparison replaces a brightness chart',
              panel.is_visible() and 'положение' in panel.inner_text() and panel.locator('.ns-chart').count() == 0)
    click(page, 'measure')
    image_width = page.locator('.ns-image-wrap img').first.bounding_box()['width']
    click(page, 'zoom')
    page.wait_for_function('width => document.querySelector(".ns-image-wrap img").getBoundingClientRect().width >= width * 1.9',
                           arg=image_width)
    run.check('zoom enlarges observation',
              page.locator('.ns-image-wrap img').first.bounding_box()['width'] >= image_width * 1.9)
    click(page, 'zoom')
    click(page, 'motion')
    run.check('motion control exposes the off state', page.locator('[data-motion="off"]').count() > 0)
    run.screenshot('instrument')


def full_level(run, count):
    run.boot(count)
    run.all_images()
    page = run.page
    click(page, 'board')
    wait_scene(page, 'board')
    run.check('opening the board does not disclose unanswered cases',
              not model(page, 'g.cases.some(c => g.note(c.id).revealed)'))
    click(page, 'sky')
    wait_scene(page, 'sky')
    run.screenshot('map')
    for index, cid in enumerate(IDS[:count]):
        run.open_sky_case(cid)
        run.check(f'{cid}: third frame is unavailable before request or review',
                  not model(page, f'g.hasThird("{cid}")') and disabled_or_absent(action(page, 'epoch', 2)))
        run.check(f'{cid}: request needs a prediction', disabled_or_absent(action(page, 'request')))
        if index == 0 and count == 3:
            mark_and_tools(run)
        click(page, 'predict', 'uncertain' if index == 0 else 'motion')
        remaining = model(page, 'g.remaining')
        if index < count // 3:
            click(page, 'request')
            run.check(f'{cid}: one request opens third frame and spends exactly one token',
                      model(page, f'g.hasThird("{cid}")') and model(page, 'g.remaining') == remaining - 1)
            remaining_after = model(page, 'g.remaining')
            click(page, 'request')
            run.check(f'{cid}: reopening third frame does not spend another token',
                      model(page, 'g.remaining') == remaining_after)
            click(page, 'epoch', 2)
            run.check(f'{cid}: requested third observation is displayed',
                      page.locator('.ns-image-wrap[data-epoch="2"]').is_visible())
        else:
            run.check(f'{cid}: exhausted budget cannot unlock third frame',
                      remaining == 0 and disabled_or_absent(action(page, 'request')) and
                      not model(page, f'g.hasThird("{cid}")'))
        if cid == 's10':
            click(page, 'measure')
            panel = page.locator('#ns-measurements')
            measured = model(page, 'g.current.photometry.epochs')
            shown_epochs = 3 if model(page, 'g.hasThird(g.current.id)') else 2
            expected = [100 * 10 ** (-0.4 * (epoch['mag'] - measured[0]['mag'])) for epoch in measured[:shown_epochs]]
            displayed = [float(value.replace(',', '.').replace('%', '').replace('\u00a0', ''))
                         for value in panel.locator('.ns-bar b').all_inner_texts()]
            run.check('brightness chart uses measured archive flux ratios', panel.is_visible() and
                      len(displayed) == shown_epochs and all(abs(a - b) < 0.15 for a, b in zip(displayed, expected)))
        click(page, 'verdict', 'uncertain')
        wait_scene(page, 'review')
        run.check(f'{cid}: decision reveals the scientific review and free third frame',
                  model(page, f'g.note("{cid}").revealed') and model(page, f'g.hasThird("{cid}")') and
                  page.locator('.ns-review').is_visible() and
                  model(page, f'g.note("{cid}").beforeReveal') == 'uncertain')
        page.locator('.ns-review summary').filter(has_text='Доказательства и пределы вывода').click()
        run.check(f'{cid}: review retains original scientific explanation',
                  model(page, 'g.current.evidence') in page.locator('.ns-review').inner_text())
        if index == 0:
            run.screenshot('review')
            snapshot = model(page, f'g.note("{cid}").beforeReveal')
            click(page, 'revise')
            wait_scene(page, 'observe')
            click(page, 'verdict', 'sky')
            wait_scene(page, 'review')
            run.check('revision changes current decision and preserves first snapshot',
                      model(page, f'g.note("{cid}").decision') == 'sky' and
                      model(page, f'g.note("{cid}").beforeReveal') == snapshot)
        click(page, 'next')
        wait_scene(page, 'board' if index == count - 1 else 'sky')
    run.check('all cases completed; next ends at the report board',
              model(page, 'g.completed') == count and model(page, 'g.nextId()') is None and
              page.locator('.ns-board').is_visible())
    run.check('report board contains every case in the selected shift',
              page.locator('.ns-board [data-ns="open-card"]').evaluate_all('(cards) => cards.map(card => card.dataset.value)') == IDS[:count])
    run.screenshot('board')
    click(page, 'open-card', IDS[0])
    wait_scene(page, 'review')
    run.check('completed board card reopens its review without replacing first version',
              model(page, 'g.current.id') == IDS[0] and
              model(page, 'g.note(g.current.id).beforeReveal') == 'uncertain')
    click(page, 'board')
    wait_scene(page, 'board')
    decisions = model(page, 'g.state.notes')
    page.once('dialog', lambda dialog: dialog.dismiss())
    click(page, 'restart')
    run.check('cancelled restart preserves completed shift', model(page, 'g.state.notes') == decisions)
    page.once('dialog', lambda dialog: dialog.accept())
    click(page, 'restart')
    wait_scene(page, 'welcome')
    run.check('confirmed restart clears progress', model(page, 'g.completed') == 0)


def responsive_offline(run):
    run.boot(3)
    page = run.page
    run.check('responsive page has no horizontal overflow',
              page.evaluate('() => document.documentElement.scrollWidth <= window.innerWidth + 1'))
    run.open_sky_case('s02')
    run.screenshot('instrument')
    run.check('responsive observation is visible and usable', page.locator('.ns-image-wrap').is_visible())
    wrap = page.locator('.ns-image-wrap').first
    wrap.click(position={'x': wrap.bounding_box()['width'] * 0.6,
                         'y': wrap.bounding_box()['height'] * 0.4})
    run.check('offline responsive pointer mark is saved', model(page, 'g.note(g.current.id).marks[0]') is not None)
    click(page, 'predict', 'motion')
    click(page, 'verdict', 'sky')
    wait_scene(page, 'review')
    run.screenshot('review')
    run.check('responsive review has no horizontal overflow',
              page.evaluate('() => document.documentElement.scrollWidth <= window.innerWidth + 1'))
    if run.reduced:
        run.check('reduced-motion preference is respected when requested',
                  page.evaluate('() => matchMedia("(prefers-reduced-motion: reduce)").matches && document.querySelector("[data-motion=off]") !== null'))


def archive_route(run):
    page = run.page
    page.goto(archive_url(run.url), wait_until='load')
    page.wait_for_function('() => window.game && window.game.state')
    run.check('archive=1 opens the preserved legacy game', page.evaluate('() => !!window.game && !window.nightshift'))
    run.check('legacy entry renders meaningful content', len(page.locator('#app').inner_text().strip()) > 30)
    run.screenshot('archive')


def launch(playwright):
    errors = []
    for engine, executable in [(playwright.chromium, chromium_executable()),
                               (playwright.firefox, firefox_executable())]:
        try:
            kwargs = {'headless': True}
            if executable:
                kwargs['executable_path'] = str(executable)
            return engine.launch(**kwargs), engine.name
        except Exception as error:
            errors.append(str(error))
    raise RuntimeError('No installed Playwright browser could launch: ' + '; '.join(errors))


def interrupted_flight(run):
    run.boot(3)
    page = run.page
    click(page, 'sky')
    click(page, 'field', 's10')
    click(page, 'aim')
    run.check('animated telescope flight starts before leaving map',
              page.locator(SCENE).get_attribute('data-scene') == 'sky' and
              page.locator('[data-ns="aim"]').is_disabled())
    click(page, 'motion')
    click(page, 'field', 's08')
    run.check('changing animation during flight leaves field selection usable',
              model(page, 'g.current.id') == 's08')
    click(page, 'aim')
    wait_scene(page, 'observe')
    run.check('a new aim succeeds after interrupted flight', model(page, 'g.current.id') == 's08')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url')
    parser.add_argument('--out', type=Path, default=Path(tempfile.mkdtemp(prefix='nightshift-browser-')))
    args = parser.parse_args()
    if not args.out.is_absolute():
        parser.error('--out must be an absolute directory')
    args.out.mkdir(parents=True, exist_ok=True)
    url = entry_url(args.base_url)
    results = []
    with sync_playwright() as playwright:
        try:
            browser, engine = launch(playwright)
        except RuntimeError as error:
            print(error, file=sys.stderr)
            return 3
        tasks = [(f'desktop-{count}', url, {}, lambda run, count=count: full_level(run, count)) for count in (3, 6, 9)]
        offline = (ROOT / 'app/index.html').as_uri()
        tasks.extend([('mobile-offline', offline, {'mobile': True}, responsive_offline),
                      ('reduced-motion-offline', offline, {'mobile': True, 'reduced': True}, responsive_offline),
                      ('archive-route', url, {}, archive_route),
                      ('interrupted-flight', url, {}, interrupted_flight)])
        for name, target, options, task in tasks:
            run = Run(browser, args.out, name, target, **options)
            try:
                task(run)
            except Exception as error:
                run.rows.append({'name': 'scenario completes', 'ok': False, 'detail': str(error)})
                print(f'FAIL {name}: {error}', flush=True)
                try:
                    run.screenshot('failure')
                except Exception:
                    pass
            finally:
                results.append(run.finish())
        browser.close()
    ok = all(row['ok'] for result in results for row in result['checks'])
    report = {'ok': ok, 'browser': engine, 'browser_plugin': 'not available', 'sessions': results}
    (args.out / 'browser-results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    (args.out / 'network.json').write_text(json.dumps({r['name']: r['blocked_requests'] for r in results}, indent=2) + '\n')
    print(f'{"PASS" if ok else "FAIL"}: {args.out / "browser-results.json"}')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
