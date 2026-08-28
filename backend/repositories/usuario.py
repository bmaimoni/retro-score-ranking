"""
Repository de perfil de usuário — leitura/edição dos campos de `users`
que a pessoa vê/edita na própria tela de perfil.

Ver docs/BACKLOG_2026.md §1 (itens 1.3/1.8) e migration 020. Distinto
de auth/repository.py, que cuida da mecânica de login/sessão — aqui é
só o dado de perfil em si.
"""
from asyncpg import Pool


async def buscar_perfil(pool: Pool, user_id: str) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT id, email, nome, foto_url, status,
               nome_completo, data_nascimento, cidade, estado, telefone,
               avatar_id, exclusao_solicitada_em, criado_em, ultimo_login_em
        FROM users WHERE id = $1
        """,
        user_id,
    )
    return dict(row) if row else None


async def atualizar_perfil(pool: Pool, user_id: str, dados: dict) -> dict | None:
    """Atualiza campos parciais. Chaves não presentes em `dados` ficam
    inalteradas (mesmo padrão de arena_repo.atualizar/event_repo.atualizar)."""
    row = await pool.fetchrow(
        """
        UPDATE users
        SET nome_completo    = COALESCE($2, nome_completo),
            data_nascimento  = COALESCE($3, data_nascimento),
            cidade           = COALESCE($4, cidade),
            estado           = COALESCE($5, estado),
            telefone         = COALESCE($6, telefone),
            avatar_id        = COALESCE($7, avatar_id)
        WHERE id = $1
        RETURNING id, email, nome, foto_url, status,
                  nome_completo, data_nascimento, cidade, estado, telefone,
                  avatar_id, criado_em, ultimo_login_em
        """,
        user_id,
        dados.get("nome_completo"),
        dados.get("data_nascimento"),
        dados.get("cidade"),
        dados.get("estado"),
        dados.get("telefone"),
        dados.get("avatar_id"),
    )
    return dict(row) if row else None


# ── Exclusão de conta (docs/EXCLUSAO_CONTA_SPEC.md) ─────────────────────────

async def solicitar_exclusao(pool: Pool, user_id: str) -> dict | None:
    """Inicia a janela de 30 dias — só em conta ativa sem solicitação
    já em andamento (idempotente: reenviar não reinicia o prazo)."""
    row = await pool.fetchrow(
        """
        UPDATE users SET exclusao_solicitada_em = now()
        WHERE id = $1 AND status = 'ativo' AND exclusao_solicitada_em IS NULL
        RETURNING id, exclusao_solicitada_em
        """,
        user_id,
    )
    return dict(row) if row else None


async def cancelar_exclusao(pool: Pool, user_id: str) -> dict | None:
    """Desistir dentro da janela de 30 dias (decisão #2) — só funciona
    antes da anonimização de verdade acontecer (status ainda 'ativo')."""
    row = await pool.fetchrow(
        """
        UPDATE users SET exclusao_solicitada_em = NULL
        WHERE id = $1 AND status = 'ativo' AND exclusao_solicitada_em IS NOT NULL
        RETURNING id, exclusao_solicitada_em
        """,
        user_id,
    )
    return dict(row) if row else None


async def buscar_para_exclusao(pool: Pool, user_id: str) -> dict | None:
    """Estado mínimo pra decidir se pode processar a anonimização."""
    row = await pool.fetchrow(
        "SELECT id, email, status, exclusao_solicitada_em FROM users WHERE id = $1",
        user_id,
    )
    return dict(row) if row else None


async def listar_exclusoes_pendentes(pool: Pool) -> list[dict]:
    """Solicitações em aberto (status ainda 'ativo', não anonimizado) —
    painel de super processa manualmente (sem job agendado, ver
    docs/EXCLUSAO_CONTA_SPEC.md §7). `elegivel`=true quando já passou
    dos 30 dias de janela de cancelamento."""
    rows = await pool.fetch(
        """
        SELECT id, email, nome, exclusao_solicitada_em,
               (exclusao_solicitada_em <= now() - interval '30 days') AS elegivel
        FROM users
        WHERE exclusao_solicitada_em IS NOT NULL AND status = 'ativo'
        ORDER BY exclusao_solicitada_em ASC
        """
    )
    return [dict(r) for r in rows]


async def anonimizar(conn, user_id: str, email_atual: str | None) -> dict | None:
    """
    Anonimização de verdade (decisão #6 do docs/EXCLUSAO_CONTA_SPEC.md
    §5 — não é só `users`): limpa dado pessoal de `users`, `identities`
    e `magic_link_tokens` (email é NOT NULL nas duas últimas, por isso
    placeholder em vez de NULL). Nick em `entries` nunca é tocado
    (decisão #6). `conn` é sempre uma conexão dentro de transação — quem
    chama garante isso (ver services/exclusao_conta.py).
    """
    if email_atual:
        await conn.execute(
            "UPDATE magic_link_tokens SET email = 'anonimizado@anonimizado.invalid' WHERE email = $1",
            email_atual,
        )

    await conn.execute(
        "UPDATE identities SET email = 'deletado-' || id || '@anonimizado.invalid' WHERE user_id = $1",
        user_id,
    )

    row = await conn.fetchrow(
        """
        UPDATE users
        SET email = NULL, nome = NULL, foto_url = NULL,
            nome_completo = NULL, data_nascimento = NULL,
            cidade = NULL, estado = NULL, telefone = NULL, avatar_id = NULL,
            status = 'excluido'
        WHERE id = $1
        RETURNING id, status
        """,
        user_id,
    )
    return dict(row) if row else None


async def desativar_pontuacoes(pool: Pool, user_id: str, identificador: str) -> int:
    """
    'Desativar pontuações' (item 1.5 do BACKLOG_2026.md §1) — ação leve
    e reversível, distinta de excluir conta (decisão #4 do
    EXCLUSAO_CONTA_SPEC.md §4: nunca no mesmo botão/fluxo). Reaproveita
    entries.arquivado, só em massa. Retorna quantas foram afetadas.
    """
    result = await pool.execute(
        """
        UPDATE entries SET arquivado = true, arquivado_em = now(), arquivado_por = $2
        WHERE user_id = $1 AND arquivado = false
        """,
        user_id, identificador,
    )
    return int(result.split()[-1])
