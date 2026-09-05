from datetime import date
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, UUID4, field_validator
from middleware.auth import require_admin, AdminContext
from utils.db import get_pool
from services.sse import broker
import repositories.entry as entry_repo
import repositories.event as event_repo
import repositories.game as game_repo
import repositories.membership as membership_repo
import repositories.event_game as event_game_repo
import repositories.usuario as usuario_repo
import auth.repository as auth_repo
import auth.service as auth_svc
import services.exclusao_conta as exclusao_svc
import services.arena_admissao as arena_admissao
import services.game_admissao as game_admissao
import services.igdb as igdb
import structlog

log = structlog.get_logger()

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ── SCHEMAS ───────────────────────────────────────────────────────────────────

class AtualizarVisibilidade(BaseModel):
    no_ranking: bool

class ResolverPendente(BaseModel):
    aprovar: bool

class CriarJogo(BaseModel):
    nome: str
    slug: str
    score_max: int | None = None
    plataforma: str | None = None
    ano_lancamento: int | None = None
    capa_url: str | None = None
    gameplay_url: str | None = None
    # Fase 9 + CATALOGO_JOGOS_SPEC.md Fase 1/5 — preenchido quando o
    # jogo vem da busca IGDB: pula pendente_aprovacao (5.4) e ancora
    # dedup estrutural (5.1). event_id: vincula só a este event, não a
    # todos os events do admin (correção do achado 5.9 — comportamento
    # antigo vinculava a todos, ver criar_game abaixo).
    igdb_id: int | None = None
    event_id: str | None = None
    # CATALOGO_JOGOS_SPEC.md Fase 7 — só preenchidos no caminho IGDB
    # (7.4); o frontend nunca envia isso no cadastro manual.
    generos: list[str] | None = None
    geracoes: list[int] | None = None

    @field_validator("ano_lancamento")
    @classmethod
    def _valida_ano(cls, v):
        if v is not None and v <= 1950:
            raise ValueError("ano_lancamento deve ser posterior a 1950")
        return v

class AtualizarJogo(BaseModel):
    ativo: bool | None = None
    score_max: int | None = None
    plataforma: str | None = None
    ano_lancamento: int | None = None
    capa_url: str | None = None
    gameplay_url: str | None = None
    # docs/CATALOGO_JOGOS_SPEC.md Fase 6 — antes só dava pra corrigir um
    # typo de nome recriando o game certo e mesclando o errado nele
    # (perde o slug original). Reaproveita a colisão de 5.6 no router,
    # excluindo o próprio game (6.2); slug depende só da UNIQUE do banco (6.3).
    nome: str | None = None
    slug: str | None = None

    @field_validator("ano_lancamento")
    @classmethod
    def _valida_ano(cls, v):
        if v is not None and v <= 1950:
            raise ValueError("ano_lancamento deve ser posterior a 1950")
        return v

class ForcarTrocaNick(BaseModel):
    novo_nick: str


async def _resolver_event_ids_admin(
    pool, admin: AdminContext, event_id: str | None,
) -> list[str] | None:
    """
    Resolve a lista de event_ids pra filtrar o feed (pendentes é só
    mais um status dentro dele, não uma rota separada — ver /feed),
    conforme o escopo do admin (docs/MARCAS_SPEC.md §6, "efeito
    colateral necessário"):
      - super-admin: event_id é opcional. Informado → filtra só nele;
        ausente → vê tudo (comportamento de sempre, sem quebra pra quem
        já usa o token ADMIN_SECRET hoje).
      - admin escopado (arena/event, via sessão): event_id é
        OBRIGATÓRIO (400 se ausente) e precisa estar dentro do escopo
        dele (403 se não estiver — nunca vaza dado de fora do escopo).
    """
    if admin.super:
        return [event_id] if event_id else None

    if not event_id:
        raise HTTPException(
            status_code=400,
            detail="event_id é obrigatório para administradores não-super",
        )

    tem_acesso = await membership_repo.tem_acesso_event(pool, admin.user_id, event_id)
    if not tem_acesso:
        raise HTTPException(status_code=403, detail="Sem acesso a este event")

    return [event_id]


# ── FEED ──────────────────────────────────────────────────────────────────────

