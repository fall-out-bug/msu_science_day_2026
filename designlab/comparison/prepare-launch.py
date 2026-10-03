#!/usr/bin/env python3
"""Prepare a held-out observation set from hash-verified local ZTF archives.

The movement field references the existing s07 export, reserved for launch in
this journey. The variable field is newly exported from three science FITS;
it does not contain pipeline-difference images or generated astronomical pixels.
"""
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools import realdata as rd

HERE = Path(__file__).resolve().parent
OBS = ROOT / 'assets/observations'


def main():
    movement_manifest = json.loads((OBS / 'manifest.json').read_text())
    movement_inputs = []
    for epoch in movement_manifest['cases']['mover2']['epochs']:
        path = OBS / epoch['file']
        actual = rd.sha256_file(path)
        if actual != movement_manifest['files'][epoch['file']]['sha256']:
            raise ValueError(f'Hash mismatch: {path.name}')
        movement_inputs.append(dict(file=str(path.relative_to(ROOT)), sha256=actual))
    handoff_file = OBS / 'variable-fields/handoff.json'
    entry = json.loads(handoff_file.read_text())['cases']['weakmid1']
    scale = 1.01286
    grid = rd.target_wcs(entry['ra'], entry['dec'], scale)
    images, dates, inputs = [], [], []
    for epoch in entry['epochs']:
        path = OBS / epoch['file']
        actual = rd.sha256_file(path)
        if actual != epoch['sha256']:
            raise ValueError(f'Hash mismatch: {path.name}')
        raw, header = rd.load_fits(path)
        image = rd.align_epoch(rd.calibrate(raw, header['MAGZP']), header, grid)
        if not np.isfinite(image).all():
            raise ValueError(f'Incomplete coverage: {path.name}')
        background = float(np.median(image))
        image = image - background
        date = rd.utc_iso_from_mjd(float(header['OBSJD']) - 2400000.5)
        images.append(image)
        dates.append(date)
        inputs.append(dict(file=str(path.relative_to(ROOT)), sha256=actual,
                           url=epoch['url'], date=date,
                           magzp=float(header['MAGZP']), seeing=float(header['SEEING']),
                           removedMedian=background))
    if dates != sorted(dates) or len(set(dates)) != 3:
        raise ValueError('Expected three chronological observations')
    sources = [[dict(x=x, y=y, peak=peak) for x, y, peak in rd.detect_sources(a, k=5)]
               for a in images]
    data = dict(id='launch-variable', name='Поле B', source='Архив ZTF / IRSA',
                dates=dates, arrays=[a.reshape(-1).tolist() for a in images],
                sources=sources, displayTop=900,
                noise=max(rd.robust_sigma(images[i] - images[0]) for i in [1, 2]),
                fluxUnits='relative science aperture flux at photometric zero point 25',
                photometryProduct='science', provenance='launch-provenance.json')
    output = HERE / 'launch-data.js'
    output.write_text('(function(root){\n"use strict";\n'
                      'const motion=root.COMPARISON_DATA.cases.find(c=>c.id==="s07");\n'
                      'if(!motion)throw new Error("Missing held-out motion observations");\n'
                      'root.LAUNCH_DATA={cases:[{...motion,id:"launch-motion",name:"Поле A",'
                      'provenance:"launch-provenance.json",photometryProduct:"science"},'
                      + json.dumps(data, ensure_ascii=False, separators=(',', ':'))
                      + '],provenance:"launch-provenance.json"};\n'
                      '})(typeof window==="undefined"?globalThis:window);\n')
    first_checks = [dict(point=dict(x=s['x'], y=s['y']),
                         scienceFlux=[rd.aperture_flux(a, s['x'], s['y'], r=4, ann=(8, 12))[0]
                                      for a in images]) for s in sources[0]
                    if 12 <= s['x'] <= 115 and 12 <= s['y'] <= 115]
    report = dict(version=1, inputs=inputs,
        handoffSha256=rd.sha256_file(handoff_file), exportedDataSha256=rd.sha256_file(output),
        movementReference=dict(file='designlab/comparison/data.js', case='s07',
            sha256=rd.sha256_file(HERE / 'data.js'),
            provenance='designlab/comparison/provenance.json',
            provenanceSha256=rd.sha256_file(HERE / 'provenance.json'), inputs=movement_inputs,
            independence='Reserved for the current launch; movement test uses only s02. '
                         'Previously present in this project, not a claim of a never-seen field.'),
        grid=dict(ra=entry['ra'], dec=entry['dec'], pixelScaleArcsec=scale),
        coordinateContract='128x128; zero-based pixel centers; x right, y down; ICRS north up east left',
        processing='SHA-256 verification; MAGZP calibration to zero point 25; WCS bilinear '
                   'alignment; one spatial median removed per science exposure; blind '
                   'Gaussian-smoothed local maxima above 5 robust sigma. No downloads.',
        independentApertureChecks=first_checks,
        instrumentLimits=['Movement proposes matches from the first two epochs and freezes a '
                          'linear prediction; the third epoch is used only after selection.',
                          'Fading scans fixed-position science apertures in the first two '
                          'epochs. Relative field controls check large common changes; '
                          'the numeric check repeats these measurements, not independent data.',
                          'Fading gates: at least 35% decrease after field median-ratio '
                          'correction; decrease above five diagnostic noise scales, each '
                          'including a 5% flux floor or larger robust control scatter; '
                          'at least two matched positive control apertures, robust ratio '
                          'scatter at most 15%, common ratio change at most 25%. These '
                          'fixed heuristics are not a five-sigma confidence claim.',
                          'No pipeline difference images exist in this launch export.',
                          'Finite aperture, blending, seeing and calibration can bias flux; '
                          'diagnostic gates are not calibrated probabilities.',
                          'Three sparse observations cannot establish persistent decline, '
                          'period, astrophysical type, orbit, or a new discovery.',
                          'No ML or catalogue truth used by the runtime scan.'],
        historicalContext=dict(catalogId=entry['catalog_id'],
                               note='Provenance context only; not exported as a runtime target.',
                               evidence=entry['evidence'], limitations=entry['limitations']))
    (HERE / 'launch-provenance.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(cases=2, sources=[len(s) for s in sources], bytes=output.stat().st_size)))


if __name__ == '__main__':
    main()
