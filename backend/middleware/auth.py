import hashlib
import hmac
from fastapi import Request, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from config import get_settings

_bearer = HTTPBearer(auto_error=False)


async def require_admin(request: Request) -> str:
    """
    Dependency para rotas de admin.
    Valida o header: Authorization: Bearer <ADMIN_SECRET>

    Usa hmac.compare_digest para prevenir timing attacks.
    Retorna o valor do secret (usado como moderado_por nos logs).
    """
    settings = get_settings()
    credentials: HTTPAuthorizationCredentials | None = await _bearer(request)

    if not credentials:
        raise HTTPException(status_code=401, detail="Autenticação necessária")

    provided = hashlib.sha256(credentials.credentials.encode()).hexdigest()
    expected = hashlib.sha256(settings.admin_secret.encode()).hexdigest()

    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    return "admin"
