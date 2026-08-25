"""
Router admin de eventos — requer autenticação.
Prefixo: /api/admin/eventos

Ver docs/PERMISSOES_SPEC.md §4: criar/editar evento (e os jogos dele)
é ação de admin, nunca moderador, e sempre restrita à própria marca —
só super opera fora dela. marca_id é obrigatório desde a migration 019
(decisão #6: todo evento exige marca, mesmo os de edição única).
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from datetime import datetime
from utils.db import get_pool
from middleware.auth import require_admin, AdminContext
import repositories.evento      as evento_repo
import repositories.evento_jogo as evento_jogo_repo

router = APIRouter(prefix="/api/admin/eventos", tags=["admin-eventos"])


TIPOGRAFIAS_VALIDAS = {"arcade", "futurista", "terminal"}


def _validar_tipografia(v):
    if v is not None and v not in TIPOGRAFIAS_VALIDAS:
        raise ValueError(f"tipografia deve ser uma de {sorted(TIPOGRAFIAS_VALIDAS)}")
    return v


class EventoCreate(BaseModel):
    nome:         str
    slug:         str
    ativo:        bool = True
    publico:      bool = True
    logo_url:     str | None = None
    cor_primaria: str | None = None
    tipografia:   str | None = None
    marca_id:     str
    data_inicio:  datetime
    data_fim:     datetime

    _valida_tipografia = field_validator("tipografia")(_validar_tipografia)

    @field_validator("data_fim")
    @classmethod
    def data_fim_apos_inicio(cls, v, info):
        inicio = info.data.get("data_inicio")
        if inicio and v <= inicio:
            raise ValueError("data_fim deve ser posterior a data_inicio")
        return v


class EventoUpdate(BaseModel):
    nome:         str | None = None
    ativo:        bool | None = None
    publico:      bool | None = None
    logo_url:     str | None = None
    cor_primaria: str | None = None
    tipografia:   str | None = None
    marca_id:     str | None = None
    data_inicio:  datetime | None = None
    data_fim:     datetime | None = None

    _valida_tipografia = field_validator("tipografia")(_validar_tipografia)


class EventoJogoUpdate(BaseModel):
    ativo: bool | None = None
    ordem: int | None = None


def _exigir_admin_na_marca(admin: AdminContext, marca_id: str, acao: str):
    if not admin.super and not admin.eh_admin_na_marca(marca_id):
        raise HTTPException(status_code=403, detail=f"Sem permissão para {acao} nesta marca")


async def _resolver_evento_ou_404(pool, evento_id: str) -> dict:
    evento = await evento_repo.buscar_por_id(pool, evento_id)
    if not evento:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    return evento


# ── CRUD de eventos ───────────────────────────────────────────

@router.get("")
async def listar_eventos(pool=Depends(get_pool), admin: AdminContext = Depends(require_admin)):
    """super vê todos; admin/moderador escopado só os eventos das
    marcas onde tem vínculo — sem isso, qualquer admin autenticado
    enxergava eventos de qualquer marca aqui (achado incidental ao
    escopar este router)."""
    eventos = await evento_repo.listar(pool)
    if admin.super:
        return eventos
    return [e for e in eventos if admin.tem_acesso_na_marca(e["marca_id"])]


@router.get("/ativos")
async def listar_ativos(pool=Depends(get_pool)):
    """Público — usado pelo frontend para listar eventos ativos."""
    return await evento_repo.listar_ativos(pool)


@router.post("", status_code=201)
async def criar_evento(
    dados: EventoCreate,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    _exigir_admin_na_marca(admin, dados.marca_id, "criar evento")
    try:
        return await evento_repo.criar(pool, dados.model_dump())
    except Exception as exc:
        if "unique" in str(exc).lower():
            raise HTTPException(status_code=409, detail="Slug já existe")
        raise


@router.patch("/{evento_id}")
async def atualizar_evento(
    evento_id: str,
    dados: EventoUpdate,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    evento_atual = await _resolver_evento_ou_404(pool, evento_id)
    _exigir_admin_na_marca(admin, evento_atual["marca_id"], "editar este evento")

    if not admin.super and dados.marca_id is not None and dados.marca_id != evento_atual["marca_id"]:
        raise HTTPException(status_code=403, detail="Só super-admin pode mover evento entre marcas")

    evento = await evento_repo.atualizar(
        pool, evento_id, dados.model_dump(exclude_none=True)
    )
    if not evento:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    return evento


# ── Gestão de jogos por evento ────────────────────────────────

@router.get("/{evento_id}/jogos")
async def listar_jogos_do_evento(
    evento_id: str,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """Lista jogos vinculados ao evento (ativos e inativos). Leitura:
    liberada pra quem tem qualquer acesso à marca (admin ou moderador),
    não só admin."""
    evento = await _resolver_evento_ou_404(pool, evento_id)
    if not admin.super and not admin.tem_acesso_na_marca(evento["marca_id"]):
        raise HTTPException(status_code=403, detail="Sem acesso a este evento")
    return await evento_jogo_repo.listar_por_evento(pool, evento_id)


@router.post("/{evento_id}/jogos/{jogo_id}", status_code=201)
async def adicionar_jogo_ao_evento(
    evento_id: str,
    jogo_id: str,
    ordem: int = 0,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """Adiciona jogo ao evento. Se já existir, reativa."""
    evento = await _resolver_evento_ou_404(pool, evento_id)
    _exigir_admin_na_marca(admin, evento["marca_id"], "editar os jogos deste evento")

    try:
        return await evento_jogo_repo.adicionar(pool, evento_id, jogo_id, ordem)
    except Exception as exc:
        if "foreign key" in str(exc).lower():
            raise HTTPException(status_code=404, detail="Evento ou jogo não encontrado")
        raise


@router.patch("/{evento_id}/jogos/{jogo_id}")
async def atualizar_jogo_do_evento(
    evento_id: str,
    jogo_id: str,
    dados: EventoJogoUpdate,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """Atualiza ativo e/ou ordem de um jogo num evento."""
    evento = await _resolver_evento_ou_404(pool, evento_id)
    _exigir_admin_na_marca(admin, evento["marca_id"], "editar os jogos deste evento")

    resultado = await evento_jogo_repo.atualizar(
        pool, evento_id, jogo_id, dados.model_dump(exclude_none=True)
    )
    if not resultado:
        raise HTTPException(status_code=404, detail="Vínculo não encontrado")
    return resultado
