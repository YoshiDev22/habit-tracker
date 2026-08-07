# CLAUDE.md — habit-tracker

Proyecto personal de Yoshio. Responde en español salvo que el prompt esté en inglés.
Código, comentarios, nombres de variables y mensajes de commit: en inglés.

## Qué es

App de seguimiento de hábitos. Backend FastAPI + SQLite con autenticación JWT,
frontend estático (HTML/CSS/JS vanilla, sin build step).

- Repo: https://github.com/YoshiDev22/habit-tracker
- Producción: https://habits.yoshidev22.com

## Stack

Versiones confirmadas en `requirements.txt` (no hay `pyproject.toml` en el repo):

- `fastapi==0.109.0`, servido con `uvicorn[standard]==0.27.0`
- `sqlmodel==0.0.14` (SQLAlchemy + Pydantic) como ORM sobre SQLite
- `python-jose[cryptography]==3.3.0` para JWT
- `bcrypt==4.0.1` para hashear/verificar contraseñas — usado directamente en `backend/auth.py`.
  `passlib[bcrypt]==1.7.4` está en `requirements.txt` pero no se importa en ningún módulo del código.
- `python-multipart==0.0.6` (requerido por FastAPI para leer el form-data de `OAuth2PasswordRequestForm` en `/api/auth/login`)
- `python-dotenv==1.0.1` para cargar `backend/.env`
- Frontend estático servido por la misma app (sin build step)

## Estructura

```
habit-tracker/
├── backend/
│   ├── __init__.py
│   ├── main.py            # Entry point FastAPI. Crea la app, monta routers, sirve el frontend estático
│   ├── database.py        # Engine SQLModel/SQLite, create_db_and_tables(), get_session()
│   ├── models.py          # Tablas SQLModel: User, HabitEntry, Habit
│   ├── schemas.py         # Esquemas Pydantic/SQLModel de request/response
│   ├── auth.py            # Hashing, JWT (create/verify), lee SECRET_KEY desde backend/.env
│   ├── .env               # no versionado. Contiene DATABASE_URL y SECRET_KEY
│   └── routers/
│       ├── __init__.py
│       ├── auth.py        # POST /api/auth/register, POST /api/auth/login
│       └── habits.py      # /api/habits/* (CRUD de entradas y definiciones de hábitos)
├── index.html
├── script.js
├── styles.css
├── requirements.txt
├── README.md
└── CLAUDE.md
```

- Frontend estático con rutas de API **relativas** (no hardcodear el dominio)

## Setup local (repo recién clonado)

El repo **no incluye** ni la base de datos ni el `.env`. Ambos hay que crearlos:

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Crear backend/.env
# SECRET_KEY de desarrollo (NO reutilizar el de producción):
python -c "import secrets; print(secrets.token_hex(32))"
```

`backend/.env` mínimo:

```
DATABASE_URL=sqlite:///./habits.db
SECRET_KEY=<el valor generado arriba>
```

Levantar el servidor (**desde la raíz del repo**, no desde `backend/`):

```bash
uvicorn backend.main:app --reload
```

`backend/main.py` importa con rutas absolutas (`from backend.database import ...`,
`from backend.routers import ...`), así que `backend` debe resolverse como paquete desde
la raíz del repo. `README.md` indica `cd backend && uvicorn main:app --reload`, pero eso
está desactualizado y falla con esos imports — usar siempre `backend.main:app` desde la raíz.

La base de datos **se crea sola al arrancar**: `backend/main.py` llama a
`create_db_and_tables()` (definida en `backend/database.py`, hace
`SQLModel.metadata.create_all(bind=engine)`) de forma incondicional al importar el módulo,
antes de instanciar `FastAPI()`. No hace falta ningún paso extra ni migraciones para
crear el esquema inicial.

## Reglas duras

- **Nunca** commitear `.env`, `*.db`, `*.sqlite3`, ni `.venv/`. Verificar `.gitignore`.
- **Nunca** poner secretos, `SECRET_KEY` ni credenciales en el código. Van en `.env`.
- El `SECRET_KEY` de producción vive solo en el VPS. Rotarlo invalida todos los tokens
  existentes: los usuarios tendrían que volver a hacer login.
- URLs de API en el frontend: **siempre relativas**. Hardcodear el dominio rompe
  el desarrollo local.
- Migraciones de esquema en SQLite: no hay Alembic. Cualquier cambio en los modelos
  necesita un plan explícito de migración antes de tocar producción — la base de prod
  tiene datos reales y no está en el repo.

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
