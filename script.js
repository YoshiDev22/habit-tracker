// ============================================
// Constantes y Configuración
// ============================================

const API_BASE_URL = '';  // Usar URL relativa

// Hooks para que archivos cargados después de este (projects.js, pomodoro.js)
// puedan engancharse al ciclo de vida de la app sin que este archivo los conozca.
window.appInitHooks = [];    // corren al final de initApp(), siempre
window.appDataHooks = [];    // corren cuando el usuario queda autenticado (login/register/reload)
window.appLogoutHooks = [];  // corren como PRIMERA acción de handleLogout(), antes de removeToken()

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

const HABITS = [];

const HABIT_LABELS = {};

// Variables para el modal de acción de hábito
let pendingHabitToRemove = null;
let previousHabits = [];
let initialSelectedHabits = [];

const habitActionModal = document.getElementById('habitActionModal');
const habitActionMessage = document.getElementById('habitActionMessage');
const hideHabitBtn = document.getElementById('hideHabitBtn');
const deleteHabitBtn = document.getElementById('deleteHabitBtn');
const cancelHabitBtn = document.getElementById('cancelHabitBtn');

// ============================================
// Estado de la aplicación
// ============================================

let currentDate = new Date();
let habitsData = {};
let selectedDate = null;
let currentUser = null;
// Racha tal como la calcula el backend (calculate_streak). La pantalla no la
// recalcula: una segunda regla en el navegador ignoraba los días de descanso.
let currentStreak = null;

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
    // Limpiar errores
    const errorDiv = modal.querySelector('.form-error');
    if (errorDiv) {
        errorDiv.classList.add('hidden');
        errorDiv.textContent = '';
    }
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
}

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
        
        // Cargar definiciones y datos de hábitos del backend
        await loadHabitDefinitionsFromAPI();
        await loadHabitsFromAPI();
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
        
        // Cargar definiciones y datos de hábitos del backend
        await loadHabitDefinitionsFromAPI();
        await loadHabitsFromAPI();
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
    runHooks(window.appLogoutHooks);
    removeToken();
    currentUser = null;
    currentStreak = null;
    habitsData = {};
    dynamicHabitCounter = 0;
    // Limpiar hábitos dinámicos
    const dynamicHabits = habitsOptions.querySelectorAll('.dynamic-habit-row');
    dynamicHabits.forEach(h => h.remove());
    // No borramos los hábitos del localStorage para que el usuario no tenga que configurarlos de nuevo
    showAuthScreen();
}

// ============================================
// Event Listeners - Auth
// ============================================

// Botones para mostrar modales
showLoginBtn.addEventListener('click', () => showModal(loginModal));
showRegisterBtn.addEventListener('click', () => showModal(registerModal));

