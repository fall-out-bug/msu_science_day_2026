#!/usr/bin/env python3
"""Генератор учебных данных «Охоты за звёздными аномалиями».

Замороженные параметры (сессия 2026-10-01, приёмка на 3 сидах):
  патч 128x128 uint8 PNG; фон 100±5σ; PSF U(1.2,1.8) px; 25–50 звёзд;
  амплитуды 10^U(1.2,2.5).
  train: 300 нормальных пар, сид 300.
  контактный лист 12 = 4 норма + 2 движение (8–14 px, 120–200) +
    2 переменность (×4–6) + 2 артефакт (600–900) + 1 слабое (10–14) +
    1 пограничное (36–46); сид курируемый перебором, коридор пограничного 1.5–2.9,
    ≤1 нормы выше мягкого порога (лишняя проверка), строгий порог 3.0 чист от нормы.
  демо: 200 патчей, отдельный сид, без инвариантов.
  доп-кадр = 3-я эпоха: артефакт исчезает, движение продолжается,
    переменность подтверждается, слабое остаётся спорным, норма — только шум.
Детектор: 3 признака (max|diff|, площадь |diff|>4σ, фон),
  score = max (f - med) / (p99 - med) по train-норме.

Запуск: python3 tools/generate_data.py --out artifacts [--contact-seed N]
"""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

H = W = 128
BG, NOISE = 100.0, 5.0
THRESH_SOFT, THRESH_STRICT = 1.0, 3.0

TRAIN_SEED, TRAIN_N = 300, 300
DEMO_SEED, DEMO_N = 400, 200
NORM_IN_CONTACT, PER_TYPE_IN_CONTACT = 4, 2

EXPLANATIONS = {
    "normal": "Обычное звёздное поле: различия между кадрами — только шум.",
    "mover": "Источник сместился между кадрами относительно звёзд — кандидат в движущиеся объекты. Для вывода нужна серия кадров, одного изображения мало.",
    "variable": "Яркость источника изменилась. Причина неизвестна: вспышка или переменность — нужны повторные наблюдения, по двум кадрам не объявляют открытие.",
    "artifact": "Яркий пик только на одном кадре — след космического луча или дефект матрицы. Дополнительный кадр показывает: пик исчез. Необычность не значит новость.",
    "weak": "Слабое изменение на шумном фоне. Модель дала низкую оценку: при строгом пороге такое легко пропустить.",
    "weak_mid": "Пограничный случай: оценка около порога отбора. Мягкий порог находит, строгий — пропускает. Порог — это выбор цены ошибки.",
}

def make_stars(rng, n=None):
    n = int(n or rng.integers(25, 51))
    return [(float(x), float(y), 10 ** rng.uniform(1.2, 2.5), rng.uniform(1.2, 1.8))
            for x, y in rng.uniform(5, W - 5, (n, 2))]

def render(stars, rng):
    img = rng.normal(BG, NOISE, (H, W))
    yy, xx = np.mgrid[0:H, 0:W]
    for (x, y, amp, sig) in stars:
        r = int(np.ceil(4 * sig))
        xi, yi = int(round(x)), int(round(y))
        x0, x1 = max(0, xi - r), min(W, xi + r + 1)
        y0, y1 = max(0, yi - r), min(H, yi + r + 1)
        if x0 >= x1 or y0 >= y1:
            continue
        lx, ly = xx[y0:y1, x0:x1], yy[y0:y1, x0:x1]
        img[y0:y1, x0:x1] += amp * np.exp(-((lx - x) ** 2 + (ly - y) ** 2) / (2 * sig ** 2))
    return img

def to_png(arr):
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="L")

def features(e1, e2):
    diff = e2 - e1
    sd = 1.4826 * np.median(np.abs(diff - np.median(diff)))
    return np.array([float(np.max(np.abs(diff))),
                     float(np.sum(np.abs(diff) > 4 * sd)),
                     float(np.median(e2))], dtype=float)

