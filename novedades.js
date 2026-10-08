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

function buildVersionNews(entry, withTitle) {
    const box = el('section', 'novedades-version');
    if (withTitle) box.appendChild(el('h3', 'novedades-version-title', `Versión ${shortVersion(entry.version)}`));
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

function closeNovedades() {
    hideModal(novedadesModal);
    if (novedadesState.data) markSeen(novedadesState.data.current);
}

async function loadNovedades() {
    try {
        novedadesState.data = await apiFetch('/api/novedades');
    } catch (error) {
        return;   // sin Novedades no pasa nada
    }
    renderNewsPage();
    const { current, versions } = novedadesState.data;
    let justRegistered = false;
    try {
        justRegistered = sessionStorage.getItem(NOVEDADES_REGISTERED_KEY) === '1';
        sessionStorage.removeItem(NOVEDADES_REGISTERED_KEY);
    } catch (error) { /* sin almacenamiento */ }
    const seen = readSeenVersion();
    // Cuenta nueva: empieza al día. Ya vista: nada.
    if (justRegistered || (seen && compareVersions(seen, current) >= 0)) {
        markSeen(current);
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
