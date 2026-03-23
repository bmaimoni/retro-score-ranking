def test_debug_html(page, base_url):
    errors = []
    page.on("console", lambda msg: errors.append(f"{msg.type}: {msg.text}") if msg.type == "error" else None)
    page.goto(f"{base_url}/index.html")
    page.wait_for_timeout(8000)
    print("\nErros do console:")
    print("\n".join(errors) if errors else "nenhum")
    print(f"\nCards encontrados: {page.locator('.jogo-card').count()}")
    print(f"Items encontrados: {page.locator('.jogo-item').count()}")
    assert True