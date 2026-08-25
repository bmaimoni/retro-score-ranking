"""
Repository de marcas_parcerias — concessões unidirecionais de acesso a
placar entre marcas.

Ver docs/RANKINGS_CONFIGURAVEIS_SPEC.md §2.2 e §4, e o comentário da
migration 024: cada linha é "origem libera o próprio placar pra
destino ver em modo_ranking=marca_parceiras". Mutualidade é resultado
de duas linhas (A→B e B→A), nunca uma propriedade da linha em si.
"""
from asyncpg import Pool


async def buscar(pool: Pool, origem_id: str, destino_id: str) -> dict | None:
    row = await pool.fetchrow(
        """
        SELECT id, marca_origem_id, marca_destino_id, ativo, criado_em
        FROM marcas_parcerias
        WHERE marca_origem_id = $1 AND marca_destino_id = $2
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
        INSERT INTO marcas_parcerias (marca_origem_id, marca_destino_id)
        VALUES ($1, $2)
        ON CONFLICT (marca_origem_id, marca_destino_id)
        DO UPDATE SET ativo = true
        RETURNING id, marca_origem_id, marca_destino_id, ativo, criado_em
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
        UPDATE marcas_parcerias SET ativo = false
        WHERE marca_origem_id = $1 AND marca_destino_id = $2 AND ativo = true
        RETURNING id, marca_origem_id, marca_destino_id, ativo, criado_em
        """,
        origem_id, destino_id,
    )
    return dict(row) if row else None


async def listar_concedidas(pool: Pool, marca_id: str) -> list[dict]:
    """Parcerias que esta marca concedeu (é a origem) — 'pra quem eu libero'."""
    rows = await pool.fetch(
        """
        SELECT mp.id, mp.marca_destino_id, m.nome AS marca_destino_nome,
               mp.ativo, mp.criado_em
        FROM marcas_parcerias mp
        JOIN marcas m ON m.id = mp.marca_destino_id
        WHERE mp.marca_origem_id = $1
        ORDER BY mp.criado_em DESC
        """,
        marca_id,
    )
    return [dict(r) for r in rows]


async def listar_recebidas(pool: Pool, marca_id: str) -> list[dict]:
    """
    Parcerias que outras marcas concederam a esta (é a destino) —
    'quem libera pra mim'. Só as ativas — uma liberação revogada não é
    'recebida' no sentido operacional, mesmo que a linha continue no
    histórico. reciproca=true quando esta marca já aceitou de volta
    (existe a linha inversa ativa) — usado pela UI pra distinguir
    'aguardando meu aceite' de 'já mútua'.
    """
    rows = await pool.fetch(
        """
        SELECT mp.id, mp.marca_origem_id, m.nome AS marca_origem_nome,
               mp.ativo, mp.criado_em,
               EXISTS (
                   SELECT 1 FROM marcas_parcerias r
                   WHERE r.marca_origem_id = mp.marca_destino_id
                     AND r.marca_destino_id = mp.marca_origem_id
                     AND r.ativo = true
               ) AS reciproca
        FROM marcas_parcerias mp
        JOIN marcas m ON m.id = mp.marca_origem_id
        WHERE mp.marca_destino_id = $1 AND mp.ativo = true
        ORDER BY mp.criado_em DESC
        """,
        marca_id,
    )
    return [dict(r) for r in rows]
