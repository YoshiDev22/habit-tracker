# BACKLOG

Cola de trabajo de habit-tracker. Cada entrada tiene el síntoma, la causa con
`archivo:línea`, el arreglo propuesto y un criterio de aceptación verificable.

**Cómo usarlo:** elegir *una* entrada y trabajarla completa. No agrupar varias en un
commit. Al terminar, borrar la entrada de este archivo en el mismo commit que la arregla.

**Estado de verificación:** las entradas marcadas *reproducido* se ejecutaron contra el
server local y fallaron de forma observable. Las marcadas *diagnosticado* salen de leer el
código y no se reprodujeron todavía.

Levantado el 2026-09-08 sobre v1.3.0. Revisado el 2026-09-22 sobre v1.10.0 (tableros), el
2026-09-30 sobre v1.16.1 (entradas 5, 6 y 22 cerradas; 24, 25 y 26 nuevas) y el 2026-10-02
sobre v1.19.0 (Fases 1 a 4 de la 24 terminadas; 25 cerrada; 27, 28 y 29 nuevas) y el
2026-10-13 sobre v1.27.0 (orden 1.28–1.30; 40 en la tabla; 38 cerrada el 2026-10-14 y 39 el 2026-10-15, en la 1.28).

| # | Prioridad | Entrada | Estado |
|---|---|---|---|
| 14 | P4 | Pestañas añadidas por el usuario, a partir de plantillas | épica |
| 17 | P2 | Metas con hábitos y avance medible | épica, para la 1.29 |
| 21 | P4 | Tableros compartidos entre usuarios | épica |
| 23 | P4 | Escudo especial que se gana con hitos de racha | épica |
| 24 | P2 | Módulos por usuario y costeo de proyectos (freelance / maker) | épica |
| 26 | P2 | Correo de confirmación al registrarse y recuperación de cuenta | parte sin correo hecha |
| 27 | P3 | Reordenar las pestañas de secciones | pedido, para la 1.30 |
| 28 | P3 | Modo ordenar en el Tablero: reordenar y cambiar el ancho de las columnas | pedido, para la 1.30 |
| 29 | P3 | Periodo de la gráfica "Costos" en la pestaña Costos (mes, año o todo) | API hecha; selector para la 1.30 |
| 30 | P2 | Reportes automáticos (semanal y mensual) con IA opcional | épica |
| 31 | P3 | Límite diario de la IA ajustable por cuenta | en parte: IA extra por día desde el panel (1.27) |
| 32 | P2 | Panel de administración y "Reportar un problema" | en producción (1.27); paso 7 (gráficas) hecho para la 1.28 |
| 33 | P3 | Lugar donde se trabajó, y la duración de ciertos hábitos | tareas y tiempo: versión por decidir (no la 1.25); hábitos: tras la 17 |
| 36 | P3 | Página de inicio pública: qué es la app, video de uso, entrar y registrarse | idea |
| 37 | P2 | Finanzas personales: gastos del correo, Telegram y a mano, con avisos de ritmo | épica, después de la 1.27; fase 1 hecha en `feat/finanzas` |
| 40 | P3 | Recurrente con fecha de fin que no se ve terminado | por observar |
| 43 | P3 | Menús de la app más sencillos: un panel lateral como el de Finanzas | pedido |
| 49 | P3 | Comparar el modelo de IA de los reportes (GPT-OSS contra Haiku) | para después: se queda GPT-OSS |
| 50 | P2 | Grupos de proyectos | plan listo, para la 1.34.0 |

---

## 14 · P4 · Pestañas añadidas por el usuario, a partir de plantillas

**Esto no es una entrada, es una épica.** El resto del backlog se puede trabajar de una
sentada; esto no. Está aquí para que la idea no se pierda y para dejar escritas las
decisiones que hay que tomar antes de escribir código, no como algo que se empiece tal
cual. La pestaña fija de Reportes (1.12.0) ya enseñó cómo se añade una vista: empezar por
ahí (`VIEWS` y `watchActiveView()` en projects.js).

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

**Estado actual (revisado el 2026-10-01).** La navegación lee de un array, `VIEWS` en
projects.js, y cada vista se nombra por su id (`'calendar'`, `'projects'`, `'reports'`),
nunca por su posición. `setViewVisible()` oculta una vista entera y `goToView()` ajusta el
ancho del indicador a las que se ven: es lo que usa el interruptor de módulos (entrada 24).
Lo que falta:

- Cada vista sigue siendo un `<section>` escrito en `index.html`, y cada tab un `<button>`.

El siguiente paso es que tabs y secciones **se creen desde ese array**, cuando haya una
plantilla que lo pida.

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

**Aceptación (del primer paso, no de la épica).** Añadir una entrada a `VIEWS` crea
su tab, su vista y el ancho del indicador, sin tocar `index.html` ni `styles.css`; el
swipe, las flechas del teclado y `Home`/`End` ya funcionan así.

