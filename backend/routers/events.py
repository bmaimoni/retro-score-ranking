"""
Router admin de events — requer autenticação.
Prefixo: /api/admin/events

Ver docs/PERMISSOES_SPEC.md §4: criar/editar event (e os games dele)
é ação de admin, nunca moderador, e sempre restrita à própria arena —
só super opera fora dela. arena_id é obrigatório desde a migration 019
(decisão #6: todo event exige arena, mesmo os de edição única).
"""
import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Literal
from utils.db import get_pool
from middleware.auth import require_admin, AdminContext
import repositories.event      as event_repo
import repositories.event_game as event_game_repo

router = APIRouter(prefix="/api/admin/events", tags=["admin-events"])
log = structlog.get_logger()


TIPOGRAFIAS_VALIDAS = {"arcade", "futurista", "terminal"}
MODOS_RANKING_VALIDOS = {"zerado", "ultimo_evento", "marca", "marca_parceiras", "geral"}


def _validar_modo_ranking(v):
    if v is not None and v not in MODOS_RANKING_VALIDOS:
        raise ValueError(f"modo_ranking deve ser um de {sorted(MODOS_RANKING_VALIDOS)}")
    return v


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
    arena_id:     str
    data_inicio:  datetime
    data_fim:     datetime
    modo_ranking: str = "zerado"

    _valida_tipografia = field_validator("tipografia")(_validar_tipografia)
    _valida_modo_ranking = field_validator("modo_ranking")(_validar_modo_ranking)

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
    arena_id:     str | None = None
    data_inicio:  datetime | None = None
    data_fim:     datetime | None = None
    modo_ranking: str | None = None

    _valida_tipografia = field_validator("tipografia")(_validar_tipografia)
    _valida_modo_ranking = field_validator("modo_ranking")(_validar_modo_ranking)


class EventoJogoUpdate(BaseModel):
    ativo: bool | None = None
    ordem: int | None = None


class OrdenarGamesBody(BaseModel):
    criterio: Literal["nome", "ano", "plataforma", "pontuacoes"]


def _exigir_admin_na_arena(admin: AdminContext, arena_id: str, acao: str):
    if not admin.super and not admin.eh_admin_na_arena(arena_id):
        raise HTTPException(status_code=403, detail=f"Sem permissão para {acao} nesta arena")


