from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, UUID4
from middleware.auth import require_admin, AdminContext
from utils.db import get_pool
from services.sse import broker
import repositories.entrada as entrada_repo
import repositories.jogo as jogo_repo
import repositories.admin_vinculo as admin_vinculo_repo
import repositories.evento_jogo as evento_jogo_repo
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

class AtualizarJogo(BaseModel):
    ativo: bool | None = None
    score_max: int | None = None


async def _resolver_evento_ids_admin(
    pool, admin: AdminContext, evento_id: str | None,
) -> list[str] | None:
    """
    Resolve a lista de evento_ids pra filtrar feed/pendentes, conforme o
    escopo do admin (docs/MARCAS_SPEC.md §6, "efeito colateral necessário"):
      - super-admin: evento_id é opcional. Informado → filtra só nele;
        ausente → vê tudo (comportamento de sempre, sem quebra pra quem
        já usa o token ADMIN_SECRET hoje).
      - admin escopado (marca/evento, via sessão): evento_id é
        OBRIGATÓRIO (400 se ausente) e precisa estar dentro do escopo
        dele (403 se não estiver — nunca vaza dado de fora do escopo).
    """
    if admin.super:
        return [evento_id] if evento_id else None

    if not evento_id:
        raise HTTPException(
            status_code=400,
            detail="evento_id é obrigatório para administradores não-super",
        )

    tem_acesso = await admin_vinculo_repo.tem_acesso_evento(pool, admin.user_id, evento_id)
    if not tem_acesso:
        raise HTTPException(status_code=403, detail="Sem acesso a este evento")

    return [evento_id]


# ── FEED ──────────────────────────────────────────────────────────────────────

