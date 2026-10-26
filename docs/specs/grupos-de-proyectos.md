# Spec: Grupos de proyectos

> Base: Habit Tracker 1.32.0 · Planteado el 2026-10-26 · Para la **1.34.0** (la 1.33.0 lleva lo
> de Reportes: días de trabajo, 2 semanas y Copiar para IA). Sin implementar.

## El problema

Hoy un proyecto es una etiqueta plana de la tarea, y en la misma lista conviven dos cosas
distintas: **áreas que no terminan** (un emprendimiento, "Personal") y **proyectos que sí
terminan** (una app, una campaña, un producto). Un emprendimiento tiene varios proyectos dentro,
y su tiempo y sus gastos se quieren ver juntos sin perder el detalle de cada uno.

## Cómo lo resuelven otras apps (investigado el 2026-10-26)

- **Toggl Track y Clockify** (tiempo y dinero): un nivel fijo arriba del proyecto (*cliente*). Un
  proyecto tiene **un solo** cliente, el tiempo nunca va directo al cliente y los reportes agrupan
  por cliente → proyecto.
- **Things 3, GTD y PARA**: separan *áreas* (sin fin) de *proyectos* (con fin) por si se terminan,
  no por tema.
- **Todoist**: subproyectos con tope de 3 niveles; pasado eso, recomienda secciones.
- **Linear, ClickUp, Asana**: jerarquías profundas (iniciativas, espacios, carpetas, portafolios),
  pensadas para equipos.

Lo que se toma: **un solo nivel** y **un solo padre**, como las apps de tiempo y dinero.

## Decisiones (2026-10-26)

- **Se llama Grupo.** No "organización": la app es personal y nada empresarial (épica 24).
- **Un grupo es un proyecto con hijos** (`projects.parent_id`, como `fin_accounts.parent_id` de
  los apartados de Finanzas). No hay tabla nueva: un proyecto que hoy hace de área se vuelve grupo
  con solo asignarle hijos, sin mover sus tareas, su tiempo ni sus gastos.
- **Un nivel.** Un proyecto con hijos no puede tener padre, y el padre no puede tener padre.
- **Un solo grupo por proyecto.** Si contara en dos, su tiempo y sus costos se sumarían dos veces.
  Para mirarlo de otra forma están las etiquetas.
- **El grupo tiene lo suyo ("General").** Puede tener tareas, tiempo y gastos propios: lo que es
  del emprendimiento entero y de ningún proyecto (infraestructura, equipo, insumos de stock,
  dominio, contador).
- **El total del grupo** = lo suyo + lo de sus proyectos, en tiempo y en costos. En pantalla:
  el grupo con su total, la fila *General* y cada proyecto.
- **El dinero se suma por moneda**, como hoy en Costos: nunca se convierte.
- **Opcional.** Quien no lo usa no ve cambios: cada proyecto queda "sin grupo".
- **"Sin asignar"** no tiene grupo ni puede serlo.
- **Archivar un grupo** no archiva sus proyectos (la pantalla lo avisa). **Borrarlo** deja sus
  proyectos sin grupo, con la misma regla de hoy para sus tareas y su tiempo.
- **El nombre sigue siendo único por cuenta**, aunque esté en otro grupo. Se revisa si estorba.
- **"Personal" como grupo no es el tipo `personal` del costeo** (`project_finance.kind`, "no se
  cobra"). La pantalla los nombra distinto.

## Fases (1.34.0)

1. **Base.** `projects.parent_id` (columna en una tabla existente: **va en `scripts/migrate.py`**
   y se corre antes de reiniciar). Reglas en el servidor (un nivel, misma cuenta, no "Sin
   asignar", sin ciclos) con sus 409 en español. La API lo devuelve. Pruebas: reglas, un caso en
   `test_isolation.py` (el padre de otra cuenta → 404), `test_limits.py` y `test_deploy.py`.
2. **Proyectos.** "Grupo" en la ficha y en Organizar. La Lista agrupa por grupo. Filtrar el
   tablero por un grupo incluye a sus proyectos.
3. **Reportes.** Por proyecto, agrupado por grupo con su subtotal. La columna *Grupo* en el CSV
   de tiempo y en *Copiar para IA*; el reporte guardado y lo que recibe la IA, igual.
4. **Costos.** El resumen agrupado por grupo con subtotales por moneda, también en el reporte de
   costos del mes.

## Para después (no en la 1.34.0)

- **Repartir un gasto con el grupo como una de las partes, y por cantidad.** Un insumo comprado
  para el grupo (un kilo de material) que se gasta por partes en varios proyectos: "0.3 a un
  proyecto, 0.2 a otro" y el resto sin asignar se queda en el grupo, editable conforme se usa.
  Hoy el reparto es por porcentaje y suma 100 % entre proyectos de una moneda.
- **No es inventario** (épica 24: "nada empresarial… ni inventario"): no lleva existencias, ni
  entradas y salidas, ni varias compras del mismo material. Cada compra es un gasto que se
  reparte. "Cuánto material me queda entre todas las compras" sí sería inventario y reabriría
  esa decisión.
- **Equipo que dura años:** se queda en el grupo. Repartir su costo por uso (depreciación) queda
  fuera por la misma razón.
- **Costos como app aparte** (idea del 2026-10-26): ver la sección siguiente.

## Idea: Costos como app aparte, hacia el punto de equilibrio

Planteada para más adelante, sin decidir. Que Costos crezca para que quien emprende o fabrica
sepa **cuánto tiene que vender para no perder** (punto de equilibrio: gastos fijos ÷ margen por
unidad). Notas para cuando se retome:

- **El grupo es la base:** el punto de equilibrio se calcula por emprendimiento (sus fijos, su
  equipo), no por proyecto suelto.
- **Pide datos que hoy no hay:** precio y costo variable **por unidad**, y unidades vendidas.
  Hoy un proyecto tiene un precio total, no por unidad, y la app no registra ventas.
- **Roza dos decisiones tomadas:** sin facturación ni inventario (épica 24). Registrar ventas por
  unidad acerca a las dos.
- **"App aparte" puede ser como Finanzas:** otra página de la misma app (`/finance`), con la misma
  sesión y su propio número de versión. A diferencia de Finanzas, Costos **comparte datos con el
  núcleo** (proyectos, grupos y el tiempo que da la mano de obra), así que no se separa en otro
  servidor ni en otra base.