def train_stats(seed=TRAIN_SEED, n=TRAIN_N):
    rng = np.random.default_rng(seed)
    tf = np.array([features(render(s := make_stars(rng), rng), render(s, rng))
                   for _ in range(n)])
    med = np.median(tf, axis=0)
    p99 = np.percentile(tf, 99, axis=0)
    return med, p99

# --- конструкторы участков (2 базовых кадра + 3-я эпоха «доп-наблюдения») ---

def patch_normal(rng):
    s = make_stars(rng)
    return [render(s, rng) for _ in range(3)], "normal"

def patch_mover(rng):
    s = make_stars(rng)
    x, y = rng.uniform(30, W - 30, 2)
    d, th = rng.uniform(8, 14), rng.uniform(0, 2 * np.pi)
    amp = rng.uniform(120, 200)
    star = lambda t: (x + t * d * np.cos(th), y + t * d * np.sin(th), amp, 1.5)
    return [render(s + [star(t)], rng) for t in (0, 1, 2)], "mover"

def patch_variable(rng):
    s = make_stars(rng)
    j = int(rng.integers(0, len(s)))
    x, y, a, sig = s[j]
    amp2 = a * rng.uniform(4, 6)
    s1, s2, s3 = list(s), list(s), list(s)
    s1[j] = (x, y, a, sig)
    s2[j] = (x, y, amp2, sig)
    s3[j] = (x, y, amp2 * rng.uniform(0.85, 1.15), sig)  # подтверждается
    return [render(s1, rng), render(s2, rng), render(s3, rng)], "variable"

def patch_artifact(rng):
    s = make_stars(rng)
    e2 = render(s, rng)
    e3 = render(s, rng)  # пик исчезает
    x, y = rng.integers(10, W - 10, 2)
    e2[y, x:x + int(rng.integers(2, 5))] += rng.uniform(600, 900)
    return [render(s, rng), e2, e3], "artifact"

def patch_weak(rng, lo=10, hi=14):
    s = make_stars(rng)
    x, y = rng.uniform(20, W - 20, 2)
    star = (x, y, rng.uniform(lo, hi), 1.5)
    return [render(s, rng), render(s + [star], rng), render(s + [star], rng)], \
        ("weak" if lo < 20 else "weak_mid")

def contact_patches(rng):
    out = []
    for _ in range(NORM_IN_CONTACT):
        out.append(patch_normal(rng))
    for _ in range(PER_TYPE_IN_CONTACT):
        out.append(patch_mover(rng))
    for _ in range(PER_TYPE_IN_CONTACT):
        out.append(patch_variable(rng))
    for _ in range(PER_TYPE_IN_CONTACT):
        out.append(patch_artifact(rng))
    out.append(patch_weak(rng, 10, 14))
    out.append(patch_weak(rng, 36, 46))
    return out

def demo_patches(rng):
    plan = (["normal"] * 100 + ["mover"] * 30 + ["variable"] * 30 +
            ["artifact"] * 20 + ["weak"] * 10 + ["weak_mid"] * 10)
    rng.shuffle(plan)
    builders = {"normal": patch_normal, "mover": patch_mover,
                "variable": patch_variable, "artifact": patch_artifact,
                "weak": patch_weak, "weak_mid": lambda r: patch_weak(r, 36, 46)}
    return [builders[t](rng) for t in plan]

def scores_of(epochs, med, p99):
    f = features(epochs[0], epochs[1])
    z = (f - med) / np.maximum(p99 - med, 1e-9)
    return f, z, float(np.max(z))

