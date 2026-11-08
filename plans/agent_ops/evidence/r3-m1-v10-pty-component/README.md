# Helper PTY v10 — preparação sintética

Esta revisão mantém v5 intacto e acrescenta dois gates públicos, em ordem:
`producer` antes do spawn PTY e `consumer` antes do Popen/entrega única da chave.
O callback `effect_guard(phase)` precisa devolver exatamente `True`; ausência,
negação, exceção ou resposta após o prazo impedem aquele lançamento.

`deadline_monotonic` compartilha o prazo absoluto do monitor proprietário.
O helper usa o menor entre esse prazo e `now + timeout_seconds`. O callback
deve ser limitado pelo mesmo prazo e deve encaminhar a decisão ao owner;
o helper não autoriza escrever no controller a partir da thread de transferência.

A chave sintética permanece na memória do worker e no stdin do consumidor.
O canal parent/worker contém apenas spec sem segredo, dois pedidos/respostas de
gate e um resultado público limitado. A ordem, os tipos, o tamanho das linhas
e a ausência de material nesse canal são verificados. Continua obrigatório
observar o bloco único da chave e o marcador exato de handoff antes do consumidor.

Os gates não são uma operação atômica com o SO e não cancelam um CLI já iniciado.
Uma recusa após o produtor preserva `possible_effect`; ausência de resultado
não prova ausência de entrega. Não há replay ou segunda tentativa de consumidor.
A limpeza forçada alcança somente o Job dos auxiliares desta transferência,
nunca serviço Scheduler ou sessão produtiva. `TRANSFERRED_ONCE` exige os dois
exits 0, Job vazio, leitores encerrados e nenhuma limpeza forçada.

Qualificação: 20 casos distintos passaram nos bytes finais do helper
(19 em attempt-002 e o caso de marcador ausente em attempt-003). A primeira
tentativa foi preservada com falha do probe de origem da extensão. O prazo de
4s da fixture de marcador ausente expirou antes de o produtor iniciar; esse
resultado também foi preservado. Somente essa fixture foi repetida com 15s
para alcançar o estado de marcador ausente; o limite operacional não mudou.

Foram usados processos Python sintéticos e as funções instaladas
`material_sink`/`handoff_sink`, sem CLI de produto, conta, credencial real,
serviço ou provedor. O fluxo cooperativo comprovou os três streams TTY,
janela não visível, produtor esperando o consumidor, uma entrega, identidade
exata dos processos no Job e material ausente dos arquivos/resultados.

O pywinpty 3.0.3 vem do prefixo anteriormente qualificado, somente leitura;
seus 12 payloads e as origens efetivas foram conferidos. `owned_job.py` é
byte-idêntico ao v5. A composição real com a fila do monitor remoto precisa
da qualificação própria do bundle e da autorização futura da campanha.
