# Novedades de Finanzas

Qué trae cada versión de Finanzas (la página `/finance`), escrito para quien la usa. Finanzas lleva
su propio número desde 2026-10-18: un cambio solo de Finanzas mueve `FINANCE_VERSION` y no la versión
de Habit Tracker (`VERSION`). Se despliega igual que la app, con el mismo servidor. Cada versión tiene su
tag (`finanzas-v0.1.0`…); las tres primeras se publicaron dentro de una versión de Habit Tracker, que se
indica. Va en 0.x mientras Finanzas esté en prueba por invitación.

Formato: [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). Versionado:
[semver](https://semver.org/lang/es/), con el criterio de la sección *Versionado* de `CLAUDE.md`.

## [0.4.0] — 2026-10-18

La primera con su propio número. El presupuesto del mes, los fijos que vienen en Movimientos, la campana
de avisos, las Novedades de Finanzas y todo el panel lateral en un mismo lugar.

### Nuevo
- **Presupuesto** (pestaña nueva): tu ingreso del mes (la primera vez, el de tu sueldo) y grupos con su
  parte en %, cada uno con lo teórico, lo planeado y el dinero que queda sin planear. Empieza con la
  referencia 50/30/20 o con grupos propios. Cada renglón es una estimación o un fijo (*Hacer fijo*).
  El presupuesto nunca crea movimientos.
- **Programados en Movimientos**: el siguiente cobro de cada fijo que aún no llega sale en su día, sin
  sumarse; tocarlo abre tus fijos.
- **Campana de avisos**, arriba a la derecha: los anuncios para todas las cuentas y los mensajes para la
  tuya. El aviso de acceso a Finanzas aquí es una bienvenida. Los avisos de Habit Tracker se quedan en su
  campana.
- **Novedades de Finanzas**: al entrar después de una actualización y en el panel lateral › Novedades. Si
  hay versión nueva con la página abierta, ofrece *Actualizar*.

### Cambios
- El panel lateral abre cada opción dentro de sí mismo (Configuración y sus páginas, Datos, Novedades y
  el aviso de privacidad), con ‹ y Escape para regresar. En computadora no cambia de ancho; en un
  teléfono, una página ocupa la pantalla.
- El aviso de privacidad menciona el presupuesto y la cifra del banco del estado de cuenta.

## [0.3.0] — 2026-10-18

Publicada con Habit Tracker 1.31.0. Meses sin intereses capturados como vienen en el estado de cuenta,
sus mensualidades en Movimientos, lo que queda de cada uno a la vista y colores por tipo de movimiento.

### Nuevo
- **Meses sin intereses como en tu estado de cuenta**: en el menú de una tarjeta, las columnas de la
  tabla del banco (descripción, monto original, saldo pendiente, pago requerido, "11 de 12" y el corte).
  La app arma el plan desde ahí y avisa si el pago requerido o el saldo pendiente no cuadran.
- **Mensualidades en Movimientos**, en su día de corte. Solo se enseñan: la compra, o la deuda inicial,
  ya las contó.
- **Lo que queda de cada compra a meses**, en *Estado de cuenta* de la tarjeta, con una barra de pagos.
- **Colores por tipo**: ingresos en verde, gastos en rojo, transferencias entre tus cuentas en gris.

### Cambios
- En *Cuentas › Tarjetas*, cada tarjeta enseña solo cuánto pagar; lo demás queda tras *Detalle*.
- Los centavos que sobran de una compra a meses van en los últimos pagos, como en los estados de cuenta.
- Los meses sin intereses dicen "10 de 12 pagos".

## [0.2.1] — 2026-10-18

Publicada con Habit Tracker 1.30.1.

### Nuevo
- **Estado de cuenta de cada tarjeta**, desde su menú: cuánto pagar y antes de cuándo, desglosado, con
  la cifra del banco, los meses sin intereses y *Pagar* en la misma pantalla.

### Correcciones
- Una tarjeta dada de alta después de su corte enseñaba el corte siguiente; ahora el pago de ese corte.
- El saldo inicial de cada cuenta (o la deuda inicial de una tarjeta) se ve en Movimientos, sin contar.
- *Importar datos*: un archivo que dice USD en cuentas en pesos saltaba esas filas; la vista previa deja
  tomar la moneda del archivo como la tuya.

## [0.2.0] — 2026-10-17

Publicada con Habit Tracker 1.30.0. Saldos desde un día, tarjetas que pasan al siguiente corte, un menú
por cuenta, exportar e importar tus datos y un panel lateral.

### Nuevo
- **Menú de cada cuenta**: Editar, Ajustar saldo, sus Movimientos, Ingreso, Gasto y Transferencia y, en
  una tarjeta, Pagar y Meses sin intereses.
- **Meses sin intereses que ya traías** en una deuda de antes.
- **El monto del banco** para no generar intereses, que manda sobre el cálculo hasta el siguiente corte.
- **Datos**: exportar los movimientos a CSV e importar un CSV con varias cuentas a la vez.
- **Panel lateral** desde tu inicial, y el 👁 para ocultar el total.

### Cambios
- El saldo inicial es de un día; lo de antes es historial que no mueve el saldo.
- Pasada la fecha límite, la tarjeta enseña el siguiente corte.
- Un solo botón *Subir estado de cuenta*, con un CSV de ejemplo y la vista previa editable.
- El ✎ de la barra de arriba ordena las categorías; Enter guarda también desde la nota.

## [0.1.0] — 2026-10-17

Publicada con Habit Tracker 1.29.0. La primera versión, en prueba y por invitación.

### Nuevo
- **Cuentas** de efectivo, débito y crédito con su saldo; las tarjetas con límite, disponible, corte,
  pago y estado de cuenta.
- **Pagar la tarjeta**, **compras a meses sin intereses** y **dividir un cargo** en varias categorías.
- **Categorías** en un anillo con un teclado calculadora; **fijos** que se anotan solos; el **periodo**
  que elijas y el **resumen** con su gráfica.
- **Pegar un estado de cuenta** o un CSV, con vista previa y sin duplicar.
- El **consentimiento expreso** para guardar datos financieros, la primera vez.

[0.4.0]: https://github.com/YoshiDev22/habit-tracker/tree/finanzas-v0.4.0
[0.3.0]: https://github.com/YoshiDev22/habit-tracker/tree/finanzas-v0.3.0
[0.2.1]: https://github.com/YoshiDev22/habit-tracker/tree/finanzas-v0.2.1
[0.2.0]: https://github.com/YoshiDev22/habit-tracker/tree/finanzas-v0.2.0
[0.1.0]: https://github.com/YoshiDev22/habit-tracker/tree/finanzas-v0.1.0
