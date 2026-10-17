// ============================================
// Finanzas: ajustes, cuentas y el sueldo
// ============================================
//
// Ajustes es un menú de desglose (createDrillDown, drilldown.js): Periodo y
// sueldo, Categorías, Fijos y Cuentas archivadas. Una cuenta se crea o edita
// en su hoja (pestaña Cuentas). "¿Cuánto cobras?" guarda el sueldo como el fijo
// de ingreso "Sueldo".

const finSettingsModal = document.getElementById('finSettingsModal');
const finSettingsError = document.getElementById('finSettingsError');
const finSettings = {
    catKind: 'expense',
    editingCategory: null,
    catIcon: 'ellipsis',
    catColor: FIN_PALETTE[0],
    editingFixed: null,
};

const finSettingsNav = createDrillDown({
    modal: finSettingsModal,
    menu: document.getElementById('finSettingsMenu'),
    back: document.getElementById('finSettingsBack'),
    title: document.getElementById('finSettingsTitle'),
    rootTitle: 'Ajustes',
    onPage: (name) => {
        finSettingsError.classList.add('hidden');
        finRenderSettingsPage(name);
    },
    onMenu: () => finSettingsError.classList.add('hidden'),
    onClose: () => closeFinSettings(),
});

function openFinSettings(page = null, { kind = null } = {}) {
    finSettingsError.classList.add('hidden');
    if (kind) finSettings.catKind = kind;
    showModal(finSettingsModal);
    if (page) finSettingsNav.show(page, { animate: false });
    else finSettingsNav.showMenu({ animate: false });
}

function closeFinSettings() {
    hideModal(finSettingsModal);
    finResetCategoryForm();
    finSettings.editingFixed = null;
    finLoad();   // lo cambiado aquí (nombres, fijos) se ve en la página
}

document.getElementById('finSettingsClose').addEventListener('click', closeFinSettings);
finSettingsModal.querySelector('.modal-overlay').addEventListener('click', closeFinSettings);

function finRenderSettingsPage(name) {
    if (name === 'period') finRenderPeriodPage();
    else if (name === 'categories') finRenderCategoriesPage();
    else if (name === 'fixed') finRenderFixedPage();
    else if (name === 'archived') finRenderArchivedPage();
}

// Un cambio en Ajustes: el error, si lo hay, y todo al día
async function finSettingsAction(request) {
    finSettingsError.classList.add('hidden');
    try {
        await request();
    } catch (error) {
        showError(finSettingsError, error.message);
    }
    await finLoad();
    if (finSettingsNav.current) finRenderSettingsPage(finSettingsNav.current);
}

// Un botón pequeño con icono para las filas
function finRowButton(className, label, icon) {
    const button = el('button', `fin-row-btn ${className}`);
    button.type = 'button';
    button.setAttribute('aria-label', label);
    button.title = label;
    button.appendChild(financeIcon(icon, 18));
    return button;
}

// ============================================
// Iconos y colores (cuentas y categorías)
// ============================================

function finRenderIconGrid(container, selected, color) {
    container.replaceChildren(...Object.keys(FINANCE_ICONS).map(name => {
        const button = el('button', `fin-icon-choice${name === selected ? ' selected' : ''}`);
        button.type = 'button';
        button.dataset.icon = name;
        button.setAttribute('aria-label', name);
        button.setAttribute('aria-pressed', String(name === selected));
        button.style.setProperty('--badge', color);
        button.appendChild(financeIcon(name, 20));
        return button;
    }));
}

function finRenderColorRow(container, selected) {
    container.replaceChildren(...FIN_PALETTE.map(color => {
        const button = el('button', `fin-color-choice${color === selected ? ' selected' : ''}`);
        button.type = 'button';
        button.dataset.color = color;
        button.style.background = color;
        button.setAttribute('aria-label', `Color ${color}`);
        button.setAttribute('aria-pressed', String(color === selected));
        return button;
    }));
}

// ============================================
// Periodo y sueldo
// ============================================

