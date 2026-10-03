#!/usr/bin/env python3
"""Replay freely accessible episodes, earned endings, history, and cancellation."""
from pathlib import Path
import json
import os
import re
import sys

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
ENTRY = sys.argv[1] if len(sys.argv) > 1 else (HERE / 'index.html').as_uri()
OUT = HERE / 'evidence'
OUT.mkdir(exist_ok=True)
checks, errors = [], []


def launch(playwright):
    executable = os.environ.get('PW_CHROMIUM')
    if not executable:
        candidates = sorted((Path.home() / '.cache/ms-playwright').glob('chromium-*/chrome-linux/chrome'))
        executable = str(candidates[-1]) if candidates else None
    options = {'headless': True}
    if executable:
        options['executable_path'] = executable
    return playwright.chromium.launch(**options)


def check(name, condition):
    assert condition, name
    checks.append(name)


with sync_playwright() as playwright:
    browser = launch(playwright)
    context = browser.new_context(viewport={'width': 1440, 'height': 1050}, reduced_motion='reduce')
    page = context.new_page()
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(ENTRY)
    page.wait_for_function('window.journey && window.comparisonProbe && window.brightnessEpisode')

    def visible(destination):
        return page.locator({'overview': '#overview', 'tracking': '#tracking-episode',
                             'brightness': '#brightness-episode'}[destination]).is_visible()

    def nav(destination):
        page.locator('#nav-' + destination).click()
        check('navigation reaches ' + destination, visible(destination))

    def count(expected):
        actual = re.sub(r'\s+', '', page.locator('#overview-count').inner_text())
        check('episode map counts ' + expected, actual == expected.replace(' ', ''))

    def brightness_result(expected):
        page.locator('#brightness-measure').click()
        page.wait_for_function('brightnessEpisode.state.phase === "result"')
        check('brightness result ' + expected,
              page.evaluate('brightnessEpisode.state.result.outcome') == expected)

    def tracking_result(expected):
        page.locator('#follow').click()
        page.wait_for_function('comparisonProbe.state.phase === "result"')
        check('tracking result ' + expected,
              page.evaluate('comparisonProbe.state.result.outcome') == expected)

    def screenshot(name):
        page.screenshot(path=str(OUT / ('navigation-' + name + '.png')), full_page=True)

    check('entry is an observatory scene', visible('overview') and page.locator('#shift-action').is_visible())
    check('episode directory remains optional',not page.locator('#episode-directory').evaluate('(el)=>el.open'))
    page.locator('#episode-directory summary').click()
    check('entry offers both destinations', all(page.locator('#' + identifier).is_visible()
          and page.locator('#' + identifier).is_enabled() for identifier in
          ['nav-overview', 'nav-tracking', 'nav-brightness', 'card-tracking', 'card-brightness']))
    check('unearned overview stories are not offered',
          page.locator('#overview-tracking-story').is_hidden()
          and page.locator('#overview-brightness-story').is_hidden())
    count('0 / 2')
    check('navigation labels name destinations',
          'Обсерватория' in page.locator('#nav-overview').inner_text()
          and 'астероид' in page.locator('#nav-tracking').inner_text().lower()
          and 'сверхнов' in page.locator('#nav-brightness').inner_text().lower())
    screenshot('overview-entry')

    page.locator('#card-brightness').click()
    check('second episode is available before completing first', visible('brightness')
          and page.evaluate('comparisonProbe.state.journal.length === 0'))
    page.evaluate('brightnessEpisode.choose(23,64)')
    brightness_result('stable')
    check('stable result earns no completion or history',
          not page.evaluate('brightnessEpisode.state.earned')
          and page.locator('#brightness-reveal').is_hidden()
          and page.locator('#brightness-completion').is_hidden())
    nav('overview')
    count('0 / 2')
    nav('brightness')
    check('return retains previous measured outcome',
          page.evaluate('brightnessEpisode.state.result.outcome === "stable"'))
    page.locator('#brightness-retry').click()
    page.evaluate('brightnessEpisode.choose(65,64)')
    brightness_result('faded')
    check('successful supernova measurement earns ending before story opens',
          page.evaluate('brightnessEpisode.state.earned && !brightnessEpisode.state.storyOpen')
          and page.locator('#brightness-completion').is_visible()
          and page.locator('#brightness-story').is_hidden())
    check('brightness ending clearly states completion',
          'заверш' in page.locator('#brightness-completion').inner_text().lower())
    screenshot('brightness-complete')
    page.locator('#brightness-reveal').click()
    check('earned supernova story has its historical identity',
          page.locator('#brightness-story').is_visible()
          and 'SN 2023tyk' in page.locator('#brightness-story').inner_text())
    attempts = page.evaluate('JSON.stringify(brightnessEpisode.state.attempts)')
    page.locator('#brightness-retry').click()
    check('retry preserves brightness completion', page.evaluate('brightnessEpisode.state.earned')
          and page.locator('#brightness-completion').is_visible())
    page.locator('#brightness-to-overview').click()
    check('brightness completion action reaches episode map', visible('overview'))
    count('1 / 2')
    page.locator('#card-tracking').click()
    check('first episode remains available after completing second', visible('tracking'))
    check('brightness attempt history survives episode change',
          attempts == page.evaluate('JSON.stringify(brightnessEpisode.state.attempts)'))

    # A hidden episode must not complete a timer after the player navigates away.
    page.emulate_media(reduced_motion='no-preference')
    page.evaluate('comparisonProbe.choose(58,68)')
    page.locator('#follow').click()
    check('tracking verification starts', page.evaluate('comparisonProbe.state.phase === "checking"'))
    nav('overview')
    page.wait_for_timeout(1050)
    check('leaving tracking cancels its pending result and preserves target',
          page.evaluate('comparisonProbe.state.phase === "search" && comparisonProbe.state.result === null'
                        ' && comparisonProbe.state.attempts.length === 0 && comparisonProbe.state.journal.length === 0'
                        ' && comparisonProbe.state.selection.point.x === 58'))
    nav('brightness')
    page.evaluate('brightnessEpisode.choose(65,64)')
    attempt_count = page.evaluate('brightnessEpisode.state.attempts.length')
    page.locator('#brightness-measure').click()
    check('brightness measurement starts', page.evaluate('brightnessEpisode.state.phase === "measuring"'))
    nav('tracking')
    page.wait_for_timeout(900)
    check('leaving brightness cancels its pending result and preserves target',
          page.evaluate('brightnessEpisode.state.phase === "search" && brightnessEpisode.state.result === null'
                        ' && brightnessEpisode.state.selection.point.x === 65')
          and attempt_count == page.evaluate('brightnessEpisode.state.attempts.length'))
    page.emulate_media(reduced_motion='reduce')

    # Navigation itself must preserve field, display settings, and exact choice.
    page.evaluate('comparisonProbe.setAmount(.43)')
    tracking_before = page.evaluate('JSON.stringify(comparisonProbe.state)')
    nav('brightness')
    nav('overview')
    nav('tracking')
    check('navigation preserves complete tracking state',
          tracking_before == page.evaluate('JSON.stringify(comparisonProbe.state)'))
    tracking_result('moving')
    check('first actual mover reveals its specific asteroid history',
          page.locator('#tracking-story').is_visible()
          and '2948' in page.locator('#tracking-story').inner_text()
          and 'астероид' in page.locator('#tracking-story').inner_text().lower())
    check('first successful track completes one-field instrument test',
          page.evaluate('comparisonProbe.state.journal.length === 1')
          and page.locator('#tracking-completion').is_visible())
    page.locator('#track-story-open').click()
    check('asteroid history button reaches its section',
          page.locator('#tracking-story').evaluate('(element)=>element.contains(document.activeElement)'))
    check('next action identifies installation destination','обсерваторию' in page.locator('#next-field').inner_text().lower())
    page.locator('#next-field').click()
    check('successful test returns to observatory',visible('overview'))
    check('earned tool still requires installation',page.evaluate('!journey.state.installed.movement'))
    count('2 / 2')
    check('passing tests alone does not finish shift',page.locator('#journey-finished').is_hidden() and not page.evaluate('journey.state.finished'))
    screenshot('overview-complete')
    saved_counts = page.evaluate('[comparisonProbe.state.attempts.length,brightnessEpisode.state.attempts.length]')
    page.locator('#overview-tracking-story').click()
    check('overview history action reopens an earned asteroid story',
          visible('tracking') and page.locator('#tracking-story').is_visible())
    check('first asteroid story is reachable from overview', '2948' in page.locator('#tracking-story-title').inner_text())
    page.locator('[data-saved-case="s02"]').click()
    check('journal reopens the only test asteroid', '2948' in page.locator('#tracking-story-title').inner_text())
    nav('overview')
    page.locator('#overview-brightness-story').click()
    check('overview history action reopens the earned supernova story',
          visible('brightness') and page.locator('#brightness-story').is_visible())
    check('reopening stories adds no scientific attempt', saved_counts ==
          page.evaluate('[comparisonProbe.state.attempts.length,brightnessEpisode.state.attempts.length]'))

    # Keyboard activation should use the same persistent navigation.
    page.locator('#nav-brightness').focus()
    page.keyboard.press('Enter')
    check('keyboard opens second episode', visible('brightness'))
    check('brightness selected target survives all switches',
          page.evaluate('brightnessEpisode.state.selection.point.x === 65 && brightnessEpisode.state.earned'))
    page.locator('#nav-tracking').focus()
    page.keyboard.press('Space')
    check('keyboard opens first episode', visible('tracking'))
    nav('brightness')
    nav('overview')
    page.go_back()
    check('browser Back restores previous episode without clearing progress',
          visible('brightness') and page.evaluate('brightnessEpisode.state.earned'
              ' && comparisonProbe.state.journal.length === 1'))

    page.set_viewport_size({'width': 390, 'height': 844})
    for destination in ['overview', 'brightness', 'tracking']:
        nav(destination)
        check(destination + ' has no mobile horizontal overflow',
              page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        check(destination + ' retains all persistent navigation buttons',
              all(page.locator('#nav-' + target).is_visible() for target in ['overview', 'tracking', 'brightness']))
    check('mobile tracking result states completion', 'ЭПИЗОД 1 ЗАВЕРШЁН' in page.locator('#outcome-tag').inner_text())
    nav('brightness')
    check('mobile supernova result states completion', 'ЭПИЗОД 2 ЗАВЕРШЁН' in page.locator('#brightness-outcome-tag').inner_text())
    nav('tracking')
    screenshot('mobile-navigation')
    page.locator('#restart').click()
    check('restart clears progress in both episodes',
          page.evaluate('comparisonProbe.state.journal.length === 0 && comparisonProbe.state.attempts.length === 0'
                        ' && comparisonProbe.state.selection === null && !brightnessEpisode.state.earned'
                        ' && brightnessEpisode.state.attempts.length === 0 && brightnessEpisode.state.selection === null'))
    nav('overview')
    count('0 / 2')
    page.locator('#episode-directory summary').click()
    check('reset does not lock either episode', all(page.locator('#card-' + target).is_enabled()
          for target in ['tracking', 'brightness']))
    check('no runtime errors', not errors)
    browser.close()

report = {'count': len(checks), 'checks': checks, 'engine': 'chromium', 'entry': ENTRY, 'errors': errors}
(OUT / 'navigation-browser.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(report, ensure_ascii=False, indent=2))
