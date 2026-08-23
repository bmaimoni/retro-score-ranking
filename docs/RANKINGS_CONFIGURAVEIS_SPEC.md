# Rankings Configuráveis: Modos de Agregação e Parcerias Entre Marcas

> Status: **decisões fechadas, pronto para virar código**. Complementa
> `EVENTOS_SPEC.md` (placares) e `PERMISSOES_SPEC.md` (modelo de marca).
> Escrito a partir de uma sessão de crítica adversarial — inclui uma
> decisão que foi **proposta, aceita, e depois revertida** dentro da
> própria sessão; o raciocínio do recuo fica registrado tanto quanto o
> das decisões que permaneceram, pra não ser reaberto sem contexto.

---

## 1. Objetivo

Permitir que um admin, ao criar um evento, escolha entre 5 modos de
ranking — de "zerado" até "combinado com marcas parceiras" — sem
introduzir uma segunda camada de controle de acesso dentro de listas que,
até aqui, sempre foram binárias (vê tudo ou não vê nada).

---

## 2. Decisões fechadas

### 2.1 — Os 5 modos, na criação de um evento

| Modo | Comportamento |
|---|---|
| A. Zerado | Placar próprio, sem herdar nada — comportamento padrão de hoje |
| B. Só o último evento da marca | Referencia o placar do evento anterior mais recente da mesma marca |
| C. Todos os eventos da marca | Agregação viva de todos os eventos da marca que também escolheram participar — **participação binária por evento** (não é lista manual escolhida um a um) |
| D. Marca + parceiras | Mesma agregação de C, **mais** todos os eventos de marcas com parceria ativa. Tudo-ou-nada: não existe "aceitar dado da Marca B mas não da Marca C" |
| E. Geral da plataforma | Placar `escopo='global'` já existente — todas as marcas, sem opt-out (por enquanto) |

### 2.2 — Demais decisões

| # | Tópico | Decisão |
|---|---|---|
| 1 | Rastreabilidade | Toda linha de um ranking agregado permanece rastreável até jogo/evento/marca de origem — sempre visível, sem exceção (ver §3 sobre a reversão) |
| 2 | Modelo de parceria | Marca B (dona do dado) **libera**; Marca A **aceita** — e ao aceitar, automaticamente libera os próprios placares de volta pra B (mútua, com aviso em tela) |
| 3 | Quem pode liberar/aceitar | **Qualquer admin** da marca — não é exclusivo do dono. `dono_user_id` só existe pra evitar marca órfã (trava de titularidade), nunca como "admin mais poderoso" em decisões operacionais |
| 4 | Parceria é tudo-ou-nada | Não existe granularidade "libero só pra alguns eventos específicos" — é a marca inteira, ou nada |
| 5 | Revogação | Efeito **imediato**, sem cópia de dado — todo ranking agregado é calculado ao vivo, via query com filtro de parceria ativa no momento da consulta. Revogar é só mudar o filtro; nada precisa ser "limpo" ou re-sincronizado |
| 6 | Auditoria | Toda liberação/aceite/revogação de parceria é registrada na tabela geral já desenhada em `PERMISSOES_SPEC.md` (`admin_vinculos_auditoria`) — mais um tipo de ação, não uma tabela nova |
| 7 | Modo D no formulário de evento | O admin do evento só escolhe entre os 5 modos listados — não precisa saber quais marcas específicas estão em parceria. Se a marca tem parceria ativa, "modo D" já inclui automaticamente tudo que a marca tem acesso naquele momento |
| 8 | Placar geral (E) sem opt-out | Confirmado: toda marca participa do placar `escopo='global'` — não há, por ora, como uma marca recusar participação |

---

## 3. Decisão revertida: ocultar origem de scores sem parceria — e por quê

Uma proposta chegou a ser aceita nesta mesma sessão e depois revertida,
antes de qualquer código ser escrito. Vale documentar o raciocínio
completo, porque é o tipo de decisão que alguém pode tentar reabrir sem
o contexto de por que foi descartada.

**A proposta**: quando o placar geral da plataforma (modo E) é exibido
dentro do contexto de uma marca específica, scores de origem fora da
parceria dessa marca apareceriam com pontuação e nick normais, mas **sem
revelar evento/marca de origem** — só uma notação genérica tipo "🌐
Plataforma".

**Por que foi descartada**:

1. **Quebra o único princípio de acesso que o projeto manteve consistente
   até aqui.** Toda decisão de autorização até este ponto — `super` vs.
   `admin` vs. `moderador`, isolamento entre marcas, trava de titularidade
   — foi desenhada como **binária**: uma tela inteira, disponível ou não.
   Ocultação linha-a-linha, dentro da mesma lista, seria a primeira
   exceção a esse padrão — e seria acidentalmente fácil de vazar por
   qualquer caminho que não passasse pela mesma lógica de filtro
   (endpoint de debug, export administrativo, consulta direta).

2. **O motivo de negócio era fraco perto do risco técnico.** Pontuação e
   nick continuariam totalmente públicos — só a origem seria escondida.
   Isso não protege dado pessoal nem informação administrativa sensível
   (as duas categorias que efetivamente justificaram toda restrição de
   acesso já desenhada neste projeto) — protegeria, na prática, só a
   estética de uma marca não querer aparecer "perdendo" visualmente para
   uma concorrente. E mesmo essa proteção seria facilmente contornável
   (o mesmo score aparece sem ocultação na visão pública do placar geral
   "puro", ou na página da própria marca de origem).

3. **Decisão**: nenhuma ocultação condicional. Todo ranking agregado —
   independente do modo, independente de parceria — permanece com
   rastreabilidade completa e uniforme. Se algum cliente B2B real, no
   futuro, apresentar uma razão de negócio concreta e validada para
   ocultação parcial, essa decisão pode ser revisitada — mas não
   antecipada especulativamente.

---

## 4. Modelo de dados (visão preliminar)

- `eventos.modo_ranking`: `'zerado' | 'ultimo_evento' | 'marca' | 'marca_parceiras' | 'geral'` — substitui/complementa o vínculo direto via `placar_eventos` para os modos B/C/D, que passam a ser **calculados**, não listados manualmente.
- `marcas_parcerias` (nova): `marca_origem_id`, `marca_destino_id`, `ativo`, `criado_em` — representa "origem libera pra destino". Como o aceite é automaticamente mútuo (decisão §2.2.2), o par completo é sempre duas linhas (A→B e B→A), ambas criadas no momento do aceite.
- Nenhuma coluna nova para ocultação de origem — decisão revertida (§3).

---

## 5. Pendência registrada

**"Visualização diferente" do placar geral da plataforma** — mencionada de
passagem, sem detalhamento, e **não confundir com a ocultação de origem
revertida em §3** (que era sobre *esconder informação*; isso aqui seria
sobre *apresentar de forma diferente*, ex.: layout, agrupamento visual, ou
destaque distinto para o placar geral vs. placares de marca). Fica
registrado como item de backlog próprio (`docs/BACKLOG_2026.md`) — escopo
a definir quando chegar a vez.
