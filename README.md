# Habit Tracker

App personal de organización hecha de módulos sobre una misma cuenta. Cada quien enciende
los que usa en *Mi perfil*:

- **Proyectos y tareas** (todos) — tableros kanban con columnas configurables. Cada tarjeta
  es una tarea con proyecto, etiquetas, descripción, checklist, comentarios y un estimado
  opcional. También hay vista Lista, y cada proyecto tiene su ficha con todo su tiempo.
- **Pomodoro** (todos) — cronómetro, pomodoro o registro manual, con tiempo por proyecto,
  tarea y etiqueta.
- **Reportes** (todos) — tiempo por día, proyecto, etiqueta y hora, tareas terminadas y
  rachas de hábitos, por semana, mes o rango.
- **Hábitos** (activo por defecto, se puede apagar) — calendario mensual, marcado por día,
  racha con escudos, días de descanso y pausa por vacaciones.
- **Plan Maker** (por invitación, gratis) — costeo de proyectos: tarifa por hora,
  presupuesto, gastos y materiales (se pueden pegar desde Excel o Google Sheets), costo y
  margen por proyecto, y cuánto se desvía uno de lo que estima.

Backend FastAPI + SQLite con autenticación JWT. Frontend estático (HTML/CSS/JS vanilla,
sin build step ni dependencias) servido por la misma app.

Producción: <https://habits.yoshidev22.com>

## Por qué la racha funciona así

La app busca que formes hábitos y alcances lo que te propones, no que la abras por miedo a
perder un número. Por eso un día suelto no borra tu racha: faltar una vez no afecta de
forma importante la formación de un hábito (Lally et al., 2010), y las metas con un margen
de emergencia se sostienen más que las que no lo tienen (Sharif y Shu, 2017, 2019). Una
racha rota, en cambio, sí empuja a abandonar (Silverman y Barasch, 2023): de ahí los
escudos, los días de descanso, la pausa por vacaciones y la pregunta "¿Olvidaste anotar
ayer?". Las fuentes
completas y qué decisión sostiene cada una están en [docs/referencias.md](docs/referencias.md).

Este README cubre la instalación y la API. Para usar la web —marcar hábitos, registrar
tiempo, corregir un registro— está la [guía de uso](GUIA-DE-USO.md).

## Stack

- FastAPI 0.109 sobre uvicorn
- SQLModel 0.0.14 (SQLAlchemy + Pydantic) sobre SQLite
- python-jose para JWT, bcrypt para las contraseñas
- Frontend vanilla, sin bundler

## Instalación

