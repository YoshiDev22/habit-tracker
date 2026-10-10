# Spec: Finanzas personales

> Base: v1.26.0 (con la 1.27 en curso) · Planteado el 2026-10-09 · Épica 37 del
> [BACKLOG](../../BACKLOG.md). Nada de esto está implementado: es el plan antes de escribir
> código. Va **después de la 1.27** (panel de administración). El esquema es un borrador; su
> impacto en producción se revisa otra vez al empezar cada fase.

## La idea, en limpio

Es fácil gastar sin darse cuenta de cuánto se lleva. La idea es que la app ayude a llevar
las finanzas **sin capturar todo a mano**: que las compras con tarjeta entren solas (de los
correos del banco), que el usuario solo agregue lo que no deja rastro (efectivo,
transferencias sin aviso), que la app diga "hoy llevas 4 compras, ¿te faltó alguna?", y que
avise si **al ritmo que va no alcanza** hasta el siguiente ingreso, con estrategias sacadas de
sus propios datos.

No es Costos (Maker): aquello es el costo de un proyecto que se cobra; esto es el dinero de
la vida diaria. Son módulos distintos y no comparten tablas.

## Decisiones (2026-10-09)

- **Un módulo de esta app, no otra app.** Encaja con el rumbo de módulos
  ([`modulos-y-costeo.md`](modulos-y-costeo.md)) y reaprovecha lo que ya existe: cuentas y
  autenticación, el interruptor de `backend/modules.py`, dinero en centavos con
  `ROUND_HALF_UP` y totales por moneda (`costing.py`), la serie de cobros de los
  recurrentes (`recurring_costs.py`), pegar o importar CSV con vista previa (`parseTable()`
  en `costs.js`), la campanita (`notices.py`), los reportes guardados con IA y su
  validación de cifras (`report_ai.py`), y la idempotencia del pomodoro. Otra app tendría
  que rehacer todo eso.
- **Módulo `finance`, con acceso como `maker`**: `{"enabled": False, "allowed": False}`, y
  se da con `scripts/grant_module.py --module finance` (o desde el panel, fase 2 de la 32).
  En la app se llama **Finanzas**. Su pestaña va entre Costos y Reportes (Reportes siempre
  al final).
- **Tablas nuevas, ninguna columna en tablas existentes**: `create_all()` las crea solas y no
  hay migración. `purge_user()` las borra con la cuenta sin tocarlo, porque todas llevan
  `user_id`.
- **Lo que trae datos de fuera corre fuera de uvicorn**, como `scripts/generate_reports.py`:
  el bot de Telegram es su propio servicio de systemd. El correo no corre en el VPS: un
  Google Apps Script en la cuenta del usuario manda lo que encuentra.
- **La app nunca tiene acceso al Gmail del usuario.** Ni OAuth de Google (exige su
  verificación y es otra superficie de seguridad, como ya se descartó en Costeo) ni IMAP con
  contraseña de aplicación guardada en el VPS.
- **Ayudar, no regañar.** La misma filosofía que la racha: avisos concretos y pocos, nunca
  culpa. Una alerta de ritmo se da una vez por periodo y umbral, no cada vez que se abre la
  app.

## Conceptos

- **Cuenta**: de dónde sale el dinero: efectivo, débito o crédito. Una moneda por cuenta, que
  nunca se convierte; los totales van por moneda.
- **Movimiento**: un gasto, un ingreso o una **transferencia** entre cuentas propias. Monto
  siempre positivo en centavos enteros; el signo lo da el tipo.
- **Tarjeta de crédito**: la **compra** es el gasto, el día que se hace. El **pago de la
  tarjeta** es una transferencia (débito → crédito) y no cuenta como gasto. Si no, todo lo
  pagado con tarjeta contaría dos veces.
- **Fijos**: lo que se repite (renta, teléfono, suscripciones). Usan la misma regla de serie
  que los gastos recurrentes de Costos: cada mes o cada año en el día de inicio, con el fin de
  mes recortado, contando los cobros hechos.
- **Periodo**: mes o quincena (1–15 y 16–fin), según cómo cobre el usuario. La proyección y
  los avisos se miden por periodo.
- **Por confirmar**: lo que llegó solo (correo, Telegram) y no se pudo leer entero, o cuya
  categoría se adivinó. Cuenta en los totales, como las sesiones `needs_review`, y la
  campanita lo pide revisar.

## Cómo entran los datos

```
Correo del banco o CFDI ──► Apps Script (Gmail del usuario) ──► POST /api/finance/ingest  (token de ingesta)
Telegram: "230 tacos efectivo" ──► bot (systemd, long polling) ──► escribe en la base, como generate_reports.py
App: alta rápida · pegar el estado de cuenta ──► /api/finance/...  (JWT de siempre)
```

