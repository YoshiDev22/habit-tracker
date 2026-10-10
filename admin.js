// ============================================
// Panel de administración (1.27): lectura en la Fase 1, acciones con bitácora en la Fase 2
// ============================================
//
// Lo sirve backend/admin_main.py, otro proceso que la app. En producción
// Cloudflare Access agrega su JWT a cada petición; aquí no se toca. En tu
// máquina, scripts/admin_dev.py abre esta página con #dev=<token> y el panel lo
// manda él mismo, solo si la página está en 127.0.0.1 o localhost.
//
// Todo se pinta con textContent: un reporte de problema lo escribe cualquier
// usuario, y nunca se interpreta como HTML (la CSP tampoco dejaría correrlo).

const DEV_TOKEN_KEY = 'admin_dev_token';
const LOCAL_HOSTS = ['127.0.0.1', 'localhost'];
const MODULE_LABELS = { habits: 'Hábitos', maker: 'Maker', ai: 'IA' };
const COUNT_LABELS = { boards: 'Tableros', tasks: 'Tareas', habits: 'Hábitos', sessions: 'Sesiones', costs: 'Gastos', reports: 'Reportes' };
const PURPOSE_LABELS = { report: 'Tiempo y hábitos', costs: 'Costos' };
const STATUS_LABELS = { open: 'Abierto', reviewed: 'Revisado', closed: 'Cerrado' };

function devToken() {
    if (!LOCAL_HOSTS.includes(location.hostname)) return null;
    const match = location.hash.match(/^#dev=([\w.-]+)$/);
    try {
        if (match) {
            sessionStorage.setItem(DEV_TOKEN_KEY, match[1]);
            history.replaceState(null, '', location.pathname);   // que no quede en la barra
        }
        return sessionStorage.getItem(DEV_TOKEN_KEY);
    } catch (error) {
        return match ? match[1] : null;
    }
}

const DEV_TOKEN = devToken();

class DeniedError extends Error {}

function apiErrorMessage(data, status) {
    const detail = data && data.detail;
    if (Array.isArray(detail)) return detail[0] && detail[0].msg ? detail[0].msg : `Error ${status}`;
    return detail || `Error ${status}`;
}

// Lo que cambia algo: JSON (el navegador agrega el Origin del panel, que el servidor pide)
async function adminSend(method, path, body) {
    const headers = { 'Content-Type': 'application/json' };
    if (DEV_TOKEN) headers['Cf-Access-Jwt-Assertion'] = DEV_TOKEN;
    const response = await fetch(path, { method, headers, credentials: 'same-origin', body: JSON.stringify(body) });
    const data = await response.json().catch(() => null);
    if (response.status === 403) throw new DeniedError('Acceso denegado');
    if (!response.ok) throw new Error(apiErrorMessage(data, response.status));
    return data;
}

async function adminGet(path) {
    const headers = DEV_TOKEN ? { 'Cf-Access-Jwt-Assertion': DEV_TOKEN } : {};
    const response = await fetch(path, { headers, credentials: 'same-origin' });
    if (response.status === 403) throw new DeniedError('Acceso denegado');
    if (!response.ok) throw new Error(`${path}: ${response.status}`);
    return response.json();
}

function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined && text !== null) element.textContent = String(text);
    return element;
}