---

## 17 · P2 · Metas con hábitos y avance medible

**Esto es una épica.** Que los hábitos estén al servicio de **metas** con avance visible,
sin perder el registro diario que ya existe. Planteado el 2026-09-22; modelo acordado el
2026-09-23.

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
motiva con constancia (días marcados, racha). Los objetivos van en un lugar aparte: se
crean y editan desde el menú de configuración. El avance se expresa en días
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
el 2026-09-30.

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
- **Plan maker (2026-10-01)**: Costeo se presenta como plan maker, gratis pero solo para
  las cuentas con acceso (`scripts/grant_module.py`). Códigos de invitación, después.

**Fases** (cada una se despliega sola): 0 base sólida ✅ (lock, CI, sesiones
idempotentes, límite de login) · 1 interruptor de módulos + ficha de proyecto solo lectura ✅ (1.17.0) ·
2 tarifa y presupuesto ✅ (1.18.0) · 3 gastos y materiales, pegar de una hoja e importar CSV ✅ (1.19.0) · 4 estimado contra real
por tarea ✅ (1.19.0) · 5 cotizador con historial (rangos P50/P80) · 6 hoja de Google publicada como
CSV, solo lectura. Fuera de las fases: tipo de proyecto, precio y margen ✅ (1.22.0), reporte
mensual de costos ✅ (1.23.0), gastos repartidos entre proyectos y recurrentes ✅ (1.24.0).

**Esquema.** Tablas nuevas (`user_modules`, `project_finance`, `project_costs`), sin
migración. La única columna en una tabla existente es `tasks.estimate_minutes` (Fase 4):
**va en `scripts/migrate.py`**, y se avisa el impacto antes de escribirla.

**Orden.** Sigue la Fase 5 (cotizador). Las Fases 3 y 4 salen juntas en la 1.19.0: la 4
agrega `tasks.estimate_minutes`, así que su deploy corre `scripts/migrate.py` antes de
reiniciar.

**Aceptación de la Fase 4 (hecha, 2026-10-02).** Una tarea puede llevar un estimado en
minutos; su tarjeta muestra "2 h de 3 h", y la ficha y Costos dicen, por etiqueta, cuánto
se desvía el usuario de lo que estima (real ÷ estimado). Decisiones cerradas el 2026-10-01 (estimado para
todos y desvío solo con Maker, tope de 100 h, qué tareas cuentan, mínimo de 3): en
`docs/specs/modulos-y-costeo.md`, "Decisiones de la Fase 4".

---

## 26 · P2 · Correo de confirmación al registrarse y recuperación de cuenta

**Parte sin correo, hecha (2026-10-05):** cambiar la contraseña estando dentro y borrar la
cuenta, ya o a 30 días, con la opción de cerrar las otras sesiones (`users.token_version`,
que resolvió el punto 3 de abajo) — ver CLAUDE.md, *Cuenta*. **Falta lo que necesita correo**:
recuperar la contraseña, verificar el correo y un registro que no revele qué correos tienen
cuenta. Para eso sigue pendiente decidir el punto 1 (cómo se envían).

**Anotado el 2026-09-30.**

**Síntoma.**

- **Nadie puede recuperar su cuenta.** No hay "olvidé mi contraseña": si alguien la
  olvida, la única salida es cambiar `users.hashed_password` a mano en la base del VPS.
- **Tampoco se puede cambiar la contraseña** estando dentro: `PATCH /api/auth/me` solo
  toca el perfil (alias, nombre, días de descanso, duraciones).
- **El correo no se verifica.** Un error al escribirlo deja la cuenta sin forma de
  recuperarse, y cualquiera puede registrar el correo de otra persona y ocupárselo.
- El registro responde "El email ya está registrado", así que deja saber qué correos
  tienen cuenta.

**Lo que obliga a decidir.**

1. **Cómo se envían los correos.** Con un servicio transaccional por SMTP (el VPS no
   debe mandarlos directo: sin SPF, DKIM y DMARC en `yoshidev22.com` caerían en spam).
   `smtplib` es de la biblioteca estándar, así que no hace falta dependencia nueva. Las
   credenciales van en `backend/.env`, nunca en el repo.
2. **Cuentas sin verificar**: ¿pueden usar la app mientras tanto (con un aviso), o no
   entran hasta confirmar? ¿Y las cuentas que ya existen: se dan por verificadas o se les
   pide confirmar al entrar?
3. **Sesiones abiertas tras un cambio de contraseña.** El JWT dura 7 días y no se puede
   revocar: quien robó una sesión la conserva aunque se cambie la contraseña. Arreglarlo
   pide una columna (`users.password_changed_at` o `token_version`) que
   `get_current_user` compare con el token. **Toca la autenticación**: avisar el impacto.
