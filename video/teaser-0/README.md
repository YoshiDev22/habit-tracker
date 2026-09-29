# Teaser 0 (prueba de flujo)

Teaser de ~20 s (1920x1080, 60 fps, H.264 yuv420p, CRF 18, sin audio) hecho en código con
capturas reales de la app corriendo en local. Resultado: `out/teaser.mp4` y `out/contact.png`
(2 fps).

## Regenerar

Desde la raíz del repo, con las dependencias de `requirements.txt` + `requirements-dev.txt`
y `ffmpeg` en el PATH:

```bash
python video/teaser-0/demo.py     # base 1.9 migrada + datos de demo -> assets/*.png y clicks.json
python video/teaser-0/render.py   # index.html cuadro a cuadro -> out/teaser.mp4 + out/contact.png
```

- `demo.py` reutiliza `tests/ui` (`conftest._prepare_db`, `ui_board.seed()`, `cdp.py`), levanta
  uvicorn en un puerto libre sobre una SQLite temporal y siembra 5 hábitos (6 semanas, racha 42),
  el proyecto "Tesis" en las tres columnas y ~30 días de sesiones. Nada toca producción ni tu `.env`.
  `--serve` deja el servidor arriba para mirarlo a mano.
- `index.html` es el montaje: todo sale de `window.seek(t)` (sin timers, transiciones CSS ni azar).
  Para ver un cuadro: servir la carpeta y abrir `index.html#t=4.5`. `render.py --frames 4.5,15.6`
  saca cuadros sueltos a `out/`.
- `clicks.json` tiene, en px CSS del viewport 1280x800, el centro del elemento clave de cada captura
  (lo usan la cámara y el cursor), más el nombre real del CSV exportado.

## Lo más difícil o frágil

- **Entorno Linux como root:** `cdp.py` lanza Chromium sin `--no-sandbox` y como root se niega a
  arrancar; `chromium.sh` lo añade sin tocar el driver. Además el `cryptography` del sistema
  (Debian) hace pánico al importar `python-jose`: hubo que usar un venv limpio.
- **Las capturas dependen del día.** Las fechas son relativas a hoy (la racha, "Septiembre 2026",
  el día marcado); regenerar otro día cambia el contenido, y a principio de mes el calendario y el
  reporte mensual se ven casi vacíos.
- **800 px de alto no alcanzan** para calendario + racha: `demo.py` hace scroll antes de las capturas
  1 y 2, y el popover del día depende de la celda de hoy (en la última fila cae fuera sin ese scroll).
- **Las coordenadas son frágiles:** cámara, cursor y el punto de color de "marcar hábito" se apoyan
  en `clicks.json`. Si cambia el layout de la app, hay que regenerar las capturas y revisar los
  offsets a mano (el punto del hábito se dibuja encima de la captura, no es la app real).
- **Nitidez:** el botón "Exportar CSV" mide 91x14 px; con zoom 2.7x pixelaba. Las capturas son del
  viewport 1280x800 pero a `deviceScaleFactor` 2 (PNG de 2560x1600).
- La fuente Inter (OFL) va en `assets/fonts/` para que el render no dependa de la red.
