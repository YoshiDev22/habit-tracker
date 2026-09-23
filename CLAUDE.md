# CLAUDE.md — habit-tracker

Proyecto personal de Yoshio. Responde en español salvo que el prompt esté en inglés.
Código, comentarios, nombres de variables y mensajes de commit: en inglés.

## Qué es

App personal de productividad. Tres módulos sobre la misma cuenta, más una vista de
reportes:

1. **Hábitos** — calendario mensual, marcado por día, rachas y estadísticas.
2. **Proyectos y tareas** — tableros kanban (cada uno con sus columnas) cuyas tarjetas son
   tareas; el proyecto es una etiqueta de la tarea. También hay vista Lista por proyecto.
3. **Pomodoro** — timer (cronómetro, pomodoro o registro manual) con tiempo por proyecto/tarea.
4. **Reportes** — pestaña de solo lectura: tiempo por día, proyecto, etiqueta y hora, tareas
   terminadas y días/rachas de hábitos en una semana, un mes o un rango.

Backend FastAPI + SQLite con autenticación JWT, frontend estático (HTML/CSS/JS
vanilla, sin build step) servido por la misma app.

- Repo: https://github.com/YoshiDev22/habit-tracker
- Producción: https://habits.yoshidev22.com
- Versión actual: ver `VERSION` en la raíz (semver, ej. `1.3.0`)

## Stack

Versiones confirmadas en `requirements.txt` (no hay `pyproject.toml` en el repo):

- `fastapi==0.109.0`, servido con `uvicorn[standard]==0.27.0`
- `sqlmodel==0.0.14` (SQLAlchemy + Pydantic) como ORM sobre SQLite. Ojo: con Pydantic v2,
  `Field(regex=...)` **no valida nada** en esta versión; usar un `@field_validator` (ver
  `_validate_hex_color` en `schemas.py`). `min_length`/`max_length` sí funcionan.
- `python-jose[cryptography]==3.3.0` para JWT
- `bcrypt==4.0.1` para hashear/verificar contraseñas — usado directamente en `backend/auth.py`
  (sin `passlib`, que se quitó por no usarse).
- `python-multipart==0.0.6` (requerido por FastAPI para leer el form-data de `OAuth2PasswordRequestForm` en `/api/auth/login`)
- `python-dotenv==1.0.1` para cargar `backend/.env`
- Frontend estático servido por la misma app (sin build step, sin dependencias JS)

No hay tests, ni linter, ni CI, ni `requirements-dev.txt`.

## Estructura

```
habit-tracker/
├── backend/
│   ├── __init__.py
│   ├── main.py            # Entry point FastAPI. Crea la app, monta routers, sirve el frontend
│   ├── database.py        # Engine SQLModel/SQLite, create_db_and_tables(), get_session()
│   ├── models.py          # Tablas (ver Modelo de datos)
│   ├── schemas.py         # Esquemas Pydantic/SQLModel de request/response
│   ├── auth.py            # Hashing, JWT (create/verify), get_current_user, lee SECRET_KEY
│   ├── dates.py           # resolve_client_today(): el "hoy" del usuario, no el del servidor (UTC)
│   ├── boards.py          # ensure_user_setup(): "Sin asignar" y relleno perezoso de columnas
│   ├── .env               # NO versionado. Contiene DATABASE_URL y SECRET_KEY
│   ├── .env.example       # Plantilla versionada del .env
│   └── routers/
│       ├── __init__.py
│       ├── auth.py        # /api/auth/*
│       ├── habits.py      # /api/habits/*      (entradas diarias + definiciones de hábitos)
│       ├── projects.py    # /api/projects/*
│       ├── tasks.py       # /api/tasks/*       (+ /{id}/checklist y /{id}/comments)
│       ├── boards.py      # /api/boards/*      (+ /{id}/columns)
│       ├── tags.py        # /api/tags/*
│       └── pomodoro.py    # /api/pomodoro/*
├── scripts/
│   └── migrate.py         # Columnas añadidas a tablas existentes; se corre antes de reiniciar
├── index.html             # Única página. Contiene todos los modales y ambas vistas
├── styles.css             # Todo el CSS, con variables de tema en :root / [data-theme]
├── script.js              # Núcleo: auth, hooks, apiFetch, calendario, hábitos, tema
├── projects.js            # Tabs con swipe, vista Lista (proyectos y tareas), menú y borrado de proyecto
├── board.js               # Vista Tablero, detalle de tarjeta y "Organizar" (tableros, columnas, etiquetas)
├── pomodoro.js            # Timer, persistencia local y envío de sesiones
├── reports.js             # Vista Reportes: rango, gráficas SVG y desgloses (solo lee)
├── VERSION                # Semver, leído por el backend y mostrado en la UI
├── CHANGELOG.md           # Novedades de cada versión, para el usuario
├── requirements.txt
├── README.md
├── BACKLOG.md             # Cola de trabajo pendiente
└── CLAUDE.md
```

