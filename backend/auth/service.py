"""
Serviço de autenticação — lógica de login Google, Magic Link, sessão
e reivindicação de nick. Sem HTTP aqui (isso fica em auth/router.py).

Ver docs/AUTH_SPEC.md §4 para os fluxos completos.
"""
import hashlib
import secrets
import urllib.parse
import httpx
import structlog
from fastapi import Depends, HTTPException, Request

from config import get_settings
from utils.db import get_pool
import auth.repository as auth_repo

log = structlog.get_logger()

GOOGLE_AUTH_URL     = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL    = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


class NickJaReivindicadoError(Exception):
    """Nick pertence a outra conta — quem está enviando não é o dono."""


def normalizar_email(email: str) -> str:
    return email.strip().lower()


# ── Google OAuth ──────────────────────────────────────────────────

def gerar_url_autorizacao_google(state: str) -> str:
    settings = get_settings()
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"


async def trocar_code_por_perfil_google(code: str) -> dict:
    """
    Troca o authorization code pelo access_token, depois busca o
    perfil no endpoint userinfo do Google. Usar o userinfo (em vez de
    decodificar o id_token manualmente) evita precisar validar
    assinatura JWT na mão — se o token fosse inválido/expirado, a
    chamada ao userinfo já falha sozinha.

    Retorna: {sub, email, email_verified, name, picture, ...}
    """
    settings = get_settings()
    async with httpx.AsyncClient(timeout=10) as client:
        token_resp = await client.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_redirect_uri,
            "grant_type": "authorization_code",
        })
        token_resp.raise_for_status()
        access_token = token_resp.json()["access_token"]

        userinfo_resp = await client.get(GOOGLE_USERINFO_URL, headers={
            "Authorization": f"Bearer {access_token}",
        })
        userinfo_resp.raise_for_status()
        return userinfo_resp.json()


# ── Account linking (AUTH_SPEC.md §4.1, decisão #2) ──────────────

async def login_ou_criar_usuario(
    pool,
    provider: str,
    provider_user_id: str,
    email: str,
    email_verified: bool,
    nome: str | None = None,
    foto_url: str | None = None,
) -> dict:
    """
    1. Já existe identity pra esse provider+provider_user_id? -> usa
       direto o user_id dela.
    2. Senão, e-mail verificado + já existe user com esse e-mail? ->
       linka automaticamente a nova identity a essa conta (decisão #2:
       account linking automático, só com email_verified=true).
    3. Senão: cria usuário novo.
    """
    email = normalizar_email(email) if email else email

    identity = await auth_repo.buscar_identity(pool, provider, provider_user_id)
    if identity:
        usuario = await auth_repo.buscar_usuario_por_id(pool, identity["user_id"])
        await auth_repo.atualizar_ultimo_login(pool, usuario["id"])
        return usuario

    usuario_existente = None
    if email_verified and email:
        usuario_existente = await auth_repo.buscar_usuario_por_email(pool, email)

    if usuario_existente:
        await auth_repo.criar_identity(pool, usuario_existente["id"], provider, provider_user_id, email)
        await auth_repo.atualizar_ultimo_login(pool, usuario_existente["id"])
        log.info("auth_conta_linkada", user_id=usuario_existente["id"], provider=provider)
        return usuario_existente

    novo_usuario = await auth_repo.criar_usuario(pool, email, email_verified, nome, foto_url)
    await auth_repo.criar_identity(pool, novo_usuario["id"], provider, provider_user_id, email)
    log.info("auth_conta_criada", user_id=novo_usuario["id"], provider=provider)
    return novo_usuario


# ── Magic Link ────────────────────────────────────────────────────

def gerar_token_magic_link() -> tuple[str, str]:
    """Retorna (token_texto_puro, token_hash) — só o hash vai pro banco."""
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    return token, token_hash


async def solicitar_magic_link(pool, email: str, next_path: str | None = None) -> None:
    """
    next_path: caminho relativo pra onde login.html deve mandar a pessoa
    de volta depois de validar o token (ex.: '/admin.html'). Validação
    de segurança (só relativo, nunca URL absoluta) fica no router, não
    aqui — este service só concatena o que já chegou validado.
    """
    settings = get_settings()
    email = normalizar_email(email)
    token, token_hash = gerar_token_magic_link()
    await auth_repo.criar_magic_link_token(pool, email, token_hash, settings.magic_link_ttl_minutes)

    link = f"{settings.frontend_base_url}/login.html?token={token}"
    if next_path:
        link += f"&next={urllib.parse.quote(next_path, safe='')}"
    await _enviar_email_magic_link(email, link)


