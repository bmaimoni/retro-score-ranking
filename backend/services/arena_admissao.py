"""
Admissão self-serve de arena — colisão de nome/slug e heurística de
risco da Fase 8. Ver docs/ARENA_SPEC.md Fase B e
docs/PLANO_IMPLEMENTACAO_2026.md Fase 8 pro desenho completo.
"""
import re
import unicodedata
from dataclasses import dataclass

NOME_FIXO_PROTEGIDO = "canal3"

_PADRAO_HOSTIL = re.compile(r'(?i)<script|javascript:|on\w+\s*=|<iframe|data:text/html')


def normalizar(texto: str) -> str:
    """minúsculo, sem acento, só letras/dígitos/espaço — comparação
    tolerante a variação superficial de escrita (maiúscula, acento,
    pontuação)."""
    sem_acento = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^a-z0-9 ]', '', sem_acento.lower()).strip()


def _distancia_edicao(a: str, b: str) -> int:
    """Levenshtein simples — strings curtas (nome/slug de arena), sem
    necessidade de otimização."""
    if a == b:
        return 0
    m, n = len(a), len(b)
    if m == 0:
        return n
    if n == 0:
        return m
    anterior = list(range(n + 1))
    for i, ca in enumerate(a, 1):
        atual = [i] + [0] * n
        for j, cb in enumerate(b, 1):
            custo = 0 if ca == cb else 1
            atual[j] = min(anterior[j] + 1, atual[j - 1] + 1, anterior[j - 1] + custo)
        anterior = atual
    return anterior[n]


@dataclass
class ResultadoAdmissao:
    bloqueado: bool
    motivo: str | None = None
    suspeito: bool = False  # dispara draft (B.4), não bloqueia a criação


def avaliar_admissao(nome: str, slug: str, existentes: list[dict]) -> ResultadoAdmissao:
    """
    existentes: [{"nome": str, "slug": str}, ...] de toda arena já
    cadastrada. Compara nome E slug do candidato contra nome E slug de
    cada existente, mais a entrada fixa "Canal3" (B.2).

    Bloqueio (409): correspondência exata após normalizar, ou uma
    forma é substring da outra (ex.: "Canal3 Oficial" contém
    "canal3"). Suspeito, sem bloquear (B.4 — nasce draft em vez de
    published): distância de edição <= 2 entre as formas normalizadas,
    sem já ter batido no bloqueio exato/substring acima.

    Critério de "quase-igual" escolhido por ser simples, objetivo e
    barato pro volume esperado (poucas dezenas/centenas de arenas,
    comparação O(n) por criação, cada comparação O(len(a)*len(b)) com
    strings curtas). Levenshtein completo (não só prefixo/sufixo) pega
    tanto erro de digitação ("Cana3") quanto variação deliberada pra
    escapar do bloqueio exato ("Canal3s", "Canal-3") — os dois casos
    que B.2/B.4 juntos precisam cobrir. Limiar 2 é generoso o
    suficiente pra não gerar falso positivo em nomes curtos diferentes
    de verdade (ex. "Liga X" vs "Liga Y" tem distância 1, mas são
    nomes de 5-6 caracteres onde qualquer diferença já é
    intencional — aceito o risco de over-flagging aqui, porque
    suspeito só atrasa com revisão humana, não bloqueia; heurística
    mais afiada fica pra depois, se abuso real for observado).
    """
    candidatos_normalizados = {normalizar(nome), normalizar(slug)}
    todos_existentes = [{"nome": e["nome"], "slug": e["slug"]} for e in existentes]
    todos_existentes.append({"nome": NOME_FIXO_PROTEGIDO, "slug": NOME_FIXO_PROTEGIDO})

    suspeito = False
    for existente in todos_existentes:
        existentes_normalizados = {normalizar(existente["nome"]), normalizar(existente["slug"])}
        for cand in candidatos_normalizados:
            if not cand:
                continue
            for exist in existentes_normalizados:
                if not exist:
                    continue
                if cand == exist or cand in exist or exist in cand:
                    return ResultadoAdmissao(
                        bloqueado=True,
                        motivo=(
                            f'Nome/slug muito parecido com uma arena já cadastrada '
                            f'("{existente["nome"]}") — escolha outro.'
                        ),
                    )
                if _distancia_edicao(cand, exist) <= 2:
                    suspeito = True

    return ResultadoAdmissao(bloqueado=False, suspeito=suspeito)


def sanitizar_logo_url(url: str | None) -> str | None:
    """
    logo_url é renderizado depois num telão físico público — tratado
    como input hostil (checklist de segurança da Fase 8). Não é
    validação de URL completa (fora de escopo aqui), só bloqueia os
    vetores óbvios de XSS que uma string vira quando cai crua num
    atributo src/href/style no frontend.
    """
    if url is None:
        return None
    if _PADRAO_HOSTIL.search(url):
        raise ValueError("logo_url contém conteúdo não permitido")
    return url
