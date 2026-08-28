# Backlog 2026 — Perfil de Usuário, Navegação, Ranking Rico, Admin Escalável

> Status: **todas as 4 seções resolvidas** (Perfil, Tela Inicial, Ranking,
> Admin) — todo item e todo ponto cego original tem decisão fechada,
> registrada aqui ou num documento dedicado (`PERMISSOES_SPEC.md`,
> `NICKNAME_SPEC.md`, `EXCLUSAO_CONTA_SPEC.md`, `SEGUIR_SPEC.md`,
> `RANKINGS_CONFIGURAVEIS_SPEC.md`). Pronto pra virar plano de
> implementação — nenhum código foi escrito ainda, por decisão explícita
> de fechar todas as decisões de arquitetura antes de começar a codar.

---

## 🚨 Achado #0 (RESOLVIDO — ver `docs/PERMISSOES_SPEC.md`)

Falta um nível "moderador" no modelo de autorização — só existia dimensão
de escopo (`super`/`marca`/`evento`), não de nível (quanto alguém pode
fazer dentro do escopo). Discutido e fechado numa sessão de crítica
adversarial; desenho completo (schema, regras de autorização, riscos
identificados, plano de migração) está em `docs/PERMISSOES_SPEC.md`.
**Ainda não implementado** — só o desenho está fechado.

Mudanças que esse desenho força nos itens abaixo desta lista:
- Todo evento passa a exigir marca (`escopo='evento'` eliminado de
  `admin_vinculos`) — qualquer item que mencione "evento sem marca" precisa
  ser revisto.
- Item 4.2 (admin vs. moderador) e a concessão de vínculos do item 1.2 já
  estão cobertos pelo novo documento — não precisam de discussão própria
  quando chegarmos neles.

---

## 1. Perfil de usuário

> **Status: seção inteira resolvida.** Todos os 6 pontos cegos fechados —
> ver `docs/NICKNAME_SPEC.md`, `docs/EXCLUSAO_CONTA_SPEC.md` e
> `docs/SEGUIR_SPEC.md`. Pronta pra virar spec técnica/migração quando
> chegar a vez desse tema no plano de implementação.

| # | Item | Nota |
|---|---|---|
| 1.1 | Base de usuários pronta pra notificações futuras | `users` já existe (`AUTH_SPEC.md`) — provavelmente é extensão, não tabela nova |
| 1.2 | 4 papéis com hierarquia: super-admin ⊃ admin ⊃ moderador ⊃ jogador | Ver achado #0 acima — `admin_vinculos` precisa de dimensão de nível |
| 1.3 | Tela de perfil: ver/editar nome completo, nickname, e-mail, foto, avatar (prontos + upload), data de nascimento, cidade/estado, telefone, "outros campos futuros" | Vários campos novos em `users`; nickname esbarra no modelo de `nick_claims` (ver ponto cego) |
| 1.4 | Ver detalhamento de todas as próprias pontuações — evento e marca de cada uma, link rápido pro jogo | Precisa de endpoint novo (`entradas` por `user_id`, join até `marcas`) |
| 1.5 | Usuário pode "desativar" todas as próprias pontuações (soft) | `entradas.arquivado` já existe — é questão de expor em massa |
| 1.6 | Usuário pode solicitar "exclusão" do próprio perfil (soft) | **RESOLVIDO — ver `docs/EXCLUSAO_CONTA_SPEC.md`** |
| 1.7 | Seguir outros usuários — lista de quem eu sigo / quem me segue | **RESOLVIDO — ver `docs/SEGUIR_SPEC.md`** |
| 1.8 | Logout a partir da tela de perfil | Trivial — endpoint já existe, só falta a tela |

### Pontos cegos — Perfil

1. ~~**Nickname no perfil vs. `nick_claims` atual.**~~ **RESOLVIDO — ver
   `docs/NICKNAME_SPEC.md`.** Nick por entrada é imutável; perfil permite
   trocar (libera o nick antigo, cooldown de 30 dias); histórico de nicks
   fica visível pro moderador; resolução de identificação ambígua é tardia
   (só quando um nick liberado é reivindicado de novo), não retroativa.
   Pré-preenchimento do nick no envio (item 2.3, Tela Inicial) já pode usar
   "nick ativo do perfil" sem ambiguidade — está desbloqueado.

