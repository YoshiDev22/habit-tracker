# Spec: Módulos y costeo de proyectos

> Base: v1.16.1 · Planteado el 2026-09-30 · Épica 24 del [BACKLOG](../../BACKLOG.md).
> Nada de esto está implementado: es el plan acordado antes de escribir código. El esquema
> es un borrador; su impacto en producción se revisa otra vez al empezar cada fase.

## La idea, en limpio

En un trabajo anterior, Yoshio anotaba tareas y tiempos en un kanban. Además de organizar,
eso le servía a la administración para sacar **horas hombre** y, con el historial, cotizar:
*"un proyecto así, con este tamaño y estas features, lleva unas X horas"*, más materiales
y gastos. La app ya hace la primera mitad (tablero, tiempo por tarea, proyecto y etiqueta,
reportes). Le falta la segunda: **dinero y estimación**.

**Esto no es un CRM.** Un CRM gestiona la relación con clientes (prospectos, embudo,
seguimiento). Lo que falta aquí es **costeo de proyectos y cotización basada en el
historial propio**: lo que en la industria se llama PSA (*Professional Services
Automation*) para servicios, y costeo de producción para makers.

## Decisión de producto (2026-09-30)

**Una app de organización y buenas prácticas, hecha de módulos.** No tres apps (personal,
maker, empresa) sino una, donde cada persona activa lo que usa.

| Módulo | Qué trae | Quién lo tiene |
|---|---|---|
| **Núcleo** | Tableros y tareas, tiempo (cronómetro, pomodoro, registro a mano), Reportes | Todos, siempre |
| **Hábitos y metas** | Calendario, racha, escudos, pausas, y las metas de la épica 17 | Activo por defecto; se puede apagar |
| **Costeo** (freelance / maker) | Tarifa, presupuesto, gastos y materiales, estimado contra real, cotizador | Apagado por defecto; se activa |

- **Perfil por defecto** (estudiante, uso personal): Núcleo + Hábitos y metas. Es lo que
  hay hoy más la épica 17.
- **Freelance / maker**: el mismo perfil más Costeo. Puede apagar Hábitos si no los usa.
- **Nada empresarial**: sin equipos, roles, tarifas por empleado, facturación ni
  inventario. La épica 21 (tableros compartidos) sigue aparte y no es requisito de esto.
- **Dos rutas independientes.** Hábitos y metas (épica 17) y Costeo (esta épica) no
  dependen una de la otra: se pueden trabajar en paralelo o en el orden que convenga.
  Solo comparten el interruptor de módulos (Fase 1 de aquí).
- **Nada cuesta.** Los módulos no son planes de pago. Si algún día hay suscripciones, el
  interruptor ya marca la frontera; no se construye nada de cobros ahora.
- **Apagar un módulo no borra nada.** Oculta su pestaña y su UI; los datos siguen ahí y
  vuelven al encenderlo. La misma regla que ocultar un hábito.

### Principios del módulo Costeo

1. **El tiempo sirve para estimar, no para vigilar.** Todo se ve como totales por
   proyecto, tarea o etiqueta. Es la misma filosofía del lado de hábitos: ayudar, no
   presionar.
2. **El historial le gana al plan.** La gente subestima sistemáticamente cuánto tardará
   *ella misma* (ver Referencias), así que el cotizador propone rangos sacados de proyectos
   parecidos ya terminados, no de lo que el usuario cree hoy.
3. **Primero lo manual, después las conexiones.** Capturar o importar un CSV antes que
   integrar Google Drive.
4. **Dinero en centavos enteros**, nunca `float`.

## Qué hay hoy que ya sirve (revisado contra el código, v1.16.1)

| Necesidad | Ya existe |
|---|---|
| Tiempo total por proyecto | `GET /api/projects/summary` (`total_seconds`, tareas hechas/total) |
| Tiempo por tarea | Campo `seconds` de cada tarea (`_task_responses()`), también en proyectos archivados |
| Tiempo por etiqueta | `GET /api/tags/summary` (con `combined_*` para no contar dos veces) |
| Sesiones por rango y proyecto | `GET /api/pomodoro?date_from&date_to&project_id` |
| Tareas terminadas por rango | Filtros `completed_from` / `completed_to` de `GET /api/tasks` |
| Pestañas desde datos | `VIEW_TABS` en `projects.js` (el primer paso de la épica 14 ya está) |
| Tiempo no duplicado | Idempotencia de sesiones (antes backlog 22): requisito para cobrar por hora |

