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

// Nombre y emoji de cada hábito, por clave. Los dos salen del backend en
// loadHabitDefinitionsFromAPI(): el nombre va SIN emoji, y el emoji se pone
// delante al pintar. Guardar el emoji dentro del nombre es lo que hacía que
// saliera dos veces.
const HABIT_LABELS = {};
const HABIT_ICONS = {};
// Y su color, también del backend (habits.color). Hasta la 1.13 vivía solo en
// localStorage.habit_colors y no viajaba entre dispositivos.
const HABIT_COLORS = {};
const DEFAULT_HABIT_COLOR = '#3498db';

function habitColor(key) {
    return HABIT_COLORS[key] || DEFAULT_HABIT_COLOR;
}

let previousHabits = [];
let initialSelectedHabits = [];

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
// Protectores, días cubiertos y "ayer quedó vacío", también del backend
// (_walk_streak). Los guarda setStreakInfo().
let streakInfo = null;

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
    currentStreak = null;
    streakInfo = null;
    habitsData = {};
    // La lista del modal se repinta desde el backend cada vez que se abre, así
    // que no hay nada que limpiar acá.
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

// ============================================
// Configuración de Hábitos
// ============================================

const habitsSetupModal = document.getElementById('habitsSetupModal');
const habitsOptions = document.getElementById('habitsOptions');
const habitsEmpty = document.getElementById('habitsEmpty');
const habitSuggestions = document.getElementById('habitSuggestions');
const customHabitIconBtn = document.getElementById('customHabitIconBtn');
const customHabitInput = document.getElementById('customHabitInput');
const customHabitColor = document.getElementById('customHabitColor');
const addCustomHabitBtn = document.getElementById('addCustomHabitBtn');
const saveHabitsBtn = document.getElementById('saveHabitsBtn');
const archivedHabits = document.getElementById('archivedHabits');
const archivedHabitsList = document.getElementById('archivedHabitsList');
const archivedCountEl = document.getElementById('archivedCount');
const settingsBtn = document.getElementById('settingsBtn');

// Configuración de hábitos por defecto
const DEFAULT_HABITS = [
    { key: 'lectura', label: 'Lectura', icon: '📚', color: '#3498db' },
    { key: 'gym', label: 'Gym', icon: '💪', color: '#e74c3c' },
    { key: 'dieta', label: 'Dieta', icon: '🥗', color: '#27ae60' },
    { key: 'estudio', label: 'Estudio', icon: '📖', color: '#9b59b6' },
    { key: 'nofumar', label: 'No fumar', icon: '🚭', color: '#f39c12' }
];

// Paleta fija para hábitos nuevos: al añadir uno se preselecciona el primer color
// que ningún hábito (oculto incluido) use. Repetir se permite, con aviso: lo que
// identifica al hábito es su lugar en el día, no el color.
const HABIT_PALETTE = ['#3498db', '#e74c3c', '#27ae60', '#9b59b6', '#f39c12', '#1abc9c', '#e84393', '#8d6e63'];

// Todos los hábitos del usuario (ocultos incluidos) tal como los trajo el modal
// de configuración, para saber qué colores están tomados.
let setupAllHabits = [];

function usedHabitColors() {
    const used = new Set(setupAllHabits.filter(h => !h.is_active).map(h => (h.color || '').toLowerCase()));
    habitsOptions.querySelectorAll('.habit-option input[type="color"]').forEach(input => {
        used.add(input.value.toLowerCase());
    });
    return used;
}

function pickFreeColor(preferred) {
    const used = usedHabitColors();
    if (preferred && !used.has(preferred.toLowerCase())) return preferred;
    return HABIT_PALETTE.find(color => !used.has(color)) || preferred || HABIT_PALETTE[0];
}

// Aviso suave, nunca bloquea: dos hábitos con el mismo color se distinguen por
// su lugar en el día.
function updateColorWarning() {
    const warning = document.getElementById('setupColorWarning');
    const byColor = {};
    habitsOptions.querySelectorAll('.habit-option').forEach(row => {
        if (!row.querySelector('input[type="checkbox"]').checked) return;
        const color = row.querySelector('input[type="color"]').value.toLowerCase();
        (byColor[color] = byColor[color] || []).push(row.dataset.habitLabel);
    });
    const repeated = Object.values(byColor).filter(names => names.length > 1);
    const customColor = customHabitColor.value.toLowerCase();
    const customTwin = customHabitInput.value.trim() && byColor[customColor] ? byColor[customColor][0] : null;

    let text = '';
    if (repeated.length) {
        text = `${repeated.map(names => names.join(' y ')).join('; ')} tienen el mismo color. Se puede, pero en el calendario solo los distinguirá su lugar.`;
    } else if (customTwin) {
        text = `Ese color ya lo usa ${customTwin}. Se puede, pero en el calendario solo los distinguirá su lugar.`;
    }
    warning.textContent = text;
    warning.classList.toggle('hidden', !text);
}

// El nombre tal como se lee en pantalla. Un único sitio que compone emoji +
// nombre: cuando esto estaba repetido por el archivo, un `label` que ya traía
// el emoji dentro salía con el emoji dos veces.
function habitDisplayName(icon, label) {
    return icon ? `${icon} ${label}` : label;
}

// ============================================
// Panel de emojis
// ============================================

// Catálogo del panel. Es una lista cerrada a propósito: el emoji se elige de
// acá, no hay que buscarlo por internet y pegarlo.
const HABIT_EMOJIS = [
    {
        group: 'Salud y deporte',
        emojis: ['💪', '🏃', '🚴', '🏋️', '🧘', '🤸', '🥊', '🚶', '⚽', '🏀',
                 '🎾', '🏊', '⛹️', '🩺', '💊', '🦷', '😴', '💧', '🧴', '🚭']
    },
    {
        group: 'Estudio y trabajo',
        emojis: ['📚', '📖', '✏️', '📝', '🎓', '🧠', '💻', '⌨️', '📊', '🗂️',
                 '📅', '⏰', '🔬', '🧮', '🗣️', '🌐', '💼', '📌']
    },
    {
        group: 'Comida',
        emojis: ['🥗', '🍎', '🥦', '🥑', '🍳', '🍚', '🐟', '🍗', '🥛', '☕',
                 '🍫', '🧂', '🥤']
    },
    {
        group: 'Casa y dinero',
        emojis: ['🧹', '🧺', '🛏️', '🚿', '🪥', '🗑️', '🪴', '🛠️', '🐕', '🐈',
                 '💰', '🧾']
    },
    {
        group: 'Ánimo y aficiones',
        emojis: ['🎯', '🔥', '⭐', '✅', '🏆', '🙏', '🧡', '🌅', '🌙', '🎵',
                 '🎸', '🎨', '📷', '✍️', '🎮', '🧩', '🎬', '🕺']
    }
];

