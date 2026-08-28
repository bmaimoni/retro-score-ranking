"""
Router admin de telões — requer autenticação.
Prefixo: /api/admin/teloes

Ver docs/EVENTOS_SPEC.md §3: um telão aponta pra exatamente um event OU
um placar (CHECK teloes_evento_ou_placar no banco). Cada telão escolhe
seus próprios games/ordem via telao_jogos, independente de event_games.

Escopo por arena (docs/PERMISSOES_SPEC.md §4, "games/events/telão,
própria arena, moderador nunca"): telão de event_id usa a arena do
event — direto. Telão de placar_id não tem arena própria no schema;
resolvemos pela arena comum dos events vinculados ao placar
(repositories.placar.resolver_arena_id) quando ela é inequívoca (todo
mundo do mesmo placar customizado pertence à mesma arena — uso real
esperado, ex: Hall da Fama só com events da Canal3). Quando a arena
não é uma só (placar global, placar customizado ainda vazio ou
misturando arenas), só super pode operar — não existe hoje um dono de
arena único pra esses casos.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator
import repositories.telao  as telao_repo
import repositories.event as event_repo
import repositories.placar as placar_repo
from utils.db import get_pool
from middleware.auth import require_admin, AdminContext

router = APIRouter(prefix="/api/admin/teloes", tags=["admin-teloes"])


class TelaoCreate(BaseModel):
    nome: str
    slug: str
    top_n: int = 10
    event_id: str | None = None
    placar_id: str | None = None

    @model_validator(mode="after")
    def event_xor_placar(self):
        if (self.event_id is not None) == (self.placar_id is not None):
            raise ValueError(
                "Informe exatamente um entre event_id e placar_id, nunca os dois nem nenhum"
            )
        return self


class TelaoUpdate(BaseModel):
    nome:  str | None = None
    top_n: int | None = None


class TelaoJogoUpdate(BaseModel):
    ativo: bool | None = None
    ordem: int | None = None


async def _resolver_arena_ou_404(pool, event_id: str | None, placar_id: str | None) -> str | None:
    """Arena 'dona' do futuro telão, checando de quebra que o
    event/placar apontado existe (senão 404 antes de checar permissão
    — evita vazar 403 quando o problema real é 'id inexistente')."""
    if event_id:
        event = await event_repo.buscar_por_id(pool, event_id)
        if not event:
            raise HTTPException(status_code=404, detail="Evento não encontrado")
        return str(event["arena_id"])

    placar = await placar_repo.buscar_por_id(pool, placar_id)
    if not placar:
        raise HTTPException(status_code=404, detail="Placar não encontrado")
    return await placar_repo.resolver_arena_id(pool, placar_id)


async def _arena_do_telao(pool, telao: dict) -> str | None:
    """Mesma resolução acima, mas pra um telão que já existe — event_id
    e placar_id são imutáveis após a criação, então a existência já foi
    garantida pela FK na hora de criar."""
    if telao["event_id"]:
        event = await event_repo.buscar_por_id(pool, str(telao["event_id"]))
        return str(event["arena_id"]) if event else None
    return await placar_repo.resolver_arena_id(pool, str(telao["placar_id"]))


def _exigir_admin_na_arena(admin: AdminContext, arena_id: str | None, acao: str):
    """arena_id=None (placar global, ou customizado sem arena única)
    só é operável por super — não há um único dono de arena pra
    autorizar."""
    if admin.super:
        return
    if arena_id is None or not admin.eh_admin_na_arena(arena_id):
        raise HTTPException(status_code=403, detail=f"Sem permissão para {acao}")


async def _telao_ou_404(pool, telao_id: str) -> dict:
    telao = await telao_repo.buscar_por_id(pool, telao_id)
    if not telao:
        raise HTTPException(status_code=404, detail="Telão não encontrado")
    return telao


# ── CRUD de telões ─────────────────────────────────────────────

@router.get("")
async def listar_teloes(pool=Depends(get_pool), admin: AdminContext = Depends(require_admin)):
    """super vê todos; admin/moderador escopado só os telões cuja
    arena (resolvida via event ou placar) ele tem acesso — telões sem
    arena inequívoca (placar global/misto) ficam de fora da lista."""
    teloes = await telao_repo.listar_todos(pool)
    if admin.super:
        return teloes

    visiveis = []
    for t in teloes:
        arena_id = await _arena_do_telao(pool, t)
        if arena_id is not None and admin.tem_acesso_na_arena(arena_id):
            visiveis.append(t)
    return visiveis


@router.post("", status_code=201)
async def criar_telao(
    dados: TelaoCreate,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """
    Cria um telão. A validação event_id XOR placar_id acontece no schema
    Pydantic (422 antes de chegar no banco); o CHECK teloes_evento_ou_placar
    no banco é a segunda linha de defesa.
    """
    arena_id = await _resolver_arena_ou_404(pool, dados.event_id, dados.placar_id)
    _exigir_admin_na_arena(admin, arena_id, "criar telão")

    try:
        return await telao_repo.criar(
            pool, dados.nome, dados.slug, dados.top_n,
            dados.event_id, dados.placar_id,
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
    admin: AdminContext = Depends(require_admin),
):
    """Atualiza nome e/ou top_n. event_id/placar_id são imutáveis após criação."""
    telao_atual = await _telao_ou_404(pool, telao_id)
    arena_id = await _arena_do_telao(pool, telao_atual)
    _exigir_admin_na_arena(admin, arena_id, "editar este telão")

    telao = await telao_repo.atualizar(pool, telao_id, dados.model_dump(exclude_none=True))
    if not telao:
        raise HTTPException(status_code=404, detail="Telão não encontrado")
    return telao


# ── Gestão de games do telão ───────────────────────────────────

@router.get("/{telao_id}/games")
async def listar_games_do_telao(
    telao_id: str,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """Lista games vinculados ao telão (ativos e inativos). Leitura:
    liberada pra quem tem qualquer acesso à arena (admin ou moderador)."""
    telao = await _telao_ou_404(pool, telao_id)
    arena_id = await _arena_do_telao(pool, telao)
    if not admin.super and (arena_id is None or not admin.tem_acesso_na_arena(arena_id)):
        raise HTTPException(status_code=403, detail="Sem acesso a este telão")
    return await telao_repo.listar_games_do_telao(pool, telao_id)


@router.post("/{telao_id}/games/{game_id}", status_code=201)
async def adicionar_game_ao_telao(
    telao_id: str,
    game_id: str,
    ordem: int = 0,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """Adiciona game ao telão. Se já existir, reativa e atualiza ordem."""
    telao = await _telao_ou_404(pool, telao_id)
    arena_id = await _arena_do_telao(pool, telao)
    _exigir_admin_na_arena(admin, arena_id, "editar os games deste telão")

    try:
        return await telao_repo.adicionar_game(pool, telao_id, game_id, ordem)
    except Exception as exc:
        if "foreign key" in str(exc).lower():
            raise HTTPException(status_code=404, detail="Telão ou game não encontrado")
        raise


@router.patch("/{telao_id}/games/{game_id}")
async def atualizar_game_do_telao(
    telao_id: str,
    game_id: str,
    dados: TelaoJogoUpdate,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """Atualiza ativo e/ou ordem de um game no telão."""
    telao = await _telao_ou_404(pool, telao_id)
    arena_id = await _arena_do_telao(pool, telao)
    _exigir_admin_na_arena(admin, arena_id, "editar os games deste telão")

    resultado = await telao_repo.atualizar_game(
        pool, telao_id, game_id, dados.model_dump(exclude_none=True)
    )
    if not resultado:
        raise HTTPException(status_code=404, detail="Vínculo não encontrado")
    return resultado
