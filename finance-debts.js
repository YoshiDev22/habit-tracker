// ============================================
// Finanzas: Deudas (Finanzas 0.9, BACKLOG 52)
// ============================================
//
// Lo que se paga de deudas, aparte de los gastos. Una compra con tarjeta (o a
// meses) ya contó como gasto el día que se hizo, y su pago es una transferencia:
// aquí se ve lo pagado y lo que piden los cortes, sin sumarlo nunca a los gastos.
// Todo sale de lo que finLoad() ya trae (movimientos del periodo, cuentas y planes
// de MSI): no hay API propia.

// Por cuenta y moneda: { account, currency, cents, count, interest }
function finDebtGroup(map, account, currency, cents, interest = 0, charges = 0) {
    const key = `${account.id}:${currency}`;
    const row = map.get(key) || { account, currency, cents: 0, count: 0, interest: 0, charges: 0 };
    row.cents += cents;
    row.count += 1;
    row.interest += interest;
    row.charges += charges;
    map.set(key, row);
}

const FIN_DEBT_TYPE_LABELS = { personal: 'Préstamo personal', acquaintance: 'De una persona conocida',
    bank: 'Crédito bancario', mortgage: 'Hipotecario', other: 'Préstamo' };

// El periodo que se ve: los pagos que llegaron a una tarjeta o a un préstamo, y las
// mensualidades de MSI de sus cortes
function finDebtPeriod() {
    const payments = new Map();
    const loans = new Map();
    (finState.transactions || []).forEach(tx => {
        if (tx.kind !== 'transfer') return;
        const target = finAccount(tx.to_account_id);
        if (target && target.kind === 'credit') finDebtGroup(payments, target, tx.currency, tx.amount_cents);
        if (target && target.kind === 'loan') {
            finDebtGroup(loans, target, tx.currency, tx.amount_cents, tx.interest_cents || 0, tx.charges_cents || 0);
        }
    });
    const bills = new Map();
    finBillsInPeriod().forEach(({ plan, bill }) => {
        finDebtGroup(bills, finAccount(plan.account_id), plan.currency, bill.amount_cents);
    });
    const sorted = map => [...map.values()].sort((a, b) => b.cents - a.cents);
    return { payments: sorted(payments), bills: sorted(bills), loans: sorted(loans) };
}

// Una fila: icono de la cuenta, nombre con su detalle y el monto
function finDebtRow(account, detail, amount, { button = false, negative = false } = {}) {
    const row = el(button ? 'button' : 'div', 'fin-debt-row');
    if (button) {
        row.type = 'button';
        row.dataset.accountId = String(account.id);
    }
    const text = el('span', 'fin-debt-text');
    text.appendChild(el('strong', '', account.name));
    if (detail) text.appendChild(el('small', '', detail));
    row.append(finBadge(finAccountIcon(account), finAccountColor(account), { size: 'sm', square: true }), text,
        el('span', `fin-debt-amount${negative ? ' negative' : ''}`, amount));
    return row;
}

// Las sumas por moneda, en una línea: "$1,200.00 · US$50.00"
function finDebtTotals(rows) {
    const byCurrency = new Map();
    rows.forEach(r => byCurrency.set(r.currency, (byCurrency.get(r.currency) || 0) + r.cents));
    return [...byCurrency].map(([currency, cents]) => formatMoney(cents, currency)).join(' · ');
}

// ---------- Resumen › Deudas del periodo ----------

function finRenderDebtSummary() {
    const { payments, bills, loans } = finDebtPeriod();
    if (!payments.length && !bills.length && !loans.length) return null;
    const card = el('section', 'fin-card fin-debts-summary');
    card.dataset.debtSummary = '';
    card.appendChild(el('h2', 'fin-card-title', 'Deudas'));
    const group = (title, rows, detail) => {
        if (!rows.length) return;
        const head = el('div', 'fin-debt-head');
        head.append(el('span', '', title), el('strong', '', finDebtTotals(rows)));
        card.appendChild(head);
        rows.forEach(r => card.appendChild(finDebtRow(r.account, detail(r), formatMoney(r.cents, r.currency))));
    };
    group('Pagos a tarjetas', payments, r => (r.count === 1 ? '1 pago' : `${r.count} pagos`));
    group('Mensualidades de MSI', bills, r => (r.count === 1 ? '1 mensualidad' : `${r.count} mensualidades`));
    group('Pagos a préstamos', loans, r => [r.count === 1 ? '1 pago' : `${r.count} pagos`,
        r.interest ? `${formatMoney(r.interest, r.currency)} de intereses` : '',
        r.charges ? `${formatMoney(r.charges, r.currency)} de seguros` : ''].filter(Boolean).join(' · '));
    card.appendChild(el('p', 'fin-hint', 'No se suma a tus gastos: la compra ya se contó el día que la hiciste.'
        + (loans.length ? ' De un préstamo, sus intereses y seguros sí están en tus gastos, y su capital también si lo que compraste con él no estaba anotado.' : '')));
    return card;
}

