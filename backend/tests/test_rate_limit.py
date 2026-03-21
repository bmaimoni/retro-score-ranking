import pytest
from unittest.mock import AsyncMock, patch
from services.rate_limit import checar_rate_limit


@pytest.mark.asyncio
async def test_abaixo_do_limite_nao_e_pendente():
    pool = AsyncMock()
    pool.fetchval = AsyncMock(return_value=2)  # 2 uploads, limite=3

    with patch("services.rate_limit.get_settings") as mock_cfg:
        mock_cfg.return_value.rate_limit = 3
        mock_cfg.return_value.rate_window_seconds = 3600
        resultado = await checar_rate_limit(pool, "hash_abc")

    assert resultado is False


@pytest.mark.asyncio
async def test_igual_ao_limite_e_pendente():
    pool = AsyncMock()
    pool.fetchval = AsyncMock(return_value=3)  # exatamente no limite

    with patch("services.rate_limit.get_settings") as mock_cfg:
        mock_cfg.return_value.rate_limit = 3
        mock_cfg.return_value.rate_window_seconds = 3600
        resultado = await checar_rate_limit(pool, "hash_abc")

    assert resultado is True


@pytest.mark.asyncio
async def test_acima_do_limite_e_pendente():
    pool = AsyncMock()
    pool.fetchval = AsyncMock(return_value=10)

    with patch("services.rate_limit.get_settings") as mock_cfg:
        mock_cfg.return_value.rate_limit = 3
        mock_cfg.return_value.rate_window_seconds = 3600
        resultado = await checar_rate_limit(pool, "hash_abc")

    assert resultado is True


@pytest.mark.asyncio
async def test_primeira_vez_nao_e_pendente():
    pool = AsyncMock()
    pool.fetchval = AsyncMock(return_value=0)  # nenhum upload anterior

    with patch("services.rate_limit.get_settings") as mock_cfg:
        mock_cfg.return_value.rate_limit = 3
        mock_cfg.return_value.rate_window_seconds = 3600
        resultado = await checar_rate_limit(pool, "hash_novo")

    assert resultado is False


@pytest.mark.asyncio
async def test_usa_ip_hash_na_query():
    """Garante que o ip_hash correto é passado para a query."""
    pool = AsyncMock()
    pool.fetchval = AsyncMock(return_value=0)

    with patch("services.rate_limit.get_settings") as mock_cfg:
        mock_cfg.return_value.rate_limit = 3
        mock_cfg.return_value.rate_window_seconds = 3600
        await checar_rate_limit(pool, "meu_hash_especifico")

    chamada = pool.fetchval.call_args
    assert "meu_hash_especifico" in chamada[0]
