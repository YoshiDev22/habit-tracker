// ============================================
// Constantes y Configuración
// ============================================

const API_BASE_URL = '';  // Usar URL relativa

// Hooks para que archivos cargados después de este (habits.js, projects.js,
// pomodoro.js…) puedan engancharse al ciclo de vida de la app sin que este archivo los conozca.
window.appInitHooks = [];    // corren al final de initApp(), siempre
window.appDataHooks = [];    // corren cuando el usuario queda autenticado (login/register/reload)
window.appLogoutHooks = [];  // corren como PRIMERA acción de handleLogout(), antes de removeToken()
window.modulesChangedHooks = [];  // corren tras encender o apagar un módulo en Mi perfil

// Ejecuta una lista de hooks en orden; un hook que falla no detiene a los demás.
async function runHooks(hooks) {
    for (const hook of hooks) {
        try {
            await hook();
        } catch (error) {
            console.error('Error en hook:', error);
        }
    }
}

// ============================================
// Estado de la aplicación
// ============================================

let currentUser = null;

// Si un módulo de la cuenta (backend/modules.py) está encendido. Sin usuario
// cargado, solo Hábitos: es lo que tiene una cuenta por defecto.
function moduleEnabled(name) {
    const state = currentUser && currentUser.modules && currentUser.modules[name];
    return state ? state.enabled : name === 'habits';
}

// ============================================
// Elementos del DOM - Auth
// ============================================

const authScreen = document.getElementById('authScreen');
const mainApp = document.getElementById('mainApp');
const userBar = document.getElementById('userBar');
const userEmail = document.getElementById('userEmail');
const brandGreeting = document.getElementById('brandGreeting');
const loginModal = document.getElementById('loginModal');
const registerModal = document.getElementById('registerModal');
const showLoginBtn = document.getElementById('showLoginBtn');
const showRegisterBtn = document.getElementById('showRegisterBtn');
const loginForm = document.getElementById('loginForm');
const registerForm = document.getElementById('registerForm');
const loginError = document.getElementById('loginError');
const registerError = document.getElementById('registerError');
const logoutBtn = document.getElementById('logoutBtn');
const profileModal = document.getElementById('profileModal');
const profileForm = document.getElementById('profileForm');
const profileError = document.getElementById('profileError');
const moduleError = document.getElementById('moduleError');
const moduleStatus = document.getElementById('moduleStatus');
const confirmModal = document.getElementById('confirmModal');
const confirmModalTitle = document.getElementById('confirmModalTitle');
const confirmModalMessage = document.getElementById('confirmModalMessage');
const confirmModalConfirmBtn = document.getElementById('confirmModalConfirmBtn');
const confirmModalCancelBtn = document.getElementById('confirmModalCancelBtn');

// ============================================
// Funciones de Autenticación - Token
// ============================================

function saveToken(token) {
    localStorage.setItem('access_token', token);
}

function getToken() {
    return localStorage.getItem('access_token');
}

// Error de API con el status HTTP adjunto, para que el caller pueda
// distinguir p.ej. un 409 (conflicto) de un error genérico.
class ApiError extends Error {
    constructor(message, status) {
        super(message);
        this.name = 'ApiError';
        this.status = status;
    }
}

// Helper de fetch autenticado, para código NUEVO (projects.js, pomodoro.js).
// No reemplaza los fetch existentes en este archivo — ver nota en handleSaveHabits.
async function apiFetch(path, options = {}) {
    const opts = { ...options, headers: { ...(options.headers || {}) } };

    const token = getToken();
    if (token) {
        opts.headers['Authorization'] = `Bearer ${token}`;
    }

    if (options.json !== undefined) {
        opts.body = JSON.stringify(options.json);
        opts.headers['Content-Type'] = 'application/json';
        delete opts.json;
    }

    const response = await fetch(`${API_BASE_URL}${path}`, opts);

    if (response.status === 401) {
        handleLogout();
        throw new ApiError('Sesión expirada', 401);
    }

    if (!response.ok) {
        let detail = 'Error de red';
        try {
            const data = await response.json();
            detail = data.detail || detail;
            // Un 422 de validación trae una lista: mostrar el primer motivo
            if (Array.isArray(detail)) {
                detail = String(detail[0]?.msg || 'Datos no válidos').replace(/^Value error, /, '');
            }
        } catch (e) {
            // Respuesta sin cuerpo JSON, usar el mensaje genérico
        }
        throw new ApiError(detail, response.status);
    }

    if (response.status === 204) {
        return null;
    }

    return response.json();
}

