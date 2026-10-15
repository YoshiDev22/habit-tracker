// ============================================
// Logros (módulo "achievements"): línea del tiempo, vitrina, detalle y el botón SOS
// ============================================
//
// Todo sale de GET /api/achievements, que además crea los hitos automáticos que
// se hayan cruzado. Las evidencias se piden con el token (apiFetch con blob) y se
// enseñan con URL.createObjectURL(): un <img src> a la API no llevaría la sesión.
// Las URLs se guardan por id y se sueltan al cerrar sesión.

const ACH_KIND_LABELS = { diploma: 'Diploma o constancia', anecdote: 'Anécdota', milestone: 'Hito' };
const ACH_MONTHS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre',
    'octubre', 'noviembre', 'diciembre'];
const ACH_NEW_COLLECTION = '__new__';

const achState = {
    loaded: false,
    achievements: [],
    categories: [],
    collections: [],
    usage: null,
    view: 'timeline',
    editingId: null,      // null = nuevo
    detailId: null,
    precision: 'day',
    sosSeen: [],          // ids ya enseñados en esta apertura del SOS
};
const achBlobUrls = new Map();   // 'thumb:12' | 'file:12' -> object URL

const achBody = document.getElementById('achBody');
const achModal = document.getElementById('achievementModal');
const achDetailModal = document.getElementById('achDetailModal');
const sosModal = document.getElementById('sosModal');
const achForm = document.getElementById('achForm');
const achFormError = document.getElementById('achFormError');
const achDetailError = document.getElementById('achDetailError');

function isAchievementsVisible() {
    return typeof currentViewId !== 'undefined' && currentViewId === 'achievements';
}

function applyAchievementsModule() {
    const on = moduleEnabled('achievements');
    // Como Costos: recargar estando en Logros vuelve a ella al saber del módulo
    const wasHere = readLastView() === 'achievements';
    setViewVisible('achievements', on);
    if (on && wasHere && currentViewId !== 'achievements') {
        goToView('achievements', { animate: false });
    }
    if (!on) achState.loaded = false;
}

// ============================================
// Fechas
// ============================================

function achDateParts(value) {
    const [year, month, day] = value.split('-').map(Number);
    return { year, month, day };
}

// "17 may 2020" o "mayo de 2020": la fecha tal como se sabe
function achDateLabel(achievement) {
    const { year, month, day } = achDateParts(achievement.date);
    if (achievement.date_precision === 'month') return `${ACH_MONTHS[month - 1]} de ${year}`;
    return new Date(year, month - 1, day).toLocaleDateString('es-MX', { day: 'numeric', month: 'short', year: 'numeric' });
}

function setPrecision(precision) {
    achState.precision = precision;
    document.querySelectorAll('.ach-precision [data-precision]').forEach(btn => {
        btn.setAttribute('aria-pressed', String(btn.dataset.precision === precision));
    });
    document.getElementById('achDay').hidden = precision !== 'day';
    achForm.querySelector('.ach-month').hidden = precision !== 'month';
}

function readFormDate() {
    if (achState.precision === 'day') return document.getElementById('achDay').value;
    const year = document.getElementById('achYear').value.trim();
    const month = document.getElementById('achMonth').value;
    return /^\d{4}$/.test(year) ? `${year}-${month}` : '';
}

// ============================================
// Carga y pintado
// ============================================

async function loadAchievements() {
    if (!getToken() || !moduleEnabled('achievements')) return;
    try {
        const data = await apiFetch('/api/achievements');
        Object.assign(achState, {
            loaded: true, achievements: data.achievements, categories: data.categories,
            collections: data.collections, usage: data.usage,
        });
    } catch (error) {
        achBody.replaceChildren(el('p', 'ach-empty', `No se pudieron cargar tus logros: ${error.message}`));
        return;
    }
    fillCategoryFilter();
    renderAchievements();
}

function fillCategoryFilter() {
    const select = document.getElementById('achFilterCategory');
    const current = select.value;
    select.replaceChildren(new Option('Todas las categorías', ''));
    achState.categories.forEach(c => select.add(new Option(c.name, String(c.id))));
    select.value = achState.categories.some(c => String(c.id) === current) ? current : '';
}

