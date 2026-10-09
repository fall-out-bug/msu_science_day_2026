#!/usr/bin/env python3
"""Render the fixed experiment as an offline diagnostic, not a game UI."""
import base64
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / 'results'
report = json.loads((OUT / 'report.json').read_text())
raw = (ROOT / 'app/data.js').read_text().split('window.GAME_DATA =', 1)[1].strip().rstrip(';')
cases = {c['id']: c for c in json.loads(raw)['contact']}
rows = json.loads((OUT / 'mover2-candidates.json').read_text())
target = rows[report['fields']['mover2']['target_index']]
false = next(rows[r['index']] for r in report['results']['initial']['mover2']['top']
             if r['label'] == 'mixed_identity')


def strip(row, color):
    parts = []
    for epoch, (uri, position) in enumerate(zip(cases['s07']['frames'], row['positions'])):
        x, y = position
        parts.append(f'''<figure><svg viewBox="0 0 128 128" role="img"
          aria-label="Наблюдение {epoch + 1}, выбранная точка {x}, {y}">
          <image href="{uri}" width="128" height="128"/>
          <circle cx="{x + .5}" cy="{y + .5}" r="6" fill="none" stroke="{color}" stroke-width="1"/>
          </svg><figcaption>Кадр {epoch + 1} · {report['fields']['mover2']['hours'][epoch]*60:.1f} мин</figcaption></figure>''')
    return '<div class="strip">' + ''.join(parts) + '</div>'


scenario_names = {'initial':'Исходные примеры', 'correction_a':'Исправление А',
                  'correction_b':'Исправление Б', 'both':'Оба исправления',
                  'wrong_label':'Ошибочная подсказка', 'undo':'Отмена изменений'}
table = ''
for s, name in scenario_names.items():
    result = report['results'][s]['mover2']
    table += (f'<tr><th>{name}</th><td>{result["target_rank"]}</td>'
              f'<td>{result["accepted_known_false"]}</td>'
              f'<td>{result["changed_decisions"]}</td></tr>')
source_hashes = {f's07-frame-{i + 1}':hashlib.sha256(base64.b64decode(uri.split(',')[1])).hexdigest()
                 for i,uri in enumerate(cases['s07']['frames'])}
(OUT / 'preview-sha256.json').write_text(json.dumps(source_hashes, indent=2) + '\n')

