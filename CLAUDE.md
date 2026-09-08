# CLAUDE.md — habit-tracker

Proyecto personal de Yoshio. Responde en español salvo que el prompt esté en inglés.
Código, comentarios, nombres de variables y mensajes de commit: en inglés.

## Qué es

App personal de productividad. Tres módulos sobre la misma cuenta:

1. **Hábitos** — calendario mensual, marcado por día, rachas y estadísticas.
2. **Proyectos y tareas** — proyectos con tasklist y progreso por proyecto.
3. **Pomodoro** — timer con registro de tiempo por proyecto/tarea.

Backend FastAPI + SQLite con autenticación JWT, frontend estático (HTML/CSS/JS
vanilla, sin build step) servido por la misma app.

- Repo: https://github.com/YoshiDev22/habit-tracker
- Producción: https://habits.yoshidev22.com
- Versión actual: ver `VERSION` en la raíz (semver, ej. `1.3.0`)

## Stack

Versiones confirmadas en `requirements.txt` (no hay `pyproject.toml` en el repo):

- `fastapi==0.109.0`, servido con `uvicorn[standard]==0.27.0`
- `sqlmodel==0.0.14` (SQLAlchemy + Pydantic) como ORM sobre SQLite
- `python-jose[cryptography]==3.3.0` para JWT
- `bcrypt==4.0.1` para hashear/verificar contraseñas — usado directamente en `backend/auth.py`.
  `passlib[bcrypt]==1.7.4` está en `requirements.txt` pero no se importa en ningún módulo del código.
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
│   ├── models.py          # Tablas: User, HabitEntry, Habit, Project, Task, PomodoroSession
│   ├── schemas.py         # Esquemas Pydantic/SQLModel de request/response
│   ├── auth.py            # Hashing, JWT (create/verify), get_current_user, lee SECRET_KEY
│   ├── .env               # NO versionado. Contiene DATABASE_URL y SECRET_KEY
│   ├── .env.example       # Plantilla versionada del .env
│   └── routers/
│       ├── __init__.py
│       ├── auth.py        # /api/auth/*
│       ├── habits.py      # /api/habits/*      (entradas diarias + definiciones de hábitos)
│       ├── projects.py    # /api/projects/*
│       ├── tasks.py       # /api/tasks/*
│       └── pomodoro.py    # /api/pomodoro/*
├── index.html             # Única página. Contiene todos los modales y ambas vistas
├── styles.css             # Todo el CSS, con variables de tema en :root / [data-theme]
├── script.js              # Núcleo: auth, hooks, apiFetch, calendario, hábitos, tema
├── projects.js            # Tabs con swipe, proyectos y tareas
├── pomodoro.js            # Timer, persistencia local y envío de sesiones
├── VERSION                # Semver, leído por el backend y mostrado en la UI
├── requirements.txt
├── README.md
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
`PomodoroSession`. Todas cuelgan de `users.id`; `Task` y `PomodoroSession` además guardan
`user_id` denormalizado. **Toda query filtra por `current_user.id`**, nunca solo por el id
del recurso — es lo único que separa los datos entre usuarios.

Lo que no se deduce leyendo los modelos:

- **`habits_data` es JSON plano, sin `MutableDict`.** Reasignar el atributo completo
  (`entry.habits_data = {...}`) se persiste; mutarlo in-place (`del entry.habits_data[k]`)
  **NO** lo detecta SQLAlchemy y el commit no escribe nada.
- **`PomodoroSession.session_date` es la fecha LOCAL del usuario**, calculada en el cliente
  con `getDateKey()` y enviada en el payload. No derivar la fecha de `started_at` en el
  servidor: agrupar por `date(started_at)` archivaría las sesiones nocturnas bajo el día
  equivocado según el huso horario.
- `started_at` / `ended_at` son UTC naive (`datetime.utcnow()`). El cliente nunca los parsea
  para la lógica del timer — usa `Date.now()` + localStorage.
