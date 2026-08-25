"""
Testes de auth/service.py — a lógica de negócio mais crítica:
account linking (AUTH_SPEC.md §4.1) e reivindicação de nick (§3, §4.3).

Testados com fake_pool/mocks — não é integração real com banco,
mas cobre exatamente as regras de decisão que importam.
"""
import uuid
import pytest
from unittest.mock import AsyncMock, patch

import auth.service as auth_svc
import auth.repository as auth_repo


def make_uuid():
    return str(uuid.uuid4())


def _usuario(user_id=None, email="pessoa@example.com", email_verified=True):
    return {
        "id": user_id or make_uuid(), "email": email, "email_verified": email_verified,
        "nome": "Pessoa Teste", "foto_url": None, "status": "ativo",
        "criado_em": "2026-01-01", "ultimo_login_em": None,
    }


def _identity(user_id, provider="google", provider_user_id="google-sub-1"):
    return {
        "id": make_uuid(), "user_id": user_id, "provider": provider,
        "provider_user_id": provider_user_id, "email": "pessoa@example.com",
        "criado_em": "2026-01-01",
    }


# ── Account linking (AUTH_SPEC.md §4.1) ───────────────────────────────────────

@pytest.mark.asyncio
async def test_identity_ja_existe_so_faz_login(fake_pool):
    """Segunda vez que a mesma conta Google loga: não cria nada novo,
    só busca o usuário já vinculado e atualiza último login."""
    usuario = _usuario()
    identity = _identity(usuario["id"])

    with patch("auth.repository.buscar_identity", AsyncMock(return_value=identity)), \
         patch("auth.repository.buscar_usuario_por_id", AsyncMock(return_value=usuario)), \
         patch("auth.repository.atualizar_ultimo_login", AsyncMock()) as atualizar_mock, \
         patch("auth.repository.criar_usuario") as criar_mock, \
         patch("auth.repository.criar_identity") as criar_identity_mock:
        resultado = await auth_svc.login_ou_criar_usuario(
            fake_pool, provider="google", provider_user_id="google-sub-1",
            email="pessoa@example.com", email_verified=True,
        )

    assert resultado["id"] == usuario["id"]
    atualizar_mock.assert_called_once()
    criar_mock.assert_not_called()
    criar_identity_mock.assert_not_called()


@pytest.mark.asyncio
async def test_email_verificado_linka_automaticamente_conta_existente(fake_pool):
    """
    Decisão #2 do AUTH_SPEC.md: conta existente com o mesmo e-mail,
    login por um provedor novo, email_verified=true -> linka
    automaticamente, sem criar usuário duplicado.
    """
    usuario_existente = _usuario(email="pessoa@example.com")

    with patch("auth.repository.buscar_identity", AsyncMock(return_value=None)), \
         patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=usuario_existente)), \
         patch("auth.repository.criar_identity", AsyncMock(return_value=_identity(usuario_existente["id"]))) as criar_identity_mock, \
         patch("auth.repository.atualizar_ultimo_login", AsyncMock()), \
         patch("auth.repository.criar_usuario") as criar_usuario_mock:
        resultado = await auth_svc.login_ou_criar_usuario(
            fake_pool, provider="magic_link", provider_user_id="pessoa@example.com",
            email="pessoa@example.com", email_verified=True,
        )

    assert resultado["id"] == usuario_existente["id"]
    criar_identity_mock.assert_called_once()
    criar_usuario_mock.assert_not_called()


@pytest.mark.asyncio
async def test_email_nao_verificado_nao_linka_cria_conta_nova(fake_pool):
    """
    Salvaguarda explícita da decisão #2: só linka automaticamente se
    o e-mail vier VERIFICADO pelo provedor. Sem isso, alguém poderia
    reivindicar a conta de outra pessoa só alegando o e-mail dela.
    """
    usuario_existente = _usuario(email="pessoa@example.com")
    novo_usuario = _usuario(email="pessoa@example.com")

    with patch("auth.repository.buscar_identity", AsyncMock(return_value=None)), \
         patch("auth.repository.buscar_usuario_por_email") as buscar_email_mock, \
         patch("auth.repository.criar_usuario", AsyncMock(return_value=novo_usuario)) as criar_mock, \
         patch("auth.repository.criar_identity", AsyncMock(return_value=_identity(novo_usuario["id"]))):
        resultado = await auth_svc.login_ou_criar_usuario(
            fake_pool, provider="google", provider_user_id="google-sub-2",
            email="pessoa@example.com", email_verified=False,
        )

    # Nem chega a checar se existe conta com esse e-mail — email_verified=False
    # bloqueia a possibilidade de linking automático de cara.
    buscar_email_mock.assert_not_called()
    criar_mock.assert_called_once()
    assert resultado["id"] == novo_usuario["id"]