2. ~~**Exclusão de perfil e LGPD.**~~ **RESOLVIDO — ver
   `docs/EXCLUSAO_CONTA_SPEC.md`.** `users.status` ganha valor `'excluido'`;
   janela de 30 dias de cancelamento antes de anonimizar de verdade;
   exclusão bloqueada se a pessoa for `dono_user_id` de alguma marca
   (mesma trava de titularidade do `PERMISSOES_SPEC.md`); retorno depois
   de excluído cria `user_id` novo (conta antiga fica anonimizada
   permanentemente).

3. ~~**Avatar vs. Foto — qual vence onde?**~~ **RESOLVIDO.** Unificado num
   campo só ("imagem de perfil resolvida"): `avatar_id` (galeria curada,
   só super-admin cadastra/desativa — upload livre pelo usuário fica fora
   de escopo por enquanto, precisa de moderação de imagem que não existe
   ainda) vence sobre `foto_url` do Google quando escolhido. Perfil ≠
   fotos de evidência de score — são conceitos completamente
   independentes.

   **Achado, fora do escopo original deste item**: as fotos de evidência
   de score já pedem, na prática, que a pessoa apareça na própria foto —
   ou seja, o sistema já armazena, desde o início, fotos com rosto de
   pessoas reais. Existe (verificado no código) um checkbox de
   consentimento explícito no envio, cobrindo foto/nome/pontuação e
   retenção pós-evento — decisão consciente de não aprofundar direito de
   imagem/menores agora, dado que já existe alguma base de consentimento.
   Fica registrado pra revisão futura, não tratado com rigor por decisão
   explícita.

4. ~~**"Indicar presença em eventos"**~~ **RESOLVIDO.** Presença é
   **inferida**, não é ação nova nem dado novo — upload de score num
   evento pressupõe presença nele, sem verificação/check-in por agora
   (fraude fica pra tratar no futuro). Nenhuma tabela nova: é consulta
   direta sobre `entradas` JOIN `eventos` JOIN `marcas`, disponível a
   qualquer momento, sem manter dado espelhado sincronizado. **Trava de
   isolamento**: qualquer relatório de recorrência **cross-marca**
   (jogador que aparece em eventos de marcas diferentes) é exclusivo de
   `super` — nunca exposto a admin/moderador escopado, mesma classe de
   risco já tratada em `PERMISSOES_SPEC.md`.

5. ~~**Pontuações antigas, enviadas antes de existir login.**~~
   **RESOLVIDO — ver `NICKNAME_SPEC.md`, decisão #11 (claim retroativo).**
   Reivindicar um nick pela primeira vez já vincula automaticamente
   qualquer pontuação antiga com esse `nick_norm` que ainda não tinha
   `user_id` — sem fluxo manual adicional, sem mecanismo novo.

6. ~~**"Seguir" — flui pra algum lugar, ou fica só na tela de perfil?**~~
   **RESOLVIDO — ver `docs/SEGUIR_SPEC.md`.** Alimenta feed de atividade
   (mensagem de superação de score entre jogador seguido e seguidor, no
   mesmo jogo), compilado no login, sem infraestrutura de notificação
   (fica como item de backlog próprio, deliberadamente adiado).

---

## 2. Tela inicial (`index.html`)

> **Status: seção resolvida.** Ver decisões abaixo — sem necessidade de
> spec dedicada, escopo pequeno o suficiente pra documentar direto aqui.

