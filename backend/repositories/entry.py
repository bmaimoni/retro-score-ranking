from asyncpg import Pool
from typing import Any


async def inserir(conn, dados: dict) -> dict:
    row = await conn.fetchrow(
        """
        INSERT INTO entries
            (game_id, nick, nick_norm, nome, pontuacao, foto_url,
             no_ranking, superado, pendente, ip_hash, event_id, user_id)
        VALUES ($1, $2, $3, $4, $5, $6, $7, false, $8, $9, $10, $11)
        RETURNING id, game_id, nick, nome, pontuacao, foto_url,
                  no_ranking, pendente, criado_em, event_id, user_id
        """,
        dados["game_id"],
        dados["nick"],
        dados["nick_norm"],
        dados.get("nome"),
        dados["pontuacao"],
        dados["foto_url"],
        dados["no_ranking"],
        dados["pendente"],
        dados["ip_hash"],
        dados.get("event_id"),
        dados.get("user_id"),
    )
    return dict(row)


async def listar_ranking(pool: Pool, game_id: str) -> list[dict]:
    """
    Ranking público: apenas entries visíveis, não superadas, não pendentes.
    Ordenadas por pontuação decrescente.

    Em caso de empate de pontuação, desempata por criado_em (quem alcançou
    primeiro fica na frente) e por id como critério final. Sem isso, o
    Postgres não garante ordem estável entre linhas empatadas — a ordem
    pode mudar entre consultas e fazer uma entry "sumir" de listas
    truncadas (ex.: top 10 do telão).

    Usa o índice parcial idx_ranking.
    """
    rows = await pool.fetch(
        """
        SELECT id, nick, nome, pontuacao, foto_url, event_id, user_id, criado_em
        FROM entries
        WHERE game_id    = $1
          AND no_ranking = true
          AND superado   = false
          AND pendente   = false
          AND arquivado  = false
        ORDER BY pontuacao DESC, criado_em ASC, id ASC
        """,
        game_id,
    )
    return [dict(r) for r in rows]


def _filtros_feed_sql(
    idx_inicial: int,
    event_ids: list[str] | None,
    status: str | None,
    data_de,
    data_ate,
    game_id: str | None,
    sem_foto: bool,
    sem_identificacao: bool,
    busca: str | None,
) -> tuple[str, list]:
    """
    Monta a cláusula WHERE (string) e a lista de parâmetros posicionais
    pros filtros combináveis do feed admin (docs/BACKLOG_2026.md §4,
    itens 4.1/4.4). Compartilhada entre listar_feed_admin e
    contar_feed_admin — as duas precisam aplicar exatamente os mesmos
    filtros, senão X-Total-Count diverge da página retornada.

    status: 'visiveis' | 'ocultos' | 'pendentes' | None/'todos' (sem filtro).
    sem_foto/sem_identificacao: filtros separados, não um só — uma
    entry sem foto pode estar identificada, e vice-versa (decisão do
    item 4.1). "sem identificação" = user_id IS NULL AND nome IS NULL,
    mesmo critério de marcar_pendente_identificacao_ambigua
    (NICKNAME_SPEC.md decisão #7).
    busca: ILIKE sobre nick/game/event — extensão direta de WHERE,
    sem full-text search (decisão do item 4.4).
    """
    condicoes = ["(${0}::uuid[] IS NULL OR e.event_id = ANY(${0}::uuid[]))".format(idx_inicial)]
    params: list = [event_ids]
    idx = idx_inicial + 1

    if status == "visiveis":
        condicoes.append("e.pendente = false AND e.no_ranking = true")
    elif status == "ocultos":
        condicoes.append("e.pendente = false AND e.no_ranking = false")
    elif status == "pendentes":
        # arquivado = false é obrigatório aqui: uma entry
        # identificacao_ambigua que já expirou (30 dias, arquivamento
        # preguiçoso — ver _arquivar_identificacao_ambigua_expirada)
        # continua com pendente=true pra sempre; sem essa exclusão ela
        # nunca sai da fila "aguardando decisão", mesmo já resolvida.
        condicoes.append("e.pendente = true AND e.arquivado = false")
    # None/'todos' — sem filtro adicional, mesmo comportamento de sempre.

    if data_de is not None:
        condicoes.append(f"e.criado_em::date >= ${idx}"); params.append(data_de); idx += 1
    if data_ate is not None:
        condicoes.append(f"e.criado_em::date <= ${idx}"); params.append(data_ate); idx += 1
    if game_id is not None:
        condicoes.append(f"e.game_id = ${idx}"); params.append(game_id); idx += 1
    if sem_foto:
        condicoes.append("e.foto_url IS NULL")
    if sem_identificacao:
        condicoes.append("e.user_id IS NULL AND e.nome IS NULL")
    if busca:
        condicoes.append(f"(e.nick ILIKE ${idx} OR j.nome ILIKE ${idx} OR ev.nome ILIKE ${idx})")
        params.append(f"%{busca}%"); idx += 1

    return " AND ".join(condicoes), params