@pytest.mark.asyncio
async def test_sem_conta_existente_cria_usuario_novo(fake_pool):
    novo_usuario = _usuario(email="novato@example.com")

    with patch("auth.repository.buscar_identity", AsyncMock(return_value=None)), \
         patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=None)), \
         patch("auth.repository.criar_usuario", AsyncMock(return_value=novo_usuario)) as criar_mock, \
         patch("auth.repository.criar_identity", AsyncMock(return_value=_identity(novo_usuario["id"]))) as criar_identity_mock:
        resultado = await auth_svc.login_ou_criar_usuario(
            fake_pool, provider="google", provider_user_id="google-sub-3",
            email="novato@example.com", email_verified=True, nome="Novato",
        )

    criar_mock.assert_called_once()
    criar_identity_mock.assert_called_once()
    assert resultado["id"] == novo_usuario["id"]


@pytest.mark.asyncio
async def test_email_normalizado_para_lowercase(fake_pool):
    """E-mail é normalizado (lowercase/trim) antes de qualquer busca,
    pra 'Pessoa@Example.com' e 'pessoa@example.com' serem a mesma conta."""
    with patch("auth.repository.buscar_identity", AsyncMock(return_value=None)), \
         patch("auth.repository.buscar_usuario_por_email", AsyncMock(return_value=None)) as buscar_mock, \
         patch("auth.repository.criar_usuario", AsyncMock(return_value=_usuario())), \
         patch("auth.repository.criar_identity", AsyncMock()):
        await auth_svc.login_ou_criar_usuario(
            fake_pool, provider="google", provider_user_id="x",
            email="  Pessoa@Example.COM  ", email_verified=True,
        )

    buscar_mock.assert_called_once_with(fake_pool, "pessoa@example.com")


# ── Reivindicação de nick (AUTH_SPEC.md §3, §4.3; NICKNAME_SPEC.md) ────────────

@pytest.mark.asyncio
async def test_anonimo_nick_livre_segue_sem_reivindicar(fake_pool):
    """Envio anônimo com nick nunca usado: comportamento inalterado,
    não cria claim nenhum (claim só nasce de login real)."""
    with patch("auth.repository.buscar_nick_claim", AsyncMock(return_value=None)), \
         patch("auth.repository.criar_nick_claim") as criar_mock:
        await auth_svc.verificar_e_reivindicar_nick(fake_pool, "Novato", "novato", user_id=None)

    criar_mock.assert_not_called()


@pytest.mark.asyncio
async def test_anonimo_nick_ja_reivindicado_bloqueia(fake_pool):
    claim = {"id": make_uuid(), "nick": "Campeao", "nick_norm": "campeao", "user_id": make_uuid(), "ativo": True, "criado_em": "2026-01-01"}

    with patch("auth.repository.buscar_nick_claim", AsyncMock(return_value=claim)):
        with pytest.raises(auth_svc.NickJaReivindicadoError):
            await auth_svc.verificar_e_reivindicar_nick(fake_pool, "Campeao", "campeao", user_id=None)


@pytest.mark.asyncio
async def test_logado_nick_livre_reivindica(fake_pool):
    """Primeira reivindicação de sempre desse nick_norm — decisão #11:
    vincula retroativamente pontuações órfãs com esse nick."""
    user_id = make_uuid()
    with patch("auth.repository.buscar_nick_claim", AsyncMock(return_value=None)), \
         patch("auth.repository.nick_ja_foi_reivindicado_alguma_vez", AsyncMock(return_value=False)), \
         patch("auth.repository.criar_nick_claim", AsyncMock()) as criar_mock, \
         patch("repositories.entrada.vincular_retroativamente", AsyncMock()) as vincular_mock, \
         patch("repositories.entrada.marcar_pendente_identificacao_ambigua", AsyncMock()) as marcar_mock:
        await auth_svc.verificar_e_reivindicar_nick(fake_pool, "Novato", "novato", user_id=user_id)

    criar_mock.assert_called_once_with(fake_pool, "Novato", "novato", user_id)
    vincular_mock.assert_called_once_with(fake_pool, "novato", user_id)
    marcar_mock.assert_not_called()


