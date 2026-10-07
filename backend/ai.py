"""
El proveedor de IA (épica 30, Fase 5): una sola función de llamada para todos
los que hablan el formato "chat completions" de OpenAI (Cloudflare Workers AI,
Google Gemini, OpenAI, o un servidor local como llama.cpp u Ollama). Uno por
instancia, en backend/.env:

    AI_PROVIDER   nombre para mostrar (cloudflare, gemini, openai, local)
    AI_BASE_URL   la URL base compatible con OpenAI (sin /chat/completions)
    AI_API_KEY    la clave; opcional para un servidor local
    AI_MODEL      el modelo, p. ej. @cf/openai/gpt-oss-120b
    AI_DAILY_LIMIT llamadas por cuenta y día (UTC); 10 si no se pone
    AI_TIMEOUT    segundos de espera; 60 si no se pone

Con la biblioteca estándar (urllib): sin dependencias nuevas. Sin AI_BASE_URL
o AI_MODEL no hay IA y todo sale de las reglas. La clave nunca se escribe en
logs, errores ni respuestas.
"""
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

DEFAULT_DAILY_LIMIT = 10
# Los reportes de costos llevan su propio contador (AI_COSTS_DAILY_LIMIT)
DEFAULT_COSTS_DAILY_LIMIT = 10
DEFAULT_TIMEOUT = 60


class AiError(Exception):
    """La llamada no dio un texto usable. El mensaje es corto y no lleva datos
    del usuario ni la clave: se guarda en ai_calls y se le muestra."""


@dataclass
class AiConfig:
    provider: str
    base_url: str
    api_key: Optional[str]
    model: str
    daily_limit: int
    timeout: int
    costs_daily_limit: int = DEFAULT_COSTS_DAILY_LIMIT

    @property
    def uses_training_free_tier(self) -> bool:
        # Gemini en la capa gratuita usa el contenido para mejorar sus productos
        return self.provider.lower() == "gemini" or "generativelanguage.googleapis.com" in self.base_url


def _int_env(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, "")))
    except ValueError:
        return default


def ai_config() -> Optional[AiConfig]:
    """La configuración de la instancia, o None si no hay proveedor."""
    base_url = (os.getenv("AI_BASE_URL") or "").strip().rstrip("/")
    model = (os.getenv("AI_MODEL") or "").strip()
    # Sin URL o modelo, o con el ejemplo de .env.example sin llenar (<ACCOUNT_ID>)
    if not base_url or not model or "<" in base_url:
        return None
    return AiConfig(
        provider=(os.getenv("AI_PROVIDER") or "").strip() or "openai-compatible",
        base_url=base_url,
        api_key=(os.getenv("AI_API_KEY") or "").strip() or None,
        model=model,
        daily_limit=_int_env("AI_DAILY_LIMIT", DEFAULT_DAILY_LIMIT),
        timeout=_int_env("AI_TIMEOUT", DEFAULT_TIMEOUT) or DEFAULT_TIMEOUT,
        costs_daily_limit=_int_env("AI_COSTS_DAILY_LIMIT", DEFAULT_COSTS_DAILY_LIMIT),
    )


@dataclass
class AiReply:
    content: str
    input_tokens: Optional[int]
    output_tokens: Optional[int]


def chat_completion(config: AiConfig, system: str, user: str, max_tokens: int = 4000) -> AiReply:
    """Una petición, una respuesta. Lanza AiError si algo falla."""
    body = json.dumps({
        "model": config.model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    request = urllib.request.Request(f"{config.base_url}/chat/completions", data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=config.timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        if error.code == 429:
            raise AiError("El proveedor de IA rechazó la llamada por límite de uso (429)") from None
        if error.code in (401, 403):
            raise AiError(f"El proveedor de IA rechazó la clave ({error.code})") from None
        raise AiError(f"El proveedor de IA respondió con un error ({error.code})") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise AiError("No se pudo conectar con el proveedor de IA") from None
    except ValueError:
        raise AiError("El proveedor de IA no respondió JSON") from None
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise AiError("La respuesta del proveedor de IA no trae texto") from None
    if not isinstance(content, str) or not content.strip():
        raise AiError("El proveedor de IA respondió vacío")
    usage = data.get("usage") or {}
    return AiReply(content=content, input_tokens=usage.get("prompt_tokens"),
                   output_tokens=usage.get("completion_tokens"))
