// ============================================
// Finanzas: préstamos (Finanzas 0.9, BACKLOG 52)
// ============================================
//
// Las páginas del menú de un préstamo (finance-accounts.js): lo pagado a capital y
// a intereses con sus pagos y su tabla (finLoanPage), pagar la mensualidad o abonar
// a capital (finLoanPayPage) y subir la tabla de amortización (finLoanTablePage).
// Cada pago es un solo movimiento: una transferencia al préstamo con sus intereses
// dentro (interest_cents); la deuda baja solo el capital y los intereses son gasto.

const finLoan = { data: null, capital: false, rows: null };

function finLoanAccount() {
    return finAccount(finMenu.account.id) || finMenu.account;
}

async function finLoanFetch() {
    const a = finLoanAccount();
    finLoan.data = await apiFetch(`/api/finance/accounts/${a.id}/loan`);
    return finLoan.data;
}

// ---------- Su página: lo pagado, los pagos y la tabla ----------

async function openFinLoan() {
    finMenuPage('loan');
    document.getElementById('finLoanSummary').replaceChildren(el('p', 'fin-hint', 'Cargando…'));
    document.getElementById('finLoanLists').replaceChildren();
    try {
        await finLoanFetch();
    } catch (error) {
        document.getElementById('finLoanSummary').replaceChildren(el('p', 'form-error', error.message));
        return;
    }
    finRenderLoan();
}

function finLoanStat(label, value, detail) {
    const box = el('div', 'fin-stat');
    box.append(el('span', 'fin-stat-label', label), el('strong', 'fin-stat-value', value));
    if (detail) box.appendChild(el('small', 'fin-loan-stat-detail', detail));
    return box;
}

function finRenderLoan() {
    const d = finLoan.data;
    const a = finLoanAccount();
    const money = cents => formatMoney(cents, d.currency);
    const tiles = el('div', 'fin-tiles');
    tiles.append(
        finLoanStat('Debes', money(Math.max(0, d.owed_cents)),
            d.ends_on ? `${d.from_table || d.rows.length ? 'Terminas' : 'Terminarías'} en ${finMonthYear(d.ends_on)}` : ''),
        finLoanStat('Has pagado', money(d.paid_cents),
            `${money(d.paid_principal_cents)} a capital · ${money(d.paid_interest_cents)} de intereses`),
    );
    const facts = [];
    facts.push(`${d.regular_count === 1 ? '1 mensualidad' : `${d.regular_count} mensualidades`}`
        + (d.capital_count ? ` y ${d.capital_count === 1 ? '1 abono' : `${d.capital_count} abonos`} a capital` : ''));
    if (d.next_payment_cents) {
        const what = d.next_number ? `Pago ${d.next_number}` : 'Siguiente pago';
        facts.push(`${what}: ${money(d.next_payment_cents)}${d.next_due ? ` el ${finShortDate(d.next_due)}` : ''}`
            + (d.next_interest_cents != null ? `, ${money(d.next_interest_cents)} de intereses` : ''));
    }
    if (a.interest_rate_bp != null) facts.push(`Tasa ${finRateText(a.interest_rate_bp)} anual`);
    document.getElementById('finLoanSummary').replaceChildren(tiles, el('p', 'fin-hint fin-loan-facts', facts.join(' · ')));

    // Los pagos, del más reciente al más viejo
    const lists = [];
    const payments = el('section', 'fin-loan-list');
    payments.appendChild(el('h3', 'fin-loan-list-title', 'Pagos'));
    if (!d.payments.length) payments.appendChild(el('p', 'fin-empty', 'Aún no hay pagos.'));
    d.payments.forEach(p => {
        const row = el('div', 'fin-loan-row');
        const text = el('span', 'fin-debt-text');
        const from = finAccount(p.account_id);
        text.append(el('strong', '', finShortDate(p.tx_date)),
            el('small', '', [p.principal_only ? 'Abono a capital'
                : `${money(p.principal_cents)} a capital · ${money(p.interest_cents)} de intereses`,
            from ? from.name : ''].filter(Boolean).join(' · ')));
        row.append(text, el('span', 'fin-debt-amount', money(p.amount_cents)));
        payments.appendChild(row);
    });
    lists.push(payments);
    if (d.rows.length) {
        const table = el('section', 'fin-loan-list');
        table.appendChild(el('h3', 'fin-loan-list-title', 'Tabla de amortización'));
        table.appendChild(finLoanTableEl(d.rows, d.currency, true));
        lists.push(table);
    }
    document.getElementById('finLoanLists').replaceChildren(...lists);
}