@pytest.mark.asyncio
async def test_logado_nick_liberado_reivindicado_de_novo_nao_vincula_so_sinaliza(fake_pool):
    """Decisão #7: nick já teve dono antes (foi liberado) — NÃO vincula
    pontuações antigas automaticamente, só sinaliza pra revisão."""
    user_id = make_uuid()
    with patch("auth.repository.buscar_nick_claim", AsyncMock(return_value=None)), \
         patch("auth.repository.nick_ja_foi_reivindicado_alguma_vez", AsyncMock(return_value=True)), \
         patch("auth.repository.criar_nick_claim", AsyncMock()), \
         patch("repositories.entrada.vincular_retroativamente", AsyncMock()) as vincular_mock, \
         patch("repositories.entrada.marcar_pendente_identificacao_ambigua", AsyncMock()) as marcar_mock:
        await auth_svc.verificar_e_reivindicar_nick(fake_pool, "Veterano", "veterano", user_id=user_id)

    vincular_mock.assert_not_called()
    marcar_mock.assert_called_once_with(fake_pool, "veterano")


@pytest.mark.asyncio
async def test_logado_nick_ja_e_seu_segue_normal(fake_pool):
    user_id = make_uuid()
    claim = {"id": make_uuid(), "nick": "Campeao", "nick_norm": "campeao", "user_id": user_id, "ativo": True, "criado_em": "2026-01-01"}

    with patch("auth.repository.buscar_nick_claim", AsyncMock(return_value=claim)), \
         patch("auth.repository.criar_nick_claim") as criar_mock:
        # Não deve levantar exceção nenhuma
        await auth_svc.verificar_e_reivindicar_nick(fake_pool, "Campeao", "campeao", user_id=user_id)

    criar_mock.assert_not_called()


@pytest.mark.asyncio
async def test_logado_nick_de_outro_usuario_bloqueia(fake_pool):
    dono_id = make_uuid()
    outro_id = make_uuid()
    claim = {"id": make_uuid(), "nick": "Campeao", "nick_norm": "campeao", "user_id": dono_id, "ativo": True, "criado_em": "2026-01-01"}

    with patch("auth.repository.buscar_nick_claim", AsyncMock(return_value=claim)):
        with pytest.raises(auth_svc.NickJaReivindicadoError):
            await auth_svc.verificar_e_reivindicar_nick(fake_pool, "Campeao", "campeao", user_id=outro_id)


# ── trocar_nick (troca deliberada no perfil, NICKNAME_SPEC.md) ─────────────────

@pytest.mark.asyncio
async def test_trocar_nick_primeira_vez_sem_cooldown(fake_pool):
    """Sem claim atual (primeira reivindicação de conta nova) — nunca
    conta como troca, sem checagem de cooldown, nada a liberar."""
    user_id = make_uuid()
    nova_claim = {"id": make_uuid(), "nick": "Estreante", "nick_norm": "estreante", "user_id": user_id, "ativo": True, "criado_em": "2026-01-01"}

    with patch("auth.repository.buscar_claim_ativo_do_usuario", AsyncMock(return_value=None)), \
         patch("auth.repository.buscar_nick_claim", AsyncMock(return_value=None)), \
         patch("auth.repository.nick_ja_foi_reivindicado_alguma_vez", AsyncMock(return_value=False)), \
         patch("auth.repository.liberar_claim", AsyncMock()) as liberar_mock, \
         patch("auth.repository.criar_nick_claim", AsyncMock(return_value=nova_claim)), \
         patch("repositories.entrada.vincular_retroativamente", AsyncMock()):
        resultado = await auth_svc.trocar_nick(fake_pool, user_id, "Estreante")

    liberar_mock.assert_not_called()
    assert resultado == nova_claim


@pytest.mark.asyncio
async def test_trocar_nick_mesmo_nick_atual_e_no_op(fake_pool):
    user_id = make_uuid()
    claim_atual = {"id": make_uuid(), "nick": "Campeao", "nick_norm": "campeao", "user_id": user_id, "ativo": True, "criado_em": "2026-01-01", "em_cooldown": True}

    with patch("auth.repository.buscar_claim_ativo_do_usuario", AsyncMock(return_value=claim_atual)), \
         patch("auth.repository.criar_nick_claim") as criar_mock:
        resultado = await auth_svc.trocar_nick(fake_pool, user_id, "Campeao")

    criar_mock.assert_not_called()
    assert resultado == claim_atual


@pytest.mark.asyncio
async def test_trocar_nick_em_cooldown_bloqueia(fake_pool):
    user_id = make_uuid()
    claim_atual = {"id": make_uuid(), "nick": "Campeao", "nick_norm": "campeao", "user_id": user_id, "ativo": True, "criado_em": "2026-01-01", "em_cooldown": True}

    with patch("auth.repository.buscar_claim_ativo_do_usuario", AsyncMock(return_value=claim_atual)):
        with pytest.raises(auth_svc.NickTrocaEmCooldownError):
            await auth_svc.trocar_nick(fake_pool, user_id, "NovoNick")


