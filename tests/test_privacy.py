"""El aviso de privacidad (1.28, BACKLOG 39): /privacidad con los datos de la instancia."""
import pytest

RESPONSABLE = ("Para conocer la identidad y domicilio del responsable del tratamiento, o para ejercer tus derechos\n"
               "        ARCO, escribe a")
PRIVACY_VARS = ("PRIVACY_EMAIL", "PRIVACY_HOSTING", "PRIVACY_BACKUPS", "PRIVACY_PROXY", "PRIVACY_AI",
                "AI_BASE_URL", "AI_MODEL")


@pytest.fixture(autouse=True)
def no_instance_data(monkeypatch):
    for name in PRIVACY_VARS:
        monkeypatch.delenv(name, raising=False)


def test_it_is_public_and_fills_in_the_instance(client, monkeypatch):
    monkeypatch.setenv("PRIVACY_EMAIL", "privacidad@ejemplo.com")
    monkeypatch.setenv("PRIVACY_HOSTING", "Proveedor X (servidor en País Y)")
    monkeypatch.setenv("PRIVACY_BACKUPS", "Nube V")
    monkeypatch.setenv("PRIVACY_PROXY", "Red Z")
    monkeypatch.setenv("PRIVACY_AI", "IA W")
    r = client.get("/privacidad")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert r.headers["cache-control"] == "no-cache"
    page = r.text
    assert RESPONSABLE in page and 'href="mailto:privacidad@ejemplo.com"' in page
    assert "Proveedor X (servidor en País Y), donde vive la app" in page
    assert "Nube V, donde se guardan las copias de respaldo" in page
    assert "Red Z, que la protege" in page and "El servidor y Red Z también registran" in page
    assert "IA W, que recibe" in page and "Nunca recibe tu correo ni tu nombre" in page
    assert "Proyecto en desarrollo" in page and "Última actualización:" in page
    assert "{{" not in page and "<!--" + "proxy-->" not in page and "<!--" + "ai-->" not in page
    assert "<!--" + "backups-->" not in page
    assert "privacy-missing" not in page


def test_without_instance_data_it_says_so_and_drops_what_does_not_apply(client):
    page = client.get("/privacidad").text
    assert "privacy-missing" in page and "[contacto sin configurar]" in page
    assert "el proveedor del servidor, donde vive la app" in page
    assert "que la protege" not in page and "El servidor también registra" in page
    assert "donde se guardan las copias de respaldo" not in page
    # Sin IA configurada en la instancia, no se habla de ella
    assert "enciendes la IA" not in page and "{{" not in page


def test_with_ai_configured_and_no_name_it_is_generic(client, monkeypatch):
    monkeypatch.setenv("AI_BASE_URL", "http://localhost:8080/v1")
    monkeypatch.setenv("AI_MODEL", "modelo")
    assert "el proveedor de IA de esta instalación, que recibe" in client.get("/privacidad").text


def test_instance_values_are_escaped(client, monkeypatch):
    monkeypatch.setenv("PRIVACY_HOSTING", "<script>alert(1)</script>")
    monkeypatch.setenv("PRIVACY_EMAIL", 'a"@b.com')
    page = client.get("/privacidad").text
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page
    assert 'mailto:a&quot;@b.com' in page
