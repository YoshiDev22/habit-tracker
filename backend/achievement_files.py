"""
Las evidencias de los Logros en disco: qué se acepta, dónde se guarda y su miniatura.

- Dónde: UPLOADS_DIR (backend/.env; por defecto <repo>/uploads, ignorado por git)
  /achievements/<user_id>/<nombre aleatorio>. La app solo sirve lo que tiene ruta,
  así que nada de esa carpeta sale a internet; el router entrega cada archivo
  solo a su dueño. Carpetas en 700 y archivos en 600.
- Qué: PDF, JPG, PNG y WEBP, reconocidos por su contenido (los primeros bytes y,
  en las imágenes, que Pillow las abra), nunca por la extensión ni por el
  Content-Type que manda el navegador.
- Cuánto: MAX_FILE_BYTES por archivo y QUOTA_BYTES por cuenta (los dos se pueden
  cambiar en backend/.env), y MAX_FILES_PER_ACHIEVEMENT por logro.
- Miniatura: WEBP de THUMB_SIZE px, hecha en el servidor. Al rehacerla se pierden
  los metadatos (EXIF, ubicación). Los PDF no tienen: la pantalla pone un ícono.
"""
import os
import shutil
import uuid
import warnings
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple

from dotenv import load_dotenv
from PIL import Image, ImageOps

BASE_DIR = Path(__file__).resolve().parents[1]
# Los topes se leen al importar: backend/.env tiene que estar cargado ya, venga de
# la app o de scripts/purge_accounts.py
load_dotenv(BASE_DIR / "backend" / ".env")

MAX_FILE_BYTES = int(os.getenv("ACHIEVEMENT_FILE_MAX_BYTES") or 10 * 1024 * 1024)
QUOTA_BYTES = int(os.getenv("ACHIEVEMENT_QUOTA_BYTES") or 200 * 1024 * 1024)
MAX_FILES_PER_ACHIEVEMENT = 20
THUMB_SIZE = 400
# Una imagen de más píxeles se rechaza antes de abrirla entera: un PNG de pocos
# KB puede pedir gigas de memoria al descomprimirse ("decompression bomb").
MAX_IMAGE_PIXELS = 40_000_000
# Global de Pillow: la app no abre imágenes en ningún otro lado
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

# Tipo que se acepta -> extensión con la que se guarda
ALLOWED = {
    "application/pdf": "pdf",
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
PILLOW_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


class UploadRejected(ValueError):
    """El archivo no se acepta; el mensaje es para el usuario."""


def uploads_root() -> Path:
    """Se lee en cada llamada: las pruebas la cambian con monkeypatch.setenv."""
    configured = os.getenv("UPLOADS_DIR")
    return Path(configured).resolve() if configured else BASE_DIR / "uploads"


def user_dir(user_id: int, create: bool = False) -> Path:
    path = uploads_root() / "achievements" / str(int(user_id))
    if create:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(path, 0o700)
    return path


def file_path(user_id: int, stored_name: str) -> Path:
    """La ruta de un archivo guardado. `stored_name` lo puso la app, pero se
    comprueba igual que no salga de la carpeta de la cuenta."""
    folder = user_dir(user_id)
    path = (folder / stored_name).resolve()
    if path.parent != folder.resolve():
        raise FileNotFoundError(stored_name)
    return path


def sniff(data: bytes) -> Optional[str]:
    """El tipo por los primeros bytes, o None si no es uno de los aceptados."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _open_image(data: bytes, mime: str) -> Image.Image:
    """Abre la imagen y comprueba que sea lo que dicen sus primeros bytes y que no
    sea desproporcionada. Cualquier fallo es UploadRejected."""
    try:
        with warnings.catch_warnings():
            # Entre 1 y 2 veces MAX_IMAGE_PIXELS Pillow solo avisa: que también falle
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            probe = Image.open(BytesIO(data))
            if PILLOW_FORMATS.get(probe.format) != mime:
                raise UploadRejected("El archivo no es la imagen que dice ser.")
            probe.verify()
            image = Image.open(BytesIO(data))   # verify() deja inservible al primero
            image.load()
    except UploadRejected:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise UploadRejected("La imagen es demasiado grande (en píxeles).")
    except Exception:
        raise UploadRejected("La imagen está dañada o no se puede leer.")
    return image


def make_thumbnail(image: Image.Image) -> bytes:
    image = ImageOps.exif_transpose(image)
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA" if "transparency" in image.info or image.mode in ("LA", "PA") else "RGB")
    image.thumbnail((THUMB_SIZE, THUMB_SIZE))
    out = BytesIO()
    image.save(out, format="WEBP", quality=80)
    return out.getvalue()


def check_upload(data: bytes) -> Tuple[str, Optional[bytes]]:
    """(tipo, miniatura o None) de un archivo ya leído, o UploadRejected."""
    if not data:
        raise UploadRejected("El archivo está vacío.")
    mime = sniff(data)
    if mime is None:
        raise UploadRejected("Solo se aceptan PDF, JPG, PNG o WEBP.")
    if mime == "application/pdf":
        return mime, None
    return mime, make_thumbnail(_open_image(data, mime))


def _write_private(path: Path, data: bytes) -> None:
    """Escribe en 600, primero a un temporal y después lo mueve: un archivo a
    medias nunca queda con el nombre definitivo."""
    tmp = path.with_name(path.name + ".part")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def store(user_id: int, mime: str, data: bytes, thumb: Optional[bytes]) -> Tuple[str, Optional[str]]:
    """Guarda el archivo (y su miniatura) con un nombre aleatorio; devuelve los nombres."""
    folder = user_dir(user_id, create=True)
    name = f"{uuid.uuid4().hex}.{ALLOWED[mime]}"
    _write_private(folder / name, data)
    thumb_name = None
    if thumb is not None:
        thumb_name = f"{name.rsplit('.', 1)[0]}.thumb.webp"
        try:
            _write_private(folder / thumb_name, thumb)
        except BaseException:
            (folder / name).unlink(missing_ok=True)
            raise
    return name, thumb_name


def remove(user_id: int, *names: Optional[str]) -> None:
    """Borra archivos de la cuenta; uno que ya no está no es error."""
    for name in names:
        if name:
            try:
                file_path(user_id, name).unlink(missing_ok=True)
            except FileNotFoundError:
                pass


def remove_user(user_id: int) -> None:
    """Toda la carpeta de la cuenta (al borrarla, backend/accounts.py)."""
    shutil.rmtree(user_dir(user_id), ignore_errors=True)


def clean_name(name: Optional[str]) -> str:
    """El nombre original, solo para enseñarlo: sin carpetas ni caracteres de control."""
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    base = "".join(c for c in base if c.isprintable()).strip()
    return base[:200] or "archivo"
