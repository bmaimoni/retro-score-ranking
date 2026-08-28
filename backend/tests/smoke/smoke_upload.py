"""
Smoke tests: tela de upload (index.html)
Cobrem: carregamento, seleção de game, tema aplicado, formulário e envio.
"""
import pytest
from playwright.sync_api import Page, expect
from conftest import DEFAULT_TIMEOUT


@pytest.fixture(autouse=True)
def set_timeout(page: Page):
    page.set_default_timeout(30_000)


def test_pagina_carrega_lista_de_games(page: Page, base_url: str):
    """A página de upload deve exibir pelo menos um game após carregar."""
    page.goto(f"{base_url}/index.html")
    # Aguarda skeleton sumir e games reais aparecerem (fetch assíncrono)
    page.wait_for_selector(".game-card", timeout=30_000)
    games = page.locator(".game-card")
    expect(games.first).to_be_visible()
    assert games.count() >= 1


def test_games_tem_nome_e_icone(page: Page, base_url: str):
    """Cada card de game deve ter nome e ícone visíveis."""
    page.goto(f"{base_url}/index.html")
    page.locator(".game-card").first.wait_for(timeout=30_000)
    primeiro = page.locator(".game-card").first
    expect(primeiro.locator(".game-nome")).to_be_visible()
    expect(primeiro.locator(".game-icone")).to_be_visible()


def test_selecionar_game_expande_card(page: Page, base_url: str):
    """Clicar em um game deve expandir o card com o formulário."""
    page.goto(f"{base_url}/index.html")
    page.locator(".game-card").first.wait_for(timeout=30_000)
    page.locator(".game-header").first.click()
    expect(page.locator(".card-form").first).to_be_visible(timeout=5_000)


def test_card_expandido_tem_campos_de_formulario(page: Page, base_url: str):
    """O formulário expandido deve ter campos nick, score e consentimento."""
    page.goto(f"{base_url}/index.html")
    page.locator(".game-card").first.wait_for(timeout=30_000)
    page.locator(".game-header").first.click()
    page.locator(".card-form").first.wait_for(timeout=5_000)

    # Pega o id do primeiro game
    game_id = page.locator(".game-card").first.get_attribute("id").replace("card-", "")
    expect(page.locator(f"#nick-{game_id}")).to_be_visible()
    expect(page.locator(f"#score-{game_id}")).to_be_visible()
    expect(page.locator(f"#consent-{game_id}")).to_be_visible()


def test_outros_cards_ficam_esmaecidos_ao_expandir(page: Page, base_url: str):
    """Quando um card está expandido, os demais devem ter opacidade reduzida."""
    page.goto(f"{base_url}/index.html")
    games = page.locator(".game-card")
    games.first.wait_for(timeout=30_000)

    if games.count() < 2:
        pytest.skip("Necessário ao menos 2 games para este teste")

    page.locator(".game-header").first.click()
    page.locator(".card-form").first.wait_for(timeout=5_000)

    # A lista deve ter a classe 'tem-expandido'
    classes = page.locator(".games-lista").get_attribute("class") or ""
    assert "tem-expandido" in classes


def test_clicar_em_outro_card_fecha_o_anterior(page: Page, base_url: str):
    """Selecionar um segundo game deve fechar o primeiro."""
    page.goto(f"{base_url}/index.html")
    headers = page.locator(".game-header")
    headers.first.wait_for(timeout=30_000)

    if headers.count() < 2:
        pytest.skip("Necessário ao menos 2 games para este teste")

    headers.first.click()
    page.locator(".card-form").first.wait_for(timeout=5_000)
    headers.nth(1).click()
    page.wait_for_timeout(600)  # aguarda animação

    primeiro_card = page.locator(".game-card").first
    assert "expandido" not in (primeiro_card.get_attribute("class") or "")


def test_envio_sem_preencher_campos_nao_submete(page: Page, base_url: str):
    """Submeter sem nick/score deve mostrar toast de erro, não sucesso."""
    page.goto(f"{base_url}/index.html")
    page.locator(".game-header").first.wait_for(timeout=30_000)
    page.locator(".game-header").first.click()
    page.locator(".card-form").first.wait_for(timeout=5_000)

    game_id = page.locator(".game-card").first.get_attribute("id").replace("card-", "")
    page.locator(f"#btn-{game_id}").click()

    expect(page.locator(".toast.error")).to_be_visible(timeout=3_000)
    expect(page.locator(".card-sucesso.visible")).not_to_be_visible()


def test_link_ver_ranking_existe(page: Page, base_url: str):
    """Deve haver link para o ranking na página de upload."""
    page.goto(f"{base_url}/index.html")
    link = page.locator("a.ranking-link")
    expect(link).to_be_visible()
    assert "ranking.html" in (link.get_attribute("href") or "")