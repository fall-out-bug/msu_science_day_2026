#!/usr/bin/env python3
"""Печатный комплект «Архив неизвестного»: три PDF в папке dist/print.

  presenter.pdf — ключ ведущего: сценарий, управление, честные счётчики,
                  таблица ответов контактного листа (тип, оценка, наблюдения,
                  пояснение), благодарности обзора данных дословно.
  ranking.pdf   — предварительный рейтинг алгоритма (офлайн-резерв): 12 участков
                  по убыванию оценки, отметки прохождения порогов 1 и 3; оценка —
                  не вероятность; типы и объяснения не раскрываются.
  cards.pdf     — страницы для групп: карточки только с кадрами 1–2 (подписи —
                  фактические даты и фильтры наблюдений), нейтральные названия,
                  пустые поля; затем страницы ведущего: вырезки с кадром 3 и
                  ответом (доказательства и ограничения — дословно).

Все снимки участков — настоящие научные наблюдения (ZTF Public Survey, IRSA):
даты, фильтры, выдержки и источники печатаются рядом с кадрами. Все тексты на
русском; шрифт DejaVu Sans (свободная лицензия, встраивается в PDF подмножеством).
Запускается сборкой tools/build_release.py, но модуль можно использовать и отдельно:

  python3 -c "import sys; sys.path.insert(0,'tools'); \
    from generate_data import build_game_data, png_bytes; \
    from print_kit import build_print_kit; \
    data, images = build_game_data(); \
    build_print_kit('dist/print', data, {cid: [png_bytes(e) for e in ee] for cid, ee in images.items()})"

Зависимости: reportlab, numpy, Pillow (tools/requirements.txt).
"""
import sys
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

ACCENT = colors.HexColor("#12263a")
INK = colors.HexColor("#1c2b36")
LINE = colors.HexColor("#b9c6d2")
PALE = colors.HexColor("#eef3f7")

TYPE_RU = {
    "normal": "норма",
    "mover": "движущийся",
    "variable": "переменность",
    "artifact": "артефакт",
    "weak": "слабая переменность",
    "weak_mid": "переменность (фотометрия)",
    "unresolved": "не классифицировано",
}

COUNTERS = (
    ("Изменений найдено", "подтверждённое изменение источника и версия группы «изменился сам объект»"),
    ("Изменений пропущено", "подтверждённое изменение источника, для которого группа выбрала другую версию или не оставила ответа"),
    ("Помех распознано", "подтверждённая помеха и версия группы «помеха на снимке»"),
    ("Проверок спокойных полей", "число заявок на участки без заметного изменения; это информация, а не штраф"),
)


def _esc(s) -> str:
    """Экранирование данных для Paragraph (реальные строки могут содержать & и <)."""
    from xml.sax.saxutils import escape
    return escape(str(s))


def _obs_line(o) -> str:
    """Факты наблюдения одной строкой: дата, время (UTC), фильтр, выдержка."""
    exp = f"{float(o['exposure']):g}".replace(".", ",")
    return f"{o['date'][:10]} {o['date'][11:19]} · {_esc(o['filter'])} · {exp} с"


def _survey(data) -> str:
    ds = (data.get("meta") or {}).get("dataset") or {}
    return str(ds.get("survey") or "")


def _composition_ru(data, ids) -> str:
    """Человеческий состав набора по фактическим типам: «норма, движущийся, …»."""
    from collections import Counter
    by = {c["id"]: c["type"] for c in data["contact"]}
    cnt = Counter(by[i] for i in ids if i in by)
    parts = [f"{n} × {TYPE_RU[t]}" if n > 1 else TYPE_RU[t]
             for t, n in sorted(cnt.items(), key=lambda kv: -kv[1])]
    return ", ".join(parts)


