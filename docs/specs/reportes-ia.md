# Spec: Reportes automáticos con IA opcional

> Base: v1.19.0 · Planteado el 2026-10-03 a partir de un brief de Yoshio y dos reportes de
> ejemplo (fuera del repo: traen datos personales) · Entrada 30 del [BACKLOG](../../BACKLOG.md).
> Nada de esto está implementado: es el plan acordado antes de escribir código. El esquema
> se revisa otra vez al empezar cada fase.

## La idea, en limpio

Hoy los reportes semanal y mensual los arma Claude con tareas programadas: Yoshio sube a
mano el CSV de tiempo y recibe un Word con métricas, gráficas, observaciones y un cierre.
La meta es que **la app los genere sola**, cada viernes y cada día 1, y los guarde para
compararlos con el periodo anterior.

- **Las cifras las calcula el código**, nunca un modelo de IA.
- **La IA solo escribe el texto** (observaciones, recomendaciones, cierre) a partir de un
  JSON de métricas ya calculadas, nunca de los registros crudos. Así no inventa números,
  cuesta poco y viaja menos información personal.
- **La IA es opcional**: sin ella, el texto sale de reglas y la app funciona completa.
- **Cada usuario elige su proveedor** entre los que tenga configurados la instancia.

**Para quién, por ahora.** Yoshio y quizá algunos conocidos. Lo que haría falta para
abrirlo a más gente queda escrito en *Pendiente*, no se construye ahora.

## Decisiones (2026-10-03)

1. **Proveedores de IA a elegir, con una sola función de llamada.** Cloudflare Workers AI,
   Google Gemini y OpenAI ofrecen el mismo formato de petición (*chat completions*
   compatible con OpenAI), igual que los servidores locales (llama.cpp, LM Studio, Ollama).
   Un solo cliente HTTP con la biblioteca estándar (`urllib`), sin dependencias nuevas,
   cubre a todos; cada proveedor es una URL base, una clave y un modelo:

   | Proveedor | URL base (compatible con OpenAI) | Clave | Costo |
   |---|---|---|---|
   | Cloudflare Workers AI | `https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1` | Token de API de Cloudflare (`Authorization: Bearer`) | 10,000 *neurons* al día gratis; con el plan Workers Paid (5 USD/mes) el excedente cuesta 0.011 USD por 1,000 *neurons* |
   | Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai/` | Clave de Google AI Studio | Hay capa gratuita para los modelos Flash y Flash-Lite. **En la capa gratuita Google usa el contenido para mejorar sus productos**; en la de pago, no |
   | OpenAI | `https://api.openai.com/v1` | Clave de OpenAI | De pago |
   | Local / otro | La del servidor (p. ej. `http://localhost:8080/v1`) | Opcional | 0 por llamada |

   Claude (Anthropic) queda como proveedor opcional aparte: el SDK oficial `anthropic` se
   importa solo si está configurado (dependencia opcional, no en `requirements.txt`).

   **Cuánto cabe en lo gratis (estimado).** Un reporte ronda los 6,000 tokens de entrada y
   3,500 de salida. Con `@cf/openai/gpt-oss-120b` en Cloudflare (31,818 *neurons* por
   millón de entrada y 68,182 por millón de salida) son unos 430 *neurons* por reporte: los
   10,000 diarios gratis alcanzan para ~23 reportes al día. Para unas pocas cuentas, el
   costo de IA es cero.

   **Quién configura qué (decidido 2026-10-03).** Un **solo proveedor por instancia**, en
   `backend/.env` (`AI_PROVIDER`, `AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL`); el de Yoshio, el
   de Cloudflare en su capa gratuita. `backend/.env.example` trae el bloque vacío con los
   valores de cada proveedor comentados, para que quien descargue el repo (o Yoshio, si
   escala) cambie de proveedor sin tocar código.

   **El uso de la IA es un módulo con acceso, como el plan maker.** Módulo `ai` en
   `backend/modules.py`, sin acceso por defecto; lo da `scripts/grant_module.py --module ai`
   a las cuentas que Yoshio elija. Todo endpoint que llame al proveedor empieza con
   `require_module(..., "ai")`: sin acceso, 403, por cualquier enlace o llamada directa a
   la API. Con acceso, el usuario la enciende o apaga en *⚙️ Configuración › Módulos*.

   **Claves propias de cada usuario: no, por ahora.** Guardarlas obliga a tenerlas en la
   base: aunque se cifren, el servidor tiene que poder descifrarlas para usarlas, así que el
   dueño de la instancia (o quien robe la base y el `.env`) podría leerlas, y un error en un
   log las expondría. Para unos pocos conocidos no vale ese riesgo: queda en *Pendiente*.