| # | Item | Nota |
|---|---|---|
| 2.1 | Sem evento vinculado → mostrar marcas com eventos válidos, em vez de permitir envio "solto" | **RESOLVIDO.** Fallback hardcoded (`canal3expo`) removido sem rede de segurança — confirmado que não existe QR/material físico impresso hoje dependendo dele |
| 2.2 | Trocar "Entrar para proteger seu nick" por algo tipo "Salve suas pontuações!" | Copy simples — sem ponto cego, segue como pedido original |
| 2.3 | Logado: mostrar nickname + avatar, e usar isso pra não pedir de novo no envio | Desbloqueado por `NICKNAME_SPEC.md` (nick ativo do perfil) + avatar já resolvido (item 1 do backlog) — sem ponto cego próprio, é composição de decisões já fechadas |
| 2.4 | Scroll infinito na lista de jogos quando há muitos ativos; busca continua achando qualquer um, independente da paginação visual | **RESOLVIDO.** Carregamento client-side completo (como já é hoje) — scroll infinito é só renderização progressiva, não paginação de servidor. Preserva o link direto por jogo (`?jogo=slug`) e a busca funcionando sobre a lista inteira, sem lógica extra. Escala de verdade (paginação de servidor) fica adiada pra quando o volume de jogos por evento justificar — decisão explícita de não resolver antecipadamente |

### Pontos cegos — Tela inicial

1. ~~**O fallback `canal3expo` desaparece de vez, ou continua pra links/QRs
   já impressos sem `?evento=`?**~~ **RESOLVIDO.** Sem QR/material físico
   ativo dependendo do fallback — remove sem necessidade de compatibilidade.

2. ~~**O que torna um evento "válido" pra aparecer no seletor de marca?**~~
   **RESOLVIDO.** Critério é `publico=true` (mesmo padrão que já vale pra
   ranking/telão continuarem acessíveis fora da janela de envio — não
   precisa estar dentro de `data_inicio`/`data_fim`). **Decisão de UX
   adicional**: se existir exatamente **uma** marca com evento(s) válido(s)
   no momento, pula o seletor direto pro fluxo dela — seletor só aparece
   de verdade com mais de uma opção real. Evita fricção hoje (só existe
   Canal3 em uso), escala sozinho conforme mais marcas entrarem.

---

## 3. Ranking (`ranking.html`)

> **Status: seção resolvida por completo** (itens 3.1-3.7, incluindo os 3
> pontos cegos originais). Ver `docs/RANKINGS_CONFIGURAVEIS_SPEC.md` pro
> item 3.7 (o mais substancial); o resto documentado direto aqui.


| # | Item | Nota |
|---|---|---|
| 3.1 | Mais informação por jogo: plataforma, ano de lançamento, capa, foto de gameplay | **REABERTO — ver `docs/CATALOGO_JOGOS_SPEC.md`.** A decisão original ("sem integração externa, consulta manual tipo IGDB fora do projeto") foi revertida por pedido explícito: a Fase 5 daquele documento integra com a IGDB de verdade pra preencher esses campos automaticamente. Capa/gameplay ainda seguem o mesmo padrão de avatar (upload via `services/storage.py`) quando não vêm da IGDB |
| 3.2 | Admin da marca configura quantos scores aparecem por página | **RESOLVIDO.** Config única por marca, todo evento dela herda — sem exceção por evento. Mesmo em ranking agregado (item 3.7, com ou sem parceria), sempre usa o valor da marca "dona" da página sendo visualizada, nunca uma mistura |
| 3.3 | "PARTICIPE PELO CELULAR" — ou implementar o QR de verdade (como no telão), ou remover | **RESOLVIDO.** Implementar de verdade — reaproveita a função `gerarQR` que já existe em `telao.html`. Elemento HTML já existe (`<div id="ranking-qrcode">`), só nunca foi preenchido por JS. Em ranking **agregado** (item 3.7), QR sempre aponta pro evento mais recente/ativo da marca dona da página — mesmo critério de "marca dona" já usado pra scores-por-página (item 3.2) |
| 3.4 | Link "Participar" no rodapé parece perdido → navegação real (hamburguer ou footer) entre as telas | **RESOLVIDO.** Escopo só nas telas públicas navegadas ativamente: `index.html` e `ranking.html` (mais "perfil", quando construído). `admin.html` fica como está (abas, modelo diferente — autenticado, condicional por nível). `telao.html` fica de fora (uso passivo, exibição num telão físico, não navegação por toque) |
| 3.5 | `game-tabs` vai ficar grande demais com muitos jogos, principalmente mobile | **RESOLVIDO junto com o item 2.4** (mesma solução: renderização progressiva client-side, sem paginação de servidor; escala real fica adiada até virar problema de fato) |
| 3.6 | Logado, clicar em "meu score" pula direto pra própria posição naquele jogo/evento | **RESOLVIDO.** Pula pra melhor entrada da pessoa dentro do que está sendo visualizado (agregado ou não — mesmo princípio de "melhor score de todos os tempos" já usado em `SEGUIR_SPEC.md`). Calcula a página onde ela cai (considerando `PAGE_SIZE` configurável do item 3.2) e navega automaticamente, com destaque visual |
| 3.7 | Rankings configuráveis por evento (zerado / último evento / marca / marca+parceiras / geral) | **RESOLVIDO — ver `docs/RANKINGS_CONFIGURAVEIS_SPEC.md`.** Surgiu como extensão da discussão do item 1.7 (seguir); inclui modelo de parceria entre marcas e uma decisão revertida (ocultação de origem — ver §3 do documento) |

