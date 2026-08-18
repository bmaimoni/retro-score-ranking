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
    monkeypatch.setenv("RESEND_API_KEY", "")
    get_settings.cache_clear()

    resp = await client.get("/api/auth/providers")

    assert resp.status_code == 200
    data = resp.json()
    assert data["google"] is True
    assert data["magic_link"] is False


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
         patch("auth.service.criar_sessao_para_usuario", AsyncMock(return_value=sessao)):
        resp = await client.post("/api/auth/magic-link/verify", json={"token": "abc"})

    assert resp.status_code == 200
    assert resp.json()["email"] == usuario["email"]
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
    with patch("auth.service.obter_usuario_da_sessao", AsyncMock(return_value=usuario)):
        resp = await client.get("/api/auth/session")

    assert resp.status_code == 200
    assert resp.json()["id"] == usuario["id"]


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
