// ============================================
// Mi perfil: el menú, cambiar la contraseña e irte
// ============================================
//
// Mi perfil es un menú de desglose (createDrillDown, drilldown.js): Datos
// personales (el formulario de script.js), Cambiar contraseña y Borrar mi
// cuenta, cada una en su página.
//
// BACKLOG 26, la parte que no necesita correo. "Irme 30 días" programa el
// borrado (POST /api/auth/me/delete, mode=later) y cierra esta sesión; al
// volver a entrar antes del plazo, la app pregunta si conservar la cuenta.
// "Borrar ahora" lo borra todo al momento. Las dos piden la contraseña, y el
// usuario elige si cerrar sus otras sesiones.

const passwordForm = document.getElementById('passwordForm');
const passwordError = document.getElementById('passwordError');
const passwordStatus = document.getElementById('passwordStatus');
const deleteForm = document.getElementById('deleteForm');
const deleteChoices = document.getElementById('deleteChoices');
const deleteError = document.getElementById('deleteError');
const deleteState = { mode: null };   // later | now
const profileModalEl = document.getElementById('profileModal');

const profileNav = createDrillDown({
    modal: profileModalEl,
    menu: document.getElementById('profileMenu'),
    back: document.getElementById('profileBack'),
    title: document.getElementById('profileTitle'),
    rootTitle: 'Mi perfil',
    onPage: (name) => {
        if (name === 'password') document.getElementById('passwordCurrent').focus();
    },
    onClose: () => closeProfileModal(),
});

function formatDeleteDate(iso) {
    // UTC sin huso: se marca como UTC para verla en hora local
    return new Date(`${iso}Z`).toLocaleDateString('es-MX', { weekday: 'long', day: 'numeric', month: 'long' });
}

// ---------- Cambiar contraseña ----------

passwordForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    passwordError.classList.add('hidden');
    passwordStatus.textContent = '';
    const current = document.getElementById('passwordCurrent').value;
    const next = document.getElementById('passwordNew').value;
    if (next !== document.getElementById('passwordRepeat').value) {
        showError(passwordError, 'Las dos contraseñas nuevas no coinciden.');
        return;
    }
    try {
        const token = await apiFetch('/api/auth/me/password', {
            method: 'POST',
            json: { current_password: current, new_password: next,
                    logout_others: document.getElementById('passwordLogoutOthers').checked },
        });
        // Si se cerraron las otras sesiones, la de aquí sigue con el token nuevo
        saveToken(token.access_token);
    } catch (error) {
        showError(passwordError, error.message);
        return;
    }
    passwordForm.reset();
    document.getElementById('passwordLogoutOthers').checked = true;
    passwordStatus.textContent = 'Contraseña cambiada ✓';
});

// ---------- Borrar la cuenta ----------

function showDeleteForm(mode) {
    deleteState.mode = mode;
    deleteError.classList.add('hidden');
    deleteForm.reset();
    document.getElementById('deleteLogoutOthers').checked = true;
    document.getElementById('deleteExplain').textContent = mode === 'later'
        ? 'Tu cuenta se borrará en 30 días y se cerrará esta sesión. Si entras antes, podrás conservarla.'
        : 'Se borra todo ahora mismo. No se puede deshacer.';
    document.getElementById('deleteConfirmGroup').hidden = mode !== 'now';
    document.getElementById('deleteLogoutGroup').hidden = mode !== 'later';
    document.getElementById('deleteSubmit').textContent = mode === 'later' ? 'Irme 30 días' : 'Borrar mi cuenta';
    deleteChoices.hidden = true;
    deleteForm.hidden = false;
    document.getElementById('deletePassword').focus();
}

function hideDeleteForm() {
    deleteForm.hidden = true;
    deleteChoices.hidden = false;
    deleteState.mode = null;
}

document.getElementById('leaveLaterBtn').addEventListener('click', () => showDeleteForm('later'));
document.getElementById('deleteNowBtn').addEventListener('click', () => showDeleteForm('now'));
document.getElementById('deleteCancel').addEventListener('click', hideDeleteForm);

deleteForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    deleteError.classList.add('hidden');
    const mode = deleteState.mode;
    try {
        const result = await apiFetch('/api/auth/me/delete', {
            method: 'POST',
            json: {
                password: document.getElementById('deletePassword').value,
                mode,
                confirm: mode === 'now' ? document.getElementById('deleteConfirm').value : null,
                logout_others: document.getElementById('deleteLogoutOthers').checked,
            },
        });
        hideModal(profileModalEl);
        if (mode === 'later') {
            await confirmDialog(`Tu cuenta se borrará el ${formatDeleteDate(result.delete_after)}. `
                + 'Si cambias de opinión, entra antes de esa fecha y podrás conservarla.',
                { title: 'Hasta pronto', confirmLabel: 'Entendido', cancelLabel: 'Cerrar' });
        } else {
            await confirmDialog('Tu cuenta y todos tus datos se borraron.',
                { title: 'Cuenta borrada', confirmLabel: 'Entendido', cancelLabel: 'Cerrar' });
        }
    } catch (error) {
        showError(deleteError, error.message);
        return;
    }
    hideDeleteForm();
    handleLogout();
});

// Al abrir Mi perfil se ve el menú; al cerrarlo, lo de la cuenta vuelve a su estado inicial
function resetAccountSections() {
    hideDeleteForm();
    passwordForm.reset();
    document.getElementById('passwordLogoutOthers').checked = true;
    passwordError.classList.add('hidden');
    passwordStatus.textContent = '';
}

let profileWasOpen = false;
new MutationObserver(() => {
    const open = !profileModalEl.classList.contains('hidden');
    if (open && !profileWasOpen) profileNav.showMenu({ animate: false });
    if (!open && profileWasOpen) resetAccountSections();
    profileWasOpen = open;
}).observe(profileModalEl, { attributes: true, attributeFilter: ['class'] });

// ---------- Al entrar con el borrado programado ----------

async function askToKeepAccount() {
    if (!currentUser || !currentUser.delete_after) return;
    const keep = await confirmDialog(
        `Tu cuenta está programada para borrarse el ${formatDeleteDate(currentUser.delete_after)}. ¿Quieres conservarla?`,
        { title: 'Tu cuenta se va a borrar', confirmLabel: 'Conservar mi cuenta', cancelLabel: 'Seguir con el borrado' });
    if (!keep) {
        handleLogout();
        return;
    }
    try {
        currentUser = await apiFetch('/api/auth/me/keep', { method: 'POST' });
        updateUserBar();
    } catch (error) {
        console.error('No se pudo conservar la cuenta:', error);
    }
}

window.appDataHooks.push(askToKeepAccount);