// Despachador de cierre: la mayoría de los modales cierran sin más
// (hideAllModals), pero confirmModal y profileModal necesitan salida propia
// — resolver la promesa pendiente, o preguntar antes de descartar cambios.
function handleModalDismiss(modalEl) {
    if (!modalEl) return;
    if (modalEl.id === 'confirmModal') {
        resolveConfirmDialog(false);
    } else if (modalEl.id === 'profileModal') {
        closeProfileModal();
    } else if (modalEl.id === 'habitsSetupModal') {
        closeHabitsSetup();
    } else if (modalEl.id === 'habitActionModal') {
        hideHabitActionModal();
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

// ============================================
// Configuración de Hábitos
// ============================================

const habitsSetupModal = document.getElementById('habitsSetupModal');
const habitsOptions = document.getElementById('habitsOptions');
const customHabitInput = document.getElementById('customHabitInput');
const customHabitCheckbox = document.getElementById('customHabitCheckbox');
const customHabitColor = document.getElementById('customHabitColor');
const addCustomHabitBtn = document.getElementById('addCustomHabitBtn');
const saveHabitsBtn = document.getElementById('saveHabitsBtn');
const settingsBtn = document.getElementById('settingsBtn');

// Configuración de hábitos por defecto
const DEFAULT_HABITS = [
    { key: 'lectura', label: 'Lectura', icon: '📚', color: '#3498db' },
    { key: 'gym', label: 'Gym', icon: '💪', color: '#e74c3c' },
    { key: 'dieta', label: 'Dieta', icon: '🥗', color: '#27ae60' },
    { key: 'estudio', label: 'Estudio', icon: '📖', color: '#9b59b6' },
    { key: 'nofumar', label: 'No fumar', icon: '🚭', color: '#f39c12' }
];

// Etiquetas por defecto
const DEFAULT_HABIT_LABELS = {
    lectura: 'Lectura',
    gym: 'Gym',
    dieta: 'Dieta',
    estudio: 'Estudio',
    nofumar: 'No fumar'
};

async function showHabitsSetup() {
    const token = getToken();

    // Marcar días de descanso según currentUser.rest_days
    const restDays = (currentUser && Array.isArray(currentUser.rest_days)) ? currentUser.rest_days : [];
    const restDayCheckboxes = habitsSetupModal.querySelectorAll('input[name="rest_day"]');
    restDayCheckboxes.forEach(cb => {
        cb.checked = restDays.includes(parseInt(cb.value, 10));
    });

    if (token) {
        try {
            const response = await fetch(`${API_BASE_URL}/api/habits/definitions`, {
                headers: {
                    'Authorization': `Bearer ${token}`,
                }
            });
            
            if (!response.ok) {
                openHabitsSetup();
                return;
            }
            
            const data = await response.json();
            
            const backendKeys = new Set();
            if (data.habits && data.habits.length > 0) {
                data.habits.forEach(h => {
                    backendKeys.add(h.key);
                });
            }
            
            const defaultCheckboxes = habitsOptions.querySelectorAll('.habit-option:not(.dynamic-habit-row):not(#customHabitRow)');
            defaultCheckboxes.forEach(checkbox => {
                const key = checkbox.querySelector('input[type="checkbox"]').value;
                const cb = checkbox.querySelector('input[type="checkbox"]');
                if (backendKeys.has(key)) {
                    cb.checked = true;
                } else {
                    cb.checked = false;
                }
            });
            
            const existingDynamicRows = habitsOptions.querySelectorAll('.dynamic-habit-row');
            existingDynamicRows.forEach(row => row.remove());
            
            data.habits.forEach(h => {
                if (!['lectura', 'gym', 'dieta', 'estudio', 'nofumar'].includes(h.key)) {
                    const newOption = document.createElement('label');
                    newOption.className = 'habit-option dynamic-habit-row';
                    newOption.setAttribute('data-habit-key', h.key);
                    newOption.setAttribute('data-habit-label', h.label);
                    newOption.setAttribute('data-habit-color', h.color || '#95a5a6');
                    
                    newOption.innerHTML = `
                        <input type="checkbox" value="${h.key}" checked data-dynamic-key="${h.key}">
                        <span class="habit-check"></span>
                        <span>🎯 ${h.label}</span>
                        <input type="color" value="${h.color || '#95a5a6'}" data-habit="${h.key}" class="habit-color">
                        <button type="button" class="remove-habit-btn" title="Opciones del hábito" data-habit-key="${h.key}">🗑️</button>
                    `;
                    
                    const customRow = document.getElementById('customHabitRow');
                    habitsOptions.insertBefore(newOption, customRow);
                }
            });
            
            openHabitsSetup();
        } catch (error) {
            console.error('Error cargando hábitos para setup:', error);
            openHabitsSetup();
        }
    } else {
        openHabitsSetup();
    }
}

function hideHabitsSetup() {
    hideModal(habitsSetupModal);
}

// Estado del formulario al abrirlo, para detectar cambios sin guardar. Mismo
// patrón que profileInitialValues en el modal de perfil.
let habitsSetupInitialState = null;

// Lee el formulario completo —hábitos marcados con su color, y días de
// descanso— como una cadena comparable. Sin efectos secundarios.
function getHabitsSetupState() {
    const habits = [];
    habitsOptions.querySelectorAll('input[type="checkbox"]').forEach(checkbox => {
        if (!checkbox.checked || checkbox.id === 'customHabitCheckbox') return;
        const colorInput = habitsOptions.querySelector(`input[type="color"][data-habit="${checkbox.value}"]`);
        habits.push(`${checkbox.value}:${colorInput ? colorInput.value : ''}`);
    });

    const restDays = [];
    habitsSetupModal.querySelectorAll('input[name="rest_day"]:checked').forEach(cb => {
        restDays.push(cb.value);
    });

    return JSON.stringify({ habits: habits.sort(), restDays: restDays.sort() });
}

// Toma la foto y muestra. showHabitsSetup() tiene varias salidas (la de éxito
// y las de error) y todas pasan por acá: si alguna mostrara el modal sin
// refrescar la foto, el formulario se vería sucio sin que el usuario tocara nada.
function openHabitsSetup() {
    habitsSetupInitialState = getHabitsSetupState();
    showModal(habitsSetupModal);
}

function isHabitsSetupDirty() {
    if (habitsSetupInitialState === null) return false;
    return getHabitsSetupState() !== habitsSetupInitialState;
}

// Cierre CON guarda, solo para la ruta de descarte. Archivar y eliminar un
// hábito ya escribieron en el backend, así que siguen llamando a
// hideHabitsSetup() directo: preguntarles si quieren descartar sería mentira.
async function closeHabitsSetup() {
    if (isHabitsSetupDirty()) {
        const ok = await confirmDialog('Tienes cambios sin guardar en tus hábitos y días de descanso. ¿Seguro que quieres salir?', {
            confirmLabel: 'Salir sin guardar',
            cancelLabel: 'Seguir editando',
            danger: true
        });
        if (!ok) return;
    }
    hideHabitsSetup();
    habitsSetupInitialState = null;
}

function getSelectedHabits() {
    const selected = [];

    const checkboxes = habitsOptions.querySelectorAll('input[type="checkbox"]');
    checkboxes.forEach(checkbox => {
        if (checkbox.checked && checkbox.id !== 'customHabitCheckbox') {
            selected.push(checkbox.value);
        }
    });

    return selected;
}

// El color de cada hábito marcado. Separado de getSelectedHabits(), que antes
// escribía habit_colors en localStorage al leer el formulario: la comprobación
// de cambios sin guardar lee el formulario antes de saber si el usuario quiere
// guardar, y no debe persistir nada por el camino.
function getSelectedHabitColors() {
    const colors = {};

    habitsOptions.querySelectorAll('input[type="checkbox"]').forEach(checkbox => {
        if (!checkbox.checked || checkbox.id === 'customHabitCheckbox') return;
        const colorInput = habitsOptions.querySelector(`input[type="color"][data-habit="${checkbox.value}"]`);
        if (colorInput) {
            colors[checkbox.value] = colorInput.value;
        }
    });

    return colors;
}

async function handleSaveHabits() {
    const selectedHabits = getSelectedHabits();
    
    const dynamicHabits = habitsOptions.querySelectorAll('.dynamic-habit-row');
    dynamicHabits.forEach(row => {
        const key = row.getAttribute('data-habit-key');
        if (key && !selectedHabits.includes(key)) {
            selectedHabits.push(key);
        }
    });
    
    if (selectedHabits.length === 0) {
        const setupError = document.getElementById('setupError');
        showError(setupError, 'Selecciona al menos un hábito');
        return;
    }

    if (!isHabitsSetupDirty()) {
        // Nada que guardar: cerrar sin preguntar y sin disparar la tanda de
        // llamadas al backend que hace el resto de esta función.
        hideHabitsSetup();
        habitsSetupInitialState = null;
        return;
    }

    const confirmed = await confirmDialog('¿Guardar estos cambios en tus hábitos y días de descanso?', {
        confirmLabel: 'Guardar'
    });
    if (!confirmed) return;

    // A partir de acá sí se persiste. Los colores se escriben recién ahora,
    // para que cancelar el confirm no deje nada guardado a medias.
    localStorage.setItem('habit_colors', JSON.stringify(getSelectedHabitColors()));

    // Guardar hábitos en localStorage
    localStorage.setItem('user_habits', JSON.stringify(selectedHabits));
    
    // Guardar etiquetas de hábitos predefinidos
    const labels = {};
    const checkboxes = habitsOptions.querySelectorAll('input[type="checkbox"]');
    checkboxes.forEach(checkbox => {
        if (checkbox.checked && checkbox.id !== 'customHabitCheckbox') {
            const labelSpan = checkbox.nextElementSibling.nextElementSibling;
            labels[checkbox.value] = labelSpan.textContent;
        }
    });
    
    // Guardar etiquetas de hábitos dinámicos
    dynamicHabits.forEach(row => {
        const key = row.getAttribute('data-habit-key');
        const label = row.getAttribute('data-habit-label');
        if (key && label) {
            labels[key] = label;
        }
    });
    
    localStorage.setItem('habit_labels', JSON.stringify(labels));
    
    // Cargar colores y renderizar popover
    loadSavedColors();
    
    // Días de descanso semanal
    const selectedRestDays = [];
    const restDayCheckboxes = habitsSetupModal.querySelectorAll('input[name="rest_day"]:checked');
    restDayCheckboxes.forEach(cb => {
        selectedRestDays.push(parseInt(cb.value, 10));
    });
    selectedRestDays.sort((a, b) => a - b);

    const token = getToken();
    if (token) {
        try {
            currentUser = await apiFetch('/api/auth/me', {
                method: 'PATCH',
                json: { rest_days: selectedRestDays }
            });
            updateUserBar();
        } catch (error) {
            console.error('Error al guardar días de descanso:', error);
        }

        try {
            const existingResponse = await fetch(`${API_BASE_URL}/api/habits/definitions?include_inactive=true`, {
                headers: {
                    'Authorization': `Bearer ${token}`,
                }
            });
            
            let existingKeys = new Set();
            let existingHabitsMap = {};
            if (existingResponse.ok) {
                const existingData = await existingResponse.json();
                if (existingData.habits && existingData.habits.length > 0) {
                    existingData.habits.forEach(h => {
                        existingKeys.add(h.key);
                        existingHabitsMap[h.key] = h;
                    });
                }
                
                const selectedSet = new Set(selectedHabits);
                for (const key of existingKeys) {
                    if (!selectedSet.has(key) && existingHabitsMap[key]) {
                        try {
                            await fetch(`${API_BASE_URL}/api/habits/definitions/${existingHabitsMap[key].id}`, {
                                method: 'PATCH',
                                headers: {
                                    'Authorization': `Bearer ${token}`,
                                    'Content-Type': 'application/json',
                                },
                                body: JSON.stringify({ is_active: false })
                            });
                            console.log(`Hábito '${key}' archivado en backend`);
                        } catch (error) {
                            console.error(`Error al archivar hábito '${key}':`, error);
                        }
                    }
                }
            }
            
            const defaultIcons = {
                lectura: '📚',
                gym: '💪',
                dieta: '🥗',
                estudio: '📖',
                nofumar: '🚭'
            };
            
            for (const checkbox of checkboxes) {
                if (checkbox.checked && checkbox.id !== 'customHabitCheckbox') {
                    const key = checkbox.value;
                    if (existingKeys.has(key) && existingHabitsMap[key]?.is_active) continue;
                    
                    if (existingKeys.has(key) && existingHabitsMap[key]) {
                        try {
                            await fetch(`${API_BASE_URL}/api/habits/definitions/${existingHabitsMap[key].id}`, {
                                method: 'PATCH',
                                headers: {
                                    'Authorization': `Bearer ${token}`,
                                    'Content-Type': 'application/json',
                                },
                                body: JSON.stringify({ is_active: true })
                            });
                            existingHabitsMap[key].is_active = true;
                            console.log(`Hábito '${key}' reactivado en backend`);
                        } catch (error) {
                            console.error(`Error al reactivar hábito '${key}':`, error);
                        }
                        continue;
                    }
                    
                    const labelSpan = checkbox.nextElementSibling.nextElementSibling;
                    const label = labelSpan.textContent;
                    const colorInput = habitsOptions.querySelector(`input[type="color"][data-habit="${key}"]`);
                    const color = colorInput ? colorInput.value : '#3498db';
                    
                    try {
                        await fetch(`${API_BASE_URL}/api/habits/definitions`, {
                            method: 'POST',
                            headers: {
                                'Authorization': `Bearer ${token}`,
                                'Content-Type': 'application/json',
                            },
                            body: JSON.stringify({
                                key: key,
                                label: label,
                                icon: defaultIcons[key] || '✅',
                                color: color,
                                order: 0
                            })
                        });
                        existingKeys.add(key);
                    } catch (error) {
                        console.error(`Error al crear hábito '${key}':`, error);
                    }
                }
            }
            
            for (const row of dynamicHabits) {
                const key = row.getAttribute('data-habit-key');
                if (existingKeys.has(key) && existingHabitsMap[key]?.is_active) continue;
                
                if (existingKeys.has(key) && existingHabitsMap[key]) {
                    try {
                        await fetch(`${API_BASE_URL}/api/habits/definitions/${existingHabitsMap[key].id}`, {
                            method: 'PATCH',
                            headers: {
                                'Authorization': `Bearer ${token}`,
                                'Content-Type': 'application/json',
                            },
                            body: JSON.stringify({ is_active: true })
                        });
                        existingHabitsMap[key].is_active = true;
                        console.log(`Hábito dinámico '${key}' reactivado en backend`);
                    } catch (error) {
                        console.error(`Error al reactivar hábito dinámico '${key}':`, error);
                    }
                    continue;
                }
                
                const label = row.getAttribute('data-habit-label');
                const color = row.getAttribute('data-habit-color');
                const icon = '🎯';
                
                try {
                    await fetch(`${API_BASE_URL}/api/habits/definitions`, {
                        method: 'POST',
                        headers: {
                            'Authorization': `Bearer ${token}`,
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            key: key,
                            label: label,
                            icon: icon,
                            color: color,
                            order: 0
                        })
                    });
                    existingKeys.add(key);
                } catch (error) {
                    console.error(`Error al crear hábito dinámico '${key}':`, error);
                }
            }
            
            await loadHabitDefinitionsFromAPI();
            await loadHabitsFromAPI();
        } catch (error) {
            console.error('Error en handleSaveHabits:', error);
        }
    } else {
        HABITS.length = 0;
        selectedHabits.forEach(h => HABITS.push(h));
        Object.assign(HABIT_LABELS, labels);
        renderHabitPopoverButtons();
        renderCalendar();
    }
    
    // Ocultar modal de manera forzada
    habitsSetupInitialState = null;
    habitsSetupModal.classList.add('hidden');
    const overlay = habitsSetupModal.querySelector('.modal-overlay');
    if (overlay) {
        overlay.style.display = 'none';
    }
    
    renderCalendar();
    
    setTimeout(() => {
        renderCalendar();
    }, 100);
}

// Event listener para checkbox "Otro"
customHabitCheckbox.addEventListener('change', () => {
    const isChecked = customHabitCheckbox.checked;
    customHabitInput.disabled = !isChecked;
    customHabitColor.disabled = !isChecked;
    addCustomHabitBtn.disabled = !isChecked;
    if (isChecked) {
        customHabitInput.focus();
    }
});

// Habilitar/deshabilitar botón + cuando el input tiene texto
customHabitInput.addEventListener('input', () => {
    addCustomHabitBtn.disabled = customHabitInput.value.trim() === '' || !customHabitCheckbox.checked;
    const setupError = document.getElementById('setupError');
    setupError.classList.add('hidden');
});

// Enter key en input de hábito personalizado
customHabitInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && customHabitInput.value.trim() !== '' && customHabitCheckbox.checked) {
        e.preventDefault();
        addDynamicHabit();
    }
});

