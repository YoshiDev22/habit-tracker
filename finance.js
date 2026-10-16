// ============================================
// Finanzas en la app: la pestaña que lleva a /finance
// ============================================
//
// Finanzas es su propia página (finance.html, con finance-app.js y los demás):
// aquí solo se muestra su pestaña, un enlace a /finance, con el módulo
// encendido, y la casilla de Configuración › Módulos a las cuentas con acceso.
// La pestaña no es una vista: el swipe no la cuenta (VIEWS en projects.js).

function applyFinanceModule() {
    // currentUser solo cambia al entrar y al tocar un módulo: los dos hooks que
    // llaman aquí, así que script.js no necesita saber de Finanzas
    const state = currentUser && currentUser.modules && currentUser.modules.finance;
    document.getElementById('moduleFinanceOption').hidden = !(state && state.allowed);
    document.getElementById('tabFinance').hidden = !moduleEnabled('finance');
    syncTabIndicator();
}

function resetFinance() {
    document.getElementById('tabFinance').hidden = true;
    document.getElementById('moduleFinanceOption').hidden = true;
    syncTabIndicator();
}

window.appDataHooks.push(applyFinanceModule);
window.modulesChangedHooks.push(applyFinanceModule);
window.appLogoutHooks.push(resetFinance);
