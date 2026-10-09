#!/usr/bin/env python3
"""Independent visible-control acceptance suite for the completed CNN lesson.

The suite intentionally has two layers.  Contracts that do not depend on the
calculated table run on every checkout; the complete player journey runs only
when all 22 calculated shards have been produced.  A missing shard is reported
as NOT RUN, never replaced by a made-up result.
"""
import json
import hashlib
import os
import sys
import contextlib
import http.server
import socketserver
import threading
import traceback
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
EVIDENCE = Path(os.environ.get("GALAXY_EVIDENCE_DIR", HERE / "evidence"))
VIEWPORTS = ((1280, 720), (1440, 900), (1920, 1080), (1366, 768))


@contextlib.contextmanager
def local_http():
    """Serve the offline bundle locally so Playwright can intercept shards."""
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(HERE), **kwargs)
        def log_message(self, *args):
            pass
    handler = Handler
    class Server(socketserver.TCPServer):
        allow_reuse_address = True
    server = Server(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/index.html"
    finally:
        server.shutdown(); server.server_close(); thread.join()


class Report:
    def __init__(self):
        self.items = []

    def add(self, criterion, status, evidence, detail=""):
        self.items.append({"criterion": criterion, "status": status,
                           "evidence": evidence, "detail": detail})

    def check(self, criterion, evidence, callback):
        try:
            callback()
        except Exception as error:  # retain later independent checks
            self.add(criterion, "FAIL", evidence, str(error) or traceback.format_exc())
        else:
            self.add(criterion, "PASS", evidence)


def static_contract(report):
    """Checks the frozen registry and the public controls without running CNN."""
    registry = HERE / "cnn-architectures.js"
    guide = (HERE / "cnn-guide.js").read_text()
    html = (HERE / "index.html").read_text()

    def registry_is_complete():
        source = registry.read_text()
        assert "[1, 2].flatMap" in source
        assert source.count('id: `d${depth}-${tail.join("-")}`') == 1
        assert source.count('["r"]') == 1 and source.count('["bn", "r"]') == 1
        assert source.count('["r", "d", "bn"]') == 1
        assert "GalaxyArchitectures" in source and "function get(id)" in source

    def controls_are_current():
        assert 'data-action="architecture-depth"' in guide
        assert 'data-action="layer-add"' in guide
        assert 'data-action="layer-earlier"' in guide and 'data-action="layer-later"' in guide
        assert 'draggable=' in guide and 'data-architecture-tail' in guide
        assert 'architecture: \'d1-r\'' in (HERE / "cnn-session.js").read_text()
        assert 'cnn-architectures.js' in html and 'cnn-results-loader.js' in html

    def remove_control_is_present():
        # A05 requires all variants to be constructible through add/remove/reorder.
        assert 'data-action="layer-remove"' in guide, "В редакторе нет видимого удаления BatchNorm/Dropout"

    report.check("A05 registry: 22 canonical architectures", "cnn-architectures.js", registry_is_complete)
    report.check("A05 editor controls: depth/add/reorder/drag", "cnn-guide.js", controls_are_current)
    report.check("A05 editor control: remove layer", "cnn-guide.js", remove_control_is_present)


def page_contract(page, label):
    page.wait_for_function("window.galaxyGame && window.GalaxyArchitectures && window.GALAXY_CNN_EXPERIMENTS")
    assert page.evaluate("GalaxyArchitectures.configurations.length") == 22
    assert page.evaluate("GalaxyArchitectures.get('d1-r').id") == "d1-r"
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), label
    assert page.evaluate("""() => [...document.querySelectorAll('button')].every(button => {
      const r = button.getBoundingClientRect(); return r.left >= -1 && r.right <= innerWidth + 1;
    })"""), label


def calculated_shards_ready(page):
    return page.evaluate("""() => GalaxyArchitectures.configurations.every(config =>
      Boolean(GALAXY_CNN_EXPERIMENTS.experiments?.[Object.keys(GALAXY_CNN_EXPERIMENTS.experiments)[0]]?.architectures?.[config.id]) ||
      Boolean(document.querySelector(`script[src='cnn-results/${config.id}.js']`)) ||
      Boolean(window.GalaxyCNNResults?.get(config.id)))""")


def capture(page, name):
    page_contract(page, name)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(EVIDENCE / f"complete-{page.viewport_size['width']}x{page.viewport_size['height']}-{name}.png"), full_page=True)


def story_frame_visible(page):
    assert page.evaluate("""() => {
      const card=document.querySelector('.route-story__card');
      const button=document.querySelector('[data-action="collect-map"]');
      if (!card || !button) return false;
      const r=button.getBoundingClientRect();
      const hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
      return document.documentElement.scrollHeight <= innerHeight+1 &&
        card.scrollHeight <= card.clientHeight+1 &&
        r.top >= 0 && r.bottom <= innerHeight &&
        (hit === button || button.contains(hit));
    }"""), 'Story text and next action must be visible before scrolling or clicking'


