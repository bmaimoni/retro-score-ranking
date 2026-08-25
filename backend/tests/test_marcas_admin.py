"""
Testes do router admin de marcas — /api/admin/marcas.
Ver docs/MARCAS_SPEC.md §3 e docs/PERMISSOES_SPEC.md decisão #7
(criar marca é exclusivo de super — achado #5 da mesma spec, corrigido
aqui: o endpoint aceitava qualquer admin autenticado antes).
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


def make_uuid():
    return str(uuid.uuid4())


def _marca(**overrides):
    base = {
        "id": make_uuid(), "nome": "Canal3", "slug": "canal3",
        "cor_primaria": "#5e2b82", "tipografia": "arcade",
        "logo_url": "https://cdn/canal3-logo.png", "criado_em": "2026-01-01T00:00:00",
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def clear_overrides():
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    yield
    app.dependency_overrides.pop(get_pool, None)
    app.dependency_overrides.pop(require_admin, None)


# ── Criar marca ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_criar_marca(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.marca.criar", AsyncMock(return_value=_marca())):
        resp = await client.post("/api/admin/marcas",
            json={"nome": "Canal3", "slug": "canal3", "cor_primaria": "#5e2b82",
                  "tipografia": "arcade", "logo_url": "https://cdn/canal3-logo.png"},
            headers=AUTH_HEADER)

    assert resp.status_code == 201
    assert resp.json()["slug"] == "canal3"


@pytest.mark.asyncio
async def test_criar_marca_sem_campos_opcionais(client):
    """cor_primaria/tipografia/logo_url são opcionais na criação."""
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    marca_minima = _marca(cor_primaria=None, tipografia=None, logo_url=None)

    with patch("repositories.marca.criar", AsyncMock(return_value=marca_minima)):
        resp = await client.post("/api/admin/marcas",
            json={"nome": "Marca Nova", "slug": "marca-nova"},
            headers=AUTH_HEADER)

    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_criar_marca_tipografia_invalida_retorna_422(client):
    """CHECK do banco tem uma segunda linha de defesa aqui, no Pydantic —
    422 antes de chegar no banco."""
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/marcas",
        json={"nome": "X", "slug": "x", "tipografia": "comic-sans"},
        headers=AUTH_HEADER)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_criar_marca_slug_duplicado_retorna_409(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.marca.criar",
               AsyncMock(side_effect=Exception("duplicate key value violates unique constraint"))):
        resp = await client.post("/api/admin/marcas",
            json={"nome": "Dup", "slug": "canal3"},
            headers=AUTH_HEADER)

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_criar_marca_sem_auth_retorna_401(client):
    app.dependency_overrides.pop(require_admin, None)
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/marcas", json={"nome": "X", "slug": "x"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_criar_marca_admin_nao_super_retorna_403(client):
    """Nem dono de marca cria marca nova — decisão #7 do
    docs/PERMISSOES_SPEC.md, exclusivo de super."""
    admin_de_marca = AdminContext(
        identificador="dono@x.com", user_id="u1", super=False,
        vinculos=[{"marca_id": make_uuid(), "nivel": "admin"}],
    )
    app.dependency_overrides[require_admin] = lambda: admin_de_marca
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/marcas", json={"nome": "X", "slug": "x"})
    assert resp.status_code == 403


# ── Listar marcas ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_listar_marcas(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.marca.listar_todas", AsyncMock(return_value=[_marca()])):
        resp = await client.get("/api/admin/marcas", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert len(resp.json()) == 1


# ── Atualizar marca ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_atualizar_cor_da_marca(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    atualizada = _marca(cor_primaria="#ff0000")

    with patch("repositories.marca.atualizar", AsyncMock(return_value=atualizada)):
        resp = await client.patch(f"/api/admin/marcas/{make_uuid()}",
            json={"cor_primaria": "#ff0000"},
            headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["cor_primaria"] == "#ff0000"


@pytest.mark.asyncio
async def test_atualizar_marca_inexistente_retorna_404(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.marca.atualizar", AsyncMock(return_value=None)):
        resp = await client.patch(f"/api/admin/marcas/{make_uuid()}",
            json={"nome": "X"},
            headers=AUTH_HEADER)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_atualizar_marca_tipografia_invalida_retorna_422(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.patch(f"/api/admin/marcas/{make_uuid()}",
        json={"tipografia": "papyrus"},
        headers=AUTH_HEADER)

    assert resp.status_code == 422


# ── Transferência de titularidade (decisão #11) ─────────────────────────────────

def _usuario(email="novo-dono@x.com", user_id=None):
    return {"id": user_id or make_uuid(), "email": email, "email_verified": True,
            "nome": "Pessoa", "foto_url": None, "status": "ativo"}


@pytest.mark.asyncio
async def test_super_transfere_titularidade(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    marca_id = make_uuid()
    dono_atual_id = make_uuid()
    usuario = _usuario()

    with patch("repositories.marca.buscar_por_id", AsyncMock(return_value=_marca(id=marca_id))), \
         patch("repositories.marca.buscar_dono_user_id", AsyncMock(return_value=dono_atual_id)), \
         patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=usuario)), \
         patch("repositories.admin_vinculo.tem_vinculo_admin_ativo", AsyncMock(return_value=True)), \
         patch("repositories.marca.transferir_titularidade",
               AsyncMock(return_value=_marca(id=marca_id, dono_user_id=usuario["id"]))), \
         patch("repositories.admin_vinculo.registrar_auditoria", AsyncMock()) as auditoria_mock:
        resp = await client.patch(f"/api/admin/marcas/{marca_id}/titularidade",
            json={"email": usuario["email"]})

    assert resp.status_code == 200
    assert resp.json()["dono_user_id"] == usuario["id"]
    auditoria_mock.assert_called_once_with(
        pool, acao="titularidade_transferida", user_alvo_id=usuario["id"],
        realizado_por="admin", marca_id=marca_id, nivel=None,
        detalhes={"dono_anterior": dono_atual_id},
    )


@pytest.mark.asyncio
async def test_dono_atual_transfere_titularidade(client):
    dono_atual_id = make_uuid()
    marca_id = make_uuid()
    dono_ctx = AdminContext(
        identificador="dono@x.com", user_id=dono_atual_id, super=False,
        vinculos=[{"marca_id": marca_id, "nivel": "admin"}],
    )
    app.dependency_overrides[require_admin] = lambda: dono_ctx
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario()

    with patch("repositories.marca.buscar_por_id", AsyncMock(return_value=_marca(id=marca_id))), \
         patch("repositories.marca.buscar_dono_user_id", AsyncMock(return_value=dono_atual_id)), \
         patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=usuario)), \
         patch("repositories.admin_vinculo.tem_vinculo_admin_ativo", AsyncMock(return_value=True)), \
         patch("repositories.marca.transferir_titularidade",
               AsyncMock(return_value=_marca(id=marca_id, dono_user_id=usuario["id"]))), \
         patch("repositories.admin_vinculo.registrar_auditoria", AsyncMock()):
        resp = await client.patch(f"/api/admin/marcas/{marca_id}/titularidade",
            json={"email": usuario["email"]})

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_admin_comum_nao_transfere_titularidade(client):
    """Adversarial: admin da marca que NÃO é o titular não pode
    transferir — só o titular atual ou super (decisão #11)."""
    marca_id = make_uuid()
    dono_atual_id = make_uuid()
    admin_comum_ctx = AdminContext(
        identificador="outro-admin@x.com", user_id=make_uuid(), super=False,
        vinculos=[{"marca_id": marca_id, "nivel": "admin"}],
    )
    app.dependency_overrides[require_admin] = lambda: admin_comum_ctx
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.marca.buscar_por_id", AsyncMock(return_value=_marca(id=marca_id))), \
         patch("repositories.marca.buscar_dono_user_id", AsyncMock(return_value=dono_atual_id)):
        resp = await client.patch(f"/api/admin/marcas/{marca_id}/titularidade",
            json={"email": "novo-dono@x.com"})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_de_outra_marca_nao_transfere_titularidade(client):
    """Adversarial: ser dono da marca A não dá poder nenhum sobre a
    titularidade da marca B."""
    marca_a, marca_b = make_uuid(), make_uuid()
    dono_de_a = make_uuid()
    ctx = AdminContext(
        identificador="dono-a@x.com", user_id=dono_de_a, super=False,
        vinculos=[{"marca_id": marca_a, "nivel": "admin"}],
    )
    app.dependency_overrides[require_admin] = lambda: ctx
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.marca.buscar_por_id", AsyncMock(return_value=_marca(id=marca_b))), \
         patch("repositories.marca.buscar_dono_user_id", AsyncMock(return_value=make_uuid())):
        resp = await client.patch(f"/api/admin/marcas/{marca_b}/titularidade",
            json={"email": "novo-dono@x.com"})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_transferir_titularidade_marca_sem_titular_bloqueia_nao_super(client):
    """Marca recém-migrada (dono_user_id NULL) — só super pode atribuir
    a primeira titularidade, ninguém é 'titular atual' ainda."""
    marca_id = make_uuid()
    ctx = AdminContext(
        identificador="admin@x.com", user_id=make_uuid(), super=False,
        vinculos=[{"marca_id": marca_id, "nivel": "admin"}],
    )
    app.dependency_overrides[require_admin] = lambda: ctx
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.marca.buscar_por_id", AsyncMock(return_value=_marca(id=marca_id))), \
         patch("repositories.marca.buscar_dono_user_id", AsyncMock(return_value=None)):
        resp = await client.patch(f"/api/admin/marcas/{marca_id}/titularidade",
            json={"email": "novo-dono@x.com"})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_transferir_titularidade_marca_inexistente_retorna_404(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.marca.buscar_por_id", AsyncMock(return_value=None)):
        resp = await client.patch(f"/api/admin/marcas/{make_uuid()}/titularidade",
            json={"email": "x@x.com"})

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_transferir_titularidade_pessoa_nunca_logou_retorna_404(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    marca_id = make_uuid()

    with patch("repositories.marca.buscar_por_id", AsyncMock(return_value=_marca(id=marca_id))), \
         patch("repositories.marca.buscar_dono_user_id", AsyncMock(return_value=make_uuid())), \
         patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=None)):
        resp = await client.patch(f"/api/admin/marcas/{marca_id}/titularidade",
            json={"email": "nunca-logou@x.com"})

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_transferir_titularidade_sem_vinculo_admin_ativo_retorna_422(client):
    """Decisão #11: nunca pra um e-mail arbitrário — a pessoa precisa
    já ter vínculo admin ativo nesta marca."""
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    marca_id = make_uuid()
    usuario = _usuario()

    with patch("repositories.marca.buscar_por_id", AsyncMock(return_value=_marca(id=marca_id))), \
         patch("repositories.marca.buscar_dono_user_id", AsyncMock(return_value=make_uuid())), \
         patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=usuario)), \
         patch("repositories.admin_vinculo.tem_vinculo_admin_ativo", AsyncMock(return_value=False)):
        resp = await client.patch(f"/api/admin/marcas/{marca_id}/titularidade",
            json={"email": usuario["email"]})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_transferir_titularidade_para_ja_titular_retorna_422(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    marca_id = make_uuid()
    dono_id = make_uuid()
    usuario = _usuario(user_id=dono_id)

    with patch("repositories.marca.buscar_por_id", AsyncMock(return_value=_marca(id=marca_id))), \
         patch("repositories.marca.buscar_dono_user_id", AsyncMock(return_value=dono_id)), \
         patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=usuario)):
        resp = await client.patch(f"/api/admin/marcas/{marca_id}/titularidade",
            json={"email": usuario["email"]})

    assert resp.status_code == 422


# ── Eventos da marca ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_listar_eventos_da_marca(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    marca_id = make_uuid()

    eventos = [
        {"id": make_uuid(), "nome": "Canal3 Expo 2026", "slug": "canal3expo-2026",
         "ativo": True, "publico": True, "criado_em": "2026-01-01"},
    ]
    with patch("repositories.marca.listar_eventos_da_marca", AsyncMock(return_value=eventos)):
        resp = await client.get(f"/api/admin/marcas/{marca_id}/eventos", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert len(resp.json()) == 1