const emojiPickerModal = document.getElementById('emojiPickerModal');
const emojiPickerGrid = document.getElementById('emojiPickerGrid');
const emojiPickerFor = document.getElementById('emojiPickerFor');
let emojiPickerResolve = null;

// La rejilla se arma una sola vez y se reutiliza: son ~80 botones y no cambian.
function buildEmojiPicker() {
    HABIT_EMOJIS.forEach(section => {
        const title = document.createElement('p');
        title.className = 'emoji-group-title';
        title.textContent = section.group;

        const grid = document.createElement('div');
        grid.className = 'emoji-grid';

        section.emojis.forEach(emoji => {
            const option = document.createElement('button');
            option.type = 'button';
            option.className = 'emoji-option';
            option.dataset.emoji = emoji;
            option.textContent = emoji;
            option.setAttribute('aria-label', `Emoji ${emoji}`);
            grid.appendChild(option);
        });

        emojiPickerGrid.append(title, grid);
    });
}

buildEmojiPicker();

// Devuelve el emoji elegido, '' si se pide "sin emoji", o null si se cerró sin
// elegir. Mismo patrón que confirmDialog(): una promesa y un solo panel vivo.
function pickEmoji(currentEmoji, habitName) {
    if (emojiPickerResolve) {
        resolveEmojiPicker(null);
    }

    emojiPickerFor.textContent = habitName ? `Para "${habitName}"` : '';
    emojiPickerGrid.querySelectorAll('.emoji-option').forEach(option => {
        option.classList.toggle('selected', option.dataset.emoji === currentEmoji);
    });
    emojiPickerGrid.scrollTop = 0;
    showModal(emojiPickerModal);

    return new Promise(resolve => {
        emojiPickerResolve = resolve;
    });
}

function resolveEmojiPicker(result) {
    emojiPickerModal.classList.add('hidden');
    if (emojiPickerResolve) {
        const resolve = emojiPickerResolve;
        emojiPickerResolve = null;
        resolve(result);
    }
}

emojiPickerGrid.addEventListener('click', (event) => {
    const option = event.target.closest('.emoji-option');
    if (option) resolveEmojiPicker(option.dataset.emoji);
});

document.getElementById('emojiPickerClearBtn').addEventListener('click', () => resolveEmojiPicker(''));
document.getElementById('emojiPickerCancelBtn').addEventListener('click', () => resolveEmojiPicker(null));

// El botón de emoji de una fila o de la zona de añadir. Un único sitio que
// escribe su estado, para que lo que se ve y lo que se guarda no se separen.
function setEmojiButton(button, emoji) {
    button.dataset.emoji = emoji || '';
    // Sin emoji el botón no puede quedar vacío, o no habría nada que pulsar.
    button.textContent = emoji || '＋';
    button.classList.toggle('is-empty', !emoji);
}

// Abre el panel desde un botón de emoji y deja elegido lo que se elija.
async function editEmojiFromButton(button, habitName) {
    const chosen = await pickEmoji(button.dataset.emoji || '', habitName);
    if (chosen === null) return;
    setEmojiButton(button, chosen);
}

// Una sola forma de fila para cualquier hábito, los cinco de siempre y los que
// escribe el usuario. Con createElement y textContent, nunca innerHTML: el
// label lo escribe una persona y no se interpola en HTML.
//
// El emoji va en su propio campo, no pegado al nombre: es lo que lo hace
// editable, y es lo que evita que vuelva a terminar guardado dentro del label.
function buildHabitRow({ key, label, icon, color, checked }) {
    const row = document.createElement('label');
    row.className = 'habit-option';
    row.dataset.habitKey = key;
    row.dataset.habitLabel = label;
    // Vacío cuando el hábito no tiene emoji (la columna admite NULL). Poner acá
    // un ✅ de relleno lo escribiría en el backend en el siguiente Guardar sin
    // que nadie lo haya elegido; va de placeholder, que no se guarda.
    row.dataset.habitIcon = icon || '';
    row.dataset.habitColor = color || '#3498db';

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.value = key;
    checkbox.checked = checked !== false;

    const check = document.createElement('span');
    check.className = 'habit-check';

    // Abre el panel de emojis. Es un <button>, que es contenido interactivo:
    // el <label> no le reenvía el clic, así que pulsarlo no marca ni desmarca
    // el hábito.
    const iconBtn = document.createElement('button');
    iconBtn.type = 'button';
    iconBtn.className = 'habit-emoji';
    iconBtn.title = 'Cambiar emoji';
    iconBtn.setAttribute('aria-label', `Cambiar el emoji de ${label}`);
    setEmojiButton(iconBtn, row.dataset.habitIcon);

    const name = document.createElement('span');
    name.className = 'habit-name';
    name.textContent = label;

    const colorInput = document.createElement('input');
    colorInput.type = 'color';
    colorInput.className = 'habit-color';
    colorInput.value = row.dataset.habitColor;
    colorInput.dataset.habit = key;

    row.append(checkbox, check, iconBtn, name, colorInput);
    return row;
}

// El emoji que muestra la fila ahora mismo. Cadena vacía = el usuario no quiere
// emoji, y es una respuesta válida.
function getRowIcon(row) {
    const button = row.querySelector('.habit-emoji');
    return button ? (button.dataset.emoji || '') : (row.dataset.habitIcon || '');
}

// La lista de arriba es lo que sigues, y nada más.
function renderHabitRows(habits) {
    habitsOptions.innerHTML = '';
    habits.forEach(habit => {
        habitsOptions.appendChild(buildHabitRow({
            key: habit.key,
            label: habit.label || habit.key,
            icon: habit.icon,
            color: habit.color || DEFAULT_HABIT_COLOR,
            checked: true
        }));
    });

    habitsEmpty.classList.toggle('hidden', habits.length > 0);
}

// Los cinco predefinidos, como catálogo. Solo se ofrece lo que no está ya en el
// backend: un archivado no vuelve por acá, se restaura desde su lista, para que
// haya un solo camino de vuelta.
function renderSuggestions(knownKeys) {
    habitSuggestions.innerHTML = '';
    const pending = DEFAULT_HABITS.filter(def => !knownKeys.has(def.key));
    habitSuggestions.hidden = pending.length === 0;

    pending.forEach(def => {
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'habit-suggestion';
        chip.dataset.habitKey = def.key;

        const dot = document.createElement('span');
        dot.className = 'habit-suggestion-dot';
        dot.style.backgroundColor = def.color;

        const label = document.createElement('span');
        label.textContent = habitDisplayName(def.icon, def.label);

        chip.append(dot, label);
        habitSuggestions.appendChild(chip);
    });
}

