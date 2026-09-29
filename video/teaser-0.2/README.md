# Teaser 0.2 (v1.16.0, con audio)

El video de `video/teaser-0.1` con música y efectos sintetizados en código. 31 s, 1920x1080,
60 fps, H.264 + AAC 192 kbps 48 kHz estéreo. La imagen es la aprobada: mismas capturas,
`clicks.json`, encuadres y textos. Solo se movieron dos cortes para caer en el beat:

| Corte | teaser-0.1 | teaser-0.2 | Clic que lo acompaña |
|---|---|---|---|
| Panel "3 de 4 hoy" → "4 de 4 hoy" | 5.20 s | 5.00 s | 5.15 → 4.95 s |
| Tablero → Lista (barrido) | 20.90 s | 21.00 s | 20.65 → 20.75 s |

`demo.py` está solo como referencia: **no se vuelve a correr** (las capturas dependen del día).

## Regenerar (un comando)

Desde la raíz del repo, en el venv con `requirements.txt` y `video/teaser-0.2/requirements-audio.txt`
(numpy; librosa solo para música propia) y `ffmpeg` en el PATH:

```bash
python video/teaser-0.2/build.py              # cues -> cuadros -> audio -> mux -> verificación (~4 min)
python video/teaser-0.2/build.py --no-render  # solo audio + mux + verificación (~20 s)
```

Pasos, cada uno también suelto:

1. `export_cues.py` abre `index.html` y guarda `cues.json` con `window.exportCues()`: cortes,
   barridos, clics, inicios de zoom, cambios de beat, "3 de 4 → 4 de 4", toast y cierre. Salen de
   los mismos `BEATS`/`SEGMENTS`/`WIPES`/`MOVES` que pintan los cuadros: **una sola fuente de
   verdad**. Mover un corte ahí mueve su sonido.
2. `render.py` → `out/video.mp4` (sin audio) y `out/contact.png`.
3. `audio.py` lee `cues.json` → `out/music.wav`, `out/sfx.wav`, `out/mix.wav` y `sfx_plan.json`
   (qué efecto va en qué cue).
4. `build.py` hace el mux sin re-encodear el video (`-c:v copy`).
5. `verify.py` mide todo → `out/verify.json` y `out/waveform.png`.

## Música y efectos

- **Música** (numpy, semilla fija `20260929`, 48 kHz): 120 BPM en Do mayor, un compás = 2 s, así
  que todo corte en segundo entero o medio cae en beat. Pad suave, bajo, marimba con un motivo
  corto, kick suave, hi-hat y palmada ligera. Intro sin percusión (0-3 s), cuerpo (3-26 s), lift
  en "¿Vacaciones?" (14 s: glockenspiel en corcheas, hats en semicorcheas, pad más brillante y un
  riser que termina 50 ms antes del corte), resolución en Do a los 28 s y cola que se apaga antes
  de 31 s. Reverb por convolución con una cola de ruido sembrada.
- **Efectos** (`plan_effects()` en `audio.py`), 15 en total: clic suave en los 2 clics del cursor, chime
  de logro (Mi-Sol-Do) en "4 de 4 hoy", pop en el clic de Exportar CSV y un "ding" cuando aparece
  el aviso de descarga, y un whoosh corto por cambio de escena grande (uno por momento, y ninguno
  justo después de un clic: el barrido Tablero → Lista ya tiene el suyo).
- **Mezcla:** música −5 dB bajo cada efecto (rampas de 20 ms / 250 ms), fade in 0.3 s y fade out
  1 s, un limitador look-ahead solo en los picos necesarios y `loudnorm` en dos pasadas con
  `linear=true` (una ganancia constante, sin compresión dinámica).
- **Reproducible:** dos corridas dan WAVs idénticos byte a byte (comprobado con md5).
- `out/music.wav` y `out/sfx.wav` son los stems a la misma escala, **antes** del ducking, el
  limitador y el loudnorm, para rehacer la mezcla en un editor.

## Mediciones (`out/verify.json`)

**Loudness** del AAC final (`ffmpeg ebur128=peak=true`):

