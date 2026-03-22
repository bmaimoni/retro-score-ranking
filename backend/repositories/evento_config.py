from asyncpg import Pool


async def listar(pool: Pool) -> dict:
    """Retorna todas as configs como dicionário chave→valor."""
    rows = await pool.fetch("SELECT chave, valor, descricao FROM evento_config ORDER BY chave")
    return {r["chave"]: {"valor": r["valor"], "descricao": r["descricao"]} for r in rows}


async def atualizar(pool: Pool, chave: str, valor: str) -> dict | None:
    row = await pool.fetchrow(
        """
        UPDATE evento_config
        SET valor = $1, atualizado_em = now()
        WHERE chave = $2
        RETURNING chave, valor, descricao, atualizado_em
        """,
        valor, chave,
    )
    return dict(row) if row else None


async def get_publico(pool: Pool) -> dict:
    """Retorna apenas as configs públicas (usadas pelo frontend de upload)."""
    rows = await pool.fetch(
        "SELECT chave, valor FROM evento_config WHERE chave LIKE 'upload_%' OR chave LIKE 'evento_%'"
    )
    return {r["chave"]: r["valor"] for r in rows}