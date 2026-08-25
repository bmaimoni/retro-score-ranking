"""
Testes de integração: POST /api/e/{slug}/upload + nick_claims
(AUTH_SPEC.md §4.3 combinado com EVENTOS_SPEC.md §4.1).

Cobre especificamente o que muda no upload com a autenticação: nick
livre reivindicado por quem loga, bloqueio de nick de terceiro, e
fluxo anônimo continuando a funcionar sem sessão.
"""
import io
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from main import app
from utils.db import get_pool
import auth.service as auth_svc

JOGO_ID     = "550e8400-e29b-41d4-a716-446655440000"
EVENTO_SLUG = "canal3expo"
URL         = f"/api/e/{EVENTO_SLUG}/upload"
FOTO_URL    = "https://cdn.example.com/foto.jpg"


def make_uuid():
    return str(uuid.uuid4())


def make_jpeg_bytes():
    return (b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
            b"\xff\xd9")


def _evento():
    return {
        "id": make_uuid(), "nome": "Canal3 Expo", "slug": EVENTO_SLUG,
        "ativo": True, "publico": True,
        "data_inicio": datetime.now(timezone.utc) - timedelta(days=1),
        "data_fim":    datetime.now(timezone.utc) + timedelta(days=1),
    }


def _usuario():
    return {"id": make_uuid(), "email": "pessoa@example.com", "email_verified": True,
            "nome": "Pessoa", "foto_url": None, "status": "ativo"}


def _entrada(user_id=None):
    return {
        "id": make_uuid(), "jogo_id": JOGO_ID, "nick": "CAMPEAO", "nome": None,
        "pontuacao": 5000, "foto_url": FOTO_URL, "no_ranking": True, "pendente": False,
        "criado_em": "2026-01-01", "evento_id": make_uuid(), "user_id": user_id,
    }


class _FakeTxn:
    async def __aenter__(self): return self
    async def __aexit__(self, *_): pass


class _FakeConn:
    def __init__(self, entry):
        self.fetchrow    = AsyncMock(return_value=entry)
        self.execute     = AsyncMock(return_value="UPDATE 1")
        self.transaction = MagicMock(return_value=_FakeTxn())
    async def __aenter__(self): return self
    async def __aexit__(self, *_): pass


def _make_pool(entry):
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)
    pool.fetchval = AsyncMock(return_value=0)
    pool.acquire  = MagicMock(return_value=_FakeConn(entry))
    return pool


def _base_patches(entry, extra_nick_claim_patches=None):
    patches = [
        patch("routers.evento_publico.evento_repo.buscar_por_slug", AsyncMock(return_value=_evento())),
        patch("routers.evento_publico.storage.upload_foto",   AsyncMock(return_value=FOTO_URL)),
        patch("routers.evento_publico.rl.checar_rate_limit",  AsyncMock(return_value=False)),
        patch("routers.evento_publico.score_svc.validar_score", AsyncMock(return_value=None)),
        patch("routers.evento_publico.nick_svc.marcar_anterior_como_superado", AsyncMock(return_value=None)),
        patch("routers.evento_publico.broker.publish",          AsyncMock()),
        patch("routers.evento_publico.entrada_repo.inserir",    AsyncMock(return_value=entry)),
        patch("routers.evento_publico._slug_from_id",           AsyncMock(return_value="pac-man")),
    ]
    if extra_nick_claim_patches:
        patches.extend(extra_nick_claim_patches)
    return patches


def _apply(patches):
    from contextlib import ExitStack
    stack = ExitStack()
    for p in patches:
        stack.enter_context(p)
    return stack


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.pop(get_pool, None)


# ── Anônimo (sem sessão) ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_anonimo_nick_livre_funciona_normal(client):
    """Sem cookie de sessão nenhum — comportamento idêntico a antes da
    autenticação existir, desde que o nick não tenha dono."""
    entry = _entrada()
    pool = _make_pool(entry)
    app.dependency_overrides[get_pool] = lambda: pool

    patches = _base_patches(entry, [
        patch("auth.repository.buscar_nick_claim", AsyncMock(return_value=None)),
    ])
    with _apply(patches):
        resp = await client.post(URL,
            data={"nick": "NOVATO", "pontuacao": "5000", "jogo_id": JOGO_ID},
            files=[("foto", ("f.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg"))])

    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_anonimo_nick_reivindicado_por_outro_bloqueia_409(client):
    """Nick já pertence a uma conta logada em outro momento — visitante
    anônimo tentando usá-lo recebe 409, com mensagem clara."""
    entry = _entrada()
    pool = _make_pool(entry)
    app.dependency_overrides[get_pool] = lambda: pool

    claim = {"id": make_uuid(), "nick_norm": "campeao", "user_id": make_uuid(), "criado_em": "2026-01-01"}
    patches = _base_patches(entry, [
        patch("auth.repository.buscar_nick_claim", AsyncMock(return_value=claim)),
    ])
    with _apply(patches):
        resp = await client.post(URL,
            data={"nick": "CAMPEAO", "pontuacao": "5000", "jogo_id": JOGO_ID},
            files=[("foto", ("f.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg"))])

    assert resp.status_code == 409
    assert "faça login" in resp.json()["detail"].lower()


