# R3 — compatibilidade, importação e integridade dos pacotes

RG-06, RG-07 e RG-08 qualificados no snapshot atual Windows; AC-07 atendido pelas fronteiras verificadas e dependências reproduzíveis. Nenhum código de aplicação ou wheel mudou. Documentação de conexão inclui a matriz de versões; guia da campanha Windows passa a apontar a proposta vigente ainda não autorizada/não executada.

## Compatibilidade instalada

Quatro pares executados via GET público real `/v1/connections/protocol`: Connector 0.0.11/Core 0.0.13 com Nexus 0.3.2/Core 0.0.13, e Connector 0.0.12/Core 0.0.14 com Nexus 0.3.3/Core 0.0.14, são compatíveis. Os dois pares cruzados recusam `VERSION_INCOMPATIBLE`, stage `protocol`, `possible_effect=false`. A igualdade da revisão de wire não dispensa igualdade da versão Core.

Foram exatamente quatro GETs, sem credenciais, query ou corpo. As 143 tabelas do servidor antigo e 160 do atual permaneceram idênticas; fixtures HTTP saíram normalmente e seus PIDs reais estavam ausentes. Aplicação instalada e SQLite reais, com lifespan nativo desligado. Não são execução autenticada, provider, serviço nativo, cliente MCP externo, TLS ou M1/M2. Histórico foi construído de commits exatos em Temp; tentativas de preparação recusadas estão preservadas. Não houve downgrade de banco pessoal nem alteração das cercas de compatibilidade.

## Imports e fronteiras

131 módulos Core importados sob guards ativos; 165 arquivos iguais entre fonte, wheel e instalação. Auditoria complementar usa ambiente/home sintéticos, sem valores de credencial, stdin DEVNULL, stdout bruto retido e nove controles negativos. Zero evento proibido, lookup originado no Core ou chamada às 19 APIs nativas guardadas. Os 255 lookups benignos de dependências (oito pares nome/caller) e nove bindings de console Click ficam explícitos. Recusas iniciais de GetStdHandle foram preservadas; a exceção final permite apenas console/buffer revisados.

As fontes Nexus (513 Python) e Connector (122 Python) não importam a aplicação irmã; quatro chamadas dinâmicas foram revisadas e ficam no próprio namespace. O verificador Core recusa dependências não declaradas e cargas dinâmicas fora do registro. A auditoria cobre o código/import observado e as superfícies instrumentadas; não é tracer universal de extensões C/syscalls ou qualificação de execução nativa.

## Empacotamento e rastreabilidade

Nexus: 690 arquivos, incluindo 167 migrações e sete recursos UI. Connector: 123 arquivos. Core: 165 arquivos, incluindo 31 schemas e dois recursos JS. Nenhum recurso-fonte omitido; payloads iguais aos artefatos instalados/candidatos atuais. A instalação CI declarada com MCP 1.30.0 e pip check aprovado permanece a prova de dependências; o browser histórico em MCP 1.29.1 continua só como evidência das interações observadas.

Revisão somente leitura verificou 1.384 entradas de manifests (incluindo sobreposições), 724 referências locais e as 71 identidades aprovadas do milestone anterior. Os 22 casos de proteção mapeados são evidência histórica de oito funções, não novas execuções. Dois arquivos de proveniência Herdr fora do manifesto principal estão inventariados no suplemento público; nenhum dado privado foi acrescentado.

RG-09 permanece em progresso: mixed e modos de sessão têm allowlists explícitas; RG03/RG05 usam fixtures temporárias mas herdaram ambiente, limite que não é apagado por outra campanha mais forte. AC-09 permanece pendente da reconciliação final de tarefas/cenários nomeados, em execução somente leitura. AC-10 mantém o limite de credencial histórica/commits anteriores já registrado. RG-05 continua parcial; M1/M2, clientes reais, provedor e campanhas nativas continuam abertos. Nenhum novo requisito de tracer universal, TLS/dois hosts ou plataforma adicional foi criado.

Reprodução e prova: compatibility/qualification.json, core/report.json, core/stdout.json e traceability/traceability.json. Os manifests de origem são preservados; o manifesto deste diretório liga todos os bytes públicos. O plano fixo e IDs 59/132/28/17 permanecem iguais.
