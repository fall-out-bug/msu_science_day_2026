#!/usr/bin/env python3
"""Package the playable campaign using only local runtime resources."""
from pathlib import Path
import hashlib,json,re,zipfile
HERE=Path(__file__).resolve().parent
ASSETS=['training-model.js','training-workshop.js','training.css','experience.css','room-layout.css','night-stories.js','constellation-data.js','exploration-provenance.json',
 'art/hubble-asteroids.jpg','art/hubble-supernova.jpg','vendor/FAL-1.3.txt','vendor/GPL-2.0.txt',
 'night.css','night.js','night-model.js','data.js','model.js','tracking.js',
 'brightness-data.js','brightness-model.js','launch-data.js','launch-model.js',
 'learning-model.js','learning-data.js','archive-data.js','provenance.json',
 'brightness-provenance.json','launch-provenance.json','learning-provenance.json',
 'archive-provenance.json','NIGHT-SOURCES.txt','world.css','world-room.js','world-art.js',
 'world-art-credits.md','world-targets.js','world-provenance.json','sky-navigation.js',
 'sky-navigation-data.js','sky-provenance.json','vendor/phaser.min.js',
 'vendor/PHASER-LICENSE.md','vendor/EVENTEMITTER3-LICENSE.txt','vendor/SKY-CC-BY-SA-4.0.txt',
 'art/scene-prompts.md','art/arkhyz-prompts.md','art/observatory-arkhyz-night-v1.png','art/observatory-arkhyz-dawn-v1.png','art/nika-success-v1.png']

def main():
    # The public domain previously served a different data.js. no-store cannot
    # evict a response that was already cached, so give each runtime file a
    # content-derived URL. Relative query URLs also work in the offline ZIP.
    entry=HERE/'night.html'
    def version_link(match):
        attr,name=match.groups()
        digest=hashlib.sha256((HERE/name).read_bytes()).hexdigest()[:12]
        return f'{attr}="{name}?v={digest}"'
    entry.write_text(re.sub(r'(src|href)="([^"?:]+\.(?:js|css))(?:\?v=[^" ]+)?"',version_link,entry.read_text()))
    out=HERE/'releases';out.mkdir(exist_ok=True)
    sources={'index.html':HERE/'night.html',**{name:HERE/name for name in ASSETS}}
    manifest={'title':'Ночная смена · Мастерская неба','version':'2026.10.05-learning.3','entry':'index.html',
      'cases':9,'modes':[3,6,9],'files':{name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in sources.items()}}
    instructions='Мастерская неба\n\nРаспакуйте весь архив. Откройте index.html в современном браузере.\nИнтернет не нужен. Рекомендуемый первый режим — 6 исследований.\nВ обсерватории открой карту неба. Перетаскивай небо, чтобы совместить отмеченный участок с прицелом. Можно навести по координатам кнопкой или клавишей Home. Открой архив и центральный прибор. После проверки вернись к Нике: снимок останется на доске.\nКлик выбирает точку на снимке, кнопки под ним переключают даты. Есть помощь и список точек для клавиатуры.\nЗвук включается кнопкой. Пауза сохраняет смену на этом устройстве, если браузер разрешает локальное хранилище.\nВ финале можно продолжить или скачать журнал.\nПеред следующим игроком выберите «Передать смену».\n\nЦелевой возраст 10–13 лет. Время самостоятельного прохождения детьми ещё не измерено.\nДанные, научные границы и благодарности — NIGHT-SOURCES.txt и файлы provenance.json.\n'
    with zipfile.ZipFile(out/'night-shift.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for name,path in sources.items():archive.write(path,name)
        archive.writestr('README.txt',instructions)
        archive.writestr('build.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    (out/'build.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'zip':str(out/'night-shift.zip'),'bytes':(out/'night-shift.zip').stat().st_size,'files':len(sources)}))
if __name__=='__main__':main()
