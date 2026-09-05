"""
Testes de services/igdb.py — mock de httpx.AsyncClient, sem chamada de
rede real. Cobertura: caminho não-configurado, mapeamento de
resultado, cache/renovação de token.
"""
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import services.igdb as igdb


@pytest.fixture(autouse=True)
def reset_token_cache():
    igdb._token_cache["access_token"] = None
    igdb._token_cache["expira_em"] = 0.0
    yield
    igdb._token_cache["access_token"] = None
    igdb._token_cache["expira_em"] = 0.0


def _settings_configurado():
    settings = MagicMock()
    settings.igdb_client_id = "cid"
    settings.igdb_client_secret = "secret"
    return settings


def _settings_vazio():
    settings = MagicMock()
    settings.igdb_client_id = ""
    settings.igdb_client_secret = ""
    return settings


@pytest.mark.asyncio
async def test_buscar_sem_credenciais_levanta_nao_configurado():
    with patch("services.igdb.get_settings", return_value=_settings_vazio()):
        with pytest.raises(igdb.IGDBNaoConfigurado):
            await igdb.buscar("Pac-Man")


@pytest.mark.asyncio
async def test_buscar_mapeia_resultado_corretamente():
    resposta_token = MagicMock()
    resposta_token.json.return_value = {"access_token": "tok123", "expires_in": 5_000_000}
    resposta_token.raise_for_status = MagicMock()

    resposta_busca = MagicMock()
    resposta_busca.raise_for_status = MagicMock()
    resposta_busca.json.return_value = [
        {
            "id": 3186,
            "name": "Street Fighter II",
            "platforms": [
                {"id": 52, "name": "Arcade", "generation": 3},
                {"id": 19, "name": "Super Nintendo", "generation": 4},
            ],
            "first_release_date": 665366400,  # 1991-02-06 UTC
            "cover": {"image_id": "abc123"},
            "genres": [{"id": 4, "name": "Fighting"}],
        },
        {
            "id": 231006,
            "name": "Sem capa nem data",
        },
    ]

    client_mock = AsyncMock()
    client_mock.__aenter__.return_value = client_mock
    client_mock.post = AsyncMock(side_effect=[resposta_token, resposta_busca])

    with patch("services.igdb.get_settings", return_value=_settings_configurado()), \
         patch("services.igdb.httpx.AsyncClient", return_value=client_mock):
        resultados = await igdb.buscar("Street Fighter II")

    assert len(resultados) == 2
    assert resultados[0]["igdb_id"] == 3186
    assert resultados[0]["nome"] == "Street Fighter II"
    assert resultados[0]["plataforma"] == "Arcade, Super Nintendo"
    assert resultados[0]["ano_lancamento"] == 1991
    assert resultados[0]["capa_url"] == "https://images.igdb.com/igdb/image/upload/t_cover_big/abc123.jpg"
    assert resultados[0]["generos"] == ["Fighting"]
    assert resultados[0]["geracoes"] == [3, 4]  # CATALOGO_JOGOS_SPEC.md 7.3 — conjunto, ordenado

    assert resultados[1]["plataforma"] is None
    assert resultados[1]["ano_lancamento"] is None
    assert resultados[1]["capa_url"] is None
    assert resultados[1]["generos"] is None
    assert resultados[1]["geracoes"] is None


@pytest.mark.asyncio
async def test_buscar_deduplica_geracoes_repetidas_entre_plataformas():
    """CATALOGO_JOGOS_SPEC.md 7.3 — duas plataformas da mesma geração
    (ex: 2 variantes de Arcade) não podem duplicar a geração no array."""
    resposta_token = MagicMock()
    resposta_token.json.return_value = {"access_token": "tok123", "expires_in": 5_000_000}
    resposta_token.raise_for_status = MagicMock()

    resposta_busca = MagicMock()
    resposta_busca.raise_for_status = MagicMock()
    resposta_busca.json.return_value = [{
        "id": 1,
        "name": "Jogo Multi-Arcade",
        "platforms": [
            {"id": 52, "name": "Arcade", "generation": 3},
            {"id": 80, "name": "Arcade Cabinet", "generation": 3},
        ],
    }]

    client_mock = AsyncMock()
    client_mock.__aenter__.return_value = client_mock
    client_mock.post = AsyncMock(side_effect=[resposta_token, resposta_busca])

    with patch("services.igdb.get_settings", return_value=_settings_configurado()), \
         patch("services.igdb.httpx.AsyncClient", return_value=client_mock):
        resultados = await igdb.buscar("Jogo Multi-Arcade")

    assert resultados[0]["geracoes"] == [3]


