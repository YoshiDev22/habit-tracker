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

## El texto

El texto aprobado (2026-10-14) vive en `privacidad.html`: el borrador que estaba aquí se
quitó para no tener dos versiones. Decisiones de esa revisión:

- **Responsable**, con estas palabras exactas: "Para conocer la identidad y domicilio del
  responsable del tratamiento, o para ejercer tus derechos ARCO, escribe a {correo}.
  Responderemos a la brevedad." Sin nombre, domicilio ni teléfono (sustituye a la opción B).
- **Nada que sugiera usos futuros**: no "si quisiéramos usarlos para otra cosa…". Los cambios
  se publican con su fecha y se avisan con antelación; el consentimiento se pide "cuando la ley
  lo pida" (art. 11).
- **Descargo aparte**: proyecto en desarrollo, bajo propio riesgo.
- En el registro, solo la línea con el enlace (no el aviso simplificado completo).

## Pendientes fuera del código

- El responsable: el correo de contacto (Cloudflare Email Routing reenvía `privacidad@…` a su
  bandeja; para *responder* desde esa dirección hace falta además un "enviar como"), y las
  `PRIVACY_*` en el `.env` del VPS.
- VPS: journald a 30 días y respaldo diario con 30 días (ya en el Acordeón, Pendientes).
- Leer el Reglamento: el transitorio Décimo Segundo daba 90 días para armonizarlo; no se
  comprobó si ya hay uno nuevo.
