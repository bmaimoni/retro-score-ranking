"""
Testes de repositories/marca_parceria.py — concessões unidirecionais
de acesso a placar entre marcas (docs/RANKINGS_CONFIGURAVEIS_SPEC.md
§2.2 e §4).
"""
import pytest
import repositories.marca_parceria as parceria_repo


@pytest.mark.asyncio
async def test_buscar_retorna_linha_existente(fake_pool):
    fake_pool.set_fetchrow({
        "id": "p1", "marca_origem_id": "a", "marca_destino_id": "b",
        "ativo": True, "criado_em": "2026-01-01",
    })

    resultado = await parceria_repo.buscar(fake_pool, "a", "b")

    assert resultado["ativo"] is True
    assert fake_pool.fetchrow.call_args[0][1:] == ("a", "b")


@pytest.mark.asyncio
async def test_buscar_inexistente_retorna_none(fake_pool):
    fake_pool.set_fetchrow(None)
    resultado = await parceria_repo.buscar(fake_pool, "a", "b")
    assert resultado is None


@pytest.mark.asyncio
async def test_criar_ou_reativar_usa_upsert_com_on_conflict(fake_pool):
    """Precisa reativar (ativo=true) uma parceria revogada antes, não
    duplicar linha — a UNIQUE(origem, destino) já impediria duplicar,
    mas o comportamento certo é reativar, não estourar erro."""
    fake_pool.set_fetchrow({
        "id": "p1", "marca_origem_id": "a", "marca_destino_id": "b",
        "ativo": True, "criado_em": "2026-01-01",
    })

    resultado = await parceria_repo.criar_ou_reativar(fake_pool, "a", "b")

    assert resultado["ativo"] is True
    sql = " ".join(fake_pool.fetchrow.call_args[0][0].split())
    assert "ON CONFLICT (marca_origem_id, marca_destino_id)" in sql
    assert "DO UPDATE SET ativo = true" in sql
    assert fake_pool.fetchrow.call_args[0][1:] == ("a", "b")


@pytest.mark.asyncio
async def test_revogar_so_afeta_a_propria_linha(fake_pool):
    fake_pool.set_fetchrow({
        "id": "p1", "marca_origem_id": "a", "marca_destino_id": "b",
        "ativo": False, "criado_em": "2026-01-01",
    })

    resultado = await parceria_repo.revogar(fake_pool, "a", "b")

    assert resultado["ativo"] is False
    sql = " ".join(fake_pool.fetchrow.call_args[0][0].split())
    assert "SET ativo = false" in sql
    assert "marca_origem_id = $1 AND marca_destino_id = $2 AND ativo = true" in sql


@pytest.mark.asyncio
async def test_revogar_sem_concessao_ativa_retorna_none(fake_pool):
    fake_pool.set_fetchrow(None)
    resultado = await parceria_repo.revogar(fake_pool, "a", "b")
    assert resultado is None


@pytest.mark.asyncio
async def test_listar_concedidas_filtra_por_origem(fake_pool):
    fake_pool.set_fetch([
        {"id": "p1", "marca_destino_id": "b", "marca_destino_nome": "Marca B",
         "ativo": True, "criado_em": "2026-01-01"},
    ])

    resultado = await parceria_repo.listar_concedidas(fake_pool, "a")

    assert len(resultado) == 1
    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "WHERE mp.marca_origem_id = $1" in sql
    assert fake_pool.fetch.call_args[0][1] == "a"


@pytest.mark.asyncio
async def test_listar_recebidas_so_ativas_com_flag_reciproca(fake_pool):
    fake_pool.set_fetch([
        {"id": "p1", "marca_origem_id": "b", "marca_origem_nome": "Marca B",
         "ativo": True, "criado_em": "2026-01-01", "reciproca": True},
    ])

    resultado = await parceria_repo.listar_recebidas(fake_pool, "a")

    assert resultado[0]["reciproca"] is True
    sql = " ".join(fake_pool.fetch.call_args[0][0].split())
    assert "WHERE mp.marca_destino_id = $1 AND mp.ativo = true" in sql
