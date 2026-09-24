# Novedades

Qué trae cada versión de Habit Tracker, escrito para quien usa la app. El detalle técnico
está en el historial de git; cada versión tiene su tag (`v1.9.0`, `v1.10.0`…).

Formato: [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). Versionado:
[semver](https://semver.org/lang/es/), con el criterio de la sección *Versionado* de
`CLAUDE.md`.

## [1.14.0] — 2026-09-24

Corregir el cronómetro sin detenerlo, configurar tu pomodoro, editar checklist y
comentarios, y usar la app como una aplicación instalada.

### Nuevo
- **Ajustar el cronómetro en marcha**: toca ✎ en la barra y escribe cuánto llevas
  trabajando (horas, minutos y segundos); la hora de inicio se calcula sola y el
  cronómetro sigue corriendo. Ahí mismo puedes cambiar la tarea: todo el tiempo pasa a la
  nueva.
- **Tu pomodoro**: en Organizar › Configurar pomodoro eliges cuánto duran el enfoque y los
  descansos. Un pomodoro en marcha termina con la duración con la que empezó.
- **Editar el checklist y los comentarios** sin borrarlos: ✎ en cada uno. Los comentarios
  se pueden ocultar.
- **Instalable**: agrégala a la pantalla de inicio del teléfono o instálala en la
  computadora; se abre como una app, con su propio ícono.

### Cambios
- El cronómetro ya no te interrumpe: solo al llegar a 8 h se detiene y te pregunta cuánto
  trabajaste, con tu última actividad en la app como pista.
- Los colores de tus hábitos se guardan en tu cuenta y se ven igual en todos tus
  dispositivos. Los que tenías en este navegador se suben solos la primera vez.
- «Exportar CSV» es ahora un enlace pequeño bajo la fecha, en Reportes.
- Con la app abierta en varias pestañas, el reloj se mantiene igual en todas.

### Para actualizar
Esta versión añade columnas a la base de datos: correr `python3 scripts/migrate.py`
**antes** de reiniciar el servicio. Si se olvida, el servicio no arranca y el log dice qué
falta. Si vienes de la 1.12.0, incluye también todo lo de la 1.13.0.

## [1.13.0] — 2026-09-23

Ver de dónde sale el tiempo de cada día, corregirlo y exportarlo, y un cronómetro olvidado
ya no suma horas que no trabajaste.

### Nuevo
- **Tiempo registrado del día**: toca «Hoy» en la barra del tablero y ves cada registro
  del día, de todas las tareas, en orden: tarea, proyecto, horario y duración. Edítalo (✎)
  o bórralo (×) ahí mismo.
  - Muévete entre días con ‹ ›, o toca la fecha para elegir cualquier día en un
    calendario.
  - Los cronómetros que se cerraron solos a las 8 h salen marcados con ⚠ para corregirlos
    rápido.
- **Exportar a CSV** desde Reportes: los registros del periodo elegido, uno por fila
  (fecha, horario, duración, tarea, proyecto, etiquetas, origen y nota), listos para Excel
  o Google Sheets.
- **Cronómetro olvidado**: si lleva 2 h corriendo sin que toques la app, te pregunta si
  seguiste trabajando y te ofrece guardar solo hasta tu última actividad. Si estás usando
  la app, no pregunta.

### Cambios
- Un cronómetro que llega a las 8 h mientras no estás ya no se cierra solo con 8 h:
  primero te pregunta.
- Al corregir la duración de un cronómetro que se cerró solo, se quita su nota automática.

### Correcciones
- Los registros de un proyecto archivado no se podían editar.

### Para actualizar
Sin migraciones: basta con actualizar el código y reiniciar el servicio.

## [1.12.0] — 2026-09-23

Nueva pestaña **Reportes** para ver en qué se fue tu tiempo y cómo van tus hábitos, y el
historial de tiempo de cada tarea.

### Nuevo
- **Reportes**, la tercera pestaña: elige Semana (de lunes a domingo), Mes o un rango
  propio, y muévete al periodo anterior o siguiente con las flechas.
  - **Resumen**: tiempo total, promedio por día, días con tiempo y tareas terminadas,
    comparado con el periodo anterior.
  - **Hábitos**: tu racha y tu récord, y cuántos días hiciste cada hábito ("18 de 20
    días"). Los días de descanso no cuentan como días que tocaban.
  - **Tiempo por día**, con los días de descanso marcados.
  - **Por proyecto** y **por etiqueta**. Toca varias etiquetas para ver su total juntas
    sin contar doble.
  - **Tareas terminadas** en el periodo, con su proyecto y su tiempo.
  - **¿A qué hora rindes más?**: un mapa por día y hora con tu mejor franja.
  - **Cómo se registró**: cuánto fue pomodoro, cronómetro o a mano.
- **Historial de tiempo en cada tarjeta**: cada registro con su origen, fecha, horario y
  nota. Edítalo (✎) o bórralo (×) sin salir de la tarjeta.
- La app **vuelve a la última pestaña** que usaste al recargar.

### Cambios
- "Registrar a mano" se abre encima de la tarjeta en vez de cerrarla.

### Correcciones
- Al detener el tiempo desde una tarjeta abierta, su total no cambiaba hasta cerrarla.
- Con la app abierta en dos pestañas, un pomodoro que terminaba se guardaba dos veces.
- Una sesión sin conexión que se encolaba mientras se reenviaban otras podía perderse.
- Las pestañas cortas quedaban con mucho espacio en blanco debajo después de ver una
  más larga.

### Para actualizar
Sin migraciones: basta con actualizar el código y reiniciar el servicio.

## [1.11.0] — 2026-09-23

Ordenar el tablero a tu gusto, y una tanda de arreglos y endurecimiento.

### Nuevo
- **Ordenar tarjetas arrastrando**: suelta una tarjeta en cualquier punto de una columna,
  la suya incluida; una línea marca dónde caerá y el orden se guarda. Las tarjetas nuevas
  y las que llegan de otra columna se ponen al final.
- **Ordenar columnas arrastrando** en Organizar, por el asa ⠿. En el teléfono siguen las
  flechas.

### Cambios
- Los datos de un hábito (nombre, emoji y color) se validan al guardarse: un nombre de
  más de 40 caracteres o un color que no sea hexadecimal se rechazan.
- La app solo acepta peticiones desde su propia página: se quitó una configuración que
  aceptaba cualquier sitio.
- La comprobación de estado para monitores pasa a `/api/health`, que sí responde en
  producción.

### Correcciones
- Las tarjetas de un proyecto archivado mostraban 0m aunque tuvieran tiempo registrado.

### Para actualizar
Sin migraciones: basta con actualizar el código y reiniciar el servicio. `passlib` ya no
está en `requirements.txt`; si queda instalado no estorba.

## [1.10.0] — 2026-09-22

La pestaña Proyectos se convierte en **Tableros**: un kanban donde cada tarjeta es una
tarea.

### Nuevo
- **Tableros kanban**: varios tableros ("Escuela", "Trabajo"…), cada uno con sus propias
  columnas. Las tarjetas se arrastran entre columnas en la computadora; en el teléfono se
  ve una columna a la vez y se mueven con "Mover a…". Al entrar sin tableros, la app te
  ofrece crear el primero.
- **Organizar (⚙)**: crear, renombrar, reordenar, archivar y borrar tableros y columnas.
  Una columna marcada "✓ Terminada" da la tarea por hecha; a la "📥 Entrada" llegan las
  nuevas.
- **Detalle de la tarjeta**: descripción, checklist, comentarios con autor y fecha,
  proyecto y etiquetas. Todo se guarda al escribir.
- **Etiquetas**: varias por tarea, bajo el título, para filtrar el tablero y saber en qué
  tipo de actividad se va tu tiempo. Al sumar varias, cada sesión cuenta una sola vez.
- **Tareas sin proyecto**: van a "Sin asignar", así ves qué tiempo te falta clasificar.
  Al darles proyecto, su tiempo se va con ellas.
- **Tiempo desde la tarjeta**: cronómetro, pomodoro o registro a mano. Mientras corre, la
  tarjeta muestra el reloj en vivo y ■ para detenerlo; al terminar un pomodoro se ofrece
  el descanso.
- Crear proyectos desde el tablero (en la tarjeta o en Organizar) y ver y restaurar los
  archivados.
- **Hábitos**: emoji propio elegido de un panel, y una lista de hábitos archivados para
  restaurarlos o borrarlos del todo.

### Cambios
- Borrar un proyecto ya no borra sus tareas ni su tiempo: pasan a "Sin asignar", salvo que
  marques "Borrar también su tiempo registrado".
- Menú pequeño ⋯ en cada proyecto (Archivar / Eliminar…) en vez de una ventana grande.
- La tarjeta grande del reloj desaparece: el tiempo se controla desde la barra inferior, y
  "Hoy" y el sonido pasan junto al selector de tablero.
- El cronómetro aparece primero entre los modos, y detener antes de un minuto ya no pide
  confirmación.

### Correcciones
- Una tarea terminada de noche quedaba con la fecha del día siguiente.
- Cerrar sesión con el reloj corriendo perdía ese tiempo.
- Editar un registro de tiempo de una tarea terminada le quitaba la tarea.
- Los modales largos se podían salir de la pantalla; "Guardar Hábitos" queda siempre a la
  vista.
- El emoji de un hábito salía dos veces.

### Para actualizar
Esta versión añade columnas a la base de datos: correr `python3 scripts/migrate.py`
**antes** de reiniciar el servicio. Si se olvida, el servicio no arranca y el log dice qué
falta. Al primer acceso, tus tareas aparecen en "Mi tablero": las terminadas en *Hecho* y
las pendientes en *Por hacer*.

## [1.9.0] — 2026-09-17

### Nuevo
- **Cronómetro**: además del pomodoro, un modo que cuenta hacia arriba hasta que lo detienes.
- Arrancar el cronómetro directamente desde una tarea, con ▶.

### Correcciones
- Las sesiones del cronómetro se guardan bien (el servidor las rechazaba, y una duración
  planeada de 0 se convertía en 25 minutos).

## [1.8.0] — 2026-09-15

### Nuevo
- Antes de guardar o descartar cambios en tus hábitos, la app te pregunta.

### Correcciones
- "Hoy" es tu día local, no el del servidor: por la noche ya no se contaba como mañana.
- La racha que ves es la que calcula el servidor, sin diferencias con el navegador.
- La app ya no hace peticiones antes de iniciar sesión.

## [1.7.0] — 2026-09-15

### Nuevo
- **Días de descanso semanales**: los días que elijas no rompen tu racha.

### Correcciones
- La racha se calcula con una regla de corte correcta.
- Archivar y borrar hábitos se guarda en el servidor (antes quedaba solo en el navegador).
- Borrar un hábito de un día se guarda de verdad.

## [1.6.0] — 2026-09-14

### Nuevo
- Confirmación antes de detener un pomodoro de enfoque a medias.
- Confirmación al salir de la edición del perfil con cambios sin guardar.

## [1.5.0] — 2026-09-08

### Nuevo
- **Registrar tiempo a mano**, con fecha y hora de inicio y fin, para lo que trabajaste sin
  el temporizador.
- Tiempo de cada tarea y registro de tiempo dentro de cada proyecto, con opción de
  corregir o borrar registros.

### Correcciones
- Un pomodoro terminado ya no cierra la sesión, y avisa aunque estés en otra pestaña.

## [1.4.0] — 2026-09-08

### Nuevo
- **Perfil**: alias, nombre y apellido opcionales, editables desde la barra de usuario.
- La cabecera muestra el nombre de la app y te saluda.

### Correcciones
- Al recargar la página se recupera tu sesión correctamente.
- La versión de la app se muestra también en producción.
- Los selectores del pomodoro se actualizan al cambiar proyectos o tareas.

## [1.3.0] — 2026-08-09

### Nuevo
- **Pomodoro** con registro de tiempo por proyecto.

## [1.2.0] — 2026-08-09

### Nuevo
- **Proyectos y tareas**, con pestañas y cambio de vista deslizando.

## [1.1.0] — 2026-08-09

### Nuevo
- **Modo oscuro**, que sigue al sistema o se elige a mano.

## [1.0.1] — 2026-08-09

### Cambios
- Base técnica para que los módulos nuevos se conecten a la app sin tocar el núcleo.

## [1.0.0] — 2026-08-09

Primera versión: hábitos con calendario mensual, rachas y estadísticas, guardados en tu
cuenta.

[1.14.0]: https://github.com/YoshiDev22/habit-tracker/tree/v1.14.0
[1.13.0]: https://github.com/YoshiDev22/habit-tracker/tree/v1.13.0
[1.12.0]: https://github.com/YoshiDev22/habit-tracker/tree/v1.12.0
[1.11.0]: https://github.com/YoshiDev22/habit-tracker/tree/v1.11.0
[1.10.0]: https://github.com/YoshiDev22/habit-tracker/tree/v1.10.0
[1.9.0]: https://github.com/YoshiDev22/habit-tracker/tree/v1.9.0
[1.8.0]: https://github.com/YoshiDev22/habit-tracker/tree/v1.8.0
[1.7.0]: https://github.com/YoshiDev22/habit-tracker/tree/v1.7.0
[1.6.0]: https://github.com/YoshiDev22/habit-tracker/tree/v1.6.0
[1.5.0]: https://github.com/YoshiDev22/habit-tracker/tree/v1.5.0
[1.4.0]: https://github.com/YoshiDev22/habit-tracker/tree/v1.4.0
[1.3.0]: https://github.com/YoshiDev22/habit-tracker/tree/v1.3.0
[1.2.0]: https://github.com/YoshiDev22/habit-tracker/tree/v1.2.0
[1.1.0]: https://github.com/YoshiDev22/habit-tracker/tree/v1.1.0
[1.0.1]: https://github.com/YoshiDev22/habit-tracker/tree/v1.0.1
[1.0.0]: https://github.com/YoshiDev22/habit-tracker/tree/v1.0.0
