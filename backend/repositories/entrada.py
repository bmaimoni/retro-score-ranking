from asyncpg import Pool
from typing import Any


async def inserir(conn, dados: dict) -> dict:
    row = await conn.fetchrow(
        """
        INSERT INTO entradas
            (jogo_id, nick, nick_norm, nome, pontuacao, foto_url,
             no_ranking, superado, pendente, ip_hash, evento_id, user_id)
        VALUES ($1, $2, $3, $4, $5, $6, $7, false, $8, $9, $10, $11)
        RETURNING id, jogo_id, nick, nome, pontuacao, foto_url,
                  no_ranking, pendente, criado_em, evento_id, user_id
        """,
        dados["jogo_id"],
        dados["nick"],
        dados["nick_norm"],
        dados.get("nome"),
        dados["pontuacao"],
        dados["foto_url"],
        dados["no_ranking"],
        dados["pendente"],
        dados["ip_hash"],
        dados.get("evento_id"),
        dados.get("user_id"),
    )
    return dict(row)


async def listar_ranking(pool: Pool, jogo_id: str) -> list[dict]:
    """
    Ranking público: apenas entradas visíveis, não superadas, não pendentes.
    Ordenadas por pontuação decrescente.

    Em caso de empate de pontuação, desempata por criado_em (quem alcançou
    primeiro fica na frente) e por id como critério final. Sem isso, o
    Postgres não garante ordem estável entre linhas empatadas — a ordem
    pode mudar entre consultas e fazer uma entrada "sumir" de listas
    truncadas (ex.: top 10 do telão).

    Usa o índice parcial idx_ranking.
    """
    rows = await pool.fetch(
        """
        SELECT id, nick, nome, pontuacao, foto_url, evento_id, criado_em
        FROM entradas
        WHERE jogo_id    = $1
          AND no_ranking = true
          AND superado   = false
          AND pendente   = false
          AND arquivado  = false
        ORDER BY pontuacao DESC, criado_em ASC, id ASC
        """,
        jogo_id,
    )
    return [dict(r) for r in rows]


async def listar_feed_admin(
    pool: Pool,
    limit: int = 50,
    offset: int = 0,
    evento_ids: list[str] | None = None,
) -> list[dict]:
    """
    Feed do admin: todas as entradas, mais recentes primeiro.

    evento_ids: se informado, restringe às entradas desses eventos —
    usado quando o admin não é super-admin (ver docs/MARCAS_SPEC.md §6,
    "efeito colateral necessário: feed e pendentes precisam saber o evento").
    None = sem filtro (comportamento de sempre, usado por super-admin).
    """
    rows = await pool.fetch(
        """
        SELECT e.id, e.nick, e.nome, e.pontuacao, e.foto_url, e.evento_id, e.no_ranking,
               e.superado, e.pendente, e.criado_em, e.moderado_em,
               e.moderado_por, j.nome AS jogo_nome, j.slug AS jogo_slug
        FROM entradas e
        JOIN jogos j ON j.id = e.jogo_id
        WHERE ($3::uuid[] IS NULL OR e.evento_id = ANY($3::uuid[]))
        ORDER BY e.criado_em DESC
        LIMIT $1 OFFSET $2
        """,
        limit, offset, evento_ids,
    )
    return [dict(r) for r in rows]


async def contar_feed_admin(pool: Pool, evento_ids: list[str] | None = None) -> int:
    """Total de entradas no feed do admin — para paginação."""
    return await pool.fetchval(
        """
        SELECT COUNT(*) FROM entradas e
        WHERE ($1::uuid[] IS NULL OR e.evento_id = ANY($1::uuid[]))
        """,
        evento_ids,
    )


