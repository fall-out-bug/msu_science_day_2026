#!/usr/bin/env python3
"""N06 browser contract: every scientific and archive record opens by visible click."""
import contextlib
import http.server
import socketserver
import threading
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent

@contextlib.contextmanager
def local_http():
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs): super().__init__(*args, directory=str(HERE), **kwargs)
        def log_message(self, *_): pass
    class Server(socketserver.TCPServer): allow_reuse_address = True
    server = Server(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try: yield f"http://127.0.0.1:{server.server_address[1]}/index.html"
    finally: server.shutdown(); server.server_close(); thread.join()

def main():
    with local_http() as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        errors=[]; page.on("pageerror", lambda error: errors.append(str(error)))
        page.set_default_timeout(3000)
        page.goto(url); page.wait_for_function("window.GalaxySky && window.GALAXY_DISCOVERIES && window.GALAXY_ARCHIVE")
        expected = page.evaluate("""() => ({
          discoveries: GALAXY_DISCOVERIES.map(item => item.id),
          archives: GALAXY_ARCHIVE.images.map(item => item.id),
          coordinateDiscoveries: GALAXY_DISCOVERIES.filter(item => Number.isFinite(item.ra) && Number.isFinite(item.dec)).map(item => item.id),
          coordinateArchives: GALAXY_ARCHIVE.images.filter(item => Number.isFinite(item.ra) && Number.isFinite(item.dec)).map(item => item.id)
        })""")
        assert len(expected["discoveries"]) == 19, expected
        assert len(expected["archives"]) == 24, expected
        assert len(expected["discoveries"]) - len(expected["coordinateDiscoveries"]) == 9, expected
        page.evaluate("""() => {
          window.__nightOpened=[];
          GalaxySky.open({onArchive:id => __nightOpened.push(`archive:${id}`), onDiscovery:id => __nightOpened.push(`discovery:${id}`)});
        }""")
        page.wait_for_selector(".sky-atlas")
        assert page.locator("[data-filter], [data-research-id]").count() == 0
        notes=page.locator("[data-note-id]")
        assert notes.count() == 9
        for index in range(notes.count()): notes.nth(index).click()
        # The world-wide default view exposes each coordinate group as a visible
        # marker. A group opens its visible list before a record is selected.
        groups=page.locator(".sky-atlas__marker")
        assert groups.count() > 0
        def open_visible_groups():
            groups=page.locator(".sky-atlas__marker")
            for index in range(groups.count()):
                group=groups.nth(index); group.click()
                choice=page.locator(".sky-atlas__choice")
                if choice.count():
                    for button in choice.locator("[data-choice]").all(): button.click()
                    choice.locator(".sky-atlas__choice-close").click()
            return groups.count()
        marker_groups=open_visible_groups()
        # SN 2023tyk lies near the north edge, so move the actual focused canvas
        # with keyboard arrows and click the newly visible marker rather than
        # assigning it a fictitious screen position.
        page.locator(".sky-atlas__canvas").click(position={"x": 640, "y": 360})
        for _ in range(12): page.keyboard.press("ArrowUp")
        page.wait_for_timeout(150)
        north=page.locator('.sky-atlas__marker[data-material-ids*="btsbot-supernova"]')
        assert north.count() == 1
        north.click()
        marker_groups += 1
        opened=set(page.evaluate("window.__nightOpened"))
        required={*(f"discovery:{item}" for item in expected["discoveries"]), *(f"archive:{item}" for item in expected["archives"])}
        missing=sorted(required-opened)
        assert not missing, f"not opened by visible click: {missing}"
        assert not errors, errors
        print({"status":"PASS", "discoveries":19, "archives":24, "notes":9, "markerGroups":marker_groups})
        browser.close()

if __name__ == "__main__": main()