// Las fechas del servidor son UTC sin huso: se marcan como UTC para verlas en hora local
function asDate(iso) {
    return iso ? new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`) : null;
}

function shortDate(iso) {
    const d = asDate(iso);
    return d ? d.toLocaleDateString('es-MX', { day: 'numeric', month: 'short', year: 'numeric' }) : '—';
}

function dateTime(iso) {
    const d = asDate(iso);
    return d ? d.toLocaleString('es-MX', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—';
}

function ago(iso) {
    const d = asDate(iso);
    if (!d) return 'Nunca';
    const minutes = Math.round((Date.now() - d.getTime()) / 60000);
    if (minutes < 60) return 'Hace menos de 1 h';
    const hours = Math.round(minutes / 60);
    if (hours < 24) return `Hace ${hours} h`;
    const days = Math.round(hours / 24);
    return days === 1 ? 'Ayer' : `Hace ${days} días`;
}

const number = new Intl.NumberFormat('es-MX');

// ---------- Resumen ----------

function stat(label, value, note) {
    const box = node('div', 'stat');
    box.append(node('span', 'stat-value', value), node('span', 'stat-label', label));
    if (note) box.append(node('span', 'stat-note', note));
    return box;
}

function renderSummary(s) {
    const grid = document.getElementById('summaryStats');
    grid.replaceChildren(
        stat('Cuentas', number.format(s.accounts), s.unknown_signup ? `${s.unknown_signup} de antes de la 1.27, sin fecha de registro` : ''),
        stat('Nuevas', `${s.new_7d} · ${s.new_30d}`, 'en 7 y en 30 días'),
        stat('Activas', `${s.active_7d} · ${s.active_30d}`, 'en 7 y en 30 días'),
        stat('Problemas abiertos', s.feedback_open),
        stat('IA hoy', `${s.ai_today.ok} · ${s.ai_today.failed}`, 'buenas y fallidas (día UTC)'),
        stat('Borrado programado', s.scheduled_deletion),
    );
}

// ---------- Cuentas ----------

function moduleBadges(modules) {
    const cell = node('td', 'badges');
    for (const [name, state] of Object.entries(modules)) {
        if (!state.allowed) continue;
        const badge = node('span', state.enabled ? 'badge on' : 'badge off', MODULE_LABELS[name] || name);
        badge.title = state.enabled ? 'Encendido' : 'Con acceso, apagado';
        cell.append(badge);
    }
    return cell;
}

function emailCell(account) {
    const cell = node('td', 'account-cell');
    const manage = node('button', 'manage', 'Gestionar');
    manage.type = 'button';
    manage.addEventListener('click', () => openAccount(account.id));
    cell.append(manage);
    const button = node('button', 'email', account.email);
    button.type = 'button';
    button.title = 'Ver el correo completo';
    button.addEventListener('click', async () => {
        try {
            const data = await adminGet(`/api/accounts/${account.id}/email`);
            button.textContent = data.email;
            button.disabled = true;
        } catch (error) {
            button.title = 'No se pudo cargar';
        }
    });
    cell.append(button);
    if (account.delete_after) cell.append(node('span', 'leaving', `Se borra el ${shortDate(account.delete_after)}`));
    if (!account.active) cell.append(node('span', 'leaving', 'Desactivada'));
    return cell;
}

const accountsState = { list: [], open: null };

function renderAccounts(accounts) {
    accountsState.list = accounts;
    const table = document.getElementById('accountsTable');
    const head = node('tr');
    for (const label of ['Cuenta', 'Registro', 'Última actividad', 'Módulos', ...Object.values(COUNT_LABELS), 'IA hoy', 'IA mes']) {
        head.append(node('th', null, label));
    }
    const body = node('tbody');
    for (const account of accounts) {
        const row = node('tr');
        row.append(emailCell(account),
            node('td', null, account.created_at ? shortDate(account.created_at) : 'Antes de la 1.27'),
            node('td', null, ago(account.last_seen_at)),
            moduleBadges(account.modules));
        for (const key of Object.keys(COUNT_LABELS)) row.append(node('td', 'num', number.format(account.counts[key])));
        for (const period of ['today', 'month']) {
            const ai = account.ai[period];
            const cell = node('td', 'num', `${ai.ok} · ${ai.failed}`);
            cell.title = `${ai.ok} buenas, ${ai.failed} fallidas, ${number.format(ai.tokens)} tokens`;
            row.append(cell);
        }
        body.append(row);
    }
    const thead = node('thead');
    thead.append(head);
    table.replaceChildren(thead, body);
}

// ---------- La ficha de una cuenta (Fase 2) ----------

const accountDialog = document.getElementById('accountDialog');
const accountError = document.getElementById('accountDialogError');

function showAccountError(message) {
    accountError.textContent = message;
    accountError.hidden = !message;
}

function describeChange(action) {
    if (action.action === 'account') return action.after.active ? 'Cuenta reactivada' : 'Cuenta desactivada';
    if (action.action === 'keep') return 'Borrado programado cancelado';
    if (action.action === 'ai_grant') {
        const added = (action.after.extra || 0) - (action.before.extra || 0);
        return `+${added} textos de IA hoy (${PURPOSE_LABELS[action.after.pool] || action.after.pool})`;
    }
    if (action.action === 'module') {
        const [name, after] = Object.entries(action.after || {})[0] || [];
        const label = MODULE_LABELS[name] || name;
        return after && after.allowed ? `Acceso a ${label} dado` : `Acceso a ${label} quitado`;
    }
    return action.action;
}

async function renderAccountLog(accountId) {
    const data = await adminGet(`/api/actions?account_id=${accountId}`);
    const list = document.getElementById('accountLog');
    list.replaceChildren(...(data.actions.length
        ? data.actions.map(a => node('li', null, `${dateTime(a.created_at)} · ${describeChange(a)} · ${a.admin}`))
        : [node('li', 'empty', 'Nada todavía.')]));
}

function moduleNote(state) {
    if (!state.allowed) return 'Sin acceso';
    return state.enabled ? 'Con acceso, encendido' : 'Con acceso, apagado por la persona';
}

function renderAccountModules(account) {
    const box = document.getElementById('accountModules');
    box.replaceChildren(...['maker', 'ai'].map((name) => {
        const state = account.modules[name];
        const label = node('label', 'module-row');
        const input = node('input');
        input.type = 'checkbox';
        input.checked = state.allowed;
        input.dataset.module = name;
        input.addEventListener('change', () => setModuleAccess(account.id, name, input));
        label.append(input, node('span', null, MODULE_LABELS[name]), node('small', 'hint', moduleNote(state)));
        return label;
    }));
}

const deactivateButton = document.getElementById('accountDeactivate');
let deactivateArmed = false;

function disarmDeactivate() {
    deactivateArmed = false;
    deactivateButton.textContent = 'Desactivar cuenta';
}

function renderAccountState(account) {
    const leaving = account.delete_after ? ` · se borra el ${shortDate(account.delete_after)}` : '';
    document.getElementById('accountState').textContent = (account.active ? 'Activa' : 'Desactivada') + leaving;
    deactivateButton.hidden = !account.active;
    document.getElementById('accountReactivate').hidden = account.active;
    document.getElementById('accountKeep').hidden = !account.delete_after;
    document.getElementById('accountStateHint').textContent = account.active
        ? 'Desactivarla la saca al momento de todos sus dispositivos. No borra nada.'
        : 'Al reactivarla tendrá que volver a entrar: sus sesiones de antes ya no valen.';
    disarmDeactivate();
}

async function changeAccount(path, body, method = 'PUT') {
    const accountId = accountsState.open;
    if (!accountId) return;
    showAccountError('');
    try {
        await adminSend(method, `/api/accounts/${accountId}/${path}`, body);
        await reloadAccounts();
        await renderAccountLog(accountId);
    } catch (error) {
        if (error instanceof DeniedError) {
            accountDialog.close();
            showFailure(error);
            return;
        }
        showAccountError(error.message);
    }
}

// Desactivar pide un segundo clic: es lo único de la ficha que saca a alguien de la app
deactivateButton.addEventListener('click', () => {
    if (!deactivateArmed) {
        deactivateArmed = true;
        deactivateButton.textContent = 'Confirmar: desactivar';
        return;
    }
    disarmDeactivate();
    changeAccount('active', { active: false });
});
document.getElementById('accountReactivate').addEventListener('click', () => changeAccount('active', { active: true }));
document.getElementById('accountKeep').addEventListener('click', () => changeAccount('keep', {}, 'POST'));

function renderAccountDialog(account) {
    document.getElementById('accountDialogTitle').textContent = account.email;
    const signup = account.created_at ? shortDate(account.created_at) : 'antes de la 1.27';
    document.getElementById('accountDialogMeta').textContent =
        `Registro: ${signup} · Última actividad: ${ago(account.last_seen_at).toLowerCase()}`;
    renderAccountModules(account);
    renderAccountState(account);
}

async function reloadAccounts() {
    const data = await adminGet('/api/accounts');
    renderAccounts(data.accounts);
    const account = data.accounts.find(a => a.id === accountsState.open);
    if (account && accountDialog.open) renderAccountDialog(account);
}

async function setModuleAccess(accountId, module, input) {
    showAccountError('');
    input.disabled = true;
    try {
        await adminSend('PUT', `/api/accounts/${accountId}/modules/${module}`, { allowed: input.checked });
        await reloadAccounts();
        await renderAccountLog(accountId);
    } catch (error) {
        input.checked = !input.checked;
        if (error instanceof DeniedError) {
            accountDialog.close();
            showFailure(error);
            return;
        }
        showAccountError(error.message);
    } finally {
        input.disabled = false;
    }
}

async function renderAccountAi(accountId) {
    const data = await adminGet(`/api/accounts/${accountId}/ai`);
    const list = document.getElementById('accountAi');
    if (!data.configured) {
        list.replaceChildren(node('li', 'empty', 'Esta instancia no tiene proveedor de IA configurado.'));
        return;
    }
    list.replaceChildren(...Object.entries(data.pools).map(([pool, usage]) => {
        const extra = usage.extra_today ? ` (incluye ${usage.extra_today} extra)` : '';
        return node('li', null, `${PURPOSE_LABELS[pool]}: ${usage.used_today} de ${usage.limit} usados${extra}`
            + (usage.failed_today ? ` · ${usage.failed_today} fallidos` : ''));
    }));
}

document.getElementById('aiGrantForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const accountId = accountsState.open;
    if (!accountId) return;
    showAccountError('');
    const button = event.submitter;
    if (button) button.disabled = true;
    try {
        await adminSend('POST', `/api/accounts/${accountId}/ai-grants`, {
            pool: document.getElementById('aiGrantPool').value,
            extra: Number(document.getElementById('aiGrantExtra').value),
        });
        await Promise.all([renderAccountAi(accountId), renderAccountLog(accountId)]);
    } catch (error) {
        if (error instanceof DeniedError) {
            accountDialog.close();
            showFailure(error);
            return;
        }
        showAccountError(error.message);
    } finally {
        if (button) button.disabled = false;
    }
});

async function openAccount(accountId) {
    const account = accountsState.list.find(a => a.id === accountId);
    if (!account) return;
    accountsState.open = accountId;
    showAccountError('');
    renderAccountDialog(account);
    accountDialog.showModal();
    try {
        await Promise.all([renderAccountLog(accountId), renderAccountAi(accountId)]);
    } catch (error) {
        showAccountError('No se pudo cargar la ficha completa.');
    }
}

document.getElementById('accountDialogClose').addEventListener('click', () => accountDialog.close());
accountDialog.addEventListener('close', () => { accountsState.open = null; });

// ---------- IA ----------

function renderAi(ai) {
    const table = document.getElementById('aiTable');
    const head = node('tr');
    for (const label of ['Día (UTC)', 'Contador', 'Buenas', 'Fallidas', 'Tokens']) head.append(node('th', null, label));
    const body = node('tbody');
    if (!ai.days.length) {
        const row = node('tr');
        const cell = node('td', 'empty', 'Sin llamadas en estos días.');
        cell.colSpan = 5;
        row.append(cell);
        body.append(row);
    }
    for (const day of [...ai.days].reverse()) {
        const row = node('tr');
        row.append(node('td', null, day.date), node('td', null, PURPOSE_LABELS[day.purpose] || day.purpose),
            node('td', 'num', day.ok), node('td', 'num', day.failed), node('td', 'num', number.format(day.tokens)));
        body.append(row);
    }
    const thead = node('thead');
    thead.append(head);
    table.replaceChildren(thead, body);
    const errors = document.getElementById('aiErrors');
    errors.replaceChildren(...(ai.errors.length
        ? ai.errors.map(e => node('li', null, `${e.count} × ${e.error}`))
        : [node('li', 'empty', 'Ninguno.')]));
}

// ---------- Problemas ----------

function renderFeedback(items) {
    const list = document.getElementById('feedbackList');
    if (!items.length) {
        list.replaceChildren(node('p', 'empty', 'Nada por aquí.'));
        return;
    }
    list.replaceChildren(...items.map((item) => {
        const card = node('article', 'feedback');
        const meta = node('p', 'feedback-meta');
        meta.append(node('span', `status ${item.status}`, STATUS_LABELS[item.status] || item.status),
            node('span', null, dateTime(item.created_at)), node('span', null, item.account.email));
        card.append(meta, node('p', 'feedback-text', item.text));
        if (item.details) {
            const details = node('details', 'feedback-details');
            details.append(node('summary', null, 'Detalles técnicos'), node('pre', null, JSON.stringify(item.details, null, 2)));
            card.append(details);
        }
        if (item.admin_note) card.append(node('p', 'feedback-note', item.admin_note));
        return card;
    }));
}

async function loadFeedback() {
    const status = document.getElementById('feedbackFilter').value;
    const data = await adminGet(`/api/feedback${status ? `?status=${status}` : ''}`);
    renderFeedback(data.feedback);
}

// ---------- Pestañas y arranque ----------

// ---------- Bitácora ----------

async function renderLog() {
    const data = await adminGet('/api/actions');
    const table = document.getElementById('logTable');
    const head = node('tr');
    for (const label of ['Cuándo', 'Quién', 'Qué', 'Cuenta']) head.append(node('th', null, label));
    const body = node('tbody');
    if (!data.actions.length) {
        const row = node('tr');
        const cell = node('td', 'empty', 'Nada todavía.');
        cell.colSpan = 4;
        row.append(cell);
        body.append(row);
    }
    for (const action of data.actions) {
        const row = node('tr');
        const account = action.account_id === null ? '—'
            : (action.account || `Cuenta borrada (#${action.account_id})`);
        row.append(node('td', null, dateTime(action.created_at)), node('td', null, action.admin),
            node('td', null, describeChange(action)), node('td', null, account));
        body.append(row);
    }
    const thead = node('thead');
    thead.append(head);
    table.replaceChildren(thead, body);
}

