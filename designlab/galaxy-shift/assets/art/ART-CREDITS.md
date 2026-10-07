# Текущий выпуск: ночная обсерватория v2

`observatory-night-v2.png` — единая сцена с Никой, мебелью, согласованным освещением и тенями. `worktop-night-v2.png` — крупный план её стола. Обе созданы встроенным image_gen 7 октября 2026 года; это художественные иллюстрации, а не снимки наблюдений. Точные промпты и референсы — [NIGHT-V2-PROMPTS.md](NIGHT-V2-PROMPTS.md). Интерактивная карта использует отдельный научный атлас NASA SVS и звёздный каталог HYG: `../../sky-provenance.json`. Неподвижные звёзды за окном — часть художественной сцены, не карта наблюдений.

SHA-256 текущих ресурсов фиксирует `build.json` в сборке. Прежние дневные иллюстрации ниже сохранены в истории, но не входят в текущий пакет.

---

# Графика лаборатории

Это художественная сцена современной астрономической лаборатории, а не фотография конкретного учреждения или участка Кавказа. Независимые элементы скомпонованы в Canvas: фон, Ника и рабочий стол; крупный план стола — отдельный фон. Файлы image_gen скопированы без обработки. Реальные снимки на мониторах добавляет renderer из принятого набора Hubble (`child_ic5332`, `child_ngc5023`); они не нарисованы генератором. Источники и атрибуция всех научных снимков — в `provenance.json`.

Техника современная: плоские мониторы, клавиатура и мышь, LED-лампа, стальной каркас стола. Небольшой ретро-намёк дают часы, блокнот и бумажные карточки. На сцене нет утки, робота, армиллярной сферы или декоративных выдуманных научных данных.

| Файл | Источник | SHA-256 |
| --- | --- | --- |
| `nika.png` | image_gen, 2026-10-02; прежний отдельный персонаж с прозрачностью | `0c4632271142a2d3688bd42c751f8211c2066a31b649491d02544e544541ebee` |
| `laboratory-modern-v1.png` | image_gen, 2026-10-07; непрозрачный фон | `fb20c6b39544c8f22d22d2c087042bac7f9970db8d75388c22cad55992c78052` |
| `workstation-modern-v1.png` | image_gen, 2026-10-07; отдельный стол, сохранён alpha | `16015d27bb141d36bd49015bdc0e1035dcf630acba64b4cf9e95460cbccb3e56` |
| `worktop-modern-v1.png` | image_gen, 2026-10-07; крупный план пустой поверхности | `0272e43e898494981259d0679a7de169acfb6f309e532e716732c86ed2a3557e` |

## Промпты современных элементов

### Фон лаборатории

Generate one independent background element for a polished children's astronomy research game. Contemporary real-world astrophysics laboratory/control room in the Caucasus mountains, warm cinematic family-animation rendering, physically plausible modern materials, teal, ivory, and restrained honey palette. Wide 16:9 architectural interior, fixed eye-level three-quarter view. Huge panoramic windows show green slopes, snow peaks and a small modern observatory dome far away. Empty central foreground/floor reserved for separate workstation and character sprites. At far left a sleek contemporary research archive cabinet with flat ivory fronts and brushed aluminum handles, a small modern unlit display above it. At far right a clean magnetic research board with just subtle blank paper rectangles, no invented scientific images. Modern timber window framing and pale floor, soft daylight, inviting human workspace. Only a very slight retro hint in a small analog wall clock. No brass globes, no armillary spheres, no steampunk, no antique cabinets, no decorative stars or invented graphs, no readable text, no logos, no foreground desk, no computers in the foreground, no chair, no people, no robot, no duck. This is the independent room backdrop ONLY. Science-modern, beautiful and believable, not futuristic fantasy. Fully opaque.

### Рабочий стол

Generate ONE independent compositing sprite for a polished family astronomy browser game: a contemporary astrophysics workstation on a truly transparent background. Warm pale ivory modern desk with sleek steel support legs and a compact low cabinet on the right. Two slim black-framed flat monitors with entirely BLANK DARK TEAL screens, tilted only slightly inward and facing the viewer clearly; nothing drawn on the screens because actual scientific images will be added by the game. A slim keyboard, optical mouse, one small closed research notebook, and a minimal white modern LED task lamp on the right. Polished warm cinematic animation rendering with physically plausible materials, soft rounded corners, daylight from upper left. Eye-level three-quarter viewpoint looking slightly down at tabletop, full legs and every item in frame with comfortable transparent padding. No chair, no floor, no room, no backdrop plane, no galaxy pictures on screens, no brass, no armillary spheres, no globe, no antiquated instruments, no steampunk, no character, no robot, no duck, no readable text, no logos. Modern working scientific equipment with only the paper notebook hinting at old school practice. This is a single foreground PROP element, not a complete scene. Preserve genuine alpha.

### Крупный план стола

Generate one independent environment background layer for a polished family astronomy puzzle browser game: close-up of a contemporary astrophysics workstation surface, wide 16:9. Viewpoint slightly above the table, looking down at a large empty pale ivory work surface with subtle satin finish, gentle natural texture, beveled front edge. Warm cinematic family-animation art style, physically plausible materials, soft daylight from upper left, teal and ivory palette with restrained warm accents. Table fills lower 85% of picture; upper15% has a narrow blurred Caucasus mountain window, cropped backs of thin modern black monitors on the upper left and a sleek small white LED task lamp on the extreme upper right. At lower-right edge only a tiny slim dark teal notebook and one ordinary pencil may provide an understated old-school hint. CENTRAL SURFACE IS COMPLETELY EMPTY because actual galaxy photos and controls will be added by the game independently. No brass, no armillary spheres, no globes, no antique instruments, no steampunk, no fake scientific pictures, no paper sheets, no UI controls, no text, no labels, no diagrams, no characters, no robot, no mascot, no logos. This is ONLY a contemporary desk surface layer, inviting and beautiful, not an interface mockup. Fully opaque.

Образ Ники и его исходный промпт — в `NIKA-CREDITS.md`. Реплики написаны заранее и не являются ответами работающей разговорной модели.
