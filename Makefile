# ── Retro Score Ranking — comandos de teste ────────────────────────────────────

# Instala dependências de teste
install-test:
	pip install -r requirements-test.txt
	playwright install chromium

# ── Fase A: unitários ─────────────────────────────────────────────────────────
unit:
	pytest tests/ --ignore=tests/smoke -v --tb=short

# Com cobertura
unit-cov:
	pytest tests/ --ignore=tests/smoke -v --tb=short \
		--cov=. --cov-report=term-missing --cov-omit="tests/*,migrations/*"

# ── Fase B: integração (subset dos unitários que cobrem fluxos) ───────────────
integration:
	pytest tests/test_fluxo_upload.py tests/test_fluxo_moderacao.py \
		tests/test_ranking_lideres.py -v --tb=short

# ── Fase C: smoke E2E ─────────────────────────────────────────────────────────
smoke:
	pytest tests/smoke/ -v --tb=short \
		--headed  # remova --headed para rodar headless

smoke-headless:
	pytest tests/smoke/ -v --tb=short

# ── Tudo ──────────────────────────────────────────────────────────────────────
all: unit integration smoke-headless

# ── CI/CD (sem smoke que precisa de ambiente externo) ─────────────────────────
ci:
	pytest tests/ --ignore=tests/smoke -v --tb=short \
		--cov=. --cov-report=xml --cov-omit="tests/*,migrations/*"
