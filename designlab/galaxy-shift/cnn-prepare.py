#!/usr/bin/env python3
"""Precompute two small, deterministic CPU CNN demonstrations.

The game never trains in the browser.  This script reads the admitted JPEGs,
checks their hashes through ``prepare-data.py``, trains on the nine correctly
labelled training objects only, and writes the exact review predictions.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
PREPARE_SPEC = importlib.util.spec_from_file_location("galaxy_prepare", ROOT / "prepare-data.py")
assert PREPARE_SPEC and PREPARE_SPEC.loader
prepare = importlib.util.module_from_spec(PREPARE_SPEC)
PREPARE_SPEC.loader.exec_module(prepare)

SEED = 20261006
IMAGE_SIZE = 32
EPOCHS = 420
LEARNING_RATE = 0.025


def load_image(filename: str) -> np.ndarray:
    """Return the fixed centre crop as a one-channel, standardized image."""
    path = prepare.ASSETS / filename
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != prepare.EXPECTED_SOURCE_SHA256[filename]:
        raise RuntimeError(f"admission hash mismatch: {filename}")
    with Image.open(path) as source:
        image = source.convert("L")
        width, height = image.size
        side = int(min(width, height) * 0.75)
        image = image.crop(((width - side) // 2, (height - side) // 2,
                            (width + side) // 2, (height + side) // 2))
        image = image.resize((IMAGE_SIZE, IMAGE_SIZE), Image.Resampling.LANCZOS)
    values = np.asarray(image, dtype=np.float64) / 255.0
    return (values - values.mean()) / (values.std() + 1e-8)


def conv_forward(x: np.ndarray, weight: np.ndarray, bias: np.ndarray) -> tuple[np.ndarray, tuple]:
    """Same-size 3x3 convolution, with a cache for its exact backward pass."""
    _, _, _, _ = x.shape
    padded = np.pad(x, ((0, 0), (0, 0), (1, 1), (1, 1)))
    windows = np.lib.stride_tricks.sliding_window_view(padded, (3, 3), axis=(2, 3))
    output = np.einsum("nchwkl,fckl->nfhw", windows, weight, optimize=True) + bias[None, :, None, None]
    return output, (windows, weight, x.shape)


def conv_backward(gradient: np.ndarray, cache: tuple) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    windows, weight, shape = cache
    d_weight = np.einsum("nfhw,nchwkl->fckl", gradient, windows, optimize=True)
    d_bias = gradient.sum(axis=(0, 2, 3))
    n, channels, height, width = shape
    padded = np.zeros((n, channels, height + 2, width + 2), dtype=np.float64)
    for row in range(3):
        for column in range(3):
            padded[:, :, row:row + height, column:column + width] += np.einsum(
                "nfhw,fc->nchw", gradient, weight[:, :, row, column], optimize=True)
    return padded[:, :, 1:-1, 1:-1], d_weight, d_bias


class TinyCNN:
    """A deliberately tiny CNN: convolution/ReLU blocks, average pool, softmax."""

    def __init__(self, blocks: int, rng: np.random.Generator):
        self.blocks = blocks
        self.params: dict[str, np.ndarray] = {}
        in_channels = 1
        for layer in range(blocks):
            self.params[f"w{layer}"] = rng.normal(0.0, np.sqrt(2 / (in_channels * 9)), (4, in_channels, 3, 3))
            self.params[f"b{layer}"] = np.zeros(4)
            in_channels = 4
        self.params["head_w"] = rng.normal(0.0, np.sqrt(2 / in_channels), (in_channels, 3))
        self.params["head_b"] = np.zeros(3)

    @property
    def parameter_count(self) -> int:
        return sum(value.size for value in self.params.values())

    def forward(self, x: np.ndarray) -> tuple[np.ndarray, tuple]:
        activations = x
        blocks = []
        for layer in range(self.blocks):
            conv, cache = conv_forward(activations, self.params[f"w{layer}"], self.params[f"b{layer}"])
            activations = np.maximum(conv, 0.0)
            blocks.append((cache, conv))
        pooled = activations.mean(axis=(2, 3))
        logits = pooled @ self.params["head_w"] + self.params["head_b"]
        return logits, (blocks, activations.shape, pooled)

    def gradients(self, x: np.ndarray, targets: np.ndarray) -> tuple[float, dict[str, np.ndarray]]:
        logits, (blocks, activation_shape, pooled) = self.forward(x)
        shifted = logits - logits.max(axis=1, keepdims=True)
        probabilities = np.exp(shifted)
        probabilities /= probabilities.sum(axis=1, keepdims=True)
        loss = float(-np.log(probabilities[np.arange(len(targets)), targets] + 1e-12).mean())
        d_logits = probabilities
        d_logits[np.arange(len(targets)), targets] -= 1
        d_logits /= len(targets)
        gradients = {
            "head_w": pooled.T @ d_logits,
            "head_b": d_logits.sum(axis=0),
        }
        gradient = (d_logits @ self.params["head_w"].T)[:, :, None, None]
        gradient = np.broadcast_to(gradient / (activation_shape[2] * activation_shape[3]), activation_shape).copy()
        for layer in reversed(range(self.blocks)):
            cache, pre_relu = blocks[layer]
            gradient *= pre_relu > 0
            gradient, d_weight, d_bias = conv_backward(gradient, cache)
            gradients[f"w{layer}"] = d_weight
            gradients[f"b{layer}"] = d_bias
        return loss, gradients

    def predict(self, x: np.ndarray) -> np.ndarray:
        return self.forward(x)[0].argmax(axis=1)


def train(model: TinyCNN, images: np.ndarray, targets: np.ndarray) -> list[float]:
    """Full-batch Adam. The fixed seed and no augmentation make the run repeatable."""
    first = {name: np.zeros_like(value) for name, value in model.params.items()}
    second = {name: np.zeros_like(value) for name, value in model.params.items()}
    losses = []
    for step in range(1, EPOCHS + 1):
        loss, gradients = model.gradients(images, targets)
        if step in (1, EPOCHS):
            losses.append(loss)
        for name, value in model.params.items():
            first[name] = 0.9 * first[name] + 0.1 * gradients[name]
            second[name] = 0.999 * second[name] + 0.001 * gradients[name] ** 2
            m_hat = first[name] / (1 - 0.9 ** step)
            v_hat = second[name] / (1 - 0.999 ** step)
            value -= LEARNING_RATE * m_hat / (np.sqrt(v_hat) + 1e-8)
    return losses


def build() -> dict:
    records, _ = prepare.build()
    items = {item["id"]: item for item in records["images"]}
    class_ids = [item["id"] for item in records["classes"]]
    label_index = {label: index for index, label in enumerate(class_ids)}
    training_ids = records["protocol"]["trainingIds"]
    review_ids = records["protocol"]["reviewIds"]
    images = {item_id: load_image(Path(items[item_id]["src"]).name) for item_id in training_ids + review_ids}
    train_x = np.asarray([images[item_id] for item_id in training_ids])[:, None, :, :]
    train_y = np.asarray([label_index[items[item_id]["label"]] for item_id in training_ids])
    review_x = np.asarray([images[item_id] for item_id in review_ids])[:, None, :, :]
    models = []
    for blocks in (1, 2):
        model = TinyCNN(blocks, np.random.default_rng(SEED))
        losses = train(model, train_x, train_y)
        predicted = model.predict(review_x)
        predictions = [{"id": item_id, "predicted": class_ids[int(label)], "expected": items[item_id]["label"]}
                       for item_id, label in zip(review_ids, predicted)]
        models.append({
            "id": f"cnn-{blocks}-block",
            "name": f"CNN: {blocks} {'свёрточный блок' if blocks == 1 else 'свёрточных блока'}",
            "blocks": blocks,
            "parameters": model.parameter_count,
            "predictions": predictions,
            "correct": sum(row["predicted"] == row["expected"] for row in predictions),
            "total": len(predictions),
            "loss": {"first": round(losses[0], 8), "last": round(losses[-1], 8)},
        })
    return {
        "models": models,
        "trainingIds": training_ids,
        "reviewIds": review_ids,
        "note": "Два заранее рассчитанных CPU-опыта на одном корректно подписанном наборе из 9 учебных объектов. Свёрточные веса и классификатор обучались полным набором 420 шагов Adam с фиксированным seed; аугментаций и проверочных ответов при обучении не было. Три review-объекта — знакомая демонстрационная проверка, поэтому её счёт не является независимой оценкой и не обещает преимущество двух блоков.",
        "protocol": {"seed": SEED, "image": "75% centre crop, grayscale 32x32, per-image standardization", "epochs": EPOCHS, "optimizer": "Adam, full batch, lr=0.025", "implementation": "NumPy CPU backpropagation; no GPU and no model service"},
    }


def rendered(data: dict) -> str:
    return "// Generated by cnn-prepare.py; do not edit by hand.\n" + "globalThis.GALAXY_CNN = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="rebuild and compare cnn-data.js without writing")
    args = parser.parse_args()
    output = rendered(build())
    target = ROOT / "cnn-data.js"
    if args.check:
        if not target.is_file() or target.read_text(encoding="utf-8") != output:
            raise SystemExit("generated file differs: cnn-data.js")
        print("check passed: two trained CPU CNNs, 9 train / 3 review, admission hashes verified")
        return
    target.write_text(output, encoding="utf-8")
    print("wrote cnn-data.js")


if __name__ == "__main__":
    main()
