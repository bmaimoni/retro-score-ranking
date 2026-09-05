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


# CATALOGO_JOGOS_SPEC.md 8.3 — age_ratings usa os enums legados
# (category/rating), flat, em vez de rating_category.organization.name
# (aninhamento de 3-4 níveis) — mais simples e sem risco de estourar
# limite de expansão de campo do Apicalypse, pra um dado de prioridade
# baixa no catálogo. Tabelas oficiais da IGDB (api-docs.igdb.com/#age-rating-enums).
_AGE_RATING_ORGS = {
    1: "ESRB", 2: "PEGI", 3: "CERO", 4: "USK", 5: "GRAC", 6: "CLASS_IND", 7: "ACB",
}
_AGE_RATING_VALUES = {
    1: "3", 2: "7", 3: "12", 4: "16", 5: "18", 6: "RP", 7: "EC", 8: "E", 9: "E10+",
    10: "T", 11: "M", 12: "AO",
    13: "A", 14: "B", 15: "C", 16: "D", 17: "Z",  # CERO
    18: "0", 19: "6", 20: "12", 21: "16", 22: "18",  # USK
    23: "ALL", 24: "12", 25: "15", 26: "18", 27: "TESTING",  # GRAC
    28: "L", 29: "10", 30: "12", 31: "14", 32: "16", 33: "18",  # CLASS_IND
    34: "G", 35: "PG", 36: "M", 37: "MA15+", 38: "R18+", 39: "RC",  # ACB
}

# Campos "leves" — usados na busca por nome (search-as-you-type,
# instantâneo, uma chamada por tecla digitada após debounce). Só o
# suficiente pra listar sugestões clicáveis; o detalhe rico (8.3) só é
# buscado sob demanda (buscar_por_id), pra não pesar toda tecla digitada.
_CAMPOS_LEVES = "name,platforms.name,platforms.generation,first_release_date,cover.image_id,genres.name"

# Campos completos — usados só ao criar/re-sincronizar um jogo
# específico (uma chamada pontual, não por tecla digitada).
_CAMPOS_COMPLETOS = _CAMPOS_LEVES + (
    ",summary,involved_companies.company.name,involved_companies.developer,"
    "involved_companies.publisher,game_modes.name,"
    "multiplayer_modes.campaigncoop,multiplayer_modes.dropin,multiplayer_modes.lancoop,"
    "multiplayer_modes.offlinecoop,multiplayer_modes.onlinecoop,multiplayer_modes.splitscreen,"
    "multiplayer_modes.splitscreenonline,franchises.name,franchise.name,total_rating,"
    "age_ratings.category,age_ratings.rating,screenshots.image_id,"
    "keywords.name,alternative_names.name"
)


def _extrair_basico(item: dict) -> dict:
    """Campos já existentes desde a Fase 5/7 — compartilhado entre busca
    leve e detalhe completo, pra não duplicar a lógica de agregação."""
    plataformas = item.get("platforms") or []
    plataforma = ", ".join(p["name"] for p in plataformas) if plataformas else None

    # CATALOGO_JOGOS_SPEC.md 7.3 — geração é atributo da plataforma, não
    # do jogo; um jogo com várias plataformas carrega o conjunto de
    # gerações delas (dedup + ordenado), não um valor só.
    geracoes = sorted({p["generation"] for p in plataformas if p.get("generation")}) or None

    # 7.1 — gêneros vêm de game.genres (lista de {id, name})
    generos = [g["name"] for g in (item.get("genres") or [])] or None

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
        "generos": generos,
        "geracoes": geracoes,
    }


def _mapear_resultado(item: dict) -> dict:
    return _extrair_basico(item)