// Botón + para agregar hábito dinámico
addCustomHabitBtn.addEventListener('click', () => {
    if (customHabitInput.value.trim() !== '' && customHabitCheckbox.checked) {
        addDynamicHabit();
    }
});

// Guardar hábitos
saveHabitsBtn.addEventListener('click', handleSaveHabits);

// Delegación de eventos para el botón 🗑️ de cada hábito en el setup
habitsOptions.addEventListener('click', (e) => {
    const btn = e.target.closest('.remove-habit-btn');
    if (!btn) return;
    e.stopPropagation();
    e.preventDefault();
    const key = btn.getAttribute('data-habit-key') || btn.getAttribute('data-dynamic-key');
    if (key) {
        showHabitActionModal(key);
    }
});

// Event listeners para el modal de acción de hábito
function showHabitActionModal(habitKey) {
    pendingHabitToRemove = habitKey;
    const savedLabels = JSON.parse(localStorage.getItem('habit_labels') || '{}');
    const habitName = savedLabels[habitKey] || HABIT_LABELS[habitKey] || DEFAULT_HABIT_LABELS[habitKey] || habitKey;
    habitActionMessage.textContent = `¿Qué quieres hacer con "${habitName}"?`;
    showModal(habitActionModal);
}

function hideHabitActionModal() {
    hideModal(habitActionModal);
    pendingHabitToRemove = null;
}