function filteredAchievements() {
    const category = document.getElementById('achFilterCategory').value;
    const kind = document.getElementById('achFilterKind').value;
    const showHidden = document.getElementById('achShowHidden').checked;
    return achState.achievements.filter(a =>
        (showHidden || !a.is_hidden)
        && (!category || String(a.category_id) === category)
        && (!kind || a.kind === kind));
}

function achCategoryName(id) {
    const category = achState.categories.find(c => c.id === id);
    return category ? category.name : '';
}

function achCollectionName(id) {
    const collection = achState.collections.find(c => c.id === id);
    return collection ? collection.name : '';
}

function renderAchievements() {
    document.querySelectorAll('[data-ach-view]').forEach(btn => {
        btn.setAttribute('aria-pressed', String(btn.dataset.achView === achState.view));
    });
    // La vitrina es de diplomas y constancias: el filtro de tipo no aplica
    document.getElementById('achFilterKind').disabled = achState.view === 'showcase';
    const items = filteredAchievements();
    if (achState.view === 'showcase') renderShowcase(items);
    else renderTimeline(items);
    renderUsage();
}

function renderUsage() {
    const usage = achState.usage;
    const node = document.getElementById('achUsage');
    if (!usage || !usage.bytes) {
        node.textContent = '';
        return;
    }
    node.textContent = `Evidencias: ${formatBytes(usage.bytes)} de ${formatBytes(usage.quota)}`;
}

