// ============================================
// Novedades (1.25)
// ============================================
//
// Al entrar después de una actualización, una ventana con lo nuevo de esa
// versión (o de las que se saltaron), y Mi perfil › Novedades para volver a
// verlas. El texto sale de NOVEDADES.md vía GET /api/novedades: nunca del
// CHANGELOG ni nada de despliegue. Lo último visto se recuerda en este
// dispositivo (localStorage.novedades_seen). Una cuenta recién creada no ve
// nada: empieza al día. Usa el() de reports.js.

const NOVEDADES_SEEN_KEY = 'novedades_seen';
const NOVEDADES_REGISTERED_KEY = 'novedades_just_registered';   // sessionStorage
const novedadesModal = document.getElementById('novedadesModal');
const novedadesState = { data: null };

function readSeenVersion() {
    try { return localStorage.getItem(NOVEDADES_SEEN_KEY); } catch (error) { return null; }
}

function markSeen(version) {
    try { localStorage.setItem(NOVEDADES_SEEN_KEY, version); } catch (error) { /* sin almacenamiento: volverá a salir */ }
}

// -1, 0 o 1, por semver (1.10.0 > 1.9.0)
function compareVersions(a, b) {
    const pa = String(a).split('.').map(Number);
    const pb = String(b).split('.').map(Number);
    for (let i = 0; i < 3; i++) {
        if ((pa[i] || 0) !== (pb[i] || 0)) return (pa[i] || 0) < (pb[i] || 0) ? -1 : 1;
    }
    return 0;
}

// "**Gastos recurrentes** (plan Maker): …" con las negritas, sin innerHTML
function richText(text) {
    const node = document.createElement('span');
    text.split(/(\*\*[^*]+\*\*)/).forEach(part => {
        if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
            node.appendChild(el('strong', '', part.slice(2, -2)));
        } else if (part) {
            node.appendChild(document.createTextNode(part));
        }
    });
    return node;
}

function shortVersion(version) {
    return version.replace(/\.0$/, '');
}

// "9 oct 2026": la fecha de la versión (AAAA-MM-DD, sin hora; a mediodía para que ningún huso la corra)
function versionDate(date) {
    if (!date) return '';
    const day = new Date(`${date}T12:00:00`);
    return Number.isNaN(day.getTime()) ? '' : day.toLocaleDateString('es-MX', { day: 'numeric', month: 'short', year: 'numeric' })
        .replace('.', '');
}

function buildVersionNews(entry, withTitle) {
    const box = el('section', 'novedades-version');
    if (withTitle) {
        const when = versionDate(entry.date);
        box.appendChild(el('h3', 'novedades-version-title', `Versión ${shortVersion(entry.version)}${when ? ` · ${when}` : ''}`));
    }
    entry.sections.forEach(section => {
        box.appendChild(el('p', 'novedades-section', section.title));
        const list = el('ul', 'novedades-list');
        section.items.forEach(item => {
            const li = el('li');
            li.appendChild(richText(item));
            list.appendChild(li);
        });
        box.appendChild(list);
    });
    return box;
}

// Mi perfil › Novedades: todas, la más nueva arriba
function renderNewsPage() {
    const page = document.getElementById('novedadesPage');
    const versions = (novedadesState.data && novedadesState.data.versions) || [];
    page.replaceChildren(...(versions.length
        ? versions.map(entry => buildVersionNews(entry, true))
        : [el('p', 'module-hint', 'Aún no hay novedades.')]));
}

function showNovedades(entries) {
    const current = novedadesState.data.current;
    document.getElementById('novedadesTitle').textContent = entries.length === 1
        ? `Novedades de la ${shortVersion(entries[0].version)}`
        : `Novedades hasta la ${shortVersion(current)}`;
    document.getElementById('novedadesBody').replaceChildren(
        ...entries.map(entry => buildVersionNews(entry, entries.length > 1)));
    showModal(novedadesModal);
}

// El aviso de Novedades de la campanita también queda leído (1.26)
function readNovedadesNotice() {
    apiFetch('/api/notices/read', { method: 'POST', json: { kinds: ['novedades'] } })
        .then(() => { if (typeof refreshNotices === 'function') refreshNotices(); })
        .catch(() => { /* sin red: se leerá al abrir la campanita */ });
}

function closeNovedades() {
    hideModal(novedadesModal);
    if (novedadesState.data) markSeen(novedadesState.data.current);
    readNovedadesNotice();
}

