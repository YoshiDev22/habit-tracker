# Spec: Calendario v2

> Base: v1.15.0 · Mockup de referencia: artifact "Franja de racha" (hecho sobre v1.5.0 con 6
> hábitos; la lógica aplica igual a 4). La tabla de estado sale del código, no del mockup.

## Objetivo

Que el usuario entienda de un vistazo su avance (racha, protectores, récord), que lo que ve en
el calendario coincida con lo que cuentan las métricas, y que ninguna acción borre datos sin
avisar.

## Estado en v1.15.0 (revisado contra el código)

| Tema | Qué hace hoy |
|---|---|
| Colores por hábito | Cada hábito guarda su color (`habits.color`), pero **nada impide repetirlo**: dos hábitos personalizados nacen con el mismo gris y uno sin color usa el azul por defecto. |
| Posición = hábito | Los puntos de un día son solo los hábitos **activos**, en orden `(order, id)`. `order` siempre se guarda en 0, así que en la práctica es el orden de creación. |
| Fila de puntos | Puntos de 6 px con 3 px de separación en 40 px: caben **4**; con 5 ya salta a dos filas. |
| Días de descanso | Días de la semana que elige cada usuario (`users.rest_days`), no fijos. La celda se atenúa solo si ese día no tiene hábitos; con alguno marcado se ve y cuenta normal. |
| Protectores 🛡️ | Máximo 2 (`SHIELD_MAX`). Se gana uno por cada 7 días hechos de racha (`SHIELD_EVERY`), **no por tiempo**. Se gastan **solos** al fallar un día que no es de descanso. Anotar tarde un día devuelve su protector. El día cubierto lleva 🛡️ en la esquina. |
| Racha | Días con al menos un hábito marcado, **ocultos incluidos**. Hoy sin marcar no corta; descanso y día protegido congelan. Todo en `_walk_streak()` (`routers/habits.py`). |
| Récord | Existe (`best_streak`), pero solo lo devuelve `GET /api/habits/report`; `GET /api/habits` y `/streak` no. |
| Métricas derivadas | Racha, récord y protectores se recalculan desde cero en cada consulta; no se guardan. |
| Métricas del Calendario | Tarjeta de racha (🔥 N días seguidos + los dos escudos con "Recarga en N días") y "Este mes". La barra del mes muestra un % sin etiqueta. No hay métrica acumulada tipo "47 días". |
| Ocultar / restaurar | `is_active = false`. Conserva registros y siguen contando para la racha, pero sus puntos desaparecen de **todos** los meses y los hábitos que venían después se corren un lugar. Restaurar lo devuelve con su historial a su lugar `(order, id)`. |
| Borrar | Solo desde "Anteriores u ocultos", con confirmación. Quita su clave de todos los días (para siempre) y borra la definición; racha, récord y protectores se recalculan sin avisar. |
| Guardar un día | Desde la Fase 0, marcar o desmarcar cambia un solo par (hábito, día): `PATCH /api/habits/day/{fecha}`. |
| Pestaña de historial | "Reportes". "Proyectos" ahora es "Tableros". |

## Problemas detectados en v1.15.0

1. **Pérdida de datos (bug) — corregido en la Fase 0.** Si un día tenía marcado un hábito oculto y uno activo, y se desmarcaba el activo en el popover, se guardaba el día vacío y se borraba el registro del oculto sin aviso. Causa: el frontend guardaba el día completo a partir de lo que veía (solo activos). Lo mismo pisaba lo que otro dispositivo hubiera guardado ese día.
2. **Pantalla y cifra no coinciden.** Un hábito oculto desaparece de todos los meses, incluso los pasados, pero sus días siguen contando para la racha. Un día donde solo hiciste el oculto se ve gris y aun así suma.
3. **Borrar cambia el pasado sin avisar.** Como todo se recalcula, borrar un hábito puede convertir días en fallados, gastar protectores retroactivamente, cortar la racha y bajar el récord. La confirmación solo menciona el historial.

## Decisiones tomadas

