import filetype
from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException
from pydantic import UUID4
from utils.db import get_pool
from utils.ip import get_client_ip, hash_ip
from services import storage, rate_limit as rl, nick as nick_svc, score as score_svc
from services.sse import broker
import repositories.entrada as entrada_repo
import repositories.jogo as jogo_repo
from fastapi import Request
import structlog

log = structlog.get_logger()

router = APIRouter(prefix="/api", tags=["upload"])

ALLOWED_MIME = {"image/jpeg", "image/png"}
MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


@router.post("/upload", status_code=201)
async def upload(
    request: Request,
    foto: UploadFile | None = File(None, description="Foto com o placar visível (JPEG ou PNG, máx 5MB — opcional)"),
    nick: str = Form(..., min_length=1, max_length=50),
    nome: str | None = Form(default=None, max_length=100),
    pontuacao: int = Form(..., gt=0),
    jogo_id: UUID4 = Form(...),
    pool=Depends(get_pool),
):
    """
    Endpoint principal de participação.

    Fluxo:
    1. Valida tipo e tamanho da foto
    2. Valida score contra o jogo
    3. Calcula hash do IP e verifica rate limit
    4. Faz upload da foto para o Storage (imutável)
    5. Dentro de uma transação:
       a. Marca entrada anterior do nick como superada
       b. Insere nova entrada (pendente se rate limit atingido)
    6. Notifica clientes SSE se a entrada for visível imediatamente
    """

    # ── 1. Validação da foto (opcional) ──────────────────────────────────────
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

    # ── 2. Validação do score ─────────────────────────────────────────────────
    await score_svc.validar_score(pool, str(jogo_id), pontuacao)

    # ── 3. Rate limit ─────────────────────────────────────────────────────────
    ip = get_client_ip(request)
    ip_hash = hash_ip(ip)
    pendente = await rl.checar_rate_limit(pool, ip_hash)

    if pendente:
        log.info("upload_rate_limited", ip_hash=ip_hash[:8], nick=nick[:20])

    # ── 4. Upload da foto (se fornecida) ─────────────────────────────────────
    foto_url = await storage.upload_foto(foto) if foto is not None else None

    # Sem foto → vai para moderação (sem evidência visual do placar)
    if foto is None:
        pendente = True

    # ── 5. Transação: marcar anterior como superado + inserir nova entrada ────
    nick_normalizado = nick_svc.normalizar_nick(nick)

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

    # ── 6. Notifica SSE se visível imediatamente ──────────────────────────────
    if not pendente:
        slug = await _slug_from_id(pool, str(jogo_id))
        jogo = await jogo_repo.buscar_por_slug(pool, slug)
        slug = jogo["slug"] if jogo else str(jogo_id)
        await broker.publish(slug, "novo_registro", {
            "id":        str(entrada["id"]),
            "nick":      entrada["nick"],
            "pontuacao": entrada["pontuacao"],
            "foto_url":  entrada["foto_url"],
            "criado_em": str(entrada["criado_em"]),
        })

    log.info(
        "upload_ok",
        entrada_id=str(entrada["id"]),
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