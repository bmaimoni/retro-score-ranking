import re
from asyncpg import Pool


def normalizar_nick(nick: str) -> str:
    """
    Normaliza o nick para comparação de unicidade:
    - strip de espaços nas bordas
    - lowercase
    - colapsa múltiplos espaços internos em um único

    O nick original é preservado para exibição.
    """
    return re.sub(r"\s+", " ", nick.strip()).lower()


async def marcar_anterior_como_superado(
    pool: Pool,
    nick_norm: str,
    jogo_id: str,
    conn=None,
) -> str | None:
    """
    Busca a entrada ativa do nick no jogo e a marca como superada.
    Deve ser chamado dentro da mesma transação do INSERT.

    Retorna o id da entrada anterior, ou None se não havia.
    """
    executor = conn or pool

    row = await executor.fetchrow(
        """
        UPDATE entradas
        SET superado = true
        WHERE nick_norm = $1
          AND jogo_id   = $2
          AND superado  = false
          AND pendente  = false
        RETURNING id
        """,
        nick_norm,
        jogo_id,
    )

    return str(row["id"]) if row else None
