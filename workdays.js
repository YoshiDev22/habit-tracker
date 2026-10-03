// ============================================
// Días festivos y huso horario (⚙️ Configuración)
// ============================================
//
// Épica 30, Fase 3. Deciden qué días son hábiles en las métricas y reportes, a
// qué hora local pasó cada sesión, y qué festivos congelan la racha (los que
// se descansan: los oficiales con "Descanso" marcado y los días libres propios).
//
// Se guardan en este dispositivo (localStorage.work_calendar_cache): al abrir
// la sección o pintar el calendario no se vuelven a pedir. "↻ Actualizar
// festivos" los pide de nuevo, y cualquier cambio los refresca. La primera vez
// que la cuenta entra sin huso guardado, se guarda el del navegador.

const workCalendarEl = document.getElementById('workCalendar');
const workTimezoneEl = document.getElementById('workTimezone');
const workCountryEl = document.getElementById('workCountry');
const workYearLabel = document.getElementById('workYearLabel');
const workOfficialEl = document.getElementById('workOfficialDays');
const workOwnEl = document.getElementById('workOwnDays');
const workAddForm = document.getElementById('workAddForm');
const workAddDate = document.getElementById('workAddDate');
const workAddName = document.getElementById('workAddName');
const workErrorEl = document.getElementById('workCalendarError');
const WORK_CACHE_KEY = 'work_calendar_cache';

const workState = { year: new Date().getFullYear() };
const workYearRequests = new Map();   // año -> promesa en curso (una a la vez)

// ============================================
// Caché en este dispositivo: {settings: {timezone, country}, years: {año: datos}}
// ============================================

function readWorkCache() {
    try {
        const cache = JSON.parse(localStorage.getItem(WORK_CACHE_KEY) || 'null');
        return cache && cache.years ? cache : { settings: null, years: {} };
    } catch (error) {
        return { settings: null, years: {} };
    }
}

function writeWorkCache(cache) {
    try {
        localStorage.setItem(WORK_CACHE_KEY, JSON.stringify(cache));
    } catch (error) {
        // Sin almacenamiento: se piden cada vez, nada más
    }
}

function rememberSettings(settings) {
    const cache = readWorkCache();
    // Otro país, otros festivos: los años guardados ya no valen
    if (cache.settings && cache.settings.country !== settings.country) cache.years = {};
    cache.settings = { timezone: settings.timezone, country: settings.country };
    writeWorkCache(cache);
}

function cachedYear(year) {
    return readWorkCache().years[String(year)] || null;
}

// Pide el año al backend (festivos oficiales + días marcados) y lo guarda
function fetchYearDays(year) {
    if (!workYearRequests.has(year)) {
        const request = apiFetch(`/api/days?year=${year}`)
            .then(data => {
                const cache = readWorkCache();
                cache.years[String(year)] = data;
                writeWorkCache(cache);
                return data;
            })
            .finally(() => workYearRequests.delete(year));
        workYearRequests.set(year, request);
    }
    return workYearRequests.get(year);
}

// Los festivos que se descansan de un año, fecha -> nombre, para el calendario.
// Si el año no está en caché devuelve un mapa vacío, lo pide y llama a
// `onLoaded` cuando llega (el calendario se vuelve a pintar).
function restedHolidaysFor(year, onLoaded) {
    const data = cachedYear(year);
    if (!data) {
        if (getToken() && !workYearRequests.has(year)) {
            fetchYearDays(year).then(() => { if (onLoaded) onLoaded(); }).catch(() => {});
        }
        return new Map();
    }
    const names = new Map();
    const worked = new Set(data.own.filter(d => d.kind === 'laboral').map(d => d.date));
    data.official.forEach(day => {
        if (!worked.has(day.date)) names.set(day.date, day.name);
    });
    data.own.filter(d => d.kind === 'libre').forEach(day => names.set(day.date, day.name || 'Día libre'));
    return names;
}

// ============================================
// Al entrar
// ============================================

function browserTimezone() {
    try {
        return Intl.DateTimeFormat().resolvedOptions().timeZone || null;
    } catch (error) {
        return null;
    }
}

// Sugerencias del campo de huso: el del navegador y los de México
function fillTimezoneList() {
    const list = document.getElementById('workTimezoneList');
    const zones = new Set([browserTimezone(), 'America/Mexico_City', 'America/Monterrey', 'America/Cancun',
        'America/Chihuahua', 'America/Hermosillo', 'America/Mazatlan', 'America/Tijuana', 'UTC'].filter(Boolean));
    list.replaceChildren(...[...zones].map(zone => new Option(zone, zone)));
}

// Si la cuenta nunca guardó su huso, se guarda el del navegador
async function ensureWorkSettings() {
    try {
        let settings = await apiFetch('/api/days/settings');
        const zone = browserTimezone();
        if (!settings.configured && zone) {
            settings = await apiFetch('/api/days/settings', { method: 'PUT', json: { timezone: zone } });
        }
        rememberSettings(settings);
    } catch (error) {
        console.error('No se pudo guardar el huso horario:', error);
    }
}

// ============================================
// La sección de Configuración
// ============================================

function shortDayLabel(dateKey) {
    const [year, month, day] = dateKey.split('-').map(Number);
    return new Date(year, month - 1, day).toLocaleDateString('es-MX', { weekday: 'short', day: 'numeric', month: 'short' });
}

// Muestra lo guardado en el dispositivo; solo pide al backend lo que falte, o
// todo con `force` (↻, o tras un cambio)
async function loadWorkCalendar({ force = false } = {}) {
    workErrorEl.classList.add('hidden');
    workYearLabel.textContent = String(workState.year);
    let { settings } = readWorkCache();
    let days = cachedYear(workState.year);
    if (settings) showWorkSettings(settings);
    if (days) renderWorkDays(days);
    try {
        if (force || !settings) {
            settings = await apiFetch('/api/days/settings');
            rememberSettings(settings);
            showWorkSettings(settings);
        }
        if (force || !days) {
            days = await fetchYearDays(workState.year);
            renderWorkDays(days);
        }
    } catch (error) {
        showError(workErrorEl, error.message);
    }
}

