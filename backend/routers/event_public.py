"""
Router público de events — acessível sem autenticação.
Prefixo: /api/e/{slug}

Endpoints:
  GET  /api/e/{slug}/config             → config pública do event
  GET  /api/e/{slug}/games              → games ativos do event
  GET  /api/e/{slug}/ranking/lideres    → top 1 de cada game do event
  GET  /api/e/{slug}/ranking/{game_slug} → ranking filtrado por event
  POST /api/e/{slug}/upload             → envio de score para o event

Ver docs/EVENTOS_SPEC.md para o desenho completo (events simultâneos,
janela de envio, integração com auth em docs/AUTH_SPEC.md §4.3).
"""
import filetype
import structlog
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, File, Form, UploadFile
from pydantic import UUID4
from utils.db import get_pool
from utils.ip import get_client_ip, hash_ip
from services import storage, rate_limit as rl, nick as nick_svc, score as score_svc, ranking as ranking_svc
from services.sse import broker
import repositories.event      as event_repo
import repositories.event_game as event_game_repo
import repositories.game        as game_repo
import repositories.entry     as entry_repo
import repositories.arena       as arena_repo
import auth.service as auth_svc

log = structlog.get_logger()

router = APIRouter(prefix="/api/e", tags=["event-publico"])

ALLOWED_MIME = {"image/jpeg", "image/png"}
MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


async def _get_event_public(slug: str, pool) -> dict:
    """Helper: busca event público ou levanta 404/403."""
    event = await event_repo.buscar_por_slug(pool, slug)
    if not event:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    if not event["ativo"]:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    if not event["publico"]:
        raise HTTPException(status_code=403, detail="Este event está temporariamente inacessível")
    return event


async def _get_event_aceitando_envios(slug: str, pool) -> dict:
    """
    Helper: além das checagens de _get_event_public, garante que o
    momento atual está dentro da janela [data_inicio, data_fim] do event.
    Visibilidade (publico) e janela de envio são independentes — ver
    docs/EVENTOS_SPEC.md §3.
    """
    event = await _get_event_public(slug, pool)
    agora = datetime.now(timezone.utc)
    if not (event["data_inicio"] <= agora <= event["data_fim"]):
        raise HTTPException(
            status_code=422,
            detail="Este event não está mais aceitando novas pontuações.",
        )
    return event


# ── Config pública do event ──────────────────────────────────

@router.get("/{slug}/config")
async def get_config_event(slug: str, pool=Depends(get_pool)):
    """
    Retorna configuração pública do event: nome, logo_url, cor_primaria,
    tipografia — já resolvidos pela cadeia de herança event → arena →
    (null, frontend usa seu próprio default). Ver docs/MARCAS_SPEC.md §3-4.
    """
    await _get_event_public(slug, pool)  # 404/403 se não existir/não público
    identidade = await arena_repo.resolver_identidade_visual(pool, slug)
    return {
        "slug":         identidade["slug"],
        "nome":         identidade["nome"],
        "logo_url":     identidade["logo_url"],
        "cor_primaria": identidade["cor_primaria"],
        "tipografia":   identidade["tipografia"],
    }


# ── Event de envio atual (QR/link "participe") ────────────────

@router.get("/{slug}/event-envio-atual")
async def get_event_envio_atual(slug: str, pool=Depends(get_pool)):
    """
    Resolve pra qual event apontar o QR/link de envio nesta página
    (docs/BACKLOG_2026.md §3 item 3.3). Em modo_ranking='zerado' o
    próprio event já é a resposta certa; nos modos agregados, aponta
    pro event mais recente/ativo da arena dona da página — mesmo
    critério de "arena dona" já usado pra itens_por_pagina (item 3.2).
    """
    event = await _get_event_public(slug, pool)
    if event["modo_ranking"] == "zerado":
        return {"slug": slug}

    alvo = await event_repo.buscar_event_envio_atual_da_arena(pool, str(event["arena_id"]))
    return {"slug": alvo["slug"] if alvo else slug}


# ── Games do event ───────────────────────────────────────────

