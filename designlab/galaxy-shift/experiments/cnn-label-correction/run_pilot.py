#!/usr/bin/env python3
"""Run the frozen CNN label-correction pilot declared in protocol.json.

This is an experiment artifact.  It imports the existing admitted-data loader and
TinyCNN implementation but writes only pilot-results.json in this directory.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
GAME = HERE.parent.parent
PROTOCOL = json.loads((HERE / "protocol.json").read_text(encoding="utf-8"))


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, GAME / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cnn = load_module("galaxy_cnn_prepare", "cnn-prepare.py")
prepare = cnn.prepare


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def probabilities(model, values: np.ndarray) -> np.ndarray:
    logits, _ = model.forward(values)
    shifted = logits - logits.max(axis=1, keepdims=True)
    exp = np.exp(shifted)
    return exp / exp.sum(axis=1, keepdims=True)


def prediction_set(model, values, ids, items, class_ids):
    probs = probabilities(model, values)
    rows = []
    for item_id, row in zip(ids, probs):
        index = int(row.argmax())
        rows.append({
            "id": item_id,
            "predicted": class_ids[index],
            "expected": items[item_id]["label"],
            "confidence": round(float(row[index]), 8),
            "probabilities": {class_id: round(float(value), 8) for class_id, value in zip(class_ids, row)},
        })
    return {"predictions": rows, "correct": sum(p["predicted"] == p["expected"] for p in rows), "total": len(rows)}


def fresh_model(blocks: int, one_initial: dict[str, np.ndarray]):
    model = cnn.TinyCNN(blocks, np.random.default_rng(cnn.SEED))
    for name in ("w0", "b0", "head_w", "head_b"):
        model.params[name][...] = one_initial[name]
    return model


def run_case(case_id, blocks, labels, arrays, items, class_ids, one_initial):
    targets = np.asarray([class_ids.index(labels[item_id]) for item_id in arrays["training_ids"]])
    model = fresh_model(blocks, one_initial)
    started = time.perf_counter()
    losses = cnn.train(model, arrays["train_x"], targets)
    wall_seconds = time.perf_counter() - started
    return {
        "id": case_id,
        "blocks": blocks,
        "parameterCount": model.parameter_count,
        "trainingLabels": {item_id: labels[item_id] for item_id in arrays["training_ids"]},
        "loss": {"first": round(losses[0], 8), "last": round(losses[-1], 8)},
        "trainingWallSeconds": round(wall_seconds, 6),
        "review": prediction_set(model, arrays["review_x"], arrays["review_ids"], items, class_ids),
        "historicallyKnownHoldout": prediction_set(model, arrays["final_x"], arrays["final_ids"], items, class_ids),
    }


def build():
    records, _ = prepare.build()  # verifies admission hashes before image loading
    items = {item["id"]: item for item in records["images"]}
    protocol = records["protocol"]
    training_ids, review_ids, final_ids = protocol["trainingIds"], protocol["reviewIds"], protocol["finalIds"]
    class_ids = [item["id"] for item in records["classes"]]
    all_ids = training_ids + review_ids + final_ids
    images = {item_id: cnn.load_image(Path(items[item_id]["src"]).name) for item_id in all_ids}
    arrays = {
        "training_ids": training_ids, "review_ids": review_ids, "final_ids": final_ids,
        "train_x": np.asarray([images[item_id] for item_id in training_ids])[:, None, :, :],
        "review_x": np.asarray([images[item_id] for item_id in review_ids])[:, None, :, :],
        "final_x": np.asarray([images[item_id] for item_id in final_ids])[:, None, :, :],
    }
    canonical = {item_id: items[item_id]["label"] for item_id in training_ids}
    corrupt = dict(canonical)
    corrupt.update(PROTOCOL["labelConditions"]["corrupt_old"])
    corrected = dict(canonical)
    corrected.update(PROTOCOL["labelConditions"]["corrected_old"])
    assert corrected == canonical
    one_initial_model = cnn.TinyCNN(1, np.random.default_rng(cnn.SEED))
    one_initial = {name: value.copy() for name, value in one_initial_model.params.items()}
    cases = [
        run_case("one_block_corrupt_old", 1, corrupt, arrays, items, class_ids, one_initial),
        run_case("one_block_corrected_old", 1, corrected, arrays, items, class_ids, one_initial),
        run_case("one_block_corrected_repeat", 1, corrected, arrays, items, class_ids, one_initial),
        run_case("two_block_corrected_old", 2, corrected, arrays, items, class_ids, one_initial),
    ]
    comparable = lambda row: {key: value for key, value in row.items() if key not in {"id", "trainingWallSeconds"}}
    if comparable(cases[1]) != comparable(cases[2]):
        raise RuntimeError("fixed one-block repeat is not identical")
    base_seconds = cases[1]["trainingWallSeconds"]
    two_seconds = cases[3]["trainingWallSeconds"]
    return {
        "schemaVersion": 1,
        "protocolFile": "protocol.json",
        "source": {
            "datasetVersion": records["datasetVersion"],
            "prepareDataSha256": digest(GAME / "prepare-data.py"),
            "cnnPrepareSha256": digest(GAME / "cnn-prepare.py"),
            "admission": "prepare.build() and cnn.load_image() verified every source image hash used here",
        },
        "split": {"trainingIds": training_ids, "reviewIds": review_ids, "historicallyKnownHoldoutIds": final_ids},
        "cases": cases,
        "costEstimate": {
            "observedOneBlockTrainingWallSeconds": base_seconds,
            "observedTwoBlockTrainingWallSeconds": two_seconds,
            "estimated243StatesTimesTwoArchitecturesWallSeconds": round(243 * (base_seconds + two_seconds), 3),
            "verdict": "A separately reviewed finite 243-state × two-architecture table is now the accepted desktop artifact. Its generator validates source hashes and exact targeted replays; this pilot remains the small before/after explanation."
        },
        "limitations": [
            "Nine training objects and three objects per evaluation split are too small for a capability claim.",
            "Review is a known teaching check, not an independent model-selection score.",
            "The final split was historically inspected before this pilot; it is reported as a historically known holdout, not a new independent test.",
            "One fixed seed demonstrates reproducibility, not uncertainty across initializations."
        ]
    }


def main():
    result = build()
    target = HERE / "pilot-results.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(target), "cases": [(c["id"], c["review"]["correct"], c["historicallyKnownHoldout"]["correct"], c["trainingWallSeconds"]) for c in result["cases"]], "cost": result["costEstimate"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