## Fases

Cada fase se puede desplegar sola y deja algo usable.

### Fase 0 — Base sólida ✅ (2026-09-30)

Árbol de dependencias fijado (`requirements.lock`), CI con `pytest`, sesiones de tiempo
idempotentes y límite de intentos en login y registro.

### Fase 1 — Interruptor de módulos + ficha de proyecto (solo lectura)

- **Módulos por usuario**: en **Mi perfil**, casillas "Hábitos y metas" y "Costeo de
  proyectos". Apagar Hábitos oculta la pestaña Calendario (y su parte de Reportes).
- **Ficha de proyecto**: al tocar un proyecto (en Lista o en Organizar) se abre su ficha:
  tiempo total, por tarea, por etiqueta y por mes, y tareas hechas contra totales. Sale
  entera de los endpoints de la tabla de arriba.
- Sin dinero todavía. Útil para cualquiera, esté o no activo Costeo.

### Fase 2 — Tarifa y presupuesto

- Por proyecto: cliente (texto libre, **no** una tabla de clientes), tarifa por hora,
  moneda, presupuesto opcional (monto u horas).
- La ficha suma **mano de obra = horas × tarifa** y, si hay presupuesto, el avance
  ("62 % del presupuesto, 38 % de las tareas").

### Fase 3 — Gastos y materiales

- Renglones por proyecto: fecha, concepto, categoría (material, software, servicio, IA,
  otro), cantidad, costo unitario. Ejemplo real: los ~310 USD de tokens de IA de
  habit-tracker son un gasto de categoría IA.
- **Importar CSV** con vista previa antes de guardar (la misma idea que "Exportar CSV" de
  Reportes, al revés). Cubre el caso "lo tengo en una hoja de Drive": se descarga como CSV
  y se sube.
- La ficha queda completa: mano de obra + gastos = costo; cotizado − costo = margen.

### Fase 4 — Estimado contra real

- Cada tarea puede llevar un estimado en minutos. La tarjeta muestra "2 h de 3 h".
- La ficha y Reportes muestran, por etiqueta, **cuánto se desvía el usuario** (real ÷
  estimado): *"en tareas de backend tardas 1.6× lo que estimas"*. Esta es la "velocidad"
  personal que usa el cotizador.

### Fase 5 — Cotizador con historial

1. Proyecto nuevo: nombre, etiquetas, tareas previstas con su estimado (o sin tareas).
2. La app propone proyectos terminados parecidos (mismas etiquetas, tamaño parecido).
3. Rango de horas **P50 / P80**: los estimados corregidos con las desviaciones reales del
   usuario (Fase 4), o las horas de los proyectos parecidos si no hay estimados.
4. Horas × tarifa + materiales + contingencia (%) = cotización, que se guarda en el
   proyecto como su presupuesto.

Todo lo calcula el backend con los datos del usuario: sin IA y sin inventar cifras. Con
menos de ~3 proyectos parecidos lo dice ("todavía hay poco historial") en vez de fingir
precisión.

### Fase 6 — Hoja de Google publicada como CSV (solo lectura)

- En Google Sheets, *Archivo → Compartir → Publicar en la web → CSV* da una URL pública.
  El proyecto guarda esa URL y el backend la lee al pedirlo, con las mismas columnas que
  la importación de la Fase 3.
- Sin OAuth ni claves de Google. **Riesgo a cuidar**: el backend haría peticiones a una URL
  que escribe el usuario. Solo `https://docs.google.com/spreadsheets/...`, con tiempo
  máximo y tamaño máximo, para que no sirva para sondear la red del VPS.
- La API de Sheets con OAuth (hojas privadas, escritura) queda fuera hasta que alguien la
  pida: exige la verificación de Google y es otra superficie de seguridad.

### Fuera de alcance

Equipos y roles, tarifa de costo por persona, facturas, cobros y suscripciones, inventario
y lotes (lo de Craftybase), CRM (prospectos, embudo), integraciones de escritura.

## Esquema (borrador — avisar el impacto antes de cada fase)

Preferir **tablas nuevas**, que `create_all()` crea solas, a columnas en tablas que ya
existen (esas van en `scripts/migrate.py` y tocan producción).

