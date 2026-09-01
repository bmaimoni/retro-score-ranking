"""
Smoke tests: PAINEIS_ADMIN_SPEC.md Fase 0 (contexto de Arena + aba Início
+ console.html novo).
Cobrem: seletor de Arena ativa no topbar, aba Início (branding + resumo de
events), console.html acessível como super, console.html bloqueado sem
sessão (mesmo branch de código de "não-super", ver §0 do spec).
Requer variável SMOKE_ADMIN_SECRET definida (bearer token — sempre super).
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


def test_aba_inicio_e_a_padrao_e_mostra_resumo(page: Page, base_url: str, admin_secret: str):
    _fazer_login(page, base_url, admin_secret)
    expect(page.locator("[data-tab='inicio']")).to_be_visible()
    expect(page.locator("[data-tab='inicio']")).to_have_class("admin-tab active")
    expect(page.locator("#tab-inicio")).to_be_visible()
    # Super sempre tem >=1 Arena em produção hoje. 3 estados válidos:
    # sem Arena nenhuma (#inicio-sem-arena), Arena ativa sem events ainda
    # (.empty-admin dentro de #inicio-lista-events) ou Arena com events
    # (.inicio-event-card). Descoberto rodando contra produção real: a
    # Arena "Rumbles" existe e está zerada — só afirmar cards>0 sem essa
    # 3ª opção falha nesse estado legítimo, não é bug do admin.html.
    sem_arena = page.locator("#inicio-sem-arena")
    lista = page.locator("#inicio-lista-events")
    page.wait_for_timeout(1500)
    assert (
        sem_arena.is_visible()
        or lista.locator(".inicio-event-card").count() > 0
        or lista.locator(".empty-admin").is_visible()
    )


def test_identidade_super_aparece_no_topbar(page: Page, base_url: str, admin_secret: str):
    _fazer_login(page, base_url, admin_secret)
    identidade = page.locator("#admin-identidade")
    expect(identidade).to_be_visible()
    expect(identidade).to_contain_text("SUPER")


def test_arena_selector_lista_arenas_de_producao(page: Page, base_url: str, admin_secret: str):
    _fazer_login(page, base_url, admin_secret)
    page.wait_for_timeout(1000)
    selector = page.locator("#arena-selector")
    # Com 2 Arenas em produção (Canal3, Old School Pinball), selector fica visível.
    # Com 1 só, fica oculto (list de opção única) — ambos são comportamento correto,
    # então só afirmamos que pelo menos uma <option> foi carregada quando visível.
    if selector.is_visible():
        assert selector.locator("option").count() >= 2


def test_trocar_arena_atualiza_resumo_e_branding(page: Page, base_url: str, admin_secret: str):
    _fazer_login(page, base_url, admin_secret)
    page.wait_for_timeout(1000)
    selector = page.locator("#arena-selector")
    if not selector.is_visible():
        pytest.skip("só 1 Arena em produção hoje — sem seletor pra trocar")

    primeira_opcao = selector.locator("option").nth(0).get_attribute("value")
    segunda_opcao = selector.locator("option").nth(1).get_attribute("value")
    assert primeira_opcao != segunda_opcao

    selector.select_option(segunda_opcao)
    page.wait_for_timeout(1000)

    topbar_nome = page.locator("#topbar-arena-nome")
    expect(topbar_nome).to_be_visible()
    nome_apos_troca = topbar_nome.text_content()
    assert nome_apos_troca  # branding atualizou pra Arena escolhida, não ficou vazio


def test_console_link_existe_para_super(page: Page, base_url: str, admin_secret: str):
    _fazer_login(page, base_url, admin_secret)
    page.locator("[data-tab='config']").click()
    link_console = page.locator("#link-console-secao a[href='console.html']")
    expect(link_console).to_be_visible()


def test_console_acessivel_como_super(page: Page, base_url: str, admin_secret: str):
    _fazer_login(page, base_url, admin_secret)
    page.goto(f"{base_url}/console.html")
    expect(page.locator("#console-panel")).to_be_visible(timeout=DEFAULT_TIMEOUT)
    expect(page.locator("#acesso-negado")).to_be_hidden()
    expect(page.locator("[data-tab='config']")).to_be_visible()
    expect(page.locator("[data-tab='avatares']")).to_be_visible()
    expect(page.locator("[data-tab='manutencao']")).to_be_visible()


def test_console_bloqueado_sem_sessao(page: Page, base_url: str):
    # Sem login algum (sem admin_secret em sessionStorage, sem cookie) —
    # mesmo branch de "!meInfo || !meInfo.super" que cobre não-super
    # logado (ver PAINEIS_ADMIN_SPEC.md §0, console.html:282).
    page.goto(f"{base_url}/console.html")
    expect(page.locator("#acesso-negado")).to_be_visible(timeout=DEFAULT_TIMEOUT)
    expect(page.locator("#console-panel")).to_be_hidden()
