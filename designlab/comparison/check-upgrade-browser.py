#!/usr/bin/env python3
"""Open the current game with a real HTTP cache left by the previous prototype."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
import json
import os
from playwright.sync_api import sync_playwright
from browser_support import launch_chromium

HERE = Path(__file__).resolve().parent
OUT = Path(os.environ.get('NIGHT_EVIDENCE_DIR', str(HERE / 'evidence')))
OUT.mkdir(parents=True, exist_ok=True)


class Handler(SimpleHTTPRequestHandler):
    legacy = True
    old_requests = 0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HERE), **kwargs)

    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path == '/legacy':
            body = b'<!doctype html><script src="data.js"></script>'
            content_type = 'text/html'
        elif self.path == '/data.js' and Handler.legacy:
            # The old site's data.js defines GAME_DATA, not COMPARISON_DATA.
            # Keep the same public API; the large old observation array is irrelevant.
            body = b'window.GAME_DATA = {cases: []};'
            content_type = 'application/javascript'
            Handler.old_requests += 1
        else:
            return super().do_GET()
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'max-age=3600')
        self.end_headers()
        self.wfile.write(body)


server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
Thread(target=server.serve_forever, daemon=True).start()
origin = f'http://127.0.0.1:{server.server_port}'
errors = []
try:
    with sync_playwright() as pw:
        browser = launch_chromium(pw)
        page = browser.new_page()
        page.goto(origin + '/legacy')
        assert page.evaluate('typeof GAME_DATA === "object"')
        Handler.legacy = False
        # Verify the browser really reuses the cached response after deployment.
        page.goto(origin + '/legacy')
        assert Handler.old_requests == 1
        assert page.evaluate('typeof GAME_DATA === "object" && typeof COMPARISON_DATA === "undefined"')
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto(origin + '/night.html', timeout=30000)
        ready = page.evaluate('typeof COMPARISON_DATA === "object" && typeof NightModel === "object" && !document.querySelector("#g-start").disabled')
        report = {'legacy_cache_primed': True, 'errors': errors, 'ready': ready}
        (OUT / 'upgrade-browser.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report))
        assert ready and not errors, 'Upgrade must initialize COMPARISON_DATA and NightModel without errors'
        page.locator('#g-start').click()
        assert page.locator('#g-room').is_visible()
        browser.close()
finally:
    server.shutdown()
    server.server_close()
