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
- **Plan maker con acceso (decidido 2026-10-01).** Costeo se presenta como el **plan
  maker**: mismas funciones de base, más las de costeo. Es gratis, pero por ahora solo lo
  encienden las cuentas a las que se les da acceso (`scripts/grant_module.py`), empezando
  por la de Yoshio. Los códigos de invitación vienen cuando se quiera dar a más gente.
  Quizá donaciones más adelante; cobrar solo tendría sentido si se añaden APIs de IA de
  pago, para cubrir ese costo. En la app se llama "Maker", no "Pro".
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
| Pestañas por id | `VIEWS` y `setViewVisible()` en `projects.js` (ocultar una vista sin correr las demás) |
| Tiempo no duplicado | Idempotencia de sesiones (antes backlog 22): requisito para cobrar por hora |

## Fases

Cada fase se puede desplegar sola y deja algo usable.

### Fase 0 — Base sólida ✅ (2026-09-30)

Árbol de dependencias fijado (`requirements.lock`), CI con `pytest`, sesiones de tiempo
idempotentes y límite de intentos en login y registro.

### Fase 1 — Interruptor de módulos + ficha de proyecto (solo lectura) ✅ (1.17.0)

- **Módulos por usuario** (`backend/modules.py`, tabla `user_modules`): en **⚙️ Configuración ›
  Módulos**, la casilla "Hábitos y metas". Apagarla oculta la pestaña
  Calendario, las secciones de hábitos de Configuración y su tarjeta de Reportes, y no pide nada de hábitos. El
  módulo `maker` ya existe con acceso por cuenta (`allowed`), y la API responde 403 si se
  enciende sin él; **su casilla llega con la Fase 2**, cuando haga algo.
- **Ficha de proyecto** (`GET /api/projects/{id}/overview`, `project-overview.js`), en un
  modal: tiempo total, por tarea, por etiqueta y por mes, y tareas hechas contra totales.
  Se abre al tocar un proyecto en la Lista (con ✎ Editar dentro) y con 📊 en Organizar.
  Un endpoint propio en vez de juntar los de la tabla de arriba: una sola consulta, con su
  prueba de que cuadra con `/summary`, y la base para sumarle dinero en la Fase 2.
- Antes, dos refactors que lo hicieron posible: los hábitos salieron de `script.js` a
  `habits.js`, y las vistas se nombran por id (`setViewVisible()`).
- Sin dinero todavía. Útil para cualquiera, esté o no activo el plan maker.

### Fase 2 — Tarifa y presupuesto ✅ (1.18.0)

- Por proyecto (`project_finance`, `GET`/`PUT /api/projects/{id}/finance`): cliente
  (texto libre, **no** una tabla de clientes), tarifa por hora, moneda (una de una lista
  cerrada) y presupuesto opcional en dinero y/o en horas. 403 sin el plan maker encendido.
- La ficha, en su tarjeta **Costeo**, suma **mano de obra = horas × tarifa** y, si hay
  presupuesto, su avance en dinero y en horas, con barras (en rojo al pasarse). Las tareas
  hechas contra totales ya estaban en el Resumen de la ficha.
- Con presupuesto y sin tiempo, la etiqueta **Cotización**. "Sin asignar" no se costea.
- La casilla **Maker** aparece en ⚙️ Configuración › Módulos para las cuentas con acceso.

### Fase 3 — Gastos y materiales ✅ (1.19.0)

**Decidido (2026-10-01):**

- **Pestaña propia, "Costos"**, junto a Calendario, Tableros y Reportes, visible solo con
  el plan maker encendido (`setViewVisible`). Arriba, el resumen por proyecto (horas, mano
  de obra, gastos, costo, presupuesto y margen, agrupado por moneda) y por categoría;
  abajo, la hoja de gastos del proyecto elegido, que se edita como una hoja de cálculo.
- **Pegar desde Excel o Google Sheets**: un rango copiado llega como texto separado por
  tabuladores; se pega en la hoja y se ve en una vista previa antes de guardar. Lo mismo
  con un archivo CSV. Sin conectar con Google (eso es la Fase 6).
- **Solo gastos por proyecto.** Para lo general (una licencia que sirve a todo), un
  proyecto "Gastos generales".
- **Borrar un proyecto borra sus gastos**, y la confirmación lo avisa. Archivar conserva.
- **Categorías del usuario**, como las etiquetas: cada cuenta recibe cinco al entrar por
  primera vez (material, licencia/software, servicio, IA, otro) y las renombra, pinta,
  ordena o crea. Una categoría con gastos no se borra (409 con el motivo, como las
  columnas).

- Renglones por proyecto: fecha, concepto, categoría, cantidad, costo unitario. Ejemplo real: los ~310 USD de tokens de IA de
  habit-tracker son un gasto de categoría IA.
