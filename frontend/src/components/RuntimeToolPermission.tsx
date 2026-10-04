import { useEffect, useState } from "react";
import { api } from "../api";

export function RuntimeToolPermission({endpoint, onUpdated}: {endpoint: string; onUpdated: () => void}) {
  const [policy, setPolicy] = useState<{revision: number; mode: "ask" | "always_allow"} | null>(null);
  const [mode, setMode] = useState<"ask" | "always_allow">("ask");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    setPolicy(null); setError("");
    api.runtimeToolPermission(endpoint).then(result => {
      if (active) {setPolicy(result); setMode(result.mode);}
    }).catch(failure => {if (active) setError(String(failure));});
    return () => {active = false;};
  }, [endpoint, revision]);
  return <section aria-label="Nexus tool permissions" className="space-y-2 rounded border p-3">
    <h5 className="font-semibold">Permissão para tools / MCP do Nexus</h5>
    <label className="block">Chamadas do agente via runtime
      <select className="block rounded border p-2 bg-white dark:bg-surface-800" value={mode} disabled={busy || !policy}
        onChange={event => {setMode(event.target.value as typeof mode); setNotice("");}}>
        <option value="ask">Solicitar aprovação do harness</option>
        <option value="always_allow">Sempre permitir</option>
      </select>
    </label>
    <p>“Sempre permitir” libera as chamadas ao servidor Nexus desta integração sem aprovação do harness. As permissões do agente e as políticas do Nexus continuam valendo. No Pi, as ferramentas nativas já não solicitam aprovação do harness.</p>
    <p>Feche as sessões runtime antes de alterar. Depois de salvar, autorize a execução novamente; a opção será aplicada às novas sessões.</p>
    <button className="btn btn-secondary" disabled={busy || !policy || mode === policy.mode} onClick={async () => {
      if (!policy) return;
      setBusy(true); setError(""); setNotice("");
      try {
        const result = await api.saveRuntimeToolPermission(endpoint, {expected_revision: policy.revision, mode});
        setPolicy(result); setNotice("Permissão salva. Autorize a execução para iniciar uma nova sessão."); onUpdated();
      } catch (failure) {setError(String(failure));}
      finally {setBusy(false);}
    }}>Salvar permissão</button>
    <button className="btn btn-secondary" disabled={busy} onClick={() => setRevision(value => value + 1)}>Recarregar</button>
    {notice && <p role="status">{notice}</p>}{error && <p role="alert">{error}</p>}
  </section>;
}
