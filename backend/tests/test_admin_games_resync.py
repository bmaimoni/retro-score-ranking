"""
Testes de POST /api/admin/games/{id}/resync-igdb —
docs/CATALOGO_JOGOS_SPEC.md 8.5.
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from utils.db import get_pool
from middleware.auth import require_admin, AdminContext
import services.igdb as igdb

SUPER_CTX = AdminContext(identificador="admin", user_id=None, super=True)
NAO_SUPER_CTX = AdminContext(
    identificador="pessoa@x.com", user_id="u1", super=False,
    vinculos=[{"arena_id": "m1", "role": "admin"}],
)


def make_uuid():
    return str(uuid.uuid4())


def make_game(**overrides):
    base = {
        "id": make_uuid(), "slug": "street-fighter-ii", "nome": "Street Fighter II",
        "ativo": True, "score_max": None, "pendente_aprovacao": False,
        "criado_em": "2026-01-01", "igdb_id": None,
        "plataforma": None, "ano_lancamento": None, "capa_url": None, "gameplay_url": None,
        "generos": None, "geracoes": None,
    }
    base.update(overrides)
    return base


DETALHE_IGDB = {
    "igdb_id": 3186, "nome": "Street Fighter II", "plataforma": "Arcade",
    "ano_lancamento": 1991, "capa_url": "https://cdn/capa.jpg",
    "generos": ["Fighting"], "geracoes": [3], "resumo": "Um clássico.",
    "desenvolvedora": "Capcom", "publicadora": "Capcom",
    "modos_jogo": ["Multiplayer"], "modos_multiplayer": None, "franquias": ["Street Fighter"],
    "rating_igdb": 90, "classificacoes_etarias": None,
    "screenshot_url": "https://cdn/screenshot.jpg",
    "palavras_chave": ["fighting"], "nomes_alternativos": None,
}


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.pop(get_pool, None)
    app.dependency_overrides.pop(require_admin, None)


@pytest.mark.asyncio
async def test_resync_nao_super_retorna_403(client):
    app.dependency_overrides[require_admin] = lambda: NAO_SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post(f"/api/admin/games/{make_uuid()}/resync-igdb", json={})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_resync_game_inexistente_retorna_404(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.game.buscar_por_id", AsyncMock(return_value=None)):
        resp = await client.post(f"/api/admin/games/{make_uuid()}/resync-igdb", json={})

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_resync_game_ja_ancorado_atualiza_direto_por_id(client):
    """igdb_id já preenchido: busca por ID exato, sem pedir confirmação,
    sobrescreve os campos de origem IGDB (8.5.2)."""
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    game = make_game(igdb_id=3186)
    atualizado = make_game(igdb_id=3186, **{k: v for k, v in DETALHE_IGDB.items() if k != "igdb_id"})

    with patch("repositories.game.buscar_por_id", AsyncMock(return_value=game)), \
         patch("services.igdb.buscar_por_id", AsyncMock(return_value=DETALHE_IGDB)) as buscar_mock, \
         patch("repositories.game.atualizar_de_igdb", AsyncMock(return_value=atualizado)) as atualizar_mock:
        resp = await client.post(f"/api/admin/games/{game['id']}/resync-igdb", json={})

    assert resp.status_code == 200
    buscar_mock.assert_called_once_with(3186)
    atualizar_mock.assert_called_once_with(pool, str(game["id"]), DETALHE_IGDB)


@pytest.mark.asyncio
async def test_resync_game_manual_sem_confirmacao_devolve_candidatos(client):
    """Game sem igdb_id, sem body.igdb_id: não aplica nada, devolve
    candidatos da IGDB por nome pro super escolher (8.5.3)."""
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    game = make_game(nome="Fighter's History", igdb_id=None)
    candidatos = [{"igdb_id": 111, "nome": "Fighter's History", "plataforma": "SNES"}]

    with patch("repositories.game.buscar_por_id", AsyncMock(return_value=game)), \
         patch("services.igdb.buscar", AsyncMock(return_value=candidatos)) as buscar_mock, \
         patch("repositories.game.atualizar_de_igdb", AsyncMock()) as atualizar_mock:
        resp = await client.post(f"/api/admin/games/{game['id']}/resync-igdb", json={})

    assert resp.status_code == 200
    assert resp.json() == {"candidatos": candidatos}
    buscar_mock.assert_called_once_with("Fighter's History", limite=5)
    atualizar_mock.assert_not_called()


@pytest.mark.asyncio
async def test_resync_game_manual_com_igdb_id_confirmado_aplica(client):
    """Segunda chamada, agora com body.igdb_id (super escolheu o
    candidato certo): aplica o resync normalmente."""
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    game = make_game(nome="Fighter's History", igdb_id=None)
    detalhe = {**DETALHE_IGDB, "igdb_id": 111, "nome": "Fighter's History"}

    with patch("repositories.game.buscar_por_id", AsyncMock(return_value=game)), \
         patch("repositories.game.buscar_por_igdb_id", AsyncMock(return_value=None)), \
         patch("services.igdb.buscar_por_id", AsyncMock(return_value=detalhe)), \
         patch("repositories.game.atualizar_de_igdb", AsyncMock(return_value={**game, **detalhe})) as atualizar_mock:
        resp = await client.post(
            f"/api/admin/games/{game['id']}/resync-igdb", json={"igdb_id": 111},
        )

    assert resp.status_code == 200
    atualizar_mock.assert_called_once_with(pool, str(game["id"]), detalhe)


@pytest.mark.asyncio
async def test_resync_game_manual_igdb_id_ja_usado_por_outro_retorna_409(client):
    """Confirmar um igdb_id que já ancora outro game do catálogo não
    pode duplicar a fonte externa (mesma dedup estrutural da criação,
    5.1, aplicada aqui — 8.5.3)."""
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    game = make_game(nome="Fighter's History", igdb_id=None)
    outro_game = make_game(nome="Outro Jogo Já Cadastrado", igdb_id=111)

    with patch("repositories.game.buscar_por_id", AsyncMock(return_value=game)), \
         patch("repositories.game.buscar_por_igdb_id", AsyncMock(return_value=outro_game)), \
         patch("services.igdb.buscar_por_id", AsyncMock()) as buscar_detalhe_mock:
        resp = await client.post(
            f"/api/admin/games/{game['id']}/resync-igdb", json={"igdb_id": 111},
        )

    assert resp.status_code == 409
    assert "Outro Jogo Já Cadastrado" in resp.json()["detail"]
    buscar_detalhe_mock.assert_not_called()


@pytest.mark.asyncio
async def test_resync_igdb_indisponivel_retorna_503(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    game = make_game(igdb_id=3186)
    with patch("repositories.game.buscar_por_id", AsyncMock(return_value=game)), \
         patch("services.igdb.buscar_por_id", AsyncMock(side_effect=igdb.IGDBIndisponivel("timeout"))):
        resp = await client.post(f"/api/admin/games/{game['id']}/resync-igdb", json={})

    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_resync_igdb_id_removido_na_igdb_retorna_404(client):
    """buscar_por_id devolve None (jogo removido/mesclado lá) — não é o
    mesmo 404 de 'game não existe no nosso catálogo'."""
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    game = make_game(igdb_id=3186)
    with patch("repositories.game.buscar_por_id", AsyncMock(return_value=game)), \
         patch("services.igdb.buscar_por_id", AsyncMock(return_value=None)):
        resp = await client.post(f"/api/admin/games/{game['id']}/resync-igdb", json={})

    assert resp.status_code == 404
