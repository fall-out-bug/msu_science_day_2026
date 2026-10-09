#!/usr/bin/env python3
"""Repeat three label states for every architecture against the stored results."""
import concurrent.futures
import importlib.util
import json
import multiprocessing
import os
import sys
from pathlib import Path
for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[name]='1'
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('generator',HERE/'generate_cnn_experiments.py')
generator=importlib.util.module_from_spec(spec)
# ProcessPoolExecutor pickles functions by module name, including with fork.
sys.modules[spec.name]=generator
spec.loader.exec_module(generator)
generator.CONTEXT=generator.context()

def main():
    table=json.loads((HERE/'cnn-experiments.json').read_text())
    assert table['protocol']==generator.protocol(generator.CONTEXT)
    assert table['source']=={'protocolSha256':generator.sha(HERE/'protocol.json'),'cnnPrepareSha256':generator.sha(HERE.parent.parent/'cnn-prepare.py'),'generatorSha256':generator.sha(HERE/'generate_cnn_experiments.py')}
    data=generator.CONTEXT
    corrected=''.join(str(data['classes'].index(data['canonical'][item_id])) for item_id in data['editable'])
    initial=dict(data['canonical']);initial.update(data['records']['initialOldLabels'])
    original=''.join(str(data['classes'].index(initial[item_id])) for item_id in data['editable'])
    keys=list(dict.fromkeys([corrected,original,'2222222']))
    jobs=[(key,architecture) for architecture in table['protocol']['architectures'] for key in keys]
    checked=[]
    with concurrent.futures.ProcessPoolExecutor(max_workers=2,mp_context=multiprocessing.get_context('fork')) as pool:
        for architecture,key,run in pool.map(generator.one,jobs):
            run.pop('_elapsed')
            assert run==table['experiments'][architecture][key],(architecture,key)
            checked.append({'architecture':architecture,'labelKey':key})
    print(json.dumps({'status':'PASS','checks':len(checked),'repeat':'exact equality of all serialized scientific fields','runs':checked}))

if __name__=='__main__':main()
