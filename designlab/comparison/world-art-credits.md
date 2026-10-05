# Иллюстрации «Ночной смены»

`observatory-v1.png`: сгенерированная вымышленная обсерватория, встроенный image_gen, 2026-10-02. Не научное изображение. Исходный PNG сохраняется без изменений; `tools/prepare_nightshift_art.py` кодирует WebP и встраивает его в `app/nightshift-art.js` для автономной поставки.

## Запрос для обсерватории

Wide illustration for a narrative astronomy browser game, a warm observatory interior at night in high quality modern animated family film style. Huge arched panoramic window frames blue starlit mountains and Milky Way, round brass telescope on the right aimed into the sky, cozy teal chairs, warm honey lamps, paper charts, cat curled asleep. Three stations: archive terminal left, central pair of blank dark screens with rounded chunky instrument panels, corkboard on right with small blank papers. Rich blue teal shadows, painterly cinematic lighting, charming rounded forms, volumetric amber glow. Wide room composition with generous uncluttered upper-left dark space. No people, no text, no letters, no numbers, no logos, no floating interface. This is a beautiful fictional illustration, not scientific imagery.

## Ника

`nika-v1.png`: вымышленный персонаж, встроенный image_gen, 2026-10-02; прозрачность сохранена. Реплики заранее написаны и не являются ответами работающей нейросети.

Character portrait asset for a warm astronomy adventure, modern high quality 3D animated family movie style with painterly polished lighting. Nika, friendly young adult woman astronomer with expressive kind face, short wavy dark brown bob hair, round amber glasses, teal cozy jacket over mustard sweater, small brass star pin. Waist-up three-quarter view facing slightly right, one hand holding small plain notebook close to her waist and other relaxed welcoming gesture. Rounded charming shapes, appealing professional capable character, dark teal and warm honey palette, soft blue rim light and warm key light. Full silhouette within image, generous padding, isolated transparent background. No text, no logo, no symbols beyond small star pin. High quality expressive eyes, clean hands.

## Утренний финал и реакция Ники

`art/observatory-dawn-v1.png` и `art/nika-success-v1.png` созданы встроенным
Imagegen как изменения исходных согласованных иллюстраций. Первая меняет
освещение той же комнаты, вторая — жест и выражение Ники. Исходные PNG
сохранены без изменений. Точные запросы: [art/scene-prompts.md](art/scene-prompts.md).
`prepare-world-art.py` упаковывает варианты в WebP с сохранением альфа-канала
и добавляет в локальный `world-art.js`; прежние ночь и поза Ники сохраняются.
SHA, размеры и цветовые режимы — в `world-provenance.json`.