async def listar_feed_admin(
    pool: Pool,
    limit: int = 50,
    offset: int = 0,
    event_ids: list[str] | None = None,
    status: str | None = None,
    data_de=None,
    data_ate=None,
    game_id: str | None = None,
    sem_foto: bool = False,
    sem_identificacao: bool = False,
    busca: str | None = None,
) -> list[dict]:
    """
    Feed do admin: entries mais recentes primeiro, com filtros
    combináveis (docs/BACKLOG_2026.md §4.1/4.4) e busca sobre
    nick/game/event.

    event_ids: se informado, restringe às entries desses events —
    usado quando o admin não é super-admin (ver docs/MARCAS_SPEC.md §6,
    "efeito colateral necessário: feed e pendentes precisam saber o event").
    None = sem filtro (comportamento de sempre, usado por super-admin).

    e.pendente_motivo sempre vem junto (coluna simples, sem custo) — é
    o que o painel usa pra distinguir "identificação ambígua" de outros
    motivos (NICKNAME_SPEC.md decisão #7). Quando status='pendentes', a
    query também traz o contexto de ranking (melhor_score_atual/
    lider_pontuacao/posicao_se_aprovado, ex-listar_pendentes) — 3
    subqueries correlacionadas por linha, só valem o custo quando é
    literalmente essa fila que está sendo vista, não em "Todos".
    """
    await _arquivar_identificacao_ambigua_expirada(pool)

    where_sql, filtro_params = _filtros_feed_sql(
        3, event_ids, status, data_de, data_ate, game_id, sem_foto, sem_identificacao, busca,
    )

    contexto_pendente_sql = ""
    if status == "pendentes":
        contexto_pendente_sql = """,
               (
                   SELECT MAX(e2.pontuacao) FROM entries e2
                   WHERE e2.game_id = e.game_id AND e2.nick_norm = e.nick_norm
                     AND e2.no_ranking = true AND e2.pendente = false AND e2.arquivado = false
               ) AS melhor_score_atual,
               (
                   SELECT MAX(e3.pontuacao) FROM entries e3
                   WHERE e3.game_id = e.game_id AND e3.no_ranking = true
                     AND e3.pendente = false AND e3.superado = false AND e3.arquivado = false
               ) AS lider_pontuacao,
               (
                   SELECT COUNT(*) + 1 FROM entries e4
                   WHERE e4.game_id = e.game_id AND e4.no_ranking = true
                     AND e4.pendente = false AND e4.superado = false AND e4.arquivado = false
                     AND e4.pontuacao > e.pontuacao
               ) AS posicao_se_aprovado"""

    rows = await pool.fetch(
        f"""
        SELECT e.id, e.nick, e.nome, e.pontuacao, e.foto_url, e.event_id, e.no_ranking,
               e.superado, e.pendente, e.pendente_motivo, e.arquivado, e.user_id, e.criado_em, e.moderado_em,
               e.moderado_por, j.nome AS game_nome, j.slug AS game_slug,
               ev.nome AS event_nome, ev.slug AS event_slug{contexto_pendente_sql}
        FROM entries e
        JOIN games j ON j.id = e.game_id
        JOIN events ev ON ev.id = e.event_id
        WHERE {where_sql}
        ORDER BY e.criado_em DESC
        LIMIT $1 OFFSET $2
        """,
        limit, offset, *filtro_params,
    )
    return [dict(r) for r in rows]


