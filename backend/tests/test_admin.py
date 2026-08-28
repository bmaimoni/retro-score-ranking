import uuid
import pytest
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from utils.db import get_pool
from middleware.auth import require_admin, AdminContext
import auth.service as auth_svc

ADMIN_SECRET = "test-secret-123"
AUTH_HEADER  = {"Authorization": f"Bearer {ADMIN_SECRET}"}
ADMIN_CTX    = AdminContext(identificador="admin", user_id=None, super=True)

# Kwargs de filtro do feed quando nenhum filtro novo (BACKLOG_2026.md §4.1/4.4)
# foi passado na query string — reaproveitado pelos testes de paginação/escopo
# que não são sobre esses filtros especificamente.
FILTROS_FEED_VAZIOS = dict(
    status=None, data_de=None, data_ate=None, game_id=None,
    sem_foto=False, sem_identificacao=False, busca=None,
)


def make_uuid():
    return str(uuid.uuid4())


def make_entry(nick="PLAYER1", pontuacao=50000, game_id=None,
                 no_ranking=True, pendente=False,
                 foto_url="https://cdn.example.com/foto.jpg"):
    return {
        "id": make_uuid(), "game_id": game_id or make_uuid(),
        "nick": nick, "nick_norm": nick.lower().strip(),
        "pontuacao": pontuacao, "foto_url": foto_url,
        "no_ranking": no_ranking, "superado": False, "pendente": pendente,
        "ip_hash": "abc123", "criado_em": "2024-01-01T00:00:00Z",
        "moderado_em": None, "moderado_por": None,
    }


def make_game(pendente_aprovacao=False):
    return {"id": make_uuid(), "slug": "pac-man", "nome": "Pac-Man",
            "score_max": 999990, "ativo": True, "pendente_aprovacao": pendente_aprovacao,
            "criado_por": None, "criado_em": "2026-01-01"}


def _pool_com_slug(slug="pac-man"):
    """Pool mock que responde o slug do game quando consultado."""
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value={"slug": slug})
    pool.fetch    = AsyncMock(return_value=[])
    return pool


@pytest.fixture(autouse=True)
def override_auth():
    """Substitui autenticação via dependency_overrides."""
    app.dependency_overrides[require_admin] = lambda: ADMIN_CTX
    yield
    app.dependency_overrides.pop(require_admin, None)


@pytest.fixture(autouse=True)
def clear_pool_override():
    """Garante limpeza do override do pool após cada teste."""
    yield
    app.dependency_overrides.pop(get_pool, None)


# ── Auth ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sem_token_retorna_401(client):
    """Sem override de auth, deve retornar 401."""
    app.dependency_overrides.pop(require_admin, None)
    resp = await client.get("/api/admin/feed")
    assert resp.status_code == 401
    # Restaura para os outros testes
    app.dependency_overrides[require_admin] = lambda: ADMIN_CTX


@pytest.mark.asyncio
async def test_token_errado_retorna_401(client):
    app.dependency_overrides.pop(require_admin, None)
    resp = await client.get("/api/admin/feed",
                            headers={"Authorization": "Bearer errado"})
    assert resp.status_code == 401
    app.dependency_overrides[require_admin] = lambda: ADMIN_CTX


@pytest.mark.asyncio
async def test_token_correto_retorna_200(client):
    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=[])
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.entry.listar_feed_admin", AsyncMock(return_value=[])), \
         patch("repositories.entry.contar_feed_admin",  AsyncMock(return_value=0)):
        resp = await client.get("/api/admin/feed", headers=AUTH_HEADER)
    assert resp.status_code == 200


# ── Moderação ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ocultar_entry(client):
    game_id = make_uuid()
    entry = make_entry(game_id=game_id, no_ranking=True)
    entry_ocultada = {**entry, "no_ranking": False}

    app.dependency_overrides[get_pool] = lambda: _pool_com_slug()

    with patch("repositories.entry.atualizar_visibilidade",
               AsyncMock(return_value=entry_ocultada)), \
         patch("routers.admin.broker.publish", AsyncMock()):
        resp = await client.patch(
            f"/api/admin/entries/{entry['id']}",
            json={"no_ranking": False}, headers=AUTH_HEADER)

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_ocultar_entry_inexistente_retorna_404(client):
    app.dependency_overrides[get_pool] = lambda: _pool_com_slug()

    with patch("repositories.entry.atualizar_visibilidade", AsyncMock(return_value=None)):
        resp = await client.patch(
            f"/api/admin/entries/{make_uuid()}",
            json={"no_ranking": False}, headers=AUTH_HEADER)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_aprovar_pendente(client):
    game_id = make_uuid()
    entry = make_entry(game_id=game_id, pendente=True, no_ranking=False)
    entry_aprovada = {**entry, "pendente": False, "no_ranking": True}

    app.dependency_overrides[get_pool] = lambda: _pool_com_slug()

    with patch("repositories.entry.resolver_pendente",
               AsyncMock(return_value=entry_aprovada)), \
         patch("routers.admin.broker.publish", AsyncMock()):
        resp = await client.patch(
            f"/api/admin/entries/{entry['id']}/pendente",
            json={"aprovar": True}, headers=AUTH_HEADER)

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_aprovar_pendente_publica_sse(client):
    game_id = make_uuid()
    entry = make_entry(game_id=game_id, pendente=True, no_ranking=False)
    entry_aprovada = {**entry, "pendente": False, "no_ranking": True}
    broker_mock = AsyncMock()

    app.dependency_overrides[get_pool] = lambda: _pool_com_slug()

    with patch("repositories.entry.resolver_pendente",
               AsyncMock(return_value=entry_aprovada)), \
         patch("routers.admin.broker.publish", broker_mock):
        await client.patch(
            f"/api/admin/entries/{entry['id']}/pendente",
            json={"aprovar": True}, headers=AUTH_HEADER)

    broker_mock.assert_called_once()
    assert broker_mock.call_args[0][1] == "novo_registro"


