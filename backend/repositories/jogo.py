from asyncpg import Pool
from typing import Any


async def listar_ativos(pool: Pool) -> list[dict]:
    rows = await pool.fetch(
        "SELECT id, nome, slug, score_max FROM jogos WHERE ativo = true ORDER BY nome"
    )
    return [dict(r) for r in rows]


async def buscar_por_slug(pool: Pool, slug: str) -> dict | None:
    row = await pool.fetchrow(
        "SELECT id, nome, slug, ativo, score_max FROM jogos WHERE slug = $1",
        slug,
    )
    return dict(row) if row else None


async def criar(pool: Pool, nome: str, slug: str, score_max: int | None) -> dict:
    row = await pool.fetchrow(
        """
        INSERT INTO jogos (nome, slug, score_max)
        VALUES ($1, $2, $3)
        RETURNING id, nome, slug, ativo, score_max, criado_em
        """,
        nome, slug, score_max,
    )
    return dict(row)


async def atualizar(
    pool: Pool,
    jogo_id: str,
    ativo: bool | None,
    score_max: int | None,
) -> dict | None:
    # Constrói SET dinâmico com apenas os campos fornecidos
    campos, valores = [], []
    idx = 1
    if ativo is not None:
        campos.append(f"ativo = ${idx}"); valores.append(ativo); idx += 1
    if score_max is not None:
        campos.append(f"score_max = ${idx}"); valores.append(score_max); idx += 1

    if not campos:
        return None

    valores.append(jogo_id)
    row = await pool.fetchrow(
        f"UPDATE jogos SET {', '.join(campos)} WHERE id = ${idx} RETURNING *",
        *valores,
    )
    return dict(row) if row else None


async def listar_todos(pool: Pool) -> list[dict]:
    """Lista todos os jogos (ativos e inativos) para o painel admin."""
    rows = await pool.fetch(
        "SELECT id, nome, slug, ativo, score_max, criado_em FROM jogos ORDER BY nome"
    )
    return [dict(r) for r in rows]