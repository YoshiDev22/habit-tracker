# BACKLOG

Cola de trabajo de habit-tracker. Cada entrada tiene el síntoma, la causa con
`archivo:línea`, el arreglo propuesto y un criterio de aceptación verificable.

**Cómo usarlo:** elegir *una* entrada y trabajarla completa. No agrupar varias en un
commit. Al terminar, borrar la entrada de este archivo en el mismo commit que la arregla.

**Estado de verificación:** las entradas marcadas *reproducido* se ejecutaron contra el
server local y fallaron de forma observable. Las marcadas *diagnosticado* salen de leer el
código y no se reprodujeron todavía.

Levantado el 2026-09-08 sobre v1.3.0. Revisado el 2026-09-22 sobre v1.10.0 (tableros).

| # | Prioridad | Entrada | Estado |
|---|---|---|---|
| 4 | P2 | Fuente de verdad partida entre `Habit` y localStorage (habit_colors) | parcial |
| 5 | P3 | Sin tests ni CI | — |
| 6 | P3 | Dependencias transitivas sin fijar | diagnosticado |
| 9 | P4 | Sin favicon ni manifest | diagnosticado |
| 12 | P2 | Pestaña de Reportes sobre el tiempo registrado | pendiente |
| 13 | P3 | Duraciones del pomodoro fijas en el código | pendiente |
| 14 | P4 | Pestañas añadidas por el usuario, a partir de plantillas | épica |
| 17 | P2 | Metas con hábitos y avance medible | épica |
| 20 | P4 | Editar comentarios y elementos del checklist | pendiente |
| 21 | P4 | Tableros compartidos entre usuarios | épica |

---

## 4 · P2 · Fuente de verdad partida entre `Habit` y localStorage (habit_colors)

**Estado:** Parcialmente resuelto, y ya solo queda el color.

- `hidden_habits` se eliminó del código y de `localStorage`: archivar y borrar van
  directos al backend (`PATCH /api/habits/definitions/{id}` con `is_active: false`,
  `DELETE /api/habits/delete-habit` y `DELETE /api/habits/definitions/{id}`).
- `habit_labels` también se fue. El nombre lo manda el backend (`HABIT_LABELS` se llena en
  `loadHabitDefinitionsFromAPI()`), y el emoji igual, en `HABIT_ICONS`. Los dos se editan
  contra `PATCH /api/habits/definitions/{id}`.
- Falta `habit_colors`.

**Síntoma.** El color de cada hábito no viaja entre dispositivos: entrando desde otro
navegador, los hábitos salen con el color por defecto.

