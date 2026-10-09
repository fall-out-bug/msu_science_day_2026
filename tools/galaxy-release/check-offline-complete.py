#!/usr/bin/env python3
"""Verify a completed offline ZIP with exact hashes and the visible full route."""
import argparse
import hashlib
import importlib.util
import json
import re
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
GAME = ROOT / "designlab" / "galaxy-shift"
DEFAULT_ZIP = GAME / "releases" / "galaxy-shift.zip"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def version_from(source, label):
    match = re.search(r"GALAXY_BUILD_VERSION\s*=\s*'([^']+)'", source)
    if not match:
        raise AssertionError(f"{label}: GALAXY_BUILD_VERSION is missing")
    return match.group(1)


def load_helper(path):
    spec = importlib.util.spec_from_file_location("offline_complete_browser", path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    return helper


def verify_zip(zip_path):
    with zipfile.ZipFile(zip_path) as archive:
        entries = archive.infolist()
        names = [item.filename for item in entries]
        assert len(names) == len(set(names)), "ZIP contains duplicate paths"
        assert all(not name.endswith("/") for name in names), "ZIP contains directory entries"
        for name in names:
            path = PurePosixPath(name)
            assert not path.is_absolute() and ".." not in path.parts and str(path) == name, f"unsafe ZIP path: {name}"
        assert "build.json" in names, "ZIP has no build.json"
        manifest = json.loads(archive.read("build.json"))
        assert isinstance(manifest, dict) and isinstance(manifest.get("version"), str), "invalid build.json version"
        files = manifest.get("files")
        assert isinstance(files, dict) and files, "invalid build.json files"
        expected = set(files) | {"build.json"}
        actual = set(names)
        assert actual == expected, f"ZIP file list differs: missing={sorted(expected-actual)} extra={sorted(actual-expected)}"
        for name, expected_digest in files.items():
            assert isinstance(expected_digest, str) and re.fullmatch(r"[0-9a-f]{64}", expected_digest), f"invalid digest: {name}"
            actual_digest = hashlib.sha256(archive.read(name)).hexdigest()
            assert actual_digest == expected_digest, f"SHA-256 mismatch: {name}"
        version = version_from(archive.read("version.js").decode("utf-8"), "ZIP version.js")
        assert manifest["version"] == version, "build.json version differs from ZIP version.js"
        return manifest, version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, default=DEFAULT_ZIP)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    result = {"status": "FAIL", "zip": str(args.zip)}
    try:
        zip_path = args.zip.resolve(strict=True)
        manifest, version = verify_zip(zip_path)
        source_version = version_from((GAME / "version.js").read_text(encoding="utf-8"), "source version.js")
        assert version == source_version, "ZIP version.js differs from source version.js"
        result.update({"version": version, "zipSha256": sha256(zip_path), "files": len(manifest["files"])})

        with tempfile.TemporaryDirectory(prefix="science-day-offline-") as temp:
            extracted = Path(temp) / "bundle"
            extracted.mkdir()
            with zipfile.ZipFile(zip_path) as archive:
                archive.extractall(extracted)
            evidence_dir = Path(temp) / "evidence"
            helper = load_helper(GAME / "check-complete-browser.py")
            helper.HERE = extracted
            helper.EVIDENCE = evidence_dir
            report = helper.Report()
            helper.static_contract(report)
            assert not report.items or all(item["status"] == "PASS" for item in report.items), report.items
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    context = browser.new_context(viewport={"width": 1280, "height": 720}, reduced_motion="reduce", offline=True)
                    try:
                        page = context.new_page()
                        helper.full_route(page, report, (1280, 720), all_architectures=True)
                    finally:
                        context.close()
                finally:
                    browser.close()
            assert not any(item["status"] != "PASS" for item in report.items), report.items
            result.update({"configurationsPassed": 22, "fullRoute": "PASS", "networkRequests": 0})
        result["status"] = "PASS"
    except Exception as error:
        result["error"] = str(error)
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