function showWorkSettings(settings) {
    // No pisar lo que el usuario está escribiendo
    if (document.activeElement !== workTimezoneEl) workTimezoneEl.value = settings.timezone;
    if (document.activeElement !== workCountryEl) workCountryEl.value = settings.country;
}

function renderWorkDays(days) {
    const markByDate = new Map(days.own.map(d => [d.date, d]));
    workState.markByDate = markByDate;
    if (days.official.length === 0) {
        workOfficialEl.replaceChildren(el('li', 'work-empty',
            `No hay festivos de ${days.country} para ${days.year}, o el servicio de festivos no respondió (prueba ↻).`));
    } else {
        workOfficialEl.replaceChildren(...days.official.map(day => {
            const item = el('li', `work-day${day.observed ? '' : ' worked'}`);
            item.appendChild(el('span', 'work-day-name', `🎉 ${shortDayLabel(day.date)} · ${day.name}`));
            // Marcada: lo descansas (no es hábil y no corta la racha). Desmarcada: lo trabajas.
            const label = el('label', 'work-day-label');
            label.title = 'Desmárcalo si ese día trabajas: contará como día hábil';
            const box = document.createElement('input');
            box.type = 'checkbox';
            box.checked = day.observed;
            box.dataset.date = day.date;
            box.className = 'work-rest';
            label.append(box, el('span', 'work-day-hint', 'Descanso'));
            item.appendChild(label);
            return item;
        }));
    }
    const free = days.own.filter(d => d.kind === 'libre');
    if (free.length === 0) {
        workOwnEl.replaceChildren(el('li', 'work-empty', 'Aún no agregas días libres.'));
    } else {
        workOwnEl.replaceChildren(...free.map(day => {
            const item = el('li', 'work-day');
            item.append(el('span', 'work-day-name', `🎉 ${shortDayLabel(day.date)}${day.name ? ` · ${day.name}` : ''}`));
            const remove = el('button', 'cost-delete work-remove', '×');
            remove.type = 'button';
            remove.dataset.id = String(day.id);
            remove.setAttribute('aria-label', `Quitar ${day.name || day.date}`);
            item.appendChild(remove);
            return item;
        }));
    }
}

// Tras un cambio: lo de este año al día, y el calendario y la racha también
async function workAction(request) {
    workErrorEl.classList.add('hidden');
    try {
        await request();
    } catch (error) {
        showError(workErrorEl, error.message);
    }
    await loadWorkCalendar({ force: true });
    if (typeof refreshStreakFromAPI === 'function') await refreshStreakFromAPI();
    if (typeof renderCalendar === 'function') renderCalendar();
}

async function saveWorkSetting(field, value) {
    await workAction(async () => {
        const settings = await apiFetch('/api/days/settings', { method: 'PUT', json: { [field]: value } });
        rememberSettings(settings);
    });
}

workTimezoneEl.addEventListener('change', () => {
    const value = workTimezoneEl.value.trim();
    if (value) saveWorkSetting('timezone', value);
});
workCountryEl.addEventListener('change', () => {
    const value = workCountryEl.value.trim().toUpperCase();
    if (value) saveWorkSetting('country', value);
});

// "Descanso": desmarcarlo marca el festivo como laboral; volver a marcarlo quita esa marca
workOfficialEl.addEventListener('change', (event) => {
    const box = event.target.closest('.work-rest');
    if (!box) return;
    const mark = workState.markByDate && workState.markByDate.get(box.dataset.date);
    if (!box.checked) {
        workAction(() => apiFetch('/api/days', { method: 'POST', json: { date: box.dataset.date, kind: 'laboral' } }));
    } else if (mark) {
        workAction(() => apiFetch(`/api/days/${mark.id}`, { method: 'DELETE' }));
    }
});

workOwnEl.addEventListener('click', (event) => {
    const remove = event.target.closest('.work-remove');
    if (remove) workAction(() => apiFetch(`/api/days/${remove.dataset.id}`, { method: 'DELETE' }));
});

workAddForm.addEventListener('submit', (event) => {
    event.preventDefault();
    if (!workAddDate.value) return;
    const date = workAddDate.value;
    const name = workAddName.value.trim() || null;
    workAction(async () => {
        await apiFetch('/api/days', { method: 'POST', json: { date, kind: 'libre', name } });
        workAddName.value = '';
        // El año de la lista sigue al día agregado
        workState.year = Number(date.slice(0, 4));
    });
});

document.getElementById('workYearPrev').addEventListener('click', () => { workState.year -= 1; loadWorkCalendar(); });
document.getElementById('workYearNext').addEventListener('click', () => { workState.year += 1; loadWorkCalendar(); });
document.getElementById('workRefresh').addEventListener('click', async () => {
    await loadWorkCalendar({ force: true });
    if (typeof renderCalendar === 'function') renderCalendar();
});

// Al desplegar la sección: lo guardado al instante, lo que falte de la red
workCalendarEl.addEventListener('toggle', () => {
    if (workCalendarEl.open) loadWorkCalendar();
});

fillTimezoneList();
window.appDataHooks.push(ensureWorkSettings);
// La caché es de la cuenta: quien entre después pide la suya
window.appLogoutHooks.push(() => {
    try { localStorage.removeItem(WORK_CACHE_KEY); } catch (error) { /* nada que limpiar */ }
    workYearRequests.clear();
    workState.year = new Date().getFullYear();
});
