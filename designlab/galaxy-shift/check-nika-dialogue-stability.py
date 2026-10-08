#!/usr/bin/env python3
"""Check that Nika's answer updates keep one reachable modal in place."""
from pathlib import Path

from playwright.sync_api import sync_playwright


HERE = Path(__file__).resolve().parent


def run(page):
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
    page.goto((HERE / 'index.html').as_uri())
    page.wait_for_function('window.galaxyGame && window.GALAXY_DATA')
    page.evaluate("""() => {
      const { model } = galaxyGame;
      model.dispatch({ type: 'START' });
      model.dispatch({ type: 'LABELS' });
      for (const id of GALAXY_DATA.childIds) {
        const image = GALAXY_DATA.images.find(item => item.id === id);
        model.dispatch({ type: 'SET_LABEL', id, label: image.label });
      }
      model.dispatch({ type: 'RUN' });
      galaxyGame.render();
      window.scrollTo(0, 120);
    }""")
    page.locator('[data-action="talk"]').first.click()
    page.wait_for_selector('.nika-dialogue')
    page.evaluate("""() => {
      const dialogue = document.querySelector('.nika-dialogue');
      window.__nikaDialog = {
        dialogue,
        card: dialogue.querySelector('.nika-dialogue__card'),
        head: dialogue.querySelector('.nika-dialogue__head'),
        context: dialogue.querySelector('.nika-dialogue__context'),
        scrollY: scrollY
      };
    }""")
    page.locator('[data-nika="why"]').click()
    assert page.evaluate("""() => {
      const before = window.__nikaDialog;
      const dialogue = document.querySelector('.nika-dialogue');
      return dialogue === before.dialogue &&
        dialogue.querySelector('.nika-dialogue__card') === before.card &&
        dialogue.querySelector('.nika-dialogue__head') === before.head &&
        dialogue.querySelector('.nika-dialogue__context') === before.context &&
        scrollY === before.scrollY;
    }""")
    assert page.evaluate("""() => {
      const card = document.querySelector('.nika-dialogue__card').getBoundingClientRect();
      const actions = [...document.querySelectorAll('.nika-dialogue__actions button')]
        .map(button => button.getBoundingClientRect());
      return card.left >= 0 && card.top >= 0 && card.right <= innerWidth && card.bottom <= innerHeight &&
        actions.length && actions.every(box => box.left >= card.left && box.right <= card.right && box.bottom <= innerHeight);
    }""")
    assert 'Свёрточная сеть' in page.locator('.nika-dialogue').inner_text()
    assert not errors, errors
    page.locator('[data-nika="result-back"]').click()
    assert page.evaluate("document.querySelector('.nika-dialogue') === window.__nikaDialog.dialogue")
    page.keyboard.press('Escape')
    assert page.locator('.nika-dialogue').count() == 0


def main():
    with sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        for viewport in ({'width': 1280, 'height': 720}, {'width': 390, 'height': 844}):
            page = browser.new_page(viewport=viewport, reduced_motion='reduce')
            run(page)
            page.close()
            print('PASS stable Nika dialogue at', viewport['width'], viewport['height'])
        browser.close()


if __name__ == '__main__':
    main()