4. **Registro sin revelar cuentas**: con verificación, el registro puede responder siempre
   igual ("te enviamos un correo") y, si el correo ya tenía cuenta, avisarle al dueño en
   vez de decirlo en pantalla.

**Propuesta de diseño (para revisar, no decidida).**

- Tabla nueva `email_tokens` (`user_id`, `purpose` verify | reset, `token_hash`,
  `expires_at`, `used_at`), que `create_all()` crea sola. El token es aleatorio
  (`secrets.token_urlsafe(32)`), **se guarda solo su hash**, sirve una vez y caduca
  (verificar: 48 h; recuperar: 1 h).
- `users.email_verified_at` como columna nueva → **va en `scripts/migrate.py`**.
- Endpoints: `POST /api/auth/verify-email`, `POST /api/auth/forgot-password` (responde
  siempre lo mismo, exista o no la cuenta), `POST /api/auth/reset-password` (token +
  contraseña nueva; invalida los demás tokens) y un cambio de contraseña con la actual.
- Límite de intentos con `backend/ratelimit.py`: por IP y por correo, para que no sirva
  para mandar correos en masa a un tercero.
- El enlace abre la app con el token en la URL (`/?reset=...`). La app lo quita de la
  barra con `history.replaceState` en cuanto lo lee, y la página manda
  `Referrer-Policy: no-referrer`, para que el token no se filtre a otros sitios.

**Orden.** Antes de abrir el registro a más gente o de anunciar los módulos (entrada 24).
Mientras tanto, `ALLOW_REGISTRATION=false` permite cerrarlo.

**Aceptación.** Alguien que olvidó su contraseña la recupera sin intervención del administrador;
un correo mal escrito no deja una cuenta usable a nombre de otro; pedir recuperación con
un correo sin cuenta responde lo mismo que con uno que sí tiene.

---

## 27 · P3 · Reordenar las pestañas de secciones

**Pedido el 2026-10-01.** Que cada usuario pueda ordenar las pestañas
(Calendario, Tableros, Costos, Reportes) a su gusto.

**Cómo encaja.** La navegación ya nombra las vistas por id (`VIEWS` en projects.js) y la
posición sale de las que se ven. Falta: guardar el orden en la cuenta (una columna o tabla
nueva: avisar el impacto antes), reordenar `VIEWS` **y** las secciones del track al
aplicarlo (el track se desplaza por el orden del DOM, ver CLAUDE.md), y la UI para
arrastrar (con flechas en táctil, como Organizar). Ojo con `LEGACY_VIEW_IDS` y con las
pruebas que comparan `currentViewIndex` con números fijos.

**Aceptación.** El orden elegido se ve igual en todos los dispositivos de la cuenta, y el
swipe y el teclado lo siguen.

---

## 28 · P3 · Modo ordenar en el Tablero: reordenar y cambiar el ancho de las columnas

**Pedido el 2026-10-01.** En el Tablero, un **modo ordenar** (un botón que se
activa y desactiva) en el que se puedan reordenar las columnas arrastrándolas y cambiarles
el ancho (resize). Solo en ese modo, para no mover ni estirar nada por accidente.

**Cómo encaja.** Reordenar columnas ya existe en Organizar (asa ⠿ y flechas); este modo lo
lleva al tablero mismo. El ancho es nuevo: `board_columns.width` sería una columna en una
tabla existente → **va en `scripts/migrate.py`** (o guardarlo por dispositivo en
localStorage, más barato; decidir). En pantalla angosta (< 700 px) se ve una columna a la
vez: ahí el ancho no aplica.

**Aceptación.** Fuera del modo ordenar el tablero se comporta igual que hoy; dentro, las
columnas se arrastran y se estiran, y el resultado se conserva al recargar.

---

## 29 · P3 · Periodo de la gráfica "Costos" en la pestaña Costos

**Decisión pendiente (2026-10-01).** La gráfica de la pestaña Costos (mano de
obra y gasto por categoría) y el resumen suman **todo, desde siempre**. ¿Debería ser por
mes, por año, o con un selector (Mes / Año / Todo, como el rango de Reportes)?

**Lo que implica.** `GET /api/costs/summary` aceptaría `date_from`/`date_to` (fechas
locales: `cost_date` de los gastos y `session_date` del tiempo). El margen de un proyecto
compara con su presupuesto total, así que en un periodo parcial habría que decidir si se
muestra o se oculta.

**Avance (1.23).** La API ya acepta `date_from`/`date_to` (`costs_summary()` en
`backend/costing.py`) y el reporte mensual de costos la usa: el mes para horas y gastos, lo
acumulado al cierre para presupuesto disponible y margen. Falta decidir el selector de la
pestaña.

---

## 30 · P2 · Reportes automáticos (semanal y mensual) con IA opcional

**Esto es una épica.** Plan, decisiones, fases y esquema en
[docs/specs/reportes-ia.md](docs/specs/reportes-ia.md). Decidido el 2026-10-03, a
partir de un brief que no está en el repo (los ejemplos traen datos personales).