// Ocultar hábito (mantener historial)
hideHabitBtn.addEventListener('click', async () => {
    if (!pendingHabitToRemove) return;
    const habitKey = pendingHabitToRemove;

    try {
        const data = await apiFetch('/api/habits/definitions?include_inactive=true');
        const habit = data.habits ? data.habits.find(h => h.key === habitKey) : null;
        if (habit) {
            await apiFetch(`/api/habits/definitions/${habit.id}`, {
                method: 'PATCH',
                json: { is_active: false }
            });
        }
        const localRow = habitsOptions.querySelector(`.dynamic-habit-row[data-habit-key="${habitKey}"]`);
        if (localRow) localRow.remove();

        hideHabitActionModal();
        hideHabitsSetup();
        await loadHabitDefinitionsFromAPI();
        await loadHabitsFromAPI();
    } catch (error) {
        console.error('Error al ocultar hábito:', error);
    }
});

// Eliminar hábito (borrar datos)
deleteHabitBtn.addEventListener('click', async () => {
    if (!pendingHabitToRemove) return;
    const habitKey = pendingHabitToRemove;

    const savedLabels = JSON.parse(localStorage.getItem('habit_labels') || '{}');
    const habitName = savedLabels[habitKey] || HABIT_LABELS[habitKey] || DEFAULT_HABIT_LABELS[habitKey] || habitKey;

    const ok = await confirmDialog(`¿Seguro que quieres eliminar el hábito "${habitName}"? Se borrará todo su historial y no se puede deshacer.`, {
        title: '¿Eliminar hábito?',
        confirmLabel: '🗑️ Eliminar',
        cancelLabel: 'Cancelar',
        danger: true
    });

    if (!ok) return;

    try {
        // Borrar historial
        await apiFetch('/api/habits/delete-habit', {
            method: 'DELETE',
            json: { habit_key: habitKey }
        });

        // Borrar definición si existe en la base
        const data = await apiFetch('/api/habits/definitions?include_inactive=true');
        const habit = data.habits ? data.habits.find(h => h.key === habitKey) : null;
        if (habit) {
            await apiFetch(`/api/habits/definitions/${habit.id}`, {
                method: 'DELETE'
            });
        }
        const localRow = habitsOptions.querySelector(`.dynamic-habit-row[data-habit-key="${habitKey}"]`);
        if (localRow) localRow.remove();

        hideHabitActionModal();
        hideHabitsSetup();
        await loadHabitDefinitionsFromAPI();
        await loadHabitsFromAPI();
    } catch (error) {
        console.error('Error al eliminar hábito:', error);
    }
});

