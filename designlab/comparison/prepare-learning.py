#!/usr/bin/env python3
"""Export a bounded learning lesson from the measured comparison detections.

This is deliberately separate from the browser model: Python computes the
reference feature vectors before the runtime replays the same formula.
"""
import hashlib, itertools, json, math
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / 'data.js'

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def stamp(value): return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp() / 3600
def generate(field, pixel_scale):
    times = [stamp(value) for value in field['dates']]
    dt = [times[1]-times[0], times[2]-times[1]]
    out = []
    for idx in itertools.product(*(range(len(epoch)) for epoch in field['sources'])):
        points = [field['sources'][epoch][n] for epoch, n in enumerate(idx)]
        velocity = [[(points[n+1]['x']-points[n]['x']) * pixel_scale / dt[n], (points[n+1]['y']-points[n]['y']) * pixel_scale / dt[n]] for n in range(2)]
        speed = [math.hypot(*vector) for vector in velocity]
        mismatch = math.hypot(velocity[1][0]-velocity[0][0], velocity[1][1]-velocity[0][1])
        feature = [math.log1p(sum(speed)/2), math.log1p(mismatch), math.log(max(p['peak'] for p in points)/min(p['peak'] for p in points))]
        out.append(dict(id=':'.join(map(str, idx)), sourceIndices=list(idx), points=[dict(x=p['x'], y=p['y'], peak=p['peak']) for p in points], feature=feature))
    return dict(caseId=field['id'], hours=[value-times[0] for value in times], candidates=out)
def find(rows, coordinates):
    for row in rows['candidates']:
        if [(p['x'],p['y']) for p in row['points']] == coordinates: return row['id']
    raise ValueError(coordinates)
def score(train, labels, query, scale):
    rows={row['id']:row for row in train['candidates']}; labeled={}
    for item in labels: labeled.setdefault(item['id'],item['label'])
    pos=[rows[key] for key,value in labeled.items() if value=='sameObject']; neg=[rows[key] for key,value in labeled.items() if value=='wrongLink']
    def d(left,right): return math.sqrt(sum(((a-b)/s)**2 for a,b,s in zip(left['feature'],right['feature'],scale)))
    return [(min(d(row,x) for x in neg)-min(d(row,x) for x in pos))/max(min(d(row,x) for x in neg)+min(d(row,x) for x in pos),1e-12) for row in query['candidates']]
def main():
    raw=json.loads(DATA.read_text().split('=',1)[1].strip().rstrip(';'))
    manifest=json.loads((HERE.parent.parent/'assets/observations/manifest.json').read_text())
    case_keys={'s02':'mover1','s07':'mover2'}
    scales={case:float(manifest['cases'][key]['epochs'][0]['header']['pixscale_as']) for case,key in case_keys.items()}
    fields={field['id']:generate(field,scales[field['id']]) for field in raw['cases'] if field['id'] in case_keys}
    train, reserved=fields['s02'],fields['s07']
    positive=find(train,[(42,82),(58,68),(91,40)])
    static=[find(train,[(x,y)]*3) for x,y in [(71,10),(2,13),(16,34),(4,45)]]
    initial=[dict(id=positive,label='sameObject')]+[dict(id=value,label='wrongLink') for value in static]
    scale=[]
    for c in range(3):
        mean=sum(row['feature'][c] for row in train['candidates'])/len(train['candidates'])
        scale.append(math.sqrt(sum((row['feature'][c]-mean)**2 for row in train['candidates'])/len(train['candidates'])) or 1)
    before=score(train,initial,reserved,scale)
    # This is a real measured triple: first two points form the confirmed track,
    # but the third point is a different detection. Its coordinates make the correction inspectable.
    correction=find(train,[(42,82),(58,68),(19,76)])
    after=score(train,initial+[dict(id=correction,label='wrongLink')],reserved,scale)
    if not next(value for row,value in zip(train['candidates'],score(train,initial,train,scale)) if row['id']==correction) > 0: raise ValueError('Chosen correction is not initially accepted')
    payload=dict(version=1, trainCase='s02', reservedCase='s07', pixelScaleArcsec=scales, initialExamples=initial,
      correction=dict(id=correction, label='wrongLink', beforeAccepted=True,
        coordinates=[dict(x=p['x'],y=p['y']) for p in next(row for row in train['candidates'] if row['id']==correction)['points']]),
      lessonLimits=dict(allThreeEpochsVisible=True, scoreIsProbability=False,
        rejectLabelMeans='reject this motion-track hypothesis, not identify an object'))
    (HERE/'learning-data.js').write_text('window.LEARNING_DATA = '+json.dumps(payload,separators=(',',':'))+';\n')
    reference=dict(fields=fields, scale=scale, beforeReservedAccepted=sum(value>0 for value in before), afterReservedAccepted=sum(value>0 for value in after))
    (HERE/'learning-reference.json').write_text(json.dumps(reference,separators=(',',':'))+'\n')
    provenance=dict(source=dict(data_js_sha256=sha(DATA), exporterSha256=sha(Path(__file__)),
        cases=['s02','s07'], coordinate_contract='zero-based 128x128 source centers; all three measured epochs are visible'),
      model=dict(features=['log1p(mean speed in arcsec/hour)','log1p(vector velocity difference in arcsec/hour)','log(max peak/min peak)'], scale='population standard deviation fitted on all s02 candidate triples only', score='nearest-negative distance minus nearest-positive distance, divided by their sum; an acceptance score, not a probability', decision='score > 0'),
      lesson=dict(initial='one confirmed s02 track and four stationary measured triples', correction='s02 42,82 -> 58,68 -> 19,76 is an initially accepted wrong association; learner labels it wrongLink', evaluation='s07 is reserved for the before/after count'),
      validation=dict(independent_python_extraction=True, runtime_must_match='learning-reference.json features and coordinates', source_tuples=[len(train['candidates']),len(reserved['candidates'])]))
    (HERE/'learning-provenance.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__': main()
