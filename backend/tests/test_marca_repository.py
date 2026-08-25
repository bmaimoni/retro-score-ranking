"""
Testes de repositories/marca.py — foco na query de resolução de
herança (evento → marca → default), que é o coração do
docs/MARCAS_SPEC.md.
"""
import pytest
import repositories.marca as marca_repo


@pytest.mark.asyncio
async def test_resolver_identidade_visual_faz_left_join_com_marcas(fake_pool):
    """
    Confirma que a resolução acontece numa única query (LEFT JOIN),
    não duas idas separadas ao banco — decisão explícita do
    MARCAS_SPEC.md §3 (normalizar em tabela própria não compensava
    exatamente por essa razão).
    """
    fake_pool.set_fetchrow({
        "slug": "canal3expo", "nome": "Canal3 Expo",
        "cor_primaria": "#5e2b82", "tipografia": "arcade",
        "logo_url": "https://cdn/evento-logo.png",
    })

    resultado = await marca_repo.resolver_identidade_visual(fake_pool, "canal3expo")

    sql = " ".join(fake_pool.fetchrow.call_args[0][0].split())
    assert "LEFT JOIN marcas m ON m.id = e.marca_id" in sql
    assert "COALESCE(e.cor_primaria, m.cor_primaria)" in sql
    assert "COALESCE(e.tipografia,   m.tipografia)" in sql or \
           "COALESCE(e.tipografia, m.tipografia)" in sql
    assert resultado["cor_primaria"] == "#5e2b82"


@pytest.mark.asyncio
async def test_resolver_identidade_visual_evento_inexistente_retorna_none(fake_pool):
    fake_pool.set_fetchrow(None)
    resultado = await marca_repo.resolver_identidade_visual(fake_pool, "nao-existe")
    assert resultado is None


@pytest.mark.asyncio
async def test_criar_marca_repository(fake_pool):
    fake_pool.set_fetchrow({
        "id": "abc", "nome": "Canal3", "slug": "canal3",
        "cor_primaria": "#5e2b82", "tipografia": "arcade",
        "logo_url": None, "criado_em": "2026-01-01",
    })

    resultado = await marca_repo.criar(fake_pool, "Canal3", "canal3", "#5e2b82", "arcade", None)

    assert resultado["slug"] == "canal3"
    # Confirma ordem/quantidade dos parâmetros passados pro INSERT
    args = fake_pool.fetchrow.call_args[0]
    assert args[1:] == ("Canal3", "canal3", "#5e2b82", "arcade", None)


@pytest.mark.asyncio
async def test_atualizar_marca_campos_parciais(fake_pool):
    """Só os campos presentes em `dados` devem ser repassados como
    não-None — os demais ficam None pro COALESCE preservar o valor atual."""
    fake_pool.set_fetchrow({
        "id": "abc", "nome": "Canal3", "slug": "canal3",
        "cor_primaria": "#ff0000", "tipografia": "arcade",
        "logo_url": None, "criado_em": "2026-01-01",
    })

    await marca_repo.atualizar(fake_pool, "abc", {"cor_primaria": "#ff0000"})

    args = fake_pool.fetchrow.call_args[0]
    # (sql, marca_id, nome, cor_primaria, tipografia, logo_url)
    assert args[1] == "abc"
    assert args[2] is None          # nome não foi passado
    assert args[3] == "#ff0000"     # cor_primaria foi passado
    assert args[4] is None          # tipografia não foi passado


# ── buscar_dono_user_id: trava de revogação do titular (decisão #10) ───────────

@pytest.mark.asyncio
async def test_buscar_dono_user_id_retorna_titular(fake_pool):
    dono_id = "550e8400-e29b-41d4-a716-446655440000"
    fake_pool.set_fetchrow({"dono_user_id": dono_id})

    resultado = await marca_repo.buscar_dono_user_id(fake_pool, "marca-1")

    assert resultado == dono_id


@pytest.mark.asyncio
async def test_buscar_dono_user_id_marca_sem_titular_retorna_none(fake_pool):
    """dono_user_id nasce NULL em toda marca existente após a
    migration 019 — precisa ser atribuído manualmente depois."""
    fake_pool.set_fetchrow({"dono_user_id": None})

    resultado = await marca_repo.buscar_dono_user_id(fake_pool, "marca-1")

    assert resultado is None


@pytest.mark.asyncio
async def test_buscar_dono_user_id_marca_inexistente_retorna_none(fake_pool):
    fake_pool.set_fetchrow(None)

    resultado = await marca_repo.buscar_dono_user_id(fake_pool, "nao-existe")

    assert resultado is None
