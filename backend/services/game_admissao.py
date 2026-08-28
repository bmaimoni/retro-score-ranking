"""
Admissão do caminho manual de cadastro de jogo — colisão de nome
(docs/CATALOGO_JOGOS_SPEC.md 5.6). Sem heurística de "suspeito"/draft
— esse conceito é exclusivo de arena (Fase 8); games.pendente_aprovacao
já cumpre esse papel pro caminho manual de jogo (só pula pra aprovado
direto via games.igdb_id, ver routers/admin.py:criar_game).

Reaproveita a normalização de texto de services/arena_admissao.py —
minúsculo/sem acento/pontuação não é lógica exclusiva de arena, evita
duplicar a mesma função em dois módulos.
"""
from dataclasses import dataclass

from services.arena_admissao import normalizar


@dataclass
class ResultadoColisao:
    bloqueado: bool
    motivo: str | None = None


def avaliar_colisao(nome: str, existentes: list[dict]) -> ResultadoColisao:
    """
    existentes: [{"nome": str}, ...] de todo game ativo já cadastrado.

    Bloqueio (409): nome normalizado do candidato bate exato com um
    existente, ou um é substring do outro — mesmo critério de bloqueio
    exato/substring de B.2 (docs/ARENA_SPEC.md), sem a parte de
    heurística "suspeito" que B.2/B.4 juntos têm pra arena.
    """
    cand = normalizar(nome)
    if not cand:
        return ResultadoColisao(bloqueado=False)

    for existente in existentes:
        exist = normalizar(existente["nome"])
        if not exist:
            continue
        if cand == exist or cand in exist or exist in cand:
            return ResultadoColisao(
                bloqueado=True,
                motivo=(
                    f'Nome muito parecido com um jogo já cadastrado '
                    f'("{existente["nome"]}") — escolha outro, ou busque na IGDB.'
                ),
            )

    return ResultadoColisao(bloqueado=False)
