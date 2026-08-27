# Arena: onboarding self-serve, efeito de rede e evolução casual→profissional

> Status: **em elaboração — Fases A-E fechadas, Fases F-H em aberto**.
> Revisa `PERMISSOES_SPEC.md` numa dimensão que aquele documento não previa:
> o container hoje chamado `marca` deixa de ser assumido como "empresa/
> terceiro pagante" por padrão — passa a nascer **casual-first**, com a
> camada de governança (nível, titularidade, auditoria) do
> `PERMISSOES_SPEC.md` continuando válida, mas como algo que se **ativa**
> quando o container profissionaliza, não como exigência desde o cadastro.
> Nome de trabalho do container, daqui pra frente: **Arena**.
>
> Processo de especificação nasceu de uma pergunta menor ("como automatizar
> a entrada de um admin de marca nova?") e expandiu, ao longo da conversa
> que originou este documento, pra uma revisão do modelo de negócio inteiro
> — registrado aqui porque a decisão de expandir escopo é, em si, uma
> decisão de arquitetura que vale documentar, não só o resultado final.
> Nenhuma decisão deste documento — nem as do `PERMISSOES_SPEC.md` original
> — é tratada como imutável; o processo segue revisitando o que já foi
> fechado à medida que aparece informação nova (decisão A.4).

---

## 1. Como chegamos aqui

Ponto de partida: automatizar a jornada de um admin de marca nova (criar
conta, configurar perfil, cadastrar colaboradores), item deixado em aberto
no §8.4 do `PERMISSOES_SPEC.md`. A pesquisa de padrões de onboarding de
outros sistemas (§2) levou a cogitar self-serve puro, o que expôs uma
tensão maior: o container `marca` foi desenhado pra um cenário específico
(cliente B2B pagante, evento presencial, moderação por foto de evidência)
que não serve bem um segundo público real — pessoas organizando
campeonato caseiro com amigos, presencial ou online, com demanda concreta
já identificada pra jogos de luta (cruzamento de jogadores entre jogos,
badges de rivalidade). Resolver isso obrigou a repensar o container antes
de qualquer decisão de onboarding fazer sentido — daí a Fase A.0.

---

## 2. Padrões de onboarding pesquisados (insumo pra Fase A/B)

Cinco padrões usados por outros sistemas, avaliados como candidatos:

| Padrão | Exemplos | Como funciona | Veredito |
|---|---|---|---|
| **A. Self-serve puro** | Slack, Notion, Shopify, Vercel, Linear | Pessoa se cadastra sozinha, cria o workspace na hora, vira Owner automaticamente, convida time depois | **Adotado como base**, com trava de admissão (Fase B) |
| **B. Provisionado pelo vendor + convite-pra-ativar** | HubSpot Enterprise, Salesforce, Zendesk, Shopify Plus | Vendor cria o tenant, convida por e-mail; clique no link cria a conta na hora, não exige conta prévia | Referência pro fluxo de convite assíncrono (Fase F) — resolve o gap atual onde `dono_email` exige que a pessoa já tenha logado antes |
| **C. Invite-link com papel, "entrar" em vez de "pré-provisionar"** | GitHub Orgs, Discord, Linear teams | Convite com papel definido; transferência de titularidade é ação explícita separada, exige aceite | Referência pro convite de colaborador do dia a dia (Fase F), já alinhado com a decisão #11 do `PERMISSOES_SPEC.md` (transferência só pra quem já é admin vinculado) |
| **D. Wizard guiado pós-ativação** | Stripe Connect, checklist de setup do Shopify/Notion/Intercom | Checklist de primeira execução: branding → convidar time → configurar a "primeira coisa real", sempre retomável | Adotado pra Fase E |
| **E. Auto-claim por domínio verificado** | Slack Enterprise Grid, Google Workspace, Okta | Cadastro com e-mail de domínio corporativo verificado entra automaticamente na org daquele domínio | **Rejeitado** — Arena não tem noção de "domínio" (uma Arena pode ser um `@gmail.com` de uma pessoa física); o risco real de self-serve aqui não é domínio, é impersonação de nome/identidade visual num contexto físico (telão de evento) — ver §3 |

---

## 3. Riscos identificados na avaliação de self-serve puro (Padrão A)

Mesmo padrão do `PERMISSOES_SPEC.md` §5 — registrar o porquê, não só a
trava, pra não reabrir esses buracos numa iteração futura sem lembrar da
razão original.

1. **Superfície de escrita não autenticada.** Hoje, criar Arena é uma
   chamada de back-office autenticada por `super`. Self-serve expõe isso
   como alvo de automação/spam do jeito que hoje não é — precisa de rate
   limit antes de ir ao ar.
2. **Impersonação de nome, não de domínio.** `nome`/`slug`/`cor_primaria`/
   `logo_url` de uma Arena aparecem publicamente em QR code, ranking e
   principalmente **telão físico projetado num evento real** — dano de
   mundo físico (prêmio, reputação), não só colisão de nome de workspace
   SaaS. É o risco que precisa de trava antes do self-serve ir ao ar —
   trava por revisão leve de nome/slug, não por domínio (que não existe
   como conceito aqui).
3. **Superfície cross-Arena cresce mais rápido.** Mais containers criados
   mais rápido aumenta a exposição a qualquer bug de escopo cross-Arena já
   sinalizado como "risco existencial" no §1 do `PERMISSOES_SPEC.md` — self-
   serve não introduz o risco, acelera a taxa de exposição a ele.
4. **Todo input de bootstrap passa a ser não confiável.** Hoje é ator
   confiável (`super`) provisionando. Self-serve exige tratar `logo_url`
   (renderizado num telão público — vetor de XSS se não sanitizado),
   corrida de unicidade de `slug`, etc., como input hostil desde a
   origem — auditoria de segurança real, não troca de tela.
5. **Vaidade de métrica de cadastro.** "N Arenas criadas" não significa
   nada se a maioria for teste/spam abandonado. Métrica que importa:
   Arena que efetivamente rodou uso real (evento com envios, temporada com
   participação recorrente).
6. **Fricção intencional vs. acidental.** Parte da fricção atual (só
   `super` cria) é acidental e pode sair sem perda. Parte funciona hoje
   como filtro humano contra fraude/spam — remover sem substituto tira os
   dois tipos juntos.
7. **Ordem de monetização invertida.** Self-serve com freemium pressupõe
   um conceito de plano/gate de feature que não existe em nenhum lugar do
   schema hoje (explicitamente fora de escopo desde o §8.4 do
   `PERMISSOES_SPEC.md`). Construir o funil de aquisição antes do que cobra
   na saída dele é sequência invertida — mitigado aqui pela decisão A.3
   (não há receita B2B viva a proteger, então o risco de "funil sem
   monetização por um tempo" é aceitável).

### Caminho de reconciliação adotado

Self-serve cria conta + Arena instantaneamente (resolve fricção, entrega
valor imediato), mas a Arena nasce num estado **não publicado/trial** —
visível só pro próprio criador, sem aparecer em listagens públicas nem
gerar QR "ao vivo" pra evento físico real — até passar por um checkpoint
leve (verificação automática de slug/nome não colidir com Arena existente
+ eventualmente aprovação rápida, não o provisionamento manual completo de
hoje). Preserva o gatilho de hábito do self-serve, mantém o filtro contra
impersonação/spam que a fricção atual cumpre, e adia a decisão de billing
pro momento em que o desenho de plano/limite existir (Fase C) — sem travar
o onboarding nela. **Este é o desenho de referência pra Fase B**, ainda
não fechado formalmente lá.

---

## 4. Tensões identificadas na expansão pro público casual

A demanda concreta que motivou repensar o container (campeonato caseiro,
jogos de luta com cruzamento de jogador entre jogos, badges de rivalidade)
expõe atrito com o modelo herdado do `PERMISSOES_SPEC.md`:

1. **Peso do container.** `cor_primaria`/`tipografia`/`logo_url`/
   `itens_por_pagina` são campos de identidade visual de cliente B2B —
   pedir isso de "eu e mais 4 amigos jogando essa semana" é fricção sem
   propósito. Resolvido pela decisão A.2 (container único, campos
   condicionais por estágio de profissionalização), mas o desenho concreto
   de quais campos ficam escondidos até quando ainda não foi feito —
   pendente da Fase C/D.
2. **Badge de rivalidade exige dado que não existe hoje.** `entradas` é
   score independente (maior pontuação vence) — não existe confronto
   direto registrado (quem venceu quem). Um badge tipo "carrasco" precisa
   de uma entidade de dado nova (resultado de partida head-to-head),
   estruturalmente diferente de `entradas`. **Fora do escopo desta spec**
   — registrado aqui como pré-requisito de uma spec futura de confrontos/
   partidas, não pra resolver dentro do onboarding.
3. **Chave de campeonato (bracket) é subsistema, não recurso.** Geração de
   chave, seed, avanço de fase — ordem de grandeza maior que qualquer coisa
   no roadmap atual. Registrado como visão de produto, **fora do escopo**
   desta spec.
4. **Moderação por foto de evidência não se aplica a jogo online entre
   amigos.** O modelo de confiança físico (foto do placar, fila de
   pendentes) pressupõe presença num evento. Score online autodeclarado é
   outro modelo de confiança (talvez sem moderação, talvez integração
   futura com API do jogo) — **não decidido nesta spec**, mas nomeado
   explicitamente pra não ser esquecido quando a Fase de scoring online for
   desenhada.
5. **Diferencial competitivo.** Ferramentas gratuitas de chave/ladder já
   existem no mercado (Challonge, Battlefy, Toornament) — o casual-first
   precisa de resposta própria pra "por que Arena e não essas" além de
   reaproveitar infra existente. **Pergunta em aberto**, não bloqueia a
   spec de onboarding, mas deve informar a priorização de features da
   Fase A.6 adiante.

---

## Fase A — Modelo de negócio e efeito de rede ✅ fechada

| # | Tópico | Decisão |
|---|---|---|
| A.1 | Nome do container | **Arena** — substitui "marca" nesta e nas specs futuras; carrega clima de competição/gaming, funciona pro grupo caseiro e pro patrocinador grande depois (marcas reais já usam o termo em venues, ex. "Red Bull Arena") |
| A.2 | Estrutura | Container único, não dois modelos paralelos — `admin_vinculos`/`dono_user_id`/auditoria do `PERMISSOES_SPEC.md` continuam existindo, mas como camada que se ativa quando a Arena profissionaliza (evento físico, prêmio, marca de terceiro), não obrigatória desde o cadastro casual |
| A.3 | Sequenciamento estratégico | Casual-first sem trilha paralela protegendo receita — **não há receita B2B viva hoje**, é aposta, não fundação a preservar; libera priorizar a fundação casual sem restrição de continuidade de receita |
| A.4 | Postura do processo | Nenhuma decisão anterior — nem as do `PERMISSOES_SPEC.md` original — é tratada como imutável; o processo segue revisitando à medida que a spec avança |
| A.5 | Mecanismos de efeito de rede identificados | (a) jogador cruza Arenas via identidade única/seguidores; (b) parcerias entre Arenas com ranking compartilhado (já existe embrião em `marcas_parcerias`); (c) viral entre operadores (um dono satisfeito indica outro); (d) liga/campeonato caseiro como caso de uso primário — demanda real já identificada (jogos de luta, cruzamento de jogador entre jogos, badges de rivalidade) |
| A.6 | Candidatos a feature de uso diário/recorrente | **Temporadas/ligas recorrentes** num grupo fixo — ranking zera/agrega por período (semana/mês); notificação de prazo com framing de urgência, ex. *"Termine à frente do ranking até segunda-feira"* — mecânica nova, não existe hoje no projeto. **Desafios diretos (duelo)** entre jogadores específicos — assíncrono, notificação de resposta; notificação de superação, ex. *"Fulano te passou hoje"* — reaproveita a mensagem de superação já existente em `SEGUIR_SPEC.md` (Fase 3), adaptada de evento único pra contexto de temporada recorrente. Desafios diretos também geram, como efeito colateral, o dado de confronto direto que um badge de rivalidade (item 4.2) precisaria. Torneio com chave fica registrado como visão de produto (§4.3), fora desta rodada. Custo comparativo: temporadas reaproveitam quase inteiramente a infra de `seguidores`/feed de atividade existente (mais barato); desafios diretos exigem máquina de estado nova (criado → aceito/recusado → resolvido), mais caro, mas é a peça que mais paga a dívida de dado do badge de rivalidade |
| A.7 | Freemium (grátis vs. pago) | Adiado deliberadamente pra Fase C, depois que modelo de dados/limites estiver desenhado — decisão explícita de não comprometer o corte de monetização antes da admissão (Fase B) estar fechada |

---

## Fase B — Controle de admissão ✅ fechada

| # | Tópico | Decisão |
|---|---|---|
| B.1 | O que "não publicada" restringe | Só **descoberta por estranho** — não bloqueia funcionalidade pro próprio grupo. Arena recém-criada funciona de imediato pra quem criou e pra quem for convidado (evento, envio de score, ranking interno); só não aparece em listagem pública (`GET /api/marcas/com-evento-ativo`) nem gera QR de venue físico até publicar. É onde o dano de impersonação realmente ocorre (estranho vendo telão físico ou listagem pública enganosa) — travar o "aha moment" de um grupo fechado jogando entre si não protege nada e mata o gatilho de hábito do casual-first. Tecnicamente barato: `GET /api/marcas` já filtra por `admin.tem_acesso_na_marca()` pra não-super desde a correção do §8.1 do `PERMISSOES_SPEC.md` — "não publicada" vira só mais um filtro na consulta pública |
| B.2 | Lista de nomes protegidos | **Não** manter lista de marcas famosas do mundo real — não escala e não é o risco real aqui. Bloqueio: nome/slug quase-idêntico a Arena **já cadastrada na própria plataforma** (é ali que existe jogador real, reputação e eventual prêmio), mais uma entrada fixa pro próprio "Canal3" como operador. Escopo bem mais estreito que proteção de marca registrada genérica, e realista de manter |
| B.3 | Rate limit | Por `user_id` autenticado, não por IP (CGNAT de operadora de celular no Brasil torna IP não confiável). Teto proposto: 3 Arenas/dia por conta — generoso pra uso legítimo, corta a maioria do abuso por script. Já parte de uma base não-anônima (Google/Magic Link) |
| B.4 | Postura de revisão | **Reativa** — publica automático se passar B.1-B.3; só entra em fila de revisão humana se disparar heurística de risco (nome quase-igual a Arena existente, velocidade anômala de criação da mesma conta). Mantém o casual-first sem gargalo humano na maioria dos casos; aceita janela curta de exposição em troca disso — trade-off explícito, decisão consciente de risco vs. o modelo proativo (super aprova tudo antes), que reintroduziria o gargalo que o casual-first está tentando eliminar |

---

## Fase C — Modelo de dados: plano, limites, estado de publicação ✅ fechada

| # | Tópico | Decisão |
|---|---|---|
| C.1 | Estados de publicação | `draft` → `published` → `suspended` (nomes atualizados pra inglês — ver §5). Resolve uma ambiguidade deixada em aberto na Fase B: pra maioria das Arenas (sem sinalização de risco), a checagem roda na própria criação e ela **já nasce `published`**, sem estado intermediário visível — só a minoria sinalizada pela heurística de B.4 fica retida em `draft` até revisão humana. Isso evita reabrir o gargalo geral que a Fase B existiu pra eliminar; a fricção de espera fica restrita só a quem já disparou sinal de risco. `suspended` é congelamento pós-hoc de uma Arena já pública, se abuso for confirmado depois |
| C.2 | Campo de plano | `arenas.plan` nasce como coluna, valor único `free` pra todo mundo por enquanto — nenhuma tier paga implementada ainda, só evita que o billing futuro precise de migração retroativa pra ter onde ancorar |
| C.3 | Corte grátis/pago | **Direção confirmada: gate por feature, não por volume/uso.** Descartados os cortes por nº de evento simultâneo ou por volume de envios/participantes — penalizariam justo as Arenas crescendo organicamente, ou seja, as que mais provam a aposta de efeito de rede (anti-padrão pra produto de rede: nunca travar o nó mais viral no momento em que mais gera valor pra rede). Âncora: identidade de jogador, seguir, temporadas e desafios recorrentes (A.6) e badges ficam **grátis sem limite** — são o motor de efeito de rede em si (A.5), não dá pra gatear sem matar o próprio mecanismo que o produto aposta. Candidatos a feature paga: parcerias formais entre Arenas, ranking agregado multi-Arena, branding customizado — sinalizam Arena se comportando como operação profissional (bate com a narrativa casual→profissional de A.2). **Não fechado em definitivo**: a lista exata de que feature é básica vs. paga continua debate aberto a cada rodada futura (consistente com a postura de A.4 — nada aqui é decisão irrevisitável), só a direção do corte (feature, não volume) está fechada |

---

## 5. Nomenclatura: migração pra inglês (decisão cross-cutting, registrada durante a Fase D)

Decidido durante a Fase D, mas afeta o documento inteiro daqui pra frente:
identificadores de código (tabelas, colunas, rotas, nomes de arquivo)
passam a ser escritos em inglês, mesmo dentro de prosa em português — nome
do container `Arena` já é compatível nos dois idiomas, sem mudança.
**Alcance explicitamente limitado a código**: a prosa dos documentos
(`docs/*.md`, este incluído) continua em português — não é migração de
documentação, é convenção de identificador. Motivo dado pra fazer isso
agora, não depois: sistema ainda pequeno, sem grandes clientes/usuários,
sem campeonatos ou rankings de peso — janela mais barata pra migrar do que
será depois de crescer. O rename retroativo do que **já existe** em
produção (`admin_vinculos`, `entradas`, `eventos`, routers, arquivos de
frontend) é uma migração real de schema/código já em produção — precisa da
mesma disciplina de qualquer migração deste projeto (testar contra
Postgres real, descrever comportamento antes de rodar, nunca `DELETE`
físico) e vale linha própria em `PLANO_IMPLEMENTACAO_2026.md`, não uma
decisão de passagem aqui. Registrado como iniciativa separada — daqui pra
frente, todo identificador **novo** desta spec já nasce em inglês; o que já
existe migra depois, em rodada dedicada.

---

## Fase D — Fluxo de cadastro self-serve ✅ fechada

| # | Tópico | Decisão |
|---|---|---|
| D.1 | Reestruturação da entrada | `index.html` vira **home institucional** do produto (proposta de valor, CTA "criar sua Arena"/"criar um ranking pra você e seus amigos", diretório de eventos abertos — ver D.7). A página de participação (hoje `index.html`, chegada por QR/link direto de evento) é renomeada pra **`play.html`** e passa a **sempre exigir identificador de evento explícito na URL** — a lógica de fallback/seletor de marca que existia (Fase 6 do `PLANO_IMPLEMENTACAO_2026.md`, `GET /api/marcas/com-evento-ativo` quando não há `?evento=`) migra inteira pra função de descoberta da home, não fica duplicada em `play.html`. Sem redirect de compatibilidade pra QR/links externos existentes — descartado por decisão explícita |
| D.2 | Login antes de criar | Sessão resolvida antes de qualquer criação de Arena — mesmo padrão já usado em `admin.html`, sem estado transitório novo de "preencha o formulário, autentique depois" |
| D.3 | Campos mínimos no cadastro | Só nome (slug derivado automático, editável). Identidade visual (cor/tipografia/logo) fica de fora — migra pro wizard pós-ativação (Fase E). Resolve o "peso do container" apontado em §4.1: não pedir branding antes da pessoa nem saber se vai usar aquilo pra evento presencial ou só pra jogar com amigos |
| D.4 | Caminho de `super` continua existindo | Provisionamento manual por `super` (com atribuição de dono por e-mail, §8.3 do `PERMISSOES_SPEC.md`) continua em paralelo ao self-serve — não é substituído, útil pro caso raro de onboarding branco-luva de um patrocinador grande de verdade |
| D.5 | Corrida de slug | Constraint único já cobre no banco (retorna 409 hoje); self-serve precisa de UX amigável de sugestão de slug alternativo na colisão — detalhe de implementação, não decisão bloqueante |
| D.6 | Implementação do rate limit (B.3) | Sem tabela nova — contagem de Arenas `WHERE owner_user_id = ? AND created_at > now() - interval '1 day'`, comparada ao teto de 3/dia já fechado em B.3 |
| D.7 | Visibilidade por evento (nova, mais fina que a de Arena) | `events.visibility = 'open' \| 'private'`, **default `private`** — diferente do default efetivo de Arena (pública assim que passa em B.1-B.4), porque a preocupação aqui é escolha do grupo, não impersonação de container. Grupo caseiro não é surpreendido aparecendo num diretório público sem pedir; operador que quer atrair gente de fora abre o evento deliberadamente. É o que alimenta o diretório "eventos abertos agora" da nova home institucional (D.1) — discovery real de produto, mais forte pro efeito de rede (A.5) do que qualquer CTA sozinho |

---

## Fase E — Wizard de configuração pós-ativação ✅ fechada

| # | Tópico | Decisão |
|---|---|---|
| E.1 | Estrutura do wizard | Checklist não-bloqueante, sempre retomável — nunca tranca acesso ao resto do painel atrás de completar (Padrão D de §2: Stripe Connect, Shopify/Notion/Intercom). Progresso calculado on-the-fly a partir do que já existe (tem evento criado? tem mais de um membro na Arena? tem branding customizado definido?) — sem tabela nova de "estado de checklist", evita abstração sem necessidade |
| E.2 | Passo 1 — primeira competição (o "aha moment") | Cria um `evento` — entidade **já existente** em `EVENTOS_SPEC.md`, sem schema novo: nome + janela de envio (`data_inicio`/`data_fim`, já obrigatórios lá). Default de janela: `data_inicio=agora`, `data_fim=+10 anos` — mesma convenção já usada na migração do `EVENTOS_SPEC.md` pra "sem previsão de encerramento". É o passo que entrega valor real na primeira sessão (link de ranking funcionando), não uma tela de configuração. Nota de reconciliação: `publico` (acesso via link — já existe, controla se `GET` de ranking/telão funciona) e `visibility` (busca/descoberta — novo, D.7) são **eixos independentes**: uma Arena/evento pode ser acessível por quem tem o link e mesmo assim não aparecer em nenhum diretório de busca |
| E.3 | Passo 2 — convidar colegas | Reserva só o espaço/ordem no wizard — o mecanismo de convite assíncrono em si é desenhado por inteiro na Fase F. Vem depois do passo 1 de propósito: convidar gente pra uma Arena vazia entrega menos valor do que convidar pra uma que já tem uma competição rodando |
| E.4 | Passo 3 — personalizar Arena | Respeita o gate de C.3 (branding customizado é candidato a feature paga): tier grátis vê um seletor limitado de opções pré-definidas, não um customizador completo — personalização total vira upsell natural mostrado dentro do próprio wizard, no momento em que a pessoa já teve a primeira experiência de valor (passos 1-2), não antes |

---

## 6. Próximos passos — fases ainda em aberto

- **Fase F** — Convite assíncrono de colaboradores (resolve o gap atual em
  que `dono_email` exige conta pré-existente — ver Padrão B/C em §2)
- **Fase G** — Migração e compatibilidade com o modelo `super`/`dono`
  atual do `PERMISSOES_SPEC.md` (o que muda pras Arenas já existentes, o
  que `super` deixa/não deixa de fazer)
- **Fase H** — Segurança consolidada e fora de escopo desta rodada
