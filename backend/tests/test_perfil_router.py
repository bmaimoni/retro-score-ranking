"""
Testes de routers/perfil.py — exige sessão de visitante logado (não admin).
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from utils.db import get_pool
import auth.service as auth_svc

SESSION_COOKIE = "canal3_session"


def make_uuid():
    return str(uuid.uuid4())


def _usuario_sessao(user_id=None):
    return {"id": user_id or make_uuid(), "email": "p@x.com", "nome": "Pessoa"}


def _perfil(**overrides):
    base = {
        "id": make_uuid(), "email": "p@x.com", "nome": "Pessoa", "foto_url": None,
        "status": "ativo", "nome_completo": None, "data_nascimento": None,
        "cidade": None, "estado": None, "telefone": None, "avatar_id": None,
        "criado_em": "2026-01-01T00:00:00", "ultimo_login_em": None,
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.pop(get_pool, None)


# ── GET /api/perfil ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ver_perfil_sem_sessao_retorna_401(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()
    resp = await client.get("/api/perfil")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_ver_perfil_com_sessao(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario_sessao()
    perfil = _perfil(id=usuario["id"])
    claim = {"id": make_uuid(), "nick": "Campeao", "nick_norm": "campeao", "user_id": usuario["id"], "ativo": True, "criado_em": "2026-01-01"}

    client.cookies.set(SESSION_COOKIE, "sessao-valida")
    with patch("auth.service.obter_usuario_da_sessao", AsyncMock(return_value=usuario)), \
         patch("repositories.usuario.buscar_perfil", AsyncMock(return_value=perfil)), \
         patch("auth.repository.buscar_claim_ativo_do_usuario", AsyncMock(return_value=claim)):
        resp = await client.get("/api/perfil")

    assert resp.status_code == 200
    assert resp.json()["id"] == usuario["id"]
    assert resp.json()["nick_atual"] == "Campeao"


@pytest.mark.asyncio
async def test_ver_perfil_sem_nick_reivindicado(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario_sessao()
    perfil = _perfil(id=usuario["id"])

    client.cookies.set(SESSION_COOKIE, "sessao-valida")
    with patch("auth.service.obter_usuario_da_sessao", AsyncMock(return_value=usuario)), \
         patch("repositories.usuario.buscar_perfil", AsyncMock(return_value=perfil)), \
         patch("auth.repository.buscar_claim_ativo_do_usuario", AsyncMock(return_value=None)):
        resp = await client.get("/api/perfil")

    assert resp.status_code == 200
    assert resp.json()["nick_atual"] is None


# ── PATCH /api/perfil ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_atualizar_perfil_sem_sessao_retorna_401(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()
    resp = await client.patch("/api/perfil", json={"cidade": "São Paulo"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_atualizar_perfil_campos_basicos(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario_sessao()
    perfil_atualizado = _perfil(id=usuario["id"], cidade="São Paulo", estado="SP")

    client.cookies.set(SESSION_COOKIE, "sessao-valida")
    with patch("auth.service.obter_usuario_da_sessao", AsyncMock(return_value=usuario)), \
         patch("repositories.usuario.atualizar_perfil", AsyncMock(return_value=perfil_atualizado)) as mock:
        resp = await client.patch("/api/perfil", json={"cidade": "São Paulo", "estado": "SP"})

    assert resp.status_code == 200
    assert resp.json()["cidade"] == "São Paulo"
    mock.assert_called_once_with(pool, usuario["id"], {"cidade": "São Paulo", "estado": "SP"})


@pytest.mark.asyncio
async def test_atualizar_perfil_com_avatar_valido(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario_sessao()
    avatar_id = make_uuid()
    avatar = {"id": avatar_id, "nome": "Robô", "url": "https://cdn/robo.png", "ativo": True, "criado_em": "2026-01-01"}
    perfil_atualizado = _perfil(id=usuario["id"], avatar_id=avatar_id)

    client.cookies.set(SESSION_COOKIE, "sessao-valida")
    with patch("auth.service.obter_usuario_da_sessao", AsyncMock(return_value=usuario)), \
         patch("repositories.avatar.buscar_por_id", AsyncMock(return_value=avatar)), \
         patch("repositories.usuario.atualizar_perfil", AsyncMock(return_value=perfil_atualizado)):
        resp = await client.patch("/api/perfil", json={"avatar_id": avatar_id})

    assert resp.status_code == 200
    assert resp.json()["avatar_id"] == avatar_id


@pytest.mark.asyncio
async def test_atualizar_perfil_com_avatar_inexistente_retorna_422(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario_sessao()

    client.cookies.set(SESSION_COOKIE, "sessao-valida")
    with patch("auth.service.obter_usuario_da_sessao", AsyncMock(return_value=usuario)), \
         patch("repositories.avatar.buscar_por_id", AsyncMock(return_value=None)):
        resp = await client.patch("/api/perfil", json={"avatar_id": make_uuid()})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_atualizar_perfil_com_avatar_desativado_retorna_422(client):
    """Avatar desativado não pode ser escolhido dali pra frente — quem
    já tinha continua com ele (não mexe no que já está setado)."""
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario_sessao()
    avatar_id = make_uuid()
    avatar_inativo = {"id": avatar_id, "nome": "Robô", "url": "https://cdn/robo.png", "ativo": False, "criado_em": "2026-01-01"}

    client.cookies.set(SESSION_COOKIE, "sessao-valida")
    with patch("auth.service.obter_usuario_da_sessao", AsyncMock(return_value=usuario)), \
         patch("repositories.avatar.buscar_por_id", AsyncMock(return_value=avatar_inativo)):
        resp = await client.patch("/api/perfil", json={"avatar_id": avatar_id})

    assert resp.status_code == 422


# ── POST /api/perfil/nick — troca deliberada (NICKNAME_SPEC.md) ────────────────

@pytest.mark.asyncio
async def test_trocar_nick_sem_sessao_retorna_401(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()
    resp = await client.post("/api/perfil/nick", json={"nick": "NovoNick"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_trocar_nick_sucesso(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario_sessao()
    nova_claim = {"id": make_uuid(), "nick": "NovoNick", "nick_norm": "novonick", "user_id": usuario["id"], "ativo": True, "criado_em": "2026-01-01"}

    client.cookies.set(SESSION_COOKIE, "sessao-valida")
    with patch("auth.service.obter_usuario_da_sessao", AsyncMock(return_value=usuario)), \
         patch("auth.service.trocar_nick", AsyncMock(return_value=nova_claim)) as trocar_mock:
        resp = await client.post("/api/perfil/nick", json={"nick": "NovoNick"})

    assert resp.status_code == 201
    assert resp.json()["nick"] == "NovoNick"
    trocar_mock.assert_called_once_with(pool, usuario["id"], "NovoNick")


@pytest.mark.asyncio
async def test_trocar_nick_em_cooldown_retorna_429(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario_sessao()

    client.cookies.set(SESSION_COOKIE, "sessao-valida")
    with patch("auth.service.obter_usuario_da_sessao", AsyncMock(return_value=usuario)), \
         patch("auth.service.trocar_nick", AsyncMock(side_effect=auth_svc.NickTrocaEmCooldownError("cooldown"))):
        resp = await client.post("/api/perfil/nick", json={"nick": "NovoNick"})

    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_trocar_nick_colisao_retorna_409(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario_sessao()

    client.cookies.set(SESSION_COOKIE, "sessao-valida")
    with patch("auth.service.obter_usuario_da_sessao", AsyncMock(return_value=usuario)), \
         patch("auth.service.trocar_nick", AsyncMock(side_effect=auth_svc.NickJaReivindicadoError("já tem dono"))):
        resp = await client.post("/api/perfil/nick", json={"nick": "Ocupado"})

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_trocar_nick_vazio_retorna_422(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()
    usuario = _usuario_sessao()

    client.cookies.set(SESSION_COOKIE, "sessao-valida")
    with patch("auth.service.obter_usuario_da_sessao", AsyncMock(return_value=usuario)):
        resp = await client.post("/api/perfil/nick", json={"nick": "   "})

    assert resp.status_code == 422


# ── GET /api/perfil/pontuacoes ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_minhas_pontuacoes_sem_sessao_retorna_401(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()
    resp = await client.get("/api/perfil/pontuacoes")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_minhas_pontuacoes_sucesso(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario_sessao()
    pontuacoes = [{"id": "e1", "nick": "Campeao", "pontuacao": 5000, "jogo_nome": "Pac-Man", "marca_nome": "Canal3"}]

    client.cookies.set(SESSION_COOKIE, "sessao-valida")
    with patch("auth.service.obter_usuario_da_sessao", AsyncMock(return_value=usuario)), \
         patch("repositories.entrada.listar_por_usuario", AsyncMock(return_value=pontuacoes)) as mock:
        resp = await client.get("/api/perfil/pontuacoes")

    assert resp.status_code == 200
    assert len(resp.json()) == 1
    mock.assert_called_once_with(pool, usuario["id"])


# ── POST /api/perfil/desativar-pontuacoes ───────────────────────────────────────

@pytest.mark.asyncio
async def test_desativar_pontuacoes_sem_sessao_retorna_401(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()
    resp = await client.post("/api/perfil/desativar-pontuacoes")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_desativar_pontuacoes_sucesso(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario_sessao()

    client.cookies.set(SESSION_COOKIE, "sessao-valida")
    with patch("auth.service.obter_usuario_da_sessao", AsyncMock(return_value=usuario)), \
         patch("repositories.usuario.desativar_pontuacoes", AsyncMock(return_value=3)) as mock:
        resp = await client.post("/api/perfil/desativar-pontuacoes")

    assert resp.status_code == 200
    assert resp.json()["total_afetadas"] == 3
    mock.assert_called_once_with(pool, usuario["id"], usuario["email"])


# ── POST /api/perfil/exclusao ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_solicitar_exclusao_sem_sessao_retorna_401(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()
    resp = await client.post("/api/perfil/exclusao")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_solicitar_exclusao_sucesso(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario_sessao()
    resultado = {"id": usuario["id"], "exclusao_solicitada_em": "2026-01-01T00:00:00"}

    client.cookies.set(SESSION_COOKIE, "sessao-valida")
    with patch("auth.service.obter_usuario_da_sessao", AsyncMock(return_value=usuario)), \
         patch("services.exclusao_conta.solicitar", AsyncMock(return_value=resultado)):
        resp = await client.post("/api/perfil/exclusao")

    assert resp.status_code == 201
    assert resp.json()["exclusao_solicitada_em"] is not None


@pytest.mark.asyncio
async def test_solicitar_exclusao_bloqueada_por_titularidade_retorna_409(client):
    import services.exclusao_conta as exclusao_svc
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario_sessao()

    client.cookies.set(SESSION_COOKIE, "sessao-valida")
    with patch("auth.service.obter_usuario_da_sessao", AsyncMock(return_value=usuario)), \
         patch("services.exclusao_conta.solicitar",
               AsyncMock(side_effect=exclusao_svc.ExclusaoBloqueadaTitularidadeError([{"id": "m1", "nome": "Canal3"}]))):
        resp = await client.post("/api/perfil/exclusao")

    assert resp.status_code == 409
    assert "Canal3" in resp.json()["detail"]


# ── POST /api/perfil/exclusao/cancelar ───────────────────────────────────────

@pytest.mark.asyncio
async def test_cancelar_exclusao_sucesso(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario_sessao()
    resultado = {"id": usuario["id"], "exclusao_solicitada_em": None}

    client.cookies.set(SESSION_COOKIE, "sessao-valida")
    with patch("auth.service.obter_usuario_da_sessao", AsyncMock(return_value=usuario)), \
         patch("services.exclusao_conta.cancelar", AsyncMock(return_value=resultado)):
        resp = await client.post("/api/perfil/exclusao/cancelar")

    assert resp.status_code == 200
    assert resp.json()["exclusao_solicitada_em"] is None


@pytest.mark.asyncio
async def test_cancelar_exclusao_sem_pendencia_retorna_404(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario_sessao()

    client.cookies.set(SESSION_COOKIE, "sessao-valida")
    with patch("auth.service.obter_usuario_da_sessao", AsyncMock(return_value=usuario)), \
         patch("services.exclusao_conta.cancelar", AsyncMock(return_value=None)):
        resp = await client.post("/api/perfil/exclusao/cancelar")

    assert resp.status_code == 404