def _demo_text(data) -> str:
    """Фактическое описание демо-набора из данных (без сидов и обещаний)."""
    from collections import Counter
    demo = data.get("demo") or []
    ds = (data.get("meta") or {}).get("dataset") or {}
    tr = (data.get("meta") or {}).get("training") or {}
    dist = ", ".join(f"{n} × {TYPE_RU.get(t, t)}" for t, n in
                     sorted(Counter(c["type"] for c in demo).items(),
                            key=lambda kv: (-kv[1], kv[0])))
    survey = f" ({ds['survey']})" if ds.get("survey") else ""
    train = f" Детектор обучен на {tr['n_rows']} отдельных участках реальных наблюдений." if tr.get("n_rows") else ""
    return (f"Расширенный набор — {len(demo)} реальных полей того же обзора{survey}, "
            f"id d001…d{len(demo):03d}; состав по данным: {dist}. "
            f"Оценки и признаки рассчитаны заранее тем же детектором.{train} "
            "Используйте этот набор для обсуждения масштаба задачи и порога отбора.")


def _threshold_paragraphs(data, st):
    """Фактическая (посчитанная по данным) картина порогов, без переносов старых обещаний."""
    m = data["meta"]
    soft, strict = m["thresholds"]["soft"], m["thresholds"]["strict"]
    cs = sorted(data["contact"], key=lambda c: c["score"])
    between = [c for c in cs if soft <= c["score"] < strict]
    below = [c for c in cs if c["score"] < soft]
    out = [Paragraph(
        f"Число отобранных участков: при пороге {soft:g} — "
        f"{sum(1 for c in cs if c['score'] >= soft)}, при пороге {strict:g} — "
        f"{sum(1 for c in cs if c['score'] >= strict)}.", st["body"])]
    if between:
        out.append(Paragraph(
            "Между порогами: " + ", ".join(f"{_esc(c['id'])} ({c['score']:.2f})" for c in between)
            + " — мягкий порог их сохраняет, строгий теряет.", st["body"]))
    else:
        out.append(Paragraph("Участков с оценкой между порогами нет.", st["body"]))
    if below:
        out.append(Paragraph(
            "Ниже обоих порогов: " + ", ".join(f"{_esc(c['id'])} ({c['score']:.2f})" for c in below)
            + " — при обоих показанных порогах алгоритм их не отбирает. Их всё равно можно исследовать вручную.", st["body"]))
    arts = [c for c in cs if c["type"] == "artifact"]
    if arts and all(c["score"] >= strict for c in arts):
        out.append(Paragraph(
            "Артефакты (яркие помехи) проходят оба порога: оценка — не «интересность».", st["body"]))
    else:
        out.append(Paragraph(
            "Оценка — не «интересность»: высокую оценку может набрать и помеха.", st["body"]))
    out.append(Paragraph(
        "Ни одна настройка не заменяет интерпретацию. Обсудите с группой цену пропуска "
        "и лишней проверки.", st["body"]))
    return out

FONT_DIRS = ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu",
             "/usr/local/share/fonts/dejavu", "/opt/homebrew/share/fonts/dejavu")


def _find_font(name):
    import os
    env = os.environ.get("DEJAVU_DIR")
    dirs = ([env] if env else []) + list(FONT_DIRS)
    for d in dirs:
        p = Path(d) / name
        if p.is_file():
            return p
    import glob
    hits = sorted(glob.glob(f"/usr/share/fonts/**/{name}", recursive=True))
    if hits:
        return Path(hits[0])
    raise SystemExit(f"Не найден шрифт {name}; установите пакет fonts-dejavu-core "
                     f"или задайте DEJAVU_DIR=/путь/к/папке/dejavu")


def register_fonts():
    pdfmetrics.registerFont(TTFont("DejaVu", str(_find_font("DejaVuSans.ttf"))))
    pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(_find_font("DejaVuSans-Bold.ttf"))))
    pdfmetrics.registerFontFamily("DejaVu", normal="DejaVu", bold="DejaVu-Bold",
                                  italic="DejaVu", boldItalic="DejaVu-Bold")