async function showHabitsSetup() {
    // Marcar días de descanso según currentUser.rest_days
    const restDays = (currentUser && Array.isArray(currentUser.rest_days)) ? currentUser.rest_days : [];
    habitsSetupModal.querySelectorAll('input[name="rest_day"]').forEach(cb => {
        cb.checked = restDays.includes(parseInt(cb.value, 10));
    });

    if (getToken()) {
        try {
            const data = await apiFetch('/api/habits/definitions?include_inactive=true');
            const all = data.habits || [];
            setupAllHabits = all;

            renderHabitRows(all.filter(h => h.is_active));
            renderArchivedHabits(all.filter(h => !h.is_active));
            renderSuggestions(new Set(all.map(h => h.key)));
        } catch (error) {
            console.error('Error cargando hábitos para setup:', error);
        }
    }

    customHabitColor.value = pickFreeColor(HABIT_PALETTE[0]);
    updateColorWarning();
    await loadPauses();

    // Siempre al final: openHabitsSetup() toma la foto del dirty-check, así que
    // tiene que ver la lista ya pintada.
    openHabitsSetup();
}

// ============================================
// Hábitos archivados
// ============================================

// Construido con createElement y textContent, no con innerHTML: un innerHTML
// que interpolaba el label de un hábito sin escapar ya costó un arreglo, y no
// tiene sentido añadir una segunda copia del problema.
function renderArchivedHabits(archived) {
    archivedHabitsList.innerHTML = '';
    archivedCountEl.textContent = String(archived.length);
    // Sin archivados la sección no aporta nada, así que no se muestra.
    archivedHabits.hidden = archived.length === 0;

    archived.forEach(habit => {
        const row = document.createElement('div');
        row.className = 'archived-row';
        row.dataset.habitKey = habit.key;
        row.dataset.habitId = String(habit.id);

        const dot = document.createElement('span');
        dot.className = 'archived-dot';
        dot.style.backgroundColor = habit.color || '#95a5a6';

        const name = document.createElement('span');
        name.className = 'archived-name';
        name.textContent = habitDisplayName(habit.icon, habit.label || habit.key);
        // Para el texto del confirm de borrado: un archivado no está en
        // HABIT_LABELS, que solo trae los activos.
        row.dataset.habitName = name.textContent;

        const restoreBtn = document.createElement('button');
        restoreBtn.type = 'button';
        restoreBtn.className = 'archived-restore';
        restoreBtn.textContent = 'Restaurar';

        const deleteBtn = document.createElement('button');
        deleteBtn.type = 'button';
        deleteBtn.className = 'archived-delete';
        deleteBtn.title = 'Eliminar definitivamente';
        deleteBtn.setAttribute('aria-label', `Eliminar definitivamente ${name.textContent}`);
        deleteBtn.textContent = '🗑️';

        row.append(dot, name, restoreBtn, deleteBtn);
        archivedHabitsList.appendChild(row);
    });
}

// Volver a seguir un hábito archivado. Su historial nunca se tocó, así que sus
// marcas antiguas reaparecen en el calendario tal como estaban.
async function restoreHabit(habitId) {
    try {
        await apiFetch(`/api/habits/definitions/${habitId}`, {
            method: 'PATCH',
            json: { is_active: true }
        });
        await loadHabitDefinitionsFromAPI();
        await loadHabitsFromAPI();
        // Repinta las dos listas y, sobre todo, vuelve a pasar por
        // openHabitsSetup(), que retoma la foto del dirty-check: el cambio ya
        // está guardado, así que al cerrar no debe preguntar si descartarlo.
        await showHabitsSetup();
    } catch (error) {
        console.error('Error al restaurar hábito:', error);
    }
}

// Borra el historial y la definición. Es lo único irreversible de este modal,
// de ahí la confirmación. Devuelve si se llegó a borrar.
// Lo que la confirmación dice que pasará: cuántos registros se van y cómo quedan
// la racha y el récord (los días en que fue lo único hecho pasan a fallados).
function deleteImpactText(impact) {
    const days = n => `${n} ${n === 1 ? 'día' : 'días'}`;
    const lost = impact.records === 0 ? 'No tiene registros que borrar, pero no se puede deshacer.'
        : impact.records === 1 ? 'Se borrará su único registro y no se puede deshacer.'
        : `Se borrarán sus ${impact.records} registros y no se puede deshacer.`;
    const lines = [lost];
    const changes = [];
    if (impact.streak_after !== impact.streak_before) {
        changes.push(`tu racha pasaría de ${days(impact.streak_before)} a ${days(impact.streak_after)}`);
    }
    if (impact.best_after !== impact.best_before) {
        changes.push(`tu récord, de ${days(impact.best_before)} a ${days(impact.best_after)}`);
    }
    lines.push(changes.length
        ? `${changes.join(' y ')}.`.replace(/^t/, 'T')
        : 'Tu racha y tu récord no cambian.');
    return lines.join(' ');
}

async function deleteHabitForever(habitKey, habitName, habitId) {
    let detail = 'Se borrará todo su historial y no se puede deshacer.';
    try {
        const impact = await apiFetch(`/api/habits/definitions/${habitId}/delete-impact?today=${getDateKey(new Date())}`);
        detail = deleteImpactText(impact);
    } catch (error) {
        // Sin el cálculo se pregunta igual, con el aviso de siempre
        console.error('No se pudo calcular el impacto de borrar:', error);
    }
    const ok = await confirmDialog(`¿Seguro que quieres eliminar el hábito "${habitName || habitKey}"? ${detail}`, {
        title: '¿Eliminar hábito?',
        confirmLabel: '🗑️ Eliminar',
        cancelLabel: 'Cancelar',
        danger: true
    });
    if (!ok) return false;

    try {
        await apiFetch('/api/habits/delete-habit', {
            method: 'DELETE',
            json: { habit_key: habitKey }
        });

        const data = await apiFetch('/api/habits/definitions?include_inactive=true');
        const habit = data.habits ? data.habits.find(h => h.key === habitKey) : null;
        if (habit) {
            await apiFetch(`/api/habits/definitions/${habit.id}`, { method: 'DELETE' });
        }

        await loadHabitDefinitionsFromAPI();
        await loadHabitsFromAPI();
        return true;
    } catch (error) {
        console.error('Error al eliminar hábito:', error);
        return false;
    }
}