async def contar_feed_admin(
    pool: Pool,
    event_ids: list[str] | None = None,
    status: str | None = None,
    data_de=None,
    data_ate=None,
    game_id: str | None = None,
    sem_foto: bool = False,
    sem_identificacao: bool = False,
    busca: str | None = None,
) -> int:
    """Total de entries no feed do admin sob os mesmos filtros de
    listar_feed_admin — para paginação (X-Total-Count)."""
    await _arquivar_identificacao_ambigua_expirada(pool)

    where_sql, filtro_params = _filtros_feed_sql(
        1, event_ids, status, data_de, data_ate, game_id, sem_foto, sem_identificacao, busca,
    )
    return await pool.fetchval(
        f"""
        SELECT COUNT(*) FROM entries e
        JOIN games j ON j.id = e.game_id
        JOIN events ev ON ev.id = e.event_id
        WHERE {where_sql}
        """,
        *filtro_params,
    )


async def _arquivar_identificacao_ambigua_expirada(pool: Pool) -> None:
    """
    Decisão #8 do docs/NICKNAME_SPEC.md, resolvida sem job agendado
    (NICKNAME_SPEC.md §4, mesmo princípio da decisão #15 — o projeto
    nunca teve cron): checagem preguiçosa, embutida toda vez que o feed
    admin é consultado (listar_feed_admin/contar_feed_admin — a fila de
    pendentes é só um status dentro dele desde a Fase 5). Arquiva na
    hora qualquer entry pendente_motivo='identificacao_ambigua' com
    mais de 30 dias — só
    "expira" de fato quando alguém abre o painel admin, não por relógio.
    Entries pendente_motivo='rate_limit' não têm prazo, não são tocadas.
    """
    await pool.execute(
        """
        UPDATE entries
        SET arquivado = true, arquivado_em = now(),
            arquivado_por = 'sistema (prazo de 30 dias expirado)'
        WHERE pendente = true AND pendente_motivo = 'identificacao_ambigua'
          AND criado_em < now() - interval '30 days'
          AND arquivado = false
        """
    )


async def atualizar_visibilidade(
    pool: Pool,
    entry_id: str,
    no_ranking: bool,
    moderado_por: str,
) -> dict | None:
    row = await pool.fetchrow(
        """
        UPDATE entries
        SET no_ranking   = $1,
            moderado_em  = now(),
            moderado_por = $2
        WHERE id = $3
        RETURNING id, game_id, nick, pontuacao, foto_url,
                  no_ranking, pendente, superado, criado_em
        """,
        no_ranking, moderado_por, entry_id,
    )
    return dict(row) if row else None


async def resolver_pendente(
    pool: Pool,
    entry_id: str,
    aprovar: bool,
    moderado_por: str,
) -> dict | None:
    """
    Aprova (pendente=false, no_ranking=true) ou
    oculta (pendente=false, no_ranking=false) uma entry pendente.
    """
    row = await pool.fetchrow(
        """
        UPDATE entries
        SET pendente     = false,
            no_ranking   = $1,
            moderado_em  = now(),
            moderado_por = $2
        WHERE id = $3
        RETURNING id, game_id, nick, pontuacao, foto_url,
                  no_ranking, pendente, superado, criado_em
        """,
        aprovar, moderado_por, entry_id,
    )
    return dict(row) if row else None


