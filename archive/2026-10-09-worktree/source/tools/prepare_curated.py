#!/usr/bin/env python3
"""Четыре спокойных поля и две помехи из отдельного CCD-квадранта ZTF.

Помехи подтверждены битовой маской инструмента, а не оценкой нашего детектора.
«Спокойное» означает только отсутствие заметной перемены в этих трёх кадрах.
"""
import json
from pathlib import Path
from urllib.request import urlopen

import numpy as np
from astropy.io import fits

from prepare_demo import (OUT, RAW, SCALE, SIZE, extract_patch, fetch_frames,
                          patch_wcs, sha256)
import realdata as rd

ARTIFACTS = (
    ("artifact_track", 149.79644206730438, 84.98907638130306, 0, 0),
    ("artifact_spike", 146.83351456241513, 84.85635965750912, 1, 7),
)
BAD_BITS = 65535 ^ (2 | 2048)  # source detections themselves are not defects


def masks_for(epochs):
    arrays, sources = [], []
    for epoch in epochs:
        path = OUT / epoch["file"].replace("sciimg", "mskimg")
        url = epoch["url"].replace("sciimg", "mskimg")
        if not path.exists():
            temporary = path.with_suffix(".download")
            with urlopen(url, timeout=180) as response, temporary.open("wb") as out:
                while block := response.read(1024 * 1024):
                    out.write(block)
            temporary.replace(path)
        with fits.open(path, memmap=False) as hdus:
            arrays.append(np.asarray(hdus[0].data, dtype=np.uint16))
            definitions = {str(bit): hdus[0].header.comments[f"BIT{bit:02d}"]
                           for bit in range(16)}
        sources.append({"file": str(path.relative_to(OUT)), "url": url,
                        "sha256": sha256(path), "bits": definitions})
    return arrays, sources


def mask_counts(frames, masks, ra, dec):
    yy, xx = np.mgrid[:SIZE, :SIZE]
    world = patch_wcs(ra, dec).all_pix2world(xx, yy, 0)
    counts = []
    for (data, native), mask in zip(frames, masks):
        px, py = native.all_world2pix(*world, 0)
        lo = np.floor(py).astype(int) * data.shape[1] + np.floor(px).astype(int)
        pixels = np.unique(np.concatenate([lo.ravel() + offset
            for offset in (0, 1, data.shape[1], data.shape[1] + 1)]))
        values = mask.ravel()[pixels]
        counts.append({str(b): int(np.sum((values & (1 << b)) != 0))
                       for b in range(16)})
    return counts


def overlaps(boxes, previous):
    return any(a[0] <= b[2] and b[0] <= a[2] and
               a[1] <= b[3] and b[1] <= a[3]
               for other in previous for a, b in zip(boxes, other))


