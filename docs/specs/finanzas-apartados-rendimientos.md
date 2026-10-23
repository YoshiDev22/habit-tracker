# Spec: Finanzas — apartados y rendimientos

> Base: Finanzas 0.5.0 (Habit Tracker 1.31.0) · Planteado el 2026-10-23 · Va en una sola versión
> de Finanzas junto con el aviso de pago de tarjeta (BACKLOG 45), con **una sola migración**.

## El problema

Una cuenta como la de un banco digital tiene el dinero **a la vista** y, aparte, **apartados**
de ahorro. Los dos ganan rendimiento **diario y sin plazo** (por ejemplo, 12 % anual a la vista y
15 % en los apartados), y el dinero se mueve entre ellos en cualquier momento. Hoy en Finanzas una
cuenta es un solo saldo, y el rendimiento hay que ajustarlo a mano cada vez que se revisa.
También hay inversiones **a plazo fijo** (CETES, pagarés): un monto, una tasa y unos días en los
que el dinero no se puede usar.

## Decisiones (2026-10-23)

- **Un apartado es una cuenta hija** (`fin_accounts.parent_id`). Mover dinero entre la cuenta y
  un apartado es una **transferencia** normal: el saldo, Movimientos, importar y exportar
  funcionan sin cambios. "Todas las cuentas" suma cada cuenta una vez.
- **El rendimiento diario se enseña como estimado y se anota con un botón.** Nada entra solo
  al saldo: la cuenta dice "Rendimiento estimado desde el 1 oct: $84.12" y *Anotar rendimientos*
  crea un ingreso con esa cifra, o con la que diga el banco si el usuario la corrige.
- **Tope opcional**: la tasa se paga hasta un monto ("hasta $25,000"); lo que pasa de ahí no gana.
- **Sin retención de ISR** por ahora: se anota lo que el banco deposita, y la cifra se corrige
  con la del banco si difiere.
- Habit Tracker no cambia: es solo de Finanzas (`FINANCE_VERSION`).

## Apartados

- Un apartado cuelga de una cuenta de **efectivo o débito** que no es apartado (un solo nivel).
  Toma la **moneda y el tipo** de su cuenta madre; no puede ser de crédito.
- Una cuenta con apartados no se vuelve de crédito ni cambia de moneda (409), no se archiva
  mientras tenga apartados activos (409) y no se borra mientras tenga apartados (409).
- Un apartado puede volverse cuenta suelta (`parent_id: null`) y una cuenta suelta sin apartados
  puede volverse apartado de otra (misma moneda).
- `GET /accounts` trae `parent_id`. En *Cuentas*, la cuenta madre enseña **su total** (a la vista
  más sus apartados) y debajo, con sangría, *A la vista* y cada apartado con su saldo.
- La hoja de una cuenta ofrece *¿Es un apartado de…?* con las cuentas que pueden ser madre, y el
  menú de una cuenta con apartados, *Agregar apartado* y *Mover dinero* (la transferencia).

## Rendimiento diario (sin plazo)

Tabla **`fin_yield_rates`**: `user_id`, `account_id`, `from_date`, `rate_bp` (tasa anual en
puntos base: 1500 = 15 %, de 0 a 10 000), `cap_cents` (NULL = sin tope), `day_basis` (365 o 360;
por defecto 365) y `created_at`. Una fila por cuenta y fecha (única): la tasa vale **desde su
fecha hasta la siguiente**, así que un cambio de tasa del banco no reescribe lo anterior.
`rate_bp = 0` es "desde aquí ya no gana".

**El estimado** (`yield_estimate()` en `backend/finance_yield.py`), día por día:

- Empieza el día siguiente al último rendimiento anotado de la cuenta (un movimiento con
  `source = "yield"`), o en la primera tasa (o el día del saldo inicial, el que sea después).
- Termina **ayer**: el banco paga el día cuando termina.
- Cada día gana `min(saldo, tope) × tasa ÷ base` sobre el saldo al cierre del día, y lo ganado
  **se suma al saldo** de los días siguientes (interés diario compuesto, como lo pagan).
- En centavos, con `Decimal` y `ROUND_HALF_UP` solo al final (no día por día, que sumaría error).

**Anotar** (`POST /accounts/{id}/yield`, `{amount_cents?, tx_date?}`): un ingreso en la cuenta,
categoría **"Rendimientos"** (de ingreso; se crea la primera vez si no existe), `source = "yield"`,
concepto "Rendimientos". Sin monto, el del estimado; con monto, el del banco. Sin fecha, hoy. Con
monto 0 o sin tasa, 422. El siguiente estimado empieza al día siguiente.

`GET /accounts` trae, por cuenta con tasa: `yield_rate_bp` (la de hoy), `yield_cap_cents`,
`yield_since` y `yield_estimate_cents`. `GET`/`PUT /accounts/{id}/yield-rates` lista y pone una
tasa desde una fecha; `DELETE /accounts/{id}/yield-rates/{rate_id}` quita una.

## A plazo fijo

Tabla **`fin_terms`**: `user_id`, `account_id` (la cuenta o apartado donde vive el dinero),
`principal_cents`, `start_date`, `days` (1 a 3650), `rate_bp`, `day_basis` (360 por defecto, como
CETES y pagarés), `on_maturity` (`stay | return | renew`), `return_account_id` (con `return`),
`matured_tx_id` y `created_at`.

- Rendimiento = `capital × tasa × días ÷ base`, con `ROUND_HALF_UP`. Vence el
  `start_date + days`.
- Al vencer, `generate_due()` (el mismo que anota los fijos, perezoso al pedir datos) anota el
  ingreso del rendimiento en la cuenta con `source = "yield"`. Con `return`, además una
  transferencia de capital + rendimiento a `return_account_id`. Con `renew`, un plazo nuevo
  desde el vencimiento con capital + rendimiento. Una vez (lo marca `matured_tx_id`).
- Mientras está abierto, la cuenta dice "No disponible: $X hasta el 15 nov".
- El dinero entra al plazo con una transferencia que hace el usuario; la app no la crea al dar
  de alta el plazo (puede venir de cualquier cuenta, o ya estar ahí).

## Impacto en producción

- **Migración**: `fin_accounts.parent_id` en `scripts/migrate.py` (`new_table: True`, como las
  otras de `fin_accounts`). Correr `migrate.py` **antes** de reiniciar: sin ella la app no arranca.
- Tablas nuevas (`fin_yield_rates`, `fin_terms`): las crea `create_all()`. Con `user_id`, así que
  `purge_user()` y *Descargar mis datos* las cubren solas.
- El aviso de privacidad no cambia: no hay un dato nuevo que salga a un tercero.

## Fases (todas en la misma versión)

1. Apartados: columna, reglas, `GET /accounts` y la pantalla de Cuentas.
2. Rendimiento diario: tasas, estimado, anotar, y su página en el menú de la cuenta.
3. A plazo fijo: alta, vencimiento en `generate_due()` y lo que enseña la cuenta.

## Por decidir

- Si *Anotar rendimientos* se ofrece también para todas las cuentas a la vez.
- Si un plazo de CETES lleva su precio de compra (son a descuento); por ahora, tasa simple.