@pytest.mark.asyncio
async def test_rejeitar_pendente_nao_publica_sse(client):
    game_id = make_uuid()
    entry = make_entry(game_id=game_id, pendente=True, no_ranking=False)
    entry_rejeitada = {**entry, "pendente": False, "no_ranking": False}
    broker_mock = AsyncMock()

    app.dependency_overrides[get_pool] = lambda: _pool_com_slug()

    with patch("repositories.entry.resolver_pendente",
               AsyncMock(return_value=entry_rejeitada)), \
         patch("routers.admin.broker.publish", broker_mock):
        await client.patch(
            f"/api/admin/entries/{entry['id']}/pendente",
            json={"aprovar": False}, headers=AUTH_HEADER)

    broker_mock.assert_not_called()


# ── Games ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_criar_game(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.game.criar", AsyncMock(return_value=make_game())):
        resp = await client.post("/api/admin/games",
                                 json={"nome": "Pac-Man", "slug": "pac-man"},
                                 headers=AUTH_HEADER)
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_criar_game_slug_duplicado_retorna_409(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.game.criar",
               AsyncMock(side_effect=Exception("unique constraint"))):
        resp = await client.post("/api/admin/games",
                                 json={"nome": "Pac-Man", "slug": "pac-man"},
                                 headers=AUTH_HEADER)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_atualizar_game_super(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.game.atualizar", AsyncMock(return_value=make_game())):
        resp = await client.patch(f"/api/admin/games/{make_uuid()}",
                                  json={"ativo": False}, headers=AUTH_HEADER)

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_atualizar_game_admin_escopado(client):
    """Admin (não só super) também edita game — a régua é 'não é
    moderador', não 'é super' (decisão #1 do PERMISSOES_SPEC.md)."""
    admin_de_arena = AdminContext(
        identificador="admin@x.com", user_id="u1", super=False,
        vinculos=[{"arena_id": make_uuid(), "role": "admin"}],
    )
    app.dependency_overrides[require_admin] = lambda: admin_de_arena
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.game.atualizar", AsyncMock(return_value=make_game())):
        resp = await client.patch(f"/api/admin/games/{make_uuid()}", json={"ativo": False})

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_atualizar_game_moderador_retorna_403(client):
    """Achado incidental: este endpoint não tinha checagem nenhuma além
    de estar autenticado — moderador editava/desativava qualquer game."""
    moderador = AdminContext(
        identificador="mod@x.com", user_id="u1", super=False,
        vinculos=[{"arena_id": make_uuid(), "role": "moderador"}],
    )
    app.dependency_overrides[require_admin] = lambda: moderador
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.patch(f"/api/admin/games/{make_uuid()}", json={"ativo": False})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_atualizar_game_com_metadado(client):
    """plataforma/ano_lancamento/capa_url/gameplay_url passam direto
    pro repository (BACKLOG_2026.md §3 item 3.1)."""
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    game_id = make_uuid()

    with patch("repositories.game.atualizar", AsyncMock(return_value=make_game())) as atualizar_mock:
        resp = await client.patch(f"/api/admin/games/{game_id}",
            json={"plataforma": "Mega Drive", "ano_lancamento": 1991},
            headers=AUTH_HEADER)

    assert resp.status_code == 200
    atualizar_mock.assert_called_once_with(
        pool, game_id, None, None,
        plataforma="Mega Drive", ano_lancamento=1991, capa_url=None, gameplay_url=None,
    )


@pytest.mark.asyncio
async def test_atualizar_game_ano_lancamento_invalido_retorna_422(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.patch(f"/api/admin/games/{make_uuid()}",
        json={"ano_lancamento": 1800}, headers=AUTH_HEADER)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_atualizar_game_inexistente_retorna_404(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.game.atualizar", AsyncMock(return_value=None)):
        resp = await client.patch(f"/api/admin/games/{make_uuid()}",
                                  json={"ativo": False}, headers=AUTH_HEADER)

    assert resp.status_code == 404


# ── Config ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_listar_config(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.event_config.listar", AsyncMock(return_value={
        "rate_limit": {"valor": "10", "descricao": "limite"},
    })):
        resp = await client.get("/api/admin/config", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert "rate_limit" in resp.json()


@pytest.mark.asyncio
async def test_atualizar_config(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.event_config.atualizar", AsyncMock(return_value={
        "chave": "rate_limit", "valor": "20", "descricao": "limite"
    })):
        resp = await client.patch("/api/admin/config/rate_limit",
                                  json={"valor": "20"}, headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["valor"] == "20"


# ── Manutenção — limpar ranking ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_limpar_ranking_sem_confirmar_retorna_400(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()
    resp = await client.post("/api/admin/manutencao/limpar-ranking",
                             json={"permanente": False, "confirmar": "errado"},
                             headers=AUTH_HEADER)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_limpar_ranking_soft_delete(client):
    pool = MagicMock()
    pool.fetchval = AsyncMock(return_value=5)
    pool.execute  = AsyncMock(return_value="UPDATE 5")
    app.dependency_overrides[get_pool] = lambda: pool

    resp = await client.post("/api/admin/manutencao/limpar-ranking",
                             json={"permanente": False, "confirmar": "CONFIRMAR"},
                             headers=AUTH_HEADER)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["permanente"] is False
    assert data["total_afetadas"] == 5


@pytest.mark.asyncio
async def test_limpar_ranking_permanente(client):
    pool = MagicMock()
    pool.fetchval = AsyncMock(return_value=3)
    pool.execute  = AsyncMock(return_value="DELETE 3")
    app.dependency_overrides[get_pool] = lambda: pool

    resp = await client.post("/api/admin/manutencao/limpar-ranking",
                             json={"permanente": True, "confirmar": "CONFIRMAR"},
                             headers=AUTH_HEADER)
    assert resp.status_code == 200
    assert resp.json()["permanente"] is True


@pytest.mark.asyncio
async def test_limpar_ranking_por_game(client):
    pool = MagicMock()
    pool.fetchval = AsyncMock(return_value=2)
    pool.execute  = AsyncMock(return_value="UPDATE 2")
    app.dependency_overrides[get_pool] = lambda: pool
    game_id = make_uuid()

    resp = await client.post("/api/admin/manutencao/limpar-ranking",
                             json={"game_id": game_id, "permanente": False, "confirmar": "CONFIRMAR"},
                             headers=AUTH_HEADER)
    assert resp.status_code == 200
    assert resp.json()["total_afetadas"] == 2


@pytest.mark.asyncio
async def test_restaurar_ranking(client):
    pool = MagicMock()
    pool.fetchval = AsyncMock(return_value=4)
    pool.execute  = AsyncMock(return_value="UPDATE 4")
    app.dependency_overrides[get_pool] = lambda: pool

    resp = await client.post("/api/admin/manutencao/restaurar-ranking",
                             json={"confirmar": "CONFIRMAR"},
                             headers=AUTH_HEADER)
    assert resp.status_code == 200
    assert resp.json()["total_restauradas"] == 4


@pytest.mark.asyncio
async def test_restaurar_ranking_sem_confirmar_retorna_400(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()
    resp = await client.post("/api/admin/manutencao/restaurar-ranking",
                             json={"confirmar": ""},
                             headers=AUTH_HEADER)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_limpar_ranking_admin_nao_super_retorna_403(client):
    """Sem filtro de arena/event no corpo, limpar afeta a plataforma
    inteira — mesmo um admin comum (não só moderador) fica de fora."""
    admin_de_arena = AdminContext(
        identificador="admin@x.com", user_id="u1", super=False,
        vinculos=[{"arena_id": make_uuid(), "role": "admin"}],
    )
    app.dependency_overrides[require_admin] = lambda: admin_de_arena
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/manutencao/limpar-ranking",
                             json={"permanente": False, "confirmar": "CONFIRMAR"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_limpar_ranking_moderador_retorna_403(client):
    moderador_ctx = AdminContext(
        identificador="mod@x.com", user_id="u1", super=False,
        vinculos=[{"arena_id": make_uuid(), "role": "moderador"}],
    )
    app.dependency_overrides[require_admin] = lambda: moderador_ctx
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/manutencao/limpar-ranking",
                             json={"permanente": True, "confirmar": "CONFIRMAR"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_restaurar_ranking_moderador_retorna_403(client):
    moderador_ctx = AdminContext(
        identificador="mod@x.com", user_id="u1", super=False,
        vinculos=[{"arena_id": make_uuid(), "role": "moderador"}],
    )
    app.dependency_overrides[require_admin] = lambda: moderador_ctx
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/manutencao/restaurar-ranking",
                             json={"confirmar": "CONFIRMAR"})
    assert resp.status_code == 403


# ── Paginação real: feed e pendentes (EVENTOS_SPEC.md §5) ─────────────────────

@pytest.mark.asyncio
async def test_feed_expoe_total_no_header(client):
    """
    GET /api/admin/feed retorna X-Total-Count com a contagem geral —
    independente de quantos itens vieram na página atual (limit/offset).
    """
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.entry.listar_feed_admin", AsyncMock(return_value=[make_entry()])), \
         patch("repositories.entry.contar_feed_admin",  AsyncMock(return_value=137)):
        resp = await client.get("/api/admin/feed?limit=1&offset=0", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.headers["X-Total-Count"] == "137"
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_feed_repassa_limit_e_offset_ao_repository(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    listar_mock = AsyncMock(return_value=[])

    with patch("repositories.entry.listar_feed_admin", listar_mock), \
         patch("repositories.entry.contar_feed_admin",  AsyncMock(return_value=0)):
        await client.get("/api/admin/feed?limit=20&offset=40", headers=AUTH_HEADER)

    listar_mock.assert_called_once_with(pool, limit=20, offset=40, event_ids=None, **FILTROS_FEED_VAZIOS)


# ── Filtros combináveis do feed (docs/BACKLOG_2026.md §4.1/4.4) ────────────────

@pytest.mark.asyncio
async def test_feed_repassa_todos_os_filtros_novos_ao_repository(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    listar_mock = AsyncMock(return_value=[])
    game_id = make_uuid()

    with patch("repositories.entry.listar_feed_admin", listar_mock), \
         patch("repositories.entry.contar_feed_admin", AsyncMock(return_value=0)):
        await client.get(
            "/api/admin/feed"
            f"?status=pendentes&data_de=2026-01-01&data_ate=2026-01-31"
            f"&game_id={game_id}&sem_foto=true&sem_identificacao=true&busca=novato",
            headers=AUTH_HEADER,
        )

    listar_mock.assert_called_once_with(
        pool, limit=50, offset=0, event_ids=None,
        status="pendentes", data_de=date(2026, 1, 1), data_ate=date(2026, 1, 31),
        game_id=game_id, sem_foto=True, sem_identificacao=True, busca="novato",
    )


@pytest.mark.asyncio
async def test_feed_status_invalido_retorna_422(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()
    resp = await client.get("/api/admin/feed?status=inventado", headers=AUTH_HEADER)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_feed_sem_filtros_novos_usa_defaults(client):
    """Sem nenhum filtro na query string, repassa os defaults (sem
    filtro nenhum) — não quebra quem já chama /feed sem esses params."""
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    listar_mock = AsyncMock(return_value=[])

    with patch("repositories.entry.listar_feed_admin", listar_mock), \
         patch("repositories.entry.contar_feed_admin", AsyncMock(return_value=0)):
        resp = await client.get("/api/admin/feed", headers=AUTH_HEADER)

    assert resp.status_code == 200
    listar_mock.assert_called_once_with(pool, limit=50, offset=0, event_ids=None, **FILTROS_FEED_VAZIOS)


@pytest.mark.asyncio
async def test_pendentes_endpoint_nao_existe_mais(client):
    """GET /api/admin/pendentes foi consolidado em GET /api/admin/feed
    ?status=pendentes (Fase 5) — a rota dedicada foi removida de vez,
    não só esquecida sem uso. Ver smoke_admin.py, que já assumia isso."""
    app.dependency_overrides[get_pool] = lambda: MagicMock()
    resp = await client.get("/api/admin/pendentes", headers=AUTH_HEADER)
    assert resp.status_code == 404


# ── Escopo de admin em feed/pendentes (MARCAS_SPEC.md §6) ──────────────────────

@pytest.mark.asyncio
async def test_admin_escopado_sem_event_id_retorna_400(client):
    """Admin não-super PRECISA informar event_id — sem isso, 400 (não
    500, não lista vazia silenciosa)."""
    escopado = AdminContext(identificador="pessoa@x.com", user_id="u1", super=False)
    app.dependency_overrides[require_admin] = lambda: escopado
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.get("/api/admin/feed")

    assert resp.status_code == 400
    assert "event_id" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_admin_escopado_event_fora_do_escopo_retorna_403(client):
    """Admin restrito tentando ver um event que não é dele — nunca
    vaza dado de fora do escopo."""
    escopado = AdminContext(identificador="pessoa@x.com", user_id="u1", super=False)
    app.dependency_overrides[require_admin] = lambda: escopado
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.membership.tem_acesso_event", AsyncMock(return_value=False)):
        resp = await client.get("/api/admin/feed?event_id=ev-de-outro")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_escopado_event_dentro_do_escopo_funciona(client):
    escopado = AdminContext(identificador="pessoa@x.com", user_id="u1", super=False)
    app.dependency_overrides[require_admin] = lambda: escopado
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.membership.tem_acesso_event", AsyncMock(return_value=True)), \
         patch("repositories.entry.listar_feed_admin", AsyncMock(return_value=[])), \
         patch("repositories.entry.contar_feed_admin",  AsyncMock(return_value=0)) as contar_mock:
        resp = await client.get("/api/admin/feed?event_id=ev-meu")

    assert resp.status_code == 200
    contar_mock.assert_called_once_with(pool, event_ids=["ev-meu"], **FILTROS_FEED_VAZIOS)


@pytest.mark.asyncio
async def test_super_admin_pode_filtrar_por_event_id_tambem(client):
    """Super-admin PODE opcionalmente passar event_id (não é obrigado,
    mas se passar, filtra normalmente — sem checagem de vínculo, já que
    é super)."""
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    tem_acesso_mock = AsyncMock()

    with patch("repositories.membership.tem_acesso_event", tem_acesso_mock), \
         patch("repositories.entry.listar_feed_admin", AsyncMock(return_value=[])), \
         patch("repositories.entry.contar_feed_admin",  AsyncMock(return_value=0)) as contar_mock:
        resp = await client.get("/api/admin/feed?event_id=algum-event", headers=AUTH_HEADER)

    assert resp.status_code == 200
    # Super-admin não passa pela checagem de vínculo — não precisa
    tem_acesso_mock.assert_not_called()
    contar_mock.assert_called_once_with(pool, event_ids=["algum-event"], **FILTROS_FEED_VAZIOS)




# ── GET /api/admin/me ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_me_super_admin(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()
    resp = await client.get("/api/admin/me", headers=AUTH_HEADER)

    assert resp.status_code == 200
    data = resp.json()
    assert data["super"] is True
    assert data["identificador"] == "admin"
    assert data["events"] == []
    assert data["vinculos"] == []


@pytest.mark.asyncio
async def test_me_admin_escopado_expoe_vinculos_por_arena(client):
    """vinculos cobre arena sem event nenhum ainda (que não apareceria
    em events) — frontend usa isso pra esconder ações por nível."""
    escopado = AdminContext(
        identificador="pessoa@x.com", user_id="u1", super=False,
        vinculos=[{"arena_id": "m1", "role": "admin"}, {"arena_id": "m2", "role": "moderador"}],
    )
    app.dependency_overrides[require_admin] = lambda: escopado
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.membership.listar_events_acessiveis_detalhado", AsyncMock(return_value=[])):
        resp = await client.get("/api/admin/me")

    assert resp.status_code == 200
    assert resp.json()["vinculos"] == [{"arena_id": "m1", "role": "admin"}, {"arena_id": "m2", "role": "moderador"}]


@pytest.mark.asyncio
async def test_me_admin_escopado_lista_events_acessiveis(client):
    escopado = AdminContext(identificador="pessoa@x.com", user_id="u1", super=False)
    app.dependency_overrides[require_admin] = lambda: escopado
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    events = [{"id": "ev1", "nome": "Canal3 Expo", "slug": "canal3expo", "role": "moderador"}]
    with patch("repositories.membership.listar_events_acessiveis_detalhado",
               AsyncMock(return_value=events)):
        resp = await client.get("/api/admin/me")

    assert resp.status_code == 200
    data = resp.json()
    assert data["super"] is False
    assert data["identificador"] == "pessoa@x.com"
    assert data["events"][0]["role"] == "moderador"
    assert data["events"] == events

# ── Fluxo de aprovação de games (migration 018) ─────────────────────────────────

@pytest.mark.asyncio
async def test_criar_game_admin_escopado_fica_pendente_e_auto_vinculado(client):
    """Admin não-super: game nasce pendente_aprovacao=True e é
    auto-vinculado a todos os events que ele tem acesso — utilizável
    de imediato, mas fora do catálogo geral até aprovação."""
    escopado = AdminContext(
        identificador="pessoa@x.com", user_id="u1", super=False,
        vinculos=[{"arena_id": "m1", "role": "admin"}],
    )
    app.dependency_overrides[require_admin] = lambda: escopado
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    criar_mock = AsyncMock(return_value=make_game(pendente_aprovacao=True))
    adicionar_mock = AsyncMock()

    with patch("repositories.game.criar", criar_mock), \
         patch("repositories.membership.listar_events_acessiveis", AsyncMock(return_value=["ev1", "ev2"])), \
         patch("repositories.event_game.adicionar", adicionar_mock):
        resp = await client.post("/api/admin/games",
            json={"nome": "Frogger", "slug": "frogger"})

    assert resp.status_code == 201
    criar_mock.assert_called_once_with(
        pool, "Frogger", "frogger", None,
        pendente_aprovacao=True, criado_por="pessoa@x.com",
        plataforma=None, ano_lancamento=None, capa_url=None, gameplay_url=None,
    )
    assert adicionar_mock.call_count == 2  # um por event acessível


@pytest.mark.asyncio
async def test_criar_game_super_admin_nasce_aprovado(client):
    """Super-admin: comportamento de sempre — game já nasce aprovado,
    sem auto-vínculo (super não tem 'seus' events)."""
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    criar_mock = AsyncMock(return_value=make_game())
    with patch("repositories.game.criar", criar_mock), \
         patch("repositories.event_game.adicionar") as adicionar_mock:
        resp = await client.post("/api/admin/games",
            json={"nome": "Pac-Man", "slug": "pac-man"}, headers=AUTH_HEADER)

    assert resp.status_code == 201
    criar_mock.assert_called_once_with(
        pool, "Pac-Man", "pac-man", None,
        pendente_aprovacao=False, criado_por="admin",
        plataforma=None, ano_lancamento=None, capa_url=None, gameplay_url=None,
    )
    adicionar_mock.assert_not_called()


@pytest.mark.asyncio
async def test_criar_game_com_metadado(client):
    """plataforma/ano_lancamento/capa_url/gameplay_url são opcionais e,
    quando enviados, passam direto pro repository (BACKLOG_2026.md §3
    item 3.1)."""
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.game.criar", AsyncMock(return_value={
        "id": "j1", "nome": "Pac-Man", "slug": "pac-man", "ativo": True,
        "score_max": None, "pendente_aprovacao": False, "criado_por": "admin",
        "plataforma": "Arcade", "ano_lancamento": 1980,
        "capa_url": "https://cdn/capa.png", "gameplay_url": "https://youtu.be/x",
    })) as criar_mock:
        resp = await client.post("/api/admin/games",
            json={
                "nome": "Pac-Man", "slug": "pac-man",
                "plataforma": "Arcade", "ano_lancamento": 1980,
                "capa_url": "https://cdn/capa.png", "gameplay_url": "https://youtu.be/x",
            },
            headers=AUTH_HEADER)

    assert resp.status_code == 201
    assert resp.json()["plataforma"] == "Arcade"
    criar_mock.assert_called_once_with(
        pool, "Pac-Man", "pac-man", None,
        pendente_aprovacao=False, criado_por="admin",
        plataforma="Arcade", ano_lancamento=1980,
        capa_url="https://cdn/capa.png", gameplay_url="https://youtu.be/x",
    )


@pytest.mark.asyncio
async def test_criar_game_ano_lancamento_invalido_retorna_422(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/games",
        json={"nome": "X", "slug": "x", "ano_lancamento": 1899},
        headers=AUTH_HEADER)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_criar_game_moderador_retorna_403(client):
    """Moderador não cria game — decisão #1 do PERMISSOES_SPEC.md
    (revertia a versão anterior do backlog, que dizia o contrário)."""
    moderador = AdminContext(
        identificador="mod@x.com", user_id="u1", super=False,
        vinculos=[{"arena_id": "m1", "role": "moderador"}],
    )
    app.dependency_overrides[require_admin] = lambda: moderador
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/games", json={"nome": "Frogger", "slug": "frogger"})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_criar_game_sem_vinculo_nenhum_retorna_403(client):
    """AdminContext sem vinculos (nunca deveria chegar aqui via
    require_admin, mas a checagem não deve confiar em super=False +
    lista vazia como 'liberado')."""
    sem_vinculo = AdminContext(identificador="pessoa@x.com", user_id="u1", super=False)
    app.dependency_overrides[require_admin] = lambda: sem_vinculo
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/games", json={"nome": "Frogger", "slug": "frogger"})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_listar_pendentes_admin_escopado_retorna_403(client):
    escopado = AdminContext(identificador="pessoa@x.com", user_id="u1", super=False)
    app.dependency_overrides[require_admin] = lambda: escopado
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.get("/api/admin/games/pendentes")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_listar_pendentes_super_admin_funciona(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    pendentes = [{"id": make_uuid(), "nome": "Frogger", "slug": "frogger",
                  "score_max": None, "criado_por": "pessoa@x.com",
                  "criado_em": "2026-01-01", "events_em_uso": ["Canal3 Expo"]}]

    with patch("repositories.game.listar_pendentes_aprovacao", AsyncMock(return_value=pendentes)):
        resp = await client.get("/api/admin/games/pendentes", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_aprovar_game_admin_escopado_retorna_403(client):
    escopado = AdminContext(identificador="pessoa@x.com", user_id="u1", super=False)
    app.dependency_overrides[require_admin] = lambda: escopado
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.patch(f"/api/admin/games/{make_uuid()}/aprovar")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_aprovar_game_super_admin_funciona(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    game_id = make_uuid()

    with patch("repositories.game.aprovar", AsyncMock(return_value=make_game(pendente_aprovacao=False))):
        resp = await client.patch(f"/api/admin/games/{game_id}/aprovar", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["pendente_aprovacao"] is False


@pytest.mark.asyncio
async def test_aprovar_game_inexistente_retorna_404(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.game.aprovar", AsyncMock(return_value=None)):
        resp = await client.patch(f"/api/admin/games/{make_uuid()}/aprovar", headers=AUTH_HEADER)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_mesclar_game_admin_escopado_retorna_403(client):
    escopado = AdminContext(identificador="pessoa@x.com", user_id="u1", super=False)
    app.dependency_overrides[require_admin] = lambda: escopado
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post(f"/api/admin/games/{make_uuid()}/mesclar",
        json={"game_destino_id": make_uuid()})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_mesclar_game_mesmo_id_origem_destino_retorna_422(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    game_id = make_uuid()

    resp = await client.post(f"/api/admin/games/{game_id}/mesclar",
        json={"game_destino_id": game_id}, headers=AUTH_HEADER)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_mesclar_game_origem_inexistente_retorna_404(client):
    pool = MagicMock()
    pool.fetchval = AsyncMock(return_value=None)  # nem origem nem destino existem
    app.dependency_overrides[get_pool] = lambda: pool

    resp = await client.post(f"/api/admin/games/{make_uuid()}/mesclar",
        json={"game_destino_id": make_uuid()}, headers=AUTH_HEADER)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_mesclar_game_sucesso(client):
    origem_id = make_uuid()
    destino_id = make_uuid()

    class _FakeTxn:
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass

    class _FakeConn:
        def __init__(self):
            self.transaction = MagicMock(return_value=_FakeTxn())
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass

    pool = MagicMock()
    pool.fetchval = AsyncMock(return_value=1)  # origem e destino existem
    pool.acquire = MagicMock(return_value=_FakeConn())
    app.dependency_overrides[get_pool] = lambda: pool

    resultado_esperado = {"id": origem_id, "nome": "Pacman Dup", "slug": "pacman-dup",
                           "ativo": False, "mesclado_em_game_id": destino_id}
    with patch("repositories.game.mesclar", AsyncMock(return_value=resultado_esperado)) as mesclar_mock:
        resp = await client.post(f"/api/admin/games/{origem_id}/mesclar",
            json={"game_destino_id": destino_id}, headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["ativo"] is False
    mesclar_mock.assert_called_once()


# ── Moderação de nick (NICKNAME_SPEC.md decisões #4/#9/#10) ────────────────────

@pytest.mark.asyncio
async def test_historico_nicks(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()
    user_id = make_uuid()
    historico = [{"id": make_uuid(), "nick": "NickNovo", "nick_norm": "nicknovo", "ativo": True, "criado_em": "2026-02-01"}]

    with patch("auth.repository.listar_historico_nicks", AsyncMock(return_value=historico)):
        resp = await client.get(f"/api/admin/usuarios/{user_id}/nicks", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_forcar_troca_nick_grava_auditoria(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()
    user_id = make_uuid()
    claim_atual = {"id": make_uuid(), "nick": "Ofensivo", "nick_norm": "ofensivo", "user_id": user_id, "ativo": True, "criado_em": "2026-01-01", "em_cooldown": True}
    nova_claim = {"id": make_uuid(), "nick": "Corrigido", "nick_norm": "corrigido", "user_id": user_id, "ativo": True, "criado_em": "2026-02-01"}

    with patch("auth.repository.buscar_claim_ativo_do_usuario", AsyncMock(return_value=claim_atual)), \
         patch("auth.service.trocar_nick", AsyncMock(return_value=nova_claim)), \
         patch("auth.repository.registrar_troca_forcada", AsyncMock()) as auditoria_mock:
        resp = await client.post(f"/api/admin/usuarios/{user_id}/trocar-nick",
            json={"novo_nick": "Corrigido"}, headers=AUTH_HEADER)

    assert resp.status_code == 200
    auditoria_mock.assert_called_once()
    assert auditoria_mock.call_args.kwargs["nick_anterior"] == "Ofensivo"
    assert auditoria_mock.call_args.kwargs["nick_novo"] == "Corrigido"
    assert auditoria_mock.call_args.kwargs["realizado_por"] == "admin"


@pytest.mark.asyncio
async def test_forcar_troca_nick_ignora_cooldown(client):
    """A chamada de forcar_troca_nick pra auth_svc.trocar_nick precisa
    ir com ignorar_cooldown=True — é a diferença central da troca
    forçada (decisão #9)."""
    app.dependency_overrides[get_pool] = lambda: MagicMock()
    user_id = make_uuid()
    nova_claim = {"id": make_uuid(), "nick": "Corrigido", "nick_norm": "corrigido", "user_id": user_id, "ativo": True, "criado_em": "2026-02-01"}

    with patch("auth.repository.buscar_claim_ativo_do_usuario", AsyncMock(return_value=None)), \
         patch("auth.service.trocar_nick", AsyncMock(return_value=nova_claim)) as trocar_mock, \
         patch("auth.repository.registrar_troca_forcada", AsyncMock()):
        resp = await client.post(f"/api/admin/usuarios/{user_id}/trocar-nick",
            json={"novo_nick": "Corrigido"}, headers=AUTH_HEADER)

    assert resp.status_code == 200
    trocar_mock.assert_called_once()
    assert trocar_mock.call_args.kwargs.get("ignorar_cooldown") is True


@pytest.mark.asyncio
async def test_forcar_troca_nick_sem_mudanca_nao_audita(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()
    user_id = make_uuid()
    claim_id = make_uuid()
    claim_atual = {"id": claim_id, "nick": "MesmoNick", "nick_norm": "mesmonick", "user_id": user_id, "ativo": True, "criado_em": "2026-01-01", "em_cooldown": True}

    with patch("auth.repository.buscar_claim_ativo_do_usuario", AsyncMock(return_value=claim_atual)), \
         patch("auth.service.trocar_nick", AsyncMock(return_value=claim_atual)), \
         patch("auth.repository.registrar_troca_forcada", AsyncMock()) as auditoria_mock:
        resp = await client.post(f"/api/admin/usuarios/{user_id}/trocar-nick",
            json={"novo_nick": "MesmoNick"}, headers=AUTH_HEADER)

    assert resp.status_code == 200
    auditoria_mock.assert_not_called()


@pytest.mark.asyncio
async def test_forcar_troca_nick_colisao_retorna_409(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()
    user_id = make_uuid()

    with patch("auth.repository.buscar_claim_ativo_do_usuario", AsyncMock(return_value=None)), \
         patch("auth.service.trocar_nick", AsyncMock(side_effect=auth_svc.NickJaReivindicadoError("já tem dono"))):
        resp = await client.post(f"/api/admin/usuarios/{user_id}/trocar-nick",
            json={"novo_nick": "Ocupado"}, headers=AUTH_HEADER)

    assert resp.status_code == 409


# ── Exclusão de conta (EXCLUSAO_CONTA_SPEC.md) ─────────────────────────────────

@pytest.mark.asyncio
async def test_admin_comum_nao_lista_exclusoes_pendentes(client):
    escopado = AdminContext(
        identificador="admin@x.com", user_id="u1", super=False,
        vinculos=[{"arena_id": make_uuid(), "role": "admin"}],
    )
    app.dependency_overrides[require_admin] = lambda: escopado
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.get("/api/admin/exclusoes-pendentes")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_super_lista_exclusoes_pendentes(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()
    pendentes = [{"id": make_uuid(), "email": "p@x.com", "nome": "Pessoa",
                  "exclusao_solicitada_em": "2026-01-01", "elegivel": True}]

    with patch("repositories.usuario.listar_exclusoes_pendentes", AsyncMock(return_value=pendentes)):
        resp = await client.get("/api/admin/exclusoes-pendentes", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_admin_comum_nao_processa_exclusao(client):
    escopado = AdminContext(
        identificador="admin@x.com", user_id="u1", super=False,
        vinculos=[{"arena_id": make_uuid(), "role": "admin"}],
    )
    app.dependency_overrides[require_admin] = lambda: escopado
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post(f"/api/admin/usuarios/{make_uuid()}/processar-exclusao")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_super_processa_exclusao(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()
    user_id = make_uuid()
    resultado = {"id": user_id, "status": "excluido"}

    with patch("services.exclusao_conta.processar", AsyncMock(return_value=resultado)):
        resp = await client.post(f"/api/admin/usuarios/{user_id}/processar-exclusao", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["status"] == "excluido"


@pytest.mark.asyncio
async def test_processar_exclusao_dentro_da_janela_retorna_400(client):
    import services.exclusao_conta as exclusao_svc
    app.dependency_overrides[get_pool] = lambda: MagicMock()
    user_id = make_uuid()

    with patch("services.exclusao_conta.processar",
               AsyncMock(side_effect=exclusao_svc.ExclusaoJanelaAbertaError("faltam 5 dias"))):
        resp = await client.post(f"/api/admin/usuarios/{user_id}/processar-exclusao", headers=AUTH_HEADER)

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_processar_exclusao_bloqueada_por_titularidade_retorna_409(client):
    import services.exclusao_conta as exclusao_svc
    app.dependency_overrides[get_pool] = lambda: MagicMock()
    user_id = make_uuid()

    with patch("services.exclusao_conta.processar",
               AsyncMock(side_effect=exclusao_svc.ExclusaoBloqueadaTitularidadeError([{"id": "m1", "nome": "Canal3"}]))):
        resp = await client.post(f"/api/admin/usuarios/{user_id}/processar-exclusao", headers=AUTH_HEADER)

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_processar_exclusao_nao_elegivel_retorna_404(client):
    import services.exclusao_conta as exclusao_svc
    app.dependency_overrides[get_pool] = lambda: MagicMock()
    user_id = make_uuid()

    with patch("services.exclusao_conta.processar",
               AsyncMock(side_effect=exclusao_svc.ExclusaoNaoElegivelError("nada pendente"))):
        resp = await client.post(f"/api/admin/usuarios/{user_id}/processar-exclusao", headers=AUTH_HEADER)

    assert resp.status_code == 404