@pytest.mark.asyncio
async def test_buscar_reaproveita_token_em_cache():
    """Segunda chamada dentro da validade não deve pedir token de
    novo — só 1 POST pro endpoint de token, mesmo com 2 buscas."""
    igdb._token_cache["access_token"] = "tok-valido"
    igdb._token_cache["expira_em"] = time.time() + 5_000_000  # bem longe de expirar

    resposta_busca = MagicMock()
    resposta_busca.raise_for_status = MagicMock()
    resposta_busca.json.return_value = []

    client_mock = AsyncMock()
    client_mock.__aenter__.return_value = client_mock
    client_mock.post = AsyncMock(return_value=resposta_busca)

    with patch("services.igdb.get_settings", return_value=_settings_configurado()), \
         patch("services.igdb.httpx.AsyncClient", return_value=client_mock):
        await igdb.buscar("qualquer coisa")

    # só a chamada de busca, nenhuma de token (token já em cache válido)
    assert client_mock.post.call_count == 1
    assert client_mock.post.call_args.args[0] == igdb._GAMES_URL


@pytest.mark.asyncio
async def test_buscar_erro_de_rede_levanta_indisponivel():
    import httpx as httpx_mod

    client_mock = AsyncMock()
    client_mock.__aenter__.return_value = client_mock
    client_mock.post = AsyncMock(side_effect=httpx_mod.ConnectError("timeout"))

    with patch("services.igdb.get_settings", return_value=_settings_configurado()), \
         patch("services.igdb.httpx.AsyncClient", return_value=client_mock):
        with pytest.raises(igdb.IGDBIndisponivel):
            await igdb.buscar("Pac-Man")


@pytest.mark.asyncio
async def test_buscar_erro_http_loga_status_e_corpo():
    """CATALOGO_JOGOS_SPEC.md 8.2/8.B3 — erro HTTP (4xx/5xx da própria
    IGDB, ex.: rate limit) precisa logar status+corpo, não só a exceção
    genérica, senão uma falha real em produção nunca dá pra diagnosticar
    sem reproduzir manualmente."""
    import httpx as httpx_mod

    # Token já em cache válido — isola o teste na chamada de busca em si,
    # sem passar pela chamada de token (mesmo truque de
    # test_buscar_reaproveita_token_em_cache).
    igdb._token_cache["access_token"] = "tok-valido"
    igdb._token_cache["expira_em"] = time.time() + 5_000_000

    resposta_erro = MagicMock()
    resposta_erro.status_code = 429
    resposta_erro.text = "Too Many Requests"
    resposta_erro.raise_for_status = MagicMock(
        side_effect=httpx_mod.HTTPStatusError("429", request=MagicMock(), response=resposta_erro)
    )

    client_mock = AsyncMock()
    client_mock.__aenter__.return_value = client_mock
    client_mock.post = AsyncMock(return_value=resposta_erro)

    with patch("services.igdb.get_settings", return_value=_settings_configurado()), \
         patch("services.igdb.httpx.AsyncClient", return_value=client_mock), \
         patch("services.igdb.log") as log_mock:
        with pytest.raises(igdb.IGDBIndisponivel):
            await igdb.buscar("Pac-Man")

    log_mock.error.assert_called_once()
    args, kwargs = log_mock.error.call_args
    assert args[0] == "igdb_busca_erro_http"
    assert kwargs["status_code"] == 429
    assert kwargs["corpo_resposta"] == "Too Many Requests"


# ── Detalhe completo (buscar_por_id) — CATALOGO_JOGOS_SPEC.md 8.3 ──────

