#!/usr/bin/env python3
"""Offline, fixed-protocol causal learning probe. Does not modify game assets."""
from __future__ import annotations

import itertools
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools import generate_data as gd
from tools import realdata as rd

HERE = Path(__file__).resolve().parent
OUT = HERE / 'results'
FEATURES = ['log1p_speed_arcsec_hour', 'log1p_velocity_difference_arcsec_hour',
            'log_peak_ratio']


def extract(entry):
    """No identity, truth, labels, or ephemerides in extraction or features."""
    images, scale, _ = gd.field_stack(entry)
    detections = [np.asarray(rd.detect_sources(frame, k=5.0)) for frame in images]
    if any(d.ndim != 2 or len(d) == 0 for d in detections):
        raise ValueError('No detections; keep failed experiment rather than lower threshold')
    indices = np.array(list(itertools.product(*(range(len(d)) for d in detections))))
    points = np.stack([d[indices[:, i], :2] for i, d in enumerate(detections)], axis=1)
    peaks = np.stack([d[indices[:, i], 2] for i, d in enumerate(detections)], axis=1)
    times = np.array(sorted(e['mjd'] for e in entry['epochs'])) * 24
    dt = np.diff(times)
    steps = np.diff(points, axis=1)
    velocity = steps * scale / dt[None, :, None]
    speed = np.linalg.norm(velocity, axis=2).mean(axis=1)
    mismatch = np.linalg.norm(velocity[:, 1] - velocity[:, 0], axis=1)
    features = np.column_stack([np.log1p(speed), np.log1p(mismatch),
                                np.log(peaks.max(axis=1) / peaks.min(axis=1))])
    fraction = dt[0] / dt.sum()
    middle = points[:, 0] + fraction * (points[:, 2] - points[:, 0])
    residual = np.linalg.norm(points[:, 1] - middle, axis=1)
    moving = (np.linalg.norm(steps, axis=2) >= 2).all(axis=1)
    geometric = np.where(moving, residual, np.inf)
    return dict(detections=detections, indices=indices, points=points,
                features=features, residual=residual, geometric=geometric,
                hours=times - times[0], scale=scale)


def identities(field, reference):
    """Evaluation/teacher labels only, kept outside extract and predict."""
    ds = field['detections']
    ids = [np.full(len(d), -1, dtype=int) for d in ds]
    truth_ids, offsets = [], []
    for epoch, d in enumerate(ds):
        distances = np.linalg.norm(d[:, :2] - reference[epoch], axis=1)
        j = int(np.argmin(distances))
        if distances[j] > 1.5 or np.sum(distances <= 1.5) != 1:
            raise ValueError('Blind detection does not uniquely recover reference target')
        truth_ids.append(j)
        offsets.append(float(distances[j]))
        ids[epoch][j] = 0
    stable = []
    for i, detection in enumerate(ds[0]):
        if ids[0][i] == 0:
            continue
        match = [i]
        for epoch in (1, 2):
            distances = np.linalg.norm(ds[epoch][:, :2] - detection[:2], axis=1)
            j = int(np.argmin(distances))
            reverse = np.linalg.norm(ds[0][:, :2] - ds[epoch][j, :2], axis=1)
            if (distances[j] > 1.5 or np.sum(distances <= 1.5) != 1
                    or int(np.argmin(reverse)) != i or np.sum(reverse <= 1.5) != 1
                    or ids[epoch][j] >= 0):
                break
            match.append(j)
        if len(match) != 3:
            continue
        if np.linalg.norm(ds[1][match[1], :2] - ds[2][match[2], :2]) > 1.5:
            continue
        identity = len(stable) + 1
        for epoch, j in enumerate(match):
            ids[epoch][j] = identity
        stable.append(match)
    track_identities = np.stack([ids[e][field['indices'][:, e]] for e in range(3)], axis=1)
    known = (track_identities >= 0).all(axis=1)
    same = (track_identities == track_identities[:, :1]).all(axis=1)
    labels = np.full(len(known), 'unknown', dtype='<U16')
    labels[known & ~same] = 'mixed_identity'
    labels[known & same] = 'stationary'
    target_mask = (field['indices'] == truth_ids).all(axis=1)
    labels[target_mask] = 'mover'
    target_index = int(np.flatnonzero(target_mask)[0])
    stable_rows = [int(np.flatnonzero((field['indices'] == row).all(axis=1))[0])
                   for row in stable]
    return dict(labels=labels, target=target_index, stable=stable_rows,
                reference_offsets_px=offsets, detection_identities=ids)


