#!/usr/bin/env python3
"""Generate exact CNN results with resumable, atomic architecture checkpoints."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import multiprocessing
import os
import sys
import tempfile
import time
from pathlib import Path

for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[name] = "1"
import numpy as np

HERE = Path(__file__).resolve().parent
GAME = HERE.parent.parent
RUNTIME = GAME / "cnn-experiments.js"
RESULTS = GAME / "cnn-results"
CHECKPOINTS = HERE / "checkpoints"
JSON_TARGET = HERE / "cnn-experiments.json"
PROTOCOL = json.loads((HERE / "protocol.json").read_text())
CONTEXT = None


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[name] = loaded
    spec.loader.exec_module(loaded)
    return loaded


cnn = module("cnn_prepare", GAME / "cnn-prepare.py")
prepare = cnn.prepare


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as output:
        json.dump(payload, output, ensure_ascii=False, separators=(",", ":"))
        output.write("\n")
        temporary = Path(output.name)
    os.replace(temporary, path)


def atomic_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as output:
        output.write(text)
        temporary = Path(output.name)
    os.replace(temporary, path)


def context():
    records, _ = prepare.build()
    items = {item["id"]: item for item in records["images"]}
    ids = records["protocol"]
    all_ids = ids["trainingIds"] + ids["reviewIds"] + ids["finalIds"]
    images = {item_id: cnn.load_image(Path(items[item_id]["src"]).name) for item_id in all_ids}
    return {
        "records": records, "items": items, "classes": [item["id"] for item in records["classes"]],
        "train": ids["trainingIds"], "review": ids["reviewIds"], "final": ids["finalIds"],
        "editable": records["editableIds"], "canonical": {item_id: items[item_id]["label"] for item_id in ids["trainingIds"]},
        "x": np.asarray([images[item_id] for item_id in ids["trainingIds"]])[:, None],
        "rx": np.asarray([images[item_id] for item_id in ids["reviewIds"]])[:, None],
        "fx": np.asarray([images[item_id] for item_id in ids["finalIds"]])[:, None],
    }


def labels(data, key):
    result = dict(data["canonical"])
    result.update({item_id: data["classes"][int(value)] for item_id, value in zip(data["editable"], key)})
    return result


def probabilities(model, images, ids, data):
    logits = model.forward(images, False)[0]
    values = np.exp(logits - logits.max(1, keepdims=True))
    values /= values.sum(1, keepdims=True)
    rows = []
    for item_id, row in zip(ids, values):
        index = int(row.argmax())
        rows.append({"id": item_id, "predicted": data["classes"][index], "expected": data["items"][item_id]["label"],
                     "probabilities": {name: round(float(value), 8) for name, value in zip(data["classes"], row)}})
    return {"predictions": rows, "correct": sum(row["predicted"] == row["expected"] for row in rows), "total": len(rows)}


def one(args):
    key, architecture_id = args
    data = CONTEXT
    architecture = cnn.architecture_by_id(architecture_id)
    model = cnn.TinyCNN(architecture)
    targets = np.asarray([data["classes"].index(labels(data, key)[item_id]) for item_id in data["train"]])
    started = time.perf_counter()
    loss = cnn.train(model, data["x"], targets, key)
    elapsed = time.perf_counter() - started
    return architecture_id, key, {
        "architectureId": architecture_id, "blocks": architecture.depth, "key": key,
        "trainLabels": {item_id: labels(data, key)[item_id] for item_id in data["train"]},
        "parameterCount": model.parameter_count,
        "loss": {"first": round(loss[0], 8), "last": round(loss[-1], 8)},
        "review": probabilities(model, data["rx"], data["review"], data),
        "final": probabilities(model, data["fx"], data["final"], data), "_elapsed": elapsed,
    }


def protocol(data):
    return {"protocolVersion": "2026-10-08-cnn-constructor-v1", "datasetVersion": data["records"]["datasetVersion"],
            "architectures": [architecture.id for architecture in cnn.architectures()], "editableIds": data["editable"],
            "classes": data["classes"], "trainingIds": data["train"], "reviewIds": data["review"], "finalIds": data["final"],
            "historicallyKnownFinal": True, "seed": cnn.SEED, "epochs": cnn.EPOCHS, "learningRate": cnn.LEARNING_RATE,
            "dropoutRate": cnn.DROPOUT_RATE, "bnMomentum": cnn.BN_MOMENTUM, "bnEpsilon": cnn.BN_EPSILON}


def valid_checkpoint(payload, architecture_id, keys, metadata, source):
    return (payload.get("architectureId") == architecture_id and payload.get("protocol") == metadata and
            payload.get("source") == source and set(payload.get("experiments", {})) == set(keys))


def publish_architecture(architecture_id, runs, metadata, source):
    if architecture_id == "d1-r":
        base = {"protocol": metadata, "source": source,
                "experiments": {key: {"key": key, "architectures": {"d1-r": runs[key]}} for key in sorted(runs)}}
        atomic_text(RUNTIME, "globalThis.GALAXY_CNN_EXPERIMENTS = " + json.dumps(base, ensure_ascii=False, separators=(",", ":")) + ";\n")
        return
    payload = {"architectureId": architecture_id, "protocol": metadata, "source": source, "experiments": runs}
    atomic_text(RESULTS / f"{architecture_id}.js", f"globalThis.GalaxyCNNResults.register({architecture_id!r}," + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ");\n")


def generate_architecture(architecture_id, keys, workers, metadata, source):
    checkpoint = CHECKPOINTS / f"{architecture_id}.json"
    if checkpoint.is_file():
        saved = json.loads(checkpoint.read_text())
        if valid_checkpoint(saved, architecture_id, keys, metadata, source):
            print(json.dumps({"architecture": architecture_id, "status": "resume", "rows": len(keys)}, ensure_ascii=False), flush=True)
            publish_architecture(architecture_id, saved["experiments"], metadata, source)
            return saved["experiments"], float(saved.get("sumTrainingWallSeconds", 0))
        print(json.dumps({"architecture": architecture_id, "status": "stale-checkpoint-ignored"}, ensure_ascii=False), flush=True)
    runs, elapsed = {}, 0.0
    jobs = [(key, architecture_id) for key in keys]
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("fork")) as executor:
        for number, (_, key, row) in enumerate(executor.map(one, jobs), 1):
            elapsed += row.pop("_elapsed")
            runs[key] = row
            if number % 100 == 0 or number == len(keys):
                print(json.dumps({"architecture": architecture_id, "completed": number, "total": len(keys),
                                  "sumTrainingWallSeconds": round(elapsed, 3)}, ensure_ascii=False), flush=True)
    atomic_json(checkpoint, {"architectureId": architecture_id, "protocol": metadata, "source": source,
                             "sumTrainingWallSeconds": elapsed, "experiments": runs})
    publish_architecture(architecture_id, runs, metadata, source)
    print(json.dumps({"architecture": architecture_id, "status": "checkpointed-and-published", "rows": len(keys)}, ensure_ascii=False), flush=True)
    return runs, elapsed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--architecture")
    args = parser.parse_args()
    global CONTEXT
    CONTEXT = context()
    keys = ["".join(map(str, item)) for item in np.ndindex(*(3 for _ in CONTEXT["editable"]))]
    architecture_ids = [architecture.id for architecture in cnn.architectures()]
    if args.architecture:
        cnn.architecture_by_id(args.architecture)
        architecture_ids = [args.architecture]
    if args.pilot:
        started = time.perf_counter()
        _, _, row = one(("0121021", architecture_ids[0]))
        print(json.dumps({"rows": 1, "seconds": row["_elapsed"], "wallSeconds": time.perf_counter() - started}, ensure_ascii=False))
        return
    metadata = protocol(CONTEXT)
    source = {"protocolSha256": sha(HERE / "protocol.json"), "cnnPrepareSha256": sha(GAME / "cnn-prepare.py"),
              "generatorSha256": sha(__file__)}
    all_runs, elapsed = {}, 0.0
    for architecture_id in architecture_ids:
        runs, seconds = generate_architecture(architecture_id, keys, args.workers, metadata, source)
        all_runs[architecture_id] = runs
        elapsed += seconds
    if architecture_ids == [architecture.id for architecture in cnn.architectures()]:
        atomic_json(JSON_TARGET, {"protocol": metadata, "source": source,
                                  "generation": {"trainings": len(keys) * len(architecture_ids), "sumTrainingWallSeconds": elapsed},
                                  "experiments": all_runs})
        print(json.dumps({"status": "complete", "trainings": len(keys) * len(architecture_ids),
                          "sumTrainingWallSeconds": round(elapsed, 3)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