**Idea.** Que la app genere y guarde sola los reportes que hoy arma Claude a partir del
CSV: cifras por código, texto opcional por IA (Cloudflare Workers AI, Gemini, OpenAI o un
modelo local, a elegir por usuario, con una sola función de llamada), PDF desde el
navegador.

**Fases.** 1 export de hábitos ✅ · 2 sesiones por confirmar (`needs_review`, con
migración) ✅ · 3 capa de métricas con huso horario y festivos ✅ · 4 reportes guardados sin IA
(systemd timer) ✅ · 5 IA para el texto ✅ · 6 tipo de proyecto y precio ✅ (1.22.0) y reporte de
costos del mes ✅ (1.23.0). También en la 1.23.0: reportes de hábitos y contadores de IA
separados. Lo que queda de la épica es la entrada 31 (límite de IA por cuenta).

**Aceptación (de la Fase 4, no de la épica).** Un botón genera el reporte de la semana o
del mes y lo guarda; también se genera solo (systemd timer: lunes, la semana anterior, y día 1); la vista lo
muestra con las secciones de los ejemplos y se imprime a PDF desde el navegador.

## 31 · P3 · Límite diario de la IA ajustable por cuenta

**Estado (2026-10-08).** Ya hay un contador por cuenta (10 textos al día para tiempo y
hábitos, otros 10 para costos, desde la 1.23): nadie gasta el de otro. Lo que falta es que
el **tope** sea distinto por cuenta. Se hace con el panel de administración (entrada 32,
fase 2: "más textos de IA para una cuenta"), así que se trabaja ahí, no aparte.

**Idea.** Hoy el límite de textos con IA es uno para toda la instancia (`AI_DAILY_LIMIT` en
`backend/.env`, 10 por defecto, día UTC) y cada cuenta ve "te quedan N de 10" en el
reporte. Pedido el 2026-10-03: dejarlo en 10 por ahora, pero poder cambiarlo por
cuenta (más para quien lo use mucho, menos para una cuenta de prueba).

**Cómo podría ser.** Una columna `daily_limit` (NULL = el de la instancia) en
`user_modules` para el módulo `ai`, que `grant_module.py` ponga con `--limit N`
(**migración**: columna en tabla existente). `calls_today()` y `/api/reports/ai-usage` ya
cuentan por cuenta; solo cambia de dónde sale el tope. Quizá también contar el día en el
huso del usuario y no en UTC.

**Aceptación.** `grant_module.py --email … --module ai --limit 20` cambia el tope de esa
cuenta, el reporte lo dice, y sin `--limit` sigue el de `AI_DAILY_LIMIT`.

---

## 32 · P2 · Panel de administración y "Reportar un problema"

**Esto es una épica.** Pedida el 2026-10-07; va después de la 1.24 (gastos
recurrentes y repartidos). El plan completo está en
[`docs/specs/panel-admin.md`](docs/specs/panel-admin.md).

**Idea.** Un panel para gestionar y monitorear la app sin entrar al VPS: cuentas, última
actividad, módulos, uso de la IA y los problemas que reporten los usuarios desde un
"Reportar un problema" en *Mi perfil*. **Gestión, no vigilancia:** nunca enseña lo que
escribe cada persona.

**Decisiones.** En este repo, pero como un segundo proceso (`backend/admin_main.py`) que
escucha solo en `127.0.0.1` y al que se llega por un Cloudflare Tunnel con Cloudflare
Access; la app pública no monta sus rutas. La app valida además el JWT de Access y una
lista de correos en `.env`.

**Fases.** 1: "Reportar un problema" y el panel de solo lectura. 2: acciones (módulos, más
textos de IA, desactivar cuentas, estado de los problemas, publicar y terminar avisos
para todas las cuentas —hoy `scripts/announce.py`, desde la 1.26—) con bitácora. 3: tunnel y Access
(a mano, con una guía). El panel no se despliega antes de la fase 3.

**Aceptación.** Las de cada fase en el spec; en todas, que el dominio público no tenga
rutas de admin y que ninguna respuesta del panel traiga contenido de usuario.

---

## 33 · P3 · Lugar donde se trabajó, y la duración de ciertos hábitos

**Pedido el 2026-10-08**, como cambio menor para después de la 1.24.

**Idea.** Poder decir **dónde** se hizo cada tiempo registrado: Escuela, Oficina, Casa,
Lugar público u Otro (la lista se puede editar, como las categorías de gastos). Para qué:

- Ver dónde trabaja más la persona, y cuánto tiempo pasa en casa contra fuera.
- Ver si trabaja fuera de su horario habitual y en qué lugar (p. ej. trabajo de oficina que
  se lleva a casa de noche): ayuda a no sobresaturarse y a separar el trabajo de la vida
  personal.
