"""
Testes de services/exclusao_conta.py — orquestração da exclusão de
conta (docs/EXCLUSAO_CONTA_SPEC.md).
"""
import uuid
from datetime import datetime, timedelta, timezone
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import services.exclusao_conta as exclusao_svc


def make_uuid():
    return str(uuid.uuid4())


# ── solicitar ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_solicitar_bloqueia_se_dono_de_marca():
    pool = MagicMock()
    marcas = [{"id": "m1", "nome": "Canal3"}]

    with patch("repositories.marca.listar_onde_e_dono", AsyncMock(return_value=marcas)):
        with pytest.raises(exclusao_svc.ExclusaoBloqueadaTitularidadeError) as exc:
            await exclusao_svc.solicitar(pool, "u1")

    assert "Canal3" in str(exc.value)
    assert exc.value.marcas == marcas


@pytest.mark.asyncio
async def test_solicitar_sucesso_sem_titularidade():
    pool = MagicMock()
    resultado_esperado = {"id": "u1", "exclusao_solicitada_em": "2026-01-01"}

    with patch("repositories.marca.listar_onde_e_dono", AsyncMock(return_value=[])), \
         patch("repositories.usuario.solicitar_exclusao", AsyncMock(return_value=resultado_esperado)):
        resultado = await exclusao_svc.solicitar(pool, "u1")

    assert resultado == resultado_esperado


@pytest.mark.asyncio
async def test_solicitar_idempotente_ja_pendente_devolve_estado_atual():
    """solicitar_exclusao no repo retorna None quando já havia
    solicitação em andamento — o service busca o estado atual em vez
    de propagar erro."""
    pool = MagicMock()
    estado_atual = {"id": "u1", "status": "ativo", "exclusao_solicitada_em": "2026-01-01"}

    with patch("repositories.marca.listar_onde_e_dono", AsyncMock(return_value=[])), \
         patch("repositories.usuario.solicitar_exclusao", AsyncMock(return_value=None)), \
         patch("repositories.usuario.buscar_para_exclusao", AsyncMock(return_value=estado_atual)):
        resultado = await exclusao_svc.solicitar(pool, "u1")

    assert resultado == estado_atual


# ── cancelar ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cancelar_delega_pro_repository():
    pool = MagicMock()
    resultado_esperado = {"id": "u1", "exclusao_solicitada_em": None}

    with patch("repositories.usuario.cancelar_exclusao", AsyncMock(return_value=resultado_esperado)):
        resultado = await exclusao_svc.cancelar(pool, "u1")

    assert resultado == resultado_esperado


# ── processar ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_processar_bloqueia_se_dono_de_marca():
    pool = MagicMock()
    marcas = [{"id": "m1", "nome": "Canal3"}]

    with patch("repositories.marca.listar_onde_e_dono", AsyncMock(return_value=marcas)):
        with pytest.raises(exclusao_svc.ExclusaoBloqueadaTitularidadeError):
            await exclusao_svc.processar(pool, "u1")


@pytest.mark.asyncio
async def test_processar_sem_solicitacao_pendente_levanta_erro():
    pool = MagicMock()
    usuario = {"id": "u1", "email": "p@x.com", "status": "ativo", "exclusao_solicitada_em": None}

    with patch("repositories.marca.listar_onde_e_dono", AsyncMock(return_value=[])), \
         patch("repositories.usuario.buscar_para_exclusao", AsyncMock(return_value=usuario)):
        with pytest.raises(exclusao_svc.ExclusaoNaoElegivelError):
            await exclusao_svc.processar(pool, "u1")


@pytest.mark.asyncio
async def test_processar_ja_excluido_levanta_erro():
    pool = MagicMock()
    usuario = {"id": "u1", "email": None, "status": "excluido", "exclusao_solicitada_em": None}

    with patch("repositories.marca.listar_onde_e_dono", AsyncMock(return_value=[])), \
         patch("repositories.usuario.buscar_para_exclusao", AsyncMock(return_value=usuario)):
        with pytest.raises(exclusao_svc.ExclusaoNaoElegivelError):
            await exclusao_svc.processar(pool, "u1")


@pytest.mark.asyncio
async def test_processar_dentro_da_janela_bloqueia():
    pool = MagicMock()
    usuario = {
        "id": "u1", "email": "p@x.com", "status": "ativo",
        # +1s de folga garante .days == 10 (não 9) independente do
        # instante exato em que o teste roda.
        "exclusao_solicitada_em": datetime.now(timezone.utc) - timedelta(days=10, seconds=1),
    }

    with patch("repositories.marca.listar_onde_e_dono", AsyncMock(return_value=[])), \
         patch("repositories.usuario.buscar_para_exclusao", AsyncMock(return_value=usuario)):
        with pytest.raises(exclusao_svc.ExclusaoJanelaAbertaError) as exc:
            await exclusao_svc.processar(pool, "u1")

    assert "20 dia" in str(exc.value)


@pytest.mark.asyncio
async def test_processar_fora_da_janela_anonimiza_e_revoga_tudo():
    class _FakeTxn:
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass

    class _FakeConn:
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass
        def transaction(self): return _FakeTxn()

    conn = _FakeConn()
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=conn)

    usuario = {
        "id": "u1", "email": "p@x.com", "status": "ativo",
        "exclusao_solicitada_em": datetime.now(timezone.utc) - timedelta(days=31),
    }
    resultado_anonimizado = {"id": "u1", "status": "excluido"}

    with patch("repositories.marca.listar_onde_e_dono", AsyncMock(return_value=[])), \
         patch("repositories.usuario.buscar_para_exclusao", AsyncMock(return_value=usuario)), \
         patch("repositories.usuario.anonimizar", AsyncMock(return_value=resultado_anonimizado)) as anonimizar_mock, \
         patch("auth.repository.revogar_todas_sessoes_usuario", AsyncMock()) as sessoes_mock, \
         patch("repositories.admin_vinculo.revogar_todos_do_usuario", AsyncMock()) as vinculos_mock:
        resultado = await exclusao_svc.processar(pool, "u1")

    assert resultado == resultado_anonimizado
    anonimizar_mock.assert_called_once_with(conn, "u1", "p@x.com")
    sessoes_mock.assert_called_once_with(conn, "u1")
    vinculos_mock.assert_called_once_with(conn, "u1")


@pytest.mark.asyncio
async def test_processar_virou_dono_depois_de_solicitar_bloqueia():
    """Checagem de titularidade repetida no momento de processar — a
    pessoa pode ter virado dono_user_id de uma marca nova depois de já
    ter pedido a exclusão (achado do PERMISSOES_SPEC.md aplicado aqui)."""
    pool = MagicMock()
    marcas = [{"id": "m1", "nome": "Marca Nova"}]

    with patch("repositories.marca.listar_onde_e_dono", AsyncMock(return_value=marcas)), \
         patch("repositories.usuario.buscar_para_exclusao", AsyncMock()) as buscar_mock:
        with pytest.raises(exclusao_svc.ExclusaoBloqueadaTitularidadeError):
            await exclusao_svc.processar(pool, "u1")

    buscar_mock.assert_not_called()  # bloqueia antes até de olhar o estado da exclusão