// Cancelar: cerrar modal de acción conservando el modal de configuración intacto
cancelHabitBtn.addEventListener('click', () => {
    hideHabitActionModal();
});

// Cerrar modal de acción al hacer click en overlay
habitActionModal.querySelector('.modal-overlay').addEventListener('click', hideHabitActionModal);

// Configuración desde la barra de usuario
settingsBtn.addEventListener('click', showHabitsSetup);
userEmail.addEventListener('click', showProfile);
profileForm.addEventListener('submit', handleProfileSave);

// ============================================
// Hábitos Dinámicos (Custom)
// ============================================

let dynamicHabitCounter = 0;

function addDynamicHabit() {
    console.log('addDynamicHabit called');
    const customValue = customHabitInput.value.trim().toLowerCase().replace(/\s+/g, '');
    const customLabel = customHabitInput.value.trim();
    const customColor = customHabitColor.value;
    console.log('customValue:', customValue);
    console.log('customLabel:', customLabel);

    if (!customValue) return;

    // Verificar que no exista ya con esa key
    const existing = habitsOptions.querySelector(`input[data-dynamic-key="${customValue}"]`);
    if (existing) {
        const setupError = document.getElementById('setupError');
        showError(setupError, `El hábito "${customLabel}" ya existe en la lista`);
        return;
    }

    dynamicHabitCounter++;
    const habitId = `dynamic_${dynamicHabitCounter}`;

    // Crear nueva fila de hábito dinámico
    const newOption = document.createElement('label');
    newOption.className = 'habit-option dynamic-habit-row';
    newOption.setAttribute('data-habit-key', customValue);
    newOption.setAttribute('data-habit-label', customLabel);
    newOption.setAttribute('data-habit-color', customColor);

    newOption.innerHTML = `
        <input type="checkbox" value="${customValue}" checked data-dynamic-key="${customValue}">
        <span class="habit-check"></span>
        <span>🎯 ${customLabel}</span>
        <input type="color" value="${customColor}" data-habit="${customValue}" class="habit-color">
        <button type="button" class="remove-habit-btn" title="Opciones del hábito" data-habit-key="${customValue}">🗑️</button>
    `;

    // Insertar antes del row de "custom"
    const customRow = document.getElementById('customHabitRow');
    habitsOptions.insertBefore(newOption, customRow);

    // Limpiar input y color
    customHabitInput.value = '';
    customHabitColor.value = '#95a5a6';

    // Deshabilitar checkbox y botón +
    customHabitCheckbox.checked = false;
    customHabitInput.disabled = true;
    customHabitColor.disabled = true;
    addCustomHabitBtn.disabled = true;

    // Ocultar errores
    const setupError = document.getElementById('setupError');
    setupError.classList.add('hidden');
    setupError.textContent = '';
}

// El overlay de este modal lo maneja handleModalDismiss -> closeHabitsSetup,
// que pregunta antes de descartar. Antes había acá un segundo listener a
// hideHabitsSetup que cerraba igual y se saltaba esa pregunta.

// ============================================
// Funciones de Datos (modificadas para API)
// ============================================

// ============================================
// Elementos del DOM
// ============================================

const monthTitle = document.getElementById('monthTitle');
const daysGrid = document.getElementById('daysGrid');
const prevMonthBtn = document.getElementById('prevMonth');
const nextMonthBtn = document.getElementById('nextMonth');
const progressFill = document.getElementById('progressFill');
const progressText = document.getElementById('progressText');
const habitPopover = document.getElementById('habitPopover');
const popoverDate = document.getElementById('popoverDate');
const habitsList = document.getElementById('habitsList');

