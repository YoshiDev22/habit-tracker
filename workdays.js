// ============================================
// Calendario de trabajo: huso horario, país y días no laborables
// ============================================
//
// En Mi perfil (épica 30, Fase 3). Lo usan las métricas (/api/metrics) y los
// reportes: qué días eran hábiles y a qué hora local pasó cada sesión. La
// primera vez que la cuenta entra sin huso guardado, se guarda el del
// navegador. Los festivos oficiales los trae el backend de Nager.Date; aquí
// solo se marcan "Lo trabajo" (laboral) o se agregan días libres propios.

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

const workState = { year: new Date().getFullYear(), own: [] };

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

// Al entrar: si la cuenta nunca guardó su huso, se guarda el del navegador
async function ensureWorkSettings() {
    try {
        const settings = await apiFetch('/api/days/settings');
        const zone = browserTimezone();
        if (!settings.configured && zone) {
            await apiFetch('/api/days/settings', { method: 'PUT', json: { timezone: zone } });
        }
    } catch (error) {
        console.error('No se pudo guardar el huso horario:', error);
    }
}

function shortDayLabel(dateKey) {
    const [year, month, day] = dateKey.split('-').map(Number);
    return new Date(year, month - 1, day).toLocaleDateString('es-MX', { weekday: 'short', day: 'numeric', month: 'short' });
}

async function loadWorkCalendar() {
    workErrorEl.classList.add('hidden');
    workYearLabel.textContent = String(workState.year);
    try {
        const [settings, days] = await Promise.all([
            apiFetch('/api/days/settings'),
            apiFetch(`/api/days?year=${workState.year}`),
        ]);
        workTimezoneEl.value = settings.timezone;
        workCountryEl.value = settings.country;
        workState.own = days.own;
        renderWorkDays(days);
    } catch (error) {
        showError(workErrorEl, error.message);
    }
}

function renderWorkDays(days) {
    const markByDate = new Map(days.own.map(d => [d.date, d]));
    if (days.official.length === 0) {
        workOfficialEl.replaceChildren(el('li', 'work-empty',
            `No hay festivos de ${days.country} para ${days.year} (o el servicio de festivos no respondió).`));
    } else {
        workOfficialEl.replaceChildren(...days.official.map(day => {
            const item = el('li', `work-day${day.observed ? '' : ' worked'}`);
            const name = el('span', 'work-day-name', `${shortDayLabel(day.date)} · ${day.name}`);
            const label = el('label', 'work-day-label');
            const box = document.createElement('input');
            box.type = 'checkbox';
            box.checked = !day.observed;
            box.dataset.date = day.date;
            box.className = 'work-worked';
            label.append(box, el('span', 'work-day-hint', 'Lo trabajo'));
            item.append(name, label);
            return item;
        }));
    }
    const free = days.own.filter(d => d.kind === 'libre');
    if (free.length === 0) {
        workOwnEl.replaceChildren(el('li', 'work-empty', 'Aún no agregas días libres.'));
    } else {
        workOwnEl.replaceChildren(...free.map(day => {
            const item = el('li', 'work-day');
            item.append(el('span', '', `${shortDayLabel(day.date)}${day.name ? ` · ${day.name}` : ''}`));
            const remove = el('button', 'cost-delete work-remove', '×');
            remove.type = 'button';
            remove.dataset.id = String(day.id);
            remove.setAttribute('aria-label', `Quitar ${day.name || day.date}`);
            item.appendChild(remove);
            return item;
        }));
    }
    // Para que el estado de cada festivo se lea del mismo lugar al guardar
    workState.markByDate = markByDate;
}

async function workAction(request) {
    workErrorEl.classList.add('hidden');
    try {
        await request();
    } catch (error) {
        showError(workErrorEl, error.message);
    }
    await loadWorkCalendar();
}

async function saveWorkSetting(field, value) {
    await workAction(() => apiFetch('/api/days/settings', { method: 'PUT', json: { [field]: value } }));
}

workTimezoneEl.addEventListener('change', () => {
    const value = workTimezoneEl.value.trim();
    if (value) saveWorkSetting('timezone', value);
});
workCountryEl.addEventListener('change', () => {
    const value = workCountryEl.value.trim().toUpperCase();
    if (value) saveWorkSetting('country', value);
});

// "Lo trabajo": marca el festivo como laboral; desmarcar quita la marca
workOfficialEl.addEventListener('change', (event) => {
    const box = event.target.closest('.work-worked');
    if (!box) return;
    const mark = workState.markByDate && workState.markByDate.get(box.dataset.date);
    if (box.checked) {
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

// Se carga al desplegarlo: los festivos pueden pedir una llamada a Nager.Date
workCalendarEl.addEventListener('toggle', () => {
    if (workCalendarEl.open) loadWorkCalendar();
});

fillTimezoneList();
window.appDataHooks.push(ensureWorkSettings);
window.appLogoutHooks.push(() => {
    workCalendarEl.open = false;
    workState.year = new Date().getFullYear();
});
