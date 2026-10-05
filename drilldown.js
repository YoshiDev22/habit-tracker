// ============================================
// Menú de desglose (drill-down): el patrón de todo menú de opciones
// ============================================
//
// Una lista de filas con "›" (#…Menu con [data-open="nombre"]); al tocar una,
// su página (.settings-page[data-section="nombre"][data-title="…"]) entra
// deslizándose desde la derecha, el título del modal pasa a ser el de la
// página y aparece ‹. ‹ o Escape vuelven a la lista; Escape desde la lista
// llama a onClose. Nunca secciones que se despliegan en el sitio (acordeón):
// así es Configuración, y así va todo menú nuevo (CLAUDE.md › Modales).
//
// Las páginas se ven con .active, no con `hidden`, para que `hidden` quede
// libre (p. ej. ocultar una opción si un módulo está apagado). Mismas clases
// que Configuración (.settings-menu, .settings-item, .settings-page,
// .settings-back): se ven igual.

function createDrillDown({ modal, menu, back, title, rootTitle, onPage = null, onMenu = null, onClose = null }) {
    const pages = [...modal.querySelectorAll('.settings-page')];
    let current = null;

    function slide(element, from) {
        element.classList.remove('slide-from-right', 'slide-from-left');
        void element.offsetWidth;   // reinicia la animación aunque la clase se repita
        element.classList.add(from === 'left' ? 'slide-from-left' : 'slide-from-right');
    }

    function scrollTop() {
        const scroller = modal.querySelector('.modal-content');
        if (scroller) scroller.scrollTop = 0;
    }

    function show(name, { animate = true } = {}) {
        const page = pages.find(p => p.dataset.section === name);
        if (!page || page.hidden) {
            showMenu({ animate: false });
            return;
        }
        current = name;
        menu.hidden = true;
        pages.forEach(p => p.classList.toggle('active', p === page));
        back.hidden = false;
        title.textContent = page.dataset.title;
        scrollTop();
        if (animate) slide(page, 'right');
        if (onPage) onPage(name, page);
    }

    function showMenu({ animate = true } = {}) {
        current = null;
        menu.hidden = false;
        pages.forEach(p => p.classList.remove('active'));
        back.hidden = true;
        title.textContent = rootTitle;
        scrollTop();
        if (animate) slide(menu, 'left');
        if (onMenu) onMenu();
    }

    menu.addEventListener('click', (event) => {
        const item = event.target.closest('[data-open]');
        if (item) show(item.dataset.open);
    });
    back.addEventListener('click', () => showMenu());

    // Con el confirm o el selector de emoji encima, el Escape es de ellos
    document.addEventListener('keydown', (event) => {
        if (event.key !== 'Escape' || modal.classList.contains('hidden')) return;
        const onTop = ['confirmModal', 'emojiPickerModal'].some(id => {
            const other = document.getElementById(id);
            return other && !other.classList.contains('hidden');
        });
        if (onTop) return;
        event.preventDefault();
        if (current) showMenu();
        else if (onClose) onClose();
    });

    return {
        show,
        showMenu,
        get current() { return current; },
    };
}
