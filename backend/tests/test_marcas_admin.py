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


@pytest.mark.asyncio
async def test_admin_edita_a_propria_marca(client):
    marca_id = make_uuid()
    admin_da_marca = AdminContext(
        identificador="admin@x.com", user_id=make_uuid(), super=False,
        vinculos=[{"marca_id": marca_id, "nivel": "admin"}],
    )
    app.dependency_overrides[require_admin] = lambda: admin_da_marca
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.marca.atualizar", AsyncMock(return_value=_marca(id=marca_id, cor_primaria="#ff0000"))):
        resp = await client.patch(f"/api/admin/marcas/{marca_id}", json={"cor_primaria": "#ff0000"})

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_admin_nao_edita_marca_de_terceiro(client):
    """Adversarial: admin de uma marca não edita outra, mesmo sabendo o id."""
    marca_de_outro = make_uuid()
    admin_de_outra_marca = AdminContext(
        identificador="admin@x.com", user_id=make_uuid(), super=False,
        vinculos=[{"marca_id": make_uuid(), "nivel": "admin"}],
    )
    app.dependency_overrides[require_admin] = lambda: admin_de_outra_marca
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.patch(f"/api/admin/marcas/{marca_de_outro}", json={"cor_primaria": "#ff0000"})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_moderador_nao_edita_marca(client):
    marca_id = make_uuid()
    moderador = AdminContext(
        identificador="mod@x.com", user_id=make_uuid(), super=False,
        vinculos=[{"marca_id": marca_id, "nivel": "moderador"}],
    )
    app.dependency_overrides[require_admin] = lambda: moderador
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.patch(f"/api/admin/marcas/{marca_id}", json={"cor_primaria": "#ff0000"})

    assert resp.status_code == 403


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


# ── itens_por_pagina (BACKLOG_2026.md §3 item 3.2) ──────────────────────────────