// La tabla (la guardada o la vista previa): número, fecha, pago, capital, intereses y saldo
function finLoanTableEl(rows, currency, marks) {
    const money = cents => (cents == null ? '' : formatMoney(cents, currency));
    const wrap = el('div', 'fin-loan-table-wrap');
    const table = el('table', 'fin-loan-table');
    const head = el('tr');
    ['No.', 'Fecha', 'Pago', 'Capital', 'Intereses', 'Saldo'].forEach(h => head.appendChild(el('th', '', h)));
    table.appendChild(head);
    rows.forEach(r => {
        const tr = el('tr', marks && r.paid ? 'paid' : '');
        [`${marks && r.paid ? '✓ ' : ''}${r.number}`, finShortDate(r.due_date), money(r.payment_cents),
            money(r.principal_cents), money(r.interest_cents), money(r.balance_cents)]
            .forEach(v => tr.appendChild(el('td', '', v)));
        table.appendChild(tr);
    });
    wrap.appendChild(table);
    return wrap;
}

document.getElementById('finLoanPage').addEventListener('click', (event) => {
    const pay = event.target.closest('[data-loan-pay]');
    if (pay) openFinLoanPay(pay.dataset.loanPay === 'capital');
    if (event.target.closest('[data-loan-table]')) openFinLoanTable();
});

// Regresar de pagar o de la tabla: a la página del préstamo si de ahí se vino; si no, al menú
document.getElementById('finAccountMenu').addEventListener('click', (event) => {
    if (!event.target.closest('[data-loan-back]')) return;
    if (finLoan.from === 'loan') openFinLoan();
    else finMenuPage(null);
});

// ---------- Pagar: la mensualidad o un abono a capital ----------

async function openFinLoanPay(capital) {
    finLoan.from = document.getElementById('finLoanPage').hidden ? 'menu' : 'loan';
    finLoan.capital = capital;
    const a = finLoanAccount();
    finMenuPage('loanpay');
    const from = document.getElementById('finLoanPayFrom');
    from.replaceChildren(...finActiveAccounts().filter(x => x.kind !== 'loan' && x.currency === a.currency).map(x => {
        const option = el('option', '', x.name);
        option.value = String(x.id);
        return option;
    }));
    const usual = finActiveAccounts().find(x => x.is_default && x.currency === a.currency);
    if (usual) from.value = String(usual.id);
    document.getElementById('finLoanPayDate').value = finToday();
    document.getElementById('finLoanPayDate').max = finToday();
    document.getElementById('finLoanPayAmountLabel').textContent = capital ? 'Abono' : 'Pago';
    document.getElementById('finLoanPayInterestField').hidden = capital;
    document.getElementById('finLoanPayAmount').value = '';
    document.getElementById('finLoanPayInterest').value = '';
    document.getElementById('finCapitalNoteHide').checked = false;
    document.getElementById('finLoanPayError').classList.add('hidden');
    document.getElementById('finLoanPayHint').textContent = capital
        ? 'Un abono a capital va completo a la deuda: no lleva intereses ni cuenta como una mensualidad.' : '';
    document.getElementById('finCapitalNote').hidden = true;
    finLoanPaySplit();
    let d = finLoan.data;
    try {
        d = await finLoanFetch();
    } catch (error) {
        if (!d) return;
    }
    document.getElementById('finCapitalNote').hidden = !capital || d.capital_note_hidden;
    if (capital) return;
    // La mensualidad que sigue: de la tabla, o la del préstamo con los intereses estimados con la tasa
    if (d.next_payment_cents) document.getElementById('finLoanPayAmount').value = (d.next_payment_cents / 100).toFixed(2);
    if (d.next_interest_cents != null) document.getElementById('finLoanPayInterest').value = (d.next_interest_cents / 100).toFixed(2);
    document.getElementById('finLoanPayHint').textContent = d.from_table
        ? `Pago ${d.next_number} de tu tabla${d.next_due ? `, del ${finShortDate(d.next_due)}` : ''}. Si tu estado de cuenta dice otra cosa, corrígelo.`
        : d.next_interest_cents != null
            ? `Intereses estimados con tu tasa de ${finRateText(a.interest_rate_bp)} anual sobre lo que debes: corrígelos con tu estado de cuenta (con IVA y seguros, si los cobra).`
            : 'Escribe cuánto del pago fue de intereses y cargos (IVA, seguros); el resto baja la deuda.';
    finLoanPaySplit();
}

function finLoanPayCents(id) {
    const text = document.getElementById(id).value.trim();
    if (!text) return 0;
    const cents = parseMoneyCents(text);
    return cents == null ? NaN : Math.abs(cents);
}

// "A capital $X · Intereses y cargos $Y", mientras se escribe
function finLoanPaySplit() {
    const a = finLoanAccount();
    const amount = finLoanPayCents('finLoanPayAmount');
    const interest = finLoan.capital ? 0 : finLoanPayCents('finLoanPayInterest');
    const line = document.getElementById('finLoanPaySplit');
    if (!amount || Number.isNaN(amount) || Number.isNaN(interest)) {
        line.textContent = '';
        return;
    }
    line.textContent = interest > amount ? 'Los intereses no pueden ser más que el pago.'
        : `A capital ${formatMoney(amount - interest, a.currency)}`
          + (interest ? ` · Intereses y cargos ${formatMoney(interest, a.currency)} (gasto en Intereses)` : '');
}

