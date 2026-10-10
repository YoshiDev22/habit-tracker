"""
El panel de administración en tu máquina, sin Cloudflare Access (1.27).

En producción, Access firma cada petición al panel. Aquí este script hace de
Access: crea una llave RSA temporal, arranca backend/admin_main.py en 127.0.0.1
confiando solo en esa llave (ADMIN_DEV_KEYS_FILE, con el equipo "dev-local") y
abre el navegador con un token firmado para tu correo. Al cerrarlo (Ctrl+C) la
llave se borra: ningún token de esta sesión vuelve a servir.

Desde la raíz del repo, con la app normal ya migrada (usa la misma base):

    python scripts/admin_dev.py --email tu-correo@ejemplo.com

Solo para desarrollo: el panel avisa en el log cuando arranca así, y se niega a
juntar este modo con un equipo de Access real.
"""
import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
import webbrowser

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwk, jwt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEAM = "dev-local"   # backend/admin_auth.py: DEV_TEAM
AUDIENCE = "dev-local"
KID = "dev"


def make_keys(folder: str) -> str:
    """La llave privada (en memoria) y su JWKS público en un archivo de `folder`."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    public = {**jwk.construct(pem, "RS256").public_key().to_dict(), "kid": KID, "alg": "RS256", "use": "sig"}
    with open(os.path.join(folder, "keys.json"), "w", encoding="utf-8") as f:
        json.dump({"keys": [public]}, f)
    return pem


def wait_until_up(url: str, process: subprocess.Popen, seconds: float = 20) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Panel de administración local, sin Cloudflare Access.")
    parser.add_argument("--email", required=True, help="tu correo: será el único administrador")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--hours", type=float, default=8, help="cuánto dura el token (8 h)")
    parser.add_argument("--no-browser", action="store_true", help="solo imprimir el enlace")
    args = parser.parse_args(argv)

    # Cerrar la ventana o Ctrl+Break en Windows: lo mismo que Ctrl+C, para que la llave se borre
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, signal.default_int_handler)

    folder = tempfile.mkdtemp(prefix="habit-admin-dev-")
    try:
        pem = make_keys(folder)
        now = int(time.time())
        token = jwt.encode({"email": args.email.strip().lower(), "aud": AUDIENCE,
                            "iss": f"https://{TEAM}.cloudflareaccess.com", "iat": now,
                            "exp": now + int(args.hours * 3600)}, pem, algorithm="RS256", headers={"kid": KID})
        env = {**os.environ, "ADMIN_EMAILS": args.email, "ADMIN_ACCESS_TEAM": TEAM,
               "ADMIN_ACCESS_AUD": AUDIENCE, "ADMIN_DEV_KEYS_FILE": os.path.join(folder, "keys.json")}
        base = f"http://127.0.0.1:{args.port}"
        process = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.admin_main:app",
                                    "--host", "127.0.0.1", "--port", str(args.port)], cwd=ROOT, env=env)
        try:
            if not wait_until_up(base + "/admin.css", process):
                print("El panel no arrancó: mira el error de arriba.", file=sys.stderr)
                return 1
            link = f"{base}/#dev={token}"
            print(f"\nPanel listo (solo esta máquina): {link}\nCtrl+C para cerrarlo.\n", flush=True)
            if not args.no_browser:
                webbrowser.open(link)
            process.wait()
        except KeyboardInterrupt:
            pass
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
        return 0
    finally:
        shutil.rmtree(folder, ignore_errors=True)
        print("Panel cerrado; la llave de esta sesión se borró.", flush=True)


if __name__ == "__main__":
    sys.exit(main())