| Fase | Cambio | Tipo | Migración |
|---|---|---|---|
| 1 | `user_modules` (`user_id`, `module`, `enabled`), único por (usuario, módulo). Sin fila = valor por defecto del módulo | Tabla nueva | No |
| 2 | `project_finance` (`project_id` único, `user_id`, `client_name`, `hourly_rate_cents`, `currency`, `budget_cents`, `budget_minutes`) | Tabla nueva, 1 a 1 con `projects` | No |
| 3 | `project_costs` (`user_id`, `project_id`, `cost_date`, `concept`, `category`, `quantity`, `unit_cost_cents`, `note`) | Tabla nueva | No |
| 4 | `tasks.estimate_minutes` (NULL = sin estimado) | Columna nueva | **Sí**: `migrate.py` + `test_deploy.py` |
| 6 | `project_finance.sheet_csv_url` | Columna en la tabla de la Fase 2 | No, si la Fase 2 aún no salió; si ya salió, sí |

- `project_finance` separada de `projects` para no tocar la tabla vieja y porque solo
  existe para quien usa Costeo.
- Todas con `user_id` y filtradas por `current_user.id`; cada endpoint nuevo por id lleva
  su caso en `tests/test_isolation.py` y sus topes en `tests/test_limits.py`.
- Borrar un proyecto (`DELETE /api/projects/{id}`) tendrá que decidir qué pasa con sus
  gastos: lo natural es borrarlos con él, y avisarlo en la confirmación.

## Decisiones abiertas (preguntar antes de implementar)

1. **Monedas**: ¿solo MXN o una por proyecto? Una por proyecto es un campo; sumar entre
   monedas (convertir) no se hace.
2. **Cotización aceptada o no**: se quitaron los estados de proyecto por falta de uso.
   Propuesta: no volver a ellos; un proyecto con presupuesto y sin tiempo registrado *es*
   una cotización. Confirmar.
3. **Dónde vive la ficha**: ¿modal grande (como el detalle de tarjeta) o vista propia
   dentro de Tableros? El modal es más barato y ya tiene patrón.
4. **Hábitos apagado y Reportes**: ¿se oculta solo la tarjeta de hábitos o también la
   pestaña Calendario? Propuesta: las dos.
5. **Módulos y épica 14** (pestañas por plantillas): el interruptor de módulos es un caso
   particular de "qué pestañas ve cada usuario". Decidir si la Fase 1 deja lista la base
   para la 14 o se mantienen separadas.

## Referencias

La investigación que sostiene los principios 2 y 3 y la forma del cotizador:

- **Buehler, R., Griffin, D. y Ross, M. (1994).** Exploring the "planning fallacy": Why
  people underestimate their task completion times. *Journal of Personality and Social
  Psychology*, 67(3), 366-381. DOI [10.1037/0022-3514.67.3.366](https://doi.org/10.1037/0022-3514.67.3.366).
  Estudiantes que estimaron en promedio 33.9 días para su tesis tardaron 55.5, más que su
  propio peor escenario (48.6). La gente se basa en su plan e ignora su historial.
  **Sostiene:** estimar con el historial propio y dar rangos, no una cifra (Fases 4 y 5).
- **Flyvbjerg, B. (2008).** Curbing optimism bias and strategic misrepresentation in
  planning: Reference class forecasting in practice. *European Planning Studies*, 16(1),
  3-21. DOI [10.1080/09654310701747936](https://doi.org/10.1080/09654310701747936).
  Pronosticar con la distribución real de una "clase de referencia" de proyectos
  parecidos; primer uso práctico en obras de transporte del Reino Unido.
  **Sostiene:** el paso "proyectos parecidos" del cotizador (Fase 5).
- **Spolsky, J. (2007).** [Evidence Based Scheduling](https://www.joelonsoftware.com/2007/10/26/evidence-based-scheduling/).
  Blog, no revisado por pares. Velocidad por persona (estimado ÷ real) y simulación Monte
  Carlo para dar probabilidades de fecha. **Sostiene:** la desviación por etiqueta de la
  Fase 4 y los percentiles P50/P80.

Productos de referencia (cómo resuelven lo mismo, no fuentes científicas): Harvest y
Clockify (tarifa facturable y de costo, estimado contra real; Clockify cobra justamente
tarifas y estimados), Productive.io (PSA completo: cotización → presupuesto → tiempo →
rentabilidad, desde ~24 USD por usuario al mes), Craftybase (lista de materiales +
mano de obra = costo del producto, con inventario).
