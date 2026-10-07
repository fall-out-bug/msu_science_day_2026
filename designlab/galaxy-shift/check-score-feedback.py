#!/usr/bin/env python3
"""Focused browser regression for the two score scopes on the final board.

Uses the live state machine with the original three child images forced before
``game.js`` initializes. This makes the teaching route reproducible: review
changes 1/3 to 2/3, while the independent final set is 1/3.
"""
import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright


HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entry", type=Path, default=HERE / "index.html",
                        help="HTML entry to check; defaults to the source game")
    entry = parser.parse_args().entry.resolve()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        game_source = (entry.parent / "game.js").read_text()
        page.route("**/game.js", lambda route: route.fulfill(
            status=200,
            content_type="application/javascript",
            body="GalaxySession.choose = base => [...base.childIds];\n" + game_source,
        ))
        page.goto(entry.as_uri())
        page.wait_for_function("window.galaxyGame && window.GALAXY_DATA")

        before, unchanged = page.evaluate("""() => {
          const game = window.galaxyGame;
          const data = window.GALAXY_DATA;
          const labels = Object.fromEntries(data.images.map(image => [image.id, image.label]));
          const dispatch = action => game.model.dispatch(action);
          dispatch({type: 'START'});
          dispatch({type: 'LABELS'});
          for (const id of data.childIds) dispatch({type: 'SET_LABEL', id, label: labels[id]});
          dispatch({type: 'RUN'});
          const before = game.model.state.current.review;
          dispatch({type: 'REPAIR'});
          dispatch({type: 'RUN'});
          const unchanged = game.model.state.current.review;
          game.render();
          return [before, unchanged];
        }""")

        assert before["correct"] == unchanged["correct"] == 1, (before, unchanged)
        assert page.locator(".before-answer").count() == 0
        assert "Первая проверка" not in page.locator(".score-strip").inner_text()
        assert page.locator("[data-review-limitation]").count() == 1

        page.locator('[data-action="finish"]').click()
        unchanged_scope = page.locator('[data-score-scope="review-after"]')
        assert "повторная проверка" in unchanged_scope.inner_text()
        assert "после правок" not in unchanged_scope.inner_text()
        page.evaluate("""() => {
          galaxyGame.model.dispatch({type: 'LABELS'});
          galaxyGame.render();
        }""")

        after, final = page.evaluate("""() => {
          const game = window.galaxyGame;
          const data = window.GALAXY_DATA;
          const labels = Object.fromEntries(data.images.map(image => [image.id, image.label]));
          const dispatch = action => game.model.dispatch(action);
          dispatch({type: 'REPAIR'});
          for (const id of data.oldIds) dispatch({type: 'SET_LABEL', id, label: labels[id]});
          dispatch({type: 'RUN'});
          const after = game.model.state.current.review;
          const final = game.model.state.current.final;
          game.render();
          return [after, final];
        }""")

        assert after["correct"] == 2 and final["correct"] == 1, (after, final)
        limitation = page.locator("[data-review-limitation]")
        assert limitation.count() == 1
        assert "не влияет" in limitation.inner_text()
        page.locator('[data-action="finish"]').click()
        page.wait_for_function("galaxyGame.model.state.phase === 'final'")

        before_scope = page.locator('[data-score-scope="review-before"]')
        after_scope = page.locator('[data-score-scope="review-after"]')
        final_scope = page.locator('[data-score-scope="final"][data-final-independent]')
        assert before_scope.count() == after_scope.count() == final_scope.count() == 1
        assert f"{before['correct']} из {before['total']}" in before_scope.inner_text()
        assert f"{after['correct']} из {after['total']}" in after_scope.inner_text()
        assert f"{final['correct']} из {final['total']}" in final_scope.inner_text()
        assert "другая подборка" in final_scope.inner_text()
        assert "не к твоей работе" in page.locator(".board-score-note").inner_text()
        assert page.locator(".board-score-summary").bounding_box()["width"] > 0
        assert not errors, errors
        browser.close()
    print({"status": "PASS", "review": [before["correct"], after["correct"]], "final": final["correct"]})


if __name__ == "__main__":
    main()
