#!/usr/bin/env python3
"""Visible-control continuity acceptance for A07, A08 and A10.

The browser never dispatches model actions from this check.  State reads are
assertions after a person-visible button click or keyboard label choice.
"""
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
REPORT = Path(os.environ.get("GALAXY_RECOMPOSE_CONTINUITY_EVIDENCE", HERE.parent.parent / "docs" / "design-2026-10-09" / "evidence" / "recompose-continuity.json"))
URL = (HERE / "index.html").as_uri()


class Checks:
    def __init__(self):
        self.items = []

    def run(self, criterion, callback):
        try:
            detail = callback()
        except Exception as error:
            self.items.append({"criterion": criterion, "status": "FAIL", "detail": str(error)})
        else:
            self.items.append({"criterion": criterion, "status": "PASS", "detail": detail or "visible controls at 1280x720"})


def click(page, action):
    page.locator(f'[data-action="{action}"]').first.click()


def state(page):
    return page.evaluate("galaxyGame.model.serialize().state")


def current(page):
    return page.evaluate("galaxyGame.model.state.current")


def wait_ready(page):
    page.wait_for_function("window.galaxyGame && window.GalaxyArchitectures && window.GALAXY_CNN_EXPERIMENTS")


def collect(page, item_id):
    page.locator(f'.sky-atlas [data-target="{item_id}"]').click()
    page.wait_for_timeout(700)
    snapshot = page.evaluate("galaxyGame.sky.snapshot()")
    page.mouse.click(snapshot["targetPixel"]["x"], snapshot["targetPixel"]["y"])
    page.wait_for_function("galaxyGame.sky.state().aligned")
    page.locator(".sky-atlas__open").click()


def enter_labels(page):
    click(page, "start-route")
    click(page, "collect-map")
    data = page.evaluate("GALAXY_DATA")
    for item_id in data["childIds"]:
        collect(page, item_id)
    page.locator(".sky-atlas__complete").click()
    page.wait_for_function("galaxyGame.model.state.phase === 'tutorial'")
    click(page, "labels")
    return data


def label_children(page, data):
    images = {item["id"]: item for item in data["images"]}
    for index, item_id in enumerate(data["childIds"]):
        page.locator(f'[data-label-id="{item_id}"][data-label="{images[item_id]["label"]}"]').click()
        if index < len(data["childIds"]) - 1:
            click(page, "next")


def prepare_review(page):
    data = enter_labels(page)
    label_children(page, data)
    click(page, "run")
    page.wait_for_function("galaxyGame.model.state.phase === 'review'")
    return data


def prepare_repair(page):
    data = prepare_review(page)
    click(page, "repair")
    page.wait_for_function("galaxyGame.model.state.phase === 'repair'")
    return data


def confirm_old(page, data):
    images = {item["id"]: item for item in data["images"]}
    for index, item_id in enumerate(data["oldIds"]):
        page.locator(f'[data-label-id="{item_id}"][data-label="{images[item_id]["label"]}"]').click()
        if index < len(data["oldIds"]) - 1:
            click(page, "next")


def complete_guide(page):
    page.wait_for_selector('.cnn-workbench .architecture-editor')
    page.wait_for_function("galaxyGame.model.state.cnnGuide === 'bridge'")
    click(page, 'guide-open')
    page.wait_for_function("galaxyGame.model.state.cnnGuide === 'intro'")
    click(page, 'guide-add-convolution')
    page.wait_for_function("galaxyGame.model.state.cnnGuide === 'compare'")
    click(page, 'run')
    page.wait_for_function("galaxyGame.model.state.cnnGuide === 'observe'")
    click(page, 'guide-confirm-compare')
    page.wait_for_function("galaxyGame.model.state.cnnGuide === 'independent'")
    page.locator('[data-action="architecture-depth"][data-depth="1"]').click()
    click(page, 'architecture-save')
    page.wait_for_function("galaxyGame.model.state.cnnGuide === 'independent-observe'")
    click(page, 'independent-confirm')
    page.wait_for_function("galaxyGame.model.state.cnnGuide === 'complete'")


