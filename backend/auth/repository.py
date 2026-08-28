"""
Repository de autenticação — SQL cru para as tabelas de auth
(users, identities, nick_claims, sessions, magic_link_tokens).

Ver docs/AUTH_SPEC.md §3 para o desenho completo, e migration 015
para o schema.
"""
from asyncpg import Pool


# ── users ──────────────────────────────────────────────────────

async def buscar_usuario_por_id(pool: Pool, user_id: str) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT id, email, email_verified, nome, foto_url, status,
               criado_em, ultimo_login_em
        FROM users WHERE id = $1
        """,
        user_id,
    )
    return dict(row) if row else None


async def buscar_usuario_por_email(pool: Pool, email: str) -> dict | None:
    """
    Busca por e-mail para account linking (AUTH_SPEC.md §4.1) — só deve
    ser usado quando o e-mail do provedor vem verificado.
    """
    row = await pool.fetchrow(
        """
        SELECT id, email, email_verified, nome, foto_url, status,
               criado_em, ultimo_login_em
        FROM users WHERE email = $1
        ORDER BY criado_em ASC
        LIMIT 1
        """,
        email,
    )
    return dict(row) if row else None


async def criar_usuario(
    pool: Pool,
    email: str | None,
    email_verified: bool,
    nome: str | None = None,
    foto_url: str | None = None,
) -> dict:
    """
    ultimo_login_em nasce NULL, não now() — desde o SEGUIR_SPEC.md
    (decisão #6) esse campo significa "última vez que o feed de
    atividade foi conferido", não mais "último login de fato" (a
    atualização foi deslocada pra quando GET /api/perfil/atividade é
    chamado, não mais pro momento do login em si — ver auth/service.py).
    """
    row = await pool.fetchrow(
        """
        INSERT INTO users (email, email_verified, nome, foto_url)
        VALUES ($1, $2, $3, $4)
        RETURNING id, email, email_verified, nome, foto_url, status,
                  criado_em, ultimo_login_em
        """,
        email, email_verified, nome, foto_url,
    )
    return dict(row)


async def atualizar_ultimo_login(pool: Pool, user_id: str) -> None:
    """
    Chamado a partir de services/seguidor.py (compilar_atividade), não
    mais do login em si — ver docs/SEGUIR_SPEC.md decisão #6. Adiar
    esse update pro momento em que o feed de atividade é realmente
    calculado é o que permite usar o valor anterior de ultimo_login_em
    como corte, sem precisar de tabela nova nem lidar com a entrega
    assíncrona do redirect do Google OAuth.
    """
    await pool.execute(
        "UPDATE users SET ultimo_login_em = now() WHERE id = $1", user_id
    )


# ── identities ─────────────────────────────────────────────────

async def buscar_identity(pool: Pool, provider: str, provider_user_id: str) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT id, user_id, provider, provider_user_id, email, criado_em
        FROM identities
        WHERE provider = $1 AND provider_user_id = $2
        """,
        provider, provider_user_id,
    )
    return dict(row) if row else None


async def criar_identity(
    pool: Pool,
    user_id: str,
    provider: str,
    provider_user_id: str,
    email: str,
) -> dict:
    row = await pool.fetchrow(
        """
        INSERT INTO identities (user_id, provider, provider_user_id, email)
        VALUES ($1, $2, $3, $4)
        RETURNING id, user_id, provider, provider_user_id, email, criado_em
        """,
        user_id, provider, provider_user_id, email,
    )
    return dict(row)


# ── nick_claims (ver docs/NICKNAME_SPEC.md — troca com soft-release) ────

async def buscar_nick_claim(pool: Pool, nick_norm: str) -> dict | None:
    """Só o claim ATIVO — um nick liberado (ativo=false) não bloqueia
    mais ninguém (decisão #5 do NICKNAME_SPEC.md). Índice único parcial
    (migration 020) já garante isso no banco; esta query espelha a
    mesma regra pra checagem em aplicação."""
    row = await pool.fetchrow(
        "SELECT id, nick, nick_norm, user_id, ativo, criado_em FROM nick_claims "
        "WHERE nick_norm = $1 AND ativo = true",
        nick_norm,
    )
    return dict(row) if row else None


async def nick_ja_foi_reivindicado_alguma_vez(pool: Pool, nick_norm: str) -> bool:
    """True se já existe QUALQUER linha (ativa ou não) pra este
    nick_norm — distingue 'primeira reivindicação de sempre' (decisão
    #11: vincula retroativamente) de 'nick liberado sendo reivindicado
    de novo' (decisão #7: fila de identificação ambígua)."""
    return await pool.fetchval(
        "SELECT EXISTS (SELECT 1 FROM nick_claims WHERE nick_norm = $1)",
        nick_norm,
    )


async def buscar_claim_ativo_do_usuario(pool: Pool, user_id: str) -> dict | None:
    """O 'nick atual do perfil' — claim ativo mais recente do usuário
    (decisão #2 do NICKNAME_SPEC.md). em_cooldown = true se foi criado
    há menos de 30 dias (decisão #6) — calculado no banco pra evitar
    diferença de fuso entre app e Postgres."""
    row = await pool.fetchrow(
        """
        SELECT id, nick, nick_norm, user_id, ativo, criado_em,
               (criado_em > now() - interval '30 days') AS em_cooldown
        FROM nick_claims
        WHERE user_id = $1 AND ativo = true
        ORDER BY criado_em DESC
        LIMIT 1
        """,
        user_id,
    )
    return dict(row) if row else None