page = f'''<!doctype html><html lang="ru"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Мой поисковик — технический эксперимент</title>
<style>
:root {{color-scheme:dark}} * {{box-sizing:border-box}}
body {{margin:0;background:#101927;color:#e9effa;font:17px/1.55 system-ui,sans-serif}}
main {{max-width:1000px;margin:auto;padding:36px 22px 60px}} h1 {{font-size:34px;line-height:1.2}}
h2 {{font-size:23px;margin-top:32px}} p {{max-width:850px}} .label {{color:#aebfd8;font-size:14px}}
.finding {{border-left:4px solid #91dbb0;padding:8px 20px;background:#182b32}}
.limit {{border-left:4px solid #eec279;padding:8px 20px;background:#2c2830}}
.scroll {{overflow-x:auto}} table {{width:100%;border-collapse:collapse;font-size:15px}}
td,th {{padding:12px;text-align:left;border-bottom:1px solid #344359}} th {{font-weight:600}}
.strip {{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}} figure {{margin:0}}
svg {{display:block;width:100%;background:#05080e;border-radius:8px}}
figcaption {{font-size:13px;color:#b8c8de;margin-top:6px}} .score {{font-size:16px}}
code {{color:#b0d5ff}} a {{color:#b0d5ff}} @media(max-width:540px) {{main{{padding:22px 12px}}h1{{font-size:27px}}.strip{{gap:6px}}figcaption{{font-size:11px}}}}
</style><main>
<p class="label">3 октября 2026 · локальный эксперимент · не игровая сцена</p>
<h1>Пример меняет поиск.<br>Нужен ли такой поиск игре?</h1>
<div class="finding"><p><b>Влияние подтверждено.</b> Один исправленный пример на участке Amosov
изменил отбор связей на другом участке — Gianni. Ошибочная подсказка ухудшила рейтинг
настоящего следа. Отмена точно восстановила прежний результат.</p></div>
<p>Модель получает три реальных наблюдения и перебирает связи между найденными точками.
Обучение: один пример движущегося объекта и четыре неподвижных следа. Затем отдельно
проверяются два исправления ложной связи. Примеры выбраны разработчиком; детей в этой
проверке не было.</p>
<h2>Испытание на другом участке</h2>
<p>На каждом снимке Gianni обнаружено 10 точек: всего <b>1000 комбинаций из трёх точек</b>.
Это не 1000 небесных объектов. Один след соответствует известному астероиду, девять —
неподвижным источникам, 990 смешивают источники по проверенным позиционным соответствиям.</p>
<div class="scroll"><table><thead><tr><th>Примеры для обучения</th><th>Место настоящего следа</th>
<th>Принятые ложные связи</th><th>Изменённые решения</th></tr></thead><tbody>{table}</tbody></table></div>
<p class="label">Порог принятия фиксирован заранее: оценка выше нуля. Исходный набор не содержит
примеров перепутанных связей, поэтому модель чрезмерно разрешительная. Тысяча комбинаций
из десяти источников не является тысячей независимых проверок.</p>
<h2>Одна конкретная ложная связь</h2>
<p>Кружки показывают точки, которые модель первоначально согласилась связать.
Каждая точка находится на своём настоящем снимке; исходные изображения не изменены.</p>
{strip(false, '#ffbb80')}
<p class="score">Оценка до: <b>{false['scores']['initial']:.3f}</b> → после исправления А:
<b>{false['scores']['correction_a']:.3f}</b>. Это мера сходства с примерами, не вероятность.</p>
<h2>Настоящий движущийся объект сохраняется</h2>
{strip(target, '#98efca')}
<p class="score">Оценка до: <b>{target['scores']['initial']:.3f}</b> → после исправления А:
<b>{target['scores']['correction_a']:.3f}</b>. Первое место в обоих случаях.</p>
<div class="limit"><p><b>Важное ограничение.</b> Простое правило равномерного движения,
без обучения, также ставит настоящий след первым на обоих участках.
Исправление очищает отбор, но не находит объект, который раньше был скрыт внизу рейтинга.</p></div>
<h2>Что это решает для игры</h2>
<p>Можно честно дать ребёнку повлиять на работу прибора. Но пока не доказано, что
выбранная задача требует обучения, что два исправления воспринимаются как разные
стратегии или что ребёнок захочет повторить эксперимент. На новом поле исправления А и Б
дают одинаковый набор принятых следов, хотя численные оценки отличаются.</p>
<p>Практический вывод: не строить всю кампанию на обещании «исправь одну связь — и машина
научится». Следующий предмет проектирования — выбор способа наблюдения или проверки,
при котором ребёнок понимает, зачем ему понадобился обучаемый инструмент.</p>
<p><b>Важная деталь управления:</b> проверено добавление отвергнутой связи как отрицательного
примера. Повторное добавление уже известного правильного следа ничего не меняет.
Жест исправления должен сохранять и отвергнутую связь; этот эксперимент пока не
доказывает работоспособность одного лишь перетаскивания точки.</p>
<p class="label">Источник изображений: архив ZTF / IRSA, участок Gianni, 2 января 2020.
Признаки вычислены по калиброванным массивам, а показаны исходные превью из проекта.
Время для расчётов взято из MJD манифеста. Все три кадра доступны модели;
это проверка на другом поле, а не предсказание скрытого третьего кадра.</p>
<p><a href="report.json">Полный машинный отчёт</a> ·
<a href="../protocol.md">Зафиксированные условия</a> ·
<a href="https://scikit-learn.org/stable/modules/neighbors.html">Принцип метода ближайших примеров</a></p>
</main></html>'''
(OUT / 'index.html').write_text(page)
print(OUT / 'index.html')
