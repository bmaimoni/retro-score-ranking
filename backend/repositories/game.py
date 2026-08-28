from asyncpg import Pool
from typing import Any


async def listar_ativos(pool: Pool) -> list[dict]:
    """
    Games do catálogo geral — usado por /api/games (sem event) e pelo
    placar escopo='global'. Exclui games pendentes de aprovação (ver
    migration 018): um game criado por admin não-super só entra aqui
    depois que um super-admin aprova.
    """
    rows = await pool.fetch(
        """
        SELECT id, nome, slug, score_max, plataforma, ano_lancamento, capa_url, gameplay_url
        FROM games
        WHERE ativo = true AND pendente_aprovacao = false
        ORDER BY nome
        """
    )
    return [dict(r) for r in rows]


async def buscar_por_slug(pool: Pool, slug: str) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT id, nome, slug, ativo, score_max,
               plataforma, ano_lancamento, capa_url, gameplay_url
        FROM games WHERE slug = $1
        """,
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
    plataforma: str | None = None,
    ano_lancamento: int | None = None,
    capa_url: str | None = None,
    gameplay_url: str | None = None,
    igdb_id: int | None = None,
) -> dict:
    row = await pool.fetchrow(
        """
        INSERT INTO games (nome, slug, score_max, pendente_aprovacao, criado_por,
                            plataforma, ano_lancamento, capa_url, gameplay_url, igdb_id)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        RETURNING id, nome, slug, ativo, score_max, pendente_aprovacao, criado_por, criado_em,
                  plataforma, ano_lancamento, capa_url, gameplay_url, igdb_id
        """,
        nome, slug, score_max, pendente_aprovacao, criado_por,
        plataforma, ano_lancamento, capa_url, gameplay_url, igdb_id,
    )
    return dict(row)


async def buscar_por_igdb_id(pool: Pool, igdb_id: int) -> dict | None:
    """Dedup estrutural do caminho IGDB (docs/CATALOGO_JOGOS_SPEC.md
    5.1) — se já existe um game com esse igdb_id, o endpoint de
    criação reaproveita em vez de tentar criar duplicata."""
    row = await pool.fetchrow(
        """
        SELECT id, nome, slug, ativo, score_max, pendente_aprovacao, criado_por, criado_em,
               plataforma, ano_lancamento, capa_url, gameplay_url, igdb_id
        FROM games WHERE igdb_id = $1
        """,
        igdb_id,
    )
    return dict(row) if row else None


async def contar_manuais_por_criador_ultimas_24h(pool: Pool, criado_por: str) -> int:
    """Rate limit do cadastro manual de jogo — só conta o caminho sem
    dedup estrutural (igdb_id IS NULL); busca via IGDB não tem limite,
    só adiciona jogo real já aprovado (docs/CATALOGO_JOGOS_SPEC.md 5.5)."""
    return await pool.fetchval(
        """
        SELECT COUNT(*) FROM games
        WHERE criado_por = $1 AND igdb_id IS NULL
          AND criado_em > now() - interval '1 day'
        """,
        criado_por,
    )


async def listar_nome_ativos(pool: Pool) -> list[dict]:
    """Nomes de todo game ativo — usado na checagem de colisão do
    cadastro manual (docs/CATALOGO_JOGOS_SPEC.md 5.6, services/game_admissao.py)."""
    rows = await pool.fetch("SELECT nome FROM games WHERE ativo = true")
    return [dict(r) for r in rows]


async def atualizar(
    pool: Pool,
    game_id: str,
    ativo: bool | None,
    score_max: int | None,
    plataforma: str | None = None,
    ano_lancamento: int | None = None,
    capa_url: str | None = None,
    gameplay_url: str | None = None,
) -> dict | None:
    # Constrói SET dinâmico com apenas os campos fornecidos
    campos, valores = [], []
    idx = 1

    def _adicionar(coluna, valor):
        nonlocal idx
        campos.append(f"{coluna} = ${idx}"); valores.append(valor); idx += 1

    if ativo is not None:
        _adicionar("ativo", ativo)
    if score_max is not None:
        _adicionar("score_max", score_max)
    if plataforma is not None:
        _adicionar("plataforma", plataforma)
    if ano_lancamento is not None:
        _adicionar("ano_lancamento", ano_lancamento)
    if capa_url is not None:
        _adicionar("capa_url", capa_url)
    if gameplay_url is not None:
        _adicionar("gameplay_url", gameplay_url)

    if not campos:
        return None

    valores.append(game_id)
    row = await pool.fetchrow(
        f"UPDATE games SET {', '.join(campos)} WHERE id = ${idx} RETURNING *",
        *valores,
    )
    return dict(row) if row else None


async def listar_todos(pool: Pool) -> list[dict]:
    """Lista todos os games (ativos e inativos) para o painel admin."""
    rows = await pool.fetch(
        """
        SELECT id, nome, slug, ativo, score_max, pendente_aprovacao, criado_em,
               plataforma, ano_lancamento, capa_url, gameplay_url
        FROM games ORDER BY nome
        """
    )
    return [dict(r) for r in rows]

# ── Aprovação pro catálogo global (migration 018) ──────────────

async def listar_pendentes_aprovacao(pool: Pool) -> list[dict]:
    """
    Games aguardando aprovação de um super-admin, com os events que já
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
            ) AS events_em_uso
        FROM games j
        LEFT JOIN event_games ej ON ej.game_id = j.id AND ej.ativo = true
        LEFT JOIN events e ON e.id = ej.event_id
        WHERE j.pendente_aprovacao = true
        GROUP BY j.id
        ORDER BY j.criado_em ASC
        """
    )
    return [dict(r) for r in rows]


async def aprovar(pool: Pool, game_id: str) -> dict | None:
    """
    Aprova um game pendente pro catálogo geral. Como listar_ativos/o
    placar global só filtram por pendente_aprovacao=false (não fazem
    nenhum backfill), as entries já enviadas para esse game entram no
    catálogo geral automaticamente, sem precisar tocar em 'entries'.
    """
    row = await pool.fetchrow(
        """
        UPDATE games SET pendente_aprovacao = false
        WHERE id = $1 AND pendente_aprovacao = true
        RETURNING id, nome, slug, ativo, score_max, pendente_aprovacao, criado_por, criado_em
        """,
        game_id,
    )
    return dict(row) if row else None


async def mesclar(conn, game_origem_id: str, game_destino_id: str) -> dict:
    """
    Mescla game_origem em game_destino — usado quando um super-admin
    percebe que um game criado por outro admin já existe na plataforma
    com outro nome/slug. Migra entries e vínculos de event, arquiva
    o game original mantendo o rastro de pra onde foi (nunca apaga).

    Recebe uma conexão já dentro de uma transação (ver router) — a
    migração de entries + vínculos + arquivamento precisa ser atômica.
    """
    await conn.execute(
        "UPDATE entries SET game_id = $1 WHERE game_id = $2",
        game_destino_id, game_origem_id,
    )
    # Vínculos de event: migra os que o destino ainda não tem
    # (ON CONFLICT porque o mesmo event pode já ter os dois games)
    await conn.execute(
        """
        INSERT INTO event_games (event_id, game_id, ordem)
        SELECT event_id, $1, ordem FROM event_games WHERE game_id = $2
        ON CONFLICT (event_id, game_id) DO NOTHING
        """,
        game_destino_id, game_origem_id,
    )
    row = await conn.fetchrow(
        """
        UPDATE games
        SET ativo = false, mesclado_em_game_id = $2, pendente_aprovacao = false
        WHERE id = $1
        RETURNING id, nome, slug, ativo, mesclado_em_game_id
        """,
        game_origem_id, game_destino_id,
    )
    return dict(row)