@pytest.mark.asyncio
async def test_trocar_nick_fora_do_cooldown_libera_e_reivindica(fake_pool):
    user_id = make_uuid()
    claim_atual = {"id": make_uuid(), "nick": "Campeao", "nick_norm": "campeao", "user_id": user_id, "ativo": True, "criado_em": "2026-01-01", "em_cooldown": False}
    nova_claim = {"id": make_uuid(), "nick": "NovoNick", "nick_norm": "novonick", "user_id": user_id, "ativo": True, "criado_em": "2026-02-01"}

    with patch("auth.repository.buscar_claim_ativo_do_usuario", AsyncMock(return_value=claim_atual)), \
         patch("auth.repository.buscar_nick_claim", AsyncMock(return_value=None)), \
         patch("auth.repository.nick_ja_foi_reivindicado_alguma_vez", AsyncMock(return_value=False)), \
         patch("auth.repository.liberar_claim", AsyncMock()) as liberar_mock, \
         patch("auth.repository.criar_nick_claim", AsyncMock(return_value=nova_claim)), \
         patch("repositories.entrada.vincular_retroativamente", AsyncMock()):
        resultado = await auth_svc.trocar_nick(fake_pool, user_id, "NovoNick")

    liberar_mock.assert_called_once_with(fake_pool, claim_atual["id"])
    assert resultado == nova_claim


@pytest.mark.asyncio
async def test_trocar_nick_colisao_com_outro_dono_bloqueia(fake_pool):
    user_id = make_uuid()
    outro_id = make_uuid()
    claim_atual = {"id": make_uuid(), "nick": "Campeao", "nick_norm": "campeao", "user_id": user_id, "ativo": True, "criado_em": "2026-01-01", "em_cooldown": False}
    colisao = {"id": make_uuid(), "nick": "Ocupado", "nick_norm": "ocupado", "user_id": outro_id, "ativo": True, "criado_em": "2026-01-01"}

    with patch("auth.repository.buscar_claim_ativo_do_usuario", AsyncMock(return_value=claim_atual)), \
         patch("auth.repository.buscar_nick_claim", AsyncMock(return_value=colisao)):
        with pytest.raises(auth_svc.NickJaReivindicadoError):
            await auth_svc.trocar_nick(fake_pool, user_id, "Ocupado")


@pytest.mark.asyncio
async def test_trocar_nick_ignorar_cooldown_usado_por_forca_troca(fake_pool):
    """ignorar_cooldown=True (usado só pela troca forçada por
    admin/moderador) libera mesmo dentro da janela de 30 dias."""
    user_id = make_uuid()
    claim_atual = {"id": make_uuid(), "nick": "Ofensivo", "nick_norm": "ofensivo", "user_id": user_id, "ativo": True, "criado_em": "2026-01-01", "em_cooldown": True}
    nova_claim = {"id": make_uuid(), "nick": "Corrigido", "nick_norm": "corrigido", "user_id": user_id, "ativo": True, "criado_em": "2026-01-02"}

    with patch("auth.repository.buscar_claim_ativo_do_usuario", AsyncMock(return_value=claim_atual)), \
         patch("auth.repository.buscar_nick_claim", AsyncMock(return_value=None)), \
         patch("auth.repository.nick_ja_foi_reivindicado_alguma_vez", AsyncMock(return_value=False)), \
         patch("auth.repository.liberar_claim", AsyncMock()), \
         patch("auth.repository.criar_nick_claim", AsyncMock(return_value=nova_claim)), \
         patch("repositories.entrada.vincular_retroativamente", AsyncMock()):
        resultado = await auth_svc.trocar_nick(fake_pool, user_id, "Corrigido", ignorar_cooldown=True)

    assert resultado == nova_claim


# ── Magic Link — geração e hash do token ───────────────────────────────────────

def test_token_magic_link_nunca_expoe_o_hash_como_o_proprio_token():
    token, token_hash = auth_svc.gerar_token_magic_link()
    assert token != token_hash
    assert len(token) >= 32
    assert len(token_hash) == 64  # sha256 hex digest


def test_token_magic_link_e_aleatorio_a_cada_chamada():
    token1, _ = auth_svc.gerar_token_magic_link()
    token2, _ = auth_svc.gerar_token_magic_link()
    assert token1 != token2


# ── sessao_obrigatoria — dependency pra rotas que exigem login ─────────────────

@pytest.mark.asyncio
async def test_sessao_obrigatoria_com_usuario_retorna_o_usuario():
    usuario = {"id": "u1", "email": "p@x.com"}
    resultado = await auth_svc.sessao_obrigatoria(usuario=usuario)
    assert resultado == usuario


@pytest.mark.asyncio
async def test_sessao_obrigatoria_sem_usuario_levanta_401():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await auth_svc.sessao_obrigatoria(usuario=None)
    assert exc.value.status_code == 401
