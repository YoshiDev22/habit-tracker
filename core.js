// ============================================
// Núcleo compartido: lo que usan las dos páginas, la app (index.html) y
// Finanzas (finance.html). Se carga primero en las dos.
// ============================================
//
// Solo funciones y constantes: nada de aquí busca un elemento al cargar, porque
// cada página tiene los suyos (el confirm, el botón del tema, el tamaño de
// letra). Cada página define su handleLogout(): apiFetch la llama con un 401.

const API_BASE_URL = '';  // Usar URL relativa

// ============================================
// Token
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

// Error de API con el status HTTP adjunto, para que el caller pueda
// distinguir p.ej. un 409 (conflicto) de un error genérico.
class ApiError extends Error {
    constructor(message, status) {
        super(message);
        this.name = 'ApiError';
        this.status = status;
    }
}

// Helper de fetch autenticado, para todo el código nuevo.
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

// ============================================
// Modales, errores y el confirm
// ============================================

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

function showError(errorDiv, message) {
    errorDiv.textContent = message;
    errorDiv.classList.remove('hidden');
}

// Confirm genérico (sí/no). Cada página trae su #confirmModal con los mismos
// ids; quien lo cierre por la X o el overlay llama a resolveConfirmDialog(false).
let confirmModalResolve = null;

function confirmDialog(message, { title = '¿Seguro?', confirmLabel = 'Sí', cancelLabel = 'Cancelar', danger = false } = {}) {
    // Solo un confirm a la vez: si ya había uno pendiente (doble click en
    // el botón que lo abrió), se resuelve como cancelado antes de abrir el nuevo.
    if (confirmModalResolve) {
        confirmModalResolve(false);
    }
    const confirmBtn = document.getElementById('confirmModalConfirmBtn');
    document.getElementById('confirmModalTitle').textContent = title;
    document.getElementById('confirmModalMessage').textContent = message;
    confirmBtn.textContent = confirmLabel;
    confirmBtn.classList.toggle('btn-danger', danger);
    document.getElementById('confirmModalCancelBtn').textContent = cancelLabel;
    showModal(document.getElementById('confirmModal'));

    return new Promise(resolve => {
        confirmModalResolve = resolve;
    });
}

function resolveConfirmDialog(result) {
    document.getElementById('confirmModal').classList.add('hidden');
    if (confirmModalResolve) {
        confirmModalResolve(result);
        confirmModalResolve = null;
    }
}

function initConfirmDialog() {
    const confirmBtn = document.getElementById('confirmModalConfirmBtn');
    if (!confirmBtn) return;
    confirmBtn.addEventListener('click', () => resolveConfirmDialog(true));
    document.getElementById('confirmModalCancelBtn').addEventListener('click', () => resolveConfirmDialog(false));
}

// ============================================
// Fechas
// ============================================

