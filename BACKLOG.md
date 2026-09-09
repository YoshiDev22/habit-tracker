# BACKLOG

Cola de trabajo de habit-tracker. Cada entrada tiene el síntoma, la causa con
`archivo:línea`, el arreglo propuesto y un criterio de aceptación verificable.

**Cómo usarlo:** elegir *una* entrada y trabajarla completa. No agrupar varias en un
commit. Al terminar, borrar la entrada de este archivo en el mismo commit que la arregla.

**Estado de verificación:** las entradas marcadas *reproducido* se ejecutaron contra el
server local y fallaron de forma observable. Las marcadas *diagnosticado* salen de leer el
código y no se reprodujeron todavía.

Levantado el 2026-09-08 sobre v1.3.0.

| # | Prioridad | Entrada | Estado |
|---|---|---|---|
| 1 | P1 | `delete-habit` responde 200 pero no borra nada | reproducido |
| 2 | P1 | La racha reporta rachas viejas como actuales | reproducido |
| 3 | P2 | Sesión de 30 min sin refresh, y 8 `fetch` que ignoran el 401 | diagnosticado |
| 4 | P2 | Fuente de verdad partida entre `Habit` y localStorage | diagnosticado |
| 5 | P3 | Sin tests ni CI | — |
| 6 | P3 | Dependencias transitivas sin fijar | diagnosticado |
| 7 | P3 | CORS abierto con credenciales | diagnosticado |
| 8 | P3 | `datetime.utcnow()` deprecado | diagnosticado |
| 9 | P4 | Sin favicon ni manifest | diagnosticado |
| 10 | P4 | `passlib` declarado y sin usar | diagnosticado |
| 11 | P4 | `/health` sin uso y 404 detrás del proxy | reproducido |
| 12 | P2 | Pestaña de Reportes sobre el tiempo registrado | pendiente |
| 13 | P3 | Duraciones del pomodoro fijas en el código | pendiente |
| 14 | P4 | Pestañas añadidas por el usuario, a partir de plantillas | épica |

---

## 1 · P1 · `delete-habit` responde 200 pero no borra nada

**Síntoma.** En el modal de un hábito, "🗑️ Eliminar (borrar datos)" responde `200` con
*"Hábito 'X' eliminado de todos los registros"*, la UI se actualiza, pero el histórico
sigue en la base. Reaparece al recargar o al consultar la API.

**Reproducido.** Dos entradas con `lectura` marcado, `DELETE /api/habits/delete-habit`
con `{"habit_key":"lectura"}` → `200`, y `GET /api/habits` sigue devolviendo
`{'lectura': True}` en ambas.