def prepare_editor(page):
    data = prepare_repair(page)
    confirm_old(page, data)
    click(page, "run")
    page.wait_for_function("galaxyGame.model.state.phase === 'review'")
    complete_guide(page)
    assert page.locator('.cnn-workbench .architecture-editor').is_visible()
    return data


def prepare_final(page):
    data = prepare_repair(page)
    confirm_old(page, data)
    click(page, "run")
    page.wait_for_function("galaxyGame.model.state.phase === 'review'")
    complete_guide(page)
    click(page, "finish")
    page.wait_for_function("galaxyGame.model.state.phase === 'final'")
    # State advances before the atomic image decode/surface swap. Persisted
    # continuity begins only once the final screen is actually visible.
    page.wait_for_selector(".final-room")
    page.locator("#experience-loading").wait_for(state="detached")
    return data


def preserved(before, after):
    for key in ("labels", "architecture", "reviewedOldIds", "repairCheckedLabelKey", "current", "cnnGuide"):
        assert after[key] == before[key], key


def home_resume(page, setup, expected_phase, expects_editor=False):
    setup(page)
    before = state(page)
    click(page, "home")
    assert page.locator('[data-action="resume"]').is_visible()
    click(page, "resume")
    page.wait_for_function(f"galaxyGame.model.state.phase === '{expected_phase}'")
    after = state(page)
    preserved(before, after)
    assert not after["modelSettings"]
    if expects_editor:
        assert page.locator('.cnn-workbench .architecture-editor').is_visible()


def reload_continue(page, setup, expected_phase, expects_editor=False):
    setup(page)
    before = state(page)
    page.reload()
    wait_ready(page)
    assert page.locator('[data-action="resume"]').is_visible()
    click(page, "resume")
    page.wait_for_function(f"galaxyGame.model.state.phase === '{expected_phase}'")
    after = state(page)
    preserved(before, after)
    assert not after["modelSettings"]
    if expects_editor:
        assert page.locator('.cnn-workbench .architecture-editor').is_visible()


def partial_collection(page):
    click(page, "start-route")
    click(page, "collect-map")
    data = page.evaluate("GALAXY_DATA")
    collect(page, data["childIds"][0])
    page.locator(".sky-atlas__close").click()
    return data


def reload_partial_collection(page):
    data = partial_collection(page)
    before = state(page)
    page.reload()
    wait_ready(page)
    assert page.locator('[data-action="resume"]').is_visible()
    assert page.evaluate("galaxyGame.found") == [data["childIds"][0]]
    click(page, "resume")
    assert page.locator('[data-action="collect-map"]').is_visible()
    assert state(page) == before
    click(page, "collect-map")
    assert page.evaluate("galaxyGame.found") == [data["childIds"][0]]
    page.locator(".sky-atlas__close").click()


def partial_labels(page):
    data = enter_labels(page)
    image = next(item for item in data["images"] if item["id"] == data["childIds"][0])
    page.locator(f'[data-label-id="{image["id"]}"][data-label="{image["label"]}"]').click()
    return data


def changed_final(page):
    data = prepare_final(page)
    old = current(page)
    page.locator("details.research-board summary").first.click()
    click(page, "labels")
    child_id = data["childIds"][0]
    current_label = state(page)["labels"][child_id]
    new_label = next(item["id"] for item in data["classes"] if item["id"] != current_label)
    page.locator(f'[data-label-id="{child_id}"][data-label="{new_label}"]').click()
    click(page, "run")
    page.wait_for_function("galaxyGame.model.state.phase === 'review'")
    changed = state(page)
    changed_current = current(page)
    assert changed_current["resultKey"] != old["resultKey"], (old, changed_current)
    assert changed["repairCheckedLabelKey"] is None, changed
    click(page, "repair")
    confirm_old(page, data)
    assert set(state(page)["reviewedOldIds"]) == set(data["oldIds"]), state(page)
    click(page, "run")
    page.wait_for_function("galaxyGame.model.state.phase === 'review'")
    repaired = state(page)
    repaired_current = current(page)
    assert repaired["repairCheckedLabelKey"] == repaired["current"]["labelKey"], repaired
    assert repaired_current["resultKey"] == changed_current["resultKey"], (changed_current, repaired_current)
    # The mandatory experience is already complete.  Free editing after it
    # preserves that completion; it must not create a second mandatory guide.
    assert repaired["cnnGuide"] == "complete", repaired
    click(page, "finish")
    page.wait_for_function("galaxyGame.model.state.phase === 'final'")
    page.locator("details.research-board summary").first.click()
    assert "повторный просмотр" in page.locator(".final-note").inner_text().lower(), page.locator(".final-note").inner_text()