archivedHabitsList.addEventListener('click', async (event) => {
    const row = event.target.closest('.archived-row');
    if (!row) return;

    if (event.target.closest('.archived-restore')) {
        await restoreHabit(Number(row.dataset.habitId));
        return;
    }

    if (event.target.closest('.archived-delete')) {
        const deleted = await deleteHabitForever(row.dataset.habitKey, row.dataset.habitName, Number(row.dataset.habitId));
        if (deleted) await showHabitsSetup();
    }
});

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
    habitsOptions.querySelectorAll('.habit-option').forEach(row => {
        if (!row.querySelector('input[type="checkbox"]').checked) return;
        const colorInput = row.querySelector('input[type="color"]');
        // El emoji entra en la foto: si no, cambiarlo y pulsar Guardar cerraría
        // el modal sin escribir nada, porque el dirty-check no vería el cambio.
        habits.push(`${row.dataset.habitKey}:${colorInput ? colorInput.value : ''}:${getRowIcon(row)}`);
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

// El color de cada hábito marcado. No escribe nada: la comprobación de cambios
// sin guardar lee el formulario antes de saber si el usuario quiere guardar, así
// que leer no debe persistir por el camino.
function getSelectedHabitColors() {
    const colors = {};

    habitsOptions.querySelectorAll('.habit-option').forEach(row => {
        if (!row.querySelector('input[type="checkbox"]').checked) return;
        const colorInput = row.querySelector('input[type="color"]');
        if (colorInput) colors[row.dataset.habitKey] = colorInput.value;
    });

    return colors;
}

async function handleSaveHabits() {
    const rows = Array.from(habitsOptions.querySelectorAll('.habit-option'));
    const checkedRows = rows.filter(row => row.querySelector('input[type="checkbox"]').checked);
    const setupError = document.getElementById('setupError');

    if (checkedRows.length === 0) {
        showError(setupError, 'Selecciona al menos un hábito');
        return;
    }

    if (!isHabitsSetupDirty()) {
        // Nada que guardar: cerrar sin preguntar y sin tocar el backend.
        hideHabitsSetup();
        habitsSetupInitialState = null;
        return;
    }

    const confirmed = await confirmDialog('¿Guardar estos cambios en tus hábitos y días de descanso?', {
        confirmLabel: 'Guardar'
    });
    if (!confirmed) return;

    // Recién ahora se persiste, para que cancelar el confirm no deje nada a
    // medias. Nombre, emoji y color viven en el backend, que es lo que los hace
    // viajar entre dispositivos.
    const selectedKeys = checkedRows.map(row => row.dataset.habitKey);

    localStorage.setItem('user_habits', JSON.stringify(selectedKeys));

    const selectedRestDays = [];
    habitsSetupModal.querySelectorAll('input[name="rest_day"]:checked').forEach(cb => {
        selectedRestDays.push(parseInt(cb.value, 10));
    });
    selectedRestDays.sort((a, b) => a - b);

    if (!getToken()) {
        // Sin sesión no hay a quién atribuir nada; al menos la vista local
        // queda coherente con lo elegido.
        HABITS.length = 0;
        selectedKeys.forEach(key => HABITS.push(key));
        checkedRows.forEach(row => {
            HABIT_LABELS[row.dataset.habitKey] = row.dataset.habitLabel;
            HABIT_ICONS[row.dataset.habitKey] = getRowIcon(row);
        });
        renderHabitPopoverButtons();
        renderCalendar();
        hideHabitsSetup();
        habitsSetupInitialState = null;
        return;
    }

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
        const data = await apiFetch('/api/habits/definitions?include_inactive=true');
        const byKey = {};
        (data.habits || []).forEach(h => { byKey[h.key] = h; });
        const checkedKeys = new Set(selectedKeys);

        // Archivar lo que el backend tiene activo y ya no está marcado.
        for (const habit of Object.values(byKey)) {
            if (habit.is_active && !checkedKeys.has(habit.key)) {
                await apiFetch(`/api/habits/definitions/${habit.id}`, {
                    method: 'PATCH',
                    json: { is_active: false }
                });
            }
        }

        // Crear, reactivar o actualizar, según qué haya cambiado.
        for (const row of checkedRows) {
            const existing = byKey[row.dataset.habitKey];
            const icon = getRowIcon(row);

            if (!existing) {
                await apiFetch('/api/habits/definitions', {
                    method: 'POST',
                    json: {
                        key: row.dataset.habitKey,
                        label: row.dataset.habitLabel,
                        icon: icon,
                        // Sin order: el backend lo pone al final, detrás de
                        // todos (ocultos incluidos), y no mueve a ninguno
                        color: row.querySelector('input[type="color"]').value
                    }
                });
                continue;
            }

            // Un solo PATCH con lo que de verdad cambió: reactivar, cambiar el
            // emoji y el color pueden pasar en el mismo Guardar.
            const changes = {};
            const color = row.querySelector('input[type="color"]').value;
            if (!existing.is_active) changes.is_active = true;
            if ((existing.icon || '') !== icon) changes.icon = icon;
            if ((existing.color || '').toLowerCase() !== color.toLowerCase()) changes.color = color;
            if (Object.keys(changes).length === 0) continue;

            await apiFetch(`/api/habits/definitions/${existing.id}`, {
                method: 'PATCH',
                json: changes
            });
        }

        await loadHabitDefinitionsFromAPI();
        await loadHabitsFromAPI();
    } catch (error) {
        console.error('Error al guardar los hábitos:', error);
        showError(setupError, 'No se pudieron guardar todos los cambios. Revisa tu conexión.');
        return;
    }

    hideHabitsSetup();
    habitsSetupInitialState = null;
    renderCalendar();
}

// El + se habilita en cuanto hay algo escrito. Antes había que marcar una
// casilla para que el campo se dejara escribir; con el catálogo fuera de la
// lista esa puerta ya no tenía sentido.
// Cambiar un color o marcar/desmarcar un hábito puede crear o deshacer una repetición
habitsOptions.addEventListener('input', updateColorWarning);
habitsOptions.addEventListener('change', updateColorWarning);
customHabitColor.addEventListener('input', updateColorWarning);

customHabitInput.addEventListener('input', () => {
    updateColorWarning();
    addCustomHabitBtn.disabled = customHabitInput.value.trim() === '';
    document.getElementById('setupError').classList.add('hidden');
});

customHabitInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && customHabitInput.value.trim() !== '') {
        e.preventDefault();
        addDynamicHabit();
    }
});

addCustomHabitBtn.addEventListener('click', () => {
    if (customHabitInput.value.trim() !== '') {
        addDynamicHabit();
    }
});

// Delegado: las filas se crean y se destruyen al abrir el modal, así que el
// listener vive en el contenedor y no en cada botón.
habitsOptions.addEventListener('click', (event) => {
    const button = event.target.closest('.habit-emoji');
    if (!button) return;
    // Un <button> es contenido interactivo y el <label> no le reenvía el clic,
    // pero cancelarlo acá cuesta una línea y el precio de equivocarse es que
    // elegir un emoji desmarque el hábito.
    event.preventDefault();
    const row = button.closest('.habit-option');
    editEmojiFromButton(button, row ? row.dataset.habitLabel : '');
});

customHabitIconBtn.addEventListener('click', () => {
    editEmojiFromButton(customHabitIconBtn, customHabitInput.value.trim());
});

