"""
Testes de services/game_admissao.py — colisão de nome no cadastro
manual de jogo (docs/CATALOGO_JOGOS_SPEC.md 5.6). Função pura, sem
banco.
"""
import services.game_admissao as admissao


def test_avaliar_colisao_sem_existentes_nunca_bloqueia():
    resultado = admissao.avaliar_colisao("Qualquer Jogo", [])
    assert resultado.bloqueado is False


def test_avaliar_colisao_bloqueia_correspondencia_exata():
    existentes = [{"nome": "Pac-Man"}]
    resultado = admissao.avaliar_colisao("pac-man", existentes)
    assert resultado.bloqueado is True
    assert "Pac-Man" in resultado.motivo


def test_avaliar_colisao_bloqueia_substring():
    existentes = [{"nome": "Street Fighter II"}]
    resultado = admissao.avaliar_colisao("Street Fighter II Turbo", existentes)
    assert resultado.bloqueado is True


def test_avaliar_colisao_nao_bloqueia_nomes_realmente_diferentes():
    existentes = [{"nome": "Pac-Man"}]
    resultado = admissao.avaliar_colisao("Galaga", existentes)
    assert resultado.bloqueado is False


def test_avaliar_colisao_nao_tem_heuristica_de_suspeito():
    """Diferente de arena_admissao.avaliar_admissao, este módulo não
    tem conceito de 'suspeito' — só bloqueado ou não (pendente_aprovacao
    já cumpre esse papel pro caminho manual de jogo)."""
    resultado = admissao.avaliar_colisao("Qualquer Jogo", [])
    assert not hasattr(resultado, "suspeito")
