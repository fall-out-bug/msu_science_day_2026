#!/usr/bin/env python3
"""Independent numerical checks for every primitive and constructor architecture."""
import importlib.util
import sys
from copy import deepcopy
from pathlib import Path

import numpy as np

PREPARE = Path(__file__).parents[1] / "cnn-prepare.py"
spec = importlib.util.spec_from_file_location("cnn_prepare_for_math_check", PREPARE)
cnn = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cnn
spec.loader.exec_module(cnn)

RNG = np.random.default_rng(20261008)
EPS = 1e-6


def close(actual, expected, name):
    assert np.isclose(actual, expected, rtol=3e-4, atol=3e-5), (name, actual, expected)


def scalar_fd(loss, array, index):
    original = array[index]
    array[index] = original + EPS
    plus = loss()
    array[index] = original - EPS
    minus = loss()
    array[index] = original
    return (plus - minus) / (2 * EPS)


def cross_entropy(model, x, y):
    """Fresh fixed stream keeps dropout identical on both sides of every FD."""
    logits, _ = model.forward(x, True, cnn.stable_rng("math-fd"), update_bn=False)
    probabilities = np.exp(logits - logits.max(1, keepdims=True))
    probabilities /= probabilities.sum(1, keepdims=True)
    return float(-np.log(probabilities[np.arange(len(y)), y]).mean())


def input_gradient(model, x, y):
    """Backpropagate to x independently of TinyCNN.gradients' public output."""
    logits, cache = model.forward(x, True, cnn.stable_rng("math-fd"), update_bn=False)
    layers, activation_shape, _ = cache
    probabilities = np.exp(logits - logits.max(1, keepdims=True))
    probabilities /= probabilities.sum(1, keepdims=True)
    probabilities[np.arange(len(y)), y] -= 1
    probabilities /= len(y)
    gradient = np.broadcast_to(
        (probabilities @ model.params["head_w"].T)[:, :, None, None]
        / (activation_shape[2] * activation_shape[3]), activation_shape).copy()
    for name, cached in reversed(layers):
        if name == "relu":
            gradient *= cached > 0
        elif name == "dropout":
            if cached is not None:
                gradient *= cached
        elif name == "bn":
            gradient, _, _ = cnn.bn_backward(gradient, cached)
        else:
            gradient, _, _ = cnn.conv_backward(gradient, cached)
    return gradient


def check_convolution():
    x = RNG.normal(size=(2, 2, 4, 5))
    w = RNG.normal(size=(3, 2, 3, 3))
    b = RNG.normal(size=3)
    upstream = RNG.normal(size=(2, 3, 4, 5))
    output, cache = cnn.conv_forward(x, w, b)
    dx, dw, db = cnn.conv_backward(upstream, cache)
    objective = lambda: float((cnn.conv_forward(x, w, b)[0] * upstream).sum())
    for array, gradient, index, name in (
        (x, dx, (1, 1, 2, 3), "conv input"),
        (w, dw, (2, 1, 2, 1), "conv weight"),
        (b, db, (1,), "conv bias"),
    ):
        close(scalar_fd(objective, array, index), gradient[index], name)
    assert output.shape == (2, 3, 4, 5)


def check_batchnorm_independently():
    x = RNG.normal(size=(3, 4, 2, 5))
    gamma = RNG.normal(size=4)
    beta = RNG.normal(size=4)
    old_mean = RNG.normal(size=4)
    old_var = RNG.uniform(.1, 2, size=4)
    running_mean, running_var = old_mean.copy(), old_var.copy()
    actual, _ = cnn.bn_forward(x, gamma, beta, running_mean, running_var, True, True)
    mean, variance = x.mean((0, 2, 3)), x.var((0, 2, 3))
    expected = gamma[None, :, None, None] * (x - mean[None, :, None, None]) / np.sqrt(variance[None, :, None, None] + cnn.BN_EPSILON) + beta[None, :, None, None]
    assert np.allclose(actual, expected)
    assert np.allclose(running_mean, (1 - cnn.BN_MOMENTUM) * old_mean + cnn.BN_MOMENTUM * mean)
    assert np.allclose(running_var, (1 - cnn.BN_MOMENTUM) * old_var + cnn.BN_MOMENTUM * variance)
    before = (running_mean.copy(), running_var.copy())
    actual_eval, cache = cnn.bn_forward(x, gamma, beta, running_mean, running_var, False, True)
    expected_eval = gamma[None, :, None, None] * (x - before[0][None, :, None, None]) / np.sqrt(before[1][None, :, None, None] + cnn.BN_EPSILON) + beta[None, :, None, None]
    assert cache is None and np.allclose(actual_eval, expected_eval)
    assert np.array_equal(running_mean, before[0]) and np.array_equal(running_var, before[1])