# ── Logado (com sessão) ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_logado_nick_livre_e_reivindicado(client):
    usuario = _usuario()
    entry = _entrada(user_id=usuario["id"])
    pool = _make_pool(entry)
    app.dependency_overrides[get_pool] = lambda: pool
    inserir_mock = AsyncMock(return_value=entry)

    client.cookies.set("canal3_session", "sessao-valida")
    patches = [
        patch("routers.evento_publico.evento_repo.buscar_por_slug", AsyncMock(return_value=_evento())),
        patch("routers.evento_publico.storage.upload_foto",   AsyncMock(return_value=FOTO_URL)),
        patch("routers.evento_publico.rl.checar_rate_limit",  AsyncMock(return_value=False)),
        patch("routers.evento_publico.score_svc.validar_score", AsyncMock(return_value=None)),
        patch("routers.evento_publico.nick_svc.marcar_anterior_como_superado", AsyncMock(return_value=None)),
        patch("routers.evento_publico.broker.publish",          AsyncMock()),
        patch("routers.evento_publico.entrada_repo.inserir",    inserir_mock),
        patch("routers.evento_publico._slug_from_id",           AsyncMock(return_value="pac-man")),
        patch("auth.service.obter_usuario_da_sessao", AsyncMock(return_value=usuario)),
        patch("auth.repository.buscar_nick_claim", AsyncMock(return_value=None)),
        patch("auth.repository.nick_ja_foi_reivindicado_alguma_vez", AsyncMock(return_value=False)),
        patch("auth.repository.criar_nick_claim", AsyncMock()),
        patch("repositories.entrada.vincular_retroativamente", AsyncMock()),
    ]
    with _apply(patches):
        resp = await client.post(URL,
            data={"nick": "NOVATO", "pontuacao": "5000", "jogo_id": JOGO_ID},
            files=[("foto", ("f.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg"))])

    assert resp.status_code == 201
    dados_inseridos = inserir_mock.call_args[0][1]
    assert dados_inseridos.get("user_id") == usuario["id"]


@pytest.mark.asyncio
async def test_logado_nick_de_outro_usuario_bloqueia_409(client):
    usuario = _usuario()
    outro_dono_id = make_uuid()
    entry = _entrada()
    pool = _make_pool(entry)
    app.dependency_overrides[get_pool] = lambda: pool

    client.cookies.set("canal3_session", "sessao-valida")
    claim = {"id": make_uuid(), "nick_norm": "campeao", "user_id": outro_dono_id, "criado_em": "2026-01-01"}
    patches = _base_patches(entry, [
        patch("auth.service.obter_usuario_da_sessao", AsyncMock(return_value=usuario)),
        patch("auth.repository.buscar_nick_claim", AsyncMock(return_value=claim)),
    ])
    with _apply(patches):
        resp = await client.post(URL,
            data={"nick": "CAMPEAO", "pontuacao": "5000", "jogo_id": JOGO_ID},
            files=[("foto", ("f.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg"))])

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_logado_reenvia_com_proprio_nick_ja_reivindicado_funciona(client):
    """Segunda vez que a mesma pessoa logada envia score com o nick que
    ela mesma já reivindicou antes — segue normal, sem re-reivindicar."""
    usuario = _usuario()
    entry = _entrada(user_id=usuario["id"])
    pool = _make_pool(entry)
    app.dependency_overrides[get_pool] = lambda: pool

    client.cookies.set("canal3_session", "sessao-valida")
    claim = {"id": make_uuid(), "nick_norm": "campeao", "user_id": usuario["id"], "criado_em": "2026-01-01"}
    criar_claim_mock = AsyncMock()
    patches = _base_patches(entry, [
        patch("auth.service.obter_usuario_da_sessao", AsyncMock(return_value=usuario)),
        patch("auth.repository.buscar_nick_claim", AsyncMock(return_value=claim)),
        patch("auth.repository.criar_nick_claim", criar_claim_mock),
    ])
    with _apply(patches):
        resp = await client.post(URL,
            data={"nick": "CAMPEAO", "pontuacao": "5000", "jogo_id": JOGO_ID},
            files=[("foto", ("f.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg"))])

    assert resp.status_code == 201
    criar_claim_mock.assert_not_called()  # já era dele, não recria claim


@pytest.mark.asyncio
async def test_sessao_invalida_trata_como_anonimo(client):
    """Cookie presente mas sessão expirada/revogada: sessao_opcional
    retorna None, upload segue como anônimo (não quebra, não bloqueia
    à toa)."""
    entry = _entrada()
    pool = _make_pool(entry)
    app.dependency_overrides[get_pool] = lambda: pool

    client.cookies.set("canal3_session", "sessao-expirada")
    patches = _base_patches(entry, [
        patch("auth.service.obter_usuario_da_sessao", AsyncMock(return_value=None)),
        patch("auth.repository.buscar_nick_claim", AsyncMock(return_value=None)),
    ])
    with _apply(patches):
        resp = await client.post(URL,
            data={"nick": "NOVATO", "pontuacao": "5000", "jogo_id": JOGO_ID},
            files=[("foto", ("f.jpg", io.BytesIO(make_jpeg_bytes()), "image/jpeg"))])

    assert resp.status_code == 201
