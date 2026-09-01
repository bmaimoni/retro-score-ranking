"""
Router admin de arenas — requer autenticação.
Prefixo: /api/admin/arenas

Ver docs/MARCAS_SPEC.md §3: arena é o nível acima de event — cor
primária, tipografia e logo herdam pra event quando o event não
define os seus (event → arena → default da plataforma).
"""
import filetype
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, EmailStr, field_validator
import repositories.arena as arena_repo
import repositories.membership as membership_repo
import repositories.arena_partnership as parceria_repo
import auth.repository as auth_repo
import auth.service as auth_svc
import services.arena_admissao as admissao
import services.convite_email as convite_email_svc
import services.storage as storage
from config import get_settings
from utils.db import get_pool
from middleware.auth import require_admin, require_super_or_authenticated_user, AdminContext

router = APIRouter(prefix="/api/admin/arenas", tags=["admin-arenas"])

TIPOGRAFIAS_VALIDAS = {"arcade", "futurista", "terminal"}

# Upload de logo (III.1) — mesma régua de tamanho/formato do upload de
# evidência de score (routers/event_public.py), validado por magic
# bytes, não pela extensão declarada.
LOGO_MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
LOGO_ALLOWED_MIME = {"image/jpeg", "image/png"}


def _validar_tipografia(v):
    if v is not None and v not in TIPOGRAFIAS_VALIDAS:
        raise ValueError(f"tipografia deve ser uma de {sorted(TIPOGRAFIAS_VALIDAS)}")
    return v


RATE_LIMIT_ARENAS_POR_DIA = 3

# H.1 — mais generoso que o de criação de Arena (B.3): convidar vários
# colegas de uma vez é o caso de uso normal, não abuso. Teto existe só
# pra não virar vetor de spam de e-mail em massa (ver
# PLANO_IMPLEMENTACAO_2026.md Fase 10).
RATE_LIMIT_CONVITES_POR_DIA = 10
ROLES_CONVITE_VALIDOS = {"admin", "moderador"}


def _exigir_super(admin: AdminContext):
    if not admin.super:
        raise HTTPException(status_code=403, detail="Só super-admin pode executar esta ação")


def _exigir_admin_na_arena(admin: AdminContext, arena_id: str):
    """
    Parcerias entre arenas: 'qualquer admin da arena, não exclusivo do
    dono' (decisão #3 do docs/RANKINGS_CONFIGURAVEIS_SPEC.md §2.2) —
    mesma régua de nível admin usada em atualizar_arena, moderador
    nunca opera parceria.
    """
    if not admin.super and not admin.eh_admin_na_arena(arena_id):
        raise HTTPException(status_code=403, detail="Sem permissão para gerenciar parcerias desta arena")


class MarcaCreate(BaseModel):
    nome: str
    slug: str
    cor_primaria: str | None = None
    tipografia: str | None = None
    logo_url: str | None = None
    dono_email: EmailStr | None = None  # ver docs/PERMISSOES_SPEC.md §8.3

    _valida_tipografia = field_validator("tipografia")(_validar_tipografia)


class MarcaUpdate(BaseModel):
    nome: str | None = None
    cor_primaria: str | None = None
    tipografia: str | None = None
    logo_url: str | None = None
    itens_por_pagina: int | None = None

    _valida_tipografia = field_validator("tipografia")(_validar_tipografia)

    @field_validator("itens_por_pagina")
    @classmethod
    def _valida_itens_por_pagina(cls, v):
        if v is not None and v <= 0:
            raise ValueError("itens_por_pagina deve ser positivo")
        return v


class TransferirTitularidade(BaseModel):
    email: EmailStr  # precisa já ter vínculo admin ativo nesta arena


class ConviteCreate(BaseModel):
    email: EmailStr
    role:  str

    @field_validator("role")
    @classmethod
    def _valida_role(cls, v):
        if v not in ROLES_CONVITE_VALIDOS:
            raise ValueError(f"role deve ser um de {sorted(ROLES_CONVITE_VALIDOS)}")
        return v


