# Novedades de Finanzas

Lo que ve quien usa Finanzas al entrar a la página después de una actualización (y en el panel
lateral › Novedades). Mismo formato que NOVEDADES.md (`backend/novedades.py`): corto, para quien la usa,
nunca nada de despliegue. Se escribe en el mismo commit del bump de `FINANCE_VERSION`.

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