@router.get("/feed")
async def feed_entries(
    response: Response,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    event_id: str | None = Query(default=None),
    status: Literal["todos", "visiveis", "ocultos", "pendentes"] | None = Query(default=None),
    data_de: date | None = Query(default=None),
    data_ate: date | None = Query(default=None),
    game_id: str | None = Query(default=None),
    sem_foto: bool = Query(default=False),
    sem_identificacao: bool = Query(default=False),
    busca: str | None = Query(default=None),
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """
    Feed de todas as entries recentes, incluindo ocultas e pendentes.
    Total de registros disponível no header X-Total-Count, para o
    frontend montar controles de paginação real (ver docs/EVENTOS_SPEC.md §5).

    event_id: opcional para super-admin (ausente = vê tudo, como
    sempre); obrigatório para admin escopado por arena/event — ver
    docs/MARCAS_SPEC.md §6.

    Filtros combináveis (docs/BACKLOG_2026.md §4.1): status (visibilidade),
    data_de/data_ate, game_id, sem_foto, sem_identificacao — mais busca
    (item 4.4) sobre nick/game/event. Todos opcionais, aplicáveis juntos.
    """
    event_ids = await _resolver_event_ids_admin(pool, admin, event_id)
    filtros = dict(
        event_ids=event_ids, status=status, data_de=data_de, data_ate=data_ate,
        game_id=game_id, sem_foto=sem_foto, sem_identificacao=sem_identificacao, busca=busca,
    )
    total = await entry_repo.contar_feed_admin(pool, **filtros)
    response.headers["X-Total-Count"] = str(total)
    return await entry_repo.listar_feed_admin(pool, limit=limit, offset=offset, **filtros)


# ── IDENTIDADE DO ADMIN LOGADO ─────────────────────────────────────────────────

@router.get("/me")
async def quem_sou_eu(pool=Depends(get_pool), admin: AdminContext = Depends(require_admin)):
    """
    Identidade e escopo do admin autenticado nesta requisição — usado
    pelo frontend logo após o login pra saber se é super-admin (vê
    tudo, sem seletor de event) ou admin escopado (precisa escolher
    entre os events que ele tem acesso). Cada event em `events` já
    carrega `role` (admin/moderador); `vinculos` traz o mesmo nível por
    arena_id direto (cobre arena sem event nenhum ainda, que não
    apareceria em `events`) — o frontend usa isso pra esconder ações
    que o nível atual não permite (docs/PERMISSOES_SPEC.md §7 item 5).
    """
    if admin.super:
        return {"identificador": admin.identificador, "super": True, "events": [], "vinculos": []}

    events = await membership_repo.listar_events_acessiveis_detalhado(pool, admin.user_id)
    return {
        "identificador": admin.identificador, "super": False,
        "events": events, "vinculos": admin.vinculos,
    }


# ── MODERAÇÃO DE ENTRIES ─────────────────────────────────────────────────────

async def _resolver_entry_com_acesso_ou_erro(pool, admin: AdminContext, entry_id: str) -> dict:
    """
    Busca a entry e garante que o moderador tem vínculo na arena do
    evento dela antes de deixar mutar (docs/MODERADOR_SPEC.md M.1) —
    achado: os dois endpoints de moderação não checavam nada além de
    autenticação, deixando qualquer moderador de qualquer arena ocultar/
    reativar/aprovar entry de arena alheia. Entry sem event_id (dado
    legado pré multi-evento) só é acessível a super, por não haver arena
    nenhuma pra checar.
    """
    entry = await entry_repo.buscar_por_id(pool, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entrada não encontrada")
    if admin.super:
        return entry
    if not entry.get("event_id"):
        raise HTTPException(status_code=403, detail="Sem permissão para moderar esta entrada")
    event = await event_repo.buscar_por_id(pool, str(entry["event_id"]))
    if not event or not admin.tem_acesso_na_arena(event["arena_id"]):
        raise HTTPException(status_code=403, detail="Sem permissão para moderar esta entrada")
    return entry


@router.patch("/entries/{entry_id}")
async def moderar_entry(
    entry_id: UUID4,
    body: AtualizarVisibilidade,
    pool=Depends(get_pool),
    moderador: AdminContext = Depends(require_admin),
):
    """
    Oculta (no_ranking=false) ou reativa (no_ranking=true) uma entry.
    A foto nunca é deletada — evidência sempre preservada.
    Emite event SSE para os clientes do ranking.
    """
    await _resolver_entry_com_acesso_ou_erro(pool, moderador, str(entry_id))
    entry = await entry_repo.atualizar_visibilidade(
        pool, str(entry_id), body.no_ranking, moderador.identificador
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Entrada não encontrada")

    # Busca o slug para o SSE
    row = await pool.fetchrow("SELECT slug FROM games WHERE id = $1", entry["game_id"])
    slug = row["slug"] if row else str(entry["game_id"])

    if body.no_ranking:
        await broker.publish(slug, "reativar", {
            "id": str(entry_id),
            "entry": {
                "id":        str(entry["id"]),
                "nick":      entry["nick"],
                "pontuacao": entry["pontuacao"],
                "foto_url":  entry["foto_url"],
            }
        })
    else:
        await broker.publish(slug, "ocultar", {"id": str(entry_id)})

    log.info(
        "moderacao",
        entry_id=str(entry_id),
        no_ranking=body.no_ranking,
        moderador=moderador.identificador,
    )

    return entry


@router.patch("/entries/{entry_id}/pendente")
async def resolver_pendente(
    entry_id: UUID4,
    body: ResolverPendente,
    pool=Depends(get_pool),
    moderador: AdminContext = Depends(require_admin),
):
    """
    Resolve uma entry pendente:
    - aprovar=true  → pendente=false, no_ranking=true  (aparece no ranking)
    - aprovar=false → pendente=false, no_ranking=false (fica oculta)
    """
    await _resolver_entry_com_acesso_ou_erro(pool, moderador, str(entry_id))
    entry = await entry_repo.resolver_pendente(
        pool, str(entry_id), body.aprovar, moderador.identificador
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Entrada não encontrada")

    if body.aprovar:
        row = await pool.fetchrow("SELECT slug FROM games WHERE id = $1", entry["game_id"])
        slug = row["slug"] if row else str(entry["game_id"])
        await broker.publish(slug, "novo_registro", {
            "id":        str(entry["id"]),
            "nick":      entry["nick"],
            "pontuacao": entry["pontuacao"],
            "foto_url":  entry["foto_url"],
            "criado_em": str(entry["criado_em"]),
        })

    log.info(
        "pendente_resolvido",
        entry_id=str(entry_id),
        aprovado=body.aprovar,
        moderador=moderador.identificador,
    )

    return entry


@router.patch("/entries/{entry_id}/arquivar")
async def arquivar_entry(
    entry_id: UUID4,
    pool=Depends(get_pool),
    moderador: AdminContext = Depends(require_admin),
):
    """
    Arquivamento manual individual (docs/MODERADOR_SPEC.md M.5,
    NICKNAME_SPEC.md decisão #15) — some do ranking público
    permanentemente (reversível só via restaurar-ranking em massa, ação
    de super), independente de estar pendente/visível/oculta. Mesmo
    escopo por arena de moderar_entry/resolver_pendente.
    """
    await _resolver_entry_com_acesso_ou_erro(pool, moderador, str(entry_id))
    entry = await entry_repo.arquivar(pool, str(entry_id), moderador.identificador)
    if not entry:
        raise HTTPException(status_code=404, detail="Entrada não encontrada ou já arquivada")

    log.info("entry_arquivada", entry_id=str(entry_id), moderador=moderador.identificador)
    return entry


# ── GESTÃO DE GAMES ───────────────────────────────────────────────────────────

RATE_LIMIT_GAMES_MANUAL_POR_DIA = 5


@router.get("/games/buscar-igdb")
async def buscar_game_igdb(
    q: str = Query(..., min_length=2),
    admin: AdminContext = Depends(require_admin),
):
    """
    Busca jogo na IGDB pro Passo 1 do wizard (Fase 9 do
    PLANO_IMPLEMENTACAO_2026.md, fundida com a Fase 1 do
    docs/CATALOGO_JOGOS_SPEC.md). Créditos obrigatórios no frontend que
    consome este endpoint: "Dados de jogos fornecidos por IGDB.com"
    (5.7) — não é opcional.

    503 quando a IGDB não está configurada ou está indisponível — o
    frontend cai pro cadastro manual sem quebrar a tela.
    """
    try:
        return await igdb.buscar(q)
    except (igdb.IGDBNaoConfigurado, igdb.IGDBIndisponivel):
        raise HTTPException(
            status_code=503,
            detail="Busca por jogo temporariamente indisponível — cadastre manualmente",
        )


@router.post("/games", status_code=201)
async def criar_game(
    body: CriarJogo,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """
    Cria um novo game. Moderador nunca cria game — decisão #1 do
    docs/PERMISSOES_SPEC.md (a primeira versão do backlog dizia o
    contrário; corrigido).

    Dois caminhos (Fase 9 + CATALOGO_JOGOS_SPEC.md Fase 5), decididos
    por `igdb_id` vir preenchido ou não:

    - Via IGDB (igdb_id presente): dedup estrutural — se já existe um
      game com esse igdb_id (alguém já importou antes), reaproveita em
      vez de duplicar. Pula pendente_aprovacao inteiramente (5.4),
      mesmo se quem criou não for super — a fonte externa já valida a
      entrada, não precisa de fila de revisão humana.
    - Manual (sem igdb_id): comportamento de sempre — admin não-super
      nasce pendente_aprovacao=true (migration 018), MAS agora com
      rate limit (5/dia — 5.5) e colisão de nome (5.6) primeiro, já
      que é o único caminho sem dedup estrutural.

    Vínculo a event: só se `event_id` vier explícito no body — vincula
    só a esse event. Correção do achado 5.9: a versão anterior
    vinculava automaticamente a TODOS os events que o admin tinha
    acesso, poluindo events sem relação nenhuma com o game criado
    (visível em escala self-serve, com uma pessoa dona de várias
    arenas). Sem `event_id`, não vincula a nada — quem quiser vincular
    depois usa POST /api/admin/events/{id}/games/{game_id}, que já
    existe.
    """
    if not admin.super and not any(v["role"] == "admin" for v in admin.vinculos):
        raise HTTPException(
            status_code=403,
            detail="Moderador não pode criar games — só admin ou super-admin",
        )

    if body.igdb_id is not None:
        game = await game_repo.buscar_por_igdb_id(pool, body.igdb_id)
        if not game:
            try:
                game = await game_repo.criar(
                    pool, body.nome, body.slug, body.score_max,
                    pendente_aprovacao=False,
                    criado_por=admin.identificador,
                    plataforma=body.plataforma,
                    ano_lancamento=body.ano_lancamento,
                    capa_url=body.capa_url,
                    gameplay_url=body.gameplay_url,
                    igdb_id=body.igdb_id,
                    generos=body.generos,
                    geracoes=body.geracoes,
                )
            except Exception as exc:
                if "unique" in str(exc).lower():
                    raise HTTPException(status_code=409, detail=f"Slug '{body.slug}' já existe")
                raise HTTPException(status_code=500, detail="Erro ao criar game")
    else:
        criadas_24h = await game_repo.contar_manuais_por_criador_ultimas_24h(pool, admin.identificador)
        if criadas_24h >= RATE_LIMIT_GAMES_MANUAL_POR_DIA:
            raise HTTPException(
                status_code=429,
                detail=f"Limite de {RATE_LIMIT_GAMES_MANUAL_POR_DIA} jogos cadastrados manualmente "
                       f"por dia atingido — tente novamente amanhã, ou busque na IGDB.",
            )

        existentes = await game_repo.listar_nome_ativos(pool)
        resultado = game_admissao.avaliar_colisao(body.nome, existentes)
        if resultado.bloqueado:
            raise HTTPException(status_code=409, detail=resultado.motivo)

        try:
            capa_url = arena_admissao.sanitizar_logo_url(body.capa_url)
        except ValueError:
            raise HTTPException(status_code=422, detail="capa_url inválida")

        try:
            game = await game_repo.criar(
                pool, body.nome, body.slug, body.score_max,
                pendente_aprovacao=not admin.super,
                criado_por=admin.identificador,
                plataforma=body.plataforma,
                ano_lancamento=body.ano_lancamento,
                capa_url=capa_url,
                gameplay_url=body.gameplay_url,
            )
        except Exception as exc:
            if "unique" in str(exc).lower():
                raise HTTPException(status_code=409, detail=f"Slug '{body.slug}' já existe")
            raise HTTPException(status_code=500, detail="Erro ao criar game")

    if body.event_id:
        # docs/ARENA_ADMIN_SPEC.md AA.3 — achado: vinculava sem checar
        # se o event_id recebido pertence a uma arena onde o admin tem
        # vínculo, deixando vincular jogo a event de arena alheia.
        if not admin.super:
            event = await event_repo.buscar_por_id(pool, body.event_id)
            if not event or not admin.tem_acesso_na_arena(event["arena_id"]):
                raise HTTPException(status_code=403, detail="Sem permissão para vincular a este event")
        await event_game_repo.adicionar(pool, body.event_id, str(game["id"]))

    return game


def _exigir_super_editar_game(admin: AdminContext):
    """docs/ARENA_ADMIN_SPEC.md AA.2 — revisão de PERMISSOES_SPEC.md §4:
    'games' é catálogo global compartilhado entre arenas desde a
    integração IGDB (CATALOGO_JOGOS_SPEC.md Fase 5), não mais 'o jogo da
    minha marca'. Editar o registro global (nome/capa/plataforma/
    score_max/ativo) afeta toda arena que usa aquele jogo — vira
    exclusivo de super. O que admin de arena continua controlando de
    verdade é o vínculo (event_games.ativo/ordem, já escopado em
    events.py). Achado anterior (só bloqueava moderador, não escopava
    por arena) fica substituído por esta regra mais simples e correta."""
    if not admin.super:
        raise HTTPException(
            status_code=403,
            detail="Só super-admin edita o catálogo global de games — "
                   "para ativar/desativar no seu event, use o vínculo do event",
        )


@router.patch("/games/{game_id}")
async def atualizar_game(
    game_id: UUID4,
    body: AtualizarJogo,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """Ativa/desativa um game ou atualiza seu score_max/metadado (inclusive
    nome/slug, Fase 6) no catálogo global — exclusivo de super
    (docs/ARENA_ADMIN_SPEC.md AA.2)."""
    _exigir_super_editar_game(admin)

    if body.nome is not None:
        existentes = [
            e for e in await game_repo.listar_nome_ativos(pool)
            if str(e["id"]) != str(game_id)
        ]
        resultado = game_admissao.avaliar_colisao(body.nome, existentes)
        if resultado.bloqueado:
            raise HTTPException(status_code=409, detail=resultado.motivo)

    try:
        game = await game_repo.atualizar(
            pool, str(game_id), body.ativo, body.score_max,
            plataforma=body.plataforma, ano_lancamento=body.ano_lancamento,
            capa_url=body.capa_url, gameplay_url=body.gameplay_url,
            nome=body.nome, slug=body.slug,
        )
    except Exception as exc:
        if "unique" in str(exc).lower():
            raise HTTPException(status_code=409, detail=f"Slug '{body.slug}' já existe")
        raise HTTPException(status_code=500, detail="Erro ao atualizar game")

    if not game:
        raise HTTPException(status_code=404, detail="Jogo não encontrado ou nada para atualizar")
    return game


class ResyncIgdb(BaseModel):
    # Preenchido pelo frontend só depois que o super confirma qual jogo
    # da IGDB corresponde a um game manual (8.5.3) — ausente na primeira
    # chamada, que devolve candidatos em vez de aplicar.
    igdb_id: int | None = None


@router.post("/games/{game_id}/resync-igdb")
async def resync_game_igdb(
    game_id: UUID4,
    body: ResyncIgdb,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """
    Atualiza um game a partir da IGDB (docs/CATALOGO_JOGOS_SPEC.md 8.5)
    — mesmo gate de edição do catálogo global (Fase 6). Dois casos:

    - Game já ancorado (`igdb_id` preenchido) ou `body.igdb_id`
      informado: busca por ID exato e sobrescreve todos os campos de
      origem IGDB (8.5.2), nunca nome/slug.
    - Game manual sem `igdb_id` nem `body.igdb_id`: sem ID pra buscar
      direto, então busca por nome e devolve candidatos pro super
      escolher (8.5.3) — não aplica nada ainda, é uma segunda chamada
      (com `body.igdb_id` do candidato escolhido) que de fato atualiza.
    """
    _exigir_super_editar_game(admin)

    game = await game_repo.buscar_por_id(pool, str(game_id))
    if not game:
        raise HTTPException(status_code=404, detail="Jogo não encontrado")

    alvo_igdb_id = body.igdb_id or game["igdb_id"]

    if not alvo_igdb_id:
        try:
            candidatos = await igdb.buscar(game["nome"], limite=5)
        except (igdb.IGDBNaoConfigurado, igdb.IGDBIndisponivel):
            raise HTTPException(
                status_code=503,
                detail="Busca por jogo temporariamente indisponível — tente de novo em instantes",
            )
        return {"candidatos": candidatos}

    # Um game manual sendo ancorado agora (não tinha igdb_id) não pode
    # roubar o igdb_id de outro game já existente no catálogo — mesma
    # dedup estrutural da criação (5.1), aplicada aqui pra não deixar
    # dois registros disputando a mesma fonte externa.
    if not game["igdb_id"]:
        conflito = await game_repo.buscar_por_igdb_id(pool, alvo_igdb_id)
        if conflito and str(conflito["id"]) != str(game_id):
            raise HTTPException(
                status_code=409,
                detail=f"Esse jogo da IGDB já está vinculado a '{conflito['nome']}' no catálogo",
            )

    try:
        detalhe = await igdb.buscar_por_id(alvo_igdb_id)
    except (igdb.IGDBNaoConfigurado, igdb.IGDBIndisponivel):
        raise HTTPException(
            status_code=503,
            detail="Busca por jogo temporariamente indisponível — tente de novo em instantes",
        )
    if not detalhe:
        raise HTTPException(
            status_code=404,
            detail="Jogo não encontrado na IGDB — pode ter sido removido/mesclado lá",
        )

    return await game_repo.atualizar_de_igdb(pool, str(game_id), detalhe)


@router.get("/games-todos")
async def listar_games_todos(
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """Lista todos os games incluindo inativos — para o painel admin.
    Pendentes de aprovação só aparecem pra super (docs/SUPER_SPEC.md
    S.2) — não-super não tem por que ver o que outras arenas estão
    tentando cadastrar antes da revisão, nem o próprio pendente."""
    games = await game_repo.listar_todos(pool)
    if not admin.super:
        games = [g for g in games if not g["pendente_aprovacao"]]
    return games


def _exigir_super_games(admin: AdminContext):
    if not admin.super:
        raise HTTPException(
            status_code=403,
            detail="Só super-admin pode revisar games pendentes de aprovação",
        )


@router.get("/games/pendentes")
async def listar_games_pendentes(
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """Games criados por admin não-super, aguardando aprovação pro
    catálogo geral — só super-admin revisa (ver migration 018)."""
    _exigir_super_games(admin)
    return await game_repo.listar_pendentes_aprovacao(pool)


@router.patch("/games/{game_id}/aprovar")
async def aprovar_game(
    game_id: UUID4,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """Aprova um game pendente pro catálogo geral — as entries já
    enviadas entram retroativamente, sem precisar tocar nelas."""
    _exigir_super_games(admin)
    game = await game_repo.aprovar(pool, str(game_id))
    if not game:
        raise HTTPException(status_code=404, detail="Jogo não encontrado ou já não está pendente")
    return game


class MesclarJogo(BaseModel):
    game_destino_id: UUID4


@router.post("/games/{game_id}/mesclar")
async def mesclar_game(
    game_id: UUID4,
    body: MesclarJogo,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """
    Mescla game_id (origem, geralmente um pendente identificado como
    duplicata) em game_destino_id (o game já existente de verdade).
    Migra entries e vínculos de event, arquiva a origem mantendo o
    rastro — nunca apaga nada.
    """
    _exigir_super_games(admin)

    if str(game_id) == str(body.game_destino_id):
        raise HTTPException(status_code=422, detail="game_destino_id não pode ser igual ao game de origem")

    origem_existe = await pool.fetchval("SELECT 1 FROM games WHERE id = $1", str(game_id))
    destino_existe = await pool.fetchval("SELECT 1 FROM games WHERE id = $1", str(body.game_destino_id))
    if not origem_existe or not destino_existe:
        raise HTTPException(status_code=404, detail="Jogo de origem ou destino não encontrado")

    async with pool.acquire() as conn:
        async with conn.transaction():
            resultado = await game_repo.mesclar(conn, str(game_id), str(body.game_destino_id))

    log.info("game_mesclado", origem=str(game_id), destino=str(body.game_destino_id), admin=admin.identificador)
    return resultado


# ── CONFIGURAÇÃO DO EVENT ────────────────────────────────────────────────────

import repositories.event_config as config_repo

class AtualizarConfig(BaseModel):
    valor: str

def _exigir_super_config(admin: AdminContext):
    """event_config é tabela legada singleton (pré multi-evento, sem
    event_id) — guarda kill-switch de upload, rate limit anti-abuso e
    texto de consentimento LGPD da plataforma inteira. Sem escopo por
    arena possível sem redesenho do modelo, é exclusiva de super
    (docs/MODERADOR_SPEC.md M.2 — achado: não tinha checagem nenhuma,
    nem de super, e a tela carregava isso automaticamente pra qualquer
    admin/moderador logado)."""
    if not admin.super:
        raise HTTPException(
            status_code=403,
            detail="Só super-admin pode ver ou alterar configurações da plataforma",
        )


@router.get("/config")
async def listar_config(
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """Lista todas as configurações do event."""
    _exigir_super_config(admin)
    return await config_repo.listar(pool)


@router.patch("/config/{chave}")
async def atualizar_config(
    chave: str,
    body: AtualizarConfig,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """Atualiza uma configuração pelo nome da chave."""
    _exigir_super_config(admin)
    cfg = await config_repo.atualizar(pool, chave, body.valor)
    if not cfg:
        raise HTTPException(status_code=404, detail=f"Configuração '{chave}' não encontrada")
    return cfg


# ── MANUTENÇÃO DE RANKINGS ────────────────────────────────────────────────────

class LimparRankingBody(BaseModel):
    game_id: str | None = None        # None = todos os games
    permanente: bool = False           # False = soft delete, True = DELETE físico
    confirmar: str = ""               # deve ser "CONFIRMAR" para prosseguir


def _exigir_super_manutencao(admin: AdminContext):
    """Limpar/restaurar ranking não tem filtro de arena/event no corpo
    da requisição — afeta um game (ou TODOS os games, de TODAS as
    arenas) de uma vez. Sem um redesenho que escope por arena, é
    ação exclusiva de super-admin (achado incidental, não coberto pela
    tabela de decisões do docs/PERMISSOES_SPEC.md — 'manutenção' não é
    'moderar feed')."""
    if not admin.super:
        raise HTTPException(
            status_code=403,
            detail="Só super-admin pode limpar ou restaurar ranking — afeta todas as arenas de uma vez",
        )


@router.post("/manutencao/limpar-ranking")
async def limpar_ranking(
    body: LimparRankingBody,
    pool=Depends(get_pool),
    moderador: AdminContext = Depends(require_admin),
):
    """
    Limpa entries de um game ou de todos os games.
    - permanente=False → soft delete (arquivado=true), reversível
    - permanente=True  → DELETE físico, irreversível
    Exige confirmar="CONFIRMAR" para prosseguir.
    """
    _exigir_super_manutencao(moderador)
    if body.confirmar != "CONFIRMAR":
        raise HTTPException(status_code=400, detail="Envie confirmar='CONFIRMAR' para prosseguir")

    if body.permanente:
        if body.game_id:
            count = await pool.fetchval(
                "SELECT COUNT(*) FROM entries WHERE game_id = $1", body.game_id
            )
            await pool.execute("DELETE FROM entries WHERE game_id = $1", body.game_id)
        else:
            count = await pool.fetchval("SELECT COUNT(*) FROM entries")
            await pool.execute("DELETE FROM entries")
        log.warning("ranking_limpo_permanente", game_id=body.game_id, total=count, moderador=moderador.identificador)
    else:
        if body.game_id:
            count = await pool.fetchval(
                "SELECT COUNT(*) FROM entries WHERE game_id = $1 AND arquivado = false",
                body.game_id
            )
            await pool.execute(
                """UPDATE entries SET arquivado = true, arquivado_em = now(), arquivado_por = $1
                   WHERE game_id = $2 AND arquivado = false""",
                moderador.identificador, body.game_id
            )
        else:
            count = await pool.fetchval(
                "SELECT COUNT(*) FROM entries WHERE arquivado = false"
            )
            await pool.execute(
                """UPDATE entries SET arquivado = true, arquivado_em = now(), arquivado_por = $1
                   WHERE arquivado = false""",
                moderador.identificador
            )
        log.warning("ranking_arquivado", game_id=body.game_id, total=count, moderador=moderador.identificador)

    return {"ok": True, "total_afetadas": count, "permanente": body.permanente}


@router.post("/manutencao/restaurar-ranking")
async def restaurar_ranking(
    body: LimparRankingBody,
    pool=Depends(get_pool),
    moderador: AdminContext = Depends(require_admin),
):
    """Restaura entries arquivadas de um game ou de todos."""
    _exigir_super_manutencao(moderador)
    if body.confirmar != "CONFIRMAR":
        raise HTTPException(status_code=400, detail="Envie confirmar='CONFIRMAR' para prosseguir")

    if body.game_id:
        count = await pool.fetchval(
            "SELECT COUNT(*) FROM entries WHERE game_id = $1 AND arquivado = true",
            body.game_id
        )
        await pool.execute(
            "UPDATE entries SET arquivado = false, arquivado_em = null, arquivado_por = null WHERE game_id = $1 AND arquivado = true",
            body.game_id
        )
    else:
        count = await pool.fetchval("SELECT COUNT(*) FROM entries WHERE arquivado = true")
        await pool.execute(
            "UPDATE entries SET arquivado = false, arquivado_em = null, arquivado_por = null WHERE arquivado = true"
        )

    log.info("ranking_restaurado", game_id=body.game_id, total=count, moderador=moderador.identificador)
    return {"ok": True, "total_restauradas": count}


# ── MODERAÇÃO DE NICK (NICKNAME_SPEC.md decisões #4/#9/#10) ────────────────────

async def _exigir_acesso_ao_usuario(pool, admin: AdminContext, user_id: str) -> None:
    """docs/SUPER_SPEC.md S.1 — moderação de nick age sobre identidade
    global do jogador, mas só faz sentido escopada: admin/moderador só
    pode agir sobre quem já tem ao menos 1 entry numa arena onde ele
    tem vínculo, mesmo padrão do M.1 pra entries. Super irrestrito."""
    if admin.super:
        return
    for vinculo in admin.vinculos:
        if await entry_repo.usuario_tem_entry_na_arena(pool, user_id, vinculo["arena_id"]):
            return
    raise HTTPException(status_code=403, detail="Sem permissão para moderar nick deste usuário")


@router.get("/usuarios/{user_id}/nicks")
async def historico_nicks(
    user_id: str,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """Histórico de nicks do usuário — decisão #4: painel de moderação
    mostra o histórico completo, não só o nick da entry isolada
    sendo revisada."""
    await _exigir_acesso_ao_usuario(pool, admin, user_id)
    return await auth_repo.listar_historico_nicks(pool, user_id)


@router.post("/usuarios/{user_id}/trocar-nick")
async def forcar_troca_nick(
    user_id: str,
    body: ForcarTrocaNick,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """
    Admin/moderador troca o nick de qualquer jogador, sem respeitar o
    cooldown de 30 dias — uso previsto: nick ofensivo/impróprio,
    especialmente relevante por exibição pública em telão (decisão #9).
    Toda troca forçada fica auditada (decisão #10) — nome antigo, nome
    novo, quem forçou, quando.
    """
    await _exigir_acesso_ao_usuario(pool, admin, user_id)
    claim_atual = await auth_repo.buscar_claim_ativo_do_usuario(pool, user_id)

    try:
        nova_claim = await auth_svc.trocar_nick(pool, user_id, body.novo_nick, ignorar_cooldown=True)
    except auth_svc.NickJaReivindicadoError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    if claim_atual and nova_claim["id"] == claim_atual["id"]:
        return nova_claim  # no-op — já era esse nick, nada a auditar

    await auth_repo.registrar_troca_forcada(
        pool, user_id=user_id,
        nick_anterior=claim_atual["nick"] if claim_atual else None,
        nick_novo=body.novo_nick, realizado_por=admin.identificador,
    )

    log.info(
        "nick_trocado_forcado", user_id=user_id,
        nick_anterior=claim_atual["nick"] if claim_atual else None,
        nick_novo=body.novo_nick, admin=admin.identificador,
    )

    return nova_claim


# ── EXCLUSÃO DE CONTA (docs/EXCLUSAO_CONTA_SPEC.md) ─────────────────────────────

def _exigir_super_exclusao(admin: AdminContext):
    """Exclusão de conta é LGPD-sensível e atravessa a plataforma
    inteira (usuário não é escopado por arena) — exclusivo de super,
    mesma régua de manutenção de ranking."""
    if not admin.super:
        raise HTTPException(status_code=403, detail="Só super-admin gerencia exclusão de conta")


@router.get("/exclusoes-pendentes")
async def listar_exclusoes_pendentes(
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """
    Solicitações de exclusão em aberto — sem job agendado (ver
    docs/EXCLUSAO_CONTA_SPEC.md §7), processar é ação manual do super
    a partir desta lista. `elegivel=true` = já passou dos 30 dias de
    janela de cancelamento.
    """
    _exigir_super_exclusao(admin)
    return await usuario_repo.listar_exclusoes_pendentes(pool)


@router.post("/usuarios/{user_id}/processar-exclusao")
async def processar_exclusao(
    user_id: str,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """
    Dispara a anonimização de verdade — bloqueado se ainda dentro da
    janela de 30 dias, ou se a pessoa virou owner_user_id de alguma
    arena depois de solicitar (checagem repetida aqui, não só na
    solicitação).
    """
    _exigir_super_exclusao(admin)
    try:
        resultado = await exclusao_svc.processar(pool, user_id)
    except exclusao_svc.ExclusaoBloqueadaTitularidadeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except exclusao_svc.ExclusaoNaoElegivelError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except exclusao_svc.ExclusaoJanelaAbertaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    log.warning("conta_anonimizada", user_id=user_id, admin=admin.identificador)
    return resultado