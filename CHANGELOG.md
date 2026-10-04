# Novedades

Qué trae cada versión de Habit Tracker, escrito para quien usa la app. El detalle técnico
está en el historial de git; cada versión tiene su tag (`v1.9.0`, `v1.10.0`…).

Formato: [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). Versionado:
[semver](https://semver.org/lang/es/), con el criterio de la sección *Versionado* de
`CLAUDE.md`.

## [1.20.0] — 2026-10-03

Reportes que se guardan solos cada semana y cada mes, con IA opcional para el texto, y una
Configuración nueva con todo en un solo lugar.

### Nuevo
- **Reportes guardados**: en Reportes, con *Semana* o *Mes*, **Generar reporte** hace el
  reporte del periodo que ves (o **Ver reporte** si ya existe). Trae un resumen con la
  limpieza de datos, una tabla de métricas contra el periodo anterior, las horas por día de
  las dos semanas lado a lado (por semana en el mensual), en qué se fue el tiempo,
  patrones, legibilidad, observaciones, próximos pasos o metas y un cierre con *Bien hecho*
  y *Tip*. **Reportes guardados** los lista todos, y **Imprimir / PDF** imprime solo el
  reporte.
- **Reportes automáticos**: cada lunes sale el de la semana anterior y cada día 1 el del mes
  anterior, si registraste tiempo.
- **IA para el texto de los reportes** (solo para las cuentas con acceso): se enciende en
  *Configuración › Módulos*. Las cifras siempre las calcula la app; la IA solo escribe el
  texto, y si cita una cifra que no estaba o falla, el reporte usa el texto de reglas y te
  dice por qué. **Ver qué se envía** muestra exactamente lo que recibe, y **Reescribir con
  IA** vuelve a pedir el texto de un reporte ya guardado.
- **Configuración**: el ⚙️ abre un menú con **Hábitos**, **Días y horario**, **Módulos**,
  **Pomodoro** y **Accesibilidad**. Cada uno se desliza a su página; ‹ o `Esc` regresan.
- **Días y horario**: tus días de descanso, tus vacaciones, los **festivos de tu país** y tu
  huso horario en un solo lugar. Cada festivo trae la casilla **Descanso**; si lo trabajas,
  desmárcala. Agrega tus propios días libres (un festivo local, un puente).
- **Festivos en el calendario**: los que descansas llevan 🎉 y **no cortan tu racha**, igual
  que los días de descanso.
- **Sesiones por confirmar**: un cronómetro que llegó al tope de 8 h sin que dijeras cuánto
  trabajaste queda marcado. La **campanita** de arriba los cuenta y te deja corregirlos o
  confirmarlos, y Reportes dice cuánto tiempo sin confirmar incluye.
- **Hábitos a CSV**: en Reportes, **⬇ Hábitos CSV** descarga un renglón por día y hábito.

### Cambios
- *Mi perfil* queda solo con alias, nombre y apellido. Los módulos, el pomodoro y el tamaño
  del texto se mudaron a Configuración. El botón de pomodoro de *Organizar* lleva ahí.
- Los días de descanso se guardan al tocarlos, sin *Guardar Hábitos*.

### Correcciones
- Cerrar sesión con el cronómetro corriendo ya no pierde ni infla el tiempo.
- Registrar tiempo a mano ya no puede guardarse antes de que carguen las tareas (se perdía
  la tarea del registro).

### Para actualizar
- **Dependencias**: hay una nueva (`tzdata`, los husos horarios). Instalar con
  `pip install -r requirements.lock`.
- **Base de datos**: correr `python3 scripts/migrate.py` **antes** de reiniciar el servicio.
  Añade la marca de *por confirmar* a las sesiones y marca una sola vez las de 8 h que se
  cerraron solas. Si se olvida, el servicio no arranca y el log dice qué falta. Las tablas
  nuevas (reportes, festivos, calendario de trabajo, llamadas a la IA) las crea la app al
  arrancar.
- **Reportes automáticos** (opcional): `deploy/habit-reports.service` y `.timer` son
  plantillas. Se ajustan con el usuario y las rutas reales, se copian a
  `/etc/systemd/system/` y se activa el timer (`systemctl enable --now habit-reports.timer`).
  `scripts/generate_reports.py --dry-run` muestra qué generaría sin guardar nada.
- **IA** (opcional): agregar el bloque `AI_*` de `backend/.env.example` al `.env`, reiniciar,
  y dar acceso a cada cuenta con
  `python3 scripts/grant_module.py --email <correo> --module ai`.

## [1.19.0] — 2026-10-02

Con el plan Maker, anota lo que cuesta cada proyecto además de tus horas, y compara lo que
estimas con lo que de verdad tardas.

### Nuevo
- **Estimado en cada tarjeta**: en el detalle de la tarjeta, el campo **Estimado** (horas y
  minutos, hasta 100 h). La tarjeta y la Lista dicen cuánto llevas de él ("1h 30m de 3h");
  si te pasas, el número cambia de color, sin avisos. Es para todos, con o sin Maker.
- **Pestaña Costos** (plan Maker), entre Tableros y Reportes:
  - un resumen con costo total, mano de obra, gastos y presupuesto, y una tabla con cada
    proyecto y su **margen** (en rojo si te pasas). La mano de obra y el presupuesto se
    editan tocando la cifra;
  - la **hoja de gastos** de cada proyecto (licencias, materiales, servicios, IA…), que se
    edita como una hoja de cálculo y guarda cada celda sola;
  - **pegar desde Excel o Google Sheets**, o importar un CSV, con vista previa antes de
    guardar: las filas que no se entienden se marcan y se saltan;
  - **categorías** tuyas: vienen cinco, y las renombras, les cambias el color, las
    ordenas (arrastrando, en la computadora) o creas más;
  - la gráfica **Costos**: una columna para la mano de obra y una por categoría, sobre un
    eje de montos que se ajusta solo. Toca un nombre de la leyenda para ocultar su
    columna: el eje se reajusta y nada de la página se mueve;
  - **Tus estimados**: cuánto tardas frente a lo que estimas ("tardas 1.3× lo que
    estimas"), en total y por etiqueta, con las tareas de todos tus proyectos.
- **Estimado contra real en la ficha del proyecto** (plan Maker): la misma cuenta, solo con
  las tareas de ese proyecto.

### Cambios
- La tarjeta **Costeo** de la ficha suma ahora los gastos al costo, y dice el margen o
  cuánto te pasaste del presupuesto.
- Al eliminar un proyecto con Maker, la confirmación avisa que se borran su costeo y sus
  gastos.

### Para actualizar
Esta versión añade una columna a la base de datos (el estimado de cada tarea): correr
`python3 scripts/migrate.py` **antes** de reiniciar el servicio. Si se olvida, el servicio
no arranca y el log dice qué falta. Las tablas de gastos y categorías son nuevas y la app
las crea sola al arrancar. Las tareas que ya existían quedan sin estimado.

## [1.18.0] — 2026-10-01

Costea tus proyectos con el plan Maker: tarifa, presupuesto y mano de obra en la ficha.

### Nuevo
- **Plan Maker**: si tu cuenta lo tiene, aparece en Mi perfil › Módulos de tu cuenta. Por
  ahora es gratis y se da por invitación. Encendido, tu nombre lleva la etiqueta **MKR**, y
  Mi perfil te dice dónde está lo nuevo.
- **Costeo en la ficha del proyecto**: con Maker encendido, cada ficha trae una tarjeta
  **Costeo** con cliente, tarifa por hora, moneda (MXN, USD, EUR y otras) y presupuesto en
  dinero, en horas o los dos. Calcula la **mano de obra** (horas trabajadas × tarifa) y
  cuánto del presupuesto llevas, en rojo si te pasas. Un proyecto con presupuesto y sin
  tiempo todavía se marca como **Cotización**.
- **La ficha del proyecto desde el Tablero**: en el detalle de una tarjeta, el **📊** junto a
  Proyecto abre su ficha encima de la tarjeta.

### Para actualizar
Esta versión crea una tabla nueva (el costeo de cada proyecto), que la app crea sola al
arrancar: no hace falta `migrate.py` para ella. Para dar el plan Maker a una cuenta:
`python3 scripts/grant_module.py --email <correo> --module maker`.

## [1.17.0] — 2026-10-01

Usa solo la parte de la app que te sirve, y mira todo el tiempo de un proyecto de un
vistazo.

### Nuevo
- **Módulos de tu cuenta**: en Mi perfil, la casilla **Hábitos y metas**. Si solo usas los
  tableros y el tiempo, apágala: desaparecen la pestaña Calendario, el ⚙️ de hábitos y la
  tarjeta de hábitos de Reportes. No se borra nada; al encenderla vuelve todo como estaba.
  Se guarda en tu cuenta, así que vale en todos tus dispositivos.
- **Ficha del proyecto**: toca un proyecto en la Lista (o el 📊 de cada proyecto en
  Organizar) y ves su tiempo total, sus tareas hechas, y cuánto lleva cada tarea, cada
  etiqueta y cada mes. Cuadra con la Lista y con Reportes. También para los archivados.

### Cambios
- Tocar un proyecto en la Lista abre su ficha; para editarlo, **✎ Editar** dentro de ella.

### Para actualizar
Esta versión crea una tabla nueva (los módulos de cada cuenta), que la app crea sola al
arrancar: no hace falta `migrate.py` para ella. Si vienes de la 1.16.1, la 1.16.2 sí pide
`python3 scripts/migrate.py` antes de reiniciar. Las dependencias se instalan con
`pip install -r requirements.lock`.

## [1.16.2] — 2026-10-01

Tu tiempo ya no se cuenta doble, y tu cuenta queda más protegida.

### Correcciones
- **Tiempo duplicado**: si el navegador se cerraba justo al guardar una sesión, o se perdía
  la conexión mientras se reenviaba una pendiente, ese tiempo podía guardarse dos veces.
  Ahora cada sesión se guarda una sola vez, por más que se reenvíe.
- **Límite de intentos al entrar**: después de 10 contraseñas equivocadas en 15 minutos
  desde la misma conexión, la app pide esperar un rato antes de volver a intentar. Entrar
  con la contraseña correcta no gasta intentos. También hay un límite de cuentas nuevas
  por hora.

### Para actualizar
Esta versión añade una columna y un índice a la base de datos: correr
`python3 scripts/migrate.py` **antes** de reiniciar el servicio. Si se olvida, el servicio
no arranca y el log dice qué falta. Las dependencias se instalan ahora con
`pip install -r requirements.lock`. Si Caddy no conecta a la app por `127.0.0.1`, añadir
su IP a `--forwarded-allow-ips` del servicio; si no, todos los usuarios comparten un mismo
límite de intentos.

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

[1.20.0]: https://github.com/YoshiDev22/habit-tracker/tree/v1.20.0
[1.19.0]: https://github.com/YoshiDev22/habit-tracker/tree/v1.19.0
[1.18.0]: https://github.com/YoshiDev22/habit-tracker/tree/v1.18.0
[1.17.0]: https://github.com/YoshiDev22/habit-tracker/tree/v1.17.0
[1.16.2]: https://github.com/YoshiDev22/habit-tracker/tree/v1.16.2
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