// ============================================
// Funciones de API - Hábitos
// ============================================

async function loadHabitsFromAPI() {
    try {
        const token = getToken();
        if (!token) return;

        // La racha depende de "hoy", y el servidor corre en UTC: mandar la
        // fecha LOCAL (ver backend/dates.py).
        const data = await apiFetch(`/api/habits?today=${getDateKey(new Date())}`);

        // Convertir formato del backend al formato local
        habitsData = {};
        data.entries.forEach(entry => {
            const dateKey = entry.date;
            habitsData[dateKey] = entry.habits_data || {};
        });
        currentStreak = data.streak;

        renderCalendar();
    } catch (error) {
        console.error('Error cargando hábitos:', error);
        // Si hay error, usar datos locales vacíos
        habitsData = {};
        renderCalendar();
    }
}

async function loadHabitDefinitionsFromAPI() {
    try {
        const token = getToken();
        if (!token) return;

        const data = await apiFetch('/api/habits/definitions');

        HABITS.length = 0;
        Object.keys(HABIT_LABELS).forEach(key => delete HABIT_LABELS[key]);

        if (data.habits && data.habits.length > 0) {
            data.habits.sort((a, b) => (a.order || 0) - (b.order || 0));
            data.habits.forEach(h => {
                HABITS.push(h.key);
                HABIT_LABELS[h.key] = h.label;
            });
        }

        loadSavedColors();
        renderHabitPopoverButtons();
        renderCalendar();
    } catch (error) {
        console.error('Error cargando definiciones de hábitos:', error);
    }
}

async function saveHabitToAPI(dateKey, habits) {
    try {
        const token = getToken();
        if (!token) return;

        await apiFetch('/api/habits', {
            method: 'POST',
            json: { date: dateKey, habits: habits }
        });

        // Actualizar datos locales
        habitsData[dateKey] = habits;
        renderCalendar();

        // Marcar o desmarcar un día puede cambiar la racha: pedirla al backend,
        // que es quien aplica la regla (días de descanso incluidos).
        await refreshStreakFromAPI();
    } catch (error) {
        console.error('Error guardando hábito:', error);
    }
}

async function refreshStreakFromAPI() {
    try {
        const data = await apiFetch(`/api/habits/streak?today=${getDateKey(new Date())}`);
        currentStreak = data.streak;
        renderMetrics();
    } catch (error) {
        console.error('Error actualizando la racha:', error);
    }
}

// Funciones locales (fallback cuando no hay backend)
function saveData() {
    localStorage.setItem('habitsData', JSON.stringify(habitsData));
}

function loadData() {
    const saved = localStorage.getItem('habitsData');
    if (saved) {
        habitsData = JSON.parse(saved);
    }
}

