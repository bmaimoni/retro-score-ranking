"""
Repository de seguidores — vínculo simples entre user_ids, sem escopo
de arena/event (docs/SEGUIR_SPEC.md decisão #8).
"""
from asyncpg import Pool


async def seguir(pool: Pool, seguidor_id: str, seguido_id: str) -> dict:
    """
    Reativa se já existiu (ativo=false) em vez de duplicar — mesmo
    padrão de event_games/memberships/nick_claims. Levanta erro de
    CHECK constraint se seguidor_id == seguido_id, ou de FK se
    seguido_id não existir — o router decide o que fazer com isso.
    """
    row = await pool.fetchrow(
        """
        INSERT INTO seguidores (seguidor_id, seguido_id)
        VALUES ($1, $2)
        ON CONFLICT (seguidor_id, seguido_id) DO UPDATE SET ativo = true
        RETURNING id, seguidor_id, seguido_id, ativo, criado_em
        """,
        seguidor_id, seguido_id,
    )
    return dict(row)


async def deixar_de_seguir(pool: Pool, seguidor_id: str, seguido_id: str) -> dict | None:
    """Soft-unfollow — ativo=false, nunca DELETE."""
    row = await pool.fetchrow(
        """
        UPDATE seguidores SET ativo = false
        WHERE seguidor_id = $1 AND seguido_id = $2 AND ativo = true
        RETURNING id, seguidor_id, seguido_id, ativo, criado_em
        """,
        seguidor_id, seguido_id,
    )
    return dict(row) if row else None


async def listar_seguindo(pool: Pool, user_id: str) -> list[dict]:
    """Quem este usuário segue, ativos, mais recentes primeiro."""
    rows = await pool.fetch(
        """
        SELECT u.id, u.nome, u.email, u.foto_url, u.avatar_id, s.criado_em AS seguindo_desde
        FROM seguidores s
        JOIN users u ON u.id = s.seguido_id
        WHERE s.seguidor_id = $1 AND s.ativo = true
        ORDER BY s.criado_em DESC
        """,
        user_id,
    )
    return [dict(r) for r in rows]


async def listar_seguidores(pool: Pool, user_id: str) -> list[dict]:
    """Quem segue este usuário, ativos, mais recentes primeiro."""
    rows = await pool.fetch(
        """
        SELECT u.id, u.nome, u.email, u.foto_url, u.avatar_id, s.criado_em AS seguindo_desde
        FROM seguidores s
        JOIN users u ON u.id = s.seguidor_id
        WHERE s.seguido_id = $1 AND s.ativo = true
        ORDER BY s.criado_em DESC
        """,
        user_id,
    )
    return [dict(r) for r in rows]


async def compilar_atividade(pool: Pool, user_id: str, desde) -> list[dict]:
    """
    Feed de superação (docs/SEGUIR_SPEC.md): pra cada pessoa que
    user_id segue, games em que o melhor score dela (de todos os
    tempos, entre todos os nicks que já usou — decisão #2) supera o
    melhor score do próprio user_id no mesmo game, E essa conquista
    aconteceu depois do maior entre (quando começou a seguir, corte de
    ultimo_login_em) — decisões #3/#6: sem backfill de histórico
    antigo, sem repetir o que já foi mostrado.

    `desde`: users.ultimo_login_em ANTERIOR a este login (capturado
    antes do update — ver auth/service.py e routers/perfil.py). Pode
    ser None (nunca conferiu o feed antes) — GREATEST ignora NULL.
    """
    rows = await pool.fetch(
        """
        WITH melhores_seguidos AS (
            SELECT DISTINCT ON (e.user_id, e.game_id)
                e.user_id AS seguido_id, e.game_id, e.pontuacao AS pontuacao_seguido,
                e.criado_em, s.criado_em AS seguindo_desde,
                u.nome AS seguido_nome, u.email AS seguido_email
            FROM entries e
            JOIN seguidores s ON s.seguido_id = e.user_id AND s.seguidor_id = $1 AND s.ativo = true
            JOIN users u ON u.id = e.user_id
            WHERE e.no_ranking = true AND e.arquivado = false
            ORDER BY e.user_id, e.game_id, e.pontuacao DESC, e.criado_em DESC
        ),
        minhas_melhores AS (
            SELECT game_id, MAX(pontuacao) AS minha_pontuacao
            FROM entries
            WHERE user_id = $1 AND no_ranking = true AND arquivado = false
            GROUP BY game_id
        )
        SELECT ms.seguido_id, ms.seguido_nome, ms.seguido_email,
               ms.game_id, j.nome AS game_nome, j.slug AS game_slug,
               ms.pontuacao_seguido, mm.minha_pontuacao, ms.criado_em
        FROM melhores_seguidos ms
        JOIN minhas_melhores mm ON mm.game_id = ms.game_id
        JOIN games j ON j.id = ms.game_id
        WHERE ms.pontuacao_seguido > mm.minha_pontuacao
          AND ms.criado_em > GREATEST(ms.seguindo_desde, $2)
        ORDER BY ms.criado_em DESC
        """,
        user_id, desde,
    )
    return [dict(r) for r in rows]