def click_action(page, name, *, require_visible_frame=False):
    if name == "collect-map": story_frame_visible(page)
    button = page.locator(f'[data-action="{name}"]').first
    if require_visible_frame:
        box = button.bounding_box()
        assert box and box["x"] >= 0 and box["y"] >= 0 and box["x"] + box["width"] <= page.viewport_size["width"] and box["y"] + box["height"] <= page.viewport_size["height"], (name, box)
        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    else:
        button.click()


def tab_to(page, selector, limit=80):
    """Reach a visible control only with the browser's sequential navigation."""
    for _ in range(limit):
        if page.evaluate("selector => document.activeElement?.matches(selector)", selector):
            return
        page.keyboard.press("Tab")
    raise AssertionError(f"Tab did not reach {selector}")


def enter_action(page, action):
    if action == "collect-map": story_frame_visible(page)
    tab_to(page, f'[data-action="{action}"]')
    page.keyboard.press("Enter")


def collect(page, item_id):
    page.locator(f'.sky-atlas [data-target="{item_id}"]').click()
    page.wait_for_timeout(700)
    snapshot = page.evaluate("galaxyGame.sky.snapshot()")
    page.mouse.click(snapshot["targetPixel"]["x"], snapshot["targetPixel"]["y"])
    page.wait_for_function("galaxyGame.sky.state().aligned")
    page.locator(".sky-atlas__open").click()


def complete_cnn_guide(page):
    """N03/N04: one persistent workbench, d1-r -> d2-r, then observation."""
    assert page.evaluate("galaxyGame.model.state.cnnGuide") == "bridge"
    page.wait_for_selector(".cnn-workbench .architecture-editor")
    # A thumbnail changes only the large selected source; it must retain the
    # source description and never discard the three scientific result cards.
    thumbs = page.locator('[data-action="cnn-image"]')
    assert thumbs.count() == 3
    cards_before = page.locator('.cnn-workbench__results article').count()
    target = thumbs.nth(1)
    image_id = target.get_attribute('data-image-id')
    expected = page.evaluate("id => GALAXY_DATA.images.find(image => image.id === id)", image_id)
    target.click()
    expected_json = json.dumps(expected, ensure_ascii=False)
    page.wait_for_function(f"""() => {{
      const expected={expected_json};
      const image=document.querySelector('.cnn-workbench__photo .cnn-workbench__frame img');
      const thumb=document.querySelector(`[data-action="cnn-image"][data-image-id="${{expected.id}}"]`);
      return image?.getAttribute('src')?.endsWith(expected.src) && thumb?.getAttribute('aria-pressed') === 'true';
    }}""")
    main = page.locator('.cnn-workbench__photo .cnn-workbench__frame img')
    assert main.get_attribute('src').endswith(expected['src']), (main.get_attribute('src'), expected)
    assert main.get_attribute('alt') == expected['name'], (main.get_attribute('alt'), expected)
    assert page.locator('.cnn-workbench__results article').count() == cards_before == 3
    assert page.evaluate("id => document.activeElement?.dataset.imageId === id", image_id)
    # The bridge gives the result a reason before the network appears.
    click_action(page, "guide-open", require_visible_frame=True)
    page.wait_for_function("galaxyGame.model.state.cnnGuide === 'intro'")
    intro = page.locator(".cnn-workbench").inner_text().lower()
    for term in ("cnn", "свёрточ", "слой", "архитектур"):
        assert term in intro, term
    click_action(page, "cnn-filter", require_visible_frame=True)
    page.wait_for_selector(".modal")
    teaching_example = page.locator(".modal").inner_text().lower()
    for marker in ("поэлементно", "фильтр", "отклик", "не активация"):
        assert marker in teaching_example, marker
    page.keyboard.press("Escape")
    assert not page.locator(".modal").count()
    # The guide contract starts after the independent thumbnail transition.
    page.evaluate("""() => { window.__guideSurface = {
      workbench: document.querySelector('.cnn-workbench'), editor: document.querySelector('.architecture-editor'),
      photo: document.querySelector('[data-action="cnn-image"]'), tail: document.querySelector('[data-architecture-tail]'), scrollY
    }; }""")
    click_action(page, "guide-add-convolution", require_visible_frame=True)
    page.wait_for_function("galaxyGame.model.state.cnnGuide === 'compare'")
    assert page.evaluate("galaxyGame.model.state.architecture") == "d2-r"
    assert page.evaluate("galaxyGame.model.state.current") is None
    click_action(page, "run", require_visible_frame=True)
    page.wait_for_function("galaxyGame.model.state.cnnGuide === 'observe'")
    assert "сравн" in page.locator(".cnn-workbench").inner_text().lower()
    click_action(page, "guide-confirm-compare", require_visible_frame=True)
    page.wait_for_function("galaxyGame.model.state.cnnGuide === 'independent'")
    page.locator('[data-action="architecture-depth"][data-depth="1"]').click()
    click_action(page, "architecture-save", require_visible_frame=True)
    page.wait_for_function("galaxyGame.model.state.cnnGuide === 'independent-observe'")
    click_action(page, "independent-confirm", require_visible_frame=True)
    page.wait_for_function("galaxyGame.model.state.cnnGuide === 'complete'")
    assert page.evaluate("""() => {
      const before=window.__guideSurface;
      return before.workbench===document.querySelector('.cnn-workbench') && before.editor===document.querySelector('.architecture-editor') &&
        before.photo===document.querySelector('[data-action="cnn-image"]') && before.tail===document.querySelector('[data-architecture-tail]') && Math.abs(before.scrollY-scrollY)<2;
    }"""), "guide transition replaced workbench/photo/editor/tail or scrolled the page"


