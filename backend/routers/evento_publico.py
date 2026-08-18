"""
Router público de eventos — acessível sem autenticação.
Prefixo: /api/e/{slug}

Endpoints:
  GET  /api/e/{slug}/config             → config pública do evento
  GET  /api/e/{slug}/jogos              → jogos ativos do evento
  GET  /api/e/{slug}/ranking/lideres    → top 1 de cada jogo do evento
  GET  /api/e/{slug}/ranking/{jogo_slug} → ranking filtrado por evento
  POST /api/e/{slug}/upload             → envio de score para o evento

Ver docs/EVENTOS_SPEC.md para o desenho completo (eventos simultâneos,
janela de envio, integração com auth em docs/AUTH_SPEC.md §4.3).
"""
import filetype
import structlog
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, File, Form, UploadFile
from pydantic import UUID4
from utils.db import get_pool
from utils.ip import get_client_ip, hash_ip
from services import storage, rate_limit as rl, nick as nick_svc, score as score_svc
from services.sse import broker
import repositories.evento      as evento_repo
import repositories.evento_jogo as evento_jogo_repo
import repositories.jogo        as jogo_repo
import repositories.entrada     as entrada_repo
import auth.service as auth_svc

log = structlog.get_logger()

router = APIRouter(prefix="/api/e", tags=["evento-publico"])

ALLOWED_MIME = {"image/jpeg", "image/png"}
MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


async def _get_evento_publico(slug: str, pool) -> dict:
    """Helper: busca evento público ou levanta 404/403."""
    evento = await evento_repo.buscar_por_slug(pool, slug)
    if not evento:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    if not evento["ativo"]:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    if not evento["publico"]:
        raise HTTPException(status_code=403, detail="Este evento está temporariamente inacessível")
    return evento


async def _get_evento_aceitando_envios(slug: str, pool) -> dict:
    """
    Helper: além das checagens de _get_evento_publico, garante que o
    momento atual está dentro da janela [data_inicio, data_fim] do evento.
    Visibilidade (publico) e janela de envio são independentes — ver
    docs/EVENTOS_SPEC.md §3.
    """
    evento = await _get_evento_publico(slug, pool)
    agora = datetime.now(timezone.utc)
    if not (evento["data_inicio"] <= agora <= evento["data_fim"]):
        raise HTTPException(
            status_code=422,
            detail="Este evento não está mais aceitando novas pontuações.",
        )
    return evento


# ── Config pública do evento ──────────────────────────────────

@router.get("/{slug}/config")
async def get_config_evento(slug: str, pool=Depends(get_pool)):
    """
    Retorna configuração pública do evento:
    nome, logo_url, cor_primaria.
    Usado pelo frontend para aplicar identidade visual.
    """
    evento = await _get_evento_publico(slug, pool)
    return {
        "slug":         evento["slug"],
        "nome":         evento["nome"],
        "logo_url":     evento.get("logo_url"),
        "cor_primaria": evento.get("cor_primaria"),
    }


# ── Jogos do evento ───────────────────────────────────────────

@router.get("/{slug}/jogos")
async def get_jogos_evento(slug: str, pool=Depends(get_pool)):
    """
    Lista jogos ativos do evento, com seus temas.
    Substitui /api/jogos no contexto de um evento específico.
    """
    evento = await _get_evento_publico(slug, pool)
    jogos  = await evento_jogo_repo.listar_por_evento(pool, str(evento["id"]))
    return jogos


# ── Líderes por evento ────────────────────────────────────────
# IMPORTANTE: esta rota deve vir ANTES de /{slug}/ranking/{jogo_slug},
# senão "lideres" é capturado como jogo_slug pela rota genérica e
# este endpoint fica inacessível.

@router.get("/{slug}/ranking/lideres")
async def get_lideres_evento(slug: str, pool=Depends(get_pool)):
    """
    Top 1 de cada jogo do evento.
    Usado no index para exibir o líder em cada card de jogo.
    """
    evento = await _get_evento_publico(slug, pool)
    rows   = await pool.fetch(
        """
        SELECT DISTINCT ON (e.jogo_id)
            e.jogo_id,
            j.slug,
            e.nick,
            e.pontuacao
        FROM entradas e
        JOIN jogos j ON j.id = e.jogo_id
        JOIN evento_jogos ej ON ej.jogo_id = e.jogo_id
                             AND ej.evento_id = $1
                             AND ej.ativo = true
        WHERE e.evento_id  = $1
          AND e.no_ranking = true
          AND e.superado   = false
          AND e.pendente   = false
          AND e.arquivado  = false
        ORDER BY e.jogo_id, e.pontuacao DESC, e.criado_em ASC, e.id ASC
        """,
        str(evento["id"]),
    )
    return {
        str(r["jogo_id"]): {
            "slug":      r["slug"],
            "nick":      r["nick"],
            "pontuacao": r["pontuacao"],
        }
        for r in rows
    }


