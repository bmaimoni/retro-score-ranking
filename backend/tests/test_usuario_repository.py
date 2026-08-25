"""
Testes de repositories/usuario.py — leitura/edição de perfil.
Ver docs/BACKLOG_2026.md §1 e migration 020.
"""
import pytest
import repositories.usuario as usuario_repo


@pytest.mark.asyncio
async def test_buscar_perfil(fake_pool):
    fake_pool.set_fetchrow({
        "id": "u1", "email": "p@x.com", "nome": "Pessoa", "foto_url": None,
        "status": "ativo", "nome_completo": "Pessoa Completa",
        "data_nascimento": None, "cidade": None, "estado": None, "telefone": None,
        "avatar_id": None, "criado_em": "2026-01-01", "ultimo_login_em": None,
    })

    resultado = await usuario_repo.buscar_perfil(fake_pool, "u1")

    assert resultado["nome_completo"] == "Pessoa Completa"


@pytest.mark.asyncio
async def test_buscar_perfil_inexistente_retorna_none(fake_pool):
    fake_pool.set_fetchrow(None)
    resultado = await usuario_repo.buscar_perfil(fake_pool, "nao-existe")
    assert resultado is None


@pytest.mark.asyncio
async def test_atualizar_perfil_campos_parciais(fake_pool):
    """Só os campos presentes em `dados` devem ser repassados como
    não-None — os demais ficam None pro COALESCE preservar o valor atual."""
    fake_pool.set_fetchrow({
        "id": "u1", "email": "p@x.com", "nome": "Pessoa", "foto_url": None,
        "status": "ativo", "nome_completo": None, "data_nascimento": None,
        "cidade": "São Paulo", "estado": None, "telefone": None,
        "avatar_id": None, "criado_em": "2026-01-01", "ultimo_login_em": None,
    })

    await usuario_repo.atualizar_perfil(fake_pool, "u1", {"cidade": "São Paulo"})

    args = fake_pool.fetchrow.call_args[0]
    # (sql, user_id, nome_completo, data_nascimento, cidade, estado, telefone, avatar_id)
    assert args[1] == "u1"
    assert args[2] is None            # nome_completo não foi passado
    assert args[4] == "São Paulo"     # cidade foi passado
    assert args[5] is None            # estado não foi passado


@pytest.mark.asyncio
async def test_atualizar_perfil_inexistente_retorna_none(fake_pool):
    fake_pool.set_fetchrow(None)
    resultado = await usuario_repo.atualizar_perfil(fake_pool, "nao-existe", {"cidade": "X"})
    assert resultado is None
