"""
Resolução de events.modo_ranking — os 5 modos de agregação de ranking.

Ver docs/RANKINGS_CONFIGURAVEIS_SPEC.md §2.1: cada event escolhe como
compõe seu ranking. Tudo calculado ao vivo, nenhum dado espelhado — a
resolução aqui só decide QUAIS event_ids entram na query de
entries; quem lê o resultado (routers/event_public.py) decide como
buscar (listar_ranking_por_events ou o "geral" sem filtro de event).
"""
from asyncpg import Pool


async def resolver_event_ids(pool: Pool, event: dict) -> list[str] | None:
    """
    Retorna a lista de event_ids cujas entries compõem o ranking
    deste event, ou None para o modo 'geral' (sem filtro de event —
    placar da plataforma inteira, sem opt-out, decisão #8).

    zerado           → só o próprio event (comportamento padrão histórico)
    ultimo_evento    → só o event anterior mais recente da mesma arena
                        (se não houver nenhum outro, cai de volta pro
                        próprio event — arena só tem esse event ainda)
    marca            → todos os events da arena com modo_ranking != 'zerado'
                        (participação binária por event, decisão §2.1.C)
    marca_parceiras  → o mesmo conjunto de 'marca', mais os events
                        (também não-zerados) de toda arena com parceria
                        ativa concedida a esta arena (arena_partnerships,
                        arena_origem=parceira, arena_destino=esta arena)
    geral            → None (placar escopo='global' já existente)
    """
    modo = event["modo_ranking"]

    if modo == "geral":
        return None

    if modo == "zerado":
        return [str(event["id"])]

    if modo == "ultimo_evento":
        row = await pool.fetchrow(
            """
            SELECT id FROM events
            WHERE arena_id = $1 AND id != $2
            ORDER BY data_inicio DESC
            LIMIT 1
            """,
            event["arena_id"], event["id"],
        )
        return [str(row["id"])] if row else [str(event["id"])]

    if modo == "marca":
        rows = await pool.fetch(
            "SELECT id FROM events WHERE arena_id = $1 AND modo_ranking != 'zerado'",
            event["arena_id"],
        )
        return [str(r["id"]) for r in rows] or [str(event["id"])]

    if modo == "marca_parceiras":
        rows = await pool.fetch(
            """
            SELECT e.id
            FROM events e
            WHERE e.modo_ranking != 'zerado'
              AND (
                    e.arena_id = $1
                 OR e.arena_id IN (
                      SELECT arena_origem_id FROM arena_partnerships
                      WHERE arena_destino_id = $1 AND ativo = true
                    )
              )
            """,
            event["arena_id"],
        )
        return [str(r["id"]) for r in rows] or [str(event["id"])]

    # modo desconhecido (não deveria acontecer, CHECK constraint no banco
    # já impede) — cai pro comportamento mais conservador.
    return [str(event["id"])]
