#!/usr/bin/env python3
"""Semantic checks for the generated, offline CNN comparison."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("galaxy_cnn", ROOT / "cnn-prepare.py")
assert spec and spec.loader
cnn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cnn)

data = cnn.build()
assert data["trainingIds"] and data["reviewIds"]
assert len(data["trainingIds"]) == 9
assert len(data["reviewIds"]) == 3
assert data["protocol"]["implementation"].startswith("NumPy CPU backpropagation")
assert {model["blocks"] for model in data["models"]} == {1, 2}
assert [model["parameters"] for model in data["models"]] == [55, 203]
for model in data["models"]:
    assert model["total"] == len(data["reviewIds"])
    assert model["correct"] == sum(row["predicted"] == row["expected"] for row in model["predictions"])
    assert [row["id"] for row in model["predictions"]] == data["reviewIds"]
    assert model["loss"]["last"] < model["loss"]["first"]

# Check the convolutional backpropagation itself on a small deterministic batch.
# This catches a plausible implementation error that a decreasing training loss
# alone would not expose.
rng = cnn.np.random.default_rng(17)
model = cnn.TinyCNN(2, rng)
inputs = rng.normal(size=(2, 1, 6, 6))
targets = cnn.np.array([0, 2])
_, analytic = model.gradients(inputs, targets)
epsilon = 1e-5
for name, index in (("w0", (0, 0, 1, 1)), ("w1", (2, 3, 0, 2)), ("head_w", (1, 2))):
    parameter = model.params[name]
    original = parameter[index]
    parameter[index] = original + epsilon
    upper, _ = model.gradients(inputs, targets)
    parameter[index] = original - epsilon
    lower, _ = model.gradients(inputs, targets)
    parameter[index] = original
    numerical = (upper - lower) / (2 * epsilon)
    assert abs(numerical - analytic[name][index]) < 2e-5, (name, numerical, analytic[name][index])
print("PASS: trained convolution weights, finite-difference backprop, fixed train-only inputs, concrete review predictions")
