import pytest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from services.score import validar_score


@pytest.mark.asyncio
async def test_aceita_score_dentro_do_limite():
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value={"score_max": 999990})
    await validar_score(pool, "jogo-id", 50000)  # não deve levantar


@pytest.mark.asyncio
async def test_aceita_score_sem_limite_definido():
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value={"score_max": None})
    await validar_score(pool, "jogo-id", 9999999)  # sem limite, qualquer valor é ok


@pytest.mark.asyncio
async def test_rejeita_score_acima_do_maximo():
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value={"score_max": 999990})

    with pytest.raises(HTTPException) as exc:
        await validar_score(pool, "jogo-id", 9999999)

    assert exc.value.status_code == 422
    assert "999990" in exc.value.detail


@pytest.mark.asyncio
async def test_rejeita_jogo_inativo():
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value=None)  # WHERE ativo = true não retornou

    with pytest.raises(HTTPException) as exc:
        await validar_score(pool, "jogo-inativo", 1000)

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_aceita_score_exatamente_no_maximo():
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value={"score_max": 999990})
    await validar_score(pool, "jogo-id", 999990)  # igual ao máximo: deve aceitar
