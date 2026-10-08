#!/usr/bin/env python3
"""Train-only comparison of automatic image features for the 1-NN lesson.

Run without arguments to select the representation from training leave-one-out.
Only the explicit ``--evaluate`` phase reads the review/final split scores.
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("galaxy_prepare", ROOT / "prepare-data.py")
assert spec and spec.loader
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


def unit(values: np.ndarray | list[float]) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64).ravel()
    return values / (np.linalg.norm(values) + 1e-9)


def image(path: Path, crop: float = .75) -> np.ndarray:
    with Image.open(path) as source:
        source = source.convert("L")
        width, height = source.size
        side = int(min(width, height) * crop)
        source = source.crop(((width - side) // 2, (height - side) // 2,
                              (width + side) // 2, (height + side) // 2))
        source = source.resize((64, 64), Image.Resampling.LANCZOS)
    values = np.asarray(source, dtype=np.float64) / 255.0
    return (values - values.mean()) / (values.std() + 1e-9)


def brightness_moments(values: np.ndarray) -> np.ndarray:
    """Centroid, principal axes and radial/light quantiles from image pixels."""
    y, x = np.indices(values.shape)
    weights = np.maximum(values - np.quantile(values, .2), 0) + 1e-8
    center_x, center_y = (weights * x).sum() / weights.sum(), (weights * y).sum() / weights.sum()
    dx, dy = x - center_x, y - center_y
    covariance = np.array([[(weights * dx * dx).sum(), (weights * dx * dy).sum()],
                           [(weights * dx * dy).sum(), (weights * dy * dy).sum()]]) / weights.sum()
    radius = np.hypot(dx, dy)
    return unit([center_x / values.shape[1], center_y / values.shape[0],
                 *np.linalg.eigvalsh(covariance),
                 *np.quantile(radius, (.1, .25, .5, .75, .9)),
                 *np.quantile(weights, (.1, .25, .5, .75, .9))])


def hog(values: np.ndarray) -> np.ndarray:
    gradient_y, gradient_x = np.gradient(values)
    magnitude = np.hypot(gradient_y, gradient_x)
    angle = (np.arctan2(gradient_y, gradient_x) + np.pi) % np.pi
    result = []
    step = 64 // 4
    for row in range(4):
        for column in range(4):
            section = (slice(row * step, (row + 1) * step), slice(column * step, (column + 1) * step))
            result.extend(np.histogram(angle[section], bins=9, range=(0, np.pi), weights=magnitude[section])[0])
    return unit(result)


def candidates() -> dict[str, tuple[float, callable]]:
    return {
        "pixels-45": (.45, lambda values: unit(values)),
        "brightness-moments-75": (.75, brightness_moments),
        "hog-75": (.75, hog),
    }


def representation(records: dict, name: str, ids: list[str]) -> dict[str, np.ndarray]:
    crop, feature = candidates()[name]
    objects = {record["id"]: record for record in records["images"]}
    return {item_id: feature(image(ROOT / objects[item_id]["src"], crop)) for item_id in ids}


def predict(features: dict[str, np.ndarray], training_ids: list[str], labels: dict[str, str], ids: list[str], leave_one_out: bool = False) -> list[dict]:
    rows = []
    for item_id in ids:
        pool = [candidate for candidate in training_ids if not leave_one_out or candidate != item_id]
        nearest = min(pool, key=lambda candidate: (float(np.linalg.norm(features[item_id] - features[candidate])), candidate))
        rows.append({"id": item_id, "neighborId": nearest, "predicted": labels[nearest], "expected": labels[item_id]})
    return rows


def score(rows: list[dict]) -> int:
    return sum(row["predicted"] == row["expected"] for row in rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluate", action="store_true", help="after selecting, report the known review/final demonstrations")
    args = parser.parse_args()
    records, _ = prepare.build()
    labels = {record["id"]: record["label"] for record in records["images"]}
    train = records["protocol"]["trainingIds"]
    results = {}
    for name in candidates():
        features = representation(records, name, train)
        results[name] = score(predict(features, train, labels, train, leave_one_out=True))
    # Tie rule fixed here: select the compact interpretable moments over HOG.
    chosen = "brightness-moments-75"
    assert results[chosen] == max(results.values())
    print({"phase": "train-only", "leaveOneOut": results, "chosen": chosen, "tieRule": "compact automatic moments before HOG"})
    if args.evaluate:
        all_ids = [record["id"] for record in records["images"]]
        features = representation(records, chosen, all_ids)
        for split in ("review", "final"):
            ids = [record["id"] for record in records["images"] if record["split"] == split]
            rows = predict(features, train, labels, ids)
            print({"phase": "known demonstration", "split": split, "correct": score(rows), "total": len(rows), "predictions": rows})


if __name__ == "__main__":
    main()
