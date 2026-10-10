# Лицензии и атрибуции материалов

`LICENSE` распространяется только на исходный код и документацию, права на
которые принадлежат участникам Science Day. Он не меняет условий для снимков,
каталогов, иллюстраций и сохранённых исторических материалов.

## Материалы текущей игры

| Материал | Условия | Где указаны источник и атрибуция |
| --- | --- | --- |
| Снимки ESA/Hubble | [CC BY 4.0](LICENSES/CC-BY-4.0.txt); кредит каждого снимка сохраняется полностью | `designlab/galaxy-shift/provenance.json`, `archive-admission.json` |
| Атлас открытий ESA/Hubble | CC BY 4.0; кредит и исходная страница находятся в данных карточки | `designlab/galaxy-shift/discovery-provenance.json`, `discovery-data.js` |
| Карта неба: каталог HYG 4.1 | [CC BY-SA 4.0](LICENSES/CC-BY-SA-4.0.txt) | `designlab/galaxy-shift/sky-provenance.json` |
| Линии и названия созвездий Stellarium | CC BY-SA 4.0 и [Free Art License 1.3](LICENSES/FAL-1.3.txt); русские переводы — [GPL-2.0-or-later](LICENSES/GPL-2.0.txt) | `designlab/galaxy-shift/sky-provenance.json` |
| Текстура звёздного неба NASA SVS и отдельные материалы NASA | Правила NASA для изображений и медиа; указание NASA как источника обязательно, логотипы не воспроизводятся | `designlab/galaxy-shift/sky-provenance.json`, `discovery-provenance.json` |
| Карточки с научными публикациями, ESA, NRAO и Rubin | Не являются частью MIT-лицензии; исходная страница и кредит указаны для каждого файла | `designlab/galaxy-shift/discovery-provenance.json`, `discovery-data.js` |
| Скриншоты для оформления репозитория | Копии кадров текущей игры: художественные слои — CC BY 4.0 в пределах прав проекта; научные снимки сохраняют условия ESA/Hubble | `docs/repository/art-notes.md`, файлы происхождения игры выше |

Полные тексты свободных лицензий, применённых к материалам пакета, лежат в
`LICENSES/`. При распространении игры сохраняйте этот файл, соответствующие
тексты лицензий и атрибуции в файлах происхождения.

В автономном ZIP эти файлы находятся в его корне: `LICENSE`,
`THIRD_PARTY_NOTICES.md`, `provenance.json`, `discovery-provenance.json` и
`sky-provenance.json`; художественные кредиты — в `assets/art/`. Пути
`designlab/galaxy-shift/` в таблице выше относятся к клону репозитория.

## Художественные иллюстрации

Ночные сцены, Ника и элементы её рабочего места в
`designlab/galaxy-shift/assets/art/` созданы для проекта с помощью
генеративного инструмента OpenAI. В пределах прав, которыми располагают
участники проекта, они предоставляются по [CC BY 4.0](LICENSES/CC-BY-4.0.txt).
Это разрешение относится только к этим иллюстрациям и не распространяется на
научные снимки, отображаемые игрой. Происхождение, даты и промпты сохранены в
`ART-CREDITS.md` и `NIKA-CREDITS.md` рядом с файлами.

## Данные и исторический архив

Снимки и метаданные ZTF/IRSA в `assets/observations/` и
`assets/discoveries/` сохраняют условия и благодарности первоисточников;
они описаны в соответствующих `manifest.json` и `provenance.json`.

`archive/2026-10-09-worktree/` — неизменяемый снимок прежней рабочей папки.
Он не перелицензируется этим репозиторием: встроенные уведомления и лицензии
остаются в его собственных путях.

Ранний прототип в `designlab/comparison/vendor/` включает Phaser
([MIT, Richard Davey и Phaser Studio Inc.](designlab/comparison/vendor/PHASER-LICENSE.md))
и EventEmitter3 ([MIT, Arnout Kazemier](designlab/comparison/vendor/EVENTEMITTER3-LICENSE.txt)).
Их исходные уведомления и тексты лицензий сохранены рядом с поставляемыми
файлами. Этот прототип и его зависимости не входят в текущий автономный ZIP.

## Проверенные первоисточники

* [ESA/Hubble copyright information](https://esahubble.org/copyright/) —
  CC BY 4.0 и требование сохранять полный видимый кредит.
* [NASA Images and Media Usage Guidelines](https://www.nasa.gov/nasa-brand-center/images-and-media/) —
  правила использования материалов NASA, атрибуции и запрет подразумевать
  одобрение NASA.
* [HYG Database](https://github.com/astronexus/hyg-database) и
  [Stellarium skycultures](https://github.com/Stellarium/stellarium) —
  первоисточники данных карты неба.