- **Importar CSV** con vista previa antes de guardar (la misma idea que "Exportar CSV" de
  Reportes, al revés). Cubre el caso "lo tengo en una hoja de Drive": se descarga como CSV
  y se sube.
- La ficha queda completa: mano de obra + gastos = costo; cotizado − costo = margen.

### Fase 4 — Estimado contra real ✅ (1.19.0)

> **Hecha** (2026-10-02; sale en la 1.19.0 junto con la Fase 3). Es la primera fase que
> agrega una **columna a una tabla existente**: leer "Impacto en producción" antes de
> desplegar. Las preguntas quedaron cerradas el 2026-10-01: ver "Decisiones de la Fase 4"
> al final de esta fase. Lo que se apartó del plan: la ficha de "Sin asignar" también trae
> `estimates` (el desvío no es dinero), y la prueba de navegador es una sola,
> `ui_card_estimate.py`, que cubre tarjeta, Lista, ficha y Costos.

- Cada tarea puede llevar un estimado en minutos. La tarjeta muestra "2 h de 3 h".
- La ficha y la pestaña **Costos** muestran, por etiqueta, **cuánto se desvía el usuario**
  (real ÷ estimado): *"en tareas de backend tardas 1.6× lo que estimas"*. Esta es la
  "velocidad" personal que usará el cotizador de la Fase 5. (La primera versión de este
  texto decía "la ficha y Reportes"; la aceptación del backlog y este plan dicen Costos.)

#### Impacto en producción

- **Columna nueva en `tasks`**: `estimate_minutes INTEGER`, NULL = sin estimado. En
  `models.py`, `Task.estimate_minutes: Optional[int] = Field(default=None)`, con el
  comentario "Columna AÑADIDA: migrate.py" como `column_id`.
- **`scripts/migrate.py`**: entrada nueva al final de `MIGRATIONS`,
  `{"table": "tasks", "column": "estimate_minutes", "type": "INTEGER"}`, sin `default`:
  nace NULL y ninguna tarea vieja queda con un estimado inventado. Sin índice (nada filtra
  por esta columna), así que `INDEXES` no cambia.
- **`check_pending_migrations()`** (`backend/database.py`) lee `MIGRATIONS` del propio
  script: sin migrar, la app se niega a arrancar y el log nombra `tasks.estimate_minutes`.
  No hay que tocar `database.py`.
- **`tests/test_deploy.py`**: en `test_the_app_refuses_to_start_without_migrating`, que la
  salida del primer `migrate.py` incluya `tasks.estimate_minutes` (y la segunda corrida
  siga diciendo "nothing, already up to date"); en
  `test_old_data_survives_and_is_placed_on_a_board`, que las tareas de la base de la 1.9
  devuelvan `estimate_minutes: null`.
- **Deploy**: `git pull` → `.venv/bin/pip install -r requirements.lock` →
  `python3 scripts/migrate.py` → reiniciar. El CHANGELOG lleva la sección "Para actualizar".
- **Volver atrás** no exige deshacer nada: `ADD COLUMN` no reescribe la tabla y el código
  anterior no lee la columna, que sobra sin estorbar (como `projects.status_id`).
- **Versión**: es un `feat:` → MINOR. La Fase 3 tampoco se ha publicado (`VERSION` sigue
  en 1.18.0): si salen juntas, es una sola 1.19.0.

#### API: lo que cambia (leído de `routers/tasks.py` y `schemas.py`)

| Dónde | Hoy | Cambio |
|---|---|---|
| `TaskUpdate` | `title`, `notes`, `is_done`, `order`, `project_id`, `column_id`, `tag_ids` | `+ estimate_minutes: Optional[int]`, con `ge=1` y `le=6000` (100 h; decisión 2) |
| `PATCH /api/tasks/{id}` | `model_dump(exclude_unset=True)`; un `null` se ignora solo en `column_id` e `is_done` | Mandar `null` borra el estimado y no mandarlo lo deja igual. Nada más que tocar: el `setattr` del final ya aplica el campo |
| `TaskResponse` | Sin estimado | `+ estimate_minutes: Optional[int] = None`. `_task_responses()` usa `model_validate(t)`, así que sale solo en `GET /api/tasks`, `POST` y `PATCH` |
| `TaskCreate` | — | Sin cambio en esta fase: las tarjetas se crean solo con título (decisión 8) |
| `OverviewTask` | `id`, `title`, `is_done`, `seconds` | `+ estimate_minutes` |
| `ProjectOverview` | Tiempo por tarea, etiqueta y mes, `finance` con el plan | `+ estimates` (bloque de abajo), solo del proyecto y solo con el plan encendido, como `finance` (decisión 1) |
| `GET /api/costs/estimates` | No existe | **Nuevo**, en `routers/costs.py` tras `maker_user`: el mismo bloque con todos los proyectos. Ruta literal: declararla antes de las paramétricas (`/{cost_id}`) |