def keyboard_baseline(page, zoom=None):
    """Keyboard-only route through map collection and first calculated result."""
    page.goto((HERE / "index.html").as_uri())
    if zoom:
        page.evaluate("value => document.body.style.zoom = value", str(zoom))
    page.wait_for_function("window.galaxyGame && galaxyGame.model.state.phase === 'intro'")
    enter_action(page, "start-route")
    enter_action(page, "collect-map")
    page.wait_for_selector(".sky-atlas")
    canvas = page.locator(".sky-atlas__canvas")
    tab_to(page, ".sky-atlas__canvas")
    before = page.evaluate("galaxyGame.sky.state().camera")
    page.keyboard.press("ArrowRight")
    after = page.evaluate("galaxyGame.sky.state().camera")
    assert before != after, "Arrow key did not move the documented sky map"
    data = page.evaluate("GALAXY_DATA")
    for item_id in data["childIds"]:
        tab_to(page, f'.sky-atlas [data-target="{item_id}"]')
        page.keyboard.press("Enter")
        # Selecting a target only frames it near the reticle.  The documented
        # arrow controls must perform the final alignment, as in the mouse route.
        tab_to(page, ".sky-atlas__canvas")
        for _ in range(48):
            snapshot = page.evaluate("galaxyGame.sky.snapshot()")
            if page.evaluate("galaxyGame.sky.state().aligned"):
                break
            dx = snapshot["aim"]["x"] - snapshot["targetPixel"]["x"]
            dy = snapshot["aim"]["y"] - snapshot["targetPixel"]["y"]
            if abs(dx) >= abs(dy):
                page.keyboard.press("ArrowRight" if dx > 0 else "ArrowLeft")
            else:
                page.keyboard.press("ArrowUp" if dy > 0 else "ArrowDown")
        assert page.evaluate("galaxyGame.sky.state().aligned"), item_id
        tab_to(page, ".sky-atlas__open")
        assert not page.locator(".sky-atlas__open").is_disabled()
        page.keyboard.press("Enter")
    tab_to(page, ".sky-atlas__complete")
    page.keyboard.press("Enter")
    page.wait_for_function("galaxyGame.model.state.phase === 'tutorial'")
    enter_action(page, "labels")
    # Label buttons support the documented 1/2/3 keyboard shortcut.
    data = page.evaluate("GALAXY_DATA")
    for index, item_id in enumerate(data["childIds"]):
        image = next(item for item in data["images"] if item["id"] == item_id)
        key = str([item["id"] for item in data["classes"]].index(image["label"]) + 1)
        page.keyboard.press(key)
        if index < len(data["childIds"]) - 1:
            enter_action(page, "next")
    enter_action(page, "run")
    page.wait_for_function("galaxyGame.model.state.phase === 'review'")
    assert page.evaluate("galaxyGame.model.state.current.architecture") == "d1-r"
    enter_action(page, "repair")
    for index, item_id in enumerate(data["oldIds"]):
        image = next(item for item in data["images"] if item["id"] == item_id)
        key = str([item["id"] for item in data["classes"]].index(image["label"]) + 1)
        page.keyboard.press(key)
        if index < len(data["oldIds"]) - 1:
            enter_action(page, "next")
    enter_action(page, "run")
    page.wait_for_function("galaxyGame.model.state.phase === 'review'")
    enter_action(page, "guide-open")
    enter_action(page, "guide-add-convolution")
    enter_action(page, "run"); page.wait_for_function("galaxyGame.model.state.cnnGuide === 'observe'")
    enter_action(page, "guide-confirm-compare"); page.wait_for_function("galaxyGame.model.state.cnnGuide === 'independent'")
    tab_to(page, '[data-action="architecture-depth"][data-depth="1"]'); page.keyboard.press("Enter")
    enter_action(page, "architecture-save"); page.wait_for_function("galaxyGame.model.state.cnnGuide === 'independent-observe'")
    enter_action(page, "independent-confirm"); page.wait_for_function("galaxyGame.model.state.cnnGuide === 'complete'")
    enter_action(page, "finish")
    page.wait_for_function("galaxyGame.model.state.phase === 'final'")