document.getElementById('finLoanPayAmount').addEventListener('input', finLoanPaySplit);
document.getElementById('finLoanPayInterest').addEventListener('input', finLoanPaySplit);

document.getElementById('finLoanPayForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const a = finLoanAccount();
    const errorEl = document.getElementById('finLoanPayError');
    errorEl.classList.add('hidden');
    const amount = finLoanPayCents('finLoanPayAmount');
    const interest = finLoan.capital ? 0 : finLoanPayCents('finLoanPayInterest');
    const date = document.getElementById('finLoanPayDate').value;
    const from = Number(document.getElementById('finLoanPayFrom').value);
    if (!from) return showError(errorEl, 'Elige desde qué cuenta pagaste.');
    if (!amount || Number.isNaN(amount) || Number.isNaN(interest)) return showError(errorEl, 'Escribe el monto: solo números.');
    if (interest > amount) return showError(errorEl, 'Los intereses no pueden ser más que el pago.');
    if (!date || date > finToday()) return showError(errorEl, 'La fecha no puede ser futura.');
    const save = document.getElementById('finLoanPaySave');
    save.disabled = true;
    try {
        await apiFetch('/api/finance/transactions', {
            method: 'POST', json: {
                kind: 'transfer', account_id: from, to_account_id: a.id, amount_cents: amount, tx_date: date,
                concept: finLoan.capital ? `Abono a capital ${a.name}` : `Pago ${a.name}`,
                interest_cents: interest || null, principal_only: finLoan.capital,
            },
        });
        if (finLoan.capital && document.getElementById('finCapitalNoteHide').checked) {
            await apiFetch('/api/finance/capital-note', { method: 'PUT', json: { hidden: true } });
        }
        await finLoad();
        finMenu.account = finLoanAccount();
        finRenderAccountMenu();
        await openFinLoan();
    } catch (error) {
        showError(errorEl, error.message);
    } finally {
        save.disabled = false;
    }
});

// ---------- La tabla de amortización: pegarla o subir un CSV ----------

const FIN_MONTH_WORDS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

// Además de lo que lee parseDate: "05/ene/2026", "5-ENE-26", "05 ene 2026"
function finLoanDate(text) {
    const s = String(text).trim();
    const m = normalize(s).match(/^(\d{1,2})[\s/.-]+([a-z]{3})[a-z]*\.?[\s/.-]+(\d{2,4})$/);
    if (m) {
        const month = FIN_MONTH_WORDS.indexOf(m[2] === 'set' ? 'sep' : m[2]);
        if (month >= 0) {
            const year = m[3].length === 2 ? `20${m[3]}` : m[3];
            return `${year}-${String(month + 1).padStart(2, '0')}-${m[1].padStart(2, '0')}`;
        }
    }
    return s ? parseDate(s) : null;
}