function finRenderPeriodPage() {
    const s = finState.summary;
    document.querySelectorAll('#finPeriodToggle [data-period]').forEach(button => {
        button.setAttribute('aria-pressed', String(Boolean(s && s.period_asked) && button.dataset.period === s.period));
    });
    const salary = finSalaryFixed();
    document.getElementById('finSalarySetting').textContent = salary ? finFixedText(salary) : 'Sin agregar';
    document.getElementById('finSalarySettingAdd').hidden = Boolean(salary);
}

async function finSavePeriod(period, errorEl) {
    try {
        await apiFetch('/api/finance/settings', { method: 'PUT', json: { period } });
        finState.range = { mode: 'period', anchor: null, from: null, to: null };   // el de hoy, con la nueva medida
        await finLoad();
        return true;
    } catch (error) {
        showError(errorEl, error.message);
        return false;
    }
}

document.getElementById('finPeriodToggle').addEventListener('click', async (event) => {
    const button = event.target.closest('[data-period]');
    if (!button) return;
    if (await finSavePeriod(button.dataset.period, finSettingsError)) finRenderPeriodPage();
});
document.getElementById('finSalarySettingAdd').addEventListener('click', () => {
    closeFinSettings();
    openFinSalary();
});

// La primera vez: cada cuándo, y luego cuánto
document.getElementById('finAsk').addEventListener('click', async (event) => {
    const button = event.target.closest('[data-period]');
    if (!button) return;
    const saved = await finSavePeriod(button.dataset.period, document.getElementById('finError'));
    if (saved && !finSalaryFixed()) openFinSalary();
});
document.getElementById('finSalaryOpen').addEventListener('click', () => openFinSalary());

// El fijo que hace de sueldo: el ingreso de la categoría Sueldo, o cualquier ingreso fijo
function finSalaryFixed() {
    const income = finState.recurring.filter(rc => rc.kind === 'income');
    const category = finState.categories.find(c => c.kind === 'income' && c.name === 'Sueldo');
    return income.find(rc => category && rc.category_id === category.id) || income[0] || null;
}

const finSalarySheet = document.getElementById('finSalarySheet');

function finSalaryBiweekly() {
    return Boolean(finState.summary && finState.summary.period === 'biweekly');
}

// La fecha que se propone: el siguiente 15 o fin de mes (quincena), o el fin de mes
function finNextPayDate(biweekly) {
    const today = finDate(finToday());
    const last = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate();
    const day = biweekly && today.getDate() <= 15 ? 15 : last;
    return getDateKey(new Date(today.getFullYear(), today.getMonth(), day));
}

function finRenderSalaryAccounts(selectedId) {
    const select = document.getElementById('finSalaryAccount');
    const accounts = finActiveAccounts();
    // El sueldo casi nunca llega en efectivo: de entrada, la primera de débito
    const preferred = selectedId || (accounts.find(a => a.kind === 'debit') || accounts.find(a => a.is_default) || accounts[0] || {}).id;
    select.replaceChildren(...accounts.map(a => {
        const option = el('option', '', a.name);
        option.value = String(a.id);
        return option;
    }));
    const fresh = el('option', '', 'Nueva cuenta de débito…');
    fresh.value = 'new';
    select.append(fresh);
    select.value = preferred ? String(preferred) : 'new';
    document.getElementById('finSalaryNewAccountField').hidden = select.value !== 'new';
}

function finRenderSalaryDays() {
    const date = document.getElementById('finSalaryDate').value;
    const text = document.getElementById('finSalaryDays');
    if (!date) {
        text.textContent = '';
        return;
    }
    if (!finSalaryBiweekly()) {
        text.textContent = `Te pagan ${finRepeatText('monthly', date)}.`;
        return;
    }
    const day = finPayDay(date);
    const other = Number(document.getElementById('finSalarySecond').value);
    if (!other) {
        text.textContent = '';
        return;
    }
    const [first, second] = [day, other].sort((a, b) => a - b);
    const shorter = second > 28 && second < 31 ? ' (o el último, si el mes es más corto)' : '';
    text.textContent = first === second ? 'Los dos pagos tienen que ser en días distintos.'
        : `Te pagan ${finDayText(first)} y ${finDayText(second)} de cada mes${shorter}.`;
}

