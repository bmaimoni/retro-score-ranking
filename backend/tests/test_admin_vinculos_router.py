"""
Testes de routers/admin_vinculos.py — concessão/revogação de acesso
administrativo.

Ver docs/PERMISSOES_SPEC.md §2 (decisões #5, #9, #10, #12) e §5 (risco
#1 — escalonamento cross-marca exige teste adversarial explícito, não
só caminho feliz).
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from utils.db import get_pool
from middleware.auth import require_admin, AdminContext

SUPER_CTX = AdminContext(identificador="admin", user_id=None, super=True)


def make_uuid():
    return str(uuid.uuid4())


MARCA_A = make_uuid()
MARCA_B = make_uuid()


def admin_ctx(marca_id=MARCA_A, user_id=None, email="admin-a@x.com"):
    return AdminContext(
        identificador=email, user_id=user_id or make_uuid(), super=False,
        vinculos=[{"marca_id": marca_id, "nivel": "admin"}],
    )


def moderador_ctx(marca_id=MARCA_A, user_id=None, email="mod-a@x.com"):
    return AdminContext(
        identificador=email, user_id=user_id or make_uuid(), super=False,
        vinculos=[{"marca_id": marca_id, "nivel": "moderador"}],
    )


def _usuario(email="pessoa@x.com"):
    return {"id": make_uuid(), "email": email, "email_verified": True,
            "nome": "Pessoa", "foto_url": None, "status": "ativo"}


def _vinculo(**overrides):
    base = {
        "id": make_uuid(), "user_id": make_uuid(), "escopo": "marca",
        "marca_id": MARCA_A, "nivel": "admin", "ativo": True,
        "criado_em": "2026-01-01T00:00:00",
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.pop(get_pool, None)
    app.dependency_overrides.pop(require_admin, None)


def _sem_auditoria():
    """Patch de registrar_auditoria pra testes que não checam auditoria
    diretamente — evita bater no pool real (MagicMock não-awaitable)."""
    return patch("repositories.admin_vinculo.registrar_auditoria", AsyncMock())


# ── GET: continua restrito a super ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_escopado_nao_pode_listar_vinculos(client):
    app.dependency_overrides[require_admin] = lambda: admin_ctx()
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.get("/api/admin/vinculos")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_super_admin_pode_listar_vinculos(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.admin_vinculo.listar_todos", AsyncMock(return_value=[_vinculo()])):
        resp = await client.get("/api/admin/vinculos")

    assert resp.status_code == 200
    assert len(resp.json()) == 1


# ── Criar vínculo (por e-mail) — super ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_criar_vinculo_super_escopo_super(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario()

    with patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=usuario)), \
         patch("repositories.admin_vinculo.criar", AsyncMock(return_value=_vinculo(escopo="super", marca_id=None, nivel=None))), \
         _sem_auditoria():
        resp = await client.post("/api/admin/vinculos",
            json={"email": usuario["email"], "escopo": "super"})

    assert resp.status_code == 201
    assert resp.json()["escopo"] == "super"


@pytest.mark.asyncio
async def test_criar_vinculo_marca_grava_auditoria(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario()

    criar_mock = AsyncMock(return_value=_vinculo(escopo="marca", marca_id=MARCA_A, nivel="moderador"))
    auditoria_mock = AsyncMock()
    with patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=usuario)), \
         patch("repositories.admin_vinculo.criar", criar_mock), \
         patch("repositories.admin_vinculo.registrar_auditoria", auditoria_mock):
        resp = await client.post("/api/admin/vinculos",
            json={"email": usuario["email"], "escopo": "marca", "marca_id": MARCA_A, "nivel": "moderador"})

    assert resp.status_code == 201
    criar_mock.assert_called_once_with(pool, usuario["id"], "marca", "moderador", MARCA_A)
    auditoria_mock.assert_called_once_with(
        pool, acao="concedido", user_alvo_id=usuario["id"], realizado_por="admin",
        marca_id=MARCA_A, nivel="moderador",
    )


@pytest.mark.asyncio
async def test_criar_vinculo_email_normalizado_antes_da_busca(client):
    """E-mail com espaço/maiúsculas é normalizado antes de buscar —
    mesma normalização usada no login (AUTH_SPEC.md)."""
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario(email="pessoa@x.com")
    buscar_mock = AsyncMock(return_value=usuario)

    with patch("auth.repository.buscar_usuario_por_email", buscar_mock), \
         patch("repositories.admin_vinculo.criar", AsyncMock(return_value=_vinculo(escopo="super", marca_id=None, nivel=None))), \
         _sem_auditoria():
        await client.post("/api/admin/vinculos",
            json={"email": "  Pessoa@X.com  ", "escopo": "super"})

    buscar_mock.assert_called_once_with(pool, "pessoa@x.com")


@pytest.mark.asyncio
async def test_criar_vinculo_pessoa_nunca_logou_retorna_404_com_mensagem_clara(client):
    """Não dá pra vincular alguém que nunca criou conta — mensagem
    explica o que fazer, não só '404 not found' genérico."""
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=None)):
        resp = await client.post("/api/admin/vinculos",
            json={"email": "nunca-logou@x.com", "escopo": "super"})

    assert resp.status_code == 404
    assert "logar" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_criar_vinculo_marca_sem_marca_id_retorna_422(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/vinculos",
        json={"email": "x@x.com", "escopo": "marca", "nivel": "admin"})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_criar_vinculo_marca_sem_nivel_retorna_422(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/vinculos",
        json={"email": "x@x.com", "escopo": "marca", "marca_id": make_uuid()})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_criar_vinculo_super_com_nivel_retorna_422(client):
    """super não aceita marca_id/nivel junto — inconsistência clara."""
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/vinculos",
        json={"email": "x@x.com", "escopo": "super", "nivel": "admin"})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_criar_vinculo_escopo_invalido_retorna_422(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/vinculos",
        json={"email": "x@x.com", "escopo": "raiz-do-sistema"})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_criar_vinculo_escopo_evento_nao_existe_mais_retorna_422(client):
    """escopo='evento' foi eliminado na migration 019 — não é mais um
    valor aceito (era válido antes)."""
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/vinculos",
        json={"email": "x@x.com", "escopo": "evento", "marca_id": make_uuid()})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_criar_vinculo_nivel_invalido_retorna_422(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/vinculos",
        json={"email": "x@x.com", "escopo": "marca", "marca_id": make_uuid(), "nivel": "super-moderador"})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_criar_vinculo_email_invalido_retorna_422(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/vinculos",
        json={"email": "nao-e-email", "escopo": "super"})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_criar_vinculo_marca_inexistente_retorna_404(client):
    """Usuário existe, mas o marca_id apontado não — FK falha no banco."""
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario()

    with patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=usuario)), \
         patch("repositories.admin_vinculo.criar",
               AsyncMock(side_effect=Exception("violates foreign key constraint"))):
        resp = await client.post("/api/admin/vinculos",
            json={"email": usuario["email"], "escopo": "marca", "marca_id": make_uuid(), "nivel": "admin"})

    assert resp.status_code == 404


# ── Criar vínculo — admin escopado (decisão #5) ─────────────────────────────────

@pytest.mark.asyncio
async def test_admin_concede_moderador_na_propria_marca(client):
    app.dependency_overrides[require_admin] = lambda: admin_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario()

    with patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=usuario)), \
         patch("repositories.admin_vinculo.criar", AsyncMock(return_value=_vinculo(marca_id=MARCA_A, nivel="moderador"))), \
         _sem_auditoria():
        resp = await client.post("/api/admin/vinculos",
            json={"email": usuario["email"], "escopo": "marca", "marca_id": MARCA_A, "nivel": "moderador"})

    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_admin_concede_outro_admin_na_propria_marca(client):
    """Admin comum pode conceder nível admin (não só moderador) — a
    restrição de decisão #9 é só na REVOGAÇÃO de admin, não na concessão."""
    app.dependency_overrides[require_admin] = lambda: admin_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario()

    with patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=usuario)), \
         patch("repositories.admin_vinculo.criar", AsyncMock(return_value=_vinculo(marca_id=MARCA_A, nivel="admin"))), \
         _sem_auditoria():
        resp = await client.post("/api/admin/vinculos",
            json={"email": usuario["email"], "escopo": "marca", "marca_id": MARCA_A, "nivel": "admin"})

    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_admin_nao_pode_conceder_em_outra_marca(client):
    """Adversarial (risco #1 do PERMISSOES_SPEC.md): admin de A não
    pode conceder vínculo em B, mesmo enviando marca_id=B explicitamente."""
    app.dependency_overrides[require_admin] = lambda: admin_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario()

    with patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=usuario)):
        resp = await client.post("/api/admin/vinculos",
            json={"email": usuario["email"], "escopo": "marca", "marca_id": MARCA_B, "nivel": "moderador"})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_nao_pode_conceder_escopo_super(client):
    app.dependency_overrides[require_admin] = lambda: admin_ctx(marca_id=MARCA_A)
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/vinculos", json={"email": "x@x.com", "escopo": "super"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_moderador_nao_pode_conceder_nada(client):
    app.dependency_overrides[require_admin] = lambda: moderador_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario()

    with patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=usuario)):
        resp = await client.post("/api/admin/vinculos",
            json={"email": usuario["email"], "escopo": "marca", "marca_id": MARCA_A, "nivel": "moderador"})

    assert resp.status_code == 403


