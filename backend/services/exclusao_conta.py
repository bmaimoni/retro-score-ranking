"""
Orquestração de exclusão de conta — docs/EXCLUSAO_CONTA_SPEC.md.

Sem HTTP aqui (fica em routers/perfil.py e routers/admin.py). Sem job
agendado (decisão registrada em EXCLUSAO_CONTA_SPEC.md §7, mesmo
princípio de NICKNAME_SPEC.md §4): processar a anonimização é ação
manual de super, não um relógio.
"""
from datetime import datetime, timezone

import auth.repository as auth_repo
import repositories.admin_vinculo as admin_vinculo_repo
import repositories.marca as marca_repo
import repositories.usuario as usuario_repo

JANELA_CANCELAMENTO_DIAS = 30


class ExclusaoBloqueadaTitularidadeError(Exception):
    """Pessoa é dono_user_id de alguma marca — precisa transferir a
    titularidade antes (decisão #5 do EXCLUSAO_CONTA_SPEC.md)."""

    def __init__(self, marcas: list[dict]):
        nomes = ", ".join(m["nome"] for m in marcas)
        super().__init__(
            f"Você é titular de {nomes} — transfira a titularidade antes de excluir a conta."
        )
        self.marcas = marcas


class ExclusaoNaoElegivelError(Exception):
    """Não há solicitação de exclusão pendente pra esse usuário."""


class ExclusaoJanelaAbertaError(Exception):
    """Ainda dentro dos 30 dias de cancelamento — não pode anonimizar ainda."""


async def solicitar(pool, user_id: str) -> dict:
    marcas = await marca_repo.listar_onde_e_dono(pool, user_id)
    if marcas:
        raise ExclusaoBloqueadaTitularidadeError(marcas)

    resultado = await usuario_repo.solicitar_exclusao(pool, user_id)
    if resultado is None:
        # Já havia solicitação em andamento (ou conta não está ativa) —
        # idempotente: devolve o estado atual em vez de erro.
        resultado = await usuario_repo.buscar_para_exclusao(pool, user_id)
    return resultado


async def cancelar(pool, user_id: str) -> dict | None:
    return await usuario_repo.cancelar_exclusao(pool, user_id)


async def processar(pool, user_id: str) -> dict:
    """
    Anonimização manual, disparada por super. Repete a checagem de
    titularidade no momento de processar (não só no de solicitar) —
    a pessoa pode ter se tornado dono_user_id de uma marca nova depois
    de já ter pedido a exclusão.
    """
    marcas = await marca_repo.listar_onde_e_dono(pool, user_id)
    if marcas:
        raise ExclusaoBloqueadaTitularidadeError(marcas)

    usuario = await usuario_repo.buscar_para_exclusao(pool, user_id)
    if not usuario or usuario["status"] != "ativo" or usuario["exclusao_solicitada_em"] is None:
        raise ExclusaoNaoElegivelError(
            "Não há solicitação de exclusão pendente para este usuário."
        )

    dias_passados = (datetime.now(timezone.utc) - usuario["exclusao_solicitada_em"]).days
    if dias_passados < JANELA_CANCELAMENTO_DIAS:
        faltam = JANELA_CANCELAMENTO_DIAS - dias_passados
        raise ExclusaoJanelaAbertaError(
            f"Ainda dentro da janela de cancelamento — faltam {faltam} dia(s)."
        )

    async with pool.acquire() as conn:
        async with conn.transaction():
            resultado = await usuario_repo.anonimizar(conn, user_id, usuario["email"])
            await auth_repo.revogar_todas_sessoes_usuario(conn, user_id)
            await admin_vinculo_repo.revogar_todos_do_usuario(conn, user_id)

    return resultado