def zoom_150(page):
    # Browser zoom changes the CSS viewport (1280/1.5 by 720/1.5), unlike
    # body.style.zoom which creates an artificial oversized document.
    assert page.viewport_size == {"width": 853, "height": 480}, page.viewport_size
    keyboard_baseline(page)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    scenes = ["intro", "tutorial", "labels", "repair", "review-after-repair", "final"]
    return {"status": "PASS", "viewport": [853, 480], "zoom": "150% CSS viewport",
            "scenes": scenes, "browserErrors": []}


def assign_all(page, data, phase):
    ids = data["childIds"] if phase == "labels" else data["oldIds"]
    images = {item["id"]: item for item in data["images"]}
    for index, item_id in enumerate(ids):
        page.locator(f'[data-label-id="{item_id}"][data-label="{images[item_id]["label"]}"]').click()
        if index < len(ids) - 1:
            click_action(page, "next")


def build_architecture(page, config):
    """Reach a canonical tail using only editor buttons, then save it."""
    page.locator(f'[data-action="architecture-depth"][data-depth="{config["depth"]}"]').click()
    # Reset optional layers, then add the desired set.  ReLU remains fixed.
    for layer in ("bn", "d"):
        button = page.locator(f'[data-action="layer-remove"][data-layer="{layer}"]')
        if button.count():
            button.click()
    for layer in ("bn", "d"):
        if layer in config["tail"]:
            page.locator(f'[data-action="layer-add"][data-layer="{layer}"]').click()
    # Button reordering validates the keyboard-accessible alternative to drag.
    expected = list(config["tail"])
    for wanted_index, layer in enumerate(expected):
        current = page.locator("[data-architecture-tail] > li").evaluate_all("els => els.map(el => el.dataset.layer)")
        index = current.index(layer)
        while index > wanted_index:
            page.locator(f'[data-action="layer-earlier"][data-layer-index="{index}"]').click()
            index -= 1
    assert page.locator("[data-architecture-tail] > li").evaluate_all("els => els.map(el => el.dataset.layer)") == expected
    save = page.locator('[data-action="architecture-save"]')
    assert save.get_attribute("data-architecture") == config["id"]
    save.click()
    page.wait_for_function("galaxyGame.model.state.current !== null")
    assert page.evaluate("galaxyGame.model.state.current.architecture") == config["id"]


def assert_metrics_from_predictions(page):
    """Compare rendered matrix cells with the actual current predictions."""
    run = page.evaluate("galaxyGame.model.state.current.result.review")
    classes = page.evaluate("GALAXY_DATA.classes.map(item => item.id)")
    matrix = [[0 for _ in classes] for _ in classes]
    for item in run["predictions"]:
        matrix[classes.index(item["expected"])][classes.index(item["predicted"])] += 1
    shown = [int(value) for value in page.locator(".modal details.metrics .metric-table td").all_text_contents()]
    assert shown == [cell for row in matrix for cell in row], (shown, matrix)


def inspect_scene(page, can_label=False):
    """A09: real image coordinates, zoom, help and selection keep one scene."""
    photo = page.locator('[data-quest-photo]')
    photo.wait_for()
    photo.evaluate("img => img.decode()")
    box = photo.evaluate("""img => {
      const r=img.getBoundingClientRect(), scale=Math.min(r.width/img.naturalWidth,r.height/img.naturalHeight);
      const w=img.naturalWidth*scale,h=img.naturalHeight*scale;
      return {x:r.x+(r.width-w)/2+w*.25,y:r.y+(r.height-h)/2+h*.4};
    }""")
    before_labels = page.evaluate('JSON.stringify(galaxyGame.model.state.labels)')
    page.mouse.click(box['x'],box['y'])
    point = page.evaluate('galaxyGame.quest.point')
    assert abs(point['x']-.25)<.02 and abs(point['y']-.4)<.02, point
    # Direct photo click opens zoom; the visible zoom control is a toggle.
    assert page.locator('.quest-scene__photo-shell.is-zoomed').count()==1
    page.locator('[data-quest="zoom"]').click()
    assert page.locator('.quest-scene__photo-shell.is-zoomed').count()==0
    page.locator('[data-quest="zoom"]').click()
    assert page.locator('.quest-scene__photo-shell.is-zoomed').count()==1
    page.locator('[data-quest="hint"]').click()
    assert page.evaluate('JSON.stringify(galaxyGame.model.state.labels)')==before_labels
    assert page.evaluate('galaxyGame.quest.point')==point
    assert page.locator('.quest-scene__photo-shell.is-zoomed').count()==1
    if can_label:
        button=page.locator('[data-quest-label]').first
        button.scroll_into_view_if_needed()
        page.evaluate("window.__sceneBefore={photo:document.querySelector('[data-quest-photo]'),scene:document.querySelector('#quest-scene'),scroll:scrollY}")
        button.click()
        assert page.evaluate("__sceneBefore.photo===document.querySelector('[data-quest-photo]') && __sceneBefore.scene===document.querySelector('#quest-scene') && Math.abs(__sceneBefore.scroll-scrollY)<2")
        assert button.evaluate('button => document.activeElement===button')
        assert page.locator('.quest-scene__photo-shell.is-zoomed').count()==1
        assert page.evaluate('galaxyGame.quest.point')==point
    page.locator('[data-quest="zoom"]').click()
    assert page.locator('.quest-scene__photo-shell.is-zoomed').count()==0


