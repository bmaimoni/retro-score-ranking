import hashlib
import hmac
from dataclasses import dataclass
from fastapi import Request, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from config import get_settings
from utils.db import get_pool
import auth.service as auth_svc
import repositories.admin_vinculo as admin_vinculo_repo

_bearer = HTTPBearer(auto_error=False)


@dataclass
class AdminContext:
    """
    Identidade do administrador autenticado nesta requisição.

    identificador: string pra logging/moderado_por — "admin" pro
        bootstrap via token, ou o e-mail/id do usuário via sessão.
    user_id: None se veio do Bearer token; setado se veio de sessão —
        usado pra checar escopo específico (ver
        repositories.admin_vinculo.tem_acesso_evento).
    super: True = enxerga e modera tudo, sem checagem de escopo por
        evento/marca necessária.
    """
    identificador: str
    user_id: str | None
    super: bool

    def __str__(self):
        # Mantém compatibilidade com código que espera uma string
        # simples (logs estruturados, moderado_por) — ver routers/admin.py
        return self.identificador


async def require_admin(request: Request, pool=Depends(get_pool)) -> AdminContext:
    """
    Dependency para rotas de admin. Aceita dois caminhos (ver
    docs/MARCAS_SPEC.md §6):

    1. Bearer <ADMIN_SECRET> — bootstrap/emergência, sempre super-admin.
       Comportamento inalterado em relação ao que já existia.
    2. Sessão de visitante comum (cookie, mesma de AUTH_SPEC.md) cujo
       usuário tenha pelo menos um admin_vinculo ativo — escopo
       conforme o(s) vínculo(s) (super, ou restrito a marca/evento
       específicos, checado depois por rota via tem_acesso_evento).
    """
    settings = get_settings()
    credentials: HTTPAuthorizationCredentials | None = await _bearer(request)

    if credentials:
        provided = hashlib.sha256(credentials.credentials.encode()).hexdigest()
        expected = hashlib.sha256(settings.admin_secret.encode()).hexdigest()
        if hmac.compare_digest(provided, expected):
            return AdminContext(identificador="admin", user_id=None, super=True)
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    # Sem Bearer — tenta sessão de visitante com vínculo de admin
    session_id = request.cookies.get(settings.session_cookie_name)
    if session_id:
        usuario = await auth_svc.obter_usuario_da_sessao(pool, session_id)
        if usuario:
            vinculos = await admin_vinculo_repo.listar_por_usuario(pool, usuario["id"])
            if vinculos:
                eh_super = any(v["escopo"] == "super" for v in vinculos)
                identificador = usuario.get("email") or usuario["id"]
                return AdminContext(identificador=identificador, user_id=usuario["id"], super=eh_super)

    raise HTTPException(status_code=401, detail="Autenticação necessária")
