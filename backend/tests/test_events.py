"""
Testes do repositório e endpoints de events.
Ver docs/PERMISSOES_SPEC.md §4: criar/editar event é ação de admin,
restrita à própria arena — moderador nunca, cross-arena sempre 403.
"""
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from utils.db import get_pool
from middleware.auth import require_admin, AdminContext

ADMIN_SECRET = "test-secret"
AUTH_HEADER  = {"Authorization": f"Bearer {ADMIN_SECRET}"}
SUPER_CTX    = AdminContext(identificador="admin", user_id=None, super=True)
ARENA_A      = str(uuid.uuid4())
ARENA_B      = str(uuid.uuid4())


def admin_ctx(arena_id=ARENA_A, user_id=None):
    return AdminContext(
        identificador="admin-a@x.com", user_id=user_id or str(uuid.uuid4()), super=False,
        vinculos=[{"arena_id": arena_id, "role": "admin"}],
    )


def moderador_ctx(arena_id=ARENA_A, user_id=None):
    return AdminContext(
        identificador="mod-a@x.com", user_id=user_id or str(uuid.uuid4()), super=False,
        vinculos=[{"arena_id": arena_id, "role": "moderador"}],
    )


class _FakeTxn:
    async def __aenter__(self): return self
    async def __aexit__(self, *_): pass


class _FakeConn:
    def __init__(self, entry=None):
        self.fetchrow    = AsyncMock(return_value=entry)
        self.execute     = AsyncMock(return_value="UPDATE 1")
        self.transaction = MagicMock(return_value=_FakeTxn())

    async def __aenter__(self): return self
    async def __aexit__(self, *_): pass


def _make_pool(entry=None):
    conn = _FakeConn(entry)
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)
    pool.fetchval = AsyncMock(return_value=0)
    pool.fetch    = AsyncMock(return_value=[])
    pool.acquire  = MagicMock(return_value=conn)
    return pool


def make_uuid():
    return str(uuid.uuid4())


def _event(ativo=True, publico=True, nome="Canal3 Expo 2024", slug="canal3-expo-2024", arena_id=ARENA_A):
    return {
        "id": make_uuid(), "nome": nome, "slug": slug,
        "ativo": ativo, "publico": publico,
        "arena_id": arena_id,
        "data_inicio": datetime.now(timezone.utc) - timedelta(days=1),
        "data_fim":    datetime.now(timezone.utc) + timedelta(days=1),
        "criado_em": "2024-01-01T00:00:00",
    }


def _event_fora_da_janela(nome="Evento Encerrado", slug="event-encerrado"):
    """Evento publico=true mas fora da janela de envio — visível, sem receber score."""
    return {
        "id": make_uuid(), "nome": nome, "slug": slug,
        "ativo": True, "publico": True,
        "data_inicio": datetime.now(timezone.utc) - timedelta(days=10),
        "data_fim":    datetime.now(timezone.utc) - timedelta(days=1),
        "criado_em": "2024-01-01T00:00:00",
    }


@pytest.fixture(autouse=True)
def clear_overrides():
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    yield
    app.dependency_overrides.pop(get_pool, None)
    app.dependency_overrides.pop(require_admin, None)


# ── Listar ativos (público) ───────────────────────────────────