- Frontend con rutas de API **relativas** (`API_BASE_URL = ''`). No hardcodear el dominio.

## Setup local (repo recién clonado)

El repo **no incluye** ni la base de datos ni el `.env`. Ambos hay que crearlos:

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp backend/.env.example backend/.env
# SECRET_KEY de desarrollo (NO reutilizar el de producción):
python -c "import secrets; print(secrets.token_hex(32))"
# Pegar el valor en SECRET_KEY dentro de backend/.env
```

`backend/.env` mínimo:

```
DATABASE_URL=sqlite:///./habits.db
SECRET_KEY=<el valor generado arriba>
```

Sin `SECRET_KEY`, `backend/auth.py` lanza `RuntimeError` al importar y la app no arranca.
Es intencional: no hay valor por defecto inseguro.

Levantar el servidor (**desde la raíz del repo**, no desde `backend/`):

```bash
uvicorn backend.main:app --reload
```

`backend/main.py` importa con rutas absolutas (`from backend.database import ...`,
`from backend.routers import ...`), así que `backend` debe resolverse como paquete desde
la raíz del repo. Usar siempre `backend.main:app` desde la raíz.

La base de datos **se crea sola al arrancar**: `backend/main.py` llama a
`create_db_and_tables()` (definida en `backend/database.py`, hace
`SQLModel.metadata.create_all(bind=engine)`) de forma incondicional al importar el módulo,
antes de instanciar `FastAPI()`. No hace falta ningún paso extra para crear el esquema inicial.

Documentación interactiva: `/api/docs` (Swagger) y `/api/redoc`. **No** están en `/docs`.

## Modelo de datos

Tablas en `backend/models.py`: `User`, `HabitEntry`, `Habit`, `Project`, `Task`,
`PomodoroSession`, y las del tablero: `Board`, `BoardColumn`, `Tag`,
`TaskTag`, `TaskChecklistItem`, `TaskComment`. Todas cuelgan de `users.id` con un `user_id`
(el dueño). **Toda query filtra por `current_user.id`**, nunca solo por el id del recurso —
es lo único que separa los datos entre usuarios.

Cómo encaja el tablero:

```
Board ("Escuela")  ── BoardColumn (Por hacer · Haciendo · Hecho, configurables)
                          └── Task (la tarjeta: column_id)
                                ├── project_id → Project (UNO: ahí se suma su tiempo)
                                ├── TaskTag → Tag (VARIAS: tipo de actividad)
                                ├── TaskChecklistItem (subtareas, sin tiempos)
                                └── TaskComment (seguimiento, con author_id)
