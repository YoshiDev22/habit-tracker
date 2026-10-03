// ============================================
// ⚙️ Configuración
// ============================================
//
// Un solo modal (#habitsSetupModal) con secciones que se despliegan: Hábitos,
// Días de descanso, Vacaciones, Días festivos y huso horario, Módulos,
// Pomodoro y Pantalla. showHabitsSetup() (habits.js) lo llena y lo muestra, y
// al final llama a onSettingsOpened(). Cada sección guarda lo suyo: los hábitos
// con "Guardar Hábitos" (el pie solo se ve con Hábitos abierto); lo demás, al
// tocarlo. Qué secciones quedaron abiertas se recuerda en este dispositivo
// (localStorage.settings_open).

const SETTINGS_OPEN_KEY = 'settings_open';
const settingsSections = [...habitsSetupModal.querySelectorAll('.settings-section')];
const settingsFooter = habitsSetupModal.querySelector('.setup-footer');

function readOpenSections() {
    try {
        const saved = JSON.parse(localStorage.getItem(SETTINGS_OPEN_KEY) || 'null');
        return Array.isArray(saved) ? saved : ['habits'];
    } catch (error) {
        return ['habits'];
    }
}

function saveOpenSections() {
    const open = settingsSections.filter(section => section.open).map(section => section.dataset.section);
    try {
        localStorage.setItem(SETTINGS_OPEN_KEY, JSON.stringify(open));
    } catch (error) {
        // Sin almacenamiento: la próxima vez abre con lo de siempre
    }
}

// "Guardar Hábitos" es solo de la sección Hábitos
function updateSettingsFooter() {
    const habits = habitsSetupModal.querySelector('[data-section="habits"]');
    settingsFooter.hidden = !(habits.open && !habits.hidden);
}

function setOpenSections(names) {
    // Sus eventos toggle vuelven a guardar lo mismo (más la sección que se pidió abrir)
    settingsSections.forEach(section => { section.open = names.includes(section.dataset.section); });
    updateSettingsFooter();
}

// Abre Configuración con una sección desplegada (y a la vista). La promesa se
// cumple con todo ya lleno.
let settingsFocusSection = null;
function openSettings(section) {
    settingsFocusSection = section;
    return showHabitsSetup();
}

// Lo llama showHabitsSetup() con el modal ya visible
function onSettingsOpened({ welcome = false } = {}) {
    let open = readOpenSections();
    if (welcome && !open.includes('habits')) open = [...open, 'habits'];
    if (settingsFocusSection && !open.includes(settingsFocusSection)) open = [...open, settingsFocusSection];
    setOpenSections(open);
    // Si ya estaba desplegada no hay toggle que la cargue (workdays.js)
    if (open.includes('holidays') && typeof loadWorkCalendar === 'function') loadWorkCalendar();
    fillPomoSettings();
    syncModuleSettings();
    if (settingsFocusSection) {
        const target = habitsSetupModal.querySelector(`[data-section="${settingsFocusSection}"]`);
        // Sin scrollIntoView(): desplazaría también las vistas de detrás (CLAUDE.md)
        const scroller = habitsSetupModal.querySelector('.setup-scroll');
        if (target) scroller.scrollTop += target.getBoundingClientRect().top - scroller.getBoundingClientRect().top;
        settingsFocusSection = null;
    }
}

settingsSections.forEach(section => {
    section.addEventListener('toggle', () => {
        if (section.dataset.section === 'habits') updateSettingsFooter();
        saveOpenSections();
    });
});

document.getElementById('settingsClose').addEventListener('click', closeHabitsSetup);

// ============================================
// Pomodoro: duraciones de la cuenta (users.pomodoro_*_seconds, null = por defecto)
// ============================================

const POMO_SETTING_FIELDS = [
    { id: 'configPomoFocus', field: 'pomodoro_focus_seconds' },
    { id: 'configPomoShort', field: 'pomodoro_short_break_seconds' },
    { id: 'configPomoLong', field: 'pomodoro_long_break_seconds' },
];
const configPomoError = document.getElementById('configPomoError');
const configPomoStatus = document.getElementById('configPomoStatus');

function fillPomoSettings() {
    POMO_SETTING_FIELDS.forEach(({ id, field }) => {
        const seconds = currentUser ? currentUser[field] : null;
        document.getElementById(id).value = seconds ? String(Math.round(seconds / 60)) : '';
    });
    configPomoError.classList.add('hidden');
    configPomoStatus.textContent = '';
}

document.getElementById('configPomoForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    configPomoError.classList.add('hidden');
    const payload = {};
    for (const { id, field } of POMO_SETTING_FIELDS) {
        const raw = document.getElementById(id).value.trim();
        const minutes = Number(raw);
        if (raw && (!Number.isInteger(minutes) || minutes < 1 || minutes > 240)) {
            showError(configPomoError, 'Las duraciones van de 1 a 240 minutos.');
            return;
        }
        payload[field] = raw ? minutes * 60 : null;
    }
    try {
        // pomoDuration() (pomodoro.js) lee currentUser al arrancar un timer
        currentUser = await apiFetch('/api/auth/me', { method: 'PATCH', json: payload });
    } catch (error) {
        showError(configPomoError, error.message || 'No se pudo guardar');
        return;
    }
    configPomoStatus.textContent = 'Guardado ✓';
    setTimeout(() => { configPomoStatus.textContent = ''; }, 2500);
});

// Apagar o encender Hábitos (en Módulos) muestra u oculta sus secciones y su pie
window.modulesChangedHooks.push(updateSettingsFooter);
