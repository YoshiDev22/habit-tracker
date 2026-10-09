# Spec: Panel de administración y reportes de problemas

> Base: v1.22.1 (con la 1.23 en curso) · Planteado el 2026-10-07 · Épica 32 del
> [BACKLOG](../../BACKLOG.md). Nada de esto está implementado: es el plan acordado antes de
> escribir código. Va **después de la 1.24** (gastos recurrentes y repartidos). El esquema es
> un borrador; su impacto en producción se revisa otra vez al empezar cada fase.

## La idea, en limpio

Yoshio quiere **gestionar y monitorear** la app y sus usuarios sin entrar al VPS ni correr
scripts: cuántas cuentas hay, quién usa qué, cuánto gasta la IA, dar o quitar módulos y
recibir los problemas que reporten los usuarios. **Gestión, no vigilancia:** el panel nunca
enseña lo que escribe cada persona (tareas, hábitos, gastos, textos de reportes).

## Decisiones (2026-10-07)

- **En este repo, como un segundo proceso.** El panel usa los mismos modelos, migraciones y
  pruebas. Un repo aparte que "solo llame APIs" necesitaría igual esas APIs aquí, o leería
  la base directo: dos programas escribiendo el mismo SQLite y un esquema duplicado que se
  desincroniza. Lo separado es el **proceso**: `backend/admin_main.py` crea otra app FastAPI
  que monta solo el router de administración y su página, y corre con su propio servicio de
  systemd escuchando **solo en `127.0.0.1`**.
- **Las rutas de administración no existen en la app pública.** `backend/main.py` nunca
  monta el router de admin: aunque alguien adivine la ruta en el dominio público, recibe 404.
- **Zero Trust delante.** Al proceso de admin solo se llega por un **Cloudflare Tunnel**
  (`cloudflared`) en un subdominio propio, protegido con **Cloudflare Access** (correo de
  Yoshio y MFA). No pasa por Caddy ni abre puertos en `ufw`. Los nombres reales (subdominio,
  tunnel, políticas) van en el documento privado de infraestructura, **no en este repo**.
- **Y verificado dentro de la app.** Cada petición al panel trae el JWT de Access
  (`Cf-Access-Jwt-Assertion`); la app lo valida contra las llaves públicas del equipo de
  Access (`https://<equipo>.cloudflareaccess.com/cdn-cgi/access/certs`, en caché) y comprueba
  que el correo esté en `ADMIN_EMAILS` del `.env`. Sin un JWT válido, 403. Si el tunnel o
  Access quedan mal configurados, el panel sigue cerrado. Sin `ADMIN_EMAILS` el proceso de
  admin no arranca (como `SECRET_KEY`).
- **Nada de "usuario administrador" en la app pública.** Un error de permisos ahí expondría
  a todos los usuarios; separar el proceso quita ese riesgo de raíz.

## Fase 1 · Reportar un problema y panel de solo lectura

**Para los usuarios: "Reportar un problema".** Una fila más en el menú de *Mi perfil*
(drill-down, como las demás), que lleva a su página:

- Un campo de texto (qué pasó, 10 a 2000 caracteres) y una casilla **"Adjuntar detalles
  técnicos"**, encendida por defecto, que **enseña lo que se mandará** antes de enviarlo:
  versión de la app, pestaña abierta, ancho de la pantalla, navegador (`userAgent`) y los
  últimos 10 errores de la consola de esta sesión (un `window.onerror` y un
  `unhandledrejection` que los guardan en memoria, sin datos del usuario).
- `POST /api/feedback` guarda el reporte. Límite: 5 por cuenta al día (429, como el login).
- Al enviar: "Gracias, lo vamos a revisar". Sin correo de respuesta todavía (entrada 26).

**Para Yoshio: el panel, solo lectura.**

- **Resumen:** cuentas totales, nuevas en 7 y 30 días, activas en 7 y 30 días, cuentas con
  borrado programado, reportes de problemas abiertos.
- **Cuentas:** correo, fecha de registro, última actividad, módulos (encendido y acceso),
  conteos de lo que tiene (**solo números**: tableros, tareas, hábitos, sesiones, gastos,
  reportes), uso de IA de hoy y del mes (buenas, fallidas, tokens).
- **IA:** llamadas por día y por contador (reportes / costos), errores más comunes (el
  `error` corto de `ai_calls`, que no lleva datos del usuario), tokens.
- **Problemas reportados:** la lista con su texto, sus detalles técnicos, la cuenta y la
  fecha.

**Lo que el panel no enseña nunca:** títulos de tareas, nombres de proyectos o hábitos,
conceptos de gastos, comentarios, textos de reportes ni sesiones. El router de admin no
importa esos campos: las consultas cuentan filas, no las leen.

## Fase 2 · Acciones, con bitácora

- Dar o quitar acceso a un módulo (`maker`, `ai`): reemplaza a `scripts/grant_module.py`
  (que se queda para emergencias).
- **Más textos de IA hoy** para una cuenta: una fila en una tabla de ajustes (`ai_grants`:
  cuenta, contador, cantidad, día) que el contador suma al límite. No se borran filas de
  `ai_calls`, que son el historial. Se junta con la entrada 31 (límite por cuenta).
