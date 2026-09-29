# Teaser 0.1 (v1.16.0)

Teaser de ~31 s (1920x1080, 60 fps, H.264 yuv420p, CRF 18, sin audio) hecho en código con
capturas reales de la app 1.16.0 corriendo en local. Resultado: `out/teaser.mp4` y
`out/contact.png` (2 fps).

## Regenerar

Desde la raíz del repo, con `requirements.txt` + `requirements-dev.txt` en un venv y `ffmpeg`
en el PATH:

```bash
python video/teaser-0.1/demo.py     # datos de demo -> assets/*.png (10) y clicks.json
python video/teaser-0.1/render.py   # index.html cuadro a cuadro -> out/teaser.mp4 + out/contact.png
```

`render.py --frames 4.9,12.5` saca cuadros sueltos a `out/` para revisar sin renderizar todo;
`demo.py --serve` deja el servidor de demo arriba para mirarlo a mano.

## Qué cambió respecto a teaser-0

- **App 1.16.0 y sus funciones nuevas.** Diez capturas en vez de seis: franja
  `🔥 racha · 🛡️ escudos · récord` con la leyenda, panel del día antes y después, ⚙️ con la
  lista de hábitos, días de descanso y Vacaciones, y el mes siguiente con los días rayados.
  Selectores y scrolls revisados: ya no existe la tarjeta "Métricas".
- **Datos de demo nuevos.** Nombre visible "Santi" (`PATCH /api/auth/me` después de
  `seed()`, sin tocar `tests/`); `demo.py` falla si "Yoshio" o un correo aparecen en alguna
  captura. 4 hábitos con ~4 meses de historia, descanso Sáb/Dom, un escudo gastado
  (recarga en N días), una racha vieja más larga que la actual (el récord) y una pausa de
  6 días que empieza mañana. Hoy queda con 3 de 4 hábitos.
- **Nada dibujado encima.** En teaser-0 el hábito marcado era un punto pintado sobre la
  captura. Ahora son dos capturas reales: `02_day_before` ("3 de 4 hoy") y `03_day_after`
  ("4 de 4 hoy"). La app cierra el panel al registrar, así que después del clic real en
  Meditar se reabre el panel con otro clic real en hoy, **con el mismo scroll**: por eso el
  corte en el momento del clic no salta.
- **Montaje por datos.** `index.html` describe la cámara como segmentos (captura + keyframes
  de zoom/foco), los barridos circulares y los clics del cursor como listas; `seek(t)` sigue
  siendo puro. 9 beats: hábitos, marcar el día, configurar, fin de semana (zoom a las
  columnas Sáb y Dom de septiembre), vacaciones (⚙️ → calendario rayado), proyectos,
  reportes, exportar y cierre.
- **Capas.** `#screen` usa `isolation: isolate`: en la primera versión, el `z-index` de las
  capturas se salía de la ventana y la tapaba al cierre morado y al cursor.

## Frágil

- Todo depende del día en que se corre `demo.py`: hoy (29/09) cae a fin de mes, así que la
  pausa se ve en octubre (`nextMonth`); otro día puede caer en el mes actual y cambiar el
  encuadre. Las fechas de la pausa y los fines de semana se leen del DOM, no están fijas.
- La cámara y el cursor se apoyan en `clicks.json`; si cambia el layout de la app hay que
  regenerar las capturas y revisar los desplazamientos en `buildTimeline()`.
- Entorno: igual que teaser-0 (`chromium.sh` con `--no-sandbox` como root, venv por el
  `cryptography` de Debian).