# ── CRUD de arenas ─────────────────────────────────────────────

@router.get("")
async def listar_arenas(pool=Depends(get_pool), admin: AdminContext = Depends(require_admin)):
    """super vê todas; admin/moderador só as arenas onde tem vínculo
    ativo — antes desta correção, o endpoint devolvia todas as arenas
    pra qualquer admin autenticado, vazando nome/identidade visual de
    outros clientes (docs/PERMISSOES_SPEC.md §8.1). Mesmo padrão já
    usado em GET /api/admin/events."""
    arenas = await arena_repo.listar_todas(pool)
    if admin.super:
        return arenas
    return [m for m in arenas if admin.tem_acesso_na_arena(m["id"])]


@router.post("", status_code=201)
async def criar_arena(
    dados: MarcaCreate,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_super_or_authenticated_user),
):
    """
    Endpoint único, comportamento condicional por quem chama (Fase 8,
    ARENA_SPEC.md G.3) — não dois endpoints separados.

    super: comportamento idêntico ao que já existia (dono_email
    opcional, sem rate limit — G.4, sem passar pela admissão B.2-B.4,
    nasce 'published' direto).

    Usuário comum autenticado (D.2/D.3): qualquer conta logada pode
    criar sua própria arena — passa pela sequência de admissão B.2-B.4
    e vira automaticamente admin+titular da arena criada.
    """
    if admin.super:
        usuario = None
        if dados.dono_email:
            usuario = await auth_repo.buscar_usuario_por_email(pool, dados.dono_email.lower().strip())
            if not usuario:
                raise HTTPException(
                    status_code=404,
                    detail="Essa pessoa ainda não tem conta — ela precisa logar pelo menos uma vez "
                           "(Google ou Magic Link) com esse e-mail antes de virar titular.",
                )

        try:
            arena = await arena_repo.criar(
                pool, dados.nome, dados.slug,
                dados.cor_primaria, dados.tipografia, dados.logo_url,
            )
        except Exception as exc:
            if "unique" in str(exc).lower():
                raise HTTPException(status_code=409, detail="Slug já existe")
            raise

        if usuario:
            # Concede o vínculo admin e já atribui a titularidade na mesma
            # chamada — colapsa os 2 passos manuais (POST /vinculos +
            # PATCH /titularidade) que antes deixavam uma janela de arena
            # sem dono se alguém esquecesse o segundo (docs/PERMISSOES_SPEC.md §8.3).
            arena_id = str(arena["id"])
            await membership_repo.criar(pool, str(usuario["id"]), "marca", "admin", arena_id)
            await membership_repo.registrar_auditoria(
                pool, acao="concedido", user_alvo_id=str(usuario["id"]), realizado_por=admin.identificador,
                arena_id=arena_id, role="admin",
            )
            arena = await arena_repo.transferir_titularidade(pool, arena_id, str(usuario["id"]))
            await membership_repo.registrar_auditoria(
                pool, acao="titularidade_transferida", user_alvo_id=str(usuario["id"]),
                realizado_por=admin.identificador, arena_id=arena_id, role=None,
                detalhes={"dono_anterior": None},
            )

        return arena

    # ── Caminho self-serve (usuário comum autenticado) ──────────────
    # admin.user_id sempre presente aqui — garantido por
    # require_super_or_authenticated_user quando super=False.

    criadas_ultimas_24h = await arena_repo.contar_criadas_por_owner_ultimas_24h(pool, admin.user_id)
    if criadas_ultimas_24h >= RATE_LIMIT_ARENAS_POR_DIA:
        raise HTTPException(
            status_code=429,
            detail=f"Limite de {RATE_LIMIT_ARENAS_POR_DIA} arenas criadas por dia atingido — tente novamente amanhã.",
        )

    try:
        logo_url = admissao.sanitizar_logo_url(dados.logo_url)
    except ValueError:
        raise HTTPException(status_code=422, detail="logo_url inválida")

    existentes = await arena_repo.listar_nome_slug(pool)
    resultado = admissao.avaliar_admissao(dados.nome, dados.slug, existentes)
    if resultado.bloqueado:
        raise HTTPException(status_code=409, detail=resultado.motivo)

    # B.4: quase-igual a uma existente, OU 2ª+ arena da mesma conta na
    # janela de 24h — qualquer um dos dois já é sinal o bastante pra
    # reter em fila de revisão em vez de publicar direto.
    status_inicial = "draft" if (resultado.suspeito or criadas_ultimas_24h >= 1) else "published"

    try:
        arena = await arena_repo.criar(
            pool, dados.nome, dados.slug,
            dados.cor_primaria, dados.tipografia, logo_url,
            status=status_inicial,
        )
    except Exception as exc:
        if "unique" in str(exc).lower():
            raise HTTPException(status_code=409, detail="Slug já existe")
        raise

    # Cria a arena já com o criador como admin+titular — sem passo
    # manual separado (mesmo padrão colapsado do caminho super acima).
    arena_id = str(arena["id"])
    await membership_repo.criar(pool, admin.user_id, "marca", "admin", arena_id)
    await membership_repo.registrar_auditoria(
        pool, acao="concedido", user_alvo_id=admin.user_id, realizado_por=admin.identificador,
        arena_id=arena_id, role="admin",
    )
    arena = await arena_repo.transferir_titularidade(pool, arena_id, admin.user_id)
    await membership_repo.registrar_auditoria(
        pool, acao="titularidade_transferida", user_alvo_id=admin.user_id,
        realizado_por=admin.identificador, arena_id=arena_id, role=None,
        detalhes={"dono_anterior": None, "self_serve": True},
    )

    return arena


