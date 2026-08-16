"""
Router admin de telões — requer autenticação.
Prefixo: /api/admin/teloes

Ver docs/EVENTOS_SPEC.md §3: um telão aponta pra exatamente um evento OU
um placar (CHECK teloes_evento_ou_placar no banco). Cada telão escolhe
seus próprios jogos/ordem via telao_jogos, independente de evento_jogos.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator
import repositories.telao as telao_repo
from utils.db import get_pool
from middleware.auth import require_admin

router = APIRouter(prefix="/api/admin/teloes", tags=["admin-teloes"])


class TelaoCreate(BaseModel):
    nome: str
    slug: str
    top_n: int = 10
    evento_id: str | None = None
    placar_id: str | None = None

    @model_validator(mode="after")
    def evento_xor_placar(self):
        if (self.evento_id is not None) == (self.placar_id is not None):
            raise ValueError(
                "Informe exatamente um entre evento_id e placar_id, nunca os dois nem nenhum"
            )
        return self


class TelaoUpdate(BaseModel):
    nome:  str | None = None
    top_n: int | None = None


class TelaoJogoUpdate(BaseModel):
    ativo: bool | None = None
    ordem: int | None = None


# ── CRUD de telões ─────────────────────────────────────────────

@router.get("")
async def listar_teloes(pool=Depends(get_pool), _=Depends(require_admin)):
    return await telao_repo.listar_todos(pool)


@router.post("", status_code=201)
async def criar_telao(
    dados: TelaoCreate,
    pool=Depends(get_pool),
    _=Depends(require_admin),
):
    """
    Cria um telão. A validação evento_id XOR placar_id acontece no schema
    Pydantic (422 antes de chegar no banco); o CHECK teloes_evento_ou_placar
    no banco é a segunda linha de defesa.
    """
    try:
        return await telao_repo.criar(
            pool, dados.nome, dados.slug, dados.top_n,
            dados.evento_id, dados.placar_id,
        )
    except Exception as exc:
        if "unique" in str(exc).lower():
            raise HTTPException(status_code=409, detail="Slug já existe")
        if "foreign key" in str(exc).lower():
            raise HTTPException(status_code=404, detail="Evento ou placar não encontrado")
        raise


@router.patch("/{telao_id}")
async def atualizar_telao(
    telao_id: str,
    dados: TelaoUpdate,
    pool=Depends(get_pool),
    _=Depends(require_admin),
):
    """Atualiza nome e/ou top_n. evento_id/placar_id são imutáveis após criação."""
    telao = await telao_repo.atualizar(pool, telao_id, dados.model_dump(exclude_none=True))
    if not telao:
        raise HTTPException(status_code=404, detail="Telão não encontrado")
    return telao


# ── Gestão de jogos do telão ───────────────────────────────────

@router.get("/{telao_id}/jogos")
async def listar_jogos_do_telao(
    telao_id: str,
    pool=Depends(get_pool),
    _=Depends(require_admin),
):
    """Lista jogos vinculados ao telão (ativos e inativos)."""
    return await telao_repo.listar_jogos_do_telao(pool, telao_id)


@router.post("/{telao_id}/jogos/{jogo_id}", status_code=201)
async def adicionar_jogo_ao_telao(
    telao_id: str,
    jogo_id: str,
    ordem: int = 0,
    pool=Depends(get_pool),
    _=Depends(require_admin),
):
    """Adiciona jogo ao telão. Se já existir, reativa e atualiza ordem."""
    try:
        return await telao_repo.adicionar_jogo(pool, telao_id, jogo_id, ordem)
    except Exception as exc:
        if "foreign key" in str(exc).lower():
            raise HTTPException(status_code=404, detail="Telão ou jogo não encontrado")
        raise


@router.patch("/{telao_id}/jogos/{jogo_id}")
async def atualizar_jogo_do_telao(
    telao_id: str,
    jogo_id: str,
    dados: TelaoJogoUpdate,
    pool=Depends(get_pool),
    _=Depends(require_admin),
):
    """Atualiza ativo e/ou ordem de um jogo no telão."""
    resultado = await telao_repo.atualizar_jogo(
        pool, telao_id, jogo_id, dados.model_dump(exclude_none=True)
    )
    if not resultado:
        raise HTTPException(status_code=404, detail="Vínculo não encontrado")
    return resultado
