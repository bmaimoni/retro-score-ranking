"""
Testes de repositories/seguidor.py — docs/SEGUIR_SPEC.md.
"""
import uuid
import pytest
import repositories.seguidor as seguidor_repo


def make_uuid():
    return str(uuid.uuid4())


# ── seguir / deixar_de_seguir ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_seguir_cria_vinculo(fake_pool):
    seguidor_id, seguido_id = make_uuid(), make_uuid()
    fake_pool.set_fetchrow({
        "id": make_uuid(), "seguidor_id": seguidor_id, "seguido_id": seguido_id,
        "ativo": True, "criado_em": "2026-01-01",
    })

    resultado = await seguidor_repo.seguir(fake_pool, seguidor_id, seguido_id)

    assert resultado["ativo"] is True
    sql = " ".join(fake_pool.fetchrow.call_args[0][0].split())
    assert "ON CONFLICT" in sql
    assert "DO UPDATE SET ativo = true" in sql


@pytest.mark.asyncio
async def test_deixar_de_seguir_e_soft_sem_delete(fake_pool):
    seguidor_id, seguido_id = make_uuid(), make_uuid()
    fake_pool.set_fetchrow({
        "id": make_uuid(), "seguidor_id": seguidor_id, "seguido_id": seguido_id,
        "ativo": False, "criado_em": "2026-01-01",
    })

    resultado = await seguidor_repo.deixar_de_seguir(fake_pool, seguidor_id, seguido_id)

    assert resultado["ativo"] is False
    sql = " ".join(fake_pool.fetchrow.call_args[0][0].split())
    assert "UPDATE seguidores SET ativo = false" in sql
    assert "DELETE" not in sql


@pytest.mark.asyncio
async def test_deixar_de_seguir_quem_nao_segue_retorna_none(fake_pool):
    fake_pool.set_fetchrow(None)
    resultado = await seguidor_repo.deixar_de_seguir(fake_pool, make_uuid(), make_uuid())
    assert resultado is None


# ── listar_seguindo / listar_seguidores ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_listar_seguindo(fake_pool):
    fake_pool.set_fetch([{"id": make_uuid(), "nome": "Ciclano", "email": "c@x.com",
                           "foto_url": None, "avatar_id": None, "seguindo_desde": "2026-01-01"}])

    resultado = await seguidor_repo.listar_seguindo(fake_pool, make_uuid())

    assert len(resultado) == 1
    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "s.seguidor_id = $1" in sql
    assert "s.ativo = true" in sql


@pytest.mark.asyncio
async def test_listar_seguidores(fake_pool):
    fake_pool.set_fetch([{"id": make_uuid(), "nome": "Fulano", "email": "f@x.com",
                           "foto_url": None, "avatar_id": None, "seguindo_desde": "2026-01-01"}])

    resultado = await seguidor_repo.listar_seguidores(fake_pool, make_uuid())

    assert len(resultado) == 1
    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "s.seguido_id = $1" in sql
    assert "s.ativo = true" in sql


# ── compilar_atividade (decisões #1/#2/#3/#6) ───────────────────────────────────

@pytest.mark.asyncio
async def test_compilar_atividade_passa_user_id_e_desde(fake_pool):
    user_id = make_uuid()
    fake_pool.set_fetch([])

    await seguidor_repo.compilar_atividade(fake_pool, user_id, "2026-01-01T00:00:00")

    args = fake_pool.fetch.call_args[0]
    assert args[1] == user_id
    assert args[2] == "2026-01-01T00:00:00"


@pytest.mark.asyncio
async def test_compilar_atividade_aceita_desde_none(fake_pool):
    """Primeira vez que a pessoa confere o feed — GREATEST ignora NULL,
    usa só seguindo_desde como corte."""
    fake_pool.set_fetch([])
    await seguidor_repo.compilar_atividade(fake_pool, make_uuid(), None)

    args = fake_pool.fetch.call_args[0]
    assert args[2] is None


@pytest.mark.asyncio
async def test_compilar_atividade_compara_melhor_score_por_game(fake_pool):
    fake_pool.set_fetch([{
        "seguido_id": make_uuid(), "seguido_nome": "Ciclano", "seguido_email": "c@x.com",
        "game_id": make_uuid(), "game_nome": "Pac-Man", "game_slug": "pac-man",
        "pontuacao_seguido": 9000, "minha_pontuacao": 5000, "criado_em": "2026-02-01",
    }])

    resultado = await seguidor_repo.compilar_atividade(fake_pool, make_uuid(), "2026-01-01")

    assert len(resultado) == 1
    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "ms.pontuacao_seguido > mm.minha_pontuacao" in sql
    assert "GREATEST(ms.seguindo_desde, $2)" in sql
    assert "DISTINCT ON (e.user_id, e.game_id)" in sql
