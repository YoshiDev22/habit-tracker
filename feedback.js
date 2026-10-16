// ============================================
// Reportar un problema (Mi perfil, 1.27)
// ============================================
//
// Una página del menú de Mi perfil: un texto (10 a 2000 caracteres) y, si el
// usuario lo deja encendido, detalles técnicos que ve tal cual antes de
// enviarlos: versión, pestaña abierta, pantalla, navegador y los últimos
// errores de la consola de esta sesión. POST /api/feedback lo guarda y se lee
// en el panel de administración. Nunca va un token ni nada de lo que
// el usuario escribe en la app (tareas, hábitos, gastos).
//
// Se carga justo después de script.js para oír los errores desde el principio.

const feedbackForm = document.getElementById('feedbackForm');
const feedbackText = document.getElementById('feedbackText');
const feedbackCount = document.getElementById('feedbackCount');
const feedbackDetailsOn = document.getElementById('feedbackDetailsOn');
const feedbackDetails = document.getElementById('feedbackDetails');
const feedbackPreview = document.getElementById('feedbackPreview');
const feedbackError = document.getElementById('feedbackError');
const feedbackStatus = document.getElementById('feedbackStatus');
const feedbackSubmit = document.getElementById('feedbackSubmit');

const FEEDBACK_MAX_ERRORS = 10;
const FEEDBACK_ERROR_CHARS = 300;
const feedbackErrors = [];

function rememberFeedbackError(text) {
    if (!text) return;
    feedbackErrors.push(String(text).slice(0, FEEDBACK_ERROR_CHARS));
    if (feedbackErrors.length > FEEDBACK_MAX_ERRORS) feedbackErrors.shift();
    if (!feedbackForm.closest('.settings-page').classList.contains('active')) return;
    refreshFeedbackPreview();
}

// Solo el nombre del archivo: la ruta completa no ayuda y podría traer más de la cuenta
function feedbackFileName(url) {
    return url ? String(url).split(/[?#]/)[0].split('/').pop() : '';
}

window.addEventListener('error', (event) => {
    const where = event.filename ? ` (${feedbackFileName(event.filename)}:${event.lineno || 0})` : '';
    rememberFeedbackError(`${event.message || 'Error'}${where}`);
});

window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason;
    rememberFeedbackError(reason && reason.message ? `${reason.name || 'Error'}: ${reason.message}` : `Promesa rechazada: ${reason}`);
});

// Lo que se envía, armado en el momento: la vista previa y el envío usan esto mismo
function feedbackTechnicalDetails() {
    const version = (document.getElementById('mainVersion').textContent || '').trim();
    const details = {
        version: version.slice(0, 20),
        view: typeof currentViewId === 'string' ? currentViewId.slice(0, 20) : '',
        screen: `${window.innerWidth}×${window.innerHeight}`,
        user_agent: navigator.userAgent.slice(0, 300),
    };
    if (feedbackErrors.length) details.errors = [...feedbackErrors];
    return details;
}

function refreshFeedbackPreview() {
    feedbackDetails.hidden = !feedbackDetailsOn.checked;
    feedbackPreview.textContent = JSON.stringify(feedbackTechnicalDetails(), null, 2);
}

function refreshFeedbackCount() {
    feedbackCount.textContent = `${feedbackText.value.length} / ${feedbackText.maxLength}`;
}

// Al abrir la página (la fila del menú de Mi perfil), con los datos de este momento
document.getElementById('profileMenu').addEventListener('click', (event) => {
    if (!event.target.closest('[data-open="feedback"]')) return;
    feedbackStatus.textContent = '';
    feedbackError.classList.add('hidden');
    refreshFeedbackPreview();
    setTimeout(() => feedbackText.focus(), 0);
});

feedbackDetailsOn.addEventListener('change', refreshFeedbackPreview);
feedbackText.addEventListener('input', refreshFeedbackCount);

feedbackForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    feedbackError.classList.add('hidden');
    feedbackStatus.textContent = '';
    const text = feedbackText.value.trim();
    if (text.length < 10) {
        showError(feedbackError, 'Cuéntanos un poco más: al menos 10 caracteres.');
        return;
    }
    feedbackSubmit.disabled = true;
    try {
        await apiFetch('/api/feedback', {
            method: 'POST',
            json: { text, details: feedbackDetailsOn.checked ? feedbackTechnicalDetails() : null },
        });
        feedbackText.value = '';
        refreshFeedbackCount();
        feedbackStatus.textContent = 'Gracias, lo vamos a revisar.';
    } catch (error) {
        showError(feedbackError, error.message || 'No se pudo enviar. Inténtalo de nuevo.');
    } finally {
        feedbackSubmit.disabled = false;
    }
});

function resetFeedback() {
    feedbackErrors.length = 0;   // los errores de esta sesión no pasan a otra cuenta
    feedbackForm.reset();
    refreshFeedbackCount();
    feedbackStatus.textContent = '';
    feedbackError.classList.add('hidden');
}

window.appLogoutHooks.push(resetFeedback);
