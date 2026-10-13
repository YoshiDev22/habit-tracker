# Aviso de privacidad y "Descargar mis datos" (BACKLOG 39, versión 1.28)

Plan y borrador del texto. Decidido el 2026-10-13. No es asesoría legal: es un aviso
escrito contra el texto vigente de la ley y lo que la app de verdad guarda, para revisarlo
antes de publicarlo.

## La ley que aplica

**Ley Federal de Protección de Datos Personales en Posesión de los Particulares**, publicada
en el DOF el 20 de marzo de 2025 (abrogó la de 2010), última reforma DOF 14-11-2025. La
autoridad es la **Secretaría Anticorrupción y Buen Gobierno** (art. 2, fr. XV). Texto
vigente: <https://www.diputados.gob.mx/LeyesBiblio/pdf/LFPDPPP.pdf>.

Lo que pide y cómo se cumple aquí:

| Artículo | Pide | En la app |
|---|---|---|
| 15 | Contenido mínimo: identidad y domicilio del responsable; datos tratados (y cuáles son sensibles); finalidades; cómo limitar su uso; cómo ejercer los derechos ARCO; cómo se avisan los cambios | La página `/privacidad` |
| 16, fr. II | Al recabar por medios electrónicos, un aviso **simplificado** (fr. I a IV del art. 15) con el sitio del integral | Bajo el formulario de registro |
| 7 | El consentimiento tácito vale si el aviso se puso a disposición y no hay oposición | Sin casilla: el aviso simplificado y su enlace, antes de crear la cuenta |
| 2, fr. XII y XX; 35 | Quien trata datos por cuenta del responsable es *persona encargada*; comunicarlos a ella no es transferencia | El proveedor del servidor, Cloudflare y el proveedor de IA se nombran como encargados; no hay transferencias |
| 29 | Designar quién atiende las solicitudes | El contacto de la instancia (`PRIVACY_EMAIL`) |
| 31 | Responder en 20 días hábiles y hacerlo efectivo en 15 más | En el aviso |
| 32 | El acceso se cumple también con documentos electrónicos | **Descargar mis datos** (JSON) |
| 34 | ARCO gratuito | En el aviso |
| 1, fr. II | Exceptúa solo el uso exclusivamente personal | No aplica: cualquiera puede registrarse |

**Decisión del responsable de la instancia principal (2026-10-13), opción B.** El responsable
se identifica con su nombre de desarrollador, la instancia, la ciudad y el estado, y un correo
que se responde; sin nombre
legal ni domicilio completo. El art. 15, fr. I, pide "identidad y domicilio": esta forma
identifica a alguien localizable, pero no es una identidad legal ni un domicilio, y es un
riesgo que el responsable asume para un proyecto personal sin cobro. Si la app crece o cobra: nombre
y un domicilio para notificaciones. Se agrega, como complemento (no como sustituto), que usar
la app es voluntario.

**Por qué los datos del responsable no van en el repo.** El repo es público y cualquiera
puede montar su instancia: el aviso describe *lo que hace el código* (igual para todas) y
deja *quién responde* a cada instancia, en `backend/.env`:

```
PRIVACY_OWNER=<nombre o alias de quien administra la instancia>
PRIVACY_LOCATION=<ciudad, estado, país>
PRIVACY_EMAIL=privacidad@…
PRIVACY_HOSTING=<proveedor del servidor y su país>
```

Sin `PRIVACY_OWNER` o `PRIVACY_EMAIL`, la página se sirve igual con un recuadro "Esta
instalación aún no tiene responsable ni contacto" (y la app arranca: no es un error de
despliegue). El proveedor de IA sale de `AI_BASE_URL`/`AI_MODEL`, que ya están en el `.env`.

## Lo que guarda la app (revisado en el código el 2026-10-13)

