"""
Router admin de marcas — requer autenticação.
Prefixo: /api/admin/marcas

Ver docs/MARCAS_SPEC.md §3: marca é o nível acima de evento — cor
primária, tipografia e logo herdam pra evento quando o evento não
define os seus (evento → marca → default da plataforma).
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
import repositories.marca as marca_repo
from utils.db import get_pool
from middleware.auth import require_admin

router = APIRouter(prefix="/api/admin/marcas", tags=["admin-marcas"])

TIPOGRAFIAS_VALIDAS = {"arcade", "futurista", "terminal"}


def _validar_tipografia(v):
    if v is not None and v not in TIPOGRAFIAS_VALIDAS:
        raise ValueError(f"tipografia deve ser uma de {sorted(TIPOGRAFIAS_VALIDAS)}")
    return v


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

    _valida_tipografia = field_validator("tipografia")(_validar_tipografia)


# ── CRUD de marcas ─────────────────────────────────────────────

@router.get("")
async def listar_marcas(pool=Depends(get_pool), _=Depends(require_admin)):
    return await marca_repo.listar_todas(pool)


@router.post("", status_code=201)
async def criar_marca(
    dados: MarcaCreate,
    pool=Depends(get_pool),
    _=Depends(require_admin),
):
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
    _=Depends(require_admin),
):
    marca = await marca_repo.atualizar(pool, marca_id, dados.model_dump(exclude_none=True))
    if not marca:
        raise HTTPException(status_code=404, detail="Marca não encontrada")
    return marca


@router.get("/{marca_id}/eventos")
async def listar_eventos_da_marca(
    marca_id: str,
    pool=Depends(get_pool),
    _=Depends(require_admin),
):
    """Eventos vinculados a esta marca (o vínculo em si é feito via
    PATCH /api/admin/eventos/{id}, atualizando eventos.marca_id)."""
    return await marca_repo.listar_eventos_da_marca(pool, marca_id)