function openFinSalary() {
    const biweekly = finSalaryBiweekly();
    document.getElementById('finSalaryError').classList.add('hidden');
    document.getElementById('finSalaryTitle').textContent = `¿Cuánto cobras ${biweekly ? 'cada quincena' : 'cada mes'}?`;
    document.getElementById('finSalaryForm').reset();
    finRenderSalaryAccounts(null);
    const date = finNextPayDate(biweekly);
    document.getElementById('finSalaryDate').value = date;
    document.getElementById('finSalarySecondField').hidden = !biweekly;
    document.getElementById('finSalarySecond').value = String(finOtherPayDay(finPayDay(date)));
    finRenderSalaryDays();
    openFinSheet(finSalarySheet);
    document.getElementById('finSalaryAmount').focus();
}

async function saveFinSalary(event) {
    event.preventDefault();
    const errorEl = document.getElementById('finSalaryError');
    errorEl.classList.add('hidden');
    const biweekly = finSalaryBiweekly();
    const cents = parseMoneyCents(document.getElementById('finSalaryAmount').value);
    const date = document.getElementById('finSalaryDate').value;
    const accountSelect = document.getElementById('finSalaryAccount');
    const newName = document.getElementById('finSalaryNewAccount').value.trim();
    if (cents == null || cents <= 0) return showError(errorEl, 'Escribe cuánto cobras: un número mayor que cero.');
    if (!date) return showError(errorEl, 'Elige en el calendario cuándo te pagan la próxima vez.');
    const fields = { frequency: biweekly ? 'semimonthly' : 'monthly' };
    if (biweekly) {
        const day = finPayDay(date);
        const other = Number(document.getElementById('finSalarySecond').value);
        if (!Number.isInteger(other) || other < 1 || other > 31) {
            return showError(errorEl, 'Escribe el día del otro pago: del 1 al 31 (31 es el último día).');
        }
        if (other === day) return showError(errorEl, 'Los dos pagos tienen que ser en días distintos.');
        Object.assign(fields, { first_day: Math.min(day, other), second_day: Math.max(day, other) });
    }
    if (accountSelect.value === 'new' && !newName) return showError(errorEl, 'Escribe el nombre de la cuenta.');
    const category = finState.categories.find(c => c.kind === 'income' && c.name === 'Sueldo') || finKindCategories('income')[0];
    if (!category) return showError(errorEl, 'Crea una categoría de ingresos en Ajustes › Categorías.');
    const save = document.getElementById('finSalarySave');
    save.disabled = true;
    try {
        let accountId = Number(accountSelect.value);
        if (accountSelect.value === 'new') {
            const account = await apiFetch('/api/finance/accounts', {
                method: 'POST', json: { name: newName, kind: 'debit', currency: finMainCurrency() },
            });
            finState.accounts.push(account);
            // Si lo siguiente falla, reintentar no crea la cuenta otra vez
            finRenderSalaryAccounts(account.id);
            accountId = account.id;
        }
        await apiFetch('/api/finance/recurring', {
            method: 'POST',
            json: { ...fields, kind: 'income', concept: 'Sueldo', amount_cents: cents, account_id: accountId,
                category_id: category.id, start_date: date },
        });
        closeFinSheet(finSalarySheet);
        await finLoad();
    } catch (error) {
        showError(errorEl, error.message);
    } finally {
        save.disabled = false;
    }
}

document.getElementById('finSalaryForm').addEventListener('submit', saveFinSalary);
document.getElementById('finSalaryLater').addEventListener('click', () => closeFinSheet(finSalarySheet));
document.getElementById('finSalaryAccount').addEventListener('change', (event) => {
    const fresh = event.target.value === 'new';
    document.getElementById('finSalaryNewAccountField').hidden = !fresh;
    if (fresh) document.getElementById('finSalaryNewAccount').focus();
});
document.getElementById('finSalaryDate').addEventListener('change', (event) => {
    if (event.target.value && finSalaryBiweekly()) {
        document.getElementById('finSalarySecond').value = String(finOtherPayDay(finPayDay(event.target.value)));
    }
    finRenderSalaryDays();
});
document.getElementById('finSalarySecond').addEventListener('input', finRenderSalaryDays);