### Pontos cegos — Ranking

1. ~~**De onde vem o metadado rico do jogo (plataforma, ano, capa,
   gameplay)?**~~ **RESOLVIDO.** Cadastro manual, sempre — integração
   externa (IGDB ou similar) fica fora do projeto, como processo separado
   de consulta pra informar o preenchimento manual. Todos os campos
   opcionais (jogos existentes não ficam bloqueados). Mesclagem de jogos:
   metadado do jogo **destino** sempre sobrevive, mesmo padrão já usado
   pra `entradas`/`evento_jogos` — nenhum preenchimento automático a
   partir da origem, decisão manual do super-admin se quiser copiar algo
   antes de mesclar.

2. ~~**A config de "scores por página" é por marca, por evento, ou os dois
   com herança**~~ **RESOLVIDO.** Só por marca, sem override por evento —
   mais simples que o padrão de cor/tipografia/logo (que permite override).
   Resolve de graça a ambiguidade de qual config vale em ranking agregado
   (item 3.7): sempre a marca dona da página, nunca uma mistura.

3. ~~**A navegação (hamburguer/footer) é só nas telas públicas...**~~
   **RESOLVIDO.** `index.html` + `ranking.html` (+ perfil, quando
   construído). `admin.html` fica com abas, sem unificar. `telao.html`
   fica de fora — uso passivo, exibição num telão físico, sem navegação
   por toque.

---

## 4. Admin

> **Status: seção resolvida por completo.** Boa parte já estava coberta
> por `docs/PERMISSOES_SPEC.md`; só faltava confirmar filtros/busca/
> paginação do feed, que não tinham sido tratados em nenhum documento
> anterior.

| # | Item | Nota |
|---|---|---|
| 4.1 | Feed ganha filtros: data, evento, jogo, sem foto, etc. | **RESOLVIDO.** Filtros: data, evento (dentro do que a pessoa já tem acesso), jogo, sem foto, **e** sem identificação (`user_id` nem `nome` — o filtro que `NICKNAME_SPEC.md` §2.15 já previu pro arquivamento manual). Os dois últimos são filtros separados, não um só |
| 4.2 | Reforço explícito: admin não pode ser confundido com moderador — moderador não cria jogo/evento, não mexe em telão | **RESOLVIDO — coberto por `docs/PERMISSOES_SPEC.md`.** Ver achado abaixo: o fluxo de aprovação de jogos já implementado precisa de ajuste, não foi escrito pensando em 3 níveis |
| 4.3 | Toda lista filtrada pagina (evitar lentidão com volume grande) | **RESOLVIDO.** Segue o padrão já estabelecido em `EVENTOS_SPEC.md` (`X-Total-Count` no header, `limit`/`offset`), suportando múltiplos filtros simultâneos |
| 4.4 | Campo de busca pro moderador achar uma entrada rápido | **RESOLVIDO.** Busca sobre os mesmos campos que já existem no feed (nick, jogo, evento) — extensão direta de `WHERE`, sem full-text search nem índice dedicado |

### Achado de implementação (não é ponto cego de decisão — é ajuste de código já escrito)