def predict(query, train, examples, scale):
    """Exemplar distance margin, no field IDs or reference data accepted."""
    positive = [i for i, label in examples if label == 1]
    negative = [i for i, label in examples if label == 0]
    if not positive or not negative:
        raise ValueError('Both classes required')
    def distance(rows):
        return np.linalg.norm((query[:, None, :] - train[rows][None, :, :]) / scale,
                              axis=2).min(axis=1)
    dp, dn = distance(positive), distance(negative)
    return (dn - dp) / np.maximum(dn + dp, 1e-12)


def ranked(scores):
    return np.lexsort((np.arange(len(scores)), -scores))


def row_report(field, truth, scores):
    order = ranked(scores)
    target = truth['target']
    labels = truth['labels']
    accepted = scores > 0
    return dict(target_rank=int(np.flatnonzero(order == target)[0]) + 1,
                target_score=float(scores[target]),
                accepted_known_false=int(np.sum(accepted & np.isin(labels, ['mixed_identity', 'stationary']))),
                accepted_unknown=int(np.sum(accepted & (labels == 'unknown'))),
                top=[dict(index=int(i), score=float(scores[i]), label=str(labels[i]),
                          positions=field['points'][i].tolist()) for i in order[:5]])


def main():
    OUT.mkdir(exist_ok=True)
    manifest = json.loads((gd.OBS / 'manifest.json').read_text())
    names = ('mover1', 'mover2')
    hashes = {str(p.relative_to(ROOT)): rd.sha256_file(p) for p in (
        gd.OBS / 'manifest.json', ROOT / 'tools/realdata.py', ROOT / 'tools/generate_data.py')}
    for name in names:
        for epoch in manifest['cases'][name]['epochs']:
            path = gd.OBS / epoch['file']
            digest = rd.sha256_file(path)
            assert digest == manifest['files'][epoch['file']]['sha256'], path
            hashes[str(path.relative_to(ROOT))] = digest
    fields = {name: extract(manifest['cases'][name]) for name in names}
    # Truth first read AFTER blind extraction of both fields.
    reference_path = gd.OBS / 'motion-fields/_research/acquire_report.json'
    reference = json.loads(reference_path.read_text())
    truths = {name: identities(fields[name], np.array([
        [r['x'], r['y']] for r in reference[name]['meas']['measured']])) for name in names}
    train = fields['mover1']['features']
    scale = train.std(axis=0)
    scale = np.where(scale > 1e-12, scale, 1)
    teacher = truths['mover1']
    stable = sorted(teacher['stable'], key=lambda i: (
        -fields['mover1']['detections'][0][fields['mover1']['indices'][i, 0], 2], i))[:4]
    initial = [(teacher['target'], 1)] + [(i, 0) for i in stable]
    initial_scores = predict(train, train, initial, scale)
    mistakes = [int(i) for i in ranked(initial_scores)
                if teacher['labels'][i] == 'mixed_identity' and initial_scores[i] > 0]
    if len(mistakes) < 2:
        raise ValueError('Fewer than two natural accepted false links; correction scene unsupported')
    a, b = mistakes[:2]
    scenarios = dict(initial=initial, correction_a=initial + [(a, 0)],
                     correction_b=initial + [(b, 0)], both=initial + [(a, 0), (b, 0)],
                     wrong_label=initial + [(a, 1)], undo=list(initial),
                     duplicate_positive=initial + [(teacher['target'], 1)])
    scores = {s: {name: predict(fields[name]['features'], train, examples, scale)
                  for name in names} for s, examples in scenarios.items()}
    checks = {}
    checks['source_hashes_verified'] = sum(p.endswith('.fits.gz') for p in hashes) == 6
    checks['undo_exact'] = all(np.array_equal(scores['initial'][n], scores['undo'][n]) for n in names)
    checks['correction_memorized'] = bool(scores['correction_a']['mover1'][a] < 0)
    checks['different_labels_different_transfer'] = not np.array_equal(
        scores['correction_a']['mover2'], scores['wrong_label']['mover2'])
    checks['two_corrections_different_transfer'] = not np.array_equal(
        scores['correction_a']['mover2'], scores['correction_b']['mover2'])
    # Export/freeze/replay uses only features, train indices, labels and train-fitted scale.
    replay = json.loads(json.dumps(dict(train=train.tolist(), scale=scale.tolist(),
        examples=scenarios['correction_a'], query=fields['mover2']['features'].tolist())))
    checks['truth_free_replay_exact'] = np.array_equal(predict(
        np.array(replay['query']), np.array(replay['train']), replay['examples'],
        np.array(replay['scale'])), scores['correction_a']['mover2'])
    checks['train_query_order_equivariant'] = np.array_equal(
        predict(fields['mover2']['features'][::-1], train, scenarios['correction_a'], scale)[::-1],
        scores['correction_a']['mover2'])
    checks['duplicate_positive_no_effect'] = all(np.array_equal(
        scores['initial'][n], scores['duplicate_positive'][n]) for n in names)
    results = {s: {n: row_report(fields[n], truths[n], scores[s][n]) for n in names} for s in scenarios}
    for s in scenarios:
        for n in names:
            delta = scores[s][n] - scores['initial'][n]
            results[s][n]['changed_scores'] = int(np.sum(np.abs(delta) > 1e-12))
            results[s][n]['changed_decisions'] = int(np.sum(
                (scores[s][n] > 0) != (scores['initial'][n] > 0)))
    baseline = {}
    for n, field in fields.items():
        order = np.argsort(field['geometric'], kind='stable')
        target = truths[n]['target']
        baseline[n] = dict(target_rank=int(np.flatnonzero(order == target)[0]) + 1,
                           target_middle_residual_px=float(field['residual'][target]),
                           top_index=int(order[0]), moving_candidates=int(np.isfinite(field['geometric']).sum()))
    report = dict(protocol='protocol.md', parameters=dict(detector_k=5, stable_tolerance_px=1.5,
                  features=FEATURES, train_scale=scale.tolist(), decision_threshold=0),
        input_sha256=hashes, reference_sha256=rd.sha256_file(reference_path),
        experiment_sha256=rd.sha256_file(Path(__file__)), protocol_sha256=rd.sha256_file(HERE / 'protocol.md'),
        fields={n: dict(detection_counts=[len(d) for d in f['detections']],
                    candidates=len(f['indices']), hours=f['hours'].tolist(),
                    labels={str(k):int(v) for k,v in zip(*np.unique(truths[n]['labels'], return_counts=True))},
                    reference_offsets_px=truths[n]['reference_offsets_px'],
                    target_index=truths[n]['target']) for n,f in fields.items()},
        examples={s:[dict(candidate=i, label=label, positions=fields['mover1']['points'][i].tolist())
                     for i,label in e] for s,e in scenarios.items()},
        checks={k:bool(v) for k,v in checks.items()}, results=results, geometric_baseline=baseline)
    (OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    (OUT / 'replay.json').write_text(json.dumps(replay, ensure_ascii=False) + '\n')
    # Complete audit rows: identities are labels only, never classifier inputs.
    for n,f in fields.items():
        rows = [dict(index=i, detections=f['indices'][i].tolist(), positions=f['points'][i].tolist(),
                     features=f['features'][i].tolist(), label=str(truths[n]['labels'][i]),
                     scores={s:float(scores[s][n][i]) for s in scenarios}) for i in range(len(f['indices']))]
        (OUT / f'{n}-candidates.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n')
    compact = dict(fields=report['fields'], checks=report['checks'], baseline=baseline,
        results={s:{n:{k:v for k,v in r.items() if k!='top'} for n,r in ns.items()} for s,ns in results.items()})
    print(json.dumps(compact, ensure_ascii=False, indent=2))
    if not all(checks.values()):
        raise SystemExit('A verification check failed; inspect evidence, do not retune the model')


if __name__ == '__main__':
    main()
