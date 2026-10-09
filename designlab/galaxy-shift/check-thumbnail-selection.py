#!/usr/bin/env python3
"""Regression for async CNN thumbnail selection.

Uses the ordinary visible journey to the free CNN workbench.  It proves that
selection follows the latest click even if an earlier image decode completes
later, and that a failed decode leaves the current photo and workbench intact.
"""
import importlib.util
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
OUT = Path(os.environ.get("GALAXY_THUMBNAIL_EVIDENCE", HERE.parent.parent / "docs" / "design-2026-10-09" / "evidence" / "lesson-thumbnail-selection.json"))

def load_visible_editor(page):
    spec = importlib.util.spec_from_file_location("continuity", HERE / "check-continuity-browser.py")
    flow = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(flow)
    page.goto((HERE / "index.html").as_uri())
    flow.wait_ready(page)
    flow.prepare_editor(page)
    page.wait_for_selector(".cnn-workbench")


def selected(page):
    return page.locator('[data-action="cnn-image"][aria-pressed="true"]').get_attribute("data-image-id")


def main_src(page):
    return page.locator(".cnn-workbench__open img").get_attribute("src")


def install_decode_hook(page, source, mode):
    page.evaluate("""([source, mode]) => {
      const original = Image.prototype.decode;
      let once = true;
      Image.prototype.decode = function () {
        if (this.src !== source) return original.call(this);
        if (mode === 'slow') return new Promise(resolve => setTimeout(resolve, 300));
        if (mode === 'fail-once' && once) {
          once = false;
          return Promise.reject(new DOMException('controlled decode failure', 'EncodingError'));
        }
        return original.call(this);
      };
    }""", [source, mode])


def main():
    report = {"status": "PASS", "scenarios": [], "browserErrors": []}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.on("pageerror", lambda error: report["browserErrors"].append(str(error)))
        load_visible_editor(page)
        thumbs = page.locator('[data-action="cnn-image"]')
        ids = thumbs.evaluate_all("els => els.map(el => el.dataset.imageId)")
        sources = thumbs.evaluate_all("els => els.map(el => el.querySelector('img').src)")
        source_attrs = thumbs.evaluate_all("els => els.map(el => el.querySelector('img').getAttribute('src'))")
        assert len(ids) == len(sources) == len(source_attrs) == 3
        page.evaluate("window.__thumbnailWorkspace = document.querySelector(\'.cnn-workbench\')")

        # Ordinary: each of the three thumbnails takes over the main photo.
        ordinary = []
        for image_id in ids:
            page.locator(f'[data-action="cnn-image"][data-image-id="{image_id}"]').click()
            page.wait_for_function("id => document.querySelector('[data-action=\"cnn-image\"][aria-pressed=\"true\"]')?.dataset.imageId === id", arg=image_id)
            assert main_src(page).endswith(source_attrs[ids.index(image_id)])
            ordinary.append({"selected": selected(page), "mainSrc": main_src(page)})
        assert [item["selected"] for item in ordinary] == ids
        report["scenarios"].append({"name": "ordinary-three-thumbnails", "status": "PASS", "selected": ids})

        # First decode resolves after the second.  The second (latest) click wins.
        install_decode_hook(page, sources[0], "slow")
        page.locator(f'[data-action="cnn-image"][data-image-id="{ids[0]}"]').click()
        page.locator(f'[data-action="cnn-image"][data-image-id="{ids[1]}"]').click()
        page.wait_for_timeout(450)
        assert selected(page) == ids[1] and main_src(page).endswith(source_attrs[1])
        assert page.evaluate("document.querySelector(\'.cnn-workbench\') === window.__thumbnailWorkspace")
        report["scenarios"].append({"name": "reordered-decode-completion", "status": "PASS", "latest": ids[1]})

        # Failed decode must neither replace the selected photo nor replace the workbench;
        # the next click can retry the same thumbnail successfully.
        before = {"selected": selected(page), "mainSrc": main_src(page)}
        install_decode_hook(page, sources[2], "fail-once")
        page.locator(f'[data-action="cnn-image"][data-image-id="{ids[2]}"]').click()
        page.wait_for_timeout(120)
        assert selected(page) == before["selected"] and main_src(page) == before["mainSrc"]
        assert page.evaluate("document.querySelector(\'.cnn-workbench\') === window.__thumbnailWorkspace")
        page.locator(f'[data-action="cnn-image"][data-image-id="{ids[2]}"]').click()
        page.wait_for_function("id => document.querySelector('[data-action=\"cnn-image\"][aria-pressed=\"true\"]')?.dataset.imageId === id", arg=ids[2])
        assert selected(page) == ids[2] and main_src(page).endswith(source_attrs[2])
        report["scenarios"].append({"name": "decode-failure-and-retry", "status": "PASS", "retained": before["selected"], "retried": ids[2]})
        browser.close()
    assert not report["browserErrors"], report["browserErrors"]
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("PASS", OUT)


if __name__ == "__main__":
    main()
