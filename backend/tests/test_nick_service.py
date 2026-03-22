import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.parametrize("entrada, esperado", [
    ("Joao",           "joao"),
    ("  Joao  ",       "joao"),
    ("JOAO",           "joao"),
    ("Joao  Silva",    "joao silva"),
    ("  Joao  Silva  ","joao silva"),
    ("j",              "j"),
    ("123",            "123"),
])
def test_normalizar_nick(entrada, esperado):
    from services.nick import normalizar_nick
    assert normalizar_nick(entrada) == esperado


def test_normalizar_nick_strip_tabs():
    from services.nick import normalizar_nick
    assert normalizar_nick("\tPlayer\t") == "player"


@pytest.mark.asyncio
async def test_marca_anterior_quando_existe():
    from services.nick import marcar_anterior_como_superado
    # marcar_anterior usa UPDATE...RETURNING — simula row com id
    fake_row = {"id": "uuid-anterior"}
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=fake_row)
    pool = MagicMock()

    resultado = await marcar_anterior_como_superado(pool, "player1", "jogo-id", conn=conn)
    assert resultado == "uuid-anterior"
    conn.fetchrow.assert_called_once()


@pytest.mark.asyncio
async def test_retorna_none_quando_nao_existe():
    from services.nick import marcar_anterior_como_superado
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    pool = MagicMock()

    resultado = await marcar_anterior_como_superado(pool, "player1", "jogo-id", conn=conn)
    assert resultado is None


@pytest.mark.asyncio
async def test_query_usa_conn_quando_fornecido():
    from services.nick import marcar_anterior_como_superado
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)

    await marcar_anterior_como_superado(pool, "player1", "jogo-id", conn=conn)

    # conn deve ser usado, não pool
    conn.fetchrow.assert_called_once()
    pool.fetchrow.assert_not_called()


@pytest.mark.asyncio
async def test_query_contem_superado():
    from services.nick import marcar_anterior_como_superado
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    pool = MagicMock()

    await marcar_anterior_como_superado(pool, "player1", "jogo-id", conn=conn)
    query = conn.fetchrow.call_args[0][0]
    assert "superado" in query.lower()