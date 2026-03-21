from asyncpg import Pool
from fastapi import HTTPException


async def validar_score(pool: Pool, jogo_id: str, pontuacao: int) -> None:
    """
    Valida a pontuação contra as regras do jogo:
    - deve ser > 0 (já garantido pelo schema Pydantic)
    - não pode exceder score_max do jogo (se definido)

    Levanta HTTPException 422 se inválido.
    """
    row = await pool.fetchrow(
        "SELECT score_max FROM jogos WHERE id = $1 AND ativo = true",
        jogo_id,
    )

    if not row:
        raise HTTPException(status_code=404, detail="Jogo não encontrado ou inativo")

    score_max = row["score_max"]
    if score_max is not None and pontuacao > score_max:
        raise HTTPException(
            status_code=422,
            detail=f"Pontuação {pontuacao} excede o máximo permitido ({score_max}) para este jogo",
        )