El cálculo vive **en una sola función pura** (p. ej. `estimate_deviation()` en
`backend/costing.py`), que usan la ficha y Costos para que sus cifras cuadren, igual que
la mano de obra.

```
estimates: {
  overall:  {tasks, estimate_seconds, actual_seconds, ratio_pct},   # cada tarea una vez
  tags:     [{tag_id, name, color, tasks, estimate_seconds, actual_seconds, ratio_pct}],
  untagged: {tasks, estimate_seconds, actual_seconds, ratio_pct}
}
```

**La regla del desvío (decisiones 3 a 5):**

- Cuentan las tareas **con estimado** y con tiempo registrado que sean:
  - **terminadas**, con su tiempo final;
  - o **abiertas que ya pasaron su estimado**, con el tiempo que llevan: ya se sabe que se
    desviaron, y al terminar solo pueden desviarse más.
- Una abierta que va por debajo de su estimado **no cuenta todavía**: su tiempo real no se
  conoce, y contarla diría "tardas 0.3×" de una tarea a medias. Esto inclina la cifra un
  poco hacia "tardas más", que para cotizar es lo prudente.
- Tiempo real = sus sesiones `focus`, el mismo criterio que `seconds` de `TaskResponse`
  (vale también en proyectos archivados).
- Por etiqueta, **cociente de sumas**: tiempo real total ÷ estimado total de esas tareas.
  No el promedio de cocientes, para que una tarea de 5 minutos estimada en 1 no domine.
- Una tarea con dos etiquetas cuenta en las dos (la misma regla del tiempo por etiqueta),
  así que las filas no se suman entre sí; el total general cuenta cada tarea una vez.
- El backend devuelve **enteros**: `ratio_pct` = real × 100 ÷ estimado, con redondeo de
  .5 hacia arriba (`ROUND_HALF_UP`), nunca `round()`. La pantalla pinta "1.6×".
- Con menos de **3 tareas** en una fila (etiqueta, *Sin etiqueta* o total), la fila dice
  "todavía hay poco historial" en vez de una cifra (principio 2: no fingir precisión).
- **Periodo**: todo el historial. Si la entrada 29 del backlog le pone periodo a Costos,
  se aplica aquí por fecha de terminada (`completed_at`); una abierta que ya se pasó, por
  la fecha de hoy.

#### Dónde se ve