2. **Limpieza de datos: no se excluye nada, se avisa.**
   - Un cronómetro que llegó al tope de 8 h y no se ha confirmado queda **por confirmar**.
     La app lo avisa con una **campanita en la barra de arriba**, visible en todas las
     pestañas, con el número de pendientes; tocarla lista las sesiones y lleva a corregir o
     confirmar cada una. La campanita servirá después para otros avisos (reporte nuevo).
   - El reporte **cuenta** esas sesiones y lo dice: "Incluye 8 h de «<tarea>» (<fecha>)
     sin confirmar".
   - Las sesiones de más de 4 h, los solapes y las duraciones raras también se cuentan y se
     listan para revisar; el usuario decide.
   - Hoy "cerrada a las 8 h" solo vive en el texto de la nota (`POMO_AUTOCLOSE_NOTE`):
     pasa a ser una columna, `pomodoro_sessions.needs_review`.

3. **Días hábiles con festivos por país, sin estado (decidido 2026-10-03).** Cada usuario
   tiene país (MX por defecto), sin estado ni ciudad: lo particular (un festivo local, un
   puente, vacaciones) lo agrega cada quien como día libre. Los festivos oficiales salen de
   **Nager.Date** (`https://date.nager.at/api/v3/PublicHolidays/{año}/{país}`, gratis y sin
   clave; trae el nombre en español en `localName`; probado el 2026-10-03) y se guardan en
   caché por año. Si el usuario trabaja un festivo, le quita la casilla "Descanso". Google Calendar
   también publica festivos, pero pide una clave de API: queda como alternativa.

4. **PDF lo más parecido al Word de hoy**, generado por el navegador: una vista del reporte
   con hoja de estilos de impresión y gráficas SVG ("Guardar como PDF" del navegador). Sin
   dependencias de PDF ni de Word en el servidor.

5. **Metas: la IA recomienda, el usuario decide.** El reporte trae *Recomendaciones*, que
   son sugerencias; las **metas** las fija el usuario y el reporte mide si se cumplieron.
   Se apoya en la épica 17 (metas).

6. **Costos (versión Maker), lo que falta:**
   - **Tipo de proyecto**: personal, producto o servicio (`project_finance.kind`).
   - **Precio** (`project_finance.price_cents`): lo que se cobra o se cobrará.
   - **Renombrar**: lo que hoy la app llama *margen* (presupuesto − costo) pasa a ser
     **presupuesto disponible**. **Margen** pasa a ser precio − costo, y solo aparece con
     precio.
   - Los gastos (`project_costs`) se quedan como están, y **no se convierte entre monedas**.
   - El punto de equilibrio queda pendiente.

## Fases (cada una se despliega sola)

1. **Export de hábitos (C)** ✅ (2026-10-03, sin publicar). CSV por rango (fecha, hábito, hecho, y si el día fue de
   descanso, vacaciones o cubierto por escudo), junto al "Exportar CSV" de Reportes. El
   export de tiempo por rango ya existe (*Personalizado*).
2. **Sesiones por confirmar** ✅ (2026-10-03, sin publicar). `needs_review` con su migración y relleno desde la nota; aviso
   en la app; confirmar o corregir lo quita. Reportes dice cuánto tiempo sin confirmar está
   contando.
3. **Capa de métricas** ✅ (2026-10-03, sin publicar) (`backend/metrics.py`,
   `GET /api/metrics?date_from&date_to`):
   - Calcula horas reales y brutas, días con registro contra hábiles, promedio y mediana
     por día, duración media por sesión, % registrado a mano, pomodoros cortados, sesiones
     nocturnas (después de las 23 h, hora local), horas en fin de semana, tiempo por
     proyecto, tarea y etiqueta, horario habitual y la lista de lo que hay que revisar.
   - Necesita el huso horario y el país de cada usuario, y los festivos.
   - ⚙️ Configuración › *Días y horario*: huso, país, festivos ("Descanso") y días
     libres propios.
   - La pestaña Reportes sigue con sus cálculos de siempre: pasará a leer de aquí cuando
     la vista de reportes guardados (Fase 4) use las mismas cifras.
4. **Reportes guardados, sin IA.**
   - **Cada reporte tiene su botón** ("Generar reporte de la semana / del mes") para
     hacerlo cuando el usuario quiera, además del automático.
   - Tabla `reports` y un script `scripts/generate_reports.py`, disparado por un
     **systemd timer** (viernes y día 1). No va dentro de uvicorn: con reinicios o varios
     workers dispararía dos veces.
   - Una vista nueva con las secciones de los ejemplos, gráficas SVG con los colores de
     cada proyecto e impresión a PDF.
   - El texto sale de reglas.
5. **IA para el texto.** `backend/ai.py` con la función de llamada única, configurada por
   `backend/.env`, y el módulo `ai` con acceso. En *⚙️ Configuración › Módulos*, quien tiene acceso la
   enciende o apaga y ve el JSON exacto que se enviaría. Si el proveedor falla o se pasa del límite diario, el texto
   sale de las reglas. Respuesta en JSON validado, y se rechaza un texto que cite números
   que no venían en las métricas.