1. **Correo del banco.** El Apps Script corre cada 15 min con un disparador de tiempo,
   busca correos **solo de los remitentes de la lista** (los avisos de compra del banco),
   manda `{message_id, from, date, subject, text}` y les pone una etiqueta para no volver a
   leerlos. **La lectura se hace en el servidor**, con un parser por banco, versionado y
   probado con correos de ejemplo inventados en `tests/fixtures/`: arreglar un parser cuando
   el banco cambia su formato no obliga a tocar el script de cada usuario. Del correo solo se
   guarda lo leído (monto, comercio, fecha, últimos 4 dígitos); el texto se descarta. Lo que
   ningún parser entiende se guarda como **por confirmar** con el asunto, nunca se tira.
   `message_id` es la `external_id`: mandar dos veces el mismo correo no duplica.
2. **Facturas (CFDI).** Las facturas electrónicas llegan por correo como XML, con total,
   emisor y fecha en campos fijos: son la fuente más confiable. Una factura de una compra que
   ya entró por el aviso del banco **se enlaza, no se duplica**: mismo monto y fecha a ±2 días
   en la misma moneda. Si hay más de un candidato, queda por confirmar.
3. **Telegram, texto primero.** Mensajes como `230 tacos efectivo` o `1,580.50 súper débito`
   se leen con reglas: monto, concepto y, si se nombra, la cuenta (si no, la de por defecto).
   La categoría se adivina por el historial (la última usada con ese concepto). El bot
   contesta con botones *Guardar* y *Editar* antes de guardar. La cuenta se enlaza con un
   código de un solo uso que da *Mi perfil › Conectar Telegram* (vence en 10 min). Habla con
   la API de Telegram por `urllib`, como `backend/ai.py`: sin dependencias nuevas.
   **Fotos de tickets después** (fase 4b): necesitan un modelo que lea imágenes, gastan tokens
   y el ticket sale hacia el proveedor. Solo con el módulo `ai`, con su propio contador.
4. **En la app.** Alta rápida (monto, concepto, cuenta; lo demás opcional) y pegar el estado
   de cuenta una vez al mes para cuadrar, con la vista previa de Costos. Al pegar, lo que ya
   existe (mismo monto, fecha y cuenta) sale marcado como repetido y no se agrega salvo que el
   usuario lo pida.

## Lo que la app dice

- **El día** (pendiente, en la campanita): "Hoy: 3 compras con tarjeta y 1 tuya. ¿Pagaste
  algo en efectivo?" con *Agregar* (abre la alta rápida) y *Está completo* (lo descarta).
  Aparece desde una hora local configurable (21:00 por defecto, con el huso de
  `user_settings`); si no se atiende, a la mañana siguiente es el de ayer. Como los demás
  pendientes, su estado sale de los datos: agregar algo ese día lo resuelve.
- **Por confirmar** (pendiente): un aviso por movimiento que llegó solo y quedó dudoso.
- **Ritmo** (informativo, una vez por periodo y umbral). Con reglas, sin IA:
  - disponible = ingresos del periodo (los registrados, o el esperado si aún no llega)
    − fijos que faltan por cobrar en el periodo − gastos variables;
  - ritmo = gastos variables ÷ días transcurridos, con al menos 3 días (como
    `PROJECTION_MIN_DAYS`);
  - si ritmo × días que faltan > disponible: "A este ritmo el dinero alcanza hasta el día
    26; faltarían $1,200 para el 31". Dice el día y la cifra, no cuánto "debería" gastar.
- **El reporte mensual** (`finance-month`, un tema más en `report_kinds.py`): gasto por
  categoría contra el mes anterior, lo que más creció, la suma de los **gastos hormiga**
  (los pequeños y frecuentes: el umbral se decide con datos reales), fijos y suscripciones,
  y lo que quedó. El texto de reglas sale primero; con el módulo `ai`, la IA escribe las
  estrategias con la misma validación (ninguna cifra que no se le haya enviado) y su propio
  contador en `AI_POOL`.

## Fases

**1 · Módulo y registro a mano.** El módulo `finance`; cuentas, categorías (con las de inicio,
perezosas como las de Costos), movimientos y fijos; la pestaña con la alta rápida, la lista del
periodo y el resumen por categoría y cuenta; pegar el estado de cuenta. *Aceptación:* registrar
efectivo, débito y una compra con crédito más su pago, y que el gasto del mes cuente la compra
una sola vez; casos en `test_isolation.py` y `test_limits.py`; apagar el módulo no borra nada.

**2 · Avisos y ritmo.** Periodo e ingreso esperado en Configuración; los avisos del día, por
confirmar y de ritmo. *Aceptación:* con datos de prueba, el día y la cifra de la proyección
cuadran con la fórmula; el de ritmo no se repite en el mismo periodo.

