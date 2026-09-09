# Guía de uso

Cómo se usa la app desde el navegador. Para instalarla o levantarla en local, eso está en
[README.md](README.md); esto es el manual de la web ya funcionando.

Producción: https://habits.yoshidev22.com

---

## Índice

- [Entrar por primera vez](#entrar-por-primera-vez)
- [Tu perfil y el alias](#tu-perfil-y-el-alias)
- [Calendario de hábitos](#calendario-de-hábitos)
- [Proyectos y tareas](#proyectos-y-tareas)
- [Pomodoro](#pomodoro)
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

## Calendario de hábitos

La pestaña **Calendario** es la vista de inicio.

- **Flechas `<` y `>`**: cambiar de mes.
- **Clic en un día**: se abre un panel con tus hábitos; púlsalos para marcar o desmarcar
  lo que hiciste ese día.
- **Barra de progreso**: porcentaje de cumplimiento del mes que estás viendo.
- **🔥 Días seguidos**: tu racha actual.
- **Métricas → Este mes**: cuántas veces cumpliste cada hábito.

Para elegir qué hábitos sigues, sus colores y sus nombres, usa el **⚙️** de la barra
superior.

## Proyectos y tareas

Pestaña **Proyectos**. También se llega deslizando el dedo hacia la izquierda desde el
calendario.

**Crear un proyecto**: el botón **+** de la cabecera "Proyectos". Puedes darle nombre,
descripción, un emoji y un color.

**Editar un proyecto**: clic sobre su nombre.

**Archivar o eliminar**: el botón **⋯** de la tarjeta.

> **Archivar** conserva todo el historial y solo lo esconde de la lista.
> **Eliminar** borra los datos y no se puede deshacer. Ante la duda, archiva.

**Tareas**: despliega el proyecto con la flecha **▾**. Debajo aparecen sus tareas, el
campo *Nueva tarea* para añadir más, y el historial de tiempo.

- La casilla marca la tarea como terminada.
- Junto a cada nombre verás **el tiempo dedicado a esa tarea**.
- La línea **"Sin tarea"** recoge el tiempo registrado en el proyecto sin elegir tarea, de
  forma que la suma de todo cuadra con el total de la tarjeta.

## Pomodoro

Está arriba de la pestaña Proyectos.

1. Elige el modo: **Enfoque** (25 min), **Descanso** (5 min) o **Descanso largo** (15 min).
2. Opcionalmente elige **proyecto** y **tarea**. Hazlo *antes* de darle a Iniciar: es en
   ese momento cuando el timer se queda con esa elección.
3. **Iniciar**. Puedes **Pausar** y retomar, o **Detener** para cortar antes de tiempo.

Detalles que conviene saber:

- **Solo se guardan las sesiones de Enfoque.** Los descansos no cuentan como trabajo.
- Si detienes antes del **primer minuto**, la sesión se descarta en vez de guardarse.
- El contador sigue corriendo aunque cambies de pestaña, y aparece en el título de la
  ventana y en una barra inferior.
- **Al terminar suena un aviso aunque estés en otra pestaña.** Son dos pitidos cortos.
- La primera vez que le des a Iniciar, el navegador te pedirá permiso para
  **notificaciones**. Si aceptas, además te avisa el sistema con el navegador de fondo,
  que es lo útil para enterarte de que toca descansar.
- El **🔊** silencia o reactiva el pitido.

Las duraciones no se pueden cambiar todavía (ver entrada 13 del [BACKLOG.md](BACKLOG.md)).

## Registrar tiempo a mano

Para cuando trabajaste sin arrancar el timer. Es lo que convierte la app en una bitácora
y no solo en un pomodoro.

1. En la tarjeta del proyecto, pulsa **⏱**.
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

- **⏱** lo midió el cronómetro.
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
Sí, el diseño se adapta y se cambia de pestaña deslizando el dedo. Todavía no es una app
instalable (ver entrada 9 del [BACKLOG.md](BACKLOG.md)).