@router.get("/pendentes")
async def listar_arenas_pendentes(pool=Depends(get_pool), admin: AdminContext = Depends(require_admin)):
    """Fila de revisão (B.4) — só super vê, arenas status='draft'."""
    _exigir_super(admin)
    return await arena_repo.listar_pendentes(pool)


@router.patch("/{arena_id}/aprovar")
async def aprovar_arena(
    arena_id: str,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """Aprova uma arena da fila de revisão — status='draft' vira
    'published', passa a aparecer em qualquer diretório público."""
    _exigir_super(admin)
    arena = await arena_repo.atualizar_status(pool, arena_id, "published")
    if not arena:
        raise HTTPException(status_code=404, detail="Marca não encontrada")
    return arena


@router.patch("/{arena_id}/suspender")
async def suspender_arena(
    arena_id: str,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """
    Congela uma arena (status='suspended') — usado tanto pra rejeitar
    uma arena ainda em 'draft' (fila de revisão) quanto pra suspender
    uma arena já 'published' com abuso confirmado depois (ARENA_SPEC.md
    C.1). Mesmo estado final nos dois casos: 'suspended' já significa
    "fora do ar publicamente", não precisa de um estado 'rejeitada'
    à parte — reaproveitar o mesmo campo evita uma transição de estado
    que a spec não distingue em nenhum outro lugar.
    """
    _exigir_super(admin)
    arena = await arena_repo.atualizar_status(pool, arena_id, "suspended")
    if not arena:
        raise HTTPException(status_code=404, detail="Marca não encontrada")
    return arena


@router.patch("/{arena_id}")
async def atualizar_arena(
    arena_id: str,
    dados: MarcaUpdate,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """Editar identidade visual da arena (nome/cor/tipografia/logo) é
    ação de admin da própria arena — mesma régua de 'games, events,
    telão' do docs/PERMISSOES_SPEC.md §4, moderador nunca edita."""
    if not admin.super and not admin.eh_admin_na_arena(arena_id):
        raise HTTPException(status_code=403, detail="Sem permissão para editar esta arena")

    arena = await arena_repo.atualizar(pool, arena_id, dados.model_dump(exclude_none=True))
    if not arena:
        raise HTTPException(status_code=404, detail="Marca não encontrada")
    return arena


@router.post("/{arena_id}/logo")
async def upload_logo_arena(
    arena_id: str,
    logo: UploadFile = File(...),
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """Upload de logo real (docs/PAINEIS_ADMIN_SPEC.md III.1) — antes só
    dava pra colar uma URL já hospedada em outro lugar. Retorna a URL
    pública; o frontend salva chamando PATCH /{arena_id} como sempre
    (mesmo campo `logo_url`, sem endpoint novo pra isso). Mesma régua de
    autorização do PATCH acima: admin da própria arena ou super."""
    await _resolver_arena_ou_404(pool, arena_id)
    if not admin.super and not admin.eh_admin_na_arena(arena_id):
        raise HTTPException(status_code=403, detail="Sem permissão para editar esta arena")

    conteudo = await logo.read()
    if len(conteudo) > LOGO_MAX_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="Logo excede o limite de 5MB")

    tipo = filetype.guess(conteudo)
    mime_detectado = tipo.mime if tipo else "application/octet-stream"
    if mime_detectado not in LOGO_ALLOWED_MIME:
        raise HTTPException(
            status_code=422,
            detail=f"Formato inválido ({mime_detectado}). Apenas JPEG e PNG são aceitos",
        )
    await logo.seek(0)

    logo_url = await storage.upload_logo(logo, arena_id)
    return {"logo_url": logo_url}


@router.patch("/{arena_id}/titularidade")
async def transferir_titularidade(
    arena_id: str,
    dados: TransferirTitularidade,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """
    Transfere arenas.owner_user_id — endpoint dedicado, não reaproveita
    PATCH /{arena_id} (docs/PERMISSOES_SPEC.md §7). Regras (decisão #11):
    só o titular atual ou super iniciam; só pra alguém que já tenha
    vínculo admin ativo nesta arena; o titular antigo mantém o vínculo
    admin (isto não revoga acesso, só muda quem é o titular).
    """
    arena = await arena_repo.buscar_por_id(pool, arena_id)
    if not arena:
        raise HTTPException(status_code=404, detail="Marca não encontrada")

    dono_atual_id = await arena_repo.buscar_owner_user_id(pool, arena_id)

    if not admin.super:
        if admin.user_id is None or dono_atual_id is None or str(admin.user_id) != str(dono_atual_id):
            raise HTTPException(
                status_code=403,
                detail="Só o titular atual da arena ou super-admin pode transferir a titularidade",
            )

    usuario = await auth_repo.buscar_usuario_por_email(pool, dados.email.lower().strip())
    if not usuario:
        raise HTTPException(
            status_code=404,
            detail="Essa pessoa ainda não tem conta — ela precisa logar pelo menos uma vez "
                   "(Google ou Magic Link) com esse e-mail antes de virar titular.",
        )

    if dono_atual_id and str(usuario["id"]) == str(dono_atual_id):
        raise HTTPException(status_code=422, detail="Essa pessoa já é a titular da arena")

    tem_vinculo = await membership_repo.tem_vinculo_admin_ativo(pool, usuario["id"], arena_id)
    if not tem_vinculo:
        raise HTTPException(
            status_code=422,
            detail="A nova titular precisa já ter vínculo admin ativo nesta arena — "
                   "conceda o vínculo antes de transferir a titularidade.",
        )

    atualizada = await arena_repo.transferir_titularidade(pool, arena_id, usuario["id"])

    await membership_repo.registrar_auditoria(
        pool, acao="titularidade_transferida", user_alvo_id=usuario["id"],
        realizado_por=admin.identificador, arena_id=arena_id, role=None,
        detalhes={"dono_anterior": dono_atual_id},
    )
    return atualizada


@router.get("/{arena_id}/wizard-status")
async def wizard_status(
    arena_id: str,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """
    Progresso do wizard pós-ativação (Fase 9, ARENA_SPEC.md E.1) —
    calculado on-the-fly a partir do que já existe, sem tabela de
    estado nova. Checklist nunca bloqueia o resto do painel — este
    endpoint só alimenta a UI de progresso.

    tem_evento: existe pelo menos 1 event pra esta arena.
    tem_colaborador: mais de 1 membership ativo scope='marca' nesta
      arena (o dono conta como 1 — "colaborador" significa mais
      alguém além dele).
    tem_branding: cor_primaria OU tipografia OU logo_url definidos.
    """
    arena = await _resolver_arena_ou_404(pool, arena_id)
    if not admin.super and not admin.tem_acesso_na_arena(arena_id):
        raise HTTPException(status_code=403, detail="Sem acesso a esta arena")

    events = await arena_repo.listar_events_da_arena(pool, arena_id)
    colaboradores = await membership_repo.listar_por_arenas(pool, [arena_id])
    colaboradores_ativos = [c for c in colaboradores if c["ativo"]]

    return {
        "tem_evento": len(events) > 0,
        "tem_colaborador": len(colaboradores_ativos) > 1,
        "tem_branding": bool(
            arena.get("cor_primaria") or arena.get("tipografia") or arena.get("logo_url")
        ),
    }


@router.get("/{arena_id}/resumo")
async def resumo_arena(
    arena_id: str,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """Tela inicial do painel (docs/PAINEIS_ADMIN_SPEC.md F0.3) — events
    da Arena ativa com janela de envio e contagem de recordes. Mesma
    checagem de acesso do wizard-status: super ou vínculo na arena."""
    await _resolver_arena_ou_404(pool, arena_id)
    if not admin.super and not admin.tem_acesso_na_arena(arena_id):
        raise HTTPException(status_code=403, detail="Sem acesso a esta arena")

    events = await arena_repo.listar_resumo_events_da_arena(pool, arena_id)
    return {"events": events}


@router.post("/{arena_id}/convites", status_code=201)
async def criar_convite(
    arena_id: str,
    dados: ConviteCreate,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """
    Convite assíncrono de coadministração (Fase 10, ARENA_SPEC.md Fase
    F) — substitui a concessão direta de POST /api/admin/vinculos, que
    exigia (404 se não) que o convidado já tivesse conta. Sempre passa
    por aceite explícito, mesmo se a pessoa já tiver conta (F.2) — um
    único caminho de código, não dois. Mesma régua de quem pode
    conceder vínculo direto (_exigir_admin_na_arena) — sem regra nova
    de quem pode convidar (F.6).
    """
    arena = await _resolver_arena_ou_404(pool, arena_id)
    _exigir_admin_na_arena(admin, arena_id)

    email = dados.email.lower().strip()
    if admin.identificador.lower().strip() == email:
        raise HTTPException(status_code=422, detail="Você não pode convidar a si mesmo")

    usuario_existente = await auth_repo.buscar_usuario_por_email(pool, email)
    if usuario_existente and await membership_repo.tem_vinculo_ativo(pool, usuario_existente["id"], arena_id):
        raise HTTPException(status_code=422, detail="Essa pessoa já colabora nesta Arena")

    if await membership_repo.buscar_convite_pendente_por_email(pool, arena_id, email):
        raise HTTPException(
            status_code=409,
            detail="Já existe um convite pendente pra esse e-mail nesta Arena — cancele antes de reenviar.",
        )

    settings = get_settings()
    criados_ultimas_24h = await membership_repo.contar_convites_por_remetente_ultimas_24h(
        pool, arena_id, admin.user_id,
    )
    if criados_ultimas_24h >= RATE_LIMIT_CONVITES_POR_DIA:
        raise HTTPException(
            status_code=429,
            detail=f"Limite de {RATE_LIMIT_CONVITES_POR_DIA} convites enviados por dia atingido — tente novamente amanhã.",
        )

    token, token_hash = auth_svc.gerar_token_magic_link()
    convite = await membership_repo.criar_convite(
        pool, arena_id, dados.role, email, admin.user_id, token_hash, settings.convite_ttl_days,
    )

    link = f"{settings.frontend_base_url}/convite.html?token={token}"
    try:
        await convite_email_svc.enviar_email_convite(email, link, arena["nome"], dados.role)
    except Exception:
        raise HTTPException(status_code=502, detail="Não foi possível enviar o e-mail de convite agora — tente novamente.")

    await membership_repo.registrar_auditoria(
        pool, acao="convite_enviado", user_alvo_id=None, realizado_por=admin.identificador,
        arena_id=arena_id, role=dados.role, detalhes={"email": email},
    )
    return convite


@router.get("/{arena_id}/convites")
async def listar_convites(
    arena_id: str,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """Fila de convites pendentes da Arena — mesma tela do wizard
    (Passo 2) usa isso pra listar quem já foi convidado e oferecer
    cancelar."""
    await _resolver_arena_ou_404(pool, arena_id)
    _exigir_admin_na_arena(admin, arena_id)
    return await membership_repo.listar_convites_pendentes(pool, arena_id)


@router.patch("/{arena_id}/convites/{convite_id}/cancelar")
async def cancelar_convite(
    arena_id: str,
    convite_id: str,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """Só quem convidou (ou super) pode cancelar — decisão F.6, mais
    restritiva que _exigir_admin_na_arena de propósito (não é 'qualquer
    admin da Arena', é quem de fato enviou aquele convite)."""
    convite = await membership_repo.buscar_convite_por_id(pool, convite_id)
    if not convite or str(convite["arena_id"]) != str(arena_id):
        raise HTTPException(status_code=404, detail="Convite não encontrado")

    if not admin.super and (admin.user_id is None or str(admin.user_id) != str(convite["invited_by"])):
        raise HTTPException(status_code=403, detail="Só quem enviou o convite pode cancelá-lo")

    cancelado = await membership_repo.cancelar_convite(pool, convite_id)
    if not cancelado:
        raise HTTPException(status_code=409, detail="Convite já foi aceito ou cancelado")

    await membership_repo.registrar_auditoria(
        pool, acao="convite_cancelado", user_alvo_id=None, realizado_por=admin.identificador,
        arena_id=arena_id, role=convite["role"], detalhes={"email": convite["email"]},
    )
    return cancelado


@router.get("/{arena_id}/events")
async def listar_events_da_arena(
    arena_id: str,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """Events vinculados a esta arena (o vínculo em si é feito via
    PATCH /api/admin/events/{id}, atualizando events.arena_id).

    docs/ARENA_ADMIN_SPEC.md AA.1 — achado: não checava escopo nenhum,
    deixando qualquer admin/moderador listar eventos (inclusive não
    públicos) de arena alheia. Leitura liberada pra quem tem qualquer
    vínculo na arena, mesmo padrão de listar_games_do_event."""
    if not admin.super and not admin.tem_acesso_na_arena(arena_id):
        raise HTTPException(status_code=403, detail="Sem acesso a esta arena")
    return await arena_repo.listar_events_da_arena(pool, arena_id)


# ── Parcerias entre arenas (docs/RANKINGS_CONFIGURAVEIS_SPEC.md §2.2) ──

async def _resolver_arena_ou_404(pool, arena_id: str) -> dict:
    arena = await arena_repo.buscar_por_id(pool, arena_id)
    if not arena:
        raise HTTPException(status_code=404, detail="Marca não encontrada")
    return arena


@router.get("/{arena_id}/parcerias")
async def listar_parcerias(
    arena_id: str,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """concedidas: arenas pra quem esta arena libera o próprio placar.
    recebidas: arenas que liberam o placar delas pra esta (com flag
    'reciproca' indicando se já foi aceita de volta)."""
    await _resolver_arena_ou_404(pool, arena_id)
    _exigir_admin_na_arena(admin, arena_id)
    return {
        "concedidas": await parceria_repo.listar_concedidas(pool, arena_id),
        "recebidas": await parceria_repo.listar_recebidas(pool, arena_id),
    }


@router.post("/{arena_id}/parcerias/{destino_id}/liberar", status_code=201)
async def liberar_parceria(
    arena_id: str,
    destino_id: str,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """
    arena_id (origem) libera o próprio placar pra destino_id ver em
    modo_ranking=marca_parceiras — efeito imediato, sem exigir aceite
    pra já valer nesse sentido (decisão #5). destino_id só reciprocar
    (ver /aceitar) fecha a mutualidade (decisão #2).
    """
    if arena_id == destino_id:
        raise HTTPException(status_code=422, detail="Uma arena não pode fazer parceria consigo mesma")
    await _resolver_arena_ou_404(pool, arena_id)
    await _resolver_arena_ou_404(pool, destino_id)
    _exigir_admin_na_arena(admin, arena_id)

    parceria = await parceria_repo.criar_ou_reativar(pool, arena_id, destino_id)
    await membership_repo.registrar_auditoria(
        pool, acao="parceria_liberada", user_alvo_id=admin.user_id,
        realizado_por=admin.identificador, arena_id=arena_id, role=None,
        detalhes={"arena_destino_id": destino_id},
    )
    return parceria


@router.post("/{arena_id}/parcerias/{origem_id}/aceitar", status_code=201)
async def aceitar_parceria(
    arena_id: str,
    origem_id: str,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """
    arena_id aceita uma liberação recebida de origem_id — cria a linha
    recíproca arena_id→origem_id, fechando a mutualidade (decisão #2).
    Exige que origem_id→arena_id exista e esteja ativa; senão não há
    o que aceitar.
    """
    if arena_id == origem_id:
        raise HTTPException(status_code=422, detail="Uma arena não pode fazer parceria consigo mesma")
    await _resolver_arena_ou_404(pool, arena_id)
    await _resolver_arena_ou_404(pool, origem_id)
    _exigir_admin_na_arena(admin, arena_id)

    liberacao = await parceria_repo.buscar(pool, origem_id, arena_id)
    if not liberacao or not liberacao["ativo"]:
        raise HTTPException(
            status_code=422,
            detail="Não há liberação ativa dessa arena pra aceitar",
        )

    parceria = await parceria_repo.criar_ou_reativar(pool, arena_id, origem_id)
    await membership_repo.registrar_auditoria(
        pool, acao="parceria_aceita", user_alvo_id=admin.user_id,
        realizado_por=admin.identificador, arena_id=arena_id, role=None,
        detalhes={"arena_origem_id": origem_id},
    )
    return parceria


@router.post("/{arena_id}/parcerias/{destino_id}/revogar")
async def revogar_parceria(
    arena_id: str,
    destino_id: str,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """Revoga só a própria concessão arena_id→destino_id — não afeta a
    linha recíproca, que pode ficar assimétrica (decisão #5)."""
    await _resolver_arena_ou_404(pool, arena_id)
    _exigir_admin_na_arena(admin, arena_id)

    parceria = await parceria_repo.revogar(pool, arena_id, destino_id)
    if not parceria:
        raise HTTPException(status_code=404, detail="Não há liberação ativa dessa arena pra essa arena destino")

    await membership_repo.registrar_auditoria(
        pool, acao="parceria_revogada", user_alvo_id=admin.user_id,
        realizado_por=admin.identificador, arena_id=arena_id, role=None,
        detalhes={"arena_destino_id": destino_id},
    )
    return parceria
