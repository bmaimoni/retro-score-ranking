"""
Router de autenticação — HTTP.
Prefixo: /api/auth

Endpoints:
  GET  /api/auth/providers            → quais métodos de login estão configurados
  GET  /api/auth/google/start         → redireciona pro Google (OAuth)
  GET  /api/auth/google/callback      → recebe volta do Google, cria sessão
  POST /api/auth/magic-link/request   → envia e-mail com link de acesso
  POST /api/auth/magic-link/verify    → valida o token do link, cria sessão
  GET  /api/auth/session              → usuário da sessão atual (ou 401)
  POST /api/auth/logout               → revoga a sessão

Ver docs/AUTH_SPEC.md §4 para os fluxos completos.
"""
import secrets
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr

from config import get_settings
from utils.db import get_pool
from utils.ip import get_client_ip, hash_ip
import auth.service as auth_svc
import auth.repository as auth_repo
import repositories.membership as membership_repo

log = structlog.get_logger()

router = APIRouter(prefix="/api/auth", tags=["auth"])

STATE_COOKIE = "oauth_state"
NEXT_COOKIE  = "oauth_next"


def _next_e_seguro(next_path: str | None) -> bool:
    """Só caminho relativo simples é aceito — nunca URL absoluta nem
    '//' (protocolo-relativo, jeito clássico de burlar open-redirect)."""
    return bool(next_path) and next_path.startswith("/") and not next_path.startswith("//")


def _resolver_redirect_final(next_path: str | None) -> str:
    """
    Valida 'next' pra evitar open redirect (ver _next_e_seguro). Sem
    next válido, cai no frontend_base_url de sempre.
    """
    settings = get_settings()
    if not _next_e_seguro(next_path):
        return settings.frontend_base_url
    return f"{settings.frontend_base_url}{next_path}"


def _set_session_cookie(response: Response, session_id: str) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.session_cookie_name,
        session_id,
        max_age=settings.session_ttl_days * 86400,
        httponly=True,
        # SameSite=None + Secure=True são obrigatórios aqui, não Lax:
        # o frontend (vercel.app) chama o backend (railway.app) via
        # fetch() cross-origin (GET /api/auth/session, POST /upload
        # com sessão) — Lax só cobre navegação de página inteira (ex.:
        # o redirect do Google), não chamadas JS. SameSite=None exige
        # Secure=True incondicionalmente, mesmo fora de produção.
        secure=True,
        samesite="none",
    )


def _usuario_publico(usuario: dict, tem_arena: bool = False) -> dict:
    """Formato de usuário exposto pro frontend — nunca campos internos.

    tem_arena: se a pessoa tem pelo menos um membership scope='marca'
    ativo — usado pela home institucional pra mostrar atalho "Meu
    painel" em vez de só "Meu perfil" pra quem já administra alguma
    Arena (achado durante o planejamento da Fase 8, ver
    PLANO_IMPLEMENTACAO_2026.md)."""
    return {
        "id": usuario["id"],
        "nome": usuario["nome"],
        "email": usuario["email"],
        "foto_url": usuario["foto_url"],
        "tem_arena": tem_arena,
    }


# ── Descoberta de providers ────────────────────────────────────

@router.get("/providers")
async def listar_providers():
    """Quais métodos de login estão configurados — o frontend usa isso
    pra decidir quais botões mostrar (evita mostrar 'Continuar com
    Google' se GOOGLE_CLIENT_ID não estiver setado, por exemplo)."""
    return get_settings().auth_configurado


# ── Google OAuth ────────────────────────────────────────────────