async def arquivar(pool: Pool, entry_id: str, arquivado_por: str) -> dict | None:
    """Arquivamento manual individual (NICKNAME_SPEC.md decisão #15 —
    pontuação nunca-identificada, por julgamento do moderador/admin, sem
    prazo fixo). Some do ranking público (queries já filtram
    arquivado=false) independente de no_ranking/pendente."""
    row = await pool.fetchrow(
        """
        UPDATE entries
        SET arquivado = true, arquivado_em = now(), arquivado_por = $1
        WHERE id = $2 AND arquivado = false
        RETURNING id, game_id, nick, pontuacao, no_ranking, pendente,
                  arquivado, criado_em
        """,
        arquivado_por, entry_id,
    )
    return dict(row) if row else None


async def buscar_por_id(pool: Pool, entry_id: str) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT e.*, j.slug AS game_slug
        FROM entries e
        JOIN games j ON j.id = e.game_id
        WHERE e.id = $1
        """,
        entry_id,
    )
    return dict(row) if row else None


async def vincular_retroativamente(pool: Pool, nick_norm: str, user_id: str) -> int:
    """
    Decisão #11 do docs/NICKNAME_SPEC.md: reivindicar um nick pela
    primeira vez (nunca teve dono antes) vincula automaticamente
    qualquer pontuação antiga com esse nick_norm que ainda não tinha
    user_id — sem fila de revisão, sem mecanismo novo. Retorna quantas
    entries foram vinculadas.
    """
    result = await pool.execute(
        "UPDATE entries SET user_id = $2 WHERE nick_norm = $1 AND user_id IS NULL",
        nick_norm, user_id,
    )
    return int(result.split()[-1])


async def marcar_pendente_identificacao_ambigua(pool: Pool, nick_norm: str) -> int:
    """
    Decisão #7 do docs/NICKNAME_SPEC.md: um nick liberado sendo
    reivindicado de novo não vincula ninguém automaticamente — só as
    entries antigas SEM user_id e SEM nome (nenhuma identificação)
    entram em fila de revisão do moderador. Entries já pendentes ou
    arquivadas não são reabertas. Retorna quantas foram marcadas.
    """
    result = await pool.execute(
        """
        UPDATE entries
        SET pendente = true, pendente_motivo = 'identificacao_ambigua'
        WHERE nick_norm = $1 AND user_id IS NULL AND nome IS NULL
          AND pendente = false AND arquivado = false
        """,
        nick_norm,
    )
    return int(result.split()[-1])


async def listar_por_usuario(pool: Pool, user_id: str) -> list[dict]:
    """
    Todas as pontuações do usuário logado, com game/event/arena — pra
    tela de perfil (BACKLOG_2026.md item 1.4: 'ver detalhamento de
    todas as próprias pontuações, event e arena de cada uma, link
    rápido pro game'). events.arena_id e entries.event_id são
    NOT NULL desde as migrations 019/011 — JOIN direto, sem LEFT.
    """
    rows = await pool.fetch(
        """
        SELECT e.id, e.nick, e.pontuacao, e.foto_url, e.no_ranking,
               e.superado, e.pendente, e.arquivado, e.criado_em,
               j.id AS game_id, j.nome AS game_nome, j.slug AS game_slug,
               ev.id AS event_id, ev.nome AS event_nome, ev.slug AS event_slug,
               m.id AS arena_id, m.nome AS arena_nome
        FROM entries e
        JOIN games j ON j.id = e.game_id
        JOIN events ev ON ev.id = e.event_id
        JOIN arenas m ON m.id = ev.arena_id
        WHERE e.user_id = $1
        ORDER BY e.criado_em DESC
        """,
        user_id,
    )
    return [dict(r) for r in rows]


async def historico_nick(pool: Pool, game_id: str, nick_norm: str) -> list[dict]:
    """
    Histórico de todas as entries de um nick em um game,
    ordenadas da mais recente para a mais antiga.
    Inclui entries superadas, arquivadas e ativas.
    """
    rows = await pool.fetch(
        """
        SELECT id, nick, nome, pontuacao, foto_url,
               no_ranking, superado, pendente, arquivado, criado_em, event_id
        FROM entries
        WHERE game_id   = $1
          AND nick_norm = $2
        ORDER BY criado_em DESC
        """,
        game_id, nick_norm,
    )
    return [dict(r) for r in rows]


async def listar_ranking_por_events(pool: Pool, game_id: str, event_ids: list[str]) -> list[dict]:
    """
    Ranking agregado de múltiplos events — modos 'ultimo_evento',
    'marca' e 'marca_parceiras' do docs/RANKINGS_CONFIGURAVEIS_SPEC.md
    §2.1. Inclui event_nome/event_slug/arena_nome em cada linha:
    decisão #1 da mesma spec exige rastreabilidade completa até
    game/event/arena de origem, sempre visível, sem exceção — mesmo
    quando os dados vêm de vários events misturados numa lista só.
    """
    rows = await pool.fetch(
        """
        SELECT e.id, e.nick, e.nome, e.pontuacao, e.foto_url, e.event_id,
               e.user_id, e.criado_em,
               ev.nome AS event_nome, ev.slug AS event_slug, m.nome AS arena_nome
        FROM entries e
        JOIN events ev ON ev.id = e.event_id
        JOIN arenas  m  ON m.id  = ev.arena_id
        WHERE e.game_id    = $1
          AND e.event_id  = ANY($2::uuid[])
          AND e.no_ranking = true
          AND e.superado   = false
          AND e.pendente   = false
          AND e.arquivado  = false
        ORDER BY e.pontuacao DESC, e.criado_em ASC, e.id ASC
        """,
        game_id, event_ids,
    )
    return [dict(r) for r in rows]


async def listar_lideres_por_events(pool: Pool, event_id_atual: str, event_ids: list[str] | None) -> dict:
    """
    Top 1 de cada game ativo do event atual (via event_games, ativo),
    mas com a pontuação/nick vindos do conjunto agregado event_ids —
    mesmo princípio de get_lideres_event, só que a fonte dos scores é
    resolvida por modo_ranking em vez de ficar presa ao próprio event.
    event_ids=None (modo 'geral') = sem filtro de event nenhum.
    """
    rows = await pool.fetch(
        """
        SELECT DISTINCT ON (e.game_id)
            e.game_id, j.slug, e.nick, e.pontuacao
        FROM entries e
        JOIN games j ON j.id = e.game_id
        JOIN event_games ej ON ej.game_id = e.game_id
                             AND ej.event_id = $1
                             AND ej.ativo = true
        WHERE ($2::uuid[] IS NULL OR e.event_id = ANY($2::uuid[]))
          AND e.no_ranking = true
          AND e.superado   = false
          AND e.pendente   = false
          AND e.arquivado  = false
        ORDER BY e.game_id, e.pontuacao DESC, e.criado_em ASC, e.id ASC
        """,
        event_id_atual, event_ids,
    )
    return {
        str(r["game_id"]): {"slug": r["slug"], "nick": r["nick"], "pontuacao": r["pontuacao"]}
        for r in rows
    }


async def listar_ranking_por_event(
    pool: Pool,
    game_id: str,
    event_id: str,
) -> list[dict]:
    """
    Ranking filtrado por event.
    Retorna apenas scores registrados neste event específico.

    Mesmo desempate de listar_ranking (criado_em ASC, id ASC) para evitar
    ordem instável entre pontuações empatadas.
    """
    rows = await pool.fetch(
        """
        SELECT id, nick, nome, pontuacao, foto_url, event_id, user_id, criado_em
        FROM entries
        WHERE game_id    = $1
          AND event_id  = $2
          AND no_ranking = true
          AND superado   = false
          AND pendente   = false
          AND arquivado  = false
        ORDER BY pontuacao DESC, criado_em ASC, id ASC
        """,
        game_id,
        event_id,
    )
    return [dict(r) for r in rows]