def _styles():
    base = dict(fontName="DejaVu", textColor=INK)
    return {
        "h1": ParagraphStyle("h1", fontSize=16, leading=20, spaceAfter=2,
                             textColor=ACCENT, fontName="DejaVu-Bold"),
        "sub": ParagraphStyle("sub", fontSize=9.5, leading=13, **base),
        "h2": ParagraphStyle("h2", fontSize=12, leading=15, spaceBefore=10,
                             spaceAfter=4, textColor=ACCENT, fontName="DejaVu-Bold"),
        "body": ParagraphStyle("body", fontSize=9.5, leading=13, spaceAfter=3, **base),
        "small": ParagraphStyle("small", fontSize=8, leading=11, fontName="DejaVu",
                                textColor=colors.HexColor("#4a5a66")),
        "cell": ParagraphStyle("cell", fontSize=8.5, leading=11.5, **base),
        "cellb": ParagraphStyle("cellb", fontSize=8.5, leading=11.5,
                                fontName="DejaVu-Bold"),
        "caption": ParagraphStyle("caption", fontSize=7.5, leading=9.5, fontName="DejaVu",
                                  alignment=1, textColor=colors.HexColor("#4a5a66")),
    }


def _header_footer(title, subtitle):
    def draw(canv, doc):
        canv.saveState()
        canv.setFont("DejaVu-Bold", 8)
        canv.setFillColor(ACCENT)
        canv.drawString(12 * mm, 285 * mm, title)
        canv.setFont("DejaVu", 7.5)
        canv.setFillColor(colors.HexColor("#4a5a66"))
        canv.drawRightString(198 * mm, 285 * mm, subtitle)
        canv.setStrokeColor(LINE)
        canv.line(12 * mm, 283.5 * mm, 198 * mm, 283.5 * mm)
        canv.drawString(12 * mm, 8 * mm,
                        "Настоящие наблюдения · оценки рассчитаны заранее · атрибуции: real/CREDITS.md")
        canv.drawRightString(198 * mm, 8 * mm, f"стр. {canv.getPageNumber()}")
        canv.restoreState()
    return draw


def _doc(path, title, subtitle):
    doc = SimpleDocTemplate(str(path), pagesize=(210 * mm, 297 * mm),
                            leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=18 * mm, bottomMargin=14 * mm,
                            title=title, author="Факультет ИИ — «Наука 0+»",
                            subject=subtitle)
    return doc, _header_footer(title, subtitle)


def _key_table(data, st):
    """Таблица ответов: id+имя, тип, оценка, наблюдения (даты/фильтры), пояснение."""
    head = ["№", "Участок (id · сектор)", "Тип", "Оценка", "Наблюдения (UTC)", "Пояснение ведущему"]
    rows = [[Paragraph(h, st["cellb"]) for h in head]]
    for i, c in enumerate(data["contact"], 1):
        obs = "<br/>".join(_obs_line(o) for o in c["observations"])
        obs += f"<br/><font size=6.5>Данные: {_esc(c['source']['label'])}</font>"
        rows.append([
            Paragraph(str(i), st["cell"]),
            Paragraph(f"{_esc(c['id'])} · {_esc(c['name'])}", st["cell"]),
            Paragraph(TYPE_RU[c["type"]], st["cell"]),
            Paragraph(f"{c['score']:.2f}", st["cell"]),
            Paragraph(obs, st["cell"]),
            Paragraph(_esc(c["explanation"]), st["cell"]),
        ])
    t = Table(rows, colWidths=[7 * mm, 27 * mm, 26 * mm, 18 * mm, 44 * mm, 64 * mm],
              repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PALE),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
    ]))
    return t


