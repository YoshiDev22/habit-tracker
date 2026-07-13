// ============================================
// Constantes y Configuración
// ============================================

const API_BASE_URL = '';  // Usar URL relativa

const HABITS = [];

const HABIT_LABELS = {};

// Variables para el modal de acción de hábito
let pendingHabitToRemove = null;
let previousHabits = [];

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

// ============================================
// Elementos del DOM - Auth
// ============================================

const authScreen = document.getElementById('authScreen');
const mainApp = document.getElementById('mainApp');
const userBar = document.getElementById('userBar');
const userEmail = document.getElementById('userEmail');
const loginModal = document.getElementById('loginModal');
const registerModal = document.getElementById('registerModal');
const showLoginBtn = document.getElementById('showLoginBtn');
const showRegisterBtn = document.getElementById('showRegisterBtn');
const loginForm = document.getElementById('loginForm');
const registerForm = document.getElementById('registerForm');
const loginError = document.getElementById('loginError');
const registerError = document.getElementById('registerError');
const logoutBtn = document.getElementById('logoutBtn');

// ============================================
// Funciones de Autenticación - Token
// ============================================

function saveToken(token) {
    localStorage.setItem('access_token', token);
}

function getToken() {
    return localStorage.getItem('access_token');
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
}

function showError(errorDiv, message) {
    errorDiv.textContent = message;
    errorDiv.classList.remove('hidden');
}

function updateUserBar() {
    if (currentUser) {
        userEmail.textContent = currentUser.email;
    }
}

// ============================================
// Funciones de API - Auth
// ============================================

async function register(email, password) {
    try {
        const response = await fetch(`${API_BASE_URL}/api/auth/register`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ email, password })
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
        const user = await register(email, password);
        
        // Después de registro exitoso, hacer login automáticamente
        const tokenData = await login(email, password);
        saveToken(tokenData.access_token);
        currentUser = user;
        
        hideAllModals();
        showMainApp();
        updateUserBar();
        
        // Cargar hábitos del backend
        loadHabitsFromAPI();
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
        
        // Obtener info del usuario (del token decodificado o hacer una llamada)
        currentUser = { email: email };
        
        hideAllModals();
        showMainApp();
        updateUserBar();
        
        // Cargar hábitos del backend
        loadHabitsFromAPI();
    } catch (error) {
        showError(loginError, error.message);
    }
}

function handleLogout() {
    removeToken();
    currentUser = null;
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

// Cerrar modales
document.querySelectorAll('[data-close-modal]').forEach(btn => {
    btn.addEventListener('click', hideAllModals);
});

// Cerrar modal al hacer click en overlay
document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', hideAllModals);
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

function showHabitsSetup() {
    showModal(habitsSetupModal);
}

function hideHabitsSetup() {
    hideModal(habitsSetupModal);
}

function getSelectedHabits() {
    const selected = [];
    const colors = {};
    
    const checkboxes = habitsOptions.querySelectorAll('input[type="checkbox"]');
    checkboxes.forEach(checkbox => {
        if (checkbox.checked && checkbox.id !== 'customHabitCheckbox') {
            selected.push(checkbox.value);
            const colorInput = habitsOptions.querySelector(`input[type="color"][data-habit="${checkbox.value}"]`);
            if (colorInput) {
                colors[checkbox.value] = colorInput.value;
            }
        }
    });
    
    localStorage.setItem('habit_colors', JSON.stringify(colors));
    
    return selected;
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
    
    // Guardar hábitos en localStorage
    localStorage.setItem('user_habits', JSON.stringify(selectedHabits));
    
    // Actualizar la variable global HABITS
    HABITS.length = 0;
    selectedHabits.forEach(h => HABITS.push(h));
    
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
    Object.assign(HABIT_LABELS, labels);
    
    // Cargar colores y renderizar popover
    loadSavedColors();
    
    // Renderizar popover con los nuevos hábitos
    renderHabitPopoverButtons();
    
    // Enviar hábitos dinámicos al backend
    const token = getToken();
    if (token) {
        for (const row of dynamicHabits) {
            const key = row.getAttribute('data-habit-key');
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
            } catch (error) {
                console.error(`Error al crear hábito dinámico '${key}':`, error);
            }
        }
    }
    
    // Ocultar modal de manera forzada
    habitsSetupModal.classList.add('hidden');
    const overlay = habitsSetupModal.querySelector('.modal-overlay');
    if (overlay) {
        overlay.style.display = 'none';
    }
    
    // Renderizar calendario con nuevos hábitos
    renderCalendar();
    
    // Forzar actualización visual
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

// Event listeners para el modal de acción de hábito
function showHabitActionModal(habitKey) {
    pendingHabitToRemove = habitKey;
    const savedLabels = JSON.parse(localStorage.getItem('habit_labels') || '{}');
    const habitName = savedLabels[habitKey] || habitKey;
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
    
    // Agregar a la lista de hábitos ocultos
    const hiddenHabits = JSON.parse(localStorage.getItem('hidden_habits') || '[]');
    if (!hiddenHabits.includes(pendingHabitToRemove)) {
        hiddenHabits.push(pendingHabitToRemove);
        localStorage.setItem('hidden_habits', JSON.stringify(hiddenHabits));
    }
    
    hideHabitActionModal();
    hideHabitsSetup();
    renderCalendar();
    renderHabitPopoverButtons();
});

