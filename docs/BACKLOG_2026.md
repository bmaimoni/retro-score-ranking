# Backlog 2026 — Perfil de Usuário, Navegação, Ranking Rico, Admin Escalável

> Status: **compilação bruta, sem desenho de solução ainda**. Cada item abaixo
> é uma reformulação objetiva do que foi pedido, agrupada por tema, com
> referência ao que já existe no código pra não redesenhar do zero. As
> perguntas de "ponto cego" no final de cada bloco são pra resolver **antes**
> de detalhar qualquer item individualmente.

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

| # | Item | Nota |
|---|---|---|
| 2.1 | Sem evento vinculado → mostrar marcas com eventos válidos, em vez de permitir envio "solto" | Muda o fallback hoje-hardcoded (`canal3expo`) |
| 2.2 | Trocar "Entrar para proteger seu nick" por algo tipo "Salve suas pontuações!" | Copy simples |
| 2.3 | Logado: mostrar nickname + avatar, e usar isso pra não pedir de novo no envio | Depende do ponto cego #1 da seção Perfil |
| 2.4 | Scroll infinito na lista de jogos quando há muitos ativos; busca continua achando qualquer um, independente da paginação visual | — |

### Pontos cegos — Tela inicial

1. **O fallback `canal3expo` desaparece de vez, ou continua pra links/QRs
   já impressos sem `?evento=`?** Se o Canal3 Expo ainal está rolando e tem
   material físico distribuído sem esse parâmetro, tirar o fallback quebra
   esses códigos na hora.

2. **O que torna um evento "válido" pra aparecer no seletor de marca?**
   `publico=true`? Também dentro da janela de envio (`data_inicio`/
   `data_fim`)? Ou só "existe e está ativo"?

---

## 3. Ranking (`ranking.html`)

| # | Item | Nota |
|---|---|---|
| 3.1 | Mais informação por jogo: plataforma, ano de lançamento, capa, foto de gameplay | Campos novos em `jogos` |
| 3.2 | Admin da marca configura quantos scores aparecem por página | Hoje `PAGE_SIZE=20` é fixo no client — vira config. Item distinto de 3.7 (tamanho de página ≠ fonte de dados do ranking) |
| 3.3 | "PARTICIPE PELO CELULAR" — ou implementar o QR de verdade (como no telão), ou remover | **Achei o bug**: o `<div id="ranking-qrcode">` já existe no HTML, mas nunca é preenchido por nenhum JS — é um elemento morto hoje, não só "estranho visualmente" |
| 3.4 | Link "Participar" no rodapé parece perdido → navegação real (hamburguer ou footer) entre as telas | Afeta o site inteiro, não só ranking.html |
| 3.5 | `game-tabs` vai ficar grande demais com muitos jogos, principalmente mobile | Mesmo tema do scroll infinito da tela inicial — provavelmente a mesma solução serve pras duas telas |
| 3.6 | Logado, clicar em "meu score" pula direto pra própria posição naquele jogo/evento | Precisa saber a página onde a própria entrada cai |
| 3.7 | Rankings configuráveis por evento (zerado / último evento / marca / marca+parceiras / geral) | **RESOLVIDO — ver `docs/RANKINGS_CONFIGURAVEIS_SPEC.md`.** Surgiu como extensão da discussão do item 1.7 (seguir); inclui modelo de parceria entre marcas e uma decisão revertida (ocultação de origem — ver §3 do documento) |

### Pontos cegos — Ranking

1. **De onde vem o metadado rico do jogo (plataforma, ano, capa,
   gameplay)?** Cadastro manual por admin (tedioso se o catálogo crescer
   muito) ou uma integração com alguma base externa tipo IGDB? Isso também
   cruza com a lógica de mesclagem de jogos que acabamos de construir —
   quando dois jogos duplicados mesclam, qual metadado "vence"?

2. **A config de "scores por página" é por marca, por evento, ou os dois
   com herança** (mesmo padrão que já criamos pra cor/tipografia/logo)?

3. **A navegação (hamburguer/footer) é só nas telas públicas
   (index/ranking/telão), ou entra no admin também?** O admin já tem abas
   próprias — não sei se faz sentido unificar.

---

## 4. Admin

| # | Item | Nota |
|---|---|---|
| 4.1 | Feed ganha filtros: data, evento, jogo, sem foto, etc. | Expande bastante `GET /api/admin/feed` |
| 4.2 | Reforço explícito: admin não pode ser confundido com moderador — moderador não cria jogo/evento, não mexe em telão | **É o achado #0** — precisa da dimensão de nível no modelo de autorização |
| 4.3 | Toda lista filtrada pagina (evitar lentidão com volume grande) | Feed já pagina hoje — checar se sobrevive aos filtros novos |
| 4.4 | Campo de busca pro moderador achar uma entrada rápido | Provavelmente entra junto com os filtros do 4.1 |

### Pontos cegos — Admin

1. **A lista exata do que "admin" pode fazer vs. "moderador" bate com o
   que já existe?** Você listou: feed, eventos, config do telão, e
   habilitar usuário como moderador/admin — isso deixa **de fora**
   explicitamente: jogos, marcas, placares. Preciso confirmar essa lista
   linha por linha antes de desenhar as permissões (ex.: admin pode criar
   marca, ou só super-admin? O texto não deixa 100% claro).

2. **"Habilitar um usuário como moderador/admin"** — isso usa a mesma UI de
   vínculos que já construímos (`/api/admin/vinculos`), só que agora
   também escolhendo o **nível**, não só o escopo?

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
