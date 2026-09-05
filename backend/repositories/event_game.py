from asyncpg import Pool


async def listar_por_event(pool: Pool, event_id: str) -> list[dict]:
    """Jogos ativos de um evento, ordenados pelo campo ordem."""
    rows = await pool.fetch(
        """
        SELECT
            j.id, j.nome, j.slug, j.score_max,
            ej.ativo, ej.ordem
        FROM event_games ej
        JOIN games j ON j.id = ej.game_id
        WHERE ej.event_id = $1
          AND ej.ativo     = true
          AND j.ativo      = true
        ORDER BY ej.ordem, j.nome
        """,
        event_id,
    )
    return [dict(r) for r in rows]


async def listar_por_event_admin(pool: Pool, event_id: str) -> list[dict]:
    """Todos os jogos vinculados ao event — vínculo ativo E inativo, e
    mesmo que o jogo esteja desativado globalmente. Uso exclusivo do
    painel admin (docs/PAINEIS_ADMIN_SPEC.md Fase I): a versão pública
    (listar_por_event, acima) filtra por ativo de propósito, pra
    ranking/telão nunca mostrarem jogo desligado — mas isso faz o vínculo
    desaparecer da tela do admin assim que ele desativa, sem jeito de
    reativar. `jogo_ativo_global` deixa o frontend avisar quando o jogo
    está oculto por decisão de super (catálogo global), não do vínculo
    deste event."""
    rows = await pool.fetch(
        """
        SELECT
            j.id, j.nome, j.slug, j.score_max,
            j.ativo AS jogo_ativo_global, j.pendente_aprovacao,
            j.generos, j.geracoes,
            ej.ativo, ej.ordem
        FROM event_games ej
        JOIN games j ON j.id = ej.game_id
        WHERE ej.event_id = $1
        ORDER BY ej.ordem, j.nome
        """,
        event_id,
    )
    return [dict(r) for r in rows]


async def adicionar(pool: Pool, event_id: str, game_id: str, ordem: int = 0) -> dict:
    """Adiciona game ao event. Se já existir, reativa e atualiza ordem."""
    row = await pool.fetchrow(
        """
        INSERT INTO event_games (event_id, game_id, ordem)
        VALUES ($1, $2, $3)
        ON CONFLICT (event_id, game_id)
        DO UPDATE SET ativo = true, ordem = EXCLUDED.ordem
        RETURNING id, event_id, game_id, ativo, ordem, criado_em
        """,
        event_id, game_id, ordem,
    )
    return dict(row)


async def atualizar(pool: Pool, event_id: str, game_id: str, dados: dict) -> dict | None:
    """Atualiza ativo e/ou ordem de um game num event."""
    row = await pool.fetchrow(
        """
        UPDATE event_games
        SET ativo = COALESCE($3, ativo),
            ordem = COALESCE($4, ordem)
        WHERE event_id = $1
          AND game_id   = $2
        RETURNING id, event_id, game_id, ativo, ordem, criado_em
        """,
        event_id, game_id,
        dados.get("ativo"),
        dados.get("ordem"),
    )
    return dict(row) if row else None


# CATALOGO_JOGOS_SPEC.md Fase 9 — substitui o reorder manual jogo a
# jogo por um recálculo em lote de `ordem`, disparado por critério
# escolhido na config do event. Chaves fixas (nunca vêm direto do
# usuário pra dentro do SQL) — validação real acontece no router
# (Literal do Pydantic), o ValueError aqui é só defesa em profundidade.
_CRITERIOS_ORDER_BY = {
    "nome":        "j.nome",
    "ano":         "j.ano_lancamento NULLS LAST, j.nome",
    "plataforma":  "j.plataforma NULLS LAST, j.nome",
    "pontuacoes":  "COALESCE(p.qtd, 0) DESC, j.nome",
}


async def reordenar_por_criterio(pool: Pool, event_id: str, criterio: str) -> list[dict]:
    """Recalcula e regrava `ordem` de todo jogo vinculado ao event
    (ativo e inativo no vínculo), por um dos critérios pré-definidos.
    "pontuacoes" conta só entries válidas (não pendente, não oculta do
    ranking) daquele jogo neste event — reflete popularidade real, não
    volume bruto de envio (docs/CATALOGO_JOGOS_SPEC.md Fase 9, 9.3)."""
    if criterio not in _CRITERIOS_ORDER_BY:
        raise ValueError(f"criterio inválido: {criterio!r}")
    order_by = _CRITERIOS_ORDER_BY[criterio]

    rows = await pool.fetch(
        f"""
        WITH pontuacoes_validas AS (
            SELECT game_id, COUNT(*) AS qtd
            FROM entries
            WHERE event_id = $1 AND pendente = false AND no_ranking = true
            GROUP BY game_id
        ),
        ranqueado AS (
            SELECT
                ej.id,
                ROW_NUMBER() OVER (ORDER BY {order_by}) - 1 AS nova_ordem
            FROM event_games ej
            JOIN games j ON j.id = ej.game_id
            LEFT JOIN pontuacoes_validas p ON p.game_id = j.id
            WHERE ej.event_id = $1
        )
        UPDATE event_games eg
        SET ordem = ranqueado.nova_ordem
        FROM ranqueado
        WHERE eg.id = ranqueado.id
        RETURNING eg.id, eg.game_id, eg.ordem
        """,
        event_id,
    )
    return [dict(r) for r in rows]
