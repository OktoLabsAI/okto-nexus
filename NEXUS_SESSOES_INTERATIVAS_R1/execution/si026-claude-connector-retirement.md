# SI-026 — Comprovante local do Claude após fechamento pelo Connector

O Connector observa o histórico por meio do owner do Core enquanto o processo ainda está vivo. O Core confere o lease, o processo, a abertura e a sessão antes e depois da leitura. O adaptador usa o último diálogo comprovado pelo próprio processo. Um turno ativo, uma decisão pendente ou uma identidade divergente impedem a captura.

Depois que o fechamento canônico confirma a saída, o Connector liga a prova à abertura, ao recibo de fechamento e à liberação da vaga. A configuração revisada precisa coincidir com a usada na abertura. O verificador aceita as alterações de metadados de custo produzidas pelo binário revisado durante seu encerramento. Alterações do diálogo ou substituição do arquivo invalidam o comprovante. O registro e os caminhos ficam no Connector.

Dois ensaios finais com Claude Code 2.1.328 real em ConPTY passaram no Windows. O primeiro gravou a prova do diálogo exato, e uma leitura após a saída do daemon conferiu novamente arquivo, perfil e integridade do SQLite. No segundo, uma alteração no arquivo após a saída do Claude impediu a gravação. Os dois fechamentos retornaram `SUCCEEDED`. Os ensaios iniciais recusaram a leitura durante o turno ativo, mas terminaram sem prova mesmo para o arquivo intacto. A causa exata ficou em aberto. [Resultados, tentativas e hashes](si026-claude-connector-retirement.json)

Passaram 100 testes do Core, 128 do Connector e 83 do Nexus nos wheels instalados. O ensaio de regressão com o Codex 0.157.0 real também passou pela retomada da thread exata, recuperação do recibo e fechamento da sucessora. Os modelos foram simulados em loopback.

O histórico capturado prepara a retomada salva do Claude via Connector. A negociação da consulta e a abertura exclusiva da sucessora ainda precisam ser ligadas ao CLI. Esta etapa acrescenta uma tabela local na revisão 6 do banco do Connector. A reversão usa os commits e pins anteriores em conjunto.