@router.get("/feed")
async def feed_entradas(
    response: Response,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    evento_id: str | None = Query(default=None),
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """
    Feed de todas as entradas recentes, incluindo ocultas e pendentes.
    Total de registros disponível no header X-Total-Count, para o
    frontend montar controles de paginação real (ver docs/EVENTOS_SPEC.md §5).

    evento_id: opcional para super-admin (ausente = vê tudo, como
    sempre); obrigatório para admin escopado por marca/evento — ver
    docs/MARCAS_SPEC.md §6.
    """
    evento_ids = await _resolver_evento_ids_admin(pool, admin, evento_id)
    total = await entrada_repo.contar_feed_admin(pool, evento_ids=evento_ids)
    response.headers["X-Total-Count"] = str(total)
    return await entrada_repo.listar_feed_admin(pool, limit=limit, offset=offset, evento_ids=evento_ids)


@router.get("/pendentes")
async def listar_pendentes(
    response: Response,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    evento_id: str | None = Query(default=None),
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """
    Entradas aguardando decisão do moderador (vieram pelo rate limit).
    Total de registros disponível no header X-Total-Count.

    evento_id: mesma regra de /feed (opcional pra super-admin,
    obrigatório e checado por escopo pra admin restrito).
    """
    evento_ids = await _resolver_evento_ids_admin(pool, admin, evento_id)
    total = await entrada_repo.contar_pendentes(pool, evento_ids=evento_ids)
    response.headers["X-Total-Count"] = str(total)
    return await entrada_repo.listar_pendentes(pool, limit=limit, offset=offset, evento_ids=evento_ids)


# ── IDENTIDADE DO ADMIN LOGADO ─────────────────────────────────────────────────

@router.get("/me")
async def quem_sou_eu(pool=Depends(get_pool), admin: AdminContext = Depends(require_admin)):
    """
    Identidade e escopo do admin autenticado nesta requisição — usado
    pelo frontend logo após o login pra saber se é super-admin (vê
    tudo, sem seletor de evento) ou admin escopado (precisa escolher
    entre os eventos que ele tem acesso). Cada evento em `eventos` já
    carrega `nivel` (admin/moderador); `vinculos` traz o mesmo nível por
    marca_id direto (cobre marca sem evento nenhum ainda, que não
    apareceria em `eventos`) — o frontend usa isso pra esconder ações
    que o nível atual não permite (docs/PERMISSOES_SPEC.md §7 item 5).
    """
    if admin.super:
        return {"identificador": admin.identificador, "super": True, "eventos": [], "vinculos": []}

    eventos = await admin_vinculo_repo.listar_eventos_acessiveis_detalhado(pool, admin.user_id)
    return {
        "identificador": admin.identificador, "super": False,
        "eventos": eventos, "vinculos": admin.vinculos,
    }


# ── MODERAÇÃO DE ENTRADAS ─────────────────────────────────────────────────────

@router.patch("/entradas/{entrada_id}")
async def moderar_entrada(
    entrada_id: UUID4,
    body: AtualizarVisibilidade,
    pool=Depends(get_pool),
    moderador: AdminContext = Depends(require_admin),
):
    """
    Oculta (no_ranking=false) ou reativa (no_ranking=true) uma entrada.
    A foto nunca é deletada — evidência sempre preservada.
    Emite evento SSE para os clientes do ranking.
    """
    entrada = await entrada_repo.atualizar_visibilidade(
        pool, str(entrada_id), body.no_ranking, moderador.identificador
    )
    if not entrada:
        raise HTTPException(status_code=404, detail="Entrada não encontrada")

    # Busca o slug para o SSE
    row = await pool.fetchrow("SELECT slug FROM jogos WHERE id = $1", entrada["jogo_id"])
    slug = row["slug"] if row else str(entrada["jogo_id"])

    if body.no_ranking:
        await broker.publish(slug, "reativar", {
            "id": str(entrada_id),
            "entrada": {
                "id":        str(entrada["id"]),
                "nick":      entrada["nick"],
                "pontuacao": entrada["pontuacao"],
                "foto_url":  entrada["foto_url"],
            }
        })
    else:
        await broker.publish(slug, "ocultar", {"id": str(entrada_id)})

    log.info(
        "moderacao",
        entrada_id=str(entrada_id),
        no_ranking=body.no_ranking,
        moderador=moderador.identificador,
    )

    return entrada


@router.patch("/entradas/{entrada_id}/pendente")
async def resolver_pendente(
    entrada_id: UUID4,
    body: ResolverPendente,
    pool=Depends(get_pool),
    moderador: AdminContext = Depends(require_admin),
):
    """
    Resolve uma entrada pendente:
    - aprovar=true  → pendente=false, no_ranking=true  (aparece no ranking)
    - aprovar=false → pendente=false, no_ranking=false (fica oculta)
    """
    entrada = await entrada_repo.resolver_pendente(
        pool, str(entrada_id), body.aprovar, moderador.identificador
    )
    if not entrada:
        raise HTTPException(status_code=404, detail="Entrada não encontrada")

    if body.aprovar:
        row = await pool.fetchrow("SELECT slug FROM jogos WHERE id = $1", entrada["jogo_id"])
        slug = row["slug"] if row else str(entrada["jogo_id"])
        await broker.publish(slug, "novo_registro", {
            "id":        str(entrada["id"]),
            "nick":      entrada["nick"],
            "pontuacao": entrada["pontuacao"],
            "foto_url":  entrada["foto_url"],
            "criado_em": str(entrada["criado_em"]),
        })

    log.info(
        "pendente_resolvido",
        entrada_id=str(entrada_id),
        aprovado=body.aprovar,
        moderador=moderador.identificador,
    )

    return entrada


# ── GESTÃO DE JOGOS ───────────────────────────────────────────────────────────

@router.post("/jogos", status_code=201)
async def criar_jogo(
    body: CriarJogo,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """
    Cria um novo jogo. Moderador nunca cria jogo — decisão #1 do
    docs/PERMISSOES_SPEC.md (a primeira versão do backlog dizia o
    contrário; corrigido). Admin não-super: nasce pendente_aprovacao=true
    (fora do catálogo/placar geral até um super-admin aprovar), mas já
    é auto-vinculado aos eventos que esse admin tem acesso — utilizável
    imediatamente ali. Super-admin: comportamento de sempre, aprovado
    direto. Ver docs/SPEC.md §10 / migration 018.
    """
    if not admin.super and not any(v["nivel"] == "admin" for v in admin.vinculos):
        raise HTTPException(
            status_code=403,
            detail="Moderador não pode criar jogos — só admin ou super-admin",
        )

    try:
        jogo = await jogo_repo.criar(
            pool, body.nome, body.slug, body.score_max,
            pendente_aprovacao=not admin.super,
            criado_por=admin.identificador,
        )
    except Exception as exc:
        if "unique" in str(exc).lower():
            raise HTTPException(status_code=409, detail=f"Slug '{body.slug}' já existe")
        raise HTTPException(status_code=500, detail="Erro ao criar jogo")

    if not admin.super and admin.user_id:
        eventos_ids = await admin_vinculo_repo.listar_eventos_acessiveis(pool, admin.user_id)
        for evento_id in eventos_ids:
            await evento_jogo_repo.adicionar(pool, evento_id, str(jogo["id"]))

    return jogo


@router.patch("/jogos/{jogo_id}")
async def atualizar_jogo(
    jogo_id: UUID4,
    body: AtualizarJogo,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """Ativa/desativa um jogo ou atualiza seu score_max. Mesma regra de
    criar_jogo — moderador nunca edita jogo (decisão #1 do
    docs/PERMISSOES_SPEC.md), achado incidental: este endpoint não
    tinha checagem nenhuma além de estar autenticado."""
    if not admin.super and not any(v["nivel"] == "admin" for v in admin.vinculos):
        raise HTTPException(
            status_code=403,
            detail="Moderador não pode editar jogos — só admin ou super-admin",
        )

    jogo = await jogo_repo.atualizar(pool, str(jogo_id), body.ativo, body.score_max)
    if not jogo:
        raise HTTPException(status_code=404, detail="Jogo não encontrado ou nada para atualizar")
    return jogo

@router.get("/jogos-todos")
async def listar_jogos_todos(
    pool=Depends(get_pool),
    _: str = Depends(require_admin),
):
    """Lista todos os jogos incluindo inativos — para o painel admin."""
    return await jogo_repo.listar_todos(pool)


def _exigir_super_jogos(admin: AdminContext):
    if not admin.super:
        raise HTTPException(
            status_code=403,
            detail="Só super-admin pode revisar jogos pendentes de aprovação",
        )


@router.get("/jogos/pendentes")
async def listar_jogos_pendentes(
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """Jogos criados por admin não-super, aguardando aprovação pro
    catálogo geral — só super-admin revisa (ver migration 018)."""
    _exigir_super_jogos(admin)
    return await jogo_repo.listar_pendentes_aprovacao(pool)


@router.patch("/jogos/{jogo_id}/aprovar")
async def aprovar_jogo(
    jogo_id: UUID4,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """Aprova um jogo pendente pro catálogo geral — as entradas já
    enviadas entram retroativamente, sem precisar tocar nelas."""
    _exigir_super_jogos(admin)
    jogo = await jogo_repo.aprovar(pool, str(jogo_id))
    if not jogo:
        raise HTTPException(status_code=404, detail="Jogo não encontrado ou já não está pendente")
    return jogo


class MesclarJogo(BaseModel):
    jogo_destino_id: UUID4


@router.post("/jogos/{jogo_id}/mesclar")
async def mesclar_jogo(
    jogo_id: UUID4,
    body: MesclarJogo,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """
    Mescla jogo_id (origem, geralmente um pendente identificado como
    duplicata) em jogo_destino_id (o jogo já existente de verdade).
    Migra entradas e vínculos de evento, arquiva a origem mantendo o
    rastro — nunca apaga nada.
    """
    _exigir_super_jogos(admin)

    if str(jogo_id) == str(body.jogo_destino_id):
        raise HTTPException(status_code=422, detail="jogo_destino_id não pode ser igual ao jogo de origem")

    origem_existe = await pool.fetchval("SELECT 1 FROM jogos WHERE id = $1", str(jogo_id))
    destino_existe = await pool.fetchval("SELECT 1 FROM jogos WHERE id = $1", str(body.jogo_destino_id))
    if not origem_existe or not destino_existe:
        raise HTTPException(status_code=404, detail="Jogo de origem ou destino não encontrado")

    async with pool.acquire() as conn:
        async with conn.transaction():
            resultado = await jogo_repo.mesclar(conn, str(jogo_id), str(body.jogo_destino_id))

    log.info("jogo_mesclado", origem=str(jogo_id), destino=str(body.jogo_destino_id), admin=admin.identificador)
    return resultado


# ── CONFIGURAÇÃO DO EVENTO ────────────────────────────────────────────────────

import repositories.evento_config as config_repo

class AtualizarConfig(BaseModel):
    valor: str

@router.get("/config")
async def listar_config(
    pool=Depends(get_pool),
    _: str = Depends(require_admin),
):
    """Lista todas as configurações do evento."""
    return await config_repo.listar(pool)


@router.patch("/config/{chave}")
async def atualizar_config(
    chave: str,
    body: AtualizarConfig,
    pool=Depends(get_pool),
    _: str = Depends(require_admin),
):
    """Atualiza uma configuração pelo nome da chave."""
    cfg = await config_repo.atualizar(pool, chave, body.valor)
    if not cfg:
        raise HTTPException(status_code=404, detail=f"Configuração '{chave}' não encontrada")
    return cfg


# ── MANUTENÇÃO DE RANKINGS ────────────────────────────────────────────────────

class LimparRankingBody(BaseModel):
    jogo_id: str | None = None        # None = todos os jogos
    permanente: bool = False           # False = soft delete, True = DELETE físico
    confirmar: str = ""               # deve ser "CONFIRMAR" para prosseguir


def _exigir_super_manutencao(admin: AdminContext):
    """Limpar/restaurar ranking não tem filtro de marca/evento no corpo
    da requisição — afeta um jogo (ou TODOS os jogos, de TODAS as
    marcas) de uma vez. Sem um redesenho que escope por marca, é
    ação exclusiva de super-admin (achado incidental, não coberto pela
    tabela de decisões do docs/PERMISSOES_SPEC.md — 'manutenção' não é
    'moderar feed')."""
    if not admin.super:
        raise HTTPException(
            status_code=403,
            detail="Só super-admin pode limpar ou restaurar ranking — afeta todas as marcas de uma vez",
        )


@router.post("/manutencao/limpar-ranking")
async def limpar_ranking(
    body: LimparRankingBody,
    pool=Depends(get_pool),
    moderador: AdminContext = Depends(require_admin),
):
    """
    Limpa entradas de um jogo ou de todos os jogos.
    - permanente=False → soft delete (arquivado=true), reversível
    - permanente=True  → DELETE físico, irreversível
    Exige confirmar="CONFIRMAR" para prosseguir.
    """
    _exigir_super_manutencao(moderador)
    if body.confirmar != "CONFIRMAR":
        raise HTTPException(status_code=400, detail="Envie confirmar='CONFIRMAR' para prosseguir")

    if body.permanente:
        if body.jogo_id:
            count = await pool.fetchval(
                "SELECT COUNT(*) FROM entradas WHERE jogo_id = $1", body.jogo_id
            )
            await pool.execute("DELETE FROM entradas WHERE jogo_id = $1", body.jogo_id)
        else:
            count = await pool.fetchval("SELECT COUNT(*) FROM entradas")
            await pool.execute("DELETE FROM entradas")
        log.warning("ranking_limpo_permanente", jogo_id=body.jogo_id, total=count, moderador=moderador.identificador)
    else:
        if body.jogo_id:
            count = await pool.fetchval(
                "SELECT COUNT(*) FROM entradas WHERE jogo_id = $1 AND arquivado = false",
                body.jogo_id
            )
            await pool.execute(
                """UPDATE entradas SET arquivado = true, arquivado_em = now(), arquivado_por = $1
                   WHERE jogo_id = $2 AND arquivado = false""",
                moderador.identificador, body.jogo_id
            )
        else:
            count = await pool.fetchval(
                "SELECT COUNT(*) FROM entradas WHERE arquivado = false"
            )
            await pool.execute(
                """UPDATE entradas SET arquivado = true, arquivado_em = now(), arquivado_por = $1
                   WHERE arquivado = false""",
                moderador.identificador
            )
        log.warning("ranking_arquivado", jogo_id=body.jogo_id, total=count, moderador=moderador.identificador)

    return {"ok": True, "total_afetadas": count, "permanente": body.permanente}


@router.post("/manutencao/restaurar-ranking")
async def restaurar_ranking(
    body: LimparRankingBody,
    pool=Depends(get_pool),
    moderador: AdminContext = Depends(require_admin),
):
    """Restaura entradas arquivadas de um jogo ou de todos."""
    _exigir_super_manutencao(moderador)
    if body.confirmar != "CONFIRMAR":
        raise HTTPException(status_code=400, detail="Envie confirmar='CONFIRMAR' para prosseguir")

    if body.jogo_id:
        count = await pool.fetchval(
            "SELECT COUNT(*) FROM entradas WHERE jogo_id = $1 AND arquivado = true",
            body.jogo_id
        )
        await pool.execute(
            "UPDATE entradas SET arquivado = false, arquivado_em = null, arquivado_por = null WHERE jogo_id = $1 AND arquivado = true",
            body.jogo_id
        )
    else:
        count = await pool.fetchval("SELECT COUNT(*) FROM entradas WHERE arquivado = true")
        await pool.execute(
            "UPDATE entradas SET arquivado = false, arquivado_em = null, arquivado_por = null WHERE arquivado = true"
        )

    log.info("ranking_restaurado", jogo_id=body.jogo_id, total=count, moderador=moderador.identificador)
    return {"ok": True, "total_restauradas": count}