async def criar_nick_claim(pool: Pool, nick: str, nick_norm: str, user_id: str) -> dict:
    """
    Reivindica um nick. Levanta erro de unique constraint se outro
    user_id já tiver um claim ATIVO desse nick_norm — o service decide
    o que fazer com isso.
    """
    row = await pool.fetchrow(
        """
        INSERT INTO nick_claims (nick, nick_norm, user_id)
        VALUES ($1, $2, $3)
        RETURNING id, nick, nick_norm, user_id, ativo, criado_em
        """,
        nick, nick_norm, user_id,
    )
    return dict(row)


async def liberar_claim(pool: Pool, claim_id: str) -> None:
    """Libera um claim (ativo=false) — nunca DELETE (decisão #5)."""
    await pool.execute(
        "UPDATE nick_claims SET ativo = false WHERE id = $1", claim_id
    )


async def listar_historico_nicks(pool: Pool, user_id: str) -> list[dict]:
    """Histórico completo de nicks do usuário (ativos e liberados),
    mais recente primeiro — decisão #4 do docs/NICKNAME_SPEC.md: painel
    de moderação mostra o histórico, não só o nick da entry isolada."""
    rows = await pool.fetch(
        """
        SELECT id, nick, nick_norm, ativo, criado_em
        FROM nick_claims
        WHERE user_id = $1
        ORDER BY criado_em DESC
        """,
        user_id,
    )
    return [dict(r) for r in rows]


async def registrar_troca_forcada(
    pool: Pool, user_id: str, nick_anterior: str | None, nick_novo: str, realizado_por: str
) -> None:
    """Auditoria de troca de nick forçada por admin/moderador (decisão
    #10 do docs/NICKNAME_SPEC.md) — log append-only, nunca editável."""
    await pool.execute(
        """
        INSERT INTO nick_troca_forcada_auditoria
            (user_id, nick_anterior, nick_novo, realizado_por)
        VALUES ($1, $2, $3, $4)
        """,
        user_id, nick_anterior, nick_novo, realizado_por,
    )


# ── sessions ───────────────────────────────────────────────────

async def criar_sessao(
    pool: Pool,
    user_id: str,
    ttl_days: int,
    user_agent: str | None = None,
    ip_hash: str | None = None,
) -> dict:
    row = await pool.fetchrow(
        """
        INSERT INTO sessions (user_id, expira_em, user_agent, ip_hash)
        VALUES ($1, now() + make_interval(days => $2), $3, $4)
        RETURNING id, user_id, criado_em, expira_em, revogada_em
        """,
        user_id, ttl_days, user_agent, ip_hash,
    )
    return dict(row)


async def buscar_sessao_ativa(pool: Pool, session_id: str) -> dict | None:
    """Só retorna a sessão se não revogada e ainda dentro do TTL."""
    row = await pool.fetchrow(
        """
        SELECT id, user_id, criado_em, expira_em, revogada_em
        FROM sessions
        WHERE id = $1
          AND revogada_em IS NULL
          AND expira_em > now()
        """,
        session_id,
    )
    return dict(row) if row else None


async def renovar_sessao(pool: Pool, session_id: str, ttl_days: int) -> None:
    """Sliding renewal — cada uso empurra o TTL pra frente (AUTH_SPEC.md §5)."""
    await pool.execute(
        "UPDATE sessions SET expira_em = now() + make_interval(days => $2) WHERE id = $1",
        session_id, ttl_days,
    )


async def revogar_sessao(pool: Pool, session_id: str) -> None:
    """Logout — nunca DELETE, sempre revogada_em (ver migration 015)."""
    await pool.execute(
        "UPDATE sessions SET revogada_em = now() WHERE id = $1 AND revogada_em IS NULL",
        session_id,
    )


async def revogar_todas_sessoes_usuario(pool, user_id: str) -> None:
    """Revoga toda sessão ativa do usuário — usado na anonimização de
    conta (docs/EXCLUSAO_CONTA_SPEC.md decisão #3). `pool` aceita tanto
    o Pool quanto uma conn dentro de transação (mesma convenção de
    repositories.entry.inserir)."""
    await pool.execute(
        "UPDATE sessions SET revogada_em = now() WHERE user_id = $1 AND revogada_em IS NULL",
        user_id,
    )


# ── magic_link_tokens ──────────────────────────────────────────

async def criar_magic_link_token(
    pool: Pool, email: str, token_hash: str, ttl_minutes: int
) -> dict:
    row = await pool.fetchrow(
        """
        INSERT INTO magic_link_tokens (email, token_hash, expira_em)
        VALUES ($1, $2, now() + make_interval(mins => $3))
        RETURNING id, email, criado_em, expira_em
        """,
        email, token_hash, ttl_minutes,
    )
    return dict(row)


async def buscar_magic_link_token_valido(pool: Pool, token_hash: str) -> dict | None:
    """Só retorna se não expirado e ainda não usado (single-use)."""
    row = await pool.fetchrow(
        """
        SELECT id, email, token_hash, criado_em, expira_em, usado_em
        FROM magic_link_tokens
        WHERE token_hash = $1
          AND expira_em > now()
          AND usado_em IS NULL
        """,
        token_hash,
    )
    return dict(row) if row else None


async def marcar_magic_link_usado(pool: Pool, token_id: str) -> None:
    await pool.execute(
        "UPDATE magic_link_tokens SET usado_em = now() WHERE id = $1", token_id
    )
