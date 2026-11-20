# SI-T-C10 — Reorientação indisponível durante um turno ativo

O ensaio retirou apenas o suporte à reorientação de um adaptador simulado com turno ativo. O catálogo retornou o motivo da indisponibilidade e preservou as opções explícitas de interromper e de enfileirar um novo turno. A API direta e a rota de comandos receberam pedidos concorrentes. Ambas recusaram a reorientação e a consulta por recibo retornou HTTP 404.

O armazenamento conservou apenas a abertura e o envio originais. O peer confirmou um único envio, sem interrupção ou mensagem substituta. A restauração do suporte na fixture permitiu retomar o cenário de reorientação autorizada. [Resultados e hashes](si010-unqualified-steer.json)

Passaram 20 testes com os wheels instalados. O ensaio usou as rotas HTTP autenticadas e um peer de protocolo simulado. A mudança se restringe a teste e evidência, dispensa migração e pode ser retirada revertendo o commit.
