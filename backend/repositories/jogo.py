from asyncpg import Pool
from typing import Any


async def listar_ativos(pool: Pool) -> list[dict]:
    """
    Jogos do catálogo geral — usado por /api/jogos (sem evento) e pelo
    placar escopo='global'. Exclui jogos pendentes de aprovação (ver
    migration 018): um jogo criado por admin não-super só entra aqui
    depois que um super-admin aprova.
    """
    rows = await pool.fetch(
        """
        SELECT id, nome, slug, score_max
        FROM jogos
        WHERE ativo = true AND pendente_aprovacao = false
        ORDER BY nome
        """
    )
    return [dict(r) for r in rows]


async def buscar_por_slug(pool: Pool, slug: str) -> dict | None:
    row = await pool.fetchrow(
        "SELECT id, nome, slug, ativo, score_max FROM jogos WHERE slug = $1",
        slug,
    )
    return dict(row) if row else None


async def criar(
    pool: Pool,
    nome: str,
    slug: str,
    score_max: int | None,
    pendente_aprovacao: bool = False,
    criado_por: str | None = None,
) -> dict:
    row = await pool.fetchrow(
        """
        INSERT INTO jogos (nome, slug, score_max, pendente_aprovacao, criado_por)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id, nome, slug, ativo, score_max, pendente_aprovacao, criado_por, criado_em
        """,
        nome, slug, score_max, pendente_aprovacao, criado_por,
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

# ── Aprovação pro catálogo global (migration 018) ──────────────

async def listar_pendentes_aprovacao(pool: Pool) -> list[dict]:
    """
    Jogos aguardando aprovação de um super-admin, com os eventos que já
    os utilizam — pro painel de revisão saber o contexto (quem criou,
    onde já está em uso) antes de aprovar ou mesclar.
    """
    rows = await pool.fetch(
        """
        SELECT
            j.id, j.nome, j.slug, j.score_max, j.criado_por, j.criado_em,
            COALESCE(
                array_agg(e.nome) FILTER (WHERE e.nome IS NOT NULL),
                '{}'
            ) AS eventos_em_uso
        FROM jogos j
        LEFT JOIN evento_jogos ej ON ej.jogo_id = j.id AND ej.ativo = true
        LEFT JOIN eventos e ON e.id = ej.evento_id
        WHERE j.pendente_aprovacao = true
        GROUP BY j.id
        ORDER BY j.criado_em ASC
        """
    )
    return [dict(r) for r in rows]


async def aprovar(pool: Pool, jogo_id: str) -> dict | None:
    """
    Aprova um jogo pendente pro catálogo geral. Como listar_ativos/o
    placar global só filtram por pendente_aprovacao=false (não fazem
    nenhum backfill), as entradas já enviadas para esse jogo entram no
    catálogo geral automaticamente, sem precisar tocar em 'entradas'.
    """
    row = await pool.fetchrow(
        """
        UPDATE jogos SET pendente_aprovacao = false
        WHERE id = $1 AND pendente_aprovacao = true
        RETURNING id, nome, slug, ativo, score_max, pendente_aprovacao, criado_por, criado_em
        """,
        jogo_id,
    )
    return dict(row) if row else None


async def mesclar(conn, jogo_origem_id: str, jogo_destino_id: str) -> dict:
    """
    Mescla jogo_origem em jogo_destino — usado quando um super-admin
    percebe que um jogo criado por outro admin já existe na plataforma
    com outro nome/slug. Migra entradas e vínculos de evento, arquiva
    o jogo original mantendo o rastro de pra onde foi (nunca apaga).

    Recebe uma conexão já dentro de uma transação (ver router) — a
    migração de entradas + vínculos + arquivamento precisa ser atômica.
    """
    await conn.execute(
        "UPDATE entradas SET jogo_id = $1 WHERE jogo_id = $2",
        jogo_destino_id, jogo_origem_id,
    )
    # Vínculos de evento: migra os que o destino ainda não tem
    # (ON CONFLICT porque o mesmo evento pode já ter os dois jogos)
    await conn.execute(
        """
        INSERT INTO evento_jogos (evento_id, jogo_id, ordem)
        SELECT evento_id, $1, ordem FROM evento_jogos WHERE jogo_id = $2
        ON CONFLICT (evento_id, jogo_id) DO NOTHING
        """,
        jogo_destino_id, jogo_origem_id,
    )
    row = await conn.fetchrow(
        """
        UPDATE jogos
        SET ativo = false, mesclado_em_jogo_id = $2, pendente_aprovacao = false
        WHERE id = $1
        RETURNING id, nome, slug, ativo, mesclado_em_jogo_id
        """,
        jogo_origem_id, jogo_destino_id,
    )
    return dict(row)
