#!/usr/bin/env python3
"""Independent scientific audit of the frozen CNN label-correction pilot.

This neither writes the pilot nor selects a score.  It checks the stored result
against a fresh deterministic run, the data boundaries, actual convolution
updates, and a counterfactual wrong-child label path needed by a future UI.
"""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PILOT = HERE / "cnn-label-correction"


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, PILOT / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load("cnn_label_correction_pilot", "run_pilot.py")


def without_timing(value):
    if isinstance(value, dict):
        return {key: without_timing(item) for key, item in value.items()
                if not (key.endswith("Seconds") or key.endswith("WallSeconds"))}
    if isinstance(value, list):
        return [without_timing(item) for item in value]
    return value


def arrays(records, split):
    items = {item["id"]: item for item in records["images"]}
    ids = split["trainingIds"] + split["reviewIds"] + split["historicallyKnownHoldoutIds"]
    images = {item_id: runner.cnn.load_image(Path(items[item_id]["src"]).name) for item_id in ids}
    return items, {
        "training_ids": split["trainingIds"], "review_ids": split["reviewIds"],
        "final_ids": split["historicallyKnownHoldoutIds"],
        "train_x": np.asarray([images[item_id] for item_id in split["trainingIds"]])[:, None, :, :],
        "review_x": np.asarray([images[item_id] for item_id in split["reviewIds"]])[:, None, :, :],
        "final_x": np.asarray([images[item_id] for item_id in split["historicallyKnownHoldoutIds"]])[:, None, :, :],
    }


def main():
    target = PILOT / "pilot-results.json"
    assert target.is_file(), "Run cnn-label-correction/run_pilot.py before auditing."
    stored = json.loads(target.read_text(encoding="utf-8"))
    fresh = runner.build()
    assert without_timing(stored) == without_timing(fresh), "stored scientific result differs from a fresh deterministic run"

    records, _ = runner.prepare.build()
    split = stored["split"]
    train, review, final = (set(split[key]) for key in ("trainingIds", "reviewIds", "historicallyKnownHoldoutIds"))
    assert len(train) == 9 and len(review) == len(final) == 3
    assert not (train & review or train & final or review & final), "train/review/final objects must not overlap"
    items, values = arrays(records, split)
    class_ids = [item["id"] for item in records["classes"]]
    canonical = {item_id: items[item_id]["label"] for item_id in split["trainingIds"]}
    conditions = runner.PROTOCOL["labelConditions"]
    expected_corrupt = {**canonical, **conditions["corrupt_old"]}
    expected_corrected = {**canonical, **conditions["corrected_old"]}
    assert expected_corrected == canonical

    cases = {case["id"]: case for case in stored["cases"]}
    assert set(cases) == {"one_block_corrupt_old", "one_block_corrected_old",
                          "one_block_corrected_repeat", "two_block_corrected_old"}
    assert cases["one_block_corrupt_old"]["trainingLabels"] == expected_corrupt
    assert cases["one_block_corrected_old"]["trainingLabels"] == expected_corrected
    assert cases["one_block_corrected_repeat"]["trainingLabels"] == expected_corrected
    assert cases["two_block_corrected_old"]["trainingLabels"] == expected_corrected
    assert cases["one_block_corrected_old"]["blocks"] == cases["one_block_corrected_repeat"]["blocks"] == 1
    assert cases["two_block_corrected_old"]["blocks"] == 2
    assert cases["two_block_corrected_old"]["parameterCount"] > cases["one_block_corrected_old"]["parameterCount"]
    repeat_a = {key: value for key, value in cases["one_block_corrected_old"].items() if key != "id"}
    repeat_b = {key: value for key, value in cases["one_block_corrected_repeat"].items() if key != "id"}
    assert without_timing(repeat_a) == without_timing(repeat_b)

    for case in cases.values():
        assert case["loss"]["last"] < case["loss"]["first"]
        for key, expected_ids in (("review", split["reviewIds"]),
                                  ("historicallyKnownHoldout", split["historicallyKnownHoldoutIds"])):
            result = case[key]
            assert [row["id"] for row in result["predictions"]] == expected_ids
            assert result["correct"] == sum(row["predicted"] == row["expected"] for row in result["predictions"])
            for row in result["predictions"]:
                assert row["id"] not in train
                assert abs(sum(row["probabilities"].values()) - 1.0) < 2e-8

    one_initial_model = runner.cnn.TinyCNN(1, np.random.default_rng(runner.cnn.SEED))
    one_initial = {name: value.copy() for name, value in one_initial_model.params.items()}
    two_initial = runner.fresh_model(2, one_initial)
    for name, value in one_initial.items():
        assert np.array_equal(two_initial.params[name], value), f"shared initialization drifted for {name}"
    targets = np.asarray([class_ids.index(canonical[item_id]) for item_id in split["trainingIds"]])
    trained = runner.fresh_model(1, one_initial)
    before = {name: value.copy() for name, value in trained.params.items()}
    runner.cnn.train(trained, values["train_x"], targets)
    for name in ("w0", "head_w"):
        assert not np.array_equal(before[name], trained.params[name]), f"{name} must actually update"
    trained_two = runner.fresh_model(2, one_initial)
    before_two = {name: value.copy() for name, value in trained_two.params.items()}
    runner.cnn.train(trained_two, values["train_x"], targets)
    for name in ("w0", "w1", "head_w"):
        assert not np.array_equal(before_two[name], trained_two.params[name]), f"{name} must actually update"
    assert np.isfinite(np.concatenate([value.ravel() for value in trained.params.values()])).all()

    # The runner accepts labels for every train item; a future child-correction
    # branch therefore need not be bolted onto an old-label-only code path.
    wrong_child = copy.deepcopy(canonical)
    child = next(item_id for item_id in split["trainingIds"] if item_id.startswith("child_"))
    wrong_child[child] = next(label for label in class_ids if label != canonical[child])
    counterfactual = runner.run_case("audit_wrong_child", 1, wrong_child, values, items, class_ids, one_initial)
    assert counterfactual["trainingLabels"][child] == wrong_child[child]
    assert counterfactual["loss"]["last"] < counterfactual["loss"]["first"]

    print(json.dumps({"status": "PASS", "checks": [
        "deterministic stored result", "disjoint split", "label conditions", "trained convolution",
        "architecture initialization control", "wrong-child counterfactual support",
        "known-holdout wording boundary"], "review": {
            key: cases[key]["review"]["correct"] for key in cases}, "knownHoldout": {
            key: cases[key]["historicallyKnownHoldout"]["correct"] for key in cases}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
