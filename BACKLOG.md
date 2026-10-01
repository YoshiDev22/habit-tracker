# BACKLOG

Cola de trabajo de habit-tracker. Cada entrada tiene el síntoma, la causa con
`archivo:línea`, el arreglo propuesto y un criterio de aceptación verificable.

**Cómo usarlo:** elegir *una* entrada y trabajarla completa. No agrupar varias en un
commit. Al terminar, borrar la entrada de este archivo en el mismo commit que la arregla.

**Estado de verificación:** las entradas marcadas *reproducido* se ejecutaron contra el
server local y fallaron de forma observable. Las marcadas *diagnosticado* salen de leer el
código y no se reprodujeron todavía.

Levantado el 2026-09-08 sobre v1.3.0. Revisado el 2026-09-22 sobre v1.10.0 (tableros) y el
2026-09-30 sobre v1.16.1 (entradas 5, 6 y 22 cerradas; 24 y 25 nuevas).

| # | Prioridad | Entrada | Estado |
|---|---|---|---|
| 14 | P4 | Pestañas añadidas por el usuario, a partir de plantillas | épica |
| 17 | P2 | Metas con hábitos y avance medible | épica |
| 21 | P4 | Tableros compartidos entre usuarios | épica |
| 23 | P4 | Escudo especial que se gana con hitos de racha | épica |
| 24 | P2 | Módulos por usuario y costeo de proyectos (freelance / maker) | épica |
| 25 | P3 | La guía de uso no cubre el Tablero ni Reportes | diagnosticado |

---

## 14 · P4 · Pestañas añadidas por el usuario, a partir de plantillas

**Esto no es una entrada, es una épica.** El resto del backlog se puede trabajar de una
sentada; esto no. Está aquí para que la idea no se pierda y para dejar escritas las
decisiones que hay que tomar antes de escribir código, no como algo que se empiece tal
cual. La pestaña fija de Reportes (1.12.0) ya enseñó cómo se añade una vista: empezar por
ahí (`VIEW_TABS` y `watchActiveView()` en projects.js).

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

