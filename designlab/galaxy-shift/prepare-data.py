#!/usr/bin/env python3
"""Build the local, fully precomputed experiment table for Galaxy Shift.

The input files are the unmodified ESA/Hubble screensize JPEGs listed below.
This program deliberately has no network access: source pages and image files must
already have been admitted to assets/galaxies.  It uses a deterministic 24x24
grayscale centre-crop feature and 1-nearest-neighbour classification.  The
features are pixels, not a hand-authored morphology score.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import argparse
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets" / "galaxies"
DATA_VERSION = "2026-10-06-hubble-15-v1"
# Admission locks for the exact ESA/Hubble screensize files.  These are
# independent of generated provenance, so rebuilding cannot bless a changed JPEG.
EXPECTED_SOURCE_SHA256 = {
    "heic1508a.jpg": "407c0906cd5a81a1c5c7ca09aa06906e3190f44ad0126818bb0adaa63cdcc205",
    "potw1905a.jpg": "28270014f69d5e5b7cb262ffb6dbfd35c468de8ee78c3f361ac8fa5e78c27951",
    "potw2342a.jpg": "841cd27ceedba7b2f60c07cab115dd22a8f8a7464f91ac1c154ab511473ed620",
    "potw1512a.jpg": "7ca8e569ecf6c8052d8a2c8f25bebfc6027a79369e495e872f075dcdfd5a905c",
    "potw1546a.jpg": "3f8af226a2a3cb65afb003d706c45efd9b138b6e0a3ab7ab58bbe5f33d1126b0",
    "potw1237a.jpg": "89f8bdfcdccf70ff4802f3d123438417b8988c5de8095e4855460babc44a122d",
    "potw2203a.jpg": "851cc045558852ef22dd0769df01dddc391de55fc97d520ad4acb2b2a51279f4",
    "potw2008a.jpg": "2d6885f3cdbc397610745e6e4364e93b25ddcf546d97403a5954430e10b25ea8",
    "potw1129a.jpg": "9a3793256c8f24fd8db5b4ccf5ea126e5721fb251ab51e10092842c48742490c",
    "potw1911a.jpg": "c284ff3261d06ef9f3fa7417bcf98d37c656e06a3355cec97067689a781005f4",
    "opo1036a.jpg": "f4d9a89eae758ca3ff1a9a2c2c7c6ddcf77d204314c9740b743c83715a641429",
    "potw1443a.jpg": "945a118afbf0b43edae7c69e8996e567ca7d12274bbba00fd1c0babc72d9137a",
    "potw1548a.jpg": "c12cb61bf31f67a3a33051f5a2ffb5814a202aabb87a6a7dac37b6ff76cf6f29",
    "potw1619a.jpg": "3aae7e8611a8e8218aac1c175b31e7bdabc22401479b27ec2c1bd0f73a59baf2",
    "potw1119a.jpg": "cd2e0fdd8670c22c2ea31e790648ae956e4fe36555a81858064dcafb27f08c0d",
}
CLASSES = [
    {"id": "smooth", "label": "Гладкая", "hint": "Ровное светящееся пятно без заметных рукавов."},
    {"id": "spiral", "label": "Видна спираль", "hint": "От центра расходятся закрученные рукава."},
    {"id": "edge_on", "label": "Диск с ребра", "hint": "Диск виден сбоку как тонкая полоса."},
]

# Each source and credit is copied/paraphrased from the linked primary ESA/Hubble
# page.  `label` is a deliberately broad classroom visual category, not a fresh
# expert morphological classification of the object.
ITEMS = [
    ("tutorial_ic2006", "IC 2006", "heic1508a", "smooth", "train", "tutorial", "Эллиптическая галактика: ровное овальное свечение.", "ESA/Hubble & NASA. Image acknowledgement: Judy Schmidt and J. Blakeslee (Dominion Astrophysical Observatory). Science acknowledgement: M. Carollo (ETH, Switzerland)."),
    ("child_m85", "Messier 85", "potw1905a", "smooth", "train", "child", "Для игры: гладкое овальное свечение без видимых рукавов.", "ESA/Hubble & NASA, R. O'Connell."),
    ("child_ic5332", "IC 5332", "potw2342a", "spiral", "train", "child", "На почти фронтальном диске хорошо видны закрученные рукава.", "ESA/Hubble & NASA, R. Chandar, J. Lee and the PHANGS-HST team."),
    ("child_ngc5023", "NGC 5023", "potw1512a", "edge_on", "train", "child", "ESA/Hubble прямо описывает этот спиральный диск как видимый с ребра.", "ESA/Hubble & NASA."),
    ("old_ngc3610", "NGC 3610", "potw1546a", "smooth", "train", "old", "Эллиптическая галактика; для урока старая подпись намеренно неверна.", "ESA/Hubble & NASA; acknowledgement: Judy Schmidt (Geckzilla)."),
    ("old_ngc7090", "NGC 7090", "potw1237a", "edge_on", "train", "old", "ESA/Hubble прямо называет NGC 7090 галактикой, видимой с ребра; для урока старая подпись намеренно неверна.", "ESA/Hubble & NASA. Acknowledgement: R. Tugral."),
    ("fixed_ngc3318", "NGC 3318", "potw2203a", "spiral", "train", "fixed", "На снимке видны спиральные рукава NGC 3318.", "ESA/Hubble & NASA, ESO, R. J. Foley; acknowledgement: R. Colombari."),
    ("fixed_ngc691", "NGC 691", "potw2008a", "spiral", "train", "fixed", "ESA/Hubble описывает NGC 691 как характерную спиральную галактику.", "ESA/Hubble & NASA, A. Riess et al."),
    ("fixed_ic755", "IC 755", "potw1129a", "edge_on", "train", "fixed", "ESA/Hubble описывает IC 755 как спиральную галактику, которую мы видим с ребра.", "ESA/Hubble & NASA."),
    ("review_m49", "Messier 49", "potw1911a", "smooth", "review", "review", "Гладкая эллиптическая галактика; ответ хранится для повторной учебной проверки.", "ESA/Hubble & NASA, J. Blakenslee, P Cote et al."),
    ("review_ngc3982", "NGC 3982", "opo1036a", "spiral", "review", "review", "Фронтальная спиральная галактика с заметными рукавами.", "NASA, ESA, and the Hubble Heritage Team (STScI/AURA)."),
    ("review_ngc4762", "NGC 4762", "potw1443a", "edge_on", "review", "review", "ESA/Hubble описывает яркую полосу как вид с ребра; ответ повторно используется в сравнении.", "ESA/Hubble & NASA."),
    ("final_ngc2768", "NGC 2768", "potw1548a", "smooth", "final", "final", "Эллиптическая галактика с мягким овальным профилем.", "ESA/Hubble, NASA and S. Smartt (Queen's University Belfast)."),
    ("final_ngc6814", "NGC 6814", "potw1619a", "spiral", "final", "final", "ESA/Hubble называет NGC 6814 фронтальной спиральной галактикой.", "ESA/Hubble & NASA. Acknowledgement: Judy Schmidt (Geckzilla)."),
    ("final_ngc5775", "NGC 5775", "potw1119a", "edge_on", "final", "final", "ESA/Hubble описывает тонкий профиль NGC 5775 как наблюдаемый с ребра.", "ESA/Hubble & NASA."),
]

EDITABLE_IDS = ["child_m85", "child_ic5332", "child_ngc5023", "old_ngc3610", "old_ngc7090"]
CHILD_IDS = EDITABLE_IDS[:3]
OLD_IDS = EDITABLE_IDS[3:]
INITIAL_OLD_LABELS = {"old_ngc3610": "spiral", "old_ngc7090": "smooth"}

# Short verbatim source captions/lead sentences captured from the linked primary
# pages at admission.  They identify the object and avoid inferring a label from
# a filename or from how an image happens to look.
SOURCE_CAPTIONS = {
    "tutorial_ic2006": "This NASA/ESA Hubble Space Telescope image shows an elliptical galaxy known as IC 2006.",
    "child_m85": "This atmospheric image shows a galaxy named Messier 85, captured in all its delicate, hazy glory by the NASA/ESA Hubble Space Telescope.",
    "child_ic5332": "This glittering image shows the spiral galaxy IC 5332, which has an almost face-on orientation to Earth.",
    "child_ngc5023": "This NASA/ESA Hubble Space Telescope image shows an edge-on view of the spiral galaxy NGC 5023.",
    "old_ngc3610": "At the centre of this amazing image is the elliptical galaxy NGC 3610.",
    "old_ngc7090": "This image portrays a beautiful view of the galaxy NGC 7090; the galaxy is viewed edge-on from the Earth.",
    "fixed_ngc3318": "The spiral arms of the galaxy NGC 3318 are lazily draped across this image from the NASA/ESA Hubble Space Telescope.",
    "fixed_ngc691": "This image of an archetypal spiral galaxy was captured by the NASA/ESA Hubble Space Telescope; the galaxy is known as NGC 691.",
    "fixed_ic755": "IC 755 is actually a spiral galaxy that we are seeing edge-on.",
    "review_m49": "This fuzzy orb of light is a giant elliptical galaxy filled with an incredible 200 billion stars.",
    "review_ngc3982": "This face-on spiral galaxy, called NGC 3982, is striking for its rich tapestry of star birth, along with its winding arms.",
    "review_ngc4762": "The bright streak slicing across the frame is an edge-on view of galaxy NGC 4762.",
    "final_ngc2768": "NGC 2768 is an elliptical galaxy in the constellation of Ursa Major.",
    "final_ngc6814": "This is demonstrated by the striking face-on spiral galaxy NGC 6814.",
    "final_ngc5775": "This NASA/ESA Hubble Space Telescope image shows the edge-on profile of the slender spiral galaxy NGC 5775.",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def feature(path: Path) -> np.ndarray:
    """Normalized greyscale pixels from a square centre crop, deterministically."""
    with Image.open(path) as opened:
        image = opened.convert("L")
        width, height = image.size
        side = int(min(width, height) * 0.75)
        left = (width - side) // 2
        top = (height - side) // 2
        image = image.crop((left, top, left + side, top + side)).resize((24, 24), Image.Resampling.LANCZOS)
    values = np.asarray(image, dtype=np.float64).reshape(-1)
    values = (values - values.mean()) / (values.std() + 1e-12)
    return values / (np.linalg.norm(values) + 1e-12)


def build() -> tuple[dict, dict]:
    admitted_files = {f"{source_id}.jpg" for _, _, source_id, *_ in ITEMS}
    actual_files = {path.name for path in ASSETS.glob("*.jpg")}
    if actual_files != admitted_files:
        unexpected = sorted(actual_files - admitted_files)
        missing = sorted(admitted_files - actual_files)
        raise RuntimeError(f"assets must be exactly the admitted set; unexpected={unexpected}, missing={missing}")
    if set(EXPECTED_SOURCE_SHA256) != admitted_files:
        raise RuntimeError("admission hash set must exactly match the admitted assets")
    for filename in sorted(admitted_files):
        expected_hash = EXPECTED_SOURCE_SHA256.get(filename)
        if expected_hash is None:
            raise RuntimeError(f"missing admission hash for {filename}")
        actual_hash = sha256(ASSETS / filename)
        if actual_hash != expected_hash:
            raise RuntimeError(f"admission hash mismatch for {filename}: expected {expected_hash}, got {actual_hash}")
    records = []
    features = {}
    provenance = {"datasetVersion": DATA_VERSION, "license": {"name": "CC BY 4.0", "url": "https://esahubble.org/copyright/"}, "images": []}
    for item_id, name, source_id, label, split, role, explanation, credit in ITEMS:
        filename = f"{source_id}.jpg"
        path = ASSETS / filename
        if not path.is_file():
            raise FileNotFoundError(path)
        features[item_id] = feature(path)
        source = f"https://esahubble.org/images/{source_id}/"
        record = {"id": item_id, "name": name, "src": f"assets/galaxies/{filename}", "label": label,
                  "explanation": explanation, "credit": credit, "source": source, "split": split,
                  "role": role, "sourceId": source_id, "sourceCaption": SOURCE_CAPTIONS[item_id]}
        records.append(record)
        provenance["images"].append({"id": item_id, "name": name, "file": filename, "sha256": sha256(path),
                                      "source": source, "credit": credit, "license": "CC BY 4.0", "split": split,
                                      "classroomLabel": label, "sourceCaption": SOURCE_CAPTIONS[item_id]})

    by_id = {record["id"]: record for record in records}
    train = [record["id"] for record in records if record["split"] == "train"]
    review = [record["id"] for record in records if record["split"] == "review"]
    final = [record["id"] for record in records if record["split"] == "final"]
    class_ids = [item["id"] for item in CLASSES]
    true_labels = {record["id"]: record["label"] for record in records}
    fixed_labels = {item_id: true_labels[item_id] for item_id in train if item_id not in EDITABLE_IDS}

    def evaluate(targets: list[str], labels: dict[str, str]) -> dict:
        predictions = []
        for target in targets:
            neighbour = min(train, key=lambda candidate: (float(np.linalg.norm(features[target] - features[candidate])), candidate))
            predictions.append({"id": target, "predicted": labels[neighbour], "expected": true_labels[target], "neighborId": neighbour})
        correct = sum(row["predicted"] == row["expected"] for row in predictions)
        return {"predictions": predictions, "correct": correct, "total": len(predictions)}

    experiments = {}
    for indices in itertools.product(range(len(class_ids)), repeat=len(EDITABLE_IDS)):
        key = "".join(map(str, indices))
        labels = dict(fixed_labels)
        labels.update({item_id: class_ids[index] for item_id, index in zip(EDITABLE_IDS, indices)})
        experiments[key] = {"key": key, "review": evaluate(review, labels), "final": evaluate(final, labels)}

    data = {
        "datasetVersion": DATA_VERSION,
        "classes": CLASSES,
        "images": records,
        "editableIds": EDITABLE_IDS,
        "childIds": CHILD_IDS,
        "oldIds": OLD_IDS,
        "initialOldLabels": INITIAL_OLD_LABELS,
        "tutorialId": "tutorial_ic2006",
        "model": {"name": "1-ближайший сосед по пикселям", "description": "Заранее рассчитанный 1-NN по нормализованным серым пикселям центрального фрагмента 24×24. Это учебная модель изображений, не CNN и не живая тренировка."},
        "protocol": {"feature": "24x24 grayscale crop from the central 75% square; per-image z-normalization; L2 distance", "selection": "The 75% centre crop is fixed for this episode. An audit recalculated leave-one-out on the nine training objects for raw grayscale crops: 100%=3/9, 90%=3/9, 75%=4/9, 60%=4/9, 45%=6/9. Therefore this package does not claim that 75% was selected as the best score; review/final predictions were not used in that recalculation.", "trainingIds": train, "reviewIds": review, "finalIds": final, "states": len(experiments), "seed": None,
                     "note": "Разбиение и метод зафиксированы до первого просмотра итоговой подборки. Проверочная подборка выбрана как учебная демонстрация и повторно используется для сравнения, поэтому не является независимой оценкой."},
        "experiments": experiments,
    }
    return data, provenance


def checked_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="rebuild in memory and compare data.js/provenance.json without writing")
    args = parser.parse_args()
    data, provenance = build()
    data_text = "// Generated by prepare-data.py; do not edit by hand.\n" + "globalThis.GALAXY_DATA = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"
    provenance_text = json.dumps(provenance, ensure_ascii=False, indent=2) + "\n"
    if args.check:
        mismatches = [str(path.name) for path, expected in ((ROOT / "data.js", data_text), (ROOT / "provenance.json", provenance_text)) if not path.is_file() or checked_text(path) != expected]
        if mismatches:
            raise SystemExit("generated files differ: " + ", ".join(mismatches))
        if len(data["images"]) != 15 or len(data["experiments"]) != 243:
            raise SystemExit("unexpected package dimensions")
        print("check passed: 15 images, 9 train / 3 review / 3 final, 243 states, admission hashes verified")
        return
    (ROOT / "data.js").write_text(data_text, encoding="utf-8")
    (ROOT / "provenance.json").write_text(provenance_text, encoding="utf-8")
    print(f"wrote 243 states for {len(data['images'])} images")


if __name__ == "__main__":
    main()
