#!/usr/bin/env python3
"""Generate and verify the exhaustive offline CNN experiment table.

The game uses the generated JS as an exact lookup table.  It never trains in a
browser, silently substitutes a state, or receives review/final labels during
training.  ``--check`` validates source admission, both generated outputs, the
whole table's shape and five targeted independent replays rather than spending
another full 4374 trainings.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import os
import multiprocessing
import time
from pathlib import Path

# This table is many independent, tiny NumPy calculations. One BLAS thread per
# worker avoids oversubscribing the host and does not change the deterministic
# arithmetic of a run.
for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[variable] = "1"

import numpy as np

HERE = Path(__file__).resolve().parent
GAME = HERE.parent.parent
RUNTIME = GAME / "cnn-experiments.js"
JSON_TARGET = HERE / "cnn-experiments.json"
PROTOCOL = json.loads((HERE / "protocol.json").read_text(encoding="utf-8"))
WORKER_CONTEXT = None


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, GAME / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pilot = load_module("cnn_label_correction_pilot", "experiments/cnn-label-correction/run_pilot.py")
cnn, prepare = pilot.cnn, pilot.prepare


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def weights_hash(model) -> str:
    payload = hashlib.sha256()
    for name in sorted(model.params):
        value = np.ascontiguousarray(model.params[name])
        payload.update(name.encode("ascii") + b"\0")
        payload.update(str(value.dtype).encode("ascii") + b"\0")
        payload.update(np.asarray(value.shape, dtype=np.int64).tobytes())
        payload.update(value.tobytes())
    return payload.hexdigest()


def experiment_context():
    frozen = PROTOCOL["frozenTraining"]
    if frozen["seed"] != cnn.SEED or frozen["epochs"] != cnn.EPOCHS or float(frozen["learningRate"]) != cnn.LEARNING_RATE:
        raise RuntimeError("protocol frozenTraining differs from the imported TinyCNN constants")
    records, _ = prepare.build()  # verifies source admission hashes
    items = {item["id"]: item for item in records["images"]}
    data_protocol = records["protocol"]
    training_ids = data_protocol["trainingIds"]
    review_ids = data_protocol["reviewIds"]
    final_ids = data_protocol["finalIds"]
    class_ids = [item["id"] for item in records["classes"]]
    all_ids = training_ids + review_ids + final_ids
    images = {item_id: cnn.load_image(Path(items[item_id]["src"]).name) for item_id in all_ids}
    one = cnn.TinyCNN(1, np.random.default_rng(cnn.SEED))
    return {
        "records": records, "items": items, "training_ids": training_ids,
        "review_ids": review_ids, "final_ids": final_ids, "class_ids": class_ids,
        "editable_ids": records["editableIds"], "canonical": {item_id: items[item_id]["label"] for item_id in training_ids},
        "arrays": {
            "train_x": np.asarray([images[item_id] for item_id in training_ids])[:, None, :, :],
            "review_x": np.asarray([images[item_id] for item_id in review_ids])[:, None, :, :],
            "final_x": np.asarray([images[item_id] for item_id in final_ids])[:, None, :, :],
        },
        "one_initial": {name: value.copy() for name, value in one.params.items()},
    }


def labels_for_key(context, key: str):
    editable = context["editable_ids"]
    classes = context["class_ids"]
    if len(key) != len(editable) or any(symbol not in "012" for symbol in key):
        raise ValueError(f"invalid editable-label key: {key}")
    labels = dict(context["canonical"])
    labels.update({item_id: classes[int(symbol)] for item_id, symbol in zip(editable, key)})
    return labels


def train_architecture(context, key: str, blocks: int):
    labels = labels_for_key(context, key)
    model = pilot.fresh_model(blocks, context["one_initial"])
    targets = np.asarray([context["class_ids"].index(labels[item_id]) for item_id in context["training_ids"]])
    started = time.perf_counter()
    losses = cnn.train(model, context["arrays"]["train_x"], targets)
    elapsed = time.perf_counter() - started
    return {
        "key": key,
        "blocks": blocks,
        "review": pilot.prediction_set(model, context["arrays"]["review_x"], context["review_ids"], context["items"], context["class_ids"]),
        "final": pilot.prediction_set(model, context["arrays"]["final_x"], context["final_ids"], context["items"], context["class_ids"]),
        "loss": {"first": round(losses[0], 8), "last": round(losses[-1], 8)},
        "weightsHash": weights_hash(model),
        "trainLabels": {item_id: labels[item_id] for item_id in context["training_ids"]},
        "_trainingWallSeconds": elapsed,
    }


def clean(row):
    return {key: value for key, value in row.items() if key != "_trainingWallSeconds"}


def evaluate_key(context, key: str):
    """Public exact replay API for the independent audit; trains only two models."""
    return {str(blocks): clean(train_architecture(context, key, blocks)) for blocks in (1, 2)}


def state_keys(context):
    return ["".join(map(str, digits)) for digits in np.ndindex(*(3 for _ in context["editable_ids"]))]


def replay_keys(context):
    """Five deterministic representative states, whatever the editable count."""
    canonical = "".join(str(context["class_ids"].index(context["canonical"][item_id])) for item_id in context["editable_ids"])
    initial = dict(context["canonical"])
    initial.update(context["records"]["initialOldLabels"])
    initial_key = "".join(str(context["class_ids"].index(initial[item_id])) for item_id in context["editable_ids"])
    wrong_first_child = list(canonical)
    wrong_first_child[0] = str((int(wrong_first_child[0]) + 1) % len(context["class_ids"]))
    candidates = [canonical, initial_key, "".join(wrong_first_child), "0" * len(canonical), "2" * len(canonical)]
    return tuple(dict.fromkeys(candidates))


def metadata(context, total_training_wall_seconds: float | None = None):
    records = context["records"]
    initial = dict(context["canonical"])
    initial.update(records["initialOldLabels"])
    document = {
        "schemaVersion": 1,
        "protocol": {
            "datasetVersion": records["datasetVersion"],
            "editableIds": context["editable_ids"],
            "classes": context["class_ids"],
            "trainingIds": context["training_ids"],
            "reviewIds": context["review_ids"],
            "finalIds": context["final_ids"],
            "initialLabels": initial,
            "preprocess": PROTOCOL["frozenTraining"]["image"],
            "optimizer": PROTOCOL["frozenTraining"]["optimizer"],
            "learningRate": PROTOCOL["frozenTraining"]["learningRate"],
            "seed": PROTOCOL["frozenTraining"]["seed"],
            "epochs": PROTOCOL["frozenTraining"]["epochs"],
            "architectureInitialization": PROTOCOL["initialization"],
            "historicallyKnownFinal": True,
            "noFallback": True,
        },
        "source": {
            "protocolSha256": sha256(HERE / "protocol.json"),
            "prepareDataSha256": sha256(GAME / "prepare-data.py"),
            "cnnPrepareSha256": sha256(GAME / "cnn-prepare.py"),
            "pilotSha256": sha256(HERE / "run_pilot.py"),
            "generatorSha256": sha256(Path(__file__)),
            "admission": "prepare.build() and cnn.load_image() verify every JPEG source hash before training",
        },
    }
    if total_training_wall_seconds is not None:
        document["generation"] = {
            "architecturesPerState": 2,
            "states": 3 ** len(context["editable_ids"]),
            "trainings": 2 * 3 ** len(context["editable_ids"]),
            "sumTrainingWallSeconds": round(total_training_wall_seconds, 6),
            "meanTrainingWallSeconds": round(total_training_wall_seconds / (2 * 3 ** len(context["editable_ids"])), 6),
        }
    return document


def render_js(data):
    return "// Generated by experiments/cnn-label-correction/generate_cnn_experiments.py; do not edit by hand.\n" + "globalThis.GALAXY_CNN_EXPERIMENTS = " + json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + ";\n"


def train_state(key):
    context = WORKER_CONTEXT
    architectures, elapsed = {}, 0.0
    for blocks in (1, 2):
        row = train_architecture(context, key, blocks)
        elapsed += row["_trainingWallSeconds"]
        architectures[str(blocks)] = clean(row)
    labels = labels_for_key(context, key)
    return key, {"key": key, "trainLabels": {item_id: labels[item_id] for item_id in context["training_ids"]}, "architectures": architectures}, elapsed


def set_worker_context(context):
    global WORKER_CONTEXT
    WORKER_CONTEXT = context


def build_full(workers):
    context = experiment_context()
    keys = state_keys(context)
    experiments, elapsed = {}, 0.0
    if workers == 1:
        set_worker_context(context)
        rows = map(train_state, keys)
    else:
        process_context = multiprocessing.get_context("fork")
        executor = concurrent.futures.ProcessPoolExecutor(
            max_workers=workers,
            mp_context=process_context,
            initializer=set_worker_context,
            initargs=(context,),
        )
        rows = executor.map(train_state, keys)
    try:
        for key, entry, seconds in rows:
            experiments[key] = entry
            elapsed += seconds
    finally:
        if workers != 1:
            executor.shutdown(wait=True, cancel_futures=True)
    output = metadata(context, elapsed)
    output["experiments"] = experiments
    return output


def load_runtime():
    text = RUNTIME.read_text(encoding="utf-8")
    prefix = "globalThis.GALAXY_CNN_EXPERIMENTS = "
    if prefix not in text or not text.rstrip().endswith(";"):
        raise RuntimeError("malformed cnn-experiments.js")
    return json.loads(text.split(prefix, 1)[1].strip()[:-1])


def validate_table(data):
    context = experiment_context()
    expected = {"".join(map(str, digits)) for digits in np.ndindex(*(3 for _ in context["editable_ids"]))}
    if set(data.get("experiments", {})) != expected:
        raise RuntimeError("table does not contain exactly all editable-label keys")
    protocol = data.get("protocol", {})
    for name, expected_value in (("editableIds", context["editable_ids"]), ("classes", context["class_ids"]), ("trainingIds", context["training_ids"]), ("reviewIds", context["review_ids"]), ("finalIds", context["final_ids"])):
        if protocol.get(name) != expected_value:
            raise RuntimeError(f"protocol mismatch: {name}")
    for key, entry in data["experiments"].items():
        labels = labels_for_key(context, key)
        if entry.get("key") != key or entry.get("trainLabels") != {item_id: labels[item_id] for item_id in context["training_ids"]}:
            raise RuntimeError(f"label mapping mismatch: {key}")
        if set(entry.get("architectures", {})) != {"1", "2"}:
            raise RuntimeError(f"architecture mapping mismatch: {key}")
        for blocks in (1, 2):
            row = entry["architectures"][str(blocks)]
            if row.get("key") != key or row.get("blocks") != blocks or row.get("trainLabels") != entry["trainLabels"]:
                raise RuntimeError(f"row metadata mismatch: {key}/{blocks}")
            for split, ids in (("review", context["review_ids"]), ("final", context["final_ids"])):
                result = row.get(split, {})
                if [p.get("id") for p in result.get("predictions", [])] != ids or result.get("correct") != sum(p.get("predicted") == p.get("expected") for p in result.get("predictions", [])) or result.get("total") != len(ids):
                    raise RuntimeError(f"prediction mismatch: {key}/{blocks}/{split}")
            if not isinstance(row.get("weightsHash"), str) or len(row["weightsHash"]) != 64:
                raise RuntimeError(f"weight hash missing: {key}/{blocks}")
    return context


def check():
    disk = json.loads(JSON_TARGET.read_text(encoding="utf-8"))
    runtime = load_runtime()
    if disk != runtime:
        raise RuntimeError("scientific JSON and runtime JS differ")
    context = validate_table(disk)
    if disk.get("source") != metadata(context)["source"]:
        raise RuntimeError("generated metadata does not match current source dependencies")
    for key in replay_keys(context):
        if evaluate_key(context, key) != disk["experiments"][key]["architectures"]:
            raise RuntimeError(f"targeted replay does not match table: {key}")
    print(json.dumps({"status": "PASS", "states": len(state_keys(context)), "architectures": 2, "targetedReplays": list(replay_keys(context)), "admission": "verified", "runtimeEqualsScientificJson": True}, ensure_ascii=False))


def refresh_metadata():
    """Refresh declared provenance only after validating all scientific rows."""
    disk = json.loads(JSON_TARGET.read_text(encoding="utf-8"))
    runtime = load_runtime()
    if disk != runtime:
        raise RuntimeError("scientific JSON and runtime JS differ")
    context = validate_table(disk)
    for key in replay_keys(context):
        if evaluate_key(context, key) != disk["experiments"][key]["architectures"]:
            raise RuntimeError(f"targeted replay does not match table: {key}")
    current = metadata(context)
    disk["protocol"] = current["protocol"]
    disk["source"] = current["source"]
    generation = disk.get("generation", {})
    # The first full generation used perf_counter but called it CPU time.  The
    # numerical measurements remain valid elapsed wall times; rename them
    # explicitly rather than implying a new full-table training measurement.
    if "totalTrainingCpuSeconds" in generation:
        disk["generation"] = {
            "architecturesPerState": generation["architecturesPerState"],
            "states": generation["states"],
            "trainings": generation["trainings"],
            "totalTrainingWallSeconds": generation["totalTrainingCpuSeconds"],
            "meanTrainingWallSeconds": generation["meanTrainingCpuSeconds"],
            "timingNote": "Elapsed wall time measured by perf_counter during the original full generation; renamed without retraining.",
        }
    JSON_TARGET.write_text(json.dumps(disk, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    RUNTIME.write_text(render_js(disk), encoding="utf-8")
    print(json.dumps({"status": "REFRESHED_METADATA", "targetedReplays": list(replay_keys(context))}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate outputs plus five exact two-architecture replays")
    parser.add_argument("--refresh-metadata", action="store_true", help="validate rows, replay five keys, then refresh provenance without retraining all states")
    parser.add_argument("--workers", type=int, default=1, help="independent CPU workers for full generation only")
    args = parser.parse_args()
    if args.check:
        check()
        return
    if args.refresh_metadata:
        refresh_metadata()
        return
    if args.workers < 1:
        parser.error("--workers must be positive")
    output = build_full(args.workers)
    JSON_TARGET.write_text(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    RUNTIME.write_text(render_js(output), encoding="utf-8")
    print(json.dumps({"wrote": [str(JSON_TARGET), str(RUNTIME)], "generation": output["generation"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