- Separar los lugares en Reportes (tiempo por lugar, como por proyecto o etiqueta) y en los
  reportes guardados, con su texto.

**Y en los hábitos**, una duración y un lugar por defecto para los que se miden en tiempo:
capoeira suele ser 2 h (lo que dura la clase), gym 1 h, ejercicio fuera de casa. Al marcar
el hábito, la app podría registrar ese tiempo sola. Con las metas (épica 17) eso daría
"tiempo de ejercicio" automático hacia una meta como bajar de peso, y permitiría también un
ejercicio más libre: 30 min de cuerda en series (7 de 2 min con 1 min de descanso), quizá
con un timer de intervalos.

**Cómo podría ser.** Una tabla nueva de lugares por cuenta (con los cinco de inicio, como
las categorías de gastos); el lugar en la sesión (`pomodoro_sessions.place_id`, columna en
tabla existente: **migración**), con uno por defecto en la tarea o en el tablero para no
tener que elegirlo cada vez. En los hábitos, `habits.default_minutes` y `habits.place_id`
(**migración**). El cruce lugar × hora sale de la capa de métricas (`backend/metrics.py`),
que ya tiene las horas locales de cada sesión.

**Decidido el 2026-10-08, para tareas y tiempo: tres niveles, gana el más
específico.**

1. **Tablero**: el lugar por defecto ("Mi tablero" → Escuela).
2. **Tarea** (opcional): para lo que siempre se hace en otro lado (→ Casa). Sin nada, usa el
   del tablero.
3. **Cada registro de tiempo**: al arrancar el cronómetro, la barra enseña **📍 Escuela** (el
   que le toca) y un toque lo cambia **solo para ese registro**; igual al registrar a mano y
   al corregir un registro del historial.

Así una tarea hecha parte en la escuela y parte en casa queda bien (cada registro guarda su
lugar), y las actividades de casa se marcan una vez en su tarea. El lugar se **guarda en el
registro al hacerlo**: mover la tarea o cambiar el lugar del tablero después no cambia el
historial. Migración: `boards.place_id`,
`tasks.place_id` y `pomodoro_sessions.place_id` (columnas en tablas existentes) y la tabla
nueva de lugares. Reportes: tiempo por lugar y cruce lugar × hora (fuera del horario
habitual en casa, por ejemplo).

**Los hábitos, después de la épica 17**: duración y lugar por defecto de un hábito, y si
marcar uno registra tiempo solo o se pregunta, se deciden con los objetivos. No cambia lo de
las tareas.

**Por decidir.** En qué versión sale la parte de tareas y tiempo (no en la 1.25, que queda sin
migración: decidido el 2026-10-08).

---

## 36 · P3 · Página de inicio pública: qué es la app, video de uso, entrar y registrarse

**Idea del 2026-10-08.** Hoy quien abre la app sin sesión ve solo el formulario de
entrar. Una página de inicio (como la de cualquier app) explicaría qué hace y
serviría a los primeros usuarios que invite: no es un producto a la venta, así que **sin
precios, blog ni planes**.

**Qué traería.** Qué es y para quién (hábitos, tableros con tiempo, reportes, costeo para
freelance), capturas o un **video de uso** (ya hay uno de la 1.14; se grabarían otros más
actuales), por qué la racha funciona así (las fuentes de `docs/referencias.md`), y los
botones **Entrar** y **Crear cuenta** (este último solo si `ALLOW_REGISTRATION`).

**Cómo podría ser.** Sin otro sitio: la app ya sirve `index.html`; sin sesión, en lugar del
formulario solo, una portada con el formulario a un clic (o `/` portada y la app en `/app`).
El video, alojado fuera (YouTube o similar) o un archivo servido con ruta propia; sin
cookies de terceros si se puede. Lo que hoy explica `GUIA-DE-USO.md` sirve de base.

**Por decidir.** Si la portada vive en la misma app o en un sitio estático aparte; dónde se
aloja el video; y si se enlaza la guía de uso.

---

## 37 · P2 · Finanzas personales: gastos del correo, Telegram y a mano, con avisos de ritmo

**Esto es una épica.** Pedida el 2026-10-09; va **después de la 1.27** (panel de
administración). El plan completo está en [`docs/specs/finanzas.md`](docs/specs/finanzas.md).

**Idea.** Llevar las finanzas personales sin capturar todo a mano: las compras con tarjeta
entran solas de los correos del banco (y de las facturas CFDI), el efectivo se agrega por
Telegram o en la app, la campanita pregunta cada noche "¿te faltó algo?" y avisa si al ritmo
que se va el dinero no alcanza hasta el siguiente ingreso. Un reporte mensual da estrategias
sacadas de los propios datos.

