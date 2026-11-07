## 2026-11-07 — contenção M1 autorizada e limpeza concluída

O usuário respondeu “Autorizar essa parada forçada” à proposta concreta da
geração `188be445d44e96d483336ee424008e56`, PID 45144. Após reconferir tarefa,
PID/birth, geração, digest, pacotes históricos e deadline, foi emitido um único
stop --force vinculado à geração. O comando retornou zero e a saída do processo
foi confirmada; somente então foi executado o uninstall já previsto, também
com retorno zero. A tarefa Nexus está ausente, a tarefa Connector M1 nunca foi
instalada e a porta 64507 está livre. Dados e journals foram preservados.

Não houve replay, reset do controlador, hotpatch, término genérico ou inferência
adicional. O total permanece duas admissões e 45.843 tokens mínimos observados;
o fault permanente e o claim histórico pendente continuam retidos. Esta
contenção forçada não comprova parada cooperativa nem transforma o trabalho
cancelado em M1 aceito. A campanha real está encerrada e limpa, porém parcial.

A correção separada do Core foi qualificada e enviada em `830f7ce`; os dois
consumidores receberam o mesmo wheel em Nexus `f44ca088` e Connector `c100002`.
Esses bytes novos não foram aplicados ao processo M1 histórico durante sua vida.
A evolução do plano permanece registrada sem promover os critérios pendentes.
Evidência: `plans/agent_ops/evidence/r3-m1-authorized-containment/closure/summary.json`.
