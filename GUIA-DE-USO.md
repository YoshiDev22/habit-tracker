# Guía de uso

Cómo se usa la app desde el navegador. Para instalarla o levantarla en local, eso está en
[README.md](README.md); esto es el manual de la web ya funcionando.

Producción: https://habits.yoshidev22.com

---

## Índice

- [Entrar por primera vez](#entrar-por-primera-vez)
- [Tu perfil y el alias](#tu-perfil-y-el-alias)
- [Calendario de hábitos](#calendario-de-hábitos)
- [Racha, escudos y vacaciones](#racha-escudos-y-vacaciones)
- [Proyectos y tareas](#proyectos-y-tareas)
- [Costos (plan Maker)](#costos-plan-maker)
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
abrir *Mi perfil* y cambiar alias, nombre o apellido cuando quieras.

Si no pones nada, la app te llama por la parte de tu correo anterior a la `@`, para no
enseñar la dirección completa. El orden que sigue es:

```
alias → nombre → parte del correo antes de la @
```

El correo completo sigue visible pasando el ratón por encima de tu nombre, y arriba del
modal de perfil.

Guardar pregunta antes de aplicar el cambio, y si cierras el modal con algo editado sin
guardar, también te pregunta si quieres salir de todos modos.

### Módulos de tu cuenta

En *Mi perfil*, **Módulos de tu cuenta › Hábitos y metas** decide si usas la parte de
hábitos. Si solo usas los tableros y el tiempo, apágala: desaparecen la pestaña
Calendario, el ⚙️ de hábitos y la tarjeta de hábitos de Reportes. **No se borra nada**: al
encenderla vuelven tus hábitos, tus días marcados y tu racha tal como estaban. Se guarda al
tocarla, en tu cuenta, así que vale en todos tus dispositivos.

### Tamaño del texto

Al final de *Mi perfil*, **En este dispositivo › Tamaño del texto** agranda toda la app
(Normal, Grande o Muy grande). Se aplica al momento y se queda en ese dispositivo, también
en la app instalada y aunque cierres sesión.

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
  por qué: descanso, escudo o vacaciones.
- **Cómo se ve cada tipo de día**: descanso, atenuado; cubierto por un escudo, con fondo
  azulado y 🛡️ en la esquina; de vacaciones, rayado.
- **"¿Olvidaste anotar ayer?"**: si ayer quedó vacío y tenías racha, al abrir la app te lo
  pregunta con tus hábitos para marcarlos. Si sí lo hiciste, lo anotas ahí y recuperas la
  racha (o el escudo que se gastó). Se pregunta una sola vez por día.

Para elegir qué hábitos sigues, sus colores y sus emojis, usa el **⚙️** de la barra
superior.

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
  día aún no termina). Los días de descanso, los cubiertos por un escudo y los de
  vacaciones la **congelan**: no suman ni la cortan.
- **Récord**: tu racha más larga.
- **Escudos 🛡️**: cada 7 días de racha ganas uno, y puedes tener 2. Si un día no anotas
  nada (y no es de descanso ni de vacaciones), se gasta uno solo y la racha sigue. Si
  después anotas ese día, el escudo vuelve. Sin escudos, un día vacío corta la racha.
- **Vacaciones**: en ⚙️, bajo los días de descanso, elige **Desde** y **Hasta** y pulsa
  **Programar pausa**. Se guarda al momento.
  - Empieza hoy o después, nunca en días pasados (para un día que ya pasó están los
    escudos y "¿Olvidaste anotar ayer?").
  - Dura hasta 30 días y no puede cruzarse con otra.
  - Mientras dura, los días sin hábitos congelan la racha. Si marcas algo, cuenta normal.
  - Una que aún no empieza se **cancela**; una en curso se **termina** (queda hasta ayer).
    Las que ya terminaron quedan en tu historial y no se pueden borrar.
  - En Reportes, los días de vacaciones no cuentan entre los que tocaban.

## Proyectos y tareas

Pestaña **Tableros**. También se llega deslizando el dedo hacia la izquierda desde el
calendario. Arriba, **Tablero** muestra las tareas como tarjetas en columnas y **Lista**
las agrupa por proyecto. Lo que sigue describe la **Lista**.

**Crear un proyecto**: el botón **+** de la cabecera "Proyectos". Puedes darle nombre,
descripción, un emoji y un color.

**Ficha del proyecto**: clic sobre su nombre. Muestra todo su tiempo de un vistazo: el
total, las tareas hechas, cuánto lleva cada tarea, cada etiqueta y cada mes. Cuadra con el
total de la tarjeta y con Reportes. También se abre con el **📊** de cada proyecto en
**⚙ Organizar**.

**Editar un proyecto**: desde su ficha, con **✎ Editar**.

**Costeo (plan Maker)**: si tu cuenta tiene el plan Maker y lo enciendes en *Mi perfil ›
Módulos de tu cuenta*, la ficha de cada proyecto trae una tarjeta **Costeo**: cliente,
tarifa por hora, moneda y presupuesto (en dinero, en horas o los dos). Cada dato se guarda
al cambiarlo. La tarjeta calcula la **mano de obra** (horas trabajadas × tarifa) y cuánto
del presupuesto llevas; si un proyecto tiene presupuesto pero todavía no tiene tiempo, lo
marca como **Cotización**.

**Archivar o eliminar**: el botón **⋯** de la tarjeta.

> **Archivar** conserva todo el historial y solo lo esconde de la lista.
> **Eliminar** borra los datos y no se puede deshacer. Ante la duda, archiva.

**Tareas**: despliega el proyecto con la flecha **▾**. Debajo aparecen sus tareas, el
campo *Nueva tarea* para añadir más, y el historial de tiempo.

- La casilla marca la tarea como terminada.
- Junto a cada nombre verás **el tiempo dedicado a esa tarea**.
- El **▶** arranca el cronómetro en esa tarea, sin pasar por los selectores de arriba.
  Mientras corre, la fila queda resaltada. Si ya tenías otro timer en curso, te pregunta
  antes de cambiarlo. En las tareas ya hechas no aparece.
- La línea **"Sin tarea"** recoge el tiempo registrado en el proyecto sin elegir tarea, de
  forma que la suma de todo cuadra con el total de la tarjeta.

## Costos (plan Maker)

Con el plan Maker encendido aparece una cuarta pestaña, **Costos**, para lo que un proyecto
cuesta además de tus horas: licencias, materiales, servicios, tokens de IA…

- **Arriba, el resumen**: costo total, mano de obra, gastos y lo presupuestado; una tabla
  con cada proyecto y su **margen** (presupuesto − costo, en rojo si te pasas), y la
  gráfica **Costos**: una columna para la mano de obra y una por categoría, con su
  porcentaje, sobre un eje de montos a la izquierda que se ajusta solo (su tope queda
  siempre un poco arriba del gasto más alto). Debajo, cada nombre con su cifra exacta;
  tócalo para ocultar o mostrar su columna (solo en la gráfica, los totales no cambian) y
  el eje se reajusta a las que quedan. En el teléfono la tabla enseña solo
  costo y margen. Si tienes proyectos en monedas distintas, cada moneda va aparte: la app
  nunca las suma ni convierte.
- **Abajo, la hoja de gastos** del proyecto elegido (toca su fila en el resumen o elígelo
  en la lista). Se usa como una hoja de cálculo: escribe en las celdas y cada cambio se
  guarda solo; **＋ Agregar fila** para uno nuevo, y Enter baja a la fila siguiente.
- **Traer varios de una vez**: copia las filas en Excel o Google Sheets y pégalas en la hoja
  (Ctrl+V). También puedes **importar un CSV**. Antes de guardar ves una vista previa: las
  filas que no se entienden salen en rojo y se saltan, y si traen una categoría que no
  tienes, puedes crearla. Las columnas pueden llevar encabezado (Fecha, Concepto,
  Categoría, Cantidad, Costo unitario, Nota) o venir en ese orden.
- **Categorías**: vienen cinco (material, licencia/software, servicio, IA y otro) y son
  tuyas: en **Categorías**, al final de la pestaña, las renombras, les cambias el color, las
  ordenas o creas más. Una categoría con gastos no se borra hasta pasar sus gastos a otra.
- Para gastos que no son de un proyecto (una licencia que usas en todo), crea un proyecto
  "Gastos generales". Borrar un proyecto borra sus gastos; archivarlo los conserva.

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
  **⚙ Organizar › ⏱ Configurar pomodoro**. Un pomodoro que ya corre termina con la
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
*Mi perfil › En este dispositivo › Tamaño del texto*.

**En el teléfono todo se ve diminuto, como si fuera la versión de computadora.**
El navegador está en modo **"Sitio para ordenador"** (o "Versión de escritorio"): dibuja la
app como si la pantalla midiera unos 980 px y la encoge. En Chrome: menú ⋮ → desmarca
"Sitio para ordenador" y recarga. Si la tienes instalada y sigue igual, reinstálala desde
el navegador ya sin ese modo.

**Me fui de vacaciones y no lo programé. ¿Perdí la racha?**
Si fueron uno o dos días, tus escudos la cubrieron (si los tenías). Para días más largos,
la pausa se programa antes de irte: no se puede poner hacia atrás.
