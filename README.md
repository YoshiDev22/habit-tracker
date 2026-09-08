# Habit Tracker

App personal de productividad, con tres módulos sobre una misma cuenta:

- **Hábitos** — calendario mensual, marcado por día, rachas y estadísticas.
- **Proyectos y tareas** — proyectos con tasklist y progreso.
- **Pomodoro** — timer con registro de tiempo por proyecto y tarea.

Backend FastAPI + SQLite con autenticación JWT. Frontend estático (HTML/CSS/JS vanilla,
sin build step ni dependencias) servido por la misma app.

Producción: <https://habits.yoshidev22.com>

## Stack

- FastAPI 0.109 sobre uvicorn
- SQLModel 0.0.14 (SQLAlchemy + Pydantic) sobre SQLite
- python-jose para JWT, bcrypt para las contraseñas
- Frontend vanilla, sin bundler

## Instalación

Requiere **Python 3.11+** (probado en 3.13). El repo **no incluye** la base de datos ni el
archivo `.env`: ambos hay que crearlos.

```bash
git clone https://github.com/YoshiDev22/habit-tracker.git
cd habit-tracker
```

### Entorno virtual

**Linux / macOS:**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows (PowerShell):**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Tres tropiezos habituales en Windows:

- Si `python` responde *"no se encontró Python"* con código de salida 9009, lo que tienes
  es el **alias del Microsoft Store**, no un intérprete. Instala Python (Store o
  [python.org](https://www.python.org/downloads/)) y vuelve a abrir la terminal.
- El lanzador `py` **solo existe si instalaste desde python.org**; la versión del
  Microsoft Store no lo trae. Usa `python` y funciona en ambos casos.
- `source` no existe en PowerShell: el script de activación es `.venv\Scripts\Activate.ps1`,
  sin `source` delante. Si da error de directivas de ejecución:
  `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned`.

### Configurar el `.env`

Con el entorno virtual **ya activado** (para que `python` sea el del venv):

```bash
cp backend/.env.example backend/.env
python -c "import secrets; print(secrets.token_hex(32))"
```

`cp` funciona igual en PowerShell (es alias de `Copy-Item`).

Pega el valor generado en `SECRET_KEY` dentro de `backend/.env`:

```
DATABASE_URL=sqlite:///./habits.db
SECRET_KEY=<el valor generado arriba>
```

La app **no arranca sin `SECRET_KEY`**: `backend/auth.py` lanza un `RuntimeError` al
importar. Es intencional — no hay valor por defecto inseguro, y la clave nunca va en el
código. Cada entorno tiene la suya; no reutilices la de producción en local.

### Levantar el servidor

Desde la **raíz del repo**, no desde `backend/`:

```bash
uvicorn backend.main:app --reload
```

Disponible en <http://localhost:8000>.

Los módulos importan con rutas absolutas (`from backend.database import ...`), así que
`backend` tiene que resolverse como paquete desde la raíz. Correrlo con
`cd backend && uvicorn main:app` falla con `ModuleNotFoundError`.

La base de datos SQLite se crea sola en el primer arranque: `create_db_and_tables()` corre
al importar `backend/main.py`. No hay migraciones ni pasos extra. El archivo `habits.db`
queda en la **raíz del repo**, no en `backend/`, porque el `DATABASE_URL` por defecto
(`sqlite:///./habits.db`) es relativo al directorio desde el que arrancas el server.

## API

Documentación interactiva generada por FastAPI (con el server corriendo):

- Swagger UI: <http://localhost:8000/api/docs>
- ReDoc: <http://localhost:8000/api/redoc>
- OpenAPI JSON: <http://localhost:8000/api/openapi.json>

Están bajo `/api/`, no en `/docs`.

Los endpoints se agrupan por módulo, todos con prefijo `/api`:

| Prefijo | Qué cubre |
|---|---|
| `/api/auth` | Registro y login |
| `/api/habits` | Entradas diarias, estadísticas, racha y definiciones de hábitos |
| `/api/projects` | CRUD de proyectos y resumen de progreso |
| `/api/tasks` | CRUD de tareas |
| `/api/pomodoro` | Registro y estadísticas de sesiones |

Todos requieren `Authorization: Bearer <token>` salvo `/api/auth/*`, `/api` y `/health`.

### Ejemplo

Registrar un usuario:

```bash
curl -X POST "http://localhost:8000/api/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email": "tu@email.com", "password": "secret123"}'
```

Iniciar sesión — es **form-data**, no JSON (usa `OAuth2PasswordRequestForm`), y el campo
se llama `username` aunque contenga el email:

```bash
curl -X POST "http://localhost:8000/api/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=tu@email.com&password=secret123"
```

Devuelve `{"access_token": "...", "token_type": "bearer"}`. Con ese token:

```bash
curl "http://localhost:8000/api/habits?month=3&year=2026" \
  -H "Authorization: Bearer TU_TOKEN_AQUI"
```

Los ejemplos usan contraseña ASCII a propósito. La API acepta UTF-8 sin problema, pero
**Git Bash en Windows** convierte los acentos a CP1252 al pasar el argumento a `curl.exe`,
manda UTF-8 inválido y la API responde `400 There was an error parsing the body`. Si
necesitas probar con acentos desde Windows, usa PowerShell o pasa el cuerpo desde un
archivo con `--data-binary @cuerpo.json`.

## Estructura

```
habit-tracker/
├── backend/
│   ├── main.py            # Entry point: crea la app, monta routers, sirve el frontend
│   ├── database.py        # Engine SQLite, create_db_and_tables(), get_session()
│   ├── models.py          # User, HabitEntry, Habit, Project, Task, PomodoroSession
│   ├── schemas.py         # Esquemas de request/response
│   ├── auth.py            # Hashing, JWT, get_current_user
│   ├── .env.example       # Plantilla del .env (el .env real no se versiona)
│   └── routers/           # auth, habits, projects, tasks, pomodoro
├── index.html             # Única página: ambas vistas y todos los modales
├── styles.css             # Variables de tema en :root / [data-theme]
├── script.js              # Núcleo: auth, hooks, apiFetch, calendario, hábitos, tema
├── projects.js            # Tabs con swipe, proyectos y tareas
├── pomodoro.js            # Timer y envío de sesiones
├── VERSION                # Semver, leído por el backend y mostrado en la UI
└── requirements.txt
```

El frontend se sirve con un `@app.get` por archivo en `main.py` — no hay `StaticFiles`
montado, así que un archivo JS nuevo necesita su propia ruta o devuelve 404.

## Notas

- **Sin migraciones.** No hay Alembic. `create_all()` crea tablas nuevas al arrancar, pero
  no hace `ALTER TABLE`: agregar una columna a un modelo existente no se aplica sobre una
  base que ya tiene datos. Requiere migración manual.
- **Sin tests ni CI** por ahora.
- **Deploy manual** sobre un VPS Ubuntu con Caddy como reverse proxy y systemd para el
  servicio.
- Rotar el `SECRET_KEY` invalida todos los tokens emitidos: los usuarios tienen que volver
  a hacer login.

Para las convenciones internas y el detalle de arquitectura, ver [CLAUDE.md](CLAUDE.md).