@router.get("/{slug}/games")
async def get_games_event(slug: str, pool=Depends(get_pool)):
    """
    Lista games ativos do event, com seus temas.
    Substitui /api/games no contexto de um event específico.
    """
    event = await _get_event_public(slug, pool)
    games  = await event_game_repo.listar_por_event(pool, str(event["id"]))
    return games


# ── Líderes por event ────────────────────────────────────────
# IMPORTANTE: esta rota deve vir ANTES de /{slug}/ranking/{game_slug},
# senão "lideres" é capturado como game_slug pela rota genérica e
# este endpoint fica inacessível.

@router.get("/{slug}/ranking/lideres")
async def get_lideres_event(slug: str, pool=Depends(get_pool)):
    """
    Top 1 de cada game do event.
    Usado no index para exibir o líder em cada card de game.

    A fonte do score respeita events.modo_ranking (docs/
    RANKINGS_CONFIGURAVEIS_SPEC.md §2.1) — em modos agregados, o líder
    pode vir de outro event da arena (ou parceira), não só deste.
    """
    event     = await _get_event_public(slug, pool)
    event_ids = await ranking_svc.resolver_event_ids(pool, event)
    return await entry_repo.listar_lideres_por_events(pool, str(event["id"]), event_ids)


# ── Ranking filtrado por event (respeita modo_ranking) ────────

@router.get("/{slug}/ranking/{game_slug}")
async def get_ranking_event(slug: str, game_slug: str, pool=Depends(get_pool)):
    """
    Ranking de um game no escopo deste event — o escopo em si depende
    de events.modo_ranking (docs/RANKINGS_CONFIGURAVEIS_SPEC.md §2.1):
    zerado = só este event; ultimo_evento/marca/marca_parceiras =
    agregação viva de vários events; geral = placar da plataforma
    inteira, sem filtro de event nenhum.
    """
    event = await _get_event_public(slug, pool)
    game   = await game_repo.buscar_por_slug(pool, game_slug)
    if not game:
        raise HTTPException(status_code=404, detail="Jogo não encontrado")

    event_ids = await ranking_svc.resolver_event_ids(pool, event)
    if event_ids is None:
        entries = await entry_repo.listar_ranking(pool, str(game["id"]))
    else:
        entries = await entry_repo.listar_ranking_por_events(pool, str(game["id"]), event_ids)

    return {
        "game": game,
        "event": slug,
        "modo_ranking": event["modo_ranking"],
        "entries": entries,
    }


# ── Upload de score ───────────────────────────────────────────

