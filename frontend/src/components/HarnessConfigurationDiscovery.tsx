import type { HarnessConfiguration } from "../runtimeApi";

export function HarnessConfigurationDiscovery({value}: {value: HarnessConfiguration}) {
  return <details className="rounded border border-surface-200 dark:border-surface-700 p-3" data-testid="harness-configuration-discovery">
    <summary className="cursor-pointer font-semibold">Harness configuration capabilities</summary>
    <p className="mt-2">{value.adapter_id} · Version {value.version || "not checked"}</p>
    <p className="text-surface-500">This describes configuration support. It does not change the running harness. Model availability and defaults require discovery on the execution host.</p>
    <table className="w-full mt-2 text-left text-xs">
      <thead><tr><th>Setting</th><th>Core support</th><th>Available values</th></tr></thead>
      <tbody>{value.parameters.map(field => <tr key={field.name}>
        <td className="py-2">{field.label}</td>
        <td>{field.core_applies ? "Launch parameter supported" : "Integration required"}</td>
        <td>{field.availability === "observed" ? field.values.join(", ") || (field.type === 'enum' ? "No available choices" : "Observed native option") :
          field.availability === 'core_contract' ? `${field.values.join(', ') || 'Custom value'} (Core contract; host not queried)` : "Not queried on host"}</td>
      </tr>)}</tbody>
    </table>
    <p className="mt-2">Human questions: {value.human_input.core_bridge === "not_implemented" ? "Bridge not implemented" : "Bridge implemented; installed-version validation required"}.</p>
    {!value.human_input.recipient_routing_implemented && <p>Routing questions to the conversation participant is not implemented yet.</p>}
    <p>Nexus tool auto-approval is separate from harness permissions and human answers.</p>
  </details>;
}
