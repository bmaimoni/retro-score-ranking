"""
Testes do serviço de rate limit.
O limite padrão agora é 10/hora (config.py).
Os testes de lógica usam limite configurado via evento_config (valor "10").
"""
import pytest
from unittest.mock import AsyncMock, patch
from services.rate_limit import checar_rate_limit


@pytest.mark.asyncio
async def test_abaixo_do_limite_nao_e_pendente():
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value={"rate_limit": "10", "rate_window_horas": "1"})
    pool.fetchval = AsyncMock(return_value=5)
    resultado = await checar_rate_limit(pool, "hash_abc")
    assert resultado is False


@pytest.mark.asyncio
async def test_igual_ao_limite_e_pendente():
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value={"rate_limit": "10", "rate_window_horas": "1"})
    pool.fetchval = AsyncMock(return_value=10)
    resultado = await checar_rate_limit(pool, "hash_abc")
    assert resultado is True


@pytest.mark.asyncio
async def test_acima_do_limite_e_pendente():
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value={"rate_limit": "10", "rate_window_horas": "1"})
    pool.fetchval = AsyncMock(return_value=15)
    resultado = await checar_rate_limit(pool, "hash_abc")
    assert resultado is True


@pytest.mark.asyncio
async def test_primeira_vez_nao_e_pendente():
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value={"rate_limit": "10", "rate_window_horas": "1"})
    pool.fetchval = AsyncMock(return_value=0)
    resultado = await checar_rate_limit(pool, "hash_novo")
    assert resultado is False


@pytest.mark.asyncio
async def test_fallback_para_env_quando_config_ausente():
    """Sem config no banco, usa o padrão do config.py (10/hora)."""
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value={"rate_limit": None, "rate_window_horas": None})
    pool.fetchval = AsyncMock(return_value=5)
    with patch("services.rate_limit.get_settings") as mock_cfg:
        mock_cfg.return_value.rate_limit = 10
        mock_cfg.return_value.rate_window_seconds = 3600
        resultado = await checar_rate_limit(pool, "hash_abc")
    assert resultado is False


@pytest.mark.asyncio
async def test_fallback_env_limite_atingido():
    """Sem config no banco, respeita limite do env."""
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value={"rate_limit": None, "rate_window_horas": None})
    pool.fetchval = AsyncMock(return_value=10)
    with patch("services.rate_limit.get_settings") as mock_cfg:
        mock_cfg.return_value.rate_limit = 10
        mock_cfg.return_value.rate_window_seconds = 3600
        resultado = await checar_rate_limit(pool, "hash_abc")
    assert resultado is True


@pytest.mark.asyncio
async def test_usa_ip_hash_na_query():
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value={"rate_limit": "10", "rate_window_horas": "1"})
    pool.fetchval = AsyncMock(return_value=0)
    await checar_rate_limit(pool, "meu_hash_especifico")
    chamada = pool.fetchval.call_args
    assert "meu_hash_especifico" in chamada[0]