- Archivar (`is_active=False`) conserva el historial; borrar (`DELETE`) lo elimina.
  `DELETE /api/projects/{id}` borra en cascada manual sus tareas y sesiones;
  `DELETE /api/tasks/{id}` conserva las sesiones y solo les pone `task_id = None`.

## Endpoints

Un router por módulo en `backend/routers/` (`auth`, `habits`, `projects`, `tasks`,
`pomodoro`), montados con prefijo `/api/<módulo>` en `main.py`. Para la lista completa con
sus esquemas, levantar el server y abrir **`/api/docs`** (Swagger) — no `/docs`. Todo
requiere `Authorization: Bearer` salvo `/api/auth/*`, `/api` y `/health`.

Lo que no se ve en Swagger:

- `POST /api/auth/login` recibe **form-data** (`username`, `password`), no JSON — es
  `OAuth2PasswordRequestForm`. El resto de la API es JSON.
- **Las rutas literales van declaradas ANTES que las paramétricas** dentro del mismo router
  (`/summary` antes de `/{project_id}` en `projects.py`). Al revés, FastAPI intenta parsear
  `"summary"` como `int` y devuelve 422.
- El frontend se sirve desde `main.py` con un `@app.get` por archivo. No hay `StaticFiles`
  montado, así que **un archivo JS nuevo necesita su propia ruta** o devuelve 404.

## Arquitectura del frontend

Sin build step, sin módulos ES. `index.html` carga los tres scripts en orden y **el orden
importa**:

```html
<script src="script.js"></script>   <!-- primero: define los hooks y apiFetch -->
<script src="projects.js"></script>
<script src="pomodoro.js"></script>
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
| `window.appLogoutHooks` | **Primera** acción de `handleLogout()`, con el token todavía vivo |

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

### Vistas y navegación

Dos vistas (`#viewCalendar`, `#viewProjects`) dentro de `#viewsTrack`, con tabs arriba y
swipe horizontal. Toda la lógica está en `projects.js` (`goToView()`, `VIEW_COUNT`, manejo
de `touchstart/move/end` con detección de eje). Agregar una vista implica tocar
`VIEW_COUNT`, el HTML de tabs y el indicador.

### Tema (claro/oscuro)

- Un script **inline en el `<head>` de `index.html`**, antes del `<link>` de estilos, lee
  `localStorage.theme` y pone `data-theme` y `data-theme-pref` en `<html>`. Es lo que evita
  el flash de tema incorrecto (FOUC). **No moverlo ni convertirlo en archivo externo.**
- `styles.css` define las variables en `:root` y las sobreescribe en `[data-theme="dark"]`.
  Usar siempre variables CSS, nunca colores literales.
- Tres estados: `light`, `dark`, `system`. `script.js` (`initTheme`) escucha
  `prefers-color-scheme` para el modo `system` y actualiza `<meta name="theme-color">`.

### Estado en localStorage

Claves: `access_token`, `theme`, `habitsData`, `user_habits`, `habit_labels`,
`habit_colors`, `hidden_habits`, `pomodoro_state`, `pomodoro_pending`, `pomodoro_sound`.

**Inconsistencia conocida:** el modelo `Habit` ya tiene `label`, `color`, `icon` e
`is_active` en la base, pero el frontend sigue leyendo `habit_labels`, `habit_colors` y
`hidden_habits` desde localStorage. La fuente de verdad está partida y el usuario pierde
colores y etiquetas al cambiar de dispositivo. Al tocar esa zona, mover hacia el backend.

El pomodoro es **offline-first**: si el POST de una sesión falla, `queuePendingSession()`
la guarda en `pomodoro_pending` y `flushPendingSessions()` la reintenta al iniciar. No
romper esa cola.

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
- Al subir la versión: actualizar `VERSION`. El backend lo lee al arrancar y el frontend
  lo muestra vía `GET /api`.

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
