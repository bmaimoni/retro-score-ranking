"""
Smoke tests: tela de ranking (ranking.html)
Cobrem: carregamento, abas por game, SSE conectado, tema aplicado.
"""
import pytest
from playwright.sync_api import Page, expect
from conftest import DEFAULT_TIMEOUT


@pytest.fixture(autouse=True)
def set_timeout(page: Page):
    page.set_default_timeout(DEFAULT_TIMEOUT)


def test_pagina_ranking_carrega(page: Page, base_url: str):
    page.goto(f"{base_url}/ranking.html")
    expect(page.locator(".ranking-header")).to_be_visible(timeout=DEFAULT_TIMEOUT)


def test_abas_de_game_aparecem(page: Page, base_url: str):
    page.goto(f"{base_url}/ranking.html")
    expect(page.locator(".game-tab").first).to_be_visible(timeout=DEFAULT_TIMEOUT)
    assert page.locator(".game-tab").count() >= 1


def test_primeira_aba_fica_ativa(page: Page, base_url: str):
    page.goto(f"{base_url}/ranking.html")
    page.locator(".game-tab").first.wait_for(timeout=DEFAULT_TIMEOUT)
    expect(page.locator(".game-tab.active")).to_be_visible()


def test_indicador_sse_aparece(page: Page, base_url: str):
    """O dot de conexão SSE deve aparecer após conectar."""
    page.goto(f"{base_url}/ranking.html")
    page.locator(".game-tab").first.wait_for(timeout=DEFAULT_TIMEOUT)
    page.wait_for_timeout(3_000)  # aguarda SSE conectar
    expect(page.locator(".connection-dot")).to_be_visible()


def test_trocar_aba_atualiza_game_exibido(page: Page, base_url: str):
    """Clicar em outra aba deve mudar o game exibido no header."""
    page.goto(f"{base_url}/ranking.html")
    abas = page.locator(".game-tab")
    abas.first.wait_for(timeout=DEFAULT_TIMEOUT)

    if abas.count() < 2:
        pytest.skip("Necessário ao menos 2 games para este teste")

    nome_antes = page.locator("#game-nome").inner_text()
    abas.nth(1).click()
    page.wait_for_timeout(1_000)
    nome_depois = page.locator("#game-nome").inner_text()
    assert nome_antes != nome_depois


def test_ranking_exibe_cards_se_houver_entries(page: Page, base_url: str):
    """Se houver entries no ranking, deve exibir pelo menos um card."""
    page.goto(f"{base_url}/ranking.html")
    page.locator(".game-tab").first.wait_for(timeout=DEFAULT_TIMEOUT)
    page.wait_for_timeout(2_000)

    cards = page.locator(".player-card")
    empty = page.locator(".empty-state")

    # Um dos dois deve ser visível
    assert cards.count() > 0 or empty.is_visible()


def test_parametro_game_na_url_seleciona_aba_correta(page: Page, base_url: str, api_url: str):
    """?game=slug deve selecionar a aba correta ao carregar."""
    import httpx
    try:
        games = httpx.get(f"{api_url}/api/games", timeout=10).json()
    except Exception:
        pytest.skip("API indisponível")

    if len(games) < 2:
        pytest.skip("Necessário ao menos 2 games")

    segundo_game = games[1]
    page.goto(f"{base_url}/ranking.html?game={segundo_game['slug']}")
    page.locator(".game-tab").first.wait_for(timeout=DEFAULT_TIMEOUT)
    page.wait_for_timeout(1_000)

    nome_exibido = page.locator("#game-nome").inner_text()
    assert segundo_game["nome"].lower() in nome_exibido.lower()


def test_footer_tem_url_de_upload(page: Page, base_url: str):
    page.goto(f"{base_url}/ranking.html")
    expect(page.locator("#footer-url")).to_be_visible(timeout=DEFAULT_TIMEOUT)
    url_exibida = page.locator("#footer-url").inner_text()
    assert len(url_exibida) > 0
