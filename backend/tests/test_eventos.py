"""
Testes do repositório e endpoints de eventos.
Ver docs/PERMISSOES_SPEC.md §4: criar/editar evento é ação de admin,
restrita à própria marca — moderador nunca, cross-marca sempre 403.
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
MARCA_A      = str(uuid.uuid4())
MARCA_B      = str(uuid.uuid4())


def admin_ctx(marca_id=MARCA_A, user_id=None):
    return AdminContext(
        identificador="admin-a@x.com", user_id=user_id or str(uuid.uuid4()), super=False,
        vinculos=[{"marca_id": marca_id, "nivel": "admin"}],
    )


def moderador_ctx(marca_id=MARCA_A, user_id=None):
    return AdminContext(
        identificador="mod-a@x.com", user_id=user_id or str(uuid.uuid4()), super=False,
        vinculos=[{"marca_id": marca_id, "nivel": "moderador"}],
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


def _evento(ativo=True, publico=True, nome="Canal3 Expo 2024", slug="canal3-expo-2024", marca_id=MARCA_A):
    return {
        "id": make_uuid(), "nome": nome, "slug": slug,
        "ativo": ativo, "publico": publico,
        "marca_id": marca_id,
        "data_inicio": datetime.now(timezone.utc) - timedelta(days=1),
        "data_fim":    datetime.now(timezone.utc) + timedelta(days=1),
        "criado_em": "2024-01-01T00:00:00",
    }


def _evento_fora_da_janela(nome="Evento Encerrado", slug="evento-encerrado"):
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

    with patch("repositories.evento.listar_ativos", AsyncMock(return_value=[_evento(ativo=True)])):
        resp = await client.get("/api/admin/eventos/ativos")

    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["ativo"] is True


@pytest.mark.asyncio
async def test_listar_ativos_vazio(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.evento.listar_ativos", AsyncMock(return_value=[])):
        resp = await client.get("/api/admin/eventos/ativos")

    assert resp.status_code == 200
    assert resp.json() == []


# ── Criar evento ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_criar_evento(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.evento.criar", AsyncMock(return_value=_evento())):
        resp = await client.post("/api/admin/eventos",
            json={
                "nome": "Canal3 Expo 2024", "slug": "canal3-expo-2024",
                "marca_id": MARCA_A,
                "data_inicio": "2024-11-01T00:00:00Z",
                "data_fim":    "2024-11-30T23:59:59Z",
            },
            headers=AUTH_HEADER)

    assert resp.status_code == 201
    assert resp.json()["slug"] == "canal3-expo-2024"


@pytest.mark.asyncio
async def test_criar_evento_sem_marca_id_retorna_422(client):
    """marca_id é obrigatório desde a migration 019 (decisão #6 do
    PERMISSOES_SPEC.md) — não existe mais evento sem marca."""
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    resp = await client.post("/api/admin/eventos",
        json={
            "nome": "Sem Marca", "slug": "sem-marca",
            "data_inicio": "2024-11-01T00:00:00Z",
            "data_fim":    "2024-11-30T23:59:59Z",
        })

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_criar_evento_sem_janela_retorna_422(client):
    """data_inicio/data_fim são obrigatórios — ver EVENTOS_SPEC.md §2, decisão #1."""
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    resp = await client.post("/api/admin/eventos",
        json={"nome": "Sem Janela", "slug": "sem-janela"},
        headers=AUTH_HEADER)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_criar_evento_data_fim_antes_de_inicio_retorna_422(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    resp = await client.post("/api/admin/eventos",
        json={
            "nome": "Janela Invertida", "slug": "janela-invertida",
            "data_inicio": "2024-11-30T00:00:00Z",
            "data_fim":    "2024-11-01T00:00:00Z",
        },
        headers=AUTH_HEADER)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_criar_evento_sem_auth_retorna_401(client):
    app.dependency_overrides.pop(require_admin, None)  # remove override p/ testar auth real
    resp = await client.post("/api/admin/eventos",
        json={"nome": "Teste", "slug": "teste"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_criar_evento_slug_duplicado_retorna_409(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.evento.criar",
               AsyncMock(side_effect=Exception("unique constraint"))):
        resp = await client.post("/api/admin/eventos",
            json={
                "nome": "Dup", "slug": "dup",
                "marca_id": MARCA_A,
                "data_inicio": "2024-11-01T00:00:00Z",
                "data_fim":    "2024-11-30T23:59:59Z",
            },
            headers=AUTH_HEADER)

    assert resp.status_code == 409


# ── Criar evento — escopo por marca (decisão #5/#6) ─────────────

@pytest.mark.asyncio
async def test_admin_cria_evento_na_propria_marca(client):
    app.dependency_overrides[require_admin] = lambda: admin_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.evento.criar", AsyncMock(return_value=_evento(marca_id=MARCA_A))):
        resp = await client.post("/api/admin/eventos",
            json={
                "nome": "Evento A", "slug": "evento-a", "marca_id": MARCA_A,
                "data_inicio": "2024-11-01T00:00:00Z",
                "data_fim":    "2024-11-30T23:59:59Z",
            })

    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_admin_nao_cria_evento_em_outra_marca(client):
    """Adversarial: admin de A não cria evento em B, mesmo enviando
    marca_id=B explicitamente."""
    app.dependency_overrides[require_admin] = lambda: admin_ctx(marca_id=MARCA_A)
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/eventos",
        json={
            "nome": "Evento B", "slug": "evento-b", "marca_id": MARCA_B,
            "data_inicio": "2024-11-01T00:00:00Z",
            "data_fim":    "2024-11-30T23:59:59Z",
        })

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_moderador_nao_cria_evento(client):
    app.dependency_overrides[require_admin] = lambda: moderador_ctx(marca_id=MARCA_A)
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/eventos",
        json={
            "nome": "Evento A", "slug": "evento-a", "marca_id": MARCA_A,
            "data_inicio": "2024-11-01T00:00:00Z",
            "data_fim":    "2024-11-30T23:59:59Z",
        })

    assert resp.status_code == 403


# ── Atualizar evento ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_desativar_evento(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    evento = _evento(marca_id=MARCA_A)

    with patch("repositories.evento.buscar_por_id", AsyncMock(return_value=evento)), \
         patch("repositories.evento.atualizar", AsyncMock(return_value=_evento(ativo=False))):
        resp = await client.patch(f"/api/admin/eventos/{evento['id']}",
            json={"ativo": False},
            headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["ativo"] is False


@pytest.mark.asyncio
async def test_atualizar_evento_inexistente_retorna_404(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.evento.buscar_por_id", AsyncMock(return_value=None)):
        resp = await client.patch(f"/api/admin/eventos/{make_uuid()}",
            json={"ativo": False},
            headers=AUTH_HEADER)

    assert resp.status_code == 404


# ── Atualizar evento — escopo por marca ─────────────────────────

@pytest.mark.asyncio
async def test_admin_edita_evento_da_propria_marca(client):
    evento = _evento(marca_id=MARCA_A)
    app.dependency_overrides[require_admin] = lambda: admin_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.evento.buscar_por_id", AsyncMock(return_value=evento)), \
         patch("repositories.evento.atualizar", AsyncMock(return_value={**evento, "ativo": False})):
        resp = await client.patch(f"/api/admin/eventos/{evento['id']}", json={"ativo": False})

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_admin_nao_edita_evento_de_outra_marca(client):
    """Adversarial: admin de A não edita evento de B, mesmo sabendo o id."""
    evento = _evento(marca_id=MARCA_B)
    app.dependency_overrides[require_admin] = lambda: admin_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.evento.buscar_por_id", AsyncMock(return_value=evento)):
        resp = await client.patch(f"/api/admin/eventos/{evento['id']}", json={"ativo": False})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_moderador_nao_edita_evento(client):
    evento = _evento(marca_id=MARCA_A)
    app.dependency_overrides[require_admin] = lambda: moderador_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.evento.buscar_por_id", AsyncMock(return_value=evento)):
        resp = await client.patch(f"/api/admin/eventos/{evento['id']}", json={"ativo": False})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_nao_pode_mover_evento_entre_marcas(client):
    """Mover um evento pra outra marca é operação de super — mesmo o
    admin que já edita o evento não pode reatribuir a marca dele."""
    evento = _evento(marca_id=MARCA_A)
    app.dependency_overrides[require_admin] = lambda: admin_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.evento.buscar_por_id", AsyncMock(return_value=evento)):
        resp = await client.patch(f"/api/admin/eventos/{evento['id']}", json={"marca_id": MARCA_B})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_super_pode_mover_evento_entre_marcas(client):
    evento = _evento(marca_id=MARCA_A)
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.evento.buscar_por_id", AsyncMock(return_value=evento)), \
         patch("repositories.evento.atualizar", AsyncMock(return_value={**evento, "marca_id": MARCA_B})):
        resp = await client.patch(f"/api/admin/eventos/{evento['id']}", json={"marca_id": MARCA_B})

    assert resp.status_code == 200


# ── Jogos do evento — escopo por marca ──────────────────────────

@pytest.mark.asyncio
async def test_listar_jogos_do_evento_moderador_com_acesso_funciona(client):
    """Leitura é liberada pra moderador (não só admin) — só a edição é
    restrita a admin."""
    evento = _evento(marca_id=MARCA_A)
    app.dependency_overrides[require_admin] = lambda: moderador_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.evento.buscar_por_id", AsyncMock(return_value=evento)), \
         patch("repositories.evento_jogo.listar_por_evento", AsyncMock(return_value=[])):
        resp = await client.get(f"/api/admin/eventos/{evento['id']}/jogos")

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_listar_jogos_do_evento_sem_acesso_a_marca_retorna_403(client):
    evento = _evento(marca_id=MARCA_B)
    app.dependency_overrides[require_admin] = lambda: moderador_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.evento.buscar_por_id", AsyncMock(return_value=evento)):
        resp = await client.get(f"/api/admin/eventos/{evento['id']}/jogos")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_listar_jogos_do_evento_inexistente_retorna_404(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.evento.buscar_por_id", AsyncMock(return_value=None)):
        resp = await client.get(f"/api/admin/eventos/{make_uuid()}/jogos")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_adiciona_jogo_ao_evento_da_propria_marca(client):
    evento = _evento(marca_id=MARCA_A)
    jogo_id = make_uuid()
    app.dependency_overrides[require_admin] = lambda: admin_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.evento.buscar_por_id", AsyncMock(return_value=evento)), \
         patch("repositories.evento_jogo.adicionar",
               AsyncMock(return_value={"id": make_uuid(), "evento_id": evento["id"],
                                        "jogo_id": jogo_id, "ativo": True, "ordem": 0,
                                        "criado_em": "2026-01-01"})):
        resp = await client.post(f"/api/admin/eventos/{evento['id']}/jogos/{jogo_id}")

    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_moderador_nao_adiciona_jogo_ao_evento(client):
    """Editar o catálogo de jogos do evento é ação de admin — decisão
    #1/§4 do PERMISSOES_SPEC.md, moderador só modera pontuações."""
    evento = _evento(marca_id=MARCA_A)
    app.dependency_overrides[require_admin] = lambda: moderador_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.evento.buscar_por_id", AsyncMock(return_value=evento)):
        resp = await client.post(f"/api/admin/eventos/{evento['id']}/jogos/{make_uuid()}")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_nao_adiciona_jogo_a_evento_de_outra_marca(client):
    """Adversarial: admin de A não mexe no catálogo de jogos de um
    evento de B."""
    evento = _evento(marca_id=MARCA_B)
    app.dependency_overrides[require_admin] = lambda: admin_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.evento.buscar_por_id", AsyncMock(return_value=evento)):
        resp = await client.post(f"/api/admin/eventos/{evento['id']}/jogos/{make_uuid()}")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_atualiza_jogo_do_evento_da_propria_marca(client):
    evento = _evento(marca_id=MARCA_A)
    jogo_id = make_uuid()
    app.dependency_overrides[require_admin] = lambda: admin_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.evento.buscar_por_id", AsyncMock(return_value=evento)), \
         patch("repositories.evento_jogo.atualizar",
               AsyncMock(return_value={"id": make_uuid(), "evento_id": evento["id"],
                                        "jogo_id": jogo_id, "ativo": False, "ordem": 0,
                                        "criado_em": "2026-01-01"})):
        resp = await client.patch(f"/api/admin/eventos/{evento['id']}/jogos/{jogo_id}", json={"ativo": False})

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_moderador_nao_atualiza_jogo_do_evento(client):
    evento = _evento(marca_id=MARCA_A)
    app.dependency_overrides[require_admin] = lambda: moderador_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.evento.buscar_por_id", AsyncMock(return_value=evento)):
        resp = await client.patch(f"/api/admin/eventos/{evento['id']}/jogos/{make_uuid()}", json={"ativo": False})

    assert resp.status_code == 403


# ── Listar eventos — filtro por marca (achado incidental) ───────

@pytest.mark.asyncio
async def test_super_lista_todos_os_eventos(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    eventos = [_evento(marca_id=MARCA_A), _evento(marca_id=MARCA_B)]

    with patch("repositories.evento.listar", AsyncMock(return_value=eventos)):
        resp = await client.get("/api/admin/eventos")

    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_admin_so_ve_eventos_da_propria_marca(client):
    app.dependency_overrides[require_admin] = lambda: admin_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    eventos = [_evento(marca_id=MARCA_A, nome="Evento A"), _evento(marca_id=MARCA_B, nome="Evento B")]

    with patch("repositories.evento.listar", AsyncMock(return_value=eventos)):
        resp = await client.get("/api/admin/eventos")

    assert resp.status_code == 200
    nomes = [e["nome"] for e in resp.json()]
    assert nomes == ["Evento A"]


# ── Upload associa evento_id ──────────────────────────────────

@pytest.mark.asyncio
async def test_upload_associa_evento_id(client):
    """Upload no endpoint escopado deve incluir evento_id na entrada."""
    import io
    evento  = _evento()
    jogo_id = make_uuid()
    entrada = {
        "id": make_uuid(), "jogo_id": jogo_id, "nick": "P1", "nome": None,
        "pontuacao": 5000, "foto_url": "https://cdn/f.jpg",
        "no_ranking": True, "pendente": False,
        "evento_id": evento["id"], "criado_em": "2024-01-01",
    }
    jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"

    pool = _make_pool(entrada)
    app.dependency_overrides[get_pool] = lambda: pool
    inserir_mock = AsyncMock(return_value=entrada)

    with patch("routers.evento_publico.storage.upload_foto",   AsyncMock(return_value="https://cdn/f.jpg")), \
         patch("routers.evento_publico.rl.checar_rate_limit",  AsyncMock(return_value=False)), \
         patch("routers.evento_publico.score_svc.validar_score", AsyncMock(return_value=None)), \
         patch("routers.evento_publico.nick_svc.marcar_anterior_como_superado", AsyncMock(return_value=None)), \
         patch("routers.evento_publico.broker.publish",          AsyncMock()), \
         patch("routers.evento_publico.entrada_repo.inserir",    inserir_mock), \
         patch("routers.evento_publico.evento_repo.buscar_por_slug", AsyncMock(return_value=evento)), \
         patch("routers.evento_publico._slug_from_id",           AsyncMock(return_value="megamania")):
        resp = await client.post(f"/api/e/{evento['slug']}/upload",
            data={"nick": "P1", "pontuacao": "5000", "jogo_id": jogo_id},
            files=[("foto", ("f.jpg", io.BytesIO(jpeg), "image/jpeg"))])

    assert resp.status_code == 201
    dados = inserir_mock.call_args[0][1]
    assert dados.get("evento_id") == evento["id"]


@pytest.mark.asyncio
async def test_upload_evento_inexistente_retorna_404(client):
    """Sem evento_id na URL não existe mais — evento inexistente é sempre 404."""
    import io
    jogo_id = make_uuid()
    jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"

    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("routers.evento_publico.evento_repo.buscar_por_slug", AsyncMock(return_value=None)):
        resp = await client.post("/api/e/nao-existe/upload",
            data={"nick": "P1", "pontuacao": "5000", "jogo_id": jogo_id},
            files=[("foto", ("f.jpg", io.BytesIO(jpeg), "image/jpeg"))])

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_upload_fora_da_janela_retorna_422(client):
    """
    Evento publico=true mas fora de [data_inicio, data_fim]: visível,
    mas não aceita mais envios (EVENTOS_SPEC.md §3).
    """
    import io
    evento  = _evento_fora_da_janela()
    jogo_id = make_uuid()
    jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"

    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("routers.evento_publico.evento_repo.buscar_por_slug", AsyncMock(return_value=evento)):
        resp = await client.post(f"/api/e/{evento['slug']}/upload",
            data={"nick": "P1", "pontuacao": "5000", "jogo_id": jogo_id},
            files=[("foto", ("f.jpg", io.BytesIO(jpeg), "image/jpeg"))])

    assert resp.status_code == 422
    assert "não está mais aceitando" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_evento_nao_publico_retorna_403(client):
    """Evento existente mas publico=false não aceita envio nem leitura."""
    import io
    evento  = _evento(publico=False)
    jogo_id = make_uuid()
    jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"

    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("routers.evento_publico.evento_repo.buscar_por_slug", AsyncMock(return_value=evento)):
        resp = await client.post(f"/api/e/{evento['slug']}/upload",
            data={"nick": "P1", "pontuacao": "5000", "jogo_id": jogo_id},
            files=[("foto", ("f.jpg", io.BytesIO(jpeg), "image/jpeg"))])

    assert resp.status_code == 403