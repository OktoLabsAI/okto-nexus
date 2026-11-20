# SI-T-E09 — Foco e rascunho durante a resposta

O Edge abriu pela Home a conversa exata de um app-server Codex 0.157.0
mantido pelo Connector em Windows. O teste usou os três wheels instalados,
o dashboard empacotado, um login de operador descartável e um provedor
determinístico em loopback. A página de histórico e a conexão SSE usaram
o servidor, executor, projeto e sessão esperados.
[Comandos, hashes e checkpoints](si017-live-draft-focus.json)

1. Com um turno ativo, o editor recebeu um rascunho e uma seleção pelo
   teclado. O primeiro fragmento da resposta foi mostrado sem mudar o
   editor, o foco, o texto, a seleção ou o endereço da conversa.
2. O roteiro digitou mais texto e selecionou outro trecho. O segundo
   fragmento apareceu e preservou o novo rascunho e a seleção. Após mais
   uma edição, o navegador mostrou o texto final e o aviso de conclusão.
   O foco e o rascunho ainda estavam no mesmo editor.
3. A API registrou dois acréscimos e uma substituição final com a mesma
   identidade de mensagem. O SQLite confirmou uma sessão fechada, um
   lançamento nativo, um turno, um resultado e zero entradas para o
   rascunho. O fechamento canônico terminou o app-server.

O cenário no navegador real, 20 verificações de componentes e 28 testes
de API e transcript passaram. As verificações de componentes reproduziram
os avisos de `useLayoutEffect` da renderização no servidor. O primeiro
ensaio recebeu `PROFILE_DRIFT` com a fixture de configuração embutida antes
de abrir o Codex. A execução concluída usou o perfil revisado via Connector.

O ledger registra `PASS` para SI-T-E09. A validação com leitor de tela,
a aceitação manual e a campanha com provedor real continuam pendentes.
Este incremento registra evidências e dispensa migração. A reversão usa
o próprio commit.