| Dato | Para qué | Cuánto tiempo |
|---|---|---|
| Correo; contraseña solo cifrada (bcrypt); alias, nombre y apellido opcionales | La cuenta | Mientras exista |
| Hábitos, notas, días de descanso y vacaciones; tableros, tareas, checklist, comentarios, etiquetas; registros de tiempo; proyectos y costeo (cliente, tarifa, gastos); reportes guardados; huso, país y días libres | Lo que la app hace | Mientras exista la cuenta |
| Fecha de registro y última actividad (como mucho una vez por hora) | Administrar la instancia | Mientras exista |
| Reportes de problemas: el texto y, si se deja, versión, pestaña, pantalla, navegador y errores de la sesión | Arreglar fallos | Mientras exista la cuenta |
| Eventos de seguridad: tipo, hora, IP completa, cuenta si la hay | Detectar abusos | 30 días |
| Conteo de textos de IA (sin contenido) | El límite diario | Mientras exista la cuenta |
| Log del servidor (journald): IP y ruta de cada petición | Técnico | Hoy sin plazo: **dejarlo en 30 días** (`MaxRetentionSec`, pendiente del VPS) |
| Copias de respaldo de la base | Recuperarse de una falla | Hoy a mano, sin plazo: **30 días** (pendiente del VPS) |
| En el navegador (`localStorage`): sesión, tema, tamaño de letra, pestaña y tablero elegidos, cronómetro en curso y la cola de envíos | Que la app funcione en ese dispositivo | Hasta cerrar sesión o borrarlos; nunca salen del dispositivo salvo lo que la app envía |

