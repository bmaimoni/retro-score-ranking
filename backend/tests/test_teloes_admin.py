"""
Testes do router admin de telões — /api/admin/teloes.
Ver docs/EVENTOS_SPEC.md §3: exatamente um entre evento_id/placar_id.
Ver docs/PERMISSOES_SPEC.md §4: telão de evento_id usa a marca do
evento; telão de placar_id usa a marca comum dos eventos vinculados
(None se ambígua/global — aí só super opera).
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from utils.db import get_pool
from middleware.auth import require_admin, AdminContext

ADMIN_SECRET = "test-secret"
AUTH_HEADER  = {"Authorization": f"Bearer {ADMIN_SECRET}"}
SUPER_CTX    = AdminContext(identificador="admin", user_id=None, super=True)
MARCA_A      = str(uuid.uuid4())
MARCA_B      = str(uuid.uuid4())


def admin_ctx(marca_id=MARCA_A):
    return AdminContext(
        identificador="admin-a@x.com", user_id=str(uuid.uuid4()), super=False,
        vinculos=[{"marca_id": marca_id, "nivel": "admin"}],
    )


def moderador_ctx(marca_id=MARCA_A):
    return AdminContext(
        identificador="mod-a@x.com", user_id=str(uuid.uuid4()), super=False,
        vinculos=[{"marca_id": marca_id, "nivel": "moderador"}],
    )


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


def _evento(marca_id=MARCA_A):
    return {"id": make_uuid(), "nome": "Evento", "slug": "evento", "marca_id": marca_id}


def _placar():
    return {"id": make_uuid(), "nome": "Placar", "slug": "placar", "escopo": "customizado"}


@pytest.fixture(autouse=True)
def clear_overrides():
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
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

    with patch("repositories.evento.buscar_por_id", AsyncMock(return_value=_evento(marca_id=MARCA_A))), \
         patch("repositories.telao.criar", AsyncMock(return_value=_telao(evento_id=evento_id, placar_id=None))):
        resp = await client.post("/api/admin/teloes",
            json={"nome": "Telão do Evento", "slug": "telao-evento", "evento_id": evento_id},
            headers=AUTH_HEADER)

    assert resp.status_code == 201
    assert resp.json()["evento_id"] == evento_id
    assert resp.json()["placar_id"] is None


@pytest.mark.asyncio
async def test_criar_telao_evento_inexistente_retorna_404(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.evento.buscar_por_id", AsyncMock(return_value=None)):
        resp = await client.post("/api/admin/teloes",
            json={"nome": "Telão Órfão", "slug": "telao-orfao", "evento_id": make_uuid()},
            headers=AUTH_HEADER)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_criar_telao_apontando_pra_placar(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    placar_id = make_uuid()

    with patch("repositories.placar.buscar_por_id", AsyncMock(return_value=_placar())), \
         patch("repositories.placar.resolver_marca_id", AsyncMock(return_value=MARCA_A)), \
         patch("repositories.telao.criar", AsyncMock(return_value=_telao(placar_id=placar_id))):
        resp = await client.post("/api/admin/teloes",
            json={"nome": "Hall da Fama Geral", "slug": "geral", "placar_id": placar_id},
            headers=AUTH_HEADER)

    assert resp.status_code == 201
    assert resp.json()["placar_id"] == placar_id


@pytest.mark.asyncio
async def test_criar_telao_placar_inexistente_retorna_404(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.placar.buscar_por_id", AsyncMock(return_value=None)):
        resp = await client.post("/api/admin/teloes",
            json={"nome": "Telão Órfão", "slug": "telao-orfao", "placar_id": make_uuid()},
            headers=AUTH_HEADER)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_criar_telao_slug_duplicado_retorna_409(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.placar.buscar_por_id", AsyncMock(return_value=_placar())), \
         patch("repositories.placar.resolver_marca_id", AsyncMock(return_value=MARCA_A)), \
         patch("repositories.telao.criar",
               AsyncMock(side_effect=Exception("duplicate key value violates unique constraint"))):
        resp = await client.post("/api/admin/teloes",
            json={"nome": "Dup", "slug": "geral", "placar_id": make_uuid()},
            headers=AUTH_HEADER)

    assert resp.status_code == 409


# ── Criar telão — escopo por marca ──────────────────────────────

@pytest.mark.asyncio
async def test_admin_cria_telao_de_evento_da_propria_marca(client):
    app.dependency_overrides[require_admin] = lambda: admin_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    evento_id = make_uuid()

    with patch("repositories.evento.buscar_por_id", AsyncMock(return_value=_evento(marca_id=MARCA_A))), \
         patch("repositories.telao.criar", AsyncMock(return_value=_telao(evento_id=evento_id))):
        resp = await client.post("/api/admin/teloes",
            json={"nome": "Telão A", "slug": "telao-a", "evento_id": evento_id})

    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_admin_nao_cria_telao_de_evento_de_outra_marca(client):
    """Adversarial: admin de A não cria telão apontando pra um evento de B."""
    app.dependency_overrides[require_admin] = lambda: admin_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.evento.buscar_por_id", AsyncMock(return_value=_evento(marca_id=MARCA_B))):
        resp = await client.post("/api/admin/teloes",
            json={"nome": "Telão B", "slug": "telao-b", "evento_id": make_uuid()})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_moderador_nao_cria_telao(client):
    app.dependency_overrides[require_admin] = lambda: moderador_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.evento.buscar_por_id", AsyncMock(return_value=_evento(marca_id=MARCA_A))):
        resp = await client.post("/api/admin/teloes",
            json={"nome": "Telão A", "slug": "telao-a", "evento_id": make_uuid()})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_cria_telao_de_placar_com_marca_unica(client):
    """Placar customizado curado só com eventos da própria marca —
    caso comum de uso real (ex: Hall da Fama da Canal3)."""
    app.dependency_overrides[require_admin] = lambda: admin_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.placar.buscar_por_id", AsyncMock(return_value=_placar())), \
         patch("repositories.placar.resolver_marca_id", AsyncMock(return_value=MARCA_A)), \
         patch("repositories.telao.criar", AsyncMock(return_value=_telao(placar_id=make_uuid()))):
        resp = await client.post("/api/admin/teloes",
            json={"nome": "Hall Canal3", "slug": "hall-canal3", "placar_id": make_uuid()})

    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_admin_nao_cria_telao_de_placar_multi_marca(client):
    """Placar cujos eventos vinculados são de marcas diferentes —
    resolver_marca_id retorna None (ambíguo) — só super opera."""
    app.dependency_overrides[require_admin] = lambda: admin_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.placar.buscar_por_id", AsyncMock(return_value=_placar())), \
         patch("repositories.placar.resolver_marca_id", AsyncMock(return_value=None)):
        resp = await client.post("/api/admin/teloes",
            json={"nome": "Hall Misto", "slug": "hall-misto", "placar_id": make_uuid()})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_nao_cria_telao_de_placar_global(client):
    """Placar global agrega tudo (todas as marcas) — resolver_marca_id
    retorna None (não usa placar_eventos) — só super opera."""
    app.dependency_overrides[require_admin] = lambda: admin_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.placar.buscar_por_id", AsyncMock(return_value={**_placar(), "escopo": "global"})), \
         patch("repositories.placar.resolver_marca_id", AsyncMock(return_value=None)):
        resp = await client.post("/api/admin/teloes",
            json={"nome": "Hall Geral", "slug": "hall-geral", "placar_id": make_uuid()})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_super_cria_telao_de_placar_global(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.placar.buscar_por_id", AsyncMock(return_value={**_placar(), "escopo": "global"})), \
         patch("repositories.placar.resolver_marca_id", AsyncMock(return_value=None)), \
         patch("repositories.telao.criar", AsyncMock(return_value=_telao(placar_id=make_uuid()))):
        resp = await client.post("/api/admin/teloes",
            json={"nome": "Hall Geral", "slug": "hall-geral", "placar_id": make_uuid()})

    assert resp.status_code == 201


# ── Atualizar telão ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_atualizar_top_n_do_telao(client):
    telao_atual = _telao(placar_id=make_uuid())
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    atualizado = {**telao_atual, "top_n": 20}
    with patch("repositories.telao.buscar_por_id", AsyncMock(return_value=telao_atual)), \
         patch("repositories.placar.resolver_marca_id", AsyncMock(return_value=MARCA_A)), \
         patch("repositories.telao.atualizar", AsyncMock(return_value=atualizado)):
        resp = await client.patch(f"/api/admin/teloes/{telao_atual['id']}",
            json={"top_n": 20},
            headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["top_n"] == 20


@pytest.mark.asyncio
async def test_atualizar_telao_inexistente_retorna_404(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.telao.buscar_por_id", AsyncMock(return_value=None)):
        resp = await client.patch(f"/api/admin/teloes/{make_uuid()}",
            json={"top_n": 5},
            headers=AUTH_HEADER)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_edita_telao_da_propria_marca(client):
    telao_atual = _telao(evento_id=make_uuid())
    app.dependency_overrides[require_admin] = lambda: admin_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.telao.buscar_por_id", AsyncMock(return_value=telao_atual)), \
         patch("repositories.evento.buscar_por_id", AsyncMock(return_value=_evento(marca_id=MARCA_A))), \
         patch("repositories.telao.atualizar", AsyncMock(return_value={**telao_atual, "top_n": 5})):
        resp = await client.patch(f"/api/admin/teloes/{telao_atual['id']}", json={"top_n": 5})

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_admin_nao_edita_telao_de_outra_marca(client):
    """Adversarial: admin de A não edita telão cujo evento é de B."""
    telao_atual = _telao(evento_id=make_uuid())
    app.dependency_overrides[require_admin] = lambda: admin_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.telao.buscar_por_id", AsyncMock(return_value=telao_atual)), \
         patch("repositories.evento.buscar_por_id", AsyncMock(return_value=_evento(marca_id=MARCA_B))):
        resp = await client.patch(f"/api/admin/teloes/{telao_atual['id']}", json={"top_n": 5})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_moderador_nao_edita_telao(client):
    telao_atual = _telao(evento_id=make_uuid())
    app.dependency_overrides[require_admin] = lambda: moderador_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.telao.buscar_por_id", AsyncMock(return_value=telao_atual)), \
         patch("repositories.evento.buscar_por_id", AsyncMock(return_value=_evento(marca_id=MARCA_A))):
        resp = await client.patch(f"/api/admin/teloes/{telao_atual['id']}", json={"top_n": 5})

    assert resp.status_code == 403


# ── Gestão de jogos do telão ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_adicionar_jogo_ao_telao(client):
    telao_atual = _telao(placar_id=make_uuid())
    telao_id = telao_atual["id"]
    jogo_id  = make_uuid()
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    vinculo = {"telao_id": telao_id, "jogo_id": jogo_id, "ativo": True, "ordem": 0, "criado_em": "2026-01-01"}
    with patch("repositories.telao.buscar_por_id", AsyncMock(return_value=telao_atual)), \
         patch("repositories.placar.resolver_marca_id", AsyncMock(return_value=MARCA_A)), \
         patch("repositories.telao.adicionar_jogo", AsyncMock(return_value=vinculo)):
        resp = await client.post(f"/api/admin/teloes/{telao_id}/jogos/{jogo_id}",
            headers=AUTH_HEADER)

    assert resp.status_code == 201
    assert resp.json()["ativo"] is True


@pytest.mark.asyncio
async def test_moderador_nao_adiciona_jogo_ao_telao(client):
    telao_atual = _telao(placar_id=make_uuid())
    app.dependency_overrides[require_admin] = lambda: moderador_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.telao.buscar_por_id", AsyncMock(return_value=telao_atual)), \
         patch("repositories.placar.resolver_marca_id", AsyncMock(return_value=MARCA_A)):
        resp = await client.post(f"/api/admin/teloes/{telao_atual['id']}/jogos/{make_uuid()}")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_reordenar_jogo_do_telao(client):
    telao_atual = _telao(placar_id=make_uuid())
    telao_id = telao_atual["id"]
    jogo_id  = make_uuid()
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    vinculo = {"telao_id": telao_id, "jogo_id": jogo_id, "ativo": True, "ordem": 3, "criado_em": "2026-01-01"}
    with patch("repositories.telao.buscar_por_id", AsyncMock(return_value=telao_atual)), \
         patch("repositories.placar.resolver_marca_id", AsyncMock(return_value=MARCA_A)), \
         patch("repositories.telao.atualizar_jogo", AsyncMock(return_value=vinculo)) as mock:
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
    telao_atual = _telao(placar_id=make_uuid())
    telao_id = telao_atual["id"]
    jogo_id  = make_uuid()
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    vinculo = {"telao_id": telao_id, "jogo_id": jogo_id, "ativo": False, "ordem": 0, "criado_em": "2026-01-01"}
    with patch("repositories.telao.buscar_por_id", AsyncMock(return_value=telao_atual)), \
         patch("repositories.placar.resolver_marca_id", AsyncMock(return_value=MARCA_A)), \
         patch("repositories.telao.atualizar_jogo", AsyncMock(return_value=vinculo)):
        resp = await client.patch(f"/api/admin/teloes/{telao_id}/jogos/{jogo_id}",
            json={"ativo": False},
            headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["ativo"] is False


@pytest.mark.asyncio
async def test_vinculo_jogo_telao_inexistente_retorna_404(client):
    telao_atual = _telao(placar_id=make_uuid())
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.telao.buscar_por_id", AsyncMock(return_value=telao_atual)), \
         patch("repositories.placar.resolver_marca_id", AsyncMock(return_value=MARCA_A)), \
         patch("repositories.telao.atualizar_jogo", AsyncMock(return_value=None)):
        resp = await client.patch(f"/api/admin/teloes/{telao_atual['id']}/jogos/{make_uuid()}",
            json={"ativo": False},
            headers=AUTH_HEADER)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_telao_inexistente_em_jogos_retorna_404(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.telao.buscar_por_id", AsyncMock(return_value=None)):
        resp = await client.patch(f"/api/admin/teloes/{make_uuid()}/jogos/{make_uuid()}",
            json={"ativo": False},
            headers=AUTH_HEADER)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_listar_jogos_do_telao(client):
    telao_atual = _telao(placar_id=make_uuid())
    telao_id = telao_atual["id"]
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    jogos = [
        {"id": make_uuid(), "nome": "Pac-Man", "slug": "pac-man", "ativo": True, "ordem": 0},
        {"id": make_uuid(), "nome": "Galaga",  "slug": "galaga",  "ativo": False, "ordem": 1},
    ]
    with patch("repositories.telao.buscar_por_id", AsyncMock(return_value=telao_atual)), \
         patch("repositories.placar.resolver_marca_id", AsyncMock(return_value=MARCA_A)), \
         patch("repositories.telao.listar_jogos_do_telao", AsyncMock(return_value=jogos)):
        resp = await client.get(f"/api/admin/teloes/{telao_id}/jogos", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_moderador_le_jogos_do_telao_com_acesso(client):
    """Leitura é liberada pra moderador com acesso à marca — só a
    edição é restrita a admin."""
    telao_atual = _telao(placar_id=make_uuid())
    app.dependency_overrides[require_admin] = lambda: moderador_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.telao.buscar_por_id", AsyncMock(return_value=telao_atual)), \
         patch("repositories.placar.resolver_marca_id", AsyncMock(return_value=MARCA_A)), \
         patch("repositories.telao.listar_jogos_do_telao", AsyncMock(return_value=[])):
        resp = await client.get(f"/api/admin/teloes/{telao_atual['id']}/jogos")

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_admin_nao_le_jogos_de_telao_de_outra_marca(client):
    telao_atual = _telao(placar_id=make_uuid())
    app.dependency_overrides[require_admin] = lambda: admin_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.telao.buscar_por_id", AsyncMock(return_value=telao_atual)), \
         patch("repositories.placar.resolver_marca_id", AsyncMock(return_value=MARCA_B)):
        resp = await client.get(f"/api/admin/teloes/{telao_atual['id']}/jogos")

    assert resp.status_code == 403


# ── Listar telões ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_super_lista_todos_os_teloes(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.telao.listar_todos", AsyncMock(return_value=[_telao(placar_id=make_uuid())])):
        resp = await client.get("/api/admin/teloes", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_admin_so_ve_teloes_da_propria_marca(client):
    telao_a = _telao(evento_id=make_uuid())
    telao_b = _telao(evento_id=make_uuid())
    app.dependency_overrides[require_admin] = lambda: admin_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    async def _buscar_evento(pool, evento_id):
        if evento_id == telao_a["evento_id"]:
            return _evento(marca_id=MARCA_A)
        return _evento(marca_id=MARCA_B)

    with patch("repositories.telao.listar_todos", AsyncMock(return_value=[telao_a, telao_b])), \
         patch("repositories.evento.buscar_por_id", AsyncMock(side_effect=_buscar_evento)):
        resp = await client.get("/api/admin/teloes")

    assert resp.status_code == 200
    ids = [t["id"] for t in resp.json()]
    assert ids == [telao_a["id"]]


@pytest.mark.asyncio
async def test_admin_nao_ve_teloes_de_placar_global_na_listagem(client):
    """Telão de placar global (marca ambígua) fica fora da lista de um
    admin escopado — não tem como agir nele mesmo."""
    telao_global = _telao(placar_id=make_uuid())
    app.dependency_overrides[require_admin] = lambda: admin_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.telao.listar_todos", AsyncMock(return_value=[telao_global])), \
         patch("repositories.placar.resolver_marca_id", AsyncMock(return_value=None)):
        resp = await client.get("/api/admin/teloes")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_listar_teloes_sem_auth_retorna_401(client):
    app.dependency_overrides.pop(require_admin, None)
    resp = await client.get("/api/admin/teloes")
    assert resp.status_code == 401
