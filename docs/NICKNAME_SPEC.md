# Modelo de Nickname: Troca, Liberação, Continuidade de Reputação

> Status: **decisões fechadas, pronto para virar código**. Revisa o modelo
> de `nick_claims` original de `docs/AUTH_SPEC.md` §3 (reivindicação livre,
> sem noção de troca/liberação) à luz de um cenário concreto de disputa de
> ranking. Escrito a partir de uma sessão de crítica adversarial — as
> justificativas ficam junto de cada decisão, não só o resultado.

---

## 1. Objetivo

Definir o que acontece quando alguém troca de nickname no perfil, sem
comprometer dois princípios que o projeto já trata como inegociáveis em
todo o resto do sistema: **nunca reescrever o passado silenciosamente**
(mesmo princípio de `entradas.arquivado`, mesclagem de jogos com rastro) e
**nunca perder a capacidade de saber quem é responsável por uma
pontuação**.

---

## 2. Decisões fechadas

| # | Tópico | Decisão |
|---|---|---|
| 1 | Nick em pontuação já enviada | **Imutável.** Trocar de nick no perfil nunca reescreve `entradas.nick` de pontuações já enviadas — mesmo padrão de "nunca apagar evidência" já usado em fotos e mesclagem de jogos |
| 2 | Múltiplos nicks por pessoa | `nick_claims` continua permitindo vários ao longo do tempo — "nick atual do perfil" é o mais recente ativo, usado só pra pré-preencher envios futuros |
| 3 | Continuidade de reconhecimento | Perfil e ranking mostram "anteriormente conhecido como X" quando há troca — resolve o risco de um jogador reconhecido "sumir" do radar da comunidade ao trocar de nick, sem reescrever histórico |
| 4 | Visibilidade pro moderador | Painel de moderação mostra o histórico de nicks do `user_id`, não só o nick da entrada isolada sendo revisada |
| 5 | Liberação do nick antigo | **Imediata** ao trocar — o nick antigo fica disponível pra qualquer pessoa reivindicar de novo. Reivindicação antiga nunca é apagada (`ativo=false`, mesmo padrão de `evento_jogos`/`admin_vinculos`/`telao_jogos`) — só marcada inativa |
| 6 | Limite de frequência de troca | 1x a cada **30 dias corridos** (não mês-calendário — evita a brecha de trocar dia 31 e dia 1 contando como "meses diferentes"). Primeira reivindicação de uma conta nova nunca conta como troca |
| 7 | Resolução de identificação ambígua | **Tardia, não retroativa.** Histórico existente não é varrido nem mexido agora. Só quando um nick **liberado** é reivindicado de novo, o sistema checa as entradas antigas daquele nick — se alguma não tiver `user_id` nem `nome`, só essas entradas específicas entram em fila de revisão |
| 8 | Prazo sem resposta na fila de revisão | 30 dias (mesma janela da troca, por consistência) — sem identificação fornecida nesse prazo, a entrada é arquivada automaticamente (`arquivado=true`, nunca `DELETE`) |
| 9 | Moderador força troca de nick | Admin/moderador pode trocar o nick de qualquer jogador **sem** respeitar o cooldown de 30 dias — uso previsto: nick ofensivo/impróprio, especialmente relevante por haver exibição pública em telão, em evento presencial |
| 10 | Auditoria de troca forçada | Toda troca de nick feita por admin/moderador fica registrada: quem forçou, de qual nick pra qual, quando |

---

## 3. Por que a resolução de identificação é tardia, não retroativa (§2.7)

Essa foi a decisão que mais mudou de forma durante a análise, vale registrar
o raciocínio: a proposta original era varrer o banco inteiro e jogar pra
moderação qualquer pontuação sem `user_id`/`nome`. Isso quebra em escala,
por dois motivos que só ficam claros levando em conta o resto do projeto:

1. **Login sempre foi opcional** (`AUTH_SPEC.md`, decisão de design desde o
   início) — a maioria das pontuações históricas provavelmente não tem
   `user_id`, e `nome` sempre foi campo opcional no formulário de envio.
2. **Não há "solicitar manualmente" quando não há canal de contato.** Uma
   entrada sem `user_id` e sem `nome` não tem e-mail nem telefone associado
   — `ip_hash` é hash unidirecional, serve pra detectar abuso, não pra
   contatar ninguém.

A ambiguidade só existe de verdade **quando dois jogadores diferentes
reivindicam o mesmo nick em momentos diferentes** — até esse momento, o
nick continua univocamente ligado ao histórico dele, ninguém está
disputando o nome. Resolver só quando o conflito realmente acontece atende
o objetivo (nunca perder identificação quando *importa*) sem o custo de
reprocessar um histórico que, na esmagadora maioria dos casos, nunca vai
colidir com ninguém.

---

## 4. Modelo de dados (visão preliminar — detalhar na implementação)

- `nick_claims.ativo boolean DEFAULT true` — soft-release em vez de
  `DELETE`. Índice único de `nick_norm` passa a ser parcial
  (`WHERE ativo = true`), permitindo o mesmo nick ter múltiplas linhas
  históricas (uma por dono ao longo do tempo), mas só uma ativa por vez.
- `nick_claims` precisa de campo de "quando foi trocado" pra calcular a
  janela de 30 dias (provavelmente `criado_em` já resolve, calculando a
  partir da reivindicação ativa mais recente do `user_id`).
- Nova tabela (ou extensão de `admin_vinculos_auditoria` com uma coluna de
  tipo de ação, a definir na implementação) pra auditoria de troca forçada
  por moderador: quem forçou, `user_id` afetado, nick antigo, nick novo,
  quando.
- Entradas que caem em fila de revisão por identificação ambígua
  provavelmente reaproveitam `entradas.pendente` (mesmo mecanismo já usado
  pro rate limit) — ou precisam de um motivo distinto (`pendente_motivo`)
  se o painel de moderação precisar diferenciar "pendente por rate limit"
  de "pendente por identificação ambígua". A definir na implementação.

---

## 5. Pendência registrada (não bloqueia este item, mas não pode ser esquecida)

**As regras acima (limite de 30 dias, liberação do nick, o que acontece
com pontuações antigas) precisam estar documentadas em algum lugar que o
**jogador** consiga consultar** — hoje o projeto não tem nenhuma tela de
"termos" ou "regras da comunidade" voltada ao usuário final. Toda a
documentação existente (`docs/*.md`) é técnica, pro time, não pro público.
Fica registrado como item de backlog próprio (ver `docs/BACKLOG_2026.md`)
— decidir formato (FAQ na própria tela de perfil? Página estática? Texto
inline no momento da troca?) é uma escolha de produto a fazer quando
chegarmos nesse item, não uma decisão técnica a antecipar aqui.
