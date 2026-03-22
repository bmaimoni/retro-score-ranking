"""
Smoke tests: painel admin (admin.html)
Cobrem: login, feed, filtros, moderação básica.
Requer variável SMOKE_ADMIN_SECRET definida.
"""
import pytest
from playwright.sync_api import Page, expect
from conftest import DEFAULT_TIMEOUT


@pytest.fixture(autouse=True)
def set_timeout(page: Page):
    page.set_default_timeout(DEFAULT_TIMEOUT)


def _fazer_login(page: Page, base_url: str, admin_secret: str):
    page.goto(f"{base_url}/admin.html")
    page.locator("#senha-input").fill(admin_secret)
    page.locator("#login-btn").click()
    expect(page.locator("#admin-panel")).to_be_visible(timeout=DEFAULT_TIMEOUT)


def test_login_incorreto_mostra_erro(page: Page, base_url: str):
    page.goto(f"{base_url}/admin.html")
    page.locator("#senha-input").fill("senha-errada-xyz")
    page.locator("#login-btn").click()
    expect(page.locator("#login-error")).to_be_visible(timeout=DEFAULT_TIMEOUT)


def test_login_correto_abre_painel(page: Page, base_url: str, admin_secret: str):
    _fazer_login(page, base_url, admin_secret)
    expect(page.locator(".admin-topbar")).to_be_visible()
    expect(page.locator(".admin-tabs")).to_be_visible()


def test_abas_do_painel_existem(page: Page, base_url: str, admin_secret: str):
    _fazer_login(page, base_url, admin_secret)
    expect(page.locator("[data-tab='feed']")).to_be_visible()
    expect(page.locator("[data-tab='jogos']")).to_be_visible()
    expect(page.locator("[data-tab='config']")).to_be_visible()
    # Aba pendentes não deve mais existir (foi consolidada no feed)
    assert page.locator("[data-tab='pendentes']").count() == 0


def test_feed_carrega_apos_login(page: Page, base_url: str, admin_secret: str):
    _fazer_login(page, base_url, admin_secret)
    expect(page.locator("#feed-list")).to_be_visible(timeout=DEFAULT_TIMEOUT)


def test_filtros_do_feed_existem(page: Page, base_url: str, admin_secret: str):
    _fazer_login(page, base_url, admin_secret)
    expect(page.locator("[data-filter='todos']")).to_be_visible()
    expect(page.locator("[data-filter='visiveis']")).to_be_visible()
    expect(page.locator("[data-filter='ocultos']")).to_be_visible()
    expect(page.locator("[data-filter='pendentes']")).to_be_visible()


def test_filtro_pendentes_filtra_corretamente(page: Page, base_url: str, admin_secret: str):
    _fazer_login(page, base_url, admin_secret)
    page.locator("[data-filter='pendentes']").click()
    page.wait_for_timeout(500)
    # Ou mostra cards pendentes ou mostra empty state — nunca cards normais
    cards = page.locator(".entrada-card.pendente-card")
    empty = page.locator(".empty-admin")
    assert cards.count() > 0 or empty.is_visible()


def test_botao_atualizar_existe_e_funciona(page: Page, base_url: str, admin_secret: str):
    _fazer_login(page, base_url, admin_secret)
    btn = page.locator("#btn-atualizar")
    expect(btn).to_be_visible()
    btn.click()
    # Após clicar, botão deve mostrar "Atualizando..." brevemente
    page.wait_for_timeout(200)
    # E depois voltar ao texto original
    page.wait_for_timeout(3_000)
    expect(btn).to_have_text("↻ Atualizar")


def test_contador_regressivo_aparece(page: Page, base_url: str, admin_secret: str):
    _fazer_login(page, base_url, admin_secret)
    expect(page.locator("#countdown-label")).to_be_visible()
    texto = page.locator("#countdown-label").inner_text()
    assert ":" in texto  # formato M:SS


def test_aba_jogos_lista_jogos(page: Page, base_url: str, admin_secret: str):
    _fazer_login(page, base_url, admin_secret)
    page.locator("[data-tab='jogos']").click()
    expect(page.locator("#jogos-list")).to_be_visible()
    page.wait_for_timeout(1_000)
    assert page.locator(".jogo-card").count() >= 1


def test_aba_config_lista_configuracoes(page: Page, base_url: str, admin_secret: str):
    _fazer_login(page, base_url, admin_secret)
    page.locator("[data-tab='config']").click()
    expect(page.locator("#config-list")).to_be_visible()
    page.wait_for_timeout(1_000)
    assert page.locator(".config-item").count() >= 1
    # Deve ter os campos de rate limit
    expect(page.locator("#config-rate_limit")).to_be_visible()


def test_logout_volta_para_tela_de_login(page: Page, base_url: str, admin_secret: str):
    _fazer_login(page, base_url, admin_secret)
    page.locator("#logout-btn").click()
    expect(page.locator("#login-gate")).to_be_visible(timeout=3_000)
    expect(page.locator("#admin-panel")).not_to_be_visible()