| Tema | Decisión |
|---|---|
| Descanso y racha | La racha **se congela**: no sube ni se rompe. Si ese día sí se marca un hábito, cuenta normal. |
| Protector y racha | Mismo comportamiento que descanso: congela. |
| Protector: consumo y recarga | Se consume solo al fallar un día; se recarga con 7 días hechos; máximo 2. Así funciona desde 1.15.0. |
| Hábitos ocultos y racha | **Siguen contando.** Ocultar no debe castigar retroactivamente. |
| Hábitos ocultos en el calendario | **Cada mes muestra los hábitos activos + los ocultos que tengan al menos un registro en ese mes**, en su posición de orden. Así la pantalla coincide con la racha. La leyenda del mes se genera de la misma lista. |
| Orden | Calendario, leyenda, tarjetas y popover usan el mismo orden, desde una sola fuente: `(order, id)`, el mismo que usa restaurar para devolver un hábito a su lugar original. Un hábito nuevo va al final. Reordenar se permite solo como acción deliberada del usuario. |
| Colores | Al crear un hábito se preselecciona un color no usado de una paleta fija de ~8. Si el usuario elige uno repetido, se avisa pero se permite. La identidad la da la posición, no el color. |
| Borrar | La confirmación muestra el impacto calculado: registros que se pierden y cómo cambian racha y récord. |
| Guardar un día | Marcar o desmarcar toca **un solo par (hábito, día)**; nunca se reescribe el día completo. |
| Día cumplido | Al menos 1 hábito marcado, activo u oculto (`MIN_HABITS_FOR_DONE_DAY = 1`). Es la regla que ya aplica la racha. |
| Recarga de escudos | "Recarga en N días" **visible** bajo los escudos, también en la franja; no en un tooltip (en el teléfono no se vería). |
| Constancia (%) | **Eliminada.** Había que explicar qué hábitos y qué días cuentan, y un porcentaje no dice nada concreto. Reportes ya da "N de M días" por hábito. |
| Métrica acumulada ("47 días") | No existe en la app (venía del mockup); nada que quitar. |
| Ubicación de métricas | Franja compacta arriba del calendario: `🔥 racha · 🛡️ escudos · récord`. "Este mes" se queda en Calendario. El historial va en "Reportes". |
| Leyenda | Justo debajo del calendario, con la misma geometría que los puntos. |
| Puntos por fila | Una fila hasta 5 (activos + ocultos con registros en el mes); con 6 o más, dos filas parejas. |

## Decisiones abiertas (preguntar antes de implementar)

- [ ] **Descanso suelto**: propuesta = no; los protectores cubren ese caso.

## Definiciones de métricas

Todas en backend, con constantes nombradas. Siguen siendo derivadas (recalculadas desde los registros); no introducir valores guardados.

- **día cumplido**: día con `>= MIN_HABITS_FOR_DONE_DAY` hábitos marcados, incluidos los ocultos.
- **racha actual**: días cumplidos consecutivos hasta hoy. Días de descanso y protegidos sin hábitos → no rompen, no suman. Hoy sin marcar todavía no rompe la racha.
- **récord**: la racha más larga del historial, misma regla.
- **protectores**: uno por cada `SHIELD_EVERY` (7) días hechos de racha, hasta `SHIELD_MAX` (2); un día fallado gasta uno en vez de cortar.

## Tareas

### Fase 0 — Integridad de datos ✅ (`48e3162`)
- [x] Test que reproduce el bug (`tests/ui/ui_hidden_habit_record.py`): día con hábito oculto + activo, desmarcar el activo → el registro del oculto sigue existiendo. También cubre lo guardado por otro dispositivo. Falló antes del fix.
- [x] Fix: `PATCH /api/habits/day/{fecha}` con `{habit_key, done}` opera sobre **un par (hábito, día)**. El backend solo cambia esa clave.
- [x] Revisados los otros lugares: el único otro que guardaba el día completo era "¿Olvidaste anotar ayer?"; ahora también marca uno por uno. `POST /api/habits` queda por compatibilidad y la pantalla no lo usa.

