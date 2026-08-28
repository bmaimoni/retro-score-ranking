"""
Testes de auth/router.py — endpoints HTTP de autenticação.
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from utils.db import get_pool
from config import get_settings


def make_uuid():
    return str(uuid.uuid4())


def _usuario():
    return {
        "id": make_uuid(), "email": "pessoa@example.com", "email_verified": True,
        "nome": "Pessoa Teste", "foto_url": "https://foto.example.com/p.jpg",
        "status": "ativo", "criado_em": "2026-01-01", "ultimo_login_em": None,
    }


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.pop(get_pool, None)
    get_settings.cache_clear()


# ── /providers ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_providers_reflete_configuracao(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "abc")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "xyz")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "https://api.example.com/api/auth/google/callback")
    monkeypatch.setenv("RESEND_API_KEY", "")
    get_settings.cache_clear()

    resp = await client.get("/api/auth/providers")

    assert resp.status_code == 200
    data = resp.json()
    assert data["google"] is True
    assert data["magic_link"] is False


@pytest.mark.asyncio
async def test_providers_google_falso_sem_redirect_uri(client, monkeypatch):
    """
    Regressão: client_id e client_secret certos mas sem
    GOOGLE_REDIRECT_URI faz o Google rejeitar com 'Missing required
    parameter: redirect_uri' — providers precisa reportar False nesse
    caso, não True (senão o frontend mostra um botão que quebra).
    """
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "abc")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "xyz")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "")
    get_settings.cache_clear()

    resp = await client.get("/api/auth/providers")

    assert resp.json()["google"] is False


# ── Google OAuth ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_google_start_sem_configuracao_retorna_503(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "")
    get_settings.cache_clear()

    resp = await client.get("/api/auth/google/start", follow_redirects=False)

    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_google_start_configurado_redireciona_e_seta_cookie_state(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "abc")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "xyz")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "https://api.example.com/api/auth/google/callback")
    get_settings.cache_clear()

    resp = await client.get("/api/auth/google/start", follow_redirects=False)

    assert resp.status_code in (302, 307)
    assert "accounts.google.com" in resp.headers["location"]
    assert "oauth_state" in resp.cookies


@pytest.mark.asyncio
async def test_google_start_com_next_seta_cookie_oauth_next(client, monkeypatch):
    """next=/admin.html — pra logar direto do admin.html sem cair na
    tela errada depois do redirect do Google (ver MARCAS_SPEC.md §6)."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "abc")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "xyz")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "https://api.example.com/api/auth/google/callback")
    get_settings.cache_clear()

    resp = await client.get("/api/auth/google/start?next=/admin.html", follow_redirects=False)

    assert resp.status_code in (302, 307)
    assert resp.cookies.get("oauth_next", "").strip('"') == "/admin.html"


@pytest.mark.asyncio
async def test_google_start_sem_next_nao_seta_cookie_oauth_next(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "abc")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "xyz")
    get_settings.cache_clear()

    resp = await client.get("/api/auth/google/start", follow_redirects=False)

    assert "oauth_next" not in resp.cookies


@pytest.mark.asyncio
async def test_google_callback_sem_state_correspondente_retorna_400(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()
    resp = await client.get("/api/auth/google/callback?code=abc&state=nao-bate")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_google_callback_completo_cria_sessao_e_redireciona(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "abc")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "xyz")
    get_settings.cache_clear()

    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario()
    sessao = {"id": make_uuid(), "user_id": usuario["id"], "criado_em": "2026-01-01",
              "expira_em": "2026-02-01", "revogada_em": None}

    perfil_google = {"sub": "google-sub-1", "email": "pessoa@example.com",
                      "email_verified": True, "name": "Pessoa Teste", "picture": None}

    client.cookies.set("oauth_state", "state-123")
    with patch("auth.service.trocar_code_por_perfil_google", AsyncMock(return_value=perfil_google)), \
         patch("auth.service.login_ou_criar_usuario", AsyncMock(return_value=usuario)), \
         patch("auth.service.criar_sessao_para_usuario", AsyncMock(return_value=sessao)):
        resp = await client.get(
            "/api/auth/google/callback?code=abc&state=state-123",
            follow_redirects=False,
        )

    assert resp.status_code in (302, 307)
    assert "canal3_session" in resp.cookies