**Estado actual (revisado en v1.16.1).** La mitad del primer paso ya está: la navegación
lee de un array. `VIEW_TABS` ([projects.js:61](projects.js#L61)) lista las tres pestañas,
y `VIEW_COUNT` es su longitud, así que el swipe y el teclado ya no tienen números fijos.
Lo que falta:

- Cada vista sigue siendo un `<section>` escrito en `index.html`, y cada tab un `<button>`.
- El ancho de `.tab-indicator` es un `calc(100% / N)` fijo en `styles.css`.

El siguiente paso es que tabs y secciones **se creen desde ese array**. El interruptor de
módulos de la entrada 24 (ocultar el Calendario si se apaga Hábitos) es el primer caso
real que lo necesita: conviene hacerlos juntos.

**Modelo de datos, la decisión de fondo.** Hará falta al menos una tabla de pestañas del
usuario (`user_id`, plantilla, título, icono, orden, activa) más el contenido de cada una.
Para el contenido hay dos caminos y conviene elegirlo a conciencia:

- **Una tabla por plantilla.** Consultas claras, agregación fácil, migración por cada
  plantilla nueva.
- **Una tabla genérica con una columna JSON.** Añadir plantillas no toca el esquema, pero
  se pierde poder consultar el contenido. Y aquí hay cicatriz: ya hubo un bug de mutar
  una columna JSON in-place sin `MutableDict` (ver `habits_data` en CLAUDE.md). Si se va
  por JSON, declararlo `MutableDict.as_mutable(JSON)` desde el primer día.

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

**Aceptación (del primer paso, no de la épica).** Añadir una entrada a `VIEW_TABS` crea
su tab, su vista y el ancho del indicador, sin tocar `index.html` ni `styles.css`; el
swipe, las flechas del teclado y `Home`/`End` ya funcionan así.

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
  el cronómetro. Es **solo lectura**: la misma suma de sesiones `focus` por rango que ya
  hace Reportes (`GET /api/pomodoro?date_from&date_to`, o `/api/tags/summary` con
  `combined_seconds` para una etiqueta); el timer y las tarjetas no cambian. Puede
  dejarse para una segunda entrega si complica la primera.

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

**Orden.** Reportes (1.12.0), los colores de hábitos en el backend, las pruebas y la CI
(antes entrada 5) ya están: nada bloquea empezar.

**Lugar en la app (decidido 2026-09-30).** Las metas son parte del módulo **Hábitos y
metas**, activo por defecto (ver entrada 24). Es una ruta independiente del costeo de
proyectos: se puede trabajar antes, después o en paralelo.

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

---

## 23 · P4 · Escudo especial que se gana con hitos de racha

**Esto es una épica.** Un escudo aparte de los dos normales que se **gana** al llegar a
un hito (30, 100 o 365 días de racha), se guarda hasta que haga falta y cubre hasta 3 días
seguidos. Premia la constancia larga sin cobrar: se decidió no vender escudos (ver
"Escudos de pago" en [docs/specs/calendario-v2.md](docs/specs/calendario-v2.md) y el
fundamento en [docs/referencias.md](docs/referencias.md)).

**Lo que obliga a decidir.** Si se gasta solo (como los normales) o lo activa el usuario;
si hay uno por hito o se acumulan; cómo se ve junto a los dos escudos de la franja. Como
los normales, puede salir de recorrer el historial en `_walk_streak()`, sin tabla nueva.

**Orden.** Después de la pausa por vacaciones (Fase 6 de Calendario v2): ver primero si,
con pausa y escudos, todavía hace falta.

---

## 24 · P2 · Módulos por usuario y costeo de proyectos (freelance / maker)

**Esto es una épica.** Plan completo, fases, esquema y referencias en
[docs/specs/modulos-y-costeo.md](docs/specs/modulos-y-costeo.md). Planteado y decidido
con Yoshio el 2026-09-30.

**Idea.** Usar lo que la app ya registra (tareas, tiempo por proyecto, tarea y etiqueta)
para lo que hacía la administración en un trabajo anterior con el kanban: sacar horas
hombre, costear proyectos y cotizar los nuevos con el historial ("un proyecto así lleva
unas X horas") más materiales y gastos. **No es un CRM**: nada de prospectos ni embudo.

**Decidido.**

- **Una app de organización hecha de módulos**, no tres apps. Núcleo (tableros, tiempo,
  Reportes) para todos; **Hábitos y metas** activo por defecto (perfil estudiante o
  personal: lo de hoy más la épica 17); **Costeo** apagado por defecto, para freelance y
  makers. Apagar un módulo oculta su UI y no borra nada.
- **Nada empresarial**: sin equipos, roles, facturación ni inventario.
- **Dos rutas independientes**: esta y la 17 no dependen una de la otra; solo comparten
  el interruptor de módulos.
- **Nada cuesta.** Los módulos no son planes de pago; si algún día los hay, el
  interruptor ya marca la frontera.

**Fases** (cada una se despliega sola): 0 base sólida ✅ (lock, CI, sesiones
idempotentes, límite de login) · 1 interruptor de módulos + ficha de proyecto solo lectura ·
2 tarifa y presupuesto · 3 gastos y materiales, con importar CSV · 4 estimado contra real
por tarea · 5 cotizador con historial (rangos P50/P80) · 6 hoja de Google publicada como
CSV, solo lectura.

**Esquema.** Tablas nuevas (`user_modules`, `project_finance`, `project_costs`), sin
migración. La única columna en una tabla existente es `tasks.estimate_minutes` (Fase 4):
**va en `scripts/migrate.py`**, y se avisa el impacto antes de escribirla.

**Orden.** La Fase 1 es chica y útil aunque no se active Costeo: empezar por ahí. Antes
de la Fase 2, cerrar las decisiones abiertas de la spec (moneda, cotización sin estados,
dónde vive la ficha).

**Aceptación (de la Fase 1, no de la épica).** Un usuario apaga "Hábitos y metas" en Mi
perfil y deja de ver el Calendario sin perder nada al volver a encenderlo; al tocar un
proyecto se abre su ficha con el mismo tiempo total que muestran la Lista y Reportes.

---

## 25 · P3 · La guía de uso no cubre el Tablero ni Reportes

**Síntoma.** [GUIA-DE-USO.md](GUIA-DE-USO.md) se escribió antes de los tableros (1.10) y
de Reportes (1.12). Quien la lee no encuentra cómo usar la vista principal de la pestaña
Tableros ni la pestaña Reportes.

**Ya corregido (2026-09-30).** La sección del pomodoro describía la UI de antes
(selectores de proyecto arriba, cierre automático a las 8 h, "las duraciones no se pueden
cambiar"): se reescribió con lo de ahora. La pestaña se llamaba "Proyectos" y ahora dice
Tableros, aclarando que lo que describe es la vista Lista.

**Falta.** Secciones nuevas, con el tono del resto de la guía:

- **Tablero**: columnas y sus marcas (📥 Entrada, ✓ Terminada), crear y mover tarjetas
  (arrastrar en computadora, "Mover a…" en el teléfono), filtros.
- **Detalle de la tarjeta**: proyecto, etiquetas, checklist, comentarios, historial de
  tiempo.
- **⚙ Organizar**: tableros, columnas (y por qué una columna con tareas no se borra),
  proyectos, etiquetas, Configurar pomodoro.
- **Reportes**: rangos, qué cuenta cada gráfica (solo tiempo de trabajo, igual que las
  tarjetas) y Exportar CSV.

**Aceptación.** Cada pestaña y cada botón de la barra del tablero tiene su explicación
en la guía, y el índice de la guía enlaza las secciones nuevas.