**Decisiones.** Un módulo de esta app (`finance`, con acceso como `maker`), no otra app ni
parte de Costos. Solo tablas nuevas: sin migración. El correo lo lee un Apps Script en el
Gmail del usuario que manda los avisos a la app con un token de ingesta (la app nunca entra
al Gmail); el bot de Telegram es su propio servicio. La compra con crédito es el gasto; el
pago de la tarjeta, una transferencia.

**Fases.** 1: módulo y registro a mano. 2: avisos y ritmo. 3: correo y CFDI. 4: Telegram
(texto; fotos con IA después). 5: reporte mensual con IA.

**Aceptación.** Las de cada fase en el spec; en todas, que una compra con tarjeta cuente una
sola vez aunque llegue por varios caminos.

**Estado.** Fase 1 (módulo y registro a mano) hecha en la rama `feat/finanzas`, sin
publicar: va después de la 1.27.

**Por decidir.** Los bancos del primer parser y lo demás que lista el spec (el periodo ya no:
la app le pregunta a cada usuario si cobra por quincena o por mes).

---

## 40 · P3 · Recurrente con fecha de fin que no se ve terminado

**Visto por usuario el 2026-10-08**, por observar: al editar un gasto recurrente y ponerle
fecha de fin (primer cobro 17/07/26, fin 17/08/26), no lo vio marcado como terminado.

**Reproducido el 2026-10-13 con la API**, sin el síntoma: tras poner el fin, `next_date` es
`None` y la lista dice "Terminado". Lo que sí pasaba: el cobro del 17 sep, anotado antes de
poner el fin, se quedaba y seguía sumando (se corrige en la 1.27.1, preguntando al guardar
si se borran los cobros posteriores al fin).

**Siguiente paso.** Volver a probarlo y anotar qué se ve en la lista ("Siguiente: …"
o "Terminado") y en la hoja. Si no se repite, cerrar la entrada.

---

## 43 · P3 · Menús de la app más sencillos: un panel lateral como el de Finanzas

**Pedido el 2026-10-17.** Configuración (⚙️) y el menú de la inicial reparten lo de la cuenta en
dos lugares, con modales de desglose largos. En la página de Finanzas la inicial de la cuenta abre un panel lateral
(`#finDrawer`, `finance-data.js`): la inicial y el nombre arriba, y una lista corta de entradas
(Configuración, Datos, Aviso de privacidad, Regresar), cada una a su pantalla. Se probó primero ahí
para no tocar la app.

**Idea.** Que la inicial (o el ⚙️) de la app abra un panel así: Mi perfil, Configuración, Datos
(*Descargar mis datos*, exportar), Novedades, Reportar un problema, Aviso de privacidad y Cerrar
sesión, y que las páginas de Configuración y Mi perfil se queden como están detrás de cada entrada.

**Por decidir.** Si la campanita y el tema siguen sueltos arriba; si el panel reemplaza el menú de
la inicial (1.29) o lo extiende; y qué pasa con el ⚙️ de la app, que hoy es de Hábitos.

## 44 · P3 · Un número de versión propio para el panel de administración

**Pedido el 2026-10-18.** Finanzas ya lleva su número (`FINANCE_VERSION`, sus Novedades y sus tags
`finanzas-vX.Y.Z`; CLAUDE.md › Versionado). El panel de administración es otro proceso
(`backend/admin_main.py`) con sus propias páginas, y hoy sus cambios mueven la versión de Habit Tracker.

**Idea.** Hacer con el panel lo mismo que con Finanzas, para cuando se trabaje solo en él: `ADMIN_VERSION`,
`CHANGELOG-ADMIN.md` y tags `admin-vX.Y.Z`; el panel enseña su número, y un cambio solo del panel no mueve
`VERSION`. No necesita Novedades (no lo ven los usuarios).

**Por decidir.** Con qué número empieza (lo publicado hasta hoy salió dentro de Habit Tracker 1.27.0 a 1.28.0)
y si su `ExecStart` se reinicia aparte en un deploy que solo toca el panel.


## 45 · P2 · Finanzas: avisar cuando se acerca el pago de una tarjeta (Finanzas 0.8)

**Pedido el 2026-10-19.** Que la tarjeta lo diga cuando la fecha límite de pago esté cerca y aún quede algo por
pagar, y que la campana de Finanzas lo avise.

**Idea.** Con lo que ya calcula `card_statement()` (`due_date` y `remaining_cents`): en *Cuentas › Tarjetas*,
una línea en la tarjeta ("Vence en 3 días", "Vence hoy") y, en la campana, un aviso **pendiente** calculado de los
datos, como `missed_day` (`backend/notices.py`): se crea al pedir los avisos y queda `done` en cuanto lo que falta
pagar llega a cero, así que nunca dice algo que ya no es cierto. Se suma a `FIN_BELL_KINDS` y **no** sale en la
campana de Habit Tracker.