def build_presenter(out, data, st):
    m = data["meta"]
    doc, painter = _doc(out / "presenter.pdf",
                        "Архив неизвестного — ключ ведущего",
                        "полная смена 12 · короткая 6 · печатный комплект")
    flow = [
        Paragraph("Ключ ведущего", st["h1"]),
        Paragraph("Офлайн-игра «Охота за звёздными аномалиями». Все снимки участков — "
                  "настоящие научные наблюдения"
                  + (f" ({_esc(_survey(data))})" if _survey(data) else "")
                  + "; даты, фильтры, выдержки и источники — в таблице ключа и на карточках. "
                  "Примеры известных объектов — на экране «Из настоящих наблюдений» "
                  "(атрибуции в real/CREDITS.md, воспроизводить дословно).", st["sub"]),
        Spacer(1, 4),

        Paragraph("1. Как идёт игра", st["h2"]),
        Paragraph("Полная смена: 12 участков и 3 жетона дополнительных наблюдений; "
                  "короткая: 6 участков и 1 жетон. Группа выбирает участок на карте "
                  "или среди карточек и записывает первое впечатление: «вижу изменение», "
                  "«не вижу изменения» или «пока не могу понять». Затем можно потратить "
                  "жетон на третий архивный кадр и выбрать объяснение: «изменился сам "
                  "объект», «помеха на снимке», «заметных изменений нет» или «недостаточно "
                  "данных». Сначала нужно записать впечатление, затем доступна заявка. "
                  "Подсказка алгоритма необязательна и не заменяет проверку.", st["body"]),
        Paragraph("После своей версии кнопка «Что показали наблюдения?» открывает "
                  "разбор только этого дела: третий кадр, объяснение, измерения "
                  "и оценку алгоритма. Заявка не тратится — она нужна для проверки "
                  "до раскрытия ответа. Версию можно уточнить; вариант до первого "
                  "разбора сохранится рядом. На бумаге оставьте обе версии.", st["body"]),
        Paragraph("Полная смена, 15–20 минут: вводная 2–3, исследование 8–12, "
                  "совет 3–5. Короткая, 5–7 минут: вводная 1, исследование 3–4, "
                  "совет 1–2. Сначала спросите, что видно на снимках; затем предложите "
                  "группе объяснить выбор проверки. На совете разберите яркую помеху "
                  "и слабый пропуск — высокая оценка не равна открытию.", st["body"]),

        Paragraph("2. Кнопки ведущего", st["h2"]),
        Paragraph("«Ведущему» открывает пульт с таймером, порогом отбора и разборами. "
                  "«Итоги и разбор» раскрывает ответы всей смены; ранний переход "
                  "предупреждает об участках без версии. После последней версии "
                  "к общему разбору ведёт кнопка «Посмотреть итоги». "
                  "Таймер отсчитывает время смены; его можно приостановить и сбросить. "
                  "«Новая группа» после подтверждения сбрасывает состояние игры. "
                  "В разделе «ИИ в астрономии» — шесть примеров: планета Кеплер-90i, "
                  "сверхновая SN 2023tyk, следы астероидов, изображение чёрной дыры, "
                  "гравитационные линзы и помехи детекторов гравитационных волн. "
                  "У каждой истории есть вопрос для обсуждения и ссылки на исследования. "
                  "В пульте кнопка «Другие наблюдения» открывает фотографии ESA/Hubble и STScI.", st["body"]),

        Paragraph("3. Честные счётчики (точные формулы)", st["h2"]),
    ]
    counters_rows = [[Paragraph("Счётчик", st["cellb"]),
                      Paragraph("Что считается", st["cellb"])]]
    for name, formula in COUNTERS:
        counters_rows.append([Paragraph(name, st["cell"]), Paragraph(formula, st["cell"])])
    t = Table(counters_rows, colWidths=[32 * mm, 154 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PALE),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    flow += [t,
             Paragraph("Счётчики отвечают на разные вопросы и не складываются в общий "
                       "балл. Они учитывают текущие версии, включая уточнения после "
                       "разбора; число участков без версии указано отдельно. "
                       "Они сопоставляют решения группы с независимо обоснованными "
                       "разборами, а не с оценками алгоритма. Неоднозначные случаи "
                       "не засчитываются как доказанные изменения или помехи.",
                       st["body"]),

             Paragraph("Пороги отбора по оценкам этого набора", st["h2"]),
             *_threshold_paragraphs(data, st),

             Paragraph("4. Ключ контактного листа (12 участков)", st["h2"]),
             _key_table(data, st),

             Paragraph("5. Короткая смена (6 участков)", st["h2"]),
             Paragraph("Используются случаи: " + _esc(", ".join(data["shortIds"])) +
                       " (состав: " + _esc(_composition_ru(data, data["shortIds"])) +
                       "; 1 жетон).", st["body"]),
             Paragraph("Перед заявкой спросите, какой вопрос поможет решить третий "
                       "кадр. После своей версии разберите одно дело. У s10 оценка "
                       "алгоритма низкая, хотя измерения подтверждают изменение: "
                       "сравните оценку с данными. Все оценки короткого набора "
                       "ниже минимального порога 0,5, поэтому алгоритм здесь "
                       "не отбирает ни одного поля.", st["body"]),

             Paragraph("6. Расширенный набор", st["h2"]),
             Paragraph(_esc(_demo_text(data)), st["body"]),

             Paragraph("7. Источники и права", st["h2"]),
             Paragraph("Реальные фотографии: ESA/Hubble (CC BY 4.0) и STScI (public "
                       "domain) — атрибуции дословно в файле real/CREDITS.md поставки. "
                       "Печатный шрифт: DejaVu Sans (свободная лицензия, встроен в PDF). "
                       "Детали — в LICENSES.txt и docs/runbook.md.", st["body"]),
             ]
    acks = (m.get("acknowledgments") or {})
    if acks:
        flow.append(Paragraph(
            "Наблюдательные данные участков"
            + (f": {_esc(_survey(data))}" if _survey(data) else "")
            + " — благодарности обзора дословно:", st["body"]))
        for v in acks.values():
            flow.append(Paragraph(_esc(v), st["small"]))
    flow.append(Paragraph(
        "Звёздная карта: Ernie Wright / NASA SVS «Deep Star Maps 2020» (каталожная "
        "визуализация Hipparcos-2, Tycho-2, Gaia DR2; svs.gsfc.nasa.gov/4851); "
        "звёзды — HYG v4.1 (CC BY-SA 4.0); линии и названия созвездий — Stellarium "
        "«western» (CC BY-SA 4.0 + Free Art License; переводы GPL-2.0+). "
        "Полные атрибуции и тексты лицензий — real/CREDITS.md и LICENSES.txt.", st["small"]))
    doc.build(flow, onFirstPage=painter, onLaterPages=painter)


def build_ranking(out, data, st):
    """Предварительный рейтинг алгоритма — офлайн-резерв экранного отбора.

    12 участков по убыванию предварительной оценки, отметки прохождения порогов
    1 (мягкий) и 3 (строгий). Лист можно показывать группам: типов и объяснений
    он не раскрывает; оценка — не вероятность. Это не бланк соревнования групп.
    """
    soft = data["meta"]["thresholds"]["soft"]
    strict = data["meta"]["thresholds"]["strict"]
    ranked = sorted(data["contact"], key=lambda c: -c["score"])
    head = ["Ранг", "Участок (id · сектор)", "Оценка",
            f"Проходит порог {soft:g}", f"Проходит порог {strict:g}"]
    rows = [[Paragraph(h, st["cellb"]) for h in head]]
    for rank, c in enumerate(ranked, 1):
        rows.append([
            Paragraph(str(rank), st["cell"]),
            Paragraph(f"{_esc(c['id'])} · {_esc(c['name'])}", st["cell"]),
            Paragraph(f"{c['score']:.2f}", st["cell"]),
            Paragraph("да" if c["score"] >= soft else "—", st["cell"]),
            Paragraph("да" if c["score"] >= strict else "—", st["cell"]),
        ])
    t = Table(rows, colWidths=[16 * mm, 62 * mm, 24 * mm, 42 * mm, 42 * mm],
              repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PALE),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 0), (4, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
    ]))
    doc, painter = _doc(out / "ranking.pdf",
                        "Архив неизвестного — рейтинг алгоритма",
                        "предварительный отбор · офлайн-резерв · без ответов")
    flow = [
        Paragraph("Рейтинг алгоритма (предварительный отбор)", st["h1"]),
        Paragraph("Офлайн-резерв экранного алгоритма: участки контактного листа в "
                  "порядке убывания предварительной оценки аномальности. Лист можно "
                  "показывать группам — типы участков и объяснения здесь не "
                  "раскрываются (ключ ведущего — в presenter.pdf).", st["sub"]),
        Spacer(1, 6),
        t,
        Spacer(1, 8),
        Paragraph("Как читать оценку", st["h2"]),
        Paragraph("Оценка необычности — максимальное нормированное отклонение "
                  "признаков участка от типичных значений обучающей выборки "
                  "(формула — в data.js, meta.score_formula). Это не вероятность "
                  "и не ответ на вопрос, интересен ли объект для исследования: "
                  "помеха тоже может получить высокую оценку.", st["body"]),
        *_threshold_paragraphs(data, st),
        Paragraph("Более строгий отбор — не гарантия открытия. Отметка «да» означает: "
                  "предварительная оценка не ниже порога.", st["body"]),
    ]
    doc.build(flow, onFirstPage=painter, onLaterPages=painter)


