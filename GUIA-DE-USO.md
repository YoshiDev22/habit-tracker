# Guía de uso

Cómo se usa la app desde el navegador. Para instalarla o levantarla en local, eso está en
[README.md](README.md); esto es el manual de la web ya funcionando.

Producción: https://habits.yoshidev22.com

---

## Índice

- [Entrar por primera vez](#entrar-por-primera-vez)
- [Tu perfil y el alias](#tu-perfil-y-el-alias)
- [Configuración](#configuración)
- [Calendario de hábitos](#calendario-de-hábitos)
- [Racha, escudos y vacaciones](#racha-escudos-y-vacaciones)
- [Tablero](#tablero)
- [Detalle de la tarjeta](#detalle-de-la-tarjeta)
- [Organizar](#organizar)
- [Proyectos y tareas](#proyectos-y-tareas)
- [Costos (plan Maker)](#costos-plan-maker)
- [Reportes](#reportes)
- [Pomodoro y cronómetro](#pomodoro-y-cronómetro)
- [Registrar tiempo a mano](#registrar-tiempo-a-mano)
- [Corregir o borrar un registro](#corregir-o-borrar-un-registro)
- [Preguntas frecuentes](#preguntas-frecuentes)

---

## Entrar por primera vez

1. Abre la web y pulsa **Registrarse**.
2. Correo y contraseña (mínimo 6 caracteres) son obligatorios.
3. **Alias, Nombre y Apellido son opcionales.** El alias es lo que la app usa para
   llamarte, y sirve para que tu correo no aparezca entero en pantalla.
4. Al crear la cuenta entras directamente, sin tener que iniciar sesión aparte.

La sesión dura **7 días**. Pasado ese plazo la app te devuelve a la pantalla de acceso.

## Tu perfil y el alias

Arriba a la derecha, tu nombre aparece subrayado con puntitos. **Haz clic en él** para
abrir *Mi perfil*: un menú con **Datos personales** (alias, nombre y apellido), **Cambiar
contraseña** y **Borrar mi cuenta**. Toca una opción para entrar y **‹** (o `Esc`) para
volver.

Si no pones nada, la app te llama por la parte de tu correo anterior a la `@`, para no
enseñar la dirección completa. El orden que sigue es:

```
alias → nombre → parte del correo antes de la @
```

El correo completo sigue visible pasando el ratón por encima de tu nombre, y arriba del
modal de perfil.

Guardar pregunta antes de aplicar el cambio, y si cierras el modal con algo editado sin
guardar, también te pregunta si quieres salir de todos modos.

### Cambiar la contraseña

En *Mi perfil › Cambiar contraseña*: la actual y la nueva dos veces (mínimo 6
caracteres). La casilla **Cerrar sesión en mis otros dispositivos** viene marcada: si la
dejas, quien tuviera tu sesión abierta en otro lado tiene que volver a entrar. Aquí sigues
dentro.

### Borrar tu cuenta

En *Mi perfil › Borrar mi cuenta*. Se borra todo: hábitos, tableros, tareas,
tiempo, costos y reportes. Si quieres conservar algo, descárgalo antes desde Reportes
(⬇ Tiempo CSV y ⬇ Hábitos CSV). Hay dos formas:

- **Irme 30 días**: tu cuenta se borra dentro de 30 días y se cierra la sesión. Si entras
  antes de esa fecha, la app te pregunta si quieres conservarla, y todo sigue como estaba.
  Mientras tanto no se generan tus reportes automáticos.
- **Borrar ahora**: se borra todo al momento. Pide tu contraseña y escribir **BORRAR**. No se
  puede deshacer.

## Configuración

El **⚙️** de la barra superior abre *Configuración*: un menú con todo lo que se ajusta.
Toca una categoría para entrar en ella, y **‹** (o `Esc`) para volver al menú. La primera
vez, si aún no sigues ningún hábito, abre directo en *Hábitos*. Los hábitos se guardan con
**Guardar Hábitos**; todo lo demás, al tocarlo.

- **Hábitos**: cuáles sigues, sus colores y sus emojis (ver más abajo).
- **Días y horario**: qué días cuentan y a qué hora: días de descanso, vacaciones,
  festivos y huso horario (ver abajo).
- **Módulos**: **Hábitos y metas** decide si usas la parte de hábitos. Si solo usas los
  tableros y el tiempo, apágala: desaparecen la pestaña Calendario, *Hábitos* y los días
  de descanso de Configuración y la tarjeta de hábitos de Reportes. **No se borra nada**: al
  encenderla vuelven tus hábitos, tus días marcados y tu racha tal como estaban. Se guarda
  en tu cuenta, así que vale en todos tus dispositivos.
- **IA para los reportes** (solo si tu cuenta tiene acceso): una IA escribe el texto de
  tus reportes guardados a partir de sus cifras. **Ver qué se envía** muestra exactamente
  lo que recibe: las instrucciones y las cifras del reporte (en minutos), con los nombres de
  tus proyectos, tareas y etiquetas; nunca tus registros uno por uno.
- **Pomodoro**: las duraciones del enfoque y los descansos.
- **Accesibilidad › Tamaño del texto**: agranda toda la app (Normal, Grande o Muy grande). Se
  aplica al momento y se queda en ese dispositivo, también en la app instalada y aunque
  cierres sesión.

### Días y horario

Dicen qué días trabajas, para que los reportes cuenten bien los días hábiles, y qué días
no cortan tu racha. Todo se guarda al tocarlo.

- **Días de descanso**: los días de la semana que congelan la racha (por ejemplo, el
  domingo). Solo con el módulo de hábitos.
- **Vacaciones**: pausas de la racha (ver [Racha, escudos y vacaciones](#racha-escudos-y-vacaciones)).
- **Días festivos › País**: de ahí salen los **festivos oficiales** del año. Cada uno trae la casilla
  **Descanso**, marcada: ese día no es hábil y congela la racha, como un día de descanso.
  Si lo trabajas, desmárcala y contará como un día normal.
- **Tus días libres**: agrega los que no vienen en el calendario oficial, como un festivo
  de tu ciudad o un puente. También congelan la racha. Tus vacaciones ya cuentan como días
  libres.
- Los festivos se guardan en tu dispositivo para no pedirlos cada vez. Si la lista sale
  vacía o falta alguno, **↻ Actualizar festivos** los vuelve a pedir.
- **Huso horario**: se guarda solo la primera vez, con el de tu dispositivo. Sirve para
  saber a qué hora local trabajaste (por ejemplo, si te desvelaste).

En el calendario, los festivos que descansas llevan 🎉 en la esquina.

## Calendario de hábitos

La pestaña **Calendario** es la vista de inicio.

- **Flechas `<` y `>`**: cambiar de mes.
- **La franja bajo el mes**: `🔥 racha · 🛡️🛡️ escudos · récord`. Tu racha actual, tus dos
  escudos (el gastado se ve vacío, con "Recarga en N días" debajo) y tu racha más larga.
  Ver [Racha, escudos y vacaciones](#racha-escudos-y-vacaciones).
- **Barra MES**: porcentaje de los hábitos que tocaban este mes (hasta hoy) que marcaste.
- **Los puntos de cada día**: uno por hábito, siempre en el mismo lugar; con color si lo
  hiciste, en gris si no. Los días que aún no llegan tienen los puntos casi transparentes.
- **La leyenda, bajo el calendario** ("Este mes · días hechos"): qué hábito es cada punto,
  en el mismo orden, con cuántos días lo hiciste este mes y su racha propia (🔥) si la
  tiene. Con 5 hábitos o menos, los puntos van en una fila; con más, en dos.
- **Clic en un día**: se abre un panel con tus hábitos, cada uno con un círculo de su color
  (vacío si no lo hiciste, relleno si sí). Tócalos para marcar o desmarcar; solo cambia el
  que tocas. Abajo dice cuántos llevas ("2 de 3 hoy") y, si el día no cuenta como fallado,
  por qué: descanso, escudo, vacaciones o festivo.
- **Cómo se ve cada tipo de día**: descanso, atenuado; cubierto por un escudo, con fondo
  azulado y 🛡️ en la esquina; de vacaciones, rayado; festivo que descansas, con 🎉.
- **"¿Olvidaste anotar ayer?"**: si ayer quedó vacío y tenías racha, al abrir la app te lo
  pregunta con tus hábitos para marcarlos. Si sí lo hiciste, lo anotas ahí y recuperas la
  racha (o el escudo que se gastó). Se pregunta una sola vez por día.

Para elegir qué hábitos sigues, sus colores y sus emojis, usa **⚙️ Configuración ›
Hábitos**.

La lista de arriba son **solo los hábitos que sigues**. No hay un catálogo mezclado con
ellos: lo que no sigues no ocupa sitio ahí.

- **Añadir un hábito**: en "Añadir un hábito" tienes los sugeridos (Lectura, Gym, Dieta,
  Estudio, No fumar) como etiquetas; toca una y sube a tu lista. Para uno propio, escribe
  su nombre en *Otro*, elige emoji y color, y pulsa **+**. En los dos casos se crea al
  pulsar "Guardar Hábitos". Un sugerido deja de ofrecerse cuando ya lo tienes. Un hábito
  nuevo va siempre al final, así que no mueve el lugar de los demás.
- **Colores**: al añadir un hábito ya viene con un color que ningún otro usa. Puedes
  repetir uno: la app te avisa, pero lo guarda igual, porque lo que identifica a cada
  hábito en el calendario es su lugar, no su color.
- **Cambiar el emoji**: cada hábito tiene su emoji en un botón, a la izquierda del nombre.
  Púlsalo y se abre un panel con emojis agrupados (salud y deporte, estudio y trabajo,
  comida, casa y dinero, ánimo y aficiones); toca el que quieras. No hace falta buscarlo
  fuera ni pegarlo. El que ya tenías aparece recuadrado. Con **Sin emoji** el hábito se
  queda solo con su nombre, y cerrando el panel sin elegir no se cambia nada. Como todo
  en este modal, se aplica al pulsar "Guardar Hábitos", y el emoji nuevo se ve en el panel
  del día y en la leyenda.
- **Dejar de seguir uno**: desmarca su casilla y pulsa "Guardar Hábitos". **No se borra
  nada**: se archiva con todo su historial intacto y baja a la lista **"Anteriores u
  ocultos"** del final. En los meses donde lo hiciste sigue apareciendo en su lugar
  (atenuado en la leyenda y en el panel del día), y esos días siguen contando para tu
  racha.
- **Recuperar uno archivado**: despliega "Anteriores u ocultos" y pulsa **Restaurar**.
  Vuelve a la lista de arriba y sus marcas antiguas reaparecen en el calendario.
- **Borrar uno para siempre**: solo desde esa misma lista, con el 🗑️ de su fila. Pide
  confirmación y borra el hábito y todo su registro histórico; no se puede deshacer. La
  confirmación te dice cuántos registros se pierden y cuánto bajarían tu racha y tu
  récord, porque los días en que ese hábito fue lo único que hiciste pasan a fallados. Está
  ahí a propósito: para borrar algo hay que archivarlo primero, así que nada de la lista
  que usas a diario puede destruir tu historial de un clic.
- **Días de descanso semanal**: puedes elegir los días de la semana en los que descansas (ej. fines de semana). En un día de descanso:
  - La racha **se congela**: si no marcas hábitos, no se corta ni suma. Si marcas alguno, sí suma a la racha.
  - En el calendario, los días de descanso sin hábitos aparecen con un estilo atenuado.
- **Vacaciones**: debajo de los días de descanso. Ver la sección siguiente.

## Racha, escudos y vacaciones

La app busca que formes el hábito, no que tengas miedo de perder un número. Por eso un día
suelto no borra tu racha. Por qué funciona así, con las investigaciones en que se basa,
está en [docs/referencias.md](docs/referencias.md).

- **Racha**: días seguidos con al menos un hábito marcado. Hoy sin marcar no la corta (el
  día aún no termina). Los días de descanso, los cubiertos por un escudo, los de
  vacaciones y los festivos que descansas la **congelan**: no suman ni la cortan.
- **Récord**: tu racha más larga.
- **Escudos 🛡️**: cada 7 días de racha ganas uno, y puedes tener 2. Si un día no anotas
  nada (y no es de descanso ni de vacaciones), se gasta uno solo y la racha sigue. Si
  después anotas ese día, el escudo vuelve. Sin escudos, un día vacío corta la racha.
- **Vacaciones**: en ⚙️ Configuración › Días y horario, elige **Desde** y **Hasta** y pulsa
  **Programar pausa**. Se guarda al momento.
  - Empieza hoy o después, nunca en días pasados (para un día que ya pasó están los
    escudos y "¿Olvidaste anotar ayer?").
  - Dura hasta 30 días y no puede cruzarse con otra.
  - Mientras dura, los días sin hábitos congelan la racha. Si marcas algo, cuenta normal.
  - Una que aún no empieza se **cancela**; una en curso se **termina** (queda hasta ayer).
    Las que ya terminaron quedan en tu historial y no se pueden borrar.
  - En Reportes, los días de vacaciones no cuentan entre los que tocaban.

## Tablero

Pestaña **Tableros**. También se llega deslizando el dedo hacia la izquierda desde el
calendario. Arriba eliges cómo ver tus tareas: **Tablero**, como tarjetas en columnas, o
**Lista**, agrupadas por proyecto (ver [Proyectos y tareas](#proyectos-y-tareas)). La app
recuerda la elección en ese dispositivo.

La primera vez que entras sin ningún tablero, la app te ofrece crear uno. Viene con tres
columnas: **Por hacer**, **Haciendo** y **Hecho**. Puedes tener varios, por ejemplo
"Escuela" y "Trabajo". **Omitir** te devuelve al calendario.

**La barra de arriba**, de izquierda a derecha:

- **El nombre del tablero**: cambia de tablero. **＋ Nuevo tablero…** abre Organizar para
  crear otro.
- **⚙**: abre [Organizar](#organizar).
- **Hoy** y **🔊**: el tiempo de hoy y el sonido del aviso (ver
  [Pomodoro y cronómetro](#pomodoro-y-cronómetro)).
- **Tablero / Lista**.

**Filtros**: debajo de la barra salen los proyectos y las etiquetas que tienen las tarjetas
de este tablero. Toca uno para ver solo sus tarjetas; si tocas varios proyectos (o varias
etiquetas), ves las de cualquiera de ellos. Con un proyecto y una etiqueta a la vez, solo
quedan las tarjetas que tienen los dos. **Quitar filtros** los apaga. Debajo, una línea
cuenta las tarjetas que ves y su tiempo, con "(con filtro)" si hay alguno.

**Cada tarjeta** muestra su título, el tiempo que lleva, el **▶** para cronometrarla, su
proyecto, sus etiquetas, y si las tiene, el avance del checklist (☑ 2/5) y cuántos
comentarios hay (💬). Si le pusiste un estimado, el tiempo dice cuánto llevas de él
("1h 30m de 3h"); al pasarte, el número cambia de color, sin avisos. Tócala para abrir su
[detalle](#detalle-de-la-tarjeta).

**Columnas con muchas tarjetas**: cada columna enseña 10; abajo, **Mostrar 10 más** suma
otras diez cada vez y **Mostrar menos** vuelve a 10. La lista de cada columna se desplaza
sola, así que la página no se alarga aunque expandas.

**Crear una tarjeta**: al pie de cada columna, escribe en **+ Añadir tarjeta** y pulsa
Enter. Nace en esa columna y en el proyecto "Sin asignar"; si tienes filtrado un solo
proyecto, nace en ese proyecto. Después le cambias el proyecto desde su detalle.

**Mover tarjetas**:

- **En la computadora**: arrástrala a otra columna, o dentro de la misma para cambiar su
  orden. Una línea marca dónde va a caer.
- **En el teléfono**: con **Mover a…**, bajo cada tarjeta. La pantalla enseña una columna a
  la vez; arriba tienes una pestaña por columna con cuántas tarjetas tiene.
- **En una tablet o con el teléfono acostado**: las columnas que no caben se desplazan de
  lado. Cuando llegas a la última, el mismo gesto cambia de pestaña.

**Columnas que marcan algo**: en Organizar verás que una columna dice **📥 Entrada** y otras
**✓ Terminada**. A la Entrada llegan las tareas nuevas que creas desde la Lista, y vuelve
una tarea a la que le quitas la palomita. Mover una tarjeta a una columna Terminada la
marca como hecha: cuenta en el avance del proyecto y en *Tareas terminadas* de Reportes, con
la fecha del día en que la moviste.

## Detalle de la tarjeta

Se abre al tocar una tarjeta. **No hay botón de guardar**: cada cambio se guarda al hacerlo,
y el tablero se actualiza al cerrar.

- **Título**: arriba, se edita ahí mismo. A su lado, el tiempo total de la tarea.
- **Etiquetas**: debajo del título. El **+** abre la lista: toca una para ponerla o
  quitarla. Escribe para buscar, o para crear una nueva con su color.
- **Columna**: para moverla sin salir del detalle.
- **Proyecto**: dónde se suma su tiempo. **＋ Nuevo proyecto…** crea uno sin salir de la
  tarjeta, y el **📊** abre la [ficha del proyecto](#proyectos-y-tareas). Si cambias el
  proyecto, su tiempo se va con ella: el tiempo es de la tarea.
- **Estimado**: cuánto crees que te va a llevar, en horas y minutos (hasta 100 h). Se
  guarda al salir del campo; vacíalo para quitarlo. La tarjeta y la Lista dicen cuánto
  llevas de él. Con el plan Maker, la app compara lo que estimas con lo que de verdad
  tardas (ver [Costos](#costos-plan-maker)).
- **Tiempo**: **▶ Cronómetro**, **🍅 Pomodoro** y **✍️ Registrar a mano**. Mientras corre,
  **■ Detener** lo para. El detalle sigue abierto mientras tanto.
- **Historial de tiempo**: cada registro de esta tarea, del más reciente al más antiguo,
  con **✎** para corregirlo y **×** para borrarlo. Si son muchos, **Ver los N registros**
  los enseña todos.
- **Descripción**: notas libres de la tarea.
- **Checklist**: escribe en *Añadir elemento* y pulsa **+**. Cada elemento tiene su casilla,
  **✎** para cambiarle el texto y **×** para quitarlo. El título del bloque cuenta cuántos
  llevas.
- **Comentarios**: para ir anotando el seguimiento. Los tuyos tienen **✎** y **×**. Con
  **▾** los pliegas; la app lo recuerda en ese dispositivo.
- **Eliminar tarjeta**: al final. Borra la tarea con su checklist y sus comentarios. **Su
  tiempo no se pierde**: se queda en el proyecto, sin tarea.

## Organizar

El **⚙** junto al nombre del tablero. Aquí se ordena todo lo que usan las tarjetas. Cada
cambio se guarda al hacerlo, y si algo no se puede, la app te dice por qué.

- **⏱ Configurar pomodoro**: arriba del todo. Lleva a **⚙️ Configuración › Pomodoro**,
  con las duraciones del enfoque y los descansos (ver [Pomodoro y cronómetro](#pomodoro-y-cronómetro)).
- **Tableros**: escribe sobre el nombre para cambiarlo. **Archivar** lo esconde sin perder
  nada, y bajo *Archivados* tienes **Restaurar**. El **×** lo borra, pero solo si está
  vacío: si tiene tareas, muévelas antes o archívalo. Tu único tablero activo no se puede
  archivar ni borrar. Para uno nuevo, escribe su nombre abajo y pulsa **+**.
- **Columnas de…**: elige el tablero en el menú del título. Cada columna tiene su color, su
  nombre y su marca (📥 Entrada o ✓ Terminada, ver [Tablero](#tablero)). Ordénalas
  arrastrando el **⠿** o con las flechas **↑ ↓**. Para una nueva, escribe el nombre; marca
  *✓ Las tareas aquí cuentan como terminadas* si debe marcarlas como hechas.
  - Una columna **con tareas no se borra**: muévelas antes a otra. Así ninguna tarea se
    queda sin columna.
  - Tampoco se borran la única Entrada ni la única Terminada de un tablero: el tablero las
    necesita para saber dónde poner una tarea nueva y cuándo una está hecha.
- **Proyectos**: nombre y color, el **📊** que abre su ficha y **Archivar**. Bajo
  *Archivados*, **Restaurar**. Para borrar un proyecto ve a la **Lista** (con su **⋯**): ahí
  eliges qué pasa con su tiempo. Si está archivado, restáuralo primero.
- **Etiquetas**: nombre, color y **×** para borrarla. Borrar una etiqueta solo la quita de
  sus tareas: las tareas y su tiempo no cambian.

## Proyectos y tareas

La vista **Lista** de la pestaña Tableros: tus tareas agrupadas por proyecto. Se elige con
**Lista**, arriba a la derecha (para las columnas, ver [Tablero](#tablero)).

**Crear un proyecto**: el botón **+** de la cabecera "Proyectos". Puedes darle nombre,
descripción, un emoji y un color.

**Ficha del proyecto**: clic sobre su nombre. Muestra todo su tiempo de un vistazo: el
total, las tareas hechas, cuánto lleva cada tarea, cada etiqueta y cada mes. Cuadra con el
total de la tarjeta y con Reportes. También se abre con el **📊** de cada proyecto en
**⚙ Organizar**.

**Editar un proyecto**: desde su ficha, con **✎ Editar**.

**Costeo (plan Maker)**: si tu cuenta tiene el plan Maker y lo enciendes en *⚙️ Configuración ›
Módulos*, la ficha de cada proyecto trae una tarjeta **Costeo**: tipo
(personal, producto o servicio), moneda, cliente, tarifa por hora, precio y presupuesto (en
dinero, en horas o los dos). Cada dato se guarda al cambiarlo. La tarjeta calcula:

- la **mano de obra** (horas trabajadas × tarifa) y el costo total con los gastos;
- el **presupuesto disponible** (presupuesto − costo), o cuánto te pasaste;
- el **margen** (precio − costo), o la pérdida si cuesta más de lo que cobras. Solo sale
  con precio.

Un proyecto **personal** no se cobra: no pide cliente ni precio, y no tiene margen. Si un
proyecto tiene presupuesto pero todavía no tiene tiempo, se marca como **Cotización**.

**Estimado contra real (plan Maker)**: si alguna tarea del proyecto tiene estimado, la
ficha trae también esta tarjeta: cuánto tardas en total frente a lo que estimaste, en
general y por etiqueta. Es la misma cuenta que *Tus estimados* de Costos, solo con las
tareas de este proyecto.

**Archivar o eliminar**: el botón **⋯** de la tarjeta.

> **Archivar** conserva todo y solo lo esconde de la lista.
> **Eliminar** quita el proyecto, pero no sus tareas: sus tareas y su tiempo pasan a
> **Sin asignar**. Si también quieres borrar su tiempo, la confirmación trae una casilla
> para eso. Con el plan Maker, su costeo y sus gastos sí se borran con él. Eliminar no se
> puede deshacer: ante la duda, archiva.

**Tareas**: despliega el proyecto con la flecha **▾**. Debajo aparecen sus tareas, el
campo *Nueva tarea* para añadir más, y el historial de tiempo.

- La casilla marca la tarea como terminada.
- Junto a cada nombre verás **el tiempo dedicado a esa tarea**, y si tiene estimado,
  cuánto llevas de él ("de 3h"), en otro color si ya te pasaste.
- El **▶** arranca el cronómetro en esa tarea, sin pasar por los selectores de arriba.
  Mientras corre, la fila queda resaltada. Si ya tenías otro timer en curso, te pregunta
  antes de cambiarlo. En las tareas ya hechas no aparece.
- La línea **"Sin tarea"** recoge el tiempo registrado en el proyecto sin elegir tarea, de
  forma que la suma de todo cuadra con el total de la tarjeta.

## Costos (plan Maker)

Con el plan Maker encendido aparece una cuarta pestaña, **Costos**, para lo que un proyecto
cuesta además de tus horas: licencias, materiales, servicios, tokens de IA…

- **Arriba, el resumen**: costo total, mano de obra, gastos y lo presupuestado; una tabla
  con cada proyecto, su presupuesto **disponible** (presupuesto − costo), su **precio** y
  su **margen** (precio − costo), en rojo si es negativo; y la gráfica **Costos**: una columna para la mano de obra y una por categoría, con su
  porcentaje, sobre un eje de montos a la izquierda que se ajusta solo (su tope queda
  siempre un poco arriba del gasto más alto). Debajo, cada nombre con su cifra exacta;
  tócalo para ocultar o mostrar su columna (solo en la gráfica, los totales no cambian) y
  el eje se reajusta a las que quedan. Arriba de la gráfica, **Proyecto** la limita a uno
  solo (su mano de obra y sus gastos); la app recuerda cuál elegiste. En el teléfono la
  tabla enseña solo costo, disponible y margen. El precio y el presupuesto se editan
  tocando su cifra. Si tienes proyectos en monedas distintas, cada moneda va aparte: la app
  nunca las suma ni convierte.
- **Reporte de costos**, hasta arriba: elige el mes y toca **Generar reporte** (o **Ver
  reporte** si ya existe). Se arma como el de tiempo: una tabla del mes anterior contra
  este (costo, mano de obra, gastos, horas), la gráfica de mano de obra y gastos por
  categoría, una dona por mes con la parte de cada proyecto, los gastos más grandes, y cada
  proyecto con su presupuesto disponible y su margen **acumulados** hasta el cierre del
  mes. Sale solo cada día 1, del mes anterior. **Reportes de
  costos** los lista todos. Con la IA encendida, el texto lo escribe ella, con su propio
  límite diario.
- **Abajo, la hoja de gastos** del proyecto elegido (toca su fila en el resumen o elígelo
  en la lista). Se usa como una hoja de cálculo: escribe en las celdas y cada cambio se
  guarda solo; **＋ Agregar fila** para uno nuevo, y Enter baja a la fila siguiente.
- **Traer varios de una vez**: copia las filas en Excel o Google Sheets y pégalas en la hoja
  (Ctrl+V). También puedes **importar un CSV**. Antes de guardar ves una vista previa: las
  filas que no se entienden salen en rojo y se saltan, y si traen una categoría que no
  tienes, puedes crearla. Las columnas pueden llevar encabezado (Fecha, Concepto,
  Categoría, Cantidad, Costo unitario, Nota) o venir en ese orden.
- **Repartir un gasto entre proyectos**: el **↔** de la fila abre el reparto. Elige los
  proyectos y su parte (por ejemplo, una suscripción de IA: 65 % Tesis, 35 % Habit
  Tracker); tienen que sumar 100 % y ser de la misma moneda. Cada proyecto ve su parte, con
  "↔ 65 %" y el total del gasto debajo. Cambiar el monto, la fecha o el concepto de una
  parte cambia el gasto entero, y borrarla lo borra de todos los proyectos.
- **Gastos recurrentes**: en su tarjeta, **＋ Nuevo recurrente** para lo que pagas cada mes o
  cada año (hosting, suscripciones, dominios), con su primer cobro y, si quieres, cuándo
  termina; también puede ir repartido. En su fecha se anota solo en la hoja, con 🔁, y ahí lo
  corriges si ese mes cambió. Cambiarlo afecta a los cobros siguientes, no a los ya
  anotados. **Pausar** lo detiene (al reanudarlo, lo de la pausa no se cobra) y **×** lo
  termina: lo ya anotado se queda.
- **Categorías**: vienen cinco (material, licencia/software, servicio, IA y otro) y son
  tuyas: en **Categorías**, al final de la pestaña, las renombras, les cambias el color, las
  ordenas o creas más. Una categoría con gastos no se borra hasta pasar sus gastos a otra.
- Para gastos que no son de un proyecto (una licencia que usas en todo), crea un proyecto
  "Gastos generales". Borrar un proyecto borra sus gastos; archivarlo los conserva.
- **Tus estimados**: cuánto te desvías de lo que estimas, con las tareas de todos tus
  proyectos. *"Tardas 1.3× lo que estimas"* quiere decir que cada hora que estimas te
  lleva 1h 18m. Debajo, la misma cifra por etiqueta, para saber en qué tipo de trabajo te
  quedas más corto. Cuentan las tareas con estimado y tiempo que ya terminaste, y las
  abiertas que ya pasaron su estimado; las que van por debajo esperan a terminarse. Con
  menos de 3 tareas, una fila dice "poco historial" en vez de una cifra. Sirve para
  cotizar: si sueles tardar 1.3×, estima con eso en mente.

## Reportes

La última pestaña. Es solo de lectura: aquí no se cambia nada, solo se ve lo que hiciste.

**El periodo**, arriba: **Semana** (de lunes a domingo), **Mes** o **Personalizado** (eliges
*Desde* y *Hasta*). Con **<** y **>** vas al periodo anterior o al siguiente.

**Qué cuenta**: solo el **tiempo de trabajo** (pomodoros de enfoque, cronómetro y registros a
mano), nunca los descansos. Es el mismo criterio que las tarjetas y la Lista, así que las
cifras cuadran entre sí.

Las tarjetas, en orden:

- **Resumen**: tiempo total, promedio por día, días con tiempo y tareas terminadas, y cuánto
  cambió respecto al periodo anterior.
- **Hábitos**: tu racha, tu récord, tus escudos y cómo te fue con cada hábito en el periodo.
  Si apagaste *Hábitos y metas* en tu perfil, esta tarjeta no sale.
- **Tiempo por día**: una barra por día. Pasa el dedo o el ratón por encima para ver la
  cifra. Los días de descanso se distinguen.
- **Por proyecto**: cuánto tiempo fue a cada uno.
- **Por etiqueta**: cuánto fue a cada etiqueta, más *Sin etiqueta*. Una sesión cuenta en
  cada etiqueta de su tarea, así que estas cifras **no se suman entre sí**. Toca varias
  etiquetas y abajo sale su total **juntas**, contando cada sesión una sola vez.
- **Tareas terminadas**: las que terminaste en el periodo, con su tiempo. Ese tiempo es el
  total de la tarea, no solo el de este periodo. Si son muchas, **Ver las N**.
- **¿A qué hora rindes más?**: un mapa de calor por día de la semana y hora. Usa la hora de este
  dispositivo, así que lo que registraste desde otro huso horario se verá corrido.
- **Cómo se registró**: qué parte vino del pomodoro, del cronómetro y de registros a mano.

**⬇ Tiempo CSV**, bajo la fecha: descarga los registros de tiempo del periodo, uno por
fila (fecha, inicio, fin, duración, horas, tarea, proyecto, etiquetas, origen y nota). Se
abre directo en Excel o en Google Sheets.

**⬇ Hábitos CSV**, a su lado: un renglón por día y hábito del periodo, hasta hoy (fecha,
día de la semana, hábito, si lo hiciste y el tipo de día: descanso, vacaciones, protegido
por escudo u hoy en curso). Para un periodo largo, elige *Personalizado* (hasta un año).

### Reportes guardados

Un reporte es una foto del periodo: guarda las cifras como estaban al generarlo, con
observaciones y recomendaciones, para leerlo después o compararlo.

- **Generar reporte de tiempo** y **Generar reporte de hábitos**, bajo el periodo (solo
  con *Semana* o *Mes*): hacen el reporte de lo que estás viendo y lo abren. Si ese periodo
  ya tiene uno, el botón dice **Ver reporte**. Uno de la semana o el mes en curso llega
  hasta hoy. El de hábitos solo aparece con el módulo Hábitos encendido.
- **Solos**: cada lunes salen los de la semana anterior, y cada día 1 los del mes anterior,
  si registraste tiempo o marcaste hábitos en ese periodo. Si generaste uno a medias con el
  botón, el automático lo completa.
- **Regenerar**: si corriges un registro después, vuelve a calcular el reporte (reemplaza
  al anterior, no se duplica). Al terminar dice **Reporte generado ✓** con la hora. Después
  hay que esperar unos segundos para volver a generarlo; si tocas antes, te dice cuánto
  falta, sin gastar nada.
- **Reportes guardados**: la lista de todos, del más nuevo al más viejo.
- **Con IA** (si la encendiste en *Configuración › Módulos*): el texto lo escribe la IA,
  y arriba dice «texto de IA» o «texto de reglas». Las cifras siempre las calcula la app;
  si la IA falla, cita una cifra que no estaba o llegaste al límite del día, el reporte
  usa las reglas y te dice por qué. **Reescribir el texto con IA** vuelve a pedir el texto de un
  reporte ya guardado, sin cambiar sus cifras: si corregiste registros o la app trae cifras
  nuevas, usa **Regenerar**. Bajo los botones dice cuántos textos con IA
  te quedan hoy: los reportes de tiempo y de hábitos comparten 10 al día, y los de costos
  tienen los suyos.
- **Imprimir / PDF**: imprime solo el reporte, en colores claros. Para un PDF, elige
  "Guardar como PDF" en la ventana de impresión.

Qué trae, con las horas en decimal (14.3 h):

- **Resumen**: horas y días hábiles con registro (qué día fue festivo, cuál sigue en curso),
  horas por día comparadas con el periodo anterior y, si va a medias, cuánto llevarías al
  cerrar si mantienes el ritmo. Debajo, la **limpieza de datos**: qué registros dudosos hay;
  nunca se excluye nada.
- **Métricas**: una tabla del periodo anterior contra este, y las horas por día de las dos
  semanas lado a lado (en el mensual, por semana). Bajo un día sin barra dice si fue
  festivo, sin registro o pendiente.
- **¿En qué se fue el tiempo?**: una dona por periodo con cada proyecto y su %, y tus
  tareas principales del color de su proyecto. En el mensual, el proyecto principal por
  etiqueta.
- **Patrones**, **Legibilidad y etiquetado** (tareas con nombres poco claros, tiempo sin
  etiqueta), **Observaciones**, **Comparativa** (el mensual), **Para la próxima semana** o
  **Metas** del mes, y el **Cierre**: un *Bien hecho* y un *Tip*.
- **Registros a revisar**: el detalle de los dudosos, si hay.

El texto lo escriben reglas fijas a partir de las cifras, o la IA si la tienes.

**El reporte de hábitos** dice cómo te fue con cada hábito:

- **Resumen**: tu cumplimiento (marcas hechas de las posibles), los días con algún hábito y
  tu racha al cierre del periodo, comparado con el anterior. Debajo, qué días **no contaron
  como fallo**: descanso, vacaciones, festivos y días cubiertos por un protector.
- **Métricas**: una tabla del periodo anterior contra este (cumplimiento, días con algún
  hábito, racha, días sin hábitos, protegidos y de descanso) y una gráfica: en el semanal,
  cuántos hábitos hiciste cada día junto a la semana anterior; en el mensual, el
  cumplimiento por semana y por día de la semana.
- **¿Cómo te fue con cada hábito?**: una dona por periodo con la parte de cada hábito, y
  cada uno con sus días hechos de los que contaban, antes y ahora, y su racha. Un hábito
  nuevo cuenta desde que lo creaste.
- **Patrones**, **Observaciones**, **Comparativa** (el mensual), los siguientes pasos y el
  **Cierre**. El texto nunca regaña: si algo costó, propone cómo retomarlo.

## Pomodoro y cronómetro

El tiempo siempre se mide **en una tarea**, y se arranca desde ella:

- En el **Tablero**, el **▶** de la tarjeta arranca el cronómetro. Si ya corre en esa
  tarea, lo detiene.
- En la **Lista**, el **▶** junto a cada tarea hace lo mismo.
- Al abrir una tarjeta, elige **▶ Cronómetro** o **🍅 Pomodoro**. El detalle sigue
  abierto mientras corre, y **■ Detener** lo para desde ahí.

Si ya tenías otro timer en curso, te pregunta antes de cambiarlo.

Mientras corre, una **barra flotante** abajo lo controla desde cualquier pestaña:
**⏸** pausa y retoma, **■** detiene. El tiempo también aparece en el título de la
ventana.

### Cronómetro

El pomodoro cuenta hacia atrás y se acaba; el **Cronómetro** cuenta hacia arriba y no
termina hasta que tú lo detengas. Es para cuando te concentras y no quieres que el tiempo
extra se quede sin registrar por no haber oído el aviso.

- Detenerlo es lo que guarda el tiempo, así que no pregunta nada.
- **¿Se te olvidó arrancarlo?** El **✎** de la barra te deja escribir cuánto llevas
  trabajando (y cambiar de tarea, si lo arrancaste en otra). Sigue corriendo desde ahí.
- **A las 8 horas se detiene y te pregunta cuánto trabajaste**, empezando en 8 h. Si la
  app vio tu última actividad, te la sugiere con **Usar esa hora**. No se guarda nada
  hasta que contestes, aunque recargues la página.
- El tiempo que pasa en pausa no cuenta.
- Si cierras la pestaña y vuelves, el cronómetro sigue contando: su tiempo se mide desde
  la hora en que arrancó, no desde que la pestaña está abierta.

### Pomodoro

- **Enfoque** dura 25 minutos, y los descansos 5 y 15. **Puedes cambiarlos** en
  **⚙️ Configuración › Pomodoro** (también desde *⚙ Organizar*). Un pomodoro que ya corre termina con la
  duración con la que empezó.
- Al terminar un enfoque, la barra te ofrece **descanso corto o largo**. Los descansos
  solo se inician desde ahí y no cuentan como trabajo.
- Detener un enfoque antes de tiempo pregunta antes, para que no lo cortes sin querer
  (si lleva menos de un minuto no pregunta: ese tiempo no se guardaría de todos modos).

### Detalles que conviene saber

- **Solo se guarda el tiempo de trabajo** (enfoque y cronómetro), nunca los descansos.
- Si detienes antes del **primer minuto**, la sesión se descarta en vez de guardarse.
- **Al terminar suena un aviso aunque estés en otra pestaña.** Son dos pitidos cortos. El
  **🔊** de la barra del tablero lo silencia o lo reactiva.
- La primera vez que arranques un timer, el navegador te pedirá permiso para
  **notificaciones**. Si aceptas, además te avisa el sistema con el navegador de fondo.
- **"Hoy"**, en la barra del tablero, suma lo trabajado hoy. Tócalo para ver cada registro
  del día, de todas las tareas, y moverte entre días con ‹ ›. Desde ahí también se
  corrigen (✎) y se borran (×).

## Registrar tiempo a mano

Para cuando trabajaste sin arrancar el timer. Es lo que convierte la app en una bitácora
y no solo en un pomodoro.

1. En la **Lista**, pulsa el **⏱** del proyecto. En el **Tablero**, abre la tarjeta y
   pulsa **✍️ Registrar a mano**.
2. **Fecha**: por defecto hoy. No se pueden registrar fechas futuras.
3. **Duración**: escribe las horas y los minutos, y **el inicio y el fin se rellenan
   solos** restando ese rato a la hora actual. Si prefieres, escribe las horas
   directamente y la duración se calcula sola. Los dos caminos se mantienen sincronizados.
4. **Tarea** y **nota** son opcionales. La nota es donde cuentas qué hiciste; caben 200
   caracteres.
5. **Guardar**.

El registro cuenta exactamente igual que uno del timer: suma al total del proyecto, al de
la tarea y al tiempo de hoy.

> **Si trabajaste a caballo de la medianoche**, hazlo en dos registros, uno por día. Un
> registro no puede cruzar de un día al siguiente. Si escribes una duración que no cabe
> antes de la hora actual, la app la ajusta y te avisa en la línea de duración.

## Corregir o borrar un registro

**La campanita 🔔**, arriba junto al ⚙️, avisa cuando un cronómetro llegó al tope de 8 h y
nadie dijo cuánto trabajaste (por ejemplo, si cerraste la sesión o la pregunta se quedó en
otra pestaña). El número rojo dice cuántos hay. Tócala y, en cada uno, elige **Corregir**
para poner el tiempo real, o **Está bien** si de verdad fueron 8 h. Mientras no lo hagas, ese
tiempo cuenta en tus totales, y Reportes te avisa que lo está incluyendo.

Despliega el proyecto y busca **Registros de tiempo**, debajo de las tareas. Cada línea
muestra día, horario, duración, tarea y nota:

- **⏱** lo midió un pomodoro.
- **▶** lo midió el cronómetro.
- **✍️** lo escribiste tú a mano.

**Corregir**: el botón **✎**. Se abre el mismo formulario, ya relleno, y puedes cambiar la
fecha, las horas, la tarea o la nota. El proyecto no se puede cambiar: para eso, borra y
vuelve a crearlo.

**Borrar**: el botón **×**. Pide confirmación antes, porque descuenta tiempo del proyecto
y de la tarea, y no se puede deshacer.

Se muestran los 10 registros más recientes de cada proyecto.

## Preguntas frecuentes

**¿Qué versión estoy usando?**
Abajo en la pantalla de acceso, y en la barra superior una vez dentro. Si acabas de
desplegar y sigue saliendo la anterior, recarga con `Ctrl + F5`.

**Terminé un pomodoro y no aparece.**
Si en ese momento no había conexión o la sesión había caducado, la app guarda la sesión en
el navegador y la reintenta al volver a entrar o al recargar. **No cierres sesión a mano
antes de que se envíe**: al cerrar sesión esa cola se borra, para que tu tiempo no acabe
registrado en la cuenta de otra persona que use el mismo dispositivo.

**¿Por qué el tiempo de una tarea no cuadra con el del proyecto?**
Porque parte del tiempo se registró sin elegir tarea. Ese resto aparece en la línea
**"Sin tarea"**, y sumado a las tareas da el total del proyecto.

**Cambié mi alias y la barra sigue igual.**
Debería cambiar al instante al guardar. Si no, recarga con `Ctrl + F5`.

**¿Se puede usar desde el móvil?**
Sí, el diseño se adapta y se cambia de pestaña deslizando el dedo. También se puede
instalar: desde el navegador, "Agregar a la pantalla de inicio" (o "Instalar app" en la
computadora), y se abre como una aplicación. Si el texto se ve pequeño, agrándalo en
*⚙️ Configuración › Accesibilidad › Tamaño del texto*.

**En el teléfono todo se ve diminuto, como si fuera la versión de computadora.**
El navegador está en modo **"Sitio para ordenador"** (o "Versión de escritorio"): dibuja la
app como si la pantalla midiera unos 980 px y la encoge. En Chrome: menú ⋮ → desmarca
"Sitio para ordenador" y recarga. Si la tienes instalada y sigue igual, reinstálala desde
el navegador ya sin ese modo.

**Me fui de vacaciones y no lo programé. ¿Perdí la racha?**
Si fueron uno o dos días, tus escudos la cubrieron (si los tenías). Para días más largos,
la pausa se programa antes de irte: no se puede poner hacia atrás.
