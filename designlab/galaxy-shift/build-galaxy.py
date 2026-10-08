#!/usr/bin/env python3
"""Build the offline astronomy package from an explicit runtime file list."""
import hashlib,json,zipfile,shutil,re,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
subprocess.run([sys.executable,str(HERE/'experiments/cnn-label-correction/check_constructor_table.py'),'--require-full'],check=True)
runtime=['index.html','galaxy.css','library.css','nika.css','companion.css','quest-scene.css','quest-scene.js','nika-dialogue.js','sky.css','sky.js','sky-data.js','sky-provenance.json','astronomy.js','game.js','world.js','data.js','archive-data.js','archive-catalog.json','archive-admission.json','version.js','lesson-storage.js','telemetry.js','cnn-architectures.js','cnn-results-loader.js','cnn-experiments.js','cnn-session.js','metrics.js','discovery-data.js','discovery-provenance.json','provenance.json','DATA-NOTES.md','README.md','FACILITATOR.md']
results=sorted(p.relative_to(HERE).as_posix() for p in (HERE/'cnn-results').glob('*.js'))
if len(results)!=21: raise SystemExit('The release requires exactly 21 additional CNN architecture files')
runtime += results
version=re.search(r"GALAXY_BUILD_VERSION = '([^']+)'",(HERE/'version.js').read_text()).group(1)
assets=sorted(p.relative_to(HERE).as_posix() for p in (HERE/'assets/galaxies').rglob('*.jpg'))
assets += sorted(p.relative_to(HERE).as_posix() for p in (HERE/'assets/discoveries').rglob('*') if p.is_file())
assets += ['assets/art/'+name for name in ['nika.png','observatory-night-v4.png','observatory-night-portrait-v4.png','worktop-night-v2.png','NIKA-CREDITS.md','ART-CREDITS.md','NIGHT-V2-PROMPTS.md','NIGHT-V4-PROMPTS.md','PORTRAIT-V3-PROMPT.md','NIKA-DIALOGUE-PROMPTS.md','nika-warm-v1.png','nika-curious-v1.png','nika-thinking-v1.png']]
assets += ['assets/sky/licenses/'+name for name in ['CC-BY-SA-4.0.txt','FAL-1.3.txt','GPL-2.0.txt']]
files=runtime+assets
for name in files:
 if not (HERE/name).is_file():raise SystemExit('Missing package resource: '+name)
manifest={'title':'ИИ в астрономии','version':version,'entry':'index.html','files':{name:hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in files}}
out=HERE/'releases';out.mkdir(exist_ok=True)
web=out/'web'
if web.exists():shutil.rmtree(web)
web.mkdir()
for name in files:
 target=web/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(HERE/name,target)
with zipfile.ZipFile(out/'galaxy-shift.zip','w',zipfile.ZIP_DEFLATED) as z:
 for name in files:z.write(HERE/name,name)
 z.writestr('build.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
(web/'build.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
(out/'build.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'files':len(files),'zipBytes':(out/'galaxy-shift.zip').stat().st_size,'version':manifest['version']}))