async def _arquivar_identificacao_ambigua_expirada(pool: Pool) -> None:
    """
    Decisão #8 do docs/NICKNAME_SPEC.md, resolvida sem job agendado
    (NICKNAME_SPEC.md §4, mesmo princípio da decisão #15 — o projeto
    nunca teve cron): checagem preguiçosa, embutida toda vez que a fila
    de pendentes é consultada. Arquiva na hora qualquer entrada
    pendente_motivo='identificacao_ambigua' com mais de 30 dias — só
    "expira" de fato quando alguém abre o painel admin, não por relógio.
    Entradas pendente_motivo='rate_limit' não têm prazo, não são tocadas.
    """
    await pool.execute(
        """
        UPDATE entradas
        SET arquivado = true, arquivado_em = now(),
            arquivado_por = 'sistema (prazo de 30 dias expirado)'
        WHERE pendente = true AND pendente_motivo = 'identificacao_ambigua'
          AND criado_em < now() - interval '30 days'
          AND arquivado = false
        """
    )


async def listar_pendentes(
    pool: Pool,
    limit: int = 50,
    offset: int = 0,
    evento_ids: list[str] | None = None,
) -> list[dict]:
    """evento_ids: mesmo filtro opcional de listar_feed_admin."""
    await _arquivar_identificacao_ambigua_expirada(pool)
    rows = await pool.fetch(
        """
        SELECT
            e.id, e.nick, e.nome, e.pontuacao, e.foto_url, e.criado_em,
            j.nome AS jogo_nome, j.slug AS jogo_slug,
            -- Melhor score atual deste nick neste jogo (no ranking)
            (
                SELECT MAX(e2.pontuacao)
                FROM entradas e2
                WHERE e2.jogo_id   = e.jogo_id
                  AND e2.nick_norm = e.nick_norm
                  AND e2.no_ranking = true
                  AND e2.pendente   = false
                  AND e2.arquivado  = false
            ) AS melhor_score_atual,
            -- Lider atual do jogo
            (
                SELECT MAX(e3.pontuacao)
                FROM entradas e3
                WHERE e3.jogo_id   = e.jogo_id
                  AND e3.no_ranking = true
                  AND e3.pendente   = false
                  AND e3.superado   = false
                  AND e3.arquivado  = false
            ) AS lider_pontuacao,
            -- Posição que ocuparia se aprovado
            (
                SELECT COUNT(*) + 1
                FROM entradas e4
                WHERE e4.jogo_id   = e.jogo_id
                  AND e4.no_ranking = true
                  AND e4.pendente   = false
                  AND e4.superado   = false
                  AND e4.arquivado  = false
                  AND e4.pontuacao  > e.pontuacao
            ) AS posicao_se_aprovado
        FROM entradas e
        JOIN jogos j ON j.id = e.jogo_id
        WHERE e.pendente = true
          AND e.arquivado = false
          AND ($3::uuid[] IS NULL OR e.evento_id = ANY($3::uuid[]))
        ORDER BY e.criado_em ASC
        LIMIT $1 OFFSET $2
        """,
        limit, offset, evento_ids,
    )
    return [dict(r) for r in rows]


async def contar_pendentes(pool: Pool, evento_ids: list[str] | None = None) -> int:
    """Total de entradas pendentes — para paginação."""
    await _arquivar_identificacao_ambigua_expirada(pool)
    return await pool.fetchval(
        """
        SELECT COUNT(*) FROM entradas e
        WHERE e.pendente = true
          AND e.arquivado = false
          AND ($1::uuid[] IS NULL OR e.evento_id = ANY($1::uuid[]))
        """,
        evento_ids,
    )


async def atualizar_visibilidade(
    pool: Pool,
    entrada_id: str,
    no_ranking: bool,
    moderado_por: str,
) -> dict | None:
    row = await pool.fetchrow(
        """
        UPDATE entradas
        SET no_ranking   = $1,
            moderado_em  = now(),
            moderado_por = $2
        WHERE id = $3
        RETURNING id, jogo_id, nick, pontuacao, foto_url,
                  no_ranking, pendente, superado, criado_em
        """,
        no_ranking, moderado_por, entrada_id,
    )
    return dict(row) if row else None


