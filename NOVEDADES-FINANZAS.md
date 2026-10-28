# Novedades de Finanzas

Lo que ve quien usa Finanzas al entrar a la página después de una actualización (y en el panel
lateral › Novedades). Mismo formato que NOVEDADES.md (`backend/novedades.py`): corto, para quien la usa,
nunca nada de despliegue. Se escribe en el mismo commit del bump de `FINANCE_VERSION`.

## 0.8.0 — 2026-10-28
### Nuevas funciones
- **Aviso del pago de tu tarjeta**: cuando se acerca la fecha límite y aún debes algo, la tarjeta se
  pone roja y la campana te lo recuerda con *Pagar*; elige 3 o 5 días en Configuración › Avisos.
- **Dar de baja una tarjeta**: desde su menú; anota desde dónde la pagaste (o a dónde va el saldo a
  favor) y qué pasa con sus fijos, y queda archivada con su fecha.
### Cambios
- **La versión de Finanzas**, al pie del panel lateral.

## 0.7.0 — 2026-10-27
### Nuevas funciones
- **Buscar en Movimientos**: con la lupa de arriba, filtra por texto, tipo, cuenta o categoría;
  arriba de la lista ves cuántos son y cuánto suman.
- **La cuenta de siempre**: al anotar, la app propone la cuenta que sueles usar con esa categoría
  y se va adaptando sola.
### Cambios
- **Rendimiento más claro**: cada tasa es una línea con ✎ para editarla; *Anotar* dice la cifra
  de tu banco cuando la escribes.
- **Anotar varios seguidos**: el botón para guardar responde al momento.

## 0.6.0 — 2026-10-26
### Nuevas funciones
- **Apartados**: separa tu ahorro dentro de una cuenta (menú de la cuenta › Apartado); la cuenta
  enseña su total y lo que tienes a la vista.
- **Rendimientos**: ponle su tasa a una cuenta o apartado (menú › Rendimiento); la app calcula lo
  ganado día a día y lo anotas con un toque, o con la cifra de tu banco.
- **Plazos fijos y cuentas de inversión**: CETES, pagarés, tu casa de bolsa o tu exchange, en
  Cuentas › Inversiones; al vencer un plazo, su rendimiento se anota solo.
- **Notas**: lo que quieras a la mano (como el prompt con el que una IA lee tus estados de cuenta),
  con el botón a la izquierda de la campana y *Copiar*.
### Cambios
- **Avisos pegados a la campana**: ya no salen desde abajo.
- **Sumas al subir un estado de cuenta**: cargos, abonos y la diferencia, para cuadrarlos con tu
  banco; y tus tarjetas guardan su tasa de interés, de referencia.

## 0.5.0 — 2026-10-19
### Nuevas funciones
- **Ordena tu presupuesto**: con el lápiz de arriba, toca un grupo y luego otro para cambiarlos
  de lugar; en computadora, también arrastrándolos.
### Cambios
- **Presupuesto en cuadrícula**: tus grupos se ven lado a lado (en el teléfono, de dos en dos).
- **+ Agregar**: en cada grupo, para un gasto, un ahorro o una inversión.
- **Tarjetas más compactas**: lo que pagar y antes de cuándo, en menos espacio.

## 0.4.0 — 2026-10-18
### Nuevas funciones
- **Presupuesto**: planea tu mes con tu ingreso y grupos con su parte (empieza con 50/30/20 o
  con los tuyos); anota lo que cuesta vivir y haz fijos los pagos seguros.
- **Lo que viene**: los fijos que aún no llegan, como la renta, salen en Movimientos en su día
  como programados.
- **Avisos**: una campana arriba a la derecha con los anuncios y mensajes para tu cuenta.
- **Novedades de Finanzas**: lo nuevo de cada versión, aquí mismo y en el menú de tu inicial.
### Cambios
- **Todo en el menú de tu inicial**: Configuración, Datos y el aviso de privacidad se abren ahí
  mismo, con ‹ para regresar.

## 0.3.0 — 2026-10-18
### Nuevas funciones
- **Meses sin intereses como en tu estado de cuenta**: en el menú de la tarjeta, cópialos de la tabla
  del banco (monto original, pendiente, pago requerido y "11 de 12").
- **Lo que te queda de cada compra a meses**: en grande, en el *Estado de cuenta* de la tarjeta, y cada
  mensualidad sale en Movimientos en su día de corte.
### Cambios
- **Colores**: lo que entra en verde, lo que sale en rojo y lo que pasa entre tus cuentas en gris.
- **Tarjetas más limpias**: a la vista, solo cuánto pagar; lo demás, en *Detalle*.

## 0.2.1 — 2026-10-18
### Nuevas funciones
- **Estado de cuenta de cada tarjeta**: toca la tarjeta y luego *Estado de cuenta* para ver de dónde
  sale lo que hay que pagar, anotar tus meses sin intereses y escribir la cifra de tu banco.
### Cambios
- **El pago correcto**: una tarjeta que diste de alta después de su corte ya enseña el pago de ese corte.
- **Tu saldo inicial en Movimientos**: sale en su día, sin contar como ingreso.

## 0.2.0 — 2026-10-17
### Nuevas funciones
- **Menú de cada cuenta**: tócala para editarla, ajustar su saldo, ver solo sus movimientos o anotar
  desde ella; en una tarjeta, pagarla o anotar meses sin intereses que ya traías.
- **Tus datos**: con tu inicial, arriba a la izquierda, **Datos** exporta tus movimientos a CSV o importa
  varias cuentas de una vez.
### Cambios
- **Tarjetas más claras**: pasado el pago, enseñan el siguiente corte, y puedes escribir lo que pide tu
  banco para no generar intereses.
- **El saldo inicial es de un día**: los movimientos viejos que cargues después quedan como historial.

## 0.1.0 — 2026-10-17
### Nuevas funciones
- **Finanzas (en prueba)**: tus cuentas, tarjetas y gastos en una página aparte, con el saldo de cada
  cuenta y cuánto pagar de tu tarjeta para no generar intereses. Por ahora, solo por invitación.
