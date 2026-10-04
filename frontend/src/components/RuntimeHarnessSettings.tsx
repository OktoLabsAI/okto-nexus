import { useEffect, useState } from "react";
import { api } from "../api";
import type { HarnessConfiguration } from "../runtimeApi";
import { harnessFieldValues, harnessSelectionError, parseHarnessConfigurationFile, harnessConfigurationFile } from '../harnessConfiguration';

export function RuntimeHarnessSettings({endpoint, schema, onUpdated}: {
  endpoint: string; schema: HarnessConfiguration; onUpdated: () => void;
}) {
  const [saved, setSaved] = useState<{revision: number; settings: Record<string,string>} | null>(null);
  const [values, setValues] = useState<Record<string,string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let live = true;
    setSaved(null); setError(""); setNotice(""); setValues({});
    api.runtimeHarnessSettings(endpoint).then(result => {if(live){setSaved(result);setValues(result.settings);}})
      .catch(reason => {if(live) setError(String(reason));});
    return () => {live = false;};
  }, [endpoint, reload]);
  const selectionError = harnessSelectionError(schema, values);
  return <section aria-label="Harness settings" className="space-y-3 rounded border p-3">
    <h5 className="font-semibold">Configuração do harness</h5>
    <p>Aplicada às novas sessões deste agente. Feche as sessões existentes antes de salvar.</p>
    <label className="block">Carregar configuração de arquivo JSON
      <input type="file" accept=".json,application/json" aria-label="Carregar configuração de arquivo JSON"
        disabled={busy || !saved} onChange={async event => {
          const input = event.currentTarget;
          const file = input.files?.[0];
          input.value = '';
          if (!file) return;
          setError(''); setNotice('');
          try {
            if (file.size > 65536) throw new Error('O arquivo deve ter no máximo 64 KiB.');
            setValues(parseHarnessConfigurationFile(await file.text(), schema));
            setNotice('Arquivo carregado. Revise os parâmetros e clique em Salvar configuração do harness.');
          } catch (reason) {setError(String(reason));}
        }} />
    </label>
    <button className="btn btn-secondary" disabled={busy || !saved || !!selectionError} onClick={() => {
      const url = URL.createObjectURL(new Blob([harnessConfigurationFile(schema.adapter_id, values)], {type:'application/json'}));
      const link = document.createElement('a'); link.href = url; link.download = `${schema.adapter_id}.harness.json`;
      link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    }}>Exportar configuração JSON</button>
    {schema.parameters.filter(p => p.core_applies).map(field => <label key={field.name} className="block">
      {field.label}
      {field.type === 'enum' ? <select aria-label={field.label} className="block w-full border rounded p-2 bg-white dark:bg-surface-800"
        disabled={busy || !saved} value={values[field.name] || ""} onChange={e => setValues(old => ({...old,[field.name]: e.target.value}))}>
        <option value="">Padrão{field.default != null ? ` (${String(field.default)})` : " do harness"}</option>
        {!!values[field.name] && !harnessFieldValues(schema, field.name, values).includes(values[field.name]) &&
          <option value={values[field.name]}>{values[field.name]} (indisponível nesta seleção)</option>}
        {harnessFieldValues(schema, field.name, values).map(value => <option key={value} value={value}>{value}</option>)}
      </select> : <input aria-label={field.label} className="block w-full border rounded p-2 bg-white dark:bg-surface-800" maxLength={200}
        placeholder="Padrão do harness" disabled={busy || !saved} value={values[field.name] || ""}
        onChange={e => setValues(old => ({...old,[field.name]: e.target.value}))} />}
    </label>)}
    <p>Permissões nativas, sandbox e aprovação das ferramentas Nexus são configurações independentes. Perguntas ao interlocutor exigem uma resposta própria.</p>
    {selectionError && <p role="alert">{selectionError}</p>}
    <button className="btn btn-secondary" disabled={busy || !saved || !!selectionError} onClick={async () => {
      if(!saved) return;
      setBusy(true); setError(""); setNotice("");
      try {
        const settings = Object.fromEntries(Object.entries(values).filter(([,value]) => value !== ""));
        const result = await api.saveRuntimeHarnessSettings(endpoint, {expected_revision:saved.revision,settings});
        setSaved(result);setValues(result.settings);setNotice("Configuração salva. Autorize a execução para iniciar uma nova sessão.");onUpdated();
      } catch(reason) {setError(String(reason));} finally {setBusy(false);}
    }}>Salvar configuração do harness</button>
    <button className="btn btn-secondary" disabled={busy} onClick={() => setReload(value => value + 1)}>Recarregar configuração</button>
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
  </section>;
}
