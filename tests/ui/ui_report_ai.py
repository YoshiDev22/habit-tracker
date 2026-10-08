"""IA para los reportes (épica 30, Fase 5): la casilla, "Ver qué se envía" y
"Reescribir con IA". Las pruebas no tienen proveedor: se ve el aviso y las reglas."""
import asyncio
import json
import os
import sqlite3
from pathlib import Path

import api
from api import login
from cdp import Browser

BASE = api.BASE
CLOSE_WELCOME = "document.getElementById('habitsSetupModal').classList.add('hidden')"
results = []


def check(cond, label):
    results.append(("OK  " if cond else "FAIL") + " " + label)


def grant_ai(email):
    db = Path(os.environ["HABIT_UI_TMP"]) / "test_report_ai.db"
    conn = sqlite3.connect(db)
    user_id = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()[0]
    conn.execute("INSERT INTO user_modules (user_id, module, allowed, enabled) VALUES (?, 'ai', 1, 1)", (user_id,))
    conn.commit()
    conn.close()


async def main():
    login("yoshi@test.com")
    token = api.TOKEN
    grant_ai("yoshi@test.com")
    b = Browser()
    await b.start()
    try:
        await b.viewport(390, 844, mobile=True)
        await b.goto(BASE + "/")
        await b.js(f"localStorage.setItem('access_token', {json.dumps(token)}); localStorage.removeItem('last_view');")
        await b.goto(BASE + "/", wait=2.5)
        await b.js(CLOSE_WELCOME)

        # Configuración › Módulos: la casilla encendida y "Ver qué se envía"
        await b.js("openSettings('modules')")
        st = await b.js("({shown: !document.getElementById('moduleAiOption').hidden, on: document.getElementById('moduleAi').checked,"
                        " preview: !document.getElementById('aiPreview').hidden})")
        check(st == {"shown": True, "on": True, "preview": True}, f"with access the AI option and preview show ({st})")
        await b.js("document.getElementById('aiPreview').open = true")
        await b.wait_for("document.getElementById('aiPreviewJson').textContent.includes('Responde SOLO')")
        meta = await b.js("document.getElementById('aiPreviewMeta').textContent")
        check("no está configurada" in meta, f"the preview says there is no provider ({meta})")
        sent = await b.js("document.getElementById('aiPreviewJson').textContent")
        check('"total_minutes"' in sent and "project_id" not in sent, "it shows the payload, in minutes and without ids")
        await b.shot("ai_preview", full=False)
        await b.js("document.getElementById('settingsClose').click()")

        # Un reporte: sale de las reglas y dice por qué; reescribir avisa sin romperlo
        await b.js("document.getElementById('tabReports').click()")
        await b.wait_for("document.getElementById('savedReportBtn').textContent === 'Generar reporte de tiempo'")
        await b.js("document.getElementById('savedReportBtn').click()")
        await b.wait_for("document.getElementById('savedReportTitle').textContent.startsWith('Reporte semanal')")
        st = await b.js("({meta: document.getElementById('savedReportMeta').textContent,"
                        " note: document.getElementById('savedReportError').textContent,"
                        " rewrite: !document.getElementById('savedReportRewrite').hidden})")
        check("Texto de reglas" in st["meta"] and "no está configurada" in st["note"] and st["rewrite"],
              f"the report says its text came from the rules, and why ({st})")
        await b.js("document.getElementById('savedReportRewrite').click()")
        await b.wait_for("document.getElementById('savedReportRewrite').textContent === 'Reescribir con IA'")
        st = await b.js("({note: document.getElementById('savedReportError').textContent,"
                        " cards: document.querySelectorAll('#savedReportBody .report-card').length})")
        check("no está configurada" in st["note"] and st["cards"] >= 3, f"rewriting without a provider says so and keeps the report ({st})")

        # Regenerar con la IA fallando (simulado): el reporte no cambia y ofrece las reglas
        meta_before = await b.js("document.getElementById('savedReportMeta').textContent")
        await b.js("""(() => {
            const real = window.apiFetch;
            window.apiFetch = (path, options) => path === '/api/reports' && options && options.method === 'POST' && options.json.use_ai
                ? Promise.reject(new ApiError('La IA no pudo escribir el texto (no se pudo conectar). El reporte no cambió.', 502))
                : real(path, options);
            savedState.readyAt = 0;
        })()""")
        await b.js("document.getElementById('savedReportRegenerate').click()")
        await b.wait_for("!document.getElementById('savedReportRules').hidden")
        st = await b.js("({meta: document.getElementById('savedReportMeta').textContent,"
                        " note: document.getElementById('savedReportError').textContent})")
        check(st["meta"] == meta_before and "no cambió" in st["note"],
              f"a failed AI regeneration keeps the report and its date, and says why ({st})")
        await b.js("savedState.readyAt = 0; document.getElementById('savedReportRules').click()")
        await b.wait_for("document.getElementById('savedReportRules').hidden && document.getElementById('savedReportStatus').textContent.startsWith('Reporte generado')")
        check(True, "Regenerar con reglas generates it without the AI")

        # Con proveedor (simulado: las pruebas no tienen), el reporte dice cuántos textos quedan hoy
        await b.js("""(() => {
            const real = window.apiFetch;
            window.apiFetch = (path, options) => path.startsWith('/api/reports/ai-usage')
                ? Promise.resolve({configured: true, limit: 10, used_today: 3, remaining: 7})
                : real(path, options);
        })()""")
        await b.js("refreshAiUsage()")
        await b.wait_for("!document.getElementById('savedReportAiUsage').hidden")
        st = await b.js("({text: document.getElementById('savedReportAiUsage').textContent,"
                        " seen: document.getElementById('savedReportAiUsage').offsetHeight > 0})")
        check(st["text"] == "IA: te quedan 7 de 10 textos hoy (reportes de tiempo y hábitos)." and st["seen"], f"the report says how many AI texts are left today ({st})")
    finally:
        await b.close()

    print("\n".join(results))
    errors = [c for c in b.console if c.startswith(("[error]", "[exception]"))]
    print("console errors:", errors or "none")
    if any(r.startswith("FAIL") for r in results) or errors:
        raise AssertionError("\n".join(r for r in results if not r.startswith("OK")) + f"\nconsole errors: {errors}")


def test_report_ai():
    asyncio.run(main())