// Eliminar hábito (borrar datos)
deleteHabitBtn.addEventListener('click', async () => {
    if (!pendingHabitToRemove) return;
    
    const token = getToken();
    if (token) {
        try {
            // Eliminar el hábito de todos los registros en la base de datos
            const response = await fetch(`${API_BASE_URL}/api/habits/delete-habit`, {
                method: 'DELETE',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ habit_key: pendingHabitToRemove })
            });
            
            if (!response.ok) {
                console.error('Error al eliminar hábito de la base de datos');
            }
        } catch (error) {
            console.error('Error:', error);
        }
    }
    
    // Eliminar de la lista de hábitos ocultos si está ahí
    const hiddenHabits = JSON.parse(localStorage.getItem('hidden_habits') || '[]');
    const newHiddenHabits = hiddenHabits.filter(h => h !== pendingHabitToRemove);
    localStorage.setItem('hidden_habits', JSON.stringify(newHiddenHabits));
    
    hideHabitActionModal();
    hideHabitsSetup();
    loadHabitsFromAPI();
});

// Cancelar
cancelHabitBtn.addEventListener('click', () => {
    hideHabitActionModal();
    // Volver a mostrar el modal de configuración
    showHabitsSetup();
});

// Cerrar modal de acción al hacer click en overlay
habitActionModal.querySelector('.modal-overlay').addEventListener('click', hideHabitActionModal);

