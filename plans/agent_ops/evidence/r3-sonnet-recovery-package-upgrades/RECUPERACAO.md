# Recuperação da conexão temporária Sonnet

Proposta JSON: `proposal.json`, SHA-256 `fca808a23bd322d9948fa89e539a3ff079bb80cfdc24fb6d8caecc7c5a2b9842`.

A transferência anterior entregou a chave uma vez, mas o Connector não a importou: o prompt de armazenamento consumiu a linha destinada à credencial. A identidade `m1-sonnet-remote` já existe, com epoch 1; o setup anterior permanece registrado como falha. Não será repetida aquela transferência.

## Exceção específica proposta

1. Permitir **armazenamento sem criptografia, protegido pela ACL do Windows**, somente para a chave de agente desta conexão temporária, em:
   `C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/campaign/connector-state/vault/secrets.json`.
2. **Revogar a chave perdida de epoch 1** por uma única rotação canônica da mesma identidade `m1-sonnet-remote`. A nova chave será importada por memória/pipe anônimo no arquivo protegido acima, sem impressão, argumento, variável de ambiente ou log.
3. Criar um novo setup `m1-sonnet-remote-setup-02` e perfil `m1-sonnet-remote-recovery02`, selecionando a mesma identidade e workspace `ws_1b0930e4c25dddad2ad1d11d903d6a52`. O setup antigo, recibos e falha serão preservados.

O plano anterior excluía armazenamento plaintext e repetição/emissão/rotação após transferência desconhecida. Esta proposta altera essas duas condições de forma explícita; não reinterpreta a execução anterior como sucesso.

## Limite do armazenamento

Antes de qualquer chave real, `secure_directory(vault_path, own_state_root)` usará o helper já qualificado para criar uma DACL protegida, sem herança externa, contendo exatamente duas entradas: SID do usuário atual e SYSTEM, controle total, herdável somente pelos filhos próprios. Reparse points/caminhos fora da raiz serão recusados. O arquivo final e arquivos temporários de gravação devem herdar essa proteção, verificada após a substituição atômica. Não serão alteradas permissões de diretórios pessoais ou globais.

O arquivo **não será criptografado**. A conta Windows e SYSTEM poderão lê-lo. Parada/uninstall normais preservam os dados: o arquivo e a validade da nova chave permanecem até uma revogação/remoção explicitamente selecionada; não há promessa de exclusão segura. Nenhuma credencial de Claude, senha ou sessão de operador será copiada para esse arquivo.

A alternativa de cofre do Windows foi testada com sentinela e serviço aleatórios próprios: gravação/leitura/remoção passaram. Porém o backend do produto usa o nome fixo `okto-nexus-connector` e lê internamente uma entrada existente desse nome antes de gravar. Essa alternativa não foi selecionada, para evitar acessar credenciais preexistentes. Nenhuma entrada pessoal foi lida no teste.

## Sequência finita e comandos

`NEW_PYTHON` já está fixado em `C:\Users\jpamb\AppData\Local\Temp\sonnet-canonical-recovery-proposal-7oq808_t\package\venv\Scripts\python.exe`. O pacote incorpora Connector `28e8093997849ba47a018e5d4728f8b3535be4b1`; W16 permanece intacto. Manifesto instalado: `a9f03ee93bfff21c5ea3fa530c4c2259180770027a0674c82fbe0fb774fa221c`. Passaram 9 testes do fix instalado, 11 testes focais do executor, um teste PTY real com sentinela e o canário de arquivo/ACL. O root verificou 1002 payloads e as três fontes alteradas entre archive/wheel/instalação. Nenhum desses testes usou credencial real ou provedor.