async def resolver_pendente(
    pool: Pool,
    entrada_id: str,
    aprovar: bool,
    moderado_por: str,
) -> dict | None:
    """
    Aprova (pendente=false, no_ranking=true) ou
    oculta (pendente=false, no_ranking=false) uma entrada pendente.
    """
    row = await pool.fetchrow(
        """
        UPDATE entradas
        SET pendente     = false,
            no_ranking   = $1,
            moderado_em  = now(),
            moderado_por = $2
        WHERE id = $3
        RETURNING id, jogo_id, nick, pontuacao, foto_url,
                  no_ranking, pendente, superado, criado_em
        """,
        aprovar, moderado_por, entrada_id,
    )
    return dict(row) if row else None


async def buscar_por_id(pool: Pool, entrada_id: str) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT e.*, j.slug AS jogo_slug
        FROM entradas e
        JOIN jogos j ON j.id = e.jogo_id
        WHERE e.id = $1
        """,
        entrada_id,
    )
    return dict(row) if row else None


async def vincular_retroativamente(pool: Pool, nick_norm: str, user_id: str) -> int:
    """
    Decisão #11 do docs/NICKNAME_SPEC.md: reivindicar um nick pela
    primeira vez (nunca teve dono antes) vincula automaticamente
    qualquer pontuação antiga com esse nick_norm que ainda não tinha
    user_id — sem fila de revisão, sem mecanismo novo. Retorna quantas
    entradas foram vinculadas.
    """
    result = await pool.execute(
        "UPDATE entradas SET user_id = $2 WHERE nick_norm = $1 AND user_id IS NULL",
        nick_norm, user_id,
    )
    return int(result.split()[-1])


async def marcar_pendente_identificacao_ambigua(pool: Pool, nick_norm: str) -> int:
    """
    Decisão #7 do docs/NICKNAME_SPEC.md: um nick liberado sendo
    reivindicado de novo não vincula ninguém automaticamente — só as
    entradas antigas SEM user_id e SEM nome (nenhuma identificação)
    entram em fila de revisão do moderador. Entradas já pendentes ou
    arquivadas não são reabertas. Retorna quantas foram marcadas.
    """
    result = await pool.execute(
        """
        UPDATE entradas
        SET pendente = true, pendente_motivo = 'identificacao_ambigua'
        WHERE nick_norm = $1 AND user_id IS NULL AND nome IS NULL
          AND pendente = false AND arquivado = false
        """,
        nick_norm,
    )
    return int(result.split()[-1])


async def historico_nick(pool: Pool, jogo_id: str, nick_norm: str) -> list[dict]:
    """
    Histórico de todas as entradas de um nick em um jogo,
    ordenadas da mais recente para a mais antiga.
    Inclui entradas superadas, arquivadas e ativas.
    """
    rows = await pool.fetch(
        """
        SELECT id, nick, nome, pontuacao, foto_url,
               no_ranking, superado, pendente, arquivado, criado_em, evento_id
        FROM entradas
        WHERE jogo_id   = $1
          AND nick_norm = $2
        ORDER BY criado_em DESC
        """,
        jogo_id, nick_norm,
    )
    return [dict(r) for r in rows]


async def listar_ranking_por_evento(
    pool: Pool,
    jogo_id: str,
    evento_id: str,
) -> list[dict]:
    """
    Ranking filtrado por evento.
    Retorna apenas scores registrados neste evento específico.

    Mesmo desempate de listar_ranking (criado_em ASC, id ASC) para evitar
    ordem instável entre pontuações empatadas.
    """
    rows = await pool.fetch(
        """
        SELECT id, nick, nome, pontuacao, foto_url, evento_id, criado_em
        FROM entradas
        WHERE jogo_id    = $1
          AND evento_id  = $2
          AND no_ranking = true
          AND superado   = false
          AND pendente   = false
          AND arquivado  = false
        ORDER BY pontuacao DESC, criado_em ASC, id ASC
        """,
        jogo_id,
        evento_id,
    )
    return [dict(r) for r in rows]