// ============================================
// Categorías
// ============================================

function finRenderCategoriesPage() {
    document.querySelectorAll('#finCatKindToggle [data-kind]').forEach(button => {
        button.setAttribute('aria-pressed', String(button.dataset.kind === finSettings.catKind));
    });
    const list = document.getElementById('finCatList');
    list.replaceChildren(...finKindCategories(finSettings.catKind).map(c => {
        const row = el('li', 'fin-config-row');
        row.dataset.categoryId = String(c.id);
        const text = el('span', 'fin-config-text');
        text.append(el('strong', '', c.name), el('small', '', c.tx_count ? `${c.tx_count} movimientos` : 'Sin movimientos'));
        row.append(finBadge(finCategoryIcon(c), finCategoryColor(c)), text,
            finRowButton('fin-cat-edit', `Editar ${c.name}`, 'pencil'),
            finRowButton('fin-cat-delete danger', `Borrar ${c.name}`, 'x'));
        return row;
    }));
    if (!finSettings.editingCategory) finResetCategoryForm();
}

function finResetCategoryForm() {
    finSettings.editingCategory = null;
    finSettings.catIcon = 'ellipsis';
    finSettings.catColor = FIN_PALETTE[(finKindCategories(finSettings.catKind).length * 3) % FIN_PALETTE.length];
    document.getElementById('finCatName').value = '';
    document.getElementById('finCatFormTitle').textContent = finSettings.catKind === 'income' ? 'Nueva categoría de ingresos' : 'Nueva categoría de gastos';
    document.getElementById('finCatSave').textContent = 'Agregar';
    document.getElementById('finCatCancel').hidden = true;
    finRenderCategoryPickers();
}

function finRenderCategoryPickers() {
    finRenderIconGrid(document.getElementById('finCatIcons'), finSettings.catIcon, finSettings.catColor);
    finRenderColorRow(document.getElementById('finCatColors'), finSettings.catColor);
}

document.getElementById('finCatKindToggle').addEventListener('click', (event) => {
    const button = event.target.closest('[data-kind]');
    if (!button) return;
    finSettings.catKind = button.dataset.kind;
    finSettings.editingCategory = null;
    finRenderCategoriesPage();
});
document.getElementById('finCatIcons').addEventListener('click', (event) => {
    const button = event.target.closest('[data-icon]');
    if (!button) return;
    finSettings.catIcon = button.dataset.icon;
    finRenderCategoryPickers();
});
document.getElementById('finCatColors').addEventListener('click', (event) => {
    const button = event.target.closest('[data-color]');
    if (!button) return;
    finSettings.catColor = button.dataset.color;
    finRenderCategoryPickers();
});
document.getElementById('finCatCancel').addEventListener('click', finResetCategoryForm);
document.getElementById('finCatList').addEventListener('click', async (event) => {
    const row = event.target.closest('[data-category-id]');
    if (!row) return;
    const category = finCategory(Number(row.dataset.categoryId));
    if (!category) return;
    if (event.target.closest('.fin-cat-edit')) {
        Object.assign(finSettings, {
            editingCategory: category, catIcon: finCategoryIcon(category), catColor: finCategoryColor(category),
        });
        document.getElementById('finCatName').value = category.name;
        document.getElementById('finCatFormTitle').textContent = `Editar "${category.name}"`;
        document.getElementById('finCatSave').textContent = 'Guardar';
        document.getElementById('finCatCancel').hidden = false;
        finRenderCategoryPickers();
        document.getElementById('finCatName').focus();
    } else if (event.target.closest('.fin-cat-delete')) {
        const ok = await confirmDialog(`¿Borrar la categoría "${category.name}"?`, { confirmLabel: 'Borrar', danger: true });
        if (ok) finSettingsAction(() => apiFetch(`/api/finance/categories/${category.id}`, { method: 'DELETE' }));
    }
});
document.getElementById('finCatForm').addEventListener('submit', (event) => {
    event.preventDefault();
    const name = document.getElementById('finCatName').value.trim();
    if (!name) {
        showError(finSettingsError, 'Escribe el nombre de la categoría.');
        return;
    }
    const editing = finSettings.editingCategory;
    const fields = { name, icon: finSettings.catIcon, color: finSettings.catColor };
    finSettingsAction(async () => {
        if (editing) {
            await apiFetch(`/api/finance/categories/${editing.id}`, { method: 'PATCH', json: fields });
        } else {
            await apiFetch('/api/finance/categories', { method: 'POST', json: { ...fields, kind: finSettings.catKind } });
        }
        finSettings.editingCategory = null;
    });
});