1. Qualificar o pacote e o canário; instalar/iniciar somente os dois serviços temporários já conhecidos e capturar as seis identidades de processo. Confirmar o operador `m1-sonnet-human` no Server próprio `http://127.0.0.1:58631`.
2. Confirmar separadamente a preferência de fallback pelo helper canônico instalado `_approve_fallback`, sem `--credential-stdin`, sem chave e sem HTTP; somente após a seleção desta proposta. Usar `OKTO_NEXUS_CONNECTOR_VAULT=file` apenas no ambiente dos processos próprios.
3. Reservar duravelmente uma única rotação e verificar identidade ativa/epoch 1/bindings ausentes. Executar pelo cliente instalado do perfil de operador:

   ```text
   POST /api/v1/agents/m1-sonnet-remote/regenerate-key
   ```

   Esse endpoint não oferece chave de idempotência/CAS. Perda da resposta bloqueia a sequência: **não há segunda tentativa automática**. A resposta sensível fica somente em memória e no pipe do consumidor abaixo.

   ```text
   NEW_PYTHON -I -B -X utf8 -m okto_nexus_connector.cli.main
     --non-interactive --json
     --state-dir C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7/campaign/connector-state
     identity add --server http://127.0.0.1:58631
     --alias m1-sonnet-remote --agent m1-sonnet-remote --credential-stdin
   ```

   O parser instalado desse comando já foi verificado sem efeito. A importação real só poderá ocorrer após os testes instalados do pacote novo e aprovação da exceção. `/me` deve corresponder à identidade e ao Server exatos antes de persistir a chave.
4. Criar draft canônico com novo request ID e as mesmas configurações selecionadas: Sonnet, effort padrão, permission mode padrão, MCP global desabilitado, `per_sender`, aprovação de ferramentas `ask`, 60 minutos/3 ações. Fazer novo `connect --plan` no operador com `--agent m1-sonnet-remote --workspace-id ws_1b0930e4c25dddad2ad1d11d903d6a52`, novo perfil e draft. Revisar `identity.mode=select`, `workspace.mode=select`, `credential.mode=reuse_existing` e epoch atual.
5. Aplicar uma vez a revisão exata. O operador produzirá um novo handoff sem emitir chave. O Connector continuará com:

   ```text
   NEW_PYTHON -I -B -X utf8 -m okto_nexus_connector.cli.main
     --non-interactive --json --state-dir OWN_STATE
     connect --setup-receipt NEW_HANDOFF --alias m1-sonnet-remote --no-start-at-login
   ```

   Não se usa `--credential-stdin` nessa etapa: resolve-se somente a identidade própria já importada. Sucesso requer os dois retornos reais, perfil canônico concluído, binding/configuração confirmados e vínculo explícito com a falha anterior; não se sobrescreve o recibo antigo.
6. Só depois do onboarding confirmado e da revisão do contexto pago, executar os trabalhos Sonnet já autorizados. Orçamento separado permanece 200k tokens observados, prevenção em 150k, máximo dois trabalhos e setup produtivo somente se canonicamente necessário. Codex continua em 579154/16. Nenhuma força de serviço está incluída; encerramento normal e provas dos seis processos continuam obrigatórios.

## Estado atual

Proposta somente: nenhuma rotação, importação de chave, novo serviço ou inferência foi executada. O teste Windows usou exclusivamente sentinela própria e a removeu. A execução real aguarda a revisão final do conjunto, a seleção desta exceção e as verificações atuais dos serviços/identidade. Os testes instalados do pacote já passaram.

## Executor concreto

Plano executável: `rotation-plan.json`, SHA-256 `5e9b827c0141d95c9b6d88cf7fec47344325449a1d85a25b43f989256e92e2c2`. Os dois comandos completos estão em `rotation-workflow.json`: primeiro `approve-storage`, depois `transfer`. Ambos exigem o hash do recibo técnico que vinculará a autorização específica recebida; esse recibo ainda não existe. O executor verifica os novos serviços/coortes, ACL, epoch 1 e identidade própria antes do único POST.

ACL própria observada somente em leitura: `connector-state` já possui DACL protegida com usuário atual e SYSTEM; `vault` herda apenas essas entradas; `secrets.json` não existe. A etapa autorizada protegerá explicitamente a DACL de `vault` e a revalidará; não altera permissões de outros diretórios.