// El botón nace con el 🎯 pintado en el HTML, pero addDynamicHabit() lee
// dataset.emoji: sin esto, el primer hábito propio se crearía sin emoji.
setEmojiButton(customHabitIconBtn, '🎯');

// Tocar una sugerencia añade su fila, ya marcada. Se crea de verdad al pulsar
// Guardar, como todo lo demás de este modal.
habitSuggestions.addEventListener('click', (event) => {
    const chip = event.target.closest('.habit-suggestion');
    if (!chip) return;

    const def = DEFAULT_HABITS.find(d => d.key === chip.dataset.habitKey);
    if (!def) return;

    habitsOptions.appendChild(buildHabitRow({ ...def, color: pickFreeColor(def.color), checked: true }));
    habitsEmpty.classList.add('hidden');
    chip.remove();
    customHabitColor.value = pickFreeColor(customHabitColor.value);
    updateColorWarning();
    habitSuggestions.hidden = habitSuggestions.children.length === 0;
});

// Guardar hábitos
saveHabitsBtn.addEventListener('click', handleSaveHabits);

// Configuración desde la barra de usuario
settingsBtn.addEventListener('click', showHabitsSetup);
userEmail.addEventListener('click', showProfile);
profileForm.addEventListener('submit', handleProfileSave);

// ============================================
// Hábitos Dinámicos (Custom)
// ============================================

function addDynamicHabit() {
    const label = customHabitInput.value.trim();
    // La clave sale del texto, así que dos nombres iguales son el mismo hábito.
    const key = label.toLowerCase().replace(/\s+/g, '');
    const setupError = document.getElementById('setupError');

    if (!key) return;

    // Comparación en JS, no un selector con la clave interpolada: un nombre con
    // comillas rompería el querySelector.
    const already = Array.from(habitsOptions.querySelectorAll('.habit-option'))
        .some(row => row.dataset.habitKey === key);
    if (already) {
        showError(setupError, `El hábito "${label}" ya está en tu lista`);
        return;
    }

    habitsOptions.appendChild(buildHabitRow({
        key,
        label,
        // El que quedó elegido en el botón de al lado; en la fila se puede
        // cambiar otra vez antes de guardar.
        icon: customHabitIconBtn.dataset.emoji || '',
        color: customHabitColor.value,
        checked: true
    }));
    habitsEmpty.classList.add('hidden');

    setEmojiButton(customHabitIconBtn, '🎯');
    customHabitInput.value = '';
    customHabitColor.value = pickFreeColor(HABIT_PALETTE[0]);
    updateColorWarning();
    addCustomHabitBtn.disabled = true;
    setupError.classList.add('hidden');
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
        setStreakInfo(data);

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

        await uploadLocalHabitColors(data.habits || []);

        HABITS.length = 0;
        resetMonthHabits();
        Object.keys(HABIT_LABELS).forEach(key => delete HABIT_LABELS[key]);
        Object.keys(HABIT_ICONS).forEach(key => delete HABIT_ICONS[key]);
        Object.keys(HABIT_COLORS).forEach(key => delete HABIT_COLORS[key]);

        if (data.habits && data.habits.length > 0) {
            data.habits.sort((a, b) => (a.order || 0) - (b.order || 0));
            data.habits.forEach(h => {
                HABITS.push(h.key);
                HABIT_LABELS[h.key] = h.label;
                HABIT_ICONS[h.key] = h.icon || '';
                if (h.color) HABIT_COLORS[h.key] = h.color;
            });
        }

        loadSavedColors();
        renderHabitPopoverButtons();
        renderCalendar();
    } catch (error) {
        console.error('Error cargando definiciones de hábitos:', error);
    }
}

// Marca o desmarca UN hábito en un día. Nunca se manda el día completo: la
// pantalla solo conoce los hábitos activos, y reescribir el día borraba los
// registros de los ocultos (y lo que otro dispositivo guardó entretanto).
// Devuelve el día tal como quedó en el backend.
async function markHabitOnDay(dateKey, habitKey, done) {
    const entry = await apiFetch(`/api/habits/day/${dateKey}`, {
        method: 'PATCH',
        json: { habit_key: habitKey, done }
    });
    const data = entry.habits_data || {};
    if (Object.values(data).some(Boolean)) {
        habitsData[dateKey] = data;
    } else {
        delete habitsData[dateKey];
    }
    return data;
}

async function saveHabitToAPI(dateKey, habitKey, done) {
    try {
        const token = getToken();
        if (!token) return;

        await markHabitOnDay(dateKey, habitKey, done);
        // Desmarcar el último registro de un oculto lo saca de la lista del mes
        if (isHiddenHabit(habitKey)) resetMonthHabits(dateKey);
        renderCalendar();

        // Marcar o desmarcar un día puede cambiar la racha: pedirla al backend,
        // que es quien aplica la regla (días de descanso incluidos).
        await refreshStreakFromAPI();
    } catch (error) {
        console.error('Error guardando hábito:', error);
        // Lo que se pintó por adelantado no se guardó: volver a lo del backend
        await loadHabitsFromAPI();
    }
}

function setStreakInfo(data) {
    currentStreak = data.streak;
    streakInfo = {
        best: data.best_streak || 0,
        shields: data.streak_shields || 0,
        nextIn: data.shield_next_in ?? null,
        protectedDays: new Set(data.protected_days || []),
        missedYesterday: data.missed_yesterday || null,
        habitStreaks: data.habit_streaks || {},
        pausedDays: new Set(data.paused_days || []),
    };
}

// Los dos lugares de protector: los que hay, llenos; los que faltan, vacíos, y
// debajo cuánto falta para recargar el siguiente (días hechos de racha).
function renderShields(info) {
    const box = document.getElementById('streakShields');
    box.classList.toggle('hidden', !info);
    if (!info) return;
    box.querySelectorAll('.shield-slot').forEach((slot, i) => {
        slot.classList.toggle('spent', i >= info.shields);
    });
    const recharge = info.shields < 2 && info.nextIn
        ? `Recarga en ${info.nextIn} ${info.nextIn === 1 ? 'día' : 'días'}`
        : '';
    document.getElementById('shieldRecharge').textContent = recharge;
    box.setAttribute('aria-label', `${info.shields} de 2 protectores de racha` + (recharge ? `. ${recharge}` : ''));
}