// ============================================
// Fijos
// ============================================

const FIN_FREQUENCY_LABELS = { monthly: 'cada mes', semimonthly: 'cada quincena', yearly: 'cada año' };

function finFixedText(rc) {
    const account = finAccount(rc.account_id);
    const days = rc.frequency === 'semimonthly' && rc.first_day
        ? ` (${finDayText(rc.first_day)} y ${finDayText(rc.second_day)})` : '';
    const parts = [`${formatMoney(rc.amount_cents, rc.currency)} ${FIN_FREQUENCY_LABELS[rc.frequency]}${days}`];
    if (account) parts.push(account.name);
    if (rc.paused) parts.push('en pausa');
    else if (rc.next_date) parts.push(`siguiente: ${finShortDate(rc.next_date)}`);
    else parts.push('terminado');
    return parts.join(' · ');
}

function finRenderFixedPage() {
    const list = document.getElementById('finFixedList');
    if (!finState.recurring.length) {
        list.replaceChildren(el('li', 'fin-empty', 'Todavía no tienes fijos.'));
    } else {
        list.replaceChildren(...finState.recurring.map(rc => {
            const row = el('li', `fin-config-row${rc.paused ? ' paused' : ''}`);
            row.dataset.fixedId = String(rc.id);
            const category = finCategory(rc.category_id);
            const text = el('span', 'fin-config-text');
            text.append(el('strong', '', `${rc.kind === 'income' ? '＋ ' : ''}${rc.concept}`), el('small', '', finFixedText(rc)));
            row.append(category ? finBadge(finCategoryIcon(category), finCategoryColor(category)) : finBadge('repeat', FIN_NEUTRAL),
                text,
                finRowButton('fin-fixed-edit', `Editar ${rc.concept}`, 'pencil'),
                el('button', 'fin-row-btn fin-fixed-pause', rc.paused ? '▶' : '⏸'),
                finRowButton('fin-fixed-delete danger', `Eliminar ${rc.concept}`, 'x'));
            const pause = row.querySelector('.fin-fixed-pause');
            pause.type = 'button';
            pause.setAttribute('aria-label', rc.paused ? `Reanudar ${rc.concept}` : `Pausar ${rc.concept}`);
            return row;
        }));
    }
    const form = document.getElementById('finFixedForm');
    form.hidden = !finSettings.editingFixed;
}

function finFillOptions(select, items, selectedId) {
    select.replaceChildren(...items.map(item => {
        const option = el('option', '', item.name);
        option.value = String(item.id);
        return option;
    }));
    if (selectedId) select.value = String(selectedId);
}

function finSyncFixedDays() {
    document.getElementById('finFixedDaysField').hidden = document.getElementById('finFixedFrequency').value !== 'semimonthly';
}

function editFinFixed(rc) {
    finSettings.editingFixed = rc;
    document.getElementById('finFixedFormTitle').textContent = `Editar "${rc.concept}"`;
    document.getElementById('finFixedConcept').value = rc.concept;
    document.getElementById('finFixedAmount').value = (rc.amount_cents / 100).toFixed(2);
    document.getElementById('finFixedFrequency').value = rc.frequency;
    document.getElementById('finFixedFirstDay').value = String(rc.first_day || 15);
    document.getElementById('finFixedSecondDay').value = String(rc.second_day || 31);
    finSyncFixedDays();
    finFillOptions(document.getElementById('finFixedAccount'),
        finState.accounts.filter(a => a.is_active || a.id === rc.account_id), rc.account_id);
    finFillOptions(document.getElementById('finFixedCategory'), finKindCategories(rc.kind), rc.category_id);
    document.getElementById('finFixedNext').value = (rc.generated ? rc.next_date : rc.start_date) || rc.start_date;
    document.getElementById('finFixedForm').hidden = false;
    document.getElementById('finFixedConcept').focus();
}