function getDateKey(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function getMonthData(year, month) {
    const monthKey = `${year}-${String(month + 1).padStart(2, '0')}`;
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    
    let completedHabits = 0;
    let totalPossible = 0;
    
    for (let day = 1; day <= daysInMonth; day++) {
        const dateKey = `${monthKey}-${String(day).padStart(2, '0')}`;
        const dayData = habitsData[dateKey];
        
        if (dayData) {
            HABITS.forEach(habit => {
                if (dayData[habit]) {
                    completedHabits++;
                }
                // Contamos solo días hasta el día actual (o todos si es mes pasado)
                const checkDate = new Date(year, month, day);
                const today = new Date();
                today.setHours(0, 0, 0, 0);
                
                if (checkDate <= today || checkDate.getMonth() < today.getMonth()) {
                    totalPossible++;
                }
            });
        }
    }
    
    // Contar días hasta hoy en el mes actual
    if (year === new Date().getFullYear() && month === new Date().getMonth()) {
        const today = new Date().getDate();
        totalPossible = today * HABITS.length;
    } else if (year > new Date().getFullYear() || 
               (year === new Date().getFullYear() && month > new Date().getMonth())) {
        totalPossible = 0;
    }
    
    return { completedHabits, totalPossible };
}

function calculateProgress() {
    const year = currentDate.getFullYear();
    const month = currentDate.getMonth();
    const { completedHabits, totalPossible } = getMonthData(year, month);
    
    if (totalPossible === 0) {
        return 0;
    }
    
    return Math.round((completedHabits / totalPossible) * 100);
}

function updateProgress() {
    const percentage = calculateProgress();
    progressFill.style.width = `${percentage}%`;
    progressText.textContent = `${percentage}%`;
}

// ============================================
// Funciones de Métricas
// ============================================

function calculateHabitStats() {
    const year = currentDate.getFullYear();
    const month = currentDate.getMonth();
    
    const stats = {};
    
    // Inicializar contadores
    HABITS.forEach(habit => {
        stats[habit] = 0;
    });
    
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    
    for (let day = 1; day <= daysInMonth; day++) {
        const date = new Date(year, month, day);
        
        // Solo contar días hasta hoy (para mes actual) o todos los días (para meses pasados)
        if (date <= today) {
            const dateKey = getDateKey(date);
            const dayData = habitsData[dateKey];
            
            if (dayData) {
                HABITS.forEach(habit => {
                    if (dayData[habit]) {
                        stats[habit]++;
                    }
                });
            }
        }
    }
    
    return stats;
}

function renderMetrics() {
    // Actualizar racha
    const streak = currentStreak ?? 0;
    const streakCount = document.getElementById('streakCount');
    streakCount.textContent = streak;
    
    // Actualizar stats por hábito
    const stats = calculateHabitStats();
    const statsGrid = document.getElementById('statsGrid');
    statsGrid.innerHTML = '';
    
    const savedColors = JSON.parse(localStorage.getItem('habit_colors') || '{}');
    
    HABITS.forEach(habit => {
        const statCard = document.createElement('div');
        statCard.className = 'stat-card';
        
        const dot = document.createElement('div');
        dot.className = `stat-dot ${habit}`;
        dot.style.backgroundColor = savedColors[habit] || '#3498db';
        
        const value = document.createElement('span');
        value.className = 'stat-value';
        value.textContent = stats[habit];
        
        const label = document.createElement('span');
        label.className = 'stat-label';
        label.textContent = HABIT_LABELS[habit];
        
        statCard.appendChild(dot);
        statCard.appendChild(value);
        statCard.appendChild(label);
        
        statsGrid.appendChild(statCard);
    });
}

// ============================================
// Funciones de UI
// ============================================

function getMonthName(month) {
    const months = [
        'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
        'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'
    ];
    return months[month];
}

function renderCalendar() {
    console.log('renderCalendar called', { daysGrid, habitsData });
    const year = currentDate.getFullYear();
    const month = currentDate.getMonth();
    
    // Actualizar título
    monthTitle.textContent = `${getMonthName(month)} ${year}`;
    
    // Limpiar grid
    daysGrid.innerHTML = '';
    
    // Primer día del mes
    const firstDay = new Date(year, month, 1).getDay();
    // Días en el mes
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    
    // Días vacíos al inicio
    for (let i = 0; i < firstDay; i++) {
        const emptyCell = document.createElement('div');
        emptyCell.className = 'day-cell empty';
        daysGrid.appendChild(emptyCell);
    }
    
    // Días del mes
    const today = new Date();
    const todayKey = getDateKey(today);
    
    for (let day = 1; day <= daysInMonth; day++) {
        const date = new Date(year, month, day);
        const dateKey = getDateKey(date);
        const dayData = habitsData[dateKey] || {};
        
        const dayCell = document.createElement('div');
        dayCell.className = 'day-cell';
        dayCell.dataset.date = dateKey;
        
        if (dateKey === todayKey) {
            dayCell.classList.add('today');
        }

        // Estilo atenuado para días de descanso sin hábitos
        const jsDay = date.getDay();
        const pyWeekday = (jsDay + 6) % 7;
        const restDays = (currentUser && Array.isArray(currentUser.rest_days)) ? currentUser.rest_days : [];
        const hasAnyHabit = Object.values(dayData).some(v => Boolean(v));
        if (restDays.includes(pyWeekday) && !hasAnyHabit) {
            dayCell.classList.add('rest-day');
        }
        
        // Número del día
        const dayNumber = document.createElement('span');
        dayNumber.className = 'day-number';
        dayNumber.textContent = day;
        dayCell.appendChild(dayNumber);
        
        // Puntos de hábitos (solo hábitos activos, no ocultos)
        const dotsContainer = document.createElement('div');
        dotsContainer.className = 'habit-dots';
        
        // Cargar colores guardados
        const savedColors = JSON.parse(localStorage.getItem('habit_colors') || '{}');
        const activeHabits = getActiveHabits();
        
        activeHabits.forEach(habit => {
            const dot = document.createElement('span');
            dot.className = `habit-dot ${habit}`;
            
            // Cargar color del hábito
            const habitColor = savedColors[habit] || '#3498db';
            
            // Si el hábito está marcado para este día, mostrar con su color
            // Si no está marcado, mostrar en gris
            if (dayData[habit]) {
                dot.classList.add('active');
                dot.style.backgroundColor = habitColor;
            } else {
                // Sin color inline: .habit-dot ya trae var(--dot-inactive) en CSS,
                // así el punto sigue el tema en vez de quedar gris fijo.
                dot.style.backgroundColor = '';
            }
            
            dotsContainer.appendChild(dot);
        });
        
        dayCell.appendChild(dotsContainer);
        
        // Evento click
        dayCell.addEventListener('click', (e) => {
            e.stopPropagation();
            showHabitPopover(dateKey, dayCell);
        });
        
        daysGrid.appendChild(dayCell);
    }
    
    updateProgress();
    renderMetrics();
}

function showHabitPopover(dateKey, targetCell) {
    selectedDate = dateKey;
    
    // Actualizar fecha en popover
    const [year, month, day] = dateKey.split('-');
    const date = new Date(year, month - 1, day);
    const options = { weekday: 'long', day: 'numeric', month: 'short' };
    popoverDate.textContent = date.toLocaleDateString('es-ES', options);
    
    // Solo renderizar botones si no existen
    if (habitsList.children.length === 0) {
        renderHabitPopoverButtons();
    }
    
    // Actualizar estado de botones según los datos actuales
    const dayData = habitsData[dateKey] || {};
    const buttons = habitsList.querySelectorAll('.habit-btn');
    
    buttons.forEach(btn => {
        const habit = btn.dataset.habit;
        const isCompleted = !!dayData[habit];
        btn.classList.toggle('completed', isCompleted);
        
        // También actualizar el color del dot según el estado
        const dot = btn.querySelector('.habit-dot');
        if (dot) {
            const savedColors = JSON.parse(localStorage.getItem('habit_colors') || '{}');
            const habitColor = savedColors[habit] || '#3498db';
            dot.style.backgroundColor = isCompleted ? habitColor : '';
        }
    });
    
    // Posicionar popover
    const rect = targetCell.getBoundingClientRect();
    const containerRect = document.querySelector('.app-container').getBoundingClientRect();
    
    let left = rect.left - containerRect.left + rect.width / 2;
    let top = rect.bottom - containerRect.top + 8;
    
    // Ajustar si sale de la pantalla
    const popoverWidth = 180;
    if (left - popoverWidth / 2 < 10) {
        left = 10 + popoverWidth / 2;
    } else if (left + popoverWidth / 2 > containerRect.width - 10) {
        left = containerRect.width - 10 - popoverWidth / 2;
    }
    
    habitPopover.style.left = `${left}px`;
    habitPopover.style.top = `${top}px`;
    habitPopover.classList.remove('hidden');
}

function hideHabitPopover() {
    habitPopover.classList.add('hidden');
    selectedDate = null;
}

function toggleHabit(habit) {
    if (!selectedDate) return;
    
    // Inicializar el objeto de hábitos para esta fecha si no existe
    if (!habitsData[selectedDate]) {
        habitsData[selectedDate] = {};
    }
    
    // Alternar el hábito específico
    const isCurrentlyActive = habitsData[selectedDate][habit];
    habitsData[selectedDate][habit] = !isCurrentlyActive;
    
    // Limpiar si no hay hábitos marcados
    const dayData = habitsData[selectedDate];
    const hasAnyHabit = HABITS.some(h => dayData[h]);
    
    if (!hasAnyHabit) {
        delete habitsData[selectedDate];
    }
    
    // Guardar en API si está autenticado
    if (isAuthenticated()) {
        saveHabitToAPI(selectedDate, habitsData[selectedDate] || {});
    } else {
        saveData();
    }
    
    // Renderizar el calendario para actualizar los puntos
    renderCalendar();
    
    // Cerrar el popover después de guardar
    hideHabitPopover();
}

// ============================================
// Event Listeners
// ============================================

prevMonthBtn.addEventListener('click', () => {
    currentDate.setMonth(currentDate.getMonth() - 1);
    renderCalendar();
});

nextMonthBtn.addEventListener('click', () => {
    currentDate.setMonth(currentDate.getMonth() + 1);
    renderCalendar();
});

habitsList.addEventListener('click', (e) => {
    const btn = e.target.closest('.habit-btn');
    if (btn) {
        const habit = btn.dataset.habit;
        toggleHabit(habit);
    }
});

// Cerrar popover al hacer click fuera
document.addEventListener('click', (e) => {
    if (!habitPopover.contains(e.target) && 
        !e.target.closest('.day-cell')) {
        hideHabitPopover();
    }
});

// ============================================
// Inicialización
// ============================================

async function initApp() {
    loadAppVersion();

    // Limpiar hábitos dinámicos al iniciar
    const dynamicHabits = habitsOptions.querySelectorAll('.dynamic-habit-row');
    dynamicHabits.forEach(h => h.remove());
    dynamicHabitCounter = 0;
    
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
        
        // Cargar definiciones y datos de hábitos del backend
        await loadHabitDefinitionsFromAPI();
        await loadHabitsFromAPI();
        await runHooks(window.appDataHooks);

        // Si no hay hábitos definidos en el backend, mostrar popup de configuración
        if (HABITS.length === 0) {
            showHabitsSetup();
        }
    } else {
        // Mostrar pantalla de autenticación
        showAuthScreen();
    }

    await runHooks(window.appInitHooks);
}