def _mapear_detalhe(item: dict) -> dict:
    """Mapeamento completo (CATALOGO_JOGOS_SPEC.md 8.3) — só chamado
    pra um jogo específico (criação/resync), nunca por tecla digitada."""
    dados = _extrair_basico(item)

    empresas = item.get("involved_companies") or []
    desenvolvedoras = [
        e["company"]["name"] for e in empresas
        if e.get("developer") and e.get("company", {}).get("name")
    ]
    publicadoras = [
        e["company"]["name"] for e in empresas
        if e.get("publisher") and e.get("company", {}).get("name")
    ]

    mm_flags = {
        "campaigncoop": "Co-op campanha", "dropin": "Drop-in/out",
        "lancoop": "Co-op LAN", "offlinecoop": "Co-op offline",
        "onlinecoop": "Co-op online", "splitscreen": "Split-screen",
        "splitscreenonline": "Split-screen online",
    }
    modos_multiplayer = sorted({
        label for mm in (item.get("multiplayer_modes") or [])
        for flag, label in mm_flags.items() if mm.get(flag)
    }) or None

    franquias = [f["name"] for f in (item.get("franchises") or []) if f.get("name")]
    if item.get("franchise", {}).get("name"):
        franquias.insert(0, item["franchise"]["name"])
    franquias = list(dict.fromkeys(franquias)) or None  # dedup preservando ordem

    classificacoes = []
    for ar in (item.get("age_ratings") or []):
        org = _AGE_RATING_ORGS.get(ar.get("category"))
        valor = _AGE_RATING_VALUES.get(ar.get("rating"))
        if org and valor:
            classificacoes.append(f"{org}: {valor}")
    classificacoes = classificacoes or None

    screenshots = item.get("screenshots") or []
    screenshot_url = None
    if screenshots and screenshots[0].get("image_id"):
        screenshot_url = (
            f"https://images.igdb.com/igdb/image/upload/t_screenshot_big/"
            f"{screenshots[0]['image_id']}.jpg"
        )

    dados.update({
        "resumo": item.get("summary"),
        "desenvolvedora": ", ".join(desenvolvedoras) or None,
        "publicadora": ", ".join(publicadoras) or None,
        "modos_jogo": [m["name"] for m in (item.get("game_modes") or []) if m.get("name")] or None,
        "modos_multiplayer": modos_multiplayer,
        "franquias": franquias,
        # CATALOGO_JOGOS_SPEC.md 8.4 — total_rating (usuários+crítica
        # combinados), nunca confundir com o ranking real da plataforma.
        "rating_igdb": round(item["total_rating"]) if item.get("total_rating") else None,
        "classificacoes_etarias": classificacoes,
        "screenshot_url": screenshot_url,
        "palavras_chave": [k["name"] for k in (item.get("keywords") or []) if k.get("name")] or None,
        "nomes_alternativos": [
            a["name"] for a in (item.get("alternative_names") or []) if a.get("name")
        ] or None,
    })
    return dados


async def _executar_apicalypse(corpo: str) -> list[dict]:
    token = await _obter_token()
    settings = get_settings()
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
            return resp.json()
    except httpx.HTTPStatusError as exc:
        # CATALOGO_JOGOS_SPEC.md 8.2/8.B3 — loga status+corpo da resposta
        # de erro (rate limit, Apicalypse malformado, etc.), não só a
        # exceção genérica — sem isso, uma falha real em produção nunca
        # dava pra diagnosticar sem reproduzir manualmente.
        log.error(
            "igdb_busca_erro_http",
            status_code=exc.response.status_code,
            corpo_resposta=exc.response.text[:500],
        )
        raise IGDBIndisponivel(f"Erro ao buscar na IGDB: {exc}") from exc
    except httpx.HTTPError as exc:
        log.error("igdb_busca_erro", exc_info=True)
        raise IGDBIndisponivel(f"Erro ao buscar na IGDB: {exc}") from exc


async def buscar(query: str, limite: int = 10) -> list[dict]:
    """
    Busca jogo por nome na IGDB (Apicalypse), campos leves (8.3) — pro
    search-as-you-type do canto Jogos. Levanta IGDBNaoConfigurado se as
    credenciais não estiverem setadas, IGDBIndisponivel em erro de
    rede/resposta inesperada — o router (routers/admin.py) traduz os
    dois em 503 com mensagem que orienta pro cadastro manual.

    Aspas no termo de busca são escapadas — query cai direto no corpo
    Apicalypse como string entre aspas duplas, sem escapar quebraria a
    sintaxe da query (e, em tese, permitiria injetar cláusula extra).
    """
    query_escapada = query.replace('"', '\\"')
    corpo = f'search "{query_escapada}"; fields {_CAMPOS_LEVES}; limit {limite};'
    resultados = await _executar_apicalypse(corpo)
    return [_mapear_resultado(item) for item in resultados]


async def buscar_por_id(igdb_id: int) -> dict | None:
    """
    Busca um jogo específico por ID na IGDB, campos completos (8.3) —
    usado na criação via IGDB e no resync (8.5) do catálogo já
    cadastrado. Diferente de `buscar`: sem ambiguidade (ID exato), sem
    limite de resultado, sem custo por tecla digitada.
    """
    corpo = f'fields {_CAMPOS_COMPLETOS}; where id = {int(igdb_id)};'
    resultados = await _executar_apicalypse(corpo)
    return _mapear_detalhe(resultados[0]) if resultados else None