document.getElementById('finFixedFrequency').addEventListener('change', finSyncFixedDays);
document.getElementById('finFixedCancel').addEventListener('click', () => {
    finSettings.editingFixed = null;
    document.getElementById('finFixedForm').hidden = true;
});
document.getElementById('finFixedList').addEventListener('click', async (event) => {
    const row = event.target.closest('[data-fixed-id]');
    const button = event.target.closest('button');
    if (!row || !button) return;
    const rc = finState.recurring.find(r => r.id === Number(row.dataset.fixedId));
    if (!rc) return;
    const url = `/api/finance/recurring/${rc.id}`;
    if (button.classList.contains('fin-fixed-edit')) {
        editFinFixed(rc);
    } else if (button.classList.contains('fin-fixed-pause')) {
        finSettingsAction(() => apiFetch(url, { method: 'PATCH', json: { paused: !rc.paused } }));
    } else if (button.classList.contains('fin-fixed-delete')) {
        const ok = await confirmDialog(`¿Dejar de anotar "${rc.concept}"? Lo que ya anotó se queda.`,
            { confirmLabel: 'Eliminar', danger: true });
        if (!ok) return;
        if (finSettings.editingFixed && finSettings.editingFixed.id === rc.id) finSettings.editingFixed = null;
        finSettingsAction(() => apiFetch(url, { method: 'DELETE' }));
    }
});
document.getElementById('finFixedForm').addEventListener('submit', (event) => {
    event.preventDefault();
    const rc = finSettings.editingFixed;
    if (!rc) return;
    const cents = parseMoneyCents(document.getElementById('finFixedAmount').value);
    const concept = document.getElementById('finFixedConcept').value.trim();
    const next = document.getElementById('finFixedNext').value;
    if (cents == null || cents <= 0) return showError(finSettingsError, 'Escribe el monto: un número mayor que cero.');
    if (!concept || !next) return showError(finSettingsError, 'Escribe el concepto y la fecha del siguiente cobro.');
    const fields = {
        concept, amount_cents: cents, frequency: document.getElementById('finFixedFrequency').value,
        account_id: Number(document.getElementById('finFixedAccount').value),
        category_id: Number(document.getElementById('finFixedCategory').value),
    };
    if (fields.frequency === 'semimonthly') {
        const days = ['finFixedFirstDay', 'finFixedSecondDay'].map(id => Number(document.getElementById(id).value));
        if (days.some(d => !Number.isInteger(d) || d < 1 || d > 31)) {
            return showError(finSettingsError, 'Los días de pago van del 1 al 31 (31 es el último día).');
        }
        [fields.first_day, fields.second_day] = days;
    }
    const shown = (rc.generated ? rc.next_date : rc.start_date) || rc.start_date;
    // La fecha solo viaja si cambió: con cobros anotados, mandarla vuelve a anclar la serie
    if (next !== shown || fields.frequency !== rc.frequency) fields.start_date = next;
    finSettingsAction(async () => {
        await apiFetch(`/api/finance/recurring/${rc.id}`, { method: 'PATCH', json: fields });
        finSettings.editingFixed = null;
    });
});

// ============================================
// Cuentas archivadas
// ============================================

function finRenderArchivedPage() {
    const archived = finState.accounts.filter(a => !a.is_active);
    const list = document.getElementById('finArchivedList');
    if (!archived.length) {
        list.replaceChildren(el('li', 'fin-empty', 'No tienes cuentas archivadas.'));
        return;
    }
    list.replaceChildren(...archived.map(a => {
        const row = el('li', 'fin-config-row');
        row.dataset.accountId = String(a.id);
        const text = el('span', 'fin-config-text');
        text.append(el('strong', '', a.name), el('small', '', `${a.tx_count} movimientos · ${formatMoney(a.balance_cents, a.currency)}`));
        const restore = el('button', 'link-btn fin-restore', 'Reactivar');
        restore.type = 'button';
        row.append(finBadge(finAccountIcon(a), finAccountColor(a), { square: true }), text, restore);
        return row;
    }));
}