// Configuración desde la barra de usuario
settingsBtn.addEventListener('click', showHabitsSetup);

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
        <button type="button" class="remove-habit-btn" title="Eliminar hábito" data-dynamic-key="${customValue}">×</button>
    `;

    // Insertar antes del row de "custom"
    const customRow = document.getElementById('customHabitRow');
    habitsOptions.insertBefore(newOption, customRow);

    // Evento para eliminar hábito dinámico
    const removeBtn = newOption.querySelector('.remove-habit-btn');
    removeBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        const key = removeBtn.getAttribute('data-dynamic-key');
        newOption.remove();
        // Limpiar localStorage si existe
        const hiddenHabits = JSON.parse(localStorage.getItem('hidden_habits') || '[]');
        const newHidden = hiddenHabits.filter(h => h !== key);
        localStorage.setItem('hidden_habits', JSON.stringify(newHidden));
    });

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

// Cerrar modal de setup al hacer click en overlay
habitsSetupModal.querySelector('.modal-overlay').addEventListener('click', hideHabitsSetup);

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

        const response = await fetch(`${API_BASE_URL}/api/habits`, {
            headers: {
                'Authorization': `Bearer ${token}`,
            }
        });

        if (!response.ok) {
            if (response.status === 401) {
                // Token expirado o inválido
                handleLogout();
                return;
            }
            throw new Error('Error al cargar hábitos');
        }

        const data = await response.json();
        
        // Convertir formato del backend al formato local
        habitsData = {};
        data.entries.forEach(entry => {
            const dateKey = entry.date;
            habitsData[dateKey] = entry.habits_data || {};
        });
        
        renderCalendar();
    } catch (error) {
        console.error('Error cargando hábitos:', error);
        // Si hay error, usar datos locales vacíos
        habitsData = {};
        renderCalendar();
    }
}

async function saveHabitToAPI(dateKey, habits) {
    try {
        const token = getToken();
        if (!token) return;

        // Convertir fecha al formato YYYY-MM-DD
        const date = dateKey;
        
        const response = await fetch(`${API_BASE_URL}/api/habits`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                date: date,
                habits: habits
            })
        });

        if (!response.ok) {
            if (response.status === 401) {
                handleLogout();
                return;
            }
            throw new Error('Error al guardar hábito');
        }

        // Actualizar datos locales
        habitsData[dateKey] = habits;
        renderCalendar();
    } catch (error) {
        console.error('Error guardando hábito:', error);
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

function calculateStreak() {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    
    let streak = 0;
    let checkDate = new Date(today);
    
    // Empezar desde hoy e ir hacia atrás
    while (true) {
        const dateKey = getDateKey(checkDate);
        const dayData = habitsData[dateKey];
        
        // Si hay datos para este día y tiene al menos un hábito completado
        if (dayData && HABITS.some(habit => dayData[habit])) {
            streak++;
            checkDate.setDate(checkDate.getDate() - 1);
        } else if (streak === 0 && dateKey === getDateKey(today)) {
            // Hoy no tiene hábitos, empezar desde ayer
            checkDate.setDate(checkDate.getDate() - 1);
        } else {
            // Romper la racha
            break;
        }
        
        // Limitar a máximo 365 días para evitar loops infinitos
        if (streak > 365) break;
    }
    
    return streak;
}

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
    const streak = calculateStreak();
    const streakCount = document.getElementById('streakCount');
    streakCount.textContent = streak;
    
    // Actualizar stats por hábito
    const stats = calculateHabitStats();
    const statsGrid = document.getElementById('statsGrid');
    statsGrid.innerHTML = '';
    
    HABITS.forEach(habit => {
        const statCard = document.createElement('div');
        statCard.className = 'stat-card';
        
        const dot = document.createElement('div');
        dot.className = `stat-dot ${habit}`;
        
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
                dot.style.backgroundColor = '#ccc'; // Gris para no completados
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
            dot.style.backgroundColor = isCompleted ? habitColor : '#ccc';
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

function initApp() {
    // Limpiar hábitos dinámicos al iniciar
    const dynamicHabits = habitsOptions.querySelectorAll('.dynamic-habit-row');
    dynamicHabits.forEach(h => h.remove());
    dynamicHabitCounter = 0;
    
    if (isAuthenticated()) {
        // Usuario ya autenticado, mostrar app y cargar datos
        currentUser = { email: 'Usuario' };
        showMainApp();
        updateUserBar();
        
        // Verificar si es usuario nuevo (sin hábitos guardados localmente)
        const userHabits = localStorage.getItem('user_habits');
        
        if (!userHabits || JSON.parse(userHabits).length === 0) {
            // Usuario nuevo - mostrar popup de configuración de hábitos
            showHabitsSetup();
            renderCalendar();
        } else {
            // Cargar hábitos guardados
            const habits = JSON.parse(userHabits);
            HABITS.length = 0;
            habits.forEach(h => HABITS.push(h));
            
            // Cargar etiquetas guardadas
            const savedLabels = localStorage.getItem('habit_labels');
            if (savedLabels) {
                const labels = JSON.parse(savedLabels);
                Object.assign(HABIT_LABELS, labels);
            }
            
            // Cargar colores guardados y renderizar popover
            loadSavedColors();
            renderHabitPopoverButtons();
            
            // Cargar datos de la API
            loadHabitsFromAPI();
        }
    } else {
        // Mostrar pantalla de autenticación
        showAuthScreen();
    }
}

// Función para obtener hábitos activos (no ocultos)
function getActiveHabits() {
    const hiddenHabits = JSON.parse(localStorage.getItem('hidden_habits') || '[]');
    return HABITS.filter(h => !hiddenHabits.includes(h));
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
    
    const savedColors = localStorage.getItem('habit_colors');
    if (savedColors) {
        const colors = JSON.parse(savedColors);
        // Actualizar variables CSS con los colores guardados
        Object.keys(colors).forEach(habit => {
            document.documentElement.style.setProperty(`--habit-${habit}`, colors[habit]);
        });
    }
}

// Inicializar estado disabled de campos custom
customHabitInput.disabled = true;
customHabitColor.disabled = true;
addCustomHabitBtn.disabled = true;

initApp();
