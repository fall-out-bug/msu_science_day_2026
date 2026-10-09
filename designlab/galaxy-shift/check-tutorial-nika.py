#!/usr/bin/env python3
"""N01/N02: opening has one DOM portrait; trial labels stay local to QuestScene."""
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent


def rect_inside(page, selector):
    return page.evaluate('''selector => {
      const r=document.querySelector(selector)?.getBoundingClientRect();
      return r && r.left >= 0 && r.top >= 0 && r.right <= innerWidth && r.bottom <= innerHeight;
    }''', selector)


def check(page):
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
    page.goto((HERE / 'index.html').as_uri())
    page.wait_for_function('window.galaxyGame && window.GALAXY_DATA')
    assert page.locator('.welcome h1').is_visible()
    assert page.locator('.welcome .mentor-portrait').count() == 0
    assert page.locator('[data-action="start-route"]').is_visible()
    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')

    page.evaluate("galaxyGame.model.dispatch({type:'START'}); galaxyGame.render()")
    scene = page.locator('#quest-scene')
    scene.wait_for(state='visible')
    page.wait_for_function('Array.from(document.images).every(image => image.complete && image.naturalWidth > 0)')
    labels_before = page.evaluate('JSON.stringify(galaxyGame.model.state.labels)')
    page.evaluate('''() => {
      window.__tutorialRefs = {scene: document.querySelector('#quest-scene'), photo: document.querySelector('[data-quest-photo]'), scrollY};
    }''')
    assert scene.locator('[data-quest-observation]').count() == 0
    assert scene.locator('[data-quest-label]').count() == 3
    scene.locator('[data-quest-label]').first.click()
    assert page.evaluate('JSON.stringify(galaxyGame.model.state.labels)') == labels_before
    assert page.evaluate('''() => __tutorialRefs.scene === document.querySelector('#quest-scene') &&
      __tutorialRefs.photo === document.querySelector('[data-quest-photo]') && Math.abs(__tutorialRefs.scrollY - scrollY) < 2''')
    assert 'пробная метка' in scene.locator('[role="status"]').inner_text().lower()
    assert scene.locator('[data-quest-label][aria-pressed="true"]').count() == 1

    page.evaluate("galaxyGame.model.dispatch({type:'LABELS'}); galaxyGame.render()")
    scene = page.locator('#quest-scene')
    item_id = page.evaluate('GALAXY_DATA.childIds[0]')
    scene.locator('[data-quest-label]').first.click()
    assert page.evaluate('(id) => Boolean(galaxyGame.model.state.labels[id])', item_id)
    assert not errors, errors


if __name__ == '__main__':
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for viewport in ({'width': 1280, 'height': 720}, {'width': 1366, 'height': 768}, {'width': 1440, 'height': 900}, {'width': 1920, 'height': 1080}):
            page = browser.new_page(viewport=viewport, reduced_motion='reduce')
            check(page)
            print(f"PASS N01/N02 at {viewport['width']}×{viewport['height']}")
            page.close()
        browser.close()
