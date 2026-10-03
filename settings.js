// ============================================
// ⚙️ Configuración
// ============================================
//
// Un solo modal (#habitsSetupModal): primero un menú (Hábitos, Días y horario,
// Módulos, Pomodoro y Accesibilidad) y, al tocar una fila, su página, que entra deslizándose; ‹ (o
// Escape) vuelve al menú. showHabitsSetup() (habits.js) lo llena y lo muestra,
// y al final llama a onSettingsOpened(). Cada página guarda lo suyo: los
// hábitos con "Guardar Hábitos" (el pie solo se ve en su página); lo demás, al
// tocarlo. Las páginas se muestran con la clase .active, no con `hidden`: ese
// lo usa el módulo Hábitos apagado ([data-habits-only], habits.js).

const settingsMenu = document.getElementById('settingsMenu');
const settingsPages = [...habitsSetupModal.querySelectorAll('.settings-page')];
const settingsFooter = habitsSetupModal.querySelector('.setup-footer');
const settingsScroll = habitsSetupModal.querySelector('.setup-scroll');
const settingsBack = document.getElementById('settingsBack');
const settingsTitle = document.getElementById('setupTitle');
const settingsWelcomeText = document.getElementById('setupWelcome');
const SETTINGS_TITLE = 'Configuración';

let settingsPage = null;        // la página abierta, o null en el menú
let settingsWelcome = false;    // primera vez sin hábitos: abre en Hábitos
let settingsFocusSection = null;

function settingsPageEl(name) {
    return settingsPages.find(page => page.dataset.section === name);
}

// Reinicia la animación de entrada (la misma clase en dos visitas seguidas no
// se volvería a animar)
function slideIn(element, direction) {
    element.classList.remove('slide-from-right', 'slide-from-left');
    void element.offsetWidth;
    element.classList.add(direction === 'back' ? 'slide-from-left' : 'slide-from-right');
}

function showSettingsPage(name, { animate = true } = {}) {
    const page = settingsPageEl(name);
    if (!page || page.hidden) {
        showSettingsMenu({ animate: false });
        return;
    }
    settingsPage = name;
    settingsMenu.hidden = true;
    settingsPages.forEach(p => p.classList.toggle('active', p === page));
    settingsBack.hidden = false;
    const welcome = settingsWelcome && name === 'habits';
    settingsTitle.textContent = welcome ? '¡Bienvenido! 👋' : page.dataset.title;
    settingsWelcomeText.classList.toggle('hidden', !welcome);
    settingsFooter.hidden = name !== 'habits';
    settingsScroll.scrollTop = 0;
    if (animate) slideIn(page, 'forward');
    // Festivos y huso: lo guardado al instante, lo que falte de la red (workdays.js)
    if (name === 'days' && typeof loadWorkCalendar === 'function') loadWorkCalendar();
}

function showSettingsMenu({ animate = true } = {}) {
    settingsPage = null;
    settingsMenu.hidden = false;
    settingsPages.forEach(p => p.classList.remove('active'));
    settingsBack.hidden = true;
    settingsTitle.textContent = SETTINGS_TITLE;
    settingsWelcomeText.classList.add('hidden');
    settingsFooter.hidden = true;
    settingsScroll.scrollTop = 0;
    if (animate) slideIn(settingsMenu, 'back');
}

// Abre Configuración directo en una página. La promesa se cumple con todo ya lleno.
function openSettings(section) {
    settingsFocusSection = section;
    return showHabitsSetup();
}

// Lo llama showHabitsSetup() con el modal ya visible
function onSettingsOpened({ welcome = false } = {}) {
    settingsWelcome = welcome;
    const target = settingsFocusSection || (welcome ? 'habits' : null);
    settingsFocusSection = null;
    if (target) showSettingsPage(target, { animate: false });
    else showSettingsMenu({ animate: false });
    fillPomoSettings();
    syncModuleSettings();
}

settingsMenu.addEventListener('click', (event) => {
    const item = event.target.closest('[data-open]');
    if (item) showSettingsPage(item.dataset.open);
});
settingsBack.addEventListener('click', () => showSettingsMenu());
document.getElementById('settingsClose').addEventListener('click', closeHabitsSetup);

// Escape: de una página vuelve al menú; desde el menú, cierra. Con el confirm o
// el selector de emoji encima, el Escape es de ellos.
document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape' || habitsSetupModal.classList.contains('hidden')) return;
    const onTop = ['confirmModal', 'emojiPickerModal'].some(id => {
        const modal = document.getElementById(id);
        return modal && !modal.classList.contains('hidden');
    });
    if (onTop) return;
    event.preventDefault();
    if (settingsPage) showSettingsMenu();
    else closeHabitsSetup();
});

// Apagar Hábitos (en Módulos) oculta su fila del menú y los días de descanso;
// si su página estaba abierta, se vuelve al menú
window.modulesChangedHooks.push(() => {
    if (settingsPage && settingsPageEl(settingsPage).hidden) showSettingsMenu({ animate: false });
});

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

// ============================================
// IA: "Ver qué se envía" (solo con acceso al módulo ai)
// ============================================

const aiPreview = document.getElementById('aiPreview');

aiPreview.addEventListener('toggle', async () => {
    if (!aiPreview.open) return;
    const meta = document.getElementById('aiPreviewMeta');
    const pre = document.getElementById('aiPreviewJson');
    meta.textContent = 'Cargando…';
    pre.textContent = '';
    try {
        const data = await apiFetch(`/api/reports/ai-preview?today=${getDateKey(new Date())}`);
        meta.textContent = data.configured
            ? `Proveedor: ${data.provider} · modelo ${data.model} · hoy van ${data.used_today} de ${data.daily_limit}. `
              + 'Se envían las instrucciones y este JSON (tu último reporte guardado, o esta semana): '
              + 'cifras en minutos y los nombres de tus proyectos, tareas y etiquetas. Nunca tus registros uno por uno.'
            : 'La IA no está configurada en este servidor: el texto sale de reglas fijas. Si se configura, se enviaría esto:';
        document.getElementById('aiPreviewWarning').classList.toggle('hidden', !data.training_warning);
        pre.textContent = `${data.system}\n\n${JSON.stringify(data.payload, null, 2)}`;
    } catch (error) {
        meta.textContent = error.message;
    }
});