// Qué columna es cada cosa, por su nombre
function finLoanColumn(header) {
    const h = normalize(header).replace(/[.:#°º]/g, ' ').replace(/\s+/g, ' ').trim();
    if (!h) return null;
    if (/^(no|num|numero|n|pago no|no pago|periodo|mes)$/.test(h) || h.startsWith('numero')) return 'number';
    if (h.includes('fecha') || h.includes('vencimiento')) return 'date';
    if (h.includes('saldo')) return 'balance';
    if (h.includes('capital') || h.includes('amortizacion') || h.includes('abono')) return 'principal';
    if (h.includes('interes')) return 'interest';
    if (h.includes('iva') || h.includes('seguro') || h.includes('comision') || h.includes('cargo')) return 'extra';
    if (h.includes('pago') || h.includes('mensualidad') || h.includes('cuota') || h.includes('total')) return 'payment';
    return null;
}

// Las filas de la tabla pegada: { rows, skipped } o { error }
function finLoanParseTable(text) {
    const cells = parseTable(text);
    const headerAt = cells.findIndex(r => r.filter(c => finLoanColumn(c)).length >= 3);
    if (headerAt < 0) {
        return { error: 'No encontré los nombres de las columnas: copia también la fila de arriba (Fecha, Pago, Capital, Interés…).' };
    }
    const columns = cells[headerAt].map(finLoanColumn);
    if (!columns.includes('date') || (!columns.includes('principal') && !columns.includes('payment'))) {
        return { error: 'La tabla necesita al menos la fecha y el capital o el pago de cada mes.' };
    }
    const rows = [];
    let skipped = 0;
    cells.slice(headerAt + 1).forEach(r => {
        const pick = kind => columns.map((c, i) => (c === kind ? r[i] : undefined)).filter(v => v !== undefined && String(v).trim() !== '');
        const money = kind => {
            const values = pick(kind).map(parseMoneyCents).filter(v => v != null);
            return values.length ? values.reduce((acc, v) => acc + Math.abs(v), 0) : null;
        };
        const date = pick('date').map(finLoanDate).find(Boolean);
        let payment = money('payment');
        let principal = money('principal');
        const interest = (money('interest') || 0) + (money('extra') || 0);
        if (!date || (payment == null && principal == null)) {
            skipped += 1;   // un total o una fila sin fecha
            return;
        }
        if (payment == null) payment = principal + interest;
        if (principal == null) principal = Math.max(0, payment - interest);
        // Un "pago" menor que el capital no era el total: el total es capital más lo demás
        if (principal > payment) payment = principal + interest;
        const numberText = pick('number')[0];
        const number = numberText && /^\d+$/.test(String(numberText).trim()) ? Number(numberText) : rows.length + 1;
        // Todo lo que no es capital (intereses, IVA, seguros, comisiones): el pago menos el capital
        rows.push({ number, due_date: date, payment_cents: payment, principal_cents: principal,
            interest_cents: payment - principal, balance_cents: money('balance') });
    });
    if (!rows.length) return { error: 'No encontré filas con fecha y montos debajo de los nombres de las columnas.' };
    return { rows, skipped };
}

function openFinLoanTable() {
    finLoan.from = document.getElementById('finLoanPage').hidden ? 'menu' : 'loan';
    finLoan.rows = null;
    finMenuPage('table');
    document.getElementById('finLoanTableText').value = '';
    document.getElementById('finLoanTablePreview').replaceChildren();
    document.getElementById('finLoanTableError').classList.add('hidden');
    document.getElementById('finLoanTableSave').disabled = true;
    document.getElementById('finLoanTableClear').hidden = true;
    finLoanFetch().then(d => { document.getElementById('finLoanTableClear').hidden = !d.rows.length; }).catch(() => {});
}

function finLoanPreview(text) {
    const a = finLoanAccount();
    const preview = document.getElementById('finLoanTablePreview');
    const errorEl = document.getElementById('finLoanTableError');
    errorEl.classList.add('hidden');
    finLoan.rows = null;
    document.getElementById('finLoanTableSave').disabled = true;
    if (!text.trim()) {
        preview.replaceChildren();
        return;
    }
    const parsed = finLoanParseTable(text);
    if (parsed.error) {
        preview.replaceChildren();
        showError(errorEl, parsed.error);
        return;
    }
    finLoan.rows = parsed.rows;
    const interest = parsed.rows.reduce((acc, r) => acc + r.interest_cents, 0);
    const last = parsed.rows[parsed.rows.length - 1];
    const summary = [`${parsed.rows.length} pagos, del ${finShortDate(parsed.rows[0].due_date)} al ${finShortDate(last.due_date)}`,
        `${formatMoney(interest, a.currency)} de intereses y cargos en total`];
    if (parsed.skipped) summary.push(`${parsed.skipped === 1 ? '1 fila' : `${parsed.skipped} filas`} sin fecha o montos se saltaron`);
    preview.replaceChildren(el('p', 'fin-hint', summary.join(' · ')), finLoanTableEl(parsed.rows, a.currency, false));
    document.getElementById('finLoanTableSave').disabled = false;
}

document.getElementById('finLoanTableText').addEventListener('input', (event) => finLoanPreview(event.target.value));
document.getElementById('finLoanTableFile').addEventListener('change', async (event) => {
    const file = event.target.files[0];
    event.target.value = '';
    if (!file) return;
    const text = await file.text();
    document.getElementById('finLoanTableText').value = text;
    finLoanPreview(text);
});

async function finLoanSaveTable(rows) {
    const a = finLoanAccount();
    const errorEl = document.getElementById('finLoanTableError');
    const save = document.getElementById('finLoanTableSave');
    save.disabled = true;
    try {
        finLoan.data = await apiFetch(`/api/finance/accounts/${a.id}/loan-schedule`, { method: 'PUT', json: { rows } });
        finMenuPage('loan');
        finRenderLoan();
    } catch (error) {
        showError(errorEl, error.message);
        save.disabled = false;
    }
}

document.getElementById('finLoanTableSave').addEventListener('click', () => {
    if (finLoan.rows) finLoanSaveTable(finLoan.rows);
});
document.getElementById('finLoanTableClear').addEventListener('click', async () => {
    const ok = await confirmDialog('¿Quitar la tabla de amortización? Tus pagos no cambian.', { confirmLabel: 'Quitar' });
    if (ok) finLoanSaveTable([]);
});