**Decidido (2026-10-19).** La tarjeta cambia a color de alerta y dice "Vence en 3 días" / "Vence mañana" /
"Vence hoy". En el panel lateral, *Configuración › Avisos* (página nueva, lista para otros avisos): con cuántos días
de anticipación (3 o 5; por defecto 5) y *Avisarme en la campana* (por defecto sí; apagada, solo el color). Se
guardan en **dos columnas nuevas de `fin_settings`** (NULL = por defecto), así que lleva **migración**
(`migrate.py` antes de reiniciar). La campana de Habit Tracker pide sus avisos sin el de Finanzas, y su conteo no lo
incluye. Se pensó para salir con la 46 (apartados y rendimientos, cerrada en Finanzas 0.6); el 2026-10-23 se
dejó para la siguiente versión, y el 2026-10-27 pasó a la 0.8 (con la 47). Lleva su propia migración.

**Decidido (2026-10-28):** no avisa el día de corte, solo el pago.

## 47 · P2 · Finanzas: tarjetas dadas de baja (Finanzas 0.8)

**Pedido el 2026-10-23.** Qué pasa con una tarjeta de crédito que se cancela en el banco. Hoy, con movimientos, solo
se archiva (`is_active = false`): sale de Cuentas y Tarjetas y de "Todas las cuentas", y se reactiva en
Configuración › Cuentas archivadas. Pero archivarla no dice nada de lo que quedó pendiente.

**Lo que hay hoy (revisado el 2026-10-27).** El servidor ya deja archivar una tarjeta con deuda y anotar pagos a una
cuenta archivada; el problema es de pantalla: archivada, su deuda desaparece de "Todas las cuentas" y de Tarjetas, y
no hay dónde pagarla.

**Decidido (2026-10-27).** Para cancelar una tarjeta, el banco pide que esté en cero. Así que **antes de archivarla, si
su saldo no es cero, la app pregunta qué hacer** en vez de archivarla así:
- **Con deuda:** cómo se pagó: desde otra cuenta (una transferencia a la tarjeta desde la que elija, en efectivo
  incluido) por lo que falta, y con eso queda en cero.
- **Con saldo a favor:** a dónde va: una transferencia de la tarjeta a la cuenta que elija.
- Con eso anotado (saldo en cero), se archiva.
- **La fecha de baja la pone el usuario (decidido 2026-10-28):** puede no abrir la app el día que la cancela, así que
  elige cuándo (hoy por defecto, o un día pasado), y el pago o el traspaso del saldo a favor llevan también su fecha.
- **MSI (decidido 2026-10-28):** una compra a meses ya cuenta completa en el saldo desde el día que se hace, y las
  mensualidades **nunca** son movimientos (solo se enseñan): en cero, la deuda de los MSI ya está pagada. Sus planes se
  dan por terminados y Movimientos deja de enseñar las mensualidades después de la fecha de baja, **sin tocar el
  saldo**. Prueba obligada: compra de 10k a 10 meses, 6k pagados, 4k transferidos después y la baja unos días más
  tarde: el saldo queda en 0, nada suma ni resta los 4 meses que el plan no llegó a pedir, y el resumen no cambia.
- **Fijos (decidido 2026-10-28):** si un fijo se cobra a esa tarjeta, la app recomienda pasarlo a otra cuenta (elige
  cuál) o **dejarlo para después**: se pausa (no se anota en una tarjeta cancelada), la tarjeta se archiva y en
  Configuración › Fijos queda marcado "su tarjeta se dio de baja" hasta cambiarle la cuenta, y la campana de Finanzas
  lo recuerda con un aviso **pendiente** calculado de los datos (como el del pago de la 45): sale mientras haya un fijo
  pausado en una cuenta dada de baja y se resuelve solo al cambiarle la cuenta (o borrarlo).
- **Cómo se ve (decidido 2026-10-28):** *Dada de baja el …*, con la fecha. Lleva una columna nueva en
  `fin_accounts`, que va en la migración de la 45. Su historial sigue en Movimientos y en los reportes.
- **Que no vuelva a usarse:** no sale al elegir cuenta en la hoja del monto ni al importar (ya pasa con las
  archivadas), pero sí en la lupa de Movimientos para filtrar su historial.

## 49 · P3 · Comparar el modelo de IA de los reportes (GPT-OSS contra Haiku)

**Decidido el 2026-10-26: se queda GPT-OSS 120B** (Workers AI, `@cf/openai/gpt-oss-120b`). Desde la 1.32 la IA
solo escribe los pasos y el tip, y con eso pasa el validador. La comparación queda para después, para no gastar
cuota de más.

**Cuando se retome.** Un script de una sola vez en el VPS (no va en el repo) pide a cada modelo los pasos y el tip
de reportes guardados reales, igual que la app, y enseña cuántas viñetas descarta `validate_suggestions()`. Haiku
va por AI Gateway con la llave guardada ahí (BYOK). A este volumen el precio no decide, sino la calidad.