document.getElementById('finArchivedList').addEventListener('click', (event) => {
    const row = event.target.closest('[data-account-id]');
    if (row && event.target.closest('.fin-restore')) {
        finSettingsAction(() => apiFetch(`/api/finance/accounts/${row.dataset.accountId}`,
            { method: 'PATCH', json: { is_active: true } }));
    }
});

// ============================================
// Una cuenta (su hoja)
// ============================================

const finAccountSheet = document.getElementById('finAccountSheet');
const finAccountForm = { account: null, icon: 'wallet', color: FIN_PALETTE[3] };

function finSyncAccountKind() {
    const kind = document.getElementById('finAccKind').value;
    const credit = kind === 'credit';
    finAccountSheet.querySelectorAll('.credit-only').forEach(field => { field.hidden = !credit; });
    document.getElementById('finAccOpeningLabel').textContent = credit ? 'Deuda total' : 'Saldo';
    document.getElementById('finAccHint').textContent = credit
        ? 'La deuda de ese día, completa. Si parte está a meses sin intereses, agrégala después en la tarjeta › '
          + 'Meses sin intereses: el pago solo pedirá la mensualidad. Los movimientos de antes de ese día son '
          + 'historial: salen en el resumen, pero no cambian la deuda.'
        : 'El saldo es el de ese día más lo que entra y sale desde entonces. Los movimientos de antes son '
          + 'historial: salen en el resumen, pero no cambian el saldo.';
}

function finRenderAccountPickers() {
    finRenderIconGrid(document.getElementById('finAccIcons'), finAccountForm.icon, finAccountForm.color);
    finRenderColorRow(document.getElementById('finAccColors'), finAccountForm.color);
}

function openFinAccount(account, kind = 'debit') {
    finAccountForm.account = account;
    const k = account ? account.kind : kind;
    finAccountForm.icon = account ? finAccountIcon(account) : FIN_KIND_ICONS[k];
    finAccountForm.color = account ? finAccountColor(account) : FIN_PALETTE[(finState.accounts.length * 4 + 3) % FIN_PALETTE.length];
    document.getElementById('finAccountTitle').textContent = account ? account.name : (k === 'credit' ? 'Nueva tarjeta' : 'Nueva cuenta');
    document.getElementById('finAccName').value = account ? account.name : '';
    document.getElementById('finAccKind').value = k;
    const currency = document.getElementById('finAccCurrency');
    currency.replaceChildren(...CURRENCIES.map(c => {
        const option = el('option', '', c);
        option.value = c;
        return option;
    }));
    currency.value = account ? account.currency : finMainCurrency();
    // En una de crédito se escribe lo que se debía (positivo); se guarda negativo
    const opening = account ? account.opening_balance_cents : 0;
    document.getElementById('finAccOpening').value = opening ? (Math.abs(opening) / 100).toFixed(2) : '';
    // El día de ese saldo: el guardado, o hoy en una nueva
    document.getElementById('finAccOpeningDate').value = account ? (account.opening_date || '') : finToday();
    document.getElementById('finAccOpeningDate').max = finToday();
    document.getElementById('finAccLast4').value = account && account.last4 ? account.last4 : '';
    document.getElementById('finAccLimit').value = account && account.credit_limit_cents != null
        ? (account.credit_limit_cents / 100).toFixed(2) : '';
    document.getElementById('finAccStatement').value = account && account.statement_day ? String(account.statement_day) : '';
    document.getElementById('finAccDue').value = account && account.due_day ? String(account.due_day) : '';
    document.getElementById('finAccArchive').hidden = !account;
    document.getElementById('finAccArchive').textContent = 'Archivar';
    document.getElementById('finAccError').classList.add('hidden');
    finSyncAccountKind();
    finRenderAccountPickers();
    openFinSheet(finAccountSheet);
}

