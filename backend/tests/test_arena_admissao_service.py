"""
Testes de services/arena_admissao.py — colisão de nome/slug (B.2) e
heurística de risco (B.4) da Fase 8. Funções puras, sem banco —
testadas diretamente, sem mock de pool.
"""
import pytest
import services.arena_admissao as admissao


def test_normalizar_remove_acento_maiuscula_pontuacao():
    assert admissao.normalizar("Canal3 Expo!") == "canal3 expo"
    # hífen é removido sem virar espaço — "canal-3" e "canal3" comparam
    # igual, que é o comportamento desejado pra colisão de nome (B.2)
    assert admissao.normalizar("  Ção-Teste  ") == "caoteste"


def test_avaliar_admissao_bloqueia_correspondencia_exata():
    existentes = [{"nome": "Old School Pinball", "slug": "oldschool"}]
    resultado = admissao.avaliar_admissao("old school pinball", "algo-diferente", existentes)
    assert resultado.bloqueado is True
    assert "Old School Pinball" in resultado.motivo


def test_avaliar_admissao_bloqueia_substring():
    existentes = [{"nome": "Canal3", "slug": "canal3"}]
    resultado = admissao.avaliar_admissao("Canal3 Oficial", "canal3-oficial", existentes)
    assert resultado.bloqueado is True


def test_avaliar_admissao_bloqueia_contra_nome_fixo_canal3_mesmo_sem_arena_cadastrada():
    resultado = admissao.avaliar_admissao("Canal3", "canal3-novo", [])
    assert resultado.bloqueado is True


def test_avaliar_admissao_marca_suspeito_quando_quase_igual():
    """Distância de edição <= 2, mas não é substring/igual — não
    bloqueia, só marca suspeito (nasce draft, não published). 'Turbo
    Clash' vs 'Turbo Crash': troca 1 caractere no meio (l→r), nenhuma
    das duas é substring/prefixo da outra."""
    existentes = [{"nome": "Turbo Clash", "slug": "turbo-clash"}]
    resultado = admissao.avaliar_admissao("Turbo Crash", "turbo-crash", existentes)
    assert resultado.bloqueado is False
    assert resultado.suspeito is True


def test_avaliar_admissao_nome_bem_diferente_nao_bloqueia_nem_marca_suspeito():
    existentes = [{"nome": "Canal3", "slug": "canal3"}]
    resultado = admissao.avaliar_admissao("Campeonato de Sinuca dos Amigos", "sinuca-amigos", existentes)
    assert resultado.bloqueado is False
    assert resultado.suspeito is False


def test_sanitizar_logo_url_aceita_url_normal():
    assert admissao.sanitizar_logo_url("https://cdn.example.com/logo.png") == "https://cdn.example.com/logo.png"


def test_sanitizar_logo_url_aceita_none():
    assert admissao.sanitizar_logo_url(None) is None


@pytest.mark.parametrize("valor_hostil", [
    'https://x.com/a.png"><script>alert(1)</script>',
    "javascript:alert(1)",
    '" onerror="alert(1)',
    "<iframe src=evil.com>",
])
def test_sanitizar_logo_url_rejeita_vetores_xss(valor_hostil):
    with pytest.raises(ValueError):
        admissao.sanitizar_logo_url(valor_hostil)