def flux_measurements(game):
    measurements = []
    sigma = rd.robust_sigma(game[0])
    for x, y, amplitude in rd.detect_sources(game[0], k=8):
        if not 16 < x < 112 or not 16 < y < 112:
            continue
        flux = [rd.aperture_flux(image, x, y, r=6, ann=(10, 15))[0]
                for image in game]
        if min(flux) < 30 * sigma * np.sqrt(np.pi * 36):
            continue
        measurements.append({"x": x, "y": y, "flux": flux,
                             "span": float((max(flux) - min(flux)) / np.median(flux))})
    return measurements


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    frames, epochs = fetch_frames(2)
    masks, mask_sources = masks_for(epochs)
    cases, arrays, footprints = {}, {}, []
    for key, ra, dec, epoch, bit in ARTIFACTS:
        extracted = extract_patch(frames, ra, dec)
        if extracted is None:
            raise RuntimeError(f"Неполная вырезка {key}")
        game, boxes, backgrounds = extracted
        counts = mask_counts(frames, masks, ra, dec)
        if counts[epoch][str(bit)] == 0 or overlaps(boxes, footprints):
            raise RuntimeError(f"Нет независимого подтверждения/пересечение: {key}")
        footprints.append(boxes)
        if bit == 0:
            name = "ZTF 872–05"
            evidence = ("На снимке 7 октября виден длинный след; на снимках 29 октября "
                        "и 10 ноября его нет. Исходная маска ZTF помечает этот след "
                        "битом 0: AIRCRAFT/SATELLITE TRACK — след самолёта или спутника.")
            limitations = "Эта маска не позволяет отличить самолёт от спутника или назвать аппарат."
        else:
            name = "ZTF 872–06"
            evidence = ("В центре снимка 29 октября появился узкий всплеск, отсутствующий "
                        "на двух других кадрах. Исходная маска ZTF помечает пиксел "
                        "битом 7: PIXEL SPIKE (POSSIBLE RAD HIT) — возможное попадание частицы.")
            limitations = ("Метка конвейера и форма поддерживают версию помехи, "
                           "но сами по себе не устанавливают физическую причину всплеска.")
        cases[key] = {"name": name, "label": "artifact", "ra": ra, "dec": dec,
                      "scale_arcsec": SCALE, "epochs": epochs, "backgrounds": backgrounds,
                      "native_footprints": boxes, "evidence": evidence,
                      "limitations": limitations,
                      "mask_evidence": {"epoch": epoch, "bit": bit,
                                        "counts": counts, "sources": mask_sources}}
        arrays[key] = game
    candidates = []
    for y in range(180, 2860, 220):
        for x in range(180, 2860, 220):
            ra, dec = [float(v) for v in frames[0][1].all_pix2world(x, y, 0)]
            extracted = extract_patch(frames, ra, dec)
            if extracted is None:
                continue
            game, boxes, backgrounds = extracted
            if overlaps(boxes, footprints):
                continue
            bad = False
            for mask, box in zip(masks, boxes):
                x0, y0, x1, y1 = box
                if np.any(mask[int(y0):int(y1) + 2, int(x0):int(x1) + 2] & BAD_BITS):
                    bad = True
                    break
            if bad:
                continue
            measurements = flux_measurements(game)
            if len(measurements) < 2:
                continue
            span = max(m["span"] for m in measurements)
            if span > 0.10:
                continue
            candidates.append((span, ra, dec, game, boxes, backgrounds, measurements))
    candidates.sort(key=lambda row: row[0])
    for candidate in candidates:
        span, ra, dec, game, boxes, backgrounds, measurements = candidate
        if overlaps(boxes, footprints):
            continue
        number = len(cases) - len(ARTIFACTS) + 1
        key = f"normal_{number}"
        cases[key] = {"name": f"ZTF 872–{number:02d}", "label": "normal",
                      "ra": ra, "dec": dec, "scale_arcsec": SCALE,
                      "epochs": epochs, "backgrounds": backgrounds,
                      "native_footprints": boxes, "measured_sources": measurements,
                      "evidence": f"На трёх снимках звёзды остаются на тех же местах. "
                          f"У {len(measurements)} ярких источников размах апертурного потока "
                          f"не превышает {100 * span:.1f}% от медианы. "
                          "В исходной маске участка нет флагов дефектов или следов.",
                      "limitations": "Это не доказательство постоянства всех звёзд: "
                          "слабая переменность может скрываться в шуме. Разница seeing "
                          "меняет форму звёзд даже при близком полном потоке."}
        arrays[key] = game
        footprints.append(boxes)
        if number == 4:
            break
    if len(cases) != 6:
        raise RuntimeError(f"Найдено только {len(cases) - 2} пригодных спокойных полей")
    archive = OUT / "curated-fields.npz"
    np.savez_compressed(archive, **arrays)
    result = {"version": 1, "archive": archive.name, "sha256": sha256(archive),
              "cases": cases, "processing": "MAGZP25, WCS TAN north-up, 128², "
              "bilinear interpolation, per-frame median background subtraction; "
              "see prepare_demo.py. Quadrant 2 is disjoint from demo q3 / train q4."}
    (OUT / "curated-provenance.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for key, entry in cases.items():
        print(key, entry["ra"], entry["dec"], entry["evidence"])
    print(f"Saved {len(cases)} genuine disjoint fields, {archive.stat().st_size} bytes")


if __name__ == "__main__":
    main()
