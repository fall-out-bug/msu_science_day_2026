#!/usr/bin/env python3
"""Build the offline Galaxy Shift archive manifest.

The catalog has 24 interchangeable training images: eight per classroom visual
class.  It deliberately reuses prepare_data.feature so the archive and the
original exercise use the same fixed 14-number image representation.  Network
access is never used here; bytes are admitted beforehand and locked in
archive-admission.json.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "archive-catalog.json"
ADMISSION = ROOT / "archive-admission.json"
OUTPUT = ROOT / "archive-data.js"
ORIGINAL_DATA = ROOT / "data.js"


def read_data_js(path: Path) -> dict:
    prefix = "globalThis.GALAXY_DATA = "
    text = path.read_text(encoding="utf-8")
    start = text.find(prefix)
    if start < 0 or not text.rstrip().endswith(";"):
        raise ValueError(f"unexpected generated data file: {path}")
    return json.loads(text[start + len(prefix):].strip().removesuffix(";"))


def load_feature_function():
    spec = importlib.util.spec_from_file_location("galaxy_prepare_data", ROOT / "prepare-data.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load prepare-data.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.feature


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_coordinate_degrees(ra: str, dec: str) -> tuple[float, float]:
    ra_parts = [float(value) for value in ra.split()]
    dec_sign = -1 if dec.startswith("-") else 1
    dec_parts = [float(value) for value in dec.lstrip("-").replace("°", " ").replace("'", " ").replace('"', " ").split()]
    if len(ra_parts) != 3 or len(dec_parts) != 3:
        raise ValueError(f"unreadable source coordinate: {ra!r}, {dec!r}")
    return (15 * (ra_parts[0] + ra_parts[1] / 60 + ra_parts[2] / 3600),
            dec_sign * (dec_parts[0] + dec_parts[1] / 60 + dec_parts[2] / 3600))


def build() -> dict:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    admission = json.loads(ADMISSION.read_text(encoding="utf-8"))
    images = catalog["images"]
    if len(images) != 24:
        raise ValueError(f"archive must contain 24 images, got {len(images)}")
    ids = [image["id"] for image in images]
    if len(set(ids)) != len(ids):
        raise ValueError("archive image ids must be unique")
    labels = {"smooth", "spiral", "edge_on"}
    if {image["label"] for image in images} != labels:
        raise ValueError("archive labels must be smooth, spiral, edge_on")
    for label in labels:
        if sum(image["label"] == label for image in images) != 8:
            raise ValueError(f"archive must have eight {label} images")
    for image in images:
        required = {"id", "name", "src", "label", "role", "explanation", "credit", "source", "ra", "dec", "sourceCaption"}
        if set(image) != required or image["role"] != "archive/train":
            raise ValueError(f"invalid archive schema for {image.get('id')}")
        if not image["source"].startswith("https://esahubble.org/images/"):
            raise ValueError(f"not an ESA/Hubble primary page: {image['id']}")
        if not np.isfinite([image["ra"], image["dec"]]).all() or not 0 <= image["ra"] < 360 or not -90 <= image["dec"] <= 90:
            raise ValueError(f"invalid coordinates: {image['id']}")
        source_position = admission["sourcePositions"].get(image["id"])
        if not source_position or source_position["source"] != image["source"]:
            raise ValueError(f"missing primary source coordinates: {image['id']}")
        source_ra, source_dec = source_coordinate_degrees(source_position["ra"], source_position["dec"])
        if not np.allclose((image["ra"], image["dec"]), (source_ra, source_dec), rtol=0, atol=1e-7):
            raise ValueError(f"catalog coordinates differ from ESA position: {image['id']}")
    if set(admission["sourcePositions"]) != set(ids):
        raise ValueError("source position set differs from catalog")

    locked = admission["files"]
    catalog_paths = {image["src"] for image in images}
    if catalog_paths != set(locked):
        raise ValueError("catalog and admission path sets differ")
    for relative, expected in locked.items():
        path = ROOT / relative
        if not path.is_file() or sha256(path) != expected:
            raise ValueError(f"admission hash mismatch: {relative}")

    archive_files = {str(path.relative_to(ROOT)) for path in (ROOT / "assets" / "galaxies" / "archive").glob("*.jpg")}
    admitted_new = {path for path in locked if path.startswith("assets/galaxies/archive/")}
    if archive_files != admitted_new:
        raise ValueError(f"archive JPEG set differs from admission: extra={sorted(archive_files - admitted_new)}, missing={sorted(admitted_new - archive_files)}")

    original = read_data_js(ORIGINAL_DATA)
    originals = original["images"]
    if len(originals) != 15:
        raise ValueError("expected 15 original images")
    if set(ids) & {image["id"] for image in originals} != {"child_m85", "child_ic5332", "child_ngc5023"}:
        raise ValueError("archive may overlap original data only at the three child images")

    feature = load_feature_function()
    feature_inputs = {image["id"]: image["src"] for image in originals}
    feature_inputs.update({image["id"]: image["src"] for image in images if image["id"] not in feature_inputs})
    features = {}
    for image_id, relative in sorted(feature_inputs.items()):
        vector = np.asarray(feature(ROOT / relative), dtype=np.float64)
        if vector.shape != (14,) or not np.isfinite(vector).all():
            raise ValueError(f"invalid 14-dimensional feature for {image_id}")
        features[image_id] = [float(value) for value in vector]
    if len(features) != 36:
        raise ValueError(f"expected 36 features (15 original + 21 new), got {len(features)}")
    return {"datasetVersion": catalog["datasetVersion"], "images": images, "features": features}


def encoded(data: dict) -> str:
    return "// Generated by prepare-archive.py; do not edit by hand.\n" + "globalThis.GALAXY_ARCHIVE = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify admissions and compare archive-data.js without writing")
    args = parser.parse_args()
    text = encoded(build())
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != text:
            raise SystemExit("generated file differs: archive-data.js")
        print("check passed: 24 archive images (8 per class), 36 finite 14-dimensional features, admission hashes verified")
        return
    OUTPUT.write_text(text, encoding="utf-8")
    print("wrote archive-data.js: 24 archive images, 36 features")


if __name__ == "__main__":
    main()
