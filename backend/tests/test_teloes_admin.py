"""
Testes do router admin de telões — /api/admin/teloes.
Ver docs/EVENTOS_SPEC.md §3: exatamente um entre evento_id/placar_id.
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from utils.db import get_pool
from middleware.auth import require_admin

ADMIN_SECRET = "test-secret"
AUTH_HEADER  = {"Authorization": f"Bearer {ADMIN_SECRET}"}


def make_uuid():
    return str(uuid.uuid4())


def _telao(evento_id=None, placar_id=None):
    if evento_id is None and placar_id is None:
        placar_id = make_uuid()  # default só quando nenhum dos dois foi informado
    return {
        "id": make_uuid(), "nome": "Telão Teste", "slug": "telao-teste", "top_n": 10,
        "evento_id": evento_id, "placar_id": placar_id,
        "criado_em": "2026-01-01T00:00:00",
    }


@pytest.fixture(autouse=True)
def clear_overrides():
    app.dependency_overrides[require_admin] = lambda: ADMIN_SECRET
    yield
    app.dependency_overrides.pop(get_pool, None)
    app.dependency_overrides.pop(require_admin, None)


# ── Validação evento_id XOR placar_id (Pydantic, antes do banco) ─────────────

@pytest.mark.asyncio
async def test_criar_telao_sem_evento_nem_placar_retorna_422(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()
    resp = await client.post("/api/admin/teloes",
        json={"nome": "Telão Órfão", "slug": "telao-orfao"},
        headers=AUTH_HEADER)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_criar_telao_com_evento_e_placar_ao_mesmo_tempo_retorna_422(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()
    resp = await client.post("/api/admin/teloes",
        json={
            "nome": "Telão Ambíguo", "slug": "telao-ambiguo",
            "evento_id": make_uuid(), "placar_id": make_uuid(),
        },
        headers=AUTH_HEADER)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_criar_telao_apontando_pra_evento(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    evento_id = make_uuid()

    with patch("repositories.telao.criar", AsyncMock(return_value=_telao(evento_id=evento_id, placar_id=None))):
        resp = await client.post("/api/admin/teloes",
            json={"nome": "Telão do Evento", "slug": "telao-evento", "evento_id": evento_id},
            headers=AUTH_HEADER)

    assert resp.status_code == 201
    assert resp.json()["evento_id"] == evento_id
    assert resp.json()["placar_id"] is None


@pytest.mark.asyncio
async def test_criar_telao_apontando_pra_placar(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    placar_id = make_uuid()

    with patch("repositories.telao.criar", AsyncMock(return_value=_telao(placar_id=placar_id))):
        resp = await client.post("/api/admin/teloes",
            json={"nome": "Hall da Fama Geral", "slug": "geral", "placar_id": placar_id},
            headers=AUTH_HEADER)

    assert resp.status_code == 201
    assert resp.json()["placar_id"] == placar_id


@pytest.mark.asyncio
async def test_criar_telao_slug_duplicado_retorna_409(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.telao.criar",
               AsyncMock(side_effect=Exception("duplicate key value violates unique constraint"))):
        resp = await client.post("/api/admin/teloes",
            json={"nome": "Dup", "slug": "geral", "placar_id": make_uuid()},
            headers=AUTH_HEADER)

    assert resp.status_code == 409


# ── Atualizar telão ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_atualizar_top_n_do_telao(client):
    telao_id = make_uuid()
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    atualizado = _telao(placar_id=make_uuid())
    atualizado["top_n"] = 20
    with patch("repositories.telao.atualizar", AsyncMock(return_value=atualizado)):
        resp = await client.patch(f"/api/admin/teloes/{telao_id}",
            json={"top_n": 20},
            headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["top_n"] == 20


@pytest.mark.asyncio
async def test_atualizar_telao_inexistente_retorna_404(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.telao.atualizar", AsyncMock(return_value=None)):
        resp = await client.patch(f"/api/admin/teloes/{make_uuid()}",
            json={"top_n": 5},
            headers=AUTH_HEADER)

    assert resp.status_code == 404


# ── Gestão de jogos do telão ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_adicionar_jogo_ao_telao(client):
    telao_id = make_uuid()
    jogo_id  = make_uuid()
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    vinculo = {"telao_id": telao_id, "jogo_id": jogo_id, "ativo": True, "ordem": 0, "criado_em": "2026-01-01"}
    with patch("repositories.telao.adicionar_jogo", AsyncMock(return_value=vinculo)):
        resp = await client.post(f"/api/admin/teloes/{telao_id}/jogos/{jogo_id}",
            headers=AUTH_HEADER)

    assert resp.status_code == 201
    assert resp.json()["ativo"] is True


@pytest.mark.asyncio
async def test_reordenar_jogo_do_telao(client):
    telao_id = make_uuid()
    jogo_id  = make_uuid()
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    vinculo = {"telao_id": telao_id, "jogo_id": jogo_id, "ativo": True, "ordem": 3, "criado_em": "2026-01-01"}
    with patch("repositories.telao.atualizar_jogo", AsyncMock(return_value=vinculo)) as mock:
        resp = await client.patch(f"/api/admin/teloes/{telao_id}/jogos/{jogo_id}",
            json={"ordem": 3},
            headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["ordem"] == 3
    mock.assert_called_once_with(pool, telao_id, jogo_id, {"ordem": 3})


@pytest.mark.asyncio
async def test_desativar_jogo_do_telao_sem_delete(client):
    """Remover jogo do carrossel é ativo=false — telao_jogos tem a coluna
    ativo justamente para isso, sem precisar de DELETE."""
    telao_id = make_uuid()
    jogo_id  = make_uuid()
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    vinculo = {"telao_id": telao_id, "jogo_id": jogo_id, "ativo": False, "ordem": 0, "criado_em": "2026-01-01"}
    with patch("repositories.telao.atualizar_jogo", AsyncMock(return_value=vinculo)):
        resp = await client.patch(f"/api/admin/teloes/{telao_id}/jogos/{jogo_id}",
            json={"ativo": False},
            headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["ativo"] is False


@pytest.mark.asyncio
async def test_vinculo_jogo_telao_inexistente_retorna_404(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.telao.atualizar_jogo", AsyncMock(return_value=None)):
        resp = await client.patch(f"/api/admin/teloes/{make_uuid()}/jogos/{make_uuid()}",
            json={"ativo": False},
            headers=AUTH_HEADER)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_listar_jogos_do_telao(client):
    telao_id = make_uuid()
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    jogos = [
        {"id": make_uuid(), "nome": "Pac-Man", "slug": "pac-man", "ativo": True, "ordem": 0},
        {"id": make_uuid(), "nome": "Galaga",  "slug": "galaga",  "ativo": False, "ordem": 1},
    ]
    with patch("repositories.telao.listar_jogos_do_telao", AsyncMock(return_value=jogos)):
        resp = await client.get(f"/api/admin/teloes/{telao_id}/jogos", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert len(resp.json()) == 2


# ── Listar telões ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_listar_teloes(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.telao.listar_todos", AsyncMock(return_value=[_telao(placar_id=make_uuid())])):
        resp = await client.get("/api/admin/teloes", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_listar_teloes_sem_auth_retorna_401(client):
    app.dependency_overrides.pop(require_admin, None)
    resp = await client.get("/api/admin/teloes")
    assert resp.status_code == 401
