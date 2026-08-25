"""
Router admin de marcas — requer autenticação.
Prefixo: /api/admin/marcas

Ver docs/MARCAS_SPEC.md §3: marca é o nível acima de evento — cor
primária, tipografia e logo herdam pra evento quando o evento não
define os seus (evento → marca → default da plataforma).
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, field_validator
import repositories.marca as marca_repo
import repositories.admin_vinculo as admin_vinculo_repo
import repositories.marca_parceria as parceria_repo
import auth.repository as auth_repo
from utils.db import get_pool
from middleware.auth import require_admin, AdminContext

router = APIRouter(prefix="/api/admin/marcas", tags=["admin-marcas"])

TIPOGRAFIAS_VALIDAS = {"arcade", "futurista", "terminal"}


def _validar_tipografia(v):
    if v is not None and v not in TIPOGRAFIAS_VALIDAS:
        raise ValueError(f"tipografia deve ser uma de {sorted(TIPOGRAFIAS_VALIDAS)}")
    return v


def _exigir_super(admin: AdminContext):
    """Só super cria marca — decisão #7 do docs/PERMISSOES_SPEC.md:
    nem o dono de uma marca pode criar outra. Achado #5 da mesma spec:
    esse endpoint aceitava qualquer admin autenticado antes desta
    correção, bug pré-existente."""
    if not admin.super:
        raise HTTPException(status_code=403, detail="Só super-admin pode criar marca")


def _exigir_admin_na_marca(admin: AdminContext, marca_id: str):
    """
    Parcerias entre marcas: 'qualquer admin da marca, não exclusivo do
    dono' (decisão #3 do docs/RANKINGS_CONFIGURAVEIS_SPEC.md §2.2) —
    mesma régua de nível admin usada em atualizar_marca, moderador
    nunca opera parceria.
    """
    if not admin.super and not admin.eh_admin_na_marca(marca_id):
        raise HTTPException(status_code=403, detail="Sem permissão para gerenciar parcerias desta marca")


class MarcaCreate(BaseModel):
    nome: str
    slug: str
    cor_primaria: str | None = None
    tipografia: str | None = None
    logo_url: str | None = None

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
    email: EmailStr  # precisa já ter vínculo admin ativo nesta marca


# ── CRUD de marcas ─────────────────────────────────────────────

@router.get("")
async def listar_marcas(pool=Depends(get_pool), _=Depends(require_admin)):
    return await marca_repo.listar_todas(pool)


@router.post("", status_code=201)
async def criar_marca(
    dados: MarcaCreate,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    _exigir_super(admin)
    try:
        return await marca_repo.criar(
            pool, dados.nome, dados.slug,
            dados.cor_primaria, dados.tipografia, dados.logo_url,
        )
    except Exception as exc:
        if "unique" in str(exc).lower():
            raise HTTPException(status_code=409, detail="Slug já existe")
        raise


@router.patch("/{marca_id}")
async def atualizar_marca(
    marca_id: str,
    dados: MarcaUpdate,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """Editar identidade visual da marca (nome/cor/tipografia/logo) é
    ação de admin da própria marca — mesma régua de 'jogos, eventos,
    telão' do docs/PERMISSOES_SPEC.md §4, moderador nunca edita."""
    if not admin.super and not admin.eh_admin_na_marca(marca_id):
        raise HTTPException(status_code=403, detail="Sem permissão para editar esta marca")

    marca = await marca_repo.atualizar(pool, marca_id, dados.model_dump(exclude_none=True))
    if not marca:
        raise HTTPException(status_code=404, detail="Marca não encontrada")
    return marca


