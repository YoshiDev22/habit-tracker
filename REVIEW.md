# REVIEW — Módulo de Logros v1

Rama creada desde `main` (v1.27.1). Sale como **v1.30.0**: el bump de `VERSION`, la sección
de `CHANGELOG.md` y la de `NOVEDADES.md` van en su propio commit antes de desplegar, como
siempre (abajo hay una propuesta de texto para Novedades). Este archivo es para revisar la
rama; se puede borrar antes de fusionarla.

## Qué se implementó

**Módulo `achievements`** (`backend/modules.py`): cualquier cuenta puede encenderlo en
Configuración › Módulos y **nace apagado**. Todo `/api/achievements` responde 403 con el
módulo apagado, también los archivos.

| Pieza | Dónde |
|---|---|
| Tablas nuevas: `achievements`, `achievement_categories`, `achievement_collections`, `achievement_files`, `sos_actions`, `sos_notes` | `backend/models.py` |
| API | `backend/routers/achievements.py` |
| Hitos automáticos, listas de inicio y sorteo del SOS | `backend/achievements.py` |
| Archivos: validación, topes, miniaturas, disco | `backend/achievement_files.py` |
| Pestaña Logros (línea del tiempo, vitrina, detalle, formulario, SOS) | `achievements.js`, `index.html`, `styles.css` |
| Revertir el módulo | `scripts/drop_achievements.py` |
| Pruebas | `tests/test_achievements.py`, casos nuevos en `test_isolation.py`, `test_limits.py` y `test_admin_panel.py`, y `tests/ui/ui_achievements.py` |

Del brief:

- **Logro**: título y fecha obligatorios; fecha exacta o **solo mes y año**; tipo
  (diploma/constancia, anécdota, hito); categoría editable con las seis de inicio; los tres
  campos de anécdota; varias evidencias (PDF, JPG, PNG, WEBP); colección opcional; destacado;
  `origin` = `manual` | `auto` | `objective` (este último solo existe en la lista).