6. **Reporte de costos (Maker), aparte (decidido 2026-10-03).** No se mezcla con el de
   tiempo y hábitos: es **su propio reporte, con su propio botón** en la pestaña Costos
   (horas, mano de obra, gastos, costo, presupuesto disponible y margen del periodo, por
   proyecto y por moneda). Con él llegan el tipo de proyecto y el precio. Requiere filtrar
   `/api/costs/summary` por fechas (entrada 29).

## Esquema (borrador)

| Fase | Cambio | Tipo | Migración |
|---|---|---|---|
| 2 | `pomodoro_sessions.needs_review` (bool), relleno desde la nota de cierre automático | Columna en tabla existente | **Sí**: `migrate.py` + `test_deploy.py` |
| 3 ✅ | `user_settings` (`user_id` único, `timezone`, `country`) | Tabla nueva | No |
| 5 | Módulo `ai` en `backend/modules.py` (usa `user_modules`, que ya existe) | Sin cambio de esquema | No |
| 3 ✅ | `user_days` (`user_id`, `date`, `name`, `kind`: libre o laboral), único por (usuario, fecha) | Tabla nueva | No |
| 3 ✅ | `holiday_cache` (`country`, `year`, JSON de Nager.Date, `fetched_at`) | Tabla nueva | No |
| 4 | `reports` (`user_id`, `kind`: semanal o mensual, `period_start`, `period_end`, `metrics` JSON, `text` JSON, `text_source`: reglas o proveedor, `created_at`) | Tabla nueva | No |
| 6 | `project_finance.kind`, `project_finance.price_cents` | Columnas en tabla existente (desde la 1.18) | **Sí**: `migrate.py` + `test_deploy.py` |

Todas las consultas filtran por `current_user.id`, y cada endpoint nuevo lleva su caso en
`tests/test_isolation.py` y sus topes en `tests/test_limits.py`. Las claves de los
proveedores van en `backend/.env`, nunca en el repo ni en la base.

## Transparencia y privacidad

- Solo las cuentas a las que Yoshio da acceso (`grant_module.py --module ai`) pueden usar
  la IA, y está apagada hasta que el usuario la enciende. El servidor lo comprueba en cada
  llamada (403), no solo la pantalla.
- *⚙️ Configuración* muestra el JSON exacto que se enviaría. Incluye títulos de tareas y nombres de
  proyectos: son texto personal.
- Si la instancia usa Gemini en la capa gratuita, *⚙️ Configuración* avisa que Google usa ese
  contenido para mejorar sus productos.
- Límite de llamadas por usuario y día; si se pasa, el texto sale de las reglas.

## Pendiente (no entra en esta iteración)

- **Punto de equilibrio** (producto: gastos fijos ÷ (precio − costo por unidad); pide
  marcar qué gastos son por unidad y las unidades planeadas o vendidas).
- **Sección Hábitos** del reporte (qué mostrar: días por hábito, racha, escudos usados,
  comparación).
- **Dos monedas.** La forma habitual de llevar cuentas en MXN y USD sin convertir: cada
  gasto se anota en la moneda en que se pagó, y los totales se dan por moneda, nunca
  sumados. Para comparar contra un presupuesto en otra moneda se usa un **tipo de cambio
  que el usuario escribe** (el del día de pago, o el de su estado de cuenta), guardado junto
  al gasto, sin convertir solo. Así un estado de cuenta en USD y otro en MXN cuadran cada
  uno por su lado. Pide una moneda por gasto y un tipo de cambio opcional: se diseña aparte.
- **Entrega por correo o Telegram** (el correo depende de la entrada 26: SMTP y
  verificación).
- **Servidor MCP de solo lectura** (opción B del brief), como capa delgada sobre la capa de
  métricas. Antes, verificar qué autenticación aceptan los conectores personalizados de
  Claude.ai (OAuth o sin autenticación; un token fijo en un header quizá solo sirva en
  Claude Code y Desktop).
- **Para abrirlo a más gente**: varios proveedores a elegir por usuario; que cada usuario
  traiga su propia clave (cifrada en la base, con el riesgo descrito en *Decisiones*),
  cuotas por usuario, festivos de más países con revisión, i18n.

## Fuentes consultadas (2026-10-03)

- Cloudflare Workers AI, precios: <https://developers.cloudflare.com/workers-ai/platform/pricing/>
- Cloudflare Workers AI, endpoint compatible con OpenAI: <https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/>
- Cloudflare, `gpt-oss-120b`: <https://developers.cloudflare.com/workers-ai/models/gpt-oss-120b/>
- Gemini API, compatibilidad con OpenAI: <https://ai.google.dev/gemini-api/docs/openai>
- Gemini API, precios y uso de datos en la capa gratuita: <https://ai.google.dev/gemini-api/docs/pricing>
- Nager.Date: <https://nagerholidays.com/Api> (antes `date.nager.at`)
- Calendarios públicos de festivos en Google Calendar: <https://dev.to/monfernape/get-country-holidays-using-google-calendar-api-3dh6>