@pytest.mark.asyncio
async def test_google_callback_com_next_redireciona_pro_next(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "abc")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "xyz")
    monkeypatch.setenv("FRONTEND_BASE_URL", "https://site.example.com")
    get_settings.cache_clear()

    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario()
    sessao = {"id": make_uuid(), "user_id": usuario["id"], "criado_em": "2026-01-01",
              "expira_em": "2026-02-01", "revogada_em": None}
    perfil_google = {"sub": "google-sub-1", "email": "pessoa@example.com",
                      "email_verified": True, "name": "Pessoa Teste", "picture": None}

    client.cookies.set("oauth_state", "state-123")
    client.cookies.set("oauth_next", "/admin.html")
    with patch("auth.service.trocar_code_por_perfil_google", AsyncMock(return_value=perfil_google)), \
         patch("auth.service.login_ou_criar_usuario", AsyncMock(return_value=usuario)), \
         patch("auth.service.criar_sessao_para_usuario", AsyncMock(return_value=sessao)):
        resp = await client.get(
            "/api/auth/google/callback?code=abc&state=state-123",
            follow_redirects=False,
        )

    assert resp.headers["location"] == "https://site.example.com/admin.html"


@pytest.mark.asyncio
async def test_google_callback_com_next_malicioso_ignora_e_usa_default(client, monkeypatch):
    """
    next apontando pra fora do site (URL absoluta ou // protocolo-
    relativo) é ignorado — nunca vira open redirect. Mesmo se alguém
    conseguisse forjar o cookie oauth_next manualmente.
    """
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "abc")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "xyz")
    monkeypatch.setenv("FRONTEND_BASE_URL", "https://site.example.com")
    get_settings.cache_clear()

    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario()
    sessao = {"id": make_uuid(), "user_id": usuario["id"], "criado_em": "2026-01-01",
              "expira_em": "2026-02-01", "revogada_em": None}
    perfil_google = {"sub": "google-sub-1", "email": "pessoa@example.com",
                      "email_verified": True, "name": "Pessoa Teste", "picture": None}

    client.cookies.set("oauth_state", "state-123")
    client.cookies.set("oauth_next", "//evil.com/phishing")
    with patch("auth.service.trocar_code_por_perfil_google", AsyncMock(return_value=perfil_google)), \
         patch("auth.service.login_ou_criar_usuario", AsyncMock(return_value=usuario)), \
         patch("auth.service.criar_sessao_para_usuario", AsyncMock(return_value=sessao)):
        resp = await client.get(
            "/api/auth/google/callback?code=abc&state=state-123",
            follow_redirects=False,
        )

    assert resp.headers["location"] == "https://site.example.com"
    assert "evil.com" not in resp.headers["location"]


