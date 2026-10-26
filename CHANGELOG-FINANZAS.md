# Novedades de Finanzas

Qué trae cada versión de Finanzas (la página `/finance`), escrito para quien la usa. Finanzas lleva
su propio número desde 2026-10-18: un cambio solo de Finanzas mueve `FINANCE_VERSION` y no la versión
de Habit Tracker (`VERSION`). Se despliega igual que la app, con el mismo servidor. Cada versión tiene su
tag (`finanzas-v0.1.0`…); las tres primeras se publicaron dentro de una versión de Habit Tracker, que se
indica. Va en 0.x mientras Finanzas esté en prueba por invitación.

Formato: [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). Versionado:
[semver](https://semver.org/lang/es/), con el criterio de la sección *Versionado* de `CLAUDE.md`.

## [0.6.0] — 2026-10-26

Apartados, rendimientos (diarios y a plazo fijo), cuentas de inversión y notas. Lleva migración.

### Nuevo
- **Apartados**: una cuenta de efectivo o débito puede tener apartados de ahorro (menú de la cuenta ›
  *Apartado*). Un apartado toma el tipo y la moneda de su cuenta, y mover dinero entre ellos es una
  transferencia. En Cuentas, la cuenta enseña su total y, debajo, *A la vista* y cada apartado. Una cuenta con
  apartados no se vuelve tarjeta de crédito, ni cambia de moneda, ni se archiva o borra mientras los tenga.
- **Rendimiento diario** (menú de la cuenta › *Rendimiento*): la tasa anual de una cuenta o apartado desde una
  fecha, con tope opcional ("hasta $X") y año de 365 o 360 días. La app estima lo ganado día por día sobre el
  saldo de cada día, y lo ganado también gana, hasta ayer. Nada entra solo al saldo: *Anotar* lo guarda como
  ingreso en la categoría *Rendimientos* (se crea la primera vez), con el estimado o con la cifra del banco. Un
  cambio de tasa vale desde su fecha; 0 % deja de ganar. La lista de cuentas dice lo ganado sin anotar.
- **Plazos fijos** (menú de la cuenta › *Plazo fijo*, o Cuentas › Inversiones): monto, tasa, días y año de 360 o
  365 días, con la vista previa de cuándo vence y cuánto da. Al vencer, el rendimiento se anota solo y el
  dinero se queda, regresa a otra cuenta o se reinvierte; cada vencimiento se anota una sola vez. Mientras está
  abierto, la cuenta dice cuánto no está disponible y hasta cuándo. Al crearlo, *El dinero sale de* anota la
  transferencia que lo mete.
- **Cuentas de inversión**: un tipo de cuenta nuevo, *Inversión* (CETES, una casa de bolsa, un exchange), que se
  porta como débito. *Cuentas › Inversiones* (antes "Próximamente") enseña las cuentas de inversión con su
  total, los plazos fijos (abiertos y vencidos) y las demás cuentas que ganan día a día. La hoja de un plazo
  puede crear la cuenta de inversión ahí mismo.
- **Notas**: en el panel lateral › *Notas* y en un botón a la izquierda de la campana. Cada una con título, texto
  largo (hasta 10,000 caracteres) y *Copiar*; por ejemplo, el prompt con el que una IA lee tus estados de cuenta.
- **Tasa de interés de una tarjeta**, de referencia: en la hoja de la tarjeta; sale en su menú y en Tarjetas. No se
  calcula nada con ella.

### Cambios
- Los avisos de la campana se abren en un panel pegado a ella, no en una hoja que sube desde abajo.
- *Subir estado de cuenta*: debajo de la vista previa salen las sumas de lo que se agregará (cargos, abonos y la
  diferencia) y, aparte, lo que no entra, para cuadrarlo con el banco antes de confirmar.
- Al elegir cuenta en la hoja del monto, un apartado dice de qué cuenta es.
- El aviso de privacidad menciona los datos nuevos de Finanzas: apartados, cuentas de inversión, la tasa de una
  tarjeta, tasas de rendimiento, plazos fijos y notas.

### Para actualizar
- Correr `python3 scripts/migrate.py` **antes** de reiniciar: agrega `fin_accounts.parent_id` y
  `fin_accounts.interest_rate_bp`. Sin ella el servicio no arranca. Las tablas nuevas (`fin_yield_rates`,
  `fin_terms`, `fin_notes`) se crean solas al arrancar.
- Publicar el aviso 📢 del cambio en el aviso de privacidad.

## [0.5.0] — 2026-10-19

El presupuesto en cuadrícula y con orden propio, y tarjetas de crédito más compactas. Sin migración.

### Nuevo
- **Ordenar el presupuesto**: el lápiz de la barra de arriba, en Presupuesto, cambia de lugar dos grupos, o dos
  renglones (también de un grupo a otro) o dos ingresos, tocando uno y luego otro. Con ratón, también se
  arrastran: un grupo cae en el lugar de otro y un renglón antes del renglón donde se suelta, o al final del grupo.

### Cambios
- El presupuesto es una cuadrícula: arriba el ingreso y la tabla del plan, debajo un grupo por tarjeta. En
  computadora la página se ensancha en esa pestaña; en un teléfono van dos grupos por fila.
- En cada grupo se agrega con *+ Agregar* (antes *+ Renglón*), porque no todo es un gasto: ahorro, inversión.
- En *Cuentas › Tarjetas*, cada tarjeta ocupa cerca de un tercio menos: icono mediano, lo disponible en una línea,
  la etiqueta del pago más corta y el botón *Pagar* más chico.

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

[0.6.0]: https://github.com/YoshiDev22/habit-tracker/tree/finanzas-v0.6.0
[0.5.0]: https://github.com/YoshiDev22/habit-tracker/tree/finanzas-v0.5.0
[0.4.0]: https://github.com/YoshiDev22/habit-tracker/tree/finanzas-v0.4.0
[0.3.0]: https://github.com/YoshiDev22/habit-tracker/tree/finanzas-v0.3.0
[0.2.1]: https://github.com/YoshiDev22/habit-tracker/tree/finanzas-v0.2.1
[0.2.0]: https://github.com/YoshiDev22/habit-tracker/tree/finanzas-v0.2.0
[0.1.0]: https://github.com/YoshiDev22/habit-tracker/tree/finanzas-v0.1.0