_ITEM_COMPLETO = {
    "id": 6710,
    "name": "Street Fighter III: 3rd Strike",
    "platforms": [{"id": 52, "name": "Arcade", "generation": 3}],
    "first_release_date": 927331200,
    "cover": {"image_id": "co6bkh"},
    "genres": [{"id": 4, "name": "Fighting"}],
    "summary": "O melhor jogo de luta já feito.",
    "involved_companies": [
        {"company": {"name": "Capcom Production Studio 2"}, "developer": True, "publisher": False},
        {"company": {"name": "Capcom"}, "developer": False, "publisher": True},
    ],
    "game_modes": [{"name": "Single player"}, {"name": "Multiplayer"}],
    "multiplayer_modes": [{"dropin": True, "splitscreen": True, "onlinecoop": False}],
    "franchise": {"name": "Street Fighter"},
    "franchises": [{"name": "Street Fighter"}, {"name": "Capcom Fighting"}],
    "total_rating": 86.4,
    "age_ratings": [{"category": 1, "rating": 11}],  # ESRB: M
    "screenshots": [{"image_id": "scr1"}, {"image_id": "scr2"}],
    "keywords": [{"name": "martial arts"}, {"name": "karate"}],
    "alternative_names": [{"name": "SF3: Third Strike"}],
}


def test_mapear_detalhe_extrai_todos_os_campos_novos():
    dados = igdb._mapear_detalhe(_ITEM_COMPLETO)

    assert dados["igdb_id"] == 6710
    assert dados["resumo"] == "O melhor jogo de luta já feito."
    assert dados["desenvolvedora"] == "Capcom Production Studio 2"
    assert dados["publicadora"] == "Capcom"
    assert dados["modos_jogo"] == ["Single player", "Multiplayer"]
    assert dados["modos_multiplayer"] == ["Drop-in/out", "Split-screen"]
    # franchise (principal) vem primeiro, dedup preserva ordem
    assert dados["franquias"] == ["Street Fighter", "Capcom Fighting"]
    assert dados["rating_igdb"] == 86  # round(86.4)
    assert dados["classificacoes_etarias"] == ["ESRB: M"]
    assert dados["screenshot_url"] == (
        "https://images.igdb.com/igdb/image/upload/t_screenshot_big/scr1.jpg"
    )
    assert dados["palavras_chave"] == ["martial arts", "karate"]
    assert dados["nomes_alternativos"] == ["SF3: Third Strike"]


def test_mapear_detalhe_campos_ausentes_viram_none():
    dados = igdb._mapear_detalhe({"id": 1, "name": "Jogo sem metadado extra"})

    assert dados["resumo"] is None
    assert dados["desenvolvedora"] is None
    assert dados["publicadora"] is None
    assert dados["modos_jogo"] is None
    assert dados["modos_multiplayer"] is None
    assert dados["franquias"] is None
    assert dados["rating_igdb"] is None
    assert dados["classificacoes_etarias"] is None
    assert dados["screenshot_url"] is None
    assert dados["palavras_chave"] is None
    assert dados["nomes_alternativos"] is None


@pytest.mark.asyncio
async def test_buscar_por_id_usa_where_e_campos_completos():
    igdb._token_cache["access_token"] = "tok-valido"
    igdb._token_cache["expira_em"] = time.time() + 5_000_000

    resposta_busca = MagicMock()
    resposta_busca.raise_for_status = MagicMock()
    resposta_busca.json.return_value = [_ITEM_COMPLETO]

    client_mock = AsyncMock()
    client_mock.__aenter__.return_value = client_mock
    client_mock.post = AsyncMock(return_value=resposta_busca)

    with patch("services.igdb.get_settings", return_value=_settings_configurado()), \
         patch("services.igdb.httpx.AsyncClient", return_value=client_mock):
        resultado = await igdb.buscar_por_id(6710)

    assert resultado["igdb_id"] == 6710
    assert resultado["resumo"] == "O melhor jogo de luta já feito."
    corpo_enviado = client_mock.post.call_args.kwargs["content"]
    assert "where id = 6710;" in corpo_enviado
    assert "summary" in corpo_enviado  # campos completos, não só os leves


@pytest.mark.asyncio
async def test_buscar_por_id_sem_resultado_retorna_none():
    """ID removido/mesclado na IGDB — resync (8.5) trata como 404, não
    como erro."""
    igdb._token_cache["access_token"] = "tok-valido"
    igdb._token_cache["expira_em"] = time.time() + 5_000_000

    resposta_busca = MagicMock()
    resposta_busca.raise_for_status = MagicMock()
    resposta_busca.json.return_value = []

    client_mock = AsyncMock()
    client_mock.__aenter__.return_value = client_mock
    client_mock.post = AsyncMock(return_value=resposta_busca)

    with patch("services.igdb.get_settings", return_value=_settings_configurado()), \
         patch("services.igdb.httpx.AsyncClient", return_value=client_mock):
        resultado = await igdb.buscar_por_id(999999)

    assert resultado is None