**3 · Correo.** El token de ingesta, `POST /api/finance/ingest`, el parser del primer
banco, la plantilla del Apps Script (fuera de las rutas servidas) con su guía, y los CFDI con
el enlace a la compra del banco. *Aceptación:* el mismo correo dos veces es un solo
movimiento; un correo que no se entiende queda por confirmar; un CFDI de una compra que ya
existe no la duplica.

**4 · Telegram.** El servicio del bot, el enlace con código y los mensajes de texto (4a); las
fotos con IA (4b). *Aceptación:* un chat sin enlazar no escribe nada; el código no sirve dos
veces ni vencido.

**5 · Reporte mensual.** `finance-month` con texto de reglas y con IA. *Aceptación:* la
validación rechaza un texto que cite una cifra que no se envió.

## Esquema (borrador — avisar el impacto antes de cada fase)

Todo tablas nuevas, sin migración.

| Fase | Tabla | Campos |
|---|---|---|
| 1 | `fin_accounts` | `user_id`, `name`, `kind` (`cash \| debit \| credit`), `currency`, `last4` (opcional), `is_default`, `is_active`, `order` |
| 1 | `fin_categories` | `user_id`, `name`, `color`, `kind` (`expense \| income`), `order`; única por (usuario, nombre) |
| 1 | `fin_transactions` | `user_id`, `account_id`, `kind` (`expense \| income \| transfer`), `amount_cents`, `tx_date` (fecha **local**, como `session_date`), `category_id`, `to_account_id` (transferencias), `concept`, `note`, `source` (`manual \| email \| cfdi \| telegram \| import \| recurring`), `external_id`, `linked_id` (CFDI ↔ compra), `recurring_id`, `needs_review`, `created_at`; única por (usuario, `source`, `external_id`) |
| 1 | `fin_recurring` | Como `recurring_costs`, sin proyecto: cuenta, categoría, monto, frecuencia, `start_date`, `generated` |
| 2 | `fin_settings` | `user_id` único, `period` (`month \| biweekly`), `expected_income_cents`, `currency`, `day_notice_hour` |
| 3 | `ingest_tokens` | `user_id`, `name`, `token_hash`, `created_at`, `last_used_at`, `revoked_at` |
| 4 | `telegram_links` | `user_id`, `chat_id` (único), `linked_at`; y los códigos de un solo uso con su vencimiento |

Antes de la fase 1 se decide si la regla de la serie de los recurrentes se extrae de
`recurring_costs.py` a una función común o se copia: extraerla toca Costos, que ya está en
producción.

## Seguridad

- **El token de ingesta es una puerta nueva de autenticación** (avisar antes de escribirla,
  regla de CLAUDE.md). Solo sirve para `POST /api/finance/ingest`, nunca como JWT; se enseña
  una vez y se guarda su hash (SHA-256 basta: es aleatorio y largo, no una contraseña); se
  revoca desde *Mi perfil*; tiene límite por token y por día, y el cuerpo, tope de tamaño.
- **Nunca números de tarjeta ni CLABE**: como mucho los últimos 4 dígitos. Ni el texto de los
  correos.
- **El bot** solo escribe para el `chat_id` enlazado, y el token del bot vive en
  `backend/.env` (`TELEGRAM_BOT_TOKEN`).
- **El panel de administración** (épica 32) solo cuenta movimientos por cuenta: nunca montos,
  conceptos ni comercios.
- Lo que cambia la infraestructura (respaldos de la base, el servicio del bot) va en el
  documento privado, no aquí.

## Fuera de alcance

Conexión directa a bancos (agregadores tipo Open Finance: costo y regulación), inversiones,
deudas con tabla de amortización, impuestos y declaraciones, conversión entre monedas, y
finanzas compartidas con otra persona (dependería de la épica 21).

## Por decidir

- **De qué banco o bancos** empieza el parser de la fase 3.
- **Quincena o mes** como periodo por defecto, y si el ingreso esperado es uno o varios.
- Las **categorías de inicio** y el umbral de un **gasto hormiga**.
- Si el aviso del día va también por **Telegram** cuando el bot ya está enlazado.
- Qué se le manda a la IA en el reporte: solo categorías y totales, o también los comercios
  más repetidos (como datos, no instrucciones).

## Referencias

- Prelec, D., y Loewenstein, G. (1998). The red and the black: Mental accounting of savings
  and debt. *Marketing Science*, 17(1), 4–28. https://doi.org/10.1287/mksc.17.1.4 — El pago
  "duele" menos cuanto más se separa del consumo, como con la tarjeta de crédito. Sostiene
  que el aviso del día y el de ritmo importen más que las gráficas: ponen el gasto a la vista
  cuando la tarjeta lo esconde.