CUT_LINE = colors.HexColor("#5a6a76")
CUT_DASH = (2.5, 2.5)


def _boxed(inner, st):
    """Оборачивает блок в пунктирную рамку-«вырезание» с подписью."""
    boxed = Table([[inner]], colWidths=[186 * mm])
    boxed.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, CUT_LINE, None, CUT_DASH),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    return boxed


def _strip_head(left, center, right, st):
    head = Table([[Paragraph(left, st["small"]),
                   Paragraph(center, st["cellb"]),
                   Paragraph(right, st["cell"])]],
                 colWidths=[34 * mm, 96 * mm, 50 * mm])
    head.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return head


def _player_card(c, frames, st):
    """Карточка группы: только кадры 1–2, нейтральное название, пустые поля."""
    imgs = [Image(BytesIO(png), width=62 * mm, height=62 * mm) for png in frames[:2]]
    caps = [Paragraph(f"кадр {k + 1} · {_obs_line(c['observations'][k])}", st["caption"])
            for k in range(2)]
    row = Table([imgs], colWidths=[90 * mm] * 2)
    row.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    caprow = Table([caps], colWidths=[90 * mm] * 2)
    caprow.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
    ]))
    fields = Table([[Paragraph(
        "Наблюдение (что изменилось?): "
        "_______________________________________________________   "
        "Версия группы: ____________________", st["cell"])]],
        colWidths=[180 * mm])
    fields.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
    ]))
    region = c["skyContext"]
    context = [
        Paragraph(f"<b>Созвездие: {_esc(region['constellation']['name'])}.</b> "
                  + _esc(region["intro"]), st["cell"]),
        Paragraph(_esc(region["scaleNote"]), st["small"]),
    ]
    boxed = _boxed([_strip_head("Карточка участка", f"{_esc(c['id'])} · {_esc(c['name'])}",
                                "кадры 1–2", st),
                    Spacer(1, 2), row, caprow, *context, fields], st)
    return KeepTogether([boxed,
                         Paragraph("вырежьте карточку по пунктирной рамке", st["caption"]),
                         Spacer(1, 8)])


