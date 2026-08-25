"""
Repository de avatares — galeria curada por super-admin
(docs/BACKLOG_2026.md §1, ponto cego #3; migration 020).
"""
from asyncpg import Pool


async def listar_todos(pool: Pool) -> list[dict]:
    """Todos os avatares (ativos e inativos) — painel admin."""
    rows = await pool.fetch(
        "SELECT id, nome, url, ativo, criado_em FROM avatares ORDER BY criado_em DESC"
    )
    return [dict(r) for r in rows]


async def listar_ativos(pool: Pool) -> list[dict]:
    """Só ativos — galeria pública que o perfil usa pra escolher."""
    rows = await pool.fetch(
        "SELECT id, nome, url FROM avatares WHERE ativo = true ORDER BY nome"
    )
    return [dict(r) for r in rows]


async def buscar_por_id(pool: Pool, avatar_id: str) -> dict | None:
    row = await pool.fetchrow(
        "SELECT id, nome, url, ativo, criado_em FROM avatares WHERE id = $1",
        avatar_id,
    )
    return dict(row) if row else None


async def criar(pool: Pool, nome: str, url: str) -> dict:
    row = await pool.fetchrow(
        """
        INSERT INTO avatares (nome, url)
        VALUES ($1, $2)
        RETURNING id, nome, url, ativo, criado_em
        """,
        nome, url,
    )
    return dict(row)


async def atualizar_ativo(pool: Pool, avatar_id: str, ativo: bool) -> dict | None:
    """Ativa/desativa — nunca DELETE (avatar_id já pode estar em uso
    por algum users.avatar_id; desativar só tira da galeria de escolha
    futura, quem já escolheu mantém)."""
    row = await pool.fetchrow(
        """
        UPDATE avatares SET ativo = $2
        WHERE id = $1
        RETURNING id, nome, url, ativo, criado_em
        """,
        avatar_id, ativo,
    )
    return dict(row) if row else None
