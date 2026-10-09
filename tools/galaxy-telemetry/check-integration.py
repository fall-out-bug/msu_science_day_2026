#!/usr/bin/env python3
"""Visible browser-to-receipt integration check for Galaxy telemetry.

It starts a private telemetry server and a deliberately local-only static proxy.
The proxy removes the browser's local Origin before forwarding: production's
backend allowlist remains unchanged and is tested separately by test_server.py.
"""
import contextlib
import http.client
import importlib.util
import json
import os
import sqlite3
import tempfile
import threading
import time
import traceback
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent / "designlab" / "galaxy-shift"
EVIDENCE = Path(os.environ.get("GALAXY_RECOMPOSE_TELEMETRY_EVIDENCE", HERE.parent.parent / "docs" / "design-2026-10-09" / "evidence" / "recompose-telemetry-integration.json"))
SPEC = importlib.util.spec_from_file_location("galaxy_telemetry_server", HERE / "server.py")
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)


class LocalProxy(SimpleHTTPRequestHandler):
    """Static package server plus the one local test-only telemetry bridge."""
    backend_port = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, *_):
        pass

    def do_POST(self):
        if self.path != "/telemetry/v1/events":
            self.send_error(404)
            return
        size = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(size)
        # Do not widen the production server allowlist for a local browser test.
        conn = http.client.HTTPConnection("127.0.0.1", self.backend_port, timeout=8)
        conn.request("POST", self.path, payload, {
            "Content-Type": self.headers.get("Content-Type", "application/json"),
            "Content-Length": str(len(payload)),
        })
        reply = conn.getresponse()
        body = reply.read()
        self.send_response(reply.status)
        self.send_header("Content-Type", reply.getheader("Content-Type", "application/json"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
        conn.close()


@contextlib.contextmanager
def running(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=8)


def click(page, action):
    page.locator(f'[data-action="{action}"]').first.click()


def collect(page, image_id, settle_ms=700):
    page.locator(f'.sky-atlas [data-target="{image_id}"]').click()
    page.wait_for_timeout(settle_ms)
    target = page.evaluate("galaxyGame.sky.snapshot().targetPixel")
    page.mouse.click(target["x"], target["y"])
    page.wait_for_function("galaxyGame.sky.state().aligned")
    page.locator(".sky-atlas__open").click()


def label_all(page, ids, images):
    for index, image_id in enumerate(ids):
        page.locator(f'[data-label-id="{image_id}"][data-label="{images[image_id]["label"]}"]').click()
        if index + 1 < len(ids):
            click(page, "next")


def journey(page):
    """Perform the published route through visible controls only."""
    click(page, "start-route")
    click(page, "collect-map")
    data = page.evaluate("GALAXY_DATA")
    images = {image["id"]: image for image in data["images"]}
    for image_id in data["childIds"]:
        collect(page, image_id)
    page.locator(".sky-atlas__complete").click()
    page.wait_for_function("galaxyGame.model.state.phase === 'tutorial'")
    click(page, "labels")
    label_all(page, data["childIds"], images)
    click(page, "run")
    page.wait_for_function("galaxyGame.model.state.phase === 'review'")
    click(page, "repair")
    label_all(page, data["oldIds"], images)
    click(page, "run")
    page.wait_for_function("galaxyGame.model.state.phase === 'review'")
    page.wait_for_selector(".cnn-workbench .architecture-editor")
    page.wait_for_function("galaxyGame.model.state.cnnGuide === 'bridge'")
    click(page, "guide-open")
    page.wait_for_function("galaxyGame.model.state.cnnGuide === 'intro'")
    click(page, "guide-add-convolution")
    click(page, "run")
    page.wait_for_function("galaxyGame.model.state.cnnGuide === 'observe'")
    click(page, "guide-confirm-compare")
    page.wait_for_function("galaxyGame.model.state.cnnGuide === 'independent'")
    page.locator('[data-action="architecture-depth"][data-depth="1"]').click()
    click(page, "architecture-save")
    page.wait_for_function("galaxyGame.model.state.cnnGuide === 'independent-observe'")
    click(page, "independent-confirm")
    page.wait_for_function("galaxyGame.model.state.cnnGuide === 'complete'")
    click(page, "finish")
    page.wait_for_function("galaxyGame.model.state.phase === 'final'")
    return data


def assert_click_during_map_animation(page):
    """A click while camera focus is still animating must not disable collection."""
    click(page, "start-route")
    click(page, "collect-map")
    image_id = page.evaluate("GALAXY_DATA.childIds[0]")
    page.locator(f'.sky-atlas [data-target="{image_id}"]').click()
    page.wait_for_timeout(350)
    target = page.evaluate("galaxyGame.sky.snapshot().targetPixel")
    page.mouse.click(target["x"], target["y"])
    page.wait_for_timeout(800)
    assert page.evaluate("galaxyGame.sky.state().aligned")
    assert page.locator(".sky-atlas__open").is_enabled()


def database_events(path, session_id=None):
    with sqlite3.connect(path) as db:
        rows = db.execute("SELECT body FROM events ORDER BY received, session_id, seq").fetchall()
    events = [json.loads(row[0]) for row in rows]
    return [event for event in events if session_id is None or event["sessionId"] == session_id]


def wait_for_events(path, session_id, minimum):
    end = time.monotonic() + 8
    while time.monotonic() < end:
        events = database_events(path, session_id)
        if len(events) >= minimum:
            return events
        time.sleep(.05)
    return database_events(path, session_id)


def verify_sequence(events, data):
    """Check the action trace, event identity, sequence and event-specific data."""
    assert events and events[0]["type"] == "session_started"
    assert [event["seq"] for event in events] == list(range(1, len(events) + 1))
    assert len({event["eventId"] for event in events}) == len(events)
    assert {event["sessionId"] for event in events} == {events[0]["sessionId"]}
    assert all(event["channel"] == "web" for event in events)
    types = [event["type"] for event in events]
    assert types.count("map_target_collected") == 4
    assert [event["detail"]["imageId"] for event in events if event["type"] == "map_target_collected"] == data["childIds"]
    labels = [event for event in events if event["type"] == "label_set"]
    assert len(labels) == 7
    assert [event["detail"]["imageId"] for event in labels] == data["childIds"] + data["oldIds"]
    assert all(event["detail"]["after"] == next(image["label"] for image in data["images"] if image["id"] == event["detail"]["imageId"]) for event in labels)
    assert types.count("run_opened") == 4 and types.count("result_opened") == 5, types
    guide_architecture = [event["detail"] for event in events if event["type"] == "architecture_selected"]
    assert guide_architecture == [{"architecture": "d2-r"}, {"architecture": "d1-r"}]
    assert types.count("final_opened") == 1 and types[-3:] == ["phase_entered", "final_opened", "result_opened"], types
    assert events[-3]["detail"] == {"phase": "final"}
    assert [event["detail"]["scope"] for event in events if event["type"] == "run_opened"] == ["review", "review", "review", "review"]
    assert [event["detail"]["scope"] for event in events if event["type"] == "result_opened"] == ["review", "review", "review", "review", "final"]
    assert {event["detail"]["architecture"] for event in events if event["type"] == "run_opened"} == {"d1-r", "d2-r"}


def browser_errors(page, errors, failed):
    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
    page.on("requestfailed", lambda request: failed.append({"url": request.url, "failure": request.failure}))


def open_game(page, url):
    # Phaser keeps timers alive, so networkidle is not a meaningful readiness test.
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_function("window.galaxyGame && window.GalaxyTelemetry")


def main():
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    result = {"status": "FAIL", "checks": [], "failures": []}
    with tempfile.TemporaryDirectory(prefix="galaxy-telemetry-e2e-") as temp:
        db_path = str(Path(temp) / "events.sqlite3")
        old_db, SERVER.DB = SERVER.DB, db_path
        os.environ["TELEMETRY_DB"] = db_path
        backend = SERVER.create_server("127.0.0.1", 0)
        LocalProxy.backend_port = backend.server_port
        proxy = ThreadingHTTPServer(("127.0.0.1", 0), LocalProxy)
        origin = f"http://127.0.0.1:{proxy.server_port}"
        try:
            with running(backend), running(proxy), sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    context = browser.new_context(viewport={"width": 1280, "height": 720}, reduced_motion="reduce", accept_downloads=True)
                    page = context.new_page()
                    errors, failed = [], []
                    browser_errors(page, errors, failed)
                    open_game(page, origin + "/index.html")
                    data = journey(page)
                    session_id = page.evaluate("GalaxyTelemetry.sessionId")
                    events = wait_for_events(db_path, session_id, 32)
                    verify_sequence(events, data)
                    assert not errors, errors
                    assert not failed, failed
                    result["checks"].append("visible full route: collect4, labels4, repair3, guided and independent CNN runs, final")
                    result["checks"].append("SQLite event sequence, image IDs, run keys, architecture, review/final results")

                    page.reload(wait_until="domcontentloaded")
                    page.wait_for_function("window.galaxyGame && window.GalaxyTelemetry")
                    assert page.evaluate("GalaxyTelemetry.sessionId") == session_id
                    click(page, "resume")
                    page.wait_for_function("galaxyGame.model.state.phase === 'final'")
                    result["checks"].append("reload retains lesson state and telemetry session ID")

                    second = context.new_page()
                    open_game(second, origin + "/index.html")
                    assert second.evaluate("GalaxyTelemetry.sessionId") != session_id
                    second.close()
                    result["checks"].append("independent second tab has a new telemetry session")

                    page.once("dialog", lambda dialog: dialog.accept())
                    click(page, "reset")
                    page.wait_for_function("galaxyGame.model.state.phase === 'intro'")
                    assert page.evaluate("GalaxyTelemetry.sessionId") != session_id
                    result["checks"].append("new shift rotates telemetry session ID")

                    # ZIP must never issue HTTP; download's JSON is the exported journal.
                    zip_context = browser.new_context(viewport={"width": 1280, "height": 720}, accept_downloads=True)
                    zip_page = zip_context.new_page()
                    zip_requests = []
                    zip_page.on("request", lambda request: zip_requests.append(request.url))
                    open_game(zip_page, (ROOT / "index.html").as_uri())
                    click(zip_page, "about")
                    with zip_page.expect_download() as download_info:
                        click(zip_page, "diagnostics")
                        click(zip_page, "export-journal")
                    download = download_info.value
                    download_path = Path(temp) / "journal.json"
                    download.save_as(str(download_path))
                    exported = json.loads(download_path.read_text())
                    assert exported["schema"] == 1 and exported["sessions"]
                    assert not [url for url in zip_requests if url.startswith(("http:", "https:"))]
                    zip_context.close()
                    result["checks"].append("file ZIP export is valid JSON and makes no HTTP request")

                    animation_context = browser.new_context(viewport={"width": 1280, "height": 720})
                    animation = animation_context.new_page()
                    animation_errors, animation_failed = [], []
                    browser_errors(animation, animation_errors, animation_failed)
                    open_game(animation, origin + "/index.html")
                    assert_click_during_map_animation(animation)
                    assert not animation_errors, animation_errors
                    assert not animation_failed, animation_failed
                    animation_context.close()
                    result["checks"].append("map collection remains aligned after a 350ms click during normal-motion camera focus")

                    # Storage refusal and network loss are non-fatal full player routes.
                    memory_context = browser.new_context(viewport={"width": 1280, "height": 720})
                    memory_context.add_init_script("""
                      const get = Storage.prototype.getItem, set = Storage.prototype.setItem;
                      Storage.prototype.getItem = function(k) { if (this === sessionStorage) throw Error('blocked'); return get.call(this,k); };
                      Storage.prototype.setItem = function(k,v) { if (this === sessionStorage) throw Error('blocked'); return set.call(this,k,v); };
                    """)
                    memory = memory_context.new_page()
                    memory_errors, memory_failed = [], []
                    browser_errors(memory, memory_errors, memory_failed)
                    memory.route("**/telemetry/v1/events", lambda route: route.abort())
                    open_game(memory, origin + "/index.html")
                    if memory.locator(".modal").count():
                        click(memory, "close-modal")
                    try:
                        journey(memory)
                    except Exception:
                        result["memoryPageErrors"] = memory_errors
                        result["memoryRequestFailures"] = memory_failed
                        result["memoryMapState"] = memory.evaluate("galaxyGame.sky?.state()")
                        raise
                    click(memory, "about")
                    click(memory, "diagnostics")
                    diagnostic = memory.locator(".modal").inner_text().lower()
                    assert "только до перезагрузки" in diagnostic
                    assert memory.evaluate("galaxyGame.model.state.phase") == "final"
                    memory_context.close()
                    result["checks"].append("blocked sessionStorage plus telemetry network failure still completes route and shows diagnostic")
                    context.close()
                finally:
                    browser.close()
            result["status"] = "PASS"
            result["environment"] = {"origin": origin, "backend": "private localhost", "proxyOriginHandling": "local test proxy strips Origin before forwarding; backend production allowlist unchanged"}
            result["events"] = {"count": len(events), "sessionId": session_id, "types": [event["type"] for event in events]}
        except Exception as error:
            result["failures"].append(traceback.format_exc())
            raise
        finally:
            SERVER.DB = old_db
            EVIDENCE.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
