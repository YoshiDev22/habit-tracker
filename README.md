# Habits Tracker - Backend FastAPI

## Instalación

1. **Instalar dependencias Python:**
```bash
pip install -r requirements.txt
```

2. **Iniciar el servidor:**
```bash
cd backend
uvicorn main:app --reload
```

El servidor estará disponible en: `http://localhost:8000`

## Endpoints de API

### Autenticación

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/api/auth/register` | Registrar nuevo usuario |
| POST | `/api/auth/login` | Iniciar sesión |

### Hábitos

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/habits` | Obtener hábitos (soporta `?month=3&year=2026`) |
| POST | `/api/habits` | Guardar hábitos de un día |
| GET | `/api/habits/stats` | Obtener estadísticas |
| GET | `/api/habits/streak` | Obtener racha actual |

## Documentación Interactiva

FastAPI genera automáticamente documentación Swagger en:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

## Ejemplo de Uso

### Registrar usuario:
```bash
curl -X POST "http://localhost:8000/api/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email": "tu@email.com", "password": "tucontraseña"}'
```

### Iniciar sesión:
```bash
curl -X POST "http://localhost:8000/api/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=tu@email.com&password=tucontraseña"
```

### Obtener hábitos (con token):
```bash
curl -X GET "http://localhost:8000/api/habits?month=3&year=2026" \
  -H "Authorization: Bearer TU_TOKEN_AQUI"
```

## Estructura del Proyecto

```
/webapp-habits
├── backend/
│   ├── main.py          # Entry point
│   ├── database.py      # Config SQLite
│   ├── models.py        # Modelos SQLAlchemy
│   ├── schemas.py       # Pydantic schemas
│   ├── auth.py          # Autenticación JWT
│   └── routers/
│       ├── auth.py      # Endpoints auth
│       └── habits.py   # Endpoints habits
├── requirements.txt
└── README.md
```

## IMPORTANTE: Cambiar SECRET_KEY

En [`backend/auth.py`](backend/auth.py:14), cambia la `SECRET_KEY` por una más segura:

```python
SECRET_KEY = "genera-una-clave-segura-aqui"
```

Puedes generar una con:
```python
python -c "import secrets; print(secrets.token_hex(32))"
```

---

**Próximo paso**: Modificar el frontend (JavaScript) para conectarse a esta API.