@router.patch("/{marca_id}/titularidade")
async def transferir_titularidade(
    marca_id: str,
    dados: TransferirTitularidade,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """
    Transfere marcas.dono_user_id — endpoint dedicado, não reaproveita
    PATCH /{marca_id} (docs/PERMISSOES_SPEC.md §7). Regras (decisão #11):
    só o titular atual ou super iniciam; só pra alguém que já tenha
    vínculo admin ativo nesta marca; o titular antigo mantém o vínculo
    admin (isto não revoga acesso, só muda quem é o titular).
    """
    marca = await marca_repo.buscar_por_id(pool, marca_id)
    if not marca:
        raise HTTPException(status_code=404, detail="Marca não encontrada")

    dono_atual_id = await marca_repo.buscar_dono_user_id(pool, marca_id)

    if not admin.super:
        if admin.user_id is None or dono_atual_id is None or str(admin.user_id) != str(dono_atual_id):
            raise HTTPException(
                status_code=403,
                detail="Só o titular atual da marca ou super-admin pode transferir a titularidade",
            )

    usuario = await auth_repo.buscar_usuario_por_email(pool, dados.email.lower().strip())
    if not usuario:
        raise HTTPException(
            status_code=404,
            detail="Essa pessoa ainda não tem conta — ela precisa logar pelo menos uma vez "
                   "(Google ou Magic Link) com esse e-mail antes de virar titular.",
        )

    if dono_atual_id and str(usuario["id"]) == str(dono_atual_id):
        raise HTTPException(status_code=422, detail="Essa pessoa já é a titular da marca")

    tem_vinculo = await admin_vinculo_repo.tem_vinculo_admin_ativo(pool, usuario["id"], marca_id)
    if not tem_vinculo:
        raise HTTPException(
            status_code=422,
            detail="A nova titular precisa já ter vínculo admin ativo nesta marca — "
                   "conceda o vínculo antes de transferir a titularidade.",
        )

    atualizada = await marca_repo.transferir_titularidade(pool, marca_id, usuario["id"])

    await admin_vinculo_repo.registrar_auditoria(
        pool, acao="titularidade_transferida", user_alvo_id=usuario["id"],
        realizado_por=admin.identificador, marca_id=marca_id, nivel=None,
        detalhes={"dono_anterior": dono_atual_id},
    )
    return atualizada


@router.get("/{marca_id}/eventos")
async def listar_eventos_da_marca(
    marca_id: str,
    pool=Depends(get_pool),
    _=Depends(require_admin),
):
    """Eventos vinculados a esta marca (o vínculo em si é feito via
    PATCH /api/admin/eventos/{id}, atualizando eventos.marca_id)."""
    return await marca_repo.listar_eventos_da_marca(pool, marca_id)


# ── Parcerias entre marcas (docs/RANKINGS_CONFIGURAVEIS_SPEC.md §2.2) ──

async def _resolver_marca_ou_404(pool, marca_id: str) -> dict:
    marca = await marca_repo.buscar_por_id(pool, marca_id)
    if not marca:
        raise HTTPException(status_code=404, detail="Marca não encontrada")
    return marca


@router.get("/{marca_id}/parcerias")
async def listar_parcerias(
    marca_id: str,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """concedidas: marcas pra quem esta marca libera o próprio placar.
    recebidas: marcas que liberam o placar delas pra esta (com flag
    'reciproca' indicando se já foi aceita de volta)."""
    await _resolver_marca_ou_404(pool, marca_id)
    _exigir_admin_na_marca(admin, marca_id)
    return {
        "concedidas": await parceria_repo.listar_concedidas(pool, marca_id),
        "recebidas": await parceria_repo.listar_recebidas(pool, marca_id),
    }


@router.post("/{marca_id}/parcerias/{destino_id}/liberar", status_code=201)
async def liberar_parceria(
    marca_id: str,
    destino_id: str,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """
    marca_id (origem) libera o próprio placar pra destino_id ver em
    modo_ranking=marca_parceiras — efeito imediato, sem exigir aceite
    pra já valer nesse sentido (decisão #5). destino_id só reciprocar
    (ver /aceitar) fecha a mutualidade (decisão #2).
    """
    if marca_id == destino_id:
        raise HTTPException(status_code=422, detail="Uma marca não pode fazer parceria consigo mesma")
    await _resolver_marca_ou_404(pool, marca_id)
    await _resolver_marca_ou_404(pool, destino_id)
    _exigir_admin_na_marca(admin, marca_id)

    parceria = await parceria_repo.criar_ou_reativar(pool, marca_id, destino_id)
    await admin_vinculo_repo.registrar_auditoria(
        pool, acao="parceria_liberada", user_alvo_id=admin.user_id,
        realizado_por=admin.identificador, marca_id=marca_id, nivel=None,
        detalhes={"marca_destino_id": destino_id},
    )
    return parceria


@router.post("/{marca_id}/parcerias/{origem_id}/aceitar", status_code=201)
async def aceitar_parceria(
    marca_id: str,
    origem_id: str,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """
    marca_id aceita uma liberação recebida de origem_id — cria a linha
    recíproca marca_id→origem_id, fechando a mutualidade (decisão #2).
    Exige que origem_id→marca_id exista e esteja ativa; senão não há
    o que aceitar.
    """
    if marca_id == origem_id:
        raise HTTPException(status_code=422, detail="Uma marca não pode fazer parceria consigo mesma")
    await _resolver_marca_ou_404(pool, marca_id)
    await _resolver_marca_ou_404(pool, origem_id)
    _exigir_admin_na_marca(admin, marca_id)

    liberacao = await parceria_repo.buscar(pool, origem_id, marca_id)
    if not liberacao or not liberacao["ativo"]:
        raise HTTPException(
            status_code=422,
            detail="Não há liberação ativa dessa marca pra aceitar",
        )

    parceria = await parceria_repo.criar_ou_reativar(pool, marca_id, origem_id)
    await admin_vinculo_repo.registrar_auditoria(
        pool, acao="parceria_aceita", user_alvo_id=admin.user_id,
        realizado_por=admin.identificador, marca_id=marca_id, nivel=None,
        detalhes={"marca_origem_id": origem_id},
    )
    return parceria


@router.post("/{marca_id}/parcerias/{destino_id}/revogar")
async def revogar_parceria(
    marca_id: str,
    destino_id: str,
    pool=Depends(get_pool),
    admin: AdminContext = Depends(require_admin),
):
    """Revoga só a própria concessão marca_id→destino_id — não afeta a
    linha recíproca, que pode ficar assimétrica (decisão #5)."""
    await _resolver_marca_ou_404(pool, marca_id)
    _exigir_admin_na_marca(admin, marca_id)

    parceria = await parceria_repo.revogar(pool, marca_id, destino_id)
    if not parceria:
        raise HTTPException(status_code=404, detail="Não há liberação ativa dessa marca pra essa marca destino")

    await admin_vinculo_repo.registrar_auditoria(
        pool, acao="parceria_revogada", user_alvo_id=admin.user_id,
        realizado_por=admin.identificador, marca_id=marca_id, nivel=None,
        detalhes={"marca_destino_id": destino_id},
    )
    return parceria
