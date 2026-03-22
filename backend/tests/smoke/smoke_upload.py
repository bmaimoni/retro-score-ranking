"""
Smoke tests: tela de upload (index.html)
Cobrem: carregamento, seleção de jogo, tema aplicado, formulário e envio.
"""
import pytest
from playwright.sync_api import Page, expect
from conftest import DEFAULT_TIMEOUT


@pytest.fixture(autouse=True)
def set_timeout(page: Page):
    page.set_default_timeout(DEFAULT_TIMEOUT)


def test_pagina_carrega_lista_de_jogos(page: Page, base_url: str):
    """A página de upload deve exibir pelo menos um jogo após carregar."""
    page.goto(f"{base_url}/index.html")
    jogos = page.locator(".jogo-item")
    expect(jogos.first).to_be_visible(timeout=DEFAULT_TIMEOUT)
    assert jogos.count() >= 1


def test_jogos_tem_nome_e_icone(page: Page, base_url: str):
    """Cada card de jogo deve ter nome e ícone visíveis."""
    page.goto(f"{base_url}/index.html")
    page.locator(".jogo-item").first.wait_for(timeout=DEFAULT_TIMEOUT)
    primeiro = page.locator(".jogo-item").first
    expect(primeiro.locator(".jogo-nome")).to_be_visible()
    expect(primeiro.locator(".jogo-icone")).to_be_visible()


def test_selecionar_jogo_expande_card(page: Page, base_url: str):
    """Clicar em um jogo deve expandir o card com o formulário."""
    page.goto(f"{base_url}/index.html")
    page.locator(".jogo-item").first.wait_for(timeout=DEFAULT_TIMEOUT)
    page.locator(".jogo-header").first.click()
    expect(page.locator(".card-form").first).to_be_visible(timeout=5_000)


def test_card_expandido_tem_campos_de_formulario(page: Page, base_url: str):
    """O formulário expandido deve ter campos nick, score e consentimento."""
    page.goto(f"{base_url}/index.html")
    page.locator(".jogo-item").first.wait_for(timeout=DEFAULT_TIMEOUT)
    page.locator(".jogo-header").first.click()
    page.locator(".card-form").first.wait_for(timeout=5_000)

    # Pega o id do primeiro jogo
    jogo_id = page.locator(".jogo-item").first.get_attribute("id").replace("card-", "")
    expect(page.locator(f"#nick-{jogo_id}")).to_be_visible()
    expect(page.locator(f"#score-{jogo_id}")).to_be_visible()
    expect(page.locator(f"#consent-{jogo_id}")).to_be_visible()


def test_outros_cards_ficam_esmaecidos_ao_expandir(page: Page, base_url: str):
    """Quando um card está expandido, os demais devem ter opacidade reduzida."""
    page.goto(f"{base_url}/index.html")
    jogos = page.locator(".jogo-item")
    jogos.first.wait_for(timeout=DEFAULT_TIMEOUT)

    if jogos.count() < 2:
        pytest.skip("Necessário ao menos 2 jogos para este teste")

    page.locator(".jogo-header").first.click()
    page.locator(".card-form").first.wait_for(timeout=5_000)

    # A lista deve ter a classe 'tem-expandido'
    expect(page.locator(".jogos-lista")).to_have_class(r".*tem-expandido.*")


def test_clicar_em_outro_card_fecha_o_anterior(page: Page, base_url: str):
    """Selecionar um segundo jogo deve fechar o primeiro."""
    page.goto(f"{base_url}/index.html")
    headers = page.locator(".jogo-header")
    headers.first.wait_for(timeout=DEFAULT_TIMEOUT)

    if headers.count() < 2:
        pytest.skip("Necessário ao menos 2 jogos para este teste")

    headers.first.click()
    page.locator(".card-form").first.wait_for(timeout=5_000)
    headers.nth(1).click()
    page.wait_for_timeout(600)  # aguarda animação

    primeiro_card = page.locator(".jogo-card").first
    assert "expandido" not in (primeiro_card.get_attribute("class") or "")


def test_envio_sem_preencher_campos_nao_submete(page: Page, base_url: str):
    """Submeter sem nick/score deve mostrar toast de erro, não sucesso."""
    page.goto(f"{base_url}/index.html")
    page.locator(".jogo-header").first.wait_for(timeout=DEFAULT_TIMEOUT)
    page.locator(".jogo-header").first.click()
    page.locator(".card-form").first.wait_for(timeout=5_000)

    jogo_id = page.locator(".jogo-item").first.get_attribute("id").replace("card-", "")
    page.locator(f"#btn-{jogo_id}").click()

    expect(page.locator(".toast.error")).to_be_visible(timeout=3_000)
    expect(page.locator(".card-sucesso.visible")).not_to_be_visible()


def test_link_ver_ranking_existe(page: Page, base_url: str):
    """Deve haver link para o ranking na página de upload."""
    page.goto(f"{base_url}/index.html")
    link = page.locator("a.ranking-link")
    expect(link).to_be_visible()
    assert "ranking.html" in (link.get_attribute("href") or "")
