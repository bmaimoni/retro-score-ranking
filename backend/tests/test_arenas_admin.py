"""
Testes do router admin de arenas — /api/admin/arenas.
Ver docs/MARCAS_SPEC.md §3 e docs/PERMISSOES_SPEC.md decisão #7
(criar arena é exclusivo de super — achado #5 da mesma spec, corrigido
aqui: o endpoint aceitava qualquer admin autenticado antes).
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from utils.db import get_pool
from middleware.auth import require_admin, require_super_or_authenticated_user, AdminContext

ADMIN_SECRET = "test-secret"
AUTH_HEADER  = {"Authorization": f"Bearer {ADMIN_SECRET}"}
SUPER_CTX    = AdminContext(identificador="admin", user_id=None, super=True)


def make_uuid():
    return str(uuid.uuid4())


def _arena(**overrides):
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
    # criar_arena usa require_super_or_authenticated_user, não
    # require_admin (Fase 8 — resolve o ovo-e-galinha de quem ainda
    # não é admin de nada) — default super aqui preserva o
    # comportamento dos testes já existentes; testes do caminho
    # self-serve sobrescrevem com um AdminContext não-super.
    app.dependency_overrides[require_super_or_authenticated_user] = lambda: SUPER_CTX
    yield
    app.dependency_overrides.pop(get_pool, None)
    app.dependency_overrides.pop(require_admin, None)
    app.dependency_overrides.pop(require_super_or_authenticated_user, None)


# ── Criar arena ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_criar_arena(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.arena.criar", AsyncMock(return_value=_arena())):
        resp = await client.post("/api/admin/arenas",
            json={"nome": "Canal3", "slug": "canal3", "cor_primaria": "#5e2b82",
                  "tipografia": "arcade", "logo_url": "https://cdn/canal3-logo.png"},
            headers=AUTH_HEADER)

    assert resp.status_code == 201
    assert resp.json()["slug"] == "canal3"


@pytest.mark.asyncio
async def test_criar_arena_sem_campos_opcionais(client):
    """cor_primaria/tipografia/logo_url são opcionais na criação."""
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    arena_minima = _arena(cor_primaria=None, tipografia=None, logo_url=None)

    with patch("repositories.arena.criar", AsyncMock(return_value=arena_minima)):
        resp = await client.post("/api/admin/arenas",
            json={"nome": "Marca Nova", "slug": "arena-nova"},
            headers=AUTH_HEADER)

    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_criar_arena_tipografia_invalida_retorna_422(client):
    """CHECK do banco tem uma segunda linha de defesa aqui, no Pydantic —
    422 antes de chegar no banco."""
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/arenas",
        json={"nome": "X", "slug": "x", "tipografia": "comic-sans"},
        headers=AUTH_HEADER)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_criar_arena_slug_duplicado_retorna_409(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.arena.criar",
               AsyncMock(side_effect=Exception("duplicate key value violates unique constraint"))):
        resp = await client.post("/api/admin/arenas",
            json={"nome": "Dup", "slug": "canal3"},
            headers=AUTH_HEADER)

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_criar_arena_sem_auth_retorna_401(client):
    # criar_arena usa require_super_or_authenticated_user (Fase 8) —
    # pop essa, não require_admin, pra exercitar o caminho real
    # sem-sessão-nem-Bearer.
    app.dependency_overrides.pop(require_super_or_authenticated_user, None)
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post("/api/admin/arenas", json={"nome": "X", "slug": "x"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_criar_arena_admin_nao_super_cria_via_caminho_selfserve(client):
    """Fase 8 (ARENA_SPEC.md G.3) reverte a decisão #7 original do
    docs/PERMISSOES_SPEC.md: qualquer usuário autenticado pode criar
    arena agora, inclusive quem já é admin de outra — não é mais
    exclusivo de super. Admin comum passa a cair no caminho self-serve
    (rate limit + colisão + heurística), não em 403."""
    admin_de_arena = AdminContext(
        identificador="dono@x.com", user_id="u1", super=False,
        vinculos=[{"arena_id": make_uuid(), "role": "admin"}],
    )
    app.dependency_overrides[require_super_or_authenticated_user] = lambda: admin_de_arena
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    arena = _arena(nome="Nova Arena do Mesmo Dono", slug="nova-arena-do-mesmo-dono")
    with patch("repositories.arena.contar_criadas_por_owner_ultimas_24h", AsyncMock(return_value=0)), \
         patch("repositories.arena.listar_nome_slug", AsyncMock(return_value=[])), \
         patch("repositories.arena.criar", AsyncMock(return_value=arena)), \
         patch("repositories.membership.criar", AsyncMock(return_value={})), \
         patch("repositories.membership.registrar_auditoria", AsyncMock(return_value=None)), \
         patch("repositories.arena.transferir_titularidade", AsyncMock(return_value=arena)):
        resp = await client.post("/api/admin/arenas",
            json={"nome": "Nova Arena do Mesmo Dono", "slug": "nova-arena-do-mesmo-dono"})

    assert resp.status_code == 201


# ── Listar arenas ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_listar_arenas(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.arena.listar_todas", AsyncMock(return_value=[_arena()])):
        resp = await client.get("/api/admin/arenas", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_admin_escopado_so_ve_a_propria_arena(client):
    """docs/PERMISSOES_SPEC.md §8.1: antes desta correção, o endpoint
    devolvia TODAS as arenas pra qualquer admin autenticado — vazando
    nome/identidade visual de outros clientes."""
    arena_a, arena_b = _arena(nome="Canal3"), _arena(nome="Cliente B")
    admin_de_a = AdminContext(
        identificador="admin-a@x.com", user_id=make_uuid(), super=False,
        vinculos=[{"arena_id": arena_a["id"], "role": "admin"}],
    )
    app.dependency_overrides[require_admin] = lambda: admin_de_a
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.arena.listar_todas", AsyncMock(return_value=[arena_a, arena_b])):
        resp = await client.get("/api/admin/arenas")

    assert resp.status_code == 200
    nomes = [m["nome"] for m in resp.json()]
    assert nomes == ["Canal3"]


@pytest.mark.asyncio
async def test_moderador_so_ve_a_propria_arena(client):
    arena_a, arena_b = _arena(nome="Canal3"), _arena(nome="Cliente B")
    moderador = AdminContext(
        identificador="mod@x.com", user_id=make_uuid(), super=False,
        vinculos=[{"arena_id": arena_a["id"], "role": "moderador"}],
    )
    app.dependency_overrides[require_admin] = lambda: moderador
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.arena.listar_todas", AsyncMock(return_value=[arena_a, arena_b])):
        resp = await client.get("/api/admin/arenas")

    assert resp.status_code == 200
    nomes = [m["nome"] for m in resp.json()]
    assert nomes == ["Canal3"]


@pytest.mark.asyncio
async def test_super_ve_todas_as_arenas(client):
    arena_a, arena_b = _arena(nome="Canal3"), _arena(nome="Cliente B")
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.arena.listar_todas", AsyncMock(return_value=[arena_a, arena_b])):
        resp = await client.get("/api/admin/arenas", headers=AUTH_HEADER)

    assert len(resp.json()) == 2


# ── Criar arena com titularidade atômica (docs/PERMISSOES_SPEC.md §8.3) ────────

@pytest.mark.asyncio
async def test_criar_arena_com_dono_email_atribui_vinculo_e_titularidade(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    arena_id = make_uuid()
    dono = _usuario(email="dono@cliente.com")
    arena_criada  = _arena(id=arena_id)
    arena_com_dono = _arena(id=arena_id, owner_user_id=dono["id"])

    with patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=dono)), \
         patch("repositories.arena.criar", AsyncMock(return_value=arena_criada)), \
         patch("repositories.membership.criar", AsyncMock()) as criar_vinculo_mock, \
         patch("repositories.arena.transferir_titularidade", AsyncMock(return_value=arena_com_dono)) as transferir_mock, \
         patch("repositories.membership.registrar_auditoria", AsyncMock()) as auditoria_mock:
        resp = await client.post("/api/admin/arenas",
            json={"nome": "Cliente Novo", "slug": "cliente-novo", "dono_email": dono["email"]},
            headers=AUTH_HEADER)

    assert resp.status_code == 201
    assert resp.json()["owner_user_id"] == dono["id"]
    criar_vinculo_mock.assert_called_once_with(pool, dono["id"], "marca", "admin", arena_id)
    transferir_mock.assert_called_once_with(pool, arena_id, dono["id"])
    assert auditoria_mock.call_count == 2
    auditoria_mock.assert_any_call(
        pool, acao="concedido", user_alvo_id=dono["id"], realizado_por="admin",
        arena_id=arena_id, role="admin",
    )
    auditoria_mock.assert_any_call(
        pool, acao="titularidade_transferida", user_alvo_id=dono["id"],
        realizado_por="admin", arena_id=arena_id, role=None,
        detalhes={"dono_anterior": None},
    )


@pytest.mark.asyncio
async def test_criar_arena_dono_email_pessoa_nunca_logou_retorna_404(client):
    """Mesma mensagem já usada em /vinculos e /titularidade — e a arena
    NÃO chega a ser criada (evita arena 'meia-pronta' se o e-mail
    estiver errado)."""
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=None)), \
         patch("repositories.arena.criar", AsyncMock()) as criar_arena_mock:
        resp = await client.post("/api/admin/arenas",
            json={"nome": "X", "slug": "x", "dono_email": "nunca-logou@x.com"},
            headers=AUTH_HEADER)

    assert resp.status_code == 404
    assert "logar" in resp.json()["detail"].lower()
    criar_arena_mock.assert_not_called()


@pytest.mark.asyncio
async def test_criar_arena_sem_dono_email_fica_sem_titular_como_antes(client):
    """dono_email continua opcional — comportamento antigo preservado."""
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.arena.criar", AsyncMock(return_value=_arena())) as criar_arena_mock, \
         patch("repositories.membership.criar", AsyncMock()) as criar_vinculo_mock:
        resp = await client.post("/api/admin/arenas",
            json={"nome": "Canal3", "slug": "canal3"},
            headers=AUTH_HEADER)

    assert resp.status_code == 201
    criar_arena_mock.assert_called_once()
    criar_vinculo_mock.assert_not_called()


@pytest.mark.asyncio
async def test_criar_arena_admin_nao_super_ignora_dono_email(client):
    """dono_email só tem efeito no caminho super (Fase 8) — admin
    comum enviando esse campo não eleva privilégio nenhum, o campo é
    simplesmente ignorado no caminho self-serve (o próprio criador
    sempre vira o dono, nunca um terceiro indicado por ele)."""
    admin_de_arena = AdminContext(
        identificador="dono@x.com", user_id="u1", super=False,
        vinculos=[{"arena_id": make_uuid(), "role": "admin"}],
    )
    app.dependency_overrides[require_super_or_authenticated_user] = lambda: admin_de_arena
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    arena = _arena(nome="X", slug="x")
    with patch("repositories.arena.contar_criadas_por_owner_ultimas_24h", AsyncMock(return_value=0)), \
         patch("repositories.arena.listar_nome_slug", AsyncMock(return_value=[])), \
         patch("repositories.arena.criar", AsyncMock(return_value=arena)), \
         patch("repositories.membership.criar", AsyncMock(return_value={})) as membership_criar_mock, \
         patch("repositories.membership.registrar_auditoria", AsyncMock(return_value=None)), \
         patch("repositories.arena.transferir_titularidade", AsyncMock(return_value=arena)):
        resp = await client.post("/api/admin/arenas",
            json={"nome": "X", "slug": "x", "dono_email": "quem@x.com"})

    assert resp.status_code == 201
    # titular é o criador (user_id="u1"), nunca "quem@x.com"
    assert membership_criar_mock.call_args[0][1] == "u1"


# ── Atualizar arena ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_atualizar_cor_da_arena(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    atualizada = _arena(cor_primaria="#ff0000")

    with patch("repositories.arena.atualizar", AsyncMock(return_value=atualizada)):
        resp = await client.patch(f"/api/admin/arenas/{make_uuid()}",
            json={"cor_primaria": "#ff0000"},
            headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["cor_primaria"] == "#ff0000"


@pytest.mark.asyncio
async def test_atualizar_arena_inexistente_retorna_404(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.arena.atualizar", AsyncMock(return_value=None)):
        resp = await client.patch(f"/api/admin/arenas/{make_uuid()}",
            json={"nome": "X"},
            headers=AUTH_HEADER)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_atualizar_arena_tipografia_invalida_retorna_422(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.patch(f"/api/admin/arenas/{make_uuid()}",
        json={"tipografia": "papyrus"},
        headers=AUTH_HEADER)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_admin_edita_a_propria_arena(client):
    arena_id = make_uuid()
    admin_da_arena = AdminContext(
        identificador="admin@x.com", user_id=make_uuid(), super=False,
        vinculos=[{"arena_id": arena_id, "role": "admin"}],
    )
    app.dependency_overrides[require_admin] = lambda: admin_da_arena
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.arena.atualizar", AsyncMock(return_value=_arena(id=arena_id, cor_primaria="#ff0000"))):
        resp = await client.patch(f"/api/admin/arenas/{arena_id}", json={"cor_primaria": "#ff0000"})

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_admin_nao_edita_arena_de_terceiro(client):
    """Adversarial: admin de uma arena não edita outra, mesmo sabendo o id."""
    arena_de_outro = make_uuid()
    admin_de_outra_arena = AdminContext(
        identificador="admin@x.com", user_id=make_uuid(), super=False,
        vinculos=[{"arena_id": make_uuid(), "role": "admin"}],
    )
    app.dependency_overrides[require_admin] = lambda: admin_de_outra_arena
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.patch(f"/api/admin/arenas/{arena_de_outro}", json={"cor_primaria": "#ff0000"})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_moderador_nao_edita_arena(client):
    arena_id = make_uuid()
    moderador = AdminContext(
        identificador="mod@x.com", user_id=make_uuid(), super=False,
        vinculos=[{"arena_id": arena_id, "role": "moderador"}],
    )
    app.dependency_overrides[require_admin] = lambda: moderador
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.patch(f"/api/admin/arenas/{arena_id}", json={"cor_primaria": "#ff0000"})

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
    arena_id = make_uuid()
    dono_atual_id = make_uuid()
    usuario = _usuario()

    with patch("repositories.arena.buscar_por_id", AsyncMock(return_value=_arena(id=arena_id))), \
         patch("repositories.arena.buscar_owner_user_id", AsyncMock(return_value=dono_atual_id)), \
         patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=usuario)), \
         patch("repositories.membership.tem_vinculo_admin_ativo", AsyncMock(return_value=True)), \
         patch("repositories.arena.transferir_titularidade",
               AsyncMock(return_value=_arena(id=arena_id, owner_user_id=usuario["id"]))), \
         patch("repositories.membership.registrar_auditoria", AsyncMock()) as auditoria_mock:
        resp = await client.patch(f"/api/admin/arenas/{arena_id}/titularidade",
            json={"email": usuario["email"]})

    assert resp.status_code == 200
    assert resp.json()["owner_user_id"] == usuario["id"]
    auditoria_mock.assert_called_once_with(
        pool, acao="titularidade_transferida", user_alvo_id=usuario["id"],
        realizado_por="admin", arena_id=arena_id, role=None,
        detalhes={"dono_anterior": dono_atual_id},
    )


@pytest.mark.asyncio
async def test_dono_atual_transfere_titularidade(client):
    dono_atual_id = make_uuid()
    arena_id = make_uuid()
    dono_ctx = AdminContext(
        identificador="dono@x.com", user_id=dono_atual_id, super=False,
        vinculos=[{"arena_id": arena_id, "role": "admin"}],
    )
    app.dependency_overrides[require_admin] = lambda: dono_ctx
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    usuario = _usuario()

    with patch("repositories.arena.buscar_por_id", AsyncMock(return_value=_arena(id=arena_id))), \
         patch("repositories.arena.buscar_owner_user_id", AsyncMock(return_value=dono_atual_id)), \
         patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=usuario)), \
         patch("repositories.membership.tem_vinculo_admin_ativo", AsyncMock(return_value=True)), \
         patch("repositories.arena.transferir_titularidade",
               AsyncMock(return_value=_arena(id=arena_id, owner_user_id=usuario["id"]))), \
         patch("repositories.membership.registrar_auditoria", AsyncMock()):
        resp = await client.patch(f"/api/admin/arenas/{arena_id}/titularidade",
            json={"email": usuario["email"]})

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_admin_comum_nao_transfere_titularidade(client):
    """Adversarial: admin da arena que NÃO é o titular não pode
    transferir — só o titular atual ou super (decisão #11)."""
    arena_id = make_uuid()
    dono_atual_id = make_uuid()
    admin_comum_ctx = AdminContext(
        identificador="outro-admin@x.com", user_id=make_uuid(), super=False,
        vinculos=[{"arena_id": arena_id, "role": "admin"}],
    )
    app.dependency_overrides[require_admin] = lambda: admin_comum_ctx
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.arena.buscar_por_id", AsyncMock(return_value=_arena(id=arena_id))), \
         patch("repositories.arena.buscar_owner_user_id", AsyncMock(return_value=dono_atual_id)):
        resp = await client.patch(f"/api/admin/arenas/{arena_id}/titularidade",
            json={"email": "novo-dono@x.com"})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_de_outra_arena_nao_transfere_titularidade(client):
    """Adversarial: ser dono da arena A não dá poder nenhum sobre a
    titularidade da arena B."""
    arena_a, arena_b = make_uuid(), make_uuid()
    dono_de_a = make_uuid()
    ctx = AdminContext(
        identificador="dono-a@x.com", user_id=dono_de_a, super=False,
        vinculos=[{"arena_id": arena_a, "role": "admin"}],
    )
    app.dependency_overrides[require_admin] = lambda: ctx
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.arena.buscar_por_id", AsyncMock(return_value=_arena(id=arena_b))), \
         patch("repositories.arena.buscar_owner_user_id", AsyncMock(return_value=make_uuid())):
        resp = await client.patch(f"/api/admin/arenas/{arena_b}/titularidade",
            json={"email": "novo-dono@x.com"})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_transferir_titularidade_arena_sem_titular_bloqueia_nao_super(client):
    """Arena recém-migrada (owner_user_id NULL) — só super pode atribuir
    a primeira titularidade, ninguém é 'titular atual' ainda."""
    arena_id = make_uuid()
    ctx = AdminContext(
        identificador="admin@x.com", user_id=make_uuid(), super=False,
        vinculos=[{"arena_id": arena_id, "role": "admin"}],
    )
    app.dependency_overrides[require_admin] = lambda: ctx
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.arena.buscar_por_id", AsyncMock(return_value=_arena(id=arena_id))), \
         patch("repositories.arena.buscar_owner_user_id", AsyncMock(return_value=None)):
        resp = await client.patch(f"/api/admin/arenas/{arena_id}/titularidade",
            json={"email": "novo-dono@x.com"})

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_transferir_titularidade_arena_inexistente_retorna_404(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.arena.buscar_por_id", AsyncMock(return_value=None)):
        resp = await client.patch(f"/api/admin/arenas/{make_uuid()}/titularidade",
            json={"email": "x@x.com"})

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_transferir_titularidade_pessoa_nunca_logou_retorna_404(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    arena_id = make_uuid()

    with patch("repositories.arena.buscar_por_id", AsyncMock(return_value=_arena(id=arena_id))), \
         patch("repositories.arena.buscar_owner_user_id", AsyncMock(return_value=make_uuid())), \
         patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=None)):
        resp = await client.patch(f"/api/admin/arenas/{arena_id}/titularidade",
            json={"email": "nunca-logou@x.com"})

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_transferir_titularidade_sem_vinculo_admin_ativo_retorna_422(client):
    """Decisão #11: nunca pra um e-mail arbitrário — a pessoa precisa
    já ter vínculo admin ativo nesta arena."""
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    arena_id = make_uuid()
    usuario = _usuario()

    with patch("repositories.arena.buscar_por_id", AsyncMock(return_value=_arena(id=arena_id))), \
         patch("repositories.arena.buscar_owner_user_id", AsyncMock(return_value=make_uuid())), \
         patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=usuario)), \
         patch("repositories.membership.tem_vinculo_admin_ativo", AsyncMock(return_value=False)):
        resp = await client.patch(f"/api/admin/arenas/{arena_id}/titularidade",
            json={"email": usuario["email"]})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_transferir_titularidade_para_ja_titular_retorna_422(client):
    app.dependency_overrides[require_admin] = lambda: SUPER_CTX
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    arena_id = make_uuid()
    dono_id = make_uuid()
    usuario = _usuario(user_id=dono_id)

    with patch("repositories.arena.buscar_por_id", AsyncMock(return_value=_arena(id=arena_id))), \
         patch("repositories.arena.buscar_owner_user_id", AsyncMock(return_value=dono_id)), \
         patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=usuario)):
        resp = await client.patch(f"/api/admin/arenas/{arena_id}/titularidade",
            json={"email": usuario["email"]})

    assert resp.status_code == 422


