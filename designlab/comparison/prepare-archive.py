#!/usr/bin/env python3
"""Export four additional, locally cached ZTF investigation windows.

This is deliberately an exporter, not a case generator: every input FITS is
listed in assets/observations/manifest.json and hash-checked before WCS
alignment.  The four cases are different 128px sky windows; the two polar
windows share three archive exposures, which is recorded in provenance.
"""
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools import realdata as rd

HERE = Path(__file__).resolve().parent
OBS = ROOT / "assets" / "observations"

# New investigation windows only.  Existing campaign fields are s02 (mover1),
# s07 (mover2), s04 (artifact_spike), SN 2023tyk and weakmid1.
CASES = (
    ("archive-brightening", "variable1", "Поле C", "brightness_increased"),
    ("archive-small-change", "weak1", "Поле D", "small_measured_change"),
    ("archive-steady", "normal_1", "Поле E", "no_large_change"),
    ("archive-track", "artifact_track", "Поле F", "one_epoch_track"),
)


def field_stack(entry):
    """Apply the same calibrated WCS extraction without the legacy game generator."""
    epochs = sorted(entry['epochs'], key=lambda epoch: epoch['mjd'])
    frames = [rd.load_fits(OBS / epoch['file']) for epoch in epochs]
    center = tuple(entry.get('patch_center', (entry['ra'], entry['dec'])))
    scale = rd.pixel_scale(frames[0][1])
    target = rd.target_wcs(*center, scale, n=rd.PATCH)
    stack = np.stack([rd.align_epoch(rd.calibrate(data, header['MAGZP']), header, target, n=rd.PATCH)
                      for data, header in frames])
    if not np.isfinite(stack).all():
        raise ValueError('Incomplete observation window')
    return stack - np.median(stack, axis=(1, 2))[:, None, None], scale, center


def checked_epochs(manifest, entry):
    result = []
    for epoch in sorted(entry["epochs"], key=lambda row: row["mjd"]):
        path = OBS / epoch["file"]
        actual = rd.sha256_file(path)
        expected = manifest["files"][epoch["file"]]["sha256"]
        if actual != expected:
            raise ValueError(f"Hash mismatch: {path}")
        _, header = rd.load_fits(path)
        date = rd.utc_iso_from_mjd(epoch["mjd"])
        result.append(dict(file=str(path.relative_to(ROOT)), sha256=actual,
                           url=epoch["url"], date=date,
                           magzp=float(header["MAGZP"]), seeing=float(header["SEEING"])))
    if len(result) != 3 or [row["date"] for row in result] != sorted(row["date"] for row in result):
        raise ValueError("Expected three chronological observations")
    return result


def main():
    manifest_path = OBS / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    rows, provenance_cases = [], []
    for case_id, key, name, lesson in CASES:
        entry = manifest["cases"][key]
        inputs = checked_epochs(manifest, entry)
        images, scale, center = field_stack(entry)
        if images.shape != (3, 128, 128) or not np.isfinite(images).all():
            raise ValueError(f"Invalid aligned images for {key}")
        sources = [[dict(x=x, y=y, peak=peak) for x, y, peak in rd.detect_sources(image, k=5)]
                   for image in images]
        rows.append(dict(id=case_id, name=name, source="Архив ZTF / IRSA",
                         dates=[row["date"] for row in inputs],
                         arrays=[image.reshape(-1).tolist() for image in images],
                         sources=sources, displayTop=900,
                         pixelScaleArcsec=scale, fluxUnits="relative science aperture flux at photometric zero point 25",
                         photometryProduct="science", provenance="archive-provenance.json",
                         archiveCase=key, lesson=lesson, evidence=entry["evidence"],
                         limitations=entry["limitations"]))
        aperture = [dict(point=dict(x=source["x"], y=source["y"]),
                         scienceFlux=[rd.aperture_flux(image, source["x"], source["y"], r=4, ann=(8, 12))[0]
                                      for image in images])
                    for source in sources[0]
                    if 12 <= source["x"] <= 115 and 12 <= source["y"] <= 115]
        # This is a reproducible reporting point, chosen among blind detections
        # nearest the documented patch centre.  It is not supplied to a runtime
        # detector and it does not alter any model threshold.
        candidates = [source for source in sources[0]
                      if 12 <= source["x"] <= 115 and 12 <= source["y"] <= 115]
        if not candidates:
            raise ValueError(f"No complete-aperture blind source in {key}")
        target = min(candidates, key=lambda source: (source["x"] - 63.5) ** 2 +
                     (source["y"] - 63.5) ** 2)
        target_check = dict(point=dict(x=target["x"], y=target["y"]),
                            scienceFlux=[rd.aperture_flux(image, target["x"], target["y"], r=4, ann=(8, 12))[0]
                                         for image in images])
        provenance_cases.append(dict(id=case_id, manifestCase=key, lesson=lesson,
                                     inputs=inputs, grid=dict(ra=center[0], dec=center[1],
                                     pixelScaleArcsec=scale), sourceCounts=[len(s) for s in sources],
                                     independentApertureChecks=aperture,
                                     independentTargetApertureCheck=target_check))
    output = HERE / "archive-data.js"
    output.write_text("(function(root){\n\"use strict\";\nroot.ARCHIVE_DATA=" +
                      json.dumps(dict(cases=rows, provenance="archive-provenance.json"),
                                 ensure_ascii=False, separators=(",", ":")) +
                      ";\n})(typeof window===\"undefined\"?globalThis:window);\n")
    # s04 is the existing, separate artifact-spike cutout from the same three
    # ZTF exposures.  These are distinct WCS centres, so no campaign patch is
    # duplicated even though the observing dates are shared.
    shared = [["s04", "archive-steady", "archive-track"]]
    report = dict(version=1, manifest=str(manifest_path.relative_to(ROOT)),
        manifestSha256=rd.sha256_file(manifest_path), exportedDataSha256=rd.sha256_file(output),
        cases=provenance_cases, coordinateContract="128x128; zero-based pixel centers; x right, y down; ICRS north up east left",
        processing="SHA-256 verification of local FITS; MAGZP calibration to zero point 25; WCS bilinear alignment; one spatial median removed from each science exposure; blind Gaussian-smoothed local maxima above 5 robust sigma. No downloads and no target snapping.",
        sharedExposureWindows=shared,
        limits=["Each row is an archived ZTF science exposure, not a new observation.",
                "The fields are distinct sky windows, not nine independent observing nights.",
                "The brightening and small-change cases establish only measured flux changes described in their manifest evidence; three sparse dates do not establish a period or subtype.",
                "The one-epoch track is recorded by the ZTF mask as aircraft/satellite track; it does not identify a particular craft.",
                "Blind peak detection is not an object classifier; TrackingModel, BrightnessModel and LaunchModel retain their own fixed gates."])
    (HERE / "archive-provenance.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(dict(cases=len(rows), sourceCounts=[len(row["sources"][0]) for row in rows],
                          bytes=output.stat().st_size), ensure_ascii=False))


if __name__ == "__main__":
    main()