async def _resolver_event_ou_404(pool, event_id: str) -> dict:
    event = await event_repo.buscar_por_id(pool, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    return event


# ── CRUD de events ───────────────────────────────────────────

@router.get("")
async def listar_events(pool=Depends(get_pool), admin: AdminContext = Depends(require_admin)):
    """super vê todos; admin/moderador escopado só os events das
    arenas onde tem vínculo — sem isso, qualquer admin autenticado
    enxergava events de qualquer arena aqui (achado incidental ao
    escopar este router)."""
    events = await event_repo.listar(pool)
    if admin.super:
        return events
    return [e for e in events if admin.tem_acesso_na_arena(e["arena_id"])]


@router.get("/ativos")
async def listar_ativos(pool=Depends(get_pool)):
    """Público — usado pelo frontend para listar events ativos."""
    return await event_repo.listar_ativos(pool)


@router.post("", status_code=201)
async def criar_event(
    dados: EventoCreate,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    _exigir_admin_na_arena(admin, dados.arena_id, "criar event")
    try:
        return await event_repo.criar(pool, dados.model_dump())
    except Exception as exc:
        if "unique" in str(exc).lower():
            raise HTTPException(status_code=409, detail="Slug já existe")
        raise


@router.patch("/{event_id}")
async def atualizar_event(
    event_id: str,
    dados: EventoUpdate,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    event_atual = await _resolver_event_ou_404(pool, event_id)
    _exigir_admin_na_arena(admin, event_atual["arena_id"], "editar este event")

    if not admin.super and dados.arena_id is not None and dados.arena_id != event_atual["arena_id"]:
        raise HTTPException(status_code=403, detail="Só super-admin pode mover event entre arenas")

    event = await event_repo.atualizar(
        pool, event_id, dados.model_dump(exclude_none=True)
    )
    if not event:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    return event


# ── Deleção física real (SUPER_SPEC.md §7, Fase 4) ──────────────

@router.get("/vazios")
async def listar_events_vazios(pool=Depends(get_pool), admin: AdminContext = Depends(require_admin)):
    """Events sem nenhuma entry — únicos candidatos seguros a apagar de
    vez. Console só oferece o botão de deleção física pra esses."""
    if not admin.super:
        raise HTTPException(status_code=403, detail="Só super-admin pode listar events sem uso")
    return await event_repo.listar_vazios(pool)


class DeletarEventBody(BaseModel):
    confirmar_slug: str


@router.delete("/{event_id}")
async def deletar_event(
    event_id: str,
    dados: DeletarEventBody,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """DELETE físico real — só quando o event não tem nenhuma entry
    (docs/SUPER_SPEC.md §7, S.3). Diferente de arquivar: não é
    reversível. Exige digitar o slug exato como confirmação (S.5)."""
    if not admin.super:
        raise HTTPException(status_code=403, detail="Só super-admin pode apagar um event permanentemente")

    event = await _resolver_event_ou_404(pool, event_id)
    if dados.confirmar_slug != event["slug"]:
        raise HTTPException(status_code=400, detail="Slug de confirmação não confere")

    qtd_entries = await event_repo.contar_entries(pool, event_id)
    if qtd_entries > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Event tem {qtd_entries} pontuação(ões) registrada(s) — não pode ser apagado permanentemente",
        )

    ok = await event_repo.deletar_se_sem_entries(pool, event_id)
    if not ok:
        raise HTTPException(
            status_code=409,
            detail="Event passou a ter pontuação entre a checagem e a exclusão — tente de novo",
        )
    log.warning("event_deletado_permanente", event_id=event_id, slug=event["slug"], super_admin=admin.identificador)
    return {"ok": True}


# ── Gestão de games por event ────────────────────────────────

@router.get("/{event_id}/games")
async def listar_games_do_event(
    event_id: str,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """Lista games vinculados ao event (ativos e inativos no vínculo, e
    mesmo desativados globalmente — ver listar_por_event_admin). Leitura:
    liberada pra quem tem qualquer acesso à arena (admin ou moderador),
    não só admin."""
    event = await _resolver_event_ou_404(pool, event_id)
    if not admin.super and not admin.tem_acesso_na_arena(event["arena_id"]):
        raise HTTPException(status_code=403, detail="Sem acesso a este event")
    return await event_game_repo.listar_por_event_admin(pool, event_id)


@router.post("/{event_id}/games/ordenar")
async def ordenar_games_do_event(
    event_id: str,
    dados: OrdenarGamesBody,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """Recalcula a ordem de todos os games do event por um critério
    pré-definido — substitui o reorder manual jogo a jogo
    (docs/CATALOGO_JOGOS_SPEC.md Fase 9). Precisa vir ANTES de
    /{game_id} abaixo: senão "ordenar" seria capturado como game_id."""
    event = await _resolver_event_ou_404(pool, event_id)
    _exigir_admin_na_arena(admin, event["arena_id"], "reordenar os games deste event")

    return await event_game_repo.reordenar_por_criterio(pool, event_id, dados.criterio)


@router.post("/{event_id}/games/{game_id}", status_code=201)
async def adicionar_game_ao_event(
    event_id: str,
    game_id: str,
    ordem: int = 0,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """Adiciona game ao event. Se já existir, reativa."""
    event = await _resolver_event_ou_404(pool, event_id)
    _exigir_admin_na_arena(admin, event["arena_id"], "editar os games deste event")

    try:
        return await event_game_repo.adicionar(pool, event_id, game_id, ordem)
    except Exception as exc:
        if "foreign key" in str(exc).lower():
            raise HTTPException(status_code=404, detail="Evento ou jogo não encontrado")
        raise


@router.patch("/{event_id}/games/{game_id}")
async def atualizar_game_do_event(
    event_id: str,
    game_id: str,
    dados: EventoJogoUpdate,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """Atualiza ativo e/ou ordem de um game num event."""
    event = await _resolver_event_ou_404(pool, event_id)
    _exigir_admin_na_arena(admin, event["arena_id"], "editar os games deste event")

    resultado = await event_game_repo.atualizar(
        pool, event_id, game_id, dados.model_dump(exclude_none=True)
    )
    if not resultado:
        raise HTTPException(status_code=404, detail="Vínculo não encontrado")
    return resultado