```

Lo que no se deduce leyendo los modelos:

- **`habits_data` y `rest_days` son JSON plano, sin `MutableDict`.** Reasignar el atributo
  completo (`entry.habits_data = {...}`, `user.rest_days = [...]`) se persiste; mutarlo
  in-place **NO** lo detecta SQLAlchemy y el commit no escribe nada.
- **`PomodoroSession.session_date` es la fecha LOCAL del usuario**, calculada en el cliente
  con `getDateKey()` y enviada en el payload. No derivar la fecha de `started_at` en el
  servidor: agrupar por `date(started_at)` archivaría las sesiones nocturnas bajo el día
  equivocado según el huso horario.
- **El servidor corre en UTC; "hoy" es la fecha LOCAL del cliente.** Todo endpoint que
  dependa de "hoy" (la racha en `GET /api/habits`, `today_seconds` en
  `GET /api/pomodoro/stats`) recibe `?today=AAAA-MM-DD` desde `getDateKey(new Date())` y lo
  resuelve con `resolve_client_today()` (`backend/dates.py`), que solo acepta ±1 día
  respecto a UTC. No usar `date.today()` para nada que el usuario vea como "hoy".
- **`habits.label` es el nombre SIN emoji; el emoji vive en `habits.icon`.** La pantalla
  compone los dos con `habitDisplayName()` en `script.js`. Nunca guardar "emoji + nombre"
  en `label`: eso es exactamente lo que hacía el guardado viejo —leía el nombre del span
  que pintaba, y ese span era "emoji + nombre"— y el emoji terminaba dos veces en pantalla.
  `scripts/migrate.py` normaliza lo que ya estaba guardado así; es idempotente.
- **La racha solo la calcula el backend** (`calculate_streak` en `routers/habits.py`). La
  pantalla muestra el `streak` de `GET /api/habits` y lo refresca con
  `GET /api/habits/streak` después de marcar un día. La regla vive en `_current_streak()`
  (y el récord en `_best_streak()`), que `GET /api/habits/report` aplica también a cada
  hábito por separado: un cambio de regla se hace ahí, una sola vez. No volver a calcularla en el
  navegador: hubo una copia de la regla en `script.js`, ignoraba los días de descanso y la
  UI contradecía a la API.
- `started_at` / `ended_at` son UTC naive (`datetime.utcnow()`). El cliente nunca los parsea
  para la lógica del timer — usa `Date.now()` + localStorage.
- Archivar (`is_active=False`) conserva el historial. `DELETE /api/tasks/{id}` borra su
  checklist, comentarios y etiquetas, y conserva las sesiones poniéndoles `task_id = None`.
  **`DELETE /api/projects/{id}` NO borra sus tareas**: el proyecto es una etiqueta, así que
  sus tareas y su tiempo pasan a "Sin asignar"; con `?delete_sessions=true` el tiempo se
  borra (la UI lo pide con una casilla explícita).
- **De una columna, el código solo lee `category`** (`todo | doing | done`); el nombre,
  color, orden y cuántas hay son del usuario, y la categoría no se cambia después de
  crear. Nunca comparar por nombre ("Hecho"): el usuario lo renombra. La UI no enseña la
  categoría: marca "📥 Entrada" (la primera `todo`) y "✓ Terminada" (las `done`).
- **No hay estados de proyecto** (Ideas / En curso / En pausa…): se probaron y se quitaron
  antes de salir a producción porque no tenían uso visible. Un proyecto está activo o
  archivado, nada más. En una base local de desarrollo pueden quedar la tabla
  `project_statuses` y la columna `projects.status_id` de esa prueba: sobran y no estorban.
- **`Task.is_done` y `Task.column_id` van siempre juntos** (`update_task` en
  `routers/tasks.py`): mover a una columna `done` marca hecha, y el checkbox mueve a la
  primera columna `done`/`todo` **del mismo tablero**. `is_done` sigue existiendo porque
  `/api/projects/summary` cuenta el progreso con él. `completed_at` se pone al PASAR a
  hecha (con `?today=`), y moverla entre dos columnas `done` conserva la fecha.
- **El tiempo es de la tarea**: cambiarle el proyecto a una tarea mueve el `project_id` de
  sus sesiones. El tiempo registrado sin tarea no se toca.
- **"Sin asignar"** es un `Project` con `is_system=True` que cada usuario recibe para las
  tareas sin proyecto (existe porque `tasks.project_id` es NOT NULL y quitarlo en SQLite
  obliga a reconstruir la tabla en producción). No se renombra, ni se archiva, ni se borra;
  sus tareas sí.
- **Los defaults y el relleno son perezosos**: `ensure_user_setup()` (`backend/boards.py`)
  crea "Sin asignar" y asigna columna a las tareas que no la tengan. "Mi tablero" solo se crea si hay tareas sin columna que acomodar (datos de antes
  de los tableros) o al crear una tarea sin tener ningún tablero; un usuario nuevo empieza
  sin tableros y `board.js` le ofrece crear el primero al entrar a la pestaña. Corre en los endpoints que lo necesitan, no en
  `migrate.py`, porque esas tablas las crea `create_all()` DESPUÉS de que migrate.py corre.
  Es idempotente, y una restricción única por nombre frena la doble siembra concurrente.
- **Etiquetas y tiempo**: una sesión cuenta en cada etiqueta de su tarea, así que los
  totales por etiqueta NO se suman entre sí. `GET /api/tags/summary` devuelve además
  `combined_*` (las etiquetas pedidas, cada sesión una vez) y `untagged_*`.
- **Comentarios**: `user_id` es el dueño de la tarea (lo que filtran las queries) y
  `author_id` quien escribió; hoy coinciden, pero están separados para compartir tableros
  sin migrar. Solo el autor edita o borra. `created_at` es UTC naive.

## Endpoints

Un router por módulo en `backend/routers/` (`auth`, `habits`, `projects`, `tasks`,
`pomodoro`), montados con prefijo `/api/<módulo>` en `main.py`. Para la lista completa con
sus esquemas, levantar el server y abrir **`/api/docs`** (Swagger) — no `/docs`. Todo
requiere `Authorization: Bearer` salvo `/api/auth/*`, `/api`, `/api/version` y `/api/health`.
En producción Caddy solo reenvía rutas con un segmento después de `/api`: una ruta pública
nueva va bajo `/api/<algo>`, nunca en la raíz (`/health` daba 404 por eso).

Lo que no se ve en Swagger:

- `POST /api/auth/login` recibe **form-data** (`username`, `password`), no JSON — es
  `OAuth2PasswordRequestForm`. El resto de la API es JSON.
- **Las rutas literales van declaradas ANTES que las paramétricas** dentro del mismo router
  (`/summary` antes de `/{project_id}` en `projects.py`, y antes de `/{tag_id}` en `tags.py`).
  Al revés, FastAPI intenta parsear `"summary"` como `int` y devuelve 422.
- Los 409 del tablero traen el motivo en español ("tiene 6 tareas", "es la única columna de
  su tipo") y la UI de Organizar lo enseña tal cual: mantener esos mensajes legibles.
- El frontend se sirve desde `main.py` con un `@app.get` por archivo. No hay `StaticFiles`
  montado, así que **un archivo JS nuevo necesita su propia ruta** o devuelve 404.

## Arquitectura del frontend

Sin build step, sin módulos ES. `index.html` carga los cinco scripts en orden y **el
orden importa**:

```html
<script src="script.js"></script>   <!-- primero: define los hooks y apiFetch -->
<script src="projects.js"></script> <!-- define projectsState y projectsChangedHooks -->
<script src="board.js"></script>    <!-- usa los dos; su loadBoard corre antes que los selects del pomodoro -->
<script src="pomodoro.js"></script>
<script src="reports.js"></script>  <!-- solo lee: usa helpers de script.js y projects.js -->
```

Todo corre en el scope global compartido. Cuidado con colisiones de nombres entre archivos.

### Sistema de hooks — así se agrega un módulo nuevo

`script.js` expone tres arrays. `projects.js` y `pomodoro.js` se enganchan a ellos y
`script.js` no los conoce. **Un archivo nuevo debe seguir este patrón en vez de tocar
`script.js`.**

| Hook | Cuándo corre |
|---|---|
| `window.appInitHooks` | Al final de `initApp()`, siempre (haya sesión o no) |
| `window.appDataHooks` | Cuando el usuario queda autenticado: login, registro y reload con token |
| `window.appLogoutHooks` | **Primera** acción de `handleLogout()`, con el token todavía vivo. Arrancan todos a la vez (no en serie): solo el código **hasta su primer `await`** corre con token, así que el POST de despedida va antes de cualquier `await` |

```js
// Al final del archivo nuevo:
window.appInitHooks.push(initMiModulo);      // UI, listeners, estado local
window.appDataHooks.push(cargarMisDatos);    // fetch al backend
window.appLogoutHooks.push(limpiarMiModulo); // último POST + limpiar localStorage
```

`runHooks()` los ejecuta en orden y **atrapa los errores**: un hook que falla no detiene a
los demás, solo hace `console.error`. `appLogoutHooks` corre antes de `removeToken()`
justamente para que un módulo pueda hacer un último POST autenticado (lo usa `pomodoro.js`
para guardar la sesión en curso antes de perder el token).

`projects.js` declara dos más, suyos:

| Hook | Cuándo corre |
|---|---|
| `window.projectsChangedHooks` | Al final de cada `loadProjects()`. Tablero, lista y selects del pomodoro se refrescan por aquí |
| `window.viewChangedHooks` | Síncrono, en cada `goToView()`, con el índice de la vista |

**Toda mutación de tareas o proyectos termina en `loadProjects()`** (en `board.js`, vía
`refreshAfterBoardChange()`, que además vacía la caché de tareas de la lista). No refrescar
el tablero por otro camino: `loadProjects()` dispara `loadBoard()`, que vuelve a pedir las
tareas, y el tiempo de cada tarjeta es su campo `seconds` (calculado en `_task_responses()`,
así que también vale para tareas de proyectos archivados).

### `apiFetch` y `ApiError`

`apiFetch(path, options)` en `script.js` es el helper para **todo el código nuevo**:

```js
const data = await apiFetch('/api/projects', { method: 'POST', json: payload });
```

Pone el `Authorization: Bearer` solo; `options.json` serializa el body y el `Content-Type`
(no usar `body` a mano); en 401 hace `handleLogout()`; en 204 devuelve `null`. Los errores
salen como `ApiError` con `.status`, para distinguir un 409 de un fallo genérico.

**Deuda conocida:** quedan ~8 `fetch()` crudos en `script.js` (hábitos, login/register,
`delete-habit`) que no manejan el 401. Migrarlos al tocar esa zona; no escribir `fetch()`
crudo nuevo.

### Modales

`.modal-content` tiene `max-height: 90vh` y `overflow-y: auto`. **No quitarlos:**
sin tope, un modal más alto que la pantalla se recorta arriba y abajo sin barra de
scroll, y sus botones quedan inalcanzables — el `.modal` que lo envuelve es
`position: fixed` y centrado, así que la página no llega a él. El de hábitos va un
paso más allá: `.setup-modal` es una columna flex con el cuerpo en `.setup-scroll`
(que necesita `min-height: 0` para poder encoger) y el pie en `.setup-footer`, para
que "Guardar Hábitos" no se vaya con el scroll.

Dos modales se abren **encima** de otro y devuelven una promesa en vez de cerrarse
solos: `#confirmModal` (`confirmDialog()`) y `#emojiPickerModal` (`pickEmoji()`).
Los dos necesitan su rama en `handleModalDismiss()` —cerrar por la X o el overlay
tiene que resolver la promesa pendiente, o quien la esperaba se queda colgado— y su
`z-index` propio en `styles.css` (1100 el confirm, 1050 el panel), porque con el
1000 de `.modal` el orden lo decidiría el documento.

Los modales de `board.js` (`#cardModal`, `#boardConfigModal`) y `#projectDeleteModal` se
cierran con sus propios listeners, no con `handleModalDismiss()`. El detalle de tarjeta
**se cierra antes** de abrir el registro manual o el cronómetro: comparte el `z-index`
1000 con `#logTimeModal`. Sus campos se guardan al cambiar (sin botón de guardar) y el
tablero se refresca una vez, al cerrar.

### Vistas y navegación

Tres vistas (`#viewCalendar`, `#viewProjects` — la pestaña se llama "Tableros" —,
`#viewReports`) dentro de `#viewsTrack`, con tabs arriba y swipe horizontal. Toda la
lógica está en `projects.js` (`goToView()`, `VIEW_TABS`, manejo de `touchstart/move/end`
con detección de eje). Agregar una vista implica sumar su tab a `VIEW_TABS`, el HTML de
tabs y el ancho de `.tab-indicator` (`calc(100% / N)`).

**El alto del viewport es el de la vista activa** (`watchActiveView()`, con un
`ResizeObserver`): las vistas están lado a lado, y sin eso la página tomaba la altura de la
más alta y el Calendario quedaba con metros de blanco debajo tras abrir Reportes. Lo que
necesite salirse de una vista (popovers) va fuera del track, como `#habitPopover`.

**Reportes** (`reports.js`) no guarda nada: pide de nuevo cada vez que se entra a la vista
(y en `projectsChangedHooks` mientras se ve), con el rango en fechas locales. Semana de
lunes a domingo. Solo cuenta sesiones `focus`, igual que tarjetas y Lista, así que sus
cifras deben cuadrar con ellas. El mapa por hora usa el huso **actual** del navegador sobre
`started_at` UTC: sesiones registradas desde otro huso se verían corridas. Si algún día
importa, guardar el offset en una columna nueva vía `scripts/migrate.py`. Endpoints propios: `GET /api/habits/report` y los filtros
`completed_from`/`completed_to` de `GET /api/tasks`.

Dentro de Proyectos, `board.js` alterna **Tablero** y **Lista**. El tablero:

- **Computadora (≥ 900 px):** mientras se ve, `body.board-wide` ensancha `.app-container`
  a 1200 px y deja marca, tabs y pomodoro en 600 px. Se arrastran tarjetas con drag &
  drop nativo, solo si `(hover: hover) and (pointer: fine)`.
- **Pantalla angosta (< 700 px):** una columna a la vez con pestañas que saltan de línea.
  **Nada del tablero puede desplazarse en horizontal**: pelearía con el swipe entre vistas.
  En táctil se mueve con el `<select>` nativo "Mover a…" de cada tarjeta.

### Tema (claro/oscuro)

- Un script **inline en el `<head>` de `index.html`**, antes del `<link>` de estilos, lee
  `localStorage.theme` y pone `data-theme` y `data-theme-pref` en `<html>`. Es lo que evita
  el flash de tema incorrecto (FOUC). **No moverlo ni convertirlo en archivo externo.**
- `styles.css` define las variables en `:root` y las sobreescribe en `[data-theme="dark"]`.
  Usar siempre variables CSS, nunca colores literales.
- Tres estados: `light`, `dark`, `system`. `script.js` (`initTheme`) escucha
  `prefers-color-scheme` para el modo `system` y actualiza `<meta name="theme-color">`.

### Estado en localStorage

Claves: `access_token`, `theme`, `habitsData`, `user_habits`, `habit_colors`,
`pomodoro_state`, `pomodoro_pending`, `pomodoro_sound`, `projects_view` (tablero o lista,
del dispositivo) y `board_selected` (último tablero abierto; se borra al cerrar sesión).

**Inconsistencia conocida:** el modelo `Habit` ya tiene `label`, `color`, `icon` e
`is_active` en la base. Archivar, borrar, el nombre y el emoji ya operan contra el backend
(se eliminaron `hidden_habits` y `habit_labels`), pero **el color sigue en localStorage**
(`habit_colors`), y el usuario lo pierde al cambiar de dispositivo. Es la entrada 4 del
`BACKLOG.md`. Al tocar esa zona, mover hacia el backend.

El pomodoro es **offline-first**: si el POST de una sesión falla, `queuePendingSession()`
la guarda en `pomodoro_pending` y `flushPendingSessions()` la reintenta al iniciar. No
romper esa cola.

### Timer

No hay tarjeta de reloj: el tiempo se inicia desde una tarea (▶ de la tarjeta o de la
lista, o el detalle de la tarjeta) con `startTimerForTask(projectId, taskId, mode, title)`,
que acaba en `startPomodoro(projectId, taskId, title)`. Mientras corre, se controla desde
`#pomodoroBar`, la barra flotante (hija de `<body>`, visible en cualquier pestaña). Sin
timer, esa barra tiene un **modo mensaje** (`showBarMessage(text, actions, ms)`) para los
avisos ("Sesión guardada") y la oferta de descanso al terminar un pomodoro: los descansos
solo se inician desde ahí (`startBreak`). "Hoy" y el botón de sonido viven en la barra del
tablero.

## Reglas duras

- **Nunca** commitear `.env`, `*.db`, `*.sqlite3`, ni `.venv/`. Verificar `.gitignore`.
- **Nunca** poner secretos, `SECRET_KEY` ni credenciales en el código. Van en `.env`.
- El `SECRET_KEY` de producción vive solo en el VPS. Rotarlo invalida todos los tokens
  existentes: los usuarios tendrían que volver a hacer login.
- URLs de API en el frontend: **siempre relativas**. Hardcodear el dominio rompe
  el desarrollo local.
- Migraciones de esquema en SQLite: no hay Alembic. `create_all()` crea tablas nuevas
  solas, pero **no hace `ALTER TABLE`**: agregar una columna a un modelo existente NO se
  aplica sobre la base de producción. Cualquier cambio de columna necesita un plan
  explícito de migración antes de tocar producción — la base de prod tiene datos reales
  y no está en el repo.
- Toda query de un recurso debe filtrar por `current_user.id`, no solo por el id del
  recurso. Es lo único que separa los datos entre usuarios.
- Al subir la versión: actualizar `VERSION` — ver **Versionado** más abajo para el criterio.

## Versionado

`VERSION` en la raíz, semver. El backend lo lee **al arrancar** y el frontend lo muestra vía
`GET /api`, así que subir el archivo sin reiniciar el servicio no cambia nada de lo que se ve.

**Qué bump toca.** Lo decide el commit de mayor rango que entra en el lote desde la última
versión publicada:

| Hay en el lote | Bump | Precedente en este repo |
|---|---|---|
| Algo que rompe datos o la API existentes | MAJOR | nunca ha pasado |
| Algún `feat:` | MINOR | 1.6.0 → 1.7.0 (días de descanso) |
| Solo `fix:`, `chore:`, `docs:`, `refactor:` | PATCH | 1.0.0 → 1.0.1 (hooks + apiFetch) |

Para ver qué entra en el lote: `git log --oneline <commit-del-último-bump>..HEAD`.

**Cuándo NO toca bump.** Cambios que no salen del repo: `docs:` sobre CLAUDE.md, BACKLOG.md
o README, ajustes de `.gitignore`, scripts de desarrollo. La versión identifica lo que corre
en el VPS, no cada commit.

**El bump va en su propio commit**, `chore: bump version to X.Y.Z`, justo antes de desplegar.
El historial tiene las dos formas —a veces viaja dentro del commit de la feature— pero
separarlo deja claro qué se desplegó y cuándo.

**Cada versión se publica así** (desde la 1.10.0):

1. El commit del bump cambia `VERSION` **y** añade la sección de la versión arriba de
   `CHANGELOG.md`: Nuevo / Cambios / Correcciones, escrito para quien usa la app (qué
   cambia para él, no qué función se tocó), con la fecha y su enlace al tag al final.
   Si el lote trae migración, una sección "Para actualizar" lo dice.
2. Tag anotado sobre ese commit: `git tag -a vX.Y.Z -m "vX.Y.Z"`. Las versiones 1.0.0 a
   1.9.0 también tienen el suyo, puesto después sobre el commit que cambió `VERSION`.
3. Yoshio hace `git push` y `git push --tags`, y despliega.
4. Release en GitHub con el texto de la sección del CHANGELOG (con `gh release create` si
   `gh` está instalado; si no, se pega en la web).

**Antes de subir la versión, revisar migraciones.** Si el lote agregó una columna a un modelo
que ya existía, su entrada tiene que estar en `scripts/migrate.py`. El deploy corre
`python3 scripts/migrate.py` ANTES de reiniciar el servicio. Saltarse esto deja producción
devolviendo `no such column` en el primer request — ya pasó con `users.rest_days` en la 1.7.0.
Desde la 1.10.0 la app **se niega a arrancar** si falta alguna columna de esa lista
(`check_pending_migrations()` en `backend/database.py`, que lee `MIGRATIONS` del propio
script): si el servicio no levanta tras un deploy, mirar el log, dice qué correr. Por eso
una columna nueva en una tabla existente **tiene** que ir en `migrate.py`: si no, ni se
detecta ni se aplica.

## Producción (VPS Ubuntu)

Contexto para que Claude no proponga rutas ni patrones equivocados:

- Los proyectos viven en `~/Proyectos/`, **no** en `/var/www`.
- Reverse proxy: **Caddy** (no nginx, no Apache).
- El servicio corre bajo systemd con `User=yoshi`, `Group=devshare`.
- Permisos: grupo `devshare` (GID 1002), directorios con setgid y modo 775.
  Yoshio (uid 1001) es el dueño de los archivos; el bot RDX corre en un contenedor
  Docker que obtiene acceso vía `group_add: ["1002"]`.
- Cloudflare en evaluación para proxy DNS. Si se activa: Caddy necesita
  `trusted_proxies` con los rangos de Cloudflare y leer `CF-Connecting-IP`,
  SSL en modo Full (strict), y `ufw` restringiendo 80/443 solo a rangos de Cloudflare.

**El deploy es manual.** No asumir CI/CD ni ejecutar comandos contra el VPS
sin que Yoshio lo pida explícitamente.

## Cómo quiero que trabajes

- Antes de una feature que toque varios archivos: plan primero, código después.
- Cambios acotados. Un commit por unidad lógica, no refactors masivos no pedidos.
- Si un cambio afecta el esquema de la base o la autenticación, avisar del impacto
  en producción antes de escribir código.
- No agregar dependencias nuevas sin justificarlo. El stack es deliberadamente simple.
- No inventar endpoints ni campos: leer el código antes de asumir.
- Código nuevo en el frontend: usar `apiFetch` y los hooks, no tocar `script.js`
  salvo que el cambio sea del núcleo.
