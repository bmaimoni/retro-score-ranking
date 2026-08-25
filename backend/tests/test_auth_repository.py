"""
Testes de auth/repository.py — funções de nick_claims adicionadas pra
suportar troca de nick com soft-release (docs/NICKNAME_SPEC.md).
"""
import uuid
import pytest
import auth.repository as auth_repo


def make_uuid():
    return str(uuid.uuid4())


# ── buscar_nick_claim: só o claim ativo ─────────────────────────────────────

@pytest.mark.asyncio
async def test_buscar_nick_claim_filtra_por_ativo(fake_pool):
    fake_pool.set_fetchrow({
        "id": make_uuid(), "nick": "Campeao", "nick_norm": "campeao",
        "user_id": make_uuid(), "ativo": True, "criado_em": "2026-01-01",
    })

    resultado = await auth_repo.buscar_nick_claim(fake_pool, "campeao")

    sql = " ".join(fake_pool.fetchrow.call_args[0][0].split())
    assert "ativo = true" in sql
    assert resultado["ativo"] is True


@pytest.mark.asyncio
async def test_buscar_nick_claim_liberado_retorna_none(fake_pool):
    """Um claim liberado (ativo=false) não deve bloquear ninguém —
    a query já filtra isso no banco, não precisa checar em Python."""
    fake_pool.set_fetchrow(None)
    resultado = await auth_repo.buscar_nick_claim(fake_pool, "campeao")
    assert resultado is None


# ── nick_ja_foi_reivindicado_alguma_vez ──────────────────────────────────────

@pytest.mark.asyncio
async def test_nick_ja_foi_reivindicado_true(fake_pool):
    fake_pool.set_fetchval(True)
    resultado = await auth_repo.nick_ja_foi_reivindicado_alguma_vez(fake_pool, "campeao")
    assert resultado is True


@pytest.mark.asyncio
async def test_nick_ja_foi_reivindicado_false(fake_pool):
    fake_pool.set_fetchval(False)
    resultado = await auth_repo.nick_ja_foi_reivindicado_alguma_vez(fake_pool, "novato")
    assert resultado is False


# ── buscar_claim_ativo_do_usuario ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_buscar_claim_ativo_do_usuario(fake_pool):
    user_id = make_uuid()
    fake_pool.set_fetchrow({
        "id": make_uuid(), "nick": "Campeao", "nick_norm": "campeao",
        "user_id": user_id, "ativo": True, "criado_em": "2026-01-01", "em_cooldown": True,
    })

    resultado = await auth_repo.buscar_claim_ativo_do_usuario(fake_pool, user_id)

    sql = " ".join(fake_pool.fetchrow.call_args[0][0].split())
    assert "ativo = true" in sql
    assert "ORDER BY criado_em DESC" in sql
    assert resultado["em_cooldown"] is True


@pytest.mark.asyncio
async def test_buscar_claim_ativo_do_usuario_sem_claim_retorna_none(fake_pool):
    fake_pool.set_fetchrow(None)
    resultado = await auth_repo.buscar_claim_ativo_do_usuario(fake_pool, make_uuid())
    assert resultado is None


# ── criar_nick_claim: grava nick + nick_norm ────────────────────────────────

@pytest.mark.asyncio
async def test_criar_nick_claim_grava_nick_e_nick_norm(fake_pool):
    user_id = make_uuid()
    fake_pool.set_fetchrow({
        "id": make_uuid(), "nick": "Campeao", "nick_norm": "campeao",
        "user_id": user_id, "ativo": True, "criado_em": "2026-01-01",
    })

    resultado = await auth_repo.criar_nick_claim(fake_pool, "Campeao", "campeao", user_id)

    assert resultado["nick"] == "Campeao"
    args = fake_pool.fetchrow.call_args[0]
    assert args[1:] == ("Campeao", "campeao", user_id)


# ── liberar_claim: soft-release, nunca DELETE ───────────────────────────────

@pytest.mark.asyncio
async def test_liberar_claim_e_update_sem_delete(fake_pool):
    claim_id = make_uuid()
    await auth_repo.liberar_claim(fake_pool, claim_id)

    sql = " ".join(fake_pool.execute.call_args[0][0].split())
    assert "UPDATE nick_claims SET ativo = false" in sql
    assert "DELETE" not in sql


# ── listar_historico_nicks (decisão #4) ─────────────────────────────────────

@pytest.mark.asyncio
async def test_listar_historico_nicks_ordenado_mais_recente_primeiro(fake_pool):
    user_id = make_uuid()
    fake_pool.set_fetch([
        {"id": make_uuid(), "nick": "NickNovo", "nick_norm": "nicknovo", "ativo": True, "criado_em": "2026-02-01"},
        {"id": make_uuid(), "nick": "NickVelho", "nick_norm": "nickvelho", "ativo": False, "criado_em": "2026-01-01"},
    ])

    resultado = await auth_repo.listar_historico_nicks(fake_pool, user_id)

    assert len(resultado) == 2
    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "ORDER BY criado_em DESC" in sql


# ── registrar_troca_forcada (decisão #10) ───────────────────────────────────

@pytest.mark.asyncio
async def test_registrar_troca_forcada_grava_auditoria(fake_pool):
    user_id = make_uuid()
    await auth_repo.registrar_troca_forcada(
        fake_pool, user_id=user_id, nick_anterior="Ofensivo", nick_novo="Corrigido",
        realizado_por="mod@x.com",
    )

    sql = " ".join(fake_pool.execute.call_args[0][0].split())
    args = fake_pool.execute.call_args[0]
    assert "INSERT INTO nick_troca_forcada_auditoria" in sql
    assert args[1:] == (user_id, "Ofensivo", "Corrigido", "mod@x.com")


@pytest.mark.asyncio
async def test_registrar_troca_forcada_nick_anterior_none_primeira_reivindicacao(fake_pool):
    """Forçar a PRIMEIRA reivindicação de alguém — sem nick anterior
    pra registrar (nick_anterior fica NULL, não string vazia)."""
    user_id = make_uuid()
    await auth_repo.registrar_troca_forcada(
        fake_pool, user_id=user_id, nick_anterior=None, nick_novo="Novato",
        realizado_por="mod@x.com",
    )

    args = fake_pool.execute.call_args[0]
    assert args[2] is None