@pytest.mark.asyncio
async def test_listar_ativos_retorna_somente_ativos(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.event.listar_ativos", AsyncMock(return_value=[_event(ativo=True)])):
        resp = await client.get("/api/admin/events/ativos")

    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["ativo"] is True


@pytest.mark.asyncio
async def test_listar_ativos_vazio(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.event.listar_ativos", AsyncMock(return_value=[])):
        resp = await client.get("/api/admin/events/ativos")

    assert resp.status_code == 200
    assert resp.json() == []


# ── Criar event ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_criar_event(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.event.criar", AsyncMock(return_value=_event())):
        resp = await client.post("/api/admin/events",
            json={
                "nome": "Canal3 Expo 2024", "slug": "canal3-expo-2024",
                "arena_id": ARENA_A,
                "data_inicio": "2024-11-01T00:00:00Z",
                "data_fim":    "2024-11-30T23:59:59Z",
            },
            headers=AUTH_HEADER)

    assert resp.status_code == 201
    assert resp.json()["slug"] == "canal3-expo-2024"


@pytest.mark.asyncio
async def test_criar_event_sem_arena_id_retorna_422(client):
    """arena_id é obrigatório desde a migration 019 (decisão #6 do
    PERMISSOES_SPEC.md) — não existe mais event sem arena."""
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    resp = await client.post("/api/admin/events",
        json={
            "nome": "Sem Marca", "slug": "sem-arena",
            "data_inicio": "2024-11-01T00:00:00Z",
            "data_fim":    "2024-11-30T23:59:59Z",
        })

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_criar_event_sem_janela_retorna_422(client):
    """data_inicio/data_fim são obrigatórios — ver EVENTOS_SPEC.md §2, decisão #1."""
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    resp = await client.post("/api/admin/events",
        json={"nome": "Sem Janela", "slug": "sem-janela"},
        headers=AUTH_HEADER)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_criar_event_data_fim_antes_de_inicio_retorna_422(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    resp = await client.post("/api/admin/events",
        json={
            "nome": "Janela Invertida", "slug": "janela-invertida",
            "data_inicio": "2024-11-30T00:00:00Z",
            "data_fim":    "2024-11-01T00:00:00Z",
        },
        headers=AUTH_HEADER)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_criar_event_sem_auth_retorna_401(client):
    app.dependency_overrides.pop(require_admin, None)  # remove override p/ testar auth real
    resp = await client.post("/api/admin/events",
        json={"nome": "Teste", "slug": "teste"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_criar_event_slug_duplicado_retorna_409(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.event.criar",
               AsyncMock(side_effect=Exception("unique constraint"))):
        resp = await client.post("/api/admin/events",
            json={
                "nome": "Dup", "slug": "dup",
                "arena_id": ARENA_A,
                "data_inicio": "2024-11-01T00:00:00Z",
                "data_fim":    "2024-11-30T23:59:59Z",
            },
            headers=AUTH_HEADER)

    assert resp.status_code == 409


# ── modo_ranking (docs/RANKINGS_CONFIGURAVEIS_SPEC.md §2.1) ─────

@pytest.mark.asyncio
async def test_criar_event_sem_modo_ranking_usa_zerado_como_default(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.event.criar", AsyncMock(return_value=_event())) as criar_mock:
        resp = await client.post("/api/admin/events",
            json={
                "nome": "Canal3 Expo 2024", "slug": "canal3-expo-2024",
                "arena_id": ARENA_A,
                "data_inicio": "2024-11-01T00:00:00Z",
                "data_fim":    "2024-11-30T23:59:59Z",
            },
            headers=AUTH_HEADER)

    assert resp.status_code == 201
    assert criar_mock.call_args[0][1]["modo_ranking"] == "zerado"


@pytest.mark.asyncio
async def test_criar_event_com_modo_ranking_valido(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.event.criar",
               AsyncMock(return_value={**_event(), "modo_ranking": "marca_parceiras"})) as criar_mock:
        resp = await client.post("/api/admin/events",
            json={
                "nome": "Canal3 Expo 2024", "slug": "canal3-expo-2024",
                "arena_id": ARENA_A, "modo_ranking": "marca_parceiras",
                "data_inicio": "2024-11-01T00:00:00Z",
                "data_fim":    "2024-11-30T23:59:59Z",
            },
            headers=AUTH_HEADER)

    assert resp.status_code == 201
    assert resp.json()["modo_ranking"] == "marca_parceiras"
    assert criar_mock.call_args[0][1]["modo_ranking"] == "marca_parceiras"


@pytest.mark.asyncio
async def test_criar_event_modo_ranking_invalido_retorna_422(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/events",
        json={
            "nome": "X", "slug": "x", "arena_id": ARENA_A,
            "modo_ranking": "inventado",
            "data_inicio": "2024-11-01T00:00:00Z",
            "data_fim":    "2024-11-30T23:59:59Z",
        },
        headers=AUTH_HEADER)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_atualizar_event_modo_ranking_invalido_retorna_422(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.patch(f"/api/admin/events/{make_uuid()}",
        json={"modo_ranking": "inventado"},
        headers=AUTH_HEADER)

    assert resp.status_code == 422


# ── Criar event — escopo por arena (decisão #5/#6) ─────────────

@pytest.mark.asyncio
async def test_admin_cria_event_na_propria_arena(client):
    app.dependency_overrides[require_admin] = lambda: admin_ctx(arena_id=ARENA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.event.criar", AsyncMock(return_value=_event(arena_id=ARENA_A))):
        resp = await client.post("/api/admin/events",
            json={
                "nome": "Evento A", "slug": "event-a", "arena_id": ARENA_A,
                "data_inicio": "2024-11-01T00:00:00Z",
                "data_fim":    "2024-11-30T23:59:59Z",
            })

    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_admin_nao_cria_event_em_outra_arena(client):
    """Adversarial: admin de A não cria event em B, mesmo enviando
    arena_id=B explicitamente."""
    app.dependency_overrides[require_admin] = lambda: admin_ctx(arena_id=ARENA_A)
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/events",
        json={
            "nome": "Evento B", "slug": "event-b", "arena_id": ARENA_B,
            "data_inicio": "2024-11-01T00:00:00Z",
            "data_fim":    "2024-11-30T23:59:59Z",
        })

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_moderador_nao_cria_event(client):
    app.dependency_overrides[require_admin] = lambda: moderador_ctx(arena_id=ARENA_A)
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/events",
        json={
            "nome": "Evento A", "slug": "event-a", "arena_id": ARENA_A,
            "data_inicio": "2024-11-01T00:00:00Z",
            "data_fim":    "2024-11-30T23:59:59Z",
        })

    assert resp.status_code == 403


# ── Atualizar event ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_desativar_event(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    event = _event(arena_id=ARENA_A)

    with patch("repositories.event.buscar_por_id", AsyncMock(return_value=event)), \
         patch("repositories.event.atualizar", AsyncMock(return_value=_event(ativo=False))):
        resp = await client.patch(f"/api/admin/events/{event['id']}",
            json={"ativo": False},
            headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["ativo"] is False


@pytest.mark.asyncio
async def test_atualizar_event_inexistente_retorna_404(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.event.buscar_por_id", AsyncMock(return_value=None)):
        resp = await client.patch(f"/api/admin/events/{make_uuid()}",
            json={"ativo": False},
            headers=AUTH_HEADER)

    assert resp.status_code == 404


# ── Atualizar event — escopo por arena ─────────────────────────

@pytest.mark.asyncio
async def test_admin_edita_event_da_propria_arena(client):
    event = _event(arena_id=ARENA_A)
    app.dependency_overrides[require_admin] = lambda: admin_ctx(arena_id=ARENA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.event.buscar_por_id", AsyncMock(return_value=event)), \
         patch("repositories.event.atualizar", AsyncMock(return_value={**event, "ativo": False})):
        resp = await client.patch(f"/api/admin/events/{event['id']}", json={"ativo": False})

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_admin_nao_edita_event_de_outra_arena(client):
    """Adversarial: admin de A não edita event de B, mesmo sabendo o id."""
    event = _event(arena_id=ARENA_B)
    app.dependency_overrides[require_admin] = lambda: admin_ctx(arena_id=ARENA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.event.buscar_por_id", AsyncMock(return_value=event)):
        resp = await client.patch(f"/api/admin/events/{event['id']}", json={"ativo": False})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_moderador_nao_edita_event(client):
    event = _event(arena_id=ARENA_A)
    app.dependency_overrides[require_admin] = lambda: moderador_ctx(arena_id=ARENA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.event.buscar_por_id", AsyncMock(return_value=event)):
        resp = await client.patch(f"/api/admin/events/{event['id']}", json={"ativo": False})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_nao_pode_mover_event_entre_arenas(client):
    """Mover um event pra outra arena é operação de super — mesmo o
    admin que já edita o event não pode reatribuir a arena dele."""
    event = _event(arena_id=ARENA_A)
    app.dependency_overrides[require_admin] = lambda: admin_ctx(arena_id=ARENA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.event.buscar_por_id", AsyncMock(return_value=event)):
        resp = await client.patch(f"/api/admin/events/{event['id']}", json={"arena_id": ARENA_B})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_super_pode_mover_event_entre_arenas(client):
    event = _event(arena_id=ARENA_A)
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.event.buscar_por_id", AsyncMock(return_value=event)), \
         patch("repositories.event.atualizar", AsyncMock(return_value={**event, "arena_id": ARENA_B})):
        resp = await client.patch(f"/api/admin/events/{event['id']}", json={"arena_id": ARENA_B})

    assert resp.status_code == 200


# ── Games do event — escopo por arena ──────────────────────────

@pytest.mark.asyncio
async def test_listar_games_do_event_moderador_com_acesso_funciona(client):
    """Leitura é liberada pra moderador (não só admin) — só a edição é
    restrita a admin."""
    event = _event(arena_id=ARENA_A)
    app.dependency_overrides[require_admin] = lambda: moderador_ctx(arena_id=ARENA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.event.buscar_por_id", AsyncMock(return_value=event)), \
         patch("repositories.event_game.listar_por_event", AsyncMock(return_value=[])):
        resp = await client.get(f"/api/admin/events/{event['id']}/games")

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_listar_games_do_event_sem_acesso_a_arena_retorna_403(client):
    event = _event(arena_id=ARENA_B)
    app.dependency_overrides[require_admin] = lambda: moderador_ctx(arena_id=ARENA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.event.buscar_por_id", AsyncMock(return_value=event)):
        resp = await client.get(f"/api/admin/events/{event['id']}/games")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_listar_games_do_event_inexistente_retorna_404(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.event.buscar_por_id", AsyncMock(return_value=None)):
        resp = await client.get(f"/api/admin/events/{make_uuid()}/games")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_adiciona_game_ao_event_da_propria_arena(client):
    event = _event(arena_id=ARENA_A)
    game_id = make_uuid()
    app.dependency_overrides[require_admin] = lambda: admin_ctx(arena_id=ARENA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.event.buscar_por_id", AsyncMock(return_value=event)), \
         patch("repositories.event_game.adicionar",
               AsyncMock(return_value={"id": make_uuid(), "event_id": event["id"],
                                        "game_id": game_id, "ativo": True, "ordem": 0,
                                        "criado_em": "2026-01-01"})):
        resp = await client.post(f"/api/admin/events/{event['id']}/games/{game_id}")

    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_moderador_nao_adiciona_game_ao_event(client):
    """Editar o catálogo de games do event é ação de admin — decisão
    #1/§4 do PERMISSOES_SPEC.md, moderador só modera pontuações."""
    event = _event(arena_id=ARENA_A)
    app.dependency_overrides[require_admin] = lambda: moderador_ctx(arena_id=ARENA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.event.buscar_por_id", AsyncMock(return_value=event)):
        resp = await client.post(f"/api/admin/events/{event['id']}/games/{make_uuid()}")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_nao_adiciona_game_a_event_de_outra_arena(client):
    """Adversarial: admin de A não mexe no catálogo de games de um
    event de B."""
    event = _event(arena_id=ARENA_B)
    app.dependency_overrides[require_admin] = lambda: admin_ctx(arena_id=ARENA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.event.buscar_por_id", AsyncMock(return_value=event)):
        resp = await client.post(f"/api/admin/events/{event['id']}/games/{make_uuid()}")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_atualiza_game_do_event_da_propria_arena(client):
    event = _event(arena_id=ARENA_A)
    game_id = make_uuid()
    app.dependency_overrides[require_admin] = lambda: admin_ctx(arena_id=ARENA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.event.buscar_por_id", AsyncMock(return_value=event)), \
         patch("repositories.event_game.atualizar",
               AsyncMock(return_value={"id": make_uuid(), "event_id": event["id"],
                                        "game_id": game_id, "ativo": False, "ordem": 0,
                                        "criado_em": "2026-01-01"})):
        resp = await client.patch(f"/api/admin/events/{event['id']}/games/{game_id}", json={"ativo": False})

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_moderador_nao_atualiza_game_do_event(client):
    event = _event(arena_id=ARENA_A)
    app.dependency_overrides[require_admin] = lambda: moderador_ctx(arena_id=ARENA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.event.buscar_por_id", AsyncMock(return_value=event)):
        resp = await client.patch(f"/api/admin/events/{event['id']}/games/{make_uuid()}", json={"ativo": False})

    assert resp.status_code == 403


# ── Listar events — filtro por arena (achado incidental) ───────

@pytest.mark.asyncio
async def test_super_lista_todos_os_events(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    events = [_event(arena_id=ARENA_A), _event(arena_id=ARENA_B)]

    with patch("repositories.event.listar", AsyncMock(return_value=events)):
        resp = await client.get("/api/admin/events")

    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_admin_so_ve_events_da_propria_arena(client):
    app.dependency_overrides[require_admin] = lambda: admin_ctx(arena_id=ARENA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    events = [_event(arena_id=ARENA_A, nome="Evento A"), _event(arena_id=ARENA_B, nome="Evento B")]

    with patch("repositories.event.listar", AsyncMock(return_value=events)):
        resp = await client.get("/api/admin/events")

    assert resp.status_code == 200
    nomes = [e["nome"] for e in resp.json()]
    assert nomes == ["Evento A"]


# ── Upload associa event_id ──────────────────────────────────

@pytest.mark.asyncio
async def test_upload_associa_event_id(client):
    """Upload no endpoint escopado deve incluir event_id na entry."""
    import io
    event  = _event()
    game_id = make_uuid()
    entry = {
        "id": make_uuid(), "game_id": game_id, "nick": "P1", "nome": None,
        "pontuacao": 5000, "foto_url": "https://cdn/f.jpg",
        "no_ranking": True, "pendente": False,
        "event_id": event["id"], "criado_em": "2024-01-01",
    }
    jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"

    pool = _make_pool(entry)
    app.dependency_overrides[get_pool] = lambda: pool
    inserir_mock = AsyncMock(return_value=entry)

    with patch("routers.event_public.storage.upload_foto",   AsyncMock(return_value="https://cdn/f.jpg")), \
         patch("routers.event_public.rl.checar_rate_limit",  AsyncMock(return_value=False)), \
         patch("routers.event_public.score_svc.validar_score", AsyncMock(return_value=None)), \
         patch("routers.event_public.nick_svc.marcar_anterior_como_superado", AsyncMock(return_value=None)), \
         patch("routers.event_public.broker.publish",          AsyncMock()), \
         patch("routers.event_public.entry_repo.inserir",    inserir_mock), \
         patch("routers.event_public.event_repo.buscar_por_slug", AsyncMock(return_value=event)), \
         patch("routers.event_public._slug_from_id",           AsyncMock(return_value="megamania")):
        resp = await client.post(f"/api/e/{event['slug']}/upload",
            data={"nick": "P1", "pontuacao": "5000", "game_id": game_id},
            files=[("foto", ("f.jpg", io.BytesIO(jpeg), "image/jpeg"))])

    assert resp.status_code == 201
    dados = inserir_mock.call_args[0][1]
    assert dados.get("event_id") == event["id"]


@pytest.mark.asyncio
async def test_upload_event_inexistente_retorna_404(client):
    """Sem event_id na URL não existe mais — event inexistente é sempre 404."""
    import io
    game_id = make_uuid()
    jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"

    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("routers.event_public.event_repo.buscar_por_slug", AsyncMock(return_value=None)):
        resp = await client.post("/api/e/nao-existe/upload",
            data={"nick": "P1", "pontuacao": "5000", "game_id": game_id},
            files=[("foto", ("f.jpg", io.BytesIO(jpeg), "image/jpeg"))])

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_upload_fora_da_janela_retorna_422(client):
    """
    Event publico=true mas fora de [data_inicio, data_fim]: visível,
    mas não aceita mais envios (EVENTOS_SPEC.md §3).
    """
    import io
    event  = _event_fora_da_janela()
    game_id = make_uuid()
    jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"

    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("routers.event_public.event_repo.buscar_por_slug", AsyncMock(return_value=event)):
        resp = await client.post(f"/api/e/{event['slug']}/upload",
            data={"nick": "P1", "pontuacao": "5000", "game_id": game_id},
            files=[("foto", ("f.jpg", io.BytesIO(jpeg), "image/jpeg"))])

    assert resp.status_code == 422
    assert "não está mais aceitando" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_event_nao_publico_retorna_403(client):
    """Evento existente mas publico=false não aceita envio nem leitura."""
    import io
    event  = _event(publico=False)
    game_id = make_uuid()
    jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"

    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("routers.event_public.event_repo.buscar_por_slug", AsyncMock(return_value=event)):
        resp = await client.post(f"/api/e/{event['slug']}/upload",
            data={"nick": "P1", "pontuacao": "5000", "game_id": game_id},
            files=[("foto", ("f.jpg", io.BytesIO(jpeg), "image/jpeg"))])

    assert resp.status_code == 403