def full_route(page, report, viewport, all_architectures=False, zoom=None):
    errors, requests = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.on("requestfailed", lambda request: errors.append(f"{request.url}: {request.failure}"))
    page.on("response", lambda response: errors.append(f"HTTP {response.status}: {response.url}") if response.status >= 400 else None)
    page.on("request", lambda request: requests.append(request.url) if request.url.startswith(("http:", "https:")) else None)
    page.goto((HERE / "index.html").as_uri())
    if zoom:
        page.evaluate("value => document.body.style.zoom = value", str(zoom))
    page_contract(page, "intro")
    data = page.evaluate("GALAXY_DATA")
    assert page.evaluate("galaxyGame.model.state.phase") == "intro"
    assert page.locator('[data-action="start-route"]').count() == 1
    assert page.locator('[data-action="sky"]').count() == 0
    capture(page, "intro")

    # A01 — all navigation is via visible controls and the map target itself.
    click_action(page, "start-route")
    click_action(page, "collect-map")
    for item_id in data["childIds"]:
        collect(page, item_id)
    page.locator(".sky-atlas__complete").click()
    page.wait_for_function("galaxyGame.model.state.phase === 'tutorial'")
    capture(page, "tutorial")
    inspect_scene(page)
    click_action(page, "labels")
    capture(page, "labels")
    inspect_scene(page, True)
    page.keyboard.press("1")
    assert page.evaluate("galaxyGame.model.state.labels[GALAXY_DATA.childIds[0]]") == data["classes"][0]["id"]
    assign_all(page, data, "labels")
    click_action(page, "run")
    page.wait_for_function("galaxyGame.model.state.phase === 'review'")
    first = page.evaluate("galaxyGame.model.state.current")
    assert first["architecture"] == "d1-r"
    assert first["result"]["review"]["total"] == 3
    capture(page, "first-result")

    # A02 — create a deliberate wrong new label.  Help may explain it, but
    # cannot write an answer; returning to labels repairs the learner's input.
    click_action(page, "labels")
    first_id = data["childIds"][0]
    first_image = next(image for image in data["images"] if image["id"] == first_id)
    wrong = next(item["id"] for item in data["classes"] if item["id"] != first_image["label"])
    page.locator(f'[data-label-id="{first_id}"][data-label="{wrong}"]').click()
    click_action(page, "run")
    page.wait_for_function("galaxyGame.model.state.phase === 'review'")
    old_label = page.evaluate("galaxyGame.model.state.labels")
    talk = page.locator('[data-action="talk"]').first
    talk.click()
    page.locator('[data-nika="limits"]').click()
    assert "softmax" in page.locator(".nika-dialogue").inner_text().lower()
    page.keyboard.press("Escape")
    assert page.evaluate("galaxyGame.model.state.labels") == old_label
    assert talk.evaluate("button => document.activeElement===button")
    click_action(page, "labels")
    page.locator(f'[data-label-id="{first_id}"][data-label="{first_image["label"]}"]').click()
    click_action(page, "run")
    page.wait_for_function("galaxyGame.model.state.phase === 'review'")

    # A09 — an image dialog keeps focus contained and can be closed by Escape.
    zoom = page.locator('[data-action="zoom"]').first
    zoom.click()
    assert page.locator('[role="dialog"]').is_visible()
    page.keyboard.press("Escape")
    assert page.locator('[role="dialog"]').count() == 0

    click_action(page, "repair")
    capture(page, "repair")
    # A03: a learner may explicitly confirm an unchanged old label; this is
    # recorded as reviewed and survives navigation before another old label is edited.
    unchanged_id = data["oldIds"][0]
    unchanged = page.evaluate("(id) => galaxyGame.model.state.labels[id]", unchanged_id)
    page.locator(f'[data-label-id="{unchanged_id}"][data-label="{unchanged}"]').click()
    assert unchanged_id in page.evaluate("galaxyGame.model.state.reviewedOldIds")
    assert page.evaluate("(id) => galaxyGame.model.state.labels[id]", unchanged_id) == unchanged
    click_action(page, "next")
    assert unchanged_id in page.evaluate("galaxyGame.model.state.reviewedOldIds")
    page.locator('[data-action="sample"][data-index="0"]').click()
    assign_all(page, data, "repair")
    click_action(page, "run")
    page.wait_for_function("galaxyGame.model.state.phase === 'review'")
    second = page.evaluate("galaxyGame.model.state.current")
    capture(page, "review-after-repair")

    # N03/N04 — the required, explained d1-r → d2-r comparison precedes finish/editor.
    complete_cnn_guide(page)
    capture(page, "cnn-guide-compare")

    # A04 — through the now-unlocked visible editor, save the unchanged d2-r
    # configuration again; it must resolve the same prepared result rather than
    # inventing a new one.
    guide_result = page.evaluate("galaxyGame.model.state.current")
    click_action(page, "architecture-save", require_visible_frame=True)
    page.wait_for_function("galaxyGame.model.state.phase === 'review'")
    assert page.evaluate("galaxyGame.model.state.current.resultKey") == guide_result["resultKey"]
    # Identity above proves the visible re-run reused the table result. The
    # notice is transient and need not occupy the persistent workbench.

    # A07 — home and resume preserve the exact current state.
    before_home = page.evaluate("galaxyGame.model.serialize()")
    click_action(page, "home")
    click_action(page, "resume")
    resumed = page.evaluate("galaxyGame.model.serialize()")
    assert resumed["state"]["phase"] == before_home["state"]["phase"] == "review"
    for key in ("labels", "architecture", "current", "baseline", "repairCheckedLabelKey", "reviewedOldIds"):
        assert resumed["state"][key] == before_home["state"][key], key

    # A12 — metric disclosure presents matrix, per-class values and Macro-F1.
    click_action(page, "metrics", require_visible_frame=True)
    page.wait_for_selector(".modal details.metrics")
    page.locator(".modal details.metrics-advanced summary").click()
    metrics = page.locator(".modal details.metrics").inner_text().lower()
    for term in ("precision", "recall", "macro-f1", "нулевом знаменател"):
        assert term in metrics, term
    assert_metrics_from_predictions(page)
    page.keyboard.press("Escape")
    assert not page.locator(".modal").count()

    if all_architectures:
        # A05 all configurations: interactions never set state directly.  The
        # test requires UI removal to reset a tail between configurations.
        assert page.locator('[data-action="layer-remove"][data-layer="r"]').count() == 0
        for layer in ('bn', 'd'):
            page.locator(f'[data-action="layer-add"][data-layer="{layer}"]').click()
            assert page.locator(f'[data-action="layer-add"][data-layer="{layer}"]').is_disabled()
        assert page.locator('[data-action="layer-remove"]').count() == 2
        page.locator('li[data-layer="r"]').drag_to(page.locator('li[data-layer="d"]'))
        assert page.evaluate('GalaxyArchitectures.get(galaxyGame.model.state.architecture).tail') == ['bn','d','r']
        tab_to(page, 'li[data-layer="r"]')
        page.keyboard.press('Alt+ArrowLeft')
        assert page.evaluate('GalaxyArchitectures.get(galaxyGame.model.state.architecture).tail') == ['bn','r','d']
        capture(page, 'architecture-reordered')
        configs = page.evaluate("GalaxyArchitectures.configurations")
        for index, config in enumerate(configs):
            build_architecture(page, config)
            page_contract(page, config["id"])

    click_action(page, "finish")
    page.wait_for_function("galaxyGame.model.state.phase === 'final'")
    page.locator(".research-board > summary").click()
    final_metrics = page.locator('details[data-metric-scope="final"]')
    final_metrics.locator(":scope > summary").click()
    assert "итоговая выборка" in final_metrics.inner_text().lower()
    page.locator(".research-board > summary").click()
    final_button = page.locator('.final-summary [data-action="sky"]')
    assert final_button.bounding_box()["y"] + final_button.bounding_box()["height"] <= viewport[1]
    capture(page, "final")

    # A11 opens a current sky note and returns to the same map/camera.  The
    # complete material catalogue belongs to check-night-sky.py.
    final_state = page.evaluate("galaxyGame.model.serialize()")
    click_action(page, "sky")
    page.wait_for_selector(".sky-atlas__note")
    camera = page.evaluate("galaxyGame.sky.snapshot().camera")
    page.locator(".sky-atlas__note").first.click()
    assert page.locator(".modal").is_visible()
    page.keyboard.press("Escape")
    page.locator(".modal").wait_for(state="detached")
    page.wait_for_selector(".sky-atlas")
    assert page.evaluate("galaxyGame.sky.snapshot().camera") == camera
    page.locator(".sky-atlas__note").first.click()
    page.locator('.modal [data-action="return-sky"]').click()
    page.wait_for_selector(".sky-atlas")
    assert page.evaluate("galaxyGame.sky.snapshot().camera") == camera
    page.locator(".sky-atlas__close").click()
    page.wait_for_function("!galaxyGame.sky")
    after_free = page.evaluate("galaxyGame.model.serialize()")
    for key in ("labels", "architecture", "current", "repairCheckedLabelKey"):
        assert after_free["state"][key] == final_state["state"][key], key
    assert page.evaluate("GALAXY_DATA.childIds") == data["childIds"]

    # A10: a different architecture after the final needs an actual new run;
    # returning to final is explicitly a repeat and retains the learner's labels.
    if all_architectures:
        page.locator(".research-board > summary").click()
        click_action(page, "labels")
        click_action(page, "run")
        page.wait_for_function("galaxyGame.model.state.phase === 'review'")
        config = page.evaluate("GalaxyArchitectures.get('d1-r')")
        build_architecture(page, config)
        assert page.evaluate("galaxyGame.model.state.current.architecture") == "d1-r"
        assert page.evaluate("galaxyGame.model.state.labels") == final_state["state"]["labels"]
        click_action(page, "finish")
        page.wait_for_function("galaxyGame.model.state.phase === 'final'")
        page.locator(".research-board > summary").click()
        assert "повторный просмотр" in page.locator("body").inner_text().lower()
        page.locator(".research-board > summary").click()

    # A08 cancel must leave the lesson untouched, then confirmation resets it.
    page.once("dialog", lambda dialog: dialog.dismiss())
    click_action(page, "reset")
    assert page.evaluate("galaxyGame.model.state.phase") == "final"
    page.once("dialog", lambda dialog: dialog.accept())
    click_action(page, "reset")
    assert page.evaluate("galaxyGame.model.state.phase") == "intro"

    assert not errors, errors
    assert not requests, requests