**Si se cambia de modelo:** `AI_BASE_URL`, `AI_MODEL` y `AI_API_KEY` en `backend/.env`; `PRIVACY_AI` debe nombrar
al proveedor (y el cambio del aviso se anuncia con 📢); si el modelo rechaza `temperature`, hacerla opcional en
`backend/ai.py` con su prueba.

## 50 · P2 · Grupos de proyectos

**Plan en [docs/specs/grupos-de-proyectos.md](docs/specs/grupos-de-proyectos.md)** (2026-10-26). Un grupo es un
proyecto con hijos (`projects.parent_id`, con migración): un nivel, un solo grupo por proyecto, con tiempo y
gastos propios ("General") y el total sumado. Para la 1.34.0: base, Proyectos, Reportes y Costos. Para después:
repartir un gasto con el grupo como parte y por cantidad (sin inventario), y la idea de Costos como página propia
hacia el punto de equilibrio.

## 51 · P3 · Finanzas: la versión al pie del panel lateral (Finanzas 0.8)

**Pedido el 2026-10-27.** Al abrir el panel lateral (la inicial, arriba a la izquierda), la versión de Finanzas hasta
abajo y centrada, discreta ("Finanzas 0.7.0"), como la versión en el menú de la app. Sale de `GET /api/version`
(`finance_version`, que ya trae) o de la que se guardó al abrir la página (`finCheckUpdate()`). Solo en la página
principal del panel, no en sus páginas internas. Sin migración.

## 52 · P2 · Finanzas: Deudas en el Resumen y en Cuentas › Deudas (Finanzas 0.9)

**Pedido el 2026-10-28.** Una compra a meses cuenta completa como gasto el día que se hace, y el pago de una tarjeta es
una transferencia, que el Resumen nunca cuenta como gasto: así no se cuenta doble, pero en los meses siguientes las
gráficas no enseñan que se sigue pagando esa deuda. Ver cuánto se paga de deudas, **sin sumarlo a los gastos**.

**Decidido (2026-10-28).**
- **Resumen › *Deudas* del periodo**, en un apartado propio: *Pagos a tarjetas* (las transferencias que llegaron a una
  tarjeta de crédito en el periodo, por tarjeta) y *Mensualidades de MSI* (las que pedían los cortes del periodo, de
  `installment_bills()`), con la nota "No se suma a tus gastos: la compra ya se contó el día que la hiciste". Nunca
  entra al total de gastos ni a las categorías.
- **Cuentas › Deudas** (hoy "Próximamente"): cada tarjeta con lo que debe, lo que paga al mes de MSI y hasta cuándo
  (el último corte de sus planes), y el total de lo que queda. Es el arranque de la sección Deudas.
- Descartado por ahora: repartir las compras a meses mes a mes dentro de los gastos (cambiaría los totales según un
  interruptor y confunde).

- **Tipos de deuda:** al crear una se elige el tipo (tarjeta de crédito, préstamo personal, préstamo de una persona
  conocida, crédito bancario, hipotecario, otro). El tipo cambia el icono y lo que pide: una tarjeta, corte y pago; un
  préstamo, mensualidad, plazo y, si cobra, su tasa.

**Préstamos: cuándo un pago es gasto (decidido 2026-10-28).** Un préstamo es una cuenta de deuda con lo que se debe
como saldo inicial (como la deuda inicial de una tarjeta), que no es un gasto. Al crearlo, la app pregunta si **lo que
se pagó con él ya está anotado como gasto**:
- **Ya está anotado** (como una compra con tarjeta): sus pagos son transferencias que solo bajan la deuda.
- **No está anotado** (por ejemplo, algo comprado antes de usar la app): se elige la **categoría de sus pagos**, y cada
  pago cuenta como gasto en esa categoría **y** baja la deuda, en un solo movimiento (se cuenta una vez). Así el gasto
  sale mes a mes donde corresponde, y la deuda en Deudas.
- Con tasa, la parte de interés de cada pago es gasto (categoría *Intereses*) y el resto baja la deuda.
- Prueba obligada: en ningún caso un mismo peso cuenta dos veces entre gastos, saldo de la deuda y Resumen › Deudas.

**Exportar (propuesta).** En *Datos › Exportar*, un CSV de deudas: cada una con lo que queda y sus pagos con fecha. El
CSV de movimientos ya trae cada pago. El apartado del Resumen entraría en un reporte de Finanzas cuando lo haya.

**Compartir una deuda (decidido 2026-10-28), en dos pasos:**
1. *Compartir* en la deuda arma un resumen para mandar (texto o PDF): lo pagado, lo que falta, cuántos pagos van y el
   último. No abre acceso a nadie: quien lo usa decide qué manda y cuándo.
2. Después, si hace falta, un enlace de solo lectura de **esa** deuda (nada más de la cuenta), que se puede apagar y
   caduca. Cambia el aviso de privacidad (lo de una cuenta queda a la vista de otra persona): va con su 📢.