El campo y el "de 3 h" son **para todos**, con o sin el plan Maker: planear sirve aunque
no se cobre, así que el `PATCH` del estimado no comprueba el módulo. El desvío ("tardas
1.6×") **solo con Maker encendido**, en la ficha y en Costos (decisión 1).

- **Detalle de la tarjeta** (`#cardModal`, `board.js`): campo **Estimado** en
  `.card-fields`, junto a Columna y Proyecto, con horas y minutos como el registro a mano.
  Se guarda al cambiarlo, como los demás campos; vacío = sin estimado.
- **Tarjeta del tablero** (`buildCard()`): "2 h de 3 h" en `.board-card-time`. Mientras
  corre el cronómetro, el reloj en vivo ocupa ese sitio, como hoy. Pasado del estimado, el
  número va en el color de alerta del tema, sin avisos ni notificaciones (decisión 7).
- **Lista** (`projects.js`, `.task-time`): el mismo "de 3 h", también en color de alerta al pasarse (decisión 6).
- **Ficha** (`project-overview.js`): en *Tareas*, cada fila con "de X"; y una tarjeta
  nueva **Estimado contra real** con el bloque `estimates` del proyecto: por etiqueta,
  real contra estimado y "tardas 1.6× lo que estimas".
- **Costos** (`costs.js`, `renderCostsSummary()`): tarjeta **Tus estimados** con
  `GET /api/costs/estimates`, de todos tus proyectos.
- **Reportes**: nada en esta fase.
- **Guía de uso**: el campo en "Detalle de la tarjeta" y la tarjeta nueva en "Costos".

#### Pruebas

De API (`pytest`):

- `tests/test_task_details.py`, o un `tests/test_estimates.py` nuevo: poner, cambiar y
  borrar (`null`) el estimado; un `PATCH` sin el campo no lo toca; aparece en
  `GET /api/tasks`.
- `tests/test_limits.py`: `0`, negativo y el tope + 1 → 422; el tope entra.
- `tests/test_isolation.py`: `PATCH` del estimado de una tarea ajena → 404, y
  `/api/costs/estimates` no trae tareas ni etiquetas de otra cuenta.
- `tests/test_deploy.py`: lo de "Impacto en producción".
- El estimado se guarda sin el plan Maker (decisión 1), y la ficha no trae `estimates`
  con el plan apagado.
- La regla: una abierta por debajo de su estimado no cuenta, y una que ya lo pasó cuenta
  con el tiempo que lleva; cociente de sumas; una tarea con dos
  etiquetas, en las dos; *Sin etiqueta*; redondeo de .5 hacia arriba; menos de 3 tareas →
  sin cifra; y una prueba de cuadre: para un mismo proyecto, la ficha y Costos dan lo
  mismo.
- Módulo: `/api/costs/estimates` responde 403 sin el plan (con `maker_on()` de
  `test_finance.py`, como `test_costs.py`).

De navegador (`pytest -m ui`):

- `tests/ui/ui_card_estimate.py`, nueva: escribir 1 h 30 min en el detalle, cerrar, y la
  tarjeta dice "de 1 h 30 min"; tras recargar sigue ahí; vaciar el campo lo quita.
- `ui_project_overview.py`: la tarjeta *Estimado contra real*, con tareas que crea la
  prueba (las del fixture son de ayer y no tienen estimado).
- `ui_costs.py`: *Tus estimados* con el plan encendido, y que no sale sin él.

#### Decisiones de la Fase 4 (2026-10-01)

1. **El estimado es para todos; el desvío, solo con Maker.** El campo y el "2 h de 3 h"
   los ve cualquiera, porque planear sirve aunque no se cobre. El "tardas 1.6× lo que
   estimas" (ficha y Costos) solo con el plan encendido, porque es la base del cotizador.
2. **Tope: de 1 minuto a 6000 (100 h) por tarea.** Más que eso suele ser un proyecto.
3. **Cuentan las terminadas y las abiertas que ya pasaron su estimado.** Las abiertas por
   debajo todavía no, porque su tiempo real no se conoce. La cifra se inclina un poco
   hacia "tardas más", que para cotizar es lo prudente.
4. **Mínimo: 3 tareas por fila.** Con menos, "todavía hay poco historial".
5. **Periodo: todo el historial.** Si la entrada 29 decide un periodo para Costos, se
   aplica aquí también.
6. **"de X" también en la Lista**, para que cuadre con el tablero.
7. **Pasado del estimado, el número en color de alerta.** Sin avisos ni notificaciones
   (principio 1: estimar, no vigilar).
8. **Sin estimado al crear la tarjeta por ahora.** Se pone en el detalle; se agrega a
   `TaskCreate` cuando el cotizador de la Fase 5 cree tareas previstas con su estimado.

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
| 1 ✅ | `user_modules` (`user_id`, `module`, `enabled`, `allowed`), único por (usuario, módulo). Sin fila o NULL = valor por defecto del módulo | Tabla nueva | No |
| 2 ✅ | `project_finance` (`project_id` único, `user_id`, `client_name`, `hourly_rate_cents`, `currency`, `budget_cents`, `budget_minutes`) | Tabla nueva, 1 a 1 con `projects` | No |
| 3 ✅ | `cost_categories` (`user_id`, `name`, `color`, `order`), único por (usuario, nombre); y `project_costs` (`user_id`, `project_id`, `category_id`, `cost_date`, `concept`, `quantity`, `unit_cost_cents`, `note`) | Tablas nuevas | No |
| 4 | `tasks.estimate_minutes` (NULL = sin estimado) | Columna nueva | **Sí**: `migrate.py` + `test_deploy.py` |
| 6 | `project_finance.sheet_csv_url` | Columna en la tabla de la Fase 2 | No, si la Fase 2 aún no salió; si ya salió, sí |

- `project_finance` separada de `projects` para no tocar la tabla vieja y porque solo
  existe para quien usa Costeo.
- Todas con `user_id` y filtradas por `current_user.id`; cada endpoint nuevo por id lleva
  su caso en `tests/test_isolation.py` y sus topes en `tests/test_limits.py`.
- Borrar un proyecto (`DELETE /api/projects/{id}`) tendrá que decidir qué pasa con sus
  gastos: lo natural es borrarlos con él, y avisarlo en la confirmación.

## Decisiones

Cerradas antes de la Fase 2 (2026-10-01):

1. **Moneda: una por proyecto.** Es un campo del proyecto; no se convierte entre monedas,
   así que un total que mezcle proyectos se da por moneda, nunca sumado.
2. **Cotización sin estados de proyecto.** No se vuelve a los estados que se quitaron: un
   proyecto con presupuesto y sin tiempo registrado *es* una cotización, y la ficha lo
   dice.

Cerradas en la Fase 1 (2026-10-01): la ficha es un **modal**; tocar un proyecto en la
Lista abre la ficha y editar va dentro; apagar Hábitos oculta **la pestaña y la tarjeta**
de Reportes; y la Fase 1 dejó la base de la épica 14 a medias (vistas por id y
`setViewVisible()`), sin crear las pestañas desde datos.

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