# ── Magic Link ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_magic_link_request_sem_configuracao_retorna_503(client, monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "")
    get_settings.cache_clear()
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/auth/magic-link/request", json={"email": "a@b.com"})
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_magic_link_request_configurado_retorna_mensagem_generica(client, monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_123")
    get_settings.cache_clear()
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("auth.service.solicitar_magic_link", AsyncMock()):
        resp = await client.post("/api/auth/magic-link/request", json={"email": "a@b.com"})

    assert resp.status_code == 200
    assert "existir" in resp.json()["mensagem"]


@pytest.mark.asyncio
async def test_magic_link_request_repassa_next_valido(client, monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_123")
    get_settings.cache_clear()
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    solicitar_mock = AsyncMock()

    with patch("auth.service.solicitar_magic_link", solicitar_mock):
        await client.post("/api/auth/magic-link/request",
            json={"email": "a@b.com", "next": "/admin.html"})

    solicitar_mock.assert_called_once_with(pool, "a@b.com", next_path="/admin.html")


@pytest.mark.asyncio
async def test_magic_link_request_next_malicioso_e_ignorado(client, monkeypatch):
    """next fora do site (URL absoluta) nunca chega no service — mesma
    defesa contra open redirect do fluxo Google."""
    monkeypatch.setenv("RESEND_API_KEY", "re_123")
    get_settings.cache_clear()
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    solicitar_mock = AsyncMock()

    with patch("auth.service.solicitar_magic_link", solicitar_mock):
        await client.post("/api/auth/magic-link/request",
            json={"email": "a@b.com", "next": "https://evil.com/phishing"})

    solicitar_mock.assert_called_once_with(pool, "a@b.com", next_path=None)


@pytest.mark.asyncio
async def test_magic_link_request_email_invalido_retorna_422(client, monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_123")
    get_settings.cache_clear()
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/auth/magic-link/request", json={"email": "nao-e-email"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_magic_link_request_erro_de_envio_nao_vaza_pro_cliente(client, monkeypatch):
    """
    Mesmo se o envio falhar (Resend fora do ar, domínio não verificado
    etc.), a resposta pro cliente continua a mensagem genérica — nunca
    expõe detalhe técnico nem confirma/nega existência do e-mail.
    """
    monkeypatch.setenv("RESEND_API_KEY", "re_123")
    get_settings.cache_clear()
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("auth.service.solicitar_magic_link", AsyncMock(side_effect=RuntimeError("falha no envio"))):
        resp = await client.post("/api/auth/magic-link/request", json={"email": "a@b.com"})

    assert resp.status_code == 200
    assert "existir" in resp.json()["mensagem"]


@pytest.mark.asyncio
async def test_magic_link_verify_token_invalido_retorna_400(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("auth.service.verificar_magic_link", AsyncMock(side_effect=ValueError("Link inválido, expirado ou já utilizado"))):
        resp = await client.post("/api/auth/magic-link/verify", json={"token": "abc"})

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_magic_link_verify_valido_cria_sessao(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario()
    sessao = {"id": make_uuid(), "user_id": usuario["id"], "criado_em": "2026-01-01",
              "expira_em": "2026-02-01", "revogada_em": None}

    with patch("auth.service.verificar_magic_link", AsyncMock(return_value=usuario)), \
         patch("auth.service.criar_sessao_para_usuario", AsyncMock(return_value=sessao)), \
         patch("repositories.membership.listar_por_usuario", AsyncMock(return_value=[])):
        resp = await client.post("/api/auth/magic-link/verify", json={"token": "abc"})

    assert resp.status_code == 200
    assert resp.json()["email"] == usuario["email"]
    assert resp.json()["tem_arena"] is False
    assert "canal3_session" in resp.cookies
    # Nunca expõe campos internos (email_verified, status)
    assert "email_verified" not in resp.json()
    assert "status" not in resp.json()


# ── Sessão ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_session_sem_cookie_retorna_401(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()
    resp = await client.get("/api/auth/session")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_session_com_cookie_valido_retorna_usuario(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario()

    client.cookies.set("canal3_session", "sessao-valida")
    with patch("auth.service.obter_usuario_da_sessao", AsyncMock(return_value=usuario)), \
         patch("repositories.membership.listar_por_usuario", AsyncMock(return_value=[])):
        resp = await client.get("/api/auth/session")

    assert resp.status_code == 200
    assert resp.json()["id"] == usuario["id"]
    assert resp.json()["tem_arena"] is False


@pytest.mark.asyncio
async def test_session_com_vinculo_marca_retorna_tem_arena_true(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario()

    client.cookies.set("canal3_session", "sessao-valida")
    vinculo = {"scope": "marca", "arena_id": make_uuid(), "role": "admin"}
    with patch("auth.service.obter_usuario_da_sessao", AsyncMock(return_value=usuario)), \
         patch("repositories.membership.listar_por_usuario", AsyncMock(return_value=[vinculo])):
        resp = await client.get("/api/auth/session")

    assert resp.status_code == 200
    assert resp.json()["tem_arena"] is True


@pytest.mark.asyncio
async def test_session_com_cookie_expirado_retorna_401(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    client.cookies.set("canal3_session", "sessao-expirada")
    with patch("auth.service.obter_usuario_da_sessao", AsyncMock(return_value=None)):
        resp = await client.get("/api/auth/session")

    assert resp.status_code == 401


# ── Logout ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_logout_revoga_sessao_e_limpa_cookie(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    client.cookies.set("canal3_session", "sessao-ativa")
    with patch("auth.repository.revogar_sessao", AsyncMock()) as revogar_mock:
        resp = await client.post("/api/auth/logout")

    assert resp.status_code == 200
    revogar_mock.assert_called_once()


@pytest.mark.asyncio
async def test_logout_sem_sessao_nao_falha(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    resp = await client.post("/api/auth/logout")
    assert resp.status_code == 200