**Causa.** El modelo `Habit` ya tiene `color` en la base
([backend/models.py:29](backend/models.py#L29)) y la API lo expone en
`/api/habits/definitions`, pero `renderHabitRows()` hace ganar al valor de
`localStorage.habit_colors` sobre el del backend, y `handleSaveHabits()` escribe ahí en vez
de mandarlo. La base tiene el dato y el navegador lo ignora.

**Arreglo.** Leer el color de `/api/habits/definitions` y mandarlo en el mismo `PATCH` que
ya se usa para el emoji (`handleSaveHabits()` compara contra `existing` y manda solo lo que
cambió: agregar `color` a esa comparación es el cambio). Conviene una migración suave: en
el primer guardado tras el cambio, subir lo que haya en `habit_colors` y después dejar de
leerlo.

Ojo con el orden: `loadHabitDefinitionsFromAPI()` llama a `loadSavedColors()`, así que hay
que desmontar esa dependencia.

**Aceptación.** Cambiar el color de un hábito, entrar desde otro navegador con la misma
cuenta y ver el color nuevo. Sin escrituras a `habit_colors` en el código.

---

## 5 · P3 · Sin tests ni CI

**Síntoma.** No hay forma de saber si un cambio rompió algo salvo probando a mano o con
guiones sueltos.

**Causa.** El repo no tiene tests, ni `requirements-dev.txt`, ni configuración de CI.

**Lo que ya se hizo fuera del repo.** La 1.10.0 se desarrolló con 17 baterías de prueba
escritas a mano en una carpeta temporal, que no se versionaron:

- **API**: un cliente `urllib` contra el server real sobre una copia de la base, que
  simula el deploy completo (base con el código viejo → `migrate.py` → código nuevo) y
  comprueba el relleno, el aislamiento entre usuarios y las reglas de cada endpoint.
- **Navegador**: Edge headless controlado por el protocolo de DevTools con `websockets`
  (ya instalado por `uvicorn[standard]`), sin Playwright ni Node. Probó el tablero, el
  arrastre, el detalle, el reloj en vivo, la persistencia al cerrar el navegador o la
  sesión, y el teléfono en 390 px.

Encontraron bugs reales antes de salir: `Field(regex=...)` que no valida, el tiempo que
no seguía a la tarea, el POST de despedida del logout sin token.

**Arreglo.** Traer lo anterior al repo como punto de partida, sin dependencias nuevas en
runtime:

- `requirements-dev.txt` con `pytest` y `httpx`; el backend con el `TestClient` de FastAPI
  y un fixture de SQLite en memoria que sobreescriba `get_session`.
- Un test que reproduzca el deploy (base vieja → `migrate.py` → arranque) con la regla
  de `check_pending_migrations()`.
- Las pruebas de navegador, si se traen, en `tests/ui/`, opcionales y fuera de CI al
  principio: dependen de tener Edge o Chrome.

CI en GitHub Actions después, cuando haya algo que correr.

**Aceptación.** `pytest` corre en verde desde la raíz del repo e incluye la simulación del
deploy y el aislamiento entre usuarios de tableros, tareas y etiquetas.

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

## 12 · P2 · Pestaña de Reportes sobre el tiempo registrado

**Síntoma.** Ninguno: es una feature pedida, no un fallo. Hoy el tiempo solo se ve como
total por tarjeta, por proyecto (vista Lista) y "Hoy". No hay forma de responder "¿a qué
hora rindo más?" ni "¿en qué se me fue la semana?".

**Plan acordado (2026-09-22).** Tercera pestaña, "Reportes", después de Tableros:

- **Rango**: Esta semana / Este mes / Personalizado, con flechas para ir al anterior.
- **Resumen**: tiempo total, tareas terminadas, promedio por día y comparación con el
  período anterior ("+2 h vs. la semana pasada").
- **Tiempo por día**: barras, con los días de descanso (`users.rest_days`) marcados.
- **Por proyecto**: barras horizontales; "Sin asignar" aparte, como tiempo sin clasificar.
- **Por etiqueta**: desglose (cuenta doble por diseño), "Sin etiqueta" y, al elegir
  varias, su total sin contar doble.
- **¿A qué hora rindes más?**: mapa de calor día de la semana × hora.
- **Tareas terminadas** en el rango y **cronometrado vs. registrado a mano**.

**Lo que ya existe y no hay que construir:**

- La hora exacta de cada sesión (`started_at`/`ended_at`, UTC naive), su día local
  (`session_date`) y su origen (`source`), desde el primer pomodoro.
- `GET /api/pomodoro/stats` con `by_date` y `by_project`, filtrable por fechas.
- `GET /api/tags/summary` con el desglose, `combined_*` (varias etiquetas sin contar doble)
  y `untagged_*`, filtrable por fechas.
- `tasks.completed_at` con la fecha local del cliente (entrada 15, cerrada).
- El sistema de vistas: `goToView()` y `VIEW_COUNT` en [projects.js](projects.js), y
  `viewChangedHooks` para lo que dependa de la vista.

**Decisiones.** Gráficas en HTML/CSS y SVG, sin librerías. El mapa por hora se calcula en
el cliente sobre `GET /api/pomodoro` con la hora local del navegador. Única API nueva
probable: tareas terminadas por rango. **Sin cambios de esquema.**

**Commits propuestos.** (1) Pestaña con el selector de rango, (2) resumen y por día,
(3) por proyecto y por etiqueta, (4) mapa por hora, (5) tareas terminadas y comparación.

**Cuidado con el huso horario.** Los datetimes se guardan en UTC y la hora local se
calcula con el desfase *actual* del navegador. Registros hechos desde otro huso se
pintarían corridos. Para un solo usuario en un huso fijo da igual; si algún día importa,
la solución es guardar el offset en una columna nueva vía `scripts/migrate.py`.

**Aceptación.** Con sesiones repartidas en varias horas y días, la pestaña muestra el
total por día, por proyecto, por etiqueta y por hora, y las cifras cuadran con las de las
tarjetas y la vista Lista.

---

## 13 · P3 · Duraciones del pomodoro fijas en el código

**Síntoma.** El enfoque dura siempre 25 minutos, el descanso corto 5 y el largo 15. No
hay forma de cambiarlos desde la app: quien trabaje en bloques de 50 minutos, o quiera un
descanso largo de media hora, no puede.

**Causa.** Están escritos como constante en
[pomodoro.js:5](pomodoro.js#L5):

```js
const POMO_DURATIONS = { focus: 1500, short_break: 300, long_break: 900, stopwatch: 0 };
```

Desde la 1.10.0 no hay tarjeta de reloj: el pomodoro se inicia desde una tarjeta y los
descansos desde la oferta de la barra al terminar (`startBreak`). El ajuste tiene que
llegar a esos dos caminos.

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

En la UI, un formulario en el modal de perfil (el ⚙️ del tablero es para organizar
tableros, proyectos y etiquetas). Validar
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

---

## 17 · P2 · Metas con hábitos y avance medible

**Esto es una épica.** Que los hábitos estén al servicio de **metas** con avance visible,
sin perder el registro diario que ya existe. Planteado el 2026-09-22; modelo acordado con
Yoshio el 2026-09-23.

**Modelo acordado: una meta agrupa hábitos; los hábitos siguen siendo sí/no.**

```
Meta "Bajar de peso" (85 → 75 kg)          Meta "Leer 10 libros"      Meta "Dejar de fumar"
 ├── hábito Ejercicio  (sí/no, "30 min")    ├── hábito Leer            └── hábito Sin fumar
 └── hábito Comer bien (sí/no)               │   (sí/no, "15 min mín.")      (sí/no)
                                             └── registro: libro 1, 2…
```

- **Hábitos: no cambian de tipo.** Se marcan hechos o no, como hoy. Se les puede añadir un
  texto de mínimo recomendado ("15 minutos al día"), que es solo una guía para el usuario.
  No hay hábitos de "cantidad por día" ni de "evitar": dejar de fumar es un hábito sí/no
  ("hoy no fumé") y su dato son los días y la racha, como cualquier otro.
- **Meta: tres formas, todas opcionales para la parte numérica:**

  | Meta | Ejemplo | Qué anota el usuario | Avance |
  |---|---|---|---|
  | Solo hábitos | Meditar más | Nada extra | Días cumplidos de sus hábitos, racha |
  | Contador | Leer 10 libros | "+1" a mano (terminé un libro) | "3 de 10 libros" |
  | Medición | Bajar de 85 a 75 kg | Un valor cuando se mide | "81 kg, te faltan 6" |

- **Avance en días primero**: "Ejercicio 18 de 30 días este mes", "12 días sin fumar
  (récord 20)", y la cifra de la meta si la tiene. El porcentaje, como mucho de apoyo.
- **Tiempo del tablero (opcional, acordado).** Una meta puede enlazarse a un proyecto o
  una etiqueta y mostrar "llevas 3 h de 5 h esta semana" con el tiempo ya registrado en
  el cronómetro. Es **solo lectura**: la misma suma de sesiones que hará Reportes
  (entrada 12), reutilizada; el timer y las tarjetas no cambian. Por eso va después de
  Reportes y puede dejarse para una segunda entrega si complica la primera.

**Esquema (borrador, avisar el impacto antes de escribir código).** Tablas nuevas, que
`create_all()` crea solas: `goals` (nombre, tipo solo-hábitos/contador/medición, valor
inicial, meta, unidad, fecha límite opcional, `project_id`/`tag_id` opcionales),
`goal_habits` (meta ↔ hábito) y `goal_entries` (meta, fecha local, valor). El texto de
mínimo recomendado sería una columna nueva en `habits` → **va en `scripts/migrate.py`**
(o se guarda en `goal_habits` y se evita tocar `habits`; decidir en el plan). Los hábitos
y su historial (`habit_entries.habits_data`, racha, días de descanso) no se migran.

**Asistente para elegir objetivos (decidido 2026-09-23): plantillas primero, IA después.**
Al crear un objetivo, la app pregunta qué quiere lograr el usuario y le propone hábitos
concretos, cada uno con una explicación breve de cómo ayuda, frecuencia y duración
recomendadas, y una meta medible. El usuario elige, ajusta y confirma; nada se guarda sin
su visto bueno. El avance ("llevas 60 %, sigue así") lo calcula el backend con los datos
del objetivo en las dos fases: gratis, instantáneo y sin inventar números.

*Fase 1 — guiado con plantillas, sin IA (la que se implementa con esta épica).* Que se
sienta como que alguien ayuda, sin llamar a ningún servicio externo:

- Un catálogo de metas escrito a mano (bajar de peso, leer más, dejar de fumar, dormir
  mejor, hacer ejercicio, aprender algo, ahorrar…) con 3-5 hábitos sugeridos cada una:
  texto de por qué ayuda, frecuencia/duración recomendada y meta por defecto editable.
- Flujo en pasos, tono cercano: "¿Qué quieres lograr?" → tarjetas de sugerencia con su
  explicación → elegir y ajustar → confirmar. Opción "Otra meta" para crear a mano.
- Vive en el frontend como datos estáticos (o un JSON servido por la app): sin tabla ni
  endpoint nuevo, salvo lo que ya necesite crear objetivos.
- Mensajes de ánimo según el avance calculado (umbrales fijos: empezar, 25 %, 50 %, 75 %,
  meta cumplida, racha rota), también escritos a mano.
- **Salud**: bienestar general, sin dietas, calorías ni fármacos; metas prudentes; en
  bajar de peso y dejar de fumar, una línea que recomiende apoyo profesional.

*Fase 2 — sugerencias con IA (en espera, no se trabaja por ahora).* Se aplaza para no
exponer una clave de API ni abrir la puerta a un mal uso antes de tener la fase 1 probada.
Plan cuando se retome:

- Solo la sugerencia usa IA: el usuario escribe su meta con sus palabras y recibe hábitos
  con el mismo formato que las plantillas, así la UI de la fase 1 se reutiliza tal cual.
- Llamada **desde el backend** (`POST /api/goals/suggest`, con sesión) con la librería
  `anthropic`; la clave en `backend/.env` del VPS, nunca en el navegador ni en el repo.
  Respuesta como JSON validado contra un esquema (structured outputs).
- Contra el mal uso: límite por usuario (p. ej. 10 al día) y tope de gasto en la consola
  de Anthropic; longitud máxima del texto; el prompt solo sugiere hábitos y rechaza lo
  demás; la salida nunca se ejecuta ni se guarda sin confirmación; manejar la negativa del
  modelo (`stop_reason: "refusal"`). Si la API falla o se llega al límite, se cae a las
  plantillas.
- Decidir entonces: modelo (costo aprox. por sugerencia de ~$0.01 a ~$0.08 USD según el
  modelo), y avisar que el texto de la meta se envía a Anthropic.

**Decidido (2026-09-23): el Calendario no cambia.** Sigue siendo la vista diaria que
motiva con constancia (días marcados, racha). Los objetivos van en un lugar aparte; Yoshio
propone el menú de configuración para crearlos y editarlos. El avance se expresa en días
siempre que se pueda ("12 de 30 días", "8 días sin fumar") y no solo como porcentaje.

**Pendiente para el plan detallado:** dónde se ve el avance a diario (propuesta: una
línea corta junto a cada hábito del Calendario, además de la sección de metas) y el
catálogo de plantillas de la fase 1.

**Orden.** Después de la entrada 12 (Reportes), que no toca el esquema.

---

## 20 · P4 · Editar comentarios y elementos del checklist

**Síntoma.** Un comentario o un elemento del checklist con una errata solo se puede
borrar y escribir de nuevo.

**Causa.** La API ya edita los dos (`PATCH /api/tasks/{id}/comments/{cid}` guarda
`edited_at`; `PATCH /api/tasks/{id}/checklist/{iid}` acepta `text`), pero el detalle de la
tarjeta solo ofrece borrar.

**Arreglo.** Doble clic (o un ✎) para editar en el sitio; Enter guarda, Escape cancela.
Los comentarios ya muestran "· editado" cuando `edited_at` existe.

**Aceptación.** Editar un comentario propio y ver "· editado" tras recargar; editar un
elemento del checklist sin perder si estaba marcado.

---

## 21 · P4 · Tableros compartidos entre usuarios

**Esto es una épica.** Que un tablero se comparta con otra cuenta y los dos vean las
mismas columnas y tarjetas. Para eso los tableros son dueños de sus columnas (1.10.0).

**Ya preparado.** `task_comments.author_id` separado de `user_id` (el dueño): los
comentarios de un tablero compartido no necesitarán migración.

**Lo que obliga a decidir.** Hoy **toda** query filtra por `current_user.id`, y es lo
único que separa los datos entre usuarios. Compartir necesita una tabla de miembros
(`board_id`, `user_id`, rol) y reescribir el acceso de tableros, columnas, tareas,
checklist, comentarios y sesiones de tiempo para "dueño o miembro". Además: qué proyectos
y etiquetas ve un invitado (hoy son del dueño), invitaciones, y quién puede borrar qué.

**Orden.** Solo si de verdad se va a usar con otra persona: es el cambio de seguridad más
grande de la app.