// ---------- Cuentas › Deudas ----------

// De los planes de MSI de una tarjeta que aún piden algo: lo del próximo corte y el último corte
function finDebtMsi(account) {
    let monthly = 0;
    let pending = 0;
    let until = null;
    (finState.installments || []).forEach(plan => {
        if (plan.account_id !== account.id || !plan.next_statement || plan.remaining_cents <= 0) return;
        const next = plan.bills.find(b => b.cut === plan.next_statement);
        if (next) monthly += next.amount_cents;
        pending += plan.remaining_cents;
        const last = plan.bills[plan.bills.length - 1].cut;
        if (!until || last > until) until = last;
    });
    return { monthly, pending, until };
}

function finRenderDebts(body) {
    const main = finMainCurrency();
    const owedOf = a => Math.max(0, -a.balance_cents);
    const cards = finActiveAccounts().filter(a => a.kind === 'credit');
    const loans = finActiveAccounts().filter(a => a.kind === 'loan');
    const all = [...cards, ...loans];
    const head = el('div', 'fin-accounts-head');
    const total = all.filter(a => a.currency === main).reduce((acc, a) => acc + owedOf(a), 0);
    head.append(el('span', '', 'Lo que debes'), el('strong', total ? 'negative' : '', finMoney(total, main)));
    const rows = [];
    // Otra moneda nunca se suma con la principal: va aparte
    const others = all.filter(a => a.currency !== main && owedOf(a));
    if (others.length) {
        rows.push(el('p', 'fin-hint fin-debt-other',
            `Además, ${finDebtTotals(others.map(a => ({ currency: a.currency, cents: owedOf(a) })))}`));
    }
    // Cada sección siempre, con su total y su + (así se agrega la primera)
    const section = (title, list, kind, label) => {
        const sub = el('div', 'fin-debt-head');
        sub.append(el('span', '', title), el('strong', '', list.length
            ? finDebtTotals(list.map(a => ({ currency: a.currency, cents: owedOf(a) }))) : finMoney(0, main)));
        rows.push(finHeadAdd(sub, { newAccount: kind }, label));
    };
    section('Tarjetas', cards, 'credit', 'Nueva tarjeta');
    cards.forEach(account => {
        const owed = owedOf(account);
        const msi = finDebtMsi(account);
        const detail = [];
        if (msi.monthly) detail.push(`MSI ${formatMoney(msi.monthly, account.currency)} al mes hasta ${finMonthYear(msi.until)}`);
        if (msi.pending && msi.pending < owed) detail.push(`de eso, ${formatMoney(msi.pending, account.currency)} a meses`);
        if (!owed) detail.push(account.balance_cents > 0 ? `${formatMoney(account.balance_cents, account.currency)} a favor` : 'Sin deuda');
        rows.push(finDebtRow(account, detail.join(' · '), formatMoney(owed, account.currency), { button: true, negative: owed > 0 }));
    });
    if (!cards.length) rows.push(el('p', 'fin-empty', 'Aún no tienes tarjetas de crédito.'));
    section('Préstamos', loans, 'loan', 'Nuevo préstamo');
    loans.forEach(account => {
        const owed = owedOf(account);
        const detail = [FIN_DEBT_TYPE_LABELS[account.debt_type] || 'Préstamo'];
        if (account.loan_payment_cents) detail.push(`${formatMoney(account.loan_payment_cents, account.currency)} al mes`);
        if (account.interest_rate_bp != null) detail.push(`tasa ${finRateText(account.interest_rate_bp)}`);
        if (!owed) detail.push('Pagado');
        rows.push(finDebtRow(account, detail.join(' · '), formatMoney(owed, account.currency), { button: true, negative: owed > 0 }));
    });
    if (!loans.length) rows.push(el('p', 'fin-empty', 'Aún no tienes préstamos.'));
    const hint = el('p', 'fin-hint', 'Lo que debe cada tarjeta, con lo que piden al mes sus compras a meses y hasta cuándo, '
        + 'y cada préstamo. Toca una para pagarla y ver sus pagos.');
    body.replaceChildren(head, ...rows, hint);
}

// "oct 2026"
function finMonthYear(iso) {
    return `${FIN_MONTHS_SHORT[Number(iso.slice(5, 7)) - 1]} ${iso.slice(0, 4)}`;
}
