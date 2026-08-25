"""
Resolução de eventos.modo_ranking — os 5 modos de agregação de ranking.

Ver docs/RANKINGS_CONFIGURAVEIS_SPEC.md §2.1: cada evento escolhe como
compõe seu ranking. Tudo calculado ao vivo, nenhum dado espelhado — a
resolução aqui só decide QUAIS evento_ids entram na query de
entradas; quem lê o resultado (routers/evento_publico.py) decide como
buscar (listar_ranking_por_eventos ou o "geral" sem filtro de evento).
"""
from asyncpg import Pool


async def resolver_evento_ids(pool: Pool, evento: dict) -> list[str] | None:
    """
    Retorna a lista de evento_ids cujas entradas compõem o ranking
    deste evento, ou None para o modo 'geral' (sem filtro de evento —
    placar da plataforma inteira, sem opt-out, decisão #8).

    zerado           → só o próprio evento (comportamento padrão histórico)
    ultimo_evento    → só o evento anterior mais recente da mesma marca
                        (se não houver nenhum outro, cai de volta pro
                        próprio evento — marca só tem esse evento ainda)
    marca            → todos os eventos da marca com modo_ranking != 'zerado'
                        (participação binária por evento, decisão §2.1.C)
    marca_parceiras  → o mesmo conjunto de 'marca', mais os eventos
                        (também não-zerados) de toda marca com parceria
                        ativa concedida a esta marca (marcas_parcerias,
                        marca_origem=parceira, marca_destino=esta marca)
    geral            → None (placar escopo='global' já existente)
    """
    modo = evento["modo_ranking"]

    if modo == "geral":
        return None

    if modo == "zerado":
        return [str(evento["id"])]

    if modo == "ultimo_evento":
        row = await pool.fetchrow(
            """
            SELECT id FROM eventos
            WHERE marca_id = $1 AND id != $2
            ORDER BY data_inicio DESC
            LIMIT 1
            """,
            evento["marca_id"], evento["id"],
        )
        return [str(row["id"])] if row else [str(evento["id"])]

    if modo == "marca":
        rows = await pool.fetch(
            "SELECT id FROM eventos WHERE marca_id = $1 AND modo_ranking != 'zerado'",
            evento["marca_id"],
        )
        return [str(r["id"]) for r in rows] or [str(evento["id"])]

    if modo == "marca_parceiras":
        rows = await pool.fetch(
            """
            SELECT e.id
            FROM eventos e
            WHERE e.modo_ranking != 'zerado'
              AND (
                    e.marca_id = $1
                 OR e.marca_id IN (
                      SELECT marca_origem_id FROM marcas_parcerias
                      WHERE marca_destino_id = $1 AND ativo = true
                    )
              )
            """,
            evento["marca_id"],
        )
        return [str(r["id"]) for r in rows] or [str(evento["id"])]

    # modo desconhecido (não deveria acontecer, CHECK constraint no banco
    # já impede) — cai pro comportamento mais conservador.
    return [str(evento["id"])]
