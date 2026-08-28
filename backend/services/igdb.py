"""
Cliente IGDB — busca de jogo pro cadastro self-serve, Passo 1 do
wizard (Fase 9 do PLANO_IMPLEMENTACAO_2026.md, fundida com a Fase 1 do
docs/CATALOGO_JOGOS_SPEC.md). Ver Fase 5 daquele documento pro desenho
completo: OAuth2 client-credentials via Twitch Developer, dedup
estrutural via games.igdb_id, aprovação automática pro catálogo geral
(sem passar pela fila de pendente_aprovacao da migração 018).

settings.igdb_client_id/igdb_client_secret vazios = caminho
desabilitado (IGDBNaoConfigurado) — cadastro manual continua
funcionando sem essa dependência, nunca derruba o backend.
"""
import time
from datetime import datetime, timezone

import httpx
import structlog

from config import get_settings

log = structlog.get_logger()

_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
_GAMES_URL = "https://api.igdb.com/v4/games"

# Cache do token em memória de processo — client-credentials não tem
# usuário por trás, um único token serve pro processo inteiro. Não
# precisa de banco/Redis pra isso: se o processo reiniciar, busca um
# token novo na próxima chamada, sem custo real (Twitch não rate-limita
# a emissão de token de forma que isso importe pro nosso volume).
_token_cache: dict = {"access_token": None, "expira_em": 0.0}


class IGDBNaoConfigurado(Exception):
    """settings.igdb_client_id/igdb_client_secret vazios."""


class IGDBIndisponivel(Exception):
    """Erro de rede/timeout/resposta inesperada da IGDB — nunca deixa
    vazar traceback pro cliente, o router traduz em 503."""


async def _obter_token() -> str:
    settings = get_settings()
    if not settings.igdb_client_id or not settings.igdb_client_secret:
        raise IGDBNaoConfigurado()

    agora = time.time()
    # Renova proativamente se faltar menos de 1 dia pra expirar (token
    # dura ~60 dias — folga generosa, evita corrida com uma chamada
    # que expira no meio da requisição).
    if _token_cache["access_token"] and (_token_cache["expira_em"] - agora) > 86400:
        return _token_cache["access_token"]

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(_TOKEN_URL, params={
                "client_id": settings.igdb_client_id,
                "client_secret": settings.igdb_client_secret,
                "grant_type": "client_credentials",
            })
            resp.raise_for_status()
            dados = resp.json()
    except httpx.HTTPError as exc:
        log.error("igdb_token_erro", exc_info=True)
        raise IGDBIndisponivel(f"Erro ao obter token IGDB: {exc}") from exc

    _token_cache["access_token"] = dados["access_token"]
    _token_cache["expira_em"] = agora + dados["expires_in"]
    return _token_cache["access_token"]


def _mapear_resultado(item: dict) -> dict:
    plataformas = item.get("platforms") or []
    plataforma = ", ".join(p["name"] for p in plataformas) if plataformas else None

    ano_lancamento = None
    if item.get("first_release_date"):
        ano_lancamento = datetime.fromtimestamp(
            item["first_release_date"], tz=timezone.utc
        ).year

    capa_url = None
    cover = item.get("cover")
    if cover and cover.get("image_id"):
        capa_url = f"https://images.igdb.com/igdb/image/upload/t_cover_big/{cover['image_id']}.jpg"

    return {
        "igdb_id": item["id"],
        "nome": item["name"],
        "plataforma": plataforma,
        "ano_lancamento": ano_lancamento,
        "capa_url": capa_url,
    }


async def buscar(query: str, limite: int = 10) -> list[dict]:
    """
    Busca jogo por nome na IGDB (Apicalypse). Levanta IGDBNaoConfigurado
    se as credenciais não estiverem setadas, IGDBIndisponivel em erro
    de rede/resposta inesperada — o router (routers/admin.py) traduz
    os dois em 503 com mensagem que orienta pro cadastro manual.

    Aspas no termo de busca são escapadas — query cai direto no corpo
    Apicalypse como string entre aspas duplas, sem escapar quebraria a
    sintaxe da query (e, em tese, permitiria injetar cláusula extra).
    """
    token = await _obter_token()
    settings = get_settings()

    query_escapada = query.replace('"', '\\"')
    corpo = (
        f'search "{query_escapada}"; '
        f'fields name,platforms.name,first_release_date,cover.image_id; '
        f'limit {limite};'
    )

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                _GAMES_URL,
                headers={
                    "Client-ID": settings.igdb_client_id,
                    "Authorization": f"Bearer {token}",
                },
                content=corpo,
            )
            resp.raise_for_status()
            resultados = resp.json()
    except httpx.HTTPError as exc:
        log.error("igdb_busca_erro", exc_info=True)
        raise IGDBIndisponivel(f"Erro ao buscar na IGDB: {exc}") from exc

    return [_mapear_resultado(item) for item in resultados]