function formatBytes(bytes) {
    if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1).replace(/\.0$/, '')} MB`;
}

function emptyMessage() {
    if (!achState.achievements.length) {
        return el('p', 'ach-empty', 'Aún no hay logros. Empieza con uno: solo necesitas qué fue y cuándo.');
    }
    return el('p', 'ach-empty', 'Nada con estos filtros.');
}

function renderTimeline(items) {
    if (!items.length) {
        achBody.replaceChildren(emptyMessage());
        return;
    }
    const list = el('div', 'ach-timeline');
    let year = null;
    items.forEach(a => {
        const itemYear = achDateParts(a.date).year;
        if (itemYear !== year) {
            year = itemYear;
            list.appendChild(el('h3', 'ach-year', String(year)));
        }
        list.appendChild(achievementRow(a));
    });
    achBody.replaceChildren(list);
}

function achievementRow(a) {
    const row = el('button', `ach-item${a.is_hidden ? ' is-hidden' : ''}`);
    row.type = 'button';
    row.addEventListener('click', () => openAchievementDetail(a.id));
    const thumb = el('span', 'ach-item-thumb');
    fillThumb(thumb, a);
    row.appendChild(thumb);
    const text = el('span', 'ach-item-text');
    const title = el('span', 'ach-item-title', a.title);
    if (a.is_featured) title.prepend(el('span', 'ach-star', '★ '));
    text.appendChild(title);
    const meta = [achDateLabel(a), ACH_KIND_LABELS[a.kind], achCategoryName(a.category_id)];
    if (a.origin === 'auto') meta.push('automático');
    if (a.is_hidden) meta.push('oculto');
    text.appendChild(el('span', 'ach-item-meta', meta.filter(Boolean).join(' · ')));
    const story = a.what_it_shows || a.what_i_did || a.situation;
    if (story) text.appendChild(el('span', 'ach-item-story', story));
    row.appendChild(text);
    return row;
}

// Miniatura de la primera imagen; si solo hay PDF, su ícono; si nada, el del tipo
function fillThumb(node, a) {
    const image = a.files.find(f => f.has_thumb);
    if (image) {
        loadBlobInto(node, `thumb:${image.id}`, `/api/achievements/files/${image.id}/thumb`, a.title);
        return;
    }
    node.textContent = a.files.length ? 'PDF' : (a.kind === 'anecdote' ? '✎' : a.kind === 'milestone' ? '⛰' : '🎓');
    node.classList.toggle('is-pdf', !!a.files.length);
}

async function loadBlobInto(node, key, path, alt) {
    let url = achBlobUrls.get(key);
    if (!url) {
        try {
            url = URL.createObjectURL(await apiFetch(path, { blob: true }));
        } catch (error) {
            node.textContent = '?';
            return;
        }
        achBlobUrls.set(key, url);
    }
    const img = document.createElement('img');
    img.src = url;
    img.alt = alt || '';
    img.loading = 'lazy';
    node.replaceChildren(img);
}

function renderShowcase(items) {
    const diplomas = items.filter(a => a.kind === 'diploma');
    if (!diplomas.length) {
        achBody.replaceChildren(el('p', 'ach-empty', achState.achievements.some(a => a.kind === 'diploma')
            ? 'Nada con estos filtros.'
            : 'Aquí se verán tus diplomas y constancias. Agrega uno con su archivo.'));
        return;
    }
    const wrap = el('div', 'ach-showcase');
    // Primero las colecciones, cada una con sus piezas; después las sueltas
    const groups = new Map();
    diplomas.forEach(a => {
        const key = a.collection_id || 0;
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(a);
    });
    [...groups.keys()].filter(Boolean)
        .sort((x, y) => achCollectionName(x).localeCompare(achCollectionName(y), 'es'))
        .forEach(id => {
            const group = groups.get(id);
            const section = el('section', 'ach-collection');
            const label = group.length === 1 ? '1 pieza' : `${group.length} piezas`;
            section.appendChild(el('h3', 'ach-collection-title', `${achCollectionName(id)} · ${label}`));
            section.appendChild(showcaseGrid(group));
            wrap.appendChild(section);
        });
    if (groups.has(0)) {
        const section = el('section', 'ach-collection');
        if (groups.size > 1) section.appendChild(el('h3', 'ach-collection-title', 'Sin colección'));
        section.appendChild(showcaseGrid(groups.get(0)));
        wrap.appendChild(section);
    }
    achBody.replaceChildren(wrap);
}

function showcaseGrid(items) {
    const grid = el('div', 'ach-grid');
    items.forEach(a => {
        const tile = el('button', `ach-tile${a.is_hidden ? ' is-hidden' : ''}`);
        tile.type = 'button';
        tile.addEventListener('click', () => openAchievementDetail(a.id));
        const thumb = el('span', 'ach-tile-thumb');
        fillThumb(thumb, a);
        tile.appendChild(thumb);
        const title = el('span', 'ach-tile-title', a.title);
        if (a.is_featured) title.prepend(el('span', 'ach-star', '★ '));
        tile.appendChild(title);
        tile.appendChild(el('span', 'ach-item-meta', achDateLabel(a)));
        grid.appendChild(tile);
    });
    return grid;
}

// ============================================
// Detalle
// ============================================

function findAchievement(id) {
    return achState.achievements.find(a => a.id === id);
}

function openAchievementDetail(id) {
    const a = findAchievement(id);
    if (!a) return;
    achState.detailId = id;
    achDetailError.classList.add('hidden');
    closeViewer();
    document.getElementById('achDetailDate').textContent = achDateLabel(a);
    document.getElementById('achDetailTitle').textContent = a.title;
    const tags = document.getElementById('achDetailTags');
    tags.replaceChildren();
    [ACH_KIND_LABELS[a.kind], achCategoryName(a.category_id), achCollectionName(a.collection_id),
        a.is_featured ? '★ Destacado' : '', a.origin === 'auto' ? 'Automático' : '', a.is_hidden ? 'Oculto' : '']
        .filter(Boolean).forEach(text => tags.appendChild(el('span', 'ach-tag', text)));

    const body = document.getElementById('achDetailBody');
    body.replaceChildren();
    [['Situación', a.situation], ['Qué hice', a.what_i_did], ['Qué demuestra', a.what_it_shows]]
        .filter(([, text]) => text)
        .forEach(([label, text]) => {
            body.appendChild(el('h3', 'report-card-title', label));
            body.appendChild(el('p', 'ach-detail-text', text));
        });
    if (a.files.length) {
        body.appendChild(el('h3', 'report-card-title', 'Evidencias'));
        const grid = el('div', 'ach-grid ach-files');
        a.files.forEach(file => {
            const tile = el('button', 'ach-tile');
            tile.type = 'button';
            tile.setAttribute('aria-label', `Abrir ${file.original_name}`);
            const thumb = el('span', 'ach-tile-thumb');
            if (file.has_thumb) loadBlobInto(thumb, `thumb:${file.id}`, `/api/achievements/files/${file.id}/thumb`, file.original_name);
            else {
                thumb.textContent = 'PDF';
                thumb.classList.add('is-pdf');
            }
            tile.appendChild(thumb);
            tile.appendChild(el('span', 'ach-item-meta', file.original_name));
            tile.addEventListener('click', () => openEvidence(file));
            grid.appendChild(tile);
        });
        body.appendChild(grid);
    }
    document.getElementById('achDetailHide').textContent = a.is_hidden ? 'Mostrar' : 'Ocultar';
    showModal(achDetailModal);
}

async function evidenceUrl(file) {
    const key = `file:${file.id}`;
    if (!achBlobUrls.has(key)) {
        achBlobUrls.set(key, URL.createObjectURL(await apiFetch(`/api/achievements/files/${file.id}`, { blob: true })));
    }
    return achBlobUrls.get(key);
}

// Una imagen se ve dentro del detalle; un PDF, en otra pestaña del navegador
async function openEvidence(file) {
    achDetailError.classList.add('hidden');
    const isPdf = file.mime === 'application/pdf';
    // La pestaña se abre antes del primer await: abierta después, el navegador la bloquea
    const tab = isPdf ? window.open('', '_blank') : null;
    try {
        const url = await evidenceUrl(file);
        if (isPdf) {
            if (tab) tab.location.href = url;
            else downloadEvidence(url, file.original_name);
            return;
        }
        const viewer = document.getElementById('achViewer');
        const img = document.getElementById('achViewerImg');
        img.src = url;
        img.alt = file.original_name;
        viewer.hidden = false;
    } catch (error) {
        if (tab) tab.close();
        showError(achDetailError, `No se pudo abrir el archivo: ${error.message}`);
    }
}

function downloadEvidence(url, name) {
    const link = document.createElement('a');
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    link.remove();
}

function closeViewer() {
    document.getElementById('achViewer').hidden = true;
    document.getElementById('achViewerImg').removeAttribute('src');
}

async function toggleHidden() {
    const a = findAchievement(achState.detailId);
    if (!a) return;
    try {
        const updated = await apiFetch(`/api/achievements/${a.id}`, { method: 'PATCH', json: { is_hidden: !a.is_hidden } });
        replaceAchievement(updated);
        openAchievementDetail(updated.id);
        renderAchievements();
    } catch (error) {
        showError(achDetailError, error.message);
    }
}

async function deleteAchievement() {
    const a = findAchievement(achState.detailId);
    if (!a) return;
    const message = a.origin === 'auto'
        ? `«${a.title}» desaparecerá y no volverá a crearse. Si solo quieres quitarlo de la vista, usa Ocultar.`
        : `Se borrarán «${a.title}» y sus ${a.files.length} evidencias. No se puede deshacer.`;
    if (!await confirmDialog(message, { title: '¿Borrar este logro?', confirmLabel: 'Borrar', danger: true })) return;
    try {
        await apiFetch(`/api/achievements/${a.id}`, { method: 'DELETE' });
    } catch (error) {
        showError(achDetailError, error.message);
        return;
    }
    a.files.forEach(f => forgetBlob(f.id));
    closeAchModal(achDetailModal);
    await loadAchievements();
}

function replaceAchievement(updated) {
    const index = achState.achievements.findIndex(a => a.id === updated.id);
    if (index >= 0) achState.achievements[index] = updated;
    else achState.achievements.push(updated);
}

function forgetBlob(fileId) {
    ['thumb', 'file'].forEach(prefix => {
        const key = `${prefix}:${fileId}`;
        if (achBlobUrls.has(key)) {
            URL.revokeObjectURL(achBlobUrls.get(key));
            achBlobUrls.delete(key);
        }
    });
}

// ============================================
// Formulario (nuevo o editar)
// ============================================

function fillFormSelects(a) {
    const category = document.getElementById('achCategory');
    category.replaceChildren(new Option('Sin categoría', ''));
    achState.categories.forEach(c => category.add(new Option(c.name, String(c.id))));
    category.value = a && a.category_id ? String(a.category_id) : '';

    const collection = document.getElementById('achCollection');
    collection.replaceChildren(new Option('Sin colección', ''));
    achState.collections.forEach(c => collection.add(new Option(c.name, String(c.id))));
    collection.add(new Option('+ Nueva colección…', ACH_NEW_COLLECTION));
    collection.value = a && a.collection_id ? String(a.collection_id) : '';
    achForm.querySelector('.ach-new-collection').hidden = true;

    const month = document.getElementById('achMonth');
    if (!month.options.length) {
        ACH_MONTHS.forEach((name, i) => month.add(new Option(name, String(i + 1).padStart(2, '0'))));
    }
}

function openAchievementForm(id = null) {
    const a = id ? findAchievement(id) : null;
    achState.editingId = a ? a.id : null;
    achForm.reset();
    achFormError.classList.add('hidden');
    fillFormSelects(a);
    document.getElementById('achFormTitle').textContent = a ? 'Editar logro' : 'Nuevo logro';
    document.getElementById('achDay').max = getDateKey(new Date());
    const today = getDateKey(new Date());
    if (a) {
        document.getElementById('achTitle').value = a.title;
        const { year, month } = achDateParts(a.date);
        setPrecision(a.date_precision);
        if (a.date_precision === 'day') document.getElementById('achDay').value = a.date;
        document.getElementById('achYear').value = String(year);
        document.getElementById('achMonth').value = String(month).padStart(2, '0');
        document.getElementById('achKind').value = a.kind;
        document.getElementById('achSituation').value = a.situation || '';
        document.getElementById('achDid').value = a.what_i_did || '';
        document.getElementById('achShows').value = a.what_it_shows || '';
        document.getElementById('achFeatured').checked = a.is_featured;
    } else {
        setPrecision('day');
        document.getElementById('achDay').value = today;
        const { year, month } = achDateParts(today);
        document.getElementById('achYear').value = String(year);
        document.getElementById('achMonth').value = String(month).padStart(2, '0');
    }
    document.getElementById('achStory').open = !!(a && (a.kind === 'anecdote' || a.situation || a.what_i_did || a.what_it_shows));
    renderExistingFiles(a);
    const usage = achState.usage;
    document.getElementById('achFilesHint').textContent = usage
        ? `Hasta ${Math.round(usage.file_max / (1024 * 1024))} MB cada uno.` : '';
    showModal(achModal);
    document.getElementById('achTitle').focus();
}

function renderExistingFiles(a) {
    const list = document.getElementById('achExistingFiles');
    list.replaceChildren();
    (a ? a.files : []).forEach(file => {
        const item = el('li', 'ach-file-row');
        item.appendChild(el('span', 'ach-file-name', file.original_name));
        const remove = el('button', 'ach-file-remove', '×');
        remove.type = 'button';
        remove.setAttribute('aria-label', `Quitar ${file.original_name}`);
        remove.addEventListener('click', () => removeEvidence(a.id, file));
        item.appendChild(remove);
        list.appendChild(item);
    });
}

async function removeEvidence(achievementId, file) {
    if (!await confirmDialog(`Se borrará «${file.original_name}». No se puede deshacer.`,
        { title: '¿Quitar esta evidencia?', confirmLabel: 'Quitar', danger: true })) return;
    try {
        await apiFetch(`/api/achievements/files/${file.id}`, { method: 'DELETE' });
    } catch (error) {
        showError(achFormError, error.message);
        return;
    }
    forgetBlob(file.id);
    const a = findAchievement(achievementId);
    if (a) {
        a.files = a.files.filter(f => f.id !== file.id);
        renderExistingFiles(a);
    }
    if (achState.usage) achState.usage.bytes = Math.max(0, achState.usage.bytes - file.size_bytes);
    renderAchievements();
}

async function collectionIdForSave() {
    const value = document.getElementById('achCollection').value;
    if (value !== ACH_NEW_COLLECTION) return value ? Number(value) : null;
    const name = document.getElementById('achNewCollection').value.trim();
    if (!name) throw new Error('Escribe el nombre de la colección nueva');
    const created = await apiFetch('/api/achievements/collections', { method: 'POST', json: { name } });
    achState.collections.push(created);
    return created.id;
}

async function saveAchievement(event) {
    event.preventDefault();
    achFormError.classList.add('hidden');
    const title = document.getElementById('achTitle').value.trim();
    const date = readFormDate();
    if (!title) return showError(achFormError, 'Escribe qué lograste.');
    if (!date) return showError(achFormError, achState.precision === 'day' ? 'Elige la fecha.' : 'Escribe el año (4 cifras).');
    const saveBtn = document.getElementById('achSaveBtn');
    saveBtn.disabled = true;
    let saved;
    try {
        const category = document.getElementById('achCategory').value;
        const payload = {
            title, date,
            kind: document.getElementById('achKind').value,
            category_id: category ? Number(category) : null,
            collection_id: await collectionIdForSave(),
            situation: document.getElementById('achSituation').value,
            what_i_did: document.getElementById('achDid').value,
            what_it_shows: document.getElementById('achShows').value,
            is_featured: document.getElementById('achFeatured').checked,
        };
        saved = achState.editingId
            ? await apiFetch(`/api/achievements/${achState.editingId}`, { method: 'PATCH', json: payload })
            : await apiFetch('/api/achievements', { method: 'POST', json: payload });
        achState.editingId = saved.id;   // si una evidencia falla, volver a guardar no lo duplica
        replaceAchievement(saved);
        await uploadSelectedFiles(saved.id);
    } catch (error) {
        showError(achFormError, error.message);
        return;
    } finally {
        saveBtn.disabled = false;
    }
    closeAchModal(achModal);
    await loadAchievements();
}

// Una por una: si alguna se rechaza, las anteriores ya quedaron y el error dice cuál
async function uploadSelectedFiles(achievementId) {
    const input = document.getElementById('achFiles');
    const files = [...input.files];
    for (const file of files) {
        const data = new FormData();
        data.append('file', file, file.name);
        try {
            await apiFetch(`/api/achievements/${achievementId}/files`, { method: 'POST', body: data });
        } catch (error) {
            input.value = '';
            await loadAchievements();
            renderExistingFiles(findAchievement(achievementId));
            throw new Error(`«${file.name}»: ${error.message}`);
        }
    }
}

// ============================================
// SOS
// ============================================

async function openSos() {
    achState.sosSeen = [];
    document.getElementById('sosNote').value = '';
    document.getElementById('sosNoteStatus').textContent = '';
    document.getElementById('sosNotesPast').open = false;
    document.getElementById('sosActionsEdit').open = false;
    document.getElementById('sosAchievements').replaceChildren(el('p', 'ach-empty', 'Buscando…'));
    showModal(sosModal);
    await loadSos({ full: true });
}

async function loadSos({ full = false } = {}) {
    let data;
    try {
        data = await apiFetch(`/api/achievements/sos?exclude=${achState.sosSeen.join(',')}`);
    } catch (error) {
        document.getElementById('sosAchievements').replaceChildren(el('p', 'ach-empty', error.message));
        return;
    }
    if (data.restarted) achState.sosSeen = [];
    achState.sosSeen.push(...data.achievements.map(a => a.id));
    document.getElementById('sosRestarted').hidden = !data.restarted;
    renderSosAchievements(data.achievements);
    if (full) {
        document.getElementById('sosFactBlock').hidden = !data.fact;
        document.getElementById('sosFact').textContent = data.fact || '';
        document.getElementById('sosActionBlock').hidden = !data.action;
        document.getElementById('sosAction').textContent = data.action ? data.action.text : '';
    }
}

function renderSosAchievements(items) {
    const list = document.getElementById('sosAchievements');
    document.getElementById('sosMore').hidden = !items.length;
    if (!items.length) {
        list.replaceChildren(el('p', 'ach-empty', 'Todavía no hay logros guardados. Cuando agregues alguno, aparecerá aquí.'));
        return;
    }
    list.replaceChildren(...items.map(a => {
        const card = el('article', 'sos-card');
        const thumb = el('span', 'ach-item-thumb');
        fillThumb(thumb, a);
        card.appendChild(thumb);
        const text = el('div', 'ach-item-text');
        text.appendChild(el('span', 'ach-item-title', a.title));
        text.appendChild(el('span', 'ach-item-meta', achDateLabel(a)));
        if (a.situation) text.appendChild(el('p', 'sos-story', `Cómo estaba: ${a.situation}`));
        if (a.what_i_did) text.appendChild(el('p', 'sos-story', `Qué hice: ${a.what_i_did}`));
        if (a.what_it_shows) text.appendChild(el('p', 'sos-story sos-shows', `Demuestra: ${a.what_it_shows}`));
        card.appendChild(text);
        return card;
    }));
}

async function saveSosNote(event) {
    event.preventDefault();
    const error = document.getElementById('sosNoteError');
    const status = document.getElementById('sosNoteStatus');
    error.classList.add('hidden');
    const body = document.getElementById('sosNote').value.trim();
    if (!body) return showError(error, 'La nota está vacía.');
    try {
        await apiFetch('/api/achievements/sos/notes', {
            method: 'POST', json: { note_date: getDateKey(new Date()), body },
        });
    } catch (err) {
        showError(error, err.message);
        return;
    }
    document.getElementById('sosNote').value = '';
    status.textContent = 'Guardada.';
    if (document.getElementById('sosNotesPast').open) loadSosNotes();
}

async function loadSosNotes() {
    const list = document.getElementById('sosNotesList');
    let notes;
    try {
        notes = await apiFetch('/api/achievements/sos/notes');
    } catch (error) {
        list.replaceChildren(el('li', 'ach-empty', error.message));
        return;
    }
    if (!notes.length) {
        list.replaceChildren(el('li', 'ach-empty', 'Sin notas todavía.'));
        return;
    }
    list.replaceChildren(...notes.map(note => {
        const item = el('li', 'sos-note');
        const { year, month, day } = achDateParts(note.note_date);
        item.appendChild(el('span', 'ach-item-meta',
            new Date(year, month - 1, day).toLocaleDateString('es-MX', { day: 'numeric', month: 'short', year: 'numeric' })));
        item.appendChild(el('p', 'ach-detail-text', note.body));
        const remove = el('button', 'ach-file-remove', '×');
        remove.type = 'button';
        remove.setAttribute('aria-label', 'Borrar esta nota');
        remove.addEventListener('click', async () => {
            if (!await confirmDialog('Se borrará esta nota.', { title: '¿Borrar la nota?', confirmLabel: 'Borrar', danger: true })) return;
            try {
                await apiFetch(`/api/achievements/sos/notes/${note.id}`, { method: 'DELETE' });
            } catch (error) {
                return;
            }
            loadSosNotes();
        });
        item.appendChild(remove);
        return item;
    }));
}

async function loadSosActions() {
    const list = document.getElementById('sosActionsList');
    const error = document.getElementById('sosActionError');
    error.classList.add('hidden');
    let actions;
    try {
        actions = await apiFetch('/api/achievements/sos/actions');
    } catch (err) {
        showError(error, err.message);
        return;
    }
    list.replaceChildren(...actions.map(action => {
        const item = el('li', 'sos-note');
        item.appendChild(el('span', 'ach-detail-text', action.text));
        const remove = el('button', 'ach-file-remove', '×');
        remove.type = 'button';
        remove.setAttribute('aria-label', `Quitar «${action.text}»`);
        remove.addEventListener('click', async () => {
            error.classList.add('hidden');
            try {
                await apiFetch(`/api/achievements/sos/actions/${action.id}`, { method: 'DELETE' });
            } catch (err) {
                showError(error, err.message);
                return;
            }
            loadSosActions();
        });
        item.appendChild(remove);
        return item;
    }));
}

async function addSosAction(event) {
    event.preventDefault();
    const input = document.getElementById('sosActionText');
    const error = document.getElementById('sosActionError');
    error.classList.add('hidden');
    const text = input.value.trim();
    if (!text) return;
    try {
        await apiFetch('/api/achievements/sos/actions', { method: 'POST', json: { text } });
    } catch (err) {
        showError(error, err.message);
        return;
    }
    input.value = '';
    loadSosActions();
}

// ============================================
// Modales, eventos y hooks
// ============================================

function closeAchModal(modal) {
    if (modal === achDetailModal) closeViewer();
    hideModal(modal);
}

function initAchievements() {
    document.getElementById('achAddBtn').addEventListener('click', () => openAchievementForm());
    document.getElementById('achSosBtn').addEventListener('click', openSos);
    document.querySelectorAll('[data-ach-view]').forEach(btn => {
        btn.addEventListener('click', () => {
            achState.view = btn.dataset.achView;
            renderAchievements();
        });
    });
    ['achFilterCategory', 'achFilterKind', 'achShowHidden'].forEach(id => {
        document.getElementById(id).addEventListener('change', renderAchievements);
    });
    document.querySelectorAll('.ach-precision [data-precision]').forEach(btn => {
        btn.addEventListener('click', () => setPrecision(btn.dataset.precision));
    });
    document.getElementById('achCollection').addEventListener('change', (event) => {
        const isNew = event.target.value === ACH_NEW_COLLECTION;
        achForm.querySelector('.ach-new-collection').hidden = !isNew;
        if (isNew) document.getElementById('achNewCollection').focus();
    });
    document.getElementById('achKind').addEventListener('change', (event) => {
        if (event.target.value === 'anecdote') document.getElementById('achStory').open = true;
    });
    achForm.addEventListener('submit', saveAchievement);

    document.getElementById('achDetailEdit').addEventListener('click', () => {
        const id = achState.detailId;
        closeAchModal(achDetailModal);
        openAchievementForm(id);
    });
    document.getElementById('achDetailHide').addEventListener('click', toggleHidden);
    document.getElementById('achDetailDelete').addEventListener('click', deleteAchievement);
    document.getElementById('achViewerClose').addEventListener('click', closeViewer);

    document.getElementById('sosMore').addEventListener('click', () => loadSos());
    document.getElementById('sosNoteForm').addEventListener('submit', saveSosNote);
    document.getElementById('sosActionForm').addEventListener('submit', addSosAction);
    document.getElementById('sosNotesPast').addEventListener('toggle', (event) => {
        if (event.target.open) loadSosNotes();
    });
    document.getElementById('sosActionsEdit').addEventListener('toggle', (event) => {
        if (event.target.open) loadSosActions();
    });

    [achModal, achDetailModal, sosModal].forEach(modal => {
        modal.querySelectorAll('[data-ach-close]').forEach(btn => {
            btn.addEventListener('click', () => closeAchModal(modal));
        });
    });
    document.addEventListener('keydown', (event) => {
        if (event.key !== 'Escape' || !document.getElementById('confirmModal').classList.contains('hidden')) return;
        const open = [achModal, achDetailModal, sosModal].find(modal => !modal.classList.contains('hidden'));
        if (open) closeAchModal(open);
    });
}

function resetAchievements() {
    [achModal, achDetailModal, sosModal].forEach(closeAchModal);
    achBlobUrls.forEach(url => URL.revokeObjectURL(url));
    achBlobUrls.clear();
    Object.assign(achState, { loaded: false, achievements: [], categories: [], collections: [], usage: null,
        editingId: null, detailId: null, sosSeen: [] });
    achBody.replaceChildren();
    setViewVisible('achievements', false);
}

window.appInitHooks.push(initAchievements);
// Primero, como Costos: la pestaña aparece con las demás
window.appDataHooks.unshift(applyAchievementsModule);
window.modulesChangedHooks.push(() => {
    applyAchievementsModule();
    if (isAchievementsVisible()) loadAchievements();
});
// Al entrar se pide de nuevo: los hitos dependen del tiempo y los hábitos
window.viewChangedHooks.push(viewId => {
    if (viewId === 'achievements') loadAchievements();
});
// Al principio: ocultar la vista pasa por goToView(), que recuerda la pestaña
window.appLogoutHooks.unshift(resetAchievements);