**A terceros:** nada se vende ni se comparte para publicidad. Encargados: **el proveedor del
servidor** (`PRIVACY_HOSTING`), **Cloudflare** (red y protección: ve la IP y el tráfico) y,
solo con el módulo de IA encendido, **el proveedor de IA** de la instancia (`AI_BASE_URL` y
`AI_MODEL`, p. ej. Cloudflare Workers AI), que recibe las cifras del reporte en minutos, los nombres de proyectos, hábitos y etiquetas y las
notas del periodo; **nunca el correo, el nombre ni el cliente** (`ai_payload()`). Con Workers AI,
Cloudflare dice que ese contenido no se usa para entrenar modelos ni se comparte con otros
clientes (<https://developers.cloudflare.com/workers-ai/platform/data-usage/>); no publica
cuánto lo conserva, y el aviso no lo afirma. Con otro proveedor, el aviso dice lo que ese
proveedor publique. Los festivos se piden a Nager.Date solo con país y año.

**Lo que no hay:** analítica, cookies de terceros, fuentes o scripts de otros sitios
(`index.html` no carga nada externo), correos de la app.

**Datos sensibles:** la app no los pide. Si alguien escribe uno (un hábito de salud, una
nota), se trata como el resto: solo para enseñárselo y, con la IA encendida, en el texto de
su reporte.

## Descargar mis datos

`GET /api/auth/me/export` devuelve un JSON con **cada tabla que tenga `user_id`**, el mismo
recorrido de `purge_user()`: una tabla nueva queda cubierta sola, y una prueba exige que todo
lo que borra `purge_user()` salga en el export. Más la fila de `users` sin `hashed_password` ni
`token_version`. Sale tal cual está guardado (fechas en ISO, UTC naive como en la base), con
`exported_at`, la versión y una nota de qué es cada tabla.

- Las filas de `security_events` sin cuenta (solo IP) no son de nadie: no salen.
- `feedback.admin_note` (la nota interna del panel) **sí sale**: es un dato sobre la persona,
  y el derecho de acceso la alcanza. El panel lo dirá junto al campo.
- Límite: 5 descargas por cuenta al día (cuenta en el mismo esquema que los reportes de
  problemas) y el evento `export_limit` en seguridad si se pasa.
- En *Mi perfil*, una fila **Descargar mis datos** (menú de desglose) con qué trae y un botón;
  el archivo se llama `habit-tracker-datos-AAAA-MM-DD.json`.

## Dónde se ve

- **`/privacidad`**: página propia, sin sesión, con el tema y el tamaño de letra de la app,
  servida con su ruta en `main.py` (como todo archivo). Fecha de "Última actualización".
- **Registro**: bajo el botón, el aviso simplificado (responsable, datos, para qué, cómo
  limitar) y el enlace al integral.
- **Mi perfil › Aviso de privacidad** y **Mi perfil › Descargar mis datos**.
- **Cambios al aviso**: se publican con su fecha y un aviso 📢 a todas las cuentas
  (`scripts/announce.py` o el panel); un cambio de finalidades pide de nuevo el consentimiento
  (art. 11).
- `GUIA-DE-USO.md` enlaza el aviso en su pregunta frecuente de seguridad.

## Borrador del texto

Los `{{…}}` vienen del `.env` de la instancia.

> ### Aviso de privacidad
> *Última actualización: AAAA-MM-DD*
>
> **Quién responde por tus datos.** Esta instalación de Habit Tracker la administra
> {{PRIVACY_OWNER}}, desde {{PRIVACY_LOCATION}}. Para cualquier duda o solicitud sobre tus
> datos: {{PRIVACY_EMAIL}}. Habit Tracker es un proyecto personal y de código abierto; usarlo
> es voluntario y gratuito.
>
> **Qué datos guardamos.** Tu correo y tu contraseña (solo cifrada: nadie puede leerla), y si
> quieres, alias, nombre y apellido. Todo lo que anotas en la app: hábitos y notas, tableros y
> tareas, el tiempo que registras, tus proyectos y sus costos, y los reportes que se generan.
> Además, para administrar y proteger la app: la fecha en que te registraste, tu última
> actividad, los problemas que nos reportes (con los detalles técnicos solo si los dejas) y,
> cuando algo falla o parece un abuso (una contraseña equivocada, demasiados intentos), la
> hora y la dirección IP desde la que llegó. La app no te pide datos sensibles (de salud,
> creencias u otros); si escribes alguno, se trata igual que el resto.
>
> **Para qué.** Solo para que la app funcione para ti: guardar lo que anotas, calcular tus
> rachas, tiempos y reportes, mantener tu cuenta segura y arreglar fallos. No vendemos ni
> compartimos tus datos, no hay publicidad ni analítica, y no usamos tus datos para nada más.
> Si algún día quisiéramos usarlos para otra cosa, te lo pediríamos antes.
>
> **Quién más los ve.** Nadie más los usa para sí. Los tratan por nuestra cuenta, sin poder
> usarlos para otra cosa: {{PRIVACY_HOSTING}}, donde vive la app; Cloudflare, que la protege y
> ve tu dirección IP y tu tráfico; y, solo si enciendes la IA para tus reportes, el modelo
> {{AI_MODEL}} en {{AI_PROVIDER_NAME}}, que recibe las cifras del reporte, los nombres de tus
> proyectos, hábitos y etiquetas y tus notas del periodo, **nunca tu correo ni tu nombre**.
> {{AI_PROVIDER_NAME}} dice que eso no se usa para entrenar modelos.
>
> **Cuánto tiempo.** Mientras tengas tu cuenta. Los eventos de seguridad y los registros
> técnicos del servidor se borran a los 30 días, y las copias de respaldo también. Al borrar
> tu cuenta se borra todo lo tuyo; en las copias de respaldo desaparece a los 30 días.
>
> **Cómo limitar su uso.** Apaga la IA o cualquier módulo en *Configuración › Módulos*; quita
> los detalles técnicos al reportar un problema; y deja vacíos alias, nombre y apellido si no
> quieres darlos.
>
> **Tus derechos (acceso, rectificación, cancelación y oposición).** Puedes hacerlo tú mismo:
> *Mi perfil › Descargar mis datos* te da todo lo que guardamos de ti; *Mi perfil › Datos
> personales* los corrige; y *Mi perfil › Borrar mi cuenta* lo borra todo, al momento o en 30
> días. Para lo demás, u oponerte a algún uso, escríbenos a {{PRIVACY_EMAIL}} desde el correo
> de tu cuenta, diciendo qué pides. Te respondemos en un máximo de 20 días hábiles y, si
> procede, lo hacemos en los 15 siguientes. Es gratis. Si no te respondemos o no estás de
> acuerdo, puedes acudir a la Secretaría Anticorrupción y Buen Gobierno.
>
> **En tu navegador.** La app guarda en tu dispositivo tu sesión y tus preferencias (tema,
> tamaño de letra, la última pestaña) y el cronómetro en curso. No usa cookies de terceros.
>
> **Si cambia este aviso.** Lo verás aquí con su fecha y te avisaremos en la campanita 📢 de
> la app.
>
> *Ley Federal de Protección de Datos Personales en Posesión de los Particulares (DOF
> 20-03-2025).*

**Aviso simplificado (registro):**

> Tus datos los administra {{PRIVACY_OWNER}} ({{PRIVACY_LOCATION}}) solo para que la app
> funcione para ti: tu correo, lo que anotas y, para protegerla, la IP cuando algo falla. No
> los vendemos ni los compartimos. Puedes limitar su uso desde *Configuración*. Lee el
> [aviso de privacidad completo](/privacidad).

## Pendientes fuera del código

- El responsable: el correo de contacto (Cloudflare Email Routing reenvía `privacidad@…` a su
  bandeja; para *responder* desde esa dirección hace falta además un "enviar como").
- VPS: journald a 30 días y respaldo diario con 30 días (ya en el Acordeón, Pendientes).
- Leer el Reglamento: el transitorio Décimo Segundo daba 90 días para armonizarlo; no se
  comprobó si ya hay uno nuevo.