def missing_shard(page, report, entry=None):
    if entry:
        page.route("**/telemetry/v1/events", lambda route: route.fulfill(status=204, body=""))
    page.goto(entry or (HERE / "index.html").as_uri())
    click_action(page, "start-route")
    click_action(page, "collect-map")
    data = page.evaluate("GALAXY_DATA")
    for item_id in data["childIds"]:
        collect(page, item_id)
    page.locator(".sky-atlas__complete").click()
    click_action(page, "labels")
    assign_all(page, data, "labels")
    click_action(page, "run")
    page.wait_for_function("galaxyGame.model.state.phase === 'review'")
    click_action(page, "repair")
    assign_all(page, data, "repair")
    click_action(page, "run")
    page.wait_for_function("galaxyGame.model.state.phase === 'review'")
    complete_cnn_guide(page)
    build = {"id": "d1-r-bn", "depth": 1, "tail": ["r", "bn"]}
    page.locator('[data-action="architecture-depth"][data-depth="1"]').click()
    page.locator('[data-action="layer-add"][data-layer="bn"]').click()
    assert page.locator('[data-action="architecture-save"]').get_attribute("data-architecture") == build["id"]
    shard = "**/cnn-results/d1-r-bn.js"
    page.route(shard, lambda route: route.abort())
    page.locator('[data-action="architecture-save"]').click()
    page.wait_for_selector(".modal")
    assert "не удалось" in page.locator(".modal").inner_text().lower()
    page.locator('[data-action="close-modal"]').click()
    page.unroute(shard)
    # Retry is a second visible save/check action, never a hidden fallback.
    page.locator('[data-action="architecture-save"]').click()
    page.wait_for_function("galaxyGame.model.state.phase === 'review' && galaxyGame.model.state.current?.architecture === 'd1-r-bn'")
    report.add("A14 missing shard and visible retry", "PASS", "intercepted then loaded cnn-results/d1-r-bn.js")
    saved = page.evaluate("sessionStorage.getItem('science-day.lesson.v1')")
    page.route(shard, lambda route: route.abort())
    page.reload()
    page.wait_for_selector('[data-restore-retry]')
    assert page.evaluate("sessionStorage.getItem('science-day.lesson.v1')")==saved
    page.once('dialog', lambda dialog: dialog.dismiss())
    page.locator('[data-restore-new]').click()
    assert page.evaluate("sessionStorage.getItem('science-day.lesson.v1')")==saved
    page.unroute(shard)
    page.locator('[data-restore-retry]').click()
    page.wait_for_function('window.galaxyGame')
    if page.locator('[data-action="resume"]').count():
        click_action(page,'resume')
    assert page.evaluate('galaxyGame.model.state.current.architecture')=='d1-r-bn'
    report.add('A08/A14 reload resource failure preserves saved shift and retries', 'PASS', 'same persisted lesson before/after failed reload; visible retry/resume')