def _cutout(c, frames, st):
    """Вырезка ведущего: кадр 3 (доп-наблюдение) и ответ; совпадение по id."""
    o3 = c["observations"][2]
    left = [Image(BytesIO(frames[2]), width=70 * mm, height=70 * mm),
            Paragraph(f"кадр 3 · доп-наблюдение · {_obs_line(o3)}", st["caption"])]
    right = [
        Paragraph(f"<b>Тип: {TYPE_RU[c['type']]}</b> · оценка {c['score']:.2f}", st["cell"]),
        Spacer(1, 2),
        Paragraph(_esc(c["explanation"]), st["cell"]),
        Spacer(1, 2),
        Paragraph(f"<b>Доказательство:</b> {_esc(c['evidence'])}", st["cell"]),
        Spacer(1, 2),
        Paragraph(f"<b>Ограничения:</b> {_esc(c['limitations'])}", st["cell"]),
        Spacer(1, 2),
        Paragraph(f"Данные: {_esc(c['source']['label'])}", st["small"]),
    ]
    body = Table([[left, right]], colWidths=[78 * mm, 102 * mm])
    body.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (0, 0), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    boxed = _boxed([_strip_head("Для карточки", f"{_esc(c['id'])} · {_esc(c['name'])}",
                                "ведущему", st), body], st)
    return KeepTogether([boxed,
                         Paragraph("вырежьте по пунктиру; согните между снимком и ответом, "
                                   "скрыв ответ внутри; выдавайте снимок по id", st["caption"]),
                         Spacer(1, 8)])