### Fase 1 — Backend de métricas y ocultos ✅
- [x] `MIN_HABITS_FOR_DONE_DAY = 1` en un solo helper (`_is_done_day()`) que usan la racha, el reporte y el impacto de borrar.
- [x] `best_streak` también en `GET /api/habits` y `/streak`: la franja lo necesita.
- [x] `GET /api/habits/month-habits?year=&month=`: los hábitos a mostrar en un mes (activos + ocultos con registros en ese mes), en orden `(order, id)`, con nombre, emoji, color e `is_active`.
- [x] Un hábito nuevo va al final (`order = máximo + 1`, ocultos incluidos); la pantalla ya no manda `order: 0`. Los existentes (todos en 0) se desempatan por id: no hace falta tocar datos.
- [x] `GET /api/habits/definitions/{id}/delete-impact`: registros que se pierden, racha y récord antes y después. Solo calcula.
- [x] Tests: racha normal, cruce de fin de semana, cruce de día protegido, descanso con hábito marcado, hoy sin marcar, récord ≠ racha actual, día con solo un hábito oculto, lista por mes con ocultos, orden de un hábito nuevo, impacto de borrar.

### Fase 2 — Ocultos y borrar en la UI ✅
- [x] Puntos del calendario, popover y "Este mes" usan la lista por mes de la Fase 1 (`habitsForMonth()` en `script.js`, con caché por mes). Un oculto se ve en los meses donde tiene registros, en su lugar; atenuado en popover ("oculto") y en "Este mes". La leyenda la usará igual cuando exista (Fase 4).
- [x] Puntos: una fila hasta 5; con 6 o más, dos filas parejas (`--dots-per-row`).
- [x] Confirmación de borrar con el impacto: "Se borrarán sus N registros… Tu racha pasaría de X a Y días y tu récord, de A a B."
- [x] Color: paleta fija de 8 (`HABIT_PALETTE`); al añadir un hábito se preselecciona uno libre (ocultos incluidos) y, si se repite, un aviso que no bloquea.

### Fase 3 — Franja y barra (un commit)
- [ ] Quitar la tarjeta grande de racha de Métricas.
- [ ] Franja entre navegador de mes y barra: `🔥 18 racha · 🛡️ 1 · récord 21` (valores de ejemplo). Números 600 + `tabular-nums`; etiquetas en gris; 🔥 en `#f2a33c`; wrap en móvil.
- [ ] "Recarga en N días" visible bajo los escudos de la franja, en pequeño; sin texto cuando hay 2.
- [ ] Barra del mes con etiqueta "MES". Si "Este mes" repite el dato, dejar solo uno.

### Fase 4 — Calendario y leyenda (un commit)
- [ ] Días futuros: puntos con `opacity: .16`.
- [ ] Leyenda debajo del calendario con la misma geometría que los puntos: punto + nombre, 10.5px, gris, `text-overflow: ellipsis`.
- [ ] Tarjetas "Este mes" en el mismo orden y columnas que los puntos, con racha propia (🔥n) si es > 0.
- [ ] Distinguir día de descanso de día protegido además del ícono.

### Fase 5 — Popover del día (un commit)
- [ ] Círculo en el color del hábito: contorno (`opacity .55`) sin marcar; relleno + halo marcado.
- [ ] Pie: "N de M hoy".
- [ ] Orden idéntico al de los puntos.

### Fase 6 — Reportes (después, spec aparte)
Récords históricos por hábito, comparativa entre meses, uso de protectores.

## Criterios de aceptación

- Ninguna acción de la UI borra registros de un hábito que el usuario no tocó.
- Todo día que suma a la racha tiene al menos un punto visible en el calendario.
- A 390px de ancho, franja + barra + calendario completo + leyenda caben sin scroll.
- Ningún número en pantalla aparece sin etiqueta que diga qué mide.
- La posición N del punto = hábito N en leyenda, popover y tarjetas, en cada mes.
- Todos los tests pasan.