| Integrado | LRA | True peak |
|---|---|---|
| −13.8 LUFS | 3.6 LU | −1.9 dBTP |

(`loudnorm` apunta a −14 LUFS / −1.5 dBTP sobre el WAV, que queda en −13.82 LUFS / −2.24 dBTP;
el AAC sube el pico 0.3 dB.)

**Duración:** video 31.000 s, audio 31.000 s (diferencia 0 cuadros). **Mux:** 0 muestras de
desfase entre `mix.wav` y el AAC (correlación cruzada).

**Efectos contra `cues.json`** (onsets por flujo espectral, saltos de 1 ms):

| Cue | Efecto | Mezcla final | Stem de efectos |
|---|---|---|---|
| 0.40 | whoosh (zoom) | +13 ms | ≤ 2 ms |
| 3.00 · 7.00 · 11.00 · 14.00 · 16.00 · 22.00 · 26.00 · 28.00 | whoosh | −1 a +1 ms (28.00: −2) | ≤ 2 ms |
| 18.00 | whoosh | **no detectado** | ≤ 2 ms |
| 4.95 · 20.75 | clic | −3 / +3 ms | ≤ 2 ms |
| 5.00 | chime | −1 ms | ≤ 2 ms |
| 27.10 · 27.30 | pop · ding | +1 / −1 ms | ≤ 2 ms |

Desfase máximo: **13 ms en la mezcla** (objetivo < 20 ms) y **2 ms en el stem**; 14 de 15
efectos detectados en la mezcla y 15 de 15 en el stem. El whoosh de 18 s está en su sitio
(stem), pero en la mezcla coincide con el kick, el bajo, el cambio de acorde y una nota de
marimba del mismo beat y el detector no lo separa. Probablemente también se oiga poco: si al
escucharlo falta, subir su `gain` en `plan_effects()`. Ojo: los cortes caen en beats, así
que un onset de la música en el mismo instante también "coincide"; la medición que prueba
la colocación es la del stem.

**Cortes del video contra `cues.json`** (diferencia entre cuadros): 3, 5, 7, 11, 14, 18, 22 y
26 s caen en el cuadro exacto (0 ms). El de 5 s es poco visible por naturaleza (solo cambian un
círculo y "4 de 4"): su cuadro destaca ×2 sobre los vecinos; los demás, de ×10 a ×139.

`out/waveform.png`: forma de onda final con los cortes (líneas oscuras, con su tiempo) y los
efectos (marcas naranjas).

## Usar un track propio

```bash
pip install librosa
python video/teaser-0.2/build.py --no-render --music mi_tema.wav [--start 12.0]
```

`replace_music.py` detecta los beats con `librosa.beat.beat_track`, estima el tempo con una
regresión lineal sobre todos los tiempos de beat (más fina que el tempo que da librosa), elige la
octava más cercana a 120 BPM (medio o doble tiempo), estira la pista a 120 BPM
(`librosa.effects.time_stretch`) y la desplaza para que un beat caiga en el primer corte (3 s).
`--start` elige desde qué segundo de tu pista empezar. Efectos, ducking, fades, loudness y
verificación son los mismos. El comando imprime a cuántos ms del beat más cercano de tu pista
queda cada corte.

Probado con la propia música ralentizada a 108 BPM: tempo detectado 108.0, estirada ×1.111, y
los cortes de 3 a 26 s quedan a ≤ 13 ms de un beat (la resolución de librosa es ~11 ms). El de
28 s sale a ~500 ms solo porque en esa pista la percusión termina a los 28 s. Para quedarte con
un track propio, deja su archivo fuera del repo si su licencia no permite redistribuirlo.

## Frágil

- Cambiar un tiempo en `buildTimeline()` exige volver a correr `build.py` completo: los cues y el
  audio salen de ahí.
- Los efectos coinciden con beats de la música a propósito, así que el detector de onsets de la
  mezcla es optimista; la medición en el stem es la estricta.
- Entorno igual que teaser-0.1 (`chromium.sh` con `--no-sandbox` como root, venv por el
  `cryptography` de Debian); numpy y librosa van en el venv, no en `requirements.txt`.
