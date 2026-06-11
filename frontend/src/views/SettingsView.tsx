// Settings: appearance, hub info and store maintenance - including the
// "wipe database" action (POST /api/v1/admin/reset), double-guarded by the
// confirm dialog and an explicit keep-agents choice.

import { useEffect, useState } from "react";
import { Database, Eraser, Moon, Sun, Trash2 } from "lucide-react";
import { api } from "../api";
import { useConfirm } from "../components/Confirm";
import { useTheme } from "../hooks/useTheme";

export function SettingsView() {
  const { theme, toggle } = useTheme();
  const { confirm, dialog } = useConfirm();
  const [info, setInfo] = useState<Record<string, unknown> | null>(null);
  const [keepAgents, setKeepAgents] = useState(true);
  const [report, setReport] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .info()
      .then((data) => setInfo(data as Record<string, unknown>))
      .catch(() => undefined);
  }, []);

  const runPrune = async (dryRun: boolean) => {
    try {
      const result = await api.prune(dryRun);
      setReport(
        (dryRun ? "Prune (simulação): " : "Prune executado: ") +
          JSON.stringify(result),
      );
      setError(null);
    } catch (exc) {
      setError((exc as Error).message);
    }
  };

  return (
    <div className="h-full overflow-y-auto p-6">
      {dialog}
      <div className="max-w-2xl mx-auto space-y-4">
        {/* Appearance */}
        <section className="panel p-5 space-y-3">
          <h2 className="font-display font-semibold text-sm">Aparência</h2>
          <div className="flex items-center justify-between text-sm">
            <span className="text-surface-600 dark:text-surface-400">
              Tema da interface
            </span>
            <button className="btn btn-secondary" onClick={toggle}>
              {theme === "dark" ? <Sun size={14} /> : <Moon size={14} />}
              {theme === "dark" ? "Mudar para claro" : "Mudar para escuro"}
            </button>
          </div>
        </section>

        {/* Hub info */}
        <section className="panel p-5 space-y-3">
          <h2 className="font-display font-semibold text-sm flex items-center gap-2">
            <Database size={14} /> Hub
          </h2>
          {info ? (
            <div className="grid grid-cols-3 gap-2 text-xs">
              <Info label="versão" value={String(info.package_version ?? "—")} />
              <Info label="schema" value={`v${info.schema_version ?? "—"}`} />
              <Info label="trust mode" value={String(info.trust_mode ?? "—")} />
            </div>
          ) : (
            <p className="text-xs text-surface-500">carregando…</p>
          )}
        </section>

        {/* Maintenance */}
        <section className="panel p-5 space-y-4">
          <h2 className="font-display font-semibold text-sm flex items-center gap-2">
            <Eraser size={14} /> Manutenção do banco
          </h2>

          <div className="flex items-center justify-between text-sm">
            <div>
              <div className="text-surface-700 dark:text-surface-300">
                Prune (retenção)
              </div>
              <p className="text-xs text-surface-500 dark:text-surface-500">
                Remove eventos antigos, deliveries lidas e sessões fechadas
                conforme as janelas de retenção.
              </p>
            </div>
            <div className="flex gap-2 shrink-0">
              <button className="btn btn-secondary" onClick={() => runPrune(true)}>
                Simular
              </button>
              <button className="btn btn-secondary" onClick={() => runPrune(false)}>
                Executar
              </button>
            </div>
          </div>

          <div className="border-t border-surface-200/60 dark:border-surface-700/50 pt-4">
            <div className="flex items-start justify-between gap-4 text-sm">
              <div>
                <div className="text-red-600 dark:text-red-400 font-medium">
                  Zerar banco de dados
                </div>
                <p className="text-xs text-surface-500 mt-1">
                  Apaga TODAS as mensagens, entregas, handoffs, sessões,
                  eventos, canais e workspaces (com VACUUM). Irreversível.
                </p>
                <label className="flex items-center gap-2 mt-2 text-xs text-surface-600 dark:text-surface-400">
                  <input
                    type="checkbox"
                    checked={keepAgents}
                    onChange={(e) => setKeepAgents(e.target.checked)}
                    className="accent-accent-500"
                  />
                  Preservar agentes e chaves de API (recomendado)
                </label>
              </div>
              <button
                className="btn btn-danger shrink-0"
                data-testid="reset-db"
                onClick={() =>
                  confirm({
                    title: "Zerar o banco de dados?",
                    body: (
                      <span>
                        Todo o histórico operacional será apagado
                        permanentemente.{" "}
                        {keepAgents ? (
                          <b>Agentes e chaves serão preservados.</b>
                        ) : (
                          <b className="text-red-500">
                            Agentes e chaves TAMBÉM serão apagados — todos os
                            clientes MCP perderão acesso.
                          </b>
                        )}
                      </span>
                    ),
                    onConfirm: async () => {
                      try {
                        const result = await api.reset(keepAgents);
                        setReport("Banco zerado: " + JSON.stringify(result));
                        setError(null);
                      } catch (exc) {
                        setError((exc as Error).message);
                      }
                    },
                  })
                }
              >
                <Trash2 size={14} /> Zerar…
              </button>
            </div>
          </div>

          {report && (
            <pre className="text-[11px] bg-surface-100 dark:bg-surface-900 rounded-lg p-2 overflow-x-auto text-surface-600 dark:text-surface-400">
              {report}
            </pre>
          )}
          {error && <p className="text-xs text-red-500">{error}</p>}
        </section>
      </div>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-surface-100 dark:bg-surface-900 rounded-lg p-2 text-center">
      <div className="font-mono text-surface-700 dark:text-surface-300">{value}</div>
      <div className="text-[10px] text-surface-500">{label}</div>
    </div>
  );
}
