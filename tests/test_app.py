"""La app en sí: rutas públicas, archivos servidos y lo que NO debe servir."""


def test_public_routes(api):
    s, body = api.call("GET", "/api/health")
    assert s == 200 and body == {"status": "healthy"}
    s, body = api.call("GET", "/api/version")
    assert s == 200 and body["version"]
    assert api.call("GET", "/health")[0] == 404


def test_frontend_files_are_served(client):
    for path in ["/", "/index.html", "/styles.css", "/script.js", "/habits.js", "/projects.js",
                 "/board.js", "/pomodoro.js", "/reports.js", "/project-overview.js", "/costs.js", "/notifications.js", "/workdays.js", "/settings.js", "/saved-reports.js", "/manifest.webmanifest",
                 "/icons/icon-192.png", "/icons/icon-512.png", "/icons/apple-touch-icon.png",
                 "/favicon.ico"]:
        assert client.get(path).status_code == 200, path
    assert client.get("/manifest.webmanifest").headers["content-type"].startswith("application/manifest+json")
    assert client.get("/icons/icon-192.png").content[:8] == b"\x89PNG\r\n\x1a\n"


def test_nothing_else_from_the_repo_is_served(client):
    # La app solo sirve lo que tiene ruta: ni el .env, ni la base, ni el código
    for path in ["/backend/.env", "/habits.db", "/.git/config", "/CLAUDE.md", "/backend/main.py",
                 "/requirements.txt", "/VERSION", "/icons/nope.png", "/icons/..%2Fbackend%2F.env",
                 "/icons/%2e%2e%2fVERSION"]:
        response = client.get(path)
        assert response.status_code == 404, path
        assert b"SECRET" not in response.content


def test_no_cors_for_other_sites(client):
    response = client.get("/api/version", headers={"Origin": "https://evil.example"})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_api_requires_a_token(api):
    for path in ["/api/tasks", "/api/boards", "/api/habits", "/api/pomodoro", "/api/auth/me"]:
        assert api.call("GET", path)[0] == 401, path
