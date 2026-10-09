#!/usr/bin/env python3
"""Build the offline game from verified real ZTF observations, without network.

Public build API: build_game_data() -> (data, contact image arrays),
png_bytes(array), render_js(data). Training uses 300 disjoint q4 patches;
200 unlabelled demonstration patches use q3. Contact labels come from the
curated manifest and independent evidence, never from the detector score.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools import realdata as rd
from tools import field_context as fc

OBS = ROOT / "assets/observations"
MANIFEST = OBS / "manifest.json"
FEATURES = ("max_diff", "area", "peak")
FEATURE_RU = {
    "max_diff": "максимальная абсолютная разность кадров",
    "area": "число пикселей с абсолютной разностью больше 4σ",
    "peak": "максимальная положительная разность в единицах σ шума",
}
THRESH_SOFT, THRESH_STRICT = 1.0, 3.0
CONTACT_LAYOUT = ("normal", "mover", "variable", "artifact", "normal", "weak",
                  "mover", "artifact", "normal", "weak_mid", "variable", "normal")
SHORT_PLAN = {"normal": 2, "mover": 1, "variable": 1, "artifact": 1, "weak_mid": 1}
VERDICTS = {"normal": "stable", "mover": "sky", "variable": "sky",
            "artifact": "artifact", "weak": "sky", "weak_mid": "sky",
            "unresolved": "uncertain"}
EXPLANATIONS = {
    "normal": "На этих трёх снимках не установлено заметного изменения источников. "
              "Это не означает, что все звёзды этого участка всегда постоянны.",
    "mover": "Источник меняет положение относительно звёзд. Его движение "
             "сопоставлено с эфемеридой малого тела Солнечной системы; "
             "вывод основан не на одной необычной точке.",
    "variable": "Изменение блеска источника подтверждается независимой фотометрией. "
                "Одна лишь разница яркости отдельных пикселей такого вывода не даёт: "
                "форму звёзд меняют атмосфера и шум.",
    "artifact": "Различие связано с помехой на изображении. Помимо формы и "
                "сравнения кадров, основанием служит исходная маска качества ZTF.",
    "weak": "Слабое изменение блеска подтверждено фотометрией: источник "
            "ослаб, тогда как звёзды сравнения почти не изменились. "
            "На глаз различие трудно заметить; низкая оценка алгоритма "
            "не отменяет измеренного изменения.",
    "weak_mid": "Блеск источника изменился: это подтверждается фотометрией "
                "кадров и каталога. Алгоритм может пропустить настоящее "
                "изменение; его оценка не заменяет проверку наблюдений.",
    "unresolved": "Реальный архивный участок без установленной физической "
                  "классификации. Оценка показывает необычность измеренных признаков, "
                  "а не вероятность события или правильный ответ.",
}
DISPLAY_LO, DISPLAY_TOP = 0.0, rd.STRETCH_TOP
DISPLAY_NOTE = (
    "Настоящие экспозиции ZTF: даты, фильтр и выдержка указаны у каждого кадра. "
    "Кадры выровнены по WCS на общую сетку ICRS: север сверху, восток слева. "
    "Поток приведён к нуль-пункту 25 по MAGZP; из каждого участка вычтена медиана "
    "фона. Для всех кадров используется одна шкала asinh и условный цвет, "
    "не естественные цвета объектов. Источники не дорисованы. Атмосферное "
    "размытие (seeing), шум и ошибки калибровки не устранены: не каждое "
    "различие пикселей означает изменение самого объекта."
)


def load_manifest():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for relative, info in manifest["files"].items():
        path = OBS / relative
        if not path.is_file() or rd.sha256_file(path) != info["sha256"]:
            raise ValueError(f"Исходный файл отсутствует или изменён: {relative}")
    return manifest


def load_prepared(stem):
    provenance = json.loads((OBS / f"{stem}-provenance.json").read_text(encoding="utf-8"))
    path = OBS / provenance["archive"]
    if rd.sha256_file(path) != provenance["sha256"]:
        raise ValueError(f"Не совпадает SHA-256 подготовленных наблюдений: {path}")
    with np.load(path, allow_pickle=False) as archive:
        arrays = {key: archive[key] for key in archive.files}
    for key, array in arrays.items():
        if array.shape[-3:] != (3, rd.PATCH, rd.PATCH) or not np.isfinite(array).all():
            raise ValueError(f"Неверная форма или пропуски в {path}:{key}")
    return arrays, provenance


def subtract_background(stack):
    return stack - np.median(stack, axis=(1, 2))[:, None, None]


def field_stack(entry):
    """Align each exposure directly on the physical target, not download center."""
    epochs = sorted(entry["epochs"], key=lambda epoch: epoch["mjd"])
    frames = [rd.load_fits(OBS / epoch["file"]) for epoch in epochs]
    center = tuple(entry.get("patch_center", (entry["ra"], entry["dec"])))
    scale = rd.pixel_scale(frames[0][1])
    target = rd.target_wcs(*center, scale, n=rd.PATCH)
    game = np.stack([rd.align_epoch(rd.calibrate(data, header["MAGZP"]),
                                    header, target, n=rd.PATCH)
                     for data, header in frames])
    if not np.isfinite(game).all():
        raise ValueError(f"Неполный наблюдаемый участок: {center}")
    return subtract_background(game), scale, center


def observations_of(entry):
    observations = []
    for epoch in sorted(entry["epochs"], key=lambda item: item["mjd"]):
        header, row = epoch["header"], epoch["row"]
        observations.append({
            "date": rd.utc_iso_from_mjd(epoch["mjd"]), "mjd": epoch["mjd"],
            "filter": header["filter"].replace("ZTF_", ""),
            "exposure": float(header["exptime"]),
            "source": epoch["url"].split("?")[0],
            "field": int(row["field"]), "ccdid": int(row["ccdid"]),
            "qid": int(row["qid"]), "seeing": float(header["seeing"]),
            "maglim": float(header["maglim"]),
        })
    return observations


def acknowledgment(survey, observations):
    phases = set(1 if o["date"] < "2020-12-01" else 2 for o in observations)
    return " ".join(survey[f"phase{phase}"] for phase in sorted(phases))


def features_of(game):
    return rd.features(game[0], game[1])[0]


def display_constants(train):
    # One shared display, learned from training only; never stretch each epoch separately.
    return 0.0, float(np.round(np.percentile(train, 99.9), 1))


def png_bytes(array):
    return rd.png_bytes(array, DISPLAY_LO, DISPLAY_TOP)


def measured_photometry(entry, game):
    if entry.get("measured_sources"):
        sources = entry["measured_sources"]
        return {"note": "Потоки ярких звёзд: апертура 6 px, фон из кольца 10–15 px, "
                        "общий нуль-пункт 25. Это не точная модель PSF.",
                "epochs": [{"source_fluxes": [round(source["flux"][i], 6)
                                               for source in sources]} for i in range(3)]}
    if entry.get("photometry_alerce"):
        return {"note": entry["magpsf_note"],
                "epochs": sorted(entry["photometry_alerce"], key=lambda p: p["mjd_frame"])}
    if entry.get("epoch_mags"):
        return {"note": entry["mag_note"], "epochs": entry["epoch_mags"]}
    return None


def make_case(cid, name, game, center, label, entry, survey, medians, scale,
              context_key=None, pixel_scale=None):
    features = features_of(game)
    deviations = (features - medians) / scale
    observations = observations_of(entry)
    case = {
        "id": cid, "name": name, "type": label,
        "frames": rd.frames_data_uris(game, DISPLAY_LO, DISPLAY_TOP),
        "features": {"max_diff": round(float(features[0]), 6),
                     "area": int(features[1]), "peak": round(float(features[2]), 6)},
        "z": [round(float(value), 6) for value in deviations],
        "score": round(float(np.max(deviations)), 6),
        "ra": float(center[0]), "dec": float(center[1]),
        "expectedVerdict": VERDICTS[label],
        "explanation": fc.EXPLANATIONS[context_key] if context_key else EXPLANATIONS[label],
        "evidence": entry["evidence"], "limitations": entry["limitations"],
        "observations": observations,
        "source": {"label": survey["name"], "url": survey["release_page"],
                   "credit": acknowledgment(survey, observations)},
    }
    if context_key is not None:
        case["skyContext"] = fc.sky_context(context_key, case["ra"], case["dec"],
                                            pixel_scale)
    if entry.get("catalog_id"):
        case["catalogId"] = entry["catalog_id"]
    for key in ("mask_evidence", "skybot", "motion_evidence"):
        if entry.get(key):
            case[key] = entry[key]
    photometry = measured_photometry(entry, game)
    if photometry is not None:
        if len(photometry["epochs"]) != 3:
            raise ValueError(f"Фотометрия не соответствует трём кадрам: {cid}")
        case["photometry"] = photometry
    return case


def build_game_data():
    manifest = load_manifest()
    prepared, demo_provenance = load_prepared("demo")
    curated, curated_provenance = load_prepared("curated")
    demo_games, training = prepared["demo"], prepared["train"]
    if demo_games.shape[0] != 200 or training.shape[0] != 300:
        raise ValueError("Нужны 200 демонстрационных и 300 обучающих участков")
    for role, array in (("demo", demo_games), ("train", training)):
        if len(demo_provenance[role]) != len(array):
            raise ValueError(f"Несогласованный список участков: {role}")
    rows = np.array([features_of(game) for game in training])
    medians, p99 = np.median(rows, axis=0), np.percentile(rows, 99, axis=0)
    scale = p99 - medians
    if np.any(scale <= 0):
        raise ValueError("Обучающие признаки не задают ненулевой масштаб")
    global DISPLAY_LO, DISPLAY_TOP
    DISPLAY_LO, DISPLAY_TOP = display_constants(training)

    entries = manifest["cases"]
    expected = Counter(CONTACT_LAYOUT)
    actual = Counter(entry["label"] for entry in entries.values())
    if actual != expected:
        raise ValueError(f"Неполный контактный набор: {dict(actual)}; нужно {dict(expected)}")
    groups = {label: iter(sorted(key for key, entry in entries.items()
                                 if entry["label"] == label)) for label in expected}
    contact, images, story = [], {}, {}
    for number, label in enumerate(CONTACT_LAYOUT, 1):
        key = next(groups[label])
        entry = entries[key]
        if key in curated:
            source_entry = curated_provenance["cases"][key]
            if entry["ra"] != source_entry["ra"] or entry["dec"] != source_entry["dec"]:
                raise ValueError(f"Координаты manifest расходятся с подготовленной вырезкой: {key}")
            game = curated[key]
            center = (source_entry["ra"], source_entry["dec"])
            pixel_scale = float(entry["scale_arcsec"])
        else:
            game, pixel_scale, center = field_stack(entry)
        cid = f"s{number:02d}"
        case = make_case(cid, f"Участок {number:02d}", game, center, label,
                         entry, manifest["survey"], medians, scale,
                         context_key=key, pixel_scale=pixel_scale)
        contact.append(case)
        images[cid] = game
        if key == "sn2023tyk":
            story["sn2023tyk"] = cid
    if "sn2023tyk" not in story:
        raise ValueError("В контактном наборе отсутствуют наблюдения SN 2023tyk")
    short_ids, remaining = [], dict(SHORT_PLAN)
    for case in contact:
        if remaining.get(case["type"], 0):
            short_ids.append(case["id"])
            remaining[case["type"]] -= 1
    demo = []
    for number, (game, original) in enumerate(zip(demo_games, demo_provenance["demo"]), 1):
        entry = {**original,
                 "evidence": "Три экспозиции одного участка ZTF, поле 872, CCD 10, q3; "
                             "7 и 29 октября, 10 ноября 2023 года. Физическая природа "
                             "возможных различий отдельно не установлена.",
                 "limitations": demo_provenance["limitations"]}
        demo.append(make_case(f"d{number:03d}", f"Поле {number:03d}", game,
                              (entry["ra"], entry["dec"]), "unresolved", entry,
                              manifest["survey"], medians, scale))
    # Граница контракта: явные даты UTC, допустимые вердикты и полный skyContext.
    utc_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
    verdict_values = set(VERDICTS.values())
    for case in contact + demo:
        if case["expectedVerdict"] not in verdict_values:
            raise ValueError(f"Недопустимый expectedVerdict: {case['id']}")
        for obs in case["observations"]:
            if not utc_pattern.match(obs["date"]):
                raise ValueError(f"Дата не в явном UTC: {case['id']} {obs['date']}")
    for case in contact:
        fc.validate(case.get("skyContext"), case["id"])
    manifest_sha = rd.sha256_file(MANIFEST)
    meta = {
        "game": "Архив неизвестного", "synthetic": False, "precomputed": True,
        "generator": "tools/generate_data.py: реальные наблюдения ZTF",
        "dataset": {"manifest": str(MANIFEST.relative_to(ROOT)),
                    "manifest_sha256": manifest_sha, "survey": manifest["survey"]["name"],
                    "pipeline": DISPLAY_NOTE,
                    "demo_provenance": "assets/observations/demo-provenance.json",
                    "curated_provenance": "assets/observations/curated-provenance.json",
                    "distinct_contact_fields": len({obs["field"] for case in contact
                                                     for obs in case["observations"]}),
                    "demo_field_count": 1},
        "training": {"n_rows": len(rows), "rule": demo_provenance["split"],
                     "limitations": demo_provenance["limitations"],
                     "digest": hashlib.sha256(memoryview(training)).hexdigest()},
        "train_stats": {"medians": np.round(medians, 6).tolist(),
                        "p99": np.round(p99, 6).tolist(), "rows": np.round(rows, 6).tolist()},
        "feature_names": list(FEATURES), "feature_labels": FEATURE_RU,
        "score_formula": "score = maxᵢ [(fᵢ − medianᵢ) / (p99ᵢ − medianᵢ)]; "
                         "median и p99 вычислены по 300 реальным обучающим участкам",
        "thresholds": {"soft": THRESH_SOFT, "strict": THRESH_STRICT},
        "display": {"stretch": "asinh", "alpha": rd.STRETCH_ALPHA,
                    "top": DISPLAY_TOP, "lo": DISPLAY_LO,
                    "stops_rgb": rd.STRETCH_STOPS, "note": DISPLAY_NOTE},
        "patch": {"w": rd.PATCH, "h": rd.PATCH, "epochs": 3, "format": "png"},
        "calibration": {"zero_point": rd.CAL_ZP,
                        "rule": "DN × 10^(−0.4·(MAGZP − 25)); WCS TAN ICRS, "
                                "билинейная интерполяция, медиана фона каждого кадра вычтена"},
        "counts": {"train": len(rows), "contact": len(contact), "demo": len(demo),
                   "short": len(short_ids)},
        "composition": dict(Counter(case["type"] for case in contact)),
        "short_composition": dict(Counter(case["type"] for case in contact
                                          if case["id"] in short_ids)),
        "storyCases": story,
        "acknowledgments": {"ztf_phase1": manifest["survey"]["phase1"],
                            "ztf_phase2": manifest["survey"]["phase2"],
                            "citation_masci": manifest["survey"]["citation_masci"],
                            "citation_alerce": manifest["survey"]["citation_alerce"],
                            "citation_skybot": manifest["survey"]["citation_skybot"]},
    }
    return {"meta": meta, "contact": contact, "demo": demo, "shortIds": short_ids}, images


def render_js(data):
    return ("// Реальные наблюдения ZTF; воспроизводимо из проверенного FITS-кэша.\n"
            "window.GAME_DATA = " + json.dumps(data, ensure_ascii=False,
                                               separators=(",", ":"), allow_nan=False) + ";\n")


def main():
    parser = argparse.ArgumentParser(description="Build GAME_DATA from real ZTF observations")
    parser.add_argument("--out", default="app/data.js")
    args = parser.parse_args()
    data, _images = build_game_data()
    destination = Path(args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_js(data), encoding="utf-8")
    print(f"GAME_DATA: {destination}, {destination.stat().st_size} bytes")
    print(json.dumps(data["meta"]["counts"], ensure_ascii=False))
    for case in data["contact"]:
        print(case["id"], case["type"], round(case["score"], 3), case["ra"], case["dec"])


if __name__ == "__main__":
    main()