function removeToken() {
    localStorage.removeItem('access_token');
}

function isAuthenticated() {
    return !!getToken();
}

// ============================================
// Funciones de Autenticación - UI
// ============================================

function showAuthScreen() {
    authScreen.classList.remove('hidden');
    mainApp.classList.add('hidden');
    userBar.classList.add('hidden');
}

function showMainApp() {
    authScreen.classList.add('hidden');
    mainApp.classList.remove('hidden');
    userBar.classList.remove('hidden');
}

function showModal(modal) {
    modal.classList.remove('hidden');
}

function hideModal(modal) {
    modal.classList.add('hidden');
    // Limpiar errores (todos: un modal puede tener más de uno, como el de hábitos)
    modal.querySelectorAll('.form-error').forEach(errorDiv => {
        errorDiv.classList.add('hidden');
        errorDiv.textContent = '';
    });
    // Limpiar formularios
    const form = modal.querySelector('form');
    if (form) form.reset();
}

function hideAllModals() {
    hideModal(loginModal);
    hideModal(registerModal);
    hideModal(profileModal);
}

// Confirm genérico (sí/no) para código nuevo (perfil, pomodoro, y lo que
// venga). No pasa por hideAllModals: ese helper no conoce confirmModal
// y no debería — ver handleModalDismiss más abajo, que sí lo conoce.
let confirmModalResolve = null;

function confirmDialog(message, { title = '¿Seguro?', confirmLabel = 'Sí', cancelLabel = 'Cancelar', danger = false } = {}) {
    // Solo un confirm a la vez: si ya había uno pendiente (doble click en
    // el botón que lo abrió), se resuelve como cancelado antes de abrir el nuevo.
    if (confirmModalResolve) {
        confirmModalResolve(false);
    }

    confirmModalTitle.textContent = title;
    confirmModalMessage.textContent = message;
    confirmModalConfirmBtn.textContent = confirmLabel;
    confirmModalConfirmBtn.classList.toggle('btn-danger', danger);
    confirmModalCancelBtn.textContent = cancelLabel;
    showModal(confirmModal);

    return new Promise(resolve => {
        confirmModalResolve = resolve;
    });
}

function resolveConfirmDialog(result) {
    confirmModal.classList.add('hidden');
    if (confirmModalResolve) {
        confirmModalResolve(result);
        confirmModalResolve = null;
    }
}

confirmModalConfirmBtn.addEventListener('click', () => resolveConfirmDialog(true));
confirmModalCancelBtn.addEventListener('click', () => resolveConfirmDialog(false));

function showError(errorDiv, message) {
    errorDiv.textContent = message;
    errorDiv.classList.remove('hidden');
}

// Cómo llamar al usuario en la UI. En cascada, para que las cuentas que ya
// existen —sin alias ni nombre— tampoco enseñen el correo entero.
function getUserLabel(user) {
    if (!user) {
        return '';
    }
    return user.display_name || user.first_name || (user.email || '').split('@')[0];
}

function updateUserBar() {
    if (currentUser) {
        const label = getUserLabel(currentUser);
        userEmail.textContent = label;
        userEmail.title = currentUser.email || '';
        brandGreeting.textContent = `Sigamos adelante, ${label}`;
    }
    // La etiqueta MKR, pegada al nombre, mientras el plan Maker esté encendido
    document.getElementById('planBadge').hidden = !(currentUser && moduleEnabled('maker'));
}

