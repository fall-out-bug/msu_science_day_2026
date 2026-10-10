# Ночь открытий: приключение в обсерватории

Самостоятельный настольный маршрут для ребёнка около 12 лет: собрать
архивные снимки, разметить обучающую выборку, проверить предсказания CNN,
разобрать старые метки, пройти объяснённый опыт с готовой сетью, а затем
самостоятельно изменить её и сравнить результаты. Подробные метрики
доступны по приглашению Ники.

Продуктовые решения и условия готовности:
`docs/design-2026-10-09/night-of-discoveries.md` (согласованные изменения)
и `docs/design-2026-10-08/{game-design,technical-plan,acceptance,goal}.md`
(исходный научный и технический контракт).
Статус выполнения и доказательства хранятся отдельно от этих требований.

## Запуск

Откройте `index.html` в настольном браузере или распакуйте
`releases/galaxy-shift.zip` целиком и откройте его `index.html`.
В автономном пакете есть снимки и все рассчитанные результаты; интернет,
сервер и учётная запись не нужны. Целевые экраны: 1280×720, 1440×900 и
1920×1080; дополнительная проверка — 1366×768 и увеличение интерфейса 150%.

Перезагрузка той же вкладки предлагает продолжить совместимую смену.
Переходы, справочные окна и возврат в обсерваторию сохраняют метки и
архитектуру. Новая смена сбрасывает работу после подтверждения.

## Маршрут и данные

После задания Ники ребёнок находит четыре галактики
на карте и открывает их архивные снимки. Ника разбирает пример; затем
ребёнок размечает четыре снимка и проверяет модель на трёх других снимках.
После явной проверки трёх старых меток ребёнок повторяет проверку. Затем
игра объясняет слои и свёртку и предлагает добавить второй свёрточный слой
к готовой сети, сохранив метки. После сравнения предсказаний ребёнок выбирает своё изменение сети,
проверяет и сравнивает ответы. Затем можно закончить смену при любом
результате или продолжить опыты.
Финал открывает отдельную итоговую выборку и свободное исследование карты,
24 архивных галактик и 19 научных карточек на едином небе. Материалы без
подтверждённых координат собраны в блок «Открытия по всему небу»;
его положение не обозначает координаты объектов.

Обучающая выборка содержит девять снимков. Семь меток изменяются: четыре
новые и три старые. Две другие фиксированы. Проверочная и итоговая выборки
содержат по три других объекта. Свободный архив не подмешивается в обучение.
Основная четвёрка: Messier 85, IC 5332, NGC 5023 и NGC 3318.

Метка класса, предсказание модели и справочная метка — разные данные.
«Вид с ребра» описывает ракурс диска, а не отдельный физический тип галактики.
Счёт относится к модели; требование 3/3 не используется. Итоговые снимки
уже изучались авторами: это учебный опыт, а не новый независимый научный тест.

## Реальные расчёты

2187 сочетаний семи редактируемых меток × 22 архитектуры = 48 114 обучений.
Основной маршрут сравнивает `d1-r` и `d2-r` на одинаковых метках. Остальные результаты загружаются по
архитектурам из 21 локального файла, в том числе через `file://`.
Неизвестный ключ или повреждённая таблица дают ошибку; похожий результат
не подставляется. Браузер открывает подготовленный опыт, не обучает модель.

CNN получает центральный фрагмент снимка в оттенках серого 32×32.
Обучаются свёртки, параметры BatchNorm при его наличии и линейный
классификатор. Dropout действует только при обучении. Условия, код,
проверки градиентов, полноты и воспроизводимости — в `experiments/README.md`
и `experiments/cnn-label-correction/protocol.json`. `DATA-NOTES.md` отделяет
нынешний метод от исторических версий.

## Проверка и сборка

Команды из корня репозитория. Для разработки нужны Python с NumPy, Pillow
и Playwright, а для JavaScript-проверок — Bun. Подготовьте окружение:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install numpy pillow playwright
python -m playwright install chromium
```

Эти зависимости нужны для разработки; готовый ZIP запускается в браузере.

```bash
python3 designlab/galaxy-shift/prepare-data.py --check
python3 designlab/galaxy-shift/prepare-archive.py --check
python3 designlab/galaxy-shift/experiments/check_constructor_math.py
python3 designlab/galaxy-shift/experiments/cnn-label-correction/check_constructor_table.py --require-full
python3 designlab/galaxy-shift/experiments/cnn-label-correction/check_reproduction.py
python tools/galaxy-release/check-image-dialogue.py --evidence docs/design-2026-10-09/evidence/dialogue-briefings.json
bun designlab/galaxy-shift/check-cnn-session.mjs
bun designlab/galaxy-shift/check-restoration.mjs
bun designlab/galaxy-shift/check-results-loader.mjs
bun designlab/galaxy-shift/check-metrics.mjs
bun tools/galaxy-telemetry/check-client.mjs
python3 tools/galaxy-telemetry/test_server.py
python3 tools/galaxy-telemetry/test_admin_export.py
GALAXY_RECOMPOSE_TELEMETRY_EVIDENCE=docs/design-2026-10-09/evidence/lesson-telemetry-integration.json python tools/galaxy-telemetry/check-integration.py
GALAXY_RECOMPOSE_RESULT_CASES_EVIDENCE=docs/design-2026-10-09/evidence/lesson-result-cases.json python designlab/galaxy-shift/check-result-cases.py
GALAXY_RECOMPOSE_CONTINUITY_EVIDENCE=docs/design-2026-10-09/evidence/lesson-continuity.json python designlab/galaxy-shift/check-continuity-browser.py
GALAXY_EVIDENCE_DIR=/tmp/science-day-complete-qa python designlab/galaxy-shift/check-complete-browser.py
python designlab/galaxy-shift/check-story-frame.py --evidence docs/design-2026-10-09/evidence/lesson-story-frame.json
GALAXY_N08_EVIDENCE=/tmp/science-day-lesson-flicker python designlab/galaxy-shift/check-no-cnn-flicker.py
GALAXY_RECOMPOSE_RESULT_IMAGE_EVIDENCE=docs/design-2026-10-09/evidence/lesson-result-image-loading.json python designlab/galaxy-shift/check-result-image-loading.py
python designlab/galaxy-shift/check-night-sky-integration.py
python3 designlab/galaxy-shift/build-galaxy.py
python tools/galaxy-release/check-offline-complete.py --evidence docs/design-2026-10-09/evidence/lesson-offline.json
```

Сборщик требует все 22 архитектуры, перечисляет ресурсы явно и записывает
их SHA-256 в `build.json`. Готовый ZIP проверяется после распаковки в новый
каталог и с отключённой сетью. Порядок публикации —
`tools/galaxy-release/RELEASE.md`. Локальные проверки не означают публикацию;
проверка публичного HTTPS выполняется отдельно. Старые тесты исторического
интерфейса не считаются приёмкой текущего конструктора.

## Журнал и происхождение

Сайт отправляет обезличенные события действий в отдельное хранилище на
30 дней. ZIP ведёт только локальный журнал. Экспорт и сведения о потерях:
«О проекте → Для стендиста: журнал смены». Подробности и административная
выгрузка — `tools/galaxy-telemetry/README.md`.

Научные изображения NASA/ESA Hubble и их SHA-256 сохранены; кредиты и ссылки
доступны у снимков. Это не изображения Roman. Комната и Ника — художественные
иллюстрации: происхождение в `assets/art/ART-CREDITS.md`. Атрибуция карты и
научных карточек находится в `sky-provenance.json` и `discovery-provenance.json`.
Понимание и интерес детей требуют отдельного пробного показа.