@router.get("/google/start")
async def google_start(next: str | None = None):
    """
    next: caminho relativo pra onde voltar depois do login (ex.:
    '/admin.html', pro admin logar com Google sem cair na tela errada).
    Ver _resolver_redirect_final para a validação de segurança.
    """
    settings = get_settings()
    if not settings.auth_configurado["google"]:
        raise HTTPException(status_code=503, detail="Login com Google não está configurado")

    state = secrets.token_urlsafe(24)
    url = auth_svc.gerar_url_autorizacao_google(state)

    redirect = RedirectResponse(url)
    redirect.set_cookie(
        STATE_COOKIE, state, max_age=600,
        httponly=True, secure=settings.is_production, samesite="lax",
    )
    if next:
        redirect.set_cookie(
            NEXT_COOKIE, next, max_age=600,
            httponly=True, secure=settings.is_production, samesite="lax",
        )
    return redirect


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    pool=Depends(get_pool),
):
    settings = get_settings()
    cookie_state = request.cookies.get(STATE_COOKIE)

    if not code or not state or not cookie_state or state != cookie_state:
        raise HTTPException(status_code=400, detail="Requisição de login inválida (state não confere)")

    try:
        perfil = await auth_svc.trocar_code_por_perfil_google(code)
    except Exception:
        log.warning("google_callback_erro", exc_info=True)
        raise HTTPException(status_code=400, detail="Não foi possível completar o login com Google")

    usuario = await auth_svc.login_ou_criar_usuario(
        pool,
        provider="google",
        provider_user_id=perfil["sub"],
        email=perfil.get("email", ""),
        email_verified=perfil.get("email_verified", False),
        nome=perfil.get("name"),
        foto_url=perfil.get("picture"),
    )

    ip_hash = hash_ip(get_client_ip(request))
    sessao = await auth_svc.criar_sessao_para_usuario(
        pool, usuario["id"],
        user_agent=request.headers.get("user-agent"),
        ip_hash=ip_hash,
    )

    redirect = RedirectResponse(_resolver_redirect_final(request.cookies.get(NEXT_COOKIE)))
    redirect.delete_cookie(STATE_COOKIE)
    redirect.delete_cookie(NEXT_COOKIE)
    _set_session_cookie(redirect, sessao["id"])
    return redirect


# ── Magic Link ──────────────────────────────────────────────────

class MagicLinkRequest(BaseModel):
    email: EmailStr
    next: str | None = None


class MagicLinkVerify(BaseModel):
    token: str


@router.post("/magic-link/request")
async def magic_link_request(dados: MagicLinkRequest, pool=Depends(get_pool)):
    settings = get_settings()
    if not settings.auth_configurado["magic_link"]:
        raise HTTPException(status_code=503, detail="Login por e-mail não está configurado")

    try:
        next_seguro = dados.next if _next_e_seguro(dados.next) else None
        await auth_svc.solicitar_magic_link(pool, dados.email, next_path=next_seguro)
    except Exception:
        # Nunca vaza detalhe de erro técnico pro cliente — só loga.
        # A resposta é sempre a mesma, exista o e-mail ou não, envio
        # tenha funcionado ou não (evita enumeration de e-mails).
        log.error("magic_link_request_erro", exc_info=True)

    return {"mensagem": "Se esse e-mail existir, enviamos um link de acesso."}


@router.post("/magic-link/verify")
async def magic_link_verify(
    dados: MagicLinkVerify,
    request: Request,
    response: Response,
    pool=Depends(get_pool),
):
    try:
        usuario = await auth_svc.verificar_magic_link(pool, dados.token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    ip_hash = hash_ip(get_client_ip(request))
    sessao = await auth_svc.criar_sessao_para_usuario(
        pool, usuario["id"],
        user_agent=request.headers.get("user-agent"),
        ip_hash=ip_hash,
    )
    _set_session_cookie(response, sessao["id"])
    vinculos = await membership_repo.listar_por_usuario(pool, usuario["id"])
    tem_arena = any(v["scope"] == "marca" for v in vinculos)
    return _usuario_publico(usuario, tem_arena)


# ── Sessão ──────────────────────────────────────────────────────

@router.get("/session")
async def obter_sessao(
    usuario: dict | None = Depends(auth_svc.sessao_opcional),
    pool=Depends(get_pool),
):
    if not usuario:
        raise HTTPException(status_code=401, detail="Não autenticado")
    vinculos = await membership_repo.listar_por_usuario(pool, usuario["id"])
    tem_arena = any(v["scope"] == "marca" for v in vinculos)
    return _usuario_publico(usuario, tem_arena)


@router.post("/logout")
async def logout(request: Request, response: Response, pool=Depends(get_pool)):
    settings = get_settings()
    session_id = request.cookies.get(settings.session_cookie_name)
    if session_id:
        await auth_repo.revogar_sessao(pool, session_id)
    response.delete_cookie(settings.session_cookie_name)
    return {"ok": True}
