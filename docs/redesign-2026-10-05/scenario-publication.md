# Публикация сценария · 6 октября 2026

- HTML: https://sd2026.beetles.family/docs/first-shift-scenario.html
- Markdown: https://sd2026.beetles.family/docs/first-shift-scenario.md
- Источник: `first-shift-scenario.md` в этой папке.
- Файлы поставки: `../../designlab/comparison/docs/first-shift-scenario.html` и `.md`.

В HTML встроены три SVG-схемы, полученные из Mermaid. Внешние скрипты, стили и шрифты не нужны. Есть оглавление, ссылка на игру, скачивание Markdown и стили печати. Это снимок документа; изменения Markdown требуют повторного экспорта.

При публикации к действующему образу игры добавлена только папка `docs/`. Контейнер основного сайта пересоздан через `compose.public.yaml`; сервис на 8081 не изменялся. Dockerfile comparison дополнен копированием `docs/` для будущих сборок.

Предыдущий образ: `sd2026-comparison:before-scenario-20261006`, ID `sha256:2d8cf9ded1477699843bf34cfcef1a6391bd179b9795671d4efe8800b169e4c6`.
Новый образ: `sha256:c3f4fb0d4ee780e0bf4148f19fd41ba7caca04774218820cf26f477bb8ac808c`.

SHA-256 HTML: `b7a5e79acefa8b5053e35788eccf9c2a61e902a77b7c8d0a25c7dc5b88663446`.
Совпадение подтверждено у локального файла, HTTP upstream и публичного HTTPS.

Браузерная проверка локального файла и HTTP upstream: 10 сцен, 3 SVG-схемы, размеры 1280 и 390 px без горизонтального переполнения страницы, ошибок JavaScript нет. Публичный HTML получен через HTTPS и совпал побайтно; прямой браузерный переход по HTTPS с этой машины завершился ERR_CONNECTION_REFUSED. Поэтому браузерная проверка публичного маршрута не заявляется.