# ── itens_por_pagina (BACKLOG_2026.md §3 item 3.2) ──────────────────────────────

@pytest.mark.asyncio
async def test_atualizar_itens_por_pagina_da_arena(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    atualizada = _arena(itens_por_pagina=50)

    with patch("repositories.arena.atualizar", AsyncMock(return_value=atualizada)):
        resp = await client.patch(f"/api/admin/arenas/{make_uuid()}",
            json={"itens_por_pagina": 50},
            headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["itens_por_pagina"] == 50


@pytest.mark.asyncio
async def test_atualizar_itens_por_pagina_zero_retorna_422(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.patch(f"/api/admin/arenas/{make_uuid()}",
        json={"itens_por_pagina": 0},
        headers=AUTH_HEADER)

    assert resp.status_code == 422


# ── Events da arena ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_listar_events_da_arena(client):
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool
    arena_id = make_uuid()

    events = [
        {"id": make_uuid(), "nome": "Canal3 Expo 2026", "slug": "canal3expo-2026",
         "ativo": True, "publico": True, "criado_em": "2026-01-01"},
    ]
    with patch("repositories.arena.listar_events_da_arena", AsyncMock(return_value=events)):
        resp = await client.get(f"/api/admin/arenas/{arena_id}/events", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_listar_events_de_arena_alheia_retorna_403(client):
    """docs/ARENA_ADMIN_SPEC.md AA.1 — achado: não checava escopo nenhum,
    deixando admin/moderador de qualquer arena listar eventos (inclusive
    não públicos) de arena alheia."""
    arena_alheia = make_uuid()
    admin_de_outra_arena = AdminContext(
        identificador="admin@x.com", user_id="u1", super=False,
        vinculos=[{"arena_id": make_uuid(), "role": "admin"}],
    )
    app.dependency_overrides[require_admin] = lambda: admin_de_outra_arena
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.get(f"/api/admin/arenas/{arena_alheia}/events")

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_moderador_lista_events_da_propria_arena(client):
    """Leitura liberada pra qualquer vínculo (admin ou moderador),
    mesmo padrão de listar_games_do_event."""
    arena_id = make_uuid()
    moderador = AdminContext(
        identificador="mod@x.com", user_id="u1", super=False,
        vinculos=[{"arena_id": arena_id, "role": "moderador"}],
    )
    app.dependency_overrides[require_admin] = lambda: moderador
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.arena.listar_events_da_arena", AsyncMock(return_value=[])):
        resp = await client.get(f"/api/admin/arenas/{arena_id}/events")

    assert resp.status_code == 200


# ── Parcerias entre arenas (docs/RANKINGS_CONFIGURAVEIS_SPEC.md §2.2) ──────────

def _parceria(**overrides):
    base = {"id": make_uuid(), "arena_origem_id": make_uuid(),
            "arena_destino_id": make_uuid(), "ativo": True, "criado_em": "2026-01-01"}
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_listar_parcerias(client):
    arena_id = make_uuid()
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.arena.buscar_por_id", AsyncMock(return_value=_arena(id=arena_id))), \
         patch("repositories.arena_partnership.listar_concedidas", AsyncMock(return_value=[_parceria()])), \
         patch("repositories.arena_partnership.listar_recebidas", AsyncMock(return_value=[])):
        resp = await client.get(f"/api/admin/arenas/{arena_id}/parcerias", headers=AUTH_HEADER)

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["concedidas"]) == 1
    assert data["recebidas"] == []


@pytest.mark.asyncio
async def test_listar_parcerias_arena_inexistente_retorna_404(client):
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.arena.buscar_por_id", AsyncMock(return_value=None)):
        resp = await client.get(f"/api/admin/arenas/{make_uuid()}/parcerias", headers=AUTH_HEADER)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_de_outra_arena_nao_lista_parcerias(client):
    """Adversarial: admin da arena A não consulta parcerias da arena B."""
    arena_b = make_uuid()
    admin_de_a = AdminContext(
        identificador="admin-a@x.com", user_id=make_uuid(), super=False,
        vinculos=[{"arena_id": make_uuid(), "role": "admin"}],
    )
    app.dependency_overrides[require_admin] = lambda: admin_de_a
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.arena.buscar_por_id", AsyncMock(return_value=_arena(id=arena_b))):
        resp = await client.get(f"/api/admin/arenas/{arena_b}/parcerias", headers=AUTH_HEADER)

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_moderador_nao_lista_parcerias(client):
    """Decisão #3: qualquer ADMIN da arena, moderador nunca."""
    arena_id = make_uuid()
    moderador = AdminContext(
        identificador="mod@x.com", user_id=make_uuid(), super=False,
        vinculos=[{"arena_id": arena_id, "role": "moderador"}],
    )
    app.dependency_overrides[require_admin] = lambda: moderador
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.arena.buscar_por_id", AsyncMock(return_value=_arena(id=arena_id))):
        resp = await client.get(f"/api/admin/arenas/{arena_id}/parcerias", headers=AUTH_HEADER)

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_liberar_parceria(client):
    """Efeito imediato — origem já libera pra destino sem exigir aceite
    antes (decisão #5). Auditoria gravada (decisão #6)."""
    origem_id, destino_id = make_uuid(), make_uuid()
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.arena.buscar_por_id", AsyncMock(side_effect=[_arena(id=origem_id), _arena(id=destino_id)])), \
         patch("repositories.arena_partnership.criar_ou_reativar",
               AsyncMock(return_value=_parceria(arena_origem_id=origem_id, arena_destino_id=destino_id))), \
         patch("repositories.membership.registrar_auditoria", AsyncMock()) as auditoria_mock:
        resp = await client.post(f"/api/admin/arenas/{origem_id}/parcerias/{destino_id}/liberar",
            headers=AUTH_HEADER)

    assert resp.status_code == 201
    assert resp.json()["arena_destino_id"] == destino_id
    auditoria_mock.assert_called_once_with(
        pool, acao="parceria_liberada", user_alvo_id=None,
        realizado_por="admin", arena_id=origem_id, role=None,
        detalhes={"arena_destino_id": destino_id},
    )


@pytest.mark.asyncio
async def test_liberar_parceria_para_si_mesma_retorna_422(client):
    arena_id = make_uuid()
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post(f"/api/admin/arenas/{arena_id}/parcerias/{arena_id}/liberar",
        headers=AUTH_HEADER)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_moderador_nao_libera_parceria(client):
    arena_id = make_uuid()
    moderador = AdminContext(
        identificador="mod@x.com", user_id=make_uuid(), super=False,
        vinculos=[{"arena_id": arena_id, "role": "moderador"}],
    )
    app.dependency_overrides[require_admin] = lambda: moderador
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.arena.buscar_por_id", AsyncMock(return_value=_arena(id=arena_id))):
        resp = await client.post(f"/api/admin/arenas/{arena_id}/parcerias/{make_uuid()}/liberar",
            headers=AUTH_HEADER)

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_aceitar_parceria_com_liberacao_ativa(client):
    """arena_id aceita liberação de origem_id — cria a linha recíproca,
    fechando a mutualidade (decisão #2)."""
    arena_id, origem_id = make_uuid(), make_uuid()
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.arena.buscar_por_id", AsyncMock(side_effect=[_arena(id=arena_id), _arena(id=origem_id)])), \
         patch("repositories.arena_partnership.buscar",
               AsyncMock(return_value=_parceria(arena_origem_id=origem_id, arena_destino_id=arena_id, ativo=True))), \
         patch("repositories.arena_partnership.criar_ou_reativar",
               AsyncMock(return_value=_parceria(arena_origem_id=arena_id, arena_destino_id=origem_id))), \
         patch("repositories.membership.registrar_auditoria", AsyncMock()) as auditoria_mock:
        resp = await client.post(f"/api/admin/arenas/{arena_id}/parcerias/{origem_id}/aceitar",
            headers=AUTH_HEADER)

    assert resp.status_code == 201
    auditoria_mock.assert_called_once_with(
        pool, acao="parceria_aceita", user_alvo_id=None,
        realizado_por="admin", arena_id=arena_id, role=None,
        detalhes={"arena_origem_id": origem_id},
    )


@pytest.mark.asyncio
async def test_aceitar_parceria_sem_liberacao_ativa_retorna_422(client):
    """Não há o que aceitar se a origem nunca liberou (ou já revogou)."""
    arena_id, origem_id = make_uuid(), make_uuid()
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.arena.buscar_por_id", AsyncMock(side_effect=[_arena(id=arena_id), _arena(id=origem_id)])), \
         patch("repositories.arena_partnership.buscar", AsyncMock(return_value=None)):
        resp = await client.post(f"/api/admin/arenas/{arena_id}/parcerias/{origem_id}/aceitar",
            headers=AUTH_HEADER)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_aceitar_parceria_liberacao_revogada_retorna_422(client):
    arena_id, origem_id = make_uuid(), make_uuid()
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.arena.buscar_por_id", AsyncMock(side_effect=[_arena(id=arena_id), _arena(id=origem_id)])), \
         patch("repositories.arena_partnership.buscar",
               AsyncMock(return_value=_parceria(ativo=False))):
        resp = await client.post(f"/api/admin/arenas/{arena_id}/parcerias/{origem_id}/aceitar",
            headers=AUTH_HEADER)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_aceitar_parceria_para_si_mesma_retorna_422(client):
    arena_id = make_uuid()
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    resp = await client.post(f"/api/admin/arenas/{arena_id}/parcerias/{arena_id}/aceitar",
        headers=AUTH_HEADER)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_revogar_parceria(client):
    """Só a própria concessão é revogada — a linha recíproca não é
    tocada (decisão #5, pode ficar assimétrica)."""
    origem_id, destino_id = make_uuid(), make_uuid()
    pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: pool

    with patch("repositories.arena.buscar_por_id", AsyncMock(return_value=_arena(id=origem_id))), \
         patch("repositories.arena_partnership.revogar",
               AsyncMock(return_value=_parceria(arena_origem_id=origem_id, arena_destino_id=destino_id, ativo=False))), \
         patch("repositories.membership.registrar_auditoria", AsyncMock()) as auditoria_mock:
        resp = await client.post(f"/api/admin/arenas/{origem_id}/parcerias/{destino_id}/revogar",
            headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["ativo"] is False
    auditoria_mock.assert_called_once_with(
        pool, acao="parceria_revogada", user_alvo_id=None,
        realizado_por="admin", arena_id=origem_id, role=None,
        detalhes={"arena_destino_id": destino_id},
    )


@pytest.mark.asyncio
async def test_revogar_parceria_inexistente_retorna_404(client):
    arena_id = make_uuid()
    app.dependency_overrides[get_pool] = lambda: MagicMock()

    with patch("repositories.arena.buscar_por_id", AsyncMock(return_value=_arena(id=arena_id))), \
         patch("repositories.arena_partnership.revogar", AsyncMock(return_value=None)):
        resp = await client.post(f"/api/admin/arenas/{arena_id}/parcerias/{make_uuid()}/revogar",
            headers=AUTH_HEADER)

    assert resp.status_code == 404
