import pytest
from services.nick import normalizar_nick, marcar_anterior_como_superado
from unittest.mock import AsyncMock


# ── normalizar_nick ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("entrada, esperado", [
    ("João",           "joão"),
    ("  João  ",       "joão"),
    ("JOÃO",           "joão"),
    ("João  Silva",    "joão  silva"),   # espaços internos colapsados
    ("  João  Silva  ","joão silva"),
    ("j",              "j"),
    ("123",            "123"),
])
def test_normalizar_nick(entrada, esperado):
    # Corrige o caso de espaços internos múltiplos
    assert normalizar_nick(entrada) == esperado


def test_normalizar_nick_preserva_acentos():
    assert normalizar_nick("Çédric") == "çédric"


def test_normalizar_nick_strip_tabs():
    assert normalizar_nick("\tNick\t") == "nick"


# ── marcar_anterior_como_superado ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_marca_anterior_quando_existe():
    import uuid
    fake_id = str(uuid.uuid4())

    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"id": fake_id})

    resultado = await marcar_anterior_como_superado(
        pool=None, nick_norm="jogador1", jogo_id="jogo-uuid", conn=conn
    )

    assert resultado == fake_id
    conn.fetchrow.assert_called_once()


@pytest.mark.asyncio
async def test_retorna_none_quando_nao_existe():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)

    resultado = await marcar_anterior_como_superado(
        pool=None, nick_norm="novo_jogador", jogo_id="jogo-uuid", conn=conn
    )

    assert resultado is None


@pytest.mark.asyncio
async def test_query_filtra_superado_e_pendente():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)

    await marcar_anterior_como_superado(
        pool=None, nick_norm="nick", jogo_id="jogo", conn=conn
    )

    sql = conn.fetchrow.call_args[0][0]
    # Garante que a query só afeta entradas não superadas e não pendentes
    assert "superado  = false" in sql
    assert "pendente  = false" in sql
