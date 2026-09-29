# Novedades

Qué trae cada versión de Habit Tracker, escrito para quien usa la app. El detalle técnico
está en el historial de git; cada versión tiene su tag (`v1.9.0`, `v1.10.0`…).

Formato: [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). Versionado:
[semver](https://semver.org/lang/es/), con el criterio de la sección *Versionado* de
`CLAUDE.md`.

## [1.16.1] — 2026-09-29

Letra un poco más grande cuando la pides.

### Cambios
- **Tamaño del texto**: Grande y Muy grande crecen un poco más (19 y 22 px, antes 18 y 20),
  para que la diferencia se note en el teléfono. Se cambia en Mi perfil › En este
  dispositivo.

### Si la app se ve diminuta en el teléfono
Revisa que el navegador no esté en modo **"Sitio para ordenador"** (o "Versión de
escritorio"): en ese modo el teléfono dibuja la app como si fuera una computadora y todo se
ve pequeño. En Chrome: menú ⋮ → desmarca "Sitio para ordenador".

### Para actualizar
Sin cambios en la base de datos: basta con reiniciar el servicio.

## [1.16.0] — 2026-09-29

Un calendario nuevo que se entiende de un vistazo, vacaciones que no rompen tu racha, y tus
hábitos ocultos siguen en su lugar.

### Nuevo
- **Franja de racha** arriba del calendario: `🔥 racha · 🛡️🛡️ escudos · récord`. Tu racha,
  tus dos escudos (el gastado se ve vacío, con los días que faltan para recargarlo) y tu
  racha más larga.
- **Leyenda bajo el calendario** ("Este mes · días hechos"): qué hábito es cada punto, en el
  mismo orden, con los días que lo hiciste este mes y su racha propia (🔥) si la tiene.
- **Vacaciones**: en ⚙️, bajo los días de descanso, programa una pausa de hasta 30 días,
  desde hoy o más adelante. Mientras dura, los días sin hábitos no cortan tu racha ni
  gastan escudos; si marcas algo, cuenta normal. Se ven rayados en el calendario. Una en
  curso se puede terminar antes y una que no ha empezado, cancelar.
- **Panel del día renovado**: cada hábito con un círculo de su color (vacío si no lo
  hiciste, relleno si sí), cuántos llevas ("2 de 3 hoy") y, si el día no cuenta como
  fallado, por qué: descanso, escudo o vacaciones.
- **Borrar un hábito te dice qué cuesta**: cuántos registros se pierden y cuánto bajarían
  tu racha y tu récord, antes de confirmar.

### Cambios
- **Tus hábitos ocultos no desaparecen del pasado**: en los meses donde los hiciste siguen
  en su lugar (atenuados en la leyenda y en el panel), y esos días siguen contando para tu
  racha. Antes se borraban de todos los meses y los demás se corrían de lugar.
- Un hábito nuevo va siempre al final: ya no mueve el lugar de los demás.
- Al añadir un hábito, viene con un color que ningún otro usa. Puedes repetir uno: la app
  avisa, pero lo guarda.
- Los días que aún no llegan tienen los puntos casi transparentes, y un día cubierto por un
  escudo ya no se ve igual que uno de descanso.
- Hasta 5 hábitos, los puntos de cada día van en una fila; con más, en dos.
- La barra del mes lleva la etiqueta "MES" y cuenta los mismos hábitos que los puntos.
- La tarjeta "Métricas" se quitó: lo que mostraba ahora está en la franja y en la leyenda.
- Reportes no cuenta los días de vacaciones entre los que tocaban.

### Correcciones
- En el teléfono, el día "Dom" de los días de descanso se salía de la pantalla en ⚙️.

### Para actualizar
Esta versión crea una tabla nueva (las pausas por vacaciones), que la app crea sola al
arrancar: no hace falta `migrate.py`, basta con reiniciar el servicio.

## [1.15.1] — 2026-09-28

Corrección importante: marcar un hábito podía borrar registros de otros.

### Correcciones
- Si un día tenía marcado un hábito que después ocultaste, y desmarcabas en ese día tu
  último hábito visible, se perdía también el registro del hábito oculto. Ahora marcar o
  desmarcar cambia solo ese hábito en ese día.
- Con la app abierta en dos dispositivos, marcar un hábito en uno podía borrar lo que
  habías marcado ese mismo día en el otro. Ya no pasa.

### Para actualizar
Sin cambios en la base de datos: basta con reiniciar el servicio. Los registros que ya se
hubieran perdido no se pueden recuperar.

## [1.15.0] — 2026-09-28

Un día suelto ya no te borra la racha, la app te pregunta si olvidaste anotar ayer, y
puedes agrandar el texto.

### Nuevo
- **Protectores de racha 🛡️**: cada 7 días de racha ganas un protector (puedes guardar
  hasta 2). Si un día no anotas ningún hábito y no es de descanso, se usa uno solo y la
  racha sigue. En Métricas, junto a tu racha, están tus dos escudos: el que gastaste se ve
  vacío, con los días que faltan para recargarlo. En el calendario, los días que cubrió
  uno llevan 🛡️.
- **«¿Olvidaste anotar ayer?»**: si ayer quedó vacío y tenías racha, al abrir la app te lo
  pregunta con tus hábitos para marcarlos. Si sí lo hiciste, lo anotas ahí y recuperas la
  racha (o el protector que se había gastado). Los días de descanso no cuentan, y cada día
  se pregunta una sola vez.
- **Tamaño del texto**: en Mi perfil (toca tu nombre) › En este dispositivo, elige Normal,
  Grande o Muy grande. Se aplica al momento y se queda en ese dispositivo, también en la
  app instalada.

### Cambios
- Tu récord de racha se calcula con los protectores, así que puede subir si en el pasado
  un solo día suelto la cortó.
- Reportes muestra cuántos protectores tienes, junto al récord.

### Correcciones
- En una tablet o con el teléfono acostado, deslizar sobre las columnas del tablero
  cambiaba a Reportes en vez de mostrar las demás columnas. Ahora las desplaza; desde la
  última columna, deslizar sí cambia de pestaña.
- En Reportes, elegir Semana, Mes o Personalizado cambiaba Proyectos a la vista Tablero si
  la tenías en Lista.
- Un texto demasiado largo (por ejemplo, una nota de más de 5000 caracteres) ahora se
  rechaza con un mensaje claro, en vez de «[object Object]».

### Para actualizar
Sin cambios en la base de datos: basta con reiniciar el servicio.

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

### Correcciones
- Al corregir un registro de tiempo desde «Hoy», solo aparecían las tareas de su proyecto.
  Ahora aparecen todas, agrupadas por proyecto, y al pasar el registro a otra tarea su
  tiempo cuenta en el proyecto de esa tarea.

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

[1.16.1]: https://github.com/YoshiDev22/habit-tracker/tree/v1.16.1
[1.16.0]: https://github.com/YoshiDev22/habit-tracker/tree/v1.16.0
[1.15.1]: https://github.com/YoshiDev22/habit-tracker/tree/v1.15.1
[1.15.0]: https://github.com/YoshiDev22/habit-tracker/tree/v1.15.0
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
