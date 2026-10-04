#!/usr/bin/env python3
"""Package the playable campaign using only local runtime resources."""
from pathlib import Path
import hashlib,json,zipfile
HERE=Path(__file__).resolve().parent
ASSETS=['night.css','night.js','night-model.js','data.js','model.js','tracking.js',
 'brightness-data.js','brightness-model.js','launch-data.js','launch-model.js',
 'learning-model.js','learning-data.js','archive-data.js','provenance.json',
 'brightness-provenance.json','launch-provenance.json','learning-provenance.json',
 'archive-provenance.json','NIGHT-SOURCES.txt']

def main():
    out=HERE/'releases';out.mkdir(exist_ok=True)
    sources={'index.html':HERE/'night.html',**{name:HERE/name for name in ASSETS}}
    manifest={'title':'Мастерская неба','version':'2026.10.04','entry':'index.html',
      'cases':9,'modes':[3,6,9],'files':{name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in sources.items()}}
    instructions='Мастерская неба\n\nРаспакуйте весь архив. Откройте index.html в современном браузере.\nИнтернет не нужен. Рекомендуемый первый режим — 6 исследований.\nКлик выбирает точку, кнопки под снимком переключают даты. Есть помощь и список точек для клавиатуры.\nЗвук включается кнопкой. Пауза сохраняет смену на этом устройстве, если браузер разрешает локальное хранилище.\nВ финале можно продолжить или скачать журнал.\nПеред следующим игроком выберите «Передать смену».\n\nЦелевой возраст 10–13 лет. Время самостоятельного прохождения детьми ещё не измерено.\nДанные, научные границы и благодарности — NIGHT-SOURCES.txt и файлы provenance.json.\n'
    with zipfile.ZipFile(out/'night-shift.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for name,path in sources.items():archive.write(path,name)
        archive.writestr('README.txt',instructions)
        archive.writestr('build.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    (out/'build.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'zip':str(out/'night-shift.zip'),'bytes':(out/'night-shift.zip').stat().st_size,'files':len(sources)}))
if __name__=='__main__':main()