async function refreshStreakFromAPI() {
    try {
        const data = await apiFetch(`/api/habits/streak?today=${getDateKey(new Date())}`);
        setStreakInfo(data);
        // Anotar un día perdido puede devolver su protector: el calendario
        // también cambia, no solo el número.
        renderCalendar();
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
    const monthHabits = habitsForMonth(year, month);
    
    for (let day = 1; day <= daysInMonth; day++) {
        const dateKey = `${monthKey}-${String(day).padStart(2, '0')}`;
        const dayData = habitsData[dateKey];
        
        if (dayData) {
            monthHabits.forEach(habit => {
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
        totalPossible = today * monthHabits.length;
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
    const monthHabits = habitsForMonth(year, month);

    // Inicializar contadores
    monthHabits.forEach(habit => {
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
                monthHabits.forEach(habit => {
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
    document.getElementById('bestStreak').textContent = streakInfo ? streakInfo.best : 0;
    renderShields(streakInfo);
    // Días de cada hábito y su racha propia viven en la leyenda (renderLegend),
    // que se repinta con el calendario
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

    const monthHabits = habitsForMonth(year, month);
    loadMonthHabits(year, month);
    
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
        // Lo que aún no pasa, distinto de lo que pasó sin cumplirse
        if (dateKey > todayKey) {
            dayCell.classList.add('future');
        }

        // Estilo atenuado para días de descanso sin hábitos
        const jsDay = date.getDay();
        const pyWeekday = (jsDay + 6) % 7;
        const restDays = (currentUser && Array.isArray(currentUser.rest_days)) ? currentUser.rest_days : [];
        const hasAnyHabit = Object.values(dayData).some(v => Boolean(v));
        if (restDays.includes(pyWeekday) && !hasAnyHabit) {
            dayCell.classList.add('rest-day');
            dayCell.title = 'Día de descanso: no suma ni corta la racha';
        } else if (streakInfo && streakInfo.pausedDays.has(dateKey) && !hasAnyHabit) {
            dayCell.classList.add('paused');
            dayCell.title = 'Vacaciones: no suma ni corta la racha';
        }
        if (streakInfo && streakInfo.protectedDays.has(dateKey)) {
            dayCell.classList.add('protected');
            dayCell.title = 'Un protector cuidó la racha este día';
            const shield = document.createElement('span');
            shield.className = 'day-shield';
            shield.textContent = '🛡️';
            dayCell.appendChild(shield);
        }
        
        // Número del día
        const dayNumber = document.createElement('span');
        dayNumber.className = 'day-number';
        dayNumber.textContent = day;
        dayCell.appendChild(dayNumber);
        
        // Puntos: un lugar por hábito del mes (activos + ocultos con registros)
        const dotsContainer = document.createElement('div');
        dotsContainer.className = 'habit-dots';
        // Una fila hasta 5; con más, dos filas parejas (3+3, 4+3…)
        dotsContainer.style.setProperty('--dots-per-row', dotsPerRow(monthHabits.length));

        monthHabits.forEach(habit => {
            const dot = document.createElement('span');
            dot.className = `habit-dot ${habit}`;
            

            // Si el hábito está marcado para este día, mostrar con su color
            // Si no está marcado, mostrar en gris
            if (dayData[habit]) {
                dot.classList.add('active');
                dot.style.backgroundColor = habitColor(habit);
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
    
    renderLegend(monthHabits);
    updateProgress();
    renderMetrics();
}

// Qué es cada punto, en los mismos lugares que los puntos del mes: punto y
// nombre, y debajo los días hechos este mes y la racha propia del hábito
function renderLegend(monthHabits) {
    const legend = document.getElementById('habitLegend');
    legend.innerHTML = '';
    legend.style.setProperty('--dots-per-row', dotsPerRow(monthHabits.length));
    document.getElementById('legendBlock').hidden = monthHabits.length === 0;
    const stats = calculateHabitStats();
    const dayWord = n => (n === 1 ? 'día' : 'días');
    monthHabits.forEach(habit => {
        const item = document.createElement('span');
        item.className = 'legend-item';
        item.dataset.habit = habit;
        const name = habitDisplayName(HABIT_ICONS[habit], HABIT_LABELS[habit] || habit);
        const done = stats[habit] || 0;
        const ownStreak = streakInfo ? (streakInfo.habitStreaks[habit] || 0) : 0;

        let tip = `${name}: ${done} ${dayWord(done)} este mes`;
        if (ownStreak > 0) tip += ` · racha de ${ownStreak} ${dayWord(ownStreak)}`;
        if (isHiddenHabit(habit)) {
            item.classList.add('is-hidden');
            tip += ' (oculto)';
        }
        item.title = tip;

        const dot = document.createElement('span');
        dot.className = 'legend-dot';
        dot.style.backgroundColor = habitColor(habit);
        const label = document.createElement('span');
        label.className = 'legend-name';
        label.textContent = name;
        const meta = document.createElement('span');
        meta.className = 'legend-meta';
        const count = document.createElement('span');
        count.className = 'legend-count';
        count.textContent = done;
        meta.appendChild(count);
        if (ownStreak > 0) {
            const streakTag = document.createElement('span');
            streakTag.className = 'legend-streak';
            streakTag.textContent = `🔥${ownStreak}`;
            meta.appendChild(streakTag);
        }
        item.append(dot, label, meta);
        legend.appendChild(item);
    });
}

function showHabitPopover(dateKey, targetCell) {
    selectedDate = dateKey;
    
    // Actualizar fecha en popover
    const [year, month, day] = dateKey.split('-');
    const date = new Date(year, month - 1, day);
    const options = { weekday: 'long', day: 'numeric', month: 'short' };
    popoverDate.textContent = date.toLocaleDateString('es-ES', options);
    
    // Los hábitos del mes de ese día: cambia con el mes y con los ocultos
    renderHabitPopoverButtons(dateKey);
    
    // Actualizar estado de botones según los datos actuales
    const dayData = habitsData[dateKey] || {};
    const buttons = habitsList.querySelectorAll('.habit-btn');
    
    let doneCount = 0;
    buttons.forEach(btn => {
        const habit = btn.dataset.habit;
        const isCompleted = !!dayData[habit];
        btn.classList.toggle('completed', isCompleted);
        btn.setAttribute('aria-pressed', String(isCompleted));
        if (isCompleted) doneCount++;
    });
    renderPopoverFooter(dateKey, doneCount, buttons.length);
    
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
    
    // Solo cambia este hábito: los demás del día (también los de hábitos
    // ocultos, que la pantalla no muestra) quedan como estaban.
    const dayData = { ...(habitsData[selectedDate] || {}) };
    const done = !dayData[habit];
    if (done) {
        dayData[habit] = true;
    } else {
        delete dayData[habit];
    }
    if (Object.values(dayData).some(Boolean)) {
        habitsData[selectedDate] = dayData;
    } else {
        delete habitsData[selectedDate];
    }

    // Guardar en API si está autenticado
    if (isAuthenticated()) {
        saveHabitToAPI(selectedDate, habit, done);
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

    // `habit_labels` quedó obsoleto: el nombre lo manda el backend. Se limpia
    // para no dejar en el navegador una copia vieja —con el emoji metido dentro
    // del nombre— que ya nadie lee.
    localStorage.removeItem('habit_labels');

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

// Pie del popover: "N de M hoy" y, si el día no cuenta como fallado, por qué
function renderPopoverFooter(dateKey, doneCount, total) {
    const isToday = dateKey === getDateKey(new Date());
    document.getElementById('popoverCount').textContent =
        total > 0 ? `${doneCount} de ${total}${isToday ? ' hoy' : ''}` : '';

    const [year, month, day] = dateKey.split('-').map(Number);
    const weekday = (new Date(year, month - 1, day).getDay() + 6) % 7;
    const restDays = (currentUser && Array.isArray(currentUser.rest_days)) ? currentUser.rest_days : [];
    let state = '';
    if (streakInfo && streakInfo.protectedDays.has(dateKey)) {
        state = '🛡️ Lo cubrió un escudo';
    } else if (restDays.includes(weekday) && doneCount === 0) {
        state = 'Día de descanso';
    } else if (streakInfo && streakInfo.pausedDays.has(dateKey) && doneCount === 0) {
        state = '🏖️ Vacaciones';
    }
    document.getElementById('popoverState').textContent = state;
}

// ============================================
// Hábitos de cada mes
// ============================================
// Un mes muestra los hábitos activos más los ocultos con algún registro en ese
// mes, en orden (order, id): GET /api/habits/month-habits. Puntos, popover y
// "Este mes" salen de esa lista, así que ocultar un hábito no cambia cómo se ve
// un mes en el que lo hiciste. Caché por "AAAA-MM"; se vacía cuando cambian
// las definiciones. Mientras llega, se usan los activos.
const monthHabitsCache = {};
const monthHabitsLoading = new Set();
let monthHabitsGeneration = 0;

function monthKeyOf(year, month) {
    return `${year}-${String(month + 1).padStart(2, '0')}`;
}

function habitsForMonth(year, month) {
    const cached = monthHabitsCache[monthKeyOf(year, month)];
    return cached ? cached.map(h => h.key) : HABITS;
}

// Puntos, leyenda y "Este mes" comparten geometría: una fila hasta 5, y con
// más, dos filas parejas (3+3, 4+3…)
function dotsPerRow(count) {
    return count <= 5 ? Math.max(count, 1) : Math.ceil(count / 2);
}

function habitsForDate(dateKey) {
    const [year, month] = dateKey.split('-').map(Number);
    return habitsForMonth(year, month - 1);
}

function isHiddenHabit(key) {
    return !HABITS.includes(key);
}

// Sin argumentos vacía todo; con una fecha "AAAA-MM-DD", solo su mes
function resetMonthHabits(dateKey) {
    if (dateKey) {
        delete monthHabitsCache[dateKey.slice(0, 7)];
        return;
    }
    Object.keys(monthHabitsCache).forEach(key => delete monthHabitsCache[key]);
    monthHabitsGeneration++;
}

async function loadMonthHabits(year, month) {
    const key = monthKeyOf(year, month);
    if (monthHabitsCache[key] || monthHabitsLoading.has(key) || !getToken()) return;
    monthHabitsLoading.add(key);
    const generation = monthHabitsGeneration;
    try {
        const data = await apiFetch(`/api/habits/month-habits?year=${year}&month=${month + 1}`);
        if (generation !== monthHabitsGeneration) return;   // las definiciones cambiaron entretanto
        const habits = data.habits || [];
        // Los ocultos no están en HABIT_LABELS/ICONS/COLORS, que llena
        // loadHabitDefinitionsFromAPI solo con los activos
        habits.forEach(h => {
            if (h.key in HABIT_LABELS) return;
            HABIT_LABELS[h.key] = h.label;
            HABIT_ICONS[h.key] = h.icon || '';
            if (h.color) HABIT_COLORS[h.key] = h.color;
        });
        monthHabitsCache[key] = habits;
        if (currentDate.getFullYear() === year && currentDate.getMonth() === month) {
            renderCalendar();
        }
    } catch (error) {
        console.error('Error cargando los hábitos del mes:', error);
    } finally {
        monthHabitsLoading.delete(key);
    }
}

// Función para renderizar los botones del popover dinámicamente
function renderHabitPopoverButtons(dateKey) {
    const habitsList = document.getElementById('habitsList');
    const activeHabits = dateKey ? habitsForDate(dateKey) : getActiveHabits();

    habitsList.innerHTML = '';

    if (activeHabits.length === 0) {
        habitsList.innerHTML = '<p class="no-habits-message">No hay hábitos configurados. <button class="link-btn" onclick="showHabitsSetup()">Configurar hábitos</button></p>';
        return;
    }
    
    activeHabits.forEach(habit => {
        const btn = document.createElement('button');
        btn.className = 'habit-btn';
        btn.dataset.habit = habit;
        
        // El color va como variable: sin marcar se pinta el aro, marcado el
        // relleno con halo (styles.css, .habit-btn .habit-dot)
        btn.style.setProperty('--habit-color', habitColor(habit));
        const dot = document.createElement('span');
        dot.className = `habit-dot ${habit}`;

        const label = document.createElement('span');
        label.className = 'habit-label';
        label.textContent = habitDisplayName(HABIT_ICONS[habit], HABIT_LABELS[habit] || habit);

        btn.appendChild(dot);
        btn.appendChild(label);
        if (isHiddenHabit(habit)) {
            btn.classList.add('is-hidden');
            const tag = document.createElement('span');
            tag.className = 'habit-hidden-tag';
            tag.textContent = 'oculto';
            btn.appendChild(tag);
        }

        // Evento click
        btn.addEventListener('click', () => toggleHabit(habit));
        
        habitsList.appendChild(btn);
    });
}

function loadSavedColors() {
    // Los colores ya están en HABIT_COLORS: solo repinta el popover
    renderHabitPopoverButtons();
}

// Hasta la 1.13 el color de cada hábito solo se guardaba en este navegador
// (localStorage.habit_colors). La primera vez que carga esta versión, se sube
// lo que haya al backend y se borra la clave. Si un PATCH falla, la clave se
// queda para reintentar en la próxima carga.
async function uploadLocalHabitColors(habits) {
    let local = null;
    try {
        local = JSON.parse(localStorage.getItem('habit_colors') || 'null');
    } catch (e) {
        local = null;
    }
    if (!local || typeof local !== 'object') {
        try { localStorage.removeItem('habit_colors'); } catch (e) {}
        return;
    }

    for (const habit of habits) {
        const color = local[habit.key];
        if (!color || !/^#[0-9a-fA-F]{6}$/.test(color)) continue;
        if (color.toLowerCase() === (habit.color || '').toLowerCase()) continue;
        try {
            const updated = await apiFetch(`/api/habits/definitions/${habit.id}`, {
                method: 'PATCH',
                json: { color },
            });
            habit.color = updated.color;
        } catch (error) {
            console.error('No se pudo subir el color del hábito:', error);
            return;
        }
    }
    try { localStorage.removeItem('habit_colors'); } catch (e) {}
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

// ============================================
// Vacaciones: pausas de la racha
// ============================================
// Se programan hoy o hacia adelante y duran hasta 30 días (lo valida el
// backend). Se guardan al momento, aparte de "Guardar Hábitos". Una en curso
// se puede terminar; una que no empieza, cancelar; las pasadas no se listan.
const pauseList = document.getElementById('pauseList');
const pauseStart = document.getElementById('pauseStart');
const pauseEnd = document.getElementById('pauseEnd');
const pauseError = document.getElementById('pauseError');

function shortDate(dateKey) {
    const [year, month, day] = dateKey.split('-').map(Number);
    return new Date(year, month - 1, day).toLocaleDateString('es-ES', { day: 'numeric', month: 'short' });
}

async function loadPauses() {
    const today = getDateKey(new Date());
    pauseStart.min = today;
    pauseEnd.min = today;
    if (!pauseStart.value || pauseStart.value < today) pauseStart.value = today;
    if (!pauseEnd.value || pauseEnd.value < pauseStart.value) pauseEnd.value = pauseStart.value;
    pauseError.classList.add('hidden');
    pauseList.innerHTML = '';
    let pauses = [];
    try {
        pauses = (await apiFetch('/api/habits/pauses')).pauses || [];
    } catch (error) {
        console.error('Error cargando las pausas:', error);
        return;
    }
    pauses.filter(p => p.end_date >= today).forEach(p => {
        const item = document.createElement('li');
        item.className = 'pause-item';
        const started = p.start_date <= today;
        const text = document.createElement('span');
        text.textContent = `🏖️ ${started ? 'En pausa' : 'Pausa'} del ${shortDate(p.start_date)} al ${shortDate(p.end_date)}`;
        const cancel = document.createElement('button');
        cancel.type = 'button';
        cancel.className = 'link-btn';
        cancel.dataset.pauseId = String(p.id);
        cancel.textContent = started ? 'Terminar' : 'Cancelar';
        item.append(text, cancel);
        pauseList.appendChild(item);
    });
}

// Tras programar o cancelar: la racha, el calendario y la lista cambian
async function afterPauseChange() {
    await loadHabitsFromAPI();
    await loadPauses();
}

document.getElementById('pauseAddBtn').addEventListener('click', async () => {
    pauseError.classList.add('hidden');
    try {
        await apiFetch(`/api/habits/pauses?today=${getDateKey(new Date())}`, {
            method: 'POST',
            json: { start_date: pauseStart.value, end_date: pauseEnd.value }
        });
    } catch (error) {
        showError(pauseError, error.message);
        return;
    }
    await afterPauseChange();
});

pauseList.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-pause-id]');
    if (!button) return;
    try {
        await apiFetch(`/api/habits/pauses/${button.dataset.pauseId}?today=${getDateKey(new Date())}`, { method: 'DELETE' });
    } catch (error) {
        showError(pauseError, error.message);
        return;
    }
    await afterPauseChange();
});

// El fin nunca antes del inicio
pauseStart.addEventListener('change', () => {
    pauseEnd.min = pauseStart.value;
    if (pauseEnd.value < pauseStart.value) pauseEnd.value = pauseStart.value;
});

// ============================================
// "¿Olvidaste anotar?" — ayer quedó sin hábitos
// ============================================
// El backend dice si ayer quedó vacío sin ser de descanso y con racha en juego
// (missed_yesterday). Se pregunta una vez por día perdido en cada dispositivo:
// se conteste o se cierre, ese día ya no se vuelve a preguntar.
const MISSED_ASKED_KEY = 'missed_day_asked';
const missedDayModal = document.getElementById('missedDayModal');
const missedDayHabits = document.getElementById('missedDayHabits');
const missedDayError = document.getElementById('missedDayError');
let missedDayDate = null;

function askMissedYesterday() {
    const missed = streakInfo && streakInfo.missedYesterday;
    if (!missed || !currentUser || HABITS.length === 0) return;
    // Otro modal a la vista (bienvenida, tope del cronómetro…): no encimarse
    if (document.querySelector('.modal:not(.hidden)')) return;
    const askedFor = `${currentUser.id}:${missed.date}`;
    try {
        if (localStorage.getItem(MISSED_ASKED_KEY) === askedFor) return;
        localStorage.setItem(MISSED_ASKED_KEY, askedFor);
    } catch (e) {
        // Sin localStorage se pregunta en cada carga: molesto, pero no rompe nada.
    }

    missedDayDate = missed.date;
    const days = `${missed.streak} ${missed.streak === 1 ? 'día' : 'días'}`;
    document.getElementById('missedDayText').textContent = missed.shielded
        ? `Ayer no anotaste ningún hábito y un protector 🛡️ cuidó tu racha de ${days}. Si sí lo hiciste, márcalo y recuperas el protector.`
        : `Ayer no anotaste ningún hábito y tu racha de ${days} se cortó. Si sí lo hiciste, márcalo y la recuperas.`;

    missedDayHabits.innerHTML = '';
    HABITS.forEach(key => {
        const row = document.createElement('label');
        row.className = 'habit-option';
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.value = key;
        const check = document.createElement('span');
        check.className = 'habit-check';
        const name = document.createElement('span');
        name.className = 'habit-label';
        name.textContent = habitDisplayName(HABIT_ICONS[key], HABIT_LABELS[key] || key);
        row.append(input, check, name);
        missedDayHabits.appendChild(row);
    });
    showModal(missedDayModal);
}

async function saveMissedYesterday() {
    const checked = [...missedDayHabits.querySelectorAll('input:checked')].map(input => input.value);
    if (checked.length === 0) {
        showError(missedDayError, 'Marca lo que hiciste, o elige «No, no lo hice».');
        return;
    }
    try {
        // Uno por uno, como en el popover: nunca reescribir el día entero
        for (const key of checked) {
            await markHabitOnDay(missedDayDate, key, true);
        }
    } catch (error) {
        showError(missedDayError, error.message);
        renderCalendar();
        return;
    }
    hideModal(missedDayModal);
    await refreshStreakFromAPI();
}

document.getElementById('missedDaySaveBtn').addEventListener('click', saveMissedYesterday);
document.getElementById('missedDaySkipBtn').addEventListener('click', () => hideModal(missedDayModal));
window.appDataHooks.push(askMissedYesterday);

// El campo de texto y el color están siempre activos; el + se habilita en
// cuanto hay algo escrito.
addCustomHabitBtn.disabled = true;

// DOMContentLoaded (no una llamada directa) para que, cuando existan más
// <script src> después de este (projects.js, pomodoro.js), sus funciones ya
// estén definidas antes de que initApp() los invoque vía los hooks de arriba.
document.addEventListener('DOMContentLoaded', initApp);