async function loadNovedades() {
    try {
        novedadesState.data = await apiFetch('/api/novedades');
    } catch (error) {
        return;   // sin Novedades no pasa nada
    }
    renderNewsPage();
    const { current, versions } = novedadesState.data;
    // La versión con la que abrió esta página: la primera que se supo (otra cuenta en
    // la misma pestaña no la cambia; el código sigue siendo el mismo)
    if (!updateState.pageVersion) updateState.pageVersion = current;
    let justRegistered = false;
    try {
        justRegistered = sessionStorage.getItem(NOVEDADES_REGISTERED_KEY) === '1';
        sessionStorage.removeItem(NOVEDADES_REGISTERED_KEY);
    } catch (error) { /* sin almacenamiento */ }
    const seen = readSeenVersion();
    // Cuenta nueva: empieza al día. Ya vista: nada.
    if (justRegistered || (seen && compareVersions(seen, current) >= 0)) {
        markSeen(current);
        if (justRegistered) readNovedadesNotice();
        return;
    }
    // Lo que no ha visto: desde la que vio (sin incluirla) hasta la actual; sin
    // registro en este dispositivo, solo la actual
    const pending = versions.filter(v => compareVersions(v.version, current) <= 0
        && (seen ? compareVersions(v.version, seen) > 0 : compareVersions(v.version, current) === 0));
    if (!pending.length) {
        markSeen(current);
        return;
    }
    showNovedades(pending);
}

// ---------- ¿Hay una versión nueva en el servidor? ----------
// Una pestaña abierta días, o la app instalada en el teléfono, sigue con el código
// con el que abrió: el HTTP está bien (no-cache + ETag, un F5 basta), pero nadie
// recarga. Al volver a la pestaña (como mucho cada 5 min) y cada 30 min a la vista
// se compara la versión del servidor con la de esta página; si es más nueva, una
// franja ofrece recargar. Nunca recarga sola: se perdería lo que se está escribiendo
// (el cronómetro no: vive en localStorage).

const UPDATE_CHECK_EVERY_MS = 30 * 60 * 1000;
const UPDATE_CHECK_MIN_GAP_MS = 5 * 60 * 1000;
const updateState = { pageVersion: null, lastCheck: 0, dismissed: null };
const updateBanner = document.getElementById('updateBanner');

async function checkForUpdate(force = false) {
    if (!updateState.pageVersion || document.visibilityState !== 'visible') return;
    if (!force && Date.now() - updateState.lastCheck < UPDATE_CHECK_MIN_GAP_MS) return;
    updateState.lastCheck = Date.now();
    let server;
    try {
        server = (await apiFetch('/api/version')).version;
    } catch (error) {
        return;   // sin red o en pleno reinicio del servicio: se vuelve a intentar después
    }
    if (server && compareVersions(server, updateState.pageVersion) > 0 && server !== updateState.dismissed) {
        updateBanner.dataset.version = server;
        updateBanner.hidden = false;
    }
}

document.getElementById('updateReload').addEventListener('click', () => location.reload());
document.getElementById('updateDismiss').addEventListener('click', () => {
    // Cerrada, no vuelve por esa misma versión; sí por una más nueva
    updateState.dismissed = updateBanner.dataset.version || null;
    updateBanner.hidden = true;
});
document.addEventListener('visibilitychange', () => { checkForUpdate(); });
setInterval(() => { checkForUpdate(true); }, UPDATE_CHECK_EVERY_MS);

// Registrarse en este navegador: la cuenta nueva no ve las Novedades de hoy
document.getElementById('registerForm').addEventListener('submit', () => {
    try { sessionStorage.setItem(NOVEDADES_REGISTERED_KEY, '1'); } catch (error) { /* sin almacenamiento */ }
});
document.getElementById('loginForm').addEventListener('submit', () => {
    try { sessionStorage.removeItem(NOVEDADES_REGISTERED_KEY); } catch (error) { /* sin almacenamiento */ }
});

document.getElementById('novedadesOk').addEventListener('click', closeNovedades);
document.getElementById('novedadesClose').addEventListener('click', closeNovedades);
novedadesModal.querySelector('.modal-overlay').addEventListener('click', closeNovedades);
document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !novedadesModal.classList.contains('hidden')) closeNovedades();
});

window.appDataHooks.push(loadNovedades);
window.appLogoutHooks.push(() => {
    hideModal(novedadesModal);
    novedadesState.data = null;
});
