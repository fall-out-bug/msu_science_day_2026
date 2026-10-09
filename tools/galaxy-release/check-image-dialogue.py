#!/usr/bin/env python3
"""Visible regression for image-specific Nika explanations in annotation work."""
import argparse
import importlib.util
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
GAME = ROOT / "designlab" / "galaxy-shift"
DEFAULT_OUT = Path(os.environ.get(
    "GALAXY_DIALOGUE_EVIDENCE",
    ROOT / "docs" / "design-2026-10-09" / "evidence" / "dialogue-briefings.json",
))
TOPICS = {
    "child_m85": "обучающая выборка",
    "child_ic5332": "признаки",
    "child_ngc5023": "ракурс",
    "fixed_ngc3318": "машинное обучение",
    "old_ngc3610": "качество данных",
    "old_ngc7090": "шум в метках",
    "fixed_ngc691": "контролируемый эксперимент",
}


def continuity():
    spec = importlib.util.spec_from_file_location("continuity", GAME / "check-continuity-browser.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def image_id(page):
    return page.locator("#quest-scene").get_attribute("data-image-id")


def line(page):
    return page.locator(".quest-scene__conversation [role=status]").inner_text()


def assert_dialogue(page, expected_id):
    assert image_id(page) == expected_id, (image_id(page), expected_id)
    text = line(page)
    assert TOPICS[expected_id] in text.lower(), (expected_id, text)
    return text


def choose_visible_label(page, expected_id):
    before = assert_dialogue(page, expected_id)
    page.locator(f'[data-label-id="{expected_id}"]').first.click()
    assert line(page) == before, "выбор метки не должен заменить пояснение понятия"


def hint_roundtrip(page, expected_id):
    before = assert_dialogue(page, expected_id)
    page.locator('[data-quest="hint"]').click()
    assert line(page) != before, "подсказка должна отдельно говорить о форме снимка"
    page.locator('[data-quest="hint"]').click()
    assert line(page) == before, "возврат из подсказки должен восстановить пояснение понятия"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=DEFAULT_OUT)
    output = parser.parse_args().evidence
    flow = continuity()
    report = {"status": "PASS", "checks": [], "browserErrors": []}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 720}, reduced_motion="reduce")
        page = context.new_page()
        page.on("pageerror", lambda error: report["browserErrors"].append(str(error)))
        page.goto((GAME / "index.html").as_uri())
        flow.wait_ready(page)
        data = flow.enter_labels(page)
        children = list(data["childIds"])
        assert children == list(TOPICS)[:4], children

        originals = {}
        for index, item_id in enumerate(children):
            text = assert_dialogue(page, item_id)
            originals[item_id] = text
            choose_visible_label(page, item_id)
            hint_roundtrip(page, item_id)
            report["checks"].append({"image": item_id, "topic": TOPICS[item_id], "phase": "labels", "text": text})
            if index + 1 < len(children):
                flow.click(page, "next")

        for item_id in reversed(children[:-1]):
            flow.click(page, "previous")
            assert_dialogue(page, item_id)
            assert line(page) == originals[item_id]
        for item_id in children[1:]:
            flow.click(page, "next")
            assert line(page) == originals[item_id]

        before_reload = line(page)
        page.reload(); flow.wait_ready(page)
        assert page.locator('[data-action="resume"]').count(), "разметка должна предлагать продолжение после перезагрузки"
        flow.click(page, "resume")
        assert_dialogue(page, children[-1])
        assert line(page) == before_reload

        flow.click(page, "run")
        page.wait_for_function("galaxyGame.model.state.phase === 'review'")
        page.wait_for_selector(".score-strip")
        review_text = page.locator(".station").inner_text().lower()
        for term in ("проверочная выборка", "предсказания"):
            assert term in review_text, term
        flow.click(page, "repair")
        old_ids = list(data["oldIds"])
        assert old_ids == list(TOPICS)[4:], old_ids
        for index, item_id in enumerate(old_ids):
            assert_dialogue(page, item_id)
            originals[item_id] = line(page)
            choose_visible_label(page, item_id)
            hint_roundtrip(page, item_id)
            report["checks"].append({"image": item_id, "topic": TOPICS[item_id], "phase": "repair", "text": originals[item_id]})
            if index + 1 < len(old_ids):
                flow.click(page, "next")

        for item_id in reversed(old_ids[:-1]):
            flow.click(page, "previous")
            assert_dialogue(page, item_id)
            assert line(page) == originals[item_id]
        for item_id in old_ids[1:]:
            flow.click(page, "next")
            assert line(page) == originals[item_id]
        before_repair_reload = line(page)
        page.reload(); flow.wait_ready(page)
        assert page.locator('[data-action="resume"]').count(), "проверка старых меток должна переживать перезагрузку"
        flow.click(page, "resume")
        assert_dialogue(page, old_ids[-1])
        assert line(page) == before_repair_reload
        flow.click(page, "run")
        page.wait_for_function("galaxyGame.model.state.phase === 'review'")
        assert not page.locator('[data-action="finish"]').count(), "новый CNN-маршрут остаётся обязательным, но разметка не блокируется"
        context.close(); browser.close()
    assert not report["browserErrors"], report["browserErrors"]
    texts = [item["text"] for item in report["checks"] if "text" in item]
    assert len(texts) == len(set(texts)) == 7, "семь основных реплик должны быть различимы"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output.read_text())


if __name__ == "__main__":
    main()