**Causa.** [backend/routers/habits.py:97](backend/routers/habits.py#L97) hace
`del entry.habits_data[habit_key]`: una mutación *in-place* de una columna JSON. Como
`habits_data` está declarada como `JSON` plano en
[backend/models.py:26](backend/models.py#L26), sin `MutableDict`, SQLAlchemy no detecta el
cambio, no marca la fila como sucia y el `commit()` no escribe nada. El `session.add()` de
la línea siguiente tampoco ayuda: la instancia ya está en la sesión y no hay cambio que
registrar.

**Arreglo.** Dos opciones:

- *Acotada:* reasignar el atributo completo en vez de mutarlo —
  `entry.habits_data = {k: v for k, v in entry.habits_data.items() if k != habit_key}`.
- *De raíz:* declarar la columna como `MutableDict.as_mutable(JSON)` en `models.py`, lo que
  arregla toda la clase de bug. **No requiere migración**: es un envoltorio del lado de
  Python, no un cambio de esquema.

Preferir la de raíz si se va a seguir tocando `habits_data`; la acotada si se quiere el
mínimo cambio.

**Aceptación.** Con dos entradas que tengan la clave `X`, un `DELETE` de `X` seguido de
`GET /api/habits` no devuelve `X` en ningún `habits_data`, sin reiniciar el servidor.

---

## 2 · P1 · La racha reporta rachas viejas como actuales

**Síntoma.** Si se dejan días sin marcar, la racha no baja a 0: muestra el largo de alguna
racha anterior, como si estuviera vigente.

**Reproducido.** Cuenta con 5 días consecutivos marcados del 2026-08-20 al 2026-08-24 y
nada desde entonces. Con fecha 2026-09-08 (15 días después),
`GET /api/habits/streak` devuelve `{"streak":5}`. Debería devolver `0`.

**Causa.** [backend/routers/habits.py:337](backend/routers/habits.py#L337). Mientras
`streak == 0`, las dos ramas `elif streak == 0` retroceden un día y siguen iterando, sin
condición de corte. El bucle recorre hasta 365 días hacia atrás hasta encontrar *cualquier*
racha y la devuelve como si fuera la actual. Efecto secundario: hasta 365 queries, una por
día.

**Arreglo.** Primero **decidir la regla de negocio**, que hoy no está escrita en ningún
lado: ¿la racha se corta si hoy no está marcado, o se permite un día de gracia porque el
día todavía no terminó? Lo razonable es: se permite que *hoy* esté vacío (el día sigue en
curso), pero si *ayer* también lo está, la racha es 0.

Luego, reescribir: traer las entradas del rango en **una sola query**, ordenarlas y
recorrerlas en memoria. Documentar la regla elegida en el docstring.

**Aceptación.** Una racha de 5 días que terminó hace 15 días devuelve `0`. Una racha que
incluye ayer devuelve su largo real, marcando hoy o sin marcarlo. Y el endpoint hace una
sola query, no una por día.

---

## 3 · P2 · Sesión de 30 min sin refresh, y 8 `fetch` que ignoran el 401

**Síntoma.** La sesión se cae a los 30 minutos. Peor: según qué parte de la UI se toque
cuando el token ya expiró, la app no cierra sesión — falla en silencio y queda mostrando
datos viejos.

**Causa.** Dos partes independientes:

- [backend/auth.py:25](backend/auth.py#L25): `ACCESS_TOKEN_EXPIRE_MINUTES = 30`, sin
  refresh token ni renovación.
- `script.js` tiene 11 llamadas `fetch()` crudas que no pasan por `apiFetch`. Tres son
  anónimas (`/api`, register, login) y no importan. Las otras **8 mandan `Bearer` y solo
  hacen `console.error` ante un 401**, en vez de cerrar sesión como hace `apiFetch`
  ([script.js:106](script.js#L106)). Están en las líneas 409, 555, 576, 607, 629, 656, 677
  y 799 — todas en el flujo de definiciones de hábitos y en `delete-habit`.

**Arreglo.** Se pueden hacer por separado, en este orden:

1. Migrar los 8 `fetch` autenticados a `apiFetch`. Arregla la inconsistencia de UI y es
   puramente mecánico.
2. Decidir la expiración. Lo más simple para una app personal es subir
   `ACCESS_TOKEN_EXPIRE_MINUTES` a algo como 10080 (7 días). Un refresh token real es más
   correcto pero mucho más trabajo. **Cualquiera de los dos cambios invalida los tokens
   emitidos: todos los usuarios tendrán que volver a hacer login.**

**Aceptación.** (1) `grep "fetch(" script.js` solo devuelve la de `apiFetch` más las tres
anónimas. (2) Con un token expirado a mano, cualquier acción de la UI lleva a la pantalla
de login, no a un error silencioso en consola.

---

## 4 · P2 · Fuente de verdad partida entre `Habit` y localStorage

**Síntoma.** Los colores y las etiquetas de los hábitos no viajan entre dispositivos. Si
se entra desde otro navegador, los hábitos salen con los valores por defecto.

**Causa.** El modelo `Habit` ya tiene `label`, `color`, `icon` e `is_active` en la base
([backend/models.py:29](backend/models.py#L29)), y la API los expone en
`/api/habits/definitions`. Pero el frontend sigue leyendo y escribiendo `habit_colors`,
`habit_labels` y `hidden_habits` en `localStorage` — 17 referencias repartidas por
`script.js`. La base tiene los datos y el navegador los ignora.

**Arreglo.** Migrar la lectura a lo que ya devuelve `/api/habits/definitions`, y las
escrituras a `PATCH /api/habits/definitions/{id}`. `hidden_habits` corresponde a
`is_active=false`, que el endpoint ya soporta. Conviene una migración suave: al primer
login tras el cambio, subir lo que haya en localStorage si el backend no lo tiene, y
después dejar de leerlo.

Ojo con el orden: `loadHabitDefinitionsFromAPI()` llama a `loadSavedColors()`
([script.js:985](script.js#L985)), así que hay que desmontar esa dependencia.

**Aceptación.** Cambiar el color de un hábito, entrar desde otro navegador con la misma
cuenta, y ver el color nuevo. Sin escrituras a `habit_colors` / `habit_labels` /
`hidden_habits` en el código.

---

## 5 · P3 · Sin tests ni CI

**Síntoma.** No hay forma de saber si un cambio rompió algo salvo probando a mano. Las
entradas 1 y 2 de este backlog llevaban tiempo en producción sin que nada avisara.

**Causa.** El repo no tiene tests, ni `requirements-dev.txt`, ni configuración de CI.

**Arreglo.** Empezar chico y donde más duele. `pytest` + el `TestClient` de FastAPI cubren
el backend sin dependencias nuevas en runtime:

- `requirements-dev.txt` con `pytest` y `httpx`.
- Un fixture que use SQLite en memoria y sobreescriba `get_session`, para no tocar
  `habits.db`.
- Primeros tests: los casos de aceptación de las entradas 1 y 2, que hoy fallan. Sirven
  como regresión desde el minuto uno.

CI en GitHub Actions después, cuando haya algo que correr.

**Aceptación.** `pytest` corre en verde desde la raíz del repo, e incluye un test que
falla si se revierte el arreglo de la entrada 1 o la 2.

---

## 6 · P3 · Dependencias transitivas sin fijar

**Síntoma.** Dos instalaciones del mismo `requirements.txt` en fechas distintas producen
entornos distintos. El venv local y el del VPS pueden divergir sin que nada lo indique.

**Causa.** `requirements.txt` fija las 8 dependencias directas, pero ninguna transitiva.
En la instalación del 2026-09-08, `pip` resolvió a lo último disponible ese día:
`pydantic 2.13.5`, `SQLAlchemy 2.0.52`, `cryptography 50.0.1`, `starlette 0.35.1`, entre
otras. Nada de eso está registrado.

**Arreglo.** Congelar el árbol completo. Lo más simple sin agregar herramientas:
`pip freeze > requirements.lock` y usar el lock en producción, dejando `requirements.txt`
como declaración de intención. Alternativa más limpia si se acepta una herramienta nueva:
`pip-tools` con `requirements.in` → `requirements.txt` compilado.

**Aceptación.** Un `pip install` desde cero en dos máquinas produce las mismas versiones,
verificable comparando `pip freeze`.

---

## 7 · P3 · CORS abierto con credenciales

**Síntoma.** Ninguno visible. Es endurecimiento, no un bug.

**Causa.** [backend/main.py:38](backend/main.py#L38) declara `allow_origins=["*"]` junto a
`allow_credentials=True`. La combinación es inválida según la spec de CORS y Starlette la
resuelve reflejando el origen que pida, lo que en la práctica acepta cualquiera. Además es
innecesaria: el frontend se sirve desde el mismo origen que la API, así que no hay petición
cross-origin que permitir.

**Riesgo real acotado:** el token vive en `localStorage`, no en una cookie, así que un sitio
externo no puede robarlo vía CORS. Por eso es P3 y no P1.

**Arreglo.** Restringir a los orígenes conocidos (`https://habits.yoshidev22.com` y
`http://localhost:8000`), o quitar el middleware entero si no se necesita ningún acceso
cross-origin.

**Aceptación.** Una petición con `Origin` arbitrario no recibe
`Access-Control-Allow-Origin` con ese valor. La app sigue funcionando en local y en
producción.

---

## 8 · P3 · `datetime.utcnow()` deprecado

**Síntoma.** Ninguno hoy. `DeprecationWarning` en Python 3.12+; se romperá en una versión
futura.

**Causa.** [backend/auth.py:46](backend/auth.py#L46) y
[backend/auth.py:48](backend/auth.py#L48). El entorno corre Python 3.13.

**Arreglo.** `datetime.now(timezone.utc)`. Cuidado: devuelve un datetime *aware*, mientras
que `utcnow()` devolvía uno *naive*. Revisar que `jwt.encode` reciba lo que espera, y que
el mismo cambio no se cuele a `PomodoroSession.started_at`/`ended_at`, que están declarados
naive a propósito ([backend/models.py:135](backend/models.py#L135)) — mezclar aware y naive
lanza `TypeError` al compararlos.

**Aceptación.** `python -W error::DeprecationWarning -c "import backend.main"` no lanza. El
login sigue emitiendo tokens válidos.

---

## 9 · P4 · Sin favicon ni manifest

**Síntoma.** Un 404 de `/favicon.ico` en cada carga, que ensucia los logs. Y la app, con
gestos táctiles y navegación por tabs, no se puede instalar en el teléfono.

**Causa.** No existen los archivos, y `main.py` no tiene rutas para ellos. Recordar que no
hay `StaticFiles` montado: cada archivo nuevo necesita su propio `@app.get`.

**Arreglo.** Un favicon y su ruta. Si se quiere PWA: `manifest.json` con iconos, el
`<link rel="manifest">` en `index.html`, y un service worker mínimo. La app ya tiene
`theme-color` y es responsive, así que el resto del camino es corto.

**Aceptación.** No hay 404 de favicon en los logs al cargar. Si se hace la PWA, Chrome
ofrece "Instalar".

---

## 10 · P4 · `passlib` declarado y sin usar

**Síntoma.** Ninguno. Es una dependencia muerta.

**Causa.** `requirements.txt` incluye `passlib[bcrypt]==1.7.4`, pero ningún módulo lo
importa: el hashing usa `bcrypt` directamente en
[backend/auth.py:5](backend/auth.py#L5).

**Arreglo.** Quitar la línea de `requirements.txt`.

**Aceptación.** `grep -rn passlib backend/` no devuelve nada, y la app arranca y hace login
con el entorno reinstalado desde cero.

---

## 11 · P4 · `/health` sin uso y 404 detrás del proxy

**Síntoma.** Ninguno hoy. `GET https://habits.yoshidev22.com/health` responde `404` con
cuerpo vacío, pero nada lo consume, así que no rompe nada. Verificado con `curl` contra
producción el 2026-09-08.

**Causa.** Dos cosas independientes:

1. El endpoint existe en [backend/main.py:119](backend/main.py#L119) y devuelve
   `{"status": "healthy"}`, pero ningún cliente lo llama. `grep -rn "/health"` sobre el
   repo solo lo encuentra en su propia definición y mencionado en `README.md` y
   `CLAUDE.md`. Quedó ahí sin consumidor.
2. La regla del reverse proxy en el VPS solo reenvía rutas con un segmento después de
   `/api`, así que `/health` — que cuelga de la raíz — nunca llega a la app. Es la misma
   causa que dejaba la versión en blanco en producción, arreglada en `d0d8886` moviendo
   el dato a `/api/version`.

**Arreglo.** Decisión pendiente, no hay prisa. Tres caminos:

- Dejarlo como está mientras no haya monitorización.
- Si se conecta un monitor de uptime: arreglar la regla de Caddy para que `/health` pase
  al backend. Es cambio en el VPS, deploy manual.
- Si se descarta monitorizar así: borrar el endpoint y su mención en `README.md` y
  `CLAUDE.md`.

**Riesgo de no hacer nada.** Un monitor futuro apuntando a `/health` daría 404 permanente
y reportaría la app como caída estando sana.

**Aceptación.** Según el camino: o `curl -s -o /dev/null -w "%{http_code}"
https://habits.yoshidev22.com/health` devuelve `200`, o `grep -rn "/health"` no encuentra
nada en el repo.

---

## 12 · P2 · Pestaña de Reportes sobre el tiempo registrado

**Síntoma.** Ninguno: es una feature pedida, no un fallo. Hoy el tiempo solo se ve como
un total por proyecto y un desglose por tarea dentro de cada tarjeta. No hay forma de
responder "¿a qué hora rindo más?" ni "¿en qué se me fue la semana?".

**Estado actual — lo que ya está listo y no hay que construir:**

- **La hora exacta de cada sesión ya está guardada**, y desde el primer pomodoro:
  `started_at` y `ended_at` en [backend/models.py:141](backend/models.py#L141), UTC naive.
  Todo el histórico sirve para un reporte de productividad por hora sin migrar nada.
- **`GET /api/pomodoro/stats`** ya devuelve `by_date` y `by_project` agregados
  ([backend/routers/pomodoro.py:107](backend/routers/pomodoro.py#L107)), y acepta
  `date_from` / `date_to`.
- **`GET /api/pomodoro`** lista sesiones crudas, filtrables por proyecto y rango.
- **`source`** distingue lo cronometrado de lo escrito a mano.
- **`seconds_by_task`** en `/api/projects/summary` da el desglose por tarea.
- **El sistema de vistas ya soporta una tercera pestaña**: `goToView()` en
  [projects.js:57](projects.js#L57) usa `VIEW_COUNT` y `translateX(-100 * i%)`, sin nada
  cableado a dos vistas. Falta el `<section>`, el `<button>` de tab, subir `VIEW_COUNT` y
  añadir la tab al array de `goToView()`.

**Arreglo.** Vista "Reportes" como tercera pestaña, después de Proyectos. Contenido
mínimo útil:

- Tiempo por día en un rango (ya está en `by_date`).
- Tiempo por proyecto en ese rango (ya está en `by_project`).
- **Productividad por hora del día**: agrupar las sesiones por la hora local de
  `started_at`. Es lo único que necesita cálculo nuevo; se puede hacer en el cliente
  sobre `GET /api/pomodoro`, o como endpoint `by_hour` si la lista crece.
- Opcional: filtrar por `source` para ver cuánto se está registrando a mano.

**Cuidado con el huso horario.** Los datetimes se guardan en UTC y la hora local se
calcula con el desfase *actual* del navegador. Registros hechos desde otro huso se
pintarían corridos. Para un solo usuario en un huso fijo da igual; si algún día importa,
la solución es guardar el offset en una columna nueva vía `scripts/migrate.py`.

**Aceptación.** Con sesiones repartidas en varias horas y días, la pestaña muestra el
total por día, por proyecto y por hora del día, y las cifras cuadran con las que ya
muestran las tarjetas de proyecto.

---

## 13 · P3 · Duraciones del pomodoro fijas en el código

**Síntoma.** El enfoque dura siempre 25 minutos, el descanso corto 5 y el largo 15. No
hay forma de cambiarlos desde la app: quien trabaje en bloques de 50 minutos, o quiera un
descanso largo de media hora, no puede.

**Causa.** Están escritos como constante en
[pomodoro.js:5](pomodoro.js#L5):

```js
const POMO_DURATIONS = { focus: 1500, short_break: 300, long_break: 900 };
```

`createIdlePomoState()` la lee al construir cada estado, así que cambiarla es cambiar el
código y volver a desplegar.

**Arreglo.** Tres ajustes por usuario: enfoque, descanso corto y descanso largo.

Sobre **dónde guardarlos**, la elección importa y hay precedente en este mismo backlog:
la entrada 4 describe el lío de tener los colores y etiquetas de los hábitos en
`localStorage` en vez de en la base. No repetir ese error — van en el backend, en tres
columnas nullable sobre `users`:

```
pomodoro_focus_seconds, pomodoro_short_break_seconds, pomodoro_long_break_seconds
```

Nullable a propósito: `NULL` significa "usa el valor por defecto", así que las cuentas
que ya existen no necesitan que nadie las rellene. Con `scripts/migrate.py` esto son tres
líneas en su lista de migraciones.

En la UI, un formulario en el modal de perfil, o uno propio colgado del ⚙️. Validar
rangos razonables (entre 1 minuto y 4 horas) para que un cero no deje el timer inservible.

**Lo que NO hay que tocar.** `planned_seconds` ya se guarda en cada
`PomodoroSession`, así que las sesiones pasadas conservan la duración que tenían cuando
se hicieron. Cambiar el ajuste no reescribe el histórico ni descuadra ningún total.

**Cuidado.** Un timer en marcha guarda su `plannedSeconds` en `localStorage`
([pomodoro.js:16](pomodoro.js#L16)). Si el ajuste cambia mientras hay un pomodoro
corriendo, la sesión en curso debe terminar con la duración con la que arrancó, no con la
nueva.

**Aceptación.** Cambiar el enfoque a 50 minutos y el descanso largo a 30, recargar, y ver
que el timer arranca con esos valores. Las sesiones anteriores siguen mostrando su
duración original en el historial del proyecto.

---

## 14 · P4 · Pestañas añadidas por el usuario, a partir de plantillas

**Esto no es una entrada, es una épica.** El resto del backlog se puede trabajar de una
sentada; esto no. Está aquí para que la idea no se pierda y para dejar escritas las
decisiones que hay que tomar antes de escribir código, no como algo que se empiece tal
cual. Antes de tocarlo, hacer la entrada 12: una tercera pestaña fija enseña la mitad de
los problemas por una fracción del trabajo.

**Idea.** Que el usuario pueda añadir las pestañas que necesite para organizarse, a partir
de **plantillas**: horarios, cronograma de un proyecto, dieta, calendario de recordatorios
importantes… Elige una plantilla, la personaliza y la añade a su app.

**Regla de proceso, pedida explícitamente.** Una idea de plantilla **se evalúa antes de
construirse**. No se convierte cada ocurrencia en una plantilla; primero se decide si
merece existir. Criterios propuestos para esa evaluación:

1. **¿Encaja en las formas de dato que ya existen?** La app sabe hacer tres cosas: algo
   que se marca por día (hábitos), algo con elementos y progreso (tareas) y algo con
   tiempo y duración (pomodoro). Una plantilla que se apoye en una de esas tres es barata.
   Una que necesite un modelo nuevo entero, no.
2. **¿La abrirías todas las semanas?** Una plantilla que se usa una vez y se abandona
   cuesta lo mismo de mantener que una que se usa a diario.
3. **¿Se puede hacer sin dependencias nuevas?** El stack es deliberadamente simple, sin
   build step. Una plantilla que pida una librería de gráficos o un motor de calendario
   cambia esa premisa y hay que decidirlo aparte, no colarlo dentro de la plantilla.
4. **¿Cuánto backend nuevo pide?** Reutilizar endpoints existentes es la diferencia entre
   una tarde y una semana.

**Estado actual — lo que hoy lo impide.** Las vistas están escritas a mano, no son datos:

- `VIEW_COUNT = 2` en [projects.js:55](projects.js#L55), usado por el swipe y por la
  navegación con teclado.
- `goToView()` recorre un array literal `[tabCalendar, tabProjects]`
  ([projects.js:68](projects.js#L68)).
- Cada vista es un `<section>` escrito en `index.html`, y cada tab un `<button>`.

El primer paso real, y probablemente el único commit que se puede hacer solo, es
**convertir esa lista en datos**: que las pestañas se construyan recorriendo un array, con
el swipe y el teclado leyendo su longitud. Sin eso, cualquier plantilla es un parche.

**Modelo de datos, la decisión de fondo.** Hará falta al menos una tabla de pestañas del
usuario (`user_id`, plantilla, título, icono, orden, activa) más el contenido de cada una.
Para el contenido hay dos caminos y conviene elegirlo a conciencia:

- **Una tabla por plantilla.** Consultas claras, agregación fácil, migración por cada
  plantilla nueva.
- **Una tabla genérica con una columna JSON.** Añadir plantillas no toca el esquema, pero
  se pierde poder consultar el contenido. Y aquí hay cicatriz: la entrada 1 de este
  backlog es exactamente un bug de mutar una columna JSON in-place sin `MutableDict`. Si
  se va por JSON, declararlo `MutableDict.as_mutable(JSON)` desde el primer día.

**Nota sobre migraciones.** Las tablas *nuevas* las crea `create_all()` sola al arrancar,
sin migración — igual que pasó con `projects`, `tasks` y `pomodoro_sessions`. Solo las
*columnas* añadidas a tablas existentes necesitan `scripts/migrate.py`.

**Cuidado con la plantilla de recordatorios.** Es la más pedida y la más engañosa: avisar
de algo a una hora concreta **no funciona con lo que hay hoy**. La notificación que se
añadió en 1.5.0 solo se dispara con la página abierta. Un recordatorio de verdad necesita
un service worker y push, o aceptar por escrito que solo avisa si la app está abierta. Eso
se decide *antes* de prometer la plantilla, no después.

**Riesgo.** Aquí es donde una app personal se convierte en una plataforma. El coste real
no es construir la primera plantilla, es mantener cinco. Empezar con **dos plantillas
concretas y escritas a mano** sobre el sistema de pestañas dinámico, y no construir un
motor genérico hasta que duela repetir código.

**Aceptación (del primer paso, no de la épica).** Las pestañas se generan desde un array
de configuración: añadir una entrada al array crea su tab y su vista, y el swipe, las
flechas del teclado y `Home`/`End` funcionan sin tocar ninguna constante.