// Función para obtener hábitos activos
function getActiveHabits() {
    return HABITS;
}

// Función para renderizar los botones del popover dinámicamente
function renderHabitPopoverButtons() {
    const habitsList = document.getElementById('habitsList');
    const savedColors = JSON.parse(localStorage.getItem('habit_colors') || '{}');
    const savedLabels = JSON.parse(localStorage.getItem('habit_labels') || '{}');
    const activeHabits = getActiveHabits();
    
    habitsList.innerHTML = '';
    
    if (activeHabits.length === 0) {
        habitsList.innerHTML = '<p class="no-habits-message">No hay hábitos configurados. <button class="link-btn" onclick="showHabitsSetup()">Configurar hábitos</button></p>';
        return;
    }
    
    activeHabits.forEach(habit => {
        const btn = document.createElement('button');
        btn.className = 'habit-btn';
        btn.dataset.habit = habit;
        
        const dot = document.createElement('span');
        dot.className = `habit-dot ${habit}`;
        
        // Aplicar color guardado o color por defecto
        const color = savedColors[habit] || '#3498db';
        dot.style.backgroundColor = color;
        
        const label = document.createElement('span');
        label.className = 'habit-label';
        label.textContent = savedLabels[habit] || HABIT_LABELS[habit] || habit;
        
        btn.appendChild(dot);
        btn.appendChild(label);
        
        // Evento click
        btn.addEventListener('click', () => toggleHabit(habit));
        
        habitsList.appendChild(btn);
    });
}

function loadSavedColors() {
    // Cargar colores guardados y renderizar popover
    renderHabitPopoverButtons();
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

// Inicializar estado disabled de campos custom
customHabitInput.disabled = true;
customHabitColor.disabled = true;
addCustomHabitBtn.disabled = true;

// DOMContentLoaded (no una llamada directa) para que, cuando existan más
// <script src> después de este (projects.js, pomodoro.js), sus funciones ya
// estén definidas antes de que initApp() los invoque vía los hooks de arriba.
document.addEventListener('DOMContentLoaded', initApp);
