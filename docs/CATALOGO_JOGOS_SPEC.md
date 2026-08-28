# Catálogo de jogos: admissão, integração IGDB e jornada de cadastro/seleção

> Status: **Fase 5 fechada — Fases 1-4 ainda não iniciadas**. Revisa o
> item 3.1 do `docs/BACKLOG_2026.md` (decisão anterior: "sem integração
> externa... processo à parte, fora do projeto") — reaberta aqui por
> pedido explícito, não por esquecimento. Nenhuma decisão anterior é
> tratada como imutável, mesma postura já registrada em `ARENA_SPEC.md`
> A.4.

---

## 1. Como chegamos aqui

Durante o planejamento de execução da `ARENA_SPEC.md` (Fases 7-10 do
`PLANO_IMPLEMENTACAO_2026.md`), uma pergunta sobre o que vem depois da
Fase 10 levou a avaliar a jornada de cadastro/escolha de jogo — e
encontrou uma lacuna real: a Fase E da `ARENA_SPEC.md` (wizard
pós-ativação, ✅ fechada) promete em E.2 um "aha moment" — link de
ranking funcionando já na primeira sessão — mas não desenha como a
pessoa resolve "qual jogo" nesse momento. Sem jogo vinculado, o link de
ranking não mostra nada.

Investigando o código existente (`admin.py`, migração 018), ficou claro
que cadastro/vínculo de jogo **já funciona**, mas inteiramente dentro do
painel `admin.html` pré-Arena, sem nenhuma ponte com o wizard self-serve,
e sem nenhuma das proteções de admissão que a Fase B da `ARENA_SPEC.md`
desenhou pra Arena (rate limit, colisão de nome, fila de revisão) — apesar
de `games` ser catálogo **global**, compartilhado por toda Arena da
plataforma, com superfície de abuso pelo menos tão grande quanto a de
Arena.

## 2. A jornada mapeada (telas envolvidas)

| Fase | Tela / fluxo | O que resolve |
|---|---|---|
| 1 | Wizard self-serve (`ARENA_SPEC.md` E.2) | Como a pessoa resolve "qual jogo" ao criar a primeira competição — escolher da lista, cadastrar novo ali, ou pular |
| 2 | Painel admin, aba "Jogos" | Cadastro, edição, fila de aprovação, mesclagem de duplicata — revisitado pra população self-serve |
| 3 | Painel admin, aba "Eventos" (vínculo jogo↔evento) | Escolher do catálogo existente, desvincular, reordenar, jogo compartilhado entre eventos/Arenas da mesma pessoa |
| 4 | Lado público (`play.html`, `ranking.html`, `telao.html`) | Comportamento visível pra quem envia score e quem assiste — jogo pendente, jogo mesclado, evento sem jogo nenhum |
| 5 | Admissão e segurança consolidada | Rate limit, dedup, quem revisa a fila — feito **primeiro**, por pedido explícito, porque a integração com a IGDB (ver abaixo) reformula o modelo de admissão que as outras fases vão assumir como já resolvido |

---

## Fase 5 — Admissão e integração com IGDB ✅ fechada

Contexto de pesquisa (não documentado em detalhe nas outras specs porque é
específico desta decisão): IGDB API (`api-docs.igdb.com`) — REST v4,
autenticação OAuth2 client-credentials via Twitch Developer (Client
ID/Secret → token Bearer, validade ~60 dias), rate limit 4 req/s (8
concorrentes), busca via linguagem própria (Apicalypse). **Grátis só pra
uso não-comercial** sob o Twitch Developer Service Agreement — uso
comercial exige parceria negociada à parte (`partner@igdb.com`), não é
plano pago self-serve. Atribuição visível obrigatória em local fixo,
independente do enquadramento comercial. Cache local dos dados retornados
é permitido e incentivado pela própria IGDB.

Decisão sobre o enquadramento comercial: usar agora sob termos
não-comerciais (bate com a realidade atual — sem receita B2B viva, ver
`ARENA_SPEC.md` A.3) e tratar contato com a IGDB pra parceria comercial
como item de ação **quando/se** um plano pago for lançado de verdade
(`ARENA_SPEC.md` C.2/C.3) — dívida técnica/de negócio registrada, não
ignorada.

| # | Tópico | Decisão |
|---|---|---|
| 5.1 | Fonte de verdade / dedup estrutural | `games` ganha coluna nova `igdb_id` (nullable, `UNIQUE` quando preenchida). Jogo vindo da IGDB é ancorado nesse ID externo — dedup deixa de depender de comparação de texto (nome/slug), garantida pelo banco |
| 5.2 | Fluxo de busca no cadastro | Campo de busca dispara Apicalypse contra a IGDB (nome, plataforma, ano, capa), mostra sugestões clicáveis. Ao selecionar: copia os dados pro `games` na criação (cache local, alinhado com a recomendação da própria IGDB) — `plataforma`/`ano_lancamento`/`capa_url` deixam de ser preenchimento manual. `gameplay_url` continua manual (a IGDB não fornece isso) |
| 5.3 | Escape hatch — "não achei na IGDB" | Cadastro manual continua existindo (retrogaming tem título obscuro/homebrew/ROM hack que a IGDB não cobre), mas é o único caminho sem dedup estrutural — carrega todo o peso de admissão abaixo |
| 5.4 | Aprovação automática pro caminho IGDB | Jogo com `igdb_id` preenchido pula `pendente_aprovacao` inteiramente — nasce aprovado, direto no catálogo geral, mesmo vindo de admin não-super. A fila de revisão de `super` (migração 018) passa a existir **só** pro caminho manual — desafoga um gargalo que viraria insustentável em volume self-serve, e é consequência direta de ter fonte externa confiável validando a entrada |
| 5.5 | Rate limit no caminho manual | 5 cadastros manuais/usuário/dia (mais generoso que o 3/dia de Arena — jogo é criado com frequência legítima maior — mas existe, porque é exatamente o caminho sem proteção estrutural). Caminho via IGDB fica **sem** rate limit — abusar dele só adiciona jogos reais já aprovados ao catálogo, sem superfície de dano |
| 5.6 | Colisão no caminho manual | Normalização simples (`lower(trim(nome))`) comparada contra `games.nome` existente — bloqueia duplicata óbvia com sugestão "já existe, quis dizer esse?", mesmo padrão de UX da colisão de nome de Arena (B.2 da `ARENA_SPEC.md`) |
| 5.7 | Atribuição obrigatória | Crédito fixo e visível "Dados de jogos fornecidos por IGDB.com" — rodapé do painel admin (aba Jogos) e qualquer tela pública que exiba capa/metadado vindo de lá (`ranking.html`). Não é negociável, vale mesmo sob uso não-comercial |
| 5.8 | Credenciais | Client ID/Secret da Twitch só no backend (`services/igdb.py` novo), nunca expostos ao frontend; token OAuth2 cacheado com renovação antes dos ~60 dias de validade. Variáveis novas em `.env.example` |
| 5.9 | Achado à parte (não é sobre IGDB) — auto-vínculo do jogo novo a todos os eventos do criador | Comportamento atual (`admin.py`, criação de game) vincula um jogo recém-criado a **todos** os eventos que o admin tem acesso, não só ao que estava editando. Fazia sentido com poucos admins/poucos eventos; em escala self-serve (uma pessoa dona de várias Arenas/eventos) polui eventos sem relação com o jogo criado. Passa a vincular só ao evento em contexto — precisa de parâmetro `event_id` explícito no endpoint de criação |

---

## Fases 1-4 — pendentes

Ainda não iniciadas. Ordem prevista (ver §2): wizard self-serve → painel
"Jogos" → painel "Eventos" (vínculo) → lado público. Cada uma assume o
modelo de admissão fechado na Fase 5 acima como já resolvido.