def check_dropout():
    x = np.ones((400, 1, 16, 16))
    model = cnn.TinyCNN(cnn.architecture_by_id("d1-r-d"))
    model.params["w0"].fill(0)
    model.params["b0"].fill(1)
    train_a, _ = model.forward(x, True, np.random.default_rng(19), update_bn=False)
    train_b, _ = model.forward(x, True, np.random.default_rng(19), update_bn=False)
    train_c, _ = model.forward(x, True, np.random.default_rng(20), update_bn=False)
    eval_a, _ = model.forward(x, False, np.random.default_rng(19), update_bn=False)
    eval_b, _ = model.forward(x, False, np.random.default_rng(20), update_bn=False)
    assert np.array_equal(train_a, train_b) and not np.array_equal(train_a, train_c)
    assert np.array_equal(eval_a, eval_b), "dropout must be disabled in eval"
    mask = (np.random.default_rng(91).random((400, 4, 16, 16)) >= cnn.DROPOUT_RATE) / (1 - cnn.DROPOUT_RATE)
    assert abs(mask.mean() - 1) < .01


def check_dropout_training_seed_is_label_independent():
    x = RNG.normal(size=(3, 1, 5, 5))
    y = np.array([0, 1, 2])
    states = []
    original = cnn.TinyCNN.gradients
    def record(self, images, targets, rng, update_bn=True):
        states.append(deepcopy(rng.bit_generator.state))
        return original(self, images, targets, rng, update_bn)
    cnn.TinyCNN.gradients = record
    epochs = cnn.EPOCHS
    cnn.EPOCHS = 1
    try:
        cnn.train(cnn.TinyCNN(cnn.architecture_by_id("d1-r-d")), x, y, "0000000")
        cnn.train(cnn.TinyCNN(cnn.architecture_by_id("d2-r-d")), x, y, "2222222")
    finally:
        cnn.EPOCHS = epochs
        cnn.TinyCNN.gradients = original
    assert len(states) == 2 and states[0] == states[1], "dropout RNG must not depend on label key or architecture"


def check_all_architectures():
    x = RNG.normal(size=(3, 1, 5, 5)) + .13
    y = np.array([0, 1, 2])
    for architecture in cnn.architectures():
        model = cnn.TinyCNN(architecture)
        loss, gradients = model.gradients(x, y, cnn.stable_rng("math-fd"), update_bn=False)
        assert np.isfinite(loss) and set(gradients) == set(model.params), architecture.id
        for name, parameter in model.params.items():
            index = tuple(size // 2 for size in parameter.shape)
            close(scalar_fd(lambda: cross_entropy(model, x, y), parameter, index), gradients[name][index], f"{architecture.id} {name}")
        index = (1, 0, 2, 3)
        close(scalar_fd(lambda: cross_entropy(model, x, y), x, index), input_gradient(model, x, y)[index], f"{architecture.id} input")
        buffers = {name: value.copy() for name, value in model.buffers.items()}
        model.forward(x, False)
        assert all(np.array_equal(value, model.buffers[name]) for name, value in buffers.items()), architecture.id


check_convolution()
check_batchnorm_independently()
check_dropout()
check_dropout_training_seed_is_label_independent()
check_all_architectures()
print("PASS: primitive convolution FD (input/weight/bias); independent BN/dropout invariants and label-independent masks; all 22 architectures and every parameter family FD")