@pytest.mark.asyncio
async def test_atualizar_itens_por_pagina_da_marca(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    atualizada = _marca(itens_por_pagina=50)

    with patch("repositories.marca.atualizar", AsyncMock(return_value=atualizada)):
        resp = await client.patch(f"/api/admin/marcas/{make_uuid()}",
            json={"itens_por_pagina": 50},
            headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["itens_por_pagina"] == 50


@pytest.mark.asyncio
async def test_atualizar_itens_por_pagina_zero_retorna_422(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.patch(f"/api/admin/marcas/{make_uuid()}",
        json={"itens_por_pagina": 0},
        headers=AUTH_HEADER)

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


# ── Parcerias entre marcas (docs/RANKINGS_CONFIGURAVEIS_SPEC.md §2.2) ──────────

def _parceria(**overrides):
    base = {"id": make_uuid(), "marca_origem_id": make_uuid(),
            "marca_destino_id": make_uuid(), "ativo": True, "criado_em": "2026-01-01"}
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_listar_parcerias(client):
    marca_id = make_uuid()
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.marca.buscar_por_id", AsyncMock(return_value=_marca(id=marca_id))), \
         patch("repositories.marca_parceria.listar_concedidas", AsyncMock(return_value=[_parceria()])), \
         patch("repositories.marca_parceria.listar_recebidas", AsyncMock(return_value=[])):
        resp = await client.get(f"/api/admin/marcas/{marca_id}/parcerias", headers=AUTH_HEADER)

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["concedidas"]) == 1
    assert data["recebidas"] == []


@pytest.mark.asyncio
async def test_listar_parcerias_marca_inexistente_retorna_404(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.marca.buscar_por_id", AsyncMock(return_value=None)):
        resp = await client.get(f"/api/admin/marcas/{make_uuid()}/parcerias", headers=AUTH_HEADER)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_de_outra_marca_nao_lista_parcerias(client):
    """Adversarial: admin da marca A não consulta parcerias da marca B."""
    marca_b = make_uuid()
    admin_de_a = AdminContext(
        identificador="admin-a@x.com", user_id=make_uuid(), super=False,
        vinculos=[{"marca_id": make_uuid(), "nivel": "admin"}],
    )
    app.dependency_overrides[require_admin] = lambda: admin_de_a
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.marca.buscar_por_id", AsyncMock(return_value=_marca(id=marca_b))):
        resp = await client.get(f"/api/admin/marcas/{marca_b}/parcerias", headers=AUTH_HEADER)

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_moderador_nao_lista_parcerias(client):
    """Decisão #3: qualquer ADMIN da marca, moderador nunca."""
    marca_id = make_uuid()
    moderador = AdminContext(
        identificador="mod@x.com", user_id=make_uuid(), super=False,
        vinculos=[{"marca_id": marca_id, "nivel": "moderador"}],
    )
    app.dependency_overrides[require_admin] = lambda: moderador
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.marca.buscar_por_id", AsyncMock(return_value=_marca(id=marca_id))):
        resp = await client.get(f"/api/admin/marcas/{marca_id}/parcerias", headers=AUTH_HEADER)

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_liberar_parceria(client):
    """Efeito imediato — origem já libera pra destino sem exigir aceite
    antes (decisão #5). Auditoria gravada (decisão #6)."""
    origem_id, destino_id = make_uuid(), make_uuid()
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.marca.buscar_por_id", AsyncMock(side_effect=[_marca(id=origem_id), _marca(id=destino_id)])), \
         patch("repositories.marca_parceria.criar_ou_reativar",
               AsyncMock(return_value=_parceria(marca_origem_id=origem_id, marca_destino_id=destino_id))), \
         patch("repositories.admin_vinculo.registrar_auditoria", AsyncMock()) as auditoria_mock:
        resp = await client.post(f"/api/admin/marcas/{origem_id}/parcerias/{destino_id}/liberar",
            headers=AUTH_HEADER)

    assert resp.status_code == 201
    assert resp.json()["marca_destino_id"] == destino_id
    auditoria_mock.assert_called_once_with(
        pool, acao="parceria_liberada", user_alvo_id=None,
        realizado_por="admin", marca_id=origem_id, nivel=None,
        detalhes={"marca_destino_id": destino_id},
    )


@pytest.mark.asyncio
async def test_liberar_parceria_para_si_mesma_retorna_422(client):
    marca_id = make_uuid()
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post(f"/api/admin/marcas/{marca_id}/parcerias/{marca_id}/liberar",
        headers=AUTH_HEADER)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_moderador_nao_libera_parceria(client):
    marca_id = make_uuid()
    moderador = AdminContext(
        identificador="mod@x.com", user_id=make_uuid(), super=False,
        vinculos=[{"marca_id": marca_id, "nivel": "moderador"}],
    )
    app.dependency_overrides[require_admin] = lambda: moderador
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.marca.buscar_por_id", AsyncMock(return_value=_marca(id=marca_id))):
        resp = await client.post(f"/api/admin/marcas/{marca_id}/parcerias/{make_uuid()}/liberar",
            headers=AUTH_HEADER)

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_aceitar_parceria_com_liberacao_ativa(client):
    """marca_id aceita liberação de origem_id — cria a linha recíproca,
    fechando a mutualidade (decisão #2)."""
    marca_id, origem_id = make_uuid(), make_uuid()
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.marca.buscar_por_id", AsyncMock(side_effect=[_marca(id=marca_id), _marca(id=origem_id)])), \
         patch("repositories.marca_parceria.buscar",
               AsyncMock(return_value=_parceria(marca_origem_id=origem_id, marca_destino_id=marca_id, ativo=True))), \
         patch("repositories.marca_parceria.criar_ou_reativar",
               AsyncMock(return_value=_parceria(marca_origem_id=marca_id, marca_destino_id=origem_id))), \
         patch("repositories.admin_vinculo.registrar_auditoria", AsyncMock()) as auditoria_mock:
        resp = await client.post(f"/api/admin/marcas/{marca_id}/parcerias/{origem_id}/aceitar",
            headers=AUTH_HEADER)

    assert resp.status_code == 201
    auditoria_mock.assert_called_once_with(
        pool, acao="parceria_aceita", user_alvo_id=None,
        realizado_por="admin", marca_id=marca_id, nivel=None,
        detalhes={"marca_origem_id": origem_id},
    )


@pytest.mark.asyncio
async def test_aceitar_parceria_sem_liberacao_ativa_retorna_422(client):
    """Não há o que aceitar se a origem nunca liberou (ou já revogou)."""
    marca_id, origem_id = make_uuid(), make_uuid()
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.marca.buscar_por_id", AsyncMock(side_effect=[_marca(id=marca_id), _marca(id=origem_id)])), \
         patch("repositories.marca_parceria.buscar", AsyncMock(return_value=None)):
        resp = await client.post(f"/api/admin/marcas/{marca_id}/parcerias/{origem_id}/aceitar",
            headers=AUTH_HEADER)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_aceitar_parceria_liberacao_revogada_retorna_422(client):
    marca_id, origem_id = make_uuid(), make_uuid()
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.marca.buscar_por_id", AsyncMock(side_effect=[_marca(id=marca_id), _marca(id=origem_id)])), \
         patch("repositories.marca_parceria.buscar",
               AsyncMock(return_value=_parceria(ativo=False))):
        resp = await client.post(f"/api/admin/marcas/{marca_id}/parcerias/{origem_id}/aceitar",
            headers=AUTH_HEADER)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_aceitar_parceria_para_si_mesma_retorna_422(client):
    marca_id = make_uuid()
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post(f"/api/admin/marcas/{marca_id}/parcerias/{marca_id}/aceitar",
        headers=AUTH_HEADER)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_revogar_parceria(client):
    """Só a própria concessão é revogada — a linha recíproca não é
    tocada (decisão #5, pode ficar assimétrica)."""
    origem_id, destino_id = make_uuid(), make_uuid()
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.marca.buscar_por_id", AsyncMock(return_value=_marca(id=origem_id))), \
         patch("repositories.marca_parceria.revogar",
               AsyncMock(return_value=_parceria(marca_origem_id=origem_id, marca_destino_id=destino_id, ativo=False))), \
         patch("repositories.admin_vinculo.registrar_auditoria", AsyncMock()) as auditoria_mock:
        resp = await client.post(f"/api/admin/marcas/{origem_id}/parcerias/{destino_id}/revogar",
            headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["ativo"] is False
    auditoria_mock.assert_called_once_with(
        pool, acao="parceria_revogada", user_alvo_id=None,
        realizado_por="admin", marca_id=origem_id, nivel=None,
        detalhes={"marca_destino_id": destino_id},
    )


@pytest.mark.asyncio
async def test_revogar_parceria_inexistente_retorna_404(client):
    marca_id = make_uuid()
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.marca.buscar_por_id", AsyncMock(return_value=_marca(id=marca_id))), \
         patch("repositories.marca_parceria.revogar", AsyncMock(return_value=None)):
        resp = await client.post(f"/api/admin/marcas/{marca_id}/parcerias/{make_uuid()}/revogar",
            headers=AUTH_HEADER)

    assert resp.status_code == 404