// Qué cambió al tocar un módulo, dicho donde se tocó: encender no recarga
// nada, así que hay que decir dónde está lo nuevo
const MODULE_STATUS = {
    maker: {
        on: 'Plan Maker encendido. Abre la ficha de un proyecto (Tableros › Lista, toca su nombre) para costearlo.',
        off: 'Plan Maker apagado. Tu costeo se guarda y vuelve al encenderlo.',
    },
    habits: {
        on: 'Hábitos encendido: vuelve la pestaña Calendario.',
        off: 'Hábitos apagado: tus registros se guardan y vuelven al encenderlo.',
    },
};

async function loadAppVersion() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/version`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        const versionText = `v${data.version}`;
        document.getElementById('authVersion').textContent = versionText;
        document.getElementById('mainVersion').textContent = versionText;
    } catch (error) {
        console.warn('Could not load app version from /api/version:', error);
    }
}

// ============================================
// Funciones de API - Auth
// ============================================

async function register(email, password, profile = {}) {
    try {
        const response = await fetch(`${API_BASE_URL}/api/auth/register`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ email, password, ...profile })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'Error al registrar usuario');
        }

        return data;
    } catch (error) {
        throw error;
    }
}

async function login(email, password) {
    try {
        // El backend espera OAuth2PasswordRequestForm (form-urlencoded)
        const formData = new URLSearchParams();
        formData.append('username', email);
        formData.append('password', password);

        const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: formData
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'Error al iniciar sesión');
        }

        return data;
    } catch (error) {
        throw error;
    }
}

// ============================================
// Funciones de Autenticación - Eventos
// ============================================

async function handleRegister(event) {
    event.preventDefault();
    
    const email = document.getElementById('registerEmail').value;
    const password = document.getElementById('registerPassword').value;
    const confirmPassword = document.getElementById('registerConfirmPassword').value;

    // Validar contraseñas
    if (password !== confirmPassword) {
        showError(registerError, 'Las contraseñas no coinciden');
        return;
    }

    if (password.length < 6) {
        showError(registerError, 'La contraseña debe tener al menos 6 caracteres');
        return;
    }

    try {
        const user = await register(email, password, {
            display_name: document.getElementById('registerDisplayName').value,
            first_name: document.getElementById('registerFirstName').value,
            last_name: document.getElementById('registerLastName').value
        });
        
        // Después de registro exitoso, hacer login automáticamente
        const tokenData = await login(email, password);
        saveToken(tokenData.access_token);
        currentUser = user;
        
        hideAllModals();
        showMainApp();
        updateUserBar();
        await runHooks(window.appDataHooks);
    } catch (error) {
        showError(registerError, error.message);
    }
}

async function handleLogin(event) {
    event.preventDefault();
    
    const email = document.getElementById('loginEmail').value;
    const password = document.getElementById('loginPassword').value;

    try {
        const tokenData = await login(email, password);
        saveToken(tokenData.access_token);

        // El login solo devuelve el token, sin datos del usuario: el alias y el
        // nombre salen de /me, igual que al recargar la página.
        currentUser = await apiFetch('/api/auth/me');
        
        hideAllModals();
        showMainApp();
        updateUserBar();
        await runHooks(window.appDataHooks);
    } catch (error) {
        showError(loginError, error.message);
    }
}

// Valores con los que se abrió el modal de perfil, para saber si hay
// cambios sin guardar (isProfileDirty) al intentar cerrarlo o guardarlo.
let profileInitialValues = null;

function showProfile() {
    if (!currentUser) {
        return;
    }
    document.getElementById('profileEmail').textContent = `Sesión iniciada como ${currentUser.email}`;
    document.getElementById('profileDisplayName').value = currentUser.display_name || '';
    document.getElementById('profileFirstName').value = currentUser.first_name || '';
    document.getElementById('profileLastName').value = currentUser.last_name || '';
    profileInitialValues = {
        displayName: currentUser.display_name || '',
        firstName: currentUser.first_name || '',
        lastName: currentUser.last_name || ''
    };
    showModal(profileModal);
}

// Las casillas de ⚙️ Configuración › Módulos, al día con la cuenta (settings.js
// las sincroniza al abrir)
function syncModuleSettings() {
    if (!currentUser) return;
    moduleError.classList.add('hidden');
    moduleStatus.hidden = true;
    moduleInputs().forEach(input => {
        input.checked = moduleEnabled(input.dataset.module);
    });
    // Un módulo sin acceso para esta cuenta no se ofrece
    const maker = currentUser.modules && currentUser.modules.maker;
    document.getElementById('moduleMakerOption').hidden = !(maker && maker.allowed);
}

function moduleInputs() {
    return [...document.querySelectorAll('#moduleSettings [data-module]')];
}

// Un módulo se guarda al tocarlo, como el tamaño del texto: no es parte del
// formulario ni de su "¿Guardar estos cambios?".
async function handleModuleToggle(event) {
    const input = event.target.closest('[data-module]');
    if (!input) return;
    moduleError.classList.add('hidden');
    moduleStatus.hidden = true;
    input.disabled = true;
    try {
        currentUser = await apiFetch(`/api/auth/me/modules/${input.dataset.module}`, {
            method: 'PUT',
            json: { enabled: input.checked }
        });
    } catch (error) {
        input.checked = !input.checked;
        showError(moduleError, error.message);
        return;
    } finally {
        input.disabled = false;
    }
    updateUserBar();
    const status = MODULE_STATUS[input.dataset.module];
    if (status) {
        moduleStatus.textContent = input.checked ? status.on : status.off;
        moduleStatus.hidden = false;
    }
    await runHooks(window.modulesChangedHooks);
}

function isProfileDirty() {
    if (!profileInitialValues) return false;
    return document.getElementById('profileDisplayName').value !== profileInitialValues.displayName
        || document.getElementById('profileFirstName').value !== profileInitialValues.firstName
        || document.getElementById('profileLastName').value !== profileInitialValues.lastName;
}

// Llamada por handleModalDismiss en vez de hideModal directo: la X y el
// overlay del modal de perfil pasan por acá para poder preguntar antes
// de descartar cambios sin guardar.
async function closeProfileModal() {
    if (isProfileDirty()) {
        const ok = await confirmDialog('Tienes cambios sin guardar en tu perfil. ¿Seguro que quieres salir?', {
            confirmLabel: 'Salir sin guardar',
            cancelLabel: 'Seguir editando',
            danger: true
        });
        if (!ok) return;
    }
    hideModal(profileModal);
    profileInitialValues = null;
}

async function handleProfileSave(event) {
    event.preventDefault();

    if (!isProfileDirty()) {
        // Nada que guardar: cerrar directo, sin preguntar.
        hideModal(profileModal);
        profileInitialValues = null;
        return;
    }

    const ok = await confirmDialog('¿Guardar estos cambios en tu perfil?', { confirmLabel: 'Guardar' });
    if (!ok) return;

    try {
        currentUser = await apiFetch('/api/auth/me', {
            method: 'PATCH',
            json: {
                display_name: document.getElementById('profileDisplayName').value,
                first_name: document.getElementById('profileFirstName').value,
                last_name: document.getElementById('profileLastName').value
            }
        });

        updateUserBar();
        hideModal(profileModal);
        profileInitialValues = null;
    } catch (error) {
        showError(profileError, error.message);
    }
}

function handleLogout() {
    // Hooks primero: el token todavía existe en este punto, algún hook
    // (ej. pomodoro) puede necesitarlo para un último POST antes de perderlo.
    // Arrancan TODOS ya, sin esperarse entre sí: con runHooks(), que va uno
    // tras otro, cada await le devolvía el control a esta función, el token
    // se borraba antes de que empezara el siguiente hook, y su POST salía sin
    // token. Pasó cuando board.js registró su hook antes que el de pomodoro.
    window.appLogoutHooks.forEach(hook => {
        try {
            Promise.resolve(hook()).catch(error => console.error('Error en hook de logout:', error));
        } catch (error) {
            console.error('Error en hook de logout:', error);
        }
    });
    removeToken();
    currentUser = null;
    showAuthScreen();
}

// ============================================
// Event Listeners - Auth
// ============================================

// Botones para mostrar modales
showLoginBtn.addEventListener('click', () => showModal(loginModal));
showRegisterBtn.addEventListener('click', () => showModal(registerModal));

// Despachador de cierre: la mayoría de los modales cierran sin más
// (hideAllModals), pero confirmModal, emojiPickerModal y profileModal necesitan
// salida propia — resolver la promesa pendiente, o preguntar antes de descartar
// cambios.
function handleModalDismiss(modalEl) {
    if (!modalEl) return;
    if (modalEl.id === 'confirmModal') {
        resolveConfirmDialog(false);
    } else if (modalEl.id === 'emojiPickerModal') {
        // Cerrar sin elegir no es "sin emoji": deja el que hubiera.
        resolveEmojiPicker(null);
    } else if (modalEl.id === 'profileModal') {
        closeProfileModal();
    } else if (modalEl.id === 'habitsSetupModal') {
        closeHabitsSetup();
    } else if (modalEl.id === 'missedDayModal') {
        hideModal(modalEl);
    } else {
        hideAllModals();
    }
}

// Cerrar modales
document.querySelectorAll('[data-close-modal]').forEach(btn => {
    btn.addEventListener('click', () => handleModalDismiss(btn.closest('.modal')));
});

// Cerrar modal al hacer click en overlay
document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', () => handleModalDismiss(overlay.closest('.modal')));
});

// Alternar entre login y registro
document.querySelectorAll('[data-switch-to]').forEach(btn => {
    btn.addEventListener('click', () => {
        const target = btn.dataset.switchTo;
        hideAllModals();
        if (target === 'register') {
            showModal(registerModal);
        } else {
            showModal(loginModal);
        }
    });
});

// Submit de formularios
loginForm.addEventListener('submit', handleLogin);
registerForm.addEventListener('submit', handleRegister);

// Logout
logoutBtn.addEventListener('click', handleLogout);

// Perfil, desde el nombre en la barra de usuario
userEmail.addEventListener('click', showProfile);
profileForm.addEventListener('submit', handleProfileSave);
document.getElementById('moduleSettings').addEventListener('change', handleModuleToggle);

// La fecha LOCAL del usuario como "AAAA-MM-DD". La usa toda la app: hábitos,
// sesiones de tiempo, Reportes y el ?today= de la API.
function getDateKey(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

// ============================================
// Inicialización
// ============================================

async function initApp() {
    loadAppVersion();

    if (isAuthenticated()) {
        // Usuario ya autenticado. El token es lo único que sobrevive a un F5,
        // así que hay que preguntarle al backend de quién es.
        try {
            currentUser = await apiFetch('/api/auth/me');
        } catch (error) {
            // Token inválido o expirado: apiFetch ya cerró sesión y dejó la
            // pantalla de login a la vista, así que no hay app que montar.
            console.warn('Could not restore the session:', error);
            await runHooks(window.appInitHooks);
            return;
        }

        showMainApp();
        updateUserBar();
        await runHooks(window.appDataHooks);
    } else {
        // Mostrar pantalla de autenticación
        showAuthScreen();
    }

    await runHooks(window.appInitHooks);
}

// ============================================
// Modo oscuro
// ============================================

const THEME_CYCLE = ['system', 'light', 'dark'];
const THEME_ICONS = { system: '🖥️', light: '☀️', dark: '🌙' };
const THEME_LABELS = { system: 'Sistema', light: 'Claro', dark: 'Oscuro' };

const themeToggleBtn = document.getElementById('themeToggle');
const themeColorMeta = document.getElementById('themeColorMeta');

function getSystemPrefersDark() {
    return !!(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
}

function getThemePref() {
    try {
        return localStorage.getItem('theme') || 'system';
    } catch (e) {
        return 'system';
    }
}

function setThemePref(pref) {
    try {
        localStorage.setItem('theme', pref);
    } catch (e) {
        // localStorage puede lanzar en navegación privada; el tema
        // simplemente no persiste entre recargas en ese caso.
    }
}

function applyTheme(pref) {
    const dark = pref === 'dark' || (pref === 'system' && getSystemPrefersDark());
    const root = document.documentElement;
    root.setAttribute('data-theme', dark ? 'dark' : 'light');
    root.setAttribute('data-theme-pref', pref);

    if (themeColorMeta) {
        themeColorMeta.setAttribute('content', dark ? '#14161a' : '#fafafa');
    }
    if (themeToggleBtn) {
        themeToggleBtn.textContent = THEME_ICONS[pref];
        const label = `Tema: ${THEME_LABELS[pref]}`;
        themeToggleBtn.title = label;
        themeToggleBtn.setAttribute('aria-label', label);
    }
}

function cycleTheme() {
    const current = getThemePref();
    const next = THEME_CYCLE[(THEME_CYCLE.indexOf(current) + 1) % THEME_CYCLE.length];
    setThemePref(next);
    applyTheme(next);
}

function initTheme() {
    // El <script> inline en <head> ya aplicó el tema antes del primer paint;
    // esto solo sincroniza el ícono/label del botón y engancha los listeners.
    applyTheme(getThemePref());

    if (themeToggleBtn) {
        themeToggleBtn.addEventListener('click', cycleTheme);
    }

    if (window.matchMedia) {
        const mql = window.matchMedia('(prefers-color-scheme: dark)');
        const onSystemChange = () => {
            // Solo re-aplicar si el usuario sigue en modo "sistema"
            if (getThemePref() === 'system') {
                applyTheme('system');
            }
        };
        if (typeof mql.addEventListener === 'function') {
            mql.addEventListener('change', onSystemChange);
        } else if (typeof mql.addListener === 'function') {
            mql.addListener(onSystemChange); // Safari viejo
        }
    }
}

window.appInitHooks.push(initTheme);

// Tamaño del texto: preferencia de este dispositivo, como el tema. El script
// inline del <head> la aplica antes del primer paint; esto la cambia y marca
// el botón elegido. Sobrevive al cierre de sesión a propósito.
const TEXT_SIZES = ['normal', 'large', 'xlarge'];
const textSizeToggle = document.getElementById('textSizeToggle');

function getTextSize() {
    try {
        const size = localStorage.getItem('text_size');
        return TEXT_SIZES.includes(size) ? size : 'normal';
    } catch (e) {
        return 'normal';
    }
}

function applyTextSize(size) {
    if (size === 'normal') {
        document.documentElement.removeAttribute('data-text-size');
    } else {
        document.documentElement.setAttribute('data-text-size', size);
    }
    textSizeToggle.querySelectorAll('[data-size]').forEach(btn => {
        btn.setAttribute('aria-pressed', btn.dataset.size === size ? 'true' : 'false');
    });
}

function initTextSize() {
    applyTextSize(getTextSize());
    textSizeToggle.addEventListener('click', (event) => {
        const btn = event.target.closest('[data-size]');
        if (!btn) return;
        try {
            if (btn.dataset.size === 'normal') localStorage.removeItem('text_size');
            else localStorage.setItem('text_size', btn.dataset.size);
        } catch (e) {
            // Sin localStorage se aplica igual, solo no persiste al recargar.
        }
        applyTextSize(btn.dataset.size);
    });
}

window.appInitHooks.push(initTextSize);


// DOMContentLoaded (no una llamada directa) para que, cuando existan más
// <script src> después de este (projects.js, pomodoro.js), sus funciones ya
// estén definidas antes de que initApp() los invoque vía los hooks de arriba.
document.addEventListener('DOMContentLoaded', initApp);
