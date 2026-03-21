from asyncpg import Pool
from config import get_settings


async def checar_rate_limit(pool: Pool, ip_hash: str) -> bool:
    """
    Verifica se o ip_hash excedeu o limite de uploads na janela configurada.

    Retorna True se deve ser marcado como pendente (acima do limite).
    Não rejeita — delega a decisão ao moderador.
    """
    settings = get_settings()

    count = await pool.fetchval(
        """
        SELECT COUNT(*)
        FROM entradas
        WHERE ip_hash = $1
          AND criado_em > now() - ($2 || ' seconds')::interval
        """,
        ip_hash,
        str(settings.rate_window_seconds),
    )

    return count >= settings.rate_limit
