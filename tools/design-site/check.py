#!/usr/bin/env python3
"""Check the built publication's checksums and local HTML/CSS dependencies."""
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import unquote, urljoin, urlsplit


class References(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if value and key in {"href", "src", "poster", "data-screen-image"}:
                self.links.append(value)
            if key == "style" and value:
                self.links.extend(css_links(value))


def css_links(value):
    return re.findall(r"url\(\s*['\"]?([^)'\"\s]+)", value)


def check(site):
    site = site.resolve()
    manifest = json.loads((site / "manifest.json").read_text())
    failures = []
    checked = 0
    for name, expected in manifest["files"].items():
        path = site / name
        if not path.resolve().is_relative_to(site) or path.is_symlink() or not path.is_file():
            failures.append(f"Unsafe or missing manifest resource: {name}")
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            failures.append(f"Checksum mismatch: {name}")
        links = []
        if path.suffix == ".html":
            parser = References()
            parser.feed(path.read_text())
            links = parser.links
        elif path.suffix == ".css":
            links = css_links(path.read_text())
        for value in links:
            if value.startswith("#") or urlsplit(value).scheme or value.startswith("//"):
                continue
            resolved = urlsplit(urljoin("https://site.invalid/design/" + name, value)).path
            # Existing game and historical /docs/ routes are preserved separately.
            if not resolved.startswith("/design/"):
                continue
            target = site / unquote(resolved.removeprefix("/design/"))
            if target.is_dir():
                target = target / "index.html"
            checked += 1
            if not target.resolve().is_relative_to(site) or not target.is_file():
                failures.append(f"Missing link: {name} -> {value}")
    pages = manifest["pages"]
    paths = [p["path"] for p in pages]
    if len(set(paths)) != len(paths):
        failures.append("Duplicate catalogue paths")
    for path in paths:
        if path not in manifest["files"]:
            failures.append(f"Catalogue page is not in the manifest: {path}")
    if failures:
        raise ValueError("\n".join(sorted(set(failures))))
    return {"pages": len(pages), "files": len(manifest["files"]), "localReferences": checked}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(check(args.site)))
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, str(error) + "\n")