function showTab(name) {
    document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
    document.querySelectorAll('.view').forEach(v => v.classList.toggle('active', v.dataset.view === name));
    // La bitácora se pide al abrirla: así enseña también lo que se hizo desde otra pestaña
    if (name === 'log') renderLog().catch(showFailure);
}

document.getElementById('tabs').addEventListener('click', (event) => {
    const tab = event.target.closest('[data-tab]');
    if (tab) showTab(tab.dataset.tab);
});

document.getElementById('feedbackFilter').addEventListener('change', () => {
    loadFeedback().catch(showFailure);
});

function showFailure(error) {
    document.getElementById('loading').hidden = true;
    if (error instanceof DeniedError) {
        const denied = document.getElementById('denied');
        // En tu máquina no hay Cloudflare: el token de admin_dev.py venció (8 h) o es de otra vez
        if (LOCAL_HOSTS.includes(location.hostname)) {
            denied.textContent = 'Acceso denegado: el enlace de scripts/admin_dev.py venció (dura 8 h) o es de '
                + 'otra vez que lo abriste. Ciérralo con Ctrl+C, vuelve a correrlo y entra con el enlace nuevo.';
        }
        denied.hidden = false;
        document.querySelectorAll('.view, .tabs').forEach(v => { v.hidden = true; });
        return;
    }
    console.error('Panel:', error);
    const loading = document.getElementById('loading');
    loading.textContent = 'No se pudo cargar el panel. Recarga la página.';
    loading.hidden = false;
}

async function start() {
    try {
        const me = await adminGet('/api/me');
        document.getElementById('who').textContent = `${me.email}${DEV_TOKEN ? ' · modo de desarrollo' : ''}`;
        const [summary, accounts, ai] = await Promise.all([
            adminGet('/api/summary'), adminGet('/api/accounts'), adminGet('/api/ai'),
        ]);
        renderSummary(summary);
        renderAccounts(accounts.accounts);
        renderAi(ai);
        await loadFeedback();
        document.getElementById('loading').hidden = true;
    } catch (error) {
        showFailure(error);
    }
}

start();
