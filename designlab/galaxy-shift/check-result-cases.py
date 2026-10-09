#!/usr/bin/env python3
"""A06: visible result cases from calculated CNN shards, with no state injection."""
import contextlib
import http.server
import json
import socketserver
import threading
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
EVIDENCE = Path(os.environ.get("GALAXY_RECOMPOSE_RESULT_CASES_EVIDENCE", HERE.parent.parent / "docs" / "design-2026-10-09" / "evidence" / "recompose-result-cases.json"))


@contextlib.contextmanager
def local_http():
    class Server(socketserver.TCPServer):
        allow_reuse_address = True

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(HERE), **kwargs)

        def log_message(self, *_):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.send_response(204)
            self.end_headers()

    handler = Handler
    server = Server(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/index.html"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def click(page, action):
    page.locator(f'[data-action="{action}"]').first.click()


def collect(page, image_id):
    page.locator(f'.sky-atlas [data-target="{image_id}"]').click()
    page.wait_for_timeout(700)
    point = page.evaluate("galaxyGame.sky.snapshot().targetPixel")
    page.mouse.click(point["x"], point["y"])
    page.wait_for_function("galaxyGame.sky.state().aligned")
    page.locator(".sky-atlas__open").click()


def start_labels(page):
    click(page, "start-route")
    click(page, "collect-map")
    data = page.evaluate("GALAXY_DATA")
    for image_id in data["childIds"]:
        collect(page, image_id)
    page.locator(".sky-atlas__complete").click()
    page.wait_for_function("galaxyGame.model.state.phase === 'tutorial'")
    click(page, "labels")
    return data


def set_labels(page, ids, labels):
    for index, image_id in enumerate(ids):
        page.locator(f'[data-label-id="{image_id}"][data-label="{labels[image_id]}"]').click()
        if index + 1 < len(ids):
            click(page, "next")


def run(page):
    click(page, "run")
    page.wait_for_function("galaxyGame.model.state.phase === 'review' && galaxyGame.model.state.current")


def repair_and_run(page, data, labels):
    click(page, "repair")
    page.wait_for_function("galaxyGame.model.state.phase === 'repair'")
    set_labels(page, data["oldIds"], labels)
    run(page)


def complete_guide(page, return_to_one_layer=False):
    page.wait_for_selector('.cnn-workbench .architecture-editor')
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
    if return_to_one_layer:
        page.locator('[data-action="architecture-depth"][data-depth="1"]').click()
        click(page, 'architecture-save')
        page.wait_for_function("galaxyGame.model.state.current?.architecture === 'd1-r'")


def table_run(page, key, architecture):
    return page.evaluate("""([key, architecture]) => {
      const run = GALAXY_CNN_EXPERIMENTS.experiments[key].architectures[architecture];
      return JSON.parse(JSON.stringify(run));
    }""", [key, architecture])


def label_map(data, values):
    classes = [item["id"] for item in data["classes"]]
    return {image_id: classes[int(value)] for image_id, value in zip(data["editableIds"], values)}


def current_key(page):
    return page.evaluate("galaxyGame.model.state.current.labelKey")


def card_texts(page):
    return page.locator(".cnn-workbench__results article, .result-grid .result").all_text_contents()


def assert_cards_match(page, before, after):
    labels = page.evaluate("Object.fromEntries(GALAXY_DATA.classes.map(item => [item.id, item.label]))")
    cards = card_texts(page)
    assert len(cards) == len(after["review"]["predictions"])
    for card, old, new in zip(cards, before["review"]["predictions"], after["review"]["predictions"]):
        assert f"До: {labels[old['predicted']]}" in card, card
        assert f"После: {labels[new['predicted']]}" in card, card
        assert f"Справочная: {labels[new['expected']]}" in card, card


def no_prediction_change(page):
    data = start_labels(page)
    images = {item["id"]: item for item in data["images"]}
    initial_old = data["initialOldLabels"]
    set_labels(page, data["childIds"], {image_id: images[image_id]["label"] for image_id in data["childIds"]})
    run(page)
    before_key = current_key(page)
    before = table_run(page, before_key, "d1-r")
    corrected = dict(initial_old)
    corrected["old_ngc3610"] = images["old_ngc3610"]["label"]
    repair_and_run(page, data, corrected)
    after_key = current_key(page)
    after = table_run(page, after_key, "d1-r")
    assert before_key == "0121100" and after_key == "0121000"
    assert [row["predicted"] for row in before["review"]["predictions"]] == [row["predicted"] for row in after["review"]["predictions"]]
    comparison = page.locator("[data-comparison]").inner_text()
    assert "Архитектура та же; изменены метки обучающих снимков." in comparison
    assert "Предсказания не изменились." in comparison
    assert not page.locator('[data-action="finish"]').count()
    assert_cards_match(page, before, after)
    complete_guide(page)
    assert page.locator('[data-action="finish"]').is_enabled()
    return {"keys": [before_key, after_key], "review": [before["review"]["correct"], after["review"]["correct"]], "comparison": comparison}


def architecture_degrades(page):
    data = start_labels(page)
    labels = label_map(data, "0001110")
    set_labels(page, data["childIds"], labels)
    run(page)
    repair_and_run(page, data, labels)
    key = current_key(page)
    before = table_run(page, key, "d1-r")
    assert key == "0001110" and before["review"]["correct"] == 1
    complete_guide(page, return_to_one_layer=True)
    page.wait_for_selector('[data-action="layer-add"][data-layer="bn"]')
    page.locator('[data-action="layer-add"][data-layer="bn"]').click()
    assert page.locator('[data-action="architecture-save"]').get_attribute("data-architecture") == "d1-r-bn"
    click(page, "architecture-save")
    page.wait_for_function("galaxyGame.model.state.current?.architecture === 'd1-r-bn'")
    after = table_run(page, key, "d1-r-bn")
    assert after["review"]["correct"] == 0
    comparison = page.locator("[data-comparison]").inner_text()
    assert "Метки те же; изменена архитектура." in comparison
    assert "Изменилось ответов: 2 из 3." in comparison
    assert "Правильных ответов стало меньше: 1 → 0." in comparison
    assert page.locator('[data-action="finish"]').is_enabled()
    assert_cards_match(page, before, after)
    return {"key": key, "architectures": ["d1-r", "d1-r-bn"], "review": [1, 0], "comparison": comparison}


def architectures_keep_predictions(page):
    data = start_labels(page)
    labels = label_map(data, "0121021")
    set_labels(page, data["childIds"], labels)
    run(page)
    repair_and_run(page, data, labels)
    key = current_key(page)
    assert key == "0121021"
    complete_guide(page, return_to_one_layer=True)

    # First checked architecture: add Dropout after the required ReLU.
    page.locator('[data-action="layer-add"][data-layer="d"]').click()
    assert page.locator('[data-action="architecture-save"]').get_attribute("data-architecture") == "d1-r-d"
    click(page, "architecture-save")
    page.wait_for_function("galaxyGame.model.state.current?.architecture === 'd1-r-d'")
    before = table_run(page, key, "d1-r-d")

    # Second checked architecture: use the editor control to move Dropout before ReLU.
    page.locator('[data-action="layer-earlier"][data-layer-index="1"]').click()
    assert page.locator('[data-action="architecture-save"]').get_attribute("data-architecture") == "d1-d-r"
    click(page, "architecture-save")
    page.wait_for_function("galaxyGame.model.state.current?.architecture === 'd1-d-r'")
    after = table_run(page, key, "d1-d-r")

    assert [row["predicted"] for row in before["review"]["predictions"]] == [row["predicted"] for row in after["review"]["predictions"]]
    comparison = page.locator("[data-comparison]").inner_text()
    assert "Метки те же; изменена архитектура." in comparison
    assert "Предсказания не изменились." in comparison
    assert page.locator('[data-action="finish"]').is_enabled()
    assert_cards_match(page, before, after)
    return {"key": key, "architectures": ["d1-r-d", "d1-d-r"], "review": [before["review"]["correct"], after["review"]["correct"]], "comparison": comparison}


def final_has_error(page):
    data = start_labels(page)
    images = {item["id"]: item for item in data["images"]}
    canonical = {image_id: images[image_id]["label"] for image_id in data["editableIds"]}
    set_labels(page, data["childIds"], canonical)
    run(page)
    repair_and_run(page, data, canonical)
    key = current_key(page)
    complete_guide(page, return_to_one_layer=True)
    page.locator('[data-action="layer-add"][data-layer="bn"]').click()
    page.locator('[data-action="layer-earlier"][data-layer-index="1"]').click()
    page.locator('[data-action="layer-add"][data-layer="d"]').click()
    assert page.locator('[data-action="architecture-save"]').get_attribute("data-architecture") == "d1-bn-r-d"
    click(page, "architecture-save")
    page.wait_for_function("galaxyGame.model.state.current?.architecture === 'd1-bn-r-d'")
    expected = table_run(page, key, "d1-bn-r-d")
    assert expected["final"]["correct"] == 2
    click(page, "finish")
    page.wait_for_function("galaxyGame.model.state.phase === 'final'")
    page.wait_for_selector(".final-room .result-grid .result-info", state="attached")
    final_cards = card_texts(page)
    labels = page.evaluate("Object.fromEntries(GALAXY_DATA.classes.map(item => [item.id, item.label]))")
    assert any("NGC 2768" in card and "Проверим ?" in card and f"Модель: {labels['edge_on']}" in card and f"Справочная метка: {labels['smooth']}" in card for card in final_cards), final_cards
    return {"key": key, "architecture": "d1-bn-r-d", "final": expected["final"]["correct"], "errorImage": "final_ngc2768"}


def main():
    result = {"status": "FAIL", "checks": [], "failures": []}
    with local_http() as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for name, check in (("correction_without_prediction_change", no_prediction_change), ("architecture_degrades", architecture_degrades), ("architectures_keep_predictions", architectures_keep_predictions), ("final_has_error", final_has_error)):
                context = browser.new_context(viewport={"width": 1280, "height": 720}, reduced_motion="reduce")
                page = context.new_page()
                try:
                    page.goto(url, wait_until="domcontentloaded")
                    page.wait_for_function("window.galaxyGame && galaxyGame.model.state.phase === 'intro'")
                    detail = check(page)
                except Exception as error:
                    result["failures"].append({"case": name, "detail": str(error)})
                else:
                    result["checks"].append({"case": name, "status": "PASS", **detail})
                finally:
                    context.close()
        finally:
            browser.close()
    if not result["failures"]:
        result["status"] = "PASS"
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