# ── Atualizar (ativar/desativar) vínculo — super ────────────────────────────────

@pytest.mark.asyncio
async def test_super_reativa_vinculo(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    vinculo_id = make_uuid()
    vinculo = _vinculo(id=vinculo_id, ativo=False)

    with patch("repositories.admin_vinculo.buscar_por_id", AsyncMock(return_value=vinculo)), \
         patch("repositories.marca.buscar_dono_user_id", AsyncMock(return_value=None)), \
         patch("repositories.admin_vinculo.atualizar_ativo",
               AsyncMock(return_value={**vinculo, "ativo": True})), \
         _sem_auditoria():
        resp = await client.patch(f"/api/admin/vinculos/{vinculo_id}", json={"ativo": True})

    assert resp.status_code == 200
    assert resp.json()["ativo"] is True


@pytest.mark.asyncio
async def test_super_revoga_vinculo_super(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    vinculo_id = make_uuid()
    vinculo = _vinculo(id=vinculo_id, escopo="super", marca_id=None, nivel=None)

    with patch("repositories.admin_vinculo.buscar_por_id", AsyncMock(return_value=vinculo)), \
         patch("repositories.admin_vinculo.atualizar_ativo",
               AsyncMock(return_value={**vinculo, "ativo": False})), \
         _sem_auditoria():
        resp = await client.patch(f"/api/admin/vinculos/{vinculo_id}", json={"ativo": False})

    assert resp.status_code == 200
    assert resp.json()["ativo"] is False


@pytest.mark.asyncio
async def test_atualizar_vinculo_inexistente_retorna_404(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.admin_vinculo.buscar_por_id", AsyncMock(return_value=None)):
        resp = await client.patch(f"/api/admin/vinculos/{make_uuid()}", json={"ativo": True})

    assert resp.status_code == 404


# ── Atualizar vínculo — admin escopado ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_revoga_moderador_da_propria_marca(client):
    app.dependency_overrides[require_admin] = lambda: admin_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    vinculo_id = make_uuid()
    vinculo = _vinculo(id=vinculo_id, marca_id=MARCA_A, nivel="moderador")

    with patch("repositories.admin_vinculo.buscar_por_id", AsyncMock(return_value=vinculo)), \
         patch("repositories.marca.buscar_dono_user_id", AsyncMock(return_value=None)), \
         patch("repositories.admin_vinculo.atualizar_ativo",
               AsyncMock(return_value={**vinculo, "ativo": False})), \
         _sem_auditoria():
        resp = await client.patch(f"/api/admin/vinculos/{vinculo_id}", json={"ativo": False})

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_admin_comum_nao_revoga_outro_admin_da_marca(client):
    """Decisão #9: admin comum não revoga outro admin, nem da própria
    marca — só o titular ou super."""
    app.dependency_overrides[require_admin] = lambda: admin_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    vinculo_id = make_uuid()
    outro_admin_user_id = make_uuid()
    vinculo = _vinculo(id=vinculo_id, user_id=outro_admin_user_id, marca_id=MARCA_A, nivel="admin")

    with patch("repositories.admin_vinculo.buscar_por_id", AsyncMock(return_value=vinculo)), \
         patch("repositories.marca.buscar_dono_user_id", AsyncMock(return_value=None)):
        resp = await client.patch(f"/api/admin/vinculos/{vinculo_id}", json={"ativo": False})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_dono_revoga_outro_admin_da_marca(client):
    """Decisão #9: titular É capaz de revogar outro admin da própria marca."""
    dono_user_id = make_uuid()
    app.dependency_overrides[require_admin] = lambda: admin_ctx(marca_id=MARCA_A, user_id=dono_user_id)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    vinculo_id = make_uuid()
    outro_admin_user_id = make_uuid()
    vinculo = _vinculo(id=vinculo_id, user_id=outro_admin_user_id, marca_id=MARCA_A, nivel="admin")

    with patch("repositories.admin_vinculo.buscar_por_id", AsyncMock(return_value=vinculo)), \
         patch("repositories.marca.buscar_dono_user_id", AsyncMock(return_value=dono_user_id)), \
         patch("repositories.admin_vinculo.atualizar_ativo",
               AsyncMock(return_value={**vinculo, "ativo": False})), \
         _sem_auditoria():
        resp = await client.patch(f"/api/admin/vinculos/{vinculo_id}", json={"ativo": False})

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_revogar_vinculo_do_titular_atual_retorna_409(client):
    """Decisão #10: revogar o vínculo do titular atual é bloqueado —
    mesmo pra super — até a titularidade ser transferida. Trava de
    integridade (marcas.dono_user_id ficaria órfão), não de permissão."""
    dono_user_id = make_uuid()
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    vinculo_id = make_uuid()
    vinculo = _vinculo(id=vinculo_id, user_id=dono_user_id, marca_id=MARCA_A, nivel="admin")

    with patch("repositories.admin_vinculo.buscar_por_id", AsyncMock(return_value=vinculo)), \
         patch("repositories.marca.buscar_dono_user_id", AsyncMock(return_value=dono_user_id)):
        resp = await client.patch(f"/api/admin/vinculos/{vinculo_id}", json={"ativo": False})

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_admin_nao_revoga_vinculo_de_outra_marca(client):
    """Adversarial (risco #1): admin de A não revoga vínculo (nem
    moderador) de B, mesmo sabendo o vinculo_id."""
    app.dependency_overrides[require_admin] = lambda: admin_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    vinculo_id = make_uuid()
    vinculo = _vinculo(id=vinculo_id, marca_id=MARCA_B, nivel="moderador")

    with patch("repositories.admin_vinculo.buscar_por_id", AsyncMock(return_value=vinculo)), \
         patch("repositories.marca.buscar_dono_user_id", AsyncMock(return_value=None)):
        resp = await client.patch(f"/api/admin/vinculos/{vinculo_id}", json={"ativo": False})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_nao_revoga_vinculo_super(client):
    app.dependency_overrides[require_admin] = lambda: admin_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    vinculo_id = make_uuid()
    vinculo = _vinculo(id=vinculo_id, escopo="super", marca_id=None, nivel=None)

    with patch("repositories.admin_vinculo.buscar_por_id", AsyncMock(return_value=vinculo)):
        resp = await client.patch(f"/api/admin/vinculos/{vinculo_id}", json={"ativo": False})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_nao_reativa_vinculo_de_outra_marca(client):
    """Adversarial: reativação segue a mesma regra de concessão
    (própria marca só) — não só a de revogação."""
    app.dependency_overrides[require_admin] = lambda: admin_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    vinculo_id = make_uuid()
    vinculo = _vinculo(id=vinculo_id, marca_id=MARCA_B, nivel="moderador", ativo=False)

    with patch("repositories.admin_vinculo.buscar_por_id", AsyncMock(return_value=vinculo)), \
         patch("repositories.marca.buscar_dono_user_id", AsyncMock(return_value=None)):
        resp = await client.patch(f"/api/admin/vinculos/{vinculo_id}", json={"ativo": True})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_moderador_nao_revoga_ninguem(client):
    app.dependency_overrides[require_admin] = lambda: moderador_ctx(marca_id=MARCA_A)
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    vinculo_id = make_uuid()
    vinculo = _vinculo(id=vinculo_id, marca_id=MARCA_A, nivel="moderador")

    with patch("repositories.admin_vinculo.buscar_por_id", AsyncMock(return_value=vinculo)), \
         patch("repositories.marca.buscar_dono_user_id", AsyncMock(return_value=None)):
        resp = await client.patch(f"/api/admin/vinculos/{vinculo_id}", json={"ativo": False})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_atualizar_vinculo_grava_auditoria_na_revogacao(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    vinculo_id = make_uuid()
    vinculo = _vinculo(id=vinculo_id, marca_id=MARCA_A, nivel="moderador")
    auditoria_mock = AsyncMock()

    with patch("repositories.admin_vinculo.buscar_por_id", AsyncMock(return_value=vinculo)), \
         patch("repositories.marca.buscar_dono_user_id", AsyncMock(return_value=None)), \
         patch("repositories.admin_vinculo.atualizar_ativo",
               AsyncMock(return_value={**vinculo, "ativo": False})), \
         patch("repositories.admin_vinculo.registrar_auditoria", auditoria_mock):
        await client.patch(f"/api/admin/vinculos/{vinculo_id}", json={"ativo": False})

    auditoria_mock.assert_called_once_with(
        pool, acao="revogado", user_alvo_id=vinculo["user_id"], realizado_por="admin",
        marca_id=MARCA_A, nivel="moderador",
    )