- Desactivar o reactivar una cuenta (`users.is_active`), cancelar un borrado programado.
- Cambiar el estado de un problema reportado (abierto → revisado → cerrado) con una nota
  interna.
- **Avisos** (la campanita, desde la 1.26). Una página *Avisos*: publicar uno para todas las
  cuentas (título hasta 80, texto hasta 500, cuánto dura o "hasta terminarlo", con vista
  previa), la lista de vigentes y anteriores con **Terminar**, y desde la ficha de una cuenta
  un aviso solo para ella. Algunas acciones lo mandan solas ("Te dimos 5 textos más de IA
  hoy", acceso a Maker). Publicar vive en una función del backend que usan el panel y
  `scripts/announce.py` (que se queda para emergencias), con las mismas reglas: **como mucho
  3 avisos vigentes** para todas (409) y una espera corta entre dos publicaciones (doble
  clic). El aviso a una cuenta es un tipo nuevo de `notices` (uno por cuenta, tipo y
  referencia): sin migración. La app pública sigue sin ninguna ruta que cree avisos
  (`test_no_account_can_publish_to_every_bell`).
- **Bitácora:** cada acción queda en `admin_actions` (quién, cuándo, qué, sobre qué cuenta,
  antes y después), también publicar, terminar y enviar avisos. El panel la enseña; no se
  edita ni se borra desde la UI.

## Fase 3 · Cloudflare (la hace Yoshio, con una guía)

1. Instalar `cloudflared` en el VPS y crear un tunnel hacia `http://127.0.0.1:<puerto de
   admin>`.
2. Crear la aplicación en Cloudflare Access para el subdominio, con una política que solo
   permita su correo y pida MFA.
3. Poner `ADMIN_EMAILS` y el dominio del equipo de Access (`ADMIN_ACCESS_TEAM`) en
   `backend/.env`, copiar el `.service` de admin desde `deploy/` y activarlo.
4. Comprobar: desde una ventana privada el subdominio pide el login de Access; el dominio
   público responde 404 en las rutas de admin; con `curl` directo al puerto sin JWT, 403.

**El panel no se despliega antes de esta fase.** Las fases 1 y 2 se prueban en local; en
producción solo sale "Reportar un problema" hasta que Access esté listo.

## Seguridad: lo que hay que cuidar

- **XSS hacia el administrador.** El texto de un problema lo escribe cualquier usuario y lo
  lee Yoshio con su sesión de admin. Todo se pinta con `textContent`, nunca `innerHTML`, y
  la página de admin lleva una `Content-Security-Policy` estricta (`script-src 'self'`).
- **CSRF.** Las acciones del panel son `POST`/`PUT` con JSON y el JWT de Access en la
  cabecera; además la app exige `Content-Type: application/json` y un `Origin` igual al del
  subdominio de admin.
- **Mínimo dato:** el panel no tiene endpoints que devuelvan contenido de usuario; una
  prueba lo comprueba (abajo).
- **Datos personales:** los correos se ven en el panel, nunca en logs. Los detalles técnicos
  de un reporte no llevan tokens (el frontend los excluye) y se borran con la cuenta
  (`purge_user()` ya borra toda tabla con `user_id`).

## Esquema (borrador)

| Fase | Cambio | Tipo | Migración |
|---|---|---|---|
| 1 | `users.last_seen_at` (UTC, se actualiza a lo más una vez por hora en `get_current_user`) | Columna en tabla existente | **Sí**: `migrate.py` + `test_deploy.py` |
| 1 | `feedback` (`user_id`, `created_at`, `text`, `details` JSON, `status`, `admin_note`) | Tabla nueva | No |
| 2 | `admin_actions` (`created_at`, `admin_email`, `action`, `user_id`, `before`/`after` JSON) | Tabla nueva | No |
| 2 | `ai_grants` (`user_id`, `pool`, `extra`, `day`) | Tabla nueva | No |

## Pruebas

- `POST /api/feedback`: topes de texto y detalles (`test_limits.py`), límite diario (429),
  aislamiento (`test_isolation.py`) y que `purge_user()` los borre (`test_accounts.py`).
- Admin: sin JWT o con uno inválido, vencido o de un correo fuera de `ADMIN_EMAILS` → 403
  (las pruebas firman JWT con una llave de prueba); la app pública no tiene ninguna ruta de
  admin (404); ninguna respuesta del panel contiene el título de una tarea, el nombre de un
  hábito ni el concepto de un gasto sembrados con marcas únicas.
- Navegador: enviar un problema desde *Mi perfil* con la vista previa de los detalles; el
  panel pinta un texto con `<script>` como texto.

## Decidido al empezar la Fase 1 (2026-10-09)

- **Correos enmascarados** por defecto (`y•••@gmail.com`); la ficha de una cuenta enseña el
  completo al tocarlo. Nunca en logs.
- **"Reportar un problema" solo con cuenta**, en *Mi perfil*: nada de formularios abiertos
  en la pantalla de login (sin superficie para spam).
- **`users.last_seen_at` una vez por hora**, en `get_current_user`: solo escribe si la marca
  tiene más de una hora (o no existe). Columna en `migrate.py`. Toca la autenticación: su
  prueba exige que dos peticiones seguidas no escriban dos veces.
- **Sin capturas de pantalla** con el reporte.