def curate_contact(med, p99):
    """Перебор сидов, пока лист не пройдёт инварианты заморозки."""
    for gs in range(1, 1000):
        rng = np.random.default_rng(gs)
        patches = contact_patches(rng)
        sc = {}
        for epochs, t in patches:
            sc.setdefault(t, []).append(scores_of(epochs, med, p99)[2])
        normals = sc["normal"]
        ok = (min(sc["mover"] + sc["variable"] + sc["artifact"]) > THRESH_STRICT
              and max(sc["weak"]) < THRESH_SOFT
              and 1.5 <= sc["weak_mid"][0] <= 2.9
              and sum(1 for v in normals if v > THRESH_SOFT) <= 1
              and max(normals) < THRESH_STRICT)
        if ok:
            return gs, patches
    raise RuntimeError("курируемый сид не найден за 999 попыток — проверить параметры")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="artifacts")
    ap.add_argument("--contact-seed", type=int, default=0, help="0 = автокурирование")
    args = ap.parse_args()
    out = Path(args.out)
    (out / "train").mkdir(parents=True, exist_ok=True)
    (out / "contact").mkdir(exist_ok=True)
    (out / "demo").mkdir(exist_ok=True)

    print("train…")
    med, p99 = train_stats()

    if args.contact_seed:
        rng = np.random.default_rng(args.contact_seed)
        patches = contact_patches(rng)
        cs = args.contact_seed
    else:
        print("курирование сида контактного листа…")
        cs, patches = curate_contact(med, p99)
    print(f"контактный лист: сид {cs}")

    print("demo…")
    demo = demo_patches(np.random.default_rng(DEMO_SEED))

    public, key = {"meta": {}, "patches": []}, {"patches": []}
    public["meta"] = {
        "train_seed": TRAIN_SEED, "train_n": TRAIN_N, "contact_seed": cs,
        "demo_seed": DEMO_SEED, "demo_n": DEMO_N,
        "thresholds": {"soft": THRESH_SOFT, "strict": THRESH_STRICT},
        "precomputed": True, "synthetic": True,
        "score_formula": "max_i (f_i - median_i)/(p99_i - median_i), f: max|diff|, площадь>4σ, фон",
    }

    def emit(prefix, folder, epochs, ptype):
        fid = f"{prefix}{ptype[1] if False else ''}"  # placeholder, заменяется ниже
    # порядок выдачи с честными id и ключом
    counter = {}
    for set_name, items in (("contact", patches), ("demo", demo)):
        for i, (epochs, ptype) in enumerate(items, 1):
            counter[set_name] = counter.get(set_name, 0) + 1
            pid = f"{set_name[0]}{counter[set_name]:03d}"
            files = []
            for k, arr in enumerate(epochs, 1):
                rel = f"{set_name}/{pid}_e{k}.png"
                to_png(arr).save(out / rel, optimize=True)
                files.append(rel)
            f, z, score = scores_of(epochs, med, p99)
            public["patches"].append({
                "id": pid, "set": set_name, "epochs": files,
                "features": {"max_diff": round(f[0], 2), "area": int(f[1]), "bg": round(f[2], 2)},
                "z": [round(float(v), 2) for v in z], "score": round(score, 2),
            })
            key["patches"].append({"id": pid, "set": set_name, "type": ptype,
                                   "explanation": EXPLANATIONS[ptype]})

    (out / "public.json").write_text(json.dumps(public, ensure_ascii=False, indent=1))
    (out / "key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1))

    # приёмочный отчёт
    by = {}
    for p in public["patches"]:
        if p["set"] == "contact":
            by.setdefault(key["patches"][public["patches"].index(p)]["type"], []).append(p["score"])
    print("\nПриёмка контактного листа (сид %s):" % cs)
    for t, v in sorted(by.items()):
        print(f"  {t:9s} scores={[round(x, 2) for x in v]}")
    n_above_soft = sum(1 for t, v in by.items() if t == "normal" for x in v if x > THRESH_SOFT)
    print(f"  строгий порог чист от нормы: {all(x < THRESH_STRICT for x in by['normal'])}")
    print(f"  норм выше мягкого: {n_above_soft} (допустимо ≤1, это «лишняя проверка»)")
    total = sum(1 for _ in out.rglob("*.png"))
    size = sum((f.stat().st_size for f in out.rglob("*") if f.is_file()), 0)
    print(f"  файлов PNG: {total}, суммарно: {size / 1024 / 1024:.1f} МиБ")

if __name__ == "__main__":
    main()
