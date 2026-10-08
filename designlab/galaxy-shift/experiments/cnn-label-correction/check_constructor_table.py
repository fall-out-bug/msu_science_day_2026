#!/usr/bin/env python3
"""Check the exact CNN constructor table; never retrains or substitutes rows."""
import argparse
import hashlib
import json
import math
from itertools import product, permutations
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parent.parent
BASE = GAME / "cnn-experiments.js"
SHARDS = GAME / "cnn-results"
FULL_JSON = HERE / "cnn-experiments.json"
EXPECTED_VERSION = "2026-10-08-cnn-constructor-v1"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def js_json(path, prefix):
    text = path.read_text(encoding="utf-8")
    suffix = ");\n" if prefix.startswith("globalThis.GalaxyCNNResults.register") else ";\n"
    assert text.startswith(prefix) and text.endswith(suffix), path
    return json.loads(text[len(prefix):-len(suffix)])


def expected_keys(width):
    return {"".join(item) for item in product("012", repeat=width)}


def assert_probability_result(result, split, protocol):
    classes = protocol["classes"]
    ids = protocol[f"{split}Ids"]
    predictions = result.get("predictions")
    assert isinstance(predictions, list) and result.get("total") == len(ids) == len(predictions)
    assert [item.get("id") for item in predictions] == ids
    correct = 0
    for item in predictions:
        probabilities = item.get("probabilities")
        assert item.get("predicted") in classes and item.get("expected") == reference_labels[item["id"]]
        assert isinstance(probabilities, dict) and list(probabilities) == classes
        assert all(isinstance(value, (int, float)) and math.isfinite(value) and 0 <= value <= 1 for value in probabilities.values())
        assert abs(sum(probabilities.values()) - 1) <= 6e-8
        # Values are serialized to eight decimals, so preserve argmax under that rounding.
        assert probabilities[item["predicted"]] >= max(probabilities.values()) - 1e-8
        correct += item["predicted"] == item["expected"]
    assert result.get("correct") == correct


def assert_run(run, aid, key, protocol, fixed_labels):
    assert run.get("architectureId") == aid and run.get("key") == key
    assert run.get("blocks") == int(aid[1]) and isinstance(run.get("parameterCount"), int) and run["parameterCount"] > 0
    labels = run.get("trainLabels")
    assert isinstance(labels, dict) and list(labels) == protocol["trainingIds"]
    for item_id, digit in zip(protocol["editableIds"], key):
        assert labels[item_id] == protocol["classes"][int(digit)]
    for item_id in protocol["trainingIds"]:
        if item_id not in protocol["editableIds"]:
            if fixed_labels is None:
                continue
            assert labels[item_id] == fixed_labels[item_id]
    loss = run.get("loss")
    assert isinstance(loss, dict) and all(isinstance(loss.get(name), (int, float)) and math.isfinite(loss[name]) for name in ("first", "last"))
    for split in ("review", "final"):
        assert_probability_result(run[split], split, protocol)


def assert_source(source):
    assert source == {
        "protocolSha256": sha(HERE / "protocol.json"),
        "cnnPrepareSha256": sha(GAME / "cnn-prepare.py"),
        "generatorSha256": sha(HERE / "generate_cnn_experiments.py"),
    }, "source hashes do not describe the present scientific code"


base = js_json(BASE, "globalThis.GALAXY_CNN_EXPERIMENTS = ")
protocol = base.get("protocol")
assert protocol and protocol.get("protocolVersion") == EXPECTED_VERSION
architectures = protocol.get("architectures")
assert isinstance(architectures, list) and len(architectures) == 22 and len(set(architectures)) == 22 and architectures[0] == "d1-r"
keys = expected_keys(len(protocol["editableIds"]))
assert len(keys) == 2187 and set(base.get("experiments", {})) == keys
assert_source(base.get("source"))

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--require-full',action='store_true')
args = parser.parse_args()
data_source = (GAME/'data.js').read_text()
data = json.loads(data_source.split('globalThis.GALAXY_DATA = ',1)[1].removesuffix(';\n'))
reference_labels = {item['id']:item['label'] for item in data['images']}
assert protocol['datasetVersion'] == data['datasetVersion']
assert protocol['classes'] == [item['id'] for item in data['classes']]
assert protocol['editableIds'] == data['editableIds'] == data['childIds'] + data['oldIds']
assert len(data['childIds']) == 4 and len(data['oldIds']) == 3
assert len(reference_labels) == 15
for split, count in [('training',9),('review',3),('final',3)]:
    assert protocol[split+'Ids'] == data['protocol'][split+'Ids']
    assert len(set(protocol[split+'Ids'])) == count