O fluxo de aprovação de jogos (`routers/admin.py:criar_jogo`, já implementado antes de `moderador` existir como conceito) hoje só distingue `super` de "qualquer outro admin" — trataria um `moderador` exatamente como trata um `admin` comum, deixando ele criar jogo pendente. Isso contradiz a decisão já fechada ("moderadores não precisam criar jogos. Admins sim.") e precisa de correção na implementação: `criar_jogo` passa a exigir nível `admin` ou `super`, bloqueando `moderador` por completo — não uma decisão nova, um ajuste pra alinhar código já escrito com decisão já tomada.

### Pontos cegos — Admin

1. ~~**A lista exata do que "admin" pode fazer vs. "moderador" bate com o
   que já existe?**~~ **RESOLVIDO.** Confirmado contra `PERMISSOES_SPEC.md`:
   feed/eventos/telão (admin sim, moderador não) bate exatamente. Marcas:
   criar é exclusivo de `super`; editar marca existente é liberado a
   qualquer admin da própria marca. Placares deixou de ser ação isolada
   desde o item 3.7 — virou parte de criar/editar evento.

2. ~~**"Habilitar um usuário como moderador/admin"**~~ **RESOLVIDO.**
   Confirmado: mesma UI de vínculos já construída (`/api/admin/vinculos`),
   só ganha um seletor de nível — `admin_vinculos.nivel` já foi desenhado
   pensando nisso desde `PERMISSOES_SPEC.md`.

---

## Itens novos, surgidos durante a análise dos itens originais

| # | Item | Origem |
|---|---|---|
| 5.1 | Documentação pública das regras de nickname (limite de 30 dias, liberação, o que acontece com pontuações antigas) — em algum lugar que o **jogador** consiga consultar, não só doc técnica interna | Surgiu ao fechar o item de modelo de nickname (`docs/NICKNAME_SPEC.md` §5). Formato (FAQ no perfil? página estática? texto inline?) ainda não decidido — é escolha de produto pra quando chegarmos nesse item |
| 5.2 | Estratégia de retenção pra quem solicita suspensão/cancelamento — intervir de forma não manipuladora durante a janela de 30 dias de cancelamento, pra reduzir churn por impulso | Surgida ao fechar o item de exclusão de conta (`docs/EXCLUSAO_CONTA_SPEC.md`) — decisão explícita de não misturar com a mecânica de exclusão em si, é estratégia de produto própria |
| 5.3 | Infraestrutura de notificação (push/e-mail) para o feed de "seguir" | Deliberadamente fora de escopo do `docs/SEGUIR_SPEC.md` §5 — feed hoje só compila no login, sem entrega em tempo real |
| 5.4 | Visualização diferente do placar geral da plataforma (layout/agrupamento, não ocultação de dado — essa foi revertida) | Mencionada de passagem, sem detalhamento, ao fechar `docs/RANKINGS_CONFIGURAVEIS_SPEC.md` §5 |
| 5.5 | Curadoria fina de parcerias entre marcas (hoje é tudo-ou-nada) | Registrado como possível evolução futura em `docs/RANKINGS_CONFIGURAVEIS_SPEC.md` §2.2.4 — sem necessidade de uso identificada agora |

## Como esses itens se cruzam (visão de dependência, não de prioridade)

```
Achado #0 (nível de permissão)
   └─→ 4.2, 4.4 (admin) — dependem diretamente
   └─→ 1.2 (perfil) — é a mesma peça, só a "moeda" do lado do usuário

Ponto cego "nickname único?" (perfil)
   └─→ 2.3 (tela inicial pré-preencher nick)
   └─→ 3.6 (achar "meu score")
   └─→ 1.3, 1.4 (perfil mostrar/ligar pontuações)

Navegação site-wide (3.4)
   └─→ toca index.html, ranking.html, telao.html, e a tela de perfil (nova)

Scroll infinito + busca (2.4, 3.5)
   └─→ mesma solução provavelmente serve pras duas telas
```

---

## Proposta de ordem pra irmos um a um

Dado que o Achado #0 e o ponto cego do nickname são pré-requisitos de boa
parte do resto, sugiro começarmos por eles — sem isso resolvido, qualquer
desenho de perfil ou de admin fica em cima de areia movediça. Depois disso,
o resto pode ser abordado por tela (perfil → tela inicial → ranking → admin)
ou por tamanho (itens pequenos primeiro pra ganhar tração). Fica ao seu
critério.
