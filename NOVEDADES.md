# Novedades

Lo que ve quien usa la app al entrar después de una actualización (y en *Mi perfil ›
Novedades*). No es el CHANGELOG: es corto, para el usuario, y nunca lleva nada de
despliegue. Se escribe en el mismo commit del bump. Formato en `backend/novedades.py`.

## 1.28.1 — 2026-10-15
### Cambios
- **Más privacidad en el servidor**: los registros técnicos de la app ya no guardan tu correo ni los
  nombres de tus gastos, solo un número de cuenta. Se borran a los 30 días, como dice el **aviso de
  privacidad** (en **Mi perfil**).

## 1.28.0 — 2026-10-15
### Nuevas funciones
- **Descargar mis datos**: en **Mi perfil › Descargar mis datos**, un archivo con todo lo que la app
  guarda de tu cuenta. Tu contraseña no va: solo se guarda cifrada.
- **Aviso de privacidad**: qué datos guardamos, para qué y cómo ejercer tus derechos, en **Mi perfil ›
  Aviso de privacidad** y en la pantalla de entrar.
- **Versión nueva**: si la app se actualiza mientras la tienes abierta, una franja arriba te ofrece
  **Actualizar**.

## 1.27.1 — 2026-10-13
### Cambios
- **Al volver a la app**: si la dejaste un rato en otra pestaña o la usaste en otro
  dispositivo, al regresar se ponen al día tus tableros, la lista y los reportes, sin
  recargar la página.
- **Fin de un gasto recurrente**: si le pones un fin anterior a cobros que ya se anotaron, te
  pregunta si los borras o los conservas.
- **Horas de un registro**: al registrar o corregir tiempo a mano, ya no se puede poner una
  hora que todavía no llega.

## 1.27.0 — 2026-10-10
### Nuevas funciones
- **Reportar un problema**: en **Mi perfil › Reportar un problema**, cuéntanos qué falló. Antes
  de enviarlo ves exactamente qué detalles técnicos van con tu texto, y puedes quitarlos.
- **Te avisamos cuando lo revisemos**: al cerrar un problema que reportaste, te llega a la
  campanita con 🛠️, con lo que te queramos decir.
- **Avisos solo para ti**: la campanita también recibe avisos para tu cuenta, con 💬; por
  ejemplo, si te damos más textos de IA por un día.
### Cambios
- **Novedades con fecha**: en **Mi perfil › Novedades**, cada versión dice cuándo salió.

## 1.26.0 — 2026-10-09
### Nuevas funciones
- **Centro de avisos**: la campanita de arriba junta todo lo que te espera: registros por
  confirmar, días sin anotar, reportes listos y novedades. El círculo rojo dice cuántos
  tienes sin ver.
- **Días sin anotar**: si ayer quedó vacío, el aviso trae **Anotar**, que abre ese día, y
  **Descartar** si no lo vas a anotar.
- **Avisos de la app**: cuando haya mantenimiento o algo que debas saber, llega con 📢 a la
  campanita.
### Cambios
- **"¿Olvidaste anotar ayer?"** sigue saliendo al abrir la app, pero si la cierras, el día
  se queda en la campanita para después.

## 1.25.0 — 2026-10-09
### Nuevas funciones
- **Notas del día en tus hábitos**: en el calendario, toca un día y luego **✎** junto a un
  hábito para anotar algo, como "cuerda 20 min". No cambia tu racha, y el día queda marcado
  con un punto.
- **Novedades**: cuando la app se actualice verás esta ventana con lo nuevo. Para volver a
  verla, **Mi perfil › Novedades**.
### Cambios
- **Tus notas en los reportes**: el reporte de hábitos y el CSV de hábitos ya las incluyen.

## 1.24.0 — 2026-10-08
### Nuevas funciones
- **Repartir un gasto entre proyectos** (plan Maker): en Costos, toca **↔** en un gasto y
  elige los proyectos y su porcentaje. Cada proyecto suma solo su parte.
- **Gastos recurrentes** (plan Maker): en Costos › **Gastos recurrentes**, crea los que pagas
  cada mes o cada año. Se anotan solos en su fecha, y con **Editar** cambias su precio o su
  reparto.
- **Volver recurrente un gasto ya anotado**: toca su **🔁** en la hoja; el formulario sale
  lleno.
- **Renombrar un hábito**: en ⚙️ Configuración › Hábitos, toca su nombre y escríbelo de
  nuevo. Conserva sus días y su racha.
### Cambios
- **Columnas más cortas en el tablero**: cada una enseña 10 tarjetas; **Mostrar 10 más**
  carga otras diez.
- **Tareas movidas a la vista**: al cambiar una tarea de columna, queda hasta arriba.
