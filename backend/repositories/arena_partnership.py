"""
Repository de arena_partnerships — concessões unidirecionais de acesso a
placar entre arenas.

Ver docs/RANKINGS_CONFIGURAVEIS_SPEC.md §2.2 e §4, e o comentário da
migration 024: cada linha é "origem libera o próprio placar pra
destino ver em modo_ranking=marca_parceiras". Mutualidade é resultado
de duas linhas (A→B e B→A), nunca uma propriedade da linha em si.
"""
from asyncpg import Pool


async def buscar(pool: Pool, origem_id: str, destino_id: str) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT id, arena_origem_id, arena_destino_id, ativo, criado_em
        FROM arena_partnerships
        WHERE arena_origem_id = $1 AND arena_destino_id = $2
        """,
        origem_id, destino_id,
    )
    return dict(row) if row else None


async def criar_ou_reativar(pool: Pool, origem_id: str, destino_id: str) -> dict:
    """
    Cria (ou reativa) a linha origem→destino: origem libera o próprio
    placar pra destino. Usado tanto por 'liberar' (efeito imediato,
    decisão #5) quanto por 'aceitar' (cria a linha recíproca fechando
    a mutualidade, decisão #2 — quem chama já validou que a liberação
    original existe e está ativa).
    """
    row = await pool.fetchrow(
        """
        INSERT INTO arena_partnerships (arena_origem_id, arena_destino_id)
        VALUES ($1, $2)
        ON CONFLICT (arena_origem_id, arena_destino_id)
        DO UPDATE SET ativo = true
        RETURNING id, arena_origem_id, arena_destino_id, ativo, criado_em
        """,
        origem_id, destino_id,
    )
    return dict(row)


async def revogar(pool: Pool, origem_id: str, destino_id: str) -> dict | None:
    """
    Revoga a própria concessão (ativo=false na linha origem→destino).
    Não mexe na linha recíproca destino→origem — a mutualidade pode
    voltar a ficar assimétrica, decisão #5 aceita esse resultado
    explicitamente ("nada precisa ser limpo ou re-sincronizado").
    """
    row = await pool.fetchrow(
        """
        UPDATE arena_partnerships SET ativo = false
        WHERE arena_origem_id = $1 AND arena_destino_id = $2 AND ativo = true
        RETURNING id, arena_origem_id, arena_destino_id, ativo, criado_em
        """,
        origem_id, destino_id,
    )
    return dict(row) if row else None


async def listar_concedidas(pool: Pool, arena_id: str) -> list[dict]:
    """Parcerias que esta arena concedeu (é a origem) — 'pra quem eu libero'."""
    rows = await pool.fetch(
        """
        SELECT mp.id, mp.arena_destino_id, m.nome AS arena_destino_nome,
               mp.ativo, mp.criado_em
        FROM arena_partnerships mp
        JOIN arenas m ON m.id = mp.arena_destino_id
        WHERE mp.arena_origem_id = $1
        ORDER BY mp.criado_em DESC
        """,
        arena_id,
    )
    return [dict(r) for r in rows]


async def listar_recebidas(pool: Pool, arena_id: str) -> list[dict]:
    """
    Parcerias que outras arenas concederam a esta (é a destino) —
    'quem libera pra mim'. Só as ativas — uma liberação revogada não é
    'recebida' no sentido operacional, mesmo que a linha continue no
    histórico. reciproca=true quando esta arena já aceitou de volta
    (existe a linha inversa ativa) — usado pela UI pra distinguir
    'aguardando meu aceite' de 'já mútua'.
    """
    rows = await pool.fetch(
        """
        SELECT mp.id, mp.arena_origem_id, m.nome AS arena_origem_nome,
               mp.ativo, mp.criado_em,
               EXISTS (
                   SELECT 1 FROM arena_partnerships r
                   WHERE r.arena_origem_id = mp.arena_destino_id
                     AND r.arena_destino_id = mp.arena_origem_id
                     AND r.ativo = true
               ) AS reciproca
        FROM arena_partnerships mp
        JOIN arenas m ON m.id = mp.arena_origem_id
        WHERE mp.arena_destino_id = $1 AND mp.ativo = true
        ORDER BY mp.criado_em DESC
        """,
        arena_id,
    )
    return [dict(r) for r in rows]
