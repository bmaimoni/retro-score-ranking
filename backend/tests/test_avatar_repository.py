"""
Testes de repositories/avatar.py — galeria curada por super-admin.
Ver docs/BACKLOG_2026.md §1, ponto cego #3, e migration 020.
"""
import uuid
import pytest
import repositories.avatar as avatar_repo


def make_uuid():
    return str(uuid.uuid4())


@pytest.mark.asyncio
async def test_listar_todos(fake_pool):
    fake_pool.set_fetch([
        {"id": make_uuid(), "nome": "Robô", "url": "https://cdn/robo.png", "ativo": True, "criado_em": "2026-01-01"},
        {"id": make_uuid(), "nome": "Fantasma", "url": "https://cdn/fantasma.png", "ativo": False, "criado_em": "2026-01-01"},
    ])

    resultado = await avatar_repo.listar_todos(fake_pool)

    assert len(resultado) == 2
    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "WHERE" not in sql  # lista tudo, ativos e inativos


@pytest.mark.asyncio
async def test_listar_ativos_filtra(fake_pool):
    fake_pool.set_fetch([
        {"id": make_uuid(), "nome": "Robô", "url": "https://cdn/robo.png"},
    ])

    resultado = await avatar_repo.listar_ativos(fake_pool)

    assert len(resultado) == 1
    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "ativo = true" in sql


@pytest.mark.asyncio
async def test_buscar_por_id(fake_pool):
    avatar_id = make_uuid()
    fake_pool.set_fetchrow({"id": avatar_id, "nome": "Robô", "url": "https://cdn/robo.png", "ativo": True, "criado_em": "2026-01-01"})

    resultado = await avatar_repo.buscar_por_id(fake_pool, avatar_id)

    assert resultado["id"] == avatar_id


@pytest.mark.asyncio
async def test_buscar_por_id_inexistente_retorna_none(fake_pool):
    fake_pool.set_fetchrow(None)
    resultado = await avatar_repo.buscar_por_id(fake_pool, "nao-existe")
    assert resultado is None


@pytest.mark.asyncio
async def test_criar_avatar(fake_pool):
    fake_pool.set_fetchrow({"id": make_uuid(), "nome": "Robô", "url": "https://cdn/robo.png", "ativo": True, "criado_em": "2026-01-01"})

    resultado = await avatar_repo.criar(fake_pool, "Robô", "https://cdn/robo.png")

    assert resultado["nome"] == "Robô"
    args = fake_pool.fetchrow.call_args[0]
    assert args[1:] == ("Robô", "https://cdn/robo.png")


@pytest.mark.asyncio
async def test_atualizar_ativo_desativa_sem_delete(fake_pool):
    avatar_id = make_uuid()
    fake_pool.set_fetchrow({"id": avatar_id, "nome": "Robô", "url": "https://cdn/robo.png", "ativo": False, "criado_em": "2026-01-01"})

    resultado = await avatar_repo.atualizar_ativo(fake_pool, avatar_id, False)

    sql = " ".join(fake_pool.fetchrow.call_args[0][0].split())
    assert "UPDATE avatares SET ativo" in sql
    assert "DELETE" not in sql
    assert resultado["ativo"] is False


@pytest.mark.asyncio
async def test_atualizar_ativo_inexistente_retorna_none(fake_pool):
    fake_pool.set_fetchrow(None)
    resultado = await avatar_repo.atualizar_ativo(fake_pool, "nao-existe", True)
    assert resultado is None
