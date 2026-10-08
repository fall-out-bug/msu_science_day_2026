#!/usr/bin/env python3
"""Focused browser regression for the CNN before/after and architecture scopes."""
import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entry", type=Path, default=HERE / "index.html")
    entry = parser.parse_args().entry.resolve()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(entry.as_uri())
        page.wait_for_function("window.galaxyGame && window.GALAXY_CNN_EXPERIMENTS")

        before, corrected = page.evaluate("""() => {
          const game=galaxyGame, data=GALAXY_DATA;
          const truth=Object.fromEntries(data.images.map(item=>[item.id,item.label]));
          const send=action=>game.model.dispatch(action);
          send({type:'START'}); send({type:'LABELS'});
          for(const id of data.childIds) send({type:'SET_LABEL',id,label:truth[id]});
          send({type:'RUN'}); const before=game.model.state.current;
          send({type:'REPAIR'});
          for(const id of data.oldIds) send({type:'SET_LABEL',id,label:truth[id]});
          send({type:'RUN'}); const corrected=game.model.state.current;
          game.render(); return [before,corrected];
        }""")
        assert before["labelKey"] == "01210" and before["architecture"] == "1"
        assert corrected["labelKey"] == "01202" and corrected["architecture"] == "1"
        assert before["result"]["review"]["correct"] == 1
        assert corrected["result"]["review"]["correct"] == 2
        assert corrected["result"]["final"]["correct"] == 3
        assert page.locator('[data-action="architecture"][data-architecture="2"]').count() == 1

        page.locator('[data-action="architecture"][data-architecture="2"]').click()
        assert page.evaluate("galaxyGame.model.state.current === null")
        page.locator('[data-action="run"]').first.click()
        page.wait_for_function("galaxyGame.model.state.current && galaxyGame.model.state.current.architecture === '2'")
        two = page.evaluate("galaxyGame.model.state.current")
        assert two["labelKey"] == "01202" and two["result"]["review"]["correct"] == 2
        assert two["result"]["final"]["correct"] == 2
        assert page.locator('.architecture-choice').inner_text().count('2 блока') == 1

        page.locator('[data-action="finish"]').click()
        page.wait_for_function("galaxyGame.model.state.phase === 'final'")
        before_scope=page.locator('[data-score-scope="review-before"]')
        after_scope=page.locator('[data-score-scope="review-after"]')
        final_scope=page.locator('[data-score-scope="final"]')
        assert before_scope.count() == after_scope.count() == final_scope.count() == 1
        assert "1 из 3" in before_scope.inner_text()
        assert "2 из 3" in after_scope.inner_text()
        assert "2 из 3" in final_scope.inner_text()
        assert "которых не было в обучении" in final_scope.inner_text()
        assert "1 блок" in before_scope.inner_text()
        assert "2 блок" in after_scope.inner_text()
        assert page.locator('.board-score-summary').bounding_box()['width'] > 0
        assert not errors, errors
        browser.close()
    print({"status":"PASS","review":[1,2],"twoBlockFinal":2})


if __name__ == "__main__":
    main()