async def _enviar_email_magic_link(email: str, link: str) -> None:
    settings = get_settings()
    if not settings.resend_api_key:
        log.warning("magic_link_sem_resend_configurado", email=email)
        raise RuntimeError("Envio de e-mail não configurado (RESEND_API_KEY ausente)")

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.resend_from_email,
                "to": [email],
                "subject": "Seu link de acesso — Canal3",
                "html": (
                    f"<p>Clique no link abaixo para entrar:</p>"
                    f'<p><a href="{link}">{link}</a></p>'
                    f"<p>Este link expira em {settings.magic_link_ttl_minutes} minutos "
                    f"e só pode ser usado uma vez.</p>"
                ),
            },
        )
        resp.raise_for_status()


async def verificar_magic_link(pool, token: str) -> dict:
    """
    Valida o token (comparando o hash no banco), marca como usado, e
    faz login/cria conta. O e-mail do magic link é considerado
    verificado pelo próprio ato de clicar (a pessoa provou acesso à
    caixa de entrada) — ver AUTH_SPEC.md §4.2.
    """
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    registro = await auth_repo.buscar_magic_link_token_valido(pool, token_hash)
    if not registro:
        raise ValueError("Link inválido, expirado ou já utilizado")

    await auth_repo.marcar_magic_link_usado(pool, registro["id"])

    return await login_ou_criar_usuario(
        pool,
        provider="magic_link",
        provider_user_id=registro["email"],
        email=registro["email"],
        email_verified=True,
    )


# ── Sessão ────────────────────────────────────────────────────────

async def criar_sessao_para_usuario(
    pool, user_id: str, user_agent: str | None = None, ip_hash: str | None = None
) -> dict:
    settings = get_settings()
    return await auth_repo.criar_sessao(pool, user_id, settings.session_ttl_days, user_agent, ip_hash)


async def obter_usuario_da_sessao(pool, session_id: str) -> dict | None:
    """
    Valida a sessão (existe, não expirada, não revogada), renova o TTL
    (sliding — AUTH_SPEC.md §5) e retorna o usuário. None se inválida.
    """
    settings = get_settings()
    sessao = await auth_repo.buscar_sessao_ativa(pool, session_id)
    if not sessao:
        return None
    await auth_repo.renovar_sessao(pool, session_id, settings.session_ttl_days)
    return await auth_repo.buscar_usuario_por_id(pool, sessao["user_id"])


async def sessao_opcional(request: Request, pool=Depends(get_pool)) -> dict | None:
    """
    Dependency FastAPI pra rotas onde login é opcional (ex.: upload de
    score — AUTH_SPEC.md §4.3). Nunca levanta erro: retorna o usuário
    se houver cookie de sessão válido, ou None.
    """
    settings = get_settings()
    session_id = request.cookies.get(settings.session_cookie_name)
    if not session_id:
        return None
    return await obter_usuario_da_sessao(pool, session_id)


async def sessao_obrigatoria(usuario: dict | None = Depends(sessao_opcional)) -> dict:
    """Dependency FastAPI pra rotas onde login é obrigatório (perfil,
    exclusão de conta) — 401 sem sessão válida."""
    if not usuario:
        raise HTTPException(status_code=401, detail="Autenticação necessária")
    return usuario


# ── Reivindicação de nick (AUTH_SPEC.md §3, §4.3) ──────────────────

async def verificar_e_reivindicar_nick(pool, nick_norm: str, user_id: str | None) -> None:
    """
    Modelo de claim, escopo plataforma inteira:
      - Sem sessão (user_id=None): bloqueia só se o nick já tiver dono.
        Nicks livres continuam funcionando exatamente como antes de a
        autenticação existir.
      - Com sessão: nick livre -> reivindica pro user_id atual.
                    nick já é do user_id atual -> segue normal.
                    nick é de outro usuário -> bloqueia (409).
    """
    claim = await auth_repo.buscar_nick_claim(pool, nick_norm)

    if user_id is None:
        if claim:
            raise NickJaReivindicadoError(
                "Esse nick já tem dono — faça login para usá-lo, ou escolha outro."
            )
        return

    if claim is None:
        await auth_repo.criar_nick_claim(pool, nick_norm, user_id)
        return

    if claim["user_id"] != user_id:
        raise NickJaReivindicadoError(
            "Esse nick já tem dono — faça login com a conta certa, ou escolha outro nick."
        )
    # claim["user_id"] == user_id -> já é do próprio usuário, segue normal
