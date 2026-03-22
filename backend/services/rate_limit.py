from asyncpg import Pool
from config import get_settings


async def checar_rate_limit(pool: Pool, ip_hash: str) -> bool:
    """
    Verifica se o ip_hash excedeu o limite de uploads na janela configurada.

    Tenta ler os limites da tabela evento_config (configurável pelo admin).
    Se não encontrar, usa os valores das variáveis de ambiente como fallback.

    Retorna True se deve ser marcado como pendente (acima do limite).
    Não rejeita — delega a decisão ao moderador.
    """
    settings = get_settings()

    # Tenta ler configuração dinâmica do banco
    try:
        row = await pool.fetchrow(
            """
            SELECT
              MAX(CASE WHEN chave = 'rate_limit'        THEN valor END) AS rate_limit,
              MAX(CASE WHEN chave = 'rate_window_horas' THEN valor END) AS rate_window_horas
            FROM evento_config
            WHERE chave IN ('rate_limit', 'rate_window_horas')
            """
        )
        limite  = int(row['rate_limit'])        if row and row['rate_limit']        else settings.rate_limit
        janela  = int(row['rate_window_horas']) * 3600 if row and row['rate_window_horas'] else settings.rate_window_seconds
    except Exception:
        # Fallback para variáveis de ambiente se a tabela não existir
        limite = settings.rate_limit
        janela = settings.rate_window_seconds

    count = await pool.fetchval(
        """
        SELECT COUNT(*)
        FROM entradas
        WHERE ip_hash  = $1
          AND criado_em > now() - ($2 || ' seconds')::interval
        """,
        ip_hash,
        str(janela),
    )

    return count >= limite