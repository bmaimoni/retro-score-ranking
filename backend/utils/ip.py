import hashlib
from fastapi import Request
from config import get_settings


def get_client_ip(request: Request) -> str:
    """
    Extrai o IP real do cliente considerando proxies reversos.
    Railway e Vercel injetam o IP original em X-Forwarded-For.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # X-Forwarded-For pode conter lista: "client, proxy1, proxy2"
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def hash_ip(ip: str) -> str:
    """
    Retorna SHA-256(ip + salt).
    Nunca armazena o IP bruto — compatível com LGPD.
    """
    settings = get_settings()
    raw = f"{ip}{settings.ip_hash_salt}"
    return hashlib.sha256(raw.encode()).hexdigest()