# ── Ranking filtrado por evento ───────────────────────────────

@router.get("/{slug}/ranking/{jogo_slug}")
async def get_ranking_evento(slug: str, jogo_slug: str, pool=Depends(get_pool)):
    """
    Ranking de um jogo filtrado pelo evento.
    Retorna apenas scores registrados neste evento.
    """
    evento = await _get_evento_publico(slug, pool)
    jogo   = await jogo_repo.buscar_por_slug(pool, jogo_slug)
    if not jogo:
        raise HTTPException(status_code=404, detail="Jogo não encontrado")

    entradas = await entrada_repo.listar_ranking_por_evento(
        pool, str(jogo["id"]), str(evento["id"])
    )
    return {"jogo": jogo, "evento": slug, "entradas": entradas}


# ── Upload de score ───────────────────────────────────────────

@router.post("/{slug}/upload", status_code=201)
async def upload_evento(
    slug: str,
    request: Request,
    foto: UploadFile | None = File(None, description="Foto com o placar visível (JPEG ou PNG, máx 5MB — opcional)"),
    nick: str = Form(..., min_length=1, max_length=50),
    nome: str | None = Form(default=None, max_length=100),
    pontuacao: int = Form(..., gt=0, lt=100_000_000),
    jogo_id: UUID4 = Form(...),
    pool=Depends(get_pool),
    usuario: dict | None = Depends(auth_svc.sessao_opcional),
):
    """
    Endpoint principal de participação, escopado por evento.

    Fluxo:
    1. Evento existe / está publico / dentro da janela de envio (data_inicio-data_fim)
    2. Valida tipo e tamanho da foto
    3. Valida score contra o jogo
    4. Calcula hash do IP e verifica rate limit
    5. Faz upload da foto para o Storage (imutável)
    6. Checa nick_claims (AUTH_SPEC.md §4.3) — nick livre reivindica
       pro usuário logado; sem sessão, só bloqueia se o nick já tiver
       dono; nick de outro usuário é rejeitado
    7. Dentro de uma transação:
       a. Marca entrada anterior do nick como superada
       b. Insere nova entrada (pendente se rate limit atingido), sempre
          com evento_id preenchido e user_id quando houver sessão
    8. Notifica clientes SSE se a entrada for visível imediatamente
    """
    evento = await _get_evento_aceitando_envios(slug, pool)

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
    await score_svc.validar_score(pool, str(jogo_id), pontuacao)

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
            pool, nick_normalizado, usuario["id"] if usuario else None
        )
    except auth_svc.NickJaReivindicadoError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    # ── 7. Transação: marcar anterior como superado + inserir nova entrada ────
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await nick_svc.marcar_anterior_como_superado(
                    pool, nick_normalizado, str(jogo_id), conn=conn
                )

                entrada = await entrada_repo.inserir(conn, {
                    "jogo_id":   str(jogo_id),
                    "nick":      nick.strip(),
                    "nick_norm": nick_normalizado,
                    "nome":      nome.strip() if nome else None,
                    "pontuacao": pontuacao,
                    "foto_url":  foto_url,
                    "no_ranking": not pendente,
                    "pendente":  pendente,
                    "ip_hash":   ip_hash,
                    "evento_id": str(evento["id"]),
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
        raise HTTPException(status_code=500, detail="Erro interno ao salvar entrada")

    # ── 7. Notifica SSE se visível imediatamente ──────────────────────────────
    if not pendente:
        jogo_slug = await _slug_from_id(pool, str(jogo_id))
        await broker.publish(jogo_slug, "novo_registro", {
            "id":        str(entrada["id"]),
            "nick":      entrada["nick"],
            "pontuacao": entrada["pontuacao"],
            "foto_url":  entrada["foto_url"],
            "criado_em": str(entrada["criado_em"]),
        })

    log.info(
        "upload_ok",
        entrada_id=str(entrada["id"]),
        evento_slug=slug,
        nick=nick[:20],
        pendente=pendente,
    )

    return {
        "id":       str(entrada["id"]),
        "nick":     entrada["nick"],
        "pontuacao": entrada["pontuacao"],
        "foto_url": entrada["foto_url"],
        "pendente": entrada["pendente"],
        "mensagem": (
            "Sua pontuação está em análise e aparecerá em breve no ranking."
            if pendente else
            "Você está no ranking!"
        ),
    }


async def _slug_from_id(pool, jogo_id: str) -> str:
    """Helper: busca o slug pelo id do jogo para o publish SSE."""
    row = await pool.fetchrow("SELECT slug FROM jogos WHERE id = $1", jogo_id)
    return row["slug"] if row else jogo_id