def reload_guided_steps(page):
    data = prepare_repair(page)
    confirm_old(page, data)
    click(page, 'run')
    for action, stage in (('guide-open', 'intro'), ('guide-add-convolution', 'compare'), ('run', 'observe'), ('guide-confirm-compare', 'independent'), ('architecture-depth', 'independent'), ('architecture-save', 'independent-observe'), ('independent-confirm', 'complete')):
        if action == 'architecture-depth':
            page.locator('[data-action="architecture-depth"][data-depth="1"]').click()
        else:
            click(page, action)
        page.wait_for_function(f"galaxyGame.model.state.cnnGuide === '{stage}'")
        before = state(page)
        page.reload(); wait_ready(page); click(page, 'resume')
        preserved(before, state(page))
        assert page.locator('.modal').count() == 0
        assert page.locator('.cnn-workbench .architecture-editor').is_visible()
    click(page, 'finish')
    page.wait_for_function("galaxyGame.model.state.phase === 'final'")
    return 'All three direct guided transitions survived reload/resume and reached final'


def main():
    checks = Checks()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        def new_page():
            context = browser.new_context(viewport={"width": 1280, "height": 720}, reduced_motion="reduce")
            page = context.new_page()
            page.goto(URL)
            wait_ready(page)
            return context, page

        for title, setup, phase, editor in (
            ("A07 home/resume: labels", enter_labels, "labels", False),
            ("A07 home/resume: repair", prepare_repair, "repair", False),
            ("A07 home/resume: architecture editor", prepare_editor, "review", True),
            ("A07 home/resume: final", prepare_final, "final", False),
        ):
            context, page = new_page()
            checks.run(title, lambda p=page, s=setup, q=phase, e=editor: home_resume(p, s, q, e))
            context.close()

        context, page = new_page()
        checks.run("A08 reload/continue: partial collection", lambda: reload_partial_collection(page))
        context.close()
        for title, setup, phase, editor in (
            ("A08 reload/continue: partial labels", partial_labels, "labels", False),
            ("A08 reload/continue: repair", prepare_repair, "repair", False),
            ("A08 reload/continue: architecture editor", prepare_editor, "review", True),
            ("A08 reload/continue: final", prepare_final, "final", False),
        ):
            context, page = new_page()
            checks.run(title, lambda p=page, s=setup, q=phase, e=editor: reload_continue(p, s, q, e))
            context.close()

        context, page = new_page()
        def fresh_tab():
            prepare_repair(page)
            second = context.new_page()
            second.goto(URL)
            wait_ready(second)
            assert state(second)["phase"] == "intro"
            assert not second.locator('[data-action="resume"]').count()
            second.close()
        checks.run("A08 new tab starts a new shift", fresh_tab)
        context.close()

        context, page = new_page()
        checks.run("N09 reload each guided CNN step", lambda: reload_guided_steps(page))
        context.close()

        context, page = new_page()
        checks.run("A10 changed child label requires current repair and repeats final notice", lambda: changed_final(page))
        context.close()
        browser.close()

    failed = any(item["status"] == "FAIL" for item in checks.items)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({"status": "FAIL" if failed else "PASS", "viewport": [1280, 720], "checks": checks.items}, ensure_ascii=False, indent=2) + "\n")
    print(REPORT.read_text())
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
