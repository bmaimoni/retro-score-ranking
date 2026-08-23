# Exclusão de Conta: Anonimização, Janela de Cancelamento, Trava de Titularidade

> Status: **decisões fechadas do lado de arquitetura, pronto para virar
> código** — com uma ressalva importante na seção 6. Complementa
> `docs/AUTH_SPEC.md` (schema de `users`) e `docs/PERMISSOES_SPEC.md`
> (titularidade de marca, que esta spec depende diretamente).

---

## 1. Objetivo

Definir o que acontece quando um usuário solicita a exclusão do próprio
perfil — sem deixar `entradas`/ranking inconsistentes, sem criar um estado
de marca "órfã" (dono que se auto-excluiu), e com uma leitura factual (não
jurídica) de LGPD suficientemente rigorosa pra não precisar redesenhar isso
de novo se a interpretação legal exigir mais rigor depois.

**Aviso, repetido de propósito**: não sou advogado. A seção 6 descreve o
panorama factual da lei que fundamentou as escolhas técnicas abaixo — não
é aconselhamento jurídico. Vale confirmar com alguém qualificado antes de
tratar a interpretação como definitiva.

---

## 2. Decisões fechadas

| # | Tópico | Decisão |
|---|---|---|
| 1 | Novo valor de `users.status` | `'excluido'`, distinto de `'suspenso'` — suspenso é ação de moderação (por comportamento); excluído é pedido do próprio usuário. Semânticas diferentes, mesmo com mecânica parecida |
| 2 | Janela de cancelamento | **30 dias** entre a solicitação e a anonimização de verdade — dá tempo pra desistir de uma decisão por impulso |
| 3 | Revogação de sessões e vínculos administrativos | Ao confirmar a exclusão (não ao solicitar — ver #2): todas as sessões ativas são revogadas, e qualquer `admin_vinculos` que a pessoa tivesse é revogado junto, automaticamente |
| 4 | Retorno depois de excluído | Logar de novo com a mesma conta Google cria um **`user_id` novo** — a conta antiga permanece anonimizada permanentemente, sem mecanismo de "reviver" |
| 5 | **Trava de titularidade** | Se a pessoa for `dono_user_id` de qualquer marca no momento do pedido, a solicitação é **bloqueada na hora** — nem começa a contar os 30 dias. Precisa transferir a titularidade primeiro (mecanismo já desenhado em `PERMISSOES_SPEC.md`). Nunca existe reatribuição automática de titularidade por timeout — só o dono atual ou `super` decidem isso |
| 6 | Nick em pontuações enviadas | Não reescrito na anonimização — mesma decisão já fechada em `NICKNAME_SPEC.md` (nick nem sempre é PII; reescrever quebraria integridade de ranking histórico pra resolver um problema que pode nem existir na prática) |

---

## 3. Por que a trava de titularidade existe (achado da análise)

Esse é o ponto mais importante desta spec, e não estava em nenhum pedido
original — só apareceu ao cruzar este item com a decisão de titularidade
de marca que já tínhamos fechado. `PERMISSOES_SPEC.md` já bloqueia
revogar o vínculo `admin` do dono atual diretamente, exatamente pra evitar
uma marca ficar sem dono. Mas **exclusão de conta é, na prática, uma forma
de auto-revogação total** — se não fosse tratada explicitamente, um
cliente B2B pagante (dono de marca) conseguiria contornar aquela trava
simplesmente excluindo a própria conta, deixando `marcas.dono_user_id`
órfão do mesmo jeito que a trava original foi desenhada pra impedir.

A decisão de bloquear (não permitir e resolver depois) é consistente com o
princípio já estabelecido: titularidade nunca muda por consequência
indireta ou automática — só por ação explícita do dono ou de `super`.

---

## 4. Diferença entre "desativar pontuações" (item 1.5) e "excluir conta"

Vale deixar explícito na UI, não só no código: são ações de peso diferente.

- **Desativar pontuações** (`entradas.arquivado=true` em massa) é
  reversível, leve, não mexe em dado pessoal nenhum — só esconde scores.
- **Excluir conta** é a ação pesada: anonimiza dado pessoal, revoga acesso
  administrativo, e (depois dos 30 dias) não tem volta.

Misturar as duas num único botão/fluxo seria confuso — a pessoa que só
quer sumir do ranking por um tempo não deveria precisar passar pelo
processo pesado de exclusão de conta pra isso.

---

## 5. Onde o dado pessoal realmente mora (não é só uma tabela)

Anonimização de verdade precisa tocar em mais lugares do que `users`
sozinho — achado da análise, não pedido original:

- `users` (nome, foto_url, e os campos novos que o backlog já propõe:
  avatar, data de nascimento, cidade/estado, telefone)
- `identities.email` — guarda e-mail **por provedor**, separado de
  `users.email`
- `magic_link_tokens.email` — pode ter e-mails ainda não expirados

Uma rotina que só limpa `users` e esquece as outras duas tabelas não
cumpre o objetivo — o e-mail continuaria existindo em texto puro em outro
lugar do banco. **Esse risco cresce com o tempo**: cada campo pessoal novo
que os próximos itens do backlog adicionarem (data de nascimento, cidade,
telefone, avatar) expande a lista de coisas que a rotina de anonimização
precisa lembrar de limpar — se for uma lista de campos hardcoded no
código, é o tipo de coisa que fica desatualizada silenciosamente numa
migração futura. Vale desenhar a rotina de forma que adicionar um campo
pessoal novo em `users` force (por convenção de código, revisão, ou
alguma checagem automatizada) considerar se ele entra na anonimização —
não é algo a resolver agora, mas fica registrado pra não esquecer quando
os campos novos do perfil forem implementados.

---

## 6. Panorama factual de LGPD (não é aconselhamento jurídico)

A LGPD dá à pessoa o direito de solicitar exclusão de dados pessoais
tratados com base em consentimento (Art. 18, VI). O Art. 16 lista exceções
em que o controlador pode manter dados mesmo após o pedido, incluindo uso
exclusivo do controlador, com acesso de terceiro vedado, desde que
anonimizados. Isso é a base factual pra um argumento plausível de "mantemos
a pontuação/ranking, mas anonimizamos os dados pessoais identificáveis" —
mas "plausível" não é "certo". As decisões técnicas acima foram desenhadas
pra suportar a versão **mais rigorosa possível** (anonimização de verdade,
não só esconder atrás de uma flag), justamente pra ser mais barato ajustar
o comportamento depois (se alguém qualificado validar um enquadramento
diferente) do que descobrir tarde que "arquivar" não bastava.

---

## 7. Próximos passos (implementação — não iniciada)

1. Migração: `users.status` ganha `'excluido'` no `CHECK`; campo de
   "solicitado em" pra controlar a janela de 30 dias.
2. Backend: endpoint de solicitar exclusão (bloqueia na hora se
   `dono_user_id` de alguma marca); rotina de anonimização (roda após 30
   dias, cobrindo `users` + `identities.email` + `magic_link_tokens.email`
   — e qualquer campo pessoal novo adicionado depois); revogação em
   cascata de sessões e `admin_vinculos` no momento da confirmação.
3. Frontend: distinguir claramente "desativar pontuações" de "excluir
   conta" na UI — nunca no mesmo botão/fluxo.
4. Testes: trava de titularidade (dono não consegue excluir sem
   transferir primeiro), rotina de anonimização cobrindo as 3 tabelas,
   cancelamento dentro da janela de 30 dias revertendo o pedido.
