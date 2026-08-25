import hashlib
import hmac
from dataclasses import dataclass, field
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
    user_id: None se veio do Bearer token; setado se veio de sessão.
    super: True = enxerga e administra tudo, sem checagem de escopo.
    vinculos: vínculos ativos escopo='marca' do usuário, cada um
        {"marca_id": str, "nivel": "admin"|"moderador"} — carregados
        uma vez aqui (sem N+1 por rota). Vazio quando super=True (nível
        por marca não se aplica a super) ou quando veio via Bearer.

    Ver docs/PERMISSOES_SPEC.md — nível é por vínculo (marca), não
    global pra pessoa: a mesma pessoa pode ser admin numa marca e
    moderador (ou nada) noutra.
    """
    identificador: str
    user_id: str | None
    super: bool
    vinculos: list[dict] = field(default_factory=list)

    def __str__(self):
        # Mantém compatibilidade com código que espera uma string
        # simples (logs estruturados, moderado_por) — ver routers/admin.py
        return self.identificador

    def nivel_na_marca(self, marca_id: str) -> str | None:
        """Nível efetivo nesta marca — 'admin' pra super (atua como
        admin em qualquer marca), o nível do vínculo se houver um
        ativo pra essa marca, ou None se não tem acesso nenhum ali."""
        if self.super:
            return "admin"
        for v in self.vinculos:
            if v["marca_id"] == str(marca_id):
                return v["nivel"]
        return None

    def eh_admin_na_marca(self, marca_id: str) -> bool:
        return self.nivel_na_marca(marca_id) == "admin"

    def tem_acesso_na_marca(self, marca_id: str) -> bool:
        return self.nivel_na_marca(marca_id) is not None


async def require_admin(request: Request, pool=Depends(get_pool)) -> AdminContext:
    """
    Dependency para rotas de admin. Aceita dois caminhos (ver
    docs/PERMISSOES_SPEC.md):

    1. Bearer <ADMIN_SECRET> — bootstrap/emergência, sempre super-admin.
       Comportamento inalterado em relação ao que já existia.
    2. Sessão de visitante comum (cookie, mesma de AUTH_SPEC.md) cujo
       usuário tenha pelo menos um admin_vinculo ativo — escopo/nível
       resolvido por marca, checado depois por rota via
       AdminContext.nivel_na_marca / eh_admin_na_marca.
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
            vinculos_raw = await admin_vinculo_repo.listar_por_usuario(pool, usuario["id"])
            if vinculos_raw:
                eh_super = any(v["escopo"] == "super" for v in vinculos_raw)
                vinculos = [
                    {"marca_id": str(v["marca_id"]), "nivel": v["nivel"]}
                    for v in vinculos_raw if v["escopo"] == "marca"
                ]
                identificador = usuario.get("email") or usuario["id"]
                return AdminContext(
                    identificador=identificador, user_id=usuario["id"],
                    super=eh_super, vinculos=vinculos,
                )

    raise HTTPException(status_code=401, detail="Autenticação necessária")