Requiere **Python 3.10+** (la CI prueba 3.10 y 3.12; en desarrollo, 3.13). El repo **no incluye** la base de datos ni el
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
pip install -r requirements.lock
```

**Windows (PowerShell):**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.lock
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

### Reportes automáticos y borrado de cuentas (opcional, en el servidor)

La app genera reportes con el botón sin nada más. Para que además salgan **solos** (cada
lunes los de la semana anterior y cada día 1 los del mes anterior: tiempo, hábitos y, con
el plan Maker, costos) y para que se borren las cuentas cuyo borrado programado ya venció,
hace falta un timer de systemd que corra una vez al día. No vive dentro de uvicorn: con
reinicios o varios workers dispararía dos veces.

`deploy/habit-reports.service` y `deploy/habit-reports.timer` son plantillas. Cambia en el
`.service` el usuario, el grupo y la ruta del repo (`CHANGE_ME` y `/path/to/habit-tracker`),
y luego:

```bash
sudo cp deploy/habit-reports.service deploy/habit-reports.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now habit-reports.timer
```

Para probarlo sin guardar nada: `.venv/bin/python scripts/generate_reports.py --dry-run`
(y lo mismo con `scripts/purge_accounts.py`). Correrlo ya: `sudo systemctl start
habit-reports.service`; lo que hizo: `journalctl -u habit-reports.service`. Correrlo dos
veces no duplica reportes. Si una versión cambia la plantilla, su CHANGELOG lo dice en
*Para actualizar*: hay que volver a copiarla y hacer `daemon-reload`.

### Avisos para todas las cuentas

Un aviso de mantenimiento (o de una caída) llega a la campanita de todas las cuentas
mientras esté vigente. Desde la raíz del repo, con el servicio ya en la 1.26 o posterior:

```bash
.venv/bin/python scripts/announce.py --title "Mantenimiento" --body "La app se reinicia hoy a las 22:00 (5 min)." --hours 24
.venv/bin/python scripts/announce.py --list
.venv/bin/python scripts/announce.py --end 1   # lo quita de todas las campanitas
```

Sin `--hours`, sigue hasta `--end`.

## Pruebas

```bash
pip install -r requirements-dev.txt
pytest            # API (rápidas, sin navegador)
pytest -m ui      # navegador (necesita Edge o Chrome)
```

Usan una base temporal: no tocan la de desarrollo.

## API

Documentación interactiva generada por FastAPI (con el server corriendo):

- Swagger UI: <http://localhost:8000/api/docs>
- ReDoc: <http://localhost:8000/api/redoc>
- OpenAPI JSON: <http://localhost:8000/api/openapi.json>

Están bajo `/api/`, no en `/docs`.

Los endpoints se agrupan por módulo, todos con prefijo `/api`:

| Prefijo | Qué cubre |
|---|---|
| `/api/auth` | Registro, login, perfil y módulos de la cuenta (`/me/modules/{módulo}`) |
| `/api/habits` | Marcar un hábito por día, racha con escudos, pausas por vacaciones, hábitos de cada mes, reporte y definiciones |
| `/api/projects` | CRUD de proyectos (etiquetas de las tareas), resumen de progreso, ficha (`/{id}/overview`) y costeo (`/{id}/finance`, plan Maker) |
| `/api/boards` | Tableros y sus columnas |
| `/api/tasks` | Tareas (tarjetas), con su estimado, su checklist y sus comentarios |
| `/api/tags` | Etiquetas y tiempo por etiqueta |
| `/api/pomodoro` | Registro y estadísticas de sesiones |
| `/api/costs` | Plan Maker: gastos de cada proyecto, importación, categorías, resumen de costo y margen, y estimado contra real |

Todos requieren `Authorization: Bearer <token>` salvo `/api/auth/*`, `/api`, `/api/version` y `/api/health`.

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
│   ├── models.py          # Tablas de hábitos, proyectos, tablero, tareas y pomodoro
│   ├── schemas.py         # Esquemas de request/response
│   ├── auth.py            # Hashing, JWT, get_current_user
│   ├── boards.py          # "Sin asignar" y columnas de las tareas de cada usuario
│   ├── modules.py         # Módulos de cada cuenta y sus valores por defecto
│   ├── costing.py         # Dinero del plan Maker: mano de obra, gastos, costo, margen, estimados
│   ├── recurring_costs.py # Gastos repartidos entre proyectos y gastos recurrentes
│   ├── reports.py         # Reportes guardados (tiempo, hábitos y costos) y cuáles faltan
│   ├── metrics.py         # Las cifras de un periodo (lo que leen los reportes)
│   ├── habit_report.py    # Cifras y texto del reporte de hábitos
│   ├── cost_report.py     # Cifras y texto del reporte de costos
│   ├── report_ai.py       # El texto de los reportes escrito por la IA (opcional)
│   ├── accounts.py        # Borrar una cuenta, ya o a 30 días
│   ├── ratelimit.py       # Límite de intentos de login y registro, por IP
│   ├── .env.example       # Plantilla del .env (el .env real no se versiona)
│   └── routers/           # auth, habits, projects, boards, tasks, tags, pomodoro, costs
├── docs/                  # Specs por fases y referencias de la racha
├── scripts/
│   ├── migrate.py         # Columnas nuevas en tablas existentes (correr antes de reiniciar)
│   ├── grant_module.py    # Da o quita a una cuenta el acceso a un módulo (plan Maker, IA)
│   ├── generate_reports.py # Reportes automáticos (lo corre el timer de systemd)
│   ├── purge_accounts.py  # Borra las cuentas con el borrado programado vencido (mismo timer)
│   └── announce.py        # Publica un aviso para todas las cuentas (mantenimiento)
├── deploy/                # Plantillas del .service y el .timer de los reportes automáticos
├── tests/                 # pytest: API, y tests/ui/ en navegador
├── index.html             # Única página: las vistas y todos los modales
├── styles.css             # Variables de tema en :root / [data-theme]
├── script.js              # Núcleo: auth, hooks, apiFetch, perfil, tema
├── habits.js              # Hábitos: calendario, racha, configuración, vacaciones
├── projects.js            # Tabs con swipe, vista Lista de proyectos
├── board.js               # Vista Tablero, detalle de tarjeta y "Organizar"
├── pomodoro.js            # Timer y envío de sesiones
├── reports.js             # Vista Reportes
├── project-overview.js    # Ficha de proyecto (tiempo, costeo y estimados)
├── costs.js               # Vista Costos (plan Maker)
├── costs-recurring.js     # Costos: repartir un gasto y los gastos recurrentes
├── saved-reports.js       # Reportes guardados: generar, ver e imprimir
├── notifications.js       # La campanita: registros por confirmar
├── workdays.js            # Festivos y huso horario
├── settings.js            # ⚙️ Configuración (menú de desglose)
├── drilldown.js           # El menú de desglose que comparten los menús de opciones
├── account.js             # Mi perfil: contraseña y borrar la cuenta
├── novedades.js           # Novedades tras actualizar (de NOVEDADES.md)
├── manifest.webmanifest   # Instalable como app
├── icons/                 # Iconos y favicon
├── VERSION                # Semver, leído por el backend y mostrado en la UI
├── requirements.txt       # Dependencias directas (qué usa la app)
└── requirements.lock      # Árbol completo fijado: lo que se instala
```

El frontend se sirve con un `@app.get` por archivo en `main.py` — no hay `StaticFiles`
montado, así que un archivo JS nuevo necesita su propia ruta o devuelve 404.

## Notas

- **Migraciones a mano.** No hay Alembic. `create_all()` crea tablas nuevas al arrancar,
  pero no hace `ALTER TABLE`: una columna nueva en una tabla existente va en
  `scripts/migrate.py`, que se corre antes de reiniciar. Si falta, la app no arranca y el
  log dice qué correr.
- **Pruebas y CI.** `pytest` (API) corre en GitHub Actions en cada push; las de navegador
  (`pytest -m ui`) se corren en local.
- **Deploy manual** sobre un VPS Ubuntu con Caddy como reverse proxy y systemd para el
  servicio y para el timer diario (ver *Reportes automáticos* arriba).
- Rotar el `SECRET_KEY` invalida todos los tokens emitidos: los usuarios tienen que volver
  a hacer login.

Para las convenciones internas y el detalle de arquitectura, ver [CLAUDE.md](CLAUDE.md).