function finOptionalCents(id) {
    const text = document.getElementById(id).value.trim();
    if (!text) return null;
    const cents = parseMoneyCents(text);
    return cents == null ? NaN : Math.abs(cents);
}

function finOptionalDay(id) {
    const text = document.getElementById(id).value.trim();
    if (!text) return null;
    const day = Number(text);
    return Number.isInteger(day) && day >= 1 && day <= 31 ? day : NaN;
}

document.getElementById('finAccKind').addEventListener('change', finSyncAccountKind);
document.getElementById('finAccIcons').addEventListener('click', (event) => {
    const button = event.target.closest('[data-icon]');
    if (!button) return;
    finAccountForm.icon = button.dataset.icon;
    finRenderAccountPickers();
});
document.getElementById('finAccColors').addEventListener('click', (event) => {
    const button = event.target.closest('[data-color]');
    if (!button) return;
    finAccountForm.color = button.dataset.color;
    finRenderAccountPickers();
});
document.getElementById('finAccCancel').addEventListener('click', () => closeFinSheet(finAccountSheet));
document.getElementById('finAccArchive').addEventListener('click', async () => {
    const account = finAccountForm.account;
    if (!account) return;
    const ok = await confirmDialog(`¿Archivar "${account.name}"? Sus movimientos se quedan; la reactivas en Ajustes.`,
        { confirmLabel: 'Archivar' });
    if (!ok) return;
    try {
        await apiFetch(`/api/finance/accounts/${account.id}`, { method: 'PATCH', json: { is_active: false } });
        closeFinSheet(finAccountSheet);
        await finLoad();
    } catch (error) {
        showError(document.getElementById('finAccError'), error.message);
    }
});
document.getElementById('finAccountForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const errorEl = document.getElementById('finAccError');
    errorEl.classList.add('hidden');
    const name = document.getElementById('finAccName').value.trim();
    const kind = document.getElementById('finAccKind').value;
    const credit = kind === 'credit';
    const opening = finOptionalCents('finAccOpening');
    const limit = credit ? finOptionalCents('finAccLimit') : null;
    const statement = credit ? finOptionalDay('finAccStatement') : null;
    const due = credit ? finOptionalDay('finAccDue') : null;
    const last4 = document.getElementById('finAccLast4').value.trim();
    const openingDate = document.getElementById('finAccOpeningDate').value || null;
    if (!name) return showError(errorEl, 'Escribe el nombre de la cuenta.');
    if (openingDate && openingDate > finToday()) return showError(errorEl, 'El día del saldo no puede ser futuro.');
    if (Number.isNaN(opening) || Number.isNaN(limit)) return showError(errorEl, 'Revisa los montos: solo números.');
    if (Number.isNaN(statement) || Number.isNaN(due)) return showError(errorEl, 'Los días van del 1 al 31.');
    if (last4 && !/^\d{4}$/.test(last4)) return showError(errorEl, 'Los últimos 4 dígitos: exactamente 4 números.');
    const fields = {
        name, kind, currency: document.getElementById('finAccCurrency').value,
        icon: finAccountForm.icon, color: finAccountForm.color, last4: last4 || null,
        opening_balance_cents: credit ? -(opening || 0) : (opening || 0),
        // Sin día y con saldo, hoy; vacío en una que ya existe: cuentan todos sus movimientos
        opening_date: openingDate || (!finAccountForm.account && opening ? finToday() : null),
        credit_limit_cents: limit, statement_day: statement, due_day: due,
    };
    const save = document.getElementById('finAccSave');
    save.disabled = true;
    try {
        const account = finAccountForm.account;
        if (account) {
            // La moneda solo cambia sin movimientos: no se manda si es la misma
            if (fields.currency === account.currency) delete fields.currency;
            await apiFetch(`/api/finance/accounts/${account.id}`, { method: 'PATCH', json: fields });
        } else {
            await apiFetch('/api/finance/accounts', { method: 'POST', json: fields });
        }
        closeFinSheet(finAccountSheet);
        await finLoad();
    } catch (error) {
        showError(errorEl, error.message);
    } finally {
        save.disabled = false;
    }
});