def build_cards(out, data, frame_pngs, st):
    doc, painter = _doc(out / "cards.pdf",
                        "Архив неизвестного — карточки участков",
                        "страницы групп + вырезки ведущего · печатный резерв")
    total = len(data["contact"])
    flow = [
        Paragraph("Карточки участков", st["h1"]),
        Paragraph("Печатный резерв на случай недоступности экрана. Печать A4; цвет "
                  "желателен — в ч/б слабые сигналы различимы хуже.", st["sub"]),
        Paragraph("Как использовать", st["h2"]),
        Paragraph("1. Страницы для групп — по одной карточке на участок: "
                  "кадры 1–2, рассказ об области неба и поля «наблюдение» и «версия». "
                  "Рассказ помогает сориентироваться на небе, но не раскрывает ответ. "
                  "Вырежьте карточки по пунктирным рамкам и раздайте группам.", st["body"]),
        Paragraph("2. Последние страницы — только для ведущего: вырезки с третьим кадром "
                  "(доп-наблюдение за жетон) и ответом (тип, оценка, пояснение). Вырежьте "
                  "по пунктиру и согните между снимком и ответом так, чтобы ответ "
                  "оказался внутри. Выдавайте снимок по id соответствующей карточки.", st["body"]),
        Paragraph("3. Третьего кадра и ответа на карточках групп нет намеренно: "
                  "до раскрытия ответа доп-наблюдение группа получает за жетон. "
                  "После записанной версии ведущий может бесплатно раскрыть ответ "
                  "и третий кадр этого дела. Исходную версию сохраните рядом с "
                  "уточнением.", st["body"]),
        PageBreak(),
        Paragraph("Страницы для групп", st["h2"]),
    ]
    for i, c in enumerate(data["contact"], 1):
        flow.append(_player_card(c, frame_pngs[c["id"]], st))
        if i % 2 == 0 and i < total:
            flow.append(PageBreak())
    flow += [
        PageBreak(),
        Paragraph("Страницы ведущего — не раздавать группам", st["h2"]),
        Paragraph("Вырезки: кадр 3 и ответ. Совпадение с карточкой — по id; держите "
                  "подписью вниз до решения группы.", st["small"]),
        Spacer(1, 4),
    ]
    for i, c in enumerate(data["contact"], 1):
        flow.append(_cutout(c, frame_pngs[c["id"]], st))
        if i % 2 == 0 and i < total:
            flow.append(PageBreak())
    doc.build(flow, onFirstPage=painter, onLaterPages=painter)


def build_print_kit(out_dir, game_data, frame_pngs):
    """Собирает dist/print/{presenter,ranking,cards}.pdf.

    frame_pngs: {case_id: [png bytes ×3]} — кадры контактного листа.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    register_fonts()
    st = _styles()
    build_presenter(out, game_data, st)
    build_ranking(out, game_data, st)
    build_cards(out, game_data, frame_pngs, st)
    return [out / "presenter.pdf", out / "ranking.pdf", out / "cards.pdf"]


if __name__ == "__main__":
    raise SystemExit("модуль печатного комплекта — запускайте через tools/build_release.py "
                     "(см. docstring для отдельного использования)")