- **Vistas**: línea del tiempo agrupada por año con filtro de categoría y tipo (y "Ver
  ocultos"); vitrina de diplomas y constancias agrupada por colección, con miniatura; detalle
  con todos los campos, evidencias (la imagen se abre dentro del detalle y el PDF en otra
  pestaña) y las acciones Editar, Ocultar y Borrar.
- **SOS**: botón fijo en la pestaña. Muestra hasta 3 logros al azar (anécdotas y destacados
  pesan ×3, sin repetir mientras está abierto, con "Otros logros"), un dato **acumulado**
  (horas totales de un proyecto, días cumplidos de un hábito, racha récord o tareas
  terminadas; nunca semanal y nunca un 0), una acción pequeña de una lista editable y la nota
  "¿Cómo me siento?" con fecha, con su lista de notas anteriores.
- **Hitos automáticos**: 10, 25, 50, 100, 250 y 500 **horas de enfoque por proyecto** y esos
  mismos números en **días cumplidos por hábito** (decisión A). Se guardan como `hito` con
  origen `auto`, con la fecha en que se cruzó el umbral. Se pueden ocultar o borrar, y
  borrados no vuelven a aparecer.

## Qué no se implementó (fuera de alcance o pendiente)

- La pregunta semanal, la integración con objetivos y cualquier IA sobre los logros o las
  notas (fuera de alcance v1).
- **Hitos de hábito en horas (opción C)**: cuando los hábitos tengan duración u objetivos.
  El cambio va en `habit_milestones()`; las claves `habit:<clave>:<n>d` ya escritas no chocan
  con unas nuevas en horas (`...h`).
- **Miniatura de los PDF**: llevan un ícono "PDF". Renderizar un PDF en el servidor necesita
  otra dependencia (poppler o PyMuPDF), y no la agregué.
- **Novedades / CHANGELOG / VERSION**: van en el commit del bump.
- No hay "Notas del SOS" fuera del SOS (solo se ven ahí, en *Notas anteriores*).

## Decisiones y supuestos

- **Módulo apagado = 403 en el servidor**, igual que el costeo de Maker: apagarlo no borra
  nada, pero tampoco se puede leer por la API mientras está apagado.
- **Fecha parcial**: la API recibe y devuelve `date` como `AAAA-MM-DD` o `AAAA-MM`. En la
  base se guarda `achieved_on` (el día 1 si es solo mes) + `date_precision`, así se ordena
  sin columnas extra. Una fecha más de un día en el futuro es 422 (el día de margen es por
  el huso).
- **Hitos**: se crean al pedir la lista o el SOS (perezoso, como los gastos recurrentes);
  no hace falta el timer. Un hito ya escrito no cambia si se renombra el proyecto o se
  borran horas después: es un hecho de ese día. "Sin asignar" y los descansos no cuentan.
  Con el módulo Hábitos apagado no se crean hitos de hábitos (al encenderlo salen con su
  fecha real).
- **Borrar un hito automático** no borra la fila: la marca `is_deleted` (y quita textos y
  archivos) para que la sincronización no lo vuelva a crear.
- **La última categoría y la última acción del SOS no se borran** (409): sin ninguna, la
  cuenta volvería a recibir las de inicio. Borrar una categoría o colección deja sus logros
  sin ella.
- **El panel de administración no ve nada de Logros**, ni siquiera si el módulo está
  encendido (`PRIVATE` en `modules.py`): usar Logros ya dice algo de la persona.
- **Topes** (aprobados): 10 MB por archivo, 200 MB por cuenta, 20 archivos por logro.
  Cambiables en `.env` (`ACHIEVEMENT_FILE_MAX_BYTES`, `ACHIEVEMENT_QUOTA_BYTES`).
- **Pillow 12.2.0** (no 12.3): es la última con ruedas para Python 3.10, el del VPS.
- **Textos de inicio** (categorías y acciones) genéricos; cada quien los cambia.

## Probarlo en local

```bash
source .venv/bin/activate
pip install -r requirements.lock          # trae pillow
uvicorn backend.main:app --reload
```

1. Entrar, ⚙️ Configuración › Módulos › **Logros**. Aparece la pestaña Logros.
2. **+ Nuevo logro**: título, "Solo mes y año", una colección nueva y un PDF y una foto.
3. Ver la línea del tiempo ("junio de 2019") y la Vitrina (agrupada por colección).
4. Tocar el logro: detalle, abrir la imagen, Ocultar / Mostrar, Editar.
5. Registrar más de 10 h en un proyecto (o 10 días de un hábito) y volver a Logros: sale el hito.
6. **SOS**: tres logros, "Otros logros" no repite, un dato acumulado, una acción y la nota.
7. Pruebas:

```bash
pytest tests/test_achievements.py tests/test_isolation.py tests/test_limits.py tests/test_admin_panel.py
pytest                                   # todo (308 pasan)
pytest -m ui tests/ui/ui_achievements.py # navegador
```

Las evidencias de desarrollo quedan en `<repo>/uploads/` (ignorado por git).

## Para desplegar

- **No hay migración**: todo son tablas nuevas que `create_all()` crea al arrancar.
  `migrate.py` no cambió y `check_pending_migrations()` sigue igual.
- **Instalar Pillow** en el venv del VPS: `pip install -r requirements.lock` antes de
  reiniciar (sin él, la app no arranca: `ImportError`).
- **`UPLOADS_DIR`** en `backend/.env` del VPS, en una carpeta **fuera del repo**, del usuario
  que corre el servicio y en 700 (la app crea las subcarpetas en 700 y los archivos en 600).
- **Respaldos**: esa carpeta tiene que entrar en el respaldo junto con la base. Si se
  restaura una sin la otra, quedan filas sin archivo (404) o archivos huérfanos.
- **Tamaño del cuerpo en Caddy**: la app ya rechaza por `Content-Length` antes de leer, pero
  conviene un tope también en el proxy (`request_body { max_size 11MB }` en las rutas de
  subida, o global).
- **Revertir**: desplegar el código sin el módulo y después
  `python3 scripts/drop_achievements.py` (dice qué borraría) y `--yes`.

## Revisar con atención

**Seguridad de archivos**
- `check_upload()` (`backend/achievement_files.py`): el tipo sale de los primeros bytes; las
  imágenes además pasan por `Image.open` + `verify()` + `load()` y se rechaza la que no sea
  del formato que dicen sus bytes. Los PDF **solo** se comprueban por la cabecera `%PDF-`:
  un PDF puede traer JavaScript o contenido activo. Mitigación: solo lo ve su dueño, se
  sirve con `Content-Security-Policy: default-src 'none'; sandbox`, `nosniff` y
  `no-store`, y el navegador lo abre como `blob:` en otra pestaña (el visor de PDF del
  navegador, no la app). Decidir si basta.
- **Bombas de descompresión**: `Image.MAX_IMAGE_PIXELS = 40 M` (global de Pillow; la app no
  abre imágenes en otro lado) y el aviso de Pillow se convierte en error. Probado.
- **Ruta**: el nombre en disco es un uuid que pone la app; `file_path()` comprueba igual que
  no salga de la carpeta de la cuenta. El nombre original solo se enseña (sin carpetas ni
  caracteres de control, 200 caracteres) y viaja en `Content-Disposition` vía Starlette.
- **Tamaño**: sin `Content-Length` es 411 y con uno mayor que el tope (+64 KB) es 413,
  **antes** de leer el formulario; después se vuelve a medir lo leído.
- **Carreras conocidas, pequeñas**: el tope por cuenta y el de 20 por logro se comprueban
  y luego se inserta (dos subidas a la vez pueden pasarse por un archivo). Si el proceso
  muere entre escribir el archivo y el commit, queda un archivo huérfano en disco (nunca una
  fila sin archivo). No lo cubrí: díganme si vale la pena un barrido de huérfanos.

**Permisos**
- Cada consulta filtra por `user_id`; lo ajeno es **404** (logros, archivos, miniaturas,
  categorías, colecciones, acciones y notas), probado en `test_isolation.py::test_achievements`
  y `test_achievements.py::test_file_permissions` (dueño 200, otra cuenta 404, sin token o
  con token falso 401, módulo apagado 403).
- Una categoría o colección ajena no se puede usar en un logro propio (404).
- `<img src>` no lleva el token: por eso `apiFetch(path, {blob: true})` (cambio pequeño en
  `script.js`) y `URL.createObjectURL()`; las URLs se sueltan al cerrar sesión.

**Privacidad**
- Notas del SOS: ninguna ruta de reportes, exportaciones, métricas ni IA lee `sos_notes`;
  `test_sos_notes_never_reach_reports_exports_or_metrics` genera reportes de tiempo y de
  hábitos, el CSV de hábitos y las métricas, y comprueba que no aparezcan. La IA solo
  recibe `ai_payload()` de las cifras del reporte, así que tampoco puede recibirlas.
- Panel: `test_admin_panel.py` siembra marcas en título, textos, categoría, colección,
  nombre de archivo, acción y nota del SOS y exige que no salgan de ningún endpoint, y que
  el módulo no aparezca en la cuenta.

**Migraciones**
- No hay `ALTER TABLE` ni cambios a tablas de otros módulos. Lo único que toca código de
  otros: `purge_user()` borra además la carpeta de la cuenta (después del commit), y
  `_module_state()` del panel omite los módulos privados.
- `scripts/drop_achievements.py` borra solo las seis tablas, las filas de `user_modules`
  del módulo y la carpeta; sin `--yes` solo informa. Probado (las demás tablas quedan).

## Propuesta para NOVEDADES.md (en el commit del bump)

```
### Nuevas funciones
- **Logros**: guarda diplomas, constancias y anécdotas con sus evidencias, en una línea del
  tiempo y una vitrina. Se enciende en Configuración › Módulos.
- **Hitos automáticos**: al llegar a 10, 25, 50… horas en un proyecto o días cumplidos de un
  hábito, se anotan solos en Logros.
- **Botón SOS**: en la pestaña Logros, para un día difícil: logros tuyos al azar, un dato de
  tu registro y una acción pequeña.
```