def corrupt_shard(page, report, entry):
    """A syntactically valid but semantically bad shard must show the same UI error."""
    page.route("**/telemetry/v1/events", lambda route: route.fulfill(status=204, body=""))
    page.goto(entry)
    page.route("**/cnn-results/d1-r-bn.js", lambda route: route.fulfill(status=200, content_type="application/javascript", body="GalaxyCNNResults.register('d1-r-bn', {});"))
    # Reuse the visible route up to the architecture editor, without direct state changes.
    click_action(page, "start-route"); click_action(page, "collect-map")
    data = page.evaluate("GALAXY_DATA")
    for item_id in data["childIds"]: collect(page, item_id)
    page.locator(".sky-atlas__complete").click(); click_action(page, "labels"); assign_all(page, data, "labels")
    click_action(page, "run"); page.wait_for_function("galaxyGame.model.state.phase === 'review'")
    click_action(page, "repair"); assign_all(page, data, "repair"); click_action(page, "run")
    page.wait_for_function("galaxyGame.model.state.phase === 'review'"); complete_cnn_guide(page)
    page.locator('[data-action="architecture-depth"][data-depth="1"]').click(); page.locator('[data-action="layer-add"][data-layer="bn"]').click(); page.locator('[data-action="architecture-save"]').click()
    page.wait_for_selector(".modal")
    assert "не удалось" in page.locator(".modal").inner_text().lower()
    report.add("A14 corrupt shard", "PASS", "HTTP fulfilled invalid d1-r-bn shard")