assert len(set(protocol['trainingIds']+protocol['reviewIds']+protocol['finalIds'])) == 15
assert set(protocol['editableIds']) <= set(protocol['trainingIds'])
allowed = {f"d{depth}-{'-'.join(tail)}" for depth in [1,2]
           for optional in [(),('bn',),('d',),('bn','d')]
           for tail in permutations(('r',)+optional)}
assert set(architectures) == allowed
frozen = json.loads((HERE/'protocol.json').read_text())['frozenTraining']
for name in ['seed','epochs','learningRate']:
    assert protocol[name] == frozen[name]
fixed_labels = {item_id:reference_labels[item_id] for item_id in protocol['trainingIds'] if item_id not in protocol['editableIds']}
for key in keys:
    row = base["experiments"][key]
    assert row == {"key": key, "architectures": {"d1-r": row["architectures"]["d1-r"]}}
    labels = row["architectures"]["d1-r"]["trainLabels"]
    if fixed_labels is None:
        fixed_labels = {item_id: labels[item_id] for item_id in protocol["trainingIds"] if item_id not in protocol["editableIds"]}
    assert_run(row["architectures"]["d1-r"], "d1-r", key, protocol, fixed_labels)

loader = (GAME / "cnn-results-loader.js").read_text(encoding="utf-8")
session = (GAME / "cnn-session.js").read_text(encoding="utf-8")
assert "Admit the entire shard before publishing any of its rows." in loader
assert "Для этих меток и архитектуры модели нет подготовленного опыта." in session

all_runs = {"d1-r": {key: base["experiments"][key]["architectures"]["d1-r"] for key in keys}}
current_shards, stale_shards = {}, []
for aid in architectures[1:]:
    path = SHARDS / f"{aid}.js"
    if not path.is_file():
        continue
    shard = js_json(path, f"globalThis.GalaxyCNNResults.register({aid!r},")
    assert shard.get("architectureId") == aid
    if shard.get("protocol") != protocol or shard.get("source") != base["source"]:
        stale_shards.append(aid)
        continue
    runs = shard.get("experiments")
    assert isinstance(runs, dict) and set(runs) == keys
    for key in keys:
        assert_run(runs[key], aid, key, protocol, fixed_labels)
    all_runs[aid] = runs
    current_shards[aid] = runs

if len(current_shards) != 21:
    print(json.dumps({"status": "BASELINE_PASS", "keys": len(keys), "inlineArchitectures": 1,
                      "readyShards": len(current_shards), "pendingShards": 21 - len(current_shards),
                      "staleShardsIgnored": len(stale_shards), "trainingsVerified": len(keys) * (1 + len(current_shards)),
                      "protocolVersion": EXPECTED_VERSION}, ensure_ascii=False))
    raise SystemExit(1 if args.require_full else 0)

complete = json.loads(FULL_JSON.read_text(encoding="utf-8"))
assert complete.get("protocol") == protocol and complete.get("source") == base["source"]
assert set(complete.get("experiments", {})) == set(architectures)
for aid in architectures:
    assert complete["experiments"][aid] == all_runs[aid], f"JSON/shard mismatch: {aid}"
generation = complete.get("generation", {})
assert generation.get("trainings") == 22 * 2187
print(json.dumps({"status": "FULL_PASS", "keys": len(keys), "architectures": len(architectures),
                  "trainings": 22 * len(keys), "protocolVersion": EXPECTED_VERSION}, ensure_ascii=False))
