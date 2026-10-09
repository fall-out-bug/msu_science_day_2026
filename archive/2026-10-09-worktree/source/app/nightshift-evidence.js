// Generated offline by tools/prepare_nightshift_evidence.py; coordinates are PNG pixel centers.
window.NIGHTSHIFT_EVIDENCE = {
  "s02": {
    "width": 128,
    "height": 128,
    "targets": [
      {
        "x": 41.6921,
        "y": 82.5012
      },
      {
        "x": 58.1446,
        "y": 68.3167
      },
      {
        "x": 90.9321,
        "y": 39.8547
      }
    ],
    "kind": "motion",
    "note": "Измеренные центроиды в каждой экспозиции; положение сверено с эфемеридой. Это не оценка точности орбиты.",
    "source": "assets/observations/motion-fields/_research/acquire_report.json: mover1.meas.measured; manifest.json: mover1.skybot"
  },
  "s08": {
    "width": 128,
    "height": 128,
    "targets": [
      {
        "x": 122.0,
        "y": 74.0
      },
      null,
      null
    ],
    "kind": "artifact",
    "note": "Точка на помехе: максимум положительной разности внутри области, подтверждённой исходной маской ZTF. В других кадрах помехи здесь нет; точка не обозначает физический центр следа.",
    "source": "assets/observations/manifest.json: artifact_track.mask_evidence; cached ZTF sciimg/mskimg WCS"
  },
  "s10": {
    "width": 128,
    "height": 128,
    "targets": [
      {
        "x": 63.5,
        "y": 63.5
      },
      {
        "x": 63.5,
        "y": 63.5
      },
      {
        "x": 63.5,
        "y": 63.5
      }
    ],
    "kind": "photometry",
    "note": "Каталожная позиция источника на общей WCS-сетке; изменение блеска подтверждено независимой фотометрией, а не яркостью одного пикселя.",
    "source": "assets/observations/manifest.json: weakmid1.ra/dec, epochs, epoch_mags; tools/realdata.py: target_wcs"
  },
  "s01": {
    "width": 128,
    "height": 128,
    "targets": [
      {
        "x": 60.0,
        "y": 29.0
      },
      {
        "x": 60.0,
        "y": 29.0
      },
      {
        "x": 60.0,
        "y": 29.0
      }
    ],
    "controls": [
      {
        "x": 98.0,
        "y": 95.0
      }
    ],
    "kind": "comparison",
    "note": "Яркая звезда с измеренным почти постоянным апертурным потоком; это опорная точка сравнения, а не найденная аномалия.",
    "source": "assets/observations/curated-provenance.json: normal_1.measured_sources"
  },
  "s07": {
    "width": 128,
    "height": 128,
    "targets": [
      {
        "x": 36.537,
        "y": 72.8942
      },
      {
        "x": 59.0423,
        "y": 65.5003
      },
      {
        "x": 95.47,
        "y": 53.1346
      }
    ],
    "kind": "motion",
    "note": "Измеренные центроиды в каждой экспозиции; положение сверено с эфемеридой. Это не оценка точности орбиты.",
    "source": "assets/observations/motion-fields/_research/acquire_report.json: mover2.meas.measured; manifest.json: mover2.skybot"
  },
  "s11": {
    "width": 128,
    "height": 128,
    "targets": [
      {
        "x": 63.5,
        "y": 63.5
      },
      {
        "x": 63.5,
        "y": 63.5
      },
      {
        "x": 63.5,
        "y": 63.5
      }
    ],
    "kind": "photometry",
    "note": "Каталожная позиция источника на общей WCS-сетке; изменение блеска подтверждено независимой фотометрией, а не яркостью одного пикселя.",
    "source": "assets/observations/manifest.json: variable1.ra/dec, epochs, epoch_mags; tools/realdata.py: target_wcs"
  },
  "s04": {
    "width": 128,
    "height": 128,
    "targets": [
      null,
      {
        "x": 63.0,
        "y": 64.0
      },
      null
    ],
    "kind": "artifact",
    "note": "Точка на помехе: максимум положительной разности внутри области, подтверждённой исходной маской ZTF. В других кадрах помехи здесь нет; точка не обозначает физический центр следа.",
    "source": "assets/observations/manifest.json: artifact_spike.mask_evidence; cached ZTF sciimg/mskimg WCS"
  },
  "s06": {
    "width": 128,
    "height": 128,
    "targets": [
      {
        "x": 63.5,
        "y": 63.5
      },
      {
        "x": 63.5,
        "y": 63.5
      },
      {
        "x": 63.5,
        "y": 63.5
      }
    ],
    "controls": [
      {
        "x": 18.0,
        "y": 52.0
      },
      {
        "x": 107.0,
        "y": 87.0
      }
    ],
    "kind": "photometry",
    "note": "Каталожная позиция источника на общей WCS-сетке; изменение блеска подтверждено независимой фотометрией, а не яркостью одного пикселя.",
    "source": "assets/observations/manifest.json: weak1.ra/dec, epochs, epoch_mags; tools/realdata.py: target_wcs; manifest.json: weak1.aperture_check.comparison_stars"
  },
  "s03": {
    "width": 128,
    "height": 128,
    "targets": [
      null,
      {
        "x": 63.5,
        "y": 63.5
      },
      {
        "x": 63.5,
        "y": 63.5
      }
    ],
    "kind": "photometry",
    "note": "Каталожная позиция SN 2023tyk. На обычном снимке свет смешан с соседним источником в 2,4″; это не отдельный центроид SN. В первом кадре нет измерения SN: null. Октябрьская и ноябрьская точки имеют разностную PSF-фотометрию.",
    "source": "assets/observations/manifest.json: sn2023tyk.ra/dec, epochs, photometry_alerce; tools/realdata.py: target_wcs"
  }
};