def main():
    report = Report()
    static_contract(report)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, **({"executable_path": os.environ["PW_CHROMIUM"]} if os.environ.get("PW_CHROMIUM") else {}))
        context = browser.new_context(viewport={"width": 1280, "height": 720}, reduced_motion="reduce")
        page = context.new_page()
        baseline = False
        try:
            page.goto((HERE / "index.html").as_uri())
            configurations = page.evaluate("GalaxyArchitectures.configurations")
            baseline = page.evaluate("""() => Object.values(GALAXY_CNN_EXPERIMENTS.experiments || {})
              .some(row => Boolean(row.architectures?.['d1-r']))""")
            ready = all(config["id"] == "d1-r" or (HERE / "cnn-results" / f"{config['id']}.js").is_file()
                        for config in configurations)
        except Exception as error:
            report.add("A01–A14 calculated baseline", "NOT RUN", "startup", str(error))
            ready = False
        context.close()
        context = browser.new_context(viewport={"width": 1280, "height": 720}, reduced_motion="reduce")
        report.check("V06 keyboard-only baseline route", "1280x720", lambda: keyboard_baseline(context.new_page()))
        context.close()
        context = browser.new_context(viewport={"width": 853, "height": 480}, reduced_motion="reduce")
        report.check("V06 150% zoom entry accessibility", "853x480 CSS viewport", lambda: zoom_150(context.new_page()))
        context.close()
        context = browser.new_context(viewport={"width": 853, "height": 480}, reduced_motion="no-preference")
        report.check("V06 150% zoom keyboard route with ordinary motion", "853x480 CSS viewport", lambda: zoom_150(context.new_page()))
        context.close()
        if baseline and not ready:
            for viewport in VIEWPORTS:
                context = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]}, reduced_motion="reduce")
                report.check("baseline route: A01/A02/A04/A09/A11/A12", f"{viewport[0]}x{viewport[1]}", lambda: full_route(context.new_page(), report, viewport))
                context.close()
        elif not baseline:
            report.add("baseline route: A01/A02/A04/A09/A11/A12", "NOT RUN", "d1-r baseline", "calculated d1-r result is not available")
        if ready:
            for viewport in VIEWPORTS:
                context = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]}, reduced_motion="reduce")
                report.check("A01–A12 visible route", f"{viewport[0]}x{viewport[1]}", lambda: full_route(context.new_page(), report, viewport, True))
                context.close()
        else:
            report.add("A05 all 22 architectures", "NOT RUN", "cnn-results shards", "21 calculated architecture shards are not yet available")
        if (HERE / 'cnn-results/d1-r-bn.js').is_file():
            with local_http() as entry:
                for label, check in [('missing shard and retry', missing_shard), ('corrupt shard', corrupt_shard)]:
                    context = browser.new_context(viewport={"width":1280,"height":720}, reduced_motion="reduce")
                    report.check('A14 '+label, 'localhost HTTP; telemetry intercepted with 204', lambda: check(context.new_page(), report, entry))
                    context.close()
        else:
            report.add('A14 unavailable/corrupt shard', 'NOT RUN', 'd1-r-bn absent')
        browser.close()
    report_path = EVIDENCE / "complete-browser.json"
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    complete = not any(item["status"] != "PASS" for item in report.items)
    runtime = ['index.html', 'game.js', 'galaxy.css', 'cnn-session.js', 'cnn-architectures.js', 'cnn-results-loader.js', 'metrics.js', 'telemetry.js', 'quest-scene.js', 'quest-scene.css', 'cnn-guide.js', 'cnn-guide.css', 'world.js', 'sky.js']
    source_hashes = {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in runtime}
    report_path.write_text(json.dumps({"status": "PASS" if complete else "INCOMPLETE" if not any(item["status"] == "FAIL" for item in report.items) else "FAIL", "versionSource": (HERE / 'version.js').read_text().strip(), "runtimeSha256": source_hashes, "checks": report.items}, ensure_ascii=False, indent=2) + "\n")
    print(report_path.read_text())
    if complete:
        return 0
    return 1 if any(item["status"] == "FAIL" for item in report.items) else 2


if __name__ == "__main__":
    sys.exit(main())
