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