@router.post("/{slug}/upload", status_code=201)
async def upload_event(
    slug: str,
    request: Request,
    foto: UploadFile | None = File(None, description="Foto com o placar visível (JPEG ou PNG, máx 5MB — opcional)"),
    nick: str = Form(..., min_length=1, max_length=50),
    nome: str | None = Form(default=None, max_length=100),
    pontuacao: int = Form(..., gt=0, lt=100_000_000),
    game_id: UUID4 = Form(...),
    pool=Depends(get_pool),
    usuario: dict | None = Depends(auth_svc.sessao_opcional),
):
    """
    Endpoint principal de participação, escopado por event.

    Fluxo:
    1. Event existe / está publico / dentro da janela de envio (data_inicio-data_fim)
    2. Valida tipo e tamanho da foto
    3. Valida score contra o game
    4. Calcula hash do IP e verifica rate limit
    5. Faz upload da foto para o Storage (imutável)
    6. Checa nick_claims (AUTH_SPEC.md §4.3) — nick livre reivindica
       pro usuário logado; sem sessão, só bloqueia se o nick já tiver
       dono; nick de outro usuário é rejeitado
    7. Dentro de uma transação:
       a. Marca entry anterior do nick como superada
       b. Insere nova entry (pendente se rate limit atingido), sempre
          com event_id preenchido e user_id quando houver sessão
    8. Notifica clientes SSE se a entry for visível imediatamente
    """
    event = await _get_event_aceitando_envios(slug, pool)

    # ── 2. Validação da foto (opcional) ──────────────────────────────────────
    if foto is not None:
        conteudo = await foto.read()
        await foto.seek(0)  # rewind para uso posterior

        if len(conteudo) > MAX_SIZE_BYTES:
            raise HTTPException(status_code=413, detail="Foto excede o limite de 5MB")

        # Valida pelo magic bytes, não pela extensão declarada
        tipo = filetype.guess(conteudo)
        mime_detectado = tipo.mime if tipo else "application/octet-stream"
        if mime_detectado not in ALLOWED_MIME:
            raise HTTPException(
                status_code=422,
                detail=f"Formato inválido ({mime_detectado}). Apenas JPEG e PNG são aceitos",
            )

    # ── 3. Validação do score ─────────────────────────────────────────────────
    await score_svc.validar_score(pool, str(game_id), pontuacao)

    # ── 4. Rate limit ─────────────────────────────────────────────────────────
    ip = get_client_ip(request)
    ip_hash = hash_ip(ip)
    pendente = await rl.checar_rate_limit(pool, ip_hash)

    if pendente:
        log.info("upload_rate_limited", ip_hash=ip_hash[:8], nick=nick[:20])

    # ── 5. Upload da foto (se fornecida) ─────────────────────────────────────
    foto_url = await storage.upload_foto(foto) if foto is not None else None

    # Sem foto → vai para moderação (sem evidência visual do placar)
    if foto is None:
        pendente = True

    # ── 6. Reivindicação de nick (AUTH_SPEC.md §3, §4.3) ──────────────────────
    nick_normalizado = nick_svc.normalizar_nick(nick)
    try:
        await auth_svc.verificar_e_reivindicar_nick(
            pool, nick, nick_normalizado, usuario["id"] if usuario else None
        )
    except auth_svc.NickJaReivindicadoError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    # ── 7. Transação: marcar anterior como superado + inserir nova entry ────
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await nick_svc.marcar_anterior_como_superado(
                    pool, nick_normalizado, str(game_id), conn=conn
                )

                entry = await entry_repo.inserir(conn, {
                    "game_id":   str(game_id),
                    "nick":      nick.strip(),
                    "nick_norm": nick_normalizado,
                    "nome":      nome.strip() if nome else None,
                    "pontuacao": pontuacao,
                    "foto_url":  foto_url,
                    "no_ranking": not pendente,
                    "pendente":  pendente,
                    "ip_hash":   ip_hash,
                    "event_id": str(event["id"]),
                    "user_id":   usuario["id"] if usuario else None,
                })

    except Exception as exc:
        # Conflito de EXCLUDE constraint = race condition de nick simultâneo
        if "nick_ativo_unico" in str(exc):
            raise HTTPException(
                status_code=409,
                detail="Outro envio deste nick está sendo processado. Tente em instantes.",
            )
        import traceback
        log.error("upload_db_error",
                  error=repr(exc),
                  error_type=type(exc).__name__,
                  traceback=traceback.format_exc())
        raise HTTPException(status_code=500, detail="Erro interno ao salvar entry")

    # ── 7. Notifica SSE se visível imediatamente ──────────────────────────────
    if not pendente:
        game_slug = await _slug_from_id(pool, str(game_id))
        await broker.publish(game_slug, "novo_registro", {
            "id":        str(entry["id"]),
            "nick":      entry["nick"],
            "pontuacao": entry["pontuacao"],
            "foto_url":  entry["foto_url"],
            "criado_em": str(entry["criado_em"]),
        })

    log.info(
        "upload_ok",
        entry_id=str(entry["id"]),
        event_slug=slug,
        nick=nick[:20],
        pendente=pendente,
    )

    return {
        "id":       str(entry["id"]),
        "nick":     entry["nick"],
        "pontuacao": entry["pontuacao"],
        "foto_url": entry["foto_url"],
        "pendente": entry["pendente"],
        "mensagem": (
            "Sua pontuação está em análise e aparecerá em breve no ranking."
            if pendente else
            "Você está no ranking!"
        ),
    }


async def _slug_from_id(pool, game_id: str) -> str:
    """Helper: busca o slug pelo id do game para o publish SSE."""
    row = await pool.fetchrow("SELECT slug FROM games WHERE id = $1", game_id)
    return row["slug"] if row else game_id
