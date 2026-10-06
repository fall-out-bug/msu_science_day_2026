#!/usr/bin/env python3
"""Export the four existing, hash-verified ZTF FITS products; no downloads."""
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit, parse_qs

import numpy as np
from astropy.io import fits

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools import realdata as rd

HERE = Path(__file__).resolve().parent
INPUT = ROOT / 'assets/discoveries'


def main():
    provenance_file = INPUT / 'provenance.json'
    provenance = json.loads(provenance_file.read_text())['sn2023tyk']
    # Use the archived cutout center, not another generated app asset.
    centers = {parse_qs(urlsplit(entry['url']).query)['center'][0] for entry in provenance['sources']}
    if len(centers) != 1:
        raise ValueError('All cutouts must use one documented sky center')
    ra, dec = map(float, centers.pop().split(','))
    scale = 1.01286  # Same grid as the existing tools/prepare_discoveries.py export.
    target = rd.target_wcs(ra, dec, scale, n=128)
    by_date, verified = {}, []
    for entry in provenance['sources']:
        source = INPUT / entry['file']
        actual = rd.sha256_file(source)
        if actual != entry['sha256']:
            raise ValueError(f'Hash mismatch: {source.name}')
        product = entry['product']
        if product not in ('science', 'difference'):
            raise ValueError(f'Unexpected FITS product: {product}')
        with fits.open(source, memmap=False) as hdus:
            hdu = hdus[0 if product == 'science' else 1]
            image = rd.align_epoch(rd.calibrate(hdu.data, hdu.header['MAGZP']),
                                   hdu.header, target, n=128)
            date = rd.utc_iso_from_mjd(float(hdu.header['OBSJD']) - 2400000.5)
            if date != entry['date'] or not np.isfinite(image).all():
                raise ValueError(f'Invalid date or coverage: {source.name}')
            if product == 'science':
                image = image - np.median(image)
            if product in by_date.setdefault(date, {}):
                raise ValueError(f'Duplicate {product} at {date}')
            by_date[date][product] = image
            verified.append(dict(file=str(source.relative_to(ROOT)), sha256=actual,
                                 product=product, date=date, magzp=float(hdu.header['MAGZP']),
                                 source=entry['url'].split('?')[0]))
    dates = sorted(by_date)
    if len(dates) != 2 or len(verified) != 4 or any(set(by_date[d]) != {'science', 'difference'} for d in dates):
        raise ValueError('Expected two science and two genuine pipeline-difference products')
    science = [by_date[d]['science'] for d in dates]
    difference = [by_date[d]['difference'] for d in dates]
    data = dict(id='brightness-01', name='Участок 04', source='Архив ZTF / IRSA',
        dates=dates, arrays=[a.reshape(-1).tolist() for a in science],
        differenceArrays=[a.reshape(-1).tolist() for a in difference],
        sources=[[dict(x=x, y=y, peak=peak) for x, y, peak in rd.detect_sources(a, k=5)] for a in science],
        displayTop=300, differenceDisplayTop=120,
        noise=max(rd.robust_sigma(a) for a in science),
        differenceNoise=max(rd.robust_sigma(a) for a in difference),
        fluxUnits='relative aperture flux at photometric zero point 25',
        historical=dict(name='SN 2023tyk', point=dict(x=63.5, y=63.5),
            associationRadiusPx=4, ra=ra, dec=dec, blendSeparationArcsec=2.4,
            note='Historical position, not a detection or a resolved component; nearby light is blended.',
            localEvidence='docs/nightshift-evidence.md'),
        provenance='brightness-provenance.json')
    output = HERE / 'brightness-data.js'
    output.write_text('window.BRIGHTNESS_DATA = ' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';\n')
    report = dict(inputs=verified, inputProvenanceSha256=rd.sha256_file(provenance_file),
        exportedDataSha256=rd.sha256_file(output),
        independentApertureChecks=[dict(point=dict(x=s['x'], y=s['y']),
            scienceFlux=[rd.aperture_flux(a, s['x'], s['y'], r=4, ann=(8, 12))[0] for a in science],
            differenceFlux=[rd.aperture_flux(a, s['x'], s['y'], r=4, ann=(8, 12))[0] for a in difference])
            for s in data['sources'][0] if 12 <= s['x'] <= 115 and 12 <= s['y'] <= 115],
        coordinateContract='128x128, zero-based pixel centers; x right, y down; ICRS north up east left',
        grid=dict(ra=ra, dec=dec, pixelScaleArcsec=scale),
        processing='Verify stored FITS SHA-256; MAGZP calibration to zero point 25; bilinear WCS alignment. Science median background removed; pipeline difference signs retained.',
        sourceDetection='realdata.detect_sources(k=5), raw calibrated science in each epoch; no target snapping',
        display=dict(scienceTop=300, differenceTop=120, fixedAcrossEpochs=True),
        photometry=dict(apertureRadiusPx=4, backgroundAnnulusPx=[8, 12],
            localBackground='median of annulus',
            noiseScale='1.4826*annulus MAD*sqrt(aperture pixel count)*3; correlation proxy, not a formal error bar',
            fadingRule='First difference flux >5 noise scales, decrease >5 combined noise scales, >=35% of first difference flux, and >10% of first science aperture flux.',
            stabilityRule='Science flux >5 noise scales in both epochs, science change <=10%, and absolute pipeline difference flux <=5% of first science flux in both epochs.',
            incompleteAnnulus='unresolved'),
        limits=['Two archived epochs only, no third observation.',
            'Pipeline difference is science minus a ZTF reference, not second epoch minus first.',
            'Aperture integrates nearby unresolved light; SN has a neighbour approximately 2.4 arcsec away.',
            'Noise scale is a conservative heuristic, not calibrated statistical confidence; PSF and subtraction systematics remain.',
            'Stable means no large change under these fixed gates, not proof of exact constancy.',
            'No transient type, physical luminosity, orbital property or independent discovery is inferred.'])
    (HERE / 'brightness-provenance.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(dates=dates, verifiedFiles=len(verified), sciencePeaks=data['sources'], dataBytes=output.stat().st_size)))


if __name__ == '__main__':
    main()