// La fecha LOCAL del usuario como "AAAA-MM-DD". La usa toda la app: hábitos,
// sesiones de tiempo, Reportes y el ?today= de la API.
function getDateKey(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

// ============================================
// Tema y tamaño del texto (de este dispositivo)
// ============================================

const THEME_CYCLE = ['system', 'light', 'dark'];
const THEME_ICONS = { system: '🖥️', light: '☀️', dark: '🌙' };
const THEME_LABELS = { system: 'Sistema', light: 'Claro', dark: 'Oscuro' };

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

// Aplica el tema; el botón del tema (#themeToggle) solo existe en la app
function applyTheme(pref) {
    const dark = pref === 'dark' || (pref === 'system' && getSystemPrefersDark());
    const root = document.documentElement;
    root.setAttribute('data-theme', dark ? 'dark' : 'light');
    root.setAttribute('data-theme-pref', pref);

    const themeColorMeta = document.getElementById('themeColorMeta');
    if (themeColorMeta) {
        themeColorMeta.setAttribute('content', dark ? '#14161a' : '#fafafa');
    }
    const themeToggleBtn = document.getElementById('themeToggle');
    if (themeToggleBtn) {
        themeToggleBtn.textContent = THEME_ICONS[pref];
        const label = `Tema: ${THEME_LABELS[pref]}`;
        themeToggleBtn.title = label;
        themeToggleBtn.setAttribute('aria-label', label);
    }
}

// Sigue al sistema mientras la preferencia sea "sistema"
function watchSystemTheme() {
    if (!window.matchMedia) return;
    const mql = window.matchMedia('(prefers-color-scheme: dark)');
    const onSystemChange = () => {
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

const TEXT_SIZES = ['normal', 'large', 'xlarge'];

function getTextSize() {
    try {
        const size = localStorage.getItem('text_size');
        return TEXT_SIZES.includes(size) ? size : 'normal';
    } catch (e) {
        return 'normal';
    }
}

// Aplica el tamaño; los botones (#textSizeToggle) solo existen en la app
function applyTextSize(size) {
    if (size === 'normal') {
        document.documentElement.removeAttribute('data-text-size');
    } else {
        document.documentElement.setAttribute('data-text-size', size);
    }
    const toggle = document.getElementById('textSizeToggle');
    if (!toggle) return;
    toggle.querySelectorAll('[data-size]').forEach(btn => {
        btn.setAttribute('aria-pressed', btn.dataset.size === size ? 'true' : 'false');
    });
}

// ============================================
// Dinero, texto y tablas pegadas (Costos y Finanzas)
// ============================================

// Las de CURRENCIES en backend/schemas.py
const CURRENCIES = ['MXN', 'USD', 'EUR', 'CAD', 'GBP', 'COP', 'ARS', 'CLP', 'PEN'];

function formatMoney(cents, currency) {
    try {
        return new Intl.NumberFormat('es-MX', { style: 'currency', currency }).format(cents / 100);
    } catch (error) {
        return `${(cents / 100).toFixed(2)} ${currency}`;
    }
}

function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
}

function normalize(text) {
    return String(text).trim().toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
}

// Texto de una hoja o un CSV en filas de celdas. Respeta comillas ("a, b") y
// saltos de línea dentro de ellas. El separador: tabulador (lo que copia
// Excel/Sheets), si no punto y coma (Excel en español), si no coma.
function parseTable(text) {
    const clean = text.replace(/^﻿/, '').replace(/\r\n?/g, '\n');
    const firstLine = clean.split('\n')[0];
    const sep = firstLine.includes('\t') ? '\t' : (firstLine.split(';').length > firstLine.split(',').length ? ';' : ',');
    const rows = [];
    let row = [];
    let value = '';
    let quoted = false;
    for (let i = 0; i < clean.length; i++) {
        const ch = clean[i];
        if (quoted) {
            if (ch === '"' && clean[i + 1] === '"') { value += '"'; i++; }
            else if (ch === '"') quoted = false;
            else value += ch;
        } else if (ch === '"' && value === '') quoted = true;
        else if (ch === sep) { row.push(value); value = ''; }
        else if (ch === '\n') { row.push(value); rows.push(row); row = []; value = ''; }
        else value += ch;
    }
    if (value !== '' || row.length) { row.push(value); rows.push(row); }
    return rows.filter(r => r.some(c => c.trim() !== ''));
}

// "1,234.50", "1.234,50", "$ 350", "350,5" → centavos; null si no es número
function parseMoneyCents(text) {
    let s = String(text).replace(/[^\d.,-]/g, '');
    if (!s) return null;
    const lastComma = s.lastIndexOf(',');
    const lastDot = s.lastIndexOf('.');
    if (lastComma > -1 && lastDot > -1) {
        // El que va al final es el decimal
        s = lastComma > lastDot ? s.replace(/\./g, '').replace(',', '.') : s.replace(/,/g, '');
    } else if (lastComma > -1) {
        // Solo coma: decimal si le siguen 1 o 2 cifras al final ("350,5"); si no, de miles
        s = /,\d{1,2}$/.test(s) ? s.replace(',', '.') : s.replace(/,/g, '');
    }
    const number = Number(s);
    return Number.isFinite(number) ? Math.round(number * 100) : null;
}

// "2026-09-30", "30/09/2026", "30/9/26" → "AAAA-MM-DD" (día primero: México); vacío → hoy
function parseDate(text) {
    const s = String(text).trim();
    if (!s) return getDateKey(new Date());
    let m = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
    if (m) return `${m[1]}-${m[2].padStart(2, '0')}-${m[3].padStart(2, '0')}`;
    m = s.match(/^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})$/);
    if (m) {
        const year = m[3].length === 2 ? `20${m[3]}` : m[3];
        const day = Number(m[1]);
        const month = Number(m[2]);
        if (month >= 1 && month <= 12 && day >= 1 && day <= 31) {
            return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
        }
    }
    return null;
}
